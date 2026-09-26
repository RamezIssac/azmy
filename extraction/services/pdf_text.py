"""Text-layer extraction and page triage using pypdfium2 (bundled PDFium)."""

from __future__ import annotations

from dataclasses import dataclass, field

import pypdfium2 as pdfium

# Pages of an LV that carry the position table are headed by this phrase.
POSITIONS_HEADER = "Aufstellung der Leistungspositionen"
# Narrative front matter (ZTV, Baubeschreibung, …) — skipped for item parsing.
VORSANN_HEADER = "Vorspanntext des Leistungsverzeichnisses"


@dataclass
class PageText:
    number: int  # 1-based
    text: str


@dataclass
class PdfContent:
    page_count: int
    pages: list[PageText] = field(default_factory=list)

    @property
    def text_coverage(self) -> float:
        """Share of pages that yield meaningful text (0..1)."""
        if not self.pages:
            return 0.0
        with_text = sum(1 for p in self.pages if len(p.text.strip()) > 20)
        return with_text / len(self.pages)

    @property
    def text_layer_ok(self) -> bool:
        """At least half of the pages yield text. Use text_coverage for nuance
        (mixed text+drawing documents sit below 0.5 but are still usable)."""
        return self.text_coverage >= 0.5

    @property
    def positions_pages(self) -> list[PageText]:
        return [p for p in self.pages if POSITIONS_HEADER in p.text]

    @property
    def cover_text(self) -> str:
        return self.pages[0].text if self.pages else ""

    def text_through(self, max_pages: int = 8) -> str:
        """First pages joined — cover, TOC, front matter (for LLM metadata)."""
        return "\n\n".join(p.text for p in self.pages[:max_pages])


def read_pdf(path: str) -> PdfContent:
    pdf = pdfium.PdfDocument(path)
    content = PdfContent(page_count=len(pdf))
    try:
        for i in range(len(pdf)):
            page = pdf[i]
            try:
                text = page.get_textpage().get_text_range() or ""
            finally:
                page.close()
            content.pages.append(PageText(number=i + 1, text=text))
    finally:
        pdf.close()
    return content
