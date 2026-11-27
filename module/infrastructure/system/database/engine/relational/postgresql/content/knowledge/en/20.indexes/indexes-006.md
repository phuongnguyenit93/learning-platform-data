# BRIN and Data Correlated with Physical Order in PostgreSQL

When a PostgreSQL table holds millions or billions of event records, access logs, sensor readings, or transaction histories, maintaining B-tree indexes across multiple columns can consume substantial storage and write overhead. However, if rows are inserted **roughly in chronological order**, records with nearby timestamps also tend to sit close together **within physical heap pages**. A query filtering yesterday's data should not have to inspect pages filled with last year's records.

**BRIN (Block Range INdex)** exploits this property: instead of storing an entry per row, it stores **summary metadata for contiguous ranges of heap pages**. For a timestamp column, the most common summary is the minimum and maximum value within each page range. PostgreSQL can skip entire page ranges whose summarized interval cannot possibly intersect the `WHERE` predicate.

BRIN is tiny and can be very effective for **data whose column values correlate with physical heap order**, yet it is a **lossy index**: it selects pages that *might* contain matches, and the database must read and recheck tuples to produce exact results. It does not replace B-tree for unique lookups, single-row point lookups, or `ORDER BY ... LIMIT`.

This lesson belongs to the **Indexes** chapter of the **Database Engine Relational PostgreSQL** module, covering BRIN architecture, correlation, operator classes, `pages_per_range`, query plans, summarization maintenance, data loading patterns, interactions with partitioning and B-trees, and practice exercises.

## 1. The Problem: Time-Series Data Laid Out Nearly Sequentially on Disk

Suppose a `sensor_event` table has columns:

~~~text
event_id | device_id | occurred_at | temperature | payload
~~~

Every minute, the system appends new events. Rows may land in the heap like this:

~~~text
Heap blocks 0–127    : early January events
Heap blocks 128–255  : mid January events
Heap blocks 256–383  : late January events
Heap blocks 384–511  : early February events
...
~~~

Timestamps do not have to increase strictly row by row, yet each **physical page range** mostly contains events from a relatively narrow time window.

Illustrative BRIN summary:

~~~text
Range 0, blocks   0–127:
    min(occurred_at) = 2026-01-01
    max(occurred_at) = 2026-01-12

Range 1, blocks 128–255:
    min(occurred_at) = 2026-01-12
    max(occurred_at) = 2026-01-24

Range 2, blocks 256–383:
    min(occurred_at) = 2026-01-24
    max(occurred_at) = 2026-02-05
~~~

When `WHERE` requests events on January 18, Range 0 and Range 2 can be skipped immediately because their min/max bounds do not overlap that day; only Range 1 remains a candidate.

Dates in this diagram illustrate the idea only and are not numbers measured from the lab dataset.

## 2. What Are a Heap Page and a Block Range?

PostgreSQL stores table data as **heap pages** (also called blocks). Standard builds use **8 KiB** pages, which you can check with:

~~~sql
SHOW block_size;
~~~

Each page holds multiple tuples and MVCC tuple versions. A **block range** is a group of pages with consecutive block numbers.

With `pages_per_range = 32`:

~~~text
Range 0: heap blocks   0–31
Range 1: heap blocks  32–63
Range 2: heap blocks  64–95
Range 3: heap blocks  96–127
...
~~~

At an 8 KiB block size, one 32-page range covers:

\[
32 \times 8\ \text{KiB} = 256\ \text{KiB}
\]

This is the **heap region size** covered by one summary entry, not the size of the index or column. The number of rows per range varies with tuple width, dead tuples, free space, and storage factors.

**`pages_per_range` is a count of heap pages, not rows.**

## 3. How Does BRIN minmax Work?

The most intuitive BRIN operator class is **minmax**. It records the smallest and largest column values within each block range.

Example:

~~~text
Range A: [10:00, 10:29]
Range B: [10:30, 10:59]
Range C: [11:00, 11:29]
~~~

Query:

~~~sql
WHERE occurred_at >= TIMESTAMPTZ '2026-01-01 10:40:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-01-01 10:50:00+00'
~~~

Ranges A and C can be pruned. Range B overlaps the query predicate, so it is kept for tuple inspection.

### 3.1. Minmax Is Not a List of Exact Values Present in the Range

Suppose:

~~~text
Range X:
    min(value) = 10
    max(value) = 100
    actual values are only 10 and 100
~~~

When searching for `value = 50`, this range is still treated as a candidate because 50 lies between 10 and 100. PostgreSQL must recheck actual rows in the range to discover that 50 is absent.

This is a **false positive during range pruning**. BRIN must never skip a range that actually contains matching rows, though it may include extra ranges.

## 4. What Does “Correlated with Physical Order” Mean?

A column has strong **physical correlation** when its values progress in an orderly fashion along physical heap tuple positions.

Strong positive correlation:

~~~text
Heap block       occurred_at
0                08:00
1                08:05
2                08:10
3                08:15
4                08:20
~~~

Strong negative correlation:

~~~text
Heap block       occurred_at
0                08:20
1                08:15
2                08:10
3                08:05
4                08:00
~~~

**Both directions can work well with BRIN minmax:** within each physical region, the value interval stays narrow. For BRIN, ascending vs. descending direction is not decisive; what matters is that **each range stays concentrated in a small sub-interval of the domain**.

When data is scrambled:

~~~text
Heap block 0: Jan, Aug, Dec
Heap block 1: Feb, Jun, Nov
Heap block 2: Jan, May, Oct
~~~

each range's min/max spans nearly the entire year. A narrow single-day query ends up scanning many ranges because the summaries cannot prune them.

### 4.1. Strict Total Ordering Is Not Required

Real-time ingestion typically sees slightly late arrivals and concurrent writers. BRIN still works well as long as values within **the same page range** remain tightly clustered. What hurts BRIN is scattered outliers stretching summaries across the entire query domain.

## 5. Checking Correlation in PostgreSQL

PostgreSQL records correlation statistics for eligible columns:

~~~sql
SELECT
    schemaname,
    tablename,
    attname,
    correlation
FROM pg_stats
WHERE schemaname = 'brin_lab'
  AND tablename = 'sensor_event'
  AND attname = 'occurred_at';
~~~

The `correlation` value ranges from **-1 to +1**:

