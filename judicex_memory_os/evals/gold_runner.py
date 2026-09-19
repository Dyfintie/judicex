"""Gold-dataset evaluator for end-to-end answer quality.

This runner takes a JSON gold suite and executes the full agent (decomposer,
retrieval, drafting, verification, contract, citator, confidence) on each
quesito. For each one it computes:

- domain_route_accuracy: did the decomposer land on `expected_domain`?
- hallucination_rate: rejected_claims / total_claims (from answer_contract)
- citation_accuracy: |cited ∩ must_cite| / |must_cite|
- false_citation_rate: |cited ∩ must_not_cite| / |cited|
- excerpt_recall: fraction of expected_answer_excerpts found in the answer
- status_accuracy: rendered_status == expected_status
- mean_confidence: average answer_confidence.score

Aggregate metrics are produced per suite and per quesito. Designed to be
runnable in CI with `judicex eval-gold --db ... --model ... --suite ...`
and to fail (non-zero exit) when any threshold is missed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..answering import GroundedAnswerEngine
from ..llm_cache import CachedLLMClient
from ..llm_provider import make_client, resolve_settings
from ..store import LegalMemoryStore


_GOLD_DIR = Path(__file__).resolve().parent / "gold"


def list_gold_suites() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if not _GOLD_DIR.exists():
        return out
    for path in sorted(_GOLD_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.append(
            {
                "name": str(data.get("name") or path.stem),
                "path": str(path),
                "description": str(data.get("description", "")),
                "quesiti": str(len(data.get("quesiti") or [])),
            }
        )
    return out


def load_gold_suite(suite: str | Path) -> dict[str, Any]:
    candidate = Path(suite)
    if candidate.exists():
        path = candidate
    else:
        path = _GOLD_DIR / f"{suite}.json"
    if not path.exists():
        raise FileNotFoundError(f"gold suite not found: {suite}")
    data = json.loads(path.read_text(encoding="utf-8"))
    quesiti = data.get("quesiti")
    if not isinstance(quesiti, list) or not quesiti:
        raise ValueError(f"gold suite {path} has no quesiti")
    return data


def run_gold_suite(
    *,
    db_path: str,
    model: str,
    suite: str | Path,
    host: str = "http://127.0.0.1:11434",
    provider: str = "",
    base_url: str = "",
    cache_enabled: bool = True,
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    suite_data = load_gold_suite(suite)
    thresholds = {**_DEFAULT_THRESHOLDS, **(thresholds or {})}
    results: list[dict[str, Any]] = []
    with LegalMemoryStore(db_path) as store:
        settings = resolve_settings(
            store,
            default_model=model,
            ollama_host=host,
            overrides={"provider": provider, "model": model, "base_url": base_url},
        )
        base_client = make_client(settings)
        client: object = CachedLLMClient(base_client, store) if cache_enabled else base_client
        for quesito in suite_data.get("quesiti") or []:
            engine = GroundedAnswerEngine(
                store=store,
                client=client,
                model=settings["model"],
                area=quesito.get("area") or None,
                matter_id=quesito.get("matter_id") or None,
            )
            answer = engine.answer(quesito["question"])
            results.append(_score_quesito(quesito, answer))

    aggregate = _aggregate(results)
    failed_thresholds = _check_thresholds(aggregate, thresholds)
    return {
        "suite": str(suite_data.get("name") or suite),
        "model": settings["model"],
        "provider": settings["provider"],
        "thresholds": thresholds,
        "aggregate": aggregate,
        "failed_thresholds": failed_thresholds,
        "status": "passed" if not failed_thresholds else "failed",
        "quesiti": results,
    }


_DEFAULT_THRESHOLDS = {
    "hallucination_rate_max": 0.10,
    "citation_accuracy_min": 0.80,
    "false_citation_rate_max": 0.05,
    "domain_route_accuracy_min": 0.90,
    "excerpt_recall_min": 0.60,
    "status_accuracy_min": 0.80,
    "mean_confidence_min": 0.50,
}


def _score_quesito(quesito: dict[str, Any], answer: dict[str, Any]) -> dict[str, Any]:
    must_cite = {str(a).strip() for a in quesito.get("must_cite_articles", []) if str(a).strip()}
    must_not_cite = {str(a).strip() for a in quesito.get("must_not_cite_articles", []) if str(a).strip()}
    expected_domain = str(quesito.get("expected_domain") or "").strip().lower()
    expected_status = str(quesito.get("expected_status") or "").strip().lower()
    expected_excerpts = [str(e) for e in quesito.get("expected_answer_excerpts", []) if str(e)]

    cited_ids = {str(c.get("id") or "") for c in answer.get("citations") or []}
    cited_articles = _extract_article_numbers(cited_ids)

    must_cite_hits = must_cite & cited_articles
    must_not_cite_hits = must_not_cite & cited_articles
    citation_accuracy = (len(must_cite_hits) / len(must_cite)) if must_cite else 1.0
    false_citation_rate = (
        len(must_not_cite_hits) / len(cited_articles) if cited_articles else 0.0
    )

    contract = answer.get("answer_contract") or {}
    claims_total = max(int(contract.get("claims_total") or 0), 0)
    claims_rejected = max(int(contract.get("claims_rejected") or 0), 0)
    hallucination_rate = (claims_rejected / claims_total) if claims_total else 0.0

    decomposition_domains = _domains_from_trace(answer)
    if expected_domain:
        domain_match = 1.0 if expected_domain in decomposition_domains else 0.0
    else:
        domain_match = 1.0

    answer_text = str(answer.get("answer") or "").lower()
    excerpt_hits = sum(1 for excerpt in expected_excerpts if excerpt.lower() in answer_text)
    excerpt_recall = (excerpt_hits / len(expected_excerpts)) if expected_excerpts else 1.0

    status_match = 1.0 if (not expected_status or expected_status == str(answer.get("status", "")).lower()) else 0.0

    confidence = float((answer.get("answer_confidence") or {}).get("score") or 0.0)

    return {
        "id": str(quesito.get("id") or ""),
        "question": str(quesito.get("question", "")),
        "scores": {
            "domain_match": domain_match,
            "hallucination_rate": round(hallucination_rate, 3),
            "citation_accuracy": round(citation_accuracy, 3),
            "false_citation_rate": round(false_citation_rate, 3),
            "excerpt_recall": round(excerpt_recall, 3),
            "status_match": status_match,
            "confidence": round(confidence, 3),
        },
        "diagnostics": {
            "expected_domain": expected_domain,
            "observed_domains": sorted(decomposition_domains),
            "must_cite": sorted(must_cite),
            "must_cite_hits": sorted(must_cite_hits),
            "must_not_cite_hits": sorted(must_not_cite_hits),
            "cited_articles": sorted(cited_articles),
            "expected_status": expected_status,
            "observed_status": str(answer.get("status", "")),
            "claims_total": claims_total,
            "claims_rejected": claims_rejected,
        },
    }


def _domains_from_trace(answer: dict[str, Any]) -> set[str]:
    domains: set[str] = set()
    for issue in answer.get("legal_issues", []) or []:
        domain = str(issue.get("scenario_domain") or "").strip().lower()
        if domain:
            domains.add(domain)
    return domains


def _extract_article_numbers(doc_ids: set[str]) -> set[str]:
    """Pick `<digits>(?:-bis|-ter)?` tokens that immediately follow `art` in
    document ids generated by the bundle ingest path. Pure structural parse,
    no external lookup, so the eval works offline.
    """

    out: set[str] = set()
    for doc_id in doc_ids:
        lowered = doc_id.lower()
        idx = 0
        while True:
            pos = lowered.find("art", idx)
            if pos == -1:
                break
            j = pos + 3
            if j < len(lowered) and lowered[j] == ".":
                j += 1
            number_chars: list[str] = []
            while j < len(lowered) and lowered[j].isdigit():
                number_chars.append(lowered[j])
                j += 1
            suffix_chars: list[str] = []
            if j < len(lowered) and lowered[j] == "-":
                k = j + 1
                while k < len(lowered) and lowered[k].isalpha():
                    suffix_chars.append(lowered[k])
                    k += 1
                if suffix_chars:
                    j = k
            if number_chars:
                article = "".join(number_chars)
                if suffix_chars:
                    article += "-" + "".join(suffix_chars)
                out.add(article)
            idx = j if j > pos else pos + 3
    return out


def _aggregate(results: list[dict[str, Any]]) -> dict[str, float]:
    if not results:
        return {}
    scores = [r["scores"] for r in results]
    n = len(scores)
    return {
        "n": n,
        "domain_route_accuracy": round(sum(s["domain_match"] for s in scores) / n, 3),
        "hallucination_rate": round(sum(s["hallucination_rate"] for s in scores) / n, 3),
        "citation_accuracy": round(sum(s["citation_accuracy"] for s in scores) / n, 3),
        "false_citation_rate": round(sum(s["false_citation_rate"] for s in scores) / n, 3),
        "excerpt_recall": round(sum(s["excerpt_recall"] for s in scores) / n, 3),
        "status_accuracy": round(sum(s["status_match"] for s in scores) / n, 3),
        "mean_confidence": round(sum(s["confidence"] for s in scores) / n, 3),
    }


def _check_thresholds(aggregate: dict[str, float], thresholds: dict[str, float]) -> list[str]:
    failed: list[str] = []
    if aggregate.get("hallucination_rate", 1.0) > thresholds["hallucination_rate_max"]:
        failed.append("hallucination_rate")
    if aggregate.get("citation_accuracy", 0.0) < thresholds["citation_accuracy_min"]:
        failed.append("citation_accuracy")
    if aggregate.get("false_citation_rate", 1.0) > thresholds["false_citation_rate_max"]:
        failed.append("false_citation_rate")
    if aggregate.get("domain_route_accuracy", 0.0) < thresholds["domain_route_accuracy_min"]:
        failed.append("domain_route_accuracy")
    if aggregate.get("excerpt_recall", 0.0) < thresholds["excerpt_recall_min"]:
        failed.append("excerpt_recall")
    if aggregate.get("status_accuracy", 0.0) < thresholds["status_accuracy_min"]:
        failed.append("status_accuracy")
    if aggregate.get("mean_confidence", 0.0) < thresholds["mean_confidence_min"]:
        failed.append("mean_confidence")
    return failed
