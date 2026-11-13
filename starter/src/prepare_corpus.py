"""Prepare local PEP RST source units only; no model, database or benchmark."""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .ingestion import normalize_text

SNAPSHOT = "155e5bee7d985ef30555b496eb994d24a591f70b"
EXCLUDED = {"references", "references and footnotes", "footnotes",
            "bibliography", "copyright", "license", "licence"}


def read_rst(path: Path) -> dict:
    """Preserve RST structure and map retained normalized lines to raw text.

    Raw offsets index UTF-8-decoded text BEFORE newline conversion, not bytes.
    Line mappings cover whole original lines, including their newline.
    """
    data = path.read_bytes()
    raw = data.decode("utf-8")
    lines = raw.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    header = {}
    key = None
    body = 0
    for i, line in enumerate(lines):
        if not line.strip():
            body = i + 1
            break
        match = re.match(r"^([A-Za-z][A-Za-z-]*):\s*(.*?)\s*$", line)
        if match:
            key = match[1]
            header[key] = match[2]
        elif line[0].isspace() and key:
            header[key] += " " + line.strip()
        else:
            raise ValueError(f"{path.name}: invalid header line {i + 1}")
    if not header.get("PEP", "").isdigit() or not header.get("Title"):
        raise ValueError(f"{path.name}: missing PEP or Title")

    headings = []
    for i in range(body, len(lines) - 1):
        title, underline = lines[i].rstrip(), lines[i + 1].strip()
        if (title and not title[0].isspace() and len(underline) >= 3
                and len(set(underline)) == 1 and underline[0] in "=-~^\"+*#"
                and len(underline) >= len(title)):
            headings.append((i, title, underline[0]))
    # Rank heading styles by first appearance, as in these PEP RST documents.
    styles = list(dict.fromkeys(h[2] for h in headings))
    excluded = []
    for n, (start, title, style) in enumerate(headings):
        if title.casefold() not in EXCLUDED:
            continue
        end = next((h[0] for h in headings[n + 1:]
                    if styles.index(h[2]) <= styles.index(style)), len(lines))
        excluded.append({"title": title, "raw_start": offsets[start],
                         "raw_end": offsets[end], "line_start": start + 1,
                         "line_end": end})
    license_parts = [raw[s["raw_start"]:s["raw_end"]] for s in excluded
                     if s["title"].casefold() in {"copyright", "license", "licence"}]
    if not license_parts:
        raise ValueError(f"{path.name}: no explicit license section")

    output, mapping = [], []
    position = 0
    for i in range(body, len(lines)):
        if any(s["line_start"] <= i + 1 <= s["line_end"] for s in excluded):
            continue
        text = normalize_text(lines[i])
        if not text and (not output or output[-1] == ""):
            continue
        # Every retained line has a separator except the first.
        if output:
            position += 1
        mapping.append({"start": position, "end": position + len(text),
                        "raw_start": offsets[i], "raw_end": offsets[i + 1],
                        "line": i + 1})
        output.append(text)
        position += len(text)
    while output and output[-1] == "":
        output.pop()
        mapping.pop()
    text = "\n".join(output)
    if not text:
        raise ValueError(f"{path.name}: empty retained content")
    return {"header": header, "text": text, "line_map": mapping,
            "excluded_sections": excluded,
            "license_or_permission": "\n\n".join(license_parts).strip(),
            "raw_char_count": len(raw), "raw_sha256": hashlib.sha256(data).hexdigest()}


def unit_ranges(text: str, minimum: int = 1500) -> list[tuple[int, int]]:
    """Partition without gaps/overlap at paragraph ends; merge short tail.

    Long paragraphs remain intact. A document below minimum is rejected, never
    padded or joined to an unrelated document.
    """
    if minimum < 1500:
        raise ValueError("minimum must be >= 1500")
    if len(text) < minimum:
        raise ValueError("document has fewer than minimum retained characters")
    ranges = []
    start = 0
    for boundary in [m.end() for m in re.finditer(r"\n\n", text)] + [len(text)]:
        if boundary - start >= minimum:
            ranges.append((start, boundary))
            start = boundary
    if start < len(text):
        ranges[-1] = (ranges[-1][0], len(text))
    return ranges


