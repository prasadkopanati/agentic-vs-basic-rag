#!/usr/bin/env python
"""Generate an 8-slide LinkedIn carousel PDF from a captured session JSON.

Usage:
    uv run python scripts/generate_carousel.py --session artifacts/session_20260527.json
    uv run python scripts/generate_carousel.py --session artifacts/session_20260527.json \
        --output artifacts/carousel.pdf
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Theme system (module-level — importable for testing)
# ---------------------------------------------------------------------------

PAGE_SIZE = (1080, 1080)  # 1080×1080 points (15×15 in at 72 dpi)

# Each theme maps semantic role names to (R, G, B) tuples in [0.0, 1.0].
# Role names:
#   BG        — slide background
#   FG        — primary text drawn on BG
#   PANEL     — card / blockquote fill
#   PANEL_FG  — text drawn inside panels
#   ACCENT_A  — agentic brand color (headers, badges, bars)
#   ACCENT_B  — basic brand color (headers, badges, bars)
#   MUTED     — secondary text, dividers, arrows
#   WARNING   — hallucination badge, error indicators, retry arrow
#   BADGE_FG  — score number text inside colored badges
THEMES: dict[str, dict] = {
    "default": {
        "BG":       (0.09, 0.12, 0.22),
        "FG":       (1.00, 1.00, 1.00),
        "PANEL":    (0.11, 0.15, 0.28),
        "PANEL_FG": (0.85, 0.88, 0.93),
        "ACCENT_A": (0.13, 0.70, 0.67),
        "ACCENT_B": (1.00, 0.75, 0.10),
        "MUTED":    (0.55, 0.60, 0.70),
        "WARNING":  (0.90, 0.20, 0.20),
        "BADGE_FG": (0.09, 0.12, 0.22),
    },
    # Inspired by warm editorial infographic style:
    # cream background, rust/terracotta accents, dark text, white cards.
    "warm_editorial": {
        "BG":       (1.00, 0.96, 0.92),
        "FG":       (0.10, 0.07, 0.04),
        "PANEL":    (1.00, 1.00, 1.00),
        "PANEL_FG": (0.30, 0.22, 0.16),
        "ACCENT_A": (0.78, 0.29, 0.10),
        "ACCENT_B": (0.83, 0.63, 0.28),
        "MUTED":    (0.48, 0.42, 0.35),
        "WARNING":  (0.78, 0.29, 0.10),
        "BADGE_FG": (1.00, 1.00, 1.00),
    },
    # Inspired by dark-mode tech card style:
    # deep charcoal background, coral agentic, violet basic, cool greys.
    "dark_modern": {
        "BG":       (0.05, 0.07, 0.09),
        "FG":       (1.00, 1.00, 1.00),
        "PANEL":    (0.10, 0.13, 0.21),
        "PANEL_FG": (0.91, 0.92, 0.94),
        "ACCENT_A": (0.91, 0.38, 0.23),
        "ACCENT_B": (0.42, 0.39, 1.00),
        "MUTED":    (0.53, 0.57, 0.64),
        "WARNING":  (1.00, 0.27, 0.27),
        "BADGE_FG": (1.00, 1.00, 1.00),
    },
}

# Active theme globals — all render functions reference these names.
# Call apply_theme(name) before rendering to switch the active palette.
BG       = THEMES["default"]["BG"]
FG       = THEMES["default"]["FG"]
PANEL    = THEMES["default"]["PANEL"]
PANEL_FG = THEMES["default"]["PANEL_FG"]
ACCENT_A = THEMES["default"]["ACCENT_A"]
ACCENT_B = THEMES["default"]["ACCENT_B"]
MUTED    = THEMES["default"]["MUTED"]
WARNING  = THEMES["default"]["WARNING"]
BADGE_FG = THEMES["default"]["BADGE_FG"]


def apply_theme(name: str) -> None:
    """Reassign module-level color globals to the named theme.

    Unknown names raise KeyError — call sites should catch if needed.
    """
    global BG, FG, PANEL, PANEL_FG, ACCENT_A, ACCENT_B, MUTED, WARNING, BADGE_FG
    t = THEMES[name]
    BG, FG, PANEL, PANEL_FG = t["BG"], t["FG"], t["PANEL"], t["PANEL_FG"]
    ACCENT_A, ACCENT_B = t["ACCENT_A"], t["ACCENT_B"]
    MUTED, WARNING, BADGE_FG = t["MUTED"], t["WARNING"], t["BADGE_FG"]


# Font sizes (points)
H1      = 52
H2      = 36
BODY    = 24
CAPTION = 18

MARGIN = 60  # page margin on all sides

SLIDE7_BULLETS = [
    "Grounded Answers with Citations",
    "Compliance Ready",
    "Iterative Self-Correction",
    "Full Audit Trail",
]

SLIDE7_WHY_NOW = [
    "Regulators Now Require Explainable AI Decisions",
    "LLM Hallucinations Are Measurable — and Fixable",
]

# Per-slide assembly config for the hybrid carousel workflow.
# "full"       — PDF-rendered 1080×1080; embedded as-is.
# "screenshot" — App screenshot; centered on BG (never upscaled) with a title.
# "cta"        — Generated CTA slide; uses supplement image + CTA text.
HYBRID_SLIDE_CONFIG = [
    {"type": "full",       "file": "slide_01.png"},
    {"type": "screenshot", "file": "slide_02.png", "title": "Introducing LLM-as-a-Judge RAG",                       "page": 2},
    {"type": "screenshot", "file": "slide_03.png", "title": "What a Typical Setup Looks Like?",                     "page": 3},
    {"type": "screenshot", "file": "slide_04.png", "title": "What additional Controls you get",                     "page": 4},
    {"type": "screenshot", "file": "slide_06.png", "title": "End to End Visibility into RAG pipeline is built-in",  "page": 5},
    {"type": "screenshot", "file": "slide_05.png", "title": "Granular and Overall Scores assist in sound judgement","page": 6},
    {"type": "full",       "file": "slide_07.png"},
    {"type": "cta",        "supplement": "slide_08-supplement.png",                                                  "page": 8},
]


# ---------------------------------------------------------------------------
# Pure helpers (exported for unit testing)
# ---------------------------------------------------------------------------


def strip_markdown(text: str) -> str:
    """Remove common Markdown syntax for plain-text display in the carousel."""
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)  # ATX headings
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text, flags=re.DOTALL)  # **bold**
    text = re.sub(r'__(.+?)__', r'\1', text, flags=re.DOTALL)  # __bold__
    text = re.sub(r'\*(.+?)\*', r'\1', text)  # *italic*
    return text.strip()


def truncate(text: str, max_chars: int) -> str:
    """Truncate text to max_chars, appending '…' if shortened."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def _format_score(score: float) -> str:
    """Format a composite score as a 2-decimal string, e.g. '0.82'."""
    return f"{score:.2f}"


