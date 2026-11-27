# Distinguishing Object Locks, Row Locks, and Internal Locks in PostgreSQL

In PostgreSQL, the word **lock** does not refer to just one mechanism. An `UPDATE` statement typically acquires a **relation/table-level lock** while also participating in the mechanism that **locks the modified rows**; inside the database engine, multiple processes also use **lightweight locks** and synchronization mechanisms to protect buffers, shared memory, and control structures. Those mechanisms differ in **what they protect, how long they are held, how they are observed, and how contention is handled**.

A common question is:

> Why can transaction B still `SELECT` an account while transaction A is updating that account, whereas another `UPDATE` has to wait?

The answer requires distinguishing **MVCC**, **row locks**, **object locks**, and **internal locks**. It cannot be explained by saying "PostgreSQL locks the whole table during an UPDATE" or "PostgreSQL doesn't lock because it has MVCC": both miss crucial layers.

This lesson focuses on three groups:

1. **Object-level / relation-level locks:** coordinate operations on tables, indexes, and database objects. At the table level, PostgreSQL has eight primary lock modes, from `ACCESS SHARE` to `ACCESS EXCLUSIVE`.
2. **Row-level / tuple locks:** coordinate multiple transactions that want to lock, modify, or delete the **same row**, with four modes: `FOR KEY SHARE`, `FOR SHARE`, `FOR NO KEY UPDATE`, and `FOR UPDATE`.
3. **Internal synchronization:** such as lightweight locks (**LWLocks**), spinlocks, and buffer pins that help PostgreSQL processes protect internal structures; these are **not** locks that an application chooses via `LOCK TABLE` or `SELECT FOR UPDATE`.

There are also **transaction-ID locks**, **advisory locks**, and **predicate/SIRead locks** for Serializable Snapshot Isolation. They are related, but should not be confused with the three main groups.

This lesson includes a practice schema, two-session scenarios, mode comparison tables, `pg_locks`/`pg_stat_activity`/`pg_blocking_pids()` monitoring queries, deadlock analysis guidance, timeouts, and exercises with solutions.

## 1. Overview Model: One SQL Statement Can Use Multiple Lock Layers

Imagine two sessions modifying data:

~~~text
Application A                      Application B
    |                                  |
    v                                  v
 PostgreSQL backend A             PostgreSQL backend B
    |                                  |
    +------------+---------------------+
                 |
      Object / relation locks
      (coordinate DDL, DML, table access)
                 |
      Row / tuple locks
      (contention on the same row)
                 |
      Engine internal synchronization
      (LWLock, spinlock, buffer pin ...)
                 |
           Shared buffers
           WAL / shared memory
           Data pages / storage
~~~

A single transaction can hold **multiple locks across multiple layers simultaneously**. For example:

~~~sql
BEGIN;
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;
-- Not committed yet.
~~~

In terms of concurrency coordination, PostgreSQL can:

- Hold a **`ROW EXCLUSIVE` table-level lock** on the updated relation.
- Mark the affected row under the **tuple locking / MVCC** mechanism, causing another transaction that wants to modify the same row to wait.
- While accessing data pages, use internal synchronization mechanisms for shorter intervals to protect shared-memory structures and buffers.

**There is no single lock broadly called an "UPDATE lock" that covers all three layers.**

## 2. Locks and MVCC: What to Understand First

PostgreSQL uses **Multi-Version Concurrency Control (MVCC)**. Updating a row typically creates a new row version and coordinates visibility based on the transaction's snapshot.

For example:

~~~text
Committed: balance = 1000

Session A: BEGIN
Session A: UPDATE balance = 900    (uncommitted)

Session B: SELECT balance
           -> usually still sees 1000 under READ COMMITTED

Session B: UPDATE balance = 800
           -> must wait for transaction A if modifying the same row
~~~

This is not a contradiction:

- **A plain `SELECT`** can read the committed version matching its snapshot without needing to acquire row locks for reading like `SELECT FOR UPDATE`.
- **`UPDATE`/`DELETE`/`SELECT FOR UPDATE`** participate in locking and coordinate potentially conflicting changes on the same row.
- Certain DDL commands require **strong object locks** that can block even plain `SELECT` queries on the affected table.

### 2.1. Do Not Equate "Can Read" with "No Locks"

A plain `SELECT` still acquires an `ACCESS SHARE` lock on the table, and the backend still uses internal synchronization when reading buffers. Saying "SELECT does not lock" is just misleading shorthand.

A more accurate statement: **a plain `SELECT` does not acquire row-level locks to block normal `UPDATE`s**, though it still participates in relation locking and internal mechanisms.

### 2.2. MVCC Does Not Eliminate All Lock Waits

If two transactions modify the same row, they must coordinate to avoid lost updates and determine the valid row version/update condition. PostgreSQL may wait for the earlier transaction to finish and then re-evaluate depending on the isolation level and statement type.

**MVCC reduces common read-write conflicts; it does not eliminate write-write conflicts.**

## 3. Setting Up the Practice Schema

Only run the following commands in a **lab database**. Some exercises intentionally leave transactions uncommitted or create lock waits; do not run them directly on production.

### 3.1. Accounts Table

~~~sql
CREATE SCHEMA lock_lab;

