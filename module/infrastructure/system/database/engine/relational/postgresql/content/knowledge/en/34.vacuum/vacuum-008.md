# Insert-Heavy Workloads and High-Churn Tables in PostgreSQL

PostgreSQL tables with heavy INSERT volume or frequent UPDATE/DELETEs require a VACUUM strategy tailored to their rate of change. An append-only table may create very few dead tuples yet still need vacuuming to update the visibility map and freeze old tuples. A high-churn table creates many tuple versions, dead index entries, and heavy cleanup pressure. The exact same autovacuum settings may work fine on small tables while failing to keep up on billion-row tables or tables absorbing tens of thousands of changes per second.

Optimizing VACUUM for heavy workloads is not simply raising worker count or lowering scale factors. You must understand **the type of modifications occurring**, **vacuum/analyze thresholds**, **I/O and WAL capacity**, **HOT updates and indexes**, **transaction horizons**, and **partitioning/retention**, then measure effectiveness with real statistics. The goal is keeping dead tuples and XID age bounded, keeping planner statistics current, avoiding needless bloat, and protecting application latency.

This lesson belongs to the **VACUUM** chapter in the **Database Engine Relational PostgreSQL** module. It focuses on insert-heavy tables, high-churn tables, how autovacuum reacts to INSERTs, per-table tuning, and monitoring/testing on realistic workloads.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish insert-heavy, update-heavy, delete-heavy, and mixed-churn workloads.
- Understand why heavy INSERTs do not automatically mean high dead tuples.
- Explain insert-triggered autovacuum and the role of the visibility map and freezing.
- Compute vacuum/analyze thresholds from base thresholds and scale factors.
- Identify HOT updates, index churn, TOAST, and fillfactor effects.
- Tune autovacuum per table based on row count, write rate, and I/O budget.
- Understand the effects of vacuum workers, cost delay, work memory, and WAL.
- Locate long transactions, replication slots, and standby feedback pinning the cleanup horizon.
- Apply partitioning/retention for time-series or expiring data.
- Monitor statistics, vacuum progress, lock waits, and XID age.
- Build an insert-heavy/high-churn lab and interpret results.
- Plan maintenance without exhausting connection pools or disk space.

## 2. Classifying Workloads Before Tuning

Not every large table has the same problem. Classify by how data is written and row lifecycle.

| Workload | Characteristics | Primary Pressure |
|---|---|---|
| Insert-heavy, append-only | Continuous INSERTs, minimal UPDATE/DELETE | Visibility map, freezing, indexes, WAL, disk growth |
| Update-heavy | Single rows modified repeatedly | Dead tuples, HOT eligibility, index churn |
| Delete-heavy | Bulk or continuous deletions | Dead tuples, cleanup, index bloat, free space |
| Mixed churn | High INSERT, UPDATE, and DELETE | Vacuum throughput, indexes, WAL, I/O |
| Bulk load | Large periodic batch loads | Analyze, index builds, checkpoints, autovacuum overlap |
| Time-series | Daily/monthly data with retention | Partition lifecycle, per-partition vacuuming |
| Mostly-static | Rarely modified after creation | Freezing, visibility map, stats when changes occur |

### 2.1. Insert-Heavy Does Not Automatically Mean Many Dead Tuples

A new INSERT creates a live tuple version. Without UPDATE/DELETEs, it does not create an old version needing cleanup. However, new pages are not yet marked all-visible, and tuples still need freezing over time.

### 2.2. Update-Heavy Creates Many Versions

An UPDATE normally creates a new version and turns the old version dead once no snapshot needs it. Updating the same row hundreds of times can generate substantial cleanup work even when logical row count stays flat.

### 2.3. Delete-Heavy Creates Cleanup Backlogs

DELETE marks old tuples no longer current. VACUUM must determine when those versions are no longer needed by any snapshot before reclaiming space.

### 2.4. Bulk Loads Differ from Continuous Writes

A batch INSERT of hundreds of millions of rows over a short span may need post-load ANALYZE and dedicated index/constraint strategies. Continuous INSERTs require autovacuum running steadily over time.

### 2.5. Measure Write Rate Over Time Windows

A snapshot showing `n_tup_ins=10000000` tells you nothing about rate without an observation window. Compare delta counters between two timestamps and note the workload window.

## 3. Why Do Insert-Heavy Tables Still Need VACUUM?

VACUUM does more than clean dead tuples. On append-only tables, it maintains the visibility map and freezes transaction IDs.

### 3.1. Visibility Map and Index-Only Scans

PostgreSQL marks heap pages as all-visible once every tuple on the page is visible to all current transactions. Index-only scans can skip reading the heap for pages marked appropriately.

### 3.2. INSERT Leaves New Pages Non-All-Visible

When rows are added, pages holding new data cannot default to all-visible. Even if a table is purely insert-only with zero deletes, it needs vacuuming to confirm page visibility once snapshot conditions allow.

### 3.3. Freezing XIDs

Tuples with aging transaction IDs must be frozen to protect against XID wraparound. Append-only tables still accumulate aging tuples even without dead rows.

### 3.4. Insert-Triggered Autovacuum

PostgreSQL provides dedicated parameters for vacuum triggered by INSERTs:

- `autovacuum_vacuum_insert_threshold`
- `autovacuum_vacuum_insert_scale_factor`

These trigger vacuuming even before a dead-tuple threshold is met, addressing visibility and freezing needs on insert-heavy tables.

### 3.5. Do Not Confuse Insert-Triggered Vacuum with Dead-Tuple Cleanup

An insert-triggered vacuum may not drop `n_dead_tup` noticeably if the table had few dead tuples to begin with. It is still valuable for the visibility map and freezing.

## 4. Autovacuum Thresholds for INSERT

The insert-triggered vacuum threshold follows the general form:

~~~text
insert vacuum threshold =
    autovacuum_vacuum_insert_threshold
    + autovacuum_vacuum_insert_scale_factor
      * estimated_table_tuples
~~~

### 4.1. Threshold Is the Fixed Component

`autovacuum_vacuum_insert_threshold` sets the minimum inserted tuples before insert-count vacuum triggers. `-1` can disable insert-triggered vacuum; check your version's docs and policy before changing it.

### 4.2. Scale Factor Scales with Table Size

`autovacuum_vacuum_insert_scale_factor` multiplies the table's estimated tuples. A huge table may require enormous numbers of inserts before hitting the threshold if the scale factor is too high.

### 4.3. Threshold Calculation Example

Suppose a table has roughly 10 million rows, insert threshold 1,000, and insert scale factor 0.1:

~~~text
threshold = 1,000 + 0.1 * 10,000,000
          = 1,001,000 inserts
~~~

This is an illustrative calculation. Actual row counts and counters are estimated/tracked by PostgreSQL; inspect settings active on your server.

### 4.4. Large Tables May Wait Too Long

On a table with hundreds of millions of rows, a 0.2 scale factor yields an enormous threshold, making insert-triggered vacuum run less often than desired.

### 4.5. Do Not Lower Scale Factors by Guesswork

Vacuuming earlier increases I/O and worker load. Pick thresholds based on insert rate, fraction of pages needing vacuum, index-only scan needs, freeze age, and storage headroom.

## 5. Autovacuum Thresholds for UPDATE/DELETE

Dead-tuple vacuum normally uses:

