"""Every file change the AI makes, kept so it can be taken back.

Aetheris made a git commit per edit. People who are not developers do not have
git, and their folders are not repositories, so this keeps its own record
instead: before the AI writes, moves or deletes anything, the original is
copied aside. One request from the person is one *change set*; the window shows
it under the reply with an "Undo" button.

Deleting is never real deletion - the file is moved into the change set, so
taking it back is moving it home again.

Undo refuses (unless forced) when a file has changed since the AI touched it,
so a person's own later edits are not silently thrown away.
"""

import hashlib
import os
import shutil
import time
import uuid

from aetheris_everyone import paths


def _hash(path: str) -> str:
    if not os.path.isfile(path):
        return ""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _snapshot(folder: str) -> dict:
    """Every file under `folder` as relative path -> [size, mtime_ns]; folders map to None."""
    found = {}
    for current, dirs, files in os.walk(folder):
        for name in dirs:
            found[os.path.relpath(os.path.join(current, name), folder)] = None
        for name in files:
            full = os.path.join(current, name)
            try:
                stat = os.stat(full)
            except OSError:
                continue
            found[os.path.relpath(full, folder)] = [stat.st_size, stat.st_mtime_ns]
    return found


def _remove_recorded(folder: str, recorded: dict) -> None:
    """Remove only what the AI put in `folder` and nobody has touched since."""
    current = _snapshot(folder)
    for rel, stamp in recorded.items():
        if stamp is not None and current.get(rel) == stamp:
            os.remove(os.path.join(folder, rel))
    for rel in sorted((r for r, s in recorded.items() if s is None), key=len, reverse=True):
        path = os.path.join(folder, rel)
        if os.path.isdir(path) and not os.listdir(path):
            os.rmdir(path)
    if not os.listdir(folder):
        os.rmdir(folder)


def _root(conversation_id: str) -> str:
    return paths.sub("history", conversation_id)


class ChangeSet:
    def __init__(self, conversation_id: str):
        self.conversation_id = conversation_id
        self.id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        self.dir = os.path.join(_root(conversation_id), self.id)
        self.ops: list = []
        self._seen: dict = {}        # path -> index of its "write" op

    def _backup_slot(self) -> str:
        os.makedirs(self.dir, exist_ok=True)
        return os.path.join(self.dir, f"b{len(self.ops)}-{uuid.uuid4().hex[:6]}")

    def before_write(self, path: str) -> None:
        """Call before creating or overwriting the file at `path`."""
        path = os.path.abspath(path)
        if path in self._seen:
            return
        backup = None
        if os.path.isfile(path):
            backup = self._backup_slot()
            shutil.copy2(path, backup)
        self._seen[path] = len(self.ops)
        self.ops.append({"op": "write", "path": path, "backup": backup, "after": ""})

    def after_write(self, path: str) -> None:
        path = os.path.abspath(path)
        if path in self._seen:
            self.ops[self._seen[path]]["after"] = _hash(path)
        self.save()

    def mkdir(self, path: str) -> None:
        self.ops.append({"op": "mkdir", "path": os.path.abspath(path)})
        self.save()

    def move(self, source: str, target: str) -> None:
        """Move `source` to `target`, remembering how to move it back."""
        source, target = os.path.abspath(source), os.path.abspath(target)
        shutil.move(source, target)
        # A file written earlier in this set has moved: its record follows it.
        for op in self.ops:
            if op["op"] == "write" and op["path"] == source:
                self._seen.pop(source, None)
        self.ops.append({"op": "move", "source": source, "target": target})
        self.save()

    def copy_in(self, target: str, is_dir: bool) -> None:
        op = {"op": "created", "path": os.path.abspath(target), "dir": is_dir}
        if is_dir:
            op["files"] = _snapshot(op["path"])
        self.ops.append(op)
        self.save()

    def delete(self, path: str) -> None:
        """'Delete' by moving into the change set."""
        path = os.path.abspath(path)
        backup = self._backup_slot()
        shutil.move(path, backup)
        self.ops.append({"op": "delete", "path": path, "backup": backup})
        self.save()

    def files(self) -> list:
        return describe(self.ops)

    def save(self) -> None:
        if not self.ops:
            return
        os.makedirs(self.dir, exist_ok=True)
        paths.write_json(os.path.join(self.dir, "manifest.json"), {
            "id": self.id, "conversation": self.conversation_id, "time": time.time(),
            "ops": self.ops, "undone": False})


