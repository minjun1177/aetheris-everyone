"""Four AI services behind one shape of event.

Every provider's `stream()` yields the same small events, whatever its wire
format:

    {"text": str}        answer text as it arrives
    {"thinking": str}    reasoning, shown folded away, never stored
    {"tool_call": {"name": str, "arguments": dict, "error": str?}}
    {"done": True}

Plain `urllib` only, so the packaged app carries no vendor SDKs. A failure is a
`ProviderError` with a short `code` the window turns into a sentence a person
can act on ("the key was not accepted", "the local AI is not running").
"""

import base64
import json
import os
import re
import socket
import ssl
import urllib.error
import urllib.request

from aetheris_everyone import settings

TIMEOUT = 300
MAX_OUTPUT_TOKENS = 8192
MAX_IMAGE_BYTES = 4_500_000

LABELS = {"ollama": "Ollama", "anthropic": "Claude (Anthropic)",
          "openai": "ChatGPT (OpenAI)", "gemini": "Gemini (Google)"}


class ProviderError(Exception):
    """`code`: ollama_down | bad_key | no_key | no_model | model_missing |
    rate_limit | network | server | other."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


def ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _open(url: str, payload=None, headers: dict | None = None, timeout: float = TIMEOUT,
          method: str | None = None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"))
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    context = ssl_context() if url.startswith("https") else None
    return urllib.request.urlopen(request, timeout=timeout, context=context)


def _error_from_http(error: urllib.error.HTTPError, provider: str) -> ProviderError:
    try:
        body = error.read().decode("utf-8", "replace")
    except Exception:
        body = ""
    detail = body
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            inner = parsed.get("error", parsed)
            detail = inner.get("message", body) if isinstance(inner, dict) else str(inner)
    except Exception:
        pass
    detail = (detail or str(error)).strip()[:400]
    status = error.code
    if status in (401, 403):
        return ProviderError("bad_key", detail)
    if status == 404 or "not found" in detail.lower():
        return ProviderError("model_missing", detail)
    if status == 429:
        return ProviderError("rate_limit", detail)
    if status >= 500:
        return ProviderError("server", detail)
    if provider == "gemini" and status == 400 and "api key" in detail.lower():
        return ProviderError("bad_key", detail)
    return ProviderError("other", f"HTTP {status}: {detail}")


def _error_from_network(error: Exception, provider: str) -> ProviderError:
    reason = getattr(error, "reason", error)
    if provider == "ollama" and isinstance(reason, (ConnectionRefusedError, ConnectionResetError,
                                                    socket.timeout, TimeoutError, OSError)):
        return ProviderError("ollama_down", str(reason))
    return ProviderError("network", str(reason))


def request_json(url: str, payload=None, headers=None, timeout: float = 30,
                 provider: str = "other", method: str | None = None):
    try:
        with _open(url, payload, headers, timeout, method) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as error:
        raise _error_from_http(error, provider) from None
    except (urllib.error.URLError, OSError) as error:
        raise _error_from_network(error, provider) from None


class Stream:
    """An open streaming response: iterate it for events, `close()` to stop."""

    def __init__(self, provider: str, url: str, payload: dict, headers: dict, parse):
        self._provider = provider
        self._response = None
        self._closed = False
        try:
            self._response = _open(url, payload, headers)
        except urllib.error.HTTPError as error:
            raise _error_from_http(error, provider) from None
        except (urllib.error.URLError, OSError) as error:
            raise _error_from_network(error, provider) from None
        self._parse = parse

    def __iter__(self):
        try:
            yield from self._parse(self._response)
        except (OSError, ValueError, AttributeError) as error:
            if self._closed:
                return
            raise _error_from_network(error, self._provider) from None
        finally:
            self.close()

    def close(self):
        self._closed = True
        try:
            if self._response is not None:
                self._response.close()
        except Exception:
            pass


def _lines(response):
    for raw in response:
        line = raw.decode("utf-8", "replace").strip()
        if line:
            yield line


def _sse(response):
    for line in _lines(response):
        if line.startswith("data:"):
            yield line[5:].strip()


class _Partial:
    """Native call arguments that arrive in fragments, put back together."""

    def __init__(self):
        self.calls = {}

    def start(self, key, name="", call_id=""):
        entry = self.calls.setdefault(key, {"name": "", "id": "", "args": ""})
        if name:
            entry["name"] = name
        if call_id:
            entry["id"] = call_id

    def feed(self, key, fragment):
        self.calls.setdefault(key, {"name": "", "id": "", "args": ""})["args"] += fragment or ""

    def take(self, key):
        entry = self.calls.pop(key, None)
        return _decode_native(entry) if entry and entry["name"] else None

    def drain(self):
        for key in list(self.calls):
            call = self.take(key)
            if call:
                yield call


def _decode_native(entry: dict) -> dict:
    raw = entry.get("args") or "{}"
    try:
        arguments = json.loads(raw)
        if not isinstance(arguments, dict):
            raise ValueError("not an object")
        return {"tool_call": {"name": entry["name"], "arguments": arguments}}
    except ValueError as error:
        return {"tool_call": {"name": entry["name"], "arguments": {},
                              "error": f"arguments were not valid JSON ({error})"}}


# -- images ------------------------------------------------------------------

_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".gif": "image/gif", ".webp": "image/webp"}


def is_image(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in _MIME


def _image_data(path: str):
    """(mime, base64) or None for an image too big or gone."""
    try:
        if os.path.getsize(path) > MAX_IMAGE_BYTES:
            return None
        with open(path, "rb") as f:
            return _MIME.get(os.path.splitext(path)[1].lower(), "image/png"), \
                base64.b64encode(f.read()).decode("ascii")
    except OSError:
        return None


def _images(message: dict) -> list:
    return [data for data in (_image_data(p) for p in message.get("images") or []) if data]


def _split_system(messages: list):
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    return system, [m for m in messages if m["role"] != "system"]


def _merge_runs(messages: list) -> list:
    """Consecutive messages from one side joined: Claude and Gemini need turns to alternate."""
    merged = []
    for message in messages:
        if merged and merged[-1]["role"] == message["role"]:
            last = merged[-1]
            last["content"] = (last["content"] + "\n\n" + message["content"]).strip()
            last["images"] = (last.get("images") or []) + (message.get("images") or [])
        else:
            merged.append({"role": message["role"], "content": message["content"],
                           "images": list(message.get("images") or [])})
    if merged and merged[0]["role"] != "user":
        merged.insert(0, {"role": "user", "content": "(conversation start)", "images": []})
    return merged


# -- providers -------------------------------------------------------------

class Provider:
    name = ""
    needs_key = True

    def __init__(self, model: str = "", key: str = ""):
        self.model = model or settings.model_for(self.name)
        self.key = key or (settings.api_key(self.name) if self.needs_key else "")

    def check_ready(self):
        if self.needs_key and not self.key:
            raise ProviderError("no_key")
        if not self.model:
            raise ProviderError("no_model")

    def native_tools(self) -> bool:
        return True

    def sees_images(self) -> bool:
        return True

    def thinks(self) -> bool:
        return False


class OllamaProvider(Provider):
    name = "ollama"
    needs_key = False
    _capabilities: dict = {}

    @property
    def host(self) -> str:
        return (os.environ.get("AETHERIS_OLLAMA_HOST") or settings.get("ollama_host")
                or "http://127.0.0.1:11434").rstrip("/")

    def capabilities(self) -> list:
        key = (self.host, self.model)
        if key not in self._capabilities:
            data = request_json(f"{self.host}/api/show", {"model": self.model},
                                timeout=20, provider="ollama")
            self._capabilities[key] = list(data.get("capabilities") or [])
        return self._capabilities[key]

    def native_tools(self) -> bool:
        return "tools" in self.capabilities()

    def sees_images(self) -> bool:
        return "vision" in self.capabilities()

    def thinks(self) -> bool:
        return "thinking" in self.capabilities()

    def list_models(self) -> list:
        data = request_json(f"{self.host}/api/tags", timeout=10, provider="ollama")
        return [m.get("model") or m.get("name") for m in data.get("models", [])
                if (m.get("model") or m.get("name"))]

    def stream(self, messages: list, tools: list | None = None, think: bool = False) -> Stream:
        out = []
        for m in messages:
            entry = {"role": m["role"], "content": m["content"]}
            pictures = _images(m)
            if pictures:
                entry["images"] = [data for _, data in pictures]
            out.append(entry)
        payload = {"model": self.model, "messages": out, "stream": True,
                   "keep_alive": "30m",
                   "options": {"num_ctx": int(settings.get("context_tokens") or 16384),
                               "num_predict": MAX_OUTPUT_TOKENS}}
        if tools:
            payload["tools"] = [{"type": "function", "function": {
                "name": t["name"], "description": t["description"],
                "parameters": t["parameters"]}} for t in tools]
        if self.thinks():
            payload["think"] = bool(think)

        def parse(response):
            for line in _lines(response):
                try:
                    chunk = json.loads(line)
                except ValueError:
                    continue
                if chunk.get("error"):
                    raise ProviderError("other", str(chunk["error"]))
                message = chunk.get("message") or {}
                if message.get("thinking"):
                    yield {"thinking": message["thinking"]}
                if message.get("content"):
                    yield {"text": message["content"]}
                for call in message.get("tool_calls") or []:
                    function = call.get("function") or {}
                    arguments = function.get("arguments")
                    if isinstance(arguments, str):
                        yield _decode_native({"name": function.get("name", ""), "args": arguments})
                    elif function.get("name"):
                        yield {"tool_call": {"name": function["name"],
                                             "arguments": arguments if isinstance(arguments, dict) else {}}}
                if chunk.get("done"):
                    yield {"done": True}
                    return

        return Stream("ollama", f"{self.host}/api/chat", payload, {}, parse)


class AnthropicProvider(Provider):
    name = "anthropic"
    base = "https://api.anthropic.com"

    def _headers(self):
        return {"x-api-key": self.key, "anthropic-version": "2023-06-01"}

    def list_models(self) -> list:
        data = request_json(f"{self.base}/v1/models?limit=100", headers=self._headers(),
                            provider=self.name)
        return [item["id"] for item in data.get("data", []) if item.get("id")]

    def stream(self, messages: list, tools: list | None = None, think: bool = False) -> Stream:
        system, conversation = _split_system(messages)
        out = []
        for m in _merge_runs(conversation):
            blocks = [{"type": "image", "source": {"type": "base64", "media_type": mime, "data": data}}
                      for mime, data in _images(m)]
            blocks.append({"type": "text", "text": m["content"] or "."})
            out.append({"role": m["role"], "content": blocks})
        payload = {"model": self.model, "max_tokens": MAX_OUTPUT_TOKENS, "stream": True,
                   "messages": out or [{"role": "user", "content": "."}]}
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = [{"name": t["name"], "description": t["description"],
                                 "input_schema": t["parameters"]} for t in tools]

        def parse(response):
            pending = _Partial()
            for data in _sse(response):
                try:
                    event = json.loads(data)
                except ValueError:
                    continue
                kind = event.get("type")
                if kind == "content_block_start":
                    block = event.get("content_block") or {}
                    if block.get("type") == "tool_use":
                        pending.start(event.get("index"), block.get("name", ""), block.get("id", ""))
                elif kind == "content_block_delta":
                    delta = event.get("delta") or {}
                    if delta.get("type") == "thinking_delta":
                        yield {"thinking": delta.get("thinking", "")}
                    elif delta.get("type") == "input_json_delta":
                        pending.feed(event.get("index"), delta.get("partial_json", ""))
                    elif delta.get("text"):
                        yield {"text": delta["text"]}
                elif kind == "content_block_stop":
                    call = pending.take(event.get("index"))
                    if call:
                        yield call
                elif kind == "error":
                    detail = (event.get("error") or {}).get("message", "error")
                    code = "rate_limit" if "overloaded" in detail.lower() else "server"
                    raise ProviderError(code, detail)
            yield from pending.drain()
            yield {"done": True}

        return Stream(self.name, f"{self.base}/v1/messages", payload, self._headers(), parse)


class OpenAIProvider(Provider):
    name = "openai"
    base = "https://api.openai.com/v1"
    _SKIP = ("audio", "realtime", "transcribe", "tts", "image", "search", "embedding",
             "instruct", "moderation", "dall-e", "whisper", "davinci", "babbage", "codex")

    def _headers(self):
        return {"Authorization": f"Bearer {self.key}"}

    def list_models(self) -> list:
        data = request_json(f"{self.base}/models", headers=self._headers(), provider=self.name)
        items = [i for i in data.get("data", []) if i.get("id")]
        items.sort(key=lambda i: i.get("created", 0), reverse=True)
        return [i["id"] for i in items
                if re.match(r"^(gpt-|o\d|chatgpt)", i["id"])
                and not any(word in i["id"] for word in self._SKIP)]

    def stream(self, messages: list, tools: list | None = None, think: bool = False) -> Stream:
        out = []
        for m in messages:
            pictures = _images(m)
            if pictures and m["role"] == "user":
                content = [{"type": "text", "text": m["content"]}] + [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}
                    for mime, data in pictures]
            else:
                content = m["content"]
            out.append({"role": m["role"], "content": content})
        payload = {"model": self.model, "messages": out, "stream": True,
                   "max_completion_tokens": MAX_OUTPUT_TOKENS}
        if tools:
            payload["tools"] = [{"type": "function", "function": {
                "name": t["name"], "description": t["description"],
                "parameters": t["parameters"]}} for t in tools]

        def parse(response):
            pending = _Partial()
            for data in _sse(response):
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                except ValueError:
                    continue
                if event.get("error"):
                    raise ProviderError("server", str(event["error"].get("message", "error")))
                for choice in event.get("choices") or []:
                    delta = choice.get("delta") or {}
                    if delta.get("reasoning_content"):
                        yield {"thinking": delta["reasoning_content"]}
                    if delta.get("content"):
                        yield {"text": delta["content"]}
                    for call in delta.get("tool_calls") or []:
                        key = call.get("index", 0)
                        function = call.get("function") or {}
                        pending.start(key, function.get("name", ""), call.get("id", ""))
                        pending.feed(key, function.get("arguments", ""))
            yield from pending.drain()
            yield {"done": True}

        return Stream(self.name, f"{self.base}/chat/completions", payload, self._headers(), parse)


class GeminiProvider(Provider):
    name = "gemini"
    base = "https://generativelanguage.googleapis.com"
    _SKIP = ("embedding", "aqa", "tts", "image", "live", "audio", "robotics", "computer-use",
             "learnlm", "imagen", "veo", "gemma", "native")

    def _headers(self):
        return {"x-goog-api-key": self.key}

    def list_models(self) -> list:
        data = request_json(f"{self.base}/v1beta/models?pageSize=200", headers=self._headers(),
                            provider=self.name)
        names = []
        for item in data.get("models", []):
            name = str(item.get("name", "")).removeprefix("models/")
            methods = item.get("supportedGenerationMethods") or []
            if name.startswith("gemini") and "generateContent" in methods \
                    and not any(word in name for word in self._SKIP):
                names.append(name)
        return names

    def stream(self, messages: list, tools: list | None = None, think: bool = False) -> Stream:
        system, conversation = _split_system(messages)
        contents = []
        for m in _merge_runs(conversation):
            parts = [{"inline_data": {"mime_type": mime, "data": data}} for mime, data in _images(m)]
            parts.append({"text": m["content"] or "."})
            contents.append({"role": "model" if m["role"] == "assistant" else "user", "parts": parts})
        payload = {"contents": contents or [{"role": "user", "parts": [{"text": "."}]}],
                   "generationConfig": {"maxOutputTokens": MAX_OUTPUT_TOKENS}}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            declarations = []
            for t in tools:
                entry = {"name": t["name"], "description": t["description"]}
                if t["parameters"].get("properties"):
                    entry["parameters"] = t["parameters"]
                declarations.append(entry)
            payload["tools"] = [{"functionDeclarations": declarations}]

        def parse(response):
            for data in _sse(response):
                try:
                    event = json.loads(data)
                except ValueError:
                    continue
                if event.get("error"):
                    raise ProviderError("server", str(event["error"].get("message", "error")))
                for candidate in event.get("candidates") or []:
                    for part in (candidate.get("content") or {}).get("parts") or []:
                        call = part.get("functionCall")
                        if call and call.get("name"):
                            args = call.get("args")
                            yield {"tool_call": {"name": call["name"],
                                                 "arguments": args if isinstance(args, dict) else {}}}
                        elif part.get("text"):
                            yield {"thinking" if part.get("thought") else "text": part["text"]}
            yield {"done": True}

        url = f"{self.base}/v1beta/models/{self.model}:streamGenerateContent?alt=sse"
        return Stream(self.name, url, payload, self._headers(), parse)


PROVIDERS = {cls.name: cls for cls in (OllamaProvider, AnthropicProvider, OpenAIProvider,
                                       GeminiProvider)}


def make(name: str = "", model: str = "", key: str = "") -> Provider:
    name = name or settings.get("provider") or "ollama"
    return PROVIDERS.get(name, OllamaProvider)(model=model, key=key)


def _version(name: str) -> float:
    match = re.search(r"(\d+(?:\.\d+)?)", name)
    return float(match.group(1)) if match else 0.0


def suggest_model(provider: str, models: list) -> str:
    """A sensible first choice from a provider's list: capable, not the priciest."""
    if not models:
        return ""
    if provider == "anthropic":
        for word in ("sonnet", "opus", "haiku"):
            hits = [m for m in models if word in m]
            if hits:
                return hits[0]          # the API lists the newest first
    if provider == "openai":
        plain = [m for m in models if m.startswith("gpt-") and not re.search(r"mini|nano|\d{4}-\d\d", m)]
        if plain:
            return plain[0]
    if provider == "gemini":
        flash = [m for m in models if "flash" in m and "lite" not in m]
        stable = [m for m in flash if "preview" not in m and "exp" not in m] or flash
        if stable:
            return max(stable, key=_version)
    return models[0]
