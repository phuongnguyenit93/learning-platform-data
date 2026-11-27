# Snapshots and Data Visibility Rules

Suppose two employees open a sales application at the same time. The first is viewing inventory, while the second updates a quantity and saves it. When the first queries again, do they see the new number immediately? Does a running transaction see another transaction's uncommitted data before `COMMIT`? Why does a `SELECT` see only one version of a row, whereas an `UPDATE` may have to wait for another transaction? And why does a long-running read transaction prevent PostgreSQL from cleaning up old row versions?

These questions are answered by **Multi-Version Concurrency Control (MVCC)** and specifically PostgreSQL's **snapshots** and **visibility rules**.

PostgreSQL does not force every read statement to wait for every write statement. Instead, multiple versions of a row can coexist physically for a period of time. A query uses a **snapshot** to decide which version is valid in the current context. A snapshot is not simply "the current wall-clock time"; it reflects which transactions had completed, were running, or had not yet started at the capture point according to PostgreSQL's transaction ID management rules.

This lesson explains:

- The nature of MVCC, row versions (*tuple versions*), and the system fields `xmin`, `xmax`, and `ctid`.
- What a snapshot conceptually contains and the rules classifying a tuple as **visible/invisible**.
- How a transaction sees **its own changes**.
- **Per-statement** snapshots in `READ COMMITTED` versus **per-transaction** snapshots in `REPEATABLE READ`.
- Differences in `SERIALIZABLE`, along with dirty reads, non-repeatable reads, phantoms, and write skew.
- Important exceptions when `UPDATE`, `DELETE`, `SELECT FOR UPDATE`, or `INSERT ... ON CONFLICT` encounter concurrent modifications.
- The impact of long-lived snapshots on `VACUUM`, table bloat, and dead-version reclamation.
- How to observe behavior using `pg_current_snapshot()`, `pg_stat_activity`, system columns, and two-session `psql` scenarios.
- How Java/JDBC applications choose isolation levels, manage transactions, and retry safely.

> **Scope:** This content focuses on modern PostgreSQL. Hands-on examples are designed for a lab database and must be run in two separate connections where instructed. System columns and snapshot internals are for learning/diagnostics, not stable APIs replacing business keys. Never rely on transaction ID values or tuple addresses as long-term data identifiers.

## 1. Why Does PostgreSQL Need Multiple Row Versions?

If a database kept only **a single physical copy per row**, a transaction modifying a value could force reading transactions to wait or expose partially modified data. MVCC separates two questions:

1. **Which versions physically exist on disk pages?**
2. **Which version is allowed to appear in this query's result?**

Example for a product:

```text
Before UPDATE:                         After UPDATE, before VACUUM cleanup:

product_id=1                           ┌─────────────────────────────┐
quantity=10                            │ Version A: quantity = 10    │
                                       │ created by old transaction  │
                                       └─────────────────────────────┘
                                       ┌─────────────────────────────┐
                                       │ Version B: quantity = 8     │
                                       │ created by new transaction  │
                                       └─────────────────────────────┘

Old reader's snapshot  ────────────────► Version A
New reader's snapshot  ────────────────► Version B (after update commits)
```

This is a conceptual diagram. In PostgreSQL, `UPDATE` normally creates a **new tuple version** rather than overwriting the old version's payload as a single record; storage also includes optimizations such as HOT updates and tuple chaining. Do not assume all versions always reside on the same page or share a layout exactly as drawn.

### Key Benefits

- Readers typically **do not wait on writers just for reading a row** with a normal `SELECT`.
- Writers can update rows while readers holding older snapshots still see the appropriate version.
- Transactions receive a consistent view according to their isolation level.
- `VACUUM` has a basis to remove old versions once no snapshot needs them.

**This does not mean PostgreSQL "never locks".** Contending writes, `SELECT ... FOR UPDATE`, DDL, table locks, and other concurrent operations still use locking.

## 2. Distinguishing a Logical Row From Physical Tuple Versions

In an application, `product_id = 1` usually identifies **one logical row**. In PostgreSQL, one logical row can go through many **tuple versions**:

```text
Logical: Product #1
  |
  +-- tuple version V1: quantity=10
  |       INSERT by transaction T10
  |
  +-- tuple version V2: quantity=8
  |       UPDATE by transaction T20
  |
  +-- tuple version V3: quantity=5
          UPDATE by transaction T30
```

At a given moment, a valid snapshot typically selects **the version visible under MVCC rules**. A new transaction sees V3 after T30 commits; a transaction with a snapshot from before T30 may still see V2.

Things to distinguish:

| Concept | Meaning |
|---|---|
| **Business key / primary key** | Logical identity defined by the schema, e.g., `product_id`. |
| **Tuple version** | A physical representation of the row at a specific data state. |
| **`xmin`** | Metadata of the transaction that created the tuple version. |
| **`xmax`** | Metadata related to the transaction that deleted/replaced/locked the tuple, interpreted alongside flags and status. |
| **`ctid`** | Current physical location of a tuple version in the table. |
| **Snapshot** | Context determining which tuple versions are valid for a query. |

**A primary key does not change just because an UPDATE creates a new tuple.** Conversely, `ctid` can change and should not be used as a stable business identifier.

## 3. Preparing Test Data

Create a dedicated schema and two tables:

```sql
CREATE SCHEMA IF NOT EXISTS lesson_mvcc;

CREATE TABLE lesson_mvcc.products (
    product_id BIGINT PRIMARY KEY,
    product_name TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    price NUMERIC(12, 2) NOT NULL CHECK (price >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE lesson_mvcc.order_lines (
    order_line_id BIGINT PRIMARY KEY,
    product_id BIGINT NOT NULL
        REFERENCES lesson_mvcc.products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);

INSERT INTO lesson_mvcc.products (
    product_id, product_name, quantity, price
)
VALUES
    (1, 'Keyboard', 10, 400000),
    (2, 'Mouse', 20, 120000),
    (3, 'Headset', 15, 800000);

INSERT INTO lesson_mvcc.order_lines(
    order_line_id, product_id, quantity
)
VALUES (100, 1, 2), (101, 2, 1);
```

The following examples use two `psql` windows:

- **Session A**: first connection.
- **Session B**: second connection, to the **same database** and with privileges on the lab tables.

If you run all commands sequentially in **one connection**, you will not reproduce phenomena between independent transactions. When a transaction is open in one session, **do not commit or roll back early** before the instructed step.

### Verifying Two Distinct Connections

Run on both A and B:

```sql
SELECT
    current_database(),
    current_user,
    pg_backend_pid();
```

Two direct sessions normally have different `pg_backend_pid()` values. In environments with proxy pooling, client-to-backend mapping can be more complex; to study MVCC, use two independent PostgreSQL connections and maintain transaction boundaries accurately.

## 4. What Is a Transaction ID (XID)?

PostgreSQL uses a **transaction ID**, commonly written **XID**, to manage changes and determine commit/abort status.

A mental model:

```text
T10: INSERT new row
T20: UPDATE old row → new version
T30: DELETE row
```

Tuples carry metadata referencing the transactions that created, deleted, or locked them. When a query must decide whether a tuple is visible, PostgreSQL checks that metadata alongside **transaction status** and the **current snapshot**.

### Not Every BEGIN Immediately Gets a Write XID

A read-only transaction can obtain a snapshot **without being assigned a permanent XID in the same way a write transaction does**. Thus, do not assume that because a session ran `BEGIN`, it always has a newly assigned write XID.

### XID Order and Commit Order Differ

Transaction ID assignment order **is not identical to commit order**:

```text
T100 starts ──────────────────────────── COMMITs late
           T101 starts ───── COMMITs early
```

T101 received its ID later yet finished before T100. Therefore, MVCC visibility cannot simply be "any tuple with `xmin` smaller than some number is visible." The system must check **whether each transaction is still running, committed, or aborted** at snapshot time.

### XID Wraparound and Freezing

Traditional tuple metadata stores XIDs in a finite number space, and PostgreSQL uses **freezing** and transaction-age management to handle wraparound safely. Do not compare two distant XIDs using plain arithmetic and treat it as absolute historical order.

## 5. System Columns xmin, xmax, and ctid

PostgreSQL allows reading several system columns on heap tables:

```sql
SELECT
    product_id,
    product_name,
    quantity,
    xmin,
    xmax,
    ctid
FROM lesson_mvcc.products
ORDER BY product_id;
```

You may see:

```text
product_id | quantity | xmin | xmax | ctid
-----------+----------+------+------+---------
1          | 10       | ...  | ...  | (...)
2          | 20       | ...  | ...  | (...)
3          | 15       | ...  | ...  | (...)
```

