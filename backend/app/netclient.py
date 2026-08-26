"""Resilient networking layer.

Provides proxy / rotation / retry support so scraping works from any country
and survives bot-protection more often:

  - rotating browser User-Agents
  - optional HTTP/SOCKS proxies (single proxy, or a pool that is cycled)
  - retries with exponential backoff on transient failures

Proxies are configured via the FLEETLEADS_PROXY env var or the app settings
(`PROXY_URL`). Examples:
    http://user:pass@host:port
    socks5://user:pass@host:port
    pool:http://p1:8080,socks5://p2:1080   (comma-separated pool)

Note on "VPN" expectations: a real VPN changes the machine's egress IP at the
OS level and cannot be installed by a Python library. The closest portable
equivalents are (a) proxies — fully supported here — and (b) rotating
identities/headers. Public "free proxy" lists exist but are mostly dead and
unreliable; for production-grade scraping you'd plug in a paid residential
proxy or your own VPN egress. The plumbing here works with any of them.
"""
from __future__ import annotations

import random
import time
from typing import Any

import httpx

USER_AGENTS = [
    # Chrome / Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    # Chrome / macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    # Firefox
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    # Safari / Edge
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]

DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Upgrade-Insecure-Requests": "1",
}


def parse_proxies(spec: str | None) -> list[str]:
    """Parse a proxy spec into a list of httpx-compatible proxy URLs."""
    if not spec or not spec.strip():
        return []
    if spec.strip().lower().startswith("pool:"):
        spec = spec.strip()[5:]
    return [p.strip() for p in spec.split(",") if p.strip()]


class NetClient:
    """httpx wrapper with UA rotation, optional proxy rotation and retries."""

    def __init__(
        self,
        proxies: list[str] | None = None,
        timeout: float = 20.0,
        retries: int = 2,
        backoff: float = 1.5,
    ):
        self.proxies = proxies or []
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self._proxy_index = 0

    def _next_proxy(self) -> str | None:
        if not self.proxies:
            return None
        proxy = self.proxies[self._proxy_index % len(self.proxies)]
        self._proxy_index += 1
        return proxy

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        h = dict(DEFAULT_HEADERS)
        h["User-Agent"] = random.choice(USER_AGENTS)
        if extra:
            h.update(extra)
        return h

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            proxy = self._next_proxy()
            try:
                with httpx.Client(
                    follow_redirects=True,
                    timeout=self.timeout,
                    proxies=proxy,
                    headers=self._headers(kwargs.pop("headers", None)),
                ) as client:
                    resp = client.request(method, url, **kwargs)
                    # 429/5xx -> retryable
                    if resp.status_code in (429, 500, 502, 503, 504) and attempt < self.retries:
                        time.sleep(self.backoff * (attempt + 1))
                        continue
                    return resp
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt < self.retries:
                    time.sleep(self.backoff * (attempt + 1))
        raise (last_exc or httpx.TransportError("request failed"))

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)


def build_netclient(settings: dict[str, str] | None = None, env: dict | None = None) -> NetClient:
    """Build a NetClient from app settings / environment."""
    import os

    settings = settings or {}
    proxy_spec = (
        settings.get("PROXY_URL")
        or (env or os.environ).get("FLEETLEADS_PROXY")
    )
    proxies = parse_proxies(proxy_spec)
    try:
        retries = int(settings.get("REQUEST_RETRIES", "2"))
    except ValueError:
        retries = 2
    try:
        timeout = float(settings.get("REQUEST_TIMEOUT", "20"))
    except ValueError:
        timeout = 20.0
    return NetClient(proxies=proxies, timeout=timeout, retries=retries)
