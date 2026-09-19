from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from .conflict_detector import detect_conflicts
from .decomposer import DecompositionError, decompose, fallback_plan, fallback_plan_today
from .store import LegalMemoryStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class LLMClient(Protocol):
    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
    ) -> str: ...


@dataclass(slots=True)
class AgentTraceStep:
    id: str
    title: str
    status: str = "pending"
    detail: str = ""
    tool: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    started_at: str = field(default_factory=_now_iso)
    completed_at: str = ""

    def complete(
        self,
        *,
        status: str = "completed",
        detail: str | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> "AgentTraceStep":
        self.status = status
        if detail is not None:
            self.detail = detail
        if metrics:
            self.metrics.update(metrics)
        self.completed_at = _now_iso()
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
            "tool": self.tool,
            "metrics": self.metrics,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


@dataclass(slots=True)
class LegalIssue:
    """A single legal question planned by the decomposer.

    `scenario_id` keeps issues from independent matter scenarios separated:
    retrieval queries are scenario-local, so facts of one scenario never
    bleed into the search for another.
    """

    id: str
    title: str
    question: str
    retrieval_query: str
    scenario_id: str = ""
    scenario_domain: str = ""
    scenario_as_of_date: str = ""
    coverage_terms: list[str] = field(default_factory=list)
    required_articles: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "question": self.question,
            "retrieval_query": self.retrieval_query,
            "scenario_id": self.scenario_id,
            "scenario_domain": self.scenario_domain,
            "scenario_as_of_date": self.scenario_as_of_date,
            "coverage_terms": self.coverage_terms,
            "required_articles": self.required_articles,
        }


