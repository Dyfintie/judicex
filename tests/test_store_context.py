from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from judicex_memory_os.models import Document
from judicex_memory_os.store import LegalMemoryStore


class BuildContextRetrievalTests(unittest.TestCase):
    def make_store(self) -> tuple[tempfile.TemporaryDirectory[str], LegalMemoryStore]:
        tempdir = tempfile.TemporaryDirectory()
        store = LegalMemoryStore(Path(tempdir.name) / "memory.db")
        return tempdir, store

    def test_multistep_question_promotes_each_relevant_source(self) -> None:
        tempdir, store = self.make_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

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
            )
        )
        store.upsert_document(
            Document(
                id="doc:art650",
                title="Codice procedura civile - Art. 650 - Opposizione tardiva",
                kind="norma",
                area="civile",
                content="L'intimato puo fare opposizione tardiva in casi specifici.",
            )
        )
        store.commit()

        context = store.build_context(
            "Entro quanti giorni il decreto ingiuntivo va notificato e quanti giorni ha il debitore per proporre opposizione?",
            area="civile",
            doc_k=4,
        )
        ids = [doc["id"] for doc in context["documents"]]

        self.assertIn("doc:art644", ids)
        self.assertIn("doc:art641", ids)
        self.assertLess(ids.index("doc:art644"), ids.index("doc:art650"))

    def test_generic_multipart_query_is_not_tied_to_decreto_ingiuntivo(self) -> None:
        tempdir, store = self.make_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        store.upsert_document(
            Document(
                id="doc:registro",
                title="Regolamento - Art. 10 - Iscrizione nel registro",
                kind="norma",
                area="amministrativo",
                content="L'iscrizione nel registro deve essere eseguita entro venti giorni dalla comunicazione.",
            )
        )
        store.upsert_document(
            Document(
                id="doc:reclamo",
                title="Regolamento - Art. 11 - Reclamo",
                kind="norma",
                area="amministrativo",
                content="Il reclamo puo essere proposto nel termine di trenta giorni dalla notificazione.",
            )
        )
        store.upsert_document(
            Document(
                id="doc:sanzione",
                title="Regolamento - Art. 12 - Sanzione accessoria",
                kind="norma",
                area="amministrativo",
                content="La sanzione accessoria si applica nei casi previsti dalla legge.",
            )
        )
        store.commit()

        context = store.build_context(
            "Entro quanti giorni va eseguita l'iscrizione e quanti giorni ci sono per proporre reclamo?",
            area="amministrativo",
            doc_k=4,
        )
        ids = [doc["id"] for doc in context["documents"]]

        self.assertIn("doc:registro", ids)
        self.assertIn("doc:reclamo", ids)


if __name__ == "__main__":
    unittest.main()
