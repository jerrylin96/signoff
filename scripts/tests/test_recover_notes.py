"""Tests for scripts/recover_notes.py (Phase 5 Gate 0 notes recovery).

Covers: reconstruction from [SIGNOFF *] commits, payload-file ingestion for
targets whose objects don't exist locally (pre-extraction attestations),
idempotency, append semantics on pre-existing notes, cat_sort_uniq
compatibility (gsa-core.md §2.5), and malformed-target skipping.
"""

import importlib.util
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from signoff_mcp.tests.helpers import commit_file, git, init_repo  # noqa: E402

_SPEC = importlib.util.spec_from_file_location(
    "recover_notes",
    os.path.join(os.path.dirname(__file__), "..", "recover_notes.py"),
)
recover_notes = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(recover_notes)

MISSING_COMMIT = "453c633078ecdd82d93c33eefac4d5f4cbe2ef55"
MISSING_TREE = "83679c5222ef2c7a7b8e5c83bc56c526d7f95567"


def attestation_message(reviewed_sha, tree_sha, extra=""):
    short = reviewed_sha[:7]
    return (
        f"[SIGNOFF {short}]: human comprehension and risk attestation\n"
        "\n"
        "Signoff-Spec-Version: 1.0\n"
        "Signoff-Status: VERIFIED_BY_HUMAN\n"
        f"Signoff-Reviewed-Commit-SHA: {reviewed_sha}\n"
        f"Signoff-Reviewed-Tree-SHA: {tree_sha}\n"
        "Signoff-Verified-By: tester@example.com\n" + extra
    )


@pytest.fixture
def repo(tmp_path):
    r = init_repo(tmp_path / "repo")
    commit_file(r, "a.txt", "hello", "initial commit")
    return r


def add_attestation(repo):
    reviewed = git(repo, "rev-parse", "HEAD").stdout.strip()
    tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    git(repo, "commit", "--allow-empty", "-m", attestation_message(reviewed, tree))
    return reviewed, tree


def notes_show(repo, target):
    return git(repo, "notes", "--ref=signoff", "show", target).stdout


def test_reconstructs_notes_for_reviewed_commit_and_tree(repo):
    reviewed, tree = add_attestation(repo)
    assert recover_notes.recover(str(repo), "HEAD", []) == 0
    for target in (reviewed, tree):
        assert f"Signoff-Reviewed-Commit-SHA: {reviewed}" in notes_show(repo, target)


def test_idempotent_second_run_creates_no_commit(repo):
    add_attestation(repo)
    recover_notes.recover(str(repo), "HEAD", [])
    ref1 = git(repo, "rev-parse", "refs/notes/signoff").stdout.strip()
    recover_notes.recover(str(repo), "HEAD", [])
    ref2 = git(repo, "rev-parse", "refs/notes/signoff").stdout.strip()
    assert ref1 == ref2


def test_payload_file_attaches_to_missing_objects(repo, tmp_path):
    payload = tmp_path / "attestation.txt"
    payload.write_text(attestation_message(MISSING_COMMIT, MISSING_TREE))
    assert recover_notes.recover(str(repo), "HEAD", [str(payload)]) == 0
    listing = git(repo, "ls-tree", "-r", "refs/notes/signoff").stdout
    assert MISSING_COMMIT in listing
    assert MISSING_TREE in listing
    # The annotated objects don't exist locally, but the note blobs do.
    blob = [ln for ln in listing.splitlines() if MISSING_COMMIT in ln][0].split()[2]
    assert MISSING_COMMIT in git(repo, "cat-file", "blob", blob).stdout


def test_appends_to_existing_note_and_preserves_it(repo):
    reviewed, tree = add_attestation(repo)
    git(repo, "notes", "--ref=signoff", "add", "-m", "pre-existing note", reviewed)
    recover_notes.recover(str(repo), "HEAD", [])
    note = notes_show(repo, reviewed)
    assert "pre-existing note" in note
    assert f"Signoff-Reviewed-Commit-SHA: {reviewed}" in note


