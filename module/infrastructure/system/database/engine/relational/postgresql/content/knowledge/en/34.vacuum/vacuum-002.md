# Standard VACUUM, VACUUM FULL, and Related Locks

PostgreSQL uses **MVCC (Multi-Version Concurrency Control)**: when a transaction UPDATEs or DELETEs a row, the database typically creates a new version or marks the old version as no longer valid for future snapshots. Old versions (*dead tuples*) cannot be removed immediately if any active transaction/snapshot might still need to see them. Over time, dead tuples occupy space in the heap and can increase index sizes, I/O, and table scan costs.

The **VACUUM** command helps PostgreSQL reclaim tuple versions that are no longer needed, update free space/visibility metadata, and guard against transaction ID wraparound. The **VACUUM FULL** command performs a table rewrite to compact the file and return unused space to the filesystem, but it requires a stronger lock, additional temporary disk space, and can block all access to the table while running.

Both commands contain the word VACUUM, yet they differ significantly in **how they process data, their ability to reclaim disk space, execution duration, and lock mode**. Choosing VACUUM FULL by mistake during peak hours can cause application outages; conversely, running only standard VACUUM when the filesystem is full from table bloat may not free enough space for the operating system.

This lesson belongs to the **VACUUM** chapter of the *Database Engine Relational PostgreSQL* module. The goal is to understand MVCC mechanics, choose the right maintenance command, read lock/progress/maintenance statistics, and handle bloat, autovacuum, and transaction ID wraparound risk.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why UPDATE/DELETE create dead tuples in PostgreSQL.
2. Distinguish tuple visibility from whether physical file space has been freed.
3. State the functions of standard VACUUM, VACUUM FULL, and ANALYZE.
4. Understand the lock modes of standard VACUUM and VACUUM FULL.
5. Know why standard VACUUM usually runs concurrently with SELECT/INSERT/UPDATE/DELETE.
6. Know that VACUUM FULL requires ACCESS EXCLUSIVE and impacts traffic.
7. Distinguish space reused inside a relation from space returned to the operating system.
8. Read VACUUM progress and lock/blocking sessions.
9. Understand autovacuum thresholds, cost settings, and per-table storage parameters.
10. Identify long transactions, replication slots, and standby feedback retaining dead tuples.
11. Understand freezing, XID age, and anti-wraparound mechanisms.
12. Schedule maintenance, evaluate disk capacity, and run restore/maintenance safely.
13. Use views such as pg_stat_user_tables, pg_stat_progress_vacuum, pg_stat_progress_cluster, and pg_locks to observe activity.
14. Practice on a lab table and distinguish the effects of both types of VACUUM.

## 2. Why Does PostgreSQL Need VACUUM?

PostgreSQL uses MVCC so transactions can read data versions matching their snapshots without locking out every reader and writer under exclusive access.

Example of a row:

~~~text
Initially:
  id=10, status='new', xmin=100, xmax=0

Transaction UPDATE:
  old version: xmin=100, xmax=205
  new version: xmin=205, xmax=0

Transaction DELETE:
  current version: xmax=310
~~~

The XID values in this diagram are illustrative only. PostgreSQL uses more complex internal metadata to determine whether a tuple is visible to a specific snapshot.

### 2.1. UPDATE Typically Creates a New Version

An UPDATE does not necessarily overwrite the value directly on the same tuple. PostgreSQL can create a new tuple version and mark the old version as no longer current for future snapshots.

### 2.2. DELETE Marks a Tuple as No Longer Current

DELETE does not necessarily erase bytes from the heap page immediately. It marks the tuple as deleted by a transaction ID so older snapshots can still see it if needed.

### 2.3. Dead Tuple

A tuple version becomes *dead* when no remaining snapshot/transaction is allowed to see it. At that point, VACUUM can reclaim the tuple's slot for reuse.

### 2.4. Why Not Delete Immediately on UPDATE/DELETE?

Another transaction may have started before the modification and still need to read the old version. MVCC keeps the necessary versions until it is safe to reclaim them.

### 2.5. VACUUM Is Not a "Delete Rows" Command

It does not replace DELETE, does not decide which business rows to keep, and does not delete rows that are still visible. It cleans up versions whose lifecycle has ended according to PostgreSQL's visibility rules.

## 3. Heap, Pages, and Dead Tuples

A PostgreSQL table is stored as pages (typically 8 KB in the default build), containing tuple versions and associated metadata.

~~~text
Illustrative heap page
+----------------------------------+
| Page header / line pointers      |
+----------------------------------+
| tuple A: LIVE                    |
| tuple B: DEAD                    |
| tuple C: LIVE                    |
| tuple D: DEAD                    |
| free space                       |
+----------------------------------+
~~~

### 3.1. Dead Tuples Still Consume Space

Before VACUUM reclaims them, dead tuples can continue occupying line pointers/page bytes and contribute to a larger relation than necessary.

### 3.2. Free Space Map

VACUUM updates free space information so PostgreSQL can locate pages with available room when INSERT or UPDATE needs to create a new tuple.

### 3.3. Visibility Map

VACUUM maintains the visibility map, recording pages where all tuples are visible to all current transactions (all-visible) and all-frozen state where appropriate. This metadata enables index-only scans and reduces visibility-checking work.

### 3.4. Indexes Are Also Affected

An UPDATE/DELETE can leave behind dead index entries that need cleanup. VACUUM typically coordinates heap processing and index cleanup according to the engine/version strategy.

### 3.5. TOAST Data

Large values may be stored in a TOAST relation. Reclaiming tuple versions and TOAST chunks must also be managed; do not look solely at the heap table and ignore the rest of the associated storage.

## 4. What Does Standard VACUUM Do?

Basic command:

~~~sql
VACUUM sales.orders;
~~~

Standard VACUUM scans the relation, identifies tuples that are no longer needed, reclaims them for reuse, updates free space/visibility metadata, and performs any required freezing work.

### 4.1. Space Reuse Inside the Relation

Most space freed by standard VACUUM becomes available for new tuples within the same relation. The file does not necessarily shrink on the filesystem.

### 4.2. Can Truncate Empty Pages at the End of the File

If pages at the end of a relation are completely empty and truncation is enabled, VACUUM can truncate that tail to return some space to the operating system. This requires an ACCESS EXCLUSIVE lock during the truncation step; it can be skipped if the lock cannot be acquired depending on version/configuration mechanics.

### 4.3. Truncate Is Not Full-Table Compaction

If empty pages are scattered throughout the middle of the relation, VACUUM normally does not move all tuples to pack them toward the start of the file. As a result, the file can remain large.

### 4.4. Does Not Block DML the Way VACUUM FULL Does

Standard VACUUM acquires a SHARE UPDATE EXCLUSIVE lock on the relation. This lock is compatible with ROW EXCLUSIVE locks from INSERT/UPDATE/DELETE and ACCESS SHARE locks from SELECT, though resource contention and conflicts with certain DDL/maintenance operations still exist.

### 4.5. Can Consume I/O and CPU

Standard VACUUM does not lock out the application completely, yet it still scans pages, reads/writes heap and index blocks, uses CPU, and can contend for I/O with the query workload.

## 5. What Does VACUUM FULL Do?

Command:

~~~sql
VACUUM FULL sales.orders;
~~~

VACUUM FULL writes a compacted copy of the relation containing only the still-needed tuple versions, then swaps the old relation for the new one. Associated indexes are also rebuilt as part of the rewrite process.

### 5.1. Physically Compacts the Relation

Because the data is rewritten, scattered gaps are eliminated and the resulting file size is usually significantly smaller afterward.

### 5.2. Returns Space to the Operating System

Space from the old relation is released after replacement, so the filesystem regains free disk space rather than merely holding free pages inside the relation.

### 5.3. Temporary Space Must Be Sufficient

During the rewrite, the old relation remains on disk while the new relation is constructed. You must provision extra disk space for the new copy and its indexes/auxiliary files, in addition to the existing data.

### 5.4. Requires an ACCESS EXCLUSIVE Lock

VACUUM FULL takes an ACCESS EXCLUSIVE lock on the table and holds it for the duration of the rewrite. This lock blocks SELECT, INSERT, UPDATE, DELETE, and any other relation access requiring a conflicting lock.

### 5.5. Not a Daily Maintenance Command

Because it consumes disk, I/O, and time while blocking access, VACUUM FULL should generally only be used when you genuinely need to compact/reclaim disk space and have a maintenance window/mitigation plan.

## 6. Comparing VACUUM and VACUUM FULL

| Criterion | Standard VACUUM | VACUUM FULL |
|---|---|---|
| Reclaims dead tuples | Yes | Yes, via rewrite |
| Keeps existing relation file | Yes, normally | Rewrites into a new relation |
| Reuses free space | Yes | Yes, relation is compacted |
| Returns space to OS | Usually no; can truncate tail pages | Usually yes after rewrite |
| Main table lock | SHARE UPDATE EXCLUSIVE | ACCESS EXCLUSIVE |
| SELECT while running | Usually allowed | Blocked |
| INSERT/UPDATE/DELETE | Usually allowed | Blocked |
| Rewrites entire heap | No | Yes |
| Rebuilds indexes | Cleans up index entries per VACUUM flow | Indexes are rebuilt with rewrite |
| Temporary disk space | Usually lower | Requires substantial space |
| Duration | Usually fits routine maintenance | Can be very long |
| Purpose | Routine cleanup, reuse, freeze | Aggressive reclaim/compaction |

### 6.1. Choose Standard VACUUM When

- You want routine dead-tuple cleanup.
- The table is actively being read/written by applications.
- You do not need to return most free space to the filesystem immediately.
- Autovacuum has not kept up and manual maintenance is needed.
- You want to update the visibility map/freeze metadata.

### 6.2. Consider VACUUM FULL When

