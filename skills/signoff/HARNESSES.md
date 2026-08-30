# Harness Setup & Portability Guide

How to install and run `/signoff` on each agent harness. The skill is
prompt-driven and self-contained (GSA Phase 1); the `signoff-mcp` server
(GSA Phase 2) is an optional enforcement upgrade wherever MCP is supported.
Canonical protocol: [specs/gsa-core.md](specs/gsa-core.md).

## Portability Rules

1. **Copy the entire `signoff/` folder**, including `specs/`, so relative links
   (e.g. `specs/gsa-core.md`) keep resolving. Never copy `SKILL.md` alone.
2. **All links are relative** — enforced by `scripts/tests/test_skill_references.py`
   (no `file://` links).
3. **Cross-skill references degrade gracefully outside Antigravity.** On
   harnesses without `explain-diff`, the agent explains diff mechanics inline
   during remediation instead of delegating. The make-feature scratchpad step
   already self-skips when the scratchpad file does not exist.
4. **Transcript digests need the harness adapter env vars below.** When none
   apply, set `SIGNOFF_TRANSCRIPT_FILE` explicitly or accept the downgraded
   `VERIFIED_BY_HUMAN_NO_TRANSCRIPT_DIGEST` status (second confirmation
   required).

## Antigravity CLI (native)

