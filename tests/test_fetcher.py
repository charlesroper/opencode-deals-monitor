"""Fetcher tests: retry policy with a mocked httpx transport."""

from __future__ import annotations

import httpx
import pytest

from opencode_monitor.fetcher import FetchError, fetch_text

URL = "https://example.test/api"


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_success_returns_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="payload")

    with _client(handler) as client:
        assert fetch_text(URL, client=client, sleep=lambda _: None) == "payload"


def test_retries_5xx_then_succeeds() -> None:
    calls: list[int] = []
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(503)
        return httpx.Response(200, text="ok")

    with _client(handler) as client:
        result = fetch_text(URL, client=client, sleep=delays.append)
    assert result == "ok"
    assert len(calls) == 3
    assert delays == [2.0, 5.0]


def test_gives_up_after_two_retries() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(500)

    with _client(handler) as client, pytest.raises(FetchError):
        fetch_text(URL, client=client, sleep=lambda _: None)
    assert len(calls) == 3  # one attempt plus two retries


def test_4xx_not_retried() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(403)

    with _client(handler) as client, pytest.raises(FetchError) as excinfo:
        fetch_text(URL, client=client, sleep=lambda _: None)
    assert excinfo.value.status == 403
    assert len(calls) == 1


def test_network_error_retried_then_raised() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise httpx.ConnectError("boom", request=request)

    with _client(handler) as client, pytest.raises(FetchError):
        fetch_text(URL, client=client, sleep=lambda _: None)
    assert len(calls) == 3


def test_user_agent_sent() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["ua"] = request.headers.get("user-agent", "")
        return httpx.Response(200, text="ok")

    from opencode_monitor.fetcher import USER_AGENT

    with _client(handler) as client:
        fetch_text(URL, client=client, sleep=lambda _: None)
    assert USER_AGENT in seen["ua"]


def test_url_exists() -> None:
    from opencode_monitor.fetcher import url_exists

    def ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    def missing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with _client(ok) as client:
        assert url_exists(URL, client=client) is True
    with _client(missing) as client:
        assert url_exists(URL, client=client) is False
    with _client(broken) as client:
        assert url_exists(URL, client=client) is None


def test_url_exists_uses_head() -> None:
    from opencode_monitor.fetcher import url_exists

    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        return httpx.Response(200)

    with _client(handler) as client:
        url_exists(URL, client=client)
    assert methods == ["HEAD"]