- The table is severely bloated and genuinely needs disk space reclaimed.
- Large amounts of free space are scattered across the heap.
- Sufficient temporary disk space exists to hold both old and new copies during rewrite.
- ACCESS EXCLUSIVE locking and downtime/blocking are acceptable.
- You have identified the cause of bloat and have a plan to prevent recurrence.

### 6.3. Do Not Run FULL Just Because n_dead_tup Is High

Dead tuple count is an estimate and does not by itself tell you the physical bloat ratio. Evaluate relation size, workload, free space, indexes, transaction horizon, and filesystem requirements.

### 6.4. Do Not Run Standard VACUUM Expecting the Filesystem to Definitely Shrink

It primarily makes space reusable internally. If the goal is to return substantial space to the OS, evaluate rewrite/partition lifecycle/alternative compaction strategies.

## 7. Lock Mode of Standard VACUUM

Standard VACUUM takes a **SHARE UPDATE EXCLUSIVE** lock on the processed relation.

### 7.1. This Lock Allows SELECT

Standard SELECT takes ACCESS SHARE, which is compatible with SHARE UPDATE EXCLUSIVE. Readers can continue accessing the table while VACUUM runs.

### 7.2. This Lock Allows Normal DML

INSERT, UPDATE, and DELETE normally take ROW EXCLUSIVE; this lock is compatible with SHARE UPDATE EXCLUSIVE. Writers can continue operating.

### 7.3. It Conflicts with Itself

SHARE UPDATE EXCLUSIVE conflicts with another SHARE UPDATE EXCLUSIVE on the same relation. Thus two VACUUM/ANALYZE runs or certain maintenance operations may have to wait for each other.

### 7.4. Conflicts with DDL/Maintenance

Operations requiring SHARE, SHARE ROW EXCLUSIVE, EXCLUSIVE, or ACCESS EXCLUSIVE may wait on VACUUM. For example, ALTER TABLE operations take strong locks depending on the subcommand.

### 7.5. Do Not Conclude "VACUUM Takes No Locks"

VACUUM does take a lock; the key point is that its lock mode is normally compatible with SELECT/DML traffic. It can still be blocked by a transaction holding a conflicting lock or slow down workloads via I/O.

## 8. Lock Mode of VACUUM FULL

VACUUM FULL uses an **ACCESS EXCLUSIVE** lock.

### 8.1. ACCESS EXCLUSIVE Is the Strongest Lock

It conflicts with every other table-level lock mode, including the ACCESS SHARE lock that SELECT normally needs.

### 8.2. SELECT Can Be Blocked

While VACUUM FULL holds the lock, new SELECTs on the table must wait. Queries already holding locks earlier can make VACUUM FULL wait before starting.

### 8.3. DML Is Blocked

INSERT, UPDATE, and DELETE require conflicting locks; applications can accumulate waiting connections, exhaust pools, and hit timeouts.

### 8.4. Other Queries Can Prolong the Incident

An open long-running transaction holding a relation lock can make VACUUM FULL wait indefinitely. Once VACUUM FULL enters the queue or acquires the lock, new application queries pile up behind it.

### 8.5. Lock Waits Can Create a Queue Effect

A DDL/VACUUM FULL waiting for a strong lock can force subsequent queries to wait depending on queueing/lock manager behavior. Therefore inspect blockers and wait times, not just active running processes.

## 9. Lock Compatibility Table to Remember

A simplified view:

| Held Lock | SELECT (ACCESS SHARE) | DML (ROW EXCLUSIVE) | Standard VACUUM (SHARE UPDATE EXCLUSIVE) | VACUUM FULL (ACCESS EXCLUSIVE) |
|---|---:|---:|---:|---:|
| ACCESS SHARE | Compatible | Compatible | Compatible | Conflict |
| ROW EXCLUSIVE | Compatible | Compatible | Compatible | Conflict |
| SHARE UPDATE EXCLUSIVE | Compatible | Compatible | Conflict | Conflict |
| ACCESS EXCLUSIVE | Conflict | Conflict | Conflict | Conflict |

This table only illustrates the primary lock modes; PostgreSQL has more table lock modes. For specific lock conflicts, consult the official lock matrix for your server version.

### 9.1. ACCESS SHARE

Normal SELECT acquires this lock when accessing a relation.

### 9.2. ROW EXCLUSIVE

INSERT/UPDATE/DELETE typically acquire this lock on the modified table.

### 9.3. SHARE UPDATE EXCLUSIVE

Used by standard VACUUM and certain maintenance/DDL operations. Does not block normal SELECT/DML, but conflicts with maintenance of the same class on the same relation.

### 9.4. ACCESS EXCLUSIVE

Used by VACUUM FULL, many DDL statements, and operations requiring strong exclusivity. It blocks every other table lock mode.

### 9.5. Relation Locks Differ from Row Locks

VACUUM FULL's table-level lock is not the same as row-level locks held by SELECT FOR UPDATE/UPDATE on individual rows. Do not use the two concepts interchangeably when analyzing blocking.

## 10. Why Can VACUUM FULL Cause Downtime?

Suppose table `sales.orders` is receiving traffic:

~~~text
Application SELECT ---- ACCESS SHARE -----+
Application UPDATE ---- ROW EXCLUSIVE ----+--> Table
VACUUM FULL ----------- ACCESS EXCLUSIVE --+
~~~

### 10.1. If Queries Started First

VACUUM FULL must wait for transactions holding conflicting locks on the table to finish. A long-running open transaction can prolong the wait.

### 10.2. If VACUUM FULL Acquires the Lock First

New SELECT/DML statements will wait until it completes and releases ACCESS EXCLUSIVE.

### 10.3. Connection Pools Can Be Exhausted

Many connections waiting on one table can exhaust the pool. Even unrelated endpoints can slow down if they share the same pool.

### 10.4. Timeouts Are Not a Complete Risk Rollback Mechanism

`lock_timeout` can bound how long a session waits for a lock when properly configured; `statement_timeout` can bound statement execution. However, you must plan for the failure consequences and application retry behavior, not just set a timeout and run FULL recklessly.

### 10.5. Maintenance Windows Must Account for Lock Wait Time

Do not estimate only rewrite time. Account for blockers, queues, disk, I/O, index rebuilds, and post-operation verification.

## 11. Tail Truncation in Standard VACUUM

Standard VACUUM mainly keeps free space inside the relation, yet it can truncate completely empty pages at the end of the heap file.

### 11.1. Why Does It Need a Strong Lock?

To safely remove trailing pages from the relation, PostgreSQL needs an ACCESS EXCLUSIVE lock for the truncation step. This step is separate from VACUUM's main SHARE UPDATE EXCLUSIVE lock.

### 11.2. Avoiding the Truncation Step

In versions supporting this option, you can run:

~~~sql
VACUUM (TRUNCATE FALSE) sales.orders;
~~~

Or configure the corresponding table storage parameter per your running version's documentation. Disabling truncation avoids brief strong-lock acquisitions, at the cost of giving up returning empty trailing pages to the OS.

### 11.3. Does Not Turn Standard VACUUM into VACUUM FULL

`TRUNCATE FALSE` only controls trimming empty pages at the end of the file; it does not rewrite the entire table.

### 11.4. Not Every Table Has Empty Tail Pages

If free space is distributed across middle pages, truncation cannot shrink the file much anyway. Standard VACUUM remains useful for internal reuse.

### 11.5. Check Documentation for Your PostgreSQL Version

VACUUM options and storage parameters can differ across major versions. Check `SHOW server_version` and matching documentation before using them.

## 12. VACUUM Is Not the Same as ANALYZE

`ANALYZE` collects data distribution statistics so the query planner can choose execution plans. It does not replace cleaning up dead tuples.

~~~sql
ANALYZE sales.orders;
VACUUM sales.orders;
VACUUM (ANALYZE) sales.orders;
~~~

### 12.1. ANALYZE

Updates statistics such as estimated distinct value counts, most common values, histograms, and null fractions for sampled columns.

### 12.2. VACUUM

Reclaims dead tuples, updates free space/visibility metadata, and performs freezing as required.

### 12.3. VACUUM ANALYZE

Runs both tasks in one maintenance operation:

~~~sql
VACUUM (VERBOSE, ANALYZE) sales.orders;
~~~

### 12.4. When Queries Are Slow After a Large Import

You may need ANALYZE so the planner sees the new data distribution. Running VACUUM FULL solely to refresh statistics is the wrong choice.

### 12.5. ANALYZE Does Not Need ACCESS EXCLUSIVE

ANALYZE uses a lighter maintenance lock and is compatible with normal traffic under PostgreSQL lock semantics. It is not a table-rewrite command.

## 13. VACUUM FREEZE and Transaction ID Wraparound

PostgreSQL uses transaction IDs (XIDs) from a finite space. If a database fails to freeze old tuples on time, XIDs can approach wraparound, risking misinterpretation of old data visibility.

### 13.1. What Is Freezing?

VACUUM can mark sufficiently old tuples as frozen according to PostgreSQL's rules so they no longer need to be compared against old XIDs in the usual way.

### 13.2. Why Prevent Wraparound?

PostgreSQL must ensure an old tuple is never treated as belonging to a "future" transaction after the XID counter wraps around. Freezing is a core part of this protection.

### 13.3. VACUUM FREEZE

~~~sql
VACUUM (FREEZE, VERBOSE) sales.orders;
~~~

This requests more aggressive freezing for the relation within the scope of the command, not file compaction like VACUUM FULL.

### 13.4. Anti-Wraparound Autovacuum

PostgreSQL can trigger emergency autovacuum to protect against XID wraparound even when normal autovacuum is disabled. Do not rely on disabling autovacuum to evade maintenance.

### 13.5. Do Not Wait for Critical Warnings

