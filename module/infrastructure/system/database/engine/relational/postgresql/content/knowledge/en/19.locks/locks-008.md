# Session-Level vs. Transaction-Level Advisory Locks in PostgreSQL

## 1. The Problem: A Task Must Not Run Twice Concurrently

Imagine an application with two workers receiving requests to generate an invoice summary for the same customer:

```text
Worker A                              Worker B
   |                                     |
   | Check "not yet summarized"          | Check "not yet summarized"
   |                                     |
   | Start summarizing                   | Start summarizing
   |                                     |
   v                                     v
Write result A                        Write result B
                 \                   /
                  Duplicate processing
```

Simply checking state with a `SELECT` before deciding to act creates a race condition. One solution is an **advisory lock**—a lock the application explicitly asks PostgreSQL to hold on a **logical identifier key**, for example:

```text
(namespace = 700, job_id = 1001)
```

Only the worker that acquires the lock proceeds with the exclusive work. Another worker trying to acquire the **same key** must either wait or receive an immediate failure, depending on which function is called.

PostgreSQL provides two primary advisory lock families:

- **Session-level locks**: persist until the session explicitly releases them or the session ends; they are not automatically released by `COMMIT` or `ROLLBACK`.
- **Transaction-level locks**: automatically released when the transaction ends via `COMMIT` or `ROLLBACK`; there is no separate unlock call while the transaction is still running.

Crucially, advisory locks **have no built-in knowledge of what an account, job, or table means**. PostgreSQL only enforces conflicts between sessions using the same logical key; **the application must agree** on which key maps to which resource and validate business state properly.

## 2. Lesson Objectives

After this lesson, you will be able to:

1. Explain how advisory locks differ from row locks and table locks.
2. Choose **session-level** vs. **transaction-level** locks for a given workflow.
3. Use **exclusive** and **shared** advisory locks.
4. Distinguish blocking functions from non-blocking `pg_try_advisory_...` functions.
5. Use both `bigint` and `(integer, integer)` key forms with proper namespacing.
6. Explain the impact of `COMMIT`, `ROLLBACK`, statement errors, and lost connections.
7. Design workflows that acquire the lock before reading/updating state.
8. Understand stale-snapshot risks, especially under `REPEATABLE READ`.
9. Use advisory locks safely in Java/JDBC and connection pools.
10. Observe held and waiting advisory locks via `pg_locks` and `pg_stat_activity`.
11. Mitigate deadlocks, excessive waits, lock leaks, and excessive lock counts.
12. Recognize problems unsuitable for advisory locks, such as replacing `UNIQUE`, row locks, or distributed coordination requiring fencing.

## 3. What Is an Advisory Lock?

In PostgreSQL, ordinary locks are acquired **automatically** because an SQL statement touches a table or row:

```sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = 1001;
```

That `UPDATE` must coordinate with other transactions modifying the same row. The row lock is tied to physical data managed by PostgreSQL.

By contrast, an advisory lock is an **application-chosen lock**:

```sql
SELECT pg_advisory_xact_lock(700, 1001);
```

PostgreSQL **does not know** that `700` means "invoice billing workflow" or that `1001` is a "job ID." It only tracks a lock under that identifier and whether other requests for that identifier are compatible.

### 3.1. Visual Comparison

```text
Row lock
  UPDATE table A, row ID=1001
       |
       v
  PostgreSQL automatically locks the row affected by UPDATE

Advisory lock
  Application picks key pair (700,1001)
       |
       v
  SELECT pg_advisory_xact_lock(700,1001)
       |
       v
  PostgreSQL coordinates advisory requests on the same key
```

### 3.2. Cooperative Locking

Advisory locks work only when **every participating component follows the same locking convention**.

For example, Worker A holds:

```sql
SELECT pg_advisory_xact_lock(700, 1001);
```

Worker B cannot acquire the same exclusive lock while it is held. Yet Worker C can still run:

```sql
UPDATE lock_lab.jobs
SET status = 'DONE'
WHERE job_id = 1001;
```

if Worker C **does not check the advisory lock** and nothing else blocks it.

An advisory lock does not lock the row `jobs(1001)`. That is why advisory locks must never be mistaken for **data constraints**.

### 3.3. Database/Cluster Scope, Not System-Wide

Advisory locks are managed by PostgreSQL's lock manager within **one database**. Identical keys in two separate databases do not conflict; two independent PostgreSQL clusters do not share a lock manager either.

If an application spans multiple databases or clusters, calling `pg_advisory_lock` on one node does **not** create a global lock across all nodes.

## 4. Setting Up Practice Data

Run these examples in a **test** database, not production. Several examples require **two or three independent connections**.

### 4.1. Create the Jobs Table

```sql
CREATE SCHEMA IF NOT EXISTS lock_lab;

CREATE TABLE lock_lab.jobs (
    job_id integer PRIMARY KEY,
    job_type text NOT NULL,
    status text NOT NULL
        CHECK (status IN (
            'PENDING', 'RUNNING', 'DONE', 'FAILED'
        )),
    attempt_count integer NOT NULL DEFAULT 0
        CHECK (attempt_count >= 0),
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO lock_lab.jobs
    (job_id, job_type, status)
VALUES
    (1001, 'invoice-report', 'PENDING'),
    (1002, 'invoice-report', 'PENDING'),
    (2001, 'daily-summary',  'PENDING');
```

Initial data:

| job_id | job_type | status | attempt_count |
| ---: | --- | --- | ---: |
| 1001 | invoice-report | PENDING | 0 |
| 1002 | invoice-report | PENDING | 0 |
| 2001 | daily-summary | PENDING | 0 |

### 4.2. Create the Report Requests Table

```sql
CREATE TABLE lock_lab.report_requests (
    request_id bigint PRIMARY KEY,
    customer_id integer NOT NULL,
    report_month date NOT NULL,
    status text NOT NULL
        CHECK (status IN ('NEW', 'RUNNING', 'READY')),
    CONSTRAINT uq_customer_month
        UNIQUE (customer_id, report_month)
);

INSERT INTO lock_lab.report_requests (
    request_id, customer_id, report_month, status
) VALUES
    (1, 101, DATE '2026-10-01', 'NEW'),
    (2, 102, DATE '2026-10-01', 'NEW');
```

This table distinguishes **advisory locks** from **`UNIQUE` constraints**: the advisory lock coordinates work, while `UNIQUE` guarantees two rows with the same `(customer_id, report_month)` cannot be saved even if a program ignores the lock convention.

### 4.3. Two Sessions Must Be Two Distinct Backends

In each `psql` window, run:

```sql
SELECT pg_backend_pid();
```

If both windows return **the same PID**, your tool is sharing a connection or talking to the same backend. To test advisory lock conflicts, you need **two genuinely independent PostgreSQL sessions**.

Labels:

- **Session A**: connection holding the lock.
- **Session B**: connection attempting to acquire the lock.
- **Session C**: optional, when testing shared locks or monitoring.

Execute statements in the exact order shown. A `SELECT pg_advisory_lock(...)` without an unlock holds the session lock until the connection closes.

## 5. Two Lock Lifetimes: Session-Level and Transaction-Level

This is the single most important distinction in the lesson.

| Characteristic | Session-level | Transaction-level |
| --- | --- | --- |
| Typical function | `pg_advisory_lock` | `pg_advisory_xact_lock` |
| Acquired when | Lock request succeeds | Lock request succeeds in transaction |
| `COMMIT` | **Does NOT release** | **Automatically releases** |
| `ROLLBACK` | **Does NOT release** | **Automatically releases** |
| Explicit unlock | `pg_advisory_unlock` | No separate unlock function |
| Session/backend ends | Released automatically | Released automatically as transaction ends |
| Under autocommit | Persists after statement | Released at statement end |
| Connection pool | Easy to leak without cleanup | Usually fits managed transactions better |
| Best suited for | Workflows spanning multiple transactions on one pinned session | Database work contained within one transaction |

### 5.1. Session-Level: Physical Connection Lifetime

```text
Session A
   |
   +-- SELECT pg_advisory_lock(key)
   |            |
   |            +----- lock remains held ------------------+
   |                                                       |
   +-- BEGIN                                               |
   +-- UPDATE                                              |
   +-- ROLLBACK  -------- lock STILL held -----------------+
   +-- BEGIN                                               |
   +-- COMMIT    -------- lock STILL held -----------------+
   |                                                       |
   +-- SELECT pg_advisory_unlock(key) --- lock released ---+
   |
   +-- Connection closes
```

### 5.2. Transaction-Level: Transaction Lifetime

```text
Session A
   |
   +-- BEGIN
   |    |
   |    +-- SELECT pg_advisory_xact_lock(key)
   |    |            |
   |    |            +-- lock held ------------+
   |    +-- SELECT / UPDATE                    |
   |    +-- COMMIT or ROLLBACK ----------------+
   |
   +-- Next transaction no longer holds that lock
```

**Quick selection rule:** if the goal is protecting a read/write sequence **inside one transaction**, prefer a **transaction-level advisory lock**, unless there is a clear reason to hold the lock across transaction boundaries.

## 6. Key Advisory Lock Functions

PostgreSQL supports two key signatures:

1. **One 64-bit integer:** `key bigint`.
2. **Two 32-bit integers:** `key1 integer, key2 integer`.

Below uses `(key1, key2)` for examples.

### 6.1. Session-Level Exclusive Locks

