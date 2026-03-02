from __future__ import annotations

import json

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


def test_login_falls_back_to_email_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/auth/login":
            payload = {}
            if request.content:
                try:
                    payload = json.loads(request.content.decode("utf-8"))
                except Exception:
                    payload = {}
            if payload.get("email") == "user@example.com":
                return httpx.Response(200, json={"access_token": "tok", "refresh_token": "ref"})
            return httpx.Response(422, json={"detail": "email required"})
        return httpx.Response(404, json={})

    client = APIClient("http://example.test", transport=httpx.MockTransport(handler))
    login = client.login(username="user@example.com", password="pw")
    assert login.access_token == "tok"
    client.close()


def test_login_accepts_nested_data_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/auth/login":
            return httpx.Response(200, json={"data": {"access_token": "tok", "refresh_token": "ref"}})
        return httpx.Response(404, json={})

    client = APIClient("http://example.test", transport=httpx.MockTransport(handler))
    login = client.login(username="u", password="p")
    assert login.access_token == "tok"
    client.close()


def test_login_request_does_not_send_authorization_header():
    seen_auth_headers = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/auth/login":
            seen_auth_headers.append(request.headers.get("authorization"))
            return httpx.Response(200, json={"access_token": "tok", "refresh_token": "ref"})
        return httpx.Response(404, json={})

    client = APIClient("http://example.test", token="stale-token", transport=httpx.MockTransport(handler))
    login = client.login(username="u", password="p")
    assert login.access_token == "tok"
    assert seen_auth_headers == [None]
    client.close()


def test_me_parses_id_field_shape():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/auth/me":
            return httpx.Response(200, json={"id": "u-1", "email": "user@example.com", "name": "User"})
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"compatible": True, "features": {"idempotency": True, "revision_conflict": True}})
        return httpx.Response(404, json={})

    client = APIClient("http://example.test", token="tok", transport=httpx.MockTransport(handler))
    client.detect_capabilities()
    me = client.me()
    assert me.user_id == "u-1"
    assert me.email == "user@example.com"
    client.close()


def test_upload_meeting_falls_back_to_multipart_file_shape(runtime_root):
    calls = {"count": 0}
    sample = runtime_root / "sample-upload.txt"
    sample.write_text("hello transcript", encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/meetings/upload":
            calls["count"] += 1
            if calls["count"] == 1:
                return httpx.Response(422, json={"detail": "invalid json payload"})
            return httpx.Response(200, json={"meeting_id": "m1"})
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"compatible": True, "features": {"idempotency": True, "revision_conflict": True}})
        return httpx.Response(404, json={})

    client = APIClient("http://example.test", token="tok", transport=httpx.MockTransport(handler))
    client.detect_capabilities()
    result = client.upload_meeting(text=None, file_path=str(sample), project_id="p1")
    assert result["meeting_id"] == "m1"
    assert calls["count"] >= 2
    client.close()


def test_upload_meeting_text_includes_project_id_variants():
    seen_payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/meetings/upload":
            payload = json.loads(request.content.decode("utf-8")) if request.content else {}
            seen_payloads.append(payload)
            if "projectId" in payload and "transcript" in payload:
                return httpx.Response(200, json={"meeting_id": "m1"})
            return httpx.Response(422, json={"detail": "shape mismatch"})
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"compatible": True, "features": {"idempotency": True, "revision_conflict": True}})
        return httpx.Response(404, json={})

    client = APIClient("http://example.test", token="tok", transport=httpx.MockTransport(handler))
    client.detect_capabilities()
    result = client.upload_meeting(text="hello", file_path=None, project_id="p1")
    assert result["meeting_id"] == "m1"
    assert any("project_id" in payload for payload in seen_payloads)
    assert any("projectId" in payload for payload in seen_payloads)
    client.close()
