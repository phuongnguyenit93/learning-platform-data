# Autovacuum Workers, Cost Limits, and Cleanup Throughput in PostgreSQL

PostgreSQL creates new tuple versions on UPDATE and marks old versions as no longer needed once relevant transactions finish. DELETE also leaves behind dead tuples that must be reclaimed. Without a cleanup mechanism, tables and indexes bloat, queries must read more pages, the visibility map becomes less effective, and transaction IDs risk approaching wraparound.

**Autovacuum** is the background mechanism that automatically runs VACUUM and ANALYZE when statistics show a relation needs maintenance. However, autovacuum does not run at unlimited speed. It is governed by a launcher, concurrent worker limits, trigger thresholds, I/O cost limits, memory caps, and limits imposed by long-running transactions.

A well-tuned configuration balances three goals:

- Reclaiming dead tuples early enough to prevent table/index bloat.
- Keeping planner statistics fresh enough to choose good execution plans.
- Preventing maintenance from consuming all CPU, I/O, memory, or connection resources needed by application workloads.

~~~mermaid
flowchart TD
    L["Autovacuum launcher"] --> S["Periodically scans databases"]
    S --> Q["Evaluates thresholds and relation stats"]
    Q -->|"Eligible"| W["Autovacuum worker"]
    Q -->|"Not yet eligible"| N["Wait for next cycle"]
    W --> V["VACUUM: dead tuples, visibility map, freeze"]
    W --> A["ANALYZE: refresh planner statistics"]
    V --> C["Cost accounting"]
    A --> C
    C --> D["Cost limit reached?"]
    D -->|"Yes"| T["Cost delay / sleep"]
    D -->|"No"| V
    T --> V
~~~

This lesson belongs to the **VACUUM** chapter in the **Database Engine Relational PostgreSQL** module. We will explore the launcher/worker architecture, threshold formulas, cost-based throttling, per-table configuration, transaction ID wraparound protection, and monitoring cleanup throughput via catalogs and statistics views.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the roles of the autovacuum launcher and autovacuum workers.
2. Distinguish VACUUM, ANALYZE, and autovacuum.
3. Understand why `track_counts` must be enabled for autovacuum to work properly.
4. Compute vacuum/analyze thresholds from base thresholds and scale factors.
5. Distinguish UPDATE/DELETE-triggered vacuum from INSERT-triggered vacuum.
6. Understand `autovacuum_naptime`, `autovacuum_max_workers`, and worker limits.
7. Explain cost-based vacuum delay, cost limit, and the page cost types.
8. Know why increasing worker count does not mean linear cleanup speedup.
9. Tune autovacuum per table using storage parameters.
10. Manage `autovacuum_work_mem` and total memory impact across concurrent workers.
11. Recognize anti-wraparound vacuum and why this mechanism must not be disabled.
12. Understand how long-running transactions, replication slots, and standby feedback block cleanup.
13. Monitor with `pg_stat_user_tables`, `pg_stat_progress_vacuum`, `pg_stat_activity`, and catalogs.
14. Diagnose slow autovacuum, un-triggered autovacuum, or rising backlogs.
15. Design workload-driven tuning instead of copying one config to every database.

## 2. How Do VACUUM, ANALYZE, and Autovacuum Differ?

| Mechanism | Goal | Key Outcome |
| --- | --- | --- |
| `VACUUM` | Reclaim eligible dead tuples | Enables space reuse, updates visibility/freeze metadata |
| `ANALYZE` | Sample data and update statistics | Improves planner cardinality/selectivity estimates |
| `autovacuum` | Automatically decide when to run vacuum/analyze | Background maintenance by thresholds and stats |
| `VACUUM FULL` | Rewrite/compact relation | Can return space to filesystem, requires strong lock |

An autovacuum worker can perform VACUUM and ANALYZE on a relation depending on conditions. The two tasks have separate triggers:

- Dead tuples or insert activity can make a relation eligible for VACUUM.
- Row modifications since the last ANALYZE can make a relation eligible for ANALYZE.

**Autovacuum is not automatic VACUUM FULL.** Standard vacuum primarily makes space reusable inside the relation and maintains the visibility map; it does not compact the whole file to return disk space to the operating system by default.

## 3. Why Is Autovacuum Needed?

PostgreSQL uses MVCC. When updating a row, the engine usually creates a new tuple version; the old version becomes a dead tuple once no snapshot needs it. DELETE likewise makes a row invisible to new transactions without necessarily erasing physical storage immediately.

Example:

~~~sql
UPDATE orders
SET status = 'paid'
WHERE order_id = 100;
~~~

Logically, the application sees one row change status. In storage, PostgreSQL may hold:

- The old tuple version.
- The new tuple version.
- Related index entries.
- Visibility metadata and transaction IDs.

After many UPDATE/DELETEs without vacuuming:

- The heap accumulates dead tuples.
- Indexes require dead-entry cleanup.
- Table scans read extra pages.
- Planner statistics go stale.
- Relation size can grow.
- Transaction ID freezing can fall behind.

Autovacuum handles most routine maintenance automatically so DBAs do not have to schedule VACUUM manually for every table.

## 4. Launcher and Worker Architecture

Autovacuum has two main roles:

**Autovacuum launcher**

- Coordinating background process.
- Periodically checks databases across the cluster.
- Spawns workers when slots and eligible work exist.
- Spreads activity across databases according to `autovacuum_naptime`.

**Autovacuum worker**

- Connects to one assigned database.
- Evaluates relations eligible for vacuum/analyze.
- Performs maintenance per thresholds and cost settings.
- Emits stats/logs per configuration.

~~~text
PostgreSQL cluster
  |
  +-- Autovacuum launcher
        |
        +-- Worker 1 -> database A -> table orders
        |
        +-- Worker 2 -> database B -> table events
        |
        +-- Worker 3 -> database A -> table sessions
~~~

This diagram illustrates concurrent workers. Each worker has its own workload and duration; do not read `autovacuum_max_workers = 3` as three workers always running or each table getting three parallel workers.

### Does One Worker Process Multiple Tables at Once?

One autovacuum worker maintains eligible relations sequentially within its assigned database. `autovacuum_max_workers` caps concurrent workers cluster-wide so multiple relations/databases can be processed in parallel. Raising it does not split a single table's vacuum across multiple independent workers automatically.

## 5. Conditions for Autovacuum to Operate

Key settings:

~~~conf
autovacuum = on
track_counts = on
~~~

`track_counts` must be enabled so PostgreSQL collects table activity statistics needed for autovacuum decisions. If disabled, the automatic mechanism lacks the stats required to function properly.

Other factors include:

- The database has relations needing maintenance.
- Table-level options can override global settings.
- Worker slots are available.
- The worker can acquire the necessary locks.
- Transaction snapshots are not blocking cleanup.
- Autovacuum launcher and workers are not disabled via configuration/operational controls.

