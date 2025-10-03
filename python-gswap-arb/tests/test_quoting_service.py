"""Tests for the path quoting service."""

from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, List, Mapping, Sequence, Tuple

import requests

from gswap_arb.quoting import PathQuoteService
from gswap_sdk.errors import GSwapSDKError
from gswap_sdk.types.sdk_results import GetQuoteResult


def make_quote(
    *,
    in_amount: Decimal,
    out_amount: Decimal,
    fee: int,
    price_impact: Decimal,
    current_sqrt: Decimal,
    new_sqrt: Decimal,
) -> GetQuoteResult:
    return GetQuoteResult(
        amount0=in_amount,
        amount1=-out_amount,
        current_pool_sqrt_price=current_sqrt,
        new_pool_sqrt_price=new_sqrt,
        current_price=current_sqrt**2,
        new_price=new_sqrt**2,
        in_token_amount=in_amount,
        out_token_amount=out_amount,
        price_impact=price_impact,
        fee_tier=fee,
    )


@dataclass
class SequenceQuoting:
    responses: Sequence[GetQuoteResult]

    def __post_init__(self) -> None:
        self.calls: List[Tuple[str, str, Decimal, int | None]] = []

    def quote_exact_input(
        self, token_in: str, token_out: str, amount_in: Decimal, fee: int | None = None
    ) -> GetQuoteResult:
        index = len(self.calls)
        self.calls.append((token_in, token_out, amount_in, fee))
        return self.responses[index]


@dataclass
class MappingQuoting:
    handlers: Mapping[Tuple[str, str], Callable[[Decimal, int | None], GetQuoteResult]]

    def __post_init__(self) -> None:
        self.calls: List[Tuple[str, str, Decimal, int | None]] = []

    def quote_exact_input(
        self, token_in: str, token_out: str, amount_in: Decimal, fee: int | None = None
    ) -> GetQuoteResult:
        self.calls.append((token_in, token_out, amount_in, fee))
        handler = self.handlers[(token_in, token_out)]
        return handler(amount_in, fee)


@dataclass
class FakeClient:
    quoting: object


def test_quote_path_chains_hops_and_computes_diagnostics() -> None:
    quoting = SequenceQuoting(
        responses=[
            make_quote(
                in_amount=Decimal("10"),
                out_amount=Decimal("20"),
                fee=300,
                price_impact=Decimal("0.01"),
                current_sqrt=Decimal("1.2"),
                new_sqrt=Decimal("1.3"),
            ),
            make_quote(
                in_amount=Decimal("20"),
                out_amount=Decimal("9"),
                fee=500,
                price_impact=Decimal("0.02"),
                current_sqrt=Decimal("1.3"),
                new_sqrt=Decimal("1.4"),
            ),
        ]
    )
    service = PathQuoteService(FakeClient(quoting), max_retries=1, per_hop_timeout_seconds=None)

    result = service.quote_path(["A", "B", "C"], Decimal("10"))

    assert result.successful is True
    assert result.final_amount == Decimal("9")
    assert result.initial_amount == Decimal("10")
    assert result.cumulative_price_impact == Decimal("0.0302")
    assert result.sqrt_price_transitions == (
        (Decimal("1.2"), Decimal("1.3")),
        (Decimal("1.3"), Decimal("1.4")),
    )
    assert [call[2] for call in quoting.calls] == [Decimal("10"), Decimal("20")]


def test_quote_path_respects_fee_overrides() -> None:
    quoting = SequenceQuoting(
        responses=[
            make_quote(
                in_amount=Decimal("5"),
                out_amount=Decimal("4.5"),
                fee=100,
                price_impact=Decimal("0.0"),
                current_sqrt=Decimal("1"),
                new_sqrt=Decimal("1.01"),
            ),
            make_quote(
                in_amount=Decimal("4.5"),
                out_amount=Decimal("4.4"),
                fee=200,
                price_impact=Decimal("0.0"),
                current_sqrt=Decimal("1.01"),
                new_sqrt=Decimal("1.02"),
            ),
        ]
    )
    service = PathQuoteService(FakeClient(quoting), max_retries=1, per_hop_timeout_seconds=None)

    result = service.quote_path(
        ["A", "B", "C"],
        Decimal("5"),
        fee_overrides={0: 300, ("B", "C"): 400},
    )

    assert result.successful is True
    assert result.initial_amount == Decimal("5")
    assert [call[3] for call in quoting.calls] == [300, 400]


def test_quote_paths_continue_after_timeout_failure() -> None:
    def _timeout_handler(amount_in: Decimal, fee: int | None) -> GetQuoteResult:
        raise requests.Timeout("network hiccup")

    def _success_handler(amount_in: Decimal, fee: int | None) -> GetQuoteResult:
        return make_quote(
            in_amount=amount_in,
            out_amount=Decimal("6"),
            fee=300,
            price_impact=Decimal("0.0"),
            current_sqrt=Decimal("1"),
            new_sqrt=Decimal("1"),
        )

    quoting = MappingQuoting({("A", "B"): _timeout_handler, ("X", "Y"): _success_handler})
    service = PathQuoteService(
        FakeClient(quoting), max_retries=2, per_hop_timeout_seconds=None, retry_backoff_seconds=0
    )

    results = service.quote_paths((["A", "B"], ["X", "Y"]), Decimal("3"))

    first, second = results
    assert first.successful is False
    assert first.failures and isinstance(first.failures[0].error, requests.Timeout)
    assert first.failures[0].attempts == 2
    assert second.successful is True
    assert second.final_amount == Decimal("6")
    assert [call[:2] for call in quoting.calls] == [("A", "B"), ("A", "B"), ("X", "Y")]


def test_quote_path_does_not_retry_on_sdk_error() -> None:
    def _error_handler(amount_in: Decimal, fee: int | None) -> GetQuoteResult:
        raise GSwapSDKError("bad pool", "NO_POOL")

    quoting = MappingQuoting({("A", "B"): _error_handler})
    service = PathQuoteService(
        FakeClient(quoting), max_retries=3, per_hop_timeout_seconds=None, retry_backoff_seconds=0
    )

    result = service.quote_path(["A", "B"], Decimal("1"))

    assert result.successful is False
    assert result.failures[0].attempts == 1
    assert len(quoting.calls) == 1


def test_quote_path_enforces_timeout_for_hanging_request() -> None:
    def _sleep_handler(amount_in: Decimal, fee: int | None) -> GetQuoteResult:
        time.sleep(0.05)
        return make_quote(
            in_amount=amount_in,
            out_amount=amount_in,
            fee=100,
            price_impact=Decimal("0"),
            current_sqrt=Decimal("1"),
            new_sqrt=Decimal("1"),
        )

    quoting = MappingQuoting({("A", "B"): _sleep_handler})
    service = PathQuoteService(
        FakeClient(quoting), max_retries=1, per_hop_timeout_seconds=0.01, retry_backoff_seconds=0
    )

    result = service.quote_path(["A", "B"], Decimal("2"))

    assert result.successful is False
    assert isinstance(result.failures[0].error, TimeoutError)

