# Reliability experiment history (I1 to I7, and the I8 design review)

This document is the engineering history of the agent-reliability case study: what was frozen before
experimentation, what the first baseline revealed, what each controlled intervention tested, which were
kept and which were rejected, and what the whole cycle taught us about where the remaining failures
actually live. The raw per-run numbers stay in [`baselines/`](../baselines/); this is the synthesis.

It is written for a future maintainer, a reviewer reading the repository cold, and for us returning to
the project later. It complements the project [`README`](../README.md) and the architecture decision
records under [`docs/decisions/`](decisions/), and it is the authoritative record of the full I1 to I7
cycle and the current accepted behavior.

Status at this checkpoint: the accepted **behavioral HEAD** is `bd9cb95` (the last commit that changed
runtime behavior); later commits on `main` are documentation-only and do not change the accepted stack.
The accepted behavioral stack is **Intervention 1 + Intervention 2 + Intervention 5 + evaluator
auditability**; Interventions 3, 4, 6, and 7 are preserved as rejected or falsified evidence.
**Intervention 8 has not started** (a design-only review is recorded in section 7).

## 1. Purpose and experimental method

The goal of the project is not the agent; it is the reliability method around a small agent. Every
behavioral change goes through one loop:

**specify → freeze → baseline → inspect failures → form a falsifiable hypothesis → change one thing →
rerun the same frozen cases → accept, reject, or revert.**

Principles that the cycle holds to:

- The evaluation set is frozen before any live measurement, and no prompt is tuned before Baseline v1.
- Each dimension is scored separately. There is deliberately **no composite "agent score"**, because a
  single number hides exactly the per-dimension failures the project studies.
- Failed experiments are preserved, not deleted. The reliability story is as much about what was
  withdrawn as what was kept.
- When a single run is too noisy to separate a real effect from model nondeterminism, the change is
  measured with a repeated stochastic A/B instead of one pass.
- Infrastructure failures (a killed run, an environment fault) are retried for the same slot and
  recorded; runs are never repeated because the score was disliked.
- The deterministic policy is treated as a fixed oracle and is reasoned about separately from the
  nondeterministic model stages.

A caution on strength of evidence: the repeated experiments use small descriptive samples (typically 5
runs per arm, or 5 post-change runs). Directional means and per-slot comparisons are reported as
descriptive evidence, never as statistical-significance claims.

## 2. The frozen system

Before the improvement loop, the architecture, policy, enums, dataset, and corpus were frozen (see
[`docs/decisions/0003-frozen-spec-provenance.md`](decisions/0003-frozen-spec-provenance.md) and
[`0004-phase1-retrieval-and-agents.md`](decisions/0004-phase1-retrieval-and-agents.md)).

An incident flows: **router → Evidence Investigator (bounded) → Diagnosis Specialist → Grounding
Validator**, with a single pure **deterministic policy** evaluated at three checkpoints. The model
produces assessments and a diagnosis; it never chooses the final action. The terminal decision is always
one of `ANSWER | ASK | ESCALATE | ABSTAIN`. Retrieval is a hand-rolled Okapi BM25 (`k = 2`) over a 10-document
fictional Northwind corpus with two deliberate distractors. Diagnosis and Grounding are single structured
calls; the system fails closed (a parse or grounding failure escalates rather than guessing).

The frozen set is **22 cases**: **20 end-to-end (E2E)** cases that drive the full model-backed graph, and
**2 deterministic fault-injection** cases used as unit tests. The Northwind domain is fictional and
closed-domain: every incident, alarm code, and manual is invented, and there is no proprietary, employer,
or customer data of any kind.

### Pre-baseline safety-detector hardening

Before baseline capture, the deterministic safety detector's resolution scope was narrowed from
sentence-wide to hazard-segment-local. Sentence-wide resolution could incorrectly suppress a
still-active hazard when another hazard in the same sentence had already been resolved or isolated;
because safety is the first policy rule, above scope, that would silently drop an `ESCALATE(safety)`.
Resolution is now scoped to the hazard's own segment (`safety.py` splits on clause punctuation, commas,
and "but"), which preserves the active hazard while still recognising genuinely resolved or isolated
conditions. Negation stays clause-wide, so a leading "no" still distributes across a coordinated list
("no smoke, fire, or burning smell"). Regression tests cover a resolved historical hazard followed by a
new active hazard (`test_resolved_historical_then_new_active_hazard`) and isolation of one object
alongside a separate active hazard (`test_isolation_of_other_object_does_not_suppress_active_hazard`).
Implementation `522f43b`, tests `9667057`.

