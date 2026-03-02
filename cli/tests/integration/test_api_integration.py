from __future__ import annotations

import json

import httpx
import pytest

from cxpm_cli.client.api import APIClient
from cxpm_cli.errors import AuthError, ConflictError
from cxpm_cli.workflows.resolve_flow import build_decisions_from_strategy, resolve_payload


class FakeBackend:
    def __init__(self, *, idempotency: bool = True, revision_conflict: bool = True) -> None:
        self.idempotency = idempotency
        self.revision_conflict = revision_conflict
        self.meeting_revision = "rev1"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        method = request.method.upper()
        if path == "/api/version":
            return httpx.Response(
                200,
                json={
                    "compatible": True,
                    "features": {"idempotency": self.idempotency, "revision_conflict": self.revision_conflict},
                },
            )
        if path == "/api/auth/login" and method == "POST":
            return httpx.Response(200, json={"access_token": "tok", "refresh_token": "ref"})
        if path == "/api/auth/me" and method == "GET":
            auth_header = request.headers.get("authorization")
            if not auth_header:
                return httpx.Response(401, json={"detail": "unauthorized"})
            if auth_header == "Bearer expired":
                return httpx.Response(401, json={"detail": "expired"})
            return httpx.Response(200, json={"user_id": "u1", "email": "u@example.com", "name": "User"})
        if path == "/api/auth/refresh" and method == "POST":
            payload = json.loads(request.content.decode("utf-8"))
            if payload.get("refresh_token") == "ref":
                return httpx.Response(200, json={"access_token": "tok2", "refresh_token": "ref2"})
            return httpx.Response(401, json={"detail": "bad refresh"})
        if path == "/api/meetings/upload":
            return httpx.Response(200, json={"meeting_id": "m1"})
        if path == "/api/meetings/m1":
            return httpx.Response(200, json={"meeting_id": "m1"})
        if path == "/api/meetings/m1/apply":
            return httpx.Response(
                200,
                json={
                    "added": [],
                    "skipped": [],
                    "conflicts": [
                        {
                            "conflict_id": "c1",
                            "existing_requirement": "A",
                            "new_item": "B",
                            "classification": "duplicate",
                            "reason": "same goal",
                        }
                    ],
                    "revision": self.meeting_revision,
                },
            )
        if path == "/api/meetings/m1/resolve":
            if self.revision_conflict and request.headers.get("If-Match") != self.meeting_revision:
                return httpx.Response(409, json={"expected_revision": self.meeting_revision})
            return httpx.Response(200, json={"applied": True, "resolved": 1, "remaining": 0})
        if path == "/api/projects/p1/requirements":
            return httpx.Response(
                200,
                json={
                    "items": [{"id": "r1", "text": "A", "updated_at": "2026-03-02T00:00:00Z"}],
                    "next_cursor": None,
                    "total_count": 1,
                },
            )
        if path == "/api/projects/p1/requirements/export":
            return httpx.Response(200, json={"markdown": "# Requirements\n- A"})
        if path == "/api/jira-epic/generate":
            return httpx.Response(200, json={"title": "Epic", "description": "Desc", "stories": []})
        if path == "/api/jira-stories/save":
            return httpx.Response(200, json={"saved": True})
        if path == "/api/projects":
            return httpx.Response(200, json={"items": [{"id": "p1", "name": "Project"}]})
        if path == "/api/auth/logout":
            return httpx.Response(200, json={"revoked": True})
        return httpx.Response(404, json={"detail": path})


def test_happy_path_end_to_end():
    backend = FakeBackend()
    client = APIClient("http://example.test", transport=httpx.MockTransport(backend))
    client.detect_capabilities()
    auth = client.login(username="u", password="p")
    client.token = auth.access_token
    me = client.me()
    assert me.user_id == "u1"
    ingest = client.upload_meeting(text="hello", file_path=None)
    apply = client.apply_meeting(ingest["meeting_id"])
    decisions = build_decisions_from_strategy(apply["conflicts"], "keep-existing")
    payload = resolve_payload(apply["revision"], decisions)
    resolved = client.resolve_meeting("m1", payload, revision=apply["revision"])
    assert resolved["applied"] is True
    reqs = client.list_requirements("p1", page_size=50, cursor=None, sort=None, filters=[])
    assert reqs["total_count"] == 1
    export = client.export_requirements("p1")
    assert "Requirements" in export["markdown"]
    client.close()


def test_auth_refresh_path():
    backend = FakeBackend()
    client = APIClient("http://example.test", token="expired", refresh_token="ref", transport=httpx.MockTransport(backend))
    client.detect_capabilities()
    me = client.me()
    assert me.email == "u@example.com"
    assert client.token == "tok2"
    client.close()


def test_auth_failure_when_refresh_fails():
    backend = FakeBackend()
    client = APIClient("http://example.test", token="expired", refresh_token="bad", transport=httpx.MockTransport(backend))
    client.detect_capabilities()
    with pytest.raises(AuthError):
        client.me()
    client.close()


def test_revision_conflict_raises_conflict_error():
    backend = FakeBackend(revision_conflict=True)
    client = APIClient("http://example.test", token="tok", transport=httpx.MockTransport(backend))
    client.detect_capabilities()
    with pytest.raises(ConflictError):
        client.resolve_meeting("m1", {"decisions": []}, revision="wrong")
    client.close()


def test_capability_downgrade_warnings():
    backend = FakeBackend(idempotency=False, revision_conflict=False)
    client = APIClient("http://example.test", token="tok", transport=httpx.MockTransport(backend))
    caps = client.detect_capabilities()
    assert caps.idempotency is False
    assert caps.revision_conflict is False
    assert len(client.warnings) >= 2
    client.close()
