"""Helpers for working with :class:`decimal.Decimal`."""
from __future__ import annotations

from decimal import Decimal, getcontext

# Increase precision for price calculations.
getcontext().prec = 50


def to_decimal(value: object) -> Decimal:
    from decimal import Decimal as _Decimal, InvalidOperation

    if isinstance(value, Decimal):
        return value

    try:
        return _Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:  # pragma: no cover - defensive
        raise ValueError(f"Cannot convert {value!r} to Decimal") from exc
