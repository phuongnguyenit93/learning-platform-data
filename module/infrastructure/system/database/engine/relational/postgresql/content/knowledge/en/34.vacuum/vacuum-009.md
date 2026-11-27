# Measuring Dead Tuples, VACUUM Runs, and Maintenance Progress in PostgreSQL

## 1. Why Measure VACUUM?

PostgreSQL uses MVCC so multiple transactions can read data versions consistent with their snapshots. When a row is updated or deleted, the old version usually cannot be erased immediately because another transaction may still need to see it. Unneeded tuple versions are called dead tuples; VACUUM determines when they can be reclaimed and updates the relevant metadata.

In production, the operational question is not merely "how many dead tuples does the table have?". We need to know:

- How fast is the dead tuple estimate climbing?
- When did the most recent manual VACUUM and autovacuum occur?
- Is autovacuum currently running, which phase is it in, and how many heap blocks has it scanned?
- Is a VACUUM running long because the table is huge, due to index cleanup, I/O, locks, or an old transaction holding back the horizon?
- Is the table genuinely running out of space, or does it merely hold reusable free space?
- Is autovacuum keeping up with the UPDATE/DELETE/INSERT rate?
- Are statistics current, or were they recently reset/not yet updated?
- Which partitions need maintenance when the parent table holds no heap pages?

No single metric answers all of these. You must combine table statistics, progress views, activity, logs, relation sizes, and selective physical checks.

```text
Table statistics
  n_live_tup / n_dead_tup / last_autovacuum
                    |
                    v
       Estimate where maintenance is needed
                    |
                    v
pg_stat_progress_vacuum ---- pg_stat_activity
 phase, heap blocks           worker, waits, blockers
                    |
                    v
          Logs + relation size
                    |
                    v
      Diagnose cause and measure trend
                    |
                    v
        Tune / schedule / verify
```

## 2. Learning Objectives

After this lesson, you will be able to:

1. Distinguish live tuples, dead tuples, obsolete tuple versions, and reusable free space.
2. Understand why `n_dead_tup` is only an estimate.
3. Read `pg_stat_user_tables` and `pg_stat_all_tables`.
4. Interpret `last_vacuum`, `last_autovacuum`, `vacuum_count`, and `autovacuum_count`.
5. Distinguish a VACUUM cleanup trigger from a freeze trigger.
6. Estimate autovacuum thresholds from table size.
7. Understand insert-triggered vacuum and analyze thresholds.
8. Identify the effects of per-table `reloptions`.
9. Monitor a running VACUUM via `pg_stat_progress_vacuum`.
10. Interpret `phase`, `heap_blks_scanned`, `heap_blks_vacuumed`, and `index_vacuum_count`.
11. Distinguish VACUUM progress from ANALYZE progress.
12. Locate autovacuum workers and wait events in `pg_stat_activity`.
13. Use `log_autovacuum_min_duration` to observe autovacuum runs.
14. Distinguish dead tuple estimates from physical measurements via `pgstattuple`.
15. Understand bloat, free space, and when disk space can return to the OS.
16. Locate transaction/replication horizons blocking tuple removal.
17. Evaluate vacuum cadence relative to write rate and table size.
18. Build dashboards, alerts, and maintenance runbooks.
19. Handle vacuums that run long, do not run, or run continuously.
20. Verify effectiveness after changing configuration or running manual VACUUM.

## 3. Concepts to Measure

### 3.1. Live Tuple

A live tuple is a row version still considered valid under the current data state. One logical row can have multiple tuple versions due to UPDATEs; only the version matching the latest snapshot is the current version.

### 3.2. Dead Tuple

A dead tuple is a tuple version no longer visible to any valid transaction snapshot and eligible to be reclaimed. A recently deleted tuple is not necessarily dead immediately: an older transaction may still need to see it.

### 3.3. Tuples No Longer Visible Yet Not Yet Reclaimable

Sometimes a tuple has been superseded, yet a transaction holding an old snapshot may still need that version. VACUUM must retain it until the global visibility horizon advances far enough. Thus dead tuple estimates can climb even while VACUUM runs without removing all expected tuples.

### 3.4. Reusable Free Space

VACUUM normally marks space inside heap pages so PostgreSQL can reuse it for later INSERT/UPDATEs. That does not mean the relation file shrinks immediately on the filesystem.

### 3.5. Bloat

Bloat is space used inefficiently due to tuple versions, page fill patterns, index structure, or fragmentation. Dead tuple count is one signal, not a complete bloat measurement.

### 3.6. Why Distinguish These Concepts?

| Observation | What You Can Conclude | What You Cannot Conclude |
| --- | --- | --- |
| High `n_dead_tup` | Statistics estimate many dead tuples | VACUUM is definitely broken |
| Low `n_dead_tup` | Few estimated dead tuples | Table/indexes have no bloat |
| Recent `last_autovacuum` | One autovacuum run was recorded | That run fixed every issue |
| VACUUM progress 100% heap scan | Heap scan reached reported extent | Entire vacuum is finished |
| Relation size did not drop | File did not shrink | VACUUM had no effect |
| `vacuum_count` increased | Manual VACUUM was recorded | Autovacuum ran |
| `autovacuum_count` increased | Autovacuum was recorded | All tables are maintained on time |

## 4. Reading pg_stat_user_tables

This is typically the first view inspected for user tables.

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    n_mod_since_analyze,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze,
    vacuum_count,
    autovacuum_count,
    analyze_count,
    autoanalyze_count
FROM pg_catalog.pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 50;
```

### 4.1. Key Columns

| Column | Meaning |
| --- | --- |
| `schemaname`, `relname` | Schema and table name |
| `n_live_tup` | Estimated live tuples |
| `n_dead_tup` | Estimated dead tuples |
| `n_mod_since_analyze` | Estimated row modifications since the latest ANALYZE |
| `last_vacuum` | Timestamp of the latest recorded manual VACUUM |
| `last_autovacuum` | Timestamp of the latest recorded autovacuum |
| `last_analyze` | Timestamp of the latest manual ANALYZE |
| `last_autoanalyze` | Timestamp of the latest autoanalyze |
| `vacuum_count` | Recorded manual VACUUM runs since stats reset |
| `autovacuum_count` | Recorded autovacuum runs since stats reset |
| `analyze_count` | Recorded manual ANALYZE runs |
| `autoanalyze_count` | Recorded autoanalyze runs |

### 4.2. How Does pg_stat_all_tables Differ?

`pg_stat_user_tables` focuses on user tables. `pg_stat_all_tables` includes system tables as well. When investigating catalogs or system relations, use the `all` view rather than only the `user` view.

### 4.3. Dead Percentage Is Only an Estimated Ratio

You can compute a ratio to sort tables:

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    round(
        100.0 * n_dead_tup
        / NULLIF(n_live_tup + n_dead_tup, 0),
        2
    ) AS estimated_dead_pct,
    pg_size_pretty(
        pg_total_relation_size(
            format('%I.%I', schemaname, relname)::regclass
        )
    ) AS total_size
FROM pg_catalog.pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 50;
```

