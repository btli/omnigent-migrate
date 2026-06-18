from pathlib import Path

from click.testing import CliRunner

from omnigent_migrate.cli import main

FIXTURE = Path(__file__).parent / "fixtures" / "claude_project"


def test_from_claude_writes_bundle_and_report(tmp_path: Path) -> None:
    out = tmp_path / "out"
    res = CliRunner().invoke(main, ["from-claude", str(FIXTURE), "-o", str(out)])
    assert res.exit_code == 0, res.output
    assert (out / "config.yaml").is_file()
    assert (out / "MIGRATION_REPORT.md").is_file()
    assert "translated" in res.output


def test_dry_run_writes_no_bundle(tmp_path: Path) -> None:
    out = tmp_path / "out"
    res = CliRunner().invoke(main, ["from-claude", str(FIXTURE), "-o", str(out), "--dry-run"])
    assert res.exit_code == 0, res.output
    assert not (out / "config.yaml").exists()
    assert "DRY RUN" in res.output
