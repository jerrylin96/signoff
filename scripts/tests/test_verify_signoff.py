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


def test_head_mode_fails_on_non_empty_attestation_commit(repo):
    # Valid trailers attesting the parent, but the commit also smuggles a
    # file change the interview never covered — must fail the PR gate.
    reviewed = git(repo, "rev-parse", "HEAD").stdout.strip()
    tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    (repo / "smuggled.txt").write_text("unreviewed change")
    git(repo, "add", "smuggled.txt")
    git(repo, "commit", "-q", "-m", attestation_message(reviewed, tree))
    ok, lines = verify_signoff.check_head(str(repo), "HEAD")
    assert not ok
    assert "not empty" in lines[0]


def test_head_mode_fails_when_attestation_tree_mismatches_parent(repo):
    # Empty commit attesting the right parent commit but the wrong tree.
    reviewed = git(repo, "rev-parse", "HEAD").stdout.strip()
    attest_head(repo, attestation_message(reviewed, "1" * 40))
    ok, lines = verify_signoff.check_head(str(repo), "HEAD")
    assert not ok
    assert "parent's tree" in lines[0]


def test_head_mode_fails_on_unsupported_spec_version(repo):
    reviewed = git(repo, "rev-parse", "HEAD").stdout.strip()
    tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    attest_head(repo, attestation_message(reviewed, tree, spec_version="2.0"))
    ok, lines = verify_signoff.check_head(str(repo), "HEAD")
    assert not ok
    assert "Signoff-Spec-Version" in lines[0]


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


def test_verifier_never_overwrites_unpushed_local_notes(repo, tmp_path):
    """Regression: main() used to fetch origin into refs/notes/signoff with a
    force refspec, destroying attestation notes not yet pushed — the failure
    gsa-core §2.5 warns about, hit in practice while dogfooding. Origin's
    notes must land in the verifier's own mirror instead."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    git(repo, "remote", "add", "origin", str(origin))

    reviewed, tree = attest_head(repo)
    git(repo, "push", "-q", "origin", "HEAD:refs/heads/main")

    payload = attestation_message(reviewed, tree)
    # Note on the commit: pushed, so origin knows about it.
    git(repo, "notes", "--ref=refs/notes/signoff", "add", "-m", payload, reviewed)
    git(repo, "push", "-q", "origin", "refs/notes/signoff")
    # Note on the tree: local only — the record a force-fetch would erase.
    git(repo, "notes", "--ref=refs/notes/signoff", "add", "-m", payload, tree)

    before = git(repo, "rev-parse", "refs/notes/signoff").stdout.strip()
    assert verify_signoff.main(["--repo", str(repo), "--target", "HEAD"]) == 0

    after = git(repo, "rev-parse", "refs/notes/signoff", check=False).stdout.strip()
    assert after == before, "verifier moved refs/notes/signoff"
    shown = git(repo, "notes", "--ref=refs/notes/signoff", "show", tree, check=False)
    assert shown.returncode == 0 and "Signoff-Spec-Version" in shown.stdout, (
        "un-pushed local note was destroyed by the verifier"
    )


def test_head_mode_verifies_an_unpushed_local_note(repo, tmp_path):
    """A note that exists only locally still satisfies the §5.1 lookup."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    git(repo, "remote", "add", "origin", str(origin))

    reviewed = git(repo, "rev-parse", "HEAD").stdout.strip()
    tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    git(repo, "push", "-q", "origin", "HEAD:refs/heads/main")
    git(
        repo,
        "notes",
        "--ref=refs/notes/signoff",
        "add",
        "-m",
        attestation_message(reviewed, tree),
        reviewed,
    )

    ok, lines = verify_signoff.check_head(str(repo), "HEAD")
    assert ok, lines
    assert "note on commit" in lines[0]


def test_failed_notes_fetch_is_named_on_failure(repo, tmp_path, capsys):
    """A failing notes fetch must not masquerade as 'never attested'."""
    git(repo, "remote", "add", "origin", str(tmp_path / "nope.git"))
    assert verify_signoff.main(["--repo", str(repo), "--target", "HEAD"]) == 1
    out = capsys.readouterr().out
    assert "no valid attestation" in out
    assert "origin notes fetch failed" in out


