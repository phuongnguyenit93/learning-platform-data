# Snapshot Consistency and the Impact of Running Dumps in PostgreSQL

A dump is only useful if the data inside reflects an explainable database state. While `pg_dump` runs, applications can still execute `INSERT`, `UPDATE`, and `DELETE`. If the tool read each table at different points in time without sharing one snapshot, tables inside the dump could mismatch: an order might be exported without its corresponding payment record, or a parent row and child row might reflect two different points in time.

PostgreSQL solves this using **MVCC snapshots** and transaction isolation. `pg_dump` holds a consistent snapshot while reading the database; during parallel dumps, workers use synchronized snapshots to view the exact same logical state. Consequently, a long dump can still represent data at a single point in time while other workloads continue running.

However, a running dump carries operational costs and interactions:

- Reads large amounts of data, consuming I/O, CPU, network, and cache.
- Holds a long-lived snapshot, which can prevent vacuum from reclaiming old row versions and increase table/index bloat.
- Acquires `ACCESS SHARE` locks on dumped tables; normal DML usually continues, whereas DDL requiring `ACCESS EXCLUSIVE` may block waiting.
- Parallel dumps open additional connections and concurrent read load.
- Sequences are a special case because sequence values do not follow MVCC transaction snapshots like ordinary table rows.

```text
                    pg_dump starts
                          |
                          v
                 Create transaction snapshot
                          |
             +------------+------------+
             |                         |
       Read table A               Read table B
       at snapshot S              at snapshot S
             |                         |
             +------------+------------+
                          |
                  Write archive / SQL
                          |
                          v
                   Dump completes

       Meanwhile:
       - INSERT/UPDATE/DELETE can still run
       - Conflicting ACCESS EXCLUSIVE DDL may wait
       - Long snapshot can retain dead tuples
```

This lesson belongs to the **Backup** chapter of the *Database Engine Relational PostgreSQL* module. It focuses on how snapshots guarantee dump consistency and the impact of a long-running dump process on workloads, vacuum, locks, replication, and operational procedures.

After this lesson, you will be able to:

1. Explain MVCC snapshots and transaction visibility.
2. Distinguish a consistent snapshot from locking the entire database.
3. Explain why `pg_dump` can run while applications continue reading and writing.
4. Distinguish `READ COMMITTED`, `REPEATABLE READ`, and `SERIALIZABLE` in multi-query export workflows.
5. Understand how `pg_dump` synchronizes snapshots when using parallel jobs.
6. Use exported snapshots to coordinate multiple dump/query sessions.
7. Identify the impact of long-held snapshots on vacuum, dead tuples, and bloat.
8. Understand `ACCESS SHARE` locks and their interaction with DDL.
9. Evaluate I/O, CPU, network, and cache load of running dumps.
10. Recognize sequences and external data not covered identically to MVCC rows.
11. Schedule, bound concurrency, monitor, and test restores for backup workflows.

> **Lab environment:** Examples use a lab database and `pg_dump`/`psql` commands. Adjust connection strings, database names, output directories, and job counts to your environment. Do not test blocking DDL, full-table read benchmarks, or long-held snapshots on production without evaluating load and maintenance windows.

---

## 1. Why Does a Dump Need a Consistent Snapshot?

### 1.1. Dumping Multiple Tables While the System Is Writing

Suppose an application manages orders and payments. One business transaction creates an order and a payment together:

```sql
BEGIN;

INSERT INTO sales.orders(order_id, customer_id, total)
VALUES (501, 12, 900000);

INSERT INTO sales.payments(payment_id, order_id, amount)
VALUES (8801, 501, 900000);

COMMIT;
```

Both changes belong to one transaction. The database guarantees they commit together or roll back together.

If a custom backup script reads `orders` first and then reads `payments` at a later moment, it can observe two inconsistent states:

1. Reads `orders` before the transaction commits: misses order 501.
2. The transaction commits.
3. Reads `payments` after commit: sees payment 8801.

The custom dump would include a payment referencing an order absent from the dump. Conversely, reading `orders` after commit and `payments` before another transaction or under different filtering can also desynchronize tables.

### 1.2. Snapshots Determine Which Transactions Are Visible

MVCC (Multi-Version Concurrency Control) lets PostgreSQL maintain multiple versions of a row. A query reads data according to snapshot and visibility rules instead of forcing all writers to halt.

A snapshot defines:

- Which transactions have already committed and are visible.
- Which transactions are still in flight and not yet visible.
- Which transactions started after the snapshot and are excluded from that visible state.

Hence, two `SELECT` statements sharing the same snapshot observe the exact same logical state of transactional data, even as other transactions keep modifying the database.

### 1.3. Timeline Example

Suppose snapshot S is taken at time T1:

```text
T0       Transaction A commits order 100
T1       pg_dump creates snapshot S
T2       Transaction B inserts order 101, uncommitted
T3       Transaction C updates order 100, commits
T4       pg_dump reads table orders
T5       Transaction B commits
T6       pg_dump reads table payments
T7       pg_dump completes
```

The dump's queries use snapshot S:

- Order 100 is seen at its committed version as of T1.
- C's update committed after T1, so the dump still sees the older version of order 100.
- B's order 101 was uncommitted at T1, so it does not appear even though B committed before the dump ended.
- Table `payments` is also read under snapshot S, so transactional rows after T1 do not appear.

As a result, the dump represents the database at logical point T1, not the latest state at T7.

### 1.4. Why Not Lock the Database to Dump?

Locking the entire database to stop all writes makes backups easy to conceptualize but disrupts applications. PostgreSQL uses MVCC so a dump can read a snapshot while DML continues.

That does not mean dumps use zero locks. `pg_dump` acquires necessary table locks to protect object structures during reads. Those locks are compatible with normal reads/writes, though they conflict with certain DDL.

---

## 2. MVCC Snapshots and Visibility

### 2.1. Every Row Has Versions

PostgreSQL stores transaction metadata on tuples to determine which row version is visible. During an `UPDATE`, PostgreSQL generally creates a new row version and marks the old version obsolete for newer snapshots.

An older snapshot may still need the old version so a query/dump returns the exact state visible when that snapshot was created.

### 2.2. A Snapshot Is Not a Physical Copy of the Database

A snapshot does not copy entire tables into memory. It is a compact structure of visibility and transaction state used by PostgreSQL when scanning row versions.

Therefore:

- A dump can scan billions of rows without holding the entire database snapshot in RAM.
- Needed older row versions must remain on disk until no active snapshot can still see them.
- The longer a snapshot persists, the more dead tuples vacuum may have to retain.

### 2.3. In-Flight Transactions When the Snapshot Starts

Transactions that started but have not committed at snapshot time are not visible as committed. Even if they commit later, the existing snapshot never shifts to include those new commits.

### 2.4. Transactions Committed After the Snapshot

A transaction that commits after a snapshot is taken does not appear in that snapshot. This is crucial for dump consistency: the dump never leaks newer commits into tables read later in the run.

### 2.5. Snapshots and Non-MVCC State

Not every piece of state in PostgreSQL follows MVCC like ordinary table rows. Examples:

- Sequence operations like `nextval()` do not roll back with transactions.
- Data in external systems outside the database is not inside PostgreSQL's snapshot.
- Files on filesystems, object storage, or message brokers are not automatically synchronized with the snapshot.
- Some configuration/cluster-level state falls outside a single-database dump.

When designing business backups, explicitly identify which state lies outside the snapshot.

---

## 3. Isolation Levels and Manual Dumps

### 3.1. `READ COMMITTED`

