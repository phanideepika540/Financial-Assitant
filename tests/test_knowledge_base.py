from pathlib import Path

import pytest
from langchain_core.documents import Document

from src.rag.knowledge_base import (
    _parse_article,
    _sync_articles,
    format_citations,
    format_references,
    load_documents,
    retrieve_references,
)

KNOWLEDGE_DIR = Path(__file__).parents[1] / "src" / "data" / "knowledge_base"


class InMemoryVectorStore:
    def __init__(self):
        self.ids = []
        self.metadatas = []
        self.added_documents = []
        self.filters = []

    def get(self, include):
        assert include == ["metadatas"]
        return {"ids": self.ids.copy(), "metadatas": self.metadatas.copy()}

    def delete(self, ids):
        deleted = set(ids)
        retained = [
            (chunk_id, metadata)
            for chunk_id, metadata in zip(self.ids, self.metadatas, strict=True)
            if chunk_id not in deleted
        ]
        self.ids = [chunk_id for chunk_id, _ in retained]
        self.metadatas = [metadata for _, metadata in retained]

    def add_documents(self, documents, ids):
        self.added_documents.extend(documents)
        self.ids.extend(ids)
        self.metadatas.extend(document.metadata for document in documents)

    def similarity_search(self, query, k, filter=None):
        self.filters.append(filter)
        return []


def test_loads_unique_articles_with_complete_metadata():
    documents = load_documents(KNOWLEDGE_DIR)
    specialist_names = {
        "finance_qa",
        "portfolio_analysis",
        "market_analysis",
        "goal_planning",
        "news_synthesizer",
        "tax_education",
    }

    assert 50 <= len(documents) <= 100
    assert len({document.metadata["article_id"] for document in documents}) == len(
        documents
    )
    assert len({document.metadata["source_url"] for document in documents}) == len(
        documents
    )
    assert specialist_names.issubset(
        {document.metadata["specialist"] for document in documents}
    )
    assert all(
        {
            "article_id",
            "title",
            "publisher",
            "source_url",
            "reviewed_date",
            "jurisdiction",
            "specialist",
            "topic",
            "content_hash",
        }.issubset(document.metadata)
        for document in documents
    )
    assert all(document.metadata["source_url"].startswith("https://") for document in documents)


def test_article_loader_requires_frontmatter():
    with pytest.raises(ValueError, match="missing YAML frontmatter"):
        from src.rag.knowledge_base import _parse_article

        _parse_article("# No metadata", "invalid.md")


def test_article_loader_rejects_unsupported_specialist():
    source_text = (KNOWLEDGE_DIR / "cfpb_emergency_fund.md").read_text(
        encoding="utf-8"
    )
    invalid_article = source_text.replace(
        "specialist: goal_planning", "specialist: goal_planner", 1
    )

    with pytest.raises(ValueError, match="unsupported specialist"):
        _parse_article(invalid_article, "invalid-specialist.md")


def test_indexes_all_articles_and_skips_unchanged_content():
    store = InMemoryVectorStore()
    documents = load_documents(KNOWLEDGE_DIR)

    indexed = _sync_articles(store, documents)

    assert len(indexed) == len(documents)
    assert len(store.added_documents) >= len(documents)
    original_ids = store.ids.copy()
    assert _sync_articles(store, documents) == []
    assert store.ids == original_ids


def test_replaces_changed_article_chunks_and_removes_deleted_articles():
    store = InMemoryVectorStore()
    documents = load_documents(KNOWLEDGE_DIR)
    _sync_articles(store, documents)
    old_chunks = {
        chunk_id
        for chunk_id, metadata in zip(store.ids, store.metadatas, strict=True)
        if metadata["article_id"] == "cfpb-emergency-fund"
    }
    source_text = (KNOWLEDGE_DIR / "cfpb_emergency_fund.md").read_text(
        encoding="utf-8"
    )
    frontmatter, _, body = source_text[4:].partition("\n---\n")
    changed_article = _parse_article(
        f"---\n{frontmatter}\n---\n{body}\nAdditional reviewed detail.",
        "cfpb_emergency_fund.md",
    )
    changed = [
        changed_article
        if document.metadata["article_id"] == "cfpb-emergency-fund"
        else document
        for document in documents
        if document.metadata["article_id"] != "irs-tax-topics"
    ]

    updated = _sync_articles(store, changed)

    assert "cfpb-emergency-fund" in updated
    assert "irs-tax-topics" not in {metadata["article_id"] for metadata in store.metadatas}
    assert old_chunks.isdisjoint(store.ids)


def test_rebuilds_legacy_chunks_without_article_metadata():
    store = InMemoryVectorStore()
    store.ids = ["legacy-1"]
    store.metadatas = [{"source": "financial_goals.md"}]
    documents = load_documents(KNOWLEDGE_DIR)

    indexed = _sync_articles(store, documents)

    assert len(indexed) == len(documents)
    assert all(metadata.get("article_id") for metadata in store.metadatas)


def test_retrieval_filters_for_selected_specialists_and_general_articles():
    store = InMemoryVectorStore()

    retrieve_references(
        store,
        "emergency savings",
        specialists=["goal_planning", "tax_education"],
    )

    assert store.filters == [
        {
            "$or": [
                {"specialist": "goal_planning"},
                {"specialist": "tax_education"},
                {"specialist": "general"},
            ]
        }
    ]


def test_reference_formatter_and_citations_use_article_metadata():
    document = Document(
        page_content="Emergency savings can help prepare for unexpected costs.",
        metadata={
            "article_id": "cfpb-emergency-fund",
            "title": "Emergency fund guide",
            "publisher": "CFPB",
            "source_url": "https://example.gov/emergency",
            "reviewed_date": "2026-10-29",
            "source": "https://example.gov/emergency",
        },
    )

    rendered, sources = format_references([document, document])
    citations = format_citations([document, document])

    assert "Article: Emergency fund guide; Publisher: CFPB" in rendered
    assert sources == ["https://example.gov/emergency"]
    assert citations == [
        {
            "article_id": "cfpb-emergency-fund",
            "title": "Emergency fund guide",
            "publisher": "CFPB",
            "source_url": "https://example.gov/emergency",
            "reviewed_date": "2026-10-29",
        }
    ]
