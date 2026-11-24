"""One request from the person, carried out: the model, its tool calls, the asking.

Shaped like Aetheris's `chat_turn`: stream a reply, read any tool calls out of
it (natively, or from text with repair), run them through `tools.dispatch`,
hand the results back as messages, and go round again until the model answers
without calling anything. Everything that happens is published as an event, so
the window can draw it live, and recorded in the conversation's `ui` list, so
it can be drawn again later.
"""

import json
import os
import threading
import time
import uuid

from aetheris_everyone import (conversations, history, prompts, providers, settings,
                               toolcalls, tools)

MAX_STEPS = 40
MAX_SAME_CALL = 3
MAX_REFUSALS = 3
MAX_CUT_OFF = 2

CUT_OFF_NOTE = (
    "[System] Your last reply was cut off because it reached the output length limit, so "
    "the tool call in it was NOT carried out and nothing was written. Do not continue from "
    "where it stopped - the cut-off part is gone. Send the work again in smaller pieces: "
    "write_file with only the first part (at most about 80 lines), then one write_file with "
    "append=true for each following part, in order, until it is complete. For .docx or .xlsx, "
    "which cannot be appended to, make the document shorter or split it into several files.")
KEEP_RECENT = 8


class Busy(Exception):
    pass


def _estimate_tokens(text: str) -> int:
    # Hangul and other non-Latin text runs close to one token per character.
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    return ascii_chars // 4 + (len(text) - ascii_chars) + 4


def fit(messages: list, budget: int) -> list:
    """The history, shortened until it fits `budget` tokens.

    Old tool results go first (they are long and already acted on), then whole
    old messages. The newest few are always kept as they are.
    """
    out = [dict(m) for m in messages]
    total = sum(_estimate_tokens(m["content"]) for m in out)
    if total <= budget:
        return out
    for message in out[:-KEEP_RECENT]:
        if message["role"] == "user" and message["content"].startswith("[Tool Result") \
                and len(message["content"]) > 700:
            before = _estimate_tokens(message["content"])
            message["content"] = message["content"][:600] + "\n... (shortened to save space)"
            total -= before - _estimate_tokens(message["content"])
            if total <= budget:
                return out
    while total > budget and len(out) > KEEP_RECENT:
        total -= _estimate_tokens(out.pop(0)["content"])
    # Still too big: the recent results themselves are huge. Shorten them,
    # oldest first, and the newest one last and least.
    for index, message in enumerate(out):
        if total <= budget:
            break
        last = index == len(out) - 1
        limit = max(1500, budget * 2) if last else 1200
        if len(message["content"]) > limit and (message["content"].startswith("[Tool Result")
                                                or not last):
            before = _estimate_tokens(message["content"])
            message["content"] = message["content"][:limit] + "\n... (shortened to save space)"
            total -= before - _estimate_tokens(message["content"])
    if out and out[0]["role"] == "assistant":
        out.insert(0, {"role": "user", "content": "(earlier conversation was shortened)"})
    return out


def _summary(name: str, arguments: dict, folder: str = "") -> dict:
    """What a tool card shows: the few arguments a person cares about."""
    keep = {}
    for key in ("path", "source", "destination", "pattern", "text", "query", "url", "command",
                "reason"):
        if isinstance(arguments, dict) and arguments.get(key):
            value = str(arguments[key])
            if key in ("path", "source", "destination") and folder and os.path.isabs(value):
                try:
                    relative = os.path.relpath(value, folder)
                    if not relative.startswith(".."):
                        value = relative
                except ValueError:
                    pass
            keep[key] = value if len(value) <= 300 else value[:300] + "…"
    return keep


