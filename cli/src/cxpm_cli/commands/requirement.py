from __future__ import annotations

import typer

from cxpm_cli.commands.helpers import output_success, raise_or_output_error
from cxpm_cli.errors import APIError, UsageError
from cxpm_cli.runtime import AppContext

app = typer.Typer(help="Requirement commands")


@app.command("ls")
def requirement_ls(
    ctx_: typer.Context,
    project_id: str = typer.Option(..., "--project-id"),
    page_size: int = typer.Option(50, "--page-size"),
    cursor: str | None = typer.Option(None, "--cursor"),
    sort: str | None = typer.Option(None, "--sort"),
    filters: list[str] = typer.Option([], "--filter"),
) -> None:
    ctx: AppContext = ctx_.obj
    command = "requirement ls"
    try:
        if page_size < 1 or page_size > 200:
            raise UsageError("--page-size must be between 1 and 200", error_code="INVALID_PAGE_SIZE")
        client = ctx.build_client()
        result = client.list_requirements(project_id, page_size=page_size, cursor=cursor, sort=sort, filters=filters)
        result.setdefault("next_cursor", None)
        result.setdefault("total_count", len(result.get("items", [])))
        output_success(ctx, command, result)
    except Exception as exc:
        if not isinstance(exc, (APIError, UsageError)):
            exc = APIError(str(exc), error_code="REQUIREMENT_LIST_FAILED")
        raise_or_output_error(ctx, command, exc)


@app.command("export")
def requirement_export(
    ctx_: typer.Context,
    project_id: str = typer.Option(..., "--project-id"),
    out: str | None = typer.Option(None, "--out"),
) -> None:
    ctx: AppContext = ctx_.obj
    command = "requirement export"
    try:
        client = ctx.build_client()
        result = client.export_requirements(project_id)
        markdown = result.get("markdown", "")
        if out:
            with open(out, "w", encoding="utf-8") as file:
                file.write(markdown)
            result["path"] = out
        if not ctx.json_mode and markdown and not out:
            print(markdown)
        output_success(ctx, command, {k: v for k, v in result.items() if k != "markdown"} if not ctx.json_mode else result)
    except Exception as exc:
        if not isinstance(exc, APIError):
            exc = APIError(str(exc), error_code="REQUIREMENT_EXPORT_FAILED")
        raise_or_output_error(ctx, command, exc)
