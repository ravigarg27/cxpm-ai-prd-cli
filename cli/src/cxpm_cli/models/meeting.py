from __future__ import annotations

from pydantic import BaseModel, Field


class MeetingConflict(BaseModel):
    conflict_id: str
    existing_requirement: str
    new_item: str
    classification: str
    reason: str


class MeetingApplyResponse(BaseModel):
    added: list[dict] = Field(default_factory=list)
    skipped: list[dict] = Field(default_factory=list)
    conflicts: list[MeetingConflict] = Field(default_factory=list)
    revision: str | None = None
