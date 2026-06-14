"""
tests/test_tools.py

Edge-case tests for all three FitFindr tools.
suggest_outfit and create_fit_card mock the Groq client so no real API calls
are made. search_listings reads from the real data file.
"""

import sys
import os
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools import search_listings, suggest_outfit, create_fit_card

# ── Fixtures ──────────────────────────────────────────────────────────────────

SAMPLE_ITEM = {
    "id": "t_001",
    "title": "Faded Band Tee",
    "description": "Vintage style band tee, slightly worn",
    "category": "tops",
    "style_tags": ["vintage", "grunge", "graphic"],
    "size": "M",
    "condition": "good",
    "price": 22.0,
    "colors": ["grey", "black"],
    "brand": None,
    "platform": "depop",
}

POPULATED_WARDROBE = {
    "items": [
        {
            "id": "w_001",
            "name": "Baggy straight-leg jeans, dark wash",
            "category": "bottoms",
            "colors": ["dark blue"],
            "style_tags": ["denim", "streetwear"],
            "notes": "High-waisted",
        },
        {
            "id": "w_002",
            "name": "Black combat boots",
            "category": "shoes",
            "colors": ["black"],
            "style_tags": ["grunge", "chunky"],
            "notes": "",
        },
    ]
}

EMPTY_WARDROBE = {"items": []}


def _make_mock_client(response_text: str) -> MagicMock:
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices[0].message.content = response_text
    return mock_client


# ── search_listings ───────────────────────────────────────────────────────────

