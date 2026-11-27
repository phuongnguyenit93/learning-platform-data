# Autovacuum Falling Behind and Transaction ID Warnings

Autovacuum is PostgreSQL's essential background maintenance mechanism. It automatically cleans up obsolete row versions, updates statistics for the query planner, and freezes old transaction IDs to prevent transaction ID wraparound. When autovacuum cannot keep up with the write rate, tables bloat, queries slow down, statistics go stale, and transaction ID age rises until it threatens write availability.

Two issues must be handled together yet clearly distinguished:

- **Autovacuum lag:** vacuum/analyze work is generated faster than workers can process it, or is obstructed by long transactions, replication slots, I/O load, or suboptimal configuration.
- **Transaction ID wraparound risk:** PostgreSQL is running out of the safe comparison window for 32-bit transaction IDs. This is a severe data integrity risk. When the limit gets too close, PostgreSQL may force emergency vacuum prioritization and ultimately refuse to assign new transaction IDs to protect data.

The operational objective is early detection, finding the true root cause, catching vacuum up, and confirming transaction ID age drops or stabilizes within safe bounds. Never simply throw more resources at it or run a single vacuum while ignoring why the system fell behind.

## 1. Why Does PostgreSQL Need Autovacuum?

### 1.1. MVCC Creates Row Versions

PostgreSQL uses Multi-Version Concurrency Control (MVCC) so transactions see a snapshot of data consistent with their point in time. When a row is updated or deleted, PostgreSQL typically writes a new row version or marks the old version obsolete. The old version cannot be reclaimed immediately if any active transaction holds a snapshot that might still need to see it.

Example:

```sql
UPDATE orders
SET status = 'shipped'
WHERE order_id = 1001;

DELETE FROM session_events
WHERE created_at < now() - interval '90 days';
```

These operations leave behind dead tuples in the heap. A dead tuple is no longer visible to any valid transaction, yet still occupies table space and may have index references pointing to it. Vacuum identifies tuples no longer visible anywhere, cleans up needed index references, and marks space as reusable.

Regular vacuum **does not necessarily shrink the table file on the filesystem**. Reclaimed space is usually kept inside the relation for PostgreSQL to reuse on future inserts and updates. That differs from returning disk space to the operating system.

### 1.2. Primary Tasks of Autovacuum

The autovacuum launcher monitors databases and spawns workers when work is needed. Workers perform two main jobs:

1. **VACUUM:** removes dead tuples, cleans up associated indexes, updates the visibility map, and freezes sufficiently old transaction IDs.
2. **ANALYZE:** samples data to update statistics for the query planner, helping PostgreSQL estimate row counts and choose sound query plans.

Autovacuum also runs special anti-wraparound vacuums. This job does not depend solely on dead tuple counts. A rarely updated table can still require vacuum freeze if old transaction IDs inside it approach the safety threshold.

### 1.3. How Vacuum, Analyze, and Freeze Differ

| Operation | Purpose | Problem If Delayed |
|---|---|---|
| `VACUUM` | Reclaim eligible dead tuples and enable space reuse | Table/index bloat, excess dead tuples, higher I/O, degraded performance. |
| `ANALYZE` | Update statistics for the planner | Planner misestimates, picks poor scans or joins. |
| `VACUUM FREEZE` | Freeze old transaction IDs in tuples | Increases risk of transaction ID wraparound. |

A single autovacuum run can perform multiple tasks in the same cycle, though vacuum and analyze have separate triggers. Never treat `last_analyze` as proof that freezing is keeping up, nor treat `last_autovacuum` as proof every table is safe.

## 2. Transaction IDs and Wraparound Risk

### 2.1. What Is a Transaction ID?

PostgreSQL assigns a transaction ID (XID) to transactions requiring identity under MVCC. Standard XIDs are 32-bit integers, so the ID space is finite and wraps around after roughly (2^{32}) values. Because PostgreSQL compares transaction ages using modular arithmetic, the safe distance between XIDs must stay below half that space—around (2^{31}) transactions.

PostgreSQL cannot allow a tuple containing a very old XID to later be compared as a newer XID after the counter wraps around. If that happened, old tuples could be misinterpreted as invisible or vice versa, threatening data integrity.

### 2.2. How Freezing Solves the Problem

Once a tuple is old enough and safe to freeze, PostgreSQL marks the creating XID (`xmin`) as `FrozenTransactionId`. The frozen marker has special semantics: the tuple is treated as existing prior to all current transactions, so PostgreSQL no longer needs to compare its original XID forever.

