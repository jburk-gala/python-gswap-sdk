"""Token swap operations."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Mapping, Optional

from .bundler import Bundler
from .token import GalaChainTokenClassKey, get_token_ordering, parse_token_class_key, stringify_token_class_key
from .validation import validate_fee, validate_numeric_amount, validate_wallet_address

MIN_SQRT_PRICE_LIMIT = Decimal("0.000000000000000000094212147")
MAX_SQRT_PRICE_LIMIT = Decimal("18446050999999999999")


@dataclass(slots=True)
class Swaps:
    bundler_service: Bundler
    wallet_address: Optional[str] = None

    def swap(
        self,
        token_in: GalaChainTokenClassKey | str,
        token_out: GalaChainTokenClassKey | str,
        fee: int,
        amount: Mapping[str, object],
        wallet_address: Optional[str] = None,
    ):
        wallet = wallet_address or self.wallet_address
        wallet = validate_wallet_address(wallet)
        validate_fee(fee)

        token_in_class = parse_token_class_key(token_in)
        token_out_class = parse_token_class_key(token_out)

        ordering = get_token_ordering(token_in_class, token_out_class, False)
        zero_for_one = stringify_token_class_key(token_in_class) == stringify_token_class_key(ordering.token0)

        if "exactIn" in amount:
            exact_in = validate_numeric_amount(amount["exactIn"], "exactIn")
            amount_out_min = amount.get("amountOutMinimum")
            if amount_out_min is not None:
                validate_numeric_amount(amount_out_min, "amountOutMinimum", allow_zero=True)
            raw_amount = exact_in
            raw_amount_out_min = (
                -validate_numeric_amount(amount_out_min, "amountOutMinimum", allow_zero=True)
                if amount_out_min is not None
                else None
            )
            raw_amount_in_max = exact_in
        elif "exactOut" in amount:
            exact_out = validate_numeric_amount(amount["exactOut"], "exactOut")
            amount_in_max = amount.get("amountInMaximum")
            if amount_in_max is not None:
                validate_numeric_amount(amount_in_max, "amountInMaximum")
            raw_amount = -exact_out
            raw_amount_out_min = -exact_out
            raw_amount_in_max = (
                validate_numeric_amount(amount_in_max, "amountInMaximum") if amount_in_max is not None else None
            )
        else:
            raise ValueError("amount must contain either 'exactIn' or 'exactOut'")

        to_sign: Dict[str, object] = {
            "token0": ordering.token0.to_payload(),
            "token1": ordering.token1.to_payload(),
            "fee": fee,
            "amount": str(raw_amount),
            "zeroForOne": zero_for_one,
            "sqrtPriceLimit": str(MIN_SQRT_PRICE_LIMIT if ordering.zero_for_one else MAX_SQRT_PRICE_LIMIT),
            "recipient": wallet,
        }
        if raw_amount_out_min is not None:
            to_sign["amountOutMinimum"] = str(raw_amount_out_min)
        if raw_amount_in_max is not None:
            to_sign["amountInMaximum"] = str(raw_amount_in_max)

        token0_key = stringify_token_class_key(ordering.token0, separator="$")
        token1_key = stringify_token_class_key(ordering.token1, separator="$")

        pool_string = f"$pool${token0_key}${token1_key}${fee}"
        token_balance0 = f"$tokenBalance${token0_key}${wallet}"
        token_balance1 = f"$tokenBalance${token1_key}${wallet}"
        token_balance0_pool = f"$tokenBalance${token0_key}${pool_string}"
        token_balance1_pool = f"$tokenBalance${token1_key}${pool_string}"

        strings_instructions: List[str] = [
            pool_string,
            token_balance0,
            token_balance1,
            token_balance0_pool,
            token_balance1_pool,
        ]

        return self.bundler_service.send_bundler_request("Swap", to_sign, strings_instructions)

