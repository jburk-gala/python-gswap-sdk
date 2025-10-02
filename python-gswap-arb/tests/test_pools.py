from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import List, Tuple

import pytest

from gswap_arb.pools import PoolGraph
from gswap_sdk.pools import PoolData
from gswap_sdk.token import stringify_token_class_key

TOKEN_A = "collection|category|type|AAA"
TOKEN_B = "collection|category|type|BBB"
TOKEN_C = "collection|category|type|CCC"


def _make_pool_data(token0: str, token1: str, fee: int) -> PoolData:
    return PoolData(
        bitmap={},
        fee=fee,
        fee_growth_global0=Decimal("0"),
        fee_growth_global1=Decimal("0"),
        gross_pool_liquidity=Decimal("2000"),
        liquidity=Decimal("1000"),
        max_liquidity_per_tick=Decimal("0"),
        protocol_fees=0,
        protocol_fees_token0=Decimal("0"),
        protocol_fees_token1=Decimal("0"),
        sqrt_price=Decimal("1"),
        tick_spacing=60,
        token0=token0,
        token0_class_key={},
        token1=token1,
        token1_class_key={},
    )


class RecordingPools:
    def __init__(self) -> None:
        self.requests: List[Tuple[str, str, int]] = []

    def get_pool_data(self, token0, token1, fee) -> PoolData:
        token_strings = sorted(
            (
                stringify_token_class_key(token0),
                stringify_token_class_key(token1),
            )
        )
        self.requests.append(
            (
                stringify_token_class_key(token0),
                stringify_token_class_key(token1),
                int(fee),
            )
        )
        return _make_pool_data(token_strings[0], token_strings[1], int(fee))


class MismatchedPools(RecordingPools):
    def get_pool_data(self, token0, token1, fee) -> PoolData:  # type: ignore[override]
        super().get_pool_data(token0, token1, fee)
        # Force an unexpected token to trigger validation
        return _make_pool_data(TOKEN_A, "different|token|class|key", int(fee))


class Client:
    def __init__(self, pools) -> None:
        self.pools = pools


def test_hydrate_builds_graph_and_caches_results() -> None:
    pools = RecordingPools()
    graph = PoolGraph(Client(pools), freshness=timedelta(minutes=10))

    graph.hydrate([(TOKEN_A, TOKEN_B, 3_000)])

    assert pools.requests == [(TOKEN_A, TOKEN_B, 3_000)]
    assert graph.edge_count() == 1

    neighbors = graph.get_neighbors(TOKEN_A)
    assert len(neighbors) == 1
    edge = neighbors[0]
    assert edge.tick_spacing == 60
    assert edge.liquidity == Decimal("1000")
    assert edge.gross_liquidity == Decimal("2000")
    assert graph.last_refreshed(TOKEN_A, TOKEN_B, 3_000) is not None

    graph.hydrate([(TOKEN_A, TOKEN_B, 3_000)])
    assert len(pools.requests) == 1


def test_k_hop_neighbors_discovers_tokens_within_depth() -> None:
    pools = RecordingPools()
    graph = PoolGraph(Client(pools), freshness=timedelta(minutes=10))
    graph.hydrate([(TOKEN_A, TOKEN_B, 500), (TOKEN_B, TOKEN_C, 500)])

    first_hop = graph.k_hop_neighbors(TOKEN_A, max_hops=1)
    assert first_hop == {1: {TOKEN_B}}

    second_hop = graph.k_hop_neighbors(TOKEN_A, max_hops=2)
    assert second_hop[1] == {TOKEN_B}
    assert second_hop[2] == {TOKEN_C}


def test_hydrate_raises_when_gateway_returns_unexpected_tokens() -> None:
    graph = PoolGraph(Client(MismatchedPools()), freshness=timedelta(minutes=10))

    with pytest.raises(ValueError):
        graph.hydrate([(TOKEN_A, TOKEN_B, 500)])
