"""Subagent orchestration — OpenClaw-style spawn, registry, depth, concurrency, announce.

Core patterns preserved from OpenClaw:
  1. SPAWN      — fork conversation context, delegate task to child agent
  2. REGISTRY   — track all subagent runs (lifecycle, status, results)
  3. DEPTH      — reject recursive spawn beyond max depth (default 3)
  4. CONCURRENCY — max N children per parent (default 5)
  5. ANNOUNCE   — subagent completion stored in registry; parent polls

Agent context tracking uses contextvars so subagent tool handlers always see
the correct parent agent, even in nested spawn chains.
"""

import contextvars
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any

# Thread-local agent reference for subagent tool handlers
_agent_ctx: contextvars.ContextVar = contextvars.ContextVar("agent", default=None)


def get_current_agent():
    """Get the agent bound to the current thread/context."""
    return _agent_ctx.get()


def set_current_agent(agent):
    """Bind an agent to the current context. Returns a token for reset."""
    return _agent_ctx.set(agent)


def reset_current_agent(token):
    """Reset the agent context using a token from set_current_agent."""
    _agent_ctx.reset(token)


@dataclass
class SubagentRun:
    """A single subagent execution tracked by the registry."""
    id: str
    parent_id: str
    task: str
    model: str
    depth: int
    status: str  # "pending" | "running" | "completed" | "failed"
    result: Optional[str] = None
    error: Optional[str] = None
    started_at: float = 0.0
    finished_at: Optional[float] = None
    # Internal: thread handle (not serializable)
    _thread: Optional[threading.Thread] = field(default=None, repr=False)


class SubagentRegistry:
    """Thread-safe registry for all subagent runs.

    Enforces:
      - max_depth:  prevent infinite recursive spawn (default 3)
      - max_children: cap concurrent children per parent (default 5)
    """

    def __init__(self, max_depth: int = 3, max_children: int = 5):
        self._runs: Dict[str, SubagentRun] = {}
        self._lock = threading.Lock()
        self.max_depth = max_depth
        self.max_children = max_children

    # ── spawn gate ──────────────────────────────────────────────

    def can_spawn(self, parent_id: str, requested_depth: int) -> tuple:
        """Check spawn policies. Returns (allowed: bool, reason: str)."""
        with self._lock:
            if requested_depth > self.max_depth:
                return False, (
                    f"Max spawn depth ({self.max_depth}) exceeded. "
                    f"Requested depth {requested_depth}. "
                    f"Subagents can spawn at most {self.max_depth} levels deep."
                )
            active = sum(
                1 for r in self._runs.values()
                if r.parent_id == parent_id and r.status in ("pending", "running")
            )
            if active >= self.max_children:
                return False, (
                    f"Max concurrent children ({self.max_children}) reached for "
                    f"parent '{parent_id}'. Wait for existing subagents to complete."
                )
            return True, ""

    # ── lifecycle ──────────────────────────────────────────────

    def register(self, run: SubagentRun):
        with self._lock:
            self._runs[run.id] = run

    def update(self, run_id: str, *,
               status: Optional[str] = None,
               result: Optional[str] = None,
               error: Optional[str] = None):
        with self._lock:
            r = self._runs.get(run_id)
            if r is None:
                return
            if status is not None:
                r.status = status
            if result is not None:
                r.result = result
            if error is not None:
                r.error = error
            if status in ("completed", "failed"):
                r.finished_at = time.time()

    # ── queries ───────────────────────────────────────────────

    def get(self, run_id: str) -> Optional[SubagentRun]:
        with self._lock:
            return self._runs.get(run_id)

    def list_runs(self, parent_id: Optional[str] = None) -> List[dict]:
        """Return all runs (or filtered by parent), newest first, as dicts."""
        with self._lock:
            runs = list(self._runs.values())
            if parent_id:
                runs = [r for r in runs if r.parent_id == parent_id]
            runs.sort(key=lambda r: r.started_at, reverse=True)
            return [_run_to_dict(r) for r in runs]

    def count_active(self, parent_id: Optional[str] = None) -> int:
        with self._lock:
            runs = self._runs.values()
            if parent_id:
                runs = [r for r in runs if r.parent_id == parent_id]
            return sum(1 for r in runs if r.status in ("pending", "running"))

    def summary(self) -> str:
        """Human-readable summary of all runs."""
        with self._lock:
            total = len(self._runs)
            active = sum(1 for r in self._runs.values() if r.status in ("pending", "running"))
            done = sum(1 for r in self._runs.values() if r.status == "completed")
            failed = sum(1 for r in self._runs.values() if r.status == "failed")
            return f"{total} total, {active} active, {done} completed, {failed} failed"


