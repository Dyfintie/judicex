# Security policy

## Supported status

Judicex is currently `v0.2.0-alpha`, intended for local development and
private evaluation. There is no security guarantee for shared, multi-user or
internet-exposed deployments. Read this file carefully before doing anything
beyond local single-user usage.

## Reporting a vulnerability

**Do not** open a public GitHub issue with exploit details. Instead:

1. Open a minimal private report through the repository's GitHub Security
   Advisories tab, or contact the maintainer through the channel listed on
   the GitHub profile.
2. Include: affected version, reproduction steps, impact, and any logs that
   do **not** contain private legal data.
3. Expect an acknowledgement within a reasonable time. We will coordinate
   disclosure once a fix is available.

If the vulnerability puts real user data at risk, please err on the side of
private disclosure even if you are unsure whether it qualifies.

## Threat model

Judicex is designed for the following scenarios:

- A single lawyer or small team, running the app on a workstation or a
  private server inside the firm, against a local SQLite database.
- LLM calls go to **either** a local Ollama instance **or** a hosted
  provider (OpenAI / Anthropic / OpenAI-compatible) the operator has
  explicitly configured.

It is **not** designed for:

- Public, internet-exposed deployment.
- Multi-tenant SaaS hosting.
- Untrusted users sharing the same instance.
- Workloads with regulatory requirements that demand audited infrastructure
  (HIPAA, FINRA, etc.) without significant additional engineering.

## Pre-publish checklist (before pushing to GitHub)

This list is the difference between “publishing the code” and “publishing
your clients”. Run it once before your first push, and again before every
public push from a working repository.

- [ ] `git status` shows **no** `.env` and **no** `*.db` / `*.sqlite*` files
- [ ] `git ls-files | grep -E "(memory_files|uploads|private)/"` returns nothing
- [ ] `git ls-files | grep -E "\\.(pdf|docx|doc|jpg|jpeg|png|webp)$"` returns
      nothing **except** intentional sample files in `examples/` (review them
      one by one)
- [ ] `git log -p | grep -i -E "(api[_-]?key|secret|bearer|password)"` shows
      no real values (sample/placeholder strings are fine)
- [ ] `judicex_memory_os/` does not contain any matter-specific data
- [ ] No client name, real party name, real fiscal code or IBAN appears in
      tests, fixtures, or docs

If any of these fail, **stop**. Clean the repo (and the git history if
needed: `git filter-repo`) before publishing.

## Secrets handling

Never commit:

- `.env`, `.env.local`, `.env.production`
- API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_COMPATIBLE_API_KEY`)
- production databases or copies thereof
- private legal documents
- generated uploads under `memory_files/` or `uploads/`

API keys should live in environment variables only. The web UI never sends
them to the browser; settings stored in `app_settings` reference *which*
provider is configured, not the credentials themselves.

If you accidentally committed a secret:

1. Rotate the secret immediately at the provider.
2. Rewrite history with `git filter-repo` (or BFG) and force-push only after
   verifying no other contributors are mid-PR.
3. Notify any party who might have pulled the leaked commit.

## Deployment hardening

Do **not** expose the Flask development server directly to the internet. If
you want to share a Judicex instance inside your firm, you need at minimum:

- a real WSGI server (gunicorn / uwsgi) behind a reverse proxy
  (nginx / Caddy)
- HTTPS termination with a real certificate
- network-level access control (VPN or firewalled subnet)
- authentication in front of the app — Judicex's local password gate is
  *not* a multi-user auth system
- per-matter authorization if multiple users will share the instance
- rate limiting on the API endpoints
- upload validation and antivirus scanning if untrusted users can upload
- a backup and restore policy with off-host copies
- a secret manager for `.env` (Vault, AWS Secrets Manager, etc.)
- log rotation and an audit-log retention policy

These are explicitly **out of scope for v0.2** as bundled features, but
required for any production-style deployment.

## Data subject considerations (GDPR / professional secrecy)

If you process personal data of EU data subjects, or data covered by
attorney-client privilege:

- Keep matter data on infrastructure under your control.
- Configure Ollama or another local provider so that prompts and answers
  never leave your perimeter.
- Document, with your DPO if applicable, the LLM provider and the
  data-flow, especially before enabling a hosted provider.
- Honour data-subject deletion requests by removing matter rows and
  associated `memory_files/` entries; agent memory should be reviewed
  separately because it may reference personal data even when the matter
  is closed.

## Known limitations

- The grounded answer engine reduces hallucinations but cannot eliminate
  them. Always verify outputs against the cited sources before relying on
  them in a professional context.
- Workflow packs encode requirements as authored. Verify the pack version
  against current law for your jurisdiction.
- The OCR pipeline depends on the Ollama OCR model you configure; quality
  varies with the model and document.

## Disclaimer

See [DISCLAIMER.md](DISCLAIMER.md). Judicex does not provide legal advice
and does not replace a qualified legal professional.
