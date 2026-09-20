from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from judicex_memory_os.models import MatterDocument
from judicex_memory_os.matter_memory import extract_matter_facts
from judicex_memory_os.store import LegalMemoryStore


PRIVATE_DOC = (
    "Creditore: Alfa S.r.l.; Debitore: Beta S.p.A. "
    "La fattura n. 12 del 15/01/2026 e pari a euro 1.234,56. "
    "Il debitore deve pagare entro 30 giorni dalla notifica."
)


class MatterMemoryTests(unittest.TestCase):
    def make_store(self) -> tuple[tempfile.TemporaryDirectory[str], LegalMemoryStore]:
        tempdir = tempfile.TemporaryDirectory()
        store = LegalMemoryStore(Path(tempdir.name) / "memory.db")
        return tempdir, store

    def test_extract_matter_facts_is_deterministic(self) -> None:
        document = MatterDocument(
            id="matterdoc:test",
            matter_id="matter:test",
            title="Fascicolo recupero credito",
            kind="memo",
            content=PRIVATE_DOC,
        )

        facts = extract_matter_facts(document)
        by_type = {fact.fact_type for fact in facts}

        self.assertIn("party", by_type)
        self.assertIn("date", by_type)
        self.assertIn("amount", by_type)
        self.assertIn("deadline", by_type)
        self.assertTrue(any(fact.value == "1234.56" and fact.unit == "EUR" for fact in facts))
        self.assertTrue(any(fact.value == "30" and fact.unit == "giorni" for fact in facts))
        self.assertTrue(any(fact.date_value == "2026-01-15" for fact in facts))

    def test_store_adds_private_documents_and_searchable_facts(self) -> None:
        tempdir, store = self.make_store()
        self.addCleanup(tempdir.cleanup)
        self.addCleanup(store.close)

        matter = store.create_matter(
            "Recupero credito Beta",
            client_name="Alfa S.r.l.",
            area="civile",
        )
        result = store.add_matter_document(
            matter["id"],
            title="Promemoria istruttorio",
            kind="memo",
            content=PRIVATE_DOC,
        )

        self.assertGreaterEqual(result["facts_count"], 5)
        self.assertEqual(store.health()["matters"], 1)
        self.assertEqual(store.health()["matter_documents"], 1)
        self.assertGreaterEqual(store.health()["matter_facts"], 4)

        docs = store.search_matter_documents("fattura", matter_id=matter["id"])
        facts = store.search_matter_facts("pagare giorni", matter_id=matter["id"], fact_type="deadline")
        context = store.build_matter_context(matter["id"], query="fattura pagamento")

        self.assertEqual(docs[0]["title"], "Promemoria istruttorio")
        self.assertEqual(facts[0]["value"], "30")
        self.assertEqual(context["coverage"]["amounts"], 1)
        self.assertEqual(context["coverage"]["deadlines"], 1)
        self.assertTrue(any(item["date_value"] == "2026-01-15" for item in context["timeline"]))


if __name__ == "__main__":
    unittest.main()
