"""SQLite-backed LRU/TTL cache around any LLM client with `chat(model, messages, temperature)`.

We only cache calls whose result is a pure function of the prompt: the
decomposer and the numeric-rule classifier. Main-answer / repair / semantic
verifier calls depend on multi-turn state and side effects in the agent
trace, so caching them would silently invalidate user-visible diagnostics.

The cache key is `sha256(model | temperature | role | system | user)`, so a
prompt change in the system or user message produces a fresh key. Default
TTL is 7 days; pass `ttl_seconds=0` to make entries permanent for the
duration of the SQLite file.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Protocol


class _BaseClient(Protocol):
    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
    ) -> str: ...


_CACHEABLE_PREFIXES_DEFAULT: tuple[tuple[str, str], ...] = (
    ("Sei l'analizzatore di domande giuridiche", "decomposer"),
    ("Sei un classificatore numerico", "numeric_verifier"),
    ("Sei l'estrattore di riferimenti normativi", "entity_extractor"),
)


class CachedLLMClient:
    """Wrap an inner client with a SQLite-backed cache."""

    def __init__(
        self,
        inner: _BaseClient,
        store: Any,
        *,
        cacheable_kinds: Iterable[tuple[str, str]] = _CACHEABLE_PREFIXES_DEFAULT,
        ttl_seconds: int = 7 * 24 * 3600,
    ) -> None:
        self._inner = inner
        self._store = store
        self._kinds = tuple(cacheable_kinds)
        self._ttl_seconds = ttl_seconds
        self.hits = 0
        self.misses = 0

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
    ) -> str:
        kind = self._classify(messages)
        if kind is None:
            return self._inner.chat(model=model, messages=messages, temperature=temperature)
        key = self._make_key(model, messages, temperature)
        cached = self._store.cache_get(key)
        if cached is not None:
            self.hits += 1
            return cached
        response = self._inner.chat(model=model, messages=messages, temperature=temperature)
        try:
            self._store.cache_put(
                key,
                response,
                model=model,
                kind=kind,
                ttl_seconds=self._ttl_seconds or None,
            )
        except Exception:
            # Cache failures must never break the agent.
            pass
        self.misses += 1
        return response

    def _classify(self, messages: list[dict[str, str]]) -> str | None:
        if not messages:
            return None
        system = str(messages[0].get("content", ""))
        for prefix, kind in self._kinds:
            if prefix in system:
                return kind
        return None

    @staticmethod
    def _make_key(model: str, messages: list[dict[str, str]], temperature: float) -> str:
        canonical = {
            "model": model,
            "temperature": round(float(temperature), 4),
            "messages": [
                {"role": str(m.get("role", "")), "content": str(m.get("content", ""))}
                for m in messages
            ],
        }
        encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return "llm:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()
