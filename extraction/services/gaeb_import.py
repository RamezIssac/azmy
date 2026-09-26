"""GAEB DA XML (X83/X31 family) import into the same LV tree.

Doubles as the ground-truth benchmark for the PDF extractor (same project as
GAEB + PDF → diff the two trees).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation

from django.db import transaction

from extraction.models import LV, LVItem, LVSection
from projects.models import Document


def _strip_ns(elem: ET.Element):
    for e in elem.iter():
        if "}" in e.tag:
            e.tag = e.tag.split("}", 1)[1]
        if e.text:
            e.text = e.text.strip()


def _text(elem: ET.Element | None, *path: str) -> str:
    node = elem
    for part in path:
        if node is None:
            return ""
        node = node.find(part)
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _decimal(raw: str) -> Decimal | None:
    raw = (raw or "").strip().replace(" ", "")
    if not raw:
        return None
    # GAEB XML uses dot as decimal separator; tolerate German comma too
    if "," in raw and "." not in raw:
        raw = raw.replace(",", ".")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


@transaction.atomic
def import_gaeb(document: Document) -> LV:
    tree = ET.parse(document.file.path)
    root = tree.getroot()
    _strip_ns(root)

    boq = root.find(".//BoQ")
    if boq is None:
        raise ValueError("no <BoQ> element — not a GAEB DA XML phase 83/31 file?")

    LV.objects.filter(document=document).delete()
    lv = LV.objects.create(
        document=document,
        number=_text(boq, "BoQInfo", "No") or _text(boq, "No"),
        gewerk=_text(boq, "BoQInfo", "Name") or _text(boq, "Name"),
    )

    ordering = 0

    def walk_ctgy(ctgy: ET.Element, parent: LVSection | None, path: list[str]):
        nonlocal ordering
        ordering += 1
        number = _text(ctgy, "No") or str(ordering)
        title = _text(ctgy, "Description", "DescriptionText") or _text(
            ctgy, "Description", "ShortText"
        )
        depth = len(path) + (0 if parent is None else 1)
        kind = (
            LVSection.Kind.TITEL
            if parent is None
            else (LVSection.Kind.UNTERTITEL if depth <= 2 else LVSection.Kind.ABSCHNITT)
        )
        section = LVSection.objects.create(
            lv=lv,
            parent=parent,
            kind=kind,
            number=number,
            title=title,
            ordering=ordering,
        )
        new_path = [*path, number]
        for item in ctgy.findall("./Itemlist/Item"):
            _import_item(item, section, new_path)
        for child in ctgy.findall("./BoQCtgy"):
            walk_ctgy(child, section, new_path)

    def _import_item(item: ET.Element, section: LVSection, path: list[str]):
        nonlocal ordering
        ordering += 1
        oz = _text(item, "OZ")
        number = oz.split(".")[-1] if oz else str(ordering)
        long_text = _text(item, "Description", "DescriptionText") or _text(
            item, "Description", "LongText"
        )
        LVItem.objects.create(
            section=section,
            number=number,
            oz=oz or ".".join([*path[1:], number]),
            short_text=_text(item, "Description", "ShortText"),
            long_text=long_text,
            menge=_decimal(_text(item, "Qty")),
            einheit=_text(item, "QU"),
            unit_price=_decimal(_text(item, "UP")),
            total_price=_decimal(_text(item, "IT")),
            source=LVItem.Source.GAEB,
            confidence=1.0,
            ordering=ordering,
        )

    top_ctgys = boq.findall("./BoQCtgy")
    if not top_ctgys and boq.find("./Itemlist") is not None:
        # flat BoQ without categories
        root_section = LVSection.objects.create(
            lv=lv, parent=None, kind=LVSection.Kind.LV,
            number=lv.number or "1", title=lv.gewerk, ordering=1,
        )
        for item in boq.findall("./Itemlist/Item"):
            _import_item(item, root_section, [root_section.number])
    for ctgy in top_ctgys:
        walk_ctgy(ctgy, None, [])

    document.extraction_report = {
        "importer": "gaeb_xml",
        "item_count": LVItem.objects.filter(section__lv=lv).count(),
        "section_count": lv.sections.count(),
    }
    return lv
