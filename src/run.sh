#!/bin/bash
# WCAG 2.1/2.2 Level AA Colour Contrast Audit Pipeline
# Analyses the top 500 domains from Common Crawl's CC-MAIN-2026-08 crawl
#
# Usage: ./run.sh [--crawl CC-MAIN-2026-08] [--workers 4]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CRAWL="${1:-CC-MAIN-2026-08}"
WORKERS="${2:-4}"

echo "============================================="
echo "WCAG AA Colour Contrast Audit Pipeline"
echo "Crawl: $CRAWL"
echo "Workers: $WORKERS"
echo "============================================="
echo ""

cd "$SCRIPT_DIR"

echo "Step 1/4: Querying Columnar Index for homepage captures..."
echo "  (This queries the Common Crawl Columnar Index via Athena)"
python3 01_fetch_index.py --crawl "$CRAWL" --workers "$WORKERS" --delay 0.5 --resume
echo ""

echo "Step 2/4: Fetching HTML from WARC archives..."
echo "  (This fetches archived pages from data.commoncrawl.org)"
python3 02_fetch_warc.py --workers 8 --delay 0.1 --resume
echo ""

echo "Step 3/4: Analysing colour contrast compliance..."
python3 03_analyze_wcag.py --workers 8
echo ""

echo "Step 4/4: Generating summary report..."
python3 04_generate_report.py
echo ""

echo "============================================="
echo "Pipeline complete!"
echo ""
echo "Output files:"
echo "  output/wcag_results.json         Per-domain results"
echo "  output/wcag_results_full.json    Full results with all pairings"
echo "  output/wcag_summary.json         Aggregate statistics"
echo "  output/wcag_report.csv           Spreadsheet export"
echo "============================================="
