from omnigent_migrate.distill.archetypes import CORE_IDS, LIBRARY


def test_library_has_core_and_specialists() -> None:
    ids = {a.id for a in LIBRARY}
    assert {"orchestrator", "implementer", "reviewer"} <= ids
    assert {"frontend", "backend", "db-migrations", "infra"} <= ids
    assert all(a.persona_template for a in LIBRARY)
    assert len(ids) == len(LIBRARY)  # ids unique
    assert CORE_IDS == {a.id for a in LIBRARY if a.kind == "core"}
