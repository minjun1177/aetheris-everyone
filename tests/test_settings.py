"""Settings validation and where API keys are kept."""

import os
import unittest

from aetheris_everyone import paths, settings
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



if __name__ == "__main__":
    unittest.main()
