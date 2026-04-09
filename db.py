import re
import sqlite3
from typing import Dict, List, Sequence

from config import DB_PATH


# =========================
# CONNECTION & SCHEMA
# =========================
# Database module centralizes all SQLite operations used by all Streamlit pages.
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kb_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kb_vectors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chunk_id INTEGER NOT NULL,
                embedding BLOB NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(chunk_id) REFERENCES kb_chunks(id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_kb_chunks_document ON kb_chunks(document_name)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_kb_vectors_chunk ON kb_vectors(chunk_id)"
        )
        conn.commit()


# =========================
# DASHBOARD QUERIES
# =========================
def get_kb_stats():
    with get_conn() as conn:
        docs = conn.execute(
            "SELECT COUNT(DISTINCT document_name) AS n FROM kb_chunks"
        ).fetchone()["n"]
        chunks = conn.execute("SELECT COUNT(*) AS n FROM kb_chunks").fetchone()["n"]
    return docs, chunks


def get_recent_documents(limit=10):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT document_name, source_type, COUNT(*) AS total_chunks, MAX(created_at) AS last_added
            FROM kb_chunks
            GROUP BY document_name, source_type
            ORDER BY last_added DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return rows


def list_documents():
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                document_name,
                COUNT(*) AS total_chunks,
                MAX(created_at) AS last_added
            FROM kb_chunks
            GROUP BY document_name
            ORDER BY last_added DESC
            """
        ).fetchall()
    return rows


def get_document_names():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT document_name FROM kb_chunks ORDER BY document_name ASC"
        ).fetchall()
    return [row["document_name"] for row in rows]


def get_document_chunks(document_name, keyword="", limit=10, offset=0):
    keyword = (keyword or "").strip().lower()
    params: List[object] = [document_name]
    where_clause = "WHERE document_name = ?"

    if keyword:
        where_clause += " AND LOWER(content) LIKE ?"
        params.append(f"%{keyword}%")

    with get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM kb_chunks {where_clause}",
            tuple(params),
        ).fetchone()["n"]

        rows = conn.execute(
            f"""
            SELECT id, document_name, chunk_index, content
            FROM kb_chunks
            {where_clause}
            ORDER BY chunk_index ASC
            LIMIT ? OFFSET ?
            """,
            tuple(params + [limit, offset]),
        ).fetchall()

    return rows, total


# =========================
# WRITE OPERATIONS
# =========================
def insert_document_chunks(file_name, source_type, chunks, embeddings):
    if not chunks:
        return 0

    if len(chunks) != len(embeddings):
        raise ValueError("Jumlah chunk dan embedding tidak sama.")

    with get_conn() as conn:
        for chunk_idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            cur = conn.execute(
                """
                INSERT INTO kb_chunks (document_name, source_type, chunk_index, content)
                VALUES (?, ?, ?, ?)
                """,
                (file_name, source_type, chunk_idx, chunk),
            )
            chunk_id = cur.lastrowid
            conn.execute(
                """
                INSERT INTO kb_vectors (chunk_id, embedding)
                VALUES (?, ?)
                """,
                (chunk_id, embedding.tobytes()),
            )
        conn.commit()

    return len(chunks)


def delete_document(document_name):
    with get_conn() as conn:
        chunk_rows = conn.execute(
            "SELECT id FROM kb_chunks WHERE document_name = ?",
            (document_name,),
        ).fetchall()
        chunk_ids = [row["id"] for row in chunk_rows]

        if not chunk_ids:
            return 0

        placeholders = ",".join("?" for _ in chunk_ids)
        conn.execute(
            f"DELETE FROM kb_vectors WHERE chunk_id IN ({placeholders})",
            tuple(chunk_ids),
        )
        conn.execute(
            "DELETE FROM kb_chunks WHERE document_name = ?",
            (document_name,),
        )
        conn.commit()

    return len(chunk_ids)


# =========================
# VECTOR INDEX SUPPORT
# =========================
def get_all_vectors():
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT v.id, v.chunk_id, v.embedding
            FROM kb_vectors v
            ORDER BY v.id ASC
            """
        ).fetchall()
    return rows


def get_vector_chunk_ids():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT chunk_id FROM kb_vectors ORDER BY id ASC"
        ).fetchall()
    return [row["chunk_id"] for row in rows]


def get_chunks_by_ids(chunk_ids: Sequence[int]) -> Dict[int, sqlite3.Row]:
    if not chunk_ids:
        return {}

    placeholders = ",".join("?" for _ in chunk_ids)
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT id, document_name, chunk_index, content
            FROM kb_chunks
            WHERE id IN ({placeholders})
            """,
            tuple(chunk_ids),
        ).fetchall()

    return {row["id"]: row for row in rows}


def has_chunks():
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM kb_chunks").fetchone()["n"]
    return count > 0


# =========================
# KEYWORD SEARCH
# =========================
def _tokenize_terms(query: str) -> List[str]:
    return [token for token in re.findall(r"[A-Za-z0-9_]+", query.lower()) if len(token) >= 2]


def search_chunks_by_keyword(query: str, limit=20):
    terms = _tokenize_terms(query)
    if not terms:
        return []

    like_clause = " OR ".join(["LOWER(content) LIKE ?"] * len(terms))
    params = [f"%{term}%" for term in terms]

    # Pull a slightly larger candidate set, then score in Python.
    sql_limit = max(limit * 3, 30)
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT id, document_name, chunk_index, content
            FROM kb_chunks
            WHERE {like_clause}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            tuple(params + [sql_limit]),
        ).fetchall()

    results = []
    query_lower = query.lower().strip()
    for row in rows:
        content_lower = row["content"].lower()
        hits = sum(content_lower.count(term) for term in terms)
        phrase_bonus = 2 if query_lower and query_lower in content_lower else 0
        denominator = max(len(terms) * 2, 1)
        keyword_score = min(1.0, (hits + phrase_bonus) / denominator)

        if keyword_score <= 0:
            continue

        results.append(
            {
                "id": row["id"],
                "document_name": row["document_name"],
                "chunk_index": row["chunk_index"],
                "content": row["content"],
                "keyword_score": keyword_score,
            }
        )

    results.sort(key=lambda item: item["keyword_score"], reverse=True)
    return results[:limit]
