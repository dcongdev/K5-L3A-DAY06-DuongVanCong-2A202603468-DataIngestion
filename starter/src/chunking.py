"""Deterministic chunking inside source units; offsets are Unicode characters."""
import hashlib
import re
from .models import Chunk, DocumentPage


def _chunk(page: DocumentPage, start: int, end: int, method: str) -> Chunk:
    base = page.metadata.get("unit_start", 0)
    text = page.text[start:end]
    identity = f"{page.document_id}:{page.page}:{method}:{start}:{end}:{text}"
    return Chunk(
        chunk_id=hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        document_id=page.document_id, source=page.source, page=page.page,
        text=text, metadata={**page.metadata, "unit_id": page.metadata.get(
            "unit_id", f"{page.document_id}:u{page.page:04d}"),
            "unit_offset_start": start, "unit_offset_end": end,
            "start": base + start, "end": base + end, "char_count": end - start,
            "chunking": method})


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    """Character windows; stop at first window reaching the end (no extra tail)."""
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("Require size > 0 and 0 <= overlap < size")
    chunks = []
    for start in range(0, len(page.text), size - overlap):
        end = min(start + size, len(page.text))
        chunks.append(_chunk(page, start, end, f"fixed:{size}:{overlap}"))
        if end == len(page.text):
            break
    return chunks


def _heading(block: str) -> bool:
    lines = block.rstrip().splitlines()
    return (len(lines) == 2 and bool(lines[0]) and not lines[0][0].isspace()
            and len(lines[1]) >= len(lines[0]) and len(lines[1]) >= 3
            and len(set(lines[1])) == 1 and lines[1][0] in "=-~^\"+*#")


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    """Greedy paragraph groups, flush at headings; no overlap or synthetic text.

    A heading is paired with its following paragraph before size splitting.
    Oversized blocks split at whitespace, falling back to character boundaries.
    Hard limits can still split code or separate a heading from long context;
    this must be inspected in the later coherence audit.
    """
    if max_size <= 0:
        raise ValueError("max_size must be > 0")
    if not page.text:
        return []
    ends = [m.end() for m in re.finditer(r"\n\n", page.text)]
    if not ends or ends[-1] != len(page.text):
        ends.append(len(page.text))
    blocks = []
    start = 0
    for end in ends:
        blocks.append((start, end))
        start = end
    paired = []
    i = 0
    while i < len(blocks):
        start, end = blocks[i]
        heading = _heading(page.text[start:end])
        if heading and i + 1 < len(blocks) and not _heading(page.text[slice(*blocks[i + 1])]):
            end = blocks[i + 1][1]
            i += 1
        paired.append((start, end, heading))
        i += 1

    ranges = []
    current = None
    for start, end, heading in paired:
        if current is not None and (heading or end - current[0] > max_size):
            ranges.append(current)
            current = None
        while end - start > max_size:
            if current is not None:
                ranges.append(current)
                current = None
            limit = start + max_size
            # Prefer a nearby word/line boundary, never lose delimiters.
            choices = [m.end() + start for m in re.finditer(r"\s+", page.text[start:limit])
                       if m.end() >= max_size // 2]
            cut = choices[-1] if choices else limit
            ranges.append((start, cut))
            start = cut
        if start < end:
            current = (current[0], end) if current else (start, end)
    if current is not None:
        ranges.append(current)
    return [_chunk(page, start, end, f"paragraph:{max_size}") for start, end in ranges]