~~~text
vacuum threshold =
    autovacuum_vacuum_threshold
    + autovacuum_vacuum_scale_factor
      * estimated_table_tuples
~~~

### 5.1. Dead Tuple Estimate

`n_dead_tup` in `pg_stat_user_tables` is an estimate, not an exact instantaneous physical count.

### 5.2. Small Tables vs. Large Tables

On small tables, the fixed threshold dominates. On large tables, the scale factor usually dominates the total threshold.

### 5.3. Update/Delete Bursts

A large update/delete spike can grow dead tuples faster than autovacuum clears them. Check whether vacuum is delayed by worker slots, I/O, locks, or the `xmin` horizon.

### 5.4. Do Not Collapse All Counters into One Metric

Insert-triggered vacuum and dead-tuple-triggered vacuum serve different needs. Track `n_ins_since_vacuum`, `n_dead_tup`, and `n_mod_since_analyze` separately where supported by your version.

### 5.5. Thresholds Are Only Triggers

Crossing a threshold does not guarantee a worker starts instantly. The launcher must inspect the table, a worker slot must be free, locks must be acquired, and resources must allow it.

## 6. ANALYZE Also Matters in Heavy Workloads

Vacuum cleanup and ANALYZE statistics are two distinct tasks.

~~~text
INSERT / UPDATE / DELETE
          |
          +----> vacuum thresholds
          |         |
          |         v
          |      VACUUM
          |      cleanup / visibility / freeze
          |
          +----> analyze thresholds
                    |
                    v
                 ANALYZE
                 planner statistics
~~~

### 6.1. Insert-Heavy Shifts Data Distributions

If new data clusters into a new range of values or a new partition, stale statistics fail to represent the current distribution. The query planner may choose poor plans.

### 6.2. n_mod_since_analyze

`n_mod_since_analyze` tracks modified tuples since the last analyze in versions providing this counter.

### 6.3. Analyze Threshold

`autovacuum_analyze_threshold` and `autovacuum_analyze_scale_factor` govern analyze triggers. They are independent of vacuum thresholds.

### 6.4. Consider Post-Load ANALYZE After Bulk Loads

After a large batch load, the planner may need fresh statistics immediately before autovacuum's turn arrives. Targeted post-load ANALYZE helps keep query plans accurate.

### 6.5. Extended Statistics

When queries filter on correlated columns, extended statistics (`CREATE STATISTICS`) can help. VACUUM does not create these statistics objects automatically.

## 7. Update-Heavy Tables and HOT Updates

HOT (*Heap-Only Tuple*) is an optimization letting certain UPDATEs avoid creating new index entries.

### 7.1. General Conditions

A HOT update can occur when updated columns do not belong to indexes requiring updates and sufficient free space exists on the same heap page. Exact details depend on index types and PostgreSQL version.

### 7.2. Why Does HOT Reduce Churn?

When a HOT update succeeds, PostgreSQL chains tuple versions within the heap page without inserting new index entries for each update. This cuts index write amplification and index cleanup work.

### 7.3. Indexes on Frequently Updated Columns

If `status`, `last_seen`, or counters are indexed, updating those columns disqualifies HOT and increases index churn.

### 7.4. Do Not Drop Indexes Just to Force HOT

Indexes may be vital for queries or constraints. Measure query workloads, index usage, and update patterns before altering schemas.

### 7.5. Tracking the HOT Ratio

`n_tup_hot_upd` and `n_tup_upd` in `pg_stat_user_tables` let you estimate the HOT update ratio:

~~~text
HOT ratio = n_tup_hot_upd / n_tup_upd
~~~

Use delta counters over a time window when measuring a workload window; cumulative lifetime counters since stats reset can mislead.

## 8. Fillfactor for Frequently Updated Tables

Fillfactor sets the target page fill percentage when creating or rewriting a relation. Leaving free space can improve HOT update odds.

~~~sql
CREATE TABLE app.sessions (
    session_id UUID PRIMARY KEY,
    status TEXT NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL
) WITH (fillfactor = 80);
~~~

### 8.1. Lower Fillfactor Leaves Headroom

For example, fillfactor 80 aims to leave room on pages during appropriate page creation/rewrite operations. It is not a guarantee that every page always stays at exactly 20% free space.

### 8.2. Helpful for Update-Heavy Patterns

If UPDATEs modify non-indexed columns and the new version fits on the same page, headroom enables HOT updates.

### 8.3. Not Necessarily Beneficial for Append-Only Tables

An insert-only table rarely benefits from low fillfactor; lower page density increases storage footprint and I/O for the same row count.

### 8.4. ALTER TABLE SET fillfactor Does Not Rewrite Existing Data

Changing the storage parameter affects subsequent page writes/rewrites per PostgreSQL semantics; applying it fully to existing pages requires an intentional rewrite/maintenance operation.

### 8.5. Measure with Workloads

Compare HOT ratio, index writes, heap size, query latency, and disk footprint in staging before applying to production.

## 9. Indexes Multiply Churn Cost

Every index adds overhead to INSERT, UPDATE, and DELETE.

### 9.1. INSERT Must Update Indexes

Each new row normally requires entries in all relevant indexes. Tables with many indexes suffer heavy write amplification.

### 9.2. Updating Indexed Columns Creates Index Churn

When indexed columns change, PostgreSQL must update index entries, increasing dead index entries and vacuum cleanup work.

### 9.3. Index-Only Scans Need the Visibility Map

Even when an index covers all SELECT columns, PostgreSQL needs heap pages marked all-visible to skip heap visibility checks. VACUUM maintains the visibility map.

### 9.4. Do Not Drop Indexes Based on One Short Stats Snapshot

An index may support constraints, infrequent reports, or maintenance jobs. Check `pg_stat_user_indexes`, query plans, and sufficiently long workload windows.

### 9.5. Partial and Covering Indexes

These can shrink index footprints when predicates and queries fit. Still, every added index raises write and maintenance overhead.

## 10. TOAST and Rows with Large Payloads

Large values such as JSONB, TEXT, and BYTEA may be stored out-of-line in TOAST.

### 10.1. Updating Large Payloads Costs More Than Small Columns

If every UPDATE replaces a large JSONB document, it can write many new TOAST chunks and leave old chunks needing cleanup.

### 10.2. HOT Eligibility Can Still Apply

Indexed columns and tuple layout govern HOT. Updating unindexed payload columns can still qualify for HOT in some cases, yet TOAST write volume remains.

### 10.3. Do Not Store Full Event Histories in One Mutable Row When Auditing

Splitting an append-only event table from a smaller current-state table separates immutable history from hot mutable state. Choose according to query and consistency requirements.

### 10.4. Measure Total Relation Size

`pg_total_relation_size` includes indexes and TOAST, whereas `pg_relation_size` measures only the main relation. Use the right metric when investigating.

### 10.5. Compression Does Not Replace Vacuum

TOAST compression shrinks value storage, but does not eliminate old tuple versions created by UPDATE/DELETE.

## 11. Insert-Heavy Workloads, WAL, and Checkpoint Pressure

Heavy INSERTs generate WAL and dirty data pages. VACUUM also generates WAL for metadata and cleanup changes.

### 11.1. VACUUM Does Not Clean Up WAL

WAL retention, archiving, and replication have their own mechanisms. VACUUM is not a command to purge old WAL files.

### 11.2. Many Indexes Increase WAL

