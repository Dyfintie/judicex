"""LLM-driven extraction of typed citation edges from a legal document.

Given the text of an article or judgment we ask the model to enumerate every
**typed reference to another norm** it contains: citations, abrogations,
derogations, modifications, applications of a principle, alignments with a
precedent, declared conflicts. The output is structured JSON: each entry
identifies the target by code (cc / cpc / costituzione / legge / dlgs / dpr /
dl / regolamento / direttiva / sentenza) plus an article / commi / number
field, and quotes the supporting passage from the source.

The materialiser then turns each entry into a concrete edge in the typed
graph (`entities` + `edges` tables). Each document also becomes an entity of
kind=document so that all paths in the citator query are addressable.
External references that do not correspond to a document already in the
store land as `kind=external_reference` entities so the graph stays
auditable rather than silently dropping them.
"""

from __future__ import annotations

import hashlib
import json
import re
import textwrap
from typing import Any, Iterable, Protocol


class LLMClient(Protocol):
    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
    ) -> str: ...


VALID_RELATIONS: frozenset[str] = frozenset(
    {
        "cita",
        "abroga",
        "deroga",
        "modifica",
        "applica_principio",
        "conforma_a",
        "confligge_con",
        "sostituisce",
        "integra",
    }
)

VALID_CODES: frozenset[str] = frozenset(
    {
        "cc",
        "cpc",
        "cp",
        "cpp",
        "costituzione",
        "legge",
        "dlgs",
        "dpr",
        "dl",
        "regolamento",
        "direttiva",
        "sentenza",
        "altro",
    }
)


_SYSTEM_PROMPT = textwrap.dedent(
    """
    Sei l'estrattore di riferimenti normativi di Judicex. Ricevi il testo di
    un articolo di legge o di un provvedimento e devi enumerare TUTTI i
    riferimenti tipizzati ad altre norme presenti nel testo.

    Per ogni riferimento individua:
      - relation: una sola fra
            cita, abroga, deroga, modifica, applica_principio, conforma_a,
            confligge_con, sostituisce, integra.
      - target: oggetto strutturato che identifica la norma di destinazione:
          {
            "code": "cc | cpc | cp | cpp | costituzione | legge | dlgs | dpr |
                     dl | regolamento | direttiva | sentenza | altro",
            "article": "numero articolo (es. '633', '2-bis') oppure ''",
            "comma": "numero comma oppure ''",
            "number": "numero/identificativo dell'atto (es. '392/1978',
                       'C-280/00') oppure ''",
            "year": "anno (YYYY) oppure ''",
            "label": "stringa originale come compare nel testo"
          }
      - evidence_quote: il frammento testuale (max 240 caratteri) che
        giustifica la classificazione.
      - summary: una frase italiana che spiega la relazione (max 200 caratteri).

    Regole:
      - NON inventare riferimenti non presenti nel testo.
      - Se un riferimento è generico ("la disciplina vigente", "la legge")
        senza articolo o atto, NON includerlo.
      - Non duplicare lo stesso (relation, target).
      - Se non ci sono riferimenti, restituisci {"references": []}.
      - Risposta SOLO JSON valido, senza testo prima o dopo:

    {
      "references": [
        {
          "relation": "...",
          "target": { ... },
          "evidence_quote": "...",
          "summary": "..."
        }
      ]
    }
    """
).strip()


