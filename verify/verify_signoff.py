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
           passes when it attests its own parent (the normal shape of a
           branch ending in /signoff).
  history  Verify that a ref's history carries valid attestations — the
           repo-badge check. Passes when at least --require valid
           attestations (default 1) are found.

Exit 0 on pass, 1 on fail. No dependencies beyond Python 3.10+ and git;
copy this file anywhere or run it via the companion composite action.
"""

import argparse
import re
import subprocess
import sys

NOTES_REF = "refs/notes/signoff"
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


def validate(trailers):
    """Structural validation of one attestation's trailers -> list of problems."""
    problems = []
    for key in REQUIRED_TRAILERS:
        if key not in trailers:
            problems.append(f"missing {key}")
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


def note_payload(repo, target):
    proc = git(repo, "notes", f"--ref={NOTES_REF}", "show", target, check=False)
    return proc.stdout if proc.returncode == 0 else None


def check_head(repo, target):
    """PR-gate check: is `target` (or, for an attestation commit, its parent)
    attested? Returns (passed, lines-to-print)."""
    commit = git(repo, "rev-parse", f"{target}^{{commit}}").stdout.strip()
    tree = git(repo, "rev-parse", f"{commit}^{{tree}}").stdout.strip()
    message = git(repo, "log", "-1", "--format=%B", commit).stdout

    if SUBJECT_RE.match(message):
        trailers = parse_trailers(message)
        problems = validate(trailers)
        parent = git(repo, "rev-parse", f"{commit}~1", check=False).stdout.strip()
        if trailers.get("Signoff-Reviewed-Commit-SHA", [None])[0] != parent:
            problems.append("attestation commit does not attest its parent")
        if problems:
            return False, [f"FAIL: {target} is a malformed attestation commit: "
                           + "; ".join(problems)]
        return True, [
            f"PASS: {commit[:7]} is a valid attestation of its parent {parent[:7]}",
            f"  {describe(trailers)}",
        ]

    candidates = []
    for note_target, how in ((commit, "note on commit"), (tree, "note on tree")):
        payload = note_payload(repo, note_target)
        if payload:
            candidates.append((how, payload))
    candidates += history_payloads(repo, commit)

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
    return False, [
        f"FAIL: no valid attestation covers commit {commit[:7]} (or tree {tree[:7]})",
        "  Run /signoff on this branch before merging.",
    ]


def check_history(repo, ref, require):
    """Repo-badge check: does ref's history carry valid attestations?"""
    lines, valid = [], 0
    seen = set()
    payloads = history_payloads(repo, ref)
    listing = git(repo, "notes", f"--ref={NOTES_REF}", "list", check=False)
    if listing.returncode == 0:
        for entry in listing.stdout.split("\n"):
            if entry:
                target = entry.split()[1]
                payload = note_payload(repo, target)
                if payload:
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


def main(argv=None):
    p = argparse.ArgumentParser(description="Verify Git Signoff Attestations (GSA v1.0)")
    p.add_argument("--repo", default=".", help="repository to verify")
    p.add_argument("--mode", choices=("head", "history"), default="head")
    p.add_argument("--target", default="HEAD", help="commit (head mode) or ref (history mode)")
    p.add_argument("--require", type=int, default=1, help="history mode: minimum valid attestations")
    args = p.parse_args(argv)

    git(args.repo, "fetch", "origin", f"+{NOTES_REF}:{NOTES_REF}", check=False)
    if args.mode == "head":
        ok, lines = check_head(args.repo, args.target)
    else:
        ok, lines = check_history(args.repo, args.target, args.require)
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
