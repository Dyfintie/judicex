from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any


DEFAULT_WORKFLOW_PACK = "civil_matter_analysis"


@dataclass(frozen=True, slots=True)
class Requirement:
    id: str
    label: str
    description: str
    required: bool
    fact_types: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()
    fact_terms: tuple[str, ...] = ()
    document_terms: tuple[str, ...] = ()
    suggestion: str = ""


@dataclass(frozen=True, slots=True)
class AnalysisProfile:
    id: str
    label: str
    match_terms: tuple[str, ...]
    requirements: tuple[Requirement, ...]


@dataclass(frozen=True, slots=True)
class WorkflowPack:
    id: str
    version: str
    label: str
    default_profile_id: str
    profiles: tuple[AnalysisProfile, ...]
    source: str


def analyze_matter_context(
    matter_context: dict[str, Any],
    thesis: str,
    *,
    workflow_pack: str | Path | dict[str, Any] | None = None,
) -> dict[str, Any]:
    if "error" in matter_context:
        return {"status": "error", "error": matter_context["error"], "thesis": thesis}

    pack = load_workflow_pack(workflow_pack)
    profile = select_profile(thesis, pack=pack)
    facts = _unique_by_id(_collect_facts(matter_context))
    documents = _unique_by_id(matter_context.get("documents") or [])
    requirement_results = [
        _evaluate_requirement(requirement, facts=facts, documents=documents)
        for requirement in profile.requirements
    ]

    required = [item for item in requirement_results if item["required"]]
    present_required = [item for item in required if item["status"] == "present"]
    partial_required = [item for item in required if item["status"] == "partial"]
    missing_required = [item for item in required if item["status"] == "missing"]
    optional_gaps = [item for item in requirement_results if not item["required"] and item["status"] == "missing"]

    score = _readiness_score(required, present_required, partial_required)
    status = _readiness_status(required, present_required, partial_required, missing_required)
    supporting_facts = _unique_by_id(
        fact
        for item in requirement_results
        for fact in item["supporting_facts"]
    )
    supporting_documents = _unique_by_id(
        doc
        for item in requirement_results
        for doc in item["supporting_documents"]
    )

    return {
        "status": status,
        "readiness_score": score,
        "thesis": thesis,
        "workflow_pack": {
            "id": pack.id,
            "version": pack.version,
            "label": pack.label,
            "source": pack.source,
        },
        "profile": {"id": profile.id, "label": profile.label},
        "matter": matter_context.get("matter") or {},
        "coverage": matter_context.get("coverage") or {},
        "requirements": requirement_results,
        "present_requirements": [item for item in requirement_results if item["status"] == "present"],
        "partial_requirements": [item for item in requirement_results if item["status"] == "partial"],
        "missing_requirements": missing_required,
        "optional_gaps": optional_gaps,
        "supporting_facts": supporting_facts,
        "supporting_documents": supporting_documents,
        "next_actions": _next_actions(missing_required, optional_gaps),
    }


def list_builtin_workflow_packs() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    package_files = resources.files("judicex_memory_os.workflow_packs")
    for item in sorted(package_files.iterdir(), key=lambda path: path.name):
        if item.suffix != ".json":
            continue
        raw = json.loads(item.read_text(encoding="utf-8"))
        out.append(
            {
                "id": str(raw.get("id", item.stem)),
                "version": str(raw.get("version", "")),
                "label": str(raw.get("label", "")),
            }
        )
    return out


def load_workflow_pack(workflow_pack: str | Path | dict[str, Any] | None = None) -> WorkflowPack:
    if isinstance(workflow_pack, dict):
        source = str(workflow_pack.get("source", "runtime"))
        return _workflow_pack_from_dict(workflow_pack, source=source)

    if workflow_pack is None or str(workflow_pack).strip() in {"", "default"}:
        workflow_pack = DEFAULT_WORKFLOW_PACK

    pack_text: str
    source: str
    pack_path = Path(str(workflow_pack))
    if pack_path.exists():
        pack_text = pack_path.read_text(encoding="utf-8")
        source = str(pack_path)
    else:
        pack_name = str(workflow_pack)
        if not pack_name.endswith(".json"):
            pack_name = f"{pack_name}.json"
        resource = resources.files("judicex_memory_os.workflow_packs").joinpath(pack_name)
        if not resource.is_file():
            raise ValueError(f"workflow pack not found: {workflow_pack}")
        pack_text = resource.read_text(encoding="utf-8")
        source = f"builtin:{pack_name}"
    return _workflow_pack_from_dict(json.loads(pack_text), source=source)


def select_profile(thesis: str, *, pack: WorkflowPack | None = None) -> AnalysisProfile:
    pack = pack or load_workflow_pack()
    lowered = thesis.lower()
    scored: list[tuple[int, int, AnalysisProfile]] = []
    for index, profile in enumerate(pack.profiles):
        score = sum(1 for term in profile.match_terms if term.lower() in lowered)
        scored.append((score, -index, profile))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    if scored and scored[0][0] > 0:
        return scored[0][2]
    for profile in pack.profiles:
        if profile.id == pack.default_profile_id:
            return profile
    return pack.profiles[-1]


def _workflow_pack_from_dict(raw: dict[str, Any], *, source: str) -> WorkflowPack:
    profiles = tuple(_profile_from_dict(item) for item in raw.get("profiles") or [])
    if not profiles:
        raise ValueError("workflow pack must contain at least one profile")
    pack_id = str(raw.get("id", "")).strip()
    if not pack_id:
        raise ValueError("workflow pack id is required")
    default_profile_id = str(raw.get("default_profile_id", "")).strip() or profiles[-1].id
    return WorkflowPack(
        id=pack_id,
        version=str(raw.get("version", "")).strip(),
        label=str(raw.get("label", pack_id)).strip(),
        default_profile_id=default_profile_id,
        profiles=profiles,
        source=source,
    )