| Function | Return | Behavior |
| --- | --- | --- |
| `pg_advisory_lock(key1, key2)` | `void` | Waits until exclusive session lock is acquired |
| `pg_try_advisory_lock(key1, key2)` | `boolean` | Non-blocking attempt: `true` if acquired, `false` if conflicting |
| `pg_advisory_unlock(key1, key2)` | `boolean` | Releases one hold count; `false` if session does not hold the lock |

Corresponding `bigint` forms:

```sql
SELECT pg_advisory_lock(900001::bigint);
SELECT pg_try_advisory_lock(900001::bigint);
SELECT pg_advisory_unlock(900001::bigint);
```

### 6.2. Session-Level Shared Locks

| Function | Meaning |
| --- | --- |
| `pg_advisory_lock_shared(key1, key2)` | Waits to acquire a shared session lock |
| `pg_try_advisory_lock_shared(key1, key2)` | Non-blocking attempt for a shared session lock |
| `pg_advisory_unlock_shared(key1, key2)` | Releases one hold of a shared session lock |

Example:

```sql
SELECT pg_advisory_lock_shared(700, 1001);
SELECT pg_advisory_unlock_shared(700, 1001);
```

### 6.3. Transaction-Level Exclusive Locks

| Function | Meaning |
| --- | --- |
| `pg_advisory_xact_lock(key1, key2)` | Waits to acquire an exclusive transaction lock |
| `pg_try_advisory_xact_lock(key1, key2)` | Non-blocking attempt for an exclusive transaction lock |

Example:

```sql
BEGIN;

SELECT pg_advisory_xact_lock(700, 1001);

-- Database work requiring coordination.
SELECT status
FROM lock_lab.jobs
WHERE job_id = 1001;

COMMIT;
```

The lock is released at `COMMIT`. **There is no need for—and no function named—`pg_advisory_xact_unlock`.**

### 6.4. Transaction-Level Shared Locks

```sql
BEGIN;

SELECT pg_advisory_xact_lock_shared(700, 1001);

-- Read state within the coordinated section.
SELECT status
FROM lock_lab.jobs
WHERE job_id = 1001;

COMMIT;
```

Non-blocking variant:

```sql
SELECT pg_try_advisory_xact_lock_shared(700, 1001);
```

The `bigint` signature supports the corresponding shared and transaction-level functions as well.

### 6.5. There Is No Explicit Transaction-Level Unlock

A common misconception:

```sql
-- This function DOES NOT exist:
SELECT pg_advisory_xact_unlock(700, 1001);
```

If you need to release the lock **before the transaction ends**, rethink the design:

- Narrow the transaction.
- Use a separate transaction for the locked step.
- Or consider session-level locks with explicit cleanup if the workflow genuinely outlives a transaction.

Never try to simulate "unlocking a transaction-level lock" with `pg_advisory_unlock`: that function operates on **session-level locks**, not transaction-level locks.

## 7. Designing Lock Keys: Not Just Picking Any Number

Advisory keys **have no automatic connection** to table names, primary keys, or text strings. Applications must manage their own namespaces.

### 7.1. Using Two Integers: Namespace and Resource ID

A clear convention:

| key1 | Resource type | key2 |
| ---: | --- | --- |
| 700 | Sync job | `job_id` |
| 701 | Customer report | `customer_id` |
| 702 | Group maintenance task | `group_id` |
| 703 | Order reconciliation | `order_id`, if it fits `integer` |

Example:

```sql
-- Lock job 1001:
SELECT pg_advisory_xact_lock(700, 1001);

-- Lock job 1002: different resource, does not conflict with 1001.
SELECT pg_advisory_xact_lock(700, 1002);

-- Lock customer 1001 report:
-- Different namespace, so does not conflict with (700,1001).
SELECT pg_advisory_xact_lock(701, 1001);
```

Partitioning namespaces prevents teams or features from accidentally colliding on keys for unrelated resources.

### 7.2. `bigint` and `(int,int)` Use Separate Key Spaces

An easily missed detail: a single `bigint` key and a pair of `integer` keys **do not share the same advisory lock namespace**.

Example:

```sql
SELECT pg_advisory_lock(700, 1001);
SELECT pg_advisory_lock(3006477108201::bigint);
```

Do not assume "packing 700 and 1001 into a 64-bit integer" conflicts with the two-argument form. PostgreSQL keeps the two key spaces distinct.

**Within a feature, standardize on one key signature.** Never mix `pg_advisory_xact_lock(bigint)` and `pg_advisory_xact_lock(int,int)` expecting them to protect the same resource.

### 7.3. Mind Value Ranges

- `integer` is signed 32-bit.
- `bigint` is signed 64-bit.

If `job_id` is a `bigint` exceeding 32-bit range, never truncate it into an `integer` just to fit the two-int signature. Options:

- Use a single `bigint` key with a planned bit/range namespace.
- Use a controlled key-mapping table.
- Or coordinate via a row in a table when uniqueness over composite business keys is needed.

### 7.4. String Keys: Beware of Hash Functions

An application might have a string resource key:

```text
invoice:customer-101:2026-10
```

PostgreSQL advisory lock functions do not accept `text` directly. You may see suggestions like:

```sql
-- Illustrative idea, does NOT guarantee zero collisions:
SELECT pg_advisory_xact_lock(
    hashtext('invoice:customer-101:2026-10')
);
```

**Warning:** `hashtext` returns a 32-bit hash, not a mathematically unique identifier. Two distinct strings **can hash-collide**, locking the wrong resource or violating expected isolation.

Never treat a 32-bit hash as proof that "each string gets a unique lock key." If collisions are unacceptable, store a mapping from business keys to unique integer IDs in the database or coordinate via table rows and constraints.

### 7.5. Locks Are Not Passwords or Access Control

Any client permitted to call advisory lock functions can request any key used by another feature. A "hard-to-guess" key provides zero security.

Table read/write permissions must still be enforced with roles, `GRANT`s, RLS, and application authorization. Advisory locks only handle **concurrency coordination**.

## 8. Session-Level Locks: Observing Waits Across Two Sessions

This lab uses key `(800, 1)` to avoid colliding with job examples.

### 8.1. Session A Acquires an Exclusive Session Lock

**Session A:**

```sql
SELECT pg_backend_pid();

SELECT pg_advisory_lock(800, 1);
-- Returns once the lock is acquired.
```

`pg_advisory_lock` returns `void`; clients usually display an empty cell. "No output" does not mean failure: the function only returns once the lock is granted or an error/cancel occurs.

### 8.2. Session B Tries Non-Blocking

**Session B:**

```sql
SELECT pg_backend_pid();

SELECT pg_try_advisory_lock(800, 1) AS acquired;
```

Result:

```text
acquired
--------
false
```

Session B does not own the lock because A holds an exclusive lock on the same key.

### 8.3. Session B Calls the Blocking Function

If B runs:

```sql
SELECT pg_advisory_lock(800, 1);
```

it **waits** until A releases the lock, or exits due to timeout/cancel/error. Never run a blocking `pg_advisory_lock` without a way to release it from the holding session.

### 8.4. Session A Releases

**Session A:**

```sql
SELECT pg_advisory_unlock(800, 1) AS released;
```

Result:

```text
released
--------
true
```

Once A unlocks, waiting B acquires the lock. **If B used the blocking call and acquired it, B must also unlock it:**

```sql
SELECT pg_advisory_unlock(800, 1);
```

### 8.5. Another Session Cannot Unlock on Your Behalf

A session can release **only session advisory locks it holds itself**. Calling in Session B:

```sql
SELECT pg_advisory_unlock(800, 1);
```

when B does not hold the lock returns `false`; it does not "command Session A to unlock."

When recovering a hung session in production, terminating a backend is a sensitive operational action affecting that entire transaction and connection—never treat it as a routine unlock step.

## 9. Critical Trap: `ROLLBACK` Does Not Release Session-Level Locks

Try this experiment yourself.

### 9.1. Session A Acquires Inside a Transaction

```sql
BEGIN;

SELECT pg_advisory_lock(800, 2);

-- Make a change then abort it:
UPDATE lock_lab.jobs
SET attempt_count = attempt_count + 1
WHERE job_id = 1001;

ROLLBACK;
```

The `UPDATE` rolls back. Yet **session advisory lock `(800,2)` remains held**.

### 9.2. Session B Tries the Same Key

```sql
SELECT pg_try_advisory_lock(800, 2) AS acquired;
```

Still returns `false`, as long as Session A has not unlocked it and the two sessions are distinct backends.

### 9.3. Session A Unlocks After Rollback

```sql
SELECT pg_advisory_unlock(800, 2) AS released;
```

After A unlocks, B retries and gets `true`:

```sql
SELECT pg_try_advisory_lock(800, 2) AS acquired;

-- If true, B must also release:
SELECT pg_advisory_unlock(800, 2);
```

### 9.4. Even Unlocking Inside a Transaction and Rolling Back Does Not Restore It

A symmetric property:

- Acquire a session lock inside a transaction then `ROLLBACK`: **lock remains held**.
- Release a session lock inside a transaction then `ROLLBACK`: **lock remains released**.

Session advisory locks have a lifecycle **outside transaction commit/rollback**.

**This causes severe leaks when applications only call unlock on the success path while exception paths roll back without cleanup.**

## 10. Session-Level Locks Are Reentrant in the Same Session

PostgreSQL allows a session to **re-acquire a lock it already holds**, even if another session is waiting for that lock.

Example:

```sql
-- Same Session A:
SELECT pg_advisory_lock(800, 3);
SELECT pg_advisory_lock(800, 3);
```

