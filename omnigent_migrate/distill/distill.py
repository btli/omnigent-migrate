"""Orchestrate the distiller: profile + select (propose), serialize the editable
plan, and build+validate the bundle from an approved plan (apply)."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from omnigent_migrate.distill.archetypes import LIBRARY
from omnigent_migrate.distill.profiler import profile as profile_project
from omnigent_migrate.distill.schema import Team
from omnigent_migrate.distill.selector.base import Selector
from omnigent_migrate.exporter import export
from omnigent_migrate.importers._util import _os_env, _sanitize
from omnigent_migrate.importers.claude_extras import collect_claude_extras
from omnigent_migrate.ir import Bundle
from omnigent_migrate.ledger import Ledger

_yaml = YAML()
_yaml.default_flow_style = False


def propose(project: Path, selector: Selector) -> Team:
    return selector.propose(profile_project(project), LIBRARY)


def write_plan(team: Team, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    _yaml.dump(team.model_dump(), buf)
    path.write_text("# Reviewed distiller plan — edit, then `distill <project> --apply`.\n" + buf.getvalue())


def read_plan(path: Path) -> Team:
    return Team.model_validate(_yaml.load(path.read_text()))


def _persona(text: str) -> str:
    return text if text.endswith("\n") else text + "\n"


def _agent_config(name: str, persona: str, harness: str, model: str | None) -> dict[str, Any]:
    executor: dict[str, Any] = {"type": "omnigent", "config": {"harness": harness}}
    if model:
        executor["model"] = model
    return {
        "spec_version": 1,
        "name": name,
        "description": f"{name} sub-agent",
        "executor": executor,
        "prompt": _persona(persona),
        "os_env": _os_env(),
    }


def apply(project: Path, plan_path: Path, out: Path, ledger: Ledger) -> Path:
    team = read_plan(plan_path)
    agents: dict[str, dict[str, Any]] = {}
    for w in [*team.workers, team.reviewer]:
        agents[_sanitize(w.name)] = _agent_config(_sanitize(w.name), w.persona, w.harness, w.model)
    for s in team.specialists:
        agents[_sanitize(s.name)] = _agent_config(_sanitize(s.name), s.persona, s.harness, s.model)

    extensions = collect_claude_extras(project, ledger)  # port permissions/hooks/commands/plugins
    config: dict[str, Any] = {
        "spec_version": 1,
        "name": _sanitize(project.name),
        "description": f"Distilled Omnigent team for {project.name}",
        "executor": {"type": "omnigent", "config": {"harness": "claude-sdk"}},
        "prompt": _persona(team.orchestrator["persona"]),
        "async": True,
        "cancellable": True,
        "os_env": _os_env(),
        "spawn": True,
        "tools": {"agents": sorted(agents)},
    }
    return export(Bundle(config=config, agents=agents, extensions=extensions), out)
