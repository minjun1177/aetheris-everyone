"""What the AI can do on this computer, and the checks around every call.

Each tool is a plain function taking a `Context` and its arguments. `dispatch`
is the single door they all go through: it resolves paths against the work
folder, decides whether the person must be asked first (by the safety level
they chose), records every change for undo, and turns any failure into a short
message the model can read and recover from.

Categories decide the asking:
    read    look at files                       - asked outside the work folder (not in "auto")
    change  create / edit / move / delete       - undoable; asked per safety level, and
                                                  always asked outside the work folder
    run     start a program                     - off unless turned on in Settings; then
                                                  asked at every safety level
    web     search, read a public page          - never asked; nothing local changes
"""

import fnmatch
import locale
import os
import shutil
import signal
import subprocess
import sys
import threading
import time

from aetheris_everyone import documents, history, paths, settings, websearch

RESULT_LIMIT = 12_000
READ_LINES = 400
MAX_TEXT_BYTES = 20_000_000
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "$RECYCLE.BIN",
             "System Volume Information", ".Trash", ".cache"}


class ToolError(Exception):
    pass


class Denied(Exception):
    pass


class Context:
    def __init__(self, folder: str, changes: history.ChangeSet, ask, safety: str,
                 granted: set, cancelled: threading.Event, extra_readable=(),
                 allow_commands: bool = False):
        self.folder = os.path.realpath(folder)
        self.changes = changes
        self.ask = ask                    # ask(request: dict) -> "allow" | "always" | "deny"
        self.safety = safety
        self.granted = granted            # categories allowed for the rest of the conversation
        self.cancelled = cancelled
        self.extra_readable = {os.path.realpath(p) for p in extra_readable}
        self.allow_commands = allow_commands

    # -- paths -----------------------------------------------------------
    def resolve(self, path) -> str:
        if not isinstance(path, str) or not path.strip():
            raise ToolError("a path is required")
        path = os.path.expanduser(path.strip().strip('"').strip("'"))
        if not os.path.isabs(path):
            path = os.path.join(self.folder, path)
        resolved = os.path.realpath(path)
        data = os.path.realpath(paths.data_dir())
        if _within(resolved, data):
            raise Denied("that is the assistant's own private data (settings, keys, history)")
        return resolved

    def inside(self, path: str) -> bool:
        return _within(path, self.folder)

    def show(self, path: str) -> str:
        """A path as the model should write it: relative inside the work folder."""
        if self.inside(path):
            rel = os.path.relpath(path, self.folder)
            return "." if rel == "." else rel.replace(os.sep, "/")
        return path

    # -- asking ------------------------------------------------------------
    def permit(self, category: str, request: dict, outside: bool = False) -> None:
        needed = set()
        # "Do everything" still asks before changing anything outside the work folder,
        # and before running a program: neither is limited to what the person chose.
        if outside and "outside" not in self.granted and \
                (self.safety != "auto" or category == "change"):
            needed.add("outside")
        if category == "change" and self.safety == "ask" and "change" not in self.granted:
            needed.add("change")
        if category == "run":
            needed.add("run")        # every program run is shown and asked, never granted ahead
        if not needed:
            return
        if self.cancelled.is_set():
            raise Denied("stopped by the user")
        answer = self.ask(dict(request, category=category, outside=outside))
        if answer == "always":
            self.granted.update(needed - {"run"})
        elif answer != "allow":
            raise Denied("the user said no")

    def ensure_parent(self, path: str) -> None:
        """Create the folders above `path`, each recorded so Undo removes it."""
        missing = []
        probe = os.path.dirname(path)
        while probe and not os.path.exists(probe):
            missing.append(probe)
            parent = os.path.dirname(probe)
            if parent == probe:
                break
            probe = parent
        for folder in reversed(missing):
            os.mkdir(folder)
            self.changes.mkdir(folder)


def _within(path: str, folder: str) -> bool:
    try:
        return os.path.normcase(os.path.commonpath([path, folder])) == os.path.normcase(folder)
    except ValueError:
        return False


def _size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n}B"


# -- text files -------------------------------------------------------------

_ENCODINGS = ("utf-8", "cp949", "euc-kr", "shift_jis", "cp1252")