CREATE TABLE lock_lab.accounts (
    account_id integer PRIMARY KEY,
    owner_name text NOT NULL,
    balance numeric(12, 2) NOT NULL CHECK (balance >= 0),
    note text,
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO lock_lab.accounts (
    account_id, owner_name, balance, note
) VALUES
    (1, 'An',   1000.00, 'A'),
    (2, 'Binh',  500.00, 'B'),
    (3, 'Chi',   250.00, 'C'),
    (4, 'Dung',  300.00, 'D');
~~~

### 3.2. Orders Table with a Foreign Key

~~~sql
CREATE TABLE lock_lab.orders (
    order_id integer PRIMARY KEY,
    account_id integer NOT NULL
        REFERENCES lock_lab.accounts(account_id),
    amount numeric(12, 2) NOT NULL CHECK (amount > 0),
    status text NOT NULL CHECK (
        status IN ('new', 'paid', 'cancelled')
    )
);

INSERT INTO lock_lab.orders
    (order_id, account_id, amount, status)
VALUES
    (101, 1, 120.00, 'new'),
    (102, 1,  80.00, 'paid'),
    (201, 2,  50.00, 'new'),
    (301, 3, 200.00, 'paid');
~~~

### 3.3. Inspecting the Data

~~~sql
SELECT account_id, owner_name, balance
FROM lock_lab.accounts
ORDER BY account_id;

SELECT order_id, account_id, status
FROM lock_lab.orders
ORDER BY order_id;
~~~

The scenarios below are designed to end with `ROLLBACK` whenever possible, restoring the initial data. If you choose to `COMMIT` a change, the lab values will change accordingly.

### 3.4. Opening Two Connections

Open two `psql` windows or two independent connections in your GUI tool:

~~~text
Session A: first transaction
Session B: second transaction
~~~

You can check each session's PID:

~~~sql
SELECT pg_backend_pid();
~~~

The PID values of A and B are different. Checking the PID helps distinguish **two truly separate connections** from two tabs sharing a connection.

## 4. What Is an Object Lock?

Here, **object locks** are the locks PostgreSQL uses to coordinate operations on a database object; the most common type is **relation-level/table-level locks**.

For example:

~~~sql
BEGIN;
LOCK TABLE lock_lab.accounts IN SHARE MODE;
-- Keep the transaction open.
~~~

The `LOCK TABLE` command acquires the `SHARE` mode on the `accounts` table. Transactions that request a conflicting mode on the table will wait.

### 4.1. "Table Lock" Does Not Always Mean Blocking All Access

PostgreSQL has **multiple table lock modes**. Some modes can coexist; others conflict and must wait.

For example:

- A plain `SELECT` acquires `ACCESS SHARE`, which is compatible with many other modes.
- `INSERT`/`UPDATE`/`DELETE` typically acquire `ROW EXCLUSIVE`.
- `ALTER TABLE` can require `ACCESS EXCLUSIVE` in many cases.

You should not describe a simple `UPDATE` as "locking the entire table so no one can use it": even though it holds table-level `ROW EXCLUSIVE`, **multiple `UPDATE`s on different rows can still run concurrently**.

### 4.2. What Do Object Locks Protect?

The goal of a relation-level lock is not just the data in individual rows. It coordinates:

- Querying and modifying data.
- Creating/altering table structure and certain index operations.
- Table maintenance or metadata changes that might conflict.
- Operations that require stable usage of the relation within a transaction.

These modes are **heavyweight locks** tracked by PostgreSQL's main lock manager. Internal lightweight locks (LWLocks) are a separate mechanism.

## 5. The Eight PostgreSQL Table Lock Modes

The mode names are easy to confuse: `ROW SHARE` and `ROW EXCLUSIVE` are **names of two table-level lock modes**, **not** locks on a specific row.

| Table-level mode | Common associated activity | Practical meaning |
| --- | --- | --- |
| `ACCESS SHARE` | Plain `SELECT` | Reads the table; mainly conflicts with ACCESS EXCLUSIVE |
| `ROW SHARE` | `SELECT ... FOR UPDATE/SHARE` | Reads combined with row-lock requests |
| `ROW EXCLUSIVE` | `INSERT`, `UPDATE`, `DELETE` | Write DML; does not block all other DML on its own |
| `SHARE UPDATE EXCLUSIVE` | Plain `VACUUM`, `ANALYZE`, some maintenance/DDL | Coordinates maintenance and structural changes |
| `SHARE` | Plain `CREATE INDEX`, `LOCK TABLE ... IN SHARE MODE` | Can block write DML while building an index |
| `SHARE ROW EXCLUSIVE` | Certain DDL operations or explicit `LOCK TABLE` | Blocks many write/maintenance types, self-conflicting |
| `EXCLUSIVE` | `LOCK TABLE ... IN EXCLUSIVE MODE` | Allows ACCESS SHARE but blocks many other modes |
| `ACCESS EXCLUSIVE` | `TRUNCATE`, `DROP TABLE`, many `ALTER TABLE` variants | Strongest mode; blocks even plain SELECT |

**The chosen mode depends on the exact command and version/execution path.** Do not assume every `ALTER TABLE` variant takes the same lock mode; consult the documentation for the specific command before deploying a migration to production.

### 5.1. ACCESS SHARE

~~~sql
SELECT *
FROM lock_lab.accounts
WHERE account_id = 1;
~~~

A plain `SELECT` acquires `ACCESS SHARE` on the accessed relation. `ACCESS SHARE` **conflicts with ACCESS EXCLUSIVE**, but is compatible with all remaining table-level modes.

Therefore, in many situations, `SELECT` still runs while another transaction is executing `UPDATE`, because `UPDATE` holds table-level `ROW EXCLUSIVE`, which **does not conflict with ACCESS SHARE**.

### 5.2. ROW SHARE

~~~sql
BEGIN;

SELECT *
FROM lock_lab.accounts
WHERE account_id = 1
FOR UPDATE;

ROLLBACK;
~~~

`SELECT FOR UPDATE` acquires table-level `ROW SHARE` on the target table, **while also** locking the selected rows in row-level `FOR UPDATE` mode.

Be sure to distinguish **table-level ROW SHARE** from **row-level FOR SHARE**: both names contain "SHARE", but they belong to **two different lock layers**.

### 5.3. ROW EXCLUSIVE

~~~sql
BEGIN;
UPDATE lock_lab.accounts
SET note = 'changed'
WHERE account_id = 1;
ROLLBACK;
~~~

`UPDATE` typically acquires table-level `ROW EXCLUSIVE`. The name sounds strong, but this mode is **compatible with itself**: two transactions updating **different rows** usually do not block each other solely because of the table lock mode.

### 5.4. ACCESS EXCLUSIVE

~~~sql
BEGIN;
LOCK TABLE lock_lab.accounts
    IN ACCESS EXCLUSIVE MODE;
-- Keep the transaction open to observe.
~~~

If B runs `SELECT ... FROM lock_lab.accounts`, it usually has to wait until A releases the strong mode.

This is a classic example of why **DDL or strong object locks** can block even simple read queries.

## 6. Conflict Matrix for Table-Level Modes

The matrix below shows whether two modes on the **same relation** conflict. `X` means conflict; `–` means compatible.

| Held ↓ / Requested → | AS | RS | RX | SUE | S | SRE | X | AX |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **AS** | – | – | – | – | – | – | – | X |
| **RS** | – | – | – | – | – | – | X | X |
| **RX** | – | – | – | – | X | X | X | X |
| **SUE** | – | – | – | X | X | X | X | X |
| **S** | – | – | X | X | – | X | X | X |
| **SRE** | – | – | X | X | X | X | X | X |
| **X** | – | X | X | X | X | X | X | X |
| **AX** | X | X | X | X | X | X | X | X |

Abbreviations:

- **AS** = `ACCESS SHARE`.
- **RS** = `ROW SHARE`.
- **RX** = `ROW EXCLUSIVE`.
- **SUE** = `SHARE UPDATE EXCLUSIVE`.
- **S** = `SHARE`.
- **SRE** = `SHARE ROW EXCLUSIVE`.
- **X** = `EXCLUSIVE`.
- **AX** = `ACCESS EXCLUSIVE`.

### 6.1. Reading the Matrix

**Case 1:** A holds `ROW EXCLUSIVE`, and B also requests `ROW EXCLUSIVE` on the same table → **compatible at the table level**. However, the two transactions can still block each other at the **row level** if they modify the same row.

**Case 2:** A holds `SHARE`, and B requests `ROW EXCLUSIVE` → **conflict**. A normal index build can cause write transactions to wait.

**Case 3:** A holds `ACCESS EXCLUSIVE`, and B requests `ACCESS SHARE` → **conflict**. Even plain `SELECT`s wait.

### 6.2. A Strong Mode Does Not Always Lock Every Object

Locks apply only to **specific objects**, and their scope depends on the command. `ACCESS EXCLUSIVE` on `accounts` does not mean the entire database is locked. Related objects (indexes, referenced tables, partitions, etc.) may acquire their own locks depending on the command.

## 7. How Long Object Locks Are Held

Table-level locks requested by a statement are typically held **until the end of the transaction** (commit or rollback), not merely for the few microseconds it takes to execute the SQL statement.

~~~sql
-- Session A:
BEGIN;

LOCK TABLE lock_lab.accounts IN SHARE MODE;

-- Now A runs no more SQL, but the transaction remains open.
~~~

Session B:

~~~sql
-- Session B: DML requires ROW EXCLUSIVE and will wait.
UPDATE lock_lab.accounts
SET note = 'from B'
WHERE account_id = 1;
~~~

After A runs `COMMIT` or `ROLLBACK`, B can proceed.

### 7.1. How Autocommit Affects Lock Duration

If you run this standalone:

~~~sql
LOCK TABLE lock_lab.accounts IN SHARE MODE;
~~~

outside an explicit transaction in autocommit mode, the statement's transaction ends immediately once the statement completes. The lock does not continue protecting a subsequent SQL statement.

To hold a lock across multiple statements, they must run in the **same transaction on the same connection**.

### 7.2. NOWAIT with LOCK TABLE

~~~sql
BEGIN;
LOCK TABLE lock_lab.accounts
    IN ACCESS EXCLUSIVE MODE NOWAIT;
ROLLBACK;
~~~

`NOWAIT` instructs PostgreSQL **not to wait** if the mode cannot be acquired immediately. Inside a transaction, failing to acquire a lock raises an error that puts the transaction in an aborted state requiring rollback or savepoint handling. Do not treat `NOWAIT` as a way to "force a lock past another transaction."

## 8. What Is a Row Lock?

A **row-level lock** coordinates transactions competing on the **same row** when locking, modifying, or deleting it.

For example:

~~~sql
-- Session A:
BEGIN;
UPDATE lock_lab.accounts
SET note = 'A'
WHERE account_id = 1;
-- Not committed yet.
~~~

Session B:

~~~sql
-- Session B:
BEGIN;
UPDATE lock_lab.accounts
SET note = 'B'
WHERE account_id = 1;
-- Must wait for transaction A under normal conditions.
~~~

After A finishes its transaction, B can proceed or receive an error depending on the isolation level and conditions. If B modifies `account_id = 2` instead of 1, it can usually proceed because the two transactions are modifying **different rows**, even though both hold table-level `ROW EXCLUSIVE`.

### 8.1. A Row-Level Lock Does Not Lock the Whole Table

The table-level `ROW EXCLUSIVE` acquired by two `UPDATE`s is compatible. **The point of contention between two `UPDATE`s on the same row lies in the tuple/transaction mechanism**, not in table-level `ROW EXCLUSIVE` conflicting with itself.

### 8.2. Row Locks Are Represented Differently in the System

Row-lock state involves the **tuple header** and transaction/MultiXact status, rather than every row lock appearing as a separate "granted row lock" entry in the shared-memory lock table.

Consequently, `pg_locks` usually **does not display a complete list of all currently held row locks**. When a backend waits on a row being modified by another transaction, you typically see a wait involving **`transactionid`** or related lock manager entries, rather than a simple list where "each locked row = one `pg_locks` row."

## 9. The Four Row Lock Modes

PostgreSQL supports four common row-level modes:

| Row-level mode | Typical purpose | Relative strength |
| --- | --- | --- |
| `FOR KEY SHARE` | Protects referenced keys, commonly used in FK checks | Lighter than FOR SHARE for updates that do not change keys |
| `FOR SHARE` | Holds a shared row lock when reading needs protection from update/delete | Allows multiple readers to share |
| `FOR NO KEY UPDATE` | Locks a row when an update does not modify relevant key columns | Stronger than FOR SHARE, weaker than FOR UPDATE |
| `FOR UPDATE` | Strongest row lock; prevents other competing operations on the row | Conflicts with all four modes |

Key point: these are **row-level modes**, distinct from the table-level mode names.

### 9.1. FOR UPDATE

~~~sql
BEGIN;

SELECT account_id, balance
FROM lock_lab.accounts
WHERE account_id = 1
FOR UPDATE;

-- Check conditions, then UPDATE in the same transaction.
ROLLBACK;
~~~

`FOR UPDATE` locks the selected rows with the strongest row mode. Another transaction attempting to `UPDATE`/`DELETE` or acquire a conflicting row lock on the same row will usually have to wait.

### 9.2. FOR NO KEY UPDATE

~~~sql
BEGIN;

SELECT account_id, note
FROM lock_lab.accounts
WHERE account_id = 1
FOR NO KEY UPDATE;

ROLLBACK;
~~~

This mode is weaker than `FOR UPDATE`: it allows certain compatible `FOR KEY SHARE` operations. PostgreSQL typically chooses the appropriate mode for an `UPDATE` depending on whether the update modifies special key columns.

### 9.3. FOR SHARE

~~~sql
BEGIN;

SELECT account_id, balance
FROM lock_lab.accounts
WHERE account_id = 1
FOR SHARE;

ROLLBACK;
~~~

Multiple transactions can hold `FOR SHARE` on the same row simultaneously. However, they will block a transaction trying to `UPDATE` that row until the locks are released.

### 9.4. FOR KEY SHARE

~~~sql
BEGIN;

SELECT account_id
FROM lock_lab.accounts
WHERE account_id = 1
FOR KEY SHARE;

ROLLBACK;
~~~

This mode is commonly used to protect the existence/value of referenced keys; it is compatible with `FOR NO KEY UPDATE` but conflicts with `FOR UPDATE`. This is one reason why FK checks and updates to non-key columns can run concurrently in many cases.

## 10. Row Lock Conflict Matrix

`X` = conflict when two different transactions request modes on the **same row**; `–` = compatible.

| Held ↓ / Requested → | KEY SHARE | SHARE | NO KEY UPDATE | UPDATE |
| --- | :---: | :---: | :---: | :---: |
| **FOR KEY SHARE** | – | – | – | X |
| **FOR SHARE** | – | – | X | X |
| **FOR NO KEY UPDATE** | – | X | X | X |
| **FOR UPDATE** | X | X | X | X |

Observations:

1. Two transactions both using `FOR KEY SHARE` are compatible.
2. Two transactions both using `FOR SHARE` are compatible.
3. `FOR SHARE` blocks `FOR NO KEY UPDATE` and `FOR UPDATE` on the same row.
4. `FOR KEY SHARE` **does not block** `FOR NO KEY UPDATE`, but it blocks `FOR UPDATE`.
5. `FOR UPDATE` conflicts with all other row lock modes.

### 10.1. UPDATE Does Not Always Use the Strongest Mode

An `UPDATE` that changes **non-key columns** typically uses row-lock behavior equivalent to `FOR NO KEY UPDATE`. When an update may change key values used by PostgreSQL's rules, it may require `FOR UPDATE`.

Do not equate every `UPDATE` with `FOR UPDATE`; this distinction matters when **foreign keys** and `FOR KEY SHARE` are involved.

### 10.2. DELETE

`DELETE` typically requires a strong row mode equivalent to `FOR UPDATE` because removing the row makes concurrent references and operations holding the row unsafe.

## 11. Lab 1: SELECT Can Read While an UPDATE Is Uncommitted

Session A:

~~~sql
BEGIN;

UPDATE lock_lab.accounts
SET balance = balance + 100
WHERE account_id = 1;

SELECT account_id, balance
FROM lock_lab.accounts
WHERE account_id = 1;
~~~

A sees **1100.00**, because it can read uncommitted changes made by its own transaction.

Session B:

~~~sql
SELECT account_id, balance
FROM lock_lab.accounts
WHERE account_id = 1;
~~~

Under `READ COMMITTED` with no other committed changes, B still sees **1000.00**. A plain `SELECT` is not blocked by the row being modified in the way an `UPDATE` would be.

Session A finishes:

~~~sql
ROLLBACK;
~~~

Account 1 returns to **1000.00**.

### 11.1. This Is Not a Dirty Read

PostgreSQL does not let Session B read the uncommitted value 1100 even if B uses `READ UNCOMMITTED`; in PostgreSQL, that isolation level is effectively treated the same as `READ COMMITTED` for data visibility.

### 11.2. Nor Does It Mean B Always Reads Immediately

If there is an **ACCESS EXCLUSIVE object lock** on the table or other waits on the query side, `SELECT` can still be blocked. Always check both the **wait type and target object** rather than inferring everything solely from MVCC.

## 12. Lab 2: Two UPDATEs on the Same Row

Session A:

~~~sql
BEGIN;

UPDATE lock_lab.accounts
SET note = 'session A'
WHERE account_id = 1;

-- Do not COMMIT/ROLLBACK yet.
~~~

Session B:

~~~sql
BEGIN;

UPDATE lock_lab.accounts
SET note = 'session B'
WHERE account_id = 1;
-- B typically waits on transaction A.
~~~

While B is waiting, use **Session C** (a third connection) to inspect `pg_stat_activity` and `pg_locks` in the later sections.

Session A:

~~~sql
ROLLBACK;
~~~

At this point B can proceed with its `UPDATE`. To preserve the lab data:

~~~sql
-- Session B:
ROLLBACK;
~~~

### 12.1. Switching B to a Different Row

Repeat, but have B update:

~~~sql
UPDATE lock_lab.accounts
SET note = 'session B'
WHERE account_id = 2;
~~~

It normally proceeds **without waiting** for A's row lock on account 1. Both transactions still hold table-level `ROW EXCLUSIVE` on the table, but that mode is **compatible with itself**.

### 12.2. A Lock Wait Is Not a Deadlock

A one-way wait:

~~~text
B waits for A
A does not wait for B
~~~

is just normal **lock contention**. A deadlock requires a **dependency cycle**, such as A waiting for B while B simultaneously waits for A.

## 13. Lab 3: SELECT FOR UPDATE vs. Plain SELECT

Session A:

~~~sql
BEGIN;
SELECT account_id, balance
FROM lock_lab.accounts
WHERE account_id = 1
FOR UPDATE;
~~~

Session B:

~~~sql
-- Plain SELECT: usually reads without waiting.
SELECT account_id, balance
FROM lock_lab.accounts
WHERE account_id = 1;
~~~

Then B tries:

~~~sql
BEGIN;
SELECT account_id, balance
FROM lock_lab.accounts
WHERE account_id = 1
FOR UPDATE;
-- B must wait for the row held by A.
~~~

Session A runs `ROLLBACK`, then B runs `ROLLBACK`.

### 13.1. NOWAIT

If you do not want B to wait:

~~~sql
BEGIN;
SELECT account_id, balance
FROM lock_lab.accounts
WHERE account_id = 1
FOR UPDATE NOWAIT;
ROLLBACK;
~~~

When the row lock cannot be acquired immediately, `NOWAIT` raises an error instead of waiting. If an error occurs inside a transaction, you must roll back or handle a savepoint properly.

### 13.2. SKIP LOCKED

~~~sql
SELECT account_id, balance
FROM lock_lab.accounts
ORDER BY account_id
FOR UPDATE SKIP LOCKED;
~~~

`SKIP LOCKED` **skips rows that are currently locked** instead of waiting, which is useful for **multi-worker job queues**.

However, the result is an **incomplete view that varies with concurrency**. Do not casually use `SKIP LOCKED` for inventory audits, financial reconciliations, or queries requiring a complete list.

### 13.3. Scope of NOWAIT/SKIP LOCKED

They primarily control **row-level locking** behavior in `SELECT FOR UPDATE/SHARE`. They do not turn every table-level lock wait into "no-wait"; PostgreSQL still must acquire the relevant relation locks.

## 14. Lab 4: Strong Object Lock Blocking SELECT

Session A:

~~~sql
BEGIN;

LOCK TABLE lock_lab.accounts
    IN ACCESS EXCLUSIVE MODE;

-- Keep the transaction open.
~~~

Session B:

~~~sql
SELECT account_id, balance
FROM lock_lab.accounts
WHERE account_id = 1;
-- B must wait.
~~~

Unlike the scenario where A only `UPDATE`s one row, here A holds an **ACCESS EXCLUSIVE relation lock**, which conflicts with the `ACCESS SHARE` that B needs.

Session A:

~~~sql
ROLLBACK;
~~~

B proceeds. This is the basic pattern of **DDL or strong locks stalling read queries**.

### 14.1. Lock Queue and Cascading Waits

Suppose A holds `ACCESS SHARE` in a long-running transaction, B is waiting for `ACCESS EXCLUSIVE`, and then C starts requesting `ACCESS SHARE`. Depending on the lock queue and lock requests, C can also get queued behind B to prevent starving the waiting strong lock request.

This explains why a **waiting** schema change can cause many new `SELECT`s to pile up behind it, even though `SELECT`s are normally compatible with A's read lock.

When investigating, do not only ask "who is holding ACCESS EXCLUSIVE?"; also check **waiting requests** in the lock queue.

## 15. Lab 5: SHARE Table Lock Blocks DML but Not SELECT

Session A:

~~~sql
BEGIN;
LOCK TABLE lock_lab.accounts IN SHARE MODE;
~~~

Session B:

~~~sql
SELECT COUNT(*) FROM lock_lab.accounts;
-- Executes normally because ACCESS SHARE is compatible with SHARE.
~~~

However:

~~~sql
UPDATE lock_lab.accounts
SET note = 'test'
WHERE account_id = 1;
-- Requires ROW EXCLUSIVE; conflicts with SHARE.
~~~

Session A runs `ROLLBACK` to release the `SHARE` lock.

Key takeaway: **object locks have multiple strength levels and a conflict matrix**, not a binary "table locked / unlocked" switch.

## 16. Row Locks and FOREIGN KEYs

A foreign key is not just an existence-check constraint. To protect referential integrity under concurrent changes, PostgreSQL uses appropriate row locks on the referenced row.

In the lab:

~~~sql
CREATE TABLE lock_lab.orders (
    -- ...
    account_id integer NOT NULL
        REFERENCES lock_lab.accounts(account_id)
);
~~~

When inserting a new order referencing `account_id = 1`, PostgreSQL must ensure the referenced account row remains valid. One related mechanism is locking the referenced row in **`FOR KEY SHARE`** mode.

### 16.1. Why Is FOR KEY SHARE Weaker Than FOR SHARE?

Suppose transaction A updates `note` on account 1 **without changing the key**:

~~~sql
BEGIN;
UPDATE lock_lab.accounts
SET note = 'updated without changing key'
WHERE account_id = 1;
~~~

An `UPDATE` that does not change keys typically uses row-lock semantics like `FOR NO KEY UPDATE`; this mode is **compatible with `FOR KEY SHARE`**. Therefore, in many situations, another transaction inserting a child row referencing account 1 can still proceed.

If A **deletes the parent row** or changes the referenced key, that conflicts with protecting the referenced key, and the transactions must coordinate so the FK is not violated.

### 16.2. Do Not Assume All FKs Wait the Same Way

Behavior also depends on:

- Whether the operation is a child `INSERT`, key `UPDATE`, or parent `DELETE`.
- Whether the constraint is `NOT DEFERRABLE` or `DEFERRABLE`, and when it is checked.
- Indexes/keys on the referenced row.
- Execution order of the transactions.

**`FOR KEY SHARE` does not replace proper FK design**, and an actual SQL statement may acquire multiple locks on both the parent and child tables.

## 17. Object Locks and Maintenance: VACUUM, ANALYZE, CREATE INDEX

Maintenance tasks must coordinate with DML/DDL, but not all maintenance operations lock tables the same way.

| Operation | Notable locking behavior |
| --- | --- |
| Plain `VACUUM` | Involves `SHARE UPDATE EXCLUSIVE` on the processed table |
| `ANALYZE` | Typically uses a maintenance mode such as `SHARE UPDATE EXCLUSIVE` |
| `VACUUM FULL` | Requires a very strong lock, typically `ACCESS EXCLUSIVE` |
| Plain `CREATE INDEX` | Involves `SHARE`, which can block writes |
| `CREATE INDEX CONCURRENTLY` | Uses a different workflow/locking to minimize write blocking, but must run outside a transaction block |
| Some `ALTER TABLE` commands | May require `ACCESS EXCLUSIVE` depending on the subcommand |

### 17.1. Plain VACUUM vs. VACUUM FULL

~~~sql
VACUUM (ANALYZE) lock_lab.accounts;
~~~

differs greatly in lock impact from:

~~~sql
VACUUM FULL lock_lab.accounts;
~~~

`VACUUM FULL` rewrites the table and requires a strong lock that easily blocks access. When planning operations, distinguish the **type of VACUUM** rather than treating them under one name.

### 17.2. CREATE INDEX CONCURRENTLY

~~~sql
CREATE INDEX CONCURRENTLY idx_orders_account_status
ON lock_lab.orders(account_id, status);
~~~

This command is designed to reduce write blocking in certain contexts, but it runs in multiple phases, must wait for relevant transactions/snapshots, and **cannot be run inside a normal explicit transaction block**.

Do not conclude that "CONCURRENTLY means no locks or no waits." It still coordinates with other processes and has operational constraints.

## 18. What Are Internal Locks?

Beyond locks that control **logical access to relations/rows**, PostgreSQL must synchronize backends operating concurrently on:

- Buffers in `shared_buffers`.
- Shared-memory structures.
- Buffer manager metadata and control structures.
- Certain structures related to WAL and internal resource management.

Internal mechanisms include **lightweight locks (LWLocks)**, **spinlocks**, **buffer pins**, and other synchronization primitives.

### 18.1. LWLock

A **lightweight lock** protects internal data structures or shared resource regions for brief/bounded operations. A backend must acquire an LWLock when operating on a given structure; if another backend holds a conflicting mode, it may have to wait.

Unlike `LOCK TABLE`:

- Applications **do not select** a specific LWLock via SQL `LOCK TABLE`.
- An LWLock **does not represent a business-level row lock**.
- Hold duration and ownership rules are managed by the engine around internal operations, not strictly "from `BEGIN` to `COMMIT`" in all cases.
- Even a plain read query can encounter LWLock contention if many backends access the same internal resource concurrently.

### 18.2. Spinlock

A spinlock is a low-level synchronization mechanism used to protect certain shared-memory states during **very short code sections**. Under contention, acquiring a spinlock may busy-wait briefly depending on the implementation.

Do not use "spinlock" as a synonym for `FOR UPDATE`. Spinlocks are **internal to the database engine**, not a "record lock" that application developers toggle with SQL.

### 18.3. Buffer Pin

A **buffer pin** is how a backend holds a reference to a buffer to protect it from inappropriate operations like eviction/replacement while it is still referenced.

A backend can wait on `BufferPin` if an operation requires a buffer to be unpinned while another backend still holds a pin. `BufferPin` is reported as a **distinct `wait_event_type`** and should not be lumped together with `LWLock`.

### 18.4. Page/Buffer Locks Are Not Row Locks

When reading or writing a data page, PostgreSQL may need short-term synchronization at the page/buffer level. However, **row-level locks** coordinate transactions modifying the same row via a different mechanism.

Do not say "PostgreSQL only locks pages" instead of rows: PostgreSQL can simultaneously use **internal page/buffer synchronization** and **row/transaction locking**.

## 19. Comparing Object, Row, and Internal Locks

| Criterion | Object / relation lock | Row / tuple lock | Internal lock / LWLock, spinlock, etc. |
| --- | --- | --- | --- |
| Protects | Access permissions / coordination on relations and objects | Contention on specific rows | Engine structures, shared memory, buffers, etc. |
| Example SQL triggering it | `SELECT`, `UPDATE`, `ALTER TABLE`, `LOCK TABLE` | `UPDATE`, `DELETE`, `SELECT FOR UPDATE` | Any query requiring the engine to access the relevant structure |
| User chooses mode directly? | Possible with `LOCK TABLE`; many commands acquire automatically | Possible with `FOR UPDATE/SHARE`; DML picks appropriately | Not via normal SQL |
| Typical hold duration | Usually until end of transaction | Usually until end of transaction | Duration of internal operation, usually shorter |
| Complete entries in `pg_locks`? | Many heavyweight locks are visible | **No** complete list of all granted row locks | **Not** represented as corresponding `pg_locks` rows |
| Common wait indicator | `wait_event_type = 'Lock'` | `Lock`, often on `transactionid` or related lock entries | `LWLock`, `BufferPin`, or other wait event groups |
| Investigation approach | Mode matrix, `pg_locks`, blocker PID | Two sessions, `transactionid`, `pg_blocking_pids` | `pg_stat_activity.wait_event_type/wait_event`, workload/internal contention |
| Mitigation direction | Shorten transactions, schedule DDL, choose appropriate lock modes | Lock ordering, indexes, `NOWAIT`/`SKIP LOCKED` where appropriate, rollback | Analyze workload, version, I/O/buffer/WAL, connection count, and execution plans |

### 19.1. The Same Query Can Wait for Many Reasons

A slow `UPDATE` statement may be slow because of:

- Another transaction holding a **row lock** on the same row.
- A conflicting **relation lock** held by DDL.
- Waiting on an internal **LWLock**.
- Waiting on **I/O**.
- A slow execution plan, scanning too many rows, or CPU saturation.

**Do not diagnose everything by only looking for "locked rows."**

## 20. Heavyweight Locks Are Not Just Relations

In `pg_locks`, PostgreSQL also tracks lock/wait types such as:

- `relation`: relations (tables, indexes, etc. depending on the operation).
- `transactionid`: waiting on or holding rights associated with a transaction ID.
- `virtualxid`: related to a virtual transaction ID.
- `tuple` and `page`: certain entries used during lock/wait coordination.
- `object` and other locktypes for specific object types or mechanisms.
- `advisory`: application-requested locks keyed by logical IDs.

**Transaction-ID locks** are critical: when B waits for A's modification to a row, B may wait for A's transaction ID to finish. Queries that only look for `locktype = 'tuple'` often **miss** this type of wait.

### 20.1. Transaction-ID Waits Differ from Relation-Level Conflicts

Pattern:

~~~text
A holds an uncommitted change on account 1
B wants to UPDATE account 1
B waits for A's transaction to end
~~~

`pg_locks` may show B waiting for a `ShareLock` on A's `transactionid`, while A holds the corresponding lock for that transaction.

**Do not conclude that B is not row-blocked just because you do not see a granted `tuple` entry in `pg_locks`.**

### 20.2. Row-Level Locks Leave Traces in the Tuple

Row locks use information in the tuple/header and may involve a `MultiXactId` when multiple transactions share a row-lock state. This is why row locks should not be thought of as a simple array of entries like relation locks in the shared-memory lock table.

Application developers usually do not need to manipulate tuple headers or MultiXacts directly; in operations, recognize their symptoms via `transactionid` waits and row-level conflict outcomes.

## 21. Advisory Locks: Application-Defined Locks

PostgreSQL provides **advisory locks** so applications can synchronize around a logical numeric key, such as "only one worker processes job 42."

~~~sql
BEGIN;

SELECT pg_advisory_xact_lock(42);

-- Work requiring exclusivity on key 42 within the transaction.

ROLLBACK;
~~~

`pg_advisory_xact_lock` is scoped to the transaction and released when the transaction ends. There are also **session-level advisory locks** held across the session until explicitly unlocked or the session ends.

### 21.1. Advisory Locks Differ from FKs and Row Locks

An advisory lock **does not automatically force every SQL statement updating account 42 to respect key 42**. Only code paths that follow the convention of acquiring the same advisory lock coordinate this way.

With row locks, PostgreSQL enforces conflicts whenever transactions operate on the same row under SQL semantics. With advisory locks, **application conventions** define what the ID means.

### 21.2. TRY Locks

~~~sql
BEGIN;

SELECT pg_try_advisory_xact_lock(42) AS acquired;

ROLLBACK;
~~~

The function returns a boolean: `false` if it cannot acquire the lock immediately, instead of waiting. In real workflows, code must check `acquired` before performing the protected work.

### 21.3. Do Not Mistake Advisory Locks for Transactions

Advisory locks help coordinate concurrency; they **do not automatically make external side effects or changes outside transaction boundaries atomic**.

## 22. Predicate Locks and SERIALIZABLE

PostgreSQL implements **Serializable Snapshot Isolation (SSI)** at the `SERIALIZABLE` isolation level. To detect read-write conflict patterns that could violate serializability, PostgreSQL uses **predicate/SIRead locks** and tracks dependencies.

~~~sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*)
FROM lock_lab.orders
WHERE amount > 100;