Each index must log entries for new rows. Over-indexed schemas amplify WAL volume and disk writes.

### 11.3. Checkpoints and Storage Throughput

Bulk inserts dirty many pages; checkpoint tuning and storage throughput strongly affect write latency. Do not blame all high disk I/O on VACUUM.

### 11.4. WAL Archive Lag

If the archiver or remote storage falls behind, WAL accumulates. Monitor `pg_stat_archiver`, archive failures, and filesystem capacity.

### 11.5. Replication Lag

High write rates can cause standby replay lag. Lag affects backup/failover RPO and, when feedback/slots hold `xmin`, impacts the vacuum horizon as well.

## 12. Partitioning for Insert-Heavy and Time-Series Tables

For time-ordered data, partitioning scopes maintenance and retention to discrete segments.

~~~text
events (partitioned parent)
   |
   +-- events_2026_10
   +-- events_2026_11
   +-- events_2026_12
~~~

### 12.1. Inserts Route to Partitions

Choose a partition key aligned with data and queries. Partition pruning lets queries read only relevant partitions when predicates match.

### 12.2. Vacuuming Per Leaf Partition

Each partition is an independent relation. Churn and autovacuum activity differ between the hot active partition (insert-heavy) and older partitions (read-mostly).

### 12.3. Retention via Detach/Drop

When data expires, detaching/dropping a partition can be far more efficient than deleting millions of rows. Still, account for DDL locks, foreign key dependencies, indexes, and archival policies.

### 12.4. New Partitions May Lack Current Statistics

After creating/loading a new partition, monitor ANALYZE and planner behavior. Parent-level statistics may need manual refreshing depending on PostgreSQL version.

### 12.5. Avoid Too Many Tiny Partitions

Excessive partition counts inflate planning and catalog overhead, maintenance coordination, and operational complexity. Size granularity to match retention, queries, and write rates.

## 13. Bulk Loads: Before, During, and After Import

A large data load creates a very different workload profile from steady-state traffic.

### 13.1. Before Load

- Estimate row, index, and WAL space requirements.
- Verify disk headroom and replication/archiver capacity.
- Decide whether loading into a staging table works.
- Choose suitable COPY/batch sizes and transaction boundaries.
- Plan index/constraint creation order per consistency and downtime needs.

### 13.2. During Load

- Monitor insert rate, WAL generation, checkpoints, and replication lag.
- Never disable autovacuum cluster-wide just to go faster.
- Bound concurrency to avoid saturating disk/CPU.
- Watch locks, transaction age, and error rates.

### 13.3. After Load

- Run ANALYZE when needed so the planner sees the new distribution.
- Verify identity/sequence values if explicit IDs were loaded.
- Check vacuum insert thresholds and visibility map coverage.
- Verify indexes, constraints, and row counts.
- Watch autovacuum afterward to ensure no backlog remains.

### 13.4. Create Indexes Before or After Load?

When bulk loading into a fresh table, creating indexes afterward can be faster than maintaining index entries per row. Still, unique constraints, availability, and downtime limits may dictate otherwise.

### 13.5. Do Not Wrap the Entire Load in an Endless Transaction

Overly long transactions hold snapshots/locks, inflate rollback footprints, and can hinder cleanup. Split into batches aligned with business semantics and restartability.

## 14. Tuning Autovacuum by Table Type

| Table Type | Tuning Focus |
|---|---|
| Append-only log | Insert thresholds, freezing, visibility, partition retention |
| Current-state table | Dead tuple thresholds, HOT, fillfactor, index churn |
| Session/presence | UPDATE churn, TTL cleanup, short transactions |
| Audit/event | Insert rate, indexes, WAL, partitioning |
| Large JSON document | TOAST, update pattern, payload size |
| Reference table | Freezing/ANALYZE when changed, low vacuum churn |
| Bulk staging | Post-load analyze, clean/drop staging per lifecycle |

### 14.1. Per-Table Storage Parameters for INSERT

~~~sql
ALTER TABLE telemetry.events
SET (
    autovacuum_vacuum_insert_threshold = 5000,
    autovacuum_vacuum_insert_scale_factor = 0.03
);
~~~

Numbers are illustrative only. Lowering thresholds triggers insert-triggered vacuum sooner; verify I/O and worker capacity.

### 14.2. Update-Heavy Tables

~~~sql
ALTER TABLE app.sessions
SET (
    autovacuum_vacuum_threshold = 500,
    autovacuum_vacuum_scale_factor = 0.01
);
~~~

A smaller scale factor reduces dead tuple backlogs, at the cost of more frequent vacuums.

### 14.3. Tables Needing Frequent Analyze

~~~sql
ALTER TABLE app.orders
SET (
    autovacuum_analyze_threshold = 500,
    autovacuum_analyze_scale_factor = 0.01
);
~~~

Fits when planner statistics must refresh quickly after changes. Weigh analyze cost against plan stability.

### 14.4. Viewing Current reloptions

~~~sql
SELECT
    n.nspname,
    c.relname,
    c.reloptions
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname IN ('telemetry', 'app')
  AND c.relkind IN ('r', 'm', 'p')
ORDER BY 1, 2;
~~~

### 14.5. Resetting Specific Options

~~~sql
ALTER TABLE telemetry.events
RESET (
    autovacuum_vacuum_insert_threshold,
    autovacuum_vacuum_insert_scale_factor
);
~~~

Reset only the options that should revert to server defaults. Avoid wiping unrelated `reloptions`.

## 15. Vacuum Cost, Workers, and I/O Budget

Autovacuum needs resources to read pages, collect dead tuple IDs, and clean indexes. Tuning balances vacuum speed against foreground workloads.

### 15.1. autovacuum_max_workers

Adding worker slots handles more tables concurrently, while increasing aggregate CPU, RAM, and I/O consumption.

### 15.2. autovacuum_naptime

Controls how long the launcher waits between checks. Lowering naptime will not make tables vacuum immediately if workers are busy or thresholds are not met.

### 15.3. Vacuum Cost Limit/Delay

Cost-based throttling paces vacuum activity to protect workloads. Throttling too hard can cause vacuum to fall behind churn.

### 15.4. autovacuum_work_mem

Working memory affects how many dead tuple identifiers fit before index cleanup passes repeat. Budget total memory across concurrent workers.

### 15.5. Per-Worker and Global Resource Budgets

Never raise worker count without inspecting disk throughput, memory, IOPS, WAL, CPU, and latency. Evaluate tuning across the entire cluster.

## 16. Transaction Horizons: The Frequently Missed Blocker

Even when thresholds are crossed and workers are free, VACUUM cannot reclaim versions still needed by an old snapshot.

### 16.1. Long-Running Transactions

A long-open transaction can hold an old `backend_xmin`, keeping dead tuples pinned.

### 16.2. Idle in Transaction

A connection that ran `BEGIN` and sits idle can still pin a snapshot. This is a common application lifecycle bug.

### 16.3. Replication Slot xmin

Logical replication slots can retain `xmin`/`catalog_xmin`, preventing vacuum from cleaning certain tuple or catalog versions.

### 16.4. Hot Standby Feedback

Standby feedback prevents cleanup from canceling standby queries, at the trade-off of holding versions longer on the primary.

### 16.5. You Cannot Tune Thresholds Past a Horizon

Lowering scale factors or adding workers cannot delete tuples PostgreSQL must keep for visibility semantics. Find the root horizon blocker first.

