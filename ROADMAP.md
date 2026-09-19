# Roadmap

Judicex is built incrementally. The roadmap is a direction, not a
commitment — community PRs can pull items forward and operational reality
can push them back.

The guiding principle: **every release should make the answer contract
stronger or expand the verticals it can serve, not just polish the UI.**

## v0.2.0-alpha — current

Local-first Legal Memory OS with the core surface in place:

- Flask + SQLite local application
- Dedicated sidebar pages (Dashboard, Documents, Workflow, Tables, Drafts,
  Tools, Memory, Sources, Settings, Security, Backup)
- Provider abstraction (Ollama / OpenAI / Anthropic / OpenAI-compatible /
  no-LLM)
- Persisted, deletable chat sessions
- Two-tier memory (legal vs. agent)
- Grounded answer engine with `grounded` / `limited` / `abstain` / `chat`
  states, JSON-validated, citations bound to retrieved evidence
- Matter analysis with versioned JSON workflow packs
- Tabular review with editable cells, saved views and CSV/XLSX/DOCX export
- **Split-view drafting page** (instruction column + Word-style live preview)
- Local password gate, backup, restore, optional matter encryption
- MCP stdio server and CLI utilities

## v0.3.0 — drafting & review polish

- Better PDF viewer with page thumbnails and annotation coordinates
- OCR setup guide and isolated `ocr` extras group
- Demo pack import/export
- More deterministic API tests (replace ad-hoc fixtures with golden files)
- Browser regression tests for the core pages (chat, drafts, tables)

## v0.4.0 — editor & template depth

- Rich text document editor with track-changes
- Side-by-side version comparison UI
- Accept / reject suggestions
- Better draft template builder with field validation and conditional blocks
- Structured workflow templates (per-step inputs, evidence binding)

## v0.5.0 — packaging & private deployment

- Desktop packaging investigation (Tauri or native bundling)
- Backup/restore flow with off-host targets
- Optional auth layer for private server deployment (single-tenant)
- Provider-specific model discovery where the API supports it

## Later — opening up the verticals

These items unlock real-firm usage but require careful design and security
work:

- Multi-user workspace
- Role-based access control per matter
- Stronger audit export (signed, append-only)
- Plugin / tool marketplace model with a vetted-pack channel
- Hosted deployment blueprint (Postgres profile, container image,
  reference IaC)
- Verticals beyond civil/labor: penal, tax, family, IP, administrative,
  EU/EUR-Lex

## How to influence the roadmap

- Open a GitHub issue with the use case and the workflow you would build.
- For new verticals, contribute a workflow pack first — that grounds the
  discussion in something concrete.
- For larger items, open a draft PR with a `DESIGN.md` and we will iterate
  on it before any code lands.

## Non-goals

- Becoming a closed-source SaaS.
- Adding heavyweight frontend frameworks or build tooling.
- Encoding jurisdiction-specific legal logic in Python instead of workflow
  packs.
- Replacing professional judgment.
