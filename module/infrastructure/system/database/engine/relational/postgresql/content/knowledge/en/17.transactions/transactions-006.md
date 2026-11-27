# Read Committed, Repeatable Read, and Serializable Isolation Levels in PostgreSQL

An ordering application may read inventory quantity, check whether stock is sufficient, and decrement it; a shift-scheduling system may check that at least one person remains on duty before letting someone go off duty; a report may compute total revenue multiple times while other transactions are writing data. When sessions execute concurrently, **the exact same SQL** can observe different data or produce different outcomes depending on the **transaction isolation level**.

PostgreSQL has three isolation levels with notably distinct execution behaviors:

- **Read Committed**: the default; each read statement sees a snapshot of data committed before that statement began.
- **Repeatable Read**: a transaction keeps a stable snapshot throughout its execution; PostgreSQL uses *snapshot isolation*, preventing both nonrepeatable reads and phantom reads, though **write skew** and non-serializable anomalies can still occur.
- **Serializable**: the strongest level, allowing transactions to commit only if the outcome is equivalent to some serial execution order; PostgreSQL uses **Serializable Snapshot Isolation (SSI)** to detect dangerous read–write dependencies and may abort a transaction with **SQLSTATE `40001`**, requiring the application to retry the **entire transaction**.

No isolation level magically provides "always reading the absolute latest data with zero waiting or errors." An isolation level is a **contract defining what is allowed to be observed and what happens under contention**, not merely a knob to tune speed.

This lesson covers the theory, runnable examples using **two independent `psql`/SQL client windows**, concurrency anomalies, mitigation techniques, Java/JDBC examples, and exercises. All content is framed specifically for PostgreSQL, because other database systems may define identically named levels with different actual behaviors.

## 1. Transactions and Isolation

A transaction groups one or more SQL statements into a single unit confirmed by `COMMIT` or discarded by `ROLLBACK`:

~~~sql
BEGIN;

UPDATE some_accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE some_accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
~~~

This example uses a hypothetical `some_accounts` table. The goal is for both updates to belong to one transaction. If an error occurs and the transaction rolls back, transactional changes are undone.

Within ACID:

- **Atomicity:** a transaction's changes are confirmed or undone according to transaction rules.
- **Consistency:** properly expressed/checked constraints and invariants must hold; the database cannot infer undocumented business rules on its own.
- **Isolation:** concurrent transactions must not observe or interact with each other in ways forbidden by the chosen isolation level.
- **Durability:** committed data has persistence guarantees according to configuration and storage setup.

In this lesson, the central question is not "did it commit?" but rather **what is a running transaction A allowed to see when transaction B writes and commits?** and **can both A and B commit together in a way that violates business invariants?**

### 1.1. Two Transactions Operating on Data Concurrently

~~~text
Time →

Session A                           Session B
---------                           ---------
BEGIN
SELECT price = 100
                                    BEGIN
                                    UPDATE price = 120
                                    COMMIT
SELECT price = ?
COMMIT
~~~

If A uses **Read Committed**, the second `SELECT` can see `120`. If A uses **Repeatable Read**, A continues seeing `100` from its established snapshot. **Serializable** also keeps a stable snapshot while adding serializability checks for dangerous read–write dependencies.

### 1.2. Isolation Does Not Mean Locks Only

PostgreSQL uses **MVCC — Multi-Version Concurrency Control**. When a row is updated, the system maintains multiple row versions managed via transaction metadata; a snapshot determines which version is visible. Consequently, normal `SELECT` queries read committed data without waiting on every writer updating the same row.

MVCC does not mean "locks never exist": `UPDATE`, `DELETE`, `SELECT ... FOR UPDATE`, DDL, and many other operations still acquire appropriate locks. Serializable additionally tracks read–write dependencies using **predicate locks (`SIReadLock`)** to detect serialization anomalies; these SSI tracking locks **do not block writers like ordinary row locks**.

## 2. Four Anomalies to Recognize

### 2.1. Dirty Read — Reading Uncommitted Data

Session A changes a price from 100 to 120 but **has not committed**. Session B sees 120 before A commits; then A rolls back. B acted on a value that was never confirmed.

~~~text
A: UPDATE price=120      (uncommitted)
B: SELECT price -> 120   (dirty read)
A: ROLLBACK              (price remains 100)
~~~

PostgreSQL **does not allow dirty reads** in its implemented isolation levels, even when `READ UNCOMMITTED` is requested; that level is treated like Read Committed.

### 2.2. Nonrepeatable Read — Re-Reading the Same Row Returns a Different Value

~~~text
A: SELECT price -> 100
B: UPDATE price=120; COMMIT
A: SELECT price -> 120
~~~

One transaction reads the same row twice and receives two different values because another transaction committed in between. **Read Committed allows** this phenomenon; **Repeatable Read and Serializable prevent** it in PostgreSQL.

### 2.3. Phantom Read — The Set of Matching Rows Changes

~~~text
A: SELECT COUNT(*) WHERE status='PAID' -> 1
B: INSERT a PAID order; COMMIT
A: SELECT COUNT(*) WHERE status='PAID' -> 2
~~~

On the second read, a new row matching the `WHERE` clause appears—called a **phantom**. Read Committed allows it. PostgreSQL Repeatable Read **does not allow phantom reads**, even though the SQL standard only requires Repeatable Read at minimum to prevent dirty/nonrepeatable reads and permits phantoms.

### 2.4. Serialization Anomaly — Outcome Not Equivalent to Any Serial Execution

Suppose at least one doctor must always remain on duty:

~~~text
Initially: Doctor An = on duty, Bình = on duty.

Transaction A:
    Count doctors on duty: 2.
    Set An off duty.

Transaction B:
    Count doctors on duty: 2.
    Set Bình off duty.
~~~

If both rely on the initial snapshot and update **two different rows**, both can commit under **Repeatable Read**. Result: **0 doctors on duty**, violating the rule. This is **write skew**, a form of serialization anomaly.

If executed **serially according to the logic**, the second transaction would see only 1 doctor remaining and refuse to let the last doctor leave. Serializable guarantees that **two such transactions cannot both commit into a non-serializable outcome**.

## 3. PostgreSQL Behavior Matrix

| Phenomenon | Read Committed | Repeatable Read (PostgreSQL) | Serializable |
| --- | --- | --- | --- |
| Dirty read | No | No | No |
| Nonrepeatable read | Possible | No | No |
| Phantom read | Possible | **No** | No |
| Serialization anomaly / write skew | Possible | **Possible** | No, among transactions following Serializable that successfully commit |
| Primary snapshot | Per statement | Stable from first statement establishing snapshot | Stable, plus SSI checks |
| Can require retry due to `40001`? | Not typical behavior of this level | **Yes**, when competing to update a row modified after snapshot | **Yes**, including read–write dependency conflicts |

**Two PostgreSQL-specific facts to remember:**

1. `READ UNCOMMITTED` is accepted syntactically but **behaves like Read Committed**, never allowing dirty reads.
2. PostgreSQL `REPEATABLE READ` uses **snapshot isolation** and **prevents phantoms**, stronger than the SQL standard minimum; however, it is **not equivalent to Serializable** because write skew remains possible.

"Possible" means the phenomenon is **permitted to occur**, not that every pair of concurrent transactions will always hit it. Actual results depend on statement ordering, snapshot timing, and data conditions.

### 3.1. Comparing by Business Need

| Need | Starting Guidance |
| --- | --- |
| Standard CRUD where each SQL reads a fresh snapshot | Read Committed |
| Multi-`SELECT` report needing one consistent snapshot | Repeatable Read, usually `READ ONLY` |
| Multi-row / predicate-based invariants with concurrent writers | Serializable **plus full-transaction retry**, or properly designed locking/constraints |
| Decrementing stock on **one specific row** with sufficient-quantity check | Often handled with a single atomic `UPDATE ... WHERE quantity >= ...` under Read Committed |
| Long read-only report willing to wait initially for a safe snapshot | `SERIALIZABLE READ ONLY DEFERRABLE` when appropriate |

Never choose Serializable purely on the slogan "safest" without building a **serialization-failure retry path**; likewise, never assume Read Committed is safe for everything simply because it is the default.

## 4. Setting and Checking Isolation Levels

### 4.1. Inspecting Current Configuration

~~~sql
SHOW default_transaction_isolation;
SHOW transaction_isolation;

SELECT
    current_setting('default_transaction_isolation')
        AS session_default_isolation,
    current_setting('transaction_isolation')
        AS current_isolation;
~~~

In an unmodified PostgreSQL setup, the session default is typically `read committed`.

### 4.2. Setting for a Single Transaction

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT current_setting('transaction_isolation');

COMMIT;
~~~

Similarly:

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
-- SELECT/UPDATE statements in this transaction...
COMMIT;
~~~

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
-- SELECT/UPDATE statements in this transaction...
COMMIT;
~~~

Or specify it right when starting the transaction:

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SELECT current_setting('transaction_isolation');
COMMIT;
~~~

### 4.3. SET TRANSACTION Must Come Early

PostgreSQL forbids changing the isolation level **after the first query or data-modifying statement** in a transaction, such as `SELECT`, `INSERT`, `UPDATE`, or `DELETE`. Do:

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
SELECT ...;
-- ...
COMMIT;
~~~

Do not write:

~~~sql
-- WARNING: wrong order, will error.
-- BEGIN;
-- SELECT ...;
-- SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
~~~

`SET TRANSACTION` applies **only to the current transaction**, not subsequent ones.

### 4.4. Setting Session Defaults for New Transactions