### Does autovacuum = off Disable Anti-Wraparound Vacuum?

Do not assume so. PostgreSQL can still spawn special autovacuum workers to prevent transaction ID wraparound even when regular autovacuum is turned off. This is a critical system safety mechanism.

Still, turning regular autovacuum off remains very dangerous because dead tuples, planner statistics, and insert-triggered vacuuming can be neglected for long periods.

## 6. Threshold and Scale Factor

Autovacuum does not vacuum every table after every INSERT/UPDATE/DELETE. It uses thresholds composed of a fixed base plus a proportion of relation size.

### UPDATE/DELETE Vacuum Threshold

General formula:

~~~text
vacuum threshold =
    autovacuum_vacuum_threshold
    + autovacuum_vacuum_scale_factor * reltuples
~~~

Where:

- `autovacuum_vacuum_threshold`: base dead tuple count.
- `autovacuum_vacuum_scale_factor`: fraction of the table's estimated tuples.
- `reltuples`: catalog estimated row count, not an exact real-time count.

Example with common defaults:

~~~text
autovacuum_vacuum_threshold = 50
autovacuum_vacuum_scale_factor = 0.20
reltuples = 1,000,000

threshold = 50 + 0.20 * 1,000,000
          = 200,050 dead tuples
~~~

If the table has 100 million rows, the threshold under the same formula reaches roughly 20 million dead tuples. That is why a scale factor fine for small tables can be far too loose for huge tables.

**Defaults can differ across major versions or distributions.** Always inspect `pg_settings` on your actual server before tuning.

### ANALYZE Threshold

General formula:

~~~text
analyze threshold =
    autovacuum_analyze_threshold
    + autovacuum_analyze_scale_factor * reltuples
~~~

ANALYZE triggers based on row modifications since the last analyze. It does not wait for dead tuples to cross the vacuum threshold.

Example:

- 1-million-row table.
- Base threshold 50.
- Analyze scale factor 0.10.

Estimated threshold is 100,050 modifications. When workloads shift distributions rapidly, more frequent analyze may be needed to keep planner stats current.

### Thresholds Are Estimates, Not Exact Schedules

Autovacuum relies on statistics and scheduling cycles. Do not expect a worker to start the instant a row count crosses the threshold. Launcher cadence, worker availability, relation eligibility, and lock conditions all play a part.

## 7. Insert-Triggered Vacuum

An append-only table may have almost no dead tuples from UPDATE/DELETE yet still require vacuuming.

PostgreSQL provides:

- `autovacuum_vacuum_insert_threshold`
- `autovacuum_vacuum_insert_scale_factor`

General formula:

~~~text
insert vacuum threshold =
    autovacuum_vacuum_insert_threshold
    + autovacuum_vacuum_insert_scale_factor * reltuples
~~~

Insert-triggered vacuum processes new pages, including updating the visibility map and freezing where appropriate. This supports index-only scans and manages transaction ID age.

### Why Do Insert-Only Tables Still Need Vacuum?

A time-series table may only INSERT millions of events. Without proper vacuuming:

- New pages may not get marked all-visible.
- Index-only scans may incur extra heap fetches.
- Tuple transaction ID ages still need management.
- Visibility/freeze metadata falls behind.

Never disable autovacuum just because a table has no UPDATE/DELETEs.

## 8. Common Threshold Parameters

| Parameter | Role |
| --- | --- |
| `autovacuum_vacuum_threshold` | Minimum dead tuples before considering vacuum |
| `autovacuum_vacuum_scale_factor` | Table-size proportion for vacuum |
| `autovacuum_vacuum_insert_threshold` | Base insert count for insert-triggered vacuum |
| `autovacuum_vacuum_insert_scale_factor` | Table-size proportion for insert vacuum |
| `autovacuum_analyze_threshold` | Base modification count for analyze |
| `autovacuum_analyze_scale_factor` | Table-size proportion for analyze |
| `autovacuum_vacuum_max_threshold` | Upper cap on vacuum threshold if supported by version |

Some parameters exist only in specific major versions. Do not place newer properties into older servers' configs without checking.

### Why Does the Absolute Threshold Still Matter?

For large tables, merely lowering scale factor can make small tables vacuum too frequently. A higher base threshold helps balance that.

Example:

~~~text
threshold = 2,000 + 0.01 * reltuples
~~~

With 10 million rows, the threshold is 102,000 dead tuples. With 10,000 rows, the threshold is 2,100. The same threshold/scale-factor pair behaves very differently depending on relation size.

## 9. Launcher Cadence and Worker Count

Two key parameters:

~~~conf
autovacuum_naptime = '1min'
autovacuum_max_workers = 3
~~~

These are common values seen in many PostgreSQL configurations, not prescriptions for every server.

### autovacuum_naptime

The interval the launcher waits between database check cycles. The launcher distributes worker launches across databases in the cluster; it is not a timer guaranteeing every table is vacuumed every minute.

If a cluster has many databases and limited worker slots, a table that just hit its threshold may have to wait for the next cycle or a free worker.

### autovacuum_max_workers

Maximum concurrent autovacuum workers, excluding the launcher.

Raising worker count lets more tables/databases be processed concurrently, but:

- Increases CPU and I/O concurrency.
- Increases overall memory usage.
- Can compete with application workloads.
- Total cost budget is shared across workers.
- Does not speed up a single relation proportionally to worker count.

### When to Increase Workers?

Consider increasing when:

- Many large tables simultaneously have backlogs.
- Workers are consistently occupying all slots.
- CPU/I/O headroom remains available.
- Transaction horizons are not blocking cleanup.
- Memory budget covers concurrent workers.

If a single table vacuums slowly due to I/O or old snapshots, merely adding workers usually will not solve the cause.

## 10. What Is Cost-Based Vacuum Delay?

VACUUM reads pages, inspects tuples, and updates heap/index metadata, consuming I/O and CPU. PostgreSQL uses **cost-based vacuum delay** to limit impact on application workloads.

Instead of simply setting "run at most X MB/s", PostgreSQL assigns cost points to page operations. Once accumulated cost hits the limit, the worker sleeps for the configured cost delay.

### Page Cost Types

| Parameter | Meaning | Common Default |
| --- | --- | ---: |
| `vacuum_cost_page_hit` | Page already in shared buffers | 1 |
| `vacuum_cost_page_miss` | Page must be read from storage | 2 |
| `vacuum_cost_page_dirty` | Page must be dirtied/written | 20 |

These values are relative cost units, not milliseconds or bytes. They weight operations by relative impact.

### Conceptual Example

Reading a cached page adds much less cost than missing in cache or dirtying a page. When accumulated cost hits the limit, the worker sleeps for the delay duration to ease I/O pressure.

**Cost units are not a direct throughput measurement.** Two tables with the same cost limit can still vacuum at very different speeds due to row width, index count, cache residency, storage latency, and concurrent load.

