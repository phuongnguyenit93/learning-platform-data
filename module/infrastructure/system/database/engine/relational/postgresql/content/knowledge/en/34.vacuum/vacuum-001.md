# Why MVCC Needs VACUUM and the Role of Autovacuum

PostgreSQL allows multiple transactions to read and write concurrently without most read queries having to wait for writers. The underlying mechanism is **MVCC (Multi-Version Concurrency Control)**: an UPDATE typically creates a new tuple version while the old version is retained until no transaction needs to see it anymore. DELETE also does not immediately remove the row's bytes from the data file; it marks the old version as deleted according to transaction semantics.

This design lets readers see a consistent snapshot, but leaves behind **dead tuples** when old versions are no longer needed. If not reclaimed and reused, the heap/indexes bloat, queries must scan more pages, planner statistics become stale, and the system can approach the risk of **transaction ID wraparound**. PostgreSQL uses **VACUUM** to clean up unneeded versions, update visibility information, and freeze sufficiently old tuples. **Autovacuum** is the daemon that automatically schedules VACUUM/ANALYZE based on statistics and configured thresholds.

Understanding VACUUM is not just memorizing an administrative command. You need to grasp MVCC visibility, snapshot horizon, dead tuples, freezing, the visibility map, autovacuum thresholds, vacuum workers, and the reasons vacuum fails to make progress. These concepts relate directly to PostgreSQL performance, storage capacity, replication, transaction design, and availability.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain MVCC and why UPDATE/DELETE do not immediately reclaim old tuples.
2. Distinguish tuple version, live tuple, dead tuple, snapshot, and transaction visibility.
3. Understand the conceptual role of xmin/xmax and why you should not read them as business timestamps.
4. Distinguish heap pruning, VACUUM, ANALYZE, and VACUUM FULL.
5. Explain that VACUUM reclaims space for PostgreSQL to reuse, but usually does not return file size to the operating system.
6. Understand freezing, transaction ID wraparound, and MultiXact wraparound.
7. Explain the visibility map and its benefit for index-only scans.
8. Understand how autovacuum decides when a table needs vacuum/analyze.
9. Read threshold/scale factor values and configure per-table settings for skewed workloads.
10. Detect long-running transactions, replication slots, or standby feedback blocking the vacuum horizon.
11. Monitor progress using pg_stat_user_tables, pg_stat_progress_vacuum, pg_stat_activity, and the system catalogs.
12. Handle large tables, partitioned tables, TOAST, temporary tables, and import/update workloads.
13. Design controlled VACUUM/ANALYZE operations without using VACUUM FULL as a reflex.

> **Version note:** Setting names and some autovacuum behaviors can differ across PostgreSQL versions. This lesson uses concepts and views common in modern PostgreSQL; before setting production configuration, verify the values in pg_settings and the documentation for your exact major version.

## 2. Why Does PostgreSQL Need MVCC?

Suppose two transactions run concurrently:

```text
Transaction A: reads account 10
Transaction B: updates account 10
```

If the database only kept a single version of a row and writers overwrote it directly, readers could see half-modified data or have to wait for writers to finish. MVCC solves this by keeping tuple versions annotated with transaction metadata, then deciding which version is visible to each transaction's snapshot.

### Core Idea

- Readers take a snapshot and read the version appropriate for that snapshot.
- Writers create a new version instead of modifying the old row's contents in a way that makes every reader see it immediately.
- An old version is cleaned up only when no remaining snapshot can possibly need to see it.

As a result, many SELECTs can run concurrently with UPDATE/DELETE without locking rows to wait for all readers to finish. MVCC does not eliminate all locks: writers still take row/table locks, and DDL can still block operations.

## 3. Tuple Versions and xmin/xmax

A row in PostgreSQL is stored as a **tuple** inside a heap page. Conceptually, a tuple carries transaction metadata:

- `xmin`: the transaction ID associated with creating the tuple version.
- `xmax`: the transaction ID or information associated with ending validity/deleting/locking the tuple; it is not always simply "the ID of the transaction that ran DELETE".

Logical example:

```text
Initially:
  tuple version V1: balance = 100

UPDATE balance = 150:
  V1 is marked invalid according to transaction semantics
  tuple version V2 is created: balance = 150

DELETE:
  the current version is marked deleted
```

This is an explanatory model. Internally, `xmax` can represent locks/MultiXact IDs and various other states; do not use arithmetic comparisons on `xmin`/`xmax` as business ordering or timestamps.

### Why Not Delete V1 Immediately on UPDATE?

An older transaction may have taken its snapshot before B committed. For that snapshot, V1 is still the visible version; V2 is either uncommitted or not visible in that snapshot. If PostgreSQL deleted V1 immediately, transaction A would lose the data its snapshot requires.

## 4. Example of Two Sessions Seeing Two Versions

Create the practice table:

```sql
CREATE SCHEMA IF NOT EXISTS lesson_vacuum;

CREATE TABLE lesson_vacuum.accounts (
    account_id BIGINT PRIMARY KEY,
    balance NUMERIC(14,2) NOT NULL
);

INSERT INTO lesson_vacuum.accounts
VALUES (10, 100.00);
```

**Session A**:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM lesson_vacuum.accounts
WHERE account_id = 10;
-- 100.00
```

**Session B**:

```sql
BEGIN;

UPDATE lesson_vacuum.accounts
SET balance = 150.00
WHERE account_id = 10;

COMMIT;
```

**Session A**:

```sql
SELECT balance
FROM lesson_vacuum.accounts
WHERE account_id = 10;
-- Still sees 100.00 within the REPEATABLE READ snapshot.

COMMIT;
```

A new transaction started after B commits will see 150.00:

```sql
SELECT balance
FROM lesson_vacuum.accounts
WHERE account_id = 10;
```

### Takeaway

While A still holds its snapshot, the old version can still be needed. VACUUM cannot delete a tuple merely because a newer version exists; it must consider the **visibility horizon** of all still-relevant transactions/snapshots.

## 5. DELETE Does Not Immediately Erase Bytes from the Heap

Try:

```sql
DELETE FROM lesson_vacuum.accounts
WHERE account_id = 10;
```

DELETE marks the old tuple as no longer visible to appropriate snapshots once the transaction commits. The physical data can remain inside the heap page until pruning/vacuum cleans it up and no snapshot needs that tuple anymore.

### Implications

- `DELETE 1` does not mean the table file shrinks immediately.
- Repeated UPDATEs can create many dead tuple versions.
- `TRUNCATE` is a different operation that alters storage in its own way and does not generate a per-row DELETE event.
- VACUUM is a normal part of MVCC management, not something you only run when the database "gets full".

## 6. Live Tuples, Dead Tuples, and Still-Needed Tuples

These terms must be understood in terms of visibility:

| Concept | Meaning |
|---|---|
| Live tuple | Current version that can be visible to an appropriate snapshot |
| Dead tuple | Version no longer visible to any transaction that needs it and eligible for reclamation |
| Recently dead / potentially removable later | Version that has been replaced/deleted but may still be needed by an older snapshot |
| Unused/free space | Space on a page that can be reused for new tuples |

A tuple marked deleted is not immediately **reclaimable**. The key condition is that no remaining transaction/snapshot can see it.

## 7. Why Do Dead Tuples Cause Table Bloat?

Suppose a table has 1 million accounts and updates 30% of them every day:

```text
UPDATE 300,000 rows
  → creates new tuple versions
  → old versions gradually become dead
  → heap pages must hold new versions
  → indexes must process related entries
