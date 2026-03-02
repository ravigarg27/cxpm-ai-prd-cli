from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any
import time

import httpx


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"


def run_cli(args: list[str], env: dict[str, str]) -> dict[str, Any]:
    cmd = [sys.executable, "-m", "cxpm_cli.main"] + args
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        safe_args = []
        skip_next = False
        for i, item in enumerate(args):
            if skip_next:
                skip_next = False
                continue
            if item in {"--password", "--token"} and i + 1 < len(args):
                safe_args.extend([item, "***REDACTED***"])
                skip_next = True
            else:
                safe_args.append(item)
        raise RuntimeError(
            f"CLI failed ({proc.returncode}) for args={safe_args}\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"CLI output was not JSON for args={args}\nstdout={proc.stdout}") from exc


def try_run_cli(args: list[str], env: dict[str, str]) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return run_cli(args, env), None
    except RuntimeError as exc:
        return None, str(exc)


def wait_for_meeting_ready(api_url: str, meeting_id: str, env: dict[str, str], timeout_seconds: int = 180) -> None:
    start = time.time()
    while True:
        review = run_cli(["--json", "--api-url", api_url, "meeting", "review", meeting_id], env)
        data = review.get("data", {})
        # Support common backend status field naming.
        status = (
            data.get("status")
            or data.get("processing_status")
            or data.get("state")
            or data.get("meeting_status")
        )
        if status is None:
            return
        status_text = str(status).lower()
        if status_text in {"processed", "completed", "ready", "done", "applied"}:
            return
        if status_text in {"failed", "error"}:
            raise RuntimeError(f"Meeting processing failed before apply (status={status})")
        if time.time() - start > timeout_seconds:
            return
        time.sleep(2)


def apply_with_retry(api_url: str, meeting_id: str, env: dict[str, str], timeout_seconds: int = 300) -> dict[str, Any]:
    start = time.time()
    while True:
        result, error = try_run_cli(["--json", "--api-url", api_url, "meeting", "apply", meeting_id], env)
        if result is not None:
            return result
        error_text = (error or "").lower()
        pending_markers = [
            "business_state_error",
            "meeting not processed",
            "not processed",
            "pending",
            "processing",
        ]
        if any(marker in error_text for marker in pending_markers):
            if time.time() - start > timeout_seconds:
                raise RuntimeError(f"Timed out waiting for apply readiness. last_error={error}")
            time.sleep(5)
            continue
        raise RuntimeError(error or "meeting apply failed")


def create_project(client: httpx.Client, name: str) -> str:
    candidates = [
        "/api/projects",
        "/api/project",
    ]
    for path in candidates:
        response = client.post(path, json={"name": name})
        if response.status_code < 400:
            payload = response.json()
            project_id = payload.get("id") or payload.get("project_id")
            if project_id:
                return project_id
    raise RuntimeError("Could not create project via known endpoints")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real backend E2E for cxpm-cli")
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--transcript", required=True)
    parser.add_argument("--project-name", default="cxpm-e2e-project")
    args = parser.parse_args()

    transcript_path = Path(args.transcript)
    if not transcript_path.exists():
        raise RuntimeError(f"Transcript file not found: {transcript_path}")
    meeting_title = transcript_path.stem.replace("_", " ").strip() or "E2E Meeting"
    meeting_date = date.today().isoformat()

    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    # Force deterministic local config path for E2E so token lookup is consistent across OSes.
    e2e_config_home = ROOT / ".e2e-runtime"
    e2e_config_home.mkdir(parents=True, exist_ok=True)
    env["XDG_CONFIG_HOME"] = str(e2e_config_home)
    env.pop("APPDATA", None)

    login = run_cli(
        [
            "--json",
            "--non-interactive",
            "--api-url",
            args.api_url,
            "auth",
            "login",
            "--username",
            args.username,
            "--password",
            args.password,
        ],
        env,
    )
    print("auth login ok")

    token = login["data"].get("access_token")
    # CLI intentionally does not output token; use stored token from local config fallback.
    # Build authenticated HTTP client using token from token file if available.
    token_file = e2e_config_home / "cxpm-cli" / "tokens.json"
    if token_file.exists():
        raw = json.loads(token_file.read_text(encoding="utf-8"))
        profiles = raw.get("profiles", {})
        if profiles:
            token = next(iter(profiles.values())).get("access_token")
    if not token:
        raise RuntimeError("Unable to load token after login")

    with httpx.Client(base_url=args.api_url, headers={"Authorization": f"Bearer {token}"}, timeout=30.0) as client:
        project_id = create_project(client, args.project_name)
    print(f"project created: {project_id}")

    ingest, ingest_error = try_run_cli(
        [
            "--json",
            "--api-url",
            args.api_url,
            "meeting",
            "ingest",
            "--file",
            str(transcript_path),
            "--project-id",
            project_id,
            "--title",
            meeting_title,
            "--meeting-date",
            meeting_date,
        ],
        env,
    )
    if ingest is None:
        transcript_text = transcript_path.read_text(encoding="utf-8", errors="ignore")
        ingest, ingest_error_text = try_run_cli(
            [
                "--json",
                "--api-url",
                args.api_url,
                "meeting",
                "ingest",
                "--text",
                transcript_text,
                "--project-id",
                project_id,
                "--title",
                meeting_title,
                "--meeting-date",
                meeting_date,
            ],
            env,
        )
        if ingest is None:
            raise RuntimeError(
                "Ingest failed for both file and text modes.\n"
                f"file_error={ingest_error}\ntext_error={ingest_error_text}"
            )
    meeting_id = ingest["data"].get("meeting_id")
    if not meeting_id:
        raise RuntimeError("meeting_id missing from ingest output")
    print(f"meeting ingest ok: {meeting_id}")

    run_cli(["--json", "--api-url", args.api_url, "meeting", "review", meeting_id], env)
    print("meeting review ok")
    wait_for_meeting_ready(args.api_url, meeting_id, env, timeout_seconds=600)
    print("meeting readiness polling complete")

    apply_res = apply_with_retry(args.api_url, meeting_id, env, timeout_seconds=600)
    print("meeting apply ok")

    decision_strategy = "keep-existing"
    if apply_res["data"].get("conflicts"):
        run_cli(
            [
                "--json",
                "--non-interactive",
                "--api-url",
                args.api_url,
                "meeting",
                "resolve",
                meeting_id,
                "--decision-strategy",
                decision_strategy,
            ],
            env,
        )
        print("meeting resolve ok")
    else:
        print("no conflicts to resolve")

    run_cli(["--json", "--api-url", args.api_url, "requirement", "ls", "--project-id", project_id], env)
    print("requirement ls ok")

    run_cli(["--json", "--api-url", args.api_url, "requirement", "export", "--project-id", project_id], env)
    print("requirement export ok")

    run_cli(["--json", "--api-url", args.api_url, "jira", "epic", "generate", "--project-id", project_id], env)
    print("jira epic generate ok")

    run_cli(["--json", "--api-url", args.api_url, "auth", "status"], env)
    run_cli(["--json", "--api-url", args.api_url, "auth", "logout"], env)
    print("auth status/logout ok")

    print("E2E COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
