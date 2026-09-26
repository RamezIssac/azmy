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
    def text_layer_ok(self) -> bool:
        """Heuristic: at least half of the pages yield meaningful text."""
        if not self.pages:
            return False
        with_text = sum(1 for p in self.pages if len(p.text.strip()) > 20)
        return with_text >= max(1, len(self.pages) // 2)

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