`READ COMMITTED` is PostgreSQL's default isolation level. Each statement starts with a fresh snapshot. Within one transaction, two `SELECT` statements can see different states if another transaction commits in between.

Example:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT COUNT(*) FROM sales.orders;

-- Another transaction can commit an INSERT here.

SELECT COUNT(*) FROM sales.payments;

COMMIT;
```

The two `SELECT` statements can use two different snapshots. Therefore, if you manually export multiple tables using separate `SELECT` statements inside a `READ COMMITTED` transaction, the result is not guaranteed to be one unified database-wide snapshot.

### 3.2. `REPEATABLE READ`

`REPEATABLE READ` uses one stable snapshot for all queries in the transaction once the snapshot is established. Transactions committed after that snapshot are invisible to subsequent queries in that transaction.

Example:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT COUNT(*) FROM sales.orders;

-- Another transaction can commit INSERT/UPDATE here.

SELECT COUNT(*) FROM sales.payments;

COMMIT;
```

Both `SELECT` statements use the same snapshot. This is typically the appropriate isolation level when building a multi-query export that must observe one consistent database state.

### 3.3. When Is the Snapshot Established?

In `REPEATABLE READ`, the snapshot is established when the transaction executes its first statement requiring a snapshot, not necessarily at the `BEGIN` command itself. Thereafter, the snapshot stays fixed for the transaction.

If multiple sessions must coordinate, explicitly establish the snapshot in the source transaction and export it to other sessions.

### 3.4. `SERIALIZABLE`

`SERIALIZABLE` adds checks ensuring concurrent transactions behave consistently with some valid serial execution order. It may abort transactions upon detecting a serialization anomaly.

For read-only dumps, PostgreSQL provides `SERIALIZABLE READ ONLY DEFERRABLE`. The transaction waits for a safe snapshot before reading, avoiding certain snapshot-related serialization anomalies.

`pg_dump --serializable-deferrable` requests this mode. It may wait before the dump begins and is not a necessary default for every backup.

### 3.5. Comparison Table

| Isolation | Snapshot Across Multiple SELECTs | Sees New Commits Between SELECTs? | Suitable for Custom Multi-Table Exports |
|---|---|---|---|
| READ COMMITTED | Each statement gets its own snapshot | Yes | No if one shared state is required |
| REPEATABLE READ | Stable snapshot across transaction | No | Yes, typically the right choice |
| SERIALIZABLE | Stable snapshot plus serialization checks | No; may wait/abort under conditions | Use when specific serializable semantics are needed |

### 3.6. Manual Export Using the Same Snapshot

Example:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

COPY (
    SELECT order_id, customer_id, total
    FROM sales.orders
    ORDER BY order_id
) TO STDOUT WITH (FORMAT csv, HEADER true);

COPY (
    SELECT payment_id, order_id, amount
    FROM sales.payments
    ORDER BY payment_id
) TO STDOUT WITH (FORMAT csv, HEADER true);

COMMIT;
```

This snippet illustrates sharing one transaction/snapshot across multiple `COPY TO STDOUT` statements. The client must route the two output streams to separate files and handle errors and transaction completion properly.

If each `COPY` runs in a separate autocommit connection, there is no guarantee they share a snapshot.

---

## 4. How Does `pg_dump` Create a Snapshot?

### 4.1. One Database, One Logical Snapshot

`pg_dump` is a logical backup tool for a single database. It connects to the server, starts a read transaction, and acquires a snapshot so all dump reads reflect one consistent state.

While the dump runs, applications can continue to:

- `INSERT` new rows.
- `UPDATE` or `DELETE` existing rows.
- `SELECT` data.
- Commit normal transactions.

Changes committed after the snapshot do not appear in that dump. This is desirable: the dump represents one logical point in time rather than a moving dataset drifting as each table is read.

### 4.2. `pg_dump` Does Not Lock the Entire Database

`pg_dump` uses MVCC to read data. It acquires `ACCESS SHARE` locks on the tables to be dumped to prevent operations needing conflicting locks from altering relation structure mid-read.

`ACCESS SHARE` is compatible with ordinary table locks from `SELECT`, `INSERT`, `UPDATE`, and `DELETE`. Applications therefore generally continue operating during a dump.

### 4.3. A Snapshot Does Not Mean a Dump Cannot Fail

A dump can still fail if:

- Permissions are insufficient to read an object.
- The connection drops or the server restarts.
- Storage/network fills up or the client cannot write files.
- DDL conflicts with the dump's locks.
- An object changes in a way that prevents consistent continuation.
- The client is killed or times out.

A large output file does not automatically prove the dump completed. Treat an artifact as a successful backup only when `pg_dump` exits cleanly and verification/restore checks pass.

### 4.4. `pg_dump` and Uncommitted Transactions

Rows written by transactions uncommitted at snapshot time are not dumped as committed data. Even if those transactions commit after the snapshot starts, the dump still does not see their rows.

Rows deleted or updated after the snapshot still appear at the versions visible to the earlier snapshot.

### 4.5. `pg_dump` Is a Per-Database Backup

`pg_dump` dumps one database. It does not take a simultaneous snapshot across all databases in a cluster, nor does it replace cluster-wide backups.

Global objects like roles and tablespaces are handled by `pg_dumpall` or separate workflows. `pg_dumpall` dumps multiple databases over separate connections/transactions; do not treat a full cluster dump as a single global atomic snapshot across all databases.

### 4.6. Scope Excluded from the Snapshot

A logical dump does not automatically include:

- Full WAL history required for point-in-time recovery.
- External files referenced by applications.
- State of message brokers, object storage, or external services.
- Server/OS configurations, secrets, and infrastructure.
- A synchronized cluster-wide snapshot across all databases.

Combine logical dumps with physical backups/WAL archiving or external system backups whenever RPO/RTO requires them.

---

## 5. Parallel Dump and Synchronized Snapshots

### 5.1. Why Does a Parallel Dump Need a Shared Snapshot?

Dumping a large database can take hours when reading tables sequentially. `pg_dump -j N` lets multiple workers read chunks of data concurrently.

If each worker acquired its own independent snapshot, worker A might see a committed transaction that worker B does not see. The resulting dump would fail to represent a single database state.

PostgreSQL solves this with **synchronized snapshots**: the leader establishes a snapshot and workers import that exact snapshot before reading data.

### 5.2. Parallel Dump Command Example

```bash
pg_dump \
  --format=directory \
  --jobs=4 \
  --file=/backup/appdb.dumpdir \
  --dbname=appdb
