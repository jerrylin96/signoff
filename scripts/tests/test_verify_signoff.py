"""Tests for verify/verify_signoff.py (the badge-backing CI verifier).

Covers: PR-gate head mode (attestation tip, missing attestation, integrity
failure), tree-SHA fallback via notes after a squash merge, history mode
counting/validation/dedup, and an end-to-end run against this repository.
"""

import importlib.util
import os
import subprocess

import pytest

import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from signoff_mcp.tests.helpers import commit_file, git, init_repo  # noqa: E402

_SPEC = importlib.util.spec_from_file_location(
    "verify_signoff",
    os.path.join(os.path.dirname(__file__), "..", "..", "verify", "verify_signoff.py"),
)
verify_signoff = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(verify_signoff)


def attestation_message(reviewed_sha, tree_sha, spec_version="1.0"):
    version = f"Signoff-Spec-Version: {spec_version}\n" if spec_version else ""
    return (
        f"[SIGNOFF {reviewed_sha[:7]}]: human comprehension and risk attestation\n"
        "\n"
        f"{version}"
        "Signoff-Status: VERIFIED_BY_HUMAN\n"
        f"Signoff-Reviewed-Commit-SHA: {reviewed_sha}\n"
        f"Signoff-Reviewed-Tree-SHA: {tree_sha}\n"
        "Signoff-Verified-By: tester@example.com\n"
    )


@pytest.fixture
def repo(tmp_path):
    r = init_repo(tmp_path / "repo")
    commit_file(r, "a.txt", "hello", "initial commit")
    return r


def attest_head(repo, message=None):
    reviewed = git(repo, "rev-parse", "HEAD").stdout.strip()
    tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    git(
        repo,
        "commit",
        "--allow-empty",
        "-m",
        message or attestation_message(reviewed, tree),
    )
    return reviewed, tree


def test_head_mode_passes_on_attestation_tip(repo):
    reviewed, _ = attest_head(repo)
    ok, lines = verify_signoff.check_head(str(repo), "HEAD")
    assert ok
    assert reviewed[:7] in "\n".join(lines)


def test_head_mode_fails_without_attestation(repo):
    ok, lines = verify_signoff.check_head(str(repo), "HEAD")
    assert not ok
    assert "FAIL" in lines[0]


def test_head_mode_fails_when_attestation_does_not_attest_parent(repo):
    bogus = "0" * 40
    attest_head(repo, attestation_message(bogus, "1" * 40))
    ok, lines = verify_signoff.check_head(str(repo), "HEAD")
    assert not ok
    assert "does not attest its parent" in lines[0]


def test_head_mode_tree_fallback_via_note_after_squash(repo, tmp_path):
    reviewed, tree = attest_head(repo)
    payload = attestation_message(reviewed, tree)
    # Squash-merge shape: a new commit with the same tree, different SHA,
    # attestation commit absent; only the note on the tree survives.
    squashed = init_repo(tmp_path / "squashed")
    commit_file(squashed, "a.txt", "hello", "squash-merged")
    assert git(squashed, "rev-parse", "HEAD^{tree}").stdout.strip() == tree
    git(squashed, "notes", "--ref=refs/notes/signoff", "add", "-m", payload, "HEAD^{tree}")
    ok, lines = verify_signoff.check_head(str(squashed), "HEAD")
    assert ok
    assert "note on tree" in lines[0]


def test_history_mode_counts_valid_and_reports_invalid(repo):
    attest_head(repo)
    commit_file(repo, "b.txt", "x", "more work")
    # Pre-spec attestation (no Signoff-Spec-Version): reported, not counted.
    attest_head(repo, attestation_message("2" * 40, "3" * 40, spec_version=None))
    ok, lines = verify_signoff.check_history(str(repo), "HEAD", require=1)
    text = "\n".join(lines)
    assert ok
    assert "1 valid attestation(s)" in lines[0]
    assert "missing Signoff-Spec-Version" in text
    ok, lines = verify_signoff.check_history(str(repo), "HEAD", require=2)
    assert not ok


def test_history_mode_dedupes_note_and_commit_payloads(repo):
    reviewed, tree = attest_head(repo)
    payload = attestation_message(reviewed, tree)
    git(repo, "notes", "--ref=refs/notes/signoff", "add", "-m", payload, reviewed)
    ok, lines = verify_signoff.check_history(str(repo), "HEAD", require=1)
    assert ok
    assert "1 valid attestation(s)" in lines[0]


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _recent_attestations_in_local_main():
    proc = subprocess.run(
        ["git", "log", "--format=%s", r"--grep=^\[SIGNOFF ", "main"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0 and "[SIGNOFF 979cb45]" in proc.stdout


@pytest.mark.skipif(
    not _recent_attestations_in_local_main(),
    reason="shallow clone or stale local main",
)
def test_end_to_end_against_this_repo():
    """History mode passes on main; head mode passes on an attestation tip."""
    ok, lines = verify_signoff.check_history(REPO_ROOT, "main", require=1)
    assert ok, lines
    ok, lines = verify_signoff.check_head(REPO_ROOT, "5bec5ee")
    assert ok, lines
