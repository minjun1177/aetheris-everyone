"""Requests the person set to run by themselves: once, every day, or every week.

Ported from Aetheris's /schedule and /loop, kept between starts and set in a
form. A scheduled request runs only while the app is open, through the same
permission rules as any other: a permission card waits for the person (who is
notified). A run missed while the app was closed is skipped, not run late, so
opening the app never sets off a burst of old work.
"""

import os
import threading
import time
import uuid

from aetheris_everyone import paths

MISSED_AFTER = 15 * 60          # a run this late (the app was closed) is skipped
DAYS = 7
_lock = threading.Lock()


def _path() -> str:
    return os.path.join(paths.data_dir(), "schedules.json")


def load() -> list:
    data = paths.read_json(_path(), [])
    return [item for item in data if isinstance(item, dict) and item.get("id")] \
        if isinstance(data, list) else []


def _write(items: list) -> None:
    paths.write_json(_path(), items)


def _at(day: time.struct_time, clock: str) -> float:
    hour, minute = (int(part) for part in clock.split(":"))
    return time.mktime((day.tm_year, day.tm_mon, day.tm_mday, hour, minute, 0, 0, 0, -1))


def next_time(when: dict, after: float) -> float | None:
    """The first run of `when` later than `after`, or None (a one-off already past)."""
    kind = when.get("kind")
    if kind == "once":
        at = float(when.get("at") or 0)
        return at if at > after else None
    clock = str(when.get("time") or "09:00")
    for days_ahead in range(0, DAYS + 1):
        day = time.localtime(after + days_ahead * 86400)
        if kind == "weekly" and day.tm_wday != int(when.get("day") or 0):
            continue
        at = _at(day, clock)
        if at > after:
            return at
    return None


def check(when) -> dict:
    """`when` cleaned up, or ValueError for something that cannot be scheduled."""
    if not isinstance(when, dict) or when.get("kind") not in ("once", "daily", "weekly"):
        raise ValueError("bad_schedule")
    if when["kind"] == "once":
        at = float(when.get("at") or 0)
        if at <= time.time():
            raise ValueError("past")
        return {"kind": "once", "at": at}
    clock = str(when.get("time") or "")
    try:
        hour, minute = (int(part) for part in clock.split(":"))
    except ValueError:
        raise ValueError("bad_schedule") from None
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ValueError("bad_schedule")
    cleaned = {"kind": when["kind"], "time": f"{hour:02d}:{minute:02d}"}
    if when["kind"] == "weekly":
        day = int(when.get("day") or 0)
        if not 0 <= day < 7:
            raise ValueError("bad_schedule")
        cleaned["day"] = day
    return cleaned


def save(text: str, when: dict, folder: str, title: str = "", item_id: str = "",
         enabled: bool = True) -> dict:
    text = str(text or "").strip()[:4000]
    if not text:
        raise ValueError("empty")
    when = check(when)
    title = " ".join(str(title or "").split())[:60] or " ".join(text.split())[:40]
    with _lock:
        items = load()
        item = next((i for i in items if item_id and i["id"] == item_id), None)
        if item is None:
            item = {"id": "s" + uuid.uuid4().hex[:6], "conversation": ""}
            items.append(item)
        item.update(title=title, text=text, when=when, folder=folder, enabled=bool(enabled),
                    next=next_time(when, time.time()) if enabled else None)
        _write(items)
        return item


def remove(item_id: str) -> None:
    with _lock:
        _write([item for item in load() if item["id"] != item_id])


def take_due(now: float, busy: bool) -> list:
    """The schedules to run now, each moved on to its next time.

    While the AI is busy nothing is taken (it waits for the next check); a run
    missed by more than MISSED_AFTER is skipped and recorded as missed.
    """
    due = []
    with _lock:
        items = load()
        changed = False
        for item in items:
            at = item.get("next")
            if not item.get("enabled") or not at or at > now:
                continue
            if now - at > MISSED_AFTER:
                item["missed"] = at
            elif busy or due:
                continue                     # one at a time; the rest wait for the next check
            else:
                due.append(dict(item))
                item["last"] = now
            item["next"] = next_time(item["when"], now)
            if item["next"] is None:
                item["enabled"] = False
            changed = True
        if changed:
            _write(items)
    return due


def set_conversation(item_id: str, conversation_id: str) -> None:
    with _lock:
        items = load()
        for item in items:
            if item["id"] == item_id:
                item["conversation"] = conversation_id
        _write(items)
