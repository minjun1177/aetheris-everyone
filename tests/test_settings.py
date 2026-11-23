"""Settings validation and where API keys are kept."""

import hashlib
import io
import json
import os
import threading
import unittest

from aetheris_everyone import ollama_setup, paths, settings
from helpers import Sandbox


class MemoryKeyring:
    """Stands in for the system password store."""

    def __init__(self):
        self.items = {}

    def get_password(self, service, name):
        return self.items.get((service, name))

    def set_password(self, service, name, value):
        self.items[(service, name)] = value

    def delete_password(self, service, name):
        if (service, name) not in self.items:
            raise KeyError(name)
        del self.items[(service, name)]


class Keys(Sandbox):
    def secrets_file(self):
        return os.path.join(paths.data_dir(), "secrets.json")

    def test_keys_go_to_the_keychain_not_a_file(self):
        backend = MemoryKeyring()
        settings.use_store(settings.KeyringStore(backend))
        settings.set_api_key("openai", "  sk-1  ")
        self.assertEqual(backend.items[(settings.KEYRING_SERVICE, "openai")], "sk-1")
        self.assertEqual(settings.api_key("openai"), "sk-1")
        self.assertFalse(os.path.exists(self.secrets_file()))
        self.assertEqual(settings.key_storage(), "keychain")
        settings.set_api_key("openai", "")
        self.assertEqual(settings.api_key("openai"), "")
        settings.set_api_key("openai", "")                    # removing twice is fine

    def test_old_key_file_moves_into_the_keychain(self):
        paths.write_json(self.secrets_file(), {"gemini": "g-key", "anthropic": "a-key"}, private=True)
        backend = MemoryKeyring()
        settings.use_store(settings.KeyringStore(backend))
        self.assertEqual(settings.api_key("gemini"), "g-key")
        self.assertEqual(settings.api_key("anthropic"), "a-key")
        self.assertFalse(os.path.exists(self.secrets_file()))

    def test_failed_move_keeps_the_file(self):
        paths.write_json(self.secrets_file(), {"gemini": "g-key"}, private=True)

        class Broken(MemoryKeyring):
            def set_password(self, *args):
                raise RuntimeError("locked")

        settings.use_store(settings.KeyringStore(Broken()))
        self.assertTrue(os.path.exists(self.secrets_file()))
        self.assertEqual(paths.read_json(self.secrets_file()), {"gemini": "g-key"})

    def test_file_fallback_when_no_keychain(self):
        self.assertEqual(settings.key_storage(), "file")     # tests turn the keychain off
        settings.set_api_key("anthropic", "a-key")
        self.assertEqual(paths.read_json(self.secrets_file()), {"anthropic": "a-key"})
        if os.name != "nt":
            self.assertEqual(os.stat(self.secrets_file()).st_mode & 0o777, 0o600)

    def test_environment_key_is_used_when_none_is_saved(self):
        os.environ["GEMINI_API_KEY"] = "from-env"
        try:
            self.assertEqual(settings.api_key("gemini"), "from-env")
        finally:
            os.environ.pop("GEMINI_API_KEY")

    def test_unknown_provider_is_ignored(self):
        settings.set_api_key("../../evil", "x")
        self.assertIsNone(paths.read_json(self.secrets_file()))


class Validation(Sandbox):
    def test_new_settings_defaults_and_checks(self):
        current = settings.load()
        self.assertFalse(current["allow_commands"])
        self.assertEqual(current["search_engine"], "auto")
        settings.update({"allow_commands": "yes", "search_engine": "google",
                         "searxng_url": "javascript:alert(1)"})
        current = settings.load()
        self.assertFalse(current["allow_commands"])         # only a real true turns it on
        self.assertEqual(current["search_engine"], "auto")
        self.assertEqual(current["searxng_url"], "")
        settings.update({"allow_commands": True, "search_engine": "searxng",
                         "searxng_url": "192.168.0.10:8080/"})
        current = settings.load()
        self.assertTrue(current["allow_commands"])
        self.assertEqual(current["searxng_url"], "http://192.168.0.10:8080")

    def test_clean_url(self):
        self.assertEqual(settings.clean_url(" https://a.example/x/ "), "https://a.example/x")
        self.assertEqual(settings.clean_url(""), "")
        self.assertIsNone(settings.clean_url("ftp://a"))
        self.assertIsNone(settings.clean_url("http://"))


