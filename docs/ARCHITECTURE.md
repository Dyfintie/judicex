# Architecture

Judicex is a local-first Flask application backed by SQLite.

## Layers

- `judicex_memory_os/store.py`: SQLite schema, persistence, search, matter memory, chat sessions, settings.
- `judicex_memory_os/web_app.py`: Flask routes and JSON APIs.
- `judicex_memory_os/static/app.js`: browser UI, page navigation, chat, document/workflow/table/draft/settings actions.
- `judicex_memory_os/templates/index.html`: server-rendered shell.
- `judicex_memory_os/llm_provider.py`: provider abstraction for Ollama, OpenAI, Anthropic, OpenAI-compatible endpoints, and no-LLM mode.
- `judicex_memory_os/agent_runtime.py`: agentic runtime that calls memory, legal, matter, and composition tools.
- `judicex_memory_os/answering.py`: grounded answer pipeline and citation/contract enforcement.
- `judicex_memory_os/matter_analysis.py`: deterministic matter workflow analysis.
- `judicex_memory_os/tools.py`: local tool definitions and calls.
- `judicex_memory_os/cli.py`: command line interface.
- `judicex_memory_os/mcp_stdio.py`: MCP stdio server.

## Data Model

The core database is SQLite.

Important tables:

- `documents`, `document_versions`, `legal_atoms`
- `entities`, `edges`
- `matters`, `matter_documents`, `matter_facts`
- `matter_folders`, `matter_document_versions`
- `tabular_reviews`, `tabular_review_views`
- `custom_workflow_packs`, `custom_workflow_versions`
- `custom_draft_templates`
- `chat_sessions`, `chat_messages`
- `agent_memories`
- `app_settings`
- `answer_audit`, `llm_cache`

Judicex keeps two memory layers separate:

- Legal/source memory: `documents`, `document_versions`, `legal_atoms`, `entities`, and `edges`. This is used as legal evidence and can produce citations.
- Agent/operational memory: `agent_memories`. This stores preferences, decisions, lessons, and operational notes. It can guide how the agent works, but it is not cited as law.

## LLM Providers

The answer engine expects any client with:

```python
chat(model: str, messages: list[dict[str, str]], temperature: float = 0.0) -> str
```

`llm_provider.py` preserves that contract while routing to:

- Ollama local `/api/chat`
- OpenAI `/v1/chat/completions`
- Claude/Anthropic `/v1/messages`
- OpenAI-compatible `/v1/chat/completions`
- no-LLM mode

API keys are read from environment variables, not stored in the browser.

## Security Model

Judicex is currently designed for local use. It has no built-in user accounts, multi-user authorization, or hardened production deployment profile.

For public deployment, add:

- authentication
- authorization per matter
- HTTPS termination
- rate limiting
- upload scanning
- secret management
- backup/restore policy

## Local-First Principle

Private matter data stays in the local SQLite database and the local attachment directory unless the user explicitly sends prompts to a configured LLM provider.
