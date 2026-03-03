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
VALID_CONFLICT_DECISIONS = {
    "conflict_keep_existing",
    "conflict_replaced",
    "conflict_kept_both",
    "conflict_merged",
}
VALID_NON_CONFLICT_DECISIONS = {"added", "skipped_duplicate", "skipped_semantic"}
VALID_DECISIONS = VALID_CONFLICT_DECISIONS | VALID_NON_CONFLICT_DECISIONS


@dataclass
class ResolveDecision:
    item_id: str
    decision: str
    matched_requirement_id: str | None = None
    merged_text: str | None = None


def _conflict_item_id(conflict: dict[str, Any]) -> str:
    item_id = conflict.get("item_id") or conflict.get("conflict_id")
    if not item_id:
        raise UsageError("Conflict item is missing item_id", error_code="MISSING_CONFLICT_ITEM_ID")
    return str(item_id)


def _matched_requirement_id(conflict: dict[str, Any]) -> str | None:
    matched = conflict.get("matched_requirement")
    if isinstance(matched, dict) and matched.get("id"):
        return str(matched["id"])
    matched_id = conflict.get("matched_requirement_id")
    if matched_id:
        return str(matched_id)
    return None


def _decision_from_action(action: str) -> str:
    mapping = {
        "keep": "conflict_keep_existing",
        "replace": "conflict_replaced",
        "both": "conflict_kept_both",
        "merge": "conflict_merged",
    }
    decision = mapping.get(action)
    if not decision:
        raise UsageError(f"Invalid decision action: {action}", error_code="DECISION_FILE_INVALID_ACTION")
    return decision


def _require_matched_requirement_id(item_id: str, decision: str, matched_requirement_id: str | None) -> None:
    if decision in VALID_CONFLICT_DECISIONS and not matched_requirement_id:
        raise UsageError(
            f"Decision '{decision}' for item '{item_id}' requires matched_requirement_id",
            error_code="MISSING_MATCHED_REQUIREMENT_ID",
        )