The column name `estimated_dead_pct` deliberately emphasizes that it is an estimate. A 10,000-row table with 30% dead tuples may matter far less than a 2-billion-row table at 3%, depending on storage size and churn rate.

### 4.4. Look at Both Absolute Counts and Ratios

Dashboards should include:

- Absolute dead tuple estimate.
- Estimated dead percentage.
- Total relation size.
- Dead tuple growth rate over time.
- Time since last vacuum.
- Write rate and latest vacuum duration.

Never prioritize solely by percentage or solely by raw count.

## 5. Understanding the Limits of Statistics

### 5.1. n_dead_tup Is Not an Exact COUNT(*)

PostgreSQL maintains table statistics via its statistics collection mechanism. Live/dead tuple values in the view are estimates, can lag, and can shift after ANALYZE/VACUUM or stats refreshes.

Never treat the following query as an exact physical count:

```sql
SELECT n_dead_tup
FROM pg_stat_user_tables
WHERE relname = 'orders';
```

### 5.2. Statistics May Not Reflect Just-Completed Workloads

Right after a massive UPDATE batch, statistics may not update instantaneously. Wait for collector/backend flushing and query from an appropriate session/transaction.

### 5.3. Statistics Snapshots Within a Transaction

Statistics views may be read from a snapshot cached inside the current transaction depending on version and consistency rules. When fresh readings are needed, use short transactions or call `pg_stat_clear_snapshot()` before the next read where appropriate for your version.

### 5.4. Resetting Counters Alters Interpretation

Functions such as `pg_stat_reset()` and `pg_stat_reset_single_table_counters()` reset counters. After a reset, `vacuum_count`/`autovacuum_count` drop to 0 and historical counts are lost.

Never reset statistics to "make dashboards look clean" or before preserving evidence. If resetting for an experiment, record the reset timestamp and scope.

### 5.5. NULL Timestamps Do Not Automatically Mean Errors

`last_autovacuum IS NULL` may simply mean no autovacuum has been recorded since the last stats reset or the table has never needed autovacuum. Check stats resets, table age, thresholds, and logs before concluding anything.

## 6. Tracking VACUUM and ANALYZE History

A handy dashboard query:

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count,
    last_analyze,
    last_autoanalyze,
    analyze_count,
    autoanalyze_count
FROM pg_catalog.pg_stat_user_tables
ORDER BY
    COALESCE(last_autovacuum, last_vacuum) NULLS FIRST,
    n_dead_tup DESC;
```

### 6.1. Timestamps Are Not Runtimes

`last_autovacuum` tells you when the latest run was recorded, not how long it took. Runtime comes from progress/activity views while running or from logs after completion.

### 6.2. Counts Are Not Permanent Lifetime History

Counters depend on stats resets and instance lifecycles. If you need multi-month audit history, export metrics and logs to an external monitoring system rather than relying on in-database counters forever.

### 6.3. Manual Vacuum and Autovacuum Are Separate Sources

A DBA running `VACUUM table_name` does not increment `autovacuum_count`. Conversely, autovacuum workers increment `autovacuum_count`.

### 6.4. Analyze Does Not Replace VACUUM

ANALYZE refreshes planner statistics. It does not remove dead tuples or replace freezing. VACUUM can be called with `ANALYZE` to do both, yet their purposes and counters remain separate.

## 7. Estimating Autovacuum Thresholds

Dead-tuple autovacuum cleanup normally uses a base threshold plus a scale factor.

An approximate formula:

```text
vacuum threshold =
    autovacuum_vacuum_threshold
    + autovacuum_vacuum_scale_factor * reltuples
```

Where `reltuples` is the estimated row count in `pg_class`, not necessarily exact.

### 7.1. Example

Suppose:

- `autovacuum_vacuum_threshold = 50`
- `autovacuum_vacuum_scale_factor = 0.2`
- `reltuples = 1,000,000`

Estimated threshold:

```text
50 + 0.2 * 1,000,000 = 200,050 dead tuples
```

A large table can accumulate vast numbers of dead tuples before triggering on scale factor. That is why large tables often need lower per-table settings.

### 7.2. Reading Global Settings

```sql
SELECT
    name,
    setting,
    unit,
    source
FROM pg_catalog.pg_settings
WHERE name IN (
    'autovacuum',
    'track_counts',
    'autovacuum_vacuum_threshold',
    'autovacuum_vacuum_scale_factor',
    'autovacuum_vacuum_insert_threshold',
    'autovacuum_vacuum_insert_scale_factor',
    'autovacuum_analyze_threshold',
    'autovacuum_analyze_scale_factor',
    'autovacuum_max_workers',
    'autovacuum_naptime'
)
ORDER BY name;
```

If a setting does not exist on your current major version, it simply will not appear in the output.

### 7.3. Per-Table reloptions Can Override Global Values

A table can specify custom options such as `autovacuum_vacuum_scale_factor` or `threshold`. Thus formulas using global settings are only estimates unless you check for table overrides.

Inspect relation options:

```sql
SELECT
    c.oid::regclass AS relation,
    c.reltuples,
    c.reloptions
FROM pg_catalog.pg_class AS c
WHERE c.relkind IN ('r', 'm')
  AND c.reloptions IS NOT NULL
ORDER BY c.oid::regclass::text;
```

### 7.4. Example Setting Scale Factor on a Large Table

```sql
ALTER TABLE app.orders
SET (
    autovacuum_vacuum_scale_factor = 0.02,
    autovacuum_vacuum_threshold = 5000
);
```

This is an example only. Pick values based on write rate, table size, vacuum runtime, I/O capacity, and bloat tolerance. Never copy the same values blindly to every table.

### 7.5. Review After Changing

After a change, watch across multiple cycles:

- Dead tuple estimate right before vacuum.
- Time taken to trigger.
- Runtime and phases.
- Dead tuple estimate after vacuum.
- Disk/I/O impact.
- Whether vacuum runs incessantly.

Settings that are too low make autovacuum run constantly and contend for I/O; settings that are too high let dead tuples pile up too long.

## 8. Insert-Triggered Vacuum and ANALYZE Thresholds

### 8.1. Append-Only Tables Can Still Need Autovacuum

An insert-only table with few dead tuples still needs vacuuming to freeze transaction IDs. Beyond the dead-tuple trigger, PostgreSQL has triggers based on newly inserted rows and freeze age.

### 8.2. Insert Threshold

An approximate formula for insert-triggered vacuum:

```text
insert vacuum threshold =
    autovacuum_vacuum_insert_threshold
    + autovacuum_vacuum_insert_scale_factor * reltuples
