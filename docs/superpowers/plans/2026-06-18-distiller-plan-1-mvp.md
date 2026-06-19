# Omnigent Distiller — Plan 1 (MVP)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`. **Hard scope rule: implement ONLY your dispatched task, commit, STOP.**

**Goal:** `omnigent-migrate distill <project>` — profile a project's stack, propose an Omnigent **agent team** (orchestrator + 2 workers + reviewer + only the specialist sub-agents the stack warrants) via an embedded Claude call, write an editable `DISTILL_PLAN.yaml`; `--apply` emits a **validated** bundle from the reviewed plan.

**Architecture:** profiler (deterministic) → archetype library (data) → selector (`RuleSelector` fallback + `AnthropicSelector`) → `DISTILL_PLAN.yaml` (review) → emitter (reuse the accelerator's exporter + real-loader validation + ledger). New code lives under `omnigent_migrate/distill/`. The LLM runs once at propose; `--apply` is deterministic.

**Tech Stack:** Python 3.13, `uv`, `click`, `ruamel.yaml`, **`pydantic`** (schema/validation), **`anthropic`** (selector), `pytest`, `ruff`, `mypy --strict`; `omnigent` (editable) for validation. Build on `feat/mvp` (Plans 1–4 committed).

**Spec:** `docs/superpowers/specs/2026-06-18-omnigent-distill-design.md`.

## Global Constraints

- `uv` only; no `# noqa`/`# type: ignore`; strict TDD; `mypy --strict` clean.
- IR is the **public bundle-config dict**; emitted `config.yaml` must pass the real `omnigent.spec.load`. No Omnigent-internal handler paths emitted (carry-only; guardrails are opt-in report hints).
- **Lenient-in:** all file reads guarded; the tool degrades (never crashes) on bad input or a missing API key (→ `RuleSelector`).
- `prompt` is a **persona** (reuse `build_persona` conventions); `CLAUDE.md`/`AGENTS.md`/skills stay repo-side.
- Latest stable deps: `uv add anthropic pydantic` (no pinning).

**Verified facts (don't re-derive):** `pydantic 2.13.4` is available; `anthropic` is not yet installed. The accelerator already provides: `exporter.export(bundle, out)->Path` (validates via real loader, raises `ExportInvalid`), `ir.Bundle(config, agents={}, extensions={})`, `ledger.Ledger`/`Status`, `harness_map.resolve_harness`, `_util.build_persona/_os_env/_sanitize/mcp_tool_entry`, `importers.claude_extras.collect_claude_extras(project, ledger)->dict` and `read_settings`. Orchestrator bundle shape (proven): `config.yaml` with `spawn: true` + `tools.agents: [...]` + `agents/<name>/config.yaml` sub-bundles, each `executor{type:omnigent,config.harness}` + `prompt` + `os_env`.

---

### Task 1: deps + `distill/schema.py` (pydantic models)

**Files:** `pyproject.toml` (deps); Create `omnigent_migrate/distill/__init__.py` (empty), `omnigent_migrate/distill/schema.py`; Test `tests/distill/test_schema.py`.

**Interfaces:** Produces pydantic models `ProjectProfile`, `Archetype`, `WorkerSpec`, `SpecialistSpec`, `Team`. `Team.model_json_schema()` must yield a dict usable as an Anthropic tool `input_schema`.

- [ ] **Step 1:** `uv add anthropic pydantic`. Create empty `omnigent_migrate/distill/__init__.py` and `tests/distill/__init__.py`.
- [ ] **Step 2: Failing test** (`tests/distill/test_schema.py`):
```python
from omnigent_migrate.distill.schema import Archetype, ProjectProfile, Team, WorkerSpec


def test_profile_defaults() -> None:
    p = ProjectProfile(name="demo")
    assert p.languages == [] and p.existing == {}


def test_archetype_required_fields() -> None:
    a = Archetype(id="db-migrations", kind="specialist", triggers=["drizzle"],
                  persona_template="You manage migrations for {project}.", default_skills=[],
                  harness="claude-sdk")
    assert a.kind == "specialist"


def test_team_round_trips_and_emits_json_schema() -> None:
    t = Team(
        orchestrator={"persona": "You are the orchestrator for x."},
        workers=[WorkerSpec(name="claude_code", harness="claude-native", persona="impl")],
        reviewer=WorkerSpec(name="reviewer", harness="pi", persona="review"),
        specialists=[], skills_instead=[],
    )
    assert t.workers[0].name == "claude_code"
    schema = Team.model_json_schema()
    assert schema["type"] == "object" and "properties" in schema
```
- [ ] **Step 3: Implement** `omnigent_migrate/distill/schema.py`:
```python
"""Pydantic models for the distiller: the project profile, the archetype library,
and the proposed agent team (also the Anthropic tool-output schema)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ProjectProfile(BaseModel):
    name: str
    languages: list[str] = Field(default_factory=list)
    package_managers: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    db: list[str] = Field(default_factory=list)
    infra: list[str] = Field(default_factory=list)
    test: list[str] = Field(default_factory=list)
    data_ml: list[str] = Field(default_factory=list)
    mobile: list[str] = Field(default_factory=list)
    security: list[str] = Field(default_factory=list)
    ci: list[str] = Field(default_factory=list)
    docs: bool = False
    repo_shape: dict[str, Any] = Field(default_factory=dict)
    existing: dict[str, Any] = Field(default_factory=dict)


class Archetype(BaseModel):
    id: str
    kind: Literal["core", "specialist"]
    triggers: list[str] = Field(default_factory=list)
    persona_template: str
    default_skills: list[str] = Field(default_factory=list)
    harness: str = "claude-sdk"
    model: str | None = None
    guardrails_hint: str | None = None


class WorkerSpec(BaseModel):
    name: str
    harness: str
    model: str | None = None
    persona: str


class SpecialistSpec(BaseModel):
    archetype: str
    name: str
    persona: str
    skills: list[str] = Field(default_factory=list)
    harness: str = "claude-sdk"
    model: str | None = None
    rationale: str = ""


class SkillInstead(BaseModel):
    concern: str
    why: str


class Team(BaseModel):
    orchestrator: dict[str, str]
    workers: list[WorkerSpec]
    reviewer: WorkerSpec
    specialists: list[SpecialistSpec] = Field(default_factory=list)
    skills_instead: list[SkillInstead] = Field(default_factory=list)
```
- [ ] **Step 4:** `uv run pytest tests/distill/test_schema.py -q` → PASS. `uv run pytest -q && uv run ruff check && uv run mypy omnigent_migrate` → clean. (If mypy flags pydantic, add `[[tool.mypy.overrides]] module="pydantic.*" ignore_missing_imports=true` only if its stubs are genuinely absent — pydantic ships types, so it should be clean.)
- [ ] **Step 5:** `git add -A && git commit -m "feat(distill): pydantic schema (ProjectProfile, Archetype, Team)"`. **STOP.**

---

### Task 2: `distill/profiler.py` — deterministic stack detection

**Files:** Create `omnigent_migrate/distill/profiler.py`; fixture `tests/fixtures/distill_project/` ; Test `tests/distill/test_profiler.py`.

**Interfaces:** Consumes `ProjectProfile` (Task 1), `claude_extras.read_settings`. Produces `profile(project: Path) -> ProjectProfile`.

- [ ] **Step 1: Build the fixture** (a Next.js + FastAPI + Drizzle + k3s project):
```bash
cd /Users/bryanli/Projects/btli/omnigent-migrate
mkdir -p tests/fixtures/distill_project/.claude/agents tests/fixtures/distill_project/drizzle tests/fixtures/distill_project/k8s
printf '{\n  "name": "demo",\n  "dependencies": {"next": "15", "react": "19", "drizzle-orm": "0.3"},\n  "devDependencies": {"vitest": "2", "@playwright/test": "1"}\n}\n' > tests/fixtures/distill_project/package.json
printf '[project]\nname="demo-api"\ndependencies=["fastapi","sqlalchemy"]\n[dependency-groups]\ndev=["pytest"]\n' > tests/fixtures/distill_project/pyproject.toml
printf 'FROM oven/bun:alpine\n' > tests/fixtures/distill_project/Dockerfile
printf 'apiVersion: apps/v1\nkind: Deployment\n' > tests/fixtures/distill_project/k8s/deploy.yaml
printf -- '---\nname: reviewer\ndescription: Reviews diffs\n---\nReview.\n' > tests/fixtures/distill_project/.claude/agents/reviewer.md
printf 'Lead.\n' > tests/fixtures/distill_project/CLAUDE.md
```
- [ ] **Step 2: Failing test** (`tests/distill/test_profiler.py`):
```python
from pathlib import Path

from omnigent_migrate.distill.profiler import profile

FIXTURE = Path(__file__).parent.parent / "fixtures" / "distill_project"


def test_profiles_web_stack() -> None:
    p = profile(FIXTURE)
    assert "typescript" in p.languages and "python" in p.languages
    assert "next.js" in p.frameworks and "fastapi" in p.frameworks
    assert "drizzle" in p.db
    assert "docker" in p.infra and "kubernetes" in p.infra
    assert "vitest" in p.test and "pytest" in p.test and "playwright" in p.test
    assert p.existing["agents"] == ["reviewer"]
    assert "CLAUDE.md" in p.existing["memory"]
```
- [ ] **Step 3: Implement** `omnigent_migrate/distill/profiler.py`:
```python
"""Deterministic project profiling — detect stack + existing agent config. No LLM."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from omnigent_migrate.distill.schema import ProjectProfile
from omnigent_migrate.importers.claude_extras import read_settings

# dependency substrings -> framework/db/test/security labels
_DEP_MARKERS: dict[str, dict[str, str]] = {
    "frameworks": {"next": "next.js", "react": "react", "vue": "vue", "svelte": "svelte",
                   "fastapi": "fastapi", "django": "django", "flask": "flask", "express": "express"},
    "db": {"drizzle": "drizzle", "prisma": "prisma", "typeorm": "typeorm",
           "sqlalchemy": "sqlalchemy", "alembic": "alembic"},
    "test": {"vitest": "vitest", "jest": "jest", "playwright": "playwright",
             "cypress": "cypress", "pytest": "pytest"},
    "security": {"next-auth": "auth", "authlib": "auth", "stripe": "payments"},
    "data_ml": {"torch": "torch", "tensorflow": "tensorflow", "pandas": "pandas"},
}


def _read_json(p: Path) -> dict[str, Any]:
    try:
        data = json.loads(p.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _deps_blob(project: Path) -> str:
    """All declared dependency names, lowercased, as one searchable string."""
    parts: list[str] = []
    pkg = _read_json(project / "package.json")
    for key in ("dependencies", "devDependencies"):
        parts.extend((pkg.get(key) or {}).keys())
    pyproject = project / "pyproject.toml"
    if pyproject.is_file():
        try:
            parts.append(pyproject.read_text())
        except (OSError, UnicodeDecodeError):
            pass
    req = project / "requirements.txt"
    if req.is_file():
        try:
            parts.append(req.read_text())
        except (OSError, UnicodeDecodeError):
            pass
    return " ".join(parts).lower()


def _match(blob: str, markers: dict[str, str]) -> list[str]:
    out: list[str] = []
    for needle, label in markers.items():
        if needle in blob and label not in out:
            out.append(label)
    return out


def profile(project: Path) -> ProjectProfile:
    project = project.expanduser().resolve()
    blob = _deps_blob(project)

    languages: list[str] = []
    package_managers: list[str] = []
    if (project / "package.json").is_file():
        languages.append("typescript")
        package_managers.append("bun" if (project / "bun.lockb").is_file() or (project / "bun.lock").is_file() else "npm")
    if (project / "pyproject.toml").is_file() or (project / "requirements.txt").is_file():
        languages.append("python")
        package_managers.append("uv" if (project / "uv.lock").is_file() else "pip")

    infra: list[str] = []
    if (project / "Dockerfile").is_file() or (project / "docker-compose.yml").is_file():
        infra.append("docker")
    if any(project.glob("**/*.tf")):
        infra.append("terraform")
    if any(d.is_dir() and d.name in ("k8s", "kubernetes", "manifests") for d in project.iterdir() if d.is_dir()):
        infra.append("kubernetes")

    settings = read_settings(project)
    agents_dir = project / ".claude" / "agents"
    existing: dict[str, Any] = {
        "agents": sorted(p.stem for p in agents_dir.glob("*.md")) if agents_dir.is_dir() else [],
        "skills": sum(1 for d in (project / ".claude" / "skills").glob("*/SKILL.md")) if (project / ".claude" / "skills").is_dir() else 0,
        "memory": [m for m in ("CLAUDE.md", "AGENTS.md") if (project / m).is_file()],
        "hooks": bool(settings.get("hooks")),
        "permissions": bool(settings.get("permissions")),
        "plugins": list((settings.get("enabledPlugins") or {})),
        "mcp": (project / ".mcp.json").is_file(),
    }

    return ProjectProfile(
        name=project.name,
        languages=languages,
        package_managers=package_managers,
        frameworks=_match(blob, _DEP_MARKERS["frameworks"]),
        db=_match(blob, _DEP_MARKERS["db"]),
        infra=infra,
        test=_match(blob, _DEP_MARKERS["test"]),
        data_ml=_match(blob, _DEP_MARKERS["data_ml"]),
        mobile=["flutter"] if (project / "pubspec.yaml").is_file() else [],
        security=_match(blob, _DEP_MARKERS["security"]),
        ci=["github-actions"] if (project / ".github" / "workflows").is_dir() else [],
        docs=(project / "docs").is_dir(),
        repo_shape={"monorepo": (project / "pnpm-workspace.yaml").is_file() or "workspaces" in blob},
        existing=existing,
    )
```
- [ ] **Step 4:** `uv run pytest tests/distill/test_profiler.py -q` → PASS. Full gate clean.
- [ ] **Step 5:** `git add -A && git commit -m "feat(distill): deterministic stack profiler"`. **STOP.**

---

### Task 3: `distill/archetypes.py` — the curated library

**Files:** Create `omnigent_migrate/distill/archetypes.py`; Test `tests/distill/test_archetypes.py`.

**Interfaces:** Consumes `Archetype` (Task 1). Produces `LIBRARY: list[Archetype]` and `CORE_IDS: frozenset[str]`.

- [ ] **Step 1: Failing test:**
```python
from omnigent_migrate.distill.archetypes import CORE_IDS, LIBRARY


def test_library_has_core_and_specialists() -> None:
    ids = {a.id for a in LIBRARY}
    assert {"orchestrator", "implementer", "reviewer"} <= ids
    assert {"frontend", "backend", "db-migrations", "infra"} <= ids
    assert all(a.persona_template for a in LIBRARY)
    assert len(ids) == len(LIBRARY)  # ids unique
    assert CORE_IDS == {a.id for a in LIBRARY if a.kind == "core"}
```
- [ ] **Step 2: Implement** `omnigent_migrate/distill/archetypes.py` — define `LIBRARY` with these entries (each an `Archetype`):
  - `orchestrator` (core): persona_template = "You are the orchestrator for the {project} repository. You coordinate specialized sub-agents and delegate work to them rather than doing it yourself. Decompose each request, route each part to the most appropriate sub-agent, and integrate their results. Follow the repo's own conventions (CLAUDE.md/AGENTS.md) and skills." harness="claude-sdk".
  - `implementer` (core): "You are a coding sub-agent for {project}. Implement the scoped task in your worktree, drive it to green (tests/lint/typecheck), and open a PR." harness="claude-native". triggers=[].
  - `reviewer` (core): "You review another agent's diff for {project} against its acceptance contract — report blocking/non-blocking issues with file:line; never edit." harness="pi".
  - `frontend` (specialist), triggers=["next.js","react","vue","svelte"]: "You own the {project} frontend (its JS/TS UI). Build and refine components, state, and styling per the repo's conventions." default_skills=[], harness="claude-native".
  - `backend` (specialist), triggers=["fastapi","django","flask","express"]: "You own the {project} backend (its server/API). Implement endpoints, services, and data access per the repo's conventions." harness="claude-native".
  - `db-migrations` (specialist), triggers=["drizzle","prisma","alembic","sqlalchemy"]: "You own schema + migrations for {project}. Author and verify migrations safely; never apply destructive changes without review." harness="claude-native".
  - `infra` (specialist), triggers=["docker","kubernetes","terraform"]: "You own {project} infrastructure (containers, k8s, IaC). Make changes safely and keep deploys reproducible." harness="claude-native".
  Then `CORE_IDS = frozenset(a.id for a in LIBRARY if a.kind == "core")`.
- [ ] **Step 3:** `uv run pytest tests/distill/test_archetypes.py -q` → PASS. Full gate clean.
- [ ] **Step 4:** `git add -A && git commit -m "feat(distill): v1 archetype library"`. **STOP.**

---

### Task 4: `distill/selector/base.py` — Selector protocol + `RuleSelector`

**Files:** Create `omnigent_migrate/distill/selector/__init__.py` (empty), `omnigent_migrate/distill/selector/base.py`; Test `tests/distill/test_rule_selector.py`.

**Interfaces:** Consumes `ProjectProfile`, `Team`, `Archetype`, `LIBRARY`. Produces `Selector` protocol (`propose(profile, library) -> Team`) and `RuleSelector` + helper `instantiate_persona(template, project) -> str`.

- [ ] **Step 1: Failing test:**
```python
from omnigent_migrate.distill.archetypes import LIBRARY
from omnigent_migrate.distill.schema import ProjectProfile
from omnigent_migrate.distill.selector.base import RuleSelector


def test_rule_selector_picks_warranted_specialists() -> None:
    profile = ProjectProfile(name="demo", frameworks=["next.js", "fastapi"], db=["drizzle"], infra=["kubernetes"])
    team = RuleSelector().propose(profile, LIBRARY)
    assert team.orchestrator["persona"]
    assert {w.name for w in team.workers} == {"claude_code", "codex"}
    assert team.reviewer.name == "reviewer"
    chosen = {s.archetype for s in team.specialists}
    assert {"frontend", "backend", "db-migrations", "infra"} == chosen


def test_rule_selector_no_specialists_when_bare() -> None:
    team = RuleSelector().propose(ProjectProfile(name="bare"), LIBRARY)
    assert team.specialists == []
```
- [ ] **Step 2: Implement** `omnigent_migrate/distill/selector/base.py`:
```python
"""Selector protocol + a deterministic rule-based fallback (no LLM)."""

from __future__ import annotations

from typing import Protocol

from omnigent_migrate.distill.schema import (
    Archetype,
    ProjectProfile,
    SpecialistSpec,
    Team,
    WorkerSpec,
)


def instantiate_persona(template: str, project: str) -> str:
    return template.replace("{project}", project)


def _signals(profile: ProjectProfile) -> set[str]:
    return set(
        profile.frameworks + profile.db + profile.infra + profile.test
        + profile.data_ml + profile.mobile + profile.security
    )


class Selector(Protocol):
    def propose(self, profile: ProjectProfile, library: list[Archetype]) -> Team: ...


class RuleSelector:
    """Instantiate a specialist iff any of its triggers fire; core always."""

    def propose(self, profile: ProjectProfile, library: list[Archetype]) -> Team:
        by_id = {a.id: a for a in library}
        signals = _signals(profile)
        orch = by_id["orchestrator"]
        impl = by_id["implementer"]
        rev = by_id["reviewer"]
        specialists: list[SpecialistSpec] = []
        for a in library:
            if a.kind != "specialist":
                continue
            if signals.intersection(a.triggers):
                specialists.append(SpecialistSpec(
                    archetype=a.id, name=a.id,
                    persona=instantiate_persona(a.persona_template, profile.name),
                    skills=a.default_skills, harness=a.harness, model=a.model,
                    rationale=f"stack signals {sorted(signals.intersection(a.triggers))} warrant a {a.id} agent",
                ))
        return Team(
            orchestrator={"persona": instantiate_persona(orch.persona_template, profile.name)},
            workers=[
                WorkerSpec(name="claude_code", harness="claude-native",
                           persona=instantiate_persona(impl.persona_template, profile.name)),
                WorkerSpec(name="codex", harness="codex-native",
                           persona=instantiate_persona(impl.persona_template, profile.name)),
            ],
            reviewer=WorkerSpec(name="reviewer", harness=rev.harness,
                                persona=instantiate_persona(rev.persona_template, profile.name)),
            specialists=specialists,
            skills_instead=[],
        )
```
- [ ] **Step 3:** `uv run pytest tests/distill/test_rule_selector.py -q` → PASS. Full gate clean.
- [ ] **Step 4:** `git add -A && git commit -m "feat(distill): Selector protocol + deterministic RuleSelector"`. **STOP.**

---

### Task 5: `distill/selector/anthropic.py` — embedded Claude selector (stubbed in tests)

**Files:** Create `omnigent_migrate/distill/selector/anthropic.py`; Test `tests/distill/test_anthropic_selector.py`.

**Interfaces:** Consumes `Selector`/`RuleSelector`, `Team.model_json_schema()`. Produces `AnthropicSelector(client: Any | None = None, model: str = "claude-opus-4-8")` implementing `Selector`; falls back to `RuleSelector` on any error.

- [ ] **Step 1: Failing test** (stub the client — no network):
```python
from typing import Any

from omnigent_migrate.distill.archetypes import LIBRARY
from omnigent_migrate.distill.schema import ProjectProfile
from omnigent_migrate.distill.selector.anthropic import AnthropicSelector


class _ToolUse:
    type = "tool_use"

    def __init__(self, data: dict[str, Any]) -> None:
        self.input = data


class _Resp:
    def __init__(self, data: dict[str, Any]) -> None:
        self.content = [_ToolUse(data)]


class _StubClient:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data
        self.messages = self

    def create(self, **_: Any) -> _Resp:
        return _Resp(self._data)


def _canned() -> dict[str, Any]:
    return {
        "orchestrator": {"persona": "You are the orchestrator for demo."},
        "workers": [{"name": "claude_code", "harness": "claude-native", "persona": "impl"}],
        "reviewer": {"name": "reviewer", "harness": "pi", "persona": "review"},
        "specialists": [{"archetype": "backend", "name": "backend", "persona": "be",
                         "skills": [], "harness": "claude-native", "rationale": "fastapi"}],
        "skills_instead": [],
    }


def test_anthropic_selector_parses_tool_output() -> None:
    sel = AnthropicSelector(client=_StubClient(_canned()))
    team = sel.propose(ProjectProfile(name="demo", frameworks=["fastapi"]), LIBRARY)
    assert team.specialists[0].archetype == "backend"


def test_anthropic_selector_falls_back_on_error() -> None:
    class _Boom:
        messages = property(lambda self: (_ for _ in ()).throw(RuntimeError("no")))
    sel = AnthropicSelector(client=_Boom())
    team = sel.propose(ProjectProfile(name="demo", db=["drizzle"]), LIBRARY)  # RuleSelector path
    assert {s.archetype for s in team.specialists} == {"db-migrations"}
```
- [ ] **Step 2: Implement** `omnigent_migrate/distill/selector/anthropic.py`:
```python
"""Embedded Claude selector. Forces a tool call whose input_schema is the Team
schema, validates the result, and falls back to RuleSelector on any failure."""

from __future__ import annotations

import json
from typing import Any

from omnigent_migrate.distill.archetypes import LIBRARY
from omnigent_migrate.distill.schema import Archetype, ProjectProfile, Team
from omnigent_migrate.distill.selector.base import RuleSelector

_RUBRIC = (
    "You design an Omnigent agent team for a project. Always include the orchestrator, "
    "two implementer workers (claude_code on claude-native, codex on codex-native), and a "
    "reviewer. Add a specialist sub-agent ONLY when its concern is a substantial/recurring "
    "slice of the work, benefits from isolated context or its own tools, or needs an "
    "independent perspective; otherwise route that concern to skills_instead. Personas are "
    "role descriptions that point at the repo's own docs/skills — never inline project docs."
)


def _make_client() -> Any:
    from anthropic import Anthropic

    return Anthropic()  # reads ANTHROPIC_API_KEY from env


class AnthropicSelector:
    def __init__(self, client: Any | None = None, model: str = "claude-opus-4-8") -> None:
        self._client = client
        self._model = model
        self._fallback = RuleSelector()

    def propose(self, profile: ProjectProfile, library: list[Archetype]) -> Team:
        try:
            client = self._client or _make_client()
            tool = {
                "name": "emit_team",
                "description": "Return the proposed Omnigent agent team.",
                "input_schema": Team.model_json_schema(),
            }
            lib = [a.model_dump(include={"id", "kind", "triggers"}) for a in library]
            resp = client.messages.create(
                model=self._model,
                max_tokens=4096,
                temperature=0,
                system=_RUBRIC,
                tools=[tool],
                tool_choice={"type": "tool", "name": "emit_team"},
                messages=[{
                    "role": "user",
                    "content": (
                        "PROJECT PROFILE:\n" + profile.model_dump_json(indent=2)
                        + "\n\nARCHETYPE LIBRARY (ids/kinds/triggers):\n" + json.dumps(lib)
                        + "\n\nReturn the team via emit_team."
                    ),
                }],
            )
            for block in resp.content:
                if getattr(block, "type", None) == "tool_use":
                    return Team.model_validate(block.input)
            raise ValueError("no tool_use block in response")
        except Exception:
            return self._fallback.propose(profile, library or LIBRARY)
```
- [ ] **Step 3:** `uv run pytest tests/distill/test_anthropic_selector.py -q` → PASS (2 tests, no network). Full gate clean. (The broad `except Exception` is deliberate and required by the lenient-in design — the selector MUST degrade to the deterministic fallback on any API/parse/key failure. Ruff's default config does not flag it; do not add a `# noqa`.)
- [ ] **Step 4:** `git add -A && git commit -m "feat(distill): AnthropicSelector with RuleSelector fallback"`. **STOP.**

---

### Task 6: `distill/distill.py` — propose → `DISTILL_PLAN.yaml` → apply → bundle

**Files:** Create `omnigent_migrate/distill/distill.py`; Test `tests/distill/test_distill.py`.

**Interfaces:** Consumes profiler, selectors, schema, and the accelerator's `exporter.export`, `ir.Bundle`, `ledger`, `_util._os_env`, `claude_extras.collect_claude_extras`. Produces `propose(project, selector)->Team`, `write_plan(team, path)`, `read_plan(path)->Team`, `apply(project, plan_path, out, ledger)->Path`.

- [ ] **Step 1: Failing test:**
```python
from pathlib import Path

from omnigent_migrate.distill.distill import apply, propose, read_plan, write_plan
from omnigent_migrate.distill.selector.base import RuleSelector
from omnigent_migrate.ledger import Ledger

FIXTURE = Path(__file__).parent.parent / "fixtures" / "distill_project"


def test_propose_write_read_round_trip(tmp_path: Path) -> None:
    team = propose(FIXTURE, RuleSelector())
    plan = tmp_path / "DISTILL_PLAN.yaml"
    write_plan(team, plan)
    assert plan.is_file()
    team2 = read_plan(plan)
    assert {s.archetype for s in team2.specialists} == {s.archetype for s in team.specialists}


def test_apply_emits_valid_bundle(tmp_path: Path) -> None:
    team = propose(FIXTURE, RuleSelector())
    plan = tmp_path / "plan.yaml"
    write_plan(team, plan)
    out = apply(FIXTURE, plan, tmp_path / "bundle", Ledger())  # raises if invalid
    assert (out / "config.yaml").is_file()
    # specialists + workers + reviewer become sub-agents
    assert (out / "agents" / "backend" / "config.yaml").is_file()
    assert (out / "agents" / "claude_code" / "config.yaml").is_file()
```
- [ ] **Step 2: Implement** `omnigent_migrate/distill/distill.py`:
```python
"""Orchestrate the distiller: profile + select (propose), serialize the editable
plan, and build+validate the bundle from an approved plan (apply)."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

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
    from omnigent_migrate.distill.archetypes import LIBRARY

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
```
(If ruff objects to the `__import__` in `propose`, replace it with a top-level `from omnigent_migrate.distill.archetypes import LIBRARY` and `return selector.propose(profile_project(project), LIBRARY)`.)
- [ ] **Step 3:** `uv run pytest tests/distill/test_distill.py -q` → PASS (the bundle validates via the real loader). Full gate clean.
- [ ] **Step 4:** `git add -A && git commit -m "feat(distill): propose/plan-IO/apply -> validated bundle"`. **STOP.**

---

### Task 7: `distill` CLI command + integration + smoke

**Files:** Modify `omnigent_migrate/cli.py`; Test `tests/test_cli.py` (extend).

**Interfaces:** Consumes `distill.propose/write_plan/apply`, `RuleSelector`, `AnthropicSelector`.

- [ ] **Step 1: Failing test** (append to `tests/test_cli.py`):
```python
DISTILL_FIXTURE = Path(__file__).parent / "fixtures" / "distill_project"


def test_distill_writes_plan(tmp_path: Path) -> None:
    res = CliRunner().invoke(main, ["distill", str(DISTILL_FIXTURE), "--no-llm",
                                    "--plan", str(tmp_path / "p.yaml")])
    assert res.exit_code == 0, res.output
    assert (tmp_path / "p.yaml").is_file()
    assert "backend" in res.output


def test_distill_apply_emits_bundle(tmp_path: Path) -> None:
    plan = tmp_path / "p.yaml"
    CliRunner().invoke(main, ["distill", str(DISTILL_FIXTURE), "--no-llm", "--plan", str(plan)])
    res = CliRunner().invoke(main, ["distill", str(DISTILL_FIXTURE), "--apply",
                                    "--plan", str(plan), "-o", str(tmp_path / "b")])
    assert res.exit_code == 0, res.output
    assert (tmp_path / "b" / "config.yaml").is_file()
```
- [ ] **Step 2: Implement** in `omnigent_migrate/cli.py` — add the `distill` command (`--no-llm` forces `RuleSelector`; default uses `AnthropicSelector`; `--plan` path defaults to `<project>/DISTILL_PLAN.yaml`; `--apply` reads the plan and emits):
```python
@main.command(name="distill")
@click.argument("project", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("-o", "--out", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option("--plan", "plan_path", type=click.Path(path_type=Path), default=None,
              help="Plan file (default: <project>/DISTILL_PLAN.yaml).")
@click.option("--apply", "do_apply", is_flag=True, help="Emit the bundle from the reviewed plan.")
@click.option("--no-llm", is_flag=True, help="Use the deterministic RuleSelector (no API call).")
@click.option("--model", default="claude-opus-4-8")
def distill(project: Path, out: Path | None, plan_path: Path | None, do_apply: bool,
            no_llm: bool, model: str) -> None:
    """Distill a project's stack into an Omnigent agent-team bundle."""
    from omnigent_migrate.distill.distill import apply as apply_plan
    from omnigent_migrate.distill.distill import propose, write_plan
    from omnigent_migrate.distill.selector.anthropic import AnthropicSelector
    from omnigent_migrate.distill.selector.base import RuleSelector

    plan_file = plan_path or (project / "DISTILL_PLAN.yaml")
    if do_apply:
        out_dir = out or (project / ".omnigent")
        apply_plan(project, plan_file, out_dir, Ledger())
        click.echo(f"OK  distilled {project.name} -> {out_dir}")
        return
    selector = RuleSelector() if no_llm else AnthropicSelector(model=model)
    team = propose(project, selector)
    write_plan(team, plan_file)
    click.echo(f"PROPOSED  {project.name}: orchestrator + {len(team.workers)} workers + reviewer "
               f"+ {len(team.specialists)} specialists ({', '.join(s.archetype for s in team.specialists)})")
    click.echo(f"  plan: {plan_file}  (review/edit, then --apply)")
```
- [ ] **Step 3:** `uv run pytest -q` → PASS (all). Full gate clean.
- [ ] **Step 4: Real-world smoke (best-effort):**
```bash
cd /Users/bryanli/Projects/btli/omnigent-migrate
uv run omnigent-migrate distill /Users/bryanli/Projects/askcv.ai --no-llm --plan /tmp/askcv-distill.yaml
cat /tmp/askcv-distill.yaml
uv run omnigent-migrate distill /Users/bryanli/Projects/askcv.ai --apply --plan /tmp/askcv-distill.yaml -o /tmp/askcv-distilled && ls -R /tmp/askcv-distilled | head -20
# If ANTHROPIC_API_KEY is set, also try the live selector:
uv run omnigent-migrate distill /Users/bryanli/Projects/askcv.ai --plan /tmp/askcv-llm.yaml || echo "(no key -> falls back)"
```
Record the proposed team + whether the bundle validated in the commit message.
- [ ] **Step 5:** `git add -A && git commit -m "feat(distill): distill CLI command (+ integration + smoke)"`. **STOP.**

---

## Self-Review

**Spec coverage:** schema (T1) ✓ · profiler (T2) ✓ · archetype library (T3) ✓ · RuleSelector + protocol (T4) ✓ · AnthropicSelector + fallback (T5) ✓ · propose/plan/apply emit+validate (T6) ✓ · CLI + smoke (T7) ✓ · propose/apply split + offline fallback ✓ · reuse exporter/ledger/_util/claude_extras ✓. **Deferred (per spec §7):** remaining specialists, multi-pass refinement, guardrail emission, upstreaming.

**Placeholder scan:** none — each step has complete code/commands. Two ruff-nuance notes (the `CORE_IDS` parity line in T4, the `__import__` in T6, the broad-catch in T5) give the exact fix if the linter objects.

**Type consistency:** pydantic models (`ProjectProfile/Archetype/WorkerSpec/SpecialistSpec/Team`) flow through `profile()->Selector.propose()->Team->write_plan/read_plan->apply()->export()`. `apply` builds the proven orchestrator shape (`spawn`+`tools.agents`+`agents/<name>`); the bundle is validated by the real loader in T6/T7.
