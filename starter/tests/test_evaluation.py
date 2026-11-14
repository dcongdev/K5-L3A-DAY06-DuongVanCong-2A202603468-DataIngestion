import unittest

from src.evaluation import evaluate_query, summarize
from src.benchmark_runner import select_strategy


class EvaluationTests(unittest.TestCase):
    def question(self):
        return {"id": "fixture", "split": "dev", "gold_source_id": "doc", "gold_page": 1,
                "evidence_quote": "Allowed only if condition holds."}

    def hit(self, text, doc="doc", page=1):
        return {"chunk_id": text, "document_id": doc, "page": page, "text": text}

    def test_location_alone_or_partial_evidence_is_not_hit(self):
        q = self.question()
        hits = [self.hit("Allowed only"), self.hit(q["evidence_quote"], page=2),
                self.hit(q["evidence_quote"], doc="wrong")]
        self.assertFalse(evaluate_query(q, hits)["hit3"])

    def test_rank_and_whitespace(self):
        q = self.question()
        result = evaluate_query(q, [self.hit("unrelated"), self.hit("Allowed\nonly if condition holds.")])
        self.assertFalse(result["hit1"])
        self.assertTrue(result["hit3"])

    def test_no_union_of_partial_chunks_and_no_fourth_rank(self):
        q = self.question()
        hits = [self.hit("Allowed only"), self.hit("if condition holds."), self.hit("other"), self.hit(q["evidence_quote"])]
        self.assertFalse(evaluate_query(q, hits)["hit3"])
        self.assertFalse(evaluate_query(q, [])["hit1"])

    def test_documented_alternative(self):
        q = self.question()
        q["gold_evidence"] = [{"source_id": "other", "page": 3, "evidence_quote": "Alternative evidence."}]
        self.assertTrue(evaluate_query(q, [self.hit("Alternative evidence.", "other", 3)])["hit1"])

    def test_denominators_and_duplicate_guard(self):
        traces = [{"strategy": "A", "split": "dev", "question_id": "x", "hit1": False,
                   "hit3": True, "retrieval_seconds": 0.1},
                  {"strategy": "A", "split": "dev", "question_id": "y", "hit1": False,
                   "hit3": False, "retrieval_seconds": 0.2}]
        row = summarize(traces)["metrics"][0]
        self.assertEqual((row["hit3_n"], row["n"], row["hit3"]), (1, 2, 0.5))
        with self.assertRaises(ValueError):
            summarize(traces + traces)

    def test_selection_ignores_test_and_uses_ordered_tiebreaks(self):
        rows = [{"strategy": name, "split": "dev", "hit3": 0.5, "hit1": 0.2,
                 "retrieval_seconds": 1.0} for name in ("A", "B", "C")]
        self.assertEqual(select_strategy(rows), "A")
        rows[1]["hit1"] = 0.3
        self.assertEqual(select_strategy(rows), "B")
        rows[2]["hit3"] = 0.6
        self.assertEqual(select_strategy(rows), "C")
        rows[2]["split"] = "test"
        with self.assertRaises(ValueError):
            select_strategy(rows)


if __name__ == "__main__":
    unittest.main()
