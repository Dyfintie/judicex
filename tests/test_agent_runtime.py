from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from judicex_memory_os.agent_runtime import JudicexAgentRuntime
from judicex_memory_os.store import LegalMemoryStore


class RaisingClient:
    def chat(self, *, model: str, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        raise RuntimeError("LLM non disponibile nel test")


class JudicexAgentRuntimeTests(unittest.TestCase):
    def test_operational_debt_recovery_request_uses_agent_tools_not_fixed_pipeline(self) -> None:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        store = LegalMemoryStore(Path(tempdir.name) / "memory.db")
        self.addCleanup(store.close)
        emitted: list[dict] = []
        runtime = JudicexAgentRuntime(
            store=store,
            client=RaisingClient(),
            model="fake",
            area="civile",
            on_step=emitted.append,
        )

        result = runtime.answer(
            "Un cliente deve recuperare 8.500 euro per tre fatture non pagate. "
            "Voglio domande sui dati mancanti, checklist documentale, rischi, "
            "strategia operativa e bozza di diffida."
        )

        self.assertEqual(result["status"], "operational")
        self.assertIn("Dati da chiarire:", result["answer"])
        self.assertIn("Checklist documentale:", result["answer"])
        self.assertIn("Strategia operativa:", result["answer"])
        self.assertIn("Bozza diffida:", result["answer"])
        trace_titles = [step["title"] for step in result["agent_trace"]]
        self.assertEqual(trace_titles[0], "Pianifico lavoro")
        self.assertIn("Tool: memoria agente", trace_titles)
        self.assertIn("Tool: ricerca legale", trace_titles)
        self.assertIn("Tool: composizione risposta", trace_titles)
        self.assertEqual([step["id"] for step in emitted], [step["id"] for step in result["agent_trace"]])

    def test_agent_memory_is_separate_from_legal_sources_and_available_to_runtime(self) -> None:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        store = LegalMemoryStore(Path(tempdir.name) / "memory.db")
        self.addCleanup(store.close)
        stored = store.add_agent_memory(
            kind="preference",
            title="Stile recupero crediti",
            content="Per recupero crediti B2B usa sempre tono pratico e poco tecnico.",
            tags=["recupero_crediti", "stile"],
            importance=0.9,
        )

        self.assertEqual(store.health()["documents"], 0)
        self.assertEqual(store.health()["agent_memories"], 1)
        self.assertEqual(store.search_agent_memories("recupero crediti")[0]["id"], stored["id"])

        runtime = JudicexAgentRuntime(
            store=store,
            client=RaisingClient(),
            model="fake",
            area="civile",
        )
        result = runtime.answer("Prepara strategia operativa per recupero crediti B2B.")

        self.assertEqual(result["status"], "operational")
        self.assertIn("Memoria agente applicata:", result["answer"])
        self.assertEqual(result["agent_memory"][0]["id"], stored["id"])


if __name__ == "__main__":
    unittest.main()