def read_text(path: str) -> tuple:
    """(text, encoding) or ToolError for something that is not text."""
    if os.path.getsize(path) > MAX_TEXT_BYTES:
        raise ToolError(f"the file is too large to read as text ({_size(os.path.getsize(path))})")
    with open(path, "rb") as f:
        raw = f.read()
    if b"\x00" in raw[:8000]:
        raise ToolError("this is not a text file (it looks like a program, picture or archive)")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", "replace"), "utf-8-sig"
    for encoding in _ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace"), "utf-8"


def _write_text(path: str, text: str, encoding: str = "") -> None:
    if not encoding:
        # Excel on Korean Windows reads a CSV without a BOM as the wrong encoding.
        encoding = "utf-8-sig" if path.lower().endswith(".csv") else "utf-8"
    with open(path, "w", encoding=encoding, newline="") as f:
        f.write(text)


def _missing(ctx: "Context", path: str, what: str = "nothing") -> ToolError:
    """'Not found', with what IS there - so a model that guessed a name can correct itself."""
    folder = os.path.dirname(path)
    while folder and not os.path.isdir(folder):
        parent = os.path.dirname(folder)
        if parent == folder:
            break
        folder = parent
    names = []
    try:
        names = sorted(os.listdir(folder))[:40]
    except OSError:
        pass
    listing = f"\nWhat {ctx.show(folder)} actually contains: " + ", ".join(names) if names else ""
    return ToolError(f"there is {what} at {ctx.show(path)}.{listing}")


# -- the tools ------------------------------------------------------------------

def list_folder(ctx: Context, path: str = ".") -> str:
    target = ctx.resolve(path)
    if not os.path.isdir(target):
        raise ToolError(f"there is no folder at {ctx.show(target)}")
    ctx.permit("read", {"tool": "list_folder", "path": target}, outside=not ctx.inside(target))
    entries = []
    with os.scandir(target) as listing:
        for entry in listing:
            try:
                stat = entry.stat()
            except OSError:
                continue
            modified = time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime))
            if entry.is_dir():
                entries.append((0, entry.name.lower(), f"[folder] {entry.name}/   (modified {modified})"))
            else:
                entries.append((1, entry.name.lower(),
                                f"{entry.name}   ({_size(stat.st_size)}, modified {modified})"))
    entries.sort()
    if not entries:
        return f"{ctx.show(target)} is empty."
    lines = [line for _, _, line in entries[:300]]
    more = f"\n... and {len(entries) - 300} more" if len(entries) > 300 else ""
    return f"Contents of {ctx.show(target)} ({len(entries)} items):\n" + "\n".join(lines) + more


def _walk(ctx: Context, root: str):
    for folder, dirs, files in os.walk(root):
        if ctx.cancelled.is_set():
            return
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        yield folder, dirs, files


def find_files(ctx: Context, pattern: str, path: str = ".") -> str:
    root = ctx.resolve(path)
    if not os.path.isdir(root):
        raise ToolError(f"there is no folder at {ctx.show(root)}")
    ctx.permit("read", {"tool": "find_files", "path": root}, outside=not ctx.inside(root))
    pattern = (pattern or "*").strip()
    wildcard = any(ch in pattern for ch in "*?[")
    found = []
    for folder, dirs, files in _walk(ctx, root):
        for name in dirs + files:
            hit = fnmatch.fnmatch(name.lower(), pattern.lower()) if wildcard \
                else pattern.lower() in name.lower()
            if hit:
                full = os.path.join(folder, name)
                found.append(ctx.show(full) + ("/" if os.path.isdir(full) else ""))
                if len(found) >= 200:
                    break
        if len(found) >= 200:
            break
    if not found:
        return f"No files matching '{pattern}' under {ctx.show(root)}."
    return f"{len(found)} match(es){' (first 200)' if len(found) >= 200 else ''}:\n" + "\n".join(found)


