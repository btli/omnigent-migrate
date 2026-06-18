"""Claude Code -> Omnigent bundle importer (core primitives)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from omnigent_migrate.harness_map import resolve_harness
from omnigent_migrate.ir import Bundle
from omnigent_migrate.ledger import Ledger, Status

_yaml = YAML(typ="safe")
_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]")


def _sanitize(name: str) -> str:
    return _NAME_RE.sub("-", name) or "agent"


def _frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return (_yaml.load(parts[1]) or {}), parts[2].lstrip("\n")
    return {}, text


def _os_env() -> dict[str, Any]:
    return {"type": "caller_process", "cwd": ".", "sandbox": {"type": "none"}}


class ClaudeCodeImporter:
    name = "claude_code"

    def detect(self, project: Path) -> bool:
        return (project / ".claude").is_dir() or (project / "CLAUDE.md").is_file()

    def to_bundle(self, project: Path, ledger: Ledger) -> Bundle:
        project = project.expanduser().resolve()
        name = _sanitize(project.name)

        prompt = ""
        for mem in ("CLAUDE.md", "AGENTS.md"):
            p = project / mem
            if p.is_file():
                prompt += p.read_text() + "\n"
                ledger.record("memory", mem, Status.TRANSLATED)
        if not prompt:
            prompt = "You are a coding agent for this repository. Follow its conventions.\n"
            ledger.record("memory", "(none)", Status.DEGRADED, "no CLAUDE.md/AGENTS.md; used a default")

        agents: dict[str, dict[str, Any]] = {}
        agents_dir = project / ".claude" / "agents"
        if agents_dir.is_dir():
            for md in sorted(agents_dir.glob("*.md")):
                fm, body = _frontmatter(md.read_text())
                aname = _sanitize(str(fm.get("name") or md.stem))
                harness, note = resolve_harness(fm.get("model"), "claude_code")
                agents[aname] = {
                    "spec_version": 1,
                    "name": aname,
                    "description": str(fm.get("description") or f"{aname} sub-agent"),
                    "executor": {"type": "omnigent", "config": {"harness": harness}},
                    "prompt": body or f"You are the {aname} sub-agent.\n",
                    "os_env": _os_env(),
                }
                ledger.record(
                    "subagent",
                    f".claude/agents/{md.name}",
                    Status.TRANSLATED if note is None else Status.DEGRADED,
                    note or "",
                )

        mcp_tools: dict[str, Any] = {}
        for mcp_file in (".mcp.json", ".claude.json"):
            p = project / mcp_file
            if not p.is_file():
                continue
            try:
                data = json.loads(p.read_text())
            except json.JSONDecodeError:
                ledger.record("mcp_servers", mcp_file, Status.UNSUPPORTED, "invalid JSON")
                continue
            servers = data.get("mcpServers") or data.get("mcp_servers") or {}
            for sname, cfg in servers.items():
                entry: dict[str, Any] = {"type": "mcp"}
                if "command" in cfg:
                    entry["command"] = cfg["command"]
                    if cfg.get("args"):
                        entry["args"] = cfg["args"]
                    if cfg.get("env"):
                        entry["env"] = cfg["env"]
                elif "url" in cfg:
                    entry["url"] = cfg["url"]
                    if cfg.get("headers"):
                        entry["headers"] = cfg["headers"]
                mcp_tools[_sanitize(sname)] = entry
                ledger.record("mcp_server", f"{mcp_file}:{sname}", Status.TRANSLATED)

        skills_dir = project / ".claude" / "skills"
        if skills_dir.is_dir():
            n = sum(1 for d in skills_dir.iterdir() if (d / "SKILL.md").is_file())
            if n:
                ledger.record(
                    "skills",
                    f".claude/skills/ ({n})",
                    Status.TRANSLATED,
                    "left in place; Omnigent host-discovers them at cwd=project",
                )

        config: dict[str, Any] = {
            "spec_version": 1,
            "name": name,
            "description": f"Migrated from Claude Code: {project.name}",
            "executor": {"type": "omnigent", "config": {"harness": "claude-sdk"}},
            "prompt": prompt,
            "async": True,
            "cancellable": True,
            "os_env": _os_env(),
        }
        tools: dict[str, Any] = dict(mcp_tools)
        if agents:
            config["spawn"] = True
            tools["agents"] = sorted(agents)
        if tools:
            config["tools"] = tools
        return Bundle(config=config, agents=agents)
