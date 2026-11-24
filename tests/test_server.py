import json
import os
import urllib.error
import urllib.parse
import urllib.request

from aetheris_everyone import server
from helpers import Sandbox


class ServerCase(Sandbox):
    def setUp(self):
        super().setUp()
        self.app = server.App()
        self.httpd = server.serve(self.app)
        self.base = f"http://127.0.0.1:{self.app.port}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        super().tearDown()

    def call(self, path, body=None, token=True, host=None):
        request = urllib.request.Request(self.base + path,
                                         data=json.dumps(body).encode() if body is not None else None)
        if token:
            request.add_header("X-Token", self.app.token)
        if host:
            request.add_header("Host", host)
        if body is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()


class ServerSecurity(ServerCase):
    def test_token_required(self):
        self.assertEqual(self.call("/api/state", token=False)[0], 401)
        status, body = self.call("/api/state")
        self.assertEqual(status, 200)
        self.assertIn("settings", json.loads(body))

    def test_foreign_host_refused(self):
        self.assertEqual(self.call("/api/state", host="evil.example")[0], 403)

    def test_page_served_with_csp(self):
        with urllib.request.urlopen(self.base + "/") as response:
            self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
            self.assertIn(b"Aetheris Everyone", response.read())

    def test_static_cannot_escape(self):
        self.assertEqual(self.call("/../settings.py", token=False)[0], 404)

    def test_keys_are_never_returned(self):
        self.call("/api/settings", {"language": "en"})
        from aetheris_everyone import settings
        settings.set_api_key("openai", "sk-secret")
        status, body = self.call("/api/state")
        self.assertNotIn(b"sk-secret", body)
        self.assertTrue(json.loads(body)["keys"]["openai"])


class ServerBehaviour(ServerCase):
    def post(self, route, body):
        status, raw = self.call("/api/" + route, body)
        return status, json.loads(raw)

    def test_conversation_folder_is_not_the_default(self):
        import os
        from aetheris_everyone import conversations, settings
        settings.update({"work_folder": self.work})
        conversation = conversations.new(self.work)
        conversation["ui"].append({"kind": "user", "text": "hi"})
        conversations.save(conversation)
        other = os.path.join(self.root, "other")
        status, body = self.post("conversation/folder", {"id": conversation["id"], "folder": other})
        self.assertTrue(body["ok"])
        self.assertEqual(conversations.load(conversation["id"])["folder"], other)
        self.assertEqual(settings.get("work_folder"), self.work)

    def test_attachments_live_as_long_as_their_conversation(self):
        import os
        import time
        from aetheris_everyone import conversations, paths
        old = time.time() - 40 * 86400

        def upload(name):
            folder = paths.sub("attachments", "20200101", name)
            path = os.path.join(folder, "pic.png")
            with open(path, "wb") as f:
                f.write(b"png")
            os.utime(folder, (old, old))
            return path

        kept, orphan, gone = upload("kept"), upload("orphan"), upload("gone")
        for path in (kept, gone):
            conversation = conversations.new(self.work)
            conversation["ui"].append({"kind": "user", "text": "",
                                       "attachments": [{"name": "pic.png", "path": path, "image": True}]})
            conversations.save(conversation)
            if path == gone:
                doomed = conversation["id"]
        server.clean_attachments(days=30)
        self.assertTrue(os.path.exists(kept))              # an old picture a saved chat still shows
        self.assertTrue(os.path.exists(gone))
        self.assertFalse(os.path.exists(orphan))           # old and referred to by nothing
        self.app.agent._granted[doomed] = {"run"}
        status, body = self.post("conversation/delete", {"id": doomed})
        self.assertTrue(body["ok"])
        self.assertFalse(os.path.exists(gone))             # deleted with its conversation
        self.assertTrue(os.path.exists(kept))
        self.assertNotIn(doomed, self.app.agent._granted)

    def test_address_checks(self):
        status, body = self.post("ollama/test", {"host": "javascript:alert(1)"})
        self.assertEqual(body, {"ok": False, "error": "bad_address"})
        status, body = self.post("ollama/test", {"host": "http://127.0.0.1:9"})
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"], "ollama_down")
        status, body = self.post("search/test", {"url": ""})
        self.assertEqual(body["error"], "bad_address")

    def test_state_reports_key_storage_not_keys(self):
        from aetheris_everyone import settings
        settings.set_api_key("anthropic", "sk-ant-secret")
        status, raw = self.call("/api/state")
        self.assertNotIn(b"sk-ant-secret", raw)
        self.assertEqual(json.loads(raw)["key_storage"], "file")
        status, body = self.post("provider/forget", {"provider": "anthropic"})
        self.assertFalse(body["keys"]["anthropic"])

    def test_katex_assets_are_served(self):
        with urllib.request.urlopen(self.base + "/vendor/katex/fonts/KaTeX_Main-Regular.woff2") as response:
            self.assertEqual(response.headers["Content-Type"], "font/woff2")
            self.assertGreater(len(response.read()), 1000)

    def test_static_types_do_not_depend_on_the_system(self):
        # Windows takes these from the registry; a script typed text/plain is blocked (nosniff).
        expected = {"/app.js": "application/javascript; charset=utf-8",
                    "/style.css": "text/css; charset=utf-8",
                    "/vendor/katex/katex.min.js": "application/javascript; charset=utf-8",
                    "/icon.svg": "image/svg+xml; charset=utf-8"}
        for path, kind in expected.items():
            with urllib.request.urlopen(self.base + path) as response:
                self.assertEqual(response.headers["Content-Type"], kind, path)