```

This is especially helpful for insert-heavy tables since freeze vacuuming cannot wait forever on dead tuples.

### 8.3. Analyze Threshold

Autoanalyze triggers based on estimated modifications:

```text
analyze threshold =
    autovacuum_analyze_threshold
    + autovacuum_analyze_scale_factor * reltuples
```

Analyze refreshes statistics so the planner picks good plans. A table with low dead tuples can still need ANALYZE after a major data distribution shift.

### 8.4. n_mod_since_analyze

This column tracks estimated modifications since the latest analyze. It is a statistical estimate/counter, not a transaction count or SQL statement count.

### 8.5. Freeze Thresholds Are a Separate Mechanism

Do not confuse cleanup triggers with `autovacuum_freeze_max_age` or MultiXact freeze thresholds. A relation can trigger anti-wraparound vacuum even when dead tuple counts are low.

## 9. Identifying Which Relations Need Maintenance Priority

Query combining size, dead tuples, timestamps, and vacuum cadence:

```sql
SELECT
    s.schemaname,
    s.relname,
    s.n_live_tup,
    s.n_dead_tup,
    round(
        100.0 * s.n_dead_tup
        / NULLIF(s.n_live_tup + s.n_dead_tup, 0),
        2
    ) AS estimated_dead_pct,
    pg_size_pretty(pg_relation_size(s.relid)) AS heap_size,
    pg_size_pretty(pg_indexes_size(s.relid)) AS indexes_size,
    pg_size_pretty(pg_total_relation_size(s.relid)) AS total_size,
    s.last_autovacuum,
    s.autovacuum_count,
    s.last_vacuum,
    s.vacuum_count
FROM pg_catalog.pg_stat_user_tables AS s
ORDER BY
    pg_total_relation_size(s.relid) DESC,
    s.n_dead_tup DESC
LIMIT 100;
```

### 9.1. Why Check Both Heap Size and Index Size?

VACUUM must process both the heap and indexes. A table with a small heap and huge indexes can still spend a lot of time in the index vacuum phase.

### 9.2. Partitioned Tables

A partitioned parent usually holds no heap rows. Monitor individual leaf partitions and their indexes; if aggregation is needed, group by parent/partition tree using catalog inheritance metadata.

### 9.3. TOAST

Large values may reside in a TOAST relation. When investigating tables with large payloads, remember total relation size includes TOAST and indexes, while heap-only size hides that footprint.

## 10. Physical Measurement with pgstattuple

When statistical estimates are not enough for investigation, the `pgstattuple` extension provides detailed physical measurements.

### 10.1. Installing the Extension

Requires appropriate privileges and the extension installed on the server:

```sql
CREATE EXTENSION IF NOT EXISTS pgstattuple;
```

### 10.2. Detailed Measurement with pgstattuple

```sql
SELECT *
FROM pgstattuple('app.orders'::regclass);
```

Output normally includes:

| Column | Meaning |
| --- | --- |
| `table_len` | Relation size in bytes |
| `tuple_count` | Observed live tuples |
| `tuple_len` | Bytes occupied by live tuples |
| `tuple_percent` | Percentage of bytes in live tuples |
| `dead_tuple_count` | Observed dead tuples |
| `dead_tuple_len` | Bytes occupied by dead tuples |
| `dead_tuple_percent` | Percentage of bytes in dead tuples |
| `free_space` | Free bytes |
| `free_percent` | Percentage of free bytes |

`pgstattuple` scans the relation and can generate substantial I/O. Choose timing and scope carefully, especially on multi-hundred-GB or TB tables.

### 10.3. pgstattuple_approx

```sql
SELECT *
FROM pgstattuple_approx('app.orders'::regclass);
```

The approximate function leverages the visibility map to skip scanning certain pages in suitable cases. Results are approximations, not a substitute for an exact full scan.

### 10.4. Do Not Run pgstattuple Continuously on Every Table

It is a diagnostic tool, not a metric to poll every few seconds. Use it to confirm suspicions or capture scheduled baselines selectively.

### 10.5. Comparing with Statistics

| Source | Advantages | Limitations |
| --- | --- | --- |
| `pg_stat_user_tables` | Lightweight, dashboard-friendly | Estimates, subject to lag |
| `pgstattuple` | Detailed physical measurement | Can scan entire relation, I/O-heavy |
| `pgstattuple_approx` | Fewer scans when eligible | Approximate, relies on VM |
| `VACUUM VERBOSE` logs | Shows exact results of one vacuum run | Available only when logging is enabled/captured |

## 11. VACUUM Does Not Necessarily Shrink Files

A common misconception: running VACUUM finishes, yet `pg_total_relation_size` does not drop.

### 11.1. Space Reuse

VACUUM normally marks free space for PostgreSQL to reuse internally within the relation. The filesystem file can stay the same size while pages inside gain useful empty space.

### 11.2. Tail Heap Truncation

Under certain conditions, VACUUM can truncate completely empty pages at the end of a relation and return them to the filesystem. This requires suitable conditions and locking; not all free pages can be truncated.

### 11.3. VACUUM FULL

`VACUUM FULL` rewrites the relation to reclaim space aggressively, requiring strong locks, runtime, and disk headroom. It is not a routine replacement for standard VACUUM.

### 11.4. Index Bloat

Heap vacuuming does not necessarily shrink index files appreciably. Index cleanup marks/recycles index pages per index type and access method; severe index bloat warrants separate investigation. Never judge index bloat from heap dead tuples.

### 11.5. Measure Heap, Indexes, and Total Size Together

```sql
SELECT
    c.oid::regclass AS relation,
    pg_size_pretty(pg_relation_size(c.oid)) AS heap_size,
    pg_size_pretty(pg_indexes_size(c.oid)) AS indexes_size,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_catalog.pg_class AS c
WHERE c.oid = 'app.orders'::regclass;
```

Compare before and after under matching conditions to observe trends.

## 12. Monitoring Running VACUUM via pg_stat_progress_vacuum

This view shows which VACUUMs are running and their phase progress.

```sql
SELECT
    p.pid,
    a.datname,
    p.relid::regclass AS relation,
    p.phase,
    p.heap_blks_total,
    p.heap_blks_scanned,
    p.heap_blks_vacuumed,
    p.index_vacuum_count,
    p.max_dead_tuples,
    p.num_dead_tuples,
    round(
        100.0 * p.heap_blks_scanned
        / NULLIF(p.heap_blks_total, 0),
        1
    ) AS heap_scan_pct,
    clock_timestamp() - a.query_start AS runtime,
    a.wait_event_type,
    a.wait_event