```

If dead tuples are not cleaned up:

- Sequential scans read many pages containing tuples that are no longer visible.
- Index scans may encounter entries pointing to dead heap tuples.
- Cache gets occupied by low-value pages.
- Table/index bloat can grow.
- Disk and backup sizes can increase.
- Planner statistics may no longer reflect the data distribution.

**VACUUM helps reclaim/reuse space inside the relation** and maintains visibility/free-space metadata. It does not by itself shrink every index/table back to its smallest possible size.

## 8. HOT Updates and Their Relationship to VACUUM

PostgreSQL can use a **Heap-Only Tuple (HOT) update** when conditions are met, typically:

- The UPDATE does not modify indexed columns in a way that prevents HOT.
- The page holding the tuple has enough free space for the new version.

A HOT update can avoid creating new index entries because the version chain is managed within the heap page. This reduces index churn and index vacuuming work in certain workloads.

### Fillfactor

For frequently updated tables, lowering fillfactor can leave free space on heap pages to increase the likelihood of HOT updates:

```sql
ALTER TABLE lesson_vacuum.accounts
SET (fillfactor = 80);
```

This is only a configuration example. A lower fillfactor makes the table require more pages upfront and does not guarantee every UPDATE becomes HOT. Change it only after measuring `n_tup_hot_upd`, update patterns, and disk/cache trade-offs.

## 9. How Heap Pruning Differs from VACUUM

**Pruning** can clean up certain dead tuple versions directly on a heap page when the page is accessed and visibility conditions allow. It helps shorten version chains and reuse space on the page.

**VACUUM** performs broader work across the relation:

- Scans the heap to find dead tuples.
- Reclaims space for the relation to reuse.
- Processes related index entries when needed.
- Updates the visibility map.
- Freezes sufficiently old tuples.
- Updates metadata for future vacuums.

Pruning does not replace a full VACUUM: it does not guarantee scanning every page or completing all freezing/index cleanup tasks.

## 10. What Does VACUUM Do?

Command:

```sql
VACUUM lesson_vacuum.accounts;
```

Standard VACUUM:

1. Finds reclaimable dead tuples based on the visibility horizon.
2. Processes the corresponding index entries.
3. Marks freed space for reuse by PostgreSQL.
4. Updates the visibility map and related metadata.
5. Freezes sufficiently old tuples when needed to prevent transaction ID wraparound.

Standard VACUUM is designed to run concurrently with most normal read/write activity. However, it still consumes I/O/CPU, takes its own locks, and can contend with the workload. "Online" does not mean free.

### What Does VACUUM Not Do?

- It does not immediately erase all old data from the OS file.
- It does not automatically fix corrupted business data.
- It does not replace ANALYZE.
- It cannot remove tuples still needed by an old snapshot.
- It does not guarantee shrinking an index/table to minimum size.
- It does not resolve every kind of bloat immediately.

## 11. Space Reuse vs. Disk Shrink

After VACUUM:

- A page can contain free space for PostgreSQL to reuse on subsequent INSERT/UPDATE operations.
- The relation file usually keeps the same physical size as before.
- PostgreSQL can return some space at the end of a relation to the operating system under suitable conditions, but you should not expect normal VACUUM to noticeably shrink files.

### Example

Suppose a table once occupied 20 GB, most rows are deleted, and VACUUM runs. PostgreSQL can reuse that space for future INSERTs while the file remains close to 20 GB.

This alone does not prove vacuum failed. If the workload will grow again, keeping space ready for reuse can be more efficient than shrinking the file only to extend it again later.

## 12. VACUUM FULL vs. VACUUM

```sql
VACUUM FULL lesson_vacuum.accounts;
```

VACUUM FULL rewrites the relation to eliminate most internal free space and shrink the file when possible.

| Characteristic | VACUUM | VACUUM FULL |
|---|---|---|
| Can run alongside normal DML | Usually yes | No, requires a strong lock |
| Reclaims dead tuples | Yes | Yes, via rewrite |
| Shrinks relation file | Usually negligible | Yes, possible |
| Rewrites entire relation | Not in the FULL sense | Yes |
| Temporary disk space | Usually lower | Requires extra space for rewrite |
| Blocking | Less blocking, still has lock/IO | ACCESS EXCLUSIVE for the duration |
| Run routinely? | Routine maintenance task | Only when specifically planned |

### Why Not Run VACUUM FULL Routinely?

It can block SELECT/INSERT/UPDATE/DELETE on the table for the entire rewrite duration, requires temporary disk space, and generates heavy I/O. For critical online tables, this can mean significant downtime.

If you need to reclaim bloat without long blocking, evaluate appropriate online tools/strategies (such as planned restructuring or an extension like pg_repack where approved), while understanding their lock/space/replication trade-offs.

## 13. VACUUM and ANALYZE Are Two Different Tasks

```sql
ANALYZE lesson_vacuum.accounts;
VACUUM lesson_vacuum.accounts;
VACUUM (ANALYZE) lesson_vacuum.accounts;
```

| Command | Purpose |
|---|---|
| ANALYZE | Collects data distribution statistics for the query planner |
| VACUUM | Reclaims dead tuples, updates visibility/freeze metadata |
| VACUUM (ANALYZE) | Performs vacuum and collects statistics in the same operation |

A table that just had millions of rows loaded via COPY may need ANALYZE so the planner knows the new distribution even if there are few dead tuples.

A table with continuous UPDATE/DELETE activity may need VACUUM to clean up dead tuples while also needing updated statistics.

### VACUUM Does Not Automatically Mean ANALYZE

Autovacuum decides autovacuum and autoanalyze using separate thresholds. Do not assume every vacuum automatically refreshes statistics like a `VACUUM (ANALYZE)`.

## 14. What Is Freezing?

PostgreSQL uses transaction IDs from a finite space. So that an old tuple is not misinterpreted when transaction IDs wrap around, the engine can **freeze** sufficiently old tuples: instead of relying on a very old XID forever to determine visibility, the tuple is marked with special frozen semantics.

### Why Is Freezing Needed?

Traditional transaction IDs are 32-bit and wrap around cyclically. If a database runs long enough without freezing old tuples, a transaction ID can wrap around to a numeric value used in the past. An old tuple could then risk being treated as created by a "future" transaction or having incorrect visibility.

This is a **wraparound hazard** that can make safe access impossible if not handled before the danger threshold. Therefore, VACUUM does not only clean up dead tuples; it must also keep the transaction age of data within safe bounds.

### Freezing Does Not Delete Data

Live tuples can be frozen. Freezing does not lose rows; it makes the tuple's transaction metadata safe against XID wraparound.

## 15. Transaction ID Wraparound

An XID is a 32-bit counter that wraps around after a fixed number of transactions. PostgreSQL uses modular comparison rules and limits the XID distance to determine which transaction is older or newer.

### Risks

If tuples still carry XIDs that are too old and the system approaches wraparound:

- Visibility semantics can become unsafe.
- PostgreSQL may have to force anti-wraparound vacuum.
- Upon reaching a critical protective limit, the server may refuse certain writes/new transactions to avoid corruption.
- The system can enter a state where only operations needed to vacuum and rescue the database are allowed.

### Do Not Wait Until Disk Is Full to Care

Wraparound is a **transaction age** problem, not simply disk capacity. A database with few rows that generates very many transactions can still need freezing; a large, rarely modified table can also hold very old tuples that need freezing.

## 16. Anti-Wraparound Vacuum

Autovacuum has a mechanism to prioritize vacuuming to freeze tuples before exceeding safe limits. Key settings:

| Setting | Conceptual Meaning |
|---|---|
| `autovacuum_freeze_max_age` | XID age threshold at which anti-wraparound freeze vacuum is triggered |
| `vacuum_freeze_min_age` | Minimum XID age at which vacuum considers freezing a tuple |
| `vacuum_freeze_table_age` | Relation age at which vacuum performs a more aggressive scan/freeze per policy |
| `vacuum_failsafe_age` | Failsafe threshold in supported versions, making vacuum prioritize wraparound rescue and reduce certain costs |
| `autovacuum_multixact_freeze_max_age` | MultiXact age threshold related to anti-wraparound |

Names, defaults, and interaction details vary by version. Check the actual configuration:

```sql
SELECT
    name,
    setting,
    unit,
    context,
    source
FROM pg_catalog.pg_settings
WHERE name LIKE '%freeze%'
   OR name LIKE '%multixact%'
ORDER BY name;
```

### Do Not Disable Autovacuum to "Reduce Load"

Autovacuum can be tuned or temporarily paused in certain maintenance situations, but disabling it long-term without a manual vacuum/freeze replacement process is dangerous. Anti-wraparound vacuum may still be triggered at special priority even if normal autovacuum is disabled on a table, depending on settings/version.

## 17. MultiXact Wraparound

Not only single XIDs need freezing. PostgreSQL also has **MultiXact IDs** to represent multiple transactions holding row locks together in certain situations.

If MultiXact age grows too high without being handled, the database risks MultiXact wraparound. Therefore, monitor all of:

- XID age.
- MultiXact age.
- Autovacuum/freeze progress.
- Tables with old tuples or long-held transaction horizons.

### Important

Do not assume a database is safe just because `age(datfrozenxid)` is still low. Also check `mxid_age(datminmxid)` and the MultiXact warnings for your version.

## 18. Monitoring XID Age at the Database Level

Query:

```sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age,
    mxid_age(datminmxid) AS multixact_age
FROM pg_catalog.pg_database
ORDER BY xid_age DESC;
```

### Reading the Results

- `age(datfrozenxid)` estimates the age of the oldest transaction ID still tracked by database metadata.
- `mxid_age(datminmxid)` measures MultiXact age in the corresponding manner.
- Increasing values should be compared against configured thresholds and tracked over time.

These are **age** counts, not time in seconds/days and not the number of currently running transactions.

### Alerting

Set alerts on both absolute thresholds and rate of growth. A database whose XID age is currently moderate but climbing rapidly while autovacuum cannot keep up needs early investigation.

## 19. Monitoring XID Age at the Table Level

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    age(c.relfrozenxid) AS xid_age,
    mxid_age(c.relminmxid) AS multixact_age,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm', 't')
ORDER BY age(c.relfrozenxid) DESC
LIMIT 30;
```

### Why Table-Level Matters

A rarely modified table holding old tuples may need freezing; a write-heavy table may need frequent vacuuming for dead tuples. Database-level age shows the overall state, while table-level identifies which relations need priority attention.

### Note

Catalog columns and relation kinds can differ by table type/version. This query is an investigation tool, not a replacement for PostgreSQL's wraparound warnings.

## 20. Freezing and the Visibility Map

PostgreSQL maintains a **visibility map (VM)** with bits per heap page, whose key states include:

- **All-visible:** all tuples on the page are known to be visible to all current transactions according to VM conditions.
- **All-frozen:** the tuples on the page have been frozen according to the required semantics.

VACUUM updates these bits when possible.

### Why Is This Useful?

The VM lets PostgreSQL know a page can skip certain visibility checks along suitable access paths. In particular, it supports **index-only scans**: if an index contains all columns needed by a query and the heap page is marked all-visible, the executor can avoid reading the heap page to check visibility for every tuple.

### Index-Only Scans Do Not Always Read Only the Index

If the VM bit is not set or the page was modified after vacuum, the executor may still have to visit the heap to confirm tuple visibility. Thus, a query using an index-only scan in EXPLAIN can still show Heap Fetches.

## 21. How Does VACUUM Help Index-Only Scans?

Example index:

```sql
CREATE INDEX ix_accounts_balance_cover
ON lesson_vacuum.accounts (account_id)
INCLUDE (balance);

EXPLAIN (ANALYZE, BUFFERS)
SELECT account_id, balance
FROM lesson_vacuum.accounts
WHERE account_id BETWEEN 1 AND 1000;
```

The index contains all returned columns. If the corresponding heap pages are all-visible, PostgreSQL can execute an index-only scan with fewer heap fetches.

### Experiment

1. Load many rows.
2. Run the query and inspect Heap Fetches.
3. Run VACUUM.
4. Re-run the query on unchanged data.
5. Compare plans, heap fetches, and buffers.

Results depend on cache, page visibility, workload, and the planner; running VACUUM alone does not guarantee the planner will always choose an index-only scan.

## 22. New INSERTs and All-Visible Pages

A page that just received a new INSERT/UPDATE is no longer all-visible. New data requires MVCC visibility checks. A later VACUUM can mark the page again when conditions allow.

