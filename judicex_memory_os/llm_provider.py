from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SETTINGS_KEY = "llm"

PROVIDERS: dict[str, dict[str, str]] = {
    "ollama": {
        "label": "Ollama locale",
        "default_model": "qwen2.5:7b",
        "default_base_url": "http://127.0.0.1:11434",
        "api_key_env": "",
        "kind": "ollama",
        "model_options": "qwen2.5:7b,glm-5:cloud,llama3.1:8b,mistral:7b,gemma3:4b,deepseek-r1:8b",
    },
    "openai": {
        "label": "OpenAI",
        "default_model": "gpt-4.1-mini",
        "default_base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "kind": "openai",
        "model_options": "gpt-4.1-mini,gpt-4.1,gpt-4o-mini,gpt-4o",
    },
    "anthropic": {
        "label": "Claude / Anthropic",
        "default_model": "claude-3-5-sonnet-latest",
        "default_base_url": "https://api.anthropic.com/v1",
        "api_key_env": "ANTHROPIC_API_KEY",
        "kind": "anthropic",
        "model_options": "claude-3-5-sonnet-latest,claude-3-5-haiku-latest,claude-3-opus-latest",
    },
    "openai_compatible": {
        "label": "OpenAI compatibile",
        "default_model": "local-model",
        "default_base_url": "http://127.0.0.1:8000/v1",
        "api_key_env": "OPENAI_COMPATIBLE_API_KEY",
        "kind": "openai",
        "model_options": "local-model,qwen2.5:7b,llama3.1:8b",
    },
    "none": {
        "label": "Nessun LLM",
        "default_model": "",
        "default_base_url": "",
        "api_key_env": "",
        "kind": "none",
        "model_options": "",
    },
}


def load_dotenv(path: str | Path = ".env") -> None:
    """Load a minimal .env file without adding a runtime dependency."""

    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


def default_settings(*, default_model: str = "", ollama_host: str = "") -> dict[str, Any]:
    load_dotenv()
    provider = os.getenv("JUDICEX_LLM_PROVIDER", "ollama").strip() or "ollama"
    if provider not in PROVIDERS:
        provider = "ollama"
    return {
        "provider": provider,
        "models": {
            "ollama": os.getenv("OLLAMA_MODEL") or default_model or PROVIDERS["ollama"]["default_model"],
            "openai": os.getenv("OPENAI_MODEL") or PROVIDERS["openai"]["default_model"],
            "anthropic": os.getenv("ANTHROPIC_MODEL") or PROVIDERS["anthropic"]["default_model"],
            "openai_compatible": os.getenv("OPENAI_COMPATIBLE_MODEL") or PROVIDERS["openai_compatible"]["default_model"],
            "none": "",
        },
        "base_urls": {
            "ollama": os.getenv("OLLAMA_HOST") or ollama_host or PROVIDERS["ollama"]["default_base_url"],
            "openai": os.getenv("OPENAI_BASE_URL") or PROVIDERS["openai"]["default_base_url"],
            "anthropic": os.getenv("ANTHROPIC_BASE_URL") or PROVIDERS["anthropic"]["default_base_url"],
            "openai_compatible": os.getenv("OPENAI_COMPATIBLE_BASE_URL") or PROVIDERS["openai_compatible"]["default_base_url"],
            "none": "",
        },
        "temperature": float(os.getenv("JUDICEX_LLM_TEMPERATURE", "0") or 0),
    }


