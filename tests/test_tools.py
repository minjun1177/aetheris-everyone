import os
import unittest

from aetheris_everyone import documents, history, paths, tools
from helpers import Sandbox


class FileTools(Sandbox):
    def test_write_read_edit(self):
        ctx = self.context()
        status, result, _ = tools.dispatch(ctx, "write_file", {"path": "notes/a.txt", "content": "one\ntwo\n"})
        self.assertEqual(status, "ok", result)
        status, result, _ = tools.dispatch(ctx, "edit_file", {"path": "notes/a.txt", "old_text": "two",
                                                              "new_text": "three"})
        self.assertEqual(status, "ok", result)
        self.assertEqual(self.read("notes/a.txt"), "one\nthree\n")
        status, result, _ = tools.dispatch(ctx, "read_file", {"path": "notes/a.txt"})
        self.assertIn("three", result)

    def test_append(self):
        self.write("list.txt", "apple")
        ctx = self.context()
        status, result, _ = tools.dispatch(ctx, "write_file", {"path": "list.txt", "content": "milk",
                                                               "append": True})
        self.assertEqual(status, "ok", result)
        self.assertEqual(self.read("list.txt"), "apple\nmilk")

    def test_edit_miss_shows_the_file(self):
        self.write("a.txt", "hello")
        status, result, _ = tools.dispatch(self.context(), "edit_file",
                                           {"path": "a.txt", "old_text": "bye", "new_text": "x"})
        self.assertEqual(status, "error")
        self.assertIn("hello", result)

    def test_aliases_from_small_models(self):
        self.write("a.txt", "x")
        status, result, name = tools.dispatch(self.context(), "cat", {"filepath": "a.txt"})
        self.assertEqual((status, name), ("ok", "read_file"))

    def test_korean_legacy_encoding_is_read_and_kept(self):
        path = os.path.join(self.work, "old.txt")
        with open(path, "wb") as f:
            f.write("안녕하세요".encode("cp949"))
        ctx = self.context()
        status, result, _ = tools.dispatch(ctx, "read_file", {"path": "old.txt"})
        self.assertIn("안녕하세요", result)
        tools.dispatch(ctx, "edit_file", {"path": "old.txt", "old_text": "안녕", "new_text": "반갑"})
        with open(path, "rb") as f:
            self.assertEqual(f.read().decode("cp949"), "반갑하세요")

    def test_private_data_is_off_limits(self):
        paths.write_json(os.path.join(paths.data_dir(), "secrets.json"), {"openai": "sk-x"})
        status, result, _ = tools.dispatch(self.context(safety="auto"), "read_file",
                                           {"path": os.path.join(paths.data_dir(), "secrets.json")})
        self.assertEqual(status, "denied")
        self.assertNotIn("sk-x", result)

    def test_outside_folder_asks(self):
        outside = os.path.join(self.root, "elsewhere.txt")
        with open(outside, "w") as f:
            f.write("secret")
        ctx = self.context(answer="deny")
        status, _, _ = tools.dispatch(ctx, "read_file", {"path": outside})
        self.assertEqual(status, "denied")
        self.assertTrue(self.asked and self.asked[0]["outside"])

    def test_safety_levels(self):
        ctx = self.context(safety="balanced")
        tools.dispatch(ctx, "write_file", {"path": "a.txt", "content": "x"})
        self.assertEqual(self.asked, [])                  # inside the folder: undoable, not asked
        ctx = self.context(safety="ask", answer="deny")
        status, _, _ = tools.dispatch(ctx, "write_file", {"path": "b.txt", "content": "x"})
        self.assertEqual(status, "denied")
        self.assertFalse(os.path.exists(os.path.join(self.work, "b.txt")))

    def test_always_allow_is_remembered(self):
        ctx = self.context(safety="ask", answer="always")
        tools.dispatch(ctx, "write_file", {"path": "a.txt", "content": "x"})
        tools.dispatch(ctx, "write_file", {"path": "b.txt", "content": "y"})
        self.assertEqual(len(self.asked), 1)

    def test_command_is_asked_and_runs_in_folder(self):
        ctx = self.context(answer="allow")
        status, result, _ = tools.dispatch(ctx, "run_command", {"command": "echo hello",
                                                                "reason": "test"})
        self.assertEqual(status, "ok", result)
        self.assertIn("hello", result)
        self.assertEqual(self.asked[0]["category"], "run")

    def test_find_and_search(self):
        self.write("docs/plan.md", "budget 2026\n")
        self.write("docs/other.txt", "nothing\n")
        ctx = self.context()
        _, result, _ = tools.dispatch(ctx, "find_files", {"pattern": "*.md"})
        self.assertIn("docs/plan.md", result)
        _, result, _ = tools.dispatch(ctx, "search_text", {"text": "BUDGET"})
        self.assertIn("plan.md:1", result)


