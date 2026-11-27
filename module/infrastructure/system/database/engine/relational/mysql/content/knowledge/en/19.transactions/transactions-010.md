# Consistent Snapshots and When Read Views Are Established

InnoDB uses MVCC (Multi-Version Concurrency Control) to allow a transaction to read a consistent version of data without locking every row being read. The data version visible to a regular `SELECT` is determined by a **read view** (read snapshot). The moment the read view is created determines which previously committed changes the transaction sees and which subsequently committed changes it ignores.

Under the `REPEATABLE READ` isolation level, consistent reads within the same transaction usually share the read view created at the first consistent read. Therefore, a regular `START TRANSACTION` does not necessarily take a snapshot at the moment that statement runs. If you want to capture the snapshot immediately at transaction start, you can use `START TRANSACTION WITH CONSISTENT SNAPSHOT` under `REPEATABLE READ`. Under `READ COMMITTED`, each consistent read creates a fresh snapshot for each statement.

Understanding snapshot timing helps you explain why two SELECTs in the same transaction can read older data, why a transaction started before an UPDATE can still see that UPDATE if it hasn't read a snapshot yet, and why a locking read can return a newer version than a consistent read. This lesson explains how MVCC determines visible data, snapshot creation points, and how to verify them across two MySQL sessions.

## 1. Consistent Read and MVCC

InnoDB stores row version metadata and undo logs so it can reconstruct older versions when a transaction needs to read an earlier snapshot. With consistent reads, InnoDB uses a read view to determine which transactions had committed at snapshot time and which versions are visible.

A regular `SELECT` on an InnoDB table is a consistent nonlocking read under appropriate isolation levels. It does not place shared locks on every row merely for reading data. Thanks to MVCC, one transaction can read versions committed prior to its snapshot while another transaction updates rows and commits new versions.

For example, an account has balance 100 at snapshot time:

```text
Time            Transaction A                  Transaction B
----------------------------------------------------------------
t1              Create read view: balance = 100
t2                                             UPDATE balance = 150
t3                                             COMMIT
t4              SELECT balance -> 100
```

Transaction A continues reading the old version per its read view, even though Transaction B already committed 150. A new transaction starting a consistent read after t3 will see 150.

### A Consistent Read Is Not a Physical Copy of the Entire Database

A read view is a rule determining which row versions are visible when reading InnoDB. It does not create a backup, does not lock the database, and does not copy entire tables into an independent data area. InnoDB combines the read view with row versions and undo logs to return consistent results.

A read view belongs to the current transaction. When the transaction ends, that snapshot is no longer available to reuse for a new transaction. To keep a result for long-term analysis, save the result or use an appropriate snapshot/backup mechanism; you cannot retain a read view as an independent backup.

## 2. When Is a Snapshot Created Under REPEATABLE READ?

In MySQL, InnoDB's default isolation level is typically `REPEATABLE READ`. Under this isolation level, consistent reads in the same transaction share the same read view.

If a transaction is started with a regular `START TRANSACTION`, the read view is typically created when the transaction executes its first consistent read, not necessarily at the `START TRANSACTION` statement.

Example sequence:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

-- At this point the transaction has started, but no consistent read has run yet.
-- A read view has not necessarily been created yet.

SELECT balance
FROM accounts
WHERE account_id = 1;
-- First consistent read: creates the read view for the transaction.

SELECT balance
FROM accounts
WHERE account_id = 1;
-- Reuses the already created read view.

COMMIT;
```

If another transaction commits a change after `START TRANSACTION` but before the first SELECT statement, the current transaction can see that change because the snapshot had not been created yet. If the change commits after the first consistent read, subsequent consistent reads in the same transaction still see the version per the old snapshot.

This is a critical distinction between **when the transaction starts** and **when the read view is created**.

## 3. Creating a Snapshot Immediately When Starting a Transaction

If you need to establish the snapshot right at the start of the transaction, MySQL supports:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT;

SELECT balance
FROM accounts
WHERE account_id = 1;

COMMIT;
```

`WITH CONSISTENT SNAPSHOT` instructs InnoDB to create the consistent read view when the transaction starts. Consequently, other transactions committing after this point will not appear in the current transaction's consistent reads.

You can combine it with `READ ONLY` for a read-only transaction:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY;

SELECT account_id, balance
FROM accounts
ORDER BY account_id;

SELECT COUNT(*) AS account_count
FROM accounts;

