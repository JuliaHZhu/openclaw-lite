"""Shared test fixtures for openclaw-lite."""
import pytest

from openclaw_lite.registry import registry
from openclaw_lite.subagent import get_registry


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    """Reset global singletons after every test."""
    # Snapshot tool registry
    tool_before = set(registry.list_tools())
    # Snapshot subagent registry
    subreg = get_registry()
    sub_before = set(subreg._runs.keys())

    yield

    # Restore tool registry: remove anything added
    for name in set(registry.list_tools()) - tool_before:
        registry.deregister(name)

    # Restore subagent registry: clear anything added
    subreg_after = get_registry()
    for rid in set(subreg_after._runs.keys()) - sub_before:
        subreg_after._runs.pop(rid, None)
