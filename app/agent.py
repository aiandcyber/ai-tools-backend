"""Strands multi-agent orchestrator with Skills, Hooks, Guardrails, and MCP."""

from __future__ import annotations

import json
from contextvars import ContextVar
from pathlib import Path

from app.catalog import CATEGORIES, TOOLS
from app.runner import run_tool
from app.workspace import publish

CHAT_FILES: ContextVar[list] = ContextVar("chat_files", default=[])
CHAT_DOWNLOADS: ContextVar[list] = ContextVar("chat_downloads", default=[])

SKILLS_ROOT = Path(__file__).resolve().parent.parent / "skills"

CATEGORY_SKILL = {
    "search": "search-tools",
    "pdf": "pdf-tools",
    "office": "office-tools",
    "image": "image-tools",
    "media": "media-tools",
    "utility": "utility-tools",
    "ai": "ai-tools",
}

_MCP_CLIENTS: list = []


def resolve_llm_provider(preferred: str | None = None) -> str:
    from app import config

    choice = (preferred or config.LLM_PROVIDER or "auto").strip().lower()
    if choice == "gemini":
        if not config.GEMINI_API_KEY:
            raise RuntimeError("Set GEMINI_API_KEY to use Gemini")
        return "gemini"
    if choice == "openrouter":
        if not config.OPENROUTER_API_KEY:
            raise RuntimeError("Set OPENROUTER_API_KEY to use OpenRouter")
        return "openrouter"
    # auto
    if config.OPENROUTER_API_KEY:
        return "openrouter"
    if config.GEMINI_API_KEY:
        return "gemini"
    raise RuntimeError("Set OPENROUTER_API_KEY or GEMINI_API_KEY")


def _build_model(provider: str):
    from strands.models.openai import OpenAIModel

    from app import config

    if provider == "gemini":
        return OpenAIModel(
            client_args={
                "api_key": config.GEMINI_API_KEY,
                "base_url": config.GEMINI_BASE_URL,
            },
            model_id=config.GEMINI_MODEL,
            params={"temperature": 0.1},
        )
    return OpenAIModel(
        client_args={
            "api_key": config.OPENROUTER_API_KEY,
            "base_url": config.OPENROUTER_BASE_URL,
        },
        model_id=config.OPENROUTER_MODEL,
        params={"temperature": 0.1},
    )


def _ids(category: str) -> str:
    return ", ".join(item.id for item in TOOLS if item.category == category)


def _skill_path(name: str) -> Path:
    return SKILLS_ROOT / name


def category_runner(category: str):
    from strands import tool

    @tool(
        name=f"run_{category}_tool",
        description=(
            f"Run a {category} tool. tool_id must be one of: {_ids(category)}. "
            "options_json is a JSON object of form fields. Uses files attached to this chat."
        ),
    )
    def run_category_tool(tool_id: str, options_json: str = "{}") -> str:
        allowed = {item.id for item in TOOLS if item.category == category}
        if tool_id not in allowed:
            return f"{tool_id} is not a {category} tool. Choose from: {_ids(category)}"
        try:
            options = json.loads(options_json or "{}")
        except json.JSONDecodeError as exc:
            return f"Invalid options_json: {exc}"
        outcome = run_tool(tool_id, list(CHAT_FILES.get()), options)
        downloads = CHAT_DOWNLOADS.get()
        for item in outcome.files:
            downloads.append(publish(item))
        if outcome.results:
            preview = [f"- {hit.get('title')} | {hit.get('url')}" for hit in outcome.results[:5]]
            return f"{outcome.message}\n" + "\n".join(preview)
        return outcome.message

    return run_category_tool


