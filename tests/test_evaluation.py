from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from judicex_memory_os.evaluation import run_eval_suite
from judicex_memory_os.models import Document
from judicex_memory_os.store import LegalMemoryStore


class EvaluationSuiteTests(unittest.TestCase):
    def test_eval_suite_passes_required_documents_and_atoms(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            suite_path = Path(tempdir) / "suite.json"
            suite_path.write_text(
                json.dumps(
                    {
                        "id": "test_suite",
                        "version": "1",
                        "cases": [
                            {
                                "id": "notifica_termine",
                                "area": "civile",
                                "question": "Entro quanti giorni deve essere eseguita la notificazione?",
                                "requires": {
                                    "documents": ["doc:art644"],
                                    "source_terms": [
                                        {
                                            "document_id": "doc:art644",
                                            "contains": ["sessanta giorni", "dalla pronuncia"],
                                        }
                                    ],
                                    "atoms": [
                                        {
                                            "document_id": "doc:art644",
                                            "atom_type": "deadline",
                                            "action": "notificazione",
                                            "value": "60",
                                            "unit": "giorni",
                                        }
                                    ],
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with LegalMemoryStore(Path(tempdir) / "memory.db") as store:
                store.upsert_document(
                    Document(
                        id="doc:art644",
                        title="Codice procedura civile - Art. 644 - Mancata notificazione del decreto",
                        kind="norma",
                        area="civile",
                        content=(
                            "Il decreto d'ingiunzione diventa inefficace qualora la notificazione non sia "
                            "eseguita nel termine di sessanta giorni dalla pronuncia."
                        ),
                    )
                )
                store.commit()

                result = run_eval_suite(store, suite=suite_path)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["checks_total"], 3)
        self.assertEqual(result["checks_passed"], 3)

    def test_eval_suite_fails_when_required_document_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            suite_path = Path(tempdir) / "suite.json"
            suite_path.write_text(
                json.dumps(
                    {
                        "id": "test_suite",
                        "cases": [
                            {
                                "id": "missing_source",
                                "area": "civile",
                                "question": "Entro quanti giorni deve essere eseguita la notificazione?",
                                "requires": {"documents": ["doc:missing"]},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with LegalMemoryStore(Path(tempdir) / "memory.db") as store:
                store.upsert_document(
                    Document(
                        id="doc:art644",
                        title="Codice procedura civile - Art. 644 - Mancata notificazione del decreto",
                        kind="norma",
                        area="civile",
                        content="La notificazione deve essere eseguita nel termine di sessanta giorni.",
                    )
                )
                store.commit()

                result = run_eval_suite(store, suite=suite_path)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failed"], 1)
        self.assertIn("missing required document: doc:missing", result["results"][0]["failures"])


if __name__ == "__main__":
    unittest.main()
