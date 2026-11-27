# Deadlocks, lock acquisition order, and how InnoDB chooses the victim transaction

In the **DATABASE_MYSQL** module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, permissions, backups, and operations. When multiple transactions concurrently read and write data, InnoDB uses locks to protect changes. If transactions hold locks needed by other transactions, they may have to wait. When wait relationships form a closed cycle, the system enters a **deadlock**.

InnoDB detects deadlocks and selects one transaction as the victim to roll back, releasing its locks so the remaining transaction can proceed. The application must recognize the error, roll back or clean up transaction state, and retry **the entire business transaction** when appropriate. Designing consistent lock acquisition order, keeping transactions short, and creating proper indexes help reduce deadlock likelihood, though they cannot guarantee complete elimination of deadlocks in a concurrent system.

## 1. What is a deadlock?

A deadlock occurs when two or more transactions form a lock wait cycle: each transaction holds at least one lock needed by another transaction while simultaneously waiting for a lock held by another transaction.

Example with two accounts:

- Transaction A locks account row 1 and needs to lock account 2.
- Transaction B locks account row 2 and needs to lock account 1.
- A must wait for B to release account 2's lock.
- B must wait for A to release account 1's lock.

Neither transaction can proceed unless one is aborted. This is a deadlock, distinct from a situation where one transaction simply waits for another to finish.

### 1.1. Wait-for graph

Transactions can be modeled with a wait-for graph:

- Each node is a transaction.
- Edge A → B means A is waiting for a lock held by B.
- If the graph contains a cycle, a deadlock exists.

Example:

~~~text
Transaction A holds lock on row 1, waits for lock on row 2
Transaction B holds lock on row 2, waits for lock on row 1

A  ───── waits for ─────>  B
^                         |
|                         |
└──────── waits for ──────┘
~~~

A deadlock does not necessarily involve only two transactions. A cycle can include three or more transactions, multiple tables, multiple indexes, and multiple lock types.

### 1.2. Waiting for a lock is not always a deadlock

If A holds a lock and B merely waits for A, while A is not waiting for any lock held by B or a related chain of transactions, the graph has no cycle. B is simply blocked. Once A commits or rolls back, B can proceed.

| Situation | Characteristics | Typical outcome |
|---|---|---|
| Normal lock wait | Transactions wait without forming a cycle | Waits until the lock is released or timeout expires |
| Deadlock | Lock wait cycle exists | InnoDB detects it and rolls back one victim transaction |
| Lock wait timeout | A single wait exceeds configured duration | Waiting statement is usually rolled back by default; transaction may stay open |

Do not conclude there is a deadlock merely because the application notices slow queries or lock waits.

## 2. Creating a deadlock with two sessions

The following example uses InnoDB and two rows in the same table. Open two independent MySQL connections, called Session A and Session B.

### 2.1. Preparing lab data

Run once before opening the two sessions:

~~~sql
CREATE TABLE lab_accounts (
    account_id INT NOT NULL,
    balance DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (account_id)
) ENGINE=InnoDB;

INSERT INTO lab_accounts (account_id, balance)
VALUES
    (1, 1000.00),
    (2, 1000.00);
~~~

### 2.2. Session A locks the first row

In Session A:

~~~sql
START TRANSACTION;

UPDATE lab_accounts
SET balance = balance - 10.00
WHERE account_id = 1;
~~~

Session A holds the required lock on row `account_id = 1` until the transaction ends.

### 2.3. Session B locks the second row

In Session B:

~~~sql
START TRANSACTION;

UPDATE lab_accounts
SET balance = balance - 20.00
WHERE account_id = 2;
~~~

Session B holds the lock on row `account_id = 2`.

### 2.4. Session B waits for the first row's lock

Still in Session B:

~~~sql
UPDATE lab_accounts
SET balance = balance + 20.00
WHERE account_id = 1;
~~~

This statement is blocked because Session A holds the lock on row 1. Session B continues holding the lock on row 2 while waiting.

### 2.5. Session A requests the second row's lock

In Session A:

~~~sql
UPDATE lab_accounts
SET balance = balance + 10.00
WHERE account_id = 2;
~~~

Session A needs the lock on row 2 held by Session B. At this point:

- A holds row 1 and waits for row 2.
- B holds row 2 and waits for row 1.

