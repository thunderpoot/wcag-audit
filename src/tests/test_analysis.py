#!/usr/bin/env python3
"""
Test suite for the WCAG color contrast analysis engine.

Validates:
  - Color parsing (hex, rgb, hsl, named)
  - Relative luminance calculation
  - Contrast ratio calculation
  - CSS extraction from HTML
  - End-to-end analysis

Run:
    python3 tests/test_analysis.py
"""

import sys
import os
import math

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from importlib.machinery import SourceFileLoader
analyse = SourceFileLoader("analyse", os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "03_analyse_wcag.py"
)).load_module()


def assert_close(a, b, tol=0.01, msg=""):
    """Assert two numbers are close within tolerance."""
    if abs(a - b) > tol:
        raise AssertionError(f"Expected {b}, got {a} (tol={tol}). {msg}")


def assert_equal(a, b, msg=""):
    if a != b:
        raise AssertionError(f"Expected {b}, got {a}. {msg}")


def test_parse_hex():
    """Test hex color parsing."""
    assert_equal(analyse.parse_hex("#fff"), (255, 255, 255))
    assert_equal(analyse.parse_hex("#000"), (0, 0, 0))
    assert_equal(analyse.parse_hex("#f00"), (255, 0, 0))
    assert_equal(analyse.parse_hex("#ffffff"), (255, 255, 255))
    assert_equal(analyse.parse_hex("#000000"), (0, 0, 0))
    assert_equal(analyse.parse_hex("#ff6600"), (255, 102, 0))
    assert_equal(analyse.parse_hex("#336699"), (51, 102, 153))
    # With alpha
    assert_equal(analyse.parse_hex("#ff660080"), (255, 102, 0))
    assert_equal(analyse.parse_hex("#f008"), (255, 0, 0))
    print("  PASS: test_parse_hex")


def test_parse_rgb():
    """Test rgb/rgba color parsing."""
    assert_equal(analyse.parse_rgb("rgb(255, 0, 0)"), (255, 0, 0))
    assert_equal(analyse.parse_rgb("rgb(0, 128, 255)"), (0, 128, 255))
    assert_equal(analyse.parse_rgb("rgba(255, 0, 0, 0.5)"), (255, 0, 0))
    assert_equal(analyse.parse_rgb("rgb(100%, 0%, 0%)"), (255, 0, 0))
    # Modern syntax (space-separated)
    assert_equal(analyse.parse_rgb("rgb(255 0 0)"), (255, 0, 0))
    assert_equal(analyse.parse_rgb("rgba(255 0 0 / 0.5)"), (255, 0, 0))
    print("  PASS: test_parse_rgb")


def test_parse_hsl():
    """Test hsl/hsla color parsing."""
    # Red
    result = analyse.parse_hsl("hsl(0, 100%, 50%)")
    assert_equal(result, (255, 0, 0), f"hsl red: got {result}")

    # Green
    result = analyse.parse_hsl("hsl(120, 100%, 50%)")
    assert_equal(result, (0, 255, 0), f"hsl green: got {result}")

    # Blue
    result = analyse.parse_hsl("hsl(240, 100%, 50%)")
    assert_equal(result, (0, 0, 255), f"hsl blue: got {result}")

    # White
    result = analyse.parse_hsl("hsl(0, 0%, 100%)")
    assert_equal(result, (255, 255, 255), f"hsl white: got {result}")

    # Black
    result = analyse.parse_hsl("hsl(0, 0%, 0%)")
    assert_equal(result, (0, 0, 0), f"hsl black: got {result}")

    # With alpha
    result = analyse.parse_hsl("hsla(0, 100%, 50%, 0.5)")
    assert_equal(result, (255, 0, 0), f"hsla red: got {result}")

    print("  PASS: test_parse_hsl")


def test_parse_named_colors():
    """Test named color parsing."""
    assert_equal(analyse.parse_color("red"), (255, 0, 0))
    assert_equal(analyse.parse_color("white"), (255, 255, 255))
    assert_equal(analyse.parse_color("black"), (0, 0, 0))
    assert_equal(analyse.parse_color("navy"), (0, 0, 128))
    assert_equal(analyse.parse_color("cornflowerblue"), (100, 149, 237))
    assert_equal(analyse.parse_color("rebeccapurple"), (102, 51, 153))
    print("  PASS: test_parse_named_colors")


