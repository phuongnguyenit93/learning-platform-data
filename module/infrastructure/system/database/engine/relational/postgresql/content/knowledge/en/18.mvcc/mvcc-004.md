# Statement-Level and Transaction-Level Snapshots in PostgreSQL

## 1. Within the Same Transaction, Why Can Re-Reading See Different Results?

Suppose an accounts table has balances:

```text
account_id | owner_name | balance
-----------+------------+--------
101        | An         | 500.00
202        | Bình       | 200.00
```

Two connections access PostgreSQL concurrently:

```text
Time          Session A                        Session B
----------------------------------------------------------------
t1            BEGIN
t2            SELECT balance -> 500
t3                                             UPDATE balance = 600
t4                                             COMMIT
t5            SELECT balance -> ?
t6            COMMIT
```

Question: at `t5`, does Session A see **500** or **600**?

The answer depends on the **transaction isolation level**, and more specifically on **when PostgreSQL chooses a snapshot: per statement or for the entire transaction**.

- Under **`READ COMMITTED`**, A's two `SELECT` statements normally use **two different snapshots**. The second can see 600 because B committed before the second statement began.
- Under **`REPEATABLE READ`**, once A establishes a snapshot on its first read, subsequent normal reads in the same transaction continue using **that snapshot**. A still sees 500 until the transaction ends.
- Under **`SERIALIZABLE`**, normal reads also use a stable snapshot like `REPEATABLE READ`, but PostgreSQL additionally monitors dependency relationships that could cause serialization anomalies; a transaction may have to roll back and retry.

This is the core of the lesson **"Statement-Level and Transaction-Level Snapshots"** in the PostgreSQL **MVCC** chapter.

> **Remember right away:** `BEGIN` does not automatically "freeze the entire database" for every isolation level. A statement-level snapshot and a transaction-wide snapshot are two different models for viewing data.

## 2. Learning Objectives

After this lesson, you will be able to:

1. Explain what MVCC and snapshots are, and how they differ from physical data copies.
2. Distinguish **committed** data, **uncommitted** data, and changes created by **the current transaction itself**.
3. Understand **statement-level** snapshots under `READ COMMITTED`.
4. Understand **transaction-level** snapshots under `REPEATABLE READ` and `SERIALIZABLE`.
5. Know that a fixed snapshot starts from **the first data-accessing statement**, not necessarily from `BEGIN` itself.
6. Run two-session labs to observe nonrepeatable reads and phantom reads.
7. Explain why a normal `SELECT` behaves differently from `UPDATE` or `SELECT FOR UPDATE` when locks and concurrent updates occur.
8. Identify the limits of a stable snapshot, especially **write skew**.
9. Use read-only transactions for multi-query reports that require consistent results.
10. Understand `pg_current_snapshot()`, `pg_export_snapshot()`, `SET TRANSACTION SNAPSHOT`, and their usage limits.
11. Recognize the impact of long transactions on `VACUUM`, bloat, and operations.
12. Apply these concepts properly in JDBC, controlling autocommit and transaction retries.

## 3. Concept: A Snapshot Is Not a Full Copy of the Database

An **MVCC snapshot** is metadata PostgreSQL uses to determine **which row versions are allowed to be visible** to a query or transaction at the appropriate point.

It does **not** mean PostgreSQL copies the entire table into a new memory region every time you run `SELECT`.

Conceptually, a snapshot records information about transaction IDs and currently active transactions, from which PostgreSQL determines whether a row version falls within the snapshot's visibility scope.

Imagine a row being updated:

```text
Before update:
accounts(101) -> balance = 500
                  old version

Transaction B runs UPDATE:
accounts(101) -> balance = 600
                  new version
                  not yet COMMITted

A's snapshot:
  +-- Does not see uncommitted changes from B.
  +-- Still sees old version = 500 if valid under snapshot.

B COMMITs:
  +-- New snapshots starting after commit can see 600.
  +-- Old REPEATABLE READ snapshot can still see 500.
```

PostgreSQL manages multiple **row versions (*tuple versions*)** so readers can observe appropriate data while other transactions are writing.

### 3.1. What Questions Does a Snapshot Answer?

For example, for a row created by transaction X:

- If X **committed before the snapshot boundary** and was not replaced by another visible change, the version can be seen.
- If X **had not committed** at the snapshot point being evaluated, other transactions normally do not see that new version.
- If X committed **after a fixed snapshot was already chosen**, the old snapshot does not suddenly see X's newly committed version.

This is a conceptual description, not the full algorithm for every MVCC case, because many other factors apply such as version deletion/updates, command IDs, the current transaction, tuple hint bits, and special mechanisms.

### 3.2. A Snapshot Is Not a Simple "Wall-Clock Timestamp"

Do not imagine a snapshot as simply:

```text
SELECT ... AS OF '2026-11-14 10:00:00'
```

Standard PostgreSQL **does not provide historical queries at arbitrary timestamps** by switching snapshots. An MVCC snapshot is tied to **visibility of existing transactions**, not a time-travel system retaining all row versions forever.

Old versions can be cleaned up by `VACUUM` when no snapshot needs them anymore. To query long-term history, design a dedicated audit/history/temporal model.

### 3.3. MVCC Does Not Eliminate All Locks

A normal `SELECT` generally reads from an MVCC snapshot without waiting on another transaction modifying a row just to read an appropriate committed version. However:

- `UPDATE` and `DELETE` must coordinate writes on the same row.
- `SELECT ... FOR UPDATE` explicitly locks rows.
- Some DDL statements acquire table-level locks.
- Higher isolation levels can detect conflicts and abort transactions.

Thus, **MVCC reduces contention between reads and writes**; it is not a claim that "PostgreSQL never locks."

## 4. Preparing the Practice Schema

Run DDL and two-session experiments only in a **learning database**, never on real accounts or production workloads.

### 4.1. Creating the Accounts Table

```sql
CREATE SCHEMA IF NOT EXISTS mvcc_snapshot_lab;

CREATE TABLE mvcc_snapshot_lab.accounts (
    account_id bigint PRIMARY KEY,
    owner_name text NOT NULL,
    balance numeric(14,2) NOT NULL
        CHECK (balance >= 0)
);

INSERT INTO mvcc_snapshot_lab.accounts
    (account_id, owner_name, balance)
VALUES
    (101, 'An',   500.00),
    (202, 'Bình', 200.00),
    (303, 'Chi',  100.00);
```

Initial data:

| account_id | owner_name | balance |
| ---: | --- | ---: |
| 101 | An | 500.00 |
| 202 | Bình | 200.00 |
| 303 | Chi | 100.00 |

### 4.2. Creating the Orders Table

```sql
CREATE TABLE mvcc_snapshot_lab.orders (
    order_id bigint PRIMARY KEY,
    customer_name text NOT NULL,
    amount numeric(12,2) NOT NULL,
    status text NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
);

INSERT INTO mvcc_snapshot_lab.orders
    (order_id, customer_name, amount, status)
VALUES
    (1001, 'An',   120.00, 'PAID'),
    (1002, 'Bình',  75.00, 'NEW'),
    (1003, 'Chi',  230.00, 'PAID');
```

The orders table helps distinguish two phenomena:

- **Nonrepeatable read:** a row in `orders` changes value.
- **Phantom read:** a new row is inserted into or removed from the set matching `WHERE`.

### 4.3. Running Controlled Experiments

Open two `psql` windows or two connections in your SQL client, named:

- **Session A:** the transaction observing snapshots.
- **Session B:** the transaction modifying and committing data.

Both connections must access **the same database and schema**.

Examples where B runs `COMMIT` mutate lab data. Therefore, before **each** experiment, reset the rows to their initial values and ensure **no experiment transactions remain open**.

Example reset statements after both sessions have finished:

```sql
UPDATE mvcc_snapshot_lab.accounts
SET balance = 500.00
WHERE account_id = 101;

UPDATE mvcc_snapshot_lab.orders
SET amount = 120.00, status = 'PAID'
WHERE order_id = 1001;

DELETE FROM mvcc_snapshot_lab.orders
WHERE order_id IN (1004, 1005);
```

These reset statements are strictly for the lesson schema, never real data. If an experiment inserted other IDs, restore according to the actual changes of that experiment.

## 5. `READ COMMITTED`: Each Statement Gets a Snapshot When It Starts

`READ COMMITTED` is PostgreSQL's common default isolation level.

For a normal `SELECT`:

- It sees data committed **before the query starts**, per that statement's snapshot.
- It does not read uncommitted values from other transactions.
- If you run another `SELECT` after another transaction commits, the new read can see the newly committed value.

### 5.1. A/B Experiment: Same Transaction, Two Different Values

Reset account 101 to 500.00 before testing.

**Session A:**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM mvcc_snapshot_lab.accounts
WHERE account_id = 101;
-- Result: 500.00.
```

Keep transaction A open.

**Session B:**

```sql
BEGIN;

UPDATE mvcc_snapshot_lab.accounts
SET balance = 600.00
WHERE account_id = 101;

COMMIT;
```

Back to **Session A:**

```sql
SELECT balance
FROM mvcc_snapshot_lab.accounts
WHERE account_id = 101;
-- Result: 600.00.

COMMIT;
```

Why?

```text
A - READ COMMITTED
BEGIN
  |
  | SELECT #1 -> snapshot S1
  |                 sees balance=500
  |
  |                   B: UPDATE balance=600
  |                   B: COMMIT
  |
  | SELECT #2 -> snapshot S2
  |                 sees balance=600
  |
COMMIT
```

This is an example of a **nonrepeatable read**: two reads of the same row in the same transaction return different values because another transaction committed between the two statements.

### 5.2. READ COMMITTED Does Not Dirty-Read

If Session B only ran:

```sql
BEGIN;
UPDATE mvcc_snapshot_lab.accounts
SET balance = 650.00
WHERE account_id = 101;
-- Not COMMITted yet.
```

then Session A's normal `SELECT` will not see **B's uncommitted 650.00**. If B eventually runs `ROLLBACK`, that value never becomes committed data.

PostgreSQL also treats `READ UNCOMMITTED` identically to `READ COMMITTED`: specifying `READ UNCOMMITTED` does not enable dirty reads as in textbook examples from some other products.

### 5.3. Each Statement Has Snapshot Consistency Across Its Read Scope

A single `SELECT` does not switch snapshots mid-execution just because another transaction commits while the statement is running.

Example of a single report query:

```sql
SELECT
    COUNT(*) AS total_orders,
    SUM(amount) AS total_amount
