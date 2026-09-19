"""Evaluation suites for Judicex.

The legacy deterministic suite lives at the top of this directory as a JSON
file (see `core_civile_recupero_crediti.json`) and is still consumed by
`judicex_memory_os.evaluation`. The newer LLM-driven gold suites live under
`evals/gold/` and are scored by `gold_runner` for end-to-end answer quality.
"""

from .gold_runner import list_gold_suites, load_gold_suite, run_gold_suite

__all__ = ["list_gold_suites", "load_gold_suite", "run_gold_suite"]
