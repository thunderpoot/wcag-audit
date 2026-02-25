#!/usr/bin/env python3
"""
Step 4: Generate aggregate statistics and summary report.

Reads the per-domain WCAG analysis results and produces:
  - Aggregate statistics (mean/median pass rates, distribution buckets)
  - Category-level breakdowns (education, government, commercial, etc.)
  - Lists of worst offenders and fully compliant sites
  - CSV export for spreadsheet use

Usage:
    python3 04_generate_report.py
"""

import json
import csv
import os
import sys
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
RESULTS_FILE = os.path.join(OUTPUT_DIR, "wcag_results.json")
SUMMARY_FILE = os.path.join(OUTPUT_DIR, "wcag_summary.json")
CSV_FILE = os.path.join(OUTPUT_DIR, "wcag_report.csv")


def categorise_domain(domain):
    """Categorise a domain by its type based on TLD and known patterns."""
    d = domain.lower()

    # Education
    edu_tlds = (".edu", ".ac.uk", ".ac.jp", ".ac.kr", ".ac.at", ".ac.za",
                ".ac.ir", ".ac.rs", ".edu.tw", ".edu.au", ".edu.ar",
                ".edu.pl", ".edu.br")
    if any(d.endswith(t) for t in edu_tlds) or ".edu." in d:
        return "Education"

    # Government
    gov_tlds = (".gov", ".gov.au", ".gov.uk", ".go.jp", ".gouv.fr",
                ".gouv.qc.ca", ".gov.ru", ".gov.sk", ".gov.bc.ca",
                ".admin.ch", ".gc.ca", ".mil")
    if any(d.endswith(t) for t in gov_tlds) or ".gov" in d:
        return "Government"

    # Wikimedia/Open knowledge
    wiki_domains = ("wikipedia.org", "wiktionary.org", "wikimedia.org",
                    "wikisource.org", "wikibooks.org", "wikiquote.org",
                    "wikinews.org", "wikidot.com", "wikivoyage.org",
                    "wikiversity.org", "wikileaks.org")
    if any(d == w or d.endswith("." + w) for w in wiki_domains):
        return "Open Knowledge"

    # Research/Academic organisations
    research_domains = ("nih.gov", "nasa.gov", "noaa.gov", "nist.gov",
                        "cern.ch", "cnrs.fr", "mpg.de", "worldbank.org",
                        "un.org", "fao.org", "si.edu")
    if d in research_domains:
        return "Research"

    # Technology
    tech_domains = ("github.com", "github.io", "google.com", "microsoft.com",
                    "apple.com", "mozilla.org", "adobe.com", "oracle.com",
                    "ibm.com", "redhat.com", "debian.org", "ubuntu.com",
                    "fedoraproject.org", "apache.org", "freebsd.org",
                    "android.com", "atlassian.net", "atlassian.com",
                    "salesforce.com", "sap.com", "kde.org", "opensuse.org",
                    "eclipse.org", "mathworks.com", "googlesource.com",
                    "launchpad.net")
    if d in tech_domains:
        return "Technology"

    # Hosting/Platform
    platform_domains = ("blogspot.com", "wordpress.org", "hatenablog.com",
                        "substack.com", "wixsite.com", "wix.com",
                        "weebly.com", "neocities.org", "netlify.app",
                        "herokuapp.com", "azurewebsites.net", "web.app",
                        "appspot.com", "cloudfront.net", "firebaseapp.com",
                        "shopify.com", "godaddy.com", "over-blog.com",
                        "tistory.com", "seesaa.net", "exblog.jp",
                        "cocolog-nifty.com", "livedoor.biz", "livedoor.blog",
                        "livejournal.com", "hatenablog.jp", "hateblo.jp",
                        "hatena.ne.jp", "blog.jp", "ning.com",
                        "sakura.ne.jp", "xrea.com", "pixnet.net")
    if d in platform_domains:
        return "Hosting/Platform"

    # E-commerce
    ecommerce_domains = ("amazon.com", "alibaba.com", "made-in-china.com",
                         "rakuten.co.jp", "shein.com", "banggood.com",
                         "shop-pro.jp", "jd.com")
    if d in ecommerce_domains:
        return "E-commerce"

    # News/Media
    media_domains = ("indiatimes.com", "rbc.ru", "voanews.com", "elpais.com",
                     "chinadaily.com.cn", "itmedia.co.jp", "hindustantimes.com",
                     "obozrevatel.com", "cbsnews.com", "espn.com", "ndtv.com",
                     "cnet.com", "ria.ru", "err.ee", "tvp.pl", "as.com")
    if d in media_domains:
        return "News/Media"

    # European institutions
    if d.endswith(".eu") or d == "europa.eu":
        return "EU Institutions"

    return "Other"