```

Directory format (`-Fd`) supports parallel dumps. `--jobs=4` runs up to four concurrent reader workers; actual connection count also depends on the leader process and dump activity.

### 5.3. Formats and Parallel Dump

| Format | Flag | Parallel Dump with `pg_dump`? | Characteristics |
|---|---|---|---|
| Plain SQL | `-Fp` | No | Readable single SQL script |
| Custom | `-Fc` | No for parallel dump | Flexible archive, selective restore, supports parallel restore |
| Directory | `-Fd` | Yes | Directory with metadata and data files, supports parallel dump/restore |
| Tar | `-Ft` | No | Tar archive, more limited object selection than custom |

If parallel dump is needed, pick directory format. Custom format remains valuable when you want a single archive file with parallel restore.

### 5.4. Workers Share the Same Snapshot

During a parallel dump:

1. The leader connects to the database and establishes a transaction/snapshot.
2. The leader acquires required locks on objects to be dumped.
3. Workers open separate connections and import the synchronized snapshot.
4. Each worker reads a portion of data under identical visibility rules.
5. The leader coordinates metadata and waits for workers to finish.
6. Snapshot/locks are released once the dump completes.

As a result, data across different tables remains consistent to the same logical point even though workers run at different wall-clock times.

### 5.5. More Jobs Do Not Make a Dump "Newer"

Parallelism changes only work distribution and completion time. The snapshot is still established at the beginning; workers finishing later never see newer commits.

### 5.6. Impact of Job Count

Increasing `--jobs` can:

- Shorten dump time if storage/network have spare throughput.
- Increase concurrent table scans and random/sequential I/O.
- Increase CPU usage for reading, encoding, compression, and networking.
- Increase connections and memory on server/client.
- Cause heavier cache churn.
- Increase contention with OLTP workloads.

Do not blindly set jobs equal to CPU count. The bottleneck may be storage bandwidth, network, IOPS, lock waits, or compression CPU.

### 5.7. Parallel Dumps and Old Snapshots

A worker reading a massive table for many minutes still holds the dump's snapshot. Workers never advance to a newer snapshot as other tables finish.

This guarantees consistency while extending snapshot lifetime if one huge object slows down the entire dump.

### 5.8. If a Worker Fails

A parallel dump must not be treated as complete if any worker fails. `pg_dump` reports an error and exits non-zero. Treat an incomplete directory archive as invalid; clean up staging per procedure and rerun.

### 5.9. Do Not Disable Synchronized Snapshots for Speed

Do not trade away snapshot consistency by letting workers read separate snapshots unless you explicitly accept inconsistent semantics and have evaluated the consequences. For database recovery backups, consistency usually outweighs saving a small amount of time.

---

## 6. Exported Snapshots and Coordinating Multiple Sessions

### 6.1. When Is an Exported Snapshot Needed?

A workflow may require:

- One `pg_dump` for schema/data.
- A separate export query for audit tables.
- A process generating manifests/counts.
- Multiple `pg_dump` runs in separate processes that must see the exact same data state.

If each process opens an independent transaction, they can capture different snapshots. PostgreSQL allows one transaction to export a snapshot identifier so another transaction can import that snapshot.

### 6.2. `pg_export_snapshot()`

Open a `REPEATABLE READ` transaction:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT pg_export_snapshot();
```

PostgreSQL returns a snapshot identifier token. This token can only be used to import the snapshot while the exporting transaction remains open.

### 6.3. Importing a Snapshot with `SET TRANSACTION SNAPSHOT`

In another session, before querying any data in the transaction:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SET TRANSACTION SNAPSHOT '00000003-0000001B-1';

SELECT COUNT(*) FROM sales.orders;

COMMIT;
```

The string in the example is a placeholder; replace it with the identifier returned by `pg_export_snapshot()`. `SET TRANSACTION SNAPSHOT` must be called at the right point in the transaction with a compatible isolation level.

### 6.4. Lifetime of a Snapshot Token

The exporting transaction must stay open until all consumer transactions have imported the snapshot. If the exporting transaction ends before a consumer imports, the token becomes invalid.

Once a consumer has imported the snapshot, that consumer can continue using it within its own transaction per PostgreSQL rules.

### 6.5. Using `--snapshot` with `pg_dump`

`pg_dump` supports the `--snapshot` option to adopt a snapshot exported by another session:

```bash
pg_dump \
  --snapshot='00000003-0000001B-1' \
  --format=custom \
  --file=appdb.dump \
  --dbname=appdb
```

This is an illustrative example. The session holding the exported snapshot must remain open until `pg_dump` has imported it. When coordinating multiple processes, manage the lifecycle of the snapshot transaction and all consumers explicitly.

### 6.6. Coordination Sequence

```text
Session A (coordinator)
    BEGIN REPEATABLE READ READ ONLY
    pg_export_snapshot() -> SNAPSHOT_ID
    keep transaction open
              |
              +----------------------+
              |                      |
              v                      v
        pg_dump process 1       query/export process 2
        import SNAPSHOT_ID      SET TRANSACTION SNAPSHOT
        dump tables A/B         export report C
              |                      |
              +----------+-----------+
                         |
              all consumers have imported
                         |
                         v
             Session A COMMIT/ROLLBACK
```

### 6.7. Limitations

- A snapshot token is not a backup file; it only identifies visibility state.
- Consumers must connect to the matching database using compatible transaction semantics.
- Tokens do not persist forever.
- Long-running transactions holding snapshots can affect vacuum.
- Snapshots do not synchronize sequence state, external services, or other databases.

---

## 7. Sequences Are a Special Case

### 7.1. Sequences Are Not Transactional Like Table Rows

`nextval()` and `setval()` do not follow ordinary rollback semantics. If a transaction calls `nextval` and then rolls back, the sequence increment remains.

Sequences are designed to issue unique/monotonic values efficiently, not to act as gapless transactional counters.

### 7.2. Snapshots Do Not Freeze Sequences

`pg_dump`'s MVCC snapshot ensures consistent visibility for table rows, but sequence state is not frozen like ordinary row versions. Another session can call `nextval` while the dump is scanning data.

Therefore, do not interpret "dump consistent as of start time" as "every sequence value matches that exact instant."

### 7.3. Implications Upon Restore

`pg_dump` saves the sequence state needed to restore sequences. Because sequences can advance concurrently during a dump, the dumped sequence value may not align strictly with the rows visible in the snapshot.

After restoring, check sequence state and next-ID generation, especially when the system experienced continuous writes during the backup.

### 7.4. Inspecting Sequences

List sequences in a schema:

```sql
SELECT
    schemaname,
    sequencename,
    last_value
FROM pg_sequences
WHERE schemaname = 'sales'
ORDER BY sequencename;
```

`pg_sequences` columns vary by version; `last_value` can be `NULL` if the role lacks read privileges on the sequence or if the sequence has not been used yet in the relevant state. Check docs for your version.

### 7.5. Sequence Cache and Gaps

Sequences can cache values per backend. After a crash or session end, gaps can appear. This is normal behavior, not evidence that a dump lost rows.

---

## 8. `pg_dump` Locks and Interaction with DML/DDL

### 8.1. `ACCESS SHARE`

`pg_dump` acquires `ACCESS SHARE` locks on the tables it reads. This is the lightest table-level lock mode in PostgreSQL.

`ACCESS SHARE` is compatible with ordinary read/write operations:

- `SELECT`.
- `INSERT`.
- `UPDATE`.
- `DELETE`.
- `MERGE` per the statement's lock behavior.

Dumps therefore normally do not block applications from writing data.

### 8.2. Which Locks Conflict?

`ACCESS SHARE` conflicts with `ACCESS EXCLUSIVE`. Common operations requiring this strong lock include:

- `DROP TABLE`.
- `TRUNCATE`.
- `VACUUM FULL`.
- Many forms of `ALTER TABLE` modifying structure.
- Certain table maintenance/relation rewrite operations.

Not every `ALTER TABLE` takes the same lock mode; lock levels depend on the subcommand and PostgreSQL version.

### 8.3. DDL Running Before the Dump

If DDL already holds an `ACCESS EXCLUSIVE` lock when `pg_dump` needs `ACCESS SHARE`, `pg_dump` must wait. Long-running DDL or open transactions can delay when the dump begins reading.

### 8.4. DDL Starting After the Dump

If `pg_dump` already holds an `ACCESS SHARE` lock, DDL needing `ACCESS EXCLUSIVE` must wait until the dump releases its lock. A `DROP TABLE` or `ALTER TABLE` can sit waiting for the duration of the dump's lock hold.

### 8.5. Lock Queues and Cascading Impact

DDL waiting for `ACCESS EXCLUSIVE` can trigger lock queuing effects. Subsequent requests needing locks compatible with the dump—yet queued behind the waiting DDL—can also stall depending on lock queue behavior.

Thus, even though `ACCESS SHARE` is compatible with DML, a queued DDL statement can introduce unexpected latency for workloads.

### 8.6. Inspecting Locks

```sql
SELECT
    a.pid,
    a.application_name,
    a.state,
    a.xact_start,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation,
    a.wait_event_type,
    a.wait_event,
    left(a.query, 140) AS query_sample
