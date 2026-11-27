# Evidence-Based PostgreSQL Maintenance Scheduling Instead of Blind Periodic Jobs

## 1. Why Shouldn't You Run VACUUM Just Because the Clock Struck?

A cron job might run:

```sql
VACUUM (ANALYZE);
```

across the entire database every night. This command is occasionally helpful, yet if it is the sole policy, operations has no idea which tables actually needed maintenance, how far autovacuum has progressed, whether transaction ID age is nearing wraparound thresholds, or whether the job drives up I/O and latency during busy windows.

An OLTP table with constant UPDATE/DELETEs accumulates dead tuples quickly. An append-only table has few dead tuples yet still needs freezing and visibility map updates. A freshly bulk-loaded table needs ANALYZE so the planner sees its new distribution. A table with ample free space may still reuse space cleanly and need no rewrite to shrink files.

**Evidence-based scheduling** means defining objectives, gathering signals, setting workload-appropriate thresholds, choosing the right operation, and re-measuring outcomes. Autovacuum remains the primary automatic line of defense; manual schedules supplement it for controlled interventions.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish VACUUM, ANALYZE, autovacuum, anti-wraparound vacuum, VACUUM FULL, and REINDEX.
2. Understand autovacuum/analyze thresholds and the effects of table size, churn, and insert rate.
3. Identify tables needing maintenance from dead tuple estimates, modifications, sizes, and vacuum history.
4. Track transaction ID age and MultiXact age to prioritize freezing.
5. Detect long-running transactions and replication slots delaying cleanup.
6. Observe vacuum progress, wait events, lock blockers, and autovacuum logs.
7. Separate the need to reuse free space from the need to reclaim filesystem space.
8. Tune autovacuum per table with evidence instead of forcing one setting across every table.
9. Build maintenance schedules aligned with workloads, partition lifecycles, and recovery time.
10. Design runbooks with triggers, actions, verification, and guardrails.
11. Avoid running `VACUUM FULL` via cron or disabling autovacuum to save I/O.
12. Re-measure outcomes after changing maintenance policies.

---

## 2. What Does VACUUM Do and Not Do?

PostgreSQL uses MVCC to keep multiple tuple versions. On UPDATE or DELETE, old tuples do not necessarily vanish immediately. Once no active transaction or snapshot needs the old version, VACUUM can reclaim that space for PostgreSQL to reuse.

```text
INSERT / UPDATE / DELETE
          |
          v
Tuple versions accumulate on heap
          |
          v
Old tuple still needed by a snapshot?
          |
          +-- Yes -> cannot safely reclaim yet
          |
          +-- No  -> VACUUM/pruning can clean up
                         |
                         +-- update free-space metadata
                         +-- visibility/freeze metadata
                         +-- index cleanup where appropriate
```

Standard VACUUM can:

- Reclaim unneeded tuple versions.
- Mark space for reuse inside the relation.
- Update the Free Space Map (FSM).
- Update the Visibility Map (VM) when eligible.
- Perform index cleanup per options and version.
- Freeze old tuples to prevent transaction ID wraparound.

Standard VACUUM does not promise to:

- Rewrite the entire table to pack every page.
- Return all free space to the filesystem.
- Eliminate all index bloat.
- Refresh planner statistics as completely as ANALYZE if only VACUUM runs.
- Reclaim tuples still needed by an old snapshot.
- Fix a bad query plan merely by running repeatedly.

### 2.1. Distinguishing Operations

| Operation | Primary Goal |
|---|---|
| `VACUUM` | Reclaim dead tuples for reuse, maintain FSM/VM, and freeze |
| `ANALYZE` | Sample data to refresh planner statistics |
| `VACUUM (ANALYZE)` | Perform both |
| Autovacuum | Daemon automatically triggering vacuum/analyze by thresholds |
| Anti-wraparound vacuum | Prioritized vacuum to prevent XID/MultiXact wraparound |
| `VACUUM FULL` | Rewrite relation to reclaim filesystem space |
| `REINDEX` | Rebuild indexes |

When reporting, always state exactly which operation ran and why. Never use the word "vacuum" loosely for every maintenance task.

## 3. Three Questions Before Scheduling

**Question 1 — What goal must be achieved?**

- Reclaim dead tuples so pages can be reused?
- Refresh statistics because data shifted substantially?
- Freeze tuples to keep transaction ID age safe?
- Improve index-only scans via the visibility map?
- Reclaim file space because a relation is genuinely bloated?
- Rebuild a problematic index?

**Question 2 — What evidence shows it is needed?**

For example: rapid dead tuple growth, modifications crossing thresholds, high XID age, vacuum lag, falling VM coverage, misestimated query plans, or abnormal storage growth.

**Question 3 — What is the operational impact?**

Know lock modes, I/O, WAL, disk headroom, replication lag, connection pressure, and application latency.

If you cannot answer these three questions, a database-wide cron job usually adds load and log noise without proving it solved anything.

## 4. Autovacuum Is the Default Line of Maintenance

Autovacuum uses a launcher and workers to perform vacuum/analyze when tables meet conditions. Under normal configurations, PostgreSQL maintains most tables automatically without daily manual VACUUM schedules.

Major trigger groups:

- Vacuum driven by UPDATE/DELETE increasing dead tuples.
- Vacuum driven by INSERTs to maintain visibility/freezing in versions supporting insert-vacuum thresholds.
- Autoanalyze when data changes enough relative to existing statistics.
- Vacuum driven by freeze/anti-wraparound thresholds.

Autovacuum does not run blindly by wall clock. It responds to thresholds, statistics, and system state.

### 4.1. Key Parameters

| Parameter | Meaning |
|---|---|
| `autovacuum` | Enables/disables the regular autovacuum daemon |
| `autovacuum_vacuum_threshold` | Minimum dead tuples threshold |
| `autovacuum_vacuum_scale_factor` | Ratio of estimated tuples added to vacuum threshold |
| `autovacuum_vacuum_insert_threshold` | Minimum inserts for insert-triggered vacuum |
| `autovacuum_vacuum_insert_scale_factor` | Proportional part of insert-vacuum threshold |
| `autovacuum_analyze_threshold` | Minimum modifications for analyze |
| `autovacuum_analyze_scale_factor` | Proportional part of analyze threshold |
| `autovacuum_naptime` | Interval launcher sleeps between database checks |
| `autovacuum_max_workers` | Maximum autovacuum workers |
| `autovacuum_work_mem` | Working memory allocated to autovacuum |
| `autovacuum_vacuum_cost_delay` | Cost-based delay for autovacuum |
| `autovacuum_vacuum_cost_limit` | Cost limit for autovacuum |
| `autovacuum_freeze_max_age` | XID age threshold triggering anti-wraparound vacuum |
| `autovacuum_multixact_freeze_max_age` | MultiXact age threshold for corresponding vacuum |

Names, defaults, and details vary by PostgreSQL version. Check your server configuration:

```sql
SELECT
    name,
    setting,
    unit,
    source
FROM pg_settings
WHERE name LIKE 'autovacuum%'
   OR name LIKE 'vacuum_%'
ORDER BY name;
```

### 4.2. Never Disable Autovacuum to Reduce Load Without an Alternative

Disabling autovacuum lets dead tuples, stale stats, and freeze age pile up. PostgreSQL still triggers emergency anti-wraparound vacuum even if regular autovacuum is off, yet relying on emergency safety valves as an operational policy is reckless.

## 5. Autovacuum Thresholds: Fixed Base Plus Ratio

Generally, UPDATE/DELETE vacuum is considered when dead tuples exceed:

```text
vacuum threshold
  = autovacuum_vacuum_threshold
  + autovacuum_vacuum_scale_factor * estimated_tuple_count
```

Autoanalyze uses a similar form:

```text
analyze threshold
  = autovacuum_analyze_threshold
  + autovacuum_analyze_scale_factor * estimated_tuple_count
```

Versions supporting insert-triggered vacuum add a matching insert threshold. Exact formulas—including how estimates and insert scale factors are evaluated—should be verified against documentation for your running server version.

### 5.1. Large Table Example

Suppose an illustrative configuration:

- `autovacuum_vacuum_threshold = 50`
- `autovacuum_vacuum_scale_factor = 0.20`
- Table has 10,000,000 estimated tuples.

Approximate threshold:

```text
50 + 0.20 * 10,000,000
= 2,000,050 dead tuples
```

On a large table, 20% represents millions of dead tuples before triggering. With continuous UPDATE/DELETEs, waiting that long may miss latency or storage targets.

### 5.2. Small Table Example

If a table has 1,000 tuples:

```text
50 + 0.20 * 1,000
= 250 dead tuples
```

Here the fixed threshold outweighs the scale factor. That is why one shared config behaves so differently on small vs. large tables.

### 5.3. Scale Factor Is Not a Time Schedule

`autovacuum_vacuum_scale_factor = 0.05` does not mean vacuum runs every 5% of elapsed time or every 5% of disk capacity. It is a term in the estimated-tuple count threshold.

### 5.4. Thresholds Are Only One Signal

Autovacuum is also governed by worker availability, cost delays, locks, table state, and freeze conditions. Crossing a threshold does not guarantee a worker starts that exact second.

## 6. Insert-Heavy Tables Also Need Vacuum

An insert-only table with almost no UPDATE/DELETEs may have few dead tuples, yet still needs vacuuming to:

- Freeze aging tuples.
- Update the Visibility Map to help index-only scans.
- Curb transaction ID age risk.
- Maintain page lifecycle health.

Modern PostgreSQL versions include insert-vacuum thresholds. Never conclude "append-only tables don't need vacuum".

### 6.1. When Is Insert-Vacuum Especially Helpful?

A huge append-only table queried via index-only scans benefits once pages settle and become all-visible. Vacuum lets the VM reflect that state when snapshot conditions permit.

### 6.2. Do Not Confuse Insert Rate with Dead Tuple Count

A table can have few dead tuples while holding many new pages that are not yet all-visible or frozen. Track insert churn, VM coverage, freeze age, and index-only scan heap fetches rather than looking solely at `n_dead_tup`.

## 7. Analyze Must Also Follow Data Changes

The planner relies on statistics to estimate row counts, selectivity, distinct values, and data distributions. Stale stats lead to poor join strategies, scan methods, or cardinality estimates.

Autoanalyze normally triggers based on modifications since the last analyze against its threshold.

### 7.1. Signs ANALYZE Is Needed

- A table recently absorbed a large data load.
- Value distributions shifted substantially.
- Query plan estimated rows diverge widely from actual rows.
- A partition was just loaded or attached.
- Query latency jumped after a batch import.
- Columns with high correlation or skew lack representative stats.

### 7.2. ANALYZE Is Not VACUUM

```sql
ANALYZE public.orders;
```

This updates statistics; it does not clean dead tuples or reclaim relation storage.

### 7.3. Statistics Target for Skewed Columns

If a column is heavily skewed, consider raising its statistics target:

```sql
ALTER TABLE public.orders
ALTER COLUMN status SET STATISTICS 500;

ANALYZE public.orders (status);
```

A higher target collects finer-grained stats at higher sampling and metadata cost. Adjust only when query evidence shows planner misestimates.

### 7.4. Special Care for Partitioned Tables

Autovacuum does not automatically handle all partitioned parent statistics the way many expect. After loading or attaching data in partitions, you may need to run `ANALYZE` on the parent to refresh inheritance/partition-level planner statistics depending on version and structure.

## 8. Evidence 1: Dead Tuple Estimates and Table Churn

`pg_stat_user_tables` is a helpful starting point:

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    n_mod_since_analyze,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_tup_hot_upd,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
```

Available columns can differ by version; check your current view definition before adding queries to long-term monitoring.

### 8.1. Dead Percentage Is Only an Indicator

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
    ) AS estimated_dead_percent
FROM pg_stat_user_tables
ORDER BY estimated_dead_percent DESC NULLS LAST;
```

`n_live_tup` and `n_dead_tup` are estimates. Never treat a fixed 10% or 20% ratio as an absolute trigger across every table.

### 8.2. Watch the Growth Rate

A table holding steady at 100,000 dead tuples may be far less urgent than one jumping from 10,000 to 500,000 in 15 minutes.

Store periodic metric snapshots to compute:

```text
dead tuple growth rate
  = (dead_tuples_now - dead_tuples_previous)
    / elapsed_time
```

Also track `n_tup_upd`/`n_tup_del`, table sizes, and autovacuum timestamps.

### 8.3. Stats Can Reset

Statistics can reset on server restarts, manual stats resets, or administrative actions. Reading a single snapshot without knowing when stats last reset can distort churn estimates.

## 9. Evidence 2: Table Size and Storage Growth

Measure main, table, index, and total sizes separately:

```sql
SELECT
    schemaname,
    relname,
    pg_size_pretty(pg_relation_size(relid)) AS main_fork_size,
    pg_size_pretty(pg_table_size(relid)) AS table_size,
    pg_size_pretty(pg_indexes_size(relid)) AS indexes_size,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 30;
```

### 9.1. Main Fork Is Not the Entire Footprint

`pg_relation_size` measures the main fork by default. `pg_table_size` adds table-associated storage such as TOAST and auxiliary forks. `pg_indexes_size` measures indexes. `pg_total_relation_size` combines table and indexes per function semantics.

Never add overlapping size columns together to fabricate an inflated sum.

### 9.2. Size Growth Does Not Guarantee Bloat

A table growing from 10 GB to 12 GB might simply hold more live data. Compare against row count, tuple width, insert/update rates, dead tuples, and TOAST/index growth.

### 9.3. Free Space Can Be a Reusable Asset

VACUUM makes free space available for subsequent INSERT/UPDATEs. Not every empty page needs to be reclaimed back to the filesystem.

## 10. Evidence 3: Transaction ID Age and Freeze Horizon

PostgreSQL uses finite transaction IDs. VACUUM must freeze old tuples before wraparound threatens visibility correctness.

Check database-level age:

```sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age,
    current_setting('autovacuum_freeze_max_age')::bigint
        AS configured_freeze_max_age
FROM pg_database
ORDER BY xid_age DESC;
```

### 10.1. Age Is Not Calendar Days

`age(datfrozenxid)` measures transaction ID distance, not how many days the database has been running. Growth speed depends on transaction throughput.

### 10.2. Relation Level

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind,
    age(c.relfrozenxid) AS xid_age,
    c.relminmxid
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm', 't')
ORDER BY xid_age DESC
LIMIT 30;
```

Adjust queries for your version/catalogs and include TOAST relations. Use this to spot high-XID-age relations, not as a replacement for cluster wraparound dashboards.

### 10.3. MultiXact Age Also Matters

MultiXacts are used when multiple transactions lock the same tuple concurrently. PostgreSQL maintains separate MultiXact freeze thresholds. Track `datminmxid`/`relminmxid` and ages with version-appropriate functions and columns.

### 10.4. Freeze Age Is a High-Priority Signal

When XID/MultiXact age nears configured limits, anti-wraparound maintenance outweighs short-term latency preferences. Never wait for a high dead tuple percentage before addressing freezing.

## 11. Anti-Wraparound Vacuum Is Not an Optional Maintenance Schedule

Autovacuum runs priority vacuuming to prevent wraparound once transaction ID age hits thresholds. This is a database correctness safeguard.

Related parameters include:

- `autovacuum_freeze_max_age`.
- `autovacuum_multixact_freeze_max_age`.
- `vacuum_freeze_min_age`.
- `vacuum_freeze_table_age`.
- `vacuum_multixact_freeze_min_age`.
- `vacuum_multixact_freeze_table_age`.

Defaults and parameter interactions vary by version. Check `pg_settings` rather than copying settings from an outdated article.

### 11.1. Why Track Anti-Wraparound Separately?

A table with almost zero UPDATE/DELETEs can still carry very old tuples. Conversely, a high-churn table with many dead tuples might have a low XID age. The two problems require separate signals.

### 11.2. When Must It Take Immediate Priority?

- XID age climbs fast toward freeze max age.
- Logs emit wraparound warnings.
- Anti-wraparound autovacuum fails to finish or is blocked.
- Relations hold very old `relfrozenxid` values.
- The database nears write-refusal wraparound protection.

### 11.3. Never Disable Autovacuum to Fix Load

If autovacuum drives up I/O, tune cost/workers/scheduling based on measurements. Turning it off turns a tunable load problem into a wraparound outage.

## 12. Evidence 4: Long-Running Transactions and the xmin Horizon

A transaction holding an old snapshot prevents VACUUM from removing tuple versions that transaction still needs.

Find old transactions:

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    now() - xact_start AS transaction_age,
    now() - query_start AS query_age,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 250) AS query_excerpt
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

### 12.1. Do Not Search Only for Active Queries

An `idle in transaction` session keeps a transaction open without executing queries. This is a prime suspect whenever vacuum fails to reclaim tuples.

### 12.2. Backend xmin

`backend_xmin` reveals a backend's snapshot horizon. NULL does not automatically prove the session has zero impact; check `state`, `xact_start`, and transaction context together.

### 12.3. Never Terminate a Session Purely Because It Is Old

A long transaction might be a legitimate batch job. Confirm owner, query, locks, business impact, and rollback cost before terminating.

### 12.4. Application-Side Controls

- Never hold transactions open across remote API calls or user input.
- Ensure exception paths always roll back/close transactions.
- Configure appropriate timeouts.
- Monitor connection pools and `idle in transaction` counts.
- Verify test frameworks do not leave transactions open indefinitely.

## 13. Evidence 5: Replication Slots and the Cleanup Horizon

Replication slots retain WAL and in some cases retain `xmin`/`catalog_xmin`, delaying reclamation of tuple and catalog versions.

Check:

```sql
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
```

### 13.1. Inactive Slots Are Not Automatically Harmless

An inactive slot still holding `restart_lsn`/`xmin` retains resources indefinitely. Confirm whether its consumer is still in use.

### 13.2. Never Drop Slots Reflexively to "Unblock Vacuum"

Dropping a replication slot can prevent a consumer from resuming from its old position and force a full resync/rebuild. Confirm owner, retention, and recovery plan first.

### 13.3. WAL Retention and Vacuum Retention Are Related Yet Distinct

Slots retain WAL via `restart_lsn`; `xmin`/`catalog_xmin` pin the cleanup horizon. Inspect each column individually rather than concluding from a single metric.

## 14. Evidence 6: Is Vacuum Running and Which Phase Is It In?

`pg_stat_progress_vacuum` reports active vacuum progress:

```sql
SELECT
    pid,
    relid::regclass AS relation_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed,
    index_vacuum_count,
    num_dead_tuples,
    max_dead_tuples
