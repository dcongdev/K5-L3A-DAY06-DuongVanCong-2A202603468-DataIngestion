"""Embed frozen A/B chunks locally and synchronize PostgreSQL; no benchmark run."""
import json
import hashlib
import os
import platform
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv
import psycopg

from .embeddings import MyEmbedder, MODEL_NAME, MODEL_REVISION
from .models import Chunk
from .prepare_chunks import CONFIG
from .store import PgVectorStore
from .validate_benchmark import validate
from .verify_vector_store import verify_store


def ingest(repo: Path) -> dict:
    run_started = perf_counter()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    result_dir = repo / "results"
    result_dir.mkdir(exist_ok=True)
    report = {"run_id": run_id, "started_at": datetime.now(timezone.utc).isoformat(), "status": "running",
              "stage": "validate inputs", "strategies": {}, "benchmark_run": False,
              "requested_model": {"name": MODEL_NAME, "revision": MODEL_REVISION},
              "api_cost": 0, "cost_note": "Local CPU; electricity/hardware/download traffic not priced"}
    try:
        validate(repo)
        summary = json.loads((repo / "data/chunks/summary.json").read_text(encoding="utf-8"))
        if summary["config"] != CONFIG:
            raise ValueError("Chunk config changed; regenerate chunks explicitly")
        prepared = {}
        for name in ("A", "B"):
            path = repo / summary["strategies"][name]["path"]
            payload = path.read_bytes()
            if hashlib.sha256(payload).hexdigest() != summary["strategies"][name]["sha256"]:
                raise ValueError(f"Chunk file hash mismatch: {name}")
            prepared[name] = [Chunk(**json.loads(line)) for line in payload.decode("utf-8").splitlines()]
        load_dotenv(repo / "starter/.env")
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL missing in starter/.env")
        report["stage"] = "database preflight"
        with psycopg.connect(database_url, connect_timeout=5) as conn:
            if not conn.execute("SELECT 1 FROM pg_extension WHERE extname='vector'").fetchone():
                raise ValueError("pgvector extension missing")
        # Keep downloaded model files within the repo cache (ignored by Git).
        cache = repo / ".cache"
        os.environ.setdefault("HF_HOME", str(cache / "huggingface"))
        report["stage"] = "load model"
        started = perf_counter()
        embedder = MyEmbedder(cache_folder=cache / "models")
        report["model_load_seconds"] = perf_counter() - started
        report["embedding"] = embedder.config
        report["embedding_signature"] = embedder.signature
        report["runtime"] = {"python": sys.version, "platform": platform.platform(),
            "packages": {p: version(p) for p in ("sentence-transformers", "transformers", "torch", "psycopg", "huggingface-hub")}}
        store = PgVectorStore(database_url, embedder.dimensions, embedding_signature=embedder.signature)
        store.create_schema()
        with store.connect() as conn:
            report["database"] = {"schema": store.schema, "search": "exact cosine, no ANN index",
                "postgresql": conn.execute("SHOW server_version").fetchone()[0],
                "pgvector": conn.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()[0]}
        for name, chunks in prepared.items():
            report["stage"] = f"embed/store {name}"
            texts = [c.text for c in chunks]
            stats = embedder.token_stats(texts)
            started = perf_counter()
            vectors = embedder.embed_documents(texts)
            embedding_seconds = perf_counter() - started
            print(f"{name}: embedded {len(vectors)} vectors ({embedder.dimensions} dimensions)", flush=True)
            if name == "A":
                report["store_contract_checks"] = verify_store(database_url, embedder.dimensions,
                    embedder.signature, chunks, vectors)
            started = perf_counter()
            store.upsert(name, chunks, vectors)
            count_first = store.count(name)
            write_seconds = perf_counter() - started
            # Second identical write proves idempotence without a second embedding call.
            started = perf_counter()
            store.upsert(name, chunks, vectors)
            count_second = store.count(name)
            if count_first != len(chunks) or count_second != count_first:
                raise ValueError(f"Reingestion duplicate/count mismatch: {name}")
            report["strategies"][name] = {"chunk_count": len(chunks), "chunk_file_sha256": summary["strategies"][name]["sha256"],
                "embedding_seconds": embedding_seconds, "store_seconds": write_seconds,
                "reingest_seconds": perf_counter() - started,
                "count_first": count_first, "count_after_reingest": count_second, "token_stats": stats}
        report["strategies"]["C"] = {"physical_strategy": "B", "count": store.count("C"), "extra_embedding_calls": 0}
        report["stage"] = "technical smoke query (not benchmark)"
        # Operational query deliberately outside the benchmark, no gold or hit labels.
        query = "Tìm nội dung liên quan đến lập trình Python."
        query_vector = embedder.embed_query(query)
        checks = []
        for name, filters in (("A", {}), ("B", {}), ("C", {}),
                              ("C", {"Type": "Process"}), ("C", {"Type": "Informational"}),
                              ("C", {"Type": "Standards Track"})):
            hits = store.search(name, query_vector, filters=filters)
            if len(hits) != 3 or any(any(h["metadata"].get(k) != v for k, v in filters.items()) for h in hits):
                raise ValueError("Technical top-3/filter check failed")
            checks.append({"strategy": name, "filter": filters, "returned": len(hits),
                           "chunk_ids": [h["chunk_id"] for h in hits], "passed": True})
        report["smoke_check"] = {"query": query, "checks": checks, "not_benchmark": True}
        report["status"] = "ok"
        report["stage"] = "complete"
    except Exception as exc:
        report["status"] = "failed"
        # Do not serialize exception strings that could include DSN/credentials.
        report["error_type"] = type(exc).__name__
        raise
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        report["total_seconds"] = perf_counter() - run_started
        serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        history = result_dir / "ingestion_runs"
        history.mkdir(exist_ok=True)
        (history / f"{run_id}.json").write_text(serialized, encoding="utf-8")
        (result_dir / "ingestion.json").write_text(serialized, encoding="utf-8")
    return report


def main() -> None:
    try:
        ingest(Path(__file__).resolve().parents[2])
    except Exception as exc:
        raise SystemExit(f"Ingestion failed ({type(exc).__name__}); see results/ingestion.json for stage. No fallback vectors used.") from None
    print("Ingestion OK: A/B persisted; C reuses B. Reingestion and top-3/filter checks passed.")
    print("No dev/test retrieval or evaluation metrics produced.")


if __name__ == "__main__":
    main()
