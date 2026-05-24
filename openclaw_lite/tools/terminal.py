from typing import Union

import fnmatch
import re
import shlex
import subprocess
from ..registry import registry
ALLOWLIST = [
    "cat*", "head*", "tail*", "less*", "more*",
    "ls*", "ll*", "pwd", "id", "uname*", "whoami",
    "echo*", "printf*", "which*", "whereis*", "stat*", "file*",
    "wc*", "ps*", "top*", "df*", "du*", "free", "uptime",
    "date", "cal", "hostname",
    "grep*", "find*", "locate*",
    "git status*", "git log*", "git diff*", "git show*", "git branch*",
    "git remote*", "git config --list", "git --version",
    "python --version", "python3 --version", "pip list*", "pip3 list*",
    "python -m pytest --collect-only*",
]

# ── Dangerous substrings: presence triggers mandatory confirmation ──
DANGEROUS = [
    "rm -rf", "rm -fr", "rm -r /", "rmdir /",
    "sudo", "su -", "doas",
    "chmod -R", "chown -R", "chmod 777",
    "mkfs", "mkswap", "swapon",
    "dd if=", "dd of=",
    "> /dev", "< /dev", "/dev/sd", "/dev/hd", "/dev/nvme",
    "curl *|*sh", "wget *|*sh", "curl *|*bash", "wget *|*bash",
    ":(){ :|:& };:",  # fork bomb
    "eval(", "exec(", "__import__('os').system",
]

# Shell metacharacters that break simple allowlist matching
_SHELL_META_RE = re.compile(r'[;&|<>$`\(\)\{\}]')


def _matches_allowlist(command: str) -> bool:
    """True if command matches allowlist AND contains no shell metacharacters."""
    if _SHELL_META_RE.search(command):
        return False
    for pattern in ALLOWLIST:
        if fnmatch.fnmatch(command, pattern):
            return True
    return False


def _is_dangerous(command: str) -> bool:
    """True if command contains any dangerous substring."""
    lowered = command.lower()
    for d in DANGEROUS:
        # fnmatch for patterns with wildcards, substring match for literals
        if "*" in d or "?" in d:
            if fnmatch.fnmatch(lowered, d.lower()):
                return True
        elif d.lower() in lowered:
            return True
    return False


def _run_command(command: Union[str, list], timeout: int, shell: bool) -> str:
    """Execute command and return trimmed output."""
    result = subprocess.run(
        command, shell=shell, capture_output=True,
        text=True, timeout=timeout
    )
    output = result.stdout + result.stderr
    return (output[:5000] + "\n... (truncated)" if len(output) > 5000 else output) or "(no output)"


def sys_terminal(command: str, timeout: int = 30, require_confirmation: bool = True) -> str:
    """Execute a shell command in the workspace.

    Security model (Option C):
      1. Allowlist  — common read-only/low-risk commands execute immediately.
      2. Dangerous  — contains dangerous substrings → mandatory confirmation.
      3. Other      — unrecognized commands → confirmation required.

    Any command with shell metacharacters (; && || | $() < > ` { }) bypasses
    the allowlist and falls into category 2 or 3.
    """
    if _matches_allowlist(command):
        # Fast path: no confirmation needed, use shell=False for safety
        try:
            args = shlex.split(command)
            return _run_command(args, timeout, shell=False)
        except Exception:
            # Fallback to shell=True if shlex.split fails
            return _run_command(command, timeout, shell=True)
    elif _is_dangerous(command):
        if not require_confirmation:
            return f"Blocked dangerous command (require_confirmation=False): {command}"
        confirm = input(f"⚠️ Dangerous command: {command}\nExecute? [y/N]: ")
        if confirm.lower() != "y":
            return "Cancelled by user."
    else:
        if not require_confirmation:
            return f"Blocked unrecognized command (require_confirmation=False): {command}"
        confirm = input(f"⚠️ Unrecognized command: {command}\nExecute? [y/N]: ")
        if confirm.lower() != "y":
            return "Cancelled by user."

    # Dangerous / unrecognized commands still use shell=True for compatibility
    return _run_command(command, timeout, shell=True)


registry.register(
    name="sys_terminal",
    description=(
        "Execute a shell command in the workspace. "
        "Common read-only commands (ls, cat, grep, git status, etc.) run immediately. "
        "Unrecognized or potentially dangerous commands require user confirmation. "
        "Set require_confirmation=false only when running in an automated, sandboxed context."
    ),
    parameters={
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
            "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
            "require_confirmation": {
                "type": "boolean",
                "description": "If false, unrecognized/dangerous commands are blocked instead of prompting",
                "default": True
            }
        },
        "required": ["command"]
    },
    handler=sys_terminal,
    tags=["system", "shell", "execute"],
    category="system"
)
