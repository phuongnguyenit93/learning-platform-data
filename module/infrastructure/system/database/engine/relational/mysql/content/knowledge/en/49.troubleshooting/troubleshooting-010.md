# Lock Wait Timeout, Deadlock, and Checking Rollback Scope

In the `DATABASE_MYSQL` module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, access control, backup, and handling relational database operations. This lesson focuses on two common locking errors in InnoDB: lock wait timeout and deadlock. The emphasis is on finding the blocking transaction, determining the actual rollback scope, and building safe application-level retries.

Both errors can cause a write statement to fail, yet their rollback behaviors differ. On a deadlock, InnoDB chooses one transaction as the victim and rolls back that entire transaction. On a lock wait timeout, by default InnoDB rolls back only the waiting statement; the transaction may remain open and still hold locks acquired by earlier statements. If an application misunderstands this difference, it can accidentally commit partial work or keep holding locks after throwing an error.

## 1. How InnoDB Locks Protect Data

InnoDB uses locks to coordinate concurrent read/write transactions and enforce data constraints. Locks are typically attached to index records or index ranges, not simply to logical rows.

Key lock types:

| Lock Type | Role | Common Scenario |
|---|---|---|
| Record lock | Locks a single index record. | `UPDATE` a single row by primary key. |
| Gap lock | Locks the gap between index records to prevent inserts into that range when required. | Locking read or range scan at an applicable isolation level. |
| Next-key lock | Combines a record lock and a gap lock over an index range. | Certain range queries under `REPEATABLE READ`. |
| Insert intention lock | Signals intent to insert into a position within a gap; inserts at different positions in the same gap may not block each other. | Concurrent `INSERT`s into an index. |
| Table intention lock | Marks a transaction's intent to acquire record locks on a table. | InnoDB coordinating table-level and record-level locks. |

Plain `SELECT` statements normally use consistent reads and do not lock records the way `SELECT ... FOR UPDATE` does. Locking reads like `SELECT ... FOR UPDATE` or `SELECT ... FOR SHARE`, `UPDATE`, and `DELETE` acquire the locks required for the operation. Lock scope depends on the index used, query predicates, isolation level, and MySQL version.

For example, if an update filters on a column lacking an appropriate index, InnoDB may scan and lock far more records than expected. A proper index for the `WHERE` predicate reduces the number of records examined and usually reduces lock scope, transaction duration, and contention risk.

## 2. Distinguishing Lock Wait Timeout and Deadlock

| Criterion | Lock Wait Timeout | Deadlock |
|---|---|---|
| Condition | A transaction waits for a lock longer than the allowed duration. | A cycle of lock dependencies exists: each transaction waits for a lock held by another, forming a wait cycle. |
| MySQL Error Code | `1205` (`ER_LOCK_WAIT_TIMEOUT`). | `1213` (`ER_LOCK_DEADLOCK`). |
| Default Rollback Scope | Only the timed-out statement. | The entire transaction chosen as the victim. |
| Related Settings | `innodb_lock_wait_timeout`; `innodb_rollback_on_timeout` changes rollback scope. | `innodb_deadlock_detect` controls deadlock detection. |
| Handling Strategy | Find the blocker, check whether the transaction is still open; usually roll back the entire unit of work in the app before considering retry. | Retry the entire victim transaction after addressing the cause; never re-run only the failed statement. |

A lock wait timeout does not prove a deadlock exists. One transaction can legitimately hold a lock while doing long work, causing another transaction to time out without forming a cycle. A deadlock is a cycle; InnoDB detects and breaks the cycle by rolling back one transaction.

## 3. Lock Wait Timeout and Rollback Scope

The `innodb_lock_wait_timeout` variable sets how long InnoDB waits for a record lock before returning a timeout error. The default is typically 50 seconds; check the value on your exact version and environment:

