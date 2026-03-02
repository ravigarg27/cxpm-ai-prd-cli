from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class ErrorPayload(BaseModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class JsonEnvelope(BaseModel):
    schema_version: str = "1.0"
    command: str
    status: Literal["success", "error"]
    timestamp: str = Field(default_factory=utc_now_iso)
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    data: dict[str, Any] = Field(default_factory=dict)
    error: ErrorPayload | None = None


class CapabilityInfo(BaseModel):
    idempotency: bool = True
    revision_conflict: bool = True
    compatibility_metadata: bool = True
    compatibility_state: Literal["known", "unknown"] = "known"