FROM pg_locks AS l
JOIN pg_stat_activity AS a
  ON a.pid = l.pid
WHERE l.relation IS NOT NULL
ORDER BY l.granted, a.xact_start;
```

This query inspects table locks and associated sessions. It is not a full report of every lock dependency; when investigating blocking, examine blockers/waiters and the broader lock graph.

### 8.7. Inspecting Blockers

```sql
SELECT
    waiting.pid AS waiting_pid,
    waiting.application_name AS waiting_app,
    waiting.wait_event_type,
    waiting.wait_event,
    blocker.pid AS blocker_pid,
    blocker.application_name AS blocker_app,
    blocker.state AS blocker_state,
    blocker.xact_start AS blocker_xact_start,
    left(blocker.query, 160) AS blocker_query
FROM pg_stat_activity AS waiting
CROSS JOIN LATERAL unnest(pg_blocking_pids(waiting.pid)) AS b(pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = b.pid
ORDER BY waiting.pid;
```

`pg_blocking_pids()` lists backends blocking a given PID. Appropriate monitoring privileges are needed to see full details of other sessions.

### 8.8. Limiting Lock Wait Time

`pg_dump` provides the option:

```bash
pg_dump \
  --lock-wait-timeout=30s \
  --format=custom \
  --file=appdb.dump \
  --dbname=appdb
```

If required locks cannot be acquired within the timeout, the dump fails instead of waiting indefinitely. Choose a timeout aligned with maintenance windows and SLAs; too short a timeout can cause frequent backup failures during legitimate DDL.

### 8.9. Dumps Are Not Schema Migration Coordinators

Before running heavy DDL migrations, check for running backups and lock interactions. Likewise, during long backups, avoid running DDL needing `ACCESS EXCLUSIVE` unless waiting/rescheduling is planned.

---

## 9. How Do Long Snapshots Affect Vacuum and Bloat?

### 9.1. Dead Tuples

`UPDATE`/`DELETE` in PostgreSQL creates or leaves behind old row versions. Once no snapshot can still see them, `VACUUM` can mark that space reusable.

If a transaction holds an old snapshot, PostgreSQL must retain tuple versions that the snapshot might still need.

### 9.2. `pg_dump` Holds Snapshots for Extended Periods

Dumping a large database can take minutes to hours. During that interval:

- Applications keep executing `UPDATE`/`DELETE`.
- Old row versions accumulate.
- Autovacuum can still run, but cannot remove dead tuples still needed by the snapshot.
- Tables/indexes can grow, with freed space unable to be reclaimed yet.

This is one of the most important operational impacts of a running dump.

### 9.3. Bloat Does Not Immediately Inflate the Dump File

A running dump does not usually enlarge the archive file because of dead tuples. The impact hits the source database: vacuum cannot reclaim old versions yet, allowing relations to grow while writes continue.

### 9.4. Vacuum Still Runs, But Is Constrained

Do not say "`pg_dump` locks vacuum." Autovacuum can continue scanning and doing much of its work; the main constraint is being unable to prune tuple versions still visible to the older snapshot.

### 9.5. Observing Transaction Age and `backend_xmin`

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    backend_xmin,
    age(backend_xmin) AS xmin_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE backend_xmin IS NOT NULL
ORDER BY xact_start NULLS LAST;
```

`backend_xmin` shows the xmin horizon held by a backend's snapshot. A backend holding an old xmin for a long time can block vacuum from cleaning up certain dead tuples.

### 9.6. Finding Tables with Many Dead Tuples

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
ORDER BY n_dead_tup DESC
LIMIT 20;
```

`n_dead_tup` is a statistical estimate, not an exact tuple-by-tuple count at query time.

### 9.7. Checking Database Age

```sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age,
    datfrozenxid
FROM pg_database
ORDER BY xid_age DESC;
```

Extremely long snapshots, long open transactions, and high transaction-rate workloads can hinder the freeze horizon from advancing. Over prolonged durations, this adds to transaction ID wraparound pressure; monitor XID age and autovacuum/freeze progress.

### 9.8. Do Not Jump to Conclusions from `n_dead_tup` Alone

A high dead tuple estimate alone does not prove `pg_dump` is the cause. Cross-check:

- Transaction/snapshot duration.
- `backend_xmin`.
- `UPDATE`/`DELETE` rate.
- Autovacuum progress and logs.
- Table/index growth.
- Replication feedback/slots.

### 9.9. Do Not Kill a Snapshot Hastily

Terminating a session holding a snapshot lets vacuum clean up tuple versions later, but will abort the dump or leave it incomplete. Before canceling, assess:

- How long the dump has run and how much work remains.
- Whether partial files/archives need deletion or retention for investigation.
- Whether the dump can finish within the maintenance window.
- Whether backups must be re-run and restore-tested.

---

## 10. Dump from Primary or Standby?

### 10.1. Dumping from the Primary

Advantages:

- Free from hot standby recovery conflicts.
- Directly sees the current primary state.
- Easier coordination with snapshot workflows and read privileges.

Trade-offs:

- Read load competes with primary read/write workloads.
- Long snapshots affect the primary's vacuum horizon.
- Dumps can increase cache churn and storage I/O.

### 10.2. Dumping from a Hot Standby

Can offload read traffic to a standby, reducing direct I/O on the primary. However, the standby is replaying WAL and can hit **recovery conflicts** with long queries.

### 10.3. Recovery Conflicts

A long query on a standby may need row versions or relation states that WAL recovery needs to remove/alter. PostgreSQL may pause recovery briefly or cancel the query to let recovery proceed according to standby delay settings.

A dump canceled mid-run does not produce a valid backup.

### 10.4. `hot_standby_feedback`

`hot_standby_feedback` sends the standby's xmin back to the primary so the primary avoids vacuuming row versions still needed by queries on the standby.

Trade-offs:

- Reduces certain recovery conflicts/query cancellations on the standby.
- Can retain dead tuples on the primary longer and increase bloat.
- Not free; monitor vacuum and storage closely.

### 10.5. Replication Lag

A heavy dump on a standby consumes I/O/CPU and can slow WAL replay. If the standby lags, queries reading from it reflect an older state than the primary.

If you need a snapshot synchronized with a primary business boundary, explicitly check LSN/timeline and topology; never assume a standby dump always equals the primary's latest state.

### 10.6. Choosing the Dump Source

| Condition | Primary | Standby |
|---|---|---|
| Want to offload primary reads | Not ideal | May be suitable |
| Very long dump queries | Holds xmin on primary | Risks recovery conflicts; feedback can bloat primary |
| Need latest primary data | Direct | May lag |
| Frequent DDL | DDL may wait on dump lock | DDL/WAL replay may cause conflicts |
| Standby lacks I/O headroom | Unaffected by standby read load | Dump can increase replay lag |

Choose based on primary SLAs, replication lag, storage capacity, and backup requirements.

---

## 11. Resource Impact of a Running Dump

### 11.1. Disk I/O

A dump reads all or most table data, TOAST values, and metadata. It can generate heavy read I/O, especially when the database exceeds RAM or OLTP workloads share the same storage.

### 11.2. CPU

CPU is consumed for:

- Reading and decoding tuples.
- Formatting data into the output format.
- Compressing archives.
- Transport encryption when using SSL.
- Coordinating parallel workers.

Compression reduces bytes written/sent over the network at the expense of CPU. Higher compression levels are not always faster overall.

### 11.3. Network

When the client runs on a separate host, data travels over the network. Network throughput, packet loss, and client bandwidth can become bottlenecks.

### 11.4. Client Disk

`pg_dump` writes the archive or SQL file on the client side. If the filesystem fills up, permissions are wrong, or a mount drops, the dump fails even if server queries are reading fine.

### 11.5. Memory and Cache

A dump does not load the entire database into memory, but multiple parallel scans can shift the cache working set and evict hot application pages from OS/shared buffers.

### 11.6. Increasing `--jobs` Is Not Always Faster

If storage is already saturated, adding workers just increases queueing and contention. If network or client disk is slow, more workers will not solve the bottleneck.

### 11.7. Archive Compression

Archive formats can compress data. Consider:

- Client/server CPU depending on implementation and version.
- Archive size.
- Transfer duration.
- Restore/decompression duration.
- Free space for staging and final artifacts.

### 11.8. Resource Isolation

If dumps regularly degrade OLTP, consider:

- Scheduling during low-traffic windows.
- Dumping from a suitably provisioned standby.
- Capping `--jobs`.
- Applying CPU/IO limits at container/OS/cloud layers if available.
- Using dedicated backup infrastructure.
- Monitoring application latency and aborting/throttling at agreed thresholds.

Do not hardcode one job count for every database and every hour of the day.

---

## 12. Common `pg_dump` Commands

### 12.1. Plain SQL Format

```bash
pg_dump \
  --format=plain \
  --file=appdb.sql \
  --dbname=appdb
```

Plain format creates a readable SQL script loaded with `psql`. It is handy for inspection and controlled editing, but lacks selective/parallel restore features of archive formats.

### 12.2. Custom Format

```bash
pg_dump \
  --format=custom \
  --file=appdb.dump \
  --dbname=appdb
```

Custom archives are ideal for single-file storage, inspecting object lists, and selective restoration via `pg_restore`. It supports parallel restore.

### 12.3. Directory Format and Parallel Dump

```bash
pg_dump \
  --format=directory \
  --jobs=4 \
  --file=appdb.dumpdir \
  --dbname=appdb
```

Directory format writes dump parts into multiple files inside a folder and supports parallel dump. Use a fresh staging directory with adequate capacity; mark the backup complete only once `pg_dump` exits cleanly.

### 12.4. Dumping Schema or Data Separately

```bash
pg_dump --schema-only --file=schema.sql --dbname=appdb
pg_dump --data-only --file=data.sql --dbname=appdb
```

Two separate runs capture two different snapshots. If schema and data must match the exact same logical point, do not assume two separate dumps combine into one consistent backup. Use one full archive or coordinate snapshots explicitly.

### 12.5. Dumping a Single Schema

```bash
pg_dump --schema=sales --format=custom --file=sales.dump --dbname=appdb
```

Dumping one schema still requires snapshots and locks on scoped objects. Foreign keys or dependencies referencing other schemas must be accounted for on restore.

### 12.6. Dumping Selected Tables

```bash
pg_dump \
  --table=sales.orders \
  --table=sales.payments \
  --format=custom \
  --file=sales-tables.dump \
  --dbname=appdb
```

A partial-object archive can miss dependencies. Verify needed extensions, types, functions, sequences, schemas, and referenced tables before relying on it as a standalone recovery artifact.

### 12.7. Writing to Staging Paths

```bash
pg_dump --format=custom --file=appdb.dump.part --dbname=appdb

# Run publish step only when pg_dump exit code = 0:
mv appdb.dump.part appdb.dump
```

For directory format, dump into a fresh staging directory, verify success, and then rename the whole directory. Rename atomicity depends on filesystem and source/destination locations.

### 12.8. Lock Wait Timeout

```bash
pg_dump \
  --lock-wait-timeout=30s \
  --format=custom \
  --file=appdb.dump \
  --dbname=appdb
```

This option bounds how long `pg_dump` waits for shared locks at the start of the dump. Check `pg_dump` version since option support depends on version.

### 12.9. Serializable Deferrable

```bash
pg_dump \
  --serializable-deferrable \
  --format=custom \
  --file=appdb.dump \
  --dbname=appdb
```

This option requests a serializable, read-only, deferrable transaction and may wait for a safe snapshot. It serves specific consistency semantics, not dump acceleration.

### 12.10. Checking Client/Server Versions

```bash
pg_dump --version
psql --version
```

`pg_dump` cannot dump from a server major version newer than `pg_dump`'s own major version. In practice, use compatible, supported client tools for the running server. Archives created by `pg_dump` generally target restoring to the same or newer PostgreSQL versions; do not assume backward compatibility to older servers.

---

## 13. A Consistent Snapshot Does Not Mean System-Wide Consistency

### 13.1. Single Database

`pg_dump` guarantees a consistent snapshot within the scope of one database per transaction snapshot and dumped objects.

### 13.2. Multiple Databases

If an application uses:

- `appdb` storing orders.
- `billingdb` storing invoices.
- `identitydb` storing users.

three independent `pg_dump` runs can capture three snapshots at three different timestamps. PostgreSQL does not provide one unified MVCC snapshot spanning multiple databases in a cluster simply by running `pg_dumpall`.

If a business operation updates multiple databases, design backup/restore coordination at the application or infrastructure layer—such as maintenance/quiesce windows, application event boundaries, coordinated backups, or reconcilable sources of truth.

### 13.3. Global Objects

Roles, tablespaces, and certain cluster-level objects do not belong to a single database. `pg_dumpall` can export them alongside database contents, but does not turn multiple databases into one simultaneous snapshot.

### 13.4. External Systems

If a PostgreSQL transaction writes to the database and then emits a Kafka message or updates object storage, PostgreSQL's snapshot does not automatically capture that message/object. Use outbox patterns, event offsets, manifests, or explicit coordination to establish a verifiable recovery boundary.

### 13.5. Foreign Data

Foreign tables and FDWs access external data sources. A local PostgreSQL snapshot does not guarantee the remote source shares the same snapshot or timestamp. Clarify what data is actually dumped and the semantics of your FDW/foreign server.

### 13.6. Sequences and Non-Transactional State

Sequence state is a notable exception as covered earlier. Non-MVCC state must be evaluated separately if an exact business cut is required.

---

## 14. Monitoring `pg_dump` While Running

### 14.1. Setting `application_name`

Assign an identifiable name to backup connections via connection service/URI or `libpq` configuration:

```text
application_name=nightly_pg_dump
```

This lets you filter sessions in `pg_stat_activity` by name. Exact parameter syntax depends on connection strings/service files and environment.

### 14.2. Viewing Dump Sessions

```sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    xact_start,
    now() - xact_start AS xact_age,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 180) AS query_sample
