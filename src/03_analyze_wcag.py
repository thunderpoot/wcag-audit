#!/usr/bin/env python3
"""
Step 3: WCAG 2.1/2.2 Level AA color contrast analysis.

Parses each archived HTML file to extract CSS color declarations,
identifies foreground/background pairings, calculates contrast ratios,
and evaluates compliance against WCAG AA thresholds.

WCAG 2.1/2.2 Level AA thresholds:
  - Normal text:     4.5:1 contrast ratio
  - Large text:      3.0:1 contrast ratio  (>= 18pt, or >= 14pt bold)
  - UI components:   3.0:1 contrast ratio

Usage:
    python3 03_analyze_wcag.py [--workers 8]
"""

import json
import os
import re
import sys
import math
import argparse
from html.parser import HTMLParser
from concurrent.futures import ProcessPoolExecutor, as_completed

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
HTML_DIR = os.path.join(DATA_DIR, "warc_html")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
RESULTS_FILE = os.path.join(OUTPUT_DIR, "wcag_results.json")

# WCAG AA thresholds
CONTRAST_NORMAL = 4.5
CONTRAST_LARGE = 3.0

# ---------------------------------------------------------------------------
# CSS Named Colors (full W3C list)
# ---------------------------------------------------------------------------
NAMED_COLORS = {
    "aliceblue": (240, 248, 255), "antiquewhite": (250, 235, 215),
    "aqua": (0, 255, 255), "aquamarine": (127, 255, 212),
    "azure": (240, 255, 255), "beige": (245, 245, 220),
    "bisque": (255, 228, 196), "black": (0, 0, 0),
    "blanchedalmond": (255, 235, 205), "blue": (0, 0, 255),
    "blueviolet": (138, 43, 226), "brown": (165, 42, 42),
    "burlywood": (222, 184, 135), "cadetblue": (95, 158, 160),
    "chartreuse": (127, 255, 0), "chocolate": (210, 105, 30),
    "coral": (255, 127, 80), "cornflowerblue": (100, 149, 237),
    "cornsilk": (255, 248, 220), "crimson": (220, 20, 60),
    "cyan": (0, 255, 255), "darkblue": (0, 0, 139),
    "darkcyan": (0, 139, 139), "darkgoldenrod": (184, 134, 11),
    "darkgray": (169, 169, 169), "darkgreen": (0, 100, 0),
    "darkgrey": (169, 169, 169), "darkkhaki": (189, 183, 107),
    "darkmagenta": (139, 0, 139), "darkolivegreen": (85, 107, 47),
    "darkorange": (255, 140, 0), "darkorchid": (153, 50, 204),
    "darkred": (139, 0, 0), "darksalmon": (233, 150, 122),
    "darkseagreen": (143, 188, 143), "darkslateblue": (72, 61, 139),
    "darkslategray": (47, 79, 79), "darkslategrey": (47, 79, 79),
    "darkturquoise": (0, 206, 209), "darkviolet": (148, 0, 211),
    "deeppink": (255, 20, 147), "deepskyblue": (0, 191, 255),
    "dimgray": (105, 105, 105), "dimgrey": (105, 105, 105),
    "dodgerblue": (30, 144, 255), "firebrick": (178, 34, 34),
    "floralwhite": (255, 250, 240), "forestgreen": (34, 139, 34),
    "fuchsia": (255, 0, 255), "gainsboro": (220, 220, 220),
    "ghostwhite": (248, 248, 255), "gold": (255, 215, 0),
    "goldenrod": (218, 165, 32), "gray": (128, 128, 128),
    "green": (0, 128, 0), "greenyellow": (173, 255, 47),
    "grey": (128, 128, 128), "honeydew": (240, 255, 240),
    "hotpink": (255, 105, 180), "indianred": (205, 92, 92),
    "indigo": (75, 0, 130), "ivory": (255, 255, 240),
    "khaki": (240, 230, 140), "lavender": (230, 230, 250),
    "lavenderblush": (255, 240, 245), "lawngreen": (124, 252, 0),
    "lemonchiffon": (255, 250, 205), "lightblue": (173, 216, 230),
    "lightcoral": (240, 128, 128), "lightcyan": (224, 255, 255),
    "lightgoldenrodyellow": (250, 250, 210), "lightgray": (211, 211, 211),
    "lightgreen": (144, 238, 144), "lightgrey": (211, 211, 211),
    "lightpink": (255, 182, 193), "lightsalmon": (255, 160, 122),
    "lightseagreen": (32, 178, 170), "lightskyblue": (135, 206, 250),
    "lightslategray": (119, 136, 153), "lightslategrey": (119, 136, 153),
    "lightsteelblue": (176, 196, 222), "lightyellow": (255, 255, 224),
    "lime": (0, 255, 0), "limegreen": (50, 205, 50),
    "linen": (250, 240, 230), "magenta": (255, 0, 255),
    "maroon": (128, 0, 0), "mediumaquamarine": (102, 205, 170),
    "mediumblue": (0, 0, 205), "mediumorchid": (186, 85, 211),
    "mediumpurple": (147, 111, 219), "mediumseagreen": (60, 179, 113),
    "mediumslateblue": (123, 104, 238), "mediumspringgreen": (0, 250, 154),
    "mediumturquoise": (72, 209, 204), "mediumvioletred": (199, 21, 133),
    "midnightblue": (25, 25, 112), "mintcream": (245, 255, 250),
    "mistyrose": (255, 228, 225), "moccasin": (255, 228, 181),
    "navajowhite": (255, 222, 173), "navy": (0, 0, 128),
    "oldlace": (253, 245, 230), "olive": (128, 128, 0),
    "olivedrab": (107, 142, 35), "orange": (255, 165, 0),
    "orangered": (255, 69, 0), "orchid": (218, 112, 214),
    "palegoldenrod": (238, 232, 170), "palegreen": (152, 251, 152),
    "paleturquoise": (175, 238, 238), "palevioletred": (219, 112, 147),
    "papayawhip": (255, 239, 213), "peachpuff": (255, 218, 185),
    "peru": (205, 133, 63), "pink": (255, 192, 203),
    "plum": (221, 160, 221), "powderblue": (176, 224, 230),
    "purple": (128, 0, 128), "rebeccapurple": (102, 51, 153),
    "red": (255, 0, 0), "rosybrown": (188, 143, 143),
    "royalblue": (65, 105, 225), "saddlebrown": (139, 69, 19),
    "salmon": (250, 128, 114), "sandybrown": (244, 164, 96),
    "seagreen": (46, 139, 87), "seashell": (255, 245, 238),
    "sienna": (160, 82, 45), "silver": (192, 192, 192),
    "skyblue": (135, 206, 235), "slateblue": (106, 90, 205),
    "slategray": (112, 128, 144), "slategrey": (112, 128, 144),
    "snow": (255, 250, 250), "springgreen": (0, 255, 127),
    "steelblue": (70, 130, 180), "tan": (210, 180, 140),
    "teal": (0, 128, 128), "thistle": (216, 191, 216),
    "tomato": (255, 99, 71), "turquoise": (64, 224, 208),
    "violet": (238, 130, 238), "wheat": (245, 222, 179),
    "white": (255, 255, 255), "whitesmoke": (245, 245, 245),
    "yellow": (255, 255, 0), "yellowgreen": (154, 205, 50),
}

