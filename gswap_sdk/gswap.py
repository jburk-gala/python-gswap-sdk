"""Public entry point for the gSwap Python SDK."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .assets import Assets
from .bundler import Bundler
from .events import Events
from .http import HttpClient, HttpRequestor
from .pools import Pools
from .positions import Positions
from .quoting import Quoting
from .signers import GalaChainSigner
from .swaps import Swaps


@dataclass(slots=True)
class GSwapOptions:
    signer: Optional[GalaChainSigner] = None
    gateway_base_url: str = "https://gateway-mainnet.galachain.com"
    dex_contract_base_path: str = "/api/asset/dexv3-contract"
    token_contract_base_path: str = "/api/asset/token-contract"
    bundler_base_url: str = "https://bundle-backend-prod1.defi.gala.com"
    bundling_api_base_path: str = "/bundle"
    dex_backend_base_url: str = "https://dex-backend-prod1.defi.gala.com"
    transaction_wait_timeout_ms: int = 300_000
    wallet_address: Optional[str] = None
    http_requestor: Optional[HttpRequestor] = None


class GSwap:
    """Main entry point for interacting with the gSwap decentralised exchange."""

    events = Events.instance

    def __init__(self, options: Optional[GSwapOptions] = None) -> None:
        self.options = options or GSwapOptions()

        self._http_client = HttpClient(self.options.http_requestor)

        self.bundler = Bundler(
            self.options.bundler_base_url,
            self.options.bundling_api_base_path,
            self.options.transaction_wait_timeout_ms,
            self.options.signer,
            self._http_client,
        )

        self.pools = Pools(
            self.options.gateway_base_url,
            self.options.dex_contract_base_path,
            self._http_client,
        )

        self.quoting = Quoting(
            self.options.gateway_base_url,
            self.options.dex_contract_base_path,
            self._http_client,
        )

        self.positions = Positions(
            self.options.gateway_base_url,
            self.options.dex_contract_base_path,
            self.bundler,
            self.pools,
            self._http_client,
            wallet_address=self.options.wallet_address,
        )

        self.swaps = Swaps(self.bundler, wallet_address=self.options.wallet_address)

        self.assets = Assets(
            self.options.dex_backend_base_url,
            self._http_client,
        )

    @property
    def gateway_base_url(self) -> str:
        return self.options.gateway_base_url

    @property
    def dex_contract_base_path(self) -> str:
        return self.options.dex_contract_base_path

    @property
    def dex_backend_base_url(self) -> str:
        return self.options.dex_backend_base_url

