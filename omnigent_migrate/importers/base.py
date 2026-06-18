"""Importer contract."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from omnigent_migrate.ir import Bundle
from omnigent_migrate.ledger import Ledger


class Importer(Protocol):
    name: str

    def detect(self, project: Path) -> bool: ...

    def to_bundle(self, project: Path, ledger: Ledger) -> Bundle: ...
