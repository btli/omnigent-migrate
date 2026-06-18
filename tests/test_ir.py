from omnigent_migrate.ir import Bundle


def test_bundle_defaults() -> None:
    b = Bundle(config={"name": "x"})
    assert b.config["name"] == "x"
    assert b.agents == {}
