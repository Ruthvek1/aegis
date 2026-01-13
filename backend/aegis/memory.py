import os
import uuid
import json
from typing import List, Dict, Any
from psycopg_pool import AsyncConnectionPool
import pgvector.psycopg  # type: ignore

EMBEDDING_DIM = 384


class DeterministicFakeEmbedder:
    """
    A fake deterministic embedder that uses character tri-grams to produce
    rough semantic similarity (bag-of-ngrams) mapped into 384 dimensions,
    so cosine distance actually reflects text overlap.
    """

    @staticmethod
    def embed(text: str) -> List[float]:
        text = text.lower()
        vec = [0.0] * EMBEDDING_DIM
        if not text:
            return vec
        # generate char trigrams
        for i in range(len(text) - 2):
            trigram = text[i : i + 3]
            # hash to bucket
            bucket = hash(trigram) % EMBEDDING_DIM
            vec[bucket] += 1.0

        # L2 Normalize
        norm = sum(x * x for x in vec) ** 0.5
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec


class MemoryManager:
    def __init__(self, db_uri: str):
        # We explicitly use autocommit=False (the default) so we can wrap operations in transactions
        self.pool = AsyncConnectionPool(db_uri, open=False)
        self._opened = False
        self._ready = False

    async def open(self):
        if not self._opened:
            await self.pool.open()
            self._opened = True

    async def close(self):
        if self._opened:
            await self.pool.close()
            self._opened = False
            self._ready = False

    async def _ensure_ready(self):
        """Lazily open the pool and create tables once (idempotent).

        This means any code path (a graph node, a direct call, a test) works
        whether or not a fixture pre-opened the manager. No node needs a
        try/except to hide a closed pool, and no test needs to pre-open it.
        """
        if self._ready:
            return
        await self.open()
        await self.setup_memory_tables()
        self._ready = True

    async def setup_memory_tables(self):
        """Idempotent setup for the tables and extensions."""
        async with self.pool.connection() as conn:
            async with conn.transaction():
                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                await pgvector.psycopg.register_vector_async(conn)

                await conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS episodic_memory (
                        id UUID PRIMARY KEY,
                        task TEXT,
                        plan JSONB,
                        outcome TEXT,
                        embedding vector({EMBEDDING_DIM})
                    )
                """)

                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS semantic_memory (
                        id UUID PRIMARY KEY,
                        entity_source TEXT,
                        entity_target TEXT,
                        relationship TEXT,
                        context TEXT
                    )
                """)

                await conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS procedural_memory (
                        id UUID PRIMARY KEY,
                        name TEXT,
                        description TEXT,
                        tool_sequence JSONB,
                        success_count INT,
                        total_runs INT,
                        embedding vector({EMBEDDING_DIM})
                    )
                """)

                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS event_log (
                        id UUID PRIMARY KEY,
                        run_id TEXT,
                        step_index INT,
                        node_name TEXT,
                        state_snapshot JSONB,
                        timestamp TIMESTAMPTZ DEFAULT NOW()
                    )
                """)

    async def save_episodic(self, task: str, plan: list, outcome: str):
        await self._ensure_ready()
        embedding = DeterministicFakeEmbedder.embed(task)
        async with self.pool.connection() as conn:
            async with conn.transaction():
                await pgvector.psycopg.register_vector_async(conn)
                await conn.execute(
                    "INSERT INTO episodic_memory (id, task, plan, outcome, embedding) VALUES (%s, %s, %s, %s, %s)",
                    (uuid.uuid4(), task, json.dumps(plan), outcome, embedding),
                )

    async def retrieve_episodic(
        self, task: str, limit: int = 3
    ) -> List[Dict[str, Any]]:
        await self._ensure_ready()
        embedding = DeterministicFakeEmbedder.embed(task)
        async with self.pool.connection() as conn:
            await pgvector.psycopg.register_vector_async(conn)
            # Use cosine distance <=> for ordering
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT task, plan, outcome, 1 - (embedding <=> %s::vector) AS similarity 
                    FROM episodic_memory 
                    ORDER BY embedding <=> %s::vector 
                    LIMIT %s
                    """,
                    (embedding, embedding, limit),
                )
                rows = await cur.fetchall()
                return [
                    {"task": r[0], "plan": r[1], "outcome": r[2], "similarity": r[3]}
                    for r in rows
                ]

    async def save_procedural(
        self, name: str, description: str, tool_sequence: list, success: bool
    ):
        await self._ensure_ready()
        embedding = DeterministicFakeEmbedder.embed(name + " " + description)
        async with self.pool.connection() as conn:
            async with conn.transaction():
                await pgvector.psycopg.register_vector_async(conn)
                # For simplicity, we just insert. In reality, we'd upsert and increment stats.
                await conn.execute(
                    """
                    INSERT INTO procedural_memory (id, name, description, tool_sequence, success_count, total_runs, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        uuid.uuid4(),
                        name,
                        description,
                        json.dumps(tool_sequence),
                        1 if success else 0,
                        1,
                        embedding,
                    ),
                )

    async def retrieve_procedural(
        self, query: str, limit: int = 1
    ) -> List[Dict[str, Any]]:
        await self._ensure_ready()
        embedding = DeterministicFakeEmbedder.embed(query)
        async with self.pool.connection() as conn:
            await pgvector.psycopg.register_vector_async(conn)
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT name, description, tool_sequence, 1 - (embedding <=> %s::vector) AS similarity
                    FROM procedural_memory
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (embedding, embedding, limit),
                )
                rows = await cur.fetchall()
                return [
                    {
                        "name": r[0],
                        "description": r[1],
                        "tool_sequence": r[2],
                        "similarity": r[3],
                    }
                    for r in rows
                ]

    async def save_semantic(
        self, entity_source: str, entity_target: str, relationship: str, context: str
    ):
        await self._ensure_ready()
        async with self.pool.connection() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO semantic_memory (id, entity_source, entity_target, relationship, context) VALUES (%s, %s, %s, %s, %s)",
                    (uuid.uuid4(), entity_source, entity_target, relationship, context),
                )

    async def query_semantic(self, entity: str) -> List[Dict[str, Any]]:
        await self._ensure_ready()
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT entity_source, entity_target, relationship, context 
                    FROM semantic_memory 
                    WHERE entity_source = %s OR entity_target = %s
                    """,
                    (entity, entity),
                )
                rows = await cur.fetchall()
                return [
                    {"source": r[0], "target": r[1], "relation": r[2], "context": r[3]}
                    for r in rows
                ]

    async def record_event(self, run_id: str, node_name: str, state_snapshot: dict):
        await self._ensure_ready()

        # Serialize carefully in case state has non-JSON types (like messages)
        # LangGraph state usually contains BaseMessage objects.
        # We need a custom serializer for LangChain messages if they appear in the state.
        def _serialize(obj):
            if hasattr(obj, "dict"):
                return obj.dict()
            if hasattr(obj, "model_dump"):
                return obj.model_dump()
            raise TypeError(f"Type {type(obj)} not serializable")

        try:
            snapshot_json = json.dumps(state_snapshot, default=_serialize)
        except Exception:
            snapshot_json = json.dumps({"error": "unserializable state"})

        async with self.pool.connection() as conn:
            async with conn.transaction():
                cur = await conn.execute(
                    "SELECT COALESCE(MAX(step_index), -1) + 1 FROM event_log WHERE run_id = %s",
                    (run_id,),
                )
                row = await cur.fetchone()
                step_index = row[0] if row else 0

                await conn.execute(
                    "INSERT INTO event_log (id, run_id, step_index, node_name, state_snapshot) VALUES (%s, %s, %s, %s, %s)",
                    (uuid.uuid4(), run_id, step_index, node_name, snapshot_json),
                )

    async def replay_log(self, run_id: str) -> List[Dict[str, Any]]:
        await self._ensure_ready()
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT step_index, node_name, state_snapshot, timestamp FROM event_log WHERE run_id = %s ORDER BY step_index ASC",
                    (run_id,),
                )
                rows = await cur.fetchall()
                return [
                    {
                        "step_index": r[0],
                        "node_name": r[1],
                        "state_snapshot": r[2],
                        "timestamp": r[3],
                    }
                    for r in rows
                ]


_global_mm = None


def get_memory_manager(db_uri: str | None = None) -> MemoryManager:
    global _global_mm
    if _global_mm is None:
        uri = (
            db_uri
            if db_uri is not None
            else os.getenv(
                "DATABASE_URL", "postgresql://postgres:password@localhost:5432/aegis"
            )
        )
        assert uri is not None
        _global_mm = MemoryManager(uri)
    return _global_mm
