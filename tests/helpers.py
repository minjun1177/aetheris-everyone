"""A throwaway data folder and work folder for every test."""

import os
import shutil
import tempfile
import threading
import unittest


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="aetheris-test-")
        self.home = os.path.join(self.root, "home")
        self.work = os.path.join(self.root, "work")
        os.makedirs(self.work)
        self._old_env = {name: os.environ.get(name)
                         for name in ("AETHERIS_EVERYONE_HOME", "AETHERIS_EVERYONE_KEYRING")}
        os.environ["AETHERIS_EVERYONE_HOME"] = self.home
        os.environ["AETHERIS_EVERYONE_KEYRING"] = "off"     # never the developer's real keychain
        from aetheris_everyone import settings
        settings.reset_cache()

    def tearDown(self):
        for name, value in self._old_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        from aetheris_everyone import settings
        settings.reset_cache()
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, name: str, text: str) -> str:
        path = os.path.join(self.work, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def read(self, name: str) -> str:
        with open(os.path.join(self.work, name), encoding="utf-8") as f:
            return f.read()

    def context(self, safety="balanced", answer="allow", commands=False):
        from aetheris_everyone import history, tools
        self.asked = []

        def ask(request):
            self.asked.append(request)
            return answer

        self.changes = history.ChangeSet("test-conversation")
        return tools.Context(self.work, self.changes, ask, safety, set(), threading.Event(),
                             allow_commands=commands)
