"""omnigent-migrate CLI."""

from __future__ import annotations

from pathlib import Path

import click

from omnigent_migrate.exporter import export
from omnigent_migrate.importers.claude_code import ClaudeCodeImporter
from omnigent_migrate.ledger import Ledger, Status


@click.group()
def main() -> None:
    """Migrate an agent setup from another framework to Omnigent."""


@main.command(name="from-claude")
@click.argument("project", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("-o", "--out", type=click.Path(file_okay=False, path_type=Path), default=None,
              help="Output bundle dir (default: <project>/.omnigent).")
@click.option("--dry-run", is_flag=True, help="Render the fidelity report; emit no bundle.")
def from_claude(project: Path, out: Path | None, dry_run: bool) -> None:
    """Import a Claude Code project into an Omnigent bundle."""
    ledger = Ledger()
    bundle = ClaudeCodeImporter().to_bundle(project, ledger)
    report_md = ledger.render_markdown()
    if dry_run:
        # A dry run previews only — render the report to stdout, never mutate the source.
        click.echo(f"DRY RUN  {project.name} (no files written)\n")
        click.echo(report_md)
    else:
        out_dir = out or (project / ".omnigent")
        export(bundle, out_dir)
        (out_dir / "MIGRATION_REPORT.md").write_text(report_md)
        click.echo(f"OK  migrated {project.name} -> {out_dir}")
        click.echo(f"  report: {out_dir / 'MIGRATION_REPORT.md'}")
    s = ledger.summary()
    click.echo(
        f"  {s[Status.TRANSLATED]} translated · {s[Status.DEGRADED]} degraded · "
        f"{s[Status.UNSUPPORTED]} unsupported"
    )
