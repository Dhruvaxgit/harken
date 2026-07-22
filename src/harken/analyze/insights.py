"""Theme extraction — group mentions into the topics people keep raising.

No API key, no embeddings: a transparent TF-based salient-term extractor that
clusters mentions by their dominant shared terms. Good enough to answer "what
are people actually talking about?" at a glance. An optional LLM pass can relabel
these themes with nicer names (see :meth:`harken.pipeline.Pipeline._maybe_llm_label`).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from math import ceil

from harken.models import Mention

_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "if",
    "then",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "to",
    "of",
    "in",
    "on",
    "for",
    "with",
    "at",
    "by",
    "from",
    "as",
    "into",
    "about",
    "it",
    "its",
    "this",
    "that",
    "these",
    "those",
    "i",
    "you",
    "he",
    "she",
    "we",
    "they",
    "them",
    "my",
    "your",
    "our",
    "their",
    "me",
    "us",
    "so",
    "just",
    "very",
    "really",
    "not",
    "no",
    "yes",
    "can",
    "will",
    "would",
    "should",
    "could",
    "do",
    "does",
    "did",
    "have",
    "has",
    "had",
    "get",
    "got",
    "im",
    "ive",
    "id",
    "youre",
    "dont",
    "doesnt",
    "didnt",
    "isnt",
    "wasnt",
    "arent",
    "thats",
    "whats",
    "there",
    "here",
    "what",
    "which",
    "who",
    "when",
    "where",
    "why",
    "how",
    "all",
    "any",
    "some",
    "more",
    "most",
    "much",
    "many",
    "one",
    "two",
    "up",
    "out",
    "down",
    "over",
    "than",
    "too",
    "also",
    "like",
    "use",
    "using",
    "used",
    "still",
    "even",
    "now",
    "new",
    "make",
    "makes",
    "made",
    "take",
    "takes",
    "taking",
    "via",
    "after",
    "before",
    "while",
    "well",
    "because",
    "http",
    "https",
    "com",
    "www",
    "amp",
    # generic product/review and valence words make poor topic labels
    "app",
    "apps",
    "product",
    "products",
    "tool",
    "tools",
    "thing",
    "things",
    "both",
    "around",
    "actually",
    "again",
    "genuinely",
    "honestly",
    "feel",
    "feels",
    "whole",
    "bit",
    "nothing",
    "groundbreaking",
    "note",
    "notes",
    "good",
    "better",
    "bad",
    "great",
    "love",
    "loved",
    "nice",
    "best",
    "worse",
    "beautiful",
    "delightful",
    "confusing",
    "expensive",
    "ridiculous",
    "solid",
    "fine",
}

_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9'+-]{1,}")

# Collapse a small set of high-confidence variants before document-frequency
# counting. This is deliberately conservative: it fixes obvious fragmentation
# ("fast" versus "speed") without pretending to be a general stemmer.
_ALIASES = {
    "cost": "pricing",
    "costs": "pricing",
    "docs": "documentation",
    "fast": "performance",
    "faster": "performance",
    "fastest": "performance",
    "latency": "performance",
    "performant": "performance",
    "price": "pricing",
    "prices": "pricing",
    "slow": "performance",
    "sluggish": "performance",
    "speed": "performance",
    "speedy": "performance",
    "synchronization": "sync",
    "syncing": "sync",
}


@dataclass
class Theme:
    label: str
    terms: list[str]
    count: int = 0
    mention_ids: list[str] = field(default_factory=list)


def _tokens(text: str, extra_stop: set[str]) -> list[str]:
    out = []
    # Preserve a few common multi-word concepts as one thematic token.
    normalized = re.sub(r"\b(?:open|closed)\s+source\b", "open-source", text.lower())
    for t in _TOKEN_RE.findall(normalized):
        t = t.split("'")[0].strip("-+")  # normalise possessives/contractions: quill's -> quill
        if len(t) < 3 or t in _STOPWORDS or t in extra_stop or t.isdigit():
            continue
        out.append(_ALIASES.get(t, t))
    return out


class ThemeExtractor:
    """Cluster mentions into themes by shared salient terms."""

    name = "tf-themes"

    def __init__(self, max_themes: int = 6, min_cluster: int = 2):
        self.max_themes = max_themes
        self.min_cluster = min_cluster

    def extract(self, mentions: list[Mention]) -> list[Theme]:
        if not mentions:
            return []

        # Re-analysis must remove labels that no longer belong to a cluster;
        # otherwise unclaimed mentions retain stale themes from an older run.
        for mn in mentions:
            mn.theme = None

        # the tracked query terms should not themselves become themes
        extra_stop = set()
        for mn in mentions:
            for w in _TOKEN_RE.findall(mn.query.lower()):
                extra_stop.add(w)

        # document frequency of each term. Insert in sorted order so that
        # Counter's tie-breaking (which follows dict insertion order) is
        # deterministic across processes — plain `set` iteration order is
        # randomised per-process by PYTHONHASHSEED and would otherwise make
        # theme labels flip between runs on identical data.
        df: Counter[str] = Counter()
        per_mention: dict[str, set[str]] = {}
        for mn in mentions:
            toks = set(_tokens(mn.content, extra_stop))
            per_mention[mn.id] = toks
            df.update(sorted(toks))

        # Consider every recurring candidate. Taking only max_themes seeds here
        # loses topics when early seeds overlap and claim the same mentions.
        seeds = [t for t, c in df.most_common() if c >= self.min_cluster]
        if not seeds:
            return []

        themes: list[Theme] = []
        claimed: set[str] = set()
        for seed in seeds:
            if len(themes) >= self.max_themes:
                break
            members = [mn for mn in mentions if mn.id not in claimed and seed in per_mention[mn.id]]
            if len(members) < self.min_cluster:
                continue
            # enrich the label with the next most co-occurring term
            co: Counter[str] = Counter()
            for mn in members:
                co.update(sorted(per_mention[mn.id]))
            co.pop(seed, None)
            # A label's second word should describe the cluster, not merely be
            # an incidental word in one member. Keep it only when it recurs in
            # at least half of the cluster (and at least two mentions).
            secondary = [
                term for term, count in co.most_common(2) if count >= max(2, ceil(len(members) / 2))
            ]
            terms = [seed] + secondary
            label = " / ".join(terms[:2]) if len(terms) > 1 else seed
            theme = Theme(
                label=label,
                terms=terms,
                count=len(members),
                mention_ids=[mn.id for mn in members],
            )
            for mn in members:
                mn.theme = label
                claimed.add(mn.id)
            themes.append(theme)

        themes.sort(key=lambda t: (-t.count, t.label))
        return themes