class InstallerCheck(Sandbox):
    def setUp(self):
        super().setUp()
        self.real_get, self.real_urlopen = ollama_setup._get, ollama_setup.urllib.request.urlopen

    def tearDown(self):
        ollama_setup._get, ollama_setup.urllib.request.urlopen = self.real_get, self.real_urlopen
        super().tearDown()

    def serve(self, release: dict, sums: str = "", payload: bytes = b""):
        def get(url, timeout=20):
            if url == ollama_setup._LATEST_API:
                return json.dumps(release).encode()
            if url.endswith("sha256sum.txt"):
                return sums.encode()
            raise OSError("unexpected " + url)

        class Response(io.BytesIO):
            headers = {"Content-Length": str(len(payload))}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.close()

        ollama_setup._get = get
        ollama_setup.urllib.request.urlopen = lambda *a, **k: Response(payload)

    def test_asset_hash_from_the_release_record(self):
        sha = hashlib.sha256(b"installer").hexdigest()
        self.serve({"tag_name": "v1.2.3", "assets": [{"name": "OllamaSetup.exe", "size": 9,
                                                      "digest": "sha256:" + sha}]})
        asset = ollama_setup.release_asset("OllamaSetup.exe")
        self.assertEqual(asset, {"url": "https://github.com/ollama/ollama/releases/download/v1.2.3/OllamaSetup.exe",
                                 "sha256": sha, "size": 9})

    def test_hash_from_sha256sum_when_the_record_has_none(self):
        sha = "a" * 64
        self.serve({"tag_name": "v1", "assets": [{"name": "install.sh", "size": 3}]},
                   sums=f"{'b' * 64}  ./other\n{sha}  ./install.sh\n")
        self.assertEqual(ollama_setup.release_asset("install.sh")["sha256"], sha)

    def test_no_hash_means_no_install(self):
        self.serve({"tag_name": "v1", "assets": [{"name": "install.sh", "size": 3}]})
        with self.assertRaises(ollama_setup.Unverified):
            ollama_setup.release_asset("install.sh")

    def test_tampered_download_is_refused_and_removed(self):
        good = b"the real installer"
        self.serve({"tag_name": "v1", "assets": []}, payload=b"something else entirely!")
        target = os.path.join(self.root, "OllamaSetup.exe")
        with self.assertRaises(ollama_setup.Unverified):
            ollama_setup._download("https://x/OllamaSetup.exe", target, lambda e: None, threading.Event(),
                                   {"sha256": hashlib.sha256(good).hexdigest(), "size": len(good)})
        self.assertFalse(os.path.exists(target))

    def test_matching_download_is_kept(self):
        good = b"the real installer"
        self.serve({"tag_name": "v1", "assets": []}, payload=good)
        target = os.path.join(self.root, "OllamaSetup.exe")
        self.assertTrue(ollama_setup._download("https://x/OllamaSetup.exe", target, lambda e: None,
                                               threading.Event(),
                                               {"sha256": hashlib.sha256(good).hexdigest(), "size": len(good)}))
        with open(target, "rb") as f:
            self.assertEqual(f.read(), good)

    def test_unverifiable_install_points_to_the_download_page(self):
        events = []
        self.serve({"tag_name": "v1", "assets": []})
        real_platform, real_which = ollama_setup.sys.platform, ollama_setup.shutil.which
        ollama_setup.sys.platform = "win32"
        try:
            ollama_setup.install(events.append, threading.Event())
        finally:
            ollama_setup.sys.platform = real_platform
        self.assertEqual(events[-1]["stage"], "manual")
        self.assertIn("not verified", events[-1]["detail"])
        self.assertIs(ollama_setup.shutil.which, real_which)


if __name__ == "__main__":
    unittest.main()
