from __future__ import annotations

import json

import pytest

from cxpm_cli.errors import UsageError
from cxpm_cli.workflows.resolve_flow import (
    build_non_conflict_decisions,
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
                "decisions": [
                    {
                        "item_id": "i1",
                        "decision": "conflict_keep_existing",
                        "matched_requirement_id": "r1",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    base_revision, decisions = parse_decisions_file(str(path), "m1")
    assert base_revision == "rev1"
    assert len(decisions) == 1
    assert decisions[0].item_id == "i1"
    assert decisions[0].decision == "conflict_keep_existing"


def test_parse_decisions_file_requires_merge_text(runtime_root):
    path = runtime_root / "decisions-merge.json"
    path.write_text(
        json.dumps(
            {
                "meeting_id": "m1",
                "decisions": [
                    {
                        "item_id": "i1",
                        "decision": "conflict_merged",
                        "matched_requirement_id": "r1",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(UsageError):
        parse_decisions_file(str(path), "m1")


def test_strategy_builds_expected_actions():
    conflicts = [
        {"item_id": "i1", "matched_requirement": {"id": "r1"}},
        {"item_id": "i2", "matched_requirement": {"id": "r2"}},
    ]
    decisions = build_decisions_from_strategy(conflicts, "replace-all")
    assert [d.decision for d in decisions] == ["conflict_replaced", "conflict_replaced"]
    assert [d.matched_requirement_id for d in decisions] == ["r1", "r2"]


def test_validate_decisions_detects_missing():
    conflicts = [{"item_id": "i1"}, {"item_id": "i2"}]
    decisions = build_decisions_from_strategy([{"item_id": "i1", "matched_requirement": {"id": "r1"}}], "keep-existing")
    with pytest.raises(UsageError):
        validate_decisions(conflicts, decisions)


def test_resolve_payload_shape():
    conflicts = [{"item_id": "i1", "matched_requirement": {"id": "r1"}}]
    decisions = build_decisions_from_strategy(conflicts, "keep-existing")
    payload = resolve_payload("rev-1", decisions)
    assert payload["base_revision"] == "rev-1"
    assert payload["decisions"][0]["item_id"] == "i1"
    assert payload["decisions"][0]["decision"] == "conflict_keep_existing"
    assert payload["decisions"][0]["matched_requirement_id"] == "r1"


def test_build_non_conflict_decisions_from_apply_result():
    apply_result = {
        "added": [{"item_id": "i1", "decision": "added"}],
        "skipped": [
            {
                "item_id": "i2",
                "decision": "skipped_duplicate",
                "matched_requirement": {"id": "r2"},
            }
        ],
    }
    decisions = build_non_conflict_decisions(apply_result)
    assert [d.item_id for d in decisions] == ["i1", "i2"]
    assert [d.decision for d in decisions] == ["added", "skipped_duplicate"]
    assert decisions[1].matched_requirement_id == "r2"
