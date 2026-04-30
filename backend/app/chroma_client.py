"""ChromaDB client wrapper used by the API for retrieval-only operations.

(Workers do the writing — see workers/shared/activities.py.)
"""
from __future__ import annotations
import chromadb
from chromadb.config import Settings as ChromaSettings


def make_chroma_client(host: str, port: int):
    return chromadb.HttpClient(
        host=host,
        port=port,
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def get_or_create_collection(client, name: str):
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


def query_collection(collection, query_text: str, top_k: int,
                     file_ids: list[str] | None = None) -> list[dict]:
    """Return list of {file_id, filename, text, distance} ordered by relevance.

    If `file_ids` is provided, the search is restricted to chunks whose
    metadata.file_id is in that list (Chroma's `where` filter).
    """
    where = None
    if file_ids:
        where = {"file_id": {"$in": list(file_ids)}} if len(file_ids) > 1 \
            else {"file_id": file_ids[0]}

    res = collection.query(
        query_texts=[query_text],
        n_results=max(1, top_k),
        where=where,
    )

    out: list[dict] = []
    if not res or not res.get("ids") or not res["ids"][0]:
        return out

    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    dists = res.get("distances", [[]])[0]
    for doc, meta, dist in zip(docs, metas, dists):
        out.append({
            "file_id": (meta or {}).get("file_id", ""),
            "filename": (meta or {}).get("filename", ""),
            "text": doc or "",
            "distance": float(dist) if dist is not None else None,
        })
    return out


def delete_by_file(collection, file_id: str) -> None:
    try:
        collection.delete(where={"file_id": file_id})
    except Exception:
        # collection may be empty / file not yet ingested — non-fatal
        pass
