"""Utilities for building decimal-safe arbitrage bots on GalaChain's gSwap."""

from __future__ import annotations

from decimal import Clamped, Decimal, getcontext

__all__ = ["configure_decimal_context"]


def configure_decimal_context(precision: int = 28) -> None:
    """Ensure every strategy starts with a deterministic decimal context.

    Args:
        precision: Desired Decimal precision for downstream calculations. Defaults to 28,
            matching Python's standard context and the SDK's recommended baseline.
    """
    context = getcontext()
    context.prec = precision
    context.traps[Clamped] = False
    # Force evaluation of an innocuous Decimal to ensure the context is ready.
    Decimal("0")