# ---------------------------------------------------------------------------
# Color parsing
# ---------------------------------------------------------------------------

def parse_hex(s):
    """Parse #RGB, #RGBA, #RRGGBB, or #RRGGBBAA to (R, G, B)."""
    s = s.strip().lstrip("#")
    if len(s) == 3:
        r, g, b = int(s[0]*2, 16), int(s[1]*2, 16), int(s[2]*2, 16)
    elif len(s) == 4:
        r, g, b = int(s[0]*2, 16), int(s[1]*2, 16), int(s[2]*2, 16)
        # s[3] is alpha, ignored for contrast
    elif len(s) == 6:
        r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    elif len(s) == 8:
        r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    else:
        return None
    return (r, g, b)


def parse_rgb(s):
    """Parse rgb(R, G, B) or rgba(R, G, B, A) to (R, G, B)."""
    m = re.match(r"rgba?\s*\(\s*([^)]+)\)", s.strip())
    if not m:
        return None
    parts = re.split(r"[,/\s]+", m.group(1).strip())
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) < 3:
        return None
    try:
        vals = []
        for i, p in enumerate(parts[:3]):
            if p.endswith("%"):
                vals.append(int(float(p[:-1]) * 255 / 100))
            else:
                vals.append(int(float(p)))
        return (max(0, min(255, vals[0])),
                max(0, min(255, vals[1])),
                max(0, min(255, vals[2])))
    except (ValueError, IndexError):
        return None