InnoDB detects the deadlock cycle and rolls back one transaction. The session chosen as the victim receives a deadlock error, typically error 1213 with SQLSTATE 40001. The remaining transaction can proceed once the victim transaction's locks are released.

Do not assume Session A or Session B is always the victim. The choice depends on the state and weight of the transactions at detection time.

### 2.6. Inspecting data after the deadlock

In the surviving session, check:

~~~sql
SELECT account_id, balance
FROM lab_accounts
ORDER BY account_id;
~~~

The victim transaction was completely rolled back. The remaining transaction may still be open; check the result and complete or roll it back depending on your lab goal.

End the remaining transaction if still open:

~~~sql
ROLLBACK;
~~~

Then verify the data returned to its initial values:

~~~sql
SELECT account_id, balance
FROM lab_accounts
ORDER BY account_id;
~~~

**Practice note:** statements must be sent in the right order between the two sessions. After Session B blocks in step 2.4, run step 2.5 in Session A to form the cycle. Running one session completely before opening the other will not produce a deadlock.

## 3. How InnoDB detects deadlocks

InnoDB tracks lock wait relationships. When deadlock detection is enabled, the engine checks for cycles in the wait-for graph. When a deadlock is found, InnoDB picks one transaction to roll back in order to break the cycle and release locks.

The `innodb_deadlock_detect` variable controls detection:

~~~sql
SELECT @@GLOBAL.innodb_deadlock_detect;
~~~

In standard configurations, deadlock detection is enabled. When enabled, InnoDB can detect deadlocks immediately instead of waiting for `innodb_lock_wait_timeout` to expire.

### 3.1. When deadlock detection is disabled

In systems with extreme lock contention, deadlock checks can consume significant CPU. MySQL lets DBAs consider disabling `innodb_deadlock_detect` in specific situations, but when disabled, deadlocks are not detected immediately and transactions must wait for timeouts to be freed.

This is an operational decision requiring measurement and load testing. Never disable deadlock detection just to hide application bugs or avoid fixing lock acquisition order.

### 3.2. Detected deadlocks vs. timeouts

- Deadlock detection finds a cycle and selects a victim to roll back the entire transaction.
- A lock wait timeout merely indicates a wait exceeded the limit; it does not prove a cycle exists.
- If deadlock detection is disabled, a cycle can persist until one transaction hits a timeout.

`innodb_lock_wait_timeout` controls InnoDB's lock wait timeout; it is not a priority mechanism for selecting a victim transaction once a deadlock is detected.

## 4. How does InnoDB choose the victim transaction?

When a deadlock is detected, InnoDB does not simply always abort the later transaction, the youngest transaction, or the first transaction to acquire a lock. The engine tries to select the transaction with the **smaller weight** to roll back, minimizing the amount of work that must be undone.

Transaction weight relates to how much data a transaction has modified and locked, such as the number of rows inserted, updated, deleted, or locked. This is an internal InnoDB decision; applications should never rely on an absolute victim selection rule based on start time or statement order.

### 4.1. Why pick the smaller transaction?

Suppose:

- Transaction A has updated hundreds of records and holds many locks.
- Transaction B has just updated one row.
- The two transactions form a wait cycle.

Rolling back B normally requires far less undo work than rolling back A. InnoDB therefore tends to choose the lighter transaction. However, this is a weight-based tendency, not a promise that the transaction with the fewest SQL statements or latest start time will always be aborted.

### 4.2. Observing active transactions

You can inspect InnoDB transactions:

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_wait_started,
    trx_mysql_thread_id,
    trx_weight,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx;
~~~

These fields help identify running transactions, start times, transaction weights, locked or modified row counts, and current SQL statements if available. Records reflect only currently existing state; the victim transaction may already be gone after the deadlock is resolved.

Do not use `trx_rows_modified` alone to accurately predict the victim. Treat it as investigative support data.

### 4.3. Applications must accept that any transaction can be aborted

A transaction executing critical business logic can still become the victim. Never assume a "more important" transaction or an earlier-started transaction will always survive. Design both sides to retry safely and prevent external side effects before commit succeeds.

## 5. Common causes of deadlocks

### 5.1. Acquiring locks in opposite order

This is a classic pattern:

~~~sql
-- Transaction A
UPDATE accounts SET balance = balance - 10 WHERE account_id = 1;
UPDATE accounts SET balance = balance + 10 WHERE account_id = 2;