def _profile_from_dict(raw: dict[str, Any]) -> AnalysisProfile:
    profile_id = str(raw.get("id", "")).strip()
    if not profile_id:
        raise ValueError("workflow profile id is required")
    requirements = tuple(_requirement_from_dict(item) for item in raw.get("requirements") or [])
    if not requirements:
        raise ValueError(f"workflow profile has no requirements: {profile_id}")
    return AnalysisProfile(
        id=profile_id,
        label=str(raw.get("label", profile_id)).strip(),
        match_terms=_tuple_of_str(raw.get("match_terms", [])),
        requirements=requirements,
    )


def _requirement_from_dict(raw: dict[str, Any]) -> Requirement:
    requirement_id = str(raw.get("id", "")).strip()
    if not requirement_id:
        raise ValueError("requirement id is required")
    return Requirement(
        id=requirement_id,
        label=str(raw.get("label", requirement_id)).strip(),
        description=str(raw.get("description", "")).strip(),
        required=bool(raw.get("required", True)),
        fact_types=_tuple_of_str(raw.get("fact_types", [])),
        labels=_tuple_of_str(raw.get("labels", [])),
        fact_terms=_tuple_of_str(raw.get("fact_terms", [])),
        document_terms=_tuple_of_str(raw.get("document_terms", [])),
        suggestion=str(raw.get("suggestion", "")).strip(),
    )


def _evaluate_requirement(
    requirement: Requirement,
    *,
    facts: list[dict[str, Any]],
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    supporting_facts = [fact for fact in facts if _fact_matches_requirement(fact, requirement)]
    supporting_documents = [doc for doc in documents if _document_matches_requirement(doc, requirement)]

    if supporting_facts:
        status = "present"
    elif supporting_documents:
        status = "partial"
    else:
        status = "missing"

    return {
        "id": requirement.id,
        "label": requirement.label,
        "description": requirement.description,
        "required": requirement.required,
        "status": status,
        "supporting_facts": supporting_facts[:8],
        "supporting_documents": supporting_documents[:8],
        "suggestion": requirement.suggestion,
    }


def _fact_matches_requirement(fact: dict[str, Any], requirement: Requirement) -> bool:
    fact_type = str(fact.get("fact_type", "")).lower()
    label = str(fact.get("label", "")).lower()
    searchable = _join_text(
        fact.get("label", ""),
        fact.get("text", ""),
        fact.get("value", ""),
        fact.get("unit", ""),
        fact.get("date_value", ""),
        fact.get("source_quote", ""),
    )
    if requirement.fact_types and fact_type not in requirement.fact_types:
        type_match = False
    else:
        type_match = bool(requirement.fact_types)
    label_match = bool(requirement.labels and any(term in label for term in requirement.labels))
    term_match = bool(requirement.fact_terms and any(term in searchable for term in requirement.fact_terms))
    if requirement.labels and fact_type == "party":
        return label_match or term_match
    if requirement.fact_types and not requirement.fact_terms and not requirement.labels:
        return type_match
    return (
        type_match and (label_match or term_match or not requirement.labels and not requirement.fact_terms)
    ) or label_match or term_match


def _document_matches_requirement(doc: dict[str, Any], requirement: Requirement) -> bool:
    searchable = _join_text(
        doc.get("title", ""),
        doc.get("kind", ""),
        doc.get("excerpt", ""),
        doc.get("content", ""),
        doc.get("source_path", ""),
    )
    return bool(requirement.document_terms and any(term in searchable for term in requirement.document_terms))


def _collect_facts(matter_context: dict[str, Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for key in ("facts", "timeline", "parties", "amounts", "deadlines"):
        for item in matter_context.get(key) or []:
            if isinstance(item, dict):
                facts.append(item)
    return facts


def _unique_by_id(items: Any) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id", "")).strip()
        if item_id and item_id in seen:
            continue
        if item_id:
            seen.add(item_id)
        out.append(item)
    return out


def _tuple_of_str(values: Any) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    return tuple(str(value).strip().lower() for value in values if str(value).strip())


def _join_text(*values: Any) -> str:
    return " ".join(str(value or "").lower() for value in values)


def _readiness_score(
    required: list[dict[str, Any]],
    present_required: list[dict[str, Any]],
    partial_required: list[dict[str, Any]],
) -> int:
    if not required:
        return 100
    points = len(present_required) + (0.5 * len(partial_required))
    return int(round((points / len(required)) * 100))


def _readiness_status(
    required: list[dict[str, Any]],
    present_required: list[dict[str, Any]],
    partial_required: list[dict[str, Any]],
    missing_required: list[dict[str, Any]],
) -> str:
    if not required:
        return "ready"
    if not missing_required and not partial_required:
        return "ready"
    if len(present_required) + len(partial_required) >= max(1, len(required) // 2):
        return "partial"
    return "insufficient"


def _next_actions(
    missing_required: list[dict[str, Any]],
    optional_gaps: list[dict[str, Any]],
) -> list[str]:
    actions: list[str] = []
    for item in missing_required:
        suggestion = str(item.get("suggestion", "")).strip()
        if suggestion and suggestion not in actions:
            actions.append(suggestion)
    for item in optional_gaps[:3]:
        suggestion = str(item.get("suggestion", "")).strip()
        if suggestion and suggestion not in actions:
            actions.append(suggestion)
    return actions