| Value | Typical Meaning |
|---|---|
| Near +1 | Values mostly increase with physical position |
| Near -1 | Values mostly decrease with physical position |
| Near 0 | Weak linear physical correlation |
| NULL | Missing statistics or inapplicable type |

`ANALYZE` refreshes these statistics:

~~~sql
ANALYZE brin_lab.sensor_event;
~~~

A correlation near ±1 signals BRIN is worth evaluating, **not a guarantee of performance**. You still must evaluate `WHERE` selectivity, `pages_per_range`, table size, outliers, and execution plans.

### 5.1. Correlation Does Not Measure Every Individual BRIN Summary

`pg_stats.correlation` is a table-wide linear correlation statistic; it does not list per-range min/max spans. A table can have moderate average correlation while certain regions are very clean and others are messy.

If queries mostly hit regions containing late-arriving events, high global correlation will not necessarily deliver expected pruning.

## 6. Comparing BRIN and B-tree

| Criterion | B-tree | BRIN |
|---|---|---|
| Structure | Index entries per key referencing tuples | Summaries per heap page range |
| Size | Usually much larger on big tables | Usually tiny relative to the heap |
| Highly selective primary/point lookups | Typically very fast | May read and recheck many rows |
| Range filtering on correlated data | Good | Often worth considering |
| Dependence on heap physical order | Less sensitive | Crucial for minmax |
| `ORDER BY ... LIMIT` | Can support ordered index scans | Provides no direct tuple ordering |
| `UNIQUE` / `PRIMARY KEY` | Supported | Does not enforce uniqueness |
| Index-Only Scan on covering index | Possible when MVCC allows | Cannot return exact tuples from summaries alone |
| Scrambled physical data | Still locates keys cleanly | Minmax summaries become ineffective |
| Index write cost on heavy appends | Can be substantial | Generally much lower, workload-dependent |

Never drop a B-tree primary key simply because BRIN exists. The two index types solve **different access patterns** and frequently coexist when workloads need both.

## 7. BRIN Is a Lossy Index

BRIN does not list exact matching tuples inside a range. It typically operates via **bitmap heap scan**:

~~~text
Bitmap Heap Scan on sensor_event
  Recheck Cond: (occurred_at >= ... AND occurred_at < ...)
  Rows Removed by Index Recheck: ...
  Heap Blocks: lossy=...
  -> Bitmap Index Scan on idx_sensor_event_time_brin
       Index Cond: (occurred_at >= ... AND occurred_at < ...)
~~~

Interpretation:

1. `Bitmap Index Scan` consults BRIN to find candidate page ranges.
2. Heap blocks belonging to candidate ranges are added to the bitmap.
3. `Bitmap Heap Scan` reads the selected heap pages.
4. `Recheck Cond` evaluates the SQL predicate on every tuple in those pages.
5. Non-matching rows are discarded before returning to the client.

### 7.1. Rows Removed by Index Recheck

If the plan shows:

~~~text
Rows Removed by Index Recheck: 5000
~~~

many rows on candidate pages failed the predicate during recheck. With BRIN, this is not automatically a bug; it reflects the lossy nature of range summaries.

### 7.2. Heap Blocks: lossy

This metric reports how many heap blocks were tracked as lossy (page-level) entries in the bitmap, **not a count of wrong rows**. Bitmap scans can also turn lossy due to `work_mem` limits, so inspect the full plan and context.

**Query correctness is always preserved:** BRIN may propose extra pages, yet PostgreSQL checks exact row values so no false-positive rows ever escape.

## 8. Creating a Chronologically Loaded Practice Table

This lab builds a synthetic 300,000-event table. **Run only in a dedicated lab database**, never in production; the `INSERT` and `CREATE INDEX` statements generate real I/O and disk usage.

~~~sql
CREATE SCHEMA brin_lab;

CREATE TABLE brin_lab.sensor_event (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    device_id INTEGER NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    temperature NUMERIC(6, 2) NOT NULL,
    payload TEXT
);

INSERT INTO brin_lab.sensor_event (
    device_id,
    occurred_at,
    temperature,
    payload
)
SELECT
    (g % 64 + 1)::INTEGER,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + g * INTERVAL '1 second',
    (18 + (g % 250) / 10.0)::NUMERIC(6, 2),
    'event-' || g::TEXT
FROM generate_series(1, 300000) AS g
ORDER BY g;
~~~

This table has:

- Timestamps advancing by 1 second per `g`.
- `device_id` cycling across 64 devices.
- Formula-derived `temperature`.
- Illustrative text `payload`.
- Identity `event_id` with its own B-tree primary key.

`ORDER BY g` illustrates ordered loading, though **SQL never guarantees physical order remains permanent** across `UPDATE`s, concurrent inserts, table rewrites, or maintenance.

### 8.1. Inspecting the Data

~~~sql
SELECT
    COUNT(*) AS total_rows,
    MIN(occurred_at) AS first_event,
    MAX(occurred_at) AS last_event
FROM brin_lab.sensor_event;
~~~

With a single run of the script, there are 300,000 rows; the earliest timestamp is `2026-01-01 00:00:01+00` and the latest is 300,000 seconds later.

## 9. CREATE INDEX ... USING brin

Create a BRIN index on the timestamp:

~~~sql
CREATE INDEX idx_sensor_event_time_brin
ON brin_lab.sensor_event
USING brin (occurred_at)
WITH (pages_per_range = 32, autosummarize = on);
~~~

Here:

- `USING brin` selects the BRIN access method.
- `occurred_at` is the summarized column.
- `pages_per_range = 32` creates one summary entry per 32 heap pages.
- `autosummarize = on` requests automatic summarization of new completed ranges when eligible, though **it does not mean summaries update synchronously on every `INSERT`**.

When omitted, the default `pages_per_range` is **128**.

### 9.1. BRIN Cannot Enforce UNIQUE

You cannot use BRIN to enforce uniqueness on a timestamp or ID. Uniqueness requires an appropriate index type, typically B-tree.

### 9.2. Multi-Column BRIN Indexes Are Possible

~~~sql
CREATE INDEX idx_sensor_event_time_device_brin
ON brin_lab.sensor_event
USING brin (occurred_at, device_id)
WITH (pages_per_range = 32);
~~~

Avoid keeping redundant overlapping indexes in production just to experiment. In this lab, the second index helps illustrate that multi-column BRIN summaries do not behave like a multi-column B-tree.

## 10. Querying by Time Range