~~~sql
SET SESSION CHARACTERISTICS AS TRANSACTION
    ISOLATION LEVEL REPEATABLE READ;

SHOW default_transaction_isolation;

BEGIN;
SELECT current_setting('transaction_isolation');
COMMIT;

-- Restore default for the lab/session:
SET SESSION CHARACTERISTICS AS TRANSACTION
    ISOLATION LEVEL READ COMMITTED;
~~~

With connection pools, **session-level settings can persist across reused connections** unless the pool/driver resets them. Applications should manage and restore connection state strictly, preferably setting isolation explicitly for transactions with special requirements.

### 4.5. READ ONLY and READ WRITE

Isolation level and read/write access mode are **two orthogonal dimensions**:

~~~sql
BEGIN TRANSACTION
    ISOLATION LEVEL REPEATABLE READ
    READ ONLY;

SELECT COUNT(*) FROM pg_catalog.pg_class;

COMMIT;
~~~

`READ ONLY` is not a "fourth isolation level": it restricts write operations permitted inside the transaction. PostgreSQL's read-only mode has nuances/exceptions such as temporary tables; never treat it as an authorization substitute for roles/`GRANT`/RLS.

## 5. Preparing a Two-Session Lab Environment

To observe concurrency, open **two separate connections** to the same PostgreSQL database:

- **Session A:** first `psql` window or SQL editor.
- **Session B:** second window, using its own separate connection.
- Each session runs its own `BEGIN`/`COMMIT`/`ROLLBACK` per the scenario.
- Never paste both A's and B's commands into **a single connection**, as that does not create two concurrent transactions.

**Safety:** use a lab database only; never run deadlock/lock-wait demos on production. A SQL statement may block waiting on the other transaction; follow the exact sequence and close every transaction before resetting. When a transaction errors, run `ROLLBACK` to return the connection to a usable state.

### 5.1. Lab Schema and Tables

~~~sql
CREATE SCHEMA iso_lab_216;

CREATE TABLE iso_lab_216.price_tags (
    item_id INTEGER PRIMARY KEY,
    item_name TEXT NOT NULL,
    price NUMERIC(12, 2) NOT NULL
        CHECK (price >= 0)
);

CREATE TABLE iso_lab_216.orders (
    order_id BIGINT PRIMARY KEY,
    status TEXT NOT NULL
        CHECK (status IN ('PAID', 'NEW', 'CANCELLED')),
    amount NUMERIC(12, 2) NOT NULL
        CHECK (amount >= 0)
);

CREATE TABLE iso_lab_216.counters (
    counter_id INTEGER PRIMARY KEY,
    value INTEGER NOT NULL
        CHECK (value >= 0)
);

CREATE TABLE iso_lab_216.stock (
    sku TEXT PRIMARY KEY,
    quantity INTEGER NOT NULL
        CHECK (quantity >= 0)
);

CREATE TABLE iso_lab_216.on_call (
    doctor_id INTEGER PRIMARY KEY,
    doctor_name TEXT NOT NULL,
    on_duty BOOLEAN NOT NULL
);

CREATE TABLE iso_lab_216.duty_guard (
    guard_id INTEGER PRIMARY KEY
);
~~~

### 5.2. Loading Initial Data

~~~sql
INSERT INTO iso_lab_216.price_tags
    (item_id, item_name, price)
VALUES
    (1, 'SQL Book', 100.00);

INSERT INTO iso_lab_216.orders
    (order_id, status, amount)
VALUES
    (101, 'PAID', 200.00),
    (102, 'NEW',  50.00);

INSERT INTO iso_lab_216.counters
    (counter_id, value)
VALUES (1, 10);

INSERT INTO iso_lab_216.stock
    (sku, quantity)
VALUES ('SKU-A', 5);

INSERT INTO iso_lab_216.on_call
    (doctor_id, doctor_name, on_duty)
VALUES
    (1, 'Doctor An', TRUE),
    (2, 'Doctor Bình', TRUE);

INSERT INTO iso_lab_216.duty_guard(guard_id)
VALUES (1);
~~~

Key initial values:

| Table | Key | Data |
| --- | --- | --- |
| `price_tags` | item_id=1 | price=100.00 |
| `orders` | 101 | PAID |
| `orders` | 102 | NEW |
| `counters` | counter_id=1 | value=10 |
| `stock` | SKU-A | quantity=5 |
| `on_call` | doctor_id=1,2 | Both on duty |
| `duty_guard` | guard_id=1 | Single row used as a shared lock point |

### 5.3. Resetting Between Exercises

After **both A and B have run `COMMIT` or `ROLLBACK`** and no open transactions remain, run in one session:

~~~sql
UPDATE iso_lab_216.price_tags
SET price = 100.00
WHERE item_id = 1;

DELETE FROM iso_lab_216.orders
WHERE order_id = 103;

UPDATE iso_lab_216.counters
SET value = 10
WHERE counter_id = 1;

UPDATE iso_lab_216.stock
SET quantity = 5
WHERE sku = 'SKU-A';

UPDATE iso_lab_216.on_call
SET on_duty = TRUE
WHERE doctor_id IN (1, 2);
~~~

**Do not reset while Session A or B still holds an open transaction**: doing so can block on locks, skew snapshots, or make concurrency outcomes confusing. Session A's `ROLLBACK` **does not undo** changes already committed by Session B; you must explicitly reset those committed changes.

## 6. Read Committed: Per-Statement Snapshots

Read Committed is PostgreSQL's default. For a normal `SELECT`:

1. The statement never sees uncommitted changes from other transactions.
2. The statement sees changes committed **before that statement started**.
3. Two `SELECT` statements inside the same transaction can receive different snapshots.
4. A transaction **still sees its own changes**, even before `COMMIT`.

### 6.1. Nonrepeatable Read Experiment

**Initial state:** `item_id=1` has `price=100`.

<escape>**Session A — open transaction and read #1:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT price
FROM iso_lab_216.price_tags
WHERE item_id = 1;
-- 100.00
~~~

Leave A uncommitted and switch to B.

<escape>**Session B — update price and commit:**</escape>

~~~sql
BEGIN;
UPDATE iso_lab_216.price_tags
SET price = 120.00
WHERE item_id = 1;
COMMIT;
~~~

<escape>**Back to Session A — read #2:**</escape>

~~~sql
SELECT price
FROM iso_lab_216.price_tags
WHERE item_id = 1;
-- 120.00

ROLLBACK;
~~~

Result:

| Moment | Price Seen by A |
| --- | ---: |
| Before B commits | 100 |
| After B commits | 120 |

This is a **nonrepeatable read permitted under Read Committed**. A remained inside the same transaction, yet its second `SELECT` received a **new snapshot**.

Reset `price=100` before the next experiment.

### 6.2. A Single SELECT's Snapshot Does Not Shift Mid-Query

Read Committed **does not** mean each row within one `SELECT` comes from an arbitrary instant. A standard `SELECT` uses the snapshot from **when that statement started**, so commits made by other sessions while `SELECT` is running do **not appear mid-scan** in that statement's output.

However, write commands such as `UPDATE`, `DELETE`, and `SELECT FOR UPDATE` follow waiting and target-row recheck rules under concurrent updates—an important nuance covered later.

### 6.3. Reading Your Own Changes

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

UPDATE iso_lab_216.price_tags
SET price = 140.00
WHERE item_id = 1;

SELECT price
FROM iso_lab_216.price_tags
WHERE item_id = 1;
-- 140.00: the same transaction sees its own changes.

ROLLBACK;
~~~

After rollback, assuming no other session changed the price, it returns to its prior value (100 in the lab). The "see your own changes" rule also holds in Repeatable Read and Serializable, without contradicting stable snapshots for changes from **other transactions**.

## 7. Read Committed: Phantom Reads

**Initial state:** `orders` has only one `PAID` order, `order_id=101`. Order `102` is `NEW`.

<escape>**Session A — count PAID orders first time:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT COUNT(*) AS paid_orders
FROM iso_lab_216.orders
WHERE status = 'PAID';
-- 1
~~~

<escape>**Session B — insert another PAID order:**</escape>

~~~sql
BEGIN;

INSERT INTO iso_lab_216.orders
    (order_id, status, amount)
VALUES
    (103, 'PAID', 300.00);

COMMIT;
~~~

<escape>**Session A — count second time:**</escape>

~~~sql
SELECT COUNT(*) AS paid_orders
FROM iso_lab_216.orders
WHERE status = 'PAID';
-- 2

ROLLBACK;
~~~

The count increases from 1 to 2 within the same Transaction A. This is a **phantom read**: **the set of rows matching the predicate** changed, not just a column value in an existing row.

**Remember to reset:** after A finishes, run `DELETE FROM iso_lab_216.orders WHERE order_id=103;` to restore initial data.

### 7.1. UPDATE or DELETE Can Also Shift the Matching Row Set

Phantoms do not only come from `INSERT`. If B updates a `NEW` order to `PAID` or updates a `PAID` order to `CANCELLED`, the count matching `WHERE status='PAID'` also changes. The core issue is that **predicate result sets are unstable across statements** under Read Committed.

## 8. PostgreSQL Has No Dirty Reads, Even Under READ UNCOMMITTED

The SQL standard defines `READ UNCOMMITTED`, but PostgreSQL maps it to **Read Committed**.

<escape>**Session A — change price without committing:**</escape>

~~~sql
BEGIN;
UPDATE iso_lab_216.price_tags
SET price = 999.00
WHERE item_id = 1;

