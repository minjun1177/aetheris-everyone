import json
import urllib.error
import urllib.request

from aetheris_everyone import server
from helpers import Sandbox


class ServerSecurity(Sandbox):
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
