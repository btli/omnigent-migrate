# `omnigent-distill` — Stack-to-Agent-Team Distiller — Design Spec

**Date:** 2026-06-18 · **Status:** Draft for review (no implementation until approved) · **Author:** Claude (brainstorming with bryanli)
**One-liner:** Point it at a project → it profiles the stack, proposes an Omnigent **agent team** (orchestrator + generic workers + reviewer + only the specialist sub-agents the stack warrants), you review, and it emits a validated bundle.

---

## 1. Why (the reframe)

The accelerator's `from-claude`/`from-codex` importers do a **mechanical 1:1 config port**. That's useful when a project already has a curated `.claude/agents` setup — but it can't answer the real question: *given this project, what agents should drive it under Omnigent?* The Claude-Code and Omnigent paradigms differ (Omnigent's unit is the **agent**, with **sub-agents** you delegate to, **skills** host-discovered, **policies** for runtime enforcement; it has **no plugin or command** concept — slash-commands and plugins decompose into skills + sub-agents). So `distill` is a second mode: **analyze the stack → design the team**, keeping the importers as the port mode beside it.

### Paradigm map (the grounding)
| Claude Code | Omnigent |
|---|---|
| system prompt / agent identity | bundle `prompt` (**persona**) |
| `CLAUDE.md` / `AGENTS.md` | **repo-side, host-auto-loaded at cwd** (not the prompt) |
| skill (`~/.claude/skills`, `.claude/skills`) | **skill** — host-discovered (bundle ∪ repo `.claude/skills` ∪ user-global `~/.claude/skills`) |
| slash-command | skill (Omnigent only *observes* commands) |
| sub-agent (`.claude/agents/*.md`) | **sub-agent** (`agents/<name>/`) |
| plugin (superpowers, feature-dev) | **decomposes** → skills + sub-agents |
| MCP server | `tools.<name> {type: mcp}` |
| permissions / hooks | guardrails/policies (runtime) / carried |

**Skill vs sub-agent rule:** needs isolated context / its own perspective / autonomy → **sub-agent**; reusable instructions the agent follows itself → **skill**.

## 2. Decisions (locked in brainstorming)

| # | Decision | Choice |
|---|---|---|
| D1 | Deliverable | A **reusable distiller** (not a per-project hand-design) |
| D2 | Team model | **Hybrid** — generic workers + reviewer always; specialist sub-agents only where the stack warrants; everything below the bar → skills |
| D3 | How it decides | **Curated archetype library + LLM selector** — deterministic detectors profile; an LLM picks/parameterizes archetypes |
| D4 | LLM execution | **Embedded Claude API** (Anthropic SDK, `ANTHROPIC_API_KEY` in `.env`) — standalone, bootstrappable |
| D5 | Importers | **Keep** `from-claude`/`from-codex` as port mode beside `distill`; **finish Plan 4** (personas, shared `build_persona`) |

## 3. Architecture

```
project ─▶ [1] Profiler (deterministic) ─▶ ProjectProfile
                                              │
                        [2] Archetype Library (curated, data)
                                              │
       ProjectProfile + Library ─▶ [3] Selector (Claude API) ─▶ Team (proposal)
                                              │
                        [4] Review  (DISTILL_PLAN.yaml — edit/approve)
                                              │
   approved Team + ported config ─▶ [5] Emitter (reuse exporter + real omnigent.spec.load + ledger) ─▶ validated bundle + report
```

**Two CLI phases (LLM runs once, apply is deterministic):**
- `omnigent-migrate distill <project> [--model M]` → profile + propose → write `DISTILL_PLAN.yaml` (editable team) + a human summary. **No bundle emitted.**
- `omnigent-migrate distill <project> --apply [-o out]` → read the (reviewed/edited) `DISTILL_PLAN.yaml` → emit + validate the bundle deterministically (no LLM).

**Reused from the accelerator (Plans 1–4):** `exporter` (+ real-loader validation), `ledger`/report, `ir.Bundle`+`extensions`+sidecar, `harness_map`, `_util` (`build_persona`, `mcp_tool_entry`), and the importers' detection (settings/MCP/skills/agents parsing → Profiler's existing-config signals + Emitter's porting). **New:** `profiler`, `archetypes` (library), `selector` (Claude), the `distill` CLI + plan I/O.

## 4. Components

