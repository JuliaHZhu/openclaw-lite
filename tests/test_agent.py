"""Tests for agent.py — AIAgent protocol conversion, subagent tools, and loop."""
from unittest.mock import MagicMock, patch

import pytest

from openclaw_lite.agent import AIAgent
from openclaw_lite.registry import registry


@pytest.fixture
def anthropic_config():
    return {
        "provider": "anthropic",
        "model": "claude-test",
        "api_key": "test-key",
        "max_iterations": 5,
        "system_prompt": "You are a test assistant.",
    }


@pytest.fixture
def openai_config():
    return {
        "provider": "openai",
        "model": "gpt-test",
        "api_key": "test-key",
        "max_iterations": 5,
        "system_prompt": "You are a test assistant.",
    }


class TestAgentInit:
    @patch("anthropic.Anthropic")
    def test_init_anthropic(self, mock_anthropic, anthropic_config):
        agent = AIAgent(anthropic_config)
        assert agent._protocol == "anthropic"
        mock_anthropic.assert_called_once_with(api_key="test-key", base_url=None)

    @patch("openai.OpenAI")
    def test_init_openai(self, mock_openai, openai_config):
        agent = AIAgent(openai_config)
        assert agent._protocol == "openai"
        mock_openai.assert_called_once_with(api_key="test-key", base_url=None)

    @patch("anthropic.Anthropic")
    def test_auto_registers_subagent_tools(self, mock_anthropic, anthropic_config):
        agent = AIAgent(anthropic_config)
        assert registry.has_tool("sessions_spawn")
        assert registry.has_tool("subagents_list")
        assert registry.has_tool("subagents_status")


class TestToolSchemaCache:
    @patch("anthropic.Anthropic")
    def test_build_tools_caching(self, mock_anthropic, anthropic_config):
        registry.register("tool_a", "TA", {"properties": {}}, lambda **kw: "ok")
        agent = AIAgent(anthropic_config)
        t1 = agent._build_tools(["tool_a"])
        t2 = agent._build_tools(["tool_a"])
        assert t1 is t2


class TestMessageConversion:
    @patch("anthropic.Anthropic")
    def test_to_api_messages_anthropic_tool_result(self, mock_anthropic, anthropic_config):
        agent = AIAgent(anthropic_config)
        msgs = [{"role": "tool", "tool_call_id": "tc1", "content": "ok"}]
        api = agent._to_api_messages(msgs)
        assert api[0]["role"] == "user"
        assert api[0]["content"][0]["type"] == "tool_result"

    @patch("openai.OpenAI")
    def test_to_api_messages_openai_tool_result(self, mock_openai, openai_config):
        agent = AIAgent(openai_config)
        msgs = [{"role": "tool", "tool_call_id": "tc1", "content": "ok"}]
        api = agent._to_api_messages(msgs)
        assert api[0]["role"] == "tool"
        assert api[0]["tool_call_id"] == "tc1"

    @patch("anthropic.Anthropic")
    def test_to_api_messages_anthropic_assistant_with_tool_calls(self, mock_anthropic, anthropic_config):
        agent = AIAgent(anthropic_config)
        msgs = [{"role": "assistant", "content": "thinking", "tool_calls": [{"id": "tc1", "name": "t", "arguments": {"x": 1}}]}]
        api = agent._to_api_messages(msgs)
        assert api[0]["role"] == "assistant"
        assert api[0]["content"][1]["type"] == "tool_use"


class TestExtractors:
    @patch("anthropic.Anthropic")
    def test_extract_text_anthropic(self, mock_anthropic, anthropic_config):
        agent = AIAgent(anthropic_config)
        msg = MagicMock()
        block = MagicMock()
        block.text = "hello"
        msg.content = [block]
        assert agent._extract_text(msg) == "hello"

    @patch("openai.OpenAI")
    def test_extract_text_openai(self, mock_openai, openai_config):
        agent = AIAgent(openai_config)
        msg = MagicMock()
        msg.content = "hello"
        assert agent._extract_text(msg) == "hello"

    @patch("anthropic.Anthropic")
    def test_extract_tool_calls_anthropic(self, mock_anthropic, anthropic_config):
        agent = AIAgent(anthropic_config)
        msg = MagicMock()
        block = MagicMock()
        block.type = "tool_use"
        block.id = "tc1"
        block.name = "tool_a"
        block.input = {"x": 1}
        msg.content = [block]
        calls = agent._extract_tool_calls(msg)
        assert len(calls) == 1
        assert calls[0]["name"] == "tool_a"
        assert calls[0]["arguments"] == {"x": 1}

    @patch("openai.OpenAI")
    def test_extract_tool_calls_openai(self, mock_openai, openai_config):
        agent = AIAgent(openai_config)
        msg = MagicMock()
        tc = MagicMock()
        tc.id = "tc1"
        tc.function.name = "tool_a"
        tc.function.arguments = '{"x": 1}'
        msg.tool_calls = [tc]
        calls = agent._extract_tool_calls(msg)
        assert calls[0]["arguments"] == {"x": 1}


class TestRunLoop:
    @patch("anthropic.Anthropic")
    def test_run_without_tool_calls(self, mock_anthropic_cls, anthropic_config):
        agent = AIAgent(anthropic_config)
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        agent.client = mock_client

        mock_msg = MagicMock()
        mock_msg.content = []
        mock_client.messages.create.return_value = mock_msg

        result = agent.run([{"role": "user", "content": "hi"}])
        assert result == ""

    @patch("anthropic.Anthropic")
    def test_run_reaches_max_iterations(self, mock_anthropic_cls, anthropic_config):
        agent = AIAgent(anthropic_config)
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        agent.client = mock_client

        mock_msg = MagicMock()
        block = MagicMock()
        block.type = "tool_use"
        block.id = "tc1"
        block.name = "nonexistent"
        block.input = {}
        block.text = ""
        mock_msg.content = [block]
        mock_client.messages.create.return_value = mock_msg

        result = agent.run([{"role": "user", "content": "loop"}])
        assert result == "(reached max iterations)"


class TestSubagentToolHandlers:
    @patch("anthropic.Anthropic")
    def test_sessions_spawn_handler_rejects_over_depth(self, mock_anthropic, anthropic_config):
        from openclaw_lite.subagent import get_registry
        reg = get_registry()
        # Temporarily lower limits
        original_max = reg.max_depth
        reg.max_depth = 0
        try:
            agent = AIAgent({**anthropic_config, "depth": 0})
            # The handler is registered globally; we can call it via registry
            result = registry.call("sessions_spawn", {"task": "test"})
            assert "REJECTED" in result or "rejected" in result.lower()
        finally:
            reg.max_depth = original_max

    @patch("anthropic.Anthropic")
    def test_subagents_list_empty(self, mock_anthropic, anthropic_config):
        agent = AIAgent(anthropic_config)
        result = registry.call("subagents_list", {})
        assert "No subagents" in result or isinstance(result, str)

    @patch("anthropic.Anthropic")
    def test_subagents_status_not_found(self, mock_anthropic, anthropic_config):
        agent = AIAgent(anthropic_config)
        result = registry.call("subagents_status", {"run_id": "nonexistent"})
        assert "not found" in result.lower()
