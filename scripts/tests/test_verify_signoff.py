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
        "Signoff-Transcript-Digest: sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n"
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


def test_head_mode_fails_on_squash_merge_onto_advanced_base_without_resignoff(repo):
    git(repo, "checkout", "-b", "feature")
    commit_file(repo, "b.txt", "feature work", "add b.txt")
    reviewed, tree = attest_head(repo)

    payload = attestation_message(reviewed, tree)
    git(repo, "notes", "--ref=refs/notes/signoff", "add", "-m", payload, reviewed)
    git(repo, "notes", "--ref=refs/notes/signoff", "add", "-m", payload, tree)

    git(repo, "checkout", "main")
    commit_file(repo, "c.txt", "main work", "advance main")

    git(repo, "merge", "--squash", "feature")
    git(repo, "commit", "-m", "Squash merge feature")

    # In head mode: squashed tree combines base + PR changes, so tree SHA lookup misses
    ok, lines = verify_signoff.check_head(str(repo), "HEAD")
    assert not ok
    assert "no valid attestation covers commit" in lines[0]

    # In history mode: note on reviewed commit remains valid in history
    ok_hist, lines_hist = verify_signoff.check_history(str(repo), "HEAD", require=1)
    assert ok_hist, lines_hist
    assert "1 valid attestation(s)" in lines_hist[0]


# --- Audit Mode Tests ---

import hashlib


def audit_attestation_message(
    reviewed_sha,
    tree_sha,
    harness_id="generic-file",
    conv_id="test-conv-123",
    digest="sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    nbytes="12",
    status="VERIFIED_BY_HUMAN",
):
    return (
        f"[SIGNOFF {reviewed_sha[:7]}]: human comprehension and risk attestation\n"
        "\n"
        "Signoff-Spec-Version: 1.0\n"
        f"Signoff-Status: {status}\n"
        f"Signoff-Reviewed-Commit-SHA: {reviewed_sha}\n"
        f"Signoff-Reviewed-Tree-SHA: {tree_sha}\n"
        f"Signoff-Harness-ID: {harness_id}\n"
        f"Signoff-Conversation-ID: {conv_id}\n"
        f"Signoff-Transcript-Digest: {digest}\n"
        f"Signoff-Transcript-Bytes: {nbytes}\n"
        "Signoff-Verified-By: tester@example.com\n"
    )


def test_check_audit_valid_match(repo, tmp_path, monkeypatch):
    t_file = tmp_path / "transcript.jsonl"
    raw_content = b'{"msg": "interview log"}\n{"msg": "extra"}\n'
    t_file.write_bytes(raw_content)
    nbytes = 25
    expected_digest = f"sha256:{hashlib.sha256(raw_content[:nbytes]).hexdigest()}"
    monkeypatch.setenv("SIGNOFF_TRANSCRIPT_FILE", str(t_file))

    reviewed = git(repo, "rev-parse", "HEAD").stdout.strip()
    tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    msg = audit_attestation_message(
        reviewed, tree, harness_id="generic-file", conv_id="conv-1",
        digest=expected_digest, nbytes=str(nbytes),
    )
    git(repo, "commit", "--allow-empty", "-m", msg)

    ok, lines = verify_signoff.check_audit(str(repo), "HEAD")
    assert ok is True
    combined = "\n".join(lines)
    assert "VALID MATCH" in combined
    assert expected_digest in combined


def test_check_audit_export(repo, tmp_path, monkeypatch):
    t_file = tmp_path / "transcript.jsonl"
    raw_content = b'{"msg": "first"}\n{"msg": "second"}\n'
    t_file.write_bytes(raw_content)
    nbytes = 17
    expected_digest = f"sha256:{hashlib.sha256(raw_content[:nbytes]).hexdigest()}"
    monkeypatch.setenv("SIGNOFF_TRANSCRIPT_FILE", str(t_file))

    reviewed = git(repo, "rev-parse", "HEAD").stdout.strip()
    tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    msg = audit_attestation_message(
        reviewed, tree, harness_id="generic-file", conv_id="conv-2",
        digest=expected_digest, nbytes=str(nbytes),
    )
    git(repo, "commit", "--allow-empty", "-m", msg)

    export_path = tmp_path / "exported.jsonl"
    ok, lines = verify_signoff.check_audit(str(repo), "HEAD", export_path=str(export_path))
    assert ok is True
    assert export_path.is_file()
    assert export_path.read_bytes() == raw_content[:nbytes]


