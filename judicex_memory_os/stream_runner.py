"""Server-sent-events generator for the agent trace.

The Flask endpoint hands off to `stream_answer()`, which:

1. Spawns a worker thread that opens its own SQLite connection (so SQLite's
   thread-local cursors stay safe) and runs `JudicexAgentRuntime.answer(...)`.
   The runtime publishes real tool steps through a callback.
2. Polls the trace from the request thread on a short interval and emits a
   `step` SSE event for every new entry.
3. When the worker thread terminates, drains any remaining steps, emits a
   single `result` event with the rendered payload, and closes the stream.
4. On any exception the generator emits an `error` event before closing.

The wire format is the standard:

    event: step
    data: {"id": "analyse_request", "status": "completed", ...}

    event: result
    data: {"status": "grounded", ...}

    event: done
    data: {}
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from typing import Any, Iterator

from .agent_runtime import JudicexAgentRuntime
from .llm_provider import make_client, resolve_settings
from .llm_cache import CachedLLMClient
from .store import LegalMemoryStore


_POLL_INTERVAL_SEC = 0.15
_MAX_RUNTIME_SEC = 600


def stream_answer(
    *,
    db_path: str,
    question: str,
    model: str = "",
    host: str = "",
    provider: str = "",
    base_url: str = "",
    area: str | None = None,
    matter_id: str | None = None,
    recent_user_turns: list[str] | None = None,
    cache_enabled: bool = True,
) -> Iterator[bytes]:
    """Yield SSE chunks for one engine.answer() call."""

    state: dict[str, Any] = {
        "trace": [],
        "result": None,
        "error": None,
        "finished": False,
    }
    state_lock = threading.Lock()

    def worker() -> None:
        try:
            store = LegalMemoryStore(db_path)
            try:
                settings = resolve_settings(
                    store,
                    default_model=model,
                    ollama_host=host,
                    overrides={
                        "provider": provider,
                        "model": model,
                        "base_url": base_url,
                    },
                )
                base_client = make_client(settings)
                client: object = (
                    CachedLLMClient(base_client, store) if cache_enabled else base_client
                )
                def publish_step(step: dict[str, Any]) -> None:
                    with state_lock:
                        state["trace"].append(step)

                engine = JudicexAgentRuntime(
                    store=store,
                    client=client,
                    model=settings["model"],
                    area=area,
                    matter_id=matter_id,
                    on_step=publish_step,
                )
                result = engine.answer(
                    question,
                    recent_user_turns=recent_user_turns or [],
                )
                with state_lock:
                    final_trace = result.get("agent_trace") or []
                    if len(final_trace) > len(state["trace"]):
                        state["trace"] = list(final_trace)
                    state["result"] = result
            finally:
                store.close()
        except Exception as exc:
            with state_lock:
                state["error"] = {
                    "message": str(exc),
                    "traceback": traceback.format_exc(limit=8),
                }
        finally:
            with state_lock:
                state["finished"] = True

    thread = threading.Thread(target=worker, name="judicex-stream", daemon=True)
    thread.start()

    deadline = time.monotonic() + _MAX_RUNTIME_SEC
    emitted = 0
    while True:
        if time.monotonic() > deadline:
            with state_lock:
                state["error"] = state["error"] or {
                    "message": f"engine exceeded {_MAX_RUNTIME_SEC}s deadline",
                    "traceback": "",
                }
                state["finished"] = True
        with state_lock:
            trace_snapshot = list(state["trace"])
            finished = state["finished"]
            error = state["error"]
            result = state["result"]

        while emitted < len(trace_snapshot):
            yield _sse("step", trace_snapshot[emitted])
            emitted += 1

        if finished:
            if error is not None:
                yield _sse("error", error)
            elif result is not None:
                yield _sse("result", result)
            yield _sse("done", {})
            return

        time.sleep(_POLL_INTERVAL_SEC)


# ---------------------------------------------------------------------------
# SSE wire format
# ---------------------------------------------------------------------------


def _sse(event: str, data: Any) -> bytes:
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    chunk = f"event: {event}\ndata: {body}\n\n"
    return chunk.encode("utf-8")
