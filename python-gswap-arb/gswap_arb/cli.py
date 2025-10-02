"""Command line entry point for the python-gswap-arb project."""

from __future__ import annotations

import argparse
from decimal import Decimal
from typing import Sequence

from gswap_arb import configure_decimal_context


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gswap-arb",
        description=(
            "Bootstrap gSwap arbitrage experiments while preserving decimal precision."
        ),
    )
    parser.add_argument(
        "--precision",
        type=int,
        default=28,
        help="Decimal precision used for all downstream strategy calculations.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not submit transactions, only log detected opportunities.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    configure_decimal_context(precision=args.precision)

    reference_value = Decimal("1") / Decimal("3")
    print(
        "gswap-arb initialized (precision=%d, sample=%s, dry_run=%s)" % (
            args.precision,
            reference_value,
            args.dry_run,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI execution helper
    raise SystemExit(main())