-- Other statements...
COMMIT;
~~~

In `pg_locks`, you may see `SIReadLock` mode associated with SSI in certain situations.

### 22.1. SIReadLock Is Not Like ACCESS EXCLUSIVE

Predicate/SIRead locks are **not intended to immediately block writers** matching a condition the way a strong row lock does. PostgreSQL can allow transactions to proceed and then **abort one with a serialization failure** if it detects an unsafe dependency cycle.

This is distinct from:

- `FOR UPDATE`, which locks rows directly.
- Relation-level `ACCESS EXCLUSIVE`, which blocks conflicting modes.
- Internal LWLocks, which protect shared-memory structures.

### 22.2. Handling SQLSTATE 40001

If a `SERIALIZABLE` transaction fails with `40001`, the application typically needs to **retry the entire transaction** (not just the failed statement) with bounded retries and proper idempotency.

Do not raise the isolation level and assume concurrency failures will disappear; verification overhead and retry logic are part of the design.

## 23. Observing Locks with pg_stat_activity

`pg_stat_activity` shows backend state, running queries, transaction start times, and current wait types.

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start,
    now() - xact_start AS transaction_age,
    LEFT(query, 200) AS query_preview
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY pid;
~~~

### 23.1. Common wait_event_type Values

| wait_event_type | Investigation clue |
| --- | --- |
| `Lock` | Backend is waiting for a heavyweight lock or related lock-manager mechanism |
| `LWLock` | Waiting on an internal lightweight lock |
| `BufferPin` | Waiting for a buffer pin to be released |
| `IO` | Waiting for an I/O operation |
| `Client` | Waiting for client communication activity |
| `IPC` | Waiting for an inter-process coordination signal/event |
| `Timeout` | Waiting on a timeout/timer for a specific operation |

