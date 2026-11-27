# Impact of Unfinished Transactions on Data Cleanup in PostgreSQL

PostgreSQL uses **MVCC (Multi-Version Concurrency Control)** to let multiple transactions read and write data concurrently without forcing every read to wait on writes. In exchange, when a row is updated or deleted, the database engine usually cannot immediately erase the old version of that row from data pages. The old version may still be needed by a transaction reading against a snapshot taken before the change committed.

**`VACUUM` and autovacuum** are responsible for reclaiming reusable space left behind by versions that are no longer needed, while performing other maintenance work. However, a transaction left open too long can pin an **old enough visibility boundary** that prevents `VACUUM` from removing versions that look "dead." The consequences can include table and index bloat, queries scanning more pages, higher I/O, storage pressure, and heavier vacuum work later.

This problem is especially hard to spot when the application is not running any complex SQL: a connection in the **`idle in transaction`** state can keep a transaction open for a long time. Still, seeing an idle-in-transaction session does not automatically mean it is holding an old snapshot causing bloat. You must distinguish **how long the transaction has been open**, **which snapshot/XID is actually holding back cleanup**, and **other horizon holders** such as replication slots, standby feedback, or prepared transactions.

This lesson walks through the underlying mechanism, a two-connection experiment, diagnostics via PostgreSQL system views, safe production remediation choices, and practice exercises.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why `UPDATE`/`DELETE` do not automatically erase old row versions right away.
2. Describe the difference between **row versions still needed for a snapshot**, **reclaimable dead tuples**, and **space already marked reusable**.
3. Understand **visibility horizon** and how it relates to open transactions, `backend_xmin`, and `backend_xid`.
4. Demonstrate with a two-session experiment that a long-held `REPEATABLE READ` snapshot restricts `VACUUM` from cleaning up row versions.
5. Distinguish `READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE`, and `idle in transaction` scenarios.
6. Monitor `pg_stat_activity`, `pg_stat_user_tables`, `pg_stat_progress_vacuum`, and other horizon holders.
7. Explain the roles of autovacuum, freezing, and transaction ID wraparound risk.
8. Analyze the impact of standby feedback, replication slots, and prepared transactions on data maintenance.
9. Establish a workflow to investigate, mitigate, and prevent issues without arbitrarily killing critical transactions.
10. Choose between `VACUUM`, `VACUUM FULL`, and other operational actions based on the true root cause.

## 2. How Does MVCC Store Multiple Row Versions?

Consider an order row:

```text
id = 101, status = 'pending'
```

Another transaction updates its status:

```sql
UPDATE orders
SET status = 'completed'
WHERE id = 101;
```

In PostgreSQL, logically the engine can create a **new tuple version** for the updated row while the old version is not physically erased immediately.

```text
Before UPDATE:

  [tuple V1: id=101, status=pending]

After UPDATE, before all old snapshots stop needing it:

  [tuple V1: id=101, status=pending] ── old version
                  |
                  v
  [tuple V2: id=101, status=completed] ── new version

Transaction with old snapshot: can see V1
Transaction with new snapshot: can see V2
```

This is a **conceptual** diagram. Internally, PostgreSQL uses transaction ID fields in the tuple header such as `xmin` and `xmax`, commit/abort status, and visibility rules to decide which version is visible. Never naively interpret those fields as wall-clock time or business record IDs.

### 2.1. What Do UPDATE and DELETE Leave Behind?

- `INSERT` creates a new row version.
- `UPDATE` normally creates a new row version and marks the old version as no longer current once the update is confirmed.
- `DELETE` marks the row version as no longer visible to sufficiently new snapshots once the delete is confirmed.
- `ROLLBACK` makes versions created by a failed transaction unusable.

`VACUUM` cleans up versions that are no longer needed. However, a transaction having committed **does not mean every old tuple from it is immediately safe to remove**.

### 2.2. Why Doesn't PostgreSQL Delete Immediately?

Suppose:

```text
Session A                         Session B
---------                         ---------
BEGIN REPEATABLE READ
SELECT status -> 'pending'

                                  UPDATE status='completed'
                                  COMMIT

SELECT status -> 'pending'
COMMIT
```

Session A must be able to keep reading the version consistent with its snapshot. If B or `VACUUM` physically deleted V1 right after B committed, A would lose the version it is still entitled to see.

This is the core trade-off of MVCC: **consistent reads and concurrency** in exchange for storing old versions until it is safe to remove them.

### 2.3. "Dead Tuple" Has Multiple Perspectives

In operations, *dead tuple* often refers loosely to any old row version no longer in the current state. At the visibility level, however:

- A tuple can be **no longer visible to new snapshots** yet **still needed** by an old snapshot.
- A tuple becomes **removable** once no snapshot/transaction needs it anymore.
- A version created by a rolled-back transaction becomes dead because its creating transaction never committed.

Therefore, never assume all old tuples become immediately cleanable right after an `UPDATE` finishes. And never treat `n_dead_tup` as an exact real-time count of removable tuples.

## 3. What Work Does VACUUM Perform?

`VACUUM` is PostgreSQL's essential maintenance mechanism. Depending on table state and PostgreSQL version, it can:

- Identify dead tuples that are **safe to clean**, making table space reusable for future operations.
- Clean index entries pointing to removed tuples, per index cleanup phases and options.
- Update the visibility map, marking pages all-visible or all-frozen when conditions are met.
- Contribute to **freezing transaction IDs** to prevent wraparound problems.
- Update related maintenance statistics; when running `VACUUM ANALYZE`, also gather statistics for the planner.
- In some cases, truncate trailing empty pages at the end of the table file if conditions allow.

### 3.1. What Regular VACUUM Does Not Guarantee

**`VACUUM` usually does not return every byte of bloat back to the operating system immediately.** Once cleanup finishes, space inside data pages normally becomes **reusable space within the table**. File size may not shrink proportionally.

To shrink physical files aggressively, a rewrite operation like `VACUUM FULL` may be needed, which requires extra disk space, time, and strong locks. Running `VACUUM FULL` before identifying the root cause can cause severe disruption without fixing an active long-running transaction.

### 3.2. VACUUM ANALYZE

`VACUUM` and `ANALYZE` serve related but distinct goals:

- `VACUUM`: cleans row versions, visibility metadata, freezing, and maintenance.
- `ANALYZE`: samples/updates planner statistics such as row counts and column distributions for query planning.

`VACUUM (ANALYZE) schema.table` combines both. `ANALYZE` cannot "force" `VACUUM` to remove versions still needed by a snapshot.

## 4. The Safety Boundary for Cleanup (Visibility Horizon)

`VACUUM` cannot simply ask: "Did the `UPDATE` transaction commit?" and delete all old versions. It must check **which transactions/snapshots could still need to see those versions**.

We can picture a logical timeline:

```text
       old transaction/snapshot             new transaction
--------------------|------------------|------------------------->
                    A                  B
                    |                  |
              A holds snapshot    B UPDATE + COMMIT

Old version before B:
  - New transaction after B: does not need old version.
  - A's old snapshot:        may still need old version.

VACUUM:
  - Must not clean old version while A still needs it.
  - Can clean once no snapshot/transaction needs it,
    alongside meeting other safety conditions.
```

The boundary `VACUUM` must respect is often called **oldest xmin**, **cleanup horizon**, or visibility horizon, depending on context, version, and internals. The general concept: PostgreSQL must know the **oldest transaction point still relevant to visibility**.

### 4.1. Distinguishing Transaction ID From Wall-Clock Time

PostgreSQL assigns **transaction IDs (XIDs)** when needed to manage MVCC. An XID is not:

- A Unix timestamp.
- A `now()` value.
- A global counter that increases forever without wrapping.
- An order ID or connection session ID.

The diagram above illustrates old-vs-new ordering only, not an exact formula between wall-clock time and horizon. In reality, the cleanup horizon is determined from transactions/snapshots and other holders, not simply elapsed minutes.

### 4.2. backend_xmin and backend_xid

`pg_stat_activity` includes relevant fields:

| Field | Common Meaning |
| --- | --- |
| `xact_start` | Timestamp when the backend's current transaction started (if any). |
| `backend_xid` | Top-level XID of the current backend, if assigned. |
| `backend_xmin` | The `xmin` boundary of the snapshot the backend is currently holding, if any. |
| `state` | State such as `active`, `idle in transaction`, `idle in transaction (aborted)`. |
| `query_start` | Start time of the active query; for idle sessions, typically the last query. |
| `state_change` | Timestamp of the most recent state transition. |

**Note:** `xact_start` can be non-NULL while `backend_xmin` is NULL. A transaction that opened long ago **does not automatically keep holding an old snapshot continuously**. Conversely, a backend with an old `backend_xmin` can pin the cleanup horizon even when the SQL query visible to an administrator looks trivial.

### 4.3. High XID Age and the Cleanup Horizon

PostgreSQL can display `age(backend_xmin)` or `age(backend_xid)` to guide investigation, but understand:

- `age(xid)` is the **logical age of the XID** relative to current XID, not minutes or hours.
- A session with an old `xact_start` does not necessarily have a non-NULL `backend_xmin`.
- `backend_xid` and `backend_xmin` represent two different aspects; inspect both.
- Cleanup is also constrained by standby feedback, replication slots, and prepared transactions, not just regular client backends.

Merely looking at `pg_stat_activity` and declaring "no old transactions exist" is not enough to conclude nothing is holding back `VACUUM`.

## 5. What Can a Long-Open Transaction Cause?

The impact typically unfolds as a chain:

```text
Application holds old transaction/snapshot
                     |
                     v
   VACUUM cannot clean all obsolete tuples
                     |
                     v
      Dead/old row versions accumulate
                     |
             +-------+--------+
             |                |
             v                v
    Table/index size    VACUUM must do more
        grows              work later
             |                |
             +-------+--------+
                     |
                     v
   Higher I/O, cache pressure, query cost,
   disk usage, and risk to write operations
```

Specific impacts:

1. **Table bloat:** many old versions remain in heap pages, causing the table to expand even when logical row counts do not grow.
2. **Index bloat:** depending on update patterns and HOT eligibility, new versions generate index entries; `VACUUM` may also be blocked from cleaning them.
3. **Reading more pages:** sequential scans traverse more physical blocks; index scans may visit the heap more often.
4. **Wasted cache:** the buffer pool fills with obsolete data that cannot yet be reclaimed for reuse.
5. **Higher I/O and WAL:** ongoing `UPDATE`/`DELETE`s keep producing changes; later maintenance becomes heavy.
6. **Storage pressure:** table/index files grow, triggering disk alerts or running out of space.
7. **Operational wraparound risk:** old transaction IDs can prevent freezing from advancing as needed, increasing anti-wraparound pressure.

Not every long transaction produces all of these consequences. For example, a `READ COMMITTED` transaction without a held snapshot on a mostly read workload may not cause noticeable bloat. Always correlate **blocker info + write activity + table stats + replication** to confirm the real cause.

## 6. READ COMMITTED vs. REPEATABLE READ: Subtle Differences

### 6.1. READ COMMITTED

At the default `READ COMMITTED` isolation level, statements normally acquire a snapshot at the start of each statement. After a read statement finishes, that statement-specific snapshot can be released; the next statement can see newer committed data.

Thus, a session doing:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;
SELECT COUNT(*) FROM some_table;
-- Leave session idle for a very long time.
```

does not necessarily keep holding **the old `SELECT`'s snapshot** throughout the idle period. However, the session still has an open transaction; it may hold locks, may have been assigned an XID from earlier writes, or may have a portal/cursor or other mechanism holding a snapshot. Never assume a session is harmless merely because its isolation level is `READ COMMITTED`.

### 6.2. REPEATABLE READ

Under `REPEATABLE READ`, the transaction gets a transaction-wide snapshot per PostgreSQL rules, typically from the first statement requiring one. Subsequent reads in the same transaction share that consistent snapshot context.

Consequently, a transaction sitting idle after a `SELECT` under `REPEATABLE READ` can **hold an old snapshot** while other transactions continuously `UPDATE`/`DELETE`.

Example:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT COUNT(*) FROM some_table;
-- No COMMIT or ROLLBACK for 30 minutes.
```

This is the classic situation where `VACUUM` may be prevented from cleaning up row versions modified after that old snapshot.

### 6.3. SERIALIZABLE

`SERIALIZABLE` guarantees semantics equivalent to a valid serial order via PostgreSQL's mechanisms. A transaction at this level can hold snapshots and dependency-tracking structures in ways that affect operations; overly long transactions also increase serialization conflict rates.

Never use `SERIALIZABLE` just to get a consistent report without understanding requirements, transaction duration, and retry policies. Conversely, never casually lower isolation on critical business logic just to reduce bloat.

### 6.4. Comparison

| Scenario | Can Hold Old Snapshot Restricting VACUUM? | Note |
| --- | --- | --- |
| Short autocommit `SELECT` | Usually only for the statement's duration. | Very brief hold when finishing quickly. |
| `READ COMMITTED` transaction, idle after `SELECT` | **Not necessarily** holding the old read snapshot. | Still inspect XID, locks, portals, and state. |
| `REPEATABLE READ` transaction, idle after `SELECT` | **Can** hold the old transaction snapshot. | Easy to reproduce in a lab. |
| Transaction ran `UPDATE`, not yet `COMMIT`ted | Can hold XID/locks and restrict cleanup. | Uncommitted row versions cannot be treated as fully dead yet. |
| Errored transaction, `idle in transaction (aborted)` | Can still hold resources and locks per actual state. | Must roll back / end transaction; cannot run arbitrary SQL until then. |
| Session closed / transaction rolled back | Snapshot/transaction normally ends. | Other horizon holders may still exist. |

## 7. Preparing the Two-Session Lab

We will intentionally create a transaction holding an old snapshot and observe `VACUUM` from another session.

**Important:** run examples only in a lab database or authorized environment. The example `UPDATE`s many rows and runs `VACUUM`, which is unsuitable to run casually on production tables. Never run these scripts inside an application connection pool serving live users.

### 7.1. Creating Schema and Table

In one PostgreSQL session:

```sql
CREATE SCHEMA IF NOT EXISTS mvcc_cleanup_lab;

CREATE TABLE mvcc_cleanup_lab.demo_rows (
    row_id bigint PRIMARY KEY,
    payload text NOT NULL,
    generation integer NOT NULL DEFAULT 0
);

INSERT INTO mvcc_cleanup_lab.demo_rows (row_id, payload)
SELECT g, repeat('x', 100)
FROM generate_series(1, 3000) AS g;

CREATE INDEX idx_demo_rows_generation
ON mvcc_cleanup_lab.demo_rows (generation);

ANALYZE mvcc_cleanup_lab.demo_rows;
```

The initial dataset has 3,000 rows with `generation=0`.

Verify:

```sql
SELECT
    COUNT(*) AS row_count,
    MIN(generation) AS min_generation,
    MAX(generation) AS max_generation
FROM mvcc_cleanup_lab.demo_rows;
```

Initial result:

| row_count | min_generation | max_generation |
| ---: | ---: | ---: |
| 3000 | 0 | 0 |

Note: `generation` is indexed, so `UPDATE`s changing it normally do not qualify for HOT updates on this index, making index entries and old tuple versions easier to observe. However, exact disk growth depends on page layout, `fillfactor`, version, and PostgreSQL execution.

### 7.2. Opening Two Independent Sessions

Prepare:

- **Session A:** opens a `REPEATABLE READ` transaction and holds the snapshot.
- **Session B:** updates data, commits, and runs `VACUUM`.

Each session must use **a separate connection** to the same database. Open two `psql` windows or two GUI tabs configured with separate database connections. Multiple SQL tabs in one GUI do not automatically mean two sessions.

To verify:

```sql
SELECT pg_backend_pid() AS session_pid;
```

The two sessions must have two different backend PIDs.

## 8. Experiment: Old Snapshot Retains Row Versions

### 8.1. Session A: Establish Snapshot and Keep Transaction Open

In **Session A**:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT
    pg_backend_pid() AS session_a_pid,
    COUNT(*) AS row_count,
    MIN(generation) AS min_generation,
    MAX(generation) AS max_generation
FROM mvcc_cleanup_lab.demo_rows;
```

Result:

```text
row_count = 3000
min_generation = 0
max_generation = 0
```

**Keep Session A open**—do not `COMMIT` or `ROLLBACK`. The `SELECT` established the snapshot context for the `REPEATABLE READ` transaction.

### 8.2. Session B: Modify Rows After A's Snapshot

In **Session B** in autocommit mode:

```sql
UPDATE mvcc_cleanup_lab.demo_rows
SET
    generation = generation + 1,
    payload = repeat('y', 100);

SELECT
    COUNT(*) AS row_count,
    MIN(generation) AS min_generation,
    MAX(generation) AS max_generation
FROM mvcc_cleanup_lab.demo_rows;
```

Result in B:

```text
row_count = 3000
min_generation = 1
max_generation = 1
```

Session B committed the autocommit `UPDATE`. The database now has new versions plus old versions that Session A may still need.

### 8.3. Session A Still Sees the Old Version

Return to **Session A**:

```sql
SELECT
    COUNT(*) AS row_count,
    MIN(generation) AS min_generation,
    MAX(generation) AS max_generation
FROM mvcc_cleanup_lab.demo_rows;
```

The result is still `generation=0` for all 3,000 rows, because A's `REPEATABLE READ` snapshot is preserved.

Two sessions return **two different results on the same table** without error:

| Session | Snapshot | Observed Value |
| --- | --- | --- |
| A | Established before B's `UPDATE`. | `generation=0`. |
| B | Fresh snapshot after `UPDATE` committed. | `generation=1`. |

This is precisely why `VACUUM` cannot arbitrarily delete `generation=0` versions while A might still read them.

### 8.4. Session B Runs VACUUM While A Is Open

In **Session B**:

```sql
VACUUM (VERBOSE, ANALYZE) mvcc_cleanup_lab.demo_rows;
```

Regular `VACUUM` must execute **outside a transaction block**; make sure Session B is not inside an open `BEGIN ... COMMIT`.

`VACUUM` completes successfully yet **cannot remove the old versions still needed by A's snapshot**. In `VERBOSE` output or stats, depending on PostgreSQL version, you may see details about non-removable tuples, remaining versions, or limited cleanup.

Do not expect identical fixed log wording across all PostgreSQL major versions. Understand correctness from the existence of A's snapshot and visibility bounds, not just a single estimated number.

### 8.5. Diagnosing Session A From Session B

In **Session B**, substitute `<PID_A>` with the PID recorded in Session A, or filter by database and state:

```sql
SELECT
    pid,
    state,
    xact_start,
    backend_xid,
    backend_xmin,
    query_start,
    state_change
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;
```

Session A will likely show `state='idle in transaction'`, an older `xact_start`, and while holding the snapshot, `backend_xmin` reflecting the session's horizon.

Another writing backend may be active; exact backends and values depend on client, version, and observation time.

### 8.6. Ending Session A

In **Session A**:

```sql
COMMIT;
```

Session A no longer needs the old snapshot. If no other horizon holder exists, PostgreSQL now has the opportunity to clean the previously blocked old tuples.

In **Session B**:

```sql
VACUUM (VERBOSE, ANALYZE) mvcc_cleanup_lab.demo_rows;
```

Now cleanup of the `generation=0` versions becomes possible, subject to other visibility conditions.

**Do not expect the table file to necessarily shrink after the second VACUUM.** Space can simply be marked reusable for future `UPDATE`/`INSERT`s. `VACUUM FULL` is a different operation and is not needed for this experiment.

### 8.7. What If A Ran ROLLBACK Instead of COMMIT?

Session A in this experiment is read-only. `ROLLBACK` also ends the transaction and releases the snapshot. For testing retention, either `COMMIT` or `ROLLBACK` in A stops holding that snapshot boundary.

If A held uncommitted `UPDATE`s, `ROLLBACK` would discard A's changes too; always verify what work a transaction is doing before ending it.

### 8.8. Checking the Final Result

```sql
SELECT
    COUNT(*) AS row_count,
    MIN(generation) AS min_generation,
    MAX(generation) AS max_generation