## 17. Monitoring: Measuring Rate of Change

`pg_stat_user_tables` exposes helpful counters:

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_tup_hot_upd,
    n_mod_since_analyze,
    n_ins_since_vacuum,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze,
    autovacuum_count
FROM pg_stat_user_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n_tup_ins DESC
LIMIT 30;
~~~

Some columns depend on PostgreSQL version. Verify the view schema on your real server before deploying monitoring queries.

### 17.1. Cumulative Counters

Counters can reset on stats resets, restarts, upgrades, or config changes. Capture two snapshots separated by a known interval to calculate deltas.

### 17.2. Insert Rate

~~~text
insert rate = delta(n_tup_ins) / elapsed_seconds
~~~

### 17.3. Update/Delete Rate

~~~text
change rate = (delta(n_tup_upd) + delta(n_tup_del))
              / elapsed_seconds
~~~

These are operation counts, not necessarily the count of distinct logical rows touched.

### 17.4. HOT Ratio

~~~text
HOT ratio = delta(n_tup_hot_upd) / delta(n_tup_upd)
~~~

When update count is zero, the ratio is undefined; avoid division by zero.

### 17.5. Dead Tuple Ratio Is Only a Signal

You can inspect `n_dead_tup / (n_live_tup + n_dead_tup)` as a rough indicator, never as an exact physical bloat measurement.

## 18. Monitoring: Sizes and Free Space

~~~sql
SELECT
    s.schemaname,
    s.relname,
    s.n_live_tup,
    s.n_dead_tup,
    pg_size_pretty(
        pg_relation_size(
            format('%I.%I', s.schemaname, s.relname)::regclass
        )
    ) AS heap_size,
    pg_size_pretty(
        pg_indexes_size(
            format('%I.%I', s.schemaname, s.relname)::regclass
        )
    ) AS indexes_size,
    pg_size_pretty(
        pg_total_relation_size(
            format('%I.%I', s.schemaname, s.relname)::regclass
        )
    ) AS total_size
FROM pg_stat_user_tables AS s
ORDER BY pg_total_relation_size(
    format('%I.%I', s.schemaname, s.relname)::regclass
) DESC
LIMIT 30;
~~~

### 18.1. Heap and Indexes

An insert-heavy table can grow index sizes faster than expected if it carries many indexes.

### 18.2. TOAST

For large payloads, total size can be dominated by TOAST relations; always check total relation size.

### 18.3. Free Space Map Is Not Pure Bloat

Free pages can be reused. Do not assume every bit of free space must be compacted away.

### 18.4. pgstattuple

The `pgstattuple` extension offers deeper inspection of live/dead/free space, at the cost of scanning and extension/privilege requirements. Use it purposefully.

### 18.5. Track Over Time

Daily size charts alongside insert/update/delete rates and autovacuum history are far more revealing than a single snapshot.

## 19. Monitoring: Autovacuum Workers and Progress

~~~sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    left(query, 160) AS query_sample
FROM pg_stat_activity
WHERE query LIKE 'autovacuum:%'
   OR backend_type = 'autovacuum worker'
ORDER BY query_start;
~~~

### 19.1. pg_stat_progress_vacuum

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS relation,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed,
    index_vacuum_count
FROM pg_stat_progress_vacuum;
~~~

### 19.2. Phases and Progress

VACUUM moves through heap scan, index vacuum, heap vacuum, index cleanup, and final cleanup. A long-running phase does not automatically mean the worker is hung.

### 19.3. Lock Waits

Combine `pg_locks`, `pg_stat_activity`, and `pg_blocking_pids(pid)` to locate blockers. Workers can wait on locks held by DDL or other maintenance.

### 19.4. Progress Views Are Not History

Progress views show only currently running operations; store logs and scraped metrics if you need historical trends.

### 19.5. Monitoring Privileges

Some columns or query texts can be restricted by role and version. Use an appropriate monitoring role rather than granting superuser just so dashboards can read everything.

## 20. Monitoring: XID Age and Replication Horizons

XID age per database:

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
~~~

Replication slots:

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    xmin,
    catalog_xmin,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
~~~

### 20.1. Alert on XID Age

Do not monitor only dead tuples; append-only tables with low dead tuples still require freezing.

### 20.2. Inactive Slots Are Not Automatically Harmless

An inactive slot can retain WAL/`xmin` indefinitely if its consumer crashed or stopped.

### 20.3. WAL Disk vs. Tuple Horizon

`restart_lsn` governs WAL retention; `xmin`/`catalog_xmin` govern the vacuum cleanup horizon. Track each independently.

### 20.4. Standby Lag

Check replication status, lag, and feedback config. A lagging standby can impact both WAL retention and the vacuum horizon.

### 20.5. Never Drop a Slot to Fix Bloat Without Owner Confirmation

Dropping a slot can break a replication consumer or logical decoding pipeline. Have a rebuild/resnapshot plan ready.

## 21. Avoiding Practices That Starve Autovacuum

### 21.1. Overly Long Transactions

Batch work and commit along business boundaries. Never hold transactions open while waiting for users or external API calls.

### 21.2. Giant Bulk Update Transactions

Batching updates bounds transaction lifetimes and rollback footprints, provided idempotency, ordering, and consistency are designed properly.

### 21.3. Competing Workers

Raising worker count when I/O is already saturated slows foreground queries without improving vacuum throughput.

### 21.4. Too Many Indexes

Audit duplicate or unused indexes with evidence. Every index adds write and cleanup costs.

### 21.5. Row-by-Row Delete Retention

For time-series tables, consider partition detach/drop to avoid creating millions of dead tuples if business retention and dependencies allow.

## 22. Designing Insert-Heavy Tables

### 22.1. Primary Keys

Pick keys suited to queries, uniqueness, and write patterns. Sequential keys can create B-tree right-edge hotspots at high scale; random/UUID keys trade off index locality and size.

### 22.2. Keep Only Essential Indexes

Every index carries write overhead. Index for real queries and constraints rather than indexing every column just in case.

### 22.3. Partition Keys

If queried and retained by time, time-range partitioning aids pruning and lifecycle management. Choose a stable partition key matching query predicates.

### 22.4. Append-Only Event Models

When recording immutable events, append-only tables avoid update churn. Materialize current state separately if needed.

### 22.5. Idempotency and Deduplication

Retrying ingestion pipelines can create duplicates without unique/idempotency keys. Use constraints and conflict handling intentionally instead of constantly deleting duplicates as normal ingestion flow.

## 23. Designing Update-Heavy Tables

### 23.1. Separate Frequently Mutated Data

If a wide row holds immutable payload columns plus a few rapidly changing status columns, consider splitting mutable state into a smaller table to cut tuple/TOAST churn.

### 23.2. Avoid Indexing Every Mutable Status Column

Indexes on frequently updated columns block HOT updates. Index them only if workloads truly require them.

### 23.3. Test Lower Fillfactor

A lower fillfactor on update-heavy tables can help HOT if pages keep headroom and updated columns are unindexed. Measure gains rather than applying globally.

### 23.4. Suppress Unnecessary No-Op Updates

Skip updating a row when new values match existing values if the application can determine that safely. Avoid creating pointless tuple versions and WAL.

### 23.5. Avoid Updating `last_seen` on Every Request If Unneeded

