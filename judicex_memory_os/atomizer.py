from __future__ import annotations

import hashlib
import re
from typing import Any

from .italian_numbers import parse as parse_italian_number
from .models import Document, LegalAtom

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

_DEADLINE_MARKERS = (
    "giorn",
    "anno",
    "anni",
    "mese",
    "mesi",
    "termine",
    "entro",
    "decors",
    "non oltre",
)

_OBLIGATION_MARKERS = (
    "deve",
    "devono",
    "è tenuto",
    "e tenuto",
    "sono tenuti",
    "obbligo",
    "obbligazione",
)

_PERMISSION_MARKERS = (
    "può",
    "puo",
    "possono",
    "è ammessa",
    "e ammessa",
    "sono ammessi",
)


def document_version_id(document: Document | dict[str, Any]) -> str:
    doc_id = document.id if isinstance(document, Document) else str(document["id"])
    content = document.content if isinstance(document, Document) else str(document.get("content", ""))
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    return f"document_version:{doc_id}:{digest}"


def compile_document_atoms(document: Document | dict[str, Any]) -> list[LegalAtom]:
    payload = _document_payload(document)
    version_id = document_version_id(document)
    title = payload["title"]
    subject = _subject_from_title(title)
    atoms: list[LegalAtom] = []
    seen: set[tuple[str, str, str, str, str]] = set()

    for sentence_index, sentence in enumerate(_sentences(payload["content"])):
        atom_type = _atom_type(sentence)
        if atom_type == "":
            continue
        action = _action(sentence, title)
        numbers = _numbers(sentence)
        if atom_type == "deadline" and not numbers:
            continue

        if numbers:
            for value, unit, raw_value in numbers:
                key = (atom_type, action, str(value), unit, sentence)
                if key in seen:
                    continue
                seen.add(key)
                atoms.append(
                    _make_atom(
                        payload=payload,
                        version_id=version_id,
                        title=title,
                        subject=subject,
                        sentence=sentence,
                        sentence_index=sentence_index,
                        atom_index=len(atoms),
                        atom_type=atom_type,
                        action=action,
                        value=str(value),
                        unit=unit,
                        raw_value=raw_value,
                    )
                )
        else:
            key = (atom_type, action, "", "", sentence)
            if key in seen:
                continue
            seen.add(key)
            atoms.append(
                _make_atom(
                    payload=payload,
                    version_id=version_id,
                    title=title,
                    subject=subject,
                    sentence=sentence,
                    sentence_index=sentence_index,
                    atom_index=len(atoms),
                    atom_type=atom_type,
                    action=action,
                    value="",
                    unit="",
                    raw_value="",
                )
            )

    return atoms


def _document_payload(document: Document | dict[str, Any]) -> dict[str, str]:
    if isinstance(document, Document):
        return {
            "id": document.id,
            "title": document.title,
            "area": document.area,
            "content": document.content,
        }
    return {
        "id": str(document["id"]),
        "title": str(document.get("title", "")),
        "area": str(document.get("area", "")),
        "content": str(document.get("content", "")),
    }


def _make_atom(
    *,
    payload: dict[str, str],
    version_id: str,
    title: str,
    subject: str,
    sentence: str,
    sentence_index: int,
    atom_index: int,
    atom_type: str,
    action: str,
    value: str,
    unit: str,
    raw_value: str,
) -> LegalAtom:
    condition = _condition(sentence)
    anchor = _temporal_anchor(sentence)
    stable = "|".join([payload["id"], str(sentence_index), atom_type, action, value, unit, sentence])
    atom_id = f"atom:{hashlib.sha1(stable.encode('utf-8')).hexdigest()[:20]}"
    return LegalAtom(
        id=atom_id,
        document_id=payload["id"],
        document_version_id=version_id,
        area=payload["area"],
        atom_type=atom_type,
        subject=subject,
        action=action,
        value=value,
        unit=unit,
        temporal_anchor=anchor,
        condition_text=condition,
        source_quote=sentence,
        confidence=_confidence(atom_type=atom_type, action=action, value=value, condition=condition, anchor=anchor),
        metadata={
            "title": title,
            "sentence_index": sentence_index,
            "atom_index": atom_index,
            "raw_value": raw_value,
        },
    )


