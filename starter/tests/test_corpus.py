"""Boundary tests and read-only checks against the generated real corpus."""
import json
from pathlib import Path
import unittest

from src.ingestion import normalize_text
from src.prepare_corpus import read_rst, unit_ranges

ROOT = Path(__file__).resolve().parents[2]


class CorpusTests(unittest.TestCase):
    def test_unicode_structure_and_code(self):
        self.assertEqual(normalize_text("e\u0301  text  \r\n\r\n\r\nHeading\r\n=======\r\n\r\n    x = 'a  b'  \r\n"),
                         "é text\n\nHeading\n=======\n\n    x = 'a  b'")

    def test_tail_and_long_paragraph(self):
        text = "a" * 1500 + "\n\n" + "b" * 1499
        self.assertEqual(unit_ranges(text), [(0, len(text))])
        self.assertEqual(unit_ranges("a" * 4000), [(0, 4000)])
        with self.assertRaises(ValueError):
            unit_ranges("a" * 1499)

    def test_real_corpus_and_saved_outputs(self):
        manifest = json.loads((ROOT / "data/manifest.json").read_text(encoding="utf-8"))
        units = [json.loads(line) for line in (ROOT / "data/processed/units.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(manifest["document_count"], 6)
        self.assertEqual(len(units), manifest["unit_count"])
        self.assertGreaterEqual(len(units), 30)
        self.assertEqual(len({u["unit_id"] for u in units}), len(units))
        for entry in manifest["documents"]:
            path = ROOT / entry["source_path_or_url"]
            doc = read_rst(path)
            saved = json.loads((ROOT / entry["normalized_path"]).read_text(encoding="utf-8"))
            self.assertEqual(saved["text"], doc["text"])
            self.assertEqual(entry["raw_sha256"], doc["raw_sha256"])
            self.assertEqual(entry["header"], doc["header"])
            own = [u for u in units if u["document_id"] == entry["document_id"]]
            self.assertEqual(len(own), entry["unit_count"])
            self.assertEqual("".join(u["text"] for u in own), doc["text"])
            cursor = 0
            for number, unit in enumerate(own, 1):
                self.assertEqual(unit["start"], cursor)
                self.assertEqual(unit["page"], number)
                self.assertGreaterEqual(unit["char_count"], 1500)
                self.assertEqual(unit["text"], doc["text"][unit["start"]:unit["end"]])
                self.assertEqual(len(unit["text"]), unit["char_count"])
                cursor = unit["end"]
            self.assertEqual(cursor, len(doc["text"]))
            raw = path.read_bytes().decode("utf-8")
            for line in saved["line_map"]:
                original = raw[line["raw_start"]:line["raw_end"]]
                self.assertEqual(doc["text"][line["start"]:line["end"]], normalize_text(original))
                for section in entry["excluded_sections"]:
                    self.assertFalse(line["raw_start"] < section["raw_end"] and line["raw_end"] > section["raw_start"])
            self.assertTrue(entry["license_or_permission"])
            if entry["document_id"] == "pep-0257":
                self.assertIn("Acknowledgements\n", doc["text"])
                self.assertNotIn("References and Footnotes\n", doc["text"])
                self.assertNotIn("Copyright\n", doc["text"])


if __name__ == "__main__":
    unittest.main()