If the database nears wraparound limits, PostgreSQL can emit warnings and eventually block certain writes to protect integrity. You must monitor XID age and ensure vacuum can run.

## 14. Autovacuum Is the Automatic Maintenance Mechanism

Autovacuum consists of a launcher and background workers. It monitors statistics and thresholds to decide when tables need VACUUM/ANALYZE.

~~~text
DML workload
     |
     v
Statistics collector / counters
     |
     v
Autovacuum launcher
     |
     +---- worker 1 ---> table A VACUUM
     |
     +---- worker 2 ---> table B ANALYZE
     |
     +---- worker 3 ---> table C VACUUM ANALYZE
~~~

### 14.1. Autovacuum Is Not a Simple Time-Based Scheduler

It reacts to statistical thresholds as well as XID age/insert activity factors, rather than merely running "every day at 2 AM".

### 14.2. Goal Is Timely Table Maintenance

Autovacuum curbs dead tuple accumulation, updates planner statistics, and freezes XIDs before wraparound becomes an incident.

### 14.3. Do Not Arbitrarily Disable Autovacuum Cluster-Wide

Disabling it can lead to bloat, slow queries, stale statistics, and wraparound risk. For special workloads, tune per-table/cluster and measure.

### 14.4. Manual VACUUM Still Has Its Place

A massive import/delete, sudden table churn, or autovacuum falling behind may warrant manual maintenance.

### 14.5. Autovacuum Uses Standard VACUUM Locking

Routine autovacuum never runs VACUUM FULL on its own. It uses standard VACUUM mechanics, so it does not rewrite the entire relation to compact it like FULL.

## 15. Autovacuum Thresholds

The standard vacuum threshold is computed from estimated dead tuples and configuration parameters.

~~~text
vacuum threshold =
    autovacuum_vacuum_threshold
    + autovacuum_vacuum_scale_factor * estimated_table_tuples
~~~

### 15.1. Fixed Threshold

`autovacuum_vacuum_threshold` is the base threshold component, adjustable in configuration.

### 15.2. Scale Factor

`autovacuum_vacuum_scale_factor` multiplies the estimated table size. A large table may need a very large number of dead tuples before the default threshold is reached.

### 15.3. Very Large Tables May Need Lower Scale Factors

For instance, on a billion-row table, the default scale factor can allow millions of dead tuples to build up before autovacuum triggers. You can lower thresholds based on table characteristics after observation.

### 15.4. Analyze Has Its Own Threshold

`autovacuum_analyze_threshold` and `autovacuum_analyze_scale_factor` govern when statistics updates are needed. Vacuum and analyze do not necessarily trigger together.

### 15.5. Insert-Triggered Vacuum

PostgreSQL provides dedicated parameters such as `autovacuum_vacuum_insert_threshold` and `autovacuum_vacuum_insert_scale_factor` to handle insert-heavy tables even when dead tuple count is not the primary signal.

## 16. Per-Table Autovacuum Tuning

You can set reloptions on a table:

~~~sql
ALTER TABLE sales.orders
SET (
    autovacuum_vacuum_threshold = 1000,
    autovacuum_vacuum_scale_factor = 0.02,
    autovacuum_analyze_threshold = 500,
    autovacuum_analyze_scale_factor = 0.01
);
~~~

These numbers are examples only. Do not copy them into production without evaluating row churn, write rate, I/O, and capacity.

### 16.1. Why Is Per-Table Tuning Useful?

A high-churn `orders` table differs from a nearly immutable `country_codes` table. A single scale factor across all tables can be too slow for huge tables or trigger overly frequent maintenance on small ones.

### 16.2. Viewing Reloptions

~~~sql
SELECT
    schemaname,
    tablename,
    reloptions
FROM pg_tables
WHERE schemaname = 'sales'
  AND tablename = 'orders';
~~~

You can query the appropriate catalog to see exact reloptions; `pg_tables` is a convenient view.

### 16.3. Resetting to Defaults

~~~sql
ALTER TABLE sales.orders
RESET (
    autovacuum_vacuum_threshold,
    autovacuum_vacuum_scale_factor
);
~~~

Only reset options that were explicitly set; verify syntax for your version.

### 16.4. Do Not Lower Thresholds Infinitely

Vacuuming too frequently creates I/O overhead, resource contention, and latency impact. The goal is balancing churn, bloat, and cost.

### 16.5. ALTER TABLE Does Not Run Vacuum Immediately

Changing reloptions affects subsequent evaluations by the launcher/workers. If immediate cleanup is needed, consider manual VACUUM at an appropriate time.

## 17. Server-Level Autovacuum Parameters

| Parameter | General Meaning |
|---|---|
| `autovacuum` | Enables/disables the autovacuum mechanism |
| `autovacuum_naptime` | Wait interval between launcher checks |
| `autovacuum_max_workers` | Maximum number of workers |
| `autovacuum_vacuum_threshold` | Base dead-tuple threshold |
| `autovacuum_vacuum_scale_factor` | Table-size-proportional threshold component |
| `autovacuum_analyze_threshold` | Base modification threshold for ANALYZE |
| `autovacuum_analyze_scale_factor` | Scale-based threshold for ANALYZE |
| `autovacuum_vacuum_cost_limit` | Cost budget for autovacuum when set |
| `autovacuum_vacuum_cost_delay` | Delay under cost-based throttling |
| `autovacuum_work_mem` | Dedicated working memory for autovacuum when configured |
| `autovacuum_freeze_max_age` | XID age threshold driving freeze/anti-wraparound |

### 17.1. Worker Count

Increasing `autovacuum_max_workers` lets more tables be processed in parallel, but also increases CPU, memory, and I/O pressure.

### 17.2. Cost-Based Delay

Vacuum cost delay/limit slows maintenance to reduce workload impact. If throttled too aggressively, autovacuum may not keep up with churn rates.

### 17.3. Work Memory

VACUUM must track dead tuple identifiers and handle index cleanup. Low memory can force multiple index cleanup passes; overly high memory multiplied across workers can cause RAM pressure.

### 17.4. Do Not Tune Based on a Single Metric

Observe dead tuple estimates, table size, autovacuum frequency/duration, I/O latency, transaction age, WAL generation, and query latency together.

### 17.5. Parameter Context and Reload

Some parameters require a reload or restart depending on context/version. Check `pg_settings.context`, `pending_restart`, and server documentation rather than guessing.

## 18. Why Can Autovacuum Fall Behind?

Common reasons:

- Table write churn exceeds vacuum capacity.
- Scale factor/threshold is too high.
- Worker slots are occupied by other tables.
- Storage I/O is too slow or cost delay is too large.
- Old transactions/snapshots retain dead tuples.
- Replication slots/standby feedback hold back xmin.
- Lock conflicts make workers wait.
- Partitioned parent tables require separate ANALYZE per version semantics.
- Memory limits/index cleanup force vacuum into multiple passes.
- Certain tables have unsuitable per-table reloptions.

### 18.1. Increasing Worker Count Does Not Fix a Pinned Horizon

If a long-running transaction still needs old versions, vacuuming continuously still cannot remove tuples that are unsafe to reclaim.

### 18.2. Low Scale Factors Do Not Fix an I/O Bottleneck

They trigger vacuum earlier, but do not speed up storage reads/writes by themselves.

### 18.3. Check What Workers Are Waiting On

Combine `pg_stat_activity`, `pg_locks`, `pg_stat_progress_vacuum`, and logs to identify waits rather than looking solely at tables with many dead tuples.

### 18.4. Be Careful Running Manual VACUUM Alongside Autovacuum

They can conflict on locks on the same relation or waste resources. Check running workers before executing manual commands.

### 18.5. Do Not Reflexively Kill Autovacuum

Killing a worker interrupts maintenance in progress and leaves the underlying issue unresolved. Identify the blocker or resource bottleneck first.

## 19. Long Transactions Retain Dead Tuples

VACUUM is only allowed to reclaim a tuple version once it is certain no transaction snapshot needs it anymore. An overly long open transaction can hold an old xmin horizon.

~~~text
Transaction A: BEGIN; SELECT ...;  (holds old snapshot)
Transaction B: UPDATE row; COMMIT
Transaction C: DELETE row; COMMIT
VACUUM: cannot yet remove versions A still needs
Transaction A: COMMIT
Subsequent VACUUM can reclaim more tuples
~~~

### 19.1. Idle in Transaction

A client that runs BEGIN and leaves the connection `idle in transaction` can hold a snapshot even while executing no queries. This is a common reason VACUUM fails to reclaim old data.

### 19.2. Long-Running Transactions

Analytical queries, cursors, or long batch transactions can hold xmin for a long time. Check transaction duration, not just the duration of the last statement.

### 19.3. Prepared Transactions

Prepared transactions can hold locks and interfere with maintenance progress until `COMMIT PREPARED` or `ROLLBACK PREPARED`. Monitor `pg_prepared_xacts` if the system uses two-phase commit.

### 19.4. VACUUM Cannot Delete Still-Visible Tuples

Adding workers or running VACUUM FULL is not the root fix if a transaction still needs old data. Handle the transaction horizon through a safe operational process.

### 19.5. Do Not Terminate Transactions Solely by Age

A long transaction may be performing critical business work. Verify owner, query, state, impact, and rollback semantics before terminating.

## 20. Replication Slots and Standby Feedback

Replication can also retain tuple versions that the primary is not yet permitted to reclaim.

### 20.1. Replication Slots Holding xmin

Logical replication slots can retain `xmin` or `catalog_xmin` so consumers can still read required changes. If a consumer stops for a long time, VACUUM may be unable to clean up some tuples/catalog rows.

### 20.2. Hot Standby Feedback

A standby can send xmin feedback to the primary to prevent standby queries from conflicting with cleanup. This helps certain read workloads, but can cause the primary to hold dead tuples longer and increase bloat.

