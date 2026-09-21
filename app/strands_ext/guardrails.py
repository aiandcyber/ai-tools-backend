"""Application guardrails using Strands InterventionHandler.

Bedrock Guardrail IDs (optional) can also be set via env for AWS Bedrock models.
These local interventions work with OpenRouter and are always on for demos.
"""

from __future__ import annotations

import re

from strands.hooks.events import BeforeInvocationEvent, BeforeToolCallEvent
from strands.interventions import Deny, InterventionHandler, Proceed

from app.strands_ext import audit

# Demo-friendly blocked phrases / attack patterns
_BLOCKED_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I),
    re.compile(r"jailbreak", re.I),
    re.compile(r"exfiltrate\s+(secrets?|api\s*keys?)", re.I),
    re.compile(r"rm\s+-rf\s+/", re.I),
]

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"OPENROUTER_API_KEY\s*=\s*\S+", re.I),
    re.compile(r"AWS_SECRET_ACCESS_KEY\s*=\s*\S+", re.I),
]

# Tools that must never be invented / called outside allowlist prefixes
_ALLOWED_TOOL_PREFIXES = (
    "run_",
    "skills",
    "search_specialist",
    "pdf_specialist",
    "office_specialist",
    "image_specialist",
    "media_specialist",
    "utility_specialist",
    "ai_specialist",
    "mcp_",  # MCP-prefixed tools
    "tools_info_",
    "list_catalog",
    "get_search",
    "health_check",
)


class ContentGuardrail(InterventionHandler):
    """Blocks prompt-injection / secret-leak attempts and unknown tools."""

    @property
    def name(self) -> str:
        return "content-guardrail"

    def before_invocation(self, event: BeforeInvocationEvent):
        text = _messages_text(event.messages)
        for pattern in _BLOCKED_PATTERNS:
            if pattern.search(text):
                audit.record("guardrail_deny", stage="before_invocation", reason=pattern.pattern)
                return Deny(reason="Blocked by Tools content guardrail (unsafe prompt pattern).")
        for pattern in _SECRET_PATTERNS:
            if pattern.search(text):
                audit.record("guardrail_deny", stage="before_invocation", reason="secret_pattern")
                return Deny(reason="Blocked by Tools content guardrail (possible secret in prompt).")
        return Proceed()

    def before_tool_call(self, event: BeforeToolCallEvent):
        tool_use = event.tool_use or {}
        name = ""
        if isinstance(tool_use, dict):
            name = str(tool_use.get("name") or "")
        else:
            name = str(getattr(tool_use, "name", "") or "")
        if not name:
            return Proceed()
        if not any(name == p or name.startswith(p) for p in _ALLOWED_TOOL_PREFIXES):
            # allow exact specialist names already listed; also bare MCP tool names from our server
            if name in {"list_catalog_tools", "get_search_regions", "tools_health"}:
                return Proceed()
            audit.record("guardrail_deny", stage="before_tool", tool=name, reason="tool_not_allowlisted")
            return Deny(reason=f"Blocked by Tools tool guardrail: '{name}' is not allowlisted.")
        return Proceed()


def _messages_text(messages) -> str:
    if not messages:
        return ""
    chunks: list[str] = []
    for message in messages:
        content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
        if isinstance(content, str):
            chunks.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and "text" in block:
                    chunks.append(str(block["text"]))
                else:
                    chunks.append(str(block))
        elif content is not None:
            chunks.append(str(content))
    return "\n".join(chunks)


GUARDRAIL_RULES = [
    "Block prompt-injection / jailbreak patterns",
    "Block prompts that look like pasted API secrets",
    "Allowlist specialist, skills, run_* and MCP catalog tools only",
    "Optional: set BEDROCK_GUARDRAIL_ID + BEDROCK_GUARDRAIL_VERSION when using Bedrock models",
]
