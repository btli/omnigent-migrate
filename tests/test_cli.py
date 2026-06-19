from pathlib import Path

from click.testing import CliRunner

from omnigent_migrate.cli import main

FIXTURE = Path(__file__).parent / "fixtures" / "claude_project"
CODEX_FIXTURE = Path(__file__).parent / "fixtures" / "codex_project"
DISTILL_FIXTURE = Path(__file__).parent / "fixtures" / "distill_project"


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
    # a dry run must not mutate the source project, and must render the report to stdout
    assert not (FIXTURE / "MIGRATION_REPORT.md").exists()
    assert "DRY RUN" in res.output
    assert "# Migration Report" in res.output


def test_from_codex_writes_bundle(tmp_path: Path) -> None:
    out = tmp_path / "out"
    res = CliRunner().invoke(
        main,
        ["from-codex", str(CODEX_FIXTURE), "-o", str(out), "--config", str(CODEX_FIXTURE / "config.toml")],
    )
    assert res.exit_code == 0, res.output
    assert (out / "config.yaml").is_file()
    assert (out / "MIGRATION_REPORT.md").is_file()
    assert "translated" in res.output


def test_auto_picks_claude_for_dotclaude(tmp_path: Path) -> None:
    res = CliRunner().invoke(main, ["auto", str(FIXTURE), "-o", str(tmp_path / "o"), "--dry-run"])
    assert res.exit_code == 0, res.output
    assert "claude" in res.output.lower()


def test_distill_writes_plan(tmp_path: Path) -> None:
    res = CliRunner().invoke(main, ["distill", str(DISTILL_FIXTURE), "--no-llm",
                                    "--plan", str(tmp_path / "p.yaml")])
    assert res.exit_code == 0, res.output
    assert (tmp_path / "p.yaml").is_file()
    assert "backend" in res.output


def test_distill_apply_emits_bundle(tmp_path: Path) -> None:
    plan = tmp_path / "p.yaml"
    CliRunner().invoke(main, ["distill", str(DISTILL_FIXTURE), "--no-llm", "--plan", str(plan)])
    res = CliRunner().invoke(main, ["distill", str(DISTILL_FIXTURE), "--apply",
                                    "--plan", str(plan), "-o", str(tmp_path / "b")])
    assert res.exit_code == 0, res.output
    assert (tmp_path / "b" / "config.yaml").is_file()
