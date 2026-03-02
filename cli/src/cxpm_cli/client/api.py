from __future__ import annotations

import os
from pathlib import Path
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx

from cxpm_cli.errors import APIError, AuthError, BusinessStateError, ConflictError
from cxpm_cli.models.auth import AuthLoginResponse, AuthMeResponse
from cxpm_cli.models.common import CapabilityInfo


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    base_backoff_seconds: float = 0.25
    max_backoff_seconds: float = 2.0


def _backoff(attempt: int, policy: RetryPolicy) -> float:
    value = policy.base_backoff_seconds * (2 ** attempt)
    return min(value, policy.max_backoff_seconds)


class APIClient:
    def __init__(
        self,
        api_url: str,
        *,
        token: str | None = None,
        refresh_token: str | None = None,
        request_id: str | None = None,
        timeout: float = 30.0,
        retry_policy: RetryPolicy | None = None,
        cli_version: str = "0.1.0",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.token = token
        self.refresh_token = refresh_token
        self.request_id = request_id or str(uuid4())
        self.cli_version = cli_version
        self.retry_policy = retry_policy or RetryPolicy()
        self._client = httpx.Client(timeout=timeout, base_url=self.api_url, transport=transport)
        self.capabilities = CapabilityInfo()
        self.warnings: list[str] = []

    def close(self) -> None:
        self._client.close()

    def detect_capabilities(self) -> CapabilityInfo:
        try:
            resp = self._client.get("/api/version", headers=self._base_headers())
            if resp.status_code == 404:
                raise APIError("Compatibility metadata unavailable", error_code="COMPATIBILITY_UNKNOWN")
            payload = resp.json()
            features = payload.get("features", {})
            self.capabilities = CapabilityInfo(
                idempotency=bool(features.get("idempotency", True)),
                revision_conflict=bool(features.get("revision_conflict", True)),
                compatibility_metadata=True,
                compatibility_state="known",
            )
            compatible = payload.get("compatible", True)
            if not compatible:
                raise BusinessStateError("Backend is incompatible with this CLI", error_code="BACKEND_INCOMPATIBLE")
        except (httpx.RequestError, APIError, ValueError):
            self.capabilities = CapabilityInfo(
                idempotency=True,
                revision_conflict=True,
                compatibility_metadata=False,
                compatibility_state="unknown",
            )
            self.warnings.append("Compatibility metadata unavailable; compatibility state is unknown")
        if not self.capabilities.idempotency:
            self.warnings.append("Backend idempotency capability unavailable; mutation retries disabled")
        if not self.capabilities.revision_conflict:
            self.warnings.append("Revision conflict capability unavailable; stale-write detection reduced")
        return self.capabilities

    def _base_headers(self) -> dict[str, str]:
        headers = {
            "X-CXPM-CLI-Version": self.cli_version,
            "X-Request-Id": self.request_id,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        data_body: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        mutating: bool = False,
        revision: str | None = None,
    ) -> dict[str, Any]:
        headers = self._base_headers()
        idempotency_key: str | None = None
        retry_allowed = method.upper() in {"GET", "HEAD"}
        if mutating:
            idempotency_key = str(uuid4())
            headers["Idempotency-Key"] = idempotency_key
            retry_allowed = self.capabilities.idempotency
        if revision:
            headers["If-Match"] = revision

        last_error: Exception | None = None
        for attempt in range(self.retry_policy.max_attempts):
            try:
                response = self._client.request(
                    method,
                    path,
                    json=json_body,
                    data=data_body,
                    files=files,
                    params=params,
                    headers=headers,
                )
                if response.status_code == 401:
                    if self._try_refresh():
                        headers = self._base_headers()
                        if idempotency_key:
                            headers["Idempotency-Key"] = idempotency_key
                        if revision:
                            headers["If-Match"] = revision
                        continue
                    raise AuthError(
                        "Session expired",
                        error_code="AUTH_EXPIRED",
                        retryable=False,
                    )
                if response.status_code in {409, 412}:
                    if self.capabilities.revision_conflict:
                        raise ConflictError(
                            "Revision conflict",
                            details=response.json() if response.content else {},
                        )
                    raise BusinessStateError("Conflict returned by backend", error_code="CONFLICT_UNSUPPORTED")
                if response.status_code >= 500:
                    raise APIError("Backend server error", error_code="BACKEND_5XX", retryable=True)
                if response.status_code >= 400:
                    details = response.json() if response.content else {}
                    if response.status_code == 422:
                        raise BusinessStateError("Validation error", error_code="VALIDATION_ERROR", details=details)
                    raise APIError(
                        f"Request failed with status {response.status_code}",
                        error_code="HTTP_ERROR",
                        details=details,
                    )
                payload: dict[str, Any]
                if response.headers.get("content-type", "").startswith("application/json"):
                    payload = response.json()
                else:
                    payload = {"text": response.text}
                payload.setdefault("request_id", response.headers.get("X-Request-Id", self.request_id))
                payload.setdefault("mutation_state", "applied" if mutating else "n/a")
                return payload
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if not retry_allowed or attempt >= self.retry_policy.max_attempts - 1:
                    break
                time.sleep(_backoff(attempt, self.retry_policy))
                continue
            except APIError as exc:
                last_error = exc
                if mutating and not self.capabilities.idempotency:
                    break
                if not exc.retryable or not retry_allowed or attempt >= self.retry_policy.max_attempts - 1:
                    break
                time.sleep(_backoff(attempt, self.retry_policy))
                continue
        if isinstance(last_error, APIError):
            if mutating:
                raise APIError(
                    "Mutation status unknown after retries",
                    error_code="MUTATION_UNKNOWN",
                    retryable=True,
                    details={"mutation_state": "unknown"},
                ) from last_error
            raise last_error
        raise APIError("Network error", error_code="NETWORK_ERROR", retryable=True)

    def _try_refresh(self) -> bool:
        if not self.refresh_token:
            return False
        resp = self._client.post(
            "/api/auth/refresh",
            json={"refresh_token": self.refresh_token},
            headers={"X-CXPM-CLI-Version": self.cli_version, "X-Request-Id": self.request_id},
        )
        if resp.status_code >= 400:
            return False
        body = resp.json()
        token = body.get("access_token")
        if not token:
            return False
        self.token = token
        self.refresh_token = body.get("refresh_token", self.refresh_token)
        return True

    def _login_with_payload(self, *, payload: dict[str, Any], as_form: bool = False) -> dict[str, Any]:
        # Login must be attempted without bearer auth header to avoid stale-token interference.
        headers = {
            "X-CXPM-CLI-Version": self.cli_version,
            "X-Request-Id": self.request_id,
        }
        response = self._client.post(
            "/api/auth/login",
            data=payload if as_form else None,
            json=None if as_form else payload,
            headers=headers,
        )
        if response.status_code >= 400:
            details = response.json() if response.content else {}
            if response.status_code in {400, 401, 422}:
                raise AuthError(
                    "Login payload rejected",
                    error_code="AUTH_LOGIN_REJECTED",
                    details=details,
                )
            raise AuthError(
                f"Login failed with status {response.status_code}",
                error_code="AUTH_LOGIN_FAILED",
                details=details,
            )
        return response.json()

    def login(self, username: str | None = None, password: str | None = None, token: str | None = None) -> AuthLoginResponse:
        if token:
            return AuthLoginResponse(access_token=token, token_type="bearer")
        if not username or not password:
            raise AuthError("Username and password are required", error_code="AUTH_INPUT_REQUIRED")
        attempts = [
            ({"username": username, "password": password}, False),
            ({"email": username, "password": password}, False),
            ({"username": username, "password": password}, True),
            ({"email": username, "password": password}, True),
        ]
        last_error: AuthError | None = None
        for payload, as_form in attempts:
            try:
                raw = self._login_with_payload(payload=payload, as_form=as_form)
                if "access_token" not in raw and isinstance(raw.get("data"), dict):
                    raw = raw["data"]
                return AuthLoginResponse.model_validate(raw)
            except AuthError as exc:
                last_error = exc
                continue
        raise AuthError(
            "Login failed for all supported payload formats",
            error_code="AUTH_LOGIN_FAILED",
            details=last_error.details if last_error else {},
        )

    def me(self) -> AuthMeResponse:
        payload = self._request("GET", "/api/auth/me")
        return AuthMeResponse.model_validate(payload)

    def logout(self) -> dict[str, Any]:
        try:
            return self._request("POST", "/api/auth/logout", mutating=True)
        except APIError:
            return {"revoked": False}

    def upload_meeting(
        self,
        *,
        text: str | None,
        file_path: str | None,
        project_id: str | None = None,
        title: str | None = None,
        meeting_date: str | None = None,
    ) -> dict[str, Any]:
        text_attempts: list[dict[str, Any]] = []
        file_attempts: list[tuple[str, dict[str, Any], dict[str, Any] | None]] = []

        if text:
            text_attempts = [
                {"text": text},
                {"transcript_text": text},
                {"content": text},
                {"transcript": text},
            ]
            if project_id:
                for item in text_attempts:
                    item["project_id"] = project_id
                text_attempts.extend(
                    [
                        {"text": text, "projectId": project_id},
                        {"transcript": text, "projectId": project_id},
                    ]
                )
            for item in text_attempts:
                if title:
                    item["title"] = title
                if meeting_date:
                    item["meeting_date"] = meeting_date
                    item["meetingDate"] = meeting_date

        if file_path:
            path = Path(file_path)
            file_bytes = path.read_bytes()
            base_data: dict[str, Any] = {}
            if project_id:
                base_data["project_id"] = project_id
            if title:
                base_data["title"] = title
            if meeting_date:
                base_data["meeting_date"] = meeting_date
            file_attempts = [
                ("file", {"file": (path.name, file_bytes, "text/plain")}, base_data or None),
                ("transcript_file", {"transcript_file": (path.name, file_bytes, "text/plain")}, base_data or None),
                ("transcript", {"transcript": (path.name, file_bytes, "text/plain")}, base_data or None),
                ("meeting_file", {"meeting_file": (path.name, file_bytes, "text/plain")}, base_data or None),
            ]
            if project_id:
                file_attempts.extend(
                    [
                        (
                            "file",
                            {"file": (path.name, file_bytes, "text/plain")},
                            {
                                "projectId": project_id,
                                **({"title": title} if title else {}),
                                **({"meetingDate": meeting_date} if meeting_date else {}),
                            },
                        ),
                        (
                            "transcript",
                            {"transcript": (path.name, file_bytes, "text/plain")},
                            {
                                "projectId": project_id,
                                **({"title": title} if title else {}),
                                **({"meetingDate": meeting_date} if meeting_date else {}),
                            },
                        ),
                    ]
                )
            decoded = file_bytes.decode("utf-8", errors="ignore")
            if decoded.strip():
                payload = {"text": decoded}
                if project_id:
                    payload["project_id"] = project_id
                if title:
                    payload["title"] = title
                if meeting_date:
                    payload["meeting_date"] = meeting_date
                    payload["meetingDate"] = meeting_date
                text_attempts.append(payload)

        last_error: Exception | None = None

        for payload in text_attempts:
            try:
                return self._request("POST", "/api/meetings/upload", json_body=payload, mutating=True)
            except BusinessStateError as exc:
                last_error = exc
                continue

        for _, files_payload, data_payload in file_attempts:
            try:
                return self._request(
                    "POST",
                    "/api/meetings/upload",
                    data_body=data_payload,
                    files=files_payload,
                    mutating=True,
                )
            except BusinessStateError as exc:
                last_error = exc
                continue

        if last_error:
            raise last_error
        raise APIError("Meeting ingest requires text or file", error_code="INGEST_INPUT_REQUIRED")

    def get_meeting(self, meeting_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/meetings/{meeting_id}")

    def update_meeting_item(self, meeting_id: str, item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", f"/api/meetings/{meeting_id}/items/{item_id}", json_body=payload, mutating=True)

    def create_meeting_item(self, meeting_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/api/meetings/{meeting_id}/items", json_body=payload, mutating=True)

    def delete_meeting_item(self, meeting_id: str, item_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/api/meetings/{meeting_id}/items/{item_id}", mutating=True)

    def apply_meeting(self, meeting_id: str, revision: str | None = None) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/meetings/{meeting_id}/apply",
            mutating=True,
            revision=revision,
        )

    def resolve_meeting(self, meeting_id: str, payload: dict[str, Any], revision: str | None = None) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/meetings/{meeting_id}/resolve",
            json_body=payload,
            mutating=True,
            revision=revision,
        )

    def list_requirements(
        self,
        project_id: str,
        *,
        page_size: int,
        cursor: str | None,
        sort: str | None,
        filters: list[str],
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"page_size": page_size}
        if cursor:
            params["cursor"] = cursor
        if sort:
            params["sort"] = sort
        if filters:
            params["filter"] = filters
        return self._request("GET", f"/api/projects/{project_id}/requirements", params=params)

    def list_projects(self) -> dict[str, Any]:
        return self._request("GET", "/api/projects")

    def export_requirements(self, project_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/requirements/export")

    def generate_epic(self, project_id: str, requirements_text: str | None = None) -> dict[str, Any]:
        body = {"project_id": project_id}
        if requirements_text:
            body["requirements_text"] = requirements_text
        return self._request("POST", "/api/jira-epic/generate", json_body=body, mutating=True)

    def save_stories(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/jira-stories/save", json_body=payload, mutating=True)
