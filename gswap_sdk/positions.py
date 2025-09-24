"""Liquidity position management."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Dict, List, Mapping, Optional

from .bundler import Bundler
from .decimal_utils import to_decimal
from .http import HttpClient
from .pools import Pools
from .token import (
    GalaChainTokenClassKey,
    get_token_ordering,
    parse_token_class_key,
    stringify_token_class_key,
)
from .validation import (
    validate_fee,
    validate_numeric_amount,
    validate_price_values,
    validate_tick_range,
    validate_tick_spacing,
    validate_token_decimals,
    validate_wallet_address,
)
from .types.sdk_results import (
    GetPositionResult,
    GetUserPositionsResponse,
    LiquidityPosition,
)


def _decimal_to_string(value: Decimal) -> str:
    return format(value, "f")


@dataclass(slots=True)
class Positions:
    gateway_base_url: str
    dex_contract_base_path: str
    bundler_service: Bundler
    pool_service: Pools
    http_client: HttpClient
    wallet_address: Optional[str] = None

    def __post_init__(self) -> None:
        self.gateway_base_url = self.gateway_base_url.rstrip("/")

    def get_user_positions(
        self, owner_address: str, limit: Optional[int] = None, bookmark: Optional[str] = None
    ) -> GetUserPositionsResponse:
        body: Dict[str, object] = {"user": validate_wallet_address(owner_address)}
        if limit is not None:
            body["limit"] = limit
        if bookmark:
            body["bookMark"] = bookmark
        return self._send_user_positions_request("/GetUserPositions", body)

    def get_position(
        self,
        owner_address: str,
        position: Mapping[str, object],
    ) -> GetPositionResult:
        token0 = parse_token_class_key(position["token0ClassKey"])
        token1 = parse_token_class_key(position["token1ClassKey"])
        body = {
            "owner": validate_wallet_address(owner_address),
            "token0": asdict(token0),
            "token1": asdict(token1),
            "fee": position["fee"],
            "tickLower": position["tickLower"],
            "tickUpper": position["tickUpper"],
        }
        return self._send_position_request("/GetPositions", body)

    def estimate_remove_liquidity(
        self,
        owner_address: str,
        position_id: str,
        token0: GalaChainTokenClassKey | str,
        token1: GalaChainTokenClassKey | str,
        fee: int,
        tick_lower: int,
        tick_upper: int,
        amount: Decimal | str | int,
    ) -> Dict[str, Decimal]:
        owner = validate_wallet_address(owner_address)
        validate_fee(fee)
        validate_tick_range(tick_lower, tick_upper)
        validate_numeric_amount(amount, "amount")

        token0_key = parse_token_class_key(token0)
        token1_key = parse_token_class_key(token1)
        ordering = get_token_ordering(token0_key, token1_key, False)

        payload = self.http_client.send_post_request(
            self.gateway_base_url,
            self.dex_contract_base_path,
            "/GetRemoveLiquidityEstimation",
            {
                "tickLower": tick_lower,
                "tickUpper": tick_upper,
                "amount": _decimal_to_string(validate_numeric_amount(amount, "amount")),
                "token0": asdict(ordering.token0),
                "token1": asdict(ordering.token1),
                "fee": fee,
                "owner": owner,
                "positionId": position_id,
            },
        )
        data = payload.get("Data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise ValueError("Unexpected remove liquidity estimation response")
        return {
            "amount0": to_decimal(data.get("amount0")),
            "amount1": to_decimal(data.get("amount1")),
        }

    def get_position_by_id(
        self, owner_address: str, position_id: str
    ) -> Optional[GetPositionResult]:
        positions = self.get_user_positions(owner_address)
        for position in positions.positions:
            if position.position_id == position_id:
                return self.get_position(
                    owner_address,
                    {
                        "token0ClassKey": position.token0_class_key,
                        "token1ClassKey": position.token1_class_key,
                        "fee": position.fee,
                        "tickLower": position.tick_lower,
                        "tickUpper": position.tick_upper,
                    },
                )
        return None

    def add_liquidity_by_ticks(
        self,
        token0: GalaChainTokenClassKey | str,
        token1: GalaChainTokenClassKey | str,
        fee: int,
        tick_lower: int,
        tick_upper: int,
        amount0_desired: Decimal | str | int,
        amount1_desired: Decimal | str | int,
        amount0_min: Decimal | str | int,
        amount1_min: Decimal | str | int,
        position_id: str,
        wallet_address: Optional[str] = None,
    ):
        wallet = validate_wallet_address(wallet_address or self.wallet_address)
        validate_fee(fee)
        validate_tick_range(tick_lower, tick_upper)

        token0_key = parse_token_class_key(token0)
        token1_key = parse_token_class_key(token1)
        ordering = get_token_ordering(
            token0_key,
            token1_key,
            True,
            [amount0_desired, amount0_min],
            [amount1_desired, amount1_min],
        )

        to_sign = {
            "token0": asdict(ordering.token0),
            "token1": asdict(ordering.token1),
            "fee": fee,
            "owner": wallet,
            "tickLower": tick_lower,
            "tickUpper": tick_upper,
            "amount0Desired": _decimal_to_string(
                validate_numeric_amount(ordering.token0_attributes[0], "amount0Desired", True)
            ),
            "amount1Desired": _decimal_to_string(
                validate_numeric_amount(ordering.token1_attributes[0], "amount1Desired", True)
            ),
            "amount0Min": _decimal_to_string(
                validate_numeric_amount(ordering.token0_attributes[1], "amount0Min", True)
            ),
            "amount1Min": _decimal_to_string(
                validate_numeric_amount(ordering.token1_attributes[1], "amount1Min", True)
            ),
            "positionId": position_id,
        }

        return self._send_bundler_request("AddLiquidity", wallet, ordering, fee, to_sign)

    def add_liquidity_by_price(
        self,
        token0: GalaChainTokenClassKey | str,
        token1: GalaChainTokenClassKey | str,
        fee: int,
        tick_spacing: int,
        min_price: Decimal | str | int,
        max_price: Decimal | str | int,
        amount0_desired: Decimal | str | int,
        amount1_desired: Decimal | str | int,
        amount0_min: Decimal | str | int,
        amount1_min: Decimal | str | int,
        position_id: str,
        wallet_address: Optional[str] = None,
    ):
        wallet = validate_wallet_address(wallet_address or self.wallet_address)
        validate_fee(fee)
        validate_tick_spacing(tick_spacing)
        validate_numeric_amount(min_price, "minPrice", allow_zero=True)
        validate_numeric_amount(max_price, "maxPrice")

        token0_key = parse_token_class_key(token0)
        token1_key = parse_token_class_key(token1)
        ordering = get_token_ordering(
            token0_key,
            token1_key,
            True,
            [amount0_desired, amount0_min],
            [amount1_desired, amount1_min],
        )

        min_ticks = self.pool_service.calculate_ticks_for_price(min_price, tick_spacing)
        max_ticks = self.pool_service.calculate_ticks_for_price(max_price, tick_spacing)

        tick_lower = min_ticks if ordering.zero_for_one else -max_ticks
        tick_upper = max_ticks if ordering.zero_for_one else -min_ticks

        to_sign = {
            "token0": asdict(ordering.token0),
            "token1": asdict(ordering.token1),
            "fee": fee,
            "owner": wallet,
            "tickLower": tick_lower,
            "tickUpper": tick_upper,
            "amount0Desired": ordering.token0_attributes[0],
            "amount1Desired": ordering.token1_attributes[0],
            "amount0Min": ordering.token0_attributes[1],
            "amount1Min": ordering.token1_attributes[1],
            "positionId": position_id,
        }

        return self._send_bundler_request("AddLiquidity", wallet, ordering, fee, to_sign)

    def remove_liquidity(
        self,
        token0: GalaChainTokenClassKey | str,
        token1: GalaChainTokenClassKey | str,
        fee: int,
        tick_lower: int,
        tick_upper: int,
        amount: Decimal | str | int,
        amount0_min: Optional[Decimal | str | int] = None,
        amount1_min: Optional[Decimal | str | int] = None,
        position_id: str = "",
        wallet_address: Optional[str] = None,
    ):
        wallet = validate_wallet_address(wallet_address or self.wallet_address)
        validate_fee(fee)
        validate_tick_range(tick_lower, tick_upper)
        validate_numeric_amount(amount, "amount")

        token0_key = parse_token_class_key(token0)
        token1_key = parse_token_class_key(token1)
        ordering = get_token_ordering(
            token0_key,
            token1_key,
            True,
            [amount0_min or 0],
            [amount1_min or 0],
        )

        to_sign = {
            "token0": asdict(ordering.token0),
            "token1": asdict(ordering.token1),
            "fee": fee,
            "tickLower": tick_lower,
            "tickUpper": tick_upper,
            "amount": _decimal_to_string(validate_numeric_amount(amount, "amount")),
            "amount0Min": _decimal_to_string(
                validate_numeric_amount(ordering.token0_attributes[0], "amount0Min", True)
            ),
            "amount1Min": _decimal_to_string(
                validate_numeric_amount(ordering.token1_attributes[0], "amount1Min", True)
            ),
            "positionId": position_id,
        }

        return self._send_bundler_request("RemoveLiquidity", wallet, ordering, fee, to_sign)

    def collect_position_fees(
        self,
        token0: GalaChainTokenClassKey | str,
        token1: GalaChainTokenClassKey | str,
        fee: int,
        tick_lower: int,
        tick_upper: int,
        amount0_requested: Decimal | str | int,
        amount1_requested: Decimal | str | int,
        position_id: str,
        wallet_address: Optional[str] = None,
    ):
        wallet = validate_wallet_address(wallet_address or self.wallet_address)
        validate_fee(fee)
        validate_tick_range(tick_lower, tick_upper)
        validate_numeric_amount(amount0_requested, "amount0Requested", True)
        validate_numeric_amount(amount1_requested, "amount1Requested", True)

        token0_key = parse_token_class_key(token0)
        token1_key = parse_token_class_key(token1)
        ordering = get_token_ordering(
            token0_key,
            token1_key,
            True,
            [amount0_requested],
            [amount1_requested],
        )

        to_sign = {
            "token0": asdict(ordering.token0),
            "token1": asdict(ordering.token1),
            "fee": fee,
            "amount0Requested": _decimal_to_string(
                validate_numeric_amount(ordering.token0_attributes[0], "amount0Requested", True)
            ),
            "amount1Requested": _decimal_to_string(
                validate_numeric_amount(ordering.token1_attributes[0], "amount1Requested", True)
            ),
            "tickLower": tick_lower,
            "tickUpper": tick_upper,
            "positionId": position_id,
        }

        return self._send_bundler_request("CollectPositionFees", wallet, ordering, fee, to_sign)

    def calculate_optimal_position_size(
        self,
        token_amount: Decimal | str | int,
        spot_price: Decimal | str | int,
        lower_price: Decimal | str | int,
        upper_price: Decimal | str | int,
        token_decimals: int,
        other_token_decimals: int,
    ) -> Decimal:
        validate_numeric_amount(token_amount, "tokenAmount")
        validate_price_values(spot_price, lower_price, upper_price)
        validate_token_decimals(token_decimals, "tokenDecimals")
        validate_token_decimals(other_token_decimals, "otherTokenDecimals")

        token_amount_decimal = Decimal(str(token_amount))
        spot = Decimal(str(spot_price))
        lower = Decimal(str(lower_price))
        upper_str = str(upper_price)
        upper = Decimal(upper_str) if upper_str.lower() not in {"inf", "infinity"} else Decimal("1e18")

        liquidity_amount = (
            token_amount_decimal
            * (Decimal(10) ** (token_decimals - other_token_decimals))
            * spot.sqrt()
            * upper.sqrt()
            / (upper.sqrt() - spot.sqrt())
        )
        y_amount = liquidity_amount * (spot.sqrt() - lower.sqrt())
        untruncated = y_amount / (Decimal(10) ** (token_decimals - other_token_decimals))
        quantizer = Decimal(10) ** -other_token_decimals
        return max(untruncated.quantize(quantizer), Decimal(0))

    def _send_user_positions_request(self, endpoint: str, body: Mapping[str, object]) -> GetUserPositionsResponse:
        response = self.http_client.send_post_request(
            self.gateway_base_url,
            self.dex_contract_base_path,
            endpoint,
            body,
        )
        data = response.get("Data") if isinstance(response, dict) else None
        if not isinstance(data, dict):
            raise ValueError("Unexpected user positions response")
        positions_payload = data.get("positions") or []
        positions: List[LiquidityPosition] = []
        for entry in positions_payload:
            if not isinstance(entry, dict):
                continue
            positions.append(
                LiquidityPosition(
                    pool_hash=entry.get("poolHash", ""),
                    position_id=entry.get("positionId", ""),
                    token0_class_key=parse_token_class_key(entry.get("token0ClassKey")),
                    token1_class_key=parse_token_class_key(entry.get("token1ClassKey")),
                    token0_img=entry.get("token0Img", ""),
                    token1_img=entry.get("token1Img", ""),
                    token0_symbol=entry.get("token0Symbol", ""),
                    token1_symbol=entry.get("token1Symbol", ""),
                    fee=int(entry.get("fee", 0)),
                    liquidity=to_decimal(entry.get("liquidity")),
                    tick_lower=int(entry.get("tickLower", 0)),
                    tick_upper=int(entry.get("tickUpper", 0)),
                    created_at=entry.get("createdAt", ""),
                )
            )

        return GetUserPositionsResponse(positions=positions, bookmark=data.get("nextBookMark", ""))

    def _send_position_request(self, endpoint: str, body: Mapping[str, object]) -> GetPositionResult:
        response = self.http_client.send_post_request(
            self.gateway_base_url,
            self.dex_contract_base_path,
            endpoint,
            body,
        )
        data = response.get("Data") if isinstance(response, dict) else None
        if not isinstance(data, dict):
            raise ValueError("Unexpected position response")
        return GetPositionResult(
            fee=int(data.get("fee", 0)),
            fee_growth_inside0_last=to_decimal(data.get("feeGrowthInside0Last")),
            fee_growth_inside1_last=to_decimal(data.get("feeGrowthInside1Last")),
            liquidity=to_decimal(data.get("liquidity")),
            pool_hash=data.get("poolHash", ""),
            position_id=data.get("positionId", ""),
            tick_lower=int(data.get("tickLower", 0)),
            tick_upper=int(data.get("tickUpper", 0)),
            token0_class_key=parse_token_class_key(data.get("token0ClassKey")),
            token1_class_key=parse_token_class_key(data.get("token1ClassKey")),
            tokens_owed0=to_decimal(data.get("tokensOwed0")),
            tokens_owed1=to_decimal(data.get("tokensOwed1")),
        )

    def _send_bundler_request(
        self,
        method: str,
        wallet: str,
        ordering,
        fee: int,
        to_sign: Dict[str, object],
    ):
        token0_key = stringify_token_class_key(ordering.token0, "$")
        token1_key = stringify_token_class_key(ordering.token1, "$")

        pool_string = f"$pool${token0_key}${token1_key}${fee}"
        user_position_string = f"$userPosition${wallet}"
        token_balance0 = f"$tokenBalance${token0_key}${wallet}"
        token_balance1 = f"$tokenBalance${token1_key}${wallet}"
        token_balance0_pool = f"$tokenBalance${token0_key}${pool_string}"
        token_balance1_pool = f"$tokenBalance${token1_key}${pool_string}"

        strings_instructions = [
            pool_string,
            user_position_string,
            token_balance0,
            token_balance1,
            token_balance0_pool,
            token_balance1_pool,
        ]

        return self.bundler_service.send_bundler_request(method, to_sign, strings_instructions)