FROM mvcc_cleanup_lab.demo_rows;
```

In Session B after the `UPDATE`, the table still has 3,000 logical rows with `generation=1`. Cleaning old versions does not mean business rows are lost. Distinguish between:

- **Currently visible rows**.
- **Physical row versions that ever existed**.
- **Heap/index file sizes**.
- **Internal space inside files available for reuse**.

## 9. Do Not Rely on n_dead_tup as an Absolute Measurement

The `pg_stat_user_tables` view includes `n_dead_tup` — an **estimate** of dead tuples based on accumulated statistics.

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_tup_hot_upd,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
WHERE schemaname = 'mvcc_cleanup_lab'
  AND relname = 'demo_rows';
```

Meaning:

| Field | Interpretation |
| --- | --- |
| `n_live_tup` | Estimated count of live rows. |
| `n_dead_tup` | Estimated count of dead tuples, not an exact heap scan count. |
| `n_tup_upd` / `n_tup_del` | Recorded `UPDATE`/`DELETE` activity. |
| `n_tup_hot_upd` | Recorded `UPDATE`s that used Heap-Only Tuple (HOT). |
| `last_vacuum` | Most recent manual `VACUUM` recorded in stats. |
| `last_autovacuum` | Most recent autovacuum recorded in stats. |
| `vacuum_count` / `autovacuum_count` | Recorded vacuum execution counts. |

### 9.1. Why Can Numbers "Disagree"?

`pg_stat_*` statistics:

- Are not exact heap scans on every query.
- Have reporting/flush lag depending on version.
- Can be affected by open transactions and cached stats snapshots.
- Change across `VACUUM`/`ANALYZE` runs and concurrent activity.
- Can be reset by administrative commands.

A single `SELECT n_dead_tup` is not enough to prove Session A alone pinned all dead tuples or exactly how many bytes `VACUUM` reclaimed or missed.

For deeper investigation, combine `pg_stat_activity`, `VACUUM VERBOSE` logs, relation sizes, vacuum progress, and (if permitted by your organization) dedicated bloat-inspection tools/extensions.

### 9.2. pg_stat_clear_snapshot When Monitoring Statistics

Where statistics snapshots are cached, `pg_stat_clear_snapshot()` can force the next stats read to fetch fresh metrics per PostgreSQL behavior:

```sql
SELECT pg_stat_clear_snapshot();
```

However, this command **does not clean heap tuples**, does not replace `VACUUM`, and does not alter the MVCC snapshot used for reading table data in a transaction. It only affects reading monitoring statistics.

## 10. Table and Index Sizes: Measuring the Right Metrics

To observe physical growth, PostgreSQL provides size functions:

```sql
SELECT
    pg_size_pretty(
        pg_relation_size('mvcc_cleanup_lab.demo_rows')
    ) AS heap_size,
    pg_size_pretty(
        pg_indexes_size('mvcc_cleanup_lab.demo_rows')
    ) AS indexes_size,
    pg_size_pretty(
        pg_total_relation_size('mvcc_cleanup_lab.demo_rows')
    ) AS total_size;
```

### 10.1. Different Sizes

- `pg_relation_size(...)`: size of the relation's main fork with one argument for a regular table; excludes indexes and other forks.
- `pg_indexes_size(...)`: total size of indexes attached to the relation.
- `pg_total_relation_size(...)`: total relation size including associated components like indexes and TOAST per PostgreSQL's calculation.
- `pg_size_pretty(...)`: simply formats byte counts into human-readable strings.

For exact numeric comparisons, inspect raw bytes rather than only pretty strings:

```sql
SELECT
    pg_relation_size('mvcc_cleanup_lab.demo_rows') AS heap_bytes,
    pg_indexes_size('mvcc_cleanup_lab.demo_rows') AS index_bytes,
    pg_total_relation_size('mvcc_cleanup_lab.demo_rows') AS total_bytes;
```

### 10.2. Why Doesn't VACUUM Always Shrink total_bytes?

Suppose a 100 MB table file contains many pages of old tuples:

```text
Before VACUUM:
 [page with live rows][page with old tuples][page with live rows]...

After VACUUM:
 [page with live rows][reusable free space][page with live rows]...
```

PostgreSQL can reuse free space on existing pages for subsequent `INSERT`/`UPDATE`s. That avoids growing the file further, even though the existing file keeps its allocated size on the filesystem.

Therefore, seeing `pg_total_relation_size` stay the same after `VACUUM` and declaring vacuum "failed" is incorrect.

## 11. HOT Updates, Pruning, and Index Cleanup

PostgreSQL uses **HOT (Heap-Only Tuple) updates** under certain conditions, typically when an `UPDATE` does not change indexed columns in a way that prevents HOT and enough free space exists on the page.

### 11.1. How Does HOT Relate to Bloat?

HOT avoids creating new index entries for every updated version and lets heap page pruning clean more efficiently. However:

- HOT still creates new row versions.
- Old tuple versions still obey MVCC visibility.
- An old snapshot still restricts cleaning versions it might need.

### 11.2. Page Pruning Differs From VACUUM

PostgreSQL can prune/collapse parts of HOT chains during page accesses when safe. Yet page pruning is also forbidden from breaking visibility for old snapshots.

**Do not confuse:** "autovacuum hasn't run" does not mean zero cleanup happened, since pruning can run during other operations. Conversely, "autovacuum just ran" does not mean every obsolete tuple was eligible for removal.

### 11.3. Index Entries

`UPDATE`s changing indexed columns generate multiple index entries corresponding to row versions. `VACUUM` runs index cleanup phases when eligible, but cannot remove entries still required to preserve access paths to tuples visible to old snapshots.

When a retention issue lasts a long time, bloat can accumulate in both **heap and indexes**. Ending the blocker and running only `ANALYZE` is not enough; check vacuum and index cleanup status.

## 12. How Is Autovacuum Triggered?

Autovacuum is PostgreSQL's background mechanism to `VACUUM`/`ANALYZE` tables when eligible. An approximate model for the `VACUUM` trigger from `UPDATE`/`DELETE` is:

\[
\text{trigger} \approx
\text{autovacuum\_vacuum\_threshold}
+ \text{autovacuum\_vacuum\_scale\_factor}
\times \text{estimated\_table\_size}
\]

Modern versions and configurations also include insert-driven vacuuming, maximum thresholds, and anti-wraparound triggers, so this formula is a **basic model**, not a full specification of autovacuum scheduling.

Hypothetical example:

- `autovacuum_vacuum_threshold = 50`.
- `autovacuum_vacuum_scale_factor = 0.2`.
- Table estimated at 100,000 rows.

The model threshold is roughly `50 + 0.2 × 100000 = 20050` dead tuples before becoming eligible for vacuum under this criterion. Real settings can vary.

### 12.1. Viewing Configuration

```sql
SHOW autovacuum;
SHOW autovacuum_vacuum_threshold;
SHOW autovacuum_vacuum_scale_factor;
SHOW autovacuum_analyze_threshold;
SHOW autovacuum_analyze_scale_factor;
SHOW autovacuum_max_workers;
SHOW autovacuum_naptime;
```

Defaults, scope, and parameter names can vary across PostgreSQL major versions. In addition to server-level settings, tables can have per-table **storage parameters**.

### 12.2. Changing Thresholds Cannot Bypass Snapshots

Lowering scale factors so autovacuum runs more often helps write-heavy tables, but:

**Even frequent autovacuum cannot remove tuple versions still needed by valid snapshots/XIDs.**

If the obstacle is an unfinished old transaction, merely adding workers or lowering `naptime` will not fix retention. Identify and resolve the horizon holder first.

### 12.3. Autovacuum Must Not Be Disabled Arbitrarily

Disabling autovacuum long-term causes dead tuple buildup and transaction ID wraparound risks. Some anti-wraparound tasks trigger under special rules even when normal settings are restricted.

In production, never disable autovacuum as a quick fix to reduce I/O without a thoroughly evaluated alternative maintenance plan.

## 13. Freezing and Transaction ID Wraparound Risk

Transaction IDs in PostgreSQL have a finite identifier space; the system must manage **XID wraparound** safely.

### 13.1. What Does Freezing Do?

`VACUUM` can "freeze" old transaction ID metadata on eligible tuples so they continue appearing validly committed even after transaction IDs advance very far.

Relation `relfrozenxid` and database `datfrozenxid` track transaction ID age boundaries requiring maintenance.

```sql
SELECT
    current_database() AS database_name,
    age(datfrozenxid) AS database_xid_age
FROM pg_database
WHERE datname = current_database();
```

And per table:

```sql
SELECT
    n.nspname AS schema_name,
    c.relname,
    age(c.relfrozenxid) AS table_xid_age
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'mvcc_cleanup_lab'
  AND c.relname = 'demo_rows';
```

Here `age(...)` is a **count in transaction ID space**, not duration in minutes or hours.

### 13.2. Why Can Old Snapshots/XIDs Be Dangerous?

An old transaction or horizon can stop PostgreSQL from advancing cleanup/freeze boundaries as far as needed. If new transactions accumulate rapidly, distance to wraparound safety thresholds shrinks.

Upon hitting safety thresholds, PostgreSQL triggers aggressive/anti-wraparound vacuuming, operational warnings, and in severe cases refuses transactions requiring new XIDs to protect data integrity.

This is an operational availability risk, not "just losing a few megabytes of disk." Monitor XID age and clear blockers well before reaching danger thresholds.

### 13.3. Related Settings

```sql
SHOW autovacuum_freeze_max_age;
SHOW vacuum_freeze_min_age;
SHOW vacuum_freeze_table_age;
```

These parameters control vacuum aggressiveness and freezing; never adjust thresholds casually just to silence alerts without understanding safety bounds. Changing settings never allows PostgreSQL to ignore an old snapshot and delete still-visible versions.

### 13.4. Monitoring Highest XID Age Across Databases

```sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_database
WHERE datallowconn
ORDER BY xid_age DESC;
```

A database with high XID age must be evaluated alongside current settings, autovacuum logs, replication, and other oldest-XID holders. You cannot diagnose solely from an age number without context.

## 14. Operational Pitfall: Vacuum Runs Yet Dead Tuples Remain