### Why Does This Matter?

An append-only table may have few dead tuples yet still need vacuuming to:

- Freeze old tuples.
- Set all-visible/all-frozen bits.
- Support index-only scans.
- Keep XID age safe.

That is why autovacuum also has an **insert-triggered vacuum threshold** in supported versions, rather than relying only on UPDATE/DELETE counts.

## 23. Freezing Does Not Mean Every Page Is Scanned Every Time

VACUUM has multiple strategies and can use the visibility map to skip unnecessary pages for certain work. When aggressive freeze thresholds are reached, more pages must be scanned to ensure old tuples get frozen.

### Impact

- A large, rarely updated table may not need frequent dead-tuple cleanup, yet still needs age-based freezing.
- A write-heavy table may need continuous vacuuming to reclaim space and update the VM.
- A normal vacuum does not necessarily make the entire relation all-frozen.

Do not rely solely on dead tuple count to decide whether a table is adequately maintained.

## 24. Snapshot Horizon: Why Can't VACUUM Clean Up?

An old tuple is reclaimable only when no remaining snapshot can see it. Sources that hold back the horizon:

- A long-running transaction at REPEATABLE READ/SERIALIZABLE.
- A transaction running a long query and holding a snapshot.
- An `idle in transaction` session.
- Unresolved prepared transactions.
- Replication slots holding `xmin`/`catalog_xmin`.
- Standby feedback holding back xmin on the primary when enabled.

### Result

VACUUM can finish running without reclaiming many dead tuples if the visibility horizon is still pinned by old transaction/replication state.

This is why "autovacuum is running" does not automatically mean "dead tuples are definitely being cleaned up".

## 25. Long-Running Transactions Holding Dead Tuples

Example:

```text
Session A:
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT ...;   -- old snapshot is held

Session B:
UPDATE many rows;
COMMIT;

Autovacuum:
scans the table but cannot remove tuples that A still needs
```

If A holds its transaction open for hours, old versions may have to stay around for hours. The table continues receiving writes and generating new dead tuples, increasing bloat.

### Danger of idle in transaction

An application that opens a transaction, runs a SELECT, and then waits on user input or an external API call without committing or rolling back can hold a snapshot open for a long time even with no active query running.

### Prevention

- Short transaction boundaries.
- Do not wait on network/user input inside a transaction.
- Enforce `idle_in_transaction_session_timeout` per policy.
- Monitor xact age and `backend_xmin`.
- Fix connection/transaction leaks in the application.

## 26. Checking Old Transactions

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    now() - xact_start AS xact_age,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 160) AS query_preview
FROM pg_catalog.pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start
LIMIT 30;
```

### Finding Specific Sessions

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    now() - state_change AS state_age,
    now() - xact_start AS xact_age,
    backend_xmin
FROM pg_catalog.pg_stat_activity
WHERE state LIKE 'idle in transaction%'
ORDER BY xact_start NULLS LAST;
```

### Do Not Terminate Blindly

An old transaction might be a migration, an important report, or a prepared workflow. Before calling `pg_terminate_backend`, verify the owner, rollback impact, lock dependencies, and whether the application can safely retry.

## 27. Prepared Transactions and the VACUUM Horizon

Two-phase commit can leave behind a prepared transaction that has not yet been COMMIT PREPARED or ROLLBACK PREPARED. A long-lived prepared transaction can hold transaction ID/snapshot-related state and prevent vacuum from making progress.

Check:

```sql
SELECT
    transaction,
    gid,
    prepared,
    owner,
    database
FROM pg_catalog.pg_prepared_xacts
ORDER BY prepared;
```

### How to Handle

Each prepared transaction must be committed or rolled back by its coordinator based on the distributed transaction state. Do not blindly roll it back just because it looks old; the wrong action can desynchronize state across systems.

Do not use prepared transactions as a way to keep transactions open for long periods "waiting until needed".

## 28. Replication Slots Can Pin the VACUUM Horizon

Replication slots retain WAL needed by consumers and, in certain configurations, also hold tuple/catalog horizons so logical decoding can continue correctly. An unconsumed logical slot can hold `xmin` or `catalog_xmin` back for a long time, preventing dead tuples/catalog rows from being reclaimed.

Check:

```sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    xmin,
    catalog_xmin,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_catalog.pg_replication_slots
ORDER BY slot_name;
```

### Reading the Fields

- `active`: whether the slot currently has a connected consumer.
- `xmin`: horizon related to tuple visibility if the slot retains this value.
- `catalog_xmin`: horizon related to catalog tuples.
- `restart_lsn`: WAL position still required by the slot.
- `confirmed_flush_lsn`: position confirmed by the consumer for a logical slot where applicable.

### Risks

A long-inactive slot can both retain WAL, growing disk usage, and block vacuum cleanup. Do not drop a slot arbitrarily: the consumer may lose the ability to resume from its previous position and require reinitialization/re-snapshot.

## 29. Checking Replication xmin and WAL Retention

Summary query:

```sql
SELECT
    slot_name,
    active,
    age(xmin) AS xmin_age,
    age(catalog_xmin) AS catalog_xmin_age,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint
    ) AS retained_wal_estimate
FROM pg_catalog.pg_replication_slots
ORDER BY retained_wal_estimate DESC NULLS LAST;
```

### Notes

`age(xmin)`/`age(catalog_xmin)` can return NULL if the corresponding field has no value. The WAL estimate here compares against the current LSN; actual retention also depends on other slots, archiving, WAL recycling, checkpoints, and server configuration.

Do not take an inactive replication slot and drop it immediately in production just to let vacuum run faster. Verify the consumer, owner, whether data can be rebuilt, and the plan to recreate the slot first.

## 30. hot_standby_feedback and Primary Vacuum

A standby can send xmin feedback so the primary does not remove tuples still needed by queries on the standby. This helps reduce some recovery conflicts on the standby, but can cause the primary to retain dead tuples longer.

Check the setting:

```sql
SHOW hot_standby_feedback;
```

On the primary, you can inspect replication status:

```sql
SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag,
    backend_xmin
FROM pg_catalog.pg_stat_replication;
```

### Trade-Offs

- Enabling feedback can reduce query cancellations on the standby.
- However, old xmin feedback can retain dead tuples on the primary, increasing bloat.
- Disabling feedback can cause standby queries to be canceled due to recovery conflicts.

Choose based on primary/replica SLAs, long-running reports, and storage capacity; there is no single right setting for every system.

## 31. Replication Slots vs. Standby Feedback

| Mechanism | Primarily Serves | Risk If Held Long-Term |
|---|---|---|
| Replication slot | Retains WAL and/or logical decoding horizon | WAL disk growth, vacuum horizon pinned old |
| hot_standby_feedback | Reports xmin from standby to primary | Primary retains dead tuples longer |
| Long-running standby query | Needs snapshot on standby | Recovery conflict or prolonged feedback horizon |
| Slow logical consumer | Has not confirmed newer LSN | Slot retains WAL and may hold catalog/data xmin |

These are distinct mechanisms; you must inspect both replication slots and standby activity to understand why vacuum is blocked.

## 32. What Is Autovacuum?

Autovacuum consists of daemon/launcher and worker components that automatically perform vacuum/analyze based on statistics, thresholds, and resource limits.

### Two Primary Tasks

**Autovacuum (VACUUM):**

- Reclaims dead tuples.
- Freezes old tuples.
- Maintains visibility map/free space.
- Reduces wraparound risk.

**Autoanalyze (ANALYZE):**

- Collects statistics after enough data has changed.
- Helps the planner refresh cardinality/distribution estimates.

An autovacuum worker can perform vacuum and/or analyze on a relation depending on why it was triggered.

## 33. Why Not Run Manual VACUUM Continuously?

Manual VACUUM is useful for targeted operations, but for continuous workloads the automatic daemon has key advantages:

- Automatically tracks changed tuple counts.
- Selects relations that reach thresholds.
- Runs multiple workers within configured limits.
- Automatically freezes based on XID age.
- Reduces the need for rigid cron jobs running VACUUM on every table.

### However, Autovacuum Is Not "Enable and Forget"

If thresholds do not fit very large tables, workloads have high update rates, or vacuum workers lack sufficient resources, the daemon can fall behind. You must monitor metrics and tune based on evidence.

## 34. Autovacuum VACUUM Threshold Formula

For a table, the vacuum threshold driven by UPDATE/DELETE is described generally as:

\[
\text{vacuum threshold}
= \text{autovacuum\_vacuum\_threshold}
+ \text{autovacuum\_vacuum\_scale\_factor}
\times \text{estimated table rows}
\]

When the number of modified tuples exceeds the threshold according to statistics, the table becomes eligible for autovacuum consideration.

### Hypothetical Example

Suppose:

- Table has 10 million rows.
- Threshold is 50.
- Scale factor is 0.2.

\[
50 + 0.2 \times 10,000,000
= 2,000,050
\]

Using only this illustrative threshold, roughly 2 million tuple modifications are needed before vacuum triggers under that rule. On a large table, 20% can represent too many dead tuples before the next vacuum.

### Caution

This is a general formula for the UPDATE/DELETE threshold; there are separate thresholds for INSERT-triggered vacuum, wraparound, and additional conditions. Row counts are estimates, not instantaneous exact counts.

## 35. INSERT-Triggered Vacuum Threshold

In supported PostgreSQL versions, autovacuum provides:

- `autovacuum_vacuum_insert_threshold`
- `autovacuum_vacuum_insert_scale_factor`

The insert threshold has the general form:

\[
\text{insert vacuum threshold}
= \text{insert threshold}
+ \text{insert scale factor}
\times \text{estimated table rows}
\]

This matters for **append-only** tables: even with few UPDATE/DELETEs, new tuples still need freezing over time and vacuum can improve the visibility map for index-only scans.

Do not assume append-only tables do not need vacuuming.

## 36. Autoanalyze Threshold

Autoanalyze uses its own modification threshold, generally:

\[
\text{analyze threshold}
= \text{autovacuum\_analyze\_threshold}
+ \text{autovacuum\_analyze\_scale\_factor}
\times \text{estimated table rows}
\]

Once modifications since the last analyze exceed the threshold, the table can be picked for autoanalyze.

### Example

With a 5-million-row table, threshold 50, and scale factor 0.1:

\[
50 + 0.1 \times 5,000,000 = 500,050
\]

The planner may keep using stale statistics even after the data has changed substantially. On large tables, a smaller scale factor can help refresh statistics sooner.

### Analyze Is Not Only for UPDATE/DELETE

INSERTs also change data distribution. An append-only table that just grew from 1 million to 20 million rows may need autoanalyze so the planner does not estimate from outdated data.

## 37. Threshold and Scale Factor: Impact of Large Tables

Scale factor is a proportion of estimated rows. Therefore, the same configuration behaves very differently across table sizes:

| Table size | Scale factor 0.2 | Meaning |
|---:|---:|---|
| 10,000 rows | 2,000 rows | Relatively small threshold |
| 1,000,000 rows | 200,000 rows | Can accumulate many changes |
| 100,000,000 rows | 20,000,000 rows | Likely too late for a write-heavy workload |

### Why Is an Absolute Threshold Still Useful?

Scale factor alone gives tiny tables very low thresholds; an absolute threshold prevents vacuum/analyze from running excessively often on small tables after just a few modifications.

### Do Not Pick Scale Factors by Guesswork

Setting them too low causes autovacuum to run constantly and contend for I/O; setting them too high lets dead tuples/stale statistics build up. Base your choices on:

- UPDATE/DELETE/INSERT rates.
- Relation size and tuple width.
- Actual vacuum speed.
- Query plans and required freshness.
- Disk/WAL/CPU headroom.

## 38. Viewing Current Autovacuum Configuration

```sql
SELECT
    name,
    setting,
    unit,
    context,
    source
FROM pg_catalog.pg_settings
WHERE name LIKE 'autovacuum%'
   OR name LIKE 'vacuum%'
ORDER BY name;
```

Common settings:

| Setting | Role |
|---|---|
| `autovacuum` | Enables/disables launcher behavior at the server level |
| `autovacuum_naptime` | Interval the launcher waits between checking databases |
| `autovacuum_max_workers` | Maximum number of concurrent autovacuum workers |
| `autovacuum_vacuum_threshold` | Absolute threshold for vacuum triggered by UPDATE/DELETE |
| `autovacuum_vacuum_scale_factor` | Table-size proportion for vacuum threshold |
| `autovacuum_vacuum_insert_threshold` | Absolute threshold for vacuum triggered by INSERT on supported versions |
| `autovacuum_vacuum_insert_scale_factor` | Table-size proportion for insert threshold |
| `autovacuum_analyze_threshold` | Absolute threshold for autoanalyze |
| `autovacuum_analyze_scale_factor` | Table-size proportion for autoanalyze |
| `autovacuum_vacuum_cost_limit` | Cost budget for autovacuum workers |
| `autovacuum_vacuum_cost_delay` | Delay between cost-based throttling cycles |
| `autovacuum_work_mem` | Separate memory budget for vacuum workers if configured |

Some setting names may not exist on older versions; only configure parameters exposed by your server.

## 39. Workers and Autovacuum Throughput

`autovacuum_max_workers` limits how many autovacuum workers can run concurrently. If many tables cross thresholds at once, some may have to wait their turn.

### Increasing Workers Can Help When

- Many independent tables need vacuuming.
- CPU/I/O headroom is available.
- The worker queue frequently has a backlog.
- Individual workers finish their jobs, but the launcher cannot keep up with all relations.

### Increasing Workers Can Hurt When

- Disk is already saturated.
- The OLTP workload is latency-sensitive.
- Workers scanning large tables/indexes simultaneously cause I/O contention.
- RAM is insufficient for both workers and query workloads.

### Important Distinction

Increasing `autovacuum_max_workers` does not speed up a single table's vacuum proportionally; it increases how many vacuum jobs can run concurrently. For a single large table, speed depends on scan/index work, I/O, cost throttling, and the horizon.

## 40. Cost-Based Vacuum Delay

Autovacuum uses cost-based throttling to avoid saturating all I/O:

- Each page access/update type carries a cost.
- The worker accumulates cost.
- Once the budget is exceeded, the worker sleeps for the configured delay.

Settings:

```sql
SHOW autovacuum_vacuum_cost_limit;
SHOW autovacuum_vacuum_cost_delay;
SHOW vacuum_cost_limit;
SHOW vacuum_cost_delay;
```

### Trade-Offs

- High cost limit or low delay: vacuum can progress faster, but competes more for I/O.
- Low cost limit or high delay: reduces immediate workload impact, but vacuum may fall behind the write rate.

Do not disable throttling simply because vacuum is slow; first measure I/O saturation, old snapshots, and how many dead tuples are actually being cleaned.

## 41. Autovacuum Memory

`autovacuum_work_mem` can cap memory used per autovacuum worker (if supported by the setting/version). Vacuum must track tuple identifiers and handle index cleanup; for large tables/indexes, memory budget can affect the number of index cleanup passes and efficiency.

### Do Not Calculate Memory Naively

Having 8 workers each allowed 1 GB does not mean they always immediately allocate the full 8 GB. However, capacity planning must account for **worst-case/concurrent memory pressure**, other allocations, and query workloads.

Do not raise autovacuum memory without factoring in the total RAM of the PostgreSQL host/container.

## 42. Per-Table Autovacuum Settings

A write-heavy table may need custom thresholds:

```sql
ALTER TABLE lesson_vacuum.accounts
SET (
    autovacuum_vacuum_threshold = 1000,
    autovacuum_vacuum_scale_factor = 0.02,
    autovacuum_analyze_threshold = 500,
    autovacuum_analyze_scale_factor = 0.01
);
```

These numbers are **illustrative only** for one table; benchmark and base values on actual modification rates.

View reloptions:

```sql
SELECT
    c.oid::regclass AS relation,
    c.reloptions
FROM pg_catalog.pg_class AS c
WHERE c.oid = 'lesson_vacuum.accounts'::regclass;
```

### When to Use Per-Table Settings?

- Large tables with high update rates.
- Append-only tables needing insert-triggered vacuum/freeze.
- Rarely modified tables that do not need low thresholds.
- Tables with sensitive query latency requiring tuned vacuum impact.

Do not copy one set of reloptions to every table when workloads differ.

## 43. Can You Disable Autovacuum on a Table?

PostgreSQL allows the `autovacuum_enabled` reloption on certain relations:

```sql
-- Illustrative to understand configuration; not recommended long-term:
ALTER TABLE lesson_vacuum.accounts
SET (autovacuum_enabled = false);
```

### Risks

- Dead tuples accumulate.
- Statistics are not refreshed automatically.
- XID/MultiXact freeze maintenance is delayed.
- The relation can approach wraparound.

### Anti-Wraparound

Do not assume `autovacuum_enabled=false` disables all anti-wraparound protection. PostgreSQL has mechanisms to force vacuuming to protect the database; exact behavior depends on version and server state.

If a table needs a custom maintenance workflow, there must be a **manual vacuum/analyze/freeze schedule**, XID age alerts, and clear ownership. Disabling autovacuum without a runbook is dangerous configuration.

## 44. Why Can Autovacuum Fall Behind?

Common reasons:

1. UPDATE/DELETE rate exceeds vacuum speed.
2. Table scale factor produces a threshold that is too high.
3. Too few autovacuum workers for many tables.
4. Cost throttling is too restrictive for the workload.
5. I/O/CPU saturation.
6. A long-running transaction holds the snapshot horizon.
7. A replication slot or standby feedback holds xmin.
8. Vacuum gets canceled by conflicting operations.
9. Table/partition has unsuitable reloptions.
10. Autovacuum does not handle the relation as the operator expects (e.g., temporary tables).

Do not merely increase workers when vacuum fails to remove tuples; if the horizon is pinned, adding workers will not solve the root cause.

## 45. Monitoring Tables via pg_stat_user_tables

```sql
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
    last_autoanalyze
FROM pg_catalog.pg_stat_user_tables
WHERE schemaname = 'lesson_vacuum'
ORDER BY n_dead_tup DESC;
```

### Reading the Columns

- `n_live_tup` and `n_dead_tup` are **statistical estimates**, not exact counts.
- `n_mod_since_analyze` indicates the estimated modifications since the last analyze.
- `last_autovacuum` and `autovacuum_count` show autovacuum worker history.
- `last_vacuum`/`vacuum_count` correspond to manual vacuums according to statistics.
- `last_autoanalyze` shows the most recent autoanalyze.

### Missing last_autovacuum Does Not Mean an Error

A table may be newly created, rarely modified, or not yet at threshold. For temporary tables, autovacuum cannot access session-local temp relations like persistent tables; the session that creates a temp table must manage ANALYZE/VACUUM itself when needed.

## 46. Dead Tuple Estimates Are Not Exact Counts

Query:

```sql
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    CASE
        WHEN n_live_tup + n_dead_tup > 0
        THEN round(
            100.0 * n_dead_tup
            / (n_live_tup + n_dead_tup),
            2
        )
        ELSE 0
    END AS estimated_dead_pct
FROM pg_catalog.pg_stat_user_tables
WHERE schemaname = 'lesson_vacuum'
ORDER BY n_dead_tup DESC;
```

This percentage is a **rough estimate**, useful for spotting relations to investigate rather than an exact bloat measurement. Do not alert solely on `dead_pct` while ignoring table size, tuple width, dead-tuple generation rate, and vacuum progress.

## 47. Viewing Running Autovacuum Workers

```sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    backend_type,
    state,
    query_start,
    now() - query_start AS query_age,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_preview
FROM pg_catalog.pg_stat_activity
WHERE backend_type = 'autovacuum worker'
ORDER BY query_start;
```

The backend type name can depend on version. This query helps identify workers, though it does not give full percentage progress; use the dedicated progress view for that.

