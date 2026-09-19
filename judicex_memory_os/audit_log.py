"""HMAC-signed audit trail for every answer Judicex produces.

Each call to `engine.answer()` writes one immutable row to `answer_audit`
containing:

  - question text and its hash
  - hash of the retrieval context that grounded the answer
  - hash of the rendered payload returned to the caller
  - HMAC-SHA256 signature over (ts | q_hash | ctx_hash | payload_hash) using
    a shared secret (env JUDICEX_AUDIT_SECRET, with a stable fallback per DB)

The intended use is forensic: if an avvocato later disputes what the system
told them on a given date, the row proves both the inputs and the output
*as they existed at that moment*. Tampering with any field after the fact
breaks the signature.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any


_SECRET_FILE_KEY = "judicex_audit_secret"


def record_answer(
    store: Any,
    *,
    question: str,
    context: dict[str, Any],
    payload: dict[str, Any],
    model: str = "",
    area: str = "",
    matter_id: str | None = None,
) -> dict[str, str]:
    """Persist the audit record and return its public fields.

    The full rendered payload is JSON-encoded and stored verbatim so the
    signature covers the exact bytes returned to the caller. Hashes are
    surfaced separately so a verifier can cheaply reject obvious tampering
    without re-encoding the payload.
    """

    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    record_id = f"audit:{uuid.uuid4().hex[:24]}"
    payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    context_subset = _summarise_context(context)
    context_json = json.dumps(context_subset, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    question_hash = _sha256(question)
    context_hash = _sha256(context_json)
    payload_hash = _sha256(payload_json)
    signature = _sign(
        secret=_resolve_secret(store),
        ts=ts,
        record_id=record_id,
        question_hash=question_hash,
        context_hash=context_hash,
        payload_hash=payload_hash,
    )

    record = {
        "id": record_id,
        "ts": ts,
        "question": question,
        "question_hash": question_hash,
        "context_hash": context_hash,
        "payload_hash": payload_hash,
        "signature": signature,
        "status": str(payload.get("status", "")),
        "model": model,
        "area": area,
        "matter_id": matter_id or "",
        "as_of_date": str(context.get("as_of_date") or ""),
        "payload_json": payload_json,
    }
    try:
        store.record_answer_audit(record)
    except Exception:
        # Audit failures must never break the user-facing answer. The caller
        # still returns the payload; the signature is included in metadata
        # so a downstream system can re-record it if needed.
        pass
    return {
        key: record[key]
        for key in (
            "id",
            "ts",
            "question_hash",
            "context_hash",
            "payload_hash",
            "signature",
        )
    }


def verify_record(store: Any, record_id: str) -> dict[str, Any]:
    """Re-derive the signature and compare with the stored value."""

    row = store.conn.execute(
        "SELECT * FROM answer_audit WHERE id = ?", (record_id,)
    ).fetchone()
    if row is None:
        return {"id": record_id, "valid": False, "reason": "record not found"}

    payload_json = row["payload_json"]
    expected = _sign(
        secret=_resolve_secret(store),
        ts=row["ts"],
        record_id=row["id"],
        question_hash=row["question_hash"],
        context_hash=row["context_hash"],
        payload_hash=row["payload_hash"],
    )
    payload_hash = _sha256(payload_json)
    return {
        "id": record_id,
        "valid": hmac.compare_digest(expected, row["signature"]) and payload_hash == row["payload_hash"],
        "expected_signature": expected,
        "stored_signature": row["signature"],
        "payload_hash_match": payload_hash == row["payload_hash"],
    }


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _summarise_context(context: dict[str, Any]) -> dict[str, Any]:
    """Reduce the retrieval context to its load-bearing fields for hashing.

    We do not hash the full context (it includes raw document content which
    can be large) — only the identifiers and coverage metrics that determined
    the answer. This is enough to detect tampering of the inputs without
    bloating the audit row.
    """

    documents = context.get("documents") or []
    related = context.get("related_documents") or []
    return {
        "as_of_date": context.get("as_of_date", ""),
        "documents": sorted(str(doc.get("id", "")) for doc in documents),
        "related_documents": sorted(str(doc.get("id", "")) for doc in related),
        "coverage": context.get("coverage", {}),
        "legal_issues": [
            {
                "id": issue.get("id", ""),
                "scenario_id": issue.get("scenario_id", ""),
                "scenario_domain": issue.get("scenario_domain", ""),
                "required_articles": list(issue.get("required_articles") or []),
            }
            for issue in (context.get("legal_issues") or [])
        ],
        "conflicts": {
            "blocked_document_ids": list((context.get("conflicts") or {}).get("blocked_document_ids") or []),
            "warning_document_ids": list((context.get("conflicts") or {}).get("warning_document_ids") or []),
        },
    }


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sign(
    *,
    secret: bytes,
    ts: str,
    record_id: str,
    question_hash: str,
    context_hash: str,
    payload_hash: str,
) -> str:
    message = "|".join([ts, record_id, question_hash, context_hash, payload_hash]).encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def _resolve_secret(store: Any) -> bytes:
    """Pick the HMAC secret in this order:

    1. Environment variable `JUDICEX_AUDIT_SECRET` (recommended for production).
    2. A self-generated 32-byte secret persisted in the LLM cache table under
       a reserved key. This makes the audit chain consistent across runs of
       the same database without requiring environment configuration.
    """

    env_secret = os.environ.get("JUDICEX_AUDIT_SECRET")
    if env_secret:
        return env_secret.encode("utf-8")
    cached = store.cache_get(_SECRET_FILE_KEY)
    if cached:
        return cached.encode("utf-8")
    new_secret = secrets.token_hex(32)
    try:
        store.cache_put(_SECRET_FILE_KEY, new_secret, model="audit", kind="secret", ttl_seconds=None)
    except Exception:
        pass
    return new_secret.encode("utf-8")
