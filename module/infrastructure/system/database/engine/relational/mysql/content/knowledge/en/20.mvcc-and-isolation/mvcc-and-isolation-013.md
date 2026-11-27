# Verifying Each Isolation Level with Two-Session Execution Schedules

A transaction's isolation level determines which changes from other transactions it can see and which read operations require locks. The surest way to understand this is by tracing an **execution schedule**: which statement runs in session A, which statement runs in session B, when commits or rollbacks occur, and the result of each read.

This lesson belongs to the **MVCC and Isolation Levels** section for MySQL. You will practice all four levels—`READ UNCOMMITTED`, `READ COMMITTED`, `REPEATABLE READ`, and `SERIALIZABLE`—on InnoDB; observe dirty reads, non-repeatable reads, and phantom reads; distinguish consistent reads from locking reads; and recognize anomalies such as lost updates and write skew.

## 1. Preparing the Practice Environment

The examples use MySQL 8.0 or later syntax and the InnoDB storage engine. Open two independent connections to the same schema: call them **session A** and **session B**. Each session has its own transactions and isolation configuration.

Create two tables dedicated to this lab. Run the setup once, outside any open transaction:

```sql
CREATE TABLE isolation_lab_accounts (
    account_id INT PRIMARY KEY,
    balance DECIMAL(12, 2) NOT NULL
) ENGINE = InnoDB;

CREATE TABLE isolation_lab_orders (
    order_id INT PRIMARY KEY,
    customer_id INT NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    KEY idx_customer_order (customer_id, order_id)
) ENGINE = InnoDB;

INSERT INTO isolation_lab_accounts (account_id, balance)
VALUES (1, 100.00);

INSERT INTO isolation_lab_orders (order_id, customer_id, amount)
VALUES (100, 7, 25.00);
```

Both tables have no foreign keys so the experiments stay focused on read and locking behavior. Before each execution schedule, verify the data is in the initial state specified in the corresponding section. Only run reset statements when both sessions have finished their previous transactions.

Check each session's configuration:

```sql
SELECT
    @@SESSION.transaction_isolation AS isolation_level,
    @@SESSION.autocommit AS autocommit_mode;
```

Note both initial values to restore them after the lab. Set the isolation level using `SET SESSION TRANSACTION ISOLATION LEVEL ...` before starting a transaction. This command applies to subsequent transactions in that session and does not change the other session or the entire server.

## 2. Four Isolation Levels in InnoDB

| Isolation Level | Behavior of Ordinary Consistent Reads | What to Observe |
| --- | --- | --- |
| `READ UNCOMMITTED` | Can read uncommitted versions from other transactions. | Dirty reads can occur. |
| `READ COMMITTED` | Each consistent read statement creates a new read view. | Does not read uncommitted data, but two reads in one transaction can differ; phantoms can appear. |
| `REPEATABLE READ` | Consistent reads in the same transaction share the same read view. This is InnoDB's common default. | Repeated consistent read results are stable; phantoms do not appear within the same snapshot. Locking reads still read current data and can use next-key locks. |
| `SERIALIZABLE` | When `autocommit=0`, InnoDB converts ordinary `SELECT` statements into locking reads using shared locks. | Conflicting transactions must wait or encounter deadlocks so execution schedules can be serialized. |

Standard isolation levels are typically described in terms of dirty reads, non-repeatable reads, and phantom reads. InnoDB's implementation of `REPEATABLE READ` has a notable detail: consistent reads use a fixed snapshot, whereas locking reads use the current version and locking mechanisms. Therefore, clearly state the read type when concluding whether a phenomenon occurs.

## 3. READ UNCOMMITTED: Uncommitted Changes Are Visible

A **dirty read** occurs when a transaction sees data that a writing transaction has not yet committed. If the writing transaction rolls back, the data the reading transaction observed never actually became committed data.

Reset balance to `100.00` before running:

```sql
UPDATE isolation_lab_accounts
SET balance = 100.00
WHERE account_id = 1;
```

**Session A** — set the isolation level and start reading:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
START TRANSACTION;