def build_orchestrator(provider: str | None = None):
    """Build Strands multi-agent graph with Skills + Hooks + Guardrails + MCP."""
    from strands import Agent, tool
    from strands.vended_plugins.skills import AgentSkills

    from app.strands_ext.guardrails import ContentGuardrail
    from app.strands_ext.hooks import ToolsAuditHook
    from app.strands_ext.mcp_loader import load_mcp_clients

    global _MCP_CLIENTS

    if not SKILLS_ROOT.is_dir():
        raise RuntimeError(f"Skills directory missing: {SKILLS_ROOT}")

    provider = resolve_llm_provider(provider)
    model = _build_model(provider)

    guardrail = ContentGuardrail()
    specialists = []
    for category, label in CATEGORIES:
        skill_name = CATEGORY_SKILL[category]
        specialist = Agent(
            model=model,
            name=f"{category}_specialist",
            description=f"Handle {label} requests. Tool ids: {_ids(category)}",
            system_prompt=(
                f"You are the {label} specialist in a Strands multi-agent Tools workspace. "
                f"Activate the `{skill_name}` skill when useful, then call run_{category}_tool. "
                "Do not claim a file was created unless the tool returns success."
            ),
            tools=[category_runner(category)],
            plugins=[AgentSkills(skills=[_skill_path(skill_name)])],
            hooks=[ToolsAuditHook(label=f"{category}_specialist")],
            interventions=[guardrail],
        )
        if hasattr(specialist, "as_tool"):
            specialists.append(
                specialist.as_tool(
                    name=f"{category}_specialist",
                    description=f"Handle {label} requests. Tool ids: {_ids(category)}",
                )
            )
        else:

            @tool(
                name=f"{category}_specialist",
                description=f"Handle {label} requests. Tool ids: {_ids(category)}",
            )
            def delegate(task: str, _agent=specialist) -> str:
                return str(_agent(task))

            specialists.append(delegate)

    _MCP_CLIENTS = load_mcp_clients()
    tools: list = list(specialists) + list(_MCP_CLIENTS)

    agent = Agent(
        model=model,
        name="tools_orchestrator",
        description="Top-level Tools assistant with Skills, Hooks, Guardrails, and MCP.",
        system_prompt=(
            "You are the Tools assistant for an enterprise file workspace. "
            "You are a Strands multi-agent orchestrator with Skills, Hooks, Guardrails, and MCP. "
            "Activate `tools-orchestrator` via the skills tool when helpful. "
            "Prefer specialist tools for file work. Use MCP tools (mcp_tools_*) to inspect the catalog "
            "or search regions when the user asks what tools/regions exist. "
            "Reply in the user's language. Never invent download links or social profile URLs. "
            "Write plain sentences. Do not use emoji, markdown, asterisks, or stage directions."
        ),
        callback_handler=None,
        tools=tools,
        plugins=[AgentSkills(skills=[SKILLS_ROOT])],
        hooks=[ToolsAuditHook(label="orchestrator")],
        interventions=[guardrail],
    )
    agent._ai_tools_llm_provider = provider  # type: ignore[attr-defined]
    return agent


def strands_feature_status() -> dict:
    from app.strands_ext import audit
    from app.strands_ext.guardrails import GUARDRAIL_RULES
    from app.strands_ext.mcp_loader import load_mcp_clients, mcp_config_path

    global _MCP_CLIENTS
    if not _MCP_CLIENTS:
        _MCP_CLIENTS = load_mcp_clients()

    skills = sorted(p.name for p in SKILLS_ROOT.iterdir() if p.is_dir() and (p / "SKILL.md").exists())
    return {
        "framework": "Amazon Strands Agents",
        "features": {
            "multi_agent": True,
            "skills": True,
            "hooks": True,
            "guardrails": True,
            "mcp": True,
        },
        "skills": skills,
        "skills_root": str(SKILLS_ROOT),
        "guardrail_rules": GUARDRAIL_RULES,
        "mcp_config": str(mcp_config_path()),
        "mcp_clients_loaded": len(_MCP_CLIENTS),
        "recent_hook_events": audit.recent(15),
    }
