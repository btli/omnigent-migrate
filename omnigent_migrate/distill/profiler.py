"""Deterministic project profiling — detect stack + existing agent config. No LLM."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

from omnigent_migrate.distill.schema import ProjectProfile
from omnigent_migrate.importers.claude_extras import read_settings

# exact dependency names -> framework/db/test/security labels
_DEP_MARKERS: dict[str, dict[str, str]] = {
    "frameworks": {"next": "next.js", "react": "react", "vue": "vue", "svelte": "svelte",
                   "fastapi": "fastapi", "django": "django", "flask": "flask", "express": "express"},
    "db": {"drizzle-orm": "drizzle", "prisma": "prisma", "typeorm": "typeorm",
           "sqlalchemy": "sqlalchemy", "alembic": "alembic"},
    "test": {"vitest": "vitest", "jest": "jest", "playwright": "playwright",
             "@playwright/test": "playwright", "cypress": "cypress", "pytest": "pytest"},
    "security": {"next-auth": "auth", "authlib": "auth", "stripe": "payments"},
    "data_ml": {"torch": "torch", "tensorflow": "tensorflow", "pandas": "pandas"},
}


def _read_json(p: Path) -> dict[str, Any]:
    try:
        data = json.loads(p.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _dep_names(project: Path) -> set[str]:
    """Return the lowercased set of declared dependency names."""
    names: set[str] = set()
    pkg = _read_json(project / "package.json")
    for key in ("dependencies", "devDependencies"):
        names.update(k.lower() for k in (pkg.get(key) or {}))
    pyproject = project / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_bytes().decode())
            for dep in (data.get("project") or {}).get("dependencies") or []:
                names.add(re.split(r"[<>=!~;\[ ]", dep, maxsplit=1)[0].lower())
            for group in ((data.get("dependency-groups") or {}).values()):
                for dep in group or []:
                    if isinstance(dep, str):
                        names.add(re.split(r"[<>=!~;\[ ]", dep, maxsplit=1)[0].lower())
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            pass
    req = project / "requirements.txt"
    if req.is_file():
        try:
            for line in req.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    names.add(re.split(r"[<>=!~;\[ ]", line, maxsplit=1)[0].lower())
        except (OSError, UnicodeDecodeError):
            pass
    return names


def _match(names: set[str], markers: dict[str, str]) -> list[str]:
    out: list[str] = []
    for needle, label in markers.items():
        if needle in names and label not in out:
            out.append(label)
    return out


def _has_k8s_manifest(d: Path) -> bool:
    for y in [*d.glob("*.yaml"), *d.glob("*.yml")]:
        try:
            t = y.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        if "apiVersion" in t or "kind:" in t:
            return True
    return False


def profile(project: Path) -> ProjectProfile:
    project = project.expanduser().resolve()
    names = _dep_names(project)

    languages: list[str] = []
    package_managers: list[str] = []
    if (project / "package.json").is_file():
        languages.append("typescript")
        package_managers.append("bun" if (project / "bun.lockb").is_file() or (project / "bun.lock").is_file() else "npm")
    if (project / "pyproject.toml").is_file() or (project / "requirements.txt").is_file():
        languages.append("python")
        package_managers.append("uv" if (project / "uv.lock").is_file() else "pip")

    infra: list[str] = []
    if (project / "Dockerfile").is_file() or (project / "docker-compose.yml").is_file():
        infra.append("docker")
    if any(project.glob("**/*.tf")):
        infra.append("terraform")
    k8s_dirs = [d for d in project.iterdir() if d.is_dir() and d.name in ("k8s", "kubernetes", "manifests")]
    if any(_has_k8s_manifest(d) for d in k8s_dirs):
        infra.append("kubernetes")

    settings = read_settings(project)
    agents_dir = project / ".claude" / "agents"
    existing: dict[str, Any] = {
        "agents": sorted(p.stem for p in agents_dir.glob("*.md")) if agents_dir.is_dir() else [],
        "skills": sum(1 for d in (project / ".claude" / "skills").glob("*/SKILL.md")) if (project / ".claude" / "skills").is_dir() else 0,
        "memory": [m for m in ("CLAUDE.md", "AGENTS.md") if (project / m).is_file()],
        "hooks": bool(settings.get("hooks")),
        "permissions": bool(settings.get("permissions")),
        "plugins": list((settings.get("enabledPlugins") or {})),
        "mcp": (project / ".mcp.json").is_file(),
    }

    pkg = _read_json(project / "package.json")
    monorepo = (
        (project / "pnpm-workspace.yaml").is_file()
        or "workspaces" in pkg
        or (project / "turbo.json").is_file()
        or (project / "nx.json").is_file()
    )

    return ProjectProfile(
        name=project.name,
        languages=languages,
        package_managers=package_managers,
        frameworks=_match(names, _DEP_MARKERS["frameworks"]),
        db=_match(names, _DEP_MARKERS["db"]),
        infra=infra,
        test=_match(names, _DEP_MARKERS["test"]),
        data_ml=_match(names, _DEP_MARKERS["data_ml"]),
        mobile=["flutter"] if (project / "pubspec.yaml").is_file() else [],
        security=_match(names, _DEP_MARKERS["security"]),
        ci=["github-actions"] if (project / ".github" / "workflows").is_dir() else [],
        docs=(project / "docs").is_dir(),
        repo_shape={"monorepo": monorepo},
        existing=existing,
    )