## 48. pg_stat_progress_vacuum

While VACUUM is running, you can inspect:

```sql
SELECT
    pid,
    datid,
    relid::regclass AS relation,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed,
    index_vacuum_count,
    num_dead_tuples,
    max_dead_tuples
FROM pg_catalog.pg_stat_progress_vacuum;
```

### Common Phases

- Scanning heap: scanning heap pages.
- Vacuuming indexes: processing related index entries.
- Vacuuming heap: processing heap pages.
- Cleaning up indexes: completing index cleanup depending on mechanism/version.
- Truncating heap: may truncate empty pages at the end of the relation when conditions permit.
- Performing final cleanup: updating metadata/final work.

Phase and column names vary across versions and job types; inspect the catalog/view schema of the actual server.

### Reading Progress Correctly

`heap_blks_scanned` over `heap_blks_total` shows scan progress within the corresponding phase, not always an exact percentage of the "entire vacuum". A worker can transition phases and update progress indicators accordingly.

## 49. Monitoring Manual VACUUM and Autovacuum Progress

`pg_stat_progress_vacuum` can show both manual VACUUM and autovacuum workers. Combine with `pg_stat_activity`:

```sql
SELECT
    p.pid,
    p.relid::regclass AS relation,
    p.phase,
    a.backend_type,
    a.application_name,
    now() - a.query_start AS elapsed,
    a.wait_event_type,
    a.wait_event
FROM pg_catalog.pg_stat_progress_vacuum AS p
JOIN pg_catalog.pg_stat_activity AS a
  ON a.pid = p.pid
ORDER BY a.query_start;
```

### Investigating When Progress Stalls

- Is the worker waiting on I/O or a lock?
- Is there an overly old transaction horizon?
- Is index cleanup taking a long time?
- Is another vacuum running on the relation?
- Is disk throughput/latency saturated?
- Is the worker getting canceled/restarted?

Do not kill a worker simply because a phase runs for a long time; vacuuming a large table with many indexes can take minutes or hours.

## 50. Autovacuum Logging

Setting:

```sql
SHOW log_autovacuum_min_duration;
```

`log_autovacuum_min_duration` logs autovacuum operations that run longer than the configured threshold (or all runs when set to the appropriate version-specific value).

### What Logs Can Reveal

- Relation vacuumed/analyzed.
- Pages/tuples processed.
- Dead tuples removed or remaining.
- Execution duration.
- Index cleanup and memory details depending on version.
- Worker reason/characteristics.

### Do Not Enable Verbose Logging Without Sizing Log Volume

A database with thousands of tables and frequent autovacuum runs can generate substantial logs. Choose thresholds, retention, structured logging, and alerts according to investigation needs.

## 51. Distinguishing VACUUM, Autoanalyze, and Autovacuum Logs

In the stats table:

- `last_autovacuum` reports the most recent autovacuum vacuum according to statistics.
- `last_autoanalyze` reports the most recent autoanalyze.
- A single autovacuum worker can perform both tasks in one pass.
- `last_vacuum` reflects manual vacuuming, not auto counters.

Do not conclude "the table has been analyzed" just because `last_autovacuum` is recent; check `last_autoanalyze`/`last_analyze` and the relevant statistics.

## 52. Manual ANALYZE After Bulk Load

After a large data load:

```sql
ANALYZE lesson_vacuum.accounts;
```

Or:

```sql
ANALYZE lesson_vacuum.accounts (balance);
```

Statistics can be collected for the whole table or specific columns.

### Why Not Wait for Autovacuum?

Right after a bulk load, an important query may run immediately. If stale statistics do not reflect the new distribution, the planner can pick a poor plan. Manual ANALYZE refreshes them before opening up the workload.

### Does ANALYZE Clean Up Dead Tuples?

No. It updates planner statistics; it does not replace VACUUM.

## 53. Manual VACUUM and Key Syntax

Examples:

```sql
VACUUM (VERBOSE, ANALYZE) lesson_vacuum.accounts;

VACUUM (FREEZE, VERBOSE) lesson_vacuum.accounts;
```

- `VERBOSE` prints detailed progress/results to client/server output.
- `ANALYZE` updates statistics.
- `FREEZE` requests more aggressive freezing per VACUUM semantics.

### Transaction Blocks

`VACUUM` and `VACUUM FULL` cannot run inside an explicit transaction block. Run them as standalone top-level commands, not inside `BEGIN ... COMMIT` or a migration framework that wraps all DDL/DML in a transaction.

### FREEZE Is Not a Daily Command

Autovacuum already manages freezing by XID age. Use manual FREEZE when there is a clear reason—such as preparing a new table or a specific maintenance window—and you understand the scan/lock cost.

## 54. VACUUM FULL and Bloat Remediation Options

If you need to shrink a relation, first determine:

- Are there unvacuumed dead tuples?
- Are long-running transactions holding back the horizon?
- Is the bloat in the heap or in indexes?
- Will the table grow again after cleanup?
- Is there enough disk space for a rewrite and WAL/replication?

### VACUUM FULL

```sql
VACUUM FULL lesson_vacuum.accounts;
```

Requires an `ACCESS EXCLUSIVE` lock and rewrites the relation. Plan a downtime/maintenance window and check free disk space, replication, and dependent objects.

### REINDEX

If bloat is mainly in indexes, consider `REINDEX INDEX`/`REINDEX TABLE` or the `CONCURRENTLY` variant when supported by your version and appropriate for your requirements. REINDEX does not replace heap vacuuming or resolve a pinned snapshot horizon.

### Do Not Measure Bloat by File Size Alone

A 100 GB table with 50 GB of reusable space may still be well-suited for a workload about to insert more data; a small index might have high relative bloat without causing meaningful latency. Use proper measurements/extensions and workload impact before rewriting.

## 55. VACUUM and Partitioned Tables

With partitioned tables, physical data normally resides in **leaf partitions**. Autovacuum processes partitions that have storage like regular tables according to their own statistics/thresholds.

### Analyzing the Parent

A partitioned parent does not contain heap rows like a leaf. Autovacuum does not always automatically update aggregate statistics on the partitioned parent the way operators expect; many versions require running manual `ANALYZE` on the parent after partition changes so the planner has partitioned-level statistics.

### Workflow

1. Check vacuum/analyze on each leaf partition.
2. After attaching/loading a partition, run ANALYZE on the parent when needed.
3. Monitor XID age across relations.
4. Plan partition detach/drop according to retention.
5. Check index/constraint inheritance and DDL lock behavior.

### Do Not Confuse DROP PARTITION with Per-Row DELETE

Detaching/dropping a partition has different DDL/storage semantics from DELETE; it does not create a dead tuple per row, and you should not expect row-level DELETE triggers to fire an event for every row when a partition is dropped.

## 56. TOAST Tables Also Need Vacuuming

PostgreSQL can store large values such as TEXT/BYTEA/JSONB out-of-line in a **TOAST relation**. When rows with large values are updated or deleted, TOAST data can also accumulate dead tuples.

VACUUM on the main table manages the associated TOAST relations according to PostgreSQL's mechanism.

### When Investigating

- Check `pg_total_relation_size`, not just heap `pg_relation_size`.
- Watch TOAST relation size when tables store large payloads.
- Do not vacuum only the heap and assume all space was evaluated.
- Measure index/TOAST storage and update patterns.

A table with few rows where each row holds a large JSONB document can generate significant write amplification when payloads are updated.

## 57. Temporary Tables and Autovacuum

The autovacuum daemon cannot process temporary tables belonging to other sessions the way it handles persistent tables. The session owning a temp table must ensure its own statistics/vacuum when needed.

Example:

```sql
CREATE TEMP TABLE temp_events AS
SELECT *
FROM lesson_vacuum.accounts;

ANALYZE temp_events;
```

### Why Does This Matter?

A session creating a temp table with millions of rows and then running complex joins may need ANALYZE so the planner picks a good plan. Not seeing `last_autovacuum` for a temp table does not mean the autovacuum daemon is broken.

### Lifecycle

A temporary relation lives for the session/transaction depending on its `ON COMMIT` clause. When using a connection pool, a session-local temp table may remain on the physical connection after the application returns its logical lease; clean up properly and understand your PgBouncer pooling mode.

## 58. Autovacuum Needs Statistics Tracking Enabled

Autovacuum relies on statistics to determine which relations have crossed thresholds. Check:

```sql
SHOW autovacuum;
SHOW track_counts;
SHOW autovacuum_naptime;
```

If count tracking is disabled or autovacuum is not configured to run as expected, the launcher may lack the data required to schedule normal vacuum/analyze runs.

### Do Not Check Only One Setting

A table may have custom reloptions, a database may have a different workload, and the server has worker/cost limits. Investigate all of:

- Global settings.
- Database/table reloptions.
- Statistics counters.
- Running workers.
- XID horizon and replication state.

## 59. Autovacuum Launcher and Database Scheduling

The launcher periodically inspects databases and launches workers as needed. `autovacuum_naptime` is the interval between database checks as configured; it does not mean every table is vacuumed on that exact period.

### Why Might a Table Wait?

- Multiple databases have tables exceeding thresholds.
- The maximum number of workers are already busy.
- A vacuum job runs for a long time.
- Cost throttling or I/O slows down workers.
- A relation is locked/conflicted.

Autovacuum is a resource-bounded scheduler, not a dedicated worker per table.

## 60. Lock Impact of Normal VACUUM

Normal VACUUM takes locks that allow most normal DML/SELECTs to continue, but it can still conflict with certain DDL/maintenance operations and other vacuums on the same relation.

### Things to Remember

- Normal VACUUM does not require `ACCESS EXCLUSIVE` like VACUUM FULL.
- DDL such as certain `ALTER TABLE` operations may have to wait or make vacuum wait depending on lock mode.
- A migration holding a lock can block autovacuum.
- Vacuum also generates I/O/CPU pressure even without locking the whole table.

### Investigating Locks

