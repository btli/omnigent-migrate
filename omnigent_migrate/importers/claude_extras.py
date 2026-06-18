"""Claude Code primitives with no direct AgentSpec field: permissions, hooks,
slash-commands, plugins. Each is recorded in the ledger; carried values become
the bundle's MigrationExtensions sidecar. Omnigent agents run sandboxed, so
permissions are carried + flagged (DEGRADED), not bolted on as a guardrail."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from omnigent_migrate.importers._util import _frontmatter
from omnigent_migrate.ledger import Ledger, Status


def read_settings(project: Path) -> dict[str, Any]:
    """Shallow-merge .claude/settings.json then settings.local.json (later wins)."""
    merged: dict[str, Any] = {}
    for fn in ("settings.json", "settings.local.json"):
        p = project / ".claude" / fn
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text())
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            merged.update(data)
    return merged


def collect_permissions(settings: dict[str, Any], ledger: Ledger) -> Any:
    """Carry Claude `permissions` verbatim; the sandbox is the real boundary.

    Returns the raw permissions (or None). No Omnigent handler enforces arbitrary
    allow/deny lists, so they are flagged DEGRADED with an opt-in guardrail hint
    rather than silently approximated.
    """
    perms = settings.get("permissions")
    if not perms:
        return None
    ledger.record(
        "permissions",
        ".claude/settings.json",
        Status.DEGRADED,
        "carried verbatim; not auto-enforced (Omnigent agents run sandboxed, so the "
        "sandbox is the safety boundary)",
        "if you want an extra catastrophic-command net, add a blast_radius policy "
        "(omnigent.inner.nessie.policies.blast_radius) to config.yaml under guardrails",
    )
    return perms


def collect_hooks(settings: dict[str, Any], ledger: Ledger) -> dict[str, Any] | None:
    """Claude shell hooks have no bundle-declarative home in Omnigent → carried."""
    hooks = settings.get("hooks")
    if not hooks or not isinstance(hooks, dict):
        return None
    n_cmds = 0
    for matchers in hooks.values():
        for entry in matchers or []:
            if isinstance(entry, dict):
                n_cmds += len(entry.get("hooks") or [])
    ledger.record(
        "hooks",
        ".claude/settings.json",
        Status.UNSUPPORTED,
        f"{n_cmds} hook command(s) across {len(hooks)} event(s); Omnigent has no "
        "bundle-declarative shell hooks",
        "re-implement as Omnigent guardrail policies or runtime hooks; the raw "
        "definitions are in MIGRATION_EXTENSIONS.yaml",
    )
    return hooks


def collect_commands(project: Path, ledger: Ledger) -> list[dict[str, Any]] | None:
    """Slash commands are prose ≈ a skill, but not auto-converted → carried."""
    cmd_dir = project / ".claude" / "commands"
    if not cmd_dir.is_dir():
        return None
    out: list[dict[str, Any]] = []
    for md in sorted(cmd_dir.glob("*.md")):
        fm, body = _frontmatter(md.read_text())
        out.append(
            {"name": md.stem, "description": str(fm.get("description") or ""), "body": body}
        )
    if not out:
        return None
    ledger.record(
        "slash_commands",
        f".claude/commands/ ({len(out)})",
        Status.DEGRADED,
        "carried as prose; a slash command ≈ a skill but is not auto-converted",
        "convert each command in MIGRATION_EXTENSIONS.yaml to a skill under "
        ".claude/skills/<name>/SKILL.md if you want it host-discovered",
    )
    return out


def collect_plugins(
    project: Path, settings: dict[str, Any], ledger: Ledger
) -> dict[str, Any] | None:
    """Plugin references are recorded but not expanded into the bundle."""
    info: dict[str, Any] = {}
    enabled = settings.get("enabledPlugins")
    if enabled:
        info["enabledPlugins"] = enabled
    plugin_dir = project / ".claude-plugin"
    if plugin_dir.is_dir():
        files = sorted(p.name for p in plugin_dir.glob("*.json"))
        if files:
            info["plugin_definition"] = files
    if not info:
        return None
    ledger.record(
        "plugins",
        ".claude-plugin / settings.enabledPlugins",
        Status.DEGRADED,
        "plugin references recorded but not expanded into the bundle",
        "install/port the referenced plugins in Omnigent; refs are in "
        "MIGRATION_EXTENSIONS.yaml",
    )
    return info


def collect_claude_extras(project: Path, ledger: Ledger) -> dict[str, Any]:
    """Parse settings/commands/plugins; return the MigrationExtensions sidecar dict."""
    settings = read_settings(project)
    extensions: dict[str, Any] = {}
    perms = collect_permissions(settings, ledger)
    if perms is not None:
        extensions["permissions"] = perms
    hooks = collect_hooks(settings, ledger)
    if hooks is not None:
        extensions["hooks"] = hooks
    commands = collect_commands(project, ledger)
    if commands:
        extensions["commands"] = commands
    plugins = collect_plugins(project, settings, ledger)
    if plugins:
        extensions["plugins"] = plugins
    return extensions
