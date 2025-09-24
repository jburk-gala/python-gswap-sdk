"""Quoting utilities for the gSwap SDK."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Iterable, Optional

from .decimal_utils import to_decimal
from .errors import GSwapSDKError
from .http import HttpClient
from .token import GalaChainTokenClassKey, get_token_ordering, parse_token_class_key
from .types.fees import ALL_FEE_TIERS
from .types.sdk_results import GetQuoteResult
from .validation import validate_numeric_amount


class Quoting:
    def __init__(
        self,
        gateway_base_url: str,
        dex_contract_base_path: str,
        http_client: Optional[HttpClient] = None,
    ) -> None:
        self._gateway_base_url = gateway_base_url.rstrip("/")
        self._dex_contract_base_path = dex_contract_base_path
        self._http_client = http_client or HttpClient()

    def quote_exact_input(
        self,
        token_in: GalaChainTokenClassKey | str,
        token_out: GalaChainTokenClassKey | str,
        amount_in: Any,
        fee: Optional[int] = None,
    ) -> GetQuoteResult:
        validate_numeric_amount(amount_in, "amount_in")
        if fee is not None:
            return self._quote_single(token_in, token_out, fee, amount_in, is_exact_input=True)

        return self._aggregate_quotes(
            ALL_FEE_TIERS,
            token_in,
            token_out,
            amount_in,
            choose_best=max,
            key=lambda quote: quote.out_token_amount,
            is_exact_input=True,
        )

    def quote_exact_output(
        self,
        token_in: GalaChainTokenClassKey | str,
        token_out: GalaChainTokenClassKey | str,
        amount_out: Any,
        fee: Optional[int] = None,
    ) -> GetQuoteResult:
        validate_numeric_amount(amount_out, "amount_out")
        if fee is not None:
            return self._quote_single(token_in, token_out, fee, amount_out, is_exact_input=False)

        return self._aggregate_quotes(
            ALL_FEE_TIERS,
            token_in,
            token_out,
            amount_out,
            choose_best=min,
            key=lambda quote: quote.in_token_amount,
            is_exact_input=False,
        )

    def _aggregate_quotes(
        self,
        fees: Iterable[int],
        token_in: GalaChainTokenClassKey | str,
        token_out: GalaChainTokenClassKey | str,
        amount: Any,
        *,
        choose_best,
        key,
        is_exact_input: bool,
    ) -> GetQuoteResult:
        quotes: list[GetQuoteResult] = []
        errors: list[GSwapSDKError] = []
        for fee_tier in fees:
            try:
                quotes.append(
                    self._quote_single(
                        token_in, token_out, int(fee_tier), amount, is_exact_input=is_exact_input
                    )
                )
            except GSwapSDKError as exc:
                if exc.code in {"CONFLICT", "OBJECT_NOT_FOUND"}:
                    continue
                errors.append(exc)

        if quotes:
            return choose_best(quotes, key=key)
        if errors:
            raise errors[0]
        raise GSwapSDKError.no_pool_available_error(token_in, token_out)

    def _quote_single(
        self,
        token_in: GalaChainTokenClassKey | str,
        token_out: GalaChainTokenClassKey | str,
        fee: int,
        amount: Any,
        *,
        is_exact_input: bool,
    ) -> GetQuoteResult:
        token_in_class = parse_token_class_key(token_in)
        token_out_class = parse_token_class_key(token_out)
        ordering = get_token_ordering(token_in_class, token_out_class, False)
        zero_for_one = ordering.zero_for_one

        unsigned_amount = validate_numeric_amount(amount, "amount", allow_zero=False)
        formatted_amount = unsigned_amount if zero_for_one else -unsigned_amount
        if not is_exact_input:
            formatted_amount = -formatted_amount

        response = self._post_quote(
            "/QuoteExactAmount",
            {
                "token0": ordering.token0.to_payload(),
                "token1": ordering.token1.to_payload(),
                "fee": fee,
                "amount": str(formatted_amount),
                "zeroForOne": zero_for_one,
            },
        )
        return self._build_quote_result(zero_for_one, fee, response)

    def _post_quote(self, endpoint: str, body: Dict[str, Any]) -> Dict[str, Any]:
        payload = self._http_client.send_post_request(
            self._gateway_base_url,
            self._dex_contract_base_path,
            endpoint,
            body,
        )
        if not isinstance(payload, dict) or "Data" not in payload:
            raise GSwapSDKError(
                "Unexpected response structure from quote endpoint",
                "INVALID_RESPONSE",
                {"payload": payload},
            )
        data = payload["Data"]
        if not isinstance(data, dict):
            raise GSwapSDKError(
                "Unexpected response payload from quote endpoint",
                "INVALID_RESPONSE",
                {"payload": payload},
            )
        return data

    def _build_quote_result(
        self, zero_for_one: bool, fee: int, payload: Dict[str, Any]
    ) -> GetQuoteResult:
        amount0 = to_decimal(payload.get("amount0"))
        amount1 = to_decimal(payload.get("amount1"))
        current_sqrt_price = to_decimal(payload.get("currentSqrtPrice"))
        new_sqrt_price = to_decimal(payload.get("newSqrtPrice"))

        current_price = current_sqrt_price**2
        new_price = new_sqrt_price**2

        if not zero_for_one:
            current_price = Decimal(1) / current_price
            new_price = Decimal(1) / new_price

        in_amount = amount0 if zero_for_one else amount1
        out_amount = amount1 if zero_for_one else amount0

        return GetQuoteResult(
            amount0=amount0,
            amount1=amount1,
            current_pool_sqrt_price=current_sqrt_price,
            new_pool_sqrt_price=new_sqrt_price,
            current_price=current_price,
            new_price=new_price,
            in_token_amount=abs(in_amount),
            out_token_amount=abs(out_amount),
            price_impact=(new_price - current_price) / current_price,
            fee_tier=fee,
        )