~~~sql
SELECT
    event_id,
    device_id,
    occurred_at,
    temperature
FROM brin_lab.sensor_event
WHERE occurred_at >= TIMESTAMPTZ '2026-01-03 12:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-01-03 12:15:00+00';
~~~

Because the table is ordered roughly by timestamp, page ranges outside this window can be pruned.

### 10.1. Using Half-Open Intervals

Writing:

~~~sql
WHERE occurred_at >= :start_time
  AND occurred_at < :end_time
~~~

is cleaner than guessing sub-second endpoints like `23:59:59.999999`. Adjacent windows `[12:00, 12:15)` and `[12:15, 12:30)` never double-count the `12:15` boundary.

`:start_time`/`:end_time` denote application parameter placeholders; in JDBC use `?` with typed binds. They are not literal SQL executed verbatim by PostgreSQL.

### 10.2. Keep Predicates on the Indexable Column

Writing:

~~~sql
WHERE occurred_at::DATE = DATE '2026-01-03'
~~~

prevents PostgreSQL from leveraging BRIN `minmax` on the raw column as cleanly as a range predicate, and casting `TIMESTAMPTZ` to `DATE` depends on session timezone.

Compute day boundaries in the business timezone and bind two `TIMESTAMPTZ` bounds instead. Avoid altering time semantics just to hit an index.

## 11. Inspecting Plans with EXPLAIN

~~~sql
ANALYZE brin_lab.sensor_event;

EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, occurred_at, temperature
FROM brin_lab.sensor_event
WHERE occurred_at >= TIMESTAMPTZ '2026-01-03 12:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-01-03 12:15:00+00';
~~~

Observe:

- Is there a `Bitmap Index Scan` using BRIN?
- Are `Bitmap Heap Scan` and `Recheck Cond` present?
- How large is `Rows Removed by Index Recheck`?
- How many `Heap Blocks` were read?
- What do `Buffers: shared hit/read` report?
- What are `actual rows` and total execution time?
- Did the planner pick `Seq Scan` instead of BRIN?

**PostgreSQL is never forced to use BRIN just because the index exists.** On small tables, wide filters, or hot cached data, `Seq Scan` can be cheaper.

`EXPLAIN ANALYZE` executes the SQL statement; this example is a `SELECT`. Never run `EXPLAIN ANALYZE` casually on DML in production since it modifies data.

## 12. Comparing Sizes of BRIN and B-tree

Add a B-tree index in the lab:

~~~sql
CREATE INDEX idx_sensor_event_time_btree
ON brin_lab.sensor_event (occurred_at);
~~~

Check sizes:

~~~sql
SELECT
    c.relname AS index_name,
    pg_size_pretty(pg_relation_size(c.oid)) AS index_size,
    pg_relation_size(c.oid) AS bytes
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'brin_lab'
  AND c.relname IN (
      'idx_sensor_event_time_brin',
      'idx_sensor_event_time_btree'
  )
ORDER BY bytes;
~~~

BRIN is typically orders of magnitude smaller than B-tree on large tables, though **do not quote a fixed ratio** since actual sizes vary with row count, `pages_per_range`, operator class, key width, and PostgreSQL version.

Once the B-tree exists, the planner may pick it for timestamp queries. To benchmark the two index types fairly, control index visibility, cache state, dataset, and identical `WHERE` clauses.

### 12.1. Smaller Index Size Does Not Mean Faster Queries

A B-tree stores more metadata, yet pinpoints single rows or narrow intervals far more precisely. BRIN saves storage and write overhead, yet may scan and recheck extra heap pages.

## 13. Experiment with Physically Scrambled Data

Create a copy loaded in hashed ID order:

~~~sql
CREATE TABLE brin_lab.sensor_event_shuffled AS
SELECT
    event_id, device_id, occurred_at,
    temperature, payload
FROM brin_lab.sensor_event
ORDER BY md5(event_id::TEXT);

CREATE INDEX idx_shuffled_time_brin
ON brin_lab.sensor_event_shuffled
USING brin (occurred_at)
WITH (pages_per_range = 32);

ANALYZE brin_lab.sensor_event_shuffled;
~~~

The shuffled table holds the exact same logical rows, yet timestamps on adjacent heap pages are widely scattered.

**`CREATE TABLE AS` does not copy constraints, identity settings, triggers, RLS, or other attributes** from the source table. Use this table strictly for index study.

### 13.1. Comparing Correlation Across Both Tables

~~~sql
SELECT
    tablename,
    attname,
    correlation
FROM pg_stats
WHERE schemaname = 'brin_lab'
  AND tablename IN ('sensor_event', 'sensor_event_shuffled')
  AND attname = 'occurred_at'
ORDER BY tablename;
~~~

Expected:

- `sensor_event`: correlation near `+1`.
- `sensor_event_shuffled`: correlation near `0`.

Actual values may vary slightly with sampling and heap layout.

### 13.2. Comparing the Same Query

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, occurred_at, temperature
FROM brin_lab.sensor_event_shuffled
WHERE occurred_at >= TIMESTAMPTZ '2026-01-03 12:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-01-03 12:15:00+00';
~~~

When values are scattered, nearly every page range has a wide min/max span. PostgreSQL must inspect many pages, discard many rows during recheck, or switch to `Seq Scan`.

This experiment proves that **with identical row counts and identical `WHERE` clauses, BRIN effectiveness varies dramatically with physical heap order**.

## 14. pages_per_range Is a Trade-Off

Assuming an 8 KiB block size:

| pages_per_range | Max Heap Space per Range |
|---:|---:|
| 16 | 128 KiB |
| 32 | 256 KiB |
| 64 | 512 KiB |
| 128 | 1 MiB |
| 256 | 2 MiB |

A **smaller** range yields tighter min/max bounds and fewer rechecked pages, at the cost of more summary entries and a larger index.

A **larger** range yields a smaller index, yet wider min/max spans—especially with outliers—causing more non-matching pages to be read.

### 14.1. Why Not Pick pages_per_range = 1?

One summary per page maximizes BRIN granularity, yet multiplies entry count and erodes BRIN's size and maintenance advantage. If queries need exact per-row lookups, a B-tree is usually better suited.

### 14.2. How to Choose pages_per_range

