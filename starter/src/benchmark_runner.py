"""Run dev, freeze selection, then test; never re-ingest or tune on test."""
import argparse
import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv
from psycopg import sql

from .embeddings import MyEmbedder
from .evaluation import evaluate_query, summarize
from .store import PgVectorStore
from .validate_benchmark import validate


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def select_strategy(rows):
    if {r["strategy"] for r in rows} != {"A", "B", "C"} or any(r["split"] != "dev" for r in rows):
        raise ValueError("Selection requires A/B/C dev metrics only")
    return min(rows, key=lambda r: (-r["hit3"], -r["hit1"], r["retrieval_seconds"], r["strategy"]))["strategy"]


def database_fingerprint(store):
    with store.connect() as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        indexes = conn.execute(sql.SQL("SELECT strategy,signature,dimensions FROM {} ORDER BY strategy").format(store.indexes_table)).fetchall()
        if {r[0] for r in indexes} != {"A", "B"} or any(r[1:] != (store.embedding_signature, store.dimensions) for r in indexes):
            raise ValueError("Indexes missing or incompatible with query model")
        records = conn.execute(sql.SQL("""SELECT strategy,chunk_id,document_id,source,page,text,metadata,
            embedding::text FROM {} ORDER BY strategy,chunk_id""").format(store.chunks_table)).fetchall()
    digest = hashlib.sha256(json.dumps([indexes, records], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return digest, records


def check_chunks(repo, records):
    summary = json.loads((repo / "data/chunks/summary.json").read_text(encoding="utf-8"))
    for strategy in ("A", "B"):
        path = repo / summary["strategies"][strategy]["path"]
        if sha(path) != summary["strategies"][strategy]["sha256"]:
            raise ValueError("Chunk artifact hash changed")
        expected = {c["chunk_id"]: c for c in map(json.loads, path.read_text(encoding="utf-8").splitlines())}
        actual = {r[1]: {"chunk_id": r[1], "document_id": r[2], "source": r[3], "page": r[4],
                         "text": r[5], "metadata": r[6]} for r in records if r[0] == strategy}
        if actual != expected:
            raise ValueError(f"Database chunks differ from current artifacts: {strategy}")


def run_split(repo, output, split, embedder, store, fingerprint):
    questions = [json.loads(l) for l in (repo / f"benchmark/{split}.jsonl").read_text(encoding="utf-8").splitlines()]
    traces = []
    with (output / f"{split}_traces.jsonl").open("w", encoding="utf-8") as stream:
        for number, question in enumerate(questions):
            started = perf_counter()
            vector = embedder.embed_query(question["question"])
            encode_seconds = perf_counter() - started
            # Rotate order to distribute first-search/cache effects. Encode once per question.
            names = ["A", "B", "C"]
            names = names[number % 3:] + names[:number % 3]
            for name in names:
                filters = question.get("filter", {}) if name == "C" else {}
                started = perf_counter()
                hits = store.search(name, vector, top_k=3, filters=filters)
                seconds = perf_counter() - started
                if any(any(h["metadata"].get(k) != v for k, v in filters.items()) for h in hits):
                    raise ValueError("Backend violated metadata filter")
                trace = {**evaluate_query(question, hits), "strategy": name,
                    "question": question["question"], "expected_answer": question["expected_answer"],
                    "gold_evidence": question["gold_evidence"], "input_filter": question.get("filter", {}),
                    "applied_filter": filters, "hits": hits, "retrieval_seconds": seconds,
                    "query_embedding_seconds": encode_seconds, "query_embedding_shared": True,
                    "query_token_stats": embedder.token_stats([question["question"]])}
                traces.append(trace)
                stream.write(json.dumps(trace, ensure_ascii=False) + "\n")
                stream.flush()
    if database_fingerprint(store)[0] != fingerprint:
        raise ValueError("Database changed during benchmark; results invalid")
    summary = summarize(traces)
    write_json(output / f"{split}_summary.json", summary)
    return summary


def run(repo, mode="all", run_dir=None):
    validate(repo)
    load_dotenv(repo / "starter/.env")
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL missing")
    if mode == "test":
        if run_dir is None:
            raise ValueError("--split test requires --run-dir with a frozen dev selection")
        output = run_dir.resolve()
        if output.parent != (repo / "results/benchmark").resolve():
            raise ValueError("run-dir must be directly inside results/benchmark")
        selection = json.loads((output / "selection.json").read_text(encoding="utf-8"))
        if (output / "test_traces.jsonl").exists():
            raise ValueError("Test already started in this run; keep existing evidence")
    else:
        output = repo / "results/benchmark" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        output.mkdir(parents=True, exist_ok=False)
    config = {"benchmark_freeze": sha(repo / "benchmark/freeze.json"),
              "chunk_summary": sha(repo / "data/chunks/summary.json"),
              "code": {name: sha(repo / f"starter/src/{name}.py") for name in
                       ("benchmark_runner", "evaluation", "embeddings", "store")}}
    embedder = MyEmbedder(cache_folder=repo / ".cache/models", local_files_only=True)
    store = PgVectorStore(url, embedder.dimensions, embedding_signature=embedder.signature)
    fingerprint, records = database_fingerprint(store)
    check_chunks(repo, records)
    config.update(embedding_signature=embedder.signature, database_fingerprint=fingerprint)
    if mode == "test":
        if config != selection["locked_config"] or sha(output / "dev_summary.json") != selection["dev_summary_sha256"]:
            raise ValueError("Configuration or dev results changed after selection")
    # One generic warm-up per strategy; excluded from all metrics and selection timing.
    warm = embedder.embed_query("Tìm nội dung liên quan đến lập trình Python.")
    for strategy in ("A", "B", "C"):
        store.search(strategy, warm)
    if mode != "test":
        write_json(output / "run_config.json", {**config, "model": embedder.config,
            "timing": "perf_counter; search includes DB connection and result transfer, excludes query embedding; generic warm-up; rotating A/B/C order; OS/database cache not reset",
            "metric": "full recorded quote required in ONE correctly sourced chunk; whitespace normalized; no automatic semantic equivalence",
            "ai_authored_gold_human_review_pending": True})
        dev = run_split(repo, output, "dev", embedder, store, fingerprint)
        selection = {"selected_at": datetime.now(timezone.utc).isoformat(),
            "selected_strategy": select_strategy(dev["metrics"]),
            "criteria": "dev Hit@3 descending, dev Hit@1 descending, total dev search time ascending, A/B/C order",
            "dev_summary_sha256": sha(output / "dev_summary.json"), "locked_config": config,
            "test_results_seen_for_selection": False}
        write_json(output / "selection.json", selection)  # Must exist BEFORE test is read/run.
        print(f"Dev complete; frozen selection: {selection['selected_strategy']}", flush=True)
    if mode in {"all", "test"}:
        run_split(repo, output, "test", embedder, store, fingerprint)
    rows = []
    for split in ("dev", "test"):
        path = output / f"{split}_summary.json"
        if path.exists():
            rows.extend(json.loads(path.read_text(encoding="utf-8"))["metrics"])
    with (output / "metrics.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(f"{row['split']} {row['strategy']}: Hit@1 {row['hit1_n']}/{row['n']}, Hit@3 {row['hit3_n']}/{row['n']}")
    print(f"Saved: {output}")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("dev", "test", "all"), default="dev")
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args()
    try:
        run(Path(__file__).resolve().parents[2], args.split, args.run_dir)
    except Exception as exc:
        parser.exit(1, f"Benchmark failed ({type(exc).__name__}). No fallback or invented metrics.\n")


if __name__ == "__main__":
    main()