class Undo(Sandbox):
    def test_every_change_comes_back(self):
        self.write("keep.txt", "original")
        self.write("old.txt", "old")
        self.write("gone.txt", "bye")
        ctx = self.context()
        tools.dispatch(ctx, "write_file", {"path": "keep.txt", "content": "changed"})
        tools.dispatch(ctx, "write_file", {"path": "new/deep/file.txt", "content": "new"})
        tools.dispatch(ctx, "move", {"source": "old.txt", "destination": "archive/"})
        tools.dispatch(ctx, "delete", {"path": "gone.txt"})
        self.changes.save()
        self.assertTrue(os.path.exists(os.path.join(self.work, "archive", "old.txt")))
        result = history.undo("test-conversation", self.changes.id)
        self.assertTrue(result["ok"], result)
        self.assertEqual(self.read("keep.txt"), "original")
        self.assertEqual(self.read("old.txt"), "old")
        self.assertEqual(self.read("gone.txt"), "bye")
        self.assertFalse(os.path.exists(os.path.join(self.work, "new")))
        self.assertFalse(os.path.exists(os.path.join(self.work, "archive")))

    def test_later_edits_are_not_overwritten_silently(self):
        self.write("a.txt", "v1")
        ctx = self.context()
        tools.dispatch(ctx, "write_file", {"path": "a.txt", "content": "v2"})
        self.changes.save()
        self.write("a.txt", "v3 by the person")
        result = history.undo("test-conversation", self.changes.id)
        self.assertFalse(result["ok"])
        self.assertEqual(len(result["conflicts"]), 1)
        self.assertEqual(self.read("a.txt"), "v3 by the person")
        self.assertTrue(history.undo("test-conversation", self.changes.id, force=True)["ok"])
        self.assertEqual(self.read("a.txt"), "v1")


class Documents(Sandbox):
    def test_word_round_trip(self):
        ctx = self.context()
        status, result, _ = tools.dispatch(ctx, "write_file", {"path": "report.docx", "content":
                                           "# 주간 보고\n- 매출 **10%** 증가\n\n| 항목 | 값 |\n|---|---|\n| A | 1 |"})
        self.assertEqual(status, "ok", result)
        text = documents.extract(os.path.join(self.work, "report.docx"))
        self.assertIn("# 주간 보고", text)
        self.assertIn("매출 10% 증가", text)

    def test_excel_round_trip(self):
        ctx = self.context()
        status, result, _ = tools.dispatch(ctx, "write_file", {"path": "budget.xlsx", "content":
                                           "날짜,항목,금액\n2026-11-01,커피,4500\n2026-11-02,점심,\"12,000\""})
        self.assertEqual(status, "ok", result)
        text = documents.extract(os.path.join(self.work, "budget.xlsx"))
        self.assertIn("날짜,항목,금액", text)
        self.assertIn("커피,4500", text)
        self.assertIn("12000", text)

    def test_csv_gets_a_bom_for_excel(self):
        tools.dispatch(self.context(), "write_file", {"path": "t.csv", "content": "가,나\n1,2"})
        with open(os.path.join(self.work, "t.csv"), "rb") as f:
            self.assertTrue(f.read().startswith(b"\xef\xbb\xbf"))


if __name__ == "__main__":
    unittest.main()
