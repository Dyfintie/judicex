from __future__ import annotations

from typing import Any

from .italian_numbers import to_words, variants_for_unit
from .numeric_verifier import classify_legal_rule_numbers

_ACTION_PATTERNS: tuple[tuple[str, str], ...] = (
    ("notific", "notificazione"),
    ("oppos", "opposizione"),
    ("ademp", "adempimento"),
    ("pag", "pagamento"),
    ("consegn", "consegna"),
    ("deposit", "deposito"),
    ("emett", "emissione"),
    ("pronunc", "pronuncia"),
    ("prescriv", "prescrizione"),
    ("esecut", "esecuzione"),
    ("sospend", "sospensione"),
    ("compet", "competenza"),
    ("prova", "prova"),
    ("mora", "costituzione in mora"),
    ("interess", "interessi"),
    ("ricorso", "ricorso"),
    ("reclamo", "reclamo"),
    ("iscrizion", "iscrizione"),
)

def enforce_answer_contract(
    payload: dict[str, Any],
    context: dict[str, Any],
    *,
    client: Any | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    if payload.get("status") not in {"grounded", "limited"}:
        return {
            **payload,
            "_answer_contract": {
                "status": "skipped",
                "reason": f"status={payload.get('status')}",
                "traces": [],
            },
        }

    docs = (context.get("documents") or []) + (context.get("related_documents") or [])
    docs_by_id = {doc["id"]: doc for doc in docs}
    atoms = context.get("legal_atoms") or []
    atoms_by_doc: dict[str, list[dict[str, Any]]] = {}
    for atom in atoms:
        atoms_by_doc.setdefault(str(atom.get("document_id", "")), []).append(atom)

    matter_facts = _flatten_matter_facts(context)
    conflicts_report = context.get("conflicts") or {}
    blocked_doc_ids = set(conflicts_report.get("blocked_document_ids") or [])
    warning_doc_ids = set(conflicts_report.get("warning_document_ids") or [])
    as_of_date = str(context.get("as_of_date") or "").strip()
    findings_by_doc: dict[str, list[dict[str, Any]]] = {}
    for finding in conflicts_report.get("findings") or []:
        findings_by_doc.setdefault(str(finding.get("document_id", "")), []).append(finding)

    retained: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    for index, claim in enumerate(payload.get("claims") or []):
        trace = _verify_claim(
            index=index,
            claim=claim,
            docs_by_id=docs_by_id,
            atoms_by_doc=atoms_by_doc,
            matter_facts=matter_facts,
            client=client,
            model=model,
            blocked_doc_ids=blocked_doc_ids,
            warning_doc_ids=warning_doc_ids,
            findings_by_doc=findings_by_doc,
            as_of_date=as_of_date,
        )
        traces.append(trace)
        if trace["passed"]:
            enriched = dict(claim)
            enriched["supporting_atoms"] = trace["supporting_atoms"]
            enriched["numeric_facts"] = trace["numeric_facts"]
            retained.append(enriched)
        else:
            rejected.append({"claim": claim, "reasons": trace["violations"]})

    total = len(payload.get("claims") or [])
    if not retained:
        # Fail closed when every legal claim is rejected. A real citation only
        # proves that the document was retrieved; it does not make an
        # unsupported legal rule safe to render.
        return {
            **payload,
            "status": "abstain",
            "intro": "Non dispongo di elementi sufficienti nelle fonti recuperate per una risposta affidabile.",
            "claims": [],
            "missing_information": payload.get("missing_information") or [],
            "_answer_contract": {
                "status": "failed",
                "user_visible": False,
                "claims_total": total,
                "claims_retained": 0,
                "claims_rejected": len(rejected),
                "rejected_claims": rejected,
                "traces": traces,
            },
        }

    new_status = "limited" if rejected else payload.get("status", "grounded")
    return {
        **payload,
        "status": new_status,
        "claims": retained,
        "missing_information": payload.get("missing_information") or [],
        "_answer_contract": {
            "status": "passed" if not rejected else "limited",
            "user_visible": False,
            "claims_total": total,
            "claims_retained": len(retained),
            "claims_rejected": len(rejected),
            "rejected_claims": rejected,
            "traces": traces,
        },
    }


def _verify_claim(
    *,
    index: int,
    claim: dict[str, Any],
    docs_by_id: dict[str, dict[str, Any]],
    atoms_by_doc: dict[str, list[dict[str, Any]]],
    matter_facts: list[dict[str, str]],
    client: Any | None,
    model: str | None,
    blocked_doc_ids: set[str],
    warning_doc_ids: set[str],
    findings_by_doc: dict[str, list[dict[str, Any]]],
    as_of_date: str,
) -> dict[str, Any]:
    text = str(claim.get("text", ""))
    citations = [str(citation) for citation in claim.get("citations", [])]
    violations: list[str] = []
    warnings: list[str] = []
    supporting_atoms: list[str] = []

    if not citations:
        violations.append("claim senza citazioni")
    for citation in citations:
        if citation not in docs_by_id:
            violations.append(f"citazione fuori contesto: {citation}")
            continue
        if citation in blocked_doc_ids:
            offenders = findings_by_doc.get(citation, [])
            offender_summary = ", ".join(
                f"abrogata da {f.get('by_document_id') or f.get('by_title') or '?'}"
                for f in offenders
                if f.get("severity") == "abrogated"
            ) or "norma abrogata"
            violations.append(f"fonte non vigente: {citation} ({offender_summary})")
            continue
        cited_doc = docs_by_id[citation]
        if as_of_date and not _doc_is_vigent(cited_doc, as_of_date):
            violations.append(
                f"fonte fuori vigenza alla data {as_of_date}: {citation} "
                f"(effective_from={cited_doc.get('effective_from','')!r}, "
                f"effective_to={cited_doc.get('effective_to','')!r})"
            )
            continue
        if citation in warning_doc_ids:
            findings = findings_by_doc.get(citation, [])
            for finding in findings:
                severity = finding.get("severity")
                if severity in {"modified", "derogated", "conflict"}:
                    warnings.append(
                        f"{citation}: {severity} ({finding.get('summary') or finding.get('by_document_id','')})"
                    )

    if client is not None and model:
        numeric_facts = classify_legal_rule_numbers(
            client,
            model,
            claim_text=text,
            matter_facts=matter_facts,
        )
    else:
        numeric_facts = []

    for fact in numeric_facts:
        support = _find_fact_support(
            fact=fact,
            citations=citations,
            docs_by_id=docs_by_id,
            atoms_by_doc=atoms_by_doc,
        )
        if not support["supported"]:
            violations.append(
                f"regola numerica non supportata: {fact['value']} {fact['unit']} ({fact['action']})"
            )
            continue
        supporting_atoms.extend(
            atom_id for atom_id in support["atom_ids"] if atom_id not in supporting_atoms
        )

    return {
        "claim_index": index,
        "claim_text": text,
        "citations": citations,
        "passed": not violations,
        "violations": violations,
        "warnings": warnings,
        "numeric_facts": numeric_facts,
        "supporting_atoms": supporting_atoms,
    }


def _doc_is_vigent(doc: dict[str, Any], as_of_date: str) -> bool:
    if not as_of_date:
        return True
    eff_from = (doc.get("effective_from") or "").strip()
    eff_to = (doc.get("effective_to") or "").strip()
    if eff_from and eff_from > as_of_date:
        return False
    if eff_to and eff_to < as_of_date:
        return False
    return True


def _flatten_matter_facts(context: dict[str, Any]) -> list[dict[str, str]]:
    """Collect matter facts from the decomposer plan, if present.

    Numbers in matter facts (importi del cliente, date specifiche del caso) are
    NOT subject to legal-rule verification: the LLM classifier uses this list
    to skip them when extracting verifiable rules from a claim.
    """

    plan = context.get("decomposition") or {}
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for scenario in plan.get("scenarios", []) or []:
        for fact in scenario.get("matter_facts", []) or []:
            if not isinstance(fact, dict):
                continue
            role = str(fact.get("role") or "altro")
            value = str(fact.get("value") or "").strip()
            if not value:
                continue
            key = (role, value.lower())
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "role": role,
                    "value": value,
                    "normalized": str(fact.get("normalized") or value),
                }
            )
    return out


