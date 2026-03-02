from __future__ import annotations

import json
import os
from datetime import date
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer

from cxpm_cli.client.sse import stream_events
from cxpm_cli.commands.helpers import output_success, raise_or_output_error
from cxpm_cli.errors import APIError, CLIError, InterruptedError, UsageError
from cxpm_cli.runtime import AppContext
from cxpm_cli.state.store import Checkpoint, CheckpointStore
from cxpm_cli.workflows.meeting_flow import apply_meeting, ingest_meeting, review_meeting
from cxpm_cli.workflows.resolve_flow import (
    build_decisions_from_strategy,
    interactive_resolve,
    parse_decisions_file,
    resolve_payload,
    validate_decisions,
)

app = typer.Typer(help="Meeting workflow commands")
item_app = typer.Typer(help="Meeting item commands")
app.add_typer(item_app, name="item")


@app.command("ingest")
def ingest(
    ctx_: typer.Context,
    file_path: str | None = typer.Option(None, "--file"),
    text: str | None = typer.Option(None),
    project_id: str | None = typer.Option(None, "--project-id"),
    title: str | None = typer.Option(None, "--title"),
    meeting_date: str | None = typer.Option(None, "--meeting-date"),
    follow: bool = typer.Option(False, "--follow"),
) -> None:
    ctx: AppContext = ctx_.obj
    command = "meeting ingest"
    try:
        if not file_path and not text:
            raise UsageError("Provide --file or --text", error_code="INGEST_INPUT_REQUIRED")
        if meeting_date:
            try:
                date.fromisoformat(meeting_date)
            except ValueError as exc:
                raise UsageError("--meeting-date must be YYYY-MM-DD", error_code="INVALID_MEETING_DATE") from exc
        inferred_title = title or (Path(file_path).stem if file_path else "Meeting Ingest")
        inferred_meeting_date = meeting_date or date.today().isoformat()
        client = ctx.build_client()
        result = ingest_meeting(
            client,
            text=text,
            file_path=file_path,
            project_id=project_id,
            title=inferred_title,
            meeting_date=inferred_meeting_date,
        )
        if follow:
            meeting_id = result.get("meeting_id")
            if not meeting_id:
                raise APIError("Missing meeting_id for follow mode", error_code="MISSING_MEETING_ID")
            stream_url = f"{client.api_url}/api/meetings/{meeting_id}/stream"
            for event in stream_events(client._client, stream_url, headers=client._base_headers()):
                if ctx.json_mode:
                    continue
                typer.echo(f"stream: {json.dumps(event)}")
        output_success(ctx, command, result)
    except KeyboardInterrupt as exc:
        cp = CheckpointStore().write(
            Checkpoint(
                meeting_id="unknown",
                base_revision=None,
                conflicts=[],
                decisions=[],
                created_at=datetime.now(UTC).isoformat(),
            )
        )
        raise_or_output_error(
            ctx,
            command,
            InterruptedError(
                "Operation interrupted",
                details={"resume_hint": f"checkpoint at {cp}"},
            ),
        )
        raise exc
    except Exception as exc:
        if not isinstance(exc, (CLIError,)):
            exc = APIError(str(exc), error_code="MEETING_INGEST_FAILED")
        raise_or_output_error(ctx, command, exc)


@app.command("review")
def review(ctx_: typer.Context, meeting_id: str) -> None:
    ctx: AppContext = ctx_.obj
    command = "meeting review"
    try:
        client = ctx.build_client()
        result = review_meeting(client, meeting_id)
        output_success(ctx, command, result)
    except Exception as exc:
        if not isinstance(exc, CLIError):
            exc = APIError(str(exc), error_code="MEETING_REVIEW_FAILED")
        raise_or_output_error(ctx, command, exc)


@app.command("apply")
def apply(ctx_: typer.Context, meeting_id: str, revision: str | None = typer.Option(None, "--revision")) -> None:
    ctx: AppContext = ctx_.obj
    command = "meeting apply"
    try:
        client = ctx.build_client()
        result = apply_meeting(client, meeting_id, revision=revision)
        output_success(ctx, command, result)
    except Exception as exc:
        if not isinstance(exc, CLIError):
            exc = APIError(str(exc), error_code="MEETING_APPLY_FAILED")
        raise_or_output_error(ctx, command, exc)