FROM mvcc_snapshot_lab.orders
WHERE status = 'PAID';
```

Both aggregate expressions are computed within **one `SELECT` statement**, using that statement's snapshot. One aggregate in the same `SELECT` will never read snapshot S1 while the other switches to S2 because another transaction committed.

However, **two separate `SELECT` statements**, even inside one `READ COMMITTED` transaction, can read two different snapshots.

### 5.4. Be Careful With Functions Executing SQL Inside a Statement

"One snapshot per statement" is the baseline rule for normal queries. In PostgreSQL, a user-defined function—especially with `VOLATILE` volatility—can execute internal SQL statements with different snapshot rules than `STABLE`/`IMMUTABLE` functions.

This is an advanced topic: do not assume every SQL query buried inside a `VOLATILE` function is locked to the outer statement's single snapshot. When consistent multi-table reads are required, understand function semantics and the active isolation level.

## 6. READ COMMITTED Snapshots and Autocommit Scope

By default, many clients run PostgreSQL with **autocommit** enabled. Without an explicit transaction, each statement runs in its own transaction.

```sql
SELECT balance
FROM mvcc_snapshot_lab.accounts
WHERE account_id = 101;

SELECT balance
FROM mvcc_snapshot_lab.accounts
WHERE account_id = 101;
```

Without `BEGIN` and with autocommit on, the two statements are two independent transactions. Therefore they can see different data if another transaction commits between them.

But here is a very common misconception:

> Grouping two `SELECT` statements into a `READ COMMITTED` transaction does **not** automatically make their snapshots identical.

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance FROM mvcc_snapshot_lab.accounts
WHERE account_id = 101;

SELECT balance FROM mvcc_snapshot_lab.accounts
WHERE account_id = 101;

COMMIT;
```

The two `SELECT`s can still see two different pictures of the database if another transaction commits in between.

That is why a dashboard running **multiple separate queries** can display:

```text
Query 1: PAID orders = 200
Query 2: Total revenue = 19,000
```

where the two figures do not correspond to the same logical instant, even if both ran inside one `READ COMMITTED` transaction.

If both queries must read from one consistent snapshot across the entire transaction, consider `REPEATABLE READ READ ONLY`.

## 7. `REPEATABLE READ`: One Stable Snapshot for the Entire Transaction

In PostgreSQL, `REPEATABLE READ` uses a single snapshot retained for normal read statements in the transaction once that snapshot is established.

### 7.1. Two-Session Experiment

Reset `account_id = 101` to 500.00 and try this.

**Session A:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM mvcc_snapshot_lab.accounts
WHERE account_id = 101;
-- 500.00, establishes snapshot S1.
```

**Session B:**

```sql
BEGIN;

UPDATE mvcc_snapshot_lab.accounts
SET balance = 600.00
WHERE account_id = 101;

COMMIT;
```

**Session A:**

```sql
SELECT balance
FROM mvcc_snapshot_lab.accounts
WHERE account_id = 101;
-- Still 500.00 in snapshot S1.

SELECT SUM(balance) AS total_balances
FROM mvcc_snapshot_lab.accounts;
-- Sum based on snapshot S1 (plus A's own changes, if any).

COMMIT;
```

After A finishes its transaction, a new transaction can see 600.00.

Diagram:

```text
A - REPEATABLE READ
BEGIN
  |
  | SELECT #1 -> snapshot S1
  |               sees 500
  |
  |                 B: UPDATE to 600
  |                 B: COMMIT
  |
  | SELECT #2 -> still uses S1
  |               sees 500
  |
COMMIT

New transaction -> fresh snapshot -> sees 600
```

### 7.2. "Transaction-Level Snapshot" Does Not Necessarily Start Exactly at `BEGIN`

This is a very important PostgreSQL detail.

Under `REPEATABLE READ`/`SERIALIZABLE`, the snapshot is normally established when the first statement that actually needs a snapshot runs—such as a `SELECT` or data-modifying statement—**not simply when the client sends `BEGIN`**.

Consider another schedule:

```text
t1   A: BEGIN ISOLATION LEVEL REPEATABLE READ
t2   B: UPDATE account 101 -> 600
t3   B: COMMIT
t4   A: first SELECT balance
```

At `t4`, A normally sees **600**, because its first read snapshot was chosen **after** B committed.

Therefore:

- `BEGIN`: starts the transaction boundary.
- First `SELECT`/DML needing a snapshot: establishes the transaction's stable view under `REPEATABLE READ`.
- Subsequent `SELECT`s: continue using that view, plus changes made by A itself.

**Never infer that `BEGIN` at 10:00 means every read under `REPEATABLE READ` only sees data from before 10:00.**

### 7.3. A Snapshot Does Not Mean the Transaction Is Completely "Frozen"

If Session A itself successfully updates a row, subsequent statements **inside A itself** see that change. A stable snapshot governs **visibility of changes from other transactions**; it does not prevent a transaction from seeing its own changes.

## 8. A Transaction Always Sees Its Own Changes

Example on the test database:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM mvcc_snapshot_lab.accounts
WHERE account_id = 202;
-- 200.00 if data is still initial.

UPDATE mvcc_snapshot_lab.accounts
SET balance = balance + 25.00
WHERE account_id = 202
RETURNING balance;
-- 225.00.

SELECT balance
FROM mvcc_snapshot_lab.accounts
WHERE account_id = 202;
-- 225.00: the transaction sees its own write.

ROLLBACK;
```

The trailing `ROLLBACK` ensures no data is modified by the example.

The same ability to see *own writes* also applies under `READ COMMITTED`.

### 8.1. Do Not Confuse a Fixed Snapshot With Read-Only Mode

`REPEATABLE READ` is not read-only by default. A transaction at that level can run `INSERT`, `UPDATE`, and `DELETE`, subject to the corresponding conflict rules.

If your goal is a report that does not modify data, specify explicitly:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT COUNT(*) FROM mvcc_snapshot_lab.orders;
SELECT SUM(amount) FROM mvcc_snapshot_lab.orders;

COMMIT;
```

`READ ONLY` describes **what operations the transaction is permitted to execute**, while `REPEATABLE READ` describes **visibility and certain concurrency rules**. They are two separate properties.

### 8.2. Rows Created by Other Transactions After the Snapshot

Suppose A already picked a snapshot, and then B inserts a new row and commits. A under `REPEATABLE READ` will not see that new row in subsequent normal reads within the same transaction.

However, if **A itself `INSERT`s** a row, A can read that row in later statements even though the initial snapshot was chosen before A's `INSERT`.

## 9. Detailed Comparison of the Two Snapshot Models

| Question | `READ COMMITTED` | `REPEATABLE READ` |
| --- | --- | --- |
| When is the snapshot for normal reads chosen? | Per statement | Fixed for the transaction when first established |
| Sees another transaction's commit between two SELECTs? | **Possible** | No, if commit happened after the snapshot |
| Can two identical SELECTs return different results? | Yes | Normally not due to external changes |
| Are dirty reads possible? | No | No |
| Are nonrepeatable reads possible? | Possible | No under normal MVCC visibility |
| Are phantom reads possible? | Possible | No under PostgreSQL snapshot isolation |
| Sees its own UPDATEs? | Yes | Yes |
| UPDATE hits a row modified after snapshot? | Can wait and re-evaluate condition against new row | May raise `40001` |
| Is write skew possible? | Possible | Still possible |
| Good for reports with multiple SELECTs needing one view? | Requires caution | **Well suited**, especially `READ ONLY` |
| Automatically eliminates all serialization anomalies? | No | No |

Another table clarifying terminology:

| Term | Accurate Meaning |
| --- | --- |
| *Statement snapshot* | A statement reads from the view determined for that statement |
| *Transaction snapshot* | Multiple statements read from the same stable transaction view |
| *Committed data* | Data from a confirmed transaction; still depends on whether commit happened before or after the snapshot |
| *Consistent snapshot* | A data view obeying one snapshot's MVCC rules; does not prove all business invariants hold automatically |
| *Fresh snapshot* | A newer snapshot able to see more recent commits than an older snapshot |
| *Old snapshot* | A snapshot predating newer commits; not an error by itself, but a requested isolation property |

## 10. Phantom Reads: Same WHERE Condition, Changing Row Set

A **phantom** is a new row appearing in or disappearing from filtered results when a transaction repeats a query due to another transaction committing.

### 10.1. Example Under READ COMMITTED

Suppose the `orders` table initially has **two PAID orders**: 1001 and 1003.

**Session A:**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT COUNT(*) AS paid_orders
FROM mvcc_snapshot_lab.orders
WHERE status = 'PAID';
-- 2.
```

**Session B:**

```sql
BEGIN;

INSERT INTO mvcc_snapshot_lab.orders
    (order_id, customer_name, amount, status)
VALUES
    (1004, 'Dung', 160.00, 'PAID');

COMMIT;
```

**Session A:**

```sql
SELECT COUNT(*) AS paid_orders
FROM mvcc_snapshot_lab.orders
WHERE status = 'PAID';
-- 3.

COMMIT;
```

The query did not change, yet the result went from **2 to 3** because the second snapshot saw the newly committed row.

### 10.2. Repeating Under REPEATABLE READ

Reset data (delete order 1004 once all experiment transactions have closed), then change Session A to:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*)
FROM mvcc_snapshot_lab.orders
WHERE status = 'PAID';
-- 2, establishes snapshot.
```

Session B inserts 1004 and commits as above.

Session A:

```sql
SELECT COUNT(*)
FROM mvcc_snapshot_lab.orders
WHERE status = 'PAID';
-- Still 2 in A's snapshot.