class Agent:
    def __init__(self, emit):
        self.emit = emit
        self._lock = threading.Lock()
        self.busy: str | None = None
        self.cancel = threading.Event()
        self._stream = None
        self._approvals: dict = {}
        self._granted: dict = {}
        self._thread: threading.Thread | None = None
        self.current: dict | None = None      # the conversation the running turn holds

    # -- control from the window ----------------------------------------------
    def start(self, conversation_id: str, text: str, attachments: list) -> str:
        with self._lock:
            if self.busy:
                raise Busy()
            conversation = conversations.load(conversation_id) if conversation_id else None
            if conversation is None:
                folder = settings.get("work_folder") or ""
                conversation = conversations.new(folder)
                conversation["title"] = conversations.title_from(text)
                conversations.save(conversation)
            self.busy = conversation["id"]
            self.current = conversation
            self.cancel.clear()
        thread = threading.Thread(target=self._run, args=(conversation, text, attachments),
                                  daemon=True)
        self._thread = thread
        thread.start()
        return conversation["id"]

    def stop(self) -> None:
        self.cancel.set()
        stream = self._stream
        if stream is not None:
            stream.close()
        for pending in list(self._approvals.values()):
            pending["answer"] = "deny"
            pending["event"].set()

    def wait(self, timeout: float) -> bool:
        """Let a running turn finish its bookkeeping (the change card); False if it did not."""
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()

    def answer(self, approval_id: str, answer: str) -> bool:
        pending = self._approvals.get(approval_id)
        if not pending:
            return False
        pending["answer"] = answer if answer in ("allow", "always", "deny") else "deny"
        pending["event"].set()
        return True

    def pending_approvals(self) -> list:
        return [p["public"] for p in self._approvals.values()]

    def forget(self, conversation_id: str) -> None:
        """Drop what was allowed "for this conversation" once it is deleted."""
        self._granted.pop(conversation_id, None)

    # -- the turn ----------------------------------------------------------------
    def _ask(self, conversation_id: str, request: dict) -> str:
        approval_id = uuid.uuid4().hex[:10]
        public = {"type": "approval", "conversation": conversation_id, "id": approval_id,
                  "request": request}
        pending = {"event": threading.Event(), "answer": "deny", "public": public}
        self._approvals[approval_id] = pending
        self.emit(public)
        try:
            while not pending["event"].wait(0.5):
                if self.cancel.is_set():
                    return "deny"
            return pending["answer"]
        finally:
            self._approvals.pop(approval_id, None)
            self.emit({"type": "approval_done", "conversation": conversation_id, "id": approval_id,
                       "answer": pending["answer"]})

    def _ui(self, conversation: dict, item: dict) -> None:
        conversation["ui"].append(item)
        self.emit({"type": "item", "conversation": conversation["id"], "item": item})

    def _run(self, conversation: dict, text: str, attachments: list) -> None:
        cid = conversation["id"]
        folder = conversation.get("folder") or settings.get("work_folder") or os.path.expanduser("~")
        if not conversation.get("folder"):
            conversation["folder"] = folder
        os.makedirs(folder, exist_ok=True)
        changes = history.ChangeSet(cid)
        try:
            self.emit({"type": "turn_start", "conversation": cid})
            images = [p for p in attachments if providers.is_image(p)]
            files = [p for p in attachments if not providers.is_image(p)]
            self._ui(conversation, {"kind": "user", "text": text, "time": time.time(),
                                    "attachments": [{"name": os.path.basename(p), "path": p,
                                                     "image": providers.is_image(p)}
                                                    for p in attachments]})
            content = text
            if files:
                content += "\n\n" + "\n".join(f"[Attached file: {p}]" for p in files)
            message = {"role": "user", "content": content}

            provider = providers.make()
            provider.check_ready()
            native = provider.native_tools()
            if images:
                if provider.sees_images():
                    shown = [p for p in images if providers.image_source(p)]
                    too_big = [p for p in images if p not in shown]
                    if shown:
                        message["images"] = shown
                    if too_big:
                        self._ui(conversation, {"kind": "notice", "code": "image_too_big"})
                        message["content"] += "\n\n" + "\n".join(
                            f"[Attached picture too large to show you: {p}]" for p in too_big)
                else:
                    self._ui(conversation, {"kind": "notice", "code": "no_vision"})
                    message["content"] += "\n\n" + "\n".join(
                        f"[Attached picture you cannot see: {p}]" for p in images)
            conversation["messages"].append(message)
            conversations.save(conversation)

            careful = bool(settings.get("careful"))
            ctx = tools.Context(folder, changes, lambda request: self._ask(cid, request),
                                settings.get("safety"), self._granted.setdefault(cid, set()),
                                self.cancel, extra_readable=files + images,
                                allow_commands=bool(settings.get("allow_commands")))
            self._loop(conversation, provider, native, careful, ctx)
        except providers.ProviderError as error:
            self._ui(conversation, {"kind": "error", "code": error.code, "detail": error.detail})
        except Exception as error:          # never leave the window spinning
            self._ui(conversation, {"kind": "error", "code": "other",
                                    "detail": f"{type(error).__name__}: {error}"})
        finally:
            self._stream = None
            if changes.ops:
                changes.save()
                self._ui(conversation, {"kind": "changes", "change_id": changes.id,
                                        "files": changes.files(), "undone": False})
            if self.cancel.is_set():
                self._ui(conversation, {"kind": "notice", "code": "stopped"})
            conversations.save(conversation)
            with self._lock:
                self.busy = None
                self.current = None
            self.emit({"type": "turn_end", "conversation": cid})

    def _loop(self, conversation, provider, native: bool, careful: bool, ctx) -> None:
        cid = conversation["id"]
        latest = next((m["content"] for m in reversed(conversation["messages"])
                       if m["role"] == "user" and not m["content"].startswith("[")), "")
        system = prompts.system_prompt(ctx.folder, native, careful, latest, ctx.allow_commands)
        if provider.name == "ollama":
            budget = int(int(settings.get("context_tokens") or 16384) * 0.7) - \
                _estimate_tokens(system)
        else:
            budget = 120_000
        seen_calls: dict = {}
        refusals = 0
        nudged = False
        cut_offs = 0

        for _step in range(MAX_STEPS):
            if self.cancel.is_set():
                return
            history_now = [{"role": "system", "content": system}] + \
                fit(conversation["messages"], max(2000, budget))
            reply_id = uuid.uuid4().hex[:10]
            self.emit({"type": "reply_start", "conversation": cid, "id": reply_id})
            raw, native_calls, thinking, truncated = self._stream_reply(
                cid, reply_id, provider, history_now, native, careful, ctx.allow_commands)
            if self.cancel.is_set():
                visible = toolcalls.visible_text(raw)
                if visible:
                    conversation["messages"].append({"role": "assistant", "content": visible})
                    self._ui(conversation, {"kind": "assistant", "id": reply_id, "text": visible})
                return

            if native_calls:
                calls = [(c["name"], c.get("arguments") or {}, c.get("error")) for c in native_calls]
            else:
                calls = [(name, args, None) for name, args in
                         toolcalls.parse_tool_calls(raw, known=lambda n: tools.lookup(n) is not None)]
            visible = toolcalls.visible_text(raw)
            stored = toolcalls.strip_thinking(raw)
            cut = stored.find("[Tool Result for")
            if cut != -1:                    # a model writing its own results
                stored = stored[:cut].rstrip()
            if native_calls:
                stored = "\n".join([visible] + [toolcalls.render_call(n, a) for n, a, _ in calls]).strip()
            if visible or thinking:
                self._ui(conversation, {"kind": "assistant", "id": reply_id, "text": visible,
                                        "thinking": thinking[:20000] if thinking else ""})
            else:
                self.emit({"type": "reply_empty", "conversation": cid, "id": reply_id})

            if truncated and _cut_call(raw, native, calls, visible):
                # A call cut off by the output limit. Keeping its half in the history makes
                # the model "continue" it, writing only the rest of a file over the whole.
                cut_offs += 1
                if cut_offs > MAX_CUT_OFF:
                    self._ui(conversation, {"kind": "notice", "code": "cut_off"})
                    return
                conversation["messages"].append(
                    {"role": "assistant", "content": (visible + "\n\n" if visible else "")
                     + "(my reply was cut off here)"})
                conversation["messages"].append({"role": "user", "content": CUT_OFF_NOTE})
                continue

            if not calls:
                if not visible:
                    if _has_tool_tag(raw) and not nudged:
                        nudged = True
                        conversation["messages"].append({"role": "assistant", "content": stored or "."})
                        conversation["messages"].append({"role": "user", "content": (
                            "[System] Your tool call could not be read (it was cut off or the JSON "
                            "was broken). Send it again, keeping long text in a raw block.")})
                        continue
                    if not nudged:
                        nudged = True
                        conversation["messages"].append({"role": "user", "content": (
                            "[System] Your reply was empty. Answer the user, or use a tool.")})
                        continue
                    self._ui(conversation, {"kind": "notice", "code": "empty_reply"})
                    return
                conversation["messages"].append({"role": "assistant", "content": stored})
                return

            conversation["messages"].append({"role": "assistant", "content": stored or "."})
            for name, arguments, error in calls:
                if self.cancel.is_set():
                    return
                call_id = uuid.uuid4().hex[:10]
                summary = _summary(name, arguments, ctx.folder)
                self.emit({"type": "tool_start", "conversation": cid, "id": call_id,
                           "name": name, "args": summary})
                key = json.dumps([name, arguments], sort_keys=True, ensure_ascii=False, default=str)
                seen_calls[key] = seen_calls.get(key, 0) + 1
                if error:
                    status, result, real = "error", (f"Error: the arguments for {name} were not "
                                                     f"valid JSON ({error}). Send the call again."), name
                elif seen_calls[key] > MAX_SAME_CALL:
                    status, result, real = "error", ("Error: you have already made exactly this "
                                                     "call several times. Do something different, "
                                                     "or answer the user."), name
                else:
                    status, result, real = tools.dispatch(ctx, name, arguments)
                item = {"kind": "tool", "id": call_id, "name": real, "args": summary,
                        "status": status, "result": result[:1500]}
                self._ui(conversation, item)
                conversation["messages"].append(
                    {"role": "user", "content": f"[Tool Result for '{real}']:\n{result}"})
                refusals = refusals + 1 if status == "denied" else 0
            conversations.save(conversation)
            if refusals >= MAX_REFUSALS:
                self._ui(conversation, {"kind": "notice", "code": "too_many_refusals"})
                return
        self._ui(conversation, {"kind": "notice", "code": "step_limit"})

    def _stream_reply(self, cid, reply_id, provider, messages, native, careful, commands=False):
        stream_filter = toolcalls.StreamFilter()
        raw, thinking, calls = [], [], []
        truncated = False
        attempt = 0
        while True:
            try:
                stream = provider.stream(messages, tools=tools.schemas(commands) if native else None,
                                         think=careful)
            except providers.ProviderError as error:
                if not self._wait_to_retry(cid, reply_id, error, attempt):
                    if self.cancel.is_set():
                        return "", [], "", False
                    raise
                attempt += 1
                continue
            self._stream = stream
            if self.cancel.is_set():
                stream.close()
            try:
                for event in stream:
                    if self.cancel.is_set():
                        break
                    if "text" in event:
                        raw.append(event["text"])
                        for kind, piece in stream_filter.feed(event["text"]):
                            if kind == "think":
                                thinking.append(piece)
                            self.emit({"type": "delta", "conversation": cid, "id": reply_id,
                                       "kind": "thinking" if kind == "think" else "text",
                                       "text": piece})
                    elif "thinking" in event:
                        thinking.append(event["thinking"])
                        self.emit({"type": "delta", "conversation": cid, "id": reply_id,
                                   "kind": "thinking", "text": event["thinking"]})
                    elif "tool_call" in event:
                        calls.append(event["tool_call"])
                    elif event.get("done"):
                        truncated = bool(event.get("truncated"))
                break
            except providers.ProviderError as error:
                # Asked again only while nothing has arrived: a started reply has been shown.
                if raw or thinking or calls or not self._wait_to_retry(cid, reply_id, error, attempt):
                    if self.cancel.is_set() and not (raw or thinking or calls):
                        return "", [], "", False
                    raise
                attempt += 1
            finally:
                stream.close()
                self._stream = None
        for kind, piece in stream_filter.close():
            if kind == "think":
                thinking.append(piece)
            self.emit({"type": "delta", "conversation": cid, "id": reply_id,
                       "kind": "thinking" if kind == "think" else "text", "text": piece})
        return "".join(raw), calls, "".join(thinking), truncated


    def _wait_to_retry(self, cid: str, reply_id: str, error: Exception, attempt: int) -> bool:
        """Wait before asking a busy service again; False when it should not be asked again."""
        seconds = providers.retry_delay(error, attempt)
        if seconds is None or self.cancel.is_set():
            return False
        self.emit({"type": "retry", "conversation": cid, "id": reply_id, "code": error.code,
                   "seconds": max(1, round(seconds)), "attempt": attempt + 1,
                   "of": providers.RETRIES})
        return not self.cancel.wait(seconds)


def _has_tool_tag(text: str) -> bool:
    return toolcalls.TOOL_CALL_TAG in text


def _cut_call(raw: str, native: bool, calls: list, visible: str) -> bool:
    """Whether a reply stopped by the output limit stopped inside a tool call."""
    if raw.count(toolcalls.TOOL_CALL_TAG) > raw.count("</tool_call>"):
        return True                  # text protocol: a call was opened and never closed
    # Native: the call either never arrived, or arrived with arguments cut short (Ollama
    # hands back what it parsed - a write_file with half its content, or with none).
    return native and (bool(calls) or not visible)
