# 🦞 OpenClaw Lite

Minimal, single-user agent framework with subagent orchestration + Skill/Deck system.

**10 files, ~1,400 lines of Python. 2 pip dependencies. 0 config files. 0 guards.**

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

Three tools:

- `sessions_spawn(task, model?, context_mode?)` — delegate a task to a background subagent
- `subagents_list()` — check status of all subagents
- `subagents_status(run_id)` — get detailed result

Policies: max 3 spawn depth, max 5 concurrent children per parent.

## Skill + Deck

Add `.md` files to `skills/`:

```yaml
---
name: code-review
trigger: review, PR, diff
tools:
  - fs_read_file
  - sys_terminal
---
```

On each turn, hermes-lite matches skills against your input, collects their tools, and builds a Deck. The agent can only use tools in the Deck.

## Built-in Tools

| Category | Tools |
|----------|-------|
| filesystem | `fs_read_file`, `fs_write_file`, `fs_search_files` |
| system | `sys_terminal` |
| network | `net_web_search`, `net_web_extract` |
| subagent | `sessions_spawn`, `subagents_list`, `subagents_status` |

**Bare tools — no workspace guard, no allowlist, no SSRF guard.** Assumes trusted single-user environment.

## Config

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENCLAW_API_KEY` | *(required)* | API key |
| `OPENCLAW_PROVIDER` | `anthropic` | `anthropic` or `openai` |
| `OPENCLAW_MODEL` | `claude-sonnet-4-20250514` | Model name |

## Architecture

```
openclaw_lite/
├── agent.py        Agent loop + subagent tool registration
├── subagent.py     Spawn, Registry, Depth, Concurrency, Announce
├── skills.py       Skill loader (YAML frontmatter + trigger matching)
├── deck.py         Immutable tool boundary (Deck)
├── registry.py     Tool registry (thread-safe, LRU-cached)
├── main.py         CLI
├── tools/
│   ├── file.py     Read, write, search files
│   ├── terminal.py Shell execution
│   └── web.py      Web search + fetch
└── skills/         Add your skill .md files here
```

## License

MIT
