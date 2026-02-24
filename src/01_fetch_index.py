#!/usr/bin/env python3
"""
Step 1: Query Common Crawl's Columnar Index via Amazon Athena.

Finds archived homepage captures for the top 500 domains in a single SQL pass
using the Parquet-based Columnar Index at s3://commoncrawl/cc-index/table/cc-main/warc/.

Supports three modes:
  sql   Print the Athena SQL query to stdout (run it yourself in the console)
  csv   Import results from a CSV downloaded from the Athena console
  auto  Execute the query directly via pyathena (requires AWS credentials)

Usage:
    python3 01_fetch_index.py sql [--crawl CC-MAIN-2026-08]
    python3 01_fetch_index.py csv path/to/athena-results.csv
    python3 01_fetch_index.py auto [--crawl CC-MAIN-2026-08] [--database ccindex]

Environment variables (auto mode):
    ATHENA_OUTPUT    S3 path for query results (required)
    ATHENA_DATABASE  Athena database name (override for --database)
"""

import json
import csv
import os
import sys
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
DOMAIN_CSV = os.path.join(DATA_DIR, "domains-top-500.csv")
OUTPUT_FILE = os.path.join(DATA_DIR, "index_results.json")


def load_domains():
    """Load the top 500 domain list."""
    domains = []
    with open(DOMAIN_CSV, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            domains.append(row["domain"])
    return domains


def build_query(domains, crawl_id, database="ccindex"):
    """
    Build the Athena SQL query to find one homepage capture per domain.

    Preferences (via ROW_NUMBER window):
      1. www or bare domain over deep subdomains
      2. HTTPS over HTTP
      3. Most recent capture
    """
    domain_list = ", ".join(f"'{d}'" for d in domains)

    return f"""SELECT
    url_host_registered_domain AS domain,
    url,
    CAST(fetch_time AS VARCHAR) AS fetch_time,
    warc_filename,
    warc_record_offset,
    warc_record_length,
    content_mime_detected,
    content_digest
FROM (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY url_host_registered_domain
            ORDER BY
                CASE
                    WHEN url_host_name = url_host_registered_domain
                         OR url_host_name = 'www.' || url_host_registered_domain
                    THEN 0 ELSE 1
                END,
                CASE WHEN url_protocol = 'https' THEN 0 ELSE 1 END,
                fetch_time DESC
        ) AS rn
    FROM {database}.ccindex
    WHERE crawl = '{crawl_id}'
      AND subset = 'warc'
      AND fetch_status = 200
      AND url_path = '/'
      AND content_mime_detected = 'text/html'
      AND url_host_registered_domain IN ({domain_list})
)
WHERE rn = 1"""


def parse_athena_rows(rows):
    """
    Convert Athena result rows into the index_results.json format
    expected by 02_fetch_warc.py.
    """
    results = []
    for row in rows:
        results.append({
            "status": "found",
            "domain": row["domain"],
            "url": row["url"],
            "timestamp": row.get("fetch_time", ""),
            "filename": row["warc_filename"],
            "offset": int(row["warc_record_offset"]),
            "length": int(row["warc_record_length"]),
            "mime": row.get("content_mime_detected", "text/html"),
            "digest": row.get("content_digest", ""),
        })
    return results


def mode_sql(domains, crawl_id, database):
    """Print the SQL query to stdout."""
    query = build_query(domains, crawl_id, database)
    print(query)
    print(f"\n-- Crawl: {crawl_id}")
    print(f"-- Database: {database}")
    print(f"-- Domains: {len(domains)}")
    print(f"-- Run this in the Athena console, download the CSV, then:")
    print(f"--   python3 01_fetch_index.py csv path/to/results.csv")


def mode_csv(csv_path, domains):
    """Import results from a downloaded Athena CSV."""
    if not os.path.exists(csv_path):
        print(f"Error: file not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    rows = []
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    print(f"Read {len(rows)} rows from {csv_path}")

    results = parse_athena_rows(rows)

    # Mark domains not found in results
    found_domains = {r["domain"] for r in results}
    for domain in domains:
        if domain not in found_domains:
            results.append({"status": "not_found", "domain": domain})

    save_results(results, domains)


def mode_auto(domains, crawl_id, database, athena_output):
    """Execute query via pyathena."""
    try:
        from pyathena import connect
    except ImportError:
        print("Error: pyathena is required for auto mode.", file=sys.stderr)
        print("  pip install pyathena", file=sys.stderr)
        sys.exit(1)

    query = build_query(domains, crawl_id, database)

    print(f"Connecting to Athena (database: {database})...")
    print(f"Output location: {athena_output}")

    conn = connect(
        s3_staging_dir=athena_output,
        schema_name=database,
    )

    print(f"Running query against {crawl_id} ({len(domains)} domains)...")
    print("  This typically scans 100-300 GB and takes 30-90 seconds.")

    cursor = conn.cursor()
    cursor.execute(query)

    columns = [desc[0] for desc in cursor.description]
    rows = []
    for row in cursor:
        rows.append(dict(zip(columns, row)))

    print(f"Query returned {len(rows)} results")
    cursor.close()
    conn.close()

    results = parse_athena_rows(rows)

    # Mark domains not found in results
    found_domains = {r["domain"] for r in results}
    for domain in domains:
        if domain not in found_domains:
            results.append({"status": "not_found", "domain": domain})

    save_results(results, domains)


def save_results(results, domains):
    """Save results and print summary."""
    os.makedirs(DATA_DIR, exist_ok=True)

    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2)

    found = sum(1 for r in results if r["status"] == "found")
    not_found = sum(1 for r in results if r["status"] == "not_found")

    print(f"\nDone. Found: {found}/{len(domains)}, Not found: {not_found}")
    print(f"Results saved to {OUTPUT_FILE}")


def main():
    parser = argparse.ArgumentParser(
        description="Query Columnar Index for homepage captures via Athena",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
modes:
  sql                       Print the SQL query (run it in the Athena console)
  csv <path>                Import results from a downloaded Athena CSV
  auto                      Run the query via pyathena (needs AWS credentials)

examples:
  %(prog)s sql
  %(prog)s sql --crawl CC-MAIN-2025-51
  %(prog)s csv athena-results.csv
  %(prog)s auto
  %(prog)s auto --database my_wcag
""",
    )
    parser.add_argument("mode", choices=["sql", "csv", "auto"],
                        help="Query mode: sql, csv, or auto")
    parser.add_argument("csv_path", nargs="?", default=None,
                        help="Path to Athena results CSV (csv mode only)")
    parser.add_argument("--crawl", default="CC-MAIN-2026-08",
                        help="Common Crawl crawl ID (default: CC-MAIN-2026-08)")
    parser.add_argument("--database", default=None,
                        help="Athena database name (default: ccindex)")
    args = parser.parse_args()

    # Resolve database: CLI flag > env var > default
    database = args.database or os.environ.get("ATHENA_DATABASE", "ccindex")

    domains = load_domains()
    print(f"Loaded {len(domains)} domains from {DOMAIN_CSV}")

    if args.mode == "sql":
        mode_sql(domains, args.crawl, database)

    elif args.mode == "csv":
        if not args.csv_path:
            parser.error("csv mode requires a file path: 01_fetch_index.py csv <path>")
        mode_csv(args.csv_path, domains)

    elif args.mode == "auto":
        athena_output = os.environ.get("ATHENA_OUTPUT")
        if not athena_output:
            print("Error: ATHENA_OUTPUT environment variable is required for auto mode.",
                  file=sys.stderr)
            print("  export ATHENA_OUTPUT=s3://your-bucket/athena-results/",
                  file=sys.stderr)
            sys.exit(1)
        mode_auto(domains, args.crawl, database, athena_output)


if __name__ == "__main__":
    main()
