#!/usr/bin/env python3
"""Git Signoff Attestation (GSA) verifier — stdlib-only, single file.

Verifies GSA v1.0 attestations (skills/signoff/specs/gsa-core.md) against a
repository's history using the §5.1 lookup order: git notes
(refs/notes/signoff) on the commit and its tree, then [SIGNOFF *]
attestation commits in the log, with the tree-SHA fallback for squash
merges and rebases.

Two modes:

  head     Verify that a specific commit (default HEAD) is attested — the
           PR-gate check. A commit that is itself an attestation commit
           passes when it is empty (same tree as its parent) and attests
           its own parent's commit and tree (the normal shape of a branch
           ending in /signoff); a non-empty attestation commit fails, so
           trailers cannot smuggle unreviewed changes past the gate.
           For 2-parent merge commits (e.g. GitHub standard PR merges),
           verifies that HEAD^{tree} cleanly matches git merge-tree HEAD^1 HEAD^2
           and that the merged PR head HEAD^2 is validly attested.
  history  Verify that a ref's history carries valid attestations — the
           repo-badge check. Passes when at least --require valid
           attestations (default 1) are found.

Exit 0 on pass, 1 on fail. No dependencies beyond Python 3.10+ and git;
copy this file anywhere or run it via the companion composite action.

Verification is non-destructive to your signoff notes: origin's notes are
fetched into an isolated mirror ref, never into refs/notes/signoff, so an
attestation you have not pushed yet survives a verifier run.
"""

import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys

NOTES_REF = "refs/notes/signoff"
# The verifier's own isolated mirror of origin's notes. Fetching origin straight
# into NOTES_REF force-overwrites attestation notes that have not been pushed
# yet — gsa-core §5.1 forbids exactly that, and a reviewer who runs /signoff
# offline and verifies before pushing would silently lose the record. This ref
# is the only ref verification writes; NOTES_REF is read and never modified.
NOTES_FETCH_REF = "refs/notes/signoff-verify"
SUBJECT_RE = re.compile(r"^\[SIGNOFF [0-9a-f]{7,40}\]: ")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
TRAILER_RE = re.compile(r"^(Signoff-[A-Za-z0-9-]+):\s*(.*)$")
REQUIRED_TRAILERS = (
    "Signoff-Spec-Version",
    "Signoff-Status",
    "Signoff-Reviewed-Commit-SHA",
    "Signoff-Reviewed-Tree-SHA",
    "Signoff-Verified-By",
)
VALID_STATUSES = ("VERIFIED_BY_HUMAN", "VERIFIED_BY_HUMAN_NO_TRANSCRIPT_DIGEST")


def git(repo, *args, check=True):
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc


def parse_trailers(payload):
    """Repeated-key-aware trailer parse; works on cat_sort_uniq note blobs."""
    trailers = {}
    for line in payload.splitlines():
        m = TRAILER_RE.match(line)
        if m:
            trailers.setdefault(m.group(1), []).append(m.group(2).strip())
    return trailers


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def validate(trailers):
    """Structural validation of one attestation's trailers -> list of problems."""
    problems = []
    for key in REQUIRED_TRAILERS:
        if key not in trailers:
            problems.append(f"missing {key}")
    for version in trailers.get("Signoff-Spec-Version", []):
        if version != "1.0":
            problems.append(f"unsupported Signoff-Spec-Version {version!r}")
    for status in trailers.get("Signoff-Status", []):
        if status not in VALID_STATUSES:
            problems.append(f"invalid Signoff-Status {status!r}")
    for key in ("Signoff-Reviewed-Commit-SHA", "Signoff-Reviewed-Tree-SHA"):
        for sha in trailers.get(key, []):
            if not SHA_RE.match(sha):
                problems.append(f"malformed {key} {sha!r}")
    for email in trailers.get("Signoff-Verified-By", []):
        if "@" not in email:
            problems.append(f"implausible Signoff-Verified-By {email!r}")

    # Cross-field status vs transcript digest check (GSA §2.2)
    statuses = trailers.get("Signoff-Status", [])
    digests = trailers.get("Signoff-Transcript-Digest", [])
    if "VERIFIED_BY_HUMAN" in statuses:
        if not digests:
            problems.append("status 'VERIFIED_BY_HUMAN' requires a Signoff-Transcript-Digest")
        else:
            for d in digests:
                if d == "unavailable":
                    problems.append("status 'VERIFIED_BY_HUMAN' requires sha256 transcript digest, got 'unavailable'")
                elif not DIGEST_RE.match(d):
                    problems.append(f"malformed Signoff-Transcript-Digest {d!r}")
    if "VERIFIED_BY_HUMAN_NO_TRANSCRIPT_DIGEST" in statuses:
        if not digests:
            problems.append("status 'VERIFIED_BY_HUMAN_NO_TRANSCRIPT_DIGEST' requires 'unavailable' digest")
        else:
            for d in digests:
                if d != "unavailable":
                    problems.append(
                        f"status 'VERIFIED_BY_HUMAN_NO_TRANSCRIPT_DIGEST' requires 'unavailable' digest, got {d!r}"
                    )

    return problems


