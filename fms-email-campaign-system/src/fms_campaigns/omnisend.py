"""Omnisend REST API client.

Just the endpoints we actually need for the v1 pipeline. Auth is via a
single header `Authorization: <key>`. Quirks documented in §10 of the
build spec are encoded as comments where they apply.
"""
from __future__ import annotations

from typing import Any

from .http_client import HttpClient

BASE_URL = "https://api.omnisend.com/v5"


class OmnisendError(RuntimeError):
    def __init__(self, status: int, body: str, url: str) -> None:
        super().__init__(f"Omnisend {status} on {url}: {body[:500]}")
        self.status = status
        self.body = body
        self.url = url


class OmnisendClient:
    def __init__(self, http: HttpClient, api_key: str, base_url: str = BASE_URL) -> None:
        if not api_key:
            raise ValueError("OMNISEND_API_KEY is empty; set it in .env")
        self._http = http
        self._key = api_key
        self._base = base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {"X-API-KEY": self._key, "Accept": "application/json"}

    def _check(self, resp: Any) -> dict[str, Any]:
        if resp.status_code >= 400:
            raise OmnisendError(resp.status_code, resp.text, str(resp.url))
        if resp.status_code == 204:
            return {}
        return resp.json()

    # -- Campaigns ------------------------------------------------------

    def list_campaigns(self, *, name_contains: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        params = {}
        if name_contains:
            params["nameContains"] = name_contains
        if status:
            params["status"] = status
        resp = self._http.get(f"{self._base}/campaigns", headers=self._headers(), params=params)
        data = self._check(resp)
        return data.get("campaigns", []) if isinstance(data, dict) else []

    def get_campaign(self, campaign_id: str) -> dict[str, Any]:
        resp = self._http.get(f"{self._base}/campaigns/{campaign_id}", headers=self._headers())
        return self._check(resp)

    def create_campaign(self, payload: dict[str, Any]) -> dict[str, Any]:
        resp = self._http.post(f"{self._base}/campaigns", headers=self._headers(), json=payload)
        return self._check(resp)

    def copy_campaign(self, template_id: str) -> dict[str, Any]:
        resp = self._http.post(
            f"{self._base}/campaigns/{template_id}/copy", headers=self._headers()
        )
        return self._check(resp)

    def patch_campaign(self, campaign_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        resp = self._http.patch(
            f"{self._base}/campaigns/{campaign_id}", headers=self._headers(), json=payload
        )
        return self._check(resp)

    def send_campaign(self, campaign_id: str) -> dict[str, Any]:
        # Returns 204 once accepted into Omnisend's send queue.
        resp = self._http.post(
            f"{self._base}/campaigns/{campaign_id}/send", headers=self._headers()
        )
        return self._check(resp)

    def cancel_campaign(self, campaign_id: str) -> dict[str, Any]:
        resp = self._http.post(
            f"{self._base}/campaigns/{campaign_id}/cancel", headers=self._headers()
        )
        return self._check(resp)

    # -- Email content --------------------------------------------------

    def get_email_content(self, content_id: str) -> dict[str, Any]:
        # Note: GET response has known echo artifacts in the footer text block
        # (§10.2). Treat the local file as truth, never write back what GET returns.
        resp = self._http.get(
            f"{self._base}/email-content/{content_id}", headers=self._headers()
        )
        return self._check(resp)

    def put_email_content(self, content_id: str, document: dict[str, Any]) -> dict[str, Any]:
        # PUT requires the FULL document — partial PUTs return 400
        # "generalSettings is a required field". (§10.1)
        resp = self._http.put(
            f"{self._base}/email-content/{content_id}",
            headers=self._headers(),
            json=document,
        )
        return self._check(resp)

    def render_email_content(self, content_id: str) -> dict[str, Any]:
        resp = self._http.post(
            f"{self._base}/email-content/{content_id}/render", headers=self._headers()
        )
        return self._check(resp)

    # -- Images ---------------------------------------------------------

    def upload_image(self, filename: str, content: bytes, mime: str) -> dict[str, Any]:
        files = {"file": (filename, content, mime)}
        # multipart upload — don't pass json= here
        resp = self._http.post(
            f"{self._base}/images/upload",
            headers={"X-API-KEY": self._key},
            files=files,
        )
        return self._check(resp)
