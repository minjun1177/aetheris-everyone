"""Every setting the app has, with its default, saved as JSON in the data folder.

API keys are kept apart in `secrets.json` (owner-only on macOS and Linux) and
are never sent back to the window: it is only told whether one is saved.
"""

import os
import threading

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
}

SAFETY_LEVELS = ("ask", "balanced", "auto")
PROVIDERS = ("ollama", "anthropic", "openai", "gemini")

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


def api_key(provider: str) -> str:
    with _lock:
        saved = (paths.read_json(_secrets_path(), {}) or {}).get(provider, "")
    if saved:
        return saved
    for name in _ENV_KEYS.get(provider, ()):
        if os.environ.get(name, "").strip():
            return os.environ[name].strip()
    return ""


def set_api_key(provider: str, key: str) -> None:
    with _lock:
        secrets = paths.read_json(_secrets_path(), {}) or {}
        if key:
            secrets[provider] = key.strip()
        else:
            secrets.pop(provider, None)
        paths.write_json(_secrets_path(), secrets, private=True)


def has_keys() -> dict:
    return {name: bool(api_key(name)) for name in _ENV_KEYS}


def reset_cache() -> None:
    """Forget what was read, so the next `load` reads the file (tests)."""
    global _cache
    with _lock:
        _cache = None
