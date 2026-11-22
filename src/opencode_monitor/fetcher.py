"""HTTP fetching with timeouts, retries, and backoff."""

from __future__ import annotations

import time
from collections.abc import Callable

import httpx

USER_AGENT = (
    "opencode-deals-monitor/0.1 "
    "(+https://github.com/example/opencode-deals-monitor; daily GitHub Actions run)"
)

# Transient failures are retried twice: 2s then 5s.
RETRY_DELAYS: tuple[float, ...] = (2.0, 5.0)

TIMEOUT = httpx.Timeout(15.0, connect=5.0)


class FetchError(Exception):
    """Raised when a URL could not be fetched after retries."""

    def __init__(self, url: str, status: int | None, reason: str) -> None:
        self.url = url
        self.status = status
        self.reason = reason
        super().__init__(f"fetch failed for {url}: status={status} reason={reason}")


def _is_transient(exc: httpx.HTTPError) -> bool:
    """Network errors, timeouts, and connection problems are transient."""
    return isinstance(
        exc,
        httpx.TransportError
        | httpx.TimeoutException
        | httpx.NetworkError
        | httpx.ProtocolError
        | httpx.ProxyError
        | httpx.UnsupportedProtocol,
    )


def fetch_text(
    url: str,
    *,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Fetch a URL as text, retrying transient failures up to 2 times.

    ``4xx`` responses are never retried. Raises FetchError on final failure.
    """
    owned_client = client is None
    if client is None:
        client = httpx.Client(
            timeout=TIMEOUT,
            follow_redirects=True,
            verify=True,
        )
    try:
        last_error: Exception | None = None
        for attempt in range(len(RETRY_DELAYS) + 1):
            if attempt > 0:
                sleep(RETRY_DELAYS[attempt - 1])
            try:
                response = client.get(url, headers={"User-Agent": USER_AGENT})
            except httpx.HTTPError as exc:
                if not _is_transient(exc):
                    raise FetchError(url, None, repr(exc)) from exc
                last_error = exc
                continue
            if response.status_code >= 500:
                last_error = FetchError(url, response.status_code, "server error")
                continue
            if response.status_code >= 400:
                raise FetchError(url, response.status_code, "client error")
            return response.text
        assert last_error is not None  # pragma: no cover - loop always sets it
        raise FetchError(url, None, repr(last_error))
    finally:
        if owned_client:
            client.close()
