from gswap_sdk.pools import Pools


class DummyHttpClient:
    def __init__(self):
        self.calls = []

    def send_post_request(self, base_url, base_path, endpoint, body):
        self.calls.append((base_url, base_path, endpoint, body))
        return {
            "Data": {
                "fee": 500,
                "feeGrowthGlobal0": "0",
                "feeGrowthGlobal1": "0",
                "grossPoolLiquidity": "0",
                "liquidity": "0",
                "maxLiquidityPerTick": "0",
                "protocolFees": 0,
                "protocolFeesToken0": "0",
                "protocolFeesToken1": "0",
                "sqrtPrice": "1",
                "tickSpacing": 10,
                "token0": "GALA$Unit$none$none",
                "token0ClassKey": {
                    "collection": "GALA",
                    "category": "Unit",
                    "type": "none",
                    "additionalKey": "none",
                },
                "token1": "GUSDC$Unit$none$none",
                "token1ClassKey": {
                    "collection": "GUSDC",
                    "category": "Unit",
                    "type": "none",
                    "additionalKey": "none",
                },
            }
        }


def test_get_pool_data_sends_token_payloads():
    http_client = DummyHttpClient()
    pools = Pools("https://example.com", "/dex", http_client)

    pools.get_pool_data("GALA|Unit|none|none", "GUSDC|Unit|none|none", 500)

    (_, _, _, body) = http_client.calls[0]

    assert body["token0"] == {
        "collection": "GALA",
        "category": "Unit",
        "type": "none",
        "additionalKey": "none",
    }
    assert body["token1"] == {
        "collection": "GUSDC",
        "category": "Unit",
        "type": "none",
        "additionalKey": "none",
    }