FROM pg_stat_activity
WHERE application_name ILIKE '%dump%'
   OR query ILIKE 'COPY %'
ORDER BY xact_start NULLS LAST;
```

`pg_dump` commonly reads data via `SELECT` statements (or `COPY` depending on object), so filtering solely for queries starting with `COPY` can miss sessions. An explicit `application_name` makes identification much easier.

### 14.3. No General `pg_stat_progress_pg_dump` View

PostgreSQL does not provide a dedicated overall progress view for logical `pg_dump` analogous to `pg_stat_progress_vacuum`. Progress views for `COPY` or base backups are not trackers for `pg_dump` `SELECT` scans.

Monitor via:

- `pg_dump` verbose output.
- Client PID/process and elapsed time.
- Growing output file/archive size.
- `pg_stat_activity`, locks, and wait events.
- I/O, CPU, network, and filesystem metrics.

A growing file indicates the process is writing data, not proof the dump will complete cleanly.

### 14.4. Monitoring Blocking

```sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    now() - xact_start AS xact_age,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE wait_event_type = 'Lock'
ORDER BY query_start;
```

If `pg_dump` is waiting on a lock, identify blockers via `pg_blocking_pids()` and inspect the DDL/transaction holding the lock. Never terminate a session solely due to high query age; determine ownership and business impact first.

### 14.5. Monitoring Vacuum and Dead Tuples

Combine:

```sql
SELECT
    pid,
    datname,
    relid::regclass AS relation,
    phase,
    heap_blks_scanned,
    heap_blks_vacuumed,
    index_vacuum_count
