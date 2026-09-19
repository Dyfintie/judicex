from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .store import LegalMemoryStore
from .tools import LegalMemoryTools


SERVER_INFO = {"name": "judicex-memory-os", "version": "0.2.0"}
PROTOCOL_VERSION = "2024-11-05"


def _read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        decoded = line.decode("utf-8").strip()
        if not decoded:
            break
        key, value = decoded.split(":", 1)
        headers[key.lower()] = value.strip()
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    body = sys.stdin.buffer.read(length)
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def _write_message(payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(encoded)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def _response(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


class JudicexMCPServer:
    def __init__(self, db_path: str) -> None:
        self.store = LegalMemoryStore(db_path)
        self.tools = LegalMemoryTools(self.store)

    def close(self) -> None:
        self.store.close()

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        request_id = message.get("id")
        method = message.get("method")
        params = message.get("params", {})

        if method == "notifications/initialized":
            return None

        if method == "initialize":
            return _response(
                request_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": SERVER_INFO,
                },
            )

        if method == "ping":
            return _response(request_id, {})

        if method == "tools/list":
            return _response(request_id, {"tools": self.tools.definitions()})

        if method == "tools/call":
            try:
                name = params["name"]
            except KeyError:
                return _error(request_id, -32602, "missing tool name")
            arguments = params.get("arguments") or {}
            try:
                result = self.tools.call(name, arguments)
            except Exception as exc:
                return _response(
                    request_id,
                    {
                        "content": [{"type": "text", "text": f"Tool error: {exc}"}],
                        "isError": True,
                    },
                )
            return _response(
                request_id,
                {
                    "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
                    "isError": False,
                },
            )

        return _error(request_id, -32601, f"method not found: {method}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Judicex MCP stdio server.")
    parser.add_argument("--db", required=True, help="Path to the Legal Memory SQLite database.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    server = JudicexMCPServer(db_path=args.db)
    try:
        while True:
            message = _read_message()
            if message is None:
                break
            response = server.handle(message)
            if response is not None:
                _write_message(response)
    finally:
        server.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