Exact values depend on the run, database, transactions, and physical layout. **Do not copy illustrative numbers to compare against another server**.

### Meaning of xmin

`xmin` is metadata indicating the transaction that created the **tuple version**. On an `UPDATE`, the new version typically records the `UPDATE` transaction as its creator, while the prior version is marked as superseded via tuple header metadata.

### Meaning of xmax

`xmax` must be interpreted carefully:

- It can relate to a transaction that deleted or replaced a tuple.
- It can be used in **row-locking** scenarios without the tuple being deleted.
- It can refer to a **MultiXact** when multiple transactions hold locks.
- A non-zero value is not enough to conclude the tuple is invisible.

**Common mistake:** `xmax <> 0` is not a general SQL predicate for "deleted row." Tuple visibility depends on multiple metadata flags, transaction status, and snapshots; PostgreSQL evaluates these inside the executor/heap access layer.

### Meaning of ctid

`ctid` represents the physical address of a tuple version, such as block and offset. It can change after an `UPDATE` or table reorganization. **Never use `ctid` as a business ID, foreign key, stable pagination token, or long-term audit reference**.

## 6. What Information Does a Snapshot Store?

Conceptually, an MVCC snapshot describes transaction ID boundaries and **the transactions currently in progress** when the snapshot was taken.

A modern representation has these components:

- **Snapshot `xmin`:** lower boundary used to evaluate transactions still requiring checks in the active set.
- **Snapshot `xmax`:** upper boundary; XIDs at or beyond this boundary are not considered completed prior to the snapshot.
- **In-progress XID list:** transactions that have been assigned IDs but had not finished at snapshot time, generally called **in-progress XIDs**.

A **hypothetical diagram**, not actual PostgreSQL output:

```text
Snapshot S
  xmin = 100
  xmax = 106
  in_progress = {101, 104}

T100: committed
T101: still running        ── uncommitted changes of T101 not visible
T102: committed
T103: committed
T104: still running        ── uncommitted changes of T104 not visible
T105: committed
T106: beyond snapshot      ── new changes from T106 not visible
```

In this example:

- Changes made by transactions **committed before the snapshot** can be visible, unless deleted/replaced by another visible change.
- Changes from transactions **in progress when captured** are not visible to that snapshot, even if those transactions commit afterward.
- Changes from transactions **starting beyond the snapshot boundary** are treated as not yet existing in the old snapshot.

This is a simplified pedagogical description. PostgreSQL also evaluates subtransactions, commit/abort status, command IDs, hint bits, MultiXacts, and specific tuple/snapshot type conditions.

### A Snapshot Is Not a Simple Comparable Timestamp

You cannot use:

```sql
WHERE created_at <= snapshot_time
```

to accurately simulate MVCC. `created_at` is an application/schema-managed column; a transaction may start earlier yet commit later, clocks can skew, and in-progress transactions make the visible set **impossible to derive from row timestamps alone**.

## 7. Tuple Version Visibility Rules

For a **normal MVCC snapshot**, imagine the evaluation process as follows:

1. Identify the transaction associated with **creating the version** (`xmin`).
2. If the creating transaction **aborted**, that version is not visible.
3. If the creating transaction **had not committed at the snapshot**, the new version is not yet visible to that snapshot.
4. If the creating transaction **committed early enough** and is valid for the snapshot, check whether the version was replaced/deleted.
5. If the deleting/replacing transaction **has not committed or is not visible to the snapshot**, the old version can remain visible to that reader.
6. If the delete/replacement **committed and is visible to the snapshot**, the old version is normally excluded from that snapshot's result.
7. Changes **made by the current transaction itself** are handled by self-visibility rules and command IDs; you cannot mechanically apply "my XID is running so all my own changes are invisible."

This is a teaching model, **not a complete algorithm you can reimplement yourself to replace PostgreSQL's visibility checks**.

### Scenario Table

| Creating Transaction | Deleting/Replacing Transaction | General Result |
|---|---|---|
| Committed before snapshot | None | Tuple can be visible. |
| Uncommitted at snapshot | None | Tuple is **not visible** to other transactions. |
| Aborted | None | Tuple is **not visible**. |
| Committed before snapshot | Delete committed before snapshot | Old tuple **not visible**; for `UPDATE`, successor version may be visible if valid. |
| Committed before snapshot | Delete in progress at snapshot | Old tuple **can still be visible**. |
| Committed before snapshot | Delete committed after snapshot | Old snapshot **can still see** old tuple. |

Because this table omits row locks, subtransactions, and implementation optimizations, do not use it as a manual SQL check via `xmin`/`xmax`.

## 8. How Does an UPDATE Create a New Version?

Suppose product 1 has quantity 10:

```text
Version V1:
  product_id = 1
  quantity   = 10
  xmin       = T10
```

Transaction T20:

```sql
UPDATE lesson_mvcc.products
SET quantity = 8
WHERE product_id = 1;
```

Model:

```text
Version V1: quantity = 10
  xmin = T10
  xmax ≈ T20 (marked replaced via corresponding metadata)
            │
            ▼
Version V2: quantity = 8
  xmin = T20
  xmax = not yet replaced/deleted
```

**If T20 has not committed:** other transactions with normal snapshots do not see V2; they can still see V1.

**If T20 commits and a reader takes a snapshot afterward:** the reader can see V2.

**If a reader holds a snapshot from before T20 committed:** it can continue seeing V1 according to its isolation level.

### UPDATE Does Not Simply Overwrite a Single Tuple

Because both V1 and V2 may need to exist simultaneously to serve different snapshots, MVCC affects storage footprint and `VACUUM` cleanup work. That is why heavy `UPDATE`/`DELETE` workloads generate **dead tuples**.

## 9. DELETE and Snapshots: Why Can Deleted Rows Still Appear?

Transaction B runs:

```sql
DELETE FROM lesson_mvcc.products
WHERE product_id = 3;
```

Assume no foreign keys reference product 3 and the operation succeeds. After B commits:

- A new query under `READ COMMITTED` with a fresh snapshot will not see that row.
- A `REPEATABLE READ` transaction with a snapshot taken **before B committed** can still see the old version of the row.

That is not a bug where "PostgreSQL forgot to DELETE." The old snapshot still represents a valid state of the database from before the `DELETE` was committed.

**Note:** If you permanently delete sample rows while practicing, subsequent steps may be affected. Prefer testing with:

```sql
BEGIN;
DELETE FROM lesson_mvcc.products WHERE product_id = 3;
ROLLBACK;
```

or use separate test copies/datasets when you need to observe concurrent commits.

## 10. No Dirty Reads in PostgreSQL

A **dirty read** is reading data modified by another transaction **before that transaction commits**. PostgreSQL does not allow dirty reads at any supported isolation level.

### Two-Session Practice

**Session A:**

```sql
BEGIN;

UPDATE lesson_mvcc.products
SET quantity = 777
WHERE product_id = 1;

-- Not yet COMMITted and not yet ROLLBACKed.
```

**Session B**, while A remains open:

```sql
SELECT quantity
FROM lesson_mvcc.products
WHERE product_id = 1;
```

B still sees **the previously committed value** (e.g., 10), not A's uncommitted 777.

**Back to Session A:**

```sql
ROLLBACK;
```

**Session B:**

```sql
SELECT quantity
FROM lesson_mvcc.products
WHERE product_id = 1;
```

The row still holds the old value because the 777 change was rolled back.

### READ UNCOMMITTED in PostgreSQL

PostgreSQL accepts the isolation level name `READ UNCOMMITTED` in SQL syntax, but **executes it with `READ COMMITTED` semantics** for data visibility. Thus, trying:

```sql
BEGIN ISOLATION LEVEL READ UNCOMMITTED;
SELECT quantity FROM lesson_mvcc.products WHERE product_id = 1;
COMMIT;
```

does not allow reading another session's uncommitted values.

## 11. READ COMMITTED: A Fresh Snapshot Per Statement

**`READ COMMITTED`** is PostgreSQL's usual default isolation level unless overridden at the server, database, role, or session level.

For normal `SELECT` queries, **each statement** takes a snapshot at the start of that statement:

```text
Session A                              Session B
----------------------------------     ------------------------
BEGIN READ COMMITTED
SELECT quantity => 10
                                       UPDATE quantity = 8
                                       COMMIT
SELECT quantity => 8
COMMIT
```

Transaction A **is still one transaction**, yet two different statements can observe two different data states.

### Step-by-Step Practice

