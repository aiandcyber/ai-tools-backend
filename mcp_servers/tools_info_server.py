#!/usr/bin/env python3
"""Local MCP server for AI Tools — catalog + search region info.

Used by Strands MCPClient (stdio) so the orchestrator can call MCP tools.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow importing app when launched from mcp_servers/
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp.server.mcpserver import MCPServer

server = MCPServer("tools-info", instructions="AI Tools catalog and search metadata over MCP.")


@server.tool(name="list_catalog_tools", description="List AI Tools catalog entries (id, category, title).")
def list_catalog_tools(category: str = "") -> str:
    from app.catalog import TOOLS

    rows = []
    for tool in TOOLS:
        if category and tool.category != category:
            continue
        rows.append({"id": tool.id, "category": tool.category, "title": tool.title})
    return json.dumps({"count": len(rows), "tools": rows}, indent=2)


@server.tool(name="get_search_regions", description="List supported search region codes for people/topic search.")
def get_search_regions() -> str:
    from app.tools.search import REGION_PROFILES
    from app import config

    return json.dumps(
        {
            "default": config.SEARCH_DEFAULT_REGION,
            "regions": [{"code": code, "label": info["label"]} for code, info in REGION_PROFILES.items()],
        },
        indent=2,
    )


@server.tool(name="tools_health", description="Return a simple health payload for the Tools MCP server.")
def tools_health() -> str:
    return json.dumps({"status": "ok", "server": "tools-info", "framework": "strands+mcp"})


if __name__ == "__main__":
    server.run(transport="stdio")