## 11. vacuum_cost_limit and vacuum_cost_delay

Manual VACUUM configuration:

~~~conf
vacuum_cost_delay = 0
vacuum_cost_limit = 200
~~~

Autovacuum-specific configuration:

~~~conf
autovacuum_vacuum_cost_delay = '2ms'
autovacuum_vacuum_cost_limit = -1
~~~

Meaning:

- `vacuum_cost_delay`: cost-based delay for standard VACUUM commands.
- `vacuum_cost_limit`: cost limit for standard VACUUM.
- `autovacuum_vacuum_cost_delay`: delay specifically for autovacuum workers.
- `autovacuum_vacuum_cost_limit`: cost limit specifically for autovacuum; `-1` usually inherits `vacuum_cost_limit`.

Do not confuse `autovacuum_vacuum_cost_delay` with `autovacuum_naptime`. One throttles work inside a vacuum run; the other governs launcher check cycles.

### Tuning Impact

- Larger delay → worker sleeps more, usually lowering I/O impact while slowing cleanup.
- Smaller delay → worker runs more aggressively, increasing potential contention.
- Higher cost limit → more work before sleeping, speeding cleanup while increasing pressure.
- Lower cost limit → earlier throttling, easing foreground impact while growing backlog.

Do not raise cost limit when storage is already saturated without measuring; it can degrade primary workloads further.

## 12. Multiple Workers Share the Cost Budget

When multiple autovacuum workers run simultaneously, PostgreSQL splits/balances the cost limit across active workers to bound total cost-based vacuum impact.

Consequences:

- Increasing `autovacuum_max_workers` does not linearly increase aggregate I/O budget.
- Each worker receives a smaller slice of the cost budget when more workers run concurrently.
- More relations can be processed concurrently, yet each worker remains throttled.
- Adding workers without extra I/O capacity can worsen application latency without noticeably shrinking the backlog.

Always evaluate `autovacuum_max_workers`, `autovacuum_vacuum_cost_limit`, `autovacuum_vacuum_cost_delay`, and real workload metrics together.

## 13. Anti-Wraparound Vacuum Is a Special Case

PostgreSQL transaction IDs come from a finite space. If a database lets old XIDs persist too long without freezing, transaction ID wraparound risk can make old data's visibility unsafe.

Autovacuum performs freezing to mark sufficiently old tuples as frozen under PostgreSQL rules, preventing wraparound.

Related parameters:

- `autovacuum_freeze_max_age`
- `vacuum_freeze_min_age`
- `vacuum_freeze_table_age`
- `vacuum_failsafe_age` (version-dependent)

### Anti-Wraparound Workers

When a relation/database nears required freeze thresholds, PostgreSQL can launch special autovacuum workers to freeze tuples even if regular autovacuum is disabled.

Anti-wraparound workers have priority to protect database correctness. Cost-based delays may behave differently compared to regular dead-tuple cleanup workers; verify documentation for your exact version.

### Do Not Disable Freezing to Save I/O

If anti-wraparound falls behind, PostgreSQL can escalate to critical warnings and eventually refuse writes to protect the database. When high XID age warnings appear, act immediately per DBA runbook rather than raising thresholds to delay vacuum.

## 14. Autovacuum Work Memory

Parameter:

~~~conf
autovacuum_work_mem = -1
~~~

`-1` typically means using `maintenance_work_mem` for each worker. When set explicitly, autovacuum workers use that configured cap.

Total memory scales with concurrent workers. For example, if each worker can allocate a large buffer, three concurrent workers consume more than one alone.

### Tuning Requires Balancing

- Worker count.
- `autovacuum_work_mem`.
- `maintenance_work_mem`.
- Index count and dead tuple volume.
- Memory needed by foreground queries/sorts/hashes.
- Total RAM and other processes on the host/container.

Do not set `autovacuum_work_mem` very high and multiply across `autovacuum_max_workers` without checking total memory capacity.

## 15. Per-Table Tuning

One global setting rarely fits every relation:

- Small, rarely changing tables.
- Large tables with constant UPDATEs.
- Append-only log tables.
- Session tables with frequent DELETE/expiration.
- Daily/monthly partitioned tables.
- Tables with many indexes.

PostgreSQL supports table-level storage parameters.

Example for a large, high-churn table:

~~~sql
ALTER TABLE public.orders
SET (
    autovacuum_vacuum_threshold = 1000,
    autovacuum_vacuum_scale_factor = 0.02,
    autovacuum_analyze_threshold = 500,
    autovacuum_analyze_scale_factor = 0.01
);
~~~

Meaning:

- Vacuum threshold is 1,000 dead tuples plus 2% of estimated row count.
- Analyze threshold is 500 modifications plus 1% of estimated row count.

These are **illustrative examples**, not default production recommendations. Choose numbers based on workload and measurement.

### Overriding Cost Per Table

Some versions support storage parameters such as:

~~~sql
ALTER TABLE public.orders
SET (
    autovacuum_vacuum_cost_delay = 1,
    autovacuum_vacuum_cost_limit = 1500
);
~~~

Table-option delay units are interpreted per version documentation; check `pg_class.reloptions` and docs. Do not assume table-level parameters share identical scope/context with global GUCs.

### Resetting to Global Defaults

~~~sql
ALTER TABLE public.orders
RESET (
    autovacuum_vacuum_threshold,
    autovacuum_vacuum_scale_factor,
    autovacuum_analyze_threshold,
    autovacuum_analyze_scale_factor,
    autovacuum_vacuum_cost_delay,
    autovacuum_vacuum_cost_limit
);
~~~

Only reset options that were actually set, and double-check schema/table names before altering.

## 16. Threshold Calculation Example for a Very Large Table

Suppose a table has 200 million estimated rows:

- `autovacuum_vacuum_threshold = 50`
- `autovacuum_vacuum_scale_factor = 0.20`

Threshold:

~~~text
50 + 0.20 * 200,000,000
= 40,000,050 dead tuples
~~~

The table could accumulate tens of millions of dead tuples before reaching that threshold.

With scale factor 0.01 and threshold 5,000:

~~~text
5,000 + 0.01 * 200,000,000
= 2,005,000 dead tuples
~~~

Autovacuum is considered much sooner. Yet more frequent vacuums also generate I/O, CPU, and index cleanup work.

**Do not pick the smallest possible scale factor.** Choose thresholds so dead tuple generation never outpaces cleanup while keeping foreground workloads stable.

## 17. Append-Only Tables and Insert-Triggered Vacuum

Example event table:

~~~sql
CREATE TABLE public.event_log (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at timestamptz NOT NULL,
    payload jsonb NOT NULL
);
~~~

The table is mostly INSERTs. Tracking only UPDATE/DELETE dead tuples rarely triggers vacuum. Insert-triggered vacuum manages new pages and freezing.