The second call is not blocked by the session's own first hold. However, session-level advisory locks maintain a **hold count**: you must unlock as many times as you acquired.

```sql
-- Release first hold:
SELECT pg_advisory_unlock(800, 3);

-- Still held by Session A because it was acquired twice.
-- Release remaining hold:
SELECT pg_advisory_unlock(800, 3);
```

### 10.1. Reentrant Calls Do Not Prove the Key Is Free

If you test locking on a connection that already holds the key:

```sql
SELECT pg_try_advisory_lock(800, 3);
```

it returns `true` because **this very connection already owns the lock**, not because no one else holds it.

When testing mutual exclusion, **always use two separate physical backends**—never test by locking twice on one connection.

### 10.2. Beware of Nested Library Calls

Function A acquires the lock, calls Function B which also acquires the same lock, and B unlocks once. If A later throws an exception without unlocking its own count, the session leaks the lock.

Manage session-level locks with strict ownership discipline:

```text
acquire -> try { work } finally { release }
```

Never rely on `COMMIT` or `ROLLBACK` to "clean up for you."

## 11. Transaction-Level: Automatically Released on COMMIT/ROLLBACK

### 11.1. Session A Starts a Transaction and Acquires

```sql
BEGIN;

SELECT pg_advisory_xact_lock(800, 10);

SELECT job_id, status
FROM lock_lab.jobs
WHERE job_id = 1001;
```

Leave Session A uncommitted.

### 11.2. Session B Tries the Same Key

```sql
BEGIN;

SELECT pg_try_advisory_xact_lock(800, 10) AS acquired;
-- false while A holds the exclusive lock.

ROLLBACK;
```

### 11.3. Session A Ends Its Transaction

```sql
COMMIT;
```

Or use:

```sql
ROLLBACK;
```

In both cases, **the transaction-level advisory lock is released** when the transaction ends.

### 11.4. Session B Tries in a New Transaction

```sql
BEGIN;

SELECT pg_try_advisory_xact_lock(800, 10) AS acquired;
-- true if no other conflicting holder exists.

COMMIT;
```

Immediately upon B's `COMMIT`, B's transaction-level lock is also released.

### 11.5. No Need for `pg_advisory_unlock`

For a lock acquired via:

```sql
pg_advisory_xact_lock(800, 10)
```

do not call `pg_advisory_unlock(800, 10)` to release it. That unlock function belongs to session-level ownership and does not release transaction-level locks.

## 12. Autocommit Trap: Transaction-Level Locks Vanishing Immediately

A common bug:

```sql
-- Client is in autocommit = ON mode.
SELECT pg_advisory_xact_lock(700, 1001);

-- Once that statement ends, its implicit transaction ends.
-- The xact-level lock is already released.

SELECT status
FROM lock_lab.jobs
WHERE job_id = 1001;

UPDATE lock_lab.jobs
SET status = 'RUNNING'
WHERE job_id = 1001;
```

Each statement runs as its own independent transaction. Once `SELECT pg_advisory_xact_lock(...)` completes under autocommit, PostgreSQL releases the transaction-level lock. The next two statements are **completely unprotected**.

### 12.1. Right Way: Open an Explicit Transaction

```sql
BEGIN;

SELECT pg_advisory_xact_lock(700, 1001);

SELECT status
FROM lock_lab.jobs
WHERE job_id = 1001;

UPDATE lock_lab.jobs
SET status = 'RUNNING',
    attempt_count = attempt_count + 1,
    updated_at = now()
WHERE job_id = 1001
  AND status = 'PENDING';

COMMIT;
```

The lock persists from acquisition until `COMMIT`.

### 12.2. Always Check Affected Row Count

An `UPDATE` conditioned on `status = 'PENDING'` can update **0 rows** if another worker already claimed the job. Acquiring the lock **does not prove** the job is still `PENDING`.

Use:

```sql
UPDATE lock_lab.jobs
SET status = 'RUNNING',
    attempt_count = attempt_count + 1,
    updated_at = now()
WHERE job_id = 1001
  AND status = 'PENDING'
RETURNING job_id, status, attempt_count;
```

In production code, only a worker receiving **exactly one row** should consider the job claimed.

### 12.3. Never Split Steps Across Separate Connections

```text
Connection A: BEGIN + pg_advisory_xact_lock
Connection B: SELECT/UPDATE job
Connection A: COMMIT
```

This is not one shared transaction. While the advisory lock might block **another worker honoring that key**, B's `SELECT`/`UPDATE` run in a different transaction without atomicity, shared snapshots, or transactional isolation expected by the design.

For atomic workflows, keep all related database steps on **the same connection and transaction**.

## 13. How Do Shared and Exclusive Modes Conflict?

There are two modes:

- **Exclusive lock**: prevents another backend from concurrently holding an **incompatible** shared or exclusive lock on the same key.
- **Shared lock**: multiple backends can hold shared locks on the same key concurrently, while conflicting with exclusive requests from other backends.

Compatibility table on **the same advisory key** across distinct backends:

| Held lock | Shared request | Exclusive request |
| --- | --- | --- |
| None | Yes | Yes |
| Shared | Yes | **Waits / try fails** |
| Exclusive | **Waits / try fails** | **Waits / try fails** |

Reentrant rules within the same session behave differently when that session already holds the lock; the table above applies to **independent backends**.

### 13.1. Two Readers Both Using Shared Locks

**Session A:**

```sql
BEGIN;
SELECT pg_advisory_xact_lock_shared(810, 1);
```

**Session B:**

```sql
BEGIN;
SELECT pg_try_advisory_xact_lock_shared(810, 1)
    AS acquired;
-- true.
```

Both A and B hold shared advisory locks on `(810,1)`.

### 13.2. Writer Cannot Acquire Exclusive While Readers Hold Shared

**Session C:**

```sql
BEGIN;

SELECT pg_try_advisory_xact_lock(810, 1)
    AS acquired;
-- false.

ROLLBACK;
```

Once both A and B `COMMIT`/`ROLLBACK`, the shared locks are released. Session C in a new transaction can then acquire the exclusive lock.

### 13.3. Shared Locks Do Not Automatically Block Normal SELECT/UPDATE SQL

If Session C **does not call advisory functions** and runs:

```sql
UPDATE lock_lab.jobs
SET attempt_count = attempt_count + 1
WHERE job_id = 1001;
```

it is not automatically blocked by the shared advisory lock. Shared locks only coordinate operations **that explicitly use the matching advisory key and mode**.

### 13.4. When Are Shared Locks Useful?

Example: "multiple scheduled read tasks may run concurrently, whereas a canonical data rebuild must run exclusively."

- Readers acquire `pg_advisory_xact_lock_shared(namespace, key)`.
- The writer acquires `pg_advisory_xact_lock(namespace, key)`.
- **Every participating component** must follow this convention.

For ordinary PostgreSQL reads, MVCC already lets readers run without blocking writers; **do not add shared advisory locks** unless you need logical coordination beyond MVCC.

## 14. Blocking vs. `try` Functions: Choosing by Desired Latency

Two common strategies:

### 14.1. Wait Until the Lock Is Acquired

```sql
BEGIN;

SELECT pg_advisory_xact_lock(700, 1001);

-- Runs only once the lock is acquired.
SELECT status FROM lock_lab.jobs WHERE job_id = 1001;

COMMIT;
```

If another transaction holds the lock, the call **waits**.

Use when:

- The task must run rather than be skipped.
- Wait time has reasonable bounds.
- Timeouts/cancellation policies are configured.
- Callers tolerate slower responses.

### 14.2. Try and Skip When Busy

```sql
BEGIN;

SELECT pg_try_advisory_xact_lock(700, 1001)
    AS acquired;

-- If acquired = false:
--   ROLLBACK and report BUSY/SKIPPED to the application.
-- If acquired = true:
--   read state, execute work, and COMMIT.
```

`pg_try_advisory_xact_lock` returns a **boolean** immediately instead of waiting.

Use when:

- A cron run can skip a tick if the prior run is still active.
- A scheduler can back off and retry later.
- A worker can pick another task rather than waiting on one resource.
- An API prefers returning "already processing" rather than hanging requests.

### 14.3. `false` Is Not an SQL Error

When a try function returns `false`:

- The transaction is **not** put into an aborted state just from returning `false`.
- The application must **explicitly decide** to roll back, commit, or pick other work.
- Never execute exclusive steps when `acquired` is `false`.

### 14.4. `true` Does Not Prove Business Success

`true` only means **the advisory lock was acquired**. It does not mean:

- The job is still `PENDING`.
- The account/order exists.
- The caller is authorized.
- No duplicate request already completed.
- Subsequent SQL statements will definitely commit.

Always separate **acquiring the lock** from **validating state** and **committing the business transition**.

## 15. Proper Workflow: Lock, Re-Read, Update, Commit

A recommended pattern for applications:

```text
BEGIN
   |
   v
Acquire advisory transaction lock for target resource
   |
   +-- Not acquired (try=false) -> ROLLBACK / defer
   |
   v
RE-READ business data after holding the lock
   |
   +-- Invalid state -> ROLLBACK / no-op
   |
   v
Conditional UPDATE/INSERT and check row count
   |
   v
COMMIT
   |
   v
Advisory xact lock released automatically
```

### 15.1. Blocking Job Processing Example

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

-- Step 1: lock on namespace=700, job_id=1001.
SELECT pg_advisory_xact_lock(700, 1001);

-- Step 2: check status AFTER acquiring the lock.
SELECT job_id, status, attempt_count
FROM lock_lab.jobs
WHERE job_id = 1001;