```sql
SELECT
    a.pid,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    l.mode,
    l.granted,
    l.relation::regclass AS relation
FROM pg_catalog.pg_locks AS l
JOIN pg_catalog.pg_stat_activity AS a
  ON a.pid = l.pid
WHERE l.relation = 'lesson_vacuum.accounts'::regclass
ORDER BY l.granted, a.pid;
```

This query is only a snapshot of current locks; correlate blocked/blocking PIDs and query text to find the root cause.

## 61. Dead Tuples After UPDATE and DELETE

Practice:

```sql
CREATE TABLE lesson_vacuum.churn_demo (
    id BIGINT PRIMARY KEY,
    payload TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

INSERT INTO lesson_vacuum.churn_demo (id, payload)
SELECT g, repeat('x', 100)
FROM generate_series(1, 100000) AS g;

UPDATE lesson_vacuum.churn_demo
SET payload = payload || '-v2',
    updated_at = clock_timestamp();

DELETE FROM lesson_vacuum.churn_demo
WHERE id % 10 = 0;
```

After committing, inspect statistics:

```sql
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_tup_hot_upd
FROM pg_catalog.pg_stat_user_tables
WHERE relid = 'lesson_vacuum.churn_demo'::regclass;
```

Counters can update with a slight delay/estimation and depend on the statistics collector. This exercise demonstrates generating churn, not an exact measurement immediately after a statement.

## 62. Observing Before and After VACUUM

Run:

```sql
VACUUM (VERBOSE) lesson_vacuum.churn_demo;
```

Then query again:

```sql
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_catalog.pg_stat_user_tables
WHERE relid = 'lesson_vacuum.churn_demo'::regclass;
```

### Expectations

If no old transaction is holding the horizon and VACUUM completes, dead tuples should drop substantially. Statistical numbers remain estimates and may take a moment to refresh; `VERBOSE` output provides more concrete details on the work performed.

### Do Not Expect the File to Shrink

Check:

```sql
SELECT
    pg_size_pretty(pg_relation_size(
        'lesson_vacuum.churn_demo'
    )) AS heap_size,
    pg_size_pretty(pg_total_relation_size(
        'lesson_vacuum.churn_demo'
    )) AS total_size;
```

VACUUM can create reusable space without noticeably shrinking the relation file.

## 63. HOT Update Counters

To observe HOT updates:

```sql
SELECT
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    CASE
        WHEN n_tup_upd > 0
        THEN round(
            100.0 * n_tup_hot_upd / n_tup_upd,
            2
        )
        ELSE 0
    END AS hot_update_pct
FROM pg_catalog.pg_stat_user_tables
WHERE schemaname = 'lesson_vacuum';
```

### Interpretation

A high HOT ratio can reduce index churn for update workloads, though it is not the sole optimization goal. If updates frequently modify indexed columns or pages lack enough free space, the HOT rate will be low.

### Experiment

Compare updates on an unindexed column versus an indexed column; observe `n_tup_hot_upd`, relation/index sizes, and throughput on sufficiently large data.

## 64. An Example Holding a Snapshot to See Vacuum Unable to Clean Up

Create a row:

```sql
INSERT INTO lesson_vacuum.churn_demo (id, payload)
VALUES (200001, 'original');
```

**Session A**:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT payload
FROM lesson_vacuum.churn_demo
WHERE id = 200001;
```

**Session B**:

```sql
UPDATE lesson_vacuum.churn_demo
SET payload = 'changed'
WHERE id = 200001;
COMMIT;

VACUUM (VERBOSE) lesson_vacuum.churn_demo;
```

While A keeps its transaction open, the old version may still be needed. End A:

```sql
COMMIT;
```

Then run VACUUM again. If no other horizon blocker exists, the old version can now be reclaimed.

### Practical Conclusion

VACUUM is not "broken" when it leaves behind a tuple still visible to an old snapshot. That is the required correctness guarantee of MVCC.

## 65. Checking Bloat and Free Space

There is no single column in `pg_stat_user_tables` that tells you the exact number of bytes immediately reclaimable. `n_dead_tup` and `n_live_tup` are row-count estimates and do not fully reflect tuple width, page density, or index bloat.

### Investigation Tools

- `pg_relation_size` and `pg_total_relation_size`.
- The `pgstattuple` extension if allowed to install and scan cost is acceptable.
- `pg_stat_user_tables` dead tuple estimates.
- `pg_stat_progress_vacuum`.
- Index sizes and query plans.
- OS/provider disk metrics.

### pgstattuple

The `pgstattuple` extension can measure live/dead/free space for a relation, but scanning a large table can be I/O-intensive. Use it only after evaluating permissions, version, impact, and environment.

Do not conclude 50% bloat merely from calculating `dead_tup / (live_tup + dead_tup)`.

## 66. VACUUM Index Cleanup

When dead heap tuples are reclaimed, the corresponding index entries must also be handled according to the vacuum/index access method strategy. With many indexes, index cleanup can take substantial time.

### Options

Modern PostgreSQL versions provide options such as `INDEX_CLEANUP` for controlling index cleanup behavior:

```sql
-- Illustrative example; check your version documentation before using:
VACUUM (INDEX_CLEANUP AUTO) lesson_vacuum.churn_demo;
```

`AUTO` lets PostgreSQL decide using conditions/heuristics. Do not use `INDEX_CLEANUP OFF` as a routine way to make vacuum faster while leaving behind index cleanup debt.

### Why Be Careful?

If index entries pointing to dead TIDs are not cleaned up, indexes can keep growing or add cost to scans. Depending on workload/version, deferring index cleanup may simply shift that cost to a later vacuum.

## 67. Vacuum Failsafe

In supported versions, `vacuum_failsafe_age` and the failsafe mechanism help vacuum prioritize wraparound prevention when XID age approaches a critical threshold. Failsafe may disable certain cost delays or skip non-essential work to accelerate freezing.

### That Does Not Mean Relying on Failsafe

Failsafe is a **last line of defense**, not a maintenance plan. If alerts only fire once failsafe has already triggered, the system may already be in a risky state requiring urgent action.

### Monitoring

- XID age trend.
- `relfrozenxid` per relation.
- `datfrozenxid` per database.
- MultiXact age.
- Autovacuum worker backlog.
- Transaction/replication horizons.

Set alerts well ahead of the failsafe threshold so you have time to investigate.

## 68. Databases with Many Small Tables

A database with tens of thousands of small tables can force the autovacuum launcher to inspect many relations and workers to divide time across numerous jobs.

### Impact

- Catalog/scheduling overhead.
- Many short vacuum/analyze jobs.
- Worker contention.
- Differing absolute/scale-factor thresholds across tables.

### Mitigation

- Reduce unnecessary relations.
- Partition in a controlled design; avoid creating one partition per small key.
- Configure reasonable thresholds by workload group.
- Monitor vacuum counts and scheduling backlog.
- Do not raise worker count indefinitely when CPU/I/O are already saturated.

## 69. Tuning Example for a Write-Heavy Table

Suppose an `orders` table has 50 million rows and receives 5 million UPDATE/DELETEs per day. If the scale factor is too high, the table can accumulate many dead tuples before the next vacuum.

A test configuration:

```sql
ALTER TABLE lesson_vacuum.churn_demo
SET (
    autovacuum_vacuum_threshold = 2000,
    autovacuum_vacuum_scale_factor = 0.01,
    autovacuum_analyze_threshold = 1000,
    autovacuum_analyze_scale_factor = 0.005
);
```

These values are **not default recommendations**. The goal is to illustrate lowering the scale factor for a large table. Before applying, measure accumulated dead tuples, vacuum duration, dead-tuple generation rate, CPU/I/O, query latency, and autoanalyze frequency.

If vacuum runs too often and causes I/O contention, the thresholds may be too low. If dead tuples grow faster than vacuum cleanup, thresholds may be too high or vacuum throughput/horizon is blocked.

## 70. Append-Only Table Example

An insert-only `events` table:

```sql
CREATE TABLE lesson_vacuum.events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);
```

Few UPDATE/DELETEs does not mean no VACUUM is needed:

- New tuples must be frozen over time.
- The visibility map can be updated for index-only scans.
- Statistics need to reflect new row counts and distributions.

In very large append-only tables, monitor insert-triggered vacuum and analyze thresholds, XID age, VM coverage, and retention strategy.

## 71. Retention via DELETE vs. Partition Drop

### Time-Based DELETE

```sql
DELETE FROM lesson_vacuum.events
WHERE occurred_at < now() - interval '90 days';
```

DELETE creates dead tuples; VACUUM must clean them up. Deleting millions of rows can create a large transaction, heavy WAL, and bloat before vacuum runs.

### Partition Retention

If the table is partitioned by time, old partitions can be detached/dropped per retention policy. This DDL operation removes a relation/partition instead of creating a dead tuple for every row.

### Trade-Offs

- DELETE allows flexible row-level retention criteria, but creates churn and vacuum work.
- Dropping a partition can be faster for cleanly partitioned data, but involves DDL locks/dependencies and does not generate row-level DELETE audit events.

Do not choose partitioning solely to avoid VACUUM; query patterns, uniqueness, foreign keys, and partition lifecycle must also fit.

## 72. VACUUM and Autovacuum Under Write Spikes

A large batch update can cross thresholds very quickly. Autovacuum begins once a worker is scheduled; in the meantime, dead tuples continue accumulating.

### Measures

- Split batch updates to bound transaction size.
- Run ANALYZE after bulk loads if the planner needs fresh statistics.
- Choose appropriate per-table thresholds.
- Ensure autovacuum workers/cost budgets have enough headroom.
- Avoid long-running transactions holding snapshots.
- Monitor WAL, replica lag, and vacuum progress.

### Do Not Run VACUUM After Every Statement

Running VACUUM after every small UPDATE usually adds unnecessary overhead. Let autovacuum batch the work by threshold unless there is a specific operational reason for a manual vacuum.

## 73. ANALYZE and Multi-Column Statistics

If the planner misestimates correlated conditions across columns, default ANALYZE may not be enough for certain queries.

Example:

```sql
CREATE STATISTICS lesson_vacuum.stats_tenant_status
(dependencies, mcv)
ON tenant_id, status
FROM lesson_vacuum.accounts;