FROM pg_catalog.pg_stat_progress_vacuum AS p
JOIN pg_catalog.pg_stat_activity AS a
  ON a.pid = p.pid
ORDER BY a.query_start;
```

### 12.1. Key Columns

| Column | Interpretation |
| --- | --- |
| `pid` | Backend running VACUUM |
| `relid` | Relation being vacuumed |
| `phase` | Current phase |
| `heap_blks_total` | Total heap blocks in progress scope |
| `heap_blks_scanned` | Heap blocks scanned |
| `heap_blks_vacuumed` | Heap blocks vacuumed |
| `index_vacuum_count` | Number of index vacuum cycles completed |
| `max_dead_tuples` | Capacity of the dead tuple storage array |
| `num_dead_tuples` | Dead tuples currently buffered in the array |

### 12.2. Common Phases

Exact phase names can vary across major versions, but typically include:

1. `initializing`: initializing VACUUM.
2. `scanning heap`: scanning heap for dead tuples and metadata to process.
3. `vacuuming indexes`: processing index entries pointing to dead tuples.
4. `vacuuming heap`: processing heap pages after index phase.
5. `cleaning up indexes`: cleaning up index structures.
6. `truncating heap`: attempting to truncate empty trailing heap pages if eligible.
7. `performing final cleanup`: updating catalog/statistics and wrapping up.

Do not assume every version or every VACUUM displays all of those exact phases.

### 12.3. Computing Heap Scan Percentage

`heap_scan_pct` is the fraction of blocks scanned out of total blocks reported by the progress view. It is meaningful during the `scanning heap` phase.

Once VACUUM moves to `vacuuming indexes` or cleanup, heap scan may already be at 100% while the job is far from done. Never use this single ratio as overall "percent complete".

### 12.4. num_dead_tuples Is Not Total Dead Tuples in the Table

`num_dead_tuples` is the count currently held in the vacuum process's buffer/array for index cleanup. When the array fills up, VACUUM runs an index vacuum cycle and resumes scanning. It is not a table-wide dead tuple count.

### 12.5. index_vacuum_count

If VACUUM runs multiple index cleanup cycles, this counter increments. Multiple cycles are not automatically an error; on huge tables, it explains why the index phase repeats.

### 12.6. What Does No Rows in the Progress View Mean?

It simply means no VACUUM process is visible at the moment of the query. VACUUM may not have been scheduled yet, may have already finished, may be waiting for a worker slot, or may be blocked before reaching an observable phase. Check history, logs, stats, and the autovacuum launcher.

## 13. Monitoring Autovacuum Workers via pg_stat_activity

```sql
SELECT
    pid,
    datname,
    backend_type,
    application_name,
    state,
    query_start,
    clock_timestamp() - query_start AS runtime,
    wait_event_type,
    wait_event,
    left(query, 300) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE backend_type = 'autovacuum worker'
   OR query LIKE 'autovacuum:%'
ORDER BY query_start;
```

### 13.1. backend_type

Modern PostgreSQL versions classify processes via `backend_type`. On older versions lacking this column, match on query text or application name appropriate for that version.

### 13.2. Wait Events

- `IO`: worker waiting on I/O.
- `Lock`: waiting on a lock.
- `BufferPin`: potentially waiting on a buffer pin.
- No wait event: backend may be running on CPU or not currently waiting.

Wait events are clues only. Combine with phase, runtime, and workload to confirm root causes.

### 13.3. Autovacuum Query Text Is Not Always Human-Friendly

`query` may show an autovacuum command or internal string depending on version. Use `pg_stat_progress_vacuum.relid` to pinpoint the exact relation when a worker is vacuuming.

### 13.4. Multiple Concurrent Workers

Autovacuum can run multiple workers across different relations. Never inspect just one PID; aggregate worker counts, target relations, runtimes, and waits.

## 14. Monitoring ANALYZE Separately

VACUUM progress and ANALYZE progress use two separate views. While ANALYZE runs, inspect:

```sql
SELECT
    p.pid,
    a.datname,
    p.relid::regclass AS relation,
    p.phase,
    p.sample_blks_total,
    p.sample_blks_scanned,
    p.ext_stats_total,
    p.ext_stats_computed,
    clock_timestamp() - a.query_start AS runtime
FROM pg_catalog.pg_stat_progress_analyze AS p
JOIN pg_catalog.pg_stat_activity AS a
  ON a.pid = p.pid;
```

Specific columns and phases can vary by version. If no rows appear, ANALYZE is either not running or already finished.

### 14.1. Why Does Analyze Progress Matter?

A table can be vacuumed regularly while planner statistics remain stale if analyze falls behind. Poor query plans slow workloads and add system pressure.

### 14.2. VACUUM ANALYZE

```sql
VACUUM (ANALYZE, VERBOSE) app.orders;
```

This requests both vacuum and analyze. Run outside transaction blocks. On large tables, assess runtime/I/O and pick an appropriate window.

## 15. VACUUM VERBOSE and Logs

### 15.1. Manual Run with VERBOSE

```sql
VACUUM (VERBOSE) app.orders;
```

Verbose output reports pages, tuples, and index cleanup performed by VACUUM. Exact formatting depends on PostgreSQL version.

### 15.2. log_autovacuum_min_duration

This setting controls logging for autovacuum/autoanalyze runs meeting a duration threshold:

```sql
SHOW log_autovacuum_min_duration;
```

- Negative values normally disable autovacuum logging via this setting.
- `0` logs every autovacuum run.
- Positive values log runs lasting at least that many milliseconds.

Logging every run long-term can produce heavy log volume; weigh storage, retention, and diagnostic goals.

### 15.3. Useful Details in Logs

Logs can reveal:

- Relation vacuumed.
- Pages scanned/vacuumed.
- Tuples removed vs. remaining.
- Index cleanup cycles.
- Buffer usage/cost details.
- Runtime.
- Why autovacuum triggered in certain messages/versions.

### 15.4. Logs and Statistics Complement Each Other

Statistics power quick dashboards; progress views track active jobs; logs preserve post-run details. Combine all three to build a complete timeline.

## 16. Identifying Vacuum Blocked by the Transaction Horizon

VACUUM cannot remove tuple versions while an old snapshot could still need them. When `n_dead_tup` stays high even as VACUUM runs without dropping it, look for horizon blockers.

### 16.1. Oldest Transactions

```sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    state,
    xact_start,
    clock_timestamp() - xact_start AS xact_age,
    backend_xmin,
    CASE
        WHEN backend_xmin IS NOT NULL THEN age(backend_xmin)
    END AS backend_xmin_age,
    wait_event_type,
    wait_event,
    left(query, 250) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

