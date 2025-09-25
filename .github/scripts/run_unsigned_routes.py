#!/usr/bin/env python3
"""Run smoke tests against unsigned gSwap routes."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gswap_sdk import GSwap


@dataclass(slots=True)
class RouteInputs:
    input_token: str
    output_token: str
    input_amount: Decimal
    pool_fee: int
    wallet_address: str
    asset_limit: int
    position_limit: int


def _env_decimal(name: str, default: str) -> Decimal:
    return Decimal(os.environ.get(name, default))


def _env_int(name: str, default: str) -> int:
    return int(os.environ.get(name, default))


def _load_inputs() -> RouteInputs:
    return RouteInputs(
        input_token=os.environ.get("INPUT_TOKEN", "GALA|Unit|none|none"),
        output_token=os.environ.get("OUTPUT_TOKEN", "GUSDC|Unit|none|none"),
        input_amount=_env_decimal("INPUT_AMOUNT", "1"),
        pool_fee=_env_int("POOL_FEE", "500"),
        wallet_address=os.environ.get(
            "WALLET_ADDRESS", "eth|5AEDA56215b167893e80B4fE645BA6d5Bab767DE"
        ),
        asset_limit=_env_int("ASSET_LIMIT", "5"),
        position_limit=_env_int("POSITION_LIMIT", "5"),
    )


def _format_decimal(value: Decimal, places: int = 6) -> str:
    if value.is_infinite():
        return "∞" if value > 0 else "-∞"
    quant = Decimal(1).scaleb(-places)
    rounded = value.quantize(quant, rounding=ROUND_HALF_UP)
    return format(rounded.normalize(), "f")


def _summarise_assets(result) -> tuple[str, str]:
    if not result.tokens:
        return "0", "None"
    top = max(result.tokens, key=lambda token: token.quantity)
    return _format_decimal(top.quantity, places=4), top.symbol or "Unknown"


def _summarise_positions(result) -> tuple[str, str]:
    if not result.positions:
        return "0", "None"
    first = result.positions[0]
    pair = f"{first.token0_symbol or first.token0_class_key.collection}/"
    pair += f"{first.token1_symbol or first.token1_class_key.collection}"
    summary = (
        f"{pair} fee {first.fee} bps"
        f" (ticks {first.tick_lower} → {first.tick_upper})"
    )
    return str(len(result.positions)), summary


def main() -> None:
    inputs = _load_inputs()
    client = GSwap()

    quote = client.quoting.quote_exact_input(
        inputs.input_token, inputs.output_token, inputs.input_amount
    )

    pool = client.pools.get_pool_data(
        inputs.input_token, inputs.output_token, inputs.pool_fee
    )
    spot_price = client.pools.calculate_spot_price(
        inputs.input_token, inputs.output_token, pool.sqrt_price
    )

    assets = client.assets.get_user_assets(
        inputs.wallet_address, limit=inputs.asset_limit
    )
    positions = client.positions.get_user_positions(
        inputs.wallet_address, limit=inputs.position_limit
    )

    top_asset_quantity, top_asset_symbol = _summarise_assets(assets)
    position_count, position_summary = _summarise_positions(positions)

    outputs = {
        "quote_out_amount": _format_decimal(quote.out_token_amount),
        "quote_price_impact_pct": _format_decimal(quote.price_impact * Decimal(100), places=4),
        "quote_current_price": _format_decimal(quote.current_price),
        "quote_new_price": _format_decimal(quote.new_price),
        "quote_fee_tier": str(quote.fee_tier),
        "pool_liquidity": _format_decimal(pool.liquidity, places=4),
        "pool_sqrt_price": _format_decimal(pool.sqrt_price),
        "pool_spot_price": _format_decimal(spot_price),
        "pool_tick_spacing": str(pool.tick_spacing),
        "pool_fee": str(pool.fee),
        "assets_count": str(assets.count),
        "assets_top_quantity": top_asset_quantity,
        "assets_top_symbol": top_asset_symbol,
        "positions_count": position_count,
        "positions_first_summary": position_summary,
    }

    for key, value in outputs.items():
        print(f"{key}: {value}")

    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as handle:
            for key, value in outputs.items():
                handle.write(f"{key}={value}\n")


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