def search_text(ctx: Context, text: str, path: str = ".") -> str:
    root = ctx.resolve(path)
    if not text:
        raise ToolError("text to search for is required")
    ctx.permit("read", {"tool": "search_text", "path": root}, outside=not ctx.inside(root))
    needle = text.lower()
    hits = []
    targets = [root] if os.path.isfile(root) else (
        os.path.join(folder, name) for folder, _, files in _walk(ctx, root) for name in files)
    for full in targets:
        try:
            if full.lower().endswith(documents.READABLE):
                body = documents.extract(full)
            elif os.path.getsize(full) > 2_000_000:
                continue
            else:
                body, _ = read_text(full)
        except (ToolError, ValueError, OSError):
            continue
        for number, line in enumerate(body.splitlines(), 1):
            if needle in line.lower():
                hits.append(f"{ctx.show(full)}:{number}: {line.strip()[:200]}")
                if len(hits) >= 100:
                    break
        if len(hits) >= 100:
            break
    if not hits:
        return f"'{text}' was not found under {ctx.show(root)}."
    return f"{len(hits)} line(s) found:\n" + "\n".join(hits)


def read_file(ctx: Context, path: str, start_line: int = 1, max_lines: int = READ_LINES) -> str:
    target = ctx.resolve(path)
    if os.path.isdir(target):
        return list_folder(ctx, path)
    if not os.path.isfile(target):
        raise _missing(ctx, target, "no file")
    outside = not ctx.inside(target) and target not in ctx.extra_readable
    ctx.permit("read", {"tool": "read_file", "path": target}, outside=outside)
    lower = target.lower()
    if lower.endswith(documents.READABLE):
        try:
            text = documents.extract(target)
        except ValueError as error:
            raise ToolError(str(error)) from None
        kind = "document text"
    elif lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".heic")):
        return (f"{ctx.show(target)} is a picture ({_size(os.path.getsize(target))}). "
                "Pictures cannot be read as text; ask the user to attach it to a message "
                "if you need to see it.")
    elif lower.endswith(".hwp"):
        raise ToolError(".hwp files cannot be read; ask the user to save it as .hwpx or .pdf")
    else:
        text, _ = read_text(target)
        kind = "text"
    lines = text.splitlines()
    try:
        start = max(1, int(start_line or 1))
        count = max(1, min(2000, int(max_lines or READ_LINES)))
    except (TypeError, ValueError):
        start, count = 1, READ_LINES
    chunk = lines[start - 1:start - 1 + count]
    end = start - 1 + len(chunk)
    header = f"{ctx.show(target)} ({kind}, {len(lines)} lines)"
    if start > 1 or end < len(lines):
        header += f" - showing lines {start}-{end}"
        if end < len(lines):
            header += f"; call again with start_line={end + 1} for more"
    return header + ":\n" + "\n".join(chunk)


def write_file(ctx: Context, path: str, content: str = "", append: bool = False) -> str:
    target = ctx.resolve(path)
    if os.path.isdir(target):
        raise ToolError(f"{ctx.show(target)} is a folder")
    if content is None:
        content = ""
    if not isinstance(content, str):
        import json
        content = json.dumps(content, ensure_ascii=False, indent=2)
    existed = os.path.exists(target)
    append = str(append).lower() in ("true", "1", "yes")
    lower = target.lower()
    if append and existed and lower.endswith(documents.WRITABLE + documents.READABLE):
        raise ToolError(f"append does not work for {os.path.splitext(target)[1]} documents. "
                        "Read the document, then write_file the whole new version "
                        "(old content plus the addition) without append.")
    if append and existed:
        current, encoding = read_text(target)
        joiner = "" if not current or current.endswith("\n") else "\n"
        content, keep_encoding = current + joiner + content, encoding
    else:
        append, keep_encoding = False, ""
    ctx.permit("change", {"tool": "write_file", "path": target, "exists": existed,
                          "append": append, "preview": content[-2000:] if append else content[:2000]},
               outside=not ctx.inside(target))
    data = None
    if lower.endswith(documents.WRITABLE):
        try:
            data = documents.render(target, content)
        except ValueError as error:
            raise ToolError(str(error)) from None
    elif lower.endswith((".pdf", ".pptx", ".hwp", ".hwpx", ".doc", ".xls", ".ppt")):
        raise ToolError(f"{os.path.splitext(target)[1]} files cannot be written. "
                        "Write .docx (Word), .xlsx (Excel), .md, .txt, .csv or .html instead.")
    ctx.ensure_parent(target)
    ctx.changes.before_write(target)
    if data is not None:
        with open(target, "wb") as f:
            f.write(data)
    else:
        _write_text(target, content, keep_encoding)
    ctx.changes.after_write(target)
    verb = "Added to" if append else "Replaced" if existed else "Created"
    return f"{verb} {ctx.show(target)} ({_size(os.path.getsize(target))})."


