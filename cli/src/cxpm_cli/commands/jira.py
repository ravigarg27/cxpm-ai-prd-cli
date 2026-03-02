from __future__ import annotations

import json
from pathlib import Path

import typer

from cxpm_cli.commands.helpers import output_success, raise_or_output_error
from cxpm_cli.errors import APIError, UsageError
from cxpm_cli.runtime import AppContext

app = typer.Typer(help="Jira commands")
epic_app = typer.Typer(help="Epic generation commands")
stories_app = typer.Typer(help="Story save commands")
app.add_typer(epic_app, name="epic")
app.add_typer(stories_app, name="stories")


@epic_app.command("generate")
def generate(
    ctx_: typer.Context,
    project_id: str = typer.Option(..., "--project-id"),
    requirements_text: str | None = typer.Option(None, "--requirements-text"),
    save: bool = typer.Option(False, "--save"),
) -> None:
    ctx: AppContext = ctx_.obj
    command = "jira epic generate"
    try:
        client = ctx.build_client()
        result = client.generate_epic(project_id, requirements_text=requirements_text)
        if save:
            save_result = client.save_stories(result)
            result["save_result"] = save_result
        output_success(ctx, command, result)
    except Exception as exc:
        if not isinstance(exc, APIError):
            exc = APIError(str(exc), error_code="JIRA_GENERATE_FAILED")
        raise_or_output_error(ctx, command, exc)


@stories_app.command("save")
def save(
    ctx_: typer.Context,
    payload_file: str = typer.Option(..., "--payload-file"),
) -> None:
    ctx: AppContext = ctx_.obj
    command = "jira stories save"
    try:
        path = Path(payload_file)
        if not path.exists():
            raise UsageError("Payload file does not exist", error_code="PAYLOAD_FILE_MISSING")
        payload = json.loads(path.read_text(encoding="utf-8"))
        client = ctx.build_client()
        result = client.save_stories(payload)
        output_success(ctx, command, result)
    except Exception as exc:
        if not isinstance(exc, (APIError, UsageError)):
            exc = APIError(str(exc), error_code="JIRA_SAVE_FAILED")
        raise_or_output_error(ctx, command, exc)