Ensure product 2 exists and check its current value. Suppose `quantity = 20`.

**Session A:**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT quantity
FROM lesson_mvcc.products
WHERE product_id = 2;
-- For example, sees 20.
```

**Session B**, another connection:

```sql
BEGIN;

UPDATE lesson_mvcc.products
SET quantity = 18
WHERE product_id = 2;

COMMIT;
```

**Session A**, still in the same transaction:

```sql
SELECT quantity
FROM lesson_mvcc.products
WHERE product_id = 2;
-- Sees 18 if B committed before this statement started.

COMMIT;
```

Inside a `READ COMMITTED` transaction, two reads can differ even though A has not ended its transaction.

### Non-Repeatable Read

The phenomenon where "re-reading the same row yields a different value because another transaction committed" is called a **non-repeatable read**. `READ COMMITTED` permits this case.

**It does not mean a single running `SELECT` automatically switches snapshots mid-execution.** A normal statement reads consistently against its own snapshot; the *next* `SELECT` acquires a fresh snapshot.

## 12. READ COMMITTED and Phantom Reads

A **phantom read** involves repeating a conditional query and seeing matching rows appear or disappear.

For example, Session A:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT COUNT(*)
FROM lesson_mvcc.products
WHERE quantity >= 10;
```

Session B inserts a new product with quantity 30 and commits:

```sql
BEGIN;

INSERT INTO lesson_mvcc.products(
    product_id, product_name, quantity, price
)
VALUES (99, 'New product', 30, 50000);

COMMIT;
```

Session A runs again:

```sql
SELECT COUNT(*)
FROM lesson_mvcc.products
WHERE quantity >= 10;

COMMIT;
```

The row count can increase because the new snapshot sees product 99. This is a form of **phantom**.

To keep lab data clean, after the exercise use a new transaction to delete product 99 if nothing depends on it, or use a different ID for new tests. Do not run `ROLLBACK` in session B after already running `COMMIT` expecting to undo the committed row.

## 13. REPEATABLE READ: Transaction-Wide Stable Snapshot

Under `REPEATABLE READ` in PostgreSQL, normal queries within the same transaction use **the same transaction snapshot** established when the transaction first executes a statement that requires a snapshot.

### Experiment

First, assume product 2 currently has quantity 18 from the previous example.

**Session A:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT quantity
FROM lesson_mvcc.products
WHERE product_id = 2;
-- For example, sees 18 and establishes the snapshot.
```

**Session B:**

```sql
BEGIN;

UPDATE lesson_mvcc.products
SET quantity = 16
WHERE product_id = 2;

COMMIT;
```

**Session A:**

```sql
SELECT quantity
FROM lesson_mvcc.products
WHERE product_id = 2;
-- Still sees 18 under the old snapshot.

COMMIT;
```

**After A finishes**, a new transaction can see 16:

```sql
SELECT quantity
FROM lesson_mvcc.products
WHERE product_id = 2;
```

### When Is the Snapshot Taken?

A subtle detail: in PostgreSQL, `BEGIN ISOLATION LEVEL REPEATABLE READ` does not necessarily "freeze all data at the exact instant the client sends BEGIN." The snapshot is normally established at the **first non-transaction-control statement** requiring a snapshot, such as the first `SELECT`. If B commits after `BEGIN` but **before A's first read**, A can see B's commit.

Therefore, when writing a two-session scenario to observe an old snapshot, have A **run its first SELECT before B commits**.

## 14. REPEATABLE READ Still Sees Changes Made by the Transaction Itself

A misconception is that "a fixed snapshot means the transaction never sees any new values at all." In fact, PostgreSQL lets a transaction see **changes made by itself** via command ID rules, even under `REPEATABLE READ`.

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT quantity
FROM lesson_mvcc.products
WHERE product_id = 1;
-- Example: 10.

UPDATE lesson_mvcc.products
SET quantity = quantity - 1
WHERE product_id = 1;

SELECT quantity
FROM lesson_mvcc.products
WHERE product_id = 1;
-- Sees 9: the transaction's own change.

ROLLBACK;
```

`ROLLBACK` at the end reverts the change to preserve lab data.

### Why Doesn't This Contradict the Snapshot?

The snapshot filters out **uncommitted changes of other transactions** and maintains visibility boundaries per isolation rules. It does not blind a transaction to **its own writes** once those write statements complete.

In implementation, PostgreSQL also uses **command IDs** and tuple metadata to determine visibility for operations inside the same transaction. You cannot describe self-visibility using only a list of transaction IDs.

## 15. Comparing READ COMMITTED and REPEATABLE READ

| Situation | READ COMMITTED | PostgreSQL REPEATABLE READ |
|---|---|---|
| Sees uncommitted data of other transactions? | **No**. | **No**. |
| Second statement sees new commit from another transaction? | **Possible**. | **No**, if snapshot was established before that commit, for normal queries. |
| Re-reading a row can return a different value due to another writer? | **Yes**. | **No**, under normal snapshots and corresponding assumptions. |
| Re-running a conditional query can see phantoms from new inserts? | **Yes**. | No under PostgreSQL's fixed snapshot. |
| Sees the transaction's own writes? | **Yes**. | **Yes**. |
| Writer encounters a row modified concurrently? | Can wait and re-check the row. | May raise `40001` if the target row changed since the snapshot began. |
| Guarantees full serializability? | No. | No; certain anomalies like write skew can still occur. |

PostgreSQL's `REPEATABLE READ` is based on snapshot isolation, which is stronger than the SQL standard's minimum requirement regarding phantoms. However, **a stable snapshot alone does not mean all concurrent transactions are equivalent to a serial schedule**.

## 16. SERIALIZABLE: Snapshots Plus Concurrency Anomaly Control

`SERIALIZABLE` is PostgreSQL's strongest isolation level. For transactions that complete successfully, the system guarantees results equivalent to **some serial execution order**.

PostgreSQL implements serializable isolation using **Serializable Snapshot Isolation (SSI)** rather than simply locking the entire database for every transaction.

### Why Is a Fixed Snapshot Still Not Enough?

Suppose the rule is "at least one doctor must remain on call."

```text
Initially:
  Doctor A = on_call
  Doctor B = on_call

Transaction T1 sees snapshot: both A and B are on call
  → T1 takes A off call

Transaction T2 sees the same initial state:
  → T2 takes B off call

The two transactions write two different rows.
If both commit under snapshot isolation:
  nobody is on call → cross-row rule violated.
```

That is an example of **write skew**. T1 and T2 may not update the same row, so detecting write-write conflicts alone is insufficient.

Under `SERIALIZABLE`, SSI tracks dangerous read-write dependencies. In schedules at risk of being non-serializable, PostgreSQL may **abort a transaction with SQLSTATE `40001`**, forcing the application to **retry the entire transaction**.

### SERIALIZABLE Does Not Mean Never Retrying

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

-- Read data and make business decisions.
-- SSI conflict with another transaction may occur.

COMMIT;
```

Error `40001` can occur during execution or at `COMMIT`, depending on the situation. The application must be ready to re-run both the reads and decisions, not merely repeat the final `UPDATE`.

## 17. Isolation Levels and Visibility Phenomena

| Phenomenon | READ UNCOMMITTED (PostgreSQL) | READ COMMITTED | REPEATABLE READ | SERIALIZABLE |
|---|---|---|---|---|
| Dirty read | No | No | No | No |
| Non-repeatable read from another commit | Possible | Possible | No per snapshot | No for successful transactions |
| Phantom from another commit | Possible | Possible | No per snapshot | No for successful transactions |
| Write skew | Possible | Possible | Possible | Prevented for committed transactions; may require `40001` retry |

PostgreSQL executes `READ UNCOMMITTED` with `READ COMMITTED` behavior. This table describes general behaviors for normal queries; locking statements, concurrent updates, and constraints have specific rules covered next.

## 18. Do Snapshots Mean UPDATE Never Sees New Writes?

You cannot apply the rules of a **normal `SELECT`** verbatim to every **`UPDATE`/`DELETE`/`SELECT FOR UPDATE`**.

Under `READ COMMITTED`, if a statement wants to modify a row currently being updated/locked by another transaction, PostgreSQL can:

1. Find candidate rows using the statement's initial snapshot.
2. Wait for the other transaction to finish if there is a lock/conflict.
3. After the other transaction commits, examine the new row version and **re-evaluate the `WHERE` condition** under concurrent-update rules.
4. If the row still satisfies the condition, apply the change to the appropriate version; otherwise, skip the row.

This mechanism is commonly explained as **rechecking/re-evaluating the updated tuple**; in PostgreSQL it involves *EvalPlanQual* (EPQ).

### Thought Example

Initially product 1 has quantity 10.

**Session A:**

```sql
BEGIN;

