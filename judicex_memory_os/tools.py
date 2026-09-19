from __future__ import annotations

import json
from typing import Any

from .evaluation import DEFAULT_SUITE, list_builtin_suites, run_eval_suite
from .official_sources import ingest_normattiva_urn, list_official_bundles, sync_official_bundle
from .store import LegalMemoryStore


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "search_documents",
        "description": "Search legal documents stored in the local memory.",
        "inputSchema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "area": {"type": "string"},
                "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
            },
        },
    },
    {
        "name": "get_document",
        "description": "Fetch one document by exact id.",
        "inputSchema": {
            "type": "object",
            "required": ["doc_id"],
            "properties": {"doc_id": {"type": "string"}},
        },
    },
    {
        "name": "search_entities",
        "description": "Search graph entities, including ingested document nodes.",
        "inputSchema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "area": {"type": "string"},
                "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
            },
        },
    },
    {
        "name": "search_atoms",
        "description": "Search compiled legal atoms extracted from official and local sources.",
        "inputSchema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "area": {"type": "string"},
                "atom_type": {"type": "string"},
                "top_k": {"type": "integer", "default": 8, "minimum": 1, "maximum": 50},
            },
        },
    },
    {
        "name": "rebuild_atoms",
        "description": "Recompile legal atoms from stored documents.",
        "inputSchema": {
            "type": "object",
            "properties": {"area": {"type": "string"}},
        },
    },
    {
        "name": "get_neighbors",
        "description": "Traverse the legal graph around one entity id.",
        "inputSchema": {
            "type": "object",
            "required": ["entity_id"],
            "properties": {
                "entity_id": {"type": "string"},
                "relation": {"type": "string"},
                "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
            },
        },
    },
    {
        "name": "build_context",
        "description": "Build a grounded context bundle for a user question.",
        "inputSchema": {
            "type": "object",
            "required": ["question"],
            "properties": {
                "question": {"type": "string"},
                "area": {"type": "string"},
                "doc_k": {"type": "integer", "default": 6, "minimum": 1, "maximum": 10},
                "entity_k": {"type": "integer", "default": 8, "minimum": 1, "maximum": 20},
                "neighbor_k": {"type": "integer", "default": 6, "minimum": 1, "maximum": 20},
            },
        },
    },
    {
        "name": "create_matter",
        "description": "Create or update a private legal matter for a client or case file.",
        "inputSchema": {
            "type": "object",
            "required": ["title"],
            "properties": {
                "title": {"type": "string"},
                "client_name": {"type": "string"},
                "area": {"type": "string"},
                "status": {"type": "string", "default": "open"},
                "summary": {"type": "string"},
                "matter_id": {"type": "string"},
            },
        },
    },
    {
        "name": "list_matters",
        "description": "List private legal matters stored in the local memory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "area": {"type": "string"},
                "status": {"type": "string"},
                "top_k": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
            },
        },
    },
    {
        "name": "get_matter",
        "description": "Fetch one private legal matter by exact id.",
        "inputSchema": {
            "type": "object",
            "required": ["matter_id"],
            "properties": {"matter_id": {"type": "string"}},
        },
    },
    {
        "name": "add_matter_document",
        "description": "Add a private text document to a matter and extract deterministic case facts.",
        "inputSchema": {
            "type": "object",
            "required": ["matter_id", "title", "content"],
            "properties": {
                "matter_id": {"type": "string"},
                "title": {"type": "string"},
                "kind": {"type": "string", "default": "document"},
                "content": {"type": "string"},
                "source_path": {"type": "string"},
            },
        },
    },
    {
        "name": "search_matter_documents",
        "description": "Search private documents stored inside legal matters.",
        "inputSchema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "matter_id": {"type": "string"},
                "top_k": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
            },
        },
    },
    {
        "name": "search_matter_facts",
        "description": "Search deterministic facts extracted from private matter documents.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "default": ""},
                "matter_id": {"type": "string"},
                "fact_type": {"type": "string"},
                "top_k": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
            },
        },
    },
    {
        "name": "build_matter_context",
        "description": "Build a private matter context with relevant documents, facts, parties, amounts, and timeline.",
        "inputSchema": {
            "type": "object",
            "required": ["matter_id"],
            "properties": {
                "matter_id": {"type": "string"},
                "query": {"type": "string", "default": ""},
                "document_k": {"type": "integer", "default": 6, "minimum": 1, "maximum": 50},
                "fact_k": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
            },
        },
    },
    {
        "name": "analyze_matter",
        "description": "Analyze a private matter against a legal thesis and identify present and missing proof elements.",
        "inputSchema": {
            "type": "object",
            "required": ["matter_id", "thesis"],
            "properties": {
                "matter_id": {"type": "string"},
                "thesis": {"type": "string"},
                "workflow_pack": {"type": "string"},
            },
        },
    },
    {
        "name": "list_workflow_packs",
        "description": "List built-in configurable workflow packs for matter analysis.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_bundles",
        "description": "List official source bundles available for sync.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_eval_suites",
        "description": "List built-in deterministic evaluation suites.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "run_eval_suite",
        "description": "Run a deterministic evaluation suite against the local memory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "suite": {"type": "string", "default": DEFAULT_SUITE},
                "rebuild_atoms": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "sync_official_bundle",
        "description": "Fetch and ingest a small official bundle from Normattiva into the local memory.",
        "inputSchema": {
            "type": "object",
            "required": ["bundle"],
            "properties": {
                "bundle": {"type": "string"},
                "as_of_date": {"type": "string", "description": "YYYY-MM-DD"},
            },
        },
    },
    {
        "name": "ingest_normattiva_urn",
        "description": "Fetch and ingest one official article from Normattiva by URN.",
        "inputSchema": {
            "type": "object",
            "required": ["urn", "area"],
            "properties": {
                "urn": {"type": "string"},
                "area": {"type": "string"},
                "document_id": {"type": "string"},
                "kind": {"type": "string"},
            },
        },
    },
    {
        "name": "list_areas",
        "description": "List legal areas available in the local memory.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "health",
        "description": "Return basic health counters for the local memory store.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


class LegalMemoryTools:
    def __init__(self, store: LegalMemoryStore) -> None:
        self.store = store

    def definitions(self) -> list[dict[str, Any]]:
        return TOOL_DEFINITIONS

    def prompt_catalog(self) -> str:
        compact = []
        for item in TOOL_DEFINITIONS:
            compact.append(
                {
                    "name": item["name"],
                    "description": item["description"],
                    "inputSchema": item["inputSchema"],
                }
            )
        return json.dumps(compact, ensure_ascii=False, indent=2)

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        args = arguments or {}
        if name == "search_documents":
            return {
                "documents": self.store.search_documents(
                    query=str(args["query"]),
                    area=args.get("area"),
                    top_k=int(args.get("top_k", 5)),
                )
            }
        if name == "get_document":
            document = self.store.get_document(str(args["doc_id"]))
            if document is None:
                return {"error": f"document not found: {args['doc_id']}"}
            return {"document": document}
        if name == "search_entities":
            return {
                "entities": self.store.search_entities(
                    query=str(args["query"]),
                    area=args.get("area"),
                    top_k=int(args.get("top_k", 5)),
                )
            }
        if name == "search_atoms":
            return {
                "legal_atoms": self.store.search_atoms(
                    query=str(args["query"]),
                    area=args.get("area"),
                    atom_type=args.get("atom_type"),
                    top_k=int(args.get("top_k", 8)),
                )
            }
        if name == "rebuild_atoms":
            return {"compiled": self.store.rebuild_legal_atoms(area=args.get("area"))}
        if name == "get_neighbors":
            return {
                "neighbors": self.store.get_neighbors(
                    entity_id=str(args["entity_id"]),
                    relation=args.get("relation"),
                    limit=int(args.get("limit", 10)),
                )
            }
        if name == "build_context":
            return {
                "context": self.store.build_context(
                    question=str(args["question"]),
                    area=args.get("area"),
                    doc_k=int(args.get("doc_k", 6)),
                    entity_k=int(args.get("entity_k", 8)),
                    neighbor_k=int(args.get("neighbor_k", 6)),
                )
            }
        if name == "create_matter":
            return {
                "matter": self.store.create_matter(
                    title=str(args["title"]),
                    client_name=str(args.get("client_name", "")),
                    area=str(args.get("area", "")),
                    status=str(args.get("status", "open")),
                    summary=str(args.get("summary", "")),
                    matter_id=args.get("matter_id"),
                )
            }
        if name == "list_matters":
            return {
                "matters": self.store.list_matters(
                    area=args.get("area"),
                    status=args.get("status"),
                    top_k=int(args.get("top_k", 20)),
                )
            }
        if name == "get_matter":
            matter = self.store.get_matter(str(args["matter_id"]))
            if matter is None:
                return {"error": f"matter not found: {args['matter_id']}"}
            return {"matter": matter}
        if name == "add_matter_document":
            return self.store.add_matter_document(
                str(args["matter_id"]),
                title=str(args["title"]),
                kind=str(args.get("kind", "document")),
                content=str(args["content"]),
                source_path=str(args.get("source_path", "")),
            )
        if name == "search_matter_documents":
            return {
                "documents": self.store.search_matter_documents(
                    str(args["query"]),
                    matter_id=args.get("matter_id"),
                    top_k=int(args.get("top_k", 10)),
                )
            }
        if name == "search_matter_facts":
            return {
                "facts": self.store.search_matter_facts(
                    str(args.get("query", "")),
                    matter_id=args.get("matter_id"),
                    fact_type=args.get("fact_type"),
                    top_k=int(args.get("top_k", 20)),
                )
            }
        if name == "build_matter_context":
            return {
                "context": self.store.build_matter_context(
                    str(args["matter_id"]),
                    query=str(args.get("query", "")),
                    document_k=int(args.get("document_k", 6)),
                    fact_k=int(args.get("fact_k", 20)),
                )
            }
        if name == "analyze_matter":
            return {
                "analysis": self.store.analyze_matter(
                    str(args["matter_id"]),
                    str(args["thesis"]),
                    workflow_pack=args.get("workflow_pack"),
                )
            }
        if name == "list_workflow_packs":
            return {"workflow_packs": self.store.list_workflow_packs()}
        if name == "list_bundles":
            return {"bundles": list_official_bundles()}
        if name == "list_eval_suites":
            return {"suites": list_builtin_suites()}
        if name == "run_eval_suite":
            return run_eval_suite(
                self.store,
                suite=str(args.get("suite", DEFAULT_SUITE)),
                rebuild_atoms=bool(args.get("rebuild_atoms", False)),
            )
        if name == "sync_official_bundle":
            return sync_official_bundle(
                self.store,
                bundle_name=str(args["bundle"]),
                as_of_date=args.get("as_of_date"),
            )
        if name == "ingest_normattiva_urn":
            return ingest_normattiva_urn(
                self.store,
                urn=str(args["urn"]),
                area=str(args["area"]),
                document_id=args.get("document_id"),
                kind=str(args.get("kind", "norma")),
            )
        if name == "list_areas":
            return {"areas": self.store.list_areas()}
        if name == "health":
            return self.store.health()
        raise ValueError(f"unknown tool: {name}")
