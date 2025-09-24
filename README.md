# python-gswap-sdk

A Pythonic port of the official [GalaChain gSwap SDK](https://github.com/GalaChain/gswap-sdk).
The library focuses on read-only workflows such as price quoting, pool inspection and
retrieving wallet balances while keeping the public API and terminology close to the
TypeScript original. All monetary values are represented with `decimal.Decimal` to avoid
floating point precision issues.

## Installation

The project is published as a standard Python package. Install it with pip:

```bash
pip install python-gswap-sdk
```

## Quick start

```python
from gswap_sdk import GSwap

client = GSwap()
quote = client.quoting.quote_exact_input(
    "GALA|Unit|none|none",  # token you are selling
    "GUSDC|Unit|none|none",  # token you want to buy
    "100",                   # amount of input token (string/Decimal/numeric)
)

print("Best out amount:", quote.out_token_amount)
print("Price impact:", quote.price_impact)
```

### Inspecting pools

```python
pool = client.pools.get_pool_data(
    "GALA|Unit|none|none",
    "GUSDC|Unit|none|none",
    500,
)

spot_price = client.pools.calculate_spot_price(
    "GALA|Unit|none|none",
    "GUSDC|Unit|none|none",
    pool.sqrt_price,
)

print("Spot price:", spot_price)
```

### Listing wallet assets

```python
assets = client.assets.get_user_assets("eth|1234567890abcdef", page=1, limit=20)
for token in assets.tokens:
    print(token.symbol, token.quantity)
```

## Design goals

- **Decimal everywhere** – financial amounts use `decimal.Decimal` internally and in the
  public data structures.
- **Par with the TypeScript SDK** – naming mirrors the official JavaScript
  implementation so switching languages requires minimal effort.
- **Reusable components** – shared helpers such as token parsing and validation live in
  dedicated modules that can be imported independently.

## Packaging notes

The project ships a `pyproject.toml` definition and is ready to be built with the
standard `python -m build` workflow. Automated tests are implemented with `pytest` and
exercise key helpers such as token parsing, validation and quote decoding.

## Contributing

1. Fork the repository and create a feature branch.
2. Install dependencies using `pip install -r requirements-dev.txt` (coming soon) or the
   minimal runtime requirements via `pip install -e .`.
3. Run the test suite with `pytest` before opening a pull request.

Please ensure any contribution keeps the public API stable and avoids reintroducing
floating point math for monetary calculations.
