from __future__ import annotations

from pydantic import BaseModel, Field


class JiraEpic(BaseModel):
    title: str
    description: str
    stories: list[dict] = Field(default_factory=list)
