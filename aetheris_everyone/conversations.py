"""Saved conversations: what the model saw, and what the window showed.

Two lists per conversation. `messages` is the model's history (role/content,
plus attached image paths). `ui` is what the person saw - their messages, the
replies, a card per tool call, the change sets - so reopening a conversation
draws it exactly as it was.
"""

import os
import re
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


_LABELS = {
    "ko": {"you": "나", "ai": "Aetheris", "attached": "첨부", "changes": "바뀐 파일",
           "undone": "되돌림", "tool": "작업", "saved": "Aetheris Everyone에서 저장한 대화"},
    "en": {"you": "You", "ai": "Aetheris", "attached": "Attached", "changes": "Files changed",
           "undone": "undone", "tool": "Action", "saved": "Chat saved from Aetheris Everyone"},
}


def to_markdown(conversation: dict, language: str = "en") -> str:
    """The chat as the person saw it, as a Markdown document anyone can open."""
    words = _LABELS.get(language, _LABELS["en"])
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(conversation.get("created") or time.time()))
    out = [f"# {conversation.get('title') or 'Aetheris'}", "",
           f"_{words['saved']} · {when}_", ""]
    for item in conversation.get("ui", []):
        kind = item.get("kind")
        if kind == "user":
            out += [f"## {words['you']}", "", item.get("text") or ""]
            names = [a.get("name", "") for a in item.get("attachments") or [] if isinstance(a, dict)]
            if names:
                out.append(f"\n_{words['attached']}: {', '.join(names)}_")
            out.append("")
        elif kind == "assistant" and item.get("text"):
            out += [f"## {words['ai']}", "", item["text"], ""]
        elif kind == "tool":
            args = item.get("args") or {}
            what = args.get("path") or args.get("query") or args.get("url") or args.get("command") \
                or args.get("text") or ""
            out += [f"> {words['tool']}: `{item.get('name', '')}` {what} ({item.get('status', '')})", ""]
        elif kind == "changes":
            title = words["changes"] + (f" ({words['undone']})" if item.get("undone") else "")
            out += [f"**{title}:**", ""]
            out += [f"- {f.get('kind', '')}: {f.get('path', '')}" for f in item.get("files") or []]
            out.append("")
    return "\n".join(out).rstrip() + "\n"


def export_name(conversation: dict, folder: str) -> str:
    """A file name in `folder` for the saved chat that does not replace anything there."""
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", conversation.get("title") or "").strip(" .")
    base = (title[:60].strip(" .") or "chat") + time.strftime(" (%Y-%m-%d %H%M)")
    candidate, number = os.path.join(folder, base + ".md"), 2
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f"{base} {number}.md")
        number += 1
    return candidate


def _from_person(message: dict) -> bool:
    content = message.get("content") or ""
    return message.get("role") == "user" and not content.startswith(("[Tool Result", "[System]"))


def rewind(conversation: dict) -> dict | None:
    """Take back the last request and everything after it. Returns that request's ui item.

    The files stay as they are; the change cards of the taken-back turns are kept
    so they can still be undone, and the model is told the files were changed.
    """
    ui = conversation.get("ui", [])
    at = next((i for i in range(len(ui) - 1, -1, -1) if ui[i].get("kind") == "user"), None)
    if at is None:
        return None
    request, later = ui[at], ui[at + 1:]
    kept_cards = [item for item in later if item.get("kind") == "changes"]
    conversation["ui"] = ui[:at] + kept_cards
    messages = conversation.get("messages", [])
    cut = next((i for i in range(len(messages) - 1, -1, -1) if _from_person(messages[i])), None)
    if cut is not None:
        conversation["messages"] = messages[:cut]
        summary = conversation.get("summary") or {}
        if int(summary.get("upto") or 0) > cut:
            conversation.pop("summary", None)     # it covered what was just taken back
    changed = [f.get("path", "") for card in kept_cards if not card.get("undone")
               for f in card.get("files") or []]
    if changed:
        conversation["messages"].append({"role": "user", "content": (
            "[System] The person took back their last request and your answer to it, but files "
            "changed while doing it are still changed: " + ", ".join(changed[:30]))})
    return request


def title_from(text: str) -> str:
    line = " ".join(text.strip().split())
    return (line[:40] + "…") if len(line) > 40 else (line or "New chat")
