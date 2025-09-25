#!/usr/bin/env python3
"""Run gSwap read-only route checks and emit CI-friendly output."""
from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Iterable, List

from gswap_sdk import GSwap
from gswap_sdk.types.sdk_results import GetUserAssetsResult


@dataclass(slots=True)
class RouteCheckResult:
    comment: str
    summary: str


def _env_decimal(name: str, default: str) -> Decimal:
    try:
        return Decimal(os.environ.get(name, default))
    except InvalidOperation as exc:  # pragma: no cover - defensive
        raise SystemExit(f"Invalid decimal value for {name}: {os.environ.get(name)}") from exc


def _format_decimal(value: Decimal, places: int = 6) -> str:
    quant = Decimal(1).scaleb(-places)
    try:
        quantized = value.quantize(quant, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):  # pragma: no cover - defensive
        quantized = value
    normalized = quantized.normalize()
    text = format(normalized, "f")
    if text == "-0":
        return "0"
    return text


def _format_large_decimal(value: Decimal) -> str:
    if value == value.to_integral():
        return f"{int(value):,}"
    return _format_decimal(value)


def _format_assets(assets: GetUserAssetsResult, max_items: int = 5) -> str:
    tokens = list(assets.tokens)[:max_items]
    if not tokens:
        return "- No token balances returned."

    lines: List[str] = []
    for token in tokens:
        quantity = _format_decimal(token.quantity, places=6)
        lines.append(
            f"- **{token.symbol or token.name}**: {quantity} (decimals: {token.decimals})"
        )
    if assets.count > len(tokens):
        lines.append(f"- …and {assets.count - len(tokens)} more tokens")
    return "\n".join(lines)


def _format_positions(
    positions: Iterable,
    max_items: int = 3,
) -> str:
    positions_list = list(positions)
    if not positions_list:
        return "- No on-chain liquidity positions reported."

    lines: List[str] = []
    for position in positions_list[:max_items]:
        liquidity = _format_large_decimal(position.liquidity)
        lines.append(
            "- Position ``{pos}`` ({sym0}/{sym1}, fee {fee} bps) ticks [{lower}, {upper}], "
            "liquidity {liq}".format(
                pos=position.position_id,
                sym0=position.token0_symbol or position.token0_class_key.collection,
                sym1=position.token1_symbol or position.token1_class_key.collection,
                fee=position.fee,
                lower=position.tick_lower,
                upper=position.tick_upper,
                liq=liquidity,
            )
        )

    if len(positions_list) > max_items:
        lines.append(f"- …and {len(positions_list) - max_items} more positions")

    return "\n".join(lines)


def run_checks() -> RouteCheckResult:
    input_token = os.environ.get("INPUT_TOKEN", "GALA|Unit|none|none")
    output_token = os.environ.get("OUTPUT_TOKEN", "GUSDC|Unit|none|none")
    fee_tier = int(os.environ.get("FEE_TIER", "500"))

    input_amount = _env_decimal("INPUT_AMOUNT", "1")
    output_amount = _env_decimal("OUTPUT_AMOUNT", "0.5")

    wallet_address = os.environ.get(
        "WALLET_ADDRESS", "eth|6cd13b1c31B4E489788F61f2dbf854509D608F42"
    )
    asset_limit = int(os.environ.get("ASSET_LIMIT", "5"))
    position_limit = int(os.environ.get("POSITION_LIMIT", "5"))

    client = GSwap()

    quote_exact_input = client.quoting.quote_exact_input(
        input_token, output_token, input_amount, fee=fee_tier
    )
    quote_exact_output = client.quoting.quote_exact_output(
        input_token, output_token, output_amount, fee=fee_tier
    )

    pool_data = client.pools.get_pool_data(input_token, output_token, fee_tier)

    assets = client.assets.get_user_assets(wallet_address, page=1, limit=asset_limit)
    positions_response = client.positions.get_user_positions(wallet_address, limit=position_limit)

    assets_section = _format_assets(assets)
    positions_section = _format_positions(positions_response.positions, max_items=position_limit)

    comment_lines = [
        "<!-- gswap-readonly -->",
        "### gSwap Read-only Route Verification",
        "",
        "**Quoting**",
        f"- Exact input {input_amount} `{input_token}` → {_format_decimal(quote_exact_input.out_token_amount)} `{output_token}`",
        f"- Exact output {output_amount} `{output_token}` requires {_format_decimal(quote_exact_output.in_token_amount)} `{input_token}`",
        f"- Price impact: {_format_decimal(quote_exact_input.price_impact * Decimal(100), places=4)}%",
        f"- Current price: {_format_decimal(quote_exact_input.current_price)}",
        f"- New price: {_format_decimal(quote_exact_input.new_price)}",
        "",
        "**Pool Data**",
        f"- Liquidity: {_format_large_decimal(pool_data.liquidity)}",
        f"- Gross liquidity: {_format_large_decimal(pool_data.gross_pool_liquidity)}",
        f"- Sqrt price: {_format_decimal(pool_data.sqrt_price)}",
        f"- Tick spacing: {pool_data.tick_spacing}",
        f"- Protocol fees token0/token1: {_format_decimal(pool_data.protocol_fees_token0)} / {_format_decimal(pool_data.protocol_fees_token1)}",
        "",
        f"**Assets for `{wallet_address}`**",
        assets_section,
        "",
        f"**Positions for `{wallet_address}`**",
        positions_section,
        "",
        "<sub>Generated by python-gswap-sdk CI</sub>",
    ]

    summary_lines = [
        "### gSwap Read-only Route Verification",
        f"* Quoted {input_amount} {input_token} → {output_token} (fee {fee_tier} bps)",
        f"* Pool liquidity: {_format_large_decimal(pool_data.liquidity)}",
        f"* Assets returned: {assets.count}",
        f"* Positions returned: {len(positions_response.positions)}",
    ]

    return RouteCheckResult(comment="\n".join(comment_lines), summary="\n".join(summary_lines))


def main() -> None:
    result = run_checks()

    print(result.summary)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(result.summary)
            handle.write("\n")

    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as handle:
            handle.write("comment_body<<GSWAP\n")
            handle.write(result.comment)
            handle.write("\nGSWAP\n")


if __name__ == "__main__":
    main()