You can set workload-appropriate table options:

~~~sql
ALTER TABLE public.event_log
SET (
    autovacuum_vacuum_insert_threshold = 5000,
    autovacuum_vacuum_insert_scale_factor = 0.05
);
~~~

This example applies to servers supporting insert-triggered vacuum parameters. Check `pg_settings` before applying on older major versions.

### Append-Only Does Not Mean ANALYZE Is Unneeded

If the distributions of `occurred_at`, `event_type`, or tenant IDs shift, planner statistics still need updates. High insert volumes can leave query plans running on outdated stats.

## 18. High-Churn Tables: Continuous UPDATE/DELETE

A sessions table may continually expire old rows:

~~~sql
DELETE FROM public.sessions
WHERE expires_at < now();
~~~

A single job deleting millions of rows in one transaction creates massive dead tuples and a long-running transaction. Autovacuum cannot clean up tuples still needed by old snapshots.

Design guidelines:

- Delete in small batches with explicit commits.
- Keep an appropriate index on `expires_at`.
- Avoid overly long delete transactions.
- Tune vacuum/analyze thresholds for the table.
- Monitor dead tuple backlogs.
- For time-based retention, consider partitioning and `DROP`/`DETACH` partition instead of row-by-row DELETEs if business rules allow.

### Illustrative Batch DELETE

~~~sql
WITH batch AS (
    SELECT ctid
    FROM public.sessions
    WHERE expires_at < now()
    ORDER BY expires_at
    FOR UPDATE SKIP LOCKED
    LIMIT 5000
)
DELETE FROM public.sessions AS s
USING batch AS b
WHERE s.ctid = b.ctid;
~~~

`ctid` must only be used within the same statement to locate selected rows. Across multiple partitions, include `tableoid`. This is a maintenance pattern example, not advice to delete data without confirming retention policies.

## 19. Partitioning and Autovacuum

Partitioning can streamline time-based retention:

- Instead of deleting tens of millions of old rows, detach/drop expired partitions.
- Each partition maintains its own statistics and storage options.
- Autovacuum can be tuned differently per partition based on churn.

However:

- Child partitions still need vacuum/analyze per their own activity.
- A partitioned parent holds no heap rows like a regular table; autovacuum does not vacuum the parent as a heap relation.
- After major data changes across partitions, manual `ANALYZE` on the parent may be needed to refresh stats for partitioned queries, depending on version/behavior.
- Adding/dropping partitions is DDL with its own lock and concurrency implications.

Do not assume partitioning eliminates all VACUUM needs. It changes how data is split and how retention is executed.

## 20. Autovacuum Runs Yet Fails to Clean Up Everything

One key culprit: **old snapshots**.

VACUUM cannot remove a tuple version if any active transaction could still need to see it under MVCC visibility rules.

Sources holding the cleanup horizon:

- Very long-running transactions.
- `idle in transaction` sessions.
- Unresolved prepared transactions.
- Replication slots pinning `xmin`/`catalog_xmin`.
- Standby feedback (`hot_standby_feedback`) keeping row versions needed by standby queries.
- Certain replication/backup/decoding workflows.

### Consequences

You may see autovacuum running and scanning many pages while `n_dead_tup` fails to drop as expected or cleanup stays restricted.

**Raising cost limit cannot clean up a tuple still needed by an old snapshot.** Locate the transaction or replication horizon holding the data.

## 21. Checking Long Transactions

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Look for:

- Long-open transactions.
- `idle in transaction`.
- Backends with an old `backend_xmin`.
- Queries or apps holding transactions open across long periods.

The `query` column can contain sensitive SQL literals; restrict visibility to authorized personnel. If query text is unnecessary, omit it from dashboards.

## 22. Checking Replication Slots

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    xmin,
    catalog_xmin,
    restart_lsn
FROM pg_replication_slots
ORDER BY slot_name;
~~~

A replication slot whose consumer is not advancing can retain WAL and/or the `xmin` horizon, causing:

- Growing WAL retention.
- Disk exhaustion.
- Blocked vacuum cleanup in certain cases.
- Catalog bloat if `catalog_xmin` is pinned old.

Never drop a replication slot just to make "VACUUM run faster". Verify the consumer, resume capability, and replication/data-loss impact first.

## 23. Checking Prepared Transactions

~~~sql
SELECT
    transaction,
    gid,
    prepared,
    owner,
    database
FROM pg_prepared_xacts
ORDER BY prepared;
~~~

Prepared transactions can linger if a 2PC application or coordinator fails. They hold transaction state and interfere with cleanup.

Never manually `ROLLBACK PREPARED` an unidentified transaction; coordinate with the transaction coordinator and recovery runbook.

## 24. Checking Table Statistics

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    n_mod_since_analyze,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count,
    last_analyze,
    last_autoanalyze,
    autoanalyze_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
~~~

Meaning:

- `n_live_tup`: estimated live tuples.
- `n_dead_tup`: estimated dead tuples.
- `n_mod_since_analyze`: estimated modifications since the last analyze.
- `last_autovacuum`: timestamp of the latest autovacuum.
- `autovacuum_count`: recorded autovacuum runs.
- `last_autoanalyze`: timestamp of the latest autoanalyze.

### Figures Are Estimates

`n_live_tup`/`n_dead_tup` are not exact `COUNT(*)` values. Statistics can lag or be reset. Observe trends over time alongside progress views and logs rather than judging from a single snapshot.

Some statistics columns vary across major versions. If a query fails due to a missing column on an older server, inspect that version's catalog and adjust.

## 25. Viewing Current VACUUM Progress

PostgreSQL provides `pg_stat_progress_vacuum`:

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS relation_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed,
    index_vacuum_count,
    num_dead_tuples,
    max_dead_tuples
FROM pg_stat_progress_vacuum
ORDER BY datname, relation_name;
~~~

Phases can include:

- Initializing.
- Scanning heap.
- Vacuuming indexes.
- Vacuuming heap.
- Cleaning up indexes.
- Truncating heap.
- Performing final cleanup.

Progress columns show which stage the worker is in and how many blocks have been processed as reported by PostgreSQL.

### Do Not Infer Completion Percentage from One Column

`heap_blks_scanned / heap_blks_total` does not always reflect total remaining work percentage, because index cleanup, heap vacuuming, truncation, and final cleanup have separate costs. Read `phase` alongside the counters.

## 26. Viewing Autovacuum Workers in pg_stat_activity

~~~sql
SELECT
    pid,
    backend_type,
    datname,
    usename,
    application_name,
    state,
    query_start,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE backend_type = 'autovacuum worker'
ORDER BY query_start;
~~~

`backend_type` and session details can depend on version and viewing privileges. In some versions/setups, you can filter by other query/application metadata.

Do not confuse workers with the launcher; the launcher coordinates, while workers execute relation maintenance.

