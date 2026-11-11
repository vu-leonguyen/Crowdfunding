"""Deterministic tests: never use a developer's RPC, JWT or deployed contracts."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from app.config import Settings, get_settings
from app.shared.web3_provider import get_web3_provider


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    monkeypatch.setitem(Settings.model_config, 'env_file', None)
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    get_settings.cache_clear()
    get_web3_provider.cache_clear()
    yield
    get_settings.cache_clear()
    get_web3_provider.cache_clear()