def _pick_carousel_queries(session: dict, n: int = 5) -> list[dict]:
    """Return up to n queries sorted by largest (agentic − basic) score gap."""
    valid = [q for q in session["queries"] if "error" not in q]
    return sorted(
        valid,
        key=lambda q: (
            q["agentic_score"]["composite"] - q["basic_score"]["composite"]
        ),
        reverse=True,
    )[:n]


def extract_slide8_rows(session: dict) -> list[dict]:
    """Extract per-query score data for the Slide 8 score dashboard."""
    return [
        {
            "query_id": q["query_id"],
            "basic_score": q["basic_score"]["composite"],
            "agentic_score": q["agentic_score"]["composite"],
        }
        for q in session["queries"]
        if "error" not in q
    ]


def _retry_label(retry_count: int) -> str:
    """Return a retry indicator string, or empty string when count is zero."""
    if retry_count <= 0:
        return ""
    noun = "retry" if retry_count == 1 else "retries"
    return f"↺  {retry_count} {noun}"


def _wrap_text(
    text: str,
    max_width: float,
    font_name: str,
    font_size: float,
    *,
    _width_fn=None,
) -> list[str]:
    """Word-wrap text so each line's rendered width fits within max_width.

    _width_fn is injectable for unit tests; defaults to reportlab stringWidth.
    """
    if not text:
        return []
    if _width_fn is None:
        from reportlab.pdfbase.pdfmetrics import stringWidth
        _width_fn = lambda s: stringWidth(s, font_name, font_size)  # noqa: E731

    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip() if current else word
        if _width_fn(candidate) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word  # lone word may exceed max_width — placed as-is
    if current:
        lines.append(current)
    return lines


def _build_query_slide_data(entry: dict) -> dict:
    """Extract and normalise query slide data from a session entry dict."""
    return {
        "query_id": entry["query_id"],
        "query_text": truncate(entry["query_text"], 120),
        "basic_answer": truncate(strip_markdown(entry["basic"]["answer"]), 220),
        "basic_score": entry["basic_score"]["composite"],
        "basic_warning": entry["basic_hallucination"].get("has_warning"),
        "agentic_answer": truncate(strip_markdown(entry["agentic"]["answer"]), 220),
        "agentic_score": entry["agentic_score"]["composite"],
        "agentic_retry_count": entry["agentic"]["retry_count"],
    }


