# Judicex Product Strategy

Judicex is a verifiable Legal Memory OS, not a generic legal chatbot.

## Product Thesis

Legal professionals do not buy AI. They buy time saved, risk reduced, and work product they can verify. Judicex must therefore keep the legal reasoning pipeline observable:

1. official and private sources are ingested with versioned provenance;
2. legal text is compiled into structured legal atoms;
3. retrieval combines documents, graph entities, and legal atoms;
4. answers cite source documents and fail closed when the source package is insufficient;
5. regressions are caught by legal evaluation tests before release.

## Strategic Advantage

The moat is not a prompt. The moat is accumulated verified legal memory:

- clean source database;
- versioned legal source history;
- legal atom compiler;
- proprietary evaluation suite;
- client-specific memory and work product;
- workflow modules tied to real legal tasks;
- measurable citation and answer reliability.

## Build Order

### Judicex Core

Source ingestion -> source versioning -> legal atom extraction -> hybrid retrieval -> citation gate -> semantic verifier -> answer renderer -> regression tests.

The answer contract is part of the core. It must deterministically check claim citations, numeric facts, source documents, and legal atoms before a generated response is exposed as grounded.

Verifier and citation-gate failures are retained as audit metadata, not rendered as user-facing legal limits. The product answer should read like professional legal software; the forensic trace remains available for debugging, QA, and compliance.

### Legal Memory OS

Matter files, client documents, extracted facts, questions asked, produced drafts, firm clauses, preferred drafting style, and internal legal positions.

The first implemented layer stores private matters, private text documents, and deterministic case facts. It extracts parties, dates, amounts, and deadlines without relying on an LLM. This gives the future product a factual workspace for chronology, evidence review, missing-proof analysis, and matter-specific chat context.

Matter-aware answering is now part of the runtime contract: official sources support legal claims, while private matter facts are rendered as case facts with validated private ids. This keeps legal provenance clean and lets the product combine "what the law says" with "what is in this file" without confusing the two evidence classes.

The first workflow layer is matter analysis against a thesis. It maps the thesis to an explicit proof profile, checks extracted facts and private documents, and returns present elements, partial support, missing requirements, and next actions. The initial profiles cover civil debt recovery/injunction proceedings, opposition to injunctions, and generic file review.

Workflow requirements are data, not application logic. Matter analysis profiles live in versioned JSON workflow packs that can be replaced or extended per vertical, firm, or customer without changing the engine. The built-in pack is only the first distributable pack, not a hardcoded limit.

The conversational runtime uses a semantic intent router when a matter is active. The model chooses only the capability (`matter_analysis`, `legal_answer`, or `chat`); it does not produce the operational file review itself. When the selected capability is `matter_analysis`, execution is deterministic and repeatable, while LLM answering remains available for legal explanation and drafting paths.

### Workflow Modules

Research, file analysis, drafting, opponent document review, litigation strategy, fact chronology, evidence extraction, version comparison, citation checking, and missing-proof analysis.

### Product Surface

A GPT-style web workspace with matter sidebar, chat, source panel, atom inspector, document upload, markdown rendering, export, and audit trail.

## Initial Vertical

The first production vertical is civil debt recovery and injunction proceedings. It is narrow enough to evaluate rigorously and valuable enough for law firms and companies.
