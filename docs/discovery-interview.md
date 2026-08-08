# Discovery interview script — prospective signoff users

Companion to [`productionization.md`](productionization.md): pricing,
escrow, and infrastructure decisions gate on evidence from these
conversations, not intuition. This script exists so every conversation
produces *comparable, recordable* evidence.

**Privacy rule (this repo is public):** filled-in notes never land in this
repository. Keep raw notes in private storage; feed only aggregated,
de-identified findings back into `productionization.md` (and escrow-demand
evidence into the gates of
[`gsa-escrow.md` §5](../skills/signoff/specs/gsa-escrow.md)).

## Ground rules (Mom-Test discipline)

- Ask about **past behavior and current practice**, never "would you use…".
  Hypothetical enthusiasm is not evidence; a story about last Tuesday is.
- Do not pitch until the final section. If you explain the tool early, every
  later answer is contaminated by politeness.
- Chase specifics: "walk me through the last time…", "what did that cost
  you?", "who else was involved?".
- Bad signs worth recording honestly: compliments, generic praise,
  deflection to "someone else would love this". Good signs: time, money, or
  reputation already lost; workarounds already built; an intro or commitment
  given at the end.
- 30 minutes. The concept test gets at most the last 10.

## Segments & recruiting

| Segment | Who specifically | Recruiting channel |
|---|---|---|
| Research code (primary) | PhD students/postdocs/PIs whose papers depend on AI-assisted analysis code; earth/atmospheric science first (matches the shipped `domain-science` profile) | AGU abstract pipeline, lab contacts, co-author networks |
| Engineering teams | Tech leads / senior ICs on teams with heavy AI-assistant usage and a PR review culture | Direct outreach, BayLearn pipeline |
| Buyer-side (secondary) | Engineering leadership, compliance/security owners with AI-usage-policy responsibility | Warm intros only at this stage |

Interview at least a handful per segment before treating any pattern as
evidence; log every conversation, including the ones that go nowhere.

## 1. Context (5 min)

1. What's your role, and what did you ship (paper, release, decision) most
   recently?
2. How much of the code behind that was written or heavily shaped by an AI
   assistant? Which tools?
3. Who reviews that code before it merges — or before its output gets used?

## 2. Problem discovery (10 min) — the core of the interview

The hypothesis under test: *AI-assisted changes get merged (or results get
published) without any human genuinely understanding them, and this has
already cost the interviewee something.* Probe for stories, not opinions.

4. Tell me about the last time code went in that, honestly, nobody fully
   understood. What happened downstream?
5. (Research) How do you convince yourself an AI-assisted analysis is
   *valid* before results go in a paper? Walk me through the last time —
   what did you actually check?
6. (Engineering) Walk me through your last review of a large AI-generated
   PR. How long did you spend? What did you actually verify vs. skim?
7. Has "who understood this change" ever come up after the fact — an
   incident review, a retraction scare, a compliance question, an advisor
   or auditor asking? What happened?
8. What do you do *today* to guard against this? (Look for existing
   workarounds: mandatory walkthroughs, pair review, "explain this diff to
   me" rituals, checklists.) What does that cost per week?
9. If nothing: why is it not a problem worth guarding against? (A genuine
   "we don't care" is evidence too — record it.)

## 3. Workflow mapping (5 min)

10. Which harness/assistant, which forge (GitHub/GitLab/other), what CI?
11. What already gates a merge (required checks, approvals, DCO/signing)?
12. Where would a new gate have to live for your team to accept it — CI
    check, pre-commit, forge-native review UI?

## 4. Concept test (max 10 min — only after sections 1–3)

Describe signoff in two sentences, neutrally: *"Before an AI-assisted diff
merges, the AI interviews the human about mechanics, trade-offs, failure
modes, and ownership; passing writes a tamper-evident attestation into git
history, with a CI badge that verifies it."* Then stop talking and record
the reaction verbatim.

13. What part of that would earn its keep on your team? What part would get
    bypassed or resented?
14. The interview takes real minutes per merge. Where is that acceptable,
    and where would it get turned off?
15. Who in your org would have to say yes, and what would they need to see?

## 5. Evidence-gate probes (weave in where natural — these unlock recorded decisions)

Escrow demand ([`gsa-escrow.md` §5](../skills/signoff/specs/gsa-escrow.md)
— the operated registry may be built only on this evidence):

16. Would anyone (auditor, legal, customer) ever need to *re-read the
    conversation* behind an attestation months later? Who, and under what
    trust constraints — your storage, or an independent party's?
17. Do you face cross-organization verification (partners/auditors who
    can't be given access to your storage)? Independent-timestamp
    requirements?

Pricing ([`productionization.md`](productionization.md), Pricing &
packaging):

18. What does your team pay per seat today for dev tooling in this class?
    Who signs that off?
19. Is there a budget line (compliance, AI governance, research integrity)
    this would plausibly come from — and has it bought anything yet?

## 6. Commitment ask (2 min — every interview ends with one)

Advancement is the only reliable positive signal. Ask for exactly one:

- Install the badge + verifier on one active repo this week
  ([two-minute install](../verify/README.md)) and let us see the result.
- An intro to the person who owns review policy / compliance.
- A scheduled follow-up after they've run `/signoff` on a real branch.

A "yes, but later" with no date is a no — record it as one.

## Logging template (keep filled copies private)

```text
Date / segment / role (de-identified):
AI-assist share of their code, harness, forge, CI:
Strongest problem story (verbatim quote if possible):
Existing workaround + weekly cost:
Concept reaction (verbatim):
Escrow-demand signals (Q16–17): none / self-host / managed / independent-witness
Pricing signals (Q18–19): comparable $/seat, budget owner:
Commitment made: which ask, by when — or explicit no:
Follow-up owed:
```

Aggregate across interviews before drawing conclusions; single-interview
enthusiasm has already been repeatedly wrong in this project's history.
