#!/usr/bin/env python3
"""OpenClaw Lite — minimal agent framework with subagent orchestration.

Usage:
    openclaw-lite              Start interactive session
    openclaw-lite -m "hello"   Quick model ping test
    openclaw-lite -v           Show version

Config via env vars:
    OPENCLAW_API_KEY           API key (required)
    OPENCLAW_PROVIDER          anthropic (default) or openai
    OPENCLAW_MODEL             model name
    OPENCLAW_BASE_URL          optional base URL override
"""

import argparse
import os
import sys

# Auto-register built-in tools on import
from .tools import file, terminal, web  # noqa: F401

from .agent import AIAgent
from .deck import build_deck
from .registry import registry
from .skills import SkillManager
from .subagent import get_registry

VERSION = "0.1.0"


def load_config():
    key = os.environ.get("OPENCLAW_API_KEY")
    if not key:
        return None
    return {
        "provider": os.environ.get("OPENCLAW_PROVIDER", "anthropic"),
        "model": os.environ.get("OPENCLAW_MODEL", "claude-sonnet-4-20250514"),
        "api_key": key,
        "base_url": os.environ.get("OPENCLAW_BASE_URL"),
        "max_iterations": 30,
        "system_prompt": (
            "You are a helpful assistant with tool access, Deck-bound execution, "
            "and subagent orchestration.\n\n"
            "DECK: You can only use tools in your Deck (pre-procured per turn). "
            "If a needed tool is not in the Deck, ask for it or work within limits.\n\n"
            "SUBAGENT TOOLS:\n"
            "- sessions_spawn(task, context_mode='compact'): Delegate a subtask to a\n"
            "  background subagent. Use for parallel independent work.\n"
            "- subagents_list(): Check status of all spawned subagents.\n"
            "- subagents_status(run_id): Get detailed result of a specific subagent.\n\n"
            "Think step by step. For complex multi-step tasks, spawn subagents for\n"
            "independent subtasks and check their results."
        ),
    }


def ping(message):
    config = load_config()
    if not config:
        sys.exit("❌ Set OPENCLAW_API_KEY first.")
    print(f"→ Pinging {config['model']}...")
    agent = AIAgent(config)
    try:
        resp = agent.run([{"role": "user", "content": message}])
        print("← " + resp)
    except Exception as e:
        sys.exit(f"❌ {e}")


def run_session():
    config = load_config()
    if not config:
        sys.exit(
            "❌ Set OPENCLAW_API_KEY env var.\n"
            "  export OPENCLAW_API_KEY=sk-...\n"
            "  export OPENCLAW_MODEL=claude-sonnet-4-20250514  # optional"
        )

    agent = AIAgent(config)
    subreg = get_registry()
    skill_mgr = SkillManager()
    base_prompt = agent.system_prompt

    loaded = skill_mgr.load_all()
    print(f"🦞 OpenClaw Lite v{VERSION} — {config['model']} ({config['provider']})")
    print(f"   {len(loaded)} skill(s), {len(registry.list_tools())} tools | subagent depth≤3, ≤5 concurrent")
    print("   /exit  /tools  /skills  /subagents  /clear  /help")
    print("-" * 50)

    messages = []
    while True:
        try:
            ui = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not ui:
            continue
        if ui.lower() in ("/exit", "exit", "quit"):
            break
        if ui.lower() == "/help":
            print(
                "Commands: /exit, /tools, /skills, /subagents, /clear, /help\n"
                "Subagent tools: sessions_spawn, subagents_list, subagents_status"
            )
            continue
        if ui.lower() == "/tools":
            for cat, names in sorted(registry.list_by_category().items()):
                print(f"  [{cat}] {', '.join(names)}")
            continue
        if ui.lower() == "/skills":
            skills = skill_mgr.list_skills()
            if skills:
                for name, meta in skills.items():
                    t = f"  triggers: {', '.join(meta.get('triggers',[]))}" if meta.get("triggers") else ""
                    tl = f"  tools: {', '.join(meta.get('tools',[]))}" if meta.get("tools") else ""
                    print(f"  • {name}: {meta.get('description','')}{t}{tl}")
            else:
                print("No skills. Add .md files to skills/")
            continue
        if ui.lower() == "/subagents":
            print(subreg.summary())
            runs = subreg.list_runs()
            if runs:
                for r in runs:
                    icon = {"pending": "⏳", "running": "🔄", "completed": "✅", "failed": "❌"}.get(r["status"], "?")
                    print(f"  {icon} {r['id']} [{r['status']}] depth={r['depth']} — {r['task'][:60]}")
            continue
        if ui.lower() == "/clear":
            messages = []
            print("Cleared.")
            continue

        messages.append({"role": "user", "content": ui})
        print("\nAgent: ", end="", flush=True)
        try:
            resp = agent.run(messages)
        except Exception as e:
            resp = f"Error: {e}"

        if resp == "(reached max iterations)":
            print(f"{resp}")
            messages.append({"role": "assistant", "content": resp})
            continue

        print(resp)
        messages.append({"role": "assistant", "content": resp})


def main():
    p = argparse.ArgumentParser(prog="openclaw-lite", add_help=False)
    p.add_argument("-m", "--ping", metavar="MSG")
    p.add_argument("-v", "--version", action="store_true")
    p.add_argument("-h", "--help", action="store_true")
    args = p.parse_args()

    if args.version:
        print(f"openclaw-lite {VERSION}")
    elif args.help:
        print(__doc__)
    elif args.ping:
        ping(args.ping)
    else:
        run_session()


if __name__ == "__main__":
    main()
