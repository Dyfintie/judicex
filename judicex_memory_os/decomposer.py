"""LLM-driven decomposition of a user prompt into matter scenarios and legal issues.

Replaces the old keyword/regex pipeline (`_ISSUE_MARKERS`, `_classify_issue`,
`_issue_query`, `_required_articles`, `_coverage_terms`) with a single
language-model call that produces a structured plan. The model:

1. Splits the prompt into **independent matter scenarios** so retrieval queries
   for one scenario never get contaminated by facts of another.
2. Detects the legal domain of each scenario (so the agent can refuse early
   when the corresponding source bundle is not loaded).
3. Extracts matter facts (parties, amounts, dates, documents) — these are
   inputs from the user, not legal rules to verify against statutes.
4. For each scenario produces legal issues, each with a self-contained
   retrieval query, the list of required articles, and short coverage terms.
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
    Sei l'analizzatore di domande giuridiche di Judicex. La tua unica funzione
    è strutturare la domanda dell'utente in un piano di lavoro per il motore di
    retrieval e validazione: non rispondi alle domande, non citi fonti, non dai
    consigli.

    L'utente può presentare uno o più SCENARI giuridici nello stesso messaggio
    (recupero crediti, locazioni, lavoro, penale, ecc.). Devi:

    1. Spezzare il messaggio in scenari INDIPENDENTI: ogni scenario ha parti,
       fatti e oggetto giuridico autonomi. Le query di uno scenario non devono
       MAI contenere fatti di un altro scenario.

    1bis. Per ogni scenario indicare la AS_OF_DATE rilevante in formato
       YYYY-MM-DD: è la data alla quale va valutato il diritto applicabile.
       Regole:
         - Se lo scenario ha una data del fatto (emissione fattura, evento di
           inadempimento, licenziamento, ecc.) usa quella, perché determina la
           versione della norma applicabile al caso.
         - Se lo scenario è una richiesta di consulenza generica sullo stato
           attuale del diritto, usa "today" come marcatore (verrà risolto a
           runtime).
         - Se la data non è desumibile, usa "today".

    2. Per ogni scenario assegnare un DOMINIO GIURIDICO scegliendo SOLO da:
       - recupero_crediti
       - locazioni_sfratto
       - lavoro_disciplinare
       - lavoro_generale
       - contrattualistica
       - famiglia
       - successioni
       - penale
       - amministrativo
       - tributario
       - civile_generale
       - altro

    3. Per ogni scenario estrarre i MATTER FACTS, cioè i dati del caso forniti
       dall'utente (parti, importi, date, documenti, eventi, stati). Questi NON
       sono regole giuridiche: non vanno verificati contro fonti normative.
       Per ogni fact specifica:
         - role: parte_attiva | parte_passiva | importo | data | durata |
                 documento | evento | stato | luogo | altro
         - value: la stringa originale come compare nel testo
         - normalized: forma normalizzata (numero intero per importi/durate,
                       data ISO YYYY-MM-DD per le date, stringa pulita altrimenti)

    4. Per ogni scenario produrre le ISSUES (questioni giuridiche operative).
       Ogni issue:
         - title: etichetta breve in italiano (es. "Prescrizione del credito").
         - question: la sotto-domanda riformulata in modo autosufficiente.
         - retrieval_query: query di ricerca CHIUSA nello scenario. Includi i
           concetti giuridici essenziali e i numeri degli articoli pertinenti.
           NON includere i fatti specifici di altri scenari.
         - required_articles: lista di numeri di articolo (solo numero, es.
           "2946", "634", "660"). Sii esaustivo: se la materia ha varianti
           (prescrizione ordinaria 2946 + presuntiva 2948/2956), elencale tutte.
         - coverage_terms: 3-8 lemmi tecnici (parole singole), NO frasi.

    Restituisci SOLO JSON valido, senza testo prima o dopo, in questo formato:

    {
      "scenarios": [
        {
          "id": "s1",
          "summary": "una riga di sintesi dello scenario",
          "domain": "uno dei domini elencati",
          "as_of_date": "YYYY-MM-DD oppure 'today'",
          "matter_facts": [
            {"role": "...", "value": "...", "normalized": "..."}
          ],
          "issues": [
            {
              "id": "s1.i1",
              "title": "...",
              "question": "...",
              "retrieval_query": "...",
              "required_articles": ["...", "..."],
              "coverage_terms": ["...", "..."]
            }
          ]
        }
      ]
    }

    Vincoli:
    - NON inventare fatti che l'utente non ha menzionato.
    - NON rispondere alle domande, solo strutturare.
    - Se la domanda è una richiesta unica e atomica, restituisci comunque un
      solo scenario con una sola issue.
    - Se l'utente non fornisce fatti del caso (domanda puramente normativa),
      matter_facts puo' essere [].
    - Mai meno di 1 scenario, mai meno di 1 issue per scenario.
    """
).strip()


