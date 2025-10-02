"""Pool graph hydration helpers for arbitrage workflows."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Deque, Dict, Iterable, Mapping, MutableMapping, Protocol, Sequence, Set, Tuple

from gswap_sdk.pools import PoolData
from gswap_sdk.token import (
    GalaChainTokenClassKey,
    parse_token_class_key,
    stringify_token_class_key,
)

__all__ = [
    "PoolSeed",
    "HydratedPoolEdge",
    "PoolGraph",
]

TokenLike = GalaChainTokenClassKey | str
PoolSeed = Tuple[TokenLike, TokenLike, int]


class PoolsClient(Protocol):
    """Minimal client protocol required for pool hydration."""

    def get_pool_data(
        self,
        token0: GalaChainTokenClassKey | str,
        token1: GalaChainTokenClassKey | str,
        fee: int,
    ) -> PoolData:
        """Return the latest on-chain state for a pool."""


class SupportsPools(Protocol):
    """Typing helper for objects that expose a ``pools`` attribute."""

    pools: PoolsClient


@dataclass(slots=True)
class HydratedPoolEdge:
    """Representation of a validated pool edge in the arbitrage graph."""

    token0: GalaChainTokenClassKey
    token1: GalaChainTokenClassKey
    fee: int
    tick_spacing: int
    liquidity: Decimal
    gross_liquidity: Decimal
    last_refreshed: datetime

    def token_strings(self) -> Tuple[str, str]:
        """Return the canonical string identifiers for the pool tokens."""

        return (
            stringify_token_class_key(self.token0),
            stringify_token_class_key(self.token1),
        )

    def other_token(self, token: str) -> GalaChainTokenClassKey:
        """Return the token on the opposite side of ``token`` for the edge."""

        token0, token1 = self.token_strings()
        if token == token0:
            return self.token1
        if token == token1:
            return self.token0
        raise KeyError(f"Token {token!r} is not part of this pool edge")


class PoolGraph:
    """Cache of validated pools seeded from operator configuration."""

    def __init__(
        self,
        client: SupportsPools,
        *,
        freshness: timedelta = timedelta(minutes=5),
    ) -> None:
        if freshness <= timedelta(0):
            raise ValueError("freshness must be a positive timedelta")

        self._client = client
        self._freshness = freshness
        self._edges: Dict[Tuple[str, str, int], HydratedPoolEdge] = {}
        self._adjacency: Dict[str, Set[Tuple[str, str, int]]] = defaultdict(set)

    def hydrate(self, seeds: Iterable[PoolSeed]) -> None:
        """Hydrate the configured pool edges via the gateway API."""

        now = datetime.now(timezone.utc)
        for seed in seeds:
            token_a, token_b, fee = seed
            parsed_a = parse_token_class_key(token_a)
            parsed_b = parse_token_class_key(token_b)
            token0_str, token1_str = sorted(
                (
                    stringify_token_class_key(parsed_a),
                    stringify_token_class_key(parsed_b),
                )
            )
            edge_key = (token0_str, token1_str, int(fee))

            existing = self._edges.get(edge_key)
            if existing and now - existing.last_refreshed < self._freshness:
                continue

            pool_data = self._client.pools.get_pool_data(parsed_a, parsed_b, int(fee))
            api_tokens = {
                stringify_token_class_key(pool_data.token0),
                stringify_token_class_key(pool_data.token1),
            }
            if {token0_str, token1_str} != api_tokens:
                raise ValueError(
                    "Gateway returned mismatched token class keys for pool edge",
                )

            token0 = parse_token_class_key(token0_str)
            token1 = parse_token_class_key(token1_str)
            hydrated = HydratedPoolEdge(
                token0=token0,
                token1=token1,
                fee=int(pool_data.fee),
                tick_spacing=int(pool_data.tick_spacing),
                liquidity=pool_data.liquidity,
                gross_liquidity=pool_data.gross_pool_liquidity,
                last_refreshed=now,
            )
            self._edges[edge_key] = hydrated
            self._adjacency[token0_str].add(edge_key)
            self._adjacency[token1_str].add(edge_key)

    def get_neighbors(self, token: TokenLike) -> Sequence[HydratedPoolEdge]:
        """Return hydrated pool edges incident to ``token``."""

        token_str = stringify_token_class_key(token)
        keys = self._adjacency.get(token_str)
        if not keys:
            return []
        return [self._edges[key] for key in keys]

    def k_hop_neighbors(
        self, token: TokenLike, *, max_hops: int
    ) -> Mapping[int, Set[str]]:
        """Return tokens reachable within ``max_hops`` steps of ``token``."""

        if max_hops < 1:
            return {}

        start = stringify_token_class_key(token)
        visited: Set[str] = {start}
        frontier: Deque[Tuple[str, int]] = deque([(start, 0)])
        layers: MutableMapping[int, Set[str]] = defaultdict(set)

        while frontier:
            current, depth = frontier.popleft()
            if depth == max_hops:
                continue

            for edge_key in self._adjacency.get(current, set()):
                edge = self._edges[edge_key]
                neighbor = stringify_token_class_key(edge.other_token(current))
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                layers[depth + 1].add(neighbor)
                frontier.append((neighbor, depth + 1))

        return {hop: set(tokens) for hop, tokens in layers.items()}

    def edge_count(self) -> int:
        """Return the number of hydrated edges currently cached."""

        return len(self._edges)

    def last_refreshed(self, token_a: TokenLike, token_b: TokenLike, fee: int) -> datetime | None:
        """Return the last hydration timestamp for the specified edge."""

        parsed_a = parse_token_class_key(token_a)
        parsed_b = parse_token_class_key(token_b)
        token0_str, token1_str = sorted(
            (
                stringify_token_class_key(parsed_a),
                stringify_token_class_key(parsed_b),
            )
        )
        edge_key = (token0_str, token1_str, int(fee))
        edge = self._edges.get(edge_key)
        return edge.last_refreshed if edge else None