```sql
SHOW GLOBAL VARIABLES LIKE 'innodb_lock_wait_timeout';
SHOW SESSION VARIABLES LIKE 'innodb_lock_wait_timeout';
```

You can set a session-specific timeout:

```sql
SET SESSION innodb_lock_wait_timeout = 10;
```

A short timeout prevents requests from hanging too long, but can also increase transient failures when valid long transactions exist. Do not lower the timeout merely to mask prolonged locking issues; first identify the lock-holding transaction and why it has not finished.

### Default: Rolling Back Only the Timed-Out Statement

Consider a two-statement transaction:

```sql
START TRANSACTION;

UPDATE account
SET balance = balance - 100
WHERE id = 1;

UPDATE account
SET balance = balance + 100
WHERE id = 2;
```

Suppose the second statement waits for a lock and receives error 1205. With the default `innodb_rollback_on_timeout=OFF`, InnoDB rolls back the second statement. The first statement remains part of the open transaction, and the transaction may still hold locks it acquired. If the application catches the error and calls `COMMIT`, the first statement's change can be committed even though the transfer operation is incomplete.

Check the configuration:

```sql
SHOW GLOBAL VARIABLES LIKE 'innodb_rollback_on_timeout';
```

If `innodb_rollback_on_timeout=ON`, InnoDB rolls back the entire transaction on a lock wait timeout. This differs from the default behavior. Never assume one environment's configuration matches another; check runtime values and test against the production configuration.

### Safe Application-Level Handling

For a multi-statement unit of work, the simplest and safest approach is usually rolling back the entire transaction upon receiving error 1205, then retrying the entire business operation only if the error is deemed transient and safe to re-execute.

```java
try {
    connection.setAutoCommit(false);

    debitAccount(connection, sourceId, amount);
    creditAccount(connection, targetId, amount);

    connection.commit();
} catch (SQLException ex) {
    try {
        connection.rollback();
    } catch (SQLException rollbackError) {
        ex.addSuppressed(rollbackError);
    }
    throw ex;
} finally {
    connection.setAutoCommit(true);
}
```

This example illustrates transaction boundaries; production code must manage connections via a pool and handle failures when `setAutoCommit()` or `rollback()` fails. If a connection is no longer reliable after a communication error, do not blindly reuse it.

With Spring `@Transactional`, errors translated into runtime exceptions normally trigger rollback by default if the exception escapes the transactional method. Catching the exception internally and returning normally may prevent the framework from rolling back as expected. Invoke the proper rollback mechanism or let the exception cross the transaction boundary; never swallow error 1205 and proceed to commit the rest.

## 4. Deadlock: Lock Wait Cycle

A deadlock happens when transactions hold locks needed by each other, creating a dependency cycle. For example, two transactions update two accounts in opposite orders.

**Session A:**

```sql
START TRANSACTION;
UPDATE account SET balance = balance - 10 WHERE id = 1;
-- Holds lock on row id=1.
UPDATE account SET balance = balance + 10 WHERE id = 2;
-- Waits for Session B if B holds id=2.
```

**Session B:**

```sql
START TRANSACTION;
UPDATE account SET balance = balance - 20 WHERE id = 2;
-- Holds lock on row id=2.
UPDATE account SET balance = balance + 20 WHERE id = 1;
-- Waits for Session A if A holds id=1.
```

Session A waits for B's lock; Session B waits for A's lock. InnoDB detects the cycle, chooses one transaction as the victim, rolls it back, and returns error 1213 to that client. The surviving transaction can proceed once the locks are released.

InnoDB usually selects the victim based on rollback cost, such as transaction size and number of modified rows. Applications must never assume the newer transaction or a specific session will always be chosen.

Deadlocks do not require two simple `UPDATE` statements. They can arise across multiple tables, secondary indexes, foreign keys, unique indexes, range locks, or concurrent insert/update operations. What matters is the order and scope of locks held by each transaction.

## 5. Finding the Root Cause of a Deadlock