### 16.2. Idle in Transaction

```sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    xact_start,
    clock_timestamp() - xact_start AS xact_age,
    state_change,
    clock_timestamp() - state_change AS idle_age,
    backend_xmin,
    left(query, 250) AS last_query
FROM pg_catalog.pg_stat_activity
WHERE state = 'idle in transaction'
ORDER BY xact_start;
```

Read-only transactions can also hold old snapshots. Never search only for sessions running UPDATE/DELETE.

### 16.3. Replication Slots

```sql
SELECT
    slot_name,
    slot_type,
    active,
    xmin,
    CASE WHEN xmin IS NOT NULL THEN age(xmin) END AS xmin_age,
    catalog_xmin,
    CASE
        WHEN catalog_xmin IS NOT NULL THEN age(catalog_xmin)
    END AS catalog_xmin_age,
    restart_lsn
FROM pg_catalog.pg_replication_slots
ORDER BY GREATEST(
    COALESCE(age(xmin), 0),
    COALESCE(age(catalog_xmin), 0)
) DESC;
```

Slots can hold WAL and/or visibility/catalog horizons. Confirm the owner and consumer before changing or dropping a slot.

### 16.4. Prepared Transactions

```sql
SELECT
    transaction,
    gid,
    prepared,
    clock_timestamp() - prepared AS prepared_age,
    owner,
    database
FROM pg_catalog.pg_prepared_xacts
ORDER BY prepared;
```

Long-lived prepared transactions hold locks and transaction state. Resolve via coordinator/runbook; never automatically roll back every prepared transaction.

### 16.5. Interpreting When Vacuum Cannot Reclaim

A VACUUM can scan successfully yet fail to remove all expected tuples due to the global horizon. Adding workers or raising cost limits will not clear the underlying blocker.

## 17. VACUUM, Visibility Map, and Index Cleanup

### 17.1. Heap and Indexes Have Different Work

VACUUM finds unneeded tuple versions in the heap, then processes index entries pointing to them. Tables with many or massive indexes can spend substantial time in index phases.

### 17.2. Visibility Map

The VM tracks per-page all-visible and all-frozen state. It supports index-only scans and lets certain vacuum scans skip already-safe pages. The VM is not a dead tuple counter.

### 17.3. Deferred Index Cleanup

Certain VACUUM options and workload conditions affect index cleanup. If cleanup is deferred, dead index entries persist longer; do not judge solely from heap `n_dead_tup`.

### 17.4. Heap Vacuumed Blocks

`heap_blks_vacuumed` shows blocks vacuumed in the progress context. It does not measure bytes returned to the OS or total bloat removed.

### 17.5. Track Index Size Separately

Use `pg_indexes_size()` and inspect index usage/structure against workloads. If indexes show bloat, evaluate appropriate tools like `REINDEX`/`REINDEX CONCURRENTLY` per version and locking needs; that is separate from standard VACUUM.

## 18. Tracking Table Size and Changes Over Time

A single size snapshot is far less informative than a trend.

```sql
SELECT
    s.schemaname,
    s.relname,
    pg_relation_size(s.relid) AS heap_bytes,
    pg_indexes_size(s.relid) AS index_bytes,
    pg_total_relation_size(s.relid) AS total_bytes,
    s.n_live_tup,
    s.n_dead_tup,
    s.last_autovacuum
FROM pg_catalog.pg_stat_user_tables AS s
ORDER BY pg_total_relation_size(s.relid) DESC
LIMIT 100;
```

Store periodic snapshots in an external monitoring system to analyze:

- Daily heap/index/total sizes.
- Dead tuple estimates.
- Vacuum timestamps and runtimes.
- Insert/update/delete rates.
- Vacuum progress duration.
- Free disk space.
- WAL generation and replication lag.

Never create an unbounded metrics table inside the same database without a retention cleanup plan.

## 19. Capacity Planning and Vacuum Cadence

### 19.1. Throughput Is the Deciding Factor

A 100 GB table receiving a few thousand updates per day differs completely from a 100 GB table receiving millions of updates per hour. Evaluate tuple-version generation rate against vacuum cleanup capacity.

### 19.2. Runtime vs. Interval

If a table needs vacuuming every 10 minutes yet each vacuum takes 30 minutes, worker capacity or threshold strategy has a problem. Track runtimes and intervals via logs and metrics.

### 19.3. Autovacuum Worker Slots

Multiple tables crossing thresholds together compete for `autovacuum_max_workers`. A critical relation may wait for a worker slot even when eligible for vacuum.

### 19.4. I/O Budget

VACUUM shares storage bandwidth with applications, backups, and replication. Cost delays pace vacuuming but can make it fall behind. Measure latency and throughput instead of blindly raising cost limit.

### 19.5. Large Tables

Fixed scale factors make dead tuple thresholds climb with table size. Use smaller scale factors for large tables paired with base thresholds to avoid over-vacuuming small tables.

### 19.6. Partitioning

Partitioning scopes maintenance and lets vacuum target individual partitions. However, excessive partitions add catalog overhead and autovacuum scheduling work. Choose balanced partition granularity.

## 20. Recommended Dashboard

An operational dashboard should cover:

| Group | Metrics | Purpose |
| --- | --- | --- |
| Table health | `n_dead_tup`, `estimated_dead_pct` | Spot accumulation |
| Table health | heap/index/total bytes | Measure storage impact |
| Maintenance history | `last_autovacuum`, `last_vacuum` | Spot tables unvacuumed too long |
| Maintenance history | `autovacuum_count`, `vacuum_count` | View runs since reset |
| Analyze | `n_mod_since_analyze`, `last_autoanalyze` | Spot stale planner stats |
| Active progress | `phase`, `heap_blks_scanned/total` | Track running vacuums |
| Active progress | runtime, wait events | Diagnose slowdowns |
| Horizon | oldest xact age, `backend_xmin` | Find blockers |
| Replication | slot `xmin`/`catalog_xmin`, lag | Detect retention pins |
| Capacity | autovacuum workers, I/O, free disk | Confirm capacity to keep up |
| Freeze | XID/MXID age | Prevent wraparound |

### 20.1. Alert on Trends

Alert when dead tuple estimates climb steadily across multiple scrapes, vacuum intervals stretch abnormally, runtimes exceed baselines, or freeze age nears thresholds.

### 20.2. Do Not Alert on a Single Sample

Statistics can lag or reset. Use multi-sample windows, thresholds, and table-size/write-rate context to cut false positives.

### 20.3. Severity by Impact

- **Info:** vacuum just ran, metrics stable.
- **Warning:** dead tuple estimate climbing, vacuum interval/runtime above baseline.
- **Critical:** anti-wraparound age nearing limit, vacuum making no progress, disk/WAL near full, or severe horizon blocker.

