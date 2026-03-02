# CXPM CLI

Turn meeting transcripts into structured, reviewable product requirements.

## What You Get Out of Meetings

After ingesting a transcript, CXPM helps you produce:

- needs and goals
- requirements
- scope and constraints
- risks and open questions
- action items
- optional Jira epic draft

You can review and resolve conflicts before anything is finalized, then export results as markdown for sharing.

## Who This Is For

- product managers and founders
- delivery/program managers
- technical leads who want a fast post-meeting requirements workflow

You do not need to be deeply technical to run the core flow.

## Non-Technical Quickstart

If someone gave you a CXPM backend URL, you can run this flow end-to-end.

1. Install the CLI from this repo:

```bash
pip install -e ./cli
```

2. Point the CLI to your CXPM backend:

```bash
cxpm config profile set --name default --api-url http://localhost:3000
```

3. Login (interactive prompt):

```bash
cxpm auth login
```

4. Find your project:

```bash
cxpm project ls
```

5. Ingest a meeting transcript:

```bash
cxpm meeting ingest --file ./cx_assistant_design_meeting_transcript.txt --project-id <PROJECT_ID> --follow
```

6. Review, apply, and resolve:

```bash
cxpm meeting review <MEETING_ID>
cxpm meeting apply <MEETING_ID>
cxpm meeting resolve <MEETING_ID> --decision-strategy keep-existing
```

7. Export the final requirements:

```bash
cxpm requirement export --project-id <PROJECT_ID> --out requirements.md
```

8. Optionally generate a Jira epic draft:

```bash
cxpm jira epic generate --project-id <PROJECT_ID>
```

## Command Cheat Sheet

- `cxpm meeting ingest`: upload transcript text/file and start extraction
- `cxpm meeting review`: inspect extracted items before applying
- `cxpm meeting apply`: create proposed requirement changes
- `cxpm meeting resolve`: resolve conflicts and finalize changes
- `cxpm requirement ls`: list resulting requirements (supports section filter)
- `cxpm requirement export`: export markdown for docs/sharing
- `cxpm jira epic generate`: generate Jira-ready epic content from requirements

## Technical / Automation Mode

Use `--json` for machine-readable output:

```bash
cxpm --json requirement ls --project-id <PROJECT_ID> --section action-items
```

For development dependencies:

```bash
pip install -e ./cli[dev]
```

Run tests:

```bash
pytest cli/tests -q
```

Run real backend E2E:

```bash
python cli/tests/e2e/run_real_backend_e2e.py \
  --api-url http://localhost:3000 \
  --username you@example.com \
  --password 'yourPassword' \
  --transcript ./cx_assistant_design_meeting_transcript.txt
```

## Repository Layout

- `cli/`: Python package (`cxpm-cli`) with source code and tests
- `docs/`: design and planning docs
- `cx_assistant_design_meeting_transcript.txt`: sample transcript for testing
