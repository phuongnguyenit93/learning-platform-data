# SELECT FOR UPDATE, FOR NO KEY UPDATE, FOR SHARE, and FOR KEY SHARE in PostgreSQL

When multiple transactions concurrently read and modify the same row, **MVCC** lets plain `SELECT` queries see consistent data without waiting for every write. Yet MVCC does not answer every business concurrency question: if two users try to deduct inventory simultaneously, if one session prepares to delete a customer while another creates an order referencing that customer, or if multiple workers pick a job, **which transaction proceeds and which must wait?**

PostgreSQL provides four **row-level lock modes** to express the required level of protection:

- `FOR UPDATE` — the strongest lock in the group; conflicts with all four modes.
- `FOR NO KEY UPDATE` — locks for updates that do not alter identifier/foreign-key-relevant keys; still permits reads holding a reference key lock.
- `FOR SHARE` — multiple sessions can hold a shared lock to read, preventing writers from updating or deleting the row while held.
- `FOR KEY SHARE` — a weaker shared lock, primarily protecting the row from deletion or changes to key values; permits updates to non-key columns in many cases.

This lesson is about **row locks**, not four types of snapshots. They work alongside MVCC, transaction isolation, table-level locks, foreign keys, and deadlock detection.

You will practice using **two PostgreSQL sessions**, read the conflict matrix, use `NOWAIT`/`SKIP LOCKED`, target specific tables with `OF`, observe blocked transactions, handle errors in JDBC, and recognize cases where **row locks should not replace a unique constraint**.

## 1. Why Plain SELECT Is Not Enough

Suppose a store has 5 units of a product in stock. Two workers run concurrently:

~~~text
Worker A                           Worker B
---------------------------------  ---------------------------------
SELECT stock_qty → 5               SELECT stock_qty → 5
Confirm stock available            Confirm stock available
Prepare to deduct 4                Prepare to deduct 4
UPDATE stock_qty = 1               UPDATE stock_qty = 1
~~~

If the application reads 5, computes the new value 1 in advance, and writes `SET stock_qty = 1` without appropriate conditions or checks, the system can overwrite and lose a stock deduction. The fact that each `SELECT` sees committed data under MVCC **does not automatically make the entire read–decide–write sequence atomic**.

There are two common solutions:

1. **Put the condition and change directly into the DML**, e.g., `UPDATE ... SET stock_qty = stock_qty - 4 WHERE stock_qty >= 4 RETURNING ...`. This is usually simplest when modifying a single row.
2. **Lock the row during the read with `SELECT ... FOR UPDATE`** and then execute one or more related decisions/UPDATEs in the same transaction. This fits workflows that must read multiple pieces of data before writing.

Row locking is neither the only option nor always the fastest. Use it when **coordination is required across transactions that may operate on the same data**.

## 2. Plain SELECT vs. SELECT with Row Locking

A `SELECT` without a locking clause:

~~~sql
SELECT product_id, stock_qty
FROM lock_lab.products
WHERE product_id = 101;
~~~

Reads a snapshot per the isolation level and places no row-level lock like `FOR UPDATE` on the returned rows.

A `SELECT` with a locking clause:

~~~sql
SELECT product_id, stock_qty
FROM lock_lab.products
WHERE product_id = 101
FOR UPDATE;
~~~

besides returning results, requests a **row lock on the selected rows**. The lock coordinates with other transactions trying to acquire row locks or modify those rows.

Distinguish the two behaviors:

| Behavior | Plain SELECT | SELECT ... FOR UPDATE |
| --- | --- | --- |
| Reads data version via MVCC | Yes | Yes, along with locking/update semantics |
| Actively acquires row lock to coordinate writes | No | Yes |
| May wait for a writer holding a row lock | Usually no, for plain SELECT | Yes |
| Can block another writer on the locked row | Normally no | Yes |
| How long is the lock held? | No corresponding row lock | Usually until end of transaction or relevant rollback |

**Do not interpret "plain SELECT doesn't lock" as using no locks at all.** PostgreSQL still uses table-level locks such as `ACCESS SHARE` to protect structure during reads; that lock can conflict with DDL requiring `ACCESS EXCLUSIVE`. Here we focus on **row-level locks**.

## 3. The Four Lock Modes and Their Meaning

| Row lock | Primary purpose | What can other transactions do? |
| --- | --- | --- |
| `FOR UPDATE` | Protects the row when the transaction may modify or delete it in any conflicting way | Cannot acquire any of the four row locks on the same row until the lock is released |
| `FOR NO KEY UPDATE` | Protects the row for an update **that does not change relevant keys** | Still allows `FOR KEY SHARE` on the same row |
| `FOR SHARE` | Multiple readers hold a shared lock, preventing updates/deletes while held | Allows `FOR SHARE` and `FOR KEY SHARE` |
| `FOR KEY SHARE` | Protects row existence and referenced key columns | Allows `FOR KEY SHARE`, `FOR SHARE`, and `FOR NO KEY UPDATE`, but not `FOR UPDATE` |

You can view protection strength roughly along this spectrum:

~~~text
FOR UPDATE
  strongest: conflicts with every row-lock mode

FOR NO KEY UPDATE
  blocks non-key writers, share, and update;
  compatible with KEY SHARE

FOR SHARE
  multiple readers share; blocks writers modifying the row

FOR KEY SHARE
  lightest: protects keys/existence, allows non-key updates
~~~

However, this is **not a simple numeric scale** where comparing "stronger/weaker" tells you every behavior. The accurate way is to use the **conflict matrix** in the next section.

## 4. Row-Level Lock Conflict Matrix

Suppose **transaction A already holds a row lock** on a row and **transaction B requests a new lock** on that same row. Notation:

- **X:** the two locks conflict; B must wait for A to finish, or error if using `NOWAIT`.
- **✓:** the two locks are compatible at the row-lock level; B may still wait for other reasons such as table locks, transactions, DDL, or FKs.

| B requests ↓ / A holds → | `FOR KEY SHARE` | `FOR SHARE` | `FOR NO KEY UPDATE` | `FOR UPDATE` |
| --- | :---: | :---: | :---: | :---: |
| **`FOR KEY SHARE`** | ✓ | ✓ | ✓ | X |
| **`FOR SHARE`** | ✓ | ✓ | X | X |
| **`FOR NO KEY UPDATE`** | ✓ | X | X | X |
| **`FOR UPDATE`** | X | X | X | X |

The matrix is symmetric: if A conflicts with B, B also conflicts with A when holding/requesting locks on the same row.

### Four Takeaways to Remember

1. **`FOR UPDATE` conflicts with everything**, even `FOR KEY SHARE`.
2. **`FOR NO KEY UPDATE` is compatible with `FOR KEY SHARE`**, allowing operations protecting referenced keys to run alongside non-key updates.
3. **Two `FOR SHARE` locks are compatible**, allowing multiple transactions to perform shared locking reads simultaneously.
4. **`FOR SHARE` and `FOR NO KEY UPDATE` conflict**, even though both are weaker than `FOR UPDATE`.

A plain `SELECT` **does not appear in the matrix** because it acquires none of these four row locks. It can normally read a committed version while another transaction holds a row lock.

## 5. Scope and Lifetime of These Locks

A `SELECT ... FOR ...` statement must be placed inside a transaction context.

~~~sql
BEGIN;

SELECT product_id, stock_qty
FROM lock_lab.products
WHERE product_id = 101
FOR UPDATE;

-- Subsequent statements on the same connection
-- continue running inside the transaction holding the lock.

COMMIT;
~~~

Row locks are normally held until the transaction **`COMMIT`s** or **`ROLLBACK`s**. If `SELECT ... FOR UPDATE` runs with autocommit enabled and no surrounding transaction block, the lock is released as soon as the statement completes; therefore it **no longer protects** a subsequent `UPDATE` sent as a new transaction.

### Must Use the Same Connection/Session

~~~text
Connection A:
    BEGIN
    SELECT ... FOR UPDATE

Connection B:
    UPDATE ...
~~~

Connection B **does not inherit A's lock**. In a Java application, if `SELECT` locks a row on one connection while `UPDATE` runs on a second independent connection, you have broken the critical section.

