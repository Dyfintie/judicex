from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from judicex_memory_os.agent_runtime import JudicexAgentRuntime
from judicex_memory_os.store import LegalMemoryStore


class NoLLMClient:
    def chat(self, *, model: str, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        raise RuntimeError("no llm in public benchmark")


def run(db_path: Path, cases_path: Path) -> dict:
    suite = json.loads(cases_path.read_text(encoding="utf-8"))
    results = []
    with LegalMemoryStore(db_path) as store:
        runtime = JudicexAgentRuntime(store=store, client=NoLLMClient(), model="benchmark", area="civile")
        for case in suite.get("cases", []):
            result = runtime.answer(str(case["question"]))
            answer = str(result.get("answer") or "")
            missing = [term for term in case.get("expected_terms", []) if term.lower() not in answer.lower()]
            results.append(
                {
                    "id": case["id"],
                    "status": "passed" if not missing else "failed",
                    "answer_status": result.get("status"),
                    "missing_terms": missing,
                }
            )
    return {
        "suite": suite.get("name", cases_path.stem),
        "status": "passed" if all(item["status"] == "passed" for item in results) else "failed",
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Judicex public demo benchmark.")
    parser.add_argument("--db", required=True)
    parser.add_argument("--cases", default="benchmarks/public_demo_cases.json")
    args = parser.parse_args()
    result = run(Path(args.db), Path(args.cases))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
