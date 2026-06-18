from pathlib import Path

from omnigent_migrate.exporter import export
from omnigent_migrate.importers.claude_code import ClaudeCodeImporter
from omnigent_migrate.ledger import Ledger

FIXTURE = Path(__file__).parent / "fixtures" / "claude_project"


def test_fixture_migrates_to_a_valid_bundle(tmp_path: Path) -> None:
    led = Ledger()
    bundle = ClaudeCodeImporter().to_bundle(FIXTURE, led)
    out = export(bundle, tmp_path / "b")  # raises ExportInvalid if the real omnigent loader rejects it
    assert (out / "config.yaml").is_file()
    assert (out / "agents" / "reviewer" / "config.yaml").is_file()
    assert led.summary()  # non-empty


def test_enriched_fixture_full_fidelity(tmp_path: Path) -> None:
    led = Ledger()
    bundle = ClaudeCodeImporter().to_bundle(FIXTURE, led)
    out = export(bundle, tmp_path / "b")  # raises ExportInvalid if the bundle is invalid
    # sidecar carries the un-mapped primitives
    sidecar = out / "MIGRATION_EXTENSIONS.yaml"
    assert sidecar.is_file()
    text = sidecar.read_text()
    assert "permissions" in text and "hooks" in text and "commands" in text
    # golden: status per deferred primitive
    by_primitive = {e.primitive: e.status.value for e in led.entries}
    assert by_primitive["permissions"] == "degraded"
    assert by_primitive["hooks"] == "unsupported"
    assert by_primitive["slash_commands"] == "degraded"
    assert by_primitive["plugins"] == "degraded"
    # report renders all three status sections + the scope note
    report = led.render_markdown()
    assert "## Translated" in report and "## Degraded" in report and "## Unsupported" in report
    assert "## Scope" in report