@app.command("resolve")
def resolve(
    ctx_: typer.Context,
    meeting_id: str,
    decisions_file: str | None = typer.Option(None, "--decisions-file"),
    decision_strategy: str | None = typer.Option(None, "--decision-strategy"),
    base_revision: str | None = typer.Option(None, "--base-revision"),
) -> None:
    ctx: AppContext = ctx_.obj
    command = "meeting resolve"
    try:
        if ctx.non_interactive and not decisions_file and not decision_strategy:
            raise UsageError("Non-interactive resolve requires --decisions-file or --decision-strategy")
        if decision_strategy and decision_strategy not in {"keep-existing", "replace-all", "accept-ai"}:
            raise UsageError("Invalid decision strategy", error_code="INVALID_DECISION_STRATEGY")

        client = ctx.build_client()
        meeting = review_meeting(client, meeting_id)
        apply_result = meeting.get("apply_result") or apply_meeting(client, meeting_id, revision=base_revision)
        conflicts: list[dict[str, Any]] = apply_result.get("conflicts", [])
        resolved_decisions = []
        payload_revision = base_revision or apply_result.get("revision")

        if conflicts:
            if decisions_file:
                payload_revision_from_file, parsed = parse_decisions_file(decisions_file, meeting_id)
                if payload_revision_from_file:
                    payload_revision = payload_revision_from_file
                resolved_decisions = parsed
            elif decision_strategy:
                resolved_decisions = build_decisions_from_strategy(conflicts, decision_strategy)
            else:
                if not os.isatty(0):
                    raise UsageError("Interactive resolve requires a TTY; use --decisions-file or --decision-strategy")
                resolved_decisions = interactive_resolve(conflicts)
            validate_decisions(conflicts, resolved_decisions)
        payload = resolve_payload(payload_revision, resolved_decisions)
        checkpoint_store = CheckpointStore()
        checkpoint_store.prune()
        checkpoint_store.write(
            Checkpoint(
                meeting_id=meeting_id,
                base_revision=payload_revision,
                conflicts=[item["conflict_id"] for item in conflicts],
                decisions=payload["decisions"],
                created_at=datetime.now(UTC).isoformat(),
            )
        )
        result = client.resolve_meeting(meeting_id, payload, revision=payload_revision)
        result.setdefault("resolved", len(payload["decisions"]))
        result.setdefault("remaining", max(0, len(conflicts) - len(payload["decisions"])))
        output_success(ctx, command, result)
    except KeyboardInterrupt as exc:
        raise_or_output_error(ctx, command, InterruptedError("Resolve interrupted"))
        raise exc
    except Exception as exc:
        if not isinstance(exc, CLIError):
            exc = APIError(str(exc), error_code="MEETING_RESOLVE_FAILED")
        raise_or_output_error(ctx, command, exc)


@item_app.command("add")
def item_add(
    ctx_: typer.Context,
    meeting_id: str = typer.Option(..., "--meeting-id"),
    text: str = typer.Option(..., "--text"),
) -> None:
    ctx: AppContext = ctx_.obj
    command = "meeting item add"
    try:
        client = ctx.build_client()
        result = client.create_meeting_item(meeting_id, {"text": text})
        output_success(ctx, command, result)
    except Exception as exc:
        if not isinstance(exc, CLIError):
            exc = APIError(str(exc), error_code="MEETING_ITEM_ADD_FAILED")
        raise_or_output_error(ctx, command, exc)


@item_app.command("edit")
def item_edit(
    ctx_: typer.Context,
    meeting_id: str = typer.Option(..., "--meeting-id"),
    item_id: str = typer.Option(..., "--item-id"),
    text: str = typer.Option(..., "--text"),
) -> None:
    ctx: AppContext = ctx_.obj
    command = "meeting item edit"
    try:
        client = ctx.build_client()
        result = client.update_meeting_item(meeting_id, item_id, {"text": text})
        output_success(ctx, command, result)
    except Exception as exc:
        if not isinstance(exc, CLIError):
            exc = APIError(str(exc), error_code="MEETING_ITEM_EDIT_FAILED")
        raise_or_output_error(ctx, command, exc)


@item_app.command("delete")
def item_delete(
    ctx_: typer.Context,
    meeting_id: str = typer.Option(..., "--meeting-id"),
    item_id: str = typer.Option(..., "--item-id"),
) -> None:
    ctx: AppContext = ctx_.obj
    command = "meeting item delete"
    try:
        client = ctx.build_client()
        result = client.delete_meeting_item(meeting_id, item_id)
        output_success(ctx, command, result)
    except Exception as exc:
        if not isinstance(exc, CLIError):
            exc = APIError(str(exc), error_code="MEETING_ITEM_DELETE_FAILED")
        raise_or_output_error(ctx, command, exc)