### 20.3. Slot Lag and WAL Retention Are Related but Distinct

A replication slot can retain WAL via `restart_lsn` while simultaneously pinning `xmin`/`catalog_xmin`. Monitor both WAL usage and the tuple cleanup horizon.

### 20.4. Inspecting Slots

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

Some columns/states may vary by PostgreSQL version and slot type.

### 20.5. Do Not Drop a Slot Just to Force VACUUM

Dropping a replication slot can prevent the consumer from resuming replication or logical decoding. Verify the owner and consumer rebuild capability before making changes.

## 21. Checking Transactions and the xmin Horizon

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    now() - xact_start AS transaction_age,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 160) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

### 21.1. backend_xmin

Indicates the xmin of the snapshot held by a backend in certain states. This is an important clue when investigating transactions pinning the cleanup horizon.

### 21.2. application_name Helps Tracing

Configure applications with clear `application_name` values so DBAs know which service/batch/reporting job owns a connection.

### 21.3. Do Not Dump Full Queries Containing Secrets

Query text can contain sensitive literals in applications that construct unsafe SQL. Redaction and access controls still matter in dashboards and tickets.

### 21.4. idle_in_transaction_session_timeout

You can configure a timeout to close sessions idle in a transaction too long, but weigh workload and application behavior before applying it.

### 21.5. Terminating a Session Can Roll Back Work

If forced to release a horizon, `pg_cancel_backend` or `pg_terminate_backend` can disrupt queries/transactions. That is an impactful operational action, not a standard part of VACUUM.

## 22. Observing Which Tables Need VACUUM

The `pg_stat_user_tables` view provides per-table statistical estimates.

~~~sql
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
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
~~~

### 22.1. n_dead_tup Is an Estimate

This is a statistical estimate, not an exact physical count of every dead tuple at the exact instant of the query.

### 22.2. Do Not Rank by Absolute Numbers Alone

A table with 100,000 dead tuples out of 10 billion rows may be less concerning than a 120,000-row table where nearly all versions are dead.

### 22.3. Comparing Against Relation Size

~~~sql
SELECT
    schemaname,
    relname,
    pg_size_pretty(
        pg_relation_size(
            format('%I.%I', schemaname, relname)::regclass
        )
    ) AS heap_size,
    pg_size_pretty(
        pg_total_relation_size(
            format('%I.%I', schemaname, relname)::regclass
        )
    ) AS total_size,
    n_live_tup,
    n_dead_tup
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(
    format('%I.%I', schemaname, relname)::regclass
) DESC
LIMIT 30;
~~~

This query builds `regclass` from schema/table names in the view; in production admin scripts, you can use OIDs/joins to avoid `search_path` dependencies and handle identifiers more cleanly.

### 22.4. Heap Size and Total Size Differ

`pg_relation_size` measures the main heap relation; `pg_total_relation_size` includes associated indexes and TOAST according to the function's semantics.

### 22.5. Do Not Infer Exact Bloat from n_dead_tup Alone

For deeper measurement, you can use an extension like `pgstattuple` if installed and authorized, or a version-aware bloat analysis tool. Simple statistical estimates are only a starting point.

## 23. Monitoring Running VACUUM

The `pg_stat_progress_vacuum` view reports progress for standard VACUUM:

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

### 23.1. Phases Change During Execution

VACUUM goes through multiple phases, such as scanning heap, vacuuming indexes, vacuuming heap, cleaning up indexes, truncating heap, and performing final cleanup. Verify exact phase/column names for your version.

### 23.2. Progress Ratio Does Not Equal Exact Remaining Time

Scanned/total heap blocks is one signal, but index cleanup phases and waits have very different costs.

### 23.3. VACUUM FULL Has a Different Progress View

VACUUM FULL is implemented as a relation rewrite and is reported in `pg_stat_progress_cluster` on supported versions. Do not look only at `pg_stat_progress_vacuum` and assume FULL is not running.

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS relation,
    command,
    phase,
    heap_tuples_scanned,
    heap_tuples_written,
    heap_blks_total,
    heap_blks_scanned,
    index_rebuild_count
FROM pg_stat_progress_cluster;
~~~

Columns can change across versions; inspect the view schema on the running server.

### 23.4. Not All Maintenance Operations Share the Same Progress View

If querying the view returns no rows, the command may not have started, may have already finished, you may lack visibility privileges, or the operation is reported in another view.

### 23.5. Verbose Output

~~~sql
VACUUM (VERBOSE) sales.orders;
~~~

VERBOSE records useful diagnostic processing details; ensure logs are not abused and appropriate access permissions are enforced.

## 24. Viewing Locks and Blocking Sessions

A basic query to inspect locks on a table:

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    l.mode,
    l.granted,
    now() - a.query_start AS query_age,
    a.wait_event_type,
    a.wait_event,
    left(a.query, 180) AS query_sample
FROM pg_locks AS l
JOIN pg_stat_activity AS a
  ON a.pid = l.pid
LEFT JOIN pg_class AS c
  ON c.oid = l.relation
LEFT JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE l.locktype = 'relation'
  AND n.nspname = 'sales'
  AND c.relname = 'orders'
ORDER BY l.granted, a.query_start;
~~~

### 24.1. granted=false

The backend is waiting on a lock. Identify who holds the conflicting lock and which statement caused it.

### 24.2. granted=true

The backend holds the lock. It might be VACUUM, an active query, or a transaction that acquired a lock and stayed open.

### 24.3. Relation Locks Are Not Every Lock

This query filters relation locks; it does not fully describe tuple locks, transactionid locks, or waits on other resources.

### 24.4. pg_blocking_pids

PostgreSQL provides `pg_blocking_pids(pid)` to locate backends blocking a given PID.

