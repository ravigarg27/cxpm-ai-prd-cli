from __future__ import annotations

from pydantic import BaseModel, Field


class MeetingConflict(BaseModel):
    item_id: str
    item_section: str
    item_content: str
    decision: str
    classification: str | None = None
    reason: str
    matched_requirement: dict | None = None


class MeetingApplyResponse(BaseModel):
    added: list[dict] = Field(default_factory=list)
    skipped: list[dict] = Field(default_factory=list)
    conflicts: list[MeetingConflict] = Field(default_factory=list)
    revision: str | None = None