UPDATE lesson_mvcc.products
SET quantity = 3
WHERE product_id = 1;

-- Keep transaction open, do not COMMIT yet.
```

**Session B**, running under `READ COMMITTED`:

```sql
UPDATE lesson_mvcc.products
SET quantity = quantity + 1
WHERE product_id = 1
  AND quantity >= 5;
-- May wait for A to finish.
```

**Session A:**

```sql
COMMIT;
```

After A commits, B re-evaluates the version with quantity 3. The condition `quantity >= 5` **is no longer true**, so B does not update that row.

### Do Not Assume Every Read Inside a Statement Sees a Pure Serial Point

`READ COMMITTED` has nuances when statements modify rows concurrently: it can operate on a newer version of the target row even while other parts of the query were evaluated against the initial snapshot. That is why PostgreSQL documentation warns that this level may be insufficient for operations with complex logical conditions.

If stronger consistency guarantees are required, consider explicit locking, `REPEATABLE READ`/`SERIALIZABLE`, unique constraints, or redesigning the write protocol.

## 19. REPEATABLE READ and Concurrent UPDATE

Under `REPEATABLE READ`, if a transaction already holds a snapshot and another transaction modifies a target row and commits, attempting an `UPDATE`/`DELETE`/`SELECT FOR UPDATE` on the modified version can end with:

```text
ERROR: could not serialize access due to concurrent update
SQLSTATE: 40001
```

### Illustrative Scenario

**Session A:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT quantity
FROM lesson_mvcc.products
WHERE product_id = 2;
-- Establishes old snapshot.
```

**Session B:**

```sql
UPDATE lesson_mvcc.products
SET quantity = quantity + 2
WHERE product_id = 2;
-- With autocommit on, statement completes and commits.
```

**Session A:**

```sql
UPDATE lesson_mvcc.products
SET quantity = quantity + 1
WHERE product_id = 2;
-- May fail with 40001 because the row was changed by B since A's snapshot.

ROLLBACK;
```

**`40001` is not an invitation to keep issuing UPDATEs inside that transaction.** The transaction has failed; the application must roll back and, if valid, start a new transaction and retry the full logic.

## 20. SELECT FOR UPDATE Is Not Like a Normal SELECT

`SELECT ... FOR UPDATE` is a read **with row-locking intent**, typically used before modifying rows:

```sql
BEGIN;

SELECT quantity
FROM lesson_mvcc.products
WHERE product_id = 1
FOR UPDATE;

-- Business decision and UPDATE within the same transaction.

ROLLBACK;
```

Unlike a plain `SELECT`, this requests row locks to coordinate with writers. If another transaction holds an incompatible lock, it may have to wait—or error when using `NOWAIT`.

### NOWAIT

```sql
BEGIN;

SELECT product_id
FROM lesson_mvcc.products
WHERE product_id = 1
FOR UPDATE NOWAIT;

ROLLBACK;
```

If the lock cannot be acquired immediately due to a conflict, PostgreSQL can return `55P03`, and an explicit transaction must handle the error with an appropriate rollback/savepoint.

### SKIP LOCKED

```sql
SELECT product_id
FROM lesson_mvcc.products
FOR UPDATE SKIP LOCKED;
```

`SKIP LOCKED` skips currently locked rows to support worker-queue patterns. Its output **does not represent a complete consistent view of all pending rows**, so never use it arbitrarily for summary reporting.

**Important:** The fact that `SELECT FOR UPDATE` takes row locks does not refute MVCC; locking and snapshot visibility are two mechanisms working together.

## 21. Unique Constraints Check Rows Not Visible in SELECT

A frequently asked question:

> "I don't see any duplicate SKU in SELECT, so why did INSERT fail with a unique violation?"

Because **uniqueness must be enforced across the entire database**, not just across rows visible in a `SELECT`'s snapshot. If two transactions insert the same `sku` concurrently, PostgreSQL must coordinate the unique index and competing transaction states.

### Two-Session Example

Suppose SKU `SKU-X` does not exist yet.

**Session A:**

```sql
BEGIN;

INSERT INTO lesson_mvcc.products(
    product_id, product_name, quantity, price
)
VALUES (101, 'SKU-X', 1, 10000);

-- product_name in the lab schema is not UNIQUE; this example
-- does not yet simulate a conflict by SKU.
ROLLBACK;
```

To properly test a unique conflict, use a small dedicated table:

```sql
CREATE TABLE lesson_mvcc.unique_demo (
    id BIGINT PRIMARY KEY,
    external_key TEXT NOT NULL UNIQUE
);
```

**Session A:**

```sql
BEGIN;

INSERT INTO lesson_mvcc.unique_demo(id, external_key)
VALUES (1, 'same-key');

-- Not committed yet.
```

**Session B**, in another connection:

```sql
SELECT *
FROM lesson_mvcc.unique_demo
WHERE external_key = 'same-key';
-- Does not see A's row because A has not committed.

INSERT INTO lesson_mvcc.unique_demo(id, external_key)
VALUES (2, 'same-key');
-- May have to WAIT for transaction A to resolve the unique conflict.
```

**Session A** commits:

```sql
COMMIT;
```

When A commits, B's insert can fail with `23505 unique_violation`. If A rolls back instead of committing, B can be allowed to insert.

**Key takeaway:** "`SELECT` didn't see it" is not proof that "another transaction hasn't already claimed/inserted the key." Unique constraints have dedicated synchronization to protect data invariants under concurrency.

## 22. INSERT ... ON CONFLICT Under READ COMMITTED

`INSERT ... ON CONFLICT` handles conflicts much more safely than the pair:

```text
SELECT to check key doesn't exist
  ↓
INSERT key
```

because another transaction can interleave between those two steps.

Example:

```sql
INSERT INTO lesson_mvcc.unique_demo(id, external_key)
VALUES (3, 'same-key')
ON CONFLICT (external_key) DO NOTHING
RETURNING id;
```

Under `READ COMMITTED`, `ON CONFLICT DO NOTHING` may **skip inserting a row due to a conflict with another transaction**, even when the conflicting row version was not visible in the statement's regular snapshot.

With `ON CONFLICT DO UPDATE`, PostgreSQL likewise has rules ensuring either `INSERT` or `UPDATE` is chosen for each input row when no independent error occurs, even if the updated target row was not yet visible in the statement's normal `SELECT` snapshot:

```sql
INSERT INTO lesson_mvcc.unique_demo(id, external_key)
VALUES (3, 'same-key')
ON CONFLICT (external_key)
DO UPDATE SET external_key = EXCLUDED.external_key
RETURNING id, external_key;
```

This is an important case: **read visibility and constraint enforcement / conflict resolution are related, but not identical**.

Do not use `ON CONFLICT` to mask arbitrary errors. Define proper unique keys and explicit upsert semantics.

## 23. UPDATE Under READ COMMITTED and Application-Level Lost Updates

Suppose a row has quantity 10. Two requests do:

```text
Request A: SELECT quantity => 10
Request B: SELECT quantity => 10
Request A: UPDATE SET quantity = 11
Request B: UPDATE SET quantity = 11
```

The final result can be 11, even though both requests intended to increment by one. This is a form of **lost update** caused by the application reading a value and sending back an **absolute value calculated from stale data**.

### Better Approach for Simple Increments

```sql
UPDATE lesson_mvcc.products
SET quantity = quantity + 1
WHERE product_id = 1;
```

Two transactions updating the same row are synchronized by PostgreSQL via row locking. Using the expression `quantity = quantity + 1` applies the increment to the appropriate version rather than overwriting with the same literal 11.

### Optimistic Locking With a Version Column

If business logic needs to check "data has not changed since I read it":

```sql
-- Illustrative example on a table with a version_no column:
UPDATE some_business_table
SET
    payload = 'new-value',
    version_no = version_no + 1
WHERE id = 42
  AND version_no = 7
RETURNING version_no;
```

This is sample SQL; `some_business_table` has not been created in the lab. If `UPDATE` returns 0 rows, the record was either modified or does not exist; the application must handle the conflict accordingly.

Never treat a tuple's `xmin` as a long-term stable business version number: transaction IDs wrap around/freeze and are not designed as an API contract.

## 24. Snapshots and Data Visibility Within the Same Transaction

Even with a fixed transaction snapshot, later statements normally see changes made by earlier statements in the same transaction:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

