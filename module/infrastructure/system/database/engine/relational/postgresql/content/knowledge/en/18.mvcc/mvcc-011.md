# Two-Session Lab to Observe Data Visibility in PostgreSQL

When two users access the same PostgreSQL table, what they **see** does not depend solely on the value currently stored. It also depends on when the transaction started, when the snapshot was taken, the isolation level, which transactions have executed `COMMIT` or `ROLLBACK`, and whether the reading transaction itself has modified the data.

A simple example:

1. Session A updates inventory stock from 10 down to 7, but **has not committed yet**.
2. Session B reads the same product.
3. Does Session B see 10 or 7? What if A rolls back?
4. If B reads again **after A commits**, does the result change within the same transaction?

These questions are an intuitive way to understand **Multi-Version Concurrency Control (MVCC)**. PostgreSQL retains the row versions needed so transactions can read a consistent state without having to wait for every write operation. However, different isolation levels have different rules regarding snapshots and updates.

This lesson belongs to the **MVCC** chapter of the *Database Engine Relational PostgreSQL* module. It is a step-by-step hands-on lab using **two independent `psql` windows**, accompanied by explanations of expected results, important limitations to know, and observation patterns when using JDBC.

**After this lesson, you will be able to:**

- Explain why Session B cannot read uncommitted changes from Session A.
- Demonstrate that a transaction **sees changes made by itself** even when other sessions cannot see them yet.
- Observe `READ COMMITTED` taking a new snapshot across different statements.
- Observe `REPEATABLE READ` maintaining a stable snapshot within a transaction, even with newly inserted rows.
- Distinguish between **non-repeatable read**, **phantom read**, **row-lock blocking**, and **serialization failure `40001`**.
- See why PostgreSQL's `READ UNCOMMITTED` actually behaves like `READ COMMITTED`.
- Read `xmin`, `ctid`, and transaction-tracking fields as **technical traces**, without misunderstanding them as a complete business audit history.
- Design, clean up, and rerun a two-session experiment without leaving transactions open indefinitely.

> **Safety:** The `UPDATE`, `INSERT`, and `DELETE` statements in this lesson are intended exclusively for the dedicated `mvcc_lab` schema in a test database. Do not run them on production tables. Sections labeled "Session A" and "Session B" must be executed **interleaved across two independent connections**, rather than running them sequentially in one window and expecting concurrency behavior.

---

## 1. An Intuitive Model of MVCC

In a DBMS that uses MVCC, updating a row logically is not necessarily as simple as "immediately overwriting a single value that every session reads at the same time."

Suppose a row has the following data:

```text
SKU-A | stock = 10
```

Session A starts a transaction and updates stock to 7:

```text
Before update:

    version V1: SKU-A, stock=10

After UPDATE in transaction A, before COMMIT:

    version V1: SKU-A, stock=10    <-- may still be visible from an appropriate snapshot
    version V2: SKU-A, stock=7     <-- A's change, uncommitted
```

A regular query in Session B **does not read uncommitted data** from A. B can continue reading the committed version appropriate for its snapshot. After A commits, new snapshots can see the value 7.

This is only a **conceptual diagram**. PostgreSQL manages tuple versions, transaction IDs, commit status, snapshots, and dead-version cleanup according to specific internal rules. Do not assume that every `UPDATE` always leaves exactly two physical copies permanently.

### 1.1. Four Distinct Questions

| Question | Related Mechanism |
|---|---|
| Has a row been committed by another transaction? | Transaction visibility / commit status |
| Does the statement's snapshot see the new version? | Snapshot and isolation level |
| This transaction itself just modified the row; what does it see when reading again? | Self-visibility / statement ordering |
| What happens when two sessions' UPDATEs touch the same row? | Row locks, waiting, and update rules by isolation level |

**Do not equate "cannot see the new version" with "unaware of a lock."** A session can read the old version via a normal `SELECT`, but when it tries to modify the exact row currently locked by another transaction, the `UPDATE` statement must wait.

### 1.2. What Is a Snapshot?

A snapshot describes the set of changes/transactions considered visible at a logical point in time, according to MVCC and isolation rules. In PostgreSQL:

- Under `READ COMMITTED`, each normal **statement** starts with a new snapshot.
- Under `REPEATABLE READ` and `SERIALIZABLE`, normal read statements use the transaction's snapshot, which is established when the transaction snapshot is first acquired according to isolation rules.
- A transaction always has rules allowing it to see appropriate changes **performed by itself** earlier; a "fixed snapshot" does not mean it fails to see updates it just wrote itself.

**Note:** Typing `BEGIN` does not mean every isolation level has already captured the data snapshot right on the `BEGIN` line. With `REPEATABLE READ`, the snapshot is typically acquired when the first statement requiring a snapshot runs. Therefore, this lab orders `SELECT` statements very explicitly.

### 1.3. Isolation and Correctness Are Not a Single On/Off Switch

MVCC does not automatically solve every business problem:

- `READ COMMITTED` allows two reads within the same transaction to see newly committed data between statements.
- `REPEATABLE READ` stabilizes snapshot reads, yet a transaction that reads certain rows and then writes other rows can still encounter **write skew**.
- `SERIALIZABLE` guarantees committed outcomes equivalent to a valid serial execution order, but may reject a transaction with `SQLSTATE 40001` and require retrying the entire transaction.

This lesson focuses on **data visibility** and only introduces the write-contention effects necessary to interpret the lab results accurately.

---

## 2. Preparation: Two Connections and a Practice Table

### 2.1. Environment Prerequisites

You need:

1. A PostgreSQL server where you have privileges to create a schema and practice tables.
2. Two independent SQL terminals/windows connected to the **same database**.
3. An SQL execution tool, ideally `psql`, because it makes observing transactions and blocking commands straightforward.
4. Privileges to view/modify the `mvcc_lab` schema you create.

To avoid confusion:

```text
Terminal A -> Connection A -> PostgreSQL lab database
Terminal B -> Connection B -> PostgreSQL lab database
```

Two tabs inside an IDE may **share the same connection** depending on configuration. Make sure they are not sharing the same backend session before starting.

### 2.2. Connecting with psql

For example, both terminals run:

```bash
psql -h localhost -p 5432 -U lab_user -d lab_database
```

Replace `lab_user` and `lab_database` with your account and database. Do not put passwords directly in terminal commands or source code; use an authentication mechanism suitable for your environment.

In window A:

```sql
SELECT pg_backend_pid() AS session_a_pid;
```

In window B:

```sql
SELECT pg_backend_pid() AS session_b_pid;
```

The two PIDs must be **different**. You can label each session for easier monitoring:

**Session A:**

```sql
SET application_name = 'mvcc-lab-A';
```

**Session B:**

```sql
SET application_name = 'mvcc-lab-B';
```

### 2.3. Checking Isolation Status

Run in both sessions while no transaction is open:

```sql
SHOW default_transaction_isolation;
SHOW transaction_isolation;
SHOW transaction_read_only;
```

Usually the default configuration is `read committed`, but do not assume all servers are identical. The lab sections will **explicitly declare the isolation level in `BEGIN`** so they do not depend on session defaults.

### 2.4. Creating the Schema and Initial Data

Execute this block **once only**, while neither session has an open transaction:

```sql
CREATE SCHEMA IF NOT EXISTS mvcc_lab;

CREATE TABLE mvcc_lab.inventory (
    sku TEXT PRIMARY KEY,
    stock INTEGER NOT NULL CHECK (stock >= 0),
    description TEXT NOT NULL
);

CREATE TABLE mvcc_lab.inventory_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL REFERENCES mvcc_lab.inventory(sku),
    event_type TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

INSERT INTO mvcc_lab.inventory (sku, stock, description)
VALUES ('SKU-A', 10, 'MVCC test product')
ON CONFLICT (sku) DO UPDATE
SET stock = EXCLUDED.stock,
    description = EXCLUDED.description;
```