def extract_norm_references(
    client: LLMClient,
    model: str,
    *,
    document: dict[str, Any],
    max_references: int = 30,
) -> list[dict[str, Any]]:
    """Run the LLM extractor on a document and return validated references."""

    title = str(document.get("title", "")).strip()
    content = str(document.get("content", "")).strip()
    if not content:
        return []

    briefing = {
        "document_id": document.get("id", ""),
        "document_title": title,
        "document_kind": document.get("kind", ""),
        "document_area": document.get("area", ""),
        "content": content[:8000],
    }
    try:
        raw = client.chat(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(briefing, ensure_ascii=False, separators=(",", ":")),
                },
            ],
            temperature=0.0,
        )
    except Exception:
        return []

    try:
        parsed = _extract_json_object(raw)
    except ValueError:
        return []

    references = parsed.get("references")
    if not isinstance(references, list):
        return []

    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for entry in references[:max_references]:
        normalised = _normalise_reference(entry)
        if normalised is None:
            continue
        target = normalised["target"]
        key = (
            normalised["relation"],
            f"{target['code']}|{target['article']}|{target['number']}|{target['year']}",
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(normalised)
    return out


def materialise_references(
    store: Any,
    *,
    document: dict[str, Any],
    references: Iterable[dict[str, Any]],
) -> dict[str, int]:
    """Persist entities + typed edges from the extractor output.

    Idempotent: re-running on the same document does not create duplicate
    edges because edge ids are content-derived (hash of source/relation/target).
    Returns counts of resolved/unresolved/total edges so the caller can audit
    what landed.
    """

    from .models import Edge

    source_doc_id = str(document["id"])
    source_entity_id = store.upsert_document_entity(document)

    counts = {"total": 0, "resolved": 0, "unresolved": 0}

    for ref in references:
        target = ref["target"]
        relation = ref["relation"]
        target_doc_id = _resolve_target_to_doc_id(
            store,
            target,
            document.get("area", ""),
            exclude_doc_id=source_doc_id,
        )
        if target_doc_id:
            target_doc = store.get_document(target_doc_id)
            if target_doc is not None:
                target_entity_id = store.upsert_document_entity(target_doc)
                counts["resolved"] += 1
            else:
                target_entity_id = _ensure_external_reference_entity(store, target, document.get("area", ""))
                counts["unresolved"] += 1
        else:
            target_entity_id = _ensure_external_reference_entity(store, target, document.get("area", ""))
            counts["unresolved"] += 1

        edge_id = _edge_id(source_entity_id, relation, target_entity_id)
        edge = Edge(
            id=edge_id,
            source_id=source_entity_id,
            target_id=target_entity_id,
            relation=relation,
            weight=1.0,
            summary=str(ref.get("summary", ""))[:500],
            metadata={
                "evidence_quote": str(ref.get("evidence_quote", ""))[:500],
                "target_label": target.get("label", ""),
                "source_document_id": source_doc_id,
                "target_document_id": target_doc_id or "",
            },
        )
        store.upsert_edge(edge)
        counts["total"] += 1

    return counts


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty output")
    if text.startswith("```"):
        text = "\n".join(line for line in text.splitlines() if not line.startswith("```")).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(str(exc)) from exc


def _normalise_reference(entry: Any) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None
    relation = str(entry.get("relation") or "").strip().lower()
    if relation not in VALID_RELATIONS:
        return None

    target_raw = entry.get("target") or {}
    if not isinstance(target_raw, dict):
        return None
    code = str(target_raw.get("code") or "").strip().lower()
    if code not in VALID_CODES:
        code = "altro"
    article = _normalise_article_token(target_raw.get("article"))
    comma = str(target_raw.get("comma") or "").strip()
    number = _normalise_act_number(target_raw.get("number"))
    year = _normalise_year(target_raw.get("year"))
    label = str(target_raw.get("label") or "").strip()[:300]

    if not (article or number or label):
        return None

    return {
        "relation": relation,
        "target": {
            "code": code,
            "article": article,
            "comma": comma,
            "number": number,
            "year": year,
            "label": label,
        },
        "evidence_quote": str(entry.get("evidence_quote") or "").strip()[:500],
        "summary": str(entry.get("summary") or "").strip()[:500],
    }


def _normalise_article_token(raw: Any) -> str:
    text = str(raw or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"^art\.?\s*", "", text)
    text = re.sub(r"\s+", "", text)
    return text


def _normalise_act_number(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    return re.sub(r"\s+", "", text)


def _normalise_year(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    match = re.search(r"(\d{4})", text)
    if not match:
        return ""
    year = int(match.group(1))
    if not (1800 <= year <= 2100):
        return ""
    return str(year)


def _resolve_target_to_doc_id(
    store: Any,
    target: dict[str, str],
    area: str,
    *,
    exclude_doc_id: str = "",
) -> str | None:
    """Try to find an already-ingested document matching the target reference.

    Strategy: search by `art<NUMBER>` token plus optional code prefix in the
    document id. The bundle ingest path uses ids like
    `normattiva:<bundle>:cpc_art633`, so this string match is reliable when
    the target is in-corpus, and gracefully returns None otherwise (the
    caller will materialise an external_reference entity).

    When `exclude_doc_id` is provided, the source document is filtered out of
    the candidate set so the extractor never produces self-loops (relevant
    when multiple temporal versions of the same article share the article
    number in their ids).
    """

    article = target.get("article", "")
    if not article:
        return None
    normalised_article = re.sub(r"[^a-z0-9-]", "", article.lower())
    if not normalised_article:
        return None
    code = target.get("code", "")
    code_to_prefix = {
        "cc": "cc_art",
        "cpc": "cpc_art",
        "cp": "cp_art",
        "cpp": "cpp_art",
        "costituzione": "costituzione_art",
    }
    needle_specific = code_to_prefix.get(code)
    rows = store.conn.execute(
        "SELECT id FROM documents WHERE id LIKE ?",
        (f"%art{normalised_article}%",),
    ).fetchall()
    candidates = [str(row["id"]) for row in rows if str(row["id"]) != exclude_doc_id]
    if not candidates:
        return None

    if needle_specific:
        for candidate in candidates:
            lowered = candidate.lower()
            if needle_specific + normalised_article in lowered:
                if not _has_digit_after(lowered, needle_specific + normalised_article):
                    return candidate

    if area:
        for candidate in candidates:
            if area in candidate.lower():
                lowered = candidate.lower()
                if not _has_digit_after(lowered, "art" + normalised_article):
                    return candidate

    for candidate in candidates:
        lowered = candidate.lower()
        if not _has_digit_after(lowered, "art" + normalised_article):
            return candidate
    return None


def _has_digit_after(haystack: str, needle: str) -> bool:
    pos = haystack.find(needle)
    while pos != -1:
        end = pos + len(needle)
        if end < len(haystack) and haystack[end].isdigit():
            pos = haystack.find(needle, end)
            continue
        return False
    return True  # no occurrence at all → conservatively reject


def _ensure_external_reference_entity(store: Any, target: dict[str, str], area: str) -> str:
    from .models import Entity

    label = target.get("label") or _format_target_label(target)
    payload = json.dumps(
        {
            "code": target.get("code", ""),
            "article": target.get("article", ""),
            "comma": target.get("comma", ""),
            "number": target.get("number", ""),
            "year": target.get("year", ""),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    entity_id = "extref:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    existing = store.conn.execute(
        "SELECT id FROM entities WHERE id = ?", (entity_id,)
    ).fetchone()
    if existing is not None:
        return entity_id
    entity = Entity(
        id=entity_id,
        name=label[:240],
        kind="external_reference",
        area=area,
        summary=label[:500],
        metadata={
            "external_target": True,
            **{k: v for k, v in target.items() if v},
        },
    )
    store.upsert_entity(entity)
    return entity_id


def _format_target_label(target: dict[str, str]) -> str:
    bits: list[str] = []
    code = target.get("code", "")
    if code:
        bits.append(code)
    if target.get("article"):
        bits.append(f"art. {target['article']}")
    if target.get("number"):
        bits.append(target["number"])
    if target.get("year"):
        bits.append(f"({target['year']})")
    return " ".join(bits) or "riferimento esterno"


def _edge_id(source_entity_id: str, relation: str, target_entity_id: str) -> str:
    digest = hashlib.sha256(
        f"{source_entity_id}|{relation}|{target_entity_id}".encode("utf-8")
    ).hexdigest()[:24]
    return f"edge:{relation}:{digest}"
