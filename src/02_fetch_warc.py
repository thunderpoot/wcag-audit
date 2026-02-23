#!/usr/bin/env python3
"""
Step 2: Fetch archived HTML content from Common Crawl WARC files.

Uses the index results from step 1 to make byte-range HTTP requests to
data.commoncrawl.org, extracting just the HTML content from each WARC record.

Usage:
    python3 02_fetch_warc.py [--workers 8] [--delay 0.1]
"""

import json
import gzip
import os
import sys
import time
import argparse
import urllib.request
import urllib.error
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
INDEX_FILE = os.path.join(DATA_DIR, "index_results.json")
HTML_DIR = os.path.join(DATA_DIR, "warc_html")
WARC_DATA_BASE = "https://data.commoncrawl.org"


def extract_html_from_warc(raw_data):
    """
    Extract HTML content from a raw WARC record.

    A WARC response record contains:
      1. WARC headers (ending with blank line)
      2. HTTP response headers (ending with blank line)
      3. HTTP response body (the HTML)
    """
    # Decompress if gzipped
    try:
        data = gzip.decompress(raw_data)
    except (gzip.BadGzipFile, OSError):
        data = raw_data

    # Find the HTTP response body
    # WARC records have: WARC headers \r\n\r\n HTTP response \r\n\r\n body
    # Split on double CRLF to find sections
    text = data

    # Find end of WARC headers
    warc_end = text.find(b"\r\n\r\n")
    if warc_end == -1:
        warc_end = text.find(b"\n\n")
        sep_len = 2
    else:
        sep_len = 4

    if warc_end == -1:
        return None

    http_start = warc_end + sep_len

    # Find end of HTTP headers
    http_end = text.find(b"\r\n\r\n", http_start)
    if http_end == -1:
        http_end = text.find(b"\n\n", http_start)
        body_start = http_end + 2
    else:
        body_start = http_end + 4

    if http_end == -1:
        return None

    # Extract HTTP headers to determine encoding
    http_headers = text[http_start:http_end].decode("utf-8", errors="replace")
    encoding = "utf-8"  # default
    for line in http_headers.split("\n"):
        if line.lower().startswith("content-type:"):
            if "charset=" in line.lower():
                charset_part = line.lower().split("charset=")[-1].strip().rstrip(";")
                encoding = charset_part.strip()
                break

    # Extract body
    body = text[body_start:]

    # Check for chunked transfer encoding and handle it
    if b"transfer-encoding: chunked" in text[http_start:http_end].lower():
        body = _decode_chunked(body)

    # Decode to string
    try:
        return body.decode(encoding, errors="replace")
    except (LookupError, UnicodeDecodeError):
        return body.decode("utf-8", errors="replace")


def _decode_chunked(data):
    """Decode HTTP chunked transfer encoding."""
    result = bytearray()
    pos = 0
    while pos < len(data):
        # Find end of chunk size line
        line_end = data.find(b"\r\n", pos)
        if line_end == -1:
            break
        # Parse chunk size (hex)
        size_str = data[pos:line_end].decode("ascii", errors="replace").strip()
        if not size_str:
            pos = line_end + 2
            continue
        try:
            # Handle chunk extensions (semicolon-separated)
            chunk_size = int(size_str.split(";")[0], 16)
        except ValueError:
            break
        if chunk_size == 0:
            break
        chunk_start = line_end + 2
        chunk_end = chunk_start + chunk_size
        result.extend(data[chunk_start:chunk_end])
        pos = chunk_end + 2  # skip trailing \r\n
    return bytes(result)


def fetch_warc_record(domain, filename, offset, length):
    """
    Fetch a single WARC record using a byte-range request.
    Returns the extracted HTML content or None on failure.
    """
    url = f"{WARC_DATA_BASE}/{filename}"
    start_byte = offset
    end_byte = offset + length - 1

    req = urllib.request.Request(url)
    req.add_header("Range", f"bytes={start_byte}-{end_byte}")
    req.add_header("User-Agent", "cc-wcag-audit/1.0 (research; contact@commoncrawl.org)")

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return extract_html_from_warc(raw)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        return None


def process_record(args):
    """Fetch and save a single WARC record."""
    record, delay = args
    time.sleep(delay)

    domain = record["domain"]
    html = fetch_warc_record(
        domain,
        record["filename"],
        record["offset"],
        record["length"]
    )

    if html:
        # Save to file
        safe_name = domain.replace("/", "_").replace(":", "_")
        out_path = os.path.join(HTML_DIR, f"{safe_name}.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        return {"domain": domain, "status": "ok", "size": len(html)}
    else:
        return {"domain": domain, "status": "failed"}


def main():
    parser = argparse.ArgumentParser(description="Fetch HTML from WARC files")
    parser.add_argument("--workers", type=int, default=8,
                        help="Number of concurrent workers (default: 8)")
    parser.add_argument("--delay", type=float, default=0.1,
                        help="Delay between requests per worker (default: 0.1s)")
    parser.add_argument("--resume", action="store_true",
                        help="Skip domains whose HTML already exists")
    args = parser.parse_args()

    # Load index results
    with open(INDEX_FILE, "r") as f:
        index_results = json.load(f)

    # Filter to found records
    records = [r for r in index_results if r.get("status") == "found"]
    print(f"Found {len(records)} domains with index records")

    os.makedirs(HTML_DIR, exist_ok=True)

    # Resume support
    if args.resume:
        existing = set()
        for fname in os.listdir(HTML_DIR):
            if fname.endswith(".html"):
                existing.add(fname[:-5])  # strip .html
        records = [r for r in records
                   if r["domain"].replace("/", "_").replace(":", "_") not in existing]
        print(f"Resuming: skipping already-fetched, {len(records)} remaining")

    print(f"Fetching {len(records)} WARC records (workers={args.workers}, delay={args.delay}s)...")

    successes = 0
    failures = 0
    fetch_log = []

    work_items = [(r, args.delay) for r in records]

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_record, item): item[0]["domain"]
                   for item in work_items}

        for i, future in enumerate(as_completed(futures), 1):
            domain = futures[future]
            try:
                result = future.result()
                fetch_log.append(result)
                if result["status"] == "ok":
                    successes += 1
                    size_kb = result["size"] / 1024
                    print(f"  [{i}/{len(records)}] {domain}: {size_kb:.1f} KB")
                else:
                    failures += 1
                    print(f"  [{i}/{len(records)}] {domain}: FAILED")
            except Exception as e:
                failures += 1
                fetch_log.append({"domain": domain, "status": "error", "error": str(e)})
                print(f"  [{i}/{len(records)}] {domain}: ERROR - {e}")

    # Save fetch log
    log_path = os.path.join(DATA_DIR, "fetch_log.json")
    with open(log_path, "w") as f:
        json.dump(fetch_log, f, indent=2)

    print(f"\nDone. Fetched: {successes}, Failed: {failures}")
    print(f"HTML files saved to {HTML_DIR}")


if __name__ == "__main__":
    main()
