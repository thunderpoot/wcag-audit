#!/usr/bin/env python3
"""
Step 1: Query Common Crawl's Columnar Index to find archived homepage captures.

For each of the top 500 domains, queries the Columnar Index for CC-MAIN-2026-08
to find a successful (HTTP 200) capture of the homepage. Stores the WARC
filename, byte offset, and record length needed to fetch the actual content.

Usage:
    python3 01_fetch_index.py [--crawl CC-MAIN-2026-08] [--workers 4] [--delay 0.5]
"""

import json
import csv
import os
import sys
import time
import argparse
import urllib.request
import urllib.parse
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
DOMAIN_CSV = os.path.join(DATA_DIR, "domains-top-500.csv")
OUTPUT_FILE = os.path.join(DATA_DIR, "index_results.json")

INDEX_BASE = "https://index.commoncrawl.org"


def query_index(domain, crawl_id, attempt_urls=None):
    """
    Query the Columnar Index for a domain's homepage.

    Tries multiple URL variants:
      1. https://www.{domain}/
      2. https://{domain}/
      3. http://www.{domain}/
      4. http://{domain}/

    Returns the first successful (status 200, mime text/html) capture found,
    or None if no capture exists.
    """
    if attempt_urls is None:
        attempt_urls = [
            f"https://www.{domain}/",
            f"https://{domain}/",
            f"http://www.{domain}/",
            f"http://{domain}/",
        ]

    api_url = f"{INDEX_BASE}/{crawl_id}-index"

    for url in attempt_urls:
        params = urllib.parse.urlencode({
            "url": url,
            "output": "json",
            "filter": "statuscode:200",
            "filter": "mime:text/html",
            "limit": "1",
        })
        # urllib.parse.urlencode deduplicates 'filter' keys, so build manually
        query = (
            f"url={urllib.parse.quote(url, safe='')}"
            f"&output=json"
            f"&filter=statuscode:200"
            f"&filter=mime:text/html"
            f"&limit=1"
        )
        full_url = f"{api_url}?{query}"

        try:
            req = urllib.request.Request(full_url)
            req.add_header("User-Agent", "cc-wcag-audit/1.0 (research; contact@commoncrawl.org)")
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8").strip()
                if not body:
                    continue
                # The index returns one JSON object per line (NDJSON)
                for line in body.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    if record.get("status") == "200":
                        return {
                            "domain": domain,
                            "url": record.get("url", url),
                            "timestamp": record.get("timestamp", ""),
                            "filename": record["filename"],
                            "offset": int(record["offset"]),
                            "length": int(record["length"]),
                            "mime": record.get("mime", ""),
                            "status": record.get("status", ""),
                            "digest": record.get("digest", ""),
                        }
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
                KeyError, TimeoutError, OSError) as e:
            continue

    return None


def process_domain(args):
    """Process a single domain: index lookup with rate limiting."""
    domain, crawl_id, delay = args
    time.sleep(delay)  # Be polite to the index server
    result = query_index(domain, crawl_id)
    if result:
        return {"status": "found", **result}
    else:
        return {"status": "not_found", "domain": domain}


def main():
    parser = argparse.ArgumentParser(description="Query Columnar Index for homepage captures")
    parser.add_argument("--crawl", default="CC-MAIN-2026-08",
                        help="Common Crawl crawl ID (default: CC-MAIN-2026-08)")
    parser.add_argument("--workers", type=int, default=4,
                        help="Number of concurrent workers (default: 4)")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="Delay in seconds between requests per worker (default: 0.5)")
    parser.add_argument("--resume", action="store_true",
                        help="Skip domains already in output file")
    args = parser.parse_args()

    # Load domain list
    domains = []
    with open(DOMAIN_CSV, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            domains.append(row["domain"])

    print(f"Loaded {len(domains)} domains from {DOMAIN_CSV}")
    print(f"Crawl: {args.crawl}, Workers: {args.workers}, Delay: {args.delay}s")

    # Resume support
    existing = {}
    if args.resume and os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r") as f:
            existing_results = json.load(f)
        existing = {r["domain"]: r for r in existing_results}
        print(f"Resuming: {len(existing)} domains already processed")

    domains_to_process = [d for d in domains if d not in existing]
    print(f"Processing {len(domains_to_process)} domains...")

    results = list(existing.values())
    found = sum(1 for r in results if r.get("status") == "found")
    not_found = sum(1 for r in results if r.get("status") == "not_found")

    work_items = [(d, args.crawl, args.delay) for d in domains_to_process]

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_domain, item): item[0]
                   for item in work_items}

        for i, future in enumerate(as_completed(futures), 1):
            domain = futures[future]
            try:
                result = future.result()
                results.append(result)
                if result["status"] == "found":
                    found += 1
                    print(f"  [{len(results)}/{len(domains)}] {domain}: FOUND "
                          f"({result['timestamp']})")
                else:
                    not_found += 1
                    print(f"  [{len(results)}/{len(domains)}] {domain}: not found")
            except Exception as e:
                not_found += 1
                results.append({"status": "error", "domain": domain, "error": str(e)})
                print(f"  [{len(results)}/{len(domains)}] {domain}: ERROR - {e}")

            # Checkpoint every 50 domains
            if len(results) % 50 == 0:
                with open(OUTPUT_FILE, "w") as f:
                    json.dump(results, f, indent=2)

    # Final save
    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nDone. Found: {found}, Not found: {not_found}")
    print(f"Results saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