def merge_settings(
    stored: dict[str, Any] | None,
    *,
    default_model: str = "",
    ollama_host: str = "",
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = default_settings(default_model=default_model, ollama_host=ollama_host)
    if stored:
        if str(stored.get("provider") or "") in PROVIDERS:
            settings["provider"] = stored["provider"]
        for section in ("models", "base_urls"):
            values = stored.get(section)
            if isinstance(values, dict):
                settings[section].update({str(k): str(v) for k, v in values.items()})
        if "temperature" in stored:
            settings["temperature"] = _safe_float(stored.get("temperature"), default=0.0)
    if overrides:
        for section in ("models", "base_urls"):
            values = overrides.get(section)
            if isinstance(values, dict):
                settings[section].update({str(k): str(v) for k, v in values.items()})
        provider = str(overrides.get("provider") or "").strip()
        if provider in PROVIDERS:
            settings["provider"] = provider
        model = str(overrides.get("model") or "").strip()
        if model:
            settings["models"][settings["provider"]] = model
        base_url = str(overrides.get("base_url") or "").strip()
        if base_url:
            settings["base_urls"][settings["provider"]] = base_url
        if "temperature" in overrides:
            settings["temperature"] = _safe_float(overrides.get("temperature"), default=settings["temperature"])
    return normalize_settings(settings)


def normalize_settings(settings: dict[str, Any]) -> dict[str, Any]:
    provider = str(settings.get("provider") or "ollama").strip()
    if provider not in PROVIDERS:
        provider = "ollama"
    settings["provider"] = provider
    settings.setdefault("models", {})
    settings.setdefault("base_urls", {})
    settings["model"] = str(settings["models"].get(provider) or PROVIDERS[provider]["default_model"])
    settings["base_url"] = str(settings["base_urls"].get(provider) or PROVIDERS[provider]["default_base_url"]).rstrip("/")
    env_name = PROVIDERS[provider]["api_key_env"]
    settings["api_key_env"] = env_name
    settings["api_key_present"] = bool(os.getenv(env_name)) if env_name else provider in {"ollama", "none"}
    settings["provider_label"] = PROVIDERS[provider]["label"]
    settings["providers"] = public_providers()
    return settings


def public_settings(settings: dict[str, Any]) -> dict[str, Any]:
    public = {
        "provider": settings["provider"],
        "provider_label": settings["provider_label"],
        "model": settings["model"],
        "base_url": settings["base_url"],
        "models": settings.get("models", {}),
        "base_urls": settings.get("base_urls", {}),
        "temperature": settings.get("temperature", 0),
        "api_key_env": settings.get("api_key_env", ""),
        "api_key_present": settings.get("api_key_present", False),
        "providers": public_providers(),
    }
    return public


def public_providers() -> list[dict[str, Any]]:
    return [
        {
            "id": provider_id,
            "label": data["label"],
            "default_model": data["default_model"],
            "default_base_url": data["default_base_url"],
            "api_key_env": data["api_key_env"],
            "model_options": [item for item in data.get("model_options", "").split(",") if item],
        }
        for provider_id, data in PROVIDERS.items()
    ]


def default_model_options(provider_id: str) -> list[str]:
    provider = PROVIDERS.get(provider_id)
    if not provider:
        return []
    return [item for item in provider.get("model_options", "").split(",") if item]


def list_provider_models(settings: dict[str, Any], *, timeout: int = 5) -> dict[str, Any]:
    provider = settings["provider"]
    if provider == "none":
        return {"status": "ok", "source": "none", "models": []}
    if provider != "ollama":
        return {"status": "ok", "source": "static", "models": default_model_options(provider)}

    url = f"{settings['base_url'].rstrip('/')}/api/tags"
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return {
            "status": "error",
            "source": "ollama",
            "models": default_model_options("ollama"),
            "message": f"Ollama non raggiungibile: {exc}",
        }
    models = []
    for item in payload.get("models", []):
        if isinstance(item, dict) and item.get("name"):
            models.append(str(item["name"]))
    return {"status": "ok", "source": "ollama", "models": models or default_model_options("ollama")}


def save_settings(store: Any, payload: dict[str, Any], *, default_model: str = "", ollama_host: str = "") -> dict[str, Any]:
    current = merge_settings(store.get_app_setting(SETTINGS_KEY), default_model=default_model, ollama_host=ollama_host)
    next_settings = merge_settings(current, default_model=default_model, ollama_host=ollama_host, overrides=payload)
    stored = {
        "provider": next_settings["provider"],
        "models": next_settings["models"],
        "base_urls": next_settings["base_urls"],
        "temperature": next_settings.get("temperature", 0),
    }
    store.set_app_setting(SETTINGS_KEY, stored)
    return next_settings


def resolve_settings(store: Any, *, default_model: str = "", ollama_host: str = "", overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    return merge_settings(
        store.get_app_setting(SETTINGS_KEY),
        default_model=default_model,
        ollama_host=ollama_host,
        overrides=overrides,
    )


def make_client(settings: dict[str, Any]) -> Any:
    provider = settings["provider"]
    if provider == "ollama":
        from .ollama_agent import OllamaClient

        return OllamaClient(host=settings["base_url"])
    if provider in {"openai", "openai_compatible"}:
        return OpenAICompatibleClient(
            base_url=settings["base_url"],
            api_key=_api_key(settings),
            provider_label=settings["provider_label"],
            api_key_required=provider == "openai",
        )
    if provider == "anthropic":
        return AnthropicClient(base_url=settings["base_url"], api_key=_api_key(settings))
    return NoLLMClient()


def test_provider(settings: dict[str, Any]) -> dict[str, Any]:
    if settings["provider"] == "none":
        return {"status": "ok", "message": "LLM disattivato. Le funzioni deterministiche restano disponibili."}
    client = make_client(settings)
    answer = client.chat(
        model=settings["model"],
        messages=[{"role": "user", "content": "Rispondi solo con: ok"}],
        temperature=0,
    )
    return {"status": "ok", "message": answer.strip()[:200] or "ok"}


class OpenAICompatibleClient:
    def __init__(self, *, base_url: str, api_key: str, provider_label: str, api_key_required: bool = True, timeout: int = 600) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.provider_label = provider_label
        self.api_key_required = api_key_required
        self.timeout = timeout

    def chat(self, model: str, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        if self.api_key_required and not self.api_key:
            raise RuntimeError(f"Configura {self.provider_label}: API key mancante.")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        body = _post_json(f"{self.base_url}/chat/completions", payload, headers=headers, timeout=self.timeout)
        try:
            return str(body["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Risposta inattesa da {self.provider_label}: {body}") from exc


class AnthropicClient:
    def __init__(self, *, base_url: str, api_key: str, timeout: int = 600) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def chat(self, model: str, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        if not self.api_key:
            raise RuntimeError("Configura Claude/Anthropic: API key mancante.")
        system_parts: list[str] = []
        user_messages: list[dict[str, str]] = []
        for message in messages:
            role = str(message.get("role") or "user")
            content = str(message.get("content") or "")
            if role == "system":
                system_parts.append(content)
            else:
                user_messages.append({"role": "assistant" if role == "assistant" else "user", "content": content})
        payload: dict[str, Any] = {
            "model": model,
            "messages": user_messages or [{"role": "user", "content": ""}],
            "temperature": temperature,
            "max_tokens": 4096,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        body = _post_json(
            f"{self.base_url}/messages",
            payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            timeout=self.timeout,
        )
        try:
            parts = body["content"]
            return "".join(str(part.get("text") or "") for part in parts if part.get("type") == "text")
        except (KeyError, TypeError) as exc:
            raise RuntimeError(f"Risposta inattesa da Claude/Anthropic: {body}") from exc


class NoLLMClient:
    def chat(self, model: str, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        raise RuntimeError("Provider LLM disattivato nelle impostazioni.")


def _post_json(url: str, payload: dict[str, Any], *, headers: dict[str, str], timeout: int) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"LLM HTTP error {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Provider LLM non raggiungibile: {exc}") from exc


def _api_key(settings: dict[str, Any]) -> str:
    env_name = str(settings.get("api_key_env") or "")
    return os.getenv(env_name, "") if env_name else ""


def _safe_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
