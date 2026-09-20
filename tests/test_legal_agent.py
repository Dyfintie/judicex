from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from judicex_memory_os.legal_agent import LegalAgentRuntime
from judicex_memory_os.models import Document
from judicex_memory_os.store import LegalMemoryStore


class FakeLLMClient:
    """Deterministic LLM stub: returns a pre-canned JSON for the decomposer.

    The decomposer is the only LLM call performed in build_context, and it is
    invoked with `system + user` messages. We ignore the messages and emit the
    plan injected at construction time. Any other call would fail loudly.
    """

    def __init__(self, plan: dict) -> None:
        self._plan = plan
        self.calls: list[list[dict[str, str]]] = []

    def chat(self, model: str, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        self.calls.append(messages)
        return json.dumps(self._plan, ensure_ascii=False)


def _runtime(store: LegalMemoryStore, plan: dict) -> LegalAgentRuntime:
    client = FakeLLMClient(plan)
    return LegalAgentRuntime(store, client=client, model="fake-model", area="civile")


class LegalAgentRuntimeTests(unittest.TestCase):
    def make_store(self) -> tuple[tempfile.TemporaryDirectory[str], LegalMemoryStore]:
        tempdir = tempfile.TemporaryDirectory()
        store = LegalMemoryStore(Path(tempdir.name) / "memory.db")
        return tempdir, store

    def test_multissue_question_retrieves_sources_per_issue(self) -> None:
        tempdir, store = self.make_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        documents = [
            Document(
                id="cc_art2946",
                title="Codice civile - Art. 2946 - Prescrizione ordinaria",
                kind="norma",
                area="civile",
                content="Salvi i casi in cui la legge dispone diversamente, i diritti si estinguono per prescrizione con il decorso di dieci anni.",
            ),
            Document(
                id="cpc_art642",
                title="Codice procedura civile - Art. 642 - Esecuzione provvisoria",
                kind="norma",
                area="civile",
                content="Il giudice puo concedere l'esecuzione provvisoria del decreto ingiuntivo quando ricorrono i presupposti previsti.",
            ),
            Document(
                id="cpc_art641",
                title="Codice procedura civile - Art. 641 - Accoglimento della domanda",
                kind="norma",
                area="civile",
                content="Il giudice ingiunge il pagamento nel termine di quaranta giorni, con avvertimento che nello stesso termine puo essere fatta opposizione.",
            ),
            Document(
                id="cpc_art647",
                title="Codice procedura civile - Art. 647 - Esecutorieta per mancata opposizione",
                kind="norma",
                area="civile",
                content="Se non e stata fatta opposizione nel termine stabilito, il giudice dichiara esecutivo il decreto.",
            ),
        ]
        for document in documents:
            store.upsert_document(document)
        store.commit()

        plan = {
            "scenarios": [
                {
                    "id": "s1",
                    "summary": "Recupero crediti SRL contro SRL via decreto ingiuntivo",
                    "domain": "recupero_crediti",
                    "matter_facts": [
                        {"role": "importo", "value": "8.500 euro", "normalized": "8500"},
                        {"role": "data", "value": "15 gennaio 2022", "normalized": "2022-01-15"},
                    ],
                    "issues": [
                        {
                            "id": "s1.i1",
                            "title": "Prescrizione",
                            "question": "Il credito è ancora azionabile o si è prescritto?",
                            "retrieval_query": "prescrizione ordinaria diritto credito decennale art 2946",
                            "required_articles": ["2946"],
                            "coverage_terms": ["prescrizione", "credito"],
                        },
                        {
                            "id": "s1.i2",
                            "title": "Esecuzione provvisoria",
                            "question": "Posso ottenere il decreto provvisoriamente esecutivo?",
                            "retrieval_query": "esecuzione provvisoria decreto ingiuntivo art 642",
                            "required_articles": ["642"],
                            "coverage_terms": ["esecuzione", "provvisoria"],
                        },
                        {
                            "id": "s1.i3",
                            "title": "Opposizione",
                            "question": "Quali termini ha il debitore per opporsi e cosa succede senza opposizione?",
                            "retrieval_query": "opposizione decreto ingiuntivo termine art 641 art 647",
                            "required_articles": ["641", "647"],
                            "coverage_terms": ["opposizione", "termine"],
                        },
                    ],
                }
            ]
        }
        question = "tre domande sul decreto ingiuntivo"
        context = _runtime(store, plan).build_context(question)

        ids = {doc["id"] for doc in context["documents"]}
        titles = {issue["title"] for issue in context["legal_issues"]}

        self.assertIn("Prescrizione", titles)
        self.assertIn("Esecuzione provvisoria", titles)
        self.assertIn("Opposizione", titles)
        self.assertIn("cc_art2946", ids)
        self.assertIn("cpc_art642", ids)
        self.assertIn("cpc_art641", ids)
        self.assertIn("cpc_art647", ids)
        self.assertGreaterEqual(context["coverage"]["issues_covered"], 3)
        self.assertGreaterEqual(len(context["agent_trace"]), 3)

    def test_irrelevant_official_sources_do_not_cover_labor_issue(self) -> None:
        tempdir, store = self.make_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        store.upsert_document(
            Document(
                id="cpc_art650",
                title="Codice procedura civile - Art. 650 - Opposizione tardiva",
                kind="norma",
                area="civile",
                content="L'intimato puo fare opposizione tardiva quando ricorrono i presupposti previsti.",
            )
        )
        store.upsert_document(
            Document(
                id="cpc_art641",
                title="Codice procedura civile - Art. 641 - Accoglimento della domanda",
                kind="norma",
                area="civile",
                content="Il giudice ingiunge il pagamento nel termine di quaranta giorni.",
            )
        )
        store.commit()

        plan = {
            "scenarios": [
                {
                    "id": "s1",
                    "summary": "Licenziamento disciplinare",
                    "domain": "lavoro_disciplinare",
                    "matter_facts": [],
                    "issues": [
                        {
                            "id": "s1.i1",
                            "title": "Licenziamento disciplinare",
                            "question": "Conseguenze del vizio della contestazione disciplinare?",
                            "retrieval_query": "licenziamento giusta causa contestazione disciplinare art 2119 art 7",
                            "required_articles": ["2119", "7"],
                            "coverage_terms": ["licenziamento", "contestazione"],
                        }
                    ],
                }
            ]
        }
        context = _runtime(store, plan).build_context("licenziamento")
        issue_coverage = context["coverage"]["issue_coverage"]
        labor_items = [item for item in issue_coverage if item["title"] == "Licenziamento disciplinare"]

        self.assertTrue(labor_items)
        self.assertTrue(all(item["status"] == "missing_sources" for item in labor_items))
        self.assertEqual(context["coverage"]["issues_covered"], 0)

    def test_partial_coverage_when_some_required_articles_missing(self) -> None:
        tempdir, store = self.make_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        # Only art. 2946 is present; art. 2948 is required but missing.
        store.upsert_document(
            Document(
                id="cc_art2946",
                title="Codice civile - Art. 2946 - Prescrizione ordinaria",
                kind="norma",
                area="civile",
                content="I diritti si estinguono con il decorso di dieci anni.",
            )
        )
        store.commit()

        plan = {
            "scenarios": [
                {
                    "id": "s1",
                    "summary": "Prescrizione",
                    "domain": "recupero_crediti",
                    "matter_facts": [],
                    "issues": [
                        {
                            "id": "s1.i1",
                            "title": "Prescrizione",
                            "question": "ordinaria o presuntiva?",
                            "retrieval_query": "prescrizione ordinaria presuntiva art 2946 art 2948",
                            "required_articles": ["2946", "2948"],
                            "coverage_terms": ["prescrizione"],
                        }
                    ],
                }
            ]
        }
        context = _runtime(store, plan).build_context("prescrizione")
        coverage = context["coverage"]["issue_coverage"][0]
        self.assertEqual(coverage["status"], "partial")
        self.assertEqual(coverage["matched_articles"], ["2946"])
        self.assertEqual(coverage["missing_articles"], ["2948"])

    def test_scenario_isolation_keeps_retrieval_queries_separate(self) -> None:
        tempdir, store = self.make_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)
        store.commit()

        plan = {
            "scenarios": [
                {
                    "id": "s1",
                    "summary": "Recupero crediti",
                    "domain": "recupero_crediti",
                    "matter_facts": [
                        {"role": "importo", "value": "8.500 euro", "normalized": "8500"},
                    ],
                    "issues": [
                        {
                            "id": "s1.i1",
                            "title": "Prova scritta",
                            "question": "fattura come prova scritta",
                            "retrieval_query": "prova scritta fattura art 634",
                            "required_articles": ["634"],
                            "coverage_terms": ["prova", "scritta"],
                        }
                    ],
                },
                {
                    "id": "s2",
                    "summary": "Sfratto per morosità",
                    "domain": "locazioni_sfratto",
                    "matter_facts": [
                        {"role": "importo", "value": "2.400 euro", "normalized": "2400"},
                    ],
                    "issues": [
                        {
                            "id": "s2.i1",
                            "title": "Sfratto",
                            "question": "convalida sfratto morosità",
                            "retrieval_query": "sfratto morosità conduttore art 658 art 660",
                            "required_articles": ["658", "660"],
                            "coverage_terms": ["sfratto", "morosità"],
                        }
                    ],
                },
            ]
        }
        context = _runtime(store, plan).build_context("due scenari")
        retrieval_per_issue = {
            entry["issue"]["id"]: entry["issue"]["retrieval_query"]
            for entry in context["retrieval"]["issues"]
        }
        self.assertNotIn("8.500", retrieval_per_issue["s2.i1"])
        self.assertNotIn("sfratto", retrieval_per_issue["s1.i1"].lower())


if __name__ == "__main__":
    unittest.main()
