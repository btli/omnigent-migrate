from omnigent_migrate.ledger import Ledger, Status


def test_record_summary_and_render() -> None:
    led = Ledger()
    led.record("memory", "CLAUDE.md", Status.TRANSLATED)
    led.record("hooks", "settings.json", Status.UNSUPPORTED, "no bundle-declarative hooks", "re-add hooks manually")
    assert led.summary() == {Status.TRANSLATED: 1, Status.DEGRADED: 0, Status.UNSUPPORTED: 1}
    md = led.render_markdown()
    assert "1 translated" in md and "1 unsupported" in md
    assert "**memory** (CLAUDE.md)" in md
    assert "Manual: re-add hooks manually" in md


def test_scope_notes_render() -> None:
    led = Ledger()
    led.record("memory", "CLAUDE.md", Status.TRANSLATED)
    led.note("hooks and permissions were not examined")
    md = led.render_markdown()
    assert "## Scope" in md
    assert "- hooks and permissions were not examined" in md