def _pick_hook_query(session: dict) -> dict:
    """Select the worst basic RAG result for Slide 1's hook.

    Priority 1: queries where has_warning is True, sorted by lowest composite score.
    Priority 2: fallback to lowest composite score across all valid queries.
    """
    valid = [q for q in session["queries"] if "error" not in q]
    if not valid:
        raise ValueError("No valid queries in session")
    warned = [q for q in valid if q["basic_hallucination"].get("has_warning") is True]
    pool = warned if warned else valid
    return min(pool, key=lambda q: q["basic_score"]["composite"])


def _screenshot_filename(page_idx: int) -> str:
    """Return the PNG filename for a zero-based page index: slide_01.png … slide_08.png."""
    return f"slide_{page_idx + 1:02d}.png"


def export_screenshots(
    pdf_path: str | Path,
    output_dir: str | Path,
    dpi: int = 72,
) -> list[Path]:
    """Render each page of *pdf_path* as a PNG into *output_dir*.

    Each run writes to its own directory so screenshots from different sessions
    are never overwritten. Returns the list of written file paths.
    """
    import fitz  # PyMuPDF — imported here so unit tests don't need it

    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    written: list[Path] = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(matrix=mat)
        out = output_dir / _screenshot_filename(i)
        pix.save(str(out))
        written.append(out)
    doc.close()
    return written


def _slide7_step_labels() -> tuple[list[str], list[str]]:
    """Return (basic_steps, agentic_steps) for the Slide 7 flow diagram."""
    return (
        ["Query", "Retrieve", "Generate"],
        ["Query", "Rewrite", "Retrieve", "Grade", "Route", "Generate"],
    )


def _compute_flow_boxes(
    steps: list[str],
    col_x: float,
    col_top: float,
    col_w: float,
    box_h: float = 54,
    gap: float = 18,
) -> list[dict]:
    """Return geometry for each box in a vertical flow column.

    Each dict has: x, y (bottom-left), w, h, label.
    Boxes are ordered top-to-bottom (first step has the highest y).
    """
    boxes = []
    y = col_top
    for label in steps:
        boxes.append({"x": col_x, "y": y - box_h, "w": col_w, "h": box_h, "label": label})
        y -= box_h + gap
    return boxes


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------


def _fill(c, color: tuple) -> None:
    c.setFillColorRGB(*color)


def _stroke(c, color: tuple) -> None:
    c.setStrokeColorRGB(*color)


def _bg(c) -> None:
    """Fill the entire page with the active theme background color."""
    W, H = PAGE_SIZE
    _fill(c, BG)
    c.rect(0, 0, W, H, fill=1, stroke=0)


def _page_number(c, num: int) -> None:
    W, _ = PAGE_SIZE
    _fill(c, MUTED)
    c.setFont("Helvetica", CAPTION)
    c.drawRightString(W - MARGIN, MARGIN - 4, str(num))


# ---------------------------------------------------------------------------
# Slide renderers
# ---------------------------------------------------------------------------


def _render_placeholder(c, page_num: int, label: str) -> None:
    """Placeholder slide: background with a centered label."""
    W, H = PAGE_SIZE
    _bg(c)
    _stroke(c, MUTED)
    c.setLineWidth(2)
    c.rect(MARGIN, MARGIN, W - 2 * MARGIN, H - 2 * MARGIN, fill=0, stroke=1)
    _fill(c, MUTED)
    c.setFont("Helvetica", H2)
    c.drawCentredString(W / 2, H / 2 - H2 / 2, label)
    _fill(c, MUTED)
    c.setFont("Helvetica", CAPTION)
    c.drawCentredString(W / 2, H / 2 - H2 / 2 - CAPTION - 12, "(coming in next tasks)")
    _page_number(c, page_num)


