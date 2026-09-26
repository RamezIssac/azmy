from django.test import SimpleTestCase

from extraction.services.llm import parse_json_content


class ParseJsonContentTest(SimpleTestCase):
    def test_plain(self):
        self.assertEqual(parse_json_content('{"ok": true}'), {"ok": True})

    def test_fenced(self):
        self.assertEqual(
            parse_json_content('```json\n{"ok": true}\n```'), {"ok": True}
        )

    def test_leading_prose(self):
        self.assertEqual(
            parse_json_content('Here is the result:\n{"ok": false}\nDone.'),
            {"ok": False},
        )

    def test_whitespace(self):
        self.assertEqual(parse_json_content('  \n {"a": 1} \n'), {"a": 1})

    def test_garbage(self):
        self.assertIsNone(parse_json_content("no json here"))
        self.assertIsNone(parse_json_content(""))
        self.assertIsNone(parse_json_content(None))
