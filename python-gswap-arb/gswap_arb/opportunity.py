"""Opportunity discovery and execution primitives for gSwap arbitrage."""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Callable, Optional, Sequence, Tuple, Protocol

from gswap_sdk.decimal_utils import to_decimal

from .quoting import HopQuote, PathQuoteResult, PathQuoteService, TokenPath

try:  # pragma: no cover - optional dependency
    from prometheus_client import CollectorRegistry, Counter, Gauge
except Exception:  # pragma: no cover - optional dependency
    CollectorRegistry = None  # type: ignore[assignment]
    Counter = None  # type: ignore[assignment]
    Gauge = None  # type: ignore[assignment]


AlertHandler = Callable[["TradingOpportunity"], None]


def _decimal_or_default(value: Decimal | int | float | str | None, default: Decimal) -> Decimal:
    if value is None:
        return default
    return to_decimal(value)


@dataclass(slots=True)
class TradingOpportunity:
    """Represents a profitable path discovered by :class:`OpportunityFinder`."""

    path: Tuple[str, ...]
    hops: Tuple[HopQuote, ...]
    initial_amount: Decimal
    expected_output: Decimal
    adjusted_output: Decimal
    net_profit: Decimal
    relative_profit: Decimal


@dataclass(slots=True)
class OpportunityMetricsRecorder:
    """Persist opportunity telemetry to JSONL and optionally Prometheus metrics."""

    jsonl_path: Optional[Path | str] = None
    registry: Optional[CollectorRegistry] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _evaluation_counter: Optional[Counter] = field(default=None, init=False, repr=False)
    _opportunity_counter: Optional[Counter] = field(default=None, init=False, repr=False)
    _execution_success_counter: Optional[Counter] = field(default=None, init=False, repr=False)
    _execution_failure_counter: Optional[Counter] = field(default=None, init=False, repr=False)
    _latest_profit_gauge: Optional[Gauge] = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        path = self.jsonl_path
        if path is not None and not isinstance(path, Path):
            self.jsonl_path = Path(path)

        if self.registry is None and CollectorRegistry is not None:
            self.registry = CollectorRegistry()

        if Counter is not None and Gauge is not None and self.registry is not None:
            self._evaluation_counter = Counter(
                "gswap_path_evaluations_total",
                "Number of multi-hop path evaluations performed.",
                registry=self.registry,
            )
            self._opportunity_counter = Counter(
                "gswap_opportunities_total",
                "Number of opportunities that met profit thresholds.",
                registry=self.registry,
            )
            self._execution_success_counter = Counter(
                "gswap_opportunity_executions_total",
                "Number of opportunities successfully executed.",
                registry=self.registry,
            )
            self._execution_failure_counter = Counter(
                "gswap_opportunity_execution_failures_total",
                "Number of opportunities that failed during execution.",
                registry=self.registry,
            )
            self._latest_profit_gauge = Gauge(
                "gswap_latest_opportunity_profit",
                "Net profit from the latest profitable opportunity.",
                registry=self.registry,
            )
        else:  # pragma: no cover - no prometheus support available
            self._evaluation_counter = None
            self._opportunity_counter = None
            self._execution_success_counter = None
            self._execution_failure_counter = None
            self._latest_profit_gauge = None

    def record_path_evaluation(
        self,
        result: PathQuoteResult,
        opportunity: Optional[TradingOpportunity],
    ) -> None:
        """Persist diagnostics for each evaluated path."""

        self._write_jsonl(
            {
                "timestamp": time.time(),
                "type": "path_evaluation",
                "path": list(result.path),
                "initial_amount": str(result.initial_amount),
                "final_amount": str(result.final_amount) if result.final_amount is not None else None,
                "net_profit": str(opportunity.net_profit) if opportunity else None,
                "relative_profit": str(opportunity.relative_profit) if opportunity else None,
                "successful": result.successful,
                "hop_failures": [failure.index for failure in result.failures],
            }
        )

        if self._evaluation_counter is not None:  # pragma: no branch - simple guard
            self._evaluation_counter.inc()
            if opportunity is not None:
                self._opportunity_counter.inc()
                self._latest_profit_gauge.set(float(opportunity.net_profit))

    def record_alert(self, opportunity: TradingOpportunity) -> None:
        """Track that an opportunity was surfaced but not executed."""

        self._write_jsonl(
            {
                "timestamp": time.time(),
                "type": "opportunity_alert",
                "path": list(opportunity.path),
                "net_profit": str(opportunity.net_profit),
                "relative_profit": str(opportunity.relative_profit),
            }
        )

    def record_execution_success(self, opportunity: TradingOpportunity) -> None:
        """Record a successful execution attempt."""

        self._write_jsonl(
            {
                "timestamp": time.time(),
                "type": "execution_success",
                "path": list(opportunity.path),
                "net_profit": str(opportunity.net_profit),
                "relative_profit": str(opportunity.relative_profit),
            }
        )

        if self._execution_success_counter is not None:  # pragma: no branch - simple guard
            self._execution_success_counter.inc()

    def record_execution_failure(
        self, opportunity: TradingOpportunity, error: Exception
    ) -> None:
        """Record a failed execution attempt."""

        self._write_jsonl(
            {
                "timestamp": time.time(),
                "type": "execution_failure",
                "path": list(opportunity.path),
                "net_profit": str(opportunity.net_profit),
                "relative_profit": str(opportunity.relative_profit),
                "error": type(error).__name__,
                "error_message": str(error),
            }
        )

        if self._execution_failure_counter is not None:  # pragma: no branch - simple guard
            self._execution_failure_counter.inc()

    def _write_jsonl(self, payload: dict) -> None:
        if self.jsonl_path is None:
            return
        with self._lock:
            self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            with self.jsonl_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(payload, ensure_ascii=False) + "\n")


