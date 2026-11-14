"""Search a custom query only; not a benchmark/evaluation runner."""
import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from .embeddings import MyEmbedder
from .store import PgVectorStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", required=True)
    parser.add_argument("--strategy", choices=("A", "B", "C"), default="B")
    parser.add_argument("--type", choices=("Process", "Informational", "Standards Track"))
    args = parser.parse_args()
    if args.type and args.strategy != "C":
        parser.error("--type requires --strategy C")
    repo = Path(__file__).resolve().parents[2]
    load_dotenv(repo / "starter/.env")
    os.environ.setdefault("HF_HOME", str(repo / ".cache/huggingface"))
    try:
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise ValueError("DATABASE_URL missing")
        embedder = MyEmbedder(cache_folder=repo / ".cache/models")
        store = PgVectorStore(url, embedder.dimensions, embedding_signature=embedder.signature)
        hits = store.search(args.strategy, embedder.embed_query(args.question),
                            filters={"Type": args.type} if args.type else {})
    except Exception as exc:
        parser.exit(1, f"Search failed ({type(exc).__name__}); check model and database setup.\n")
    print(json.dumps({"strategy": args.strategy, "question": args.question,
                      "filter": {"Type": args.type} if args.type else {}, "hits": hits}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