COMMIT;
```

In PostgreSQL, `REPEATABLE READ` **does not allow this kind of phantom read** because the snapshot does not change between statements. This is worth noting when comparing against isolation tables based only on SQL standard minimums.

### 10.3. No Phantoms Does Not Mean No Write Skew

A stable snapshot preserves the transaction's **visible row set**, but **does not automatically stop** two concurrent transactions from reading the same condition and updating **two different rows** so that a global invariant is broken.

We will see an example with `SERIALIZABLE` later.

## 11. A Statement Snapshot Is a Stable View, Not Continuously Updating Row-by-Row

Imagine a `SELECT` scanning a large table for several seconds. If transaction B commits mid-scan, a normal `SELECT` under `READ COMMITTED` does not "switch snapshots halfway through the table" so the first half sees old state and the second half sees new state just because time passed.

That is the benefit of **statement-level consistency**.

### 11.1. Running Multiple Consecutive Queries

Conversely, a dashboard might run:

```sql
SELECT COUNT(*)
FROM mvcc_snapshot_lab.orders
WHERE status = 'PAID';

SELECT SUM(amount)
FROM mvcc_snapshot_lab.orders
WHERE status = 'PAID';
```

If both commands run under `READ COMMITTED`, another transaction can commit between them. Consequently, a ratio computed by combining **results from two separate queries** risks mixing different views.

There are two common solutions:

- **Combine metrics into a single statement** if business logic allows.
- If multiple separate statements are needed, use a `REPEATABLE READ READ ONLY` transaction.

### 11.2. Combining Metrics Into One SELECT

```sql
SELECT
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders,
    COALESCE(
        SUM(amount) FILTER (WHERE status = 'PAID'),
        0::numeric
    ) AS paid_amount,
    COUNT(*) AS all_orders
FROM mvcc_snapshot_lab.orders;
```

All three metrics are computed in the same statement and under the same MVCC view.

This is a great choice when metrics come from one data source and do not require overly complex queries.

### 11.3. CTEs Do Not Create New Transactions

```sql
WITH paid AS (
    SELECT *
    FROM mvcc_snapshot_lab.orders
    WHERE status = 'PAID'
),
metrics AS (
    SELECT COUNT(*) AS total, SUM(amount) AS revenue
    FROM paid
)
SELECT *
FROM metrics;
```

This is still **one SQL statement**. Do not mistake two CTEs for two independent transactions.

**Advanced note:** data-modifying statements inside data-modifying CTEs have specific snapshot, ordering, and `RETURNING` rules; this lesson focuses on normal `SELECT`s. Do not nest CTEs assuming independent `UPDATE`s will see each other like sequential statements.

## 12. `UPDATE` Under READ COMMITTED Has an Important Practical Exception

The "one snapshot per statement" rule is helpful for normal `SELECT`s. However, statements **that lock rows** like `UPDATE`, `DELETE`, and `SELECT ... FOR UPDATE` must handle cases where a row is updated concurrently by another transaction.

Under `READ COMMITTED`, if a statement needs to update a row currently locked by another transaction, PostgreSQL can:

1. Wait for the transaction holding the lock.
2. When that transaction finishes, inspect the appropriate row version.
3. **Re-evaluate the `WHERE` condition** against the newly committed version before deciding whether to update.

This re-evaluation mechanism is referred to in PostgreSQL documentation as **EvalPlanQual** in relevant contexts.

### 12.1. Example: Conditional Inventory Decrement

Create table:

```sql
CREATE TABLE mvcc_snapshot_lab.inventory (
    product_id bigint PRIMARY KEY,
    available integer NOT NULL
        CHECK (available >= 0)
);

INSERT INTO mvcc_snapshot_lab.inventory
    (product_id, available)
VALUES (701, 1);
```

Two transactions both try to sell a product with only 1 unit remaining.

**Session A:**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

UPDATE mvcc_snapshot_lab.inventory
SET available = available - 1
WHERE product_id = 701
  AND available >= 1
RETURNING product_id, available;
-- Returns row product_id=701, available=0.
-- Not COMMITted yet, so it still holds the row lock.
```

**Session B:**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

UPDATE mvcc_snapshot_lab.inventory
SET available = available - 1
WHERE product_id = 701
  AND available >= 1
RETURNING product_id, available;
-- May wait on A's lock.
```

After **A COMMITs**, B proceeds. PostgreSQL re-checks the row, which now has `available = 0`, so `available >= 1` is false. B **updates 0 rows** instead of decrementing further to -1.

**Key takeaways:**

- This is still `READ COMMITTED`.
- `UPDATE` handles write contention and re-evaluates the row after waiting.
- `CHECK available >= 0` provides an additional layer of protection.
- The application must check the row count from `RETURNING` or affected rows; never treat "UPDATE produced no error" as guaranteed sale success.

### 12.2. Do Not Generalize That Every UPDATE Sees a Whole-Table Consistent Image

Under `READ COMMITTED`, a complex update statement can **see newly updated state on contended target rows** while other rows still come from the statement's initial snapshot. PostgreSQL documentation warns this can create an inconsistent overall view for complex updates.

Therefore, for invariants spanning multiple rows, design appropriate **transactions and isolation** rather than trusting a complex `UPDATE ... WHERE` to simulate an unchanging system-wide snapshot under contention.

### 12.3. `SELECT ... FOR UPDATE` Differs From Normal SELECT

```sql
BEGIN;

SELECT *
FROM mvcc_snapshot_lab.accounts
WHERE account_id = 101
FOR UPDATE;

ROLLBACK;
```

`SELECT FOR UPDATE` attempts to lock the row. If another transaction is updating that row, it may have to wait, and under `READ COMMITTED` process the new row version accordingly.

By contrast, a plain `SELECT` simply reads the version visible under its snapshot without trying to acquire update rights on the row.

**Therefore:** never apply the plain `SELECT` "statement snapshot" diagram mechanically to predict every `SELECT FOR UPDATE` outcome while waiting on locks.

## 13. When a Write Conflict Occurs Under REPEATABLE READ

Under `REPEATABLE READ`, PostgreSQL does **not** simply reuse `READ COMMITTED`'s behavior of seeing the newer version of a row modified after the snapshot.

A transaction can be rejected when attempting to modify a row already updated and committed by another transaction since its snapshot.

### 13.1. Two-Session Experiment

Assume account 101 has 500.00.

**Session A:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM mvcc_snapshot_lab.accounts
WHERE account_id = 101;
-- 500.00: establishes snapshot S1.
```

**Session B:**

```sql
BEGIN;

UPDATE mvcc_snapshot_lab.accounts
SET balance = balance + 50.00
WHERE account_id = 101;

COMMIT;
-- Database now has 550.00.
```

**Session A:**

```sql
UPDATE mvcc_snapshot_lab.accounts
SET balance = balance + 10.00
WHERE account_id = 101;

-- May raise:
-- ERROR: could not serialize access due to concurrent update
-- SQLSTATE: 40001

ROLLBACK;
```

Why isn't A allowed to freely add onto version 550 after using snapshot S1 that saw 500? Because doing so breaks the consistency of the snapshot/write model at this level.

### 13.2. What Does Error 40001 Mean?

SQLSTATE **`40001`** is `serialization_failure`. It is not restricted only to `SERIALIZABLE` isolation; in PostgreSQL, certain concurrent update conflicts in `REPEATABLE READ` also raise this error code.

The application should:

1. Roll back the failed transaction.
2. Start a **new** transaction.
3. Re-read data and recompute decisions.
4. Execute the appropriate statements.
5. Commit or retry with limits if contention persists.

Never retry a failed `UPDATE` **inside the already-failed transaction** against the old snapshot.

### 13.3. What If A Does Not UPDATE?

If A only `SELECT`s account 101 again inside the same `REPEATABLE READ` transaction after B commits, A still sees 500.00. It does not automatically receive `40001` merely because another transaction committed a change.

However, once A performs a conflicting write or triggers other serializable checks, an error may be raised depending on the situation.

## 14. Isolation Levels and Read Anomalies

The table below is based on PostgreSQL behavior:

| Isolation Level | Dirty read | Nonrepeatable read | Phantom read | Serialization anomaly |
| --- | --- | --- | --- | --- |
| `READ UNCOMMITTED` | No | Possible | Possible | Possible |
| `READ COMMITTED` | No | Possible | Possible | Possible |
| `REPEATABLE READ` | No | No | No under MVCC snapshot | Still possible |
| `SERIALIZABLE` | No | No | No | System prevents non-serializable schedules; may roll back/retry |

`READ UNCOMMITTED` in PostgreSQL behaves like `READ COMMITTED`, so dirty reads do not occur simply by requesting that level.

### 14.1. `SERIALIZABLE` Is Not Just "More Stable Reads" Than REPEATABLE READ

Both have fixed snapshots for normal reads. The key difference is that `SERIALIZABLE` additionally guarantees that committed transactions can be explained by a **valid serial execution order**, provided participating transactions use compatible isolation and access patterns.

PostgreSQL uses **Serializable Snapshot Isolation (SSI)** to detect dependency patterns that could produce anomalies. When necessary, it aborts a transaction with `40001`.

Thus:

- `REPEATABLE READ`: stable view, but **write skew** is still possible.
- `SERIALIZABLE`: monitors for non-serializable anomalies, at the cost of being ready to **retry**.

### 14.2. Isolation Does Not Replace Business Validation

Even under `SERIALIZABLE`, a transaction running:

```sql
UPDATE mvcc_snapshot_lab.accounts
SET balance = balance + 999999.00
WHERE account_id = 101;
```

can still be valid from an isolation standpoint if schema/logic does not forbid it. Isolation governs interactions *between* transactions; it does not know whether a deposit has a legitimate source.

## 15. Write Skew: The Limit of a Stable Snapshot

Consider a clinic with two doctors A and B. The rule is **there must always be at least one doctor on call**.

### 15.1. Creating Data

