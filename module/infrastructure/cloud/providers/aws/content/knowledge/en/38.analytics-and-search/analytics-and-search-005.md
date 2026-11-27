# Data Loading, Table Distribution, and Query Optimization in Redshift

## Learning Objectives

After this lesson, you will be able to:

- Describe Amazon Redshift's distributed processing architecture and how data is loaded, stored, distributed, and sorted.
- Choose how to load data via `COPY` from Amazon S3, manifests, Parquet, ORC, or text files.
- Design IAM roles, bucket policies, KMS key policies, and network paths for `COPY` jobs.
- Organize input files to leverage MPP, reduce preparation time, and avoid sequential loads.
- Distinguish between staging loads, incremental loads, full refreshes, and how to prevent duplicate batch loads.
- Choose `DISTSTYLE AUTO`, `KEY`, `EVEN`, or `ALL` based on table size, join patterns, and data distribution.
- Choose `SORTKEY AUTO`, compound, or interleaved keys based on predicates and real workloads.
- Understand compression encodings, `ANALYZE`, `VACUUM`, and Automatic Table Optimization.
- Read `EXPLAIN` plans and identify costly broadcasts/redistributions, scans, sorts, joins, and aggregations.
- Optimize SQL, materialized views, workload management, and concurrency.
- Use `SYS` monitoring views to diagnose queries, loads, and table maintenance.
- Build repeatable workflows for data ingestion, quality validation, and performance tuning.

## 1. How Does Amazon Redshift Process Data?

Amazon Redshift is a relational data warehouse built on a massively parallel processing (MPP) architecture. A query is planned and divided into steps executed in parallel across compute nodes and slices. Data is stored by column and split into blocks; each block maintains metadata such as minimum/maximum values so the engine can skip blocks unrelated to filter predicates.

A provisioned cluster has a leader node coordinating queries and compute nodes processing data. Redshift Serverless provides workgroups and namespaces with on-demand managed compute. Both use SQL and share the same principles for table design, data distribution, sort keys, and query optimization; certain system views and administrative actions vary by deployment type.

~~~mermaid
flowchart TD
    U["BI / SQL clients / applications"] --> L["Leader / query coordinator"]
    L --> P["Query plan"]
    P --> C1["Compute node / slices"]
    P --> C2["Compute node / slices"]
    P --> C3["Compute node / slices"]
    C1 --> R["Intermediate results"]
    C2 --> R
    C3 --> R
    R --> L
    L --> U
    S3["Amazon S3 data lake"] -->|COPY / Spectrum| C1
~~~

Performance depends on far more than CPU. A query can be slow because it must move data across nodes, read too many blocks, sort large volumes, rely on stale statistics, or wait for WLM resources.

Three design decisions are tightly coupled:

1. **Load layout:** input files and loading strategies determine `COPY` parallelism.
2. **Table layout:** distribution styles and sort keys determine where rows live and how blocks are ordered.
3. **Query shape:** filters, joins, aggregations, and concurrency determine how much data the engine must read, move, and compute.

## 2. Choosing How to Load Data into Redshift

There are several ways to ingest data into Redshift. Choose based on data source, size, frequency, and target latency.

| Method | When Appropriate | Key Considerations |
|---|---|---|
| `COPY` from Amazon S3 | Large, scheduled, or partitioned batch loads | Leverages MPP; uses IAM roles |
| `COPY` with manifest | Exact file sets across prefixes or buckets | Auditable and tightly controlled file list |
| `COPY` Parquet/ORC | Columnar data from a data lake | Schemas and formats must align; some `COPY` options are restricted |
| Multi-row `INSERT` | Small datasets or application operations | Unsuitable as a substitute for large bulk loads |
| Staging table + `MERGE`/`INSERT` | Incremental loads and upserts | Requires business keys, deduplication, and explicit transactions |
| Amazon Redshift Spectrum | Querying data in S3 without loading everything into local tables | Performance depends on file layout, partitioning, and scan volume |
| Streaming ingestion | Continuous streams from Kinesis or MSK | Differs from batch `COPY`; design around freshness and stream semantics |

For large batches, `COPY` from S3 is typically the first choice because Redshift reads multiple files in parallel. Row-by-row `INSERT`s from an application generate heavy request overhead and underutilize compute.

## 3. Preparing Data Before COPY

A solid ingestion pipeline standardizes data before writing to the warehouse:

1. Validate data schemas and versions.
2. Standardize column names, data types, timezones, and encoding.
3. Check for nulls, duplicates, out-of-range values, and required fields.
4. Split files into evenly sized parts.
5. Write files to batch/date prefixes.
6. Generate a manifest if an exact file list is needed.
7. Execute `COPY` into a staging or target table.
8. Reconcile row counts, load errors, and batch identifiers.
9. Run `MERGE`/`INSERT` into analytics tables.
10. Update statistics and inspect query plans whenever workloads shift significantly.

Keep raw data immutable in S3 so loads are replayable. Never modify files already referenced by a batch load; instead, write a new batch version and track manifests or batch IDs for lineage.

## 4. COPY from Amazon S3

`COPY` accepts an S3 object prefix or a manifest file. With a prefix, Redshift loads every object whose key begins with that prefix. While convenient for daily folders, it can accidentally ingest backup files, temp files, or files from another batch if prefixes are not strictly isolated.

Example target table:

~~~sql
CREATE TABLE stage_orders (
    order_id        BIGINT,
    customer_id     BIGINT,
    order_ts        TIMESTAMP,
    order_status    VARCHAR(30),
    order_amount    DECIMAL(18,2),
    source_batch_id VARCHAR(80)
)
DISTSTYLE AUTO
SORTKEY AUTO;
~~~

Example `COPY` of pipe-delimited files:

~~~sql
COPY stage_orders (
    order_id,
    customer_id,
    order_ts,
    order_status,
    order_amount,
    source_batch_id
)
FROM 's3://company-data-lake/curated/orders/dt=2026-11-19/'
IAM_ROLE 'arn:aws:iam::111122223333:role/RedshiftCopyRole'
REGION 'ap-southeast-1'
DELIMITER '|'
TIMEFORMAT 'auto'
DATEFORMAT 'auto'
EMPTYASNULL
BLANKSASNULL
TRUNCATECOLUMNS
STATUPDATE ON;
~~~

The example assumes source files have six fields, with the final field being a pipeline-added batch ID. If source files lack a batch ID, load into a batch-scoped staging table and stamp the ID during post-`COPY` orchestration; avoid updating the entire table while multiple batches may run concurrently. Omit `TRUNCATECOLUMNS` if string truncation is disallowed by business rules. Do not enable `ACCEPTINVCHARS` or permissive `MAXERROR` limits merely to force loads to succeed—those options can mask data corruption.

`COPY` appends rows to a table. Re-running the same batch can introduce duplicates. Use staging tables, batch IDs, immutable manifests, and idempotent merge/dedup workflows.

### 4.1 S3 Bucket Region

By default, the S3 bucket being `COPY`ed should reside in the same Region as Redshift. You can specify `REGION` when the source sits in another Region, though cross-Region transfers increase latency and can incur data transfer charges.

Prefer placing landing buckets and Redshift in the same Region whenever architecture permits. If data resides in another Region due to DR or ownership boundaries, factor in transfer costs and load durations.

### 4.2 IAM Roles for COPY

Prefer attaching an IAM role to the Redshift cluster or namespace instead of static access keys. The role needs read permissions for the exact bucket/prefix, such as:

- `s3:ListBucket` scoped with appropriate prefix conditions.
- `s3:GetObject` on the objects to load.
- `s3:GetBucketLocation` if workflows verify Region.
- `kms:Decrypt` if objects are encrypted with a customer managed KMS key.

