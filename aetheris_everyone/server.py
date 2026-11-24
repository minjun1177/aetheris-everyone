"""The local web server the window talks to.

Bound to 127.0.0.1 only, on a random port, and every /api call must carry a
random token the window was given at start - so neither another computer nor
another web page open in a browser can drive the assistant. The Host header
is checked too, which stops a DNS-rebinding page from posing as localhost.

Live updates go out as Server-Sent Events on /api/events.
"""

import json
import mimetypes
import os
import queue
import secrets
import shutil
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from aetheris_everyone import (__version__, agent, conversations, history, memory, ollama_setup,
                               paths, providers, settings, system, usage, websearch)

MAX_UPLOAD = 200 * 1024 * 1024

# The window's own files, typed here rather than by `mimetypes`: on Windows that reads the
# registry, which may lack .woff2 or call .js "text/plain" (blocked under nosniff).
STATIC_TYPES = {".html": "text/html", ".js": "application/javascript", ".css": "text/css",
                ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon",
                ".woff2": "font/woff2", ".json": "application/json"}


class Bus:
    """Fan-out of events to every open window."""

    def __init__(self):
        self._subscribers: list = []
        self._lock = threading.Lock()
        self.last_job: dict = {}

    def subscribe(self) -> queue.Queue:
        q = queue.Queue(maxsize=5000)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def publish(self, event: dict) -> None:
        if event.get("type") in ("pull", "install"):
            self.last_job[event["type"]] = event
        with self._lock:
            for q in list(self._subscribers):
                try:
                    q.put_nowait(event)
                except queue.Full:
                    pass


class App:
    def __init__(self):
        self.token = secrets.token_urlsafe(24)
        self.bus = Bus()
        self.agent = agent.Agent(self.bus.publish)
        self.last_seen = time.time()
        self.job_stop = threading.Event()
        self.job_thread: threading.Thread | None = None
        self.port = 0

    # -- state -----------------------------------------------------------------
    def state(self) -> dict:
        current = settings.load()
        name = current["provider"]
        return {"version": __version__, "settings": current, "keys": settings.has_keys(),
                "provider_label": providers.LABELS.get(name, name),
                "model": settings.model_for(name), "busy": self.agent.busy,
                "approvals": self.agent.pending_approvals(),
                "conversations": conversations.list_all(),
                "memories": memory.load(),
                "jobs": self.bus.last_job, "job_running": bool(self.job_thread
                                                                and self.job_thread.is_alive()),
                "default_folder": paths.default_work_folder(),
                "data_dir": paths.data_dir(),
                "key_storage": settings.key_storage(),
                "can_shortcut": system.can_make_shortcut(),
                "home": os.path.expanduser("~")}

    def run_job(self, target, *args) -> bool:
        if self.job_thread and self.job_thread.is_alive():
            return False
        self.job_stop = threading.Event()
        self.bus.last_job = {}
        self.job_thread = threading.Thread(target=target, args=(*args, self.bus.publish,
                                                                self.job_stop), daemon=True)
        self.job_thread.start()
        return True


def _pull_then_use(model: str, emit, stop):
    if ollama_setup.pull(model, emit, stop):
        ollama_setup.use_model(model)
        emit({"type": "settings_changed"})


