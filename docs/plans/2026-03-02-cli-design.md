# CXPM CLI Design

Date: 2026-03-02
Status: Proposed
Owner: Agent-assisted design
Scope: V1 CLI for single-user power workflow, backend-driven, dual-mode (interactive + scriptable)

## 1. Goal

Build a production-quality CLI that reuses the existing backend APIs and business logic while providing:

1. Human-friendly interactive terminal experience by default.
2. Scriptable non-interactive mode from day one, including a deterministic conflict-resolution path.
3. Interactive conflict resolution for meeting apply/resolve flow.

This CLI is explicitly not a `curl` wrapper. It should be a first-class product interface.

## 2. Product Direction

Chosen direction:

1. Backend-driven CLI (reuse FastAPI APIs).
2. Dual mode from day one:
   - Interactive default for humans.
   - `--non-interactive` + `--json` for automation.
3. V1 target persona: single-user power workflow (not admin/collaboration-heavy CLI yet).
4. Implementation language: Python.

### Tradeoff summary

- Backend-driven provides fastest path with lowest business-logic drift.
- Dual mode raises complexity but avoids repainting architecture later.
- Interactive conflict resolver increases usability for core workflow while preserving scriptability elsewhere.

## 3. V1 Core Workflow (User Journey)

1. `cxpm auth login`
2. `cxpm meeting ingest`
3. `cxpm meeting review <meeting-id>`
4. `cxpm meeting apply <meeting-id>`
5. `cxpm meeting resolve <meeting-id>`
6. `cxpm requirement ls/export --project-id <id>`
7. `cxpm jira epic generate --project-id <id>` (optional)

### Command behavior

#### `cxpm auth login`
- Authenticates via `/api/auth/login`.
- Stores token locally (securely where possible).
- Verifies session via `/api/auth/me`.
- Supports non-interactive auth via `--token` or `CXPM_TOKEN` for CI and automation.
- On auth failure due to expiry, attempts one refresh (if refresh token/session exists) before surfacing error.

#### `cxpm auth logout`
- Clears local credentials for the active profile.
- Calls backend logout/revoke endpoint when available.
- Returns success even if revoke fails, but prints warning to stderr.

#### `cxpm auth status`
- Validates current credentials via `/api/auth/me`.
- Outputs machine-readable session state in `--json` mode.

#### `cxpm meeting ingest`
- Uploads file/text to `/api/meetings/upload`.
- Optional `--follow` attaches to SSE stream (`/api/meetings/{id}/stream`) and renders live extraction.

#### `cxpm meeting review`
- Reads `/api/meetings/{id}` and shows grouped items.
- Supports edit/add/delete via meeting item endpoints.

#### `cxpm meeting apply`
- Calls `/api/meetings/{id}/apply`.
- Displays categorized output: `added`, `skipped`, `conflicts`.
- No persistence happens here.

#### `cxpm meeting resolve`
- Interactive terminal conflict resolution.
- Submits final decisions to `/api/meetings/{id}/resolve`.
- Persists requirement changes and updates meeting to applied.
- Non-interactive mode is supported via `--decisions-file <path>` or `--decision-strategy <name>`.
- In `--non-interactive` mode, if unresolved conflicts remain and no strategy/file is provided, command exits `2`.

#### `cxpm requirement ls/export`
- List requirements via `/api/projects/{id}/requirements`.
- Export markdown via `/api/projects/{id}/requirements/export`.
- `requirement ls` uses cursor-based pagination.
- Default `--page-size` is `50` (max `200`).
- Supports `--cursor`, `--sort`, and repeated `--filter key=value`.
- Results are deterministically ordered by `updated_at desc, id asc` unless overridden by `--sort`.
- Invalid cursor/filter input fails with exit `2`.

#### `cxpm jira epic generate`
- Sends requirement text to `/api/jira-epic/generate`.
- Optional save via `/api/jira-stories/save`.