-- Keep transaction open, DO NOT COMMIT.
~~~

<escape>**Session B — request READ UNCOMMITTED:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;

SELECT price
FROM iso_lab_216.price_tags
WHERE item_id = 1;
-- 100.00 in the reset initial dataset.

ROLLBACK;
~~~

<escape>**Session A — undo:**</escape>

~~~sql
ROLLBACK;
~~~

Session B **does not see `999`** because it is A's uncommitted data. Note that `SHOW transaction_isolation` displays the requested level name, yet actual read visibility for `READ UNCOMMITTED` in PostgreSQL remains identical to Read Committed.

### 8.1. Things Not Guaranteed to Roll Back Like Table Rows

Do not infer from this example that **every** effect rolls back. For example, PostgreSQL's sequence `nextval()` does not return allocated numbers when a transaction rolls back. Sequences follow special rules unlike ordinary MVCC rows; **gaps in IDs are not evidence of dirty reads**.

## 9. Repeatable Read: Transaction-Wide Stable Snapshots

In PostgreSQL, Repeatable Read sees rows committed before **the transaction's snapshot** and always sees changes made by the transaction itself. The snapshot is fixed when the transaction executes its **first non-transaction-control statement** (in practice, the first data query or modification), **not necessarily the instant `BEGIN` is typed**.

### 9.1. Direct Comparison with the Read Committed Experiment

**Initial state:** `price=100`. Run A first, then B as instructed.

<escape>**Session A — establish snapshot with SELECT:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT price
FROM iso_lab_216.price_tags
WHERE item_id = 1;
-- 100.00
~~~

<escape>**Session B — commit new price:**</escape>

~~~sql
BEGIN;
UPDATE iso_lab_216.price_tags
SET price = 120.00
WHERE item_id = 1;
COMMIT;
~~~

<escape>**Session A — read again inside the same transaction:**</escape>

~~~sql
SELECT price
FROM iso_lab_216.price_tags
WHERE item_id = 1;
-- Still 100.00

COMMIT;
~~~

<escape>**Session A — start a new transaction (or standalone SELECT):**</escape>

~~~sql
SELECT price
FROM iso_lab_216.price_tags
WHERE item_id = 1;
-- 120.00
~~~

Inside the Repeatable Read transaction, B's commit does not alter A's snapshot. **A is not reading uncommitted data; A is reading an older version consistent with its chosen snapshot.**

Reset `price=100` after both sessions finish.

### 9.2. BEGIN Is Not Immediately the Snapshot Timestamp

Compare these two schedules:

~~~text
Scenario 1:
A: BEGIN REPEATABLE READ
A: SELECT price -> 100   (snapshot established)
B: UPDATE price=120; COMMIT
A: SELECT price -> 100
~~~

~~~text
Scenario 2:
A: BEGIN REPEATABLE READ
B: UPDATE price=120; COMMIT
A: SELECT price -> 120   (first read establishes snapshot here)
A: SELECT price -> 120
~~~

**Do not treat `BEGIN` as an absolute snapshot timestamp** if no read/write statement has created the snapshot yet. To reason accurately about consistency, understand when a transaction first accesses data.

### 9.3. Do Not Confuse a Stable Snapshot with "Full-Table Locking"

Session B can still update and commit `price_tags` even while A is running Repeatable Read `SELECT`s. A does not need an exclusive lock on that row to keep seeing the older version. This is a key MVCC advantage: **readers and writers do not necessarily block each other** for standard operations.

## 10. Repeatable Read Also Prevents Phantoms in PostgreSQL

**Initial state:** one `PAID` order, no `order_id=103`.

<escape>**Session A — open RR and count:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS paid_orders
FROM iso_lab_216.orders
WHERE status = 'PAID';
-- 1
~~~

<escape>**Session B — insert a new order and commit:**</escape>

~~~sql
BEGIN;
INSERT INTO iso_lab_216.orders(order_id, status, amount)
VALUES (103, 'PAID', 300.00);
COMMIT;
~~~

<escape>**Session A — still in the same transaction:**</escape>

~~~sql
SELECT COUNT(*) AS paid_orders
FROM iso_lab_216.orders
WHERE status = 'PAID';
-- Still 1.

COMMIT;
~~~

<escape>**After A commits:**</escape>

~~~sql
SELECT COUNT(*) AS paid_orders
FROM iso_lab_216.orders
WHERE status = 'PAID';
-- 2 in a new transaction.
~~~

Under PostgreSQL Repeatable Read, both queries read the same snapshot, so **the phantom row added by B does not appear inside Transaction A**. That **does not mean Repeatable Read equals Serializable**: write skew can still occur because concurrent transactions can act on older snapshots while updating **disjoint rows**.

Reset by deleting `order_id=103` after both sessions finish.

## 11. Repeatable Read: Updates to Already-Modified Rows Still Error

A stable snapshot **does not mean a transaction may overwrite any row based on stale values**. PostgreSQL Repeatable Read rejects an update when another transaction already committed a modification to **the same row** after the current transaction's snapshot.

**Initial state:** `price=100`.

<escape>**Session A — RR, establish snapshot first:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT price
FROM iso_lab_216.price_tags
WHERE item_id = 1;
-- 100.00
~~~

<escape>**Session B — update that exact row and commit:**</escape>

~~~sql
BEGIN;
UPDATE iso_lab_216.price_tags
SET price = 120.00
WHERE item_id = 1;
COMMIT;
~~~

<escape>**Session A — attempt to update the modified row:**</escape>

~~~sql
UPDATE iso_lab_216.price_tags
SET price = 130.00
WHERE item_id = 1;

-- Expected error:
-- ERROR: could not serialize access due to concurrent update
-- SQLSTATE: 40001

ROLLBACK;
~~~

PostgreSQL will not blindly let A overwrite the version B just committed as if no conflict existed. After `40001`, A must **roll back and rerun the entire transaction** if business logic needs to continue.

### 11.1. Does Error 40001 Only Appear in Serializable?

**No.** Repeatable Read can also encounter serialization failures when competing to update or lock a row modified after its snapshot. The difference is that Serializable additionally detects **read–write dependencies across different rows** that cause write skew or serialization anomalies.

### 11.2. Read-Only Repeatable Read Does Not Need This Retry

If A only runs `SELECT`s on a Repeatable Read snapshot, B updating and committing that row will not fail A for "writing a modified row." Per PostgreSQL documentation, read-only transactions under Repeatable Read never experience this class of serialization conflict. Once `UPDATE` or `SELECT FOR UPDATE` is added, however, conflicts can happen.

## 12. Read Committed: UPDATE Waits and Re-Evaluates WHERE

A major behavioral difference between Read Committed and Repeatable Read lies in handling **concurrent updates on the same row**.

Under Read Committed, if an `UPDATE` targets a row whose write lock is held by another transaction, it **waits**. If that other transaction commits, PostgreSQL re-applies the command against the **latest committed version of the target row** and **re-evaluates the `WHERE` condition**.

### 12.1. Decrementing Stock with a Conditional UPDATE

**Initial state:** `SKU-A` has `quantity=5`. Two customers concurrently try to buy **4 items**; only one may succeed.

<escape>**Session A — begin and deduct 4:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

UPDATE iso_lab_216.stock
SET quantity = quantity - 4
WHERE sku = 'SKU-A'
  AND quantity >= 4
RETURNING sku, quantity;
-- 1 row, new quantity = 1.

-- Keep A uncommitted.
~~~

<escape>**Session B — send the same request:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

UPDATE iso_lab_216.stock
SET quantity = quantity - 4
WHERE sku = 'SKU-A'
  AND quantity >= 4
RETURNING sku, quantity;
-- Will WAIT for Session A to finish.
~~~

While B is waiting, switch back to A:

<escape>**Session A — commit:**</escape>

~~~sql
COMMIT;
~~~

Once B resumes, PostgreSQL sees the new version of `SKU-A` with `quantity=1`. The condition `quantity >= 4` **no longer holds**, so B updates **0 rows**.

<escape>**Session B — finish:**</escape>

~~~sql
COMMIT;
~~~

Final outcome:

- Only one request to deduct 4 succeeds.
- `quantity=1`, never going negative.
- The application must inspect **rowcount / `RETURNING`** to determine "stock reserved" vs. "insufficient stock."

**If A rolls back instead of committing**, B proceeds on the original row version and succeeds. Both outcomes correspond to different commit histories, not a bug.

### 12.2. Why Is This a Good Pattern?

The check and quantity decrement happen inside **one statement on the target row**, protected by write locks and predicate re-evaluation. Contrast this with:

~~~text
SELECT quantity
→ application checks
→ waits a moment
→ UPDATE quantity = old_value - 4
~~~

The gap between read and write in the second pattern lets decisions rest on stale data.

### 12.3. Do Not Overgeneralize That Every Invariant Is Protected

`UPDATE stock SET quantity=quantity-4 WHERE quantity>=4` protects a constraint **on one specific stock row**. Invariants such as "total stock across all warehouses is at least 10" or "at least one doctor remains on duty across multiple rows" are broader; they may require Serializable, coordinator locks, or different constraint/transaction designs.

## 13. Application-Tier Lost Updates: Reading and Writing Precomputed Constants

Not all lost-update bugs come from PostgreSQL running two `UPDATE`s simultaneously. A classic bug occurs when **an application reads a value into memory, computes the new value itself, and sends a literal constant to overwrite it**.

### 13.1. Two Workers Incrementing a Counter from 10

**Initial state:** `counters.value=10`.

