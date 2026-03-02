from __future__ import annotations

from enum import IntEnum
from typing import Any


class ExitCode(IntEnum):
    SUCCESS = 0
    USAGE = 2
    AUTH = 3
    API = 4
    BUSINESS = 5
    CONFLICT = 6
    INTERRUPTED = 7


class CLIError(Exception):
    def __init__(
        self,
        message: str,
        *,
        exit_code: ExitCode,
        error_code: str,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.error_code = error_code
        self.retryable = retryable
        self.details = details or {}


class UsageError(CLIError):
    def __init__(self, message: str, *, error_code: str = "USAGE_ERROR", details: dict[str, Any] | None = None) -> None:
        super().__init__(message, exit_code=ExitCode.USAGE, error_code=error_code, details=details)


class AuthError(CLIError):
    def __init__(
        self,
        message: str,
        *,
        error_code: str = "AUTH_ERROR",
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            exit_code=ExitCode.AUTH,
            error_code=error_code,
            retryable=retryable,
            details=details,
        )


class APIError(CLIError):
    def __init__(
        self,
        message: str,
        *,
        error_code: str = "API_ERROR",
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            exit_code=ExitCode.API,
            error_code=error_code,
            retryable=retryable,
            details=details,
        )


class BusinessStateError(CLIError):
    def __init__(
        self,
        message: str,
        *,
        error_code: str = "BUSINESS_STATE_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, exit_code=ExitCode.BUSINESS, error_code=error_code, details=details)


class ConflictError(CLIError):
    def __init__(
        self,
        message: str,
        *,
        error_code: str = "REVISION_CONFLICT",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, exit_code=ExitCode.CONFLICT, error_code=error_code, details=details)


class InterruptedError(CLIError):
    def __init__(
        self,
        message: str,
        *,
        error_code: str = "INTERRUPTED",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, exit_code=ExitCode.INTERRUPTED, error_code=error_code, details=details)
