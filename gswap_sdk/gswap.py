"""Public entry point for the gSwap Python SDK."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .assets import Assets
from .http import HttpClient
from .pools import Pools
from .quoting import Quoting


@dataclass(slots=True)
class GSwapOptions:
    signer: Optional[object] = None
    gateway_base_url: str = "https://gateway-mainnet.galachain.com"
    dex_contract_base_path: str = "/api/asset/dexv3-contract"
    token_contract_base_path: str = "/api/asset/token-contract"
    bundler_base_url: str = "https://bundle-backend-prod1.defi.gala.com"
    bundling_api_base_path: str = "/bundle"
    dex_backend_base_url: str = "https://dex-backend-prod1.defi.gala.com"
    transaction_wait_timeout_ms: int = 300_000
    wallet_address: Optional[str] = None


class GSwap:
    """Main entry point for interacting with the gSwap decentralised exchange."""

    def __init__(self, options: Optional[GSwapOptions] = None) -> None:
        self.options = options or GSwapOptions()
        self._http_client = HttpClient()

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