def _sentences(text: str) -> list[str]:
    normalized = text.replace("\r", "\n")
    normalized = re.sub(r"\(\([^)]+\)\)", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    chunks = re.split(r"(?<=[.;:])\s+|\n+", normalized)
    out: list[str] = []
    for chunk in chunks:
        cleaned = chunk.strip(" \t\n.;")
        if len(cleaned) < 18:
            continue
        if cleaned.upper().startswith("AGGIORNAMENTO"):
            continue
        out.append(cleaned)
    return out


def _subject_from_title(title: str) -> str:
    article = re.search(r"\bArt\.\s*([0-9]+(?:[- ][A-Za-z]+)?)", title)
    heading = ""
    heading_match = re.search(r"\(([^()]{3,120})\)", title)
    if heading_match:
        heading = heading_match.group(1).strip()
    if article and heading:
        return f"art. {article.group(1).strip()} - {heading}"
    if article:
        return f"art. {article.group(1).strip()}"
    return title.strip()


def _atom_type(sentence: str) -> str:
    lowered = sentence.lower()
    if any(marker in lowered for marker in _DEADLINE_MARKERS) and _numbers(sentence):
        return "deadline"
    if any(marker in lowered for marker in _OBLIGATION_MARKERS):
        return "obligation"
    if any(marker in lowered for marker in _PERMISSION_MARKERS):
        return "permission"
    return ""


def _action(sentence: str, title: str) -> str:
    lowered = f"{sentence} {title}".lower()
    for marker, action in _ACTION_PATTERNS:
        if marker in lowered:
            return action
    return "regola"


def _numbers(sentence: str) -> list[tuple[int, str, str]]:
    out: list[tuple[int, str, str]] = []
    pattern = r"\b([0-9]+|[A-Za-zÀ-ÿ]+)\s+(giorni|giorno|anni|anno|mesi|mese|settimane|settimana|ore|ora)\b"
    for match in re.finditer(pattern, sentence, flags=re.IGNORECASE):
        raw = match.group(1)
        unit = _normalize_unit(match.group(2))
        value = parse_italian_number(raw)
        if value is None:
            continue
        out.append((value, unit, raw))
    return out


def _normalize_unit(unit: str) -> str:
    lowered = unit.lower()
    if lowered.startswith("giorn"):
        return "giorni"
    if lowered.startswith("ann"):
        return "anni"
    if lowered.startswith("mes"):
        return "mesi"
    if lowered.startswith("settiman"):
        return "settimane"
    if lowered in ("ora", "ore"):
        return "ore"
    return lowered


def _condition(sentence: str) -> str:
    patterns = (
        r"\b(se|quando|qualora)\s+([^.;]{3,180})",
        r"\b(salvo che|eccetto|tranne)\s+([^.;]{3,180})",
    )
    for pattern in patterns:
        match = re.search(pattern, sentence, flags=re.IGNORECASE)
        if match:
            return " ".join(match.group(0).split()).strip(" ,")
    condition_bits: list[str] = []
    for marker in ("nel territorio", "in uno degli altri Stati", "in altri Stati"):
        pos = sentence.lower().find(marker.lower())
        if pos >= 0:
            condition_bits.append(sentence[pos:pos + 160].strip(" ,.;"))
    return "; ".join(condition_bits)


def _temporal_anchor(sentence: str) -> str:
    match = re.search(
        r"\b(dalla|dal|dallo|dall'|dalle|dopo|decorsi|entro|non oltre)\s+([^.;,]{3,120})",
        sentence,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    return " ".join(match.group(0).split()).strip(" ,")


def _confidence(*, atom_type: str, action: str, value: str, condition: str, anchor: str) -> float:
    score = 0.65
    if atom_type:
        score += 0.1
    if action != "regola":
        score += 0.1
    if value:
        score += 0.1
    if condition or anchor:
        score += 0.05
    return min(score, 0.98)
