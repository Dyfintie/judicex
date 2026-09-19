from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .evaluation import DEFAULT_SUITE, list_builtin_suites, run_eval_suite
from .official_sources import ingest_normattiva_urn, list_official_bundles, sync_official_bundle
from .ollama_agent import ask_once, run_chat_session
from .store import LegalMemoryStore


def _print_json(payload: dict[str, Any] | list[dict[str, Any]]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Judicex Legal Memory OS CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_db = subparsers.add_parser("init-db", help="Create or update the SQLite schema.")
    init_db.add_argument("--db", required=True)

    list_bundles = subparsers.add_parser("list-bundles", help="List official bundles.")

    sync_bundle = subparsers.add_parser("sync-bundle", help="Fetch and ingest an official bundle from Normattiva.")
    sync_bundle.add_argument("--db", required=True)
    sync_bundle.add_argument("--bundle", required=True)
    sync_bundle.add_argument("--as-of-date", help="YYYY-MM-DD. Defaults to today's date.")

    ingest_urn = subparsers.add_parser("ingest-urn", help="Fetch and ingest one official Normattiva URN.")
    ingest_urn.add_argument("--db", required=True)
    ingest_urn.add_argument("--urn", required=True)
    ingest_urn.add_argument("--area", required=True)
    ingest_urn.add_argument("--document-id")
    ingest_urn.add_argument("--kind", default="norma")

    ingest_json = subparsers.add_parser("ingest-json", help="Ingest documents/entities/edges from JSON.")
    ingest_json.add_argument("--db", required=True)
    ingest_json.add_argument("--file", required=True)

    matter_create = subparsers.add_parser("matter-create", help="Create or update a private legal matter.")
    matter_create.add_argument("--db", required=True)
    matter_create.add_argument("--title", required=True)
    matter_create.add_argument("--client-name", default="")
    matter_create.add_argument("--area", default="")
    matter_create.add_argument("--status", default="open")
    matter_create.add_argument("--summary", default="")
    matter_create.add_argument("--matter-id")

    matter_list = subparsers.add_parser("matter-list", help="List private legal matters.")
    matter_list.add_argument("--db", required=True)
    matter_list.add_argument("--area")
    matter_list.add_argument("--status")
    matter_list.add_argument("--top-k", type=int, default=20)

    matter_get = subparsers.add_parser("matter-get", help="Get one private legal matter.")
    matter_get.add_argument("--db", required=True)
    matter_get.add_argument("--matter-id", required=True)

    matter_add_doc = subparsers.add_parser("matter-add-doc", help="Add a private text document to a matter.")
    matter_add_doc.add_argument("--db", required=True)
    matter_add_doc.add_argument("--matter-id", required=True)
    matter_add_doc.add_argument("--file", required=True)
    matter_add_doc.add_argument("--title")
    matter_add_doc.add_argument("--kind", default="document")

    matter_search_docs = subparsers.add_parser("matter-search-docs", help="Search private matter documents.")
    matter_search_docs.add_argument("--db", required=True)
    matter_search_docs.add_argument("--query", required=True)
    matter_search_docs.add_argument("--matter-id")
    matter_search_docs.add_argument("--top-k", type=int, default=10)

    matter_search_facts = subparsers.add_parser("matter-search-facts", help="Search extracted private matter facts.")
    matter_search_facts.add_argument("--db", required=True)
    matter_search_facts.add_argument("--query", default="")
    matter_search_facts.add_argument("--matter-id")
    matter_search_facts.add_argument("--fact-type")
    matter_search_facts.add_argument("--top-k", type=int, default=20)

    matter_context = subparsers.add_parser("matter-context", help="Build a private matter context bundle.")
    matter_context.add_argument("--db", required=True)
    matter_context.add_argument("--matter-id", required=True)
    matter_context.add_argument("--query", default="")
    matter_context.add_argument("--document-k", type=int, default=6)
    matter_context.add_argument("--fact-k", type=int, default=20)

    memory_add = subparsers.add_parser("memory-add", help="Save an operational agent memory.")
    memory_add.add_argument("--db", required=True)
    memory_add.add_argument("--kind", default="note", help="preference, decision, lesson, note, instruction...")
    memory_add.add_argument("--title", required=True)
    memory_add.add_argument("--content", help="Memory content. Use --file for longer content.")
    memory_add.add_argument("--file", help="Read memory content from a UTF-8 text file.")
    memory_add.add_argument("--scope", default="global")
    memory_add.add_argument("--matter-id", default="")
    memory_add.add_argument("--tag", action="append", default=[])
    memory_add.add_argument("--importance", type=float, default=0.5)
    memory_add.add_argument("--source", default="cli")

    memory_search = subparsers.add_parser("memory-search", help="Search operational agent memory.")
    memory_search.add_argument("--db", required=True)
    memory_search.add_argument("--query", default="")
    memory_search.add_argument("--kind")
    memory_search.add_argument("--scope")
    memory_search.add_argument("--matter-id")
    memory_search.add_argument("--top-k", type=int, default=8)
    memory_search.add_argument("--full", action="store_true")
    memory_search.add_argument("--no-global", action="store_true")

    memory_delete = subparsers.add_parser("memory-delete", help="Delete one operational agent memory.")
    memory_delete.add_argument("--db", required=True)
    memory_delete.add_argument("--memory-id", required=True)

    list_workflow_packs = subparsers.add_parser("list-workflow-packs", help="List built-in matter analysis workflow packs.")
    list_workflow_packs.add_argument("--db", required=True)

    matter_analyze = subparsers.add_parser("matter-analyze", help="Analyze a matter against a legal thesis.")
    matter_analyze.add_argument("--db", required=True)
    matter_analyze.add_argument("--matter-id", required=True)
    matter_analyze.add_argument("--thesis", required=True)
    matter_analyze.add_argument("--workflow-pack")

    search_docs = subparsers.add_parser("search-docs", help="Search documents.")
    search_docs.add_argument("--db", required=True)
    search_docs.add_argument("--query", required=True)
    search_docs.add_argument("--area")
    search_docs.add_argument("--top-k", type=int, default=5)

    get_doc = subparsers.add_parser("get-doc", help="Get one document by id.")
    get_doc.add_argument("--db", required=True)
    get_doc.add_argument("--doc-id", required=True)

    search_entities = subparsers.add_parser("search-entities", help="Search graph entities.")
    search_entities.add_argument("--db", required=True)
    search_entities.add_argument("--query", required=True)
    search_entities.add_argument("--area")
    search_entities.add_argument("--top-k", type=int, default=5)

    search_atoms = subparsers.add_parser("search-atoms", help="Search compiled legal atoms.")
    search_atoms.add_argument("--db", required=True)
    search_atoms.add_argument("--query", required=True)
    search_atoms.add_argument("--area")
    search_atoms.add_argument("--atom-type")
    search_atoms.add_argument("--top-k", type=int, default=8)

    rebuild_atoms = subparsers.add_parser("rebuild-atoms", help="Recompile legal atoms from stored documents.")
    rebuild_atoms.add_argument("--db", required=True)
    rebuild_atoms.add_argument("--area")

    neighbors = subparsers.add_parser("neighbors", help="Traverse graph neighbors from an entity.")
    neighbors.add_argument("--db", required=True)
    neighbors.add_argument("--entity-id", required=True)
    neighbors.add_argument("--relation")
    neighbors.add_argument("--limit", type=int, default=10)

    context = subparsers.add_parser("context", help="Build a grounded context bundle for a question.")
    context.add_argument("--db", required=True)
    context.add_argument("--question", required=True)
    context.add_argument("--area")
    context.add_argument("--doc-k", type=int, default=6)
    context.add_argument("--entity-k", type=int, default=8)
    context.add_argument("--neighbor-k", type=int, default=6)

    health = subparsers.add_parser("health", help="Show store counters.")
    health.add_argument("--db", required=True)

    areas = subparsers.add_parser("areas", help="List areas in the store.")
    areas.add_argument("--db", required=True)

    ask = subparsers.add_parser("ask", help="One-shot grounded answer via configured LLM provider.")
    ask.add_argument("--db", required=True)
    ask.add_argument("--model", default="")
    ask.add_argument("--provider", default="")
    ask.add_argument("--question", required=True)
    ask.add_argument("--area")
    ask.add_argument("--matter-id")
    ask.add_argument("--host", default="http://127.0.0.1:11434")
    ask.add_argument("--base-url", default="")

    chat = subparsers.add_parser("chat", help="Terminal chat backed by configured LLM provider.")
    chat.add_argument("--db", required=True)
    chat.add_argument("--model", default="")
    chat.add_argument("--provider", default="")
    chat.add_argument("--area")
    chat.add_argument("--matter-id")
    chat.add_argument("--host", default="http://127.0.0.1:11434")
    chat.add_argument("--base-url", default="")

    web = subparsers.add_parser("web", help="Run the Flask web UI.")
    web.add_argument("--db", required=True)
    web.add_argument("--model", default="")
    web.add_argument("--area", default="civile")
    web.add_argument("--host", default="http://127.0.0.1:11434")
    web.add_argument("--bind", default="127.0.0.1")
    web.add_argument("--port", type=int, default=5050)
    web.add_argument("--debug", action="store_true")

    extract_refs = subparsers.add_parser(
        "extract-references",
        help="Extract typed citation edges (cita/abroga/deroga/...) from stored documents via LLM.",
    )
    extract_refs.add_argument("--db", required=True)
    extract_refs.add_argument("--model", default="")
    extract_refs.add_argument("--provider", default="")
    extract_refs.add_argument("--host", default="http://127.0.0.1:11434")
    extract_refs.add_argument("--base-url", default="")
    extract_refs.add_argument("--area")
    extract_refs.add_argument("--limit", type=int, default=0, help="0 = all")
    extract_refs.add_argument("--reset", action="store_true", help="Drop existing graph edges before re-extraction")

    shepardize_cmd = subparsers.add_parser(
        "shepardize",
        help="Citator: vigency status, citing references, abrogations for a document.",
    )
    shepardize_cmd.add_argument("--db", required=True)
    shepardize_cmd.add_argument("--doc-id", required=True)
    shepardize_cmd.add_argument("--as-of-date", default="", help="YYYY-MM-DD; empty = ignore date")

    audit_list = subparsers.add_parser("audit-list", help="List most recent answer audit records.")
    audit_list.add_argument("--db", required=True)
    audit_list.add_argument("--limit", type=int, default=20)

    metrics_cmd = subparsers.add_parser(
        "metrics",
        help="Observability JSON: audit, corpus, graph, cache aggregates.",
    )
    metrics_cmd.add_argument("--db", required=True)
    metrics_cmd.add_argument("--since", default="", help="ISO datetime; only audit rows after this point are counted")
    metrics_cmd.add_argument("--audit-window", type=int, default=200, help="Recent audit rows considered")

    draft_list = subparsers.add_parser("draft-list", help="List built-in atto templates.")

    draft_cmd = subparsers.add_parser(
        "draft",
        help="Render an atto from a template, enforcing vigency at as_of_date.",
    )
    draft_cmd.add_argument("--db", required=True)
    draft_cmd.add_argument("--template", required=True, help="Template name (e.g. ricorso_decreto_ingiuntivo)")
    draft_cmd.add_argument("--as-of-date", required=True, help="YYYY-MM-DD del fatto / dell'atto")
    draft_cmd.add_argument("--matter-id", help="Optional: matter id from which to seed parametri")
    draft_cmd.add_argument(
        "--params",
        action="append",
        default=[],
        help="key=value, ripetibile (es. --params importo=8500 --params creditore='Alfa SRL')",
    )

    graph_traverse = subparsers.add_parser(
        "graph-traverse",
        help="Multi-hop traversal over the typed citation graph.",
    )
    graph_traverse.add_argument("--db", required=True)
    graph_traverse.add_argument("--start", required=True, help="Document id to start from")
    graph_traverse.add_argument("--relations", help="Comma-separated relation types (default: all)")
    graph_traverse.add_argument("--direction", default="outbound", choices=["outbound", "inbound", "both"])
    graph_traverse.add_argument("--max-depth", type=int, default=3)
    graph_traverse.add_argument("--as-of-date", default="")
    graph_traverse.add_argument("--max-nodes", type=int, default=200)

    eval_parser = subparsers.add_parser("eval", help="Run deterministic Judicex evaluation suites.")
    eval_subparsers = eval_parser.add_subparsers(dest="eval_command", required=True)

    eval_list = eval_subparsers.add_parser("list", help="List built-in evaluation suites.")

    eval_run = eval_subparsers.add_parser("run", help="Run one deterministic evaluation suite.")
    eval_run.add_argument("--db", required=True)
    eval_run.add_argument("--suite", default=DEFAULT_SUITE, help="Built-in suite id or path to a JSON suite.")
    eval_run.add_argument("--rebuild-atoms", action="store_true")

    eval_gold_list = eval_subparsers.add_parser("gold-list", help="List built-in gold suites for end-to-end LLM eval.")

    eval_gold_run = eval_subparsers.add_parser(
        "gold-run",
        help="Run a gold suite end-to-end through the LLM agent. Computes hallucination rate, citation accuracy, etc.",
    )
    eval_gold_run.add_argument("--db", required=True)
    eval_gold_run.add_argument("--model", default="")
    eval_gold_run.add_argument("--provider", default="")
    eval_gold_run.add_argument("--host", default="http://127.0.0.1:11434")
    eval_gold_run.add_argument("--base-url", default="")
    eval_gold_run.add_argument("--suite", required=True, help="Suite name (e.g. recupero_crediti) or path to JSON.")
    eval_gold_run.add_argument("--no-cache", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "list-bundles":
        _print_json(list_official_bundles())
        return 0

    if args.command == "eval" and args.eval_command == "list":
        _print_json({"suites": list_builtin_suites()})
        return 0

    if args.command == "eval" and args.eval_command == "gold-list":
        from .evals import list_gold_suites

        _print_json({"gold_suites": list_gold_suites()})
        return 0

    if args.command == "eval" and args.eval_command == "gold-run":
        from .evals import run_gold_suite

        result = run_gold_suite(
            db_path=args.db,
            model=args.model,
            suite=args.suite,
            host=args.host,
            provider=args.provider,
            base_url=args.base_url,
            cache_enabled=not args.no_cache,
        )
        _print_json(result)
        return 0 if result["status"] == "passed" else 1

    if args.command == "ask":
        result = ask_once(
            db_path=args.db,
            model=args.model,
            question=args.question,
            area=args.area,
            host=args.host,
            provider=args.provider,
            base_url=args.base_url,
            matter_id=args.matter_id,
        )
        _print_json(result)
        return 0

    if args.command == "chat":
        run_chat_session(
            db_path=args.db,
            model=args.model,
            area=args.area,
            host=args.host,
            provider=args.provider,
            base_url=args.base_url,
            matter_id=args.matter_id,
        )
        return 0

    if args.command == "web":
        from .web_app import create_app

        app = create_app(
            db_path=args.db,
            default_model=args.model,
            default_area=args.area,
            ollama_host=args.host,
        )
        app.run(host=args.bind, port=args.port, debug=args.debug)
        return 0

    try:
        store_context = LegalMemoryStore(args.db)
    except RuntimeError as exc:
        _print_json({"status": "error", "error": str(exc)})
        return 1

    with store_context as store:
        if args.command == "init-db":
            _print_json({"status": "ok", "db": args.db, "health": store.health()})
            return 0
        if args.command == "sync-bundle":
            _print_json(
                sync_official_bundle(
                    store,
                    bundle_name=args.bundle,
                    as_of_date=args.as_of_date,
                )
            )
            return 0
        if args.command == "ingest-urn":
            _print_json(
                ingest_normattiva_urn(
                    store,
                    urn=args.urn,
                    area=args.area,
                    document_id=args.document_id,
                    kind=args.kind,
                )
            )
            return 0
        if args.command == "ingest-json":
            _print_json({"status": "ok", "db": args.db, "health": store.ingest_json_file(args.file)})
            return 0
        if args.command == "matter-create":
            _print_json(
                store.create_matter(
                    title=args.title,
                    client_name=args.client_name,
                    area=args.area,
                    status=args.status,
                    summary=args.summary,
                    matter_id=args.matter_id,
                )
            )
            return 0
        if args.command == "matter-list":
            _print_json(store.list_matters(area=args.area, status=args.status, top_k=args.top_k))
            return 0
        if args.command == "matter-get":
            _print_json(store.get_matter(args.matter_id) or {"error": "matter not found"})
            return 0
        if args.command == "matter-add-doc":
            _print_json(
                store.add_matter_document_file(
                    args.matter_id,
                    args.file,
                    title=args.title,
                    kind=args.kind,
                )
            )
            return 0
        if args.command == "matter-search-docs":
            _print_json(
                store.search_matter_documents(
                    args.query,
                    matter_id=args.matter_id,
                    top_k=args.top_k,
                )
            )
            return 0
        if args.command == "matter-search-facts":
            _print_json(
                store.search_matter_facts(
                    args.query,
                    matter_id=args.matter_id,
                    fact_type=args.fact_type,
                    top_k=args.top_k,
                )
            )
            return 0
        if args.command == "matter-context":
            _print_json(
                store.build_matter_context(
                    args.matter_id,
                    query=args.query,
                    document_k=args.document_k,
                    fact_k=args.fact_k,
                )
            )
            return 0
        if args.command == "memory-add":
            content = args.content or ""
            if args.file:
                content = Path(args.file).read_text(encoding="utf-8")
            if not content.strip():
                _print_json({"status": "error", "error": "Use --content or --file."})
                return 2
            _print_json(
                store.add_agent_memory(
                    kind=args.kind,
                    title=args.title,
                    content=content,
                    scope=args.scope,
                    matter_id=args.matter_id,
                    tags=args.tag,
                    importance=args.importance,
                    source=args.source,
                )
            )
            return 0
        if args.command == "memory-search":
            _print_json(
                store.search_agent_memories(
                    args.query,
                    kind=args.kind,
                    scope=args.scope,
                    matter_id=args.matter_id,
                    include_global=not args.no_global,
                    top_k=args.top_k,
                    full=args.full,
                )
            )
            return 0
        if args.command == "memory-delete":
            _print_json({"status": "deleted" if store.delete_agent_memory(args.memory_id) else "not_found"})
            return 0
        if args.command == "list-workflow-packs":
            _print_json({"workflow_packs": store.list_workflow_packs()})
            return 0
        if args.command == "matter-analyze":
            _print_json(store.analyze_matter(args.matter_id, args.thesis, workflow_pack=args.workflow_pack))
            return 0
        if args.command == "search-docs":
            _print_json(store.search_documents(args.query, area=args.area, top_k=args.top_k))
            return 0
        if args.command == "get-doc":
            _print_json(store.get_document(args.doc_id) or {"error": "document not found"})
            return 0
        if args.command == "search-entities":
            _print_json(store.search_entities(args.query, area=args.area, top_k=args.top_k))
            return 0
        if args.command == "search-atoms":
            _print_json(
                store.search_atoms(
                    args.query,
                    area=args.area,
                    atom_type=args.atom_type,
                    top_k=args.top_k,
                )
            )
            return 0
        if args.command == "rebuild-atoms":
            _print_json({"status": "ok", "db": args.db, "compiled": store.rebuild_legal_atoms(area=args.area)})
            return 0
        if args.command == "neighbors":
            _print_json(store.get_neighbors(args.entity_id, relation=args.relation, limit=args.limit))
            return 0
        if args.command == "context":
            _print_json(
                store.build_context(
                    args.question,
                    area=args.area,
                    doc_k=args.doc_k,
                    entity_k=args.entity_k,
                    neighbor_k=args.neighbor_k,
                )
            )
            return 0
        if args.command == "health":
            _print_json(store.health())
            return 0
        if args.command == "areas":
            _print_json(store.list_areas())
            return 0
        if args.command == "eval" and args.eval_command == "run":
            result = run_eval_suite(
                store,
                suite=args.suite,
                rebuild_atoms=bool(args.rebuild_atoms),
            )
            _print_json(result)
            return 0 if result["status"] == "passed" else 1
        if args.command == "extract-references":
            from .entity_extractor import extract_norm_references, materialise_references
            from .llm_provider import make_client, resolve_settings

            llm_settings = resolve_settings(
                store,
                default_model=args.model,
                ollama_host=args.host,
                overrides={"provider": args.provider, "model": args.model, "base_url": args.base_url},
            )
            client = make_client(llm_settings)
            sql = "SELECT * FROM documents"
            params: list[Any] = []
            if args.area:
                sql += " WHERE area = ?"
                params.append(args.area)
            sql += " ORDER BY id"
            if args.limit and args.limit > 0:
                sql += " LIMIT ?"
                params.append(args.limit)
            rows = store.conn.execute(sql, params).fetchall()
            if args.reset:
                # Drop only typed-citation edges, leave bookkeeping `references`
                # edges (created by replace_document_references) untouched.
                from .entity_extractor import VALID_RELATIONS

                placeholders = ",".join(["?"] * len(VALID_RELATIONS))
                store.conn.execute(
                    f"DELETE FROM edges WHERE relation IN ({placeholders})",
                    list(VALID_RELATIONS),
                )
                store.conn.commit()

            summary = {"documents_processed": 0, "edges": 0, "resolved": 0, "unresolved": 0}
            for row in rows:
                doc = store._document_row_to_dict(row, full=True)
                refs = extract_norm_references(client, llm_settings["model"], document=doc)
                counts = materialise_references(store, document=doc, references=refs)
                summary["documents_processed"] += 1
                summary["edges"] += counts["total"]
                summary["resolved"] += counts["resolved"]
                summary["unresolved"] += counts["unresolved"]
            _print_json(summary)
            return 0
        if args.command == "shepardize":
            _print_json(store.shepardize(args.doc_id, args.as_of_date))
            return 0
        if args.command == "audit-list":
            _print_json(store.list_answer_audit(limit=args.limit))
            return 0
        if args.command == "metrics":
            from .metrics import collect_metrics

            _print_json(
                collect_metrics(
                    store,
                    since=args.since,
                    recent_audit_window=args.audit_window,
                )
            )
            return 0
        if args.command == "draft-list":
            from .drafter import list_templates

            _print_json({"templates": list_templates()})
            return 0
        if args.command == "draft":
            from .drafter import draft_atto, DraftingError

            params: dict[str, str] = {}
            for entry in args.params or []:
                if "=" not in entry:
                    continue
                key, _, value = entry.partition("=")
                params[key.strip()] = value.strip()
            try:
                result = draft_atto(
                    store,
                    template_name=args.template,
                    as_of_date=args.as_of_date,
                    params=params,
                    matter_id=args.matter_id,
                )
            except DraftingError as exc:
                _print_json({"status": "error", "error": str(exc)})
                return 1
            _print_json(result)
            return 0 if result.get("status") == "drafted" else 2
        if args.command == "graph-traverse":
            relations = (
                tuple(r.strip() for r in args.relations.split(",") if r.strip())
                if args.relations
                else None
            )
            _print_json(
                store.traverse_graph(
                    args.start,
                    relations=relations,
                    direction=args.direction,
                    max_depth=args.max_depth,
                    as_of_date=args.as_of_date,
                    max_nodes=args.max_nodes,
                )
            )
            return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
