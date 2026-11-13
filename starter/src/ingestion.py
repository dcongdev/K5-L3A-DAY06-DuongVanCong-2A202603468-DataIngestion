"""Read and normalize source data. TODO: implement functions."""
from pathlib import Path
import re
import unicodedata
from .models import DocumentPage


def load_pdf(path: Path, document_id: str, source: str) -> list[DocumentPage]:
    """TODO: extract each physical page; keep its page number and source.

    Detect and record pages with no text. OCR, when needed, is a separate step.
    """
    raise NotImplementedError("TODO: load_pdf")


def normalize_text(text: str) -> str:
    """NFC, LF, no trailing spaces, one blank line; retain RST/code indentation.

    RST markup and hard line breaks are intentionally retained. Internal spacing
    on indented lines can be significant in code, lists and tables.
    """
    lines = []
    for line in unicodedata.normalize("NFC", text).splitlines():
        line = line.expandtabs(8).rstrip()
        if line and not line[0].isspace():
            line = re.sub(r"[^\S\n]+", " ", line)
        if line or (lines and lines[-1]):
            lines.append(line)
    return "\n".join(lines).strip("\n")
