from __future__ import annotations

import shutil
from pathlib import Path
import sys

import pytest


@pytest.fixture(scope="session")
def runtime_root() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test-runtime"
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture(autouse=True)
def isolated_config(runtime_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(runtime_root))
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("CXPM_TOKEN", raising=False)


def pytest_sessionstart() -> None:
    src = Path(__file__).resolve().parents[1] / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