def _loose(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").split("\n"))


def edit_file(ctx: Context, path: str, old_text: str, new_text: str = "",
              replace_all: bool = False) -> str:
    target = ctx.resolve(path)
    if not os.path.isfile(target):
        raise _missing(ctx, target, "no file")
    if target.lower().endswith(documents.READABLE):
        raise ToolError("documents cannot be edited piece by piece; read it, then write the "
                        "whole new version with write_file (as .docx / .xlsx)")
    if not old_text:
        raise ToolError("old_text is required: the exact text to replace")
    text, encoding = read_text(target)
    count = text.count(old_text)
    if count == 0:
        # Line endings and trailing spaces are what small models get wrong most.
        loose_text, loose_old = _loose(text), _loose(old_text)
        if loose_old and loose_text.count(loose_old):
            text, old_text = loose_text, loose_old
            new_text = _loose(new_text or "")
            count = text.count(old_text)
    if count == 0:
        hint = ""
        if len(text) <= 4000:
            hint = f"\nThe file currently contains exactly:\n{text}"
        raise ToolError("old_text was not found in the file. Copy the text exactly, use "
                        "write_file with append=true to add at the end, or write_file to "
                        "rewrite it whole." + hint)
    if count > 1 and not replace_all:
        raise ToolError(f"old_text appears {count} times; include more surrounding text so "
                        "it is unique, or set replace_all to true")
    ctx.permit("change", {"tool": "edit_file", "path": target, "old": old_text[:1500],
                          "new": (new_text or "")[:1500]}, outside=not ctx.inside(target))
    updated = text.replace(old_text, new_text or "") if replace_all \
        else text.replace(old_text, new_text or "", 1)
    ctx.changes.before_write(target)
    _write_text(target, updated, encoding)
    ctx.changes.after_write(target)
    return f"Edited {ctx.show(target)} ({count if replace_all else 1} place(s) changed)."


def create_folder(ctx: Context, path: str) -> str:
    target = ctx.resolve(path)
    if os.path.isdir(target):
        return f"{ctx.show(target)} already exists."
    ctx.permit("change", {"tool": "create_folder", "path": target}, outside=not ctx.inside(target))
    ctx.ensure_parent(target)
    os.mkdir(target)
    ctx.changes.mkdir(target)
    return f"Created folder {ctx.show(target)}."


def _destination(ctx: Context, source: str, destination: str) -> str:
    target = ctx.resolve(destination)
    if os.path.isdir(target) or destination.endswith(("/", "\\")):
        target = os.path.join(target, os.path.basename(source))
    if os.path.exists(target):
        raise ToolError(f"{ctx.show(target)} already exists; choose another name")
    return target


def move(ctx: Context, source: str, destination: str) -> str:
    origin = ctx.resolve(source)
    if not os.path.exists(origin):
        raise _missing(ctx, origin)
    if origin == ctx.folder:
        raise ToolError("the work folder itself cannot be moved")
    target = _destination(ctx, origin, destination)
    outside = not (ctx.inside(origin) and ctx.inside(target))
    ctx.permit("change", {"tool": "move", "path": origin, "target": target}, outside=outside)
    ctx.ensure_parent(target)
    ctx.changes.move(origin, target)
    return f"Moved {ctx.show(origin)} to {ctx.show(target)}."


def copy(ctx: Context, source: str, destination: str) -> str:
    origin = ctx.resolve(source)
    if not os.path.exists(origin):
        raise _missing(ctx, origin)
    target = _destination(ctx, origin, destination)
    outside = not ctx.inside(target) or not ctx.inside(origin)
    ctx.permit("change", {"tool": "copy", "path": origin, "target": target}, outside=outside)
    ctx.ensure_parent(target)
    if os.path.isdir(origin):
        shutil.copytree(origin, target)
        ctx.changes.copy_in(target, True)
    else:
        ctx.changes.before_write(target)
        shutil.copy2(origin, target)
        ctx.changes.after_write(target)
    return f"Copied {ctx.show(origin)} to {ctx.show(target)}."


def delete(ctx: Context, path: str) -> str:
    target = ctx.resolve(path)
    if not os.path.lexists(target):
        raise _missing(ctx, target)
    if target == ctx.folder or target == os.path.realpath(os.path.expanduser("~")):
        raise ToolError("that folder cannot be deleted")
    ctx.permit("change", {"tool": "delete", "path": target, "is_dir": os.path.isdir(target)},
               outside=not ctx.inside(target))
    ctx.changes.delete(target)
    return f"Deleted {ctx.show(target)} (it can be restored with Undo)."


def _decode_output(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode(locale.getpreferredencoding(False) or "utf-8", "replace")


def _kill_tree(process: subprocess.Popen) -> None:
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)],
                           capture_output=True, creationflags=0x08000000)
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


