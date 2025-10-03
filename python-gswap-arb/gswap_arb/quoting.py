"""Path-aware quoting helpers for gSwap arbitrage tools."""

from __future__ import annotations

import concurrent.futures
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, MutableSequence, Optional, Sequence, Tuple, TYPE_CHECKING, Union

import requests

from gswap_sdk.errors import GSwapSDKError
from gswap_sdk.gswap import GSwap
from gswap_sdk.types.sdk_results import GetQuoteResult

if TYPE_CHECKING:
    from gswap_sdk.token import GalaChainTokenClassKey

TokenPath = Sequence[Union[str, "GalaChainTokenClassKey"]]
FeeOverrides = Union[Sequence[Optional[int]], Mapping[int, int], Mapping[Tuple[str, str], int]]


@dataclass(slots=True)
class HopQuote:
    """Successful quote for an individual hop along a path."""

    index: int
    token_in: str
    token_out: str
    amount_in: Decimal
    amount_out: Decimal
    fee_tier: int
    price_impact: Decimal
    current_sqrt_price: Decimal
    new_sqrt_price: Decimal
    attempts: int


@dataclass(slots=True)
class HopFailure:
    """Metadata describing a hop that failed to quote."""

    index: int
    token_in: str
    token_out: str
    amount_in: Decimal
    attempts: int
    error: Exception


@dataclass(slots=True)
class PathQuoteResult:
    """Result of chaining quotes across a multi-hop path."""

    path: Tuple[str, ...]
    initial_amount: Decimal
    hops: Tuple[HopQuote, ...]
    failures: Tuple[HopFailure, ...]
    final_amount: Optional[Decimal]
    cumulative_price_impact: Optional[Decimal]

    @property
    def successful(self) -> bool:
        """Whether every hop produced a quote."""

        return not self.failures and bool(self.hops)

    @property
    def sqrt_price_transitions(self) -> Tuple[Tuple[Decimal, Decimal], ...]:
        """Expose the intermediate sqrt price movements for diagnostics."""

        return tuple((hop.current_sqrt_price, hop.new_sqrt_price) for hop in self.hops)


@dataclass(slots=True)
class _HopAttempt:
    """Internal helper describing the outcome of a hop attempt."""

    attempts: int
    quote: Optional[GetQuoteResult]
    error: Optional[Exception]


