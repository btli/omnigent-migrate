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
