from __future__ import annotations

import json

import httpx
import pytest

from cxpm_cli.client.api import APIClient
from cxpm_cli.errors import AuthError, ConflictError
from cxpm_cli.workflows.resolve_flow import build_decisions_from_strategy, resolve_payload


class FakeBackend:
    def __init__(self, *, revision_conflict: bool = True) -> None:
        self.revision_conflict = revision_conflict
        self.meeting_revision = "rev1"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        method = request.method.upper()
        if path == "/api/health":
            return httpx.Response(200, json={"status": "ok"})
        if path == "/api/auth/login" and method == "POST":
            return httpx.Response(200, json={"access_token": "tok", "refresh_token": "ref"})
        if path == "/api/auth/me" and method == "GET":
            auth_header = request.headers.get("authorization")
            if not auth_header:
                return httpx.Response(401, json={"detail": "unauthorized"})
            if auth_header == "Bearer expired":
                return httpx.Response(401, json={"detail": "expired"})
            return httpx.Response(200, json={"user_id": "u1", "email": "u@example.com", "name": "User"})
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
                            "item_id": "i1",
                            "item_section": "requirements",
                            "item_content": "B",
                            "decision": "conflict",
                            "classification": "duplicate",
                            "reason": "same goal",
                            "matched_requirement": {
                                "id": "r1",
                                "section": "requirements",
                                "content": "A",
                            },
                        }
                    ],
                    "revision": self.meeting_revision,
                },
            )
        if path == "/api/meetings/m1/resolve":
            if self.revision_conflict and request.headers.get("If-Match") != self.meeting_revision:
                return httpx.Response(409, json={"expected_revision": self.meeting_revision})
            payload = json.loads(request.content.decode("utf-8"))
            decisions = payload.get("decisions", [])
            if not decisions:
                return httpx.Response(422, json={"detail": "decisions required"})
            first = decisions[0]
            if first.get("item_id") != "i1" or first.get("decision") != "conflict_keep_existing":
                return httpx.Response(422, json={"detail": "invalid decision payload"})
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


def test_auth_expired_raises_auth_error():
    backend = FakeBackend()
    client = APIClient("http://example.test", token="expired", refresh_token="ref", transport=httpx.MockTransport(backend))
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


def test_capability_state_is_unknown_without_version_endpoint():
    backend = FakeBackend()
    client = APIClient("http://example.test", token="tok", transport=httpx.MockTransport(backend))
    caps = client.detect_capabilities()
    assert caps.compatibility_state == "unknown"
    assert caps.compatibility_metadata is False
    assert client.warnings
    client.close()
