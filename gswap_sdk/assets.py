"""Asset utilities for the gSwap SDK."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import List

from .http import HttpClient
from .types.sdk_results import AssetBalance, GetUserAssetsResult
from .validation import validate_wallet_address


@dataclass(slots=True)
class Assets:
    """Service responsible for wallet asset queries."""

    dex_backend_base_url: str
    http_client: HttpClient

    def __post_init__(self) -> None:
        self.dex_backend_base_url = self.dex_backend_base_url.rstrip("/")

    def get_user_assets(
        self, owner_address: str, page: int = 1, limit: int = 10
    ) -> GetUserAssetsResult:
        owner = validate_wallet_address(owner_address)
        if page < 1 or int(page) != page:
            raise ValueError("Invalid page: must be a positive integer")
        if limit < 1 or limit > 100 or int(limit) != limit:
            raise ValueError("Invalid limit: must be an integer between 1 and 100")

        payload = self.http_client.send_get_request(
            self.dex_backend_base_url,
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
        tokens: List[AssetBalance] = []
        for token in tokens_payload:
            if not isinstance(token, dict):
                try:
                    token = dict(token)  # type: ignore[arg-type]
                except TypeError:
                    continue
            if not isinstance(token, dict):
                continue
            quantity_raw = token.get("quantity", "0")
            tokens.append(
                AssetBalance(
                    image=token.get("image", ""),
                    name=token.get("name", ""),
                    decimals=int(token.get("decimals", 0)),
                    verify=bool(token.get("verify", False)),
                    symbol=token.get("symbol", ""),
                    quantity=Decimal(str(quantity_raw)),
                )
            )

        return GetUserAssetsResult(tokens=tokens, count=int(data.get("count", 0)))

