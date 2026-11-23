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
        self._old_home = os.environ.get("AETHERIS_EVERYONE_HOME")
        os.environ["AETHERIS_EVERYONE_HOME"] = self.home
        from aetheris_everyone import settings
        settings.reset_cache()

    def tearDown(self):
        if self._old_home is None:
            os.environ.pop("AETHERIS_EVERYONE_HOME", None)
        else:
            os.environ["AETHERIS_EVERYONE_HOME"] = self._old_home
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

    def context(self, safety="balanced", answer="allow"):
        from aetheris_everyone import history, tools
        self.asked = []

        def ask(request):
            self.asked.append(request)
            return answer

        self.changes = history.ChangeSet("test-conversation")
        return tools.Context(self.work, self.changes, ask, safety, set(), threading.Event())
