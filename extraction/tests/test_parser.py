from pathlib import Path

from django.test import TestCase

from extraction.services.lv_parser import parse_lv_pages
from extraction.services.pdf_text import read_pdf

FIXTURE = Path(__file__).parent / "fixtures" / "trockenbauarbeiten.pdf"


class LVParserTest(TestCase):
    """The 90-page sample tender is our golden file."""

    @classmethod
    def setUpTestData(cls):
        content = read_pdf(str(FIXTURE))
        cls.content = content
        cls.lv = parse_lv_pages(content.pages)

    def test_text_layer(self):
        self.assertEqual(self.content.page_count, 90)
        self.assertTrue(self.content.text_layer_ok)
        self.assertGreater(len(self.content.positions_pages), 50)

    def test_lv_header(self):
        self.assertEqual(self.lv.number, "11")
        self.assertEqual(self.lv.gewerk, "Trockenbauarbeiten")

    def test_section_tree(self):
        kinds = {(s.kind, s.number) for s in self.lv.sections}
        self.assertIn(("lv", "11"), kinds)
        self.assertIn(("titel", "03"), kinds)
        self.assertIn(("untertitel", "01"), kinds)
        titels = [s for s in self.lv.sections if s.kind == "titel"]
        self.assertGreaterEqual(len(titels), 5)

    def test_items_complete(self):
        self.assertEqual(len(self.lv.items), 178)
        self.assertEqual(self.lv.report["items_without_qty"], 0)
        self.assertEqual(self.lv.report["warnings"], [])
        for item in self.lv.items:
            self.assertTrue(item.short_text, f"{item.oz} missing short text")
            self.assertTrue(item.long_lines, f"{item.oz} missing long text")
            self.assertIsNotNone(item.menge, f"{item.oz} missing quantity")
            self.assertTrue(item.einheit, f"{item.oz} missing unit")
            self.assertGreaterEqual(item.confidence, 0.9)

    def test_spot_check_item(self):
        item = next(i for i in self.lv.items if i.oz == "02.01.10")
        self.assertIn("Metallständerwand", item.short_text)
        self.assertEqual(item.menge, 6900.0)
        self.assertEqual(item.einheit, "m²")

    def test_multipage_item_merged(self):
        """Position 03.01.310 spans pages 60-61 via Fortsetzung markers."""
        item = next(i for i in self.lv.items if i.oz == "03.01.310")
        self.assertEqual(item.page_start, 60)
        self.assertEqual(item.page_end, 61)
        self.assertEqual(item.menge, 1.0)
        self.assertEqual(item.einheit, "St")
        self.assertGreater(len(item.long_lines), 10)

    def test_unit_price_only_positions(self):
        """'* nur Einheitspreis *' rows still yield quantity+unit."""
        item = next(i for i in self.lv.items if i.oz == "02.01.530")
        self.assertEqual(item.menge, 1750.0)
        self.assertIsNone(item.unit_price)

    def test_repeated_position_numbers_scoped_per_section(self):
        numbers = [i for i in self.lv.items if i.number == "310"]
        self.assertGreaterEqual(len(numbers), 2)
        ozs = {i.oz for i in numbers}
        self.assertEqual(len(ozs), len(numbers))  # no OZ collision
