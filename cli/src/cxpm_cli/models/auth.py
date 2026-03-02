from __future__ import annotations

from pydantic import BaseModel, model_validator


class AuthLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str | None = None


class AuthMeResponse(BaseModel):
    user_id: str
    email: str | None = None
    name: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, data):
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        payload.setdefault("user_id", payload.get("id") or payload.get("userId"))
        payload.setdefault("email", payload.get("email") or payload.get("username"))
        payload.setdefault("name", payload.get("name") or payload.get("full_name"))
        return payload
