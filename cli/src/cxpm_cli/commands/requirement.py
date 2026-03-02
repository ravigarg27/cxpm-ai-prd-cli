from __future__ import annotations

import typer

from cxpm_cli.commands.helpers import output_success, raise_or_output_error
from cxpm_cli.errors import APIError, UsageError
from cxpm_cli.runtime import AppContext

app = typer.Typer(help="Requirement commands")

SECTION_VALUES = (
    "needs_and_goals",
    "requirements",
    "scope_and_constraints",
    "risks_and_questions",
    "action_items",
)


def _normalize_section(value: str) -> str:
    return value.strip().lower().replace("-", "_")


def _filter_result_by_section(result: dict, section: str) -> dict:
    filtered = dict(result)
    if "items" in filtered and isinstance(filtered["items"], list):
        filtered_items = [
            item
            for item in filtered["items"]
            if isinstance(item, dict) and _normalize_section(str(item.get("section", ""))) == section
        ]
        filtered["items"] = filtered_items
        filtered["total_count"] = len(filtered_items)
        filtered["section"] = section
        return filtered

    for section_key in SECTION_VALUES:
        values = filtered.get(section_key)
        if section_key == section:
            filtered[section_key] = values if isinstance(values, list) else []
        else:
            filtered[section_key] = []
    filtered["total_count"] = len(filtered.get(section, []))
    filtered["section"] = section
    return filtered


@app.command("ls")
def requirement_ls(
    ctx_: typer.Context,
    project_id: str = typer.Option(..., "--project-id"),
    page_size: int = typer.Option(50, "--page-size"),
    cursor: str | None = typer.Option(None, "--cursor"),
    sort: str | None = typer.Option(None, "--sort"),
    filters: list[str] = typer.Option([], "--filter"),
    section: str | None = typer.Option(None, "--section"),
) -> None:
    ctx: AppContext = ctx_.obj
    command = "requirement ls"
    try:
        if page_size < 1 or page_size > 200:
            raise UsageError("--page-size must be between 1 and 200", error_code="INVALID_PAGE_SIZE")
        normalized_section = None
        if section:
            normalized_section = _normalize_section(section)
            if normalized_section not in SECTION_VALUES:
                raise UsageError(
                    "--section must be one of: needs_and_goals, requirements, scope_and_constraints, risks_and_questions, action_items",
                    error_code="INVALID_SECTION",
                )

        effective_filters = list(filters)
        if normalized_section:
            effective_filters.append(f"section:{normalized_section}")
        client = ctx.build_client()
        result = client.list_requirements(
            project_id,
            page_size=page_size,
            cursor=cursor,
            sort=sort,
            filters=effective_filters,
        )
        if normalized_section:
            result = _filter_result_by_section(result, normalized_section)
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
