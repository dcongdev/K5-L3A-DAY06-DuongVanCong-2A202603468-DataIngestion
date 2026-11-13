"""Validate frozen benchmark inputs; never performs retrieval or evaluation."""
import hashlib
import json
from pathlib import Path


def validate(repo: Path) -> dict:
    def require(condition: bool, message: str) -> None:
        if not condition:
            raise ValueError(message)

    folder = repo / "benchmark"
    lock = json.loads((folder / "freeze.json").read_text(encoding="utf-8"))
    for name, expected in lock["sha256"].items():
        require(hashlib.sha256((repo / name).read_bytes()).hexdigest() == expected,
                f"Frozen input changed: {name}. Review and version explicitly; do not silently re-freeze.")
    units = [json.loads(line) for line in (repo / "data/processed/units.jsonl").read_text(encoding="utf-8").splitlines()]
    index = {u["unit_id"]: u for u in units}
    require(len(index) == len(units), "Duplicate corpus unit IDs")
    questions = []
    for split in ("dev", "test"):
        batch = [json.loads(line) for line in (folder / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()]
        require(len(batch) >= (15 if split == "dev" else 5), f"Insufficient {split} questions")
        for q in batch:
            require(q["split"] == split, f"Wrong split: {q['id']}")
            require(all(q.get(k) for k in ("id", "question", "expected_answer", "gold_source_id", "gold_page", "evidence_quote", "gold_evidence")),
                    f"Missing required fields: {q['id']}")
            require(set(q["filter"]) <= {"Type"}, f"Unexpected filter field: {q['id']}")
            for field, value in q["filter"].items():
                require(value in q["question"] and bool(q.get("filter_origin")), f"Filter not stated in question: {q['id']}")
                require(len({u["metadata"].get(field) for u in units}) >= 2, "Filter has no distinct scopes")
            primary = False
            for gold in q["gold_evidence"]:
                require(gold["unit_id"] in index, f"Missing gold unit: {q['id']}")
                unit = index[gold["unit_id"]]
                require(unit["document_id"] == gold["source_id"] and unit["page"] == gold["page"], f"Gold location mismatch: {q['id']}")
                quote = gold["evidence_quote"]
                require(quote in unit["text"], f"Evidence absent from unit: {q['id']}")
                require(unit["start"] <= gold["start"] < gold["end"] <= unit["end"], f"Invalid evidence offsets: {q['id']}")
                require(unit["text"][gold["start"] - unit["start"]:gold["end"] - unit["start"]] == quote, f"Evidence offset mismatch: {q['id']}")
                require(all(unit["metadata"].get(k) == v for k, v in q["filter"].items()), f"Gold excluded by filter: {q['id']}")
                primary |= (gold["source_id"] == q["gold_source_id"] and gold["page"] == q["gold_page"] and quote == q["evidence_quote"])
            require(primary, f"Primary gold absent from alternatives: {q['id']}")
        questions.extend(batch)
    require(len({q["id"] for q in questions}) == len(questions), "Duplicate question IDs")
    require(len({q["question"] for q in questions}) == len(questions), "Duplicate question text")
    counts = {"dev": sum(q["split"] == "dev" for q in questions),
              "test": sum(q["split"] == "test" for q in questions),
              "filter_questions": sum(bool(q["filter"]) for q in questions),
              "test_filter_questions": sum(bool(q["filter"]) and q["split"] == "test" for q in questions)}
    require(counts["filter_questions"] >= 3 and counts["test_filter_questions"] >= 1, "Insufficient filter questions")
    require(counts == lock["counts"], "Frozen counts mismatch")
    return counts


def main() -> None:
    try:
        counts = validate(Path(__file__).resolve().parents[2])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"Benchmark validation failed: {exc}") from exc
    print("Benchmark inputs OK: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    print("Evidence locations and frozen hashes verified. No retrieval metrics or independent human audit produced.")


if __name__ == "__main__":
    main()
