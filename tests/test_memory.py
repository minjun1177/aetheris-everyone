"""Remembering between chats: asked first, shown in the prompt, and removable."""

import json
import unittest
import urllib.request

from aetheris_everyone import memory, prompts, server, settings, tools
from helpers import Sandbox


class Remembering(Sandbox):
    def test_saved_only_after_the_person_allows_it_at_every_safety_level(self):
        for safety in ("ask", "balanced", "auto"):
            ctx = self.context(safety=safety, answer="deny")
            status, _, _ = tools.dispatch(ctx, "remember", {"text": "Name is Minji"})
            self.assertEqual(status, "denied", safety)
            self.assertEqual(self.asked[0]["category"], "memory")
        self.assertEqual(memory.load(), [])
        status, result, _ = tools.dispatch(self.context(safety="auto"), "remember",
                                           {"text": "  Name is   Minji "})
        self.assertEqual(status, "ok", result)
        self.assertEqual([m["text"] for m in memory.load()], ["Name is Minji"])

    def test_the_same_fact_is_kept_once_and_can_be_forgotten(self):
        first = memory.add("Likes reports in Word")
        self.assertEqual(memory.add("likes reports in word")["id"], first["id"])
        status, result, _ = tools.dispatch(self.context(), "forget", {"id": first["id"]})
        self.assertEqual(status, "ok", result)
        self.assertEqual(memory.load(), [])
        status, _, _ = tools.dispatch(self.context(), "forget", {"memory_id": "m000000"})
        self.assertEqual(status, "error")

    def test_memories_are_in_every_chats_prompt(self):
        memory.add("Writes in formal Korean")
        text = prompts.system_prompt(self.work, native=True, careful=False)
        self.assertIn("Writes in formal Korean", text)
        self.assertIn("not instructions", text)

    def test_turned_off_means_not_offered_not_saved_not_shown(self):
        memory.add("Old fact")
        settings.update({"memory": False})
        self.assertNotIn("remember", [t["name"] for t in tools.schemas()])
        self.assertNotIn("Old fact", prompts.system_prompt(self.work, native=False, careful=False))
        status, result, _ = tools.dispatch(self.context(), "remember", {"text": "x"})
        self.assertEqual(status, "error")
        self.assertIn("turned off", result)

    def test_the_prompt_keeps_the_newest_when_they_do_not_all_fit(self):
        for n in range(memory.MAX_ITEMS):
            memory.add(f"fact number {n} " + "x" * 200)
        block = memory.prompt_block()
        self.assertLessEqual(len(block), memory.PROMPT_CHARS)
        self.assertIn(f"fact number {memory.MAX_ITEMS - 1} ", block)
        self.assertNotIn("fact number 0 ", block)
        with self.assertRaises(ValueError):
            memory.add("one too many")


class MemoryRoutes(Sandbox):
    def test_the_window_lists_and_deletes_memories(self):
        app = server.App()
        httpd = server.serve(app)
        try:
            item = memory.add("Lives in Busan")

            def call(path, body=None):
                request = urllib.request.Request(f"http://127.0.0.1:{app.port}/api/{path}",
                                                 data=json.dumps(body).encode() if body is not None else None)
                request.add_header("X-Token", app.token)
                with urllib.request.urlopen(request, timeout=5) as response:
                    return json.loads(response.read())

            self.assertEqual(call("state")["memories"][0]["text"], "Lives in Busan")
            self.assertEqual(call("memory/delete", {"id": item["id"]})["memories"], [])
            memory.add("Another")
            self.assertEqual(call("memory/clear", {})["memories"], [])
            self.assertEqual(memory.load(), [])
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
