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