The trust policy must allow the Redshift service to assume the role. With SSE-KMS, both the IAM policy and the KMS key policy must allow the role to decrypt. Cross-account S3 access also requires bucket policies and key policies in the data-owning account.

Never grant `s3:*` account-wide if `COPY` only needs one prefix. Never embed access keys in SQL, notebooks, or source control.

## 5. Using Manifests to Control File Sets

A manifest is a JSON file listing the exact S3 objects to load. Use a manifest when:

- Files span multiple prefixes or buckets.
- Only a specific subset of files should be loaded.
- Every mandatory file must be verified to exist.
- You need an auditable record of exactly which files comprised a batch.

Example manifest:

~~~json
{
  "entries": [
    {
      "url": "s3://company-data-lake/curated/orders/batch-20261119/part-0001.csv",
      "mandatory": true
    },
    {
      "url": "s3://company-data-lake/curated/orders/batch-20261119/part-0002.csv",
      "mandatory": true
    },
    {
      "url": "s3://company-data-lake/curated/orders/batch-20261119/part-0003.csv",
      "mandatory": true
    }
  ]
}
~~~

`COPY` with manifest:

~~~sql
COPY stage_orders
FROM 's3://company-data-lake/manifests/orders-20261119.manifest'
IAM_ROLE 'arn:aws:iam::111122223333:role/RedshiftCopyRole'
MANIFEST
CSV
IGNOREHEADER 1;
~~~

The `mandatory` field defaults to `false`. Set it to `true` for required files so `COPY` fails if any file is missing. Manifests have a 100 MB size limit; for larger lists, split across multiple manifests and execute multiple `COPY` commands.

When using Parquet or ORC with a manifest, entries require `content_length` metadata in the AWS-specified format. Verify manifest examples for columnar formats before deploying.

## 6. Choosing Formats and Compression

| Format | Advantages | Notes |
|---|---|---|
| CSV | Easy to exchange; splittable when uncompressed | Must standardize delimiters, quotes, nulls, and encoding |
| Delimited text | Simple and effective for batches | Escaping and field ordering must be strict |
| JSON | Flexible for semi-structured data | Supports JSON auto or JSONPaths; generally not auto-splittable |
| Parquet | Columnar, explicit schema, data lake friendly | `COPY` restricts options and requires schema compatibility |
| ORC | Columnar, strong compression | Similar to Parquet; verify supported options |
| GZIP/BZIP2/LZOP/ZSTD | Shrinks storage and transfer bytes | Compressed files are not always splittable |

`COPY` supports multiple text compression codecs including GZIP, BZIP2, LZOP, and ZSTD. ZSTD is supported in `COPY` documentation when loading from S3. Never assume every codec or option applies to every format.

### 6.1 File Size and File Count

`COPY` uses MPP to distribute work across slices. For uncompressed CSV and columnar Parquet/ORC, Redshift can automatically split large files starting at 128 MB into chunks. Parquet/ORC files smaller than 128 MB are not split automatically.

JSON and CSV compressed with codecs that cannot split automatically can force each file to be processed sequentially. AWS recommends splitting non-splittable files into roughly equal files between 1 MB and 1 GB after compression, with file counts set to a multiple of the slice count.

Avoid creating millions of tiny files. Excessive object counts inflate `LIST`/`GET` overhead, inventory duration, and operational complexity.

## 7. COPY Parquet and ORC

Parquet/ORC fit naturally when upstream Spark, Glue, or data lake pipelines generate files. Example:

~~~sql
COPY stage_orders
FROM 's3://company-data-lake/curated/orders-parquet/dt=2026-11-19/'
IAM_ROLE 'arn:aws:iam::111122223333:role/RedshiftCopyRole'
FORMAT AS PARQUET;
~~~

Key considerations:

- The S3 bucket must reside in the same Region as Redshift when `COPY`ing Parquet/ORC.
- Columnar `COPY` does not automatically apply compression encodings like some text loads.
- Only a subset of `COPY` parameters is supported for columnar formats.
- File and table schemas must align in column count, order, and data types per mapping rules.
- If a load fails, the `COPY` command fails; inspect schema/format errors before retrying.

If sources contain nested fields or schema evolution, test mappings with representative sample files. For complex preprocessing, standardize into Parquet with Glue/Spark prior to `COPY`.

## 8. JSON, CSV, and Handling Data Errors

For JSON, `COPY` can use JSON `auto` when field names match column names, or `JSONPaths` to map differing structures. JSON `auto` is not general-purpose schema inference for arbitrary nested structures.

Example `JSONPaths` mapping:

~~~json
{
  "jsonpaths": [
    "$.order.id",
    "$.customer.id",
    "$.created_at",
    "$.status",
    "$.total"
  ]
}
~~~

~~~sql
COPY stage_orders
FROM 's3://company-data-lake/raw/orders/'
IAM_ROLE 'arn:aws:iam::111122223333:role/RedshiftCopyRole'
JSON 's3://company-data-lake/config/order-jsonpaths.json';
~~~

The order of `JSONPaths` expressions must match the target column order in `COPY`. If specifying an explicit column list in `COPY`, align the mapping order accordingly.

For CSV, use the `CSV` option when fields contain commas, quotes, or newlines per CSV rules. Avoid simple `DELIMITER` parsing if unescaped delimiters appear inside field values.

### 8.1 Pre-Load Validation

`COPY` supports `NOLOAD` to validate readability and parsing without writing rows into the table. This is a useful check in deployment pipelines or before large batches.

~~~sql
COPY stage_orders
FROM 's3://company-data-lake/curated/orders/dt=2026-11-19/'
IAM_ROLE 'arn:aws:iam::111122223333:role/RedshiftCopyRole'
CSV
IGNOREHEADER 1
NOLOAD;
~~~

`NOLOAD` does not replace business validations such as duplicate detection, referential integrity, or financial totals. Validate schemas, row counts, null rates, and business totals as well.

### 8.2 MAXERROR and Skipped Rows

`MAXERROR` allows `COPY` to continue despite a set number of parse errors. Use it only with an explicit bad-data handling policy and reconciliation of skipped row counts. Do not set high limits in production to mask upstream defects.

When `COPY` fails, inspect `SYS_LOAD_HISTORY` and `SYS_LOAD_ERROR_DETAIL`. On provisioned clusters, `STL` views such as `STL_LOAD_ERRORS` are also helpful; they do not cover every Redshift Serverless or concurrency scaling workload.

## 9. Staging Tables and Safe Incremental Loads

`COPY` appends data into target tables. If a batch retries, reloading the same files can create duplicates. A safe pattern is:

1. Load the batch into a staging table.
2. Attach a `batch_id` or `load_id`.
3. Validate row counts and check for duplicate business keys.
4. Execute a transaction to merge into the target table.
5. Record committed batch status.
6. Purge staging rows only after reconciliation passes.

Example batch `DELETE` + `INSERT`:

~~~sql
BEGIN;

DELETE FROM fact_orders
USING stage_orders
WHERE fact_orders.order_id = stage_orders.order_id
  AND stage_orders.source_batch_id = 'batch-20261119';

INSERT INTO fact_orders (
    order_id,
    customer_id,
    order_ts,
    order_status,
    order_amount
)
SELECT
    order_id,
    customer_id,
    order_ts,
    order_status,
    order_amount
FROM stage_orders
WHERE source_batch_id = 'batch-20261119';

COMMIT;
~~~