class LegalAgentRuntime:
    """Controlled legal agent loop for retrieval, coverage and visible audit trace.

    Decomposition, classification and coverage assessment are LLM-driven so the
    pipeline works for any legal domain without keyword tables. Source matching
    against retrieved documents is structural: it relies on article numbers
    declared by the decomposer and the URN-based document identifiers we
    control, not on free-text heuristics.
    """

    def __init__(
        self,
        store: LegalMemoryStore,
        *,
        client: LLMClient | None = None,
        model: str | None = None,
        area: str | None = None,
    ) -> None:
        self.store = store
        self.client = client
        self.model = model
        self.area = area

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def build_context(
        self,
        question: str,
        *,
        base_doc_k: int = 6,
        issue_doc_k: int = 4,
        max_documents: int = 10,
        as_of_date: str = "",
    ) -> dict[str, Any]:
        trace: list[AgentTraceStep] = []

        plan_step = AgentTraceStep(
            id="analyse_request",
            title="Analisi richiesta",
            status="running",
            detail="Scomposizione della domanda in scenari e questioni giuridiche.",
            tool="LLM.decompose",
        )
        trace.append(plan_step)
        plan, plan_status, plan_detail = self._plan(question)
        plan = self._resolve_scenario_dates(plan, override=as_of_date)
        issues = self._issues_from_plan(plan)
        plan_step.complete(
            status=plan_status,
            detail=plan_detail,
            metrics={
                "scenarios": len(plan.get("scenarios", [])),
                "issues": len(issues),
                "domains": sorted(
                    {
                        scenario.get("domain", "altro")
                        for scenario in plan.get("scenarios", [])
                    }
                ),
            },
        )

        retrieval_step = AgentTraceStep(
            id="source_retrieval",
            title="Ricerca fonti",
            status="running",
            detail="Recupero fonti generali e fonti mirate per ciascuna questione.",
            tool="LegalMemoryStore.build_context",
        )
        trace.append(retrieval_step)
        global_as_of = as_of_date or fallback_plan_today()
        base_context = self.store.build_context(
            question,
            area=self.area,
            doc_k=base_doc_k,
            as_of_date=global_as_of,
        )
        issue_contexts = [
            {
                "issue": issue,
                "context": self.store.build_context(
                    issue.retrieval_query,
                    area=self.area,
                    doc_k=issue_doc_k,
                    as_of_date=issue.scenario_as_of_date or global_as_of,
                ),
            }
            for issue in issues
        ]

        issue_coverage = self._issue_coverage(issue_contexts)
        covered_issue_ids = {
            item["id"] for item in issue_coverage if item["status"] == "covered"
        }
        merged = self._merge_contexts(
            base_context,
            issue_contexts,
            max_documents=max_documents,
            covered_issue_ids=covered_issue_ids,
        )
        retrieval_step.complete(
            detail=(
                f"Recuperate {merged['coverage']['official_documents']} fonti ufficiali "
                f"su {merged['coverage']['documents_total']} documenti disponibili nel contesto."
            ),
            metrics={
                "candidate_documents": merged["coverage"].get("candidate_documents", 0),
                "documents_total": merged["coverage"].get("documents_total", 0),
                "legal_atoms": merged["coverage"].get("legal_atoms", 0),
            },
        )

        coverage_step = AgentTraceStep(
            id="coverage_gate",
            title="Verifica copertura",
            status="running",
            detail="Controllo che ogni questione abbia tutti gli articoli richiesti.",
        )
        trace.append(coverage_step)
        covered = sum(1 for item in issue_coverage if item["status"] == "covered")
        partial = sum(1 for item in issue_coverage if item["status"] == "partial")
        missing = sum(1 for item in issue_coverage if item["status"] == "missing_sources")
        coverage_status = "completed" if covered == len(issue_coverage) and issue_coverage else "limited"
        coverage_step.complete(
            status=coverage_status,
            detail=(
                f"{covered} coperte, {partial} parziali, {missing} senza fonti "
                f"su {len(issue_coverage)} questioni."
            ),
            metrics={"issues": issue_coverage},
        )

        domain_step = self._domain_alignment_step(plan)
        if domain_step is not None:
            trace.append(domain_step)

        conflict_step = AgentTraceStep(
            id="conflict_detection",
            title="Rilevazione conflitti / abrogazioni",
            status="running",
            detail="Verifico vigenza e relazioni nel grafo per ogni fonte recuperata.",
            tool="LegalMemoryStore.shepardize",
        )
        trace.append(conflict_step)
        all_evidence_docs = (merged.get("documents") or []) + (merged.get("related_documents") or [])
        conflicts_report = detect_conflicts(
            self.store,
            documents=all_evidence_docs,
            as_of_date=global_as_of,
        )
        if conflicts_report["graph_populated"]:
            blocked = len(conflicts_report["blocked_document_ids"])
            warnings = len(conflicts_report["warning_document_ids"])
            conflict_step.complete(
                status="completed" if not blocked else "limited",
                detail=(
                    f"{blocked} fonti bloccate per abrogazione, {warnings} con avvisi "
                    f"(modifiche/deroghe/contrasti) sui {len(all_evidence_docs)} documenti recuperati."
                ),
                metrics={
                    "blocked": blocked,
                    "warnings": warnings,
                    "examined": len(conflicts_report["examined_documents"]),
                },
            )
        else:
            conflict_step.complete(
                status="limited",
                detail=(
                    "Grafo citatorio non popolato: esegui `extract-references` per "
                    "abilitare la rilevazione di abrogazioni e contrasti."
                ),
                metrics={"graph_populated": False},
            )

        merged["legal_issues"] = [issue.to_dict() for issue in issues]
        merged["decomposition"] = plan
        merged["as_of_date"] = global_as_of
        merged["conflicts"] = conflicts_report
        merged["coverage"]["issue_coverage"] = issue_coverage
        merged["coverage"]["issues_total"] = len(issue_coverage)
        merged["coverage"]["issues_covered"] = covered
        merged["coverage"]["issues_partial"] = partial
        merged["coverage"]["issues_missing"] = missing
        merged["agent_trace"] = [step.to_dict() for step in trace]
        return merged

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    def _plan(self, question: str) -> tuple[dict[str, Any], str, str]:
        if self.client is None or not self.model:
            plan = fallback_plan(question)
            return (
                plan,
                "limited",
                "Nessun client LLM configurato: scomposizione disattivata, uso degenerato.",
            )
        try:
            plan = decompose(self.client, self.model, question)
        except DecompositionError as exc:
            plan = fallback_plan(question)
            return (
                plan,
                "limited",
                f"Decomposer LLM fallito ({exc}): uso piano degenerato.",
            )
        scenarios = plan.get("scenarios", [])
        issues = sum(len(scenario.get("issues", [])) for scenario in scenarios)
        return (
            plan,
            "completed",
            f"Identificati {len(scenarios)} scenari e {issues} questioni operative.",
        )

    @staticmethod
    def _issues_from_plan(plan: dict[str, Any]) -> list[LegalIssue]:
        issues: list[LegalIssue] = []
        for scenario in plan.get("scenarios", []) or []:
            scenario_id = str(scenario.get("id") or "")
            scenario_domain = str(scenario.get("domain") or "altro")
            scenario_as_of = str(scenario.get("as_of_date") or "")
            for raw_issue in scenario.get("issues", []) or []:
                issues.append(
                    LegalIssue(
                        id=str(raw_issue.get("id") or ""),
                        title=str(raw_issue.get("title") or "Questione giuridica"),
                        question=str(raw_issue.get("question") or ""),
                        retrieval_query=str(raw_issue.get("retrieval_query") or ""),
                        scenario_id=scenario_id,
                        scenario_domain=scenario_domain,
                        scenario_as_of_date=scenario_as_of,
                        coverage_terms=list(raw_issue.get("coverage_terms") or []),
                        required_articles=list(raw_issue.get("required_articles") or []),
                    )
                )
        return issues

    @staticmethod
    def _resolve_scenario_dates(plan: dict[str, Any], *, override: str = "") -> dict[str, Any]:
        """Resolve each scenario's `as_of_date` to a concrete ISO string.

        - explicit `override` from the caller wins for every scenario;
        - otherwise the LLM-supplied date is kept;
        - missing or malformed dates fall back to today's UTC date so the
          retrieval layer always operates with a concrete temporal anchor.
        """

        today = fallback_plan_today()
        resolved: list[dict[str, Any]] = []
        for scenario in plan.get("scenarios", []) or []:
            entry = dict(scenario)
            if override:
                entry["as_of_date"] = override
            elif not entry.get("as_of_date"):
                entry["as_of_date"] = today
            resolved.append(entry)
        return {**plan, "scenarios": resolved}

    @staticmethod
    def _domain_alignment_step(plan: dict[str, Any]) -> AgentTraceStep | None:
        scenarios = plan.get("scenarios", []) or []
        if not scenarios:
            return None
        domains = sorted({scenario.get("domain", "altro") for scenario in scenarios})
        step = AgentTraceStep(
            id="domain_alignment",
            title="Riconoscimento dominio",
            status="completed",
            detail=f"Domini individuati: {', '.join(domains) or 'nessuno'}.",
            metrics={"domains": domains},
        )
        step.complete()
        return step

    # ------------------------------------------------------------------
    # Coverage
    # ------------------------------------------------------------------

    @staticmethod
    def _issue_coverage(issue_contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for item in issue_contexts:
            issue: LegalIssue = item["issue"]
            context = item["context"]
            docs = context.get("documents", []) + context.get("related_documents", [])
            official_docs = [doc for doc in docs if doc.get("source_type") == "official"]

            article_status = LegalAgentRuntime._article_match_status(issue, official_docs)
            relevant_docs = article_status["matching_docs"]

            if issue.required_articles:
                if article_status["matched_count"] == len(issue.required_articles):
                    status = "covered"
                elif article_status["matched_count"] > 0:
                    status = "partial"
                else:
                    status = "missing_sources"
            else:
                # No required articles declared: fall back to "any official doc"
                # signal. This keeps the gate working when the decomposer cannot
                # name specific articles (rare, exploratory questions).
                status = "covered" if official_docs else "missing_sources"
                relevant_docs = official_docs

            display_docs = relevant_docs or docs[:6]
            out.append(
                {
                    **issue.to_dict(),
                    "status": status,
                    "documents": [
                        {
                            "id": doc.get("id"),
                            "title": doc.get("title"),
                            "source_ref": doc.get("source_ref"),
                            "source_type": doc.get("source_type"),
                        }
                        for doc in display_docs[:6]
                    ],
                    "official_documents": len(relevant_docs),
                    "retrieved_official_documents": len(official_docs),
                    "matched_articles": article_status["matched_articles"],
                    "missing_articles": article_status["missing_articles"],
                    "legal_atoms": int((context.get("coverage") or {}).get("legal_atoms", 0)),
                }
            )
        return out

    @staticmethod
    def _article_match_status(
        issue: LegalIssue,
        docs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Match required article numbers against retrieved documents structurally.

        Document identifiers we generate look like
        `normattiva:<bundle>:<code>_art<NUMBER>`, and Normattiva URNs end with
        `~art<NUMBER>!vig=...`. We look for the literal token `art<NUMBER>` in
        the doc id / source_ref and require the next character not to be a
        digit (so "art63" doesn't match "art633"). No keyword regex.
        """

        matched_articles: list[str] = []
        missing_articles: list[str] = []
        matching_docs_index: dict[str, dict[str, Any]] = {}

        for article in issue.required_articles:
            needle = f"art{article}".lower()
            article_hit = False
            for doc in docs:
                haystack = " ".join(
                    [
                        str(doc.get("id") or ""),
                        str(doc.get("source_ref") or ""),
                    ]
                ).lower()
                if LegalAgentRuntime._token_present(haystack, needle):
                    article_hit = True
                    doc_id = str(doc.get("id") or "")
                    if doc_id and doc_id not in matching_docs_index:
                        matching_docs_index[doc_id] = doc
            if article_hit:
                matched_articles.append(article)
            else:
                missing_articles.append(article)

        return {
            "matched_articles": matched_articles,
            "missing_articles": missing_articles,
            "matched_count": len(matched_articles),
            "matching_docs": list(matching_docs_index.values()),
        }

    @staticmethod
    def _token_present(haystack: str, needle: str) -> bool:
        """Return True if `needle` appears in `haystack` not followed by a digit."""
        if not needle:
            return False
        position = haystack.find(needle)
        while position != -1:
            end = position + len(needle)
            if end >= len(haystack) or not haystack[end].isdigit():
                return True
            position = haystack.find(needle, end)
        return False

    @staticmethod
    def _doc_supports_issue(doc: dict[str, Any], issue: LegalIssue) -> bool:
        if not issue.required_articles:
            return True
        haystack = " ".join(
            [
                str(doc.get("id") or ""),
                str(doc.get("source_ref") or ""),
            ]
        ).lower()
        return any(
            LegalAgentRuntime._token_present(haystack, f"art{article}".lower())
            for article in issue.required_articles
        )

    # ------------------------------------------------------------------
    # Context merge (preserved from previous design)
    # ------------------------------------------------------------------

    def _merge_contexts(
        self,
        base_context: dict[str, Any],
        issue_contexts: list[dict[str, Any]],
        *,
        max_documents: int,
        covered_issue_ids: set[str] | None = None,
    ) -> dict[str, Any]:
        covered_issue_ids = covered_issue_ids or set()
        documents = self._unique_documents(
            [
                doc
                for item in issue_contexts
                if item["issue"].id in covered_issue_ids
                for doc in item["context"].get("documents", [])
                if self._doc_supports_issue(doc, item["issue"])
            ]
            + base_context.get("documents", []),
            limit=max_documents,
        )
        document_ids = {doc["id"] for doc in documents}
        related_documents = self._unique_documents(
            base_context.get("related_documents", [])
            + [
                doc
                for item in issue_contexts
                if item["issue"].id in covered_issue_ids
                for doc in item["context"].get("related_documents", [])
                if self._doc_supports_issue(doc, item["issue"])
            ],
            exclude=document_ids,
            limit=max(0, max_documents - len(documents)),
        )
        evidence_documents = documents + related_documents
        evidence_ids = {doc["id"] for doc in evidence_documents}

        merged = dict(base_context)
        merged["documents"] = documents
        merged["related_documents"] = related_documents
        merged["entities"] = self._unique_by_id(
            base_context.get("entities", [])
            + [entity for item in issue_contexts for entity in item["context"].get("entities", [])],
            limit=20,
        )
        merged["legal_atoms"] = self._unique_by_id(
            [
                atom
                for atom in base_context.get("legal_atoms", [])
                + [atom for item in issue_contexts for atom in item["context"].get("legal_atoms", [])]
                if atom.get("document_id") in evidence_ids
            ],
            limit=30,
        )
        merged["relationships"] = self._unique_by_id(
            base_context.get("relationships", [])
            + [edge for item in issue_contexts for edge in item["context"].get("relationships", [])],
            limit=30,
        )
        official_documents = [doc for doc in evidence_documents if doc.get("source_type") == "official"]
        merged["coverage"] = {
            **base_context.get("coverage", {}),
            "documents_total": len(evidence_documents),
            "documents_primary": len(documents),
            "documents_related": len(related_documents),
            "official_documents": len(official_documents),
            "candidate_documents": sum(
                int((item["context"].get("coverage") or {}).get("candidate_documents", 0))
                for item in issue_contexts
            )
            + int((base_context.get("coverage") or {}).get("candidate_documents", 0)),
            "retrieval_queries": sum(
                int((item["context"].get("coverage") or {}).get("retrieval_queries", 0))
                for item in issue_contexts
            )
            + int((base_context.get("coverage") or {}).get("retrieval_queries", 0)),
            "legal_atoms": len(merged["legal_atoms"]),
        }
        merged["retrieval"] = {
            "base": base_context.get("retrieval", {}),
            "issues": [
                {
                    "issue": item["issue"].to_dict(),
                    "retrieval": item["context"].get("retrieval", {}),
                }
                for item in issue_contexts
            ],
        }
        merged["citations"] = [
            {
                "id": doc["id"],
                "title": doc["title"],
                "source_ref": doc["source_ref"],
                "authority": doc["authority"],
                "effective_from": doc["effective_from"],
                "effective_to": doc["effective_to"],
            }
            for doc in evidence_documents
        ]
        return merged

    @staticmethod
    def _unique_documents(
        documents: list[dict[str, Any]],
        *,
        limit: int,
        exclude: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        exclude = exclude or set()
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for doc in documents:
            doc_id = str(doc.get("id", "")).strip()
            if not doc_id or doc_id in seen or doc_id in exclude:
                continue
            seen.add(doc_id)
            out.append(doc)
            if len(out) >= limit:
                break
        return out

    @staticmethod
    def _unique_by_id(items: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for item in items:
            item_id = str(item.get("id", "")).strip()
            if not item_id or item_id in seen:
                continue
            seen.add(item_id)
            out.append(item)
            if len(out) >= limit:
                break
        return out
