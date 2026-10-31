from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

from src.core.config import Settings
from src.rag.knowledge_base import _sync_articles, load_documents

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rebuild the finance knowledge-base Chroma collection from Markdown articles."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm replacing the existing finance_education collection.",
    )
    args = parser.parse_args()
    if not args.yes:
        parser.error("Reindexing replaces the finance_education collection; pass --yes to confirm.")

    load_dotenv(ROOT / ".env")
    settings = Settings.load(ROOT / "config.yaml")
    documents = load_documents(settings.knowledge_base_path)
    persist_directory = settings.chroma_path
    persist_directory.mkdir(parents=True, exist_ok=True)
    embeddings = OpenAIEmbeddings(model=settings.embedding_model)
    store = Chroma(
        collection_name="finance_education",
        embedding_function=embeddings,
        persist_directory=str(persist_directory),
    )
    store.delete_collection()
    store = Chroma(
        collection_name="finance_education",
        embedding_function=embeddings,
        persist_directory=str(persist_directory),
    )
    indexed = _sync_articles(
        store,
        documents,
    )
    chunk_count = len(store.get(include=["metadatas"])["ids"])
    print(
        f"Reindexed {len(indexed)} articles into {chunk_count} chunks at "
        f"{persist_directory}."
    )


if __name__ == "__main__":
    main()