| Module | Responsibility | Key interface |
|---|---|---|
| `profiler.py` | Deterministic stack + existing-config detection | `profile(project: Path) -> ProjectProfile` |
| `archetypes.py` | The curated library (data + loader) | `LIBRARY: list[Archetype]` |
| `selector/base.py` | Selector protocol + schema + deterministic fallback | `Selector.propose(profile, library) -> Team` |
| `selector/anthropic.py` | Embedded Claude API impl | implements `Selector` |
| `distill.py` | Orchestrate phases; plan I/O | `propose(project) -> Team`; `apply(project, plan_path, out) -> Path` |
| `cli.py` | `distill` subcommand (+ existing port commands) | — |

### 4.1 `ProjectProfile` (deterministic)
A dataclass (serialisable to the compact JSON the Selector sees):
```
ProjectProfile:
  name: str
  languages: list[str]          # ["typescript", "python"]
  package_managers: list[str]   # ["bun", "uv"]
  frameworks: list[str]         # ["next.js", "fastapi"]
  db: list[str]                 # ["drizzle"]  (+ migration dirs found)
  infra: list[str]              # ["docker", "k3s", "terraform"]
  test: list[str]               # ["vitest", "pytest", "playwright"]
  data_ml: list[str]; mobile: list[str]; security: list[str]; ci: list[str]; docs: bool
  repo_shape: dict              # {monorepo: bool, splits: ["frontend","backend"], file_counts: {...}}
  existing: dict                # {agents:[...], skills:int, mcp:[...], hooks:bool, permissions:bool, plugins:[...], memory:[...]}
```
Detection sources: `package.json`/`pyproject.toml`/lockfiles/`Cargo.toml`/`go.mod` (langs+pms+frameworks+db+test from deps), `Dockerfile`/compose/`*.tf`/k8s manifests/helm (infra), `*.ipynb`+ml deps (data_ml), `pubspec.yaml`/expo (mobile), auth/stripe deps (security), `.github/workflows` (ci), `docs/` (docs), workspaces/turbo/nx + dir layout (repo_shape), and the importers' `.claude` detectors (existing).

### 4.2 Archetype Library
```
Archetype:
  id: str                       # "db-migrations"
  kind: "core" | "specialist"
  triggers: list[str]           # profile signals that make it a candidate (selector context + fallback)
  persona_template: str         # persona with {project}/{stack} placeholders (built via build_persona conventions)
  default_skills: list[str]     # host-discoverable skills it relies on (names; left repo/host-side)
  harness: str                  # recommended harness (claude-sdk / codex-native / pi)
  model: str | None
  guardrails_hint: str | None   # an OPT-IN guardrail recommendation (NOT auto-emitted — carry-only/sandbox-is-boundary)
```
**v1 library:** core = `orchestrator`, `implementer` (×2: claude_code, codex), `reviewer`; specialists = `frontend`, `backend`, `db-migrations`, `infra`. (Deferred: `test-qa`, `data-ml`, `mobile`, `security`, `docs`.)

### 4.3 Selector (embedded Claude API)
- **Interface:** `Selector` protocol with `propose(profile: ProjectProfile, library: list[Archetype]) -> Team`. Two impls: `AnthropicSelector` (real) and a deterministic `RuleSelector` (fallback / offline / tests).
- **Real impl:** one Anthropic API call (model default `claude-opus-4-8`, low temperature, `ANTHROPIC_API_KEY` from `.env`). Prompt = the profile (compact JSON) + the library (ids/triggers/templates) + **the rubric** + an instruction to return ONLY the `Team` JSON (tool-use / JSON schema). Validate the response against the `Team` schema; on validation failure retry once, then fall back to `RuleSelector` + a ledger note.
- **The "warranted" rubric (in the prompt):** a specialist earns its own sub-agent when its concern is (a) a substantial/recurring slice of the work, (b) benefits from isolated context or its own model/tools, or (c) needs an independent perspective; otherwise route it to a **skill**. Always include orchestrator + the two implementers + reviewer.
- **`RuleSelector` fallback:** instantiate a specialist iff its `triggers` fire in the profile; everything else → skills. Deterministic, no API. Guarantees the tool works offline (degraded) and gives a testable baseline.

