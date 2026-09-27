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


def classify_document(content, filename: str) -> str:
    """Auto-triage: decide the doc type from filename hints + text content."""
    name = filename.lower()
    if name.endswith((".x83", ".x31", ".xml")):
        return Document.DocType.GAEB
    if content.positions_pages:
        return Document.DocType.LV
    if any(k in name for k in ("grundriss", "schnitt", "plan", "zeichnung", "ansicht")):
        return Document.DocType.PLAN
    if content.text_coverage > 0:
        return Document.DocType.SPEC
    return Document.DocType.PLAN  # no text at all: most likely drawings


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
        else:
            content = read_pdf(document.file.path)
            document.page_count = content.page_count
            document.text_layer_ok = content.text_layer_ok

            # triage before OCR when text exists; after OCR when it doesn't
            if document.doc_type == Document.DocType.AUTO and content.text_coverage > 0:
                document.doc_type = classify_document(content, document.original_filename)
                document.extraction_report["auto_classified_as"] = document.doc_type
                document.save(update_fields=["doc_type", "extraction_report", "updated_at"])

            if document.doc_type == Document.DocType.GAEB:
                from .gaeb_import import import_gaeb

                import_gaeb(document)
            else:
                if content.text_coverage == 0:
                    content = _ensure_text(document, content)
                    if content is None:
                        return document  # manual queue already set
                    if document.doc_type == Document.DocType.AUTO:
                        document.doc_type = classify_document(
                            content, document.original_filename
                        )
                        document.extraction_report["auto_classified_as"] = document.doc_type
                        document.save(
                            update_fields=["doc_type", "extraction_report", "updated_at"]
                        )
                if document.doc_type == Document.DocType.LV:
                    _extract_lv(document, content)
                    if document.status != Document.Status.PROCESSING:
                        return document  # routed to manual queue inside
                else:
                    _extract_narrative(document, content)

        lv = getattr(document, "lv", None)
        if lv is not None:
            meta = lv_extract_meta = None
        if document.doc_type == Document.DocType.LV and hasattr(document, "lv"):
            # LLM: project metadata + DIN 276 + judge (all failure-tolerant)
            meta = llm.extract_project_metadata(read_pdf(document.file.path).text_through(8))
            if meta:
                _apply_metadata(document, meta)
            din = llm.suggest_din276(document.lv)
            if din:
                document.lv.din276_group = din
                document.lv.save(update_fields=["din276_group"])

        if document.run_judge and hasattr(document, "lv"):
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


def _ensure_text(document: Document, content):
    """OCR fallback when the text layer is empty. None → manual queue set."""
    from django.conf import settings

    if content.text_coverage > 0:
        return content
    max_pages = getattr(settings, "OPENROUTER_OCR_MAX_PAGES", 80)
    if content.page_count > max_pages:
        document.status = Document.Status.MANUAL_QUEUE
        document.extraction_report = {
            "reason": f"scan with {content.page_count} pages > OCR limit {max_pages}",
        }
        document.save()
        return None
    from .ocr import ocr_document

    ocr_content = ocr_document(document)
    if ocr_content.text_coverage == 0:
        document.status = Document.Status.MANUAL_QUEUE
        document.extraction_report = {"reason": "OCR produced no text"}
        document.save()
        return None
    document.extraction_report["ocr"] = True
    document.save(update_fields=["extraction_report", "updated_at"])
    return ocr_content


def _extract_lv(document: Document, content):
    parsed = parse_lv_pages(content.pages)
    if not parsed.items:
        document.status = Document.Status.MANUAL_QUEUE
        document.extraction_report = {
            "reason": "no LV position table detected (not an LV?)",
            "text_coverage": round(content.text_coverage, 3),
        }
        document.save()
        return
    lv = persist_parsed_lv(document, parsed, source=LVItem.Source.PDF)
    document.extraction_report.update(parsed.report)
    document.save(update_fields=["extraction_report", "updated_at"])


def _extract_narrative(document: Document, content):
    from . import llm

    intel = llm.summarize_document(content.text_through(6))
    if intel:
        document.extraction_report["document_intel"] = intel
        _apply_procedure_facts(document, intel)
    document.save(update_fields=["extraction_report", "updated_at"])


def _apply_procedure_facts(document: Document, intel: dict):
    """EOI/notice deadlines land on the project (empty fields only)."""
    from datetime import datetime

    facts = intel.get("key_facts") or {}
    project = document.document_set.project
    raw = (facts.get("procedure_deadline") or "").strip()
    if raw and not project.bid_deadline:
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            project.bid_deadline = dt
            project.save(update_fields=["bid_deadline", "updated_at"])
        except ValueError:
            pass


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