~~~sql
SELECT
    blocked.pid AS blocked_pid,
    blocker.pid AS blocker_pid,
    blocked.application_name AS blocked_app,
    blocker.application_name AS blocker_app,
    now() - blocker.xact_start AS blocker_xact_age,
    left(blocked.query, 120) AS blocked_query,
    left(blocker.query, 120) AS blocker_query
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL
    unnest(pg_blocking_pids(blocked.pid)) AS b(pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = b.pid;
~~~

### 24.5. Do Not Just Kill the Waiting PID

Identify the root blocker, transaction age, owner, and consequences. Killing a waiter does not resolve the transaction holding the original lock.

## 25. Standard VACUUM Can Still Be Blocked

Even though its main lock is compatible with DML, VACUUM can still wait on conflicting locks from DDL or other maintenance.

Examples:

- `ALTER TABLE` requiring ACCESS EXCLUSIVE.
- Another VACUUM/ANALYZE holding SHARE UPDATE EXCLUSIVE.
- `CREATE INDEX CONCURRENTLY` using a maintenance lock that can conflict.
- Certain REINDEX/CLUSTER or schema maintenance operations.
- Lock queues affected by a waiting ACCESS EXCLUSIVE request.

### 25.1. DDL and VACUUM

Schedule schema migrations so they do not collide with heavy maintenance. A DDL requiring a strong lock may wait on VACUUM; conversely, VACUUM can queue behind DDL depending on arrival order.

### 25.2. Lock Timeout

You can set a timeout for a maintenance session:

~~~sql
SET lock_timeout = '5s';
VACUUM sales.orders;
~~~

If the lock cannot be acquired within the allowed time, the statement fails. Note that VACUUM cannot run inside a transaction block; session-level `SET` still applies when running commands in autocommit mode.

### 25.3. VACUUM Cannot Run Inside a Transaction Block

~~~sql
-- Do not use:
BEGIN;
VACUUM sales.orders;
COMMIT;
~~~

VACUUM must run as a utility command outside an explicit transaction block. Some migration frameworks automatically wrap all statements in a transaction and require special configuration.

### 25.4. VACUUM Does Not Roll Back Like Normal DML

This is a maintenance command with side effects that cannot be treated like an UPDATE where ROLLBACK restores the previous state. Do not run it inside a transaction to "try it out".

### 25.5. Privileges to Run VACUUM

Required privileges depend on the PostgreSQL version and relation: typically table owner/superuser, while newer versions may offer the `MAINTAIN` privilege. Check actual privileges rather than granting broad superuser access.

## 26. VACUUM FULL and Disk Space

A critical detail before running FULL: during the rewrite, both the old table and the new copy must coexist.

~~~text
Before:
  old heap + old indexes

During rewrite:
  old heap + old indexes
  new heap + new indexes

After completion:
  new heap + new indexes
  old files are freed
~~~

### 26.1. Extra Space Needed

Temporary space required depends on heap size, indexes, TOAST, tablespaces, and the specific process. Do not use the expected final size as your free-disk limit.

### 26.2. Tablespaces

If the table or its indexes reside in separate tablespaces, provision space on the corresponding filesystems/volumes, not just PGDATA.

### 26.3. Running Out of Disk Mid-Rewrite

Insufficient disk can fail the command and put severe stress on the cluster and other workloads. Check both temporary growth and WAL/storage impacts for your architecture.

### 26.4. Index Rebuilds

VACUUM FULL rewrites the relation and rebuilds associated indexes; therefore it consumes extra disk, CPU, and I/O beyond just the heap.

### 26.5. Plan for the Worst Case

Use a comparably sized staging/clone environment, measure duration and peak disk consumption, allow for concurrent growth, and maintain a safety buffer.

## 27. Does VACUUM FULL Change the Physical Identity of the Table?

Because FULL rewrites the relation, new physical files are created and replace the old ones. Physical attributes such as `relfilenode` can change.

### 27.1. Do Not Hard-Code Relation File Paths

Do not let applications or operational scripts depend on internal filenames in `base/` or `global/`. Use SQL/catalogs and PostgreSQL-managed tools.

### 27.2. Object OID and relfilenode Are Different Concepts

The OID identifies the catalog object; `relfilenode` identifies the current storage file. A rewrite can change the filenode while the SQL table object remains the same.

### 27.3. Logical References Remain Managed

Indexes, constraints, and dependencies are updated by the rewrite operation. SQL clients should never rely on internal file paths.

### 27.4. Locks and Prepared Statements

VACUUM FULL blocks access during the rewrite. PostgreSQL and drivers handle plan invalidation and metadata per server mechanisms; do not cache internal relation file identifiers externally.

### 27.5. Check Non-Standard Extensions/Tooling

Backup tools, monitoring agents, or extensions reading physical files must be compatible with maintenance and catalog changes. Never touch table files directly during a rewrite.

## 41. Lab: Observing Progress and Blockers

Open a session to run a maintenance command on a sufficiently large lab table:

~~~sql
VACUUM (VERBOSE) vacuum_lab.items;
~~~

In another session, monitor:

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS relation,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed
FROM pg_stat_progress_vacuum;
~~~

### 41.1. Monitoring FULL

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS relation,
    command,
    phase,
    heap_blks_total,
    heap_blks_scanned
FROM pg_stat_progress_cluster;
~~~

VACUUM FULL can be reported through the progress view for cluster/rewrite operations, depending on version.

### 41.2. Monitoring Locks

~~~sql
SELECT
    a.pid,
    a.state,
    l.mode,
    l.granted,
    a.wait_event_type,
    a.wait_event,
    now() - a.query_start AS elapsed
FROM pg_locks AS l
JOIN pg_stat_activity AS a USING (pid)
WHERE l.locktype = 'relation'
  AND l.relation = 'vacuum_lab.items'::regclass
ORDER BY l.granted, elapsed DESC;
~~~

### 41.3. Viewing Blockers

~~~sql
SELECT
    pid,
    pg_blocking_pids(pid) AS blocking_pids,
    wait_event_type,
    wait_event,
    left(query, 120) AS query_sample
FROM pg_stat_activity
WHERE cardinality(pg_blocking_pids(pid)) > 0;
~~~

### 41.4. Sampling State at Multiple Points

Progress views are point-in-time snapshots when queried. An empty result can simply mean VACUUM finished between checks.

### 41.5. Do Not Wait Indefinitely in the Lab

If a session is unexpectedly blocked, check the blocker and end the lab transaction deliberately. Do not run terminate commands on shared systems.

## 42. Diagnosing Bloat: Using Multiple Signals

Bloat is physical space no longer useful for current data or used inefficiently, yet no single simple metric always measures it accurately.

### 42.1. Signals from pg_stat_user_tables

`n_dead_tup` helps spot dead tuple estimates, but does not cover overall free space, page density, or index bloat.

### 42.2. Signals from Size

Track `pg_relation_size`, `pg_indexes_size`, and `pg_total_relation_size` over time. A growing table may simply reflect legitimate data growth rather than bloat.

### 42.3. Signals from Workload

If a table grows rapidly again right after cleanup, examine UPDATE churn, DELETE patterns, fillfactor, index count, and HOT update ratio.

### 42.4. The pgstattuple Extension

`pgstattuple` can provide detailed live/dead/free space metrics inside a relation, but requires extension installation, privileges, and scan cost. Use it with care on large workloads.

### 42.5. Index Bloat Is a Separate Issue

A compact heap table does not guarantee every index is compact. Evaluate individual indexes and choose REINDEX/maintenance when evidence supports it.

## 43. Maintenance Runbook for Standard VACUUM

A routine runbook may include:

1. Select the database/schema/table to inspect.
2. Check dead tuple estimates, sizes, and last vacuum/analyze timestamps.
3. Check transaction age, replication slots, and blockers.
4. Check autovacuum workers and current progress.
5. Determine whether manual VACUUM or just ANALYZE is needed.
6. Pick an appropriate window if the table has high churn/I/O.
7. Run standard VACUUM with VERBOSE when diagnostics are needed.
8. Monitor progress, locks, I/O, and application latency.
9. Re-check statistics and planner behavior.
10. Document results, anomalies, and tuning changes.

### 43.1. Minimal Command

~~~sql
VACUUM sales.orders;
~~~

### 43.2. When Planner Refresh Is Needed

~~~sql
VACUUM (ANALYZE) sales.orders;
~~~

### 43.3. When Detailed Output Is Needed

~~~sql
VACUUM (VERBOSE, ANALYZE) sales.orders;
~~~

### 43.4. Do Not Schedule Nightly FULL Out of Habit

Routine maintenance should favor standard VACUUM/autovacuum. Run FULL only with a specific reclaim objective and a lock/disk plan.

### 43.5. Evaluating Afterward

If `n_dead_tup` drops while query latency stays the same, queries may be slow due to indexes/plans/other I/O. VACUUM does not replace EXPLAIN analysis.

## 44. Maintenance Runbook for VACUUM FULL

Before running FULL:

- Confirm the table truly has significant bloat/free space to reclaim.
- Estimate peak disk usage, including indexes/TOAST/tablespaces.
- Measure rewrite time using an equivalent clone/staging instance.
- Check open transactions and sessions holding locks.
- Check application timeouts, connection pools, and retry behavior.
- Schedule a maintenance window and notify owners.
- Verify backup/restore points per procedure.
- Prepare operational abort/rollback steps if the lock cannot be acquired.
- Run against the exact right table/schema/database/host.
- Verify sizes, constraints, indexes, and application health afterward.

### 44.1. Command

~~~sql
VACUUM FULL (VERBOSE, ANALYZE) sales.orders;
~~~

### 44.2. Do Not Set Arbitrarily Tiny Timeouts

If `lock_timeout` is too short, FULL may fail repeatedly before starting. If too long, a lock request can sit in the queue and worsen blocking. Choose based on the maintenance plan.

### 44.3. Do Not Blindly Run Many FULLs Concurrently

Concurrent rewrites compete for disk/CPU/I/O and require large temporary space. A cluster with many large tables may recover slower if all FULL jobs run at once.

### 44.4. Do Not Use CANCEL as a Normal Control Mechanism

Canceling a running FULL rolls back the rewrite work and holds resources during cleanup. Avoid starting unless prerequisites are met.

### 44.5. Monitoring Still Matters After FULL

A freshly compacted table does not mean autovacuum can be disabled. Ongoing workloads continue generating dead tuples and still need routine maintenance.

## 45. Common Mistakes and Misconceptions

### 45.1. "VACUUM immediately deletes DELETEd rows from the file"

False. It reclaims dead tuple versions when safe; the physical file usually retains its size for reuse.

### 45.2. "Standard VACUUM always returns disk space to the OS"

False. It primarily enables internal reuse; it can only truncate completely empty trailing pages when conditions permit.

### 45.3. "VACUUM FULL is just a slightly stronger VACUUM"

False. It rewrites the relation, rebuilds indexes, and requires ACCESS EXCLUSIVE.

### 45.4. "Standard VACUUM takes no locks"

False. It acquires SHARE UPDATE EXCLUSIVE; this is compatible with normal SELECT/DML, but conflicts with certain maintenance/DDL.

### 45.5. "VACUUM FULL only blocks INSERT/UPDATE/DELETE"

False. ACCESS EXCLUSIVE also conflicts with ACCESS SHARE, so SELECT is blocked too.

### 45.6. "VACUUM FULL always runs faster because it cleans more thoroughly"

False. Rewriting and rebuilding indexes usually consume substantial I/O, CPU, and temporary disk.

### 45.7. "Running FULL requires no extra disk space"

False. Old and new relations can coexist during the rewrite.

### 45.8. "High n_dead_tup always proves FULL is needed"

False. It is an estimate; evaluate ratios, size, free space, and reclaim goals.

### 45.9. "Autovacuum enabled means every table is handled on time"

False. Worker capacity, thresholds, locks, I/O, and the xmin horizon can cause delays.

### 45.10. "Disabling autovacuum safely avoids CPU overhead"

False. It can cause bloat, stale planner stats, and XID wraparound risk.

### 45.11. "VACUUM FULL replaces autovacuum"

False. FULL is an exclusive-lock rewrite operation; routine autovacuum is still needed to maintain the table afterward.

### 45.12. "ANALYZE cleans up dead tuples"

False. ANALYZE collects planner statistics; VACUUM cleans up tuple versions.

### 45.13. "An idle transaction does not affect VACUUM"

False. `idle in transaction` can pin a snapshot and an old cleanup horizon.

### 45.14. "Replicas always let the primary free tuples"

False. Replication slots and `hot_standby_feedback` can pin `xmin`/`catalog_xmin`.

### 45.15. "Adding autovacuum workers solves every lag issue"

False. It does not resolve a pinned transaction horizon, lock blocker, or storage bottleneck.

### 45.16. "Killing a waiting PID frees the blocker"

False. You must find the root blocker; terminating a waiter does not end the transaction holding the lock.

### 45.17. "pg_stat_progress_vacuum always displays VACUUM FULL"

False. FULL is reported in the cluster/rewrite operation progress view in supported versions.

### 45.18. "pg_relation_size is the entire table size"

False. Indexes and TOAST can make total size much larger than heap size.

### 45.19. "VACUUM FULL fixes all index bloat across the database"

False. It affects indexes of the rewritten relation, not all indexes in the cluster.

### 45.20. "CLUSTER/pg_repack need no locks"

False. They have their own trade-offs and locking phases.

### 45.21. "Old partitions must be DELETEd row by row"

False. For time-based retention, partition detach/drop can be far more efficient if schema/dependencies allow.

### 45.22. "VACUUM can run inside a transaction block"

False. The VACUUM utility command must run outside an explicit transaction block.

### 45.23. "VACUUM can be ROLLBACKed to restore the previous state"

False. Do not treat maintenance like a normal DML transaction that can roll back to undo cleanup.

### 45.24. "VACUUM FULL is the default way to handle wraparound"

False. Freezing/anti-wraparound is handled by standard VACUUM and autovacuum; FULL is not a routine requirement.

### 45.25. "Tables with few UPDATE/DELETEs do not need VACUUM"

False. Freezing/XID age and the visibility map still matter.

### 45.26. "If VACUUM finishes with no output, it did nothing"

False. Lack of VERBOSE output does not mean cleanup did not happen; inspect stats/progress/logs.

### 45.27. "One VACUUM removes all dead tuples"

False. Tuples still retained by snapshots cannot be reclaimed yet; ongoing workloads keep creating dead tuples.

### 45.28. "Disabling truncate disables VACUUM"

False. `TRUNCATE FALSE` only skips trimming empty trailing pages per supported options; cleanup and reuse still occur.

### 45.29. "After FULL, maintenance can be turned off"

False. New DML continues creating tuple versions and still needs autovacuum.

### 45.30. "Making a table smaller with VACUUM guarantees faster queries"

False. Query plans, indexes, cache, I/O, and selectivity govern performance; VACUUM can help some access paths, but it is no guarantee.

## 46. Practice Exercises

### Exercise 1 — MVCC

Why does PostgreSQL not immediately delete the old tuple on UPDATE?

**Hint:** An older transaction snapshot may still need to see that version.

### Exercise 2 — Dead Tuple

When does a tuple version become dead?

**Answer:** When no remaining snapshot/transaction can possibly need it.

### Exercise 3 — VACUUM

What is the primary goal of standard VACUUM?

**Hint:** Reclaiming dead tuple versions, updating free space/visibility metadata, and freezing.

### Exercise 4 — VACUUM FULL

What is the core storage difference?

**Answer:** Rewriting the relation and compacting the file.

### Exercise 5 — Disk Reuse

Why can a file stay large after standard VACUUM finishes?

**Hint:** Free space is kept inside the relation for reuse.

### Exercise 6 — OS Reclaim

Under what circumstance can standard VACUUM return some space to the OS?

**Hint:** Truncating completely empty pages at the end of the relation.

### Exercise 7 — Standard Lock

What is the main lock of standard VACUUM?

**Answer:** SHARE UPDATE EXCLUSIVE.

### Exercise 8 — FULL Lock

What is the lock of VACUUM FULL?

**Answer:** ACCESS EXCLUSIVE.

### Exercise 9 — SELECT

Can normal SELECT run concurrently with standard VACUUM?

**Answer:** Usually yes; ACCESS SHARE is compatible with SHARE UPDATE EXCLUSIVE.

### Exercise 10 — DML

Can normal INSERT/UPDATE/DELETE run alongside standard VACUUM?

**Answer:** Usually yes; ROW EXCLUSIVE is compatible with SHARE UPDATE EXCLUSIVE.

### Exercise 11 — FULL and SELECT

Why does VACUUM FULL block SELECT?

**Hint:** ACCESS EXCLUSIVE conflicts with ACCESS SHARE.

### Exercise 12 — Lock Queue

How can a VACUUM FULL waiting for a lock affect new queries?

**Hint:** Lock requests can queue up behind the waiting strong lock.

### Exercise 13 — Long Transaction

What problem can an `idle in transaction` session cause?

**Answer:** Holding a snapshot/xmin horizon, preventing cleanup.

### Exercise 14 — Replication Slot

How can a slot with `xmin`/`catalog_xmin` affect VACUUM?

**Hint:** Retaining tuple/catalog versions needed by the consumer.

### Exercise 15 — Hot Standby Feedback

What trade-off does this setting introduce?

**Hint:** Reduces query conflicts on the standby, but can increase primary bloat.

### Exercise 16 — ANALYZE

What does ANALYZE do?

**Answer:** Updates planner statistics.

### Exercise 17 — VACUUM ANALYZE

Which statement runs both?

**Answer:** `VACUUM (ANALYZE) schema.table;`.

### Exercise 18 — FREEZE

What does VACUUM FREEZE protect against?

**Hint:** XID wraparound.

### Exercise 19 — Autovacuum

What does autovacuum typically base its run decisions on?

**Hint:** Dead tuple/modification thresholds, insert activity, and XID age.

### Exercise 20 — Threshold Formula

Write the basic vacuum threshold formula.

**Answer:** `autovacuum_vacuum_threshold + autovacuum_vacuum_scale_factor * estimated_table_tuples`.

### Exercise 21 — Scale Factor

Why might a very large table need a lower scale factor?

**Hint:** The default implied dead tuple threshold may be too large.

### Exercise 22 — Per-Table Options

Which command sets the autovacuum scale factor for one table?

**Hint:** `ALTER TABLE ... SET (autovacuum_vacuum_scale_factor = ...)`.

### Exercise 23 — Worker Tuning

What trade-off can increasing `autovacuum_max_workers` introduce?

**Hint:** More tables processed in parallel, but higher CPU/RAM/I/O usage.

### Exercise 24 — Wraparound

Why does a low-write database still need freezing?

**Answer:** XID age still advances and tuple visibility must be protected.

### Exercise 25 — n_dead_tup

Is this an exact instantaneous count of dead tuples?

**Answer:** No, it is an estimate.

### Exercise 26 — Size

Which function checks a table's heap size?

**Answer:** `pg_relation_size`.

### Exercise 27 — Total Size

Which function includes associated indexes/TOAST?

**Answer:** `pg_total_relation_size`.

### Exercise 28 — Standard Progress

Which view monitors standard VACUUM?

**Answer:** `pg_stat_progress_vacuum`.

### Exercise 29 — FULL Progress

Which view can report VACUUM FULL rewrite progress?

**Answer:** `pg_stat_progress_cluster` in supported versions.

### Exercise 30 — Locks

Which view shows lock grants and waits?

**Answer:** `pg_locks`.

### Exercise 31 — Blockers

Which function finds backends blocking a PID?

**Answer:** `pg_blocking_pids(pid)`.

### Exercise 32 — XID Age

How do you check which database has a high `datfrozenxid` age?

**Hint:** Query `pg_database` and `age(datfrozenxid)`.

### Exercise 33 — VACUUM FULL Disk

Why is extra free disk space required?

**Hint:** Old/new relations and indexes coexist during the rewrite.

### Exercise 34 — pg_repack

Is this tool completely lock-free?

**Answer:** No; it has its own locking phases and requirements.

### Exercise 35 — Partition Retention

Why can dropping a partition be better than deleting millions of rows?

**Hint:** Drops a relation/partition at large scale, avoiding per-row churn.

### Exercise 36 — Transaction Block

Can VACUUM run inside BEGIN/COMMIT?

**Answer:** No.

### Exercise 37 — Routine VACUUM FULL

Should VACUUM FULL run nightly on every table?

**Answer:** No; evaluate bloat, locks, disk, and necessity.

### Exercise 38 — Lock Lab

Transaction A opens a SELECT without committing. Can VACUUM FULL in B acquire ACCESS EXCLUSIVE immediately?

**Answer:** No; it must wait for A to release ACCESS SHARE.

### Exercise 39 — Standard Lab

With transaction A holding that open SELECT, can standard VACUUM in B run?

**Answer:** Usually yes, since lock modes are compatible, provided no other blocker exists.

### Exercise 40 — Choosing a Solution

A large table has scattered free space, needs to return disk to the OS, traffic cannot stop, and there is no maintenance window. What do you do?

**Hint:** Do not run VACUUM FULL recklessly; address the cause of bloat, evaluate `pg_repack`/partitioning based on compatibility and lock/disk planning, then rehearse.

## 47. Checklist Before Running Standard VACUUM

- [ ] Have you selected the right database/schema/table?
- [ ] Have you checked `last_vacuum`/`last_autovacuum` and stats?
- [ ] Is any long transaction or xmin horizon pinning tuples?
- [ ] Is autovacuum already processing the same relation?
- [ ] Is any DDL/maintenance holding a conflicting lock?
- [ ] Do the current workload and I/O have enough headroom?
- [ ] Is ANALYZE needed at the same time?
- [ ] Is VERBOSE/progress monitoring needed?
- [ ] Should brief tail truncation locking be avoided via version-supported options?
- [ ] Do you have a baseline to compare against afterward?

## 48. Checklist Before Running VACUUM FULL

- [ ] Is there evidence of substantial bloat/free space?
- [ ] Is the goal returning disk to the OS or only internal reuse?
- [ ] Have you considered partition lifecycle/`pg_repack`/CLUSTER/REINDEX?
- [ ] Have you measured table, index, and TOAST sizes?
- [ ] Have you verified free disk space on the relevant tablespaces and volumes?
- [ ] Is there an appropriate maintenance window?
- [ ] Have you identified blockers and transaction ages?
- [ ] Have you assessed the ACCESS EXCLUSIVE impact on SELECT/DML?
- [ ] Are connection pools/timeouts/retries configured appropriately?
- [ ] Have you verified your backup/recovery plan?
- [ ] Is someone monitoring progress, locks, disk, I/O, and application latency?
- [ ] Is there a post-rewrite verification plan?

## 49. Quick Reference Table

| Concept | Key Note |
|---|---|
| MVCC | Multiple tuple versions serving snapshots |
| Dead tuple | Version no longer needed by current/future snapshots |
| VACUUM | Cleanup, free space reuse, visibility map, and freeze |
| VACUUM FULL | Rewrites/compacts relation, rebuilds indexes |
| SHARE UPDATE EXCLUSIVE | Main lock of standard VACUUM |
| ACCESS EXCLUSIVE | Lock of VACUUM FULL |
| ACCESS SHARE | Normal lock of SELECT |
| ROW EXCLUSIVE | Normal lock of INSERT/UPDATE/DELETE |
| Free space map | Hints at pages with available space for reuse |
| Visibility map | All-visible/all-frozen page metadata |
| ANALYZE | Updates planner statistics |
| FREEZE | Protects tuple visibility against XID wraparound |
| Autovacuum | Background VACUUM/ANALYZE driven by thresholds and XID age |
| Scale factor | Table-size-proportional modification threshold |
| n_dead_tup | Dead tuple estimate |
| pg_stat_user_tables | Vacuum/analyze history and tuple estimates |
| pg_stat_progress_vacuum | Standard VACUUM progress |
| pg_stat_progress_cluster | Rewrite/CLUSTER and VACUUM FULL progress per version |
| pg_locks | Lock grants and waiters |
| pg_blocking_pids | Finds blocking backends |
| backend_xmin | Snapshot horizon held by a backend |
| Replication slot xmin | Can delay tuple cleanup |
| hot_standby_feedback | Can hold back xmin on the primary |
| VACUUM FULL disk | Requires extra space for rewrite |
| pg_repack | Online-ish rewrite tool with trade-offs |
| CLUSTER | Rewrites in index order, strong lock |
| REINDEX | Rebuilds indexes |
| Partition detach/drop | Relation-level retention instead of mass DELETE |
| XID age | Metric tracking wraparound risk |

## 50. Conclusion

**Standard VACUUM and VACUUM FULL serve two different purposes.** Standard VACUUM reclaims dead tuple versions, updates free space/visibility metadata, and freezes required tuples; it primarily makes space reusable inside the relation and usually does not shrink the file significantly. It uses SHARE UPDATE EXCLUSIVE so it is compatible with normal SELECT and DML, though it can still cause I/O contention or conflict with other DDL/maintenance. The step to truncate empty trailing pages can require a brief ACCESS EXCLUSIVE lock and can be controlled with version-appropriate options.

**VACUUM FULL rewrites the entire relation and its indexes to compact them, usually returning space to the filesystem, but requires ACCESS EXCLUSIVE for the entire operation.** This blocks SELECT/INSERT/UPDATE/DELETE on the table and needs extra disk while old and new files coexist. Therefore FULL should only run when there is a clear reclaim goal, bloat has been measured, sufficient space is available, and a maintenance window or traffic-control plan is in place.

Autovacuum is an essential routine mechanism, not something to disable to dodge I/O. If vacuum fails to reclaim tuples, look for long transactions, idle-in-transaction sessions, prepared transactions, replication slots, and standby feedback before adding workers or running FULL. Monitor `n_dead_tup` alongside relation sizes, XID age, progress views, and `pg_locks` to understand root causes rather than guessing from a single metric.

Operational principle: **use standard VACUUM for routine cleanup and reuse; use VACUUM FULL only when you genuinely need a rewrite to return disk space and can accept an exclusive lock; always fix the root cause of bloat, monitor autovacuum/freezing, and check blockers before maintenance.**


## 29. Standard VACUUM Does Not Always Reduce File Size

After standard VACUUM completes, check:

~~~sql
SELECT
    pg_size_pretty(pg_relation_size('sales.orders')) AS heap_size,
    pg_size_pretty(pg_total_relation_size('sales.orders')) AS total_size;
~~~

### 29.1. Free Space Can Be Reused

Subsequent INSERTs can reuse pages that have available room. Thus the file remains large, yet the table is not necessarily still "full of dead tuples".

### 29.2. Free Space Is Not the Same as Bloat

Free pages inside a relation can be useful capacity to absorb incoming workload. Not all free space is waste that must be eliminated.

### 29.3. Before/After Measurements Must Look Beyond the Filesystem

Record heap size, index size, total relation size, dead tuple estimates, throughput, and latency. Compare measurements under matching workload conditions.

### 29.4. VACUUM FULL Does Not Guarantee Big Reductions

If the table is already compact or free space is small, a rewrite can spend time and disk for little gain.

### 29.5. Do Not Run FULL Just to "Make Dashboards Look Pretty"

Run it only with a concrete disk-reclaim/compaction goal after understanding locks, peak disk, and impact.

## 30. Freezing and the Visibility Map in Operations

Beyond cleanup, VACUUM maintains critical metadata for read performance and XID safety.

### 30.1. All-Visible Pages

The visibility map marks pages where all tuples are considered visible to all current transactions. Index-only scans can use this information to avoid visiting the heap in suitable cases.

### 30.2. All-Frozen Pages

A page is marked all-frozen once tuples on the page have been frozen under the corresponding conditions. This lets subsequent vacuums safely skip certain pages.

### 30.3. DML Clears Visibility Status

An UPDATE/INSERT on a page can require visibility information to be re-evaluated. A later VACUUM determines the new status.

### 30.4. VACUUM Is Not Only for Deleting Dead Rows

Even a table with little bloat still needs periodic vacuuming/freezing to maintain the visibility map and prevent XID wraparound.

### 30.5. VACUUM FULL Is Not the Only Freezing Strategy

Freezing behavior is governed by vacuum options and XID age; you do not need to rewrite the entire table just to ensure tuple freezing.

## 31. Checking XID Age and Wraparound Risk

XID age per database:

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
~~~

XID age per relation:

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    age(c.relfrozenxid) AS xid_age
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm')
ORDER BY xid_age DESC
LIMIT 30;
~~~

### 31.1. XID Age Is Not the Exact Number of Remaining Transactions

It is a metric for tracking the relative age of the frozen horizon. Interpret it alongside wraparound configuration and server warnings.

### 31.2. Inspect the Highest-Risk Database

The database with the largest age warrants investigation, along with the oldest relations, vacuum history, and worker activity.

### 31.3. Freeze Settings

Parameters such as `vacuum_freeze_min_age`, `vacuum_freeze_table_age`, and `autovacuum_freeze_max_age` govern freezing behavior. Do not change them based solely on a blog post or an isolated number.

### 31.4. Do Not Ignore Low-Traffic Databases

Low-write databases can still need vacuum freeze to prevent XID age from climbing. "Few dead tuples" does not mean "no vacuum needed".

### 31.5. Anti-Wraparound Is a High-Priority Condition

As the server nears safety limits, PostgreSQL can launch aggressive autovacuum and log warnings. Do not postpone or kill these workers arbitrarily.

## 32. Partitioned Tables and VACUUM

Partitioning creates one logical parent table and multiple leaf partitions with their own storage.

~~~text
sales.events (partitioned parent)
       |
       +-- events_2026_01 (heap)
       +-- events_2026_02 (heap)
       +-- events_2026_03 (heap)
~~~

### 32.1. Dead Tuples Live in Partitions

Leaf partitions are the relations that store rows. Autovacuum processes partitions based on each relation's own activity.

### 32.2. The Parent Table Has Separate Statistics

Autovacuum does not automatically refresh statistics on a partitioned parent the same way it handles leaf tables in some versions; when parent-level planner statistics are needed, run an appropriate ANALYZE on the parent per your version's documentation.

### 32.3. VACUUM Parent vs. Leaf

A VACUUM command on a partitioned table applies to partitions according to PostgreSQL semantics; if operating per partition, specify the exact target and monitor per-relation progress.

### 32.4. Retention via Partition Detach/Drop

If business requirements allow dropping data by month, detaching/dropping old partitions can avoid millions of DELETEs and reduce per-row VACUUM demand. However, this DDL still involves locks, foreign keys, dependencies, and archival requirements.

### 32.5. Do Not Blindly Schedule FULL Across All Partitions

Evaluate each partition's size, churn, and disk individually. An immutable partition does not need the same strategy as an actively written one.

## 33. Alternatives Beyond VACUUM FULL

### 33.1. Fix the Root Cause of Bloat

If a long transaction, forgotten replication slot, or unsuitable autovacuum threshold is responsible, fix the root cause before rewriting. Otherwise bloat will return immediately.

### 33.2. Partition Rotation

For time-expiring data, dropping/detaching partitions can remove large volumes of data far more efficiently than row-by-row DELETEs.

### 33.3. pg_repack

Can fit when you want to rewrite a table/index with shorter strong-lock windows than VACUUM FULL, though it requires compatible extensions/tools, triggers/log tables, temporary disk space, and operational testing.

### 33.4. CLUSTER

Used when you need rows physically reordered by an index. CLUSTER also rewrites the table and requires a strong lock; it is not a zero-downtime online solution.

### 33.5. REINDEX

If index bloat/corruption is the primary issue, evaluate regular or `CONCURRENTLY` REINDEX per index and version. Do not assume VACUUM FULL is the only option.

### 33.6. Fillfactor and HOT Updates

Adjusting fillfactor can leave page headroom for HOT updates, reducing index churn in suitable workloads. It is a design/tuning decision—it does not replace vacuum and does not compact an existing table by itself.

## 34. Commonly Used VACUUM Commands

~~~sql
-- Clean up one table
VACUUM sales.orders;

-- Clean up and update planner statistics
VACUUM (ANALYZE) sales.orders;

-- View detailed progress output
VACUUM (VERBOSE) sales.orders;

-- Clean up, freeze, and display details
VACUUM (FREEZE, VERBOSE) sales.orders;

-- Compact via rewrite, exclusive lock
VACUUM FULL sales.orders;

-- FULL while also updating statistics
VACUUM (FULL, ANALYZE, VERBOSE) sales.orders;
~~~

### 34.1. Do Not Run Inside BEGIN/COMMIT

VACUUM commands must run outside explicit transaction blocks. A migration tool that wraps every statement in a transaction may need a special mode.

### 34.2. VACUUM Without a Table Name

`VACUUM;` can vacuum all eligible tables in the current database. This is a broad operation; check scope and duration before running manually.

### 34.3. VACUUM FULL Is Not an ANALYZE Option

`FULL` changes how the relation is rewritten; `ANALYZE` requests planner stats collection. The two options serve different purposes and can be combined when appropriate.

### 34.4. VACUUM Does Not Delete Live Rows

If you want to delete business data, use DELETE/TRUNCATE/partition retention as required; VACUUM only reclaims expired tuple versions.

### 34.5. Referencing vacuumdb

The `vacuumdb` CLI tool can run VACUUM/ANALYZE across databases/tables from operational scripts. Available options depend on version; do not target the wrong database/host due to an old cron job.

## 35. Lab: Generating Dead Tuples

**Environment:** an isolated test database and a role with privileges to create schemas/tables. Do not run mass UPDATE/DELETE demonstrations on production.

~~~sql
CREATE SCHEMA vacuum_lab;

CREATE TABLE vacuum_lab.items (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO vacuum_lab.items(payload)
SELECT repeat('x', 500)
FROM generate_series(1, 100000);
~~~

### 35.1. Check Initial Row Count

~~~sql
SELECT count(*) FROM vacuum_lab.items;
~~~

### 35.2. UPDATE Creates New Versions

~~~sql
UPDATE vacuum_lab.items
SET payload = repeat('y', 500),
    updated_at = now()
WHERE id % 2 = 0;
~~~

### 35.3. DELETE Marks Rows

~~~sql
DELETE FROM vacuum_lab.items
WHERE id % 5 = 0;
~~~

### 35.4. Dead Tuple Statistics Are Estimates

After statistics update, check:

~~~sql
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    last_vacuum
FROM pg_stat_user_tables
WHERE schemaname = 'vacuum_lab';
~~~

If autovacuum runs too fast in the lab, estimates may look smaller than expected. You can temporarily adjust thresholds on the lab table to observe, then restore settings afterward.

### 35.5. Measure Size Before VACUUM

~~~sql
SELECT
    pg_size_pretty(pg_relation_size('vacuum_lab.items')) AS heap,
    pg_size_pretty(pg_total_relation_size('vacuum_lab.items')) AS total;
~~~

Record the numbers; do not expect the exact same byte counts as another machine because storage, page layout, and versions differ.

## 36. Lab: Running Standard VACUUM

~~~sql
VACUUM (VERBOSE, ANALYZE) vacuum_lab.items;
~~~

### 36.1. Re-Check Statistics

~~~sql
SELECT
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_analyze
FROM pg_stat_user_tables
WHERE schemaname = 'vacuum_lab'
  AND relname = 'items';
~~~

### 36.2. Reading VERBOSE

Output can report pages, dead tuples, index cleanup, and related actions. Exact output format varies by version.

### 36.3. Measure Size After VACUUM

~~~sql
SELECT
    pg_size_pretty(pg_relation_size('vacuum_lab.items')) AS heap,
    pg_size_pretty(pg_total_relation_size('vacuum_lab.items')) AS total;
~~~

The file may not shrink much because most space was marked reusable inside the relation. This is normal.

### 36.4. Try Inserting More Rows

~~~sql
INSERT INTO vacuum_lab.items(payload)
SELECT repeat('z', 500)
FROM generate_series(1, 10000);
~~~

VACUUM created opportunities to reuse free space. The database does not necessarily have to allocate corresponding extra disk for every new row, though exact behavior depends on page layout and free space levels.

### 36.5. Check Planner Statistics

`ANALYZE` in the command above updates statistics. That is why the query planner can change plans after the command, regardless of whether file size decreased.

## 37. Lab: Comparing Standard VACUUM and VACUUM FULL

To see the difference, test on a lab table large enough to hold substantial dead space. Record heap/total size, duration, lock wait, and free disk before/after.

~~~sql
VACUUM (VERBOSE) vacuum_lab.items;

SELECT
    pg_size_pretty(pg_relation_size('vacuum_lab.items')) AS heap_size,
    pg_size_pretty(pg_total_relation_size('vacuum_lab.items')) AS total_size;

VACUUM FULL (VERBOSE, ANALYZE) vacuum_lab.items;

SELECT
    pg_size_pretty(pg_relation_size('vacuum_lab.items')) AS heap_size,
    pg_size_pretty(pg_total_relation_size('vacuum_lab.items')) AS total_size;
~~~

### 37.1. Expected Result

Standard VACUUM mainly marks free space reusable; VACUUM FULL rewrites to compact, so the file is usually smaller if significant bloat existed beforehand.

### 37.2. Do Not Expect a Fixed Number

Sizes depend on payload, fillfactor, indexes, TOAST, compression, page layout, and autovacuum. The takeaway is the mechanism and trade-offs, not a fixed byte count.

### 37.3. VACUUM FULL Needs Temporary Disk

Before running, check disk capacity and keep a safe buffer. A small lab does not reflect production peak disk usage.

### 37.4. Compare Execution Time

Record execution duration and watch progress. FULL can take longer due to rewriting and index rebuilds.

### 37.5. FULL Blocks Traffic on the Table

Do not run tests on a real application table with active users. Use a second session to observe locking in the lab.

## 38. Two-Session Lab: Standard VACUUM and SELECT/DML

Open two terminal/psql sessions to the same lab database.

**Session A:**

~~~sql
BEGIN;
SELECT count(*) FROM vacuum_lab.items;
-- Keep transaction open to hold a relation lock.
~~~

**Session B:**

~~~sql
VACUUM (VERBOSE) vacuum_lab.items;
~~~

Standard VACUUM can acquire SHARE UPDATE EXCLUSIVE, which is compatible with ACCESS SHARE from the SELECT running in Session A. It can complete even while transaction A remains open, depending on other conditions.

### 38.1. Try Concurrent DML

While VACUUM is running in Session B, run a small UPDATE from Session C. VACUUM's SHARE UPDATE EXCLUSIVE is compatible with normal DML's ROW EXCLUSIVE.

### 38.2. End Session A

~~~sql
COMMIT;
~~~

Remember to finish transactions after the lab; long open sessions hold snapshots and affect cleanup.

### 38.3. Observe Locks

In a third session, run the query from the `pg_locks` section to inspect relation lock modes and `granted` status.

### 38.4. This Does Not Mean VACUUM Has Zero Latency Impact

It still competes for CPU/I/O, can increase workload latency, and can wait on DDL/maintenance.

## 39. Two-Session Lab: VACUUM FULL and ACCESS EXCLUSIVE

Use the lab table. Practice only in an isolated database.

**Session A:**

~~~sql
BEGIN;
SELECT count(*) FROM vacuum_lab.items;
-- Do not COMMIT yet.
~~~

**Session B:**

~~~sql
SET lock_timeout = '5s';
VACUUM FULL vacuum_lab.items;
~~~

### 39.1. Expectation

VACUUM FULL requires ACCESS EXCLUSIVE and must wait for transaction A to release ACCESS SHARE. With a short `lock_timeout`, the command fails because it cannot acquire the lock in time.

### 39.2. Release the Lock

In Session A:

~~~sql
COMMIT;
~~~

You can then retry VACUUM FULL in the lab once confirmed no blocker remains.

### 39.3. Try a New SELECT While FULL Holds the Lock

While FULL is rewriting, a SELECT from Session C blocks until FULL completes. Observe wait events/locks and stop testing once you have gathered enough data.

### 39.4. Do Not Arbitrarily Terminate Blockers in Production

If transaction A is a business transaction, terminating it rolls back work and triggers retries. Follow an incident/maintenance plan.

### 39.5. Understanding the Queue

A waiting ACCESS EXCLUSIVE request can force new lock requests to queue behind it depending on the lock queue. Thus FULL can cause impact even before starting the rewrite.

## 40. Lab: Checking Autovacuum and Freezing

View current settings:

~~~sql
SHOW autovacuum;
SHOW autovacuum_naptime;
SHOW autovacuum_max_workers;
SHOW autovacuum_vacuum_threshold;
SHOW autovacuum_vacuum_scale_factor;
SHOW autovacuum_freeze_max_age;
~~~

### 40.1. View XID Age per Database

~~~sql
SELECT datname, age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
~~~

### 40.2. View Vacuum History

~~~sql
SELECT
    schemaname,
    relname,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
WHERE schemaname = 'vacuum_lab';
~~~

### 40.3. Do Not Force Wraparound in the Lab

Do not attempt to generate billions of transactions or lower freeze thresholds dangerously to simulate wraparound. Read metrics and understand the mechanism on the test database.

### 40.4. Try Per-Table Thresholds

You can set low thresholds on the lab table to see autovacuum trigger sooner, while observing logs and restoring reloptions afterward.

### 40.5. Distinguish Autovacuum from Manual VACUUM

The `last_autovacuum` and `last_vacuum` columns show whether the latest run came from a background worker or a manual command.


## 28. When Should You Consider pg_repack or CLUSTER?

### 28.1. CLUSTER

`CLUSTER` rewrites a table in the order of a chosen index and requires an ACCESS EXCLUSIVE lock for the duration of the operation. It can physically reorder data, not just compact it.

### 28.2. pg_repack

`pg_repack` is an external extension/tool that can reorganize a table with shorter strong-lock durations in certain cases by tracking changes and syncing them. It has its own operational requirements, permissions, temporary disk needs, and compatibility constraints.

### 28.3. There Is No "Zero Lock" Option

Even online rewrite tools require lock phases for setup and cutover. Read the extension documentation for your exact version, check conflicts, and plan for rollback.

### 28.4. REINDEX Is a Separate Operation

If index bloat/corruption is the issue, evaluate targeted `REINDEX`. Standard VACUUM cleans up dead index entries; VACUUM FULL rebuilds indexes alongside the rewrite; not every index issue requires a FULL table rewrite.

### 28.5. Partition Lifecycle Can Beat Mass DELETE

For monthly/daily data, dropping/detaching old partitions can be far more effective than deleting millions of rows and running VACUUM FULL. However, partition detach/drop also involves locks, constraints, and dependencies to account for.