## 4. Command and Output Contract

### Global conventions

- `--json`: machine-readable output only on stdout.
- `--non-interactive`: no prompts; fail-fast if inputs missing.
- `--profile <name>`: config profile selection.
- `--api-url <url>`: override backend URL.
- `--verbose`: debug transport summaries (never secrets).
- `--request-id <id>`: optional caller-provided correlation id propagated as request header.
- `--no-color`: disable ANSI styling for logs and interactive output.

### Exit codes

- `0`: success
- `2`: usage/validation error
- `3`: auth/session error
- `4`: API/network error
- `5`: business-state error (e.g., meeting not processed)
- `6`: concurrency/version conflict (stale revision / optimistic lock failure)
- `7`: interrupted/resumable operation state written locally

### JSON contract principle

For commands supporting `--json`, output includes:

- `schema_version`
- `command`
- `status`
- `timestamp`
- `request_id`
- `data`
- optional `error`

No interactive text in JSON mode.

Base envelope (required shape):

```json
{
  "schema_version": "1.0",
  "command": "meeting apply",
  "status": "success",
  "timestamp": "2026-03-02T18:30:00Z",
  "request_id": "9d7c4a2a-66eb-4ee6-a31e-7ba8ff3d4b1f",
  "data": {},
  "error": null
}
```

`error` object contract when `status=error`:

```json
{
  "code": "AUTH_EXPIRED",
  "message": "Session expired",
  "retryable": true,
  "details": {}
}
```

Command-specific `data` schemas must be versioned and snapshot-tested.

`requirement ls --json` data shape:

```json
{
  "items": [],
  "next_cursor": null,
  "total_count": 0
}
```

### JSON schema governance

- Canonical JSON schemas live under `cli/schemas/<command>/<schema_version>.json`.
- Every `--json` command response MUST validate against one canonical schema in CI.
- Schema compatibility rules:
  - Additive fields: allowed in minor CLI releases.
  - Field removals/type changes/semantic changes: major CLI release only.
- `schema_version` in output MUST match the schema file used for validation.
- Deprecated schema versions must remain supported for at least one minor CLI release.

## 5. Internal Architecture

Recommended package layout:

```text
cli/
  pyproject.toml
  src/cxpm_cli/
    main.py
    errors.py
    commands/
      auth.py
      project.py
      meeting.py
      requirement.py
      jira.py
      config.py
    client/
      api.py
      sse.py
    models/
      auth.py
      project.py
      meeting.py
      requirement.py
      jira.py
      common.py
    workflows/
      meeting_flow.py
      resolve_flow.py
    ui/
      interactive.py
      render.py
      json_output.py
    state/
      store.py
      profiles.py
```

### Tech choices

- Typer: command framework
- Rich: tables, status, prompts, cards
- httpx: HTTP client + retries/timeouts
- pydantic: typed API models
- pytest: unit/integration tests

### Data and transport safety requirements

- Mutating requests (`meeting apply`, `meeting resolve`, `jira save`) MUST send an idempotency key.
- CLI retries are enabled only for retry-safe operations:
  - GET/HEAD: automatic retry with exponential backoff + jitter.
  - Mutations: retry only when an idempotency key is present and failure is transport-level or 5xx.
- CLI MUST surface whether a mutation result is `applied`, `already_applied`, or `unknown` after retry recovery.
- CLI MUST propagate backend entity revision/version values and include them in subsequent mutating requests.

### Backend capability matrix and fallback behavior

- CLI MUST detect backend capabilities at startup (idempotency support, revision/conflict support, compatibility metadata).
- If idempotency capability is unavailable, CLI disables mutation retries and prints warning to stderr.
- If revision/conflict capability is unavailable, CLI runs in best-effort mode and warns that stale-write detection is reduced.
- Exit code `6` is used only when backend provides explicit conflict/stale-revision response.
- Capability gaps MUST NOT silently change behavior in `--non-interactive` mode; warnings must be machine-visible in JSON `data.warnings`.