FROM pg_stat_progress_vacuum;

SELECT
    schemaname,
    relname,
    n_dead_tup,
    last_autovacuum,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;
```

An old snapshot can stop vacuum from removing certain dead tuples. The progress view shows what vacuum is doing; table stats show dead tuple estimates.

### 14.6. Monitoring Replication

If dumping from a standby:

```sql
SELECT
    application_name,
    state,
    sync_state,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
```

Watch `replay_lag` throughout the backup to see whether dump load is causing the standby to fall behind.

### 14.7. Monitoring WAL Retention Separately

A logical `pg_dump` snapshot on the primary does not automatically retain all WAL segments for the duration of the dump. WAL retention typically depends on archiving backlogs, replication slots, and standby requirements.

If replication slots exist:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status,
    safe_wal_size
FROM pg_replication_slots;
```

Columns vary by major version. Inactive slots or slow consumers can pin WAL and grow the WAL filesystem; investigate independently of `pg_dump` snapshots.

---

## 15. Scheduling and Organizing Production Dumps

### 15.1. Choosing Backup Windows

Prefer windows where:

- Write workload is lower.
- Storage has spare read bandwidth.
- Heavy migrations/DDL do not overlap.
- Archive and staging disk space are sufficient.
- Operators/automation can monitor and handle failures.

Do not assume overnight is always quiet; batch/reporting jobs can create concurrent spikes.

### 15.2. Bounding Parallel Jobs

Start with a low job count, measure impact, and scale up carefully. Track:

- Dump duration.
- Application commit latency.
- Storage read/write latency.
- CPU and network throughput.
- Vacuum lag/dead tuples.
- Replication lag.

The goal is meeting the backup window without breaching primary workload SLAs.

### 15.3. Avoid Overlapping Multiple Large Dumps

Two concurrent dumps can scan the same tables, multiply I/O, and hold multiple long snapshots. When backing up multiple databases, stagger schedules and concurrency within capacity.

### 15.4. Snapshot Hold Duration

The longer the dump runs, the longer the snapshot persists. You can shorten duration by:

- Optimizing storage/network.
- Choosing an appropriate job count.
- Avoiding heavy compression if CPU-bottlenecked.
- Excluding genuinely unnecessary objects.
- Using dedicated backup infrastructure for very large databases.

Do not split one database into multiple independent dumps merely to shorten each run if consistency across all parts under one snapshot is required.

### 15.5. Checking Disk Space

Account for:

- Archives being written.
- `.part` files or staging directories.
- Completed backups retained locally.
- Temporary files.
- Headroom for test restores.

Directory format writes multiple files; custom/plain can produce one huge file. Running out of disk mid-run yields an incomplete backup.

### 15.6. Timeouts and Cancellation

Set sensible timeouts for lock acquisition, client connections, and orchestration. Too short a query timeout cancels large dumps; too long a timeout holds snapshots and locks for hours when systems are unhealthy.

### 15.7. Recording Manifests

A sidecar manifest should record:

- Database and server identity.
- PostgreSQL server/client versions.
- Start/end timestamps.
- Dump format and key options.
- Snapshot identifier if coordinated.
- File list, sizes, checksums.
- Exit status.
- Backup retention class.

Never store passwords/secrets inside manifests or command lines exposed via process listings/logs.

---

## 16. Handling Failed or Canceled Dumps

### 16.1. Exit Code

Backup automation must check `pg_dump`'s exit code. If the process is killed, the connection resets, or the server throws an error, the output file may already hold partial data.

### 16.2. Never Publish Incomplete Artifacts

Write to a staging path. Rename/publish only after:

1. `pg_dump` exits with code 0.
2. File/archive metadata is readable.
3. Checksums are computed.
4. The manifest records a success status.

### 16.3. Custom Archive Inspection

```bash
pg_restore --list appdb.dump
```

This lists the archive's table of contents. It checks that archive metadata is readable; **it does not replace a restore test**.

### 16.4. Directory Archive Inspection

```bash
pg_restore --list appdb.dumpdir
```

If a directory dump is incomplete or missing files, inspection/restoration may report errors.

### 16.5. When Canceling a Running Dump

Before canceling:

- Check the backup window and the dump's impact level.
- Check whether the dump is blocking DDL or merely reading.
- Check vacuum/bloat and application latency.
- Consider lowering jobs or deferring DDL if feasible.
- If stopping is required, send a controlled termination signal and confirm the client process exited.
- Clean up incomplete staging artifacts per retention/incident procedures.

Never delete the last known-good backup before verifying a replacement exists.

### 16.6. Retries

After a failure, normally run a fresh dump with a new snapshot. Do not stitch data files from separate dump runs together unless supported by explicit snapshot coordination and archive semantics.

---

## 17. Test Restores Are the Real Proof a Backup Works

### 17.1. Checking Archives

```bash
pg_restore --list appdb.dump
```

Inspect the TOC and file checksums. An archive with a readable TOC can still lack object data or fail restore due to version/extension/privilege dependencies.

### 17.2. Restoring Custom Archives into a Test Database

```bash
createdb appdb_restore

pg_restore \
  --exit-on-error \
  --dbname=appdb_restore \
  appdb.dump
```

For large archives, use `--jobs` for parallel restore if format and server resources permit.

### 17.3. Parallel Restore of a Directory Archive

```bash
createdb appdb_restore

pg_restore \
  --jobs=4 \
  --exit-on-error \
  --dbname=appdb_restore \
  appdb.dumpdir
```

Parallel restore increases CPU/I/O load on the target. Do not run it on production targets without evaluation.

### 17.4. Restoring Plain SQL

```bash
createdb appdb_restore

psql \
  -X \
  -v ON_ERROR_STOP=1 \
  --dbname=appdb_restore \
  --file=appdb.sql
```

### 17.5. Verifying Data

After restoring, check:

- Database and schemas exist.
- Tables, views, functions, types, and extensions are created.
- Constraints and indexes are valid.
- Row counts or key business invariants match.
- Sequence state and ID generation behave properly.
- Owners, grants, and default privileges match.
- Large objects if used by the application.
- Application smoke tests pass.

Do not compare only total row counts; two databases with identical row counts can still have differing data.

### 17.6. Restore Version Compatibility

Verify the target server has required extensions, locale/collation, and privileges. Logical dumps do not carry all OS/cluster dependencies. Restoring onto a newer major version is the standard supported upgrade path, yet extension and SQL object compatibility must still be tested.

### 17.7. Measuring RTO

Record durations for:

- Preparing the target.
- Restoring schemas/data.
- Building indexes/constraints.
- Running `ANALYZE` statistics.
- Smoke testing.
- Cutover.

A backup created quickly that restores too slowly may still miss RTO.

---

## 18. `pg_dump`, Physical Backups, and Point-in-Time Recovery

### 18.1. Logical Dumps

`pg_dump` creates a logical representation of one database: schemas and data as SQL or archives. Useful for:

- Database migrations.
- Selective object restores.
- Major version upgrades.
- Backing up a single database/schema.
- Inspecting and archiving logical data.

### 18.2. Physical Backups

Physical backups copy the data directory at the physical level via PostgreSQL workflows such as `pg_basebackup` or a compatible backup solution. They are commonly paired with WAL archiving to restore clusters to a desired point in time.

### 18.3. Logical Snapshots Are Not PITR

`pg_dump` reflects one logical state at the dump's snapshot. It does not provide continuous WAL history to replay to an arbitrary timestamp.

If point-in-time recovery is needed, you need a valid base backup, a continuous WAL archive, and a tested recovery target procedure.

### 18.4. Combining Backups

A strategy can combine:

- Physical base backups and WAL archiving for disaster recovery/PITR.
- Periodic `pg_dump` for logical restores, migrations, and object-level recovery.
- Separate backups for roles/global objects when needed.
- Backups/manifests for external systems.
- Independent restore drills and retention.

Never rely on one backup mechanism to satisfy every requirement.

---

## 19. Common Misconceptions

**1. "`pg_dump` locks the entire database."** No. It uses an MVCC snapshot and appropriate table locks; normal DML continues running.

**2. "Because DML keeps running, dumps use no locks."** False. `pg_dump` acquires `ACCESS SHARE` locks; they are compatible with DML but conflict with `ACCESS EXCLUSIVE`.

**3. "Each table is dumped at the time that table is read."** No. Queries share one snapshot, reflecting a single logical state.

**4. "Transactions committed during a dump appear in tables read later."** Not if committed after the snapshot; the dump continues seeing the older state.

**5. "`READ COMMITTED` is enough for multiple `SELECT`s in one transaction."** Not if one shared snapshot is needed; each statement can get a new snapshot.

**6. "`REPEATABLE READ` locks out writers."** No. It holds a stable snapshot; DML continues via MVCC.

**7. "In parallel dumps, each worker sees its own snapshot."** No. `pg_dump` synchronizes the snapshot across workers.

**8. "Increasing jobs always makes dumps faster."** No. Storage/network/CPU can saturate and OLTP workloads suffer contention.

**9. "Long dumps do not affect vacuum."** False. Old snapshots can block vacuum from removing still-needed dead tuples.

**10. "`pg_dump` locks vacuum."** No. Vacuum still runs, though it is constrained from cleaning up certain tuple versions.

**11. "High dead tuples must be caused by `pg_dump`."** Not necessarily. Check transaction age, `backend_xmin`, write rate, and autovacuum.

**12. "`ACCESS SHARE` blocks `INSERT`/`UPDATE`/`DELETE`."** No. It is compatible with ordinary DML locks.

**13. "`ACCESS SHARE` cannot affect DDL."** False. DDL needing `ACCESS EXCLUSIVE` may wait on the dump.

**14. "Seeing the dump file means the backup succeeded."** No. Verify exit codes, archive inspection, checksums, and test restores.

**15. "`pg_dump` snapshots the entire cluster."** No. It dumps one database; `pg_dumpall` does not create one cross-database MVCC snapshot.

**16. "Sequences follow the snapshot like table rows."** No. `nextval`/`setval` are not transactional under standard MVCC.

**17. "A consistent dump means Kafka/object storage are synchronized too."** No. External systems require separate coordination.

**18. "Dumping from a standby never affects the primary."** No. Standby read load, recovery conflicts, and `hot_standby_feedback` can affect replication/primary vacuum.

**19. "`hot_standby_feedback` has only upsides."** No. It reduces query cancellations at the cost of retaining dead tuples and increasing primary bloat.

**20. "`pg_stat_progress_copy` tracks `pg_dump`."** No. `pg_dump` primarily reads using `SELECT`; the COPY progress view is not a logical dump tracker.

**21. "A `pg_dump` snapshot automatically pins all WAL segments."** No. WAL retention is governed by archiving, replication slots, and standby needs.

**22. "Two separate schema-only and data-only dumps always match."** No. They can capture two different snapshots.

**23. "`pg_dumpall` is an atomic backup across databases."** No. Global objects and individual databases are dumped in separate operations.

**24. "An archive readable by `pg_restore --list` is guaranteed to restore."** No. Run a test restore and verify dependencies.

**25. "Logical backups replace PITR."** No. PITR requires base backups and continuous WAL archiving.

---

## 20. Practice Exercises and Answers

### Exercise 1 — What Is a Snapshot?

**Question:** What does a snapshot determine?

**Answer:** The set of transactions/row versions a query is permitted to see under MVCC visibility rules at a logical point in time.

### Exercise 2 — Commits After Snapshot

**Question:** Does a transaction committed after `pg_dump` takes its snapshot appear in the dump?

**Answer:** No. Snapshots do not change as other transactions commit.

### Exercise 3 — `READ COMMITTED`

**Question:** Can two `SELECT` statements inside one `READ COMMITTED` transaction see two different states?

**Answer:** Yes. Each statement gets its own snapshot.

### Exercise 4 — `REPEATABLE READ`

**Question:** Why does `REPEATABLE READ` suit multi-query exports?

**Answer:** Queries within the transaction share one stable snapshot.

### Exercise 5 — `pg_dump` and DML

**Question:** Must `INSERT`/`UPDATE`/`DELETE` stop during `pg_dump`?

**Answer:** No. MVCC and `ACCESS SHARE` locks allow ordinary DML to continue.

### Exercise 6 — `ACCESS SHARE`

**Question:** Which lock mode conflicts with `ACCESS SHARE`?

**Answer:** `ACCESS EXCLUSIVE`.

### Exercise 7 — DDL

**Question:** Why might `DROP TABLE` wait for a dump?

**Answer:** `DROP TABLE` requires `ACCESS EXCLUSIVE`, which conflicts with the `ACCESS SHARE` lock held by `pg_dump`.

### Exercise 8 — Parallel Dump

**Prompt:** Write a parallel dump command using four jobs.

```bash
pg_dump --format=directory --jobs=4 --file=appdb.dumpdir --dbname=appdb
```

### Exercise 9 — Format

**Question:** Which format supports parallel dumps with `pg_dump`?

**Answer:** Directory format.

### Exercise 10 — Synchronized Snapshots

**Question:** Why do workers need a synchronized snapshot?

**Answer:** So every worker reads the same logical state, preventing parts of the dump from reflecting different timestamps.

### Exercise 11 — Exported Snapshot

**Prompt:** Obtain a snapshot token.

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT pg_export_snapshot();
```

### Exercise 12 — Importing a Snapshot

**Prompt:** Import a token in another session.

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET TRANSACTION SNAPSHOT 'snapshot-token';
```

Replace the token with the actual value, and keep the exporter transaction open until all consumers finish importing.

### Exercise 13 — Sequences

**Question:** Does `nextval()` roll back with a transaction?

**Answer:** No. Sequence operations are not transactional like row updates.

### Exercise 14 — Vacuum

**Question:** Why can a long snapshot increase bloat?

**Answer:** Vacuum cannot remove dead tuple versions still visible to the older snapshot.

### Exercise 15 — `backend_xmin`

**Prompt:** Inspect backends holding an xmin.

