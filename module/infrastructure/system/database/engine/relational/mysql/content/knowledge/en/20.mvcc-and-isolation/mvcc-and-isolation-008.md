# Dirty Read, Nonrepeatable Read, Phantom, and Write Skew

When multiple connections read and write data concurrently, what each transaction sees depends on the *isolation level* and how the storage engine performs reads. A transaction may read uncommitted changes from another transaction, re-read the same row and receive a new value, see additional rows matching a search condition, or together with another transaction violate a business rule even though each transaction individually checked a valid condition.

Four phenomena to recognize are **dirty read**, **nonrepeatable read**, **phantom read**, and **write skew**. MySQL InnoDB uses MVCC (Multi-Version Concurrency Control) combined with locking to control data visibility and protect write operations. The isolation level governs how read views are created, how locking reads behave, and which conflicts are prevented.

This lesson belongs to the `DATABASE_MYSQL` module, focusing on table design, data types, keys, SQL queries, indexes, transactions, concurrency control, reading execution plans, and relational database operations. The goal is to understand these anomalies via two-transaction schedules, know InnoDB's default isolation level, and choose protection mechanisms matching business invariants.

After this lesson, you will be able to:

- Define dirty read, nonrepeatable read, phantom read, and write skew.
- Distinguish consistent reads (snapshot reads) from locking/current reads.
- Explain how MVCC creates read views and how InnoDB uses undo versions.
- Compare MySQL's four isolation levels.
- Predict outcomes when two sessions interleave SELECT, UPDATE, INSERT, COMMIT, and ROLLBACK.
- Understand why InnoDB REPEATABLE READ prevents phantoms in consistent reads yet is not equivalent to SERIALIZABLE.
- Recognize write skew and protect multi-row invariants with locks, constraints, or SERIALIZABLE.
- Choose strategies for handling deadlocks, lock waits, and transaction retries.

## 1. Four Phenomena to Distinguish

| Phenomenon | What Happens | Short Example |
| --- | --- | --- |
| Dirty read | Reading another transaction's uncommitted change | A deducts funds without committing; B reads the new balance; A rolls back |
| Nonrepeatable read | Reading the same row twice in one transaction and getting different values | A reads balance 500; B updates it to 400 and commits; A reads again and sees 400 |
| Phantom read | Rerunning the same predicate and seeing matching rows added/removed | A finds orders from 100 to 200; B inserts order 150 and commits; A reruns and sees the new row |
| Write skew | Two transactions read the same state and update different rows, violating a shared invariant | Two doctors both see another doctor on call; each turns off their own on-call status; ultimately nobody is on call |

The first three phenomena describe types of changes in read data. Write skew is an anomaly at the multi-row business-rule level; it can occur even when no two transactions overwrite the same row.

## 2. MVCC and the Two Read Modes in InnoDB

InnoDB uses MVCC to allow consistent reads to read a data version matching their read view without locking every row being read. When a transaction updates a row, InnoDB creates a new version and keeps the undo information needed to reconstruct older versions for active read views that still require them.

Two important read modes:

### 2.1. Consistent Read — Reading by Snapshot

An ordinary `SELECT` statement, without `FOR UPDATE` or `FOR SHARE`, is typically a consistent nonlocking read for InnoDB tables.

- Under `REPEATABLE READ`, consistent reads within the same transaction share the read view established at the first consistent read. You can create the read view immediately upon start using `START TRANSACTION WITH CONSISTENT SNAPSHOT`.
- Under `READ COMMITTED`, each consistent read creates a new read view at the start of the statement. Therefore, two SELECT statements in the same transaction can see different commits.
- Under `READ UNCOMMITTED`, an ordinary consistent read can read uncommitted versions; there is no stable snapshot as in RR/RC.

A snapshot is not a physical copy of the entire table. InnoDB uses the current version and undo records to return values matching the read view.

### 2.2. Locking Read — Reading Current State and Locking Rows

Statements such as:

```sql
SELECT ... FOR UPDATE;
SELECT ... FOR SHARE;
```

are locking reads. They read the latest version matching the condition and place locks according to isolation level, index, and access path rules. This is a current read, distinct from a consistent snapshot read.

