"""IR = the public Omnigent bundle config (the config.yaml form omnigent.spec.load validates)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Bundle:
    """A migrated bundle: the root config.yaml plus orchestrator sub-agent configs."""

    config: dict[str, Any]
    agents: dict[str, dict[str, Any]] = field(default_factory=dict)
