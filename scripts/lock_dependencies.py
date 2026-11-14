"""Regenerate exact installed dependency graphs after a clean pip install -e '.[dev]'."""

import importlib.metadata as metadata
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]


def lock(requirements):
    queue = [Requirement(value) for value in requirements]
    visited = set()
    versions = {}
    while queue:
        requirement = queue.pop()
        name = canonicalize_name(requirement.name)
        extras = {"", *requirement.extras}
        key = (name, tuple(sorted(extras)))
        if key in visited:
            continue
        visited.add(key)
        distribution = metadata.distribution(name)
        versions[name] = distribution.version
        for child in distribution.requires or []:
            dependency = Requirement(child)
            if not dependency.marker or any(
                dependency.marker.evaluate({"extra": extra}) for extra in extras
            ):
                queue.append(dependency)
    return (
        "# Python 3.13; generated from a verified installation. Regenerate with scripts/lock_dependencies.py.\n"
        + "\n".join(f"{name}=={version}" for name, version in sorted(versions.items()))
        + "\n"
    )


Path("requirements.lock").write_text(lock(project["dependencies"]), encoding="utf-8")
Path("requirements-dev.lock").write_text(
    lock([*project["dependencies"], *project["optional-dependencies"]["dev"]]), encoding="utf-8"
)
print("Wrote exact runtime and development dependency locks")
