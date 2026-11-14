"""Choose a real embedding provider (API or local) and implement this contract."""
from typing import Protocol
from pathlib import Path
import hashlib
import json
import math
import warnings
from importlib.metadata import version

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MODEL_REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        ...


class MyEmbedder:
    """Real local CPU embeddings; identical encoding for documents and queries."""

    def __init__(self, model_name: str = MODEL_NAME, *, revision: str = MODEL_REVISION,
                 cache_folder: Path | None = None, batch_size: int = 32,
                 local_files_only: bool = False) -> None:
        from sentence_transformers import SentenceTransformer
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
            raise ValueError("Pin model to a full commit SHA")
        self.model_name = model_name
        self.revision = revision
        self.batch_size = batch_size
        self.model = SentenceTransformer(model_name, revision=revision, device="cpu",
            trust_remote_code=False, cache_folder=str(cache_folder) if cache_folder else None,
            model_kwargs={"use_safetensors": True}, local_files_only=local_files_only)
        self.dimensions = self.model.get_sentence_embedding_dimension()
        self.model.tokenizer.truncation_side = "right"
        self.config = {"provider": "local SentenceTransformers", "model": model_name,
            "revision": revision, "dimensions": self.dimensions, "device": "cpu",
            "normalize_embeddings": True, "max_seq_length": self.model.max_seq_length,
            "query_document_encoding": "same encode; no prefix or prompt",
            "truncation": "model default right truncation; token statistics recorded",
            "packages": {p: version(p) for p in ("sentence-transformers", "transformers", "torch")}}
        self.signature = hashlib.sha256(json.dumps(self.config, sort_keys=True).encode()).hexdigest()

    def token_stats(self, texts: list[str]) -> dict:
        lengths = []
        for start in range(0, len(texts), self.batch_size):
            tokens = self.model.tokenizer(texts[start:start + self.batch_size],
                truncation=False, padding=False, verbose=False)
            lengths.extend(len(ids) for ids in tokens["input_ids"])
        return {"text_count": len(texts), "total_tokens_before_truncation": sum(lengths),
            "max_tokens_before_truncation": max(lengths, default=0),
            "truncated_text_count": sum(n > self.model.max_seq_length for n in lengths),
            "max_seq_length": self.model.max_seq_length}

    def _encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if any(not isinstance(t, str) or not t.strip() for t in texts):
            raise ValueError("Embedding inputs must be nonempty strings")
        stats = self.token_stats(texts)
        if stats["truncated_text_count"]:
            warnings.warn(f"{stats['truncated_text_count']} inputs exceed token limit "
                f"{self.model.max_seq_length}; right truncation applies", stacklevel=2)
        vectors = self.model.encode(texts, batch_size=self.batch_size,
            normalize_embeddings=True, convert_to_numpy=True,
            show_progress_bar=False, prompt="").tolist()
        if len(vectors) != len(texts):
            raise ValueError("Embedding output count mismatch")
        for vector in vectors:
            if len(vector) != self.dimensions or not all(math.isfinite(v) for v in vector):
                raise ValueError("Invalid embedding dimensions or nonfinite values")
            if not any(v != 0 for v in vector):
                raise ValueError("Zero embedding cannot be used with cosine")
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode(texts)

    def embed_query(self, question: str) -> list[float]:
        return self._encode([question])[0]