## 21. Runbook When Dead Tuples Spike

### Step 1. Identify the Table and Scale

Gather `n_dead_tup`, estimated percentage, heap/index/total size, write rate, and partition scope.

### Step 2. Check the Latest Vacuum

Read `last_autovacuum`, `last_vacuum`, counters, and reset history. Verify whether the table has ever been autovacuumed.

### Step 3. Check If Autovacuum Is Running

Use `pg_stat_progress_vacuum` and `pg_stat_activity`. If a worker is active, inspect `phase`, runtime, wait events, and relation.

### Step 4. Check Thresholds

Read global settings, `reltuples`, and `reloptions`. Compute approximate thresholds and compare against write rate. Never call autovacuum "broken" if the table has not crossed its trigger yet.

### Step 5. Search for Horizon Blockers

Check long transactions, `idle in transaction`, prepared transactions, replication slots, and standby feedback.

### Step 6. Inspect Logs

Use autovacuum logs to verify runtime, pages, tuples, index cycles, and any cancellations/failures.

### Step 7. Choose Action

- If not yet at threshold: consider table-specific tuning if workload warrants.
- If worker slots are exhausted: inspect worker count and backlog.
- If I/O is slow: measure storage and balance vacuum cost.
- If the horizon is pinned: clear the blocker cleanly.
- If index cleanup is the bottleneck: inspect index workload and size.
- If exact physical proof is needed: run `pgstattuple` selectively.

### Step 8. Verify Afterward

Re-check estimates, timestamps, progress/logs, and size trends. Never treat exit code 0 from `VACUUM` as proof everything is resolved.

## 22. Running Manual VACUUM Properly

### 22.1. Standard VACUUM

```sql
VACUUM (VERBOSE) app.orders;
```

### 22.2. VACUUM with ANALYZE

```sql
VACUUM (ANALYZE, VERBOSE) app.orders;
```

### 22.3. VACUUM FREEZE

```sql
VACUUM (FREEZE, VERBOSE) app.orders;
```

Use when intentionally freezing earlier per plan. Freezing and anti-wraparound are distinct concerns; watch both XID/MXID age and dead tuples.

### 22.4. VACUUM Cannot Run Inside a Transaction Block

Do not wrap these commands in an explicit `BEGIN ... COMMIT`. Some migration tools wrap statements in transactions automatically; configure a non-transactional mode for VACUUM.

### 22.5. Target the Right Relation

If a relation is a partitioned parent, vacuuming the parent may not process heap work the way you expect; check leaf partitions. Verify privileges and maintenance windows.

### 22.6. VACUUM FULL Is Not the Default

Use `VACUUM FULL` only when the genuine goal is rewriting/shrinking and locks, runtime, and disk headroom are planned. It is never a substitute for regular autovacuum.

## 23. Diagnostic Scenarios

| Symptom | Possible Cause | Next Evidence to Check |
| --- | --- | --- |
| High `n_dead_tup`, `last_autovacuum` NULL | Not triggered yet, stats reset, autovacuum disabled, or worker not run | Settings, `reloptions`, logs, counters |
| High `n_dead_tup`, worker scanning | Large table or vacuum progressing | Progress phase, runtime, blocks |
| Heap scan finished yet worker still running | Index cleanup / final cleanup | `phase`, `index_vacuum_count`, waits |
| Vacuum ran multiple times yet estimate stays high | High write rate, estimate lag, horizon blocker | Trend, transactions, logs |
| Low dead estimate yet large size | Free space / bloat / index size | `pgstattuple`, index size, history |
| Size did not drop after VACUUM | Space marked reusable inside relation | Heap size trend, future inserts |
| Autovacuum runs continuously | Threshold too low or high churn | `reloptions`, write rate, runtime |
| One partition stale | Parent holds no heap; partition missed trigger or worker backlog | Per-leaf partition stats |
| Stale analyze timestamp | Analyze threshold unreached or stats reset | `n_mod_since_analyze`, analyze settings |
| Vacuum cannot reclaim tuples | Snapshot/horizon holding them | `backend_xmin`, slots, prepared xacts |
| Many index vacuum cycles | Dead tuple array filled multiple times | `index_vacuum_count`, index count, logs |
| Vacuum slow on I/O | Storage contention / cost throttling | Wait events, disk metrics, logs |

## 24. Mistakes to Avoid

1. Treating `n_dead_tup` as an exact count.
2. Judging vacuum solely by `last_autovacuum` without checking runtime and outcome.
3. Confusing `vacuum_count` with `autovacuum_count`.
4. Concluding a table needs no vacuum because it has no UPDATE/DELETEs.
5. Treating 100% heap scan as meaning the entire vacuum is complete.
6. Treating `num_dead_tuples` in the progress view as table-wide dead tuples.
7. Polling `pgstattuple` continuously across all large tables.
8. Resetting statistics before capturing diagnostic evidence.
9. Raising autovacuum workers without checking I/O and CPU.
10. Raising scale factor just to quiet log noise.
11. Disabling autovacuum to avoid I/O.
12. Canceling anti-wraparound vacuum because workloads look slow.
13. Reaching for `VACUUM FULL` as a default remedy.
14. Expecting standard VACUUM to always shrink files on the filesystem.
15. Ignoring indexes, TOAST, or partitions when checking total relation size.
16. Overlooking old transactions and replication slots.
17. Comparing metrics across two timestamps without checking stats resets.
18. Alerting on a single `n_dead_tup` sample.
19. Assuming ANALYZE replaces VACUUM.
20. Failing to retain logs/metrics, losing visibility into vacuum cadence over time.

## 25. Practice Exercises with Answers

Exercises use PostgreSQL catalog/statistics views. All `VACUUM` commands must run outside transaction blocks.

### Exercise 1. What is a dead tuple?

**Answer:** A tuple version no longer visible to any valid snapshot and eligible to be reclaimed when VACUUM runs.

### Exercise 2. Why might a freshly deleted tuple not be reclaimable yet?

**Answer:** An older transaction snapshot may still need to see that tuple version.

### Exercise 3. Is `n_dead_tup` an exact COUNT?

**Answer:** No. It is a statistical estimate.

### Exercise 4. Which view monitors user tables?

**Answer:** `pg_stat_user_tables`.

### Exercise 5. Which view includes system tables too?

**Answer:** `pg_stat_all_tables`.

### Exercise 6. What does `n_live_tup` mean?

**Answer:** Estimated count of live tuples in the relation.

### Exercise 7. How does `last_autovacuum` differ from `last_vacuum`?

**Answer:** One records the latest autovacuum; the other records the latest manual VACUUM.

