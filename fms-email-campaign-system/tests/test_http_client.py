"""HTTP client tests — token bucket math + rate-limit interaction."""
from __future__ import annotations

import time

from fms_campaigns.http_client import TokenBucket


def test_token_bucket_allows_initial() -> None:
    b = TokenBucket(qps=2.0, capacity=1.0)
    start = time.monotonic()
    b.acquire()
    assert (time.monotonic() - start) < 0.05


def test_token_bucket_throttles() -> None:
    b = TokenBucket(qps=10.0, capacity=1.0)
    start = time.monotonic()
    for _ in range(3):
        b.acquire()
    elapsed = time.monotonic() - start
    # 3 acquires at 10 qps → roughly 0.2s (the first is free; next 2 each ~0.1s)
    assert 0.15 <= elapsed <= 0.5
