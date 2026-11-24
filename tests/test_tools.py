import os
import threading
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

    def test_edit_keeps_windows_line_endings_and_the_rest_of_the_file(self):
        path = os.path.join(self.work, "memo.txt")
        with open(path, "wb") as f:
            f.write(b"title  \r\none\r\ntwo\r\nend   \r\n")
        status, result, _ = tools.dispatch(self.context(), "edit_file", {
            "path": "memo.txt", "old_text": "one\ntwo", "new_text": "first\nsecond"})
        self.assertEqual(status, "ok", result)
        with open(path, "rb") as f:
            # only the edited lines change; the other lines keep CRLF and their spaces
            self.assertEqual(f.read(), b"title  \r\nfirst\r\nsecond\r\nend   \r\n")

    def test_edit_ignores_trailing_spaces_only_where_it_matches(self):
        self.write("a.txt", "keep   \nold line   \nnext\n")
        status, result, _ = tools.dispatch(self.context(), "edit_file", {
            "path": "a.txt", "old_text": "old line\nnext", "new_text": "new line\nnext"})
        self.assertEqual(status, "ok", result)
        self.assertEqual(self.read("a.txt"), "keep   \nnew line\nnext\n")

    def test_replace_all_given_as_text_false_stays_false(self):
        self.write("a.txt", "x x")
        status, result, _ = tools.dispatch(self.context(), "edit_file", {
            "path": "a.txt", "old_text": "x", "new_text": "y", "replace_all": "false"})
        self.assertEqual(status, "error")
        self.assertIn("2 times", result)

    def test_folders_holding_the_work_or_the_app_data_are_never_carried_off(self):
        nested = os.path.join(self.work, "project")
        os.makedirs(nested)
        ctx = tools.Context(nested, history.ChangeSet("c"), lambda r: "allow", "auto", set(),
                            threading.Event())
        for name, args in (("delete", {"path": self.work}),
                           ("move", {"source": self.work, "destination": os.path.join(self.root, "x")}),
                           ("delete", {"path": os.path.dirname(paths.data_dir())})):
            status, result, _ = tools.dispatch(ctx, name, args)
            self.assertEqual(status, "error", (name, result))
        self.assertTrue(os.path.isdir(nested))
        self.assertTrue(os.path.isdir(paths.data_dir()))

    def test_a_folder_is_not_copied_or_moved_into_itself(self):
        self.write("album/a.jpg", "x")
        ctx = self.context()
        for name in ("copy", "move"):
            status, result, _ = tools.dispatch(ctx, name, {"source": "album", "destination": "album/inner"})
            self.assertEqual(status, "error", result)
            self.assertIn("into itself", result)
        self.assertEqual(os.listdir(os.path.join(self.work, "album")), ["a.jpg"])

    def test_aliases_from_small_models(self):
        self.write("a.txt", "x")
        status, result, name = tools.dispatch(self.context(), "cat", {"filepath": "a.txt"})
        self.assertEqual((status, name), ("ok", "read_file"))

    def test_several_items_in_one_move(self):
        for name in ("a.jpg", "b.png", "c.txt"):
            self.write(name, "x")
        ctx = self.context()
        status, result, _ = tools.dispatch(ctx, "move", {"source": "a.jpg b.png", "destination": "pics"})
        self.assertEqual(status, "ok", result)
        self.assertEqual(sorted(os.listdir(os.path.join(self.work, "pics"))), ["a.jpg", "b.png"])
        status, _, _ = tools.dispatch(ctx, "delete", {"path": ["c.txt"]})
        self.assertEqual(status, "ok")

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
        ctx = self.context(answer="allow", commands=True)
        status, result, _ = tools.dispatch(ctx, "run_command", {"command": "echo hello",
                                                                "reason": "test"})
        self.assertEqual(status, "ok", result)
        self.assertIn("hello", result)
        self.assertEqual(self.asked[0]["category"], "run")

    def test_commands_are_off_unless_turned_on(self):
        status, result, _ = tools.dispatch(self.context(safety="auto"), "run_command",
                                           {"command": "echo hello"})
        self.assertEqual(status, "error")
        self.assertIn("turned off", result)
        self.assertEqual(self.asked, [])
        self.assertNotIn("run_command", [t["name"] for t in tools.schemas(commands=False)])
        self.assertNotIn("run_command", tools.text_protocol_catalog(commands=False))

    def test_reading_outside_for_this_chat_does_not_allow_changing_outside(self):
        elsewhere = os.path.join(self.root, "elsewhere")
        os.makedirs(elsewhere)
        with open(os.path.join(elsewhere, "keep.txt"), "w") as f:
            f.write("mine")
        ctx = self.context(answer="always")
        tools.dispatch(ctx, "read_file", {"path": os.path.join(elsewhere, "keep.txt")})
        tools.dispatch(ctx, "list_folder", {"path": elsewhere})
        self.assertEqual(len(self.asked), 1)              # the read grant covers other reads
        tools.dispatch(ctx, "delete", {"path": os.path.join(elsewhere, "keep.txt")})
        self.assertEqual(len(self.asked), 2)              # ...but a change outside is asked again
        self.assertEqual(self.asked[1]["category"], "change")

    def test_allow_for_this_chat_never_covers_the_next_command(self):
        ctx = self.context(safety="auto", answer="always", commands=True)
        tools.dispatch(ctx, "run_command", {"command": "echo a"})
        tools.dispatch(ctx, "run_command", {"command": "echo b"})
        self.assertEqual(len(self.asked), 2)
        self.assertNotIn("run", ctx.granted)

    def test_auto_mode_asks_before_every_command(self):
        ctx = self.context(safety="auto", commands=True)
        status, _, _ = tools.dispatch(ctx, "run_command", {"command": "echo a"})
        self.assertEqual(status, "ok")
        self.assertEqual(len(self.asked), 1)
        self.assertEqual(self.asked[0]["category"], "run")

    def test_shell_cannot_reach_private_data(self):
        secrets = os.path.join(paths.data_dir(), "secrets.json")
        paths.write_json(secrets, {"openai": "sk-REAL-SECRET"})
        reader = "type" if os.name == "nt" else "cat"
        attempts = [f'{reader} "{secrets}"',
                    f"{reader} {paths.data_dir()}{os.sep}settings.json",
                    f"cd {os.path.dirname(paths.data_dir())} && {reader} {os.path.basename(paths.data_dir())}/secrets.json",
                    "type %APPDATA%\\AetherisEveryone\\secrets.json",
                    "cat ~/.local/share/aetheris-everyone/secrets.json",
                    "cat \"$HOME/Library/Application Support/AetherisEveryone/secrets.json\"",
                    "python -m keyring get \"Aetheris Everyone\" openai",
                    "security find-generic-password -s \"Aetheris Everyone\" -w",
                    "cmdkey /list"]
        for command in attempts:
            ctx = self.context(safety="auto", commands=True)
            status, result, _ = tools.dispatch(ctx, "run_command", {"command": command})
            self.assertEqual(status, "denied", command)
            self.assertNotIn("sk-REAL-SECRET", result)
            self.assertEqual(self.asked, [], command)     # refused before anyone is asked

    def test_default_data_folders_are_recognised_without_a_file_name(self):
        for command in ("dir %APPDATA%\\AetherisEveryone", "Get-ChildItem $env:APPDATA/AetherisEveryone",
                        "ls ~/.local/share/aetheris-everyone/", "ls $XDG_DATA_HOME/aetheris-everyone",
                        'ls "$HOME/Library/Application Support/AetherisEveryone"',
                        "type C:\\Users\\kim\\AppData\\Roaming\\AetherisEveryone\\settings.json"):
            self.assertTrue(tools.touches_private_data(command), command)

    def test_ordinary_commands_are_not_mistaken_for_private_ones(self):
        for command in ("echo hello", "python convert.py report.csv", "dir", "ls -la docs",
                        "cd ~/aetheris-everyone && git status", "pip list"):
            self.assertFalse(tools.touches_private_data(command), command)

    def test_command_environment_has_no_keys(self):
        os.environ["OPENAI_API_KEY"] = "sk-from-env"
        try:
            ctx = self.context(commands=True)
            command = "echo %OPENAI_API_KEY%" if os.name == "nt" else "echo \"[$OPENAI_API_KEY]\""
            status, result, _ = tools.dispatch(ctx, "run_command", {"command": command})
        finally:
            os.environ.pop("OPENAI_API_KEY", None)
        self.assertEqual(status, "ok", result)
        self.assertNotIn("sk-from-env", result)

    def test_auto_mode_asks_before_changing_outside(self):
        outside = os.path.join(self.root, "elsewhere")
        os.makedirs(outside)
        target = os.path.join(outside, "x.txt")
        with open(target, "w") as f:
            f.write("keep")
        ctx = self.context(safety="auto", answer="deny")
        status, _, _ = tools.dispatch(ctx, "delete", {"path": target})
        self.assertEqual(status, "denied")
        self.assertTrue(os.path.exists(target))
        self.assertTrue(self.asked[0]["outside"])
        ctx = self.context(safety="auto", answer="deny")
        status, _, _ = tools.dispatch(ctx, "read_file", {"path": target})
        self.assertEqual(status, "ok")                   # reading outside stays unasked in auto
        self.assertEqual(self.asked, [])

    def test_append_to_a_document_is_refused(self):
        ctx = self.context()
        tools.dispatch(ctx, "write_file", {"path": "d.docx", "content": "# Title\nfirst"})
        status, result, _ = tools.dispatch(ctx, "write_file", {"path": "d.docx", "content": "appended",
                                                               "append": True})
        self.assertEqual(status, "error")
        self.assertIn("append", result)
        text = documents.extract(os.path.join(self.work, "d.docx"))
        self.assertIn("first", text)
        self.assertNotIn("appended", text)

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

    def test_copied_folder_with_later_files_is_not_wiped(self):
        self.write("src/a.txt", "a")
        self.write("src/sub/b.txt", "b")
        ctx = self.context()
        status, result, _ = tools.dispatch(ctx, "copy", {"source": "src", "destination": "copy"})
        self.assertEqual(status, "ok", result)
        self.changes.save()
        self.write("copy/mine.txt", "the person's own file")
        result = history.undo("test-conversation", self.changes.id)
        self.assertFalse(result["ok"])
        self.assertEqual(result["conflicts"], [os.path.join(os.path.realpath(self.work), "copy")])
        self.assertTrue(history.undo("test-conversation", self.changes.id, force=True)["ok"])
        self.assertEqual(self.read("copy/mine.txt"), "the person's own file")
        self.assertFalse(os.path.exists(os.path.join(self.work, "copy", "a.txt")))
        self.assertFalse(os.path.exists(os.path.join(self.work, "copy", "sub")))

    def test_untouched_copied_folder_is_removed(self):
        self.write("src/a.txt", "a")
        ctx = self.context()
        tools.dispatch(ctx, "copy", {"source": "src", "destination": "copy"})
        self.changes.save()
        self.assertTrue(history.undo("test-conversation", self.changes.id)["ok"])
        self.assertFalse(os.path.exists(os.path.join(self.work, "copy")))

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