This is an illustrative example; define upsert, duplicate, and batch ID semantics properly. If a batch contains multiple records for the same `order_id`, deduplicate inside staging before merging.

Never truncate a staging table while another batch is actively loading. Use batch-isolated staging tables or transaction/process orchestration so concurrent loaders do not wipe each other's data.

## 10. Parallel Data Loading and Batch Orchestration

`COPY` is built to ingest multiple files in parallel. An effective pipeline typically includes:

~~~mermaid
flowchart TD
    A["Source database / applications"] --> B["S3 raw landing"]
    B --> C["Validate schema and quality"]
    C --> D["Partition and split files"]
    D --> E["Manifest / batch metadata"]
    E --> F["COPY into staging"]
    F --> G["Validate counts and errors"]
    G --> H["MERGE / INSERT into warehouse"]
    H --> I["ANALYZE / query validation"]
    I --> J["BI and downstream users"]
~~~

Guidelines:

- Do not run so many concurrent `COPY` commands that WLM slots or I/O saturate.
- Group files into batches with consistent schemas.
- Use manifests to lock file sets.
- Track end-to-end duration from start to commit, not just `COPY` elapsed time.
- Separate raw, staging, and curated tables by permissions and lifecycle.
- Propagate batch IDs to trace data from S3 to reports.
- Implement retries in the orchestration layer and keep batches idempotent.

## 11. Distribution Styles and Why They Matter

Redshift distributes table rows across compute nodes according to distribution style. When joining two tables, the optimizer aims to co-locate matching rows on the same node to minimize network movement.

Four distribution styles:

| Style | Behavior | Suitable Use Cases |
|---|---|---|
| `AUTO` | Redshift selects automatically and can adapt by size/workload | Default starting point for most new tables |
| `EVEN` | Distributes rows round-robin evenly | No suitable join key or table rarely joins |
| `KEY` | Rows with identical `DISTKEY` values sit on the same slice | Large tables frequently joined on a uniformly distributed key |
| `ALL` | Copies the full table to every node | Small, slowly changing dimension tables |

`DISTSTYLE AUTO` is the default and usually a sound starting point. Redshift may choose `ALL` for small tables and transition to `KEY` or `EVEN` as tables grow. Transitions occur in the background with minimal query disruption.

### 11.1 DISTSTYLE KEY

Example where `fact_orders` and `dim_customer` frequently join on `customer_id`:

~~~sql
CREATE TABLE fact_orders (
    order_id BIGINT,
    customer_id BIGINT,
    order_ts TIMESTAMP,
    order_amount DECIMAL(18,2)
)
DISTSTYLE KEY
DISTKEY (customer_id)
SORTKEY (customer_id, order_ts);
~~~

~~~sql
CREATE TABLE dim_customer (
    customer_id BIGINT,
    customer_name VARCHAR(200),
    customer_segment VARCHAR(40)
)
DISTSTYLE KEY
DISTKEY (customer_id)
SORTKEY (customer_id);
~~~

When both tables share the same distribution key, matching rows sit on the same slices, eliminating redistribution. However, do not choose a key merely because it appears in many SQL queries. Evaluate cardinality and value distribution.

### 11.2 Avoiding Skew

A `DISTKEY` with excessive duplicates or one dominant value concentrates rows onto a few slices, forcing one node to do far more work and degrading parallelism.

Avoid columns like low-cardinality `status`, booleans, `country` with few nations, or `tenant_id` if one tenant dominates volume—unless measurements confirm even balance.

Check skew via `SVV_TABLE_INFO` and related system views. If one slice holds disproportionately more rows/bytes, change the key or revert to `AUTO`/`EVEN`.

### 11.3 DISTSTYLE ALL

`ALL` copies the entire table onto every node. It avoids join broadcasts for small, stable dimensions, while increasing storage and load/update overhead since every node holds a copy.

Do not default to `ALL` for every small dimension. Redshift can broadcast small tables cheaply; keep `ALL` only when query plans and workloads demonstrate clear benefit.

## 12. Choosing Distribution Keys by Workload

When evaluating a candidate `DISTKEY`, ask:

1. Does the table join frequently?
2. Which join keys appear in business-critical queries?
3. What are the post-filter data sizes of both join sides?
4. Are key values evenly distributed?
5. Are there nulls or dominant hot values?
6. Can multiple large tables share the same key without skew?
7. Do collocation gains outweigh storage/load costs and schema rigidity?

AWS recommends starting with `AUTO` until clear workload evidence dictates otherwise. When picking manually, base decisions on filtered datasets and query plans rather than raw table size alone.

## 13. Sort Keys and Zone Maps

Sort keys determine physical row ordering on disk. Redshift tracks min/max metadata per data block; when query predicates fall outside a block's range, the engine skips that block. This mechanism is called block skipping / zone maps.

Example `fact_orders` table frequently filtered by date ranges:

~~~sql
CREATE TABLE fact_orders (
    order_id BIGINT,
    customer_id BIGINT,
    order_ts TIMESTAMP,
    order_status VARCHAR(30),
    order_amount DECIMAL(18,2)
)
DISTSTYLE AUTO
SORTKEY (order_ts);
~~~

Query:

~~~sql
SELECT
    DATE_TRUNC('day', order_ts) AS order_day,
    SUM(order_amount) AS revenue
FROM fact_orders
WHERE order_ts >= '2026-11-01'
  AND order_ts <  '2026-12-01'
GROUP BY 1
ORDER BY 1;
~~~

The `order_ts` sort key lets Redshift skip blocks outside the date window when rows are well sorted.

### 13.1 SORTKEY AUTO

If no sort key is specified, Redshift uses `AUTO`. Automatic Table Optimization observes workloads and selects sort keys once enough query history accumulates. Prefer `AUTO` while access patterns are still evolving.

### 13.2 Compound Sort Key

Compound keys order columns sequentially. They shine when query filters match a leading prefix of the sort key.

For example, `SORTKEY(order_ts, customer_id)` works best for filters on `order_ts` alone or `order_ts` plus `customer_id`. Filtering solely on `customer_id` without `order_ts` yields much less benefit.

### 13.3 Interleaved Sort Key

Interleaved keys assign equal weight across columns to support multi-dimensional filters. However, interleaved keys carry higher maintenance and `VACUUM REINDEX` costs, particularly under continuous appends with shifting distributions.

Pick interleaved only when workloads filter independently across multiple dimensions and benchmarks prove net gains. For most periodically ingested tables, compound or `AUTO` is simpler to operate.

## 14. Automatic Table Optimization (ATO)

ATO observes query patterns and metadata to automatically recommend and apply distribution styles and sort keys. It reduces manual key guesswork while workloads are changing.

You can switch existing tables to `AUTO`:

~~~sql
ALTER TABLE fact_orders ALTER DISTSTYLE AUTO;
ALTER TABLE fact_orders ALTER SORTKEY AUTO;
~~~

Monitor:

- `SVV_TABLE_INFO`: distribution, sort keys, unsorted rows, and table health.
- `SVV_ALTER_TABLE_RECOMMENDATIONS`: optimization recommendations.
- `SVL_AUTO_WORKER_ACTION`: history of automated changes on provisioned clusters.
- `SYS_AUTOMATIC_OPTIMIZATION`: autonomic task events such as `AutoAlterTable`, `VacuumSort`, and `Analyze`; visible only to superusers. Some `SVV`/`SVL` recommendations and audit views are provisioned-only, so verify deployment type and permissions before building dashboards.

ATO needs representative workload history to make decisions. Do not assume a table is optimal merely because `AUTO` is on; observe recommendations, plans, and query runtimes over multiple cycles.