INSERT INTO lesson_mvcc.products(
    product_id, product_name, quantity, price
)
VALUES (500, 'In-transaction product', 5, 25000);

SELECT *
FROM lesson_mvcc.products
WHERE product_id = 500;
-- Sees the row inserted by the transaction itself.

UPDATE lesson_mvcc.products
SET quantity = 7
WHERE product_id = 500;

SELECT quantity
FROM lesson_mvcc.products
WHERE product_id = 500;
-- Sees 7.

DELETE FROM lesson_mvcc.products
WHERE product_id = 500;

SELECT *
FROM lesson_mvcc.products
WHERE product_id = 500;
-- Row is gone, reflecting the transaction's own change.

ROLLBACK;
```

These results reflect self-visibility and statement ordering within a transaction. Remember: **reading an old snapshot with respect to other transactions** does not mean **being blind to your own writes**.

## 25. Command IDs and the Limits of Comparing Only by XID

Internally, a tuple version also carries **command ID** information for operations within the same transaction.

Example:

```text
T100:
  Command 0: INSERT product 500
  Command 1: SELECT product 500
  Command 2: UPDATE product 500
  Command 3: SELECT product 500
```

A naive rule like "tuple created by T100, and T100 is still running, so invisible" is wrong for changes **created by T100 itself**. PostgreSQL must track **command ordering within the same transaction** to avoid:

- Failing to see its own `INSERT` in a subsequent statement.
- Incorrectly seeing a version already replaced by the same transaction.
- Treating operations within the same transaction as independent transactions.

Certain situations within the **same statement** have additional special rules: parts of a single SQL statement are not arbitrarily allowed to see every side effect produced by another part of the same statement in any order. For instance, data-modifying CTEs have specific snapshot rules and data passing via `RETURNING`. That is an advanced topic and should not be extrapolated from a simple command ID model.

## 26. How Does a Long Transaction Affect VACUUM?

If a transaction holds an old snapshot, PostgreSQL may have to keep old tuple versions that the snapshot is still entitled to see.

```text
T1: BEGIN REPEATABLE READ
    SELECT ...  → snapshot S1
    [holds transaction open for a very long time]

T2: UPDATE 10,000 rows, COMMIT
    → creates new versions

VACUUM:
    May be unable to clean all old versions
    if S1 still needs those versions.

T1: COMMIT/ROLLBACK
    → old snapshot released
    → future VACUUM can reclaim eligible versions
```

This involves the **xmin horizon / visibility horizon** and determining which versions are still needed by transactions, replicas, or other consumers.

### Symptoms

- `n_dead_tup` grows in table statistics.
- Table/index sizes grow larger than expected.
- Autovacuum runs without reclaiming all old tuples.
- A long transaction is held open by an unclosed request/JDBC connection.
- A backend sits in `idle in transaction`.

**Do not conclude "any long transaction keeps every old version across the entire database."** Snapshots, backend `xmin`, transaction XIDs, replication needs, and global horizon rules determine which tuples are actually retained.

### Readers Do Not Row-Lock Writers, Yet Still Create Storage Cost

A long read query may not block a normal `UPDATE` with a row lock, but holding a snapshot open for a long time can **delay cleanup of old versions**. This is an important trade-off of MVCC.

## 27. VACUUM Does Not Alter Query Visibility Rules

`VACUUM` aims to reclaim tuples that are no longer needed, maintain visibility metadata, and help prevent transaction ID wraparound.

Do not think that:

- `VACUUM` will cause a transaction with an old snapshot to "suddenly see new versions."
- `VACUUM` can immediately delete every old tuple even while a snapshot needs it.
- `VACUUM FULL` is a routine step to run after every `UPDATE`.

PostgreSQL designs `VACUUM` to respect visibility safety boundaries. A transaction holding a snapshot still follows its isolation rules within supported guarantees.

### VACUUM and VACUUM FULL

- Regular `VACUUM` cleans eligible dead tuples and reuses space internally per PostgreSQL mechanisms, generally without returning the full file size to the operating system.
- `VACUUM FULL` rewrites the table to compact it and requires a stronger lock; it is not a solution to run casually on an active system.

If a long snapshot blocks vacuuming, merely running `VACUUM FULL` does not fix the transaction-lifecycle root cause and can cause substantial locking disruption.

## 28. pg_stat_activity: Inspecting Transactions and backend_xmin

From **a separate monitoring connection**, run:

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    query_start,
    backend_xmin,
    wait_event_type,
    wait_event
FROM pg_catalog.pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST, pid;
```

Important columns:

| Column | Meaning |
|---|---|
| `pid` | Backend process ID. |
| `state` | Activity state, e.g., `active`, `idle`, `idle in transaction`. |
| `xact_start` | Start time of the current transaction, if any. |
| `query_start` | Start time of the query reported per state. |
| `backend_xmin` | XID horizon associated with the snapshot currently held by the backend, if any. |
| `wait_event_type`/`wait_event` | Current wait details if the backend is waiting. |

### How to Use It

If a `REPEATABLE READ` session stays open for hours:

1. Identify the exact `pid`/`application_name`.
2. Check `xact_start` and `idle in transaction` state.
3. Check `backend_xmin` if present.
4. Correlate with workload, autovacuum, and tables accumulating dead tuples.
5. Prioritize fixing the transaction lifecycle in the application.

**Do not treat `backend_xmin` as the full snapshot itself**, and do not compare raw XID numbers naively while ignoring wraparound. `backend_xmin` is a useful administrative indicator, not the full set of in-progress transactions in a snapshot.

### Monitoring Privileges

Depending on the role, some columns of other sessions in `pg_stat_activity` may be restricted. Use minimal appropriate monitoring privileges; never grant superuser just to inspect snapshots.

## 29. Dead Tuple Statistics in Tables

PostgreSQL provides statistics views such as `pg_stat_user_tables`:

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
FROM pg_catalog.pg_stat_user_tables
WHERE schemaname = 'lesson_mvcc'
ORDER BY relname;
```

`n_live_tup` and `n_dead_tup` are **statistical estimates**, not an exact per-tuple count under a snapshot like `COUNT(*)`.

To diagnose whether a table is bloated due to snapshots:

- Track trends across multiple points in time.
- Inspect `UPDATE`/`DELETE` volume, autovacuum activity, and transaction/replication horizons.
- Check whether locks, long transactions, replication slots, or standby feedback are involved.
- Measure actual size, workload, and vacuum progress.

Never guess a single root cause from one `n_dead_tup` number alone.

## 30. Replication and Snapshots Retaining Old Versions

It is not only read transactions on the primary that can affect tuple cleanup. Replication mechanisms, replication slots, and **`hot_standby_feedback`** can cause the primary to retain metadata/versions longer to serve consumers or standbys.

### A Standby Has Its Own Snapshot Context

A physical standby performs WAL replay, and read-only queries on the standby see data at a particular replay state. A standby does not necessarily catch up to the primary instantaneously.

An application flow:

```text
Write to primary → COMMIT succeeds
Read immediately on standby → may not see change yet
```

This can be **replication lag**, which is not the same phenomenon as holding an old `REPEATABLE READ` snapshot on the primary.

### Recovery Conflicts With Long Queries

In certain standby configurations, WAL replay needs to clean information that conflicts with a standby read-only snapshot/query. The query may be canceled via **recovery conflict** mechanisms depending on delay/feedback settings. Never assume a standby snapshot can remain open forever without affecting replay.

### Trade-Offs of Enabling Feedback

`hot_standby_feedback` can reduce certain snapshot conflicts on a standby, but can cause the primary to retain dead tuples longer. Configuration must balance lag, bloat, query SLAs, and resources.

**Do not lump replication lag, snapshot visibility, and access permissions into a single cause** when a query "does not see new data."

## 31. Observing Snapshots With pg_current_snapshot()

Modern PostgreSQL provides the function:

```sql
SELECT pg_current_snapshot() AS snapshot_info;
```

The return type is **`pg_snapshot`**, typically formatted in three parts:

```text
xmin:xmax:xip_list
```

where `xip_list` represents transaction IDs in progress at snapshot time per the function's format. This is not a single "capture timestamp" number; each part has meaning for visibility.

Example inspecting components:

```sql
WITH s AS (
    SELECT pg_current_snapshot() AS snap
)
SELECT
    snap::text AS snapshot_text,
    pg_snapshot_xmin(snap) AS snapshot_xmin,
    pg_snapshot_xmax(snap) AS snapshot_xmax