class Handler(BaseHTTPRequestHandler):
    app: App = None          # set by `serve`
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    # -- plumbing --------------------------------------------------------------
    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").lower()
        return host in (f"127.0.0.1:{self.app.port}", f"localhost:{self.app.port}")

    def _token_ok(self, query: dict) -> bool:
        given = self.headers.get("X-Token") or (query.get("t") or [""])[0]
        return secrets.compare_digest(given, self.app.token)

    def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, data, status: int = 200):
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}

    def _static(self, path: str):
        if path in ("", "/"):
            path = "/index.html"
        root = os.path.realpath(paths.resource("web"))
        target = os.path.realpath(os.path.join(root, path.lstrip("/")))
        if not target.startswith(root + os.sep) or not os.path.isfile(target):
            return self._send(404, b"not found", "text/plain")
        with open(target, "rb") as f:
            body = f.read()
        kind = STATIC_TYPES.get(os.path.splitext(target)[1].lower()) or \
            mimetypes.guess_type(target)[0] or "application/octet-stream"
        if kind.startswith("text/") or kind in ("application/javascript", "image/svg+xml"):
            kind += "; charset=utf-8"
        extra = {}
        if target.endswith(".html"):
            extra["Content-Security-Policy"] = (
                "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
                "script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        self._send(200, body, kind, extra)

    # -- methods ---------------------------------------------------------------
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, b"forbidden", "text/plain")
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        if not parsed.path.startswith("/api/"):
            return self._static(parsed.path)
        if not self._token_ok(query):
            return self._json({"error": "unauthorised"}, 401)
        self.app.last_seen = time.time()
        route = parsed.path[len("/api/"):]
        try:
            if route == "events":
                return self._events()
            if route == "state":
                return self._json(self.app.state())
            if route == "conversation":
                data = conversations.load((query.get("id") or [""])[0])
                return self._json(data or {"error": "not_found"}, 200 if data else 404)
            if route == "usage":
                return self._json({"months": usage.summary()})
            if route == "ollama/status":
                return self._json(ollama_setup.status())
            if route == "ollama/size":
                model = (query.get("model") or [""])[0]
                return self._json({"model": model, "bytes": ollama_setup.download_size(model)})
            if route == "file":
                return self._file((query.get("path") or [""])[0])
            return self._json({"error": "unknown"}, 404)
        except providers.ProviderError as error:
            return self._json({"error": error.code, "detail": error.detail}, 502)

    def do_POST(self):
        if not self._host_ok():
            return self._send(403, b"forbidden", "text/plain")
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        if not parsed.path.startswith("/api/") or not self._token_ok(query):
            return self._json({"error": "unauthorised"}, 401)
        self.app.last_seen = time.time()
        route = parsed.path[len("/api/"):]
        if route == "upload":
            return self._upload()
        body = self._body()
        try:
            handler = getattr(self, "_post_" + route.replace("/", "_"), None)
            if handler is None:
                return self._json({"error": "unknown"}, 404)
            return handler(body)
        except providers.ProviderError as error:
            return self._json({"ok": False, "error": error.code, "detail": error.detail})
        except Exception as error:
            return self._json({"ok": False, "error": "other", "detail": str(error)}, 500)

    # -- streams and files ---------------------------------------------------------
    def _events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        q = self.app.bus.subscribe()
        try:
            self.wfile.write(b"retry: 1500\n\n")
            self.wfile.flush()
            while True:
                try:
                    event = q.get(timeout=15)
                    payload = json.dumps(event, ensure_ascii=False)
                    self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
                self.app.last_seen = time.time()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            self.app.bus.unsubscribe(q)
            self.close_connection = True

    def _file(self, path: str):
        """An attached picture, for its thumbnail. Only pictures, only by full path."""
        if not path or not providers.is_image(path) or not os.path.isfile(path):
            return self._send(404, b"not found", "text/plain")
        if os.path.getsize(path) > 30_000_000:
            return self._send(413, b"too large", "text/plain")
        with open(path, "rb") as f:
            body = f.read()
        self._send(200, body, mimetypes.guess_type(path)[0] or "application/octet-stream")

    def _upload(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_UPLOAD:
            self.close_connection = True          # the unread body must not become a request
            return self._json({"ok": False, "error": "too_large"}, 413)
        small_for = urllib.parse.unquote(self.headers.get("X-Small-For") or "")
        if small_for:
            # The reduced copy of a large photo uploaded just before, kept beside it.
            original = os.path.realpath(small_for)
            if not providers.is_image(original) or not os.path.isfile(original) or \
                    os.path.dirname(os.path.dirname(os.path.dirname(original))) != _attachments_root():
                self.close_connection = True
                return self._json({"ok": False, "error": "other"}, 400)
            target = original + providers.SMALL_SUFFIX
            name = os.path.basename(target)
        else:
            name = urllib.parse.unquote(self.headers.get("X-Filename") or "file")
            name = os.path.basename(name.replace("\\", "/")).strip() or "file"
            folder = paths.sub("attachments", time.strftime("%Y%m%d"), uuid.uuid4().hex[:8])
            target = os.path.join(folder, name)
        remaining = length
        try:
            with open(target, "wb") as out:
                while remaining:
                    chunk = self.rfile.read(min(remaining, 1 << 20))
                    if not chunk:
                        break
                    out.write(chunk)
                    remaining -= len(chunk)
        except OSError:
            remaining = remaining or 1
        if remaining:
            # Cut off on the way (window closed, connection dropped): half a file is no file.
            try:
                os.remove(target)
            except OSError:
                pass
            self.close_connection = True
            return self._json({"ok": False, "error": "incomplete"}, 400)
        return self._json({"ok": True, "path": target, "name": name,
                           "image": providers.is_image(target)})

    # -- POST routes ------------------------------------------------------------------
    def _post_heartbeat(self, body):
        return self._json({"ok": True})

    def _post_settings(self, body):
        if "work_folder" in body and body["work_folder"]:
            folder = os.path.abspath(os.path.expanduser(str(body["work_folder"])))
            os.makedirs(folder, exist_ok=True)
            body["work_folder"] = folder
        updated = settings.update(body)
        self.app.bus.publish({"type": "settings_changed"})
        return self._json({"ok": True, "settings": updated})

    def _post_provider_test(self, body):
        name = body.get("provider", "")
        if name not in providers.PROVIDERS:
            return self._json({"ok": False, "error": "other"})
        key = (body.get("key") or "").strip()
        provider = providers.make(name, model="-", key=key or settings.api_key(name))
        if provider.needs_key and not provider.key:
            return self._json({"ok": False, "error": "no_key"})
        models = provider.list_models()
        if key:
            settings.set_api_key(name, key)
        return self._json({"ok": True, "models": models,
                           "suggested": settings.model_for(name) if settings.model_for(name) in models
                           else providers.suggest_model(name, models)})

    def _post_provider_use(self, body):
        name, model = body.get("provider", ""), (body.get("model") or "").strip()
        if name not in providers.PROVIDERS or not model:
            return self._json({"ok": False, "error": "other"})
        settings.update({"provider": name, "models": {name: model}})
        self.app.bus.publish({"type": "settings_changed"})
        return self._json({"ok": True})

    def _post_provider_forget(self, body):
        settings.set_api_key(body.get("provider", ""), "")
        self.app.bus.publish({"type": "settings_changed"})
        return self._json({"ok": True, "keys": settings.has_keys()})

    def _post_ollama_test(self, body):
        """Whether an Ollama address answers, before it is saved."""
        url = settings.clean_url(body.get("host"))
        if not url:
            return self._json({"ok": False, "error": "bad_address"})
        try:
            data = providers.request_json(f"{url}/api/version", timeout=5, provider="ollama")
        except providers.ProviderError as error:
            return self._json({"ok": False, "error": error.code, "detail": error.detail})
        return self._json({"ok": True, "version": data.get("version", ""), "host": url})

    def _post_search_test(self, body):
        """Search once through a SearXNG address, before it is saved."""
        url = settings.clean_url(body.get("url"))
        if not url:
            return self._json({"ok": False, "error": "bad_address"})
        try:
            results = websearch.searxng("Aetheris", url)
        except Exception as error:
            return self._json({"ok": False, "error": "search", "detail": str(error)[:400]})
        return self._json({"ok": True, "count": len(results), "url": url})

    def _post_ollama_start(self, body):
        return self._json({"ok": ollama_setup.start()})

    def _post_ollama_install(self, body):
        return self._json({"ok": self.app.run_job(ollama_setup.install)})

    def _post_ollama_pull(self, body):
        model = (body.get("model") or "").strip()
        if not model:
            return self._json({"ok": False})
        if not ollama_setup.running() and not ollama_setup.start():
            return self._json({"ok": False, "error": "ollama_down"})
        return self._json({"ok": self.app.run_job(_pull_then_use, model)})

    def _post_job_cancel(self, body):
        self.app.job_stop.set()
        return self._json({"ok": True})

    def _post_send(self, body):
        text = (body.get("text") or "").strip()
        attachments = [p for p in body.get("attachments") or [] if isinstance(p, str)
                       and os.path.isfile(p)]
        if not text and not attachments:
            return self._json({"ok": False, "error": "empty"})
        if not settings.get("work_folder"):
            folder = paths.default_work_folder()
            os.makedirs(folder, exist_ok=True)
            settings.update({"work_folder": folder})
        try:
            conversation_id = self.app.agent.start(body.get("conversation") or "", text or "(see attached)",
                                                   attachments)
        except agent.Busy:
            return self._json({"ok": False, "error": "busy"})
        return self._json({"ok": True, "conversation": conversation_id})

    def _post_stop(self, body):
        self.app.agent.stop()
        return self._json({"ok": True})

    def _post_approve(self, body):
        return self._json({"ok": self.app.agent.answer(body.get("id", ""), body.get("answer", ""))})

    def _post_conversation_new(self, body):
        folder = body.get("folder") or settings.get("work_folder") or paths.default_work_folder()
        conversation = conversations.new(folder)
        return self._json({"ok": True, "conversation": conversation})

    def _post_conversation_rename(self, body):
        title = str(body.get("title") or "").strip()[:120]
        running = self.app.agent.current
        if running is not None and running.get("id") == body.get("id"):
            running["title"] = title          # the turn saves its copy last; it must carry this
        conversations.rename(body.get("id", ""), title)
        return self._json({"ok": True, "conversations": conversations.list_all()})

    def _post_conversation_delete(self, body):
        if body.get("id") == self.app.agent.busy:
            return self._json({"ok": False, "error": "busy"})
        conversation = conversations.load(body.get("id", ""))
        conversations.delete(body.get("id", ""))
        self.app.agent.forget(body.get("id", ""))
        if conversation:
            remove_attachments(attachment_folders(conversation)
                               - attachment_folders(*_all_conversations()))
        return self._json({"ok": True, "conversations": conversations.list_all()})

    def _post_conversation_export(self, body):
        """Save the chat as a Markdown file in its work folder, for keeping or sharing."""
        conversation = conversations.load(body.get("id", ""))
        if not conversation:
            return self._json({"ok": False, "error": "other"}, 404)
        folder = conversation.get("folder") or settings.get("work_folder") or \
            paths.default_work_folder()
        os.makedirs(folder, exist_ok=True)
        target = conversations.export_name(conversation, folder)
        text = conversations.to_markdown(conversation, "ko" if body.get("language") == "ko" else "en")
        with open(target, "x", encoding="utf-8", newline="\n") as f:
            f.write(text)
        return self._json({"ok": True, "path": target})

    def _post_conversation_folder(self, body):
        conversation = conversations.load(body.get("id", ""))
        folder = os.path.abspath(os.path.expanduser(str(body.get("folder") or "")))
        if not body.get("folder"):
            return self._json({"ok": False})
        if conversation and conversation["id"] == self.app.agent.busy:
            return self._json({"ok": False, "error": "busy"})   # the turn works in the old one
        os.makedirs(folder, exist_ok=True)
        # Only this conversation moves; the default for new conversations stays as it is.
        if conversation:
            conversation["folder"] = folder
            conversations.save(conversation)
        return self._json({"ok": True, "folder": folder})

    def _post_undo(self, body):
        conversation_id, change_id = body.get("conversation", ""), body.get("change", "")
        if self.app.agent.busy == conversation_id:
            return self._json({"ok": False, "error": "busy"})
        result = history.undo(conversation_id, change_id, force=bool(body.get("force")))
        if result["ok"] or result["errors"]:
            conversation = conversations.load(conversation_id)
            if conversation:
                for item in conversation["ui"]:
                    if item.get("kind") == "changes" and item.get("change_id") == change_id:
                        item["undone"] = True
                conversation["messages"].append({"role": "user", "content": (
                    "[System] The user pressed Undo: every file change from one of your earlier "
                    "replies was reverted. Files are back to how they were before it.")})
                conversations.save(conversation)
        return self._json(result)

    def _post_memory_delete(self, body):
        memory.remove(str(body.get("id") or ""))
        return self._json({"ok": True, "memories": memory.load()})

    def _post_memory_clear(self, body):
        memory.clear()
        return self._json({"ok": True, "memories": []})

    def _post_pick_folder(self, body):
        return self._json({"path": system.pick_folder(body.get("initial") or "")})

    def _post_pick_files(self, body):
        return self._json({"paths": system.pick_files(body.get("initial") or "")})

    def _post_open(self, body):
        if body.get("url"):
            return self._json({"ok": system.open_url(body["url"])})
        return self._json({"ok": system.open_path(body.get("path", ""))})

    def _post_reveal(self, body):
        return self._json({"ok": system.reveal(body.get("path", ""))})

    def _post_shortcut(self, body):
        return self._json({"ok": system.make_shortcut()})

    def _post_reset(self, body):
        """Settings back to the start (keys and conversations are kept)."""
        settings.update({"setup_done": False})
        self.app.bus.publish({"type": "settings_changed"})
        return self._json({"ok": True})


def serve(app: App, port: int = 0) -> ThreadingHTTPServer:
    Handler.app = app
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    app.port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def recover_changes() -> int:
    """Give back the Undo card of a turn the app was closed in the middle of.

    The change set is saved after every operation, but its card is added to the
    conversation only when the turn ends; a turn cut short by closing the app
    (or a crash) left changes on disk that nothing in the window could undo.
    Run at start, before any turn. Returns how many cards were restored.
    """
    restored = 0
    for item in conversations.list_all():
        conversation = conversations.load(item.get("id", ""))
        if not conversation:
            continue
        shown = {i.get("change_id") for i in conversation["ui"] if i.get("kind") == "changes"}
        missing = [m for m in history.recorded(conversation["id"])
                   if m.get("id") not in shown]
        for manifest in missing:
            conversation["ui"].append({"kind": "changes", "change_id": manifest["id"],
                                       "files": history.describe(manifest["ops"]),
                                       "undone": bool(manifest.get("undone"))})
            restored += 1
        if missing:
            conversations.save(conversation)
    return restored


def _attachments_root() -> str:
    return os.path.realpath(os.path.join(paths.data_dir(), "attachments"))


def _all_conversations() -> list:
    found = []
    for item in conversations.list_all():
        conversation = conversations.load(item.get("id", ""))
        if conversation:
            found.append(conversation)
    return found


def attachment_folders(*conversation_list) -> set:
    """The upload folders (attachments/<day>/<id>) that conversations still show or use."""
    root = _attachments_root()
    folders = set()
    for conversation in conversation_list:
        files = [a.get("path", "") for item in conversation.get("ui", [])
                 for a in item.get("attachments") or [] if isinstance(a, dict)]
        files += [p for m in conversation.get("messages", []) for p in m.get("images") or []]
        for path in files:
            folder = os.path.dirname(os.path.realpath(str(path)))
            if os.path.dirname(os.path.dirname(folder)) == root:
                folders.add(folder)
    return folders


def remove_attachments(folders) -> None:
    root = _attachments_root()
    for folder in folders:
        if os.path.dirname(os.path.dirname(folder)) != root:
            continue
        shutil.rmtree(folder, ignore_errors=True)
        try:
            os.rmdir(os.path.dirname(folder))          # the day folder, once it is empty
        except OSError:
            pass


def clean_attachments(days: int = 30) -> None:
    """Remove old uploads that no saved conversation refers to any more.

    Attachments of a kept conversation stay as long as the conversation does, so
    reopening it never shows broken pictures; they go when it is deleted.
    """
    root = _attachments_root()
    if not os.path.isdir(root):
        return
    keep = attachment_folders(*_all_conversations())
    cutoff = time.time() - days * 86400
    for day in os.listdir(root):
        day_folder = os.path.join(root, day)
        if not os.path.isdir(day_folder):
            continue
        for name in os.listdir(day_folder):
            full = os.path.join(day_folder, name)
            try:
                if full not in keep and os.path.getmtime(full) < cutoff:
                    shutil.rmtree(full, ignore_errors=True)
            except OSError:
                pass
        try:
            os.rmdir(day_folder)
        except OSError:
            pass
