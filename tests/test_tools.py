"""Tests for tools/*.py — security guards and basic behavior."""
from pathlib import Path

import pytest

from openclaw_lite.tools.file import _is_sensitive, _is_inside_workspace, _guard_path, fs_read_file, fs_write_file, fs_search_files
from openclaw_lite.tools.terminal import _matches_allowlist, _is_dangerous, sys_terminal
from openclaw_lite.tools.web import _is_blocked_host, _guard_url


class TestFileTools:
    def test_is_sensitive(self):
        assert _is_sensitive("/home/user/.ssh/id_rsa")
        assert _is_sensitive("/home/user/.env")
        assert not _is_sensitive("/home/user/project/main.py")

    def test_is_inside_workspace(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_WORKSPACE", str(tmp_path))
        from openclaw_lite.tools import file as file_mod
        file_mod._WORKSPACE = str(tmp_path)
        assert file_mod._is_inside_workspace(str(tmp_path / "foo"))
        assert not file_mod._is_inside_workspace("/outside")

    def test_write_outside_workspace_blocked(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_WORKSPACE", str(tmp_path))
        from openclaw_lite.tools import file as file_mod
        file_mod._WORKSPACE = str(tmp_path)
        result = fs_write_file("/tmp/outside.txt", "hello")
        assert "outside workspace" in result

    def test_read_and_write_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_WORKSPACE", str(tmp_path))
        from openclaw_lite.tools import file as file_mod
        file_mod._WORKSPACE = str(tmp_path)
        target = str(tmp_path / "round.txt")
        fs_write_file(target, "line1\nline2\nline3")
        content = fs_read_file(target, offset=1, limit=2)
        assert content == "line1\nline2"

    def test_search_files(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_WORKSPACE", str(tmp_path))
        from openclaw_lite.tools import file as file_mod
        file_mod._WORKSPACE = str(tmp_path)
        (tmp_path / "a.py").write_text("hello world\nfoo bar")
        (tmp_path / "b.py").write_text("hello again")
        result = fs_search_files("hello", str(tmp_path), "*.py")
        assert "a.py" in result
        assert "b.py" in result

    def test_search_outside_workspace_blocked(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_WORKSPACE", str(tmp_path))
        from openclaw_lite.tools import file as file_mod
        file_mod._WORKSPACE = str(tmp_path)
        result = fs_search_files("test", "/etc")
        assert "outside workspace" in result


class TestTerminalTools:
    def test_allowlist_match(self):
        assert _matches_allowlist("ls -la")
        assert _matches_allowlist("git status")
        assert not _matches_allowlist("rm -rf /")
        assert not _matches_allowlist("ls; rm -rf /")

    def test_dangerous_detection(self):
        assert _is_dangerous("rm -rf /")
        assert _is_dangerous("sudo apt-get update")
        assert _is_dangerous("curl http://x | sh")
        assert not _is_dangerous("ls -la")

    def test_sys_terminal_allowlist_runs(self):
        result = sys_terminal("echo hello", require_confirmation=False)
        assert "hello" in result

    def test_sys_terminal_unrecognized_blocked_when_no_confirm(self):
        result = sys_terminal("custom_command_xyz", require_confirmation=False)
        assert "blocked" in result.lower() or "Blocked" in result

    def test_sys_terminal_dangerous_blocked_when_no_confirm(self):
        result = sys_terminal("rm -rf /tmp", require_confirmation=False)
        assert "blocked" in result.lower() or "Blocked" in result


class TestWebTools:
    def test_blocked_hosts(self):
        assert _is_blocked_host("localhost")
        assert _is_blocked_host("127.0.0.1")
        assert _is_blocked_host("10.0.0.1")
        assert _is_blocked_host("192.168.1.1")
        assert not _is_blocked_host("example.com")

    def test_guard_url_blocks_file_scheme(self):
        with pytest.raises(ValueError, match="scheme"):
            _guard_url("file:///etc/passwd")

    def test_guard_url_blocks_internal_ip(self):
        with pytest.raises(ValueError, match="host"):
            _guard_url("http://127.0.0.1/admin")

    def test_guard_url_allows_external(self):
        _guard_url("https://example.com/path")
