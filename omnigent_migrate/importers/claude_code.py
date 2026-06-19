"""Claude Code -> Omnigent bundle importer (core primitives)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from omnigent_migrate.harness_map import resolve_harness
from omnigent_migrate.importers._util import _frontmatter, _os_env, _sanitize, build_persona, mcp_tool_entry
from omnigent_migrate.importers.claude_extras import collect_claude_extras
from omnigent_migrate.ir import Bundle
from omnigent_migrate.ledger import Ledger, Status


class ClaudeCodeImporter:
    name = "claude_code"

    def detect(self, project: Path) -> bool:
        return (project / ".claude").is_dir() or (project / "CLAUDE.md").is_file()

    def to_bundle(self, project: Path, ledger: Ledger) -> Bundle:
        project = project.expanduser().resolve()
        name = _sanitize(project.name)

        memory_files = [m for m in ("CLAUDE.md", "AGENTS.md") if (project / m).is_file()]
        for m in memory_files:
            ledger.record(
                "memory", m, Status.TRANSLATED,
                "left in place; the harness auto-loads it at cwd=project",
            )

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
                entry = mcp_tool_entry(cfg)
                if entry is None:
                    ledger.record(
                        "mcp_server", f"{mcp_file}:{sname}", Status.UNSUPPORTED,
                        "no command/url transport — not representable as an Omnigent MCP tool",
                    )
                    continue
                mcp_tools[_sanitize(sname)] = entry
                ledger.record("mcp_server", f"{mcp_file}:{sname}", Status.TRANSLATED)

        skills_present = False
        skills_dir = project / ".claude" / "skills"
        if skills_dir.is_dir():
            n = sum(1 for d in skills_dir.iterdir() if (d / "SKILL.md").is_file())
            if n:
                skills_present = bool(n)
                ledger.record(
                    "skills",
                    f".claude/skills/ ({n})",
                    Status.TRANSLATED,
                    "left in place; Omnigent host-discovers them at cwd=project",
                )

        prompt = build_persona(
            project.name,
            memory_files,
            skills_present,
            [(a, agents[a]["description"]) for a in sorted(agents)],
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

        extensions = collect_claude_extras(project, ledger)
        ledger.note(
            "Scanned: memory, sub-agents, MCP, skills, permissions, hooks, "
            "slash-commands, plugins. Items not representable in the bundle are "
            "recorded above (DEGRADED/UNSUPPORTED) and carried in "
            "MIGRATION_EXTENSIONS.yaml — nothing was dropped."
        )
        return Bundle(config=config, agents=agents, extensions=extensions)
