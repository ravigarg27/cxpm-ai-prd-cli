from __future__ import annotations

from typing import Any

from cxpm_cli.client.api import APIClient


def ingest_meeting(
    client: APIClient,
    *,
    text: str | None,
    file_path: str | None,
    project_id: str | None = None,
    title: str | None = None,
    meeting_date: str | None = None,
) -> dict[str, Any]:
    return client.upload_meeting(
        text=text,
        file_path=file_path,
        project_id=project_id,
        title=title,
        meeting_date=meeting_date,
    )


def review_meeting(client: APIClient, meeting_id: str) -> dict[str, Any]:
    return client.get_meeting(meeting_id)


def apply_meeting(client: APIClient, meeting_id: str, revision: str | None = None) -> dict[str, Any]:
    return client.apply_meeting(meeting_id, revision=revision)