Vacuum freeze also updates metadata tracking the oldest transaction ID that might still exist in a relation. Key concepts to distinguish:

- `pg_class.relfrozenxid`: oldest XID PostgreSQL must still consider for that relation.
- `pg_database.datfrozenxid`: oldest XID watermark for the database, derived from tracked relations inside that database.
- `age(xid)`: estimated number of transactions elapsed since the specified XID.
- `autovacuum_freeze_max_age`: age threshold at which autovacuum triggers an anti-wraparound vacuum on a table.

`datfrozenxid` and `relfrozenxid` are freeze management watermarks, not database creation times or the timestamp of the last transaction. The higher the XID age, the more urgent the attention needed.

### 2.3. Key Freeze Thresholds

PostgreSQL provides several related parameters:

| Parameter | Meaning |
|---|---|
| `vacuum_freeze_min_age` | Minimum age of an XID before a normal vacuum considers freezing the tuple. |
| `vacuum_freeze_table_age` | Relation age beyond which vacuum performs an aggressive scan to freeze more broadly. |
| `autovacuum_freeze_max_age` | Maximum age before autovacuum proactively launches an anti-wraparound vacuum. |
| `vacuum_failsafe_age` | Very high threshold enabling vacuum failsafe mode, prioritizing wraparound completion. |
| `autovacuum_multixact_freeze_max_age` | Corresponding threshold for MultiXact IDs. |

Default values and configuration bounds can vary across major versions. Common values across many PostgreSQL versions are tens of millions for `vacuum_freeze_min_age`, around 150 million for `vacuum_freeze_table_age`, 200 million for `autovacuum_freeze_max_age`, and around 1.6 billion for `vacuum_failsafe_age`; always inspect actual values on your server rather than relying on these illustrative figures.

When vacuum approaches the failsafe threshold, PostgreSQL skips cost-based delays and non-essential maintenance such as index cleanup to prioritize finishing freezing. This is a last-resort safeguard, not a normal operating state.

### 2.4. Why Transaction ID Warnings Are Critical

If a database nears the wraparound limit, PostgreSQL logs warnings such as:

```text
WARNING: database "..." must be vacuumed within ... transactions
```

If it continues approaching the danger threshold, PostgreSQL refuses to allocate new transaction IDs to prevent wraparound and throws errors like:

```text
ERROR: database is not accepting commands to avoid wraparound data loss
```

This is a self-protection mechanism. Once the system reaches this state, writes suffer severe disruption and recovery requires DBA or service-provider intervention. Never wait for the final warning to act.

### 2.5. MultiXacts Have Their Own Wraparound Threshold

Beyond XIDs, PostgreSQL uses MultiXact IDs to represent a group of transactions concurrently holding locks on a tuple—for example, multiple transactions locking the same row in compatible modes. MultiXacts have their own lifecycle and freeze mechanism.

If logs warn about `multixact` or `datminmxid`/`relminmxid` age climbs high, investigate similarly using MultiXact functions and parameters such as `mxid_age()` and `autovacuum_multixact_freeze_max_age`. Do not use `age()` for MultiXact IDs.

## 3. Recognizing Autovacuum Falling Behind

A single symptom is insufficient to conclude autovacuum is broken. Combine dead tuple counts, last vacuum timestamps, XID age, worker status, long transactions, and replication slots.

### 3.1. Table-Level Symptoms

- `n_dead_tup` climbs steadily across multiple samples.
- `last_autovacuum` or `last_autoanalyze` stays stale despite heavy writes to the table.
- Table/index size grows faster than useful business data.
- Query latency rises, buffer hit ratio drops, or more pages must be read from storage.
- Frequently updated or deleted tables are not vacuumed quickly enough.
- `relfrozenxid` age climbs across measurements.

`n_dead_tup` is a statistics estimate, not an exact tuple count. Watch trends over time alongside table size, write volume, and vacuum progress.

### 3.2. Database/Cluster-Level Symptoms

- `age(datfrozenxid)` rises rapidly or one database shows abnormally high age compared to others.
- Logs contain warnings to vacuum within a remaining number of transactions.
- Autovacuum workers are constantly busy, max workers is insufficient, or vacuums take a very long time.
- WAL, storage, or I/O surges sharply when vacuums begin running heavily.
- Replication slots or standby feedback pin an old `xmin`.
- Many sessions sit in `idle in transaction` or transactions stay open for hours or days.

### 3.3. Reading Current Autovacuum Configuration

Run inside the database under investigation:

```sql
SHOW autovacuum;
SHOW track_counts;
SHOW autovacuum_naptime;
SHOW autovacuum_max_workers;
SHOW autovacuum_vacuum_threshold;
SHOW autovacuum_vacuum_scale_factor;
SHOW autovacuum_vacuum_insert_threshold;
SHOW autovacuum_vacuum_insert_scale_factor;
SHOW autovacuum_analyze_threshold;
SHOW autovacuum_analyze_scale_factor;
SHOW autovacuum_vacuum_cost_limit;
SHOW autovacuum_vacuum_cost_delay;
SHOW autovacuum_work_mem;
SHOW vacuum_freeze_min_age;
SHOW vacuum_freeze_table_age;
SHOW autovacuum_freeze_max_age;
SHOW vacuum_failsafe_age;
```

Some parameters may not exist in older major versions. Use `pg_settings` to inspect parameter names, values, configuration sources, and restart requirements:

```sql
SELECT
    name,
    setting,
    unit,
    source,
    pending_restart
FROM pg_settings
WHERE name LIKE 'autovacuum%'
   OR name LIKE 'vacuum_freeze%'
   OR name = 'vacuum_failsafe_age'
ORDER BY name;
```

`track_counts` must be enabled for statistics-driven autovacuum to work properly. In managed PostgreSQL environments, some settings may be locked or modifiable only via parameter groups and may require a restart.

## 4. Essential Diagnostic Queries

### 4.1. Ranking Databases by XID Age

Run from any database where your role has catalog read privileges:

```sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age,
    current_setting('autovacuum_freeze_max_age')::bigint AS freeze_max_age,
    round(
        100.0 * age(datfrozenxid)
        / current_setting('autovacuum_freeze_max_age')::bigint,
        1
    ) AS pct_of_freeze_max_age
FROM pg_database
WHERE datallowconn
ORDER BY age(datfrozenxid) DESC;
```

This query identifies which database requires priority. The percentage is a relative monitoring indicator against the configured threshold, not a probability of wraparound. Track XID age trends and growth rates rather than relying on a single snapshot.

### 4.2. Ranking Relations by `relfrozenxid` Age

Run inside the high-age database:

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind,
    age(c.relfrozenxid) AS xid_age,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
    COALESCE(s.n_live_tup, 0) AS estimated_live_tuples,
    COALESCE(s.n_dead_tup, 0) AS estimated_dead_tuples,
    s.last_autovacuum,
    s.autovacuum_count
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
LEFT JOIN pg_stat_all_tables AS s
    ON s.relid = c.oid
WHERE c.relkind IN ('r', 'm', 't')
ORDER BY age(c.relfrozenxid) DESC
LIMIT 30;
```

`r` is a regular table with storage, `m` is a materialized view, and `t` is a TOAST table. Partition leaves with storage appear here; partitioned parent tables hold no heap of their own and must not be judged for tuple age like regular tables. Do not filter out `pg_catalog` on an initial pass because system catalogs must be frozen too.

### 4.3. Checking Dead Tuples and Vacuum History

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
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
```

If `n_dead_tup` remains large even though autovacuum ran recently, the worker may not have finished everything yet or the table continues generating dead tuples rapidly. Take multiple samples and compare trends. For partitioned tables, inspect each leaf partition individually since every partition has its own vacuum cycle.

### 4.4. Viewing Running Vacuums

```sql
SELECT
    pid,
    datname,
    relid::regclass AS relation_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed,
    index_vacuum_count
FROM pg_stat_progress_vacuum
ORDER BY datname, relation_name;
```

This view shows active vacuums and their current phase. Sample periodically to gauge progress. Not every vacuum type or stage is reflected equally across every progress column.

### 4.5. Finding Long Transactions and Old Snapshots

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    backend_xmin,
    age(backend_xmin) AS backend_xmin_age,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
   OR backend_xmin IS NOT NULL
ORDER BY xact_start NULLS LAST;
```

Pay close attention to `idle in transaction`, old transactions, sessions holding long-lived cursors/snapshots, and hung batch processes. An old snapshot prevents vacuum from removing tuples that transaction could still see.

Never automatically terminate every old session. Before killing one, verify the application owner, transaction state, user impact, and whether it holds critical locks. Once termination is warranted, `pg_cancel_backend()` cancels only the active query; `pg_terminate_backend()` ends the session and rolls back any uncommitted transaction. Follow your runbook and privilege controls.

### 4.6. Checking Replication Slots Holding xmin

```sql
SELECT
    slot_name,
    slot_type,
    active,
    xmin,
    age(xmin) AS xmin_age,
    catalog_xmin,
    age(catalog_xmin) AS catalog_xmin_age,
    restart_lsn
