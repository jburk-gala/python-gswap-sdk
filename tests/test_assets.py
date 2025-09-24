from decimal import Decimal

from gswap_sdk.assets import Assets


class DummyHttpClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def send_get_request(self, base_url, base_path, endpoint, params):
        self.calls.append((base_url, base_path, endpoint, params))
        return self.payload


def test_get_user_assets_parses_response():
    payload = {
        "data": {
            "token": [
                {
                    "image": "image-a",
                    "name": "Token A",
                    "decimals": 18,
                    "verify": True,
                    "symbol": "TKNA",
                    "quantity": "1.5000",
                },
                {
                    "image": "image-b",
                    "name": "Token B",
                    "decimals": 6,
                    "verify": False,
                    "symbol": "TKNB",
                    "quantity": 42,
                },
            ],
            "count": 2,
        }
    }
    http_client = DummyHttpClient(payload)
    assets = Assets("https://dex-backend.example", http_client)

    result = assets.get_user_assets(" eth|wallet ", page=2, limit=5)

    assert http_client.calls[0] == (
        "https://dex-backend.example",
        "/user/assets",
        "",
        {"address": "eth|wallet", "page": "2", "limit": "5"},
    )
    assert len(result.tokens) == 2
    assert result.tokens[0].quantity == Decimal("1.5000")
    assert result.tokens[1].quantity == Decimal("42")
    assert result.tokens[0].verify is True
    assert result.count == 2
