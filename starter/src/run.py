"""Benchmark entry point for an already prepared and ingested corpus.

Run source preparation, chunk preparation and ingest_vectors explicitly first.
The default runs dev only. See BENCHMARK_RUN.md for freezing and test commands.
"""
from .benchmark_runner import main


if __name__ == "__main__":
    main()