class TestSearchListings:
    def test_returns_list(self):
        assert isinstance(search_listings("tee"), list)

    def test_matching_query_returns_results(self):
        results = search_listings("vintage graphic tee")
        assert len(results) > 0

    def test_no_match_returns_empty_list(self):
        # impossible combination — should not raise, just return []
        results = search_listings("designer ballgown", size="XXS", max_price=5.0)
        assert results == []

    def test_price_filter_inclusive_boundary(self):
        # items priced exactly at max_price must be included
        results = search_listings("tee", max_price=18.0)
        assert all(item["price"] <= 18.0 for item in results)
        prices = [item["price"] for item in results]
        assert 18.0 in prices  # at least one item AT the boundary

    def test_price_filter_excludes_above_max(self):
        results = search_listings("jacket", max_price=20.0)
        assert all(item["price"] <= 20.0 for item in results)

    def test_price_filter_none_skips_filtering(self):
        all_results = search_listings("vintage", max_price=None)
        capped_results = search_listings("vintage", max_price=20.0)
        assert len(all_results) >= len(capped_results)

    def test_size_exact_match(self):
        results = search_listings("tee", size="L")
        assert all("l" in item["size"].lower() for item in results)

    def test_size_substring_match(self):
        # "M" should match listings whose size field contains "S/M"
        results = search_listings("top", size="M")
        assert all("m" in item["size"].lower() for item in results)

    def test_size_case_insensitive(self):
        lower = search_listings("tee", size="m")
        upper = search_listings("tee", size="M")
        assert [r["id"] for r in lower] == [r["id"] for r in upper]

    def test_size_none_skips_filtering(self):
        with_size = search_listings("tee", size="M")
        without_size = search_listings("tee", size=None)
        assert len(without_size) >= len(with_size)

    def test_combined_size_and_price_filters(self):
        results = search_listings("jeans", size="M", max_price=35.0)
        assert all(item["price"] <= 35.0 for item in results)
        assert all("m" in item["size"].lower() for item in results)

    def test_results_sorted_by_relevance(self):
        # a query with two keywords — items matching both should score higher
        # and therefore appear before items matching only one
        results = search_listings("vintage denim jacket")
        assert len(results) > 1
        # just verify the list is in non-increasing score order by checking
        # the first result's searchable text contains more query keywords
        # than a random later result (pragmatic proxy for sort correctness)
        def keyword_hits(item: dict, keywords: set) -> int:
            text = " ".join([
                item["title"], item["description"],
                item["category"], " ".join(item["style_tags"]),
            ]).lower()
            return sum(1 for kw in keywords if kw in text)

        keywords = {"vintage", "denim", "jacket"}
        scores = [keyword_hits(r, keywords) for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_result_has_all_required_fields(self):
        required = {
            "id", "title", "description", "category", "style_tags",
            "size", "condition", "price", "colors", "brand", "platform",
        }
        results = search_listings("tee")
        assert len(results) > 0
        for item in results:
            assert required.issubset(item.keys())

    def test_empty_description_returns_empty_list(self):
        # no keywords → every listing scores 0 → nothing returned
        results = search_listings("")
        assert results == []

    def test_unmatched_keyword_only_returns_empty(self):
        results = search_listings("zzzznotaword")
        assert results == []


# ── suggest_outfit ────────────────────────────────────────────────────────────

class TestSuggestOutfit:
    def test_returns_string_with_populated_wardrobe(self):
        mock_client = _make_mock_client("Pair with jeans and boots.")
        with patch("tools._get_groq_client", return_value=mock_client):
            result = suggest_outfit(new_item=SAMPLE_ITEM, wardrobe=POPULATED_WARDROBE)
        assert isinstance(result, str)

    def test_returns_non_empty_string_with_populated_wardrobe(self):
        mock_client = _make_mock_client("Pair with jeans and boots.")
        with patch("tools._get_groq_client", return_value=mock_client):
            result = suggest_outfit(new_item=SAMPLE_ITEM, wardrobe=POPULATED_WARDROBE)
        assert len(result.strip()) > 0

    def test_returns_non_empty_string_with_empty_wardrobe(self):
        mock_client = _make_mock_client("Great with high-waisted trousers.")
        with patch("tools._get_groq_client", return_value=mock_client):
            result = suggest_outfit(new_item=SAMPLE_ITEM, wardrobe=EMPTY_WARDROBE)
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_empty_wardrobe_does_not_raise(self):
        mock_client = _make_mock_client("General styling advice here.")
        with patch("tools._get_groq_client", return_value=mock_client):
            try:
                suggest_outfit(new_item=SAMPLE_ITEM, wardrobe=EMPTY_WARDROBE)
            except Exception as e:
                pytest.fail(f"suggest_outfit raised with empty wardrobe: {e}")

    def test_populated_wardrobe_prompt_includes_item_names(self):
        # verify that wardrobe item names are passed into the LLM prompt
        mock_client = _make_mock_client("Outfit suggestion.")
        with patch("tools._get_groq_client", return_value=mock_client):
            suggest_outfit(new_item=SAMPLE_ITEM, wardrobe=POPULATED_WARDROBE)
        call_args = mock_client.chat.completions.create.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "Baggy straight-leg jeans, dark wash" in prompt
        assert "Black combat boots" in prompt

    def test_empty_wardrobe_prompt_does_not_list_items(self):
        # general-styling prompt should not contain the populated-wardrobe header
        mock_client = _make_mock_client("General advice.")
        with patch("tools._get_groq_client", return_value=mock_client):
            suggest_outfit(new_item=SAMPLE_ITEM, wardrobe=EMPTY_WARDROBE)
        call_args = mock_client.chat.completions.create.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "wardrobe includes" not in prompt.lower()

    def test_item_title_appears_in_prompt(self):
        mock_client = _make_mock_client("Outfit suggestion.")
        with patch("tools._get_groq_client", return_value=mock_client):
            suggest_outfit(new_item=SAMPLE_ITEM, wardrobe=POPULATED_WARDROBE)
        call_args = mock_client.chat.completions.create.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert SAMPLE_ITEM["title"] in prompt

    def test_missing_items_key_does_not_crash(self):
        # wardrobe with no 'items' key at all — should behave like empty wardrobe
        mock_client = _make_mock_client("General advice.")
        with patch("tools._get_groq_client", return_value=mock_client):
            try:
                result = suggest_outfit(new_item=SAMPLE_ITEM, wardrobe={})
            except Exception as e:
                pytest.fail(f"suggest_outfit raised with missing 'items' key: {e}")


# ── create_fit_card ───────────────────────────────────────────────────────────

class TestCreateFitCard:
    OUTFIT = "Pair with dark jeans and chunky boots for a grunge look."

    def test_empty_outfit_returns_error_string(self):
        result = create_fit_card(outfit="", new_item=SAMPLE_ITEM)
        assert "Could not generate a fit card" in result

    def test_whitespace_outfit_returns_error_string(self):
        result = create_fit_card(outfit="   ", new_item=SAMPLE_ITEM)
        assert "Could not generate a fit card" in result

    def test_empty_outfit_does_not_raise(self):
        try:
            create_fit_card(outfit="", new_item=SAMPLE_ITEM)
        except Exception as e:
            pytest.fail(f"create_fit_card raised on empty outfit: {e}")

    def test_whitespace_outfit_does_not_raise(self):
        try:
            create_fit_card(outfit="\n\t  ", new_item=SAMPLE_ITEM)
        except Exception as e:
            pytest.fail(f"create_fit_card raised on whitespace outfit: {e}")

    def test_empty_outfit_no_llm_call(self):
        # guard should short-circuit before hitting the LLM
        mock_client = _make_mock_client("Should not be called.")
        with patch("tools._get_groq_client", return_value=mock_client):
            create_fit_card(outfit="", new_item=SAMPLE_ITEM)
        mock_client.chat.completions.create.assert_not_called()

    def test_valid_outfit_returns_string(self):
        mock_client = _make_mock_client("thrifted this tee for $22 on depop 🖤")
        with patch("tools._get_groq_client", return_value=mock_client):
            result = create_fit_card(outfit=self.OUTFIT, new_item=SAMPLE_ITEM)
        assert isinstance(result, str)

    def test_valid_outfit_returns_non_empty_string(self):
        mock_client = _make_mock_client("thrifted this tee for $22 on depop 🖤")
        with patch("tools._get_groq_client", return_value=mock_client):
            result = create_fit_card(outfit=self.OUTFIT, new_item=SAMPLE_ITEM)
        assert len(result.strip()) > 0

    def test_prompt_includes_item_title(self):
        mock_client = _make_mock_client("caption here")
        with patch("tools._get_groq_client", return_value=mock_client):
            create_fit_card(outfit=self.OUTFIT, new_item=SAMPLE_ITEM)
        prompt = mock_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        assert SAMPLE_ITEM["title"] in prompt

    def test_prompt_includes_price(self):
        mock_client = _make_mock_client("caption here")
        with patch("tools._get_groq_client", return_value=mock_client):
            create_fit_card(outfit=self.OUTFIT, new_item=SAMPLE_ITEM)
        prompt = mock_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        assert str(SAMPLE_ITEM["price"]) in prompt

    def test_prompt_includes_platform(self):
        mock_client = _make_mock_client("caption here")
        with patch("tools._get_groq_client", return_value=mock_client):
            create_fit_card(outfit=self.OUTFIT, new_item=SAMPLE_ITEM)
        prompt = mock_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        assert SAMPLE_ITEM["platform"] in prompt

    def test_uses_higher_temperature_than_suggest_outfit(self):
        mock_client = _make_mock_client("caption here")
        with patch("tools._get_groq_client", return_value=mock_client):
            create_fit_card(outfit=self.OUTFIT, new_item=SAMPLE_ITEM)
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["temperature"] > 0.7


# ── Failure mode tests (one per row in planning.md Error Handling table) ──────

def test_failure_mode_search_listings_no_match():
    # Failure mode: no listings match the query.
    # Tool must return [] and must not raise — the agent sets session["error"] upstream.
    results = search_listings("designer ballgown", size="XXS", max_price=5.0)
    assert results == [], "Expected empty list when no listings match, not an exception"


def test_failure_mode_suggest_outfit_empty_wardrobe():
    # Failure mode: wardrobe['items'] is empty.
    # Tool must NOT exit early — it calls the LLM with a general-styling prompt
    # and returns a non-empty string so the agent can continue to create_fit_card.
    mock_client = _make_mock_client("Try pairing with high-waisted trousers and loafers.")
    with patch("tools._get_groq_client", return_value=mock_client):
        result = suggest_outfit(new_item=SAMPLE_ITEM, wardrobe={"items": []})
    assert isinstance(result, str) and len(result.strip()) > 0, (
        "Expected non-empty string from suggest_outfit when wardrobe is empty"
    )
    mock_client.chat.completions.create.assert_called_once()


def test_failure_mode_create_fit_card_missing_outfit():
    # Failure mode: outfit string is empty or missing.
    # Tool must return the error message string without raising — never None, never an exception.
    result = create_fit_card(outfit="", new_item=SAMPLE_ITEM)
    assert result == "Could not generate a fit card: outfit description is missing.", (
        f"Expected exact error message string, got: {result!r}"
    )
