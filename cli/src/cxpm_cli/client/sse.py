from __future__ import annotations

import json
from typing import Iterator

import httpx


def stream_events(client: httpx.Client, url: str, headers: dict[str, str]) -> Iterator[dict]:
    with client.stream("GET", url, headers=headers, timeout=None) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8") if isinstance(line, bytes) else line
            if text.startswith("data:"):
                raw = text.removeprefix("data:").strip()
                if raw == "[DONE]":
                    break
                try:
                    yield json.loads(raw)
                except json.JSONDecodeError:
                    yield {"message": raw}
