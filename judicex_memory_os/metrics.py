"""Observability metrics over a Judicex SQLite store.

Aggregates the audit log, document inventory and citation graph into a single
JSON document suitable for piping into Grafana / Prometheus exporters or for
inspection via the CLI. All numbers are computed deterministically from the
DB; nothing is recomputed via the LLM.

Metrics surfaced:

- audit.total / status_breakdown / area_breakdown / domain_breakdown
- audit.mean_confidence and confidence histogram (from payload_json)
- audit.hallucination_rate over the last N records
- corpus.documents_by_area / by_source_type / temporal_buckets
- graph.edges_by_relation / typed_edge_density
- cache.entries / by_kind / oldest / newest

Use `--since YYYY-MM-DD` to scope time-bounded counters.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any


def collect_metrics(store: Any, *, since: str = "", recent_audit_window: int = 200) -> dict[str, Any]:
    return {
        "as_of": store._now(),
        "since": since,
        "audit": _audit_metrics(store, since=since, recent_audit_window=recent_audit_window),
        "corpus": _corpus_metrics(store),
        "graph": _graph_metrics(store),
        "cache": _cache_metrics(store),
    }


def _audit_metrics(store: Any, *, since: str, recent_audit_window: int) -> dict[str, Any]:
    base_sql = "SELECT status, model, area, matter_id, as_of_date, payload_json, ts FROM answer_audit"
    params: list[Any] = []
    if since:
        base_sql += " WHERE ts >= ?"
        params.append(since)
    base_sql += " ORDER BY ts DESC"
    rows = store.conn.execute(base_sql, params).fetchall()

    status_counter: Counter[str] = Counter()
    area_counter: Counter[str] = Counter()
    domain_counter: Counter[str] = Counter()
    confidence_values: list[float] = []
    hallucination_signals = {"claims_total": 0, "claims_rejected": 0}
    confidence_histogram: dict[str, int] = {
        "0.0-0.2": 0,
        "0.2-0.4": 0,
        "0.4-0.6": 0,
        "0.6-0.8": 0,
        "0.8-1.0": 0,
    }
    recent_records = rows[: max(1, recent_audit_window)]
    for row in recent_records:
        status_counter[row["status"] or "unknown"] += 1
        if row["area"]:
            area_counter[row["area"]] += 1
        try:
            payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
        except Exception:
            payload = {}
        confidence = float((payload.get("answer_confidence") or {}).get("score") or 0.0)
        confidence_values.append(confidence)
        confidence_histogram[_bucket(confidence)] += 1
        contract = payload.get("answer_contract") or {}
        hallucination_signals["claims_total"] += int(contract.get("claims_total") or 0)
        hallucination_signals["claims_rejected"] += int(contract.get("claims_rejected") or 0)
        # Domain comes from legal_issues.scenario_domain
        for issue in payload.get("legal_issues") or []:
            domain = str(issue.get("scenario_domain") or "").strip().lower()
            if domain:
                domain_counter[domain] += 1

    mean_confidence = (
        sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
    )
    hallucination_rate = (
        hallucination_signals["claims_rejected"] / hallucination_signals["claims_total"]
        if hallucination_signals["claims_total"]
        else 0.0
    )
    return {
        "total": len(rows),
        "recent_window": len(recent_records),
        "status_breakdown": dict(status_counter),
        "area_breakdown": dict(area_counter),
        "domain_breakdown": dict(domain_counter),
        "mean_confidence": round(mean_confidence, 3),
        "confidence_histogram": confidence_histogram,
        "claims_total": hallucination_signals["claims_total"],
        "claims_rejected": hallucination_signals["claims_rejected"],
        "hallucination_rate": round(hallucination_rate, 3),
    }


def _corpus_metrics(store: Any) -> dict[str, Any]:
    rows = store.conn.execute(
        "SELECT area, source_type, effective_from, effective_to FROM documents"
    ).fetchall()
    area_counter: Counter[str] = Counter()
    source_counter: Counter[str] = Counter()
    bucket_counter: Counter[str] = Counter()
    for row in rows:
        area_counter[row["area"] or "unknown"] += 1
        source_counter[row["source_type"] or "unknown"] += 1
        bucket_counter[_temporal_bucket(row["effective_from"], row["effective_to"])] += 1
    return {
        "documents_total": len(rows),
        "by_area": dict(area_counter),
        "by_source_type": dict(source_counter),
        "by_temporal_status": dict(bucket_counter),
    }


def _graph_metrics(store: Any) -> dict[str, Any]:
    from .entity_extractor import VALID_RELATIONS

    placeholders = ",".join(["?"] * len(VALID_RELATIONS))
    relation_counter: Counter[str] = Counter()
    rows = store.conn.execute(
        f"SELECT relation, COUNT(*) AS n FROM edges WHERE relation IN ({placeholders}) GROUP BY relation",
        list(VALID_RELATIONS),
    ).fetchall()
    for row in rows:
        relation_counter[row["relation"]] = int(row["n"])
    typed_total = sum(relation_counter.values())
    docs_total = store.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    typed_edge_density = typed_total / docs_total if docs_total else 0.0
    return {
        "typed_edges_total": typed_total,
        "by_relation": dict(relation_counter),
        "documents_total": int(docs_total),
        "typed_edge_density": round(typed_edge_density, 3),
    }


def _cache_metrics(store: Any) -> dict[str, Any]:
    total = store.conn.execute("SELECT COUNT(*) FROM llm_cache").fetchone()[0]
    by_kind_rows = store.conn.execute(
        "SELECT kind, COUNT(*) AS n FROM llm_cache GROUP BY kind"
    ).fetchall()
    by_kind = {row["kind"] or "unknown": int(row["n"]) for row in by_kind_rows}
    oldest = store.conn.execute(
        "SELECT MIN(created_at) FROM llm_cache"
    ).fetchone()[0] or ""
    newest = store.conn.execute(
        "SELECT MAX(created_at) FROM llm_cache"
    ).fetchone()[0] or ""
    return {
        "entries_total": int(total),
        "by_kind": by_kind,
        "oldest_entry": oldest,
        "newest_entry": newest,
    }


def _bucket(value: float) -> str:
    if value < 0.2:
        return "0.0-0.2"
    if value < 0.4:
        return "0.2-0.4"
    if value < 0.6:
        return "0.4-0.6"
    if value < 0.8:
        return "0.6-0.8"
    return "0.8-1.0"


def _temporal_bucket(effective_from: str, effective_to: str) -> str:
    eff_from = (effective_from or "").strip()
    eff_to = (effective_to or "").strip()
    if not eff_from and not eff_to:
        return "no_temporal_info"
    if eff_to:
        return "closed"
    return "open_ended"
