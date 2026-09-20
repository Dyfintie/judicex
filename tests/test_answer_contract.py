from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from judicex_memory_os.answering import GroundedAnswerEngine
from judicex_memory_os.models import Document
from judicex_memory_os.store import LegalMemoryStore


def _default_plan(question: str) -> dict:
    """Permissive single-issue plan for tests that don't override it.

    Uses the user question itself as the retrieval query so retrieval against
    the test store actually returns the seeded documents. No required articles
    means the coverage gate falls back to "covered if any official doc found".
    """

    return {
        "scenarios": [
            {
                "id": "s1",
                "summary": question[:120] if question else "test scenario",
                "domain": "civile_generale",
                "matter_facts": [],
                "issues": [
                    {
                        "id": "issue_1",
                        "title": "Questione giuridica",
                        "question": question or "questione",
                        "retrieval_query": question or "questione",
                        "required_articles": [],
                        "coverage_terms": [],
                    }
                ],
            }
        ]
    }


class FakeClient:
    """Test stub that intercepts decomposer + numeric-verifier calls.

    The main-answer queue stays unchanged; LLM calls added by the new pipeline
    (decomposer at the top of build_context, numeric-rule classifier inside
    enforce_answer_contract) are answered with deterministic defaults so each
    test only has to script the answers it actually cares about.
    """

    def __init__(
        self,
        responses: list[dict[str, object] | str],
        *,
        decomposer_plan: dict | None = None,
        numeric_legal_rules: list[dict[str, str]] | None = None,
    ) -> None:
        self.responses = list(responses)
        self.decomposer_plan = decomposer_plan
        self.numeric_legal_rules = numeric_legal_rules or []
        self.calls: list[dict[str, object]] = []
        self.answer_calls: list[dict[str, object]] = []

    def chat(self, *, model: str, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        self.calls.append({"model": model, "messages": messages, "temperature": temperature})
        system_prompt = messages[0]["content"] if messages else ""
        if "analizzatore di domande giuridiche" in system_prompt:
            user_question = messages[1]["content"] if len(messages) > 1 else ""
            plan = self.decomposer_plan or _default_plan(user_question)
            return json.dumps(plan, ensure_ascii=False)
        if "router semantico" in system_prompt:
            return json.dumps(
                {
                    "intent": "legal_answer",
                    "confidence": 0.9,
                    "thesis": "",
                    "chat_answer": "",
                    "reason": "quesito giuridico",
                },
                ensure_ascii=False,
            )
        if "classificatore numerico" in system_prompt:
            # Apply only the rules whose textual form is present in the claim
            # being verified. Mirrors a real LLM that wouldn't invent numbers
            # absent from the claim text.
            try:
                briefing = json.loads(messages[1]["content"]) if len(messages) > 1 else {}
            except Exception:
                briefing = {}
            claim_text = str(briefing.get("claim") or "").lower()
            applicable = [
                rule for rule in self.numeric_legal_rules
                if str(rule.get("raw") or "").lower() in claim_text
                or f"{rule.get('value')} {rule.get('unit')}".lower() in claim_text
            ]
            return json.dumps({"legal_rule_numbers": applicable}, ensure_ascii=False)
        self.answer_calls.append({"model": model, "messages": messages, "temperature": temperature})
        if not self.responses:
            raise AssertionError("FakeClient has no queued response")
        response = self.responses.pop(0)
        if isinstance(response, str):
            return response
        return json.dumps(response, ensure_ascii=False)


class AnswerContractTests(unittest.TestCase):
    def make_store(self) -> tuple[tempfile.TemporaryDirectory[str], LegalMemoryStore]:
        tempdir = tempfile.TemporaryDirectory()
        store = LegalMemoryStore(Path(tempdir.name) / "memory.db")
        store.upsert_document(
            Document(
                id="doc:art644",
                title="Codice procedura civile - Art. 644 - Mancata notificazione del decreto",
                kind="norma",
                area="civile",
                content=(
                    "Il decreto d'ingiunzione diventa inefficace qualora la notificazione non sia "
                    "eseguita nel termine di sessanta giorni dalla pronuncia e di novanta giorni negli altri casi."
                ),
                source_ref="https://example.test/art644",
            )
        )
        store.commit()
        return tempdir, store

    def test_contract_accepts_supported_numeric_claim_and_links_atom(self) -> None:
        tempdir, store = self.make_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)
        client = FakeClient(
            [
                {
                    "status": "grounded",
                    "chat_answer": "",
                    "intro": "Risposta fondata sulle fonti.",
                    "claims": [
                        {
                            "text": "La notificazione deve essere eseguita entro sessanta giorni dalla pronuncia.",
                            "citations": ["doc:art644"],
                        }
                    ],
                    "missing_information": [],
                    "follow_up_questions": [],
                },
                {"verdicts": [{"id": "0", "supported": True, "reason": "supportato"}]},
            ],
            numeric_legal_rules=[
                {"value": "60", "unit": "giorni", "action": "notificazione", "raw": "sessanta giorni"}
            ],
        )
        engine = GroundedAnswerEngine(store=store, client=client, model="fake", area="civile")

        result = engine.answer("Entro quanti giorni va notificato il decreto?")

        self.assertEqual(result["status"], "grounded")
        self.assertEqual(result["answer_contract"]["status"], "passed")
        self.assertTrue(result["evidence_trace"][0]["supporting_atoms"])

    def test_contract_blocks_numeric_claim_approved_by_llm_verifier_but_not_in_sources(self) -> None:
        tempdir, store = self.make_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)
        client = FakeClient(
            [
                {
                    "status": "grounded",
                    "chat_answer": "",
                    "intro": "Risposta fondata sulle fonti.",
                    "claims": [
                        {
                            "text": "La notificazione deve essere eseguita entro settanta giorni dalla pronuncia.",
                            "citations": ["doc:art644"],
                        }
                    ],
                    "missing_information": [],
                    "follow_up_questions": [],
                },
                {"verdicts": [{"id": "0", "supported": True, "reason": "supportato"}]},
            ],
            numeric_legal_rules=[
                {"value": "70", "unit": "giorni", "action": "notificazione", "raw": "settanta giorni"}
            ],
        )
        engine = GroundedAnswerEngine(store=store, client=client, model="fake", area="civile")

        result = engine.answer("Entro quanti giorni va notificato il decreto?")

        self.assertEqual(result["status"], "abstain")
        self.assertEqual(result["answer_contract"]["status"], "failed")
        self.assertIn("70 giorni", result["evidence_trace"][0]["violations"][0])
        self.assertNotIn("settanta giorni dalla pronuncia. [", result["answer"])

    def test_covered_issue_repairs_model_abstain_before_validation(self) -> None:
        tempdir, store = self.make_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)
        store.upsert_document(
            Document(
                id="doc:art634",
                title="Codice procedura civile - Art. 634 - Prova scritta",
                kind="norma",
                area="civile",
                content="Sono prove scritte idonee anche gli estratti autentici delle scritture contabili.",
                source_ref="https://example.test/art634",
            )
        )
        store.commit()
        client = FakeClient(
            [
                {
                    "status": "abstain",
                    "chat_answer": "",
                    "intro": "Servirebbero altre fonti.",
                    "claims": [],
                    "missing_information": [],
                    "follow_up_questions": [],
                },
                {
                    "status": "grounded",
                    "chat_answer": "",
                    "intro": "Risposta sulle fonti disponibili.",
                    "claims": [
                        {
                            "text": "L'articolo 644 disciplina la mancata notificazione del decreto d'ingiunzione.",
                            "citations": ["doc:art644"],
                        },
                        {
                            "text": "L'articolo 634 disciplina la prova scritta nel procedimento monitorio.",
                            "citations": ["doc:art634"],
                        },
                    ],
                    "missing_information": [],
                    "follow_up_questions": [],
                },
                {
                    "verdicts": [
                        {"id": "0", "supported": True, "reason": "supportato"},
                        {"id": "1", "supported": True, "reason": "supportato"},
                    ]
                },
            ]
        )
        engine = GroundedAnswerEngine(store=store, client=client, model="fake", area="civile")

        result = engine.answer("Il decreto ingiuntivo va notificato e la fattura basta come prova scritta?")

        self.assertEqual(result["status"], "grounded")
        self.assertEqual(result["answer_contract"]["status"], "passed")
        self.assertIn("Correzione astensione", [step["title"] for step in result["agent_trace"]])

    def test_covered_issue_repairs_fallback_abstain_after_json_failures(self) -> None:
        tempdir, store = self.make_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)
        client = FakeClient(
            [
                "non-json",
                "ancora non-json",
                "Non posso rispondere con le fonti disponibili.",
                {
                    "status": "grounded",
                    "chat_answer": "",
                    "intro": "Risposta sulle fonti disponibili.",
                    "claims": [
                        {
                            "text": "Il decreto d'ingiunzione diventa inefficace se la notificazione non e eseguita nel termine di sessanta giorni dalla pronuncia.",
                            "citations": ["doc:art644"],
                        }
                    ],
                    "missing_information": [],
                    "follow_up_questions": [],
                },
                {"verdicts": [{"id": "0", "supported": True, "reason": "supportato"}]},
            ],
            numeric_legal_rules=[
                {"value": "60", "unit": "giorni", "action": "notificazione", "raw": "sessanta giorni"}
            ],
        )
        engine = GroundedAnswerEngine(store=store, client=client, model="fake", area="civile")

        result = engine.answer("Entro quando va notificato il decreto ingiuntivo?")

        self.assertEqual(result["status"], "grounded")
        self.assertEqual(result["answer_contract"]["status"], "passed")
        self.assertIn("Correzione astensione", [step["title"] for step in result["agent_trace"]])

    def test_abstain_repair_keeps_valid_claims_and_drops_uncited_claims(self) -> None:
        tempdir, store = self.make_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)
        client = FakeClient(
            [
                {
                    "status": "abstain",
                    "chat_answer": "",
                    "intro": "Servirebbero altre fonti.",
                    "claims": [],
                    "missing_information": [],
                    "follow_up_questions": [],
                },
                {
                    "status": "limited",
                    "chat_answer": "",
                    "intro": "Risposta sulle fonti disponibili.",
                    "claims": [
                        {
                            "text": "Il decreto d'ingiunzione diventa inefficace se la notificazione non e eseguita nel termine di sessanta giorni dalla pronuncia.",
                            "citations": ["doc:art644"],
                        },
                        {
                            "text": "Per altre questioni servono fonti ulteriori.",
                            "citations": [],
                        },
                    ],
                    "missing_information": [],
                    "follow_up_questions": [],
                },
                {"verdicts": [{"id": "0", "supported": True, "reason": "supportato"}]},
            ],
            numeric_legal_rules=[
                {"value": "60", "unit": "giorni", "action": "notificazione", "raw": "sessanta giorni"}
            ],
        )
        engine = GroundedAnswerEngine(store=store, client=client, model="fake", area="civile")

        result = engine.answer("Entro quando va notificato il decreto ingiuntivo?")

        self.assertEqual(result["status"], "limited")
        self.assertEqual(result["answer_contract"]["status"], "passed")
        self.assertNotIn("Per altre questioni", result["answer"])

    def test_missing_covered_issue_triggers_completion_repair(self) -> None:
        tempdir, store = self.make_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)
        store.upsert_document(
            Document(
                id="doc:art2946",
                title="Codice civile - Art. 2946 - Prescrizione ordinaria",
                kind="norma",
                area="civile",
                content="Salvi i casi in cui la legge dispone diversamente, i diritti si estinguono per prescrizione con il decorso di dieci anni.",
                source_ref="https://example.test/art2946",
            )
        )
        store.upsert_document(
            Document(
                id="doc:art634",
                title="Codice procedura civile - Art. 634 - Prova scritta",
                kind="norma",
                area="civile",
                content="Per le prestazioni di servizi sono prove scritte idonee le fatture elettroniche e gli estratti autentici delle scritture contabili.",
                source_ref="https://example.test/art634",
            )
        )
        store.commit()
        client = FakeClient(
            [
                {
                    "status": "grounded",
                    "chat_answer": "",
                    "intro": "Risposta sulle fonti disponibili.",
                    "claims": [
                        {
                            "text": "L'articolo 634 disciplina la prova scritta nel procedimento monitorio.",
                            "citations": ["doc:art634"],
                        }
                    ],
                    "missing_information": [],
                    "follow_up_questions": [],
                },
                {
                    "status": "grounded",
                    "chat_answer": "",
                    "intro": "Risposta integrata sulle fonti disponibili.",
                    "claims": [
                        {
                            "text": "Il termine ordinario di prescrizione dei diritti e di dieci anni.",
                            "issue_ids": ["issue_1"],
                            "citations": ["doc:art2946"],
                        },
                        {
                            "text": "L'articolo 634 disciplina la prova scritta nel procedimento monitorio.",
                            "issue_ids": ["issue_2"],
                            "citations": ["doc:art634"],
                        },
                    ],
                    "missing_information": [],
                    "follow_up_questions": [],
                },
                {
                    "verdicts": [
                        {"id": "0", "supported": True, "reason": "supportato"},
                        {"id": "1", "supported": True, "reason": "supportato"},
                    ]
                },
            ],
            decomposer_plan={
                "scenarios": [
                    {
                        "id": "s1",
                        "summary": "Prescrizione e prova scritta",
                        "domain": "recupero_crediti",
                        "matter_facts": [],
                        "issues": [
                            {
                                "id": "issue_1",
                                "title": "Prescrizione",
                                "question": "Il credito è prescritto?",
                                "retrieval_query": "prescrizione ordinaria credito art 2946",
                                "required_articles": ["2946"],
                                "coverage_terms": ["prescrizione"],
                            },
                            {
                                "id": "issue_2",
                                "title": "Prova scritta",
                                "question": "La fattura basta come prova scritta?",
                                "retrieval_query": "prova scritta fattura art 634",
                                "required_articles": ["634"],
                                "coverage_terms": ["prova", "scritta"],
                            },
                        ],
                    }
                ]
            },
            numeric_legal_rules=[
                {"value": "10", "unit": "anni", "action": "prescrizione", "raw": "dieci anni"}
            ],
        )
        engine = GroundedAnswerEngine(store=store, client=client, model="fake", area="civile")

        result = engine.answer("Il credito e prescritto? La fattura basta come prova scritta?")

        self.assertEqual(result["status"], "grounded")
        self.assertEqual(result["answer_contract"]["status"], "passed")
        self.assertIn("doc:art2946", {citation["id"] for citation in result["citations"]})
        self.assertIn("Completamento issue coperte", [step["title"] for step in result["agent_trace"]])


if __name__ == "__main__":
    unittest.main()
