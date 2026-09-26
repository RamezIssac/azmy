# Phase 2 Design — multi-document intelligence + web bidding

Status: **scope locked** (2026-09-27). Builds on `phase-1-design.md`.

**Scope decision (Ramez, 2026-09-27): Phase 2 = 2A + 2C (web only).**
The agent substrate (2B: MCP server, API keys, webhooks) moves to Phase 3.
Bids in Phase 2 are submitted through the provider **web portal** (allauth accounts),
not by agents — but the bid schema is designed agent-compatible from day one, so
`submit_bid` later is a thin wrapper.

## What Phase 2 is (recap + learned)

Original phasing table: **Provider portal + API keys + MCP server + structured bid
submission.** The first real multi-document project (Haus der Gesundheit: EOI notice +
plans + energy certificate + 65-page scanned fire report) taught us:

- Real projects are **document sets**, not single LVs. 2 of 4 sample docs are **scans**.
- Providers don't only need the BOQ: they need to *ask questions against every document*
  (plans, reports, certificates). That is our `ask_question` MCP tool — it needs RAG
  over the whole set, and OCR for scans.

So Phase 2 = **2A multi-document intelligence → 2B agent substrate → 2C structured bids**.

## 2A — Multi-document intelligence

1. **Vision-LLM OCR for scans.** pypdfium2 renders pages to images → vision model
   (gemini-2.5-flash vision via OpenRouter) transcribes → text flows into the same
   pipeline. No tesseract/system deps. Scans leave `manual_queue` history.
2. **Auto-triage.** Upload without choosing a type: classify (LV? notice? plan? report?
   certificate?) via text heuristics + LLM `document_intel`, then route. Correct the
   uploader's choice when wrong (EOI-as-LV → notice).
3. **RAG index over all stored docs.** Chunk + embed text (incl. OCR output), store
   embeddings (Postgres; decide: pgvector extension on rasystem26 vs. numpy cosine at
   this scale — **decision pending**, default numpy to avoid server changes).
4. **EOI/procedure extraction.** Notices like the Interessenbekundung carry deadlines,
   eligibility, contacts → structured `procedure` fields on Project (extends the
   Phase 1 metadata pass to non-LV docs).

## 2B — Agent substrate (the differentiator)

1. **Provider accounts + API keys.** `Provider` model (trade codes, regions, contact),
   hashed API keys with scopes (`read`, `bid`), per-key rate limits, full audit log.
2. **Expanded read API v1.** `/projects` list (published), project detail incl.
   documents + `document_intel`, LV tree, item detail. Token-link API from Phase 1
   stays; keys add tracking and revocation.
3. **MCP server** (the headline): tools `search_projects`, `get_boq`, `get_item_detail`,
   `ask_question` (RAG with page citations), `submit_bid`. Deployed alongside Daphne.
4. **Events.** Webhook per provider: `project.published`, `documentset.added`.
   v1: polling-friendly `?since=` feed if webhooks are flaky.

## 2C — Structured bids

1. `Bid` + `BidItem` models: bids reference LVItems by OZ; prices per item; status
   (draft/submitted/withdrawn/awarded/rejected).
2. Submission via API/MCP (`submit_bid`) + a clean provider web form (same schema).
3. **Leveling view** for the GC: normalized side-by-side per section, outliers and
   scope gaps (9 of 12 items priced) flagged automatically. This is the moment the
   schema ownership pays off.

## Explicitly still out

Drawing takeoff (measurement off plans), negotiations/award workflow, multi-tenancy,
provider reputation, GC portal monitoring, payments.

## Order of attack

1. Vision OCR (unblocks the 50% of real docs that are scans)
2. Provider accounts (allauth) + provider profile (trade codes, regions)
3. Bid schema + provider bid form (web) + leveling view for staff
4. RAG index over all docs (powers staff Q&A now, `ask_question` in Phase 3)

## Deferred to Phase 3

MCP server, provider API keys + scopes, webhooks/event feed, provider reputation,
GC portal monitoring.