def describe(ops: list) -> list:
    """What a change card lists for a set of recorded operations."""
    out = []
    for op in ops:
        if op["op"] == "write":
            out.append({"kind": "created" if op["backup"] is None else "modified",
                        "path": op["path"]})
        elif op["op"] == "move":
            out.append({"kind": "moved", "path": op["target"], "from": op["source"]})
        elif op["op"] == "delete":
            out.append({"kind": "deleted", "path": op["path"]})
        elif op["op"] == "created":
            out.append({"kind": "created", "path": op["path"]})
        elif op["op"] == "mkdir":
            out.append({"kind": "folder", "path": op["path"]})
    return out


def _manifest_path(conversation_id: str, change_id: str) -> str:
    safe = os.path.basename(change_id)
    return os.path.join(_root(conversation_id), safe, "manifest.json")


def load(conversation_id: str, change_id: str) -> dict | None:
    return paths.read_json(_manifest_path(conversation_id, change_id))


def conflicts(manifest: dict) -> list:
    """Files that changed after the AI touched them, which undo would overwrite."""
    found = []
    for op in manifest["ops"]:
        if op["op"] == "write" and op.get("after") and os.path.exists(op["path"]):
            if _hash(op["path"]) != op["after"]:
                found.append(op["path"])
        elif op["op"] == "move" and not os.path.exists(op["target"]):
            found.append(op["target"])
        elif op["op"] == "delete" and os.path.exists(op["path"]):
            found.append(op["path"])
        elif op["op"] == "created" and op.get("dir") and os.path.isdir(op["path"]):
            # Something was added to, changed in or taken from a copied folder since.
            if op.get("files") is None or _snapshot(op["path"]) != op["files"]:
                found.append(op["path"])
    return found


def undo(conversation_id: str, change_id: str, force: bool = False) -> dict:
    """Take a change set back. {"ok", "conflicts", "errors"}."""
    manifest = load(conversation_id, change_id)
    if not manifest:
        return {"ok": False, "conflicts": [], "errors": ["not found"]}
    if manifest.get("undone"):
        return {"ok": True, "conflicts": [], "errors": []}
    clash = conflicts(manifest)
    if clash and not force:
        return {"ok": False, "conflicts": clash, "errors": []}
    errors = []
    for op in reversed(manifest["ops"]):
        try:
            kind = op["op"]
            if kind == "write":
                if op["backup"]:
                    os.makedirs(os.path.dirname(op["path"]), exist_ok=True)
                    shutil.copy2(op["backup"], op["path"])
                elif os.path.isfile(op["path"]):
                    os.remove(op["path"])
            elif kind == "move":
                if os.path.exists(op["target"]) and not os.path.exists(op["source"]):
                    os.makedirs(os.path.dirname(op["source"]), exist_ok=True)
                    shutil.move(op["target"], op["source"])
            elif kind == "delete":
                if os.path.exists(op["backup"]) and not os.path.exists(op["path"]):
                    os.makedirs(os.path.dirname(op["path"]), exist_ok=True)
                    shutil.move(op["backup"], op["path"])
            elif kind == "created":
                if op.get("dir") and os.path.isdir(op["path"]):
                    if op.get("files") is not None:
                        _remove_recorded(op["path"], op["files"])
                    else:                    # recorded by an older version: no snapshot
                        shutil.rmtree(op["path"])
                elif os.path.isfile(op["path"]):
                    os.remove(op["path"])
            elif kind == "mkdir":
                if os.path.isdir(op["path"]) and not os.listdir(op["path"]):
                    os.rmdir(op["path"])
        except OSError as error:
            errors.append(f"{op.get('path') or op.get('target')}: {error}")
    manifest["undone"] = True
    paths.write_json(_manifest_path(conversation_id, change_id), manifest)
    return {"ok": not errors, "conflicts": [], "errors": errors}


def recorded(conversation_id: str) -> list:
    """Every change set kept for a conversation, oldest first."""
    root = os.path.join(paths.data_dir(), "history", os.path.basename(conversation_id))
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return []
    found = []
    for name in names:
        manifest = paths.read_json(os.path.join(root, name, "manifest.json"))
        if isinstance(manifest, dict) and manifest.get("ops"):
            found.append(manifest)
    return found


def forget(conversation_id: str) -> None:
    shutil.rmtree(os.path.join(paths.data_dir(), "history", os.path.basename(conversation_id)),
                  ignore_errors=True)