For read–decide–write to be protected, the operations must stay within the **same transaction** controlled by the service or transaction manager.

### SAVEPOINT

When rolling back to a `SAVEPOINT`, PostgreSQL releases locks acquired after that savepoint according to subtransaction rollback rules. This differs from `RELEASE SAVEPOINT`, which does not end the outer transaction.

## 6. Setting Up the Lab Database and Sample Data

All examples run in a **dedicated learning PostgreSQL database**. The setup drops schema `lock_lab` if present. **Do not run this in a production database or a shared schema with data you need to keep.**

### 6.1. Creating the Schema and Tables

~~~sql
-- WARNING: run only on a lab database you own.
DROP SCHEMA IF EXISTS lock_lab CASCADE;
CREATE SCHEMA lock_lab;

CREATE TABLE lock_lab.customers (
    customer_id integer PRIMARY KEY,
    full_name text NOT NULL,
    tier text NOT NULL DEFAULT 'standard'
        CHECK (tier IN ('standard', 'silver', 'gold')),
    email text NOT NULL UNIQUE
);

CREATE TABLE lock_lab.orders (
    order_id integer PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES lock_lab.customers(customer_id),
    status text NOT NULL
        CHECK (status IN ('pending', 'paid', 'cancelled')),
    total numeric(12,2) NOT NULL CHECK (total >= 0)
);

CREATE TABLE lock_lab.products (
    product_id integer PRIMARY KEY,
    product_name text NOT NULL,
    stock_qty integer NOT NULL CHECK (stock_qty >= 0)
);

CREATE TABLE lock_lab.jobs (
    job_id integer PRIMARY KEY,
    job_type text NOT NULL,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'done', 'failed')),
    priority integer NOT NULL DEFAULT 0,
    claimed_by text,
    claimed_at timestamptz,
    attempts integer NOT NULL DEFAULT 0
        CHECK (attempts >= 0)
);

CREATE INDEX idx_lock_lab_jobs_pending
ON lock_lab.jobs (priority DESC, job_id)
WHERE status = 'pending';
~~~

Only two tables have an FK relationship: `orders` and `customers`; this is key for demonstrating `FOR KEY SHARE`. `products` supports the inventory-deduction example; `jobs` supports multi-worker `SKIP LOCKED`.

### 6.2. Loading Sample Data

~~~sql
INSERT INTO lock_lab.customers
    (customer_id, full_name, tier, email)
VALUES
    (1, 'An',   'gold',     'an@example.test'),
    (2, 'Binh', 'silver',   'binh@example.test'),
    (3, 'Chi',  'standard', 'chi@example.test');

INSERT INTO lock_lab.orders
    (order_id, customer_id, status, total)
VALUES
    (101, 1, 'pending', 120.00),
    (102, 2, 'paid',     75.00);

INSERT INTO lock_lab.products
    (product_id, product_name, stock_qty)
VALUES
    (101, 'Coffee', 10),
    (102, 'Tea',     5),
    (103, 'Cup',     0);

INSERT INTO lock_lab.jobs
    (job_id, job_type, status, priority)
VALUES
    (1001, 'send_email', 'pending', 10),
    (1002, 'create_pdf', 'pending',  7),
    (1003, 'sync_stock', 'pending',  7),
    (1004, 'cleanup',    'pending',  2);
~~~

Initial data:

| Table | Key | Sample values |
| --- | --- | --- |
| `customers` | 1 | An, tier gold |
| `customers` | 2 | Binh, tier silver |
| `customers` | 3 | Chi, tier standard, no orders yet |
| `orders` | 101 | An's pending order |
| `products` | 101 | Coffee, stock 10 |
| `jobs` | 1001–1004 | Four pending jobs, priorities 10/7/7/2 |

### 6.3. Preparing Two psql Windows

Open **two separate connections to the same database**:

- **Session A:** holds a lock inside a transaction.
- **Session B:** tries to acquire a compatible/conflicting lock or runs an `UPDATE`.

You can check each backend PID to tell them apart:

~~~sql
SELECT pg_backend_pid() AS my_pid;
~~~

Before each experiment, **end the previous experiment's transaction in both A and B**. Use `ROLLBACK` for write exercises so data returns to the initial seed. If a session errors and enters an aborted transaction state, execute `ROLLBACK` before starting the next step.

You do not need extra databases or global PostgreSQL config changes for these basic labs.

## 7. Experiment 1: FOR UPDATE Blocks Another FOR UPDATE

Goal: show that transaction B cannot acquire the strongest row lock on Coffee while A holds the lock.

**Session A:**

~~~sql
BEGIN;

SELECT product_id, product_name, stock_qty
FROM lock_lab.products
WHERE product_id = 101
FOR UPDATE;

-- A keeps the transaction open; switch to B.
~~~

**Session B — try NOWAIT so it does not hang waiting:**

~~~sql
BEGIN;

SELECT product_id, stock_qty
FROM lock_lab.products
WHERE product_id = 101
FOR UPDATE NOWAIT;

-- Expected error 55P03 (lock_not_available)
-- while A holds FOR UPDATE on the same row.

ROLLBACK;
~~~

The `NOWAIT` error puts transaction B into an aborted state requiring rollback. `NOWAIT` keeps the example from hanging indefinitely; it **does not mean the lock was acquired successfully**.

**Session A finishes:**

~~~sql
ROLLBACK;
~~~

Now a `SELECT ... FOR UPDATE NOWAIT` in a new transaction can acquire the lock on product 101 provided no other session holds a conflicting lock.

### FOR UPDATE Does Not Block Plain SELECT

While A still holds `FOR UPDATE`, another session can run:

~~~sql
SELECT product_id, stock_qty
FROM lock_lab.products
WHERE product_id = 101;
~~~

and still read the committed value via its snapshot. This is how **MVCC for plain SELECT** works alongside **row locks for operations needing synchronization**.

## 8. Experiment 2: FOR UPDATE Blocks UPDATE

**Session A:**

~~~sql
BEGIN;

SELECT stock_qty
FROM lock_lab.products
WHERE product_id = 101
FOR UPDATE;
~~~

**Session B:**

~~~sql
BEGIN;
SET LOCAL lock_timeout = '1s';

UPDATE lock_lab.products
SET stock_qty = stock_qty - 2
WHERE product_id = 101
  AND stock_qty >= 2
RETURNING product_id, stock_qty;

-- If A has not released the lock:
-- B waits, then receives error 55P03 due to lock_timeout.

ROLLBACK;
~~~

**Session A:**

~~~sql
ROLLBACK;
~~~

`UPDATE` needs a row lock to modify the tuple. Even though B only modifies `stock_qty` and does not change the `product_id` key, it still conflicts with A's `FOR UPDATE`.

### Why Use SET LOCAL lock_timeout?

`SET LOCAL lock_timeout = '1s'` applies only to the current transaction; once the transaction ends, it no longer applies. It bounds lock wait time in the example without altering settings for all sessions.

Do not confuse:

- `lock_timeout`: limits wait time to **acquire a lock**.
- `statement_timeout`: limits duration of the **entire statement**.

In production, pick timeouts based on SLA and transaction type; do not treat 1 second as a universal default for every system.

## 9. FOR NO KEY UPDATE: Locking a Non-Key Update

`FOR NO KEY UPDATE` is close to `FOR UPDATE` but weaker in one crucial respect: it **does not conflict with `FOR KEY SHARE`**.

For example, A intends to update a customer's tier without changing `customer_id`:

**Session A:**

~~~sql
BEGIN;

SELECT customer_id, full_name, tier
FROM lock_lab.customers
WHERE customer_id = 1
FOR NO KEY UPDATE;

-- Keep the transaction open.
~~~

**Session B:**

~~~sql
BEGIN;

SELECT customer_id, full_name
FROM lock_lab.customers
WHERE customer_id = 1
FOR KEY SHARE NOWAIT;

-- Succeeds per the matrix,
-- because FOR KEY SHARE is compatible with FOR NO KEY UPDATE.

ROLLBACK;
~~~

**Session A:**

~~~sql
ROLLBACK;
~~~

Although both sessions hold row locks, their intents differ:

- A wants to protect its ability to update **non-key attributes**.
- B only needs to ensure the parent row and referenced key are not deleted or modified in a conflicting way.

