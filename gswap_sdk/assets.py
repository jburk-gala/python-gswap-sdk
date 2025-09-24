"""Asset utilities for the gSwap SDK."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import List

from .http import HttpClient
from .validation import validate_wallet_address


@dataclass(slots=True)
class Asset:
    image: str
    name: str
    decimals: int
    verify: bool
    symbol: str
    quantity: Decimal


@dataclass(slots=True)
class AssetPage:
    tokens: List[Asset]
    count: int


class Assets:
    def __init__(self, dex_backend_base_url: str, http_client: HttpClient) -> None:
        self._dex_backend_base_url = dex_backend_base_url.rstrip("/")
        self._http_client = http_client

    def get_user_assets(self, owner_address: str, page: int = 1, limit: int = 10) -> AssetPage:
        owner = validate_wallet_address(owner_address)
        if page < 1 or int(page) != page:
            raise ValueError("Invalid page: must be a positive integer")
        if limit < 1 or limit > 100 or int(limit) != limit:
            raise ValueError("Invalid limit: must be an integer between 1 and 100")

        payload = self._http_client.get(
            self._dex_backend_base_url,
            "/user/assets",
            "",
            {
                "address": owner,
                "page": str(page),
                "limit": str(limit),
            },
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise ValueError("Unexpected asset response")

        tokens_payload = data.get("token") or []
        tokens: List[Asset] = []
        for token in tokens_payload:
            if not isinstance(token, dict):
                continue
            quantity_raw = token.get("quantity", "0")
            tokens.append(
                Asset(
                    image=token.get("image", ""),
                    name=token.get("name", ""),
                    decimals=int(token.get("decimals", 0)),
                    verify=bool(token.get("verify", False)),
                    symbol=token.get("symbol", ""),
                    quantity=Decimal(str(quantity_raw)),
                )
            )

        return AssetPage(tokens=tokens, count=int(data.get("count", 0)))
