"""Every setting the app has, with its default, saved as JSON in the data folder.

API keys are kept in the operating system's own password store (Windows
Credential Manager, macOS Keychain, the Secret Service on Linux) through
`keyring`, so there is no key file a program started by the AI could read.
Where no such store works, they fall back to `secrets.json` (owner-only on
macOS and Linux). Either way they are never sent back to the window: it is
only told whether one is saved.
"""

import os
import re
import threading
import urllib.parse

from aetheris_everyone import paths

DEFAULTS = {
    "language": "auto",          # auto | ko | en
    "theme": "auto",             # auto | light | dark
    "accepted_terms": False,
    "setup_done": False,
    "provider": "ollama",        # ollama | anthropic | openai | gemini
    "models": {"ollama": "", "anthropic": "", "openai": "", "gemini": ""},
    "ollama_host": "http://127.0.0.1:11434",
    "work_folder": "",
    "safety": "balanced",        # ask | balanced | auto
    "careful": False,            # plan -> do -> check, and let the model think
    "context_tokens": 16384,     # Ollama only: how much the local model keeps in view
    "allow_commands": False,     # whether the AI may run programs at all (run_command)
    "memory": True,              # whether the AI may remember things between chats
    "search_engine": "auto",     # auto | searxng
    "searxng_url": "",           # base address of the person's own SearXNG
}

SAFETY_LEVELS = ("ask", "balanced", "auto")
PROVIDERS = ("ollama", "anthropic", "openai", "gemini")
SEARCH_ENGINES = ("auto", "searxng")


def clean_url(value) -> str | None:
    """An http(s) base address without a trailing slash, "" for empty, None if invalid."""
    text = str(value or "").strip().rstrip("/")
    if not text:
        return ""
    if "://" not in text:
        if re.match(r"^[A-Za-z][\w+.-]*:(?!\d)", text):     # another scheme, e.g. "javascript:"
            return None
        text = "http://" + text                              # "192.168.0.2:11434"
    parsed = urllib.parse.urlparse(text)
    try:
        parsed.port
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    return text

_lock = threading.RLock()
_cache: dict | None = None


def _settings_path() -> str:
    return os.path.join(paths.data_dir(), "settings.json")


def _secrets_path() -> str:
    return os.path.join(paths.data_dir(), "secrets.json")


def load() -> dict:
    global _cache
    with _lock:
        if _cache is None:
            saved = paths.read_json(_settings_path(), {}) or {}
            merged = {**DEFAULTS, **{k: v for k, v in saved.items() if k in DEFAULTS}}
            merged["models"] = {**DEFAULTS["models"], **(saved.get("models") or {})}
            if merged["safety"] not in SAFETY_LEVELS:
                merged["safety"] = DEFAULTS["safety"]
            if merged["provider"] not in PROVIDERS:
                merged["provider"] = DEFAULTS["provider"]
            if merged["search_engine"] not in SEARCH_ENGINES:
                merged["search_engine"] = DEFAULTS["search_engine"]
            merged["allow_commands"] = merged["allow_commands"] is True
            merged["memory"] = merged["memory"] is True
            _cache = merged
        return dict(_cache, models=dict(_cache["models"]))


def update(changes: dict) -> dict:
    """Apply the known keys of `changes`, save, and return the new settings."""
    global _cache
    with _lock:
        current = load()
        for key, value in changes.items():
            if key not in DEFAULTS:
                continue
            if key == "models" and isinstance(value, dict):
                current["models"].update({k: str(v) for k, v in value.items()
                                          if k in PROVIDERS})
            elif key == "safety" and value not in SAFETY_LEVELS:
                continue
            elif key == "provider" and value not in PROVIDERS:
                continue
            elif key == "context_tokens":
                try:
                    current[key] = max(2048, min(262144, int(value)))
                except (TypeError, ValueError):
                    pass
            elif key in ("allow_commands", "memory"):
                current[key] = value is True
            elif key == "search_engine" and value not in SEARCH_ENGINES:
                continue
            elif key in ("ollama_host", "searxng_url"):
                url = clean_url(value)
                if url is None:
                    continue
                current[key] = url or DEFAULTS[key]
            else:
                current[key] = value
        paths.write_json(_settings_path(), current)
        _cache = current
        return load()


