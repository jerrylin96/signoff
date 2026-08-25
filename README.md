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
curl -fsSL https://raw.githubusercontent.com/jerrylin96/signoff/main/init.py -o /tmp/signoff-init.py && python3 /tmp/signoff-init.py
```

The script automatically:
1. Detects your repo, branch, and stack (suggests science or general software profile).
2. Scaffolds `.github/workflows/signoff.yml`, `.signoff/profile.md`, and `.claude/settings.json`.
3. Injects the **attested by humans** badge into your `README.md`.
4. Automates GitHub Ruleset protection (via `gh` CLI or a 1-click settings link).
5. Creates feature branch `signoff/init` with your scaffolded setup ready for you to run `/signoff` and merge.

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

## How to use it: three steps

1. **Install** — run the 60-second initializer above, or pick the one row for your harness below.
2. **Run** — from the branch you want to merge, type `/signoff` (adaptive default auto-selects intensity from diff; `--deep` for skeptical rigor, `--quick` for low-risk diffs subject to safety clamps).
3. **Answer and confirm** — respond in your own words, acknowledge the named trade-offs and risks, confirm your email. The attestation commit and note are created and pushed with your branch.

---

## Installation & Harness Channels

| Where you work | One-time action |
|---|---|
| **Any repository (Zero-touch)** | `curl -fsSL https://raw.githubusercontent.com/jerrylin96/signoff/main/init.py -o /tmp/signoff-init.py && python3 /tmp/signoff-init.py` |
| **Claude Code CLI / desktop** | `/plugin marketplace add jerrylin96/signoff` then `/plugin install signoff@signoff` (or claude.ai → Customize → Plugins → Add → **Add marketplace** → "Add from a repository" → `jerrylin96/signoff`). Auto-updates from this repo. |
| **claude.ai web / cloud sessions** | Download [`signoff.zip` from the latest release](https://github.com/jerrylin96/signoff/releases/latest/download/signoff.zip) (CI-built from the tagged tree), then claude.ai → Customize → Skills → Add. Snapshot install — re-download on new releases. |
| **A team repo you control (cloud + local)** | Declare the plugin under [`enabledPlugins`](https://code.claude.com/docs/en/settings#enabledplugins) in that repo's `.claude/settings.json` — loads at session start from this marketplace and auto-updates. |
| **Other harnesses (Antigravity, Codex, Goose, …)** | Copy the self-contained `skills/signoff/` folder into your harness's skill location and set the transcript adapter env vars — full matrix in [HARNESSES.md](skills/signoff/HARNESSES.md). |

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
machine; editing the block inside an installed `SKILL.md` still works for
self-managed copies (auto-updating plugin installs overwrite such edits —
prefer the repo-local file). Full details:
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

Why the install split: this repo is a Claude Code **plugin marketplace**
(`.claude-plugin/marketplace.json` at root; the repo root is the plugin), and
the plugin is the auto-updating channel everywhere it reaches. As of
2026-08-05, account-scoped plugin installs register in claude.ai cloud
sessions but do not yet load the bundled skill there — hence the release-zip
row for web/cloud, which retires once the platform closes that gap.

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

Contract tests live in `scripts/tests/` (skill contracts), `tests/` (plugin
manifests), and `signoff_mcp/tests/` (server mechanics).

## Provenance

Extracted from [jerrylin96/dotgemini](https://github.com/jerrylin96/dotgemini)
with full history via `git filter-repo`; dotgemini now consumes this repo via
`git subtree`. Code is MIT licensed; the GSA specifications are licensed
under the [Community Specification License 1.0](LICENSE-SPEC), so anyone can
implement, verify, or extend the protocol.
