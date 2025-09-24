"""HTTP client helpers used by the gSwap SDK."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, MutableMapping, Optional

import requests

from .errors import GSwapSDKError

HttpRequestor = Callable[[str, Mapping[str, Any]], requests.Response]


@dataclass
class HttpClient:
    """Small convenience wrapper around :mod:`requests` with SDK defaults."""

    requestor: Optional[HttpRequestor] = None
    user_agent: str = "python-gswap-sdk/0.1"

    def __post_init__(self) -> None:
        if self.requestor is None:
            session = requests.Session()

            def _requestor(url: str, kwargs: Mapping[str, Any]) -> requests.Response:
                return session.request(url=url, **dict(kwargs))

            self.requestor = _requestor

    def _send_request(
        self,
        method: str,
        base_url: str,
        base_path: str,
        endpoint: str,
        *,
        params: Optional[Mapping[str, str]] = None,
        body: Optional[Mapping[str, Any]] = None,
    ) -> Any:
        url = f"{base_url.rstrip('/')}{base_path}{endpoint}"
        headers: MutableMapping[str, str] = {
            "Content-Type": "application/json",
            "User-Agent": self.user_agent,
        }

        kwargs: MutableMapping[str, Any] = {
            "method": method,
            "headers": headers,
            "timeout": 30,
        }
        if params:
            kwargs["params"] = params
        if body is not None:
            kwargs["json"] = body

        assert self.requestor is not None
        response = self.requestor(url, kwargs)

        if not response.ok:
            error_key: Optional[str] = None
            message: Optional[str] = None
            try:
                payload = response.json()
            except ValueError:
                payload = response.text
            else:
                if isinstance(payload, Mapping):
                    error = payload.get("error")
                    if isinstance(error, Mapping):
                        error_key = error.get("ErrorKey") or error.get("errorKey")  # type: ignore[assignment]
                        message = error.get("Message") or error.get("message")  # type: ignore[assignment]
            raise GSwapSDKError.from_http_response(
                url, response.status_code, payload, error_key, message
            )

        try:
            return response.json()
        except ValueError:
            return response.text

    def send_post_request(
        self,
        base_url: str,
        base_path: str,
        endpoint: str,
        body: Mapping[str, Any],
    ) -> Any:
        return self._send_request("POST", base_url, base_path, endpoint, body=body)

    def send_get_request(
        self,
        base_url: str,
        base_path: str,
        endpoint: str,
        params: Optional[Mapping[str, str]] = None,
    ) -> Any:
        return self._send_request("GET", base_url, base_path, endpoint, params=params)

    # Backwards compatible aliases used by the early Python port
    def post(
        self,
        base_url: str,
        base_path: str,
        endpoint: str,
        body: Mapping[str, Any],
    ) -> Any:
        return self.send_post_request(base_url, base_path, endpoint, body)

    def get(
        self,
        base_url: str,
        base_path: str,
        endpoint: str,
        params: Optional[Mapping[str, str]] = None,
    ) -> Any:
        return self.send_get_request(base_url, base_path, endpoint, params)

