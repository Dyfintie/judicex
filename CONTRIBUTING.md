# Contributing to Judicex

Thanks for considering a contribution. Judicex is an open-source legal
memory OS built on the assumption that the verticals (civil, labor,
constitutional, criminal, tax, …) are best built in the open by people who
practice the law — not behind a SaaS NDA.

This document explains how to set up the project, what kind of changes are
welcome, and the few rules we keep strict.

## Code of conduct

Be respectful, especially toward people from other jurisdictions and other
practice areas. Legal terminology that is obvious in one country can be
misleading in another; assume good faith and ask before correcting.

## Development setup

```bash
git clone https://github.com/<your-fork>/judicex-memory-os.git
cd judicex-memory-os
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[crypto,test]"
cp .env.example .env

scripts/test.sh
scripts/dev.sh
```

The web UI is at <http://127.0.0.1:5051>.

## Project rules

These are deliberate constraints, not accidents. Please respect them in PRs:

- **Stack:** Flask, Python, HTML, vanilla JavaScript, SQLite. No TypeScript,
  no Next.js, no Supabase, no external frontend build step.
- **Do not commit** `.env`, real databases, private legal documents, uploads,
  API keys, real client data, or screenshots that contain private data.
- **Provider integrations** stay behind `judicex_memory_os/llm_provider.py`.
  Never call provider SDKs directly from `web_app.py`, `agent_runtime.py`,
  `answering.py` or any other module.
- **Memory layers stay separate.** Anything user-written (preferences,
  decisions, lessons) goes into `agent_memories`. Anything cite-able as law
  goes into `documents` / `legal_atoms` / `entities` / `edges`. PRs that
  blur this boundary will be asked to refactor.
- **Workflow logic is data, not code.** New matter-analysis profiles ship as
  JSON workflow packs in `judicex_memory_os/workflow_packs/`. Do not encode
  legal requirements in Python conditionals.
- **Answer contract is sacred.** Changes to `answer_contract.py`,
  `numeric_verifier.py`, `confidence.py` or `answering.py` need a regression
  test under `tests/` — the contract exists precisely so we catch regressions
  before users do.
- **Tests required** for any change that touches API behavior, persistence,
  workflow packs or the answer pipeline.

## What contributions are welcome

- New workflow packs for additional verticals (penal, tax, family, IP, …).
- Source ingestors for additional official corpora (EUR-Lex, BOE, JORF,
  CURIA, BGH, etc.) — keep each ingestor self-contained.
- Bug fixes with a regression test.
- Performance improvements with a benchmark.
- Documentation in any language users actually speak.
- UI/UX improvements that respect the “no frontend build step” rule.

## What is **not** in scope

- Closed-source plugins or paywalled features in this repo.
- Adding heavyweight frameworks (React, Next.js, Vue) or build tooling.
- Switching the database away from SQLite for the local-first profile.
  (A separate Postgres profile for self-hosted multi-user deployment is on
  the roadmap and tracked there.)
- Hardcoding legal rules in Python instead of workflow packs.

## Pull request checklist

Before opening a PR:

- [ ] `scripts/test.sh` passes locally
- [ ] New tests cover the change
- [ ] No `.env`, `*.db`, `memory_files/`, uploaded files, or API keys are
      staged (`git status` to confirm)
- [ ] Schema changes include a migration note in the PR description
- [ ] UI changes include a screenshot **without** any private data
- [ ] You have read [SECURITY.md](SECURITY.md) if your change touches the
      answer contract, file uploads or any external network call

A good PR description answers:

1. What changes, in one sentence.
2. Why — the user-facing motivation, not the implementation detail.
3. How to test, with a concrete command or click path.

## Reporting bugs

Open a GitHub issue with:

- Judicex version (`pip show judicex-memory-os`)
- Python version and OS
- The smallest reproduction you can produce
- Whether private data is involved (do not paste it; describe its shape)

For security issues, follow [SECURITY.md](SECURITY.md) instead.

## License of contributions

By contributing, you agree that your contribution is licensed under
Apache-2.0 — the same license as the rest of the repository.