def describe(trailers):
    who = ", ".join(trailers.get("Signoff-Verified-By", ["?"]))
    status = ", ".join(trailers.get("Signoff-Status", ["?"]))
    reviewed = ", ".join(s[:7] for s in trailers.get("Signoff-Reviewed-Commit-SHA", []))
    return f"reviewed={reviewed} status={status} by={who}"


def history_payloads(repo, ref):
    """(source, payload) for every [SIGNOFF *] commit reachable from ref."""
    proc = git(repo, "log", ref, "--format=%H", r"--grep=^\[SIGNOFF ", check=False)
    out = []
    for sha in proc.stdout.split():
        payload = git(repo, "log", "-1", "--format=%B", sha).stdout
        if SUBJECT_RE.match(payload):
            out.append((f"commit {sha[:7]}", payload))
    return out


def note_payloads(repo, target):
    """Every payload attached to `target`, across the local notes ref and the
    fetched mirror. Local notes are read first so an un-pushed attestation
    verifies without ever being overwritten by origin."""
    out = []
    for ref in (NOTES_REF, NOTES_FETCH_REF):
        proc = git(repo, "notes", f"--ref={ref}", "show", target, check=False)
        if proc.returncode == 0 and proc.stdout.strip() and proc.stdout not in out:
            out.append(proc.stdout)
    return out


