import pytest

from gswap_sdk.token import get_token_ordering, parse_token_class_key
from gswap_sdk.errors import GSwapSDKError


def test_parse_token_round_trip():
    key = parse_token_class_key("GALA|Unit|none|none")
    assert key.collection == "GALA"
    assert str(key) == "GALA|Unit|none|none"


def test_parse_token_invalid():
    with pytest.raises(GSwapSDKError):
        parse_token_class_key("invalid")


def test_get_token_ordering_correct():
    first = "GALA|Unit|none|none"
    second = "GUSDC|Unit|none|none"
    ordering = get_token_ordering(first, second, False)
    assert str(ordering.token0) == first
    assert ordering.zero_for_one


def test_get_token_ordering_incorrect_raises():
    first = "GUSDC|Unit|none|none"
    second = "GALA|Unit|none|none"
    with pytest.raises(GSwapSDKError):
        get_token_ordering(first, second, True)