## 27. Reading Effective Configuration

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'autovacuum',
    'track_counts',
    'autovacuum_naptime',
    'autovacuum_max_workers',
    'autovacuum_vacuum_threshold',
    'autovacuum_vacuum_scale_factor',
    'autovacuum_vacuum_insert_threshold',
    'autovacuum_vacuum_insert_scale_factor',
    'autovacuum_analyze_threshold',
    'autovacuum_analyze_scale_factor',
    'autovacuum_vacuum_cost_delay',
    'autovacuum_vacuum_cost_limit',
    'autovacuum_work_mem',
    'autovacuum_freeze_max_age'
)
ORDER BY name;
~~~

Fields:

- `setting`: effective value.
- `unit`: measurement unit.
- `context`: change scope (`postmaster`, `sighup`, `superuser`, `user`, etc.).
- `source`: configuration source.
- `pending_restart`: whether a restart is required for a pending change.

Do not assume every autovacuum parameter can be changed with a reload. Some require a restart depending on context.

## 28. Checking Per-Table reloptions

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.reloptions
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm')
  AND c.reloptions IS NOT NULL
ORDER BY n.nspname, c.relname;
~~~

`reloptions` lists storage parameters overridden on the relation. A table might have a vacuum scale factor completely different from the global GUC.

If you tune by inspecting only `pg_settings`, you can miss table-level overrides.

## 29. Enabling Logs to See What Autovacuum Is Doing

PostgreSQL provides:

~~~conf
log_autovacuum_min_duration = '1s'
~~~

It logs autovacuum/autoanalyze operations meeting the configured duration threshold. Exact values and interpretation should be checked in your version's docs.

Options:

- `-1`: disables logging via this parameter.
- `0`: logs all autovacuum operations per parameter semantics.
- Positive value: logs operations lasting at least that duration.

### Benefits

Logs help identify:

- Which relation was vacuumed.
- How many pages/tuples were processed.
- Index cleanup effort.
- Workers canceled or encountering special conditions.
- Long-running jobs and observable causes.

### Risks

Logging every worker on a large cluster can create high log volume. Protect logs, enforce retention, and avoid logging unnecessary sensitive details.

## 30. Diagnosis: Table Has Many Dead Tuples Yet Autovacuum Has Not Run

Check in order:

1. Is `autovacuum` enabled?
2. Is `track_counts` enabled?
3. Does `pg_stat_user_tables.n_dead_tup` exceed the estimated threshold?
4. Do table-level `reloptions` override the threshold?
5. Are all `autovacuum_max_workers` slots occupied?
6. Is the launcher running and visiting the database?
7. Is the worker blocked/canceled by DDL or lock conflicts?
8. Do logs show errors or cancellations?
9. Does the table have temporary/unlogged/special relation behavior requiring separate handling?
10. Is a transaction horizon preventing cleanup even when workers run?

### Approximate Effective Threshold Calculation

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    current_setting('autovacuum_vacuum_threshold')::numeric
      + current_setting('autovacuum_vacuum_scale_factor')::numeric
        * GREATEST(reltuples, 0) AS estimated_global_threshold
FROM pg_stat_user_tables AS s
JOIN pg_class AS c
    ON c.oid = s.relid
ORDER BY n_dead_tup DESC;
~~~

This query illustrates global settings and `reltuples`; it **does not account for table-level `reloptions`**, insert thresholds, version-specific max caps, stats lag, or every scheduling condition. Use it for orientation, not as an exact simulation of internal launcher decisions.

## 31. Diagnosis: Autovacuum Runs Slowly

Possible causes:

- Large cost delay.
- Low cost limit.
- Multiple workers sharing the budget.
- High storage latency.
- CPU/I/O consumed by other workloads.
- Many indexes needing cleanup.
- Large row widths/TOAST data.
- High dead tuple counts.
- Old snapshots pinning the cleanup horizon.
- Large relations with many pages to scan.
- Workers interrupted by lock conflicts/DDL.

### Do Not Merely Raise autovacuum_vacuum_cost_limit

If the root cause is a long-running transaction or replication slot, raising cost limit will not make tuples removable.

If the root cause is storage saturation, raising cost limit can worsen foreground query latency.

Before tuning, read progress phases, server logs, wait events, transaction age, and replication state.

## 32. Diagnosis: Autovacuum Runs Too Frequently

Small or write-heavy tables can get vacuumed/analyzed constantly if thresholds are too low.

Impact:

- Higher I/O and WAL.
- Higher CPU usage and contention.
- Heavy autovacuum log noise.
- Frequent analyze runs and planner stats churn.
- Potential latency jitter on primary workloads.

Approach:

- Check table size and modification rate.
- Separate vacuum threshold from analyze threshold.
- Inspect table-level `reloptions`.
- Do not raise global thresholds just because one table is noisy.
- Consider partitioning/retention.
- Check planner stats freshness before loosening analyze thresholds.

## 33. Diagnosis: Table Bloats Even Though Autovacuum Runs

Autovacuum is not an automatic tool to shrink files back to the filesystem.

Scenarios:

- Dead tuples were converted into reusable free space while the file kept its size.
- Trailing empty pages can be truncated if conditions/locks permit, though this is not always possible.
- Long-running snapshots prevent cleanup.
- Index bloat may require separate investigation.
- High-churn workloads continuously generate new dead tuples.
- Table fillfactor/index design causes suboptimal page layouts.

### Do Not Use VACUUM FULL as a First Reflex

VACUUM FULL rewrites the relation, takes a strong lock, and needs extra disk space during execution. It requires a maintenance window, capacity, a lock plan, and impact assessment.

Other options depending on context include partition retention, `pg_repack` (external extension/tool), targeted index rebuilds, or schema/workload changes. Choose based on evidence, not file size alone.

## 34. Cost Limit and Application Latency

~~~text
High cost delay / low cost limit
    -> less I/O pressure
    -> worker may run longer
    -> dead tuple backlog can grow

Low cost delay / high cost limit
    -> worker works harder
    -> cleanup can finish faster
    -> CPU/I/O contention can rise
    -> query latency can degrade
~~~

Define SLOs for both sides:

- Query/API p95/p99 latency.
- Vacuum backlog / oldest dead tuples.
- Transaction ID age.
- Replication lag.
- Disk growth.
- Autovacuum worker utilization.

Never optimize vacuum throughput at the cost of slowing down application database traffic beyond acceptable limits.

## 35. autovacuum_max_workers and naptime Do Not Replace Thresholds

Different parameters govern different layers:

| Group | Parameter | Question Answered |
| --- | --- | --- |
| Eligibility | Threshold/scale factor | When does a table qualify? |
| Scheduling | `autovacuum_naptime` | How often does the launcher inspect/coordinate? |
| Concurrency | `autovacuum_max_workers` | How many workers run simultaneously? |
| Throttling | Cost delay/limit | How aggressively do workers use I/O? |
| Memory | `autovacuum_work_mem` | How much memory can a worker use for vacuum work? |
| Safety | Freeze ages | When is anti-wraparound freezing required? |

