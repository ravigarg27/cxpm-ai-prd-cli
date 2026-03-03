from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from cxpm_cli.main import app
from cxpm_cli.runtime import AppContext


class FakeClient:
    def __init__(self) -> None:
        self.request_id = "req-1"
        self.last_item_create_payload = None
        self.last_item_update_payload = None
        self.last_resolve_payload = None
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

    def upload_meeting(self, *, text=None, file_path=None, project_id=None, title=None, meeting_date=None):
        return {
            "meeting_id": "m1",
            "status": "uploaded",
            "input": text or file_path,
            "project_id": project_id,
            "title": title,
            "meeting_date": meeting_date,
        }

    def get_meeting(self, meeting_id):
        return {"meeting_id": meeting_id, "apply_result": {"conflicts": [], "revision": "rev1"}}

    def apply_meeting(self, meeting_id, revision=None):
        return {"meeting_id": meeting_id, "added": [], "skipped": [], "conflicts": [], "revision": revision or "rev1"}

    def resolve_meeting(self, meeting_id, payload, revision=None):
        self.last_resolve_payload = payload
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

    def create_project(self, name, description=None):
        return {"id": "p2", "name": name, "description": description}

    def create_meeting_item(self, meeting_id, payload):
        self.last_item_create_payload = payload
        return {"id": "i1", "meeting_id": meeting_id, **payload}

    def update_meeting_item(self, meeting_id, item_id, payload):
        self.last_item_update_payload = payload
        return {"id": item_id, "meeting_id": meeting_id, **payload}

    def delete_meeting_item(self, meeting_id, item_id):
        return {"id": item_id, "meeting_id": meeting_id, "deleted": True}


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


def test_meeting_resolve_includes_added_and_skipped_decisions(monkeypatch):
    class ResolveClient(FakeClient):
        def get_meeting(self, meeting_id):
            return {
                "meeting_id": meeting_id,
                "apply_result": {
                    "added": [{"item_id": "i1", "decision": "added"}],
                    "skipped": [
                        {
                            "item_id": "i2",
                            "decision": "skipped_duplicate",
                            "matched_requirement": {"id": "r2"},
                        }
                    ],
                    "conflicts": [
                        {
                            "item_id": "i3",
                            "item_content": "new requirement text",
                            "matched_requirement": {"id": "r3", "content": "existing text"},
                            "classification": "refinement",
                            "reason": "same requirement, updated wording",
                        }
                    ],
                },
            }

    def builder(self: AppContext):
        self.warnings = []
        return ResolveClient()

    monkeypatch.setattr(AppContext, "build_client", builder)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["--json", "--non-interactive", "meeting", "resolve", "m1", "--decision-strategy", "keep-existing"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    decisions = payload["data"]["payload"]["decisions"]
    assert any(item["item_id"] == "i1" and item["decision"] == "added" for item in decisions)
    assert any(item["item_id"] == "i2" and item["decision"] == "skipped_duplicate" for item in decisions)
    assert any(item["item_id"] == "i3" and item["decision"] == "conflict_keep_existing" for item in decisions)


def test_project_create_json(monkeypatch):
    _patch_client(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(app, ["--json", "project", "create", "--name", "New Project"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "project create"
    assert payload["data"]["name"] == "New Project"


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


def test_meeting_item_add_uses_section_and_content(monkeypatch):
    captured: dict[str, object] = {}

    class ItemClient(FakeClient):
        def create_meeting_item(self, meeting_id, payload):
            captured["meeting_id"] = meeting_id
            captured["payload"] = payload
            return {"id": "i1", "meeting_id": meeting_id, **payload}

    def builder(self: AppContext):
        self.warnings = []
        return ItemClient()

    monkeypatch.setattr(AppContext, "build_client", builder)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--json",
            "meeting",
            "item",
            "add",
            "--meeting-id",
            "m1",
            "--section",
            "requirements",
            "--content",
            "Capture deployment requirement",
        ],
    )
    assert result.exit_code == 0
    assert captured["meeting_id"] == "m1"
    assert captured["payload"] == {
        "section": "requirements",
        "content": "Capture deployment requirement",
    }


def test_meeting_item_edit_uses_content_field(monkeypatch):
    captured: dict[str, object] = {}

    class ItemClient(FakeClient):
        def update_meeting_item(self, meeting_id, item_id, payload):
            captured["meeting_id"] = meeting_id
            captured["item_id"] = item_id
            captured["payload"] = payload
            return {"id": item_id, "meeting_id": meeting_id, **payload}

    def builder(self: AppContext):
        self.warnings = []
        return ItemClient()

    monkeypatch.setattr(AppContext, "build_client", builder)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--json",
            "meeting",
            "item",
            "edit",
            "--meeting-id",
            "m1",
            "--item-id",
            "i1",
            "--content",
            "Updated wording",
        ],
    )
    assert result.exit_code == 0
    assert captured["meeting_id"] == "m1"
    assert captured["item_id"] == "i1"
    assert captured["payload"] == {"content": "Updated wording"}


def test_requirement_ls_section_filters_grouped_response(monkeypatch):
    class SectionClient(FakeClient):
        def list_requirements(self, project_id, *, page_size, cursor, sort, filters):
            return {
                "needs_and_goals": [{"id": "n1", "content": "Need"}],
                "requirements": [{"id": "r1", "content": "Req"}],
                "scope_and_constraints": [],
                "risks_and_questions": [{"id": "q1", "content": "Risk"}],
                "action_items": [{"id": "a1", "content": "Action 1"}, {"id": "a2", "content": "Action 2"}],
            }

    def builder(self: AppContext):
        self.warnings = []
        return SectionClient()

    monkeypatch.setattr(AppContext, "build_client", builder)
    runner = CliRunner()
    result = runner.invoke(app, ["--json", "requirement", "ls", "--project-id", "p1", "--section", "action-items"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    data = payload["data"]
    assert data["section"] == "action_items"
    assert data["total_count"] == 2
    assert len(data["action_items"]) == 2
    assert data["needs_and_goals"] == []
    assert data["requirements"] == []
    assert data["scope_and_constraints"] == []
    assert data["risks_and_questions"] == []


def test_requirement_ls_rejects_invalid_section(monkeypatch):
    _patch_client(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(app, ["--json", "requirement", "ls", "--project-id", "p1", "--section", "not-a-section"])
    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "INVALID_SECTION"


def test_meeting_ingest_follow_stream_includes_query_token(monkeypatch):
    captured: dict[str, str] = {}

    class FollowClient(FakeClient):
        api_url = "http://example.test"
        token = "tok-value"
        _client = object()

        def _base_headers(self):
            return {"Authorization": "Bearer tok-value"}

    def builder(self: AppContext):
        self.warnings = []
        return FollowClient()

    def fake_stream_events(client, url, headers):
        captured["url"] = url
        captured["authorization"] = headers.get("Authorization", "")
        yield {"item_count": 1}

    monkeypatch.setattr(AppContext, "build_client", builder)
    monkeypatch.setattr("cxpm_cli.commands.meeting.stream_events", fake_stream_events)

    runner = CliRunner()
    result = runner.invoke(app, ["--json", "meeting", "ingest", "--text", "hello", "--follow"])
    assert result.exit_code == 0
    assert "token=tok-value" in captured["url"]
    assert captured["authorization"] == "Bearer tok-value"