FROM pg_stat_progress_vacuum
ORDER BY pid;
```

Columns and phases can vary by PostgreSQL version; inspect the view on your running server.

### 14.1. Progress Phases Distinguish Work

Phases can include:

- Scanning heap.
- Vacuuming indexes.
- Vacuuming heap.
- Cleaning up indexes.
- Truncating heap.
- Performing final cleanup.

Exact phase names depend on version.

### 14.2. Progress Ratio Is Not an Exact ETA

`heap_blks_scanned / heap_blks_total` shows heap block scan progress. Remaining wall-clock time still depends on index cleanup, I/O, cost delays, lock waits, and skipped pages.

### 14.3. Concurrent Vacuums Can Compete

Worker slots, storage throughput, and query workloads are all bounded. Adding workers will not reduce total runtime if the bottleneck is disk I/O or CPU.

## 15. Evidence 7: Lock Waits and Blockers

Standard VACUUM runs concurrently with most reads/writes, yet can still wait on locks or conflict with DDL/other maintenance.

Find blocked sessions:

```sql
SELECT
    a.pid,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blocking_pids,
    now() - a.query_start AS query_age,
    left(a.query, 200) AS query_excerpt
FROM pg_stat_activity AS a
WHERE cardinality(pg_blocking_pids(a.pid)) > 0
ORDER BY a.query_start;
```

### 15.1. VACUUM FULL Takes Strong Locks

`VACUUM FULL` rewrites the relation and normally requires an `ACCESS EXCLUSIVE` lock, blocking SELECT/DML on the table during the rewrite.

### 15.2. Standard VACUUM Can Still Feel DDL Impact

`ALTER TABLE`, `DROP`/rewrites, and other maintenance can conflict on locks. Never schedule vacuuming without checking migration and DDL windows.

### 15.3. Do Not Confuse Lock Waits with Cost-Throttled Slowness

A worker can run slowly due to cost delays/I/O even with zero lock blockers. Check wait events, progress views, and logs to distinguish them.

## 16. Evidence 8: Autovacuum Logs

You can configure:

```conf
log_autovacuum_min_duration = '1s'
```

This example logs autovacuum runs exceeding the duration threshold. `0` logs all runs while `-1` disables logging via this parameter; confirm exact syntax/version and log volume before enabling.

Logs reveal:

- Which table was vacuumed/analyzed.
- Pages scanned/vacuumed.
- Dead tuples removed.
- Index cleanup and timing.
- Buffer and cost throttling details.
- Vacuums skipped or incomplete under certain conditions.
- Per-phase/operation timings per version format.

### 16.1. Log Volume Has a Cost

Logging every autovacuum on a large database generates high event volume. Use duration thresholds, sampling, or focused logging on critical tables.

### 16.2. Correlate Logs with Relation Identity

Schema/table name, database, PID, duration, and timestamp tie logs back to metrics. Never read a single log line and declare the whole cluster healthy.

## 17. Evidence 9: Query Performance and the Visibility Map

Vacuum improves index-only scan efficiency when pages become all-visible. Check with:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM public.orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 20;
```

If the plan shows an `Index Only Scan`, inspect `Heap Fetches`.

### 17.1. High Heap Fetches Can Be a Signal

An index-only plan incurring heavy heap fetches may point to pages not yet marked all-visible. Also consider query selectivity, update churn, and vacuum history.

### 17.2. Vacuum Does Not Fix Index Design

If queries select columns absent from the index, the planner visits the heap. If predicates/sorts do not match the index, vacuum cannot substitute for proper index design.

### 17.3. Do Not Vacuum Constantly Just to Hit Zero Heap Fetches

The VM changes with workloads; UPDATEs clear visibility bits. Balance index-only scan benefits against vacuum cost and write traffic.

## 18. Consolidated Evidence Matrix

| Signal | Observation Source | Question to Answer |
|---|---|---|
| Dead tuple estimate | `pg_stat_user_tables` | Is it climbing fast or crossing reasonable bounds? |
| Modification count | `n_mod_since_analyze` | Are planner statistics stale? |
| Insert/update/delete rate | Table stats or telemetry | Which type of churn drives pressure? |
| Table/index/TOAST size | Relation size functions | Which component is growing? |
| XID age | `pg_database`, `age()` | Is there wraparound risk? |
| MultiXact age | `datminmxid`, `relminmxid` | Does MultiXact need freezing? |
| Long transactions | `pg_stat_activity` | Is a snapshot pinning the cleanup horizon? |
| Replication slots | `pg_replication_slots` | Is a slot pinning `xmin` or WAL? |
| Vacuum progress | `pg_stat_progress_vacuum` | What is the worker doing and how far along? |
| Lock blockers | `pg_blocking_pids`, `pg_locks` | Is a session blocking maintenance? |
| Autovacuum history | Table stats, logs | Is the table maintained regularly? |
| Index-only heap fetches | `EXPLAIN (ANALYZE, BUFFERS)` | Is the VM assisting queries? |
| Disk/I/O pressure | OS/cloud metrics | Will maintenance overload storage? |
| Replication lag | Replication monitoring | Is WAL/maintenance impacting replicas? |
| Application latency | APM/metrics | Is user-facing latency rising? |

Never decide on a table rewrite from a single isolated metric.

## 19. Build Thresholds from Baselines, Not Someone Else's Numbers

One organization might alert at 10% dead tuples, yet that number is not a universal PostgreSQL standard.

How to establish baselines:

1. Collect per-table metrics over a representative window.
2. Capture peak and off-peak workload profiles.
3. Measure dead tuple and table size growth rates.
4. Observe autovacuum duration, frequency, and completion.
5. Measure query latency, index-only scans, and disk I/O.
6. Compare before and after vacuum/analyze runs.
7. Identify the backlog level at which applications still meet SLOs.
8. Set warning/critical thresholds matching risk and response time.
9. Tailor thresholds per table group.
10. Review after traffic, schema, or version changes.

### 19.1. Use Multi-Tier Alerting

Illustrative policy example:

| Level | Signal | Response |
|---|---|---|
| Info | Autovacuum finishes within baseline | Record, no intervention |
| Warning | Dead tuple growth rises, vacuum lag extends | Investigate churn, workers, cost |
| Critical | Freeze age nears limit or anti-wraparound fails to finish | Immediate priority response |
| Capacity | Table/TOAST/index growth exceeds forecast | Break down storage components |
| Performance | Stale planner stats or abnormal heap fetch rise | Run ANALYZE / check VM and query plans |

Tiers are illustrative; set concrete thresholds from XID burn rates, workloads, and response capacity.

### 19.2. Thresholds Need Persistence Windows

Brief spikes may require no action. Use duration/persistence windows to cut false alarms, except on urgent wraparound signals.

### 19.3. Calculate XID Budget Burn Rate

If XID age is 100 million and climbs 2 million per day, project time to threshold so you have time to act. Never wait for one static magic number before paging on-call.

