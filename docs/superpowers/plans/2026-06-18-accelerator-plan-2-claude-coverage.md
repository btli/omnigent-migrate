# Omnigent Migration Accelerator — Plan 2 (full Claude coverage)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Hard scope rule: implement ONLY the task you were dispatched for, commit it, and STOP — do not start the next task** (the workflow requires a review between tasks).

**Goal:** Extend the Claude Code importer to cover the four primitives Plan 1 deferred — **permissions, hooks, slash-commands, plugins** — each mapped honestly (TRANSLATED / DEGRADED / UNSUPPORTED), with a `MigrationExtensions` sidecar so nothing carried is ever silently dropped, plus a golden-report test.

**Architecture:** Same lenient-in / strict-out loop as Plan 1. New: (1) `Bundle` gains an `extensions` dict (carried-but-unmapped source primitives); the exporter writes them to a companion `MIGRATION_EXTENSIONS.yaml` that Omnigent ignores at load. (2) A new `importers/claude_extras.py` parses `settings.json` + `.claude/commands/` + `.claude-plugin/` and records fidelity. (3) Permissions map to an *approximate* `blast_radius` guardrail in `config.yaml` (the only one that references a real Omnigent handler); the precise allow/deny rules ride in the sidecar as a DEGRADED manual step.

**Tech Stack:** Python 3.13, `uv`, `click`, `ruamel.yaml`, `pytest`, `ruff`, `mypy`; `omnigent` (editable) for validation only. Build on the `feat/mvp` branch (Plan 1 is committed there).

**Spec:** `docs/superpowers/specs/2026-06-18-migration-accelerator-design.md` §6 (the deferred rows), §5 (`MigrationExtensions`), §12 (golden tests).

## Global Constraints

