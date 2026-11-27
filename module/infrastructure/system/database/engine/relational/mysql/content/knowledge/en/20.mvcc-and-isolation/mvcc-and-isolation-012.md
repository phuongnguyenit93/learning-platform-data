# Long-Running Read Transactions, Undo History, and Purge Behavior

InnoDB uses MVCC (Multi-Version Concurrency Control) so a consistent read query can see the data version matching its snapshot while other transactions continue updating. When a row is updated or deleted, InnoDB keeps old version information in the undo log so older read transactions can reconstruct the data they are allowed to see.

Old versions cannot be cleaned up immediately when a writing transaction commits, because an active read view might still need them. Purge is the background process that cleans up versions and undo history that are no longer needed. A long-running read transaction can hold onto an old read view for a long time, forcing purge to wait, causing the history list to grow, and keeping required undo storage occupied.

In the `DATABASE_MYSQL` module, understanding the relationship between consistent reads, read views, undo history, and purge helps diagnose long-lived transactions, degrading query performance, growing undo tablespaces, and DDL statements waiting on metadata locks. This lesson focuses on InnoDB in MySQL 8.0 and later.

## Objectives

After this lesson, you will be able to:

- Explain why InnoDB needs to store old row versions in the undo log.
- Describe how a read view determines which versions a consistent read is allowed to see.
- Distinguish a transaction that started long ago from a read view that has been created and held for a long time.
- Compare the effect of `REPEATABLE READ` and `READ COMMITTED` on snapshot lifetime.
- Explain why a read-only transaction can still prevent purge from cleaning up undo history.
- Read `History list length` and transaction information to identify signs of purge lag.
- Understand the impact on undo tablespaces, read performance, and metadata locks.
- Choose measures to handle long transactions and reduce the risk of recurrence.

## 1. Why Must InnoDB Keep Old Row Versions?

Suppose a report starts reading account balances at time T1. While the report is running, another transaction updates a balance and commits at T2. If InnoDB only kept the new value, the report using an old snapshot could read a value that does not belong to the point in time the snapshot represents.

MVCC solves this problem by keeping enough information to reconstruct old versions. A consistent read query can read the version matching its read view, typically without locking rows to block other transactions from writing.

Conceptual example:

```text
Time ----------------------------------------------------------->

Transaction A (read): creates read view R1 ----- SELECT -------- COMMIT
                                              |
Transaction B (write):     UPDATE balance ---- COMMIT
                                              |
Row versions:          balance = 100       balance = 80
Undo history:          retains info for R1 to reconstruct balance = 100
Purge:                 cannot delete old version while R1 still needs it
```

As long as transaction A still holds read view R1, purge must not delete the undo information needed to reconstruct the `balance = 100` version. Once A finishes and no read view needs that version anymore, purge can clean up the corresponding history.

## 2. Undo Log and Row Versions

The undo log stores the information needed to undo changes and support MVCC. For InnoDB rows, records in the clustered index have internal metadata such as transaction ID and undo pointer. When a row is updated, InnoDB writes an undo record describing the prior state; the undo chain allows reconstructing the version required by an older read view.

### 2.1. Undo Serves Rollbacks and Consistent Reads

Undo serves two related roles:

- **Rollback:** if a writing transaction has not committed and needs to be aborted, InnoDB uses undo to restore the pre-change state.
- **MVCC/consistent read:** after a writing transaction commits, undo may still be needed for an older read view to reconstruct the version that existed before the update.

Therefore, committing does not mean all undo records of a transaction are immediately deleted. Some update undo must remain until no read view can possibly need it and purge can process that history.

### 2.2. Insert Undo and Update Undo

InnoDB distinguishes undo for insert operations from undo for update/delete operations. Insert undo is primarily needed for rollbacks while a transaction is uncommitted; once the transaction commits, an inserted record does not need to be reconstructed into a prior version for consistent reads. Update undo may continue to be needed after commit because an older read view must see the pre-update value or the row prior to being delete-marked.

