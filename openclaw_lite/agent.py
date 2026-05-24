"""AI Agent — dual-protocol (Anthropic/OpenAI) with subagent orchestration.

Extends the hermes-lite agent loop with three subagent tools:
  sessions_spawn   — delegate a task to a background subagent
  subagents_list   — list all subagent runs
  subagents_status — get detailed status of a subagent run
"""

import json
import uuid
from typing import List, Dict, Optional

from .registry import registry
from .subagent import spawn_subagent, get_registry


class AIAgent:
    def __init__(self, config: dict):
        self.config = config
        self.model = config.get("model", "claude-sonnet-4-20250514")
        self.max_iterations = config.get("max_iterations", 30)
        self.system_prompt = config.get(
            "system_prompt", "You are a helpful assistant with tool access."
        )
        self.enabled_tools = config.get("tools", [])
        self._tool_schema_cache: dict = {}
        # Subagent context
        self.session_id = config.get("session_id", str(uuid.uuid4())[:8])
        self.depth = config.get("depth", 0)  # 0 = root agent
        self._messages: List[dict] = []  # track conversation for spawn context
        self._auto_register_subagent_tools()
        self._init_client()

    def _auto_register_subagent_tools(self):
        """Register subagent orchestration tools if not already registered."""
        # Only register once (check by name)
        if not registry.has_tool("sessions_spawn"):
            self._register_subagent_tools()

    def _register_subagent_tools(self):
        """Register the three subagent tools into the global registry."""
        agent_ref = self  # capture for closure

        def _sessions_spawn(
            task: str,
            model: Optional[str] = None,
            context_mode: str = "compact",
        ) -> str:
            """Spawn a subagent to work on a task in the background.

            Use this to delegate independent subtasks. The subagent runs in a
            separate thread with its own conversation context.

            Args:
                task: The task description for the subagent.
                model: Override model (default: inherit from parent).
                context_mode: How much parent context to give the subagent.
                    "compact" (default) — brief summary of parent conversation
                    "full" — complete parent conversation history
                    "none" — only the task itself
            """
            reg = get_registry()
            result = spawn_subagent(
                task=task,
                agent_factory=lambda: AIAgent(agent_ref.config),
                parent_id=agent_ref.session_id,
                parent_messages=agent_ref._messages,
                depth=agent_ref.depth + 1,
                model=model or "",
                context_mode=context_mode,
            )
            if "error" in result:
                return f"SPAWN REJECTED: {result['error']}"
            return (
                f"Subagent spawned: {result['id']} (depth {result['depth']})\n"
                f"Track with: subagents_status('{result['id']}') or subagents_list()"
            )

        def _subagents_list() -> str:
            """List all subagent runs and their statuses.

            Returns a table of subagents with id, status, task, and timing.
            """
            reg = get_registry()
            runs = reg.list_runs(parent_id=agent_ref.session_id)
            if not runs:
                return "No subagents spawned yet."
            lines = ["Subagents:"]
            for r in runs:
                elapsed = ""
                if r.get("elapsed_s"):
                    elapsed = f" ({r['elapsed_s']}s)"
                status_icon = {
                    "pending": "⏳", "running": "🔄",
                    "completed": "✅", "failed": "❌",
                }.get(r["status"], "❓")
                lines.append(
                    f"  {status_icon} {r['id']} [{r['status']}]{elapsed} "
                    f"depth={r['depth']} — {r['task'][:80]}"
                )
            return "\n".join(lines)

        def _subagents_status(run_id: str) -> str:
            """Get detailed status and result of a specific subagent run."""
            reg = get_registry()
            run = reg.get(run_id)
            if run is None:
                return f"Subagent '{run_id}' not found."
            d = {
                "id": run.id,
                "status": run.status,
                "task": run.task,
                "depth": run.depth,
                "model": run.model,
                "started_at": run.started_at,
            }
            if run.result:
                d["result"] = run.result
            if run.error:
                d["error"] = run.error
            if run.finished_at:
                d["elapsed_s"] = round(run.finished_at - run.started_at, 1)
            return json.dumps(d, indent=2, ensure_ascii=False)

        registry.register(
            name="sessions_spawn",
            description=(
                "Spawn a subagent to work on a task in the background. "
                "The subagent runs in its own thread with isolated context. "
                "Use for parallel independent subtasks. "
                "Max 3 depth levels, max 5 concurrent children."
            ),
            parameters={
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Task description for the subagent. Be specific."
                    },
                    "model": {
                        "type": "string",
                        "description": "Override model (default: inherit from parent)"
                    },
                    "context_mode": {
                        "type": "string",
                        "enum": ["compact", "full", "none"],
                        "description": "How much parent context to give subagent",
                        "default": "compact"
                    },
                },
                "required": ["task"]
            },
            handler=_sessions_spawn,
            tags=["subagent", "spawn", "orchestration"],
            category="subagent"
        )

        registry.register(
            name="subagents_list",
            description=(
                "List all subagent runs spawned by this agent. "
                "Shows id, status, task summary, and timing for each."
            ),
            parameters={
                "properties": {},
                "required": []
            },
            handler=_subagents_list,
            tags=["subagent", "list", "orchestration"],
            category="subagent"
        )

        registry.register(
            name="subagents_status",
            description=(
                "Get detailed status and result of a specific subagent run. "
                "Use this to check if a spawned subagent has completed and retrieve its output."
            ),
            parameters={
                "properties": {
                    "run_id": {
                        "type": "string",
                        "description": "The subagent run ID (from sessions_spawn output)"
                    }
                },
                "required": ["run_id"]
            },
            handler=_subagents_status,
            tags=["subagent", "status", "orchestration"],
            category="subagent"
        )

    def _init_client(self):
        provider = self.config.get("provider", "anthropic")
        if provider == "openai":
            from openai import OpenAI
            self.client = OpenAI(
                api_key=self.config["api_key"],
                base_url=self.config.get("base_url")
            )
            self._protocol = "openai"
        else:
            from anthropic import Anthropic
            self.client = Anthropic(
                api_key=self.config["api_key"],
                base_url=self.config.get("base_url")
            )
            self._protocol = "anthropic"

    def _build_tools(self, tool_names=None):
        names = tool_names if tool_names is not None else self.enabled_tools
        if not names:
            return None
        cache_key = (frozenset(names), self._protocol, registry.generation)
        if cache_key in self._tool_schema_cache:
            return self._tool_schema_cache[cache_key]

        schemas = registry.get_schemas(enabled=names)
        if self._protocol == "openai":
            converted = []
            for s in schemas:
                openai_schema = {
                    "name": s["name"],
                    "description": s["description"],
                    "parameters": s.get("input_schema", {"type": "object"})
                }
                converted.append({"type": "function", "function": openai_schema})
            result = converted
        else:
            result = schemas

        self._tool_schema_cache[cache_key] = result
        return result

    def _to_api_messages(self, messages: List[Dict]) -> List[Dict]:
        api_msgs = []
        for m in messages:
            role = m["role"]
            content = m.get("content", "")
            tool_calls = m.get("tool_calls")
            if role == "tool":
                if self._protocol == "anthropic":
                    api_msgs.append({
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": m.get("tool_call_id", ""),
                            "content": content
                        }]
                    })
                else:
                    api_msgs.append({
                        "role": "tool",
                        "tool_call_id": m.get("tool_call_id", ""),
                        "content": content
                    })
            elif role == "assistant" and tool_calls:
                if self._protocol == "anthropic":
                    blocks = []
                    if content:
                        blocks.append({"type": "text", "text": content})
                    for tc in tool_calls:
                        blocks.append({
                            "type": "tool_use",
                            "id": tc.get("id", tc.get("tool_use_id", "")),
                            "name": tc.get("name", tc.get("function", {}).get("name", "")),
                            "input": tc.get("input") or tc.get("function", {}).get("arguments", {}) or tc.get("arguments", {})
                        })
                    api_msgs.append({"role": "assistant", "content": blocks})
                else:
                    api_msgs.append(m)
            else:
                api_msgs.append({"role": role, "content": content})
        return api_msgs

    def _extract_text(self, msg) -> str:
        if self._protocol == "anthropic":
            texts = []
            for block in msg.content:
                if hasattr(block, "text"):
                    texts.append(block.text)
            return "\n".join(texts)
        return msg.content or ""

    def _extract_tool_calls(self, msg) -> List[Dict]:
        calls = []
        if self._protocol == "anthropic":
            for block in msg.content:
                if getattr(block, "type", None) == "tool_use":
                    args = block.input
                    if hasattr(args, "model_dump"):
                        args = args.model_dump()
                    calls.append({
                        "id": block.id,
                        "name": block.name,
                        "arguments": args
                    })
        else:
            for tc in (msg.tool_calls or []):
                calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments)
                })
        return calls

    def run(self, messages: List[Dict], tools: Optional[List[str]] = None) -> str:
        """Run one turn of conversation with tool use loop.

        Args:
            messages: Conversation history.
            tools: Optional list of tool names. If None, uses self.enabled_tools.
        """
        # Track messages for subagent spawn context
        self._messages = messages

        active_tools = self._build_tools(tools)
        api_messages = self._to_api_messages(messages)

        for i in range(self.max_iterations):
            if self._protocol == "anthropic":
                kwargs = {
                    "model": self.model,
                    "max_tokens": 4096,
                    "messages": api_messages,
                    "system": self.system_prompt,
                }
                if active_tools:
                    kwargs["tools"] = active_tools
                response = self.client.messages.create(**kwargs)
                msg = response
            else:
                kwargs = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": self.system_prompt}
                    ] + api_messages,
                }
                if active_tools:
                    kwargs["tools"] = active_tools
                    kwargs["tool_choice"] = "auto"
                response = self.client.chat.completions.create(**kwargs)
                msg = response.choices[0].message

            text = self._extract_text(msg)
            tool_calls = self._extract_tool_calls(msg)

            if not tool_calls:
                return text

            assistant_msg = {
                "role": "assistant", "content": text, "tool_calls": tool_calls
            }
            messages.append(assistant_msg)

            if self._protocol == "anthropic":
                api_msgs = []
                if text:
                    api_msgs.append({"type": "text", "text": text})
                for tc in tool_calls:
                    api_msgs.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["name"],
                        "input": tc["arguments"]
                    })
                api_messages.append({"role": "assistant", "content": api_msgs})
            else:
                api_messages.append({
                    "role": "assistant",
                    "content": text,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["arguments"])
                            }
                        }
                        for tc in tool_calls
                    ]
                })

            for tc in tool_calls:
                result = registry.call(tc["name"], tc["arguments"])
                tool_msg = {
                    "role": "tool", "tool_call_id": tc["id"], "content": result
                }
                messages.append(tool_msg)

                if self._protocol == "anthropic":
                    api_messages.append({
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": tc["id"],
                            "content": result
                        }]
                    })
                else:
                    api_messages.append(tool_msg)

        return "(reached max iterations)"