<escape>**Session A — read:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT value
FROM iso_lab_216.counters
WHERE counter_id = 1;
-- 10
~~~

<escape>**Session B — also read before A commits:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT value
FROM iso_lab_216.counters
WHERE counter_id = 1;
-- 10
~~~

Both programs compute in memory: `newValue = 10 + 1 = 11`.

<escape>**Session A — write fixed value:**</escape>

~~~sql
UPDATE iso_lab_216.counters
SET value = 11
WHERE counter_id = 1;
COMMIT;
~~~

<escape>**Session B — write stale computed value:**</escape>

~~~sql
UPDATE iso_lab_216.counters
SET value = 11
WHERE counter_id = 1;
COMMIT;
~~~

Final value is **11** instead of **12**. Two logical increments occurred, yet the second increment was **lost** by overwriting with a stale constant.

### 13.2. Fixing with an Atomic Database Update

After resetting `value=10`, each worker sends:

~~~sql
UPDATE iso_lab_216.counters
SET value = value + 1
WHERE counter_id = 1
RETURNING value;
~~~

Under Read Committed, when both statements contend on the same row, one transaction waits for the other and operates on the updated version once the lock releases. When both commit, the **final value is 12**.

### 13.3. If Application Logic Must Use the Read Value

Options include:

- `SELECT ... FOR UPDATE` to lock the row before read–compute–write inside the transaction;
- Optimistic locking via a `version` column: `UPDATE ... SET value=?, version=version+1 WHERE id=? AND version=?`, checking rowcount and retrying on mismatch;
- Higher isolation with **retries on `40001`**;
- Rewriting as a single atomic SQL statement whenever possible.

**Never promote every transaction to Serializable by default** just to increment a counter cleanly; `UPDATE SET value=value+1` is simpler and more efficient.

## 14. Repeatable Read Still Allows Write Skew

This is the clearest experiment separating Repeatable Read from Serializable.

**Business rule:** at least **one** doctor must always be on duty. The `on_call` table starts with two rows:

| doctor_id | doctor_name | on_duty |
| ---: | --- | --- |
| 1 | Doctor An | TRUE |
| 2 | Doctor Bình | TRUE |

A doctor may go off duty **only if at least two doctors are currently on duty**. Two transactions concurrently try to take **two different doctors** off duty.

### 14.1. Two-Session Schedule Under Repeatable Read

<escape>**Session A — count on-duty doctors:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS on_duty_count
FROM iso_lab_216.on_call
WHERE on_duty;
-- 2
~~~

<escape>**Session B — also count before A writes/commits:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS on_duty_count
FROM iso_lab_216.on_call
WHERE on_duty;
-- 2
~~~

Both established separate snapshots and both see two doctors on duty.

<escape>**Session A — take An off duty:**</escape>

~~~sql
UPDATE iso_lab_216.on_call
SET on_duty = FALSE
WHERE doctor_id = 1;
-- 1 row.
~~~

<escape>**Session B — take Bình off duty:**</escape>

~~~sql
UPDATE iso_lab_216.on_call
SET on_duty = FALSE
WHERE doctor_id = 2;
-- 1 row.
~~~

Because they modify **two disjoint rows**, they do not block each other on row locks.

<escape>**Commit both sessions sequentially:**</escape>

~~~sql
-- Session A:
COMMIT;
~~~

~~~sql
-- Session B:
COMMIT;
~~~

<escape>**Verify in a new transaction:**</escape>

~~~sql
SELECT
    COUNT(*) FILTER (WHERE on_duty) AS doctors_remaining,
    COUNT(*) AS total_doctors
FROM iso_lab_216.on_call;
-- doctors_remaining = 0, total_doctors = 2.
~~~

**Both can commit successfully under Repeatable Read**, leaving zero doctors on duty. Each transaction individually saw the rule satisfied at decision time, yet **the combination of both commits** violates the invariant.

### 14.2. Why Is This Write Skew Rather Than a Same-Row Lost Update?

- Transaction A reads the **set of doctors** and writes row 1.
- Transaction B reads the same set and writes row 2.
- No single target row is updated by both; A and B's writes **do not overwrite each other**.
- The flaw is that **both decided based on stale snapshots** of an aggregate condition across the set.

This is *write skew*: two transactions write skewed changes to distinct rows, producing an outcome incompatible with any serial ordering of "if at least two remain, take one off duty."

### 14.3. Cannot Be Fixed Merely by Re-Reading the Snapshot Twice

Under Repeatable Read, if A and B re-run `COUNT(*) WHERE on_duty` before committing, each still sees its own snapshot plus its own uncommitted update:

- A sees doctor 1 off duty, doctor 2 still on duty → **1** remaining.
- B sees doctor 2 off duty, doctor 1 still on duty → **1** remaining.

Each transaction still thinks one doctor remains on duty, yet **their combined commits** produce 0. Re-reading the same snapshot cannot reveal post-snapshot changes by the other transaction.

### 14.4. Finishing and Resetting

After observing the outcome, run:

~~~sql
UPDATE iso_lab_216.on_call
SET on_duty = TRUE
WHERE doctor_id IN (1, 2);
~~~

Reset only after both A and B finish; already committed transactions cannot be undone by a new transaction's `ROLLBACK`.

## 15. Serializable: Adding Serializability Checks via SSI

**Serializable** in PostgreSQL ensures committed outcomes match running the participating Serializable transactions **sequentially in some order** (*serial execution*). It does not literally run transactions one by one; instead, it uses **Serializable Snapshot Isolation (SSI)** to permit concurrency while detecting read–write dependencies that could produce anomalies.

### 15.1. SSI Builds on Snapshot Isolation

Under Serializable, queries still read a stable snapshot just like Repeatable Read. The difference is that PostgreSQL also tracks dependencies across transactions, such as:

~~~text
Transaction A reads row/predicate X.
Transaction B writes something that would change what A read.
Transaction B also reads a predicate that A's write could change.
      |
      v
A non-serializable dependency cycle can form.
      |
      v
SSI aborts at least one transaction when needed,
returning SQLSTATE 40001.
~~~

PostgreSQL does not have to block all writers with predicate locks. **`SIReadLock`** entries in Serializable mainly **track read–write dependencies** and do not block writers the way `SELECT ... FOR UPDATE` does.

### 15.2. Serializability Applies Only to Successfully Committed Transactions

When a conflict occurs, one transaction may see:

~~~text
ERROR: could not serialize access due to
       read/write dependencies among transactions
SQLSTATE: 40001
~~~

Exact error wording varies by cause. The failed transaction **did not complete its business operation**. The application must roll back, **re-read from scratch, and re-execute the entire decision** in a fresh transaction.

### 15.3. Serializable Does Not Infer Business Rules Automatically

Suppose an application blindly sets `on_duty=FALSE` **without reading/checking the on-duty count**. Serializable only guarantees committed transactions match some serial order; a sequence of statements that is **already wrong when run serially** still corrupts data. To protect "at least one doctor remains on duty," transactions must **execute the check logic** or use constraints/mechanisms designed to enforce that invariant.

## 16. Write Skew Experiment Under Serializable

**Initial state:** reset so both doctors are on duty.

<escape>**Session A — Serializable, read count:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS on_duty_count
FROM iso_lab_216.on_call
WHERE on_duty;
-- 2
~~~

<escape>**Session B — Serializable, read same set before A commits:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS on_duty_count
FROM iso_lab_216.on_call
WHERE on_duty;
-- 2
~~~

<escape>**Session A — take doctor 1 off duty:**</escape>

~~~sql
UPDATE iso_lab_216.on_call
SET on_duty = FALSE
WHERE doctor_id = 1;
~~~

<escape>**Session B — take doctor 2 off duty:**</escape>

~~~sql
UPDATE iso_lab_216.on_call
SET on_duty = FALSE
WHERE doctor_id = 2;
~~~

<escape>**Attempt to commit both transactions:**</escape>

~~~sql
-- Session A:
COMMIT;
~~~

~~~sql
-- Session B:
COMMIT;
~~~

**Expected outcome:** under this schedule where two Serializable transactions both read `count=2` and update disjoint rows, PostgreSQL will not allow **both to commit successfully** into a non-serializable outcome. One transaction will fail with `serialization_failure` (`40001`), either at `UPDATE` or `COMMIT` depending on timing. **Do not assume A or B is always the victim.**

### 16.1. Inspecting State After One Transaction Fails

~~~sql
SELECT
    doctor_id,
    doctor_name,
    on_duty
FROM iso_lab_216.on_call
ORDER BY doctor_id;
~~~

In a normal run, one doctor went off duty and one remains on duty, because only one transaction succeeded and committed.

### 16.2. Retrying the Failed Transaction

Suppose Transaction B failed:

~~~sql
ROLLBACK;

BEGIN;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS on_duty_count
FROM iso_lab_216.on_call
WHERE on_duty;
-- 1 (assuming A committed and only doctor 2 remains on duty).
~~~

The application observes `COUNT(*)=1` and **does not run `UPDATE on_duty=FALSE`**. Then:

~~~sql
COMMIT;
~~~

The business invariant is preserved. **This demonstrates why you must retry the whole transaction**: re-running only the `UPDATE` using the stale `COUNT=2` from the aborted attempt would violate the invariant.

### 16.3. Serializable Does Not Mean Every Transaction Must Wait for All Others

SSI allows non-conflicting transactions to run and commit concurrently. When a dangerous dependency cycle arises, it **aborts one transaction** rather than blocking every path up front. Thus Serializable often simplifies correctness logic in exchange for tracking overhead and retry requirements.