Exact values/events depend on PostgreSQL version and runtime state. `wait_event_type IS NULL` is not enough to conclude whether a query has a problem.

### 23.2. Do Not Confuse state with wait_event_type

`state = 'active'` indicates the backend is executing a query or active within a query context. It **can still be waiting** with `wait_event_type = 'Lock'`.

`state = 'idle in transaction'` means the transaction is still open while the backend waits for commands from the client; this session can **hold locks and block others**, even though it is not active.

### 23.3. Permissions to Read Information

A session usually only has full visibility into its own query/details unless granted monitoring privileges. Administrative roles or `pg_read_all_stats` can be used under an appropriate privilege policy. Do not grant excessive privileges indiscriminately just to run monitoring queries.

## 24. Observing Heavyweight Locks with pg_locks

~~~sql
SELECT
    l.pid,
    l.locktype,
    l.mode,
    l.granted,
    l.waitstart,
    CASE
        WHEN l.locktype = 'relation'
        THEN l.relation::regclass::text
        ELSE NULL
    END AS relation_name,
    l.transactionid,
    l.virtualxid
FROM pg_locks AS l
WHERE l.database = (
    SELECT oid FROM pg_database
    WHERE datname = current_database()
)
   OR l.database IS NULL
ORDER BY l.pid NULLS LAST, l.locktype, l.mode;
~~~