def hsl_to_rgb(h, s, l):
    """Convert HSL (h: 0-360, s: 0-1, l: 0-1) to RGB (0-255)."""
    h = h % 360
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = l - c / 2

    if h < 60:
        r1, g1, b1 = c, x, 0
    elif h < 120:
        r1, g1, b1 = x, c, 0
    elif h < 180:
        r1, g1, b1 = 0, c, x
    elif h < 240:
        r1, g1, b1 = 0, x, c
    elif h < 300:
        r1, g1, b1 = x, 0, c
    else:
        r1, g1, b1 = c, 0, x

    return (
        max(0, min(255, round((r1 + m) * 255))),
        max(0, min(255, round((g1 + m) * 255))),
        max(0, min(255, round((b1 + m) * 255))),
    )


def parse_hsl(s):
    """Parse hsl(H, S%, L%) or hsla(H, S%, L%, A) to (R, G, B)."""
    m = re.match(r"hsla?\s*\(\s*([^)]+)\)", s.strip())
    if not m:
        return None
    parts = re.split(r"[,/\s]+", m.group(1).strip())
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) < 3:
        return None
    try:
        h_str = parts[0]
        h = float(h_str.replace("deg", "").replace("turn", "").replace("rad", "").replace("grad", ""))
        if "turn" in h_str:
            h = h * 360
        elif "rad" in h_str:
            h = h * 180 / math.pi
        elif "grad" in h_str:
            h = h * 0.9

        s_val = float(parts[1].replace("%", "")) / 100
        l_val = float(parts[2].replace("%", "")) / 100
        return hsl_to_rgb(h, s_val, l_val)
    except (ValueError, IndexError):
        return None


def parse_color(value):
    """
    Parse any CSS color value to (R, G, B) tuple.
    Returns None for unparseable values, 'transparent', 'inherit', 'currentColor', etc.
    """
    if not value or not isinstance(value, str):
        return None

    value = value.strip().lower()

    # Skip non-color values
    if value in ("transparent", "inherit", "initial", "unset", "currentcolor",
                 "none", "auto", "revert"):
        return None

    # Hex
    if value.startswith("#"):
        return parse_hex(value)

    # RGB/RGBA
    if value.startswith("rgb"):
        return parse_rgb(value)

    # HSL/HSLA
    if value.startswith("hsl"):
        return parse_hsl(value)

    # Named colors
    if value in NAMED_COLORS:
        return NAMED_COLORS[value]

    return None


# ---------------------------------------------------------------------------
# WCAG contrast calculation
# ---------------------------------------------------------------------------