1. Identify typical `WHERE` interval widths.
2. Measure how many heap pages span one typical time window.
3. Inspect correlation and late-arrival rates.
4. Benchmark a few BRIN settings in a lab.
5. Compare index size, bitmap heap blocks, and rechecked rows.
6. Compare p50/p95 latencies on representative queries.
7. Check write and maintenance overhead.
8. Pick a balanced trade-off rather than tuning for one query.

## 15. BRIN Does Not Support ORDER BY Like B-tree

Consider:

~~~sql
SELECT event_id, occurred_at
FROM brin_lab.sensor_event
ORDER BY occurred_at DESC
LIMIT 20;
~~~

A B-tree on timestamp can walk keys in order and stop after 20 entries. BRIN stores no per-row key ordering; it only knows min/max spans per page range.

Consequently, BRIN **cannot eliminate the `Sort` step for `ORDER BY ... LIMIT`**. The planner must use a B-tree, `Seq Scan` + `Sort`, or another strategy.

Even with a time filter:

~~~sql
SELECT event_id, occurred_at
FROM brin_lab.sensor_event
WHERE occurred_at >= TIMESTAMPTZ '2026-01-03 00:00:00+00'
ORDER BY occurred_at DESC
LIMIT 20;
~~~

BRIN can prune earlier ranges, yet matching rows still have to be sorted.

## 16. Single-ID Lookups Usually Belong on B-tree

~~~sql
SELECT *
FROM brin_lab.sensor_event
WHERE event_id = 123456;
~~~

Our demo table has `PRIMARY KEY(event_id)`, so PostgreSQL already provides a B-tree for exact ID lookups.

Even when `event_id` correlates closely with heap position, a BRIN index on it still selects an entire page range and rechecks many rows. BRIN is not a drop-in replacement for primary-key or foreign-key lookups.

## 17. Which Columns Fit BRIN?

Strong candidates when loaded sequentially:

- `created_at` or `occurred_at` in append-only tables.
- Monotonically increasing sequence or log offsets.
- `batch_id` when batches load contiguously.
- Reporting dates loaded day by day.
- Numeric counters inserted roughly monotonically.
- Other types with BRIN operator classes and clustered heap layouts.

Candidates requiring caution:

- `device_id` cycling across the whole table.
- Randomly updated `status` columns.
- Random UUIDs.
- `email` addresses uncorrelated with heap order.
- `occurred_at` on late-arriving events spanning years.
- Columns frequently updated to distant values.

**Column data type alone is never enough to choose BRIN.** Two pipelines storing timestamps can have completely opposite physical correlations.

## 18. Late-Arriving Data and Outliers

Suppose the system is currently ingesting July events, yet occasionally inserts a delayed February event.

~~~text
Most rows in range: 2026-07-01 ... 2026-07-03
One outlier:        2026-02-01
~~~

The `minmax` summary becomes:

~~~text
min = 2026-02-01
max = 2026-07-03
~~~

A query for April will retain this range even though zero rows actually belong to April. This is why BRIN `minmax` degrades when **outliers scatter across many ranges**.

### 18.1. Mitigation Approaches

- Batch and sort inserts by event time where pipelines allow.
- Partition by time interval.
- Route late events to a dedicated stream/table and reconcile via workflow.
- Try a smaller `pages_per_range` to isolate outliers.
- Test a multi-range summary operator class if supported by your server.
- Keep a B-tree for queries demanding extreme selectivity.
- Consider table rewrites/`CLUSTER` only when read gains outweigh operational cost.

A handful of outliers rarely justifies rewriting a multi-terabyte table.

## 19. Operator Classes: minmax, minmax-multi, and Others

BRIN is not limited to single-interval `minmax` summaries. Depending on data type and PostgreSQL version, BRIN provides operator class families such as:

- **Minmax:** one `[min, max]` interval per range.
- **Minmax-multi:** multiple disjoint sub-intervals representing value clusters inside a page range.
- **Inclusion:** bounding metadata for containment and overlap on supported types.
- **Bloom-style summaries:** probabilistic membership summaries on supported types/opclasses.

### 19.1. Why Can minmax-multi Help?

If 99% of rows in a range fall in July and 1% fall in February, plain `minmax` spans five months. Multiple tight sub-intervals represent the two clusters separately, enabling April queries to prune that range.

Trade-offs include larger index size and limited type support. Benchmark on real workloads; no BRIN operator class turns BRIN into an exact row index.

### 19.2. Listing BRIN Operator Classes on Your Server

~~~sql
SELECT
    opc.opcname,
    opc.opcintype::regtype AS input_type
FROM pg_opclass AS opc
JOIN pg_am AS am
    ON am.oid = opc.opcmethod
WHERE am.amname = 'brin'
ORDER BY opc.opcname;
~~~

Never assume an operator class name from another type or major version exists without checking.

## 20. Multi-Column BRIN Is Not Like Multi-Column B-tree

~~~sql
CREATE INDEX idx_sensor_event_time_device_brin
ON brin_lab.sensor_event
USING brin (occurred_at, device_id)
WITH (pages_per_range = 32);
~~~

Each column is summarized independently per page range using its opclass. In our lab table:

- `occurred_at` correlates tightly with the heap.
- `device_id` cycles through all 64 devices within every range.

Thus `device_id` cannot prune many ranges. A multi-column BRIN index **does not organize keys lexicographically** like a B-tree on `(device_id, occurred_at)`.

When queries frequently isolate a single device:

~~~sql
SELECT event_id, occurred_at, temperature
FROM brin_lab.sensor_event
WHERE device_id = 7
  AND occurred_at >= TIMESTAMPTZ '2026-01-02 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-01-03 00:00:00+00'
ORDER BY occurred_at DESC
LIMIT 100;
~~~

a B-tree like this is usually far more effective:

~~~sql
CREATE INDEX idx_sensor_event_device_time_btree
ON brin_lab.sensor_event (device_id, occurred_at DESC);
~~~

If the workload also runs reports **across all devices for a date window**, keeping the time BRIN index alongside it may make sense—weighed against the write cost of maintaining both.

## 21. BRIN and Partitioning Complement Each Other

Partitioning divides a table into logical child relations (such as monthly partitions). BRIN divides **heap pages inside each relation** into block ranges.

Flow:

~~~text
WHERE occurred_at within 2026-02-12
              |
              v
Partition pruning: keep only February partition
              |
              v
BRIN inside February partition:
prune ranges not overlapping day 12
              |
              v
