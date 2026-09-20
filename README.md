# Judicex

> Open-source **legal AI software** for evidence-grounded drafting, matter
> management and AI-assisted legal work — with an answer contract that
> fails closed instead of hallucinating.

[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Status: alpha](https://img.shields.io/badge/status-v0.2.0--alpha-orange.svg)](ROADMAP.md)

Judicex is a workspace for lawyers and legal teams. You can ingest official
sources and private matter files, run deterministic workflow checks,
generate drafts in a Word-style split-view editor, and chat with an LLM
whose answers are bound to the evidence in a SQLite knowledge base you
control.

The project ships with a Flask web UI, a CLI, and an MCP stdio server, and
talks to Ollama, OpenAI, Anthropic, OpenAI-compatible providers — or runs
with no LLM at all.

> **Open-source vs. cloud.** This repository is the open-source build of
> Judicex: install it on your laptop, on a workstation, or on a private
> server inside the firm. A managed cloud version with hosted multi-tenant
> deployment, SSO and audit features is on the roadmap as a separate
> offering; this codebase is and will remain Apache-2.0.

---

## Why Judicex

Most legal AI products today are either:

1. **Closed SaaS** that ship your client data to a vendor (Harvey, Legora, …), or
2. **Generic RAG demos** that paste retrieved chunks into a prompt and hope.

Judicex takes a different bet. In legal work, the value is not in the
prompt — it is in the **structured, verifiable evidence the answer stands
on**. So the codebase is organised around that idea:

- **Two evidence layers, never confused.**
  Legal sources (`documents`, `document_versions`, `legal_atoms`,
  `entities`, `edges`) are the only thing that can produce **citations**.
  Operational notes (`agent_memories`) store preferences, decisions and
  lessons — they shape *how* the agent works, but are never cited as law.
- **Versioned official sources.**
  Real ingestion from Normattiva with URN extraction, versioned over time
  (`effective_from` / `effective_to`) so you can ask “what did this article
  say on date X?” instead of pretending the law is timeless.
- **Answer contract that fails closed.**
  `answer_contract.py` + `numeric_verifier.py` + `confidence.py` enforce
  the states `grounded` / `limited` / `abstain` / `chat` with JSON-schema
  validation, citations bound to retrieved `document_id`s only, and
  temperature 0. If evidence is insufficient, Judicex abstains. It does
  not improvise.
- **Workflow packs as data.**
  Matter-analysis profiles (e.g. civil debt recovery, opposition to
  injunctions, generic file review) are JSON workflow packs, versioned and
  swappable per vertical / firm — not application logic.
- **You control where it runs.**
  SQLite, Flask, vanilla JS, no external build step. The same codebase
  runs on a single workstation or on a private server inside the firm.
  Matter data lives in the SQLite database and the attachment directory
  you point Judicex at — nothing leaves the host until **you** explicitly
  point a chat at a hosted LLM.

This repository is `v0.2.0-alpha`: a usable prototype, not production SaaS.

## Features

**Sources & evidence**

- Local SQLite knowledge base with versioned document history and legal
  atoms.
- One-click import of official source bundles (Normattiva-driven).
- Two-tier evidence model: legal sources (citable) and operational notes
  (style and decisions).

**Matters & files**

- Private matters, folders, versioned matter documents.
- Upload PDF, DOCX, text, markdown, CSV, JSON, images.
- PDF / image preview, stored-text viewer, OCR via Ollama.
- Matter facts, timelines, parties, amounts and deadlines extracted
  deterministically.

**Workflows & analysis**

- `matter_analysis` against a thesis: explicit proof profile, present /
  partial / missing elements, next actions.
- Built-in workflow packs and a custom workflow builder.
- Tabular review with editable cells, filtering, sorting, saved views and
  CSV / XLSX / DOCX export.

**Drafting**

- Built-in templates plus a custom template editor.
- **Split-view drafting page** (Claude- / ChatGPT-artifact style):
  instruction column on the left, live Word-style document preview on the
  right.
- Generate, save into the matter, copy, export to DOCX / PDF.

**AI surface**

- Persisted chat sessions (sidebar, deletable).
- Multi-provider: Ollama, OpenAI, Anthropic, OpenAI-compatible, no-LLM.
- Grounded answer engine with citations bound to evidence.
- MCP stdio server for integration with MCP-aware clients.
- CLI utilities (`judicex`, `judicex-mcp`, `judicex-agent`, `judicex-web`).

**Privacy & ops**

- Local password gate, backup and restore, optional matter-file
  encryption.
- API keys stay in `.env` / shell, never in the browser.

## Screenshots

> Drop PNGs into `docs/screenshots/` and reference them here once you
> publish: `docs/screenshots/drafts-split-view.png`,
> `docs/screenshots/matter-analysis.png`, etc. They are intentionally not
> committed yet — the repository is currently text-only to keep diffs clean.

## Architecture at a glance

```
┌──────────────────────────────┐    ┌──────────────────────────────┐
│  Web UI (Flask + vanilla JS) │    │  CLI / MCP stdio / Agent     │
└──────────────┬───────────────┘    └──────────────┬───────────────┘
               │                                   │
               ▼                                   ▼
        ┌─────────────────────────────────────────────────┐
        │            agent_runtime + answering            │
        │  intent router → tools → answer_contract → out  │
        └────────────┬───────────────────────┬────────────┘
                     │                       │
                     ▼                       ▼
        ┌──────────────────────┐  ┌────────────────────────┐
        │  llm_provider.py     │  │  store.py (SQLite)     │
        │  ollama / openai /   │  │  documents, atoms,     │
        │  anthropic / oai-c / │  │  entities, edges,      │
        │  none                │  │  matters, agent notes  │
        └──────────────────────┘  └────────────────────────┘
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full layer
description and database tables, and
[docs/JUDICEX_PRODUCT_STRATEGY.md](docs/JUDICEX_PRODUCT_STRATEGY.md) for
the product thesis.

## Quick start

```bash
git clone https://github.com/JustVugg/judicex.git
cd judicex
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[crypto]"
cp .env.example .env

judicex init-db --db ./memory.db
judicex web --db ./memory.db --area civile --port 5051
```

Then open <http://127.0.0.1:5051>.

For OCR on scanned PDFs:

```bash
pip install -e ".[crypto,ocr]"
```

## AI provider setup

Judicex reads provider settings from the in-app **Settings** page and from
environment variables. API keys are kept out of the frontend on purpose.

**Local Ollama** (default, fully offline):

```bash
ollama serve
ollama pull qwen2.5:7b
```

```env
JUDICEX_LLM_PROVIDER=ollama
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:7b
JUDICEX_OCR_MODEL=glm-5:cloud
```

**OpenAI:**

```env
JUDICEX_LLM_PROVIDER=openai
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4.1-mini
```

**Anthropic / Claude:**

```env
JUDICEX_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=...
ANTHROPIC_MODEL=claude-3-5-sonnet-latest
```

**OpenAI-compatible** (LocalAI, vLLM, hosted compatible APIs):

```env
JUDICEX_LLM_PROVIDER=openai_compatible
OPENAI_COMPATIBLE_API_KEY=...
OPENAI_COMPATIBLE_BASE_URL=http://127.0.0.1:8000/v1
OPENAI_COMPATIBLE_MODEL=local-model
```

**No-LLM mode** also works: deterministic matter analysis, draft templates,
search and audit still run.

## Demo & CLI

Synthetic demo database:

```bash
python scripts/create_demo.py --db ./memory.demo.db
judicex web --db ./memory.demo.db --area civile --port 5051
```

CLI examples:

```bash
judicex matter-create   --db ./memory.db --title "Recupero credito Beta" \
                        --client-name "Alfa S.r.l." --area civile
judicex matter-add-doc  --db ./memory.db --matter-id "matter:..." \
                        --file ./examples/demo_matter.md --kind memo
judicex matter-context  --db ./memory.db --matter-id "matter:..." \
                        --query "fattura pagamento"
judicex list-workflow-packs --db ./memory.db
judicex matter-analyze  --db ./memory.db --matter-id "matter:..." \
                        --thesis "ricorso per decreto ingiuntivo"
judicex ask             --db ./memory.db --provider ollama --model qwen2.5:7b \
                        --area civile --matter-id "matter:..." \
                        --question "Che elementi mancano?"
```

Operational notes are separate from legal sources. Legal sources hold
statutes, official documents, legal atoms and citations; operational notes
hold how the assistant should work — preferences, decisions, lessons,
recurring strategies, and matter-specific notes.

```bash
judicex memory-add    --db ./memory.db --kind preference \
                      --title "Stile recupero crediti" \
                      --content "Per recupero crediti B2B usa tono pratico." \
                      --tag recupero_crediti --importance 0.9
judicex memory-search --db ./memory.db --query "recupero crediti"
```

## Self-host or cloud — your call

The open-source build is designed to run wherever you install it:

- On a single workstation, with a local LLM via Ollama, for a sole
  practitioner who wants zero recurring cost.
- On a private server inside the firm, behind a real WSGI stack, VPN and
  backups (see [SECURITY.md](SECURITY.md) for the hardening checklist).
- On any cloud you operate yourself — the codebase has no hard dependency
  on a specific provider.

A managed cloud version of Judicex (multi-tenant, SSO, hosted upgrades) is
on the roadmap as a separate offering. This repository remains
Apache-2.0; the cloud product is built on top of it, not in place of it.

## Project layout

```
judicex/
├── judicex_memory_os/        # Python package (engine, store, agent, web)
│   ├── store.py              # SQLite schema, persistence, search
│   ├── web_app.py            # Flask routes & JSON APIs
│   ├── agent_runtime.py      # tool-calling agent loop
│   ├── answering.py          # grounded answer pipeline
│   ├── answer_contract.py    # claim/citation/numeric validation
│   ├── matter_analysis.py    # deterministic matter workflow analysis
│   ├── llm_provider.py       # Ollama / OpenAI / Anthropic / compatible
│   ├── mcp_stdio.py          # MCP stdio server entry point
│   ├── cli.py                # `judicex` CLI
│   ├── workflow_packs/       # JSON workflow packs
│   ├── templates/            # Flask + draft templates
│   └── static/               # Vanilla JS UI
├── tests/                    # unittest suite
├── benchmarks/               # public benchmark fixtures
├── docs/                     # architecture, strategy, installers
└── scripts/                  # dev / test / installer / demo helpers
```

The Python package is named `judicex_memory_os` for historical reasons; the
product is just **Judicex**.

## Development

For local development, install the package in editable mode and run the
standard test script. The tests use Python's built-in `unittest`; no pytest
dependency is required.

```bash
pip install -e ".[crypto,test]"
scripts/dev.sh
scripts/test.sh
python scripts/run_public_benchmark.py --db ./memory.benchmark.db
```

The web UI is server-rendered Flask plus static JavaScript. There is **no
TypeScript, Next.js, Supabase or external frontend build step** — and there
is no plan to add one. Contributions that require one will be politely
declined.

## Simple local installers

- Windows: `powershell -ExecutionPolicy Bypass -File .\scripts\install_windows.ps1`
- macOS: `bash scripts/install_macos.sh`

See [docs/INSTALLERS.md](docs/INSTALLERS.md).

## Repository hygiene before publishing

The included `.gitignore` excludes the things that *must not* end up on
GitHub. Before your first push, double-check that none of these are
tracked:

- `.env`
- `memory.db` and any other `*.db` / `*.sqlite*` files
- `memory_files/`, `uploads/`, `private/`
- API keys, real client documents, screenshots with private data

A pre-publish checklist is documented in [SECURITY.md](SECURITY.md).

## Roadmap

See [ROADMAP.md](ROADMAP.md). Highlights:

- Better PDF viewer with page thumbnails and annotation coordinates (`v0.3`)
- Rich document editor with version diff and accept/reject (`v0.4`)
- Optional auth layer + desktop packaging (`v0.5`)
- Multi-user workspace + RBAC + audit export (later)

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). The
general rules:

- Keep the stack Flask / Python / HTML / JavaScript / SQLite.
- Never commit private legal documents, real databases, uploads or API
  keys.
- Add or update tests for changes touching API behavior, persistence or
  workflows.
- Keep provider integrations behind `llm_provider.py`.

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
Apache-2.0 was chosen because it is permissive **and** includes an
explicit patent grant, which matters for a domain that intersects
regulated work.

## Disclaimer

Judicex is a software assistant for legal drafting, document organization
and evidence-grounded answering. **It does not provide legal advice and
does not replace a qualified legal professional.** Outputs may be
incomplete, incorrect, outdated or unsuitable for a specific
jurisdiction. See [DISCLAIMER.md](DISCLAIMER.md).

## Security

To report a vulnerability, please follow [SECURITY.md](SECURITY.md). Do
not open public issues with exploit details.

---

If you build something on top of Judicex — a vertical pack for criminal
law, a richer drafting UI, an integration with case-management software —
please open an issue or a PR. The point of an open-source legal AI is that
the verticals are built in the open, not behind a sales NDA.