If you explicitly assign a `DISTKEY` or `SORTKEY`, that attribute is no longer managed automatically. Leave `AUTO` only with evidence and a plan to revisit as workloads evolve.

## 15. Compression Encoding and Columnar Storage

Redshift stores columns separately and supports compression encodings to cut storage I/O. Proper encoding reduces bytes read, whereas mismatched encoding can raise decompression CPU or bloat size.

Common encodings:

| Encoding | General Characteristics | Suitable Data |
|---|---|---|
| `AZ64` | Efficient compression for numeric/date/time | Numbers, timestamps |
| `ZSTD` | Strong general-purpose compression | Wide variety of data types |
| `LZO` | Fast compression | Certain text workloads |
| `BYTEDICT` | Byte-level dictionary | Short text columns with moderate cardinality |
| `DELTA` / `DELTA32K` | Delta encoding | Monotonically increasing/decreasing numbers |
| `RAW` | Uncompressed | Certain sort keys or specialized access patterns |

Prefer `ENCODE AUTO` so Redshift selects encodings based on data and workload. On existing tables, `ANALYZE COMPRESSION` suggests encodings; validate suggestions on representative datasets.

Do not tune compression on tiny or unrepresentative samples. Production cardinality and distributions often differ from samples.

## 16. ANALYZE and Statistics

`ANALYZE` updates statistical metadata so the optimizer accurately estimates row counts and chooses join orders, join methods, memory, and data movement.

Redshift runs automatic analyze in the background as data changes. Still, after large bulk loads or major shifts in filter/join columns, running `ANALYZE` explicitly may be needed:

~~~sql
ANALYZE fact_orders;
~~~

You can scope to predicate columns to conserve resources:

~~~sql
ANALYZE fact_orders PREDICATE COLUMNS;
~~~

Stale statistics can mislead the optimizer into treating a huge table as tiny, picking the wrong inner table, or choosing an expensive broadcast. When `EXPLAIN` row estimates deviate sharply from reality, check statistics before changing `DISTKEY`/`SORTKEY`.

## 17. VACUUM, Unsorted Rows, and Deleted Rows

`INSERT`, `UPDATE`, and `DELETE` operations leave unsorted regions or mark rows as deleted, increasing scan cost and eroding sort key benefits.

`VACUUM` serves three goals:

- Re-sorts rows into sort key order.
- Reclaims space from deleted rows.
- Reindexes interleaved sort keys where needed.

Redshift runs automatic sort and `VACUUM DELETE` in the background, so rigid `VACUUM FULL` schedules across every table are unnecessary. Check table health before intervening.

Example:

~~~sql
VACUUM SORT ONLY fact_orders;
ANALYZE fact_orders;
~~~

The command above illustrates a table needing re-sorting. Other tables may need `DELETE ONLY` or another mode. `VACUUM` consumes resources and can impact active workloads; avoid blanket runs without metrics.

Watch unsorted percentages, deleted rows, and vacuum history. Loading via `COPY` already ordered by sort key keeps unsorted percentages lower.

## 18. Table Layout Optimization Workflow

A practical workflow:

1. Identify the 5–10 most important queries by frequency, latency, and business impact.
2. Map their join keys and filter predicates.
3. Measure table size, skew, unsorted percentage, and stats freshness.
4. Run `EXPLAIN` to inspect data movement and scans.
5. Evaluate `AUTO` first.
6. If manual tuning is needed, test distribution/sort keys on a clone or benchmark environment.
7. Load representative data.
8. Run `ANALYZE` and execute the sample workload.
9. Compare elapsed time, queue time, bytes scanned, and query plans.
10. Deploy with a rollback plan and monitor post-change metrics.

Do not optimize one isolated query at the expense of every other workload. Table design should reflect the overall workload mix.

## 19. Reading EXPLAIN Query Plans

`EXPLAIN` displays the plan Redshift expects to use without executing the query. Read plans bottom-up to see how data is scanned, joined, aggregated, and returned.

~~~sql
EXPLAIN
SELECT
    c.customer_segment,
    SUM(o.order_amount) AS revenue
FROM fact_orders o
JOIN dim_customer c
  ON o.customer_id = c.customer_id
WHERE o.order_ts >= '2026-11-01'
  AND o.order_ts <  '2026-12-01'
GROUP BY c.customer_segment;
~~~

Common data movement labels:

| Label | Meaning | Assessment |
|---|---|---|
| `DS_DIST_NONE` | No redistribution needed | Usually ideal for large joins |
| `DS_DIST_ALL_NONE` | Inner table is present on all nodes | Expected with `ALL` |
| `DS_BCAST_INNER` | Broadcasts inner table to all nodes | Acceptable when table is small |
| `DS_DIST_INNER` | Redistributes inner table | Check volume of moved data |
| `DS_DIST_OUTER` | Redistributes outer table | Check whether collocation is possible |
| `DS_DIST_BOTH` | Redistributes both sides | Usually a signal to investigate |
| `DS_DIST_ALL_INNER` | Pulls inner table to one slice due to `ALL` outer | Can destroy parallelism |

Costs in `EXPLAIN` are cumulative relative plan numbers, not wall-clock time or MB read. Never compare `EXPLAIN` cost numbers across two distinct plans as if they were absolute benchmarks.

`EXPLAIN` omits many runtime realities. After execution, inspect `SYS_QUERY_DETAIL` or query summaries to compare actual rows/bytes against estimates.

## 20. Optimizing SQL for Redshift

High-impact principles:

- Select only required columns; avoid `SELECT *` on wide tables.
- Filter early to trim rows before joins/aggregations.
- Write direct predicates on sort keys whenever possible.
- Avoid casting or wrapping filter columns in functions that disable block skipping.
- Use explicit join predicates with matching data types.
- Avoid casting one side of join keys when schemas can be aligned.
- Prevent accidental Cartesian joins from missing join conditions.
- Trim unnecessary intermediate data in subqueries and CTEs.
- Use approximate aggregations or pre-aggregations where business rules allow.
- Never slap `DISTINCT` onto queries to mask duplicates from broken joins.
- Check skew and cardinality before scaling parallelism.

### 20.1 Joins

Joins between large tables often redistribute rows by join key. If both tables are collocated, `EXPLAIN` shows `DS_DIST_NONE`. If you see `DS_DIST_BOTH`, evaluate `AUTO` or an appropriate shared key.

Do not try to tune joins simply by reordering tables in `FROM`; the optimizer uses statistics to choose inner/outer relations. Update statistics and examine the query plan.

### 20.2 Filters and Block Skipping

Range conditions on a sort key let Redshift prune blocks outside the interval. For example:

~~~sql
WHERE order_ts >= '2026-11-01'
  AND order_ts < '2026-11-08'
~~~

is far easier to optimize than wrapping the column in a function before comparing:

~~~sql
WHERE DATE_TRUNC('day', order_ts) = '2026-11-01'
~~~

Rewrite column-function filters into equivalent range predicates so zone maps work effectively.

### 20.3 Aggregations and Window Functions

Aggregating massive row counts involves reading and redistributing data. Filter early, pick group keys with sensible cardinality, and watch `HashAggregate`/`Sort` operators in the plan. Window functions can require sorting by `PARTITION BY` and `ORDER BY`; filter rows before applying windows whenever semantics permit.

## 21. Materialized Views and Pre-Aggregation

Materialized views store precomputed results of queries over base tables. They suit recurring dashboards/reports, heavy joins/aggregations, and workloads that tolerate refresh lag.

Example:

~~~sql
CREATE MATERIALIZED VIEW mv_daily_sales
AUTO REFRESH YES
AS
SELECT
    DATE_TRUNC('day', order_ts) AS sales_day,
    customer_id,
    SUM(order_amount) AS total_amount,
    COUNT(*) AS order_count
FROM fact_orders
GROUP BY 1, 2;
~~~

Manual refresh:

~~~sql
REFRESH MATERIALIZED VIEW mv_daily_sales;
~~~

Redshift can refresh incrementally when the view definition and base table changes are supported; otherwise it executes a full refresh. Auto refresh runs when resources allow and may lag behind base table commits.

Automatic query rewrite can leverage a fresh materialized view even if SQL queries base tables directly. Check `EXPLAIN` and `SYS_MV_AQMV_HISTORY` to confirm whether a query was rewritten. If the view is stale, the engine skips automatic rewrite to avoid serving outdated results.

Do not materialize every query. Each view consumes storage and refresh compute. Weigh query latency savings against refresh costs.

## 22. Automatic Materialized Views and Result Cache

Redshift can automatically create and manage Automated Materialized Views (AutoMV) based on observed workloads. AutoMV accelerates recurring queries without DBAs manually defining every aggregate view.

The result cache stores eligible query results in memory. When an identical query arrives and underlying objects/settings have not changed, Redshift can return cached results without re-executing.

Result caching does not replace table design or materialized views. It does not accelerate every query—queries using volatile functions or external Spectrum tables may be ineligible. When benchmarking, verify whether queries hit the cache or executed genuinely to avoid misleading numbers.

## 23. Workload Management (WLM) and Concurrency

WLM governs resources for concurrent queries. Two modes:

| Mode | Characteristics | When to Use |
|---|---|---|
| Automatic WLM | Redshift dynamically sets concurrency and memory per query | Recommended for most workloads |
| Manual WLM | DBAs configure queues, slots, and memory percentages | Specialized use cases needing rigid static control |

Auto WLM combines query priorities and Query Monitoring Rules (QMR). Manual WLM separates queues by workload such as ETL, dashboards, and ad-hoc analytics.

### 23.1 Isolating Workloads

Example:
- ETL queue running `COPY`/`MERGE` and batch aggregations.
- Dashboard queue prioritizing short queries.
- Analyst queue for ad-hoc exploration.
- Admin queue for controlled maintenance.

Do not raise concurrency without bounds. Excess concurrent queries starve per-query memory, trigger disk spills, and extend completion times.

### 23.2 Query Monitoring Rules

QMR applies metric-based conditions and actions such as log, hop, or abort. For example, log queries containing nested loops or abort runaway queries in the dashboard queue.

Base rules on real workload data. Overly strict rules kill valid queries; overly loose rules fail to protect the cluster.

### 23.3 Concurrency Scaling

Concurrency Scaling adds transient compute capacity during concurrent bursts and scales down when demand subsides. It helps bursty concurrency, though it does not fix bad query plans or single queries bottlenecked on data movement.

Monitor whether queries run on the main cluster or concurrency scaling clusters, and track eligibility and costs.

## 24. System Views for Monitoring Queries and Loads

Prefer `SYS` monitoring views for unified visibility across provisioned and Serverless. Certain `STL`/`SVL`/`STV` views apply only to provisioned clusters or differ in visibility.

| View | Purpose |
|---|---|
| `SYS_QUERY_HISTORY` | Query history, status, elapsed/queue/execution times |
| `SYS_QUERY_DETAIL` | Step- and metric-level query details |
| `SYS_QUERY_EXPLAIN` | Query plans by query ID |
| `SYS_LOAD_HISTORY` | `COPY`/load history |
| `SYS_LOAD_DETAIL` | File/table-level load details |
| `SYS_LOAD_ERROR_DETAIL` | Load error details |
| `SYS_VACUUM_HISTORY` | Vacuum history |
| `SYS_ANALYZE_HISTORY` | Analyze history |
| `SYS_AUTOMATIC_OPTIMIZATION` | Autonomic events like `AutoAlterTable`, `VacuumSort`, and `Analyze`; superuser-only |
| `SVV_TABLE_INFO` | Size, distribution, sort key, and table health |
| `SVV_ALTER_TABLE_RECOMMENDATIONS` | ATO recommendations |

Example finding slow queries in the last 24 hours:

~~~sql
SELECT
    query_id,
    query_type,
    status,
    elapsed_time / 1000000.0 AS elapsed_seconds,
    queue_time / 1000000.0 AS queue_seconds,
    execution_time / 1000000.0 AS execution_seconds,
    LEFT(query_text, 300) AS query_sample
FROM sys_query_history
WHERE start_time >= DATEADD(day, -1, GETDATE())
ORDER BY elapsed_time DESC
LIMIT 20;
~~~

`elapsed_time`, `queue_time`, and `execution_time` in `SYS_QUERY_HISTORY` are reported in microseconds. Compare queue time against execution time to tell resource contention apart from plan inefficiency.

### 24.1 Monitoring Table Health

~~~sql
SELECT
    "schema",
    "table",
    size,
    pct_used,
    unsorted,
    stats_off,
    skew_rows,
    diststyle,
    sortkey1
FROM svv_table_info
ORDER BY size DESC
LIMIT 30;
~~~

Column names and visibility can vary by version/deployment. If a column is unavailable in your environment, check the current view schema before building production dashboards.

## 25. Diagnosing COPY and Load Failures

When `COPY` fails, do not blindly retry. Identify the root cause:

- IAM role cannot be assumed or lacks S3 permissions.
- Bucket is in the wrong Region or endpoint is misconfigured.
- KMS key policy lacks decrypt permissions.
- Prefix matches unintended files or zero objects.
- Manifest references a missing mandatory file.
- Schema or column ordering mismatch.
- Unbalanced CSV quotes or delimiters.
- Malformed timestamps, decimals, integers, or UTF-8 characters.
- Incompatible Parquet/ORC schemas.
- Concurrent loads into the same staging table colliding logically.

Query load errors using `SYS` views:

~~~sql
SELECT
    e.query_id,
    h.table_name,
    e.start_time,
    e.file_name,
    line_number,
    column_name,
    column_type,
    error_code,
    e.error_message
FROM sys_load_error_detail e
LEFT JOIN sys_load_history h
  ON e.query_id = h.query_id
ORDER BY e.start_time DESC
LIMIT 50;
~~~

This is an illustrative query; verify exact column names against `SYS_LOAD_ERROR_DETAIL` in your Region/version. On provisioned clusters, `STL_LOAD_ERRORS` and `STL_S3CLIENT_ERROR` provide corresponding diagnostics.

## 26. Reference Ingestion Architecture

A batch warehouse architecture:

~~~mermaid
flowchart TD
    A["Operational DB / SaaS / files"] --> B["S3 raw zone"]
    B --> C["Glue / ETL validation"]
    C --> D["S3 curated Parquet"]
    D --> E["Manifest / batch registry"]
    E --> F["Redshift COPY"]
    F --> G["Staging tables"]
    G --> H["Dedup / MERGE / transaction"]
    H --> I["Fact and dimension tables"]
    I --> J["ANALYZE / ATO / maintenance"]
    J --> K["BI dashboards / analysts"]
    I --> L["Materialized views"]
    L --> K
~~~

Separating raw and curated zones preserves source data while allowing schema standardization and file splitting before loading. Manifests and batch registries prove exactly which batches were ingested.

If datasets are queried only ad hoc without needing local warehouse performance, consider Spectrum or external tables instead of `COPY`ing everything into Redshift. For high-frequency queries with tight SLAs, local tables or materialized views fit better.

## 27. Case Study: Optimizing the fact_orders Table

