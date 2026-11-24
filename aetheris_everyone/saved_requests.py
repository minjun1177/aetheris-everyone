"""Requests the person makes again and again, saved to reuse with one click.

Aetheris has skills and custom /commands for this; for someone who does not
write either, a saved request is simply text: "Sort this week's downloads into
folders by type" kept under a name and put back in the message box when picked.
"""

import os
import threading
import uuid

from aetheris_everyone import paths

MAX_ITEMS = 60
MAX_TEXT = 4000
_lock = threading.Lock()


def _path() -> str:
    return os.path.join(paths.data_dir(), "saved_requests.json")


def load() -> list:
    data = paths.read_json(_path(), [])
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict) and isinstance(item.get("id"), str)
            and isinstance(item.get("text"), str)]


def save(text: str, title: str = "", item_id: str = "") -> dict:
    """Add a request, or change the one with `item_id`. Raises ValueError when it cannot."""
    text = str(text or "").strip()[:MAX_TEXT]
    if not text:
        raise ValueError("empty")
    title = " ".join(str(title or "").split())[:60] or " ".join(text.split())[:40]
    with _lock:
        items = load()
        for item in items:
            if item_id and item["id"] == item_id:
                item.update(title=title, text=text)
                break
        else:
            if len(items) >= MAX_ITEMS:
                raise ValueError("full")
            item = {"id": "r" + uuid.uuid4().hex[:6], "title": title, "text": text}
            items.append(item)
        paths.write_json(_path(), items)
        return item


def remove(item_id: str) -> None:
    with _lock:
        paths.write_json(_path(), [item for item in load() if item["id"] != item_id])
