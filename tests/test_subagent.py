"""Tests for subagent.py — SubagentRegistry and spawn orchestration."""
import time
from unittest.mock import MagicMock, patch

import pytest

from openclaw_lite.subagent import (
    SubagentRegistry,
    SubagentRun,
    spawn_subagent,
    _compact_context,
    _run_to_dict,
    get_registry,
)


class TestSubagentRegistry:
    def test_can_spawn_depth_limit(self):
        reg = SubagentRegistry(max_depth=3)
        assert reg.can_spawn("p1", 1)[0] is True
        assert reg.can_spawn("p1", 3)[0] is True
        assert reg.can_spawn("p1", 4)[0] is False

    def test_can_spawn_concurrency_limit(self):
        reg = SubagentRegistry(max_depth=3, max_children=2)
        reg.register(SubagentRun(id="r1", parent_id="p1", task="t", model="m", depth=1, status="running", started_at=time.time()))
        reg.register(SubagentRun(id="r2", parent_id="p1", task="t", model="m", depth=1, status="running", started_at=time.time()))
        allowed, reason = reg.can_spawn("p1", 1)
        assert allowed is False
        assert "concurrent" in reason.lower() or "children" in reason.lower()

    def test_can_spawn_ignores_completed(self):
        reg = SubagentRegistry(max_depth=3, max_children=1)
        reg.register(SubagentRun(id="r1", parent_id="p1", task="t", model="m", depth=1, status="completed", started_at=time.time()))
        assert reg.can_spawn("p1", 1)[0] is True

    def test_register_and_get(self):
        reg = SubagentRegistry()
        run = SubagentRun(id="abc", parent_id="p", task="test", model="m", depth=1, status="pending", started_at=1.0)
        reg.register(run)
        assert reg.get("abc") == run
        assert reg.get("missing") is None

    def test_update_status_and_result(self):
        reg = SubagentRegistry()
        run = SubagentRun(id="abc", parent_id="p", task="t", model="m", depth=1, status="pending", started_at=time.time())
        reg.register(run)
        reg.update("abc", status="completed", result="done")
        fetched = reg.get("abc")
        assert fetched.status == "completed"
        assert fetched.result == "done"
        assert fetched.finished_at is not None

    def test_update_missing_run_is_noop(self):
        reg = SubagentRegistry()
        reg.update("missing", status="completed")  # should not raise

    def test_list_runs(self):
        reg = SubagentRegistry()
        reg.register(SubagentRun(id="a", parent_id="p", task="t1", model="m", depth=1, status="completed", started_at=1.0))
        reg.register(SubagentRun(id="b", parent_id="p", task="t2", model="m", depth=1, status="running", started_at=2.0))
        reg.register(SubagentRun(id="c", parent_id="other", task="t3", model="m", depth=1, status="pending", started_at=3.0))

        all_runs = reg.list_runs()
        assert len(all_runs) == 3

        p_runs = reg.list_runs(parent_id="p")
        assert len(p_runs) == 2
        ids = {r["id"] for r in p_runs}
        assert ids == {"a", "b"}

    def test_count_active(self):
        reg = SubagentRegistry()
        reg.register(SubagentRun(id="a", parent_id="p", task="t", model="m", depth=1, status="running", started_at=1.0))
        reg.register(SubagentRun(id="b", parent_id="p", task="t", model="m", depth=1, status="completed", started_at=2.0))
        assert reg.count_active("p") == 1
        assert reg.count_active() == 1

    def test_summary(self):
        reg = SubagentRegistry()
        reg.register(SubagentRun(id="a", parent_id="p", task="t", model="m", depth=1, status="running", started_at=1.0))
        reg.register(SubagentRun(id="b", parent_id="p", task="t", model="m", depth=1, status="completed", started_at=2.0))
        reg.register(SubagentRun(id="c", parent_id="p", task="t", model="m", depth=1, status="failed", started_at=3.0))
        s = reg.summary()
        assert "3 total" in s
        assert "1 active" in s
        assert "1 completed" in s
        assert "1 failed" in s