_PRIVATE_WORDS = ("secrets.json", "aetheris_everyone_home",
                  # programs that read the system password store
                  "keyring", "cmdkey", "credentialmanager", "get-storedcredential", "credread",
                  "vaultcmd", "find-generic-password", "find-internet-password",
                  "dump-keychain", "secret-tool")
_DATA_NAMES = ("aetheriseveryone", "aetheris-everyone")       # paths.data_dir() on each system
_DATA_PARENTS = ("%appdata%", "$appdata", "${appdata}", "$env:appdata", "$xdg_data_home",
                 "${xdg_data_home}", "roaming", "share", "application support")
_HOME_PREFIXES = ("~", "$home", "${home}", "%userprofile%", "$env:userprofile", "%homepath%")


def _flat(text: str) -> str:
    return " ".join(text.replace("\\", "/").lower().replace('"', "").replace("'", "").split())


def touches_private_data(command: str) -> bool:
    """Whether a command names the app's own data folder or the key store.

    A guard against the obvious, not a sandbox: a determined program can still
    find its way there, so the command is also always shown to the person first.
    """
    flat = _flat(command)
    data = os.path.normpath(paths.data_dir())
    words = {_flat(data), _flat(os.path.realpath(data)), *_PRIVATE_WORDS}
    names = {_flat(os.path.basename(data)), *_DATA_NAMES}
    parents = {_flat(os.path.basename(os.path.dirname(data))), *_DATA_PARENTS}
    # "share/aetheris-everyone", "%appdata%/aetheriseveryone", "roaming/aetheriseveryone" ...
    words |= {f"{parent}/{name}" for parent in parents for name in names}
    # "~/.local/share/aetheris-everyone", "$home/library/application support/aetheriseveryone" ...
    words |= {f"{home}/{rest}/{name}" for home in _HOME_PREFIXES for name in names
              for rest in (".local/share", "library/application support", "appdata/roaming")}
    return any(word in flat for word in words)