-- Step 3: claim if still PENDING.
UPDATE lock_lab.jobs
SET status = 'RUNNING',
    attempt_count = attempt_count + 1,
    updated_at = now()
WHERE job_id = 1001
  AND status = 'PENDING'
RETURNING job_id, status, attempt_count;

-- In the application: consider the claim successful
-- only if UPDATE returns exactly one row.

COMMIT;
```

If an earlier worker already claimed the job, a later worker acquires the lock after the first commits, and `UPDATE ... WHERE status = 'PENDING'` returns **0 rows**. That is how data state complements locking.

### 15.2. Why Re-Read After Acquiring the Lock?

Wrong order:

```text
Worker A: SELECT status='PENDING'
Worker B: SELECT status='PENDING'
Worker B: acquires lock, sets status='RUNNING', COMMITs
Worker A: acquires lock, still trusts old SELECT result
Worker A: processes job twice
```

An advisory lock does not magically refresh earlier `SELECT` results. Any decision based on data **read before acquiring the lock** may be stale.

**Always re-read and re-check conditions after acquiring.**

### 15.3. Why Separate Lock Acquisition and Data SELECT Into Two Statements?

Under `READ COMMITTED`, each normal statement takes a snapshot when it begins. If you combine:

```sql
SELECT
    pg_advisory_xact_lock(700, 1001),
    status
FROM lock_lab.jobs
WHERE job_id = 1001;
```

the `SELECT` takes its **snapshot before waiting for the lock**. Once the lock is granted, the `status` returned by that same statement is not guaranteed to reflect commits made by a previous holder while you waited.

Therefore, for "wait for previous worker, then read latest committed state," use **two separate SQL statements**:

```sql
SELECT pg_advisory_xact_lock(700, 1001);

SELECT status
FROM lock_lab.jobs
WHERE job_id = 1001;
```

Under `READ COMMITTED`, the second `SELECT` begins **after the lock is granted**, so it sees commits that completed before it started.

### 15.4. Be Careful with REPEATABLE READ

If a `REPEATABLE READ` transaction already established its snapshot **before waiting on the lock**, acquiring the advisory lock afterward **does not refresh that snapshot**.

Even if `SELECT pg_advisory_xact_lock(...)` is the first query, do not assume the snapshot is taken **after** the wait finishes. Treat snapshot establishment time as part of your transaction design.

For the "wait for lock then read latest committed state" pattern, `READ COMMITTED` plus a **separate post-acquire `SELECT`** is usually easiest to reason about. If your logic requires `REPEATABLE READ`/`SERIALIZABLE`, analyze snapshots, row locks, and `40001` retries carefully.

## 16. Advisory Locks and MVCC: Two Mechanisms Serving Two Purposes

MVCC and advisory locks are not two names for the same feature.

| Mechanism | Purpose |
| --- | --- |
| MVCC snapshot | Determines which row versions are visible to reads |
| Row lock | Coordinates updates/locks on concrete table rows |
| Table lock | Coordinates table-level operations and conflicts |
| Advisory lock | Coordinates **application-defined operations** on logical keys |
| `UNIQUE`/FK/CHECK | Enforces data integrity constraints |
| `SERIALIZABLE` | Prevents non-serializable concurrent transaction schedules |

### 16.1. Advisory Locks Do Not Raise Isolation Level

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;
SELECT pg_advisory_xact_lock(700, 1001);
```

The transaction remains at `READ COMMITTED`. Advisory locks do not upgrade it to `SERIALIZABLE`.

### 16.2. Advisory Locks Do Not Refresh Stale Snapshots

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT status
FROM lock_lab.jobs
WHERE job_id = 1001;

-- Another transaction UPDATEs status and COMMITs.

SELECT pg_advisory_xact_lock(700, 1001);

SELECT status
FROM lock_lab.jobs
WHERE job_id = 1001;
```

The second `SELECT` still sees the old status from the `REPEATABLE READ` snapshot. A logical lock never forces a snapshot refresh.

### 16.3. Advisory Locks Do Not Replace UNIQUE Constraints

```sql
CREATE TABLE lock_lab.once_per_customer (
    customer_id integer PRIMARY KEY,
    processed_at timestamptz NOT NULL DEFAULT now()
);
```

If business rules allow only one row per customer, `PRIMARY KEY` enforces that even if a client **ignores advisory locks** and attempts a duplicate `INSERT`.

Whenever an invariant can be expressed as a constraint, prefer the constraint. Advisory locks are a **supplement** to serialize work, avoid redundant expensive work, or coordinate scopes with no single table row.

## 17. Session-Level Locks and Connection Pools

In Java, Node.js, or Go applications, "the request ended" **does not mean the physical PostgreSQL session ended**.

Connection pools keep TCP connections and backends alive for reuse.

### 17.1. Lock Leak Scenario

```text
HTTP Request A
  |
  +-- Checks out connection #5
  +-- SELECT pg_advisory_lock(900,1)
  +-- Performs work
  +-- Errors before unlocking
  +-- Returns connection #5 to pool

HTTP Request B
  |
  +-- Checks out connection #5
  +-- Gets backend still holding session lock (900,1)
  +-- pg_try_advisory_lock returns true due to reentrancy
  +-- Or blocks other backends unexpectedly
```

If Request A only rolls back its transaction on error, the session-level lock **stays held**. This is why session locks require much stricter cleanup than transaction-level locks.

### 17.2. Safer Model: Transaction-Level

```text
Check out connection
    |
    v
BEGIN
    |
    v
pg_advisory_xact_lock(...)
    |
    v
Execute database statements
    |
    +-- success -> COMMIT -> lock released automatically
    |
    +-- error -> ROLLBACK -> lock released automatically
    |
    v
Return connection to pool
```

Still ensure the connection actually closes its transaction before returning to the pool. An abandoned open transaction holds transaction-level locks too.

### 17.3. Session-Level Requires `finally`

If you must hold a session-level lock, place the unlock inside cleanup code that runs on both success and exception paths.

Note carefully:

- Unlock must run on **the exact physical session** that acquired the lock.
- If the connection drops, the backend releases on session exit; if the network drops silently, the backend may hold the lock briefly until it detects the dead peer.
- You cannot borrow a **different** connection to unlock the first session's lock.
- If the connection's transaction is aborted, roll back first so cleanup SQL can run.

In pooled applications, **transaction-level locks** or explicit worker/transaction boundaries are far less error-prone.

### 17.4. PgBouncer Transaction Pooling

In **transaction pooling**, consecutive transactions from one logical client can be routed to **different server backends**.

Session-level advisory locks are dangerous if a client expects to keep the same backend across transactions:

```text
Client:
  TX 1 -> backend A -> pg_advisory_lock(...)
  TX 2 -> backend B -> pg_advisory_unlock(...)

Result: B does not hold A's lock.
```

Never use session advisory locks across transaction boundaries when connections are multiplexed per transaction.

Transaction-level advisory locks **fit much better** because locking and protected statements run within one transaction pinned to a backend. Still verify your pool's exact mode and keep the full workflow inside one transaction.

## 18. Java/JDBC: Claiming a Job with Transaction-Level Advisory Locks

Suppose a Java service wants to claim job 1001 if no other worker is handling it. Use `pg_try_advisory_xact_lock` to avoid waiting indefinitely.

### 18.1. One Transaction, One Physical Connection

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class JobClaimService {
    private final DataSource dataSource;

    public JobClaimService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean claimJob(int jobId) throws SQLException {
        try (Connection conn = dataSource.getConnection()) {
            conn.setTransactionIsolation(
                Connection.TRANSACTION_READ_COMMITTED
            );
            conn.setAutoCommit(false);

            try {
                // Namespace 700 reserved for jobs.
                boolean acquired;
                try (PreparedStatement ps = conn.prepareStatement(
                    "SELECT pg_try_advisory_xact_lock(?, ?)"
                )) {
                    ps.setInt(1, 700);
                    ps.setInt(2, jobId);

                    try (ResultSet rs = ps.executeQuery()) {
                        rs.next();
                        acquired = rs.getBoolean(1);
                    }
                }

                if (!acquired) {
                    conn.rollback();
                    return false;
                }

                // Separate statement AFTER acquiring the lock.
                // Conditionally verify and transition status.
                int changed;
                try (PreparedStatement ps = conn.prepareStatement(
                    "UPDATE lock_lab.jobs " +
                    "SET status = 'RUNNING', " +
                    "    attempt_count = attempt_count + 1, " +
                    "    updated_at = now() " +
                    "WHERE job_id = ? AND status = 'PENDING'"
                )) {
                    ps.setInt(1, jobId);
                    changed = ps.executeUpdate();
                }

                if (changed != 1) {
                    conn.rollback();
                    return false;
                }

                conn.commit();
                return true;
            } catch (SQLException | RuntimeException error) {
                try {
                    conn.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    }
}
```

In this example:

- `setAutoCommit(false)` ensures the xact-level lock remains held across subsequent steps.
- `pg_try_advisory_xact_lock` returns a boolean; `false` is not treated as a successful claim.
- The `UPDATE` runs **after** acquiring the lock, so `READ COMMITTED` uses a fresh statement snapshot.
- `status = 'PENDING'` prevents re-claiming after an earlier worker committed.
- `commit` or `rollback` releases the advisory xact lock.
- If `UPDATE` affects 0 rows, the method does not report a successful claim.

### 18.2. Separating Job Claiming from Job Execution

