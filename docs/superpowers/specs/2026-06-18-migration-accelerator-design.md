# Omnigent Migration Accelerator (`omnigent-migrate`) — Design Spec

**Date:** 2026-06-18
**Status:** Draft for review (no implementation until approved)
**Author:** Claude (brainstorming session with bryanli)
**One-liner:** Point it at a Claude Code or Codex project → get a validated Omnigent bundle + a per-primitive fidelity report.

---

## 1. Goal & non-goals

### Goal
A **product-grade** tool that imports an existing agent setup from another framework and emits a **runnable, validated Omnigent agent bundle** plus an honest **fidelity report** (what translated cleanly, what degraded, what needs manual work). v1 supports **Claude Code** and **Codex** as sources; Omnigent is the only target.

### Non-goals (v1)
- Any→any transpilation. Target is **Omnigent only** (sources fan in).
- A neutral/bespoke IR. We **adopt Omnigent's `AgentSpec`** as the IR.
- Runtime/behavioral migration (translating *running sessions*); this migrates *configuration/setup*.
- Reverse direction (Omnigent → Claude/Codex) beyond what round-trip tests need.

---

## 2. Decisions (locked in brainstorming)

| # | Decision | Choice |
|---|---|---|
| D1 | Topology | Many sources → **Omnigent** (omnigent-centric) |
| D2 | Audience | **Product** (Omnigent onboarding; general, polished, documented) |
| D3 | v1 sources | **Claude Code + Codex** importers |
| D4 | Coverage | **Maximal best-effort** — translate everything translatable; per-primitive fidelity report for the rest |
| D5 | IR & home | **Standalone `omnigent-migrate` package** on Omnigent's `AgentSpec` IR, reusing its validator/translator/bundlegen; **upstreamable** to `omnigent migrate …` |

---

## 3. Architecture

A transpiler, source → Omnigent:

```
source project (.claude/ | .codex/)
   │  Importer (claude_code | codex)            ← LENIENT: never aborts; records every decision
   ▼
 AgentSpec IR  +  MigrationLedger (fidelity records)  +  MigrationExtensions (carried-but-unmapped)
   │  Exporter (Omnigent — reuses bundlegen's compose/write/validate)
   ▼
 Omnigent bundle  ──► validated against the REAL omnigent.spec.load   ← STRICT: output must be runnable
   │
   ▼
 MIGRATION_REPORT.md  (TRANSLATED / DEGRADED / UNSUPPORTED per primitive + manual steps)
```

**Core principle — lenient in, strict out:** importers tolerate anything and *report*; the exported bundle is always validated and must be runnable, or the tool fails loud on its own output.

---

## 4. Components

Each is a small, independently-testable unit with a clear interface.

| Module | Responsibility | Key interface |
|---|---|---|
| `ir.py` | Thin layer over omnigent `AgentSpec` + a `MigrationExtensions` sidecar (carries source primitives with no AgentSpec home, so nothing is silently dropped) | `IR = (AgentSpec, MigrationExtensions)` |
| `ledger.py` | Fidelity engine — accumulate decisions, render the report | `Ledger.record(primitive, source_ref, status, note, manual_step)`; `Ledger.render_markdown() -> str` |
| `importers/base.py` | Importer contract | `class Importer: name; detect(path)->bool; discover(path)->Sources; to_ir(sources, ledger)->IR` |
| `importers/claude_code.py` | Claude Code → IR (§6) | implements `Importer` |
| `importers/codex.py` | Codex → IR (§7) | implements `Importer` |
| `harness_map.py` | model string → Omnigent harness (itself a fidelity surface) | `resolve_harness(model, source) -> (harness, FidelityNote)` |
| `exporter/omnigent.py` | IR → Omnigent bundle dir; validate | `export(ir, out_dir) -> Path` (raises if the bundle fails `omnigent.spec.load`) |
| `cli.py` | UX | `omnigent-migrate <from-claude|from-codex|auto> <project> [-o out] [--dry-run]` |

`Status` enum = `TRANSLATED` (clean) · `DEGRADED` (mapped with caveats) · `UNSUPPORTED` (carried, manual step required).

---

## 5. IR — `AgentSpec` + `MigrationExtensions`

- The IR **is** omnigent's `AgentSpec` (a cross-framework agent model: executor/harness, model, prompt, tools, MCP, sub-agents, guardrails, skills). We import `omnigent` and build `AgentSpec` objects directly, so the exporter and validator are free.
- `MigrationExtensions` is a typed sidecar holding source primitives that have **no AgentSpec field** (e.g. Claude slash commands, raw hook scripts). These are NOT lost: they ride in the IR, surface in the report, and may be exported as comments/companion files. This keeps `AgentSpec` clean while honoring "maximal best-effort, nothing dropped."

