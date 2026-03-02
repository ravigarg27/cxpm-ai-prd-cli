from __future__ import annotations

import os

import typer

from cxpm_cli.commands.helpers import output_success, raise_or_output_error
from cxpm_cli.errors import AuthError
from cxpm_cli.runtime import AppContext

app = typer.Typer(help="Authentication commands")


@app.command("login")
def login(
    ctx_: typer.Context,
    username: str | None = typer.Option(None),
    password: str | None = typer.Option(None),
    token: str | None = typer.Option(None, help="Use static token"),
) -> None:
    ctx: AppContext = ctx_.obj
    command = "auth login"
    try:
        client = ctx.build_client()
        if ctx.non_interactive and not token and (not username or not password):
            raise AuthError("Non-interactive login requires --token or username/password", error_code="AUTH_INPUT_REQUIRED")
        token = token or os.getenv("CXPM_TOKEN")
        if not token and (not username or not password):
            username = username or typer.prompt("Username")
            password = password or typer.prompt("Password", hide_input=True)
        login_response = client.login(username=username, password=password, token=token)
        me = client.me()
        ctx.persist_tokens(login_response.access_token, login_response.refresh_token)
        output_success(
            ctx,
            command,
            {
                "user_id": me.user_id,
                "email": me.email,
                "name": me.name,
                "token_source": "flag_or_env" if token else "login",
            },
        )
    except Exception as exc:
        if not isinstance(exc, AuthError):
            exc = AuthError(str(exc), error_code="AUTH_LOGIN_FAILED")
        raise_or_output_error(ctx, command, exc)


@app.command("status")
def status(ctx_: typer.Context) -> None:
    ctx: AppContext = ctx_.obj
    command = "auth status"
    try:
        client = ctx.build_client()
        me = client.me()
        output_success(ctx, command, {"authenticated": True, "user_id": me.user_id, "email": me.email, "name": me.name})
    except Exception as exc:
        if not isinstance(exc, AuthError):
            exc = AuthError(str(exc), error_code="AUTH_STATUS_FAILED")
        raise_or_output_error(ctx, command, exc)


@app.command("logout")
def logout(ctx_: typer.Context) -> None:
    ctx: AppContext = ctx_.obj
    command = "auth logout"
    try:
        client = ctx.build_client()
        resp = client.logout()
        ctx.clear_tokens()
        output_success(ctx, command, {"cleared_local_credentials": True, "revoked_remote": resp.get("revoked", False)})
    except Exception as exc:
        if not isinstance(exc, AuthError):
            exc = AuthError(str(exc), error_code="AUTH_LOGOUT_FAILED")
        raise_or_output_error(ctx, command, exc)