## 6. Interactive Conflict Resolver Design

Command: `cxpm meeting resolve <meeting-id>`

### Loop behavior

1. Load meeting + apply results.
2. If no conflicts, show summary and confirm apply.
3. If conflicts exist, present one conflict at a time with:
   - Existing requirement
   - New item
   - Classification + reason
4. Resolution actions:
   - `k`: keep existing
   - `r`: replace
   - `b`: keep both
   - `m`: merge (opens multiline editor)
   - `s`: skip for now
   - `p`: previous
5. Bulk assist: apply AI recommendations for unresolved conflicts.
6. Commit confirmation table, then submit resolve payload.

### Reliability behaviors

- Session progress kept in memory and checkpointed locally.
- On failure, write temp decision draft and print resume command.
- Checkpoint writes are atomic (write temp file then rename).
- Checkpoints include meeting id, base revision, and conflict ids to prevent replaying against wrong state.

### Non-interactive resolve contract

`cxpm meeting resolve <meeting-id> --non-interactive` requires one of:

1. `--decisions-file <path>`
2. `--decision-strategy keep-existing|replace-all|accept-ai`

Decision file JSON shape:

```json
{
  "meeting_id": "m_123",
  "base_revision": "rev_42",
  "decisions": [
    {
      "conflict_id": "c_001",
      "action": "keep|replace|both|merge",
      "merged_text": "required only when action=merge"
    }
  ]
}
```

Rules:

- Unknown conflict ids fail with exit `2`.
- Missing decisions for existing conflicts fail with exit `2` unless strategy is provided.
- `base_revision` mismatch fails with exit `6`.
- On success, JSON output includes counts for resolved, skipped, applied, and remaining.

### TTY and editor behavior

- If interactive resolve is requested without a TTY, command fails with exit `2` and prints required non-interactive flags.
- `merge` action uses `$EDITOR` when available; if unavailable, CLI falls back to inline multi-line prompt in TTY mode.
- In `--non-interactive` mode, merge content MUST come from `--decisions-file`; editor launch is forbidden.

## 7. Non-Interactive and Automation Rules

Even though conflict resolution is interactive for v1, broader CLI must be automation-ready:

1. Read-only/reporting commands fully support `--json`.
2. Mutating commands support deterministic non-interactive input flags, including `meeting resolve`.
3. Missing required inputs in `--non-interactive` mode produce exit code `2` with clear stderr.
4. No spinner/progress escape sequences in JSON mode.
5. In `--non-interactive` mode, prompts are forbidden and treated as implementation bugs.

## 8. Security and Local State

- Store auth token outside repo in user config directory.
- Prefer OS keyring when available.
- Support named profiles (e.g., `default`, `staging`, `prod`).
- Never log passwords or raw tokens.
- If keyring is unavailable, credentials are stored in a file with user-only permissions.
- `auth logout` clears both keyring and file fallback for the selected profile.

### Auth lifecycle requirements

- CLI MUST attempt exactly one silent refresh/re-auth path on first 401, then fail with exit `3`.
- CLI MUST expose token source precedence: flag > env > profile store.
- CLI MUST include `auth status` command for scriptable session checks.

Suggested paths:

