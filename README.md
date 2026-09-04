# signoff — Git Signoff Attestation (GSA)

[![attested by humans](https://github.com/jerrylin96/signoff/actions/workflows/signoff.yml/badge.svg)](https://github.com/jerrylin96/signoff/actions/workflows/signoff.yml)

**Verify that a human actually understands an AI-assisted diff before it merges.**

`/signoff` flips the usual review direction: instead of you interrogating the
AI's code, the AI interviews **you** — then records the outcome as a
machine-parsable, tamper-evident **Git Signoff Attestation** inside your
repository.

## What it does, in plain language

You (or your AI assistant) changed some code. Before that change merges — or
before its output goes into a paper, a report, or a decision — run `/signoff`.
The agent reads the full diff, then asks you a short series of pointed
questions across four fixed axes:

1. **Mechanics & intent** — what changed, and why this design?
2. **Trade-offs & edge cases** — what approximations were made, and are they intentional?
3. **Boundary conditions & failure loudness** — where does it break, and does it break *loudly* or silently?
4. **Ownership** — do you explicitly accept responsibility for the results and risks?

Vague answers don't pass. If you hand-wave, the agent pauses, explains the
relevant mechanics, and re-probes with a concrete scenario. When you do pass,
it writes an empty signed commit plus a mirrored git note
(`refs/notes/signoff`) recording who understood what, when, and at exactly
which state of the code — a record that survives squash merges and branch
deletion. The goal is preventing *cognitive surrender*: rubber-stamping AI
output nobody actually understands.

## Who it's for

**Software engineers** — the default interview profile emphasizes algorithmic
complexity, data-structure invariants, and API contract changes.

**Scientists, physicists, and mathematicians** — research code fails
differently: it rarely crashes, it produces *plausible-but-invalid results*.
An ML parameterization that quietly leaks energy, a unit slip between hPa and
Pa, a trend that vanishes at higher grid resolution — none of these throw an
exception. The shipped `domain-science` profile emphasizes unit and
dimensional validity, surrogate-vs-ground-truth boundaries, numerical
stability, statistical validity (leakage, multiple comparisons), uncertainty
quantification, and reproducibility (seeds, environments, data provenance).
And at the research frontier there is no oracle to check against —
`/signoff` deliberately does not claim to verify that the science is *right*;
it verifies that **you** know the assumptions, the validity regimes, and how
you'd notice drift outside them. That is exactly the part a human must own.

## Quickstart: Set up any repo in 60 seconds

Inside your repository root, run the zero-touch initializer (Python 3.10+ stdlib only — zero dependencies):

```bash
curl -fsSL https://raw.githubusercontent.com/jerrylin96/signoff/init-v5/init.py -o /tmp/signoff-init.py && python3 /tmp/signoff-init.py
```

The script automatically:
1. Detects your repo, branch, and stack (suggests science or general software profile).
2. Vendors the `/signoff` skill into `.claude/skills/signoff/` and/or `.agents/skills/signoff` (cross-client convention, auto-detected from repository markers, or explicitly chosen via `--skill-target {auto,claude,agents,both}`) — committed with your repo, it loads for every collaborator, across Claude Code, Antigravity, Codex, Cursor, and other agent harnesses alike, with nothing account-scoped to install.
3. Scaffolds `.github/workflows/signoff.yml` and `.signoff/profile.md`.
4. Injects the **attested by humans** badge into your `README.md`.
5. Automates GitHub Ruleset protection (via `gh` CLI or a 1-click settings link).
6. Creates feature branch `signoff/init` with your scaffolded setup ready for you to run `/signoff` and merge.

---

### What an interview looks like

```text
AI: [Axis 1 — Mechanics] What changed in this diff, and why did you choose this design?
You: Added an automatic fallback to /dev/tty when stdin is connected to a curl pipe.

AI: [Axis 2 — Edge Cases] What happens if this runs in a headless CI environment without a TTY?
You: It catches OSError cleanly and gracefully degrades to non-interactive default choices.

AI: [Axis 3 — Ownership] Do you accept accountability for these failure modes and CI configurations?
You: Confirmed, my email is dev@example.com.

AI: ✅ Attestation commit [SIGNOFF a1b2c3d] created! Your badge is green.
```

## How to use it: four steps

1. **Install** — run the 60-second initializer above, or pick the one row for your harness below.
2. **Open the PR** — review the diff as usual (when the branch's commits are well-structured, reading them one at a time shows what changed when and why far better than one squashed diff); the `verify-signoff` check runs red until the branch ends in a valid attestation. Attest *after* the diff is final: the attestation must be the last commit on the branch, so pushing anything after it turns the check red again (just re-run `/signoff`).
3. **Run** — from the branch you want to merge, type `/signoff` (adaptive default auto-selects intensity from diff; `--deep` for skeptical rigor, `--quick` for low-risk diffs subject to safety clamps).
4. **Answer, confirm, merge** — respond in your own words, acknowledge the named trade-offs and risks, confirm your email. The attestation commit and note are created and pushed with your branch; when `verify-signoff` turns green, merge as usual.

---

## Auditing & retrieving interview transcripts

Git signoff attestations bind the interview transcript's SHA-256 digest (`Signoff-Transcript-Digest`) into immutable git history and notes. Transcripts remain locally on the reviewer's laptop for privacy and security. Anyone — leads, reviewers, compliance auditors — can verify or audit the transcript at any time using the verifier CLI.

### The 3-Step Verification Loop (Auditor $\leftrightarrow$ Reviewer)

```text
Auditor (Lead / Compliance)                  Reviewer (Employee)
           │                                          │
           │  1. Request transcript snapshot          │
           │  (quotes commit or PR)                   │
           ├─────────────────────────────────────────>│
           │                                          │  2. Export snapshot:
           │                                          │     verify_signoff.py --audit HEAD
           │                                          │       --export transcript.jsonl
           │  3. Send transcript.jsonl                │
           │<─────────────────────────────────────────┤
           │                                          │
           │  4. Verify against git trailers:         │
           │     SIGNOFF_TRANSCRIPT_FILE=transcript.jsonl
           │     python3 verify_signoff.py --audit HEAD
           │                                          │
           │  Output: ✅ VALID MATCH                   │
```

#### Step 1: Auditor requests transcript
The auditor identifies the attestation on the commit or PR (e.g. `[SIGNOFF 979cb45]`) and asks the reviewer to export the session transcript.

#### Step 2: Reviewer exports transcript
On the machine where the signoff interview occurred, the reviewer runs the verifier CLI with `--audit` and `--export`:
```bash
python3 verify/verify_signoff.py --audit HEAD --export /tmp/transcript.jsonl
```
The verifier resolves the local transcript for the harness (`claude-code`, `antigravity-cli`, `codex-cli`, etc.), checks that the first $N$ bytes match the `Signoff-Transcript-Digest` trailer, and writes the snapshot to the specified path:
```text
✅ VALID MATCH: Transcript SHA-256 matches sha256:1675b6...
  Harness: claude-code
  Conversation ID: 979cb45-session
  Bytes verified: 8432
  Exported snapshot to: /tmp/transcript.jsonl
```
The reviewer sends `/tmp/transcript.jsonl` to the auditor.

#### Step 3: Auditor verifies snapshot against git trailers
The auditor points `SIGNOFF_TRANSCRIPT_FILE` at the received file and audits the target commit:
```bash
SIGNOFF_TRANSCRIPT_FILE=/tmp/transcript.jsonl python3 verify/verify_signoff.py --audit HEAD
```
The verifier recomputes the SHA-256 digest and confirms it matches the git attestation byte-for-byte.

---

## Installation

One channel, everywhere: the skill is a self-contained folder of Markdown
that lives *in the repository under review*. Committed once, `/signoff`
works for every collaborator — no plugins, no marketplaces, no downloads,
nothing account-scoped.

| Where you work | One-time action |
|---|---|
| **Any repository (Zero-touch)** | `curl -fsSL https://raw.githubusercontent.com/jerrylin96/signoff/init-v5/init.py -o /tmp/signoff-init.py && python3 /tmp/signoff-init.py` (use `--skill-target {auto,claude,agents,both}` to control destinations) |
| **Any repository (manual)** | Copy this repo's `skills/signoff/` folder to `<your-repo>/.claude/skills/signoff/` (Claude Code) or `<your-repo>/.agents/skills/signoff/` (Antigravity, Codex, Cursor, etc.) and commit before running the initializer; an untracked skill destination now aborts as an unrelated working-tree change. Update by re-copying (or re-running the initializer) on new releases. |
| **Other harnesses (Antigravity, Codex, Cursor, …)** | Same folder, cross-client convention: copy `skills/signoff/` into `.agents/skills/signoff` (or `.claude/skills/signoff`) and set the transcript adapter env vars — full matrix in [HARNESSES.md](skills/signoff/HARNESSES.md). |

> [!NOTE]
> **Initializer Flags & Policy A:**
> - `--skill-target {auto,claude,agents,both}`: Selects target client destinations (defaults to auto-detect based on repo markers).
> - `--allow-dirty`: Permits unrelated unstaged/untracked work to remain in place. It still refuses any pre-staged change, any uncommitted or ignored state under paths the initializer manages, and all Policy A violations (symbolic links, parent-path collisions, unrelated non-empty directories, and destination-level `.gitignore` rules). This boundary prevents user work from being swept into the scaffold commit or overwritten during vendoring/rollback.

## Make it yours: changing what gets asked

The four axes above are fixed for everyone. What you customize is the
**interview profile** — a single, clearly delimited text block that weights
the questions toward your domain's failure modes. It is the sole
customization point of the skill; profiles can add domain emphases but can
never remove axes or lower pass criteria, so a customized interview is never
a weaker one.

**The dead-simple path — commit a profile to your own repository:**

1. In the repo you want reviewed, create `.signoff/profile.md`.
2. Paste in a shipped profile block —
   [`domain-science`](skills/signoff/profiles/domain-science.md) for research
   code, [`software-general`](skills/signoff/profiles/software-general.md)
   for classic engineering — or edit its bullets into your own.
3. Done. Every `/signoff` run on that repository now uses your profile — for
   every collaborator, on every install channel, surviving skill updates.

**Write your own profile for your lab or team:** copy a shipped profile as a
template, set your own `Profile-ID:` (lowercase, hyphens), and rewrite the
emphasis bullets to name *your* failure modes — conservation properties of a
new parameterization, grid-resolution sensitivity of a reported trend,
CFL-limited timestep choices, leakage between reanalysis training and
evaluation periods, what the ensemble spread does and doesn't capture —
whatever "wrong but plausible" looks like in your field.

**Science is probed by default:** even with no customization at all, any
diff that touches scientific computation — numpy/scipy/jax-style imports,
notebooks, RNG seeding, unit-bearing constants, netCDF/GRIB/zarr datasets —
automatically triggers the science questions on top of the active profile.

Every attestation records which question set actually ran: the profile ID
plus, for repo-supplied profiles, a content digest
(`Signoff-Agent: ... interview=standard/<your-profile-id>/sha256:<digest>`),
so downstream readers can always see which questions the human was held to —
and a diluted profile is distinguishable from a shipped one.

Other knobs: `SIGNOFF_PROFILE_FILE=<path>` overrides everything for one
machine; editing the block inside the vendored `SKILL.md` also works, but
re-vendoring on update overwrites such edits — prefer the repo-local
`.signoff/profile.md`. Full details:
[HARNESSES.md](skills/signoff/HARNESSES.md).

## What an attestation looks like

```text
[SIGNOFF <short-sha>]: human comprehension and risk attestation

Signoff-Spec-Version: 1.0
Signoff-Status: VERIFIED_BY_HUMAN
Signoff-Base-SHA: ...
Signoff-Reviewed-Commit-SHA: ...
Signoff-Reviewed-Tree-SHA: ...
Signoff-Harness-ID: claude-code
Signoff-Transcript-Digest: sha256:...
Signoff-Tradeoff: ...
Signoff-Risk: ...
Signoff-Verified-By: you@example.com
Signoff-Agent: harness=claude-code/2.x model=... reasoning=... interview=standard/software-general
```

Verification survives squash merges via the reviewed **tree SHA** and the
notes mirror — lookup order in [gsa-core.md §5](skills/signoff/specs/gsa-core.md).

**Show it: the badge & CI gate.** A two-minute GitHub Actions check turns attestations into a visible, enforceable claim — PRs fail until the branch ends in a valid attestation, and your README carries an **attested by humans** badge (the one at the top of this file):

```yaml
# .github/workflows/signoff.yml
name: attested by humans
on:
  pull_request:
  push:
    branches: [ main ]
jobs:
  verify-signoff:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # full history — attestations live in it
      - uses: jerrylin96/signoff/verify@verify-v1.2
```

Supports standard merge strategies: **2-parent PR merges** (verifies clean merge tree & attested PR head in `head` mode), **fast-forward merges** (`head` mode), **squash merges** (`history` mode; in `head` mode when base is unchanged), and **rebase merges** (`history` mode; in `head` mode, re-run `/signoff` after rebase). Enforce strictly with preconfigured [`ruleset.json`](verify/ruleset.json). Full setup & badge markdown: [`verify/`](verify/README.md).

The protocol is harness-, model-, and vendor-neutral. The skill is
prompt-driven and self-contained; the optional `signoff-mcp` server adds
deterministic server-side enforcement (derived status, stale-state circuit
breakers, notes concurrency handling).

- **Protocol spec:** [`skills/signoff/specs/gsa-core.md`](skills/signoff/specs/gsa-core.md)
- **Per-harness install & portability guide:** [`skills/signoff/HARNESSES.md`](skills/signoff/HARNESSES.md)
- **Skill entry point:** [`skills/signoff/SKILL.md`](skills/signoff/SKILL.md)

Distribution is deliberately boring: a folder of Markdown committed to the
repository under review, loaded by the harness from disk. Earlier
account-scoped channels (a Claude Code plugin marketplace and a release-zip
skill upload) were retired in v0.4.0 — the vendored folder replaced them on
every surface; the spec's phase log records the history.

### MCP server (optional enforcement)

```bash
pip install "signoff-mcp @ git+https://github.com/jerrylin96/signoff"
claude mcp add signoff -- signoff-mcp   # server must run with cwd = target repo
```

Tools: `signoff_prepare` (resolves the review range and also reports the
active interview profile — source, ID, provenance digest — plus the
science-guard signals detected in the diff), `signoff_commit`
(server-derived status, `ack_no_transcript` circuit breaker),
`signoff_push_notes` (`cat_sort_uniq` notes merge). PyPI release pending:
the credential-free publish workflow (trusted publishing) is in place;
it activates once the PyPI-side trusted-publisher configuration exists.

## Status & roadmap

**v0.2.0** ships the researcher-facing feature set described above —
repo-local profiles, the default-on science guard, and profile provenance
digests — verified end-to-end by scripted mechanics checks plus live
interview runs: this repository signs off its own branches, and the
resulting attestations are in its history (`git log --grep='SIGNOFF'`).
Phase 5 (tracked in [gsa-core.md §6](skills/signoff/specs/gsa-core.md))
adds the production surface: a [project website](https://jerrylin96.github.io/signoff/),
the [attested-by-humans badge + CI verifier](verify/README.md),
automated `refs/notes/signoff` recovery, an open
[spec license](LICENSE-SPEC) with [conformance vectors](conformance/README.md)
for third-party implementations, and a reviewed
[transcript-escrow spec](skills/signoff/specs/gsa-escrow.md) whose
privacy baseline is user-owned storage with client-side encryption.
Cloud escrow implementation and PyPI publish remain next.

## Development

```bash
pip install -e . pytest
pytest
```

Contract tests live in `scripts/tests/` (skill contracts), `tests/` (repo
initializer), and `signoff_mcp/tests/` (server mechanics).

## License

Code is MIT licensed; the GSA specifications are licensed under the
[Community Specification License 1.0](LICENSE-SPEC), so anyone can implement,
verify, or extend the protocol.