The first table has **one product** with an initial stock of 10. The second table stores events for testing how **newly INSERTed rows** are counted.

**Why only one product?** When the number of rows is small and the state is clear, it is much easier to prove what is being seen than testing on a large table with constantly changing data.

### 2.5. Reset Procedure Before Each Experiment

Only reset when **all transactions in both sessions have ended with `COMMIT` or `ROLLBACK`**; otherwise, the reset command might wait on a lock or produce confusing interleaved states.

```sql
-- Run in a session that is not inside an open lab transaction.
UPDATE mvcc_lab.inventory
SET stock = 10
WHERE sku = 'SKU-A';

DELETE FROM mvcc_lab.inventory_events;
```

The `DELETE` command empties the events table; the identity sequence may **not reset to 1** after deletion. The event-counting exercises only use `COUNT(*)`, so **do not assume `event_id` starts at 1**.

If you want to reset the identity sequence in your own lab, you can consider `TRUNCATE ... RESTART IDENTITY` after checking foreign keys, though it is **unnecessary** for these experiments.

### 2.6. Verifying the Baseline State

```sql
SELECT sku, stock
FROM mvcc_lab.inventory
ORDER BY sku;

SELECT COUNT(*) AS event_count
FROM mvcc_lab.inventory_events;
```

Baseline output:

```text
sku   | stock
------+------
SKU-A | 10

event_count = 0
```

### 2.7. Two-Session Execution Rules

- **Do not run all of A consecutively and then move to B.** A "stop here" instruction means keeping the transaction open so the other session can interleave.
- If a statement in B **blocks waiting for a lock**, switch to A to `COMMIT` or `ROLLBACK`, then observe B.
- After each scenario, end all transactions before resetting.
- If the `psql` prompt shows an errored transaction state or `current transaction is aborted`, run `ROLLBACK` in that session before continuing.
- Do not use an SQL tool that automatically commits every statement when testing scenarios that require keeping a transaction open; verify your client's autocommit/transaction settings.

---

## 3. Experiment 1 — Session B Cannot Read Uncommitted Changes

**Goal:** observe that **dirty reads are prevented**, while transaction A itself can still read the data it just modified.

Before running, reset stock to 10.

### Step 1 — Session A Starts a Transaction

**Run in A only:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT sku, stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

Result:

```text
SKU-A | 10
```

### Step 2 — Session A Updates Without Committing

**In A:**

```sql
UPDATE mvcc_lab.inventory
SET stock = 7
WHERE sku = 'SKU-A'
RETURNING sku, stock;
```

A's result:

```text
SKU-A | 7
```

Read again immediately in A:

```sql
SELECT sku, stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

A sees **7**. **Do not run `COMMIT` or `ROLLBACK` yet.**

### Step 3 — Session B Reads While A Is Uncommitted

**Switch to B:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT sku, stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

B sees:

```text
SKU-A | 10
```

**Why does B still see 10?** The `stock=7` version created by A belongs to an **uncommitted** transaction. A normal snapshot in B does not treat this update as confirmed data. Therefore, PostgreSQL selects the older `stock=10` version that remains visible.

### Step 4 — Session A ROLLBACK

**Return to A:**

```sql
ROLLBACK;
```

Now A's `stock=7` update has been canceled.

### Step 5 — Session B Reads Again and Finishes

**In B:**

```sql
SELECT sku, stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';

COMMIT;
```

B still sees `10`. After A's `ROLLBACK`, no new change became committed.

### Timeline Table

| Time | Session A | Session B | Value Seen by B |
|---|---|---|---|
| T0 | No open transaction | No open transaction | 10 |
| T1 | `BEGIN`, reads 10 | — | — |
| T2 | `UPDATE stock=7`, uncommitted | — | — |
| T3 | — | `SELECT` | **10** |
| T4 | `ROLLBACK` | — | — |
| T5 | — | `SELECT` again | **10** |

**Takeaway:** another session cannot read **uncommitted** values. A itself sees changes it made within its own transaction. These are two distinct rules to keep in mind at the same time.

---

## 4. Experiment 2 — READ COMMITTED Can See New Data on the Next Read

**Goal:** observe a **non-repeatable read** at `READ COMMITTED`: the same transaction B reads **the same row twice**, yet the value differs because transaction A committed in between.

Reset stock to `10` and ensure neither A nor B has an open transaction.

### Step 1 — Session B Starts and Performs First Read

**In B:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

B sees `10`. Keep B inside its transaction.

### Step 2 — Session A Updates and COMMITs

**In A:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

UPDATE mvcc_lab.inventory
SET stock = 6
WHERE sku = 'SKU-A'
RETURNING sku, stock;

COMMIT;
```

A has committed the value `6`. B is not continuously streaming reads; B's two `SELECT` statements are separated before and after this commit.

### Step 3 — Session B Reads a Second Time in the SAME Transaction

**In B:**

```sql
SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';

COMMIT;
```

This time B sees `6`, even though it opened its transaction when the value was still 10.

### Timeline Table

| Step | Session A | Session B | B's Result |
|---|---|---|---|
| 1 | — | `BEGIN READ COMMITTED`, `SELECT` | 10 |
| 2 | `UPDATE 6; COMMIT` | Has not re-read yet | — |
| 3 | — | Second `SELECT` | **6** |
| 4 | — | `COMMIT` | — |

### Why Does This Not Contradict MVCC?

MVCC does not promise that **every transaction sees a single snapshot from start to finish**. It provides the version visibility mechanism, while the **isolation level** determines which snapshot is used.

In PostgreSQL `READ COMMITTED`, each normal `SELECT` statement acquires a new snapshot when the statement begins. B's second query started **after A committed**, so it is allowed to see `stock=6`.

### The Non-Repeatable Read Concept

A `non-repeatable read` is a situation where a transaction reads the same row twice and observes **a changed value** caused by another transaction committing between the two reads.

Do not confuse it with:

- **Dirty read:** seeing uncommitted data from another transaction — Experiment 1 showed PostgreSQL does not allow that.
- **Phantom read:** re-running a query with a condition and seeing the set of **matching rows** change — Experiment 4 will illustrate this.

---

## 5. Experiment 3 — REPEATABLE READ Keeps the Old Snapshot Within the Same Transaction

**Goal:** repeat Experiment 2's scenario, switching B to `REPEATABLE READ` to see the difference.

Reset stock to `10` before starting.

### Step 1 — B Starts REPEATABLE READ and Reads

**In B:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

B sees `10`. This is B's first read statement requiring a data snapshot in this experiment. **Keep transaction B open.**

### Step 2 — A Updates and Commits

**In A:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

UPDATE mvcc_lab.inventory
SET stock = 4
WHERE sku = 'SKU-A'
RETURNING stock;

COMMIT;
```

A commits the value `4` successfully.

### Step 3 — B Reads a Second Time

**In B:**

```sql
SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

B **still sees `10`**. Even though A has committed, B is still using the snapshot associated with its `REPEATABLE READ` transaction, established before A committed.

### Step 4 — B Ends the Transaction and Performs a Fresh Read

**In B:**