def run_command(ctx: Context, command: str, reason: str = "", timeout_seconds: int = 120) -> str:
    if not command or not command.strip():
        raise ToolError("command is required")
    if not ctx.allow_commands:
        raise ToolError("running programs is turned off in this app's Settings. Do the job with "
                        "the file tools, or tell the user it needs a program to be run and that "
                        "they can allow it in Settings.")
    if touches_private_data(command):
        raise Denied("that command reaches the assistant's own private data (settings, keys, "
                     "history)")
    try:
        timeout = max(5, min(900, int(timeout_seconds or 120)))
    except (TypeError, ValueError):
        timeout = 120
    ctx.permit("run", {"tool": "run_command", "command": command, "reason": reason or "",
                       "folder": ctx.folder})
    kwargs = {"shell": True, "cwd": ctx.folder, "stdin": subprocess.DEVNULL,
              "stdout": subprocess.PIPE, "stderr": subprocess.STDOUT}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x08000000 | 0x00000200   # no window, own process group
    else:
        kwargs["start_new_session"] = True
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    for secret in settings.ENV_KEY_NAMES + ("AETHERIS_EVERYONE_HOME",):
        env.pop(secret, None)
    process = subprocess.Popen(command, env=env, **kwargs)
    chunks = []

    def drain():
        total = 0
        for block in iter(lambda: process.stdout.read(4096), b""):
            if total < 400_000:
                chunks.append(block)
            total += len(block)

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    started = time.time()
    status = None
    while status is None:
        status = process.poll()
        if status is not None:
            break
        if ctx.cancelled.is_set():
            _kill_tree(process)
            raise Denied("stopped by the user")
        if time.time() - started > timeout:
            _kill_tree(process)
            reader.join(2)
            output = _decode_output(b"".join(chunks))
            raise ToolError(f"the command did not finish within {timeout} seconds and was "
                            f"stopped. It may be waiting for input, which is not possible "
                            f"here.\nOutput so far:\n{output[-4000:]}")
        time.sleep(0.1)
    reader.join(5)
    if not reader.is_alive():
        process.stdout.close()
    output = _decode_output(b"".join(chunks)).strip()
    if len(output) > RESULT_LIMIT:
        output = output[:3000] + "\n... (middle cut) ...\n" + output[-(RESULT_LIMIT - 3000):]
    body = output or "(no output)"
    if status != 0:
        raise ToolError(f"the command failed (exit code {status}).\nOutput:\n{body}")
    return f"Command finished (exit code 0).\nOutput:\n{body}"


def web_search(ctx: Context, query: str) -> str:
    if not query:
        raise ToolError("query is required")
    try:
        results = websearch.search(query)
    except Exception as error:
        raise ToolError(f"the search failed: {error}") from None
    if not results:
        return f"No results for '{query}'."
    lines = [f"{n}. {r['title']}\n   {r['url']}\n   {r['snippet']}" for n, r in enumerate(results, 1)]
    return (f"Search results for '{query}':\n" + "\n".join(lines) +
            "\n\nUse read_webpage on the most relevant result before answering from it.")


def read_webpage(ctx: Context, url: str) -> str:
    if not url:
        raise ToolError("url is required")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        return websearch.read_page(url)
    except websearch.BlockedAddress as error:
        raise ToolError(str(error)) from None
    except Exception as error:
        raise ToolError(f"the page could not be opened: {error}") from None


# -- the table -----------------------------------------------------------------

def _p(kind: str, description: str) -> dict:
    return {"type": kind, "description": description}


