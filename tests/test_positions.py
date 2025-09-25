from decimal import Decimal

from gswap_sdk.positions import Positions


class DummyBundler:
    pass


class DummyPools:
    pass


class DummyHttpClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def send_post_request(self, base_url, base_path, endpoint, body):
        self.calls.append((base_url, base_path, endpoint, body))
        return self.responses[endpoint]


def _build_positions_service(responses):
    return Positions(
        "https://gateway.example",
        "/dex",
        DummyBundler(),
        DummyPools(),
        DummyHttpClient(responses),
    )


def test_get_user_positions_parses_response():
    responses = {
        "/GetUserPositions": {
            "Data": {
                "positions": [
                    {
                        "poolHash": "hash",
                        "positionId": "pos-1",
                        "token0ClassKey": "GALA|Unit|none|none",
                        "token1ClassKey": "GUSDC|Unit|none|none",
                        "token0Img": "image0",
                        "token1Img": "image1",
                        "token0Symbol": "GALA",
                        "token1Symbol": "GUSDC",
                        "fee": 3000,
                        "liquidity": "1000",
                        "tickLower": -120,
                        "tickUpper": 120,
                        "createdAt": "2023-01-01",
                    }
                ],
                "nextBookMark": "bookmark",
            }
        }
    }
    service = _build_positions_service(responses)

    result = service.get_user_positions(" eth|wallet ")

    call = service.http_client.calls[0]
    assert call[2] == "/GetUserPositions"
    assert call[3]["user"] == "eth|wallet"
    assert len(result.positions) == 1
    assert result.positions[0].fee == 3000
    assert result.bookmark == "bookmark"


def test_get_position_parses_response():
    responses = {
        "/GetPositions": {
            "Data": {
                "fee": 3000,
                "feeGrowthInside0Last": "10",
                "feeGrowthInside1Last": "20",
                "liquidity": "1000",
                "poolHash": "hash",
                "positionId": "pos-1",
                "tickLower": -120,
                "tickUpper": 120,
                "token0ClassKey": "GALA|Unit|none|none",
                "token1ClassKey": "GUSDC|Unit|none|none",
                "tokensOwed0": "5",
                "tokensOwed1": "6",
            }
        }
    }
    service = _build_positions_service(responses)

    result = service.get_position(
        "eth|wallet",
        {
            "token0ClassKey": "GALA|Unit|none|none",
            "token1ClassKey": "GUSDC|Unit|none|none",
            "fee": 3000,
            "tickLower": -120,
            "tickUpper": 120,
        },
    )

    assert service.http_client.calls[0][2] == "/GetPositions"
    assert result.tokens_owed0 == Decimal("5")
    assert result.tokens_owed1 == Decimal("6")
    assert result.token0_class_key.collection == "GALA"
    assert result.token1_class_key.collection == "GUSDC"


def test_estimate_remove_liquidity_parses_amounts():
    responses = {
        "/GetRemoveLiquidityEstimation": {
            "Data": {"amount0": "1.5", "amount1": "2.5"}
        }
    }
    service = _build_positions_service(responses)

    result = service.estimate_remove_liquidity(
        "eth|wallet",
        "pos-1",
        "GALA|Unit|none|none",
        "GUSDC|Unit|none|none",
        3000,
        -120,
        120,
        Decimal("1"),
    )

    call = service.http_client.calls[0]
    assert call[2] == "/GetRemoveLiquidityEstimation"
    assert call[3]["owner"] == "eth|wallet"
    assert result["amount0"] == Decimal("1.5")
    assert result["amount1"] == Decimal("2.5")