## 3. Baseline v1

Baseline v1 ([`baselines/baseline-v1.json`](../baselines/baseline-v1.json)) is the first honest
measurement of the real implementation, preserved unchanged.

- Model: `google_genai:gemini-3.8-flash`
- Frozen implementation under test: `526745c`
- Scope: 20 E2E cases

| Metric | Baseline v1 |
| --- | ---: |
| Route correctness | 20 / 20 |
| Decision correctness | 12 / 20 |
| Reason correctness | 7 / 10 |
| Retrieval behavior | 18 / 20 |
| Retrieval source | 9 / 10 |
| Grounding correctness | 1 / 7 |
| Output-contract validity | 20 / 20 |
| Structured-output validity | 14 / 20 |
| Distractor resistance | 17 / 20 |

The weak dimensions (grounding and decision especially) were recorded and left in place. A poor baseline
that is honestly measured is more useful than a good-looking one that was tuned before anyone looked at
where it failed. The two dominant failure clusters it exposed, which became the first intervention
targets, were (a) Diagnosis emitting `confidence=high` with `proposed_answer=None` (a self-contradiction),
and (b) Investigator state that was computed and then silently dropped before the policy could use it.

## 4. Intervention history

| # | Target | Result | Active? | Main lesson |
| --- | --- | --- | --- | --- |
| I1 | Diagnosis confidence/answer coupling | Accepted | Yes | single runs too noisy; adopt repeated A/B |
| I2 | Monotonic Investigator conflict preservation | Accepted | Yes | fixing upstream state-loss can expose a downstream failure |
| I3 | Conflict-resolvability prompt | Falsified, reverted | No | cannot prompt a stage about information it does not hold |
| I4 | Propagate prior conflict into reassessment | Partially supported, rejected, reverted | No | a mechanism can work locally and still be rejected system-wide |
| I5 | Distinguish telemetry acquisition from missing evidence | Accepted | Yes | an accidentally-correct decision can hide a wrong mechanism |
| I6 | Shared evidence-sufficiency semantics | Partially supported, rejected, reverted | No | prose alone could not separate "bounded differential" from "inspection-only" |
| I7 | Diagnosis confidence calibration | Falsified, reverted | No | downstream calibration cannot fix a latent structure discarded upstream |

SHAs: I1 `a3c81b4`, I2 `247441e`, I3 `214924e` (revert `fa8fdc6`), I4 `fe291c3` (revert `43f7eb8`),
I5 `183d67f`, I6 `985e0c6` (revert `1565f0e`), I7 `435ba84` (revert `bd9cb95`). Per-run artifacts are
under [`baselines/`](../baselines/).

### Intervention 1: Diagnosis confidence/answer coupling (accepted)

Target: the `confidence=high` + `proposed_answer=None` cluster, which the policy had to treat as an
internal error. The change coupled confidence to the presence of a grounded answer. A single-run A/B was
too noisy to trust (control decision correctness alone ranged 11 to 15 of 20 across runs), so the effect
was measured with a repeated 5-control / 5-treatment protocol
([`baselines/repeated-ab/summary.json`](../baselines/repeated-ab/summary.json)):

| Metric | Control mean | Treatment mean |
| --- | ---: | ---: |
| Decision correctness | 13 / 20 | 16 / 20 |
| Structured-output validity | 15 / 20 | 18.4 / 20 |
| Grounding correctness | 2.4 / 7 | 5.6 / 7 |
| High-confidence + null-answer states | 5.0 | 1.6 |

Treatment decision correctness was higher in all 5 paired slots (deltas `[1, 7, 1, 4, 2]`). This is
descriptive evidence across 5 runs per arm, not a significance claim. Accepted. The lasting lesson was
methodological: **single agent runs were too noisy to support a causal conclusion, so the protocol
evolved to repeated stochastic evaluation** for the rest of the cycle.

