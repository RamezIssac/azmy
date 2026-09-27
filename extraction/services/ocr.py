"""Vision-LLM OCR: render scanned pages → vision model → text.

No system OCR deps (no tesseract): pypdfium2 renders pages to PNG, a
vision-capable OpenRouter model transcribes them. Results are cached in a
sidecar JSON next to the source file, so re-runs resume after interrupts
and rate-limit backoffs.
"""

from __future__ import annotations

import base64
import io
import json
import logging
from pathlib import Path

import pypdfium2 as pdfium
from django.conf import settings

from . import llm
from .pdf_text import PageText, PdfContent

logger = logging.getLogger(__name__)

OCR_PROMPT = (
    "Dies ist eine Seite aus einem deutschen Baudokument (Ausschreibung, "
    "Bericht, Plan oder Ausweis). Transkribiere den Seiteninhalt vollständig "
    "und wörtlich auf Deutsch. Tabellen als einfachen Text mit Spalten. "
    "Bei Plänen/Zeichnungen: beschreibe was zu sehen ist und transkribiere "
    "alle Beschriftungen, Maße und Legenden. Keine Kommentare, nur Inhalt."
)

OCR_SCALE = 2.0  # ~144 dpi — enough for 10pt text, cheap on tokens


def _ocr_cache_path(document) -> Path:
    return Path(document.file.path + ".ocr.json")


def _load_cache(document) -> dict:
    path = _ocr_cache_path(document)
    if path.exists():
        try:
            # empty strings are failed attempts — never sticky
            return {k: v for k, v in json.loads(path.read_text()).items() if v.strip()}
        except json.JSONDecodeError:
            return {}
    return {}


def _save_cache(document, cache: dict):
    _ocr_cache_path(document).write_text(json.dumps(cache))


def transcribe_page(png_bytes: bytes) -> str:
    """One page image → text. Returns '' on failure (caller continues)."""
    b64 = base64.b64encode(png_bytes).decode()
    result = llm.chat(
        settings.OPENROUTER_MODEL_OCR,
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": OCR_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                ],
            }
        ],
        json_mode=False,
    )
    return (result or {}).get("text", "").strip()


def ocr_document(document, max_pages: int | None = None) -> PdfContent:
    """OCR a scanned document, page by page, with resume caching.

    Returns a PdfContent whose pages carry OCR'd text (unOCR'd pages keep
    whatever the text layer had — often nothing).
    """
    base = None
    # keep the native text layer where it exists
    from .pdf_text import read_pdf

    base = read_pdf(document.file.path)
    limit = max_pages or int(getattr(settings, "OPENROUTER_OCR_MAX_PAGES", 80))
    cache = _load_cache(document)

    pdf = pdfium.PdfDocument(document.file.path)
    done = 0
    try:
        for i in range(min(len(pdf), limit)):
            key = str(i + 1)
            native = base.pages[i].text if i < len(base.pages) else ""
            if len(native.strip()) > 20:
                continue  # page already has text
            if key not in cache:
                page = pdf[i]
                try:
                    png = page.render(scale=OCR_SCALE).to_pil()
                    buf = io.BytesIO()
                    png.save(buf, format="PNG", optimize=True)
                finally:
                    page.close()
                text = transcribe_page(buf.getvalue())
                if text:  # only successful pages are cached (failures retry next run)
                    cache[key] = text
                    _save_cache(document, cache)
                    done += 1
                    logger.info("OCR %s page %d: %d chars", document.pk, i + 1, len(text))
                else:
                    logger.warning("OCR %s page %d: no text (rate limit?)", document.pk, i + 1)
    finally:
        pdf.close()

    pages = []
    for i, page in enumerate(base.pages):
        ocr_text = cache.get(str(i + 1), "")
        text = page.text if len(page.text.strip()) > 20 else ocr_text
        pages.append(PageText(number=page.number, text=text))
    content = PdfContent(page_count=base.page_count, pages=pages)
    content.ocr_applied = bool(cache)  # type: ignore[attr-defined]
    return content