ANALYZE lesson_vacuum.accounts;
```

Extended statistics help the planner model certain relationships between columns. It does not replace VACUUM, and not every query uses every statistic type.

## 74. VACUUM in Managed PostgreSQL Environments

Managed databases still typically run PostgreSQL autovacuum, but users may not have permission to:

- Read all server logs.
- Change all `postgresql.conf` settings.
- Terminate every backend.
- Install arbitrary extensions.
- Access the filesystem directly.

### How to Operate

- Use the views and metrics permitted by the provider.
- Watch provider alerts for XID age/wraparound.
- Monitor replica/slot lag via the control plane.
- Use supported parameter groups/flags.
- Contact the provider before intervening in an anti-wraparound emergency.

Do not assume a managed-service superuser role has the exact same privileges as a self-hosted PostgreSQL superuser.

## 75. Wraparound Warnings to Distinguish

When XID age approaches thresholds, PostgreSQL can log warnings about databases/tables needing `vacuum freeze`. If it reaches critical limits, the server may start refusing writes to protect data.

### Right Response

1. Identify the database and relation with the highest XID age.
2. Check whether autovacuum workers are running or blocked.
3. Find long-running transactions and prepared transactions.
4. Check replication slots and standby feedback.
5. Ensure sufficient disk/CPU/I/O for vacuum to complete.
6. Run manual `VACUUM FREEZE` per plan and appropriate permissions if needed.
7. Watch age decrease and `relfrozenxid` advance.

### Do Not Just Increase max_connections or Restart

Restarting does not freeze tuples by itself. Increasing connections also does not help and may add load. The goal is to let vacuum make progress and release horizon blockers.

## 76. VACUUM FREEZE and When to Use It

```sql
VACUUM (FREEZE, VERBOSE) lesson_vacuum.churn_demo;
```

This is a top-level command, not inside a transaction block.

### Effect

Requests VACUUM to freeze tuples per the corresponding policy; useful in certain maintenance scenarios, preparing snapshots/clones, or addressing freeze age.

### Caution

- Scanning a large relation can generate significant I/O.
- It cannot bypass visibility rules for tuples still needed by an old snapshot.
- It does not replace finding horizon blockers.
- It should not be run indiscriminately across all production tables at once.

Normal autovacuum already manages freezing; manual FREEZE requires a specific justification.

## 77. Configuring Vacuum Failsafe and Cost

Inspect related settings:

```sql
SELECT
    name,
    setting,
    unit,
    context
FROM pg_catalog.pg_settings
WHERE name IN (
    'autovacuum_freeze_max_age',
    'vacuum_failsafe_age',
    'vacuum_cost_delay',
    'vacuum_cost_limit',
    'autovacuum_vacuum_cost_delay',
    'autovacuum_vacuum_cost_limit'
)
ORDER BY name;
```

Do not raise age thresholds too high to postpone freezing. XID/MultiXact safety limits are database-wide protections; pushing thresholds higher can shrink your reaction window before wraparound.

## 78. Which Relations Have High XID Age?

Extended query:

```sql
SELECT
    n.nspname,
    c.relname,
    c.relkind,
    age(c.relfrozenxid) AS xid_age,
    mxid_age(c.relminmxid) AS mxid_age,
    c.reltuples,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm', 't')
ORDER BY age(c.relfrozenxid) DESC
LIMIT 50;
```

### Note on relkind

The relation kinds listed are those that can have associated storage. Certain internal/system relations are also critical for catalog freezing; do not filter to only application schemas when investigating a database-wide wraparound warning.

## 79. Checking When a Table Was Last Vacuumed

```sql
SELECT
    schemaname,
    relname,
    last_autovacuum,
    last_vacuum,
    autovacuum_count,
    vacuum_count,
    n_dead_tup,
    n_live_tup
