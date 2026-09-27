# Phase 2 Design — multi-document intelligence + web bidding

Status: **2A + 2C BUILT AND DEPLOYED** (2026-09-27, azmy.raenterprises.de).
Remaining open item: publish gate requires an approved LV — document-only projects
(EOI phase) can't be published yet (product decision pending).

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
   transcribes → text flows into the same pipeline. No tesseract/system deps.
   Scans leave `manual_queue` history. **Model: free-tier via OpenRouter**
   (`OPENROUTER_MODEL_OCR`, default `google/gemini-2.0-flash-exp:free`).
2. **Auto-triage.** Upload without choosing a type: classify (LV? notice? plan? report?
   certificate?) via text heuristics + LLM `document_intel`, then route. Correct the
   uploader's choice when wrong (EOI-as-LV → notice).
3. **EOI/procedure extraction.** Notices like the Interessenbekundung carry deadlines,
   eligibility, contacts → structured `procedure` fields on Project (extends the
   Phase 1 metadata pass to non-LV docs).

~~RAG index~~ → **deferred to Phase 3** (review, 2026-09-27): position pages are
structured rows already — RAG adds value for narrative front matter + non-LV docs,
which matters once agents ask questions. Lives with the agent substrate.

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

## LLM routing (decided 2026-09-27)

**Fallback chains**, free tier first, paid backstop (comma-separated per setting).
Free tier 429s under shared load (observed live) — chain keeps the pipeline alive;
429s retried with backoff inside each model. Upgrade any task via env, no code change.

| Setting | Task | Default (free tier) |
|---|---|---|
| `OPENROUTER_MODEL_METADATA` | project/doc metadata | `qwen/qwen3.8-27b:free` |
| `OPENROUTER_MODEL_STRUCTURE` | DIN 276, structuring | `qwen/qwen3.8-27b:free` |
| `OPENROUTER_MODEL_OCR` | scan transcription (vision) | `google/gemma-4-31b-it:free` |
| `OPENROUTER_MODEL_JUDGE` | extraction audit | `qwen/qwen3.8-27b:free` |

Free tier is **rate-limited and occasionally 429s** — `llm.chat()` retries with
backoff, and every LLM step is failure-tolerant (skips rather than fails). Slugs were
picked from the live `/models` list on 2026-09-27; check availability before changing.

## Order of attack

1. Vision OCR (unblocks the 50% of real docs that are scans)
2. Provider accounts — **staff-created first** (agreed in review), self-signup later
3. Bid schema + provider bid form (web) + leveling view for staff

## Deferred to Phase 3

MCP server, provider API keys + scopes, webhooks/event feed, **RAG index + ask_question**,
provider reputation, GC portal monitoring.
