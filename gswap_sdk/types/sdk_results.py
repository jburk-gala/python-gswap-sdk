"""Dataclasses describing common results returned by the SDK."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import List

from ..token import GalaChainTokenClassKey


@dataclass(slots=True)
class GetQuoteResult:
    amount0: Decimal
    amount1: Decimal
    current_pool_sqrt_price: Decimal
    new_pool_sqrt_price: Decimal
    current_price: Decimal
    new_price: Decimal
    in_token_amount: Decimal
    out_token_amount: Decimal
    price_impact: Decimal
    fee_tier: int


@dataclass(slots=True)
class LiquidityPosition:
    pool_hash: str
    position_id: str
    token0_class_key: GalaChainTokenClassKey
    token1_class_key: GalaChainTokenClassKey
    token0_img: str
    token1_img: str
    token0_symbol: str
    token1_symbol: str
    fee: int
    liquidity: Decimal
    tick_lower: int
    tick_upper: int
    created_at: str


@dataclass(slots=True)
class GetUserPositionsResponse:
    positions: List[LiquidityPosition]
    bookmark: str


@dataclass(slots=True)
class GetPositionResult:
    fee: int
    fee_growth_inside0_last: Decimal
    fee_growth_inside1_last: Decimal
    liquidity: Decimal
    pool_hash: str
    position_id: str
    tick_lower: int
    tick_upper: int
    token0_class_key: GalaChainTokenClassKey
    token1_class_key: GalaChainTokenClassKey
    tokens_owed0: Decimal
    tokens_owed1: Decimal


@dataclass(slots=True)
class AssetBalance:
    image: str
    name: str
    decimals: int
    verify: bool
    symbol: str
    quantity: Decimal


@dataclass(slots=True)
class GetUserAssetsResult:
    tokens: List[AssetBalance]
    count: int

