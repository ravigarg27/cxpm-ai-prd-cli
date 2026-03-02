from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cxpm_cli.errors import BusinessStateError

CONFIG_VERSION = 1


def config_root() -> Path:
    appdata = os.getenv("APPDATA")
    xdg_config = os.getenv("XDG_CONFIG_HOME")
    if os.name == "nt" and appdata:
        return Path(appdata) / "cxpm-cli"
    if xdg_config:
        return Path(xdg_config) / "cxpm-cli"
    return Path.home() / ".config" / "cxpm-cli"


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        path.chmod(0o700)


@dataclass(frozen=True)
class Profile:
    name: str
    api_url: str


class ProfileStore:
    def __init__(self, root: Path | None = None) -> None:
        preferred = root or config_root()
        try:
            ensure_private_dir(preferred)
            self.root = preferred
        except PermissionError:
            fallback = Path.cwd() / ".cxpm-cli"
            ensure_private_dir(fallback)
            self.root = fallback
        self.config_path = self.root / "profiles.json"

    def load(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {
                "config_version": CONFIG_VERSION,
                "active_profile": "default",
                "profiles": {"default": {"api_url": "http://localhost:8000"}},
            }
        raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        version = raw.get("config_version", 0)
        if version > CONFIG_VERSION:
            raise BusinessStateError(
                "Local config is newer than this CLI version",
                error_code="CONFIG_TOO_NEW",
                details={"config_version": version, "supported_version": CONFIG_VERSION},
            )
        if version < CONFIG_VERSION:
            raw = self._migrate(raw, version)
        return raw

    def save(self, data: dict[str, Any]) -> None:
        data = {**data, "config_version": CONFIG_VERSION}
        tmp = self.config_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self.config_path)
        if os.name != "nt":
            self.config_path.chmod(0o600)

    def active_profile(self) -> Profile:
        data = self.load()
        active = data.get("active_profile", "default")
        profile_data = data.get("profiles", {}).get(active)
        if not profile_data:
            raise BusinessStateError(
                f"Active profile '{active}' is missing",
                error_code="PROFILE_MISSING",
            )
        return Profile(name=active, api_url=profile_data["api_url"])

    def set_active_profile(self, profile: str) -> None:
        data = self.load()
        if profile not in data.get("profiles", {}):
            raise BusinessStateError(f"Unknown profile: {profile}", error_code="PROFILE_MISSING")
        data["active_profile"] = profile
        self.save(data)

    def upsert_profile(self, profile: Profile) -> None:
        data = self.load()
        profiles = data.setdefault("profiles", {})
        profiles[profile.name] = {"api_url": profile.api_url}
        data["profiles"] = profiles
        self.save(data)

    def list_profiles(self) -> list[Profile]:
        data = self.load()
        profiles = data.get("profiles", {})
        return [Profile(name=name, api_url=item["api_url"]) for name, item in profiles.items()]

    def _migrate(self, data: dict[str, Any], version: int) -> dict[str, Any]:
        backup = self.config_path.with_suffix(".bak")
        if self.config_path.exists():
            backup.write_text(self.config_path.read_text(encoding="utf-8"), encoding="utf-8")
        migrated = data
        if version == 0:
            migrated = {
                "config_version": CONFIG_VERSION,
                "active_profile": migrated.get("active_profile", "default"),
                "profiles": migrated.get("profiles", {"default": {"api_url": "http://localhost:8000"}}),
            }
        self.save(migrated)
        return migrated