- `FOR UPDATE` acquires the exclusive lock needed for a subsequent update operation.
- `FOR SHARE` acquires a shared lock, allowing other transactions to read/shared-lock while preventing conflicting updates until the transaction ends.
- In InnoDB `REPEATABLE READ`, locking range reads can use next-key locks (record lock combined with gap lock) to block inserts into the locked range.

A transaction under RR can read an old snapshot with a plain SELECT, and then use `SELECT ... FOR UPDATE` and see a newer version. Do not mix the two read modes without understanding the difference.

## 3. MySQL's Four Isolation Levels

MySQL supports four standard isolation levels. For InnoDB, the default level is `REPEATABLE READ`.

| Isolation Level | Dirty Read | Nonrepeatable Read | Phantom in Consistent Reads | Key InnoDB Characteristics |
| --- | --- | --- | --- | --- |
| `READ UNCOMMITTED` | Possible | Possible | Possible | SELECT can see uncommitted data |
| `READ COMMITTED` | No | Possible | Possible | Each consistent SELECT gets a fresh snapshot; gap locking mostly disabled |
| `REPEATABLE READ` | No | No across consistent reads in the same transaction | No across consistent reads in the same snapshot | InnoDB default; locking range reads use next-key locking |
| `SERIALIZABLE` | No | No | No in serialized execution schedules | Increases locking and lowers concurrency; deadlocks can occur |

This table describes phenomena under ordinary reads and InnoDB mechanisms. Locking reads, DML, and lock types have their own rules. InnoDB's `REPEATABLE READ` provides stronger phantom protection than the simplified descriptions of many other systems, yet it still does not mean every schedule is equivalent to SERIALIZABLE; write skew is a key example.

## 4. Creating Lab Data for Two Sessions

Run the setup once before opening two connections A and B. Use dedicated lab tables; do not test these operations on production data.

```sql
DROP TABLE IF EXISTS mvcc_demo_orders;
DROP TABLE IF EXISTS mvcc_demo_accounts;

CREATE TABLE mvcc_demo_accounts (
    account_id INT UNSIGNED NOT NULL,
    balance DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (account_id)
) ENGINE = InnoDB;

INSERT INTO mvcc_demo_accounts (account_id, balance) VALUES
(1, 500.00),
(2, 800.00);

CREATE TABLE mvcc_demo_orders (
    order_id BIGINT UNSIGNED NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_mvcc_demo_orders_amount (amount)
) ENGINE = InnoDB;

INSERT INTO mvcc_demo_orders (order_id, amount) VALUES
(101, 90.00),
(102, 120.00),
(103, 180.00),
(104, 250.00);
```

Verify engine and data:

```sql
SELECT TABLE_NAME, ENGINE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('mvcc_demo_accounts', 'mvcc_demo_orders');

SELECT * FROM mvcc_demo_accounts ORDER BY account_id;
SELECT * FROM mvcc_demo_orders ORDER BY order_id;
```

Ensure both tables use InnoDB. In the following sections, "Session A" and "Session B" are two separate physical connections to the same schema. Do not open two tabs sharing one connection and treat them as two sessions.

## 5. Dirty Read — Reading Uncommitted Data

A dirty read occurs when a transaction sees changes from another transaction before those changes are committed. If the writing transaction rolls back, the data the reading transaction read earlier never became committed data.

In InnoDB, dirty reads can happen at `READ UNCOMMITTED`. `READ COMMITTED`, `REPEATABLE READ`, and `SERIALIZABLE` prevent consistent SELECTs from reading uncommitted changes.

### 5.1. Two-Session Schedule

Set both sessions to `READ UNCOMMITTED` before starting transactions.

**Session A:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
START TRANSACTION;

UPDATE mvcc_demo_accounts
SET balance = 100.00
WHERE account_id = 1;

-- Not COMMITted or ROLLBACKed yet.
```

**Session B:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
START TRANSACTION;

SELECT account_id, balance
FROM mvcc_demo_accounts
WHERE account_id = 1;
```

Session B can read `balance = 100.00` even though Session A has not committed. This is a dirty read.

Continue in **Session A**:

```sql
ROLLBACK;
```

Session A discards the change. If Session B reads again while still under `READ UNCOMMITTED`, it can see the rolled-back value of 500.00. What B read previously was a temporary, uncommitted value.

Finish **Session B**:

```sql
COMMIT;
```

