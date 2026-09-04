# Productionization Review — living document

Going from an internal tool with 1–2 users to software that dozens-to-hundreds
of people rely on (some paying) demands orders-of-magnitude more scrutiny.
This document records the strategic decisions behind gsa-core.md §6 Phase 5:
what is decided, what is deliberately deferred, and what evidence unlocks each
deferred decision. Iterate it adversarially each session that touches Phase 5.

## Adoption reality check

Current verified reach: this repository's own branches, two humans, zero
measured external installs. Every infrastructure and pricing decision below is
sequenced against that fact: we invest now in what compounds regardless of
scale (design, protocol quality, distribution), and defer what only pays off
at scale (operated infrastructure, pricing tiers) behind explicit evidence.

## Website & hosting

**Decision: static-first, design-first.** The front door is a static site
built with genuine design investment — the bar is the polish of
[ndstudio.gov](https://ndstudio.gov/) and
[americabydesign.gov](https://americabydesign.gov/) (their attention to
design, not their content): coherent type system, generous whitespace,
seamless navigation, fast loads, accessible.

- GitHub Pages is production-grade *for a static front door* (CDN-backed,
  TLS, custom domains; serious dev tools ship docs on it). It is not, and
  never will be, the host for dynamic product (auth, dashboards, storage
  APIs) — that is a separate, later system, and conflating the two is the
  failure mode to avoid.
- Static output is portable by construction: if analytics/previews justify
  it, moving to Cloudflare Pages or Vercel is an afternoon, not a migration.
- **Highest-leverage credibility item: a custom domain** (user action —
  purchase + DNS). A github.io URL undercuts any design effort.
- **Status 2026-08-06:** shipped as `site/index.html` — one self-contained
  page (zero external requests: inline CSS, system font stacks, data-URI
  favicon), deployed by `.github/workflows/pages.yml`. Remaining user
  actions: Pages enablement if the workflow's auto-enable attempt lacks
  permission, then the domain purchase.
- **Post-merge verification 2026-08-06:** the auto-enable attempt did lack
  permission — the first `pages` run on `main` failed inside
  `actions/configure-pages` ("Create Pages site failed: Resource not
  accessible by integration"); deploy steps were skipped, so the failure is
  isolated to enablement. Pages enablement (Settings → Pages → Source:
  GitHub Actions) is now the confirmed blocking user action, followed by
  the domain purchase.

## Storage, provider, database

**Decision: deferred behind the gate-2 spec review, which holds user-owned
storage (own bucket or private git ref) with client-side encryption as the
null hypothesis.** Operating storage makes the project a data controller for
whole dev conversations (secrets, proprietary code, non-consenting third
parties) — that liability must be justified by demand, not assumed.

**Status 2026-08-06: the gate-2 review is done** — the analysis below is
now normative in `skills/signoff/specs/gsa-escrow.md` (privacy principles,
user-owned baseline with age encryption, ciphertext-only operated registry,
evidence gates, cost model). This section remains the strategy record; the
spec governs implementations. Building escrow (Phase 5 gate 3) gates on the
spec's evidence rules.

If the null hypothesis is beaten, the workload is deliberately boring:
append-only encrypted blobs + a small metadata index.

- Object storage: S3 or Cloudflare R2 (zero egress fees suit a
  verification-heavy read pattern).
- Metadata: small managed Postgres (Neon/Supabase class). No exotic database
  is warranted by this workload; boring is a feature.
- DBOS-class durable-execution frameworks (real technology — Postgres-backed
  transactional workflows): relevant *category*, wrong *stage*. Escrow has
  almost no workflow to orchestrate; record as an alternative in the gate-2
  spec, do not adopt now.
- Expected cost at small scale: single-digit dollars/month for storage +
  metadata until usage proves otherwise; the spec review must include a cost
  model before any operated service ships.

## Pricing & packaging

**Decision: no numbers before discovery.** Pricing gates on structured
conversations with prospective users, not intuition — the interview script
for those conversations is [`docs/discovery-interview.md`](discovery-interview.md).
What is already clear:

- Buyer: engineering leadership / compliance. Value story: audit trail of
  human comprehension for AI-assisted code (EU AI Act, SOC 2, internal AI
  usage policies).
- Comparable per-seat dev tooling: ~$10–30/seat/month; "enterprise"
  concretely means SSO, retention controls, self-hosted escrow, support SLA.
- Charging at all requires an entity, terms of service, and support
  capacity — real fixed costs that belong in the decision, not after it.

## Moat strategy

First-mover advantage and audience network effects are **weak** for this
product: attestation value is mostly intra-team, and the software itself was
built quickly with a frontier model anyone can rent — it will be reproduced.
The defensible layer is the **protocol**: make GSA the format other tools
verify. Concretely: keep the spec open and excellent, ship reference
verifiers, pursue integrations (CI checks, platform badges), and let hosted
convenience monetize a standard we author. Audience compounds linearly;
standardization compounds structurally. Both matter; the plan prioritizes
the second.

### Seeding & the sharing loop

Colleague seeding (free for academics, champions in industry) is the
ignition strategy and is complementary to standardization — standards
without users die. But seeding alone yields *linear* adoption bounded by
personal social capital; the snowball requires a **visible artifact per
use**, which GSA currently lacks (attestations live in git history where no
third party encounters them). Two high-priority mechanisms:

- **Badge + verifier check**: a README/PR badge ("attested by humans") and a
  CI/GitHub check that verifies GSA trailers — every adopting repo becomes
  an advertisement. **Shipped 2026-08-06** as `verify/` (stdlib-only
  single-file verifier + composite action, two-minute install per
  `verify/README.md`) and dogfooded by this repo's own badge. Every seeded
  adopter should land with it from day one.
- **Citable wedge for academia**: a short paper/preprint defining GSA
  (human-comprehension attestation for AI-assisted research code) makes the
  standard citable; the endgame is journals/labs requiring attestations for
  AI-assisted analysis code. Builds directly on Phase 3d's researcher
  accessibility work.

Pipeline in motion (kept intentionally generic here — personal-network
details stay out of a public repo): a conference abstract on signoff is
submitted to AGU (audience matches the domain-science profile and this
repo's earth/atmospheric example convention exactly); an ML-venue abstract
(BayLearn) is under consideration; direct outreach to contacts across
industry and research universities is planned. Each seeded adopter should
land with the badge/verifier artifact available, so adoption is visible.

### Path to an open standard

Target end-state: GSA as a widely adopted open standard, conceivably donated
to a neutral foundation, applicable across domains and industries. Candidate
home, dual-track: the Linux Foundation's **Agentic AI Foundation (AAIF)** for
governance — MCP itself was donated there, `signoff-mcp` is an MCP server,
and human-accountability attestation for agentic coding is core AAIF
territory — while the **OpenSSF** attestation ecosystem (in-toto, SLSA,
Sigstore) remains the interop target rather than the home. Crucially, that
ecosystem attests *builds, provenance, and signatures*; nothing in it attests
**human comprehension** — GSA is complementary, not competing, and an
**in-toto predicate type carrying GSA trailers** is a concrete candidate
donation vehicle. Milestones, in order:

1. **Spec hygiene** (mostly done): versioned, self-contained,
   implementation-neutral core spec; keep tightening normative language
   (MUST/SHOULD) and separating normative from informative sections.
2. **Spec licensing** — ✅ 2026-08-06: Community Specification License 1.0
   in `LICENSE-SPEC`, declared by `gsa-core.md` and `gsa-escrow.md`; code
   stays MIT.
3. **Independent implementations**: the skill and signoff-mcp are two
   same-author implementations; the milestone is one *third-party* verifier
   or producer. The enabler shipped 2026-08-06 — `conformance/` publishes
   the test-vector suite (mostly real attestations, reference verifier
   pinned to it in CI); the milestone itself (an external implementation)
   remains open and is now a seeding ask, not an engineering task.
   **First divergent implementation observed 2026-08-08:** dotgemini's
   independently authored `Signoff Verification Gate` (its
   `.github/workflows/signoff.yml`, PR #62) re-implements §5.1 verification
   in shell and diverged from the reference verifier in exactly the ways a
   conformance suite exists to catch. Two of its checks were *stricter* and
   correct — it required attestation commits to be empty (parent tree ==
   head tree, closing a real reference-verifier false positive where a
   non-empty "attestation" commit could smuggle unreviewed changes past
   head mode) and enforced `Signoff-Spec-Version: 1.0` as a value — both
   adopted into `verify/verify_signoff.py` with tests and a new conformance
   vector. One of its checks is *over-strict*: an exactly-one-occurrence
   rule per mandatory trailer, which rejects `cat_sort_uniq`-merged note
   blobs that §2.5's own notes flow produces (our
   `valid-note-cat-sort-uniq.txt` vector would fail its gate). Standing
   seeding ask: run any independent gate against `conformance/` before
   trusting it. **Same-day follow-up:** dotgemini's alignment branch
   (`gemini/cat-sort-uniq-conformance-gate`) fixed the note-check
   divergence, adopted `conformance/` as a synced subtree, and added a
   vector-pinning test — the first external consumer of the suite.
   Review of that branch surfaced the next round: its conformance test
   validates a hand-copied duplicate of the workflow's validator (drift
   risk — the pin should extract the validator from the workflow), and its
   validator never requires `Signoff-Verified-By`; the suite now carries
   `invalid-missing-verified-by.txt` to make that gap fail loudly on their
   next subtree resync. A third round surfaced a genuine spec ambiguity —
   trailer-key case sensitivity, on which the two implementations reached
   opposite verdicts — resolved normatively in gsa-core.md §2.3 and pinned
   by `invalid-lowercase-keys.txt`. Convergence confirmed 2026-08-08: the
   dotgemini validator, run against the full 10-vector suite (including
   three vectors it had never seen), agrees with the reference verifier on
   every verdict. Net effect of the exchange: rigor moved in both
   directions (their empty-commit and spec-version checks hardened the
   reference verifier; our cat_sort_uniq and required-trailer vectors
   hardened their gate) and the spec itself got tighter — the
   standardization flywheel working as designed, on its first external
   consumer.
4. **Ecosystem interop**: the in-toto predicate-type mapping is drafted
   (`specs/gsa-in-toto-predicate.md`, provisional namespace — registry
   submission gates on milestone 3 evidence), and the CI check / badge
   exists (`verify/`). Remaining: platform-native checks beyond Actions if
   demand appears.
5. **Governance & donation**: gates on evidence of external adoption
   (milestone 3), not before — donating an unused spec buys prestige for
   nobody. Name/trademark considerations belong to this milestone too.

## Simplification backlog — ponytail audit (2026-08-30)

Recorded so future sessions argue against this list instead of
re-discovering it. Context: an outside-user review found the setup story
convoluted, and distribution was consolidated to a single per-repo channel
in v0.4.0 — the skill folder vendored into the target repo's
`.claude/skills/signoff/`; the plugin-marketplace and release-zip channels
were retired (decision log: gsa-core.md Phase 4 amendment 2026-08-30). The
audit principle is dotgemini's ponytail skill: simplest working thing,
deletion over addition, nothing speculative. Remaining candidates, each
with a verdict and the trigger that changes it:

- **`init.py` duplication** (674 byte-identical lines at root and
  `signoff_mcp/init.py`, pinned by `test_init_scripts_byte_parity`):
  mechanical debt — the parity test makes it safe, but every change is
  written twice. Dedupe when packaging allows, or shrink the script itself:
  the vendor step is the essential one; ruleset/badge/branch automation is
  optional polish that could become flags-off-by-default.
- **Transcript-digest machinery** (per-harness adapters, the env-var
  matrix, snapshot timing rules): the single biggest onboarding/portability
  tax — it is why HARNESSES.md needs a harness matrix at all — and weakest
  exactly on cloud sessions, where the transcript dies with the container.
  Candidate: make the no-digest status the default and digests opt-in.
  That is a spec-level change (gsa-core §2.2/§2.3 status semantics), to be
  decided deliberately, not drifted into.
- **SKILL.md intensity legalese** (~50 lines of tier tables, 4-row clamps,
  and precedence orders, pinned by the Phase 3f contract test): the
  adaptive-intensity *idea* earns its keep; the lawyering may not.
  Candidate: compress to judgment guidance once live runs show the model
  doesn't need the full matrix. Cost of keeping: comprehension tax on every
  new reader; cost of cutting: re-litigating the rigor floors the tests pin.
- **`signoff-mcp` server (~900 lines + tests) and the PyPI publish path**:
  freeze until someone asks for deterministic server-side enforcement — no
  adopter of the skill channel has, and the PyPI trusted-publisher setup
  remains an unspent user action. Keep it out of the adoption path either
  way.
- **Escrow spec (`gsa-escrow.md`)**: already evidence-gated — correct
  shape; no further investment until its gates trip.
- **Conformance vectors, spec license, in-toto draft**: *not* baggage —
  they serve the declared moat (standardization) and have produced measured
  value (the dotgemini convergence exchange under "Path to an open
  standard"). The tension is placement, not existence: keep the standards
  apparatus out of the adoption path (README quickstart, HARNESSES.md) so
  a curious lab never has to read it to install.
- **`site/` and the seven workflows**: front door and plumbing sized for
  the current stage; no action.

Resolution rule for future sessions: adoption-path surfaces (README,
HARNESSES.md, SKILL.md, `init.py`) get ponytail applied hardest — an
outside user should reach a working `/signoff` reading almost nothing.
Standards and strategy surfaces (`specs/`, `conformance/`, this document)
justify their weight by moat milestones, not by user convenience, and are
allowed to be heavy as long as no install instruction depends on them.

### Known caveats accepted at v0.4.0 (from the branch signoff interview, 2026-08-30)

Recorded so they never need re-derivation; each names its future fix.

- **Unpinned vendor payload (the one silent path) — FIXED 2026-08-31.**
  `vendor_skill` used to shallow-clone the repo's *default branch at run
  time*, regardless of which pinned `init.py` tag the user downloaded, and
  the vendored folder carried no version marker. Fixed as prescribed, in
  one move: the clone now happens at the pinned tag `SKILL_SOURCE_REF`
  (`init-v4`, served by the install snippets and created by tag.yml's PINS
  list — `test_skill_source_ref_pin_consistency` fails if the three ever
  drift), and every vendored copy carries a `VENDORED-FROM` stamp (source,
  ref, commit; `ref: local` for `--skill-source` installs) — self-describing
  staleness. HARNESSES.md caveat updated in the same change.
- **`VENDORED-FROM` stamp is claim, not proof (2026-08-31).** The stamp is
  plain text with no signature or content hash: it self-describes provenance
  for honest users but cannot prove it — a hand-edited stamp, or skill files
  modified after vendoring, go undetected. Accepted at the init-v3 signoff
  interview: anyone positioned to forge the stamp can edit the skill files
  themselves, so stamp integrity cannot exceed folder integrity; in
  committed repos git history already provides tamper evidence, and the
  forger's payoff is unclear. Future fix if audit demand appears: record a
  content hash of the vendored tree alongside ref/commit, verifiable
  against the source repo.
- **No update notification.** Vendored copies never self-update or announce
  releases; update = re-run the initializer or re-copy. Deliberate — the
  same trust model as any vendored code.
- **Verifier pin immutability.** Scaffolded workflows pin
  `verify@verify-v1.2`; pin tags never move, so verifier fixes reach
  adopters only when they edit the pin or re-run the initializer.
  Deliberate: a floating pin would let upstream changes silently alter the
  behavior of downstream *merge gates*, and widens the CI supply-chain
  surface.
- **Offline initializer runs fail loudly but mid-scaffold — FIXED
  2026-08-31.** With no network, the vendor clone aborts (RuntimeError →
  exit 1) *after* branch creation and workflow/profile scaffolding; it used
  to leave the repo stranded on `signoff/init` with half-written, unstaged
  files. `run_init` now rolls back atomically: any failure after branch
  creation removes the paths it created, reverts tracked files it overwrote
  (the README badge) to HEAD, prunes only the directories it made, and
  restores the original branch — so a failed run leaves the repository
  exactly as it found it and is safely re-runnable (born, unborn, and
  detached-HEAD starts all covered; `test_vendor_failure_rolls_back_scaffold`
  and neighbors pin it). Rollback restores local git state only; a GitHub
  ruleset already created via `gh` is idempotent and left in place.
  `--skill-source <path>` remains the intended offline path (HPC clusters).
- **Policy A fail-fast validation.** Pre-flight validation (`validate_policy_a`)
  safeguards destination directories before any branch is created. Symlinks at
  the destination or in any parent path component, ordinary-file collisions,
  git-ignored destinations, pre-existing ignored untracked descendants, and
  unrelated non-empty directories are refused with actionable diagnostic messages.
  Outside repos should commit real copies — dogfood symlinks at
  `.claude/skills/signoff` and `.agents/skills/signoff` are this repository's
  internal pattern only. `--allow-dirty` is intentionally narrow: it permits
  unrelated unstaged/untracked work, but refuses pre-staged changes and any
  uncommitted or ignored state under managed scaffold paths. The guard runs
  before branch creation, and a second staged-path check runs immediately before
  the scaffold commit, preventing user work from being overwritten or committed.
  Rollback is best-effort and preserves the original exception, but every failed
  filesystem/Git recovery operation is now collected and reported; the initializer
  only claims local Git state was restored when no rollback failure was observed.
  If GitHub ruleset creation succeeded before a later local failure, the runtime
  explicitly warns that the remote ruleset remains configured.
- **Old-channel installs are orphaned.** Accounts that installed the
  retired plugin or zip skill stop receiving anything and are not notified;
  accepted as a pre-production breaking change (the maintainer removed
  their own installs 2026-08-30).

## User actions (cannot be done from a cloud session)

- Purchase custom domain; DNS to Pages.
- Enable GitHub Pages in repo settings.
- GitHub About sidebar text.
- Configure the PyPI trusted publisher for `signoff-mcp` (pypi.org →
  Publishing → add pending publisher: owner `jerrylin96`, repository
  `signoff`, workflow `pypi-publish.yml`, environment `pypi`) — the
  `pypi-publish` workflow then publishes with no stored credentials.
- Discovery conversations with prospective users — script:
  [`docs/discovery-interview.md`](discovery-interview.md); keep filled
  notes private, record only aggregated evidence back into this document.
