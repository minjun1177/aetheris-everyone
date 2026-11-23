import unittest

from aetheris_everyone import toolcalls, tools


class ParseToolCalls(unittest.TestCase):
    def test_plain_call(self):
        calls = toolcalls.parse_tool_calls(
            'Sure.\n<tool_call>\n{"name": "list_folder", "arguments": {"path": "."}}\n</tool_call>')
        self.assertEqual(calls, [("list_folder", {"path": "."})])

    def test_raw_block_carries_the_file(self):
        text = ('<tool_call>\n{"name": "write_file", "arguments": {"path": "a.py"}}\n'
                '<content>\nprint("hi \\n there")\n</content>\n</tool_call>')
        name, args = toolcalls.parse_tool_calls(text)[0]
        self.assertEqual(name, "write_file")
        self.assertEqual(args["content"], 'print("hi \\n there")')

    def test_missing_brace_is_repaired(self):
        calls = toolcalls.parse_tool_calls(
            '<tool_call>{"name": "read_file", "arguments": {"path": "x.txt"}</tool_call>')
        self.assertEqual(calls, [("read_file", {"path": "x.txt"})])

    def test_flattened_and_renamed(self):
        calls = toolcalls.parse_tool_calls(
            '<tool_call>{"tool_name": "read_file", "path": "x.txt"}</tool_call>')
        self.assertEqual(calls, [("read_file", {"path": "x.txt"})])

    def test_envelope_unwrapped(self):
        calls = toolcalls.parse_tool_calls(
            '<tool_call>{"tool_call": {"name": "web_search", "arguments": {"query": "q"}}}</tool_call>')
        self.assertEqual(calls, [("web_search", {"query": "q"})])

    def test_fenced_call_only_when_tool_exists(self):
        known = lambda n: tools.lookup(n) is not None
        fenced = '```tool_call\n{"name": "list_folder", "arguments": {}}\n```'
        self.assertEqual(toolcalls.parse_tool_calls(fenced, known), [("list_folder", {})])
        code = '```json\n{"name": "Alice", "age": 3}\n```'
        self.assertEqual(toolcalls.parse_tool_calls(code, known), [])

    def test_cut_off_raw_block_is_not_run(self):
        text = '<tool_call>{"name": "write_file", "arguments": {"path": "a"}}\n<content>\nhalf'
        self.assertEqual(toolcalls.parse_tool_calls(text), [])

    def test_several_calls_in_order(self):
        text = ('<tool_call>{"name": "read_file", "arguments": {"path": "a"}}</tool_call>'
                '<tool_call>{"name": "read_file", "arguments": {"path": "b"}}</tool_call>')
        self.assertEqual([a["path"] for _, a in toolcalls.parse_tool_calls(text)], ["a", "b"])

    def test_thinking_is_not_parsed(self):
        text = ('<think>maybe <tool_call>{"name": "delete", "arguments": {"path": "x"}}'
                '</tool_call></think>Done.')
        self.assertEqual(toolcalls.parse_tool_calls(text), [])


class StreamFilterTest(unittest.TestCase):
    def test_tags_split_across_chunks(self):
        f = toolcalls.StreamFilter()
        out = []
        for chunk in ["Hel", "lo <th", "ink>secret</thi", "nk> world <tool", "_call>{...}"]:
            out += f.feed(chunk)
        out += f.close()
        prose = "".join(text for kind, text in out if kind == "prose")
        think = "".join(text for kind, text in out if kind == "think")
        self.assertEqual(prose, "Hello  world ")
        self.assertEqual(think, "secret")

    def test_visible_text(self):
        self.assertEqual(toolcalls.visible_text("<think>x</think>Hi <tool_call>{}"), "Hi")


if __name__ == "__main__":
    unittest.main()