---

## 6. Claude Code importer (maximal)

A Claude Code "project" is `.claude/` + root memory files. Mapping:

| Claude Code source | → Omnigent (`AgentSpec`) | Fidelity |
|---|---|---|
| `CLAUDE.md` (+ imported `@file` refs), `AGENTS.md` | `prompt` / `instructions` | **TRANSLATED** |
| `.claude/agents/*.md` (frontmatter `name`/`description`/`tools`/`model` + body) | one `agents/<name>` sub-spec each + `tools.agents: [...]`; body→prompt; `model`→harness (§8) | **TRANSLATED** |
| `.claude/skills/*/SKILL.md` | skills — **left in place** (`.claude/skills/` is host-discovered by Omnigent at cwd=project); recorded as translated-in-place | **TRANSLATED** |
| `.mcp.json`, `.claude.json`/`settings.json` `mcpServers` (stdio + http) | `tools.<name>: {type: mcp, command/args/env | url/headers}` | **TRANSLATED** |
| `settings.json` `permissions` (`allow`/`deny`/`defaultMode`) | guardrails (`blast_radius`, ask-mode) — approximate mapping | **DEGRADED** (note the approximation) |
| `settings.json` `hooks` (PreToolUse/PostToolUse/…) | Omnigent hooks are runtime-internal, not bundle-declarative; hook commands carried in `MigrationExtensions` | **UNSUPPORTED** → manual step |
| `.claude/commands/*.md` (slash commands) | best-effort: convert each to a bundled **skill** (a command is prose instructions); flagged | **DEGRADED** (command→skill is approximate) |
| `.claude-plugin/` + enabled plugins | expand enabled plugins' skills/agents into the IR where structure allows; record marketplace refs | **DEGRADED** |

**Tier inference:** project has `.claude/agents/*` → Omnigent **orchestrator** shape (supervisor prompt + `agents/` + `tools.agents`); none → **solo** bundle.

---

## 7. Codex importer

| Codex source | → Omnigent (`AgentSpec`) | Fidelity |
|---|---|---|
| `~/.codex/config.toml` + project config (`model`, `model_provider`) | `executor.config.harness` = `codex`/`codex-native`; `model` | **TRANSLATED** |
| `config.toml` `mcp_servers` | `tools.<name>: {type: mcp, …}` | **TRANSLATED** |
| `AGENTS.md` | `prompt`/`instructions` | **TRANSLATED** |
| Codex skills (codex skill path) | skills (repo-side) | **TRANSLATED** |
| `approval_policy` / sandbox settings | guardrails approximation | **DEGRADED** |

Codex is largely single-agent → a **solo** Omnigent bundle (no `agents/`). Codex features without an Omnigent equivalent → reported.

---

## 8. Model → harness mapping (`harness_map.py`)

A small, data-driven table; ambiguity is a fidelity note, not a guess:

| Source model pattern | Omnigent harness | Note |
|---|---|---|
| `claude-*` / `anthropic/*` | `claude-sdk` (or `claude-native` if a terminal is implied) | clean |
| `gpt-*`, `o1/o3/o4*`, `codex*` | `codex` (or `openai-agents`) | clean |
| `gemini-*` | `antigravity` | gated until agy ships → DEGRADED note |
| gateway/other (OpenRouter, Ollama, …) | `pi` (multi-model) + a gateway connection | DEGRADED |
| unknown | default per source (claude-sdk / codex) + **report** | UNSUPPORTED note |

---

## 9. Exporter

The exporter **serializes the `AgentSpec` IR into the bundle layout** — `config.yaml` from executor/prompt/os_env/tools/guardrails, and each sub-spec → `agents/<name>/config.yaml` — using a deterministic, idempotent YAML writer + `omnigent.spec.load` validation (`enforce_handler_allowlist=False`), the same write/validate approach proven in bundlegen (small utilities, reimplemented or shared — not a cross-repo dependency). Skills stay repo-side. A bundle that fails validation is a tool bug, not a user problem → fail loud with the offending field. Output layout:
```
<out>/                      # the Omnigent bundle
  config.yaml
  agents/<name>/config.yaml  # orchestrator shape only
  tools/mcp/*.yaml           # or inline tools.mcp
MIGRATION_REPORT.md          # the ledger, rendered
```
(Skills are NOT copied into the bundle — they stay repo-side in the source project's `.claude/skills/`, per the migration's repo-side finding.)

---

## 10. CLI / UX