### 5.2. Why Are Dirty Reads Dangerous?

An application might use uncommitted data to decide to ship goods, send notifications, calculate quotas, or write a result to another system. If the source transaction rolls back, external actions were based on data that does not exist in the database.

For ordinary business data, avoid `READ UNCOMMITTED`. This level is rarely suitable for reports requiring reliability.

## 6. Nonrepeatable Read — Same Row, Changing Value

A nonrepeatable read occurs when a transaction reads a row, another transaction updates and commits that row, and then the first transaction re-reads the same row and receives the new value.

### 6.1. Reproducing Under READ COMMITTED

Set both sessions to `READ COMMITTED`.

**Session A:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT balance
FROM mvcc_demo_accounts
WHERE account_id = 1;
-- Initial result: 500.00
```

**Session B:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

UPDATE mvcc_demo_accounts
SET balance = 400.00
WHERE account_id = 1;

COMMIT;
```

Switch back to **Session A**:

```sql
SELECT balance
FROM mvcc_demo_accounts
WHERE account_id = 1;
-- New result: 400.00

COMMIT;
```

Under READ COMMITTED, each consistent SELECT creates a new read view. A's second SELECT starts after B committed and therefore sees 400.00. A previously read row is not guaranteed to retain the same value throughout the transaction.

### 6.2. Same Schedule Under REPEATABLE READ

Restore the balance before the test with a statement run outside a transaction, then set A to RR and B to RC or RR:

```sql
UPDATE mvcc_demo_accounts
SET balance = 500.00
WHERE account_id = 1;
```

**Session A:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT balance
FROM mvcc_demo_accounts
WHERE account_id = 1;
-- Suppose the result is 500.00; the read view is established.
```

**Session B:**

```sql
START TRANSACTION;

UPDATE mvcc_demo_accounts
SET balance = 350.00
WHERE account_id = 1;

COMMIT;
```

Switch back to **Session A**:

```sql
SELECT balance
FROM mvcc_demo_accounts
WHERE account_id = 1;
-- Consistent read still returns 500.00 in A's snapshot.

COMMIT;
```

Under InnoDB RR, consistent reads within a transaction share the same read view. B committed the value 350.00, but A's snapshot still sees version 500.00.

## 7. Consistent Read Differs from Locking/Current Read

A critical point: RR does not mean every type of SELECT in the transaction always returns the same version.

Inside the same transaction A under RR:

```sql
-- Consistent read: reads from snapshot
SELECT balance
FROM mvcc_demo_accounts
WHERE account_id = 1;

-- Locking read: reads the latest matching version and locks the row
SELECT balance
FROM mvcc_demo_accounts
WHERE account_id = 1
FOR UPDATE;
```

If another transaction committed an update after A's read view was created, a plain SELECT can continue returning the old snapshot version, while `FOR UPDATE` can return the latest version. A locking read is a current read, not a consistent snapshot read.

This also relates to `UPDATE` and `DELETE`: they must locate the current row and lock the appropriate row, not simply modify an old version in a snapshot. When a transaction mixes snapshot reads and locking reads/DML, observed results can span different logical points in time. Design read/write flows clearly, especially when an update decision is based on a condition just read.

If you want to lock the row before deciding on an update:

```sql
START TRANSACTION;

SELECT balance
FROM mvcc_demo_accounts
WHERE account_id = 1
FOR UPDATE;

-- Check condition on the locked value, then UPDATE.
UPDATE mvcc_demo_accounts
SET balance = balance - 50.00
WHERE account_id = 1
  AND balance >= 50.00;

COMMIT;
```

Locking the row prevents another transaction from updating the same row between the decision and the write. You still must check the update count and handle deadlocks/timeouts.

## 8. Phantom Read — New Rows Appearing That Match a Predicate

A phantom read is not the same row changing value. It occurs when a transaction reruns a query with a set predicate and sees the matching set of rows has changed—for instance, a new row was inserted or an existing row was updated to begin matching the predicate.

### 8.1. Reproducing a Phantom Under READ COMMITTED

If rerunning the exercise, delete the row added from the previous run before opening transactions:

```sql
DELETE FROM mvcc_demo_orders
WHERE order_id = 105;
```

**Session A:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT order_id, amount
FROM mvcc_demo_orders
WHERE amount BETWEEN 100.00 AND 200.00
ORDER BY amount, order_id;
-- Initially: orders 102 and 103.
```

