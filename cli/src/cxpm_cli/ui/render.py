from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table

console = Console()


def render_kv(title: str, data: dict[str, Any]) -> None:
    table = Table(title=title)
    table.add_column("Field")
    table.add_column("Value")
    for key, value in data.items():
        table.add_row(str(key), str(value))
    console.print(table)


def render_list(title: str, items: list[dict[str, Any]]) -> None:
    table = Table(title=title)
    keys = set()
    for item in items:
        keys.update(item.keys())
    headers = sorted(keys)
    for header in headers:
        table.add_column(header)
    for item in items:
        table.add_row(*[str(item.get(header, "")) for header in headers])
    console.print(table)