SELECT balance
FROM isolation_lab_accounts
WHERE account_id = 1;
-- Result: 100.00
```

**Session B** — update without committing:

```sql
START TRANSACTION;

UPDATE isolation_lab_accounts
SET balance = 40.00
WHERE account_id = 1;

-- Not COMMITted or ROLLBACKed yet.
```

Return to **session A**:

```sql
SELECT balance
FROM isolation_lab_accounts
WHERE account_id = 1;
-- May see: 40.00, even though session B has not committed.
```

Next, in **session B**:

```sql
ROLLBACK;
```

Read again in **session A**:

```sql
SELECT balance
FROM isolation_lab_accounts
WHERE account_id = 1;
-- Value reverts to: 100.00
```

Session A read a temporary value written by B and then rolled back. That is a dirty read. End session A:

```sql
COMMIT;
```

`READ UNCOMMITTED` is unsuitable for business operations needing confirmed figures, such as balances, inventory, payment statuses, or financial reports. Write statements still must acquire required locks; this level primarily alters the data visibility of consistent reads.

## 4. READ COMMITTED: Each Read Statement Gets a New Snapshot

Under `READ COMMITTED`, a consistent read only sees data committed before the read statement starts. However, a subsequent `SELECT` statement in the same transaction can create a new read view and see commits that occurred between the two reads. This allows **non-repeatable reads** to occur.

Reset balance to `100.00` before running. **Session A**:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT balance
FROM isolation_lab_accounts
WHERE account_id = 1;
-- First read: 100.00
```

**Session B** updates and commits:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

UPDATE isolation_lab_accounts
SET balance = 75.00
WHERE account_id = 1;

COMMIT;
```

**Session A** reads the same row again:

```sql
SELECT balance
FROM isolation_lab_accounts
WHERE account_id = 1;
-- Second read: 75.00

COMMIT;
```

Two read statements in the same transaction A returned two values because B committed in between. This is a non-repeatable read. `READ COMMITTED` prevents dirty reads but does not preserve the same snapshot across the entire transaction.

### Phantom Read Under READ COMMITTED

A **phantom read** occurs when the same query condition returns a different set of rows on a later read because another transaction inserted or deleted matching rows and committed.

Reset the order data for customer 7. Run outside any open transaction:

```sql
DELETE FROM isolation_lab_orders
WHERE customer_id = 7;

INSERT INTO isolation_lab_orders (order_id, customer_id, amount)
VALUES (100, 7, 25.00);
```

**Session A**:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT order_id, amount
FROM isolation_lab_orders
WHERE customer_id = 7
ORDER BY order_id;
-- First time: only order_id = 100.
```

**Session B** inserts a row matching the same condition:

```sql
START TRANSACTION;

INSERT INTO isolation_lab_orders (order_id, customer_id, amount)
VALUES (101, 7, 30.00);

COMMIT;
```

Return to **session A**:

```sql
SELECT order_id, amount
FROM isolation_lab_orders
WHERE customer_id = 7
ORDER BY order_id;
-- Second time: both order_id = 100 and 101.

COMMIT;
```

Row `101` is a phantom for the second read. Same predicate `customer_id = 7`, yet the fresh read view under `READ COMMITTED` sees the newly committed row.

## 5. REPEATABLE READ: Retaining the Snapshot for Consistent Reads

`REPEATABLE READ` is InnoDB's default isolation level in standard MySQL configurations. When a transaction performs its first consistent read, InnoDB creates a read view. Subsequent consistent reads in that transaction continue using this read view.

Reset balance to `100.00`. **Session A**:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance
FROM isolation_lab_accounts
WHERE account_id = 1;
-- First time: 100.00. Read view is created.
```

**Session B** updates and commits:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

UPDATE isolation_lab_accounts
SET balance = 60.00
WHERE account_id = 1;

COMMIT;
```

**Session A** reads again with an ordinary consistent read:

```sql
SELECT balance
FROM isolation_lab_accounts
WHERE account_id = 1;
-- Still sees: 100.00

COMMIT;
```

InnoDB uses undo records to reconstruct the `100.00` version matching A's read view. The committed `60.00` version does not belong to the snapshot A is using. After A finishes its transaction, a new transaction can see `60.00`.