**Session B:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

INSERT INTO mvcc_demo_orders (order_id, amount)
VALUES (105, 150.00);

COMMIT;
```

Switch back to **Session A**:

```sql
SELECT order_id, amount
FROM mvcc_demo_orders
WHERE amount BETWEEN 100.00 AND 200.00
ORDER BY amount, order_id;
-- This time order 105 is also included.

COMMIT;
```

Under RC, the second SELECT creates a new read view and therefore sees committed row 105. This is a phantom row for the predicate `amount BETWEEN 100 AND 200`.

### 8.2. Consistent Reads Under REPEATABLE READ

Under InnoDB RR, if A uses two plain SELECTs in the same transaction and the read view was created on the first statement, the second statement still uses that snapshot. Row 105 committed by B after the snapshot time will not appear in the second consistent read. Thus, InnoDB RR prevents phantoms across a series of consistent reads sharing the same read view.

This does not mean inserts into that range are impossible during all operations. Locking reads and DML have separate current-read and locking rules.

### 8.3. Next-Key Locks Protect Locking Range Reads

Under InnoDB RR, a range-based locking read can acquire next-key locks on the index. A next-key lock combines a record lock with a gap lock before the record, preventing other transactions from inserting values into the protected range.

Example in **Session A**:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT order_id, amount
FROM mvcc_demo_orders
WHERE amount BETWEEN 100.00 AND 200.00
FOR UPDATE;
```

With the `idx_mvcc_demo_orders_amount` index, InnoDB can lock the index records and gaps needed for the condition. If **Session B** tries to insert a row with `amount = 150.00`, the INSERT may have to wait for A to finish its transaction.

After A runs:

```sql
COMMIT;
```

B can then proceed with the insert if no other conflicts remain.

The actual lock range depends on the chosen index, predicate, access path, and isolation level. Use `EXPLAIN` to understand the access path; do not assume a range query always locks only the exact displayed rows.

Under READ COMMITTED, InnoDB largely disables gap locking for ordinary searches/index scans (exceptions include foreign key and duplicate-key checks). Consequently, locking reads under RC generally do not prevent phantom inserts the way RR next-key locking does.

## 9. Write Skew — Two Transactions Write Different Rows Yet Break a Shared Invariant

Write skew is a subtler anomaly than the three classic read phenomena. Two transactions read the same consistent state, each decides to update its own distinct row, and the updated rows do not directly conflict. Both can commit, yet the overall state violates a business rule.

Example: a team has two doctors on call. The rule is that at least one doctor must always remain on call. Each transaction wants to take one doctor off call and proceeds only if it sees at least two doctors currently on call.

Create the lab table:

```sql
DROP TABLE IF EXISTS mvcc_demo_doctors;

CREATE TABLE mvcc_demo_doctors (
    doctor_id INT UNSIGNED NOT NULL,
    doctor_name VARCHAR(100) NOT NULL,
    on_call TINYINT(1) NOT NULL,
    PRIMARY KEY (doctor_id),
    KEY idx_mvcc_demo_doctors_on_call (on_call)
) ENGINE = InnoDB;

INSERT INTO mvcc_demo_doctors (doctor_id, doctor_name, on_call) VALUES
(1, 'An', 1),
(2, 'Binh', 1);
```

### 9.1. Schedule Causing Write Skew Under REPEATABLE READ

Set both A and B to RR.

**Session A:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT COUNT(*) AS doctors_on_call
FROM mvcc_demo_doctors
WHERE on_call = 1;
-- Result: 2. A decides doctor 1 can go off call.
```

**Session B:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT COUNT(*) AS doctors_on_call
FROM mvcc_demo_doctors
WHERE on_call = 1;
-- Also sees 2 in B's snapshot.
```

Then A updates row 1:

```sql
UPDATE mvcc_demo_doctors
SET on_call = 0
WHERE doctor_id = 1;

COMMIT;
```

B updates row 2:

```sql
UPDATE mvcc_demo_doctors
SET on_call = 0
WHERE doctor_id = 2;

COMMIT;
```

The two transactions write two different primary keys, so they do not necessarily wait for each other. Both can commit. Final result:

```sql
SELECT doctor_id, doctor_name, on_call
FROM mvcc_demo_doctors
ORDER BY doctor_id;
```

| doctor_id | doctor_name | on_call |
| ---: | --- | ---: |
| 1 | An | 0 |
| 2 | Binh | 0 |

The invariant "always have at least one doctor on call" was violated. There was no dirty read; both transactions read committed data in their snapshots. There was no nonrepeatable read across consistent reads; each transaction only read once. The issue is two independent decisions based on the same aggregate condition writing different rows.

### 9.2. Why Doesn't REPEATABLE READ Automatically Prevent Write Skew?

RR guarantees consistent reads within a transaction use the same snapshot. It does not automatically lock all rows or predicates that the application read. An ordinary `SELECT COUNT(*)` does not lock the on-call doctors to preserve the invariant until the transaction ends.

When A and B update different rows, InnoDB can let both proceed because there is no write conflict on the same record. MVCC improves concurrency, but snapshot repeatability does not equate to serializing all business decisions.

## 10. How to Prevent Write Skew

Choose protection based on the invariant. If the rule can be expressed via a row-level constraint or unique key, prefer constraints. For invariants spanning multiple rows, create a synchronization point on which competing transactions contend.

### 10.1. Locking Related Rows with SELECT FOR UPDATE

Before deciding to take a doctor off call, lock the rows currently on call:

```sql
START TRANSACTION;

SELECT doctor_id
FROM mvcc_demo_doctors
WHERE on_call = 1
FOR UPDATE;

-- Application counts the returned rows.
-- Only update one doctor if at least one person remains on call afterward.

UPDATE mvcc_demo_doctors
SET on_call = 0
WHERE doctor_id = 1
  AND on_call = 1;

COMMIT;
```

If two transactions both lock the set of on-call doctors, one transaction must wait. After acquiring the lock, the transaction must re-evaluate the condition using locking/current reads and current data. Do not rely on an older snapshot created before waiting for the lock.

The outcome and lock scope depend on indexes and predicates. Inspect `EXPLAIN` and test real concurrent schedules.

### 10.2. Using a Guard Row to Serialize Decisions

An easily controllable approach is creating a guard row for each on-call group. Every transaction modifying the on-call schedule must lock the same guard row before checking and updating.

```sql
DROP TABLE IF EXISTS mvcc_demo_schedule_guard;

CREATE TABLE mvcc_demo_schedule_guard (
    team_id INT UNSIGNED NOT NULL,
    guard_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (team_id)
) ENGINE = InnoDB;

INSERT INTO mvcc_demo_schedule_guard (team_id) VALUES (1);
```

Transaction pattern:

```sql
START TRANSACTION;

SELECT team_id
FROM mvcc_demo_schedule_guard
WHERE team_id = 1
FOR UPDATE;

-- After holding the guard lock, use a current read to check the current state.
SELECT doctor_id
FROM mvcc_demo_doctors
WHERE on_call = 1
FOR UPDATE;

-- Application checks the on-call count and updates only if the invariant still holds.
-- For example, update a specific doctor after verifying.

COMMIT;
```

A guard row turns decisions on the same team into a serial sequence. Every code path capable of altering the invariant must follow the same protocol; a write path bypassing the guard can still break the rule.

Key point: after waiting for the guard lock, use a locking/current read to inspect current data. If the transaction had already created an old RR snapshot before waiting, a subsequent plain SELECT could still read the old snapshot.

### 10.3. Using SERIALIZABLE When Appropriate

`SERIALIZABLE` requires schedules to be equivalent to a serial order. With InnoDB, this level increases locking; inside explicit transactions, ordinary SELECTs are treated as shared locking reads under MySQL's rules. This can prevent write skew, but reduces concurrency and raises deadlock/lock-wait likelihood.

Only use SERIALIZABLE for transactions or workloads genuinely needing stronger guarantees, after measuring contention. Even when using this level, applications must still handle deadlocks and retry transactions properly.

## 11. Setting Isolation Levels in MySQL

Check the current isolation level:

```sql
SELECT
    @@session.transaction_isolation AS session_isolation,
    @@global.transaction_isolation AS global_isolation;
```

Set for the next transaction on the current connection:

```sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;
-- Operations belonging to this transaction.
COMMIT;
```