### View the Most Recent Deadlock

```sql
SHOW ENGINE INNODB STATUS\G
```

Locate the `LATEST DETECTED DEADLOCK` section. The report typically shows:

- Participating transactions and start times.
- Active statements or transaction metadata.
- Indexes and records/gaps held by each transaction.
- Locks awaited by each transaction.
- Which transaction was chosen as the victim.

This is a snapshot of the most recent deadlock, so it can be overwritten when another deadlock occurs. Save the report promptly during incident investigation.

To log every deadlock to the error log during an investigation, you can enable:

```sql
SET GLOBAL innodb_print_all_deadlocks = ON;
```

Once enough evidence is collected, consider turning it off again if required by logging policies:

```sql
SET GLOBAL innodb_print_all_deadlocks = OFF;
```

Do not leave verbose deadlock logging enabled indefinitely without considering disk space and log ingestion pipelines. Appropriate privileges are required to modify system variables.

### Inspecting Transactions Waiting for Locks

The `sys.innodb_lock_waits` view helps find waiting and blocking transactions:

```sql
SELECT
    waiting_pid,
    waiting_query,
    waiting_trx_started,
    waiting_trx_age,
    waiting_lock_type,
    waiting_lock_mode,
    blocking_pid,
    blocking_query,
    blocking_trx_started,
    blocking_trx_age,
    blocking_lock_type,
    blocking_lock_mode
FROM sys.innodb_lock_waits
ORDER BY waiting_trx_age DESC;
```

This view describes currently active lock waits. A detected and rolled-back deadlock finishes very quickly, so it may no longer appear in this view by the time a DBA queries it. For deadlocks that already occurred, `SHOW ENGINE INNODB STATUS` and the error log are usually more useful.

To query Performance Schema directly, join `data_lock_waits` with two rows from `data_locks`:

```sql
SELECT
    req.ENGINE_TRANSACTION_ID AS waiting_trx,
    req.OBJECT_SCHEMA,
    req.OBJECT_NAME,
    req.INDEX_NAME AS waiting_index,
    req.LOCK_TYPE AS waiting_lock_type,
    req.LOCK_MODE AS waiting_lock_mode,
    req.LOCK_DATA AS waiting_lock_data,
    blk.ENGINE_TRANSACTION_ID AS blocking_trx,
    blk.INDEX_NAME AS blocking_index,
    blk.LOCK_MODE AS blocking_lock_mode,
    blk.LOCK_DATA AS blocking_lock_data
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS req
    ON req.ENGINE = w.ENGINE
   AND req.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blk
    ON blk.ENGINE = w.ENGINE
   AND blk.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID;
```

To map transactions to connection IDs, join `performance_schema.threads` on `THREAD_ID`. Performance Schema tables reflect locks existing at query time; they do not replace recorded deadlock reports.

## 6. Distinguishing Row Locks from Metadata Locks

Not every message containing the word "lock" comes from InnoDB record locks.

| Symptom | Wait Type | Related Timeout Variable |
|---|---|---|
| `UPDATE` waits for another transaction modifying the same record | InnoDB row/index lock | `innodb_lock_wait_timeout` |
| `SELECT ... FOR UPDATE` waits on record/gap lock | InnoDB row/index lock | `innodb_lock_wait_timeout` |
| `ALTER TABLE` shows `Waiting for table metadata lock` | Metadata lock (MDL) | `lock_wait_timeout` |
| `CREATE INDEX` or `RENAME TABLE` waits on metadata | Metadata lock (MDL) | `lock_wait_timeout` |

Increasing `innodb_lock_wait_timeout` does not resolve DDL waiting on a metadata lock. Conversely, increasing `lock_wait_timeout` does not resolve a transaction waiting on a record lock. Inspect session state and lock type before adjusting timeouts.

## 7. Common Deadlock Causes

### Inconsistent Update Ordering

