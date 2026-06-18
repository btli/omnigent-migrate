# Omnigent Migration Accelerator — Plan 1 (MVP)

**Status:** ✅ executed 2026-06-18 — all 8 tasks committed on `feat/mvp`. 12 tests green (ruff + `mypy --strict` clean). Validated end-to-end on the fixture **and two real projects**: `remote-dev` (7-subagent orchestrator → valid bundle) and `askcv.ai` (solo + 20 skills → valid bundle). **Two review-driven changes beyond the plan code:** (1) `--dry-run` now renders the report to stdout instead of writing `MIGRATION_REPORT.md` into the *source* project (it had been polluting the committed fixture on every test run); (2) the report carries a `## Scope` section disclosing that only memory / sub-agents / MCP / skills are scanned, so `0 unsupported` is not misleading. *(Process note: the implementer subagent overran its single-task scope and committed Tasks 2–8 in one run; every file was verified byte-for-byte against this plan and re-gated before acceptance.)*

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A working `omnigent-migrate from-claude <project>` that imports a Claude Code project's core primitives (memory, sub-agents, MCP, skills) into a **validated** Omnigent bundle + a fidelity report — proving the whole import→IR→export→validate loop.

**Architecture:** A standalone `uv` package. Importer parses the source → a `Bundle` (the public Omnigent config.yaml form) while recording fidelity in a `Ledger`. Exporter writes the bundle + validates it against the **real `omnigent.spec.load`** (lenient-in/strict-out). IR = the bundle config dict (NOT omnigent's internal `AgentSpec`), so we never reach into internal constructors.

**Tech Stack:** Python 3.13, `uv`, `click`, `ruamel.yaml`, `pytest`, `ruff`, `mypy`; `omnigent` (editable) for validation only.

**Spec:** `docs/superpowers/specs/2026-06-18-migration-accelerator-design.md`.

**Verified facts (don't re-derive):**
- Claude subagent `.claude/agents/*.md` = YAML frontmatter (`name`, `description`, `model`, `tools`, `skills`) + markdown body (the prompt).
- Claude `SKILL.md` = `name`/`description` frontmatter + body (≈ Omnigent's skill format; left in place, host-discovered at cwd=project).
- `omnigent.spec.load(Path(bundle), expand_env=False, enforce_handler_allowlist=False)` parses+validates a bundle dir (config.yaml + agents/) and raises `omnigent.errors.OmnigentError` on failure (proven in the fleet work).
- Validated bundle shape: `config.yaml` with `spec_version/name/description/executor{type:omnigent,config.harness}/prompt/os_env/...`; orchestrator adds `spawn:true` + `tools.agents` + `agents/<name>/config.yaml` sub-bundles.

**MVP scope:** memory + sub-agents + MCP + skills-in-place. **Deferred to Plan 2:** hooks, slash-commands→skills, plugins, permissions→guardrails. **Plan 3:** Codex importer.

---

### Task 0: Spike — confirm a *migrated-Claude-shaped* bundle validates

- [ ] **Step 1: Hand-write the shape the importer will produce** at `/tmp/mig-spike/config.yaml`:
```yaml
spec_version: 1
name: demo
description: Migrated from Claude Code demo.
spawn: true
executor:
  type: omnigent
  config:
    harness: claude-sdk
prompt: |
  You are the orchestrator for demo. Follow the repo conventions.
async: true
cancellable: true
os_env:
  type: caller_process
  cwd: .
  sandbox:
    type: none
tools:
  agents: [reviewer]
```
and `/tmp/mig-spike/agents/reviewer/config.yaml`:
```yaml
spec_version: 1
name: reviewer
description: reviewer sub-agent
executor:
  type: omnigent
  config:
    harness: claude-native
prompt: |
  You review diffs.
os_env:
  type: caller_process
  cwd: .
  sandbox:
    type: none
```
- [ ] **Step 2: Validate via the real loader**
```bash
PYBIN="$HOME/.local/share/uv/tools/omnigent/bin/python"
"$PYBIN" -c "from pathlib import Path; from omnigent.spec import load; s=load(Path('/tmp/mig-spike'), expand_env=False, enforce_handler_allowlist=False); print('OK', s.name, [a.name for a in s.sub_agents])"
```
Expected: `OK demo ['reviewer']`. If it fails, read the `path: message`, adjust the shape (and the importer's emitted dicts in Task 5), re-run until OK. Then `rm -rf /tmp/mig-spike`.

---

### Task 1: Scaffold `omnigent-migrate`

- [ ] **Step 1: Init**
```bash
mkdir -p /Users/bryanli/Projects/btli/omnigent-migrate
cd /Users/bryanli/Projects/btli/omnigent-migrate
git init && git checkout -b feat/mvp
uv init --package --python 3.13 --name omnigent-migrate .
```
- [ ] **Step 2: Overwrite `pyproject.toml`**
```toml
[project]
name = "omnigent-migrate"
version = "0.1.0"
description = "Migrate agent setups from Claude Code / Codex to Omnigent"
requires-python = ">=3.13"
dependencies = ["click>=8.1", "ruamel.yaml>=0.18"]

[project.scripts]
omnigent-migrate = "omnigent_migrate.cli:main"

[dependency-groups]
dev = ["pytest>=8.3", "mypy>=1.13", "ruff>=0.8"]

[tool.ruff]
target-version = "py313"
line-length = 100

[tool.mypy]
python_version = "3.13"
strict = true

[[tool.mypy.overrides]]
module = "omnigent.*"
ignore_missing_imports = true

[tool.uv.build-backend]
module-name = "omnigent_migrate"
module-root = ""

[build-system]
requires = ["uv_build>=0.5"]
build-backend = "uv_build"
```
- [ ] **Step 3:** Ensure flat layout: `omnigent_migrate/__init__.py` contains `"""omnigent-migrate — migrate agent setups to Omnigent."""\n__version__ = "0.1.0"`. Remove any `src/`. Create `.gitignore` with `.venv/ __pycache__/ *.pyc .mypy_cache/ .ruff_cache/ .pytest_cache/`.
- [ ] **Step 4:** `uv add --editable /Users/bryanli/Projects/btli/omnigent && uv sync` (fallback `uv add "omnigent"` if editable is slow). Verify: `uv run python -c "from omnigent.spec import load; print('ok')"`.
- [ ] **Step 5:** `git add -A && git commit -m "chore: scaffold omnigent-migrate"` on `feat/mvp`.

---

### Task 2: `ledger.py` — the fidelity engine

**Files:** Create `omnigent_migrate/ledger.py`; Test `tests/test_ledger.py`.

- [ ] **Step 1: Failing test** (`tests/test_ledger.py`):
```python
from omnigent_migrate.ledger import Ledger, Status


def test_record_summary_and_render() -> None:
    led = Ledger()
    led.record("memory", "CLAUDE.md", Status.TRANSLATED)
    led.record("hooks", "settings.json", Status.UNSUPPORTED, "no bundle-declarative hooks", "re-add hooks manually")
    assert led.summary() == {Status.TRANSLATED: 1, Status.DEGRADED: 0, Status.UNSUPPORTED: 1}
    md = led.render_markdown()
    assert "1 translated" in md and "1 unsupported" in md
    assert "**memory** (CLAUDE.md)" in md
    assert "Manual: re-add hooks manually" in md
```
- [ ] **Step 2:** `uv run pytest tests/test_ledger.py -v` → FAIL (no module).
- [ ] **Step 3: Implement** `omnigent_migrate/ledger.py`:
```python
"""Fidelity ledger: record per-primitive translation decisions + render the report."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    TRANSLATED = "translated"
    DEGRADED = "degraded"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class LedgerEntry:
    primitive: str
    source_ref: str
    status: Status
    note: str = ""
    manual_step: str = ""


@dataclass
class Ledger:
    entries: list[LedgerEntry] = field(default_factory=list)

    def record(
        self,
        primitive: str,
        source_ref: str,
        status: Status,
        note: str = "",
        manual_step: str = "",
    ) -> None:
        self.entries.append(LedgerEntry(primitive, source_ref, status, note, manual_step))

    def summary(self) -> dict[Status, int]:
        out = {s: 0 for s in Status}
        for e in self.entries:
            out[e.status] += 1
        return out

    def render_markdown(self) -> str:
        s = self.summary()
        lines = [
            "# Migration Report",
            "",
            f"**{s[Status.TRANSLATED]} translated · {s[Status.DEGRADED]} degraded · "
            f"{s[Status.UNSUPPORTED]} unsupported**",
            "",
        ]
        for status in Status:
            rows = [e for e in self.entries if e.status is status]
            if not rows:
                continue
            lines.append(f"## {status.value.title()}")
            for e in rows:
                line = f"- **{e.primitive}** ({e.source_ref})"
                if e.note:
                    line += f" — {e.note}"
                lines.append(line)
                if e.manual_step:
                    lines.append(f"  - Manual: {e.manual_step}")
            lines.append("")
        return "\n".join(lines)
```
- [ ] **Step 4:** `uv run pytest tests/test_ledger.py -v` → PASS. Then `uv run ruff check && uv run mypy omnigent_migrate`.
- [ ] **Step 5:** `git add -A && git commit -m "feat: fidelity ledger"`.

---

### Task 3: `harness_map.py` — model → harness

**Files:** Create `omnigent_migrate/harness_map.py`; Test `tests/test_harness_map.py`.

- [ ] **Step 1: Failing test:**
```python
from omnigent_migrate.harness_map import resolve_harness


def test_resolve_harness() -> None:
    assert resolve_harness("claude-opus-4-8", "claude_code") == ("claude-sdk", None)
    assert resolve_harness("sonnet", "claude_code") == ("claude-sdk", None)
    assert resolve_harness("gpt-5.5", "codex") == ("codex", None)
    h, note = resolve_harness("gemini-3-pro", "claude_code")
    assert h == "antigravity" and note and "gated" in note
    h, note = resolve_harness(None, "codex")
    assert h == "codex" and note
    h, note = resolve_harness("llama-3", "claude_code")
    assert h == "pi" and note
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implement** `omnigent_migrate/harness_map.py`:
```python
"""Map a source model string to an Omnigent harness (a fidelity surface)."""

from __future__ import annotations


def resolve_harness(model: str | None, source: str) -> tuple[str, str | None]:
    """Return (harness, note); note is None only when the mapping is unambiguous."""
    m = (model or "").lower()
    if not m:
        default = "codex" if source == "codex" else "claude-sdk"
        return default, f"no model specified; defaulted to {default}"
    if any(k in m for k in ("claude", "sonnet", "opus", "haiku")) or m.startswith("anthropic"):
        return "claude-sdk", None
    if m.startswith(("gpt", "o1", "o3", "o4")) or "codex" in m:
        return "codex", None
    if "gemini" in m or "antigravity" in m:
        return "antigravity", "antigravity harness is gated until feat/antigravity ships"
    return "pi", f"unrecognized model {model!r}; routed to pi (multi-model gateway) — verify"
```
- [ ] **Step 4:** run → PASS; ruff + mypy clean.
- [ ] **Step 5:** `git commit -am "feat: model->harness mapping"`.

---

### Task 4: `ir.py` — the Bundle IR

**Files:** Create `omnigent_migrate/ir.py`; Test `tests/test_ir.py`.

- [ ] **Step 1: Failing test:**
```python
from omnigent_migrate.ir import Bundle


def test_bundle_defaults() -> None:
    b = Bundle(config={"name": "x"})
    assert b.config["name"] == "x"
    assert b.agents == {}
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implement** `omnigent_migrate/ir.py`:
```python
"""IR = the public Omnigent bundle config (the config.yaml form omnigent.spec.load validates)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Bundle:
    """A migrated bundle: the root config.yaml plus orchestrator sub-agent configs."""

    config: dict[str, Any]
    agents: dict[str, dict[str, Any]] = field(default_factory=dict)
```
- [ ] **Step 4:** run → PASS; ruff + mypy clean.
- [ ] **Step 5:** `git commit -am "feat: Bundle IR"`.

---

### Task 5: Claude Code importer (core primitives)

**Files:** Create `omnigent_migrate/importers/__init__.py` (empty), `omnigent_migrate/importers/base.py`, `omnigent_migrate/importers/claude_code.py`; Test `tests/test_claude_importer.py` + fixture under `tests/fixtures/claude_project/`.

- [ ] **Step 1: Build the fixture project** (a Claude Code project on disk):
```bash
cd /Users/bryanli/Projects/btli/omnigent-migrate
mkdir -p tests/fixtures/claude_project/.claude/agents tests/fixtures/claude_project/.claude/skills/debugging
printf 'You are the lead for the demo app. Use uv and pytest.\n' > tests/fixtures/claude_project/CLAUDE.md
printf -- '---\nname: reviewer\ndescription: Reviews diffs\nmodel: sonnet\ntools: Bash\n---\nYou review diffs against the contract. Report issues only.\n' > tests/fixtures/claude_project/.claude/agents/reviewer.md
printf -- '---\nname: debugging\ndescription: debugging skill\n---\nbody\n' > tests/fixtures/claude_project/.claude/skills/debugging/SKILL.md
printf '{\n  "mcpServers": {\n    "github": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"], "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"}}\n  }\n}\n' > tests/fixtures/claude_project/.mcp.json
```
- [ ] **Step 2: Failing test** (`tests/test_claude_importer.py`):
```python
from pathlib import Path

from omnigent_migrate.importers.claude_code import ClaudeCodeImporter
from omnigent_migrate.ledger import Ledger, Status

FIXTURE = Path(__file__).parent / "fixtures" / "claude_project"


def test_imports_core_primitives() -> None:
    led = Ledger()
    bundle = ClaudeCodeImporter().to_bundle(FIXTURE, led)
    # memory -> prompt
    assert "lead for the demo app" in bundle.config["prompt"]
    # subagent -> agents/ + tools.agents + spawn (orchestrator shape)
    assert "reviewer" in bundle.agents
    assert bundle.agents["reviewer"]["executor"]["config"]["harness"] == "claude-sdk"  # sonnet -> claude-sdk
    assert bundle.config["spawn"] is True
    assert bundle.config["tools"]["agents"] == ["reviewer"]
    # MCP server -> tools.<name>
    assert bundle.config["tools"]["github"]["type"] == "mcp"
    assert bundle.config["tools"]["github"]["command"] == "npx"
    # skills recorded as translated-in-place
    statuses = {(e.primitive, e.status) for e in led.entries}
    assert ("skills", Status.TRANSLATED) in statuses
    assert ("subagent", Status.TRANSLATED) in statuses


def test_detect() -> None:
    assert ClaudeCodeImporter().detect(FIXTURE) is True
```
- [ ] **Step 3:** run → FAIL (no module).
- [ ] **Step 4: Implement** `omnigent_migrate/importers/base.py`:
```python
"""Importer contract."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from omnigent_migrate.ir import Bundle
from omnigent_migrate.ledger import Ledger


class Importer(Protocol):
    name: str

    def detect(self, project: Path) -> bool: ...

    def to_bundle(self, project: Path, ledger: Ledger) -> Bundle: ...
```
Then `omnigent_migrate/importers/claude_code.py`:
```python
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
```
- [ ] **Step 5:** run → PASS (2 tests); ruff + mypy clean.
- [ ] **Step 6:** `git add -A && git commit -m "feat: Claude Code importer (core primitives)"`.

---

### Task 6: `exporter.py` — write + validate

**Files:** Create `omnigent_migrate/exporter.py`; Test `tests/test_exporter.py`.

- [ ] **Step 1: Failing test:**
```python
from pathlib import Path

import pytest

from omnigent_migrate.exporter import ExportInvalid, export
from omnigent_migrate.ir import Bundle


def _solo() -> Bundle:
    return Bundle(config={
        "spec_version": 1, "name": "demo", "description": "d",
        "executor": {"type": "omnigent", "config": {"harness": "claude-native"}},
        "prompt": "You are a coding agent.\n",
        "os_env": {"type": "caller_process", "cwd": ".", "sandbox": {"type": "none"}},
    })


def test_export_solo_validates(tmp_path: Path) -> None:
    out = export(_solo(), tmp_path / "bundle")
    assert (out / "config.yaml").is_file()
    text = (out / "config.yaml").read_text()
    assert text.startswith("# GENERATED by omnigent-migrate")


def test_export_orchestrator_with_agents(tmp_path: Path) -> None:
    b = _solo()
    b.config["spawn"] = True
    b.config["tools"] = {"agents": ["reviewer"]}
    b.agents["reviewer"] = {
        "spec_version": 1, "name": "reviewer", "description": "r",
        "executor": {"type": "omnigent", "config": {"harness": "claude-native"}},
        "prompt": "You review diffs.\n",
        "os_env": {"type": "caller_process", "cwd": ".", "sandbox": {"type": "none"}},
    }
    out = export(b, tmp_path / "bundle")
    assert (out / "agents" / "reviewer" / "config.yaml").is_file()


def test_export_invalid_raises(tmp_path: Path) -> None:
    bad = Bundle(config={"spec_version": 1, "executor": {"type": "omnigent", "config": {"harness": "nope"}}})
    with pytest.raises(ExportInvalid):
        export(bad, tmp_path / "bundle")
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implement** `omnigent_migrate/exporter.py`:
```python
"""Export a Bundle to a validated Omnigent bundle directory (strict: output must be runnable)."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from omnigent_migrate.ir import Bundle

_HEADER = "# GENERATED by omnigent-migrate — do not edit by hand.\n"


class ExportInvalid(Exception):
    """The exported bundle failed omnigent.spec.load — a tool bug, not user input."""


def _write_yaml(path: Path, cfg: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    yaml = YAML()
    yaml.default_flow_style = False
    setattr(yaml, "sort_base_mapping_type_on_output", False)
    buf = io.StringIO()
    yaml.dump(cfg, buf)
    path.write_text(_HEADER + buf.getvalue())


def export(bundle: Bundle, out_dir: Path) -> Path:
    out_dir = out_dir.expanduser()
    _write_yaml(out_dir / "config.yaml", bundle.config)
    for name, cfg in bundle.agents.items():
        _write_yaml(out_dir / "agents" / name / "config.yaml", cfg)

    from omnigent.errors import OmnigentError
    from omnigent.spec import load

    try:
        load(out_dir, expand_env=False, enforce_handler_allowlist=False)
    except (OmnigentError, FileNotFoundError) as exc:
        raise ExportInvalid(f"{out_dir}: {exc}") from exc
    return out_dir
```
- [ ] **Step 4:** run → PASS (3 tests). If `test_export_invalid_raises` does NOT raise (omnigent accepts an unknown harness at load time), change the bad bundle to one that's structurally invalid (drop `name`), keeping the intent; note it. ruff + mypy clean.
- [ ] **Step 5:** `git add -A && git commit -m "feat: exporter with strict omnigent.spec.load validation"`.

---

### Task 7: `cli.py` — `omnigent-migrate from-claude`

**Files:** Create `omnigent_migrate/cli.py`; Test `tests/test_cli.py`.

- [ ] **Step 1: Failing test:**
```python
from pathlib import Path

from click.testing import CliRunner

from omnigent_migrate.cli import main

FIXTURE = Path(__file__).parent / "fixtures" / "claude_project"


def test_from_claude_writes_bundle_and_report(tmp_path: Path) -> None:
    out = tmp_path / "out"
    res = CliRunner().invoke(main, ["from-claude", str(FIXTURE), "-o", str(out)])
    assert res.exit_code == 0, res.output
    assert (out / "config.yaml").is_file()
    assert (out / "MIGRATION_REPORT.md").is_file()
    assert "translated" in res.output


def test_dry_run_writes_no_bundle(tmp_path: Path) -> None:
    out = tmp_path / "out"
    res = CliRunner().invoke(main, ["from-claude", str(FIXTURE), "-o", str(out), "--dry-run"])
    assert res.exit_code == 0, res.output
    assert not (out / "config.yaml").exists()
    assert "DRY RUN" in res.output
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implement** `omnigent_migrate/cli.py`:
```python
"""omnigent-migrate CLI."""

from __future__ import annotations

from pathlib import Path

import click

from omnigent_migrate.exporter import export
from omnigent_migrate.importers.claude_code import ClaudeCodeImporter
from omnigent_migrate.ledger import Ledger, Status


@click.group()
def main() -> None:
    """Migrate an agent setup from another framework to Omnigent."""


@main.command(name="from-claude")
@click.argument("project", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("-o", "--out", type=click.Path(file_okay=False, path_type=Path), default=None,
              help="Output bundle dir (default: <project>/.omnigent).")
@click.option("--dry-run", is_flag=True, help="Render the fidelity report; emit no bundle.")
def from_claude(project: Path, out: Path | None, dry_run: bool) -> None:
    """Import a Claude Code project into an Omnigent bundle."""
    ledger = Ledger()
    bundle = ClaudeCodeImporter().to_bundle(project, ledger)
    out_dir = out or (project / ".omnigent")
    if dry_run:
        report = project / "MIGRATION_REPORT.md"
        report.write_text(ledger.render_markdown())
        click.echo(f"DRY RUN  {project.name} (no bundle written)")
    else:
        export(bundle, out_dir)
        report = out_dir / "MIGRATION_REPORT.md"
        report.write_text(ledger.render_markdown())
        click.echo(f"OK  migrated {project.name} -> {out_dir}")
    s = ledger.summary()
    click.echo(
        f"  {s[Status.TRANSLATED]} translated · {s[Status.DEGRADED]} degraded · "
        f"{s[Status.UNSUPPORTED]} unsupported"
    )
    click.echo(f"  report: {report}")
```
- [ ] **Step 4:** run → PASS (2 tests). Full gate: `uv run pytest -q && uv run ruff check && uv run mypy omnigent_migrate`.
- [ ] **Step 5:** `git add -A && git commit -m "feat: from-claude CLI (+ --dry-run)"`.

---

### Task 8: Integration + real-world smoke

**Files:** Test `tests/test_integration_claude.py`.

- [ ] **Step 1: Failing test** (full loop on the fixture, asserting the bundle VALIDATES):
```python
from pathlib import Path

from omnigent_migrate.exporter import export
from omnigent_migrate.importers.claude_code import ClaudeCodeImporter
from omnigent_migrate.ledger import Ledger

FIXTURE = Path(__file__).parent / "fixtures" / "claude_project"


def test_fixture_migrates_to_a_valid_bundle(tmp_path: Path) -> None:
    led = Ledger()
    bundle = ClaudeCodeImporter().to_bundle(FIXTURE, led)
    out = export(bundle, tmp_path / "b")  # raises ExportInvalid if the real omnigent loader rejects it
    assert (out / "config.yaml").is_file()
    assert (out / "agents" / "reviewer" / "config.yaml").is_file()
    assert led.summary()  # non-empty
```
- [ ] **Step 2:** run → it should PASS already (all parts built); if `export` raises `ExportInvalid`, the importer's emitted config is missing something the real loader needs — read the error, fix the importer (Task 5) shape, re-run. This is the end-to-end proof.
- [ ] **Step 3: Real-world smoke (manual, best-effort):**
```bash
cd /Users/bryanli/Projects/btli/omnigent-migrate
uv run omnigent-migrate from-claude ~/Projects/askcv.ai -o /tmp/askcv-omnigent
cat /tmp/askcv-omnigent/MIGRATION_REPORT.md | head -40
```
Expected: a validated bundle + a sensible report (askcv has CLAUDE.md + subagents + MCP). If `from-claude` errors on a real edge (a malformed subagent, an exotic MCP entry), capture it — it's the first real fidelity finding and seeds a Plan 2 task. Record the report summary in the commit message.
- [ ] **Step 4:** `git add -A && git commit -m "test: end-to-end Claude->Omnigent migration on a fixture"`.

---

## Self-Review

**Spec coverage (MVP slice):** importer interface + Claude importer (memory, subagents, MCP, skills) → Tasks 4-5 ✓ · ledger/fidelity → Task 2 ✓ · model→harness → Task 3 ✓ · exporter + strict validation → Task 6 ✓ · CLI + dry-run → Task 7 ✓ · lenient-in/strict-out → Tasks 5 (record, never raise) + 6 (validate, raise) ✓ · IR-as-bundle-config (not AgentSpec) → Task 4 ✓ · tier inference (subagents→orchestrator) → Task 5 + 8 ✓. **Deferred (not gaps):** hooks/commands/plugins/permissions (Plan 2), Codex importer (Plan 3), `MigrationExtensions` sidecar (Plan 2), round-trip + golden-report tests (Plan 2).

**Placeholder scan:** no TBD/"handle errors"/"similar to". Every code step is complete. Recovery instructions (Task 0/6/8) cite exact commands.

**Type consistency:** `Status`, `Ledger.record/summary/render_markdown`, `Bundle(config, agents)`, `Importer.detect/to_bundle`, `resolve_harness(model, source)->(str, str|None)`, `export(bundle, out_dir)->Path`, `ExportInvalid` are used consistently across tasks. The exporter validates exactly the shape the importer emits (Task 0 pins it).

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-18-accelerator-plan-1-mvp.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between tasks (as in the fleet plans).
2. **Inline Execution** — execute here with checkpoints.

This creates the `omnigent-migrate` repo + commits. Plan 2 (full Claude coverage: hooks/commands/plugins/permissions + `MigrationExtensions` + golden reports) and Plan 3 (Codex importer) follow.
