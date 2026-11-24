"""How many tokens each AI model has used, month by month.

The services report the tokens of every request; a cloud service bills by
them and a local model is limited by them. Kept as one small JSON file in the
data folder so Settings can show "this month" per model.
"""

import os
import threading
import time

from aetheris_everyone import paths

_lock = threading.Lock()
KEEP_MONTHS = 24


def _path() -> str:
    return os.path.join(paths.data_dir(), "usage.json")


def _load() -> dict:
    data = paths.read_json(_path(), {})
    return data if isinstance(data, dict) else {}


def record(provider: str, model: str, tokens_in: int, tokens_out: int) -> None:
    month = time.strftime("%Y-%m")
    with _lock:
        data = _load()
        entry = data.setdefault(month, {}).setdefault(f"{provider}|{model}",
                                                      {"input": 0, "output": 0, "requests": 0})
        entry["input"] += int(tokens_in or 0)
        entry["output"] += int(tokens_out or 0)
        entry["requests"] += 1
        for old in sorted(data)[:-KEEP_MONTHS]:
            data.pop(old, None)
        paths.write_json(_path(), data)


def summary() -> list:
    """[{"month", "items": [{"provider", "model", "input", "output", "requests"}]}], newest first."""
    months = []
    for month, entries in sorted(_load().items(), reverse=True):
        if not isinstance(entries, dict):
            continue
        items = []
        for key, entry in entries.items():
            provider, _, model = key.partition("|")
            if isinstance(entry, dict):
                items.append({"provider": provider, "model": model,
                              **{k: int(entry.get(k) or 0) for k in ("input", "output", "requests")}})
        items.sort(key=lambda item: item["input"] + item["output"], reverse=True)
        months.append({"month": month, "items": items})
    return months