Because those two intents do not clash, PostgreSQL allows both to proceed.

### Yet FOR NO KEY UPDATE Still Blocks Another Non-Key Writer

If A holds `FOR NO KEY UPDATE` on customer 1, and transaction B tries:

~~~sql
UPDATE lock_lab.customers
SET tier = 'silver'
WHERE customer_id = 1;
~~~

then B must acquire a row lock for `UPDATE` and will be blocked. Two writers cannot concurrently modify the same row merely because neither changes a key.

## 10. Why Does the Name "NO KEY UPDATE" Matter for Foreign Keys?

A row in `customers` can be referenced by many rows in `orders` via a foreign key:

~~~sql
customer_id integer
    REFERENCES lock_lab.customers(customer_id)
~~~

When creating an order referencing customer 1, PostgreSQL must ensure that customer row is not deleted or altered in a way that invalidates the FK during validation. This mechanism uses a **`FOR KEY SHARE`**-level row lock on the parent row.

If another transaction only updates `tier` from gold to silver, a strong lock like `FOR UPDATE` is unnecessary. `FOR NO KEY UPDATE` is designed to be compatible with `FOR KEY SHARE`, letting **non-key attribute updates** run concurrently with **FK protection**.

~~~mermaid
flowchart TD
    A["Customer 1"] --> B["UPDATE tier (no key change)"]
    A --> C["INSERT order referencing customer_id=1"]
    B --> D["FOR NO KEY UPDATE"]
    C --> E["FK check / KEY SHARE"]
    D --> F["Both row lock modes are compatible"]
    E --> F
~~~

This is a major practical benefit of having **multiple lock modes instead of a single exclusive lock**.

**Caveat:** exact FK execution details also depend on the SQL statement, triggers, constraints, and concurrency; compatibility of two row locks does not promise the whole statement will never wait on any other resource.

## 11. Which Row Lock Do UPDATE and DELETE Acquire Automatically?

PostgreSQL does not require developers to always run `SELECT ... FOR ...` before modifying data. DML statements **automatically acquire the appropriate row lock**.

### An UPDATE That Does Not Change Keys Uses FOR NO KEY UPDATE Level

Example:

~~~sql
UPDATE lock_lab.customers
SET tier = 'silver'
WHERE customer_id = 1;
~~~

This updates `tier` without changing identifier key `customer_id`, so it falls into the normal `UPDATE` category with row-locking strength equivalent to `FOR NO KEY UPDATE`.

### An UPDATE That Modifies Relevant Keys Uses FOR UPDATE Level

~~~sql
UPDATE lock_lab.customers
SET customer_id = 30
WHERE customer_id = 3;
~~~

The primary key changes; PostgreSQL needs the strong mode to coordinate with transactions holding `FOR KEY SHARE` on that row.

Since customer 3 has no orders in the lab, this statement can execute if no conflicting locks exist; wrap it in `BEGIN ... ROLLBACK` when testing.

### DELETE Uses the Strongest Level

~~~sql
DELETE FROM lock_lab.customers
WHERE customer_id = 3;
~~~

`DELETE` threatens the parent row's existence, so it conflicts with `FOR KEY SHARE` and other modes—equivalent in row-lock conflict terms to `FOR UPDATE`.

### What Counts as a "Key" in an UPDATE?

Under PostgreSQL's rules, an `UPDATE` is considered a key update if it modifies columns belonging to a **unique index that can be used by a foreign key**. Partial and expression indexes are excluded from that determination. This does **not** mean any column the application happens to name "key" automatically triggers the strong lock.

Keep the practical rules in mind:

- Modifying ordinary data columns like `tier`, `status`, or `note` → normally a non-key update.
- Modifying a primary key or unique column eligible for FK references → may require `FOR UPDATE`-level protection.
- `DELETE` → requires strong protection because the row may disappear.

## 12. FOR SHARE: Multiple Readers Holding a Shared Lock

`FOR SHARE` is used when a transaction wants to **read a row and prevent other transactions from updating or deleting it**, while still allowing other transactions to acquire shared locks.

**Session A:**

~~~sql
BEGIN;

SELECT customer_id, full_name, tier
FROM lock_lab.customers
WHERE customer_id = 2
FOR SHARE;
~~~

**Session B:**

~~~sql
BEGIN;

SELECT customer_id, full_name, tier
FROM lock_lab.customers
WHERE customer_id = 2
FOR SHARE NOWAIT;

-- Succeeds per the matrix: SHARE and SHARE are compatible.

ROLLBACK;
~~~

**Session A:**

~~~sql
ROLLBACK;
~~~

### FOR SHARE Blocks Non-Key UPDATEs

Try again with A holding `FOR SHARE`; B runs:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '1s';

UPDATE lock_lab.customers
SET tier = 'gold'
WHERE customer_id = 2;

-- Times out because A holds FOR SHARE.

ROLLBACK;
~~~

Because `FOR SHARE` conflicts with `FOR NO KEY UPDATE`, B cannot modify the row while A holds the shared lock.

### FOR SHARE Is Not the Same as Plain SELECT

A read-only report that does not depend on the row staying unchanged after `SELECT` usually **does not need `FOR SHARE`**. If many reports casually take `SHARE` and hold transactions open, writers are blocked unnecessarily.

Use `FOR SHARE` only when the transaction genuinely requires **a guarantee that the read row is not updated** during a subsequent business step—not simply because the name sounds like "reading."

## 13. FOR KEY SHARE: Protecting the Key Without Locking Every Attribute

`FOR KEY SHARE` is the weakest of the four row locks.

**Session A:**

~~~sql
BEGIN;

SELECT customer_id
FROM lock_lab.customers
WHERE customer_id = 3
FOR KEY SHARE;
~~~

**Session B — updating an ordinary column:**

~~~sql
BEGIN;
SET LOCAL lock_timeout = '1s';

UPDATE lock_lab.customers
SET tier = 'gold'
WHERE customer_id = 3
RETURNING customer_id, tier;

-- Succeeds because a non-key UPDATE
-- is compatible with FOR KEY SHARE.

ROLLBACK;
~~~

**Session A:**

~~~sql
ROLLBACK;
~~~

A requested to keep customer ID 3 and its identifier key stable, **without blocking changes to `tier`**. B can update `tier` without violating that guarantee.

### FOR KEY SHARE Blocks DELETE and Key Changes

While A still holds `FOR KEY SHARE`:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '1s';

DELETE FROM lock_lab.customers
WHERE customer_id = 3;

-- Waits and hits lock_timeout.

ROLLBACK;
~~~

Likewise, changing `customer_id` on the same row is blocked because modifying the key is a conflicting operation.

**Do not confuse KEY SHARE with SHARE:** `FOR SHARE` blocks normal updates, whereas `FOR KEY SHARE` generally allows updates to non-key columns.

## 14. Summary of All Four Modes Through One Scenario

Suppose transaction A holds a lock on customer 1. Session B tries one of: plain read, locking read, updating `tier`, changing `customer_id`, or deleting the row.

| A's lock | B plain SELECT | B FOR KEY SHARE | B FOR SHARE | B UPDATE tier | B DELETE |
| --- | --- | --- | --- | --- | --- |
| `FOR UPDATE` | Usually reads | Waits | Waits | Waits | Waits |
| `FOR NO KEY UPDATE` | Usually reads | Allowed | Waits | Waits | Waits |
| `FOR SHARE` | Usually reads | Allowed | Allowed | Waits | Waits |
| `FOR KEY SHARE` | Usually reads | Allowed | Allowed | Usually allowed | Waits |

**"Allowed" in the table reflects row-lock compatibility only**; it does not guarantee freedom from other locks, constraints, or snapshot changes. `UPDATE tier` assumes a non-key update under the sample schema.

The key row to remember: if you only need to protect a referenced key during an FK check, **`FOR KEY SHARE` allows higher concurrency than `FOR SHARE` or `FOR UPDATE`**.

## 15. When Does FOR NO KEY UPDATE Differ from FOR UPDATE?

This is a frequent question because both modes can protect an update step.

Suppose an application reads an account and will update its `status` without altering its identifier key. Some developers default to:

~~~sql
SELECT customer_id, tier
FROM lock_lab.customers
WHERE customer_id = 1
FOR UPDATE;
~~~

