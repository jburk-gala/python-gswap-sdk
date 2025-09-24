"""Bundler interactions for write operations."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional

from .errors import GSwapSDKError
from .events import Events
from .http import HttpClient
from .pending_transaction import PendingTransaction
from .signers import GalaChainSigner


@dataclass(slots=True)
class Bundler:
    bundler_base_url: str
    bundling_api_base_path: str
    transaction_wait_timeout_ms: int
    signer: Optional[GalaChainSigner]
    http_client: HttpClient

    def __post_init__(self) -> None:
        self.bundler_base_url = self.bundler_base_url.rstrip("/")

    def sign_object(self, method_name: str, to_sign: Dict[str, object]) -> Dict[str, object]:
        if not self.signer:
            raise GSwapSDKError.no_signer_error()

        payload = dict(to_sign)
        payload.setdefault("uniqueKey", f"galaswap - operation - {uuid.uuid4()}")
        return self.signer.sign_object(method_name, payload)

    def send_bundler_request(
        self,
        method: str,
        body: Dict[str, object],
        strings_instructions: List[str],
    ) -> PendingTransaction:
        if not self.signer:
            raise GSwapSDKError.no_signer_error()

        request_body = {
            "method": method,
            "signedDto": self.sign_object(method, body),
            "stringsInstructions": strings_instructions,
        }

        response = self.http_client.send_post_request(
            self.bundler_base_url,
            self.bundling_api_base_path,
            "",
            request_body,
        )

        if not isinstance(response, dict):
            raise GSwapSDKError(
                "Invalid response from bundler",
                "INVALID_RESPONSE",
                {"payload": response},
            )

        tx_id = response.get("data")
        message = response.get("message", "")
        error = bool(response.get("error", False))
        if not isinstance(tx_id, str):
            raise GSwapSDKError(
                "Invalid bundler response: missing transaction id",
                "INVALID_RESPONSE",
                {"payload": response},
            )

        Events.instance.register_tx_id(tx_id, self.transaction_wait_timeout_ms)

        return PendingTransaction(
            transaction_id=tx_id,
            message=message,
            error=error,
            _wait_delegate=lambda: Events.instance.wait(tx_id),
        )

    def has_signer(self) -> bool:
        return self.signer is not None