One transaction updates account A then B, while another updates B then A. This is easy to reproduce and can be reduced by always accessing resources in a deterministic order.

### Queries Locking Too Many Rows

A statement lacking an appropriate index can scan many records and acquire broad lock ranges. Inspect the execution plan and indexes:

```sql
EXPLAIN UPDATE orders
SET status = 'PROCESSING'
WHERE customer_id = 1001
  AND status = 'PENDING';
```

Evaluate access type, chosen key, estimated rows, and filter conditions. If needed, create a composite index aligned with the query predicates after evaluating write cost and index size.

### Range Scans and Gap Locks

Under `REPEATABLE READ`, locking reads or range DML statements may use next-key/gap locks to prevent phantom inserts. Two transactions inserting or updating within the same range can conflict even when targeting different primary key values.

Do not disable gap locks or change isolation levels solely to reduce deadlocks without assessing semantics. `READ COMMITTED` typically reduces certain gap locks, yet alters read consistency and transaction behavior. Test business logic and replication thoroughly before changing it.

### Unique Indexes and Foreign Keys

Unique constraint or foreign key checks can cause transactions to acquire locks on related records. Two transactions manipulating parent/child tables in different orders can also form wait cycles. Standardize operation order across services and keep transactions short.

### Long Transactions and External Operations

Making HTTP calls, sending emails, waiting on user input, or processing large files while a transaction remains open keeps locks held for long periods. Perform external work outside the transaction whenever possible; keep the transaction open only for the database read/write work requiring atomicity.

## 8. Preventing Deadlocks and Reducing Lock Waits

Effective measures typically include:

1. **Keep lock ordering consistent.** When multiple transactions update the same group of resources, always sort by the same primary key or follow the same table order.
2. **Keep transactions short.** Never wait on network calls, users, or external systems inside a transaction.
3. **Use appropriate indexes.** Reduce scanned and locked records; inspect execution plans rather than guessing.
4. **Update in small batches.** Split large batches into moderate chunks and commit at defined business boundaries.
5. **Lock explicitly when needed.** Use `SELECT ... FOR UPDATE` to acquire locks before updating in check-then-modify flows; the query must use an appropriate index.
6. **Access tables in a fixed order.** Services touching multiple tables should follow a uniform order to minimize dependency cycles.
7. **Do not hold transactions during external work.** Prepare data first, open a short transaction, commit, and then execute side effects via an appropriate mechanism.
8. **Monitor and measure.** Track error codes, transaction duration, involved tables/indexes, and retry rates.

No InnoDB system can guarantee zero deadlocks forever. Deadlocks are a natural possibility when concurrent transactions contend for resources; applications must implement proper retry handling even after optimizing lock ordering.

## 9. Safe Transaction Retries

For error 1213, the victim transaction has been completely rolled back. The application must re-run the entire unit of work, not just the last statement. For error 1205, by default only the failing statement is rolled back; the application should explicitly roll back the entire unit of work before retrying, unless a verified statement-level recovery design exists.

A retry policy should include:

- Retrying only recognized transient errors, such as `SQLState`/vendor error codes matching deadlock or lock timeout.
- Capping retry attempts; avoiding infinite loops.
- Using backoff with jitter so colliding transactions do not retry at the exact same instant.
- Starting a fresh transaction and re-reading required state on every retry.
- Ensuring operations are idempotent or protected by idempotency keys/unique constraints to avoid executing side effects twice.
- Logging retry counts and final errors; returning a handleable error upstream if attempts are exhausted.

Pseudocode:

```text
for attempt from 1 to MAX_ATTEMPTS:
    begin a new transaction
    try:
        execute the entire business operation
        commit
        return success
    catch lock timeout or deadlock:
        rollback the whole transaction
        if attempt == MAX_ATTEMPTS:
            return/report failure
        wait for bounded exponential backoff with jitter
```

In plain Java, note that the transaction must be recreated on each loop iteration:

```java
int maxAttempts = 3;

for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);
        try {
            transfer(connection, fromId, toId, amount);
            connection.commit();
            return;
        } catch (SQLException ex) {
            connection.rollback();
            if (!isRetryableLockError(ex) || attempt == maxAttempts) {
                throw ex;
            }
        }
    }

    sleepWithJitter(attempt);
}
```

`isRetryableLockError()` must check vendor error codes and/or `SQLState` per driver; never retry every `SQLException`. `sleepWithJitter()` must be bounded and must not hold an open transaction or connection while waiting. Production code should add exception handling around rollback failures, thread interruption, and resetting connection state per connection pool conventions.

### External Side Effects Outside the Database

Never send emails, invoke payment gateways, or publish irreversible messages inside a retryable transaction. If the transaction rolls back after the side effect already occurred, a retry could trigger the side effect a second time. Use a transactional outbox, idempotency keys, or safely repeatable event handlers.

## 10. NOWAIT and SKIP LOCKED

In MySQL versions supporting `NOWAIT` and `SKIP LOCKED` in locking reads, applications can choose alternative behaviors when a record is already locked:

```sql
SELECT id, status
FROM job_queue
WHERE status = 'READY'
ORDER BY id
LIMIT 10
FOR UPDATE SKIP LOCKED;
```

`SKIP LOCKED` skips records locked by other transactions, fitting worker-queue consumption patterns. It does not produce a complete snapshot and can return a non-contiguous result set; never use it for business queries that must see every matching row.

`NOWAIT` causes a locking read to fail immediately if locks cannot be acquired instead of waiting for timeout. This works well when the application wants to report "currently in use" or move to alternative work. Verify MySQL version support and test under the exact isolation level.

## 11. Practice Lab: Reproducing and Checking Rollback

Run on a test MySQL instance with this table:

```sql
CREATE TABLE account (
    id BIGINT NOT NULL PRIMARY KEY,
    balance DECIMAL(19,2) NOT NULL
) ENGINE=InnoDB;

INSERT INTO account (id, balance)
VALUES (1, 1000.00), (2, 1000.00);
```

### Lab A — Reproducing Lock Wait Timeout

**Session A:**

```sql
START TRANSACTION;
UPDATE account SET balance = balance - 10 WHERE id = 1;
-- Keep transaction open.
```

**Session B:**

```sql
SET SESSION innodb_lock_wait_timeout = 5;
START TRANSACTION;
UPDATE account SET balance = balance + 10 WHERE id = 1;
-- Waits and receives error 1205.
```

After the error, check Session B's transaction status and test `SELECT`/`COMMIT` in the lab environment. With default `innodb_rollback_on_timeout=OFF`, statement B rolls back while transaction B may stay open. Explicitly run `ROLLBACK` to end the transaction. Session A runs `COMMIT` or `ROLLBACK` to release its lock.

Repeat after testing `innodb_rollback_on_timeout=ON` in the lab environment to compare rollback scope. Record config values, errors, final data, and which session still holds an open transaction.

### Lab B — Reproducing a Deadlock

Reset balances if needed. Run Session A and B per Section 4's example, interleaving the two `UPDATE` statements so each holds one row and waits for the other. One session will receive error 1213.

Afterward:

1. Run `SHOW ENGINE INNODB STATUS\G` to read the deadlock report.
2. Check which session rolled back and which survived.
3. Verify final data after the surviving transaction commits.
4. Re-run the exercise with both sessions updating in ascending `id` order.
5. Compare deadlock counts and wait times.

### Lab C — Observing Lock Waits

While Session B is waiting in Lab A, open Session C:

```sql
SELECT * FROM sys.innodb_lock_waits;
SHOW FULL PROCESSLIST;
```

Record `waiting_pid`, `blocking_pid`, transaction age, statements, and involved tables/indexes. Do not kill the blocker immediately; first identify its owner and assess what the transaction is doing.

