from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
import yaml

_ARTICLE_FIELDS = {
    "id",
    "title",
    "publisher",
    "source_url",
    "reviewed_date",
    "jurisdiction",
    "specialist",
    "topic",
}
_ALLOWED_SPECIALISTS = {
    "finance_qa",
    "portfolio_analysis",
    "market_analysis",
    "goal_planning",
    "news_synthesizer",
    "tax_education",
    "general",
}


def load_documents(directory: str | Path) -> list[Document]:
    root = Path(directory)
    if not root.is_dir():
        raise FileNotFoundError(f"Knowledge base directory not found: {root}")
    documents = []
    article_ids: set[str] = set()
    for path in sorted(root.glob("*.md")):
        content = path.read_text(encoding="utf-8").strip()
        if content:
            document = _parse_article(content, path.name)
            article_id = document.metadata["article_id"]
            if article_id in article_ids:
                raise ValueError(f"Duplicate knowledge article id '{article_id}' in {root}.")
            article_ids.add(article_id)
            documents.append(document)
    if not documents:
        raise FileNotFoundError(f"No Markdown knowledge documents found in {root}")
    return documents


def _parse_article(content: str, filename: str) -> Document:
    if not content.startswith("---\n"):
        raise ValueError(f"Knowledge article '{filename}' is missing YAML frontmatter.")
    frontmatter, separator, body = content[4:].partition("\n---\n")
    if not separator:
        raise ValueError(f"Knowledge article '{filename}' has invalid YAML frontmatter.")
    metadata = yaml.safe_load(frontmatter)
    if not isinstance(metadata, dict):
        raise ValueError(f"Knowledge article '{filename}' frontmatter must be a mapping.")
    missing = _ARTICLE_FIELDS - metadata.keys()
    if missing:
        raise ValueError(
            f"Knowledge article '{filename}' is missing metadata fields: "
            + ", ".join(sorted(missing))
        )
    normalized = {key: str(metadata[key]).strip() for key in _ARTICLE_FIELDS}
    if any(not value for value in normalized.values()):
        raise ValueError(f"Knowledge article '{filename}' metadata values cannot be blank.")
    if normalized["specialist"] not in _ALLOWED_SPECIALISTS:
        raise ValueError(
            f"Knowledge article '{filename}' has unsupported specialist "
            f"'{normalized['specialist']}'."
        )
    if not normalized["source_url"].startswith(("https://", "http://")):
        raise ValueError(f"Knowledge article '{filename}' source_url must be an HTTP URL.")
    body = body.strip()
    if not body:
        raise ValueError(f"Knowledge article '{filename}' has no article content.")
    digest_input = json.dumps(
        {"metadata": normalized, "content": body},
        sort_keys=True,
        ensure_ascii=True,
    )
    content_hash = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
    chroma_metadata = {
        "article_id": normalized["id"],
        "title": normalized["title"],
        "publisher": normalized["publisher"],
        "source_url": normalized["source_url"],
        "reviewed_date": normalized["reviewed_date"],
        "jurisdiction": normalized["jurisdiction"],
        "specialist": normalized["specialist"],
        "topic": normalized["topic"],
        "content_hash": content_hash,
        "source": normalized["source_url"],
    }
    return Document(page_content=body, metadata=chroma_metadata)


def open_or_create_vector_store(
    knowledge_base_dir: str | Path,
    persist_directory: str | Path,
    embedding_model: str,
) -> Chroma:
    embeddings = OpenAIEmbeddings(model=embedding_model)
    persist_path = Path(persist_directory)
    persist_path.mkdir(parents=True, exist_ok=True)
    store = Chroma(
        collection_name="finance_education",
        embedding_function=embeddings,
        persist_directory=str(persist_path),
    )
    _sync_articles(store, load_documents(knowledge_base_dir))
    return store