```sql
COMMIT;

SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

The `SELECT` **after COMMIT** executes in a new transaction under `psql`'s default autocommit behavior, so it now sees **4**.

### Result Comparison Table

| Scenario | B's First Read | A Commits Update | B Re-reads While Transaction Open | B Reads in New Transaction |
|---|---:|---:|---:|---:|
| `READ COMMITTED` | 10 | 6 | **6** | 6 |
| `REPEATABLE READ` | 10 | 4 | **10** | 4 |

The two rows use **two separate resets and two separate test runs**. Do not compare 6 and 4 as if they appeared in the same execution schedule.

### 5.1. REPEATABLE READ Does Not Mean A Cannot Commit

A can still update and commit the row; B is simply **reading the old version matching its snapshot**. A normal `SELECT` in B does not automatically acquire a row lock blocking A the way `SELECT ... FOR UPDATE` does.

### 5.2. B Reads the New Value After Commit Because Snapshots Do Not Live Forever

Once B runs `COMMIT`/`ROLLBACK`, the old transaction and old snapshot are no longer the boundary for new reads. Starting a new transaction is the straightforward way to observe subsequently committed data.

### 5.3. Does Transaction B See Its Own Changes?

**Yes**, if B itself performs a valid write operation within the transaction, B's subsequent statements can see the changes it created. `REPEATABLE READ` fixes the view of changes made **by other transactions** according to the snapshot; it does not make a transaction blind to its own operations.

---

## 6. Experiment 4 — Newly INSERTed Records and the Phantom Phenomenon

**Goal:** instead of re-reading a value in the same row, re-run a `COUNT(*)` query to see whether the **number of matching rows** changes.

The `mvcc_lab.inventory_events` table was created at the beginning. Ensure no transaction is open, then reset:

```sql
DELETE FROM mvcc_lab.inventory_events;
```

### 6.1. Part A — READ COMMITTED Sees Newly COMMITted Rows

**Session B — start and count:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT COUNT(*) AS event_count
FROM mvcc_lab.inventory_events
WHERE sku = 'SKU-A';
```

Result: `0`.

**Session A — insert an event and commit:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

INSERT INTO mvcc_lab.inventory_events(sku, event_type)
VALUES ('SKU-A', 'received');

COMMIT;
```

**Session B — recount within the same transaction:**

```sql
SELECT COUNT(*) AS event_count
FROM mvcc_lab.inventory_events
WHERE sku = 'SKU-A';

COMMIT;
```

New result: **1**.

### 6.2. Why Is This Called a Phantom?

The first query for "number of events for SKU-A" returned no rows. After A committed, the exact same filter condition returned **one new row**.

```text
READ COMMITTED

B run 1: WHERE sku='SKU-A'  -> 0 rows
A:       INSERT + COMMIT
B run 2: WHERE sku='SKU-A'  -> 1 row
```

A **phantom read** is illustrated by a change in the set of rows matching a predicate, rather than merely changing a value inside an existing row.

### 6.3. Part B — REPEATABLE READ Does Not See Phantoms from A

Keep the one committed event from the previous part; you do not necessarily need to reset, just verify there is currently 1 event and no open transactions before starting.

**Session B — start and count:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS event_count
FROM mvcc_lab.inventory_events
WHERE sku = 'SKU-A';
```

Result: `1`.

**Session A — add a new event and commit:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

INSERT INTO mvcc_lab.inventory_events(sku, event_type)
VALUES ('SKU-A', 'sold');

COMMIT;
```

**Session B — recount while the REPEATABLE READ transaction is still open:**

```sql
SELECT COUNT(*) AS event_count
FROM mvcc_lab.inventory_events
WHERE sku = 'SKU-A';
```

B **still sees 1**. Next:

```sql
COMMIT;

SELECT COUNT(*) AS event_count
FROM mvcc_lab.inventory_events
WHERE sku = 'SKU-A';
```

The new read sees **2**.

### 6.4. Important Note on the Name "Phantom"

Across different database systems, isolation level names can imply different behaviors. In PostgreSQL, the `REPEATABLE READ` level uses snapshot isolation and **does not see new rows committed by other transactions** while the current transaction holds its snapshot.

However, that **does not prove that every outcome of two REPEATABLE READ transactions is serializable**. Write skew can still happen when two transactions read a shared set of data and then write to different rows.

---

## 7. Experiment 5 — UPDATE Waits for a Row Lock Even Though SELECT Still Reads the Old Version

**Goal:** understand why **data visibility** and **write concurrency** are two separate concerns.

Reset `stock=10` and end all prior transactions.

### Step 1 — Session A Modifies the Row and Holds the Transaction Open

**In A:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

UPDATE mvcc_lab.inventory
SET stock = stock - 2
WHERE sku = 'SKU-A'
RETURNING stock;
```

A sees `stock=8`. **Do not commit yet.**

### Step 2 — Session B Runs a Normal SELECT

**In B:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

B still sees **10**, because A's `8` is uncommitted.

### Step 3 — Session B Attempts to UPDATE the Same Row

**In B, send the following command and let it wait:**

```sql
UPDATE mvcc_lab.inventory
SET stock = stock - 3
WHERE sku = 'SKU-A'
RETURNING stock;
```

Normally the command **blocks and waits** because A holds a write lock on the same row. This is not B "dirty reading"; B is trying to **modify a row on which another transaction has not finished its modification**.

### Step 4 — Session A COMMITs to Release the Contention

**Switch to A:**

```sql
COMMIT;
```

A commits `stock=8`. B can now proceed with its waiting `UPDATE` statement.

### Step 5 — Session B Completes the UPDATE

**Switch to B to observe the output of the waiting command.**

```text
stock
-----
5
```

In this schedule, `READ COMMITTED` allows B's `UPDATE` to operate on the new row version after A commits, so subtracting `3` from `8` yields **5**. B finishes:

```sql
COMMIT;
```

### Timeline Table

| Time | Session A | Session B |
|---|---|---|
| T0 | stock=10 | stock=10 |
| T1 | `UPDATE stock=stock-2` → sees 8, uncommitted | — |
| T2 | — | Normal `SELECT` still sees 10 |
| T3 | — | `UPDATE stock=stock-3` waits |
| T4 | `COMMIT`, row becomes 8 | UPDATE resumes |
| T5 | — | UPDATE computes from 8 → **5**; `COMMIT` |

**Takeaway:** PostgreSQL does not force normal `SELECT` queries to wait on rows being modified just to read a committed version, whereas a concurrent `UPDATE` on the same row generally coordinates via locks and re-evaluates versions after waiting.

### 7.1. Why Didn't the Subtract-3 UPDATE Reuse the Old "10"?

Under `READ COMMITTED`, `UPDATE` has a mechanism for handling rows modified by another transaction while waiting: once the other transaction finishes, PostgreSQL can **re-evaluate the condition** against the appropriate new version.

This is why updates should be expressed relative to the current value:

```sql
SET stock = stock - 3
```

rather than:

```sql
SET stock = 7
```

if `7` was simply precomputed from an earlier `SELECT stock=10`. The second pattern can lead to an **application-level lost update** if you compute the final value from stale data without guards or concurrency control.

### 7.2. The WHERE Condition Must Also Be Re-Evaluated

A statement that should only deduct stock when enough inventory exists:

```sql
UPDATE mvcc_lab.inventory
SET stock = stock - 3
WHERE sku = 'SKU-A'
  AND stock >= 3
RETURNING stock;
```

If, while waiting, another transaction reduces stock below 3 and commits, the condition may no longer hold when the `UPDATE` resumes, so the result can be **`UPDATE 0`** instead of driving stock negative.

This is a very useful pattern for designing **conditional updates** in a single statement; you still need to check affected row counts, constraints, and related business rules.

---

## 8. Experiment 6 — READ COMMITTED Rechecks WHERE After Waiting

**Goal:** verify the `stock >= 3` condition on the new version of the row empirically rather than just reading the explanation.

Reset `stock=4`:

```sql
UPDATE mvcc_lab.inventory
SET stock = 4
WHERE sku = 'SKU-A';
```

### Step 1 — A Reduces from 4 to 1 and Holds the Transaction Open

**Session A:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

UPDATE mvcc_lab.inventory
SET stock = stock - 3
WHERE sku = 'SKU-A'
  AND stock >= 3