-- Transaction B
UPDATE accounts SET balance = balance - 20 WHERE account_id = 2;
UPDATE accounts SET balance = balance + 20 WHERE account_id = 1;
~~~

A locks 1 then 2; B locks 2 then 1. When the two transactions interleave, they can form a cycle.

### 5.2. Same table order but different row order

Deadlocks do not happen only across multiple tables. Two transactions can update the exact same table in different row orders, as in the two-account example above.

### 5.3. Range scans and next-key locks

Under InnoDB's default REPEATABLE READ isolation level, certain locking reads, UPDATEs, or DELETEs over index ranges can acquire next-key locks, combining record locks and gap locks to protect intervals.

Common lock types encountered in investigations:

- A record lock locks a specific index record.
- A gap lock locks an interval between index records, preventing inserts into that interval where applicable.
- A next-key lock combines a record lock with the index gap immediately preceding the record.
- An insert intention lock signals intent to insert a record into an index gap; it may have to wait for locks protecting that gap.

These are InnoDB index-locking concepts. A range query can lock more intervals than a reader might infer from the returned row list, depending on index, isolation level, and execution plan.

Two transactions updating overlapping ranges or inserting into a locked gap can conflict even when they do not target the exact same primary key value.

Example:

~~~sql
START TRANSACTION;

SELECT *
FROM orders
WHERE order_id BETWEEN 100 AND 200
FOR UPDATE;
~~~

This query can lock index records and related intervals depending on isolation level, index, and execution plan. Read actual lock data rather than assuming only returned rows can conflict.

### 5.4. Secondary indexes and multiple access paths

InnoDB manages locks on index records and related clustered index records. An UPDATE may need to modify multiple indexes if it alters indexed columns. Two transactions updating rows in different orders can collide on a secondary index even if the business conditions look independent.

Missing indexes can also cause queries to scan more records than necessary and hold more locks longer, raising the likelihood of intersecting with other transactions.

### 5.5. Foreign keys and unique checks

When inserting or updating data with foreign keys, InnoDB must check the referenced record. When adding a value to a unique index, the engine must check for key conflicts. These verification steps can also acquire locks and create wait edges between transactions.

Consequently, a deadlock can occur during an INSERT or UPDATE even if the application never wrote an explicit `SELECT ... FOR UPDATE`.

### 5.6. Long transactions

The longer a transaction holds locks, the larger the conflict window. Causes of long transactions include:

- Reading or writing too many rows at once.
- Waiting on users or network services while a transaction remains open.
- Running slow queries due to missing indexes.
- Performing multiple unrelated steps inside the same transaction.
- Forgetting to COMMIT or ROLLBACK before returning a connection to the pool.

Shortening transactions reduces lock-holding time and the probability of forming cycles.

## 6. Consistent lock ordering principle

A key solution for reducing deadlocks is standardizing lock acquisition order across all business flows that may touch the same data.

### 6.1. Ascending primary key order

If a transaction needs to update account 1 and account 2, every flow should lock account 1 first and then account 2, regardless of which account is sender or receiver.

A clear way to express this in an application is locking by sorted ascending IDs:

~~~sql
START TRANSACTION;

SELECT account_id, balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;

SELECT account_id, balance
FROM accounts
WHERE account_id = 2
FOR UPDATE;

-- Perform updates after locking in a consistent order.
COMMIT;
~~~

If another transaction also needs these two accounts, it must follow the same order. Once A locks account 1, B waits immediately at account 1 without holding account 2; thus this reverse-order deadlock pattern cannot form.

With a list of many IDs, the application can sort IDs before acquiring locks. If using a single `SELECT WHERE id IN (...) ORDER BY id FOR UPDATE`, check the access path to confirm actual traversal order matches; never assume literal order in an `IN` list determines lock order.

### 6.2. Standardizing order across tables

If a workflow updates `customers`, `orders`, and `inventory`, potentially conflicting flows must acquire locks in the same table order and the same key order within each table.

Example convention:

1. Lock the `customer` row.
2. Lock the `order` row.
3. Lock `inventory` rows in ascending `product_id` order.

Every code path must follow this convention. If one path locks `inventory` before `customer` while another locks `customer` before `inventory`, deadlocks can still happen.

### 6.3. Locking rows by a consistent business criterion