def compute_statistics(results):
    """Compute aggregate statistics from per-domain results."""
    analysed = [r for r in results if r.get("status") == "analysed"]
    with_colors = [r for r in analysed if r.get("total_pairings", 0) > 0]

    if not with_colors:
        return {"error": "No domains with color data found"}

    # Pass rates
    normal_rates = [r["pass_rate_normal"] for r in with_colors
                    if r.get("pass_rate_normal") is not None]
    large_rates = [r["pass_rate_large"] for r in with_colors
                   if r.get("pass_rate_large") is not None]

    # Distribution buckets
    buckets = {"0-25%": 0, "25-50%": 0, "50-75%": 0, "75-90%": 0,
               "90-99%": 0, "100%": 0}
    for rate in normal_rates:
        if rate == 100:
            buckets["100%"] += 1
        elif rate >= 90:
            buckets["90-99%"] += 1
        elif rate >= 75:
            buckets["75-90%"] += 1
        elif rate >= 50:
            buckets["50-75%"] += 1
        elif rate >= 25:
            buckets["25-50%"] += 1
        else:
            buckets["0-25%"] += 1

    # Category analysis
    categories = defaultdict(lambda: {"domains": [], "rates": []})
    for r in with_colors:
        cat = categorise_domain(r["domain"])
        categories[cat]["domains"].append(r["domain"])
        if r.get("pass_rate_normal") is not None:
            categories[cat]["rates"].append(r["pass_rate_normal"])

    cat_summary = {}
    for cat, data in sorted(categories.items()):
        rates = data["rates"]
        cat_summary[cat] = {
            "count": len(data["domains"]),
            "avg_pass_rate": round(sum(rates) / len(rates), 1) if rates else None,
            "median_pass_rate": round(sorted(rates)[len(rates) // 2], 1) if rates else None,
            "fully_compliant": sum(1 for r in rates if r == 100),
            "below_50_pct": sum(1 for r in rates if r < 50),
        }

    # Worst offenders (lowest pass rate, at least some pairings)
    worst = sorted(with_colors, key=lambda r: (r.get("pass_rate_normal", 100)))
    worst_list = []
    for r in worst[:20]:
        entry = {
            "domain": r["domain"],
            "pass_rate_normal": r["pass_rate_normal"],
            "total_pairings": r["total_pairings"],
            "fail_normal": r["fail_normal"],
            "worst_ratio": r.get("worst_ratio"),
        }
        if r.get("worst_pairings"):
            entry["example_failure"] = {
                "foreground": r["worst_pairings"][0].get("foreground"),
                "background": r["worst_pairings"][0].get("background"),
                "ratio": r["worst_pairings"][0].get("ratio"),
            }
        worst_list.append(entry)

    # Fully compliant sites
    compliant = [r for r in with_colors if r.get("pass_rate_normal") == 100]
    compliant_list = [{
        "domain": r["domain"],
        "total_pairings": r["total_pairings"],
        "mean_ratio": r.get("mean_ratio"),
    } for r in sorted(compliant, key=lambda r: -r.get("total_pairings", 0))]

    # Contrast ratio statistics
    all_ratios = []
    for r in with_colors:
        if r.get("worst_ratio") is not None:
            all_ratios.append(r["worst_ratio"])

    sorted_normal = sorted(normal_rates)

    summary = {
        "crawl_id": "CC-MAIN-2026-08",
        "total_domains_in_list": len(results),
        "domains_analysed": len(analysed),
        "domains_with_color_data": len(with_colors),
        "domains_no_color_data": len(analysed) - len(with_colors),
        "domains_failed": len(results) - len(analysed),

        "total_unique_pairings": sum(r["total_pairings"] for r in with_colors),
        "total_failing_normal": sum(r["fail_normal"] for r in with_colors),
        "total_failing_large": sum(r["fail_large"] for r in with_colors),

        "mean_pass_rate_normal": round(sum(normal_rates) / len(normal_rates), 1),
        "median_pass_rate_normal": round(sorted_normal[len(sorted_normal) // 2], 1),
        "min_pass_rate_normal": sorted_normal[0] if sorted_normal else None,
        "max_pass_rate_normal": sorted_normal[-1] if sorted_normal else None,

        "mean_pass_rate_large": round(sum(large_rates) / len(large_rates), 1) if large_rates else None,
        "median_pass_rate_large": round(sorted(large_rates)[len(large_rates) // 2], 1) if large_rates else None,

        "pct_fully_compliant_normal": round(len(compliant) / len(with_colors) * 100, 1),
        "pct_above_90_normal": round(
            sum(1 for r in normal_rates if r >= 90) / len(normal_rates) * 100, 1),
        "pct_above_75_normal": round(
            sum(1 for r in normal_rates if r >= 75) / len(normal_rates) * 100, 1),
        "pct_below_50_normal": round(
            sum(1 for r in normal_rates if r < 50) / len(normal_rates) * 100, 1),

        "pass_rate_distribution": buckets,
        "category_analysis": cat_summary,

        "worst_offenders": worst_list,
        "fully_compliant_sites": compliant_list[:30],

        "min_worst_ratio_across_sites": round(min(all_ratios), 2) if all_ratios else None,
    }

    return summary


def export_csv(results):
    """Export results as CSV for spreadsheet use."""
    analysed = [r for r in results if r.get("status") == "analysed"
                and r.get("total_pairings", 0) > 0]

    with open(CSV_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "rank", "domain", "category", "total_pairings",
            "pass_normal", "fail_normal", "pass_rate_normal",
            "pass_large", "fail_large", "pass_rate_large",
            "worst_ratio", "median_ratio", "mean_ratio",
            "fully_compliant_normal", "fully_compliant_large",
        ])

        for i, r in enumerate(
                sorted(analysed, key=lambda x: x["domain"]), 1):
            writer.writerow([
                i,
                r["domain"],
                categorise_domain(r["domain"]),
                r.get("total_pairings", 0),
                r.get("pass_normal", 0),
                r.get("fail_normal", 0),
                r.get("pass_rate_normal", ""),
                r.get("pass_large", 0),
                r.get("fail_large", 0),
                r.get("pass_rate_large", ""),
                r.get("worst_ratio", ""),
                r.get("median_ratio", ""),
                r.get("mean_ratio", ""),
                "Yes" if r.get("pass_rate_normal") == 100 else "No",
                "Yes" if r.get("pass_rate_large") == 100 else "No",
            ])

    print(f"CSV exported to {CSV_FILE}")


def main():
    # Load results
    with open(RESULTS_FILE, "r") as f:
        results = json.load(f)

    print(f"Loaded {len(results)} domain results")

    # Compute statistics
    summary = compute_statistics(results)

    # Save summary
    with open(SUMMARY_FILE, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Summary saved to {SUMMARY_FILE}")

    # Export CSV
    export_csv(results)

    # Print key findings
    print("\n" + "=" * 60)
    print("WCAG 2.1/2.2 Level AA Color Contrast Audit")
    print(f"Crawl: {summary.get('crawl_id', 'N/A')}")
    print("=" * 60)

    print(f"\nDomains analysed:        {summary.get('domains_analysed', 0)}")
    print(f"With color data:           {summary.get('domains_with_color_data', 0)}")
    print(f"No color data:             {summary.get('domains_no_color_data', 0)}")
    print(f"Failed to process:         {summary.get('domains_failed', 0)}")

    print(f"\nTotal color pairings:    {summary.get('total_unique_pairings', 0)}")
    print(f"Failing (normal text):     {summary.get('total_failing_normal', 0)}")
    print(f"Failing (large text):      {summary.get('total_failing_large', 0)}")

    print(f"\nMean pass rate (normal): {summary.get('mean_pass_rate_normal', 'N/A')}%")
    print(f"Median pass rate:          {summary.get('median_pass_rate_normal', 'N/A')}%")
    print(f"Fully compliant:           {summary.get('pct_fully_compliant_normal', 'N/A')}%")
    print(f"Above 90% pass:            {summary.get('pct_above_90_normal', 'N/A')}%")
    print(f"Below 50% pass:            {summary.get('pct_below_50_normal', 'N/A')}%")

    if summary.get("pass_rate_distribution"):
        print(f"\nPass rate distribution:")
        for bucket, count in summary["pass_rate_distribution"].items():
            bar = "#" * min(count, 50)
            print(f"  {bucket:>8}: {count:>4} {bar}")

    if summary.get("category_analysis"):
        print(f"\nBy category:")
        for cat, data in sorted(summary["category_analysis"].items(),
                                key=lambda x: -(x[1].get("avg_pass_rate") or 0)):
            print(f"  {cat:>20}: {data['count']:>3} domains, "
                  f"avg {data.get('avg_pass_rate', 'N/A')}% pass, "
                  f"{data.get('fully_compliant', 0)} fully compliant")

    if summary.get("worst_offenders"):
        print(f"\nWorst offenders (normal text):")
        for w in summary["worst_offenders"][:10]:
            print(f"  {w['domain']:>30}: {w['pass_rate_normal']}% pass "
                  f"({w['fail_normal']} failures)")

    if summary.get("fully_compliant_sites"):
        print(f"\nFully compliant sites ({len(summary['fully_compliant_sites'])} total):")
        for c in summary["fully_compliant_sites"][:10]:
            print(f"  {c['domain']:>30}: {c['total_pairings']} pairings checked")


if __name__ == "__main__":
    main()