### Phantoms in Consistent Reads Under REPEATABLE READ

Retry the order-insertion schedule from the previous section, but set session A to `REPEATABLE READ`. Before starting, delete order `101` and ensure only row `100` exists for customer 7:

```sql
DELETE FROM isolation_lab_orders
WHERE customer_id = 7;

INSERT INTO isolation_lab_orders (order_id, customer_id, amount)
VALUES (100, 7, 25.00);
```

**Session A**:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT order_id, amount
FROM isolation_lab_orders
WHERE customer_id = 7
ORDER BY order_id;
-- First time: only order_id = 100. Read view is created.
```

**Session B**:

```sql
START TRANSACTION;

INSERT INTO isolation_lab_orders (order_id, customer_id, amount)
VALUES (101, 7, 30.00);

COMMIT;
```

**Session A** reads the same predicate again:

```sql
SELECT order_id, amount
FROM isolation_lab_orders
WHERE customer_id = 7
ORDER BY order_id;
-- Still only sees order_id = 100 in the old read view.

COMMIT;
```

With consistent reads, A does not see phantom `101` because the snapshot does not change. This is a key difference between InnoDB's `REPEATABLE READ` and the minimal description of `REPEATABLE READ` in the SQL standard, which permits phantom reads.

### Locking Reads Do Not Use the Old Snapshot

Do not infer that every read statement under `REPEATABLE READ` returns old data. `SELECT ... FOR UPDATE` and `SELECT ... FOR SHARE` are locking reads (current reads): they read the current version appropriate for locking and coordinating with write operations.

Example in session A:

```sql
START TRANSACTION;

SELECT order_id, amount
FROM isolation_lab_orders
WHERE customer_id = 7
ORDER BY order_id
FOR UPDATE;
```

With an appropriate index, InnoDB can use record locks and gap/next-key locks for the scanned range. An insert into the locked range may have to wait until A commits or rolls back. The actual lock scope depends on the chosen index, query condition, and execution plan; use `EXPLAIN` and inspect locks when verification is needed.

End the transaction in session A before moving to the next experiment:

```sql
COMMIT;
```

## 6. SERIALIZABLE: Coordinating Reads and Writes with Locks

`SERIALIZABLE` requires the execution schedule to be equivalent to a serial ordering of transactions. InnoDB achieves this by applying stricter locking. An easily overlooked detail is that `SELECT` handling depends on autocommit mode.

When `autocommit=0`, InnoDB implicitly converts an ordinary `SELECT` statement into a locking read using a shared lock (`FOR SHARE`). To observe this, configure both sessions before starting the experiment:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE;
SET SESSION autocommit = 0;
```

Reset balance to `100.00` before running. **Session A** executes the read statement:

```sql
SELECT balance
FROM isolation_lab_accounts
WHERE account_id = 1;
-- Reads 100.00 and holds a shared lock in the transaction.
```

In **session B**, run:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE;
SET SESSION autocommit = 0;

UPDATE isolation_lab_accounts
SET balance = 80.00
WHERE account_id = 1;
```

The `UPDATE` in B must wait because A holds a shared lock on the row to be updated. While B is waiting, return to **session A** and run:

```sql
COMMIT;
```

Once A releases the lock, B's `UPDATE` proceeds. When the statement finishes, commit in B:

```sql
COMMIT;
```

Read the result again and restore autocommit mode in both sessions:

```sql
SELECT balance
FROM isolation_lab_accounts
WHERE account_id = 1;