An e-commerce company has a `fact_orders` table with 2 billion rows. Dashboards typically filter by month, join `dim_customer`, and group by `customer_segment`. Queries currently take 90 seconds.

### Symptoms

- `EXPLAIN` shows `DS_DIST_BOTH` between `fact_orders` and `dim_customer`.
- Queries scan many blocks despite filtering a single month.
- `SVV_TABLE_INFO` shows a high unsorted percentage.
- `stats_off` is high following a large bulk load.
- WLM queue time climbs during dashboard hours.

### Investigation Steps

1. Establish query frequency and p95 latency.
2. Inspect sort keys and distribution styles of both tables.
3. Measure `customer_id` skew.
4. Run `ANALYZE` to refresh statistics.
5. Check whether timestamp is a suitable leading sort key.
6. Check if `AUTO` has distribution/sort key recommendations.
7. Compare queue time vs. execution time to separate WLM contention from query execution.

### Actions

- Start with `DISTSTYLE AUTO` and `SORTKEY AUTO` in a test environment.
- If workloads confirm `customer_id` is a stable join key, test `KEY` distribution on `customer_id` across both large related tables.
- Use `order_ts` as the leading sort key if time-range filters dominate and `AUTO` has not picked it yet.
- Load data ordered by sort key when pipelines allow.
- Run `ANALYZE` after major bulk loads.
- Run `VACUUM` only when unsorted/deleted row metrics warrant it.
- Create a materialized view for dashboard aggregations if refresh latency meets SLAs.
- Separate dashboard and ETL workloads using Auto WLM priorities/QMR.

### Metrics to Measure

- Bytes scanned and rows scanned.
- Number of blocks scanned.
- `DS_DIST_NONE`/`BCAST`/`DIST_BOTH` in `EXPLAIN`.
- p50/p95/p99 elapsed time.
- Queue time and execution time.
- Materialized view refresh time and staleness.
- Post-change compute and storage costs.

Never aim solely to drop one query to a few seconds. Ensure ETL still meets batch windows and ad-hoc workloads do not degrade.

## 28. Lab: Loading Data from S3 and Reading Query Plans

Use a Redshift sandbox or learning environment—never run on a production warehouse. Replace buckets, Region, account IDs, and role ARNs with your provisioned lab resources.

### Step 1: Create Table

~~~sql
CREATE TABLE lab_orders (
    order_id BIGINT,
    customer_id BIGINT,
    order_ts TIMESTAMP,
    order_status VARCHAR(30),
    order_amount DECIMAL(18,2)
)
DISTSTYLE AUTO
SORTKEY AUTO;
~~~

### Step 2: Create Sample File

Pipe-delimited CSV file without header:

~~~text
1001|501|2026-11-19 10:00:00|PAID|125000.00
1002|502|2026-11-19 10:05:00|PENDING|45000.00
1003|501|2026-11-19 10:10:00|PAID|89000.00
1004|503|2026-11-19 10:15:00|CANCELLED|120000.00
~~~

Upload the file to your designated lab S3 prefix. Never use production buckets.

### Step 3: Run COPY NOLOAD

~~~sql
COPY lab_orders
FROM 's3://company-redshift-lab/orders/'
IAM_ROLE 'arn:aws:iam::111122223333:role/RedshiftLabCopyRole'
REGION 'ap-southeast-1'
DELIMITER '|'
TIMEFORMAT 'auto'
NOLOAD;
~~~

If `NOLOAD` fails, verify the IAM role, prefix, schema, and delimiter before running the real load.

### Step 4: Load Data

~~~sql
COPY lab_orders
FROM 's3://company-redshift-lab/orders/'
IAM_ROLE 'arn:aws:iam::111122223333:role/RedshiftLabCopyRole'
REGION 'ap-southeast-1'
DELIMITER '|'
TIMEFORMAT 'auto';
~~~

### Step 5: Verify Rows

~~~sql
SELECT
    COUNT(*) AS row_count,
    COUNT(DISTINCT order_id) AS unique_orders,
    SUM(order_amount) AS total_amount,
    MIN(order_ts) AS first_order,
    MAX(order_ts) AS last_order
FROM lab_orders;
~~~

If you run `COPY` a second time, check for duplicates. This demonstrates that `COPY` appends rows and why batch idempotency is essential.

### Step 6: Inspect EXPLAIN

~~~sql
EXPLAIN
SELECT
    customer_id,
    SUM(order_amount) AS total_amount
FROM lab_orders
WHERE order_ts >= '2026-11-19'
GROUP BY customer_id;
~~~

Try altering the table design in another lab table, run `ANALYZE`, and compare query plans. Never infer real performance solely from cost estimates; run queries and measure elapsed time and bytes scanned.

### Step 7: Check System Views

~~~sql
SELECT *
FROM sys_query_history
ORDER BY start_time DESC
LIMIT 10;
~~~

~~~sql
SELECT
    "schema",
    "table",
    size,
    unsorted,
    stats_off,
    diststyle,
    sortkey1
FROM svv_table_info
WHERE "table" = 'lab_orders';
~~~

### Step 8: Cleanup

~~~sql
DROP TABLE IF EXISTS lab_orders;
~~~

Delete S3 lab objects, manifests, and IAM roles only if certain no other lab uses them. Never delete shared buckets.

## 29. Common Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `COPY` AccessDenied | IAM role, bucket policy, or KMS key policy lacks permission | Verify trust policy, S3 prefix, and KMS permissions |
| `COPY` file not found | Wrong prefix or manifest points to missing object | Check S3 keys and mandatory entries |
| `COPY` misses files yet succeeds | Prefix does not guarantee all expected files exist | Use a manifest with `mandatory=true` |
| `COPY` is very slow | Single huge non-splittable file or too few files | Split files evenly and leverage parallel loading |
| `COPY` Parquet fails | Incompatible schema, Region, or format option | Check schemas and columnar `COPY` limits |
| CSV delimiter error | Inconsistent delimiters, quotes, or escapes | Standardize CSV formatting and inspect sample files |
| Timestamp parse error | `TIMEFORMAT`/`DATEFORMAT` mismatch | Use `auto` or explicit format string |
| Duplicate data loaded | `COPY` appends on batch retries | Use staging, batch IDs, and dedup/merge |
| Query shows `DS_DIST_BOTH` | Both tables require redistribution | Evaluate `AUTO`, join keys, and key skew |
| Query scans too many blocks | Poor sort key or high unsorted region | Review filters, sort keys, `VACUUM`, and ATO |
| Query plan row estimates wrong | Stale statistics | Run `ANALYZE` and check `stats_off` |
| One node runs slower | Distribution skew or hot key | Check `skew_rows` and adjust distribution strategy |
| High query queue time | WLM concurrency or competing workloads | Inspect Auto WLM, priorities, and QMR |
| Materialized view unused | Stale view or query ineligible for rewrite | Refresh view, check `EXPLAIN`, and rewrite history |
| `VACUUM` takes too long | Large table, many unsorted/deleted rows, or interleaved key | Pick right vacuum mode and schedule carefully |
| `SYS` view hides queries | Permissions/visibility or retention window | Verify user permissions and view scope |
| `STL_LOAD_ERRORS` empty on Serverless | `STL` views do not cover Serverless | Query `SYS_LOAD_ERROR_DETAIL` |
| Unusually fast benchmark query | Result cache hit | Check `result_cache_hit` and benchmark cold/warm separately |

## 30. Best Practices for Redshift Ingestion and Query Performance

### Data Ingestion