_VALID_DOMAINS: frozenset[str] = frozenset(
    {
        "recupero_crediti",
        "locazioni_sfratto",
        "lavoro_disciplinare",
        "lavoro_generale",
        "contrattualistica",
        "famiglia",
        "successioni",
        "penale",
        "amministrativo",
        "tributario",
        "civile_generale",
        "altro",
    }
)


def decompose(
    client: LLMClient,
    model: str,
    question: str,
    *,
    max_scenarios: int = 8,
    max_issues_per_scenario: int = 12,
) -> dict[str, Any]:
    """Run the LLM decomposer and return a validated, normalised plan.

    Returns a dict shaped exactly like the JSON above. On any failure the
    function raises `DecompositionError`; callers are expected to handle the
    fallback explicitly so failures stay visible in the trace.
    """

    cleaned_question = question.strip()
    if not cleaned_question:
        return _empty_plan()

    raw = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": cleaned_question},
        ],
        temperature=0.0,
    )
    parsed = _extract_json_object(raw)
    return _normalise_plan(
        parsed,
        max_scenarios=max_scenarios,
        max_issues_per_scenario=max_issues_per_scenario,
    )


class DecompositionError(RuntimeError):
    """Raised when the LLM output cannot be coerced into a valid plan."""


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        raise DecompositionError("decomposer returned empty output")
    if text.startswith("```"):
        text = "\n".join(line for line in text.splitlines() if not line.startswith("```")).strip()
    # tolerate models that prepend a sentence: take from first '{' to matching last '}'
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise DecompositionError(f"no JSON object in decomposer output: {text[:200]!r}")
    candidate = text[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise DecompositionError(f"decomposer output is not valid JSON: {exc}") from exc


def _normalise_plan(
    parsed: dict[str, Any],
    *,
    max_scenarios: int,
    max_issues_per_scenario: int,
) -> dict[str, Any]:
    scenarios_in = parsed.get("scenarios")
    if not isinstance(scenarios_in, list) or not scenarios_in:
        raise DecompositionError("decomposer plan has no scenarios")

    scenarios_out: list[dict[str, Any]] = []
    for scenario_index, scenario in enumerate(scenarios_in[:max_scenarios], start=1):
        if not isinstance(scenario, dict):
            continue
        scenario_id = _safe_id(scenario.get("id"), default=f"s{scenario_index}")
        domain = str(scenario.get("domain") or "").strip().lower().replace(" ", "_")
        if domain not in _VALID_DOMAINS:
            domain = "altro"
        summary = _clean_text(scenario.get("summary"))
        matter_facts = _normalise_matter_facts(scenario.get("matter_facts"))
        issues = _normalise_issues(
            scenario.get("issues"),
            scenario_id=scenario_id,
            limit=max_issues_per_scenario,
        )
        if not issues:
            continue
        scenarios_out.append(
            {
                "id": scenario_id,
                "summary": summary,
                "domain": domain,
                "as_of_date": _normalise_as_of_date(scenario.get("as_of_date")),
                "matter_facts": matter_facts,
                "issues": issues,
            }
        )

    if not scenarios_out:
        raise DecompositionError("decomposer plan had no usable scenarios after normalisation")

    return {"scenarios": scenarios_out}


_ISO_DATE_PATTERN = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def _normalise_as_of_date(raw: Any) -> str:
    """Validate the LLM-provided date.

    Accepts a strict YYYY-MM-DD ISO date or the sentinel "today" (which the
    runtime resolves against the current UTC date). Anything else is rejected
    and the field is dropped, so the caller falls back to its own default.
    """

    text = str(raw or "").strip().lower()
    if not text or text == "today":
        return ""
    match = _ISO_DATE_PATTERN.fullmatch(text)
    if not match:
        return ""
    year, month, day = (int(g) for g in match.groups())
    if not (1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31):
        return ""
    return f"{year:04d}-{month:02d}-{day:02d}"


def fallback_plan_today() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).date().isoformat()