TOOLS = [
    {"name": "list_folder", "category": "read", "fn": list_folder,
     "description": "List the files and folders inside a folder, with sizes and dates.",
     "properties": {"path": _p("string", "Folder path. '.' is the work folder.")},
     "required": []},
    {"name": "find_files", "category": "read", "fn": find_files,
     "description": "Find files or folders by name anywhere under a folder. "
                    "Use a wildcard like '*.pdf' or part of a name like 'invoice'.",
     "properties": {"pattern": _p("string", "Wildcard or part of the name."),
                    "path": _p("string", "Folder to search. Default: the work folder.")},
     "required": ["pattern"]},
    {"name": "search_text", "category": "read", "fn": search_text,
     "description": "Find which files contain some text (also searches inside Word, Excel, "
                    "PowerPoint, HWPX and PDF files).",
     "properties": {"text": _p("string", "The text to look for (not case sensitive)."),
                    "path": _p("string", "File or folder to search. Default: the work folder.")},
     "required": ["text"]},
    {"name": "read_file", "category": "read", "fn": read_file,
     "description": "Read a file. Text files, and the text of .docx, .xlsx, .pptx, .hwpx and "
                    ".pdf documents. Long files are returned in parts.",
     "properties": {"path": _p("string", "The file to read."),
                    "start_line": _p("integer", "First line to show (default 1)."),
                    "max_lines": _p("integer", "How many lines to show (default 400).")},
     "required": ["path"]},
    {"name": "write_file", "category": "change", "fn": write_file,
     "description": "Create a file, or replace one completely. A path ending in .docx becomes a "
                    "real Word document (write the content as markdown: # headings, - lists, "
                    "**bold**, | tables |). A path ending in .xlsx becomes a real Excel sheet "
                    "(write the content as CSV or a markdown table). Folders are created as needed.",
     "properties": {"path": _p("string", "The file to write."),
                    "content": _p("string", "The complete content of the file (or, with "
                                            "append, the text to add)."),
                    "append": _p("boolean", "true = add content at the end of an existing "
                                            "plain text file (.txt, .md, .csv ...) instead of "
                                            "replacing it. Not for .docx / .xlsx.")},
     "required": ["path", "content"]},
    {"name": "edit_file", "category": "change", "fn": edit_file,
     "description": "Change part of a text file: replace old_text (copied exactly from the file) "
                    "with new_text. For Word/Excel files use write_file instead.",
     "properties": {"path": _p("string", "The file to edit."),
                    "old_text": _p("string", "The exact text to replace."),
                    "new_text": _p("string", "What to put instead (empty to remove)."),
                    "replace_all": _p("boolean", "Replace every occurrence (default false).")},
     "required": ["path", "old_text", "new_text"]},
    {"name": "create_folder", "category": "change", "fn": create_folder,
     "description": "Create a folder (and any missing folders above it).",
     "properties": {"path": _p("string", "The folder to create.")},
     "required": ["path"]},
    {"name": "move", "category": "change", "fn": move,
     "description": "Move or rename a file or folder. If destination is an existing folder, "
                    "the item is moved into it.",
     "properties": {"source": _p("string", "What to move."),
                    "destination": _p("string", "New path, or a folder to move it into.")},
     "required": ["source", "destination"]},
    {"name": "copy", "category": "change", "fn": copy,
     "description": "Copy a file or folder.",
     "properties": {"source": _p("string", "What to copy."),
                    "destination": _p("string", "New path, or a folder to copy it into.")},
     "required": ["source", "destination"]},
    {"name": "delete", "category": "change", "fn": delete,
     "description": "Delete a file or folder. The user can restore it with Undo.",
     "properties": {"path": _p("string", "What to delete.")},
     "required": ["path"]},
    {"name": "run_command", "category": "run", "fn": run_command,
     "description": "Run a command in the system shell, in the work folder. Use it only when no "
                    "other tool can do the job (for example converting files or calculating "
                    "with a script). It cannot answer questions the program asks.",
     "properties": {"command": _p("string", "The command line to run."),
                    "reason": _p("string", "One plain sentence for the user saying what this does "
                                           "and why, in the user's language."),
                    "timeout_seconds": _p("integer", "Stop it after this many seconds (default 120).")},
     "required": ["command", "reason"]},
    {"name": "web_search", "category": "web", "fn": web_search,
     "description": "Search the web. Returns titles, links and short snippets.",
     "properties": {"query": _p("string", "What to search for.")},
     "required": ["query"]},
    {"name": "read_webpage", "category": "web", "fn": read_webpage,
     "description": "Read the text of a public web page.",
     "properties": {"url": _p("string", "The page address.")},
     "required": ["url"]},
]

_BY_NAME = {tool["name"]: tool for tool in TOOLS}

# Names small models reach for instead of the real ones.
ALIASES = {"read": "read_file", "open_file": "read_file", "cat": "read_file",
           "write": "write_file", "create_file": "write_file", "save_file": "write_file",
           "list_files": "list_folder", "list_dir": "list_folder", "ls": "list_folder",
           "list_directory": "list_folder", "mkdir": "create_folder", "make_folder": "create_folder",
           "rename": "move", "move_file": "move", "copy_file": "copy", "delete_file": "delete",
           "remove": "delete", "rm": "delete", "run": "run_command", "run_cmd": "run_command",
           "shell": "run_command", "search": "web_search", "search_web": "web_search",
           "fetch": "read_webpage", "browse": "read_webpage", "fetch_url": "read_webpage",
           "grep": "search_text", "find": "find_files", "glob": "find_files"}

# Argument names small models use for the real ones.
_ARG_ALIASES = {"filepath": "path", "file_path": "path", "filename": "path", "file": "path",
                "folder": "path", "directory": "path", "dir": "path", "src": "source",
                "dst": "destination", "dest": "destination", "target": "destination",
                "to": "destination", "from": "source", "old_content": "old_text",
                "new_content": "new_text", "old": "old_text", "new": "new_text", "text_to_find": "text",
                "cmd": "command", "q": "query", "link": "url", "body": "content", "data": "content"}


