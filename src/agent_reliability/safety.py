"""Deterministic safety detector (frozen spec).

A hazard token counts as *active* only when it is (a) positive - not governed by a
negation cue - AND (b) not scoped to a resolved / isolated state. This is a small,
testable heuristic, deliberately NOT a general NLP classifier. It runs at intake,
independently of routing, so a misrouted hazard still trips gate rule 1.
"""

from __future__ import annotations

import re

# Multi-word terms must come before their single-word prefixes so the longer match
# is found first when scanning.
HAZARD_TERMS: tuple[str, ...] = (
    "burning smell",
    "gas leak",
    "refrigerant leak",
    "chemical smell",
    "arc flash",
    "electrical shock",
    "smoke",
    "fire",
    "flames",
    "flame",
    "burning",
    "sparks",
    "explosion",
    "evacuate",
    "shock",
)

NEGATORS: tuple[str, ...] = ("no", "not", "without", "never", "cleared", "gone", "n't")

RESOLUTION_CUES: tuple[str, ...] = (
    "isolated",
    "locked out",
    "lockout",
    "de-energized",
    "de-energised",
    "shut down and",
    "already resolved",
    "since returned to service",
    "was cleared",
    "been cleared",
    "has cleared",
)

# Tokens allowed to sit between a negator and a hazard term for the negation to
# still apply (handles coordinated lists like "no smoke, fire, or burning smell").
_HAZARD_WORDS = {w for term in HAZARD_TERMS for w in term.split()}
_CONNECTORS = {"or", "and", "nor", "a", "an", "any", "the", "of", "is", "are", "there"}
_ALLOWED_BETWEEN = _HAZARD_WORDS | _CONNECTORS


def _clause_start(text: str, pos: int) -> int:
    return max(
        text.rfind(".", 0, pos),
        text.rfind(";", 0, pos),
        text.rfind("\n", 0, pos),
    )


# Resolution/isolation is scoped LOCALLY to the hazard's own segment (split on
# clause punctuation, commas, and "but"), so a resolved historical hazard or the
# isolation of a different object cannot suppress a separate active hazard in the
# same sentence. Negation (below) stays clause-wide so a leading "no" can still
# distribute across a coordinated list ("no smoke, fire, or burning smell").
_SEGMENT_BOUNDARY = re.compile(r"[.;,\n]|\bbut\b")


def _segment_for(text: str, hazard_start: int, hazard_end: int) -> str:
    seg_start = 0
    seg_end = len(text)
    for m in _SEGMENT_BOUNDARY.finditer(text):
        if m.end() <= hazard_start:
            seg_start = m.end()
        elif m.start() >= hazard_end:
            seg_end = m.start()
            break
    return text[seg_start:seg_end]


def _is_negated(text: str, hazard_start: int) -> bool:
    clause = text[_clause_start(text, hazard_start) + 1 : hazard_start]
    last = -1
    for neg in NEGATORS:
        j = clause.rfind(neg)
        if j > last:
            last = j
            neg_len = len(neg)
    if last == -1:
        return False
    between = clause[last + neg_len :]
    words = re.findall(r"[a-z']+", between)
    return all(w in _ALLOWED_BETWEEN for w in words)


def _is_resolved(text: str, hazard_start: int, hazard_end: int) -> bool:
    segment = _segment_for(text, hazard_start, hazard_end)
    return any(cue in segment for cue in RESOLUTION_CUES)


def detect_safety_critical(incident_raw: str) -> bool:
    """Return True iff the incident contains an active (positive, non-resolved) hazard."""
    text = incident_raw.lower()
    for term in HAZARD_TERMS:
        for m in re.finditer(r"\b" + re.escape(term), text):
            if _is_negated(text, m.start()):
                continue
            if _is_resolved(text, m.start(), m.end()):
                continue
            return True
    return False