```sql
SELECT pid, application_name, xact_start, backend_xmin
FROM pg_stat_activity
WHERE backend_xmin IS NOT NULL
ORDER BY xact_start;
```

### Exercise 16 — Dead Tuples

**Prompt:** View tables with the highest dead tuple estimates.

```sql
SELECT schemaname, relname, n_dead_tup
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 10;
```

### Exercise 17 — Standby

**Question:** Why can a dump from a standby be canceled?

**Answer:** Recovery conflicts when a long query needs row versions or relation states that WAL replay needs to clean up or modify.

### Exercise 18 — `hot_standby_feedback`

**Question:** What trade-off does feedback carry?

**Answer:** It reduces query cancellations on the standby while retaining dead tuples longer on the primary.

### Exercise 19 — Multi-Database

**Question:** Does `pg_dumpall` guarantee a simultaneous snapshot across multiple databases?

**Answer:** No. Databases are dumped via separate operations.

### Exercise 20 — Monitoring

**Question:** Is there a standard `pg_stat_progress_pg_dump` view?

**Answer:** No unified progress view exists for logical `pg_dump`; use verbose output, `pg_stat_activity`, and OS metrics.

### Exercise 21 — Lock Timeout

**Prompt:** Limit lock waiting to 30 seconds.

```bash
pg_dump --lock-wait-timeout=30s --format=custom --file=appdb.dump --dbname=appdb
```

### Exercise 22 — Custom Archive

**Prompt:** Inspect the TOC.

```bash
pg_restore --list appdb.dump
```

### Exercise 23 — Test Restore

**Prompt:** Restore a custom archive into a test database.

```bash
createdb appdb_restore
pg_restore --exit-on-error --dbname=appdb_restore appdb.dump
```

### Exercise 24 — PITR

**Question:** Does `pg_dump` alone provide point-in-time recovery to an arbitrary timestamp?

**Answer:** No. Physical base backups and continuous WAL archiving are required.

### Exercise 25 — Failed Dumps

**Question:** Should a `.part` file be published when `pg_dump` exits non-zero?

**Answer:** No. Keep staging for investigation or clean up per procedure; run a fresh dump and publish only upon success.

### Exercise 26 — Load Impact

**Question:** Why can increasing jobs slow down applications?

**Answer:** Concurrent scans contend for storage I/O, CPU, network, and cache.

### Exercise 27 — Snapshots Outside the Database

**Question:** Does a `pg_dump` snapshot include Kafka messages published after commit?

**Answer:** No. Outboxes/offsets/coordination with external systems are required.

### Exercise 28 — Separate Schema/Data Dumps

**Question:** Do separate schema-only and data-only dump runs share the same snapshot?

**Answer:** Not by default; each run can start its own transaction snapshot.

### Exercise 29 — Application Name

**Prompt:** Assign an identifiable connection name.

**Answer:** Configure the `libpq` connection parameter `application_name`, such as `nightly_pg_dump`, and filter on it in `pg_stat_activity`.

### Exercise 30 — Backup Validation

**Question:** What confirms a backup is usable?

**Answer:** A successful test restore verifying schemas, data, sequences, permissions, dependencies, and application smoke tests.

---

## 21. Pre-, During-, and Post-Dump Checklist

### Before the Dump

1. Identify database, schema/object scope, and backup objective.
2. Choose logical dump vs. physical backup/PITR.
3. Verify PostgreSQL server/client versions.
4. Select plain/custom/directory format.
5. Choose jobs based on capacity, not raw CPU count.
6. Verify read privileges, extensions, large objects, and dependencies.
7. Verify disk space, network, and client destination.
8. Check for running migrations/DDL.
9. Set `application_name` to identify the session.
10. Pick the backup window and lock timeout.

### During the Dump

11. Watch exit status and verbose output.
12. Monitor CPU, I/O, network, archive size, and free filesystem space.
13. Monitor `xact_start`/`backend_xmin` and transaction age.
14. Monitor dead tuple estimates and autovacuum progress.
15. Monitor lock waits and DDL blockers.
16. If dumping from a standby, monitor recovery conflicts and replay lag.
17. Do not increase jobs once storage/network is saturated.
18. Never terminate a long snapshot without evaluating impact and rerun plans.

### After the Dump

19. Confirm `pg_dump` exited with code 0.
20. Inspect archive TOC or SQL output.
21. Compute checksums and write the manifest.
22. Publish staging artifacts per procedure.
23. Run a test restore into a dedicated database.
24. Verify schemas, constraints, data invariants, sequences, and permissions.
25. Run application smoke tests.
26. Measure RTO and record restore drill results.
27. Clean up staging/old dumps per retention policy.
28. Check whether vacuum has a cleanup backlog to monitor after the snapshot ends.

---

## 22. Summary

Consistent snapshots are the foundation enabling a multi-table dump to reflect one coherent database state. PostgreSQL uses MVCC; `pg_dump` holds a snapshot while reading, and parallel workers use synchronized snapshots so differing logical timestamps are never mixed.

Key points to remember:

- Commits after the snapshot do not appear in the dump; old row versions needed by that snapshot remain visible.
- `pg_dump` does not lock the entire database. `ACCESS SHARE` locks allow ordinary DML to proceed, though DDL needing `ACCESS EXCLUSIVE` may wait.
- `READ COMMITTED` takes a new snapshot per statement; `REPEATABLE READ` fits multi-query exports needing one shared snapshot.
- Parallel dumps use synchronized snapshots; directory format supports parallel dumps.
- Exported snapshots can coordinate multiple sessions/processes, provided the exporter transaction stays open until consumers import.
- Sequence operations do not follow MVCC snapshots like table rows.
- Long snapshots can pin dead tuples, slow vacuum cleanup, and increase bloat; monitor `backend_xmin`, transaction age, and autovacuum.
- Dumping from a standby risks recovery conflicts; `hot_standby_feedback` reduces cancellations at the cost of potential primary bloat.
- Dumps consume I/O, CPU, network, and cache; increasing jobs helps only when resources have headroom.
- `pg_dump` is a single-database logical backup, not a cluster-wide snapshot or PITR backup.
- Publish artifacts only after exit code 0, archive inspection, checksums, and test restores.

**Self-check question:** A dump runs for two hours while the application continuously runs `UPDATE` on rows. Why can the output file stay consistent, why might autovacuum fail to clean up certain dead tuples, and why might an `ALTER TABLE` statement wait? If you can explain MVCC snapshots, the xmin horizon, and `ACCESS SHARE`/`ACCESS EXCLUSIVE`, you have mastered the core mechanics of running dump impact.

### Official PostgreSQL Documentation

- [pg_dump — extract a PostgreSQL database](https://www.postgresql.org/docs/current/app-pgdump.html).
- [pg_dumpall — extract a PostgreSQL cluster](https://www.postgresql.org/docs/current/app-pg-dumpall.html).
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html).
- [MVCC Introduction](https://www.postgresql.org/docs/current/mvcc-intro.html).
- [System Information Functions — Snapshot Synchronization](https://www.postgresql.org/docs/current/functions-info.html).
- [Explicit Locking — Table-level Lock Modes](https://www.postgresql.org/docs/current/explicit-locking.html).
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html).
- [Monitoring Statistics — pg_stat_activity and pg_stat_user_tables](https://www.postgresql.org/docs/current/monitoring-stats.html).
- [Warm Standby — Hot Standby and Recovery Conflicts](https://www.postgresql.org/docs/current/hot-standby.html).
- [pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html).
- [Backup and Restore](https://www.postgresql.org/docs/current/backup.html).