Batch or debounce telemetry heartbeats or offload high-frequency heartbeats if semantics permit. Cutting update frequency drastically cuts bloat.

## 24. Designing Delete-Heavy and Retention Tables

### 24.1. Batch Deletions

When rows must be deleted, use bounded batches and commit regularly instead of one massive transaction.

### 24.2. Vacuum After Delete Bursts

After a large delete wave, watch autovacuum and run manual VACUUM/ANALYZE if workload demands it, without defaulting to FULL.

### 24.3. Partition Drops

For expired historical partitions, `DROP`/`DETACH PARTITION` removes whole relations faster than row-by-row deletion.

### 24.4. Foreign Keys and Cascades

Deleting a parent row can trigger large cascades into child tables. Account for churn and locks across the entire dependency graph.

### 24.5. Audit/History

If deletion history must be preserved, write an audit or event log in a dedicated schema; VACUUM does not substitute for business retention rules.

## 25. Autovacuum and Bulk Loads into New Tables

A huge bulk load into a new table behaves differently from a long-running steady-state table.

### 25.1. Load into Staging Tables

Where feasible, load into a staging table and validate before swapping or attaching into production structures.

### 25.2. Build Indexes After Loading

In some scenarios, building indexes after `COPY` finishes is faster than updating index entries per row during load. Weigh unique constraints, availability, and write windows.

### 25.3. ANALYZE After Loading

Right after a large load, run ANALYZE when the planner needs updated statistics immediately.

### 25.4. Visibility and Freezing

A post-load VACUUM can establish visibility and freeze metadata, though weigh insert-triggered autovacuum and XID age instead of defaulting to FULL.

### 25.5. Verify Identity/Sequence State

If explicit IDs were loaded into an identity column, verify sequence/identity state so subsequent inserts do not hit duplicate key errors.

## 26. Safely Changing Configuration Parameters

Inspect settings and sources:

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    context,
    pending_restart
FROM pg_settings
WHERE name LIKE 'autovacuum%'
   OR name LIKE 'vacuum_%'
ORDER BY name;
~~~

### 26.1. SHOW Shows Only the Current Value

`SHOW` displays the active value, whereas `pg_settings` also reveals `source` and `context` so you know where it came from and whether a restart is required.

### 26.2. Reload vs. Restart

Parameters have different contexts; inspect `context` and `pending_restart`. Never assume `ALTER SYSTEM` always takes effect instantly.

### 26.3. ALTER SYSTEM

`ALTER SYSTEM` writes to `postgresql.auto.conf` at the server level. Enforce change management and appropriate privileges.

### 26.4. Per-Table reloptions

Prefer per-table tuning when only a subset of tables has special patterns. This avoids altering behavior across unrelated databases and tables.

### 26.5. Record Baselines and Rollbacks

Before tuning, save old settings/`reloptions`, baseline metrics, targets, and rollback criteria. Avoid changing many parameters at once so you can isolate effects.

## 27. Operational Metrics That Deserve Alerts

| Metric | Why It Matters |
|---|---|
| Insert/update/delete rate | Quantifies write churn |
| `n_dead_tup` estimate | Signals cleanup backlog |
| `n_ins_since_vacuum` | Insert-triggered vacuum activity |
| `n_mod_since_analyze` | Statistics may be stale |
| Last autovacuum / duration | Confirms maintenance is running |
| XID age | Prevents wraparound |
| HOT update ratio | Measures UPDATE index churn |
| Heap/index/TOAST sizes | Tracks bloat and storage growth |
| Autovacuum worker saturation | Shows capacity/backlog |
| Vacuum progress/phase | Shows current job stage |
| Lock waits/blockers | Maintenance blocked |
| WAL generation/archive lag | Archive and replication health |
| Replication lag/slot `xmin` | Horizon and recovery risks |
| Disk free/IOPS/latency | Storage headroom and bottlenecks |
| Query latency | Application impact |

### 27.1. Alert on Trends

A one-minute spike may just be a legitimate batch job. Alerts should incorporate thresholds, duration, rate of change, and context.

### 27.2. Do Not Alert Only on n_dead_tup

Insert-heavy tables can need vacuuming for inserts/freezing even with low dead tuple counts. Monitor XID age and insert counters separately.

### 27.3. Do Not Alert Only on Free Disk Space

The filesystem can still have plenty of space while vacuum is badly behind and XID age climbs. Both alert classes protect against different failures.

## 28. Ordered Diagnosis for Autovacuum Lag

When a table changes rapidly and `n_dead_tup` climbs:

1. Confirm write rate and churn type (INSERT/UPDATE/DELETE).
2. Check `last_autovacuum`, vacuum counters, and progress.
3. Check dead tuple estimates, relation size, and index size.
4. Check worker slots, cost delay, memory, and I/O latency.
5. Check long transactions, `idle in transaction`, and prepared transactions.
6. Check replication slots, `xmin`/`catalog_xmin`, and standby feedback.
7. Check lock waits and DDL/maintenance blockers.
8. Inspect the table's exact threshold and scale factor.
9. Adjust one targeted parameter and monitor.
10. Confirm foreground workloads, vacuum throughput, and XID age all improve.

### 28.1. Worker Never Appears

Thresholds may not be crossed yet, the launcher may not have reached its check cycle, workers may be busy, the table may be ineligible, or stats may not have flushed.

### 28.2. Worker Runs Yet Reclaims Little

A snapshot horizon may be pinning tuples, or the dead tuple estimate may be inaccurate at observation time.

### 28.3. Worker Runs Slowly

Inspect I/O, cost delay, index cleanup, relation size, and contention with query workloads.

### 28.4. Bloat Keeps Growing

Inspect update patterns, indexes, fillfactor, TOAST, and write rates; a single vacuum cannot outrun a workload generating dead tuples faster than cleanup capacity.

### 28.5. XID Age Climbs

Prioritize inspecting freeze progress, oldest relations/databases, slots, and transaction horizons. Do not merely add dead-tuple workers.

## 29. Lab: Creating an Insert-Heavy Table

**Practice only in a test database.** Create schema and table:

~~~sql
CREATE SCHEMA vacuum_workload_lab;

CREATE TABLE vacuum_workload_lab.events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL
);
~~~

### 29.1. Load Many Rows

~~~sql
INSERT INTO vacuum_workload_lab.events (
    tenant_id, event_time, event_type, payload
)
SELECT
    (g % 1000)::integer,
    clock_timestamp(),
    CASE WHEN g % 4 = 0 THEN 'click' ELSE 'view' END,
    repeat('x', 200)
FROM generate_series(1, 200000) AS g;
~~~

### 29.2. Check Counters

~~~sql
SELECT
    relname,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_dead_tup,
    n_ins_since_vacuum,
    last_autovacuum
FROM pg_stat_user_tables
WHERE schemaname = 'vacuum_workload_lab';
~~~

If `n_ins_since_vacuum` does not exist in your version, omit that column and use the available counters.

### 29.3. Observe Visibility Behavior Indirectly

Run `VACUUM (VERBOSE, ANALYZE)` in the lab and examine output/plans. The visibility map can be inspected more deeply using suitable extensions/tools if installed.

### 29.4. Do Not Expect High Dead Tuples

Because the new table is mostly INSERTs, dead tuples remain low. This lab illustrates why insert-triggered vacuum differs from dead-tuple vacuum.

### 29.5. Measure Sizes