def test_remote_without_notes_ref_stays_quiet(repo, tmp_path, capsys):
    """A remote that simply has no notes ref yet is the normal first-adopter
    state, not a fault — no warning for it."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "-q", "origin", "HEAD:refs/heads/main")
    assert verify_signoff.main(["--repo", str(repo), "--target", "HEAD"]) == 1
    out = capsys.readouterr().out
    assert "no valid attestation" in out
    assert "fetch failed" not in out


def test_no_warning_when_verification_passes(repo, tmp_path, capsys):
    """The warning is a failure diagnostic, not a general nag."""
    git(repo, "remote", "add", "origin", str(tmp_path / "nope.git"))
    attest_head(repo)
    assert verify_signoff.main(["--repo", str(repo), "--target", "HEAD"]) == 0
    assert "fetch failed" not in capsys.readouterr().out


def test_head_mode_passes_on_clean_2_parent_merge_with_attested_pr_head(repo):
    git(repo, "checkout", "-b", "feature")
    commit_file(repo, "b.txt", "feature work", "add b.txt")
    attest_head(repo)
    pr_head = git(repo, "rev-parse", "HEAD").stdout.strip()

    git(repo, "checkout", "main")
    git(repo, "merge", "--no-ff", "-m", "Merge pull request #1 from feature", "feature")

    merge_commit = git(repo, "rev-parse", "HEAD").stdout.strip()
    ok, lines = verify_signoff.check_head(str(repo), "HEAD")
    assert ok, lines
    text = "\n".join(lines)
    assert f"PASS: merge commit {merge_commit[:7]} verified via attested PR head {pr_head[:7]}" in text


def test_head_mode_passes_on_clean_2_parent_merge_with_attested_pr_head_via_notes(repo):
    git(repo, "checkout", "-b", "feature")
    commit_file(repo, "b.txt", "feature work", "add b.txt")
    pr_head = git(repo, "rev-parse", "HEAD").stdout.strip()
    pr_tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    payload = attestation_message(pr_head, pr_tree)
    git(repo, "notes", "--ref=refs/notes/signoff", "add", "-m", payload, pr_head)

    git(repo, "checkout", "main")
    git(repo, "merge", "--no-ff", "-m", "Merge pull request #1 from feature", "feature")

    merge_commit = git(repo, "rev-parse", "HEAD").stdout.strip()
    ok, lines = verify_signoff.check_head(str(repo), "HEAD")
    assert ok, lines
    assert f"PASS: merge commit {merge_commit[:7]} verified via attested PR head {pr_head[:7]}" in lines[0]


def test_head_mode_fails_on_merge_with_unattested_pr_head(repo):
    git(repo, "checkout", "-b", "feature")
    commit_file(repo, "b.txt", "un-attested feature work", "add b.txt")
    pr_head = git(repo, "rev-parse", "HEAD").stdout.strip()

    git(repo, "checkout", "main")
    git(repo, "merge", "--no-ff", "-m", "Merge pull request #1 from feature", "feature")

    merge_commit = git(repo, "rev-parse", "HEAD").stdout.strip()
    ok, lines = verify_signoff.check_head(str(repo), "HEAD")
    assert not ok
    assert f"FAIL: merge commit {merge_commit[:7]} PR head {pr_head[:7]} is not attested" in lines[0]


def test_head_mode_fails_on_dirty_conflict_resolved_merge(repo):
    git(repo, "checkout", "-b", "feature")
    commit_file(repo, "b.txt", "feature content", "feature edit")
    attest_head(repo)

    git(repo, "checkout", "main")
    commit_file(repo, "c.txt", "main content", "main edit")

    git(repo, "merge", "--no-ff", "--no-commit", "feature")
    # Smuggle an unreviewed file modification into the merge commit
    (repo / "smuggled_in_merge.txt").write_text("unreviewed")
    git(repo, "add", "smuggled_in_merge.txt")
    git(repo, "commit", "-m", "Dirty merge with smuggled file")

    merge_commit = git(repo, "rev-parse", "HEAD").stdout.strip()
    ok, lines = verify_signoff.check_head(str(repo), "HEAD")
    assert not ok
    assert f"FAIL: merge commit {merge_commit[:7]} tree does not match clean 3-way merge" in lines[0]


def test_head_mode_fails_on_redundant_merge_where_pr_head_is_ancestor(repo):
    commit_file(repo, "b.txt", "b", "commit b")
    p1 = git(repo, "rev-parse", "HEAD").stdout.strip()
    p2 = git(repo, "rev-parse", "HEAD~1").stdout.strip()
    tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    merge_commit = git(
        repo, "commit-tree", "-p", p1, "-p", p2, "-m", "Redundant merge", tree
    ).stdout.strip()
    git(repo, "update-ref", "HEAD", merge_commit)

    ok, lines = verify_signoff.check_head(str(repo), "HEAD")
    assert not ok
    assert f"FAIL: merge commit {merge_commit[:7]} PR head {p2[:7]} is an ancestor of base" in lines[0]


def test_head_mode_fails_on_octopus_merge(repo):
    git(repo, "checkout", "-b", "branch1")
    commit_file(repo, "b1.txt", "1", "branch 1")
    attest_head(repo)

    git(repo, "checkout", "main")
    git(repo, "checkout", "-b", "branch2")
    commit_file(repo, "b2.txt", "2", "branch 2")
    attest_head(repo)

    git(repo, "checkout", "main")
    commit_file(repo, "m.txt", "m", "main edit")
    git(repo, "merge", "branch1", "branch2", "-m", "Octopus merge")

    merge_commit = git(repo, "rev-parse", "HEAD").stdout.strip()
    ok, lines = verify_signoff.check_head(str(repo), "HEAD")
    assert not ok
    assert f"FAIL: merge commit {merge_commit[:7]} is an octopus merge with 3 parents" in lines[0]


def test_head_mode_passes_on_fast_forward_merge_with_attested_pr_head(repo):
    git(repo, "checkout", "-b", "feature")
    commit_file(repo, "b.txt", "feature work", "add b.txt")
    attest_head(repo)
    pr_head = git(repo, "rev-parse", "HEAD").stdout.strip()

    git(repo, "checkout", "main")
    git(repo, "merge", "--ff-only", "feature")

    ok, lines = verify_signoff.check_head(str(repo), "HEAD")
    assert ok, lines
    assert pr_head[:7] in "\n".join(lines)


def test_head_mode_fails_on_rebase_onto_advanced_base_without_resignoff(repo):
    git(repo, "checkout", "-b", "feature")
    commit_file(repo, "b.txt", "feature work", "add b.txt")
    attest_head(repo)

    git(repo, "checkout", "main")
    commit_file(repo, "c.txt", "main work", "advance main")

    git(repo, "checkout", "feature")
    git(repo, "rebase", "main")

    # In head mode: rebase rewrote parent SHA, so old attestation commit does not attest new parent
    ok, lines = verify_signoff.check_head(str(repo), "HEAD")
    assert not ok
    assert "does not attest its parent" in lines[0]

    # In history mode: historical attestation remains valid in history log
    ok_hist, lines_hist = verify_signoff.check_history(str(repo), "HEAD", require=1)
    assert ok_hist, lines_hist
    assert "1 valid attestation(s)" in lines_hist[0]

