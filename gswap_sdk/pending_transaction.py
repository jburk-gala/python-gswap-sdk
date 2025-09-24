"""Representation of a pending transaction returned by bundler operations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict


WaitResult = Dict[str, object]
WaitDelegate = Callable[[], WaitResult]


@dataclass(slots=True)
class PendingTransaction:
    transaction_id: str
    message: str
    error: bool
    _wait_delegate: WaitDelegate

    def wait(self) -> WaitResult:
        """Block until the transaction is processed by the bundler."""

        return self._wait_delegate()