### Intervention 2: monotonic conflict preservation (accepted)

A deterministic state-loss bug: the Investigator's triage step could detect an evidence conflict that the
later reassessment step then overwrote with `False`, dropping a signal the policy needed. The fix made the
final conflict monotonic: `final_conflict = triage_conflict OR reassessment_conflict`
([`baselines/intervention-02/`](../baselines/intervention-02/)). Conflict survival on the target case went
from 0/10 historically to 5/5; the unresolvable-conflict case ARC-08 stayed correct
(`ESCALATE(conflict_unresolvable)` 5/5); and across the scanned runs no non-conflict case acquired a
spurious conflict. The headline decision score did not move, because the target case's final decision was
still gated by a separate gap-resolvability problem. Retained as a correctness fix regardless of the flat
score. Lesson: **fixing an upstream state-loss mechanism can expose an independent downstream failure
rather than immediately improve the final score.**

### Intervention 3: conflict-resolvability prompt (falsified, reverted)

An attempt to make the reassessment step classify conflict resolvability whenever it detected a conflict.
It was falsified: the reassessment step's own conflict read was usually `False`, so an instruction gated
on a perceived conflict never engaged. No target improvement; reverted. Lesson: **prompting a stage about
information it does not hold cannot repair missing information flow.**

### Intervention 4: propagate prior conflict into reassessment (partially supported, rejected, reverted)

A coupled plumbing-plus-prompt change that passed the triage-detected conflict into reassessment as prior
context ([`baselines/intervention-04/`](../baselines/intervention-04/)). The mechanism worked (the missing
resolvability classification was eliminated and ARC-08 discrimination was preserved), but at the system
level the target case reached `ASK` only 1/5 while a previously-correct case acquired a spurious `ASK` 2/5.
Rejected and reverted. Lesson: **a mechanism can work locally and still be rejected at the system level
when it trades an unreliable gain for a regression on a previously correct case.**

### Intervention 5: distinguish telemetry acquisition from missing evidence (accepted)

Root cause on ARC-03: the Investigator used `needs_live_telemetry` as a generic "more information needed"
signal, so it tried the (backendless) telemetry tool, failed, never retrieved, and the policy produced an
**accidentally-correct** `ESCALATE(tool_failure)` with the wrong evidence path and the wrong reason. The
triage prompt was narrowed so telemetry means a genuine current-reading/telemetry-tool acquisition
([`baselines/intervention-05/`](../baselines/intervention-05/)).

After the change, ARC-03: telemetry `False` 5/5, retrieval `True` 5/5, `DOC-COMMS-A31` retrieved 5/5,
tool-failure eliminated. The contrast case ARC-06 (the deliberate telemetry-tool-failure case) kept
telemetry `True` 5/5 and `ESCALATE(tool_failure)` 5/5. ARC-03's final gold reason was still wrong, because
repairing the evidence-source path exposed a separate sufficiency failure downstream. Accepted anyway,
because the mechanism is now correct. Lesson: **an accidentally-correct final decision can hide an
incorrect mechanism**, which is why I5 is kept even though ARC-03's headline decision did not improve.

### Intervention 6: shared evidence-sufficiency semantics (partially supported, rejected, reverted)

Hypothesis: "sufficient" should mean enough evidence for a bounded, policy-actionable diagnosis, not
definitive root-cause certainty. The same sufficiency definition was applied at both places the system
judges it (triage `supplied_sufficient` and reassessment `evidence_sufficient`)
([`baselines/intervention-06/`](../baselines/intervention-06/)). Results: ARC-21 moved from
`evidence_sufficient=False` 5/5 to `True` 5/5 and then reached MEDIUM confidence → `ESCALATE(low_confidence)`
5/5, the full gold path. But the co-primary target ARC-03 stayed `True` 5/5 (unmoved), and a
previously-correct case (ARC-09) regressed from `ASK` 5/5 to mostly `ESCALATE(internal_error)`. Rejected
and reverted despite the ARC-21 win, because it failed the ARC-03 edge and broke a correct case. Lesson:
**one prose-level sufficiency definition could not reliably separate a "bounded differential" (ARC-21)
from "inspection-only" evidence (ARC-03).**

