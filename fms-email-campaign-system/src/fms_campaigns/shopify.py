"""Shopify Storefront client (read-only, public JSON endpoints).

No auth required for the endpoints we use. Rate-limit conscious — every call
goes through the shared HttpClient with the brand's `shopify_qps` policy.
"""
from __future__ import annotations

from typing import Any

from .http_client import HttpClient


class ShopifyClient:
    def __init__(self, http: HttpClient, base_url: str) -> None:
        self._http = http
        self._base = base_url.rstrip("/")

    @property
    def base_url(self) -> str:
        return self._base

    def collection_exists(self, handle: str) -> tuple[bool, int]:
        """Return (exists, http_status). 200 = ok, 404 = does-not-exist, other = treat as missing."""
        url = f"{self._base}/collections/{handle}.json"
        resp = self._http.get(url)
        if resp.status_code == 200:
            return True, 200
        return False, resp.status_code

    def collection_products_count(self, handle: str, *, peek: int = 2) -> int:
        """Cheap emptiness probe — fetch up to `peek` products and return the count seen.

        A return of 0 means "doesn't exist or is empty"; both are dead-ends for an email link.
        """
        url = f"{self._base}/collections/{handle}/products.json"
        resp = self._http.get(url, params={"limit": peek})
        if resp.status_code != 200:
            return 0
        try:
            data = resp.json()
        except Exception:
            return 0
        products = data.get("products", []) if isinstance(data, dict) else []
        return len(products)

    def collection_meta(self, handle: str) -> dict[str, Any] | None:
        url = f"{self._base}/collections/{handle}.json"
        resp = self._http.get(url)
        if resp.status_code != 200:
            return None
        try:
            data = resp.json()
        except Exception:
            return None
        return data.get("collection") if isinstance(data, dict) else None