def test_parse_color_edge_cases():
    """Test edge cases in color parsing."""
    assert_equal(analyse.parse_color("transparent"), None)
    assert_equal(analyse.parse_color("inherit"), None)
    assert_equal(analyse.parse_color("currentColor"), None)
    assert_equal(analyse.parse_color("initial"), None)
    assert_equal(analyse.parse_color(""), None)
    assert_equal(analyse.parse_color(None), None)
    assert_equal(analyse.parse_color("not-a-color"), None)
    print("  PASS: test_parse_color_edge_cases")


def test_relative_luminance():
    """Test WCAG relative luminance calculation."""
    # White should have luminance 1.0
    assert_close(analyse.relative_luminance((255, 255, 255)), 1.0)

    # Black should have luminance 0.0
    assert_close(analyse.relative_luminance((0, 0, 0)), 0.0)

    # Known values from WCAG spec examples
    # Mid-gray
    lum = analyse.relative_luminance((128, 128, 128))
    assert_close(lum, 0.2159, tol=0.01)

    print("  PASS: test_relative_luminance")


def test_contrast_ratio():
    """Test WCAG contrast ratio calculation."""
    white = (255, 255, 255)
    black = (0, 0, 0)

    # White on black: maximum contrast 21:1
    ratio = analyse.contrast_ratio(white, black)
    assert_close(ratio, 21.0, tol=0.1)

    # Same color: minimum contrast 1:1
    ratio = analyse.contrast_ratio(white, white)
    assert_close(ratio, 1.0, tol=0.01)

    # Known example: #767676 on white is approximately 4.54:1
    # This is the classic "minimum passing gray"
    gray = (118, 118, 118)
    ratio = analyse.contrast_ratio(gray, white)
    assert_close(ratio, 4.54, tol=0.1, msg=f"Gray on white: {ratio}")

    # Red on white
    red = (255, 0, 0)
    ratio = analyse.contrast_ratio(red, white)
    assert_close(ratio, 4.0, tol=0.1, msg=f"Red on white: {ratio}")

    print("  PASS: test_contrast_ratio")


def test_contrast_ratio_symmetry():
    """Contrast ratio should be the same regardless of order."""
    c1 = (100, 50, 200)
    c2 = (200, 200, 50)
    assert_close(
        analyse.contrast_ratio(c1, c2),
        analyse.contrast_ratio(c2, c1)
    )
    print("  PASS: test_contrast_ratio_symmetry")


def test_extract_colors_from_css():
    """Test CSS color extraction."""
    css = """
    body {
        color: #333;
        background-color: #fff;
    }
    .link {
        color: rgb(0, 102, 204);
    }
    .warning {
        color: red;
        background-color: yellow;
    }
    """
    decls = analyse.extract_colors_from_css(css)
    assert len(decls) >= 3, f"Expected >= 3 declarations, got {len(decls)}"

    # Check that we found the body colors
    body_decl = [d for d in decls if "body" in d.get("selector", "")]
    assert len(body_decl) >= 1, "Should find body declaration"
    assert body_decl[0].get("color") == "#333"
    assert body_decl[0].get("background") == "#fff"

    print("  PASS: test_extract_colors_from_css")


def test_css_comments_removed():
    """CSS comments should be stripped before parsing."""
    css = """
    /* This is a comment with color: red */
    body {
        color: blue; /* inline comment */
        background-color: white;
    }
    """
    decls = analyse.extract_colors_from_css(css)
    assert len(decls) >= 1
    body_decl = [d for d in decls if "body" in d.get("selector", "")]
    assert body_decl[0].get("color") == "blue"
    print("  PASS: test_css_comments_removed")


