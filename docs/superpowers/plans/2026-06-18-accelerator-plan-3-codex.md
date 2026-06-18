# Omnigent Migration Accelerator — Plan 3 (Codex importer)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. **Hard scope rule: implement ONLY the task you were dispatched for, commit it, then STOP** (the workflow requires a review between tasks; a prior implementer overran scope and caused problems).

**Goal:** Add a `from-codex` importer that turns a Codex setup (project `AGENTS.md` + global `~/.codex/config.toml`) into a **validated** Omnigent **solo** bundle + a fidelity report — the "Codex to framework" half of the original ask, proving the IR/exporter/ledger generalize beyond Claude.

**Architecture:** Same lenient-in / strict-out loop. A new `importers/codex.py` reads `AGENTS.md` (prompt) and the global `config.toml` (model → `executor.model` + harness, `model_context_window` → `executor.context_window`, `[mcp_servers.*]` → `tools.<name>`). Codex config is **global**, so the importer takes a `config_path` (default `~/.codex/config.toml`). Approval/sandbox settings are carried DEGRADED in the sidecar (Omnigent agents run sandboxed by design — the Plan 2 carry-only philosophy). Codex is single-agent → a **solo** bundle (no `agents/`, no `spawn`).

**Tech Stack:** Python 3.13, `uv`, `click`, `ruamel.yaml`, stdlib **`tomllib`** (no new dependency), `pytest`, `ruff`, `mypy`; `omnigent` (editable) for validation. Build on `feat/mvp` (Plans 1+2 committed).

**Spec:** `docs/superpowers/specs/2026-06-18-migration-accelerator-design.md` §7 (Codex importer), §8 (harness map), §10 (CLI).

## Global Constraints

- `uv` only (`uv run pytest`, `uv run ruff check`, `uv run mypy omnigent_migrate`). NEVER pip/python.
- NEVER disable a linter/type check (`# noqa`, `# type: ignore`).
- Strict TDD: failing test first → watch fail → implement → watch pass → commit.
- `mypy --strict` clean. IR is the **public bundle-config dict**; emit no Omnigent-internal handler paths into `config.yaml`.
- **Lenient-in from the start:** every file/TOML read is guarded (a Plan 2 review caught an unguarded parser that crashed the whole import — do not repeat it). Wrap reads in `try/except` and record a ledger entry instead of raising.

**Verified facts (spike-confirmed against the real `omnigent.spec.load`; do not re-derive):**
- The migrated solo-Codex bundle shape **validates** and **captures** model/context_window/harness/tools:
  ```yaml
  spec_version: 1
  name: <project>
  description: "Migrated from Codex: <project>"
  executor:
    type: omnigent
    model: gpt-5.5            # executor.model — top-level of executor (NOT under config)
    context_window: 1000000   # executor.context_window — optional, top-level
    config:
      harness: codex
  prompt: <AGENTS.md text>
  async: true
  cancellable: true
  os_env: {type: caller_process, cwd: ., sandbox: {type: none}}
  tools:                       # optional
    <name>: {type: mcp, command: ..., args: [...], env: {...}}
  ```
  `omnigent/spec/types.py:535` confirms `ExecutorSpec.model` is "populated by the parser from the `executor.model` YAML key." Putting `model` under `config` silently drops it.
