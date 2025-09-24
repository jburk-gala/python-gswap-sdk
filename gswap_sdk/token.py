"""Token utilities and type helpers for the gSwap SDK."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Generic, Optional, Tuple, TypeVar

from .errors import GSwapSDKError


@dataclass(slots=True, frozen=True)
class GalaChainTokenClassKey:
    """Representation of a GalaChain token class key."""

    collection: str
    category: str
    type: str
    additional_key: str

    def as_tuple(self) -> Tuple[str, str, str, str]:
        return (self.collection, self.category, self.type, self.additional_key)

    def __str__(self) -> str:  # pragma: no cover - convenience wrapper
        return stringify_token_class_key(self)

    def to_payload(self) -> Dict[str, str]:
        """Return the GalaChain API payload representation for the token."""

        return {
            "collection": self.collection,
            "category": self.category,
            "type": self.type,
            "additionalKey": self.additional_key,
        }


_T = TypeVar("_T")


@dataclass(slots=True)
class TokenOrdering(Generic[_T]):
    token0: GalaChainTokenClassKey
    token1: GalaChainTokenClassKey
    zero_for_one: bool
    token0_attributes: Optional[_T]
    token1_attributes: Optional[_T]


def stringify_token_class_key(
    token_class_key: GalaChainTokenClassKey | str, *, separator: str = "|"
) -> str:
    """Return the canonical string representation for a token class key."""

    if isinstance(token_class_key, str):
        return token_class_key

    return separator.join(token_class_key.as_tuple())


def parse_token_class_key(
    token_class_key: GalaChainTokenClassKey | str,
) -> GalaChainTokenClassKey:
    """Parse a token class key into :class:`GalaChainTokenClassKey`."""

    if isinstance(token_class_key, GalaChainTokenClassKey):
        return GalaChainTokenClassKey(*token_class_key.as_tuple())

    parts = token_class_key.split("|")
    if len(parts) != 4 or not all(parts):
        raise GSwapSDKError(
            "Invalid token class key",
            "INVALID_TOKEN_CLASS_KEY",
            {"tokenClassKey": token_class_key},
        )

    collection, category, type_, additional_key = parts
    return GalaChainTokenClassKey(collection, category, type_, additional_key)


def compare_tokens(
    first: GalaChainTokenClassKey | str, second: GalaChainTokenClassKey | str
) -> int:
    """Compare two token class keys lexicographically."""

    first_key = stringify_token_class_key(first).casefold()
    second_key = stringify_token_class_key(second).casefold()

    if first_key < second_key:
        return -1
    if first_key > second_key:
        return 1
    return 0


def get_token_ordering(
    first: GalaChainTokenClassKey | str,
    second: GalaChainTokenClassKey | str,
    assert_correctness: bool,
    token1_data: Optional[_T] = None,
    token2_data: Optional[_T] = None,
) -> TokenOrdering[_T]:
    """Return the canonical ordering for a token pair.

    Parameters mirror the TypeScript helper and behave identically: when
    ``assert_correctness`` is ``True`` the function raises if ``first`` sorts
    above ``second``.  ``token1_data`` and ``token2_data`` travel with the
    associated tokens so the caller can keep token specific metadata aligned
    with the ordering.
    """

    token0 = parse_token_class_key(first)
    token1 = parse_token_class_key(second)
    zero_for_one = compare_tokens(token0, token1) < 0

    if zero_for_one:
        return TokenOrdering(token0, token1, True, token1_data, token2_data)

    if assert_correctness:
        raise GSwapSDKError.incorrect_token_ordering_error(first, second)

    return TokenOrdering(token1, token0, False, token2_data, token1_data)

