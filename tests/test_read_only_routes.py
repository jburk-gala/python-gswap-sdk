from __future__ import annotations

from decimal import Decimal

import pytest

from gswap_sdk.assets import Assets
from gswap_sdk.pools import Pools
from gswap_sdk.positions import Positions


class RecordingHttpClient:
    def __init__(self, *, post_responses=None, get_responses=None) -> None:
        self.post_calls = []
        self.get_calls = []
        self._post_responses = post_responses or {}
        self._get_responses = get_responses or {}

    def send_post_request(self, base_url, base_path, endpoint, body):
        self.post_calls.append((base_url, base_path, endpoint, body))
        try:
            response = self._post_responses[endpoint]
        except KeyError as exc:  # pragma: no cover - sanity guard
            raise AssertionError(f"Unexpected POST endpoint {endpoint}") from exc
        if callable(response):
            return response()
        return response

    def send_get_request(self, base_url, base_path, endpoint, params=None):
        self.get_calls.append((base_url, base_path, endpoint, params or {}))
        try:
            response = self._get_responses[endpoint]
        except KeyError as exc:  # pragma: no cover - sanity guard
            raise AssertionError(f"Unexpected GET endpoint {endpoint}") from exc
        if callable(response):
            return response()
        return response


def test_get_pool_data_posts_token_payloads():
    payload = {
        "Data": {
            "bitmap": {},
            "fee": 500,
            "feeGrowthGlobal0": "1.2",
            "feeGrowthGlobal1": "3.4",
            "grossPoolLiquidity": "1000",
            "liquidity": "500",
            "maxLiquidityPerTick": "2000",
            "protocolFees": 0,
            "protocolFeesToken0": "0.1",
            "protocolFeesToken1": "0.2",
            "sqrtPrice": "1.5",
            "tickSpacing": 10,
            "token0": "GALA|Unit|none|none",
            "token0ClassKey": {},
            "token1": "GUSDC|Unit|none|none",
            "token1ClassKey": {},
        }
    }
    client = RecordingHttpClient(post_responses={"/GetPoolData": payload})
    pools = Pools("https://example.com", "/dex", client)

    result = pools.get_pool_data("GUSDC|Unit|none|none", "GALA|Unit|none|none", 500)

    base_url, base_path, endpoint, body = client.post_calls[0]
    assert base_url == "https://example.com"
    assert base_path == "/dex"
    assert endpoint == "/GetPoolData"
    assert body["token0"] == {
        "collection": "GALA",
        "category": "Unit",
        "type": "none",
        "additionalKey": "none",
    }
    assert body["token1"]["collection"] == "GUSDC"
    assert result.liquidity == Decimal("500")
    assert result.sqrt_price == Decimal("1.5")


def test_get_user_assets_normalises_parameters():
    response = {
        "data": {
            "count": 2,
            "token": [
                {
                    "image": "https://example.com/gala.png",
                    "name": "Gala",
                    "decimals": 8,
                    "verify": True,
                    "symbol": "GALA",
                    "quantity": "123.456",
                }
            ],
        }
    }
    client = RecordingHttpClient(get_responses={"": response})
    assets = Assets("https://backend.example", client)

    result = assets.get_user_assets(" eth|ABC ", page=2, limit=5)

    base_url, base_path, endpoint, params = client.get_calls[0]
    assert base_url == "https://backend.example"
    assert base_path == "/user/assets"
    assert endpoint == ""
    assert params == {"address": "eth|ABC", "page": "2", "limit": "5"}
    assert result.count == 2
    assert result.tokens[0].quantity == Decimal("123.456")


def test_get_user_assets_invalid_page():
    assets = Assets("https://backend.example", RecordingHttpClient())
    with pytest.raises(ValueError):
        assets.get_user_assets("eth|ABC", page=0)


def test_get_user_positions_parses_response():
    response = {
        "Data": {
            "positions": [
                {
                    "poolHash": "hash",
                    "positionId": "pos-1",
                    "token0ClassKey": "GALA|Unit|none|none",
                    "token1ClassKey": "GUSDC|Unit|none|none",
                    "token0Img": "img0",
                    "token1Img": "img1",
                    "token0Symbol": "GALA",
                    "token1Symbol": "GUSDC",
                    "fee": 500,
                    "liquidity": "10.5",
                    "tickLower": -100,
                    "tickUpper": 100,
                    "createdAt": "2024-01-01T00:00:00Z",
                }
            ],
            "nextBookMark": "bookmark-1",
        }
    }
    client = RecordingHttpClient(post_responses={"/GetUserPositions": response})
    positions = Positions(
        "https://gateway.example",
        "/dex",
        bundler_service=object(),
        pool_service=object(),
        http_client=client,
    )

    result = positions.get_user_positions(" eth|ABC ", limit=3, bookmark="b1")

    base_url, base_path, endpoint, body = client.post_calls[0]
    assert base_url == "https://gateway.example"
    assert base_path == "/dex"
    assert endpoint == "/GetUserPositions"
    assert body == {"user": "eth|ABC", "limit": 3, "bookMark": "b1"}

    assert result.bookmark == "bookmark-1"
    assert len(result.positions) == 1
    position = result.positions[0]
    assert position.fee == 500
    assert position.token0_class_key.collection == "GALA"
    assert position.liquidity == Decimal("10.5")


def test_get_position_returns_decimals():
    response = {
        "Data": {
            "fee": 3000,
            "feeGrowthInside0Last": "1.23",
            "feeGrowthInside1Last": "4.56",
            "liquidity": "7.89",
            "poolHash": "pool-hash",
            "positionId": "pos-2",
            "tickLower": -120,
            "tickUpper": 120,
            "token0ClassKey": "GALA|Unit|none|none",
            "token1ClassKey": "GUSDC|Unit|none|none",
            "tokensOwed0": "0.001",
            "tokensOwed1": "0.002",
        }
    }
    client = RecordingHttpClient(post_responses={"/GetPositions": response})
    positions = Positions(
        "https://gateway.example",
        "/dex",
        bundler_service=object(),
        pool_service=object(),
        http_client=client,
    )

    payload = {
        "token0ClassKey": "GALA|Unit|none|none",
        "token1ClassKey": "GUSDC|Unit|none|none",
        "fee": 3000,
        "tickLower": -120,
        "tickUpper": 120,
    }
    result = positions.get_position("eth|ABC", payload)

    _, _, endpoint, body = client.post_calls[0]
    assert endpoint == "/GetPositions"
    assert body["owner"] == "eth|ABC"
    assert body["token0"]["collection"] == "GALA"
    assert result.tokens_owed0 == Decimal("0.001")
    assert result.tokens_owed1 == Decimal("0.002")
