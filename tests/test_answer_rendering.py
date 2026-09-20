from __future__ import annotations

import unittest

from judicex_memory_os.answering import GroundedAnswerEngine


class AnswerRenderingTests(unittest.TestCase):
    def test_internal_verifier_messages_are_not_rendered_to_user(self) -> None:
        engine = GroundedAnswerEngine(store=None, client=None, model="test")
        payload = {
            "status": "limited",
            "chat_answer": "",
            "intro": "Sulla base delle fonti disponibili.",
            "claims": [
                {
                    "text": "Il debitore puo proporre opposizione nel termine di quaranta giorni.",
                    "citations": ["doc:art641"],
                }
            ],
            "missing_information": [
                "Affermazione rimossa dal verificatore: motivo tecnico interno",
                "Manca la residenza del debitore per distinguere i regimi territoriali.",
                "Mancano gli articoli 633, 635 e 640 necessari per descrivere il procedimento.",
            ],
            "follow_up_questions": [
                "Si desidera chiarimenti su eventuali giusti motivi?",
                "Occorre sapere se il debitore risiede in Italia, UE o extra-UE.",
            ],
            "_semantic_verifier": {"status": "limited", "claims_rejected": 1},
            "_answer_contract": {"status": "limited", "claims_rejected": 1},
        }
        context = {
            "coverage": {},
            "documents": [
                {
                    "id": "doc:art641",
                    "title": "Codice procedura civile - Art. 641",
                    "source_ref": "https://example.test/art641",
                }
            ],
            "related_documents": [],
        }

        result = engine._render(payload, context)

        self.assertNotIn("Affermazione rimossa", result["answer"])
        self.assertNotIn("633", result["answer"])
        self.assertNotIn("Servono questi elementi", result["answer"])
        self.assertIn("Dati da chiarire:", result["answer"])
        self.assertIn("Occorre sapere se il debitore risiede in Italia", result["answer"])
        self.assertEqual(
            result["limits"],
            [
                "Manca la residenza del debitore per distinguere i regimi territoriali.",
                "La risposta resta limitata alle fonti disponibili nella memoria locale.",
            ],
        )
        self.assertEqual(
            result["follow_up_questions"],
            ["Occorre sapere se il debitore risiede in Italia, UE o extra-UE."],
        )
        self.assertEqual(result["semantic_verifier"]["claims_rejected"], 1)

    def test_no_limits_line_when_only_internal_limits_exist(self) -> None:
        engine = GroundedAnswerEngine(store=None, client=None, model="test")
        payload = {
            "status": "limited",
            "chat_answer": "",
            "intro": "",
            "claims": [{"text": "Termine di sessanta giorni.", "citations": ["doc:art644"]}],
            "missing_information": ["Claim rimosso dal citation gate: affermazione non supportata"],
            "follow_up_questions": [],
        }
        context = {
            "coverage": {},
            "documents": [
                {
                    "id": "doc:art644",
                    "title": "Codice procedura civile - Art. 644",
                    "source_ref": "https://example.test/art644",
                }
            ],
            "related_documents": [],
        }

        result = engine._render(payload, context)

        self.assertNotIn("Limiti:", result["answer"])
        self.assertEqual(result["limits"], [])

    def test_operational_sections_do_not_require_legal_claims(self) -> None:
        engine = GroundedAnswerEngine(store=None, client=None, model="test")
        payload = {
            "status": "operational",
            "chat_answer": "",
            "intro": "Prima raccolgo solo i dati necessari.",
            "sections": [
                {
                    "type": "questions",
                    "title": "Dati da chiarire",
                    "items": [
                        "Quali sono numero, data e scadenza delle tre fatture?",
                        "Il debitore ha contestato formalmente le fatture?",
                    ],
                }
            ],
            "claims": [],
            "missing_information": [],
            "follow_up_questions": [],
        }
        context = {"coverage": {}, "documents": [], "related_documents": []}

        validated = engine._validate_payload(payload, set(), context)
        result = engine._render(validated, context)

        self.assertEqual(result["status"], "operational")
        self.assertEqual(result["citations"], [])
        self.assertIn("Dati da chiarire:", result["answer"])
        self.assertIn("Il debitore ha contestato", result["answer"])

    def test_cited_legal_section_becomes_validated_claim_without_duplicate_rendering(self) -> None:
        engine = GroundedAnswerEngine(store=None, client=None, model="test")
        payload = {
            "status": "limited",
            "chat_answer": "",
            "intro": "Risposta operativa.",
            "sections": [
                {
                    "type": "legal_basis",
                    "title": "Base giuridica",
                    "items": [
                        {
                            "text": "Le fatture elettroniche trasmesse via Sistema di interscambio rientrano tra le prove scritte idonee.",
                            "citations": ["doc:art634"],
                        }
                    ],
                }
            ],
            "claims": [],
            "missing_information": [],
            "follow_up_questions": [],
        }
        context = {
            "coverage": {},
            "documents": [
                {
                    "id": "doc:art634",
                    "title": "Codice procedura civile - Art. 634",
                    "source_ref": "https://example.test/art634",
                }
            ],
            "related_documents": [],
        }

        validated = engine._validate_payload(payload, {"doc:art634"}, context)
        result = engine._render(validated, context)

        self.assertEqual(validated["claims"][0]["citations"], ["doc:art634"])
        self.assertTrue(validated["claims"][0]["_from_section"])
        self.assertIn("Base giuridica:", result["answer"])
        self.assertIn("[1]", result["answer"])
        self.assertEqual(result["answer"].count("fatture elettroniche"), 1)


if __name__ == "__main__":
    unittest.main()
