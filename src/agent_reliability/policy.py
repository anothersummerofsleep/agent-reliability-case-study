"""The single authoritative deterministic policy (frozen Phase -1 spec).

One pure function, evaluated at three checkpoints. There is exactly one copy of the
decision rules. Returning ``None`` means CONTINUE (internal graph control - traverse
the normal edge to the next node); it is never a user-facing decision.

Guarantees (enforced by the explicit guards below and the tests):
* ANSWER is only rule 9, never a fallthrough.
* ``None`` never truthiness-coerces into a later rule (every guard is ``is``/``==``/``in``).
* high confidence + missing answer -> ESCALATE(internal_error)  (rule 7 guard)
* unsupported candidate answer   -> ESCALATE(grounding_failure) (rule 8)
* malformed terminal state       -> ESCALATE(internal_error)    (terminal fallthrough)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .contracts import GraphState
from .enums import AbstainReason, Confidence, Decision, EscalationReason, Route


@dataclass(frozen=True)
class PolicyDecision:
    decision: Decision
    escalation_reason: Optional[EscalationReason] = None
    abstain_reason: Optional[AbstainReason] = None


def _escalate(reason: EscalationReason) -> PolicyDecision:
    return PolicyDecision(Decision.ESCALATE, escalation_reason=reason)


def evaluate_policy(state: GraphState, *, terminal: bool) -> Optional[PolicyDecision]:
    """Evaluate the frozen policy against ``state``.

    Returns a :class:`PolicyDecision`, or ``None`` for CONTINUE. Pass
    ``terminal=True`` only at the final (post-Diagnosis/Grounding) checkpoint; a
    fallthrough there fails closed to ESCALATE(internal_error) instead of CONTINUE.
    """
    # 1. safety is absolute (above scope)
    if state.safety_critical is True:
        return _escalate(EscalationReason.SAFETY)

    # 2. out of scope -> abstain with the router-produced reason, else fail closed
    if state.route is Route.OUT_OF_SCOPE:
        if isinstance(state.abstain_reason, AbstainReason):
            return PolicyDecision(Decision.ABSTAIN, abstain_reason=state.abstain_reason)
        return _escalate(EscalationReason.INTERNAL_ERROR)

    # 3. tool failure after bounded retry
    if state.tool_failed is True:
        return _escalate(EscalationReason.TOOL_FAILURE)

    # 4. conflicting evidence
    if state.evidence_conflict is True:
        if state.gap_user_resolvable is True:
            return PolicyDecision(Decision.ASK)
        return _escalate(EscalationReason.CONFLICT_UNRESOLVABLE)

    # 5. insufficient evidence
    if state.evidence_sufficient is False:
        if state.gap_user_resolvable is True:
            return PolicyDecision(Decision.ASK)
        return _escalate(EscalationReason.EVIDENCE_UNRESOLVABLE)

    # 6. valid-but-uncertain diagnosis
    if state.confidence in (Confidence.LOW, Confidence.MEDIUM):
        if state.gap_user_resolvable is True:
            return PolicyDecision(Decision.ASK)
        return _escalate(EscalationReason.LOW_CONFIDENCE)

    # 7. guard: high confidence but no answer is a contract violation, not grounding
    if state.confidence is Confidence.HIGH and state.proposed_answer is None:
        return _escalate(EscalationReason.INTERNAL_ERROR)

    # 8. an answer exists but the evidence does not support it
    if state.answer_grounded is False:
        return _escalate(EscalationReason.GROUNDING_FAILURE)

    # 9. ANSWER - the only positive rule, never a fallthrough
    if (
        state.confidence is Confidence.HIGH
        and state.proposed_answer is not None
        and state.evidence is not None
        and len(state.evidence) > 0
        and state.answer_grounded is True
    ):
        return PolicyDecision(Decision.ANSWER)

    # fallthrough
    if terminal:
        return _escalate(EscalationReason.INTERNAL_ERROR)
    return None  # CONTINUE


def apply_policy(state: GraphState, *, terminal: bool) -> Optional[PolicyDecision]:
    """Evaluate the policy and, if it produced a decision, write it onto ``state``.

    Returns the same :class:`PolicyDecision` (or ``None`` for CONTINUE) so callers /
    conditional edges can branch. Mutating in place keeps the emitted decision on the
    graph state for the output-contract check.
    """
    result = evaluate_policy(state, terminal=terminal)
    if result is not None:
        state.decision = result.decision
        state.escalation_reason = result.escalation_reason
        if result.abstain_reason is not None:
            state.abstain_reason = result.abstain_reason
    return result