Never let lock order depend on arbitrary input order. For example, transferring money from A to B and transferring from B to A must both lock the account with the smaller ID first. Locking based on "sender" and "receiver" roles reverses order between the two transactions.

### 6.4. Consistent ordering reduces risk; it does not eliminate all deadlocks

Consistent ordering eliminates many deadlocks caused by flows locking the same resources in reverse order. However, deadlocks can still arise from:

- Record locks and gap/next-key locks on overlapping ranges.
- Unique indexes or foreign keys.
- Multiple indexes updated within the same statement.
- Triggers or cascades generating additional operations.
- Different statements having different execution plans and traversal orders.

Therefore, you still need to catch error 1213 and retry transactions safely.

## 7. Indexes and lock scope

Indexes do not just affect query speed; they also affect how many records InnoDB must traverse and lock.

### 7.1. Predicates with suitable indexes

Suppose:

~~~sql
UPDATE orders
SET status = 'PROCESSING'
WHERE customer_id = 100
  AND order_id = 500;
~~~

With a suitable index, InnoDB can locate the target row directly instead of scanning a wide range. Locks stay tighter around the relevant records.

~~~sql
CREATE INDEX ix_orders_customer_order
ON orders (customer_id, order_id);
~~~

This is just an example of column ordering to evaluate; if `order_id` is already the primary key and the predicate already selects one row via the primary key, a new index may be unnecessary. Check existing indexes and `EXPLAIN` before creating one.

### 7.2. Range scans and gap locks

Under REPEATABLE READ, range locking can place next-key locks across an index interval. If a query lacks a suitable index, the scan range can be wide and lock more records than expected.

A suitable index can narrow the access range and shorten lock duration. However, a new index also increases write overhead and adds index records to maintain. Design indexes based on actual queries.

### 7.3. Using EXPLAIN to inspect the access path

~~~sql
EXPLAIN
UPDATE orders
SET status = 'PROCESSING'
WHERE customer_id = 100
  AND order_id = 500;
~~~

Check:

- `key`: chosen index.
- `type` or access method: `const`, `eq_ref`, `ref`, `range`, or `ALL`.
- `rows`: estimated rows to read.
- Which predicates locate records and which are only filtered after reading.

A full-table-scan plan can increase the number of records checked and locks held during writes. Even so, not every `ALL` access type is wrong; evaluate table size and actual row counts.

## 8. Diagnosing deadlocks

When the application receives a deadlock error, gather evidence from MySQL to find the two transactions, held locks, and statements that formed the cycle.

### 8.1. SHOW ENGINE INNODB STATUS

In the MySQL client:

~~~sql
SHOW ENGINE INNODB STATUS\G
~~~

In GUI tools that do not support `\G`, use:

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

Find the `LATEST DETECTED DEADLOCK` section. This section typically describes:

- Transactions involved in the deadlock.
- Status and running statements.
- Locks held by each transaction.
- Locks awaited by each transaction.
- Involved records or indexes.
- The transaction chosen as the victim.

The latest section stores only the most recently recorded deadlock, so a newer deadlock can overwrite older evidence.

### 8.2. Logging all deadlocks to the error log

The `innodb_print_all_deadlocks` variable enables writing details of every deadlock to the MySQL error log:

~~~sql
SELECT @@GLOBAL.innodb_print_all_deadlocks;
~~~

A DBA can enable it during an investigation:

~~~sql
SET GLOBAL innodb_print_all_deadlocks = ON;
~~~

Changing GLOBAL settings requires appropriate privileges and has server-wide operational scope. Changes made with `SET GLOBAL` typically do not persist across server restarts; if needed long-term, the DBA must configure it per deployment policy. Error logs may contain SQL and sensitive data details and must be protected by log access permissions.

### 8.3. Viewing current lock waits with Performance Schema

In MySQL 8.0, `performance_schema.data_locks` and `performance_schema.data_lock_waits` let you observe existing locks and wait relationships:

~~~sql
SELECT
    w.REQUESTING_ENGINE_TRANSACTION_ID AS waiting_trx_id,
    r.OBJECT_SCHEMA,
    r.OBJECT_NAME,
    r.INDEX_NAME,
    r.LOCK_TYPE,
    r.LOCK_MODE AS waiting_lock_mode,
    w.BLOCKING_ENGINE_TRANSACTION_ID AS blocking_trx_id,
    b.LOCK_MODE AS blocking_lock_mode
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS r
  ON r.ENGINE = w.ENGINE
 AND r.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS b
  ON b.ENGINE = w.ENGINE
 AND b.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID;