- Use `uv` for everything (`uv run pytest`, `uv run ruff check`, `uv run mypy omnigent_migrate`). NEVER pip/python directly.
- NEVER disable a linter/type check (`# noqa`, `# type: ignore`, etc.). Fix the root cause.
- Strict TDD: failing test first → watch it fail → implement → watch it pass → commit.
- `mypy --strict` clean: annotate everything; use `dict[str, Any]` for the loosely-typed bundle/settings JSON.
- The IR is the **public bundle-config dict** (NOT omnigent's internal `AgentSpec`). Express guardrails/extensions in bundle-config terms only.

**Verified facts (spike-confirmed against the real `omnigent.spec.load`; don't re-derive):**
- A `guardrails:` block referencing the real `blast_radius` builtin **validates** under `load(path, expand_env=False, enforce_handler_allowlist=False)`. The **minimal** valid form (proven) is:
  ```yaml
  guardrails:
    policies:
      blast_radius:
        type: function
        function:
          path: omnigent.inner.nessie.policies.blast_radius
  ```
- Omnigent policies must reference a **real handler path**; `omnigent/spec/validator.py` rejects/no-ops fabricated handlers. So arbitrary Claude allow/deny lists CANNOT be auto-enforced — `blast_radius` is an honest *approximation* (a catastrophic-command DENY set), and the precise rules are carried + flagged DEGRADED.
- Extra files in the bundle dir (`MIGRATION_REPORT.md`, and now `MIGRATION_EXTENSIONS.yaml`) are **ignored** by the loader — proven by Plan 1's passing integration test, which validates a dir already containing `MIGRATION_REPORT.md`.
- Real Claude shapes (from live projects):
  - `settings.json` → `{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "...", "timeout": 10}]}], "PostToolUse": [...]}, "enabledPlugins": {...}, "permissions": {"allow": [...], "deny": [...], "defaultMode": "..."}}`.
  - `.claude/commands/<name>.md` → frontmatter (`description`, `allowed-tools`, `argument-description`, `user-invocable`) + a prose markdown body.
  - `.claude-plugin/` → `plugin.json` + `marketplace.json`.

---

### Task 1: `Bundle.extensions` + exporter writes the sidecar

**Files:**
- Modify: `omnigent_migrate/ir.py`
- Modify: `omnigent_migrate/exporter.py`
- Test: `tests/test_ir.py`, `tests/test_exporter.py`

**Interfaces:**
- Produces: `Bundle(config, agents={}, extensions={})` — `extensions: dict[str, Any]`. Exporter writes `<out>/MIGRATION_EXTENSIONS.yaml` iff `bundle.extensions` is non-empty; the bundle still validates.

- [ ] **Step 1: Failing tests.** Append to `tests/test_ir.py`:
```python
def test_bundle_extensions_default_empty() -> None:
    from omnigent_migrate.ir import Bundle

    assert Bundle(config={"name": "x"}).extensions == {}
```
Append to `tests/test_exporter.py`:
```python
def test_export_writes_extensions_sidecar(tmp_path: Path) -> None:
    b = _solo()
    b.extensions["hooks"] = {"PreToolUse": [{"matcher": "Bash"}]}
    out = export(b, tmp_path / "bundle")
    sidecar = out / "MIGRATION_EXTENSIONS.yaml"
    assert sidecar.is_file()
    assert sidecar.read_text().startswith("# Carried from the source project")


def test_export_no_extensions_no_sidecar(tmp_path: Path) -> None:
    out = export(_solo(), tmp_path / "bundle")
    assert not (out / "MIGRATION_EXTENSIONS.yaml").exists()
```
- [ ] **Step 2:** `uv run pytest tests/test_ir.py tests/test_exporter.py -q` → FAIL (no `extensions`; no sidecar).
- [ ] **Step 3: Implement.** In `omnigent_migrate/ir.py`, add the field to `Bundle`:
```python
@dataclass
class Bundle:
    """A migrated bundle: the root config.yaml plus orchestrator sub-agent configs."""

    config: dict[str, Any]
    agents: dict[str, dict[str, Any]] = field(default_factory=dict)
    extensions: dict[str, Any] = field(default_factory=dict)
```
In `omnigent_migrate/exporter.py`, add the sidecar header constant next to `_HEADER`:
```python
_EXT_HEADER = (
    "# Carried from the source project by omnigent-migrate but with no Omnigent\n"
    "# bundle home. NOT loaded by Omnigent — a record so nothing is silently lost.\n"
    "# See MIGRATION_REPORT.md for the manual steps.\n"
)
```
Parametrize the writer's header (default unchanged) so it can also write the sidecar:
```python
def _write_yaml(path: Path, data: dict[str, Any], header: str = _HEADER) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    yaml = YAML()
    yaml.default_flow_style = False
    setattr(yaml, "sort_base_mapping_type_on_output", False)
    buf = io.StringIO()
    yaml.dump(data, buf)
    path.write_text(header + buf.getvalue())
```
In `export()`, after the `for name, cfg in bundle.agents.items(): ...` loop and **before** the omnigent import/validate block, add:
```python
    if bundle.extensions:
        _write_yaml(out_dir / "MIGRATION_EXTENSIONS.yaml", bundle.extensions, header=_EXT_HEADER)
```
- [ ] **Step 4:** `uv run pytest tests/test_ir.py tests/test_exporter.py -q` → PASS. Then `uv run pytest -q && uv run ruff check && uv run mypy omnigent_migrate` → all clean.
- [ ] **Step 5:** `git add -A && git commit -m "feat: Bundle.extensions + MIGRATION_EXTENSIONS.yaml sidecar"`. **STOP.**

---

### Task 2: extract shared importer helpers to `_util.py`

A pure refactor so `claude_code.py` and the new `claude_extras.py` share one copy of the frontmatter/sanitize/os_env helpers (avoids a circular import). No behavior change.

**Files:**
- Create: `omnigent_migrate/importers/_util.py`
- Modify: `omnigent_migrate/importers/claude_code.py`
- Test: existing `tests/test_claude_importer.py` must stay green (no new test).

**Interfaces:**
- Produces: `_util._sanitize(name) -> str`, `_util._frontmatter(text) -> tuple[dict[str, Any], str]`, `_util._os_env() -> dict[str, Any]`.

- [ ] **Step 1: Create** `omnigent_migrate/importers/_util.py` with the helpers moved verbatim from `claude_code.py`:
```python
"""Shared importer helpers (frontmatter parsing, name sanitizing, os_env)."""

from __future__ import annotations

import re
from typing import Any

from ruamel.yaml import YAML

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
```
- [ ] **Step 2: Edit** `omnigent_migrate/importers/claude_code.py`: delete its local `_yaml`, `_NAME_RE`, `_sanitize`, `_frontmatter`, `_os_env` definitions and the now-unused `import re` / `from ruamel.yaml import YAML`, and import them instead. The import block becomes:
```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from omnigent_migrate.harness_map import resolve_harness
from omnigent_migrate.importers._util import _frontmatter, _os_env, _sanitize
from omnigent_migrate.ir import Bundle
from omnigent_migrate.ledger import Ledger, Status
```
Leave the rest of `claude_code.py` unchanged (it already calls `_sanitize`/`_frontmatter`/`_os_env`).
- [ ] **Step 3:** `uv run pytest -q` → PASS (unchanged behavior). Then `uv run ruff check && uv run mypy omnigent_migrate` → clean (ruff will confirm no unused imports remain).
- [ ] **Step 4:** `git add -A && git commit -m "refactor: share importer helpers via importers/_util.py"`. **STOP.**

---

### Task 3: `claude_extras.py` — permissions → approximate guardrail (DEGRADED)

**Files:**
- Create: `omnigent_migrate/importers/claude_extras.py`
- Test: `tests/test_claude_extras.py`

**Interfaces:**
- Produces:
  - `read_settings(project: Path) -> dict[str, Any]` — shallow-merge `.claude/settings.json` then `.claude/settings.local.json` (later wins); `{}` if absent/invalid.
  - `collect_permissions(settings: dict[str, Any], ledger: Ledger) -> tuple[dict[str, Any] | None, Any]` — returns `(guardrails_block | None, raw_permissions | None)`; records a DEGRADED `permissions` entry when present.

- [ ] **Step 1: Failing test** (`tests/test_claude_extras.py`):
```python
from pathlib import Path

from omnigent_migrate.exporter import export
from omnigent_migrate.importers.claude_extras import collect_permissions, read_settings
from omnigent_migrate.ir import Bundle
from omnigent_migrate.ledger import Ledger, Status


def test_collect_permissions_emits_blast_radius() -> None:
    led = Ledger()
    settings = {"permissions": {"allow": ["Read"], "deny": ["Bash(rm:*)"], "defaultMode": "acceptEdits"}}
    guardrails, perms = collect_permissions(settings, led)
    assert guardrails is not None
    path = guardrails["policies"]["blast_radius"]["function"]["path"]
    assert path == "omnigent.inner.nessie.policies.blast_radius"
    assert perms == settings["permissions"]
    assert any(e.primitive == "permissions" and e.status is Status.DEGRADED for e in led.entries)


def test_collect_permissions_absent_is_noop() -> None:
    led = Ledger()
    guardrails, perms = collect_permissions({}, led)
    assert guardrails is None and perms is None
    assert led.entries == []


def test_emitted_guardrail_actually_validates(tmp_path: Path) -> None:
    led = Ledger()
    guardrails, _ = collect_permissions({"permissions": {"deny": ["Bash(rm:*)"]}}, led)
    bundle = Bundle(config={
        "spec_version": 1, "name": "demo", "description": "d",
        "executor": {"type": "omnigent", "config": {"harness": "claude-sdk"}},
        "prompt": "You are a coding agent.\n",
        "os_env": {"type": "caller_process", "cwd": ".", "sandbox": {"type": "none"}},
        "guardrails": guardrails,
    })
    export(bundle, tmp_path / "b")  # raises ExportInvalid if the real loader rejects the guardrail


def test_read_settings_merges_local(tmp_path: Path) -> None:
    cdir = tmp_path / ".claude"
    cdir.mkdir()
    (cdir / "settings.json").write_text('{"permissions": {"allow": ["Read"]}}')
    (cdir / "settings.local.json").write_text('{"enabledPlugins": {"x@y": true}}')
    s = read_settings(tmp_path)
    assert s["permissions"]["allow"] == ["Read"]
    assert s["enabledPlugins"] == {"x@y": True}
```
- [ ] **Step 2:** `uv run pytest tests/test_claude_extras.py -q` → FAIL (no module).
- [ ] **Step 3: Implement** `omnigent_migrate/importers/claude_extras.py`:
```python
"""Claude Code primitives with no direct AgentSpec field: permissions, hooks,
slash-commands, plugins. Each is recorded in the ledger; carried values become
the bundle's MigrationExtensions sidecar. Permissions additionally yield an
approximate `blast_radius` guardrail (the only one backed by a real handler)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from omnigent_migrate.ledger import Ledger, Status

# The single Omnigent builtin guardrail we can safely emit: it references a real
# handler (omnigent.inner.nessie.policies.blast_radius) and validates at load.
_BLAST_RADIUS_PATH = "omnigent.inner.nessie.policies.blast_radius"


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


def collect_permissions(
    settings: dict[str, Any], ledger: Ledger
) -> tuple[dict[str, Any] | None, Any]:
    """Map Claude `permissions` to an approximate blast_radius guardrail.

    Returns (guardrails_block | None, raw_permissions | None). The precise
    allow/deny rules are NOT auto-enforced (no Omnigent handler does that) — they
    are carried in the sidecar and flagged DEGRADED with a manual step.
    """
    perms = settings.get("permissions")
    if not perms:
        return None, None
    guardrails: dict[str, Any] = {
        "policies": {
            "blast_radius": {
                "type": "function",
                "function": {"path": _BLAST_RADIUS_PATH},
            }
        }
    }
    ledger.record(
        "permissions",
        ".claude/settings.json",
        Status.DEGRADED,
        "approximated with the blast_radius guardrail (a catastrophic-command DENY "
        "set); your specific allow/deny rules are NOT auto-enforced",
        "review the carried rules in MIGRATION_EXTENSIONS.yaml and translate them to "
        "Omnigent policies if you need exact enforcement",
    )
    return guardrails, perms
```
- [ ] **Step 4:** `uv run pytest tests/test_claude_extras.py -q` → PASS (4 tests). Then `uv run pytest -q && uv run ruff check && uv run mypy omnigent_migrate` → clean.
- [ ] **Step 5:** `git add -A && git commit -m "feat: permissions -> approximate blast_radius guardrail (DEGRADED)"`. **STOP.**

---

### Task 4: hooks / slash-commands / plugins collectors + coordinator

**Files:**
- Modify: `omnigent_migrate/importers/claude_extras.py`
- Test: `tests/test_claude_extras.py`

**Interfaces:**
- Consumes: `_util._frontmatter`; `read_settings`/`collect_permissions` from Task 3.
- Produces:
  - `collect_hooks(settings, ledger) -> dict[str, Any] | None` (records UNSUPPORTED).
  - `collect_commands(project, ledger) -> list[dict[str, Any]] | None` (records DEGRADED).
  - `collect_plugins(project, settings, ledger) -> dict[str, Any] | None` (records DEGRADED).
  - `collect_claude_extras(project, config, ledger) -> dict[str, Any]` — coordinator: mutates `config` (adds `guardrails` when permissions present) and returns the `extensions` dict.

- [ ] **Step 1: Failing test.** Append to `tests/test_claude_extras.py`:
```python
from omnigent_migrate.importers.claude_extras import (
    collect_claude_extras,
    collect_commands,
    collect_hooks,
    collect_plugins,
)


def test_collect_hooks_unsupported() -> None:
    led = Ledger()
    settings = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "x"}]}]}}
    hooks = collect_hooks(settings, led)
    assert hooks == settings["hooks"]
    e = next(e for e in led.entries if e.primitive == "hooks")
    assert e.status is Status.UNSUPPORTED and e.manual_step


def test_collect_commands_degraded(tmp_path: Path) -> None:
    cdir = tmp_path / ".claude" / "commands"
    cdir.mkdir(parents=True)
    (cdir / "deploy.md").write_text("---\ndescription: Deploy it\n---\nRun the deploy steps.\n")
    led = Ledger()
    cmds = collect_commands(tmp_path, led)
    assert cmds is not None and cmds[0]["name"] == "deploy"
    assert cmds[0]["description"] == "Deploy it"
    assert "deploy steps" in cmds[0]["body"]
    assert any(e.primitive == "slash_commands" and e.status is Status.DEGRADED for e in led.entries)


def test_collect_plugins_degraded(tmp_path: Path) -> None:
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "plugin.json").write_text("{}")
    led = Ledger()
    info = collect_plugins(tmp_path, {"enabledPlugins": {"a@b": True}}, led)
    assert info is not None and info["enabledPlugins"] == {"a@b": True}
    assert "plugin.json" in info["plugin_definition"]
    assert any(e.primitive == "plugins" and e.status is Status.DEGRADED for e in led.entries)


def test_coordinator_attaches_guardrail_and_returns_extensions(tmp_path: Path) -> None:
    cdir = tmp_path / ".claude"
    cdir.mkdir()
    (cdir / "settings.json").write_text(
        '{"permissions": {"deny": ["Bash(rm:*)"]}, '
        '"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "x"}]}]}}'
    )
    led = Ledger()
    config: dict[str, object] = {"name": "demo"}
    ext = collect_claude_extras(tmp_path, config, led)
    assert config["guardrails"]["policies"]["blast_radius"]["function"]["path"]  # attached
    assert ext["permissions"]["deny"] == ["Bash(rm:*)"]
    assert "hooks" in ext
```
- [ ] **Step 2:** `uv run pytest tests/test_claude_extras.py -q` → FAIL (no such functions).
- [ ] **Step 3: Implement.** Add to `omnigent_migrate/importers/claude_extras.py` — extend the imports and append the functions:
```python
# add to the import block:
from omnigent_migrate.importers._util import _frontmatter
```
```python
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


def collect_claude_extras(
    project: Path, config: dict[str, Any], ledger: Ledger
) -> dict[str, Any]:
    """Parse settings/commands/plugins; mutate `config` with a guardrail when
    permissions are present; return the MigrationExtensions sidecar dict."""
    settings = read_settings(project)
    extensions: dict[str, Any] = {}
    guardrails, perms = collect_permissions(settings, ledger)
    if guardrails is not None:
        config["guardrails"] = guardrails
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
```
- [ ] **Step 4:** `uv run pytest tests/test_claude_extras.py -q` → PASS (8 tests). Then `uv run pytest -q && uv run ruff check && uv run mypy omnigent_migrate` → clean.
- [ ] **Step 5:** `git add -A && git commit -m "feat: hooks/commands/plugins collectors + extras coordinator"`. **STOP.**

---

### Task 5: wire the extras into the Claude importer + enrich the fixture

**Files:**
- Modify: `omnigent_migrate/importers/claude_code.py`
- Modify: `tests/fixtures/claude_project/` (add settings.json, a command, a plugin def)
- Modify: `tests/test_claude_importer.py`

**Interfaces:**
- Consumes: `collect_claude_extras` (Task 4); `Bundle(config, agents, extensions)` (Task 1).

- [ ] **Step 1: Enrich the fixture** (a Claude project that exercises all four primitives):
```bash
cd /Users/bryanli/Projects/btli/omnigent-migrate
mkdir -p tests/fixtures/claude_project/.claude/commands tests/fixtures/claude_project/.claude-plugin
printf '{\n  "permissions": {"allow": ["Read", "Bash(git:*)"], "deny": ["Bash(rm:*)"], "defaultMode": "acceptEdits"},\n  "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo guard", "timeout": 5}]}]},\n  "enabledPlugins": {"superpowers@official": true}\n}\n' > tests/fixtures/claude_project/.claude/settings.json
printf -- '---\ndescription: Deploy the app\nallowed-tools: Bash, Read\n---\nRun the deploy checklist step by step.\n' > tests/fixtures/claude_project/.claude/commands/deploy.md
printf '{"name": "demo-plugin", "version": "0.1.0"}\n' > tests/fixtures/claude_project/.claude-plugin/plugin.json
```
- [ ] **Step 2: Failing test.** In `tests/test_claude_importer.py`, replace the scope-note assertion line (`assert any("Hooks" in n for n in led.notes)`) and extend `test_imports_core_primitives` with:
```python
    # Plan 2: deferred primitives now examined
    assert bundle.config["guardrails"]["policies"]["blast_radius"]["function"]["path"]
    assert bundle.extensions["permissions"]["deny"] == ["Bash(rm:*)"]
    assert "hooks" in bundle.extensions
    assert bundle.extensions["commands"][0]["name"] == "deploy"
    assert bundle.extensions["plugins"]["enabledPlugins"] == {"superpowers@official": True}
    by_primitive = {e.primitive: e.status for e in led.entries}
    assert by_primitive["permissions"] is Status.DEGRADED
    assert by_primitive["hooks"] is Status.UNSUPPORTED
    assert by_primitive["slash_commands"] is Status.DEGRADED
    assert by_primitive["plugins"] is Status.DEGRADED
```
- [ ] **Step 3:** `uv run pytest tests/test_claude_importer.py -q` → FAIL (importer doesn't call extras yet).
- [ ] **Step 4: Implement.** In `omnigent_migrate/importers/claude_code.py`:
  1. Add the import: `from omnigent_migrate.importers.claude_extras import collect_claude_extras`.
  2. **Replace** the existing scope-note block (the `ledger.note("This importer scanned ... NOT yet examined ...")` call added in Plan 1) with the extras call + an accurate note, immediately before `return Bundle(...)`:
```python
        extensions = collect_claude_extras(project, config, ledger)
        ledger.note(
            "Scanned: memory, sub-agents, MCP, skills, permissions, hooks, "
            "slash-commands, plugins. Items not representable in the bundle are "
            "recorded above (DEGRADED/UNSUPPORTED) and carried in "
            "MIGRATION_EXTENSIONS.yaml — nothing was dropped."
        )
        return Bundle(config=config, agents=agents, extensions=extensions)
```
  (Delete the old `ledger.note(...)` text so it isn't duplicated.)
- [ ] **Step 5:** `uv run pytest -q` → PASS (all). `uv run ruff check && uv run mypy omnigent_migrate` → clean.
- [ ] **Step 6:** `git add -A && git commit -m "feat: Claude importer covers permissions/hooks/commands/plugins"`. **STOP.**

---

### Task 6: golden-report integration test

**Files:**
- Test: `tests/test_integration_claude.py` (extend)

**Interfaces:**
- Consumes: the full importer + exporter on the enriched fixture (Task 5).

- [ ] **Step 1: Failing test.** Append to `tests/test_integration_claude.py`:
```python
def test_enriched_fixture_full_fidelity(tmp_path: Path) -> None:
    led = Ledger()
    bundle = ClaudeCodeImporter().to_bundle(FIXTURE, led)
    out = export(bundle, tmp_path / "b")  # raises if the guardrail/bundle is invalid
    # sidecar carries the un-mapped primitives
    sidecar = out / "MIGRATION_EXTENSIONS.yaml"
    assert sidecar.is_file()
    text = sidecar.read_text()
    assert "permissions" in text and "hooks" in text and "commands" in text
    # golden: status per deferred primitive
    by_primitive = {e.primitive: e.status.value for e in led.entries}
    assert by_primitive["permissions"] == "degraded"
    assert by_primitive["hooks"] == "unsupported"
    assert by_primitive["slash_commands"] == "degraded"
    assert by_primitive["plugins"] == "degraded"
    # report renders all three status sections + the scope note
    report = led.render_markdown()
    assert "## Translated" in report and "## Degraded" in report and "## Unsupported" in report
    assert "## Scope" in report
```
- [ ] **Step 2:** `uv run pytest tests/test_integration_claude.py -q` → should PASS already (all parts built in Tasks 1–5). If `export` raises `ExportInvalid`, the emitted `guardrails` shape drifted from the verified minimal form — re-check against the "Verified facts" block, fix `collect_permissions`, re-run.
- [ ] **Step 3: Real-world smoke (best-effort).** Confirm the new coverage on a real project that has hooks + plugins + commands:
```bash
cd /Users/bryanli/Projects/btli/omnigent-migrate
uv run omnigent-migrate from-claude /Users/bryanli/Projects/askcv.ai -o /tmp/askcv-omnigent2
cat /tmp/askcv-omnigent2/MIGRATION_REPORT.md
ls /tmp/askcv-omnigent2/MIGRATION_EXTENSIONS.yaml
```
Expected: a validated bundle; the report now shows `hooks` UNSUPPORTED, `slash_commands`/`plugins` DEGRADED (askcv has all three), and a sidecar exists. Record the report summary in the commit message.
- [ ] **Step 4:** `git add -A && git commit -m "test: golden-report + sidecar fidelity on the enriched fixture"`. **STOP.**

---

## Self-Review

**Spec coverage (§6 deferred rows):** permissions→guardrails DEGRADED → Task 3 ✓ · hooks→UNSUPPORTED+carry → Task 4 ✓ · slash-commands→DEGRADED+carry → Task 4 ✓ · plugins→DEGRADED+carry → Task 4 ✓ · `MigrationExtensions` sidecar (§5) → Task 1 ✓ · golden report (§12) → Task 6 ✓ · wired + fixture → Task 5 ✓. **Honesty fix:** the Plan 1 scope note ("NOT yet examined") is replaced with an accurate one (Task 5). **Deferred (not gaps):** deep plugin expansion (spec §16 follow-on), command→skill auto-generation (invasive; manual step instead), Codex importer (Plan 3), round-trip tests (Plan 3+).

**Placeholder scan:** none — every step has complete code/commands and expected output. Recovery cited in Task 6 Step 2.

**Type consistency:** `read_settings(project)->dict`, `collect_permissions(settings,ledger)->(dict|None, Any)`, `collect_hooks(settings,ledger)->dict|None`, `collect_commands(project,ledger)->list[dict]|None`, `collect_plugins(project,settings,ledger)->dict|None`, `collect_claude_extras(project,config,ledger)->dict`, `Bundle(config,agents,extensions)`, `_write_yaml(path,data,header=...)`, `_util._frontmatter/_sanitize/_os_env` — used consistently across tasks. The emitted `guardrails` shape matches the spike-verified minimal form exactly.

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-06-18-accelerator-plan-2-claude-coverage.md`. Builds on `feat/mvp` (Plan 1). Subagent-driven execution with a strict one-task-per-subagent rule (the Plan 1 implementer overran its scope; each Task here ends with **STOP**), two-stage review between tasks.
