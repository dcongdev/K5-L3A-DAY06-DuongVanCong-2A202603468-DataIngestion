"""Persistent pgvector store with exact cosine search and safe metadata filters."""
import math
import re
from typing import Any
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from .models import Chunk


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int, *, embedding_signature: str,
                 schema: str = "day6_ingestion") -> None:
        if not isinstance(dimensions, int) or not 1 <= dimensions <= 16000:
            raise ValueError("Invalid vector dimensions")
        if not embedding_signature or not re.fullmatch(r"[a-z][a-z0-9_]*", schema):
            raise ValueError("Embedding signature and valid schema name required")
        self.database_url = database_url
        self.dimensions = dimensions
        self.embedding_signature = embedding_signature
        self.schema = schema
        self.chunks_table = sql.Identifier(schema, "chunks")
        self.indexes_table = sql.Identifier(schema, "indexes")

    def connect(self):
        return psycopg.connect(self.database_url, connect_timeout=5)

    @staticmethod
    def _strategy(strategy: str) -> str:
        if strategy not in {"A", "B", "C"}:
            raise ValueError("Strategy must be A, B or C")
        return "B" if strategy == "C" else strategy

    def _vector(self, values: list[float]) -> str:
        if len(values) != self.dimensions:
            raise ValueError("Vector dimensions mismatch")
        values = [float(v) for v in values]
        if not all(math.isfinite(v) for v in values) or not any(values):
            raise ValueError("Cosine vectors must be finite and nonzero")
        return "[" + ",".join(repr(v) for v in values) + "]"

    def create_schema(self) -> None:
        with self.connect() as conn:
            if not conn.execute("SELECT 1 FROM pg_extension WHERE extname='vector'").fetchone():
                raise ValueError("pgvector extension missing; run database setup")
            conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(self.schema)))
            conn.execute(sql.SQL("""CREATE TABLE IF NOT EXISTS {} (
                strategy text PRIMARY KEY, signature text NOT NULL, dimensions integer NOT NULL,
                updated_at timestamptz NOT NULL DEFAULT now())""").format(self.indexes_table))
            conn.execute(sql.SQL("""CREATE TABLE IF NOT EXISTS {} (
                strategy text NOT NULL REFERENCES {}(strategy), chunk_id text NOT NULL,
                document_id text NOT NULL, source text NOT NULL, page integer NOT NULL,
                text text NOT NULL, metadata jsonb NOT NULL, embedding vector({}) NOT NULL,
                PRIMARY KEY(strategy, chunk_id))""").format(
                    self.chunks_table, self.indexes_table, sql.Literal(self.dimensions)))
            actual = conn.execute("""SELECT format_type(a.atttypid, a.atttypmod)
                FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname=%s AND c.relname='chunks' AND a.attname='embedding'""", (self.schema,)).fetchone()
            if not actual or actual[0] != f"vector({self.dimensions})":
                raise ValueError("Existing table dimensions differ; use a new schema")

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Atomically sync a COMPLETE strategy snapshot and remove stale chunks.

        Always pass the full current corpus for the strategy, never partial
        document batches. Empty snapshots rejected. C shares B, not separately stored.
        """
        if strategy == "C":
            raise ValueError("C reuses B; ingest B only")
        strategy = self._strategy(strategy)
        if not chunks or len(chunks) != len(vectors):
            raise ValueError("Require nonempty chunks and matching vector count")
        if len({c.chunk_id for c in chunks}) != len(chunks):
            raise ValueError("Duplicate chunk IDs")
        rows = [(strategy, c.chunk_id, c.document_id, c.source, c.page, c.text,
                 Jsonb(c.metadata), self._vector(v)) for c, v in zip(chunks, vectors)]
        with self.connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (self.schema + ":" + strategy,))
            conn.execute(sql.SQL("""INSERT INTO {}(strategy,signature,dimensions) VALUES (%s,%s,%s)
                ON CONFLICT(strategy) DO UPDATE SET signature=excluded.signature,
                dimensions=excluded.dimensions, updated_at=now()""").format(self.indexes_table),
                         (strategy, self.embedding_signature, self.dimensions))
            with conn.cursor() as cur:
                cur.executemany(sql.SQL("""INSERT INTO {}
                    (strategy,chunk_id,document_id,source,page,text,metadata,embedding)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s::vector)
                    ON CONFLICT(strategy,chunk_id) DO UPDATE SET
                    document_id=excluded.document_id,source=excluded.source,page=excluded.page,
                    text=excluded.text,metadata=excluded.metadata,embedding=excluded.embedding""").format(self.chunks_table), rows)
            conn.execute(sql.SQL("DELETE FROM {} WHERE strategy=%s AND NOT (chunk_id=ANY(%s))").format(self.chunks_table),
                         (strategy, [c.chunk_id for c in chunks]))

    def count(self, strategy: str) -> int:
        with self.connect() as conn:
            return conn.execute(sql.SQL("SELECT count(*) FROM {} WHERE strategy=%s").format(self.chunks_table),
                                (self._strategy(strategy),)).fetchone()[0]

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        physical = self._strategy(strategy)
        if not isinstance(top_k, int) or not 1 <= top_k <= 100:
            raise ValueError("top_k must be 1..100")
        filters = filters or {}
        if set(filters) - {"Type"} or any(not isinstance(v, str) for v in filters.values()):
            raise ValueError("Only string Type metadata filters allowed")
        if strategy in {"A", "B"} and filters:
            raise ValueError("A/B do not apply filters; use C")
        vector = self._vector(query_vector)
        with self.connect() as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            registry = conn.execute(sql.SQL("SELECT signature, dimensions FROM {} WHERE strategy=%s").format(self.indexes_table),
                                    (physical,)).fetchone()
            if registry != (self.embedding_signature, self.dimensions):
                raise ValueError("Missing index or model signature mismatch; ingest first")
            rows = conn.execute(sql.SQL("""SELECT chunk_id,document_id,source,page,text,metadata,
                1 - (embedding <=> %s::vector) AS score FROM {}
                WHERE strategy=%s AND metadata @> %s
                ORDER BY embedding <=> %s::vector, chunk_id LIMIT %s""").format(self.chunks_table),
                                (vector, physical, Jsonb(filters), vector, top_k)).fetchall()
        return [{"chunk_id": r[0], "document_id": r[1], "source": r[2], "page": r[3],
                 "text": r[4], "metadata": {**r[5], "document_id": r[1], "source": r[2], "page": r[3]},
                 "score": float(r[6])} for r in rows]
