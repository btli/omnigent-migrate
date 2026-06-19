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