RETURNING stock;
```

A sees `stock=1`. Do not commit yet.

### Step 2 — B Attempts to Deduct 3 with the Same Condition

**Session B:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

UPDATE mvcc_lab.inventory
SET stock = stock - 3
WHERE sku = 'SKU-A'
  AND stock >= 3
RETURNING stock;
```

B **waits on A** for the same row.

### Step 3 — A COMMITs

**Session A:**

```sql
COMMIT;
```

### Step 4 — B Resumes Without Modifying the Row

**Session B:** observe the output:

```text
UPDATE 0
```

At this point the newly committed value is 1, so `stock >= 3` evaluates to **false**. B no longer has a matching row to update.

Finish B:

```sql
COMMIT;
```

Final state:

```sql
SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

Result: **1**, not negative.

### 8.1. What This Experiment Proves

- **An earlier SELECT** and a subsequent UPDATE can observe different states under `READ COMMITTED`.
- An UPDATE waiting on a lock can re-evaluate its condition so it does not modify a row that is no longer valid.
- `UPDATE 0` is **a statement that succeeded with zero rows modified**, not automatically a connection or serialization error.
- If you need to distinguish "insufficient stock" from "SKU does not exist," the application may need additional read logic inside an appropriate transaction.

### 8.2. Do Not Treat a WHERE Clause as a Database-Wide Invariant

`WHERE stock >= 3` guards the deduction performed by this specific statement. If another code path has permission to run `UPDATE stock=-5`, or if the table lacks `CHECK (stock>=0)`, you cannot conclude that every transaction enforces the inventory rule.

In our lab table, `CHECK (stock>=0)` adds a data-integrity layer. Database constraints and atomic conditions reinforce each other.

---

## 9. Experiment 7 — REPEATABLE READ and Concurrent UPDATE Can Raise SQLSTATE 40001

**Goal:** distinguish between "reading an old version from a snapshot" and "attempting to write a row already modified by another transaction after the snapshot."

Reset stock to `10` and close old transactions.

### Step 1 — B Opens REPEATABLE READ and Reads

**Session B:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

B sees `10`; B's snapshot is established.

### Step 2 — A Modifies the Same Row and Commits

**Session A:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

UPDATE mvcc_lab.inventory
SET stock = 8
WHERE sku = 'SKU-A';

COMMIT;
```

A commits `8` successfully.

### Step 3 — B Still Reads from the Old Snapshot

**Session B:**

```sql
SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

B still sees `10`.

### Step 4 — B Attempts to UPDATE the Row Modified After Its Snapshot

**Session B:**

```sql
UPDATE mvcc_lab.inventory
SET stock = stock - 1
WHERE sku = 'SKU-A'
RETURNING stock;
```

In this scenario, PostgreSQL under `REPEATABLE READ` will not simply proceed with the calculation against a newer version as in `READ COMMITTED`. The statement can fail with:

```text
ERROR: could not serialize access due to concurrent update
SQLSTATE: 40001
```

**Important:** `40001` can also occur under `REPEATABLE READ`, not only `SERIALIZABLE`.

### Step 5 — B Rolls Back and Retries in a New Transaction

**Session B:**

```sql
ROLLBACK;

BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

This time B sees `8`. If business rules still allow deducting 1:

```sql
UPDATE mvcc_lab.inventory
SET stock = stock - 1
WHERE sku = 'SKU-A'
  AND stock >= 1
RETURNING stock;

COMMIT;
```

After a valid retry, stock becomes **7**.

### 9.1. Why Not Retry Only the UPDATE?

If the application already checked stock or other conditions from the old snapshot, those conditions **must be re-read and re-evaluated** inside the new transaction. Do not merely rerun the failed statement while keeping decisions from the previous attempt.

Under `SERIALIZABLE`, PostgreSQL can also raise `40001` due to read-write dependencies across multiple transactions even when they do not UPDATE the same row.

### 9.2. After an Error, a Transaction Cannot Continue Normally

If you keep running `SELECT` inside an already aborted transaction, you may get:

```text
ERROR: current transaction is aborted,
       commands ignored until end of transaction block
SQLSTATE: 25P02
```

This is **the aborted state of the transaction**, not the original root cause. You must `ROLLBACK` and look at the original SQLSTATE, such as `40001`.

---

## 10. Experiment 8 — READ UNCOMMITTED in PostgreSQL Does Not Do Dirty Reads

The SQL standard defines a `READ UNCOMMITTED` level, often described as allowing uncommitted changes to be read in some DBMSs. However, **PostgreSQL treats `READ UNCOMMITTED` like `READ COMMITTED`** for key observable MVCC behaviors.

Reset stock to `10`.

### Step 1 — A Runs UPDATE Without Committing

**Session A:**

```sql
BEGIN;

UPDATE mvcc_lab.inventory
SET stock = 3
WHERE sku = 'SKU-A';
```

Keep A open.

### Step 2 — B Sets READ UNCOMMITTED and Reads

**Session B:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;

SHOW transaction_isolation;

SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

`SHOW transaction_isolation` may display the label `read uncommitted` because you requested that level, yet **PostgreSQL's read behavior remains identical to `READ COMMITTED`**: B sees **10**, not the uncommitted `3`.

### Step 3 — A COMMITs, B Reads Again

**Session A:**

```sql
COMMIT;
```

**Session B:**

```sql
SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';

COMMIT;
```

B now sees **3**, just like the `READ COMMITTED` experiment: the new `SELECT` acquires a new snapshot.

### 10.1. Lesson About Isolation Levels on Paper

Do not infer how a server behaves solely from the isolation level name. PostgreSQL has specific rules:

- `READ UNCOMMITTED` behaves like `READ COMMITTED`.
- `REPEATABLE READ` does not allow phantoms under PostgreSQL's snapshot implementation, even though generic isolation-level tables sometimes classify it differently.
- `SERIALIZABLE` uses Serializable Snapshot Isolation and can reject conflicting transactions with `40001`.

---

## 11. Experiment 9 — Uncommitted DELETE and Row Appearance/Disappearance

Earlier experiments changed a row's **value**. Now try deleting the entire row to observe visibility when a row may be marked for deletion while the transaction is still uncommitted.

Reset inventory: ensure `SKU-A` exists with `stock=10` and no open transactions. If you ran the previous parts in order without deleting it, simply run:

```sql
UPDATE mvcc_lab.inventory
SET stock = 10
WHERE sku = 'SKU-A';
```

### 11.1. A Deletes Without Committing

**Session A:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

DELETE FROM mvcc_lab.inventory
WHERE sku = 'SKU-A'
RETURNING sku, stock;
```

If no rows in `inventory_events` reference `SKU-A`, the delete can succeed. **If event rows remain from Experiment 4, the default foreign key will reject the DELETE.** In the lab, before this step you must run **`DELETE FROM mvcc_lab.inventory_events;` while neither session has an open transaction**.

A will no longer see the `SKU-A` row in A's own subsequent `SELECT`:

```sql
SELECT sku, stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

Result: **0 rows** in A.

### 11.2. B Still Sees the Row Not Yet Deleted by a Commit

**Session B:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT sku, stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

B still sees **SKU-A, stock=10** because A's `DELETE` has not committed yet.

### 11.3. A Rolls Back

**Session A:**

```sql
ROLLBACK;
```

**Session B:**

```sql
SELECT sku, stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';

COMMIT;
```

B still sees `SKU-A`.

### 11.4. What If A COMMITs Instead of ROLLBACK?

With the same scenario except A runs `COMMIT`, B under `READ COMMITTED` will observe:

- `SELECT` before A's commit: the `SKU-A` row is still present.
- `SELECT` after A's commit: **0 rows**.

This is the visibility of a `DELETE` operation: an uncommitted deletion **does not immediately vanish from all other snapshots**.

### 11.5. Which Constraints Still Apply?

A `DELETE` operation can still:

- Be rejected by a foreign key if child rows still reference it.
- Fire triggers.
- Wait on row locks.
- Lead to `40001` if a transaction uses an older snapshot and encounters a concurrent update under the applicable isolation level.

MVCC explains part of visibility; it **does not bypass data integrity constraints**.

---

## 12. Experiment 10 — A Transaction Sees Its Own Changes

"Fixed snapshot" sometimes misleads learners into thinking a transaction cannot read what it just wrote. PostgreSQL allows a transaction to see **its own prior changes** according to statement visibility rules.

Ensure `SKU-A` exists, reset `stock=10`, with no open transactions:

```sql
INSERT INTO mvcc_lab.inventory (sku, stock, description)
VALUES ('SKU-A', 10, 'MVCC test product')
ON CONFLICT (sku) DO UPDATE
SET stock = EXCLUDED.stock;
```

### 12.1. Within the Same REPEATABLE READ Transaction

**Run in Session A:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';

UPDATE mvcc_lab.inventory
SET stock = 9
WHERE sku = 'SKU-A'
RETURNING stock;

SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';

ROLLBACK;
```

Results in sequence:

```text
First SELECT     -> 10
UPDATE RETURNING -> 9
Second SELECT    -> 9
ROLLBACK         -> outside the transaction remains 10
```

### 12.2. Why Does This Not Contradict REPEATABLE READ?

A transaction's snapshot controls what is visible **from other transactions**. Changes performed by the transaction itself in earlier statements are still considered part of the valid state that the transaction must be able to read.

If that were not true, a transaction could not intuitively perform:

```text
INSERT order
INSERT order_items pointing to the newly inserted order
SELECT the newly inserted order
COMMIT
```

MVCC does not turn a transaction's own writes into invisible data for that same transaction.

### 12.3. Caution Regarding a Single Statement with Multiple Data-Modifying Branches

Do not generalize "later statements see earlier writes" into claiming that every subquery or write clause inside **the same complex SQL statement** sees each other's modifications in written order. In data-modifying CTEs, PostgreSQL has specific snapshot/`RETURNING` rules. When you need to pass newly written rows to logic within the same statement, prefer `RETURNING` and consult the documentation for that statement form.

---

## 13. Summary Table Comparing Visibility Scenarios

Assume stock starts at `10` in each scenario and A updates it to `7`.

| Read Timing in B | `READ COMMITTED` | `REPEATABLE READ` with Snapshot Taken Before Commit |
|---|---|---|
| A uncommitted, B runs SELECT | 10 | 10 |
| A commits, B runs new SELECT in the **same** transaction B | **7** | **10** |
| B ends transaction, runs SELECT in a new transaction | **7** | **7** |
| B itself UPDATEs row in a valid transaction, then runs SELECT | Sees B's change | Sees B's change |
| B UPDATEs row already modified by A after B's snapshot | May wait/recheck under `READ COMMITTED` semantics | May hit **`40001`** |

**Table precondition:** B under `REPEATABLE READ` must have already read and established its snapshot **before A committed**. If B only typed `BEGIN REPEATABLE READ` without running any statement requiring a snapshot until after A committed, it may see A's committed data on its very first read.

### 13.1. A Visual Timeline

```text
Time ──────────────────────────────────────────────────►

Session A:
  BEGIN ── UPDATE stock=7 ─────── COMMIT
                  |                  |
                  |                  +── new committed version
                  +── new uncommitted version

Session B / READ COMMITTED:
          SELECT -> 10                 SELECT -> 7
          snapshot B1                  snapshot B2

Session B / REPEATABLE READ:
          SELECT -> 10                 SELECT -> 10
          snapshot BRR                 same snapshot BRR
                                                   COMMIT
                                                       |
                                                       v
                                                  SELECT -> 7
                                                  new snapshot
```

### 13.2. Why Use the Word "May" When Discussing UPDATE?

A contending `UPDATE` depends on whether the row changed, whether the other transaction committed or rolled back, the isolation level, and the current predicate. For example:

- Another transaction holds a row lock: it may **wait**.
- That transaction rolls back: the other session may proceed from the pre-update state.
- That transaction commits: `READ COMMITTED` may **recheck** the row after the update.
- An older `REPEATABLE READ` snapshot encounters a changed row: it may **be rejected with 40001**.
- If `NOWAIT` or `lock_timeout` is configured in a relevant context, waiting may turn into a different error.

Do not write tests assuming every concurrent schedule produces one exact exception without controlling step ordering.

---

## 14. Inspecting Tuple Version Traces: xmin, xmax, and ctid

PostgreSQL lets you read several **system columns** on rows:

- `xmin`: ID of the transaction that inserted the row version.
- `xmax`: system field related to the transaction deleting/locking the tuple, though **you cannot directly infer "the row was deleted" solely from `xmax` being non-zero**.
- `ctid`: current physical location of the tuple version within the table.

### 14.1. Reading Row Metadata

```sql
SELECT
    sku,
    stock,
    xmin,
    xmax,
    ctid
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

Example output might look like:

```text
sku   | stock | xmin | xmax | ctid
------+-------+------+------+-------
SKU-A | 10    | 8452 | 0    | (0,7)
```

**The numbers in the table are illustrative only**, not exact values your machine needs to match.

### 14.2. Observing Before and After UPDATE

When all other transactions have ended:

```sql
BEGIN;

SELECT xmin, xmax, ctid, stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';

UPDATE mvcc_lab.inventory
SET stock = stock + 1
WHERE sku = 'SKU-A'
RETURNING xmin, xmax, ctid, stock;

ROLLBACK;
```

`UPDATE RETURNING` lets you observe the tuple version created/used by the transaction itself. `xmin` and `ctid` values may differ from the previous version, reflecting the creation of a new row version under MVCC.

### 14.3. Very Important Limitations When Reading System Columns

**Do not** use `xmin`, `xmax`, or `ctid` on their own as:

- A business primary key.
- A stable historical ID across `VACUUM FULL`/table rewrites or physical moves.
- Proof that a transaction committed merely because `xmin` is present.
- A way to determine a row was deleted solely because `xmax <> 0`.
- A long-term version history source replacing an audit log.

`xmax` can reflect row locking, MultiXact IDs, and other internal states. `ctid` can change when a row is updated or a table is rewritten. Transaction IDs are also subject to wraparound and freezing. These fields are helpful for **learning and diagnostics**, not as the sole basis for business actions.

### 14.4. Why Isn't xmin Required to Understand MVCC?

Hands-on experiments can demonstrate the essential mechanics through **the values returned by `SELECT`**, `COMMIT` timing, and isolation levels alone. System columns merely offer an extra lens into row versions; learners do not need to decode tuple status bits from SQL to understand what becomes visible.

---

## 15. Sessions, Transactions, and Snapshots in psql

### 15.1. A Session Is Not the Same as a Transaction

One **session/connection** can execute many consecutive transactions:

```sql
BEGIN;
SELECT ...;
COMMIT;

BEGIN;
SELECT ...;
ROLLBACK;
```

Having the same `pg_backend_pid()` does not mean statements across two consecutive transactions share the same snapshot. Transaction boundaries are one of the key factors determining visibility.

### 15.2. psql Autocommit

In the typical configuration, when you run:

```sql
SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

**without writing `BEGIN`**, the client/server executes the statement inside an implicit transaction and finishes it right away. Thus, two standalone `SELECT` commands can see different snapshots.

When you need to hold a snapshot across multiple statements to observe `REPEATABLE READ`, you must use an explicit `BEGIN`/`COMMIT` and prevent your IDE from splitting them into separate transactions.

### 15.3. Checking Isolation Inside a Transaction

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SHOW transaction_isolation;

ROLLBACK;
```

