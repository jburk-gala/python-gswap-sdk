#!/usr/bin/env python3
"""Run a small suite of read-only gSwap checks used in CI."""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from gswap_sdk import GSwap
from gswap_sdk.token import get_token_ordering, parse_token_class_key


@dataclass
class RouteResult:
    name: str
    status: str
    details: Mapping[str, Any]
    error: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "details": dict(self.details),
        }
        if self.error is not None:
            payload["error"] = self.error
        return payload


def decimal_to_string(value: Decimal, *, places: int = 6) -> str:
    """Return a nicely formatted decimal string."""

    quant = Decimal(1).scaleb(-places)
    rounded = value.quantize(quant, rounding=ROUND_HALF_UP)
    return format(rounded.normalize(), "f")


def stringify_pair(token_a: str, token_b: str) -> str:
    return f"{token_a} → {token_b}"


def build_pool_request_body(token_a: str, token_b: str, fee: int) -> Mapping[str, Any]:
    first = parse_token_class_key(token_a)
    second = parse_token_class_key(token_b)
    ordering = get_token_ordering(first, second, False)

    return {
        "token0": ordering.token0.to_payload(),
        "token1": ordering.token1.to_payload(),
        "fee": int(fee),
    }


def run_quote_exact_input(
    client: GSwap, token_in: str, token_out: str, amount_in: Decimal
) -> RouteResult:
    try:
        quote = client.quoting.quote_exact_input(token_in, token_out, amount_in)
    except Exception as exc:  # pragma: no cover - defensive
        return RouteResult(
            name="QuoteExactInput",
            status="error",
            details={
                "token_pair": stringify_pair(token_in, token_out),
                "amount_in": str(amount_in),
            },
            error=str(exc),
        )

    return RouteResult(
        name="QuoteExactInput",
        status="success",
        details={
            "token_pair": stringify_pair(token_in, token_out),
            "amount_in": decimal_to_string(amount_in),
            "estimated_output": decimal_to_string(quote.out_token_amount),
            "price_impact_pct": decimal_to_string(quote.price_impact * Decimal(100), places=4),
            "current_price": decimal_to_string(quote.current_price),
            "new_price": decimal_to_string(quote.new_price),
            "fee_tier": quote.fee_tier,
        },
    )


def run_quote_exact_output(
    client: GSwap, token_in: str, token_out: str, amount_out: Decimal
) -> RouteResult:
    try:
        quote = client.quoting.quote_exact_output(token_in, token_out, amount_out)
    except Exception as exc:  # pragma: no cover - defensive
        return RouteResult(
            name="QuoteExactOutput",
            status="error",
            details={
                "token_pair": stringify_pair(token_in, token_out),
                "amount_out": str(amount_out),
            },
            error=str(exc),
        )

    return RouteResult(
        name="QuoteExactOutput",
        status="success",
        details={
            "token_pair": stringify_pair(token_in, token_out),
            "amount_out": decimal_to_string(amount_out),
            "required_input": decimal_to_string(quote.in_token_amount),
            "price_impact_pct": decimal_to_string(quote.price_impact * Decimal(100), places=4),
            "current_price": decimal_to_string(quote.current_price),
            "new_price": decimal_to_string(quote.new_price),
            "fee_tier": quote.fee_tier,
        },
    )


def run_pool_data(
    client: GSwap, token_a: str, token_b: str, fee: int
) -> RouteResult:
    body = build_pool_request_body(token_a, token_b, fee)
    try:
        payload = client._http_client.send_post_request(  # type: ignore[attr-defined]
            client.gateway_base_url,
            client.dex_contract_base_path,
            "/GetPoolData",
            body,
        )
    except Exception as exc:  # pragma: no cover - defensive
        return RouteResult(
            name="GetPoolData",
            status="error",
            details={
                "token_pair": stringify_pair(token_a, token_b),
                "fee": fee,
            },
            error=str(exc),
        )

    data = payload.get("Data") if isinstance(payload, Mapping) else None
    if not isinstance(data, Mapping):
        return RouteResult(
            name="GetPoolData",
            status="error",
            details={"token_pair": stringify_pair(token_a, token_b), "fee": fee},
            error="Unexpected response structure",
        )

    try:
        liquidity = Decimal(str(data.get("liquidity", "0")))
        sqrt_price = Decimal(str(data.get("sqrtPrice", "0")))
    except (ArithmeticError, ValueError, TypeError, InvalidOperation) as exc:  # pragma: no cover - defensive
        return RouteResult(
            name="GetPoolData",
            status="error",
            details={"token_pair": stringify_pair(token_a, token_b), "fee": fee},
            error=f"Failed to parse pool data: {exc}",
        )

    return RouteResult(
        name="GetPoolData",
        status="success",
        details={
            "token_pair": stringify_pair(token_a, token_b),
            "fee": fee,
            "liquidity": decimal_to_string(liquidity, places=8),
            "sqrt_price": decimal_to_string(sqrt_price, places=18),
            "tick_spacing": data.get("tickSpacing"),
        },
    )


