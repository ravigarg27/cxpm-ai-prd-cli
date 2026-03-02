from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from cxpm_cli.main import app
from cxpm_cli.runtime import AppContext


class FakeClient:
    def __init__(self) -> None:
        self.request_id = "req-1"
        self.capabilities = type(
            "Caps",
            (),
            {
                "compatibility_state": "known",
                "model_dump": lambda self: {
                    "idempotency": True,
                    "revision_conflict": True,
                    "compatibility_metadata": True,
                    "compatibility_state": "known",
                },
            },
        )()

    def login(self, username=None, password=None, token=None):
        return type("Login", (), {"access_token": token or "tok", "refresh_token": "ref"})()

    def me(self):
        return type("Me", (), {"user_id": "u1", "email": "u@example.com", "name": "User"})()

    def logout(self):
        return {"revoked": True}

    def upload_meeting(self, *, text=None, file_path=None, project_id=None):
        return {"meeting_id": "m1", "status": "uploaded", "input": text or file_path, "project_id": project_id}

    def get_meeting(self, meeting_id):
        return {"meeting_id": meeting_id, "apply_result": {"conflicts": [], "revision": "rev1"}}

    def apply_meeting(self, meeting_id, revision=None):
        return {"meeting_id": meeting_id, "added": [], "skipped": [], "conflicts": [], "revision": revision or "rev1"}

    def resolve_meeting(self, meeting_id, payload, revision=None):
        return {"meeting_id": meeting_id, "applied": True, "revision": revision, "payload": payload}

    def list_requirements(self, project_id, *, page_size, cursor, sort, filters):
        return {
            "items": [{"id": "r1", "text": "A", "updated_at": "2026-03-02T00:00:00Z"}],
            "next_cursor": None,
            "total_count": 1,
        }

    def export_requirements(self, project_id):
        return {"markdown": "# Requirements\n- A", "project_id": project_id}

    def generate_epic(self, project_id, requirements_text=None):
        return {"title": "Epic", "description": "Desc", "stories": []}

    def save_stories(self, payload):
        return {"saved": True, "count": len(payload.get("stories", []))}

    def list_projects(self):
        return {"items": [{"id": "p1", "name": "P"}]}


def _patch_client(monkeypatch):
    def builder(self: AppContext):
        self.warnings = []
        return FakeClient()

    monkeypatch.setattr(AppContext, "build_client", builder)


def test_version_json(monkeypatch):
    _patch_client(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(app, ["--json", "version"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "version"
    assert payload["status"] == "success"


def test_auth_login_json(monkeypatch):
    _patch_client(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(app, ["--json", "--non-interactive", "auth", "login", "--token", "abc"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["data"]["email"] == "u@example.com"


def test_meeting_resolve_non_interactive_strategy(monkeypatch):
    _patch_client(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["--json", "--non-interactive", "meeting", "resolve", "m1", "--decision-strategy", "keep-existing"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "meeting resolve"


def test_requirement_ls_validates_page_size(monkeypatch):
    _patch_client(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(app, ["--json", "requirement", "ls", "--project-id", "p1", "--page-size", "400"])
    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "INVALID_PAGE_SIZE"


def test_requirement_export_writes_file(monkeypatch, runtime_root: Path):
    _patch_client(monkeypatch)
    out = runtime_root / "reqs.md"
    runner = CliRunner()
    result = runner.invoke(app, ["--json", "requirement", "export", "--project-id", "p1", "--out", str(out)])
    assert result.exit_code == 0
    assert out.exists()


def test_jira_generate_and_save(monkeypatch):
    _patch_client(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(app, ["--json", "jira", "epic", "generate", "--project-id", "p1", "--save"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["data"]["save_result"]["saved"] is True
