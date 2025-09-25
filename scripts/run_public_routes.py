#!/usr/bin/env python3
"""Execute read-only gSwap routes and record their results.

This helper calls the public gSwap SDK routes that do not require a signer
and stores both machine readable JSON data and a Markdown summary suitable for
pull request comments.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List

from gswap_sdk import GSwap
from gswap_sdk.token import stringify_token_class_key


@dataclass(slots=True)
class QuoteSummary:
    direction: str
    token_in: str
    token_out: str
    amount: str
    amount_other: str
    fee_tier: int
    price_impact_pct: str
    current_price: str
    new_price: str


@dataclass(slots=True)
class PoolSummary:
    token0: str
    token1: str
    fee: int
    liquidity: str
    sqrt_price: str
    spot_price: str
    tick_spacing: int


@dataclass(slots=True)
class AssetSummary:
    wallet: str
    page: int
    limit: int
    count: int
    tokens: List[Dict[str, Any]]


@dataclass(slots=True)
class PositionSummary:
    wallet: str
    limit: int | None
    count: int
    bookmark: str
    positions: List[Dict[str, Any]]


def _decimal_from_env(value: str, *, name: str) -> Decimal:
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError) as exc:  # pragma: no cover - defensive
        raise ValueError(f"Invalid decimal value for {name}: {value!r}") from exc


def _format_decimal(value: Decimal, *, places: int = 6) -> str:
    quant = Decimal(1).scaleb(-places)
    rounded = value.quantize(quant, rounding=ROUND_HALF_UP)
    return format(rounded.normalize(), "f")


def _format_percentage(value: Decimal, *, places: int = 4) -> str:
    return _format_decimal(value * Decimal(100), places=places)


def _summarise_quote(direction: str, config: Dict[str, str], quote) -> QuoteSummary:
    if direction == "exact_input":
        amount = _format_decimal(quote.in_token_amount)
        other_amount = _format_decimal(quote.out_token_amount)
    else:
        amount = _format_decimal(quote.out_token_amount)
        other_amount = _format_decimal(quote.in_token_amount)

    return QuoteSummary(
        direction=direction,
        token_in=config["token_in"],
        token_out=config["token_out"],
        amount=amount,
        amount_other=other_amount,
        fee_tier=quote.fee_tier,
        price_impact_pct=_format_percentage(quote.price_impact),
        current_price=_format_decimal(quote.current_price),
        new_price=_format_decimal(quote.new_price),
    )


def _summarise_pool(config: Dict[str, str], pool) -> PoolSummary:
    spot_price = config.get("spot_price_token_in")
    if spot_price is None or spot_price == config["token_out"]:
        spot = _format_decimal(pool.sqrt_price ** 2)
    else:
        spot = _format_decimal(Decimal(1) / (pool.sqrt_price ** 2))

    return PoolSummary(
        token0=pool.token0.replace("$", "|"),
        token1=pool.token1.replace("$", "|"),
        fee=pool.fee,
        liquidity=_format_decimal(pool.liquidity),
        sqrt_price=_format_decimal(pool.sqrt_price),
        spot_price=spot,
        tick_spacing=pool.tick_spacing,
    )


def _summarise_assets(wallet: str, page: int, limit: int, assets) -> AssetSummary:
    tokens: List[Dict[str, Any]] = []
    for token in assets.tokens[:limit]:
        tokens.append(
            {
                "symbol": token.symbol,
                "name": token.name,
                "quantity": _format_decimal(token.quantity),
                "decimals": token.decimals,
                "verify": token.verify,
            }
        )
    return AssetSummary(wallet=wallet, page=page, limit=limit, count=assets.count, tokens=tokens)


def _summarise_positions(wallet: str, limit: int | None, positions) -> PositionSummary:
    entries: List[Dict[str, Any]] = []
    for position in positions.positions[: limit or None]:
        entries.append(
            {
                "position_id": position.position_id,
                "pool_hash": position.pool_hash,
                "token0": stringify_token_class_key(position.token0_class_key, separator="|"),
                "token1": stringify_token_class_key(position.token1_class_key, separator="|"),
                "fee": position.fee,
                "tick_lower": position.tick_lower,
                "tick_upper": position.tick_upper,
                "liquidity": _format_decimal(position.liquidity),
            }
        )
    return PositionSummary(
        wallet=wallet,
        limit=limit,
        count=len(positions.positions),
        bookmark=positions.bookmark,
        positions=entries,
    )


def build_markdown(results: Dict[str, Any]) -> str:
    lines: List[str] = [
        "<!-- gswap-route-tests -->",
        "### gSwap Public Route Checks",
        "",
    ]

    quote_in = results.get("quote_exact_input")
    if isinstance(quote_in, dict) and quote_in.get("status") == "success":
        data = quote_in["data"]
        lines.extend(
            [
                "#### Quote – Exact Input",
                f"- Input: `{data['token_in']}` → `{data['token_out']}`",
                f"- Input Amount: {data['amount']}",
                f"- Estimated Output: {data['amount_other']}",
                f"- Fee Tier: {data['fee_tier']} bps",
                f"- Price Impact: {data['price_impact_pct']}%",
                f"- Current Price: {data['current_price']}",
                f"- New Price: {data['new_price']}",
                "",
            ]
        )
    else:
        error = quote_in.get("error") if isinstance(quote_in, dict) else "Unknown error"
        lines.extend(["#### Quote – Exact Input", f"- ❌ Error: {error}", ""])

    quote_out = results.get("quote_exact_output")
    if isinstance(quote_out, dict) and quote_out.get("status") == "success":
        data = quote_out["data"]
        lines.extend(
            [
                "#### Quote – Exact Output",
                f"- Output: `{data['token_out']}` ← `{data['token_in']}`",
                f"- Output Amount: {data['amount']}",
                f"- Required Input: {data['amount_other']}",
                f"- Fee Tier: {data['fee_tier']} bps",
                f"- Price Impact: {data['price_impact_pct']}%",
                f"- Current Price: {data['current_price']}",
                f"- New Price: {data['new_price']}",
                "",
            ]
        )
    else:
        error = quote_out.get("error") if isinstance(quote_out, dict) else "Unknown error"
        lines.extend(["#### Quote – Exact Output", f"- ❌ Error: {error}", ""])

    pool = results.get("pool_data")
    if isinstance(pool, dict) and pool.get("status") == "success":
        data = pool["data"]
        lines.extend(
            [
                "#### Pool Data",
                f"- Pair: `{data['token0']}` / `{data['token1']}`",
                f"- Fee Tier: {data['fee']} bps",
                f"- Liquidity: {data['liquidity']}",
                f"- Sqrt Price: {data['sqrt_price']}",
                f"- Spot Price (`{data['token0']}`→`{data['token1']}`): {data['spot_price']}",
                f"- Tick Spacing: {data['tick_spacing']}",
                "",
            ]
        )
    else:
        error = pool.get("error") if isinstance(pool, dict) else "Unknown error"
        lines.extend(["#### Pool Data", f"- ❌ Error: {error}", ""])

    assets = results.get("assets")
    if isinstance(assets, dict) and assets.get("status") == "success":
        data = assets["data"]
        lines.extend(
            [
                "#### Wallet Assets",
                f"- Wallet: `{data['wallet']}`",
                f"- Page / Limit: {data['page']} / {data['limit']}",
                f"- Token Types: {data['count']}",
            ]
        )
        if data["tokens"]:
            lines.append("- Top Tokens:")
            for token in data["tokens"]:
                lines.append(
                    f"  - {token['symbol']}: {token['quantity']} (decimals: {token['decimals']}, verified: {token['verify']})"
                )
        else:
            lines.append("- Top Tokens: _none returned in page_")
        lines.append("")
    else:
        error = assets.get("error") if isinstance(assets, dict) else "Unknown error"
        lines.extend(["#### Wallet Assets", f"- ❌ Error: {error}", ""])

    positions = results.get("positions")
    if isinstance(positions, dict) and positions.get("status") == "success":
        data = positions["data"]
        lines.extend(
            [
                "#### Wallet Positions",
                f"- Wallet: `{data['wallet']}`",
                f"- Returned Positions: {data['count']}",
                f"- Bookmark: `{data['bookmark']}`",
            ]
        )
        if data["positions"]:
            lines.append("- Sample Positions:")
            for position in data["positions"]:
                lines.append(
                    "  - "
                    + f"ID `{position['position_id']}` | Pool `{position['token0']}`/`{position['token1']}` | "
                    + f"Fee {position['fee']} | Tick [{position['tick_lower']}, {position['tick_upper']}] | "
                    + f"Liquidity {position['liquidity']}"
                )
        else:
            lines.append("- Sample Positions: _none returned_")
        lines.append("")
    else:
        error = positions.get("error") if isinstance(positions, dict) else "Unknown error"
        lines.extend(["#### Wallet Positions", f"- ❌ Error: {error}", ""])

    lines.append("<sub>Generated automatically by python-gswap-sdk CI.</sub>")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-output", required=True, help="Path to write JSON results")
    parser.add_argument("--markdown-output", required=True, help="Path to write Markdown summary")
    args = parser.parse_args()

    client = GSwap()

    config = {
        "quote_input_token": os.environ.get("QUOTE_INPUT_TOKEN", "GALA|Unit|none|none"),
        "quote_output_token": os.environ.get("QUOTE_OUTPUT_TOKEN", "GUSDC|Unit|none|none"),
        "quote_input_amount": os.environ.get("QUOTE_INPUT_AMOUNT", "1"),
        "quote_output_amount": os.environ.get("QUOTE_OUTPUT_AMOUNT", "1"),
        "pool_token_a": os.environ.get("POOL_TOKEN_A", "GALA|Unit|none|none"),
        "pool_token_b": os.environ.get("POOL_TOKEN_B", "GUSDC|Unit|none|none"),
        "pool_fee": int(os.environ.get("POOL_FEE", "500")),
        "assets_wallet": os.environ.get("ASSETS_WALLET_ADDRESS", "eth|90F79bf6EB2c4f870365E785982E1f101E93b906"),
        "assets_page": int(os.environ.get("ASSETS_PAGE", "1")),
        "assets_limit": int(os.environ.get("ASSETS_LIMIT", "5")),
        "positions_wallet": os.environ.get("POSITIONS_WALLET_ADDRESS", "eth|90F79bf6EB2c4f870365E785982E1f101E93b906"),
        "positions_limit": os.environ.get("POSITIONS_LIMIT", "5"),
    }

    results: Dict[str, Any] = {"config": config}

    try:
        amount_in = _decimal_from_env(config["quote_input_amount"], name="QUOTE_INPUT_AMOUNT")
        quote_in = client.quoting.quote_exact_input(
            config["quote_input_token"], config["quote_output_token"], amount_in
        )
    except Exception as exc:  # pragma: no cover - network error reporting
        results["quote_exact_input"] = {"status": "error", "error": str(exc)}
    else:
        summary = _summarise_quote(
            "exact_input",
            {"token_in": config["quote_input_token"], "token_out": config["quote_output_token"]},
            quote_in,
        )
        results["quote_exact_input"] = {"status": "success", "data": asdict(summary)}

    try:
        amount_out = _decimal_from_env(config["quote_output_amount"], name="QUOTE_OUTPUT_AMOUNT")
        quote_out = client.quoting.quote_exact_output(
            config["quote_input_token"], config["quote_output_token"], amount_out
        )
    except Exception as exc:  # pragma: no cover - network error reporting
        results["quote_exact_output"] = {"status": "error", "error": str(exc)}
    else:
        summary = _summarise_quote(
            "exact_output",
            {"token_in": config["quote_input_token"], "token_out": config["quote_output_token"]},
            quote_out,
        )
        results["quote_exact_output"] = {"status": "success", "data": asdict(summary)}

    try:
        pool = client.pools.get_pool_data(config["pool_token_a"], config["pool_token_b"], config["pool_fee"])
    except Exception as exc:  # pragma: no cover - network error reporting
        results["pool_data"] = {"status": "error", "error": str(exc)}
    else:
        summary = _summarise_pool(
            {
                "token_in": config["pool_token_a"],
                "token_out": config["pool_token_b"],
                "spot_price_token_in": config["pool_token_a"],
            },
            pool,
        )
        results["pool_data"] = {"status": "success", "data": asdict(summary)}

    try:
        assets = client.assets.get_user_assets(
            config["assets_wallet"], page=config["assets_page"], limit=config["assets_limit"]
        )
    except Exception as exc:  # pragma: no cover - network error reporting
        results["assets"] = {"status": "error", "error": str(exc)}
    else:
        summary = _summarise_assets(config["assets_wallet"], config["assets_page"], config["assets_limit"], assets)
        results["assets"] = {"status": "success", "data": asdict(summary)}

    positions_limit_env = config.get("positions_limit")
    positions_limit = int(positions_limit_env) if positions_limit_env else None
    try:
        positions = client.positions.get_user_positions(
            config["positions_wallet"], limit=positions_limit
        )
    except Exception as exc:  # pragma: no cover - network error reporting
        results["positions"] = {"status": "error", "error": str(exc)}
    else:
        summary = _summarise_positions(config["positions_wallet"], positions_limit, positions)
        results["positions"] = {"status": "success", "data": asdict(summary)}

    os.makedirs(os.path.dirname(os.path.abspath(args.json_output)), exist_ok=True)
    with open(args.json_output, "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2)

    markdown = build_markdown(results)
    os.makedirs(os.path.dirname(os.path.abspath(args.markdown_output)), exist_ok=True)
    with open(args.markdown_output, "w", encoding="utf-8") as handle:
        handle.write(markdown)


if __name__ == "__main__":  # pragma: no cover - script entry point
    main()