def check_head(repo, target):
    """PR-gate check: is `target` (or, for an attestation commit, its parent,
    or for a 2-parent merge commit, its attested PR head) attested?
    Returns (passed, lines-to-print)."""
    commit = git(repo, "rev-parse", f"{target}^{{commit}}").stdout.strip()
    tree = git(repo, "rev-parse", f"{commit}^{{tree}}").stdout.strip()
    message = git(repo, "log", "-1", "--format=%B", commit).stdout

    if SUBJECT_RE.match(message):
        trailers = parse_trailers(message)
        problems = validate(trailers)
        parent = git(repo, "rev-parse", f"{commit}~1", check=False).stdout.strip()
        parent_tree = ""
        if parent:
            parent_tree = git(repo, "rev-parse", f"{parent}^{{tree}}", check=False).stdout.strip()
        if trailers.get("Signoff-Reviewed-Commit-SHA", [None])[0] != parent:
            problems.append("attestation commit does not attest its parent")
        if not parent_tree or tree != parent_tree:
            problems.append(
                "attestation commit is not empty (its tree differs from its parent's — "
                "it smuggles changes the attestation does not cover)"
            )
        if trailers.get("Signoff-Reviewed-Tree-SHA", [None])[0] != parent_tree:
            problems.append("attestation does not attest its parent's tree")
        if problems:
            return False, [f"FAIL: {target} is a malformed attestation commit: "
                           + "; ".join(problems)]
        return True, [
            f"PASS: {commit[:7]} is a valid attestation of its parent {parent[:7]}",
            f"  {describe(trailers)}",
        ]

    candidates = []
    for note_target, how in ((commit, "note on commit"), (tree, "note on tree")):
        for payload in note_payloads(repo, note_target):
            candidates.append((how, payload))

    for source, payload in candidates:
        trailers = parse_trailers(payload)
        if validate(trailers):
            continue
        if commit in trailers.get("Signoff-Reviewed-Commit-SHA", []) or tree in trailers.get(
            "Signoff-Reviewed-Tree-SHA", []
        ):
            return True, [
                f"PASS: {commit[:7]} attested via {source}",
                f"  {describe(trailers)}",
            ]

    parents = git(repo, "log", "-1", "--format=%P", commit, check=False).stdout.split()
    if len(parents) > 2:
        return False, [
            f"FAIL: merge commit {commit[:7]} is an octopus merge with {len(parents)} parents "
            "(only 2-parent merges supported for provenance verification)"
        ]
    if len(parents) == 2:
        p1, p2 = parents[0], parents[1]
        is_ancestor = git(repo, "merge-base", "--is-ancestor", p2, p1, check=False).returncode == 0
        if is_ancestor:
            return False, [
                f"FAIL: merge commit {commit[:7]} PR head {p2[:7]} is an ancestor of base {p1[:7]}"
            ]
        mproc = git(repo, "merge-tree", "--write-tree", p1, p2, check=False)
        if mproc.returncode != 0:
            return False, [
                f"FAIL: merge commit {commit[:7]} failed clean 3-way merge calculation between {p1[:7]} and {p2[:7]}"
            ]
        expected_tree = mproc.stdout.strip().splitlines()[0]
        if expected_tree != tree:
            return False, [
                f"FAIL: merge commit {commit[:7]} tree does not match clean 3-way merge of parents "
                f"{p1[:7]} and {p2[:7]} (manual conflict resolution or unreviewed changes introduced in merge)"
            ]
        ok2, lines2 = check_head(repo, p2)
        if ok2:
            return True, [
                f"PASS: merge commit {commit[:7]} verified via attested PR head {p2[:7]}",
                *[f"  {line}" for line in lines2],
            ]
        return False, [
            f"FAIL: merge commit {commit[:7]} PR head {p2[:7]} is not attested",
            *[f"  {line}" for line in lines2],
        ]

    for source, payload in history_payloads(repo, commit):
        trailers = parse_trailers(payload)
        if validate(trailers):
            continue
        if commit in trailers.get("Signoff-Reviewed-Commit-SHA", []) or tree in trailers.get(
            "Signoff-Reviewed-Tree-SHA", []
        ):
            return True, [
                f"PASS: {commit[:7]} attested via {source}",
                f"  {describe(trailers)}",
            ]

    return False, [
        f"FAIL: no valid attestation covers commit {commit[:7]} (or tree {tree[:7]})",
        "  Run /signoff on this branch before merging.",
    ]


def check_history(repo, ref, require):
    """Repo-badge check: does ref's history carry valid attestations?"""
    lines, valid = [], 0
    seen = set()
    payloads = history_payloads(repo, ref)
    annotated = []
    for ref in (NOTES_REF, NOTES_FETCH_REF):
        listing = git(repo, "notes", f"--ref={ref}", "list", check=False)
        if listing.returncode != 0:
            continue
        for entry in listing.stdout.split("\n"):
            if entry and entry.split()[1] not in annotated:
                annotated.append(entry.split()[1])
    for target in annotated:
        for payload in note_payloads(repo, target):
            payloads.append((f"note on {target[:7]}", payload))
    for source, payload in payloads:
        trailers = parse_trailers(payload)
        problems = validate(trailers)
        key = tuple(trailers.get("Signoff-Reviewed-Commit-SHA", [source]))
        if key in seen:
            continue
        seen.add(key)
        if problems:
            lines.append(f"  invalid ({source}): " + "; ".join(problems))
            continue
        valid += 1
        lines.append(f"  valid ({source}): {describe(trailers)}")
    verdict = "PASS" if valid >= require else "FAIL"
    lines.insert(
        0,
        f"{verdict}: {valid} valid attestation(s) in {ref} history"
        + (f" (required {require})" if verdict == "FAIL" else ""),
    )
    return valid >= require, lines


