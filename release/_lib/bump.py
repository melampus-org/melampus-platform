#!/usr/bin/env python3
"""Semver helpers shared by release guard and release notes tooling."""
from __future__ import annotations

import re

RANK = {"none": 0, "patch": 1, "minor": 2, "major": 3}
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def parse(v: str) -> tuple[int, int, int]:
    m = SEMVER_RE.match(v.strip().lstrip("v"))
    if not m:
        raise ValueError(f"not a semver: {v!r}")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def declared_level(old: str | None, new: str) -> str:
    """Bump level from old tag version to new declared version."""
    n = parse(new)
    if old is None:
        return "minor"
    o = parse(old)
    if n <= o:
        return "none"
    if n[0] != o[0]:
        return "major"
    if n[1] != o[1]:
        return "minor"
    return "patch"