- Harnesses `codex`, `codex-native`, and `openai-agents` all validate for a solo bundle. This plan emits **`codex`** (the output of `resolve_harness(model, "codex")`, consistent with the existing map and the Claude importer's pattern).
- The real `~/.codex/config.toml` is **global** with top-level `model`, `model_context_window`, `model_reasoning_effort`, `approvals_reviewer`; `[mcp_servers.<name>]` (command/args/env or url/headers, same shape as Claude `mcpServers`); `[profiles.<name>]`; `[projects."<path>"]` trust tables; `[tui]`; `[apps.connector_<id>...]`. A project's instructions live in its `AGENTS.md` (plain markdown, no frontmatter).
- Extra files in the bundle dir (`MIGRATION_REPORT.md`, `MIGRATION_EXTENSIONS.yaml`) are ignored by the loader (proven in Plans 1–2).

---

### Task 1: extract `mcp_tool_entry` to `_util.py` (shared by both importers)

A small refactor so the Codex importer reuses the Claude importer's MCP-entry builder (identical command/args/env|url/headers shape). No behavior change.

**Files:**
- Modify: `omnigent_migrate/importers/_util.py`
- Modify: `omnigent_migrate/importers/claude_code.py`
- Test: existing `tests/test_claude_importer.py` stays green (no new test).

**Interfaces:**
- Produces: `_util.mcp_tool_entry(cfg: dict[str, Any]) -> dict[str, Any]` — `{type: mcp, ...}` from a single MCP server config.

- [ ] **Step 1: Add to `omnigent_migrate/importers/_util.py`:**
```python
def mcp_tool_entry(cfg: dict[str, Any]) -> dict[str, Any]:
    """Build an Omnigent `tools.<name>` MCP entry from a source MCP server config.

    Handles both Claude JSON `mcpServers` and Codex `[mcp_servers.*]` — they share the
    command/args/env (stdio) and url/headers (http) shape.
    """
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
    return entry
```
- [ ] **Step 2: Edit `omnigent_migrate/importers/claude_code.py`:** import it (`from omnigent_migrate.importers._util import _frontmatter, _os_env, _sanitize, mcp_tool_entry`) and replace the inline entry-building block inside the `for sname, cfg in servers.items():` loop with:
```python
                mcp_tools[_sanitize(sname)] = mcp_tool_entry(cfg)
                ledger.record("mcp_server", f"{mcp_file}:{sname}", Status.TRANSLATED)
```
(Delete the old `entry: dict[str, Any] = {"type": "mcp"} … mcp_tools[_sanitize(sname)] = entry` lines.)
- [ ] **Step 3:** `uv run pytest -q` → PASS (unchanged behavior; `test_imports_core_primitives` still asserts the github mcp entry). `uv run ruff check && uv run mypy omnigent_migrate` → clean.
- [ ] **Step 4:** `git add -A && git commit -m "refactor: share mcp_tool_entry via importers/_util.py"`. **STOP.**

---

### Task 2: `CodexImporter` (full) + fixture + unit tests

**Files:**
- Create: `omnigent_migrate/importers/codex.py`
- Create fixture: `tests/fixtures/codex_project/AGENTS.md`, `tests/fixtures/codex_project/config.toml`
- Test: `tests/test_codex_importer.py`

**Interfaces:**
- Consumes: `resolve_harness` (harness_map), `_util._os_env`/`_sanitize`/`mcp_tool_entry`, `ir.Bundle`, `ledger`.
- Produces: `class CodexImporter` with `name = "codex"`, `detect(project: Path) -> bool`, and `to_bundle(project: Path, ledger: Ledger, config_path: Path | None = None) -> Bundle`.

- [ ] **Step 1: Build the fixture:**
```bash
cd /Users/bryanli/Projects/btli/omnigent-migrate
mkdir -p tests/fixtures/codex_project
printf 'You are the lead for the demo Codex app. Use uv and pytest.\n' > tests/fixtures/codex_project/AGENTS.md
cat > tests/fixtures/codex_project/config.toml <<'TOML'
model = "gpt-5.5"
model_context_window = 1000000
model_reasoning_effort = "xhigh"
approval_policy = "on-request"
sandbox_mode = "workspace-write"
approvals_reviewer = "user"

[mcp_servers.github]
command = "npx"
args = ["-y", "@modelcontextprotocol/server-github"]
env = { GITHUB_TOKEN = "x" }

[apps.connector_abc.tools.create_issue]
approval_mode = "approve"
TOML
```
- [ ] **Step 2: Failing test** (`tests/test_codex_importer.py`):
```python
from pathlib import Path

from omnigent_migrate.importers.codex import CodexImporter
from omnigent_migrate.ledger import Ledger, Status

FIXTURE = Path(__file__).parent / "fixtures" / "codex_project"
CONFIG = FIXTURE / "config.toml"


def test_detect() -> None:
    assert CodexImporter().detect(FIXTURE) is True


def test_imports_codex_setup() -> None:
    led = Ledger()
    bundle = CodexImporter().to_bundle(FIXTURE, led, config_path=CONFIG)
    cfg = bundle.config
    # AGENTS.md -> prompt
    assert "lead for the demo Codex app" in cfg["prompt"]
    # model -> executor.model (top-level) + harness via resolve_harness
    assert cfg["executor"]["model"] == "gpt-5.5"
    assert cfg["executor"]["config"]["harness"] == "codex"
    assert cfg["executor"]["context_window"] == 1000000
    # solo bundle — no orchestrator shape
    assert "spawn" not in cfg
    assert bundle.agents == {}
    # mcp_servers -> tools.<name>
    assert cfg["tools"]["github"]["type"] == "mcp"
    assert cfg["tools"]["github"]["command"] == "npx"
    # approval/sandbox carried DEGRADED in the sidecar (sandbox is the boundary)
    assert bundle.extensions["approvals"]["approval_policy"] == "on-request"
    assert bundle.extensions["approvals"]["sandbox_mode"] == "workspace-write"
    by_primitive = {e.primitive: e.status for e in led.entries}
    assert by_primitive["model"] is Status.TRANSLATED
    assert by_primitive["mcp_server"] is Status.TRANSLATED
    assert by_primitive["approvals"] is Status.DEGRADED
    # connectors noted (not carried verbatim — may hold secrets)
    assert by_primitive["connectors"] is Status.DEGRADED


def test_missing_config_is_lenient(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("Be a good agent.\n")
    led = Ledger()
    bundle = CodexImporter().to_bundle(tmp_path, led, config_path=tmp_path / "nope.toml")
    assert "good agent" in bundle.config["prompt"]
    assert bundle.config["executor"]["config"]["harness"] == "codex"  # default codex harness
```
- [ ] **Step 3:** `uv run pytest tests/test_codex_importer.py -q` → FAIL (no module).
- [ ] **Step 4: Implement** `omnigent_migrate/importers/codex.py`:
```python
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
```
- [ ] **Step 5:** `uv run pytest tests/test_codex_importer.py -q` → PASS (3 tests). Then `uv run pytest -q && uv run ruff check && uv run mypy omnigent_migrate` → clean. (If mypy flags `CodexImporter` against the `Importer` Protocol because of the extra optional `config_path`, that is allowed — an implementation may add optional params; if it genuinely errors, give `config_path` a default and keep it keyword-only, do NOT `# type: ignore`.)
- [ ] **Step 6:** `git add -A && git commit -m "feat: Codex importer (AGENTS.md + config.toml -> solo bundle)"`. **STOP.**

---

### Task 3: `from-codex` CLI (+ `auto`) + integration test + smoke

**Files:**
- Modify: `omnigent_migrate/cli.py`
- Test: `tests/test_cli.py` (extend), `tests/test_integration_codex.py` (new)

**Interfaces:**
- Consumes: `CodexImporter` (Task 2), `export` (exporter), `Ledger`.
- Produces: `omnigent-migrate from-codex <project> [-o out] [--dry-run] [--config PATH]`; `omnigent-migrate auto <project> [-o out] [--dry-run]` (picks claude if `.claude/` present, else codex).

- [ ] **Step 1: Failing tests.** Append to `tests/test_cli.py`:
```python
CODEX_FIXTURE = Path(__file__).parent / "fixtures" / "codex_project"


def test_from_codex_writes_bundle(tmp_path: Path) -> None:
    out = tmp_path / "out"
    res = CliRunner().invoke(
        main,
        ["from-codex", str(CODEX_FIXTURE), "-o", str(out), "--config", str(CODEX_FIXTURE / "config.toml")],
    )
    assert res.exit_code == 0, res.output
    assert (out / "config.yaml").is_file()
    assert (out / "MIGRATION_REPORT.md").is_file()
    assert "translated" in res.output


def test_auto_picks_claude_for_dotclaude(tmp_path: Path) -> None:
    res = CliRunner().invoke(main, ["auto", str(FIXTURE), "-o", str(tmp_path / "o"), "--dry-run"])
    assert res.exit_code == 0, res.output
    assert "claude" in res.output.lower()
```
Create `tests/test_integration_codex.py`:
```python
from pathlib import Path

from omnigent_migrate.exporter import export
from omnigent_migrate.importers.codex import CodexImporter
from omnigent_migrate.ledger import Ledger

FIXTURE = Path(__file__).parent / "fixtures" / "codex_project"


def test_codex_fixture_migrates_to_a_valid_bundle(tmp_path: Path) -> None:
    led = Ledger()
    bundle = CodexImporter().to_bundle(FIXTURE, led, config_path=FIXTURE / "config.toml")
    out = export(bundle, tmp_path / "b")  # raises ExportInvalid if the real loader rejects it
    assert (out / "config.yaml").is_file()
    assert not (out / "agents").exists()  # solo bundle
    assert (out / "MIGRATION_EXTENSIONS.yaml").is_file()  # approvals carried
```
- [ ] **Step 2:** `uv run pytest tests/test_cli.py tests/test_integration_codex.py -q` → FAIL.
- [ ] **Step 3: Implement** in `omnigent_migrate/cli.py` — add the import and two commands. Add `from omnigent_migrate.importers.codex import CodexImporter` and the `Path`/click imports already present. Add:
```python
@main.command(name="from-codex")
@click.argument("project", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("-o", "--out", type=click.Path(file_okay=False, path_type=Path), default=None,
              help="Output bundle dir (default: <project>/.omnigent).")
@click.option("--config", "config_path", type=click.Path(path_type=Path), default=None,
              help="Codex config.toml (default: ~/.codex/config.toml).")
@click.option("--dry-run", is_flag=True, help="Render the fidelity report; emit no bundle.")
def from_codex(project: Path, out: Path | None, config_path: Path | None, dry_run: bool) -> None:
    """Import a Codex setup (AGENTS.md + config.toml) into an Omnigent bundle."""
    ledger = Ledger()
    bundle = CodexImporter().to_bundle(project, ledger, config_path=config_path)
    _emit(project, bundle, ledger, out, dry_run)


@main.command(name="auto")
@click.argument("project", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("-o", "--out", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option("--dry-run", is_flag=True)
def auto(project: Path, out: Path | None, dry_run: bool) -> None:
    """Detect the source framework and import (claude if .claude/ present, else codex)."""
    ledger = Ledger()
    if (project / ".claude").is_dir() or (project / "CLAUDE.md").is_file():
        click.echo("detected: claude")
        bundle = ClaudeCodeImporter().to_bundle(project, ledger)
    else:
        click.echo("detected: codex")
        bundle = CodexImporter().to_bundle(project, ledger)
    _emit(project, bundle, ledger, out, dry_run)
```
Then refactor the existing `from-claude` body and the new commands to share one emit helper. Replace the inner body of `from_claude` (everything after it builds `bundle`) with a call to `_emit`, and add the helper (place it above the commands):
```python
def _emit(project: Path, bundle: object, ledger: Ledger, out: Path | None, dry_run: bool) -> None:
    from omnigent_migrate.exporter import export
    from omnigent_migrate.ir import Bundle

    assert isinstance(bundle, Bundle)
    report_md = ledger.render_markdown()
    if dry_run:
        click.echo(f"DRY RUN  {project.name} (no files written)\n")
        click.echo(report_md)
    else:
        out_dir = out or (project / ".omnigent")
        export(bundle, out_dir)
        (out_dir / "MIGRATION_REPORT.md").write_text(report_md)
        click.echo(f"OK  migrated {project.name} -> {out_dir}")
        click.echo(f"  report: {out_dir / 'MIGRATION_REPORT.md'}")
    s = ledger.summary()
    click.echo(
        f"  {s[Status.TRANSLATED]} translated · {s[Status.DEGRADED]} degraded · "
        f"{s[Status.UNSUPPORTED]} unsupported"
    )
```
Update `from_claude` to build `bundle = ClaudeCodeImporter().to_bundle(project, ledger)` then `_emit(project, bundle, ledger, out, dry_run)`. Keep its existing options. The existing `test_cli.py` dry-run/non-dry-run assertions (`DRY RUN`, `# Migration Report`, `translated`, no source mutation) must still pass — `_emit` preserves that exact behavior.
- [ ] **Step 4:** `uv run pytest -q` → PASS (all, incl. the preserved Plan 1/2 CLI tests). `uv run ruff check && uv run mypy omnigent_migrate` → clean.
- [ ] **Step 5: Real-world smoke (best-effort):** Codex-migrate a real project that has `AGENTS.md`, using the real global config:
```bash
cd /Users/bryanli/Projects/btli/omnigent-migrate
uv run omnigent-migrate from-codex /Users/bryanli/Projects/btli/remote-dev -o /tmp/remote-dev-codex
cat /tmp/remote-dev-codex/config.yaml | head -20
cat /tmp/remote-dev-codex/MIGRATION_REPORT.md
```
Expected: a validated **solo** bundle (`executor.model: gpt-5.5`, `harness: codex`, `context_window` from the real config), prompt from remote-dev's `AGENTS.md`(+`CLAUDE.md`), `approvals` carried (the real config has `approvals_reviewer`). Record the report summary in the commit message. If it errors on a real edge, capture it — it's a real fidelity finding.
- [ ] **Step 6:** `git add -A && git commit -m "feat: from-codex + auto CLI commands (+ Codex integration test)"`. **STOP.**

---

## Self-Review

**Spec coverage (§7):** model+provider → `executor.model` + harness (Task 2) ✓ · `mcp_servers` → tools (Tasks 1+2) ✓ · AGENTS.md → prompt (Task 2) ✓ · approval/sandbox → DEGRADED carry (Task 2) ✓ · solo bundle (Task 2) ✓ · CLI from-codex + auto (Task 3) ✓ · validated end-to-end (Task 3 integration) ✓. **Deferred (not gaps):** Codex skills path, profiles, per-project trust, app-connector expansion, model-tuning keys (all noted/UNSUPPORTED, not silently dropped); round-trip tests.

**Placeholder scan:** none — full code/commands + expected output in every step.

**Type consistency:** `CodexImporter.detect/to_bundle(project, ledger, config_path=None)`, `_read_toml(path, ledger)->dict`, `_util.mcp_tool_entry(cfg)->dict`, `Bundle(config, agents, extensions)`, `_emit(project, bundle, ledger, out, dry_run)`, `resolve_harness(model, "codex")->("codex", note)`. The emitted executor places `model`/`context_window` at executor top-level (spike-confirmed captured) and `harness` under `config`.

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-06-18-accelerator-plan-3-codex.md`. Builds on `feat/mvp`. Subagent-driven, one-task-per-subagent with **STOP** after each, two-stage review between tasks, capable whole-branch review at the end.
