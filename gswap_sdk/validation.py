"""Input validation helpers."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from .errors import GSwapSDKError


def _to_decimal(amount: Any) -> Decimal:
    try:
        return Decimal(str(amount))
    except (InvalidOperation, ValueError, TypeError) as exc:  # pragma: no cover - defensive
        raise GSwapSDKError(
            "Invalid numeric amount: could not be converted to Decimal",
            "VALIDATION_ERROR",
            {"value": amount, "reason": "conversion_error"},
        ) from exc


def validate_numeric_amount(amount: Any, parameter_name: str, allow_zero: bool = False) -> Decimal:
    value = _to_decimal(amount)
    if value.is_infinite():
        raise GSwapSDKError(
            f"Invalid {parameter_name}: must be a finite number",
            "VALIDATION_ERROR",
            {
                "type": "INVALID_NUMERIC_AMOUNT",
                "parameter_name": parameter_name,
                "value": str(amount),
                "reason": "not_finite",
            },
        )
    if not allow_zero and value == 0:
        raise GSwapSDKError(
            f"Invalid {parameter_name}: must be positive",
            "VALIDATION_ERROR",
            {
                "type": "INVALID_NUMERIC_AMOUNT",
                "parameter_name": parameter_name,
                "value": str(amount),
                "reason": "zero_not_allowed",
            },
        )
    if value < 0:
        raise GSwapSDKError(
            f"Invalid {parameter_name}: must be {'non-negative' if allow_zero else 'positive'}",
            "VALIDATION_ERROR",
            {
                "type": "INVALID_NUMERIC_AMOUNT",
                "parameter_name": parameter_name,
                "value": str(amount),
                "reason": "negative",
            },
        )
    return value


def validate_price_values(spot_price: Any, lower_price: Any, upper_price: Any) -> None:
    spot = validate_numeric_amount(spot_price, "spot_price")
    lower = validate_numeric_amount(lower_price, "lower_price")
    upper = validate_numeric_amount(upper_price, "upper_price")

    if lower > upper:
        raise GSwapSDKError(
            "Invalid price range: lower price must be less than or equal to upper price",
            "VALIDATION_ERROR",
            {
                "type": "INVALID_PRICE_RANGE",
                "lower_price": str(lower_price),
                "upper_price": str(upper_price),
            },
        )


def validate_token_decimals(decimals: int, parameter_name: str) -> None:
    if decimals < 0 or int(decimals) != decimals:
        raise GSwapSDKError(
            f"Invalid {parameter_name}: must be a non-negative integer",
            "VALIDATION_ERROR",
            {
                "type": "INVALID_TOKEN_DECIMALS",
                "parameter_name": parameter_name,
                "value": decimals,
            },
        )


def validate_tick_range(tick_lower: int, tick_upper: int) -> None:
    if int(tick_lower) != tick_lower or int(tick_upper) != tick_upper:
        raise GSwapSDKError(
            "Invalid tick values: ticks must be integers",
            "VALIDATION_ERROR",
            {
                "type": "INVALID_TICK_VALUES",
                "tick_lower": tick_lower,
                "tick_upper": tick_upper,
            },
        )

    if tick_lower >= tick_upper:
        raise GSwapSDKError(
            "Invalid tick range: tickLower must be less than tickUpper",
            "VALIDATION_ERROR",
            {
                "type": "INVALID_TICK_RANGE",
                "tick_lower": tick_lower,
                "tick_upper": tick_upper,
            },
        )

    if tick_lower < -886800 or tick_upper > 886800:
        raise GSwapSDKError(
            "Invalid tick range: ticks must be between -886800 and 886800",
            "VALIDATION_ERROR",
            {
                "type": "INVALID_TICK_BOUNDS",
                "tick_lower": tick_lower,
                "tick_upper": tick_upper,
                "min_tick": -886800,
                "max_tick": 886800,
            },
        )


def validate_fee(fee: int) -> None:
    if int(fee) != fee or fee < 0:
        raise GSwapSDKError(
            "Invalid fee: must be a non-negative integer",
            "VALIDATION_ERROR",
            {"type": "INVALID_FEE", "value": fee},
        )


def validate_tick_spacing(tick_spacing: int) -> None:
    if int(tick_spacing) != tick_spacing or tick_spacing <= 0:
        raise GSwapSDKError(
            "Invalid tick spacing: must be a positive integer",
            "VALIDATION_ERROR",
            {"type": "INVALID_TICK_SPACING", "value": tick_spacing},
        )


def validate_wallet_address(address: Optional[str]) -> str:
    if address is None:
        raise GSwapSDKError(
            "Invalid wallet address: No wallet address provided",
            "VALIDATION_ERROR",
            {
                "type": "MISSING_WALLET_ADDRESS",
                "hint": "Either provide a wallet address to the function you are calling, or set one when instantiating GSwapSDK",
            },
        )

    address = address.strip()
    if not address:
        raise GSwapSDKError(
            "Invalid wallet address: must be a non-empty string",
            "VALIDATION_ERROR",
            {"type": "INVALID_WALLET_ADDRESS", "value": address},
        )

    return address
