"""Build A/B chunks from frozen source units; C reuses B without copying."""
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

from .chunking import by_paragraph, fixed_size
from .models import DocumentPage
from .validate_benchmark import validate

CONFIG = {
    "A": {"method": "fixed", "size": 500, "overlap": 50, "filter": False},
    "B": {"method": "paragraph", "max_size": 500, "overlap": 0, "filter": False},
    "C": {"chunks_from": "B", "filter": "question.filter, only if nonempty"},
}


def prepare(repo: Path) -> dict:
    validate(repo)  # Verify frozen inputs, never read gold to construct chunks.
    path = repo / "data/processed/units.jsonl"
    units = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    pages = [DocumentPage(u["document_id"], u["source"], u["page"], u["text"],
                          {**u["metadata"], "unit_id": u["unit_id"],
                           "unit_start": u["start"], "unit_end": u["end"]}) for u in units]
    output = repo / "data/chunks"
    output.mkdir(parents=True, exist_ok=True)
    summary = {"schema_version": 1, "config": CONFIG,
               "units_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
               "offset_convention": "0-based Unicode characters, end exclusive; start/end in normalized document; unit_offset_* in source unit.",
               "source_unit_count": len(pages), "strategies": {}}
    for strategy in ("A", "B"):
        started = perf_counter()
        chunks = [c for page in pages for c in (
            fixed_size(page, CONFIG["A"]["size"], CONFIG["A"]["overlap"]) if strategy == "A"
            else by_paragraph(page, CONFIG["B"]["max_size"]))]
        seconds = perf_counter() - started
        lengths = sorted(len(c.text) for c in chunks)
        payload = "".join(json.dumps(asdict(c), ensure_ascii=False) + "\n" for c in chunks)
        destination = output / f"{strategy}.jsonl"
        destination.write_text(payload, encoding="utf-8")
        summary["strategies"][strategy] = {
            "path": destination.relative_to(repo).as_posix(), "chunk_count": len(chunks),
            "min_chars": min(lengths), "max_chars": max(lengths),
            "mean_chars": sum(lengths) / len(lengths),
            "median_chars": (lengths[(len(lengths) - 1) // 2] + lengths[len(lengths) // 2]) / 2,
            "total_chars": sum(lengths), "chunking_seconds": seconds,
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()}
    summary["strategies"]["C"] = {"chunks_from": "B", "path": "data/chunks/B.jsonl",
                                   "chunk_count": summary["strategies"]["B"]["chunk_count"]}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    try:
        summary = prepare(Path(__file__).resolve().parents[2])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"Chunk preparation failed: {exc}") from exc
    for name in ("A", "B"):
        s = summary["strategies"][name]
        print(f"{name}: {s['chunk_count']} chunks, {s['min_chars']}..{s['max_chars']} chars, mean={s['mean_chars']:.1f}")
    print("C: reuses B chunks; filtering will be applied during retrieval. No embeddings or database writes.")


if __name__ == "__main__":
    main()