~~~sql
SELECT
    pg_size_pretty(pg_relation_size('vacuum_workload_lab.events')) AS heap,
    pg_size_pretty(pg_indexes_size('vacuum_workload_lab.events')) AS indexes,
    pg_size_pretty(pg_total_relation_size('vacuum_workload_lab.events')) AS total;
~~~

## 30. Lab: Generating Update/Delete Churn

~~~sql
UPDATE vacuum_workload_lab.events
SET payload = repeat('y', 220)
WHERE event_id % 3 = 0;

UPDATE vacuum_workload_lab.events
SET event_type = 'updated'
WHERE event_id % 10 = 0;

DELETE FROM vacuum_workload_lab.events
WHERE event_id % 7 = 0;
~~~

### 30.1. Check Stats

~~~sql
SELECT
    n_live_tup,
    n_dead_tup,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_tup_hot_upd
FROM pg_stat_user_tables
WHERE schemaname = 'vacuum_workload_lab'
  AND relname = 'events';
~~~

### 30.2. Create an Index to Compare Churn

~~~sql
CREATE INDEX events_type_idx
ON vacuum_workload_lab.events(event_type);
~~~

Then update the indexed column in the lab and observe HOT ratio and sizes. Adding an index can lower HOT eligibility when updated columns belong to an index.

### 30.3. VACUUM and ANALYZE

~~~sql
VACUUM (VERBOSE, ANALYZE) vacuum_workload_lab.events;
~~~

### 30.4. Compare Before and After

Record dead tuple estimates, heap/index sizes, and query latencies. Autovacuum can fire between steps, so record timestamps.

### 30.5. Do Not Extrapolate Absolute Production Numbers from Lab Runs

Results vary by version, settings, page layout, indexes, storage, and workload concurrency.

## 31. Lab: Tuning Insert-Triggered Vacuum on the Test Table

Inspect current settings:

~~~sql
SHOW autovacuum_vacuum_insert_threshold;
SHOW autovacuum_vacuum_insert_scale_factor;
SHOW autovacuum_vacuum_threshold;
SHOW autovacuum_vacuum_scale_factor;
~~~

### 31.1. Apply Illustrative reloptions

~~~sql
ALTER TABLE vacuum_workload_lab.events
SET (
    autovacuum_vacuum_insert_threshold = 1000,
    autovacuum_vacuum_insert_scale_factor = 0.02
);
~~~

### 31.2. Verify reloptions

~~~sql
SELECT relname, reloptions
FROM pg_class
WHERE oid = 'vacuum_workload_lab.events'::regclass;
~~~

### 31.3. Generate More Inserts

~~~sql
INSERT INTO vacuum_workload_lab.events (
    tenant_id, event_time, event_type, payload
)
SELECT
    (g % 1000)::integer,
    clock_timestamp(),
    'batch',
    repeat('z', 200)
FROM generate_series(1, 50000) AS g;
~~~

### 31.4. Observe Autovacuum

Watch `last_autovacuum`, `n_ins_since_vacuum`, `pg_stat_activity`, and the progress view. Workers do not necessarily start the instant `INSERT` finishes.

### 31.5. Reset Options After Lab If Desired

~~~sql
ALTER TABLE vacuum_workload_lab.events
RESET (
    autovacuum_vacuum_insert_threshold,
    autovacuum_vacuum_insert_scale_factor
);
~~~

## 32. Lab: Comparing Fillfactor and HOT

Create two identically structured tables:

~~~sql
CREATE TABLE vacuum_workload_lab.sessions_default (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status TEXT NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL
);

CREATE TABLE vacuum_workload_lab.sessions_ff (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status TEXT NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL
) WITH (fillfactor = 75);
~~~

### 32.1. Load Initial Data

~~~sql
INSERT INTO vacuum_workload_lab.sessions_default(status, last_seen)
SELECT 'active', now()
FROM generate_series(1, 50000);

INSERT INTO vacuum_workload_lab.sessions_ff(status, last_seen)
SELECT 'active', now()
FROM generate_series(1, 50000);
~~~

### 32.2. Update an Unindexed Column

~~~sql
UPDATE vacuum_workload_lab.sessions_default
SET last_seen = now()
WHERE id % 2 = 0;

UPDATE vacuum_workload_lab.sessions_ff
SET last_seen = now()
WHERE id % 2 = 0;
~~~

### 32.3. Compare HOT Counters

~~~sql
SELECT
    relname,
    n_tup_upd,
    n_tup_hot_upd
FROM pg_stat_user_tables
WHERE schemaname = 'vacuum_workload_lab'
  AND relname IN ('sessions_default', 'sessions_ff');
~~~

Results depend on page layout, timing, autovacuum, and workload; lower fillfactor creates opportunity rather than a guarantee of HOT.

### 32.4. Add an Index on last_seen and Re-Test

~~~sql
CREATE INDEX sessions_default_seen_idx
ON vacuum_workload_lab.sessions_default(last_seen);

CREATE INDEX sessions_ff_seen_idx
ON vacuum_workload_lab.sessions_ff(last_seen);
~~~

Repeat the update and compare. Because the column is now indexed, updates may no longer be HOT eligible.

### 32.5. Clean Up the Lab

Once finished observing, you can drop the lab schema in your test database if the data is no longer needed:

~~~sql
DROP SCHEMA vacuum_workload_lab CASCADE;
~~~

Only run drop commands on labs you created yourself, never on schemas holding other data.

## 33. Troubleshooting: Symptoms and First Checks

| Symptom | Check First |
|---|---|
| Insert-heavy table never autovacuums | Insert threshold/scale factor, `last_autovacuum`, worker capacity |
| Dead tuples rise rapidly | Update/delete rate, horizon, locks, I/O |
| `n_dead_tup` low yet XID age rises | Freeze/autovacuum, old snapshots, relation age |
| Low HOT ratio | Index on updated column, fillfactor, page free space |
| Index size grows fast | Index count, updates to indexed columns, churn |
| Large TOAST size | Payload update size/frequency, data model |
| Vacuum workers continuously busy | Cost settings, I/O, table sizes, churn |
| Vacuum waiting on lock | DDL, long transactions, blockers |
| Replication slot holding `xmin` | Consumer lag/slot owner, retention |
| WAL disk full | Archive/replication lag, slot `restart_lsn` |
| Planner chooses bad plan after load | ANALYZE, statistics, extended stats |
| Query latency spikes during vacuum | I/O saturation, worker concurrency, cost delay |
| New partition queries are slow | ANALYZE parent/leaf, partition pruning |
| Delete retention causes bloat | Batch deletes, partition drop/detach |
| Table grows even while vacuum runs | Workload churn, indexes, free space, TOAST |

### 33.1. Do Not React with VACUUM FULL Before Diagnosing

FULL compacts once, but does not fix write patterns, transaction horizons, or autovacuum capacity. Bloat will return if the underlying cause stays.

### 33.2. Separate Heap Bloat from Index Bloat

Measure heap, indexes, and TOAST separately. A table with a stable heap and rapidly bloating indexes needs a different fix.

### 33.3. Distinguish Backlog from Normal Growth

An append-only table growing alongside row count is legitimate data growth, not bloat by itself.

### 33.4. Inspect WAL and Disk Separately

WAL accumulation is not dead-tuple bloat. Investigate the archiver/replication slots and filesystem separately.