def _sync_articles(store: Any, documents: list[Document]) -> list[str]:
    existing = store.get(include=["metadatas"])
    ids = existing.get("ids", [])
    metadatas = existing.get("metadatas", [])
    existing_by_article: dict[str, list[tuple[str, str]]] = {}
    has_legacy_chunks = False
    for chunk_id, metadata in zip(ids, metadatas, strict=True):
        if not metadata or not metadata.get("article_id"):
            has_legacy_chunks = True
            continue
        article_id = str(metadata["article_id"])
        existing_by_article.setdefault(article_id, []).append(
            (str(chunk_id), str(metadata.get("content_hash", "")))
        )

    desired = {str(document.metadata["article_id"]): document for document in documents}
    changed_ids: list[str] = []
    to_index: list[Document] = []
    for article_id, indexed_chunks in existing_by_article.items():
        desired_document = desired.get(article_id)
        if desired_document is None or any(
            chunk_hash != desired_document.metadata["content_hash"]
            for _, chunk_hash in indexed_chunks
        ):
            changed_ids.extend(chunk_id for chunk_id, _ in indexed_chunks)
    if has_legacy_chunks:
        changed_ids = list(ids)
        to_index = documents
    else:
        indexed_article_ids = set(existing_by_article)
        to_index = [
            document
            for article_id, document in desired.items()
            if article_id not in indexed_article_ids
            or any(
                chunk_hash != document.metadata["content_hash"]
                for _, chunk_hash in existing_by_article[article_id]
            )
        ]
    if changed_ids:
        store.delete(ids=changed_ids)
    if not to_index:
        return []
    splitter = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=120)
    chunks = splitter.split_documents(to_index)
    chunk_ids = [
        f"{document.metadata['article_id']}:{document.metadata['content_hash']}:{index}"
        for index, document in enumerate(chunks)
    ]
    store.add_documents(chunks, ids=chunk_ids)
    return [str(document.metadata["article_id"]) for document in to_index]


def retrieve_references(
    store: Any,
    query: str,
    limit: int = 4,
    specialists: list[str] | None = None,
) -> list[Document]:
    if not specialists:
        return store.similarity_search(query, k=limit)
    allowed_specialists = retrieval_specialist_values(specialists)
    metadata_filter = {
        "$or": [{"specialist": specialist} for specialist in allowed_specialists]
    }
    return store.similarity_search(query, k=limit, filter=metadata_filter)


def retrieval_specialist_values(specialists: list[str]) -> list[str]:
    return list(dict.fromkeys([*specialists, "general"]))


def format_references(documents: list[Document]) -> tuple[str, list[str]]:
    if not documents:
        return "No relevant knowledge-base passages were retrieved.", []
    rendered = []
    sources = []
    for index, document in enumerate(documents, start=1):
        source = str(
            document.metadata.get("source_url")
            or document.metadata.get("source", "Knowledge base")
        )
        title = str(document.metadata.get("title", source))
        publisher = str(document.metadata.get("publisher", ""))
        rendered.append(
            f"[{index}] Article: {title}; Publisher: {publisher}; Source: {source}\n"
            f"{document.page_content}"
        )
        if source not in sources:
            sources.append(source)
        for url in re.findall(r"https?://[^\s)>\]]+", document.page_content):
            cleaned_url = url.rstrip(".,;")
            if cleaned_url not in sources:
                sources.append(cleaned_url)
    return "\n\n".join(rendered), sources


def format_citations(documents: list[Document]) -> list[dict[str, str]]:
    citations: dict[str, dict[str, str]] = {}
    for document in documents:
        metadata = document.metadata
        article_id = str(metadata.get("article_id", ""))
        source_url = str(metadata.get("source_url") or metadata.get("source", ""))
        key = article_id or source_url
        if not key or key in citations:
            continue
        citations[key] = {
            "article_id": article_id,
            "title": str(metadata.get("title", source_url)),
            "publisher": str(metadata.get("publisher", "")),
            "source_url": source_url,
            "reviewed_date": str(metadata.get("reviewed_date", "")),
            "specialist": str(metadata.get("specialist", "")),
        }
    return list(citations.values())
