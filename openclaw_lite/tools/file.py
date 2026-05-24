"""Bare file tools — read, write, search. No workspace/security guards."""
import fnmatch
import os
import re
from pathlib import Path
from ..registry import registry


def fs_read_file(path: str, offset: int = 1, limit: int = 100) -> str:
    """Read a text file with pagination."""
    try:
        p = Path(path).expanduser()
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[offset - 1:offset - 1 + limit])
    except Exception as e:
        return f"Error: {e}"


def fs_write_file(path: str, content: str) -> str:
    """Write text to a file (creates parent directories)."""
    try:
        p = Path(path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Written {len(content)} chars to {path}"
    except Exception as e:
        return f"Error: {e}"


def fs_search_files(pattern: str, path: str = ".", file_glob: str = "*") -> str:
    """Search file contents with regex."""
    results = []
    search_root = Path(path).expanduser()
    for root, _, files in os.walk(search_root):
        for f in files:
            if not fnmatch.fnmatch(f, file_glob):
                continue
            fp = os.path.join(root, f)
            try:
                content = Path(fp).read_text(encoding="utf-8", errors="replace")
                for i, line in enumerate(content.splitlines(), 1):
                    if re.search(pattern, line):
                        results.append(f"{fp}:{i}: {line.strip()}")
                        if len(results) >= 30:
                            return "\n".join(results) + "\n... (truncated)"
            except Exception:
                pass
    return "\n".join(results) or "No matches"


registry.register(
    name="fs_read_file",
    description="Read a text file with line numbers and pagination.",
    parameters={
        "properties": {
            "path": {"type": "string", "description": "Absolute or relative file path"},
            "offset": {"type": "integer", "description": "Start line (1-indexed)", "default": 1},
            "limit": {"type": "integer", "description": "Max lines to read", "default": 100}
        },
        "required": ["path"]
    },
    handler=fs_read_file,
    tags=["filesystem", "read"],
    category="filesystem"
)

registry.register(
    name="fs_write_file",
    description="Write text to a file. Creates parent directories. Overwrites existing content.",
    parameters={
        "properties": {
            "path": {"type": "string", "description": "Target file path"},
            "content": {"type": "string", "description": "Full text content to write"}
        },
        "required": ["path", "content"]
    },
    handler=fs_write_file,
    tags=["filesystem", "write"],
    category="filesystem"
)

registry.register(
    name="fs_search_files",
    description="Search file contents with regex. Filter by file glob (e.g. '*.py').",
    parameters={
        "properties": {
            "pattern": {"type": "string", "description": "Regex pattern to search"},
            "path": {"type": "string", "description": "Directory to search in", "default": "."},
            "file_glob": {"type": "string", "description": "File glob filter", "default": "*"}
        },
        "required": ["pattern"]
    },
    handler=fs_search_files,
    tags=["filesystem", "search"],
    category="filesystem"
)