This locks strongly, blocking even another transaction that only needs `FOR KEY SHARE` for an FK check.

If the operation only needs to lock for updating non-key columns:

~~~sql
SELECT customer_id, tier
FROM lock_lab.customers
WHERE customer_id = 1
FOR NO KEY UPDATE;
~~~

it still conflicts with other non-key writers and `FOR SHARE`, while staying **compatible with KEY SHARE**, avoiding unnecessary waits.

### Do Not Downgrade Locks Just to Be "Faster"

If the transaction actually deletes the row or alters a key column, another transaction's `FOR KEY SHARE` has a valid reason to be protected. Using an insufficiently strong lock or basing workflow logic on wrong assumptions can lead to later waits, deadlocks, or broken application invariants.

Choose the mode based on **the intended action and business invariants**, not a blind "weakest is fastest" rule.

## 16. NOWAIT: Failing Fast Instead of Waiting for a Row Lock

Syntax:

~~~sql
SELECT *
FROM lock_lab.jobs
WHERE job_id = 1001
FOR UPDATE NOWAIT;
~~~

If a conflicting row lock exists, PostgreSQL raises `lock_not_available`, SQLSTATE **`55P03`**, instead of waiting for the lock to be released.

Use `NOWAIT` when:

- An API needs to respond quickly with "busy, please retry."
- A worker should not wait on an item already being processed.
- The task can be deferred or re-queued.
- You want to demonstrate lock contention in a lab without hanging sessions.

### NOWAIT Does Not Guarantee Every Step Is Instant

`NOWAIT` in a locking clause applies to the associated **row-level locks**. The statement still acquires required table-level locks normally and can wait on a table-level conflict.

If a specialized workflow also cannot wait on table-level locks, it may need `LOCK TABLE ... NOWAIT` or an appropriate `lock_timeout`. Do not assume adding `FOR UPDATE NOWAIT` makes every phase of a query non-blocking.

## 17. SKIP LOCKED: Skipping Rows Locked by Other Workers

`SKIP LOCKED` lets a worker **skip** rows for which it cannot immediately acquire a row lock due to a conflicting lock held by another session.

~~~sql
SELECT job_id, job_type, priority
FROM lock_lab.jobs
WHERE status = 'pending'
ORDER BY priority DESC, job_id
LIMIT 1
FOR UPDATE SKIP LOCKED;
~~~

If job 1001 is locked by worker A, worker B picks job 1002 or another pending job, depending on visible rows and the query plan.

### Why Is It Suitable for Queues?

In a job table, two workers usually do not want to wait on each other just to fight over **the same job**. Worker B can simply process the next job.

~~~mermaid
flowchart LR
    J["Pending jobs: 1001, 1002, 1003"] --> A["Worker A: lock 1001"]
    J --> B["Worker B: SKIP LOCKED"]
    B --> C["Skip locked 1001"]
    C --> D["Lock 1002"]
~~~

### Why Is It Unsuitable for Accurate Reports?

`SKIP LOCKED` intentionally yields an **incomplete** view of the rows—currently locked rows vanish temporarily from the result set. Never use it to determine:

- How many pending orders exist across the system.
- Every customer requiring an audit.
- Exact totals across all matching rows.

It is meant for **work distribution across multiple consumers**, not as a general trick to "avoid locks in every SELECT."

## 18. Two-Worker Experiment with SKIP LOCKED

After resetting `jobs` to the seed data, run in **two sessions**.

**Session A:**

~~~sql
BEGIN;

SELECT job_id, priority
FROM lock_lab.jobs
WHERE status = 'pending'
ORDER BY priority DESC, job_id
LIMIT 1
FOR UPDATE SKIP LOCKED;

-- Result: job 1001 (priority 10).
-- Keep transaction A open.
~~~

**Session B:**

~~~sql
BEGIN;

SELECT job_id, priority
FROM lock_lab.jobs
WHERE status = 'pending'
ORDER BY priority DESC, job_id
LIMIT 1
FOR UPDATE SKIP LOCKED;

-- While 1001 is locked by A, B picks job 1002.

ROLLBACK;
~~~

**Session A:**

~~~sql
ROLLBACK;
~~~

Because both sessions rolled back without changing status, all jobs remain pending. B received 1002 in the example because job 1001 was locked by A, not because it had been committed as `running`.

### A Note on Fairness

`SKIP LOCKED` does not guarantee strict FIFO fairness or starvation prevention. A repeatedly locked row can be skipped by workers, or high-priority jobs may wait behind other business conditions. Real queue systems require lease deadlines, retries, timeouts, metrics, and stuck-job recovery.

## 19. Atomically Claiming a Job with CTE + UPDATE

Merely running `SELECT ... FOR UPDATE SKIP LOCKED` and closing the transaction is **not enough** for a worker to own a job persistently. Once committed or rolled back, the lock is released; another worker could pick the same job again if `status` has not changed.

A common pattern is **selecting and marking as `running` in the same transaction**:

~~~sql
BEGIN;