### Intervention 7: Diagnosis confidence calibration (falsified, reverted)

Defined HIGH/MEDIUM/LOW in the Diagnosis prompt in terms of unresolved material alternatives
([`baselines/intervention-07/`](../baselines/intervention-07/)). With I6 reverted, the sufficiency gate
kept the target cases out of Diagnosis: ARC-09 and ARC-21 reached Diagnosis 0/5, and ARC-10 only 1/5 and
still chose HIGH. Across all 41 Diagnosis-executed samples in the five runs, MEDIUM was emitted **0 times**;
the HIGH guard cases (ARC-22, ARC-13, ARC-15, etc.) stayed HIGH, so the change was not harmful, but it had
no useful behavioral effect. Falsified and reverted. Lesson: **downstream prompt calibration cannot repair
a latent structure that is discarded or never made explicit upstream**. Confidence calibration is
downstream of the sufficiency gate, so the targets could not even exercise it.

## 5. Accepted active system at this checkpoint

At the accepted behavioral HEAD `bd9cb95`, the accepted behavioral stack is:

- **I1**: Diagnosis confidence/answer coupling
- **I2**: monotonic Investigator conflict preservation
- **I5**: telemetry-vs-missing-evidence triage semantics
- **evaluator auditability**: per-case `mechanism_state` plus the observed triage choices
  (`triage_needs_retrieval`, `triage_needs_live_telemetry`), observability-only

Rejected or falsified, and preserved as historical evidence but **not active**: **I3, I4, I6, I7**. Their
run artifacts and summaries remain under [`baselines/`](../baselines/) unchanged.

## 6. What the experiments established

The cycle splits cleanly into two kinds of outcome.

**Local fixes worked when the mechanism was explicit.** I1 (a consistency constraint), I2 (deterministic
state preservation), and I5 (evidence-source semantics) each targeted a well-localized, inspectable
mechanism and stuck. These were either deterministic bugs or narrow, checkable prompt semantics.

**Prompt clarification failed when the model had to rediscover latent diagnostic structure from prose.**
I3, I6, and I7 all asked a stage to re-derive, from raw text, a distinction that another stage had already
(or should have) determined. I3 asked reassessment to act on a conflict it did not perceive; I6 asked a
single sufficiency definition to separate a bounded differential from inspection-only evidence; I7 asked
Diagnosis to down-rate confidence for a differential it could not see as such. Sharper wording did not
reliably repair any of them.

The most consistent explanation across them, offered here as an architectural inference rather than a
demonstrated causal result, is an information boundary. The Investigator→Diagnosis handoff currently carries
`evidence_sufficient`, `evidence_conflict`, `gap_user_resolvable`, and the evidence list, but **no explicit
representation of what diagnostic shape the gathered evidence actually supports**: whether it supports one
bounded conclusion, a bounded set of competing alternatives, or no bounded conclusion at all (evidence that
only prescribes further inspection). Diagnosis receives the incident text and the evidence prose and must
reconstruct that structure every time. On this reading, the three resistant interventions were each, in
effect, trying to compensate with wording for a distinction that is discarded at the stage boundary. This
remains a hypothesis: no implemented representation has yet isolated the effect, which is precisely what
the design-only I8 review (below) exists to test.

## 7. Diagnostic-shape architecture finding (design only)

A design-only review turned that observation into a concrete, minimal proposal. **Nothing below is
implemented**; no code, schema, node, prompt, or policy change exists for it.

The proposal is a single enum describing what the final gathered evidence supports:

- `SINGLE_CONCLUSION`: one bounded, action-relevant conclusion.
- `BOUNDED_DIFFERENTIAL`: a small set of material competing alternatives remains.
- `NO_BOUNDED_CONCLUSION`: no bounded conclusion yet; the evidence primarily indicates that further
  evidence, inspection, or measurement is required.

Inspecting the frozen cases, they map conceptually as:

