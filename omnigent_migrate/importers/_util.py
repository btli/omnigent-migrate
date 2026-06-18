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