FROM s;
```

To list in-progress transaction IDs in the snapshot:

```sql
SELECT xid
FROM pg_snapshot_xip(pg_current_snapshot()) AS x(xid)
ORDER BY xid;
```

The last query can return **0 rows** if the snapshot recorded no in-progress XIDs in that list. Results and XID numbers depend on server concurrency.

### Points to Remember

- `pg_current_snapshot()` returns the snapshot for the current statement/transaction and active isolation level.
- `pg_snapshot_xmin`/`pg_snapshot_xmax` return the snapshot's XID boundaries.
- `pg_snapshot_xip` returns XIDs in the snapshot's in-progress list.
- **Never use the snapshot string as a timestamp, order ID, or "time travel" contract that can be stored arbitrarily and reused later.**

The `pg_snapshot` family is the modern interface; older docs/applications may use `txid_*` functions and the `txid_snapshot` type. When maintaining legacy systems, check the server version and actual API rather than mixing the two families carelessly.

## 32. pg_current_xact_id() and XID Assignment

When you need to observe the current transaction's ID in modern PostgreSQL, functions include:

```sql
SELECT pg_current_xact_id() AS my_xid;
```

This call can **force XID assignment** if the transaction does not already have one. Therefore, do not call it indiscriminately while probing a read-only transaction and then conclude that every read-only transaction has an XID.

There is a variant that checks if one has already been assigned:

```sql
SELECT pg_current_xact_id_if_assigned() AS maybe_xid;
```

This variant can return SQL `NULL` if no XID is attached to the transaction yet per function semantics.

### Transaction XID Is Not a Snapshot

`pg_current_xact_id()` returns the calling transaction's identifier. `pg_current_snapshot()` describes the visible/in-progress XID landscape at the snapshot. A single transaction ID cannot represent the full visible dataset of a query.

## 33. Checking an XID Against a Snapshot: For Learning and Debugging Only

Modern PostgreSQL has `pg_visible_in_snapshot(xid8, pg_snapshot)` to check **visibility of a transaction ID in a snapshot** via a function interface.

Syntax example:

```sql
WITH snapshot_data AS (
    SELECT pg_current_snapshot() AS snap
)
SELECT
    s.snap,
    pg_visible_in_snapshot(
        pg_current_xact_id_if_assigned(),
        s.snap
    ) AS current_xid_visible
FROM snapshot_data AS s
WHERE pg_current_xact_id_if_assigned() IS NOT NULL;
```

This is an exploratory example and **may return zero rows** when the transaction has not been assigned an XID. Do not interpret the returned boolean as "every tuple created by that transaction is visible": tuple visibility also depends on deletions/replacements, subtransactions, self-visibility, and internal flags.

**Important:** `pg_visible_in_snapshot` checks an XID against a snapshot; it does not replace PostgreSQL's check on a **specific tuple**, nor is it an authorization check or business-key existence check.

## 34. Exporting and Importing Snapshots Across Multiple Transactions

Sometimes two workers need to run multiple queries while **seeing data from the exact same snapshot**. PostgreSQL supports exporting and importing snapshots under specific conditions.

### Session A: Export Snapshot

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT pg_export_snapshot();
-- Returns a text snapshot identifier, for example:
-- 00000003-0000001A-1

-- Keep this transaction open until B imports the snapshot.
```

### Session B: Import Snapshot

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SET TRANSACTION SNAPSHOT '00000003-0000001A-1';
-- Replace the sample string with the actual identifier returned by A.

SELECT COUNT(*)
FROM lesson_mvcc.products;

COMMIT;
```

### Session A: End After B Has Imported

```sql
COMMIT;
```

Important conditions:

1. **The exporting transaction must remain open** when the importing transaction imports the snapshot.
2. The importing transaction must use a compatible isolation level (typically `REPEATABLE READ` or `SERIALIZABLE` per PostgreSQL constraints).
3. `SET TRANSACTION SNAPSHOT` must be executed **before any other query that acquires a snapshot** in the importing transaction.
4. The snapshot ID is a **temporary identifier**, not a backup or token you can save in a DB and reuse anytime.
5. Additional restrictions apply based on isolation, database/session, and transaction properties. Consult the docs for your exact version when building multi-connection backup/reporting tools.

### Exporting a Snapshot Does Not Replace Backups

Snapshots synchronize the view across cooperating transactions. They do not hold data themselves, do not archive row versions permanently, and cannot restore a database to an arbitrary historical point.

## 35. Snapshots and Consistent Backups

Dump tools often need a **consistent snapshot** so multiple tables are read from the same logical state, avoiding:

```text
Read orders table at time T1
Read order_items table at time T2
→ Can be inconsistent if another transaction commits between T1 and T2.
```

When a dump transaction uses a consistent snapshot, the read data reflects one shared state under MVCC rules. Tools like `pg_dump` establish snapshots and, for parallel dumps, coordinate snapshots across workers under supported conditions.

Never build a backup by copying data directory files while the server is running and assuming a SQL query's snapshot guarantees physical file consistency. Logical dumps and physical backups are separate procedures.

## 36. Isolation Levels in JDBC

JDBC supports configuring isolation on a connection:

```java
int oldIsolation = connection.getTransactionIsolation();
boolean oldAutoCommit = connection.getAutoCommit();

try {
    connection.setTransactionIsolation(
        Connection.TRANSACTION_REPEATABLE_READ
    );
    connection.setAutoCommit(false);

    try (PreparedStatement ps = connection.prepareStatement("""
            SELECT product_id, quantity
            FROM lesson_mvcc.products
            WHERE product_id = ?
            """)) {
        ps.setLong(1, 1L);

        try (ResultSet rs = ps.executeQuery()) {
            if (rs.next()) {
                int quantity = rs.getInt("quantity");
                // Use quantity in business logic.
            }
        }
    }

    connection.commit();
} catch (SQLException | RuntimeException e) {
    try {
        connection.rollback();
    } catch (SQLException rollbackFailure) {
        e.addSuppressed(rollbackFailure);
    }
    throw e;
} finally {
    // Only change isolation/autoCommit after the transaction has ended.
    connection.setAutoCommit(oldAutoCommit);
    connection.setTransactionIsolation(oldIsolation);
}
```

This is an illustrative snippet inside a method with `throws SQLException`, proper imports, and a valid `Connection connection`. In production code, handle errors if restoring connection state fails (e.g., avoid masking the original exception), follow pool contracts, and never change isolation while a transaction is active.

### Can You Call setTransactionIsolation Mid-Transaction?

Avoid changing the isolation level **after a transaction has started executing queries**. PostgreSQL requires setting isolation at the appropriate point before the transaction acquires a snapshot or executes data statements. In JDBC, set isolation **before starting the transaction** or let the transaction manager configure it per framework contract.

### Transaction Isolation Is Not Just a UI Setting

Choosing `REPEATABLE READ`/`SERIALIZABLE` affects:

- The dataset visible to subsequent queries.
- The likelihood of concurrent `40001` errors.
- The need to retry the entire transaction.
- Snapshot retention duration and impact on old versions.
- Locking costs/modes and workload-dependent performance risks.

Never raise isolation levels blindly just to fix a screen bug.

## 37. Spring @Transactional and Snapshots

In Spring, isolation levels can be requested via the transaction manager:

```java
@Service
public class InventoryService {
    private final ProductRepository repository;

    public InventoryService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public InventoryDto getInventory(long productId) {
        Product product = repository.findById(productId)
            .orElseThrow();
        return new InventoryDto(product.getId(), product.getQuantity());
    }
}
```

This is an illustrative skeleton; real projects require full class/import/repository definitions.

Points to watch:

- `@Transactional` must actually be applied through the proxy/aspect/transaction manager per Spring configuration.
- Isolation takes effect only when queries execute inside a **real transaction** using the corresponding connection.
- Self-invocation within the same object may bypass the proxy in common Spring configurations.
- Long transactions caused by remote API calls or slow processing hold snapshots open and impact vacuuming.
- Entity caches / ORM persistence contexts can produce re-read behavior different from plain SQL queries.

### Persistence Context Is Not a PostgreSQL Snapshot

Hibernate/JPA has a **first-level cache**. Reading an entity a second time may return the managed object without even sending an SQL query. Therefore, when debugging MVCC, distinguish:

1. What the PostgreSQL snapshot returns for **an SQL query actually sent**.
2. Whether the ORM even sent SQL.
3. Whether application/client caches interfered.

Do not jump to concluding `REPEATABLE READ` caused "stale data" if the real cause is an ORM cache or reading from a lagging standby.

## 38. Retrying Transactions That Fail With 40001 and 40P01

When encountering:

- **`40001`**: serialization failure.
- **`40P01`**: deadlock detected.

The application can implement a retry policy if the operation is **safe to retry**.

A proper flow:

```text
Attempt 1
  BEGIN
  SELECT data used to make decisions
  Compute business logic
  INSERT/UPDATE
  COMMIT → 40001
  ROLLBACK if needed / per transaction state

