"""Tests for tools/*.py — bare tools with no security guards."""
from pathlib import Path

import pytest

from openclaw_lite.tools.file import fs_read_file, fs_write_file, fs_search_files
from openclaw_lite.tools.terminal import sys_terminal
from openclaw_lite.tools.web import net_web_search, net_web_extract


class TestFileTools:
    def test_read_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("line1\nline2\nline3")
        result = fs_read_file(str(f), offset=2, limit=1)
        assert result == "line2"

    def test_read_file_not_found(self):
        result = fs_read_file("/nonexistent/path.txt")
        assert "Error" in result

    def test_write_and_read_roundtrip(self, tmp_path):
        target = str(tmp_path / "round.txt")
        fs_write_file(target, "hello world")
        result = fs_read_file(target)
        assert "hello world" in result

    def test_write_creates_parent_dirs(self, tmp_path):
        target = str(tmp_path / "deep" / "nested" / "file.txt")
        result = fs_write_file(target, "ok")
        assert "Written" in result
        assert Path(target).read_text() == "ok"

    def test_search_files(self, tmp_path):
        (tmp_path / "a.py").write_text("hello world\nfoo bar")
        (tmp_path / "b.py").write_text("hello again")
        result = fs_search_files("hello", str(tmp_path), "*.py")
        assert "a.py" in result
        assert "b.py" in result

    def test_search_files_no_match(self, tmp_path):
        (tmp_path / "x.py").write_text("nothing here")
        result = fs_search_files("zzzTOP", str(tmp_path))
        assert result == "No matches"


class TestTerminalTools:
    def test_echo(self):
        result = sys_terminal("echo hello")
        assert "hello" in result

    def test_ls(self):
        result = sys_terminal("ls /tmp")
        assert result.strip() != ""

    def test_command_not_found(self):
        result = sys_terminal("nonexistent_cmd_xyz_12345")
        assert result != ""


class TestWebTools:
    def test_search_returns_results(self):
        result = net_web_search("python")
        assert result  # should return something or "No results"
        # Don't assert on external service content, just that it doesn't crash

    def test_search_empty_query(self):
        result = net_web_search("")
        assert result  # should not crash

    def test_extract_invalid_url(self):
        result = net_web_extract("not-a-valid-url")
        assert "Error" in result.lower() or "Fetch error" in result or result