def prepare(repo: Path, snapshot: str = SNAPSHOT) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", snapshot):
        raise ValueError("snapshot must be a full 40-character commit hash")
    files = sorted((repo / "data/raw").glob("*.rst"))
    if not files:
        raise ValueError("no RST files found in data/raw")
    documents, units, normalized = [], [], []
    for path in files:
        doc = read_rst(path)
        document_id = f"pep-{int(doc['header']['PEP']):04d}"
        if any(d["document_id"] == document_id for d in documents):
            raise ValueError(f"duplicate document ID: {document_id}")
        source = f"https://raw.githubusercontent.com/python/peps/{snapshot}/peps/{path.name}"
        boundaries = []
        for number, (start, end) in enumerate(unit_ranges(doc["text"]), 1):
            lines = [m for m in doc["line_map"] if m["end"] > start and m["start"] < end]
            boundary = {"unit_id": f"{document_id}:u{number:04d}", "unit_number": number,
                        "start": start, "end": end, "char_count": end - start,
                        "raw_line_start": lines[0]["line"], "raw_line_end": lines[-1]["line"]}
            boundaries.append(boundary)
            units.append({**boundary, "document_id": document_id, "source": source,
                          "page": number, "metadata": doc["header"],
                          "text": doc["text"][start:end]})
        documents.append({"source_id": document_id, "document_id": document_id,
                          "title": doc["header"]["Title"], "source": source,
                          "source_path_or_url": path.relative_to(repo).as_posix(),
                          "snapshot": snapshot, "snapshot_provenance": "user supplied; not remotely verified",
                          "accessed_at": None,
                          "accessed_at_note": "Original download date not recorded; processed_at is local read time.",
                          "header": doc["header"], "license_or_permission": doc["license_or_permission"],
                          "raw_sha256": doc["raw_sha256"], "raw_char_count": doc["raw_char_count"],
                          "char_count": len(doc["text"]), "unit_count": len(boundaries),
                          "excluded_sections": doc["excluded_sections"], "units": boundaries,
                          "normalized_path": f"data/processed/{document_id}.json"})
        normalized.append((document_id, {"document_id": document_id, "source": source,
                                       "text": doc["text"], "line_map": doc["line_map"]}))
    manifest = {"schema_version": 1, "processed_at": datetime.now(timezone.utc).isoformat(),
                "offset_convention": "0-based Unicode character offsets, end exclusive; start/end refer to processed document text; raw_* offsets refer to original UTF-8 decoded file including original newlines. line_map maps whole lines, not individual characters.",
                "normalization": "NFC, LF, tabs expanded to 8 columns; trim trailing whitespace, collapse unindented horizontal whitespace and repeated blank lines; retain RST markup, headings, paragraphs and code indentation.",
                "unit_rule": "Sequential paragraph-end boundaries >=1500 characters including retained RST markup/whitespace; merge short tail into previous unit, no overlap or duplication; header and listed reference/license sections excluded.",
                "document_count": len(documents), "unit_count": len(units),
                "char_count": sum(d["char_count"] for d in documents), "documents": documents}
    # Parse and validate every input before writing any output.
    target = repo / "data/processed"
    target.mkdir(parents=True, exist_ok=True)
    for document_id, content in normalized:
        (target / f"{document_id}.json").write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (target / "units.jsonl").write_text("".join(json.dumps(u, ensure_ascii=False) + "\n" for u in units), encoding="utf-8")
    (repo / "data/manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", default=SNAPSHOT)
    args = parser.parse_args()
    try:
        manifest = prepare(Path(__file__).resolve().parents[2], args.snapshot)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.exit(1, f"Corpus preparation failed: {exc}\n")
    for doc in manifest["documents"]:
        print(f"{doc['document_id']}: {doc['char_count']} chars, {doc['unit_count']} units")
    print(f"Total: {manifest['unit_count']} units; >=30: {manifest['unit_count'] >= 30}")


if __name__ == "__main__":
    main()
