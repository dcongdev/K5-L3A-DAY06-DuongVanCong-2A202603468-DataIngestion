"""TODO: evaluate retrieved evidence and preserve per-query traces."""
from typing import Any
import re
from collections import defaultdict


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    """TODO: check source/page and enough gold evidence; keep hit@1 and hit@3 trace.

    Accept any documented alternative gold evidence. Do not infer human grounding
    or chunk coherence labels from exact string match.
    """
    gold = question.get("gold_evidence") or [{"source_id": question["gold_source_id"],
        "page": question["gold_page"], "evidence_quote": question["evidence_quote"]}]
    def normalized(text):
        return re.sub(r"\s+", " ", text).strip()
    labels = []
    for rank, hit in enumerate(hits[:3], 1):
        locations = [g for g in gold if hit["document_id"] == g["source_id"] and hit["page"] == g["page"]]
        matched = [g for g in locations if normalized(g["evidence_quote"]) and
                   normalized(g["evidence_quote"]) in normalized(hit["text"])]
        labels.append({"rank": rank, "chunk_id": hit["chunk_id"], "hit": bool(matched),
            "reason": "full recorded evidence present" if matched else
                      "correct location but full evidence absent" if locations else "different gold location"})
    return {"question_id": question["id"], "split": question["split"],
            "hit1": bool(labels and labels[0]["hit"]), "hit3": any(l["hit"] for l in labels),
            "labels": labels, "method": "full recorded quote with whitespace normalization; equivalent evidence requires later documented review"}


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """TODO: aggregate Hit@1 and Evidence Hit@3 by strategy and dev/test split."""
    groups = defaultdict(list)
    for trace in traces:
        groups[(trace["strategy"], trace["split"])].append(trace)
    rows = []
    for (strategy, split), items in sorted(groups.items()):
        if len({t["question_id"] for t in items}) != len(items):
            raise ValueError("Duplicate query within strategy/split")
        n = len(items)
        h1, h3 = sum(t["hit1"] for t in items), sum(t["hit3"] for t in items)
        rows.append({"strategy": strategy, "split": split, "n": n, "hit1_n": h1,
                     "hit3_n": h3, "hit1": h1 / n, "hit3": h3 / n,
                     "retrieval_seconds": sum(t["retrieval_seconds"] for t in items)})
    return {"metrics": rows, "manual_audits_completed": False}
