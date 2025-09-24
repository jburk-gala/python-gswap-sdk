"""Pool utilities for the gSwap SDK."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict

from .decimal_utils import to_decimal
from .http import HttpClient
from .token import GalaChainTokenClassKey, get_token_ordering, parse_token_class_key
from .validation import validate_fee, validate_numeric_amount, validate_tick_spacing


@dataclass(slots=True)
class PoolData:
    bitmap: Dict[str, str]
    fee: int
    fee_growth_global0: Decimal
    fee_growth_global1: Decimal
    gross_pool_liquidity: Decimal
    liquidity: Decimal
    max_liquidity_per_tick: Decimal
    protocol_fees: int
    protocol_fees_token0: Decimal
    protocol_fees_token1: Decimal
    sqrt_price: Decimal
    tick_spacing: int
    token0: str
    token0_class_key: Dict[str, Any]
    token1: str
    token1_class_key: Dict[str, Any]


class Pools:
    def __init__(self, gateway_base_url: str, dex_contract_base_path: str, http_client: HttpClient) -> None:
        self._gateway_base_url = gateway_base_url.rstrip("/")
        self._dex_contract_base_path = dex_contract_base_path
        self._http_client = http_client

    def get_pool_data(
        self,
        token0: GalaChainTokenClassKey | str,
        token1: GalaChainTokenClassKey | str,
        fee: int,
    ) -> PoolData:
        validate_fee(fee)
        ordering = get_token_ordering(token0, token1, False)

        response = self._http_client.send_post_request(
            self._gateway_base_url,
            self._dex_contract_base_path,
            "/GetPoolData",
            {"token0": str(ordering.token0), "token1": str(ordering.token1), "fee": fee},
        )
        data = response.get("Data") if isinstance(response, dict) else None
        if not isinstance(data, dict):
            raise ValueError("Unexpected pool data response")

        return PoolData(
            bitmap=data.get("bitmap", {}),
            fee=int(data["fee"]),
            fee_growth_global0=to_decimal(data["feeGrowthGlobal0"]),
            fee_growth_global1=to_decimal(data["feeGrowthGlobal1"]),
            gross_pool_liquidity=to_decimal(data["grossPoolLiquidity"]),
            liquidity=to_decimal(data["liquidity"]),
            max_liquidity_per_tick=to_decimal(data["maxLiquidityPerTick"]),
            protocol_fees=int(data.get("protocolFees", 0)),
            protocol_fees_token0=to_decimal(data["protocolFeesToken0"]),
            protocol_fees_token1=to_decimal(data["protocolFeesToken1"]),
            sqrt_price=to_decimal(data["sqrtPrice"]),
            tick_spacing=int(data["tickSpacing"]),
            token0=data.get("token0", str(ordering.token0)),
            token0_class_key=data.get("token0ClassKey", {}),
            token1=data.get("token1", str(ordering.token1)),
            token1_class_key=data.get("token1ClassKey", {}),
        )

    def calculate_ticks_for_price(self, price: Any, tick_spacing: int) -> int:
        validate_numeric_amount(price, "price", allow_zero=True)
        validate_tick_spacing(tick_spacing)

        price_decimal = Decimal(str(price))
        if price_decimal == 0:
            return -886_800
        if price_decimal == Decimal("Infinity"):
            return 886_800

        base = Decimal("1.0001")
        uncoerced_ticks = int((price_decimal.ln() / base.ln()).to_integral_value(rounding="ROUND_HALF_UP"))
        ticks = (uncoerced_ticks // tick_spacing) * tick_spacing
        return max(-886_800, min(886_800, ticks))

    def calculate_price_for_ticks(self, tick: int) -> Decimal:
        if tick == -886_800:
            return Decimal("0")
        if tick == 886_800:
            return Decimal("Infinity")

        return Decimal(1.0001) ** Decimal(tick)

    def calculate_spot_price(
        self,
        in_token: GalaChainTokenClassKey | str,
        out_token: GalaChainTokenClassKey | str,
        pool_sqrt_price: Any,
    ) -> Decimal:
        validate_numeric_amount(pool_sqrt_price, "pool_sqrt_price")
        ordering = get_token_ordering(parse_token_class_key(in_token), parse_token_class_key(out_token), False)
        pool_price = Decimal(str(pool_sqrt_price)) ** 2
        if ordering.zero_for_one:
            return pool_price
        return Decimal(1) / pool_price
