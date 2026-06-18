"""Shared importer helpers (frontmatter parsing, name sanitizing, os_env)."""

from __future__ import annotations

import re
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

_yaml = YAML(typ="safe")
_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]")


def _sanitize(name: str) -> str:
    return _NAME_RE.sub("-", name) or "agent"


def _frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            try:
                loaded = _yaml.load(parts[1])
            except YAMLError:
                loaded = None
            fm = loaded if isinstance(loaded, dict) else {}
            return fm, parts[2].lstrip("\n")
    return {}, text


def _os_env() -> dict[str, Any]:
    return {"type": "caller_process", "cwd": ".", "sandbox": {"type": "none"}}


def build_persona(
    project_name: str,
    memory_files: list[str],
    skills_present: bool,
    agents: list[tuple[str, str]],
) -> str:
    """The agent's persona (its role) — NOT the project's docs. Points the agent at
    the repo's CLAUDE.md/AGENTS.md/skills, which the harness auto-loads at cwd=project."""
    refs: list[str] = []
    if memory_files:
        refs.append("the guidance in the repo's " + " / ".join(memory_files))
    if skills_present:
        refs.append("the skills under .claude/skills/")
    follow = (" Follow " + " and ".join(refs) + ".") if refs else ""
    if agents:
        roster = "\n".join(f"  - {name}: {desc}" for name, desc in agents)
        return (
            f"You are the orchestrator for the {project_name} repository. You coordinate "
            "specialized sub-agents and delegate work to them rather than doing it yourself. "
            f"Your sub-agents:\n{roster}\n"
            "Decompose each request, route each part to the most appropriate sub-agent, and "
            f"integrate their results.{follow}\n"
        )
    return f"You are a coding agent working in the {project_name} repository.{follow}\n"


def mcp_tool_entry(cfg: dict[str, Any]) -> dict[str, Any] | None:
    """Build an Omnigent `tools.<name>` MCP entry from a source MCP server config.

    Handles both Claude JSON `mcpServers` and Codex `[mcp_servers.*]` — they share the
    command/args/env (stdio) and url/headers (http) shape.

    Returns None when neither ``command`` nor ``url`` is present — no representable
    transport, so no valid Omnigent MCP tool can be constructed.
    """
    if "command" not in cfg and "url" not in cfg:
        return None
    entry: dict[str, Any] = {"type": "mcp"}
    if "command" in cfg:
        entry["command"] = cfg["command"]
        if cfg.get("args"):
            entry["args"] = cfg["args"]
        if cfg.get("env"):
            entry["env"] = cfg["env"]
    else:
        entry["url"] = cfg["url"]
        if cfg.get("headers"):
            entry["headers"] = cfg["headers"]
    return entry
