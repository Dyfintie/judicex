"""Matter-aware pre-flight check.

Before drafting the answer we summarise, per scenario, what the system is
about to do:

- which date determines the applicable law (`as_of_date`)
- which legal domain was routed to
- which articles are deemed required by the decomposer
- for every required article actually retrieved, the vigency status at that
  date plus any modification or abrogation introduced afterwards (so the
  user knows whether the version cited is the one that applied to the fact)

The check is purely deterministic — no LLM call — so it cannot itself
hallucinate. It uses the typed citation graph populated by the entity
extractor; if the graph is empty the summary still works but says so.
"""

from __future__ import annotations

from typing import Any


def run_preflight(store: Any, *, context: dict[str, Any]) -> dict[str, Any]:
    plan = context.get("decomposition") or {}
    today = (context.get("as_of_date") or "").strip()
    scenarios_out: list[dict[str, Any]] = []
    for scenario in plan.get("scenarios", []) or []:
        scenario_id = str(scenario.get("id") or "")
        domain = str(scenario.get("domain") or "")
        scenario_as_of = str(scenario.get("as_of_date") or today)
        articles = _required_articles_for_scenario(scenario, context)

        article_reports: list[dict[str, Any]] = []
        for article, doc_id in articles.items():
            article_reports.append(
                _article_report(store, article=article, doc_id=doc_id, as_of=scenario_as_of)
            )

        scenarios_out.append(
            {
                "scenario_id": scenario_id,
                "domain": domain,
                "as_of_date": scenario_as_of,
                "matter_facts": [
                    {"role": fact.get("role"), "value": fact.get("value")}
                    for fact in scenario.get("matter_facts") or []
                ],
                "articles": article_reports,
                "warnings": _scenario_warnings(article_reports, scenario_as_of),
            }
        )

    overall_warnings = _aggregate_warnings(scenarios_out)
    return {
        "as_of_date": today,
        "scenarios": scenarios_out,
        "warnings": overall_warnings,
        "graph_populated": bool((context.get("conflicts") or {}).get("graph_populated")),
    }


def _required_articles_for_scenario(
    scenario: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, str]:
    """Map each required article to the document id (if any) currently in evidence.

    Articles are deduplicated across the scenario's issues. The mapping is
    structural (article number → doc id), built from `issue_coverage` so the
    mapping reflects what retrieval actually surfaced.
    """

    articles: dict[str, str] = {}
    issue_coverage = (context.get("coverage") or {}).get("issue_coverage") or []
    coverage_by_id = {str(item.get("id") or ""): item for item in issue_coverage}
    for issue in scenario.get("issues") or []:
        issue_id = str(issue.get("id") or "")
        coverage = coverage_by_id.get(issue_id) or {}
        documents = coverage.get("documents") or []
        # Build a quick lookup of doc-id-by-article from the issue coverage.
        for article in issue.get("required_articles") or []:
            article_token = str(article).strip()
            if not article_token or article_token in articles:
                continue
            doc_id = ""
            needle = f"art{article_token}".lower()
            for doc in documents:
                doc_id_candidate = str(doc.get("id") or "")
                if needle in doc_id_candidate.lower():
                    doc_id = doc_id_candidate
                    break
            articles[article_token] = doc_id
    return articles


def _article_report(store: Any, *, article: str, doc_id: str, as_of: str) -> dict[str, Any]:
    if not doc_id:
        return {
            "article": article,
            "document_id": "",
            "status": "missing_in_corpus",
            "as_of_date": as_of,
            "modifications_since": [],
            "abrogations_since": [],
        }
    report = store.shepardize(doc_id, as_of)
    modifications_since: list[dict[str, str]] = []
    abrogations_since: list[dict[str, str]] = []
    for finding in report.get("modifications") or []:
        modifications_since.append(
            {
                "by_document_id": finding.get("source_document_id", ""),
                "summary": finding.get("summary", ""),
            }
        )
    for finding in report.get("active_abrogations") or []:
        abrogations_since.append(
            {
                "by_document_id": finding.get("source_document_id", ""),
                "summary": finding.get("summary", ""),
            }
        )
    return {
        "article": article,
        "document_id": doc_id,
        "title": report.get("title", ""),
        "status": report.get("status", "unknown"),
        "effective_from": report.get("effective_from", ""),
        "effective_to": report.get("effective_to", ""),
        "as_of_date": as_of,
        "modifications_since": modifications_since,
        "abrogations_since": abrogations_since,
    }


def _scenario_warnings(article_reports: list[dict[str, Any]], as_of: str) -> list[str]:
    warnings: list[str] = []
    for report in article_reports:
        if report["status"] == "missing_in_corpus":
            warnings.append(
                f"art. {report['article']}: non presente nel corpus, "
                f"caricalo o disabilita la richiesta."
            )
        elif report["status"] == "abrogato":
            warnings.append(
                f"art. {report['article']}: norma abrogata alla data {as_of}."
            )
        elif report["status"] == "non_vigente_per_data":
            warnings.append(
                f"art. {report['article']}: versione non in vigore alla data {as_of}, "
                f"vigente dal {report.get('effective_from')} al {report.get('effective_to') or 'oggi'}."
            )
        if report.get("abrogations_since"):
            warnings.append(
                f"art. {report['article']}: presenti abrogazioni nel grafo, "
                f"verificare se applicabili al caso."
            )
    return warnings


def _aggregate_warnings(scenarios: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    for scenario in scenarios:
        for warning in scenario.get("warnings") or []:
            scoped = f"[{scenario.get('scenario_id', '?')}] {warning}"
            if scoped not in warnings:
                warnings.append(scoped)
    return warnings