## 12. Incident Investigation Checklist

When receiving error 1205 or 1213 from an application, record at minimum:

| Information | Purpose |
|---|---|
| Error code, `SQLState`, statement, and timestamp | Distinguish timeout, deadlock, and other SQL errors. |
| Transaction boundaries and autocommit | Determine what partial work might remain open after failure. |
| `innodb_lock_wait_timeout`, `innodb_rollback_on_timeout` | Understand wait duration and timeout rollback behavior. |
| Isolation level | Explain record/gap/next-key locks. |
| Transaction ID, connection ID, start time | Locate waiting and blocking transactions. |
| Involved table, index, and record/range | Identify contention scope and indexes to inspect. |
| Deadlock report / error log | Reconstruct the wait cycle that occurred. |
| Retry count and final outcome | Assess whether retries help or amplify load. |
| External side effects | Check risk of duplicate execution during retries. |

Never increase timeouts or kill sessions before understanding the cause. If the blocker is an abnormal transaction, coordinate with its owner; if deadlocks repeat, fix lock ordering, indexes, or transaction scope. After deploying changes, monitor 1205/1213 rates and transaction durations to confirm effectiveness.

## 13. Common Mistakes and Fixes

| Symptom | Common Cause | Fix |
|---|---|---|
| App gets 1205 yet still commits partial data | Default timeout rolls back only the statement; transaction stays open. | Roll back the entire unit of work before retrying or returning an error. |
| App retries only the last statement after 1213 | Deadlock victim already had its entire transaction rolled back. | Start a new transaction and re-execute the entire business operation. |
| Raising `innodb_lock_wait_timeout` still leaves requests hanging | Blocker transaction is long-lived or waiting on a different lock type. | Identify lock type, blocker, and transaction age; set appropriate timeouts. |
| `ALTER TABLE` waits despite higher `innodb_lock_wait_timeout` | Waiting on a metadata lock. | Check `lock_wait_timeout` and the MDL blocker. |
| Deadlocks persist after adding an index | Lock order, multiple tables, unique/FK checks, or range locks still form a cycle. | Read the deadlock report, standardize access order, and examine actual lock ranges. |
| Retries increase system load | Many clients retry simultaneously without backoff/jitter or retry too often. | Cap retries, add backoff with jitter, and monitor success rates. |
| Email/payment sent twice after retry | Side effect sits inside a retryable transaction. | Use outbox, idempotency keys, or idempotent consumers. |

## 14. Comprehensive Practice Exercise

A money transfer app has two tables: `account` and `transfer_log`. Two concurrent requests transfer money between the same two accounts in opposite directions. Do the following:

1. Create a test schema with appropriate primary keys and indexes.
2. Write a transfer transaction that checks balance, updates both accounts, and inserts a transfer log.
3. Use two sessions to reproduce a deadlock and save the `LATEST DETECTED DEADLOCK` report.
4. Update the code to lock accounts in consistent ID order; re-run the workload and compare deadlocks.
5. Lower `innodb_lock_wait_timeout`, reproduce error 1205, and demonstrate how statement rollback differs from transaction rollback.
6. Enable `innodb_rollback_on_timeout` in the test environment, repeat, and document the change.
7. Write a retry wrapper that retries only recognized 1205/1213 errors, rolls back the whole transaction, and uses backoff with jitter.
8. Simulate a retry after a side effect is emitted; design an outbox or idempotency key so transfers are never recorded twice.
9. Measure transaction duration, lock wait counts, deadlock rates, and final data consistency under concurrency.
10. Write a runbook covering diagnostic queries, rollback conditions, retry policy, and criteria for DBA intervention.

After the exercise, learners should be able to explain why default timeout 1205 differs from deadlock 1213, why open transactions must be checked after timeouts, why retries must replay the entire unit of work, and why optimizing lock order still requires a retry policy. This is the foundation for handling transaction contention in MySQL without corrupting business data.
