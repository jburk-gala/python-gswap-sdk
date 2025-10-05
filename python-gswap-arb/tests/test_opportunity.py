from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

import pytest

from gswap_arb.opportunity import (
    OpportunityFinder,
    OpportunityMetricsRecorder,
    OpportunityMonitor,
    TradingOpportunity,
)
from gswap_arb.quoting import HopQuote, PathQuoteResult


class _StubQuoteService:
    def __init__(self, results: Sequence[PathQuoteResult]) -> None:
        self._results = tuple(results)
        self.calls: list[Tuple[Sequence[Sequence[str]], Decimal]] = []

    def quote_paths(
        self,
        paths: Sequence[Sequence[str]],
        amount_in: Decimal,
        *,
        fee_overrides: Optional[object] = None,
    ) -> Tuple[PathQuoteResult, ...]:
        self.calls.append((paths, amount_in))
        return self._results


class _StubSwapClient:
    def __init__(self) -> None:
        self.calls: list[Tuple[str, str, int, dict]] = []

    def swap(self, token_in: str, token_out: str, fee: int, amount: dict) -> None:
        self.calls.append((token_in, token_out, fee, amount))


class _StubGSwap:
    def __init__(self) -> None:
        self.swaps = _StubSwapClient()


class _StubEventClient:
    def __init__(self) -> None:
        self.handlers: dict[str, List[Callable[..., None]]] = {}
        self.connected = False

    def on(self, event: str, callback: Callable[..., None]) -> None:
        self.handlers.setdefault(event, []).append(callback)

    def off(self, event: str, callback: Callable[..., None]) -> None:
        callbacks = self.handlers.get(event, [])
        if callback in callbacks:
            callbacks.remove(callback)

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def is_connected(self) -> bool:
        return self.connected

    def emit(self, event: str, *args) -> None:
        for callback in list(self.handlers.get(event, [])):
            callback(*args)


def _build_successful_path_result(
    path: Sequence[str],
    *,
    amount_in: str,
    amount_out: str,
) -> PathQuoteResult:
    hop = HopQuote(
        index=0,
        token_in=path[0],
        token_out=path[1],
        amount_in=Decimal(amount_in),
        amount_out=Decimal(amount_out),
        fee_tier=100,
        price_impact=Decimal("0.01"),
        current_sqrt_price=Decimal("1"),
        new_sqrt_price=Decimal("1.01"),
        attempts=1,
    )
    return PathQuoteResult(
        path=tuple(path),
        initial_amount=Decimal(amount_in),
        hops=(hop,),
        failures=tuple(),
        final_amount=Decimal(amount_out),
        cumulative_price_impact=Decimal("0.01"),
    )


def test_opportunity_finder_filters_by_profit(tmp_path: Path) -> None:
    profitable = _build_successful_path_result(("TOKEN_A", "TOKEN_B"), amount_in="100", amount_out="103")
    marginal = _build_successful_path_result(("TOKEN_A", "TOKEN_C"), amount_in="100", amount_out="100.5")

    metrics = OpportunityMetricsRecorder(jsonl_path=tmp_path / "metrics.jsonl")
    service = _StubQuoteService((profitable, marginal))

    finder = OpportunityFinder(
        service,
        min_absolute_profit=Decimal("2"),
        min_relative_profit=Decimal("0.01"),
        slippage_buffer=Decimal("0.005"),
        metrics=metrics,
    )

    opportunities = finder.evaluate_paths((("TOKEN_A", "TOKEN_B"), ("TOKEN_A", "TOKEN_C")), Decimal("100"))

    assert len(opportunities) == 1
    opportunity = opportunities[0]
    assert opportunity.path == ("TOKEN_A", "TOKEN_B")
    assert opportunity.net_profit == Decimal("103") * (Decimal("1") - Decimal("0.005")) - Decimal("100")

    # Ensure metrics were recorded for both paths.
    contents = (tmp_path / "metrics.jsonl").read_text().strip().splitlines()
    assert len(contents) == 2


def test_opportunity_monitor_executes_when_enabled() -> None:
    path_result = _build_successful_path_result(("A", "B"), amount_in="10", amount_out="11")
    service = _StubQuoteService((path_result,))
    finder = OpportunityFinder(service)
    client = _StubGSwap()

    monitor = OpportunityMonitor(
        finder,
        client,
        execution_enabled=True,
        slippage_guard=Decimal("0.02"),
    )

    opportunities = monitor.poll_once((("A", "B"),), Decimal("10"))

    assert len(opportunities) == 1
    swap_call = client.swaps.calls[0]
    assert swap_call[0] == "A"
    assert swap_call[1] == "B"
    assert swap_call[2] == 100
    assert swap_call[3]["exactIn"] == Decimal("10")
    assert swap_call[3]["amountOutMinimum"] == Decimal("11") * (Decimal("1") - Decimal("0.02"))


def test_opportunity_monitor_emits_alerts_when_execution_disabled() -> None:
    path_result = _build_successful_path_result(("A", "B"), amount_in="10", amount_out="11")
    service = _StubQuoteService((path_result,))
    finder = OpportunityFinder(service)
    client = _StubGSwap()

    captured: list[TradingOpportunity] = []

    monitor = OpportunityMonitor(
        finder,
        client,
        execution_enabled=False,
        alert_handler=captured.append,
    )

    opportunities = monitor.poll_once((("A", "B"),), Decimal("10"))

    assert len(opportunities) == 1
    assert captured and captured[0].path == ("A", "B")
    assert not client.swaps.calls


def test_opportunity_monitor_subscribes_to_event_socket() -> None:
    path_result = _build_successful_path_result(("A", "B"), amount_in="10", amount_out="12")
    service = _StubQuoteService((path_result,))
    finder = OpportunityFinder(service)
    client = _StubGSwap()
    socket = _StubEventClient()

    monitor = OpportunityMonitor(finder, client, execution_enabled=False)

    unsubscribe = monitor.subscribe_to_events(socket, (("A", "B"),), Decimal("10"))
    assert socket.is_connected()

    socket.emit("transaction", "Swap", {"data": {"transactionId": "abc"}})

    assert service.calls, "quote_paths should be triggered by transaction events"

    unsubscribe()
    monitor.close()