If a table only reaches its threshold after hours, lowering `naptime` will not make the threshold disappear. If all worker slots are busy, raising `cost_limit` will not create an extra worker.

## 36. Anti-Wraparound and Checking XID Age

Check database age:

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
~~~

Check relation age:

~~~sql
SELECT
    n.nspname,
    c.relname,
    age(c.relfrozenxid) AS xid_age
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm')
ORDER BY xid_age DESC
LIMIT 30;
~~~

Compare these numbers against your server's freeze settings. Do not take one fixed number from an article as a universal safety threshold for every version.

### When XID Age Is High

- Check autovacuum logs.
- Check worker slots and I/O.
- Find long-running or prepared transactions.
- Check replication slots and standby feedback.
- Identify the largest relations and oldest `relfrozenxid`.
- Plan controlled vacuum/freeze execution.
- Watch wraparound and failsafe warnings.

Never simply raise `autovacuum_freeze_max_age` to silence warnings; that increases how much work piles up and increases risk.

## 37. Freezing Is Not Deleting Data

VACUUM freeze does not delete rows. It marks sufficiently old transaction IDs so PostgreSQL can keep interpreting visibility safely across XID wraparound.

Distinguish:

- Dead tuple cleanup: removes unneeded tuple versions.
- Freezing: marks sufficiently old XID metadata.
- Analyze: refreshes planner statistics.
- Full rewrite: creates a compacted physical relation.

A single vacuum can perform multiple tasks in one pass, yet their goals and triggers differ.

## 38. Autovacuum and Index Cleanup

VACUUM cleans up dead tuple references in indexes using appropriate strategies. Index count and size heavily influence vacuum duration.

A table with 15 indexes takes far more cleanup work than a table with 2 indexes and the same row count.

### Why Not Drop Indexes Just to Vacuum Faster?

Indexes support queries, UNIQUE constraints, foreign keys, and other workloads. Only drop an index after proving it is unused and having a migration plan.

Options such as `INDEX_CLEANUP`/`PROCESS_MAIN` have version-specific semantics; never disable index cleanup globally just to rush a vacuum without evaluating index bloat and correctness.

## 39. Visibility Map and Index-Only Scans

VACUUM updates the visibility map so PostgreSQL knows which pages contain tuples visible to all relevant transactions under proper conditions.

When the visibility map marks a page all-visible, eligible Index Only Scans can skip heap fetches for that page.

With ongoing inserts/updates, visibility map bits get cleared and require vacuuming to be set again once eligible.

Check query plan:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM public.orders
WHERE order_id BETWEEN 1000 AND 2000;
~~~

Watch `Heap Fetches` if the plan is an Index Only Scan. Autovacuum does not guarantee every query becomes index-only; index coverage, the visibility map, and planner choices still govern execution.

## 40. Autovacuum on Tables with TOAST

Tables with large text/JSON/binary values can use TOAST relations. Storage parameters and vacuum work on TOAST can impact cleanup.

When investigating large tables:

- Check both `pg_total_relation_size()` and `pg_relation_size()`.
- Check index sizes.
- Remember TOAST relations can dominate total size.
- Certain table storage parameters support `toast.` variants per supported syntax; use them only when you understand the relation and version behavior.

Never inspect only heap size and conclude vacuum cleaned up the table's entire footprint.

## 41. Bulk Loads and ANALYZE

After loading millions of rows via `COPY` or bulk `INSERT`:

- Planner statistics may not yet reflect the new distribution.
- Autovacuum/autoanalyze may not have run yet.
- Production queries right after import may pick suboptimal plans.

You can proactively run:

~~~sql
ANALYZE public.orders;
~~~

If the bulk load also created dead tuples or needs freeze/visibility maintenance, evaluate VACUUM separately. Not every big INSERT needs immediate VACUUM; ANALYZE and VACUUM serve different goals.

## 42. Partitioned Tables and ANALYZE Parent

Autovacuum vacuums child partitions based on their physical data. A partitioned parent holds no heap rows like a normal table. Therefore, after major partition changes, verify whether parent statistics are updated as needed by the planner.

You can run manually:

~~~sql
ANALYZE public.partitioned_orders;
~~~

This is especially useful when data distribution or row counts across partitions shift significantly. Verify autoanalyze behavior for your major version.

## 43. Diagnosing Blocked or Canceled Workers

Autovacuum can be disrupted by DDL/lock conflicts. Check:

~~~sql
SELECT
    a.pid,
    a.backend_type,
    a.datname,
    a.query_start,
    a.wait_event_type,
    a.wait_event,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name
FROM pg_stat_activity AS a
LEFT JOIN pg_locks AS l
    ON l.pid = a.pid
WHERE a.backend_type = 'autovacuum worker'
ORDER BY a.query_start;
~~~

If a worker lacks a lock or gets canceled, inspect server logs and concurrent DDL activity.

Do not assume a worker is stuck just because a progress counter pauses for a few seconds; a phase may be doing heavy work that does not increment one counter steadily.

## 44. Reference Configurations for Different Workloads

The samples below are starting points for benchmarking, not ready-made production profiles.

### Small, Low-Churn Tables

Keeping global defaults is usually sensible. Do not lower thresholds so far that small tables vacuum/analyze constantly.

### Large, Heavy UPDATE/DELETE Tables

You can test:

~~~sql
ALTER TABLE public.orders
SET (
    autovacuum_vacuum_threshold = 2000,
    autovacuum_vacuum_scale_factor = 0.01,
    autovacuum_analyze_threshold = 1000,
    autovacuum_analyze_scale_factor = 0.02
);
~~~

Track `n_dead_tup`, query latency, worker runtime, and I/O before and after.

### Append-Only Tables

Consider insert-triggered vacuum:

~~~sql
ALTER TABLE public.event_log
SET (
    autovacuum_vacuum_insert_threshold = 5000,
    autovacuum_vacuum_insert_scale_factor = 0.05
);
~~~

Track visibility map coverage, index-only scans, insert rate, and XID age.

### Partition-Based Retention Tables

Consider dropping/detaching partitions per retention policy. Avoid deleting millions of rows just for autovacuum to clean up afterward if partition lifecycle allows safe DDL.

## 45. A Controlled Tuning Workflow

1. Capture baseline: relation sizes, `n_live_tup`/`n_dead_tup`, autovacuum count, worker progress, XID age.
2. Identify tables driving backlog and dead tuple generation rates.
3. Identify root cause: thresholds, worker slots, cost throttle, I/O, locks, or old snapshots.
4. Change only one related parameter group at a time.
5. Use table-level `reloptions` if the issue affects only a few tables.
6. Measure query p95/p99, autovacuum runtime, disk/WAL, and replication lag.
7. Observe across multiple cycles; never judge from a single vacuum run.
8. Verify freeze age and anti-wraparound safety.
9. Document old values, new values, rationale, and rollback plan.
10. Revisit tuning when workloads or table sizes change.