def _normalise_matter_facts(raw: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if not isinstance(raw, list):
        return out
    valid_roles = {
        "parte_attiva",
        "parte_passiva",
        "importo",
        "data",
        "durata",
        "documento",
        "evento",
        "stato",
        "luogo",
        "altro",
    }
    for fact in raw:
        if not isinstance(fact, dict):
            continue
        role = str(fact.get("role") or "altro").strip().lower()
        if role not in valid_roles:
            role = "altro"
        value = _clean_text(fact.get("value"))
        if not value:
            continue
        normalized = _clean_text(fact.get("normalized")) or value
        out.append({"role": role, "value": value, "normalized": normalized})
    return out


def _normalise_issues(
    raw: Any,
    *,
    scenario_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return out
    for index, issue in enumerate(raw[:limit], start=1):
        if not isinstance(issue, dict):
            continue
        issue_id = _safe_id(issue.get("id"), default=f"{scenario_id}.i{index}")
        title = _clean_text(issue.get("title")) or "Questione giuridica"
        question = _clean_text(issue.get("question"))
        retrieval_query = _clean_text(issue.get("retrieval_query")) or question or title
        required_articles = _normalise_articles(issue.get("required_articles"))
        coverage_terms = _normalise_terms(issue.get("coverage_terms"))
        if not question:
            continue
        out.append(
            {
                "id": issue_id,
                "title": title,
                "question": question,
                "retrieval_query": retrieval_query,
                "required_articles": required_articles,
                "coverage_terms": coverage_terms,
            }
        )
    return out


def _normalise_articles(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for value in raw:
        text = str(value or "").strip().lower()
        if not text:
            continue
        # accept "art. 2946", "2946", "2946-bis"
        match = re.search(r"([0-9]+(?:[\-\s]?[a-z]+)?)", text)
        if not match:
            continue
        normalised = re.sub(r"\s+", "", match.group(1))
        if normalised in seen:
            continue
        seen.add(normalised)
        out.append(normalised)
        if len(out) >= 12:
            break
    return out


def _normalise_terms(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for value in raw:
        text = str(value or "").strip().lower()
        if not text or len(text) < 3:
            continue
        text = re.sub(r"\s+", " ", text)
        if text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= 10:
            break
    return out


def _safe_id(value: Any, *, default: str) -> str:
    text = str(value or "").strip()
    if not text:
        return default
    text = re.sub(r"[^a-zA-Z0-9._-]", "_", text)
    return text or default


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    return re.sub(r"\s+", " ", text)


def _empty_plan() -> dict[str, Any]:
    return {"scenarios": []}


def fallback_plan(question: str) -> dict[str, Any]:
    """Degenerate plan used when the LLM call cannot run (offline / failure).

    Treats the whole prompt as a single scenario with one issue. No keyword
    classification, no regex magic — just a passthrough so retrieval still has
    something to work with and the trace shows `decomposition_failed`.
    """

    cleaned = re.sub(r"\s+", " ", question or "").strip()
    if not cleaned:
        return _empty_plan()
    return {
        "scenarios": [
            {
                "id": "s1",
                "summary": cleaned[:240],
                "domain": "altro",
                "matter_facts": [],
                "issues": [
                    {
                        "id": "s1.i1",
                        "title": "Questione giuridica",
                        "question": cleaned,
                        "retrieval_query": cleaned,
                        "required_articles": [],
                        "coverage_terms": [],
                    }
                ],
            }
        ]
    }
