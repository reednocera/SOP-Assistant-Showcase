"""BM25 keyword search over SOP documents."""

import re

from rank_bm25 import BM25Okapi

from loader import SOP


def _tokenize(text: str) -> list[str]:
    """Lowercase and split on non-alphanumeric characters."""
    return re.findall(r'[a-z0-9]+', text.lower())


class SOPIndex:
    """BM25 index over a collection of SOPs."""

    def __init__(self, sops: list[SOP]):
        self.sops = sops
        self._corpus = []
        for sop in sops:
            tokens = _tokenize(sop.id + ' ' + sop.title + ' ' + sop.body)
            self._corpus.append(tokens)
        self._bm25 = BM25Okapi(self._corpus)

    def search(self, query: str, top_k: int = 5) -> list[SOP]:
        """Return the top-k most relevant SOPs for the query."""
        query_tokens = _tokenize(query)
        if not query_tokens:
            return self.sops[:top_k]

        scores = self._bm25.get_scores(query_tokens)

        if scores.max() > 0:
            top_indices = scores.argsort()[::-1][:top_k]
            return [self.sops[i] for i in top_indices]

        # Fallback: match query tokens against SOP metadata
        query_lower = query.lower()
        scored = []
        for i, sop in enumerate(self.sops):
            meta = (sop.id + ' ' + sop.title).lower()
            count = sum(1 for token in query_tokens if token in meta)
            scored.append((count, i))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [self.sops[i] for _, i in scored[:top_k]]

    def search_summaries(self, query: str, top_k: int = 8) -> list[dict]:
        """Return top-k candidates as lightweight dicts (id, title, summary only)."""
        query_tokens = _tokenize(query)
        if not query_tokens:
            return [{"id": s.id, "title": s.title, "summary": s.summary}
                    for s in self.sops[:top_k]]

        scores = self._bm25.get_scores(query_tokens)

        if scores.max() > 0:
            top_indices = scores.argsort()[::-1][:top_k]
        else:
            scored = []
            for i, sop in enumerate(self.sops):
                meta = (sop.id + ' ' + sop.title).lower()
                count = sum(1 for token in query_tokens if token in meta)
                scored.append((count, i))
            scored.sort(key=lambda x: x[0], reverse=True)
            top_indices = [i for _, i in scored[:top_k]]

        return [{"id": self.sops[i].id,
                 "title": self.sops[i].title,
                 "summary": self.sops[i].summary}
                for i in top_indices]

    def get_sops_by_ids(self, ids: list[str]) -> list[SOP]:
        """Return full SOP objects for the given IDs, preserving order."""
        id_map = {s.id: s for s in self.sops}
        return [id_map[i] for i in ids if i in id_map]
