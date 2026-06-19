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
