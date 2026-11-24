"""Standing rules the person writes for one work folder.

Like Aetheris's per-project instructions file, but kept in the app's data
folder (nothing is added to the person's folder) and written in a form in the
window: "file names start with the date", "reports go in the 보고서 folder".
Every chat that works in that folder is given them.
"""

import os
import threading

from aetheris_everyone import paths

MAX_CHARS = 4000
_lock = threading.Lock()


def _path() -> str:
    return os.path.join(paths.data_dir(), "folder_rules.json")


def _key(folder: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.expanduser(str(folder or ""))))


def _all() -> dict:
    data = paths.read_json(_path(), {})
    return data if isinstance(data, dict) else {}


def get(folder: str) -> str:
    if not folder:
        return ""
    text = _all().get(_key(folder), "")
    return text if isinstance(text, str) else ""


def put(folder: str, text: str) -> str:
    """Save (or, with empty text, remove) the rules for `folder`. Returns what was kept."""
    text = str(text or "").strip()[:MAX_CHARS]
    with _lock:
        data = _all()
        if text:
            data[_key(folder)] = text
        else:
            data.pop(_key(folder), None)
        paths.write_json(_path(), data)
    return text
