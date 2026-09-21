"""Strands HookProvider — audit trail for multi-agent lifecycle events."""

from __future__ import annotations

from typing import Any

from strands.hooks import (
    AfterInvocationEvent,
    AfterToolCallEvent,
    BeforeInvocationEvent,
    BeforeToolCallEvent,
    HookProvider,
    HookRegistry,
)

from app.strands_ext import audit


class ToolsAuditHook(HookProvider):
    """Records Strands lifecycle events for demos and debugging."""

    def __init__(self, label: str = "orchestrator") -> None:
        self.label = label

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeInvocationEvent, self.on_before_invocation)
        registry.add_callback(AfterInvocationEvent, self.on_after_invocation)
        registry.add_callback(BeforeToolCallEvent, self.on_before_tool)
        registry.add_callback(AfterToolCallEvent, self.on_after_tool)

    def on_before_invocation(self, event: BeforeInvocationEvent) -> None:
        preview = ""
        if event.messages:
            last = event.messages[-1]
            content = last.get("content") if isinstance(last, dict) else getattr(last, "content", None)
            preview = str(content)[:180]
        audit.record("before_invocation", agent=self.label, preview=preview)

    def on_after_invocation(self, event: AfterInvocationEvent) -> None:
        audit.record("after_invocation", agent=self.label)

    def on_before_tool(self, event: BeforeToolCallEvent) -> None:
        tool_use = event.tool_use or {}
        name = tool_use.get("name") if isinstance(tool_use, dict) else getattr(tool_use, "name", "")
        audit.record("before_tool", agent=self.label, tool=name)

    def on_after_tool(self, event: AfterToolCallEvent) -> None:
        tool_use = event.tool_use or {}
        name = tool_use.get("name") if isinstance(tool_use, dict) else getattr(tool_use, "name", "")
        status = None
        if event.tool_result and isinstance(event.tool_result, dict):
            status = event.tool_result.get("status")
        audit.record("after_tool", agent=self.label, tool=name, status=status, cancelled=bool(event.cancel_message))
