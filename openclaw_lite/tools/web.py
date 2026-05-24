"""Bare web tools — search and fetch. No SSRF/URL guards."""
import re
import urllib.request
import urllib.parse
from ..registry import registry


def net_web_search(query: str, num_results: int = 5) -> str:
    """Search the web using DuckDuckGo HTML endpoint."""
    try:
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        results = []
        for m in re.finditer(r'<a rel="nofollow" class="result__a" href="([^"]+)">([^<]+)</a>', html):
            href, title = m.group(1), re.sub(r'<[^>]+>', '', m.group(2))
            results.append(f"- {title}\n  {href}")
            if len(results) >= num_results:
                break
        return "\n".join(results) or "No results found."
    except Exception as e:
        return f"Search error: {e}"


def net_web_extract(url: str) -> str:
    """Fetch and extract text from a URL."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:4000] + ("\n... (truncated)" if len(text) > 4000 else "")
    except Exception as e:
        return f"Fetch error: {e}"


registry.register(
    name="net_web_search",
    description="Search the web using DuckDuckGo. No API key required.",
    parameters={
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "num_results": {"type": "integer", "description": "Number of results", "default": 5}
        },
        "required": ["query"]
    },
    handler=net_web_search,
    tags=["network", "search"],
    category="network"
)

registry.register(
    name="net_web_extract",
    description="Fetch a URL and extract plain text. Strips HTML tags.",
    parameters={
        "properties": {
            "url": {"type": "string", "description": "Full http(s) URL to fetch"}
        },
        "required": ["url"]
    },
    handler=net_web_extract,
    tags=["network", "fetch"],
    category="network"
)
