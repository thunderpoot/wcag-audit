# Athena Setup

![Athena](https://i.ibb.co/MDz8CpQL/athena-sm.png)

# Athena Setup

The pipeline queries Common Crawl's Columnar Index via Amazon Athena. You have three options for running the index lookup, depending on your AWS access.

## Option 1: Print the SQL and run it yourself

No AWS CLI configuration needed. The script prints the query; you paste it into the [Athena console](https://console.aws.amazon.com/athena/) and download the CSV result.

```
./run.sh sql
```

To target a different crawl:

```
CRAWL_ID=CC-MAIN-2025-51 ./run.sh sql
```

This prints the full SQL query to stdout. Copy it, run it in the Athena Query Editor (making sure the `ccindex` database is selected), then download the result CSV and feed it back in:

```
./run.sh csv path/to/downloaded-results.csv
```

If you don't already have a `ccindex` database in your Athena catalogue, see "Creating your own table" below.

## Option 2: Run directly with pyathena

Requires Python, `pyathena`, AWS credentials, and an S3 bucket for query output.

### Prerequisites

```
pip install pyathena
```

Your AWS credentials need these permissions:
- `athena:StartQueryExecution`, `athena:GetQueryExecution`, `athena:GetQueryResults`
- `s3:PutObject`, `s3:GetObject` on your output bucket
- `glue:GetTable`, `glue:GetPartitions` on the `ccindex` table

**Note:** `s3:GetObject` and `s3:ListBucket` on `s3://commoncrawl/cc-index/*` are already fine because the bucket is public.

### Running

```
export ATHENA_OUTPUT=s3://your-bucket/athena-results/
./run.sh
```

### Configuration

All options are set via environment variables:

| Variable | Default | Description |
|---|---|---|
| `ATHENA_OUTPUT` | *(required for auto mode)* | S3 path for Athena query results |
| `ATHENA_DATABASE` | `ccindex` | Athena database containing the `ccindex` table |
| `CRAWL_ID` | `CC-MAIN-2026-08` | Common Crawl crawl identifier |
| `WORKERS` | `20` | Number of parallel workers for WARC fetches |

Examples:

```
# Run against December 2025 crawl with 10 workers
CRAWL_ID=CC-MAIN-2025-51 WORKERS=10 ./run.sh

# Use a personal Athena database
ATHENA_DATABASE=my_wcag ./run.sh
```

## Creating your own table

If you don't have access to an existing `ccindex` table, create one in the Athena console (or via pyathena). This creates a personal external table that points at Common Crawl's public S3 data — no data is copied.

```sql
CREATE DATABASE IF NOT EXISTS my_wcag;

CREATE EXTERNAL TABLE IF NOT EXISTS my_wcag.ccindex (
  url_surtkey                STRING,
  url                        STRING,
  url_host_name              STRING,
  url_host_tld               STRING,
  url_host_2nd_last_part     STRING,
  url_host_3rd_last_part     STRING,
  url_host_4th_last_part     STRING,
  url_host_5th_last_part     STRING,
  url_host_registry_suffix   STRING,
  url_host_registered_domain STRING,
  url_host_private_suffix    STRING,
  url_host_private_domain    STRING,
  url_protocol               STRING,
  url_port                   INT,
  url_path                   STRING,
  url_query                  STRING,
  fetch_time                 TIMESTAMP,
  fetch_status               SMALLINT,
  fetch_redirect             STRING,
  content_digest             STRING,
  content_mime_type          STRING,
  content_mime_detected      STRING,
  content_charset            STRING,
  content_languages          STRING,
  content_truncated          STRING,
  warc_filename              STRING,
  warc_record_offset         INT,
  warc_record_length         INT,
  warc_segment               STRING
)
PARTITIONED BY (
  crawl  STRING,
  subset STRING
)
STORED AS PARQUET
LOCATION 's3://commoncrawl/cc-index/table/cc-main/warc/';
```

Then discover partitions. You have two options:

### All partitions

Registers every crawl. Can take a minute or two.

```sql
MSCK REPAIR TABLE my_wcag.ccindex;
```

### Single partition (faster)

If you only need one crawl, add just that partition:

```sql
ALTER TABLE my_wcag.ccindex ADD IF NOT EXISTS
  PARTITION (crawl = 'CC-MAIN-2026-08', subset = 'warc')
  LOCATION 's3://commoncrawl/cc-index/table/cc-main/warc/crawl=CC-MAIN-2026-08/subset=warc/';
```

After creating the table, set `ATHENA_DATABASE=my_wcag` when running the pipeline.

## Costs

Athena charges $5 per TB scanned. The query for this pipeline typically scans 100–300 GB of columnar data, costing roughly $0.50–$1.50 per run. Using partition filters (`crawl` and `subset`) keeps scans efficient.

The S3 output bucket stores a small CSV (a few hundred KB) per query run.

WARC fetches in step 2 use HTTP byte-range requests to `data.commoncrawl.org` and do not incur any S3 costs on your account.