def _render_slide1(c, session: dict) -> None:
    """Slide 1: 'The Failure' hook — full-bleed background, dramatic contrast."""
    W, H = PAGE_SIZE
    _bg(c)

    hook = _pick_hook_query(session)
    has_warning = hook["basic_hallucination"].get("has_warning") is True
    basic_score = hook["basic_score"]["composite"]
    query_text = truncate(hook["query_text"], 80)
    answer_snippet = truncate(strip_markdown(hook["basic"]["answer"]), 180)

    # ── Statement (two lines, H1, centred) ──────────────────────────────────
    line1 = "RAG failed this Compliance"
    line2 = "Question at a Large Enterprise"
    stmt_y = H - MARGIN - H1
    _fill(c, FG)
    c.setFont("Helvetica-Bold", H1)
    c.drawCentredString(W / 2, stmt_y, line1)
    c.drawCentredString(W / 2, stmt_y - H1 - 10, line2)

    # ── Query label ─────────────────────────────────────────────────────────
    qlabel_y = stmt_y - H1 - 10 - H2 - 20
    _fill(c, MUTED)
    c.setFont("Helvetica", BODY)
    c.drawCentredString(W / 2, qlabel_y, f"Q: {query_text}")

    # ── Blockquote callout ───────────────────────────────────────────────────
    BQ_X = MARGIN + 40
    BQ_W = W - BQ_X - MARGIN
    LEADING = int(BODY * 1.38)
    lines = _wrap_text(answer_snippet, BQ_W - 24, "Helvetica", BODY)
    bq_lines = lines[:4]
    bq_content_h = len(bq_lines) * LEADING
    bq_pad = 20
    bq_h = bq_content_h + bq_pad * 2
    bq_top = qlabel_y - 28
    bq_bot = bq_top - bq_h

    # Subtle background fill for callout block
    _fill(c, PANEL)
    c.rect(BQ_X, bq_bot, BQ_W, bq_h, fill=1, stroke=0)
    # Left warning-color accent bar
    _fill(c, WARNING)
    c.rect(BQ_X, bq_bot, 6, bq_h, fill=1, stroke=0)
    # Answer text
    _fill(c, PANEL_FG)
    c.setFont("Helvetica", BODY)
    for i, line in enumerate(bq_lines):
        c.drawString(BQ_X + 22, bq_top - bq_pad - i * LEADING, line)

    # ── Badge (warning or score) ─────────────────────────────────────────────
    badge_label = "! Hallucination Detected" if has_warning else f"Score: {_format_score(basic_score)}"
    badge_top = bq_bot - 28
    badge_h = 46
    badge_bot = badge_top - badge_h
    _fill(c, WARNING)
    c.rect(MARGIN, badge_bot, W - 2 * MARGIN, badge_h, fill=1, stroke=0)
    _fill(c, (1.0, 1.0, 1.0))  # always white text on warning banner
    c.setFont("Helvetica-Bold", BODY)
    c.drawCentredString(W / 2, badge_bot + (badge_h - BODY) / 2 + 2, badge_label)

    # ── Curiosity hook at bottom ─────────────────────────────────────────────
    hook_y = MARGIN + CAPTION + 4
    _fill(c, ACCENT_A)
    c.setFont("Helvetica-Bold", CAPTION)
    c.drawCentredString(W / 2, hook_y, "Slide 2 → How agentic RAG answered it.")

    _page_number(c, 1)


def _draw_flow_box(c, box: dict, color: tuple) -> None:
    """Draw a single diagram box with rounded corners, colored border and label."""
    x, y, w, h, label = box["x"], box["y"], box["w"], box["h"], box["label"]
    _fill(c, PANEL)
    _stroke(c, color)
    c.setLineWidth(1.5)
    c.roundRect(x, y, w, h, 8, fill=1, stroke=1)
    _fill(c, color)
    c.setFont("Helvetica-Bold", BODY - 2)
    c.drawCentredString(x + w / 2, y + (h - (BODY - 2)) / 2, label)
    c.setLineWidth(1)


def _render_slide7_bullets(c) -> None:
    """Slide 7: Why LLM-as-a-Judge RAG? Why now? — two-section bullet layout."""
    W, H = PAGE_SIZE
    _bg(c)

    TITLE_SIZE = 44  # slightly smaller to fit the longer title on one line
    LINE_GAP = 28
    LINE_H = H2 + LINE_GAP
    SUB_GAP = 14   # gap between sub-header and its first bullet
    SECTION_GAP = 40  # gap between the two sections

    # Title
    title_y = H - MARGIN - TITLE_SIZE
    _fill(c, FG)
    c.setFont("Helvetica-Bold", TITLE_SIZE)
    c.drawCentredString(W / 2, title_y, "Why LLM-as-a-Judge RAG? Why now?")

    # Compute total block height so we can center it vertically
    all_bullets = SLIDE7_BULLETS + SLIDE7_WHY_NOW
    section1_h = len(SLIDE7_BULLETS) * LINE_H - LINE_GAP
    section2_h = len(SLIDE7_WHY_NOW) * LINE_H - LINE_GAP
    total_h = section1_h + SECTION_GAP + section2_h

    avail_top = title_y - TITLE_SIZE - 36
    avail_bot = MARGIN + CAPTION + 16
    avail_h = avail_top - avail_bot
    block_top = avail_bot + (avail_h + total_h) / 2

    DOT_X = MARGIN + 60
    TEXT_X = DOT_X + 28

    y = block_top

    # ── Section 1 ────────────────────────────────────────────────────────────
    for text in SLIDE7_BULLETS:
        _fill(c, ACCENT_A)
        c.circle(DOT_X, y + H2 * 0.35, 7, fill=1, stroke=0)
        _fill(c, FG)
        c.setFont("Helvetica-Bold", H2)
        c.drawString(TEXT_X, y, text)
        y -= LINE_H

    # ── Section 2 ────────────────────────────────────────────────────────────
    y += LINE_GAP   # undo trailing gap from last bullet
    y -= SECTION_GAP

    for text in SLIDE7_WHY_NOW:
        _fill(c, ACCENT_A)
        c.circle(DOT_X, y + H2 * 0.35, 7, fill=1, stroke=0)
        _fill(c, FG)
        c.setFont("Helvetica-Bold", H2)
        c.drawString(TEXT_X, y, text)
        y -= LINE_H

    _page_number(c, 7)


