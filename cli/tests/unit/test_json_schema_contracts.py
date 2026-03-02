from __future__ import annotations

import json
from pathlib import Path

from jsonschema import validate


def test_all_command_schemas_validate_success_and_error_payloads():
    schema_root = Path(__file__).resolve().parents[2] / "schemas"
    schema_paths = sorted(schema_root.glob("*/1.0.json"))
    assert schema_paths
    for schema_path in schema_paths:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        command = schema["properties"]["command"]["const"]
        success_payload = {
            "schema_version": "1.0",
            "command": command,
            "status": "success",
            "timestamp": "2026-03-02T18:30:00Z",
            "request_id": "abc",
            "data": {"ok": True},
            "error": None,
        }
        validate(instance=success_payload, schema=schema)
        error_payload = {
            "schema_version": "1.0",
            "command": command,
            "status": "error",
            "timestamp": "2026-03-02T18:30:00Z",
            "request_id": "abc",
            "data": {},
            "error": {
                "code": "ERR",
                "message": "bad",
                "retryable": False,
                "details": {},
            },
        }
        validate(instance=error_payload, schema=schema)