Bitmap Heap Scan + Recheck remaining tuples
~~~

Reference DDL for another lab table:

~~~sql
CREATE TABLE brin_lab.event_partitioned (
    event_id BIGINT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    device_id INTEGER NOT NULL,
    payload TEXT
) PARTITION BY RANGE (occurred_at);

CREATE TABLE brin_lab.event_partitioned_2026_01
PARTITION OF brin_lab.event_partitioned
FOR VALUES FROM ('2026-01-01 00:00:00+00')
             TO ('2026-02-01 00:00:00+00');

CREATE TABLE brin_lab.event_partitioned_2026_02
PARTITION OF brin_lab.event_partitioned
FOR VALUES FROM ('2026-02-01 00:00:00+00')
             TO ('2026-03-01 00:00:00+00');

CREATE INDEX idx_partitioned_time_brin
ON brin_lab.event_partitioned
USING brin (occurred_at);
~~~

In supported PostgreSQL versions, creating an index on the partitioned parent creates a partitioned index and matching child indexes on each partition.

Inserting rows outside defined partition bounds without a matching/default partition fails. PostgreSQL does not auto-create monthly partitions by itself.

### 21.1. Not Every Partition Needs BRIN

If a partition is small or queries read almost the entire partition, `Seq Scan` suffices. If partitions are huge and queries target a few minutes or hours, BRIN adds real value.

Measure effectiveness **after partition pruning**, rather than assuming every partition needs identical indexing.

## 22. What Is Summarization?

BRIN summary entries represent completed page ranges. When you create a BRIN index on an existing table, PostgreSQL summarizes all existing ranges.

As new rows append to the end of the table, newly allocated page ranges may **not be summarized immediately**.

While a trailing range remains unsummarized:

- PostgreSQL still guarantees exact SQL results.
- It cannot rely on a non-existent `minmax` entry to skip that range.
- Unsummarized ranges must be scanned as candidates.
- Queries targeting the newest data may read more pages than expected.

**Unsummarized ranges never cause missing rows; they only reduce pruning efficiency.**

## 23. VACUUM and autosummarize

PostgreSQL maintains BRIN summaries via:

### 23.1. VACUUM

~~~sql
VACUUM (ANALYZE) brin_lab.sensor_event;
~~~

`VACUUM` summarizes unsummarized BRIN ranges while performing standard MVCC cleanup. `ANALYZE` updates planner statistics.

Standard `VACUUM` must run **outside an explicit transaction block**.

### 23.2. autosummarize

With:

~~~sql
WITH (pages_per_range = 32, autosummarize = on)
~~~

BRIN schedules autovacuum to summarize newly completed ranges when eligible. This **does not guarantee synchronous summarization on every `INSERT`**, because autovacuum scheduling and worker queues introduce delay.

High-ingest systems may keep a short unsummarized tail temporarily. Monitor before treating it as an error.

## 24. Manual BRIN Maintenance Functions

On an existing index:

~~~sql
SELECT brin_summarize_new_values(
    'brin_lab.idx_sensor_event_time_brin'::regclass
);
~~~

This summarizes any unsummarized ranges per supported semantics and returns the count of newly summarized ranges.

You can also summarize a specific range by passing any block number inside it:

~~~sql
SELECT brin_summarize_range(
    'brin_lab.idx_sensor_event_time_brin'::regclass,
    256
);
~~~

With `pages_per_range = 32`, block 256 begins a range.

PostgreSQL also provides `brin_desummarize_range` to clear a range's summary for controlled maintenance. Neither function is meant to be run after every `INSERT` or blindly in production.

**Never modify index files manually** to “tune BRIN.” PostgreSQL must maintain index state safely and consistently.

## 25. Filtering by Event Time vs. Ingest Time

A system often tracks two timestamps:

- `occurred_at`: when the event occurred.
- `ingested_at`: when the system received and wrote the event.

When many events arrive late, `ingested_at` follows `INSERT` order closely and exhibits much higher physical correlation than `occurred_at`.

However, a report asking for “events that occurred on January 10” **cannot swap `WHERE occurred_at ...` for `WHERE ingested_at ...`** just to make BRIN prune better. That changes the business question.

Valid options include separate indexes for each timestamp, partitioning, pre-sorting source batches by event time, or dedicated late-event pipelines. Design around domain semantics first, not benchmark numbers alone.

## 26. Viewing Heap Locations via ctid in the Lab

PostgreSQL provides the `ctid` system column showing a tuple version's physical `(block, offset)` location.

~~~sql
SELECT ctid, event_id, occurred_at
FROM brin_lab.sensor_event
ORDER BY ctid
LIMIT 30;
~~~

Compare against the shuffled table:

~~~sql
SELECT ctid, event_id, occurred_at
FROM brin_lab.sensor_event_shuffled
ORDER BY ctid
LIMIT 30;
~~~

When rows arrive roughly in chronological order, adjacent `ctid`s share close timestamps. In the shuffled table, adjacent `ctid`s jump wildly across timestamps.

### 26.1. ctid Is Not a Business Key

`ctid` is unstable across `UPDATE`s (which create new tuple versions), `CLUSTER`, `VACUUM FULL`, and table rewrites. Never use `ctid` as a primary key, foreign key, or application pagination cursor.

It is a diagnostic tool for inspecting physical layout, not a substitute for `ORDER BY`.

## 27. CLUSTER Can Change Physical Correlation

If you need to reorder heap rows by timestamp, you can run `CLUSTER` using a **clustering-capable index**, such as the B-tree created earlier.

In a **lab database**:

~~~sql
CLUSTER brin_lab.sensor_event
USING idx_sensor_event_time_btree;

ANALYZE brin_lab.sensor_event;
~~~

`CLUSTER` rewrites the table in index order at that point in time, restoring physical correlation.

### 27.1. You Cannot CLUSTER Directly Using BRIN

BRIN does not support ordered scans required for `CLUSTER`. Do not run:

~~~sql
-- Do not use:
-- CLUSTER brin_lab.sensor_event USING idx_sensor_event_time_brin;
~~~

### 27.2. CLUSTER Is Not Free

It can:

- Acquire an exclusive table lock, blocking concurrent reads and writes.
- Rewrite the entire table, requiring extra free disk space.
- Generate heavy I/O and WAL, impacting replicas.
- Require fresh statistics afterward.
- Gradually lose physical order again as new `INSERT`/`UPDATE`s arrive.