## 34. Common Misconceptions

1. **"Insert-heavy tables don't need VACUUM because they don't DELETE."** False: insert-triggered vacuum maintains the visibility map and freezes tuples.
2. **"INSERT creates dead tuples like UPDATE."** False: INSERT creates a live version, not an obsolete old version.
3. **"Autovacuum only runs when `n_dead_tup` is high."** False: insert-triggered vacuum and anti-wraparound also trigger it.
4. **"Lower scale factor is always better."** False: excessive vacuuming raises I/O and contention.
5. **"Adding workers always makes vacuum faster."** False: extra workers can contend for CPU, RAM, and I/O.
6. **"Dead tuple estimate is an exact count."** False: it is a statistical estimate.
7. **"Standard VACUUM always shrinks files."** False: it mainly enables internal free space reuse.
8. **"VACUUM FULL is the optimal way to maintain insert-heavy tables."** False: FULL rewrites and takes an `ACCESS EXCLUSIVE` lock.
9. **"Append-only tables have no XID wraparound risk."** False: old tuples still need freezing.
10. **"HOT update happens whenever columns don't change."** False: indexed columns and page free space conditions must be met.
11. **"Low fillfactor is always good."** False: it increases storage footprint and I/O for insert-only workloads.
12. **"More indexes are always better."** False: every index adds write and maintenance cost.
13. **"Updating a small column never affects TOAST."** Not always true; check actual row version and payload behavior.
14. **"Setting a low `autovacuum_naptime` is enough."** False: workers, thresholds, horizons, and resources still govern execution.
15. **"Long transactions only cause locks."** False: they can pin snapshots and block vacuum cleanup.
16. **"Dropping a replication slot is a safe way to clean dead tuples."** False: it can break consumers with no simple rollback.
17. **"Replicas automatically protect against accidental deletes."** False: changes are replayed.
18. **"ANALYZE and VACUUM are the same thing."** False: statistics differ from cleanup and freezing.
19. **"No ANALYZE is needed after bulk loads."** False: the planner may rely on stale statistics.
20. **"Delete retention should always use DELETE."** False: partition lifecycle can be far better.
21. **"Cumulative `n_tup_ins` shows insert rate."** False: you need deltas and elapsed time.
22. **"One autovacuum lasts for the life of the table."** False: ongoing workloads keep changing data.
23. **"Full WAL stops VACUUM from running."** They are distinct issues, though both can share slot/replication causes.
24. **"VACUUM FULL fixes every bloat problem."** False: it does not fix root causes and can cause downtime.
25. **"No rows in the progress view means no vacuum exists."** False: it may have finished, not started yet, or be in another view.
26. **"VACUUM can run inside a transaction block."** False: VACUUM must run outside explicit transaction blocks.

## 35. Practice Exercises

### Exercise 1 — Insert-Only

An insert-only table has zero UPDATE/DELETEs. Why does it still need autovacuum?

**Hint:** Visibility map and XID freezing.

### Exercise 2 — Dead Tuples

Does a pure INSERT directly create dead tuple versions like an UPDATE?

**Answer:** No.

### Exercise 3 — Insert Threshold

Which parameter sets the minimum INSERT count for insert-triggered vacuum?

**Answer:** `autovacuum_vacuum_insert_threshold`.

### Exercise 4 — Insert Scale Factor

Which parameter scales the insert vacuum threshold with table size?

**Answer:** `autovacuum_vacuum_insert_scale_factor`.

### Exercise 5 — Formula

Write the general insert vacuum threshold formula.

**Hint:** Fixed threshold + scale factor × estimated table tuples.

### Exercise 6 — Large Tables

Why can a 0.2 scale factor create an overly high threshold on a multi-billion-row table?

**Hint:** The proportional component reaches hundreds of millions of inserts.

### Exercise 7 — Dead Tuple Threshold

Which scale factor parameter applies to UPDATE/DELETE-triggered vacuum?

**Answer:** `autovacuum_vacuum_scale_factor`.

### Exercise 8 — ANALYZE

Why might a bulk load need immediate ANALYZE?

**Hint:** The query planner needs statistics reflecting the new distribution.

### Exercise 9 — n_ins_since_vacuum

What does this counter track?

**Answer:** Number of tuples inserted since the last vacuum, when supported by the view/version.

### Exercise 10 — n_dead_tup

Is this an exact instantaneous count of dead tuples?

**Answer:** No.

### Exercise 11 — HOT

What does HOT stand for?

**Answer:** Heap-Only Tuple.

### Exercise 12 — HOT Eligibility

What are two key conditions for a HOT update to occur?

**Hint:** No indexed columns requiring updates are modified, and sufficient page space is available.

### Exercise 13 — Index Churn

Why can an index on a frequently updated `status` column raise maintenance cost?

**Hint:** Updates must maintain index entries, losing HOT eligibility.

### Exercise 14 — HOT Ratio

How do you estimate the HOT ratio?

**Answer:** Delta `n_tup_hot_upd / n_tup_upd`.

### Exercise 15 — Fillfactor

What does `fillfactor = 75` aim to do?

**Hint:** Reserve page free space to support HOT updates.

### Exercise 16 — Insert-Only Fillfactor

Why might low fillfactor be poorly suited for append-only tables?

**Hint:** Lowers page density, raising storage and I/O.

### Exercise 17 — TOAST

Why can frequently updating large JSONB payloads increase TOAST churn?

**Hint:** Creates new versions/chunks while leaving old chunks needing cleanup.

### Exercise 18 — WAL

Is VACUUM a command to clean up WAL files?

**Answer:** No.

### Exercise 19 — Partitioning

Why can dropping an old partition be more effective than deleting millions of rows?

**Hint:** Drops a relation at large scale, avoiding row-by-row churn.

### Exercise 20 — Partition Stats

Why check `ANALYZE` on a partitioned parent after loading?

**Hint:** The planner needs parent-level statistics per version behavior.

### Exercise 21 — Autovacuum Workers

What risk can raising max workers create?

**Hint:** CPU/RAM/I/O contention.

### Exercise 22 — Cost Delay

If cost delay is too high, what can happen?

**Answer:** Vacuum runs slowly and backlogs grow.

### Exercise 23 — Long Transaction

How can an `idle in transaction` session block vacuum?

**Hint:** Holds an old snapshot/`xmin` horizon.

### Exercise 24 — Replication Slots

Which columns in `pg_replication_slots` relate to the cleanup horizon?

**Answer:** `xmin`, `catalog_xmin`.

### Exercise 25 — WAL Retention

Which column relates to the WAL position a slot must retain?

**Answer:** `restart_lsn`.

### Exercise 26 — XID Age

Which catalog view shows database frozen XID age?

**Answer:** `pg_database` with `age(datfrozenxid)`.

### Exercise 27 — Monitoring

Which view contains `n_tup_ins`/`n_tup_upd`/`n_tup_del`?

**Answer:** `pg_stat_user_tables`.

### Exercise 28 — Progress

Which view shows currently running standard VACUUMs?

**Answer:** `pg_stat_progress_vacuum`.

### Exercise 29 — Locks

Which function identifies PIDs blocking a backend?

**Answer:** `pg_blocking_pids(pid)`.

### Exercise 30 — Insert Rate

What data is needed to calculate insert rate?

**Hint:** Delta `n_tup_ins` and elapsed time between two snapshots.