Key columns:

| Column | Meaning |
| --- | --- |
| `pid` | Backend PID if the lock belongs to an active backend; may be null in some cases |
| `locktype` | Object type of the lock: `relation`, `transactionid`, `virtualxid`, `advisory`, etc. |
| `mode` | Specific mode, e.g. `AccessShareLock` or `RowExclusiveLock` |
| `granted` | `true` if granted; `false` if waiting |
| `waitstart` | Timestamp when waiting started, when available |
| `relation` | OID of the relation when `locktype` applies |
| `transactionid` | Associated transaction ID when `locktype` applies |

Mode names in `pg_locks` use CamelCase forms such as `AccessShareLock`, unlike the spaced syntax in `LOCK TABLE ... IN ACCESS SHARE MODE`.

### 24.1. Do Not Treat pg_locks as a List of All Row Locks

`pg_locks` displays **locks exposed by the lock manager and corresponding instrumentation**, not a table listing every tuple locked by `FOR UPDATE`.

To investigate row-modification waits, combine:

1. `pg_stat_activity.wait_event_type = 'Lock'`.
2. `pg_blocking_pids(pid)`.
3. Relevant `transactionid`/`tuple` rows in `pg_locks`.
4. Query details, transaction age, and behavior of both sessions.

### 24.2. Resolving relation OIDs to Names

`l.relation::regclass` works when the relation belongs to the current database. For locks involving other databases, do not assume the OID resolves cleanly in the querying session's database.

## 25. Finding Blocked Sessions and True Blockers

The `pg_blocking_pids(pid)` function returns the list of PIDs **blocking** the specified session according to PostgreSQL's lock mechanism.

~~~sql
SELECT
    a.pid AS waiting_pid,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    now() - a.query_start AS query_age,
    now() - a.xact_start AS transaction_age,
    pg_blocking_pids(a.pid) AS blocking_pids,
    LEFT(a.query, 200) AS waiting_query
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
  AND cardinality(pg_blocking_pids(a.pid)) > 0