FROM pg_replication_slots
ORDER BY GREATEST(
    COALESCE(age(xmin), 0),
    COALESCE(age(catalog_xmin), 0)
) DESC;
```

Logical replication slots or CDC connector slots can hold `xmin`/`catalog_xmin`, forcing vacuum to retain old tuples or catalog rows. An inactive slot sitting idle for a long time still pins resources. Before dropping a slot, verify whether the consumer still needs it; dropping an active dependency can force subscribers to rebuild or resync data.

For streaming standbys, also inspect `pg_stat_replication` and `hot_standby_feedback`. Feedback reduces query conflicts on standbys at the cost of pinning an older `xmin` on the primary and increasing bloat.

### 4.7. Checking Prepared Transactions

```sql
SELECT
    gid,
    owner,
    database,
    prepared,
    now() - prepared AS prepared_age
FROM pg_prepared_xacts
ORDER BY prepared;
```

Abandoned prepared transactions retain state and block cleanup. Coordinate with the transaction coordinator or application owner to decide between `COMMIT PREPARED` and `ROLLBACK PREPARED`. Never roll back a prepared transaction on your own solely because it is old; doing so carelessly can cause data divergence across distributed systems.

## 5. Why Does Autovacuum Fall Behind?

### 5.1. Dead Tuple Generation Exceeds Vacuum Capacity

A table with high update/delete rates can produce dead tuples faster than a worker can clean them. This is common in event, status, session, queue, or continuously updated tables.

Standard autovacuum triggers based on a threshold plus a scale factor. Approximate formula for tables with updates/deletes:

\[
\text{Vacuum threshold} =
\text{autovacuum\_vacuum\_threshold} +
\text{autovacuum\_vacuum\_scale\_factor} \times
\text{estimated table tuples}
\]

For instance, with a threshold of 50, a scale factor of 0.2, and 10 million tuples, the trigger threshold is roughly 2,000,050 dead tuples. On very large tables, waiting until 20% dead tuples is often too late and forces each vacuum run to process massive work.

Besides update/delete vacuuming, PostgreSQL has a separate insert trigger to freeze newly inserted tuples on insert-heavy tables. `autovacuum_vacuum_insert_threshold` and `autovacuum_vacuum_insert_scale_factor` govern this mechanism; setting the threshold to `-1` disables insert-based vacuum triggering.

### 5.2. Long Transactions or Snapshots

A long-open transaction—even while `idle in transaction`—pins an old snapshot. Vacuum cannot reclaim row versions still potentially visible to that snapshot.

Common causes:

- Applications opening a transaction before calling an external API and waiting too long for a response.
- Batch jobs processing millions of rows inside one giant transaction.
- Connection pools returning a connection to the pool before ending its transaction.
- Operators opening a transaction in `psql` and leaving the session idle overnight.
- Reports or cursors holding snapshots open for long periods.

Fix this at the application layer with short transactions, checkpointed batches, proper timeouts, and guaranteed `COMMIT`/`ROLLBACK` across all error paths. Never hold a transaction open while waiting on users or network services.

### 5.3. Replication Slots or Standby Feedback Pinning Old Data

Replication slots exist to retain WAL and/or tuples needed by consumers. If a consumer stops or lags badly, its slot pins an old `xmin` or `catalog_xmin`. Likewise, `hot_standby_feedback` can pin an old horizon to avoid query conflicts on standbys.

Consequences include:

- Dead tuples remain unremoved even after autovacuum runs.
- Table and index bloat grow.
- Old catalog rows linger longer.
- WAL archives or `pg_wal` grow if the slot pins an old `restart_lsn`.

The fix is recovering the consumer, resolving lag, fixing the CDC pipeline, or revisiting feedback policy. Drop a slot only after confirming the consumer no longer needs it and a resynchronization plan exists.

### 5.4. Too Few Autovacuum Workers or Overloaded Workers

`autovacuum_max_workers` caps concurrent workers. When many large tables require vacuuming, too few workers forces jobs to queue. `autovacuum_naptime` affects how often the launcher checks databases.

Even with enough workers, they can be throttled by cost delays, I/O, CPU, or storage throughput. Vacuuming many tables simultaneously can compete with application workloads. Raising worker counts or cost limits speeds up vacuum at the cost of higher I/O load and potential latency impact.

### 5.5. Autovacuum Disabled or Statistics Inactive

Verify `autovacuum` and `track_counts`. If autovacuum is disabled or statistics collection is off, normal triggers will not fire as expected. Never disable autovacuum to reduce production load without an equivalent manual vacuum schedule and strict freeze monitoring.

Individual tables may override server defaults via storage parameters. Check `reloptions`:

```sql
SELECT
    n.nspname,
    c.relname,
    c.reloptions
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.reloptions IS NOT NULL
ORDER BY n.nspname, c.relname;
```

Watch for settings like `autovacuum_enabled=false`, very high scale factors, or large thresholds. Never assume a table with autovacuum disabled receives identical automatic protection across all versions; verify behavior for your running version and never disable freeze protection.

### 5.6. Vacuum Blocked or Canceled

Regular vacuum runs concurrently with most reads and writes, yet still acquires locks and can conflict with certain DDL or maintenance commands. Autovacuum can also be canceled due to lock conflicts, worker crashes, or manual termination.

Check PostgreSQL logs for worker cancellation messages, lock timeouts, I/O errors, or filesystem errors. Correlate with `pg_stat_progress_vacuum`, `pg_stat_activity`, and DDL timestamps.

### 5.7. Bulk Loads and Insert-Heavy Tables

Importing hundreds of millions of rows creates vast amounts of new data quickly. On tables with few updates, dead-tuple-based vacuum triggers fail to reflect the need to freeze new tuples. Review insert-based vacuum thresholds and schedule `VACUUM` after bulk loads when appropriate.

After a large bulk load, run `ANALYZE` to refresh statistics. If the table needs early freezing or has high XID age, consider `VACUUM (FREEZE, ANALYZE)` under resource-controlled procedures.

## 6. Procedure When Receiving a Transaction ID Warning

When logs warn that a database must be vacuumed within a remaining transaction count, treat it as a high-priority incident. First identify the high-XID-age database and relations, and ensure PostgreSQL can make vacuum progress.

### 6.1. Step 1 — Assess Urgency

1. Record the exact warning text, timestamp, and PostgreSQL major version.
2. Run the XID age query across all accessible databases.
3. Rank relations by `age(relfrozenxid)`.
4. Compare current ages against `autovacuum_freeze_max_age` and `vacuum_failsafe_age`.
5. Measure XID age growth rate using multiple samples over time.
6. Confirm whether the system still accepts writes and whether autovacuum workers are running.

You can set internal alert thresholds as percentages of `autovacuum_freeze_max_age`—for example, early warning at 50%, elevated at 70%, and critical at 85%. These are starting points for monitoring; calibrate them to XID consumption rate, vacuum throughput, and operational requirements. Direct PostgreSQL warnings must always be acted on even if dashboards have not tripped internal thresholds yet.

### 6.2. Step 2 — Check Autovacuum and Workers

```sql
SELECT
    pid,
    datname,
    relid::regclass AS relation_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed
FROM pg_stat_progress_vacuum;

SELECT
    pid,
    backend_type,
    datname,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE backend_type = 'autovacuum worker'
ORDER BY query_start;
```

If no workers are running, check the launcher, configuration, `track_counts`, logs, and managed service limits/permissions. If workers are active yet slow, inspect their phase, relation sizes, I/O latency, and sessions pinning old snapshots.

### 6.3. Step 3 — Remove Horizon Blockers

Check long transactions, prepared transactions, replication slots, and standby feedback. Coordinate with application owners to close abandoned transactions. Recover replication slot consumers or resolve lag per runbook.

Never blindly drop slots, terminate sessions, or roll back prepared transactions solely based on age. Each action risks desynchronization or rolling back business work. Record owner, rationale, and impact before acting.

### 6.4. Step 4 — Run Controlled Vacuum Freeze

If XID age is high and autovacuum cannot keep pace, a DBA can run a manual freeze vacuum on priority relations:

```sql
VACUUM (FREEZE, VERBOSE) public.large_events;
```

`FREEZE` freezes eligible tuples, bringing the relation's XID age back to a safer level. Run it inside the database containing the table. `VACUUM` cannot run inside a transaction block, so do not wrap it in `BEGIN`/`COMMIT`.

When multiple tables across a database need attention, use `vacuumdb` from an administrative host:

```bash
vacuumdb \
  --all \
  --freeze \
  --jobs=2 \
  --verbose