This example only **claims** a job inside a short transaction. After `COMMIT`, the advisory xact lock is released, while `RUNNING` status persists in the table.

It does **not** hold the lock while the worker performs external CPU/HTTP/email work.

If you need **no two workers to execute the same long-running job simultaneously** after claiming, add explicit ownership mechanisms:

- Job state and worker ownership columns.
- Expiring leases with heartbeat renewal.
- Fencing tokens or version numbers to reject stale workers after ownership transfers.
- Retry/recovery handling on worker crash.
- Idempotency guarantees where side effects could repeat.

Never claim that a transaction-level advisory lock released at `COMMIT` continues protecting work running **after commit**.

### 18.3. Never Hold Long Transactions Waiting on HTTP or Users

A dangerous pattern:

```text
BEGIN
pg_advisory_xact_lock
UPDATE state
Call HTTP API taking 60 seconds
Wait on message queue for 20 seconds
COMMIT
```

The transaction pins locks and resources throughout external waits, worsening contention and impacting `VACUUM` and connection pools.

Prefer **short transactions to claim/transition state**, then coordinate long execution via durable state, leases, and fencing where required.

## 19. Long Tasks: Why Advisory Locks Are Not Distributed Leases

Suppose a worker:

1. Acquires a session advisory lock.
2. Begins calling an external API.
3. Loses its PostgreSQL connection while still running the API call.
4. PostgreSQL detects backend exit and releases the lock.
5. Another worker acquires the same lock and also calls the API.
6. The old worker is still running.

Both workers are now **executing concurrently** even though the advisory lock ensured no two backends held the lock at the exact same moment.

An advisory lock is **not proof of exclusive ownership outside the database after a connection drops**.

### 19.1. Fencing Tokens Are Needed to Protect External Side Effects

A common pattern issues a **monotonically increasing fencing token** on each claim. Downstream systems reject requests carrying a token older than the newest accepted token.

Example:

```text
Worker A receives token 41
Worker A loses lease but keeps running

Worker B receives token 42
Downstream records token 42

Worker A sends request with token 41
Downstream rejects because token 41 is stale
```

Advisory locks **do not generate fencing tokens** or force external APIs to enforce them. That is an additional design layer.

### 19.2. For DB-Only Work, Transaction-Level Is Usually Clear Enough

When the entire business operation executes inside one PostgreSQL transaction, xact-level locks work well because lock ownership matches commit/rollback atomicity.

Whenever work outlives a transaction, design **durable state, leases, and idempotency** rather than holding transactions open indefinitely or mistaking session locks for TTL-based distributed locks.

## 20. Timeouts: Preventing Workers from Waiting Forever

### 20.1. `lock_timeout`

In PostgreSQL:

```sql
BEGIN;

SET LOCAL lock_timeout = '2s';

SELECT pg_advisory_xact_lock(820, 1);

-- Continues only if lock was acquired successfully.
SELECT status
FROM lock_lab.jobs
WHERE job_id = 1001;

COMMIT;
```

If the lock is not acquired within the limit, PostgreSQL throws a lock timeout error. The transaction enters an aborted state and requires `ROLLBACK`.

`SET LOCAL` applies only to the current transaction, avoiding leaking timeout changes to future requests reusing the pooled connection.

### 20.2. `statement_timeout`

```sql
BEGIN;

SET LOCAL statement_timeout = '5s';

SELECT pg_advisory_xact_lock(820, 1);

ROLLBACK;
```

`statement_timeout` limits **statement execution duration**, including time spent waiting if the statement has not completed.

Differences:

- `lock_timeout` targets **time spent waiting to acquire a lock**.
- `statement_timeout` limits total statement duration.
- `idle_in_transaction_session_timeout` targets sessions **idle inside a transaction**, not every session holding a session-level lock.

### 20.3. Use Try Functions When You Do Not Want to Wait

If the rule is "skip if another worker is busy," rather than a tiny timeout, it is usually clearer to use:

```sql
SELECT pg_try_advisory_xact_lock(820, 1) AS acquired;
```

Ensure this runs inside the transaction wrapping the protected work. Under autocommit, `true` lasts only for that single statement.

### 20.4. When a Statement Is Canceled

If a session-level advisory lock **was already acquired earlier**, canceling another statement or rolling back a transaction **does not release** that session lock.

For xact-level locks, they release when the transaction ends; if a statement error leaves the transaction aborted while the client keeps the transaction open, explicitly roll back to release resources.

## 21. Deadlocks with Advisory Locks

Advisory locks can deadlock just like any other lock when backends acquire multiple keys in inconsistent orders.

### 21.1. Wait Cycle Example

**Session A:**

```sql
BEGIN;

SELECT pg_advisory_xact_lock(830, 1);
-- A holds key (830,1).

SELECT pg_advisory_xact_lock(830, 2);
-- Must wait for B.
```

**Session B:**

```sql
BEGIN;

SELECT pg_advisory_xact_lock(830, 2);
-- B holds key (830,2).

SELECT pg_advisory_xact_lock(830, 1);
-- Must wait for A.
```

Execute in exact interleaving to form a cycle:

1. A acquires `(830,1)`.
2. B acquires `(830,2)`.
3. A requests `(830,2)` and waits.
4. B requests `(830,1)` and waits.

PostgreSQL's deadlock detector aborts one transaction with:

```text
SQLSTATE 40P01: deadlock_detected
```

**Test deadlocks only in a lab database**, never in production.

### 21.2. Preventing Deadlocks with Consistent Lock Ordering

If a workflow must lock jobs 1001 and 1002, every worker must acquire them in the same order, such as ascending ID:

```sql
BEGIN;

SELECT pg_advisory_xact_lock(700, 1001);
SELECT pg_advisory_xact_lock(700, 1002);

-- Work requiring both locks.

COMMIT;
```

Other workers must also lock 1001 before 1002 to avoid each holding one lock while waiting for the other.

Do not standardize only the order among **advisory locks** while forgetting **row/table locks** in the same workflow. If transaction A takes advisory lock then row lock, while B takes row lock then advisory lock, they can still deadlock.

### 21.3. Reentrancy and Lock Upgrades Also Need Care

Two sessions holding shared locks and then both trying to upgrade to exclusive can deadlock depending on timing. Avoid "acquire shared then upgrade to exclusive" patterns unless you have accounted for deadlocks and retries.

If the operation knows it needs exclusive access upfront, acquire exclusive from the start.

### 21.4. Deadlock Aborts Differ from Session-Level Cleanup

When a transaction aborts due to deadlock:

- Transaction-level advisory locks are released as the transaction ends.
- **Already-held session-level advisory locks can remain held** after transaction rollback.

So if using session-level locks in a deadlock-prone workflow, design explicit application cleanup.

## 22. Observing Advisory Locks via `pg_locks`

PostgreSQL's `pg_locks` view displays advisory locks with:

```sql
locktype = 'advisory'
```

### 22.1. Listing Advisory Locks in the Database

```sql
SELECT
    pid,
    database,
    locktype,
    mode,
    granted,
    classid,
    objid,
    objsubid,
    waitstart
FROM pg_locks
WHERE locktype = 'advisory'
ORDER BY pid NULLS LAST, granted, mode;
```

Columns:

| Column | Meaning |
| --- | --- |
| `pid` | Backend PID holding or requesting the lock, when applicable |
| `database` | OID of the associated database |
| `locktype` | `advisory` for advisory locks |
| `mode` | Typically `ExclusiveLock` or `ShareLock` |
| `granted` | `true` if held, `false` if waiting |
| `classid`, `objid`, `objsubid` | Fields encoding the advisory key identifier |
| `waitstart` | Timestamp when wait started, if available by version/state |

Do not read one row in `pg_locks` as "exactly one function call." A session holding the same key multiple times tracks an internal hold count; the view does not necessarily show the reentrant acquisition count.

### 22.2. Filtering Locks Held by the Current Connection

```sql
SELECT
    pid,
    mode,
    granted,
    classid,
    objid,
    objsubid
FROM pg_locks
WHERE locktype = 'advisory'
  AND pid = pg_backend_pid();
```

Useful for checking which locks your current session holds.

### 22.3. Reading Key Format from `pg_locks`

In current PostgreSQL advisory-lock representation, `classid` and `objid` encode key values while `objsubid` distinguishes key signature:

- `objsubid = 1` indicates a `bigint` key.
- `objsubid = 2` indicates a two-`integer` key.

These fields belong to the **lock manager's internal layout**; applications should store business keys in real tables rather than relying on `pg_locks` as a state table.

### 22.4. Identifying Transactions Waiting on Advisory Locks

```sql
SELECT
    l.pid,
    l.mode,
    l.granted,
    l.waitstart,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.query
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
    ON a.pid = l.pid
WHERE l.locktype = 'advisory'
ORDER BY l.granted, l.waitstart NULLS LAST;
```

Seeing `granted = false` and `wait_event_type = 'Lock'` points to a backend waiting on an advisory lock.

### 22.5. Who Is Blocking a Backend?

```sql
SELECT
    a.pid AS waiting_pid,
    pg_blocking_pids(a.pid) AS blocking_pids,
    a.wait_event_type,
    a.wait_event,
    a.state,
    a.query
FROM pg_stat_activity AS a
WHERE EXISTS (
    SELECT 1
    FROM pg_locks AS l
    WHERE l.pid = a.pid
      AND l.locktype = 'advisory'
      AND NOT l.granted
)
ORDER BY a.pid;
```

