"""Claude Code primitives with no direct AgentSpec field: permissions, hooks,
slash-commands, plugins. Each is recorded in the ledger; carried values become
the bundle's MigrationExtensions sidecar. Omnigent agents run sandboxed, so
permissions are carried + flagged (DEGRADED), not bolted on as a guardrail."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