ORDER BY a.query_start NULLS LAST;
~~~

When Session B is blocked by A's uncommitted `UPDATE`, `blocking_pids` will contain A's PID.

### 25.1. Joining to See the Blocker's Query

~~~sql
SELECT
    waiter.pid AS waiting_pid,
    waiter.state AS waiting_state,
    waiter.wait_event_type AS waiting_type,
    waiter.wait_event AS waiting_event,
    LEFT(waiter.query, 160) AS waiting_query,
    b.blocker_pid,
    blocker.state AS blocker_state,
    now() - blocker.xact_start AS blocker_xact_age,
    LEFT(blocker.query, 160) AS blocker_last_query
FROM pg_stat_activity AS waiter
CROSS JOIN LATERAL
    unnest(pg_blocking_pids(waiter.pid))
    AS b(blocker_pid)
LEFT JOIN pg_stat_activity AS blocker
    ON blocker.pid = b.blocker_pid
WHERE waiter.datname = current_database()
ORDER BY waiter.pid, b.blocker_pid;
~~~

Notes:

- The blocker may be `idle in transaction`, meaning it is no longer running SQL but still holds locks.
- The `query` shown for an idle blocker is usually its **most recent SQL statement**, not necessarily the statement that acquired every lock still held.
- Certain special blockers (such as prepared transactions) have no active backend PID; interpret observations in context.
- `pg_blocking_pids()` focuses on blocker relationships within the lock manager, **not on explaining every I/O or LWLock wait**.

### 25.2. Do Not Assume the Blocker Is the Sole Culprit

A long-running transaction holding locks may be the immediate cause, while the root cause could be application code opening a transaction before making an HTTP call, a poorly timed migration, or a long-running query that never commits.

Remediation usually belongs to **transaction boundaries and workload design**, not merely "killing whichever PID shows up."

## 26. Step-by-Step Wait Chain Analysis

Suppose:

~~~text
Session A: BEGIN; UPDATE account_id=1;  (not COMMITted)
Session B: BEGIN; UPDATE account_id=1;  (waiting)
Session C: queries pg_stat_activity / pg_locks
~~~

When observing, you may see:

1. Session B has `state = 'active'`, `wait_event_type = 'Lock'`, and a wait event matching transaction waiting.
2. `pg_blocking_pids(B_PID)` returns A's PID.
3. Session A has `state = 'idle in transaction'` if waiting for the user to enter another command.
4. `pg_locks` shows compatible relation lock entries for both A and B, yet B still waits on a **transactionid/tuple-level conflict**.
5. When A runs `ROLLBACK`/`COMMIT`, B wakes up to continue/re-evaluate.

### 26.1. Why Inspecting Only Table Locks Misleads Diagnosis

If you only check:

~~~sql
SELECT *
FROM pg_locks
WHERE locktype = 'relation'
  AND relation = 'lock_lab.accounts'::regclass;
~~~

you may see both A and B holding `RowExclusiveLock` with `granted = true`. Because this table-level mode is compatible with itself, you might wonder why B is waiting.

**The reason is a row/transaction lock wait**, not a conflict between the two table-level `RowExclusiveLock` entries.

### 26.2. Inspecting Waiting Locks

~~~sql
SELECT
    pid,
    locktype,
    mode,
    granted,
    transactionid,
    relation::regclass AS relation_name
FROM pg_locks
WHERE NOT granted
ORDER BY pid, locktype, mode;
~~~

This query targets ungranted lock requests, though it does not describe waits outside `Lock`. Do not expect every blocking wait to have a `relation_name`: a `transactionid` locktype may not reference a table OID in that entry itself.

## 27. Deadlocks: A Wait Cycle, Not Just a Long Wait

Two transactions modify two accounts in **opposite order**:

~~~text
Session A                         Session B
BEGIN                             BEGIN
UPDATE account 1                  UPDATE account 2
      |                                 |
UPDATE account 2  (waits for B)   UPDATE account 1 (waits for A)
      |                                 |
      +----------- wait cycle ----------+
~~~

### 27.1. Reproducing in the Lab

Session A:

~~~sql
BEGIN;
UPDATE lock_lab.accounts
SET note = 'A1'
WHERE account_id = 1;
~~~

Session B:

~~~sql
BEGIN;
UPDATE lock_lab.accounts
SET note = 'B2'
WHERE account_id = 2;
~~~

Session A continues:

~~~sql
UPDATE lock_lab.accounts
SET note = 'A2'
WHERE account_id = 2;
-- Waits for B.
~~~

Session B continues:

~~~sql
UPDATE lock_lab.accounts
SET note = 'B1'
WHERE account_id = 1;
-- Creates a wait cycle.
~~~

PostgreSQL has deadlock detection and typically aborts one transaction to break the cycle. The error usually has SQLSTATE **`40P01`**.

End the exercise with `ROLLBACK` in both sessions as appropriate.

### 27.2. Avoiding Deadlocks with Consistent Lock Ordering

When a business flow must modify multiple accounts, use a **consistent lock acquisition order**, such as ascending `account_id`, to avoid cases where A locks 1→2 while B locks 2→1.

You should also:

- Keep transactions short.
- Avoid updating multiple tables in different orders across code paths.
- Implement bounded **full-transaction** retries for `40P01` when business logic allows.
- Avoid network calls and user prompts while holding locks.

### 27.3. The Deadlock Detector Does Not Replace Lock Timeouts

PostgreSQL automatically detects **wait cycles**, but a session waiting a very long time for another transaction **without a cycle** will keep waiting. That is why `lock_timeout` and operational monitoring remain important.

## 28. Timeouts: Controlling Lock Waits

Three common timeouts:

| Parameter | Purpose |
| --- | --- |
| `lock_timeout` | Limits how long to wait for a lock |
| `statement_timeout` | Limits total statement execution time |
| `idle_in_transaction_session_timeout` | Terminates sessions idle too long while in a transaction |

### 28.1. SET LOCAL lock_timeout

~~~sql
BEGIN;

SET LOCAL lock_timeout = '1500ms';

UPDATE lock_lab.accounts
SET note = 'timeout_demo'
WHERE account_id = 1;

ROLLBACK;
~~~

If the statement has to wait for a lock longer than 1.5 seconds, PostgreSQL raises a timeout error. `SET LOCAL` applies only to the current transaction.

Note: after a timeout error inside a transaction, the transaction becomes **aborted**; you must roll back or use a savepoint before running further statements.

### 28.2. statement_timeout vs. lock_timeout

`statement_timeout` measures statement execution time and includes time spent waiting for locks. `lock_timeout` targets **lock wait time** specifically. Setting `lock_timeout` longer than `statement_timeout` usually adds no benefit because the statement will be canceled earlier.

### 28.3. What Is deadlock_timeout?

`deadlock_timeout` controls how long PostgreSQL waits on a lock before running deadlock detection, and also affects lock-wait logging when configured. It is not "the maximum time a lock is allowed to be held."

Do not change this setting arbitrarily in production; investigate lock contention using actual wait metrics and monitoring.

## 29. Idle in Transaction: Blockers Not Running SQL Still Hold Locks

Session A:

~~~sql
BEGIN;
UPDATE lock_lab.accounts
SET note = 'still locked'
WHERE account_id = 1;

-- Now the user steps away without COMMIT/ROLLBACK.
~~~

The session becomes `idle in transaction`. It is **not active**, yet its transaction locks are still held.

Session B trying to modify account 1 will wait. If A holds a snapshot or transaction horizon open for a long time, the impact can also extend to VACUUM and table bloat.

### 29.1. Finding Long-Running Transactions

~~~sql
SELECT
    pid,
    application_name,
    state,
    now() - xact_start AS xact_age,
    wait_event_type,
    wait_event,
    LEFT(query, 160) AS last_query
FROM pg_stat_activity
WHERE datname = current_database()
  AND state IN (
      'idle in transaction',
      'idle in transaction (aborted)'
  )
ORDER BY xact_start NULLS LAST;
~~~

### 29.2. Why Fix This in the Application?

Common causes include:

- Code opens a transaction and forgets to commit/rollback on error paths.
- Connection pools return connections that were not cleaned up properly.
- SQL GUI tools left in manual commit mode.
- Application makes HTTP calls or does slow work inside a transaction.
- An interactive script pauses after an `UPDATE` awaiting user input.

The lasting fix is **clear transaction boundaries**, cleanup on all error paths, and minimizing connection and lock hold times. Timeouts are only an additional safeguard.

## 30. Should You Terminate a Blocking Backend?

PostgreSQL provides administrative functions:

~~~sql
SELECT pg_cancel_backend(<pid>);
SELECT pg_terminate_backend(<pid>);
~~~