```
Team:
  orchestrator: {persona: str}
  workers: list[{name: str, harness: str, model: str|None, persona: str}]   # claude_code, codex
  reviewer: {name: str, harness: str, model: str|None, persona: str}
  specialists: list[{archetype: str, name: str, persona: str, skills: list[str], harness: str, model: str|None, rationale: str}]
  skills_instead: list[{concern: str, why: str}]
```

### 4.4 Review + Emit
- **Review:** `distill` writes `Team` to `DISTILL_PLAN.yaml` (human-editable; rationale as comments) and prints a summary. The user edits/approves.
- **Emit (`--apply`):** read `DISTILL_PLAN.yaml` → build the bundle: orchestrator `config.yaml` (persona, `spawn: true`, `tools.agents: [...]`) + `agents/<name>/config.yaml` for each worker/reviewer/specialist (persona, harness, model, `os_env`) → port existing MCP/skills/permissions/hooks/plugins (reuse importer logic) into config/sidecar → **validate via the real `omnigent.spec.load`** → write `MIGRATION_REPORT.md` (distillation + fidelity). Skills stay repo-side/host-discovered; `guardrails_hint`s surface in the report as opt-in manual steps (not auto-emitted).

## 5. Testing
- **Profiler:** unit tests over fixture project trees (a Next.js+FastAPI+Drizzle+k3s fixture; a bare fixture) → asserts detected signals.
- **Archetypes:** schema tests (every archetype has required fields; ids unique).
- **Selector:** `RuleSelector` unit-tested directly (triggers → specialists). `AnthropicSelector` tested with a **stubbed client** returning canned JSON (no network) — asserts schema-validation + the parse. The rubric is exercised via `RuleSelector` + a couple of stubbed-response cases.
- **Emit:** the produced bundle passes the real `omnigent.spec.load` (strict-out, as in Plans 1–3); golden `DISTILL_PLAN.yaml` → bundle test.
- **Live smoke (manual):** `distill askcv.ai` + `distill remote-dev` with a real key → review the proposed teams + validate the applied bundles.

## 6. Relationship to the accelerator
`distill` and the importers share `exporter`/validator/`ledger`/`ir`/`harness_map`/`_util`. **Finish Plan 4** (persona prompts in both importers) — `build_persona` is the shared persona builder the archetypes also use. The importers remain the **port mode**; `distill` is the **design mode**; `auto` keeps detecting source for the port mode.

## 7. Scope
**v1:** profiler (web stack + existing `.claude`), library (core + frontend/backend/db-migrations/infra), `AnthropicSelector` + `RuleSelector` + schema, `DISTILL_PLAN.yaml` propose/apply, emit via exporter, smoke on askcv.ai + remote-dev. **Deferred:** remaining specialists, multi-pass refinement, guardrail emission, importer deprecation, upstream to `omnigent migrate/distill`.

## 8. Risks & open questions
- **Selector non-determinism** — mitigated by low temp, schema validation, the propose/apply split (LLM runs once; apply is deterministic from the reviewed file), and the deterministic fallback.
- **Persona quality** — archetype templates need iteration on real projects; the smoke is the check.
- **`~/.claude/plugins` discovery** — global *plugin* skills (e.g. `/global:ship-it`) may live under `~/.claude/plugins/<p>/skills/`, which `discover_host_skills` may not scan (it scans `~/.claude/skills`); the report should flag plugin-provided skills that need relocating onto a discovered path. (Verify during implementation.)
- **API key absence** — `RuleSelector` fallback keeps the tool usable offline (degraded), with a clear note.

## 9. Acceptance criteria (v1)
- `omnigent-migrate distill <project>` writes a `DISTILL_PLAN.yaml` with an orchestrator + 2 workers + reviewer + only the warranted specialists, each with a persona + rationale.
- `omnigent-migrate distill <project> --apply` emits a bundle that **passes `omnigent.spec.load`** + a report; ported MCP/skills/permissions appear honestly (TRANSLATED/DEGRADED/UNSUPPORTED).
- Offline (no key) falls back to `RuleSelector` with a note; still emits a valid bundle.
- Smoke on askcv.ai (frontend+backend+db) proposes frontend/backend (+ db if warranted) and routes thin concerns to skills; remote-dev likewise.
- `from-claude`/`from-codex` still work (port mode), now with persona prompts (Plan 4).
- Full gate: `uv run pytest`, `ruff check`, `mypy --strict` clean.