CONV_ID_SAFE_RE = re.compile(r"^[a-zA-Z0-9._-]+$")


def split_attestation_blocks(payload):
    """Split a note payload into individual attestation blocks (handles cat_sort_uniq concatenation)."""
    blocks = []
    raw_blocks = re.split(r"(?=(?:^|\n)\[SIGNOFF |\n\n(?=Signoff-))", payload.strip())
    for b in raw_blocks:
        b = b.strip()
        if b and ("Signoff-Spec-Version:" in b or SUBJECT_RE.search(b)):
            blocks.append(b)
    if not blocks and payload.strip():
        blocks.append(payload.strip())
    return blocks


def extract_attestation_trailers(repo, target):
    """Find and return trailers dict for target commit or tree."""
    commit_proc = git(repo, "rev-parse", f"{target}^{{commit}}", check=False)
    if commit_proc.returncode != 0:
        return None
    commit = commit_proc.stdout.strip()
    tree = git(repo, "rev-parse", f"{commit}^{{tree}}", check=False).stdout.strip()
    message = git(repo, "log", "-1", "--format=%B", commit, check=False).stdout

    # 1. Check target commit's own message
    if SUBJECT_RE.match(message) or "Signoff-Spec-Version:" in message:
        t = parse_trailers(message)
        if t.get("Signoff-Status"):
            return t

    # 2. Check notes on commit and tree
    candidates = []
    for note_target in (commit, tree):
        for payload in note_payloads(repo, note_target):
            for block in split_attestation_blocks(payload):
                candidates.append(block)

    for payload in candidates:
        t = parse_trailers(payload)
        if commit in t.get("Signoff-Reviewed-Commit-SHA", []) or tree in t.get(
            "Signoff-Reviewed-Tree-SHA", []
        ):
            return t

    # 3. Check if target is a 2-parent merge commit
    parents = git(repo, "log", "-1", "--format=%P", commit, check=False).stdout.split()
    if len(parents) == 2:
        p2_trailers = extract_attestation_trailers(repo, parents[1])
        if p2_trailers:
            return p2_trailers

    # 4. Check history payloads
    for _, payload in history_payloads(repo, commit):
        for block in split_attestation_blocks(payload):
            t = parse_trailers(block)
            if commit in t.get("Signoff-Reviewed-Commit-SHA", []) or tree in t.get(
                "Signoff-Reviewed-Tree-SHA", []
            ):
                return t

    return None


