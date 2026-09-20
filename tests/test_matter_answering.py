from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from judicex_memory_os.answering import GroundedAnswerEngine
from judicex_memory_os.models import Document
from judicex_memory_os.store import LegalMemoryStore


def _default_decomposer_plan(question: str) -> dict:
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


class RecordingClient:
    """Test client that records all calls and routes auxiliary LLM steps.

    The decomposer + numeric-rule classifier added by the new pipeline are
    answered with deterministic defaults; the existing scripted queue still
    drives intent routing, main answers, and semantic verification, in that
    order. `answer_calls` exposes only the main-answer-style invocations so
    tests can assert on the final user briefing without indexing past
    auxiliary calls.
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
            plan = self.decomposer_plan or _default_decomposer_plan(user_question)
            return json.dumps(plan, ensure_ascii=False)
        if "classificatore numerico" in system_prompt:
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
        # Distinguish the main grounded-answer / repair calls from the
        # auxiliary intent-router and semantic-verifier calls so tests can
        # index `answer_calls[0]` to reach the user briefing they care about.
        is_auxiliary = (
            "router semantico" in system_prompt
            or "verificatore legale" in system_prompt
        )
        if not is_auxiliary:
            self.answer_calls.append({"model": model, "messages": messages, "temperature": temperature})
        if not self.responses:
            raise AssertionError("RecordingClient has no queued response")
        response = self.responses.pop(0)
        if isinstance(response, str):
            return response
        return json.dumps(response, ensure_ascii=False)


class MatterAwareAnsweringTests(unittest.TestCase):
    def make_store(self) -> tuple[tempfile.TemporaryDirectory[str], LegalMemoryStore]:
        tempdir = tempfile.TemporaryDirectory()
        store = LegalMemoryStore(Path(tempdir.name) / "memory.db")
        store.upsert_document(
            Document(
                id="doc:art641",
                title="Codice procedura civile - Art. 641 - Accoglimento della domanda",
                kind="norma",
                area="civile",
                content=(
                    "Il giudice ingiunge all'altra parte di pagare nel termine di quaranta giorni, "
                    "con espresso avvertimento che nello stesso termine puo essere fatta opposizione."
                ),
                source_ref="https://example.test/art641",
            )
        )
        store.commit()
        return tempdir, store

    def test_answer_can_use_private_matter_facts_without_treating_them_as_legal_sources(self) -> None:
        tempdir, store = self.make_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        matter = store.create_matter("Recupero credito Beta", client_name="Alfa S.r.l.", area="civile")
        added = store.add_matter_document(
            matter["id"],
            title="Promemoria istruttorio",
            kind="memo",
            content=(
                "Creditore: Alfa S.r.l.; Debitore: Beta S.p.A. "
                "La fattura n. 12 del 15/01/2026 e pari a euro 1.234,56."
            ),
        )
        amount_fact = next(fact for fact in added["facts"] if fact["fact_type"] == "amount")
        matter_doc_id = added["document"]["id"]

        client = RecordingClient(
            [
                {
                    "intent": "legal_answer",
                    "confidence": 0.88,
                    "thesis": "termine di opposizione nel fascicolo Beta",
                    "reason": "serve una risposta giuridica fondata su fonte normativa",
                },
                {
                    "status": "grounded",
                    "chat_answer": "",
                    "intro": "Risposta fondata sulle fonti e sul fascicolo indicato.",
                    "case_facts": [
                        {
                            "text": "Nel fascicolo risulta una fattura di euro 1.234,56.",
                            "fact_ids": [amount_fact["id"]],
                            "document_ids": [matter_doc_id],
                        }
                    ],
                    "claims": [
                        {
                            "text": "Il debitore puo proporre opposizione nello stesso termine di quaranta giorni.",
                            "citations": ["doc:art641"],
                        }
                    ],
                    "missing_information": [],
                    "follow_up_questions": [],
                },
                {"verdicts": [{"id": "0", "supported": True, "reason": "supportato"}]},
            ]
        )
        engine = GroundedAnswerEngine(
            store=store,
            client=client,
            model="fake",
            area="civile",
            matter_id=matter["id"],
        )

        result = engine.answer("Nel fascicolo Beta, qual e il termine di opposizione?")
        # answer_calls excludes intent_router/decomposer/numeric-verifier; the first
        # entry is the main grounded-answer briefing whose user message embeds the
        # matter_context payload.
        prompt_payload = json.loads(client.answer_calls[0]["messages"][1]["content"])

        self.assertIn("matter_context", prompt_payload)
        self.assertEqual(prompt_payload["matter_context"]["matter"]["id"], matter["id"])
        self.assertIn("Fatti del fascicolo:", result["answer"])
        self.assertIn("fattura di euro 1.234,56", result["answer"])
        self.assertEqual(result["case_facts"][0]["fact_ids"], [amount_fact["id"]])
        self.assertEqual(result["citations"][0]["id"], "doc:art641")
        self.assertEqual(result["matter"]["id"], matter["id"])
        self.assertEqual(result["answer_contract"]["status"], "passed")

    def test_simple_greeting_bypasses_legal_agent_pipeline(self) -> None:
        tempdir, store = self.make_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        matter = store.create_matter("Recupero credito Beta", client_name="Alfa S.r.l.", area="civile")
        client = RecordingClient(
            [
                {
                    "intent": "chat",
                    "confidence": 0.99,
                    "thesis": "",
                    "chat_answer": "Ciao, dimmi pure come posso aiutarti con Judicex.",
                    "reason": "messaggio conversazionale semplice",
                }
            ]
        )
        engine = GroundedAnswerEngine(
            store=store,
            client=client,
            model="fake",
            area="civile",
            matter_id=matter["id"],
        )

        result = engine.answer("ciao")

        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.answer_calls, [])
        self.assertEqual(result["status"], "chat")
        self.assertIn("Ciao", result["answer"])
        self.assertEqual(result["citations"], [])
        self.assertEqual(result["agent_trace"], [])
        self.assertEqual(result["answer_contract"]["reason"], "chat_intent")

    def test_router_chat_intent_bypasses_legal_agent_pipeline(self) -> None:
        tempdir, store = self.make_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        matter = store.create_matter("Recupero credito Beta", client_name="Alfa S.r.l.", area="civile")
        client = RecordingClient(
            [
                {
                    "intent": "chat",
                    "confidence": 0.92,
                    "thesis": "",
                    "chat_answer": "",
                    "reason": "domanda sul funzionamento del sistema",
                },
                "Puoi caricare documenti nel fascicolo e poi chiedermi di cercare, riassumere o generare tabelle.",
            ]
        )
        engine = GroundedAnswerEngine(
            store=store,
            client=client,
            model="fake",
            area="civile",
            matter_id=matter["id"],
        )

        result = engine.answer("questa schermata mi confonde, cosa sto guardando?")

        self.assertEqual(result["status"], "chat")
        self.assertIn("caricare documenti", result["answer"])
        self.assertEqual(result["agent_trace"], [])
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(client.answer_calls[0]["messages"][0]["content"].startswith("Sei Judicex."), True)

    def test_mixed_operational_request_does_not_end_in_abstain_without_active_matter(self) -> None:
        tempdir, store = self.make_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        question = (
            "Un cliente deve recuperare 8.500 euro per tre fatture non pagate. "
            "Voglio capire se posso procedere con decreto ingiuntivo. Prima fammi solo "
            "le domande sui dati mancanti, poi dammi checklist documentale, rischi processuali "
            "e strategia operativa. Spiegami la differenza pratica tra diffida, messa in mora "
            "e ricorso per decreto ingiuntivo. Redigi una bozza di diffida di pagamento."
        )
        client = RecordingClient(
            [
                {
                    "intent": "matter_analysis",
                    "confidence": 0.91,
                    "thesis": "recupero credito B2B",
                    "answer_style": "strategy",
                    "requested_outputs": ["domande sui dati mancanti", "checklist", "rischi", "strategia", "bozza"],
                    "reason": "il router ha confuso la richiesta con analisi fascicolo",
                },
                {
                    "status": "abstain",
                    "chat_answer": "",
                    "intro": "Non posso rispondere con le fonti disponibili.",
                    "claims": [],
                    "case_facts": [],
                    "missing_information": [],
                    "follow_up_questions": [],
                },
                {
                    "status": "operational",
                    "chat_answer": "",
                    "intro": "Imposto il lavoro in modo operativo, separando dati mancanti e bozza prudente.",
                    "sections": [
                        {
                            "type": "questions",
                            "title": "Dati da chiarire",
                            "items": [
                                "Quali sono numero, data di emissione e scadenza delle tre fatture?",
                                "Il debitore ha contestato le prestazioni o gli importi?",
                            ],
                        },
                        {
                            "type": "checklist",
                            "title": "Checklist documentale",
                            "items": [
                                "Fatture, contratto o ordine, prova di consegna o esecuzione del servizio.",
                                "Solleciti, PEC inviate e visura del debitore.",
                            ],
                        },
                        {
                            "type": "risks",
                            "title": "Rischi processuali",
                            "items": [
                                "Contestazione del credito o prova incompleta della prestazione.",
                                "Debitore incapiente o indirizzo PEC non corretto.",
                            ],
                        },
                        {
                            "type": "strategy",
                            "title": "Strategia operativa",
                            "items": [
                                "Inviare una diffida breve e documentata prima di valutare il ricorso.",
                                "Preparare subito il fascicolo documentale per non perdere tempo se il debitore non paga.",
                            ],
                        },
                        {
                            "type": "draft",
                            "title": "Bozza diffida",
                            "content": "Oggetto: diffida di pagamento per fatture scadute. Spett.le [Debitore], Vi invitiamo a pagare euro 8.500,00 entro [termine], con riserva di agire nelle sedi competenti.",
                        },
                    ],
                    "claims": [],
                    "case_facts": [],
                    "missing_information": ["La base normativa specifica resta limitata alle fonti presenti in memoria."],
                    "follow_up_questions": [],
                },
            ]
        )
        engine = GroundedAnswerEngine(
            store=store,
            client=client,
            model="fake",
            area="civile",
        )

        result = engine.answer(question)

        self.assertEqual(result["intent_route"]["intent"], "legal_answer")
        self.assertNotIn("matter_analysis", result["intent_route"]["agent_plan"]["actions"])
        self.assertEqual(result["status"], "operational")
        self.assertIn("Dati da chiarire:", result["answer"])
        self.assertIn("Checklist documentale:", result["answer"])
        self.assertIn("Bozza diffida:", result["answer"])
        self.assertEqual(result["answer_contract"]["reason"], "status=operational")
        planning = result["agent_trace"][0]
        self.assertEqual(planning["id"], "answer_planning")
        self.assertIn("Checklist documentale", planning["detail"])

    def test_case_facts_must_reference_private_matter_context(self) -> None:
        tempdir, store = self.make_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        matter = store.create_matter("Recupero credito Beta", client_name="Alfa S.r.l.", area="civile")
        store.add_matter_document(
            matter["id"],
            title="Promemoria istruttorio",
            kind="memo",
            content="Debitore: Beta S.p.A. La fattura e pari a euro 1.234,56.",
        )
        client = RecordingClient(
            [
                {
                    "intent": "legal_answer",
                    "confidence": 0.82,
                    "thesis": "termine di opposizione nel fascicolo Beta",
                    "reason": "serve una risposta giuridica",
                },
                {
                    "status": "grounded",
                    "chat_answer": "",
                    "intro": "Risposta.",
                    "case_facts": [
                        {
                            "text": "Fatto non verificato.",
                            "fact_ids": ["matterfact:inesistente"],
                            "document_ids": [],
                        }
                    ],
                    "claims": [
                        {
                            "text": "Il debitore puo proporre opposizione nello stesso termine di quaranta giorni.",
                            "citations": ["doc:art641"],
                        }
                    ],
                    "missing_information": [],
                    "follow_up_questions": [],
                },
                {
                    "status": "abstain",
                    "chat_answer": "",
                    "intro": "Non posso validare il fatto privato indicato con la memoria del fascicolo.",
                    "case_facts": [],
                    "claims": [],
                    "missing_information": [],
                    "follow_up_questions": [],
                },
            ]
        )
        engine = GroundedAnswerEngine(
            store=store,
            client=client,
            model="fake",
            area="civile",
            matter_id=matter["id"],
        )

        result = engine.answer("Nel fascicolo Beta, qual e il termine di opposizione?")

        self.assertEqual(result["status"], "abstain")
        self.assertEqual(result["case_facts"], [])
        self.assertIn("Non posso validare", result["answer"])

    def test_missing_proof_intent_uses_deterministic_matter_analysis_after_routing(self) -> None:
        tempdir, store = self.make_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        matter = store.create_matter("Recupero credito Beta", client_name="Alfa S.r.l.", area="civile")
        store.add_matter_document(
            matter["id"],
            title="Promemoria istruttorio",
            kind="memo",
            content=(
                "Creditore: Alfa S.r.l.; Debitore: Beta S.p.A. "
                "La fattura n. 12 del 15/01/2026 e pari a euro 1.234,56."
            ),
        )
        client = RecordingClient(
            [
                {
                    "intent": "matter_analysis",
                    "confidence": 0.93,
                    "thesis": "ricorso per decreto ingiuntivo per recupero credito",
                    "reason": "l'utente chiede una valutazione di prontezza del fascicolo",
                }
            ]
        )
        engine = GroundedAnswerEngine(
            store=store,
            client=client,
            model="fake",
            area="civile",
            matter_id=matter["id"],
        )

        result = engine.answer("Valuta la solidita probatoria per procedere in monitorio con questo file.")

        self.assertEqual(len(client.calls), 1)
        self.assertEqual(result["status"], "analysis")
        self.assertEqual(result["matter_analysis"]["profile"]["id"], "civil_debt_recovery_injunction")
        self.assertIn("Elementi mancanti:", result["answer"])
        self.assertTrue(result["matter_analysis"]["missing_requirements"])
        self.assertEqual(result["intent_route"]["intent"], "matter_analysis")
        self.assertEqual(result["semantic_verifier"]["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
