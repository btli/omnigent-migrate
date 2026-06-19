import json
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


def test_next_auth_only_does_not_trigger_nextjs(tmp_path: Path) -> None:
    # A project whose only JS dep is 'next-auth' must NOT produce 'next.js' in frameworks.
    pkg = {"dependencies": {"next-auth": "4"}}
    (tmp_path / "package.json").write_text(json.dumps(pkg))
    p = profile(tmp_path)
    assert "next.js" not in p.frameworks
    assert "auth" in p.security


def test_empty_manifests_dir_no_kubernetes(tmp_path: Path) -> None:
    # A directory named 'manifests' with no yaml files must NOT add 'kubernetes'.
    pkg = {"dependencies": {}}
    (tmp_path / "package.json").write_text(json.dumps(pkg))
    (tmp_path / "manifests").mkdir()
    p = profile(tmp_path)
    assert "kubernetes" not in p.infra
