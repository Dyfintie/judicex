from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .agent_runtime import JudicexAgentRuntime
from .llm_provider import make_client, resolve_settings
from .llm_cache import CachedLLMClient
from .store import LegalMemoryStore


SKILL_MAP = {
    "lavoro": "diritto_lavoro.md",
    "civile": "diritto_civile.md",
    "costituzionale": "diritto_costituzionale.md",
}


class OllamaClient:
    """HTTP client for Ollama / OpenAI-compatible /api/chat endpoints.

    Retries automatically on transient server errors (HTTP 5xx and connection
    failures) with exponential backoff, so a single overloaded reply does
    not cascade into a cold abstain through the whole agent loop.
    """

    _RETRY_STATUSES: tuple[int, ...] = (429, 500, 502, 503, 504)

    def __init__(
        self,
        host: str = "http://127.0.0.1:11434",
        timeout: int = 600,
        stream: bool = False,
        on_chunk: "Callable[[str], None] | None" = None,
        max_retries: int = 3,
        retry_backoff_seconds: float = 1.5,
    ) -> None:
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.stream = stream
        self.on_chunk = on_chunk
        self.max_retries = max(0, int(max_retries))
        self.retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))

    def chat(self, model: str, messages: list[dict[str, Any]], temperature: float = 0.0) -> str:
        payload = {
            "model": model,
            "messages": messages,
            "stream": self.stream,
            "options": {"temperature": temperature},
        }
        attempts = self.max_retries + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                return self._do_chat(payload)
            except RuntimeError as exc:
                last_error = exc
                message = str(exc)
                retryable = any(
                    f"HTTP error {code}" in message for code in self._RETRY_STATUSES
                ) or "Cannot reach Ollama" in message
                if not retryable or attempt == attempts - 1:
                    raise
                _backoff_sleep(self.retry_backoff_seconds, attempt)
        if last_error is not None:
            raise last_error
        raise RuntimeError("ollama chat failed without raising — unreachable")

    def _do_chat(self, payload: dict[str, Any]) -> str:
        request = Request(
            f"{self.host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                if not self.stream:
                    body = json.loads(response.read().decode("utf-8"))
                    try:
                        return body["message"]["content"]
                    except KeyError as exc:
                        raise RuntimeError(f"Unexpected Ollama response: {body}") from exc
                parts: list[str] = []
                for raw_line in response:
                    if not raw_line:
                        continue
                    try:
                        chunk = json.loads(raw_line.decode("utf-8"))
                    except json.JSONDecodeError:
                        continue
                    token = (chunk.get("message") or {}).get("content", "")
                    if token:
                        parts.append(token)
                        if self.on_chunk is not None:
                            try:
                                self.on_chunk(token)
                            except Exception:
                                pass
                    if chunk.get("done"):
                        break
                return "".join(parts)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Ollama HTTP error {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(
                f"Cannot reach Ollama at {self.host}. Start 'ollama serve' and ensure a model is available."
            ) from exc


def _backoff_sleep(base: float, attempt: int) -> None:
    import time

    delay = base * (2 ** attempt)
    time.sleep(min(delay, 30.0))


def _skill_path(area: str | None) -> Path | None:
    if not area:
        return None
    name = SKILL_MAP.get(area.lower(), area)
    candidate = Path(__file__).resolve().parent / "skills" / name
    if candidate.exists():
        return candidate
    return None


def ask_once(
    *,
    db_path: str,
    model: str,
    question: str,
    area: str | None,
    host: str,
    provider: str = "",
    base_url: str = "",
    matter_id: str | None = None,
    recent_user_turns: list[str] | None = None,
    cache_enabled: bool = True,
) -> dict[str, object]:
    with LegalMemoryStore(db_path) as store:
        settings = resolve_settings(
            store,
            default_model=model,
            ollama_host=host,
            overrides={"provider": provider, "model": model, "base_url": base_url},
        )
        base_client = make_client(settings)
        client: object = CachedLLMClient(base_client, store) if cache_enabled else base_client
        engine = JudicexAgentRuntime(store=store, client=client, model=settings["model"], area=area, matter_id=matter_id)
        return engine.answer(question, recent_user_turns=recent_user_turns or [])


def _print_pending_trace() -> None:
    print("judicex agente:")
    for title, detail in (
        ("Pianifico lavoro", "scelgo quali tool interni usare"),
        ("Tool disponibili", "memoria, fonti, fascicolo, bozze e motore legale"),
    ):
        print(f"  - {title}: {detail}")


def _print_agent_trace(result: dict[str, object]) -> None:
    trace = result.get("agent_trace")
    if not isinstance(trace, list) or not trace:
        return
    print("percorso agente:")
    for item in trace:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "passaggio")
        status = str(item.get("status") or "unknown")
        detail = str(item.get("detail") or "").strip()
        suffix = f" - {detail}" if detail else ""
        print(f"  - {title} [{status}]{suffix}")


def run_chat_session(
    *,
    db_path: str,
    model: str,
    area: str | None,
    host: str,
    provider: str = "",
    base_url: str = "",
    matter_id: str | None = None,
) -> None:
    recent_user_turns: list[str] = []

    def _tick(_token: str) -> None:
        return None

    with LegalMemoryStore(db_path) as store:
        settings = resolve_settings(
            store,
            default_model=model,
            ollama_host=host,
            overrides={"provider": provider, "model": model, "base_url": base_url},
        )
        client = make_client(settings)
        if hasattr(client, "stream"):
            client.stream = True
            client.on_chunk = _tick
        engine = JudicexAgentRuntime(store=store, client=client, model=settings["model"], area=area, matter_id=matter_id)
        print("Judicex terminal chat. Comandi: /exit /areas /health /matter /reset")
        print(f"provider AI: {settings['provider_label']} / {settings['model'] or 'nessun modello'}")
        if matter_id:
            matter = store.get_matter(matter_id)
            if matter:
                print(f"fascicolo attivo: {matter['title']} ({matter['id']})")
            else:
                print(f"fascicolo non trovato: {matter_id}")
        while True:
            try:
                user_text = input("tu> ").strip()
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print()
                break
            if not user_text:
                continue
            if user_text in {"/exit", "exit", "quit"}:
                break
            if user_text == "/reset":
                recent_user_turns.clear()
                print("cronologia utente azzerata")
                continue
            if user_text == "/areas":
                print(json.dumps({"areas": store.list_areas()}, ensure_ascii=False, indent=2))
                continue
            if user_text == "/health":
                print(json.dumps(store.health(), ensure_ascii=False, indent=2))
                continue
            if user_text == "/matter":
                if not matter_id:
                    print(json.dumps({"matter": None}, ensure_ascii=False, indent=2))
                else:
                    print(json.dumps(store.build_matter_context(matter_id), ensure_ascii=False, indent=2))
                continue

            _print_pending_trace()
            result = engine.answer(user_text, recent_user_turns=recent_user_turns)
            _print_agent_trace(result)
            print(f"judicex[{result['status']}]> {result['answer']}")
            citations = result.get("citations", [])
            if citations:
                print("fonti:")
                for citation in citations:
                    print(f"[{citation['index']}] {citation['title']} - {citation['source_ref']}")
            follow_ups = result.get("follow_up_questions", [])
            if follow_ups:
                print("integrazioni richieste:", "; ".join(str(item) for item in follow_ups))
            recent_user_turns.append(user_text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Judicex terminal agent.")
    parser.add_argument("--db", required=True, help="Path to the Legal Memory SQLite database.")
    parser.add_argument("--model", default="", help="Model name. If omitted, Judicex uses the configured provider default.")
    parser.add_argument("--provider", default="", help="LLM provider: ollama, openai, anthropic, openai_compatible, none.")
    parser.add_argument("--area", help="Optional legal area, for example lavoro.")
    parser.add_argument("--matter-id", help="Optional private matter id to use as case memory.")
    parser.add_argument("--host", default="http://127.0.0.1:11434", help="Legacy Ollama base URL.")
    parser.add_argument("--base-url", default="", help="Provider base URL override.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    run_chat_session(
        db_path=args.db,
        model=args.model,
        area=args.area,
        matter_id=args.matter_id,
        host=args.host,
        provider=args.provider,
        base_url=args.base_url,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
