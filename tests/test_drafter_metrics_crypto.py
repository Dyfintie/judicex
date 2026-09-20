from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from judicex_memory_os.drafter import DraftingError, draft_atto, list_templates
from judicex_memory_os.metrics import collect_metrics
from judicex_memory_os.models import Document
from judicex_memory_os.preflight import run_preflight
from judicex_memory_os.store import LegalMemoryStore


def _seed_decreto_corpus(store: LegalMemoryStore) -> None:
    for doc_id, title in [
        ("cpc_art633", "Codice procedura civile - Art. 633"),
        ("cpc_art634", "Codice procedura civile - Art. 634"),
        ("cpc_art641", "Codice procedura civile - Art. 641"),
        ("cpc_art642", "Codice procedura civile - Art. 642"),
    ]:
        store.upsert_document(
            Document(
                id=doc_id,
                title=title,
                kind="norma",
                area="civile",
                content=f"contenuto {title}",
                source_ref=f"urn:nir:test:{doc_id}",
            )
        )
    store.commit()


class DrafterTests(unittest.TestCase):
    def test_built_in_templates_include_three_atti(self) -> None:
        names = {t["name"] for t in list_templates()}
        self.assertIn("ricorso_decreto_ingiuntivo", names)
        self.assertIn("intimazione_sfratto_morosita", names)
        self.assertIn("opposizione_decreto_ingiuntivo", names)

    def test_drafter_renders_decreto_when_articles_vigent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = LegalMemoryStore(Path(td) / "m.db")
            self.addCleanup(store.close)
            _seed_decreto_corpus(store)

            result = draft_atto(
                store,
                template_name="ricorso_decreto_ingiuntivo",
                as_of_date="2026-04-29",
                params={
                    "creditore": "Alfa S.r.l.",
                    "debitore": "Beta S.p.A.",
                    "importo": "8.500",
                    "causale": "consulenza",
                    "tribunale": "Milano",
                },
            )
            self.assertEqual(result["status"], "drafted")
            self.assertIn("Alfa S.r.l.", result["rendered"])
            self.assertIn("art. 633", result["rendered"])
            self.assertIn("art. 642", result["rendered"])
            cited_articles = {c["article"] for c in result["citations"]}
            self.assertSetEqual(cited_articles, {"633", "634", "641", "642"})

    def test_drafter_blocks_when_required_article_missing_from_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = LegalMemoryStore(Path(td) / "m.db")
            self.addCleanup(store.close)
            # Seed only 633 + 634; 641 / 642 missing
            for doc_id, title in [
                ("cpc_art633", "cpc 633"),
                ("cpc_art634", "cpc 634"),
            ]:
                store.upsert_document(Document(
                    id=doc_id, title=title, kind="norma", area="civile",
                    content="x", source_ref=f"urn:{doc_id}"))
            store.commit()

            result = draft_atto(
                store,
                template_name="ricorso_decreto_ingiuntivo",
                as_of_date="2026-04-29",
                params={
                    "creditore": "Alfa", "debitore": "Beta", "importo": "100",
                    "causale": "y", "tribunale": "Roma",
                },
            )
            self.assertEqual(result["status"], "blocked")
            self.assertIn("641", result["blocked_articles"])
            self.assertIn("642", result["blocked_articles"])

    def test_drafter_raises_on_missing_required_param(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = LegalMemoryStore(Path(td) / "m.db")
            self.addCleanup(store.close)
            _seed_decreto_corpus(store)
            with self.assertRaises(DraftingError):
                draft_atto(
                    store,
                    template_name="ricorso_decreto_ingiuntivo",
                    as_of_date="2026-04-29",
                    params={"creditore": "Alfa"},
                )


class PreflightTests(unittest.TestCase):
    def test_preflight_marks_missing_articles_and_keeps_known_ones(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = LegalMemoryStore(Path(td) / "m.db")
            self.addCleanup(store.close)
            store.upsert_document(Document(
                id="cc_art2946", title="cc 2946", kind="norma", area="civile",
                content="dieci anni", source_ref="urn:art2946"))
            store.commit()

            context = {
                "as_of_date": "2026-04-29",
                "decomposition": {
                    "scenarios": [
                        {
                            "id": "s1",
                            "domain": "recupero_crediti",
                            "as_of_date": "2026-04-29",
                            "matter_facts": [],
                            "issues": [
                                {
                                    "id": "issue_1",
                                    "title": "Prescrizione",
                                    "required_articles": ["2946", "2948"],
                                }
                            ],
                        }
                    ]
                },
                "coverage": {
                    "issue_coverage": [
                        {
                            "id": "issue_1",
                            "required_articles": ["2946", "2948"],
                            "documents": [
                                {"id": "cc_art2946"},
                            ],
                        }
                    ]
                },
                "conflicts": {"graph_populated": True},
            }
            preflight = run_preflight(store, context=context)
            self.assertEqual(len(preflight["scenarios"]), 1)
            articles = {a["article"]: a for a in preflight["scenarios"][0]["articles"]}
            self.assertEqual(articles["2946"]["status"], "vigente")
            self.assertEqual(articles["2948"]["status"], "missing_in_corpus")
            self.assertTrue(any("2948" in w for w in preflight["scenarios"][0]["warnings"]))


class MetricsTests(unittest.TestCase):
    def test_metrics_aggregates_corpus_audit_graph_and_cache(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = LegalMemoryStore(Path(td) / "m.db")
            self.addCleanup(store.close)
            store.upsert_document(Document(
                id="cc_art2946", title="cc 2946", kind="norma", area="civile",
                content="dieci anni", source_ref="urn:1"))
            store.upsert_document(Document(
                id="cpc_art633", title="cpc 633", kind="norma", area="civile",
                content="x", source_ref="urn:2"))
            store.commit()

            store.cache_put("k1", "v1", model="m1", kind="decomposer", ttl_seconds=None)
            store.cache_put("k2", "v2", model="m1", kind="numeric_verifier", ttl_seconds=None)

            metrics = collect_metrics(store)
            self.assertEqual(metrics["corpus"]["documents_total"], 2)
            self.assertEqual(metrics["corpus"]["by_area"].get("civile"), 2)
            self.assertEqual(metrics["audit"]["total"], 0)
            self.assertEqual(metrics["cache"]["entries_total"], 2)
            self.assertIn("decomposer", metrics["cache"]["by_kind"])


class EncryptionTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            from cryptography.fernet import Fernet  # noqa: F401
        except ImportError:
            self.skipTest("cryptography package not installed")
        self._original_env = os.environ.get("JUDICEX_MATTER_KEY", "")

    def tearDown(self) -> None:
        if self._original_env:
            os.environ["JUDICEX_MATTER_KEY"] = self._original_env
        else:
            os.environ.pop("JUDICEX_MATTER_KEY", None)

    def test_at_rest_encryption_writes_ciphertext_and_decrypts_on_read(self) -> None:
        from cryptography.fernet import Fernet

        os.environ["JUDICEX_MATTER_KEY"] = Fernet.generate_key().decode("utf-8")
        with tempfile.TemporaryDirectory() as td:
            store = LegalMemoryStore(Path(td) / "m.db")
            self.addCleanup(store.close)
            matter = store.create_matter("M1")
            added = store.add_matter_document(
                matter["id"], title="Memo", kind="memo",
                content="Importo: 8.500 euro; Creditore: Alfa SRL",
            )
            raw = store.conn.execute(
                "SELECT content FROM matter_documents WHERE id = ?",
                (added["document"]["id"],),
            ).fetchone()[0]
            self.assertTrue(raw.startswith("JX1"))
            fetched = store.get_matter_document(added["document"]["id"])
            self.assertIn("Alfa SRL", fetched["content"])
            hits = store.search_matter_documents("Alfa SRL", matter_id=matter["id"])
            self.assertEqual(len(hits), 1)


if __name__ == "__main__":
    unittest.main()
