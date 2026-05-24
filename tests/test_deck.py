"""Tests for deck.py — Deck and build_deck."""
import pytest
from openclaw_lite.deck import Deck, build_deck, BASELINE_POOL
from openclaw_lite.registry import ToolRegistry


def make_registry(names):
    r = ToolRegistry()
    for n in names:
        r.register(n, f"Desc {n}", {"properties": {}}, lambda **kw: "ok")
    return r


class TestDeck:
    def test_deduplication(self):
        r = make_registry(["a", "b"])
        d = Deck(["a", "a", "b", "a"], r)
        assert d.tools == ["a", "b"]

    def test_has(self):
        r = make_registry(["x", "y"])
        d = Deck(["x"], r)
        assert d.has("x")
        assert not d.has("y")

    def test_schemas(self):
        r = make_registry(["m"])
        d = Deck(["m"], r)
        schemas = d.schemas()
        assert len(schemas) == 1
        assert schemas[0]["name"] == "m"

    def test_schemas_skip_missing(self):
        r = make_registry(["m"])
        d = Deck(["m", "missing"], r)
        schemas = d.schemas()
        assert len(schemas) == 1

    def test_get_schemas_for_protocol_openai(self):
        r = make_registry(["t"])
        r.register("t", "Tool T", {"properties": {"p": {"type": "string"}}}, lambda **kw: "ok")
        d = Deck(["t"], r)
        schemas = d.get_schemas_for_protocol("openai")
        assert len(schemas) == 1
        assert schemas[0]["type"] == "function"
        assert schemas[0]["function"]["name"] == "t"
        assert "parameters" in schemas[0]["function"]

    def test_get_schemas_for_protocol_anthropic(self):
        r = make_registry(["t"])
        r.register("t", "Tool T", {"properties": {}}, lambda **kw: "ok")
        d = Deck(["t"], r)
        schemas = d.get_schemas_for_protocol("anthropic")
        assert len(schemas) == 1
        assert schemas[0]["name"] == "t"
        assert "type" not in schemas[0]

    def test_size(self):
        r = make_registry(["a", "b", "c"])
        d = Deck(["a", "b"], r)
        assert d.size() == 2

    def test_repr(self):
        r = make_registry(["a"])
        d = Deck(["a"], r)
        assert repr(d) == "Deck(['a'])"


class TestBuildDeck:
    def test_build_deck_adds_redundancy(self):
        r = make_registry(BASELINE_POOL)
        d = build_deck([], r, redundancy=3)
        assert d.size() == 3
        assert d.tools[0] == BASELINE_POOL[0]
        assert d.tools[1] == BASELINE_POOL[1]
        assert d.tools[2] == BASELINE_POOL[2]

    def test_build_deck_does_not_duplicate_skill_tools(self):
        r = make_registry(BASELINE_POOL)
        d = build_deck([BASELINE_POOL[0]], r, redundancy=3)
        assert BASELINE_POOL[0] in d.tools
        assert d.size() == 4

    def test_build_deck_respects_redundancy_zero(self):
        r = make_registry(BASELINE_POOL)
        d = build_deck(["fs_read_file"], r, redundancy=0)
        assert d.size() == 1

    def test_build_deck_skips_missing_tools(self):
        r = make_registry([BASELINE_POOL[0]])
        d = build_deck([], r, redundancy=5)
        assert d.size() == 1
