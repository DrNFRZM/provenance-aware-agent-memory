"""Text embedders. The default is a dependency-free hashing embedder so that every
experiment is bit-for-bit reproducible; sentence-transformers is an optional swap-in."""

from __future__ import annotations

import re
from typing import Protocol, Sequence

import numpy as np

from .seeding import digest_int

_TOKEN = re.compile(r"[a-z0-9]+")


class Embedder(Protocol):
    dim: int

    def embed(self, text: str) -> np.ndarray: ...


class HashingEmbedder:
    """Signed feature hashing over word unigrams, word bigrams and character trigrams,
    L2-normalised. Lexical, not semantic: it is a stand-in whose only job in this
    project is to make claims about the same (subject, attribute) look alike
    regardless of their value, as a real embedder would."""

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim
        self._cache: dict[str, np.ndarray] = {}

    def _features(self, text: str) -> list[str]:
        words = _TOKEN.findall(text.lower())
        feats = [f"w:{w}" for w in words]
        feats += [f"b:{a}_{b}" for a, b in zip(words, words[1:])]
        for w in words:
            padded = f"^{w}$"
            feats += [f"c:{padded[i:i + 3]}" for i in range(len(padded) - 2)]
        return feats

    def embed(self, text: str) -> np.ndarray:
        hit = self._cache.get(text)
        if hit is not None:
            return hit
        vec = np.zeros(self.dim, dtype=np.float32)
        for f in self._features(text):
            h = digest_int("emb", f)
            vec[h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        self._cache[text] = vec
        return vec


class SentenceTransformerEmbedder:
    """Optional. Requires `pip install sentence-transformers`; the model is downloaded
    by that library on first use and is never bundled with this repository."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError("install the 'embeddings' extra to use this embedder") from exc
        self._model = SentenceTransformer(model_name)
        self.dim = int(self._model.get_sentence_embedding_dimension())
        self._cache: dict[str, np.ndarray] = {}

    def embed(self, text: str) -> np.ndarray:
        if text not in self._cache:
            v = self._model.encode([text], normalize_embeddings=True)[0]
            self._cache[text] = np.asarray(v, dtype=np.float32)
        return self._cache[text]


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def embed_all(embedder: Embedder, texts: Sequence[str]) -> np.ndarray:
    return np.stack([embedder.embed(t) for t in texts]) if texts else np.zeros((0, embedder.dim))
