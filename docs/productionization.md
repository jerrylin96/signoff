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

## Storage, provider, database

**Decision: deferred behind the gate-2 spec review, which holds user-owned
storage (own bucket or private git ref) with client-side encryption as the
null hypothesis.** Operating storage makes the project a data controller for
whole dev conversations (secrets, proprietary code, non-consenting third
parties) — that liability must be justified by demand, not assumed.

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
conversations with prospective users, not intuition. What is already clear:

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
  an advertisement. Cheap; prioritize alongside the website.
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
2. **Spec licensing**: the code is MIT; the spec itself should carry an
   explicit open specification license (e.g. Community Specification
   License) before soliciting external implementations.
3. **Independent implementations**: the skill and signoff-mcp are two
   same-author implementations; the milestone is one *third-party* verifier
   or producer. Publish a small conformance test-vector suite (the
   production-attestation fixture is the seed) to make that cheap.
4. **Ecosystem interop**: draft the in-toto predicate-type mapping; explore
   CI checks / platform badges that verify GSA attestations.
5. **Governance & donation**: gates on evidence of external adoption
   (milestone 3), not before — donating an unused spec buys prestige for
   nobody. Name/trademark considerations belong to this milestone too.

## User actions (cannot be done from a cloud session)

- Purchase custom domain; DNS to Pages.
- Enable GitHub Pages in repo settings.
- GitHub About sidebar text.
- PyPI credentials when publishing signoff-mcp.
- Discovery conversations with prospective users (agent can draft the
  interview script).