You do not need to manage individual undo records manually. What matters operationally is that an old read transaction can extend the retention time required for update undo, preventing purge from cleaning up history behind it.

### 2.3. Undo Tablespace Is Not a Backup

The undo log is an internal structure serving transactions, rollbacks, and MVCC. It does not replace backups, binary logs, or point-in-time recovery mechanisms. Do not manually delete or edit undo tablespace files to reclaim space; doing so can corrupt the database.

## 3. Read Views and Consistent Reads

A read view is the set of information InnoDB uses to determine which transactions have committed and which row versions are visible at a snapshot. When a consistent read encounters a version newer than the snapshot, InnoDB follows undo to find a matching older version.

A read view is not a physical copy of the entire database. It is a visibility boundary enabling InnoDB to decide which version is visible to the query.

### 3.1. When Is a Read View Created?

With `REPEATABLE READ` (InnoDB's default isolation level), an ordinary consistent read in a transaction creates a read view at the first consistent read; subsequent consistent reads in the same transaction reuse that snapshot. You can request snapshot creation immediately upon starting the transaction with `START TRANSACTION WITH CONSISTENT SNAPSHOT` under the appropriate isolation level.

With `READ COMMITTED`, each ordinary consistent read creates a new read view for that statement. A transaction can see new commits in the next statement, even though the transaction has not ended.

Example requesting snapshot creation immediately upon starting the transaction:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY;

SELECT account_id, balance
FROM account_balance
WHERE account_id = 100;

COMMIT;
```

`WITH CONSISTENT SNAPSHOT` takes effect to create a consistent snapshot when the isolation level is `REPEATABLE READ`; do not use it expecting to force `READ COMMITTED` to share a single snapshot across multiple statements.

This means an old `trx_started` timestamp does not by itself prove a read view has existed for that entire duration. For example, if an RR transaction starts without running a consistent read yet, an ordinary read view has not been created; a transaction with `WITH CONSISTENT SNAPSHOT` is a different case. When investigating, examine the isolation level and actual read operations.

### 3.2. Consistent Read vs. Locking Read

An ordinary `SELECT` on InnoDB is usually a consistent nonlocking read. `SELECT ... FOR UPDATE` and `SELECT ... FOR SHARE` are locking/current reads, with different current-data reading and locking rules than ordinary consistent reads.

Do not assume a locking read releases an old read view created earlier in the same transaction. If the transaction already performed a consistent read under RR and remains open, the old read view can continue retaining needed undo history until the transaction ends.

## 4. How Long-Running Read Transactions Retain Undo History

A long-running read transaction might run just one initial `SELECT` statement and then sit idle, yet still hold its snapshot if the transaction has not ended. During that time, other transactions can update/delete rows and commit. New undo history accumulates; purge must preserve versions needed by the old read view.

```text
Time ------------------------------------------------------------------->

Session A: START TRANSACTION; SELECT ... (creates read view R1) --- COMMIT
                 |                                                 |
                 |       Session A idle yet transaction still open |
                 |                                                 |
Session B:       UPDATE/DELETE -- COMMIT -- UPDATE -- COMMIT -- ...
                       |                 |                 |
Undo history:         U1                U2                U3
                       \_______________________________   |
Purge:                  cannot clean versions needed by R1 -> cleans after A ends
```

Transaction A does not need to run queries continuously to keep holding a read view. If an application forgets `COMMIT`/`ROLLBACK`, or keeps a transaction open while waiting on a user or calling an external service, the read view can persist far longer than SQL execution time.

### 4.1. Read-Only Transactions Can Still Hold Snapshots

`START TRANSACTION READ ONLY` prevents ordinary write operations inside the transaction and can help InnoDB optimize certain internal work. However, read-only does not mean the snapshot automatically expires after the first SELECT statement. A read-only transaction that performs a consistent read and stays open can still prevent purge from removing old versions needed by the snapshot.

Example:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION READ ONLY;

SELECT account_id, balance
FROM account_balance
WHERE account_id = 100;

-- Application may be sitting idle here.
-- The read view can still be held in the transaction.

COMMIT;
```

If you only need a single standalone read statement, letting autocommit handle a statement-level transaction generally avoids holding snapshots for long. If multiple read statements need the same snapshot, keep the transaction open deliberately and set appropriate time bounds.

### 4.2. A Long Statement Can Also Hold a Read View While Running

Even with autocommit enabled, a SELECT statement taking several minutes still needs a snapshot for the entire duration the statement runs. Once the statement finishes, the transaction ends automatically under autocommit and the statement's read view is no longer held by that transaction.

Thus, two forms should be distinguished:

- **Long statement:** the read view exists for the duration the query is executing.
- **Long transaction:** the read view can persist after the statement finishes, even while the connection is idle, until the transaction commits/rolls back.

## 5. Isolation Levels Affect Snapshot Retention Time

### 5.1. REPEATABLE READ

In InnoDB RR, the first consistent read creates a snapshot and later consistent reads in the same transaction reuse that snapshot. If the transaction lives a long time, the read view can also live a long time.

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance
FROM account_balance
WHERE account_id = 100;

-- Subsequent consistent reads continue using the same snapshot.
SELECT balance
FROM account_balance
WHERE account_id = 100;

COMMIT;
```

RR fits when multiple reads in a transaction must see the same snapshot. In return, a long-lived read view can retain undo history longer.

### 5.2. READ COMMITTED

In RC, each consistent read creates a new read view. The transaction does not hold one shared snapshot for all ordinary SELECTs; each statement can see changes committed before that statement starts.

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT balance
FROM account_balance
WHERE account_id = 100;

-- Another transaction updates and commits.

SELECT balance
FROM account_balance
WHERE account_id = 100;

COMMIT;
```

The second SELECT can see the newly committed value. The first statement's snapshot does not need to be retained as the snapshot for the later statement, so RC generally reduces the impact of holding read views across multiple statements. However, a long-running RC statement still holds a read view while it executes; RC does not eliminate the cost of long statements.

### 5.3. Quick Comparison

| Characteristic | REPEATABLE READ | READ COMMITTED |
|---|---|---|
| Consistent read's read view | Created at the first consistent read in the transaction, unless requested early | Created fresh for each consistent read statement |
| Two SELECTs in the same transaction | Typically see the same snapshot | Can see new commits between the two statements |
| Old read view held across statements | Yes, until the transaction ends | Typically no; each statement has its own snapshot |
| Long-running read statement | Holds read view while executing | Holds read view while executing |
| Effect of idle transaction after SELECT | Can continue holding the old snapshot | Previous statement's snapshot is not used for the next statement, though the transaction can still hold other resources/metadata locks |

Do not switch isolation levels just to make purge run faster without evaluating business semantics. Changing RR to RC can cause two reads within the same transaction to see different data.

## 6. What Is Purge?

Purge is InnoDB's background process that cleans up row versions and undo log records no longer needed for rollbacks or any active read view. It processes history created by writing transactions after commit, once older versions have become safe to remove.

Purge is not a `DELETE` operation called by the application, nor an SQL command users must run manually after every transaction. InnoDB manages purge threads automatically.

### 6.1. Conditions for a Version to Be Purged

Conceptually, an old version can only be cleaned up when no read view needs it anymore. If an old read view can still see that version, purge must retain the necessary undo. After the transaction holding that read view ends, purge can resume processing history if cleanup throughput is fast enough.

Besides read views, purge must also handle delete-marked records and other internal constraints. Therefore, an old transaction ending does not mean all undo history vanishes instantaneously at commit time; purge runs asynchronously.

### 6.2. Purge Threads and Keeping Up

InnoDB has purge threads to process history in the background. If the rate at which write transactions generate undo exceeds purge cleanup speed, the history list can grow even without any single read transaction holding a snapshot for too long.

Therefore, when seeing a large history list, check both possibilities:

- An old read view is blocking purge from advancing past the history it must retain.
- Write workload is generating undo faster than purge can process it.

Do not rush to increase `innodb_purge_threads` or alter purge lag variables based on a single metric reading. First identify the source retaining history, undo generation rate, CPU/I/O, and actual configuration.

## 7. History List Length and How to Read It

`SHOW ENGINE INNODB STATUS` displays transaction and purge information. In the TRANSACTIONS section there is typically a line like:

```text
History list length 12500
```

History list length is an indicator of the number of undo log pages in the history list awaiting purge processing. It is useful for tracking trends, but it is not the number of deleted rows, open transactions, exact bytes, or transaction age.

### 7.1. Checking InnoDB Status

In the MySQL CLI:

```sql
SHOW ENGINE INNODB STATUS\G
```

Locate the `TRANSACTIONS` section, `History list length`, purge status, and active transaction details. Compare multiple readings over time:

- History list length growing continuously: purge is blocked or failing to keep up with the workload.
- History list length decreasing: purge is catching up on the backlog.
- Fluctuating metric: may be normal under the workload; examine trend and sustained duration.

Do not apply a single universal threshold for every system. What is acceptable depends on write rate, data size, latency, undo capacity, and longest snapshot duration.

### 7.2. Checking InnoDB Metrics If Enabled

Some versions/configurations expose the `trx_rseg_history_len` metric in `INFORMATION_SCHEMA.INNODB_METRICS`:

```sql
SELECT NAME, COUNT
FROM INFORMATION_SCHEMA.INNODB_METRICS
WHERE NAME = 'trx_rseg_history_len';
```

If the metric does not appear or is not enabled in the current environment, use `SHOW ENGINE INNODB STATUS` and your existing monitoring system. Do not interpret `COUNT` as bytes or exact row version counts.

## 8. Finding Long-Open Transactions

`INFORMATION_SCHEMA.INNODB_TRX` provides information about current InnoDB transactions. You can sort by start time to find the oldest transactions:

```sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS age_seconds,
    trx_isolation_level,
    trx_is_read_only,
    trx_rows_locked,
    trx_rows_modified,
    trx_mysql_thread_id,
    trx_query
FROM INFORMATION_SCHEMA.INNODB_TRX
ORDER BY trx_started;
```

Useful columns:

- `trx_started`: timestamp when the transaction began.
- `age_seconds`: transaction age at the moment the monitoring query runs.
- `trx_isolation_level`: isolation level of the transaction.
- `trx_is_read_only`: whether the transaction is marked read-only.
- `trx_rows_locked`: number of rows locked by the transaction according to InnoDB info.
- `trx_rows_modified`: number of rows modified by the transaction.
- `trx_mysql_thread_id`: connection ID, which can be matched with the process list.
- `trx_query`: current statement; may be `NULL` if the transaction is idle.

A transaction with `trx_query IS NULL` yet a very old `trx_started` may be a session sitting idle inside a transaction. This is worth investigating, especially when history list length is rising.

### 8.1. Cross-Referencing Connection ID with the Process List

```sql
SHOW FULL PROCESSLIST;
```

Match `trx_mysql_thread_id` against the `Id` column to see user, host, database, command, time, and connection state. Look for `Sleep` sessions that still have an entry in `INNODB_TRX`; they are usually prime candidates for closer inspection.

Do not conclude a transaction is causing purge lag solely from its age. Determine whether it has created a read view yet, its isolation level, whether it holds metadata locks, and how the history list changed over the same period.

## 9. Impact of Long-Running Read Transactions

### 9.1. Undo History Grows and Purge Is Blocked

If an old read view needs versions prior to a point in time, purge cannot clean up undo records that snapshot might need. Update/delete workloads continue generating new history, growing the backlog.

### 9.2. Consistent Reads Must Traverse Longer Version Chains

When a row is updated many times, a query needing a very old version may have to traverse many undo versions. A long version chain increases the work to reconstruct the row version, potentially slowing down consistent reads.

### 9.3. Undo Tablespace and Disk Space

Undo pages must be retained or reused. When the backlog grows, undo space can expand, and allocated space may not immediately be returned to the OS after purge catches up. Reclaiming undo tablespace file space depends on undo tablespace configuration and truncation mechanisms; a shrinking purge backlog does not mean files always shrink immediately.

Do not delete undo tablespace files or edit system files manually. Check configuration and MySQL version documentation before changing truncation policies.

### 9.4. Metadata Locks Can Force DDL to Wait

A transaction holding accessed tables can hold metadata locks until the transaction ends. A long-running read transaction can therefore force `ALTER TABLE`, `RENAME TABLE`, or DDL needing an exclusive metadata lock to wait. While DDL is waiting, new queries against the table can also queue behind the metadata lock request depending on the situation.

This is a different mechanism from retaining undo history, even though both can appear together in a single long transaction. Diagnosing waiting DDL requires inspecting metadata locks and the process list, not just history list length.

## 10. Two-Session Lab: RR Holding a Snapshot Long-Term

Run in a dedicated lab database. Create data:

```sql
CREATE TABLE mvcc_demo_account (
    account_id BIGINT NOT NULL PRIMARY KEY,
    balance DECIMAL(12, 2) NOT NULL
) ENGINE=InnoDB;

INSERT INTO mvcc_demo_account (account_id, balance)
VALUES (100, 1000.00);
```

### Session A: Open an RR Transaction and Perform the First Read

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance
FROM mvcc_demo_account
WHERE account_id = 100;
-- Result: 1000.00
```

After the first SELECT, RR's read view is created. Leave transaction A open and do not commit.

### Session B: Update and Commit Multiple Times

```sql
START TRANSACTION;
UPDATE mvcc_demo_account
SET balance = 900.00
WHERE account_id = 100;
COMMIT;

START TRANSACTION;
UPDATE mvcc_demo_account
SET balance = 800.00
WHERE account_id = 100;
COMMIT;
```

### Back in Session A

```sql
SELECT balance
FROM mvcc_demo_account
WHERE account_id = 100;
```

Under RR, A's consistent read still sees `1000.00`, even though B committed `800.00`. InnoDB uses undo to reconstruct the old version matching A's read view.

End Session A:

```sql
COMMIT;
```

Once no read view needs the old versions anymore, purge can resume cleaning up that history. Because the process runs in the background, history list does not necessarily drop instantaneously at commit time.

## 11. Two-Session Lab: READ COMMITTED Creates a New Snapshot per Statement

Set Session A to RC:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT balance
FROM mvcc_demo_account
WHERE account_id = 100;
```

Suppose the initial result is `800.00`. Session B updates and commits `700.00`:

```sql
START TRANSACTION;
UPDATE mvcc_demo_account
SET balance = 700.00
WHERE account_id = 100;
COMMIT;
```

Rerun SELECT in Session A:

```sql
SELECT balance
FROM mvcc_demo_account
WHERE account_id = 100;
```

Under RC, the second statement can see `700.00` because it creates a new read view. Transaction A is still open, yet the first statement's snapshot is not reused for the second statement as in RR.

End Session A:

```sql
COMMIT;
```

## 12. Idle Transaction Scenario in Applications

A common mistake in JDBC or connection pool applications is starting a transaction, running a SELECT, and then waiting on non-database processing while forgetting to end the transaction:

```java
connection.setAutoCommit(false);

try {
    readReportRows(connection);

    // Do not keep a transaction open while waiting on users,
    // calling HTTP services, or processing large files.
    callExternalService();

    connection.commit();
} catch (Exception failure) {
    connection.rollback();
    throw failure;
}
```

If `readReportRows()` already created a consistent read view under RR, the duration of the external service call also extends the snapshot's age. The connection may appear in `Sleep` state in the process list while the transaction remains open.

A better design is typically:

- Open a transaction only right before the database operations needing consistency.
- End the transaction immediately after those operations complete.
- Never hold a transaction open across network waits, input prompts, or user interaction.
- Ensure every exception branch rolls back and returns a clean connection to the pool.
- For standalone read-only queries, consider autocommit or short read-only transactions.

If you need to process a very long report on a single snapshot, make that a deliberate architectural decision. Measure undo history impact, run on a suitable replica if available, bound runtime, and plan for ending the snapshot.

## 13. Reducing the Impact of Long-Running Read Queries

### 13.1. Keep Transactions Short

This is the single most important measure. Avoid opening a transaction at the start of a request and holding it across steps that do not need the database. Commit/roll back immediately once transactional work finishes.

### 13.2. Keyset Pagination

For reports that can be read in batches, keyset pagination helps avoid a single SELECT scanning and holding a cursor for too long:

```sql
SELECT account_id, updated_at, balance
FROM account_balance
WHERE account_id > 1000
ORDER BY account_id
LIMIT 500;
```

The next page uses the previous page's last key as the boundary. Each page can be a short statement/transaction. However, if committing between pages, data can change between reads; results are no longer one unified snapshot. Clearly decide whether the report tolerates new data between pages or requires a single consistent snapshot across the entire output.

### 13.3. Fetch Only Needed Columns and Use Indexes

Reducing the number of rows/columns read helps statements finish faster, thereby reducing how long read views are held. Choose suitable indexes, avoid unnecessary full table scans, and inspect `EXPLAIN` to understand the access path.

### 13.4. Do Not Use a Higher Isolation Level Than Needed

If business rules allow each SELECT to see a new snapshot, RC can reduce snapshot retention across multiple statements compared to RR. However, RC does not make long-running statements disappear and can change results when the same transaction reads multiple times.

### 13.5. Set Operational Limits

Monitor transaction age, history list length, and query latency. You can configure application-tier timeouts or transaction monitoring mechanisms to detect sessions sitting idle in transactions. Choose thresholds based on workload; do not blindly kill every transaction solely because its age exceeds a generic number.

## 14. Procedure for Investigating a Growing History List

When history list length increases persistently, proceed in order:

1. Record history list length and timestamps; inspect the trend across multiple samples.
2. List transactions in `INFORMATION_SCHEMA.INNODB_TRX`, sorted by `trx_started`.
3. Identify idle transactions (`trx_query IS NULL`), read-only transactions, and isolation levels.
4. Cross-reference connection IDs with `SHOW FULL PROCESSLIST` to find the application, host, and state.
5. Determine which transactions have performed consistent reads and may be holding old read views.
6. Check update/delete rates and I/O/CPU load to see whether purge is failing to keep up with the workload even without an old snapshot.
7. Check metadata locks if DDL or new queries are waiting.
8. Coordinate with the application owner to end the transaction cleanly or schedule remediation.
9. After the transaction ends, monitor purge catching up and history list gradually decreasing.
10. Adjust code or operations to prevent recurrence; tune purge settings only after identifying the root cause.

Do not arbitrarily kill connections solely based on transaction age. A transaction may be a legitimate running report or an important operational job.

### 14.1. KILL QUERY and KILL CONNECTION

`KILL QUERY <id>` stops the connection's currently executing statement without necessarily ending the transaction. If the session is idle inside a transaction, there is no statement to stop and the transaction can still hold its read view.

`KILL CONNECTION <id>` terminates the connection; any uncommitted transaction on that connection will be rolled back. Rollback can take time if the transaction modified a large amount of data. Only DBAs or authorized personnel should run this after confirming the owner, business impact, and recovery plan.

After ending the transaction, purge still needs time to process the backlog; do not expect KILL to drop history list to 0 instantaneously.

## 15. Common Misconceptions

| Misconception | Reality |
|---|---|
| Read-only transactions do not affect purge | A read-only consistent read can still hold a read view and undo history |
| Writing transaction COMMIT immediately deletes all undo | Update undo may still be needed for older read views |
| History list length is the count of old rows | It is an undo history/page indicator, not an exact row version or byte count |
| Old `trx_started` always means an old read view | Check whether the transaction has performed a consistent read yet and check its isolation level |
| Idle transactions hold no resources | An idle transaction after a consistent read can still hold a snapshot and metadata locks |
| READ COMMITTED eliminates all purge lag | Long-running RC statements still hold read views; write workloads can also outpace purge |
| KILL QUERY ends the transaction | It stops the statement, without guaranteeing transaction/connection closure |
| When purge shrinks the backlog, undo files immediately shrink | Pages can be reused; tablespace truncation is a separate mechanism |
| Long reads always lock writers | Consistent reads usually do not lock rows like locking reads, but can retain undo history and metadata locks |

## 16. Practice Exercises

Perform in a MySQL lab with at least two sessions and InnoDB tables:

1. Create a balances table and insert a sample row.
2. Open Session A under RR, run the first SELECT, and leave the transaction open.
3. Use Session B to update the same row and commit multiple times.
4. Rerun SELECT in Session A; explain why it still sees the old version.
5. Commit Session A, then inspect `SHOW ENGINE INNODB STATUS` multiple times to observe purge processing history.
6. Repeat the experiment under RC and confirm the second read statement sees new commits.
7. Open a read-only transaction, perform a consistent read, and leave the session idle; locate it in `INNODB_TRX` and the process list.
8. Compare `trx_started`, `trx_query`, `trx_is_read_only`, and `trx_isolation_level`; explain why `trx_query` can be NULL.
9. Generate an update/delete workload in the lab while holding an old read view; observe the history list length trend. Stop the workload before creating excessive load.
10. Run a long autocommit SELECT and compare snapshot retention duration against a multi-statement transaction.
11. Open a transaction reading a table and try DDL from another session; observe metadata lock waits in the lab environment.
12. Use keyset pagination to split a large query; explain the consistency trade-off when committing between pages.
13. Distinguish the behavior of `KILL QUERY` and `KILL CONNECTION` on a lab transaction; verify whether the transaction ends or not.
14. Write an investigation checklist for a growing history list, covering transaction age, read views, purge throughput, undo tablespace, and metadata locks.

You have completed this lesson when you can explain why an idle read transaction can retain undo history, read signs of purge backlog, and choose ways to shorten snapshot duration while still meeting report consistency requirements.

## 17. Key Principles to Remember

- InnoDB retains undo for rollbacks and for consistent reads to reconstruct older row versions.
- A read view determines which versions a transaction sees; it is not a physical copy of the database.
- Under RR, the first consistent read creates a snapshot reused for subsequent consistent reads in the transaction; `WITH CONSISTENT SNAPSHOT` can create the snapshot immediately upon start.
- Under RC, each consistent read statement creates a new read view; long statements still hold their snapshot while running.
- Read-only transactions can still hold read views and prevent purge from cleaning up old versions.
- Transactions left idle after a SELECT can continue holding snapshots if not committed/rolled back.
- Purge cleans up undo history and delete-marked records when no read view needs them anymore; purge runs in the background, not synchronously at COMMIT.
- History list length is an undo history backlog indicator, not an exact row or byte count.
- Use `INFORMATION_SCHEMA.INNODB_TRX`, `SHOW FULL PROCESSLIST`, and `SHOW ENGINE INNODB STATUS` to investigate.
- Long transactions can force consistent reads to spend more effort reconstructing old versions and cause undo tablespaces to require more space.
- Transactions accessing tables can hold metadata locks until the end of the transaction, forcing DDL to wait.
- `KILL QUERY` stops a statement; `KILL CONNECTION` closes the connection and rolls back uncommitted transactions.
- Purge catching up does not mean undo tablespace files immediately shrink.
- Keep transactions short, do not wait on external services inside transactions, and only change isolation levels when business semantics allow.
