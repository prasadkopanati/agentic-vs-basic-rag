"""Unit tests for pure-logic helpers in scripts/generate_carousel.py.

No I/O, no PDF rendering. Tests cover data extraction and text helpers.
"""

from __future__ import annotations

import pytest

import scripts.generate_carousel as _carousel_mod
from scripts.generate_carousel import (
    THEMES,
    _build_query_slide_data,
    _compute_flow_boxes,
    _format_score,
    _pick_carousel_queries,
    _pick_hook_query,
    _retry_label,
    _screenshot_filename,
    _slide7_step_labels,
    _wrap_text,
    apply_theme,
    extract_slide8_rows,
    strip_markdown,
    truncate,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_entry(query_id: str, basic: float, agentic: float, error: bool = False) -> dict:
    """Build a minimal session entry for testing."""
    entry = {
        "query_id": query_id,
        "query_text": f"Question {query_id}",
        "basic_score": {"composite": basic, "profile": "compliance_grade", "dimensions": {}},
        "agentic_score": {"composite": agentic, "profile": "compliance_grade", "dimensions": {}},
        "basic_hallucination": {"faithfulness_score": None, "has_warning": None, "claims": []},
        "agentic_hallucination": {"faithfulness_score": None, "has_warning": None, "claims": []},
        "basic": {"answer": "basic ans", "retry_count": 0, "grader_scores": []},
        "agentic": {"answer": "agentic ans", "retry_count": 1, "grader_scores": [0.8]},
    }
    if error:
        entry["error"] = "LLM timeout"
    return entry


def _make_session(*entries) -> dict:
    return {"queries": list(entries), "query_count": len(entries)}


# ---------------------------------------------------------------------------
# truncate
# ---------------------------------------------------------------------------


class TestTruncate:
    def test_short_text_unchanged(self):
        assert truncate("hello", 10) == "hello"

    def test_text_at_limit_unchanged(self):
        assert truncate("hello", 5) == "hello"

    def test_text_over_limit_truncated(self):
        result = truncate("hello world", 8)
        assert result == "hello w…"

    def test_truncated_length_equals_max(self):
        result = truncate("abcdefghij", 6)
        assert len(result) == 6

    def test_truncated_ends_with_ellipsis(self):
        result = truncate("abcdefghij", 6)
        assert result.endswith("…")

    def test_empty_string_unchanged(self):
        assert truncate("", 10) == ""

    def test_max_one_returns_ellipsis(self):
        result = truncate("abc", 1)
        assert result == "…"


# ---------------------------------------------------------------------------
# _format_score
# ---------------------------------------------------------------------------


class TestFormatScore:
    def test_rounds_to_two_decimals(self):
        assert _format_score(0.823) == "0.82"

    def test_zero(self):
        assert _format_score(0.0) == "0.00"

    def test_one(self):
        assert _format_score(1.0) == "1.00"

    def test_rounds_up(self):
        assert _format_score(0.999) == "1.00"

    def test_half(self):
        assert _format_score(0.5) == "0.50"


# ---------------------------------------------------------------------------
# _pick_carousel_queries
# ---------------------------------------------------------------------------


class TestPickCarouselQueries:
    def test_returns_top_n_by_score_gap(self):
        entries = [
            _make_entry("Q1", basic=0.8, agentic=0.82),  # gap 0.02
            _make_entry("Q2", basic=0.4, agentic=0.90),  # gap 0.50
            _make_entry("Q3", basic=0.5, agentic=0.95),  # gap 0.45
        ]
        session = _make_session(*entries)
        result = _pick_carousel_queries(session, n=2)
        assert [r["query_id"] for r in result] == ["Q2", "Q3"]

    def test_n_larger_than_queries_returns_all(self):
        entries = [_make_entry("Q1", 0.5, 0.8), _make_entry("Q2", 0.4, 0.9)]
        session = _make_session(*entries)
        assert len(_pick_carousel_queries(session, n=10)) == 2

    def test_excludes_errored_entries(self):
        entries = [
            _make_entry("Q1", 0.3, 0.95),
            _make_entry("Q2", 0.1, 0.99, error=True),
        ]
        session = _make_session(*entries)
        result = _pick_carousel_queries(session, n=5)
        assert len(result) == 1
        assert result[0]["query_id"] == "Q1"

    def test_descending_gap_order(self):
        entries = [
            _make_entry("Q1", 0.6, 0.7),   # gap 0.10
            _make_entry("Q2", 0.5, 0.9),   # gap 0.40
            _make_entry("Q3", 0.3, 0.85),  # gap 0.55
        ]
        session = _make_session(*entries)
        result = _pick_carousel_queries(session, n=3)
        gaps = [r["agentic_score"]["composite"] - r["basic_score"]["composite"] for r in result]
        assert gaps == sorted(gaps, reverse=True)

    def test_negative_gap_entries_included_last(self):
        entries = [
            _make_entry("Q1", 0.9, 0.7),  # gap -0.20 (basic wins)
            _make_entry("Q2", 0.4, 0.9),  # gap +0.50
        ]
        session = _make_session(*entries)
        result = _pick_carousel_queries(session, n=2)
        assert result[0]["query_id"] == "Q2"
        assert result[1]["query_id"] == "Q1"

    def test_empty_session_returns_empty(self):
        assert _pick_carousel_queries({"queries": []}, n=5) == []


# ---------------------------------------------------------------------------
# extract_slide8_rows
# ---------------------------------------------------------------------------


class TestExtractSlide8Rows:
    def test_returns_one_row_per_non_errored_query(self):
        entries = [_make_entry("Q1", 0.6, 0.85), _make_entry("Q2", 0.4, 0.90)]
        rows = extract_slide8_rows(_make_session(*entries))
        assert len(rows) == 2

    def test_row_has_required_keys(self):
        entries = [_make_entry("Q1", 0.6, 0.85)]
        row = extract_slide8_rows(_make_session(*entries))[0]
        assert set(row.keys()) == {"query_id", "basic_score", "agentic_score"}

    def test_scores_extracted_correctly(self):
        entries = [_make_entry("Q3", 0.43, 0.81)]
        row = extract_slide8_rows(_make_session(*entries))[0]
        assert row["basic_score"] == pytest.approx(0.43)
        assert row["agentic_score"] == pytest.approx(0.81)

    def test_query_id_preserved(self):
        entries = [_make_entry("Q7", 0.5, 0.7)]
        assert extract_slide8_rows(_make_session(*entries))[0]["query_id"] == "Q7"

    def test_errored_entries_excluded(self):
        entries = [
            _make_entry("Q1", 0.5, 0.8),
            _make_entry("Q2", 0.4, 0.9, error=True),
        ]
        rows = extract_slide8_rows(_make_session(*entries))
        assert len(rows) == 1
        assert rows[0]["query_id"] == "Q1"

    def test_preserves_order(self):
        entries = [_make_entry(f"Q{i}", 0.5, 0.7) for i in range(1, 6)]
        rows = extract_slide8_rows(_make_session(*entries))
        assert [r["query_id"] for r in rows] == [f"Q{i}" for i in range(1, 6)]


# ---------------------------------------------------------------------------
# _retry_label
# ---------------------------------------------------------------------------


class TestRetryLabel:
    def test_zero_returns_empty(self):
        assert _retry_label(0) == ""

    def test_one_retry_singular(self):
        label = _retry_label(1)
        assert "1" in label
        assert "retry" in label.lower()

    def test_two_retries_plural(self):
        label = _retry_label(2)
        assert "2" in label
        assert "retries" in label.lower()

    def test_six_retries(self):
        label = _retry_label(6)
        assert "6" in label

    def test_negative_returns_empty(self):
        assert _retry_label(-1) == ""


# ---------------------------------------------------------------------------
# _wrap_text
# ---------------------------------------------------------------------------


class TestWrapText:
    def _char_width_fn(self, chars_per_line: int):
        """Mock width function: each character costs 1 unit, max is chars_per_line."""
        return lambda s: float(len(s))

    def test_short_text_is_one_line(self):
        lines = _wrap_text("hello world", max_width=100.0, font_name="Helvetica", font_size=24, _width_fn=lambda s: float(len(s)))
        assert lines == ["hello world"]

    def test_long_text_wraps(self):
        # With width_fn that counts chars, max_width=10 forces wrapping
        text = "one two three four five"
        lines = _wrap_text(text, max_width=10.0, font_name="Helvetica", font_size=24, _width_fn=lambda s: float(len(s)))
        assert len(lines) > 1

    def test_each_line_fits_within_max_width(self):
        text = "the quick brown fox jumps over the lazy dog and keeps running far"
        max_w = 15.0
        lines = _wrap_text(text, max_width=max_w, font_name="Helvetica", font_size=24, _width_fn=lambda s: float(len(s)))
        for line in lines:
            assert len(line) <= max_w + 1  # allow for the last word that may be just at limit

    def test_reconstructed_text_has_same_words(self):
        text = "alpha beta gamma delta epsilon zeta"
        lines = _wrap_text(text, max_width=12.0, font_name="Helvetica", font_size=24, _width_fn=lambda s: float(len(s)))
        assert " ".join(lines) == text

    def test_empty_string_returns_empty_list(self):
        lines = _wrap_text("", max_width=100.0, font_name="Helvetica", font_size=24, _width_fn=lambda s: float(len(s)))
        assert lines == []

    def test_single_long_word_placed_alone(self):
        # A single word longer than max_width still goes on its own line
        lines = _wrap_text("superlongword", max_width=5.0, font_name="Helvetica", font_size=24, _width_fn=lambda s: float(len(s)))
        assert len(lines) == 1
        assert lines[0] == "superlongword"


# ---------------------------------------------------------------------------
# _build_query_slide_data
# ---------------------------------------------------------------------------


def _make_full_entry(
    query_id="Q3",
    query_text="What triggers a SAR?",
    basic_answer="Basic says X.",
    agentic_answer="Agentic says Y.",
    basic_score=0.55,
    agentic_score=0.88,
    retry_count=2,
    has_warning=True,
):
    return {
        "query_id": query_id,
        "query_text": query_text,
        "basic": {"answer": basic_answer, "retry_count": 0, "grader_scores": []},
        "agentic": {"answer": agentic_answer, "retry_count": retry_count, "grader_scores": [0.8]},
        "basic_score": {"composite": basic_score, "profile": "compliance_grade", "dimensions": {}},
        "agentic_score": {"composite": agentic_score, "profile": "compliance_grade", "dimensions": {}},
        "basic_hallucination": {"faithfulness_score": 0.5, "has_warning": has_warning, "claims": []},
        "agentic_hallucination": {"faithfulness_score": 1.0, "has_warning": False, "claims": []},
    }


class TestBuildQuerySlideData:
    def test_has_required_keys(self):
        data = _build_query_slide_data(_make_full_entry())
        required = {
            "query_id", "query_text",
            "basic_answer", "basic_score", "basic_warning",
            "agentic_answer", "agentic_score", "agentic_retry_count",
        }
        assert required <= set(data.keys())

    def test_query_id_preserved(self):
        data = _build_query_slide_data(_make_full_entry(query_id="Q7"))
        assert data["query_id"] == "Q7"

    def test_query_text_truncated_at_120(self):
        long_query = "A" * 200
        data = _build_query_slide_data(_make_full_entry(query_text=long_query))
        assert len(data["query_text"]) == 120
        assert data["query_text"].endswith("…")

    def test_short_query_text_unchanged(self):
        data = _build_query_slide_data(_make_full_entry(query_text="Short question?"))
        assert data["query_text"] == "Short question?"

    def test_basic_answer_truncated_at_220(self):
        long_ans = "B" * 300
        data = _build_query_slide_data(_make_full_entry(basic_answer=long_ans))
        assert len(data["basic_answer"]) == 220
        assert data["basic_answer"].endswith("…")

    def test_agentic_answer_truncated_at_220(self):
        long_ans = "C" * 300
        data = _build_query_slide_data(_make_full_entry(agentic_answer=long_ans))
        assert len(data["agentic_answer"]) == 220

    def test_scores_extracted_correctly(self):
        data = _build_query_slide_data(_make_full_entry(basic_score=0.43, agentic_score=0.91))
        assert data["basic_score"] == pytest.approx(0.43)
        assert data["agentic_score"] == pytest.approx(0.91)

    def test_retry_count_extracted(self):
        data = _build_query_slide_data(_make_full_entry(retry_count=3))
        assert data["agentic_retry_count"] == 3

    def test_basic_warning_extracted(self):
        data = _build_query_slide_data(_make_full_entry(has_warning=True))
        assert data["basic_warning"] is True

    def test_basic_warning_false(self):
        data = _build_query_slide_data(_make_full_entry(has_warning=False))
        assert data["basic_warning"] is False


# ---------------------------------------------------------------------------
# _pick_hook_query
# ---------------------------------------------------------------------------


def _make_hook_entry(query_id, basic_score, has_warning, error=False):
    entry = {
        "query_id": query_id,
        "query_text": f"Question {query_id}",
        "basic": {"answer": f"Basic answer for {query_id}", "retry_count": 0, "grader_scores": []},
        "agentic": {"answer": "agentic ans", "retry_count": 0, "grader_scores": []},
        "basic_score": {"composite": basic_score, "profile": "compliance_grade", "dimensions": {}},
        "agentic_score": {"composite": 0.9, "profile": "compliance_grade", "dimensions": {}},
        "basic_hallucination": {
            "faithfulness_score": 0.5 if has_warning else 1.0,
            "has_warning": has_warning,
            "claims": [],
        },
        "agentic_hallucination": {"faithfulness_score": 1.0, "has_warning": False, "claims": []},
    }
    if error:
        entry["error"] = "LLM timeout"
    return entry


class TestPickHookQuery:
    def test_prefers_warned_query_over_higher_scoring_clean(self):
        session = {"queries": [
            _make_hook_entry("Q1", basic_score=0.80, has_warning=False),  # high score, no warning
            _make_hook_entry("Q2", basic_score=0.45, has_warning=True),   # lower score, warning
        ]}
        hook = _pick_hook_query(session)
        assert hook["query_id"] == "Q2"

    def test_among_warned_picks_lowest_score(self):
        session = {"queries": [
            _make_hook_entry("Q1", basic_score=0.55, has_warning=True),
            _make_hook_entry("Q2", basic_score=0.40, has_warning=True),
            _make_hook_entry("Q3", basic_score=0.70, has_warning=True),
        ]}
        hook = _pick_hook_query(session)
        assert hook["query_id"] == "Q2"

    def test_fallback_to_lowest_score_when_no_warnings(self):
        session = {"queries": [
            _make_hook_entry("Q1", basic_score=0.75, has_warning=False),
            _make_hook_entry("Q2", basic_score=0.50, has_warning=False),
            _make_hook_entry("Q3", basic_score=0.60, has_warning=False),
        ]}
        hook = _pick_hook_query(session)
        assert hook["query_id"] == "Q2"

    def test_warned_wins_even_if_score_higher_than_unwarneds(self):
        session = {"queries": [
            _make_hook_entry("Q1", basic_score=0.30, has_warning=False),  # lowest score but no warning
            _make_hook_entry("Q2", basic_score=0.65, has_warning=True),   # warned, higher score
        ]}
        hook = _pick_hook_query(session)
        assert hook["query_id"] == "Q2"

    def test_skips_errored_entries(self):
        session = {"queries": [
            _make_hook_entry("Q1", basic_score=0.20, has_warning=True, error=True),
            _make_hook_entry("Q2", basic_score=0.55, has_warning=False),
        ]}
        hook = _pick_hook_query(session)
        assert hook["query_id"] == "Q2"

    def test_single_entry_returned(self):
        session = {"queries": [_make_hook_entry("Q1", basic_score=0.75, has_warning=False)]}
        assert _pick_hook_query(session)["query_id"] == "Q1"

    def test_none_warning_treated_as_no_warning(self):
        # has_warning=None (checker unavailable) should not count as warned
        entry = _make_hook_entry("Q1", basic_score=0.45, has_warning=False)
        entry["basic_hallucination"]["has_warning"] = None
        session = {"queries": [
            entry,
            _make_hook_entry("Q2", basic_score=0.60, has_warning=False),
        ]}
        # Neither is warned; fallback picks lowest → Q1
        assert _pick_hook_query(session)["query_id"] == "Q1"


# ---------------------------------------------------------------------------
# _slide7_step_labels
# ---------------------------------------------------------------------------


class TestSlide7StepLabels:
    def test_returns_tuple_of_two_lists(self):
        result = _slide7_step_labels()
        assert isinstance(result, tuple) and len(result) == 2

    def test_basic_has_three_steps(self):
        basic, _ = _slide7_step_labels()
        assert len(basic) == 3

    def test_agentic_has_more_steps_than_basic(self):
        basic, agentic = _slide7_step_labels()
        assert len(agentic) > len(basic)

    def test_basic_contains_generate(self):
        basic, _ = _slide7_step_labels()
        assert "Generate" in basic

    def test_agentic_contains_rewrite_and_grade(self):
        _, agentic = _slide7_step_labels()
        assert "Rewrite" in agentic
        assert "Grade" in agentic

    def test_both_start_with_query(self):
        basic, agentic = _slide7_step_labels()
        assert basic[0] == "Query"
        assert agentic[0] == "Query"

    def test_both_end_with_generate(self):
        basic, agentic = _slide7_step_labels()
        assert basic[-1] == "Generate"
        assert agentic[-1] == "Generate"


# ---------------------------------------------------------------------------
# _compute_flow_boxes
# ---------------------------------------------------------------------------


class TestComputeFlowBoxes:
    def test_returns_one_box_per_step(self):
        boxes = _compute_flow_boxes(["A", "B", "C"], col_x=100, col_top=800, col_w=300)
        assert len(boxes) == 3

    def test_empty_steps_returns_empty_list(self):
        assert _compute_flow_boxes([], col_x=100, col_top=800, col_w=300) == []

    def test_boxes_have_required_keys(self):
        boxes = _compute_flow_boxes(["A"], col_x=100, col_top=800, col_w=300)
        assert set(boxes[0].keys()) == {"x", "y", "w", "h", "label"}

    def test_labels_match_steps(self):
        steps = ["Query", "Retrieve", "Generate"]
        boxes = _compute_flow_boxes(steps, col_x=100, col_top=800, col_w=300)
        assert [b["label"] for b in boxes] == steps

    def test_boxes_stack_downward(self):
        boxes = _compute_flow_boxes(["A", "B"], col_x=100, col_top=800, col_w=300, box_h=50, gap=20)
        assert boxes[1]["y"] < boxes[0]["y"]

    def test_boxes_all_same_width(self):
        boxes = _compute_flow_boxes(["A", "B", "C"], col_x=100, col_top=800, col_w=300)
        assert all(b["w"] == 300 for b in boxes)

    def test_boxes_all_same_height(self):
        boxes = _compute_flow_boxes(["A", "B", "C"], col_x=100, col_top=800, col_w=300, box_h=60)
        assert all(b["h"] == 60 for b in boxes)

    def test_col_x_preserved(self):
        boxes = _compute_flow_boxes(["A", "B"], col_x=200, col_top=800, col_w=300)
        assert all(b["x"] == 200 for b in boxes)

    def test_gap_increases_spacing(self):
        boxes_small_gap = _compute_flow_boxes(["A", "B"], col_x=0, col_top=800, col_w=300, box_h=50, gap=10)
        boxes_large_gap = _compute_flow_boxes(["A", "B"], col_x=0, col_top=800, col_w=300, box_h=50, gap=30)
        assert boxes_large_gap[1]["y"] < boxes_small_gap[1]["y"]

    def test_first_box_top_equals_col_top(self):
        boxes = _compute_flow_boxes(["A"], col_x=100, col_top=800, col_w=300, box_h=60)
        assert boxes[0]["y"] + boxes[0]["h"] == pytest.approx(800)


# ---------------------------------------------------------------------------
# _screenshot_filename
# ---------------------------------------------------------------------------


class TestScreenshotFilename:
    def test_first_page(self):
        assert _screenshot_filename(0) == "slide_01.png"

    def test_last_carousel_page(self):
        assert _screenshot_filename(7) == "slide_08.png"

    def test_middle_page(self):
        assert _screenshot_filename(4) == "slide_05.png"

    def test_double_digit(self):
        assert _screenshot_filename(9) == "slide_10.png"

    def test_always_ends_with_png(self):
        for i in range(8):
            assert _screenshot_filename(i).endswith(".png")


# ---------------------------------------------------------------------------
# strip_markdown
# ---------------------------------------------------------------------------


class TestStripMarkdown:
    def test_plain_text_unchanged(self):
        assert strip_markdown("hello world") == "hello world"

    def test_bold_asterisks_removed(self):
        assert strip_markdown("**hello**") == "hello"

    def test_bold_underscores_removed(self):
        assert strip_markdown("__hello__") == "hello"

    def test_italic_asterisks_removed(self):
        assert strip_markdown("*hello*") == "hello"

    def test_h1_heading_stripped(self):
        assert strip_markdown("# Title") == "Title"

    def test_h2_heading_stripped(self):
        assert strip_markdown("## Section") == "Section"

    def test_h3_heading_stripped(self):
        assert strip_markdown("### Sub") == "Sub"

    def test_inline_bold_in_sentence(self):
        result = strip_markdown("The **$500M threshold** applies here.")
        assert "**" not in result
        assert "$500M threshold" in result

    def test_heading_in_multiline(self):
        text = "## Summary\nSome text."
        result = strip_markdown(text)
        assert "##" not in result
        assert "Summary" in result

    def test_mixed_markdown_cleaned(self):
        text = "## Key Finding\n**Important**: credit unions *must* comply."
        result = strip_markdown(text)
        assert "##" not in result
        assert "**" not in result
        assert "*" not in result
        assert "Important" in result
        assert "must" in result


# ---------------------------------------------------------------------------
# Theme system
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = {"BG", "FG", "PANEL", "PANEL_FG", "ACCENT_A", "ACCENT_B", "MUTED", "WARNING", "BADGE_FG"}
_KNOWN_THEMES = {"default", "warm_editorial", "dark_modern"}


class TestThemesDict:
    def test_all_expected_themes_present(self):
        assert _KNOWN_THEMES.issubset(set(THEMES))

    def test_each_theme_has_required_keys(self):
        for name, theme in THEMES.items():
            missing = _REQUIRED_KEYS - set(theme)
            assert not missing, f"Theme '{name}' missing keys: {missing}"

    def test_each_color_is_rgb_triple(self):
        for name, theme in THEMES.items():
            for key, value in theme.items():
                assert isinstance(value, tuple) and len(value) == 3, (
                    f"Theme '{name}' key '{key}' must be a 3-tuple, got {value!r}"
                )

    def test_each_channel_in_unit_range(self):
        for name, theme in THEMES.items():
            for key, (r, g, b) in theme.items():
                assert 0.0 <= r <= 1.0 and 0.0 <= g <= 1.0 and 0.0 <= b <= 1.0, (
                    f"Theme '{name}' key '{key}' channel out of [0,1]: ({r},{g},{b})"
                )

    def test_default_and_dark_modern_are_dark(self):
        # BG luminance should be low for dark themes
        for name in ("default", "dark_modern"):
            r, g, b = THEMES[name]["BG"]
            luminance = 0.299 * r + 0.587 * g + 0.114 * b
            assert luminance < 0.3, f"Theme '{name}' BG is not dark (luminance={luminance:.3f})"

    def test_warm_editorial_has_light_bg(self):
        r, g, b = THEMES["warm_editorial"]["BG"]
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        assert luminance > 0.7, f"warm_editorial BG should be light (luminance={luminance:.3f})"

    def test_warm_editorial_has_dark_fg(self):
        r, g, b = THEMES["warm_editorial"]["FG"]
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        assert luminance < 0.3, f"warm_editorial FG should be dark (luminance={luminance:.3f})"


class TestApplyTheme:
    def setup_method(self):
        # Reset to default before every test so tests are independent
        apply_theme("default")

    def teardown_method(self):
        apply_theme("default")

    def test_apply_warm_editorial_changes_bg(self):
        apply_theme("warm_editorial")
        assert _carousel_mod.BG == THEMES["warm_editorial"]["BG"]

    def test_apply_dark_modern_changes_accent_a(self):
        apply_theme("dark_modern")
        assert _carousel_mod.ACCENT_A == THEMES["dark_modern"]["ACCENT_A"]

    def test_apply_default_restores_original_bg(self):
        apply_theme("dark_modern")
        apply_theme("default")
        assert _carousel_mod.BG == THEMES["default"]["BG"]

    def test_apply_theme_sets_all_globals(self):
        apply_theme("warm_editorial")
        t = THEMES["warm_editorial"]
        assert _carousel_mod.BG       == t["BG"]
        assert _carousel_mod.FG       == t["FG"]
        assert _carousel_mod.PANEL    == t["PANEL"]
        assert _carousel_mod.PANEL_FG == t["PANEL_FG"]
        assert _carousel_mod.ACCENT_A == t["ACCENT_A"]
        assert _carousel_mod.ACCENT_B == t["ACCENT_B"]
        assert _carousel_mod.MUTED    == t["MUTED"]
        assert _carousel_mod.WARNING  == t["WARNING"]
        assert _carousel_mod.BADGE_FG == t["BADGE_FG"]

    def test_unknown_theme_raises_key_error(self):
        with pytest.raises(KeyError):
            apply_theme("nonexistent_theme")

    def test_themes_are_independent(self):
        apply_theme("warm_editorial")
        warm_accent_a = _carousel_mod.ACCENT_A
        apply_theme("dark_modern")
        assert _carousel_mod.ACCENT_A != warm_accent_a