`pg_blocking_pids(pid)` returns the PIDs blocking that backend per PostgreSQL's lock rules, without guessing from raw `pg_locks` rows alone.

### 22.6. Respect Privileges and Sensitive Data

Not every role can see full `query` strings of other sessions. Queries may contain sensitive literals.

Run monitoring queries within granted privileges; never dump raw parameterized or sensitive SQL into uncontrolled logs or tickets.

## 23. Releasing Session-Level Locks When Needed

### 23.1. Unlocking a Specific Key

```sql
SELECT pg_advisory_unlock(800, 1) AS released;
```

`true` indicates one matching hold count was released; if the session acquired it multiple times, multiple unlocks are needed.

For shared session locks:

```sql
SELECT pg_advisory_unlock_shared(810, 1)
    AS released;
```

### 23.2. `pg_advisory_unlock_all()`

PostgreSQL provides:

```sql
SELECT pg_advisory_unlock_all();
```

This releases **all session-level advisory locks held by the current backend**. It is **not** an API for releasing transaction-level advisory locks.

**Never call `pg_advisory_unlock_all()` recklessly on a shared connection.** It can release session locks held by other libraries or components on that backend, breaking concurrency coordination.

### 23.3. When a Backend Exits

PostgreSQL automatically releases session advisory locks when the backend/session truly exits. Yet a network drop can make the client think the connection died before the backend detects it; do not assume instantaneous release in every environment.

### 23.4. No "Unlock by Key from Another Session"

If Session A holds a lock, Session B cannot call `pg_advisory_unlock` to strip A's ownership. Recovering a stuck session requires operational tooling to verify backend, request owner, and termination consequences.

Terminating a backend aborts running work, rolls back transactions, and releases all its locks; this is a sensitive operational action, not routine lock release.

## 24. SQL Evaluation Order: Avoid Acquiring Unintended Advisory Locks

Advisory locks are invoked via SQL functions with **side effects on the lock manager**. Be careful placing them in `SELECT`s with `LIMIT`, filters, or joins.

### 24.1. Misleading Pattern

```sql
-- DO NOT rely on this to guarantee only 5 locks are taken:
SELECT pg_advisory_lock(900, job_id)
FROM lock_lab.jobs
ORDER BY job_id
LIMIT 5;
```

Never assume a lock-acquiring expression is evaluated **strictly after `LIMIT`** in the exact order you picture. Query optimization and evaluation order can take more locks than expected in complex queries.

Especially with session-level locks, unintended locks persist after the `SELECT` finishes without the application tracking them to unlock.

### 24.2. Select the List First, Then Call the Lock Function

If you genuinely must lock a bounded set:

```sql
WITH selected_jobs AS MATERIALIZED (
    SELECT job_id
    FROM lock_lab.jobs
    WHERE status = 'PENDING'
    ORDER BY job_id
    LIMIT 5
)
SELECT pg_advisory_xact_lock(900, job_id)
FROM selected_jobs;
```

`MATERIALIZED` (on PostgreSQL versions supporting this syntax) enforces an evaluation boundary around the selected jobs, expressing the intent to **pick up to five rows before locking**.

Still:

- Avoid batch session-level locks without tracking and unlocking every key.
- With multiple keys, enforce a **consistent lock order** to minimize deadlocks.
- Never assume one `SELECT` calling lock functions over multiple rows guarantees strict evaluation order solely from an outer `ORDER BY`.
- When strict order is mandatory, fetch the sorted list and acquire locks sequentially in controlled application code or procedures.

### 24.3. Locking One Specific Resource Is Easiest to Control

Whenever possible:

```sql
BEGIN;

SELECT pg_advisory_xact_lock(700, 1001);

-- Business SQL for specifically job 1001.

COMMIT;
```

Acquiring one or a few intentional locks per transaction is far easier to debug and puts far less pressure on the lock table than acquiring tens of thousands of per-row advisory locks.

## 25. Performance and Resource Limits

Advisory locks are convenient, not free.

### 25.1. Lock Capacity Is Bounded

PostgreSQL tracks locks in shared memory structures. Capacity for many simultaneous locks depends on configuration and resources, including `max_locks_per_transaction` and active backend/transaction counts.

**Never acquire separate advisory locks for millions of IDs at once** thinking they are zero-cost. You can exhaust shared lock table space or hit resource errors.

### 25.2. Contention

If thousands of workers simultaneously call:

```sql
SELECT pg_advisory_xact_lock(700, 1001);
```

all contending on one key, throughput of that protected section is capped by lock hold duration.

Common optimizations:

- Keep critical sections short.
- Lock only the minimal required scope.
- Partition work cleanly by key.
- Use `pg_try_advisory_xact_lock` to move on to other work when busy.
- Avoid external network I/O while holding locks.
- Avoid holding unnecessary locks.

### 25.3. Session Locks Do Not Auto-Expire

PostgreSQL attaches no automatic business TTL to session advisory locks. As long as the session stays alive, a leaked lock can sit held indefinitely.

A statement timeout is not a "lease TTL" for held session locks.

### 25.4. `EXPLAIN` Does Not Replace Lock Monitoring

A query can be fast with zero contention yet crawl when waiting on another worker's advisory lock. To diagnose, monitor:

- `pg_locks.granted`.
- `pg_stat_activity.wait_event_type`/`wait_event`.
- `pg_blocking_pids`.
- Transaction hold times.
- Wait durations, timeouts, and deadlocks in logs/metrics.

Benchmark lock performance under **concurrent load**, not single-session `SELECT` timing alone.

## 26. Comparing Advisory Locks with Other Tools

| Tool | Use when | Caveats |
| --- | --- | --- |
| `pg_advisory_xact_lock` | Coordinating a logical resource within a transaction | Auto-released at commit/rollback |
| `pg_advisory_lock` | Lock must span transactions on one pinned physical session | Must unlock manually; leaks easily in pools |
| `SELECT ... FOR UPDATE` | Protecting/updating concrete existing rows | Uses row locks directly |
| `FOR UPDATE SKIP LOCKED` | Worker queues claiming rows while skipping busy ones | Wrong if skipping a row breaks business logic |
| `UNIQUE` / `PRIMARY KEY` | Enforcing data uniqueness | Works even if clients ignore advisory conventions |
| `CHECK` / `FOREIGN KEY` | Enforcing relational invariants | Not replaced by advisory locks |
| `SERIALIZABLE` | Preventing serialization anomalies | Requires full-transaction retries |
| Lease + fencing token | Long tasks or external side effects across systems | Needs ownership protocol beyond advisory locks |
| Message queue with claim/ack | Asynchronous task distribution, retries, tracking | Must handle idempotency/delivery semantics |

### 26.1. Why Not Use `FOR UPDATE` Everywhere?

When the locked entity is an **abstract logical name** with no corresponding table row, an advisory lock is cleaner than creating dummy mutex rows.

For example, "only one migration for module X runs at a time" maps neatly to a fixed advisory key.

Conversely, for "claim an existing `jobs` row," `SELECT ... FOR UPDATE SKIP LOCKED` inside a transaction expresses it directly without designing integer namespaces.

### 26.2. Advisory Locks Do Not Replace `UNIQUE`

To prevent two requests from generating duplicate invoices, advisory locks reduce contention, yet you still need a data constraint:

```sql
CREATE TABLE lock_lab.invoice_batches (
    customer_id integer NOT NULL,
    report_month date NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (customer_id, report_month)
);
```

Even if a worker forgets to acquire the advisory lock, the constraint blocks committing two rows with duplicate `(customer_id, report_month)`.

### 26.3. Advisory Locks Do Not Automatically Prevent Write Skew

Two transactions can read a multi-row invariant and then update different rows. Unless they acquire **the exact same advisory key** representing that invariant, per-row/per-ID locks will not stop write skew.

To guard an invariant with advisory locks, lock the **shared logical resource**, ensure every write path cooperates, and verify snapshot/transaction logic.

In many cases, `SERIALIZABLE` or a redesigned schema constraint is far easier to prove correct.

## 27. Practical Pattern: Preventing Overlapping Cron Runs

Suppose a cron job fires every minute, yet an aggregation run can take 90 seconds. You want to prevent the next run from overlapping the active run.

### 27.1. When Work Fits Entirely Inside One Transaction

```sql
BEGIN;

SELECT pg_try_advisory_xact_lock(1000, 1) AS acquired;

-- If acquired=false: roll back and skip this tick.
-- If true: compute and write data inside the transaction.

COMMIT;
```

Above is the **control skeleton**; the client must read `acquired` and decide whether to run the subsequent SQL.

### 27.2. When Cron Must Call External APIs

If the cron job must:

1. Read the database.
2. Call an external API for several minutes.
3. Write results back.

Holding a PostgreSQL transaction open for minutes just to retain an xact advisory lock is risky. Consider instead:

- Claim a run record via `UNIQUE`/row lock in a short transaction.
- Record owner/lease/version or fencing token.
- Commit.
- Call the external API with an idempotency key.
- Write results using ownership re-validation.

A session-level advisory lock can be convenient for a batch process using **one dedicated session** without strict fencing needs, provided you accept that losing the connection releases the lock even if external work is still running.

### 27.3. Never Use Locks as the Sole Source of Truth

Even when the scheduler says "the job is not running," persist state and progress in a table so you can:

- Recover from crashes.
- Audit run history.
- Perform controlled retries.
- Reconcile outcomes.
- Distinguish "pending," "running," "done," and "failed."

Locks express **temporary coordination rights**, not durable job history.

## 28. Practical Pattern: Only One Migration/Maintenance Process at a Time

