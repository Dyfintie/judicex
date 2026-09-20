from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from judicex_memory_os.audit_log import record_answer, verify_record
from judicex_memory_os.confidence import compute_confidence
from judicex_memory_os.conflict_detector import detect_conflicts
from judicex_memory_os.entity_extractor import (
    extract_norm_references,
    materialise_references,
)
from judicex_memory_os.llm_cache import CachedLLMClient
from judicex_memory_os.models import Document
from judicex_memory_os.store import LegalMemoryStore


class StubLLM:
    """LLM stub: dispatches based on system prompt prefix."""

    def __init__(self) -> None:
        self.refs_by_doc: dict[str, list[dict]] = {}
        self.calls = 0

    def chat(self, model: str, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        self.calls += 1
        sys_prompt = messages[0]["content"]
        if "estrattore di riferimenti normativi" in sys_prompt:
            briefing = json.loads(messages[1]["content"])
            doc_id = briefing.get("document_id", "")
            return json.dumps({"references": self.refs_by_doc.get(doc_id, [])})
        if "analizzatore di domande giuridiche" in sys_prompt:
            return json.dumps({"scenarios": [{"id": "s1", "summary": "x", "domain": "civile_generale",
                "matter_facts": [], "issues": [{"id": "i1", "title": "t", "question": "q",
                "retrieval_query": "q", "required_articles": [], "coverage_terms": []}]}]})
        if "classificatore numerico" in sys_prompt:
            return json.dumps({"legal_rule_numbers": []})
        return "{}"


class CitatorTests(unittest.TestCase):
    def _make_store(self) -> tuple[tempfile.TemporaryDirectory[str], LegalMemoryStore]:
        td = tempfile.TemporaryDirectory()
        store = LegalMemoryStore(Path(td.name) / "memory.db")
        return td, store

    def test_temporal_filter_excludes_doc_outside_effective_window(self) -> None:
        td, store = self._make_store()
        self.addCleanup(td.cleanup)
        self.addCleanup(store.close)
        store.upsert_document(Document(
            id="art_old", title="versione 2005", kind="norma", area="civile",
            content="canone si prescrive in sei anni",
            effective_from="2005-01-01", effective_to="2010-12-31",
        ))
        store.upsert_document(Document(
            id="art_new", title="versione 2011+", kind="norma", area="civile",
            content="canone si prescrive in cinque anni",
            effective_from="2011-01-01",
        ))
        store.commit()

        ctx_2008 = store.build_context("prescrizione canone", area="civile", as_of_date="2008-06-01")
        ids_2008 = {d["id"] for d in ctx_2008["documents"]}
        self.assertIn("art_old", ids_2008)
        self.assertNotIn("art_new", ids_2008)

        ctx_2026 = store.build_context("prescrizione canone", area="civile", as_of_date="2026-04-29")
        ids_2026 = {d["id"] for d in ctx_2026["documents"]}
        self.assertIn("art_new", ids_2026)
        self.assertNotIn("art_old", ids_2026)

    def test_extractor_skips_self_loops_when_multiple_versions_share_article_number(self) -> None:
        td, store = self._make_store()
        self.addCleanup(td.cleanup)
        self.addCleanup(store.close)
        store.upsert_document(Document(
            id="art_old", title="art previgente", kind="norma", area="civile",
            content="prima formulazione",
            effective_from="2005-01-01", effective_to="2010-12-31",
        ))
        store.upsert_document(Document(
            id="art_new", title="art vigente", kind="norma", area="civile",
            content="abroga la previgente formulazione",
            effective_from="2011-01-01",
        ))
        store.commit()

        llm = StubLLM()
        llm.refs_by_doc["art_new"] = [{
            "relation": "abroga",
            "target": {"code": "altro", "article": "previgente", "label": "art previgente"},
            "evidence_quote": "abroga la previgente",
            "summary": "abrogazione",
        }]
        for row in store.conn.execute("SELECT * FROM documents"):
            doc = store._document_row_to_dict(row, full=True)
            refs = extract_norm_references(llm, "fake", document=doc)
            materialise_references(store, document=doc, references=refs)

        # No self-loop for art_new
        self_loops = store.conn.execute(
            "SELECT COUNT(*) FROM edges WHERE source_id = target_id"
        ).fetchone()[0]
        self.assertEqual(self_loops, 0)

    def test_shepardize_marks_doc_abrogated_when_inbound_edge_from_vigent_norm(self) -> None:
        td, store = self._make_store()
        self.addCleanup(td.cleanup)
        self.addCleanup(store.close)
        store.upsert_document(Document(
            id="cc_art1234_old", title="cc 1234 old", kind="norma", area="civile",
            content="vecchio testo", effective_from="2000-01-01", effective_to="2010-12-31",
        ))
        store.upsert_document(Document(
            id="cc_art1234", title="cc 1234 nuovo", kind="norma", area="civile",
            content="abroga il testo previgente", effective_from="2011-01-01",
        ))
        store.commit()

        llm = StubLLM()
        llm.refs_by_doc["cc_art1234"] = [{
            "relation": "abroga",
            "target": {"code": "cc", "article": "1234", "number": "", "year": "2010", "label": "cc 1234 vecchio"},
            "evidence_quote": "abroga il testo previgente",
            "summary": "abrogazione testo previgente",
        }]
        for row in store.conn.execute("SELECT * FROM documents"):
            doc = store._document_row_to_dict(row, full=True)
            refs = extract_norm_references(llm, "fake", document=doc)
            materialise_references(store, document=doc, references=refs)

        report = store.shepardize("cc_art1234_old", "2026-04-29")
        # The OLD doc is out of its effective window AND inbound abroga from vigent successor
        self.assertEqual(report["status"], "abrogato")
        self.assertTrue(report["active_abrogations"])
        self.assertEqual(report["active_abrogations"][0]["source_document_id"], "cc_art1234")

    def test_conflict_detector_blocks_abrogated_evidence_at_as_of_date(self) -> None:
        td, store = self._make_store()
        self.addCleanup(td.cleanup)
        self.addCleanup(store.close)
        store.upsert_document(Document(
            id="cc_art1234_old", title="cc 1234 old", kind="norma", area="civile",
            content="vecchio", effective_from="2000-01-01", effective_to="2010-12-31",
        ))
        store.upsert_document(Document(
            id="cc_art1234", title="cc 1234 nuovo", kind="norma", area="civile",
            content="abroga il testo previgente", effective_from="2011-01-01",
        ))
        store.commit()
        llm = StubLLM()
        llm.refs_by_doc["cc_art1234"] = [{
            "relation": "abroga",
            "target": {"code": "cc", "article": "1234", "label": "cc 1234"},
            "evidence_quote": "abroga", "summary": "abrogazione",
        }]
        for row in store.conn.execute("SELECT * FROM documents"):
            doc = store._document_row_to_dict(row, full=True)
            materialise_references(store, document=doc, references=extract_norm_references(llm, "fake", document=doc))

        report = detect_conflicts(
            store,
            documents=[
                {"id": "cc_art1234_old"},
                {"id": "cc_art1234"},
            ],
            as_of_date="2026-04-29",
        )
        self.assertIn("cc_art1234_old", report["blocked_document_ids"])
        self.assertNotIn("cc_art1234", report["blocked_document_ids"])
        self.assertTrue(report["graph_populated"])

    def test_audit_record_signature_verifies_and_detects_tamper(self) -> None:
        td, store = self._make_store()
        self.addCleanup(td.cleanup)
        self.addCleanup(store.close)
        rendered = {"status": "grounded", "answer": "test", "claims": []}
        public = record_answer(
            store,
            question="domanda?",
            context={"as_of_date": "2026-04-29", "documents": [{"id": "doc:x"}], "coverage": {}},
            payload=rendered,
            model="fake",
            area="civile",
            matter_id=None,
        )
        check_ok = verify_record(store, public["id"])
        self.assertTrue(check_ok["valid"])

        # Tamper
        store.conn.execute(
            "UPDATE answer_audit SET payload_json = ? WHERE id = ?",
            (json.dumps({"status": "grounded", "answer": "ALTERED"}), public["id"]),
        )
        store.conn.commit()
        check_tampered = verify_record(store, public["id"])
        self.assertFalse(check_tampered["valid"])

    def test_confidence_score_drops_when_blocked_citations_present(self) -> None:
        ctx_clean = {
            "coverage": {
                "issues_total": 1,
                "issues_covered": 1,
                "issues_partial": 0,
                "documents_total": 2,
                "candidate_documents": 2,
                "excluded_by_date": 0,
                "issue_coverage": [{"required_articles": ["X"], "matched_articles": ["X"]}],
            },
            "conflicts": {"blocked_document_ids": [], "warning_document_ids": []},
        }
        payload_clean = {
            "status": "grounded",
            "_answer_contract": {"claims_total": 1, "claims_retained": 1, "status": "passed"},
            "_semantic_verifier": {"status": "passed"},
        }
        clean = compute_confidence(payload_clean, ctx_clean)
        self.assertGreater(clean["score"], 0.9)

        ctx_blocked = {**ctx_clean, "conflicts": {"blocked_document_ids": ["doc:1", "doc:2"], "warning_document_ids": []}}
        blocked = compute_confidence(payload_clean, ctx_blocked)
        self.assertLess(blocked["score"], clean["score"])
        self.assertLess(blocked["components"]["conflict"], 1.0)

    def test_llm_cache_routes_decomposer_calls_and_passes_others_through(self) -> None:
        td, store = self._make_store()
        self.addCleanup(td.cleanup)
        self.addCleanup(store.close)
        store.commit()

        class Inner:
            def __init__(self) -> None:
                self.n = 0
            def chat(self, model, messages, temperature=0.0):
                self.n += 1
                return json.dumps({"scenarios": [{"id": "s1", "summary": "", "domain": "altro",
                    "matter_facts": [], "issues": [{"id": "i1", "title": "t", "question": "q",
                    "retrieval_query": "q", "required_articles": [], "coverage_terms": []}]}]})

        inner = Inner()
        cached = CachedLLMClient(inner, store)
        msg = [
            {"role": "system", "content": "Sei l'analizzatore di domande giuridiche di Judicex."},
            {"role": "user", "content": "domanda identica"},
        ]
        cached.chat(model="m", messages=msg)
        cached.chat(model="m", messages=msg)
        self.assertEqual(inner.n, 1)
        self.assertEqual(cached.hits, 1)
        self.assertEqual(cached.misses, 1)


if __name__ == "__main__":
    unittest.main()
