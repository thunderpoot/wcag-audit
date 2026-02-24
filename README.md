# WCAG 2.1/2.2 Level AA Colour Contrast Audit of Common Crawl's Top 500 Domains

An automated pipeline for assessing WCAG 2.1/2.2 Level AA colour contrast compliance across the 500 most-crawled registered domains in Common Crawl's February 2026 crawl archive (CC-MAIN-2026-08), using archived copies from Common Crawl's WARC data.

## Overview

This pipeline:

1. Takes the top 500 registered domains from CC-MAIN-2026-08 crawl statistics
2. Queries Common Crawl's **Columnar Index** via Amazon Athena to locate archived homepage captures in a single SQL pass
3. Fetches the actual HTML from WARC files via byte-range requests to `data.commoncrawl.org`
4. Parses all CSS colour declarations (inline styles, embedded `<style>` blocks)
5. Evaluates every foreground/background colour pairing against WCAG 2.1/2.2 Level AA thresholds
6. Produces a comprehensive JSON results file and summary statistics

**No live websites are crawled.** All page content comes from Common Crawl's open archive.

## The Columnar Index

The pipeline uses Common Crawl's [Columnar Index](https://commoncrawl.org/columnar-index), a Parquet-based representation of the crawl index stored on S3 at
`s3://commoncrawl/cc-index/table/cc-main/warc/`. A single Athena SQL query finds all 500 homepage captures in one pass.

The query:

- Filters for `crawl = 'CC-MAIN-2026-08'`, `subset = 'warc'`, `fetch_status = 200`, `url_path = '/'`, `content_mime_detected = 'text/html'`
- Uses `ROW_NUMBER() OVER (PARTITION BY url_host_registered_domain ...)` to pick one capture per domain
- Prefers the `www` subdomain or bare domain over deep subdomains, HTTPS over HTTP, and the most recent capture
- Scans roughly 100-300 GB of columnar data at a typical cost of $0.50-1.50

## Requirements

- Python 3.9+
- For Athena auto mode: `pip install pyathena` and AWS credentials with Athena access
- No other external dependencies (uses only `urllib`, `json`, `re`, `html.parser`, `csv`, `gzip`, `io`, `concurrent.futures`)

## Quick Start

See [ATHENA_SETUP](./ATHENA_SETUP.md) for instructions for setting up Amazon Athena.

Step 1 (`01_fetch_index.py`) supports three modes for querying the Columnar Index:

```bash
# Mode 1: Print the SQL query, run it yourself in the Athena console
python3 01_fetch_index.py --mode=sql

# Mode 2: Import results from a CSV downloaded from the Athena console
python3 01_fetch_index.py --mode=csv path/to/athena-results.csv

# Mode 3: Run the query directly via pyathena (requires AWS credentials)
export ATHENA_OUTPUT=s3://your-bucket/athena-results/
python3 01_fetch_index.py --mode=auto
```

Optionally use a personal database namespace to avoid touching shared resources:

```bash
python3 01_fetch_index.py --mode=auto --database=my_wcag --setup
```

Then run the rest of the pipeline:

```bash
python3 02_fetch_warc.py             # ~1 min  (WARC byte-range fetches with 8 workers)
python3 03_analyze_wcag.py           # ~2 min  (colour extraction + analysis)
python3 04_generate_report.py        # ~2 sec  (summary statistics)
```

Or use the wrapper:

```bash
./run.sh                             # Query existing ccindex table
./run.sh --setup                     # Create personal table first
./run.sh --database=my_wcag --setup  # Use personal namespace
./run.sh sql                         # Print SQL only
./run.sh csv path/to/results.csv     # Import CSV
```

## Output

- `data/domains-top-500.csv` -- Input domain list with rankings
- `data/index_results.json` -- Columnar Index lookup results (WARC filename, offset, length)
- `data/warc_html/` -- Extracted HTML files from WARC records
- `output/wcag_results.json` -- Per-domain WCAG analysis results
- `output/wcag_summary.json` -- Aggregate statistics
- `output/wcag_report.csv` -- Tabular summary for spreadsheet use
- `wcag-dashboard.html` -- Interactive results dashboard

## Dashboard

The interactive dashboard (`wcag-dashboard.html`) visualises the audit results across four tabs: Overview, Distribution, By Category, and Notable Sites. It is a standalone HTML file with no external dependencies beyond Google Fonts. The dashboard itself passes WCAG 2.1 Level AA colour contrast on all text/background pairings.

## WCAG AA Thresholds

| Element | Minimum contrast ratio |
|---------|----------------------|
| Normal text (< 18pt, or < 14pt bold) | 4.5:1 |
| Large text (>= 18pt, or >= 14pt bold) | 3:1 |
| UI components and graphical objects | 3:1 |

## Methodology Notes

- Colour extraction is **static**: it parses CSS from the archived HTML without executing JavaScript.
  This means dynamically injected styles are not captured, but all inline styles, embedded
  `<style>` blocks, and `style` attributes are analysed.
- When only a foreground colour is specified without an explicit background, white (`#FFFFFF`) is assumed.
- When only a background colour is specified without explicit foreground text, black (`#000000`) is assumed.
- Named CSS colours (e.g., `red`, `navy`, `cornflowerblue`) are fully supported.
- Shorthand hex colours (e.g., `#fff`) are expanded to full form.
- `rgb()`, `rgba()`, `hsl()`, and `hsla()` functions are parsed.
- The crawl used is CC-MAIN-2026-08, Common Crawl's February 2026 crawl.

## Crawl Reference

- **Crawl ID**: CC-MAIN-2026-08
- **Domain ranking source**: [CC Crawl Statistics](https://commoncrawl.github.io/cc-crawl-statistics/plots/domains)
- **Columnar Index**: `s3://commoncrawl/cc-index/table/cc-main/warc/` (queried via Amazon Athena)
- **WARC data**: `https://data.commoncrawl.org/`

## Licence

- This code is released under the MIT Licence.
- Site content is dedicated to the public domain under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/).
- Common Crawl data is available under the [Common Crawl Terms of Use](https://commoncrawl.org/terms-of-use).