A deployment tool can acquire a fixed logical key:

```sql
BEGIN;

SELECT pg_advisory_xact_lock(1100, 1);

-- Inspect schema version and run operations
-- permitted by PostgreSQL inside a transaction block.

COMMIT;
```

When all deployment steps are transactional and run inside one transaction, xact-level locking is clean and self-cleaning.

### 28.1. Not All DDL Can Run Inside a Transaction Block

For instance, `CREATE INDEX CONCURRENTLY` cannot run inside an explicit transaction block.

If maintenance requires statements **outside a transaction**, you cannot wrap everything in one xact-level lock assuming it stays held across commands.

If considering session-level locks for multi-transaction deployment flows, ensure:

- All commands run on the exact **same physical PostgreSQL session**.
- `unlock` executes on every exit path.
- Transaction pooling is not multiplexing backends.
- Disconnects, per-step rollback, and state verification before retries are handled.
- Advisory locks are never treated as a recovery tool after a broken migration.

### 28.2. Do Not Lock Multi-Database Migrations with One Key

Advisory locks are local to each database/cluster lock manager. If a deployment runs across two separate databases, the same key provides zero mutual exclusion across them.

Multi-database coordination requires an external coordinator or a single shared source of ownership.

## 29. Troubleshooting Common Issues

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `pg_try_advisory_lock` returns `true` despite thinking another worker holds it | Same physical backend already holds lock; reentrant | Test with two distinct backend PIDs |
| Session B keeps getting `false` even after A rolled back | A holds a **session-level lock** | Call unlock on A or close A's backend |
| `pg_advisory_xact_lock` succeeds yet job runs twice | Autocommit released lock right after statement | Wrap entire critical section in explicit transaction |
| Two "identical numeric" keys do not conflict | One uses `bigint`, the other `(int,int)` | Standardize key signature |
| No conflict observed between two environments | Different databases or clusters | Understand lock-manager scope |
| Worker acquires lock yet acts on stale status | Read data before acquiring or stale snapshot | Re-read after locking; check isolation |
| `REPEATABLE READ` still sees old data after lock wait | Snapshot already fixed | Use `READ COMMITTED` or retry/redesign |
| Exclusive lock blocked even with only readers | Readers hold shared advisory lock on same key | Follow compatibility rules |
| Rollback executed yet session lock remains held | Session locks are independent of transactions | Clean up in `finally` |
| One unlock ran yet lock remains held | Session acquired same key multiple times | Unlock matching count or track ownership |
| `pg_advisory_unlock` returns `false` | Current backend does not hold that session lock | Verify PID and key |
| `pg_advisory_unlock_all` breaks unrelated coordination | Released session locks owned by other logic on same backend | Unlock only keys you acquired |
| Worker hangs forever | Blocking call and slow lock holder | Use `try`/timeouts and monitor blocking PIDs |
| `lock_timeout` puts transaction in aborted state | Lock wait error failed transaction | `ROLLBACK` and handle per policy |
| Multi-key conflict raises `40P01` | Opposite lock acquisition order | Standardize lock order and retry whole transaction |
| Connection returned to pool while lock still held | Leaked session-level lock | Clean up on exact physical connection; prefer xact-level |
| PgBouncer transaction pooling breaks unlock | Backend switched between transactions | Avoid session locks across transactions |
| Two workers call API after A drops DB connection | Advisory locks are not distributed fencing | Use leases, fencing tokens, and idempotency |
| Duplicate data despite advisory lock | Another client ignored lock convention | Add `UNIQUE`/`PRIMARY KEY` |
| Thousands of locks grow shared memory usage | Too many concurrent keys | Lock fewer keys; use worker queues or row locks |
| Locking inside `SELECT ... LIMIT` behaves unexpectedly | Evaluation order differs from expectation | Materialize bounded set first, then lock safely |
| `pg_locks` does not show reentrant hold count | View is not a full ownership counter | Track acquire/unlock counts in application |
| Plain queries still run while exclusive advisory lock held | Advisory locks do not block normal SQL | All coordinating paths must use the same lock |

## 30. Practice Exercises with Answers

Use the `lock_lab` schema and test connections. For session-level exercises, remember to unlock afterward; for xact-level, end the transaction to release.

### Exercise 1. Transaction-Level Lock on Job 1001

Requirement: use namespace 700, holding the lock only within one transaction.

```sql
BEGIN;

SELECT pg_advisory_xact_lock(700, 1001);

SELECT status
FROM lock_lab.jobs
WHERE job_id = 1001;

COMMIT;
```

**Answer:** exclusive lock `(700,1001)` is released automatically at `COMMIT`.

### Exercise 2. Non-Blocking Try-Lock

```sql
BEGIN;

SELECT pg_try_advisory_xact_lock(700, 1001)
    AS acquired;

ROLLBACK;
```

**Answer:** `true` if acquired; `false` if another backend holds a conflicting lock. `ROLLBACK` releases the lock if acquired.

### Exercise 3. Does a Session Lock Release on COMMIT?

```sql
SELECT pg_advisory_lock(800, 11);

BEGIN;
SELECT 1;
COMMIT;
```

**Answer:** no. The session still holds `(800,11)`; you must call:

```sql
SELECT pg_advisory_unlock(800, 11);
```

or close the session.

### Exercise 4. Does a Session Lock Release on ROLLBACK?

```sql
BEGIN;
SELECT pg_advisory_lock(800, 12);
ROLLBACK;
```

**Answer:** no. Call `pg_advisory_unlock(800,12)` in the same session holding the lock.

### Exercise 5. Does an Xact-Level Lock Have an Unlock Function?

**Answer:** no. It releases automatically when the transaction ends. `pg_advisory_unlock` works only on session-level locks.

### Exercise 6. Why Does Autocommit Leave the Next Statement Unprotected by an Xact-Level Lock?

**Answer:** when `SELECT pg_advisory_xact_lock(...)` finishes under autocommit, its transaction ends and the lock releases. You must issue `BEGIN` first and run all related SQL inside that same transaction.

### Exercise 7. Do One `bigint` and Two `integer`s Share a Key Space?

**Answer:** no. The two signatures occupy separate advisory key spaces. Standardize on one signature so workers actually contend on the same resource.

### Exercise 8. Session A Exclusive, Session B Try Exclusive

**Session A:**

```sql
SELECT pg_advisory_lock(800, 21);
```

**Session B:**

```sql
SELECT pg_try_advisory_lock(800, 21) AS acquired;
```

**Answer:** B gets `false`. Afterward, A unlocks `(800,21)`.

### Exercise 9. Why Does `pg_try_advisory_lock` Return True When the Same Session Already Holds the Key?

**Answer:** session advisory locks support reentrant re-acquisition. To test contention between workers, use distinct backends.

### Exercise 10. Two Acquires, One Unlock

```sql
SELECT pg_advisory_lock(800, 22);
SELECT pg_advisory_lock(800, 22);
SELECT pg_advisory_unlock(800, 22);
```

**Answer:** one hold remains active. Call:

```sql
SELECT pg_advisory_unlock(800, 22);
```

### Exercise 11. Are Shared/Shared Compatible?

**Answer:** yes. Two backends can hold shared advisory locks on the same key concurrently.

### Exercise 12. Are Shared/Exclusive Compatible?

**Answer:** no, across two independent backends. Exclusive waits until all conflicting shared holds are released.

### Exercise 13. Does `pg_try_advisory_xact_lock` Returning False Abort the Transaction?

**Answer:** no. `false` is a normal boolean value; the application chooses whether to roll back, skip, or try another key.

### Exercise 14. After Acquiring the Advisory Lock, Must You Still Check `status`?

**Answer:** yes. The lock only coordinates access temporarily. A later worker can acquire the lock after an earlier worker committed, finding the job already `RUNNING` or `DONE`.

### Exercise 15. Why SELECT Status After Acquiring?

**Answer:** data read prior to acquiring can become stale if another worker committed while you waited. Under `READ COMMITTED`, run the read as a separate statement after the lock is granted.

### Exercise 16. Does REPEATABLE READ Refresh Its Snapshot Upon Acquiring an Advisory Lock?

**Answer:** no. Once a snapshot is established, an advisory lock never refreshes it. You may still read stale data and must design isolation/retries appropriately.

### Exercise 17. Why Are Session Locks Hard to Use with Connection Pools?

**Answer:** request completion does not terminate the backend. Unless unlocked on every path, the pooled physical connection retains the lock and affects subsequent requests.

### Exercise 18. Does Transaction Pooling Keep the Same Backend Across Two Transactions?

**Answer:** not guaranteed. Thus acquiring a session-level advisory lock in one transaction and unlocking it in another can fail because the backend switched.

### Exercise 19. Write a Query to Inspect Advisory Locks

```sql
SELECT
    pid,
    mode,
    granted,
    classid,
    objid,
    objsubid
FROM pg_locks
WHERE locktype = 'advisory';
```

**Answer:** each row describes a lock entry reported by the lock manager, with `granted` showing held vs. waiting.

### Exercise 20. Find PIDs Blocking a Backend Waiting on an Advisory Lock

```sql
SELECT
    a.pid,
    pg_blocking_pids(a.pid) AS blockers
FROM pg_stat_activity AS a
WHERE EXISTS (
    SELECT 1
    FROM pg_locks AS l
    WHERE l.pid = a.pid
      AND l.locktype = 'advisory'
      AND NOT l.granted
);
```

**Answer:** `blockers` returns the blocking PIDs under PostgreSQL's lock rules.