class InterruptedTurn(ServerCase):
    def test_a_change_set_without_its_card_gets_one_at_start(self):
        from aetheris_everyone import conversations, history
        conversation = conversations.new(self.work)
        conversations.save(conversation)
        changes = history.ChangeSet(conversation["id"])     # what a turn cut short leaves behind
        path = f"{self.work}/made.txt"
        changes.before_write(path)
        with open(path, "w") as f:
            f.write("x")
        changes.after_write(path)
        self.assertEqual(server.recover_changes(), 1)
        cards = [i for i in conversations.load(conversation["id"])["ui"] if i["kind"] == "changes"]
        self.assertEqual([c["change_id"] for c in cards], [changes.id])
        self.assertEqual(cards[0]["files"], [{"kind": "created", "path": path}])
        self.assertEqual(server.recover_changes(), 0)        # never added twice
        status, raw = self.call("/api/undo", {"conversation": conversation["id"], "change": changes.id})
        self.assertTrue(json.loads(raw)["ok"])
        self.assertFalse(os.path.exists(path))


class EditsDuringATurn(ServerCase):
    def test_rename_reaches_the_running_turn_and_folder_change_is_refused(self):
        from aetheris_everyone import conversations
        conversation = conversations.new(self.work)
        conversations.save(conversation)
        self.app.agent.busy = conversation["id"]       # a turn holding its own copy
        self.app.agent.current = conversation
        try:
            self.call("/api/conversation/rename", {"id": conversation["id"], "title": "Budget"})
            self.assertEqual(conversation["title"], "Budget")
            status, raw = self.call("/api/conversation/folder",
                                    {"id": conversation["id"], "folder": self.root})
            self.assertEqual(json.loads(raw), {"ok": False, "error": "busy"})
        finally:
            self.app.agent.busy = None
            self.app.agent.current = None
        conversations.save(conversation)               # what the turn does when it ends
        self.assertEqual(conversations.load(conversation["id"])["title"], "Budget")
        self.assertEqual(conversations.load(conversation["id"])["folder"], self.work)


class LargePhotos(ServerCase):
    def upload(self, body, **headers):
        request = urllib.request.Request(self.base + "/api/upload", data=body, method="POST")
        request.add_header("X-Token", self.app.token)
        for key, value in headers.items():
            request.add_header(key, value)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            return json.loads(error.read())

    def test_the_reduced_copy_is_what_the_model_sees(self):
        from aetheris_everyone import providers
        original = self.upload(b"x" * (providers.MAX_IMAGE_BYTES + 1), **{"X-Filename": "big.jpg"})
        self.assertTrue(original["ok"])
        self.assertEqual(providers.image_source(original["path"]), "")       # too big as it is
        small = self.upload(b"small-jpeg", **{"X-Small-For": urllib.parse.quote(original["path"])})
        self.assertTrue(small["ok"])
        self.assertEqual(providers.image_source(original["path"]),
                         original["path"] + providers.SMALL_SUFFIX)
        with open(original["path"], "rb") as f:
            self.assertEqual(len(f.read()), providers.MAX_IMAGE_BYTES + 1)  # the original stays

    def test_a_reduced_copy_goes_only_beside_an_uploaded_picture(self):
        outside = os.path.join(self.work, "mine.jpg")
        with open(outside, "wb") as f:
            f.write(b"jpg")
        result = self.upload(b"evil", **{"X-Small-For": urllib.parse.quote(outside)})
        self.assertFalse(result["ok"])
        self.assertFalse(os.path.exists(outside + ".small.jpg"))


class CutOffUpload(ServerCase):
    def test_an_upload_that_stops_early_is_not_kept(self):
        import socket
        from aetheris_everyone import paths
        with socket.create_connection(("127.0.0.1", self.app.port), timeout=5) as sock:
            sock.sendall((f"POST /api/upload HTTP/1.1\r\nHost: 127.0.0.1:{self.app.port}\r\n"
                          f"X-Token: {self.app.token}\r\nX-Filename: report.pdf\r\n"
                          "Content-Length: 1000\r\n\r\n").encode() + b"only part")
            sock.shutdown(socket.SHUT_WR)               # the window went away mid-upload
            answer = b""
            while True:
                data = sock.recv(4096)
                if not data:
                    break
                answer += data
        self.assertIn(b'"incomplete"', answer)
        kept = [name for _, _, files in os.walk(paths.sub("attachments")) for name in files]
        self.assertEqual(kept, [])


