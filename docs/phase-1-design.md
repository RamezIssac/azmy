# Phase 1 Design — Living Spec

Status: **agreed baseline** (2026-09-26). Update as decisions evolve; major changes get a
dated entry in `docs/brainstorms/`.

## Scope

Internal tool: we upload a construction project's documents → pipeline extracts a
structured, coded **Leistungsverzeichnis (LV)** → human review/approve → published as
shareable read link + read-only JSON API.

Single-tenant. German market first (VOB / DIN 276 / GAEB vocabulary).

## Locked decisions

- Internal uploads only; internal review (polished UI and/or second LLM as judge).
- Accept all document types; only the LV is item-extracted. Plans/specs are stored and
  RAG-indexed (future `ask_question`).
- GAEB import (X83/X31…) in v1 → also serves as extraction accuracy benchmark.
- Scanned PDFs (no text layer) → manual-processing queue, no OCR in v1.
- Human-gated publish: nothing goes live without explicit approval.
- LLM access via **OpenRouter**; per-task model assignment decided later.
- Publish = shareable read link + read-only JSON API (the future MCP server's base).
- DocumentSet versioning: store versions, no diffing yet.
- Prices: extract EP/GP when present (often empty on bidder copies).

## Flow

```
UPLOAD            EXTRACT                    JUDGE (optional)         REVIEW               PUBLISH
┌───────────┐   ┌────────────────────┐    ┌──────────────────┐    ┌───────────────┐   ┌──────────────────┐
│ staff     │   │ 1. page triage     │    │ 2nd LLM critiques│    │ side-by-side  │   │ human approval   │
│ uploads   │──▶│ 2. text-layer parse│──▶│ extraction,      │──▶│ PDF ↔ tree,   │──▶│ → read link +    │
│ 1..n files│   │ 3. LLM → LV tree   │    │ proposes fixes   │    │ inline edit   │   │ read-only API    │
│           │   │    + confidence    │    │                  │    │               │   │                  │
└───────────┘   └────────────────────┘    └──────────────────┘    └───────────────┘   └──────────────────┘
                     │ no text layer
                     ▼
               manual-processing queue
```

## Data model (target)

```
Project            (name, address, Bauherr/client, architect, deadlines, source)
DocumentSet        (project FK, version, uploaded_by, created_at)   ← addenda = new set
Document           (set FK, file, doc_type [lv|plan|spec|other], status, page_count)
  └─ status: uploaded → processing → extracted|manual_queue → reviewed
LV                 (document FK, gewerk, title)
LVSection          (lv FK, parent self-FK, position/ordering, title)  ← Titel/Untertitel tree
LVItem (Position)  (section FK, oz, short_text, long_text, menge, einheit,
                    einheitspreis, gesamtpreis, din276_group, confidence,
                    page_refs [JSON], source [pdf|gaeb|manual])
```

Every extracted field carries provenance: page refs (+ later bbox) into the source PDF.

## Extraction pipeline tasks

1. **Triage** — classify each page (cover / TOC / ZTV-text / LV-table / drawing / scan).
2. **Text-layer parse** — deterministic extraction of the LV position tables
   (regular structure: OZ, Bezeichnung, Menge, ME, EP, GP).
3. **LLM structuring** — section tree, short/long text split, DIN 276 cost-group coding,
   cover-page metadata (Bauherr, Termine, Abgabeort, contacts).
4. **Confidence + provenance** per item; low-confidence items flagged for review.
5. **Judge pass (optional toggle)** — second LLM reviews extraction against source text.
6. **GAEB importer** — parse X83/X31 into the same LV tree; diff-report vs PDF extraction.

## Review UI

- Split view: source PDF page (left) ↔ extracted tree (right), item ↔ page-region linked.
- Confidence heatmap / filter ("show me everything < 0.9").
- Inline edit of any field; bulk accept; edit log (feeds eval dataset).
- Approve → publish. No approval, no publish.

## Publish surface (v1)

- Shareable read link per project (tokenized URL, no login).
- Read-only JSON API: projects, LV tree, items (+ OpenAPI schema).
- This exact API gets wrapped by the MCP server in Phase 2.

## Out of scope (Phase 1)

OCR for scans, drawing takeoff, multi-tenancy, provider accounts, bid submission,
addenda diffing, GC portal monitoring (post-v1).

## Open / next

- [ ] Pick per-task OpenRouter models (structuring, judge, embeddings).
- [ ] GAEB X83 sample file for the importer + benchmark.
- [ ] Scaffold `projects`/`extraction` Django apps; migrate.
- [ ] Review-UI stack decision (server-rendered + htmx fits house stack).
