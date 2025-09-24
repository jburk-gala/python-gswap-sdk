"""Signer interfaces used by the SDK."""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Dict, Protocol

from .errors import GSwapSDKError


class GalaChainSigner(Protocol):
    def sign_object(self, method_name: str, obj: Dict[str, object]) -> Dict[str, object]:
        ...


@dataclass
class PrivateKeySigner(GalaChainSigner):
    private_key: str

    def __post_init__(self) -> None:
        key = self.private_key[2:] if self.private_key.startswith("0x") else self.private_key
        try:
            self._key_bytes = bytes.fromhex(key)
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError("Private key must be a hexadecimal string") from exc

    def sign_object(self, method_name: str, obj: Dict[str, object]) -> Dict[str, object]:
        payload = dict(obj)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        signature = hmac.new(self._key_bytes, canonical, hashlib.sha256).hexdigest()
        payload["signature"] = signature
        return payload


@dataclass
class GalaWalletSigner(GalaChainSigner):
    wallet_address: str

    def sign_object(self, method_name: str, obj: Dict[str, object]) -> Dict[str, object]:  # pragma: no cover - environment
        raise GSwapSDKError(
            "Gala wallet signing is not available in the Python SDK environment.",
            "GALA_WALLET_NOT_AVAILABLE",
        )

