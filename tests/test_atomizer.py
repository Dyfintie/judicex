from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from judicex_memory_os.atomizer import compile_document_atoms
from judicex_memory_os.models import Document
from judicex_memory_os.store import LegalMemoryStore


class LegalAtomCompilerTests(unittest.TestCase):
    def test_extracts_deadline_atoms_from_normative_text(self) -> None:
        document = Document(
            id="doc:art644",
            title="Codice procedura civile - Art. 644 - Mancata notificazione del decreto",
            kind="norma",
            area="civile",
            content=(
                "Il decreto d'ingiunzione diventa inefficace qualora la notificazione non sia "
                "eseguita nel termine di sessanta giorni dalla pronuncia, se deve avvenire "
                "nel territorio nazionale, e di novanta giorni negli altri casi."
            ),
        )

        atoms = compile_document_atoms(document)
        deadlines = [atom for atom in atoms if atom.atom_type == "deadline"]

        self.assertTrue(any(atom.action == "notificazione" and atom.value == "60" for atom in deadlines))
        self.assertTrue(any(atom.action == "notificazione" and atom.value == "90" for atom in deadlines))
        self.assertTrue(any("dalla pronuncia" in atom.temporal_anchor for atom in deadlines))

    def test_store_indexes_and_searches_atoms(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            with LegalMemoryStore(Path(tempdir) / "memory.db") as store:
                store.upsert_document(
                    Document(
                        id="doc:art641",
                        title="Codice procedura civile - Art. 641 - Accoglimento della domanda",
                        kind="norma",
                        area="civile",
                        content=(
                            "Il giudice ingiunge all'altra parte di pagare nel termine di quaranta giorni, "
                            "con l'avvertimento che nello stesso termine puo essere fatta opposizione."
                        ),
                    )
                )
                store.commit()

                atoms = store.search_atoms("termine opposizione quaranta giorni", area="civile")

        self.assertTrue(atoms)
        self.assertEqual(atoms[0]["document_id"], "doc:art641")
        self.assertTrue(any(atom["value"] == "40" for atom in atoms))


if __name__ == "__main__":
    unittest.main()