@dataclass(slots=True)
class OpportunityFinder:
    """Score multi-hop paths and surface profitable opportunities."""

    quote_service: PathQuoteService
    min_absolute_profit: Decimal = field(default_factory=lambda: Decimal("0"))
    min_relative_profit: Decimal = field(default_factory=lambda: Decimal("0"))
    slippage_buffer: Decimal = field(default_factory=lambda: Decimal("0"))
    metrics: Optional[OpportunityMetricsRecorder] = None
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))

    def __post_init__(self) -> None:
        self.min_absolute_profit = _decimal_or_default(self.min_absolute_profit, Decimal("0"))
        self.min_relative_profit = _decimal_or_default(self.min_relative_profit, Decimal("0"))
        self.slippage_buffer = _decimal_or_default(self.slippage_buffer, Decimal("0"))
        if self.slippage_buffer < Decimal("0"):
            raise ValueError("slippage_buffer cannot be negative")
        if self.min_absolute_profit < Decimal("0"):
            raise ValueError("min_absolute_profit cannot be negative")
        if self.min_relative_profit < Decimal("0"):
            raise ValueError("min_relative_profit cannot be negative")

    def evaluate_paths(
        self,
        paths: Sequence[TokenPath],
        amount_in: Decimal | int | str,
        *,
        fee_overrides: Optional[dict | Sequence[Optional[int]]] = None,
    ) -> Tuple[TradingOpportunity, ...]:
        """Evaluate candidate paths and return profitable opportunities."""

        amount_decimal = to_decimal(amount_in)
        results = self.quote_service.quote_paths(paths, amount_decimal, fee_overrides=fee_overrides)

        opportunities: list[TradingOpportunity] = []
        for result in results:
            opportunity = self._score_result(result)
            if opportunity is not None:
                opportunities.append(opportunity)
            if self.metrics is not None:
                self.metrics.record_path_evaluation(result, opportunity)

        opportunities.sort(key=lambda item: item.net_profit, reverse=True)
        return tuple(opportunities)

    def find_best_opportunity(
        self,
        paths: Sequence[TokenPath],
        amount_in: Decimal | int | str,
        *,
        fee_overrides: Optional[dict | Sequence[Optional[int]]] = None,
    ) -> Optional[TradingOpportunity]:
        """Return the most profitable opportunity for the provided paths."""

        opportunities = self.evaluate_paths(paths, amount_in, fee_overrides=fee_overrides)
        return opportunities[0] if opportunities else None

    def _score_result(self, result: PathQuoteResult) -> Optional[TradingOpportunity]:
        if not result.successful or result.final_amount is None:
            if result.failures:
                self.logger.debug(
                    "Path %s failed to quote hop(s): %s",
                    result.path,
                    [failure.index for failure in result.failures],
                )
            return None

        adjusted_output = self._apply_slippage(result.final_amount)
        net_profit = adjusted_output - result.initial_amount
        if net_profit < self.min_absolute_profit:
            self.logger.debug(
                "Rejected path %s due to insufficient absolute profit (%s < %s)",
                result.path,
                net_profit,
                self.min_absolute_profit,
            )
            return None

        if result.initial_amount == Decimal("0"):
            relative_profit = Decimal("0")
        else:
            relative_profit = net_profit / result.initial_amount

        if relative_profit < self.min_relative_profit:
            self.logger.debug(
                "Rejected path %s due to insufficient relative profit (%s < %s)",
                result.path,
                relative_profit,
                self.min_relative_profit,
            )
            return None

        opportunity = TradingOpportunity(
            path=result.path,
            hops=result.hops,
            initial_amount=result.initial_amount,
            expected_output=result.final_amount,
            adjusted_output=adjusted_output,
            net_profit=net_profit,
            relative_profit=relative_profit,
        )
        self.logger.info(
            "Profitable opportunity detected on path %s: net=%s (relative=%s)",
            result.path,
            net_profit,
            relative_profit,
        )
        return opportunity

    def _apply_slippage(self, amount: Decimal) -> Decimal:
        if self.slippage_buffer == Decimal("0"):
            return amount
        multiplier = Decimal("1") - self.slippage_buffer
        if multiplier < Decimal("0"):
            multiplier = Decimal("0")
        return amount * multiplier


