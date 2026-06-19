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
