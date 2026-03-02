from __future__ import annotations

from pydantic import BaseModel


class Requirement(BaseModel):
    id: str
    text: str
    updated_at: str