```

This example runs freeze vacuum across accessible databases with two parallel jobs. Pick a job count suited to CPU, I/O, storage, and production load. When targeting one specific database, narrow the scope rather than running cluster-wide unnecessarily. On managed services, commands or privileges may be restricted; follow vendor documentation and support channels.

Never default to `VACUUM FULL` for wraparound recovery. `VACUUM FULL` rewrites the table, requires exclusive locks and extra disk space, can disrupt applications, and is not the right emergency tool for freezing XIDs. Regular `VACUUM` or `VACUUM (FREEZE)` is far better suited to anti-wraparound goals.

### 6.5. Step 5 — Monitor and Verify

While vacuum runs, monitor:

- Progress in `pg_stat_progress_vacuum`.
- `relfrozenxid` age on priority relations and `datfrozenxid` on the database.
- I/O latency, CPU, storage headroom, and application query latency.
- Logs for canceled vacuums, index errors, filesystem errors, or wraparound warnings.
- Replication lag and WAL retention if standbys or slots exist.

After vacuum completes, re-run the XID age queries. Confirm relation and database ages dropped or stabilized below safe limits, no new warnings appear, and autovacuum continues operating normally. If database age did not drop as expected, check for other high-`relfrozenxid` relations, system catalogs, or TOAST tables not yet processed.

## 7. Tuning Autovacuum to Prevent Recurrence

No single parameter set fits every table. Small tables, append-only tables, update-heavy tables, and large partitions behave differently. Tune using per-relation metrics and measure the impact after each change.

### 7.1. Lowering Vacuum Thresholds for Large, Update-Heavy Tables

For example, a `public.events` table with tens of millions of frequently updated rows:

```sql
ALTER TABLE public.events SET (
    autovacuum_vacuum_threshold = 5000,
    autovacuum_vacuum_scale_factor = 0.02,
    autovacuum_analyze_threshold = 2000,
    autovacuum_analyze_scale_factor = 0.01
);
```

These numbers are illustrative. A lower scale factor runs vacuum more often before huge dead-tuple backlogs build up. An absolute threshold avoids vacuuming tiny tables too aggressively. Factor in write rates, table scan costs, indexes, and application latency.

To revert back to server defaults:

```sql
ALTER TABLE public.events RESET (
    autovacuum_vacuum_threshold,
    autovacuum_vacuum_scale_factor,
    autovacuum_analyze_threshold,
    autovacuum_analyze_scale_factor
);
```

### 7.2. Tuning Insert-Heavy Tables

For tables receiving mostly inserts with few updates or deletes, configure insert-based vacuuming:

```sql
ALTER TABLE public.audit_events SET (
    autovacuum_vacuum_insert_threshold = 10000,
    autovacuum_vacuum_insert_scale_factor = 0.05
);
```

This trigger freezes new tuples on insert-heavy tables instead of waiting for dead tuples to accumulate. Choose thresholds based on table size, insert velocity, and XID age requirements.

### 7.3. Increasing Worker Capacity

Server-level parameters commonly reviewed:

```conf
autovacuum = on
track_counts = on
autovacuum_max_workers = 5
autovacuum_naptime = 20s
autovacuum_vacuum_cost_limit = 2000
autovacuum_vacuum_cost_delay = 2ms
```

These illustrate the parameter group, not a universal recommendation. Raising `autovacuum_max_workers` lets more relations run in parallel at the cost of greater CPU, memory, and I/O contention. Raising cost limits or lowering cost delays reduces worker throttling, speeding up vacuum while potentially slowing foreground application workloads.

`autovacuum_work_mem` sets working memory for workers storing dead tuple/index lists. Evaluate total memory when multiple workers run concurrently. A change beneficial to one table can strain the whole cluster.

In managed PostgreSQL, parameters are typically configured via parameter groups or APIs. Verify which changes require a restart, which apply dynamically, and which are capped by the provider.

### 7.4. Avoiding Vacuum Running Too Late or Too Often

Vacuuming too late lets dead tuples accumulate, lengthens each vacuum run, and risks dangerous XID ages. Vacuuming too often wastes I/O and CPU and can hurt application throughput.

Balance this by:

- Setting lower scale factors on large, high-churn tables.
- Keeping reasonable thresholds so tiny tables do not vacuum continuously.
- Tuning insert thresholds on append-only tables.
- Tracking `n_dead_tup`, `last_autovacuum`, table size, and `relfrozenxid` age over time.
- Partitioning data by time or business key when feasible to simplify retention and maintenance.
- Using bounded batch updates/deletes rather than one giant transaction.
- Using partition drops/detaches for data retention where data models allow, rather than deleting billions of rows and waiting for vacuum.

### 7.5. Reducing Bloat and Churn at the Application Layer

Autovacuum cannot infinitely compensate for write-amplifying application patterns. Ways to reduce pressure include:

- Avoid repeatedly updating a column when each update needlessly writes a new row version.
- Tune `fillfactor` on update-heavy tables to leave room for HOT updates where conditions permit.
- Audit unnecessary indexes since every non-HOT update maintains all indexes.
- Break huge batches into short checkpointed transactions.
- Design retention and partitioning to drop old data in bulk.
- Avoid holding long snapshots in reports and export jobs.
- Monitor replication slots and CDC consumers so they never pin `xmin` indefinitely.

## 8. Proactive Monitoring and Alerting

Monitor both autovacuum health and wraparound risk. Watching CPU and disk alone is insufficient for early detection.

### 8.1. Metrics to Collect

| Metric | Source | Purpose |
|---|---|---|
| `age(datfrozenxid)` by database | `pg_database` | Track database-level XID wraparound risk. |
| `age(relfrozenxid)` by relation | `pg_class` | Identify oldest tables and catalogs. |
| `n_dead_tup` | `pg_stat_all_tables` | Track estimated dead tuples. |
| `last_autovacuum`, `autovacuum_count` | `pg_stat_all_tables` | Track automatic vacuum history. |
| Active workers and phase | `pg_stat_progress_vacuum`, `pg_stat_activity` | Determine whether work is progressing or stuck. |
| Transaction age / backend xmin | `pg_stat_activity` | Catch long snapshots and horizon-pinning sessions. |
| Slot `xmin`/`catalog_xmin`/`restart_lsn` | `pg_replication_slots` | Detect consumers pinning old tuples or WAL. |
| WAL/archive and storage growth | `pg_stat_archiver`, monitoring systems | Catch archive failures or abnormal storage growth. |
| MultiXact age | `pg_database`, `pg_class`, and `mxid_age()` | Monitor MultiXact wraparound risk separately. |

### 8.2. Tracking XID Age Growth Rate

A single XID age snapshot shows current level; two or more samples over time show consumption velocity. You can approximate the rate:

\[
\text{XID growth rate} =
\frac{\text{age}_{t2} - \text{age}_{t1}}{t2 - t1}
\]

If age grows by millions of transactions per hour, time remaining before hitting the limit may be shorter than expected. Store historical metrics per database and relation, and alert on abnormal growth rates.

### 8.3. Alert Thresholds

A starting policy might include:

- **Warning:** XID age reaches a substantial percentage of `autovacuum_freeze_max_age`, or climbs rapidly across consecutive intervals.
- **High:** age climbs steadily, large relations lack recent autovacuums, workers are constantly saturated, or a slot pins an old `xmin`.
- **Critical:** PostgreSQL logs warnings requiring vacuum within remaining transactions, age nears failsafe threshold, or database headroom is nearly exhausted.

Do not use one fixed percentage threshold for every system. A high-transaction-rate database needs earlier alerts because real wall-clock time to the limit is much shorter. Route PostgreSQL log warnings directly into alerting immediately.

### 8.4. Logging Autovacuum

Enable logging for slow vacuums using:

```conf
log_autovacuum_min_duration = 1s
```

Smaller values give finer visibility at the cost of higher log volume. `0` logs every autovacuum run; `-1` disables threshold-based logging. Choose based on log volume and retention policies. Managed services may expose logs via console or external log export.

Vacuum logs report tuples processed, remaining dead tuples, buffers, and elapsed time. Use them to distinguish productive workers from workers repeatedly canceled or making minimal progress.

## 9. Common Troubleshooting Mistakes

| Wrong Approach | Why It Is Dangerous | Better Approach |
|---|---|---|
| Disabling autovacuum to lower I/O | Dead tuples and XID age can build up to critical levels | Keep autovacuum enabled; tune per table and monitor workers. |
| Looking only at `n_dead_tup` | Does not directly reflect XID age or freeze horizons | Also monitor `age(datfrozenxid)` and `age(relfrozenxid)`. |
| Raising `autovacuum_freeze_max_age` to silence alerts | Only delays vacuuming without fixing why workers fell behind | Find why vacuum lags; never raise limits as a band-aid. |
| Running `VACUUM FULL` on wraparound warning | Acquires exclusive lock, rewrites table, needs extra disk | Prefer controlled `VACUUM (FREEZE)`. |
| Dropping all inactive replication slots | Can break replication/CDC resumption | Verify consumer and rebuild plan before dropping. |
| Killing every long transaction | Can roll back valid business work or break applications | Identify owner, snapshot, and impact, then follow runbook. |
| Maxing out workers and cost limits | Can overload storage and foreground applications | Scale up gradually while monitoring latency and I/O. |
| Vacuuming only one user table | Database age depends on all relations, including catalogs and TOAST | Rank every relation and database. |
| Assuming vacuum ran means XID is safe | Workers may not have finished or may be blocked by a horizon | Re-measure `relfrozenxid`/`datfrozenxid` afterward. |
| Restarting PostgreSQL on wraparound warnings | Restarting does not freeze tuples and extends disruption | Diagnose and execute vacuum per procedure. |

## 10. Reference Runbook for Autovacuum Lag Incidents

This runbook provides an operational framework; adapt it for your major version, privileges, and deployment environment.

### Phase A — Triage

1. Capture warning logs and onset timestamp.
2. Run the XID age query across all databases.
3. Rank relations by `age(relfrozenxid)` and size.
4. Check running workers, phases, and progress speed.
5. Inspect long transactions, prepared transactions, replication slots, and standby feedback.
6. Check `pg_wal`, archives, storage headroom, CPU, and I/O.

### Phase B — Restore Vacuum Capability

1. Close abandoned transactions after confirming with owners.
2. Recover or resolve consumers pinning replication slots.
3. Fix autovacuum or statistics settings if disabled or misconfigured.
4. If necessary, run `VACUUM (FREEZE, VERBOSE)` on the highest-age relations in priority order.
5. Bound parallel job counts and monitor workload impact.
6. On managed PostgreSQL, contact the provider if required privileges are missing or if the service manages anti-wraparound vacuums directly.

### Phase C — Verify

1. Re-measure XID age at both relation and database levels.
2. Confirm wraparound warnings stop appearing.
3. Confirm workers and normal vacuum schedules run cleanly.
4. Check dead tuples, bloat, replication lag, and WAL retention.
5. Watch trends across multiple cycles to confirm XID age does not climb back.
6. Record root cause, corrective actions, and owner.

### Phase D — Prevent Recurrence

1. Add alerts for XID age and consumption velocity per database.
2. Tune scale factors and thresholds on large or write-heavy tables.
3. Tune workers and cost limits around I/O capacity.
4. Enforce application transaction timeouts and boundary rules.
5. Monitor replication slots, prepared transactions, and standby feedback.
6. Audit autovacuum behavior after every upgrade, migration, or workload shift.

## 11. Notes When Operating Managed PostgreSQL

In managed PostgreSQL services, the provider may restrict autovacuum launcher controls, superuser privileges, parameter groups, and certain maintenance tasks. Verify:

- Whether you can view autovacuum logs and `pg_stat_progress_vacuum`.
- Whether you can run manual `VACUUM (FREEZE)`.
- Any caps on workers, cost limits, `autovacuum_freeze_max_age`, or freeze settings.
- Whether the provider runs automated anti-wraparound vacuums or exposes dedicated monitoring alerts.
- How to escalate urgently if transaction ID age climbs rapidly.
- Whether service-managed replication slots are controlled via SQL or only via provider APIs.

Never assume the provider automatically resolves every edge case. Database owners must still track XID age and know escalation paths. If the platform restricts intervening on a stuck worker, provide the vendor with the database name, relation, XID age, logs, long transactions, and slot details for investigation.

## 12. Conclusion

Autovacuum keeps PostgreSQL healthy by reclaiming dead tuples, refreshing statistics, and freezing old transaction IDs. When autovacuum falls behind, investigate write generation rates, long transactions, replication slots, worker capacity, I/O, and per-table configuration together. Transaction ID warnings demand immediate priority because wraparound causes PostgreSQL to stop accepting new XIDs to protect data integrity.

A reliable resolution process starts by measuring `age(datfrozenxid)` and `age(relfrozenxid)`, finding the oldest relations, clearing horizon blockers, restoring vacuum throughput, and running controlled freeze vacuums when needed. Afterward, tune thresholds to workload, monitor XID growth trends, and prevent transactions or slots from pinning snapshots indefinitely. Never disable autovacuum or raise thresholds merely to silence alerts instead of fixing the root cause.

## References

- [PostgreSQL — Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html)
- [PostgreSQL — Autovacuum Configuration](https://www.postgresql.org/docs/current/runtime-config-autovacuum.html)
- [PostgreSQL — VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html)
- [PostgreSQL — Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html)
- [PostgreSQL — System Catalogs: pg_class](https://www.postgresql.org/docs/current/catalog-pg-class.html)
- [PostgreSQL — System Catalogs: pg_database](https://www.postgresql.org/docs/current/catalog-pg-database.html)
- [PostgreSQL — Replication Slots](https://www.postgresql.org/docs/current/view-pg-replication-slots.html)