def relative_luminance(rgb):
    """
    Calculate relative luminance per WCAG 2.1 definition.
    https://www.w3.org/TR/WCAG21/#dfn-relative-luminance
    """
    def linearize(c):
        c = c / 255.0
        if c <= 0.04045:
            return c / 12.92
        else:
            return ((c + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)


def contrast_ratio(rgb1, rgb2):
    """
    Calculate contrast ratio between two colors per WCAG 2.1.
    https://www.w3.org/TR/WCAG21/#dfn-contrast-ratio
    Returns a value >= 1.0 (1:1 means identical).
    """
    l1 = relative_luminance(rgb1)
    l2 = relative_luminance(rgb2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


# ---------------------------------------------------------------------------
# CSS extraction from HTML
# ---------------------------------------------------------------------------

class StyleExtractor(HTMLParser):
    """
    Extract CSS from HTML:
      - <style> block contents
      - style="" attributes on elements
    """

    def __init__(self):
        super().__init__()
        self.in_style = False
        self.style_blocks = []
        self.inline_styles = []
        self._current_style = []

    def handle_starttag(self, tag, attrs):
        if tag == "style":
            self.in_style = True
            self._current_style = []

        # Collect inline style attributes
        attrs_dict = dict(attrs)
        if "style" in attrs_dict and attrs_dict["style"]:
            self.inline_styles.append(attrs_dict["style"])

    def handle_endtag(self, tag):
        if tag == "style" and self.in_style:
            self.in_style = False
            self.style_blocks.append("".join(self._current_style))
            self._current_style = []

    def handle_data(self, data):
        if self.in_style:
            self._current_style.append(data)

    def error(self, message):
        pass


def extract_colors_from_css(css_text):
    """
    Extract color and background-color declarations from CSS text.
    Returns list of dicts: {"selector": ..., "color": ..., "background": ...}
    """
    declarations = []

    # Remove CSS comments
    css_text = re.sub(r"/\*.*?\*/", "", css_text, flags=re.DOTALL)

    # Parse CSS rules: selector { declarations }
    rule_pattern = re.compile(r"([^{}]+?)\{([^{}]*)\}", re.DOTALL)

    for match in rule_pattern.finditer(css_text):
        selector = match.group(1).strip()
        body = match.group(2).strip()
        decl = _parse_declarations(body)
        if decl.get("color") or decl.get("background"):
            decl["selector"] = selector
            declarations.append(decl)

    return declarations


def _parse_declarations(css_body):
    """Parse CSS declarations to extract color-related properties."""
    result = {}

    # Split on semicolons, handling values that contain parentheses
    props = re.split(r";\s*", css_body)

    for prop in props:
        prop = prop.strip()
        if not prop or ":" not in prop:
            continue

        name, _, value = prop.partition(":")
        name = name.strip().lower()
        value = value.strip().rstrip(";").strip()

        # Remove !important
        value = re.sub(r"\s*!important\s*$", "", value, flags=re.IGNORECASE)

        if name == "color":
            result["color"] = value
        elif name in ("background-color", "background"):
            # For shorthand 'background', try to extract color
            if name == "background":
                # Try to find a color value in the shorthand
                color = _extract_color_from_background_shorthand(value)
                if color:
                    result["background"] = color
            else:
                result["background"] = value

    return result


def _extract_color_from_background_shorthand(value):
    """Extract color from CSS background shorthand property."""
    # Try parsing the whole thing as a color first
    if parse_color(value):
        return value

    # Look for color-like tokens in the shorthand
    # Try hex colors
    hex_match = re.search(r"(#[0-9a-fA-F]{3,8})\b", value)
    if hex_match:
        return hex_match.group(1)

    # Try rgb/rgba/hsl/hsla
    func_match = re.search(r"((?:rgb|hsl)a?\s*\([^)]+\))", value, re.IGNORECASE)
    if func_match:
        return func_match.group(1)

    # Try named colors
    for token in value.split():
        token_clean = token.strip().lower()
        if token_clean in NAMED_COLORS:
            return token_clean

    return None


def extract_inline_colors(style_str):
    """Extract color/background-color from an inline style string."""
    return _parse_declarations(style_str)


# ---------------------------------------------------------------------------
# Analysis engine
# ---------------------------------------------------------------------------

def analyze_html(html_content):
    """
    Analyze an HTML document for WCAG AA color contrast compliance.

    Returns a dict with:
      - pairings: list of color pairings found with contrast ratios
      - summary: pass/fail counts and rates
    """
    # Extract styles
    extractor = StyleExtractor()
    try:
        extractor.feed(html_content)
    except Exception:
        pass

    # Collect all color declarations
    all_decls = []

    # From <style> blocks
    for block in extractor.style_blocks:
        all_decls.extend(extract_colors_from_css(block))

    # From inline styles
    for style_str in extractor.inline_styles:
        decl = extract_inline_colors(style_str)
        if decl.get("color") or decl.get("background"):
            decl["selector"] = "[inline]"
            all_decls.append(decl)

    # Build color pairings
    pairings = []
    seen = set()  # deduplicate

    for decl in all_decls:
        fg_str = decl.get("color")
        bg_str = decl.get("background")

        fg_rgb = parse_color(fg_str) if fg_str else None
        bg_rgb = parse_color(bg_str) if bg_str else None

        if fg_rgb and bg_rgb:
            # Explicit pairing
            key = (fg_rgb, bg_rgb)
            if key not in seen:
                seen.add(key)
                ratio = contrast_ratio(fg_rgb, bg_rgb)
                pairings.append({
                    "foreground": fg_str,
                    "background": bg_str,
                    "fg_rgb": list(fg_rgb),
                    "bg_rgb": list(bg_rgb),
                    "ratio": round(ratio, 2),
                    "pass_normal": ratio >= CONTRAST_NORMAL,
                    "pass_large": ratio >= CONTRAST_LARGE,
                    "explicit": True,
                    "selector": decl.get("selector", ""),
                })
        elif fg_rgb and not bg_rgb:
            # Foreground only: assume white background
            bg_default = (255, 255, 255)
            key = (fg_rgb, bg_default)
            if key not in seen:
                seen.add(key)
                ratio = contrast_ratio(fg_rgb, bg_default)
                pairings.append({
                    "foreground": fg_str,
                    "background": "#ffffff (assumed)",
                    "fg_rgb": list(fg_rgb),
                    "bg_rgb": list(bg_default),
                    "ratio": round(ratio, 2),
                    "pass_normal": ratio >= CONTRAST_NORMAL,
                    "pass_large": ratio >= CONTRAST_LARGE,
                    "explicit": False,
                    "selector": decl.get("selector", ""),
                })
        elif bg_rgb and not fg_rgb:
            # Background only: assume black foreground
            fg_default = (0, 0, 0)
            key = (fg_default, bg_rgb)
            if key not in seen:
                seen.add(key)
                ratio = contrast_ratio(fg_default, bg_rgb)
                pairings.append({
                    "foreground": "#000000 (assumed)",
                    "background": bg_str,
                    "fg_rgb": list(fg_default),
                    "bg_rgb": list(bg_rgb),
                    "ratio": round(ratio, 2),
                    "pass_normal": ratio >= CONTRAST_NORMAL,
                    "pass_large": ratio >= CONTRAST_LARGE,
                    "explicit": False,
                    "selector": decl.get("selector", ""),
                })

    # Calculate summary
    total = len(pairings)
    if total == 0:
        return {
            "pairings": [],
            "total_pairings": 0,
            "pass_normal": 0,
            "fail_normal": 0,
            "pass_large": 0,
            "fail_large": 0,
            "pass_rate_normal": None,
            "pass_rate_large": None,
            "worst_ratio": None,
            "best_ratio": None,
            "median_ratio": None,
            "mean_ratio": None,
        }

    pass_n = sum(1 for p in pairings if p["pass_normal"])
    pass_l = sum(1 for p in pairings if p["pass_large"])
    ratios = sorted([p["ratio"] for p in pairings])

    return {
        "pairings": pairings,
        "total_pairings": total,
        "pass_normal": pass_n,
        "fail_normal": total - pass_n,
        "pass_large": pass_l,
        "fail_large": total - pass_l,
        "pass_rate_normal": round(pass_n / total * 100, 1),
        "pass_rate_large": round(pass_l / total * 100, 1),
        "worst_ratio": ratios[0],
        "best_ratio": ratios[-1],
        "median_ratio": round(ratios[len(ratios) // 2], 2),
        "mean_ratio": round(sum(ratios) / len(ratios), 2),
    }


def process_file(args):
    """Analyze a single HTML file."""
    filepath, domain = args
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            html = f.read()
        result = analyze_html(html)
        result["domain"] = domain
        result["status"] = "analyzed"
        return result
    except Exception as e:
        return {"domain": domain, "status": "error", "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="WCAG AA color contrast analysis")
    parser.add_argument("--workers", type=int, default=8,
                        help="Number of parallel workers (default: 8)")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Find all HTML files
    html_files = []
    for fname in sorted(os.listdir(HTML_DIR)):
        if fname.endswith(".html"):
            domain = fname[:-5]  # strip .html
            filepath = os.path.join(HTML_DIR, fname)
            html_files.append((filepath, domain))

    print(f"Found {len(html_files)} HTML files to analyze")

    results = []

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_file, item): item[1]
                   for item in html_files}

        for i, future in enumerate(as_completed(futures), 1):
            domain = futures[future]
            try:
                result = future.result()
                results.append(result)
                if result["status"] == "analyzed":
                    n = result["total_pairings"]
                    rate = result["pass_rate_normal"]
                    if rate is not None:
                        print(f"  [{i}/{len(html_files)}] {domain}: "
                              f"{n} pairings, {rate}% pass (normal text)")
                    else:
                        print(f"  [{i}/{len(html_files)}] {domain}: no color data")
                else:
                    print(f"  [{i}/{len(html_files)}] {domain}: {result.get('error', 'unknown error')}")
            except Exception as e:
                results.append({"domain": domain, "status": "error", "error": str(e)})
                print(f"  [{i}/{len(html_files)}] {domain}: ERROR - {e}")

    # Save results (without full pairing details for the main file)
    results_summary = []
    results_full = []

    for r in results:
        full = dict(r)
        results_full.append(full)

        summary = {k: v for k, v in r.items() if k != "pairings"}
        # Include worst offending pairings
        if r.get("pairings"):
            failing = [p for p in r["pairings"] if not p["pass_normal"]]
            failing.sort(key=lambda p: p["ratio"])
            summary["worst_pairings"] = failing[:5]
        results_summary.append(summary)

    # Save summary results
    with open(RESULTS_FILE, "w") as f:
        json.dump(results_summary, f, indent=2)

    # Save full results (with all pairings) to a separate file
    full_path = os.path.join(OUTPUT_DIR, "wcag_results_full.json")
    with open(full_path, "w") as f:
        json.dump(results_full, f, indent=2)

    analyzed = sum(1 for r in results if r.get("status") == "analyzed")
    with_colors = sum(1 for r in results
                      if r.get("status") == "analyzed" and r.get("total_pairings", 0) > 0)
    print(f"\nDone. Analyzed: {analyzed}, With color data: {with_colors}")
    print(f"Results: {RESULTS_FILE}")
    print(f"Full results: {full_path}")


if __name__ == "__main__":
    main()