def lookup(name: str):
    return _BY_NAME.get(ALIASES.get(name, name))


def offered(commands: bool) -> list:
    """The tools the model is told about: run_command only when running programs is on."""
    return [t for t in TOOLS if commands or t["category"] != "run"]


def schemas(commands: bool = True) -> list:
    return [{"name": t["name"], "description": t["description"],
             "parameters": {"type": "object", "properties": t["properties"],
                            "required": t["required"]}} for t in offered(commands)]


def text_protocol_catalog(commands: bool = True) -> str:
    lines = []
    for t in offered(commands):
        params = ", ".join(f"{k}{'' if k in t['required'] else '?'}" for k in t["properties"])
        lines.append(f"- {t['name']}({params}): {t['description']}")
    return "\n".join(lines)


def _normalise(tool: dict, arguments: dict) -> dict:
    out = {}
    accepted = tool["properties"]
    for key, value in (arguments or {}).items():
        real = key if key in accepted else _ARG_ALIASES.get(key, key)
        if real in accepted and real not in out:
            out[real] = value
    if tool["name"] == "search_text" and "text" not in out and "pattern" in (arguments or {}):
        out["text"] = arguments["pattern"]
    return out


def _several(ctx: Context, name: str, arguments: dict) -> list:
    """Several items packed into one move / copy / delete, as small models often do.

    A list, or one string naming several things that each exist ("a.jpg b.jpg",
    "a.jpg, b.jpg") when the string as a whole does not.
    """
    if name not in ("move", "copy", "delete"):
        return []
    value = arguments.get("path" if name == "delete" else "source")
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        if os.path.lexists(ctx.resolve(value)):
            return []
    except (ToolError, Denied):
        return []
    for separator in ("\n", ",", ";", " "):
        parts = [p.strip() for p in value.split(separator) if p.strip()]
        if len(parts) > 1:
            try:
                if all(os.path.lexists(ctx.resolve(p)) for p in parts):
                    return parts
            except (ToolError, Denied):
                return []
    return []


def dispatch(ctx: Context, name: str, arguments: dict) -> tuple:
    """Run one call. Returns (status, result text, display name).

    status: "ok" | "error" | "denied".
    """
    tool = lookup(name)
    if tool is None:
        return "error", (f"Error: there is no tool called '{name}'. Available: "
                         + ", ".join(t["name"] for t in TOOLS)), name
    arguments = _normalise(tool, arguments if isinstance(arguments, dict) else {})
    missing = [key for key in tool["required"] if key not in arguments
               and not (tool["name"] == "edit_file" and key == "new_text")]
    if tool["name"] == "run_command" and "reason" in missing:
        arguments["reason"] = ""
        missing.remove("reason")
    if missing:
        return "error", (f"Error: {tool['name']} needs {', '.join(missing)}. "
                         f"It takes: {', '.join(tool['properties'])}."), tool["name"]
    many = _several(ctx, tool["name"], arguments)
    if many:
        key = "path" if tool["name"] == "delete" else "source"
        each = dict(arguments)
        if tool["name"] != "delete" and isinstance(each.get("destination"), str) \
                and not each["destination"].endswith(("/", "\\")):
            each["destination"] += "/"      # several items always go *into* a folder
        outcomes = [dispatch(ctx, tool["name"], dict(each, **{key: item})) for item in many]
        status = "ok" if all(o[0] == "ok" for o in outcomes) else \
            "denied" if any(o[0] == "denied" for o in outcomes) else "error"
        return status, "\n".join(o[1] for o in outcomes), tool["name"]
    try:
        result = tool["fn"](ctx, **arguments)
    except Denied as reason:
        return "denied", f"Denied: {reason}. Do not try this again; ask the user what to do instead.", \
            tool["name"]
    except ToolError as error:
        return "error", f"Error: {error}", tool["name"]
    except PermissionError:
        return "error", "Error: the operating system refused access to that file or folder.", \
            tool["name"]
    except (OSError, ValueError, TypeError) as error:
        return "error", f"Error: {error}", tool["name"]
    if len(result) > RESULT_LIMIT:
        result = result[:RESULT_LIMIT] + "\n... (cut off here - ask for a smaller part)"
    return "ok", result, tool["name"]