class SavingAChat(ServerCase):
    def test_a_chat_is_saved_as_markdown_in_its_folder_without_replacing_anything(self):
        from aetheris_everyone import conversations
        conversation = conversations.new(self.work)
        conversation["title"] = 'Budget: May/June?'
        conversation["ui"] += [
            {"kind": "user", "text": "Make a budget", "attachments": [{"name": "receipts.pdf"}]},
            {"kind": "tool", "name": "write_file", "args": {"path": "budget.xlsx"}, "status": "ok"},
            {"kind": "assistant", "text": "I made **budget.xlsx**."},
            {"kind": "changes", "change_id": "c1", "undone": False,
             "files": [{"kind": "created", "path": f"{self.work}/budget.xlsx"}]}]
        conversations.save(conversation)
        paths = []
        for _ in range(2):
            status, raw = self.call("/api/conversation/export", {"id": conversation["id"], "language": "en"})
            body = json.loads(raw)
            self.assertTrue(body["ok"], body)
            paths.append(body["path"])
        self.assertNotEqual(paths[0], paths[1])                       # the second does not replace the first
        for path in paths:
            self.assertEqual(os.path.dirname(path), self.work)
            self.assertNotIn(":", os.path.basename(path).split(" (")[0])
        with open(paths[0], encoding="utf-8") as f:
            text = f.read()
        for expected in ("# Budget: May/June?", "## You", "Make a budget", "receipts.pdf",
                         "`write_file` budget.xlsx (ok)", "## Aetheris", "I made **budget.xlsx**.",
                         "**Files changed:**", "- created: "):
            self.assertIn(expected, text)


class TakingBack(ServerCase):
    def test_the_last_request_is_taken_back_and_its_undo_card_kept(self):
        from aetheris_everyone import conversations
        conversation = conversations.new(self.work)
        conversation["ui"] = [
            {"kind": "user", "text": "first"}, {"kind": "assistant", "text": "ok"},
            {"kind": "user", "text": "make a.txt", "quote": "that part"},
            {"kind": "tool", "name": "write_file", "status": "ok"},
            {"kind": "changes", "change_id": "c1", "undone": False,
             "files": [{"kind": "created", "path": "/w/a.txt"}]},
            {"kind": "assistant", "text": "made it"}]
        conversation["messages"] = [
            {"role": "user", "content": "first"}, {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "About this part...\n\nmake a.txt"},
            {"role": "assistant", "content": "<tool_call>..."},
            {"role": "user", "content": "[Tool Result for 'write_file']:\nCreated a.txt."},
            {"role": "assistant", "content": "made it"}]
        conversations.save(conversation)
        status, raw = self.call("/api/conversation/rewind", {"id": conversation["id"]})
        body = json.loads(raw)
        self.assertEqual((body["ok"], body["text"], body["quote"]), (True, "make a.txt", "that part"))
        saved = conversations.load(conversation["id"])
        self.assertEqual([i["kind"] for i in saved["ui"]], ["user", "assistant", "changes"])
        self.assertEqual([m["content"][:5] for m in saved["messages"]], ["first", "ok", "[Syst"])
        self.assertIn("/w/a.txt", saved["messages"][-1]["content"])
        self.app.agent.busy = conversation["id"]
        try:
            status, raw = self.call("/api/conversation/rewind", {"id": conversation["id"]})
            self.assertEqual(json.loads(raw)["error"], "busy")
        finally:
            self.app.agent.busy = None


class UndoStorage(ServerCase):
    def test_old_undo_copies_are_cleared_and_their_cards_say_so(self):
        import time
        from aetheris_everyone import conversations, history, settings
        conversation = conversations.new(self.work)
        conversations.save(conversation)
        sets = []
        for name in ("old.txt", "new.txt"):
            path = os.path.join(self.work, name)
            with open(path, "w") as f:
                f.write("x")
            changes = history.ChangeSet(conversation["id"])
            changes.delete(path)                       # kept aside for undo
            sets.append(changes)
            conversation["ui"].append({"kind": "changes", "change_id": changes.id, "files": changes.files()})
        conversations.save(conversation)
        manifest = os.path.join(sets[0].dir, "manifest.json")
        data = json.load(open(manifest))
        data["time"] = time.time() - 100 * 86400
        with open(manifest, "w") as f:
            json.dump(data, f)
        self.assertEqual(history.storage()["sets"], 2)
        settings.update({"history_days": 90})
        server.prune_history()
        self.assertFalse(os.path.exists(sets[0].dir))
        self.assertTrue(os.path.exists(sets[1].dir))
        cards = conversations.load(conversation["id"])["ui"]
        self.assertEqual([c.get("expired", False) for c in cards], [True, False])
        status, raw = self.call("/api/storage/prune", {"all": True})
        self.assertEqual(json.loads(raw)["removed"], 1)
        self.assertEqual(history.storage(), {"bytes": 0, "sets": 0})
        status, raw = self.call("/api/storage")
        self.assertEqual(json.loads(raw)["days"], 90)

    def test_never_clearing_keeps_everything(self):
        from aetheris_everyone import settings
        settings.update({"history_days": 0})
        status, raw = self.call("/api/storage/prune", {})
        self.assertEqual(json.loads(raw)["removed"], 0)
        settings.update({"history_days": "x"})
        self.assertEqual(settings.get("history_days"), 0)
