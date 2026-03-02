from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from cxpm_cli import __version__
from cxpm_cli.client.api import APIClient
from cxpm_cli.state.profiles import ProfileStore
from cxpm_cli.state.store import TokenStore, configure_logger


@dataclass
class AppContext:
    profile_name: str | None = None
    api_url_override: str | None = None
    json_mode: bool = False
    non_interactive: bool = False
    verbose: bool = False
    request_id: str | None = None
    no_color: bool = False
    logger = None
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.request_id:
            self.request_id = str(uuid4())

    def ensure_logger(self) -> None:
        if self.logger is None:
            self.logger = configure_logger(verbose=self.verbose)

    def _profile_data(self) -> tuple[str, str]:
        store = ProfileStore()
        if self.profile_name:
            store.set_active_profile(self.profile_name)
        profile = store.active_profile()
        api_url = self.api_url_override or profile.api_url
        return profile.name, api_url

    def build_client(self) -> APIClient:
        self.ensure_logger()
        profile_name, api_url = self._profile_data()
        token_env = os.getenv("CXPM_TOKEN")
        token_store = TokenStore()
        token_data = token_store.get_token(profile_name) or {}
        token = token_env or token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        client = APIClient(
            api_url=api_url,
            token=token,
            refresh_token=refresh_token,
            request_id=self.request_id,
            cli_version=__version__,
        )
        self.request_id = client.request_id
        client.detect_capabilities()
        self.warnings = list(client.warnings)
        return client

    def persist_tokens(self, access_token: str, refresh_token: str | None) -> None:
        profile_name, _ = self._profile_data()
        TokenStore().set_token(profile_name, access_token, refresh_token)

    def clear_tokens(self) -> None:
        profile_name, _ = self._profile_data()
        TokenStore().clear_token(profile_name)

    def config_root(self) -> Path:
        return ProfileStore().root
