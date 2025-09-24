"""Custom exceptions for the gSwap Python SDK."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping, Optional


@dataclass(eq=False)
class GSwapSDKError(Exception):
    """Base exception raised by the gSwap SDK."""

    message: str
    code: str
    details: Optional[Mapping[str, Any]] = None

    def __post_init__(self) -> None:
        super().__init__(self.message)

    @classmethod
    def no_signer_error(cls) -> "GSwapSDKError":
        return cls(
            "This method requires a signer. Please provide a signer to the GSwap constructor.",
            "NO_SIGNER",
        )

    @classmethod
    def incorrect_token_ordering_error(
        cls, specified_token0: Any, specified_token1: Any
    ) -> "GSwapSDKError":
        return cls(
            "Token ordering is incorrect. token0 should sort below token1.",
            "INCORRECT_TOKEN_ORDERING",
            {
                "specified_token0": specified_token0,
                "specified_token1": specified_token1,
            },
        )

    @classmethod
    def socket_connection_required_error(cls) -> "GSwapSDKError":
        return cls(
            "This method requires a socket connection. Did you call connect_socket()?",
            "SOCKET_CONNECTION_REQUIRED",
        )

    @classmethod
    def no_pool_available_error(
        cls, token_in: Any, token_out: Any, fee: Optional[int] = None
    ) -> "GSwapSDKError":
        if fee is not None:
            message = (
                "No pool available for the specified token pair at fee tier " f"{fee}"
            )
        else:
            message = "No pools available for the specified token pair"

        return cls(
            message,
            "NO_POOL_AVAILABLE",
            {"token_in": token_in, "token_out": token_out, "fee": fee},
        )

    @classmethod
    def transaction_wait_timeout_error(cls, tx_id: str) -> "GSwapSDKError":
        return cls(
            "Transaction wait timed out.",
            "TRANSACTION_WAIT_TIMEOUT",
            {"tx_id": tx_id},
        )

    @classmethod
    def transaction_wait_failed_error(
        cls, tx_id: str, detail: Mapping[str, Any]
    ) -> "GSwapSDKError":
        transaction_hash = detail.get("transactionId")
        rest: MutableMapping[str, Any] = dict(detail)
        rest.pop("transactionId", None)
        return cls(
            "Transaction wait failed.",
            "TRANSACTION_WAIT_FAILED",
            {"tx_id": tx_id, "transaction_hash": transaction_hash, **rest},
        )

    @classmethod
    def from_http_response(
        cls, url: str, status: int, body: Any, error_key: Optional[str], message: Optional[str]
    ) -> "GSwapSDKError":
        if error_key and message:
            return cls(
                f"GalaChain Error {error_key} from {url}: {message}",
                error_key,
                {
                    "message": message,
                    "error_key": error_key,
                    "status": status,
                    "body": body,
                    "url": url,
                },
            )

        return cls(
            f"Unexpected HTTP Error {status} from {url}",
            "HTTP_ERROR",
            {"status": status, "body": body, "url": url},
        )
