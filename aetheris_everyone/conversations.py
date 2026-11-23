"""Saved conversations: what the model saw, and what the window showed.

Two lists per conversation. `messages` is the model's history (role/content,
plus attached image paths). `ui` is what the person saw - their messages, the
replies, a card per tool call, the change sets - so reopening a conversation
draws it exactly as it was.
"""

import os
import threading
import time
import uuid

from aetheris_everyone import history, paths

_lock = threading.RLock()


def _dir() -> str:
    return paths.sub("conversations")


def _path(conversation_id: str) -> str:
    return os.path.join(_dir(), os.path.basename(conversation_id) + ".json")


def _index_path() -> str:
    return os.path.join(_dir(), "index.json")


def _index() -> dict:
    index = paths.read_json(_index_path())
    if isinstance(index, dict):
        return index
    index = {}
    for name in os.listdir(_dir()):
        if name.endswith(".json") and name != "index.json":
            data = paths.read_json(os.path.join(_dir(), name))
            if isinstance(data, dict) and data.get("id"):
                index[data["id"]] = _summary(data)
    paths.write_json(_index_path(), index)
    return index


def _summary(conversation: dict) -> dict:
    return {"id": conversation["id"], "title": conversation.get("title") or "",
            "updated": conversation.get("updated", 0), "folder": conversation.get("folder", "")}


def new(folder: str) -> dict:
    now = time.time()
    return {"id": time.strftime("%Y%m%d%H%M%S-") + uuid.uuid4().hex[:6], "title": "",
            "created": now, "updated": now, "folder": folder, "messages": [], "ui": []}


def save(conversation: dict) -> None:
    with _lock:
        conversation["updated"] = time.time()
        paths.write_json(_path(conversation["id"]), conversation)
        index = _index()
        index[conversation["id"]] = _summary(conversation)
        paths.write_json(_index_path(), index)


def load(conversation_id: str) -> dict | None:
    data = paths.read_json(_path(conversation_id))
    if not isinstance(data, dict) or not data.get("id"):
        return None
    data.setdefault("messages", [])
    data.setdefault("ui", [])
    return data


def list_all() -> list:
    with _lock:
        items = list(_index().values())
    items.sort(key=lambda item: item.get("updated", 0), reverse=True)
    return items


def rename(conversation_id: str, title: str) -> None:
    with _lock:
        data = load(conversation_id)
        if data:
            data["title"] = title.strip()[:120]
            save(data)


def delete(conversation_id: str) -> None:
    with _lock:
        try:
            os.remove(_path(conversation_id))
        except OSError:
            pass
        index = _index()
        index.pop(conversation_id, None)
        paths.write_json(_index_path(), index)
    history.forget(conversation_id)


def title_from(text: str) -> str:
    line = " ".join(text.strip().split())
    return (line[:40] + "…") if len(line) > 40 else (line or "New chat")
