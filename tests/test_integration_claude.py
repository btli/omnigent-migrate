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