This is **illustrative syntax**; `<pid>` must be replaced with an actual PID and requires appropriate privileges.

- `pg_cancel_backend` requests canceling the target backend's current query; it does not necessarily end the session or clear an idle transaction.
- `pg_terminate_backend` requests terminating the backend/session, typically rolling back uncommitted transactions and closing the connection.

### 30.1. Do Not Kill Simply Because You See a Wait

Before intervening, determine:

1. Is the PID waiting or **holding the lock**?
2. Does the blocker's transaction contain important uncommitted work?
3. Is the blocker a business request, migration, batch job, or maintenance task?
4. Can the application be asked to commit/rollback safely?
5. Will terminating cause a retry storm or connection failures?

Do not blindly terminate PostgreSQL processes or backends whose role is unknown. In production systems, terminating sessions must follow operational runbooks and approved permissions.

## 31. Common Misconceptions

### Misconception 1: PostgreSQL does not use locks because it has MVCC

False. MVCC handles snapshot visibility, while DML/DDL still use locks to coordinate concurrency and schema changes.

### Misconception 2: UPDATE locks the entire table so all UPDATEs must run serially

False. `UPDATE` typically holds table-level `ROW EXCLUSIVE`, which is compatible with itself; transactions modifying different rows can run concurrently.

### Misconception 3: ROW EXCLUSIVE is a row-level lock

False. `ROW EXCLUSIVE` is one of the **eight table-level lock modes**. `FOR NO KEY UPDATE` or `FOR UPDATE` are **row-level modes**.

### Misconception 4: SELECT is never blocked

False. Plain `SELECT` is usually not blocked by another `UPDATE`'s row lock, but an `ACCESS EXCLUSIVE` relation lock can block even `SELECT`.

### Misconception 5: SELECT reads uncommitted data because it isn't blocked

False. MVCC enforces visibility by isolation level; reading an older committed version is **not a dirty read** of an uncommitted version.

### Misconception 6: pg_locks lists every row locked with FOR UPDATE

False. Granted tuple locks do not all appear like relation locks. Row contention often shows up as waiting on `transactionid`.

### Misconception 7: wait_event_type = Lock always means a table lock

False. Heavyweight lock waits can involve `relation`, `transactionid`, `tuple`, `object`, `advisory`, and other lock types.

### Misconception 8: LWLock is a LOCK TABLE mode

False. LWLocks protect internal structures and are not chosen via SQL `LOCK TABLE`.

### Misconception 9: BufferPin is the same as LWLock

False. PostgreSQL reports `BufferPin` as a separate wait type; you need to distinguish its cause and tuning approach.

### Misconception 10: FOR SHARE and ROW SHARE are the same

False. `FOR SHARE` is a **row lock** mode; `ROW SHARE` is a **table lock** mode.

### Misconception 11: FOR KEY SHARE blocks all UPDATEs

False. `FOR KEY SHARE` is compatible with `FOR NO KEY UPDATE` on the same row, though it conflicts with `FOR UPDATE`.

### Misconception 12: SKIP LOCKED gives complete reporting results

False. It skips locked rows, which suits certain queue workers but not reports requiring all rows.

### Misconception 13: Any waiting session is a deadlock

False. A deadlock is a **wait cycle**, not a one-way wait between two transactions.

### Misconception 14: Adding a timeout fixes the root cause

Timeouts bound wait time; they do not replace short transactions, proper lock ordering, and sound application design.

### Misconception 15: CREATE INDEX CONCURRENTLY uses no locks

False. It still coordinates with transactions and has waiting phases; it merely reduces certain write-blocking patterns compared to regular `CREATE INDEX`.

### Misconception 16: Advisory locks automatically protect every row with the same ID

False. Advisory locks coordinate code paths that **agree by convention to use the same key**; they do not automatically put row locks on an account.

## 32. Practice Exercises

The following exercises use the `lock_lab` schema. For two-session exercises, pay attention to which transaction remains open and end with `ROLLBACK`. Never run `LOCK TABLE ... ACCESS EXCLUSIVE` in production to test.

### Exercise 1. Lock Classification

Given three scenarios: (a) `ALTER TABLE` requiring a strong lock; (b) two `UPDATE`s on the same account; (c) two backends contending on buffer metadata. Which primary lock category does each involve?

### Exercise 2. ACCESS SHARE

Which table lock mode does a plain `SELECT` acquire? Which table-level mode does it conflict with in the matrix?

### Exercise 3. ROW EXCLUSIVE

Why can A and B concurrently `UPDATE` two different accounts even though both transactions hold table-level `ROW EXCLUSIVE`?

### Exercise 4. ROW SHARE vs. FOR SHARE

Explain the difference between the lock names `ROW SHARE` and `FOR SHARE`.

### Exercise 5. Two-Session Read-Write

A executes `BEGIN` and `UPDATE`s account 1's balance without committing. B runs a plain `SELECT` under `READ COMMITTED`; does B see the new or old value?

### Exercise 6. Two UPDATEs on the Same Row

A holds an uncommitted `UPDATE` on account 1. B `UPDATE`s account 1. Describe what happens and how to release the lock.

### Exercise 7. ACCESS EXCLUSIVE

A runs `BEGIN; LOCK TABLE lock_lab.accounts IN ACCESS EXCLUSIVE MODE;`. B runs a `SELECT` on that table. Why must B wait?

### Exercise 8. SHARE Table Lock

Why can `LOCK TABLE ... IN SHARE MODE` allow `SELECT` while blocking `UPDATE`?

### Exercise 9. Four Row Lock Modes

List the four row-level lock modes. Does `FOR KEY SHARE` conflict with `FOR NO KEY UPDATE`? Does it conflict with `FOR UPDATE`?

### Exercise 10. FK

Why does PostgreSQL need to protect the parent row when inserting a child row referencing an FK? What differs if another transaction only updates a non-key `note` column?

### Exercise 11. pg_locks

Why is a query filtering only `locktype='tuple'` insufficient to detect every transaction waiting on a row lock?

### Exercise 12. Finding Blockers

Write a query returning `pid`, `wait_event_type`, `wait_event`, and `pg_blocking_pids(pid)` for backends that currently have blockers.

### Exercise 13. LWLock

How should `wait_event_type = 'LWLock'` be interpreted? Should you immediately look for a specific row locked by `FOR UPDATE`?

### Exercise 14. BufferPin

Why should `BufferPin` not be equated with `LWLock` or row-level locks?

### Exercise 15. Deadlock

A updates account 1 then waits on account 2; B updates account 2 then waits on account 1. Is this a normal wait or a deadlock? What is the typical SQLSTATE?

### Exercise 16. NOWAIT

What does `FOR UPDATE NOWAIT` do when a row already has a conflicting lock held by another transaction? If the statement errors inside a transaction, how must you handle it?

### Exercise 17. SKIP LOCKED

Why is `SKIP LOCKED` suitable for queue workers, yet unsuitable for accurately counting all orders?

### Exercise 18. VACUUM

Compare the locking impact of plain `VACUUM` versus `VACUUM FULL`.

### Exercise 19. Advisory Lock

Write an example using `pg_try_advisory_xact_lock` and explain why it does not automatically lock the account row with the same ID.

### Exercise 20. Serializable Predicate Lock

Does `SIReadLock` aim to block writers immediately like `FOR UPDATE`? Which error can occur when SSI detects a non-serializable history?

### Exercise 21. Idle in Transaction

A session has been `state='idle in transaction'` for 20 minutes. Can it block other `UPDATE`s? Write a query to find sessions in this state.

### Exercise 22. Lock Timeout

Write `SET LOCAL lock_timeout = '2s'` inside a transaction. How does this timeout differ from `statement_timeout`?

### Exercise 23. Distinguishing relation and transactionid Waits

In `pg_locks`, both A and B hold `RowExclusiveLock` on the table with `granted=true`, yet B is still waiting. Give a reason.

### Exercise 24. Designing to Avoid Deadlocks

An application transfers money between two accounts with high concurrency. Propose a lock-ordering rule and a strategy for handling deadlocks if they still occur.

## 33. Suggested Solutions

### Solution 1. Three Layers

(a) Primarily object/relation locking; (b) row-locking / transaction coordination mechanism, along with DML table locks; (c) internal synchronization such as LWLock/spinlock/buffer control.

### Solution 2. SELECT

`ACCESS SHARE`, which conflicts with `ACCESS EXCLUSIVE` on the same relation.

### Solution 3. Two UPDATEs on Different Rows

`ROW EXCLUSIVE` is a **table-level mode** that is compatible with itself. If two transactions do not modify the same row and have no other conflicts, they can proceed concurrently.

### Solution 4. Two Confusing Names

`ROW SHARE` is the table-level mode acquired by `SELECT FOR UPDATE/SHARE`; `FOR SHARE` is a row-level mode on individual selected rows.

