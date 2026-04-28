"""HTTP client wrapper with per-host token-bucket rate limiting + retries.

Single source of truth for outbound HTTP. Every external call (Omnisend,
Shopify storefront, Omnisend CDN) goes through here so we get uniform
logging and rate-limit behavior.

Why custom token bucket: pyrate-limiter is fine but we need *per-host*
buckets and the ability to back off on 429 specifically. A small
hand-rolled bucket keeps the surface area minimal.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from loguru import logger


@dataclass
class TokenBucket:
    """Simple thread-safe token bucket. Tokens refill at `qps` per second."""

    qps: float
    capacity: float = 1.0
    _tokens: float = field(default=1.0, init=False)
    _last_refill: float = field(default_factory=time.monotonic, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def acquire(self, n: float = 1.0) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_refill
                self._tokens = min(self.capacity, self._tokens + elapsed * self.qps)
                self._last_refill = now
                if self._tokens >= n:
                    self._tokens -= n
                    return
                deficit = n - self._tokens
                wait = deficit / self.qps if self.qps > 0 else 60.0
            time.sleep(wait)


@dataclass
class HostPolicy:
    qps: float
    max_retries: int = 1
    backoff_seconds: float = 8.0


class HttpClient:
    """Thin wrapper over httpx.Client with per-host rate limiting + retries."""

    def __init__(
        self,
        policies: dict[str, HostPolicy],
        default_policy: HostPolicy | None = None,
        timeout: float = 30.0,
        user_agent: str = "fms-campaigns/0.1 (+https://fabricmegastore.com)",
    ) -> None:
        self._policies = policies
        self._default = default_policy or HostPolicy(qps=10.0, max_retries=2, backoff_seconds=2.0)
        self._buckets: dict[str, TokenBucket] = {
            host: TokenBucket(qps=p.qps) for host, p in policies.items()
        }
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": user_agent},
            follow_redirects=True,
        )

    def _policy(self, url: str) -> HostPolicy:
        host = httpx.URL(url).host
        return self._policies.get(host, self._default)

    def _bucket(self, url: str) -> TokenBucket:
        host = httpx.URL(url).host
        if host not in self._buckets:
            self._buckets[host] = TokenBucket(qps=self._default.qps)
        return self._buckets[host]

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        policy = self._policy(url)
        bucket = self._bucket(url)
        attempt = 0
        while True:
            bucket.acquire()
            try:
                resp = self._client.request(method, url, **kwargs)
            except httpx.RequestError as e:
                logger.warning(f"{method} {url} → request error: {e}")
                if attempt >= policy.max_retries:
                    raise
                attempt += 1
                time.sleep(policy.backoff_seconds)
                continue

            if resp.status_code == 429 and attempt < policy.max_retries:
                logger.warning(
                    f"{method} {url} → 429, backing off {policy.backoff_seconds}s "
                    f"(attempt {attempt + 1}/{policy.max_retries})"
                )
                attempt += 1
                time.sleep(policy.backoff_seconds)
                continue

            if resp.status_code >= 500 and attempt < policy.max_retries:
                logger.warning(
                    f"{method} {url} → {resp.status_code}, retrying in "
                    f"{policy.backoff_seconds}s (attempt {attempt + 1}/{policy.max_retries})"
                )
                attempt += 1
                time.sleep(policy.backoff_seconds)
                continue

            logger.debug(f"{method} {url} → {resp.status_code}")
            return resp

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PATCH", url, **kwargs)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