Set the default for subsequent transactions in the session:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
```

Set the default for new connections:

```sql
SET GLOBAL TRANSACTION ISOLATION LEVEL REPEATABLE READ;
```

`SET GLOBAL` requires appropriate administrative privileges and does not alter the isolation level of existing sessions. Set the isolation level before starting a transaction; do not treat it as an option that can be changed mid-transaction.

In MySQL 8.x, the system variable name is `transaction_isolation`. Some older versions used `tx_isolation`; check the deployment version before running multi-version configuration scripts.

### 11.1. Creating a Snapshot Immediately at Start

Under RR, you can request a consistent snapshot right at start time:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT;
```

Without `WITH CONSISTENT SNAPSHOT`, the read view for consistent reads under RR is usually established when the transaction performs its first consistent read. The snapshot syntax is useful when you want to pin the exact snapshot start time for a long-running read transaction.

`WITH CONSISTENT SNAPSHOT` does not turn locking reads into snapshot reads; `FOR UPDATE` and `FOR SHARE` remain locking/current reads. This option is meaningful for InnoDB under REPEATABLE READ; at other isolation levels it does not create the same snapshot guarantee.

## 12. Reading the Comparison Table by Scenario

| Isolation Level | How Consistent SELECT Sees Data | When Appropriate |
| --- | --- | --- |
| READ UNCOMMITTED | Can read uncommitted versions | Rarely suitable for business operations needing reliability |
| READ COMMITTED | Each SELECT takes a fresh snapshot | Reports/applications tolerating data changing between read statements |
| REPEATABLE READ | Consistent SELECTs share the same snapshot within the transaction | InnoDB default; repeated consistent reads |
| SERIALIZABLE | Increases locking so schedules are serial-equivalent | Complex invariants needing strong guarantees and tolerating lower concurrency |

No isolation level completely replaces data design and constraints. Identify which anomalies can break the business logic and then choose specific mechanisms.

## 13. Deadlocks, Lock Waits, and Retries

Locks prevent conflicts, yet can create deadlocks. For example, A locks row 1 and waits for row 2; B locks row 2 and waits for row 1. InnoDB detects the wait cycle and rolls back one transaction as the victim.

Handling principles:

- Keep transactions short and lock as few rows as possible.
- Update multiple rows in the same locking order across all code paths.
- Create suitable indexes to avoid scanning and locking excessive records/gaps.
- Catch deadlock errors and retry the entire transaction with bounded attempts and backoff.
- On a lock wait timeout, do not assume the entire transaction rolled back; proactively roll back if business logic cannot proceed.
- Ensure retryable operations are idempotent or have duplicate-execution guards.

You can inspect recent deadlocks with:

```sql
SHOW ENGINE INNODB STATUS;
```

The `LATEST DETECTED DEADLOCK` section usually contains details on the involved transactions, statements, and locks. In environments with frequent deadlocks, collect logs and observe frequency rather than merely raising timeouts.

## 14. Inspecting Access Paths and Indexes

Isolation levels affect not only data visibility; they also affect the lock types acquired and lock scope. Indexes can narrow the range of records/gaps needing checks.

Range query example:

```sql
EXPLAIN
SELECT order_id, amount
FROM mvcc_demo_orders
WHERE amount BETWEEN 100.00 AND 200.00
FOR UPDATE;
```

Check:

- Whether index `idx_mvcc_demo_orders_amount` is selected.
- Access type and estimated row count.
- Whether the predicate uses a range scan or must scan broadly.
- The isolation level active for the session.
- Lock types and index ranges that may be locked along the access path.

`EXPLAIN` shows the access plan, not a complete list of runtime locks. To investigate waiting locks, inspect `performance_schema.data_locks`, `performance_schema.data_lock_waits`, and related metadata tables if enabled and permitted.