def test_analyse_html_basic():
    """Test end-to-end HTML analysis."""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        body { color: #333333; background-color: #ffffff; }
        a { color: #0066cc; }
        .error { color: #ff0000; background-color: #ffeeee; }
    </style>
    </head>
    <body>
        <p>Hello</p>
        <a href="#">Link</a>
        <p class="error">Error message</p>
        <div style="color: white; background-color: #336699;">Inline styled</div>
    </body>
    </html>
    """
    result = analyse.analyse_html(html)
    assert result["total_pairings"] > 0, "Should find pairings"
    assert result["pass_rate_normal"] is not None
    assert result["worst_ratio"] is not None

    # Verify contrast calculations are reasonable
    for p in result["pairings"]:
        assert 1.0 <= p["ratio"] <= 21.0, f"Ratio out of range: {p['ratio']}"
        assert isinstance(p["pass_normal"], bool)
        assert isinstance(p["pass_large"], bool)
        if p["pass_normal"]:
            assert p["ratio"] >= 4.5
        if p["pass_large"]:
            assert p["ratio"] >= 3.0

    print("  PASS: test_analyse_html_basic")


def test_analyse_html_no_colors():
    """HTML with no color declarations should return empty results."""
    html = "<html><body><p>Plain text</p></body></html>"
    result = analyse.analyse_html(html)
    assert result["total_pairings"] == 0
    assert result["pass_rate_normal"] is None
    print("  PASS: test_analyse_html_no_colors")


def test_analyse_html_inline_only():
    """Test with only inline styles."""
    html = """
    <html><body>
        <div style="color: #000; background-color: #fff;">High contrast</div>
        <div style="color: #ccc; background-color: #ddd;">Low contrast</div>
    </body></html>
    """
    result = analyse.analyse_html(html)
    assert result["total_pairings"] == 2, f"Expected 2 pairings, got {result['total_pairings']}"

    # One should pass, one should fail
    ratios = sorted([p["ratio"] for p in result["pairings"]])
    assert ratios[0] < 4.5, "Low contrast pair should fail normal text"
    assert ratios[1] >= 4.5, "High contrast pair should pass normal text"
    print("  PASS: test_analyse_html_inline_only")


def test_background_shorthand():
    """Test extraction of colors from background shorthand property."""
    html = """
    <html><head><style>
        .a { color: #000; background: #f0f0f0 url(bg.png) no-repeat; }
        .b { color: white; background: linear-gradient(red, blue); }
        .c { color: #333; background: navy; }
    </style></head><body></body></html>
    """
    result = analyse.analyse_html(html)
    # Should find at least the explicit color pairings
    assert result["total_pairings"] >= 2, f"Expected >= 2, got {result['total_pairings']}"
    print("  PASS: test_background_shorthand")


def test_wcag_threshold_boundary():
    """Test exact boundary of WCAG AA thresholds."""
    # #767676 on white is approximately 4.54:1, just passing normal text
    gray = analyse.parse_color("#767676")
    white = (255, 255, 255)
    ratio = analyse.contrast_ratio(gray, white)
    assert ratio >= 4.5, f"#767676 on white should pass normal (ratio: {ratio})"

    # #777777 on white is approximately 4.48:1, just failing normal text
    lighter_gray = analyse.parse_color("#777777")
    ratio2 = analyse.contrast_ratio(lighter_gray, white)
    assert ratio2 < 4.5, f"#777777 on white should fail normal (ratio: {ratio2})"
    assert ratio2 >= 3.0, f"#777777 on white should pass large (ratio: {ratio2})"

    print("  PASS: test_wcag_threshold_boundary")


def test_deduplication():
    """Identical color pairings should be deduplicated."""
    html = """
    <html><head><style>
        .a { color: #333; background-color: #fff; }
        .b { color: #333; background-color: #fff; }
        .c { color: #333; background-color: #fff; }
    </style></head><body></body></html>
    """
    result = analyse.analyse_html(html)
    assert result["total_pairings"] == 1, \
        f"Duplicate pairings should be merged, got {result['total_pairings']}"
    print("  PASS: test_deduplication")


def run_all():
    """Run all tests."""
    print("Running WCAG analysis tests...\n")

    tests = [
        test_parse_hex,
        test_parse_rgb,
        test_parse_hsl,
        test_parse_named_colors,
        test_parse_color_edge_cases,
        test_relative_luminance,
        test_contrast_ratio,
        test_contrast_ratio_symmetry,
        test_extract_colors_from_css,
        test_css_comments_removed,
        test_analyse_html_basic,
        test_analyse_html_no_colors,
        test_analyse_html_inline_only,
        test_background_shorthand,
        test_wcag_threshold_boundary,
        test_deduplication,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  FAIL: {test.__name__}: {e}")

    print(f"\n{'=' * 40}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")

    if failed > 0:
        sys.exit(1)
    else:
        print("All tests passed!")


if __name__ == "__main__":
    run_all()