COMMIT;
```

Both SELECT statements share the same snapshot, which is suitable when reading multiple tables or running multiple queries to build a consistent report. `READ ONLY` declares the intent not to write data in the transaction and can help InnoDB optimize certain operations.

### Isolation Level Requirement

`WITH CONSISTENT SNAPSHOT` is only meaningful with `REPEATABLE READ`. At other isolation levels, MySQL ignores this option and emits a warning depending on version behavior. Do not use it expecting `READ COMMITTED` to hold a single snapshot across the entire transaction.

Check isolation level and session configuration:

```sql
SELECT
    @@SESSION.transaction_isolation AS session_isolation,
    @@GLOBAL.transaction_isolation AS global_isolation,
    @@SESSION.autocommit AS autocommit_value;
```

`transaction_isolation` is the variable name on modern MySQL versions. Some older versions use the name `tx_isolation`; verify the server version when working with legacy systems.

## 4. Two-Session Example: Snapshot Created at the First Read

To observe snapshot creation timing precisely, open two independent connections to the same database. Create test data once:

```sql
CREATE TABLE snapshot_demo (
    id BIGINT UNSIGNED NOT NULL,
    balance DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

INSERT INTO snapshot_demo (id, balance)
VALUES (1, 100.00);
```

### Session A

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

-- No snapshot read at the moment of START TRANSACTION.
```

### Session B

```sql
START TRANSACTION;

UPDATE snapshot_demo
SET balance = 150.00
WHERE id = 1;

COMMIT;
```

### Back to Session A

```sql
SELECT balance
FROM snapshot_demo
WHERE id = 1;
```

The result is `150.00`. This is transaction A's first consistent read, so the read view was created after B committed.

Next, in Session B update again:

```sql
START TRANSACTION;

UPDATE snapshot_demo
SET balance = 200.00
WHERE id = 1;

COMMIT;
```

In Session A, read again:

```sql
SELECT balance
FROM snapshot_demo
WHERE id = 1;
```

The result is still `150.00` because transaction A already has a read view from the earlier SELECT. End it:

```sql
COMMIT;
```

A new transaction will see `200.00`.

## 5. Two-Session Example: WITH CONSISTENT SNAPSHOT Captures Immediately at Start

Reset the data to an easily observable value:

```sql
UPDATE snapshot_demo
SET balance = 100.00
WHERE id = 1;
```

### Session A

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT;
```

As soon as the transaction starts, the read view is created.

### Session B

```sql
START TRANSACTION;

UPDATE snapshot_demo
SET balance = 150.00
WHERE id = 1;

COMMIT;
```

### Back to Session A

```sql
SELECT balance
FROM snapshot_demo
WHERE id = 1;
```

The result is `100.00`, because the snapshot was created before Session B committed 150. Subsequent consistent reads in Session A continue seeing 100 until the transaction ends.

```sql
COMMIT;
```

A new transaction afterward will see 150.

## 6. REPEATABLE READ and READ COMMITTED Differ in Snapshot Timing

Both isolation levels use InnoDB consistent reads, but differ in read view lifetime:

| Isolation Level | Snapshot Creation Time for Consistent Read | Two SELECTs in the Same Transaction |
|---|---|---|
| `REPEATABLE READ` | First read view is created on the first consistent read; or immediately at start if using `WITH CONSISTENT SNAPSHOT`. | Share the same read view, so they can read the same committed version. |
| `READ COMMITTED` | Each consistent read creates a fresh read view when the statement starts. | Can see newly committed changes between two statements. |
| `READ UNCOMMITTED` | Does not guarantee consistent snapshots in the manner above; SELECT can read uncommitted versions. | Can see uncommitted data and results are not stably repeatable. |

Example with `READ COMMITTED`:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT balance
FROM snapshot_demo
WHERE id = 1;
-- Snapshot for the first statement.

SELECT balance
FROM snapshot_demo
WHERE id = 1;
-- Fresh snapshot for the second statement.

COMMIT;
```

If another transaction commits between the two SELECTs, the second statement can see the new value. This is expected `READ COMMITTED` behavior, not an MVCC bug.

### Setting the Isolation Level

Set for the next transaction:

```sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
```

Set default for transactions in the current session:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
```

Set default for new sessions (requires appropriate privileges):

```sql
SET GLOBAL TRANSACTION ISOLATION LEVEL REPEATABLE READ;
```

Changing GLOBAL does not alter the isolation level of already connected sessions. When using a connection pool, inspect actual sessions rather than assuming every connection received the new setting.

## 7. Consistent Read and Current Read Are Two Different Read Modes

Not every SELECT in a transaction reads from a snapshot. InnoDB distinguishes:

- **Consistent read:** regular SELECT, reading versions matching the read view without placing row locks like a locking read.
- **Current read:** locking reads such as `SELECT ... FOR UPDATE`, `SELECT ... FOR SHARE`, and write operations such as UPDATE/DELETE that must find the current version to lock and modify.

In `REPEATABLE READ`, a current read can see the latest committed version at read time, while a consistent read still uses the old snapshot. Consequently, mixing both read types in the same transaction can produce results that look inconsistent if you do not understand the semantics.

Example:

```sql
-- Session A
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance
FROM snapshot_demo
WHERE id = 1;
-- Suppose the snapshot returns 100.
```

Meanwhile Session B updates and commits balance to 150:

```sql
-- Session B
START TRANSACTION;

UPDATE snapshot_demo
SET balance = 150.00
WHERE id = 1;

COMMIT;
```

Then Session A runs:

```sql
SELECT balance
FROM snapshot_demo
WHERE id = 1
FOR UPDATE;
```

This is a locking/current read, which can read the current version 150 and lock the row to protect subsequent writes. A subsequent regular SELECT in Session A can still return 100 according to its initial read view.

```sql
SELECT balance
FROM snapshot_demo
WHERE id = 1;
-- Consistent read still uses the old snapshot.

COMMIT;
```

Never use `FOR UPDATE` just to "refresh the snapshot." It alters semantics by locking rows and can cause lock waits or deadlocks. If you need fresh data, usually end the current transaction and start a new one.

## 8. A Transaction Sees Its Own Changes

A read view does not mean a transaction always sees an absolutely immutable version of every row. A transaction always sees changes that it performed itself earlier.

Example:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance
FROM snapshot_demo
WHERE id = 1;
-- Initial snapshot.

UPDATE snapshot_demo
SET balance = balance + 10.00
WHERE id = 1;

SELECT balance
FROM snapshot_demo
WHERE id = 1;
-- Sees this transaction's own change.

ROLLBACK;
```

The transaction sees the version it just wrote itself. Changes from other transactions are still evaluated against its read view in consistent reads. When reading multiple rows after modifying some rows, results may include the transaction's own changes alongside old snapshot versions of rows not modified by that transaction.

This is part of InnoDB MVCC semantics. If you need a consistent read-only report, avoid modifying data and using the same transaction while assuming every row represents a pure global point in time.

## 9. Autocommit and Snapshot Lifetime

MySQL usually enables `autocommit` by default. When `autocommit = 1`, each standalone statement executes as its own transaction unless an explicit transaction is opened. A standalone SELECT has a snapshot serving that statement alone; the next SELECT is a different transaction/statement and can see new commits.

Check:

```sql
SELECT @@SESSION.autocommit;
```

To make multiple SELECTs share the same snapshot, open a transaction explicitly:

```sql
START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY;

SELECT COUNT(*) FROM accounts;
SELECT SUM(balance) FROM accounts;
SELECT account_id, balance FROM accounts ORDER BY account_id;

COMMIT;
```

The InnoDB SELECT statements share the same read view in `REPEATABLE READ`. Without opening a transaction, each separate statement may see a different state as data changes between statements.

Do not arbitrarily turn off session-wide autocommit inside a connection pool. When `autocommit = 0`, a transaction can stay open across multiple statements if not committed/rolled back promptly, holding snapshots and locks longer than expected.

## 10. Consistent Snapshots Across Multiple Tables

One advantage of a read view is that multiple consistent reads in the same transaction can observe InnoDB tables at the exact same snapshot point. This is useful for summary reports needing to read accounts, transactions, and history in one transaction.

Example:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY;

SELECT COUNT(*) AS account_count
FROM accounts;

SELECT COUNT(*) AS transaction_count
FROM account_transactions;

SELECT SUM(amount) AS total_amount
FROM account_transactions;

COMMIT;
```

If all tables use InnoDB and the statements are consistent reads, they are evaluated against the transaction's snapshot together. As a result, a report will not pull account counts from one point in time and transaction totals from another point due to other transactions committing between SELECTs.

### Note on Storage Engines

MVCC consistent snapshots are an InnoDB mechanism. If a transaction reads a table that does not support transactions/MVCC like MyISAM, you cannot assume that table follows the same snapshot or rollback semantics. When reports require cross-table consistency, use InnoDB for the involved tables and verify the actual storage engines.

Check engines:

```sql
SELECT
    table_name,
    engine
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN ('accounts', 'account_transactions');
```

## 11. Long-Lived Snapshots and Undo/Purge Cost

A transaction holding a read view for a long time can prevent InnoDB from removing old row versions that the snapshot might still need to read. Old versions are retained in undo history until no read view needs them and purge can clean them up.

Long-running read transactions can lead to:

- Growing undo history and delayed purge.
- Growing undo tablespaces or storage usage.
- I/O and CPU overhead to retain, traverse, or purge old versions.
- Indirect impact on other queries when the history list grows long.
- Connection pool exhaustion caused by unclosed transactions.

Risk example:

```sql
START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY;

SELECT COUNT(*)
FROM very_large_table;

-- Application keeps the transaction open for many minutes or hours.
-- Other transactions continue updating data constantly.

-- Only ends when reading finishes:
COMMIT;
```

`READ ONLY` does not mean the transaction holds no snapshot or incurs no undo/purge cost. If a transaction must read for a long time, consider breaking up the work, creating staging/report snapshot tables, exporting data in batches, or using a dedicated reporting solution.

### Monitoring Transactions and History List

You can inspect open transactions:

```sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_isolation_level,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

To inspect more InnoDB status:

```sql
SHOW ENGINE INNODB STATUS;
```

In the TRANSACTIONS section, inspect running transaction details and history list length. These are signals to investigate alongside transaction open duration, write load, and purge rate; do not use a single number alone to conclude the system is failing.

## 12. Consistent Read and Locking Do Not Replace Each Other

Choose the read mode according to your goal:

| Goal | Approach |
|---|---|
| Report needing the same committed state across multiple SELECTs | `REPEATABLE READ` transaction with consistent reads; consider `WITH CONSISTENT SNAPSHOT`. |
| Each statement must see the latest commit before that statement starts | `READ COMMITTED`. |
| Read a row then update that row, preventing concurrent modification by other transactions | Locking read `SELECT ... FOR UPDATE`. |
| Only read data without needing row locks | Regular SELECT using consistent read. |
| Need to read fresh data after an old snapshot | End the transaction and start a new transaction. |

Do not use locking reads to solve every stale-data issue. Locking reads can block other transactions, create deadlocks, and reduce throughput. Conversely, consistent reads do not lock rows, so they cannot replace locks when protecting a write decision.

## 13. Procedure to Verify Snapshot Timing

When an application reports reading "stale" data, check in order:

1. Identify the table's storage engine; verify involved tables use InnoDB.
2. Check the connection's actual isolation level, not just the global default.
3. Determine autocommit status and whether a transaction was opened explicitly.
4. Locate the timestamp of `START TRANSACTION` or `BEGIN`.
5. Locate the first consistent read in the transaction.
6. Check whether the transaction uses `WITH CONSISTENT SNAPSHOT`.
7. Check whether locking reads (`FOR UPDATE`, `FOR SHARE`) or DML are interleaved between SELECTs.
8. Compare the commit timestamp of writing transactions against read view creation time.
9. Check whether the transaction is being kept open by the application or connection pool.
10. End the transaction promptly and verify a new transaction sees the new data.

Useful application logs should record connection/transaction boundaries, isolation level, start time, query time, and commit/rollback time. Avoid logging only SQL text without transaction context, as it becomes very hard to reconstruct when the read view was created.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Thinking `START TRANSACTION` always creates a snapshot immediately | Missing commits that occur before the first consistent read | Distinguish transaction start from read-view creation; use `WITH CONSISTENT SNAPSHOT` when needed. |
| Thinking every SELECT in RR always sees the latest data | Subsequent reads still use the old snapshot | End the transaction and start a new one if a fresh snapshot is needed. |
| Using `WITH CONSISTENT SNAPSHOT` in READ COMMITTED expecting a fixed snapshot | The option is ignored at unsupported isolation levels | Set RR before starting the transaction. |
| Confusing consistent read with `SELECT ... FOR UPDATE` | Not understanding why locking reads see a newer version | Distinguish snapshot reads from current/locking reads. |
| Using `FOR UPDATE` just to refresh data | Unnecessary locking, increased lock waits and deadlocks | Commit/roll back the old transaction and open a new one. |
| Thinking READ ONLY retains no undo history | Long read transactions still retain a read view | End transactions early and monitor purge/history list. |
| Keeping a transaction open across multiple requests in a connection pool | Prolonged old snapshots, occupied connections | Set clear transaction boundaries and always commit/roll back in finally/try-with-resources. |
| Assuming MyISAM has MVCC snapshots like InnoDB | Results lack matching transaction semantics | Use InnoDB for data requiring consistent reads. |
| Using autocommit and expecting multiple SELECTs to share one snapshot | Each statement has its own transaction/snapshot | Open an explicit transaction when reading multiple queries at the same point. |
| Not checking session isolation in a pool | Some connections run with different isolation levels | Set/reset isolation per connection and check `@@SESSION.transaction_isolation`. |

## 15. Practice Exercises

### Exercise A — Snapshot at First Read

1. Create an InnoDB `snapshot_demo` table and insert balance 100.
2. Session A sets `REPEATABLE READ` and runs `START TRANSACTION` without running SELECT yet.
3. Session B updates balance to 150 and commits.
4. Session A runs its first SELECT and records the result.
5. Session B updates to 200 and commits; Session A runs SELECT again.
6. Explain why Session A sees 150 on both reads.

### Exercise B — WITH CONSISTENT SNAPSHOT

1. Reset balance to 100.
2. Session A runs `START TRANSACTION WITH CONSISTENT SNAPSHOT`.
3. Session B updates balance to 150 and commits.
4. Session A runs SELECT and records the result.
5. Compare with Exercise A to explain why snapshots were created at two different times.

### Exercise C — READ COMMITTED

1. Session A sets isolation level `READ COMMITTED` and opens a transaction.
2. Session A SELECTs balance for the first time.
3. Session B updates balance and commits.
4. Session A runs SELECT a second time.
5. Explain why the second query can see the new commit.

### Exercise D — Consistent Read and Current Read

1. Session A opens a `REPEATABLE READ` transaction and runs a regular SELECT.
2. Session B updates and commits.
3. Session A runs `SELECT ... FOR UPDATE`.
4. Session A runs a regular SELECT again.
5. Compare the visible versions and explain why the two read modes differ.

### Exercise E — Long Transactions and Undo History

1. Open a read-only transaction with a consistent snapshot.
2. In another session, update the same table multiple times and commit.
3. Observe the transaction in `information_schema.innodb_trx`.
4. View `SHOW ENGINE INNODB STATUS` and history list length.
5. Commit the reading transaction and observe purge resuming.

You have completed this lesson when you can identify when a read view is created, predict outcomes between two sessions under REPEATABLE READ/READ COMMITTED, distinguish consistent reads from current reads, and explain the impact of transactions holding snapshots for too long.

## 16. Principles to Remember

- InnoDB uses MVCC and read views to provide consistent nonlocking reads.
- In `REPEATABLE READ`, the read view is normally created at the first consistent read; subsequent consistent reads in the transaction reuse that view.
- `START TRANSACTION` does not necessarily create a snapshot immediately; `START TRANSACTION WITH CONSISTENT SNAPSHOT` creates the snapshot immediately at start under `REPEATABLE READ`.
- `WITH CONSISTENT SNAPSHOT` is ignored at other isolation levels; do not use it to create a fixed snapshot in READ COMMITTED.
- In `READ COMMITTED`, each consistent read creates a new snapshot at the start of the statement.
- `SELECT ... FOR UPDATE`, `FOR SHARE`, and DML use current/locking reads per InnoDB semantics, unlike consistent reads.
- A transaction always sees changes made by itself.
- Autocommit makes each standalone statement end its own transaction; to make multiple SELECTs share a snapshot, open an explicit transaction.
- Consistent snapshots are useful for running multiple queries across InnoDB tables at the same read point.
- Transactions holding snapshots for a long time can retain undo history and slow down purge, even when the transaction is READ ONLY.
- Check actual isolation level, transaction boundaries, `innodb_trx`, and InnoDB status when investigating stale reads.
- End transactions promptly after completing read work to release the read view.

Once you understand when InnoDB creates a read view and distinguish consistent reads from current reads, you can accurately predict the data each transaction sees. This helps you build consistent reports, handle stale-data symptoms, and avoid holding long snapshots that put pressure on undo/purge.
