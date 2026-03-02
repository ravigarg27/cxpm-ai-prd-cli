from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cxpm_cli.errors import UsageError
from cxpm_cli.ui.interactive import ask_action, ask_multiline


VALID_STRATEGIES = {"keep-existing", "replace-all", "accept-ai"}
VALID_ACTIONS = {"keep", "replace", "both", "merge"}


@dataclass
class ResolveDecision:
    conflict_id: str
    action: str
    merged_text: str | None = None


def parse_decisions_file(path: str, meeting_id: str) -> tuple[str | None, list[ResolveDecision]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("meeting_id") != meeting_id:
        raise UsageError("Decision file meeting_id does not match command meeting-id", error_code="DECISION_FILE_MEETING_MISMATCH")
    decisions = []
    for item in data.get("decisions", []):
        action = item.get("action")
        if action not in VALID_ACTIONS:
            raise UsageError(f"Invalid decision action: {action}", error_code="DECISION_FILE_INVALID_ACTION")
        merged_text = item.get("merged_text")
        if action == "merge" and not merged_text:
            raise UsageError("merged_text is required for merge action", error_code="DECISION_FILE_MISSING_MERGE_TEXT")
        decisions.append(ResolveDecision(conflict_id=item["conflict_id"], action=action, merged_text=merged_text))
    return data.get("base_revision"), decisions


def build_decisions_from_strategy(conflicts: list[dict[str, Any]], strategy: str) -> list[ResolveDecision]:
    if strategy not in VALID_STRATEGIES:
        raise UsageError("Invalid decision strategy", error_code="INVALID_DECISION_STRATEGY")
    actions = {
        "keep-existing": "keep",
        "replace-all": "replace",
        "accept-ai": "replace",
    }
    action = actions[strategy]
    return [ResolveDecision(conflict_id=conf["conflict_id"], action=action) for conf in conflicts]


def interactive_resolve(conflicts: list[dict[str, Any]]) -> list[ResolveDecision]:
    decisions: list[ResolveDecision] = []
    i = 0
    while i < len(conflicts):
        conflict = conflicts[i]
        print(f"\nConflict {i + 1}/{len(conflicts)}")
        print(f"ID: {conflict['conflict_id']}")
        print(f"Existing: {conflict.get('existing_requirement', '')}")
        print(f"New: {conflict.get('new_item', '')}")
        print(f"Classification: {conflict.get('classification', '')}")
        print(f"Reason: {conflict.get('reason', '')}")
        action_key = ask_action({"k", "r", "b", "m", "s", "p"})
        if action_key == "p":
            i = max(i - 1, 0)
            if decisions:
                decisions.pop()
            continue
        if action_key == "s":
            i += 1
            continue
        mapping = {"k": "keep", "r": "replace", "b": "both", "m": "merge"}
        action = mapping[action_key]
        merged_text = None
        if action == "merge":
            merged_text = ask_multiline("Enter merged text")
        decisions.append(ResolveDecision(conflict_id=conflict["conflict_id"], action=action, merged_text=merged_text))
        i += 1
    return decisions


def validate_decisions(
    conflicts: list[dict[str, Any]],
    decisions: list[ResolveDecision],
) -> None:
    conflict_ids = {item["conflict_id"] for item in conflicts}
    decision_ids = {item.conflict_id for item in decisions}
    unknown = decision_ids - conflict_ids
    if unknown:
        raise UsageError("Unknown conflict ids in decisions", error_code="UNKNOWN_CONFLICT_IDS", details={"ids": sorted(unknown)})
    missing = conflict_ids - decision_ids
    if missing:
        raise UsageError("Missing decisions for conflicts", error_code="MISSING_CONFLICT_DECISIONS", details={"ids": sorted(missing)})


def resolve_payload(base_revision: str | None, decisions: list[ResolveDecision]) -> dict[str, Any]:
    return {
        "base_revision": base_revision,
        "decisions": [
            {
                "conflict_id": item.conflict_id,
                "action": item.action,
                **({"merged_text": item.merged_text} if item.merged_text else {}),
            }
            for item in decisions
        ],
        "submitted_at": datetime.now(UTC).isoformat(),
    }