## 20. Group Workloads and Differentiate Policies

Never apply one vacuum threshold to all tables. Group them:

| Table Group | Characteristics | Priority Evidence |
|---|---|---|
| Hot OLTP | Heavy UPDATE/DELETE | Dead tuple growth, vacuum lag, locks/I/O |
| Append-only events | Heavy INSERT, minimal updates | Insert vacuum, freeze age, VM |
| Large history | Huge, rarely modified | Freeze horizon, partition lifecycle |
| Queue/work tables | Rapid INSERT/DELETE | Churn, dead tuples, index bloat |
| Reference tables | Small, rarely modified | Analyze on load/migration |
| Partitioned fact tables | Many partitions | Per-partition churn, parent ANALYZE |
| TOAST-heavy documents | Large payloads | TOAST size, update patterns, I/O |
| Materialized views | Scheduled refreshes | Analyze after refresh, size/locks |

### 20.1. Hot OLTP Tables

May need lower scale factors to trigger autovacuum earlier, sufficient cost limits, and tight latency monitoring.

### 20.2. Append-Only Tables

Monitor insert-triggered vacuum and freeze age. Looking only at `n_dead_tup` misses VM and freeze needs.

### 20.3. Queue Tables

Queues with continuous INSERT/DELETEs generate heavy churn. Consider partitioning/retention, batching, and index design alongside autovacuum.

### 20.4. History Tables

Time partitioning lets you drop/detach old partitions faster than deleting millions of rows, depending on retention rules. Each partition still needs analyze/freezing per its lifecycle.

## 21. Per-Table Autovacuum Tuning

PostgreSQL supports per-table storage parameters, for example:

```sql
ALTER TABLE public.orders SET (
    autovacuum_vacuum_threshold = 5000,
    autovacuum_vacuum_scale_factor = 0.02,
    autovacuum_analyze_threshold = 5000,
    autovacuum_analyze_scale_factor = 0.01
);
```

These numbers are illustrative examples only, not universal defaults. Compute thresholds from row estimates, churn, and actual vacuum duration.

### 21.1. Why Can Lower Scale Factors Help?

Large tables can accumulate too many dead tuples before hitting default thresholds. Lowering scale factor triggers earlier.

### 21.2. Why Do Fixed Thresholds Still Matter?

On tiny tables, fixed thresholds dominate. Setting thresholds too low makes vacuum/analyze fire excessively often.

### 21.3. Do Not Lower Thresholds on Every Table Simultaneously

If thousands of tables cross thresholds together, the worker pool saturates. Tune by table group while watching queues and durations.

### 21.4. Confirm reloptions After Changes

```sql
SELECT
    c.oid::regclass AS relation,
    c.reloptions
FROM pg_class AS c
WHERE c.oid = 'public.orders'::regclass;
```

This verifies stored relation configuration; it does not prove vacuum ran or thresholds were met.

## 22. Cost-Based Vacuum Delay: Pacing I/O

VACUUM uses cost-based delays to avoid hogging resources. Related parameters include:

- `vacuum_cost_delay`.
- `vacuum_cost_limit`.
- `autovacuum_vacuum_cost_delay`.
- `autovacuum_vacuum_cost_limit`.
- `vacuum_cost_page_hit`.
- `vacuum_cost_page_miss`.
- `vacuum_cost_page_dirty`.

### 22.1. Low Cost Limit

Vacuum yields resources more generously, but runs longer and lets dead tuples linger longer.

### 22.2. High Cost Limit or Low Delay

Vacuum completes faster in some workloads, yet competes harder for I/O and CPU against applications and replication.

### 22.3. Cost Limit and Multiple Workers

When multiple autovacuum workers run concurrently, the cost budget can be shared per version mechanics. Never multiply worker count by cost limit assuming fixed aggregate I/O; verify version docs and measure.

### 22.4. Do Not Optimize Duration in Isolation

Balance dead tuple backlogs, query latency, disk throughput, replication lag, XID age, and vacuum completion time. A 30-minute vacuum can be completely fine on a huge table if SLOs stay intact.

## 23. Workers and Capacity Planning

Parameters:

- `autovacuum_max_workers`.
- `autovacuum_naptime`.
- `autovacuum_work_mem`.
- `autovacuum_vacuum_cost_limit`.
- `autovacuum_vacuum_cost_delay`.

### 23.1. When to Increase Workers?

When evidence shows multiple tables waiting for autovacuum, workers stay constantly busy, and storage/CPU headroom remains.

### 23.2. Do Not Add Workers When Disk Is Saturated

More workers lengthen I/O queues and slow down user queries.

### 23.3. Memory for Dead Tuple Tracking

Tables with massive dead tuples and indexes need memory during vacuum. Insufficient memory forces multiple index cleanup cycles. Watch logs/progress and size `autovacuum_work_mem` within total RAM and worker budgets.

### 23.4. Capacity Is More Than Worker Count

Factor in relation count, churn, index count, table sizes, storage throughput, WAL/replication, and maintenance windows.

## 24. Partitioning and Maintenance Scheduling

Partitioning changes how maintenance is scheduled:

- Older partitions may be nearly read-only.
- Current partitions face heavy churn.
- Newly bulk-loaded partitions need ANALYZE.
- Expired partitions can be detached/dropped per retention instead of row-by-row DELETEs.
- Partitioned parents may need manual ANALYZE so the planner has aggregate statistics.

### 24.1. Parent and Child Tables

```sql
SELECT
    inhparent::regclass AS parent_table,
    inhrelid::regclass AS partition_table
FROM pg_inherits
WHERE inhparent = 'public.events'::regclass
ORDER BY inhrelid::regclass::text;
```

Each partition is an independent relation with its own size, statistics, `reloptions`, and maintenance state.

### 24.2. Loading New Partitions

After a bulk load, run ANALYZE on the partition and/or parent per planner needs. Never assume autovacuum refreshed all stats the moment a partition was attached.

### 24.3. Retention via DROP/DETACH

Dropping partitions is faster than deleting many rows and vacuuming afterward, though evaluate DDL locks, foreign key dependencies, replication, backup/retention, and concurrent queries.

### 24.4. Old Partitions Still Need Freezing

Read-only does not exempt a partition from XID maintenance. Track age on old partitions and their TOAST relations.

## 25. Maintenance Schedules Should Combine Trigger Types

A practical operational schedule blends:

1. Continuous autovacuum: handles routine thresholds.
2. Metric scrapes: collect table stats, XID age, progress, and blockers.
3. Event-triggered manual VACUUM: when backlogs or lag breach policy.
4. Event-triggered ANALYZE: after bulk loads or data distribution shifts.
5. Freeze-priority maintenance: driven by XID/MultiXact horizons.
6. Capacity reviews: inspect table/index/TOAST growth.
7. Rewrite/reindex windows: only when evidence warrants and a dedicated plan exists.
8. Post-maintenance verification: confirm objectives were met.

### 25.1. Not Everything Needs a Cron Job

Metrics scrape periodically; autovacuum fires on triggers; manual intervention runs only when specific conditions are met.

### 25.2. Off-Peak Schedules Do Not Override Urgent Triggers

If freeze age hits danger thresholds at 14:00, do not wait until a weekend window just for the calendar. Prioritize by risk, not day of the week.

### 25.3. Schedules Must Account for Completion Time

Vacuuming a 2 TB table can run for hours. Starting too late inside a maintenance window pushes heavy I/O into peak hours. Estimate duration from history and monitor closely.

## 26. Deciding Between VACUUM and VACUUM (ANALYZE)

Use `VACUUM` when evidence points mainly to dead tuples, free-space reuse, freezing, or visibility maintenance.

Use `ANALYZE` when evidence points mainly to stale statistics or bad planner estimates.

Use `VACUUM (ANALYZE)` when both needs coincide and combining them fits.

Targeted example:

```sql
VACUUM (ANALYZE, VERBOSE) public.orders;
```

VACUUM must run outside normal transaction blocks. Do not invoke it inside an application-opened transaction where the server forbids it.

### 26.1. VERBOSE Aids Investigation

Output/logs report pages, tuples, index cleanup, and freeze details depending on version. Use it to capture before/after evidence.

### 26.2. Analyzing Specific Columns

```sql
ANALYZE public.orders (status, customer_id, created_at);
```

This narrows scope when only key columns need refreshed stats; pick columns from actual query patterns.

### 26.3. Do Not Use VACUUM to Fix Unrelated Slow Queries

If a plan picks sequential scan because the table is small, predicates are unselective, or the query returns most rows, vacuuming will not meaningfully alter the outcome.