def _render_answer_panel(
    c,
    panel_color: tuple,
    label: str,
    answer: str,
    score: float,
    extra_label: str,
    panel_top: float,
    panel_bot: float,
) -> None:
    """Render one answer panel (basic or agentic) within its vertical bounds."""
    W, _ = PAGE_SIZE
    ACCENT_W = 8
    TEXT_X = MARGIN + ACCENT_W + 12
    text_w = W - TEXT_X - MARGIN
    LEADING = int(BODY * 1.38)

    # Accent bar — left edge in panel color
    _fill(c, panel_color)
    c.rect(MARGIN, panel_bot, ACCENT_W, panel_top - panel_bot, fill=1, stroke=0)

    # Pipeline label
    label_y = panel_top - CAPTION - 14
    _fill(c, panel_color)
    c.setFont("Helvetica-Bold", CAPTION)
    c.drawString(TEXT_X, label_y, label)

    # Answer snippet — word-wrapped, max 4 lines
    lines = _wrap_text(answer, text_w, "Helvetica", BODY)
    answer_y = label_y - LEADING
    _fill(c, FG)
    c.setFont("Helvetica", BODY)
    for i, line in enumerate(lines[:4]):
        c.drawString(TEXT_X, answer_y - i * LEADING, line)
    text_bottom = answer_y - min(len(lines), 4) * LEADING

    # Score badge — centred in the space below the text
    badge_w, badge_h = 116, 46
    space_below = text_bottom - panel_bot
    badge_y = panel_bot + max(8, (space_below - badge_h) / 2)
    _fill(c, panel_color)
    c.rect(TEXT_X, badge_y, badge_w, badge_h, fill=1, stroke=0)
    _fill(c, BADGE_FG)
    c.setFont("Helvetica-Bold", H2)
    c.drawCentredString(TEXT_X + badge_w / 2, badge_y + (badge_h - H2) / 2 + 2, _format_score(score))

    # Extra label (retry count / warning)
    if extra_label:
        _fill(c, MUTED)
        c.setFont("Helvetica", CAPTION)
        c.drawString(TEXT_X + badge_w + 14, badge_y + (badge_h - CAPTION) / 2 + 2, extra_label)


def _render_query_slide(
    c,
    slide_num: int,
    slide_data: dict,
    query_index: int,
    total_queries: int,
) -> None:
    """Render a query comparison slide (slides 2–6)."""
    W, H = PAGE_SIZE
    _bg(c)

    # ── Progress indicator ──────────────────────────────────────────────────
    progress_y = H - MARGIN - CAPTION + 4
    _fill(c, ACCENT_A)
    c.setFont("Helvetica-Bold", CAPTION)
    c.drawString(MARGIN, progress_y, f"Question {query_index} of {total_queries}")

    # ── Query text ──────────────────────────────────────────────────────────
    query_y = progress_y - CAPTION - 16
    _fill(c, FG)
    c.setFont("Helvetica-Bold", H2)
    c.drawString(MARGIN, query_y, slide_data["query_text"])

    # ── Divider below query ─────────────────────────────────────────────────
    div_y = query_y - 22
    _stroke(c, MUTED)
    c.setLineWidth(1)
    c.line(MARGIN, div_y, W - MARGIN, div_y)

    # ── Panel layout ────────────────────────────────────────────────────────
    content_top = div_y - 6
    content_bot = MARGIN + CAPTION + 10     # leave room for slide number
    panel_h = (content_top - content_bot) / 2
    mid_y = content_bot + panel_h

    # Mid-panel divider
    c.line(MARGIN, mid_y, W - MARGIN, mid_y)

    # Basic RAG panel (upper half)
    extra_basic = "! hallucination detected" if slide_data.get("basic_warning") else ""
    _render_answer_panel(
        c,
        panel_color=ACCENT_B,
        label="■  BASIC RAG",
        answer=slide_data["basic_answer"],
        score=slide_data["basic_score"],
        extra_label=extra_basic,
        panel_top=content_top,
        panel_bot=mid_y + 2,
    )

    # Agentic RAG panel (lower half)
    _render_answer_panel(
        c,
        panel_color=ACCENT_A,
        label="■  AGENTIC RAG",
        answer=slide_data["agentic_answer"],
        score=slide_data["agentic_score"],
        extra_label=_retry_label(slide_data["agentic_retry_count"]),
        panel_top=mid_y - 2,
        panel_bot=content_bot,
    )

    _page_number(c, slide_num)


