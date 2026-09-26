"""OpenRouter client + LLM tasks (metadata, DIN 276 coding, judge).

Everything here is failure-tolerant: no API key / network error / bad JSON
all degrade to empty results — the deterministic parser output stands alone.
"""

from __future__ import annotations

import json
import logging
import re

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(90.0, connect=15.0)


_FENCE_START = re.compile(r"^\s*```(?:json)?\s*")
_FENCE_END = re.compile(r"\s*```\s*$")


def parse_json_content(content: str) -> dict | None:
    """Tolerant JSON parsing of LLM output: fences, prose padding, whitespace."""
    text = (content or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = _FENCE_END.sub("", _FENCE_START.sub("", text))
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
    return None


def chat(model: str, messages: list[dict], json_mode: bool = True) -> dict | None:
    if not settings.OPENROUTER_API_KEY:
        logger.info("OPENROUTER_API_KEY not set — skipping LLM step")
        return None
    payload: dict = {"model": model, "messages": messages, "temperature": 0}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    try:
        resp = httpx.post(
            f"{settings.OPENROUTER_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://azmy.raenterprises.de",
                "X-Title": "azmy bau_match",
            },
            json=payload,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        if not json_mode:
            return {"text": content}
        parsed = parse_json_content(content)
        if parsed is None:
            logger.warning(
                "LLM (%s) returned non-JSON content: %r", model, content[:200]
            )
        return parsed
    except Exception as exc:  # noqa: BLE001
        logger.warning("OpenRouter call failed (%s): %s", model, exc)
        return None


def extract_project_metadata(front_text: str) -> dict:
    """Cover/front matter → structured project metadata."""
    if not front_text.strip():
        return {}
    result = chat(
        settings.OPENROUTER_MODEL_METADATA,
        [
            {
                "role": "system",
                "content": (
                    "Du analysierst deutsche Ausschreibungsunterlagen (Leistungsverzeichnisse). "
                    "Extrahiere Projektdaten als JSON mit exakt diesen Schlüsseln "
                    "(leerer String wenn unbekannt): project_name, address, client_name "
                    "(Bauherr/Auftraggeber), architect (Planung), submission_place "
                    "(Abgabeort), execution_period (Termine/Ausführung), lv_title, gewerk."
                ),
            },
            {"role": "user", "content": front_text[:12000]},
        ],
    )
    return result or {}


DIN276_GROUPS = (
    "100 Grundstück, 200 Herrichten+Erschließen, 300 Bauwerk-Baukonstruktion, "
    "310 Baugrube, 320 Gründung, 330 Außenwände, 340 Innenwände, 350 Decken/Dächer, "
    "360 Baukonstruktionseinbauten, 370 Elemente, 380 Dach, 390 Ausbau, "
    "400 Bauwerk-Technische Anlagen, 500 Außenanlagen, 600 Ausstattung, 700 Baunebenkosten"
)


def suggest_din276(lv) -> str:
    """Assign a DIN 276 cost group to the whole LV (trade-level coding)."""
    sections = ", ".join(s.title for s in lv.sections.all()[:30] if s.title)
    result = chat(
        settings.OPENROUTER_MODEL_STRUCTURE,
        [
            {
                "role": "system",
                "content": (
                    "Ordne ein Bau-Gewerk der DIN 276 Kostengruppe zu. "
                    f"Gruppen: {DIN276_GROUPS}. "
                    'Antworte als JSON: {"din276_group": "390"} — nur die Nummer.'
                ),
            },
            {
                "role": "user",
                "content": f"Gewerk: {lv.gewerk or lv.title}\nTitel: {sections}",
            },
        ],
    )
    group = (result or {}).get("din276_group", "")
    return "".join(ch for ch in str(group) if ch.isdigit())[:3]


def summarize_document(front_text: str) -> dict:
    """Classify and summarize a non-LV document (notice, report, certificate…).

    Returns {"document_kind": str, "title": str, "summary": str,
             "key_facts": {"deadlines": [...], "contact": str, "scope": str}}.
    """
    if not front_text.strip():
        return {}
    result = chat(
        settings.OPENROUTER_MODEL_METADATA,
        [
            {
                "role": "system",
                "content": (
                    "Du analysierst Dokumente aus deutschen Bau-Ausschreibungen. "
                    "Identifiziere das Dokument und fasse es zusammen. Antworte als JSON "
                    "mit exakt diesen Schlüsseln: document_kind (z.B. "
                    "Interessenbekundungsverfahren, Energieausweis, Brandschutzbericht, "
                    "Grundrisse, Baubeschreibung, Sonstiges), title, summary (2-3 Sätze), "
                    "key_facts: {deadlines: [Strings], contact: String, scope: String}."
                ),
            },
            {"role": "user", "content": front_text[:12000]},
        ],
    )
    return result or {}


def judge_extraction(document) -> dict:
    """Second LLM critiques the extraction against the source text.

    Samples a few items, checks them against their source pages, and returns
    {"ok": bool, "issues": [{"oz": ..., "problem": ...}], "summary": str}.
    """
    lv = getattr(document, "lv", None)
    if lv is None:
        return {}
    from extraction.models import LVItem

    items = list(
        LVItem.objects.filter(section__lv=lv)
        .order_by("ordering")
        .values("oz", "short_text", "menge", "einheit", "page_start")
    )
    if not items:
        return {}
    # sample up to 8 items spread across the LV
    step = max(1, len(items) // 8)
    sample = items[::step][:8]

    from .pdf_text import read_pdf

    content = read_pdf(document.file.path)
    excerpts = []
    for item in sample:
        page = item["page_start"] or 1
        text = content.pages[page - 1].text if page <= len(content.pages) else ""
        excerpts.append(
            f"--- Seite {page} (Position {item['oz']}) ---\n{text[:2500]}"
        )
    result = chat(
        settings.OPENROUTER_MODEL_JUDGE,
        [
            {
                "role": "system",
                "content": (
                    "Du prüfst die automatische Extraktion eines Leistungsverzeichnisses. "
                    "Vergleiche jede extrahierte Position mit dem Quelltext der Seite. "
                    "Prüfe: Kurztext korrekt? Menge und Einheit korrekt? "
                    'Antworte als JSON: {"ok": true/false, "issues": [{"oz": "...", '
                    '"problem": "..."}], "summary": "ein Satz"}.'
                ),
            },
            {
                "role": "user",
                "content": (
                    "Extrahierte Positionen:\n"
                    + json.dumps(sample, ensure_ascii=False, default=str)
                    + "\n\nQuelltext:\n"
                    + "\n".join(excerpts)
                ),
            },
        ],
    )
    return result or {}