def test_check_audit_mismatch(repo, tmp_path, monkeypatch):
    t_file = tmp_path / "transcript.jsonl"
    t_file.write_bytes(b'{"msg": "altered content"}\n')
    monkeypatch.setenv("SIGNOFF_TRANSCRIPT_FILE", str(t_file))

    reviewed = git(repo, "rev-parse", "HEAD").stdout.strip()
    tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    msg = audit_attestation_message(
        reviewed, tree, harness_id="generic-file", conv_id="conv-3",
        digest="sha256:" + "a" * 64, nbytes="10",
    )
    git(repo, "commit", "--allow-empty", "-m", msg)

    ok, lines = verify_signoff.check_audit(str(repo), "HEAD")
    assert ok is False
    assert any("MISMATCH" in line for line in lines)


def test_check_audit_missing_file(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("SIGNOFF_TRANSCRIPT_FILE", str(tmp_path / "nonexistent.jsonl"))

    reviewed = git(repo, "rev-parse", "HEAD").stdout.strip()
    tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    msg = audit_attestation_message(
        reviewed, tree, harness_id="generic-file", conv_id="conv-4",
        digest="sha256:" + "b" * 64, nbytes="10",
    )
    git(repo, "commit", "--allow-empty", "-m", msg)

    ok, lines = verify_signoff.check_audit(str(repo), "HEAD")
    assert ok is False
    assert any("Transcript file not found" in line for line in lines)


@pytest.mark.parametrize(
    "bad_conv_id",
    [
        "../../etc/passwd",
        "../escape",
        "session/123",
        "id;rm -rf",
        "id with space",
        "id\\0null",
    ],
)
def test_check_audit_security_path_traversal(repo, bad_conv_id):
    reviewed = git(repo, "rev-parse", "HEAD").stdout.strip()
    tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    msg = audit_attestation_message(
        reviewed, tree, harness_id="claude-code", conv_id=bad_conv_id,
        digest="sha256:" + "c" * 64, nbytes="10",
    )
    git(repo, "commit", "--allow-empty", "-m", msg)

    ok, lines = verify_signoff.check_audit(str(repo), "HEAD")
    assert ok is False
    assert any("Malformed or unsafe" in line for line in lines)


def test_check_audit_security_null_byte(repo, monkeypatch):
    trailers = {
        "Signoff-Spec-Version": ["1.0"],
        "Signoff-Status": ["VERIFIED_BY_HUMAN"],
        "Signoff-Reviewed-Commit-SHA": ["a" * 40],
        "Signoff-Reviewed-Tree-SHA": ["b" * 40],
        "Signoff-Harness-ID": ["claude-code"],
        "Signoff-Conversation-ID": ["id\x00null"],
        "Signoff-Transcript-Digest": ["sha256:" + "c" * 64],
        "Signoff-Transcript-Bytes": ["10"],
        "Signoff-Verified-By": ["tester@example.com"],
    }
    monkeypatch.setattr(verify_signoff, "extract_attestation_trailers", lambda repo, target: trailers)
    ok, lines = verify_signoff.check_audit(str(repo), "HEAD")
    assert ok is False
    assert any("Malformed or unsafe" in line for line in lines)



def test_check_audit_no_transcript_notice(repo):
    reviewed = git(repo, "rev-parse", "HEAD").stdout.strip()
    tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    msg = audit_attestation_message(
        reviewed, tree, harness_id="unknown", conv_id="unavailable",
        digest="unavailable", nbytes="unavailable",
        status="VERIFIED_BY_HUMAN_NO_TRANSCRIPT_DIGEST",
    )
    git(repo, "commit", "--allow-empty", "-m", msg)

    ok, lines = verify_signoff.check_audit(str(repo), "HEAD")
    assert ok is True
    assert any("NOTICE" in line for line in lines)


def test_check_audit_no_attestation_fails(repo):
    # Regular commit with no signoff message and no notes
    commit_file(repo, "feature.txt", "content\n", "regular commit")
    ok, lines = verify_signoff.check_audit(str(repo), "HEAD")
    assert ok is False
    assert any("No signoff attestation found" in line for line in lines)


def test_check_audit_from_git_notes_on_commit(repo, tmp_path, monkeypatch):
    t_file = tmp_path / "notes_transcript.jsonl"
    raw_content = b'{"msg": "note interview log"}\n'
    t_file.write_bytes(raw_content)
    nbytes = len(raw_content)
    expected_digest = f"sha256:{hashlib.sha256(raw_content).hexdigest()}"
    monkeypatch.setenv("SIGNOFF_TRANSCRIPT_FILE", str(t_file))

    commit_file(repo, "feature.txt", "content\n", "regular feature commit")
    reviewed = git(repo, "rev-parse", "HEAD").stdout.strip()
    tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()

    note_msg = audit_attestation_message(
        reviewed, tree, harness_id="generic-file", conv_id="conv-note-1",
        digest=expected_digest, nbytes=str(nbytes),
    )
    git(repo, "notes", "--ref=refs/notes/signoff", "add", "-m", note_msg, reviewed)

    ok, lines = verify_signoff.check_audit(str(repo), "HEAD")
    assert ok is True
    assert any("VALID MATCH" in line for line in lines)


def test_check_audit_from_git_notes_on_tree(repo, tmp_path, monkeypatch):
    t_file = tmp_path / "tree_transcript.jsonl"
    raw_content = b'{"msg": "tree note interview log"}\n'
    t_file.write_bytes(raw_content)
    nbytes = len(raw_content)
    expected_digest = f"sha256:{hashlib.sha256(raw_content).hexdigest()}"
    monkeypatch.setenv("SIGNOFF_TRANSCRIPT_FILE", str(t_file))

    commit_file(repo, "feature.txt", "content\n", "squash commit without commit note")
    reviewed = git(repo, "rev-parse", "HEAD").stdout.strip()
    tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()

    note_msg = audit_attestation_message(
        reviewed, tree, harness_id="generic-file", conv_id="conv-tree-1",
        digest=expected_digest, nbytes=str(nbytes),
    )
    # Attach note strictly to tree SHA
    git(repo, "notes", "--ref=refs/notes/signoff", "add", "-m", note_msg, tree)

    ok, lines = verify_signoff.check_audit(str(repo), "HEAD")
    assert ok is True
    assert any("VALID MATCH" in line for line in lines)


def test_check_audit_multi_note_block_selection(repo, tmp_path, monkeypatch):
    t_file = tmp_path / "multi_transcript.jsonl"
    raw_content = b'{"msg": "selected block"}\n'
    t_file.write_bytes(raw_content)
    nbytes = len(raw_content)
    expected_digest = f"sha256:{hashlib.sha256(raw_content).hexdigest()}"
    monkeypatch.setenv("SIGNOFF_TRANSCRIPT_FILE", str(t_file))

    commit_file(repo, "feature.txt", "content\n", "multi-note target commit")
    reviewed = git(repo, "rev-parse", "HEAD").stdout.strip()
    tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()

    other_sha = "1" * 40
    other_tree = "2" * 40
    block1 = audit_attestation_message(
        other_sha, other_tree, harness_id="generic-file", conv_id="other-conv",
        digest="sha256:" + "0" * 64, nbytes="10",
    )
    block2 = audit_attestation_message(
        reviewed, tree, harness_id="generic-file", conv_id="matching-conv",
        digest=expected_digest, nbytes=str(nbytes),
    )
    combined_notes = f"{block1}\n\n{block2}"
    git(repo, "notes", "--ref=refs/notes/signoff", "add", "-m", combined_notes, reviewed)

    ok, lines = verify_signoff.check_audit(str(repo), "HEAD")
    assert ok is True
    assert any("VALID MATCH" in line for line in lines)


def test_check_audit_harness_claude_code(repo, tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    root_str = str(repo.resolve())
    slug = root_str.replace("/", "-")
    conv_id = "claude-session-999"

    claude_dir = home / ".claude" / "projects" / slug
    claude_dir.mkdir(parents=True, exist_ok=True)
    transcript_file = claude_dir / f"{conv_id}.jsonl"
    raw_content = b'{"role": "assistant", "content": "audited session"}\n'
    transcript_file.write_bytes(raw_content)
    nbytes = len(raw_content)
    expected_digest = f"sha256:{hashlib.sha256(raw_content).hexdigest()}"

    reviewed = git(repo, "rev-parse", "HEAD").stdout.strip()
    tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    msg = audit_attestation_message(
        reviewed, tree, harness_id="claude-code", conv_id=conv_id,
        digest=expected_digest, nbytes=str(nbytes),
    )
    git(repo, "commit", "--allow-empty", "-m", msg)

    ok, lines = verify_signoff.check_audit(str(repo), "HEAD")
    assert ok is True
    assert any("VALID MATCH" in line for line in lines)


def test_check_audit_harness_antigravity_cli(repo, tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    conv_id = "agy-session-888"
    agy_dir = home / ".gemini" / "antigravity-cli" / "brain" / conv_id / ".system_generated" / "logs"
    agy_dir.mkdir(parents=True, exist_ok=True)
    transcript_file = agy_dir / "transcript.jsonl"
    raw_content = b'{"action": "test", "result": "ok"}\n'
    transcript_file.write_bytes(raw_content)
    nbytes = len(raw_content)
    expected_digest = f"sha256:{hashlib.sha256(raw_content).hexdigest()}"

    reviewed = git(repo, "rev-parse", "HEAD").stdout.strip()
    tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    msg = audit_attestation_message(
        reviewed, tree, harness_id="antigravity-cli", conv_id=conv_id,
        digest=expected_digest, nbytes=str(nbytes),
    )
    git(repo, "commit", "--allow-empty", "-m", msg)

    ok, lines = verify_signoff.check_audit(str(repo), "HEAD")
    assert ok is True
    assert any("VALID MATCH" in line for line in lines)


def test_check_audit_cli_flags(repo, tmp_path, monkeypatch):
    t_file = tmp_path / "cli_transcript.jsonl"
    raw_content = b'{"msg": "cli test"}\n'
    t_file.write_bytes(raw_content)
    nbytes = len(raw_content)
    expected_digest = f"sha256:{hashlib.sha256(raw_content).hexdigest()}"
    monkeypatch.setenv("SIGNOFF_TRANSCRIPT_FILE", str(t_file))

    reviewed = git(repo, "rev-parse", "HEAD").stdout.strip()
    tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    msg = audit_attestation_message(
        reviewed, tree, harness_id="generic-file", conv_id="cli-conv",
        digest=expected_digest, nbytes=str(nbytes),
    )
    git(repo, "commit", "--allow-empty", "-m", msg)

    export_path = tmp_path / "cli_exported.jsonl"

    # 1. --export without --audit should fail
    with pytest.raises(SystemExit):
        verify_signoff.main(["--repo", str(repo), "--export", str(export_path)])

    # 2. --audit with --export should succeed and write snapshot
    rc = verify_signoff.main(["--repo", str(repo), "--audit", "HEAD", "--export", str(export_path)])
    assert rc == 0
    assert export_path.is_file()
    assert export_path.read_bytes() == raw_content



