import pytest

from gswap_sdk import validation
from gswap_sdk.errors import GSwapSDKError


def test_validate_numeric_amount_positive():
    value = validation.validate_numeric_amount("1.23", "amount")
    assert str(value) == "1.23"


def test_validate_numeric_amount_negative():
    with pytest.raises(GSwapSDKError):
        validation.validate_numeric_amount("-1", "amount")


def test_validate_wallet_address():
    assert validation.validate_wallet_address(" eth|abc ") == "eth|abc"
    with pytest.raises(GSwapSDKError):
        validation.validate_wallet_address("")