Attempt 2: NEW transaction
  BEGIN
  Re-SELECT data
  Recompute logic
  INSERT/UPDATE
  COMMIT → succeeds
```

If the error occurs at `COMMIT`, the transaction may already have been aborted; handle cleanup based on actual connection/driver state. Never try to reuse an old snapshot just to re-run the final `UPDATE`.

### Retries Need Idempotency and Bounds

- Cap attempt counts and use backoff/jitter.
- Log attempt count alongside `SQLSTATE`.
- Never send external emails/payments before commit and then retry repeatedly without control.
- Use idempotency keys / transactional outbox for external side effects.
- Distinguish retriable PostgreSQL errors from network errors **where commit outcome is uncertain**.

## 39. A Query Doesn't See a Row: Diagnostic Flowchart

When an application says "I just INSERTed but SELECT doesn't see it," check in order:

```text
                New row not visible
                         │
                         ▼
               Which database am I on?
                         │
                         ▼
               Right schema/table?
                         │
                         ▼
           Has the new row COMMITted yet?
                    │           │
                   No          Yes
                    │           │
       Other reader not         ▼
       seeing it is valid  Is reader using an old snapshot?
                                │
                         ┌──────┴────────┐
                         │               │
                   REPEATABLE READ   READ COMMITTED
                   old snapshot?     new statement?
                         │               │
                         ▼               ▼
                  End txn and       Check next:
                  try again         replica lag / RLS /
                                    filter / cache
```

### Causes Outside Snapshots

- **Not yet committed** by the writer; reading transactions must not see uncommitted writes.
- **Reading from a standby** that has not yet replayed recent WAL.
- **Wrong database/schema** or different `search_path`.
- **RLS** filtering rows by role/policy.
- **Query `WHERE`/`JOIN`** filtering out the row.
- **ORM cache** returning a stale entity.
- **Connection pool** reusing a transaction kept open longer than expected.
- **Rollback** on the writer after an error, so the row never actually persisted.

Do not blame MVCC for every case of "missing row."

## 40. Stale Data and Query Volume: Long Transactions Must Be Bounded

`REPEATABLE READ` is great for consistent reports, but if a request opens a transaction and does:

```text
BEGIN REPEATABLE READ
  SELECT across many tables
  call HTTP API for 30 seconds
  wait 5 minutes for user confirmation
  more processing
COMMIT
```

then the transaction/snapshot is held unnecessarily long. During that time:

- Subsequent reads may miss data committed after the snapshot.
- `VACUUM` may be restricted from cleaning certain dead tuples.
- A connection remains occupied.
- Locking/writing operations may cause contention.

### Design Principles

1. Keep transactions short, scoped to database work that truly needs a single snapshot.
2. Never hold a transaction open while waiting for user interaction.
3. Avoid long remote I/O inside a transaction whenever it can be separated.
4. Set SLA timeouts and roll back on errors.
5. Measure `xact_start`, `state`, and `backend_xmin` to detect long-running snapshots.

## 41. Why Snapshots Do Not Mean "Time Travel"

PostgreSQL MVCC **does not automatically provide arbitrary querying of data as of any past point in time**.

Once old versions become eligible and are reclaimed by `VACUUM`, the application cannot expect them to remain in the table to re-read via a saved timestamp.

If the requirement is:

- View an order's change history.
- Audit who changed a price and when.
- Restore an old business state.
- Answer "what was inventory on 2025-01-01?"

design a dedicated **audit table, temporal model, event sourcing, change data capture, or PITR/backup** for that need. `xmin`, `xmax`, and snapshots generally do not replace a business history model.

### Why Not Save pg_current_snapshot() in the App to Read Tomorrow?

A snapshot ID and in-progress XID list are not a promise that PostgreSQL will keep every tuple version forever. `pg_export_snapshot()` also has a finite lifecycle tied to the exporting transaction. Do not treat them as durable historical query tokens.

## 42. Common Misconceptions

**"PostgreSQL SELECT always reads the latest version on disk."** No. `SELECT` sees **the version visible under its snapshot**, not necessarily the newest version created by another transaction.

**"A snapshot is a timestamp; comparing created_at is enough."** No. Snapshots use transaction state and XID boundaries, not just system clock time.

**"A larger XID always commits later."** No. ID assignment order differs from commit order.

**"BEGIN always captures a REPEATABLE READ snapshot immediately."** Not necessarily; the snapshot is normally set at the first statement that actually needs one.

**"READ UNCOMMITTED allows dirty reads in PostgreSQL."** No. PostgreSQL treats this level as `READ COMMITTED`.

**"READ COMMITTED holds one snapshot for the whole transaction."** Not for normal `SELECT`s; each statement gets a fresh snapshot.

**"REPEATABLE READ does not see its own UPDATEs."** False. Self-visible writes are handled separately.

**"REPEATABLE READ guarantees full serializability."** No. Write skew can still occur; `SERIALIZABLE` uses SSI.

**"SERIALIZABLE locks the entire database."** No. It uses dependency tracking and can abort transactions with `40001`.

**"A fixed snapshot means UPDATE never has to wait."** False. Contending writers still encounter row locks and recheck/concurrent update rules.

**"If SELECT doesn't see a key, INSERT definitely won't conflict."** False. Unique indexes must consider concurrent transactions, including rows not yet visible to a `SELECT` snapshot.

**"Non-zero xmax means DELETEd."** False. Metadata can reflect row locks/MultiXacts and requires checking status/flags.

**"ctid is a stable ID."** False. It is the physical address of a tuple version, which can change.

**"Just raising isolation fixes all bugs."** No. Stronger isolation can require `40001` retries and carries its own overhead.

**"VACUUM can delete all old versions right away."** No. It must respect the visibility horizon and snapshots still needing the data.

**"n_dead_tup is the exact count of dead rows for the snapshot I'm reading."** No. It is an estimated statistic.

**"Replication standby not seeing data is caused by REPEATABLE READ."** It could be WAL replay lag; isolate the root cause.

**"Snapshots can be saved to query last year's data."** No. MVCC snapshots are not a long-term temporal history mechanism.

**"ORM cache and PostgreSQL snapshot are the same thing."** No. Application caches can return data without sending SQL at all.

**"SELECT FOR UPDATE and normal SELECT have the same writer-waiting behavior."** No. `FOR UPDATE` acquires row locks and has distinct concurrent-modification handling.

## 43. Workflow for Solving Snapshot and Visibility Problems

When designing or troubleshooting, follow this sequence:

1. **Confirm the actual isolation level**: run `SHOW transaction_isolation` on the relevant connection.
2. **Determine whether the transaction has started and acquired a snapshot**: order of `BEGIN` and the first statement, especially under `REPEATABLE READ`.
3. **Identify which transaction created/modified/deleted the row**, and whether it committed.
4. **Distinguish normal `SELECT` from locking/modifying statements** like `UPDATE`, `DELETE`, `SELECT FOR UPDATE`, `ON CONFLICT`.
5. **Check self-visible writes** when reading data created by the same transaction.
6. **Check layers outside MVCC**: schema, RLS, filters, ORM cache, replication lag.
7. **Check long transactions** and vacuum impact via `pg_stat_activity`/`pg_stat_user_tables`.
8. **Choose isolation appropriate for the business rules**; if serializable is required, handle `40001` with full-transaction retries.
9. **Keep transactions short and committed/rolled back** before returning connections to the pool.
10. **Use dedicated business keys and audit mechanisms**, never relying on `ctid` or raw XIDs for long-term features.

Quick-recall diagram:

```text
          A tuple version exists on disk
                       │
                       ▼
             Has the creating txn
             validly committed?
                 │          │
                No         Yes
                 │          │
                 ▼          ▼
           Not visible   Check deletion/replacement
           (to other txn)      │
                              ▼
                   Is the deletion visible
                   under this snapshot?
                       │         │
                      Yes        No
                       │         │
                       ▼         ▼
                Old tuple     Old tuple
                excluded      can be visible

    + Special rules for self-writes, locks, subtransactions,
      command IDs, and concurrent-modification handling.
