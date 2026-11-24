"""What the AI remembers about the person, from one chat to the next.

Carried over from Aetheris's important memories: a few standing facts (a
name, how documents should look, a preference) written into the prompt of
every chat, so the model has them from the first message instead of being
told again. Each one is saved only after the person allows it, can be seen
and deleted in Settings, and the whole feature can be turned off there.
"""

import os
import threading
import time
import uuid

from aetheris_everyone import paths

MAX_ITEMS = 50
MAX_TEXT = 300
PROMPT_CHARS = 3000

_lock = threading.Lock()


def _path() -> str:
    return os.path.join(paths.data_dir(), "memory.json")


def load() -> list:
    """Every memory, oldest first: [{"id", "text", "time"}]."""
    data = paths.read_json(_path(), [])
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)
            and isinstance(item.get("id"), str) and isinstance(item.get("text"), str)]


def clean(text) -> str:
    return " ".join(str(text or "").split())[:MAX_TEXT]


def add(text: str) -> dict:
    """Save `text` (or find it already saved). Raises ValueError when it cannot."""
    text = clean(text)
    if not text:
        raise ValueError("there is nothing to remember")
    with _lock:
        items = load()
        for item in items:
            if item["text"].lower() == text.lower():
                return item
        if len(items) >= MAX_ITEMS:
            raise ValueError(f"memory is full ({MAX_ITEMS} items); the person can delete some "
                             "in Settings")
        item = {"id": "m" + uuid.uuid4().hex[:6], "text": text, "time": time.time()}
        items.append(item)
        paths.write_json(_path(), items)
        return item


def remove(memory_id: str) -> bool:
    with _lock:
        items = load()
        kept = [item for item in items if item["id"] != memory_id]
        if len(kept) == len(items):
            return False
        paths.write_json(_path(), kept)
        return True


def clear() -> None:
    with _lock:
        paths.write_json(_path(), [])


def prompt_block() -> str:
    """The memories as the prompt lists them, newest kept when they do not all fit."""
    lines, used = [], 0
    for item in reversed(load()):
        line = f"- [{item['id']}] {item['text']}"
        if used + len(line) > PROMPT_CHARS:
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(reversed(lines))
