"""Database contract checks using real chunk embeddings in a disposable schema."""
from dataclasses import replace
from uuid import uuid4

import psycopg
from psycopg import sql

from .store import PgVectorStore


def verify_store(database_url, dimensions, signature, chunks, vectors) -> dict:
    schema = "day6_check_" + uuid4().hex
    store = PgVectorStore(database_url, dimensions, embedding_signature=signature, schema=schema)
    passed = []

    def check(condition, name):
        if not condition:
            raise ValueError(f"Store contract check failed: {name}")
        passed.append(name)

    try:
        store.create_schema()
        store.upsert("B", chunks[:2], vectors[:2])
        store.upsert("B", chunks[:2], vectors[:2])
        check(store.count("B") == 2, "idempotent upsert")
        store.upsert("B", chunks[:1], vectors[:1])
        check(store.count("B") == 1, "obsolete chunk removed on changed snapshot")
        fresh = PgVectorStore(database_url, dimensions, embedding_signature=signature, schema=schema)
        hits = fresh.search("C", vectors[0], filters={"Type": chunks[0].metadata["Type"]})
        check(fresh.count("C") == 1 and len(hits) == 1 and hits[0]["chunk_id"] == chunks[0].chunk_id,
              "persistent read and C alias/filter")
        check(abs(hits[0]["score"] - 1.0) < 1e-5, "self-vector cosine score")
        check(store.search("C", vectors[0], filters={"Type": "Process' OR TRUE --"}) == [],
              "filter value parameterized")
        try:
            store.upsert("B", chunks[:1], [vectors[0][:-1]])
        except ValueError:
            check(store.count("B") == 1, "bad vector rejected without mutation")
        else:
            raise ValueError("Bad vector accepted")
        try:
            store.upsert("B", [replace(chunks[0], page=None)], vectors[:1])
        except psycopg.errors.NotNullViolation:
            check(store.count("B") == 1 and store.search("B", vectors[0])[0]["page"] == chunks[0].page,
                  "failed database write rolled back")
        else:
            raise ValueError("Invalid database row accepted")
        incompatible = PgVectorStore(database_url, dimensions, embedding_signature="different-model", schema=schema)
        try:
            incompatible.search("B", vectors[0])
        except ValueError:
            passed.append("incompatible model blocked")
        else:
            raise ValueError("Incompatible query model accepted")
        try:
            store.search("C", vectors[0], filters={"source": "gold-source"})
        except ValueError:
            passed.append("nonallowlisted filter blocked")
        else:
            raise ValueError("Unexpected filter accepted")
    finally:
        # Only the fresh UUID-named schema created by this function is removed.
        with store.connect() as conn:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
    return {"passed": passed, "uses_real_embeddings": True, "temporary_schema_removed": True}
