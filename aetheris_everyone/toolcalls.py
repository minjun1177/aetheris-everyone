"""Reading tool calls out of a model's text, and keeping them off the screen.

Carried over from Aetheris, where it was built for 4B-parameter local models:
they forget a closing brace, nest the call one level too deep, rename `name`,
or wrap the whole thing in a markdown fence. Each of those is repaired here
rather than thrown away, because a dropped call is a turn that silently does
nothing - the most confusing thing a person can be shown.

Long values (a whole file) may be sent as a raw block after the JSON instead of
inside it, so the model never has to escape a document into a JSON string:

    <tool_call>
    {"name": "write_file", "arguments": {"path": "notes.md"}}
    <content>
    # Notes
    </content>
    </tool_call>
"""

import json
import re

TOOL_CALL_TAG = "<tool_call>"
THINK_OPEN = ("<think>", "<thinking>")
THINK_CLOSE = ("</think>", "</thinking>")

_THINK_BLOCK = re.compile(r"<(think|thinking)>.*?</\1>", re.DOTALL)
_THINK_START = re.compile(r"<(think|thinking)>")

RAW_KEYS = ("content", "new_text", "old_text", "text", "body")


def _holdback(buffer: str, markers: tuple) -> int:
    """Length of the tail that could still grow into one of `markers`."""
    longest = max(len(m) for m in markers) - 1
    for size in range(min(len(buffer), longest), 0, -1):
        tail = buffer[-size:]
        if any(m.startswith(tail) for m in markers):
            return size
    return 0


class StreamFilter:
    """Splits a raw stream into ("prose" | "think", text) pieces.

    Everything from `<tool_call>` on is withheld: it is not prose, and the
    window shows the call as an activity card instead.
    """

    def __init__(self):
        self._buffer = ""
        self._state = "prose"        # prose | think | tool

    def _markers(self) -> tuple:
        if self._state == "think":
            return THINK_CLOSE + (TOOL_CALL_TAG,)
        return (TOOL_CALL_TAG,) + THINK_OPEN

    def feed(self, text: str) -> list:
        self._buffer += text
        return self._drain(final=False)

    def close(self) -> list:
        return self._drain(final=True)

    def _drain(self, final: bool) -> list:
        out = []
        while self._buffer and self._state != "tool":
            markers = self._markers()
            hits = [(self._buffer.find(m), m) for m in markers if m in self._buffer]
            if hits:
                index, marker = min(hits, key=lambda hit: hit[0])
                if index:
                    out.append((self._state, self._buffer[:index]))
                self._buffer = self._buffer[index + len(marker):]
                if marker == TOOL_CALL_TAG:
                    self._state = "tool"
                    self._buffer = ""
                else:
                    self._state = "think" if marker in THINK_OPEN else "prose"
                continue
            hold = 0 if final else _holdback(self._buffer, markers)
            keep = len(self._buffer) - hold
            if keep > 0:
                out.append((self._state, self._buffer[:keep]))
                self._buffer = self._buffer[keep:]
            break
        return [(kind, text) for kind, text in out if text]


def strip_thinking(text: str) -> str:
    cleaned = _THINK_BLOCK.sub("", text)
    start = _THINK_START.search(cleaned)
    if start:
        tail = cleaned[start.end():]
        tool = tail.find(TOOL_CALL_TAG)
        cleaned = cleaned[:start.start()] + (tail[tool:] if tool != -1 else "")
    return cleaned.strip()


def visible_text(text: str) -> str:
    """What the person should see of a reply: no reasoning, no call markup."""
    text = strip_thinking(text)
    cut = text.find(TOOL_CALL_TAG)
    if cut != -1:
        text = text[:cut]
    return text.strip()


# -- JSON repair -------------------------------------------------------------

_CLOSERS = {"{": "}", "[": "]"}
_JSON_ESCAPES = {'"': '"', "\\": "\\", "/": "/", "b": "\b",
                 "f": "\f", "n": "\n", "r": "\r", "t": "\t"}
_FIELD_PATTERN = re.compile(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*:\s*"')
_SCALAR_PATTERN = re.compile(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*:\s*"((?:[^"\\]|\\.)*)"')
_RAW_BLOCK = re.compile(r"<(%s)>\r?\n?(.*?)\r?\n?</\1>" % "|".join(RAW_KEYS), re.DOTALL)
_RAW_OPEN = re.compile(r"<(%s)>\r?\n?" % "|".join(RAW_KEYS))
_FENCED_CALL = re.compile(
    r"```[ \t]*(?P<lang>[A-Za-z_][A-Za-z0-9_]*)?[ \t]*\r?\n(?P<body>.*?)\r?\n?```", re.DOTALL)
_CALL_FENCE_LANGS = frozenset(
    ("tool_call", "tool_code", "tool_use", "toolcall", "function_call", "functioncall"))
_ENVELOPE_KEYS = frozenset(
    ("tool_call", "tool_use", "toolcall", "function_call", "functioncall",
     "function", "tool", "call", "action"))
_NAME_KEYS = ("name", "tool_name", "toolName", "function_name", "functionName",
              "tool", "function", "recipient_name")


def _json_tail_state(blob: str):
    depth, in_string, escaped = [], False, False
    for char in blob:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in _CLOSERS:
            depth.append(char)
        elif char in ("}", "]") and depth:
            depth.pop()
    return depth, in_string