def _find_fact_support(
    *,
    fact: dict[str, str],
    citations: list[str],
    docs_by_id: dict[str, dict[str, Any]],
    atoms_by_doc: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    atom_ids: list[str] = []
    for citation in citations:
        for atom in atoms_by_doc.get(citation, []):
            if _atom_supports_fact(atom, fact):
                atom_id = str(atom.get("id", ""))
                if atom_id and atom_id not in atom_ids:
                    atom_ids.append(atom_id)
    if atom_ids:
        return {"supported": True, "atom_ids": atom_ids}

    for citation in citations:
        doc = docs_by_id.get(citation)
        if not doc:
            continue
        content = str(doc.get("content") or doc.get("excerpt") or "")
        if _source_text_supports_fact(content, fact):
            return {"supported": True, "atom_ids": []}
    return {"supported": False, "atom_ids": []}


def _atom_supports_fact(atom: dict[str, Any], fact: dict[str, str]) -> bool:
    if str(atom.get("value", "")) != fact["value"]:
        return False
    if _normalize_unit(str(atom.get("unit", ""))) != fact["unit"]:
        return False
    action = fact.get("action", "regola")
    if action == "regola":
        return True
    atom_action = str(atom.get("action", "")).lower()
    source_quote = str(atom.get("source_quote", "")).lower()
    if action == atom_action:
        return True
    # The atomizer's action stems (e.g. "prescriv") are tuned for verb forms;
    # the LLM-driven verifier emits noun labels (e.g. "prescrizione"). Accept
    # either the full label or the stem as a substring of the source quote.
    return action in source_quote or _action_stem(action) in source_quote


def _source_text_supports_fact(content: str, fact: dict[str, str]) -> bool:
    lowered = content.lower()
    value = int(fact["value"])
    unit = fact["unit"]
    variants = variants_for_unit(value, unit)
    if not any(variant in lowered for variant in variants):
        return False
    action = fact.get("action", "regola")
    if action == "regola":
        return True
    return action in lowered or _action_stem(action) in lowered


def _action_stem(action: str) -> str:
    for marker, normalized in _ACTION_PATTERNS:
        if normalized == action:
            return marker
    return action[:8].lower()


def _normalize_unit(unit: str) -> str:
    lowered = unit.lower().strip()
    if lowered.startswith("giorn"):
        return "giorni"
    if lowered.startswith("ann"):
        return "anni"
    if lowered.startswith("mes"):
        return "mesi"
    if lowered in {"percento", "per cento"}:
        return "per cento"
    return lowered
