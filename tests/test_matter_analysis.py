from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from judicex_memory_os.store import LegalMemoryStore


class MatterAnalysisTests(unittest.TestCase):
    def make_store(self) -> tuple[tempfile.TemporaryDirectory[str], LegalMemoryStore]:
        tempdir = tempfile.TemporaryDirectory()
        store = LegalMemoryStore(Path(tempdir.name) / "memory.db")
        return tempdir, store

    def test_debt_recovery_analysis_finds_present_and_missing_proof(self) -> None:
        tempdir, store = self.make_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        matter = store.create_matter("Recupero credito Beta", client_name="Alfa S.r.l.", area="civile")
        store.add_matter_document(
            matter["id"],
            title="Promemoria recupero credito",
            kind="memo",
            content=(
                "Creditore: Alfa S.r.l.; Debitore: Beta S.p.A. "
                "La fattura n. 12 del 15/01/2026 e pari a euro 1.234,56. "
                "Il debitore deve pagare entro 30 giorni dalla notifica."
            ),
        )

        result = store.analyze_matter(matter["id"], "ricorso per decreto ingiuntivo per recupero credito")
        by_id = {item["id"]: item for item in result["requirements"]}

        self.assertEqual(result["profile"]["id"], "civil_debt_recovery_injunction")
        self.assertIn(result["status"], {"ready", "partial"})
        self.assertGreaterEqual(result["readiness_score"], 70)
        self.assertEqual(by_id["creditor"]["status"], "present")
        self.assertEqual(by_id["debtor"]["status"], "present")
        self.assertEqual(by_id["amount"]["status"], "present")
        self.assertEqual(by_id["written_evidence"]["status"], "partial")
        self.assertTrue(any(fact["fact_type"] == "amount" for fact in result["supporting_facts"]))
        self.assertTrue(result["next_actions"])

    def test_sparse_matter_analysis_identifies_required_gaps(self) -> None:
        tempdir, store = self.make_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        matter = store.create_matter("Fascicolo vuoto", client_name="Alfa S.r.l.", area="civile")
        store.add_matter_document(
            matter["id"],
            title="Nota generica",
            kind="memo",
            content="Il cliente chiede una valutazione preliminare.",
        )

        result = store.analyze_matter(matter["id"], "ricorso per decreto ingiuntivo per recupero credito")
        missing_ids = {item["id"] for item in result["missing_requirements"]}

        self.assertEqual(result["status"], "insufficient")
        self.assertIn("creditor", missing_ids)
        self.assertIn("debtor", missing_ids)
        self.assertIn("amount", missing_ids)
        self.assertGreaterEqual(len(result["next_actions"]), 3)

    def test_opposition_profile_requires_notification_date_and_grounds(self) -> None:
        tempdir, store = self.make_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        matter = store.create_matter("Opposizione Beta", client_name="Beta S.p.A.", area="civile")
        store.add_matter_document(
            matter["id"],
            title="Memo notifica decreto ingiuntivo",
            kind="memo",
            content="Debitore: Beta S.p.A. Il decreto ingiuntivo e stato notificato il 10/02/2026.",
        )

        result = store.analyze_matter(matter["id"], "opposizione a decreto ingiuntivo")
        by_id = {item["id"]: item for item in result["requirements"]}

        self.assertEqual(result["profile"]["id"], "opposition_to_injunction")
        self.assertEqual(by_id["notification_date"]["status"], "present")
        self.assertEqual(by_id["opposition_grounds"]["status"], "missing")

    def test_analysis_can_use_external_workflow_pack(self) -> None:
        tempdir, store = self.make_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        pack_path = Path(tempdir.name) / "custom_pack.json"
        pack_path.write_text(
            json.dumps(
                {
                    "id": "custom_locazioni",
                    "version": "1",
                    "label": "Custom locazioni",
                    "default_profile_id": "locazione",
                    "profiles": [
                        {
                            "id": "locazione",
                            "label": "Locazione custom",
                            "match_terms": ["locazione", "canone"],
                            "requirements": [
                                {
                                    "id": "contract",
                                    "label": "Contratto di locazione",
                                    "description": "Contratto o scrittura che regola il rapporto.",
                                    "required": True,
                                    "document_terms": ["contratto di locazione"],
                                    "suggestion": "Caricare il contratto di locazione.",
                                },
                                {
                                    "id": "rent_amount",
                                    "label": "Canone",
                                    "description": "Importo del canone.",
                                    "required": True,
                                    "fact_types": ["amount"],
                                    "document_terms": ["canone"],
                                    "suggestion": "Caricare importo del canone o conteggio morosita.",
                                },
                            ],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        matter = store.create_matter("Locazione Gamma", client_name="Gamma", area="civile")
        store.add_matter_document(
            matter["id"],
            title="Contratto di locazione",
            kind="contratto",
            content="Contratto di locazione. Il canone mensile e pari a euro 900,00.",
        )

        result = store.analyze_matter(
            matter["id"],
            "azione per canoni di locazione",
            workflow_pack=pack_path,
        )

        self.assertEqual(result["workflow_pack"]["id"], "custom_locazioni")
        self.assertEqual(result["profile"]["id"], "locazione")
        self.assertEqual(result["status"], "partial")
        self.assertEqual({item["id"] for item in result["present_requirements"]}, {"rent_amount"})
        self.assertEqual({item["id"] for item in result["partial_requirements"]}, {"contract"})


if __name__ == "__main__":
    unittest.main()
