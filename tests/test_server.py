import json
import urllib.error
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
