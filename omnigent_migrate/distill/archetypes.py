"""Curated archetype library for the distiller.

Defines LIBRARY (all archetypes) and CORE_IDS (ids of core archetypes).
Each Archetype carries a persona_template, trigger keywords, default skills,
and a harness assignment.
"""

from omnigent_migrate.distill.schema import Archetype

LIBRARY: list[Archetype] = [
    # ── Core archetypes ────────────────────────────────────────────────────
    Archetype(
        id="orchestrator",
        kind="core",
        triggers=[],
        persona_template=(
            "You are the orchestrator for the {project} repository. You coordinate"
            " specialized sub-agents and delegate work to them rather than doing it"
            " yourself. Decompose each request, route each part to the most appropriate"
            " sub-agent, and integrate their results. Follow the repo's own conventions"
            " (CLAUDE.md/AGENTS.md) and skills."
        ),
        default_skills=[],
        harness="claude-sdk",
    ),
    Archetype(
        id="implementer",
        kind="core",
        triggers=[],
        persona_template=(
            "You are a coding sub-agent for {project}. Implement the scoped task in"
            " your worktree, drive it to green (tests/lint/typecheck), and open a PR."
        ),
        default_skills=[],
        harness="claude-native",
    ),
    Archetype(
        id="reviewer",
        kind="core",
        triggers=[],
        persona_template=(
            "You review another agent's diff for {project} against its acceptance"
            " contract — report blocking/non-blocking issues with file:line; never edit."
        ),
        default_skills=[],
        harness="pi",
    ),
    # ── Specialist archetypes ──────────────────────────────────────────────
    Archetype(
        id="frontend",
        kind="specialist",
        triggers=["next.js", "react", "vue", "svelte"],
        persona_template=(
            "You own the {project} frontend (its JS/TS UI). Build and refine"
            " components, state, and styling per the repo's conventions."
        ),
        default_skills=[],
        harness="claude-native",
    ),
    Archetype(
        id="backend",
        kind="specialist",
        triggers=["fastapi", "django", "flask", "express"],
        persona_template=(
            "You own the {project} backend (its server/API). Implement endpoints,"
            " services, and data access per the repo's conventions."
        ),
        default_skills=[],
        harness="claude-native",
    ),
    Archetype(
        id="db-migrations",
        kind="specialist",
        triggers=["drizzle", "prisma", "alembic", "sqlalchemy"],
        persona_template=(
            "You own schema + migrations for {project}. Author and verify migrations"
            " safely; never apply destructive changes without review."
        ),
        default_skills=[],
        harness="claude-native",
    ),
    Archetype(
        id="infra",
        kind="specialist",
        triggers=["docker", "kubernetes", "terraform"],
        persona_template=(
            "You own {project} infrastructure (containers, k8s, IaC). Make changes"
            " safely and keep deploys reproducible."
        ),
        default_skills=[],
        harness="claude-native",
    ),
]

CORE_IDS: frozenset[str] = frozenset(a.id for a in LIBRARY if a.kind == "core")
