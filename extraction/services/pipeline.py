"""Persistence of parsed/ imported LVs + the extraction pipeline."""

from __future__ import annotations

from django.db import transaction

from extraction.models import LV, LVItem, LVSection
from projects.models import Document

from .lv_parser import ParsedLV, parse_lv_pages
from .pdf_text import read_pdf


@transaction.atomic
def persist_parsed_lv(document: Document, parsed: ParsedLV, source: str) -> LV:
    """Replace any existing extraction of this document with `parsed`."""
    LV.objects.filter(document=document).delete()
    lv = LV.objects.create(
        document=document, number=parsed.number, gewerk=parsed.gewerk
    )
    sections_by_path: dict[tuple, LVSection] = {}
    for sec in parsed.sections:
        parent = sections_by_path.get(sec.path[:-1]) if sec.path else None
        sections_by_path[sec.path] = LVSection.objects.create(
            lv=lv,
            parent=parent,
            kind=sec.kind,
            number=sec.number,
            title=sec.title,
            ordering=sec.ordering,
            page_start=sec.page_start,
        )
    for item in parsed.items:
        section = sections_by_path.get(item.section_path)
        if section is None:
            # orphan position — attach to the LV root
            section = sections_by_path.get((("lv", parsed.number),))
        if section is None:
            continue  # no LV root at all — should not happen
        LVItem.objects.create(
            section=section,
            number=item.number,
            oz=item.oz,
            short_text=item.short_text,
            long_text=item.long_text,
            menge=item.menge,
            einheit=item.einheit,
            unit_price=item.unit_price,
            total_price=item.total_price,
            confidence=item.confidence,
            page_start=item.page_start or None,
            page_end=item.page_end or None,
            source=source,
            notes="\n".join(item.notes),
            ordering=item.ordering,
        )
    return lv


def extract_document(document: Document) -> Document:
    """Full extraction flow for one document. Never raises — status reflects outcome."""
    from . import llm  # deferred: keeps parser usable without settings/httpx

    document.status = Document.Status.PROCESSING
    document.error_message = ""
    document.save(update_fields=["status", "error_message", "updated_at"])

    try:
        if document.doc_type == Document.DocType.GAEB:
            from .gaeb_import import import_gaeb

            import_gaeb(document)
        elif document.doc_type == Document.DocType.LV:
            content = read_pdf(document.file.path)
            document.page_count = content.page_count
            document.text_layer_ok = content.text_layer_ok
            if not content.text_layer_ok:
                document.status = Document.Status.MANUAL_QUEUE
                document.extraction_report = {"reason": "no usable text layer (scan?)"}
                document.save()
                return document
            parsed = parse_lv_pages(content.pages)
            lv = persist_parsed_lv(document, parsed, source=LVItem.Source.PDF)
            document.extraction_report = parsed.report
            # LLM: project metadata from cover/front matter (failure-tolerant)
            meta = llm.extract_project_metadata(content.text_through(8))
            if meta:
                _apply_metadata(document, meta)
            din = llm.suggest_din276(lv)
            if din:
                lv.din276_group = din
                lv.save(update_fields=["din276_group"])
        else:
            # plans/specs/other: stored for later RAG — nothing to extract yet
            document.status = Document.Status.EXTRACTED
            document.save()
            return document

        if document.run_judge:
            try:
                judge_notes = llm.judge_extraction(document)
            except Exception as exc:  # noqa: BLE001 — judge is advisory only
                judge_notes = {"ok": None, "error": f"{type(exc).__name__}: {exc}"}
            if judge_notes:
                document.extraction_report["judge"] = judge_notes

        document.status = Document.Status.EXTRACTED
        document.save()
    except Exception as exc:  # noqa: BLE001 — pipeline must not crash the worker
        document.status = Document.Status.FAILED
        document.error_message = f"{type(exc).__name__}: {exc}"
        document.save()
    return document


def _apply_metadata(document: Document, meta: dict):
    project = document.document_set.project
    mapping = {
        "address": "address",
        "client_name": "client_name",
        "architect": "architect",
        "submission_place": "submission_place",
        "execution_period": "execution_period",
    }
    changed = []
    for src, dst in mapping.items():
        value = (meta.get(src) or "").strip()
        if value and not getattr(project, dst):
            setattr(project, dst, value)
            changed.append(dst)
    name = (meta.get("project_name") or "").strip()
    if name and not project.name:
        project.name = name
        changed.append("name")
    if changed:
        project.save()
    if hasattr(document, "lv") and meta.get("lv_title"):
        document.lv.title = meta["lv_title"][:255]
        document.lv.save(update_fields=["title"])
    document.extraction_report["metadata"] = meta