@dataclass(slots=True)
class OpportunityMonitor:
    """Coordinate real-time evaluation and optional execution of opportunities."""

    finder: OpportunityFinder
    client: "GSwapClient"
    execution_enabled: bool = False
    slippage_guard: Decimal = field(default_factory=lambda: Decimal("0"))
    metrics: Optional[OpportunityMetricsRecorder] = None
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))
    alert_handler: Optional[AlertHandler] = None
    _subscriptions: list[tuple["EventSocketLike", Callable[..., None]]] = field(
        default_factory=list, init=False, repr=False
    )

    def __post_init__(self) -> None:
        self.slippage_guard = _decimal_or_default(self.slippage_guard, Decimal("0"))
        if self.slippage_guard < Decimal("0"):
            raise ValueError("slippage_guard cannot be negative")

    def poll_once(
        self,
        paths: Sequence[TokenPath],
        amount_in: Decimal | int | str,
        *,
        fee_overrides: Optional[dict | Sequence[Optional[int]]] = None,
    ) -> Tuple[TradingOpportunity, ...]:
        """Evaluate paths immediately and act according to configuration."""

        opportunities = self.finder.evaluate_paths(paths, amount_in, fee_overrides=fee_overrides)
        if not opportunities:
            self.logger.debug("No profitable opportunities detected during poll")
            return opportunities

        if self.execution_enabled:
            best = opportunities[0]
            try:
                self._execute(best)
            except Exception as exc:
                if self.metrics is not None:
                    self.metrics.record_execution_failure(best, exc)
                self.logger.exception("Failed to execute opportunity on path %s", best.path)
                raise
        else:
            for opportunity in opportunities:
                self._emit_alert(opportunity)

        return opportunities

    def poll_continuously(
        self,
        paths: Sequence[TokenPath],
        amount_in: Decimal | int | str,
        *,
        fee_overrides: Optional[dict | Sequence[Optional[int]]] = None,
        interval_seconds: float = 5.0,
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        """Continuously poll for opportunities until ``stop_event`` is set."""

        if stop_event is None:
            stop_event = threading.Event()

        while not stop_event.is_set():
            self.poll_once(paths, amount_in, fee_overrides=fee_overrides)
            stop_event.wait(interval_seconds)

    def subscribe_to_events(
        self,
        event_client: "EventSocketLike",
        paths: Sequence[TokenPath],
        amount_in: Decimal | int | str,
        *,
        fee_overrides: Optional[dict | Sequence[Optional[int]]] = None,
        event_filter: Optional[Callable[[str, dict], bool]] = None,
    ) -> Callable[[], None]:
        """Subscribe to bundler socket events and react to each transaction."""

        def _handle(event: str, payload: dict) -> None:
            if event_filter is not None and not event_filter(event, payload):
                return
            try:
                self.poll_once(paths, amount_in, fee_overrides=fee_overrides)
            except Exception:
                # Errors are already logged inside ``poll_once``.
                return

        event_client.on("transaction", _handle)
        self._subscriptions.append((event_client, _handle))
        if not event_client.is_connected():
            event_client.connect()

        def _unsubscribe() -> None:
            event_client.off("transaction", _handle)
            try:
                self._subscriptions.remove((event_client, _handle))
            except ValueError:  # pragma: no cover - defensive
                pass

        return _unsubscribe

    def close(self) -> None:
        """Detach from all event subscriptions."""

        for client, callback in list(self._subscriptions):
            client.off("transaction", callback)
            if client.is_connected():
                client.disconnect()
            self._subscriptions.remove((client, callback))

    def _emit_alert(self, opportunity: TradingOpportunity) -> None:
        self.logger.info(
            "Opportunity detected (path=%s, net=%s, relative=%s)",
            opportunity.path,
            opportunity.net_profit,
            opportunity.relative_profit,
        )
        if self.alert_handler is not None:
            self.alert_handler(opportunity)
        if self.metrics is not None:
            self.metrics.record_alert(opportunity)

    def _execute(self, opportunity: TradingOpportunity) -> None:
        self.logger.info(
            "Executing opportunity (path=%s, net=%s)", opportunity.path, opportunity.net_profit
        )
        for hop in opportunity.hops:
            amount_payload: dict[str, object] = {"exactIn": hop.amount_in}
            minimum_out = self._minimum_output(hop)
            if minimum_out is not None:
                amount_payload["amountOutMinimum"] = minimum_out
            self.client.swaps.swap(hop.token_in, hop.token_out, hop.fee_tier, amount_payload)

        if self.metrics is not None:
            self.metrics.record_execution_success(opportunity)

    def _minimum_output(self, hop: HopQuote) -> Optional[Decimal]:
        if self.slippage_guard == Decimal("0"):
            return None
        multiplier = Decimal("1") - self.slippage_guard
        if multiplier < Decimal("0"):
            multiplier = Decimal("0")
        return hop.amount_out * multiplier


class EventSocketLike(Protocol):
    """Structural protocol for :class:`EventSocketClient` compatibility."""

    def on(self, event: str, callback: Callable[..., None]) -> None:
        ...

    def off(self, event: str, callback: Callable[..., None]) -> None:
        ...

    def connect(self) -> None:
        ...

    def disconnect(self) -> None:
        ...

    def is_connected(self) -> bool:
        ...


class SwapsLike(Protocol):
    def swap(self, token_in: str, token_out: str, fee: int, amount: dict[str, object]) -> None:
        ...


class GSwapClient(Protocol):
    """Structural protocol for the :class:`gswap_sdk.gswap.GSwap` client."""

    swaps: SwapsLike

