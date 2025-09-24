"""Utilities for waiting on bundler transaction results."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Dict, Optional

from .errors import GSwapSDKError


@dataclass
class _PromiseInfo:
    event: threading.Event = field(default_factory=threading.Event)
    waited: bool = False
    result: Optional[dict] = None
    error: Optional[GSwapSDKError] = None
    timer: Optional[threading.Timer] = None


class TransactionWaiter:
    def __init__(self) -> None:
        self._enabled = False
        self._lock = threading.RLock()
        self._promises: Dict[str, _PromiseInfo] = {}

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = enabled
            if not enabled:
                for tx_id, info in list(self._promises.items()):
                    if info.timer:
                        info.timer.cancel()
                    info.error = GSwapSDKError.transaction_wait_failed_error(
                        tx_id, {"message": "Transaction waiter disabled"}
                    )
                    info.event.set()
                self._promises.clear()

    def register_tx_id(self, tx_id: str, timeout_ms: int) -> None:
        with self._lock:
            if tx_id in self._promises:
                raise GSwapSDKError(
                    "Transaction ID is already registered",
                    "TRANSACTION_ID_ALREADY_REGISTERED",
                    {"txId": tx_id},
                )

            if not self._enabled:
                return

            info = _PromiseInfo()

            def on_timeout() -> None:
                with self._lock:
                    stored = self._promises.pop(tx_id, None)
                if stored is None:
                    return
                if stored.waited:
                    stored.error = GSwapSDKError.transaction_wait_timeout_error(tx_id)
                else:
                    stored.result = {"txId": tx_id, "transactionHash": tx_id, "Data": {}}
                stored.event.set()

            timer = threading.Timer(timeout_ms / 1000, on_timeout)
            info.timer = timer
            self._promises[tx_id] = info
            timer.start()

    def wait(self, tx_id: str) -> dict:
        with self._lock:
            info = self._promises.get(tx_id)
            if info is None:
                raise GSwapSDKError(
                    "Transaction ID is not registered for waiting",
                    "TRANSACTION_ID_NOT_REGISTERED",
                    {"txId": tx_id},
                )
            info.waited = True
            event = info.event

        event.wait()

        if info.timer:
            info.timer.cancel()

        if info.error:
            raise info.error
        if info.result is None:
            raise GSwapSDKError(
                "Transaction wait completed without a result",
                "TRANSACTION_WAIT_NO_RESULT",
                {"txId": tx_id},
            )
        return info.result

    def notify_success(self, tx_id: str, data: dict) -> None:
        with self._lock:
            info = self._promises.pop(tx_id, None)
        if info is None:
            return
        if info.timer:
            info.timer.cancel()
        info.result = {
            "txId": tx_id,
            "transactionHash": data.get("transactionId", tx_id),
            "Data": data.get("Data", {}),
        }
        info.event.set()

    def notify_failure(self, tx_id: str, detail: dict) -> None:
        with self._lock:
            info = self._promises.pop(tx_id, None)
        if info is None:
            return
        if info.timer:
            info.timer.cancel()
        if info.waited:
            info.error = GSwapSDKError.transaction_wait_failed_error(tx_id, detail)
        else:
            info.result = {"txId": tx_id, "transactionHash": tx_id, "Data": {}}
        info.event.set()