### Exercise 8. Does `autovacuum_count` count manual VACUUMs?

**Answer:** No. Manual VACUUMs are tracked in `vacuum_count`.

### Exercise 9. What is `n_mod_since_analyze` used for?

**Answer:** Estimating row modifications since the latest ANALYZE.

### Exercise 10. Does a NULL `last_autovacuum` prove autovacuum is disabled?

**Answer:** No. It may simply not have triggered yet, stats may have reset, or none was recorded yet.

### Exercise 11. Dead-tuple vacuum threshold formula?

```text
autovacuum_vacuum_threshold
+ autovacuum_vacuum_scale_factor * reltuples
```

**Answer:** Base threshold plus scale factor times estimated row count.

### Exercise 12. With threshold 50, scale factor 0.2, and 1 million rows, roughly what is the threshold?

**Answer:** 200,050 dead tuples.

### Exercise 13. Is `reltuples` an exact absolute count?

**Answer:** No. It is an estimate in `pg_class`.

### Exercise 14. Can `reloptions` change the threshold?

**Answer:** Yes. Per-table options can override global settings.

### Exercise 15. When is insert-triggered vacuum helpful?

**Answer:** On insert-heavy/append-only tables with few dead tuples that still need freeze vacuuming and VM updates.

### Exercise 16. What does the autoanalyze trigger use?

**Answer:** Analyze threshold plus analyze scale factor times `reltuples` per effective configuration.

### Exercise 17. Is a freeze trigger the same as a dead-tuple trigger?

**Answer:** No. Anti-wraparound triggers on XID/MultiXact age.

### Exercise 18. Which query shows the latest autovacuum timestamp?

**Answer:** Read `last_autovacuum` in `pg_stat_user_tables` or `pg_stat_all_tables`.

### Exercise 19. Does `last_autovacuum` show runtime?

**Answer:** No. Runtime comes from progress views or logs.

### Exercise 20. Why can counters drop back to 0?

**Answer:** Statistics can be reset by reset functions or administrative events.

### Exercise 21. Should you reset stats before measuring?

**Answer:** Only in controlled lab experiments after recording baselines; never reset production stats to erase history.

### Exercise 22. Which view monitors a running VACUUM?

**Answer:** `pg_stat_progress_vacuum`.

### Exercise 23. What is `heap_blks_scanned`?

**Answer:** Number of heap blocks scanned so far in the progress context.

### Exercise 24. What is `heap_blks_total`?

**Answer:** Total heap blocks reported by the progress view for that relation during the vacuum run.

### Exercise 25. Does 100% heap scan mean VACUUM is done?

**Answer:** No. Index cleanup, truncation, and final cleanup may still remain.

### Exercise 26. Is `num_dead_tuples` the same as `n_dead_tup`?

**Answer:** No. It is the dead tuples currently buffered by the vacuum worker for processing.

### Exercise 27. What does `index_vacuum_count` show?

**Answer:** Number of index vacuum cycles executed so far in that run.

### Exercise 28. Why can one VACUUM execute multiple index cycles?

**Answer:** The dead tuple storage array can fill up, forcing vacuum to clean indexes in multiple passes.

### Exercise 29. What does zero rows in `pg_stat_progress_vacuum` mean?

**Answer:** No VACUUM is visible at the instant of the query; it does not prove no table needs vacuum.

### Exercise 30. Which view monitors autovacuum workers?

**Answer:** `pg_stat_activity`, combined with `backend_type`/query text and `pg_stat_progress_vacuum`.

### Exercise 31. What can wait event `IO` tell you?

**Answer:** The backend is waiting on I/O; cross-check storage metrics and current phase.

### Exercise 32. Which view tracks ANALYZE progress?

**Answer:** `pg_stat_progress_analyze`.

### Exercise 33. What does `VACUUM ANALYZE` do?

**Answer:** Performs both vacuum cleanup/freezing and planner statistics updates.

### Exercise 34. Which setting logs autovacuum runs?

**Answer:** `log_autovacuum_min_duration`.

### Exercise 35. What does `log_autovacuum_min_duration = 0` mean?

**Answer:** Logs every autovacuum/autoanalyze run governed by this setting.

### Exercise 36. How does `pgstattuple` differ from `pg_stat_user_tables`?

**Answer:** `pgstattuple` measures physical storage details directly; `pg_stat_user_tables` gives lightweight estimates for monitoring.

### Exercise 37. Why can `pgstattuple` consume heavy I/O?

**Answer:** It scans the relation to measure tuple and free-space bytes.

### Exercise 38. What does `pgstattuple_approx` use to reduce scanning?

**Answer:** It leverages the visibility map to skip/estimate pages under eligible conditions.

### Exercise 39. Does standard VACUUM always shrink the file?

**Answer:** No. It mainly marks space for reuse; it only truncates trailing heap pages when conditions allow.

### Exercise 40. How does `VACUUM FULL` differ from standard `VACUUM`?

**Answer:** FULL rewrites the relation, reclaims space aggressively, and requires a strong exclusive lock.

### Exercise 41. Why measure index size separately?

**Answer:** Index cleanup and index bloat have different lifecycles and costs from heap dead tuples.

### Exercise 42. Query to measure total relation size?

```sql
SELECT pg_size_pretty(pg_total_relation_size('app.orders'::regclass));
```

**Answer:** `pg_total_relation_size()` includes the relation, indexes, and associated TOAST.

### Exercise 43. Does a partitioned parent have heap blocks like a leaf partition?

**Answer:** Usually not; monitor the leaf partitions holding physical heap storage.

### Exercise 44. Why do long transactions retain dead tuples?

**Answer:** Old snapshots may still need earlier tuple versions.

### Exercise 45. What does `backend_xmin` help investigate?

**Answer:** It reflects the `xmin` horizon held by a backend in certain states, helping locate old snapshots.

### Exercise 46. Which replication slot fields can hold the vacuum horizon?

**Answer:** `xmin` and `catalog_xmin`; `restart_lsn` is a separate WAL retention marker.

### Exercise 47. Should you drop an inactive slot to speed up VACUUM?

**Answer:** Never automatically. Verify the consumer, retention, and recovery/resync plan first.

### Exercise 48. Is autovacuum running continuously always a bug?

**Answer:** No. It can reflect a high write workload or intentionally low thresholds; compare runtime, interval, I/O, and backlog.

### Exercise 49. Why might large tables need a lower scale factor?

**Answer:** High scale factors create massive absolute thresholds, letting too many dead tuples accumulate before triggering.

### Exercise 50. What risk comes with raising `autovacuum_max_workers`?

**Answer:** Increased I/O and CPU contention if storage/host capacity is insufficient.

### Exercise 51. Why must autovacuum not be disabled?