class TestRunToDict:
    def test_serialization(self):
        run = SubagentRun(id="abc", parent_id="p", task="hello world", model="m", depth=2, status="completed", started_at=1.0, finished_at=3.0, result="ok")
        d = _run_to_dict(run)
        assert d["id"] == "abc"
        assert d["depth"] == 2
        assert d["status"] == "completed"
        assert d["result"] == "ok"
        assert d["elapsed_s"] == 2.0
        assert "_thread" not in d


class TestCompactContext:
    def test_full_mode(self):
        msgs = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        ctx = _compact_context(msgs, max_chars=500)
        assert "Subagent context" in ctx
        assert "assistant" in ctx

    def test_truncation(self):
        msgs = [{"role": "user", "content": "x" * 1000} for _ in range(10)]
        ctx = _compact_context(msgs, max_chars=500)
        assert "truncated" in ctx


class TestSpawnSubagent:
    def test_spawn_success(self):
        reg = SubagentRegistry()
        with patch("openclaw_lite.subagent.get_registry", return_value=reg):
            mock_agent = MagicMock()
            mock_agent.run.return_value = "done"
            result = spawn_subagent(
                task="test task",
                agent_factory=lambda: mock_agent,
                parent_id="parent1",
                parent_messages=[],
                depth=1,
            )
        assert "id" in result
        assert result["depth"] == 1
        assert result["status"] == "spawned"

    def test_spawn_rejected_depth(self):
        reg = SubagentRegistry(max_depth=2)
        with patch("openclaw_lite.subagent.get_registry", return_value=reg):
            result = spawn_subagent(
                task="test",
                agent_factory=lambda: MagicMock(),
                parent_id="p",
                parent_messages=[],
                depth=3,
            )
        assert "error" in result
        assert result["status"] == "rejected"

    def test_spawn_rejected_concurrency(self):
        reg = SubagentRegistry(max_depth=3, max_children=1)
        reg.register(SubagentRun(id="x", parent_id="p", task="t", model="m", depth=1, status="running", started_at=time.time()))
        with patch("openclaw_lite.subagent.get_registry", return_value=reg):
            result = spawn_subagent(
                task="test",
                agent_factory=lambda: MagicMock(),
                parent_id="p",
                parent_messages=[],
                depth=1,
            )
        assert "error" in result
        assert result["status"] == "rejected"

    def test_run_subagent_completes(self):
        """Test the thread runner directly via a short-lived spawn."""
        reg = SubagentRegistry()
        mock_agent = MagicMock()
        mock_agent.run.return_value = "result from agent"
        mock_agent.system_prompt = "base"

        with patch("openclaw_lite.subagent.get_registry", return_value=reg):
            result = spawn_subagent(
                task="do work",
                agent_factory=lambda: mock_agent,
                parent_id="p",
                parent_messages=[{"role": "user", "content": "hi"}],
                depth=1,
                context_mode="none",
            )
        run_id = result["id"]
        # Poll briefly for completion
        for _ in range(50):
            if reg.get(run_id).status in ("completed", "failed"):
                break
            time.sleep(0.01)
        run = reg.get(run_id)
        assert run.status == "completed"
        assert run.result == "result from agent"

    def test_run_subagent_failure(self):
        reg = SubagentRegistry()
        mock_agent = MagicMock()
        mock_agent.run.side_effect = ValueError("boom")
        mock_agent.system_prompt = "base"

        with patch("openclaw_lite.subagent.get_registry", return_value=reg):
            result = spawn_subagent(
                task="fail",
                agent_factory=lambda: mock_agent,
                parent_id="p",
                parent_messages=[],
                depth=1,
                context_mode="none",
            )
        run_id = result["id"]
        for _ in range(50):
            if reg.get(run_id).status in ("completed", "failed"):
                break
            time.sleep(0.01)
        run = reg.get(run_id)
        assert run.status == "failed"
        assert "boom" in run.error
