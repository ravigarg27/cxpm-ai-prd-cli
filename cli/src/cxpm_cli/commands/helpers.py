from __future__ import annotations

from typing import Any

import typer

from cxpm_cli.errors import CLIError
from cxpm_cli.runtime import AppContext
from cxpm_cli.ui.json_output import emit_error, emit_success
from cxpm_cli.ui.render import render_kv, render_list


def output_success(ctx: AppContext, command: str, data: dict[str, Any]) -> None:
    if ctx.json_mode:
        emit_success(command, data, ctx.request_id or "unknown", warnings=ctx.warnings)
        return
    if ctx.warnings:
        for warning in ctx.warnings:
            typer.echo(f"Warning: {warning}", err=True)
    if "items" in data and isinstance(data["items"], list):
        render_list(command, data["items"])
        remainder = {k: v for k, v in data.items() if k != "items"}
        if remainder:
            render_kv("Meta", remainder)
        return
    render_kv(command, data)


def raise_or_output_error(ctx: AppContext, command: str, error: CLIError) -> None:
    if ctx.json_mode:
        emit_error(
            command,
            str(error),
            ctx.request_id or "unknown",
            error_code=error.error_code,
            retryable=error.retryable,
            details=error.details,
        )
        raise typer.Exit(code=int(error.exit_code))
    typer.echo(f"Error: {error}", err=True)
    raise typer.Exit(code=int(error.exit_code))
