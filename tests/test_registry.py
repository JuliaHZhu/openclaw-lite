"""Tests for registry.py — ToolRegistry."""
import threading
import time

import pytest
from openclaw_lite.registry import ToolRegistry, registry


def dummy_handler(x: int = 1):
    return f"result-{x}"


class TestToolRegistry:
    def test_register_and_get_schema(self):
        r = ToolRegistry()
        r.register("add", "Add two numbers", {"properties": {"a": {"type": "integer"}}}, dummy_handler)
        schema = r.get_schema("add")
        assert schema is not None
        assert schema["name"] == "add"
        assert schema["description"] == "Add two numbers"

    def test_deregister(self):
        r = ToolRegistry()
        r.register("sub", "Subtract", {"properties": {}}, dummy_handler)
        assert r.has_tool("sub")
        assert r.deregister("sub") is True
        assert not r.has_tool("sub")
        assert r.deregister("sub") is False

    def test_get_schemas_filtered(self):
        r = ToolRegistry()
        r.register("a", "A", {"properties": {}}, dummy_handler, tags=["math"])
        r.register("b", "B", {"properties": {}}, dummy_handler, tags=["text"])
        r.register("c", "C", {"properties": {}}, dummy_handler, tags=["math", "text"])

        assert len(r.get_schemas()) == 3
        assert len(r.get_schemas(tags=["math"])) == 2
        assert len(r.get_schemas(enabled=["a", "b"])) == 2

    def test_call_tool(self):
        r = ToolRegistry()
        r.register("echo", "Echo", {"properties": {"msg": {"type": "string"}}}, lambda msg: msg)
        assert r.call("echo", {"msg": "hello"}) == "hello"

    def test_call_missing_tool(self):
        r = ToolRegistry()
        assert "not found" in r.call("missing", {})

    def test_call_tool_error(self):
        r = ToolRegistry()
        r.register("boom", "Boom", {"properties": {}}, lambda: (_ for _ in ()).throw(ValueError("fail")))
        result = r.call("boom", {})
        assert "Error:" in result
        assert "fail" in result

    def test_list_by_category(self):
        r = ToolRegistry()
        r.register("x", "X", {"properties": {}}, dummy_handler, category="cat1")
        r.register("y", "Y", {"properties": {}}, dummy_handler, category="cat2")
        r.register("z", "Z", {"properties": {}}, dummy_handler)
        groups = r.list_by_category()
        assert "cat1" in groups and "x" in groups["cat1"]
        assert "cat2" in groups and "y" in groups["cat2"]
        assert "uncategorized" in groups and "z" in groups["uncategorized"]

    def test_schema_caching(self):
        r = ToolRegistry()
        r.register("cached", "Cached", {"properties": {}}, dummy_handler)
        s1 = r.get_schemas(enabled=["cached"])
        s2 = r.get_schemas(enabled=["cached"])
        assert s1 == s2
        r.register("cached2", "C2", {"properties": {}}, dummy_handler)
        s3 = r.get_schemas(enabled=["cached"])
        assert len(s3) == 1

    def test_cache_ttl_eviction(self):
        r = ToolRegistry()
        r.register("t", "T", {"properties": {}}, dummy_handler)
        r._cache_ttl_seconds = 0.001
        r.get_schemas()
        time.sleep(0.01)
        schemas = r.get_schemas()
        assert len(schemas) == 1

    def test_thread_safety_register(self):
        r = ToolRegistry()
        errors = []

        def worker(i):
            try:
                r.register(f"t{i}", f"T{i}", {"properties": {}}, dummy_handler)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert len(r.list_tools()) == 50

    def test_snapshot(self):
        r = ToolRegistry()
        r.register("snap", "Snap", {"properties": {}}, dummy_handler, tags=["a"], category="c")
        snap = r.snapshot()
        assert "snap" in snap
        assert snap["snap"]["category"] == "c"
        assert "a" in snap["snap"]["tags"]


def test_module_level_registry_has_default_tools():
    names = registry.list_tools()
    assert "fs_read_file" in names
    assert "fs_write_file" in names
    assert "fs_search_files" in names
    assert "sys_terminal" in names
    assert "net_web_search" in names
    assert "net_web_extract" in names