```sql
CREATE TABLE mvcc_snapshot_lab.doctors_on_call (
    doctor_id bigint PRIMARY KEY,
    doctor_name text NOT NULL,
    on_call boolean NOT NULL
);

INSERT INTO mvcc_snapshot_lab.doctors_on_call
    (doctor_id, doctor_name, on_call)
VALUES
    (1, 'Doctor A', TRUE),
    (2, 'Doctor B', TRUE);
```

Each doctor wants to go off call if someone else is still on call.

### 15.2. Two REPEATABLE READ Transactions Both Read a Valid Snapshot

**Session A:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS people_on_call
FROM mvcc_snapshot_lab.doctors_on_call
WHERE on_call = TRUE;
-- 2.
```

**Session B:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS people_on_call
FROM mvcc_snapshot_lab.doctors_on_call
WHERE on_call = TRUE;
-- 2.
```

**Session A:**

```sql
UPDATE mvcc_snapshot_lab.doctors_on_call
SET on_call = FALSE
WHERE doctor_id = 1;
```

**Session B:**

```sql
UPDATE mvcc_snapshot_lab.doctors_on_call
SET on_call = FALSE
WHERE doctor_id = 2;
```

The two transactions modify **two different rows**, so both can commit under `REPEATABLE READ`:

```sql
COMMIT;
```

Final result: nobody is on call.

### 15.3. Why Was a Stable Snapshot Still Not Enough?

Each transaction read from a snapshot showing **two doctors on call** and assumed that if it went off call, one would remain. However, they **did not see each other's uncommitted decisions**. Because they updated different rows, no direct write-write conflict occurred to force one to fail.

This is **write skew**, a type of serialization anomaly.

### 15.4. How Does SERIALIZABLE Handle It Differently?

Reset both doctors to `TRUE` after closing both transactions:

```sql
UPDATE mvcc_snapshot_lab.doctors_on_call
SET on_call = TRUE;
```

Repeat the same read–update schedule, opening with:

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;
```

and let both transactions read the condition and write as before.

PostgreSQL detects the read–write dependencies forming a non-serializable schedule, and **one transaction must fail** with `40001` rather than letting both commit and break the rule.

After rollback and a full-transaction retry, the retried transaction reads the updated on-call count and must **refuse to let the last doctor go off call**.

**Important:** PostgreSQL `SERIALIZABLE` does not magically know the rule "at least one person on call"; **the application must still perform that check inside the transaction**. `SERIALIZABLE` preserves serial equivalence of the transactions actually written.

## 16. A Stable Snapshot Does Not Mean the Data Is the "Latest"

A report opening a `REPEATABLE READ` transaction around 10:00 and keeping it open until 10:30 can continue seeing data matching the snapshot from its first access.

That is **correct behavior per isolation**, not a caching bug.

Example:

```text
10:00  A: BEGIN REPEATABLE READ
10:01  A: SELECT revenue -> snapshot S1
10:05  B: COMMIT many new orders
10:10  A: SELECT revenue -> still S1
10:20  B: COMMIT more orders
10:30  A: SELECT revenue -> still S1
10:31  A: COMMIT
10:32  A: new transaction -> fresh snapshot
```

A consistent view across multiple queries is an advantage for reporting, but if a transaction is held too long, dashboards can display **older data than reality**.

### 16.1. Choosing the Right Data Contract

Different requirements:

| Requirement | Approach |
| --- | --- |
| "Each screen needs the latest numbers when the request runs" | `READ COMMITTED` may be acceptable; know which query gets which snapshot |
| "Three metrics in one query must be mutually consistent" | Combine into one `SELECT` if appropriate |
| "Multiple queries in one report must share one data state" | `REPEATABLE READ READ ONLY` transaction |
| "Transaction reads a multi-row condition and writes safely against concurrent writes" | Consider `SERIALIZABLE`, locks/constraints, or another design |
| "Report must be strictly up to the current instant" | Long fixed snapshots are unsuitable; define acceptable staleness |
| "Re-read as new commits arrive in real time" | New transactions or per-statement `READ COMMITTED` |

There is no single best isolation level for every kind of application.

## 17. Read-Only Transactions for Multi-SELECT Reports

Suppose you need to build a report containing:

- Count of paid orders.
- Total amount of paid orders.
- List of paid orders for CSV export.

If you run three independent queries under `READ COMMITTED`, they can receive different snapshots. An intentional approach:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT COUNT(*) AS paid_orders
FROM mvcc_snapshot_lab.orders
WHERE status = 'PAID';

SELECT COALESCE(SUM(amount), 0::numeric) AS paid_amount
FROM mvcc_snapshot_lab.orders
WHERE status = 'PAID';

SELECT order_id, customer_name, amount
FROM mvcc_snapshot_lab.orders
WHERE status = 'PAID'
ORDER BY order_id;

COMMIT;
```

These `SELECT`s read from **the same transaction view**, so the order list cannot suddenly pick up a new order committed by another transaction between the three `SELECT`s.

### 17.1. Does READ ONLY Lock the Table to Block Others From Writing?

**No.** A read transaction gets a stable snapshot without locking the entire table to block writers.

Other transactions can still update/insert data. Those changes simply do not appear in the established read snapshot of the `REPEATABLE READ` transaction.

### 17.2. Notes on Ordering and Pagination

A stable snapshot guarantees a consistent view of data, but `LIMIT`/`OFFSET` does not guarantee deterministic ordering if the query lacks `ORDER BY`.

Example paginated export:

```sql
SELECT order_id, amount
FROM mvcc_snapshot_lab.orders
ORDER BY order_id
LIMIT 100 OFFSET 0;
```

Use a deterministic sort order such as the primary key `order_id`. Otherwise, pages can have inconsistent presentation order even when sourced from the same snapshot.

### 17.3. Long Reports Must Mind Snapshot Retention Cost

A transaction scanning all data still holds an MVCC horizon, preventing `VACUUM` from cleaning some old row versions referenced by the snapshot. Therefore, never keep a `REPEATABLE READ` transaction open while a user views a page or waits on UI interactions for minutes.

A good workflow is:

1. Open the transaction.
2. Run the `SELECT`s actually needed.
3. End the transaction.
4. Format/return results outside the transaction whenever possible.

## 18. `SERIALIZABLE READ ONLY DEFERRABLE`: Safe Snapshots for Complex Reports

PostgreSQL offers a special mode:

```sql
BEGIN TRANSACTION
    ISOLATION LEVEL SERIALIZABLE
    READ ONLY
    DEFERRABLE;

SELECT COUNT(*)
FROM mvcc_snapshot_lab.orders;

SELECT SUM(amount)
FROM mvcc_snapshot_lab.orders;

COMMIT;
```

Meaning:

- `SERIALIZABLE`: requests serializable semantics.
- `READ ONLY`: the transaction does not modify data.
- `DEFERRABLE`: the transaction can **wait before executing its first query** until a suitable safe snapshot is found.

This is useful for certain long read-only reports where you want to avoid having to roll back and retry due to serialization conflicts after doing heavy computation.

### 18.1. Do Not Treat DEFERRABLE as "Instant Non-Waiting Reads"

On the contrary, the transaction **may wait at the start** to obtain a safe snapshot. If an application has a very tight SLA, factor in that startup wait.

### 18.2. DEFERRABLE Does Not Replace READ ONLY / SERIALIZABLE

The `DEFERRABLE` option has special meaning for **`SERIALIZABLE READ ONLY`** transactions. You cannot just turn it on for a `READ COMMITTED` writer and expect the safe snapshot behavior above.

### 18.3. When Should It Be Used?

Suitable cases:

- Generating a large accounting report requiring a consistent view.
- Multi-table reconciliation in a read-only process.
- Read-only analytics able to tolerate a startup wait to avoid serialization errors later.

There is no need to apply it to every small API request; it is a tool for when **isolation semantics and operational trade-offs** genuinely call for it.

## 19. `BEGIN`, `SET TRANSACTION`, and When Isolation Can Be Changed

You can set isolation right at the start:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
```

Or set it inside the transaction **before running any query that forbids changing isolation**:

```sql
BEGIN;

SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SET TRANSACTION READ ONLY;

SELECT COUNT(*)
FROM mvcc_snapshot_lab.orders;

COMMIT;
```

### 19.1. Do Not Change Isolation After Reading and Expect the Snapshot to Reset

Wrong idea:

```sql
BEGIN;

SELECT COUNT(*)
FROM mvcc_snapshot_lab.orders;

SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
-- Too late to switch snapshot models for queries already run.

COMMIT;
```

In PostgreSQL, changing isolation via `SET TRANSACTION ISOLATION LEVEL` must happen before the transaction's first data-querying or data-modifying statement.

### 19.2. `SET SESSION CHARACTERISTICS` Differs From `SET TRANSACTION`

```sql
SET SESSION CHARACTERISTICS AS TRANSACTION
    ISOLATION LEVEL REPEATABLE READ;
```

The command above changes the **default for future transactions in this session**; it does not necessarily alter an already-started transaction or other sessions.

With connection pools, be especially careful with session-level settings: a connection may be reused by a subsequent request. Prefer a transaction manager or setting isolation explicitly per request and pool policy.

### 19.3. Chosen Isolation Is Not a Database-Wide Switch

If two services have separate connections, service A choosing `REPEATABLE READ` does not force service B to switch isolation levels too. Each transaction has its own configuration.

To protect a multi-transaction invariant, examine all participating flows, not just a single `SELECT`.

## 20. `now()` and `statement_timestamp()` Are Not Snapshot Identifiers

When writing reports, many people confuse:

- `now()`.
- `transaction_timestamp()`.
- `statement_timestamp()`.
- `clock_timestamp()`.
- MVCC snapshot.

They are **not synonymous**.

| Expression | Meaning |
| --- | --- |
| `now()` | Start time of the current transaction per PostgreSQL rules |
| `transaction_timestamp()` | Equivalent to `now()` |
| `statement_timestamp()` | Start time of the current statement |
| `clock_timestamp()` | Actual wall-clock time at the moment of call; can change even within one statement |
| `pg_current_snapshot()` | MVCC snapshot info, not a simple timestamp |

### 20.1. Testing Within One Transaction

```sql
BEGIN;

