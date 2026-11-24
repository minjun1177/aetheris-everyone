"""Scheduled requests: when they run, what is skipped, and that a run is a normal turn."""

import threading
import time
import unittest

from aetheris_everyone import conversations, providers, schedules, server, settings
from helpers import Sandbox


def at(year, month, day, hour, minute):
    return time.mktime((year, month, day, hour, minute, 0, 0, 0, -1))


class Times(unittest.TestCase):
    def test_daily_weekly_and_once(self):
        monday_8 = at(2026, 11, 23, 8, 0)                    # 2026-11-23 is a Monday
        self.assertEqual(schedules.next_time({"kind": "daily", "time": "09:00"}, monday_8),
                         at(2026, 11, 23, 9, 0))
        self.assertEqual(schedules.next_time({"kind": "daily", "time": "07:30"}, monday_8),
                         at(2026, 11, 24, 7, 30))
        self.assertEqual(schedules.next_time({"kind": "weekly", "day": 4, "time": "18:00"}, monday_8),
                         at(2026, 11, 27, 18, 0))            # Friday
        self.assertEqual(schedules.next_time({"kind": "weekly", "day": 0, "time": "07:00"}, monday_8),
                         at(2026, 11, 30, 7, 0))             # this Monday's 07:00 has passed
        self.assertIsNone(schedules.next_time({"kind": "once", "at": monday_8 - 60}, monday_8))

    def test_bad_schedules_are_refused(self):
        for when in ({"kind": "hourly"}, {"kind": "daily", "time": "25:00"}, {"kind": "daily", "time": "x"},
                     {"kind": "weekly", "time": "09:00", "day": 9}, {"kind": "once", "at": time.time() - 5}, None):
            with self.assertRaises(ValueError, msg=str(when)):
                schedules.check(when)


class Due(Sandbox):
    def test_a_run_waits_while_busy_and_a_long_missed_one_is_skipped(self):
        item = schedules.save("tidy", {"kind": "daily", "time": "09:00"}, self.work)
        due_at = item["next"]
        self.assertEqual(schedules.take_due(due_at + 1, busy=True), [])        # waits
        self.assertEqual([i["id"] for i in schedules.take_due(due_at + 60, busy=False)], [item["id"]])
        moved = schedules.load()[0]
        self.assertEqual(moved["next"], schedules.next_time(moved["when"], due_at + 60))
        self.assertEqual(schedules.take_due(moved["next"] + schedules.MISSED_AFTER + 5, busy=False), [])
        self.assertEqual(schedules.load()[0]["missed"], moved["next"])          # recorded, not run late

    def test_a_one_off_turns_itself_off_after_running(self):
        item = schedules.save("once", {"kind": "once", "at": time.time() + 30}, self.work)
        self.assertEqual(len(schedules.take_due(item["next"] + 1, busy=False)), 1)
        saved = schedules.load()[0]
        self.assertFalse(saved["enabled"])
        self.assertIsNone(saved["next"])


class Running(Sandbox):
    def test_a_due_schedule_is_a_normal_turn_marked_as_scheduled(self):
        settings.update({"work_folder": self.work, "auto_title": False})
        item = schedules.save("정리해줘", {"kind": "daily", "time": "09:00"}, self.work, "아침 정리")

        class Fake:
            name = "fake"

            def check_ready(self):
                pass

            def native_tools(self):
                return False

            def sees_images(self):
                return False

            def stream(self, messages, tools=None, think=False):
                self.seen = messages
                return iter([{"text": "정리했어요."}, {"done": True}])

        fake = Fake()
        original = providers.make
        providers.make = lambda *a, **k: fake
        app = server.App()
        done = threading.Event()
        app.agent.emit = lambda e: done.set() if e["type"] == "turn_end" else None
        try:
            self.assertEqual(app.run_schedules(item["next"] + 1), [item["id"]])
            self.assertTrue(done.wait(10))
        finally:
            providers.make = original
        conversation_id = schedules.load()[0]["conversation"]
        conversation = conversations.load(conversation_id)
        self.assertEqual(conversation["title"], "⏰ 아침 정리")
        self.assertTrue(conversation["ui"][0]["scheduled"])
        self.assertIn("started by a schedule", fake.seen[-1]["content"])


if __name__ == "__main__":
    unittest.main()