FROM pg_catalog.pg_stat_user_tables
ORDER BY last_autovacuum NULLS FIRST;
```

A table with no `last_autovacuum` is not automatically a problem. Combine row count, churn, `relfrozenxid` age, and insert/update rates to evaluate.

## 80. Why Can Autovacuum Be Canceled?

Several situations:

- DDL or lock conflict.
- The relation was dropped/altered while the worker was processing it.
- Server shutdown/restart.
- The worker was terminated by an administrator.
- Resource pressure or storage errors.

Autovacuum can retry in the next scheduling cycle, but if the same cause repeats, backlog grows. Monitor logs and `pg_stat_progress_vacuum`, not just failed runs.

### Caution with Migrations

A migration waiting on an autovacuum lock or vacuum waiting on a DDL lock can create blocking chains. Use lock timeouts and sensible deploy schedules, but do not broadly disable autovacuum just to make migrations "run faster".

## 81. Runbook: Dead Tuples Continuously Increasing

When dashboards show dead tuples growing across multiple scrapes:

1. Identify top tables by estimated dead tuples and total relation size.
2. Compare growth rate against `autovacuum_count`/`last_autovacuum`.
3. Check `pg_stat_progress_vacuum` to see if workers are running/advancing.
4. Check old transactions and `backend_xmin`.
5. Check replication slots, prepared transactions, and standby feedback.
6. Measure I/O, CPU, WAL, and replica lag.
7. Check table reloptions and global thresholds.
8. Determine whether dead tuples are actually being cleaned while the file keeps space for reuse.
9. Adjust thresholds/cost/workers in a controlled way.
10. Observe trends after the change, not just a single query.

### Do Not Confuse Bloat with Dead Tuple Estimates

If dead tuples drop while relation size stays unchanged, VACUUM may still be doing its job properly: space was reclaimed for reuse. If bloat truly hurts queries/storage, measure heap and indexes separately and plan an appropriate rewrite/reindex.

## 82. Runbook: Autovacuum Cannot Clean Up Even Though Worker Finishes

If a vacuum completes but dead tuple estimates remain high:

1. Check `VACUUM VERBOSE`/autovacuum logs to see how many tuples remain.
2. Check long-running transactions and snapshot horizons.
3. Check replication slot `xmin`/`catalog_xmin`.
4. Check standby feedback and long queries on replicas.
5. Check prepared transactions.
6. Check whether the relation had continuous writes during vacuum.
7. Determine if vacuum was limited by index cleanup/cost.

If a tuple can still be visible to an existing snapshot, vacuum **is not allowed** to remove it. Resolve the horizon blocker according to business/replication policy; do not try to force vacuum past visibility rules.

## 83. Runbook: XID Age Approaching Threshold

1. Read `age(datfrozenxid)` and `mxid_age(datminmxid)` by database.
2. Find relations with high `age(relfrozenxid)`/MultiXact age.
3. Check autovacuum workers, progress, and logs.
4. Identify old snapshots, prepared transactions, and replication slots.
5. Confirm enough disk space remains for vacuum to proceed.
6. Throttle non-essential workloads generating extra churn/transactions if needed.
7. Run manual VACUUM/FREEZE according to version, permissions, and plan.
8. Watch XID/MultiXact age decline and warnings clear.
9. After the incident, investigate why autovacuum fell behind.
10. Set alerts earlier to prevent repeat emergencies.

### Do Not Arbitrarily Raise Freeze Max Age

Raising the threshold does not solve slow vacuuming; it delays warnings/forced work and can erode your safety margin.

## 84. Runbook: Slow Queries Due to Table/Index Bloat

1. Measure latency and buffers with `EXPLAIN (ANALYZE, BUFFERS)` on a representative workload.
2. Check if statistics are stale; run ANALYZE when needed.
3. Check dead tuple estimates and vacuum history.
4. Check long snapshots and vacuum progress.
5. Measure heap/index sizes and free space with appropriate tools.
6. Check HOT update rate, indexes, and fillfactor.
7. Choose regular VACUUM, REINDEX, or rewrite depending on where the bloat is.
8. Evaluate lock/disk/WAL/replica impact.
9. Test in staging or a maintenance window.
10. Verify query plans/latency after remediation.

Do not run `VACUUM FULL` just because a query is slow; query plans, index design, locks, or I/O could be the real cause.

## 85. Autovacuum Design Checklist

### Workload

- Which tables are insert-heavy, update-heavy, delete-heavy?
- What is the hourly/daily churn rate?
- What are table/partition sizes and tuple widths?
- Is there heavy index/TOAST/audit overhead?
- How fresh do query statistics need to be for latency?

### Configuration

- Are `autovacuum` and `track_counts` enabled?
- Are thresholds/scale factors appropriate for large tables?
- Does insert-triggered vacuum need tuning?
- Are worker/cost/memory budgets sufficient?
- Have per-table reloptions been unintentionally disabled?

### Horizon and Safety

- Are there long-running or idle-in-transaction sessions?
- Are any prepared transactions left behind?
- Are inactive replication slots pinning xmin/WAL?
- Is standby feedback holding the horizon too long?
- Are XID/MultiXact ages alerted?

### Observability

- Dashboard for dead tuples, vacuum/analyze timestamps/counts.
- `pg_stat_progress_vacuum` and autovacuum logs.
- `pg_stat_activity`/`backend_xmin`/wait events.
- Database/table XID age.
- Disk/WAL/replication lag.

## 86. Common Misconceptions

**"DELETE immediately removes the row from the file."** No. DELETE marks the version no longer visible; cleanup happens later.

**"UPDATE simply overwrites the old value."** It normally creates a new tuple version under MVCC.

**"After VACUUM finishes, the file must shrink."** No. Most reclaimed space is reused internally within the relation.

**"VACUUM FULL is a faster VACUUM."** No. It rewrites the relation, takes a strong lock, and can block workloads.

**"ANALYZE cleans up dead tuples."** No. ANALYZE updates planner statistics.

**"VACUUM can always remove every dead tuple."** Not if a snapshot horizon still needs the tuple.

**"An idle connection holds the vacuum horizon."** Not necessarily. A session idle outside a transaction normally does not hold a snapshot like `idle in transaction`.

**"Having autovacuum enabled means no monitoring is needed."** No. Thresholds, worker capacity, horizons, and I/O can still cause vacuum to lag behind.

**"Append-only tables do not need vacuum."** No. Freezing and the visibility map still matter.

**"`n_dead_tup` is the exact number of dead tuples."** No. It is an estimate.

**"Increasing `autovacuum_max_workers` always makes vacuum faster."** No. It increases concurrent jobs and can worsen I/O contention.

**"Lowering scale factor is always good."** No. Too low can trigger continuous vacuum/analyze runs.

**"Disabling autovacuum on a table prevents all anti-wraparound vacuums."** No. PostgreSQL has special wraparound protection mechanisms.

**"A replication slot only retains WAL."** No. Logical slots can hold `xmin`/`catalog_xmin` and block cleanup.

**"`hot_standby_feedback` only has benefits."** No. It reduces recovery conflicts but can retain dead tuples on the primary.

**"VACUUM FREEZE ignores old transactions."** No. Visibility horizons must still be respected.

**"Index-only scans never read the heap."** Not always; the visibility map determines whether heap fetches are needed.

**"Increasing/tuning fillfactor makes every UPDATE HOT."** No. HOT also depends on indexed columns and page free space.

**"Dropping a partition is equivalent to deleting each row."** No. It is a different DDL/storage operation.

## 87. Practice Exercises

### Exercise 1 — What Is MVCC?

Explain why PostgreSQL uses multiple tuple versions instead of overwriting rows in place for every UPDATE.

### Exercise 2 — xmin and xmax

Describe the conceptual role of xmin/xmax. Why is xmax not always simply the transaction ID of a DELETE?

### Exercise 3 — Two Sessions

Open two sessions as in the REPEATABLE READ example. Session A reads balance, B updates/commits. Why does A still see the old value?

### Exercise 4 — DELETE

DELETE a row and explain why the heap file does not immediately shrink in size.

### Exercise 5 — Dead Tuples

UPDATE the same row 100 times. Describe the tuple versions and the condition required for old versions to be reclaimed.

### Exercise 6 — Heap Pruning

Distinguish on-page pruning from VACUUM scanning the relation and handling indexes/visibility metadata.

### Exercise 7 — Standard VACUUM

Run VACUUM on the lab table. List what tasks it performs and what it does not do.

### Exercise 8 — Space Reuse

Delete most rows, run VACUUM, then measure `pg_relation_size`. Why might size not drop even though space is reusable?

### Exercise 9 — VACUUM FULL

Compare locks, rewrites, disk requirements, and availability between VACUUM and VACUUM FULL.

### Exercise 10 — ANALYZE

Run ANALYZE after a bulk load. Explain why statistics can change query plans even when the dead tuple count is near 0.

### Exercise 11 — Visibility Map

Explain the all-visible and all-frozen bits. Why can vacuum help index-only scans reduce heap fetches?

### Exercise 12 — Index-Only Scan

Create an index with an `INCLUDE` column, run `EXPLAIN (ANALYZE, BUFFERS)`, and observe Heap Fetches before/after VACUUM.

### Exercise 13 — HOT Updates

Update an unindexed column and an indexed column. Compare `n_tup_upd`/`n_tup_hot_upd`.

### Exercise 14 — Fillfactor

Set a lower fillfactor on the lab table, run an update workload, and measure HOT rate and heap size. Why should you not apply this to every table?

### Exercise 15 — XID Wraparound

Explain what risk 32-bit transaction ID wraparound poses if old tuples are not frozen.

### Exercise 16 — Freezing

Why can live tuples still need freezing? Does freezing lose business data?

### Exercise 17 — MultiXact

Explain how a MultiXact differs from a single XID and why mxid age must be monitored.

### Exercise 18 — Database Age

Run the `age(datfrozenxid)` and `mxid_age(datminmxid)` query. Why are these values not numbers of days?

### Exercise 19 — Table Age

Use `pg_class.relfrozenxid`/`relminmxid` to find relations with high age. Why must you check system/catalog relations as well?

### Exercise 20 — Autovacuum Thresholds

Calculate the threshold when a table has 20 million rows, vacuum threshold 50, and scale factor 0.05. State the assumptions behind the calculation.

### Exercise 21 — Autoanalyze

Calculate the analyze threshold for a 5-million-row table, threshold 100, scale factor 0.02. Why does an insert-only table still need autoanalyze?

### Exercise 22 — Insert-Triggered Vacuum

Explain the role of `autovacuum_vacuum_insert_threshold` and `autovacuum_vacuum_insert_scale_factor` on append-only tables.

### Exercise 23 — Workers

A server has many tables crossing thresholds simultaneously. State when increasing `autovacuum_max_workers` helps and when it worsens I/O contention.

### Exercise 24 — Cost Delay

Compare `autovacuum_vacuum_cost_limit` and `autovacuum_vacuum_cost_delay`. What is the impact of high vs. low cost limit on throughput and foreground latency?

### Exercise 25 — Per-Table Settings

Set a low autovacuum scale factor for a write-heavy table. Inspect reloptions and measure before/after results.

### Exercise 26 — Long-Running Transaction

Hold a REPEATABLE READ transaction open, UPDATE the same row in another session, then run VACUUM. Explain why the old tuple remains.

### Exercise 27 — Idle in Transaction

Find long-running `idle in transaction` sessions using `pg_stat_activity`. Explain the risk to the vacuum horizon and how to prevent it in the application.

### Exercise 28 — Prepared Transactions

Read `pg_prepared_xacts`. Why should you not blindly run `ROLLBACK PREPARED` on an old transaction without confirming coordinator state?

### Exercise 29 — Replication Slots

Query `pg_replication_slots` and explain `xmin`, `catalog_xmin`, and `restart_lsn`. What problems can an inactive logical slot cause?

### Exercise 30 — Standby Feedback

Toggle `hot_standby_feedback` in an appropriate lab environment. Compare recovery conflicts on the standby against dead tuple retention on the primary.

### Exercise 31 — VACUUM Progress

While vacuuming a large table, query `pg_stat_progress_vacuum`. Explain the phases and why `heap_blks_scanned` is not the overall job percentage at every point.

### Exercise 32 — Autovacuum Logs

Set `log_autovacuum_min_duration` in a lab environment, generate churn, and read the logs. Which details tell you whether vacuum is keeping up?

### Exercise 33 — Dead Tuple Estimates

Query `n_live_tup`/`n_dead_tup`. Why should you not use `dead_pct` alone to conclude bloat?

### Exercise 34 — Partitioned Tables

Create a partitioned parent and several leaf partitions. Observe autovacuum on the leaves; run ANALYZE on the parent after loading and explain why that step is needed in many versions.

### Exercise 35 — TOAST

Load large JSONB payloads and update them repeatedly. Measure `pg_total_relation_size` and explain why TOAST also needs vacuuming.

### Exercise 36 — Temporary Tables

Create a TEMP table with many rows, ANALYZE it, and inspect statistics. Why does the autovacuum daemon not automatically process a session's temp table?

### Exercise 37 — DELETE Retention

Delete old data by timestamp, measure dead tuples/WAL, and run VACUUM. Compare against retention via partition drop.

### Exercise 38 — VACUUM FREEZE

Run `VACUUM (FREEZE, VERBOSE)` on a lab table. Explain the goal and why it should not be run simultaneously across all production tables.

### Exercise 39 — Handling a Wraparound Alert

Design a runbook for when `age(datfrozenxid)` rises rapidly. Include finding blockers, checking workers, replication slots, disk, and a manual freeze plan.

### Exercise 40 — End-to-End Operational Design

A PostgreSQL server has:

- An `orders` table with 100 million rows, 5 million UPDATEs/day.
- An append-only `events` table with 1 billion rows.
- A logical replication slot that occasionally goes inactive.
- A reporting transaction that can run for 45 minutes.
- Multiple monthly partitions.
- An OLTP API sensitive to p99 latency.

Design:

1. Autovacuum thresholds/scale factors for each table group.
2. Insert-triggered vacuum and autoanalyze for `events`.
3. Worker/cost/memory budgets based on CPU/I/O.
4. Dashboards for dead tuples, progress, and XID/MultiXact age.
5. Runbooks for reporting snapshots and replication slot horizons.
6. Retention policy: DELETE vs. partition drop.
7. ANALYZE plan for parent/partitions and statistics.
8. When to use VACUUM, VACUUM FREEZE, REINDEX, or VACUUM FULL.
9. How to protect p99 latency and replica lag during vacuum.
10. Alerting/escalation ahead of wraparound failsafe.

## Conclusion

**MVCC creates multiple tuple versions so readers see consistent snapshots while writers continue modifying data.** Because UPDATE/DELETE do not immediately erase old versions, PostgreSQL relies on VACUUM to reclaim dead tuples once they are no longer visible to any snapshot that needs them. VACUUM also updates the visibility map, performs index cleanup, and freezes sufficiently old tuples.

**Autovacuum is an essential automatic maintenance mechanism**, not merely a garbage-collection utility. It relies on thresholds/scale factors, statistics, worker capacity, and cost throttling to schedule vacuum/analyze. Large, write-heavy, and append-only tables can require different settings; measure dead tuple trends, vacuum duration, analyze freshness, and XID/MultiXact age instead of applying one setting across the whole database.

**The vacuum horizon is the core constraint:** long-running transactions, idle-in-transaction sessions, prepared transactions, replication slots, and standby feedback can pin old versions, preventing vacuum from removing them. When that happens, adding workers will not fix the root cause; you must locate and resolve the snapshot/replication blocker according to business policy.

Finally, VACUUM typically helps PostgreSQL **reuse space**, not necessarily shrink files. VACUUM FULL rewrites the relation and requires strong locks; ANALYZE updates statistics; freezing prevents XID/MultiXact wraparound. Good operations combine the right tools, monitoring progress and transaction age, keeping transactions short, and having runbooks ready before the database nears critical thresholds.