In this example, the output is `repeatable read`. Running `SHOW` verifies the setting, but **the execution order of data queries** is what determines whether the lab snapshot is established before or after A's commit.

### 15.4. Setting Isolation Before Running Business Queries

You can write:

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT ...

COMMIT;
```

`SET TRANSACTION` must be placed **before the relevant query/modification statements** in the transaction per PostgreSQL rules; do not attempt to change isolation mid-transaction and expect previously read statements to be re-evaluated.

### 15.5. Why Does now() Not Prove a New Snapshot?

In PostgreSQL, `now()` / `CURRENT_TIMESTAMP` reflects the **start time of the current transaction** per function semantics, whereas `clock_timestamp()` returns the wall-clock time at the moment of invocation.

```sql
BEGIN;

SELECT now() AS transaction_time,
       clock_timestamp() AS wall_clock_time;

-- Try again after performing operations for a moment within the same transaction.
SELECT now() AS transaction_time,
       clock_timestamp() AS wall_clock_time;

ROLLBACK;
```

`now()` can stay constant while `clock_timestamp()` advances. Still, **do not** equate `now()` or `clock_timestamp()` with an "MVCC snapshot ID." Time-function values and the set of visible transactions are two different things.

---

## 16. Observing Sessions Holding Transactions and Locks

### 16.1. pg_stat_activity

In a separate monitoring session, with sufficient privileges, you can inspect:

```sql
SELECT
    pid,
    application_name,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
  AND application_name IN ('mvcc-lab-A', 'mvcc-lab-B')
ORDER BY application_name;
```

Useful columns:

- `pid`: the session's backend process ID.
- `state`: e.g., `active`, `idle`, `idle in transaction`.
- `xact_start`: when the current transaction began, if one is active.
- `wait_event_type` / `wait_event`: helps show whether the session is waiting on an event or lock.

**Privilege note:** A role may not be able to view full details of other sessions. Use appropriate monitoring privileges; do not attempt to collect sensitive query text without authorization.

### 16.2. Seeing Who Is Blocking Whom

When B is waiting during the same-row `UPDATE` experiment, from another monitoring session you can run:

```sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids
FROM pg_stat_activity
WHERE datname = current_database()
  AND application_name IN ('mvcc-lab-A', 'mvcc-lab-B')
ORDER BY application_name;
```

`pg_blocking_pids(pid)` helps identify which PIDs are blocking the inspected session in lock scenarios. Results depend on timing and wait type; if A already committed before you check, no blocker will appear.

### 16.3. pg_locks and Lock Modes

```sql
SELECT
    l.pid,
    a.application_name,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a ON a.pid = l.pid
WHERE a.application_name IN ('mvcc-lab-A', 'mvcc-lab-B')
ORDER BY a.application_name, l.locktype, l.mode;
```

PostgreSQL uses many internal lock types; a wait on a row update may not show up in `pg_locks` exactly as you initially guess, because it can involve waiting on a transaction ID. To answer "who is blocking whom," `pg_blocking_pids` is usually clearer.

### 16.4. Idle in Transaction Is an Operational Signal

A long-open transaction can hold back an old snapshot and delay cleanup of tuple versions that the system must preserve for that snapshot. Therefore:

- Do not leave the two lab sessions sitting `idle in transaction` and forget about them.
- Finish every transaction at the end of each scenario.
- In applications, keep transactions short and do not wait on user input or HTTP requests while a transaction remains open.
- Use monitoring and appropriate timeouts according to system policy.

Never kill another backend simply because its transaction looks long; first understand what it is doing and the consequences of terminating it.

---

## 17. MVCC, VACUUM, and Expired Row Versions

If `UPDATE` generally creates a new tuple version, old versions cannot accumulate without bound forever. PostgreSQL uses **VACUUM / autovacuum** to reclaim or mark storage space as reusable once no active snapshot still needs those versions.

### 17.1. High-Level Lifecycle Diagram

```text
INSERT version V1
        |
      COMMIT
        |
      UPDATE
        |
        +--- V1 may be needed by older snapshots
        |
        +--- new V2 is created
                  |
                COMMIT
                  |
        older snapshots gradually finish
                  |
          VACUUM can reclaim
          versions no longer needed
```

### 17.2. Long Transactions Affect Cleanup

A session held open under `REPEATABLE READ` for a long time may still need to read superseded versions while other transactions update the table. To preserve consistent visibility, PostgreSQL may have to keep old versions around longer.

This can affect:

- Number of dead tuples and table/index bloat.
- Autovacuum workload.
- I/O volume and cache efficiency.
- Query performance in write-heavy workloads.

Do not assume a tiny lab experiment causes noticeable bloat, but it is a key reason not to hold transactions open in real environments.

### 17.3. Dead Tuple Statistics Are Estimates

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum
FROM pg_stat_user_tables
WHERE schemaname = 'mvcc_lab'
ORDER BY relname;
```

`n_dead_tup` is a **statistic/estimate**, not an exact real-time count of every dead version. The figures lag and depend on the statistics collector mechanism.

### 17.4. VACUUM Never Causes Old Snapshots to Read New Data by Mistake

PostgreSQL must retain versions still required by MVCC visibility rules. Vacuum cannot arbitrarily break the correctness of a valid active transaction.

`VACUUM` can normally run concurrently with regular activity, though you should not force aggressive maintenance operations in the middle of a concurrency lab. Commands like `VACUUM FULL` differ in locking and table-rewriting behavior and are not needed for this lesson.

---

## 18. From Two psql Sessions to Two JDBC Connections

Fundamentally, "Session A and Session B" correspond to **two separate database connections**. In Java, each connection manages an independent transaction.

### 18.1. Example Opening Two Connections

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class MvccConnections {
    public static void showSessionIds(DataSource dataSource)
            throws SQLException {
        try (Connection a = dataSource.getConnection();
             Connection b = dataSource.getConnection()) {

            System.out.println("A PID = " + backendPid(a));
            System.out.println("B PID = " + backendPid(b));
        }
    }

    private static int backendPid(Connection connection)
            throws SQLException {
        try (PreparedStatement ps =
                 connection.prepareStatement(
                     "SELECT pg_backend_pid()"
                 );
             ResultSet rs = ps.executeQuery()) {
            rs.next();
            return rs.getInt(1);
        }
    }
}
```

Two `Connection` instances opened simultaneously from a pool usually map to two distinct PostgreSQL backends, though you should verify actual PIDs/drivers/proxies in your application environment. Do not use the same JDBC connection concurrently from two threads and treat it as two independent sessions.

### 18.2. Setting Isolation and Disabling Autocommit

```java
try (Connection conn = dataSource.getConnection()) {
    conn.setTransactionIsolation(
        Connection.TRANSACTION_REPEATABLE_READ
    );
    conn.setAutoCommit(false);

    try {
        // SELECT and UPDATE within the same transaction.
        conn.commit();
    } catch (SQLException e) {
        try {
            conn.rollback();
        } catch (SQLException rollbackError) {
            e.addSuppressed(rollbackError);
        }
        throw e;
    }
}
```

Configure isolation and transaction boundaries before business statements. When using a transaction-management framework, follow the framework's rules instead of manually calling `commit` on a framework-managed connection.

### 18.3. Reading Stock with PreparedStatement

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public static int readStock(Connection conn, String sku)
        throws SQLException {
    String sql = """
        SELECT stock
        FROM mvcc_lab.inventory
        WHERE sku = ?
        """;
    try (PreparedStatement ps =
             conn.prepareStatement(sql)) {
        ps.setString(1, sku);
        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                throw new SQLException(
                    "SKU not found: " + sku
                );
            }
            return rs.getInt("stock");
        }
    }
}
```

This snippet is an illustrative method that can be placed inside a Java class; it uses text blocks (Java 15+). The SKU input is **bound as a parameter**, not concatenated directly into SQL.