### Exercise 31 — Bloat

Does a table growing in size after a million new INSERTs prove bloat?

**Answer:** No; that can be legitimate data growth.

### Exercise 32 — Bulk Loads

Why should you not keep one giant bulk load transaction open indefinitely?

**Hint:** Snapshots/locks, rollback footprint, and cleanup horizon.

### Exercise 33 — Analyze Threshold

Which parameter tunes auto-analyze proportionally?

**Answer:** `autovacuum_analyze_scale_factor`.

### Exercise 34 — Append-Only Freeze

What risk can a very old append-only table face even with `n_dead_tup` near zero?

**Answer:** XID wraparound if tuples are not frozen on time.

### Exercise 35 — Choosing a Solution

A 500-million-row insert-only `events` table has low `n_dead_tup`, yet index-only scan queries perform poorly. What do you check?

**Hint:** Insert-triggered vacuum thresholds, visibility map, ANALYZE, indexes, and query plans.

### Exercise 36 — Choosing a Solution

A 20-million-row `sessions` table updates every row every minute, and `n_dead_tup` climbs continuously. What do you check?

**Hint:** Dead tuple threshold, HOT ratio, indexed columns, fillfactor, transaction horizon, and workers/I/O.

### Exercise 37 — Choosing a Solution

WAL disk grows rapidly while `n_dead_tup` is low. Should you run `VACUUM FULL`?

**Answer:** No; check archiver, replication slots, lag, and WAL retention.

### Exercise 38 — Choosing a Solution

A monthly `logs` table needs data purged after 18 months. Which strategy is worth considering?

**Hint:** Range partitioning and partition detach/drop per retention.

### Exercise 39 — Choosing a Solution

An autovacuum worker runs for a long time without cleaning more tuples. What do you investigate first?

**Hint:** `backend_xmin`, long transactions, replication slot `xmin`, locks, and progress phase.

### Exercise 40 — End-to-End Design

Design a strategy for a 1-billion-row/day append-only `events` table with 30-day retention, tenant/time queries, index-only scan requirements, and low RPO.

**Hint:** Time partitioning, indexes tailored to tenant/time queries, insert-triggered vacuum and freeze monitoring, ANALYZE, WAL/archive/replication capacity, partition-lifecycle retention, offsite backups and restore tests; measure I/O and visibility map coverage.

## 36. Operational Checklist for Insert-Heavy / High-Churn Tables

### 36.1. Understand the Workload

- [ ] Classified insert/update/delete rates?
- [ ] Measured rates via delta counters over time?
- [ ] Batch bursts or continuous writes?
- [ ] Large payloads / TOAST involved?
- [ ] Indexes on frequently modified columns?
- [ ] Time-based partitioning/retention applicable?

### 36.2. Autovacuum and ANALYZE

- [ ] Insert-triggered threshold/scale factor suitable?
- [ ] Dead tuple threshold suitable?
- [ ] Analyze threshold keeping planner fresh?
- [ ] Worker count / cost delay / `work_mem` balanced for I/O?
- [ ] Per-table `reloptions` documented with rollback plans?
- [ ] Autovacuum not accidentally disabled?

### 36.3. Transaction Horizon

- [ ] No lingering `idle in transaction` sessions?
- [ ] No orphaned prepared transactions?
- [ ] Replication slots have active consumers?
- [ ] `xmin`/`catalog_xmin` not held too long?
- [ ] Standby feedback and lag monitored?

### 36.4. Storage and Performance

- [ ] Heap/index/TOAST sizes tracked individually?
- [ ] HOT ratio healthy for the update pattern?
- [ ] Fillfactor benchmarked in staging?
- [ ] WAL/archive/checkpoint/disk capacity sufficient?
- [ ] Vacuum progress and lock waits monitored?
- [ ] `VACUUM FULL` not run arbitrarily during peak traffic?

### 36.5. Data and Retention

- [ ] Only valuable indexes retained?
- [ ] Partition granularity sensible?
- [ ] Retention uses detach/drop where appropriate?
- [ ] Bulk loads followed by ANALYZE/validation?
- [ ] Identity/sequences synced after importing explicit IDs?
- [ ] Backups and restore tests verified before major changes?

## 37. Quick Reference Table

| Component | Meaning |
|---|---|
| Insert-heavy | Heavy INSERTs, potentially few dead tuples |
| High churn | Heavy UPDATE/DELETEs creating tuple versions |
| `autovacuum_vacuum_insert_threshold` | Fixed INSERT threshold |
| `autovacuum_vacuum_insert_scale_factor` | Proportional INSERT threshold |
| `autovacuum_vacuum_threshold` | Fixed dead-tuple threshold |
| `autovacuum_vacuum_scale_factor` | Proportional dead-tuple threshold |
| `autovacuum_analyze_threshold` | Fixed auto-analyze threshold |
| `autovacuum_analyze_scale_factor` | Proportional auto-analyze threshold |
| `n_ins_since_vacuum` | Inserts since vacuum, where supported by version |
| `n_dead_tup` | Dead tuple estimate |
| `n_mod_since_analyze` | Modifications since analyze |
| `n_tup_hot_upd` | Count of HOT updates |
| HOT update | Heap-only update, reduces index churn |
| Fillfactor | Target page density, can reserve room for updates |
| Visibility map | All-visible/all-frozen page metadata |
| Freeze | Protects against XID wraparound |
| TOAST | Storage for large values |
| `pg_stat_user_tables` | Table-level counters and history |
| `pg_stat_progress_vacuum` | Vacuum progress |
| `pg_stat_activity` | Sessions and transactions |
| `pg_locks` | Locks and waits |
| `pg_replication_slots` | WAL and `xmin` retention |
| `pg_total_relation_size` | Heap + indexes + TOAST |
| Partition retention | Data removal at the relation level |
| WAL archive | Historical WAL protection and replay |
| Bulk load | Large batch data import |
| Autovacuum cost delay | Throttles vacuum activity |
| XID age | Tracks freeze/wraparound risk |

## 38. Conclusion

**Insert-heavy and high-churn are two workload patterns that demand different VACUUM mindsets.** Append-only tables may generate almost no dead tuples yet still need insert-triggered vacuum to maintain the visibility map and freeze aging tuples. High-UPDATE/DELETE tables require dead-tuple cleanup, index churn control, and enough autovacuum throughput to match modification rates.

Do not start by cranking up every autovacuum setting. Measure insert/update/delete rates, dead tuple estimates, inserts-since-vacuum counters, analyze backlogs, HOT ratios, heap/index/TOAST sizes, worker saturation, and XID age. If vacuum cannot reclaim tuples, locate long transactions, `idle in transaction` sessions, replication slots, standby feedback, and lock blockers before altering thresholds.

For high-write tables, a strong strategy combines **per-table autovacuum tuning, sensible index/fillfactor choices, short transactions, partitioning/retention, and WAL/I/O monitoring**. Bulk loads need before-during-after planning; update-heavy tables need fewer unnecessary writes and room for HOT updates; time-series tables benefit from partition lifecycle over mass DELETEs.

The operational principle is: **tune to actual data patterns and real resource limits, keep autovacuum and freezing active, resolve cleanup horizons, and verify with metrics over time**. `VACUUM FULL` is not the default answer for busy workloads; reserve it for clear rewrite/reclaim needs where disk and lock costs are acceptable.
