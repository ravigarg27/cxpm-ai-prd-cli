from __future__ import annotations

import json

import pytest

from cxpm_cli.errors import UsageError
from cxpm_cli.workflows.resolve_flow import (
    build_decisions_from_strategy,
    parse_decisions_file,
    resolve_payload,
    validate_decisions,
)


def test_parse_decisions_file_success(runtime_root):
    path = runtime_root / "decisions-success.json"
    path.write_text(
        json.dumps(
            {
                "meeting_id": "m1",
                "base_revision": "rev1",
                "decisions": [{"conflict_id": "c1", "action": "keep"}],
            }
        ),
        encoding="utf-8",
    )
    base_revision, decisions = parse_decisions_file(str(path), "m1")
    assert base_revision == "rev1"
    assert len(decisions) == 1
    assert decisions[0].conflict_id == "c1"


def test_parse_decisions_file_requires_merge_text(runtime_root):
    path = runtime_root / "decisions-merge.json"
    path.write_text(
        json.dumps(
            {
                "meeting_id": "m1",
                "decisions": [{"conflict_id": "c1", "action": "merge"}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(UsageError):
        parse_decisions_file(str(path), "m1")


def test_strategy_builds_expected_actions():
    conflicts = [{"conflict_id": "c1"}, {"conflict_id": "c2"}]
    decisions = build_decisions_from_strategy(conflicts, "replace-all")
    assert [d.action for d in decisions] == ["replace", "replace"]


def test_validate_decisions_detects_missing():
    conflicts = [{"conflict_id": "c1"}, {"conflict_id": "c2"}]
    decisions = build_decisions_from_strategy([{"conflict_id": "c1"}], "keep-existing")
    with pytest.raises(UsageError):
        validate_decisions(conflicts, decisions)


def test_resolve_payload_shape():
    conflicts = [{"conflict_id": "c1"}]
    decisions = build_decisions_from_strategy(conflicts, "keep-existing")
    payload = resolve_payload("rev-1", decisions)
    assert payload["base_revision"] == "rev-1"
    assert payload["decisions"][0]["action"] == "keep"
