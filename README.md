# CXPM CLI

Command-line interface for the CXPM workflow:
- authenticate with the backend
- ingest meeting transcripts
- review/apply/resolve extracted items
- list/export requirements
- generate Jira epic output

The CLI supports both human-readable output and strict JSON output (`--json`) for automation.

## Repository Layout

- `cli/` - Python package (`cxpm-cli`) with source code and tests
- `docs/` - design and planning docs
- `cx_assistant_design_meeting_transcript.txt` - sample transcript for E2E testing

## Prerequisites

- Python 3.11+
- A reachable CXPM backend API URL (for example: `http://localhost:3000`)

## Install (Editable)

```bash
pip install -e ./cli
```

For development dependencies:

```bash
pip install -e ./cli[dev]
```

## Quickstart

Set backend profile:

```bash
cxpm config profile set --name default --api-url http://localhost:3000
```

Login:

```bash
cxpm auth login --username you@example.com --password 'yourPassword'
```

Create/inspect projects:

```bash
cxpm project ls
```

Ingest a meeting transcript and stream extraction:

```bash
cxpm meeting ingest --file ./cx_assistant_design_meeting_transcript.txt --project-id <PROJECT_ID> --follow
```

Review, apply, resolve:

```bash
cxpm meeting review <MEETING_ID>
cxpm meeting apply <MEETING_ID>
cxpm meeting resolve <MEETING_ID> --decision-strategy keep-existing
```

Requirements:

```bash
cxpm requirement ls --project-id <PROJECT_ID>
cxpm requirement ls --project-id <PROJECT_ID> --section action-items
cxpm requirement export --project-id <PROJECT_ID> --out requirements.md
```

Jira epic generation:

```bash
cxpm jira epic generate --project-id <PROJECT_ID>
```

## JSON Mode (Automation)

All commands support `--json` for machine-readable output:

```bash
cxpm --json requirement ls --project-id <PROJECT_ID> --section action-items
```

## Run Tests

```bash
pytest cli/tests -q
```

## Real Backend E2E

```bash
pytest cli/tests -q
python cli/tests/e2e/run_real_backend_e2e.py \
  --api-url http://localhost:3000 \
  --username you@example.com \
  --password 'yourPassword' \
  --transcript ./cx_assistant_design_meeting_transcript.txt
```

## Publish to GitHub

This workspace is already a git repo but currently has no remote configured.

1. Authenticate GitHub CLI:

```bash
gh auth login -h github.com
```

2. Create and push a new repo:

```bash
gh repo create <your-org-or-user>/<repo-name> --private --source . --remote origin --push
```

Use `--public` instead of `--private` if you want a public repository.
