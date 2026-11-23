"""Each provider's streaming format, turned into the one shape of event - from canned wire data."""

import json
import unittest

from aetheris_everyone import providers
from helpers import Sandbox


class FakeResponse:
    def __init__(self, lines):
        self.lines = [line.encode("utf-8") + b"\n" for line in lines]
        self.closed = False

    def __iter__(self):
        return iter(self.lines)

    def close(self):
        self.closed = True


def sse(*events):
    lines = []
    for event in events:
        lines += [f"data: {event if isinstance(event, str) else json.dumps(event)}", ""]
    return lines


class Streams(Sandbox):
    def stream(self, name, lines, tools=None):
        sent = {}

        def fake_open(url, payload=None, headers=None, timeout=0, method=None):
            sent.update(url=url, payload=payload, headers=headers)
            return FakeResponse(lines)

        original = providers._open
        providers._open = fake_open
        try:
            provider = providers.make(name, model="m", key="k")
            if name == "ollama":
                provider.thinks = lambda: False
            events = list(provider.stream([{"role": "system", "content": "sys"},
                                           {"role": "user", "content": "hi"}], tools=tools))
        finally:
            providers._open = original
        return events, sent

    def test_anthropic(self):
        events, sent = self.stream("anthropic", sse(
            {"type": "message_start"},
            {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking"}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "hmm"}},
            {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "Hel"}},
            {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "lo"}},
            {"type": "content_block_start", "index": 2,
             "content_block": {"type": "tool_use", "name": "read_file", "id": "t1"}},
            {"type": "content_block_delta", "index": 2, "delta": {"type": "input_json_delta", "partial_json": "{\"pa"}},
            {"type": "content_block_delta", "index": 2, "delta": {"type": "input_json_delta", "partial_json": "th\": \"a.txt\"}"}},
            {"type": "content_block_stop", "index": 2},
            {"type": "message_stop"}))
        self.assertEqual(events, [{"thinking": "hmm"}, {"text": "Hel"}, {"text": "lo"},
                                  {"tool_call": {"name": "read_file", "arguments": {"path": "a.txt"}}},
                                  {"done": True, "truncated": False}])
        self.assertEqual(sent["payload"]["system"], "sys")
        self.assertEqual(sent["headers"]["x-api-key"], "k")

    def test_anthropic_overloaded_is_a_rate_limit(self):
        with self.assertRaises(providers.ProviderError) as caught:
            self.stream("anthropic", sse({"type": "error", "error": {"message": "Overloaded"}}))
        self.assertEqual(caught.exception.code, "rate_limit")

    def test_openai(self):
        events, _ = self.stream("openai", sse(
            {"choices": [{"delta": {"reasoning_content": "think"}}]},
            {"choices": [{"delta": {"content": "Hi"}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c", "function": {"name": "list_folder", "arguments": ""}}]}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "{\"path\": \".\"}"}}]}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 1, "function": {"name": "web_search", "arguments": "{bad"}}]}}]},
            "[DONE]"))
        self.assertEqual(events[:2], [{"thinking": "think"}, {"text": "Hi"}])
        self.assertEqual(events[2], {"tool_call": {"name": "list_folder", "arguments": {"path": "."}}})
        self.assertEqual(events[3]["tool_call"]["name"], "web_search")
        self.assertIn("not valid JSON", events[3]["tool_call"]["error"])
        self.assertEqual(events[-1], {"done": True, "truncated": False})

    def test_gemini(self):
        events, sent = self.stream("gemini", sse(
            {"candidates": [{"content": {"parts": [{"text": "plan", "thought": True}, {"text": "Answer"}]}}]},
            {"candidates": [{"content": {"parts": [{"functionCall": {"name": "find_files", "args": {"pattern": "*.pdf"}}}]}}]}),
            tools=[{"name": "find_files", "description": "d", "parameters": {"type": "object", "properties": {}}}])
        self.assertEqual(events, [{"thinking": "plan"}, {"text": "Answer"},
                                  {"tool_call": {"name": "find_files", "arguments": {"pattern": "*.pdf"}}},
                                  {"done": True, "truncated": False}])
        self.assertNotIn("parameters", sent["payload"]["tools"][0]["functionDeclarations"][0])
        self.assertTrue(sent["url"].endswith(":streamGenerateContent?alt=sse"))

    def test_ollama(self):
        lines = [json.dumps({"message": {"thinking": "t"}}), "not json",
                 json.dumps({"message": {"content": "Hi"}}),
                 json.dumps({"message": {"tool_calls": [{"function": {"name": "read_file", "arguments": {"path": "x"}}},
                                                        {"function": {"name": "move", "arguments": "{\"source\": \"a\"}"}}]}}),
                 json.dumps({"done": True}), json.dumps({"message": {"content": "after done"}})]
        events, sent = self.stream("ollama", lines)
        self.assertEqual(events, [{"thinking": "t"}, {"text": "Hi"},
                                  {"tool_call": {"name": "read_file", "arguments": {"path": "x"}}},
                                  {"tool_call": {"name": "move", "arguments": {"source": "a"}}},
                                  {"done": True, "truncated": False}])
        self.assertTrue(sent["url"].endswith("/api/chat"))

    def test_length_limit_is_reported_by_every_provider(self):
        cases = {
            "ollama": [json.dumps({"message": {"content": "<tool_call>{"}}),
                       json.dumps({"done": True, "done_reason": "length"})],
            "anthropic": sse({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "x"}},
                             {"type": "message_delta", "delta": {"stop_reason": "max_tokens"}}),
            "openai": sse({"choices": [{"delta": {"content": "x"}, "finish_reason": "length"}]}, "[DONE]"),
            "gemini": sse({"candidates": [{"content": {"parts": [{"text": "x"}]}, "finishReason": "MAX_TOKENS"}]}),
        }
        for name, lines in cases.items():
            events, _ = self.stream(name, lines)
            self.assertEqual(events[-1], {"done": True, "truncated": True}, name)

    def test_ollama_error_line(self):
        with self.assertRaises(providers.ProviderError):
            self.stream("ollama", [json.dumps({"error": "model crashed"})])


class Hosts(Sandbox):
    def test_ollama_host_setting_is_used_and_validated(self):
        from aetheris_everyone import ollama_setup, settings
        settings.update({"ollama_host": "192.168.0.2:11434/"})
        self.assertEqual(providers.OllamaProvider().host, "http://192.168.0.2:11434")
        self.assertFalse(ollama_setup.is_local())
        launched = []
        real_running, real_popen = ollama_setup.running, ollama_setup.subprocess.Popen
        ollama_setup.running = lambda: False
        ollama_setup.subprocess.Popen = lambda *a, **k: launched.append(a)
        try:
            self.assertFalse(ollama_setup.start())       # another computer's engine is not ours
        finally:
            ollama_setup.running, ollama_setup.subprocess.Popen = real_running, real_popen
        self.assertEqual(launched, [])
        ollama_setup.running = lambda: False
        try:
            self.assertFalse(ollama_setup.status()["can_install"])
        finally:
            ollama_setup.running = real_running
        settings.update({"ollama_host": "ftp://nope"})
        self.assertEqual(settings.get("ollama_host"), "http://192.168.0.2:11434")
        settings.update({"ollama_host": ""})
        self.assertEqual(settings.get("ollama_host"), "http://127.0.0.1:11434")
        self.assertTrue(ollama_setup.is_local())


if __name__ == "__main__":
    unittest.main()