def run_user_assets(
    client: GSwap, wallet_address: str, page: int, limit: int
) -> RouteResult:
    try:
        result = client.assets.get_user_assets(wallet_address, page=page, limit=limit)
    except Exception as exc:  # pragma: no cover - defensive
        return RouteResult(
            name="GetUserAssets",
            status="error",
            details={"wallet_address": wallet_address, "page": page, "limit": limit},
            error=str(exc),
        )

    tokens_preview: List[str] = []
    for balance in result.tokens[: min(3, len(result.tokens))]:
        tokens_preview.append(f"{balance.symbol or balance.name} ({decimal_to_string(balance.quantity)})")

    return RouteResult(
        name="GetUserAssets",
        status="success",
        details={
            "wallet_address": wallet_address,
            "page": page,
            "limit": limit,
            "token_count": result.count,
            "sample_tokens": tokens_preview,
        },
    )


def run_user_positions(client: GSwap, wallet_address: str) -> RouteResult:
    try:
        result = client.positions.get_user_positions(wallet_address)
    except Exception as exc:  # pragma: no cover - defensive
        return RouteResult(
            name="GetUserPositions",
            status="error",
            details={"wallet_address": wallet_address},
            error=str(exc),
        )

    return RouteResult(
        name="GetUserPositions",
        status="success",
        details={
            "wallet_address": wallet_address,
            "position_count": len(result.positions),
            "next_bookmark": result.bookmark,
        },
    )


def render_markdown(results: Iterable[RouteResult]) -> str:
    lines = ["<!-- gswap-unsigned-routes -->", "### gSwap unsigned route checks", ""]
    status_icon = {"success": "✅", "error": "❌"}

    for result in results:
        icon = status_icon.get(result.status, "❔")
        lines.append(f"{icon} **{result.name}**")
        for key, value in result.details.items():
            if isinstance(value, list):
                if not value:
                    lines.append(f"  - {key.replace('_', ' ').title()}: _none_")
                    continue
                lines.append(f"  - {key.replace('_', ' ').title()}:")
                for entry in value:
                    lines.append(f"    - {entry}")
            else:
                lines.append(f"  - {key.replace('_', ' ').title()}: {value}")
        if result.error:
            lines.append(f"  - Error: `{result.error}`")
        lines.append("")

    lines.append("<sub>Generated by python-gswap-sdk CI</sub>")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run read-only gSwap route checks")
    parser.add_argument("--input-token", default=os.environ.get("INPUT_TOKEN", "GALA|Unit|none|none"))
    parser.add_argument("--output-token", default=os.environ.get("OUTPUT_TOKEN", "GUSDC|Unit|none|none"))
    parser.add_argument(
        "--input-amount",
        default=os.environ.get("INPUT_AMOUNT", "1"),
        help="Amount of the input token to use for exact input quotes",
    )
    parser.add_argument(
        "--output-amount",
        default=os.environ.get("OUTPUT_AMOUNT", "1"),
        help="Amount of the output token to request for exact output quotes",
    )
    parser.add_argument(
        "--pool-fee",
        type=int,
        default=int(os.environ.get("POOL_FEE", "500")),
        help="Pool fee tier (in bps) to request from the GetPoolData route",
    )
    parser.add_argument(
        "--wallet-address",
        default=os.environ.get("WALLET_ADDRESS", "eth|742d35Cc6634C0532925a3b844Bc454e4438f44e"),
        help="Wallet address used for asset and position queries",
    )
    parser.add_argument(
        "--assets-page",
        type=int,
        default=int(os.environ.get("ASSETS_PAGE", "1")),
        help="Page number for asset pagination",
    )
    parser.add_argument(
        "--assets-limit",
        type=int,
        default=int(os.environ.get("ASSETS_LIMIT", "5")),
        help="Number of assets to fetch from the backend",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path(os.environ.get("UNSIGNED_ROUTES_JSON", "unsigned_routes.json")),
        help="Where to store the JSON result payload",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=Path(os.environ.get("UNSIGNED_ROUTES_MARKDOWN", "unsigned_routes.md")),
        help="Where to store the markdown summary",
    )
    args = parser.parse_args()

    client = GSwap()

    amount_in = Decimal(str(args.input_amount))
    amount_out = Decimal(str(args.output_amount))

    checks: List[RouteResult] = []
    checks.append(run_quote_exact_input(client, args.input_token, args.output_token, amount_in))
    checks.append(run_quote_exact_output(client, args.input_token, args.output_token, amount_out))
    checks.append(run_pool_data(client, args.input_token, args.output_token, args.pool_fee))
    checks.append(run_user_assets(client, args.wallet_address, args.assets_page, args.assets_limit))
    checks.append(run_user_positions(client, args.wallet_address))

    args.json_output.write_text(json.dumps([entry.as_dict() for entry in checks], indent=2), encoding="utf-8")
    args.markdown_output.write_text(render_markdown(checks), encoding="utf-8")

    print(args.markdown_output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