class DamagedDocuments(Sandbox):
    def test_a_damaged_pdf_is_an_error_message_not_the_end_of_the_turn(self):
        try:
            import pypdf  # noqa: F401
        except ImportError:
            self.skipTest("pypdf is not installed")
        with open(os.path.join(self.work, "broken.pdf"), "wb") as f:
            f.write(b"%PDF-1.4\nthis is not really a pdf")
        self.write("notes.txt", "budget line")
        ctx = self.context()
        status, result, _ = tools.dispatch(ctx, "read_file", {"path": "broken.pdf"})
        self.assertEqual(status, "error")
        self.assertIn("damaged", result)
        status, result, _ = tools.dispatch(ctx, "search_text", {"text": "budget"})
        self.assertEqual(status, "ok", result)              # the broken file is skipped
        self.assertIn("notes.txt", result)


class LookingAtPictures(Sandbox):
    def picture(self, name="cat.png"):
        path = os.path.join(self.work, name)
        with open(path, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n fake")
        return path

    def test_a_model_that_sees_gets_the_picture(self):
        path = self.picture()
        ctx = self.context()
        ctx.sees_images = True
        status, result, _ = tools.dispatch(ctx, "view_image", {"path": "cat.png"})
        self.assertEqual(status, "ok", result)
        self.assertEqual(ctx.shown, [os.path.realpath(path)])
        self.assertEqual(self.asked, [])                  # inside the folder: a read, not asked

    def test_a_blind_model_is_told_instead(self):
        self.picture()
        ctx = self.context()
        status, result, _ = tools.dispatch(ctx, "view_image", {"path": "cat.png"})
        self.assertEqual(status, "error")
        self.assertIn("cannot see pictures", result)
        self.assertEqual(ctx.shown, [])

    def test_not_a_picture_and_too_large(self):
        self.write("notes.txt", "x")
        ctx = self.context()
        ctx.sees_images, ctx.image_limit = True, 5
        self.assertEqual(tools.dispatch(ctx, "view_image", {"path": "notes.txt"})[0], "error")
        self.picture("big.jpg")
        status, result, _ = tools.dispatch(ctx, "view_image", {"path": "big.jpg"})
        self.assertIn("too large", result)
        self.assertEqual(ctx.shown, [])


class WritingDecks(Sandbox):
    def test_write_file_makes_a_deck_and_refuses_to_append_to_one(self):
        ctx = self.context()
        status, result, _ = tools.dispatch(ctx, "write_file", {"path": "talk.pptx", "content": "# Hi\n- one"})
        self.assertEqual(status, "ok", result)
        self.assertIn("## Slide 1", documents.extract(os.path.join(self.work, "talk.pptx")))
        status, result, _ = tools.dispatch(ctx, "write_file", {"path": "talk.pptx", "content": "- two",
                                                               "append": True})
        self.assertEqual(status, "error")
