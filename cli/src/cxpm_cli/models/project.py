from __future__ import annotations

from pydantic import BaseModel


class Project(BaseModel):
    id: str
    name: str