~~~

This query shows active lock waits at execution time. Deadlocks are usually resolved very quickly after InnoDB selects a victim, so this query may return no rows after the error has already occurred. To investigate a completed deadlock, use `LATEST DETECTED DEADLOCK` or the error log.

### 8.4. Correlating with transaction info

You can inspect active transactions:

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_wait_started,
    trx_mysql_thread_id,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx;
~~~

Join the thread ID with the connection/process list to identify which application or worker owns the session. Appropriate Performance Schema and Information Schema read privileges are required.

### 8.5. Workflow for reading a deadlock report

1. Find the two or more participating transactions.
2. Identify which SQL statements each transaction executed.
3. Read the awaited lock and held locks for each transaction.
4. Identify the involved table, index, record, or index range.
5. Reconstruct the lock acquisition order for each transaction.
6. Pinpoint where lock order reversed or lock scopes intersected.
7. Inspect the indexes and execution plans of the statements.
8. Fix access order, scan scope, or transaction duration.
9. Re-monitor the deadlock rate after deployment.

Do not look only at the statement that received error 1213. That statement is simply where the engine notified the victim; the root cause often lies in the preceding sequence of operations in both transactions.

## 9. Distinguishing deadlock errors from lock wait timeouts

| Property | Deadlock | Lock wait timeout |
|---|---|---|
| Common error code | 1213 | 1205 |
| Common SQLSTATE | 40001 | HY000 |
| Condition | Lock wait cycle exists | A single wait exceeded allowed duration |
| Default InnoDB behavior | Rolls back the entire victim transaction | Rolls back the waiting statement; transaction usually stays open |
| Handling | Retry the entire transaction if safe | Check whether transaction is still open; usually roll back the whole unit of work before retrying |

The `innodb_rollback_on_timeout` variable can make a lock wait timeout roll back the entire transaction:

~~~sql
SELECT @@GLOBAL.innodb_rollback_on_timeout;
~~~

Do not change this variable just to mask issues. Applications must handle both cases cleanly and never assume every 1205 error leaves the transaction in the same state across all configurations.

## 10. Retrying transactions after a deadlock

Deadlocks are recoverable errors in many transactional systems. After InnoDB rolls back the victim, the application can re-run the business operation in a new transaction.

### 10.1. Retry the entire transaction

Recommended workflow:

1. Catch error 1213 / SQLSTATE 40001.
2. End or clean up transaction/connection state per driver requirements.
3. Wait briefly with jitter to reduce the chance of transactions colliding again immediately.
4. Start a new transaction.
5. Re-run all reads, validations, and writes of the business operation.
6. Commit if all steps succeed.
7. Cap the retry count; if errors persist, return an appropriate error to the caller.

Never retry only the final SQL statement that failed. InnoDB already rolled back the entire victim transaction, so earlier changes no longer exist.

### 10.2. Pseudocode

~~~text
for attempt in 1..MAX_RETRIES:
    begin transaction
    try:
        read and lock required rows
        validate business conditions
        execute all required writes
        commit
        return success
    catch error:
        if transaction is still active:
            rollback

        if error is deadlock and attempt < MAX_RETRIES:
            wait with bounded backoff and jitter
            continue

        raise error
~~~

Drivers and frameworks may automatically roll back or mark the transaction invalid after a deadlock. Therefore, the cleanup branch must follow the driver's API; never keep using the old transaction.

### 10.3. Retries must be idempotent

A retry can repeat operations that already produced side effects outside MySQL if the application sent emails, called APIs, or wrote files before the transaction ended. Ensure you:

- Keep external side effects after commit whenever possible.
- Use idempotency keys or unique business identifiers.
- Write events to a transactional outbox inside the same transaction, then dispatch via a worker after commit.
- Never retry infinitely or retry every error type.

Constraint errors such as duplicate keys usually do not resolve on retry; handle them per business semantics instead of treating them like deadlocks.

## 11. Ways to reduce deadlocks

### 11.1. Acquire locks in a consistent order

Standardize table, primary key, and ID ordering across all flows that can update the same resources. This is the most direct fix for reverse-order deadlocks.