class PathQuoteService:
    """Quote chained paths using the SDK's per-hop pricing.

    The service retries transient network issues and surfaces detailed diagnostics for
    each hop so callers can make informed routing decisions.
    """

    def __init__(
        self,
        client: GSwap,
        *,
        max_retries: int = 3,
        per_hop_timeout_seconds: Optional[float] = 10.0,
        retry_backoff_seconds: float = 0.2,
    ) -> None:
        if max_retries < 1:
            raise ValueError("max_retries must be at least 1")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds cannot be negative")

        self._client = client
        self._max_retries = max_retries
        self._per_hop_timeout = per_hop_timeout_seconds
        self._retry_backoff = retry_backoff_seconds

    def quote_path(
        self,
        path: TokenPath,
        amount_in: Union[Decimal, int, str],
        *,
        fee_overrides: Optional[FeeOverrides] = None,
    ) -> PathQuoteResult:
        """Quote a multi-hop path, chaining each hop's output into the next.

        Args:
            path: Ordered token class keys that define the swap path.
            amount_in: Exact-input amount for the first hop.
            fee_overrides: Optional per-hop fee tier overrides. Supports either a
                sequence of overrides (aligned to the hop index), a mapping of hop
                index to fee, or a mapping keyed by ``(token_in, token_out)``.

        Returns:
            A :class:`PathQuoteResult` with detailed diagnostics. If a hop fails, the
            failure information is recorded while subsequent paths can continue.
        """

        tokens = tuple(str(token) for token in path)
        if len(tokens) < 2:
            raise ValueError("A path must include at least two tokens")

        initial_amount = amount_in if isinstance(amount_in, Decimal) else Decimal(str(amount_in))
        current_amount = initial_amount
        hops: MutableSequence[HopQuote] = []
        failures: MutableSequence[HopFailure] = []

        for index, (token_in, token_out) in enumerate(zip(tokens, tokens[1:])):
            fee_override = self._resolve_fee_override(fee_overrides, index, token_in, token_out)
            attempt = self._quote_with_retries(token_in, token_out, current_amount, fee_override)

            if attempt.quote is None:
                assert attempt.error is not None
                failures.append(
                    HopFailure(
                        index=index,
                        token_in=token_in,
                        token_out=token_out,
                        amount_in=current_amount,
                        attempts=attempt.attempts,
                        error=attempt.error,
                    )
                )
                break

            quote = attempt.quote
            hops.append(
                HopQuote(
                    index=index,
                    token_in=token_in,
                    token_out=token_out,
                    amount_in=current_amount,
                    amount_out=quote.out_token_amount,
                    fee_tier=quote.fee_tier,
                    price_impact=quote.price_impact,
                    current_sqrt_price=quote.current_pool_sqrt_price,
                    new_sqrt_price=quote.new_pool_sqrt_price,
                    attempts=attempt.attempts,
                )
            )
            current_amount = quote.out_token_amount

        final_amount: Optional[Decimal] = current_amount if hops and not failures else None
        cumulative_price_impact: Optional[Decimal] = None
        if hops and not failures:
            cumulative_multiplier = Decimal("1")
            for hop in hops:
                cumulative_multiplier *= Decimal("1") + hop.price_impact
            cumulative_price_impact = cumulative_multiplier - Decimal("1")

        return PathQuoteResult(
            path=tokens,
            initial_amount=initial_amount,
            hops=tuple(hops),
            failures=tuple(failures),
            final_amount=final_amount,
            cumulative_price_impact=cumulative_price_impact,
        )

    def quote_paths(
        self,
        paths: Sequence[TokenPath],
        amount_in: Union[Decimal, int, str],
        *,
        fee_overrides: Optional[FeeOverrides] = None,
    ) -> Tuple[PathQuoteResult, ...]:
        """Quote several paths while isolating failures per-path."""

        return tuple(self.quote_path(path, amount_in, fee_overrides=fee_overrides) for path in paths)

    def _quote_with_retries(
        self,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        fee_override: Optional[int],
    ) -> _HopAttempt:
        last_error: Optional[Exception] = None
        for attempt in range(1, self._max_retries + 1):
            try:
                quote = self._invoke_with_timeout(token_in, token_out, amount_in, fee_override)
            except (TimeoutError, requests.RequestException) as exc:
                last_error = exc
            except GSwapSDKError as exc:
                return _HopAttempt(attempts=attempt, quote=None, error=exc)
            except Exception as exc:  # pragma: no cover - defensive guard
                return _HopAttempt(attempts=attempt, quote=None, error=exc)
            else:
                return _HopAttempt(attempts=attempt, quote=quote, error=None)

            if attempt < self._max_retries and self._retry_backoff:
                time.sleep(self._retry_backoff * attempt)

        assert last_error is not None
        return _HopAttempt(attempts=self._max_retries, quote=None, error=last_error)

    def _invoke_with_timeout(
        self,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        fee_override: Optional[int],
    ) -> GetQuoteResult:
        def _call() -> GetQuoteResult:
            if fee_override is not None:
                return self._client.quoting.quote_exact_input(token_in, token_out, amount_in, fee=fee_override)
            return self._client.quoting.quote_exact_input(token_in, token_out, amount_in)

        if self._per_hop_timeout is None:
            return _call()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_call)
            try:
                return future.result(timeout=self._per_hop_timeout)
            except concurrent.futures.TimeoutError as exc:
                future.cancel()
                raise TimeoutError(f"Quote request timed out after {self._per_hop_timeout} seconds") from exc

    @staticmethod
    def _resolve_fee_override(
        fee_overrides: Optional[FeeOverrides], index: int, token_in: str, token_out: str
    ) -> Optional[int]:
        if fee_overrides is None:
            return None

        if isinstance(fee_overrides, Mapping):
            pair_override = fee_overrides.get((token_in, token_out))  # type: ignore[arg-type]
            if pair_override is not None:
                return pair_override
            index_override = fee_overrides.get(index)  # type: ignore[arg-type]
            if index_override is not None:
                return index_override
            return None

        if index < len(fee_overrides):
            return fee_overrides[index]
        return None