In the [dotgemini](https://github.com/jerrylin96/dotgemini) Antigravity global
config this skill is indexed natively in `AGENTS.md` and maps to `/signoff`;
on other Antigravity setups, copy the folder per the Portability Rules.

- Transcript env: `ANTIGRAVITY_CONVERSATION_ID`
- Transcript path: `~/.gemini/antigravity-cli/brain/<cid>/.system_generated/logs/transcript.jsonl`

## Claude Code — CLI, desktop, and web (claude.ai/code)

One mechanism covers every Claude Code surface: a **project skill** — the
self-contained folder committed to the repository under review at
`<repo>/.claude/skills/signoff/`. Local sessions load it from the working
tree; cloud sessions load it from the clone at session start. Vendor it with
the zero-touch initializer (README Quickstart) or copy the folder per the
Portability Rules. `git pull` is the whole update mechanism for
collaborators; re-running the initializer (or re-copying) bumps the vendored
copy to a new release. Vendored copies never self-update or announce new
releases, and the initializer vendors the default branch's current skill
content (no version marker yet — caveat log in `docs/productionization.md`);
offline installs pass `--skill-source <path-to-skills/signoff>`. Commit a
real copy, not a symlink — re-running the initializer over a symlinked
destination aborts, since `rmtree` refuses symlinks. This repository
dogfoods the same path via a `.claude/skills/signoff` symlink to its own
`skills/signoff/`; that symlink pattern is for this repo only.

A machine-local install also works for local CLI/desktop sessions: copy the
folder to `~/.claude/skills/signoff` (user-level, all projects). Linked git
worktrees are handled by the `--git-common-dir` fallback: the transcript is
keyed to the primary repository root, and the adapter resolves it
automatically.

- Transcript env: `CLAUDE_CODE_SESSION_ID` (exported to Bash subprocesses;
  verified live in a web session on 2026-08-05, including full adapter
  resolution of the running session's transcript).
- Transcript path: `~/.claude/projects/<cwd-slug>/<session-id>.jsonl`

Optional MCP enforcement (server-derived status, `ack_no_transcript` circuit
breaker, stale-state checks — GSA §4):

```bash
pip install "signoff-mcp @ git+https://github.com/jerrylin96/signoff"
claude mcp add signoff -- signoff-mcp   # server must run with cwd = target repo
```

Web-specific caveats:
- **Ephemeral containers**: the transcript file is destroyed when the session
  container is reclaimed. The digest still proves what existed at commit time,
  but can never be re-hashed locally afterward — push the attestation commit
  and `refs/notes/signoff` before the session ends. (This is the primary
  motivation for transcript escrow in the cloud concept.)
- **Weaker append-only assumption** (GSA §2.3): web sessions sync and compact
  transcripts, so first-N-bytes re-verification is less reliable than on
  local CLI harnesses.
- **`refs/notes/signoff` cannot be pushed from a web session** (verified
  2026-08-05): the cloud GitHub proxy restricts pushes to the session's
  working branch and returns HTTP 403 for notes refs (misreported by git as
  "Everything up-to-date" — verify with `git ls-remote`). The attestation
  commit still pushes with the branch, so verification falls back to the
  git-log lookup (GSA §5.1). Recover the notes mirror afterward from any
  unrestricted clone — the note body is byte-identical to the attestation
  commit message:
  ```bash
  NOTE_BODY=$(git log -1 --format=%B <attestation-sha>)
  git notes --ref=signoff append -m "$NOTE_BODY" <reviewed-commit-sha>
  git notes --ref=signoff append -m "$NOTE_BODY" <reviewed-tree-sha>
  git fetch origin +refs/notes/signoff:refs/notes/signoff-remote &&
      git notes --ref=signoff merge -s cat_sort_uniq refs/notes/signoff-remote
  git push origin refs/notes/signoff
  ```

### Verified-By resolution (all harnesses)

`Signoff-Verified-By` is proposed deterministically, never inferred; the
human's explicit confirmation of the proposed value remains the
accountability step. Resolution order:

1. `SIGNOFF_VERIFIED_BY` env override — export once (e.g. shell profile) to
   pin a canonical identity across harnesses
2. Harness-authenticated account email (`CLAUDE_CODE_USER_EMAIL` on Claude
   Code web)
3. `git config user.email` (local harnesses; on web this is the session
   identity, not the human — never use it there)

Unifying multiple recorded emails to one human is the read side's job via
standard `.mailmap`, not the capture side's.

### Distribution to end users

One channel: the vendored project skill above, committed to each repository
that wants `/signoff`. Users never clone or link this repo, and there is
nothing account-scoped to install or keep updated. The earlier account-scoped
channels — a Claude Code plugin marketplace and a CI-built release-zip skill
upload — were retired in v0.4.0: both demanded per-account setup, and the
plugin's bundled skill never loaded in cloud sessions (platform gap, verified
2026-08-05); the per-repo folder covers every surface without either. Other
harnesses use the same folder in their own skill location (sections below).

## ChatGPT Codex CLI

Codex stores session rollouts under `$CODEX_HOME/sessions/` (default
`~/.codex/sessions/`) as date-partitioned
`rollout-<timestamp>-<session-id>.jsonl` files, but does **not** inject a
session-id env var. Two options:

1. Export the session id (from the rollout filename) so the `CodexAdapter`
   discovers the newest matching rollout:
   ```bash
   export CODEX_SESSION_ID=<session-uuid>
   ```
2. Or point the generic override at the rollout file directly:
   ```bash
   export SIGNOFF_TRANSCRIPT_FILE=~/.codex/sessions/<yyyy>/<mm>/<dd>/rollout-<ts>-<uuid>.jsonl
   ```

## Other harnesses (Goose, etc.)

Use the generic override — it takes precedence over every harness adapter:

```bash
export SIGNOFF_TRANSCRIPT_FILE=/path/to/transcript.log
```

Adapter resolution order (fixed): `SIGNOFF_TRANSCRIPT_FILE` →
`ANTIGRAVITY_CONVERSATION_ID` → `CLAUDE_CODE_SESSION_ID` → `CODEX_SESSION_ID`.

## Interviewer provenance (`Signoff-Agent`)

Attestations record who conducted the interview via the `Signoff-Agent`
trailer (grammar: [specs/gsa-core.md](specs/gsa-core.md) §2.3):

```text
Signoff-Agent: harness=<id>/<version|N/A> model=<model-id|N/A> reasoning=<level|N/A> interview=<intensity-level>/<profile-id>
```

Fields are deterministically sourced where the harness exposes them; the
digest helper emits harness version, model, and reasoning from the same
transcript snapshot bytes as the digest. Per-harness sources:

| Harness | harness version | model | reasoning |
|---|---|---|---|
| Claude Code (web + CLI) | `CLAUDE_CODE_VERSION` | `ANTHROPIC_MODEL` → transcript scan (last `"model"` field) → agent self-report | `CLAUDE_EFFORT` (set on web; CLI only if exported), else `N/A` |
| Antigravity CLI | `N/A` (not exposed) | transcript scan → self-report | `N/A` (not exposed) |
| Codex CLI | `N/A` (not exposed) | rollout scan → self-report | `N/A` at skill level (`model_reasoning_effort` lives in `$CODEX_HOME/config.toml` and is not auto-discovered) |
| Generic / other | `N/A` | transcript scan → self-report | `N/A` |

`interview=` records the intensity level actually run (cursory / standard /
skeptical, post-escalation) and the active profile's `Profile-ID`. When no
explicit modifier (`--quick` / `--deep`) is supplied, `/signoff` uses
**adaptive intensity by default** — dynamically evaluating range diff semantics
and blast radius per SKILL.md's classification precedence: Tier 0 (`cursory`
for tiny pure docs/types <50 LoC AND ≤2 files), Tier 1 (`standard` for default
feature work, with docs-only churn of any size capped at Tier 1), or Tier 2
(`skeptical` for high-impact content/path triggers or executable blast
radius >200 LoC / >5 files). Explicit `--quick` permits cursory opt-in on
small routine code (≤200 LoC, ≤5 files) or small docs (<50 LoC, ≤2 files), but
is subject to a 4-row safety clamp that strictly blocks cursory and
auto-escalates to Tier 1 for docs blast radius (≥50 LoC or >2 files), or Tier 2
for high-impact triggers / executable blast radius.
Self-reported model values are honest best-effort, not verifiable; where the
harness records model IDs in the transcript, the transcript digest lets
auditors re-derive the model from the same bytes.

