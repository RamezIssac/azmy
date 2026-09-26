"""Deterministic parser for German Leistungsverzeichnis (LV) position tables.

Targets the widespread "Nr. / Art | Text / Menge / Einheit | EP | GP" layout
produced by common AVA software (see docs/phase-1-design.md). Works on the
reading-order text layer (pypdfium2). Returns plain data — persistence lives
in the pipeline.

Structure of a positions page (sample: trockenbauarbeiten.pdf):

    Leistungsverzeichnis
    Aufstellung der Leistungspositionen   Projekt: ...
     11 LV Trockenbauarbeiten
    03 Titel Trockenbauarbeiten EDEKA
    01 Untertitel Montagewände            Übertrag: ..........
     Nr. / Art   Text / Menge / Einheit   Einheitspreis (EP)  Gesamtpreis (GP)
    290 Öffnung herstellen D 150mm ...           <- position number + short text
    Position Öffnung herstellen, ...             <- "Position" + long text lines
    ...
    1 St EP ........................ GP ........................   <- qty row
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .pdf_text import POSITIONS_HEADER, PageText

# --- line patterns -----------------------------------------------------------

SECTION_RE = re.compile(
    r"^\s*(\d{1,4})\s+(LV|Titel|Untertitel|Abschnitt)\s+(.+?)\s*$"
)
UEBERTRAG_RE = re.compile(r"\s*Übertrag\s*:?\s*[.…]*\s*$")
# A position candidate: number + text. Must be confirmed by a following
# "Position" line (guards against numbered long-text lines).
POS_RE = re.compile(r"^(\d{1,6})\s{1,}(\S.*)$")
ART_RE = re.compile(r"^(Position|Sonderposition|Bedarfsposition|Grundposition)\b[:\s]?(.*)$")
QTY_RE = re.compile(
    r"^\s*([\d][\d.,]*)\s*([A-Za-zÄÖÜäöüµ%²³0-9/\-]{0,12}?)\s*"
    r"EP\s+([.…]+|[\d.,]+)\s*"
    r"(?:GP\s+([.…]+|[\d.,]+)|\*\s*nur\s+Einheitspreis\s*\*)?\s*$"
)
CONT_NEXT_RE = re.compile(r"-\s*Fortsetzung auf n[aä]chster Seite\s*-")
CONT_FROM_RE = re.compile(r"-\s*Fortsetzung von Eintrag\s+(\d+)\s*-")
FOOTER_RES = [
    re.compile(r"Alle Einzelbeträge Netto", re.I),
    re.compile(r"\d{2}\.\d{2}\.\d{4}\s*-\s*Seite\s+\d+\s+von\s+\d+"),
    re.compile(r"^Leistungsverzeichnis\s*$"),
    re.compile(r"^Aufstellung der Leistungspositionen\b"),
    re.compile(r"^Projekt\s*:"),
    re.compile(r"Nr\.\s*/\s*Art"),
    re.compile(r"^Seite\s+\d+\s+von\s+\d+\s*$"),
    re.compile(r"^Übertrag\s*:?\s*[.…]*$"),
    re.compile(r"^Text(\s*/\s*Menge)?(\s*/\s*Einheit)?\s*$"),
    re.compile(r"^\*{2,3}\s*Bedarfspos\.?\s*$"),
]
SECTION_KIND_MAP = {
    "LV": "lv",
    "Titel": "titel",
    "Untertitel": "untertitel",
    "Abschnitt": "abschnitt",
}


def _is_noise(line: str) -> bool:
    return any(rx.search(line) for rx in FOOTER_RES)


def _parse_qty(text: str) -> float | None:
    """German number format: 1.234,56 -> 1234.56"""
    text = text.strip().replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


@dataclass
class ParsedSection:
    number: str
    kind: str
    title: str
    page_start: int
    ordering: int
    path: tuple = ()  # full path incl. self, e.g. (("lv","11"),("titel","03"))
    items: list["ParsedItem"] = field(default_factory=list)

    @property
    def path_key(self) -> tuple:
        return (self.kind, self.number)


@dataclass
class ParsedItem:
    number: str
    short_text: str = ""
    long_lines: list[str] = field(default_factory=list)
    menge: float | None = None
    einheit: str = ""
    unit_price: float | None = None
    total_price: float | None = None
    page_start: int = 0
    page_end: int = 0
    confidence: float = 1.0
    notes: list[str] = field(default_factory=list)
    ordering: int = 0
    section_path: tuple = ()  # (("lv","11"),("titel","03"),("untertitel","01"))

    @property
    def oz(self) -> str:
        parts = [num for kind, num in self.section_path if kind != "lv"]
        return ".".join([*parts, self.number])

    @property
    def long_text(self) -> str:
        return "\n".join(self.long_lines).strip()


@dataclass
class ParsedLV:
    number: str = ""
    gewerk: str = ""
    sections: list[ParsedSection] = field(default_factory=list)
    items: list[ParsedItem] = field(default_factory=list)
    report: dict = field(default_factory=dict)


class LVParser:
    def __init__(self):
        self.sections: list[ParsedSection] = []
        self.section_index: dict[tuple, ParsedSection] = {}
        self.current_path: list[ParsedSection] = []
        self.items: list[ParsedItem] = []
        self.item_by_key: dict[tuple, ParsedItem] = {}
        self.current_item: ParsedItem | None = None
        self.lv_number = ""
        self.lv_gewerk = ""
        self._ordering = 0
        self.warnings: list[str] = []

    # -- helpers --------------------------------------------------------------

    def _register_section(self, number: str, kind_word: str, title: str, page: int):
        kind = SECTION_KIND_MAP[kind_word]
        title = UEBERTRAG_RE.sub("", title).strip()
        if kind == "lv" and not self.lv_number:
            self.lv_number = number
            self.lv_gewerk = title
        # hierarchy: LV < Titel < Untertitel < Abschnitt
        order = ["lv", "titel", "untertitel", "abschnitt"]
        depth = order.index(kind)
        while self.current_path and (
            order.index(self.current_path[-1].kind) >= depth
        ):
            self.current_path.pop()
        key = tuple(s.path_key for s in [*self.current_path]) + ((kind, number),)
        if key not in self.section_index:
            self._ordering += 1
            sec = ParsedSection(
                number=number,
                kind=kind,
                title=title,
                page_start=page,
                ordering=self._ordering,
                path=key,
            )
            self.section_index[key] = sec
            self.sections.append(sec)
        sec = self.section_index[key]
        self.current_path.append(sec)

    def _open_item(self, number: str, short_text: str, page: int):
        self._close_item(reason="superseded")
        self._ordering += 1
        item = ParsedItem(
            number=number,
            short_text=short_text.strip(),
            page_start=page,
            page_end=page,
            ordering=self._ordering,
            section_path=tuple(s.path_key for s in self.current_path),
        )
        if not self.current_path:
            item.confidence = 0.3
            item.notes.append("position found outside any section")
        self.items.append(item)
        self.item_by_key[(item.section_path, number)] = item
        self.current_item = item

    def _close_item(self, reason: str = ""):
        # no-qty penalty is applied in a final pass (parse()), because items
        # legitimately span page/section-header breaks before their qty row.
        self.current_item = None

    # -- main ------------------------------------------------------------------

    def parse(self, pages: list[PageText]) -> ParsedLV:
        position_pages = [p for p in pages if POSITIONS_HEADER in p.text]
        if not position_pages:
            # no fallback: parsing narrative pages as positions produces garbage.
            # The pipeline routes such documents to the manual queue instead.
            self.warnings.append("no positions-header pages found")
            return ParsedLV(report={"item_count": 0, "section_count": 0,
                                    "items_without_qty": 0, "low_confidence": [],
                                    "warnings": self.warnings})

        for page in position_pages:
            self._parse_page(page)

        self._close_item(reason="eof")
        for item in self.items:
            if item.menge is None:
                item.confidence = min(item.confidence, 0.6)
                item.notes.append("no quantity row detected")
        lv = ParsedLV(
            number=self.lv_number,
            gewerk=self.lv_gewerk,
            sections=self.sections,
            items=self.items,
        )
        lv.report = {
            "item_count": len(self.items),
            "section_count": len(self.sections),
            "items_without_qty": sum(1 for i in self.items if i.menge is None),
            "low_confidence": [
                {"oz": i.oz, "confidence": i.confidence, "notes": i.notes}
                for i in self.items
                if i.confidence < 0.9
            ],
            "warnings": self.warnings,
        }
        return lv

    def _parse_page(self, page: PageText):
        lines = [ln.rstrip() for ln in page.text.splitlines()]
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            i += 1
            if not line or _is_noise(line):
                continue

            m = CONT_NEXT_RE.search(line)
            if m:
                # current item continues on next page; keep it open
                continue
            m = CONT_FROM_RE.search(line)
            if m:
                num = m.group(1)
                path = tuple(s.path_key for s in self.current_path)
                target = self.item_by_key.get((path, num))
                if target is None:
                    # fall back to the most recent item with that number
                    target = next(
                        (it for it in reversed(self.items) if it.number == num),
                        None,
                    )
                if target is not None:
                    self.current_item = target
                    target.page_end = page.number
                else:
                    self.warnings.append(
                        f"continuation of unknown position {num} on page {page.number}"
                    )
                continue

            m = SECTION_RE.match(line)
            if m:
                self._close_item(reason="section break")
                self._register_section(m.group(1), m.group(2), m.group(3), page.number)
                continue

            m = QTY_RE.match(line)
            if m and self.current_item is not None:
                self.current_item.menge = _parse_qty(m.group(1))
                self.current_item.einheit = m.group(2)
                if not set(m.group(3)) <= {".", "…"}:
                    self.current_item.unit_price = _parse_qty(m.group(3))
                if m.group(4) and not set(m.group(4)) <= {".", "…"}:
                    self.current_item.total_price = _parse_qty(m.group(4))
                self.current_item.page_end = page.number
                self._close_item(reason="qty")
                continue

            m = POS_RE.match(line)
            if m and i < len(lines):
                art = ART_RE.match(lines[i].strip())
                if art:
                    self._open_item(m.group(1), m.group(2), page.number)
                    first_long = art.group(2).strip()
                    if first_long:
                        self.current_item.long_lines.append(first_long)
                    i += 1
                    continue

            # plain long-text line → append to the open item
            if self.current_item is not None:
                self.current_item.page_end = page.number
                self.current_item.long_lines.append(line)


def parse_lv_pages(pages: list[PageText]) -> ParsedLV:
    return LVParser().parse(pages)
