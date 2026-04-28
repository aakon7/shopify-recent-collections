"""Service factory — wires up clients with the right rate-limit policies.

A single `Services` bundle is built once per CLI invocation and passed down
through the command implementations. Easier to test than module-level globals.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import BrandConfig
from .http_client import HostPolicy, HttpClient
from .omnisend import OmnisendClient
from .shopify import ShopifyClient


@dataclass
class Services:
    config: BrandConfig
    http: HttpClient
    omnisend: OmnisendClient
    shopify: ShopifyClient

    def close(self) -> None:
        self.http.close()


def build_services(config: BrandConfig) -> Services:
    rl = config.rate_limits
    policies = {
        config.shopify_domain: HostPolicy(
            qps=rl.shopify_qps,
            max_retries=rl.shopify_max_retries,
            backoff_seconds=rl.shopify_backoff_seconds,
        ),
        f"fabric.{config.shopify_domain}": HostPolicy(
            qps=rl.shopify_qps,
            max_retries=rl.shopify_max_retries,
            backoff_seconds=rl.shopify_backoff_seconds,
        ),
        "api.omnisend.com": HostPolicy(qps=rl.omnisend_qps, max_retries=2, backoff_seconds=2.0),
    }
    http = HttpClient(policies=policies)
    omnisend = OmnisendClient(http=http, api_key=config.secrets.omnisend_api_key)
    shopify = ShopifyClient(http=http, base_url=config.shopify_base_url)
    return Services(config=config, http=http, omnisend=omnisend, shopify=shopify)