### 18.4. Synchronizing Two Connections in an Integration Test

In Java tests, you can use `CountDownLatch` or `CyclicBarrier`:

```text
Thread A / Connection A:
    BEGIN
    UPDATE stock=7
    signal("A has updated but not committed")
    await("B has read old value")
    COMMIT

Thread B / Connection B:
    BEGIN READ COMMITTED
    await("A has updated but not committed")
    SELECT stock -> expect 10
    signal("B has read old value")
    await("A committed")
    SELECT stock -> expect 7
    COMMIT
```

This is **coordination pseudocode**, not a complete program. Real tests must include timeouts on barriers, exception handling on both threads, rollback/close in `finally`, and must never leave connections waiting indefinitely.

### 18.5. Do Not Confuse Framework Transactions with HTTP Requests

An HTTP request does not inherently correspond to a single PostgreSQL transaction. One service might open multiple connections or separate transactions; a framework might auto-commit before the response returns. When observing visibility, identify **where the transaction actually begins and ends**, not just the Java method name.

---

## 19. Common Misconceptions in Two-Session Experiments

**1. "When A runs UPDATE, B immediately sees the new value."** False if A has not committed yet. B's snapshot does not read uncommitted data.

**2. "READ COMMITTED takes a snapshot exactly once at BEGIN."** False. Regular statements acquire new snapshots.

**3. "REPEATABLE READ always takes its snapshot right at the BEGIN keyword."** Not necessarily; the snapshot is established when the first statement needing a snapshot runs according to isolation rules.

**4. "A REPEATABLE READ transaction cannot see changes it created itself."** False. It can see its own earlier writes.

**5. "Two SELECT statements under READ COMMITTED always return the same number."** False if another transaction commits between the two statements.

**6. "READ UNCOMMITTED in PostgreSQL allows dirty reads."** False. PostgreSQL handles this level equivalently to READ COMMITTED.

**7. "Because B's SELECT didn't wait for A's UPDATE, B's UPDATE won't wait either."** False. Normal reads and concurrent writes follow different rules.

**8. "B's UPDATE will definitely use stock=10 that B's earlier SELECT saw."** No. Under READ COMMITTED, UPDATE can process the new version after waiting and recheck its condition.

**9. "UPDATE 0 means the transaction rolled back."** No. It can simply be a successful statement where no row satisfied WHERE.

**10. "REPEATABLE READ can UPDATE any row even if modified after the snapshot."** No. It can hit `40001` due to a concurrent update.

**11. "SQLSTATE 40001 only happens under SERIALIZABLE."** False. REPEATABLE READ can raise it too.

**12. "When hitting 40001, just retry the final UPDATE statement."** False. Read/decision logic in the new transaction may produce a different outcome.

**13. "One IDE window definitely equals one connection."** No. Verify PID or session configuration.

**14. "Having two UI tabs means having two PostgreSQL sessions."** Not if they share the same underlying connection.

**15. "BEGIN under READ COMMITTED freezes all data until COMMIT."** No. Each statement gets its own snapshot.

**16. "Under REPEATABLE READ, A's commit is blocked because B is running a normal SELECT."** No. Normal SELECT does not hold row locks blocking every UPDATE; it reads the old version instead.

**17. "Seeing non-zero xmax means the row was definitely deleted."** No. xmax can be used for row locks, MultiXact IDs, and internal meanings.

**18. "ctid is a permanent ID for a row."** False. It is a physical tuple location that can change.

**19. "xmin is enough to replace an audit log."** No. It does not capture who changed what or why, and it is not stable like a business identifier.

**20. "VACUUM must keep every row version forever to support MVCC."** No. It only preserves versions still required by visibility rules; dead versions can be reclaimed.

**21. "Just keep a REPEATABLE READ transaction open all day for consistent data."** Operationally harmful; long transactions strain tuple cleanup and system resources.

**22. "A SELECT COUNT on an old snapshot always proves the current state of the whole database."** No. It only reflects the rows visible to that query/transaction's snapshot.

**23. "With a foreign key, A's DELETE always succeeds in the lab."** No. Child rows in `inventory_events` referencing `inventory` can block deleting the parent row.

**24. "READ COMMITTED automatically guarantees all multi-row invariants."** No. Constraints, row locks, transaction logic, or SERIALIZABLE may be required.

**25. "A READ ONLY transaction can never increase MVCC overhead."** No. A long-lived read snapshot can hinder cleanup of old versions.

**26. "SHOW transaction_isolation returning read uncommitted proves dirty reads occur."** No. That is only the requested setting label; PostgreSQL's behavior matches READ COMMITTED.

**27. "If now() changes, that means a new snapshot."** No. Time functions and snapshots are not the same thing.

**28. "After B runs COMMIT, the next SELECT still uses B's prior snapshot."** No. Under regular autocommit, the next SELECT runs in a new transaction.

**29. "A test running two SQL blocks sequentially is a concurrency test."** No. You need two connections and interleaved ordering.

**30. "Passing an experiment on a tiny table means production will never see deadlocks or serialization failures."** No. Scale, timing, and access patterns drive contention.

---

## 20. Practice Exercises with Answers

### Exercise 1 — Dirty Read

Session A ran `UPDATE stock=7` without committing. What does Session B under `READ COMMITTED` read if the previously committed value was 10?

**Answer:** B reads **10**, because it cannot see A's uncommitted change.

### Exercise 2 — Does a Transaction See Its Own Update?

Session A just ran `UPDATE stock=7` and runs `SELECT` again before `COMMIT`.

**Answer:** A reads **7** according to self-visibility rules.

### Exercise 3 — A Rolls Back

A left value 7 uncommitted and ran `ROLLBACK`. B reads again under READ COMMITTED.

**Answer:** B still reads **10** assuming no other transaction modified that row.

### Exercise 4 — Non-Repeatable Read

B runs `BEGIN READ COMMITTED` and `SELECT`s `stock=10`. A updates `stock=6` and `COMMIT`s. B runs `SELECT` again in the same transaction.

**Answer:** B sees **6** on the second read. READ COMMITTED takes a new snapshot for each regular SELECT.

### Exercise 5 — REPEATABLE READ

Same scenario as Exercise 4, except B uses REPEATABLE READ and ran its first SELECT before A committed.

**Answer:** B's second read is still **10**. B only sees **6** in a new transaction after ending the old one.

### Exercise 6 — When Does a Snapshot Start?

B runs `BEGIN REPEATABLE READ`, **does not SELECT yet**, A commits an update, and then B runs its first SELECT.

**Answer:** B can see the new value committed by A, because the snapshot for a REPEATABLE READ transaction is taken when the first statement needing a snapshot executes, not necessarily right when `BEGIN` is typed.

### Exercise 7 — Phantom Under READ COMMITTED

B counts 0 events for `SKU-A`. A INSERTs a `SKU-A` event and COMMITs. B recounts inside the same READ COMMITTED transaction.

**Answer:** B can see **1** row; this is an example of a phantom read.

### Exercise 8 — Phantom Under REPEATABLE READ

B counted 0 before A ran `INSERT + COMMIT`. B recounts inside its REPEATABLE READ transaction.

**Answer:** B still sees **0** under its old snapshot; a new transaction will see the newly committed row.

### Exercise 9 — UPDATE vs SELECT

Why does B's SELECT still read 10 while A has an uncommitted UPDATE, whereas B's UPDATE on the same row blocks?

**Answer:** Regular SELECT can read the older row version matching its snapshot, while UPDATE must coordinate row locks to prevent inconsistent concurrent writes to the same row.

### Exercise 10 — Rechecking WHERE

Initial stock is 4. A deducts 3 without committing; B tries to deduct 3 with `WHERE stock >= 3`. A commits, and B resumes.

**Answer:** B can receive `UPDATE 0`, because the newly committed stock is only 1 and no longer satisfies the condition to deduct more.