```

This diagram is an explanatory model and does not replace the actual MVCC algorithm.

## 44. Practice Exercises

### Exercise 1 — Observing System Columns

In the lab, run `SELECT product_id, xmin, xmax, ctid FROM lesson_mvcc.products`. Note what each field means. Why must you never use `ctid` or `xmin` as a business key?

### Exercise 2 — Dirty Read

Session A opens a transaction and sets `quantity = 777` without committing. Session B runs `SELECT` on the same row. Predict what B sees and why. Then roll back A.

### Exercise 3 — READ UNCOMMITTED

Repeat Exercise 2 in session B using `BEGIN ISOLATION LEVEL READ UNCOMMITTED`. Does PostgreSQL allow dirty reads?

### Exercise 4 — READ COMMITTED Two SELECTs

Session A opens `READ COMMITTED` and `SELECT`s quantity. Session B `UPDATE`s and `COMMIT`s. A `SELECT`s again before committing. Explain why the value can change.

### Exercise 5 — REPEATABLE READ Two SELECTs

Repeat Exercise 4, but have A use `REPEATABLE READ` and run its first `SELECT` **before B commits**. Explain why A continues seeing the old data.

### Exercise 6 — Snapshot Timing

A sends `BEGIN ISOLATION LEVEL REPEATABLE READ` without running a `SELECT` yet. B `UPDATE`s and `COMMIT`s. Then A runs its first `SELECT`. Does A necessarily see the pre-`BEGIN` old data? Explain.

### Exercise 7 — Self-Visible Writes

Inside a `REPEATABLE READ` transaction, `SELECT` a product, `UPDATE` its quantity, then `SELECT` again. Explain why the transaction sees its own change, then `ROLLBACK`.

### Exercise 8 — Phantom Read

A under `READ COMMITTED` counts products with `quantity >= 10`. B inserts a matching product and `COMMIT`s. A counts again. What phenomenon is this? How does `REPEATABLE READ` differ?

### Exercise 9 — XID and Commit Order

Suppose T100 starts before T101, but T101 commits first. Does a snapshot taken between the two commits see T100's and T101's changes identically? Explain using the in-progress transaction list.

### Exercise 10 — New and Old Tuples

Sketch two tuple versions for an `UPDATE` changing quantity from 10 to 8. Explain which version a snapshot before vs. after the writer's commit can see.

### Exercise 11 — xmax and Row Locking

Why can't `WHERE xmax = 0` serve as a universal rule to identify all non-deleted rows? Mention the roles of row locks, MultiXacts, and transaction status.

### Exercise 12 — SELECT FOR UPDATE

Session A locks product 1 with `SELECT ... FOR UPDATE` inside a transaction. Session B tries `FOR UPDATE NOWAIT` on the same row. Predict the possible error and the rollback requirement after an error in an explicit transaction.

### Exercise 13 — Concurrent UPDATE Under READ COMMITTED

A changes quantity 10 to 3 without committing. B `UPDATE`s with `WHERE quantity >= 5` and may wait. After A commits, how does PostgreSQL evaluate B's condition? Why shouldn't `UPDATE` be equated with a pure snapshot `SELECT`?

### Exercise 14 — REPEATABLE READ Concurrent Update

A acquires a snapshot when a product has quantity 10. B changes quantity and `COMMIT`s. A tries to `UPDATE` the same row. Under what condition can `40001` occur, and what must the application do?

### Exercise 15 — Unique Constraints and Invisible Rows

A `INSERT`s key `same-key` without committing. B `SELECT`s, sees no key, and tries to `INSERT` the same key. Why can B still wait or receive `23505`?

### Exercise 16 — ON CONFLICT and Snapshots

Explain why `ON CONFLICT DO NOTHING` under `READ COMMITTED` may skip inserting even when the conflicting row is not visible in the statement's regular `SELECT` snapshot.

### Exercise 17 — Lost Update

Two requests both read quantity 10 and send `UPDATE SET quantity = 11`. Explain the lost update risk. Fix it using `quantity = quantity + 1` or optimistic locking with a version column.

### Exercise 18 — Write Skew

Two doctors are on call; two transactions both check "at least one person on call" and then each takes one doctor off call. Why might `REPEATABLE READ` fail to protect this cross-row invariant? How does `SERIALIZABLE` handle it?

### Exercise 19 — pg_current_snapshot

Inspect `pg_current_snapshot()`, `pg_snapshot_xmin()`, `pg_snapshot_xmax()`, and `pg_snapshot_xip()` on modern PostgreSQL. Explain the general meaning of `xmin`, `xmax`, and the in-progress XID list.

### Exercise 20 — Long-Running Snapshot

A opens `REPEATABLE READ`, runs `SELECT`, and keeps the transaction open. B `UPDATE`s many rows, `COMMIT`s, and `VACUUM` runs in another session when appropriate. Why might some old versions remain unreclaimed? End A and compare state after appropriate `VACUUM` runs. **Only perform on a small lab and never run heavy maintenance operations in production.**

### Exercise 21 — pg_stat_activity

From a monitoring session, query `pid`, `state`, `xact_start`, and `backend_xmin`. Find long transactions and distinguish `xact_start` from when a snapshot was actually established.

### Exercise 22 — Snapshots on a Standby

A write commits on the primary, yet an immediate `SELECT` on a standby does not see the row. List ways to distinguish replication lag from an old transaction snapshot, RLS, and ORM cache.

### Exercise 23 — Exporting/Importing Snapshots

With two test sessions, A runs `BEGIN REPEATABLE READ` and `pg_export_snapshot()`. B runs `BEGIN REPEATABLE READ` and `SET TRANSACTION SNAPSHOT` with the real ID before running `SELECT`. How long must A keep its transaction open?

### Exercise 24 — Java/JDBC Isolation

Write a JDBC example setting `Connection.TRANSACTION_REPEATABLE_READ` before a transaction, running a `SELECT`, committing/rolling back, and restoring connection state. Why must you not change isolation mid-transaction once a snapshot exists?

### Exercise 25 — Retrying SERIALIZABLE

Design pseudocode for retrying the entire transaction on `40001`. Each attempt must re-read data and recompute decisions. Why is retrying only the last `UPDATE` insufficient?

### Exercise 26 — Snapshots Are Not Time Travel

An application needs to query daily balances over three years. Why can't you save `pg_current_snapshot()` daily and assume it lets you re-query any point later? Propose a dedicated audit/event history or temporal model.

### Exercise 27 — Designing an API to See Fresh Data

An API writes to the primary, immediately reads from a read replica, and occasionally returns stale state. Propose options such as reading from primary when read-your-writes is required, monitoring replay lag, or waiting until the replica reaches an appropriate LSN. Explain clearly why raising isolation level on the replica alone does not solve replication lag.

### Exercise 28 — Evaluating Isolation Costs

A report runs for one hour under `REPEATABLE READ`. Analyze the benefits of a consistent snapshot alongside long-transaction risks: dead tuple retention, connection occupancy, and autovacuum impact. Propose ways to narrow scope and separate processing steps that do not need to hold the snapshot.

## Conclusion

**MVCC** enables PostgreSQL to store multiple versions of a row and pick the right version for each query using a **snapshot**. A tuple existing physically does not mean every transaction sees it: visibility depends on whether the creating transaction committed, whether any deleting/replacing transaction is visible, the in-progress transaction list, and self-visibility rules within the current transaction.

Under **`READ COMMITTED`**, normal `SELECT` statements receive **a fresh snapshot per statement**, so a transaction can observe different values across two reads. Under **`REPEATABLE READ`**, the snapshot is preserved for the transaction once established, giving consistent reads while still seeing the transaction's own changes. **`SERIALIZABLE`** adds SSI to prevent concurrent schedules not equivalent to serial execution, in exchange for requiring applications to handle `40001` and retry full transactions when appropriate.

Never equate `SELECT` snapshot behavior with every other operation: **`UPDATE`/`DELETE`/`SELECT FOR UPDATE`** have their own locks and concurrency handling; **unique constraints** and **`ON CONFLICT`** must check conflicts even against rows not yet visible to normal `SELECT`s. And because old snapshots can require retaining old tuple versions, long transactions can delay **VACUUM** cleanup.

To design systems correctly, verify **the actual isolation level, snapshot timing, writer commit status, self-writes, replication lag, RLS, and application caches** before concluding data is "inconsistent." Use `pg_current_snapshot()`, `pg_stat_activity`, and vacuum statistics as observability tools; use primary keys, version columns, and dedicated audit mechanisms for business logic. A solid grasp of snapshots and visibility rules is the foundation for leveraging MVCC performance while preserving PostgreSQL transaction correctness.