### 16.4. All Relevant Writers Must Follow the Same Policy

If one service enforces the invariant under Serializable while **another service** modifies the same rows under a weaker isolation level or skips checking the rule, the system as a whole is not protected merely because one transaction used Serializable. You must govern **every write path affecting the invariant**, or use centralized locking, constraints, or procedures.

Reset both doctors to `on_duty=TRUE` once all sessions finish.

## 17. SQLSTATE 40001: Why Must You Retry the Entire Transaction?

When a PostgreSQL transaction executes:

~~~text
Read data
    ↓
Check invariant
    ↓
Make decision
    ↓
Write data
    ↓
COMMIT
~~~

the reads, validated conditions, and computed values **are valid only within that transaction's execution history**. If PostgreSQL rejects the transaction for a serialization conflict, the application must never keep a decision from the stale snapshot and replay only `UPDATE`/`COMMIT`.

### 17.1. Proper Retry Pattern

~~~text
for attempt = 1..MAX_ATTEMPTS:
    acquire connection
    BEGIN SERIALIZABLE
    try:
        RE-READ all required data
        RECOMPUTE business decision
        EXECUTE all writes inside transaction
        COMMIT
        return success
    if SQLSTATE == 40001:
        ROLLBACK if still needed
        release connection/resources
        wait brief bounded backoff
        retry ENTIRE transaction from start
    if other error:
        ROLLBACK
        handle error per policy
    if attempts exhausted:
        report conflict for handling or later retry
~~~

**Never write an infinite loop**: use a maximum attempt cap, sensible backoff/jitter, thorough logging, and explicit failure reporting under excessive contention.

### 17.2. Never Retry Only the Failing Statement

**Business-incorrect:**

~~~text
Read count=2 in failed transaction.
ROLLBACK.
BEGIN new transaction.
UPDATE doctor_2 SET on_duty=FALSE.  -- reuses stale decision
COMMIT.
~~~

If another transaction already took doctor 1 off duty, the `UPDATE` in the new transaction breaks the "always keep one doctor on duty" rule. You must **re-read the count** inside the fresh transaction.

### 17.3. Error 40001 Can Surface at UPDATE or COMMIT

Applications must wrap **including `COMMIT`** inside retry handling. Even if every `SELECT`/`UPDATE` returned cleanly, SSI can detect a conflict requiring abort at commit time.

In PostgreSQL, the standard SQLSTATE for serialization failures is **`40001`**; inspect **SQLSTATE** rather than matching error message strings, which vary across versions, locales, and causes.

### 17.4. Other Errors Should Not Be Blindly Retried

| Typical SQLSTATE | Name / Meaning | Approach |
| --- | --- | --- |
| `40001` | `serialization_failure` | Retry **entire transaction**, bounded |
| `40P01` | `deadlock_detected` | Often safe to retry **entire transaction** if operation is safe and bounded |
| `23505` | `unique_violation` | Analyze key conflict; do not blindly retry all cases |
| `23514` | `check_violation` | Fix data or logic violating CHECK |
| `23503` | `foreign_key_violation` | Fix referenced data or operation ordering |
| `55P03` | `lock_not_available` | Review timeout/`NOWAIT` policy; avoid blind loops |

Under Serializable, certain concurrent unique-key insert races can yield `23505` even after an application pre-check. That **does not make every `23505` automatically retryable**: understand the invariant, key conventions, and whether repeating the request is safe.

### 17.5. External Side Effects Must Be Managed Separately

Never send emails, call payment APIs, emit non-idempotent events, or write external files **inside each retry attempt** as if the transaction were guaranteed to commit:

~~~text
Attempt 1:
    Send confirmation email
    UPDATE in PostgreSQL
    COMMIT -> 40001

Attempt 2:
    Resend confirmation email
    UPDATE
    COMMIT succeeds

Result: confirmation email sent twice.
~~~

A common pattern is the **transactional outbox**: write an event row inside the same database transaction, publish externally only after commit succeeds, and make consumers idempotent. This separates **database transaction retries** from **non-rollbackable external effects**.

### 17.6. Connection Loss at COMMIT Is a Separate Case

If the network drops right during `COMMIT`, the application may **not know** whether the transaction committed or not. Never treat that as `40001` and re-run a non-idempotent financial write. Use idempotency keys, unique request IDs, reconciliation lookups, or recovery workflows.

## 18. Java/JDBC Example: Serializable Transaction with Retries

Java applications call `Connection.setTransactionIsolation(Connection.TRANSACTION_SERIALIZABLE)` before the first SQL statement, then inspect `SQLException.getSQLState()` to handle `40001`.

The following example uses the lab schema to **request taking a doctor off duty if at least two doctors remain on duty**. It demonstrates the retry loop without external side effects, assuming all operations touching this invariant use Serializable or an equivalent coordination protocol.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OnCallService {
    public static boolean requestOffDuty(
            DataSource dataSource,
            int doctorId
    ) throws SQLException, InterruptedException {
        final int maxAttempts = 5;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            boolean retry = false;

            try (Connection connection = dataSource.getConnection()) {
                connection.setAutoCommit(false);
                connection.setTransactionIsolation(
                    Connection.TRANSACTION_SERIALIZABLE
                );

                try {
                    int onDutyCount;
                    try (PreparedStatement query = connection.prepareStatement(
                            "SELECT COUNT(*) FROM iso_lab_216.on_call "
                            + "WHERE on_duty"
                         );
                         ResultSet rs = query.executeQuery()) {
                        rs.next();
                        onDutyCount = rs.getInt(1);
                    }

                    if (onDutyCount <= 1) {
                        connection.commit();
                        return false; // Cannot go off duty.
                    }

                    int changedRows;
                    try (PreparedStatement update = connection.prepareStatement(
                            "UPDATE iso_lab_216.on_call "
                            + "SET on_duty = FALSE "
                            + "WHERE doctor_id = ? AND on_duty"
                         )) {
                        update.setInt(1, doctorId);
                        changedRows = update.executeUpdate();
                    }

                    connection.commit();
                    return changedRows == 1;

                } catch (SQLException ex) {
                    try {
                        connection.rollback();
                    } catch (SQLException rollbackFailure) {
                        ex.addSuppressed(rollbackFailure);
                    }

                    if ("40001".equals(ex.getSQLState())
                            && attempt < maxAttempts) {
                        retry = true;
                    } else {
                        throw ex;
                    }
                }
            }

            if (retry) {
                // Simple backoff illustration.
                // Real systems should use jitter and a timeout policy.
                Thread.sleep(20L * attempt);
            }
        }

        throw new SQLException("Retry limit exhausted");
    }
}
~~~

### 18.1. Why Read Inside the Retry Loop?

Each retry acquires a fresh connection/transaction and re-runs `SELECT COUNT(*)`. Thus, once one doctor has gone off duty, the next attempt sees only one remaining doctor and refuses to let the last doctor leave.

### 18.2. Why Wrap COMMIT Inside try/catch?

`COMMIT` under Serializable can also fail with `40001`. Wrapping only `UPDATE` in the retry block and calling commit outside would miss a critical failure path.

### 18.3. What Real Applications Still Need

- Timeouts, backoff with jitter, bounded retries, and `40001` metrics.
- Ensuring the connection pool restores isolation/autocommit state upon return.
- Distinguishing business errors, missing doctor IDs, already off-duty doctors, and concurrency conflicts.
- Protecting every write path affecting on-call counts, not just a single method.
- Clear policies for when external notifications or audits are emitted.
- Idempotency and reconciliation for requests whose commit outcome becomes ambiguous on network loss.

The code above is a **lesson on transactions and retries**, not production-complete healthcare scheduling code.

## 19. An Alternative: Coordinator Locking with SELECT FOR UPDATE

Serializable is not the only way to protect multi-row invariants. You can **explicitly serialize the business operation** by requiring every writer to lock **the same coordinator row** before reading and modifying data.

In the lab schema, `duty_guard` contains a single row `guard_id=1`.

### 19.1. Session A Acquires the Lock First

**Initial state:** both doctors are on duty.

<escape>**Session A:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT guard_id
FROM iso_lab_216.duty_guard
WHERE guard_id = 1
FOR UPDATE;
-- A holds this row lock until transaction end.

SELECT COUNT(*) AS on_duty_count
FROM iso_lab_216.on_call
WHERE on_duty;
-- 2.

UPDATE iso_lab_216.on_call
SET on_duty = FALSE
WHERE doctor_id = 1;

-- Do not commit yet so Session B attempts to lock.
~~~

### 19.2. Session B Must Wait on the Same Lock

<escape>**Session B:**</escape>

~~~sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT guard_id
FROM iso_lab_216.duty_guard
WHERE guard_id = 1
FOR UPDATE;
-- WAITS for Session A to COMMIT/ROLLBACK.
~~~

While B is waiting, let A run `COMMIT`:

~~~sql
-- Session A:
COMMIT;
~~~

Once the lock releases, B proceeds:

~~~sql
-- Session B:
SELECT COUNT(*) AS on_duty_count
FROM iso_lab_216.on_call
WHERE on_duty;
-- 1 (because A committed taking doctor 1 off duty).

-- Since only 1 remains, the app does NOT run
-- UPDATE doctor_id=2 SET on_duty=FALSE.

COMMIT;
~~~

**Why it works:** every transaction modifying duty status locks `duty_guard(1)` before counting on-duty doctors. Checks and writes occur **one at a time**, so under Read Committed, once B acquires the lock, `SELECT COUNT(*)` sees A's committed update.

### 19.3. Limits of Coordinator Locking