SELECT
    now() AS transaction_time,
    statement_timestamp() AS statement_time,
    clock_timestamp() AS wall_clock_time;

-- Run another SELECT afterward:
SELECT
    now() AS transaction_time,
    statement_timestamp() AS statement_time,
    clock_timestamp() AS wall_clock_time;

ROLLBACK;
```

Within the same transaction:

- `now()` keeps the transaction start time.
- `statement_timestamp()` can differ across statements.
- `clock_timestamp()` reflects the exact call time.

### 20.2. An Easy-to-Make Mistake

Under `REPEATABLE READ`, the snapshot may only be chosen at the **first `SELECT`**, after `BEGIN`. Therefore, `now()` being transaction start time **is not proof of when the snapshot was chosen**.

Under `READ COMMITTED`, `now()` still stays fixed across the entire transaction even though each statement takes a fresh snapshot.

Therefore, running:

```sql
SELECT now();
```

does not prove a transaction is reading a fixed snapshot like `REPEATABLE READ`.

### 20.3. Do Not Use Wall-Clock Timestamps to Infer Commit Ordering

Two sessions' clocks do not align with how transactions are confirmed, and a transaction's timestamp may not match its commit time. When a durable business ordering is required, design locks, sequences/commit pipelines, or explicit event models; `now()` alone is not a commit ID.

## 21. Observing Snapshots With PostgreSQL Functions

PostgreSQL provides functions to inspect snapshot information, useful for learning and diagnostics.

### 21.1. `pg_current_snapshot()`

```sql
SELECT pg_current_snapshot();
```

The result has type `pg_snapshot`, showing information used to determine visible vs. invisible transaction IDs under the current view.

The display format looks like:

```text
xmin:xmax:xip_list
```

Conceptually:

- `xmin` is the lower bound related to transactions still being tracked.
- `xmax` is the upper bound of the transaction ID set considered by the snapshot.
- The list of active transactions at snapshot time determines which transactions **are not yet considered committed in that view**.

This is internal MVCC metadata, **not** "the database at 10:15:00."

### 21.2. Extracting Snapshot Fields

In PostgreSQL versions supporting the `pg_snapshot` functions:

```sql
SELECT
    pg_snapshot_xmin(pg_current_snapshot()) AS snapshot_xmin,
    pg_snapshot_xmax(pg_current_snapshot()) AS snapshot_xmax;
```

These numbers are transaction ID boundaries, not bank transaction sequence numbers or timestamps.

If you are working on an older PostgreSQL version, snapshot function names and types may differ; check the documentation for the exact PostgreSQL version in use.

### 21.3. Do Not Treat Identical/Different Snapshot Strings as an Absolute Isolation Test

A snapshot is a structure richer than a single number. Two consecutive `SELECT pg_current_snapshot()` calls can return **the same string representation** even though they belong to **two different statement snapshots**, if no active transaction state changed.

Conversely, a snapshot displaying transaction IDs is not a stable end-user "timestamp."

To demonstrate isolation, two-session exercises with **concrete table values committed between two `SELECT`s** are usually clearer and more meaningful than comparing snapshot strings alone.

## 22. `xmin` and `xmax`: MVCC Traces on Rows

PostgreSQL has system columns related to row versions, including `xmin` and `xmax`.

You can observe them in the lab:

```sql
SELECT
    account_id,
    balance,
    xmin,
    xmax,
    ctid
FROM mvcc_snapshot_lab.accounts
ORDER BY account_id;
```

Simple meanings:

- `xmin`: transaction info for the transaction that created the row version being read.
- `xmax`: system field related to deleting/updating/locking the row under MVCC.
- `ctid`: physical location of the row version in the table, which can change on updates or physical reorganization.

### 22.1. Why Does UPDATE Create a New Version?

Conceptually, PostgreSQL generally does not modify a row version in place in a way that immediately wipes out data needed by older readers. Instead, `UPDATE` can create a **new row version**, while the old version persists for snapshots that still need it.

```text
Snapshot S1  ---> version accounts(101, balance=500)
                  [old tuple]

B UPDATE + COMMIT
               \
                \--> version accounts(101, balance=600)
                     [new tuple]

Snapshot S2  ---> sees new version = 600
```

### 22.2. Do Not Use `xmin/xmax/ctid` as a Business API

System columns help with learning and debugging. However:

- `xmax` can carry **locking** metadata rather than deletion.
- Detailed structures and meanings depend on PostgreSQL internals.
- `ctid` can change when rows are updated and is not a stable ID.
- Transaction IDs have lifecycles and wraparound/freezing mechanisms.

Never use `xmin <> ...` or `xmax <> 0` as a business filter to assert a row was definitely deleted or committed.

To build applications, use primary keys, version columns, business timestamps, CDC, or appropriate audit mechanisms.

## 23. Statement and Transaction Snapshots on a Complete Timeline

Place three distinct transactions on a diagram:

```text
                    Time ----------------------------------------------------->

Session A             BEGIN -------------------------------------------- COMMIT
                      SELECT #1                SELECT #2           SELECT #3

Session B                        BEGIN
                                      UPDATE rows
                                      COMMIT

Session C                                                      BEGIN
                                                              INSERT row
                                                              COMMIT
```

**If A is under READ COMMITTED:**

- `SELECT #1` gets snapshot S1 before B commits.
- `SELECT #2` gets snapshot S2 after B commits, possibly before C commits.
- `SELECT #3` gets snapshot S3 after C commits.
- The three statements can see **three different data states**.

**If A is under REPEATABLE READ:**

- `SELECT #1` establishes snapshot S1.
- `SELECT #2` and `SELECT #3` still use S1 with respect to B's and C's changes.
- Changes committed by B/C after S1 do not automatically appear in A.
- Once A ends and a new transaction opens, new queries can see them.

**If A is under SERIALIZABLE:**

- `SELECT`s normally also observe a stable snapshot.
- PostgreSQL tracks additional dependencies needed to prevent non-serializable schedules by aborting/retrying transactions when necessary.

### 23.1. Do Not Merge "Freshness" and "Consistency" Into One Criterion

- `READ COMMITTED`: allows subsequent statements to update their view to newer commits.
- `REPEATABLE READ`: maintains one stable view across multiple statements.
- `SERIALIZABLE`: adds guarantees of serial equivalence among committed transactions.

A higher level does not mean a report always gets **newer** data. Sometimes it intentionally sees **older data, but all from one snapshot**.

## 24. Exporting and Importing Snapshots Across Multiple Connections

A transaction snapshot normally belongs to **one transaction** and is not automatically shared across connections.

However, PostgreSQL provides a mechanism to **export and import snapshots** so multiple transactions can reference the same view.

Functions/commands:

- `pg_export_snapshot()`.
- `SET TRANSACTION SNAPSHOT 'snapshot_id'`.

This is an advanced tool useful for certain synchronized read workflows across multiple connections.

### 24.1. Session A Exports a Snapshot

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT pg_export_snapshot();
```

An example result is a snapshot identifier string:

```text
00000003-0000001B-1
```

**This string is only an example**—never hardcode it as an always-valid ID; the real value must come from Session A's actual call.

Session A must **keep its transaction open** until the other transactions finish importing the snapshot. Do not `COMMIT` immediately before Session B uses it.

### 24.2. Session B Imports the Snapshot Before Its First Query

In a **separate** connection:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SET TRANSACTION SNAPSHOT '00000003-0000001B-1';

SELECT COUNT(*)
FROM mvcc_snapshot_lab.orders;

SELECT SUM(amount)
FROM mvcc_snapshot_lab.orders;

COMMIT;
```

Replace `'00000003-0000001B-1'` with the **actual ID returned by Session A**.

Important conditions:

1. The importing transaction must use **`REPEATABLE READ` or `SERIALIZABLE`** isolation per PostgreSQL requirements.
2. The snapshot must be imported **before the importing transaction executes any query or data modification**.
3. The exporting transaction must remain open **until importing completes**.
4. Importing a snapshot **does not share uncommitted changes from the exporting transaction**.
5. For `SERIALIZABLE`, additional compatibility rules apply between exporting and importing transactions; consult your version's docs rather than mixing snapshots arbitrarily across mismatched levels/types.

Once Session B has imported successfully, Session A can finish; importing transactions retain their view per established semantics.

### 24.3. Do Not Turn Export/Import Snapshot Into a Time-Travel Mechanism

You cannot save a snapshot token into a table, wait a week, and use it to read data "as of last week." An exported snapshot is only available for importing while the exporting transaction remains open.

For long-term history, use backup/PITR operationally or a business history model. Exported snapshots solve **reading the same view across cooperating concurrent transactions**, not permanent snapshot storage.

### 24.4. Use Case

Suppose three workers read different datasets to build one report for the same period. If each worker opens `REPEATABLE READ` at slightly different times, each could pick a different snapshot. Importing the same snapshot unifies their view under valid conditions.

PostgreSQL's `pg_dump` with multiple parallel jobs also relies on snapshot synchronization for consistent dumps.

## 25. Long Transactions and VACUUM: The Cost of Old Snapshots

MVCC allows multiple row versions to exist so older readers can keep reading appropriate data. However, old versions cannot be kept indefinitely.

PostgreSQL uses `VACUUM` to reclaim space and clean versions no longer needed under visibility rules.

### 25.1. Why Do Long Snapshots Hinder Cleaning Old Versions?

Suppose:

```text
t1   A starts REPEATABLE READ, SELECT account 101 = 500
t2   B UPDATE account 101 = 600; COMMIT
t3   B UPDATE account 101 = 700; COMMIT
t4   B UPDATE account 101 = 800; COMMIT
t5   A is still open and needs to see 500
```

At `t5`, PostgreSQL must keep the version matching A's old snapshot. If `VACUUM` deleted all those versions while A still needed them, A could not read its snapshot properly.

When transactions hold snapshots for long periods, PostgreSQL may be unable to reclaim certain old versions, leading to:

- Growing dead tuple counts.
- Table/index growth over time (*bloat*).
- Higher query and `VACUUM` overhead.
- Storage pressure or operational latency.