- Windows: `%APPDATA%\cxpm-cli\`
- Linux/macOS: `$XDG_CONFIG_HOME/cxpm-cli` or `~/.config/cxpm-cli`

### Local config/state versioning and migration

- Local config and checkpoint files MUST include `config_version` or `state_version`.
- On startup, CLI auto-migrates older compatible versions before command execution.
- Migration is backup-first: CLI writes a timestamped backup before applying migrations.
- If migration fails, CLI restores the backup, exits `5`, and prints recovery guidance.
- CLI only guarantees automatic migration from the previous two CLI minor versions.
- If local state was written by a newer CLI major/minor version, CLI fails with exit `5` and does not mutate local files.

### Sensitive local data handling

- Checkpoints and migration backups MUST store the minimum data required to resume work.
- Checkpoints and backups MUST be written with user-only file permissions.
- Default retention for checkpoints/backups is `7 days`; older files are pruned automatically.
- `cxpm diagnostics` MUST not include raw checkpoint/backup contents unless explicitly requested via an opt-in flag.
- Diagnostic redaction MUST cover tokens, authorization headers, and free-text fields that may contain sensitive meeting content.

## 9. Test Strategy

### Unit tests

- API client, model parsing, error translation.
- JSON schema output snapshots.
- Decision payload builder for resolve.

### Command tests

- Typer `CliRunner` tests for help/options/errors.
- Exit-code assertions by failure type.

### Integration tests (mock server)

- Auth flow
- Ingest -> apply -> resolve happy path
- Conflict-heavy path with mixed decisions
- Network and auth-expiry failure paths
- Idempotent retry behavior for mutating commands
- Revision mismatch path returning exit `6`
- Non-interactive resolve with decisions file and strategy modes
- SSE reconnect/stream interruption behavior
- Backend capability downgrade paths (idempotency/revision unavailable) with expected warnings and retry behavior

### Required real-backend E2E suite

- Real auth login/status/logout flow against a test backend environment.
- Full workflow: ingest -> review -> apply -> resolve -> requirement export with persistence assertions.
- Non-interactive resolve via `--decisions-file` with backend-side state verification.
- Interrupt and resume flow for long-running commands with checkpoint recovery and final success.
- Compatibility E2E against current and previous supported backend minor versions.
- Install/upgrade E2E: fresh `pipx install`, run commands, upgrade CLI, run state migration, re-run commands.

### Required real-backend failure E2E matrix

- Auth failure path: expired session + refresh failure returns exit `3` with machine-readable error code.
- Revision conflict path: stale `base_revision` returns exit `6` with conflict metadata.
- Network interruption during mutation: command exits `4` or `7` per operation stage and supports deterministic resume behavior.
- Capability metadata unavailable: CLI runs with compatibility `unknown` warning and still executes supported commands.
- Non-interactive missing input path: required flags absent returns exit `2` with no prompt output.

### Required capability-state verification matrix

- Idempotency available + revision available: mutation retries enabled, conflict detection enabled.
- Idempotency unavailable + revision available: mutation retries disabled, conflict detection enabled, warning emitted.
- Idempotency available + revision unavailable: mutation retries enabled, stale-write warning emitted, no exit `6` expectation.
- Idempotency unavailable + revision unavailable: mutation retries disabled, best-effort mode warning emitted.
- Each matrix state MUST be validated in CI for both human-readable and `--json` outputs.

### Required command-level E2E assertions

- `meeting ingest --follow`: verifies stream render and completion status.
- `meeting review`: verifies grouped output and item edit/add/delete roundtrip.
- `meeting apply`: verifies categorized result (`added`, `skipped`, `conflicts`) and idempotent replay semantics.
- `meeting resolve` (interactive and non-interactive): verifies persisted changes and final meeting state.
- `requirement ls`: verifies pagination, deterministic ordering, cursor advancement, and filter behavior.
- `requirement export`: verifies produced markdown structure and content determinism.
- `jira epic generate`: verifies generated payload structure.
- `jira ... save` (when configured): verifies persistence confirmation and idempotent handling.

### Contract and platform tests

- JSON envelope and per-command schema snapshots are required for all `--json` commands.
- CLI/backend compatibility tests run against supported backend versions.
- Cross-platform smoke tests are required on Windows, macOS, and Linux.
- Non-TTY behavior tests are required for automation flows.

## 10. Phased Delivery Plan

### Phase 1: Foundation

- CLI scaffold, config/profile store, auth commands, JSON envelope contract.

### Phase 2: Meeting core

- ingest/review/apply/resolve (interactive + non-interactive resolver), idempotency keys, revision checks.

### Phase 3: Requirements and project utilities

- list/export and project selection helpers.

### Phase 4: Jira command

- generate + optional save.

### Phase 5: Hardening

- deterministic JSON contracts, retries/timeouts, docs polish, smoke suite, cross-platform CI.

### Phase 6: Distribution and operations

- Install path (`pipx` + wheel), version command, changelog, upgrade guidance, diagnostics command.

## 11. V1 Scope Guardrails

### In scope

1. Single-user power workflow.
2. Dual-mode fundamentals from day one.
3. Interactive conflict resolution.

### Out of scope (v1)

1. Admin command suite parity.
2. Full-screen TUI.
3. Local-only execution mode.
4. New backend features beyond existing endpoints.

## 12. V1 Definition of Done

Implementation is complete only when all are true:

1. End-to-end flow works in both interactive and non-interactive modes.
2. `--json` schemas are stable and snapshot-tested.
3. Idempotency and revision-conflict handling are validated by integration tests.
4. Cross-platform smoke tests pass on Windows, macOS, and Linux.
5. Packaging and install docs are verified using a clean environment.
6. Required real-backend E2E suite passes in CI.
7. Required real-backend failure E2E matrix and capability-state verification matrix pass in CI.
8. Required command-level E2E assertions pass for all V1 commands in scope.

## 13. Success Criteria

1. User can complete end-to-end meeting ingestion -> apply -> resolve entirely via CLI.
2. No raw curl-style UX required.
3. Script consumers can use `--json` on core reporting commands reliably.
4. Failure modes are deterministic and diagnosable by exit code and stderr.
5. Automation can complete apply->resolve with zero prompts.
6. CLI behavior is verified against at least one current and one previous supported backend version.

## 14. Backend Compatibility and Versioning

- CLI MUST send `X-CXPM-CLI-Version` on every request.
- CLI MUST verify backend compatibility at startup via existing backend metadata (version endpoint or response headers) without requiring new backend features.
- If compatibility metadata is unavailable, CLI continues with warning and marks compatibility as `unknown`.
- If compatibility metadata indicates incompatibility, CLI fails fast with exit `5`.
- Supported compatibility window:
  - Current backend release: required support.
  - Previous backend minor release: required support.
- On deprecation signals from backend, CLI prints actionable upgrade guidance to stderr.

## 15. Packaging, Release, and Upgrade Policy

- Release artifacts: Python wheel and source distribution.
- Recommended install path: `pipx install cxpm-cli`.
- CLI MUST provide `cxpm version` with CLI version, Python version, platform, and API base URL.
- Every release MUST include:
  - changelog entry
  - compatibility matrix update
  - smoke test evidence for supported platforms

## 16. Diagnostics and Supportability

- CLI MUST provide `cxpm diagnostics` command that outputs:
  - redacted config summary
  - profile name
  - API URL
  - CLI/backend version info
  - last error category and request id (if available)
- Logs MUST be structured and include timestamp, level, command, and request id.
- Diagnostic output MUST redact secrets by default.
- Log storage defaults:
  - max file size: `10MB`
  - retention: `7 days`
- Default log locations:
  - Windows: `%APPDATA%\cxpm-cli\logs\`
  - Linux/macOS: `$XDG_CONFIG_HOME/cxpm-cli/logs` or `~/.config/cxpm-cli/logs`

## 17. Performance and Reliability Targets

- `cxpm auth login` and `cxpm meeting review` median latency overhead introduced by CLI should be <= 200ms excluding network time.
- Long-running commands (`ingest --follow`, `resolve`) must handle Ctrl+C gracefully and emit a resume command.
- Retry policy defaults:
  - max attempts: 3
  - base backoff: 250ms
  - max backoff: 2s
