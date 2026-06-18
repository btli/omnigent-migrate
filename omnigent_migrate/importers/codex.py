"""Codex -> Omnigent bundle importer.

A Codex setup = a project's AGENTS.md (instructions) + the global ~/.codex/config.toml
(model / mcp_servers / approval+sandbox). Produces a solo Omnigent bundle. Lenient-in:
every read is guarded and recorded; never aborts on bad input.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from omnigent_migrate.harness_map import resolve_harness
from omnigent_migrate.importers._util import _os_env, _sanitize, mcp_tool_entry
from omnigent_migrate.ir import Bundle
from omnigent_migrate.ledger import Ledger, Status

_DEFAULT_CONFIG = Path("~/.codex/config.toml")
_GOV_KEYS = ("approval_policy", "sandbox_mode", "approvals_reviewer")


def _read_toml(path: Path, ledger: Ledger) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return tomllib.loads(path.read_text())
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError):
        ledger.record("codex_config", str(path), Status.UNSUPPORTED, "unreadable or invalid TOML")
        return {}


class CodexImporter:
    name = "codex"

    def detect(self, project: Path) -> bool:
        return (project / "AGENTS.md").is_file() or _DEFAULT_CONFIG.expanduser().is_file()

    def to_bundle(
        self, project: Path, ledger: Ledger, config_path: Path | None = None
    ) -> Bundle:
        project = project.expanduser().resolve()
        name = _sanitize(project.name)

        prompt = ""
        for mem in ("AGENTS.md", "CLAUDE.md"):
            p = project / mem
            if not p.is_file():
                continue
            try:
                text = p.read_text()
            except (OSError, UnicodeDecodeError):
                ledger.record("memory", mem, Status.UNSUPPORTED, "unreadable")
                continue
            prompt += text + "\n"
            ledger.record("memory", mem, Status.TRANSLATED)
        if not prompt:
            prompt = "You are a coding agent for this repository. Follow its conventions.\n"
            ledger.record("memory", "(none)", Status.DEGRADED, "no AGENTS.md/CLAUDE.md; used a default")

        cfg_path = (config_path or _DEFAULT_CONFIG).expanduser()
        toml = _read_toml(cfg_path, ledger)
        ref = cfg_path.name

        model = toml.get("model")
        model_str = model if isinstance(model, str) and model else None
        harness, note = resolve_harness(model_str, "codex")
        executor: dict[str, Any] = {"type": "omnigent", "config": {"harness": harness}}
        if model_str is not None:
            executor["model"] = model_str
            ledger.record(
                "model", f"{ref}:model",
                Status.TRANSLATED if note is None else Status.DEGRADED, note or "",
            )
        else:
            ledger.record("model", "(none)", Status.DEGRADED, "no model in config; harness defaulted")
        cw = toml.get("model_context_window")
        if isinstance(cw, int):
            executor["context_window"] = cw
            ledger.record("context_window", f"{ref}:model_context_window", Status.TRANSLATED)

        tools: dict[str, Any] = {}
        servers = toml.get("mcp_servers")
        if isinstance(servers, dict):
            for sname, scfg in servers.items():
                if isinstance(scfg, dict):
                    tools[_sanitize(str(sname))] = mcp_tool_entry(scfg)
                    ledger.record("mcp_server", f"{ref}:mcp_servers.{sname}", Status.TRANSLATED)

        extensions: dict[str, Any] = {}
        gov = {k: toml[k] for k in _GOV_KEYS if k in toml}
        if gov:
            extensions["approvals"] = gov
            ledger.record(
                "approvals", f"{ref} (approval/sandbox)", Status.DEGRADED,
                "carried verbatim; not auto-enforced (Omnigent agents run sandboxed — the "
                "sandbox is the safety boundary)",
                "review the carried approval/sandbox settings; translate to an Omnigent "
                "guardrail policy if you need enforcement",
            )
        if toml.get("apps"):
            ledger.record(
                "connectors", f"{ref}:apps", Status.DEGRADED,
                "Codex app-connectors found; not migrated (may hold credentials, so not carried)",
                "re-add the equivalent integrations as Omnigent MCP tools",
            )

        config: dict[str, Any] = {
            "spec_version": 1,
            "name": name,
            "description": f"Migrated from Codex: {project.name}",
            "executor": executor,
            "prompt": prompt,
            "async": True,
            "cancellable": True,
            "os_env": _os_env(),
        }
        if tools:
            config["tools"] = tools

        ledger.note(
            "Scanned: AGENTS.md/CLAUDE.md, model, context_window, MCP servers, "
            "approval/sandbox. Codex profiles, per-project trust, TUI, model-tuning "
            "(reasoning_effort/auto_compact) and app-connectors are not migrated — "
            "noted above where present."
        )
        return Bundle(config=config, extensions=extensions)
