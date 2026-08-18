# attested by humans — GSA verifier check & badge

A GitHub Actions check that verifies **Git Signoff Attestations** — the
machine-parsable records `/signoff` writes after a human passes a Socratic
comprehension interview about a diff — against your repository's history,
plus a README badge that shows the check is green.

Attestations are verified per the
[GSA v1.0 spec](../skills/signoff/specs/gsa-core.md) §5.1 lookup order:
git notes (`refs/notes/signoff`) on the commit and its tree, `[SIGNOFF *]`
attestation commits in the log, and the tree-SHA fallback that survives
squash merges.

## Install (two minutes)

**1.** Add `.github/workflows/signoff.yml` to your repository:

```yaml
name: attested by humans

on:
  pull_request:
  push:
    branches: [ main ]

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # full history — attestations live in it
      - uses: jerrylin96/signoff/verify@verify-v1.1
```

**2.** Add the badge to your README:

```markdown
[![attested by humans](https://github.com/OWNER/REPO/actions/workflows/signoff.yml/badge.svg)](https://github.com/OWNER/REPO/actions/workflows/signoff.yml)
```

Done. Pull requests now fail the check until the branch ends in a valid
attestation (run `/signoff` before merging), and your default branch badge
reads **attested by humans: passing**.

Pin tags do not move. Backward-compatible fixes ship as new `verify-v1.x`
tags; a breaking change to the action's inputs or pass criteria would ship
as `verify-v2`. Tracking `@main` works but couples your CI to this
repository's development pace.

> **If you pinned `@verify-v1`, move to `@verify-v1.1`.** `verify-v1`
> predates a fix for a bug that could destroy attestation notes you had
> created but not yet pushed: the verifier fetched origin's notes directly
> into `refs/notes/signoff`, force-overwriting local ones, while still
> reporting `PASS`. Verdicts are unaffected — only the note-handling side
> effect — so the upgrade is drop-in. Because pins never move, `verify-v1`
> keeps running the old behavior until you re-pin.

## What it checks

| Event | Mode | Passes when |
|---|---|---|
| `pull_request` | `head` | The PR head commit is (or carries) a valid attestation: an **empty** attestation commit attesting its own parent's commit and tree — the normal shape of a branch ending in `/signoff`; a non-empty attestation commit fails, so trailers cannot smuggle unreviewed changes — or a notes/log/tree-SHA match for the head commit. |
| `push` / anything else | `history` | The ref's history carries at least `require` (default 1) structurally valid attestations. |

Override with inputs:

```yaml
      - uses: jerrylin96/signoff/verify@verify-v1.1
        with:
          mode: history      # or: head
          target: main       # commit (head) or ref (history)
          require: '1'       # history mode: minimum valid attestations
```

The verifier is a single stdlib-only Python file
([`verify_signoff.py`](verify_signoff.py)) — no dependencies beyond git and
Python 3.10+. Copy it into any CI system; GitHub Actions is just the
packaged path.

Running it is non-destructive to your signoff notes: it fetches origin's
notes into an isolated mirror (`refs/notes/signoff-verify`) and never writes
to `refs/notes/signoff` — ensuring any unpushed local attestations remain
intact and verifiable (gsa-core §5.1).

## What a green badge means — and doesn't

Green means: a human answered a Socratic interview about this code in their
own words, acknowledged its named trade-offs and risks, and accepted
accountability — and the record of that survives in git, tamper-evident.
It does **not** mean the code is correct; it means a named human
understands it. That is exactly the claim, no more.

Two enforcement caveats. First, the check is advisory until you add a
branch protection rule (or repository ruleset) on your default branch that
requires it — without that, a red check does not block the merge button.
Second, unsigned trailers are self-attested: they verify that a
structurally valid GSA record binds to this exact code state, not who wrote
it. Where independent identity assurance matters, combine the gate with
signed attestation commits (`git commit -S`, GSA §2.4) and your platform's
signature verification.
