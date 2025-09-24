"""Socket client used for streaming bundler events."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, DefaultDict, List, Optional

try:  # pragma: no cover - optional dependency
    import socketio
except Exception:  # pragma: no cover - optional dependency
    socketio = None  # type: ignore[assignment]


EventCallback = Callable[..., None]


class TradeEventEmitter:
    def __init__(self) -> None:
        self._listeners: DefaultDict[str, List[EventCallback]] = defaultdict(list)

    def on(self, event: str, callback: EventCallback) -> None:
        self._listeners[event].append(callback)

    def off(self, event: str, callback: EventCallback) -> None:
        listeners = self._listeners.get(event)
        if not listeners:
            return
        try:
            listeners.remove(callback)
        except ValueError:  # pragma: no cover - defensive
            return

    def emit(self, event: str, *args: Any) -> None:
        for callback in list(self._listeners.get(event, [])):
            callback(*args)

    def connect(self) -> None:  # pragma: no cover - interface placeholder
        raise NotImplementedError

    def disconnect(self) -> None:  # pragma: no cover - interface placeholder
        raise NotImplementedError

    def is_connected(self) -> bool:  # pragma: no cover - interface placeholder
        raise NotImplementedError


class EventSocketClient(TradeEventEmitter):
    def __init__(self, bundler_url: str) -> None:
        super().__init__()
        self._bundler_url = bundler_url
        self._socket: Optional[socketio.Client] = None  # type: ignore[assignment]

    def connect(self) -> None:
        if socketio is None:
            raise RuntimeError(
                "python-socketio is required for socket connections. "
                "Install it with `pip install python-socketio`."
            )

        if self._socket and self._socket.connected:
            return

        client = socketio.Client(transports=["websocket"], logger=False, engineio_logger=False)

        client.on("connect", lambda: self.emit("connect"))
        client.on("disconnect", lambda reason: self.emit("disconnect", reason))

        def handle_error(error: Any) -> None:
            self.emit("error", error)

        client.on("connect_error", handle_error)

        @client.on("*")  # type: ignore[misc]
        def handle_any(event: str, data: Any) -> None:
            if isinstance(data, dict):
                payload = dict(data)
            else:
                payload = {"data": data}
            transaction_hash = payload.get("data", {}).get("transactionId")
            payload.setdefault("transactionHash", transaction_hash)
            self.emit("transaction", event, payload)

        client.connect(self._bundler_url)

        self._socket = client

    def disconnect(self) -> None:
        if self._socket is not None:
            self._socket.disconnect()
            self._socket = None

    def is_connected(self) -> bool:
        return bool(self._socket and self._socket.connected)

