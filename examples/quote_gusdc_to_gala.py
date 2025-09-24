"""Example quoting from GUSDC to GALA using the Python SDK."""
from decimal import Decimal

from gswap_sdk import GSwap


def main() -> None:
    client = GSwap()
    quote = client.quoting.quote_exact_input(
        "GUSDC|Unit|none|none",
        "GALA|Unit|none|none",
        Decimal("100"),
    )

    print("Best fee tier:", quote.fee_tier)
    print("Input amount:", quote.in_token_amount)
    print("Estimated output:", quote.out_token_amount)
    print("Price impact:", quote.price_impact)


if __name__ == "__main__":  # pragma: no cover - manual usage
    main()
