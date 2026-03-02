from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cxpm_cli.state.profiles import ProfileStore, ensure_private_dir

try:
    import keyring  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    keyring = None

TOKEN_FILENAME = "tokens.json"
CHECKPOINT_DIR = "checkpoints"
LOG_DIR = "logs"
STATE_VERSION = 1
RETENTION_DAYS = 7


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)
    if os.name != "nt":
        path.chmod(0o600)


class TokenStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or ProfileStore().root
        ensure_private_dir(self.root)
        self.path = self.root / TOKEN_FILENAME

    def set_token(self, profile: str, access_token: str, refresh_token: str | None = None) -> None:
        if keyring:
            keyring.set_password("cxpm-cli", f"{profile}:access_token", access_token)
            if refresh_token:
                keyring.set_password("cxpm-cli", f"{profile}:refresh_token", refresh_token)
        payload = _read_json(self.path)
        payload.setdefault("state_version", STATE_VERSION)
        payload.setdefault("profiles", {})
        payload["profiles"][profile] = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        _write_json_atomic(self.path, payload)

    def get_token(self, profile: str) -> dict[str, Any] | None:
        if keyring:
            access_token = keyring.get_password("cxpm-cli", f"{profile}:access_token")
            refresh_token = keyring.get_password("cxpm-cli", f"{profile}:refresh_token")
            if access_token:
                return {"access_token": access_token, "refresh_token": refresh_token}
        payload = _read_json(self.path)
        if not payload:
            return None
        return payload.get("profiles", {}).get(profile)

    def clear_token(self, profile: str) -> None:
        if keyring:
            try:
                keyring.delete_password("cxpm-cli", f"{profile}:access_token")
            except Exception:
                pass
            try:
                keyring.delete_password("cxpm-cli", f"{profile}:refresh_token")
            except Exception:
                pass
        payload = _read_json(self.path)
        profiles = payload.get("profiles", {})
        if profile in profiles:
            profiles.pop(profile)
            payload["profiles"] = profiles
            _write_json_atomic(self.path, payload)


@dataclass
class Checkpoint:
    meeting_id: str
    base_revision: str | None
    conflicts: list[str]
    decisions: list[dict[str, Any]]
    created_at: str


class CheckpointStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (ProfileStore().root / CHECKPOINT_DIR)
        ensure_private_dir(self.root)

    def path_for_meeting(self, meeting_id: str) -> Path:
        return self.root / f"{meeting_id}.json"

    def write(self, checkpoint: Checkpoint) -> Path:
        data = {
            "state_version": STATE_VERSION,
            "meeting_id": checkpoint.meeting_id,
            "base_revision": checkpoint.base_revision,
            "conflicts": checkpoint.conflicts,
            "decisions": checkpoint.decisions,
            "created_at": checkpoint.created_at,
        }
        path = self.path_for_meeting(checkpoint.meeting_id)
        _write_json_atomic(path, data)
        return path

    def read(self, meeting_id: str) -> dict[str, Any] | None:
        path = self.path_for_meeting(meeting_id)
        if not path.exists():
            return None
        data = _read_json(path)
        if data.get("state_version", 0) > STATE_VERSION:
            return None
        return data

    def prune(self, retention_days: int = RETENTION_DAYS) -> None:
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        for item in self.root.glob("*.json"):
            if datetime.fromtimestamp(item.stat().st_mtime, UTC) < cutoff:
                item.unlink(missing_ok=True)


def configure_logger(root: Path | None = None, verbose: bool = False) -> logging.Logger:
    base = root or (ProfileStore().root / LOG_DIR)
    ensure_private_dir(base)
    logger = logging.getLogger("cxpm")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()

    log_path = base / "cxpm.log"
    if log_path.exists() and log_path.stat().st_size > 10 * 1024 * 1024:
        archive = base / f"cxpm-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.log"
        log_path.replace(archive)

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)

    cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS)
    for file in base.glob("cxpm-*.log"):
        if datetime.fromtimestamp(file.stat().st_mtime, UTC) < cutoff:
            file.unlink(missing_ok=True)

    return logger