## 15. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using READ UNCOMMITTED for business data | Reading data that may roll back | Use RC/RR appropriately |
| Thinking READ COMMITTED keeps the same snapshot throughout the transaction | Re-reads can see new commits | Choose RR if repeated snapshots are needed |
| Thinking RR makes every type of SELECT return the same version | Locking reads can see newer versions | Distinguish consistent reads from current reads |
| Thinking RR prevents all phantoms in all operations | Locking reads/DML have different locking rules | Understand snapshot reads, next-key locks, and access paths |
| Thinking RR equals SERIALIZABLE | Write skew can still happen | Protect invariants with locks, guard rows, constraints, or SERIALIZABLE |
| Using SELECT COUNT(*) then updating another row without locking | Two transactions can both pass the check | Create a synchronization point and re-check with a current read |
| Using FOR UPDATE without a suitable index | Can lock a wide range and reduce concurrency | Design indexes, inspect EXPLAIN |
| Retrying only the statement that caused the deadlock | Transaction may no longer be in a consistent state | Retry the entire rolled-back transaction |
| Assuming lock timeout always rolls back the entire transaction | Earlier changes may remain in the transaction | Proactively roll back when business logic fails |

## 16. Practice Exercises

1. Use two sessions to reproduce a dirty read under `READ UNCOMMITTED`. Roll back Session A and observe the value B read.
2. Reproduce a nonrepeatable read under `READ COMMITTED`: A reads a row twice, B updates and commits in between.
3. Repeat exercise 2 under `REPEATABLE READ` using consistent SELECTs and explain why the result stays the same.
4. Inside an RR transaction, compare a plain SELECT with `SELECT ... FOR UPDATE` after another session has committed an update.
5. Reproduce a phantom under `READ COMMITTED` using the predicate `amount BETWEEN 100 AND 200` and an INSERT from another session.
6. Repeat with consistent SELECTs under RR. Then try a locking range read `FOR UPDATE` and observe the INSERT being blocked by next-key locks.
7. Reproduce write skew with two on-call doctors. Confirm both transactions can commit yet the invariant is broken.
8. Fix write skew by locking related rows or using a guard row; ensure re-checking via current read after acquiring the lock.
9. Try the same problem under `SERIALIZABLE`, record lock waits/deadlocks, and explain the concurrency trade-off.
10. Run `EXPLAIN` for the locking range read before and after adding a suitable index. Observe the impact on the access path.
11. Create a deadlock schedule with two sessions locking two rows in opposite orders. Read `SHOW ENGINE INNODB STATUS` and design a retry mechanism.

## 17. Checklist Before Choosing an Isolation Level

- [ ] Identified which data must never be read before commit.
- [ ] Determined whether a transaction needs to re-read the same row with the same value.
- [ ] Determined whether a predicate's matching row set must remain stable throughout the transaction.
- [ ] Reviewed business invariants spanning multiple rows, not just individual rows.
- [ ] Distinguished consistent snapshot reads from locking/current reads.
- [ ] Selected an isolation level based on the actual anomalies to prevent.
- [ ] If using `FOR UPDATE`/`FOR SHARE`, checked indexes and lock scope.
- [ ] If using a guard row or locking a set of rows, ensured all code paths updating the invariant follow the same protocol.
- [ ] Implemented handling for deadlocks, lock timeouts, and full-transaction retries.
- [ ] Tested impact on concurrency, latency, and lock contention using representative workloads.
- [ ] Defined how to handle duplicate requests or ambiguous commit outcomes due to connection loss.

## 18. Completion Criteria

You have completed this lesson when you can reproduce and explain dirty read, nonrepeatable read, phantom read, and write skew using two sessions; distinguish snapshot reads from locking/current reads; explain the behavior of all four isolation levels in InnoDB; know why RR prevents phantoms in consistent snapshots yet can still permit write skew; and implement invariant protection using `FOR UPDATE`, guard rows, or SERIALIZABLE with proper deadlock/retry handling.

## References

- [MySQL 8.4 Reference Manual — InnoDB Transaction Isolation Levels](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html)
- [MySQL 8.4 Reference Manual — Consistent Nonlocking Reads](https://dev.mysql.com/doc/refman/8.4/en/innodb-consistent-read.html)
- [MySQL 8.4 Reference Manual — Locking Reads](https://dev.mysql.com/doc/refman/8.4/en/innodb-locking-reads.html)
- [MySQL 8.4 Reference Manual — InnoDB Multi-Versioning](https://dev.mysql.com/doc/refman/8.4/en/innodb-multi-versioning.html)
- [MySQL 8.4 Reference Manual — InnoDB Locking](https://dev.mysql.com/doc/refman/8.4/en/innodb-locking.html)
