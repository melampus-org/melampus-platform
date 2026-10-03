#!/usr/bin/env python3
"""PR-side release guard for simple single-package repos.

Checks against the latest v* git tag:
  1. VERSION is strictly greater than the last released tag,
  2. CHANGELOG.md has a [X.Y.Z] entry for the new version.

Usage:
  version_check.py [--strict] [--prev-version X.Y.Z] [--markdown FILE]
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bump  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VERSION_FILE = os.path.join(REPO, "VERSION")
CHANGELOG = os.path.join(REPO, "CHANGELOG.md")


def read_version() -> str:
    if not os.path.isfile(VERSION_FILE):
        return ""
    return open(VERSION_FILE, encoding="utf-8").read().strip()


def latest_tag_version() -> str | None:
    try:
        out = subprocess.run(
            ["git", "tag", "--list", "v*"],
            cwd=REPO, capture_output=True, text=True, check=True,
        ).stdout
    except subprocess.CalledProcessError:
        return None
    versions = []
    for line in out.splitlines():
        tag = line.strip()
        if not tag.startswith("v"):
            continue
        try:
            versions.append(bump.parse(tag[1:]))
        except ValueError:
            pass
    if not versions:
        return None
    hi = max(versions)
    return f"{hi[0]}.{hi[1]}.{hi[2]}"


def changelog_has(version: str) -> bool:
    if not os.path.isfile(CHANGELOG):
        return False
    return f"[{version}]" in open(CHANGELOG, encoding="utf-8").read()


def check(prev_override: str | None) -> dict:
    new = read_version()
    prev = prev_override or latest_tag_version()
    problems: list[str] = []
    notes: list[str] = []

    if not new:
        problems.append("`VERSION` is missing or empty")
        return {"new": new, "prev": prev, "problems": problems, "notes": notes, "declared": "none"}

    declared = bump.declared_level(prev, new)
    if prev and declared == "none":
        problems.append(f"version `{new}` is not greater than the last release `{prev}` — bump VERSION")

    if not changelog_has(new):
        problems.append(f"`CHANGELOG.md` has no `[{new}]` entry — every release needs change notes")

    return {"new": new, "prev": prev, "problems": problems, "notes": notes, "declared": declared}


def report_md(result: dict) -> str:
    lines = ["## Release version guard", ""]
    ok = not result["problems"]
    lines.append("✅ Version bump looks correct." if ok else "❌ Version bump issues — see below.")
    lines.append("")
    lines.append(f"### {result['prev'] or '(first release)'} → **{result['new'] or '?'}**")
    lines.append(f"- declared bump: **{result['declared']}**")
    for p in result["problems"]:
        lines.append(f"- ❌ {p}")
    for n in result["notes"]:
        lines.append(f"- ℹ️ {n}")
    if not result["problems"]:
        lines.append("- ✅ version increment and changelog entry are consistent")
    lines.append("")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--prev-version", default=None)
    ap.add_argument("--markdown")
    args = ap.parse_args()

    result = check(args.prev_version)
    md = report_md(result)
    if args.markdown:
        open(args.markdown, "w", encoding="utf-8").write(md)
    print(md)
    if args.strict and result["problems"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
