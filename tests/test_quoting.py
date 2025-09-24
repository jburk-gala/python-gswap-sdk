from decimal import Decimal

from gswap_sdk.quoting import Quoting


class DummyHttpClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def post(self, base_url, base_path, endpoint, body):
        self.calls.append((base_url, base_path, endpoint, body))
        return {"Data": self.payload}


def test_quote_exact_input_uses_decimal_arithmetic():
    payload = {
        "amount0": "-1000000000000000000",
        "amount1": "500000000000000000",
        "currentSqrtPrice": "1.5",
        "newSqrtPrice": "1.8",
    }
    http_client = DummyHttpClient(payload)
    quoting = Quoting("https://example.com", "/dex", http_client)

    result = quoting.quote_exact_input("A|B|C|D", "A|B|C|E", Decimal("1"), fee=50)

    assert http_client.calls[0][0] == "https://example.com"
    assert result.out_token_amount == Decimal("500000000000000000")
    assert result.current_price == Decimal("2.25")


def test_quote_exact_input_handles_descending_token_order():
    payload = {
        "amount0": "500000000000000000",
        "amount1": "-1000000000000000000",
        "currentSqrtPrice": "1.5",
        "newSqrtPrice": "1.2",
    }
    http_client = DummyHttpClient(payload)
    quoting = Quoting("https://example.com", "/dex", http_client)

    result = quoting.quote_exact_input("B|B|C|E", "A|B|C|D", Decimal("1"), fee=50)

    assert http_client.calls[0][3]["amount"] == "-1"
    assert result.in_token_amount == Decimal("1000000000000000000")
    assert result.out_token_amount == Decimal("500000000000000000")


def test_quote_exact_output_handles_descending_token_order():
    payload = {
        "amount0": "-500000000000000000",
        "amount1": "1000000000000000000",
        "currentSqrtPrice": "1.5",
        "newSqrtPrice": "1.8",
    }
    http_client = DummyHttpClient(payload)
    quoting = Quoting("https://example.com", "/dex", http_client)

    result = quoting.quote_exact_output("B|B|C|E", "A|B|C|D", Decimal("1"), fee=50)

    assert http_client.calls[0][3]["amount"] == "1"
    assert result.in_token_amount == Decimal("1000000000000000000")
    assert result.out_token_amount == Decimal("500000000000000000")