def _render_slide8(c, session: dict) -> None:
    """Slide 8: Score dashboard — all queries, basic vs agentic bars."""
    W, H = PAGE_SIZE
    rows = extract_slide8_rows(session)

    _bg(c)

    # ── Header ──────────────────────────────────────────────────────────────
    _fill(c, FG)
    c.setFont("Helvetica-Bold", H1)
    header_y = H - MARGIN - H1
    c.drawCentredString(W / 2, header_y, "Retrieval Quality Scores")

    _fill(c, MUTED)
    c.setFont("Helvetica", BODY)
    sub_y = header_y - BODY - 8
    c.drawCentredString(W / 2, sub_y, "Compliance-Grade Profile  ·  RAG_ENV=prod  ·  Claude Sonnet 4.6")

    # ── Legend ───────────────────────────────────────────────────────────────
    legend_y = MARGIN + 4
    box_h = 16
    _fill(c, ACCENT_B)
    c.rect(MARGIN, legend_y, 24, box_h, fill=1, stroke=0)
    _fill(c, FG)
    c.setFont("Helvetica", CAPTION)
    c.drawString(MARGIN + 32, legend_y + 2, "Basic RAG")

    _fill(c, ACCENT_A)
    c.rect(MARGIN + 160, legend_y, 24, box_h, fill=1, stroke=0)
    _fill(c, FG)
    c.drawString(MARGIN + 192, legend_y + 2, "Agentic RAG")

    # ── Score rows ───────────────────────────────────────────────────────────
    label_w   = 80   # width reserved for "Q1", "Q2", etc.
    bar_x     = MARGIN + label_w
    score_w   = 52   # width reserved for "0.82" label
    bar_max_w = W - bar_x - score_w - MARGIN  # max bar width
    bar_h     = 28   # height of each individual bar
    gap_inner = 6    # gap between basic and agentic bars within a pair
    gap_outer = 24   # gap between query pairs

    n = max(len(rows), 1)
    pair_h = bar_h * 2 + gap_inner
    total_rows_h = n * pair_h + (n - 1) * gap_outer

    # Centre the row block vertically between subheader and legend
    available_top = sub_y - 20
    available_bot = legend_y + box_h + 16
    block_top = available_bot + total_rows_h + (available_top - available_bot - total_rows_h) / 2

    for i, row in enumerate(rows):
        pair_top = block_top - i * (pair_h + gap_outer)  # top of this pair

        label     = row["query_id"]
        basic     = row["basic_score"]
        agentic   = row["agentic_score"]

        # Query label (centred vertically in pair)
        _fill(c, MUTED)
        c.setFont("Helvetica-Bold", CAPTION)
        c.drawRightString(MARGIN + label_w - 8, pair_top - pair_h / 2 - CAPTION / 2, label)

        # Basic RAG bar
        basic_bar_w = max(2.0, basic * bar_max_w)
        _fill(c, ACCENT_B)
        c.rect(bar_x, pair_top - bar_h, basic_bar_w, bar_h, fill=1, stroke=0)
        _fill(c, FG)
        c.setFont("Helvetica-Bold", CAPTION)
        c.drawString(bar_x + basic_bar_w + 6, pair_top - bar_h + (bar_h - CAPTION) / 2, _format_score(basic))

        # Agentic RAG bar
        agentic_bar_y = pair_top - bar_h - gap_inner - bar_h
        agentic_bar_w = max(2.0, agentic * bar_max_w)
        _fill(c, ACCENT_A)
        c.rect(bar_x, agentic_bar_y, agentic_bar_w, bar_h, fill=1, stroke=0)
        _fill(c, FG)
        c.setFont("Helvetica-Bold", CAPTION)
        c.drawString(bar_x + agentic_bar_w + 6, agentic_bar_y + (bar_h - CAPTION) / 2, _format_score(agentic))

    _page_number(c, 8)


def _render_slide8_cta(c) -> None:
    """Slide 8: CTA — 'Try Agentic RAG today / DM for complete setup guide'."""
    W, H = PAGE_SIZE
    _bg(c)

    mid = H / 2
    _fill(c, FG)
    c.setFont("Helvetica-Bold", H1)
    c.drawCentredString(W / 2, mid + 20, "Try Agentic RAG today")

    _fill(c, ACCENT_A)
    c.setFont("Helvetica", H2)
    c.drawCentredString(W / 2, mid - H2 - 20, "DM for complete setup guide")

    _page_number(c, 8)


