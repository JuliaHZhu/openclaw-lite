# 🦞 OpenClaw Lite

Minimal, single-user agent framework preserving OpenClaw's signature subagent orchestration.

**9 files, ~1,500 lines of Python. 2 pip dependencies. 0 config files. 0 daemons.**

## Install

```bash
pip install git+https://github.com/JuliaHZhu/openclaw-lite.git
# or
git clone https://github.com/JuliaHZhu/openclaw-lite.git
cd openclaw-lite && pip install -e .
```

## Run

```bash
export OPENCLAW_API_KEY=sk-...
openclaw-lite              # interactive session
openclaw-lite -m "hello"   # ping test
```

## Subagent Orchestration

Preserves OpenClaw's five core patterns:

| Pattern | What it does | Default |
|---------|-------------|---------|
| **SPAWN** | Fork context, delegate task to child agent | — |
| **REGISTRY** | Track all subagent runs (lifecycle, status, results) | — |
| **DEPTH** | Prevent infinite recursive spawn | max 3 |
| **CONCURRENCY** | Cap parallel children per parent | max 5 |
| **ANNOUNCE** | Subagent completion stored in registry; parent polls | — |

### Subagent Tools

- `sessions_spawn(task, context_mode='compact')` — delegate a subtask
- `subagents_list()` — list all subagent runs
- `subagents_status(run_id)` — get detailed result

### Example

```
You: Research Rust vs Zig for systems programming. Then compare them on 3 dimensions.

Agent: I'll spawn subagents for parallel research.
  [calls sessions_spawn("Research Rust: ecosystem, safety, performance")]
  [calls sessions_spawn("Research Zig: ecosystem, simplicity, performance")]
  [calls subagents_list() → both running]
  [calls subagents_status("abc123") → Rust research complete]
  [calls subagents_status("def456") → Zig research complete]
  [synthesizes comparison across both results]
```

## Built-in Tools

| Category | Tools |
|----------|-------|
| filesystem | `fs_read_file`, `fs_write_file`, `fs_search_files` |
| system | `sys_terminal` |
| network | `net_web_search`, `net_web_extract` |
| subagent | `sessions_spawn`, `subagents_list`, `subagents_status` |

## Config

All via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENCLAW_API_KEY` | *(required)* | API key |
| `OPENCLAW_PROVIDER` | `anthropic` | `anthropic` or `openai` |
| `OPENCLAW_MODEL` | `claude-sonnet-4-20250514` | Model name |
| `OPENCLAW_BASE_URL` | *(none)* | Custom API base URL |

## Architecture

```
openclaw_lite/
├── agent.py       ~320 lines   Agent loop + subagent tool registration
├── subagent.py    ~240 lines   Spawn, Registry, Depth, Concurrency, Announce
├── registry.py    ~190 lines   Tool registry (thread-safe, LRU-cached)
├── main.py        ~130 lines   CLI entry point
├── tools/
│   ├── file.py    ~160 lines   File operations (workspace-guarded)
│   ├── terminal.py ~130 lines  Shell execution (allowlist + dangerous detection)
│   └── web.py     ~135 lines   Web search/extract (SSRF-guarded)
└── __init__.py
```

## From OpenClaw

This project captures the *spirit* of OpenClaw's subagent mechanism, not its code. OpenClaw's subagent is 2,700+ lines deeply integrated into a multi-tenant gateway. OpenClaw Lite extracts the five core patterns into ~240 lines of standalone Python — suitable for single-user, single-machine use.

## License

MIT