```
omnigent-migrate from-claude  ./my-project [-o ./out] [--dry-run]
omnigent-migrate from-codex   ./my-project [-o ./out] [--dry-run]
omnigent-migrate auto         ./my-project          # detect source by markers
```
- `--dry-run`: run importers + render the report, **emit no bundle** (preview fidelity before committing).
- Always prints a fidelity summary (`N translated · M degraded · K unsupported`) and writes `MIGRATION_REPORT.md`.
- Exit non-zero only if the *exported bundle* fails validation (lenient-in/strict-out).

---

## 11. Fidelity philosophy (the product's moat)

Most migration tools lie about lossiness. This one's value is honesty:
- **Importers never abort.** Every primitive yields a ledger entry; degraded/unsupported ones get a concrete manual step.
- **The report is the deliverable**, co-equal with the bundle. It's reviewable, diffable, and a punch-list.
- **The output is always validated** against the real Omnigent loader — a migration that "succeeds" but produces an unrunnable bundle is worse than useless.

---

## 12. Testing

- **Fixture projects:** a representative `.claude/` project (subagents + skills + MCP + hooks + commands + permissions) and a `.codex/` project. Import → export → assert (a) the bundle passes `omnigent.spec.load`, (b) the ledger matches a golden report (statuses per primitive).
- **Unit:** each importer's per-primitive mapping; `harness_map`; `ledger` rendering.
- **Round-trip (supported subset):** `omnigent → claude-export → omnigent` identity for the cleanly-translatable core (reuses omnigent's round-trip discipline).
- **Real-world smoke:** run `from-claude` on an actual project (e.g. `askcv.ai`) → validate the bundle + human-review the report.

---

## 13. Relationship to bundlegen + the fleet

- The exporter **reuses bundlegen's write+validate approach** and adds the new core: `AgentSpec`→bundle serialization. The **template-composition half of bundlegen** (templates + `fleet.yaml` → config) is **superseded** — the accelerator builds the config from each project's *real* `AgentSpec` instead of canned `flavors`, which **resolves the earlier over-build** (the flavor taxonomy collapses).
- The hand-built fleet bundles become **outputs the accelerator regenerates** from each project's own Claude Code setup — `omnigent-fleet` becomes "run the accelerator over my projects," not a bespoke generator.
- `fleet.yaml` survives as a thin **batch manifest** (which projects to migrate), if wanted.

---

## 14. Upstream path

Package layout mirrors a future `omnigent/migrate/` module: `importers/`, `ir`, `harness_map`, `exporter` (already omnigent-internal), `cli` → `omnigent migrate`. Avoid private-API reach-through where a public one exists; keep the AgentSpec dependency surface small and documented. Goal: the eventual PR to `omnigent-ai/omnigent` is a **move, not a rewrite**.

---

## 15. Scope & decomposition

**v1 (this spec):** core (`ir`, `ledger`, `importers/base`, `harness_map`, `exporter`, `cli`) + **claude_code** + **codex** importers + the fixture/golden test suite + docs.
**Follow-on (separate specs):** additional importers (Cursor, Gemini-CLI, Windsurf, rdv/remote-dev), plugin-expansion depth, an importer SDK for third parties, the upstream PR.

---

## 16. Risks & open questions

- **AgentSpec is an internal API** — it may change across omnigent versions. Mitigation: pin + a thin adapter layer; round-trip tests catch drift.
- **`MigrationExtensions` export form** — comments in config.yaml vs a companion `.migration/` dir. Decide during implementation.
- **Plugin expansion** is open-ended (plugins vary) — v1 does best-effort + reports; deep plugin support is follow-on.
- **Command→skill conversion** is heuristic — validate it reads well on real commands; otherwise downgrade to UNSUPPORTED+report.
- **Codex format coverage** — we understand it less than Claude Code; budget importer time + fixtures accordingly.
- **agy/antigravity** target harness stays gated (gemini-model sources map to it with a DEGRADED note until `feat/antigravity` ships).

---

## 17. Acceptance criteria (v1)

- `omnigent-migrate from-claude <fixture>` produces a bundle that **passes `omnigent.spec.load`** + a `MIGRATION_REPORT.md` whose statuses match the golden.
- Same for `from-codex <fixture>`.
- A Claude project **with subagents** → orchestrator-shaped bundle (`agents/` + `tools.agents`); **without** → solo bundle.
- Hooks / slash commands appear as DEGRADED/UNSUPPORTED with concrete manual steps (never silently dropped).
- `--dry-run` emits the report and **no** bundle.
- Real-world smoke on `askcv.ai` validates + the report is human-sensible.
- Full gate: `uv run pytest`, `ruff check`, `mypy --strict` clean.