### 25.2. READ COMMITTED Can Also Cause Issues

Do not conclude that only `REPEATABLE READ` affects `VACUUM`.

A long-running `SELECT` statement under `READ COMMITTED` still holds a snapshot for the duration of that statement. Other open transactions or waiting states can also maintain cleanup constraints.

However, short statements under `READ COMMITTED` frequently advance to newer snapshots instead of pinning one snapshot from the first query until transaction end as in `REPEATABLE READ`.

### 25.3. `idle in transaction` Is Especially Dangerous

An application opening a transaction and leaving the connection idle:

```text
BEGIN REPEATABLE READ
SELECT ... -> establishes snapshot
Application waits 20 minutes for user input
COMMIT
```

can hold unnecessary snapshots, locks, and resources.

Transactions should be short with clear boundaries. Never hold a reporting snapshot open while waiting for a user to read or scroll a UI.

## 26. Observing Long Transactions With `pg_stat_activity`

A monitoring query in PostgreSQL:

```sql
SELECT
    pid,
    usename,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    backend_xmin,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

Important columns:

| Column | General Meaning |
| --- | --- |
| `pid` | Backend process ID |
| `state` | Session state: `active`, `idle in transaction`, etc. |
| `xact_start` | Time the current transaction started |
| `transaction_age` | How long the transaction has been open |
| `backend_xmin` | Transaction ID bound related to the snapshot horizon held by the backend, if any |
| `wait_event_type` / `wait_event` | What the backend is currently waiting on |
| `query` | Recent/running SQL statement, subject to state and privileges |

**Warning:** `xact_start` does not prove the snapshot started at that exact moment. Under `REPEATABLE READ`, the snapshot may only appear when the first query actually needing it runs.

`backend_xmin` can be `NULL` when the backend is not holding a snapshot horizon in the current state. Do not use a single `NULL`/non-`NULL` value alone to diagnose the entire cause of bloat.

### 26.1. Monitoring Privileges

Depending on privileges, you may not see full details of all sessions. The `query` column may contain sensitive data. Use monitoring data strictly according to privileges and system policies.

### 26.2. Timeout for Idle Transactions

Check:

```sql
SHOW idle_in_transaction_session_timeout;
```

PostgreSQL can configure a timeout to terminate sessions stuck `idle in transaction` for too long.

Example setting local limits for SQL statements in a transaction:

```sql
BEGIN;

SET LOCAL statement_timeout = '10s';
SET LOCAL lock_timeout = '3s';

SELECT COUNT(*)
FROM mvcc_snapshot_lab.orders;

COMMIT;
```

`statement_timeout` bounds statement execution, whereas `lock_timeout` bounds lock waiting; they are **not equivalent** to `idle_in_transaction_session_timeout`. Choose settings based on operational needs rather than setting overly low thresholds that cause unnecessary failures.

## 27. Snapshots and Transactions in Java/JDBC

A Java application using JDBC typically runs multiple queries over the same `Connection`.

Key points:

- `Connection` has an autocommit state.
- Isolation level must be configured before the transaction starts reading/modifying data.
- Multiple queries must use **the same connection and same transaction** if they must share a snapshot.

### 27.1. Example Report Reading the Same Snapshot

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class SnapshotReportService {
    private final DataSource dataSource;

    public SnapshotReportService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void printPaidOrdersReport() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            connection.setTransactionIsolation(
                Connection.TRANSACTION_REPEATABLE_READ
            );
            connection.setReadOnly(true);
            connection.setAutoCommit(false);

            try {
                long paidCount;
                try (PreparedStatement statement =
                         connection.prepareStatement(
                             "SELECT COUNT(*) FROM " +
                             "mvcc_snapshot_lab.orders " +
                             "WHERE status = 'PAID'"
                         );
                     ResultSet rs = statement.executeQuery()) {
                    rs.next();
                    paidCount = rs.getLong(1);
                }

                BigDecimal paidAmount;
                try (PreparedStatement statement =
                         connection.prepareStatement(
                             "SELECT COALESCE(SUM(amount), 0) FROM " +
                             "mvcc_snapshot_lab.orders " +
                             "WHERE status = 'PAID'"
                         );
                     ResultSet rs = statement.executeQuery()) {
                    rs.next();
                    paidAmount = rs.getBigDecimal(1);
                }

                System.out.println("Paid orders: " + paidCount);
                System.out.println("Paid amount: " + paidAmount);

                connection.commit();
            } catch (SQLException | RuntimeException error) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    }
}
```

Both `SELECT`s run on **one connection** with `TRANSACTION_REPEATABLE_READ` and autocommit disabled, so they share the MVCC view established for the transaction.

### 27.2. Note JDBC Configuration Ordering

Configure isolation, read-only mode, and autocommit **before running queries**. Some drivers/pools enforce strict rules about changing isolation after a transaction has started.

In a transaction management framework, prefer the transaction manager's annotations/configuration rather than manually calling `setAutoCommit` or `commit` inside a framework-managed transaction.

### 27.3. Two Connections Do Not Automatically Share a Snapshot

Wrong expectation:

```text
Connection A -> SELECT COUNT(*) (REPEATABLE READ)
Connection B -> SELECT SUM(*)   (REPEATABLE READ)
```

If A and B open two separate transactions, each transaction can establish its snapshot at a different time. Having the same isolation level **does not guarantee the same snapshot across two connections**.

If you genuinely need a shared snapshot across multiple connections, see **export/import snapshot** in section 24; otherwise, using the same connection is usually simpler.

### 27.4. Do Not Keep a Transaction Open While Calling External APIs

If after the first `SELECT`, the application calls an HTTP API taking 30 seconds before running the second `SELECT`, the `REPEATABLE READ` transaction holds its snapshot throughout that wait.

It is usually better to **finish all needed reads first**, commit, and then call external APIs/format documents outside the transaction, unless the business architecture specifically requires otherwise with proper safeguards.

## 28. One Snapshot Across Paginated Results: Conditions and Limits

An application exporting millions of records across pages can use a `REPEATABLE READ` transaction to prevent data from shifting between pages.

### 28.1. Deterministic Paginated Example

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT order_id, customer_name, amount
FROM mvcc_snapshot_lab.orders
ORDER BY order_id
LIMIT 100 OFFSET 0;

SELECT order_id, customer_name, amount
FROM mvcc_snapshot_lab.orders
ORDER BY order_id
LIMIT 100 OFFSET 100;

COMMIT;
```

With the same snapshot and a deterministic `ORDER BY`, another transaction inserting new orders after the snapshot will not shift the visible dataset between the two `SELECT`s in this transaction.

### 28.2. However, OFFSET Has a Cost

On large tables, deep `OFFSET` forces PostgreSQL to process and discard many rows. **Keyset pagination** by `order_id` is often helpful:

```sql
SELECT order_id, customer_name, amount
FROM mvcc_snapshot_lab.orders
WHERE order_id > 1000
ORDER BY order_id
LIMIT 100;
```

However, when an application issues **multiple independent HTTP requests** over time, those are normally **different transactions**. Keyset pagination stabilizes ordering by key, but **does not guarantee the same snapshot** across requests.

For long-running full consistent exports, consider streaming cursors, dedicated backups/exports, or batch workflows designed around snapshot lifetime and transaction maintenance costs.

### 28.3. Keeping One Transaction Open for Hours Is Not Optimal

A stable snapshot prevents page drift from concurrent writes, yet holding a transaction open for a long time impacts `VACUUM` and resources. Balance:

- Required consistency.
- Data volume.
- Export duration.
- Restart/resume capability.
- Snapshot retention cost.
- Reading from a replica or materialized snapshot architecture.

## 29. Reading From a Standby/Replica Has a Different Snapshot Context

If an application reads from a **read replica**, distinguish:

1. The MVCC snapshot established **on the node executing the query**.
2. WAL progress **received and replayed** by the replica.
3. Replication lag behind the primary.

A `REPEATABLE READ` snapshot on a replica is consistent with the replica's state, but **does not mean the replica has received every transaction recently committed on the primary**.

### 29.1. Replication Lag Example

```text
Primary:
  COMMIT order #1005

Standby:
  Has not replayed corresponding WAL yet

Application:
  BEGIN REPEATABLE READ on Standby
  SELECT ... -> does not see #1005 yet
```

This can be normal asynchronous replica behavior, not necessarily an MVCC bug.

### 29.2. Conflict With Cleanup on Standby

On a hot standby, long read queries can conflict with replaying certain WAL cleanup actions from the primary. PostgreSQL has policies and settings to resolve replay conflicts, which can cancel queries on the standby.

Therefore, a read-only transaction on a replica is not guaranteed the right to hold a snapshot indefinitely. Account for report duration and operational settings such as `max_standby_streaming_delay` or `hot_standby_feedback` as appropriate.

### 29.3. Consistent Read Does Not Mean Latest Read

A report on a replica can be:

- Consistent **within its snapshot**.
- Yet behind **in reflecting recent primary data**.

When designing dashboards or *read-your-writes* flows across multiple nodes, account for replication lag and routing—not just isolation level.

## 30. Transaction-Level Snapshots and Limits on Update Workflows

There is a misconception: "Simply using REPEATABLE READ makes every multi-step update workflow safe."

Incorrect.

### 30.1. Fixed Snapshots Do Not Protect All Multi-Row Invariants

The two-doctor write skew example showed two `REPEATABLE READ` transactions can both observe a valid state and modify two different rows to produce a rule-violating outcome.

### 30.2. Reading an Old Snapshot Then Deciding an Update Can Become Invalid

Suppose an application reads "number of open orders" in an old snapshot and uses it to allow creating a new order. If another transaction does the same concurrently, both can make wrong decisions regarding an overall order cap.

Common approaches:

- Database constraints expressing the invariant, if possible.
- Atomic conditional updates on a coordinating row.
- Locking resources that must be protected per appropriate rules.
- `SERIALIZABLE` with full-transaction retries.
- Data modeling that avoids redundant state that is hard to guard.

### 30.3. Do Not Run `SELECT FOR UPDATE` on an Aggregate Assuming It Locks a Range

```sql
SELECT COUNT(*)
FROM mvcc_snapshot_lab.orders
WHERE status = 'NEW';
```

This is a count. It **does not lock all future rows** that might be inserted matching the condition.

If the business rule is "no more than N NEW orders," simply counting current rows and inserting under `READ COMMITTED` or `REPEATABLE READ` cannot stop two transactions from both counting below the threshold and both inserting.

You need an actual coordination mechanism—often a redesigned model constraint, a locked counter row, or `SERIALIZABLE`.

## 31. Retrying Transactions on `40001`

A transaction under `REPEATABLE READ` or `SERIALIZABLE` may raise:

```text
SQLSTATE 40001: serialization_failure
```

The application must not treat this error as "a SELECT failed, just re-read inside the old transaction."

### 31.1. Proper Retry Algorithm

```text
attempt = 0

