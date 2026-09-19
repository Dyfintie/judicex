"""Optional at-rest encryption for matter (private) documents.

Activation rules:

1. If env var `JUDICEX_MATTER_KEY` is set, the value is treated as a
   url-safe base64-encoded 32-byte key (the standard Fernet format) and used
   directly for encryption/decryption. This is the recommended path for
   production: the key lives outside the SQLite file and can be rotated.

2. Otherwise, if `JUDICEX_MATTER_KEY_AUTO=1` is set, the module derives a
   stable key, persists it inside `llm_cache` under a reserved key and uses
   it. Convenient for local development / single-tenant prototypes.

3. Otherwise encryption is disabled. Writes go through as plaintext, and
   reads return content as-is. Existing rows remain readable.

Encrypted blobs carry a 4-byte magic prefix (`JX1\\n`) so the loader can
distinguish them from legacy plaintext rows. Decryption is therefore safe
to call on every read; if the marker is absent the input is returned
unchanged.

The `cryptography` package is imported lazily: if encryption is requested
but the package is not installed the call fails loudly rather than silently
falling back to plaintext.
"""

from __future__ import annotations

import os
from typing import Any


_MAGIC = "JX1\n"
_AUTO_KEY_CACHE_KEY = "judicex_matter_key_auto"


class CryptoUnavailable(RuntimeError):
    """Raised when encryption is requested but `cryptography` is not installed."""


class MatterCrypto:
    """Thin Fernet wrapper that no-ops when no key is configured."""

    def __init__(self, key: bytes | None) -> None:
        self._key = key
        self._fernet = None
        if key is not None:
            self._fernet = self._build_fernet(key)

    @property
    def enabled(self) -> bool:
        return self._fernet is not None

    @classmethod
    def from_store(cls, store: Any) -> "MatterCrypto":
        env_key = os.environ.get("JUDICEX_MATTER_KEY", "").strip()
        if env_key:
            return cls(env_key.encode("utf-8"))
        if os.environ.get("JUDICEX_MATTER_KEY_AUTO", "").strip() in {"1", "true", "yes"}:
            cached = store.cache_get(_AUTO_KEY_CACHE_KEY)
            if cached:
                return cls(cached.encode("utf-8"))
            new_key = cls._generate_key()
            try:
                store.cache_put(
                    _AUTO_KEY_CACHE_KEY,
                    new_key.decode("utf-8"),
                    model="matter_crypto",
                    kind="auto_key",
                    ttl_seconds=None,
                )
            except Exception:
                pass
            return cls(new_key)
        return cls(None)

    def encrypt(self, plaintext: str) -> str:
        if self._fernet is None:
            return plaintext
        token = self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")
        return _MAGIC + token

    def decrypt(self, ciphertext: str) -> str:
        if not ciphertext.startswith(_MAGIC):
            return ciphertext
        if self._fernet is None:
            raise CryptoUnavailable(
                "found encrypted matter content but no JUDICEX_MATTER_KEY is configured; "
                "set the key to read this row"
            )
        token = ciphertext[len(_MAGIC):].encode("utf-8")
        return self._fernet.decrypt(token).decode("utf-8")

    @staticmethod
    def _build_fernet(key: bytes) -> Any:
        try:
            from cryptography.fernet import Fernet
        except ImportError as exc:
            raise CryptoUnavailable(
                "cryptography package is required for matter at-rest encryption; "
                "install with `pip install 'cryptography>=42,<46'`"
            ) from exc
        return Fernet(key)

    @staticmethod
    def _generate_key() -> bytes:
        try:
            from cryptography.fernet import Fernet
        except ImportError as exc:
            raise CryptoUnavailable(
                "cryptography package is required to generate an auto key"
            ) from exc
        return Fernet.generate_key()


def is_encrypted(blob: str) -> bool:
    return isinstance(blob, str) and blob.startswith(_MAGIC)
