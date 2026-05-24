"""Bare terminal tool — execute shell commands. No allowlist/guard."""
import shlex
import subprocess
from ..registry import registry


def sys_terminal(command: str, timeout: int = 30) -> str:
    """Execute a shell command. No restrictions — use responsibly."""
    try:
        args = shlex.split(command)
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except Exception:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
    output = result.stdout + result.stderr
    return (output[:5000] + "\n... (truncated)" if len(output) > 5000 else output) or "(no output)"


registry.register(
    name="sys_terminal",
    description="Execute a shell command. No allowlist — use responsibly.",
    parameters={
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
            "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30}
        },
        "required": ["command"]
    },
    handler=sys_terminal,
    tags=["system", "shell"],
    category="system"
)
