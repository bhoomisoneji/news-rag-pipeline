from __future__ import annotations

from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from src.config import (
    CHROMA_COLLECTION,
    CHROMA_DIR,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    EMBEDDING_MODEL,
    RECORDS_DIR,
)
from src.io_util import read_json
from src.schema import ArticleRecord


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    if size <= 0:
        raise ValueError("chunk size must be positive")
    if overlap >= size:
        raise ValueError("overlap must be smaller than chunk size")
    cleaned = " ".join(text.split())
    if not cleaned:
        return []
    chunks: list[str] = []
    start = 0
    length = len(cleaned)
    while start < length:
        end = min(start + size, length)
        if end < length:
            window = cleaned[start:end]
            split_at = window.rfind(". ")
            if split_at >= size // 2:
                end = start + split_at + 1
        piece = cleaned[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= length:
            break
        start = max(end - overlap, start + 1)
    return chunks


def metadata_for(record: ArticleRecord, chunk_index: int) -> dict:
    companies = ", ".join(record.companies)
    locations = ", ".join(record.locations)
    published = record.published_at.isoformat()
    return {
        "article_id": record.id,
        "url": record.url,
        "title": record.title[:300],
        "published_at": published,
        "category": record.category,
        "companies": companies,
        "locations": locations,
        "chunk_index": chunk_index,
        "has_funding": bool(record.funding),
    }


def get_collection(path: Path | None = None, embedder=None):
    persist = str(path or CHROMA_DIR)
    client = chromadb.PersistentClient(path=persist)
    embedding_fn = embedder or SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )
    return client.get_or_create_collection(
        name=CHROMA_COLLECTION,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )


def replace_article(collection, record: ArticleRecord) -> int:
    existing = collection.get(where={"article_id": record.id})
    if existing and existing.get("ids"):
        collection.delete(ids=existing["ids"])
    chunks = chunk_text(record.body)
    if not chunks:
        return 0
    ids = [f"{record.id}:{index}" for index in range(len(chunks))]
    metadatas = [metadata_for(record, index) for index in range(len(chunks))]
    collection.add(ids=ids, documents=chunks, metadatas=metadatas)
    return len(chunks)


def load_records(records_dir: Path | None = None) -> list[ArticleRecord]:
    directory = records_dir or RECORDS_DIR
    records: list[ArticleRecord] = []
    for path in sorted(directory.glob("*.json")):
        records.append(ArticleRecord.model_validate(read_json(path)))
    return records


def index_all(records_dir: Path | None = None, chroma_dir: Path | None = None, embedder=None) -> dict[str, int]:
    records = load_records(records_dir)
    collection = get_collection(chroma_dir, embedder=embedder)
    chunks = 0
    for record in records:
        chunks += replace_article(collection, record)
    return {"articles": len(records), "chunks": chunks}