- **Every writer must follow the protocol.** If any job skips locking the guard row, this example alone no longer preserves the invariant.
- A shared lock row can become a **contention bottleneck** under high concurrency.
- Keep transactions short and acquire locks in consistent order to reduce deadlocks.
- If the rule is scoped per hospital or shift, consider **one guard row per scope** rather than a single global lock.
- Restrict permissions and access on the guard table to prevent unintended modifications.

Avoid overly broad global locks on heavy workloads, yet this example shows how **a multi-row invariant can be protected via business-level serialization** without forcing every unrelated operation to contend on a data row.

### 19.4. Contrast with SELECT FOR UPDATE Locking Only Each Doctor's Row

If A locks only doctor 1's row and B locks only doctor 2's row, both transactions can still update separate rows without blocking each other. Because the invariant governs **the total count on duty**, you must lock a **shared coordination resource** or use SSI to detect read–write conflicts across the set.

## 20. SELECT FOR UPDATE and Repeatable Read: Still Can Error

`SELECT ... FOR UPDATE` locks rows selected by the query. Unlike a plain `SELECT`:

~~~sql
BEGIN;

SELECT *
FROM iso_lab_216.stock
WHERE sku = 'SKU-A'
FOR UPDATE;

-- Operations on the locked row.

COMMIT;
~~~

Under Read Committed, if the row is locked/updated by another transaction, the query waits and then locks the **updated committed version** once the other transaction commits.

Under Repeatable Read or Serializable, if a target row **was modified by another transaction after the current transaction's snapshot**, PostgreSQL raises `could not serialize access due to concurrent update` instead of silently locking the newer version.

### 20.1. FOR UPDATE Does Not Prevent All Phantoms

Locking a few existing rows does not automatically prevent another transaction from inserting **a new row matching the predicate** under Read Committed. For example, locking two existing doctors does not automatically block inserts or deletes affecting an aggregate business rule.

When an invariant depends on a **mutable set of rows**, consider:

- Serializable with validation logic and retries;
- Scope-matched coordinator locking followed by all writers;
- Constraints, triggers, or procedures tailored to the invariant;
- Redesigning the schema so the invariant maps to constraints on a single parent entity.

### 20.2. NOWAIT and SKIP LOCKED Do Not Replace Isolation

PostgreSQL offers:

~~~sql
SELECT *
FROM iso_lab_216.stock
WHERE sku = 'SKU-A'
FOR UPDATE NOWAIT;
~~~

or:

~~~sql
SELECT *
FROM iso_lab_216.stock
FOR UPDATE SKIP LOCKED;
~~~

`NOWAIT` errors immediately instead of waiting on a row lock; `SKIP LOCKED` skips rows that are currently locked. These are useful in job-queue/worker models, yet **do not provide a consistent snapshot for general business decisions**. `SKIP LOCKED` deliberately yields an incomplete view of locked rows, so never use it to sum inventory or verify table-wide invariants.

## 21. SERIALIZABLE READ ONLY DEFERRABLE for Long Reports

A long-running read-only transaction may need a **serializable-consistent snapshot** without risking repeated retries. PostgreSQL supports:

~~~sql
BEGIN TRANSACTION
    ISOLATION LEVEL SERIALIZABLE
    READ ONLY
    DEFERRABLE;

SELECT
    COUNT(*) AS total_orders,
    SUM(amount) AS total_amount
FROM iso_lab_216.orders;

SELECT
    COUNT(*) FILTER (WHERE on_duty) AS active_doctors
FROM iso_lab_216.on_call;

COMMIT;
~~~

When all three flags **`SERIALIZABLE READ ONLY DEFERRABLE`** are combined, the transaction may **wait before taking its initial snapshot** until PostgreSQL finds a safe snapshot. Afterward, it reads with serializability guarantees without risk of aborting for serialization anomalies, while avoiding some tracking overhead of normal read–write Serializable transactions.

### 21.1. DEFERRABLE Does Not Apply in Every Mode

Per PostgreSQL rules, `DEFERRABLE` only takes effect when the transaction is **both** `SERIALIZABLE` and `READ ONLY`. Using it with Read Committed or a read–write transaction does not provide this safe-snapshot waiting behavior.

### 21.2. A Safe Snapshot Does Not Mean Instantaneous Real-Time Data

The report still reads **a point-in-time snapshot**. Other transactions committing **after that snapshot** will not appear in the report's SELECTs. `DEFERRABLE` prioritizes serializable safety, not "real-time" freshness.

### 21.3. When to Consider It

- Generating long financial summary reports.
- Long-running snapshot exports/backups needing serializable consistency.
- Computing multi-table analytics without SSI retry overhead.

In exchange, **there may be an initial wait before the first query**. Measure latency and avoid holding transactions open unnecessarily; never make this the default for everyday HTTP requests.

## 22. READ ONLY Repeatable Read or Serializable?

If the goal is simply "every SELECT inside a report sees the same snapshot," Repeatable Read Read Only usually suffices:

~~~sql
BEGIN TRANSACTION
    ISOLATION LEVEL REPEATABLE READ
    READ ONLY;

SELECT COUNT(*) FROM iso_lab_216.orders;
SELECT SUM(amount) FROM iso_lab_216.orders;

COMMIT;
~~~

However, a **stable snapshot** does not guarantee **global equivalence to a serial execution** when analyzing cross-transaction dependencies. A report enforcing complex logical consistency over data written concurrently by multiple writers may require Serializable guarantees.

**Distinguish three questions:**

1. Do two SELECTs just need the **same snapshot**? → Repeatable Read.
2. Must committed transaction history match a **serial execution order**? → Serializable, with retries.
3. Can a long read-only query accept an **initial wait** for a safe snapshot to avoid serialization failures? → Serializable Read Only Deferrable.

## 23. Isolation Levels Do Not Replace Constraints

Isolation governs interactions across concurrent transactions; **constraints** define valid data structure. Both toolsets complement each other.

Example:

~~~sql
CREATE TABLE iso_lab_216.wallets (
    wallet_id INTEGER PRIMARY KEY,
    balance NUMERIC(12, 2) NOT NULL
        CHECK (balance >= 0)
);
~~~

`CHECK (balance >= 0)` keeps **every wallet row's balance** non-negative across all isolation levels. Likewise:

- `PRIMARY KEY`/`UNIQUE` prevent duplicate keys.
- `FOREIGN KEY` protects referential integrity.
- `NOT NULL` requires a value to be present.

However, no simple single-row `CHECK` on `on_call` can express "**at least one row in the table** must be on duty." Multi-row invariants require extra design. Serializable isolation protects compliant read–write logic across transactions, yet **cannot create schema constraints on the application's behalf**.

### 23.1. A Common Design Bug: SELECT First, Then Unprotected INSERT

~~~text
Transaction A: SELECT "does this code exist?" -> no.
Transaction B: SELECT "does this code exist?" -> no.
Both A and B INSERT that code.
~~~

Under Read Committed or Repeatable Read, pre-checking with SELECT **never replaces** a unique constraint. Placing `UNIQUE` on the key is the reliable barrier; the application must handle conflicts cleanly. Even Serializable does not remove the need for schema constraints on core invariants.

### 23.2. Business Invariants Must Cover Full Scope

If an invariant states "the total balance across accounts in a group cannot go negative" or "at least one person must be on shift," locking or updating **just one row** is not necessarily enough. Identify **the full dataset involved in the decision** and **every write path that can modify that dataset**.

## 24. Deadlocks vs. Serialization Failures

Deadlocks occur when transactions wait on each other in a cycle:

~~~text
Transaction A holds lock on row 1, wants row 2.
Transaction B holds lock on row 2, wants row 1.

A waits for B; B waits for A.
~~~

PostgreSQL detects the deadlock and aborts one transaction to break the cycle, typically raising `SQLSTATE 40P01`.

Serialization failure `40001` can occur **without any row-lock deadlock**, when SSI detects a non-serializable read–write history.

| Distinction | Deadlock | Serialization Failure |
| --- | --- | --- |
| Typical scenario | Lock-wait cycle | Conflicting read–write / update dependencies |
| Typical SQLSTATE | `40P01` | `40001` |
| Requires transactions holding locks waiting on each other? | Yes, in a wait cycle | Not necessarily |
| Handling | Safe rollback/retry, consistent lock ordering | Retry **entire transaction** with fresh data |
| Possible under Read Committed? | Yes | Not the hallmark error, though other contention errors occur |

### 24.1. Consistent Lock Ordering Reduces Deadlocks

When updating multiple accounts, design every transaction to lock them in the same ascending order rather than one locking 1→2 and another locking 2→1. Still, **lock ordering does not replace serializability logic** for invariants evaluated over multi-row snapshots.

## 25. Resource Usage and Latency of Isolation Levels

There is no universal formula saying "Serializable is always N× slower" or "Read Committed is always fastest" across every workload.

### 25.1. Read Committed

Strengths:

- Familiar default suitable for many simple operations.
- Per-statement snapshots allow later statements to see recent commits.
- Pairs well with atomic `UPDATE ... WHERE` for single-row invariants.

Trade-offs:

- The same transaction can see values or row sets shift between two SELECTs.
- Multi-step read-then-decide-then-write logic risks acting on stale data.
- Complex write conditions under concurrent writers can produce nuanced recheck outcomes.

### 25.2. Repeatable Read

Strengths:

- Stable snapshot well-suited for multi-query reads and reports.
- PostgreSQL prevents dirty, nonrepeatable, and phantom reads.
- Allows concurrent writers to continue via MVCC rather than locking the entire dataset just to read a snapshot.

