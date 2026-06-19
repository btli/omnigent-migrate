# omnigent-migrate

Migrate **or** distill agent setups into **validated** Omnigent bundles.

Two modes, one validated-output engine:

- **Port** an existing Claude Code / Codex setup, 1:1 — `from-claude`, `from-codex`, `auto`.
- **Distill** a project's stack into a *designed* agent team — `distill`: profile the stack, select agent archetypes (LLM-assisted, with a deterministic fallback), review an editable plan, emit a validated bundle.

Every emitted bundle is validated against the real `omnigent.spec.load` (**lenient-in / strict-out**), and the report is honest about what translated, degraded, or couldn't be carried.

## Install

```bash
uv sync
```

Python 3.13+. Bundle validation requires the [`omnigent`](https://github.com/omnigent-ai/omnigent) package (currently expected as an editable install — see `pyproject.toml`'s `[tool.uv.sources]`). The `distill` LLM selector uses the Anthropic API — put `ANTHROPIC_API_KEY` in a local `.env`; **without a key, `distill` falls back to a deterministic rule-based selector** so it still works offline.

## Usage

### Port an existing setup

```bash
# Claude Code project -> Omnigent bundle + fidelity report
uv run omnigent-migrate from-claude ./my-project -o ./out
uv run omnigent-migrate from-claude ./my-project --dry-run     # preview the report, write nothing

# Codex setup (AGENTS.md + ~/.codex/config.toml) -> solo bundle
uv run omnigent-migrate from-codex ./my-project -o ./out

# Detect the source framework automatically
uv run omnigent-migrate auto ./my-project -o ./out
```

### Distill a stack into an agent team

```bash
# Profile the stack + propose a team -> an editable DISTILL_PLAN.yaml
uv run omnigent-migrate distill ./my-project
uv run omnigent-migrate distill ./my-project --no-llm          # deterministic, no API call

# Review / edit DISTILL_PLAN.yaml, then emit the validated bundle
uv run omnigent-migrate distill ./my-project --apply -o ./out
```

## How it works

- **Port mode** — an importer that is *lenient* (records every primitive, never aborts on bad input) → the IR (the public Omnigent bundle config) → an exporter that is *strict* (validates via the real loader, fails loud on its own bad output).
- **Distill mode** — a deterministic **profiler** (stack + existing config) → a curated **archetype library** (orchestrator, implementer workers, reviewer, + specialists like frontend / backend / db-migrations / infra) → a **selector** (Claude API, with a `RuleSelector` fallback) that decides *"does this concern earn its own sub-agent, or is it a skill?"* → an editable `DISTILL_PLAN.yaml` → emit.
- **Personas, not docs** — a bundle's `prompt` is the agent's *persona* (its role); `CLAUDE.md` / `AGENTS.md` / skills stay in the repo, where the harness auto-loads them at `cwd`.
- **Honest fidelity** — skills, MCP servers, permissions, hooks, slash-commands, and plugins are each reported `TRANSLATED` / `DEGRADED` / `UNSUPPORTED`, and anything carried-but-unmapped lands in a `MIGRATION_EXTENSIONS.yaml` sidecar. Nothing is silently dropped, and a status is never falsely "translated".

## Paradigm map (Claude Code → Omnigent)

| Claude Code | Omnigent |
|---|---|
| system prompt / agent identity | bundle `prompt` (a **persona**) |
| `CLAUDE.md` / `AGENTS.md` | repo-side, host-auto-loaded at `cwd` |
| skill | skill — host-discovered (bundle ∪ repo `.claude/skills` ∪ `~/.claude/skills`) |
| slash-command | skill |
| sub-agent (`.claude/agents/*.md`) | sub-agent (`agents/<name>/`) |
| plugin | decomposes → skills + sub-agents |
| MCP server | `tools.<name> {type: mcp}` |
| permissions / hooks | guardrails (runtime) / carried in the sidecar |

## Status

MVP. Port mode covers Claude Code + Codex; `distill` ships the core archetypes plus the frontend / backend / db-migrations / infra specialists. The full design lives in `docs/superpowers/specs/`. Output is always validated against the real Omnigent loader.