A DBA receives an alert:

```text
n_dead_tup rising
autovacuum_count increasing
last_autovacuum is recent
heap/index size still growing
```

The right diagnosis is not immediately "autovacuum is broken." Autovacuum may be running right on schedule yet constrained by the **oldest visibility horizon**.

### 14.1. Other Possibilities to Distinguish

1. **Long-running transaction holding snapshot/XID:** old tuple versions are not yet removable.
2. **Very high write rate:** vacuum cleans, yet cannot keep pace with dead tuple generation.
3. **Suboptimal autovacuum configuration:** triggers too infrequent, worker/cost/memory limits mismatched.
4. **Autovacuum canceled or lock-contended:** runs fail to complete as expected.
5. **Replicas / slots / prepared transactions:** holding horizons outside regular application backends.
6. **Pre-existing bloat:** `VACUUM` reuses space without shrinking file sizes.
7. **Stats lag or estimation:** `n_dead_tup` is not an exact instantaneous count.

Verify the exact situation before tuning server parameters or killing queries.

### 14.2. Why Is Running VACUUM FULL First Usually the Wrong Move?

`VACUUM FULL` rewrites the table and takes a strong lock (`ACCESS EXCLUSIVE` on the target relation), blocking reads and writes for significant durations. It also requires extra disk space to rebuild the data.

If the old blocker remains active, the issue will simply return afterward. Do not turn a retention bug fixable in the application into unnecessary downtime from a table rewrite.

### 14.3. VACUUM (VERBOSE) After Clearing the Blocker

```sql
VACUUM (VERBOSE, ANALYZE) mvcc_cleanup_lab.demo_rows;
```

Once old snapshots are gone, `VACUUM` can clean up additional tuples per actual conditions. If reducing physical file size immediately is required, evaluate a rewrite/reindex strategy and downtime window separately as an operational decision.

## 15. Diagnosing Long Transactions With pg_stat_activity

This is a key monitoring query for this lesson:

```sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    client_addr,
    state,
    clock_timestamp() - xact_start AS transaction_age,
    clock_timestamp() - state_change AS state_age,
    backend_xid,
    backend_xmin,
    CASE
        WHEN backend_xmin IS NULL THEN NULL
        ELSE age(backend_xmin)
    END AS snapshot_xid_age,
    LEFT(query, 150) AS query_sample
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start NULLS LAST;
```

Purpose:

- Find sessions with transactions open for a long time.
- See whether the session is `active` or `idle in transaction`.
- Check whether `backend_xmin` and `backend_xid` are set.
- Identify user/application/client to trace the owner.
- Inspect the most recent query sample (which may not be all SQL run in the transaction).

### 15.1. Interpreting transaction_age

`transaction_age` is elapsed wall-clock time since the transaction started. It helps prioritize investigation, but **does not directly measure how many old tuples are being retained**.

A 30-minute session with an old `backend_xmin` can matter far more than a 2-hour session holding no relevant snapshot or XID, depending on workload and system.

Never enforce a universal "over 5 minutes definitely causes bloat" threshold across every system.

### 15.2. Interpreting state_age

`state_age` shows how long the backend has been in its current state. For example:

- `idle in transaction` for 10 minutes: the application may have left an open transaction without issuing new SQL.
- `active` for 10 minutes: could be a long query, lock wait, batch job, or `VACUUM`.
- `idle in transaction (aborted)`: the transaction hit an error and has not been ended properly.

To investigate blocking, include `wait_event_type` and `wait_event` from `pg_stat_activity`.

### 15.3. Inspecting backend_xid and backend_xmin Together

```sql
SELECT
    pid,
    state,
    xact_start,
    backend_xid,
    backend_xmin
FROM pg_stat_activity
WHERE datname = current_database()
  AND (
      backend_xid IS NOT NULL
      OR backend_xmin IS NOT NULL
      OR state LIKE 'idle in transaction%'
  )
ORDER BY xact_start NULLS LAST;
```

If `backend_xmin` is NULL, you still cannot conclude "the session cannot possibly obstruct vacuum" from that field alone: an unfinished XID, cursor/portal, prepared transaction, or replication feedback may still need checking. Conversely, a present `backend_xmin` must be compared against other horizons to assess true impact.

### 15.4. Visibility Permissions

Query text and session details of other users may be restricted by PostgreSQL privileges. Monitoring operators should use appropriate monitoring roles such as `pg_monitor` or `pg_read_all_stats` per policy, rather than granting superuser broadly.

Never paste raw `query` text containing sensitive literals into tickets or unprotected logs. Truncating to 150 characters reduces length, but **does not guarantee sensitive data isn't exposed** when SQL uses inline literals.

## 16. Monitoring Active VACUUM With pg_stat_progress_vacuum

PostgreSQL provides `pg_stat_progress_vacuum` to inspect currently running `VACUUM` progress:

```sql
SELECT
    pid,
    relid::regclass AS relation_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed
FROM pg_stat_progress_vacuum
ORDER BY pid;
```

Available columns and detailed meanings can change across PostgreSQL major versions, though core phases typically cover:

- Scanning heap for tuples needing cleanup.
- Vacuuming indexes per chosen strategies.
- Vacuuming heap.
- Cleaning up indexes/metadata and finishing.

### 16.1. Zero Rows Does Not Mean VACUUM Is Disabled

The progress view only shows `VACUUM` operations currently executing at query time. Once autovacuum finishes, it disappears from this view. Check `last_autovacuum`/`autovacuum_count` and logs to confirm history.

### 16.2. VACUUM Can Complete Without Removing Many Rows

If a scan encounters dead tuples that the visibility horizon forbids removing, `VACUUM` still performs its other duties and completes normally. Therefore:

**"VACUUM completed" does not equal "all old row versions were reclaimed."**

Conversely, if `VACUUM` runs unusually long, distinguish large table scans, I/O contention, index cleanup, locking, and heavy concurrent writes before blaming an idle transaction.

## 17. Another Horizon Holder: Standby Feedback

A PostgreSQL primary may have read replicas (*hot standby*) serving reporting queries or high availability. A replica can hold long read snapshots while the primary is updating/deleting data.

### 17.1. Cleanup Conflict Between Primary and Standby

```text
Primary                                Standby
-------                                -------
UPDATE/DELETE
    |
    +-- creates old tuples
    |
VACUUM wants to remove old tuples
                                       Long query needs old snapshot
    |                                       |
    +---------- conflict to resolve --------+
```

PostgreSQL has mechanisms to handle conflicts between WAL replay and standby queries. If configured appropriately with `hot_standby_feedback` on the standby, the replica sends its XID horizon back to the primary so the primary **delays cleaning up** versions standby queries still need.

Trade-off:

- Reduces standby queries getting canceled due to recovery conflicts.
- Can increase bloat on the primary because vacuum retains versions longer.

### 17.2. Checking Configuration on the Replica

On the relevant standby:

```sql
SHOW hot_standby_feedback;
```

Reading the setting alone does not tell you whether a query is currently holding a horizon; inspect streaming/replay state and active snapshots.

### 17.3. Inspecting Replication Info on the Primary

On the primary with appropriate privileges:

```sql
SELECT
    pid,
    application_name,
    client_addr,
    state,
    backend_xmin
FROM pg_stat_replication
ORDER BY application_name, pid;
```

`backend_xmin` in replication stats can reflect the horizon reported via feedback. An old value is a signal to inspect the standby and replication strategy.

### 17.4. Do Not Disable Feedback Arbitrarily

Turning off `hot_standby_feedback` to free cleanup can cause long standby queries to be canceled when replay must apply primary changes. It is a trade-off between **primary bloat** and **consistent standby querying**, not a "free bloat fix" switch.

Parameters like `max_standby_streaming_delay` also govern how a standby waits or cancels queries on recovery conflicts. Evaluate reporting SLAs, replica lag, and RPO/RTO before changing settings.

## 18. Replication Slots and Data Retention Boundaries

Replication slots are used by PostgreSQL to track information that must be retained for replication. Some slots carry **`xmin` or `catalog_xmin`** affecting row/catalog version retention, in addition to **`restart_lsn`** governing WAL retention.

This is an important source because **it does not appear as a regular `idle in transaction` session in `pg_stat_activity`**.

### 18.1. Listing Replication Slots

On a server with appropriate monitoring privileges:

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

Meaning:

| Field | Interpretation Hint |
| --- | --- |
| `slot_name` | Name of the slot. |
| `slot_type` | `physical` or `logical`. |
| `active` | Whether a process is currently consuming the slot. |
| `xmin` | XID horizon the slot may require keeping for normal data, if set. |
| `catalog_xmin` | XID horizon for catalog tuples needed by logical decoding, if set. |
| `restart_lsn` | Oldest WAL position still retained for the slot's current state. |
| `confirmed_flush_lsn` | Confirmed consumer position for logical slots, if applicable. |

**Never read `active=false` as "the slot has no effect."** An inactive slot can still hold required positions/horizons and cause WAL accumulation or block cleanup depending on slot state.

### 18.2. Heap Bloat and WAL Retention Are Two Distinct Problems

One incident can cause both:

```text
Logical subscriber stopped
          |
          +-- old restart_lsn
          |      -> WAL can accumulate
          |
          +-- old catalog_xmin
                 -> catalog row versions may be kept long
```

Yet do not conflate the two metrics:

- `restart_lsn` primarily governs retaining **WAL** so the consumer can resume.
- `xmin`/`catalog_xmin` govern boundaries retaining **row versions** for replication/decoding correctness.

A slot with large WAL lag does not automatically prove it is retaining dead tuples in a business table; a slot holding `catalog_xmin` does not mean it retains all heap data rows. Read each field accurately.

### 18.3. Checking WAL Retained by a Slot

On the primary in the appropriate context:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    CASE
        WHEN restart_lsn IS NOT NULL THEN
            pg_size_pretty(
                pg_wal_lsn_diff(
                    pg_current_wal_lsn(),
                    restart_lsn
                )::bigint
            )
        ELSE NULL
    END AS approximate_wal_distance