## Customizing the interview (INTERVIEW PROFILE)

The interview profile — a single delimited text block — is the sole
customization point of the skill. Universal axes, intensity levels, workflow
steps, and attestation mechanics are fixed: profiles weight probes *within*
the universal axes and may add domain emphases; they cannot remove axes or
lower pass criteria.

The active profile is resolved per run, in fixed order:

1. **`SIGNOFF_PROFILE_FILE`** — explicit path to a profile file. Highest
   precedence; if set but unreadable, signoff aborts rather than silently
   falling back.
2. **`<repo>/.signoff/profile.md`** — repo-local profile. Commit one file to
   the repository under review and every `/signoff` run there uses it — for
   every collaborator, on every harness, surviving skill updates. This is
   the recommended path for labs and teams.
3. **Embedded block in `SKILL.md`** — the shipped default
   (`software-general`). Editing it in the vendored copy still works, but
   re-vendoring on update overwrites such edits — prefer the repo-local
   file.

A profile file must contain exactly one block of the form:

```text
<!-- INTERVIEW-PROFILE:BEGIN (sole customization point — replace only this block) -->
### Interview Profile: <your domain>
Profile-ID: <your-domain-id>

Domain emphases — weight probes within the universal axes; never remove axes
or lower pass criteria:
- **<Emphasis>:** <what to probe — e.g. grid-resolution sensitivity of any
  reported trend; conservation properties of a new parameterization>
<!-- INTERVIEW-PROFILE:END -->
```

Start from a shipped profile:

- [profiles/software-general.md](profiles/software-general.md) — default:
  efficiency, data structures, API contracts.
- [profiles/domain-science.md](profiles/domain-science.md) — research code:
  unit/dimensional validity, surrogate-vs-ground-truth boundaries, numerical
  stability, statistical validity, uncertainty quantification,
  reproducibility.

Malformed or out-of-scope file-sourced profiles (missing markers or
`Profile-ID`, attempts to weaken axes or pass criteria, instructions
unrelated to interview emphasis) are announced and ignored — the run falls
back to the embedded default, so a broken profile can only restore stock
rigor, never lower it.

**Provenance:** the `Profile-ID:` line feeds the `interview=` token of
`Signoff-Agent`, and file-sourced profiles additionally record a 12-hex
SHA256 prefix of the block
(`interview=<level>/<profile-id>/sha256:<digest>`, GSA §2.3), so every
attestation shows exactly which question set interviewed the human — a
diluted profile is distinguishable from a shipped one.

**Science guard:** independent of the active profile, any diff that touches
scientific computation (scientific-stack imports, notebooks, RNG seeding,
unit-bearing constants, netCDF/GRIB/zarr datasets or model configs)
additively triggers the `domain-science` emphases — see the guard in
`SKILL.md`. A repo whose profile already carries those emphases sees no
change; the guard exists so science probes never depend on someone having
configured anything.