# ── module-level singleton ───────────────────────────────────────────

_registry = SubagentRegistry()


def get_registry() -> SubagentRegistry:
    return _registry


def _run_to_dict(r: SubagentRun) -> dict:
    """Serialize a SubagentRun for tool output (no thread handle)."""
    d = {
        "id": r.id,
        "parent_id": r.parent_id,
        "task": r.task[:200],
        "model": r.model,
        "depth": r.depth,
        "status": r.status,
        "started_at": r.started_at,
    }
    if r.result:
        d["result"] = r.result[:500]
    if r.error:
        d["error"] = r.error
    if r.finished_at:
        d["finished_at"] = r.finished_at
        d["elapsed_s"] = round(r.finished_at - r.started_at, 1)
    return d


# ── spawn runner (called in a thread) ─────────────────────────────

def _run_subagent(
    run_id: str,
    agent_factory: Callable[[], Any],
    task: str,
    parent_messages: List[dict],
    context_mode: str,
    model: str,
):
    """Execute a subagent in a thread. Updates registry on completion."""
    reg = get_registry()
    reg.update(run_id, status="running")

    try:
        agent = agent_factory()

        # Bind this agent as the current context for any nested spawns
        token = set_current_agent(agent)
        try:
            # Build subagent messages
            if context_mode == "full":
                messages = list(parent_messages)
            elif context_mode == "compact":
                # Compact: summarize parent context briefly
                summary = _compact_context(parent_messages, max_chars=1500)
                messages = [{"role": "user", "content": summary}]
            else:  # "none"
                messages = []

            messages.append({"role": "user", "content": task})

            # Override system prompt for subagent role
            original_prompt = agent.system_prompt
            agent.system_prompt = (
                f"You are a subagent. Your task: {task}\n\n"
                f"{original_prompt}"
            )

            result = agent.run(messages)
            reg.update(run_id, status="completed", result=result)
        finally:
            reset_current_agent(token)

    except Exception as e:
        reg.update(run_id, status="failed", error=str(e))


def _compact_context(messages: List[dict], max_chars: int = 1500) -> str:
    """Build a compact summary of conversation context for subagent."""
    parts = ["[Subagent context — summary of parent conversation]\n"]
    chars = 0
    for m in reversed(messages):  # newest first
        role = m.get("role", "?")
        content = m.get("content", "")
        if not content:
            continue
        snippet = content[:300]
        line = f"[{role}] {snippet}"
        if chars + len(line) > max_chars:
            parts.append("... (earlier context truncated)")
            break
        parts.append(line)
        chars += len(line) + 1
    return "\n".join(reversed(parts))


# ── spawn entry point (called by sessions_spawn tool) ──────────────────

def spawn_subagent(
    *,
    task: str,
    agent_factory: Callable[[], Any],
    parent_id: str,
    parent_messages: List[dict],
    depth: int = 1,
    model: str = "",
    context_mode: str = "compact",
) -> dict:
    """Spawn a subagent. Returns {id, depth, status, ...}.

    Args:
        task: The task description for the subagent.
        agent_factory: Callable that creates a fresh AIAgent instance.
        parent_id: ID of the parent agent session.
        parent_messages: Parent's conversation history.
        depth: Current spawn depth (1 = direct child of root).
        model: Override model. Empty = use parent's model.
        context_mode: "compact" | "full" | "none".
    """
    reg = get_registry()
    allowed, reason = reg.can_spawn(parent_id, depth)
    if not allowed:
        return {"error": reason, "status": "rejected"}

    run_id = str(uuid.uuid4())[:8]
    run = SubagentRun(
        id=run_id,
        parent_id=parent_id,
        task=task,
        model=model or "(inherited)",
        depth=depth,
        status="pending",
        started_at=time.time(),
    )
    reg.register(run)

    # Run in background thread
    t = threading.Thread(
        target=_run_subagent,
        args=(run_id, agent_factory, task, parent_messages, context_mode, model),
        daemon=True,
    )
    run._thread = t
    t.start()

    return {
        "id": run_id,
        "depth": depth,
        "status": "spawned",
        "message": f"Subagent '{run_id}' spawned at depth {depth}. Use subagents_status('{run_id}') to check progress.",
    }