### 11.2. Keep transactions short

Include only operations requiring atomicity inside the transaction. Never make HTTP calls, wait for user input, run long reports, or perform unrelated tasks while holding locks.

### 11.3. Create the right indexes for locking predicates

Proper indexes help InnoDB locate target records faster, scan fewer records, and potentially narrow lock scope. Verify with EXPLAIN; avoid redundant indexes that add write overhead and maintenance cost.

### 11.4. Update fewer rows

Split large batches into smaller batches if business rules allow. However, batch splitting alters atomicity boundaries: if the whole batch must succeed or fail together, you cannot split it into independent transactions.

### 11.5. Lock early when required resources are known

If you must read a value before deciding to update, use a locking read like `SELECT ... FOR UPDATE` inside the same transaction to avoid reading and then writing against a modified state. Acquire locks in a consistent order.

### 11.6. Narrow range query scope

Avoid UPDATE/DELETE with overly broad predicates or missing indexes. Use selective predicates, appropriate indexes, and bounded batches. Check next-key/gap locks when deadlock reports indicate conflicts on index intervals.

### 11.7. Evaluate isolation level by data requirements

Isolation level affects lock types and scope, especially for range access in REPEATABLE READ. READ COMMITTED can reduce some gap locks, though it also changes read semantics and does not eliminate all deadlocks. Change isolation only after evaluating consistency requirements and testing potential anomalies.

## 12. Hands-on lab: fixing a deadlock via lock ordering

Continue using the `lab_accounts` table from section 2. If you cleaned it up, recreate it:

~~~sql
CREATE TABLE lab_accounts (
    account_id INT NOT NULL,
    balance DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (account_id)
) ENGINE=InnoDB;

INSERT INTO lab_accounts (account_id, balance)
VALUES (1, 1000.00), (2, 1000.00);
~~~

### 12.1. Step 1 — Reproduce the deadlock

Repeat the sequence from section 2: Session A locks row 1; Session B locks row 2; B requests row 1; A requests row 2. Record which session receives error 1213.

### 12.2. Step 2 — Standardize lock order

Establish the convention that every transaction needing two accounts locks the smaller `account_id` first:

In Session A:

~~~sql
START TRANSACTION;

SELECT account_id, balance
FROM lab_accounts
WHERE account_id = 1
FOR UPDATE;

SELECT account_id, balance
FROM lab_accounts
WHERE account_id = 2
FOR UPDATE;
~~~

Keep transaction A open. Do not run COMMIT yet.

In Session B:

~~~sql
START TRANSACTION;

-- B will wait here because A holds the lock on row 1.
SELECT account_id, balance
FROM lab_accounts
WHERE account_id = 1
FOR UPDATE;
~~~

While B is waiting, switch back to Session A and complete it:

~~~sql
UPDATE lab_accounts
SET balance = balance - 10.00
WHERE account_id = 1;

UPDATE lab_accounts
SET balance = balance + 10.00
WHERE account_id = 2;

COMMIT;
~~~

After A commits, B's waiting SELECT proceeds. B acquires the lock on row 2 in the same order and then applies updates in the reverse business direction:

~~~sql
SELECT account_id, balance
FROM lab_accounts
WHERE account_id = 2
FOR UPDATE;

UPDATE lab_accounts
SET balance = balance - 20.00
WHERE account_id = 2;

UPDATE lab_accounts
SET balance = balance + 20.00
WHERE account_id = 1;

COMMIT;
~~~

Because both transactions lock row 1 and then row 2, B waits before holding row 2. Once A commits, B proceeds in the same order; the cycle from reverse locking on these two rows never forms.

### 12.3. Step 3 — Read the deadlock report

After reproducing the deadlock in step 1:

~~~sql
SHOW ENGINE INNODB STATUS\G
~~~

Locate `LATEST DETECTED DEADLOCK`, and record the transaction IDs, SQL statements, indexes, and waited/held locks. Compare with the lock order executed in the two sessions.

### 12.4. Step 4 — Check active lock waits

While one session is blocked, run the Performance Schema query from section 8.3 from another session with appropriate privileges. Identify the requesting transaction and the blocking transaction.

### 12.5. Step 5 — Verify data and clean up the lab

~~~sql
SELECT account_id, balance
FROM lab_accounts
ORDER BY account_id;