FROM pg_replication_slots
ORDER BY slot_name;
```

Here `pg_wal_lsn_diff` gives an **LSN distance**, not an exact guarantee of WAL bytes on disk held solely by that slot. Actual retention also depends on the primary, current WAL position, configuration, and replication state.

Do not run this SQL blindly on a standby/read-only environment where functions like `pg_current_wal_lsn()` may not apply.

### 18.4. Risk of Dropping the Wrong Slot

Never drop a replication slot just because it looks inactive. A slot may belong to:

- A temporarily paused replica.
- A CDC connector feeding a data pipeline.
- An audit or downstream system configured to use it.
- A failover/HA process relying on replication progress.

Dropping a slot can prevent the consumer from resuming at its old position, force a full resync, and risk breaking downstream data continuity. Always verify **owner, RPO/RTO**, consumer status, confirmed position, and recovery plan before intervening.

## 19. Prepared Transactions: Holding Resources Without an Active Backend

PostgreSQL supports two-phase commit (2PC) via `PREPARE TRANSACTION`, `COMMIT PREPARED`, and `ROLLBACK PREPARED` when enabled in server configuration.

A *prepared* transaction has detached from its originating session yet **has not finally committed or rolled back**. It can hold locks and transaction resources, and also pin the horizon for `VACUUM`.

### 19.1. Inspecting Prepared Transactions

```sql
SELECT
    gid,
    prepared,
    owner,
    database,
    transaction
FROM pg_prepared_xacts
ORDER BY prepared;
```

Here:

- `gid`: identifier of the prepared transaction.
- `prepared`: timestamp when the transaction was prepared.
- `owner` / `database`: ownership details.
- `transaction`: corresponding transaction ID.

If a prepared transaction lingers, investigators cannot rely solely on `pg_stat_activity`: **a prepared transaction no longer has an active backend session in the usual way**.

### 19.2. Never Commit/Rollback Prepared Transactions Arbitrarily

A prepared transaction may belong to a distributed transaction coordinator. Running `COMMIT PREPARED` or `ROLLBACK PREPARED` blindly without verifying outcomes across other systems can break distributed consistency.

The right procedure is to identify the coordinator, status of all branches, transaction GID, recovery plan, and administrative authority before deciding to commit or roll back.

### 19.3. 2PC Configuration

```sql
SHOW max_prepared_transactions;
```

On many systems not using 2PC, this parameter is left at zero to disable preparing transactions. If a system uses 2PC, monitor orphaned prepared transactions as a dedicated category.

## 20. Summary of Sources That Can Hold the Cleanup Horizon

| Source | How to Observe | Signals to Check |
| --- | --- | --- |
| Active/idle application transaction | `pg_stat_activity` | `xact_start`, `backend_xid`, `backend_xmin`, `state`. |
| Long query holding a snapshot | `pg_stat_activity` | `state=active`, `query_start`, `backend_xmin`. |
| Idle `REPEATABLE READ` transaction | `pg_stat_activity` | Snapshot/XID held for a long time. |
| Standby feedback | `pg_stat_replication` on primary | `backend_xmin` reported over replication, if set. |
| Replication slot | `pg_replication_slots` | `xmin`, `catalog_xmin`, and WAL position. |
| Prepared transaction | `pg_prepared_xacts` | Old GID, transaction ID, prepare timestamp. |
| Long-lived cursors/portals/snapshots | Session/client and monitoring tools | Cursor usage context, retained snapshot. |
| High-intensity write/maintenance stream | `pg_stat_user_tables`, logs, progress | Dead tuples generated faster than cleanup rate. |

**No single column always points directly to "the culprit holding dead tuples for every table."** Visibility depends on the data source, PostgreSQL version, privileges, and state at sampling time.

## 21. Common Case: idle in transaction

Application bug pattern:

```text
check out connection
BEGIN
SELECT data
call external HTTP service
wait for user / process file
write log
forget COMMIT/ROLLBACK
leave connection in pool or thread
```

While the application waits on external work with the transaction still open, the session sits in `idle in transaction`. If a snapshot/XID is held, it restricts `VACUUM`. Even without holding an old snapshot, it can hold locks and occupy connections.

### 21.1. Timeout Configuration

PostgreSQL provides:

```sql
SHOW idle_in_transaction_session_timeout;
```

This setting limits how long a session is allowed to stay **idle inside a transaction**. Exceeding it causes PostgreSQL to terminate the session via timeout, rolling back the uncommitted transaction.

**Important trade-off:** if an application has a legitimate workflow intentionally idling in a transaction, too short a timeout will drop its connection and roll back work.

A timeout is a **safety guardrail**, not a substitute for fixing missing `commit/rollback` code.

### 21.2. statement_timeout Does Not Catch Idle Sessions

`statement_timeout` bounds execution time of a single statement within its scope. A session that finished a `SELECT` and now sits `idle in transaction` will not be terminated by `statement_timeout` because no statement is currently running.

Similarly, `lock_timeout` bounds waiting to acquire a lock and does not replace `idle_in_transaction_session_timeout`.

### 21.3. Transaction Timeout by Version

Newer PostgreSQL major versions add parameters limiting total transaction age, though **support and interaction between timeouts depend on version**. Always verify exact parameters on your target server rather than copying config from another major version.

Never set up a configuration where valid operations get killed periodically and then rely on infinite retries to mask an architectural bug.

## 22. Prevention in Java/JDBC Applications

PostgreSQL only sees connections and transactions. The root cause usually lives in the application's transaction lifecycle.

### 22.1. Never Hold a Transaction Open Across Long Tasks

Risky design example:

```text
BEGIN
SELECT rows
call external API for 20 seconds
wait for download
UPDATE rows
COMMIT
```

If consistency does not require those steps to share one transaction, move **API calls, heavy CPU/file processing, and user waits** outside the transaction:

```text
call external API, prepare data
BEGIN
SELECT/UPDATE requiring consistency
COMMIT
record result and emit post-commit events
```

However, do not split blindly if read/write steps share pricing or inventory invariants: evaluate locking, optimistic concurrency, version checks, or retries accordingly.

### 22.2. JDBC: Commit and Rollback With try/catch

Illustrative explicit transaction handling structure:

```java
Connection connection = dataSource.getConnection();

try (connection) {
    connection.setAutoCommit(false);

    try {
        // Only run SQL statements belonging to the same business unit of work.
        // Do not wait on HTTP calls or long user interactions here.

        try (PreparedStatement statement =
                 connection.prepareStatement(
                     "UPDATE inventory SET quantity = quantity - 1 " +
                     "WHERE product_id = ? AND quantity > 0"
                 )) {
            statement.setLong(1, productId);
            int updated = statement.executeUpdate();

            if (updated != 1) {
                throw new SQLException("Insufficient stock");
            }
        }

        connection.commit();
    } catch (Exception failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    }
}
```

This Java snippet is an **illustrative skeleton**, assuming `dataSource` and `productId` are initialized; `inventory` is not part of this lesson's lab schema. In production, handle lifecycle, checked exceptions, timeouts, and specific transaction managers. The goal is **zero exception paths leaving a transaction abandoned**.

### 22.3. Framework Transaction Boundaries

ORM libraries and frameworks often open a transaction around a service method. If that method calls slow APIs, downloads files, waits on queues, or runs slow logic after querying the database, the connection holds the transaction open unnecessarily.

Audit:

- Which methods actually start transactions?
- Are there network calls inside transaction scope?
- Can swallowed exceptions leave transactions open or rollback-only?
- Do streaming results/cursors hold snapshots across long reads?
- Are app, pool, and database timeouts aligned?
- Are transaction duration and `idle in transaction` connection counts monitored?

Never assume a transaction annotation on a long method is "free" just because it makes code look safer.

## 23. Cursors, Streaming, and Long Reporting Queries

Idle sessions are not the only concern. A report may intentionally read large datasets via cursors or streaming:

```text
BEGIN
DECLARE cursor...
FETCH 1000 rows
process batch in application
FETCH 1000 rows
process next batch
...
COMMIT
```

Cursor/portal/snapshot lifetimes depend on isolation, cursor type, and client usage. Some patterns hold resources or snapshots open for long periods while the application processes outside the database.

### 23.1. Do Not Assume Streaming Always Saves Every Resource

Streaming reduces application RAM compared to loading all rows at once, yet can extend connection and transaction lifetimes.

Solutions depend on the problem:

- Reduce query scope or time range.
- Use keyset pagination where correctness permits.
- Offload large reports to a replica or dedicated ETL environment, accounting for standby feedback trade-offs.
- Use one explicit snapshot when cross-chunk consistency is mandatory; accept and manage the snapshot retention cost.
- Move slow processing outside the transaction by design.

Never switch blindly to per-statement pagination if requirements demand one consistent snapshot across the whole report without deciding how to reconcile mid-report changes.

### 23.2. Do Not Confuse Locks With Snapshots

A long query can:

- Hold an old snapshot, restricting cleanup.
- Hold locks, causing blocking.
- Do both.
- Only consume CPU/I/O with minimal cleanup impact.

These have **different symptoms and fixes**. `pg_blocking_pids(pid)` helps analyze lock blocking, but cannot replace identifying visibility horizon holders.

## 24. Errored Transactions Not Yet Rolled Back

A session can sit in:

```text
idle in transaction (aborted)
```

When SQL errors inside an explicit transaction, the session cannot run normal SQL statements until rolled back or handled via an appropriate savepoint. If the client catches the exception and forgets the transaction, the session can linger there for a long time.

Example flow:

```text
BEGIN
UPDATE ...
INSERT duplicate unique -> ERROR
application catches SQLException without rollback
connection stays open
```

This is a transaction-management bug that must be fixed. However, **never assume from the state string alone that the backend is definitely holding `backend_xmin`**; inspect snapshot/XID/locks to understand concrete impact.

The primary fix is ensuring the application always ends transactions on unrecovered errors, and the pool resets connections to a clean state.

## 25. Safe Approach When Spotting a Suspicious Session

In production, never immediately run a connection-termination command just because `xact_start` looks old.

Recommended sequence:

1. **Verify symptoms:** are table sizes growing, autovacuum falling behind, XID age climbing, query latency rising, disk usage increasing, or is it just a temporary stats fluctuation?
2. **Identify affected objects:** schema/table, when growth started, and tables with high write rates.
3. **Inspect backends:** `xact_start`, `state`, `backend_xid`, `backend_xmin`, application/client.
4. **Inspect non-backend holders:** replication slots, standby feedback, prepared transactions.
5. **Find the owner:** identify the service, job, or user running the query.
6. **Assess safe termination:** is the transaction serving a critical payment/batch or is it an orphaned session?
7. **Have the application commit/roll back normally** whenever possible.
8. **Only intervene forcefully per an approved runbook** if risk is clear and the owner has been contacted/evaluated.
9. **Re-observe vacuum** after the blocker finishes.
10. **Fix the root cause:** transaction boundaries, timeouts, queries, replication config, monitoring, and retry policies.

### 25.1. pg_cancel_backend and pg_terminate_backend Are Different

Administrative functions serve distinct purposes:

- `pg_cancel_backend(pid)`: requests canceling the backend's **current query**; does not necessarily end the session or roll back the entire transaction in every scenario.
- `pg_terminate_backend(pid)`: requests terminating the **backend session**; uncommitted work in that session will not be committed.

For an `idle in transaction` session **with no query currently running**, canceling a query typically does not end the open transaction. Terminating breaks the connection, causes application errors, and rolls back uncommitted work.

**This lesson does not provide copy-paste terminate commands** because terminating sessions mutates state and can disrupt services. In production, always verify the latest PID, privileges, owner, and impact before acting. PIDs can also be recycled after an old backend exits; never act on a stale PID list.

### 25.2. Never Kill Autovacuum Arbitrarily to Reduce Load

Autovacuum is a maintenance mechanism. If it runs long, identify its phase and reason first. Repeatedly canceling it increases bloat and freeze pressure. Coordinating with DDL is sometimes needed, but must follow an operational plan rather than a knee-jerk reflex.

### 25.3. Lock Blockers and Horizon Holders May Not Be the Same Session

A session blocking `VACUUM` via a lock differs from a session holding a visibility horizon that prevents `VACUUM` from removing tuples. Both can coexist, yet they are **not identical**.

If `VACUUM` is waiting on a lock, analyze lock holders; if `VACUUM` finishes scanning yet old tuples remain retained, inspect the visibility horizon. The fixes for the two problems differ.

## 26. Read-Only Runbook: Gathering Evidence Before Intervening

The queries below are **read-only** within the listed monitoring views/functions. They do not stop backends and do not modify table data.

### 26.1. Databases and XID Age

```sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
```

### 26.2. Long-Open Transactions

```sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    state,
    clock_timestamp() - xact_start AS transaction_age,
    backend_xid,
    backend_xmin,
    CASE
        WHEN backend_xmin IS NOT NULL
            THEN age(backend_xmin)
        ELSE NULL
    END AS backend_snapshot_xid_age
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