def check_audit(repo, target="HEAD", export_path=None):
    """Audit local transcript against signoff trailers on target."""
    trailers = extract_attestation_trailers(repo, target)
    if not trailers:
        return False, [f"FAIL: No signoff attestation found for {target}"]

    status = trailers.get("Signoff-Status", [""])[0]
    if status == "VERIFIED_BY_HUMAN_NO_TRANSCRIPT_DIGEST":
        return True, [
            f"[NOTICE] Attestation for {target} verified without transcript digest (status: {status})."
        ]

    conv_id = trailers.get("Signoff-Conversation-ID", [""])[0]
    if not conv_id or not CONV_ID_SAFE_RE.match(conv_id):
        return False, [f"FAIL: Malformed or unsafe Signoff-Conversation-ID {conv_id!r}"]

    expected_digest = trailers.get("Signoff-Transcript-Digest", [""])[0]
    bytes_str = trailers.get("Signoff-Transcript-Bytes", [""])[0]
    harness_id = trailers.get("Signoff-Harness-ID", [""])[0]

    try:
        nbytes = int(bytes_str)
        if nbytes < 0:
            raise ValueError()
    except (ValueError, TypeError):
        return False, [f"FAIL: Malformed Signoff-Transcript-Bytes {bytes_str!r}"]

    # Resolve transcript path
    if os.environ.get("SIGNOFF_TRANSCRIPT_FILE"):
        transcript_path = Path(os.environ["SIGNOFF_TRANSCRIPT_FILE"])
    else:
        home_dir = Path(os.environ.get("HOME") or os.environ.get("USERPROFILE") or Path.home())
        if harness_id == "claude-code":
            proc = git(repo, "rev-parse", "--show-toplevel", check=False)
            if proc.returncode == 0 and proc.stdout.strip():
                root = proc.stdout.strip()
            else:
                proc_common = git(repo, "rev-parse", "--git-common-dir", check=False)
                if proc_common.returncode == 0 and proc_common.stdout.strip():
                    root = proc_common.stdout.strip()
                else:
                    root = os.path.abspath(repo)
            try:
                root = str(Path(root).resolve())
            except Exception:
                pass
            slug = root.replace("/", "-")
            transcript_path = home_dir / ".claude" / "projects" / slug / f"{conv_id}.jsonl"
        elif harness_id == "antigravity-cli":
            transcript_path = (
                home_dir
                / ".gemini"
                / "antigravity-cli"
                / "brain"
                / conv_id
                / ".system_generated"
                / "logs"
                / "transcript.jsonl"
            )
        elif harness_id == "codex-cli":
            transcript_path = home_dir / ".codex" / "sessions" / f"{conv_id}.jsonl"
        elif harness_id == "generic-file":
            transcript_path = Path(conv_id)
        else:
            return False, [f"FAIL: Unsupported or unknown harness {harness_id!r}"]

    if not transcript_path.is_file():
        return False, [f"FAIL: Transcript file not found at {transcript_path}"]

    raw_bytes = transcript_path.read_bytes()[:nbytes]
    actual_digest = f"sha256:{hashlib.sha256(raw_bytes).hexdigest()}"

    if actual_digest != expected_digest:
        return False, [
            f"❌ MISMATCH: Transcript SHA-256 {actual_digest} does not match trailer {expected_digest}"
        ]

    if export_path:
        export_file = Path(export_path)
        export_file.parent.mkdir(parents=True, exist_ok=True)
        export_file.write_bytes(raw_bytes)

    lines = [
        f"✅ VALID MATCH: Transcript SHA-256 matches {expected_digest}",
        f"  Harness: {harness_id}",
        f"  Conversation ID: {conv_id}",
        f"  Bytes verified: {len(raw_bytes)}",
    ]
    if export_path:
        lines.append(f"  Exported snapshot to: {export_path}")
    return True, lines


def main(argv=None):
    p = argparse.ArgumentParser(description="Verify Git Signoff Attestations (GSA v1.0)")
    p.add_argument("--repo", default=".", help="repository to verify")
    p.add_argument("--mode", choices=("head", "history"), default="head")
    p.add_argument("--target", default="HEAD", help="commit (head mode) or ref (history mode)")
    p.add_argument("--require", type=int, default=1, help="history mode: minimum valid attestations")
    p.add_argument(
        "--audit",
        nargs="?",
        const="HEAD",
        default=None,
        metavar="COMMIT",
        help="audit local transcript against signoff trailers",
    )
    p.add_argument(
        "--export",
        default=None,
        metavar="PATH",
        help="export audited transcript snapshot to path (requires --audit)",
    )
    args = p.parse_args(argv)

    if args.export and args.audit is None:
        p.error("--export requires --audit")

    if args.audit is not None:
        ok, lines = check_audit(args.repo, target=args.audit, export_path=args.export)
        print("\n".join(lines))
        return 0 if ok else 1

    fetched = git(args.repo, "fetch", "origin", f"+{NOTES_REF}:{NOTES_FETCH_REF}", check=False)
    if args.mode == "head":
        ok, lines = check_head(args.repo, args.target)
    else:
        ok, lines = check_history(args.repo, args.target, args.require)
    if not ok and fetched.returncode != 0:
        # A failed notes fetch turns "attested, note unreachable" into the same
        # message as "never attested", sending the reader to re-run an interview
        # instead of at the network. Name the real cause — but stay quiet about
        # a remote that simply has no notes ref yet, which is the normal state
        # for a first-time adopter and not a fault.
        err = fetched.stderr.strip()
        if err and "couldn't find remote ref" not in err:
            lines.append(f"  warning: origin notes fetch failed ({err.splitlines()[-1]})")
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

