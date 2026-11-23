"""Where the app keeps its own files, and crash-safe writes into it."""

import json
import os
import sys
import tempfile


def data_dir() -> str:
    """The per-user folder for settings, conversations and undo history.

    `AETHERIS_EVERYONE_HOME` overrides it - the tests use that so they never
    touch a real profile.
    """
    override = os.environ.get("AETHERIS_EVERYONE_HOME", "").strip()
    if override:
        base = override
    elif sys.platform == "win32":
        base = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"),
                            "AetherisEveryone")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support/AetherisEveryone")
    else:
        root = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
        base = os.path.join(root, "aetheris-everyone")
    os.makedirs(base, exist_ok=True)
    return base


def sub(*parts: str) -> str:
    path = os.path.join(data_dir(), *parts)
    os.makedirs(path, exist_ok=True)
    return path


def resource(*parts: str) -> str:
    """A file shipped with the app, whether running from source or frozen."""
    root = getattr(sys, "_MEIPASS", None)
    if root:
        return os.path.join(root, "aetheris_everyone", *parts)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), *parts)


def write_text(path: str, text: str, private: bool = False) -> None:
    """Write through a temporary file, so a crash never leaves half a file."""
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        if private and sys.platform != "win32":
            os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_json(path: str, data, private: bool = False) -> None:
    write_text(path, json.dumps(data, ensure_ascii=False, indent=1), private)


def read_json(path: str, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def default_work_folder() -> str:
    """`Documents/Aetheris` - somewhere a person will find it again."""
    home = os.path.expanduser("~")
    for name in ("Documents", "문서", "My Documents"):
        candidate = os.path.join(home, name)
        if os.path.isdir(candidate):
            return os.path.join(candidate, "Aetheris")
    return os.path.join(home, "Aetheris")
