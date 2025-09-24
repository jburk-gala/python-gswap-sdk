"""Global management of the bundler event socket."""
from __future__ import annotations

import threading
from typing import Optional

from .errors import GSwapSDKError
from .event_socket_client import EventSocketClient, TradeEventEmitter
from .tx_waiter import TransactionWaiter


class Events:
    trade_event_emitter_constructor = EventSocketClient
    instance: "Events"

    def __init__(self) -> None:
        self._global_socket_client: Optional[TradeEventEmitter] = None
        self._global_wait_helper = TransactionWaiter()
        self._connection_lock = threading.RLock()
        self._transaction_listener = None

    def connect_event_socket(self, bundler_base_url: Optional[str] = None) -> TradeEventEmitter:
        with self._connection_lock:
            if self._global_socket_client and self._global_socket_client.is_connected():
                return self._global_socket_client

            url = bundler_base_url or "https://bundle-backend-prod1.defi.gala.com"
            client = self.trade_event_emitter_constructor(url)
            client.connect()

            self._transaction_listener = lambda tx_id, response: self._handle_socket_message(
                tx_id, response
            )
            client.on("transaction", self._transaction_listener)

            self._global_socket_client = client
            self._global_wait_helper.set_enabled(True)

            return client

    def disconnect_event_socket(self) -> None:
        with self._connection_lock:
            client = self._global_socket_client
            if not client:
                return
            if self._transaction_listener is not None:
                client.off("transaction", self._transaction_listener)
                self._transaction_listener = None
            client.disconnect()
            self._global_socket_client = None
            self._global_wait_helper.set_enabled(False)

    def event_socket_connected(self) -> bool:
        client = self._global_socket_client
        return bool(client and client.is_connected())

    def register_tx_id(self, tx_id: str, timeout_ms: int) -> None:
        self._global_wait_helper.register_tx_id(tx_id, timeout_ms)

    def wait(self, tx_id: str) -> dict:
        if not self.event_socket_connected():
            raise GSwapSDKError.socket_connection_required_error()
        return self._global_wait_helper.wait(tx_id)

    def _handle_socket_message(self, tx_id: str, response: dict) -> None:
        status = response.get("status")
        data = response.get("data") or {}
        if status == "PROCESSED":
            self._global_wait_helper.notify_success(tx_id, data)
        elif status == "FAILED":
            self._global_wait_helper.notify_failure(tx_id, data)


Events.instance = Events()

