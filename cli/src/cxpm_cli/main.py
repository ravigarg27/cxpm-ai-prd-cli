from __future__ import annotations

import json
import platform
from pathlib import Path

import typer

from cxpm_cli import __version__
from cxpm_cli.commands import auth, config, jira, meeting, project, requirement
from cxpm_cli.commands.helpers import output_success, raise_or_output_error
from cxpm_cli.errors import APIError, UsageError
from cxpm_cli.runtime import AppContext
from cxpm_cli.state.profiles import ProfileStore
from cxpm_cli.state.store import CheckpointStore, TokenStore

app = typer.Typer(help="CXPM command line interface")
app.add_typer(auth.app, name="auth")
app.add_typer(meeting.app, name="meeting")
app.add_typer(requirement.app, name="requirement")
app.add_typer(jira.app, name="jira")
app.add_typer(project.app, name="project")
app.add_typer(config.app, name="config")


@app.callback()
def main(
    ctx: typer.Context,
    json_mode: bool = typer.Option(False, "--json"),
    non_interactive: bool = typer.Option(False, "--non-interactive"),
    profile: str | None = typer.Option(None, "--profile"),
    api_url: str | None = typer.Option(None, "--api-url"),
    verbose: bool = typer.Option(False, "--verbose"),
    request_id: str | None = typer.Option(None, "--request-id"),
    no_color: bool = typer.Option(False, "--no-color"),
) -> None:
    ctx.obj = AppContext(
        profile_name=profile,
        api_url_override=api_url,
        json_mode=json_mode,
        non_interactive=non_interactive,
        verbose=verbose,
        request_id=request_id,
        no_color=no_color,
    )


@app.command("version")
def version(ctx_: typer.Context) -> None:
    ctx: AppContext = ctx_.obj
    command = "version"
    try:
        profile = ProfileStore().active_profile()
        output_success(
            ctx,
            command,
            {
                "cli_version": __version__,
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                "api_url": profile.api_url,
            },
        )
    except Exception as exc:
        if not isinstance(exc, UsageError):
            exc = UsageError(str(exc), error_code="VERSION_FAILED")
        raise_or_output_error(ctx, command, exc)


@app.command("diagnostics")
def diagnostics(
    ctx_: typer.Context,
    include_checkpoints: bool = typer.Option(False, "--include-checkpoints"),
) -> None:
    ctx: AppContext = ctx_.obj
    command = "diagnostics"
    try:
        profile_store = ProfileStore()
        profile = profile_store.active_profile()
        token_store = TokenStore()
        token = token_store.get_token(profile.name)
        client = ctx.build_client()
        backend_state = client.capabilities.compatibility_state
        token_present = bool(token and token.get("access_token"))
        checkpoint_paths = [str(p) for p in (CheckpointStore().root.glob("*.json"))]
        data = {
            "profile": profile.name,
            "api_url": profile.api_url,
            "config_root": str(profile_store.root),
            "token_present": token_present,
            "backend_compatibility_state": backend_state,
            "capabilities": client.capabilities.model_dump(),
            "last_error_category": None,
            "request_id": client.request_id,
        }
        if include_checkpoints:
            redacted = []
            for path in checkpoint_paths:
                raw = json.loads(Path(path).read_text(encoding="utf-8"))
                redacted.append(
                    {
                        "meeting_id": raw.get("meeting_id"),
                        "base_revision": raw.get("base_revision"),
                        "decision_count": len(raw.get("decisions", [])),
                    }
                )
            data["checkpoints"] = redacted
        output_success(ctx, command, data)
    except Exception as exc:
        if not isinstance(exc, (UsageError, APIError)):
            exc = UsageError(str(exc), error_code="DIAGNOSTICS_FAILED")
        raise_or_output_error(ctx, command, exc)


def run() -> None:
    app()


if __name__ == "__main__":
    run()