Trade-offs:

- Can hit `40001` when updating or locking a row modified by another transaction after snapshot start.
- Still susceptible to write skew / serialization anomalies across disjoint rows.
- Long-lived snapshots force PostgreSQL to retain older row versions longer.

### 25.3. Serializable

Strengths:

- Serializable transactions that **successfully commit** produce results equivalent to some serial execution.
- Reduces manual locking designs for complex data-check invariants when all relevant writers participate properly.

Trade-offs:

- Overhead from tracking read–write / predicate dependencies.
- Higher probability of `40001` retries under contention.
- Query plans and scanned row counts affect `SIReadLock` granularity; broad scans can trigger more false-positive conflicts.
- Requires idempotency, retry logic, and monitoring.

### 25.4. Long-Running Transactions Affect VACUUM

A snapshot kept open too long forces PostgreSQL to retain dead row versions needed by that active transaction, increasing table bloat and autovacuum pressure. Never leave transactions open while waiting on user input, especially with long-lived snapshots.

### 25.5. Do Not Turn Every Application Bug into an Isolation Change

For instance, lost updates caused by writing stale precomputed constants are cleanly fixed with `UPDATE SET counter=counter+1`. Duplicate SKUs belong in a `UNIQUE` constraint. Multi-row invariants may need Serializable or coordinator locking. **Picking the right tool for each problem class** outperforms blanket isolation upgrades.

## 26. Monitoring Transactions and Locks in PostgreSQL

### 26.1. Viewing Open Transactions

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event
FROM pg_catalog.pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Visibility into other sessions' details depends on PostgreSQL roles and configuration. Watch closely for prolonged **`idle in transaction`** connections and lock-waiting transactions.

### 26.2. Viewing SSI Locks

~~~sql
SELECT
    pid,
    locktype,
    mode,
    relation::regclass AS relation_name,
    granted
FROM pg_catalog.pg_locks
WHERE mode = 'SIReadLock'
ORDER BY pid, relation_name;
~~~

`SIReadLock` tracks predicates for Serializable SSI; **never interpret it as a `FOR UPDATE` lock blocking all writers**. Exact lock granularity depends on queries, indexes, plans, and PostgreSQL lock-table memory management.

### 26.3. Finding Sessions Blocked by Other Sessions

~~~sql
SELECT
    a.pid,
    a.state,
    a.wait_event_type,
    a.wait_event,
    pg_catalog.pg_blocking_pids(a.pid) AS blocking_pids
FROM pg_catalog.pg_stat_activity AS a
WHERE a.wait_event_type = 'Lock'
ORDER BY a.pid;
~~~

When Session B waits on Session A in the `SELECT FOR UPDATE`/`UPDATE` experiment, you will see a `Lock` wait event here. When only `SIReadLock` entries exist for SSI, writers are not necessarily blocked by predicate locks.

### 26.4. Wait Limits and Timeouts

In a lab environment, you can scope timeouts to a transaction:

~~~sql
BEGIN;

SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '15s';

SELECT COUNT(*)
FROM iso_lab_216.orders;

ROLLBACK;
~~~

- `lock_timeout` bounds waiting time for a lock.
- `statement_timeout` bounds execution time of a single statement.
- `idle_in_transaction_session_timeout` can be set at server/session level to terminate connections idling in a transaction too long.

Timeouts **do not guarantee invariant correctness**. When a statement errors or times out inside a PostgreSQL transaction, the transaction enters the aborted state and must roll back before continuing.

### 26.5. Which Metrics to Track in Production?

An operational dashboard should monitor:

- Count and rate of transactions ending with `40001`.
- Average retry counts and retry-exhaustion rate.
- Transaction duration, lock-wait time, and deadlocks.
- Count of `idle in transaction` connections.
- Throughput and latency shifts across isolation levels.
- Table bloat and autovacuum activity if long read transactions exist.

**Never "optimize" by disabling SSI or lowering isolation just to silence `40001` errors without an alternative mechanism preserving business correctness.**

## 27. Common Misconceptions

| Misconception | Reality in PostgreSQL |
| --- | --- |
| Read Committed can read uncommitted data | No; PostgreSQL does not allow dirty reads |
| READ UNCOMMITTED speeds things up via dirty reads | It behaves equivalently to Read Committed |
| Read Committed keeps one snapshot for the whole transaction | Each read statement normally gets its own snapshot |
| Repeatable Read always sees other transactions' commits on each SELECT | It keeps a stable snapshot |
| PostgreSQL Repeatable Read allows phantoms like the SQL standard minimum | PostgreSQL **prevents phantoms** under Repeatable Read |
| Repeatable Read is equivalent to Serializable | **Write skew** can still happen |
| Two transactions updating disjoint rows are always safe | They can jointly violate a multi-row invariant |
| Serializable forces transactions to run serially via row locks | PostgreSQL uses SSI, running concurrently and aborting dangerous schedules |
| Serializable never produces concurrency errors | It can raise `40001` |
| Retrying only the failing UPDATE is enough | You must retry the **entire transaction logic**, including reads |
| 40001 only occurs under Serializable | Repeatable Read can also raise it on concurrent updates |
| SELECT FOR UPDATE locks all future rows matching a predicate | It locks selected rows, not future phantoms under Read Committed |
| Re-running COUNT under Repeatable Read shows newer commits | It still uses the same snapshot |
| An atomic UPDATE does not help with concurrency | With proper conditions on one row, it is far safer than read–then–write |
| Serializable automatically enforces every business rule | Rules still must be coded/checked |
| Retrying can freely resend emails or payments | External side effects require idempotency/outboxes |
| Sending COMMIT guarantees success even if connection drops | Outcome may be uncertain, requiring reconciliation |
| READ ONLY means the user lacks write privileges | Transaction access mode is distinct from SQL privileges |
| DEFERRABLE works at every isolation level | It only activates with Serializable + Read Only |
| SIReadLock always blocks writers | It tracks SSI conflicts without blocking like row locks |
| Long transactions are always harmless thanks to MVCC | They retain old row versions, worsening bloat and vacuum load |

## 28. Hands-On Exercises

### Exercise 1 — Identifying the Default Level

Run:

~~~sql
SHOW default_transaction_isolation;
SHOW transaction_isolation;
~~~

**Question:** what is your database's default? In an unmodified configuration, which level does PostgreSQL normally use?

**Suggested answer:** normally `read committed`. Never assume every server keeps the default unchanged.

### Exercise 2 — Nonrepeatable Read

Following Section 6.1, run two windows A and B and record the observed prices.

**Expected:** under Read Committed, A reads `100` before B commits, then `120` after B commits. Explain per-statement snapshots.

### Exercise 3 — No Dirty Reads

Session A updates price to `999` without committing. Session B uses `READ UNCOMMITTED` and reads the price.

**Expected:** B does not see uncommitted `999`. Why does PostgreSQL differ from engines that permit dirty reads?

### Exercise 4 — Phantoms Under Read Committed

Session A counts `PAID` orders, B inserts `order_id=103` as PAID and commits, and A counts again.

**Expected:** `1 → 2`. Reset afterward.

### Exercise 5 — Repeatable Read Preserves the Old Price

Repeat Exercise 2, except A sets `REPEATABLE READ` right before the first `SELECT`.

**Expected:** both SELECTs in A return `100`; only after committing and starting a new transaction does `120` appear.

### Exercise 6 — When Does the Snapshot Start?

Compare:

~~~text
A: BEGIN RR
A: SELECT price
B: UPDATE/COMMIT
A: SELECT price
~~~

with:

~~~text
A: BEGIN RR
B: UPDATE/COMMIT
A: first SELECT price
~~~

**Expected:** in the second schedule, A's first SELECT sees the new price because the snapshot was not yet fixed at `BEGIN`.

### Exercise 7 — Phantoms Under PostgreSQL Repeatable Read

Repeat Exercise 4 with A using Repeatable Read. Predict both `COUNT(*)` results before running.

**Answer:** still `1` inside Transaction A; `2` only in a subsequent transaction. Here PostgreSQL exceeds the SQL standard's minimum requirement.

### Exercise 8 — Same-Row UPDATE Under Repeatable Read

A opens RR and reads `price=100`; B updates the same row to `120` and commits; A attempts to update it to `130`.

**Expected:** `SQLSTATE 40001`, not a silent overwrite. A must roll back and retry.

### Exercise 9 — Decrementing Stock Under READ COMMITTED

Using two sessions, deduct `4` from `quantity=5` via:

~~~sql
UPDATE iso_lab_216.stock
SET quantity = quantity - 4
WHERE sku = 'SKU-A'
  AND quantity >= 4
RETURNING quantity;
~~~

Have A update first and hold the transaction, B send the same statement and wait, then A commit.

**Expected:** one UPDATE returns 1 row; the other returns **0 rows**; final stock is **1**.

### Exercise 10 — Application-Tier Lost Update

Two transactions read `counter=10`, compute 11 in the app, and sequentially run `SET value=11`.

**Answer:** final value is 11 despite two increments. Switch to `SET value=value+1` and explain why the result is 12 when both transactions commit.

### Exercise 11 — Writing Optimistic Locking

Suppose a table has `version INTEGER NOT NULL`. Design the statement:

~~~sql
UPDATE some_table
SET value = :new_value,
    version = version + 1
WHERE id = :id
  AND version = :version_read_before;
~~~

Explain why **0 rows updated** signals that the value/version changed and requires re-reading/recomputing. This technique handles concurrency without changing the session's isolation level.