while attempt < max_attempts:
    attempt += 1
    open a NEW transaction
    choose appropriate isolation
    read data from NEW snapshot
    check business invariants
    perform modifications
    COMMIT

    if succeeded:
        return result

    if SQLSTATE = 40001:
        ROLLBACK old transaction
        wait backoff/jitter interval
        retry ENTIRE logic from the beginning

    if non-retriable error:
        ROLLBACK
        return appropriate error

if max attempts exceeded:
    return observable error for investigation
```

This is **pseudocode**, not directly executable PL/pgSQL or SQL.

### 31.2. Do Not Retry Only the UPDATE Statement

If A read numbers and made decisions on snapshot S1 and then hit `40001`, merely re-running the `UPDATE` can act on decisions made from stale data. Retrying must include **re-reading** and **recomputing decisions**.

### 31.3. Limit External Side Effects Inside Transactions

If transaction logic sends an email or calls a payment API between reading and committing, retries can trigger those side effects multiple times. PostgreSQL `ROLLBACK` **does not roll back emails**.

Use a transactional outbox, idempotency keys, or an appropriate pattern when coordinating with external systems.

### 31.4. Deadlocks May Require Similar Retries

In addition to `40001`, `40P01` is **deadlock detected**. Where business logic permits, retry the entire transaction after rollback with a bounded retry policy.

Never blindly retry every `SQLSTATE`: `CHECK` violations, foreign key errors, or bad input require fixing data/rules and will not resolve by waiting.

## 32. Common Mistakes When Understanding PostgreSQL Snapshots

| Misconception / Mistake | Why Is It Wrong? | Better Mental Model or Fix |
| --- | --- | --- |
| `BEGIN` always fixes the snapshot at `BEGIN` time | `REPEATABLE READ` snapshots are normally set on the first query needing one | Identify the actual first query point |
| `READ COMMITTED` uses one snapshot per transaction | It usually takes a snapshot per statement | Use `REPEATABLE READ` when multiple `SELECT`s must match |
| `READ UNCOMMITTED` permits dirty reads | PostgreSQL implements it like `READ COMMITTED` | Never expect to read uncommitted data |
| Same transaction means two `SELECT`s always match | Under `READ COMMITTED`, another commit can occur between statements | Understand isolation level and snapshots |
| One `SELECT` can read two snapshots if B commits mid-query | Normal `SELECT`s read from a consistent statement view | Distinguish single-statement vs. multi-statement |
| `REPEATABLE READ` "freezes data, including own writes" | Transactions still see their own changes | Distinguish own writes from other transactions' commits |
| `REPEATABLE READ` snapshots always show the latest data | They intentionally preserve the established view | Open a new transaction when fresh data is needed |
| No phantoms means `SERIALIZABLE` | PostgreSQL `REPEATABLE READ` prevents phantoms but allows write skew | Use `SERIALIZABLE`/locks/constraints when needed |
| `SERIALIZABLE` never errors | SSI can abort transactions to avoid anomalies | Be ready to roll back and retry the whole transaction |
| `UPDATE` in `READ COMMITTED` always uses the initial snapshot without rechecking | Contended/locked rows can be re-evaluated after waiting | Understand DML, row locking, and `WHERE` rechecks |
| `REPEATABLE READ` updating a row changed by B succeeds automatically | Can raise `40001` | Retry in a new transaction |
| `SELECT FOR UPDATE` is like a plain `SELECT` | It requests locks and has conflict rules | Use deliberately to coordinate writes |
| Checking `now()` tells you which snapshot is active | `now()` is transaction start time, not an MVCC snapshot | Separate wall-clock time from visibility |
| Identical `pg_current_snapshot()` strings mean one snapshot object | Strings can match if active XID state didn't change | Test visibility using two sessions |
| `xmin` is row creation timestamp | It is transaction ID metadata, not a datetime | Never use as a business timestamp |
| `xmax != 0` definitely means row deleted | `xmax` also tracks locks and MVCC details | Never use as a business filter |
| A snapshot can be kept to re-read data next week | Exported snapshots are importable only while exporter stays open | Use history/backups for past data |
| Two `REPEATABLE READ` connections share one snapshot | They are separate transactions | Share a connection or export/import snapshot |
| Long read-only snapshots have zero cost | Long transactions hold back MVCC horizon / block `VACUUM` | Keep transactions short |
| A replica snapshot always includes all primary commits | Replicas can lag behind WAL | Account for replication lag and consistency needs |
| Isolation alone protects every business invariant | Transactions still need checks, constraints, and proper updates | Design atomic/isolated logic per invariant |
| Retry only the statement that hit `40001` | Decisions made on the old snapshot are stale | Retry the entire transaction |
| Read-only transactions lock tables to block writers | MVCC enables reading without blocking writers in many cases | Consistent reads do not mean blocking writes |
| Adding `ORDER BY` at the end of `SELECT` chooses the snapshot | `ORDER BY` sorts output, not visibility | Snapshots are governed by transaction/isolation |

## 33. Practice Exercises With Answers

Exercises use schema `mvcc_snapshot_lab`. Two-session exercises should only be run on a test database, resetting data before each comparison.

### Exercise 1. READ COMMITTED: Same Transaction, Two Reads

A reads balance 500. B updates to 600 and commits. A reads again in the same `READ COMMITTED` transaction. Result?

**Answer:** A can see **600** on the second `SELECT`, because the new statement takes a new snapshot after B committed.

### Exercise 2. REPEATABLE READ: Same Schedule

A opens `REPEATABLE READ`, `SELECT`s balance 500, then B commits balance 600. A `SELECT`s again. Result?

**Answer:** still **500**, because A established its snapshot before B committed.

### Exercise 3. BEGIN Before B COMMITs, Before A Runs SELECT

```text
A: BEGIN ISOLATION LEVEL REPEATABLE READ
B: UPDATE balance=600; COMMIT
A: first SELECT balance
```

**Answer:** A normally sees **600**, because the `REPEATABLE READ` snapshot is established when A runs its first query needing a snapshot, not automatically at `BEGIN`.

### Exercise 4. What Does A See When B Has Not COMMITted?

B updated to 600 without committing, and A `SELECT`s from another transaction.

**Answer:** no dirty read of 600. A sees the appropriate version for its snapshot, such as the committed 500.

### Exercise 5. Can PostgreSQL READ UNCOMMITTED Read Uncommitted Data?

**Answer:** no. PostgreSQL implements this level like `READ COMMITTED`.

### Exercise 6. Does READ COMMITTED Have Phantoms?

A counts two PAID orders; B inserts one PAID order and commits; A counts again.

**Answer:** A can see **three orders**, because the second statement uses a fresh snapshot.

### Exercise 7. Does REPEATABLE READ Have That Phantom Read?

**Answer:** not for normal read queries under PostgreSQL snapshots: A continues seeing two orders inside the transaction whose snapshot was set before B committed.

### Exercise 8. Does a REPEATABLE READ Transaction See Its Own UPDATE?

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

UPDATE mvcc_snapshot_lab.accounts
SET balance = balance + 25.00
WHERE account_id = 202;

SELECT balance
FROM mvcc_snapshot_lab.accounts
WHERE account_id = 202;

ROLLBACK;
```

**Answer:** yes, `SELECT` sees the value updated by the transaction itself, e.g., 225.00 starting from 200.00. `ROLLBACK` discards the change.

### Exercise 9. Why Can an UPDATE in REPEATABLE READ Fail With `40001`?

A established a snapshot, then B updated the same row and committed; afterward A tries to `UPDATE` that row.

**Answer:** because a newer row version committed after A's snapshot. PostgreSQL rejects the conflicting update with a serialization failure rather than merging outside the snapshot.

### Exercise 10. Single-Unit Inventory UPDATE Under READ COMMITTED

```sql
UPDATE mvcc_snapshot_lab.inventory
SET available = available - 1
WHERE product_id = 701
  AND available >= 1
RETURNING available;
```

If two transactions both try to sell a product with 1 left, what must be checked?

**Answer:** one transaction decrements to 0, while the other—after waiting and re-evaluating the condition—updates **0 rows**. The application must check `RETURNING` or affected row count to know if the sale succeeded.

### Exercise 11. Why Is `SELECT FOR UPDATE` Different From a Normal SELECT?

**Answer:** it acquires row locks, so it can wait for other write transactions and inspect the row after the lock is released; a normal `SELECT` reads from an MVCC snapshot without waiting on write locks just to read.

### Exercise 12. Is REPEATABLE READ the Same as SERIALIZABLE?

**Answer:** no. It maintains a stable snapshot yet still permits write skew. `SERIALIZABLE` adds SSI to prevent non-serializable schedules.

### Exercise 13. Which Anomaly Is Both Doctors Going Off Call?

**Answer:** **write skew**: both transactions read an on-call count of 2, then updated two different rows to `FALSE`, leaving zero doctors on call even though each saw a valid state.

### Exercise 14. Why Can SERIALIZABLE Raise 40001?

**Answer:** PostgreSQL detected a dependency cycle/schedule that could lead to a serialization anomaly, so it aborted one transaction to preserve serial equivalence.

### Exercise 15. When Hit With `40001`, Can You Retry Just the UPDATE?