Consider `CLUSTER` only when read gains justify operational downtime/overhead and a rollback plan exists.

## 28. REINDEX, VACUUM, and ANALYZE Are Not CLUSTER

Distinguish clearly:

| Operation | Primary Purpose | Sorts Heap by a Column? |
|---|---|---|
| `ANALYZE` | Collect planner statistics | No |
| Standard `VACUUM` | MVCC cleanup, free space, visibility map, index maintenance | No |
| `REINDEX` | Rebuild index structures | No |
| `VACUUM FULL` | Rewrite table to reclaim disk space | Not an intentional key-order sort |
| `CLUSTER ... USING btree_index` | Rewrite heap in B-tree index order | Yes, at execution time |
| `CREATE TABLE AS SELECT ... ORDER BY` | Populate a new copy in `SELECT` order | Creates initial layout, not maintained later |

**Rebuilding BRIN does not fix scattered physical heap order.** If wide `minmax` spans stem from scrambled rows, address data layout or pick another index type—not just `REINDEX`.

## 29. Ordered CTAS to Compare Again in the Lab

~~~sql
CREATE TABLE brin_lab.sensor_event_reordered AS
SELECT
    event_id, device_id, occurred_at,
    temperature, payload
FROM brin_lab.sensor_event_shuffled
ORDER BY occurred_at, event_id;

CREATE INDEX idx_reordered_time_brin
ON brin_lab.sensor_event_reordered
USING brin (occurred_at)
WITH (pages_per_range = 32);

ANALYZE brin_lab.sensor_event_reordered;
~~~

Now you can compare:

- `sensor_event_shuffled`: scattered timestamps.
- `sensor_event_reordered`: ordered timestamps.

Never use `CTAS` as a naive production table replacement: it **does not copy** constraints, identity columns, foreign keys, triggers, RLS policies, grants, or other table properties.

## 30. BRIN Does Not Serve Index-Only Scans Like a Covering B-tree

With a covering B-tree and all-visible heap pages under MVCC, PostgreSQL can often satisfy queries via **`Index Only Scan`**.

BRIN holds range summaries, not individual row keys or values. For example:

~~~sql
SELECT occurred_at
FROM brin_lab.sensor_event
WHERE occurred_at >= TIMESTAMPTZ '2026-01-03 12:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-01-03 12:15:00+00';
~~~

Even though `SELECT` requests only `occurred_at`, BRIN still must visit candidate heap pages to read and verify actual values. It is never an exact index-only lookup.

The visibility map cannot turn a `minmax` summary into a list of matching tuples.

## 31. BRIN Under UPDATE and MVCC

`UPDATE` normally writes a new tuple version under MVCC. If timestamps or indexed values change, PostgreSQL must keep summaries valid for the heap pages receiving those versions.

When a table frequently modifies time keys:

- Physical correlation degrades.
- Range summaries widen.
- Dead tuples awaiting cleanup add heap work.
- Heap and index maintenance incur write cost.

Append-only historical tables are far more natural BRIN candidates than tables with arbitrary timestamp updates.

### 31.1. Updating Other Columns Still Costs Work

Even updating `payload` without changing `occurred_at` creates a new tuple version, affects physical placement, and writes WAL. Never assume `UPDATE`s stay in place or become free because a BRIN index is used.

## 32. NULLs and Operators on BRIN Columns

If an indexed column is nullable, queries like `IS NULL` follow different semantics from ordered value comparisons. BRIN and its operator classes track NULL presence per range; never treat `NULL` simply as the smallest timestamp.

Our demo uses `occurred_at NOT NULL`, keeping predicates simpler. When a table contains `NULL`s, test the opclass and `EXPLAIN` plans for your actual conditions.

Do not add BRIN merely because a column is nullable; examine `NULL` fraction, key `WHERE` clauses, and physical layout.

## 33. Can BRIN Apply Beyond Timestamps?

Yes. What matters is:

1. Does a BRIN operator class support the type and operators?
2. Do values cluster within heap page ranges?
3. Does `WHERE` prune a large fraction of ranges?
4. Do queries avoid needing exact sorting or point lookups that BRIN lacks?
5. Does the tiny index size outweigh the cost of rechecking candidate pages?

Sequence IDs, dates, batch IDs, monotonically loaded metrics, and other clustered data types are all worth testing.

Not every numeric or date column has strong physical correlation.

## 34. Can BRIN Compute Exact COUNT(*)?

~~~sql
SELECT COUNT(*)
FROM brin_lab.sensor_event
WHERE occurred_at >= TIMESTAMPTZ '2026-01-03 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-01-04 00:00:00+00';
~~~

BRIN can shrink the set of heap pages scanned. However, `minmax` summaries **do not store exact row counts for arbitrary predicates**. PostgreSQL must still inspect matching tuples and MVCC visibility to return an exact `COUNT`.

If daily count reports run constantly, consider a summary/rollup table with its own update and reconciliation strategy.

## 35. Broad Queries May Not Benefit from BRIN

Example:

~~~sql
SELECT COUNT(*)
FROM brin_lab.sensor_event
WHERE occurred_at >= TIMESTAMPTZ '2020-01-01 00:00:00+00';
~~~

If the table starts in 2026, **every range matches**. BRIN prunes zero pages, so `Seq Scan` is cheaper.

BRIN helps only when it can **prune a substantial share of irrelevant ranges**, not merely because a query contains `>=`.

## 36. Large Tables and Continuous Ingestion: What to Monitor

Operational metrics worth tracking:

- `INSERT` rate and the age/volume of unsummarized trailing page ranges.
- Rate of late-arriving events.
- `UPDATE`/`DELETE` volume.
- Autovacuum and BRIN summarization activity.
- BRIN vs. competing B-tree sizes.
- Shifts in `pg_stats.correlation` across batches.
- Query plans and heap blocks read.
- Ratio of range scans to point lookups.
- Effectiveness of partition pruning.
- End-to-end application latency and total cost, not a single `EXPLAIN`.

A BRIN index can shine during initial append-only ingestion and gradually degrade if ingestion shifts toward backfilling historical data.

## 37. Reading pg_stat_user_indexes Carefully

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'brin_lab'
  AND relname = 'sensor_event'
ORDER BY idx_scan DESC, indexrelname;
~~~

Stats show whether an index is scanned, though keep in mind:

- Counters may have been reset.
- Bitmap heap fetches are not attributed identically to regular `Index Scan`s.
- BRIN and B-tree have very different index-entry models.
- `idx_tup_read` is not equivalent to valid SQL rows returned.
- An index used by weekly jobs can show low `idx_scan` over a single-day window.

Read usage stats alongside `EXPLAIN` for real queries; never drop an index based solely on one isolated counter snapshot.

## 38. BRIN Index Design Checklist

1. Confirm whether primary queries are **range scans** rather than point lookups or `ORDER BY`.
2. Measure table size and current index storage footprint.
3. Check column correlation with the physical heap.
4. Inspect ingestion patterns, late arrivals, and `UPDATE` frequency.
5. Verify whether `WHERE` predicates prune many page ranges.
6. Choose an operator class matching your data type and PostgreSQL version.
7. Test several `pages_per_range` values.
8. Build BRIN in a lab on representative data.
9. Run `ANALYZE` so the planner has current statistics.
10. Inspect `EXPLAIN (ANALYZE, BUFFERS)` and rechecked row counts.
11. Compare against B-tree and `Seq Scan` for the same queries.
12. Check whether `ORDER BY ... LIMIT` requires a B-tree.
13. Combine with partitioning and evaluate per-partition indexing.
14. Plan `VACUUM`, `autosummarize`, or manual summarization properly.
15. Measure write overhead and storage across all indexes.
16. Never edit index files manually or force planner flags in production.
17. If considering heap reordering, weigh locks, I/O, WAL, and downtime.
18. Monitor effectiveness over time as physical correlation can drift.

No single BRIN setting fits every table. Choose based on **how data is written, how queries filter it, and how tight summaries stay in practice**.

## 39. Common Mistakes

### Mistake 1 — BRIN stores one entry per row

No. It stores summaries per group of heap pages.

### Mistake 2 — pages_per_range is a row count

No, it is a count of physical heap pages.

### Mistake 3 — Correlation near -1 is bad

No. Strong negative correlation still yields tight `minmax` ranges.

### Mistake 4 — Any TIMESTAMPTZ column fits BRIN automatically

No. Interleaving old and new events produces low physical correlation.

### Mistake 5 — BRIN returns exact tuples straight from the index

No. It is lossy and requires reading and rechecking heap pages.

### Mistake 6 — BRIN accelerates every ORDER BY LIMIT

No. It does not support ordered index scans like B-tree.

### Mistake 7 — Use BRIN to enforce UNIQUE

No. Use an index method supporting uniqueness, typically B-tree.

### Mistake 8 — The smallest pages_per_range is always fastest

No. Index size and maintenance grow without always helping queries.

### Mistake 9 — The largest pages_per_range is always best

No. Overly wide summaries cause excessive false-positive ranges.

### Mistake 10 — BRIN(a, b) works like a smaller B-tree(a, b)

No. BRIN summarizes each column independently per block range.

### Mistake 11 — REINDEX reorders the heap

No. `REINDEX` never sorts table rows.

### Mistake 12 — VACUUM restores physical correlation

Standard `VACUUM` does not reorder heap rows by key.

### Mistake 13 — CLUSTER directly on a BRIN index

BRIN is not an ordered index capable of driving `CLUSTER`.

### Mistake 14 — autosummarize = on means instant summary after every INSERT

No. Summarization runs asynchronously via autovacuum scheduling.

### Mistake 15 — Unsummarized ranges lose query rows

No. PostgreSQL scans unsummarized ranges as candidates to guarantee correctness.

### Mistake 16 — Rows Removed by Index Recheck is a bug

No. It is normal behavior for lossy bitmap rechecks.

### Mistake 17 — pg_stats.correlation is always up-to-the-second exact

It is sampled statistics that may lag; run `ANALYZE` and verify `EXPLAIN`.

### Mistake 18 — Smaller index always means faster query

Queries still read and recheck candidate heap pages and may sort.

### Mistake 19 — SQL without ORDER BY guarantees heap order

There is zero result-order guarantee without `ORDER BY`.

### Mistake 20 — ctid is a stable row key

No. `ctid` changes on `UPDATE`s and table rewrites.

### Mistake 21 — Adding extra BRIN/B-tree indexes is free

Every index adds storage, WAL, and write/maintenance overhead.

### Mistake 22 — BRIN minmax computes exact COUNT from summaries

No. `minmax` does not store row counts for arbitrary filters.

### Mistake 23 — BRIN and partitioning are mutually exclusive

Partition pruning and BRIN range pruning work cleanly together.

### Mistake 24 — Choose BRIN from table size alone

No. Correlation, selectivity, `WHERE`/`ORDER BY`, and late arrivals matter just as much.

## 40. Practice Exercises

### Exercise 1 — Block Range

`pages_per_range = 64`, `block_size = 8 KiB`. How many KiB of heap does one range cover at most?

**Hint:** 512 KiB.

### Exercise 2 — Range Pruning

Range A has min = 10, max = 20. Query asks `x >= 30 AND x < 40`. Can BRIN prune Range A?

**Hint:** yes.

### Exercise 3 — False Positives

A range has min = 10, max = 100, yet actual rows only contain 10 and 100. Must a query for `x = 50` still recheck that range?

**Hint:** yes, `minmax` cannot prove 50 is absent.

### Exercise 4 — Positive Correlation

Rows are inserted with timestamps increasing across blocks. Correlation is close to what value?

**Hint:** `+1`.

### Exercise 5 — Negative Correlation

Rows are inserted with timestamps steadily decreasing across blocks. Does BRIN perform poorly because correlation is negative?

**Hint:** no; near `-1` is still strong correlation.

### Exercise 6 — Scrambled Data

When loading with `ORDER BY md5(event_id::TEXT)`, what happens to timestamp `minmax` ranges?

**Hint:** they become wide and prune very few pages.

### Exercise 7 — CREATE INDEX

Write SQL creating a BRIN on `occurred_at` with `pages_per_range = 32`.

**Hint:** `USING brin (occurred_at) WITH (pages_per_range = 32)`.

### Exercise 8 — EXPLAIN

Which plan nodes/metrics reveal BRIN's lossy behavior?

**Hint:** `Bitmap Heap Scan`, `Recheck Cond`, `Rows Removed by Index Recheck`.

### Exercise 9 — ORDER BY

A query fetches the 20 newest events with no `WHERE` clause. Is BRIN or B-tree on time usually better?

