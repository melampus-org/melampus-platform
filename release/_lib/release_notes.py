#!/usr/bin/env python3
"""Auto-assemble release notes from CHANGELOG and git history.

Usage:
  release_notes.py <version> [--prev-tag vX.Y.Z]
Prints markdown suitable for a GitHub Release body.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHANGELOG = os.path.join(REPO, "CHANGELOG.md")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True).stdout.strip()


def changelog_section(version: str) -> str | None:
    if not os.path.isfile(CHANGELOG):
        return None
    text = open(CHANGELOG, encoding="utf-8").read()
    m = re.search(rf"## \[{re.escape(version)}\][^\n]*\n(.*?)(?=\n## \[|\Z)", text, re.DOTALL)
    return m.group(1).strip() if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("version")
    ap.add_argument("--prev-tag", default=None)
    args = ap.parse_args()
    version = args.version

    out = [f"## v{version}", ""]

    section = changelog_section(version)
    if section:
        out += ["**Changelog:**", section, ""]

    rng = f"{args.prev_tag}..HEAD" if args.prev_tag else "HEAD"
    log = git("log", "--no-merges", "--pretty=format:- %s (%h)", rng)
    if log:
        out += ["**Commits:**", log, ""]

    if args.prev_tag:
        out += [f"_Compare: `{args.prev_tag}...v{version}`_", ""]

    out += [f"_Pin this version:_ `git clone --branch v{version} <repo>`"]
    sys.stdout.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
