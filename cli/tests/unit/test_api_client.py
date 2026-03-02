from __future__ import annotations

import httpx
import pytest

from cxpm_cli.client.api import APIClient
from cxpm_cli.errors import APIError


def test_get_retries_on_transport_error():
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, json={"ok": True})

    client = APIClient("http://example.test", transport=httpx.MockTransport(handler))
    result = client._request("GET", "/any")
    assert result["ok"] is True
    assert attempts["count"] == 3
    client.close()


def test_mutation_does_not_retry_when_idempotency_unavailable():
    attempts = {"count": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(500, json={"error": "server"})

    client = APIClient("http://example.test", transport=httpx.MockTransport(handler))
    client.capabilities.idempotency = False
    with pytest.raises(APIError):
        client._request("POST", "/mutate", json_body={"x": 1}, mutating=True)
    assert attempts["count"] == 1
    client.close()


def test_detect_capabilities_unknown_when_endpoint_missing():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(404, json={"detail": "not found"})
        return httpx.Response(200, json={})

    client = APIClient("http://example.test", transport=httpx.MockTransport(handler))
    caps = client.detect_capabilities()
    assert caps.compatibility_state == "unknown"
    assert client.warnings
    client.close()
