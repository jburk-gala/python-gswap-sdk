"""Constants that describe supported fee tiers."""
from __future__ import annotations

from enum import IntEnum


class FEE_TIER(IntEnum):
    """Fee tiers supported by the protocol."""

    PERCENT_00_05 = 500
    PERCENT_00_30 = 3_000
    PERCENT_01_00 = 10_000


ALL_FEE_TIERS = (
    FEE_TIER.PERCENT_00_05,
    FEE_TIER.PERCENT_00_30,
    FEE_TIER.PERCENT_01_00,
)

