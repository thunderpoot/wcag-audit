#!/bin/bash
# WCAG 2.1/2.2 Level AA Colour Contrast Audit Pipeline
# Analyses the top 500 domains from Common Crawl using the Columnar Index via Athena
#
# Usage:
#   ./run.sh                                   Full pipeline (auto mode, needs pyathena + AWS creds)
#   ./run.sh sql                               Print the Athena SQL query and exit
#   ./run.sh csv path/to/athena-results.csv    Import from Athena console CSV, then run pipeline
#
# Environment variables:
#   ATHENA_OUTPUT    S3 path for Athena query results (required for auto mode)
#   ATHENA_DATABASE  Athena database name (default: ccindex)
#   CRAWL_ID         Common Crawl crawl identifier (default: CC-MAIN-2026-08)
#   WARC_WORKERS     Parallel workers for WARC fetches (default: 8)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CRAWL_ID="${CRAWL_ID:-CC-MAIN-2026-08}"
WARC_WORKERS="${WARC_WORKERS:-8}"
MODE="${1:-auto}"

cd "$SCRIPT_DIR"

echo "============================================="
echo "WCAG AA Colour Contrast Audit Pipeline"
echo "Crawl:   $CRAWL_ID"
echo "Workers: $WARC_WORKERS"
echo "============================================="
echo ""

case "${MODE}" in
    sql)
        echo "Step 1: Printing Athena SQL query"
        echo ""
        python3 01_fetch_index.py sql --crawl "$CRAWL_ID"
        exit 0
        ;;
    csv)
        CSV_PATH="${2:?Usage: ./run.sh csv <path/to/athena-results.csv>}"
        echo "Step 1/4: Importing Athena results from ${CSV_PATH}..."
        python3 01_fetch_index.py csv "$CSV_PATH"
        ;;
    auto)
        if [ -z "${ATHENA_OUTPUT:-}" ]; then
            echo "Error: ATHENA_OUTPUT must be set for auto mode." >&2
            echo "" >&2
            echo "  export ATHENA_OUTPUT=s3://your-bucket/athena-results/" >&2
            echo "" >&2
            echo "Or use a different mode:" >&2
            echo "  ./run.sh sql                         Print the SQL query" >&2
            echo "  ./run.sh csv path/to/results.csv     Import from CSV" >&2
            exit 1
        fi
        echo "Step 1/4: Querying Columnar Index via Athena..."
        python3 01_fetch_index.py auto --crawl "$CRAWL_ID"
        ;;
    *)
        echo "Usage: ./run.sh [sql | csv <path> | auto]" >&2
        echo "" >&2
        echo "Modes:" >&2
        echo "  sql    Print the Athena SQL query and exit" >&2
        echo "  csv    Import a downloaded Athena CSV, then run full pipeline" >&2
        echo "  auto   Query Athena directly via pyathena (default)" >&2
        echo "" >&2
        echo "Environment variables:" >&2
        echo "  ATHENA_OUTPUT    S3 output path (required for auto mode)" >&2
        echo "  ATHENA_DATABASE  Athena database name (default: ccindex)" >&2
        echo "  CRAWL_ID         Crawl identifier (default: CC-MAIN-2026-08)" >&2
        echo "  WARC_WORKERS     Parallel WARC fetch workers (default: 8)" >&2
        exit 1
        ;;
esac

echo ""
echo "Step 2/4: Fetching HTML from WARC archives (${WARC_WORKERS} workers)..."
echo "  (byte-range requests to data.commoncrawl.org)"
python3 02_fetch_warc.py --workers "$WARC_WORKERS" --delay 0.1 --resume
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
