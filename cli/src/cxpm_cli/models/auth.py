from __future__ import annotations

from pydantic import BaseModel


class AuthLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str | None = None


class AuthMeResponse(BaseModel):
    user_id: str
    email: str
    name: str | None = None