## 27. When Is VACUUM FREEZE Needed?

`VACUUM FREEZE` or `VACUUM (FREEZE)` forces more aggressive freezing per PostgreSQL semantics. It is not a command to run on every table every night.

Consider it when:

- XID age needs planned reduction.
- A table is transitioning to long-term read-only status.
- Preparing data ahead of a suitable snapshot/backup workflow.
- Specific post-bulk-load freeze maintenance is required.
- Responding to an operational situation per PostgreSQL guidance.

### 27.1. Freezing Does Not Replace Retention

Freezing does not delete data and does not shrink relations.

### 27.2. Freezing Still Respects Snapshot Horizons

Old transactions/snapshots still restrict which tuples can be frozen or reclaimed in a run.

### 27.3. Do Not Overuse FREEZE for Cosmetic Numbers

Track XID/MultiXact age and vacuum results. Aggressive freezing generates heavy I/O; schedule based on risk and workload.

## 28. When Should You Finally Consider VACUUM FULL?

`VACUUM FULL` rewrites the relation to return space to the filesystem. Consider it only when:

- Evidence proves the relation holds huge free/dead space that workloads cannot effectively reuse.
- Real disk pressure requires space reclamation.
- Sufficient temporary disk exists for the rewrite.
- A maintenance window is approved and strong locking is acceptable.
- Long transactions, replication, and downstream impacts have been evaluated.
- Backups/restore and failure recovery plans are ready.

Example:

```sql
VACUUM FULL public.orders;
```

### 28.1. Lock Impact

`VACUUM FULL` requires an `ACCESS EXCLUSIVE` lock, blocking all other access to the relation during the rewrite.

### 28.2. Temporary Disk Space

Rewriting creates a full new copy before removing the old one. A nearly full filesystem risks command failure or cluster outages.

### 28.3. WAL and Replication

Rewrites generate substantial I/O and WAL, affecting replication and storage. Size and plan using actual relation footprints.

### 28.4. VACUUM FULL Must Never Be a Routine Cron Job

If you need `VACUUM FULL` every week, investigate autovacuum threshold/worker lag, long transactions, replication slots, UPDATE patterns/HOT ratios, schema/partitioning/retention, index bloat, and real storage growth.

### 28.5. Online Rewrite Tools

Some teams use tools/extensions like `pg_repack` to shorten exclusive lock windows compared to `VACUUM FULL`, yet these have their own prerequisites, trigger/temporary storage overhead, and trade-offs. Never treat them as zero-cost core commands requiring no testing.

## 29. When Is REINDEX Needed?

`REINDEX` rebuilds indexes. It is not a substitute for heap VACUUM.

Evidence can include:

- Index size growing disproportionately relative to heap/row count.
- Index-specific bloat confirmed by appropriate tools.
- Confirmed index corruption or invalid index states.
- Delete/update patterns leaving index entries uncleaned as expected.
- Query plans/index performance isolating an index issue after ruling out other causes.

### 29.1. Inspecting Index Sizes

```sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY pg_relation_size(indexrelid) DESC
LIMIT 30;
```

A large index is not automatically bloated; it may simply cover wide keys, `INCLUDE` columns, or large datasets.

### 29.2. REINDEX CONCURRENTLY

On supported versions, consider:

```sql
REINDEX INDEX CONCURRENTLY public.idx_orders_customer;
```

It has trade-offs, multiple phases, and cannot run inside a normal transaction block. Verify version docs and monitor disk and locks.

### 29.3. Index Cleanup Inside VACUUM

Standard VACUUM cleans up dead index entries during index cleanup. Even so, it does not cure every form of index fragmentation or bloat.

## 30. Avoid Running the Entire Database on a Rigid Cycle

A job like:

```text
Every Sunday 02:00:
  VACUUM FULL every table
  REINDEX every index
  ANALYZE every table
```

causes massive locks, I/O, and WAL without targeting real needs.

An evidence-based alternative:

```text
Continuous:
  autovacuum + autoanalyze
  scrape stats and XID age

When churn threshold exceeded:
  inspect blockers and run targeted VACUUM

After bulk load / planner drift:
  targeted ANALYZE

When freeze risk rises:
  prioritize anti-wraparound/freeze work

When storage reclaim is proven necessary:
  plan a rewrite/repack window

After every intervention:
  verify metrics and record outcome
```

### 30.1. Rarely Modified Tables Need Less Frequent VACUUM

Still monitor freeze age and visibility/maintenance needs.

### 30.2. High-Churn Tables Need Continuous Autovacuum

Do not wait until an overnight window if backlogs grow rapidly and hurt queries.

### 30.3. "Periodic Runs" Can Still Be Useful

Teams may schedule periodic health checks or post-load analyzes. The difference is targeted operations, baselines, and verification—not blindly rewriting the entire database by the clock.

## 31. Hands-On: Tables-Needing-Attention Dashboard

A consolidated starting query:

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
    s.n_mod_since_analyze,
    s.last_autovacuum,
    s.last_autoanalyze,
    s.autovacuum_count,
    pg_size_pretty(pg_total_relation_size(s.relid)) AS total_size
FROM pg_stat_user_tables AS s
ORDER BY
    s.n_dead_tup DESC,
    pg_total_relation_size(s.relid) DESC
LIMIT 50;
```

### 31.1. How to Read It

- High dead tuples: inspect growth rate, vacuum history, and snapshot horizons.
- High modifications: check analyze freshness and query plans.
- Large size: break down main/TOAST/indexes.
- Low autovacuum count: do not assume the daemon is broken; the table may have low churn or be below threshold.
- Old `last_autovacuum`: weigh `n_dead_tup` and XID age before acting.

### 31.2. Dashboards Are Not Automated Triggers

Never feed the top 50 straight into `VACUUM FULL`. Dashboards provide evidence for DBAs to pick the right action.

## 32. Hands-On: Tracking XID Risk

```sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age,
    current_setting('autovacuum_freeze_max_age')::bigint
        AS freeze_max_age,
    round(
        100.0 * age(datfrozenxid)
        / NULLIF(
            current_setting('autovacuum_freeze_max_age')::bigint,
            0
        ),
        2
    ) AS percent_of_configured_max
FROM pg_database
ORDER BY xid_age DESC;
```

### 32.1. How to Read It

A ratio approaching 100% is an urgent signal relative to configured limits, though consider exact version/database limits and triggers. Never wait until 100% to alert.

### 32.2. Track Trends

Store metrics by minute/hour/day to see:
- Whether age is rising or falling.
- Rate of climb.
- Whether anti-wraparound vacuum keeps up.
- Whether one specific database races toward limits faster than others.

### 32.3. Multi-Database Clusters

Rank every database; an idle or rarely used database can still hold an old `datfrozenxid` and endanger cluster management.

## 33. Hands-On: Finding Active Vacuums and Blocking Transactions

Progress:

```sql
SELECT
    p.pid,
    p.relid::regclass AS relation_name,
    p.phase,
    p.heap_blks_total,
    p.heap_blks_scanned,
    p.heap_blks_vacuumed
FROM pg_stat_progress_vacuum AS p;
```

Long transactions:

```sql
SELECT
    pid,
    application_name,
    usename,
    state,
    now() - xact_start AS xact_age,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_excerpt
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

### 33.1. Correlate by PID

Join PIDs from progress views with `pg_stat_activity` to see `application_name`, `state`, and `wait_event`. Never judge solely from `phase`.

### 33.2. If No Vacuum Progress Appears

Either no vacuum is running right now, or your role lacks privileges to inspect details. Check permissions and query appropriate views.

### 33.3. Finding Replication Slots

```sql
SELECT
    slot_name,
    active,
    xmin,
    catalog_xmin,
    restart_lsn
FROM pg_replication_slots;
```

If a slot holds an old `xmin`, verify the consumer/owner and remediation plan before dropping it.

## 34. Hands-On: Tuning a High-Churn Table

Suppose `public.orders` has 20 million rows, frequent UPDATE/DELETEs, and a rapidly growing dead tuple backlog. After measuring a baseline, a DBA might test an illustrative configuration:

```sql
ALTER TABLE public.orders SET (
    autovacuum_vacuum_threshold = 5000,
    autovacuum_vacuum_scale_factor = 0.02,
    autovacuum_analyze_threshold = 5000,
    autovacuum_analyze_scale_factor = 0.01
);
```

### 34.1. Before the Change

Record dead tuple estimates and growth rates, autovacuum duration/frequency, query p95/p99, disk I/O/queues, XID age, transaction/replication horizons, and index count/sizes.

### 34.2. After the Change

