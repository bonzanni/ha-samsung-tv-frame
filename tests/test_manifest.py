"""Manifest requirement checks.

Home Assistant installs a custom integration's requirements with
``--constraint homeassistant/package_constraints.txt``. Any requirement this
manifest pins to a different version than core constrains is therefore
unsatisfiable: pip fails with ``ResolutionImpossible``, setup aborts before the
module is imported, and the config entry silently stays ``not_loaded`` with no
error in the log. That is the 0.9.1 regression -- see CHANGELOG.

The failure is invisible to a dev environment pinned to an older Home Assistant
than production, so these tests guard the class of bug rather than one version.
"""
from __future__ import annotations

import json
from pathlib import Path

import homeassistant
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

MANIFEST = (
    Path(__file__).parent.parent
    / "custom_components"
    / "samsung_tv_frame"
    / "manifest.json"
)


def _core_constraints() -> dict[str, str]:
    """Map canonical package name -> version pinned by Home Assistant core."""
    path = Path(homeassistant.__file__).parent / "package_constraints.txt"
    constraints: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        name, _, version = line.partition("==")
        constraints[canonicalize_name(name)] = version.strip()
    return constraints


def _conflicts(requirements: list[str], constraints: dict[str, str]) -> list[str]:
    """Return requirements pip could not satisfy under ``constraints``."""
    found = []
    for req_str in requirements:
        req = Requirement(req_str)
        constrained = constraints.get(canonicalize_name(req.name))
        if constrained is None:
            continue  # core does not manage this package: free to pin
        if not req.specifier.contains(constrained, prereleases=True):
            found.append(f"{req_str} (core constrains {req.name}=={constrained})")
    return found


def test_manifest_requirements_do_not_conflict_with_core_constraints() -> None:
    """Every pinned requirement must accept the version core constrains."""
    requirements = json.loads(MANIFEST.read_text())["requirements"]
    conflicts = _conflicts(requirements, _core_constraints())
    assert not conflicts, (
        "manifest requirements conflict with Home Assistant's "
        f"package_constraints.txt, so setup will fail: {conflicts}. "
        "Drop the requirement and depend on the core integration that "
        "provides it, or widen the specifier."
    )


def test_conflict_detector_catches_the_0_9_0_regression() -> None:
    """Pin the historical bug so the detector itself cannot rot.

    Version-independent: it feeds the exact 0.9.0 requirement list and the
    constraint from HA 2026.8.1 that broke production, rather than whatever
    Home Assistant happens to be installed here.
    """
    broken = [
        "samsungtvws[async,encrypted]==3.0.5",
        "wakeonlan==3.3.0",
        "async-upnp-client==0.46.2",
    ]
    conflicts = _conflicts(broken, {"async-upnp-client": "0.47.1"})
    assert len(conflicts) == 1
    assert "async-upnp-client==0.46.2" in conflicts[0]


def test_ssdp_matchers_declare_the_ssdp_dependency() -> None:
    """Using ssdp discovery requires depending on ssdp, which provides upnp."""
    manifest = json.loads(MANIFEST.read_text())
    if manifest.get("ssdp"):
        assert "ssdp" in manifest.get("dependencies", [])
