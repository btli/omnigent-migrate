from pathlib import Path

from omnigent_migrate.exporter import export
from omnigent_migrate.importers.codex import CodexImporter
from omnigent_migrate.ledger import Ledger

FIXTURE = Path(__file__).parent / "fixtures" / "codex_project"


def test_codex_fixture_migrates_to_a_valid_bundle(tmp_path: Path) -> None:
    led = Ledger()
    bundle = CodexImporter().to_bundle(FIXTURE, led, config_path=FIXTURE / "config.toml")
    out = export(bundle, tmp_path / "b")  # raises ExportInvalid if the real loader rejects it
    assert (out / "config.yaml").is_file()
    assert not (out / "agents").exists()  # solo bundle
    assert (out / "MIGRATION_EXTENSIONS.yaml").is_file()  # approvals carried