Measure the same metrics under comparable workloads. Targets include lower backlogs, vacuums finishing before impacting queries, stable XID age, negligible latency impact, and explainable storage growth.

### 34.3. If Vacuum Runs Too Often

Thresholds may be too low, worker capacity/cost delays mismatched, or churn higher than assumed. Adjust thresholds based on measurement—never disable autovacuum.

### 34.4. If Vacuum Still Falls Behind

Check blockers, long snapshots, workers, cost throttling, indexes, and storage. Only raise cost limits or worker counts when headroom exists.

## 35. Decision Matrix: Which Evidence Leads to Which Operation?

| Primary Evidence | Action Typically Considered | Reflex to Avoid |
|---|---|---|
| Dead tuples rising, autovacuum lagging | Check horizon/workers; targeted `VACUUM` if needed | Immediate `VACUUM FULL` |
| Heavy modifications, planner estimates off | `ANALYZE` | `REINDEX` |
| XID age near threshold | Prioritize freeze/anti-wraparound vacuum | Waiting for weekend window |
| High MultiXact age | Check MultiXact freezing and vacuum | Looking only at dead tuples |
| Long transaction pinning `xmin` | Handle owner/transaction lifecycle | Running `VACUUM` repeatedly |
| Replication slot pinning `xmin`/WAL | Check consumer/retention | Dropping slot blindly |
| Large main heap yet good free-space reuse | Monitor/reuse | Rewriting just to shrink file |
| Confirmed heap bloat needing reclaim | Plan `VACUUM FULL`/`pg_repack` | Cron `VACUUM FULL` |
| Index-specific bloat/corruption evidence | Targeted `REINDEX` | `VACUUM FULL` for everything |
| Rising index-only scan heap fetches | Inspect VM, update churn, vacuum | Constant `VACUUM` |
| Bulk load / partition attach | `ANALYZE` partition/parent as needed | Waiting for stats to self-heal |
| I/O saturation during autovacuum | Tune cost/workers and workload | Raising workers endlessly |
| Zero autovacuum activity on low-churn table | Continue observing | Assuming daemon is broken |
| Table growth from live data | Capacity planning/partition retention | Calling it bloat |

## 36. Scheduling by Risk and Workload

A complete policy splits across cadences:

### Continuous

- Autovacuum/autoanalyze running.
- Collecting dead tuples, modifications, sizes, and XID age.
- Monitoring long transactions, replication slots, and blockers.
- Alerting when freeze risk or backlogs exceed baselines.

### Data-Event Driven

- After bulk loads: `ANALYZE`.
- After attaching partitions: `ANALYZE` parent/partition as needed.
- After migrations shifting distributions: `ANALYZE`.
- After heavy delete/update waves: watch VACUUM and storage.
- After restores/upgrades: inspect statistics and maintenance state.

### Maintenance Windows

- Review bloat and storage capacity.
- Execute `REINDEX` or rewrites when evidence justifies and plans exist.
- Review table-level autovacuum parameters.
- Audit XID/MultiXact horizons.
- Test restore/replication after major changes.

### Emergency

- XID age nearing danger thresholds.
- Anti-wraparound autovacuum failing to finish.
- Disk nearly full alongside abnormal relation growth.
- Vacuum stalled behind blockers/horizons.
- Corruption or invalid indexes needing recovery plans.

Maintenance windows manage impact; they are never a reason to postpone critical data-integrity risks.

## 37. Evidence-Based Maintenance Runbook

**Step 1 — Capture current state.** Collect table stats, relation sizes, XID age, vacuum progress, activity, locks, slots, and I/O.

**Step 2 — Classify the issue.** Dead tuple backlog, stale planner stats, freeze risk, index bloat, heap bloat, horizon blocker, or disk pressure.

**Step 3 — Identify owner and blast radius.** Which service owns the table? Are peak workloads active? Do replicas/CDC/backups depend on it?

**Step 4 — Pick the smallest sufficient action.** `VACUUM`, `ANALYZE`, threshold tuning, transaction/slot resolution, `REINDEX`, or rewrite backed by evidence.

**Step 5 — Check prerequisites.** Privileges, disk headroom, lock impacts, WAL/replication, maintenance windows, and rollback/restore plans.

**Step 6 — Execute and monitor.** Watch progress, locks, latency, I/O, replication lag, and logs.

**Step 7 — Verify goals.** Did dead tuple growth, XID age, stats/plans, free-space reuse, and storage move in the right direction?

**Step 8 — Document outcomes.** Record timestamp, relation, before/after evidence, command, duration, warnings, and owner.

## 38. Verification After VACUUM

After targeted vacuuming, inspect:

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
WHERE schemaname = 'public'
  AND relname = 'orders';
```

Pair with:
- `pg_relation_size`/`pg_total_relation_size`.
- `age(relfrozenxid)` or database XID age.
- `pg_stat_progress_vacuum` while running.
- `pg_stat_activity` and `pg_locks`.
- Query plans/`Heap Fetches` if VM was the goal.
- Application latency and I/O.

### 38.1. Do Not Expect Dead Tuples to Always Drop to Zero

Concurrent workloads keep updating and deleting. Stats are estimates, and cleanup remains bounded by snapshot horizons.

### 38.2. Do Not Expect File Size to Shrink After Standard VACUUM

The goal is usually space reuse. If file size holds steady while dead tuples drop and page reuse improves, the run can still be completely successful.

### 38.3. Never Declare Success from Command Exit Code Alone

A completed VACUUM does not prove the root cause is gone: long transactions/replication slots may keep pinning versions, churn may rebuild the backlog, or index bloat may remain.

## 39. Verification After ANALYZE

Check:
- `last_analyze`/`last_autoanalyze`.
- Query plan estimated rows vs. actual rows.
- Join orders and scan strategies.
- Query latency on representative workloads.
- Statistics targets on critical columns.

Example:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM public.orders
WHERE status = 'PENDING';
```

If estimated and actual rows still diverge widely, investigate skew, correlation, extended statistics, or query predicates. Running ANALYZE does not guarantee the planner picks an optimal plan in every scenario.

## 40. Verification After VACUUM FULL or REINDEX

### VACUUM FULL

- Confirm relation size after rewrite.
- Confirm disk headroom was not exhausted.
- Confirm locks released and applications access the table normally.
- Check replication lag and WAL impact.
- Check indexes and query latency after rewrite.
- Confirm backup/recovery readiness if anything went wrong.

### REINDEX

- Confirm indexes are valid and ready in catalogs.
- Check sizes and query plans.
- Verify lock/downtime impact.
- Check unique constraints if any operation failed mid-way.
- Confirm dependent indexes/constraints are intact.

Never treat these two commands as interchangeable maintenance.

## 41. Scheduling Mistakes

### Mistake 1 — Running VACUUM FULL Across the Whole Database Weekly

Generates massive locks and I/O without evidence every table needs a rewrite.

### Mistake 2 — Hourly VACUUM Without Tracking Outcomes

Repeats futile scans while the true culprit is a long-running transaction.

### Mistake 3 — Disabling Autovacuum Because CPU Rose

Lets dead tuples and freeze age accumulate into a far larger crisis.

### Mistake 4 — Watching Only n_dead_tup

Overlooks XID age, insert-vacuum, the visibility map, and statistics.

### Mistake 5 — Watching Only Table Size

Fails to separate live data, TOAST, indexes, and reusable free space.

### Mistake 6 — Applying One Scale Factor to Every Table

Small tables, huge tables, hot OLTP, and append-only tables have very different workloads.

### Mistake 7 — Lowering Thresholds Too Far Cluster-Wide

Triggers massive concurrent vacuum/analyze runs and escalates I/O and worker contention.

### Mistake 8 — Adding Workers Without Checking Storage Headroom

More workers worsen disk saturation.

### Mistake 9 — Vacuuming While Old Transactions Hold the Horizon

Vacuum runs yet cannot reclaim the needed tuples.

### Mistake 10 — Dropping Replication Slots to Speed Up Vacuum

Breaks replication consumers and forces resyncs.

### Mistake 11 — Labeling Every Storage Increase as Bloat

Live data growth, index/TOAST growth, and retention policies can be completely legitimate.

### Mistake 12 — Running ANALYZE and Concluding Dead Tuples Were Cleaned

ANALYZE only updates statistics.

### Mistake 13 — Running REINDEX to Cure Heap Bloat

REINDEX rebuilds indexes, not the heap.

### Mistake 14 — Running VACUUM FULL Without Disk Headroom

Rewrites need extra temporary space and fail dangerously on nearly full disks.