| Diagnostic shape | Cases | Gold outcome |
| --- | --- | --- |
| `SINGLE_CONCLUSION` | ARC-18, ARC-22, ARC-13, ARC-15 | ANSWER (high confidence) |
| `BOUNDED_DIFFERENTIAL` | ARC-09, ARC-10, ARC-21 | ASK or `ESCALATE(low_confidence)` |
| `NO_BOUNDED_CONCLUSION` | ARC-03 | `ESCALATE(evidence_unresolvable)` |

This is useful for three reasons. ARC-09 versus ARC-10/ARC-21 have the **same** diagnostic shape
(`BOUNDED_DIFFERENTIAL`); under this abstraction they share a shape and differ in `gap_user_resolvable`
(ARC-09 requester-resolvable, ARC-10/ARC-21 not), which keeps shape and gap ownership as separate axes.
They also differ, of course, in their concrete evidence and expected terminal outcome. ARC-03 is distinguishable from a bounded differential even though it has a relevant
retrieved document, which is exactly the distinction I6 could not express in prose. And the shape is
orthogonal to conflict, gap ownership, technician involvement, retrieval need, answer presence, and the
final decision. These mappings are a design aid only; they are **not** added to the dataset as gold labels.

## 8. Architecture options considered (design only)

- **A: enrich the Investigator output.** Smallest graph change, but shape would be classified at two
  sites (triage skip-branch and reassessment retrieval-branch), which risks the same two-location semantic
  drift that made I6 fragile.
- **B: a dedicated diagnostic-shape synthesis step. Chosen design direction.** One path-independent
  owner classifies the final gathered evidence once and emits only the shape enum. It does not produce a
  diagnosis or an answer, so it does not become a second Diagnosis Specialist.
- **C: move closure into Diagnosis.** Rejected: it weakens the pre-Diagnosis fail-closed boundary and
  requires broader policy changes.
- **D: reuse the existing booleans.** Rejected: `evidence_sufficient` and `gap_user_resolvable` are lossy
  and already demonstrably inconsistent between stages; they cannot impose a shared closure invariant
  (ARC-03's `evidence_sufficient=True` is itself the wrong value).

The intended consumption is deterministic: derive `evidence_sufficient` from the shape
(`!= NO_BOUNDED_CONCLUSION`), and forbid HIGH confidence while a `BOUNDED_DIFFERENTIAL` remains. Both
derivations hold across all eight matrix cases, and the deterministic policy would stay unchanged because
the shape only feeds the fields the policy already reads. This is design approval only; no I8
implementation exists at this checkpoint. The decision will be recorded as ADR `0005` if and when it is
implemented.

## 9. Planned I8 rollout (future work)

The implementation, when approved, is deliberately split so that the representation is proven before any
behavior trusts it.

- **I8A: representation and measurement.** Add a `DiagnosticShape`, classify the final gathered evidence
  once, and persist it as an audit signal only. No existing behavior consumes it; `evidence_sufficient`
  stays authoritative; Diagnosis does not receive the shape. A misclassification cannot alter accepted
  behavior. Purpose: **measure whether the representation is reliable before anything depends on it**, the
  same auditability-before-behavior discipline used earlier in the cycle.
- **I8B: sufficiency consumption (candidate).** Only if I8A is reliable: test deriving `evidence_sufficient`
  from the shape. Primary target ARC-03.
- **I8C: confidence constraint (candidate).** Only after representation and sufficiency are validated:
  test forbidding HIGH confidence when a genuine bounded differential remains. Primary target ARC-10.

I8B and I8C are experimental candidates, not committed designs.

## 10. Current stopping point

The project intentionally stops here, before implementing I8. I1, I2, and I5 are the accepted behavioral
interventions; I3, I4, I6, and I7 remain preserved as rejected or falsified evidence. The I1 to I7 cycle
indicates that the next reliability problem is likely no longer well isolated as another prompt tweak: the
most consistent reading is that it concerns the structured information crossing the evidence-gathering →
Diagnosis boundary, a hypothesis the behavior-neutral I8A step is designed to test. The next planned
experiment is the behavior-neutral I8A diagnostic-shape measurement.

- Accepted behavioral HEAD: `bd9cb95` (later `main` commits are documentation-only)
- Repository: private
- Intervention 8: not started (design-only review recorded above)