def get(key: str):
    return load().get(key)


def model_for(provider: str) -> str:
    return (load()["models"].get(provider) or "").strip()


# -- API keys ----------------------------------------------------------------

_ENV_KEYS = {
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
}


ENV_KEY_NAMES = tuple(name for names in _ENV_KEYS.values() for name in names)
KEYRING_SERVICE = "Aetheris Everyone"


class FileStore:
    """Keys in `secrets.json`: the fallback where no system password store works."""

    kind = "file"

    def get(self, provider: str) -> str:
        return (paths.read_json(_secrets_path(), {}) or {}).get(provider, "")

    def set(self, provider: str, key: str) -> None:
        secrets = paths.read_json(_secrets_path(), {}) or {}
        if key:
            secrets[provider] = key
        else:
            secrets.pop(provider, None)
        paths.write_json(_secrets_path(), secrets, private=True)


class KeyringStore:
    """Keys in the operating system's password store, through `keyring`."""

    kind = "keychain"

    def __init__(self, backend):
        self.backend = backend

    def get(self, provider: str) -> str:
        return self.backend.get_password(KEYRING_SERVICE, provider) or ""

    def set(self, provider: str, key: str) -> None:
        if key:
            self.backend.set_password(KEYRING_SERVICE, provider, key)
            return
        try:
            self.backend.delete_password(KEYRING_SERVICE, provider)
        except Exception:            # nothing saved under that name
            pass


def _system_keyring():
    """The usable system password store, or None (not installed, none running, turned off)."""
    if os.environ.get("AETHERIS_EVERYONE_KEYRING", "").strip().lower() in ("off", "file", "0"):
        return None
    try:
        import keyring
        from keyring.backends import fail, null
        backend = keyring.get_keyring()
        if isinstance(backend, (fail.Keyring, null.Keyring)):
            return None
        backend.get_password(KEYRING_SERVICE, "probe")      # a locked or broken store fails here
        return backend
    except Exception:
        return None


_store = None


def _migrate(store: KeyringStore) -> None:
    """Move keys saved by an older version from `secrets.json` into the password store."""
    path = _secrets_path()
    saved = paths.read_json(path, {}) or {}
    if not saved:
        return
    for provider, key in list(saved.items()):
        try:
            if key:
                store.set(provider, key)
                if store.get(provider) != key:
                    return
        except Exception:
            return                   # keep the file; nothing is lost
    paths.write_json(path, {}, private=True)
    try:
        os.remove(path)
    except OSError:
        pass


def secret_store():
    global _store
    with _lock:
        if _store is None:
            backend = _system_keyring()
            if backend is not None:
                _store = KeyringStore(backend)
                _migrate(_store)
            else:
                _store = FileStore()
        return _store


def use_store(store) -> None:
    """Replace where keys are kept (tests); None goes back to choosing automatically."""
    global _store
    with _lock:
        _store = store
        if isinstance(store, KeyringStore):
            _migrate(store)


def key_storage() -> str:
    return secret_store().kind


def api_key(provider: str) -> str:
    with _lock:
        try:
            saved = secret_store().get(provider)
        except Exception:
            saved = ""
    if saved:
        return saved
    for name in _ENV_KEYS.get(provider, ()):
        if os.environ.get(name, "").strip():
            return os.environ[name].strip()
    return ""


def set_api_key(provider: str, key: str) -> None:
    if provider not in _ENV_KEYS:
        return
    with _lock:
        secret_store().set(provider, (key or "").strip())


def has_keys() -> dict:
    return {name: bool(api_key(name)) for name in _ENV_KEYS}


def reset_cache() -> None:
    """Forget what was read, so the next `load` reads the file (tests)."""
    global _cache, _store
    with _lock:
        _cache = None
        _store = None