**Answer:** no. You must roll back and re-run the **entire transaction** starting from reading business conditions, because the prior snapshot and decisions may be stale.

### Exercise 16. Can You Read Three Consistent Metrics in One SELECT?

```sql
SELECT
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_count,
    SUM(amount) FILTER (WHERE status = 'PAID') AS paid_amount,
    COUNT(*) AS all_count
FROM mvcc_snapshot_lab.orders;
```

**Answer:** the metrics belong to one statement and read from that statement's snapshot.

### Exercise 17. Do Three Separate SELECTs in READ COMMITTED Share a Snapshot?

**Answer:** not guaranteed. If another transaction commits between `SELECT`s, they can observe different datasets.

### Exercise 18. Transaction Pattern for Running Multiple Reports From One Snapshot

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT COUNT(*) FROM mvcc_snapshot_lab.orders;
SELECT SUM(amount) FROM mvcc_snapshot_lab.orders;

COMMIT;
```

**Answer:** this is the appropriate pattern so both `SELECT`s share a single view inside a read-only transaction.

### Exercise 19. Does `READ ONLY` Block All UPDATEs From Other Sessions?

**Answer:** no. It restricts write operations by the current transaction; other sessions can still write per lock/MVCC rules.

### Exercise 20. What Does `SERIALIZABLE READ ONLY DEFERRABLE` Do?

**Answer:** the transaction can wait at the start to acquire a suitable safe snapshot, avoiding having to retry a long read-only transaction due to serialization conflicts. It is not an option to enable blindly on every query.

### Exercise 21. Is `now()` an MVCC Snapshot Timestamp?

**Answer:** no. `now()` is the transaction timestamp; `statement_timestamp()` and `clock_timestamp()` have different meanings. MVCC snapshots rely on transaction visibility metadata, not just a timestamp.

### Exercise 22. What Does `pg_current_snapshot()` Return?

```sql
SELECT pg_current_snapshot();
```

**Answer:** a `pg_snapshot` value describing the active transaction ID visibility scope. It does not return a calendar timestamp or a table copy.

### Exercise 23. Can `xmin` Be Used as an Order Creation Date?

**Answer:** no. `xmin` relates to the tuple-creating transaction ID, not a business `created_at`. Use a schema/application-managed timestamp column.

### Exercise 24. Should You Rely on `xmax != 0` to Conclude a Row Was Deleted?

**Answer:** no. `xmax` has internal meanings including row-locking metadata, so it is not a simple deletion flag for applications.

### Exercise 25. Can an Exported Snapshot Be Reused After One Month?

**Answer:** no. An exported snapshot is only importable while the exporting transaction remains open. Long-term history requires a different mechanism.

### Exercise 26. Must Snapshot Import Happen Before or After the First SELECT?

**Answer:** it must happen **before** the first query in the importing transaction and use an appropriate isolation level such as `REPEATABLE READ`.

### Exercise 27. Why Can Two REPEATABLE READ Connections Read Different Results?

**Answer:** each connection opens a separate transaction and establishes its snapshot at a different time. The same isolation level does not mean the same snapshot. Use one connection or export/import if synchronization is genuinely needed.

### Exercise 28. How Do Long Snapshots Affect VACUUM?

**Answer:** they can retain old row versions still needed by the reader, preventing `VACUUM` from reclaiming them and creating bloat/resource pressure.

### Exercise 29. Does `xact_start` Equal Snapshot Establishment Time?

**Answer:** not necessarily. A transaction can `BEGIN` before its first `SELECT` establishes a `REPEATABLE READ` snapshot.

### Exercise 30. Does Reading REPEATABLE READ on a Replica Always See Recent Primary Commits?

**Answer:** no. The replica may lag in WAL replay; a consistent snapshot on the replica may not include recent primary commits.

### Exercise 31. Why Can READ COMMITTED Show Mismatched Dashboard Numbers Across Two Queries?

**Answer:** two separate `SELECT` statements can use two different snapshots. Combine metrics into one `SELECT` or use `REPEATABLE READ READ ONLY` for the whole report.

### Exercise 32. Is Keeping a REPEATABLE READ Transaction Open Longer Always Better?

**Answer:** no. It can cause reports to view stale data for a long time while holding a snapshot that pressures `VACUUM`. Keep transactions short and bound report duration.

### Exercise 33. How Do You Change Isolation Safely?

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SELECT COUNT(*) FROM mvcc_snapshot_lab.orders;
COMMIT;
```

**Answer:** isolation must be configured before the transaction executes its first data-reading/modifying statement. Another way is specifying it directly in `BEGIN`.

### Exercise 34. Can a READ COMMITTED UPDATE Modify 0 Rows Even If WHERE Was True at Statement Start?

**Answer:** yes. If another transaction updates the row while holding a lock, PostgreSQL can wait and re-evaluate `WHERE` against the newly committed version. A previously true condition can become false.

### Exercise 35. What Is the Difference Between Single-Query Consistency and Workflow Consistency?

**Answer:** a normal `SELECT` reads consistently against its statement snapshot; however, a workflow running multiple separate `SELECT`s under `READ COMMITTED` can mix multiple views. If the whole workflow needs one snapshot, use an appropriate transaction model.

## 34. Checklist for Designing Queries Needing Accurate Snapshots

| Question | What to Verify |
| --- | --- |
| Is the goal one statement or multiple statements? | Affects choosing `READ COMMITTED` vs. `REPEATABLE READ` |
| Is autocommit enabled? | Two `SELECT`s may run in two separate transactions |
| Which isolation level is active? | Check/set before the first query |
| Must the snapshot be fresh or stable? | Those two goals are not synonymous |
| Has the `REPEATABLE READ` transaction run a `SELECT` yet? | The snapshot may not be set at `BEGIN` |
| Can another session commit between two `SELECT`s? | `READ COMMITTED` can see changes |
| Need phantom protection? | `REPEATABLE READ` preserves the visible set per snapshot |
| Does the transaction `UPDATE` rows itself? | Own writes remain visible |
| Could it `UPDATE` rows modified by another session? | May wait/recheck or raise `40001` depending on isolation |
| Are there multi-row invariants to protect? | `REPEATABLE READ` allows write skew |
| Using `SERIALIZABLE`? | Prepare full-transaction retries |
| Is `READ ONLY` set? | Use it when a report is truly read-only |
| Need a safe snapshot for a long report? | Consider `SERIALIZABLE READ ONLY DEFERRABLE` |
| Are multiple connections reading together? | Same isolation does not mean same snapshot |
| Exporting/importing snapshots? | Control import order and exporter lifetime |
| Paginating with deterministic `ORDER BY`? | Snapshots do not determine row ordering |
| Running queries on a standby? | Replication lag is an independent factor |
| Is a read transaction held too long? | Impacts `VACUUM`, bloat, and snapshot age |
| Monitoring long-running transactions? | `pg_stat_activity` and related metrics |
| Need long-term data history? | Snapshots are not time travel |
| Using system columns for business logic? | Avoid `xmin`/`xmax`/`ctid` as business data |
| Tested with two sessions? | Verify visibility around specific commit points |
| Handling connection loss / commit errors? | Never assume commit success/failure when ambiguous |
| External side effects during retries? | Use outbox/idempotency where appropriate |

## 35. Summary

In PostgreSQL, MVCC enables every query or transaction to read data under an appropriate **visibility snapshot** without copying the entire database for each reader.

The most important points:

1. **A snapshot is neither a physical copy nor a calendar timestamp.** It is metadata determining which row versions are visible.
2. **`READ COMMITTED` reads per-statement snapshots.** Two `SELECT`s in the same transaction can differ if another transaction commits between them.
3. **`REPEATABLE READ` reads a stable snapshot for the entire transaction** once established. It does not switch to new data committed by other transactions.
4. **`BEGIN` is not necessarily when a `REPEATABLE READ` snapshot is chosen**; the first data-accessing query is the point to watch.
5. **A transaction sees its own changes**, even when its snapshot with respect to other transactions is fixed.
6. PostgreSQL **never dirty-reads** under `READ COMMITTED` or `READ UNCOMMITTED`. `READ UNCOMMITTED` behaves like `READ COMMITTED`.
7. **`READ COMMITTED` allows nonrepeatable reads and phantoms**, whereas PostgreSQL `REPEATABLE READ` prevents them under normal snapshots.
8. **`UPDATE` and `SELECT FOR UPDATE` involve locks and conflict rules**, so they cannot be reasoned about identically to normal `SELECT`s. `READ COMMITTED` can re-evaluate conditions after waiting; `REPEATABLE READ` can raise `40001` if a row changed after the snapshot.
9. **`REPEATABLE READ` does not protect all multi-row invariants**; write skew can still happen. `SERIALIZABLE` uses SSI to prevent non-serializable schedules and can require retries.
10. **Multiple report queries needing one view** can use `BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY`.
11. **`SERIALIZABLE READ ONLY DEFERRABLE`** can wait for a safe snapshot for long read-only reports with strict serializability requirements.
12. **`pg_current_snapshot()`** helps inspect snapshot info, while `xmin`/`xmax` are MVCC metadata and never replace business columns.
13. **`pg_export_snapshot()` and `SET TRANSACTION SNAPSHOT`** coordinate views across multiple connections under strict timing and lifetime rules.
14. **Long snapshots carry a cost**, notably pinning old versions needed against `VACUUM` and increasing bloat.
15. **A consistent snapshot does not mean the latest data**, especially when reading from a replica experiencing replication lag.

Short reference snippets:

```sql
-- Multiple statements may see new commits between reads:
BEGIN ISOLATION LEVEL READ COMMITTED;
SELECT ...;
SELECT ...;
COMMIT;

-- Multiple statements read the same established view:
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT ...;
SELECT ...;
COMMIT;
```

Both snippets are **syntax templates**; replace `...` with real queries.

**Core principle:** when designing a report or multi-statement SQL workflow, do not only ask "is it in a transaction?" Also ask **"which snapshot does each statement read, when is that snapshot chosen, and what invariants can concurrent transactions modify?"** Answering those three questions accurately is the foundation for using PostgreSQL MVCC correctly.