### Avoid Reactive Knee-Jerk Tuning

- Backlog rises → immediately raise workers.
- Query is slow → disable autovacuum.
- File is large → run VACUUM FULL.
- Worker sleeps → set cost delay to 0.

Each action can worsen the situation if the real cause is an old snapshot, disk saturation, wrong threshold, or index bloat.

## 46. Common Mistakes

1. **Disabling autovacuum cluster-wide** to save I/O, accumulating dead tuples and XID age.
2. **Disabling `track_counts`** while expecting autovacuum to still decide properly.
3. **Thinking `autovacuum_naptime` is a fixed per-table vacuum schedule.**
4. **Raising `autovacuum_max_workers` without sizing CPU/I/O/memory.**
5. **Assuming more workers speed up a single table linearly.**
6. **Confusing cost units with MB/s or milliseconds.**
7. **Setting a very high cost limit when storage is already saturated.**
8. **Setting cost delay too high, letting backlogs grow.**
9. **Tuning global thresholds for one huge table**, impacting every other table.
10. **Failing to compute thresholds using `reltuples`**, leaving a 100-million-row table waiting too long for dead tuples.
11. **Tracking only dead tuples while ignoring analyze statistics.**
12. **Thinking append-only tables need no vacuum**, overlooking insert-triggered vacuum, freezing, and the visibility map.
13. **Raising `autovacuum_work_mem` without multiplying by worker count.**
14. **Ignoring `reloptions`**, assuming global GUCs govern the table.
15. **Confusing standard VACUUM with VACUUM FULL.**
16. **Expecting standard VACUUM to return all file size to the OS.**
17. **Running VACUUM FULL on a huge table without planning locks and disk headroom.**
18. **Raising cost limit to solve old snapshots**, even though tuples are not removable yet.
19. **Ignoring `idle in transaction` and prepared transactions.**
20. **Not checking replication slots/standby feedback** when the xmin horizon is pinned.
21. **Inspecting `pg_stat_user_tables` once** instead of tracking trends.
22. **Interpreting vacuum scan progress as overall job completion percentage.**
23. **Disabling anti-wraparound/autovacuum freeze** to avoid worker runs.
24. **Raising `autovacuum_freeze_max_age` to delay warnings** without a remediation plan.
25. **Forgetting to analyze a partitioned parent after major partition changes.**
26. **Assuming index cleanup is negligible** on tables with many indexes.
27. **Looking only at heap size while ignoring TOAST and indexes.**
28. **Running ANALYZE and assuming it replaced VACUUM.**
29. **Running VACUUM and assuming planner statistics are definitely fresh.**
30. **Failing to measure impact on query latency/replication lag** after tuning.

## 47. Practice Exercises with Answers

### Exercise 1. What are the main components of autovacuum?

**Answer:** The launcher coordinates and spawns workers; workers execute vacuum/analyze on eligible relations.

### Exercise 2. What role does `track_counts` play?

**Answer:** Collects table activity statistics required for autovacuum decisions. It must be enabled for autovacuum to work properly.

### Exercise 3. How does VACUUM differ from ANALYZE?

**Answer:** VACUUM handles dead tuples, visibility, and freezing; ANALYZE updates planner statistics.

### Exercise 4. Calculate the vacuum threshold

Suppose threshold = 50, scale factor = 0.2, `reltuples` = 1,000,000.

**Answer:** `50 + 0.2 × 1,000,000 = 200,050` dead tuples.

### Exercise 5. Why is scale factor 0.2 too large for a 500-million-row table?

**Answer:** The proportional threshold reaches roughly 100 million dead tuples, letting the table accumulate huge dead space before qualifying for vacuum.

### Exercise 6. What is the analyze threshold based on?

**Answer:** Base threshold plus scale factor times estimated rows; triggered by modifications since the last analyze.

### Exercise 7. Does an insert-only table need vacuum?

**Answer:** It can need insert-triggered vacuum to process new pages, update the visibility map, and freeze tuples.

### Exercise 8. What does `autovacuum_naptime` mean?

**Answer:** The cycle interval at which the launcher inspects/coordinates databases; it does not guarantee every table vacuums on that exact interval.

### Exercise 9. What is `autovacuum_max_workers`?

**Answer:** The maximum number of concurrent autovacuum workers in the cluster.

### Exercise 10. Does doubling workers double the vacuum speed of one table?

**Answer:** No. Worker count primarily increases concurrency across jobs; cost budget is shared, and a single relation's vacuum is not automatically split across workers.

### Exercise 11. What are cost page hit/miss/dirty?

**Answer:** Relative cost units for cached pages, pages read from storage, and dirtied pages; they are not direct bytes or time durations.

### Exercise 12. What does `autovacuum_vacuum_cost_limit = -1` mean?

**Answer:** In common configurations, it uses `vacuum_cost_limit` as the cost limit for autovacuum; verify with your version's docs and `pg_settings`.

### Exercise 13. What risk comes with raising cost limit?

**Answer:** Workers run more aggressively, increasing CPU/I/O contention and potentially raising query latency.

### Exercise 14. Why does cost delay not solve old snapshots?

**Answer:** Old snapshots make tuples ineligible for removal; changing worker speed does not make them removable.

### Exercise 15. What does `autovacuum_work_mem = -1` mean?

**Answer:** Uses `maintenance_work_mem` as the corresponding limit per PostgreSQL configuration.

### Exercise 16. Why must memory be calculated with worker count?

**Answer:** Multiple workers can allocate memory concurrently, so total memory budget scales with concurrency.

### Exercise 17. What are table-level `reloptions` used for?

**Answer:** Overriding threshold/cost/autovacuum behavior for a specific relation without changing global settings.

### Exercise 18. Does disabling autovacuum on a table disable anti-wraparound?

**Answer:** Do not assume so. PostgreSQL can still run anti-wraparound workers; however, disabling regular autovacuum stops normal maintenance.

### Exercise 19. What does anti-wraparound vacuum solve?

**Answer:** Freezes tuple transaction IDs to prevent XID wraparound from threatening database correctness.

### Exercise 20. Checking database XID age

~~~sql
SELECT datname, age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
~~~

**Answer:** Reports transaction ID age per database to identify where freeze monitoring/action is needed.

### Exercise 21. Is `pg_stat_user_tables.n_dead_tup` an exact count?

**Answer:** No. It is a statistical estimate; watch trends and combine with other sources.

### Exercise 22. Which view shows vacuum progress?

**Answer:** `pg_stat_progress_vacuum`.

### Exercise 23. What can an `idle in transaction` session cause?

