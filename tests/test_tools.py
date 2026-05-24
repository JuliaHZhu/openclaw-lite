"""Tests for tools/*.py — bare tools without security guards."""
from pathlib import Path

import pytest

from openclaw_lite.tools.file import fs_read_file, fs_write_file, fs_search_files
from openclaw_lite.tools.terminal import sys_terminal
from openclaw_lite.tools.web import net_web_search, net_web_extract


class TestFileTools:
    def test_read_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("line1\nline2\nline3")
        result = fs_read_file(str(f), offset=1, limit=2)
        assert result == "line1\nline2"

    def test_write_file(self, tmp_path):
        f = tmp_path / "out.txt"
        result = fs_write_file(str(f), "hello world")
        assert "Written" in result
        assert f.read_text() == "hello world"

    def test_write_creates_parents(self, tmp_path):
        f = tmp_path / "sub" / "dir" / "file.txt"
        fs_write_file(str(f), "nested")
        assert f.read_text() == "nested"

    def test_search_files(self, tmp_path):
        (tmp_path / "a.py").write_text("hello world\nfoo bar")
        (tmp_path / "b.py").write_text("hello again")
        result = fs_search_files("hello", str(tmp_path), "*.py")
        assert "a.py" in result
        assert "b.py" in result

    def test_search_no_matches(self, tmp_path):
        (tmp_path / "x.txt").write_text("nothing here")
        result = fs_search_files("xyz", str(tmp_path))
        assert result == "No matches"

    def test_read_file_error(self):
        result = fs_read_file("/nonexistent/path/file.txt")
        assert "Error:" in result


class TestTerminalTools:
    def test_sys_terminal_runs_command(self):
        result = sys_terminal("echo hello")
        assert "hello" in result

    def test_sys_terminal_with_timeout(self):
        result = sys_terminal("echo ok", timeout=5)
        assert "ok" in result

    def test_sys_terminal_error(self):
        result = sys_terminal("nonexistent_command_xyz_123")
        assert "Error:" in result or "not found" in result.lower() or "(no output)" in result


class TestWebTools:
    def test_web_search_returns_results(self):
        result = net_web_search("python programming language", num_results=3)
        assert isinstance(result, str)
        # DuckDuckGo may return results or "No results"
        assert len(result) > 0

    def test_web_extract_returns_text(self):
        result = net_web_extract("https://example.com")
        assert isinstance(result, str)
        # example.com should return some text
        assert len(result) > 0

    def test_web_extract_error(self):
        result = net_web_extract("https://invalid-domain-12345.example")
        assert "Fetch error:" in result or "error" in result.lower()
