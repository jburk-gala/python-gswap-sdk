from decimal import Decimal

from gswap_sdk.pools import Pools


class DummyHttpClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def send_post_request(self, base_url, base_path, endpoint, body):
        self.calls.append((base_url, base_path, endpoint, body))
        return {"Data": self.payload}


def test_get_pool_data_parses_response():
    payload = {
        "bitmap": {"0": "1"},
        "fee": "3000",
        "feeGrowthGlobal0": "1000000",
        "feeGrowthGlobal1": "2000000",
        "grossPoolLiquidity": "500000000000000000",
        "liquidity": "400000000000000000",
        "maxLiquidityPerTick": "999",
        "protocolFees": "1",
        "protocolFeesToken0": "123456",
        "protocolFeesToken1": "654321",
        "sqrtPrice": "1.2",
        "tickSpacing": "60",
        "token0": "GALA|Unit|none|none",
        "token1": "GUSDC|Unit|none|none",
        "token0ClassKey": {"Collection": "GALA"},
        "token1ClassKey": {"Collection": "GUSDC"},
    }
    http_client = DummyHttpClient(payload)
    pools = Pools("https://gateway.example/", "/dex", http_client)

    result = pools.get_pool_data("GALA|Unit|none|none", "GUSDC|Unit|none|none", 3000)

    assert http_client.calls[0][2] == "/GetPoolData"
    assert result.fee == 3000
    assert result.sqrt_price == Decimal("1.2")
    assert result.protocol_fees_token0 == Decimal("123456")
    assert result.protocol_fees_token1 == Decimal("654321")
    assert result.token0 == "GALA|Unit|none|none"
    assert result.token1 == "GUSDC|Unit|none|none"
