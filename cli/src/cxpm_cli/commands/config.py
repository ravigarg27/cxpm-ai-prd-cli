from __future__ import annotations

import typer

from cxpm_cli.commands.helpers import output_success, raise_or_output_error
from cxpm_cli.errors import UsageError
from cxpm_cli.runtime import AppContext
from cxpm_cli.state.profiles import Profile, ProfileStore

app = typer.Typer(help="Config and profile commands")
profile_app = typer.Typer(help="Profile management")
app.add_typer(profile_app, name="profile")


@profile_app.command("ls")
def profile_ls(ctx_: typer.Context) -> None:
    ctx: AppContext = ctx_.obj
    command = "config profile ls"
    try:
        store = ProfileStore()
        profiles = [{"name": item.name, "api_url": item.api_url} for item in store.list_profiles()]
        output_success(ctx, command, {"items": profiles, "count": len(profiles)})
    except Exception as exc:
        raise_or_output_error(ctx, command, UsageError(str(exc), error_code="PROFILE_LIST_FAILED"))


@profile_app.command("set")
def profile_set(
    ctx_: typer.Context,
    name: str = typer.Option(..., "--name"),
    api_url: str = typer.Option(..., "--api-url"),
) -> None:
    ctx: AppContext = ctx_.obj
    command = "config profile set"
    try:
        store = ProfileStore()
        store.upsert_profile(Profile(name=name, api_url=api_url))
        store.set_active_profile(name)
        output_success(ctx, command, {"active_profile": name, "api_url": api_url})
    except Exception as exc:
        raise_or_output_error(ctx, command, UsageError(str(exc), error_code="PROFILE_SET_FAILED"))
