"""LLM-driven numeric classification for the answer contract.

The old verifier extracted EVERY number from a claim with a regex and required
each one to appear in an authoritative source. That is wrong by construction:
the claim restates user-provided facts (importi, date) which do not need
statutory support, while only **legal rule numbers** (a 10-year prescription,
a 40-day opposition window, a 5% rate) must be verifiable against the cited
articles.

This module replaces the regex extractor with a single language-model call
that, given the claim text and the matter facts already known to the system,
returns ONLY the numbers that express legal rules — together with their unit
and the legal action they bind. The downstream support check
(`_atom_supports_fact` / `_source_text_supports_fact` in answer_contract.py)
is unchanged.
"""

from __future__ import annotations

import json
import re
import textwrap
from typing import Any, Protocol


class LLMClient(Protocol):
    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
    ) -> str: ...


_SYSTEM_PROMPT = textwrap.dedent(
    """
    Sei un classificatore numerico per il motore di verifica di Judicex. Il tuo
    unico compito è separare i numeri all'interno di una claim giuridica già
    scritta in tre categorie:

    1. LEGAL RULE NUMBER (ASSERITO): un numero che la claim AFFERMA come
       contenuto di una regola normativa (termine processuale, durata di
       prescrizione, percentuale legale, soglia di legge). Esempi:
       "il termine è di sessanta giorni" -> 60 giorni asserito;
       "la prescrizione è di dieci anni" -> 10 anni asserito.

    2. NEGATED NUMBER: un numero che la claim ESPLICITAMENTE NEGA, smentisce
       o segnala come ASSENTE dalla norma. Esempi:
       "non esiste alcun termine di novanta giorni" -> 90 negato;
       "la norma non prevede 120 giorni" -> 120 negato;
       "non è previsto un saggio del 5%" -> 5 negato.
       Marker di negazione: "non", "alcun/a", "nessun/a", "smentisce",
       "esclude", "non prevede", "non è previsto", "non esiste", "non
       contiene", "diversamente da", "non corrisponde a".
       NON includere questi numeri tra i legal_rule_numbers — sono affermazioni
       sull'ASSENZA, non sulla PRESENZA, e non vanno verificati cercandoli
       nella fonte (sarebbe esattamente l'opposto di ciò che la claim dice).

    3. MATTER FACT NUMBER: un numero che riporta un FATTO DEL CASO già
       fornito dall'utente (importo, data, durata di un evento del cliente,
       quantità di documenti). Non deriva da una norma. Esempi:
       "8.500 euro" (fattura del cliente), "15 gennaio 2022" (data di
       emissione), "tre mensilità" (mancato pagamento).

    Ti viene fornita la claim testuale e l'elenco dei matter_facts già
    estratti. Devi restituire SOLO i LEGAL RULE NUMBERS ASSERITI (categoria 1),
    ignorando sia i NEGATED (cat. 2) sia i MATTER FACTS (cat. 3).

    Per ogni legal rule number asserito specifica:
      - value: il numero come INTERO (10, 40, 5). Se la claim usa una parola
        ("dieci"), restituisci comunque 10.
      - unit: una delle stringhe esatte: "giorni", "anni", "mesi", "per cento",
        "euro", "altro".
      - action: l'azione/istituto giuridico legato al numero. Usa una di queste
        etichette quando applicabile: "prescrizione", "opposizione",
        "notificazione", "adempimento", "pagamento", "consegna", "deposito",
        "emissione", "pronuncia", "esecuzione", "sospensione", "competenza",
        "prova", "interessi", "ricorso", "reclamo", "iscrizione",
        "costituzione in mora". Se nessuna calza, "regola".
      - raw: la stringa originale come compare nella claim (es. "dieci anni").

    Restituisci SOLO JSON valido in questo formato, senza testo prima o dopo:

    {
      "legal_rule_numbers": [
        {"value": 10, "unit": "anni", "action": "prescrizione", "raw": "dieci anni"}
      ]
    }

    Vincoli:
    - Se la claim non contiene alcun legal rule number asserito, restituisci
      {"legal_rule_numbers": []}.
    - NON inventare numeri non presenti nella claim.
    - NON includere mai numeri negati o smentiti dalla claim.
    - NON includere mai numeri che siano riportati anche nei matter_facts.
    - NON spiegare la classificazione, non aggiungere commenti.
    """
).strip()