### Exercise 21. In What Order Should Jobs 1001 and 1002 Be Locked to Reduce Deadlocks?

**Answer:** all workers must acquire in the same order, e.g. `(700,1001)` before `(700,1002)`, then commit/roll back to release.

### Exercise 22. What to Do Upon Receiving `40P01`?

**Answer:** roll back the failed transaction, review lock ordering, and retry the entire transaction if business logic allows, using bounded retries and backoff.

### Exercise 23. Distinguish `pg_advisory_unlock_all` from Rollback

**Answer:** `pg_advisory_unlock_all()` releases session-level locks held by the current backend; `ROLLBACK` ends the transaction and releases transaction-level locks automatically, without releasing session-level advisory locks.

### Exercise 24. Why Not Replace `UNIQUE` with an Advisory Lock?

**Answer:** advisory locks only work if every writer cooperates on the exact key. A client ignoring the lock can still insert duplicates unless the schema enforces `UNIQUE`/`PRIMARY KEY`.

### Exercise 25. Why Doesn't a String Hash Prove Uniqueness?

**Answer:** hash functions map arbitrary strings into a finite range, so collisions can occur. If collisions are unacceptable, use unique ID mappings or another locking mechanism.

### Exercise 26. How Do `lock_timeout` and `statement_timeout` Differ?

**Answer:** `lock_timeout` caps time waiting to acquire a lock; `statement_timeout` caps total statement execution time. If a timeout error aborts the transaction, roll back.

### Exercise 27. Why Is an Advisory Session Lock Not a TTL Lease?

**Answer:** it does not auto-expire after a business interval. It stays held until unlocked or session exit; on network loss, external worker work may still continue.

### Exercise 28. When Is a Fencing Token Needed?

**Answer:** when a worker can lose ownership yet keep causing external side effects. Monotonically increasing tokens let downstream systems reject stale workers once ownership transfers.

### Exercise 29. Why Avoid Acquiring Advisory Locks Arbitrarily via `SELECT ... LIMIT`?

**Answer:** evaluation order of side-effecting lock calls relative to filters/`LIMIT` may differ from intuition. Materialize and bound the target set first, then lock cleanly.

### Exercise 30. When Should You Use `FOR UPDATE SKIP LOCKED` Instead of an Advisory Lock?

**Answer:** when a worker queue is modeled as **existing job rows** and multiple workers should claim distinct rows without inventing an integer namespace. Understand row locks and job state transitions.

### Exercise 31. How Long Does a Transaction-Level Lock Stay Held If the Transaction Sits Idle?

**Answer:** until the transaction ends, not just while `pg_advisory_xact_lock` executes. Avoid prolonged `idle in transaction` states.

### Exercise 32. Worker Claims, COMMITs, Then Calls API: Is the Lock Still Held?

**Answer:** no. The xact-level advisory lock released at commit. To prevent two workers from running the same post-commit task, track ownership, state, leases, and idempotency explicitly.

### Exercise 33. Does a Shared Advisory Lock Block an SQL UPDATE Not Using Advisory Locks?

**Answer:** not automatically. `UPDATE` uses row/table locks; a shared advisory lock coordinates only with other advisory calls using the same key.

### Exercise 34. Should You Call `pg_advisory_unlock_all` for Pool Housekeeping?

**Answer:** not indiscriminately. It can release session locks held by other code sharing that backend. Track ownership explicitly and unlock only the keys you acquired.

### Exercise 35. Naming a Namespace and Choosing Locks for a Report Export Workflow

A system runs report exports per `customer_id` and wants only one customer report processed per transaction at a time.

**Suggested solution:**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT pg_advisory_xact_lock(701, 101);

SELECT request_id, status
FROM lock_lab.report_requests
WHERE customer_id = 101
  AND report_month = DATE '2026-10-01';

-- Verify status; conditional UPDATE/INSERT
-- backed by UNIQUE(customer_id, report_month).

COMMIT;
```

If business rules must distinguish **customer and month** so different months for the same customer do not block each other, `(701, customer_id)` is **too coarse**. Use a unique mapping designed for `(customer_id, report_month)`, or coordinate via rows and `UNIQUE`, avoiding ad-hoc hash collisions.

## 31. Pre-Deployment Advisory Lock Checklist

| Question | How to decide |
| --- | --- |
| What logical resource is locked? | Define keys clearly; avoid locking too broad or too narrow |
| Which clients must honor the key? | Include every code path that can contend |
| How many databases/clusters exist? | Advisory locks do not coordinate across separate databases |
| One `bigint` or two `integer`s? | Standardize signature and namespace |
| Can keys collide? | Avoid unchecked hashing |
| How long must the lock live? | Choose session-level vs. transaction-level |
| Does all work fit inside one transaction? | Prefer xact-level |
| Is there a connection pool? | Avoid leaking session-level locks |
| Is PgBouncer transaction pooling used? | Never span transactions with session locks |
| Is autocommit enabled? | Open an explicit transaction for xact-level |
| Shared or exclusive mode? | Understand compatibility rules |
| Wait or skip when busy? | Blocking vs. `pg_try_advisory...` |
| What if waiting takes too long? | Timeouts, cancellation, metrics |
| Was data read before acquiring? | Re-read after lock is granted |
| What is the transaction isolation? | `READ COMMITTED` vs. `REPEATABLE READ` snapshots |
| Is state verified after acquiring? | Status, permissions, `UPDATE` row count |
| Do constraints protect correctness? | Never replace `UNIQUE`/FK/CHECK with advisory locks |
| How many locks per transaction? | Keep count low to avoid exhausting shared memory |
| Is multi-key ordering consistent? | Prevent deadlocks |
| Are row locks also taken in the workflow? | Audit overall lock acquisition order |
| Are there external side effects? | Consider outbox, idempotency, fencing |
| What if a worker crashes or disconnects? | Design state recovery |
| Is session-level cleanup solid? | Unlock on exact backend inside `finally` |
| Are calls nested/reentrant? | Track acquire/unlock hold counts |
| Are monitoring queries ready? | `pg_locks`, `pg_stat_activity`, blocking PIDs |
| Tested with two distinct backend PIDs? | Avoid false confidence from reentrancy |
| Tested timeout/deadlock/rollback paths? | Crucial failure scenarios |
| Are transactions time-bounded? | Prevent long `idle in transaction` |
| Need cross-cluster coordination? | If yes, use an external mechanism |
| Is `try=false` handling defined? | Appropriate `BUSY`/`SKIPPED`/`RETRY` behavior |

## 32. Summary

**Advisory locks** in PostgreSQL are a concurrency coordination tool keyed by **application-chosen logical identifiers**. They shine when the locked resource does not map to a single table row or when workers need to coordinate execution rights.

Key points to remember:

1. **Session-level**: `pg_advisory_lock` / `pg_try_advisory_lock` survive `COMMIT` and `ROLLBACK`, persisting until the same session unlocks them or the backend exits.
2. **Transaction-level**: `pg_advisory_xact_lock` / `pg_try_advisory_xact_lock` release automatically when the transaction ends. There is no separate xact unlock function.
3. **Shared and exclusive** follow compatibility rules: multiple shared holders coexist, while exclusive conflicts with other holders on the same key.
4. **Blocking functions** wait; **try functions** return a boolean immediately. `false` is not an SQL exception, and `true` does not prove business state is valid.
5. **`bigint` and `(int,int)` occupy separate namespaces**; standardize key signatures and namespace design.
6. **Advisory locks are cooperative**: clients ignoring the key still read/write tables freely; `UNIQUE`/PK/FK/CHECK remain mandatory.
7. **Lock first, then re-read state**. Under `READ COMMITTED`, keep acquire and business `SELECT` in **two separate statements** so you do not read from a pre-wait snapshot.
8. **`REPEATABLE READ` does not refresh its snapshot when an advisory lock is granted**. Logical locks and MVCC visibility are separate mechanisms.
9. **Autocommit releases xact-level locks right after the statement**, before subsequent work even starts.
10. **Connection pools and PgBouncer transaction pooling** make session-level locks especially error-prone unless backend ownership is strictly controlled.
11. **Deadlocks and timeouts can still happen**; enforce consistent lock ordering, monitor waits, and retry entire transactions where appropriate.
12. **`pg_locks` and `pg_blocking_pids`** help inspect holders and waiters; never confuse this metadata with a durable job state table.
13. **Advisory locks are not distributed leases with fencing**. If a disconnected worker can still cause external side effects, build proper ownership, idempotency, and fencing.
14. **Keep transactions and critical sections short**, avoid locking huge key sets at once, and avoid bulk session locks without strict cleanup.

A clean default template for database-contained work:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

-- 1. Coordinate on a deterministic logical key.
SELECT pg_advisory_xact_lock(700, 1001);

-- 2. Read state in a separate statement AFTER acquiring the lock.
SELECT status
FROM lock_lab.jobs
WHERE job_id = 1001;

-- 3. Conditional update, verifying row count.
UPDATE lock_lab.jobs
SET status = 'RUNNING',
    attempt_count = attempt_count + 1
WHERE job_id = 1001
  AND status = 'PENDING'
RETURNING job_id, status;

-- 4. Commit only once business logic confirms a valid outcome.
COMMIT;
```

**Core rule:** before calling an advisory lock function, answer three questions: **which logical resource is locked, how long must it stay held, and what happens if the transaction or connection fails?** Answering those three questions clearly guides the choice between **session-level** and **transaction-level** locks and prevents subtle concurrency bugs.