SET SESSION autocommit = 1;
```

Locks force B's write operation to wait for A's read operation to complete. For range queries, range locks (gap/next-key) can also prevent other transactions from inserting phantoms into the protected range. SERIALIZABLE can lower concurrency, increase wait times, and raise deadlock likelihood; applications must handle deadlock errors by retrying transactions appropriately.

When `autocommit=1`, a standalone `SELECT` is its own read transaction and can run as a nonlocking consistent read. Therefore, to verify a multi-statement schedule protected by shared locks as shown above, explicitly set `autocommit=0` and end transactions with `COMMIT` or `ROLLBACK`.

## 7. Summary Table of Phenomena

The following table describes ordinary read schedules in InnoDB. For `REPEATABLE READ`, the phantom conclusion applies to consistent reads using the same read view; locking reads have separate locking rules.

| Phenomenon | READ UNCOMMITTED | READ COMMITTED | REPEATABLE READ (InnoDB) | SERIALIZABLE |
| --- | --- | --- | --- | --- |
| Dirty read | Possible | No | No | No |
| Non-repeatable read between two consistent reads | Possible | Possible | No, same snapshot | No in serialized schedules |
| Phantom between two consistent reads with the same condition | Possible | Possible | No, same snapshot | No in serialized schedules |
| Read may have to wait for write locks | Generally no for plain SELECT | Generally no for plain SELECT | Generally no for plain SELECT | Yes, when autocommit is off and SELECT is converted to a locking read |

Do not use this table to conclude that `REPEATABLE READ` and `SERIALIZABLE` are identical. `REPEATABLE READ` retains a snapshot for consistent reads yet still allows certain write schedules that cannot be ordered serially. `SERIALIZABLE` adds locking constraints to prevent those schedules.

## 8. Lost Update and Write Skew: Issues Requiring Additional Control

### Lost Update from Writing Values Computed from Stale Data

Suppose the initial balance is `100.00`. A reads the balance and computes a new value `110.00`; B also reads `100.00` and computes a new value `90.00`. If both then submit `UPDATE ... SET balance = <value computed in application>`, the later write can overwrite the earlier one. Having `UPDATE` acquire its own lock cannot fix the stale value the application already computed.

Illustrative schedule under `REPEATABLE READ` (reset balance to `100.00` before running):

**Session A**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance
FROM isolation_lab_accounts
WHERE account_id = 1;
-- Application reads 100.00 and computes the new value 110.00.
```

**Session B**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance
FROM isolation_lab_accounts
WHERE account_id = 1;
-- Application also reads 100.00 and computes the new value 90.00.
```

Let A write and commit first:

```sql
UPDATE isolation_lab_accounts
SET balance = 110.00
WHERE account_id = 1;

COMMIT;
```

Then B writes the absolute value computed from the stale read:

```sql
UPDATE isolation_lab_accounts
SET balance = 90.00
WHERE account_id = 1;

COMMIT;
```

The final result is `90.00`; A's update was overwritten. This is an application-layer read-modify-write coordination bug, not a dirty read.

A safer approach for additions/subtractions is performing the arithmetic directly in SQL:

```sql
UPDATE isolation_lab_accounts
SET balance = balance + 10.00
WHERE account_id = 1;
```

Or lock the row before reading and then compute:

```sql
START TRANSACTION;

SELECT balance
FROM isolation_lab_accounts
WHERE account_id = 1
FOR UPDATE;

-- Application computes from the locked value and updates.
UPDATE isolation_lab_accounts
SET balance = 110.00
WHERE account_id = 1;

COMMIT;
```

For data that can be edited by multiple flows, you can also use a version column and `UPDATE ... WHERE version = ?` to detect updates based on an older version.

### Write Skew Under REPEATABLE READ

Suppose two doctors are on call and the business rule requires at least one doctor to always remain on call. Create the lab table:

```sql
CREATE TABLE isolation_lab_doctors (
    doctor_id INT PRIMARY KEY,
    is_on_call BOOLEAN NOT NULL
) ENGINE = InnoDB;

INSERT INTO isolation_lab_doctors (doctor_id, is_on_call)
VALUES (1, TRUE), (2, TRUE);
```

Under `REPEATABLE READ`, start transactions in both sessions before reading. **Session A**:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT COUNT(*) AS doctors_on_call
FROM isolation_lab_doctors
WHERE is_on_call = TRUE;
-- Result: 2.
```

**Session B**:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT COUNT(*) AS doctors_on_call
FROM isolation_lab_doctors
WHERE is_on_call = TRUE;
-- Result: 2.
```

Then A turns doctor 1 off call:

```sql
UPDATE isolation_lab_doctors
SET is_on_call = FALSE
WHERE doctor_id = 1;