def assemble_carousel_from_pngs(
    source: str | Path,
    output_path: str | Path,
) -> list[Path]:
    """Assemble an ordered set of PNG slides into a carousel PDF.

    source may be a directory (reads slide_01.png … slide_NN.png in sorted order)
    or a comma-separated string of explicit file paths.
    Returns the list of PNG paths embedded, in order.
    """
    from reportlab.pdfgen import canvas as pdf_canvas
    from reportlab.lib.utils import ImageReader

    if isinstance(source, str) and "," in source:
        pngs = [Path(p.strip()) for p in source.split(",")]
    else:
        source_path = Path(source)
        if source_path.is_dir():
            pngs = sorted(source_path.glob("slide_*.png"))
        else:
            raise ValueError(f"source must be a directory or comma-separated paths: {source}")

    if not pngs:
        raise ValueError(f"No slide_*.png files found in {source}")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    W, H = PAGE_SIZE
    c = pdf_canvas.Canvas(str(output_path), pagesize=PAGE_SIZE)
    for png in pngs:
        c.drawImage(ImageReader(str(png)), 0, 0, width=W, height=H)
        c.showPage()
    c.save()

    return pngs


def assemble_hybrid_carousel(
    source_dir: str | Path,
    output_path: str | Path,
    theme: str = "default",
) -> list[Path]:
    """Assemble the hybrid carousel PDF using per-slide rendering rules in HYBRID_SLIDE_CONFIG.

    - "full" slides (1, 7): PDF-rendered 1080×1080 PNGs embedded at full page size.
    - "screenshot" slides (2–6): App screenshots centered on the theme BG, never upscaled,
      with a bold title at the top.
    - "cta" slide (8): supplement image centered, CTA text below.

    Returns the list of source files processed, in order.
    """
    from reportlab.pdfgen import canvas as pdf_canvas
    from reportlab.lib.utils import ImageReader

    apply_theme(theme)

    source_dir = Path(source_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    W, H = PAGE_SIZE
    c = pdf_canvas.Canvas(str(output_path), pagesize=PAGE_SIZE)
    processed: list[Path] = []

    for slide in HYBRID_SLIDE_CONFIG:
        stype = slide["type"]

        if stype == "full":
            png_path = source_dir / slide["file"]
            if not png_path.exists():
                raise FileNotFoundError(f"Missing slide: {png_path}")
            c.drawImage(ImageReader(str(png_path)), 0, 0, width=W, height=H)
            processed.append(png_path)

        elif stype == "screenshot":
            png_path = source_dir / slide["file"]
            if not png_path.exists():
                raise FileNotFoundError(f"Missing slide: {png_path}")

            _bg(c)

            # Title centred at top
            title_y = H - MARGIN - H2
            _fill(c, FG)
            c.setFont("Helvetica-Bold", H2)
            c.drawCentredString(W / 2, title_y, slide["title"])

            # Image area: below title down to bottom margin
            img_area_top = title_y - 20
            img_area_bot = MARGIN
            img_area_w = W - 2 * MARGIN
            img_area_h = img_area_top - img_area_bot

            img_reader = ImageReader(str(png_path))
            img_w, img_h = img_reader.getSize()
            # Scale to fit but never upscale — preserve natural crispness
            scale = min(img_area_w / img_w, img_area_h / img_h, 1.0)
            draw_w, draw_h = img_w * scale, img_h * scale
            draw_x = MARGIN + (img_area_w - draw_w) / 2
            draw_y = img_area_bot + (img_area_h - draw_h) / 2

            c.drawImage(img_reader, draw_x, draw_y, width=draw_w, height=draw_h)
            _page_number(c, slide["page"])
            processed.append(png_path)

        elif stype == "cta":
            supplement_path = source_dir / slide["supplement"]
            if not supplement_path.exists():
                raise FileNotFoundError(f"Missing supplement: {supplement_path}")

            _bg(c)

            # Title at top
            title_y = H - MARGIN - H1
            _fill(c, FG)
            c.setFont("Helvetica-Bold", H1)
            c.drawCentredString(W / 2, title_y, "Try Agentic RAG today")

            # CTA text pinned near bottom
            cta_y = MARGIN + H2
            _fill(c, ACCENT_A)
            c.setFont("Helvetica", H2)
            c.drawCentredString(W / 2, cta_y, "DM for complete setup guide")

            # Supplement image centred in the space between title and CTA
            img_area_top = title_y - 24
            img_area_bot = cta_y + H2 + 16
            img_area_w = W - 2 * MARGIN
            img_area_h = img_area_top - img_area_bot

            img_reader = ImageReader(str(supplement_path))
            img_w, img_h = img_reader.getSize()
            scale = min(img_area_w / img_w, img_area_h / img_h)
            draw_w, draw_h = img_w * scale, img_h * scale
            draw_x = (W - draw_w) / 2
            draw_y = img_area_bot + (img_area_h - draw_h) / 2

            c.drawImage(img_reader, draw_x, draw_y, width=draw_w, height=draw_h)
            _page_number(c, slide["page"])
            processed.append(supplement_path)

        c.showPage()

    c.save()
    return processed


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------


def generate_carousel(session: dict, output_path: str | Path, theme: str = "default") -> None:
    """Render an 8-page PDF carousel from a captured session dict."""
    from reportlab.pdfgen import canvas as pdf_canvas

    apply_theme(theme)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    c = pdf_canvas.Canvas(str(output_path), pagesize=PAGE_SIZE)

    # Slide 1: Hook — "The Failure"
    _render_slide1(c, session)
    c.showPage()

    # Slides 2–6: Query comparisons
    carousel_queries = _pick_carousel_queries(session, n=5)
    total_q = len(carousel_queries)
    for idx, entry in enumerate(carousel_queries, start=1):
        slide_data = _build_query_slide_data(entry)
        _render_query_slide(c, slide_num=idx + 1, slide_data=slide_data,
                            query_index=idx, total_queries=total_q)
        c.showPage()

    # Slide 7: Why Agentic RAG — bullet points
    _render_slide7_bullets(c)
    c.showPage()

    # Slide 8: CTA
    _render_slide8_cta(c)
    c.showPage()

    c.save()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    from rich.console import Console

    parser = argparse.ArgumentParser(
        description=(
            "Generate or assemble a LinkedIn carousel PDF.\n\n"
            "Mode 1 — session-based (original): provide --session to generate all slides from a "
            "captured RAG session JSON.\n"
            "Mode 2 — assemble: provide --assemble DIR to pack existing PNG slides into a PDF "
            "(hybrid workflow where slides 2–6 are app screenshots)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--session",
        metavar="PATH",
        help="Path to session JSON produced by capture_session.py (required unless --assemble is given)",
    )
    parser.add_argument(
        "--assemble",
        metavar="DIR",
        help=(
            "Directory containing slide_01.png … slide_NN.png. "
            "Packs them in sorted order into --output PDF. "
            "Use with --output; --session and --theme are ignored."
        ),
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        default="artifacts/carousel.pdf",
        help="Output PDF path (default: artifacts/carousel.pdf)",
    )
    parser.add_argument(
        "--theme",
        metavar="NAME",
        default="default",
        choices=list(THEMES),
        help=f"Color theme (default: default). Choices: {', '.join(THEMES)}",
    )
    parser.add_argument(
        "--screenshots",
        nargs="?",
        const="",  # sentinel: derive from PDF path
        metavar="DIR",
        help=(
            "Export each slide as a PNG. "
            "Omit DIR to auto-derive: artifacts/screenshots/<pdf-stem>/. "
            "Pass a path to override."
        ),
    )
    args = parser.parse_args(argv)

    console = Console()

    # ── Mode 2: assemble hybrid carousel from PNG directory ─────────────────
    if args.assemble:
        assemble_dir = Path(args.assemble)
        if not assemble_dir.is_dir():
            console.print(f"[red]Error:[/red] --assemble path is not a directory: {assemble_dir}")
            raise SystemExit(1)
        console.print(
            f"[bold]Assembling hybrid carousel[/bold] from {assemble_dir}/  "
            f"theme=[cyan]{args.theme}[/cyan]"
        )
        processed = assemble_hybrid_carousel(assemble_dir, args.output, theme=args.theme)
        console.print(f"[green]✓[/green] {len(processed)} slides → {args.output}")
        return

    # ── Mode 1: generate from session JSON ──────────────────────────────────
    if not args.session:
        parser.error("--session is required unless --assemble is given")

    session_path = Path(args.session)
    if not session_path.exists():
        console.print(f"[red]Error:[/red] session file not found: {session_path}")
        raise SystemExit(1)

    session = json.loads(session_path.read_text())
    console.print(
        f"[bold]Generating carousel[/bold] from {session_path.name} "
        f"({session['query_count']} queries)  theme=[cyan]{args.theme}[/cyan]"
    )

    generate_carousel(session, args.output, theme=args.theme)
    console.print(f"[green]✓[/green] Carousel saved → {args.output}")

    if args.screenshots is not None:
        pdf_stem = Path(args.output).stem
        screenshots_dir = (
            Path(args.screenshots)
            if args.screenshots
            else Path("artifacts") / "screenshots" / pdf_stem
        )
        written = export_screenshots(args.output, screenshots_dir)
        console.print(
            f"[green]✓[/green] {len(written)} screenshots → {screenshots_dir}/"
        )


if __name__ == "__main__":
    main()
