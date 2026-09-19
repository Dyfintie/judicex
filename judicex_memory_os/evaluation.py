from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from .store import LegalMemoryStore


DEFAULT_SUITE = "core_civile_recupero_crediti"


@dataclass(slots=True)
class EvalResult:
    suite_id: str
    case_id: str
    passed: bool
    checks_total: int
    checks_passed: int
    failures: list[str]
    selected_documents: list[str]
    selected_atoms: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_id": self.suite_id,
            "case_id": self.case_id,
            "passed": self.passed,
            "checks_total": self.checks_total,
            "checks_passed": self.checks_passed,
            "failures": self.failures,
            "selected_documents": self.selected_documents,
            "selected_atoms": self.selected_atoms,
        }


def list_builtin_suites() -> list[dict[str, str]]:
    suites: list[dict[str, str]] = []
    eval_root = resources.files("judicex_memory_os").joinpath("evals")
    for item in eval_root.iterdir():
        if item.name.endswith(".json"):
            payload = json.loads(item.read_text(encoding="utf-8"))
            suites.append(
                {
                    "id": str(payload.get("id", item.name.removesuffix(".json"))),
                    "version": str(payload.get("version", "")),
                    "description": str(payload.get("description", "")),
                }
            )
    return sorted(suites, key=lambda item: item["id"])


def load_eval_suite(suite: str | Path) -> dict[str, Any]:
    suite_text = str(suite)
    if suite_text.endswith(".json") or Path(suite_text).exists():
        return json.loads(Path(suite_text).read_text(encoding="utf-8"))

    suite_name = suite_text.removeprefix("builtin:")
    if suite_name.endswith(".json"):
        filename = suite_name
    else:
        filename = f"{suite_name}.json"
    resource = resources.files("judicex_memory_os").joinpath("evals", filename)
    if not resource.is_file():
        available = ", ".join(item["id"] for item in list_builtin_suites())
        raise ValueError(f"unknown eval suite: {suite_text}. Available suites: {available}")
    return json.loads(resource.read_text(encoding="utf-8"))


def run_eval_suite(
    store: LegalMemoryStore,
    *,
    suite: str | Path = DEFAULT_SUITE,
    rebuild_atoms: bool = False,
) -> dict[str, Any]:
    payload = load_eval_suite(suite)
    suite_id = str(payload.get("id") or suite)
    cases = payload.get("cases") or []
    if not isinstance(cases, list):
        raise ValueError("eval suite field 'cases' must be a list")

    if rebuild_atoms:
        areas = sorted({str(case.get("area", "")).strip() for case in cases if str(case.get("area", "")).strip()})
        if areas:
            for area in areas:
                store.rebuild_legal_atoms(area=area)
        else:
            store.rebuild_legal_atoms()

    results = [_run_case(store, suite_id=suite_id, raw_case=case) for case in cases]
    passed = sum(1 for result in results if result.passed)
    checks_total = sum(result.checks_total for result in results)
    checks_passed = sum(result.checks_passed for result in results)
    return {
        "suite": {
            "id": suite_id,
            "version": payload.get("version", ""),
            "description": payload.get("description", ""),
            "cases": len(results),
        },
        "passed": passed,
        "failed": len(results) - passed,
        "checks_total": checks_total,
        "checks_passed": checks_passed,
        "status": "passed" if passed == len(results) else "failed",
        "results": [result.to_dict() for result in results],
    }


def _run_case(store: LegalMemoryStore, *, suite_id: str, raw_case: dict[str, Any]) -> EvalResult:
    case_id = str(raw_case.get("id", "")).strip() or "unnamed_case"
    question = str(raw_case["question"])
    area = raw_case.get("area")
    context = store.build_context(
        question,
        area=str(area) if area else None,
        doc_k=int(raw_case.get("doc_k", 6)),
        entity_k=int(raw_case.get("entity_k", 8)),
        neighbor_k=int(raw_case.get("neighbor_k", 6)),
    )
    selected_documents = [doc["id"] for doc in context.get("documents", []) + context.get("related_documents", [])]
    selected_atoms = [atom["id"] for atom in context.get("legal_atoms", [])]

    checks_total = 0
    checks_passed = 0
    failures: list[str] = []
    requirements = raw_case.get("requires") or {}

    for doc_id in requirements.get("documents", []):
        checks_total += 1
        if doc_id in selected_documents:
            checks_passed += 1
        else:
            failures.append(f"missing required document: {doc_id}")

    docs_by_id = {doc["id"]: doc for doc in context.get("documents", []) + context.get("related_documents", [])}
    for term_req in requirements.get("source_terms", []):
        checks_total += 1
        doc_id = str(term_req.get("document_id", ""))
        terms = [str(term).lower() for term in term_req.get("contains", [])]
        content = str((docs_by_id.get(doc_id) or {}).get("content", "")).lower()
        missing_terms = [term for term in terms if term not in content]
        if not missing_terms:
            checks_passed += 1
        else:
            failures.append(f"source terms missing in {doc_id}: {missing_terms}")

    atoms = context.get("legal_atoms", [])
    for atom_req in requirements.get("atoms", []):
        checks_total += 1
        if _atom_requirement_matches(atoms, atom_req):
            checks_passed += 1
        else:
            failures.append(f"missing required atom: {json.dumps(atom_req, ensure_ascii=False, sort_keys=True)}")

    return EvalResult(
        suite_id=suite_id,
        case_id=case_id,
        passed=not failures,
        checks_total=checks_total,
        checks_passed=checks_passed,
        failures=failures,
        selected_documents=selected_documents,
        selected_atoms=selected_atoms,
    )


def _atom_requirement_matches(atoms: list[dict[str, Any]], requirement: dict[str, Any]) -> bool:
    for atom in atoms:
        matched = True
        for key, expected in requirement.items():
            if key == "source_quote_contains":
                source_quote = str(atom.get("source_quote", "")).lower()
                expected_terms = expected if isinstance(expected, list) else [expected]
                if any(str(term).lower() not in source_quote for term in expected_terms):
                    matched = False
                    break
                continue
            actual = atom.get(key)
            if str(actual) != str(expected):
                matched = False
                break
        if matched:
            return True
    return False
