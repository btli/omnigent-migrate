from pathlib import Path

import pytest

from omnigent_migrate.distill.distill import apply, propose, read_plan, write_plan
from omnigent_migrate.distill.schema import SpecialistSpec, Team, WorkerSpec
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


def test_apply_raises_on_name_collision(tmp_path: Path) -> None:
    # A specialist named 'reviewer' sanitizes to the same key as the core reviewer agent.
    team = Team(
        orchestrator={"persona": "You are the orchestrator."},
        workers=[WorkerSpec(name="backend", harness="claude-sdk", persona="Backend worker.")],
        reviewer=WorkerSpec(name="reviewer", harness="claude-sdk", persona="Code reviewer."),
        specialists=[
            SpecialistSpec(
                archetype="code-reviewer",
                name="reviewer",  # collides with the core reviewer
                persona="Specialist reviewer.",
            )
        ],
    )
    plan = tmp_path / "collision_plan.yaml"
    write_plan(team, plan)
    with pytest.raises(ValueError, match="duplicate agent name"):
        apply(FIXTURE, plan, tmp_path / "bundle", Ledger())
