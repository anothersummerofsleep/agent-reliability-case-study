"""Fictional Northwind corpus + a tiny BM25 retriever (Phase 1).

Deliberately minimal and inspectable: the corpus is parsed from the single frozen
source ``datasets/corpus/manuals.md`` (no duplicated content), and retrieval is a
hand-rolled Okapi BM25 over those ten short docs. No database, no embeddings, no
external service - a weak lexical baseline is the point, so the frozen ARC-14 /
ARC-15 distractors stay genuinely capable of fooling it. ``k`` is frozen at 2 for
the baseline; do not tune it before the baseline is captured.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CORPUS = Path(__file__).resolve().parents[2] / "datasets" / "corpus" / "manuals.md"
DEFAULT_K = 2

_DOC_LINE = re.compile(r"^-\s+(DOC-[A-Z0-9-]+):\s*(.*)$")
_TOKEN = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class CorpusDoc:
    doc_id: str
    text: str
    is_distractor: bool


@dataclass(frozen=True)
class RetrievedDoc:
    doc_id: str
    score: float
    rank: int  # 1-based


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def load_corpus(path: Path | str | None = None) -> list[CorpusDoc]:
    """Parse the frozen markdown corpus into structured docs.

    Each ``- DOC-XXX: ...`` bullet starts a doc; indented continuation lines are
    folded into its text. A ``(DISTRACTOR)`` marker flags a precision trap.
    """
    p = Path(path) if path is not None else DEFAULT_CORPUS
    docs: list[CorpusDoc] = []
    current_id: str | None = None
    current_parts: list[str] = []

    def _flush() -> None:
        nonlocal current_id, current_parts
        if current_id is not None:
            text = " ".join(part.strip() for part in current_parts).strip()
            docs.append(
                CorpusDoc(
                    doc_id=current_id,
                    text=text,
                    is_distractor="(DISTRACTOR)" in text,
                )
            )
        current_id = None
        current_parts = []

    with p.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            m = _DOC_LINE.match(line.strip()) if line.strip().startswith("- DOC-") else None
            if m:
                _flush()
                current_id = m.group(1)
                current_parts = [m.group(2)]
            elif current_id is not None and line[:1].isspace() and line.strip():
                # indented continuation of the current doc
                current_parts.append(line)
            elif current_id is not None and not line.strip():
                # blank line ends the current doc block
                _flush()
    _flush()
    return docs


class BM25Retriever:
    """Okapi BM25 over a small in-memory corpus. Deterministic; ties break by the
    corpus order of ``doc_id`` (stable)."""

    def __init__(self, docs: list[CorpusDoc], *, k1: float = 1.5, b: float = 0.75):
        if not docs:
            raise ValueError("BM25Retriever needs a non-empty corpus")
        self.docs = docs
        self.by_id = {d.doc_id: d for d in docs}
        self.k1 = k1
        self.b = b
        self._doc_tokens = [_tokenize(d.text + " " + d.doc_id) for d in docs]
        self._doc_len = [len(toks) for toks in self._doc_tokens]
        self._avgdl = sum(self._doc_len) / len(docs)
        n = len(docs)
        # document frequency per term
        df: dict[str, int] = {}
        for toks in self._doc_tokens:
            for term in set(toks):
                df[term] = df.get(term, 0) + 1
        # Okapi idf with the +1 floor so common terms never go negative
        self._idf = {
            term: math.log(1 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()
        }
        self._tf = [self._term_freqs(toks) for toks in self._doc_tokens]

    @staticmethod
    def _term_freqs(tokens: list[str]) -> dict[str, int]:
        freqs: dict[str, int] = {}
        for t in tokens:
            freqs[t] = freqs.get(t, 0) + 1
        return freqs

    def _score(self, query_terms: list[str], idx: int) -> float:
        tf = self._tf[idx]
        dl = self._doc_len[idx]
        score = 0.0
        for term in query_terms:
            if term not in tf:
                continue
            idf = self._idf.get(term, 0.0)
            f = tf[term]
            denom = f + self.k1 * (1 - self.b + self.b * dl / self._avgdl)
            score += idf * (f * (self.k1 + 1)) / denom
        return score

    def doc(self, doc_id: str) -> CorpusDoc:
        return self.by_id[doc_id]

    def search(self, query: str, k: int = DEFAULT_K) -> list[RetrievedDoc]:
        """Return the top-``k`` docs by BM25, best first. Docs with a zero score are
        excluded (a non-matching query retrieves nothing rather than noise)."""
        query_terms = _tokenize(query)
        scored = [
            (self._score(query_terms, i), i) for i in range(len(self.docs))
        ]
        # sort by score desc, then by original index asc (stable tie-break)
        scored.sort(key=lambda s: (-s[0], s[1]))
        out: list[RetrievedDoc] = []
        for rank, (score, i) in enumerate(scored[:k], start=1):
            if score <= 0.0:
                break
            out.append(RetrievedDoc(doc_id=self.docs[i].doc_id, score=score, rank=rank))
        return out


def default_retriever(path: Path | str | None = None) -> BM25Retriever:
    return BM25Retriever(load_corpus(path))
