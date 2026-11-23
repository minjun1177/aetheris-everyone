"""The window's strings: both languages complete, and every key the code asks for exists."""

import os
import re
import unittest

WEB = os.path.join(os.path.dirname(__file__), "..", "aetheris_everyone", "web")


def _read(name: str) -> str:
    with open(os.path.join(WEB, name), encoding="utf-8") as f:
        return f.read()


def _keys(block: str) -> set:
    return set(re.findall(r'^\s*"([\w.]+)":', block, re.MULTILINE))


class Strings(unittest.TestCase):
    def setUp(self):
        source = _read("i18n.js")
        ko_start, en_start = source.index("  ko: {"), source.index("  en: {")
        self.ko = _keys(source[ko_start:en_start])
        self.en = _keys(source[en_start:])

    def test_both_languages_have_the_same_keys(self):
        self.assertEqual(sorted(self.ko - self.en), [], "missing in English")
        self.assertEqual(sorted(self.en - self.ko), [], "missing in Korean")

    def test_every_literal_key_used_exists(self):
        used = set()
        for name in ("app.js", "markdown.js"):
            used |= set(re.findall(r'\bt\(\s*"([\w.]+)"\s*[,)]', _read(name)))
        self.assertEqual(sorted(used - self.en), [])

    def test_every_server_error_code_has_a_sentence(self):
        server = _read(os.path.join("..", "server.py"))
        codes = set(re.findall(r'"error":\s*"(\w+)"', server)) - {"unknown", "unauthorised", "not_found"}
        self.assertEqual(sorted(c for c in codes if f"err.{c}" not in self.en), [])


class Vendored(unittest.TestCase):
    def test_katex_is_shipped_and_loaded(self):
        for name in ("vendor/katex/katex.min.js", "vendor/katex/katex.min.css",
                     "vendor/katex/fonts/KaTeX_Main-Regular.woff2", "vendor/katex/LICENSE"):
            self.assertTrue(os.path.isfile(os.path.join(WEB, name)), name)
        page = _read("index.html")
        self.assertLess(page.index("vendor/katex/katex.min.js"), page.index("markdown.js"))


if __name__ == "__main__":
    unittest.main()