- Use `COPY` for bulk loads.
- Prefer IAM roles over access keys.
- Place S3 and Redshift in the same Region whenever possible.
- Use multiple evenly sized files to exploit MPP.
- Use manifests for exact file sets.
- Standardize schemas, timezones, nulls, and encodings before loading.
- Run `NOLOAD` and sample batches before production.
- Monitor `SYS_LOAD_HISTORY` and `SYS_LOAD_ERROR_DETAIL`.
- Design staging and batch IDs so `COPY` retries never create duplicates.
- Separate raw, staging, and curated datasets.

### Table Design

- Start with `DISTSTYLE AUTO` and `SORTKEY AUTO`.
- Choose `DISTKEY` only when join workloads and key distribution prove clear gains.
- Avoid skew and low-cardinality distribution keys.
- Use `ALL` selectively for small, static tables backed by benchmarks.
- Pick sort keys matching filter patterns and time-range queries.
- Prefer compound or `AUTO` for most workloads; reserve interleaved for measured multi-dimensional needs.
- Use `ENCODE AUTO` unless benchmarks prove otherwise.
- Review ATO recommendations as workloads evolve.

### Query Tuning

- Run `EXPLAIN` before changing schemas.
- Read data movement labels and scan/sort/aggregate operators.
- Run `ANALYZE` after major bulk changes.
- Watch unsorted rows and vacuum history.
- Filter early; avoid `SELECT *` and unnecessary casts.
- Align join key types and statistics.
- Use materialized views for recurring workloads tolerant of refresh lag.
- Distinguish queue time from execution time.

### Workloads and Operations

- Start with Auto WLM.
- Use query priorities/QMR across distinct workloads.
- Track concurrency scaling usage and cost.
- Use `SYS` monitoring views across Provisioned and Serverless.
- Protect S3 data, IAM roles, and KMS keys.
- Log load manifests, batch IDs, and query labels.
- Track p95/p99 latency and ETL completion times.
- Benchmark with representative data while accounting for result caches.
- Maintain rollback plans for table redesigns and ingestion pipelines.

## 31. Self-Practice Exercises

1. Why is `COPY` preferred over row-by-row `INSERT` for large batches?
2. What risk does a manifest solve compared to `COPY`ing an S3 prefix?
3. Why are IAM roles recommended over access keys?
4. What does `COPY NOLOAD` validate?
5. Why can retrying `COPY` create duplicates?
6. When should you use Parquet/ORC?
7. Why can a single large GZIP file slow down loading?
8. How do file size and file count affect MPP?
9. How does `DISTSTYLE AUTO` work?
10. When should you choose `DISTSTYLE KEY`?
11. When can `DISTSTYLE ALL` be useful?
12. Why does a low-cardinality `DISTKEY` cause skew?
13. When does `DISTSTYLE EVEN` fit?
14. What two different problems do sort keys and distribution keys solve?
15. How do zone maps reduce data scanned?
16. Which subset of columns makes a compound sort key most effective?
17. When is an interleaved sort key worth considering?
18. What does ATO monitor and optimize automatically?
19. What metadata does `ANALYZE` update for the optimizer?
20. How does `VACUUM` address unsorted and deleted rows?
21. Why shouldn't you run `VACUUM FULL` on a fixed schedule across all tables?
22. Does `EXPLAIN` execute the query?
23. How do `DS_DIST_NONE` and `DS_DIST_BOTH` differ?
24. Why is query plan cost not equal to execution time?
25. How does `SYS_QUERY_HISTORY` separate queue time from execution time?
26. Why does Auto WLM fit most workloads?
27. What actions can QMR perform?
28. When does a materialized view need refreshing?
29. When can automatic query rewrite use a materialized view?
30. Why can the result cache skew benchmarks?
31. Why should `SYS_LOAD_ERROR_DETAIL` be used on Serverless instead of `STL_LOAD_ERRORS`?
32. How do you make `COPY` retries safe?

### Suggested Answers

1. `COPY` reads multiple files in parallel, cuts request overhead, and leverages MPP.
2. Ensures an exact file set, catches missing mandatory files, and avoids loading unintended backups.
3. Roles provide temporary credentials, least privilege, and avoid secrets in SQL.
4. Readability and parsing without inserting rows into the table.
5. `COPY` appends rows; re-running on the same files reloads duplicate records.
6. When pipelines emit well-typed columnar datasets suited for bulk loads.
7. Non-splittable files may be processed sequentially.
8. Evenly sized files allow slices to work in parallel; too few files bottleneck parallelism.
9. Redshift chooses `ALL`, `KEY`, or `EVEN` based on size/workload and adjusts in the background.
10. When large tables frequently join on a uniformly distributed key.
11. When a small, static dimension table joins frequently and broadcast/redistribution is costly.
12. Many rows cluster onto a subset of slices, creating imbalance.
13. When no suitable join key exists or the table rarely joins.
14. Distribution decides which node stores each row; sort key decides block/row ordering.
15. The engine skips blocks whose min/max values do not overlap query predicates.
16. A leading prefix of columns in declared order.
17. When queries filter independently across multiple dimensions and benchmarks prove gains.
18. Distribution styles and sort keys based on query workloads and table metadata.
19. Data distribution statistics helping the optimizer estimate rows and pick plans.
20. Re-sorts rows and reclaims space from deleted rows.
21. Redshift already runs background sort and `VACUUM DELETE`; manual vacuums consume resources and are needed only when table health indicates.
22. No. `EXPLAIN` only prints the plan.
23. `DS_DIST_NONE` moves no data; `DS_DIST_BOTH` redistributes both sides of the join.
24. Cost is a relative plan unit, not elapsed time or memory.
25. Queue time measures WLM waiting; execution time measures active execution.
26. It dynamically tunes concurrency and memory based on workload.
27. Log, hop, or abort queries per rule.
28. When base tables change and snapshot results must update; via manual or auto refresh.
29. When the view is fresh and the query belongs to supported patterns.
30. Queries may return cached results instead of executing, producing artificially low latency.
31. Several `STL` views do not cover Serverless; `SYS` views provide broader coverage.
32. Use staging tables, batch IDs, immutable manifests, validation, and transactional merge/dedup.

## 32. Interview Questions

### Why is COPY the recommended bulk loading method?

`COPY` leverages MPP to read multiple files in parallel, uses IAM roles, and supports multiple formats. Row-by-row `INSERT`s incur heavy round trips and fail to utilize parallel ingestion architecture.

### Why use a manifest instead of an S3 prefix alone?

A prefix can match unwanted files or miss a file while still letting `COPY` succeed. A manifest lists exact objects and can mark entries `mandatory` to ensure batch completeness.

### Should DISTKEY always be placed on the primary key?

No. Redshift is not an OLTP database and does not use primary keys as row-lookup indexes. `DISTKEY` should reflect join patterns, cardinality, skew, and filtered data volumes.

### When should DISTSTYLE ALL be used?

When a small, slowly changing table joins frequently and avoiding broadcast/redistribution outweighs storage/load overhead. For very small dimensions, broadcasts may already be cheap enough.

### Why is a timestamp SORTKEY often helpful for fact tables?

When workloads routinely query recent time windows, a leading timestamp sort key enables zone maps to skip blocks outside the time range.

### Does ATO completely eliminate the need to understand query plans?

No. ATO tunes physical table layout, while DBAs still need to read plans, measure latency, inspect skew, and evaluate critical queries.

### When should ANALYZE and VACUUM be run?

Run `ANALYZE` when statistics are stale or data shifts substantially. Run `VACUUM` when unsorted/deleted rows degrade performance and background maintenance has not caught up. Never run them blindly on a fixed schedule without measuring.

