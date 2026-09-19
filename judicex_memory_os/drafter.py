"""Template-bound drafter for legal acts (atti).

The drafter renders a structured template (JSON) into a text block while
ENFORCING vigency at a given `as_of_date` for every cited norm. If a
required article is abrogated or missing from the corpus, the drafting
fails closed with a structured error rather than producing an unsafe atto.

Templates live under `judicex_memory_os/templates/atti/<name>.json` and
declare:

    {
      "name": "...",
      "title": "Ricorso per decreto ingiuntivo (...)",
      "required_articles": ["633", "634", "641", "642"],
      "required_params": ["creditore", "debitore", "importo", "causale"],
      "sections": [
        {"heading": "Premesso che", "body": "..., come risulta dalla fattura n. {fattura}"},
        {"heading": "Diritto", "body": "Il credito è azionabile ai sensi degli {ARTICLE_BLOCK}."}
      ]
    }

Placeholders:
- `{ARTICLE_BLOCK}` is replaced with a nicely-formatted list of vigent
  articles (with title + source_ref).
- `{ARTICLES.633}` selects a single cited article inline.
- `{param_name}` is replaced from the `params` dict.
- Any unresolved placeholder raises and the drafting fails.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "atti"
_PLACEHOLDER_PATTERN = re.compile(r"\{([A-Z_][A-Z0-9_]*|ARTICLES\.[A-Za-z0-9\-]+|[a-z_][a-z0-9_]*)\}")


class DraftingError(RuntimeError):
    """Raised when the drafter cannot safely render an atto."""


def list_templates() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if not _TEMPLATE_DIR.exists():
        return out
    for path in sorted(_TEMPLATE_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.append(
            {
                "name": str(data.get("name") or path.stem),
                "title": str(data.get("title", "")),
                "required_articles": ",".join(data.get("required_articles") or []),
                "required_params": ",".join(data.get("required_params") or []),
                "path": str(path),
            }
        )
    return out


def load_template(name: str) -> dict[str, Any]:
    candidate = Path(name)
    if candidate.exists():
        path = candidate
    else:
        path = _TEMPLATE_DIR / f"{name}.json"
    if not path.exists():
        raise DraftingError(f"template not found: {name}")
    return json.loads(path.read_text(encoding="utf-8"))


def draft_atto(
    store: Any,
    *,
    template_name: str,
    as_of_date: str,
    params: dict[str, str] | None = None,
    matter_id: str | None = None,
) -> dict[str, Any]:
    template = load_template(template_name)
    params = dict(params or {})

    if matter_id:
        params = {**_params_from_matter(store, matter_id), **params}

    missing_params = [
        key for key in (template.get("required_params") or []) if not params.get(key)
    ]
    if missing_params:
        raise DraftingError(
            f"missing required params for template {template['name']}: {missing_params}"
        )

    article_lookup = _resolve_articles(
        store,
        articles=template.get("required_articles") or [],
        as_of_date=as_of_date,
    )
    blocked = [a for a, info in article_lookup.items() if info["status"] in {"abrogato", "missing"}]
    if blocked:
        return {
            "status": "blocked",
            "template": template["name"],
            "as_of_date": as_of_date,
            "reason": "uno o più articoli richiesti non sono disponibili o non vigenti alla data",
            "blocked_articles": blocked,
            "article_status": article_lookup,
            "rendered": "",
            "citations": [],
        }

    article_block = _format_article_block(article_lookup)
    citations = _citations_payload(article_lookup)

    rendered_sections: list[dict[str, str]] = []
    for section in template.get("sections") or []:
        heading = str(section.get("heading", ""))
        body = _render_text(
            template_text=str(section.get("body", "")),
            params=params,
            article_block=article_block,
            article_lookup=article_lookup,
        )
        rendered_sections.append({"heading": heading, "body": body})

    rendered = _join_sections(template, rendered_sections, citations)

    return {
        "status": "drafted",
        "template": template["name"],
        "title": template.get("title", ""),
        "as_of_date": as_of_date,
        "matter_id": matter_id or "",
        "rendered": rendered,
        "sections": rendered_sections,
        "citations": citations,
        "article_status": article_lookup,
        "warnings": [
            f"art. {article}: {info['note']}"
            for article, info in article_lookup.items()
            if info.get("note")
        ],
    }


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _resolve_articles(
    store: Any,
    *,
    articles: list[str],
    as_of_date: str,
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for article in articles:
        article_token = str(article).strip().lower()
        if not article_token:
            continue
        doc = _find_document_for_article(store, article_token)
        if doc is None:
            out[article_token] = {
                "article": article_token,
                "status": "missing",
                "document_id": "",
                "title": "",
                "source_ref": "",
                "note": "non presente nel corpus locale; eseguire sync-bundle",
            }
            continue
        report = store.shepardize(doc["id"], as_of_date)
        note = ""
        if report["status"] == "abrogato":
            note = "norma abrogata alla data del fatto"
        elif report["status"] == "non_vigente_per_data":
            note = "versione fuori vigenza alla data del fatto"
        elif report.get("modifications"):
            note = "norma modificata; verificare versione applicabile"
        out[article_token] = {
            "article": article_token,
            "status": report["status"] if report["status"] in {"abrogato"} else (
                "ok" if report["status"] == "vigente" else "missing"
            ),
            "document_id": doc["id"],
            "title": doc.get("title", ""),
            "source_ref": doc.get("source_ref", ""),
            "effective_from": doc.get("effective_from", ""),
            "effective_to": doc.get("effective_to", ""),
            "note": note,
        }
    return out


def _find_document_for_article(store: Any, article: str) -> dict[str, Any] | None:
    """Pick the best document in the corpus matching `art<NUMBER>` token.

    When multiple temporal versions live in the store, prefer the one with no
    `effective_to` (still in force) over closed ones; the caller may further
    narrow by as_of_date through shepardize.
    """

    rows = store.conn.execute(
        "SELECT * FROM documents WHERE id LIKE ? ORDER BY effective_to DESC, id",
        (f"%art{article}%",),
    ).fetchall()
    for row in rows:
        doc = store._document_row_to_dict(row, full=True)
        if not (doc.get("effective_to") or "").strip():
            return doc
    if rows:
        return store._document_row_to_dict(rows[0], full=True)
    return None


def _format_article_block(article_lookup: dict[str, dict[str, Any]]) -> str:
    if not article_lookup:
        return ""
    bits: list[str] = []
    for entry in article_lookup.values():
        if entry["status"] != "ok":
            continue
        bits.append(f"art. {entry['article']} ({entry['title']})")
    return "; ".join(bits)


def _citations_payload(article_lookup: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "article": entry["article"],
            "document_id": entry["document_id"],
            "title": entry["title"],
            "source_ref": entry["source_ref"],
            "status": entry["status"],
            "note": entry.get("note", ""),
        }
        for entry in article_lookup.values()
    ]


def _render_text(
    *,
    template_text: str,
    params: dict[str, str],
    article_block: str,
    article_lookup: dict[str, dict[str, Any]],
) -> str:
    def _replace(match: re.Match[str]) -> str:
        token = match.group(1)
        if token == "ARTICLE_BLOCK":
            return article_block
        if token.startswith("ARTICLES."):
            article = token.split(".", 1)[1].lower()
            entry = article_lookup.get(article)
            if entry is None or entry["status"] != "ok":
                raise DraftingError(
                    f"placeholder {{{token}}} riferisce un articolo non disponibile/vigente: {article}"
                )
            return f"art. {entry['article']} {entry['title']}"
        if token in params:
            return str(params[token])
        if token.lower() in params:
            return str(params[token.lower()])
        raise DraftingError(f"placeholder non risolto: {{{token}}}")

    return _PLACEHOLDER_PATTERN.sub(_replace, template_text)


def _join_sections(
    template: dict[str, Any],
    rendered_sections: list[dict[str, str]],
    citations: list[dict[str, Any]],
) -> str:
    out: list[str] = []
    title = str(template.get("title") or "").strip()
    if title:
        out.append(title.upper())
        out.append("")
    for section in rendered_sections:
        if section["heading"]:
            out.append(section["heading"].upper())
        out.append(section["body"].strip())
        out.append("")
    if citations:
        out.append("CITAZIONI NORMATIVE")
        for citation in citations:
            status_marker = "" if citation["status"] == "ok" else f" [{citation['status']}]"
            note = f" — {citation['note']}" if citation.get("note") else ""
            out.append(
                f"- art. {citation['article']}{status_marker}: {citation['title']}{note}"
            )
    return "\n".join(out).strip()


def _params_from_matter(store: Any, matter_id: str) -> dict[str, str]:
    """Extract a flat params dict from matter facts: party, amount, date, fact_type → key=value."""

    matter = store.get_matter(matter_id)
    if matter is None:
        return {}
    params: dict[str, str] = {}
    facts = store.search_matter_facts("", matter_id=matter_id, top_k=200)
    for fact in facts:
        label = str(fact.get("label") or fact.get("fact_type") or "").strip().lower()
        text = str(fact.get("text") or "").strip()
        if not label or not text:
            continue
        key = re.sub(r"[^a-z0-9_]+", "_", label).strip("_")
        if key and key not in params:
            params[key] = text
    return params