_VALID_UNITS: frozenset[str] = frozenset(
    {"giorni", "anni", "mesi", "per cento", "euro", "altro"}
)


def classify_legal_rule_numbers(
    client: LLMClient,
    model: str,
    *,
    claim_text: str,
    matter_facts: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Run the LLM and return validated legal-rule numeric facts.

    Returns a list of `{value: str, unit: str, action: str, raw: str}` where
    `value` is the integer (as string) and `unit`/`action` are normalized.
    On any failure returns an empty list — the downstream verifier will simply
    treat the claim as having no numeric obligations to check, which is the
    safe default (citation/text checks still apply).
    """

    text = (claim_text or "").strip()
    if not text:
        return []

    briefing = {
        "claim": text,
        "matter_facts": matter_facts or [],
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

    raw_items = parsed.get("legal_rule_numbers")
    if not isinstance(raw_items, list):
        return []

    out: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for entry in raw_items:
        normalised = _normalise_entry(entry)
        if normalised is None:
            continue
        if _is_negated_in_claim(text, normalised):
            continue
        key = (normalised["value"], normalised["unit"], normalised["action"])
        if key in seen:
            continue
        seen.add(key)
        out.append(normalised)
    return out


_NEGATION_MARKERS: tuple[str, ...] = (
    "non ",
    "alcun",
    "nessun",
    "smentisce",
    "esclude",
    "non prevede",
    "non e' previsto",
    "non è previsto",
    "non esiste",
    "non contiene",
    "diversamente da",
    "non corrisponde",
    "non ha introdotto",
    "non ha previsto",
)


def _is_negated_in_claim(claim_text: str, fact: dict[str, str]) -> bool:
    """Defensive backstop: skip facts whose number appears in a negation context.

    The system prompt already instructs the LLM to filter negated numbers.
    This Python check protects against weaker models that ignore the rule
    and would otherwise cause the citation gate to reject a claim that is
    correctly *denying* a false premise (anti-sycophancy).
    """

    from .italian_numbers import to_words

    raw = (fact.get("raw") or "").lower().strip()
    digit = str(fact.get("value") or "").strip()
    word = to_words(int(digit)) if digit.isdigit() else None
    lowered = claim_text.lower()
    needles = [n for n in (raw, digit, word) if n]
    for needle in needles:
        idx = 0
        while True:
            pos = lowered.find(needle, idx)
            if pos < 0:
                break
            window_start = max(0, pos - 40)
            window = lowered[window_start:pos]
            if any(marker in window for marker in _NEGATION_MARKERS):
                return True
            idx = pos + len(needle)
    return False


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


def _normalise_entry(entry: Any) -> dict[str, str] | None:
    if not isinstance(entry, dict):
        return None
    raw_value = entry.get("value")
    try:
        value_int = int(raw_value) if not isinstance(raw_value, bool) else None
    except (TypeError, ValueError):
        # tolerate string forms like "10" or "  10 "
        try:
            value_int = int(str(raw_value).strip())
        except (TypeError, ValueError):
            return None
    if value_int is None or value_int < 0:
        return None

    unit = str(entry.get("unit") or "").strip().lower()
    if unit in {"giorno"}:
        unit = "giorni"
    elif unit in {"anno"}:
        unit = "anni"
    elif unit in {"mese"}:
        unit = "mesi"
    elif unit in {"percento"}:
        unit = "per cento"
    if unit not in _VALID_UNITS:
        unit = "altro"

    action = str(entry.get("action") or "regola").strip().lower()
    action = re.sub(r"\s+", " ", action)
    if not action:
        action = "regola"

    raw_text = str(entry.get("raw") or f"{value_int} {unit}").strip()

    return {
        "value": str(value_int),
        "unit": unit,
        "action": action,
        "raw": raw_text,
    }