COMMIT;
```

B turns doctor 2 off call:

```sql
UPDATE isolation_lab_doctors
SET is_on_call = FALSE
WHERE doctor_id = 2;

COMMIT;
```

The two transactions update two different rows so both can commit, even though each transaction decided based on a snapshot seeing two doctors on call. The outcome is nobody left on call. This is write skew: each individual transaction satisfies the condition it observed, yet combined they violate the global rule.

To protect this rule, you can lock the relevant set of rows before checking:

```sql
START TRANSACTION;

SELECT doctor_id, is_on_call
FROM isolation_lab_doctors
ORDER BY doctor_id
FOR UPDATE;

-- Only turn one doctor off call if at least one person remains on call afterward.
-- Run UPDATE after verifying the locked data.

COMMIT;
```

The second transaction must wait for the lock and then inspect the current state. Another approach is designing a constraint or a representative guard row to turn the cross-row rule into a condition that can be synchronized. `SERIALIZABLE` can also prevent write skew schedules, at the cost of accepting waits and potential deadlocks.

## 9. How to Read an Execution Schedule

When analyzing a concurrency scenario, record in chronological order:

1. Isolation level and `autocommit` of each session.
2. When transactions begin and which first consistent read creates the snapshot (if any).
3. Whether `SELECT` statements are consistent reads or locking/current reads.
4. Which transaction modifies rows, and which transaction commits or rolls back before each read.
5. Actual read results and which locks cause a statement to wait.

Example using `A1`, `B1` for ordered steps:

| Step | Session A | Session B |
| --- | --- | --- |
| 1 | `START TRANSACTION` | |
| 2 | `SELECT balance` → 100 | |
| 3 | | `UPDATE balance = 75` |
| 4 | | `COMMIT` |
| 5 | `SELECT balance` → 75 under READ COMMITTED; 100 under REPEATABLE READ | |
| 6 | `COMMIT` | |

When comparing isolation levels, keep initial data and statement order unchanged; change only the isolation level. If you simultaneously change queries, indexes, autocommit, and commit order, you can no longer isolate the cause from the results.

## 10. Cleaning Up Data and Ending Sessions

After completing the experiments, ensure no transactions remain open. Restore sample data and drop the doctors table if no longer needed:

```sql
UPDATE isolation_lab_accounts
SET balance = 100.00
WHERE account_id = 1;

DELETE FROM isolation_lab_orders
WHERE customer_id = 7;

INSERT INTO isolation_lab_orders (order_id, customer_id, amount)
VALUES (100, 7, 25.00);

DROP TABLE isolation_lab_doctors;
```

If using `autocommit=0`, run `COMMIT` or `ROLLBACK` before running cleanup, then restore:

```sql
-- Replace REPEATABLE READ with the isolation_level noted at the start of the lesson,
-- if the session's initial value differed from this level.
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;

-- Restore the autocommit_mode noted at the start of the lesson; a common value is 1.
SET SESSION autocommit = 1;
```

Perform restoration on both sessions A and B. If `autocommit=0` initially, set it back to `0` after restoring the isolation level. Do not close connections while an unfinished transaction remains open.

## 11. Self-Check Exercises

1. In the `READ UNCOMMITTED` schedule, why can session A read `40.00` and then later read `100.00`?
2. Under `READ COMMITTED`, what causes two `SELECT` statements in the same transaction to see two different values?
3. Why does a consistent read under `REPEATABLE READ` not see a new row committed by session B after A's snapshot was created?
4. Distinguish the results of an ordinary `SELECT` and `SELECT ... FOR UPDATE` inside a `REPEATABLE READ` transaction.
5. Why must `autocommit=0` be set to observe `SERIALIZABLE`'s plain `SELECT` holding shared locks across multiple statements?
6. Describe a write skew schedule and explain why two transactions updating two different rows can still violate a shared business rule.
7. For a balance addition, why is `SET balance = balance + 10` safer than reading the balance into the application and sending back a precomputed absolute value?

When verifying, always distinguish the **snapshot seen by a consistent read** from the **current version that a locking read or write statement must process**. This distinction helps explain each two-session schedule accurately and choose the right isolation level, locks, and update strategy for business workflows.
