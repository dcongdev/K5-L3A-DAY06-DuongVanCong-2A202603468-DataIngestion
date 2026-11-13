import json
from pathlib import Path
import unittest

from src.chunking import by_paragraph, fixed_size
from src.models import DocumentPage

ROOT = Path(__file__).resolve().parents[2]


class ChunkingTests(unittest.TestCase):
    def page(self, text):
        return DocumentPage("doc", "source", 2, text,
                            {"Type": "Process", "unit_start": 100, "unit_id": "doc:u0002"})

    def test_windows_no_redundant_tail_and_invalid_settings(self):
        page = self.page("a" * 950)
        chunks = fixed_size(page, 500, 50)
        self.assertEqual([(c.metadata["unit_offset_start"], c.metadata["unit_offset_end"]) for c in chunks], [(0, 500), (450, 950)])
        for size, overlap in ((0, 0), (50, 50), (50, -1)):
            with self.assertRaises(ValueError):
                fixed_size(page, size, overlap)
        self.assertEqual(fixed_size(self.page(""), 500, 50), [])

    def test_heading_is_kept_with_following_paragraph(self):
        text = "Intro paragraph.\n\nHeading\n=======\n\nNew paragraph."
        chunks = by_paragraph(self.page(text), 100)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[1].text.startswith("Heading\n=======\n\nNew"))
        self.assertEqual("".join(c.text for c in chunks), text)

    def test_oversize_paragraph_and_unicode(self):
        for text in ("đ" * 1201, "    code = 'a  b'\n" * 100, "Title\n=====\n\n" + "word " * 300):
            chunks = by_paragraph(self.page(text), 500)
            self.assertEqual("".join(c.text for c in chunks), text)
            self.assertTrue(all(0 < len(c.text) <= 500 for c in chunks))
        with self.assertRaises(ValueError):
            by_paragraph(self.page("text"), 0)

    def test_real_outputs_coverage_offsets_metadata_and_stability(self):
        units = [json.loads(s) for s in (ROOT / "data/processed/units.jsonl").read_text(encoding="utf-8").splitlines()]
        for strategy in ("A", "B"):
            saved = [json.loads(s) for s in (ROOT / f"data/chunks/{strategy}.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len({c["chunk_id"] for c in saved}), len(saved))
            for unit in units:
                own = [c for c in saved if c["metadata"]["unit_id"] == unit["unit_id"]]
                page = DocumentPage(unit["document_id"], unit["source"], unit["page"], unit["text"],
                                    {**unit["metadata"], "unit_id": unit["unit_id"], "unit_start": unit["start"], "unit_end": unit["end"]})
                rebuilt = fixed_size(page, 500, 50) if strategy == "A" else by_paragraph(page, 500)
                self.assertEqual([c["chunk_id"] for c in own], [c.chunk_id for c in rebuilt])
                covered = [False] * len(unit["text"])
                for c in own:
                    m = c["metadata"]
                    start, end = m["unit_offset_start"], m["unit_offset_end"]
                    self.assertEqual(c["text"], unit["text"][start:end])
                    self.assertEqual((m["start"], m["end"]), (unit["start"] + start, unit["start"] + end))
                    self.assertEqual((c["source"], c["document_id"], c["page"]), (unit["source"], unit["document_id"], unit["page"]))
                    for key, value in unit["metadata"].items():
                        self.assertEqual(m[key], value)
                    self.assertTrue(0 < end - start <= 500)
                    covered[start:end] = [True] * (end - start)
                self.assertTrue(all(covered))
                if strategy == "B":
                    self.assertEqual("".join(c["text"] for c in own), unit["text"])
        summary = json.loads((ROOT / "data/chunks/summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["strategies"]["C"]["path"], summary["strategies"]["B"]["path"])


if __name__ == "__main__":
    unittest.main()
