from __future__ import annotations

import typer

from cxpm_cli.commands.helpers import output_success, raise_or_output_error
from cxpm_cli.errors import APIError
from cxpm_cli.runtime import AppContext

app = typer.Typer(help="Project commands")


@app.command("ls")
def project_ls(ctx_: typer.Context) -> None:
    ctx: AppContext = ctx_.obj
    command = "project ls"
    try:
        client = ctx.build_client()
        result = client.list_projects()
        output_success(ctx, command, result)
    except Exception as exc:
        if not isinstance(exc, APIError):
            exc = APIError(str(exc), error_code="PROJECT_LIST_FAILED")
        raise_or_output_error(ctx, command, exc)


@app.command("create")
def project_create(
    ctx_: typer.Context,
    name: str = typer.Option(..., "--name"),
    description: str | None = typer.Option(None, "--description"),
) -> None:
    ctx: AppContext = ctx_.obj
    command = "project create"
    try:
        client = ctx.build_client()
        result = client.create_project(name=name, description=description)
        output_success(ctx, command, result)
    except Exception as exc:
        if not isinstance(exc, APIError):
            exc = APIError(str(exc), error_code="PROJECT_CREATE_FAILED")
        raise_or_output_error(ctx, command, exc)