**Hint:** B-tree, because it provides an ordered scan.

### Exercise 10 — Uniqueness

Can BRIN back `PRIMARY KEY(event_id)`?

**Hint:** no.

### Exercise 11 — Index Size

Write SQL fetching BRIN byte size via `pg_relation_size`.

**Hint:** pass the index `regclass`.

### Exercise 12 — Multi-Column

Why might `BRIN(device_id, time)` prune poorly on `device_id` when devices cycle through every range?

**Hint:** per-range min/max for `device_id` spans almost all devices.

### Exercise 13 — Single-Device Timeline

Propose a B-tree for `WHERE device_id = ? ORDER BY occurred_at DESC LIMIT 50`.

**Hint:** `(device_id, occurred_at DESC)`.

### Exercise 14 — Late Arrivals

A February event is inserted into a page holding July events. What happens to the `minmax` summary?

**Hint:** the summary stretches from February to July.

### Exercise 15 — CTID

Why shouldn't `ctid` be used as a long-lived pagination cursor?

**Hint:** it changes across `UPDATE`s and table rewrites.

### Exercise 16 — CLUSTER

Can BRIN be passed directly to `CLUSTER ... USING`?

**Hint:** no; use a clustering-capable B-tree index.

### Exercise 17 — REINDEX

Does `REINDEX` on BRIN sort the heap chronologically?

**Hint:** no.

### Exercise 18 — VACUUM

Does regular `VACUUM` restore timestamp physical correlation?

**Hint:** no, it does not reorder rows.

### Exercise 19 — autosummarize

Does enabling `autosummarize` guarantee every new range is summarized immediately at `COMMIT`?

**Hint:** no, it runs asynchronously in the background with delay.

### Exercise 20 — Manual Summarization

Write the command calling `brin_summarize_new_values` on the lab BRIN index.

**Hint:** pass `'brin_lab.idx_sensor_event_time_brin'::regclass`.

### Exercise 21 — Unsummarized Ranges

Why can an unsummarized range slow down a query without ever losing matching rows?

**Hint:** PostgreSQL treats unsummarized ranges as candidates that might hold matches.

### Exercise 22 — Partitioning

If a table is partitioned by month and each partition has a time BRIN index, what two levels of pruning occur for a single-day `WHERE` filter?

**Hint:** partition pruning followed by BRIN range pruning.

### Exercise 23 — COUNT

Can a `minmax` BRIN return an exact `COUNT(*)` for one day without inspecting tuples?

**Hint:** no.

### Exercise 24 — Minmax-multi

A range holds two distant timestamp clusters. Why might `minmax-multi` be worth testing?

**Hint:** multiple intervals describe disjoint clusters much more tightly than one wide span.

### Exercise 25 — Broad Query

A `WHERE` clause matches over 90% of the table. Might the planner choose `Seq Scan` over BRIN?

**Hint:** yes.

### Exercise 26 — Workload-Based Index Choice

Pick indexes for (a) finding a customer by email; (b) daily log reports on an append-only table; (c) the 20 latest events for a specific device.

**Hint:** (a) unique B-tree, (b) time BRIN worth testing, (c) B-tree `(device, time)`.

### Exercise 27 — Practical Measurement

Compare the ordered and shuffled tables via `EXPLAIN`. What should you check besides execution time?

**Hint:** index/heap nodes, rechecked rows, heap blocks, and buffers.

### Exercise 28 — pg_stats

Write a query reading `correlation` for both practice tables.

**Hint:** query `pg_stats` filtering schema, table, and `attname`.

### Exercise 29 — Ingest Time vs. Event Time

If many events arrive late, which column likely has higher physical correlation? Can you blindly switch `WHERE` to it?

**Hint:** `ingested_at` may correlate better, yet it changes business semantics.

### Exercise 30 — pages_per_range

Does lowering `pages_per_range` always improve queries?

**Hint:** no; index size and maintenance overhead increase.

### Exercise 31 — Index Usage

Is `idx_scan = 0` over a single day enough to drop a BRIN index?

**Hint:** no, if periodic jobs use it or stats were recently reset.

### Exercise 32 — Ordering Data

Does `CTAS` with `ORDER BY timestamp` copy all PKs, FKs, and triggers?

**Hint:** no; schema objects require explicit migration.

## 41. Summary

- **BRIN** is a **block-range** index storing compact summaries of heap page ranges instead of per-row index entries.
- With **`minmax`**, it prunes entire page ranges whose bounds cannot intersect the `WHERE` predicate.
- Its greatest benefit appears when column values **correlate with physical heap order**: chronologically appended dates, events, or sequences.
- Correlations **near either +1 or -1** work well. Scrambled inserts and late-arriving events widen `minmax` ranges.
- BRIN is **lossy**, so `Bitmap Heap Scan` must apply `Recheck Cond` on tuples inside candidate pages.
- **`pages_per_range`** tunes summary granularity; smaller ranges prune better at the expense of larger index size.
- BRIN is usually **tiny** on large tables, yet never replaces B-tree for primary/unique keys, selective point lookups, or `ORDER BY ... LIMIT`.
- Multi-column BRIN still tracks **independent per-column page-range summaries**, unlike a multi-column B-tree.
- **Partitioning** and BRIN complement each other: partition pruning narrows child tables, while BRIN prunes page ranges inside them.
- **Summarization** must keep up as new pages are appended via `VACUUM`, `autosummarize`, or `brin_summarize_*` functions.
- **`REINDEX`/`VACUUM`/`ANALYZE` do not reorder the heap.** Improving physical correlation via physical sorting requires `CLUSTER` or table rewrites with real operational costs.
- Evaluate using **`pg_stats.correlation`**, `pg_relation_size`, and **`EXPLAIN (ANALYZE, BUFFERS)`** on representative workloads rather than guesswork or index size alone.

Mental model:

~~~text
Column values correlate with heap order
                |
                v
   Tight min/max within each range
                |
                v
    BRIN prunes most page ranges
                |
                v
 Read and recheck only remaining pages
                |
                v
   Lower I/O with a tiny index footprint
~~~

The core principle of BRIN is not merely the `CREATE INDEX ... USING brin` syntax. **Physical data layout determines how useful range summaries actually are.** Understanding that link lets you choose among BRIN, B-tree, and partitioning based on how PostgreSQL actually reads data rather than index names alone.
