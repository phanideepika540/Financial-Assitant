import pytest

from src.rag.knowledge_base import format_references
from src.utils.input_validation import build_goal_planning_question, validate_question


def test_validates_and_trims_question():
    assert validate_question("  Explain bonds  ", 100) == "Explain bonds"


def test_rejects_empty_or_oversized_question():
    with pytest.raises(ValueError, match="enter a question"):
        validate_question(" \n ", 100)
    with pytest.raises(ValueError, match="under 5"):
        validate_question("too long", 5)


def test_goal_planning_prompt_contains_goal_and_context():
    question = build_goal_planning_question(
        "build an emergency fund",
        "2 years",
        "$5,000",
    )
    assert "build an emergency fund" in question
    assert "2 years" in question
    assert "$5,000" in question


def test_goal_planning_requires_a_goal():
    with pytest.raises(ValueError, match="Enter a goal"):
        build_goal_planning_question(" ")


def test_reference_formatter_includes_source_urls():
    from langchain_core.documents import Document

    rendered, sources = format_references(
        [
            Document(
                page_content="Diversification spreads risk. Source: https://www.investor.gov/example",
                metadata={"source": "basics.md"},
            )
        ]
    )
    assert "basics.md" in rendered
    assert "https://www.investor.gov/example" in sources