### Is DS_DIST_BOTH always an error?

It is not a runtime error, though it indicates both join sides must redistribute data. On large tables, this increases network traffic and slows execution; inspect the plan and actual row volumes.

### Why use SYS monitoring views?

`SYS` views provide a more consistent observability layer across queries, loads, and maintenance and support both Redshift Serverless and provisioned in many scenarios. Several `STL`/`SVL` views are provisioned-only.

### Is a materialized view always faster than the base query?

No. It reduces query-time computation by pre-storing results, while incurring storage and refresh compute. Use them only when repeated reads are frequent enough and refresh-based freshness is acceptable.

## 33. Pre-Production Checklist for Redshift Warehouses

### Data ingestion

- [ ] S3 prefixes/manifests contain strictly the batch to load.
- [ ] Least-privilege IAM roles and KMS key policies are verified.
- [ ] File formats, delimiters, encodings, timezones, and schemas are confirmed.
- [ ] File counts and sizes leverage parallel loading.
- [ ] `COPY NOLOAD` or pilot batches passed.
- [ ] Load errors and row counts are reported.
- [ ] Batch IDs and retry semantics prevent duplicate loads.
- [ ] Cross-Region transfer costs are estimated.

### Table layout

- [ ] `DISTSTYLE AUTO` / `SORTKEY AUTO` evaluated first.
- [ ] `DISTKEY` avoids skew and matches join workloads.
- [ ] `SORTKEY` aligns with filter patterns.
- [ ] Compression encodings reviewed.
- [ ] Table size, unsorted rows, and stats freshness are tracked.
- [ ] ATO recommendations are reviewed regularly.

### Query performance

- [ ] Critical queries have reviewed `EXPLAIN` plans.
- [ ] Data redistribution and broadcasts are evaluated.
- [ ] Statistics are refreshed after large bulk loads.
- [ ] `VACUUM` runs only when table health requires it.
- [ ] SQL avoids unnecessary scans/joins.
- [ ] Materialized views have refresh/freshness policies.
- [ ] Result caching is accounted for during benchmarks.

### Workloads and monitoring

- [ ] Auto WLM and priorities fit workloads.
- [ ] QMR rules and actions are well defined.
- [ ] Queue time and execution time are tracked.
- [ ] Dashboards cover `SYS_QUERY_HISTORY`/`DETAIL` and `SYS_LOAD_HISTORY`/`ERROR_DETAIL`.
- [ ] Serverless/Provisioned system view differences are documented.
- [ ] Concurrency scaling usage and costs are tracked.

### Security and operations

- [ ] Redshift roles use no static credentials.
- [ ] S3 buckets, KMS keys, and network access are locked down.
- [ ] SQL privileges by role/schema/table are reviewed.
- [ ] Audit trails exist for load batches and schema changes.
- [ ] Runbooks exist for `COPY` errors, skew, slow queries, and WLM queueing.
- [ ] Rollback procedures exist for table redesigns and ingestion pipelines.
- [ ] Owners are assigned for ingestion, warehouse schemas, and dashboard SLAs.

## 34. Official Reference Documentation

- [Amazon Redshift best practices for loading data](https://docs.aws.amazon.com/redshift/latest/dg/c_loading-data-best-practices.html)
- [Using the COPY command to load from Amazon S3](https://docs.aws.amazon.com/redshift/latest/dg/t_loading-tables-from-s3.html)
- [COPY command reference](https://docs.aws.amazon.com/redshift/latest/dg/r_COPY.html)
- [COPY examples](https://docs.aws.amazon.com/redshift/latest/dg/r_COPY_command_examples.html)
- [Loading data files and parallel loading](https://docs.aws.amazon.com/redshift/latest/dg/c_best-practices-use-multiple-files.html)
- [Loading compressed and uncompressed files](https://docs.aws.amazon.com/redshift/latest/dg/t_splitting-data-files.html)
- [COPY from Parquet and ORC](https://docs.aws.amazon.com/redshift/latest/dg/copy-usage_notes-copy-from-columnar.html)
- [COPY authorization parameters](https://docs.aws.amazon.com/redshift/latest/dg/copy-parameters-authorization.html)
- [IAM permissions for COPY, UNLOAD, and CREATE LIBRARY](https://docs.aws.amazon.com/redshift/latest/dg/loading-data-access-permissions.html)
- [Troubleshooting data loads](https://docs.aws.amazon.com/redshift/latest/dg/t_Troubleshooting_load_errors.html)
- [System tables for troubleshooting data loads](https://docs.aws.amazon.com/redshift/latest/dg/system-tables-for-troubleshooting-data-loads.html)
- [SYS_LOAD_HISTORY](https://docs.aws.amazon.com/redshift/latest/dg/SYS_LOAD_HISTORY.html)
- [SYS_LOAD_ERROR_DETAIL](https://docs.aws.amazon.com/redshift/latest/dg/SYS_LOAD_ERROR_DETAIL.html)
- [SYS_AUTOMATIC_OPTIMIZATION](https://docs.aws.amazon.com/redshift/latest/dg/SYS_AUTOMATIC_OPTIMIZATION.html)
- [Distribution styles](https://docs.aws.amazon.com/redshift/latest/dg/c_choosing_dist_sort.html)
- [Data distribution for query optimization](https://docs.aws.amazon.com/redshift/latest/dg/t_Distributing_data.html)
- [Choose the best sort key](https://docs.aws.amazon.com/redshift/latest/dg/c_best-practices-sort-key.html)
- [Sort keys](https://docs.aws.amazon.com/redshift/latest/dg/t_Sorting_data.html)
- [Automatic table optimization](https://docs.aws.amazon.com/redshift/latest/dg/t_Creating_tables.html)
- [Monitoring automatic table optimization](https://docs.aws.amazon.com/redshift/latest/dg/c_ato-enabling-disabling-monitoring.html)
- [Compression encodings](https://docs.aws.amazon.com/redshift/latest/dg/c_Compression_encodings.html)
- [ANALYZE command](https://docs.aws.amazon.com/redshift/latest/dg/r_ANALYZE.html)
- [VACUUM command](https://docs.aws.amazon.com/redshift/latest/dg/r_VACUUM_command.html)
- [Creating and interpreting a query plan](https://docs.aws.amazon.com/redshift/latest/dg/c-the-query-plan.html)
- [Analyzing a query plan](https://docs.aws.amazon.com/redshift/latest/dg/c-analyzing-the-query-plan.html)
- [SYS_QUERY_HISTORY](https://docs.aws.amazon.com/redshift/latest/dg/SYS_QUERY_HISTORY.html)
- [SYS_QUERY_DETAIL](https://docs.aws.amazon.com/redshift/latest/dg/SYS_QUERY_DETAIL.html)
- [Workload management](https://docs.aws.amazon.com/redshift/latest/dg/cm-c-implementing-workload-management.html)
- [WLM query monitoring rules](https://docs.aws.amazon.com/redshift/latest/dg/cm-c-wlm-query-monitoring-rules.html)
- [Concurrency scaling](https://docs.aws.amazon.com/redshift/latest/dg/concurrency-scaling.html)
- [Materialized views](https://docs.aws.amazon.com/redshift/latest/dg/materialized-view-overview.html)
- [Refreshing materialized views](https://docs.aws.amazon.com/redshift/latest/dg/materialized-view-refresh.html)
- [Automatic query rewriting to use materialized views](https://docs.aws.amazon.com/redshift/latest/dg/materialized-view-auto-rewrite.html)
- [Automated materialized views](https://docs.aws.amazon.com/redshift/latest/dg/materialized-view-auto-mv.html)