### Mistake 15 — Running VACUUM Inside a Transaction Block

Standard VACUUM cannot run inside explicit transaction blocks. Use an appropriate session/connection mode.

### Mistake 16 — Judging Progress Solely by Elapsed Time

A long vacuum may be advancing steadily; a brief vacuum may be stuck behind a lock. Use progress views and wait events.

### Mistake 17 — Failing to Capture Pre-Maintenance Baselines

Without a baseline, you cannot tell whether latency or storage improved or worsened.

### Mistake 18 — Skipping Post-Maintenance Verification

Command success does not prove operational goals were met.

### Mistake 19 — Forgetting Partitioned Parent Statistics

The planner may use outdated statistics after partition loads or attaches.

### Mistake 20 — Ignoring MultiXact Age

XID age can look fine while MultiXact freeze pressure builds unnoticed.

## 42. Sample Policies for Three Table Groups

The notes below illustrate policy design, not standard PostgreSQL defaults.

| Group | Reference Policy | Deciding Evidence |
|---|---|---|
| `orders` hot OLTP | Lower scale factor than default, track vacuum duration routinely | Update/delete rate, dead tuple growth, p95 |
| `events` append-only | Insert-vacuum/freezing and post-bulk-load analyze | Insert rate, XID age, VM/index-only scans |
| `audit_history` partitioned | Monitor each partition, analyze parent post-load/attach, partition-lifecycle retention | Partition sizes, freeze age, query plans |

### 42.1. Never Apply Policies Without Measuring

A 100-million-row table with 1% churn generates far more dead tuples than a 100,000-row table with 20% churn. Evaluate absolute numbers, rates, and processing cost.

### 42.2. Document the Rationale for Every Override

When setting per-table `reloptions`, record workload patterns, old/new thresholds, evidence, goals, review dates, and owners. This prevents temporary overrides from lingering long after workloads evolve.

## 43. Safe Automation

Automate **metric collection and alerting** long before automating heavy DDL/maintenance.

### 43.1. Low-Risk Automation

- Scrape `pg_stat_user_tables`.
- Scrape XID/MultiXact ages.
- Record vacuum durations and progress.
- Alert when long transactions or slots pin horizons.
- Compute growth rates and forecast threshold crossings.
- Flag tables unanalyzed after bulk loads.

### 43.2. Automation Requiring Guardrails

- Targeted `VACUUM`/`ANALYZE` against an allowlist.
- Versioned per-table `reloptions` policy updates.
- Scheduling eligible maintenance off-peak.
- Concurrency throttling and automatic pause if I/O or latency breaches limits.

### 43.3. Never Automate VACUUM FULL from a Single Metric

A high dead tuple estimate alone never proves a rewrite is needed. Require bloat confirmation, disk need, lock window approval, and storage headroom checks.

### 43.4. Idempotent Schedulers

A maintenance scheduler should:
- Never run duplicate jobs concurrently on the same relation unexpectedly.
- Enforce timeouts and log exit statuses.
- Never swallow errors silently.
- Capture before/after evidence.
- Pause automatically when cluster health is degraded.
- Never alter roles or privileges beyond minimal required scope.

## 44. Sample Operational Schedule

### Every Minute or Few Minutes

- XID age and MultiXact age.
- Autovacuum progress.
- Long-running transactions.
- Replication slot horizons.
- Disk/I/O and replication lag.
- Critical threshold alerts.

### Hourly

- Dead tuple growth snapshots.
- Modification counts and analyze freshness.
- Autovacuum activity and failure logs.
- Pool/DB latency and query workloads.

### Daily

- Review top relations by dead tuple growth and total size.
- Confirm vacuum/analyze completion on critical tables.
- Inspect newly bulk-loaded tables or partitions.
- Review unresolved alerts.

### Weekly or Periodic Review

- Evaluate per-table thresholds, workers, and cost settings.
- Review bloat evidence.
- Check index growth and query plans.
- Audit long transactions and replication slots.
- Plan rewrites/reindexes where evidence justifies.

### Event-Driven

- After restores, upgrades, or bulk loads.
- After schema migrations or partition attaches.
- After traffic or retention policy changes.
- When XID age rises abnormally.
- When vacuum is blocked or disk nears capacity.

This is an observation and review cadence; it does not mean running `VACUUM FULL` or `REINDEX` every day or week.

## 45. Practice Exercises with Answers

### Exercise 1. Is a weekly Sunday cron running `VACUUM FULL` across the whole database a good policy?

**Answer:** No. It triggers rewrites, exclusive locks, and heavy I/O on every table regardless of need. Rely on autovacuum and schedule rewrites only when evidence proves filesystem space must be reclaimed.

### Exercise 2. How do VACUUM and ANALYZE differ?

**Answer:** VACUUM manages dead tuples, free space, and freezing; ANALYZE collects planner statistics.

### Exercise 3. Is `n_dead_tup` an exact count of dead tuples?

**Answer:** No. It is an estimate in the statistics view.

### Exercise 4. A table has 10 million rows, scale factor 0.2, threshold 50; roughly what is the vacuum threshold?

**Answer:** `50 + 0.2 × 10,000,000 = 2,000,050` dead tuples under the general update/delete trigger formula.

### Exercise 5. Does scale factor 0.02 mean vacuum runs every 2 hours?

**Answer:** No. It is a proportion of estimated tuples in the threshold formula, not a time interval.

### Exercise 6. Does an append-only table with zero DELETEs need vacuum?

**Answer:** It can need insert-triggered vacuum, freezing, and VM updates; low dead tuples do not mean zero maintenance.

### Exercise 7. After a large bulk load the planner chooses bad plans; what should you check?

**Answer:** Statistics freshness and running an appropriate ANALYZE, then comparing EXPLAIN estimated vs. actual rows.

### Exercise 8. Does ANALYZE reclaim dead tuples?

**Answer:** No.

### Exercise 9. How is database XID age checked?

```sql
SELECT datname, age(datfrozenxid)
FROM pg_database
ORDER BY age(datfrozenxid) DESC;
```

**Answer:** `age(datfrozenxid)` reports XID age distance at the database level.

### Exercise 10. Is XID age the number of days since the last vacuum?

**Answer:** No. It is a transaction ID distance, not calendar time.

### Exercise 11. If autovacuum is disabled, is anti-wraparound protection still enforced?

**Answer:** PostgreSQL can still launch emergency anti-wraparound vacuum; however, never rely on that in place of regular autovacuum.

### Exercise 12. Can an `idle in transaction` session block VACUUM?

**Answer:** Yes, if it holds an old snapshot/horizon that keeps tuple versions needed.

### Exercise 13. Should you terminate every transaction running over 30 minutes?

**Answer:** No. Identify owner, query, locks, snapshot impact, and business consequences first.

### Exercise 14. Can an inactive replication slot affect cleanup?

**Answer:** Yes. A slot can retain `xmin`/`catalog_xmin` or WAL even while inactive.

### Exercise 15. Is dropping a replication slot safe just to free the vacuum horizon?

**Answer:** Not automatically. It can break replication consumers' ability to resume and force a resync.

### Exercise 16. What does `pg_stat_progress_vacuum` provide?

**Answer:** Tracks relation, phase, and `heap_blks_scanned`/`vacuumed` of running vacuums.

### Exercise 17. Does a vacuum running for 2 hours mean it is hung?

**Answer:** No. Check progress, wait events, I/O, cost throttling, and blockers.

### Exercise 18. What is the trade-off of `log_autovacuum_min_duration = 0`?

**Answer:** Logs every autovacuum run, useful for investigation, at the cost of potentially huge log volume.

### Exercise 19. Does a heap growing by 20% prove bloat?

**Answer:** No. Live data may have grown; separate live/dead data, TOAST, indexes, and free space.

### Exercise 20. Does standard VACUUM return all free space to the filesystem?

**Answer:** No. It mainly makes space reusable; empty trailing pages can be truncated when conditions permit.

### Exercise 21. When should `VACUUM FULL` be used?

**Answer:** When filesystem space reclamation is confirmed necessary, disk headroom exists, `ACCESS EXCLUSIVE` locking is acceptable, and an operational plan is ready.

### Exercise 22. Is `VACUUM FULL` suitable for a daily cron job?

**Answer:** No.

### Exercise 23. Does `REINDEX` clean up heap bloat?

**Answer:** No. It rebuilds indexes.

### Exercise 24. Does a large index size alone prove index bloat?

**Answer:** No. The index may hold many keys/`INCLUDE` columns or serve large data; evaluate against row counts and index-specific evidence.

### Exercise 25. Why do queue tables need dedicated policies?