### Exercise 11 — REPEATABLE READ Concurrent Update

B has taken a snapshot with `stock=10`. A changes it to 8 and commits. B updates the same SKU row inside its REPEATABLE READ transaction.

**Answer:** B can receive `SQLSTATE 40001` (concurrent update). It must roll back, open a new transaction, and re-evaluate its decision.

### Exercise 12 — READ UNCOMMITTED

B uses `BEGIN ISOLATION LEVEL READ UNCOMMITTED` in PostgreSQL. A has an uncommitted `stock=3`.

**Answer:** B does **not** see 3; PostgreSQL implements this level's behavior like READ COMMITTED.

### Exercise 13 — Transaction State After an Error

B hits `40001`, then runs another SELECT and gets `25P02`.

**Answer:** The transaction is already aborted; `25P02` is a consequence. You must roll back and inspect the original `40001` error.

### Exercise 14 — Uncommitted DELETE

A runs `DELETE` on `SKU-A` without committing; B runs a normal SELECT under READ COMMITTED.

**Answer:** B can still see `SKU-A` from the committed version matching its snapshot, assuming A was allowed to DELETE (not blocked by a foreign key or trigger).

### Exercise 15 — xmin and xmax

If `xmax` is non-zero, can you conclude the row has been deleted and committed?

**Answer:** No. `xmax` can reflect lock/MultiXact information and internal states. Never use it as sole proof of a committed deletion.

### Exercise 16 — ctid

Can `ctid` be stored as a stable product identifier?

**Answer:** No. `ctid` is the physical location of a tuple version and can change on `UPDATE` or table rewrite; use a business key like `sku`.

### Exercise 17 — Isolation via JDBC

**Task:** set a JDBC connection to REPEATABLE READ.

**Answer:**

```java
conn.setTransactionIsolation(
    Connection.TRANSACTION_REPEATABLE_READ
);
conn.setAutoCommit(false);
```

Set this before business statements and end with commit/rollback.

### Exercise 18 — Are Two Tabs Two Sessions?

**Answer:** Not guaranteed. Run `SELECT pg_backend_pid();` in each tab. If they show the same backend PID concurrently, they are not the two independent PostgreSQL connections needed for the lab.

### Exercise 19 — Monitoring Waiting Sessions

**Task:** identify which session is blocking another.

**Suggested Answer:**

```sql
SELECT
    pid,
    application_name,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids
FROM pg_stat_activity
WHERE datname = current_database();
```

Results depend on monitoring privileges and whether the blocking situation is still active.

### Exercise 20 — Why Not Leave a Lab Transaction Open for an Hour?

**Answer:** Long transactions can pin old snapshots and delay reclamation of needed tuple versions, increasing pressure on autovacuum, bloat, and system resources. End transactions immediately after each experiment.

### Exercise 21 — Distinguishing Time Functions from Snapshots

In a long transaction, `now()` stays unchanged across `SELECT` statements while `clock_timestamp()` increases.

**Answer:** `now()` is tied to transaction start time; `clock_timestamp()` reflects the wall clock at call time. Do not infer whether an MVCC snapshot is new or old directly from those values.

### Exercise 22 — Can a Transaction Hold an Old Read Snapshot and Still Write?

**Answer:** It depends on the rows written and the isolation level. A REPEATABLE READ transaction can write non-conflicting rows, but trying to update a row modified after its snapshot can raise `40001`. Stable reads do not mean every write will succeed.

### Exercise 23 — Does Serializable Always Return 40001?

**Answer:** No. SERIALIZABLE transactions commit normally whenever the concurrent schedule is valid; `40001` only appears when PostgreSQL must reject a transaction to preserve serialization guarantees.

### Exercise 24 — Where Does a SELECT Run?

An application first reads stock in transaction 1, closes the transaction, and then reads again in transaction 2.

**Answer:** Two separate transactions can have different snapshots even when using the same connection/session. Do not confuse connection identity with transaction snapshot identity.

---

## 21. Checklist for Running a Two-Session MVCC Lab

### Before Testing

1. **Use a test database:** never use tables containing production data.
2. **Two independent connections:** verify `pg_backend_pid()`.
3. **Same database:** avoid accidentally connecting A and B to two different databases.
4. **Dedicated schema:** `mvcc_lab`, avoiding impact on others' tables.
5. **Clear initial state:** `SKU-A stock=10`, known event count.
6. **No leftover transactions:** close A and B before resetting.
7. **Intentional isolation level:** declare it in `BEGIN`.
8. **Clear autocommit behavior:** ensure your IDE/`psql` does not split transactions meant to stay open.

### During Testing

9. **Interleave in the exact order:** while A holds a transaction open, switch to B.
10. **Record values and COMMIT timing:** do not just copy SQL statements.
11. **Distinguish SELECT from UPDATE:** one reads an old version, while the other may wait on a lock.
12. **Predict before running:** check predictions against dirty read, non-repeatable read, and phantom read behavior.
13. **If B is waiting:** switch back to A to finish its transaction instead of opening extra unnecessary transactions.
14. **If 40001 occurs:** roll back and recompute decisions in a fresh transaction.
15. **If 25P02 occurs:** look up the initial error and roll back before trying again.
16. **If DELETE is blocked by FK:** clear the lab event rows first rather than disabling constraints.
17. **Never rely on row return order without an ORDER BY.**

### After Testing

18. **COMMIT/ROLLBACK all sessions:** never leave sessions idle in transaction.
19. **Reset data before new scenarios:** avoid stale state corrupting the next experiment.
20. **Note isolation and snapshot timing:** especially with REPEATABLE READ.
21. **Do not treat xmin/xmax/ctid as business data:** use them only for learning/observation.
22. **Distinguish new transactions from existing sessions:** one session runs many transactions.
23. **Do not treat one test as proof of all concurrent schedules:** you need multiple tests with controlled conflict patterns.
24. **Release resources:** close terminals/connections when finished.

---

## 22. Summary in Four Memorable Rules

**Rule 1 — Uncommitted changes are invisible to other sessions.** A transaction can read back what **it just wrote itself**, but other transactions do not read dirty data via normal `SELECT` in PostgreSQL.

**Rule 2 — Isolation determines the snapshot.** `READ COMMITTED` typically acquires a snapshot **per statement**, so two reads in the same transaction can see different values. `REPEATABLE READ` uses a stable snapshot for regular reads, so data committed by A after B's snapshot does not appear in B until a new transaction starts.

**Rule 3 — Reads and writes have different concurrency behavior.** B can read an old version while A holds a lock, whereas when B runs `UPDATE` on the same row it may have to **wait**, **recheck WHERE**, or receive **`40001`**, depending on isolation and write order.

**Rule 4 — MVCC is a visibility mechanism, not the entirety of business rules.** MVCC together with isolation levels supports consistency, but you still need constraints, proper transaction boundaries, retry handling, appropriate locks, and business checks to protect data integrity.

If you remember only one experiment, remember this timeline:

```text
A: UPDATE 10 -> 7 (not COMMITted yet)
B: SELECT -> 10
A: COMMIT

B/READ COMMITTED:  second SELECT -> 7
B/REPEATABLE READ: second SELECT -> 10

B ends transaction and runs a new read -> 7
```

That is the fundamental picture of how **the same row can be observed differently depending on snapshots and transaction boundaries** in PostgreSQL.

### Official PostgreSQL Documentation

- [Introduction to MVCC](https://www.postgresql.org/docs/current/mvcc-intro.html).
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html).
- [Transaction ID and Snapshot Semantics](https://www.postgresql.org/docs/current/functions-info.html).
- [System Columns: xmin, xmax, ctid](https://www.postgresql.org/docs/current/ddl-system-columns.html).
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html).
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html).
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html).