def parse_decisions_file(path: str, meeting_id: str) -> tuple[str | None, list[ResolveDecision]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("meeting_id") != meeting_id:
        raise UsageError("Decision file meeting_id does not match command meeting-id", error_code="DECISION_FILE_MEETING_MISMATCH")
    decisions = []
    for item in data.get("decisions", []):
        decision = str(item.get("decision") or "")
        item_id = str(item.get("item_id") or item.get("conflict_id") or "")
        if not decision:
            action = str(item.get("action") or "")
            if action not in VALID_ACTIONS:
                raise UsageError(f"Invalid decision action: {action}", error_code="DECISION_FILE_INVALID_ACTION")
            decision = _decision_from_action(action)
        if decision not in VALID_DECISIONS:
            raise UsageError(f"Invalid decision: {decision}", error_code="DECISION_FILE_INVALID_DECISION")
        if not item_id:
            raise UsageError("Decision item_id is required", error_code="DECISION_FILE_MISSING_ITEM_ID")
        merged_text = item.get("merged_text")
        matched_requirement_id = item.get("matched_requirement_id")
        if decision == "conflict_merged" and not merged_text:
            raise UsageError("merged_text is required for merge action", error_code="DECISION_FILE_MISSING_MERGE_TEXT")
        _require_matched_requirement_id(item_id, decision, matched_requirement_id)
        decisions.append(
            ResolveDecision(
                item_id=item_id,
                decision=decision,
                matched_requirement_id=matched_requirement_id,
                merged_text=merged_text,
            )
        )
    return data.get("base_revision"), decisions


def build_decisions_from_strategy(conflicts: list[dict[str, Any]], strategy: str) -> list[ResolveDecision]:
    if strategy not in VALID_STRATEGIES:
        raise UsageError("Invalid decision strategy", error_code="INVALID_DECISION_STRATEGY")
    decisions_by_strategy = {
        "keep-existing": "conflict_keep_existing",
        "replace-all": "conflict_replaced",
        "accept-ai": "conflict_replaced",
    }
    decision = decisions_by_strategy[strategy]
    resolved: list[ResolveDecision] = []
    for conflict in conflicts:
        item_id = _conflict_item_id(conflict)
        matched_requirement_id = _matched_requirement_id(conflict)
        _require_matched_requirement_id(item_id, decision, matched_requirement_id)
        resolved.append(
            ResolveDecision(
                item_id=item_id,
                decision=decision,
                matched_requirement_id=matched_requirement_id,
            )
        )
    return resolved


def build_non_conflict_decisions(apply_result: dict[str, Any]) -> list[ResolveDecision]:
    decisions: list[ResolveDecision] = []
    for item in apply_result.get("added", []) or []:
        item_id = item.get("item_id")
        if not item_id:
            continue
        decisions.append(ResolveDecision(item_id=str(item_id), decision="added"))

    for item in apply_result.get("skipped", []) or []:
        item_id = item.get("item_id")
        if not item_id:
            continue
        decision = str(item.get("decision") or "")
        if decision not in VALID_NON_CONFLICT_DECISIONS:
            classification = str(item.get("classification") or "").lower()
            decision = "skipped_semantic" if "semantic" in classification else "skipped_duplicate"
        decisions.append(
            ResolveDecision(
                item_id=str(item_id),
                decision=decision,
                matched_requirement_id=_matched_requirement_id(item),
            )
        )
    return decisions


def interactive_resolve(conflicts: list[dict[str, Any]]) -> list[ResolveDecision]:
    decisions: list[ResolveDecision] = []
    i = 0
    while i < len(conflicts):
        conflict = conflicts[i]
        item_id = _conflict_item_id(conflict)
        matched_requirement = conflict.get("matched_requirement")
        existing_requirement = ""
        if isinstance(matched_requirement, dict):
            existing_requirement = str(matched_requirement.get("content") or "")
        if not existing_requirement:
            existing_requirement = str(conflict.get("existing_requirement") or "")
        new_item = str(conflict.get("item_content") or conflict.get("new_item") or "")
        matched_requirement_id = _matched_requirement_id(conflict)
        print(f"\nConflict {i + 1}/{len(conflicts)}")
        print(f"ID: {item_id}")
        print(f"Existing: {existing_requirement}")
        print(f"New: {new_item}")
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
        mapping = {
            "k": "conflict_keep_existing",
            "r": "conflict_replaced",
            "b": "conflict_kept_both",
            "m": "conflict_merged",
        }
        decision = mapping[action_key]
        merged_text = None
        if decision == "conflict_merged":
            merged_text = ask_multiline("Enter merged text")
        _require_matched_requirement_id(item_id, decision, matched_requirement_id)
        decisions.append(
            ResolveDecision(
                item_id=item_id,
                decision=decision,
                matched_requirement_id=matched_requirement_id,
                merged_text=merged_text,
            )
        )
        i += 1
    return decisions


def validate_decisions(
    conflicts: list[dict[str, Any]],
    decisions: list[ResolveDecision],
) -> None:
    conflict_ids = {_conflict_item_id(item) for item in conflicts}
    decision_ids = {item.item_id for item in decisions}
    unknown = decision_ids - conflict_ids
    if unknown:
        raise UsageError("Unknown conflict ids in decisions", error_code="UNKNOWN_CONFLICT_IDS", details={"ids": sorted(unknown)})
    missing = conflict_ids - decision_ids
    if missing:
        raise UsageError("Missing decisions for conflicts", error_code="MISSING_CONFLICT_DECISIONS", details={"ids": sorted(missing)})
    for item in decisions:
        if item.decision not in VALID_CONFLICT_DECISIONS:
            raise UsageError(f"Invalid conflict decision: {item.decision}", error_code="INVALID_CONFLICT_DECISION")
        _require_matched_requirement_id(item.item_id, item.decision, item.matched_requirement_id)
        if item.decision == "conflict_merged" and not item.merged_text:
            raise UsageError("merged_text is required for merge action", error_code="DECISION_FILE_MISSING_MERGE_TEXT")


def resolve_payload(base_revision: str | None, decisions: list[ResolveDecision]) -> dict[str, Any]:
    return {
        "base_revision": base_revision,
        "decisions": [
            {
                "item_id": item.item_id,
                "decision": item.decision,
                **({"matched_requirement_id": item.matched_requirement_id} if item.matched_requirement_id else {}),
                **({"merged_text": item.merged_text} if item.merged_text else {}),
            }
            for item in decisions
        ],
        "submitted_at": datetime.now(UTC).isoformat(),
    }
