"""Regression tests for .github/workflows/tag.yml.

The pin-tag workflow creates non-release tags (verify-v1, ...) that cloud
sessions cannot push through the git proxy. Its release-tag guard originally
used the glob `v*`, which also matched `verify-v1` — so the workflow rejected
the very tag it exists to create, and the failure only surfaced post-merge in
Actions. These tests extract the guard pattern and the pin list from the
workflow itself (never a hand-copy, which would drift) and exercise the glob
through the same shell that runs it.
"""

import os
import re
import subprocess

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "tag.yml")

GUARD_RE = re.compile(r"^\s*(\S+)\)\s*echo \"Release tags", re.MULTILINE)
PINS_RE = re.compile(r"^\s*PINS:\s*(.+?)\s*$", re.MULTILINE)


def workflow_text():
    with open(WORKFLOW, encoding="utf-8") as f:
        return f.read()


def guard_pattern():
    m = GUARD_RE.search(workflow_text())
    assert m, "release-tag guard not found in tag.yml"
    return m.group(1)


def glob_matches(pattern, value):
    """Evaluate the workflow's own case-glob in bash, as the workflow does."""
    script = f'case "$1" in\n  {pattern}) exit 0 ;;\nesac\nexit 1\n'
    return subprocess.run(["bash", "-c", script, "bash", value]).returncode == 0


@pytest.mark.parametrize("pin", ["verify-v1", "verify-v2", "verify-v1.1", "verify-v1.2"])
def test_pin_tags_are_not_rejected_as_release_tags(pin):
    assert not glob_matches(guard_pattern(), pin), (
        f"tag.yml's release-tag guard rejects pin tag {pin!r}"
    )


@pytest.mark.parametrize("release", ["v0.1.0", "v0.3.0", "v1.0.0", "v10.2.3"])
def test_release_tags_are_still_rejected(release):
    assert glob_matches(guard_pattern(), release), (
        f"tag.yml's release-tag guard lets release tag {release!r} through"
    )


def test_declared_pins_survive_the_guard():
    m = PINS_RE.search(workflow_text())
    assert m, "PINS not declared in tag.yml"
    pins = m.group(1).split()
    assert pins, "PINS is empty"
    for pin in pins:
        assert not glob_matches(guard_pattern(), pin), (
            f"declared pin {pin!r} would be rejected by the workflow's own guard"
        )