### Exercise 12 — Write Skew Under Repeatable Read

Reset both doctors to `on_duty=TRUE` and run the Section 14 scenario.

**Expected:** both transactions read `count=2`, each turns off a different row, and both commit, leaving **0 doctors on duty**. Why wasn't there a same-row lost update?

### Exercise 13 — Serializable Protects the Invariant

Reset both doctors to on duty and repeat Exercise 12 using **SERIALIZABLE** in both A and B.

**Expected:** both cannot commit into a non-serializable outcome; one receives `40001`.

### Exercise 14 — Proper Retry Under Serializable

After a transaction hits `40001`, start a new transaction and re-read `COUNT(*) WHERE on_duty`.

**Expected:** if only one doctor remains on duty, refuse to take that doctor off duty. Explain why retrying only the `UPDATE` statement is wrong.

### Exercise 15 — Coordinator Lock

Use `duty_guard` and `SELECT ... FOR UPDATE` as in Section 19.

**Question:** when does Transaction B wait? After A commits, how many on-duty doctors does B see under Read Committed? What is the risk if a job C skips acquiring the guard lock?

### Exercise 16 — Read Committed and WHERE Recheck

A holds a lock updating stock from 5 down to 1; B sends `UPDATE ... WHERE quantity>=4` before A commits.

**Answer:** after A commits, B re-evaluates the predicate against the new row version and updates 0 rows. What differs if A rolls back?

### Exercise 17 — Report Snapshot

A report reads total orders and total amount using two `SELECT` statements inside one transaction while B inserts an order.

Compare:

- A using `READ COMMITTED`.
- A using `REPEATABLE READ READ ONLY`.

**Answer:** RC can observe two different snapshots; RR uses one consistent snapshot for both SELECTs. This matters whenever report KPIs must reflect the exact same point in time.

### Exercise 18 — READ ONLY DEFERRABLE

Write the transaction:

~~~sql
BEGIN TRANSACTION
    ISOLATION LEVEL SERIALIZABLE
    READ ONLY
    DEFERRABLE;

SELECT COUNT(*) FROM iso_lab_216.orders;

COMMIT;
~~~

**Question:** why might it wait before reading? Does `DEFERRABLE` without `SERIALIZABLE READ ONLY` have the same effect?

### Exercise 19 — Distinguishing Error Codes

Explain the differences among:

- `40001` — serialization failure.
- `40P01` — deadlock.
- `23505` — duplicate unique key.

Which errors merit full-transaction retries? Which require analyzing data/logic instead of blind retries?

### Exercise 20 — Designing Safe Retries

A request creates an order, decrements stock, and sends a confirmation email. If a Serializable transaction hits `40001` after the email was sent, what happens on retry?

**Hint:** do not send emails inside each database transaction attempt; consider an outbox/idempotency and emitting events after commit.

### Exercise 21 — Monitoring Check

Write a `pg_stat_activity` query to find transactions whose `xact_start` exceeds 5 minutes:

~~~sql
SELECT
    pid,
    state,
    now() - xact_start AS transaction_age
FROM pg_catalog.pg_stat_activity
WHERE xact_start IS NOT NULL
  AND now() - xact_start > INTERVAL '5 minutes';
~~~

**Question:** why can holding a snapshot too long hurt VACUUM? When is `idle in transaction` a dangerous signal?

### Exercise 22 — Observing SIReadLock

Inside an open Serializable transaction, query `on_call` and then inspect `pg_locks` from another session.

**Question:** what is `SIReadLock` for? Why shouldn't you confuse it with `FOR UPDATE`?

### Exercise 23 — Choosing the Right Mechanism

Match each scenario with the appropriate direction:

| Scenario | Recommended Direction |
| --- | --- |
| Increment a single-row counter | Atomic `UPDATE SET value=value+1` |
| Decrement stock for one SKU | `UPDATE ... WHERE quantity>=requested`, check rowcount |
| Multi-SELECT report needing a stable snapshot | Repeatable Read Read Only |
| Prevent both doctors from going off duty | Serializable + retry or proper coordinator lock |
| Forbid duplicate SKUs | `UNIQUE` constraint |
| Forbid negative single-row balance | `CHECK` plus atomic update |
| Long batch report needing a safe serializable snapshot | Serializable Read Only Deferrable |

No single mechanism fits every application.

### Exercise 24 — Code Review

A developer wrote:

~~~sql
BEGIN;
SELECT COUNT(*) FROM iso_lab_216.on_call WHERE on_duty;
-- If count >= 2, application executes:
UPDATE iso_lab_216.on_call
SET on_duty = FALSE
WHERE doctor_id = :chosen_doctor;
COMMIT;
~~~

List at least six review questions:

1. Which isolation level does the transaction use?
2. Can multiple writers evaluate the same predicate concurrently?
3. Is write skew possible if disjoint rows are updated?
4. Do all writers share the same policy or coordinator lock?
5. Does the application handle `40001` and retry the **entire transaction**?
6. If the transaction fails, did any external side effects already happen?
7. If the doctor is already off duty or missing, is rowcount checked?
8. Are auditing, permissions, and long-transaction protections needed?

### Exercise 25 — Comparing Read Committed and Serializable

One system handles 10,000 requests/s incrementing a single-row view count with `SET view_count=view_count+1`. Another system maintains multi-table conditional invariants across transactions.

**Question:** should both systems use the same isolation level just because the second needs Serializable? Explain retry cost, correctness, and atomic SQL/constraint alternatives.

## 29. Isolation Selection and Operations Checklist

Before choosing an isolation level for a workflow, answer:

1. **How many statements inside a transaction need a consistent read?** One snapshot per statement, or one snapshot for the whole transaction?
2. **Is the invariant single-row or multi-row?** Are there set/predicate-based aggregate rules?
3. **Do multiple writers make decisions from read data?** If so, is write skew possible?
4. **Can you write one atomic SQL statement instead of read–then–write?** E.g., `UPDATE quantity=quantity-n WHERE quantity>=n`.
5. **Can deterministic rules be enforced with constraints?** `UNIQUE`, `CHECK`, `FOREIGN KEY`?
6. **If using Serializable/Repeatable Read and `40001` occurs, how does the app retry the full transaction?**
7. **Are there external side effects outside the database?** Email, payments, event buses, files?
8. **Do any transactions mix different isolation levels while affecting the same invariant?**
9. **When waiting on locks or retrying repeatedly, do requests have proper timeouts, backoff, and logs?**
10. **Is transaction duration stretched by user interaction, network I/O, or heavy reports?**
11. **Have you tested with two real concurrent sessions rather than running SQL sequentially in one console?**
12. **Have you measured `40001` rates, deadlocks, latency, lock waits, and VACUUM impact under representative load?**

If answers are unclear, never blindly raise or lower isolation expecting it to "handle concurrency automatically." Sketch **possible two-transaction schedules**, then pick the minimal mechanism sufficient to guarantee business correctness.

## 30. Official PostgreSQL Documentation

Key reference pages:

- [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): anomaly matrix, Read Committed, Repeatable Read, and Serializable behavior, `40001`, and SSI.
- [PostgreSQL — SET TRANSACTION](https://www.postgresql.org/docs/current/sql-set-transaction.html): setting isolation, READ ONLY/READ WRITE, DEFERRABLE, and timing rules.
- [PostgreSQL — Concurrency Control / MVCC](https://www.postgresql.org/docs/current/mvcc.html): how PostgreSQL manages concurrency.
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): row locks, `SELECT FOR UPDATE`, deadlocks, and lock modes.
- [PostgreSQL — BEGIN](https://www.postgresql.org/docs/current/sql-begin.html): opening transactions with transaction modes.
- [PostgreSQL — pg_stat_activity](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-ACTIVITY-VIEW): inspecting active sessions and transactions.
- [PostgreSQL — pg_locks](https://www.postgresql.org/docs/current/view-pg-locks.html): inspecting locks, including `SIReadLock` for Serializable.
- [PostgreSQL — Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html): SQLSTATE `40001`, `40P01`, `23505`, and others.

URLs using `/docs/current/` point to the current stable PostgreSQL release documentation. When targeting a specific major version (such as PostgreSQL 14, 15, 16, 17, or 18), consult the **documentation for that exact version** to confirm syntax and recent behavior details.

## 31. Summary

PostgreSQL's three isolation levels serve clear purposes:

- **Read Committed** is the default, prevents dirty reads, and creates snapshots **per statement**. It fits many everyday workloads, especially when paired with properly conditioned atomic `UPDATE`s. In return, two statements in one transaction can see different commits, allowing nonrepeatable reads and phantoms.
- **Repeatable Read** keeps a **stable snapshot** and in PostgreSQL prevents both nonrepeatable reads and phantoms. However, it still allows **write skew** across transactions updating disjoint rows based on stale snapshots, and attempting to update/lock a row modified after the snapshot can raise `40001`.
- **Serializable** adds **SSI** tracking so that Serializable transactions that **successfully commit** match a serial execution order. It is a powerful tool for multi-row and predicate-based invariants, provided the application implements **bounded, observable full-transaction retries on `SQLSTATE 40001`** and avoids blindly repeating external side effects.

**Key lesson:** choose isolation based on behavior, not just the level name. Determine **how stable your snapshot must be, whether invariants span one or many rows, whether SQL can be written atomically, who else can write concurrently, and what the app does when a transaction cannot commit**. Combining isolation levels with atomic statements, constraints, appropriate locks, retries/idempotency, and real two-session testing keeps PostgreSQL data accurate under concurrent users and workers.