### 26.3. Tables With High Estimated Dead Tuples

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;
```

Never interpret `n_dead_tup` as an exact real-time measurement; a large table with many dead tuples and healthy autovacuum activity may not be an emergency.

### 26.4. Active VACUUM Runs

```sql
SELECT
    pid,
    relid::regclass AS relation_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed
FROM pg_stat_progress_vacuum;
```

### 26.5. Replication Slots

```sql
SELECT
    slot_name,
    slot_type,
    active,
    xmin,
    catalog_xmin,
    restart_lsn
FROM pg_replication_slots
ORDER BY slot_name;
```

### 26.6. Prepared Transactions

```sql
SELECT
    gid,
    prepared,
    owner,
    database
FROM pg_prepared_xacts
ORDER BY prepared;
```

### 26.7. Standby Feedback on the Primary

```sql
SELECT
    application_name,
    state,
    backend_xmin
FROM pg_stat_replication;
```

**Read the outputs as a combined set of evidence**, rather than picking the oldest timestamp row and declaring the root cause solved. Correlate with when bloat began, `UPDATE`/`DELETE` rates, vacuum logs, replication config, and each source's XID horizon.

## 27. Symptom-Based Decision Table

| Symptom | What to Check First | What Not to Do Immediately |
| --- | --- | --- |
| Dead tuples rising despite autovacuum running | Old snapshots/XIDs, slots, feedback, write rate, and vacuum logs. | Run `VACUUM FULL` in production. |
| Table size grew while dead tuples dropped | Space reuse behavior, bloat history, index size. | Conclude `VACUUM` is useless. |
| Session `idle in transaction` for long | Snapshot/XID, locks, owner, transaction boundaries. | Auto-terminate every session by age. |
| Primary bloat during long replica reports | `hot_standby_feedback`, `pg_stat_replication.backend_xmin`. | Disable standby feedback without assessing conflicts. |
| WAL directory growing | Replication slots, `restart_lsn`, archiving, replication lag. | Assume WAL growth equals heap dead tuples. |
| `pg_prepared_xacts` has old GIDs | Coordinator, incomplete 2PC transactions. | Run `ROLLBACK PREPARED` unverified. |
| High XID age | Autovacuum freeze, old XID holders, anti-wraparound logs. | Disable autovacuum or only raise thresholds. |
| `VACUUM` waiting on locks for long | Lock holders, `wait_event`, DDL, workload. | Confuse it immediately with a visibility horizon issue. |
| `n_dead_tup` fluctuates erratically | Statistical estimates, stats snapshot caching. | Treat a single number as definitive proof. |

## 28. Bloat Reduction Strategy After Resolving the Root Cause

Once old transactions/horizons are no longer held, next steps depend on bloat scale and impact:

### 28.1. Regular VACUUM

Usually the right starting point:

```sql
VACUUM (VERBOSE, ANALYZE) mvcc_cleanup_lab.demo_rows;
```

Expected outcome is making space inside the relation reusable and updating related metadata as eligible. Do not demand immediate file-size reduction as the measure of success.

### 28.2. Letting Autovacuum Maintain Steady State

For continuously `UPDATE`d tables, you may need to:

- Tune thresholds/scale factors to match table size and write rate.
- Adjust worker/cost settings so vacuum does not fall too far behind.
- Ensure sufficient I/O and disk headroom.
- Fix long transactions / replication feedback first.
- Monitor results long enough to confirm stability.

Never change dozens of parameters at once and lose track of which change caused improvement.

### 28.3. VACUUM FULL and Rewrites

`VACUUM FULL` is an option when shrinking the relation on the filesystem is genuinely necessary. However:

- Requires strong locks and can block table activity.
- Consumes extra disk space during the rewrite.
- Generates heavy WAL and I/O.
- Must be scheduled and assessed against replication, backups, and application SLAs.
- Will not fix bloat if transactions or workloads keep pinning abnormal horizons.

### 28.4. Index Bloat and REINDEX

In cases of severe index bloat, `REINDEX` or an appropriate index rebuild strategy can help. Syntax and concurrent support depend on index type and server version, and rebuilding consumes significant resources.

Perform it only after confirming **indexes are genuinely bloated** and planning for locks, space, and availability. Never treat `REINDEX` as a routine substitute for `VACUUM` or a fix for old snapshots.

### 28.5. Never Use DELETE to "Clean Dead Tuples"

`DELETE` creates additional MVCC state requiring maintenance; it is not a tool to directly remove dead row versions and cure bloat. If deleting business data per retention policy, use dedicated `DELETE`/partitioning policies and still rely on `VACUUM` or corresponding maintenance.

## 29. Architectural and Operational Prevention

### 29.1. Short Transactions Yet Long Enough to Preserve Invariants

Scope a transaction to contain only operations that must be atomic together. Avoid spanning:

- HTTP or message-queue waits.
- Waiting for user input.
- Slow client data streaming.
- Long CPU computations that do not need a snapshot.
- Unbounded sleeps/retries.

"As short as possible" must go hand-in-hand with "still sufficient for business correctness." Never split a payment transaction needing an invariant into separate independent commits without a compensating consistency mechanism.

### 29.2. Intentional Timeouts

Use appropriate session/role/database settings to bound:

- Runaway SQL statements.
- Excessive lock waits.
- Sessions idling in transactions too long.
- Overall transaction age where supported and appropriate.

Timeouts must be paired with retries/idempotency and error observability in the application. Never set timeouts shorter than legitimate batch execution durations.

### 29.3. Controlling Data-Ingestion Workflows

Instead of opening one transaction and loading hundreds of millions of rows in one shot, consider:

- Loading into staging tables.
- Validating in sets.
- Splitting into chunks with clear checkpoints.
- Using idempotency keys for safe retries.
- Finalizing batch state on completion.

Chunking alters batch-wide atomicity guarantees; align with business stakeholders before implementing.

### 29.4. Monitoring Replication

Track:

- Standby feedback and query duration on replicas.
- Replication lag and active/inactive slots.
- `xmin`, `catalog_xmin`, and `restart_lsn` by slot type.
- WAL disk usage and retention policies.
- Consumer/CDC owners and reconnect/resync health.

Never fix primary bloat by causing downstream consumers to lose data.

### 29.5. Recommended Alerting Metrics

A DBA dashboard might include:

| Group | Suggested Metrics |
| --- | --- |
| Transactions | Count of `idle in transaction` sessions, max transaction age, age distribution. |
| Visibility horizon | Old `backend_xmin`/`backend_xid`, replication feedback, slot `xmin`, prepared xacts. |
| Vacuum | `last_autovacuum`, autovacuum counts, active runs and phases. |
| Tables | Estimated `n_dead_tup`, `UPDATE`/`DELETE` rates, table/index sizes. |
| XID safety | `age(datfrozenxid)`, `age(relfrozenxid)`, wraparound alerts. |
| Capacity | Free disk, WAL growth, relation expansion rate. |
| Application | Transaction duration per service, timeout errors, pool connection counts. |

It is essential to **track trends** and understand normal workloads rather than setting one rigid threshold for every table.

## 30. Common Reasoning Errors and Operational Mistakes

### Error 1. "After UPDATE, the old tuple is gone"

False. PostgreSQL normally keeps old tuple versions to preserve MVCC; `VACUUM` cleans only when safe.

### Error 2. "Transaction A isn't reading the table again, so old versions can be deleted"

Unfounded. While A holds a snapshot entitled to see old versions, the engine cannot gamble on predicting whether the user will query again and delete data prematurely.

### Error 3. "Every idle in transaction session holds an old snapshot"

No. Under `READ COMMITTED`, a statement's snapshot can be released after the statement completes. Check `backend_xmin`, `backend_xid`, isolation, and context.

### Error 4. "NULL backend_xmin means the session is completely harmless"

Insufficient basis. It may still hold an XID, locks, or other state; check `backend_xid` and non-backend horizon holders.

### Error 5. "The highest transaction_age is definitely the biggest blocker"

Elapsed minutes do not equal the oldest XID horizon. A shorter session with an older snapshot/XID or an inactive replication slot can matter more.

### Error 6. "Once autovacuum runs, all dead tuples must disappear"

No. `VACUUM` only removes tuples eligible under the visibility horizon; autovacuum also performs other maintenance duties.

### Error 7. "n_dead_tup is an exact real-time count"

No. It is a statistics estimate and can lag or shift with stats updates.

### Error 8. "A successful VACUUM must shrink the file"

No. Space freed by `VACUUM` is normally reused internally. File shrinking has its own mechanisms and conditions.

### Error 9. "VACUUM FULL is the first solution to try"

No. It can block the system and does not fix root causes if old horizons persist. Investigate first.

### Error 10. "Adding more autovacuum workers will bypass old snapshots"

No. Adding workers does not allow bypassing MVCC visibility rules.

### Error 11. "REINDEX fixes all dead tuple problems"

No. Index rebuilds do not replace heap cleanup or clear transaction horizons.

### Error 12. "Dropping an inactive replication slot is safe"

No. The slot may be a required resume point for CDC or replication; dropping it carelessly can force a full resync.

### Error 13. "WAL lag equals dead heap bloat"

No. `restart_lsn` governs WAL retention; `xmin`/`catalog_xmin` govern cleanup horizons. They are related yet distinct.

### Error 14. "No old backends means no blockers remain"

No. Prepared transactions or replication slots/feedback can still hold boundaries requiring investigation.

### Error 15. "Just COMMIT PREPARED an old GID to clear it"

No. It may be a 2PC transaction belonging to another coordinator; committing or rolling back blindly causes inconsistency.

### Error 16. "Running one SELECT holds a snapshot until the connection closes"

False in general. Snapshot lifetime depends on transaction scope, isolation level, cursors, and client behavior.

### Error 17. "Run VACUUM inside BEGIN to test in the same transaction"

No. Regular `VACUUM` cannot run inside an explicit transaction block. The two-session experiment requires B to run `VACUUM` outside `BEGIN`.

### Error 18. "Just canceling a query clears an idle transaction"

No. Canceling the current query does not end an open transaction or session; `idle in transaction` must be resolved at transaction boundaries.

### Error 19. "Terminating a session is always safe because it rolls back"

No. Termination causes application errors, aborts uncommitted work, and can disrupt pipelines and users. Follow ownership and runbooks.

### Error 20. "Setting transaction timeout very low cures all bloat"

No. Overly aggressive timeouts break legitimate workloads, trigger retries, and degrade services.

### Error 21. "Long transactions only waste disk space"

No. They also impact latency, lock contention, vacuuming, freezing, cache efficiency, and wraparound risk.

### Error 22. "No DELETEs means zero dead tuples"

False. `UPDATE`s also create old row versions, and rolled-back transactions can leave tuples needing cleanup.

### Error 23. "HOT updates produce no old tuples"

False. HOT mainly avoids creating new index entries when conditions hold; MVCC row versions still exist.

### Error 24. "Lowering isolation arbitrarily is a good optimization"

No. Isolation must satisfy business correctness; lowering it can alter results and consistency. Usually you need to fix transaction boundaries and workloads instead.

## 31. Practice Exercises

Exercises use schema `mvcc_cleanup_lab` and system views. For two-session exercises, ensure both genuinely use **the same database but separate connections**. Exercises involving killing backends or modifying replicas require **analysis only**, not destructive actions.

### Exercise 1. Why Does UPDATE Create Multiple Versions?

Explain why PostgreSQL does not immediately delete the old tuple when another transaction `UPDATE`s and commits.

### Exercise 2. Two-Session Design

List the minimal steps to demonstrate Session A under `REPEATABLE READ` still seeing `generation=0` while Session B sees `generation=1`.

### Exercise 3. VACUUM While A Is Open

If B runs `VACUUM (VERBOSE)` while A still holds an old snapshot, why can `VACUUM` complete without cleaning all old tuple versions?

### Exercise 4. Ending A

After A `COMMIT`s, B runs `VACUUM` again. What changed to make cleaning the old versions possible?

### Exercise 5. READ COMMITTED

A session only runs `SELECT` inside a `READ COMMITTED` transaction and then sits idle for 30 minutes. Can you definitively conclude it held that `SELECT`'s snapshot for all 30 minutes?

### Exercise 6. Backend XID vs. Backend xmin

Distinguish `backend_xid` from `backend_xmin`, and explain why an old `xact_start` alone is not enough to prove dead tuples are being retained.

### Exercise 7. Querying pg_stat_activity

Write a query showing PID, state, transaction age, and `backend_xmin` for sessions with open transactions.

### Exercise 8. Dead Tuple Estimates

Write a query retrieving `n_dead_tup`, `last_autovacuum`, and `autovacuum_count` for `mvcc_cleanup_lab.demo_rows`. Explain why these numbers can lag.

### Exercise 9. Physical Sizes

Compare `pg_relation_size`, `pg_indexes_size`, and `pg_total_relation_size`. Why doesn't total size always shrink after `VACUUM`?

### Exercise 10. HOT Updates

Why does updating an indexed column normally reduce HOT eligibility? Does HOT remove the need to obey snapshots?

### Exercise 11. Autovacuum Threshold

Assume threshold 50, scale factor 0.1, and 200,000 estimated rows. What is the basic threshold for dead tuples?

### Exercise 12. Freezing

What is the meaning of `age(datfrozenxid)`? Is it seconds/minutes or transaction ID age?

### Exercise 13. Finding Active VACUUMs

Write a query displaying PID, relation name, phase, and heap blocks scanned for active `VACUUM` operations.

### Exercise 14. Standby Feedback

Explain how `hot_standby_feedback` can reduce recovery conflicts on a replica while causing the primary to retain dead tuples longer.

### Exercise 15. Replication Slots

Distinguish the meanings of `restart_lsn`, `xmin`, and `catalog_xmin`. Why shouldn't you immediately drop a slot with `active=false`?

### Exercise 16. Prepared Transactions

`pg_stat_activity` shows no old sessions, yet the XID horizon is still held back. Which view helps find unresolved prepared transactions?

### Exercise 17. Idle Timeout

Does `idle_in_transaction_session_timeout` address every long-running query? What happens if the timeout terminates a session holding an uncommitted transaction?

### Exercise 18. Handling Suspicious Backends

Distinguish `pg_cancel_backend` from `pg_terminate_backend` and explain why you shouldn't auto-terminate solely based on transaction age.

### Exercise 19. Symptom-Based Diagnosis

A table has increasing `autovacuum_count`, rising `n_dead_tup`, and a backend holding an old `backend_xmin`. Propose three investigation steps before altering autovacuum configuration.

### Exercise 20. Java Transactions

A method opens a transaction, reads several tables, calls an external API for 90 seconds, and only then commits. Identify the risks and how to improve it while still preserving business invariants.

### Exercise 21. VACUUM FULL

In production, a large table serves an application that tolerates zero downtime. Should you run `VACUUM FULL` as soon as you see bloat? What must be evaluated?

### Exercise 22. Growing WAL

When `pg_wal` grows rapidly and a logical replication consumer has stopped, which fields in `pg_replication_slots` should you check? Why shouldn't you conclude that metric means heap bloat?

### Exercise 23. MVCC and Locks

Distinguish a transaction holding a lock that makes another query wait from a transaction holding a snapshot that prevents `VACUUM` from cleaning tuples.

### Exercise 24. Designing a Dashboard

Select at least six metrics across multiple groups (transactions, vacuum, sizes, XID age, replication, application) to monitor the risk of delayed cleanup.

## 32. Suggested Solutions

### Solution 1. MVCC Retains Versions for Old Snapshots

A transaction that took a snapshot before the `UPDATE` may still need the old tuple version for consistent reads. Only when no eligible snapshot/transaction needs it anymore can `VACUUM` safely remove it.

### Solution 2. Two Sessions

Session A:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT MIN(generation), MAX(generation)
FROM mvcc_cleanup_lab.demo_rows;
-- Keep transaction open.
```

