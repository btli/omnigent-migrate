"""Shared importer helpers (frontmatter parsing, name sanitizing, os_env)."""

from __future__ import annotations

import re
from typing import Any

from ruamel.yaml import YAML

_yaml = YAML(typ="safe")
_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]")


def _sanitize(name: str) -> str:
    return _NAME_RE.sub("-", name) or "agent"


def _frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return (_yaml.load(parts[1]) or {}), parts[2].lstrip("\n")
    return {}, text


def _os_env() -> dict[str, Any]:
    return {"type": "caller_process", "cwd": ".", "sandbox": {"type": "none"}}
