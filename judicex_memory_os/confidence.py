"""Confidence calibration for the final answer.

We expose the answer's reliability as a single calibrated number in [0, 1]
plus a breakdown so the user (and downstream gates) can see what is dragging
the score up or down. The number is *not* a probability of correctness — it
is a transparent aggregate of signals the pipeline already produces:

- coverage_score:     issues fully covered / total issues
- article_score:      mean (matched_articles / required_articles) per covered issue
- retention_score:    claims_retained / claims_total from the answer contract
- semantic_score:     1.0 passed / 0.5 limited / 0.0 failed (from semantic verifier)
- conflict_score:     1 − weighted penalty for blocked/warning citations
- temporal_score:     1 − share of evidence excluded by date filter

Each signal is bounded to [0, 1]; the final score is their weighted mean.
The breakdown is included so dashboards can plot every component.
"""

from __future__ import annotations

from typing import Any


_WEIGHTS = {
    "coverage": 0.20,
    "article": 0.15,
    "retention": 0.20,
    "semantic": 0.15,
    "conflict": 0.20,
    "temporal": 0.10,
}


def compute_confidence(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    coverage = context.get("coverage") or {}
    issues_total = max(int(coverage.get("issues_total") or 0), 0)
    issues_covered = max(int(coverage.get("issues_covered") or 0), 0)
    issues_partial = max(int(coverage.get("issues_partial") or 0), 0)
    coverage_score = (
        (issues_covered + 0.5 * issues_partial) / issues_total if issues_total else 1.0
    )

    article_score = _article_match_score(coverage)

    contract = payload.get("_answer_contract") or {}
    claims_total = max(int(contract.get("claims_total") or 0), 0)
    claims_retained = max(int(contract.get("claims_retained") or 0), 0)
    if not claims_total:
        retention_score = 0.0 if payload.get("status") == "abstain" else 1.0
    else:
        retention_score = claims_retained / claims_total

    verifier = payload.get("_semantic_verifier") or {}
    verifier_status = str(verifier.get("status") or "").lower()
    if verifier_status == "passed":
        semantic_score = 1.0
    elif verifier_status == "limited":
        semantic_score = 0.5
    elif verifier_status in {"failed", "abstain"}:
        semantic_score = 0.0
    else:
        semantic_score = 1.0 if payload.get("status") in {"grounded", "limited", "chat", "operational"} else 0.0

    conflicts = context.get("conflicts") or {}
    blocked = len(conflicts.get("blocked_document_ids") or [])
    warnings = len(conflicts.get("warning_document_ids") or [])
    documents_total = max(int(coverage.get("documents_total") or 0), 1)
    conflict_score = max(0.0, 1.0 - (blocked / documents_total) - 0.25 * (warnings / documents_total))

    excluded_by_date = max(int(coverage.get("excluded_by_date") or 0), 0)
    candidates = max(int(coverage.get("candidate_documents") or 0), 0)
    if candidates:
        temporal_score = max(0.0, 1.0 - excluded_by_date / max(candidates, 1))
    else:
        temporal_score = 1.0

    components = {
        "coverage": _clamp(coverage_score),
        "article": _clamp(article_score),
        "retention": _clamp(retention_score),
        "semantic": _clamp(semantic_score),
        "conflict": _clamp(conflict_score),
        "temporal": _clamp(temporal_score),
    }
    score = sum(components[name] * _WEIGHTS[name] for name in _WEIGHTS)
    return {
        "score": round(_clamp(score), 3),
        "label": _label(score),
        "components": {name: round(value, 3) for name, value in components.items()},
        "weights": dict(_WEIGHTS),
        "signals": {
            "issues_total": issues_total,
            "issues_covered": issues_covered,
            "issues_partial": issues_partial,
            "claims_total": claims_total,
            "claims_retained": claims_retained,
            "blocked_document_ids": list(conflicts.get("blocked_document_ids") or []),
            "warning_document_ids": list(conflicts.get("warning_document_ids") or []),
            "excluded_by_date": excluded_by_date,
            "documents_total": documents_total,
            "verifier_status": verifier_status or "unknown",
        },
    }


def _article_match_score(coverage: dict[str, Any]) -> float:
    issue_coverage = coverage.get("issue_coverage") or []
    if not issue_coverage:
        return 1.0
    ratios: list[float] = []
    for entry in issue_coverage:
        required = entry.get("required_articles") or []
        matched = entry.get("matched_articles") or []
        if not required:
            ratios.append(1.0)
            continue
        ratios.append(min(1.0, len(matched) / len(required)))
    if not ratios:
        return 1.0
    return sum(ratios) / len(ratios)


def _label(score: float) -> str:
    if score >= 0.85:
        return "alta"
    if score >= 0.6:
        return "media"
    if score >= 0.35:
        return "bassa"
    return "molto_bassa"


def _clamp(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return float(value)
