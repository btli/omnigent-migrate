from omnigent_migrate.importers._util import build_persona


def test_solo_persona_points_at_repo_context() -> None:
    p = build_persona("askcv.ai", ["CLAUDE.md"], skills_present=True, agents=[])
    assert "coding agent working in the askcv.ai repository" in p
    assert "Follow the guidance in the repo's CLAUDE.md" in p
    assert "skills under .claude/skills/" in p
    assert "orchestrator" not in p


def test_orchestrator_persona_lists_subagents() -> None:
    p = build_persona("remote-dev", ["CLAUDE.md", "AGENTS.md"], skills_present=False,
                      agents=[("reviewer", "Reviews diffs"), ("ui", "Designs UI")])
    assert "orchestrator for the remote-dev repository" in p
    assert "- reviewer: Reviews diffs" in p
    assert "- ui: Designs UI" in p
    assert "delegate" in p.lower()
    assert "CLAUDE.md / AGENTS.md" in p


def test_persona_with_no_context_is_clean() -> None:
    p = build_persona("x", [], skills_present=False, agents=[])
    assert p.strip() == "You are a coding agent working in the x repository."