DROP TABLE lab_accounts;
~~~

Only drop the lab table after all transactions in both sessions have been committed or rolled back.

**Expected outcomes:** reproduce a lock wait cycle; distinguish deadlocks from ordinary lock waits; identify the victim transaction; read a deadlock report; fix a two-row deadlock pattern via consistent lock ordering.

## 13. Deadlock incident investigation checklist

When deadlocks appear in a real environment:

1. Collect the error code, SQLSTATE, timestamp, and frequency.
2. Save the deadlock report from InnoDB status or the error log.
3. Identify which transaction was rolled back and which statement received the error.
4. Read the lock modes, indexes, records, or ranges involved.
5. Reconstruct the statement sequence of all transactions in the cycle.
6. Inspect access paths, indexes, and isolation levels.
7. Look for inconsistent lock ordering, overly long transactions, or broad range scans.
8. Fix access order or narrow lock scope.
9. Add bounded full-transaction retries and idempotency.
10. Monitor deadlock rate, lock wait time, and transaction duration after deploying changes.

Occasional deadlocks can be a normal consequence of concurrent load. The operational goal is keeping the rate within acceptable bounds, ensuring applications recover properly, and resolving recurring deadlock patterns that have clear root causes.

## 14. Common design mistakes

| Practice | Risk | Fix |
|---|---|---|
| Each flow locks rows in arbitrary input order | Two flows can lock the same rows in opposite directions | Sort IDs and use a shared lock order |
| Retrying only the SQL statement that got error 1213 | The victim transaction was completely rolled back | Retry the entire transaction from the start |
| Assuming the old transaction remains open after a deadlock | InnoDB already rolled back the victim transaction | Start a new transaction |
| Treating every lock wait as a deadlock | Misdiagnosis and unnecessary config changes | Check for a cycle or deadlock report |
| Increasing innodb_lock_wait_timeout to fix deadlocks | Timeout does not fix lock order; waits may simply grow longer | Fix lock order and access paths |
| Dropping indexes to save write cost without assessing locks | Queries can scan and lock far more records | Measure trade-offs with EXPLAIN and workload testing |
| Keeping transactions open during external service calls | Locks persist longer, raising deadlock probability | Move side effects after commit or use an outbox |
| Lowering isolation level just to eliminate deadlocks | Can introduce new data anomalies | Choose isolation based on business semantics |
| Assuming InnoDB always aborts the transaction with fewest SQL statements | Victim is based on internal weight, not simple statement count | Design every transaction to tolerate abort and safe retry |
| Retrying infinitely | Can create retry storms and saturate the system | Cap retries, apply backoff, and track error rates |

## 15. Key principles to remember

- A deadlock is a lock wait cycle; one transaction merely waiting on another is not necessarily a deadlock.
- InnoDB detects deadlocks and rolls back the entire transaction selected as the victim.
- InnoDB tends to pick the lighter-weight transaction to minimize rollback cost; never rely on transaction age or arrival order to guess the victim.
- Applications must handle error 1213 / SQLSTATE 40001 and retry the entire transaction in a fresh transaction when safe to retry.
- Lock wait timeout is normally error 1205; by default only the waiting statement is rolled back, though `innodb_rollback_on_timeout` can change that scope.
- Acquiring locks in the same table and primary key order across all flows reduces reverse-order deadlocks.
- Proper indexes narrow scan and lock scope; range scans under REPEATABLE READ can involve gap locks and next-key locks.
- Foreign keys, unique indexes, triggers, and secondary indexes can also participate in lock chains.
- Short transactions, sensible batches, and avoiding network waits inside transactions reduce lock-holding duration.
- `SHOW ENGINE INNODB STATUS` shows the latest deadlock; `innodb_print_all_deadlocks` can log every deadlock to the error log.
- Performance Schema `data_locks` and `data_lock_waits` help inspect active lock waits; resolved deadlocks may no longer appear in these tables.
- Consistent lock ordering reduces risk without eliminating all deadlocks; retries and idempotency remain necessary.

Deadlocks must be addressed on both sides: transaction design to minimize contention, and application logic to recover when InnoDB selects a transaction as the victim. By understanding wait-for cycles, transaction weight, indexes, and lock acquisition order, you can interpret the evidence accurately and fix root causes instead of merely raising timeouts or retrying a single isolated statement.
