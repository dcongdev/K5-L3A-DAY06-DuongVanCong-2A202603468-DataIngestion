"""Check saved audit provenance and totals; does not assign or infer labels."""
import hashlib
import json
from pathlib import Path


def validate(repo):
    folder = repo / "results/audit/20261114T022140610429Z"
    load = lambda name: json.loads((folder / name).read_text(encoding="utf-8"))
    rows = lambda name: list(map(json.loads, (folder / name).read_text(encoding="utf-8").splitlines()))
    protocol = load("protocol.json")
    for name, digest in protocol["input_sha256"].items():
        if hashlib.sha256((repo / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Audit input changed: {name}")
    coherence, grounding, metadata = (rows(n) for n in ("coherence.jsonl", "grounding.jsonl", "metadata.jsonl"))
    if (len(coherence), len(grounding), len(metadata)) != (30, 15, 45):
        raise ValueError("Unexpected audit sample count")
    units = {u["unit_id"]: u for u in map(json.loads, (repo / "data/processed/units.jsonl").read_text(encoding="utf-8").splitlines())}
    chunks = {}
    for strategy in ("A", "B"):
        chunks[strategy] = {c["chunk_id"]: c for c in map(json.loads, (repo / f"data/chunks/{strategy}.jsonl").read_text(encoding="utf-8").splitlines())}
    for row in metadata:
        chunk = chunks["B" if row["strategy"] == "C" else row["strategy"]][row["chunk_id"]]
        if any(row[k] != chunk[k] for k in ("document_id", "source", "page")):
            raise ValueError("Metadata identity mismatch")
        if any(row[k] != chunk["metadata"][k] for k in ("Type", "start", "end")):
            raise ValueError("Metadata field mismatch")
        if row["enough_and_correct"] != (not row["errors"]):
            raise ValueError("Metadata label/errors inconsistent")
    for row in coherence:
        unit = units[row["unit_id"]]
        if row["text"] != unit["text"][row["start"]-unit["start"]:row["end"]-unit["start"]]:
            raise ValueError("Coherence text/offset mismatch")
        if not row["start"] <= row["source_position"] < row["end"]:
            raise ValueError("Chunk does not cover sample position")
    for row in coherence + grounding:
        if row["score"] not in (0, 1, 2) or not row["reason"]:
            raise ValueError("Invalid label or missing explanation")
    summary = load("summary.json")["strategies"]
    for strategy in ("A", "B", "C"):
        c = [r for r in coherence if r["strategy"] == strategy]
        g = [r for r in grounding if r["strategy"] == strategy]
        m = [r for r in metadata if r["strategy"] == strategy]
        if (len(c), len(g), len(m)) != (10, 5, 15):
            raise ValueError("Incomplete strategy audit")
        if len({r["sample_id"] for r in c}) != 10 or len({r["question_id"] for r in g}) != 5:
            raise ValueError("Duplicate audit samples")
        expected_positions = {(p["unit_id"], p["position"]) for p in protocol["sample_positions"]}
        if {(r["unit_id"], r["source_position"]) for r in c} != expected_positions:
            raise ValueError("Strategies do not share source positions")
        saved = summary[strategy]
        if sum(r["score"] for r in c)/10 != saved["coherence_mean"] or sum(r["score"] for r in g)/5 != saved["grounding_mean"]:
            raise ValueError("Label averages mismatch")
        if {str(k): sum(r["score"] == k for r in g) for k in (0,1,2)} != saved["grounding_distribution"]:
            raise ValueError("Grounding distribution mismatch")
        if sum(r["enough_and_correct"] for r in m) != saved["metadata_correct"]:
            raise ValueError("Metadata totals mismatch")
        filtered = {r["question_id"] for r in m if r["requested_filter"]}
        correct = sum(all(r["requested_scope_matches"] for r in m if r["question_id"] == q) for q in filtered)
        if (correct, len(filtered)) != (saved["requested_scope_compliant_questions"], saved["requested_scope_questions"]):
            raise ValueError("Scope compliance totals mismatch")
        for q in {r["question_id"] for r in g}:
            if {r["rank"] for r in m if r["question_id"] == q} != {1,2,3}:
                raise ValueError("Missing top-3 metadata record")
    print("Audit artifacts OK: 30 coherence labels, 15 grounding labels, 45 metadata records; input hashes and totals match.")
    print("Label interpretation still requires owner review; this check does not certify independent human judgment.")


if __name__ == "__main__":
    validate(Path(__file__).resolve().parents[2])
