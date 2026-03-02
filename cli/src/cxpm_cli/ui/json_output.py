from __future__ import annotations

import json
from typing import Any

from cxpm_cli.models.common import ErrorPayload, JsonEnvelope


def emit_success(command: str, data: dict[str, Any], request_id: str, *, warnings: list[str] | None = None) -> str:
    payload = data.copy()
    if warnings:
        payload["warnings"] = warnings
    envelope = JsonEnvelope(command=command, status="success", data=payload, request_id=request_id)
    text = envelope.model_dump_json(indent=2)
    print(text)
    return text


def emit_error(
    command: str,
    message: str,
    request_id: str,
    *,
    error_code: str,
    retryable: bool = False,
    details: dict[str, Any] | None = None,
) -> str:
    envelope = JsonEnvelope(
        command=command,
        status="error",
        request_id=request_id,
        error=ErrorPayload(code=error_code, message=message, retryable=retryable, details=details or {}),
    )
    text = envelope.model_dump_json(indent=2)
    print(text)
    return text


def dump_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, indent=2))