**Answer:** Dead tuples build up, statistics go stale, and wraparound risk grows.

### Exercise 52. If size stays unchanged after VACUUM, was the command useless?

**Answer:** No. Space may have been marked reusable for PostgreSQL internally.

### Exercise 53. Can dead percentage be low while dead bytes are huge?

**Answer:** Yes. A massive table can have a small percentage that still equals huge dead bytes.

### Exercise 54. Does `pg_stat_progress_vacuum` show runtime directly?

**Answer:** Not directly; join `pg_stat_activity` and compute from `query_start`.

### Exercise 55. Why read logs after vacuum finishes?

**Answer:** Progress views show only active jobs; logs retain final results and durations once finished.

### Exercise 56. Why check stats reset times?

**Answer:** Counters and timestamps only reflect activity since the latest reset rather than full lifetime history.

### Exercise 57. If VACUUM is blocked by the horizon, is raising cost limit enough?

**Answer:** No. You must resolve the transaction, slot, or prepared transaction pinning the horizon.

### Exercise 58. How should cadence be measured?

**Answer:** Record timestamps/runtimes and write/dead-tuple trends across multiple cycles, comparing intervals against tuple generation rates.

### Exercise 59. Should dead tuple alerts trigger from a single sample?

**Answer:** No. Use multiple samples, table size, write rate, and trends to avoid false positives from stats lag.

### Exercise 60. Build an investigation checklist for a table with rising `n_dead_tup`

**Suggested answer:**

1. Collect `n_live_tup`, `n_dead_tup`, estimated percentage, and relation size.
2. Check `last_autovacuum`/`last_vacuum`, counters, and stats reset context.
3. Compute approximate thresholds from global settings, `reltuples`, and `reloptions`.
4. Check `pg_stat_progress_vacuum` for phase and runtime.
5. Inspect autovacuum worker waits in `pg_stat_activity`.
6. Read `log_autovacuum_min_duration` or `VACUUM VERBOSE` logs if available.
7. Locate long transactions, `idle in transaction` sessions, prepared transactions, and slot `xmin`.
8. Run `pgstattuple` selectively if physical confirmation is needed.
9. Pick tuning/remediation matching the blocker, threshold, I/O, and workload.
10. Re-measure dead estimates, timestamps, runtime, and size trends afterward.

## 26. Production Operations Checklist

| Check | What to Ensure |
| --- | --- |
| `n_live_tup`/`n_dead_tup` | Track estimates and trends |
| Dead percentage | Label clearly as an estimate |
| Heap/index/total size | Measure individually |
| `last_autovacuum` | Track critical tables |
| `last_vacuum` | Distinguish manual vs. auto |
| `vacuum_count`/`autovacuum_count` | Know stats reset context |
| `n_mod_since_analyze` | Track planner statistics freshness |
| Global autovacuum settings | Baseline documented |
| Per-table `reloptions` | Audited |
| Insert vacuum threshold | Checked on append-only tables |
| Freeze threshold | Monitored separately from dead tuple threshold |
| `pg_stat_progress_vacuum` | Track phases and blocks |
| `pg_stat_activity` | Worker runtime and wait events |
| `pg_stat_progress_analyze` | Track analyze when needed |
| `log_autovacuum_min_duration` | Logged appropriately for goals |
| `pgstattuple` | Used selectively for diagnostics only |
| Long transactions | Alerted with runbooks |
| Idle in transaction | Controlled |
| Prepared transactions | Owner and runbook defined |
| Replication slots | Monitor `xmin`/`catalog_xmin`/`restart_lsn` |
| Partition leaf tables | Tracked individually |
| TOAST/index size | Included in total footprint |
| Autovacuum workers | Sufficient capacity without overload |
| Storage I/O | Headroom verified |
| VACUUM runtime/interval | Baselined per relation |
| Dead tuple trend | Not just one snapshot |
| Free disk space | Sufficient for maintenance |
| Freeze age | Tracked separately for wraparound |
| Post-vacuum verification | Before/after measured |
| Metrics retention | Long enough for historical trends |

## 27. Summary

Measuring dead tuples and VACUUM progress is a multi-layered observability practice. `pg_stat_user_tables` supplies estimates and history; `pg_stat_progress_vacuum` shows where active jobs stand; `pg_stat_activity` reveals workers and wait events; logs preserve completed outcomes; and `pgstattuple` provides physical confirmation when truly needed.

Key principles:

1. **`n_dead_tup` is an estimate.** Use it to spot trends and prioritize investigation.
2. **`last_autovacuum` and `last_vacuum` differ.** Never conflate manual and automatic maintenance.
3. **Counters depend on stats resets.** Keep reset context in mind when analyzing history.
4. **Dead tuple thresholds differ from freeze thresholds.** Append-only tables still require vacuuming.
5. **Global settings can be overridden by `reloptions`.** Threshold calculations are incomplete without per-table overrides.
6. **Progress phases matter more than one percentage.** 100% heap scan does not mean index or final cleanup is done.
7. **`num_dead_tuples` in the progress view is not the table-wide dead count.**
8. **Standard VACUUM mainly enables space reuse.** Files do not necessarily shrink on the filesystem.
9. **Heap, indexes, and TOAST must be inspected separately.** A small heap can still carry heavy index cleanup cost.
10. **Long transactions and replication slots pin horizons.** Vacuum can run yet fail to reclaim expected tuples.
11. **Logs complement statistics and progress views.** They retain durations and results of finished runs.
12. **`pgstattuple` has real scan cost.** Never poll full scans across all large relations.
13. **Autovacuum capacity must match write rates.** Adjust workers and cost settings with measurement.
14. **Alert on trends and impact.** Combine dead bytes, size, runtime, cadence, and freeze age.
15. **Always verify after changes.** Inspect stats, logs, progress, and sizes within the same scope.

Brief diagnostic model:

```text
Dead tuple estimate rising?
          |
          v
Which table, how big, what write rate?
          |
          v
Threshold reached? reloptions overriding?
          |
          v
Is autovacuum running?
      +---+---+
      |       |
     Yes      No
      |       |
      v       v
Phase / wait  Worker slots / scheduling /
/ runtime     config / logs
      |       |
      +---+---+
          |
          v
Any horizon blockers?
          |
          v
Re-measure stats + logs + size trends
          |
          v
Confirm vacuum keeps up with workload
```

**Final review question:** "When `n_dead_tup` climbs, can we tell whether it is a stale estimate, an unreached threshold, a worker waiting on I/O, an active index cleanup pass, or an old transaction pinning the horizon? And after VACUUM finishes, do we have evidence that maintenance is keeping pace with the workload rather than just seeing exit status success?" A good monitoring setup answers these with verifiable metrics and timelines.