def _close_brackets(blob: str):
    depth, _ = _json_tail_state(blob)
    if not depth:
        return None
    closers = "".join(_CLOSERS[b] for b in reversed(depth))
    try:
        repaired, _ = json.JSONDecoder().raw_decode(blob + closers)
    except json.JSONDecodeError:
        return None
    return repaired if isinstance(repaired, dict) else None


def _lenient_unescape(raw: str) -> str:
    out, i = [], 0
    while i < len(raw):
        char = raw[i]
        if char != "\\" or i + 1 >= len(raw):
            out.append(char)
            i += 1
            continue
        nxt = raw[i + 1]
        if nxt in _JSON_ESCAPES:
            out.append(_JSON_ESCAPES[nxt])
            i += 2
        elif nxt == "u" and i + 6 <= len(raw):
            try:
                out.append(chr(int(raw[i + 2:i + 6], 16)))
                i += 6
            except ValueError:
                out.append(char)
                i += 1
        else:
            out.append(char + nxt)
            i += 2
    return "".join(out)


def _lenient_tool_call(blob: str):
    """A call whose one long text field broke the JSON, read by position."""
    name_match = re.search(r'"name"\s*:\s*"([A-Za-z0-9_]+)"', blob)
    if not name_match:
        return None
    long_fields = [(m.group(1), m.end()) for m in _FIELD_PATTERN.finditer(blob)
                   if m.group(1) in RAW_KEYS]
    if len(long_fields) != 1:
        return None
    key, value_start = long_fields[0]
    close_quote = blob.rfind('"')
    if close_quote <= value_start or blob[close_quote + 1:].strip(" \t\r\n}]),"):
        return None
    arguments = {m.group(1): _lenient_unescape(m.group(2))
                 for m in _SCALAR_PATTERN.finditer(blob[:value_start]) if m.group(1) != "name"}
    arguments[key] = _lenient_unescape(blob[value_start:close_quote])
    return {"name": name_match.group(1), "arguments": arguments}


def _normalise_arguments(data: dict) -> dict:
    arguments = data.get("arguments", data.get("parameters"))
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            arguments = {}
    if isinstance(arguments, dict) and arguments:
        return arguments
    flattened = {k: v for k, v in data.items()
                 if k not in _NAME_KEYS and k not in ("arguments", "parameters")}
    if flattened:
        return flattened
    return arguments if isinstance(arguments, dict) else {}


def _take_raw_blocks(blob: str, complete: bool):
    blocks = {}

    def _collect(match):
        if match.group(2).strip():
            blocks[match.group(1)] = match.group(2)
        return ""

    stripped = _RAW_BLOCK.sub(_collect, blob)
    opened = _RAW_OPEN.search(stripped)
    if opened:
        if not complete:
            return stripped, blocks, True
        blocks[opened.group(1)] = stripped[opened.end():].rstrip()
        stripped = stripped[:opened.start()]
    return stripped, blocks, False


def _unwrap_envelope(data: dict) -> dict:
    if data.get("name") or len(data) != 1:
        return data
    key, inner = next(iter(data.items()))
    if key.lower() not in _ENVELOPE_KEYS or not isinstance(inner, dict):
        return data
    return inner if inner.get("name") else data


def _rename_to_name(data: dict) -> dict:
    if data.get("name"):
        return data
    for key in _NAME_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            renamed = {k: v for k, v in data.items() if k != key}
            renamed["name"] = value.strip()
            return renamed
    return data


def decode_call(blob: str, complete: bool = True):
    """(name, arguments), or None when nothing trustworthy can be read."""
    blob, raw_blocks, cut_block = _take_raw_blocks(blob.strip(), complete)
    if cut_block:
        return None
    blob = blob.strip()
    try:
        data, _ = json.JSONDecoder().raw_decode(blob)
        if not isinstance(data, dict):
            data = None
    except json.JSONDecodeError:
        data = None
    _, in_string = _json_tail_state(blob)
    if data is None and not in_string and complete:
        data = _close_brackets(blob) or _lenient_tool_call(blob)
    if data is None:
        return None
    data = _rename_to_name(_unwrap_envelope(data))
    if not data.get("name") or not isinstance(data.get("name"), str):
        return None
    arguments = _normalise_arguments(data)
    arguments.update(raw_blocks)
    return data["name"], arguments


def parse_tool_calls(text: str, known=None) -> list:
    """Every tool call in a reply, in order. `known(name)` vets fenced ones."""
    text = strip_thinking(text)
    calls, closed = [], False
    for match in re.finditer(r"<tool_call>(.*?)</tool_call>", text, re.DOTALL):
        closed = True
        call = decode_call(match.group(1))
        if call:
            calls.append(call)
    if calls or closed:
        return calls
    start = text.find(TOOL_CALL_TAG)
    if start != -1:
        call = decode_call(text[start + len(TOOL_CALL_TAG):], complete=False)
        return [call] if call else []
    for match in _FENCED_CALL.finditer(text):
        lang = (match.group("lang") or "").lower()
        if lang and lang not in _CALL_FENCE_LANGS and lang != "json":
            continue
        tail = text[match.end():]
        next_fence = tail.find("```")
        call = decode_call(match.group("body") + "\n" + (tail if next_fence == -1 else tail[:next_fence]))
        if call and (known is None or known(call[0])):
            calls.append(call)
    return calls


def render_call(name: str, arguments: dict) -> str:
    """A native call written into the history the way the text protocol would."""
    body = {"name": name, "arguments": arguments or {}}
    return f"{TOOL_CALL_TAG}\n{json.dumps(body, ensure_ascii=False)}\n</tool_call>"