def test_recognizes_cat_sort_uniq_rewritten_note(repo):
    reviewed, tree = add_attestation(repo)
    recover_notes.recover(str(repo), "HEAD", [])
    # Simulate a §2.5 cat_sort_uniq merge: note becomes sorted unique lines.
    sorted_note = "\n".join(sorted(set(notes_show(repo, reviewed).splitlines()))) + "\n"
    git(repo, "notes", "--ref=signoff", "remove", reviewed)
    git(repo, "notes", "--ref=signoff", "add", "-m", sorted_note, reviewed)
    ref1 = git(repo, "rev-parse", "refs/notes/signoff").stdout.strip()
    recover_notes.recover(str(repo), "HEAD", [])
    assert git(repo, "rev-parse", "refs/notes/signoff").stdout.strip() == ref1


def test_reconstructed_ref_merges_with_cat_sort_uniq(repo, tmp_path):
    reviewed, tree = add_attestation(repo)
    recover_notes.recover(str(repo), "HEAD", [])
    # Diverged notes ref (as another clone would produce), then §2.5 merge.
    git(repo, "notes", "--ref=other", "add", "-m", "diverged note", reviewed)
    git(
        repo, "notes", "--ref=signoff", "merge", "-s", "cat_sort_uniq", "refs/notes/other"
    )
    note = notes_show(repo, reviewed)
    assert "diverged note" in note
    assert f"Signoff-Reviewed-Commit-SHA: {reviewed}" in note


def test_malformed_target_skipped(repo, capsys):
    reviewed = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(
        repo,
        "commit",
        "--allow-empty",
        "-m",
        attestation_message(reviewed, "b96a7889c2258c1f1282cef20f05accc"),  # 32 hex
    )
    recover_notes.recover(str(repo), "HEAD", [])
    assert "malformed" in capsys.readouterr().out
    listing = git(repo, "ls-tree", "-r", "refs/notes/signoff").stdout
    assert "b96a7889" not in listing


def test_non_attestation_commits_ignored(repo):
    commit_file(repo, "b.txt", "x", "mentions [SIGNOFF abc1234]: in body only\n\nnot a subject match")
    reviewed, tree = add_attestation(repo)
    recover_notes.recover(str(repo), "HEAD", [])
    listing = git(repo, "ls-tree", "-r", "refs/notes/signoff").stdout
    assert len(listing.splitlines()) == 2  # reviewed commit + tree only


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _recent_attestations_in_local_main():
    """The clone below sees this repo's local branches; require a main branch
    whose history already carries the three recent attestations."""
    proc = subprocess.run(
        ["git", "log", "--format=%s", r"--grep=^\[SIGNOFF ", "main"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0 and all(
        f"[SIGNOFF {short}]" in proc.stdout for short in ("a4d1c6c", "daf4939", "979cb45")
    )


@pytest.mark.skipif(
    not _recent_attestations_in_local_main(),
    reason="shallow clone or stale local main",
)
def test_end_to_end_against_this_repo(tmp_path):
    """The workflow's exact invocation, against a local clone of this repo."""
    clone = tmp_path / "clone"
    subprocess.run(
        ["git", "clone", "-q", REPO_ROOT, str(clone)], check=True, capture_output=True
    )
    git(clone, "config", "user.email", "tester@example.com")
    git(clone, "config", "user.name", "Tester")
    fixture = os.path.join(
        REPO_ROOT, "signoff_mcp", "tests", "fixtures", "production_attestation.txt"
    )
    assert recover_notes.recover(str(clone), "origin/main", [fixture]) == 0
    # Recent attestations: notes resolve on the reviewed commits in main.
    for reviewed in ("a4d1c6c", "daf4939", "979cb45"):
        assert "VERIFIED_BY_HUMAN" in notes_show(clone, reviewed)
    # Pre-extraction production attestation: entry present for missing object.
    listing = git(clone, "ls-tree", "-r", "refs/notes/signoff").stdout
    assert MISSING_COMMIT in listing
