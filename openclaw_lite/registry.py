"""Tool registry — with tags, categories, thread safety, and LRU caching."""
import threading
import time
from collections import OrderedDict
from typing import Dict, Callable, List, Optional


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, dict] = {}
        self._lock = threading.RLock()
        self._generation: int = 0
        self._schemas_cache: OrderedDict = OrderedDict()
        self._cache_lock = threading.Lock()
        self._cache_max_size: int = 64
        self._cache_ttl_seconds: float = 30.0

    def _bump_generation(self):
        with self._lock:
            self._generation += 1

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    def register(
        self,
        name: str,
        description: str,
        parameters: dict,
        handler: Callable,
        tags: Optional[List[str]] = None,
        category: Optional[str] = None
    ):
        with self._lock:
            self._tools[name] = {
                "schema": {
                    "name": name,
                    "description": description,
                    "input_schema": {"type": "object", **parameters}
                },
                "handler": handler,
                "tags": set(tags or []),
                "category": category or "",
                "name": name,
                "description": description,
            }
        self._bump_generation()
        with self._cache_lock:
            self._schemas_cache.clear()

    def deregister(self, name: str) -> bool:
        removed = False
        with self._lock:
            if name in self._tools:
                del self._tools[name]
                removed = True
        if removed:
            self._bump_generation()
            with self._cache_lock:
                self._schemas_cache.clear()
        return removed

    def get_schemas(
        self,
        enabled: Optional[List[str]] = None,
        tags: Optional[List[str]] = None
    ) -> List[dict]:
        key_enabled = frozenset(enabled) if enabled else frozenset()
        key_tags = frozenset(tags) if tags else frozenset()
        gen = self.generation
        cache_key = (key_enabled, key_tags, gen)

        now = time.monotonic()
        with self._cache_lock:
            cached = self._schemas_cache.get(cache_key)
            if cached is not None:
                ts, schemas = cached
                if now - ts < self._cache_ttl_seconds:
                    self._schemas_cache.move_to_end(cache_key)
                    return list(schemas)

        with self._lock:
            results = []
            names = set(enabled or [])
            tag_set = set(tags or [])
            for n, info in self._tools.items():
                if enabled and n in names:
                    results.append(info["schema"])
                    continue
                if tags and info["tags"] & tag_set:
                    results.append(info["schema"])
                    continue
                if not enabled and not tags:
                    results.append(info["schema"])

        with self._cache_lock:
            self._schemas_cache[cache_key] = (now, list(results))
            while len(self._schemas_cache) > self._cache_max_size:
                self._schemas_cache.pop(next(iter(self._schemas_cache)))

        return results

    def get_schema(self, name: str) -> Optional[dict]:
        with self._lock:
            entry = self._tools.get(name)
            if entry:
                return dict(entry["schema"])
            return None

    def call(self, name: str, args: dict) -> str:
        with self._lock:
            entry = self._tools.get(name)
        if entry is None:
            return f"Error: tool '{name}' not found"
        try:
            result = entry["handler"](**args)
            return str(result)[:8000]
        except Exception as e:
            return f"Error: {e}"

    def list_tools(self, tags: Optional[List[str]] = None) -> List[str]:
        with self._lock:
            if not tags:
                return list(self._tools.keys())
            tag_set = set(tags)
            return [n for n, info in self._tools.items() if info["tags"] & tag_set]

    def list_by_category(self) -> Dict[str, List[str]]:
        with self._lock:
            groups: Dict[str, List[str]] = {}
            for n, info in self._tools.items():
                cat = info["category"] or "uncategorized"
                groups.setdefault(cat, []).append(n)
            return groups

    def has_tool(self, name: str) -> bool:
        with self._lock:
            return name in self._tools

    def snapshot(self) -> Dict[str, dict]:
        with self._lock:
            return {
                name: {
                    "schema": info["schema"].copy(),
                    "tags": set(info["tags"]),
                    "category": info["category"],
                }
                for name, info in self._tools.items()
            }


registry = ToolRegistry()