Session B:

```sql
UPDATE mvcc_cleanup_lab.demo_rows
SET generation = generation + 1;

SELECT MIN(generation), MAX(generation)
FROM mvcc_cleanup_lab.demo_rows;
```

Return to A to run `SELECT` again before `COMMIT`. A still sees `0`, while B sees `1`. The example assumes the table started at `generation=0`.

### Solution 3. Not Removing Needed Versions

`VACUUM` must preserve old tuple versions still required for A's snapshot. It can still complete its scan and other maintenance tasks, but must not destroy data A can legitimately read.

### Solution 4. Horizon Released

When A finishes, A's snapshot is gone. Provided no other snapshot/XID holder or horizon source remains, `VACUUM` in B can clean the previously blocked old tuples.

### Solution 5. READ COMMITTED

No. A snapshot used for a single `READ COMMITTED` statement can be released after that statement finishes. However, an open transaction can still hold locks, an XID, or other resources; inspect actual state and metadata.

### Solution 6. XID and xmin

`backend_xid` is the top-level XID if the backend has one; `backend_xmin` reflects the `xmin` horizon of a snapshot currently held by the backend, if any. `xact_start` is the wall-clock start time of the transaction; alone it does not prove an old snapshot is held.

### Solution 7. Monitoring Query

```sql
SELECT
    pid,
    state,
    clock_timestamp() - xact_start AS transaction_age,
    backend_xmin
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

### Solution 8. Dead Tuple Statistics

```sql
SELECT
    n_dead_tup,
    last_autovacuum,
    autovacuum_count