**Answer:** Holds a snapshot/`xmin` horizon, preventing VACUUM from cleaning up certain tuple versions.

### Exercise 24. Can a replication slot affect vacuum?

**Answer:** Yes. A slot's `xmin`/`catalog_xmin` can pin the cleanup horizon; slot lag can also retain WAL.

### Exercise 25. Does standard VACUUM return file size to the OS?

**Answer:** Usually it mainly makes space reusable inside the relation; only under certain tail-truncation conditions can it return trailing space. `VACUUM FULL` rewrites/compacts.

### Exercise 26. Why do tables with many indexes vacuum slowly?

**Answer:** Cleaning up dead index entries and index maintenance create substantial extra work.

### Exercise 27. Why might a partitioned table need `ANALYZE` on the parent?

**Answer:** The parent holds no heap rows like an ordinary table; after major partition changes, parent statistics may need refreshing for accurate planning.

### Exercise 28. Does running ANALYZE replace VACUUM?

**Answer:** No. ANALYZE updates statistics; it does not clean dead tuples or freeze.

### Exercise 29. Tuning for a 200-million-row table with scale 0.01 and threshold 5,000?

**Answer:** Estimated threshold is `5,000 + 2,000,000 = 2,005,000` dead tuples.

### Exercise 30. Autovacuum is running yet `n_dead_tup` is not dropping; what to check first?

**Answer:** Check long transactions, `backend_xmin`, prepared transactions, replication slots/standby feedback, worker phase, and locks/logs before raising cost limit.

## 48. Operational Checklist

- [ ] `autovacuum` enabled and `track_counts` enabled.
- [ ] Understand launcher/worker roles and worker slots.
- [ ] Check global and table-level thresholds/scale factors.
- [ ] Calculate thresholds for large tables using estimated `reltuples`.
- [ ] Track vacuum and analyze separately.
- [ ] Check insert-triggered vacuum for append-only tables.
- [ ] Tune `autovacuum_naptime` for database count and workload.
- [ ] Never raise `autovacuum_max_workers` without checking CPU/I/O/memory.
- [ ] Understand cost units, cost delay, and cost limit.
- [ ] Account for cost budget sharing across workers.
- [ ] Calculate aggregate memory across autovacuum workers.
- [ ] Use `reloptions` for special tables instead of changing globals arbitrarily.
- [ ] Monitor anti-wraparound and `age(datfrozenxid)`.
- [ ] Never disable freezing/autovacuum to dodge I/O.
- [ ] Check long-running and `idle in transaction` sessions.
- [ ] Check prepared transactions.
- [ ] Check replication slots and standby feedback.
- [ ] Monitor `n_dead_tup`, `last_autovacuum`, and `autovacuum_count`.
- [ ] Monitor `pg_stat_progress_vacuum` and worker wait events.
- [ ] Enable autovacuum logging with an appropriate duration threshold.
- [ ] Distinguish standard VACUUM from VACUUM FULL.
- [ ] Never expect standard VACUUM to shrink relation files to the OS.
- [ ] Track index/TOAST sizes, not heap size alone.
- [ ] Run parent `ANALYZE` after major partition changes when needed.
- [ ] Benchmark before/after across query p95/p99, I/O, WAL, and replication lag.
- [ ] Maintain a runbook for when XID age nears alert thresholds.

## 49. Official PostgreSQL Documentation

Read according to the major version you run:

- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — VACUUM, autovacuum, dead tuples, freezing, and statistics.
- [Autovacuum Configuration](https://www.postgresql.org/docs/current/runtime-config-autovacuum.html) — launcher, workers, thresholds, cost delay, memory, and freeze settings.
- [Resource Consumption](https://www.postgresql.org/docs/current/runtime-config-resource.html) — cost-based vacuum delay and memory settings.
- [VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html) — options, VERBOSE, ANALYZE, FULL, and freeze.
- [ANALYZE](https://www.postgresql.org/docs/current/sql-analyze.html) — updating planner statistics.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — `pg_stat_user_tables`, `pg_stat_activity`, and progress views.
- [Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html) — `pg_stat_progress_vacuum`.
- [System Catalog pg_class](https://www.postgresql.org/docs/current/catalog-pg-class.html) — `reltuples`, `reloptions`, and `relfrozenxid`.
- [System Catalog pg_database](https://www.postgresql.org/docs/current/catalog-pg-database.html) — `datfrozenxid`.
- [Replication Slots](https://www.postgresql.org/docs/current/view-pg-replication-slots.html) — `xmin`/`catalog_xmin` and slot state.
- [Hot Standby](https://www.postgresql.org/docs/current/hot-standby.html) — feedback and conflict behavior.
- [Transaction ID Wraparound](https://www.postgresql.org/docs/current/routine-vacuuming.html#VACUUM-FOR-WRAPAROUND) — freezing and wraparound prevention.
- [Table Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html) — partition maintenance and statistics.
- [ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html) — per-relation storage parameters.

URLs with `/current/` point to the current PostgreSQL documentation. Thresholds, progress columns, insert-triggered vacuum, and some cost/freeze parameters can differ across major versions; verify `pg_settings` and version-specific docs before deploying.

## 50. Summary

**Autovacuum is a background scheduling and maintenance system governed by trigger thresholds, concurrency caps, cost throttling, and transaction ID protection.** Keeping it up to speed with workloads requires fixing the right bottleneck rather than blindly bumping a single setting.

1. **Launcher schedules, workers execute.** `autovacuum_max_workers` caps concurrent workers; it does not automatically split one table's vacuum into parallel tasks.
2. **Thresholds decide when a relation qualifies.** A 20% scale factor can be far too high for tables with hundreds of millions of rows.
3. **VACUUM, ANALYZE, and insert-triggered vacuum have distinct purposes.** Append-only tables can still need vacuuming.
4. **Cost delay/limit throttle I/O impact.** Cost units are relative weights, not MB/s.
5. **Multiple workers share the cost budget.** Raising concurrency does not linearly multiply aggregate throughput.
6. **Table-level `reloptions` let you tune huge/high-churn tables individually** without changing every other relation.
7. **Autovacuum work memory multiplies with worker concurrency**, so budget against total RAM.
8. **Anti-wraparound vacuum is a mandatory safety safeguard.** Never disable freezing to reduce load.
9. **Long-running snapshots, prepared transactions, and replication slots can block cleanup.** Raising cost limit will not release a pinned cleanup horizon.
10. **Monitoring must combine table statistics, progress views, activity, logs, and XID age.**
11. **Standard VACUUM mainly creates reusable space**, unlike VACUUM FULL which rewrites the relation.
12. **Tuning must be workload-driven and measured**, including query latency, I/O, WAL, replication lag, and backlog.

Once you understand **which threshold triggers workers, how much resource workers are allowed to consume, and what can prevent tuples from being cleaned**, you can keep PostgreSQL healthy while protecting application performance.