### Solution 5. MVCC

Under `READ COMMITTED`, B sees the **previously committed value**, not A's uncommitted change. B is not blocked by A's row update during a plain `SELECT`.

### Solution 6. UPDATE on the Same Row

B waits for A to commit or roll back due to row/transaction conflict. In the lab, A runs `ROLLBACK` so B can continue; finally, B runs `ROLLBACK` to preserve the data.

### Solution 7. ACCESS EXCLUSIVE

`ACCESS EXCLUSIVE` conflicts with the `ACCESS SHARE` required by `SELECT`, so B waits for A's transaction to finish.

### Solution 8. SHARE

`SHARE` is compatible with `SELECT`'s `ACCESS SHARE`, but conflicts with `UPDATE`'s `ROW EXCLUSIVE`.

### Solution 9. Row-Level Modes

`FOR KEY SHARE`, `FOR SHARE`, `FOR NO KEY UPDATE`, `FOR UPDATE`. `FOR KEY SHARE` is compatible with `FOR NO KEY UPDATE` but conflicts with `FOR UPDATE`.

### Solution 10. FK

The FK must ensure the parent row remains valid when the child row is written. FK checking may use `FOR KEY SHARE` on the parent row; updating `note` without changing keys typically uses the compatible `FOR NO KEY UPDATE` mode.

### Solution 11. pg_locks

Row locks are not listed completely as granted tuple entries; a backend waiting on a row modified by another transaction may wait on `transactionid`.

### Solution 12. Finding Blocker PIDs

~~~sql
SELECT
    pid,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE datname = current_database()
  AND cardinality(pg_blocking_pids(pid)) > 0;
~~~

### Solution 13. LWLock

That indicates waiting on internal PostgreSQL structure synchronization. Investigate the specific wait event, load pattern, and resource; do not assume a row is locked by `FOR UPDATE`.

### Solution 14. BufferPin

`BufferPin` is a wait state related to buffer pinning; PostgreSQL reports it separately from `LWLock` and from logical tuple locks.

### Solution 15. Deadlock

The A→B→A cycle is a deadlock; PostgreSQL typically detects it and aborts one transaction with `40P01`.

### Solution 16. NOWAIT

`NOWAIT` raises an error if the row lock cannot be acquired immediately. After an error inside a transaction, roll back or roll back to a valid savepoint before continuing.

### Solution 17. SKIP LOCKED

It skips locked rows, letting other workers pick up available jobs. Because the returned data **omits locked rows**, it is unsuitable for reports that must count every order.

### Solution 18. VACUUM

Plain `VACUUM` typically uses `SHARE UPDATE EXCLUSIVE` and allows most normal operations to continue; `VACUUM FULL` requires strong `ACCESS EXCLUSIVE` locking and can block `SELECT`/DML.

### Solution 19. Advisory Try-Lock

~~~sql
BEGIN;
SELECT pg_try_advisory_xact_lock(42) AS acquired;
-- Only perform the protected work if acquired = true.
ROLLBACK;
~~~

Advisory locks operate by **application-level ID convention**, and do not automatically force SQL statements updating row ID 42 to acquire the same lock.

### Solution 20. SSI

`SIReadLock` tracks read-write dependencies rather than directly blocking writers like `FOR UPDATE`; PostgreSQL may abort a transaction with a `40001` serialization failure.

### Solution 21. Idle Session

~~~sql
SELECT
    pid, application_name, state,
    now() - xact_start AS xact_age
FROM pg_stat_activity
WHERE datname = current_database()
  AND state LIKE 'idle in transaction%'
ORDER BY xact_start NULLS LAST;
~~~

An idle session can still hold row/relation locks and block other transactions.

### Solution 22. Timeout

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';
SELECT * FROM lock_lab.accounts
WHERE account_id = 1 FOR UPDATE;
ROLLBACK;
~~~

`lock_timeout` limits **lock wait time**, whereas `statement_timeout` limits **statement execution time**.

### Solution 23. Transactionid Wait

Two table-level `RowExclusiveLock` entries are compatible. B can still wait on A's transaction ID because both are updating the **same row**; it is not a conflict between the two granted relation locks.

### Solution 24. Reducing Deadlocks

Acquire locks in a **consistent ID order**, keep transactions short, check affected row counts, and handle `40P01` by rolling back and performing bounded full-transaction retries with proper idempotency.

## 34. Quick Reference Table

| Goal | Syntax / indicator |
| --- | --- |
| Select a row with strong lock | `SELECT ... FOR UPDATE` |
| Lock row without changing primary key | `SELECT ... FOR NO KEY UPDATE` |
| Lock row in shared mode | `SELECT ... FOR SHARE` |
| Protect referenced key | `SELECT ... FOR KEY SHARE` |
| Do not wait for row lock | `FOR UPDATE NOWAIT` |
| Skip locked rows | `FOR UPDATE SKIP LOCKED` |
| Acquire explicit table lock | `LOCK TABLE ... IN SHARE MODE` |
| Strongest table lock | `LOCK TABLE ... IN ACCESS EXCLUSIVE MODE` |
| Inspect locks tracked by manager | `SELECT ... FROM pg_locks` |
| Find wait type | `pg_stat_activity.wait_event_type` |
| Find specific event | `pg_stat_activity.wait_event` |
| Find blocking PIDs | `pg_blocking_pids(pid)` |
| Check transaction age | `now() - pg_stat_activity.xact_start` |
| Limit lock wait duration | `SET LOCAL lock_timeout = '2s'` |
| Limit statement duration | `statement_timeout` |
| Kill long idle transactions | `idle_in_transaction_session_timeout` |
| Transaction-scoped advisory lock | `pg_advisory_xact_lock(key)` |
| Advisory try-lock | `pg_try_advisory_xact_lock(key)` |
| Deadlock detected | SQLSTATE `40P01` |
| Serialization failure | SQLSTATE `40001` |
| Internal lightweight wait | `wait_event_type = 'LWLock'` |
| Buffer pin wait | `wait_event_type = 'BufferPin'` |

## 35. Checklist When Facing a Blocked Query

1. **Identify PID, query, and timestamps:** use `pg_stat_activity`.
2. **Classify the wait:** `Lock`, `LWLock`, `BufferPin`, `IO`, or something else?
3. **If it is a `Lock`:** use `pg_blocking_pids(pid)` to find blockers; avoid manually joining `pg_locks` under overly simplistic assumptions.
4. **Check mode and target:** relation `ACCESS EXCLUSIVE` or `transactionid` row conflict?
5. **Check if the blocker is `idle in transaction`:** is an old transaction left uncommitted?
6. **Check query/transaction age:** distinguish migrations, APIs, batch jobs, maintenance, and online queries.
7. **Verify table-level vs. row-level conflict:** two granted `ROW EXCLUSIVE` locks do not prove there is no row contention.
8. **Assess data impact:** before canceling/terminating, understand whether the transaction will roll back or the job will retry.
9. **Fix the long-term cause:** short transactions, lock ordering, DDL planning, proper indexes, and deliberate timeouts.
10. **If it is `LWLock`/`BufferPin`:** analyze internal bottlenecks, system load, and specific wait events; do not blindly apply "kill the row-lock blocker."

## 36. Summary

In PostgreSQL, **object locks**, **row locks**, and **internal locks** answer three different questions:

- **Object / relation-level locks:** is a transaction allowed to operate on a table/object while another transaction performs DDL, maintenance, or access? They have **eight table-level modes** and a conflict matrix. `ROW EXCLUSIVE` is a **table lock mode**, not a single-row lock.
- **Row / row-level locks:** can two transactions concurrently lock/modify the **same row** or must one wait? They have **four modes**—`FOR KEY SHARE`, `FOR SHARE`, `FOR NO KEY UPDATE`, `FOR UPDATE`—working alongside MVCC and transaction status.
- **Internal locks:** how does PostgreSQL protect shared buffers and memory structures when multiple backends run concurrently? That is the job of **LWLocks, spinlocks, buffer pins**, and related mechanisms—not something applications control via `LOCK TABLE`.

The operational key is **classifying the wait type correctly before optimizing**. `pg_locks` is invaluable for heavyweight locks but does not list all row locks; `pg_stat_activity` shows state and wait type; `pg_blocking_pids()` traces blocker chains during lock-manager contention. A plain `SELECT` can read committed MVCC versions while another `UPDATE` waits on a row lock, yet `ACCESS EXCLUSIVE` can still block both.

When encountering a "locked" SQL query, ask in order: **"What resource type is it waiting on? Is it waiting on a transaction/row or an object? Is it internal contention? Who holds the resource, and for how long?"** Answering those questions accurately fixes the **real root cause** instead of blindly raising timeouts or killing sessions uncontrollably.