FROM pg_stat_user_tables
WHERE schemaname = 'mvcc_cleanup_lab'
  AND relname = 'demo_rows';
```

`n_dead_tup` is a statistics-system estimate, not an exact real-time heap count.

### Solution 9. Sizes

```sql
SELECT
    pg_relation_size('mvcc_cleanup_lab.demo_rows') AS heap_bytes,
    pg_indexes_size('mvcc_cleanup_lab.demo_rows') AS index_bytes,
    pg_total_relation_size('mvcc_cleanup_lab.demo_rows') AS total_bytes;
```

Regular `VACUUM` marks space reusable without necessarily shrinking the physical file.

### Solution 10. HOT

If an indexed column changes, PostgreSQL normally must update index entries and loses HOT eligibility. HOT still creates heap row versions and still obeys MVCC visibility.

### Solution 11. Basic Threshold

`50 + 0.1 × 200000 = 20050` dead tuples under the basic model. Actual triggers also depend on other server autovacuum settings/conditions.

### Solution 12. XID Age

`age(datfrozenxid)` is a logical age in transaction IDs, not elapsed minutes or days. It is a safety signal for monitoring wraparound.

### Solution 13. VACUUM Progress

```sql
SELECT
    pid,
    relid::regclass AS relation_name,
    phase,
    heap_blks_total,
    heap_blks_scanned
FROM pg_stat_progress_vacuum;
```

### Solution 14. Hot Standby Feedback

A replica can report its horizon to the primary to avoid replay conflicts with replica queries needing old tuples. Consequently, the primary delays cleanup and bloat can grow; if feedback is turned off, long replica queries can be canceled per conflict policy.

### Solution 15. Slot Fields

`restart_lsn` governs WAL retention; `xmin` holds a data horizon if present; `catalog_xmin` retains catalog versions for decoding. An inactive slot can still hold required boundaries and belong to a consumer that needs to resume; dropping it wrongly can break resumability.

### Solution 16. Prepared Transactions

```sql
SELECT gid, prepared, owner, database, transaction
FROM pg_prepared_xacts;
```

Never commit/roll back a GID without identifying its owner.

### Solution 17. Idle Timeout

No. It targets sessions sitting idle inside a transaction, not active running queries. If the timeout terminates a session with an uncommitted transaction, uncommitted work rolls back, causing application errors that require policy-appropriate retries.

### Solution 18. Cancel vs. Terminate

Cancel requests aborting the current query; terminate requests ending the backend/session. Terminating rolls back uncommitted transactions and disrupts service operations. Always verify owner, purpose, horizon, and impact rather than acting on a single timestamp.

### Solution 19. Three Investigation Steps

1. Use `pg_stat_activity` to inspect `backend_xmin`/`backend_xid`, state, and owner of old backends.
2. Check `pg_replication_slots`, `pg_stat_replication`, and `pg_prepared_xacts` to rule out other horizon holders.
3. Correlate `pg_stat_user_tables`, `VACUUM VERBOSE`/progress, heap/index sizes, and write rates to verify whether dead versions are pinned by a horizon and gauge severity.

Only then coordinate with the application to end the transaction and observe vacuum recovery.

### Solution 20. Java Transaction Boundary

Holding a transaction open for 90 seconds while waiting on an API pins snapshots/XIDs/locks and ties up a pool connection. Improve by running slow API calls outside the transaction when business rules permit, using short transactions for atomic reads/writes, and using locks/version checks and retries to uphold invariants.

### Solution 21. VACUUM FULL

Do not run it right away. Check whether blockers still exist, whether free space can be reused, whether file shrinkage is truly needed, disk headroom, lock/downtime impact, replication lag, and less disruptive maintenance options suitable for the server.

### Solution 22. Growing WAL

Check `active`, `restart_lsn`, `confirmed_flush_lsn`, and consumer health for the logical slot; also inspect `xmin`/`catalog_xmin` if investigating cleanup horizons. WAL retention and old-tuple cleanup are related yet distinct mechanisms.

### Solution 23. Locks vs. Horizons

Lock blocking makes another SQL query wait to acquire a lock; an old snapshot/XID horizon prevents `VACUUM` from removing certain row versions even while `VACUUM` runs. Inspect wait events/locks for the first, and visibility metadata plus vacuum output for the second.

### Solution 24. Dashboard

Example eight metrics:

1. Count of `idle in transaction` sessions per service.
2. Maximum transaction age and top backends holding old `backend_xmin`.
3. Estimated `n_dead_tup` per table.
4. Time since `last_autovacuum` and `autovacuum_count`.
5. `pg_total_relation_size`/index sizes over time.
6. `age(datfrozenxid)` and tables with high `age(relfrozenxid)`.
7. Slot `restart_lsn` lag and `xmin`/`catalog_xmin`.
8. `pg_stat_replication.backend_xmin` and long-running standby queries.

A dashboard should also track `UPDATE`/`DELETE` rates and disk/WAL alerts to put those numbers in proper context.

## 33. Synthesis Scenario: Incident After an ETL Deployment

Suppose the operations team observes:

```text
Day 1:
  orders has 2 million live rows
  autovacuum runs regularly
  heap size stays fairly stable

After a new ETL deployment:
  a worker opens a REPEATABLE READ transaction
  the worker reads orders and waits very long on an external API
  other services continuously UPDATE order statuses

One day later:
  heap/index sizes increase
  n_dead_tup estimate rises
  last_autovacuum is still updating
  one idle in transaction session holds an old backend_xmin
```

### 33.1. Diagnosis

Never conclude from a single metric. Combine:

- `pg_stat_activity` confirming the worker, `xact_start`, and `backend_xmin`.
- `pg_stat_user_tables` showing `UPDATE` rate, dead tuple estimates, and autovacuum history.
- `pg_relation_size` and `pg_indexes_size` showing physical growth.
- `pg_replication_slots`/`pg_stat_replication`/`pg_prepared_xacts` checking other horizons.
- `VACUUM` logs and I/O/disk status.

### 33.2. Safe Response

1. Notify the application/ETL owner and confirm whether the transaction can complete or be retried.
2. Prefer letting the worker **commit/roll back cleanly per application flow** instead of blindly terminating.
3. If operational risk is critical and intervention is required, follow an authorized runbook with impact review.
4. Once the blocker clears, observe autovacuum or run a controlled `VACUUM`.
5. Monitor `n_dead_tup` estimates, table sizes, XID age, and disk headroom.
6. Fix the worker: stop holding snapshots across API calls, split transaction scope, and add timeouts and logging.

### 33.3. Expected Outcome

Once the blocker is gone:

- Eligible old tuple versions can be cleaned by `VACUUM`.
- Space inside the relation becomes reusable.
- Growth rate stabilizes once workload and autovacuum rebalance.
- File size **will not necessarily return to its original size**.

For systems that already accumulated massive bloat, a separate physical compaction decision may be needed. Never cite "the disk file didn't shrink" as proof that fixing the root cause did nothing.

## 34. Root-Cause and Remediation Checklist

Before concluding "unfinished transactions are blocking VACUUM":

1. **Know the target:** which table, which workload, how many live rows, and what `UPDATE`/`DELETE` rate?
2. **Know the timeline:** when did bloat begin, and does it correlate with a deployment or job?
3. **Inspect snapshot/XID:** `backend_xmin`, `backend_xid`, `xact_start`, `state`.
4. **Check isolation:** is the transaction `READ COMMITTED` or `REPEATABLE READ`, and are cursors/portals open?
5. **Check replication:** `hot_standby_feedback`, replication slots, `xmin`/`catalog_xmin`, and WAL lag.
6. **Check 2PC:** are any prepared transactions lingering?
7. **Read stats accurately:** `n_dead_tup` is an estimate; `last_autovacuum` does not guarantee all tuples were removed.
8. **Check VACUUM progress:** is it scanning, vacuuming indexes, or waiting on a lock?
9. **Check XID age:** is freeze/wraparound risk rising?
10. **Separate reuse from shrinking:** unchanged file size does not always mean vacuum isn't helping.
11. **Assess owner and impact:** never terminate critical transactions without a plan.
12. **Be careful with 2PC/replication:** never drop slots or force-finish unknown GIDs.
13. **Plan post-fix verification:** after clearing the blocker, verify vacuum progress and workload stability.
14. **Fix the root cause:** shorten transactions, configure sensible timeouts, fix pooling/streaming code.
15. **Protect business correctness:** evaluate every change to isolation, retries, batch boundaries, and replication policy.

## 35. Summary

MVCC lets PostgreSQL serve multiple concurrent transactions using row versions governed by snapshot visibility rules. This mechanism imposes a crucial condition on data cleanup: **`VACUUM` can only remove a row version when no valid transaction or snapshot still needs it**.

Key takeaways:

- **`UPDATE`/`DELETE` do not immediately erase all old tuples.** A version obsolete to new snapshots may still be required by an old snapshot.
- **Long-open transactions can pin the cleanup horizon.** That can cause heap/index bloat, increase I/O and disk usage, and create freezing pressure.
- **Not every `idle in transaction` session holds an old snapshot.** Inspect `backend_xmin`, `backend_xid`, isolation level, and actual resources; `xact_start` alone is only one signal.
- **Autovacuum can still run without cleaning old tuples.** Adding workers or lowering scale factors cannot override MVCC rules.
- **`n_dead_tup` is an estimate**, and regular `VACUUM` normally **reuses space within files** rather than shrinking files immediately.
- **Horizon holders are not limited to application backends.** Standby feedback, replication slots, and prepared transactions must also be monitored.
- **Freezing and XID age** make handling old transactions a long-term safety issue, not merely a performance issue.
- **Never rush into `VACUUM FULL`, terminating backends, or dropping replication slots.** Identify the owner, root cause, impact, and recovery path first.
- **Sustainable prevention** means properly scoped transactions, well-designed timeouts, clean error/rollback handling, monitoring, and workload-appropriate vacuum/replication settings.

A helpful operational principle:

> When `VACUUM` cannot clean old versions yet, ask **"Who or what mechanism still has the right to see them?"** before asking **"How do I force VACUUM to run harder?"**

That is the key to maintaining PostgreSQL in alignment with MVCC while preserving both data integrity and system availability.
