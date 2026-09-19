"""Conflict / abrogation / supersession detection over the typed citation graph.

This step is deterministic: it reads the typed edges populated by
`entity_extractor.materialise_references` and produces a structured report on
the documents currently in evidence. The output is consumed by the answer
contract (claims citing abrogated norms are blocked) and surfaces in the
agent trace so the user can see why a fonte was disqualified.

Severity scale:
- "abrogated": the cited norm is abrogated by another vigent norm at the
  given as_of_date. Use to BLOCK claims.
- "modified": the cited norm has been modified by a later vigent norm; the
  cited text may still be substantively correct but a more recent version
  exists. Use to WARN.
- "derogated": a special norm derogates from this one in specific cases.
  Use to WARN.
- "conflict": two cited norms have an explicit `confligge_con` edge.
  Use to WARN.
"""

from __future__ import annotations

from typing import Any


SeverityBlocking = "abrogated"
SeverityWarning = ("modified", "derogated", "conflict")


def detect_conflicts(
    store: Any,
    *,
    documents: list[dict[str, Any]],
    as_of_date: str = "",
) -> dict[str, Any]:
    """Run the citator over each evidence document and merge the findings."""

    findings: list[dict[str, Any]] = []
    pair_findings: list[dict[str, Any]] = []
    examined: list[str] = []

    doc_ids = [str(doc.get("id") or "") for doc in documents if doc.get("id")]
    doc_id_set = set(doc_ids)
    for doc_id in doc_ids:
        report = store.shepardize(doc_id, as_of_date)
        examined.append(doc_id)
        for abrogation in report.get("active_abrogations", []) or []:
            findings.append(
                {
                    "severity": "abrogated",
                    "document_id": doc_id,
                    "document_title": report.get("title", ""),
                    "by_document_id": abrogation.get("source_document_id", ""),
                    "by_title": abrogation.get("source_title", ""),
                    "evidence_quote": abrogation.get("evidence_quote", ""),
                    "summary": abrogation.get("summary", ""),
                    "as_of_date": as_of_date,
                }
            )
        for modification in report.get("modifications", []) or []:
            findings.append(
                {
                    "severity": "modified",
                    "document_id": doc_id,
                    "document_title": report.get("title", ""),
                    "by_document_id": modification.get("source_document_id", ""),
                    "by_title": "",
                    "evidence_quote": modification.get("evidence_quote", ""),
                    "summary": modification.get("summary", ""),
                    "as_of_date": as_of_date,
                }
            )
        for derogation in report.get("derogations", []) or []:
            findings.append(
                {
                    "severity": "derogated",
                    "document_id": doc_id,
                    "document_title": report.get("title", ""),
                    "by_document_id": derogation.get("source_document_id", ""),
                    "by_title": "",
                    "evidence_quote": derogation.get("evidence_quote", ""),
                    "summary": derogation.get("summary", ""),
                    "as_of_date": as_of_date,
                }
            )
        for conflict in report.get("conflicts", []) or []:
            other_id = conflict.get("source_document_id", "")
            if other_id and other_id in doc_id_set:
                # Only surface conflicts where BOTH sides are in evidence:
                # otherwise the warning lacks actionable context.
                pair_findings.append(
                    {
                        "severity": "conflict",
                        "document_a_id": doc_id,
                        "document_b_id": other_id,
                        "evidence_quote": conflict.get("evidence_quote", ""),
                        "summary": conflict.get("summary", ""),
                    }
                )

    blocked_ids = sorted({f["document_id"] for f in findings if f["severity"] == SeverityBlocking})
    warning_ids = sorted({f["document_id"] for f in findings if f["severity"] in SeverityWarning})

    return {
        "as_of_date": as_of_date,
        "examined_documents": examined,
        "findings": findings,
        "pair_findings": pair_findings,
        "blocked_document_ids": blocked_ids,
        "warning_document_ids": warning_ids,
        "graph_populated": _graph_has_typed_edges(store),
    }


def _graph_has_typed_edges(store: Any) -> bool:
    """Quick health check: returns False when the citator graph is empty.

    Surfacing this lets the agent trace explain why no conflicts were found —
    "graph not populated, run `extract-references`" — instead of pretending
    everything is fine.
    """

    from .entity_extractor import VALID_RELATIONS

    placeholders = ",".join(["?"] * len(VALID_RELATIONS))
    row = store.conn.execute(
        f"SELECT 1 FROM edges WHERE relation IN ({placeholders}) LIMIT 1",
        list(VALID_RELATIONS),
    ).fetchone()
    return row is not None