**Answer:** Heavy INSERT/DELETE churn creates dead tuples and index cleanup pressure; retention, partitioning, and batching also matter.

### Exercise 26. What does high `n_mod_since_analyze` suggest?

**Answer:** Statistics may be stale; inspect query plans and analyze thresholds.

### Exercise 27. Does a newly attached partition require `ANALYZE` on the parent?

**Answer:** It may be needed so the planner has parent statistics; autovacuum does not automatically refresh all partitioned parent stats as expected.

### Exercise 28. Is lowering `autovacuum_vacuum_scale_factor` from 0.2 to 0.02 always better?

**Answer:** No. Vacuum may trigger sooner while raising I/O and worker pressure; measure first.

### Exercise 29. Does adding autovacuum workers always cut vacuum backlogs?

**Answer:** Not if storage/CPU is the bottleneck or workers contend for the same resources.

### Exercise 30. What does a lower cost delay mean?

**Answer:** Vacuum runs more aggressively and yields less time, potentially increasing I/O contention.

### Exercise 31. How does a VM `all-visible` bit help?

**Answer:** Enables index-only scans to skip heap visibility checks when eligible.

### Exercise 32. Should you vacuum constantly to keep Heap Fetches at 0?

**Answer:** No. UPDATEs clear VM bits; balance vacuum cost against workload benefits.

### Exercise 33. Does freezing delete old data?

**Answer:** No. Freezing manages transaction ID visibility, not data retention/deletion.

### Exercise 34. Must MultiXact age be tracked separately?

**Answer:** Yes. MultiXacts have separate freeze thresholds not captured by XID age alone.

### Exercise 35. What does `pg_total_relation_size` measure?

**Answer:** Total table plus associated indexes and TOAST; use other size functions to separate components.

### Exercise 36. When vacuum is slow, what should you inspect first?

**Answer:** Progress, wait events, blockers, cost throttling, long transactions, and replication slots.

### Exercise 37. Can `VACUUM` run inside normal `BEGIN/COMMIT`?

**Answer:** No. `VACUUM` cannot run inside a normal transaction block.

### Exercise 38. After VACUUM, file size stayed the same while dead tuples dropped; was it successful?

**Answer:** It can be successful if the goal was cleanup and internal space reuse; not every vacuum shrinks filesystem files.

### Exercise 39. After ANALYZE, estimated rows are still far off; what do you do?

**Answer:** Check skew, statistics targets, extended statistics, predicates, and query plans; ANALYZE does not guarantee accurate estimates in every case.

### Exercise 40. Pick an action for a table with rising dead tuples, normal XID age, and a transaction holding `xmin` for hours.

**Answer:** Investigate the transaction owner/horizon and fix the cause; run targeted vacuum once the cleanup horizon opens up. Repeatedly running vacuum while the horizon stays pinned will not clear the backlog.

### Exercise 41. Pick an action for a huge insert-only table where index-only scans show many heap fetches and freeze age rises.

**Answer:** Review insert-vacuum/freeze policy, VM coverage, and query plans; targeted vacuum can help if conditions allow.

### Exercise 42. Pick an action when only planner statistics are stale after a bulk load.

**Answer:** Run `ANALYZE` on the partition/table as needed; no `VACUUM FULL` is needed.

### Exercise 43. Pick an action when index-specific bloat is confirmed while the heap is healthy.

**Answer:** Evaluate targeted `REINDEX`, possibly `CONCURRENTLY` if supported; do not rewrite the heap needlessly.

### Exercise 44. Pick an action when heap bloat is confirmed, disk is nearly full, and temporary space is insufficient.

**Answer:** Do not start `VACUUM FULL`. Execute capacity planning / free disk headroom and choose a safe rewrite strategy.

### Exercise 45. What must a maintenance job log?

**Answer:** Relation, trigger/evidence, command, start/end/duration, progress, locks, I/O/replication, before/after results, warnings, and owner.

## 46. Pre- and Post-Maintenance Checklist

| Stage | Question |
|---|---|
| Before | Is the goal cleanup, analyze, freeze, or filesystem reclaim? |
| Before | Are concrete evidence and baselines recorded? |
| Before | Is XID/MultiXact age urgent? |
| Before | Are long transactions or replication slots pinning the horizon? |
| Before | Are there blockers or DDL conflicts? |
| Before | Does storage have enough headroom for a rewrite? |
| Before | Do I/O, CPU, and replication have headroom? |
| Before | Are there application SLOs or peak windows to protect? |
| Before | Can the command run outside a transaction block? |
| Before | Are required privileges and extensions ready? |
| During | Are vacuum progress/phases advancing? |
| During | Are lock waits or query latencies rising? |
| During | Are disk/WAL/replication lag breaching guardrails? |
| After | Did dead tuple growth drop? |
| After | Did XID/MultiXact age improve? |
| After | Are planner statistics/estimated rows more accurate? |
| After | How did table/index/TOAST sizes change? |
| After | Did VM/index-only heap fetches improve if that was the goal? |
| After | Are applications and replicas healthy? |
| After | Should threshold/worker/cost policies be adjusted? |
| After | Were results documented with a next review date? |

## 47. Official PostgreSQL Documentation

- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — VACUUM, ANALYZE, autovacuum, and freezing.
- [VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html) — syntax, options, and operational limits.
- [ANALYZE](https://www.postgresql.org/docs/current/sql-analyze.html) — collecting planner statistics.
- [Autovacuum Configuration](https://www.postgresql.org/docs/current/runtime-config-autovacuum.html) — trigger thresholds, workers, freezing, and cost.
- [Vacuum Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html#VACUUM-PROGRESS-REPORTING) — `pg_stat_progress_vacuum`.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — table stats, activity, locks, and database statistics.
- [pg_stat_activity](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-ACTIVITY-VIEW) — transactions and backend state.
- [pg_replication_slots](https://www.postgresql.org/docs/current/view-pg-replication-slots.html) — slot state, `xmin`, and WAL positions.
- [Routine Reindexing](https://www.postgresql.org/docs/current/routine-reindex.html) — when and how to reindex.
- [REINDEX](https://www.postgresql.org/docs/current/sql-reindex.html) — concurrent and non-concurrent reindex operations.
- [Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html) — lifecycle and maintenance of partitioned tables.

Thresholds, view columns, and options vary by PostgreSQL version and distribution. Before applying, verify `server_version`, `pg_settings`, catalogs, and docs for your exact running version.

## 48. Summary: Maintenance Is an Evidence-Based Decision

```text
Observe
   |
   +-- Dead tuples/churn rising?
   |      -> check vacuum triggers, horizon, workers
   |
   +-- Statistics stale?
   |      -> ANALYZE
   |
   +-- XID/MultiXact age climbing?
   |      -> prioritize freeze/anti-wraparound
   |
   +-- Long transaction/replication slot blocking cleanup?
   |      -> resolve horizon first
   |
   +-- Confirmed heap/index bloat?
   |      -> pick targeted VACUUM / REINDEX / rewrite
   |
   +-- After operation?
          -> re-measure, confirm, and record
```

Key principles to remember:

1. **Autovacuum is the routine maintenance line.** Manual schedules supplement concrete needs rather than replacing the daemon.
2. **Dead tuples, stale statistics, and freeze age are three distinct problems.** They demand separate signals and actions.
3. **Autovacuum thresholds depend on tuple counts and scale factors.** One shared setting rarely fits both small and massive tables.
4. **Insert-only tables still need vacuuming.** Freezing and the visibility map remain essential.
5. **Long transactions and replication slots retain tuple versions.** Vacuum running does not mean cleanup reaches its goal.
6. **XID/MultiXact age is a correctness safeguard.** Never wait for high dead tuple percentages before addressing wraparound risk.
7. **Standard VACUUM creates reusable free space.** It does not guarantee smaller files.
8. **`VACUUM FULL` is a costly, locking rewrite.** Use it only when filesystem space reclamation is proven necessary and planned.
9. **`ANALYZE` updates statistics; `REINDEX` rebuilds indexes.** Never misuse either to solve a different class of problem.
10. **Worker/cost tuning trades off backlogs against system load.** Speeding up vacuum can slow primary workloads.
11. **Partition lifecycles are part of maintenance.** Parent analyze, partition freezing, and retention must be designed together.
12. **Every operation requires verification.** Measure before/after across XIDs, dead tuples, plans, storage, locks, and latency.

**One sentence to remember:** *Good VACUUM scheduling is not running the exact same command on the exact same day; it is observing churn, visibility, statistics, transaction horizons, and storage, then choosing the right operation at the right time with measured impact.*