WITH picked AS (
    SELECT job_id
    FROM lock_lab.jobs
    WHERE status = 'pending'
    ORDER BY priority DESC, job_id
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
UPDATE lock_lab.jobs AS j
SET
    status = 'running',
    claimed_by = 'worker-A',
    claimed_at = clock_timestamp(),
    attempts = attempts + 1
FROM picked AS p
WHERE j.job_id = p.job_id
  AND j.status = 'pending'
RETURNING
    j.job_id,
    j.job_type,
    j.status,
    j.claimed_by,
    j.attempts;

COMMIT;
~~~

Step by step:

1. CTE `picked` finds one pending job and acquires `FOR UPDATE SKIP LOCKED` as it selects it.
2. `UPDATE` transitions the chosen job to `running`.
3. `RETURNING` returns **the exact claimed job** for the worker to process.
4. `COMMIT` persists the claim; once the lock is released, other transactions will no longer pick this job because `status <> 'pending'`.

If no eligible job exists, `RETURNING` returns 0 rows. The worker can sleep or poll again on schedule—it is not an SQL error.

**Post-commit risk:** if the worker crashes right after claiming the job but before finishing, the job remains stuck in `running`. A production system needs **lease deadlines/heartbeats, retries with backoff, idempotency**, and safe recovery to re-queue failed jobs. A transaction-scoped row lock does not replace post-commit recovery.

## 20. OF table_alias: Locking the Right Table in a JOIN

A `JOIN` query can read multiple tables:

~~~sql
SELECT
    o.order_id,
    o.status,
    c.full_name
FROM lock_lab.orders AS o
JOIN lock_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.order_id = 101
FOR UPDATE;
~~~

Without `OF`, the locking clause applies to **all eligible base tables referenced** in the query. Thus the query above locks rows in both `orders` and `customers`, creating unnecessary contention.

If you only want to lock **the order**, and `customers` is only for displaying the name:

~~~sql
SELECT
    o.order_id,
    o.status,
    c.full_name
FROM lock_lab.orders AS o
JOIN lock_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.order_id = 101
FOR UPDATE OF o;
~~~

`FOR UPDATE OF o` requests row locks only on table reference `o`, without applying the locking clause to rows of `c`.

### When You Truly Need Two Different Lock Levels

You can write multiple locking clauses with explicit targets:

~~~sql
SELECT
    o.order_id,
    c.customer_id,
    c.full_name
FROM lock_lab.orders AS o
JOIN lock_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.order_id = 101
FOR UPDATE OF o
FOR KEY SHARE OF c;
~~~

Here:

- The order is locked strongly because it may be modified.
- The customer only needs key/existence protection when the transaction relies on the FK.

If a table is given an alias, use **that alias** in `OF`. Applying multiple locking clauses to the same table resolves to the strongest applicable mode.

### LEFT JOIN Limitation

You cannot always lock the **nullable** side of an outer join; PostgreSQL restricts locking clauses on the nullable side of an outer join. In such cases, restructure the query or lock only the valid side using `OF`.

## 21. CTEs and Lock Scope

Locks are acquired wherever the locking clause actually applies. If using a CTE to pick a set of rows to lock, place the locking clause **inside the CTE**:

~~~sql
WITH chosen AS (
    SELECT job_id
    FROM lock_lab.jobs
    WHERE status = 'pending'
    ORDER BY priority DESC, job_id
    LIMIT 2
    FOR UPDATE SKIP LOCKED
)
SELECT job_id
FROM chosen;
~~~

A `FOR UPDATE` on the **outer query** does not automatically apply inside referenced CTEs the way a writer might assume.

In the queue pipeline in Section 19, putting `FOR UPDATE SKIP LOCKED` inside `picked` is intentional: the row is locked **as it is selected** so multiple workers do not claim the same one.

### Do Not Place Locking Clauses in Invalid Positions

Locking clauses have restrictions in queries with `DISTINCT`, `GROUP BY`, set operations, and result forms that do not map directly to a concrete source row. For example, do not expect this to work:

~~~sql
-- Not the right way to lock individual source rows:
SELECT status, COUNT(*)
FROM lock_lab.jobs
GROUP BY status
FOR UPDATE;
~~~

To lock source rows before aggregating, you typically split steps or use a CTE over valid source rows. First ask the business question: **why lock just to count?** For reporting, an MVCC snapshot is usually far better.

## 22. READ COMMITTED: Locks Can Wait and Re-Evaluate the Row

Suppose session B is updating job 1001 from `pending` to `running` and has not committed yet. Session A runs:

~~~sql
SELECT job_id, status
FROM lock_lab.jobs
WHERE job_id = 1001
  AND status = 'pending'
FOR UPDATE;
~~~

Under `READ COMMITTED`, if `SELECT ... FOR UPDATE` encounters a row currently updated by another transaction, it **waits** for that transaction. Once the writer commits, PostgreSQL inspects the updated row version and re-evaluates the `WHERE` predicate under isolation rules.

If the post-commit status is `running`, the row will **no longer be returned** because `status = 'pending'` no longer holds.

Therefore:

- `SELECT ... FOR UPDATE` does not guarantee returning every row that matched the condition before waiting.
- A row may be dropped if another transaction changed it so it no longer satisfies the predicate.
- Applications must handle a 0-row result as a valid concurrency outcome.

This is also why workflows often re-check state inside the `UPDATE` condition itself.

## 23. REPEATABLE READ and SERIALIZABLE Can Error Instead of Re-Updating

Under `REPEATABLE READ`, the snapshot is fixed for the transaction. If the transaction tries to lock or update a row modified by another transaction since that snapshot, PostgreSQL raises an error like:

~~~text
ERROR: could not serialize access due to concurrent update
SQLSTATE: 40001
~~~

This differs from `READ COMMITTED`, where an `UPDATE` can wait and re-evaluate against the newly committed version.

### What to Do When Encountering 40001?

Typically you must:

1. `ROLLBACK` the failed transaction.
2. Start a **new** transaction.
3. Re-read the data and re-make decisions on the fresh snapshot.
4. Repeat the write if business logic permits.
5. Enforce retry limits and backoff to avoid infinite loops.

**Do not retry only the final UPDATE statement** if earlier decisions depended on `SELECT`s read from the stale snapshot.

`SERIALIZABLE` detects additional logical read-write conflicts across transactions and aborts a transaction to preserve serializability. Row locks help coordinate, but **do not replace** the guarantees and retry requirements of stricter isolation levels.

## 24. Deadlocks: Locking Rows in Opposite Order

Locks can cause a **deadlock** when two transactions wait on each other in a cycle.

Consider two logical items A and B stored in `products`.

**Session A:**

~~~sql
BEGIN;

SELECT product_id
FROM lock_lab.products
WHERE product_id = 101
FOR UPDATE;

-- A now holds the lock on product 101.
~~~

**Session B:**

~~~sql
BEGIN;

SELECT product_id
FROM lock_lab.products
WHERE product_id = 102
FOR UPDATE;

-- B now holds the lock on product 102.
~~~

Now:

**Session A requests B's row:**

~~~sql
SELECT product_id
FROM lock_lab.products
WHERE product_id = 102
FOR UPDATE;

-- A waits for B.
~~~

**Session B requests A's row:**

~~~sql
SELECT product_id
FROM lock_lab.products
WHERE product_id = 101
FOR UPDATE;

-- B waits for A: deadlock cycle created.
~~~

PostgreSQL runs deadlock detection and aborts one transaction with SQLSTATE **`40P01`** to break the cycle. The aborted transaction must roll back; the surviving transaction proceeds once locks are released.

### Reducing Deadlocks with Consistent Lock Ordering

If all code paths lock multiple products in **ascending `product_id` order**, wait-cycle risk drops sharply:

~~~sql
SELECT product_id
FROM lock_lab.products
WHERE product_id IN (101, 102)
ORDER BY product_id
FOR UPDATE;
~~~

Lock ordering should be consistent across related execution paths, including triggers/FKs and multiple tables. `ORDER BY` in a single query is helpful, though not a guarantee that deadlocks can never occur elsewhere.

Additional recommendations:

- Keep transactions short.
- Avoid network API calls while holding locks whenever possible.
- Acquire locks in consistent order across services.
- Avoid locking more rows/tables than needed.
- Implement safe full-transaction retries on `40P01`.

## 25. Lock Timeouts Differ from Deadlocks

Both errors fail a statement, yet their causes differ:

| SQLSTATE | Situation | Approach |
| --- | --- | --- |
| `55P03` | Lock not available due to `NOWAIT` or `lock_timeout` | Return busy, wait/retry with control, or pick other work |
| `40P01` | Deadlock detected | Roll back and retry the transaction per policy |
| `40001` | Serialization failure | Retry the entire transaction on a new snapshot |
| `57014` | Statement canceled, e.g., `statement_timeout` or user cancel | Investigate cause; do not treat automatically as a lock conflict |

**Do not retry every SQL error identically.** Especially if a transaction caused external side effects outside PostgreSQL, ensure idempotency and reconciliation before retrying.

## 26. Observing Blocked Sessions

Use a **Session C** to diagnose while A and B run experiments.

### 26.1. Who Is Waiting and Who Is Blocking?

~~~sql
SELECT
    pid,
    usename,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids,
    left(query, 160) AS query_snippet
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
ORDER BY pid;
~~~

A session blocked by a row lock typically shows `wait_event_type = 'Lock'` and a `wait_event` related to transaction IDs or another lock type. Do not search only for a fixed string like `tuple`: row locks and transaction waits appear through different metadata types.

`pg_blocking_pids(pid)` identifies the PIDs blocking the inspected transaction.

### 26.2. Inspecting Table-Level Locks

~~~sql
SELECT
    pid,
    locktype,
    mode,
    granted,
    relation::regclass AS relation_name
FROM pg_locks
WHERE relation = 'lock_lab.products'::regclass
ORDER BY pid, granted, mode;
~~~

You will see relation-level locks such as `RowShareLock` and `RowExclusiveLock` associated with statements accessing the table.

**Important:** not every held row lock appears explicitly as a `locktype='tuple'` row in `pg_locks`. Row lock state is also stored in tuple metadata on disk; when waiting, a session often waits for another transaction to finish. Therefore, combining `pg_stat_activity`, `pg_blocking_pids`, and `pg_locks` is far more informative than searching `pg_locks` alone for all row locks.

### 26.3. Do Not Blindly Terminate Sessions in Production

A long transaction may be running a migration, report, or critical business workflow. Never run `pg_terminate_backend` just because a PID has been waiting long without checking owner, impact, and rollback consequences.

## 27. Table-Level Locks Accompanied by Row-Level Locking Clauses

When using:

~~~sql
SELECT *
FROM lock_lab.products
WHERE product_id = 101
FOR UPDATE;
~~~

PostgreSQL also acquires a relation-level **`ROW SHARE`** lock on tables subject to the locking clause. Conversely, `UPDATE` acquires table-level **`ROW EXCLUSIVE`** alongside row locks for modified rows.

The names `ROW SHARE`/`ROW EXCLUSIVE` are confusing because they are **table-level lock modes**, not row-level `FOR SHARE` and `FOR UPDATE`.

| Lock type | Example | Scope |
| --- | --- | --- |
| Table-level `ACCESS SHARE` | Plain `SELECT` | Relation/table |
| Table-level `ROW SHARE` | `SELECT FOR UPDATE/SHARE` | Relation/table |
| Table-level `ROW EXCLUSIVE` | `UPDATE`/`INSERT`/`DELETE` | Relation/table |
| Row-level `FOR UPDATE` | `SELECT ... FOR UPDATE` | Locked rows |

Therefore:

- Two plain `SELECT`s do not block each other over row locks.
- A `SELECT FOR UPDATE` can wait on DDL even when no writer touches the same row.
- `NOWAIT` on a locking clause does not bypass every table-level lock conflict.

When analyzing a lock-induced slowdown, always ask **whether it is waiting on a row lock or a table lock**, never conflate the two.

## 28. Row Locks Do Not Protect Non-Existent Rows

Suppose two requests concurrently try to create a customer with email `new@example.test`.

One transaction runs:

~~~sql
SELECT customer_id
FROM lock_lab.customers
WHERE email = 'new@example.test'
FOR UPDATE;
~~~

If **no matching row exists**, the query returns 0 rows and **no tuple is locked**. Another transaction can still try to `INSERT` that email.

Thus, the pattern:

~~~text
SELECT ... WHERE email=? FOR UPDATE;
If not found, INSERT ...
~~~

is **insufficient** as the primary guard against duplicates. PostgreSQL does not automatically create "gap locks on non-existent values" the way developers might expect from some other database engines.

### The Right Way to Enforce Uniqueness

The `customers` table has `UNIQUE(email)`, so rely on the constraint and `INSERT ... ON CONFLICT` or handle unique violations cleanly:

~~~sql
INSERT INTO lock_lab.customers
    (customer_id, full_name, email)
VALUES
    (10, 'New', 'new@example.test')
ON CONFLICT (email) DO NOTHING
RETURNING customer_id;
~~~

If two sessions insert concurrently, PostgreSQL coordinates through the unique index so two rows with the same email cannot both commit.

**Row locks protect existing rows; unique constraints protect key uniqueness under concurrent `INSERT`s.** The two mechanisms serve different goals.

## 29. Row Locks Do Not Automatically Protect All Multi-Row Invariants

Suppose the application requires the combined stock of two products never to drop below a threshold, or at least one employee to remain on shift.

Two transactions can lock and modify **two different rows**, each reading a snapshot and deciding based on the other row. Without a write conflict on the same row, **write skew** can occur under certain isolation levels.

Solutions may include:

- Locking the **entire relevant set of rows** consistently.
- Introducing a parent/coordination row to lock per business invariant.
- Using constraints that express the invariant directly.
- Using `SERIALIZABLE` and retrying transactions when needed.
- Adjusting the data model so writes enforcing an invariant contend on a clear shared key.

Do not assume that **putting one `SELECT FOR UPDATE` somewhere makes the entire transaction serializable**. Proving correctness requires knowing **which rows are read, which are locked, which are modified, and what concurrent transactions can interleave**.

## 30. Row Locks Are Not Advisory Locks

PostgreSQL also supports **advisory locks** so applications can lock arbitrary logical keys, e.g., `pg_advisory_xact_lock(...)`. They differ from row locks:

| Property | Row-level `FOR ...` | Advisory lock |
| --- | --- | --- |
| Tied to a table row | Yes | Not required |
| Automatically used by PostgreSQL for `UPDATE`/FK | Yes | Not automatic |
| Can lock something with no existing row | No, since no tuple exists | Yes, can lock an application-chosen logical key |
| Requires application-wide lock convention | Less so for row data | Yes |
| When to use | Prevent contention on existing rows | Coordinate a logical resource or custom workflow |

Advisory locks do not replace `UNIQUE`, FKs, or row locks for every case. They are handy when no concrete row exists to lock, provided you manage lock scope, deadlocks, connection pooling, and release rules.

This lesson focuses on the **four row-level locking modes** and avoids advisory locks in the lab to keep the two mechanisms separate.

## 31. Filtering, Ordering, and Which Rows Get Locked

A `SELECT` with a locking clause locks rows according to its execution plan and PostgreSQL's locking rules. Do not assume the number of locked rows always equals the exact number of rows returned on screen in every complex query.

### LIMIT

~~~sql
SELECT job_id
FROM lock_lab.jobs
WHERE status = 'pending'
ORDER BY priority DESC, job_id
LIMIT 1
FOR UPDATE;
~~~

In this query style, locking stops once `LIMIT` rows have been returned, making it suitable for picking a single job. Still, understand plan/scan details when joins, subqueries, `OFFSET`, or concurrent updates are involved.

### OFFSET

Rows skipped by `OFFSET` can still get locked during a locking query. Do not use a large `OFFSET` assuming only the returned rows are locked.

### ORDER BY and READ COMMITTED

Under `READ COMMITTED`, an `ORDER BY ... FOR UPDATE` query can sometimes **return rows out of the newest sorted order** if it waits on a row lock and sort columns change while waiting. PostgreSQL documents this behavior and workarounds, though workarounds can broaden locking scope.

For queues, use a deterministic tie-breaker (`ORDER BY priority DESC, job_id`), keep transactions short, and accept that concurrent workers may slightly reorder claim timestamps.

## 32. Never Hold Locks During Slow Network Service Calls

An anti-pattern:

~~~text
BEGIN;
SELECT order_id FROM orders WHERE order_id=? FOR UPDATE;
Call payment API for 30 seconds;
Wait for callback;
UPDATE orders;
COMMIT;
~~~

Throughout the API wait, the transaction holds the row lock, blocking other transactions and increasing latency, timeouts, and deadlock risk.

Depending on business needs, design instead:

1. Write a `processing`/claimed state to the database and commit early.
2. Call the external service using an idempotency key.
3. In a new transaction, record the result and update state cleanly.
4. Write an outbox event for downstream steps.
5. Build retry/reconciliation for ambiguous API outcomes.

This multi-step workflow is more complex, yet far safer operationally than holding a row lock across an unbounded network request.

## 33. Reading and Locking via JDBC

In Java with pgJDBC, keep the locking read and `UPDATE` **in the same transaction on the same connection**.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class ProductStockService {

    public static boolean deduct(
        Connection connection,
        int productId,
        int requested
    ) throws SQLException {
        if (requested <= 0) {
            throw new IllegalArgumentException(
                "requested must be positive"
            );
        }

        // Assumes connection belongs to a caller/service-managed
        // transaction (autoCommit = false).
        String readSql = """
            SELECT stock_qty
            FROM lock_lab.products
            WHERE product_id = ?
            FOR UPDATE
            """;

        String updateSql = """
            UPDATE lock_lab.products
            SET stock_qty = stock_qty - ?
            WHERE product_id = ?
              AND stock_qty >= ?
            RETURNING stock_qty
            """;

        try (PreparedStatement read =
                 connection.prepareStatement(readSql)) {
            read.setInt(1, productId);

            try (ResultSet rs = read.executeQuery()) {
                if (!rs.next() || rs.getInt("stock_qty") < requested) {
                    return false;
                }
            }
        }

        try (PreparedStatement update =
                 connection.prepareStatement(updateSql)) {
            update.setInt(1, requested);
            update.setInt(2, productId);
            update.setInt(3, requested);

            try (ResultSet rs = update.executeQuery()) {
                return rs.next();
            }
        }
    }
}
~~~

This example deliberately shows that the locking read **retains its guarantee** while the connection maintains the same transaction. The `UPDATE ... WHERE stock_qty >= ?` re-checks the condition defensively.

**Applicable optimization:** if you only need to deduct stock on one row, a conditional `UPDATE` with `RETURNING` **without a prior `SELECT FOR UPDATE`** is often sufficient. Use a locking read when multiple decisions or writes depend on the read columns, not simply out of habit.

### Transaction Boundaries in the Service Layer

~~~java
boolean oldAutoCommit = connection.getAutoCommit();

try {
    connection.setAutoCommit(false);

    boolean success = ProductStockService.deduct(
        connection, 101, 3
    );

    if (success) {
        connection.commit();
    } else {
        connection.rollback();
    }
} catch (SQLException ex) {
    connection.rollback();
    throw ex;
} finally {
    connection.setAutoCommit(oldAutoCommit);
}
~~~

This illustrates a **connection directly owned by this code**. If the application uses Spring/Hibernate or a transaction manager, let the framework manage transaction boundaries; never toggle autocommit on a shared connection without a clear contract.

### Handling SQLSTATE

~~~java
try {
    // SELECT ... FOR UPDATE NOWAIT or DML.
} catch (SQLException ex) {
    String state = ex.getSQLState();

    if ("55P03".equals(state)) {
        // lock_not_available: return busy or controlled retry.
    } else if ("40P01".equals(state)) {
        // deadlock_detected: roll back, consider retrying transaction.
    } else if ("40001".equals(state)) {
        // serialization_failure: retry entire transaction.
    }

    throw ex;
}
~~~

After an error, the PostgreSQL transaction is aborted. Roll back or roll back to a valid savepoint before continuing.

## 34. Performance, WAL, and the Cost of Row Locking

Row-level locking is not free:

- There is overhead to check/acquire locks and contention under high concurrency.
- Locks add latency to competing transactions.
- `SELECT ... FOR UPDATE` can force PostgreSQL to **write lock metadata into tuples on disk** and generate WAL records, even when no business column value changes.
- Long-held locks stall other transactions, raising transaction age and operational pressure.
- Locking many rows across concurrent transactions increases deadlock probability.

If the goal is purely reporting or reading data, **plain MVCC `SELECT`s** are usually far more suitable.

### What to Monitor Before Optimizing

- Lock-wait rates and wait durations.
- `pg_blocking_pids` and `pg_stat_activity.wait_event`.
- Frequency of `55P03`, `40P01`, and `40001`.
- Long transactions and `idle in transaction` sessions.
- Number of rows matched and locked by locking queries.
- Number of workers contending on a single hot job/row.
- Query plans and indexes to locate target rows without broad scans.

An index on filter predicates (such as `job_id` or `status + priority`) lowers row-lookup cost, though it does not make row locks conflict-free. Distinguish **queries slow due to row scanning** from **queries slow due to lock waits**.

## 35. Common Mistakes

### 35.1. Thinking SELECT FOR UPDATE Blocks Plain SELECT

Readers can still read matching tuples under MVCC. `FOR UPDATE` conflicts with other locking reads and writes, not plain readers.

### 35.2. Forgetting Transactions and Using Autocommit

The lock is released as soon as the statement ends; a subsequent `UPDATE` in a new transaction is no longer protected by the earlier lock.

### 35.3. Acquiring the Lock on Connection A, Writing on Connection B

Two connections do not share a transaction. Keep the locking read and dependent writes in the same transaction on the same connection.

### 35.4. Using FOR UPDATE When FOR NO KEY UPDATE Suffices

A stronger lock unnecessarily blocks transactions that only need `KEY SHARE` for FK checks. Pick the right level of protection.

### 35.5. Confusing FOR KEY SHARE with FOR SHARE

`KEY SHARE` permits non-key `UPDATE`s; `SHARE` conflicts with those updates.

### 35.6. Thinking FOR NO KEY UPDATE Allows Two Writers on the Same Row

Two `NO KEY UPDATE`s on the same row still conflict. Compatibility with `KEY SHARE` does not mean compatibility with all writes.

### 35.7. Using SKIP LOCKED for Complete Reports

It skips locked rows, producing an incomplete result set.

### 35.8. Using NOWAIT and Assuming No Lock Can Wait

`NOWAIT` in a locking clause applies to row locks; table-level locks can still wait.

### 35.9. Omitting OF in a JOIN

`FOR UPDATE` without `OF` locks rows in display-only joined tables, increasing unnecessary contention.

### 35.10. Thinking SELECT FOR UPDATE Locks Non-Existent Values

With no matching row, there is no tuple to lock. Use `UNIQUE`/`ON CONFLICT` to prevent duplicate `INSERT`s.

### 35.11. Forgetting That UPDATE/DELETE Already Acquire Locks

Not every `UPDATE` needs a prior `SELECT FOR UPDATE`. For a single row, a conditional `UPDATE` is often simpler.

### 35.12. Holding Locks During External API Calls

Long transactions cause lock waits and operational hazards. Design a state machine with idempotency for slow external workflows.

### 35.13. Locking Multiple Rows in Different Orders Across Code Paths

This invites deadlocks; enforce consistent ordering and retry transactions when needed.

### 35.14. Retrying Only the Final Statement After 40001

If decisions relied on earlier `SELECT`s, retry **the entire transaction**.

### 35.15. Assuming pg_locks Lists Every Held Row Lock

Not every row lock appears as an obvious record there; use `pg_blocking_pids`, `pg_stat_activity`, and understand tuple metadata.

### 35.16. Using FOR SHARE for Long Reports That Need No Writer Protection

This stalls writers unnecessarily; plain `SELECT` with MVCC snapshot isolation is usually better.

### 35.17. Assuming FOR UPDATE Automatically Prevents Multi-Row Write Skew

Locking selected rows does not automatically uphold all set-level invariants. Lock the proper set, use constraints, or use `SERIALIZABLE`.

### 35.18. Failing to Handle 0 Rows Returned After Waiting for a Lock

Under `READ COMMITTED`, a row may no longer match `WHERE` after another transaction updates and commits. Zero rows is not necessarily an SQL error.

### 35.19. Using Large OFFSET in a Locking Query and Thinking Only Returned Rows Are Locked

Rows skipped by `OFFSET` can still be locked, causing unexpected contention.

### 35.20. Treating lock_timeout as a Total Transaction Wait Cap

`lock_timeout` bounds waiting to acquire locks per PostgreSQL's rules; `statement_timeout` and application timeouts are separate mechanisms.

## 36. Practice Exercises with Answers

Use the lab data from Section 6. For two-session exercises, keep A open, run B, then roll back both. If a test hits a timeout or `NOWAIT` error, roll back the errored session before continuing.

### Exercise 1. Which Lock Conflicts with Every Other Row Lock?

**Answer:** `FOR UPDATE`. It conflicts with `FOR UPDATE`, `FOR NO KEY UPDATE`, `FOR SHARE`, and `FOR KEY SHARE` on the same row.

### Exercise 2. Do Two FOR SHARE Locks on the Same Row Wait on Each Other?

**Answer:** No, because this row lock mode is compatible with itself, unless something else blocks them (such as a stronger lock from a third transaction or a table lock).

### Exercise 3. FOR NO KEY UPDATE and FOR KEY SHARE

**Session A:**

~~~sql
BEGIN;
SELECT customer_id
FROM lock_lab.customers
WHERE customer_id = 1
FOR NO KEY UPDATE;
~~~

**Session B:**

~~~sql
BEGIN;
SELECT customer_id
FROM lock_lab.customers
WHERE customer_id = 1
FOR KEY SHARE NOWAIT;
ROLLBACK;
~~~

**Answer:** B acquires `KEY SHARE` because the two modes are compatible. Then A rolls back.

### Exercise 4. FOR SHARE and FOR NO KEY UPDATE

**Question:** A holds `FOR SHARE` on customer 2; B requests `FOR NO KEY UPDATE` on the same row with `NOWAIT`.

**Answer:** Conflict; B receives `55P03`.

### Exercise 5. Does KEY SHARE Block UPDATE tier?

~~~sql
UPDATE lock_lab.customers
SET tier = 'gold'
WHERE customer_id = 3;
~~~

**Answer:** Per the schema, `tier` is not an FK key, so this is a non-key update. Its mode is equivalent to `FOR NO KEY UPDATE` and is compatible with A's `KEY SHARE`.

### Exercise 6. Does KEY SHARE Block DELETE?

**Answer:** Yes. `DELETE` requires a strong row lock and conflicts with `KEY SHARE`.

### Exercise 7. Why Does a Foreign Key Need KEY SHARE?

**Answer:** When inserting a child row pointing to a parent row, the engine must protect the parent row from conflicting deletion or key changes during FK validation without necessarily blocking updates to non-key columns of the parent.

### Exercise 8. How Does NOWAIT Differ from SKIP LOCKED?

**Answer:** `NOWAIT` raises an error upon hitting a conflicting row lock; `SKIP LOCKED` skips locked rows and returns other eligible rows.

### Exercise 9. Which Job Does Worker B Pick?

A holds `FOR UPDATE` on job 1001. B runs:

~~~sql
SELECT job_id
FROM lock_lab.jobs
WHERE status = 'pending'
ORDER BY priority DESC, job_id
LIMIT 1
FOR UPDATE SKIP LOCKED;
~~~

**Answer:** With the seed data and no other changes, B picks **1002** because 1001 is locked and 1002 is the next highest-priority pending job.

### Exercise 10. Why Must Claiming a Job UPDATE status?

**Answer:** Row locks are released when the transaction ends; if `status` stays `pending`, another worker can pick the same job again. You must persist the claim/status inside the transaction and implement recovery for failed workers.

### Exercise 11. Which Table Does the JOIN Lock?

~~~sql
SELECT o.order_id, c.full_name
FROM lock_lab.orders AS o
JOIN lock_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.order_id = 101
FOR UPDATE OF o;
~~~

**Answer:** The locking clause targets rows of `orders` aliased as `o`, without requesting `FOR UPDATE` on customer rows `c` via that clause.

### Exercise 12. READ COMMITTED After Waiting

A waits on a lock on a `pending` job; B changes the job to `running` and commits.

**Answer:** A resumes with the updated row version and omits that row if `status = 'pending'` is no longer true.

### Exercise 13. What Error Can Occur Under REPEATABLE READ?

**Answer:** If attempting to lock/update a row modified by another transaction since the snapshot, PostgreSQL raises `40001`; the application rolls back and retries the entire transaction.

### Exercise 14. Two Transactions Locking Two Rows in Opposite Order

**Answer:** Can cause a deadlock. PostgreSQL detects it and aborts one transaction with `40P01`; use consistent lock ordering and controlled retries.

### Exercise 15. Why Does SELECT FOR UPDATE Not Replace UNIQUE?

**Answer:** When the query finds no matching row, it cannot lock a non-existent key value to prevent another transaction from `INSERT`ing it. A unique constraint is the proper guard for uniqueness.

### Exercise 16. Is SELECT FOR UPDATE Mandatory Before Deducting 3 Units of Stock?

**Answer:** Not necessarily. For a single-row operation, a conditional `UPDATE` with `RETURNING` suffices:

~~~sql
UPDATE lock_lab.products
SET stock_qty = stock_qty - 3
WHERE product_id = 101
  AND stock_qty >= 3
RETURNING product_id, stock_qty;
~~~

With the seed data, the resulting stock is **7**. In the lab, wrap it in `BEGIN`/`ROLLBACK`.

### Exercise 17. Checking Who Is Blocking a Session

~~~sql
SELECT
    pid,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE datname = current_database();
~~~

**Answer:** `pg_blocking_pids(pid)` returns the PIDs blocking the inspected session at the moment of observation. Combine with queries, transaction age, and lock metadata to diagnose.

### Exercise 18. How Long Does SELECT FOR UPDATE Hold Its Lock?

**Answer:** Until the transaction `COMMIT`s or `ROLLBACK`s. With autocommit enabled, the statement finishes and immediately ends its transaction, offering no protection to subsequent statements in new transactions.

### Exercise 19. Why Avoid FOR SHARE When Simply Viewing a Report?

**Answer:** It blocks writers needing `FOR NO KEY UPDATE` on read rows, hurting concurrency. Plain `SELECT` with MVCC is far better when a snapshot suffices.

### Exercise 20. Running a SKIP LOCKED Test and Rolling Back

**Session A:**

~~~sql
BEGIN;
SELECT job_id
FROM lock_lab.jobs
WHERE job_id = 1001
FOR UPDATE;
~~~

**Session B:**

~~~sql
BEGIN;
SELECT job_id
FROM lock_lab.jobs
WHERE status = 'pending'
ORDER BY priority DESC, job_id
LIMIT 2
FOR UPDATE SKIP LOCKED;
ROLLBACK;
~~~

**Answer:** Under the seed data, B returns **1002 and 1003**, skipping job 1001. After A rolls back, data remains unchanged.

## 37. Checklist for Choosing the Right Lock in Real Projects

1. **Define the business invariant:** are you protecting against row edits, deletes, key changes, or just an FK?
2. **Determine whether the row exists yet:** for non-existent values, row locks do not replace `UNIQUE`.
3. **Prefer atomic DML when sufficient:** a conditional `UPDATE` with `RETURNING` is simpler than `SELECT FOR UPDATE` followed by `UPDATE`.
4. **If read–decide–write is needed, keep it in the same transaction and connection.**
5. **Choose the minimal lock that is strong enough:** `KEY SHARE`, `SHARE`, `NO KEY UPDATE`, or `UPDATE` per the conflict matrix.
6. **Distinguish row locks from table locks:** `NOWAIT`/`SKIP LOCKED` on rows does not eliminate table-level waits.
7. **In JOINs, specify `OF alias` if only one table needs locking.**
8. **In CTEs, place the locking clause on the source needing the lock.**
9. **Never use `SKIP LOCKED` for complete reporting.**
10. **Handle fallbacks for `NOWAIT`/timeouts and 0-row results.**
11. **Keep transactions short**, avoiding external API calls while holding locks.
12. **Enforce consistent lock ordering** when touching multiple rows or tables.
13. **Handle `55P03`, `40P01`, and `40001` by root cause**, rolling back and using bounded retries.
14. **Manage post-commit worker state:** claiming a job does not guarantee exactly-once execution or crash recovery.
15. **Measure real lock waits** with `pg_stat_activity`, `pg_blocking_pids`, and `pg_locks`.
16. **Never use system columns like `ctid`/`xmin` as durable business keys** for long-lived row selection.
17. **Test with two real sessions** covering both B-commit and B-rollback cases.
18. **Check the isolation level**, because `READ COMMITTED` and `REPEATABLE READ` behave differently on concurrently updated rows.

## 38. Official PostgreSQL Documentation

To verify exact syntax and rules for your **actual PostgreSQL major version**, refer to:

- [Explicit Locking — Row-Level Locks](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-ROWS): the four row-level lock modes, conflict matrix, and implicit DML locks.
- [SELECT](https://www.postgresql.org/docs/current/sql-select.html): `FOR UPDATE`, `FOR NO KEY UPDATE`, `FOR SHARE`, `FOR KEY SHARE`; `OF`, `NOWAIT`, `SKIP LOCKED`, and join/aggregation limits.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): snapshots, `READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE`.
- [Explicit Locking — Deadlocks](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-DEADLOCKS): deadlock detection and lock ordering.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_activity` and wait indicators.
- [System View pg_locks](https://www.postgresql.org/docs/current/view-pg-locks.html): reported locks and limitations observing row locks.
- [Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html): `55P03`, `40P01`, `40001`.
- [INSERT / ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): preventing duplicates via `UNIQUE` and upsert rather than locking non-existent rows.

The `/current/` path points to the latest PostgreSQL release on the website. When operating a different major version, consult the documentation for **that exact version** to confirm every detail.

## 39. Summary

The four locking clauses in PostgreSQL do not mean the same thing:

| Lock level | Quick takeaway |
| --- | --- |
| **`FOR UPDATE`** | Strongest lock; conflicts with all other row-level lock modes on the same row |
| **`FOR NO KEY UPDATE`** | Intended for non-key updates; remains compatible with `FOR KEY SHARE` |
| **`FOR SHARE`** | Multiple transactions can read in shared mode; blocks conflicting updates/deletes |
| **`FOR KEY SHARE`** | Protects keys and row existence; permits non-key updates |

Three foundational principles:

1. **MVCC keeps plain `SELECT`s from waiting on writers in many cases; a locking `SELECT` adds explicit coordination**, rather than replacing snapshots.
2. **Choose row locks based on the conflict matrix, row scope, and business logic**, instead of defaulting to `FOR UPDATE` out of habit.
3. **Locks must live inside a clearly managed transaction**. For queues, use `SKIP LOCKED` and persist claim state; for fast-fail APIs, use `NOWAIT`; for `JOIN`s, use `OF` to avoid locking unrelated tables.

Understanding these four modes helps you design PostgreSQL operations that stay **correct under concurrent sessions**, minimize over-locking, recognize when waits or retries are expected, and prevent logic bugs that a plain `SELECT` cannot stop on its own.
