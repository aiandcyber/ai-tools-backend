"""MCP helpers — connect Strands Agent to local MCP servers."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from app.strands_ext import audit

MCP_ROOT = Path(__file__).resolve().parents[2] / "mcp_servers"
DEFAULT_CONFIG = MCP_ROOT / "mcp.json"


def mcp_config_path() -> Path:
    return DEFAULT_CONFIG


def write_default_mcp_config() -> Path:
    """Ensure mcp.json points at the local tools-info stdio server."""
    MCP_ROOT.mkdir(parents=True, exist_ok=True)
    server = MCP_ROOT / "tools_info_server.py"
    config = {
        "mcpServers": {
            "tools-info": {
                "command": sys.executable,
                "args": [str(server)],
                "cwd": str(MCP_ROOT.parent),
                "prefix": "mcp_tools_",
                "continue_on_error": True,
                "startup_timeout": 20,
                "application_name": "ai-tools",
                "application_version": "0.1.0",
            }
        }
    }
    DEFAULT_CONFIG.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return DEFAULT_CONFIG


def load_mcp_clients() -> list[Any]:
    """Load MCP clients for the orchestrator. Empty list if unavailable."""
    try:
        from strands.tools.mcp import MCPClient
    except Exception as exc:  # noqa: BLE001
        audit.record("mcp_error", error=f"import failed: {exc}")
        return []

    path = write_default_mcp_config()
    try:
        clients = MCPClient.load_servers(str(path), continue_on_error=True, prefix_with_server_name=False)
        audit.record("mcp_loaded", servers=len(clients), config=str(path))
        return clients
    except Exception as exc:  # noqa: BLE001
        audit.record("mcp_error", error=str(exc))
        return []
