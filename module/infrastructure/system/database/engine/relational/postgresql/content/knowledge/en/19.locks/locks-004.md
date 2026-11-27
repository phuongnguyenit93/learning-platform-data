# NOWAIT, SKIP LOCKED, and Lock-Waiting Choices in PostgreSQL

When two transactions want to lock or modify the same row, PostgreSQL usually makes the later transaction **wait** for the transaction holding the lock. This protects consistency, but not every application wants to wait indefinitely.

In an order-placement API, the application may want to **detect immediately** that a resource is busy so it can respond and retry later. In a background job system, a worker may want to **skip a job locked by another worker**, pick another available job, and keep working. Those two needs lead to crucial choices:

- **Default wait:** wait for the lock to be released, unless deadlock or timeout/cancel occurs.
- **`NOWAIT`:** if the **row lock** cannot be acquired immediately, raise an error instead of waiting.
- **`SKIP LOCKED`:** if a row cannot be locked immediately, **skip that row** and continue evaluating other rows.
- **`lock_timeout`:** allow waiting, but only up to a configured time limit.

Examples:

```sql
-- Wait for a locked row using default behavior.
SELECT *
FROM work_items
WHERE id = 10
FOR UPDATE;

-- Error immediately if the row cannot be locked.
SELECT *
FROM work_items
WHERE id = 10
FOR UPDATE NOWAIT;

-- Skip currently locked rows.
SELECT *
FROM work_items
WHERE status = 'PENDING'
ORDER BY id
LIMIT 5
FOR UPDATE SKIP LOCKED;
```

`work_items` is an illustrative table name; later sections create runnable tables.

**Core takeaway:** `NOWAIT` and `SKIP LOCKED` change **how row-lock conflicts are handled** by locking clauses such as `FOR UPDATE`. They do not replace transaction management, do not prevent every kind of blocking, and `SKIP LOCKED` in particular can yield **an inconsistent view compared to a normal read query**. Choose based on business requirements.

## 1. First: Row Locks and Table Locks Are Two Separate Layers

PostgreSQL has multiple locking mechanisms. For this topic, distinguish:

1. **Row-level locks:** protect updates, deletes, or specific interactions on individual rows.
2. **Table-level locks:** protect relations against incompatible operations such as certain DDL, `TRUNCATE`, or explicit `LOCK TABLE`.
3. **Other locks/waits:** transaction IDs, advisory locks, predicate locks, I/O, and internal engine resources are not synonymous with row locks.

A statement like:

```sql
SELECT *
FROM jobs
WHERE job_id = 101
FOR UPDATE;
```

does not merely say "lock one row." PostgreSQL also acquires a **`ROW SHARE` table-level lock** on the relation targeted by the locking clause, in addition to row-level locks on the selected rows.

Important consequence:

> `NOWAIT` and `SKIP LOCKED` in a locking clause apply only to **acquiring row locks**; they do not make acquiring **table-level locks** non-blocking.

If another transaction holds an `ACCESS EXCLUSIVE` table lock, such as from `TRUNCATE` or certain DDL, `SELECT ... FOR UPDATE SKIP LOCKED` still has to **wait at the table-lock layer** before it can reach the step of selecting and skipping rows.

### 1.1. Plain SELECT Locks

A `SELECT` without `FOR UPDATE` acquires `ACCESS SHARE` on the table and reads data via MVCC. It does not attempt to take row-level locks to block other transactions from updating rows.

For example:

```sql
SELECT account_id, balance
FROM lock_wait_lab.accounts
WHERE account_id = 1;
```

While another transaction holds a row lock from an `UPDATE`, a plain read query still reads the **committed version** per its snapshot. It does not "wait on the same row lock" the way `SELECT ... FOR UPDATE` does.

### 1.2. How Long Are Row Locks Held?

Normally, row locks acquired by `SELECT ... FOR UPDATE` are held until **the transaction ends** via `COMMIT` or `ROLLBACK`.

```sql
BEGIN;

SELECT *
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE;

-- The lock remains held while the transaction is open.

COMMIT;
```

Never run a locking `SELECT` and hold the transaction open while the application waits on a user, calls a slow API, or runs external computations for minutes. Held locks will block other transactions.

## 2. SELECT Locking Clauses

PostgreSQL supports four common row-level locking modes:

| Syntax | Primary meaning |
| --- | --- |
| `FOR UPDATE` | Strong lock when preparing to modify or delete a row |
| `FOR NO KEY UPDATE` | Lock for updates that do not alter relevant key values per PostgreSQL rules |
| `FOR SHARE` | Shared lock preventing incompatible updates or deletes |
| `FOR KEY SHARE` | Weaker shared lock, primarily protecting referenced keys |

Example:

```sql
SELECT *
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE;
```

Or:

```sql
SELECT *
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR NO KEY UPDATE;
```

Where appropriate, any of these locking clauses can take `NOWAIT` or `SKIP LOCKED`:

```sql
SELECT *
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE NOWAIT;

SELECT *
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR SHARE SKIP LOCKED;
```

### 2.1. Not Every Lock Conflicts with Every Other

Some modes are compatible and some conflict:

| Held lock / requested lock | `FOR KEY SHARE` | `FOR SHARE` | `FOR NO KEY UPDATE` | `FOR UPDATE` |
| --- | :---: | :---: | :---: | :---: |
| `FOR KEY SHARE` | Yes | Yes | Yes | No |
| `FOR SHARE` | Yes | Yes | No | No |
| `FOR NO KEY UPDATE` | Yes | No | No | No |
| `FOR UPDATE` | No | No | No | No |

"Yes" means the modes can coexist on the same row per the compatibility matrix; "No" means they conflict. This table describes **row-level lock modes** only and does not replace analyzing table locks, transaction isolation, and other conditions.

### 2.2. Why Is FOR NO KEY UPDATE Useful?

Many `UPDATE`s modify only ordinary columns without touching referenced keys, and PostgreSQL can use a lock mode weaker than `FOR UPDATE`. In schemas with foreign keys, this keeps `FOR KEY SHARE` reference checks from being blocked unnecessarily.

However, do not pick `FOR NO KEY UPDATE` merely because its name sounds "lighter": verify **what actually needs protection** and whether another transaction might modify or delete keys.

## 3. NOWAIT: Fail Immediately When a Row Lock Is Unavailable

Syntax:

```sql
SELECT column_list
FROM some_table
WHERE ...
FOR UPDATE NOWAIT;
```

When a transaction encounters a row locked in an incompatible mode by another transaction, `NOWAIT` tells PostgreSQL **not to wait for that row lock**. PostgreSQL raises an error with SQLSTATE **`55P03`** (*lock_not_available*).

Scenario example:

```text
Session A: BEGIN
Session A: SELECT account 1 FOR UPDATE
Session A: keeps the transaction open

Session B: SELECT account 1 FOR UPDATE NOWAIT
Session B: ERROR 55P03 (cannot obtain row lock immediately)
```

**`NOWAIT` does not mean the SQL statement executes in 0 milliseconds.** The database still must parse, plan, fetch data, execute other steps, and potentially wait on other locks. "No wait" specifically means **do not wait upon hitting a row-level lock conflict in the locking clause**.

### 3.1. When to Use NOWAIT

Reasonable examples:

- An API managing a resource where the client wants to know immediately that "another operation is in progress."
- A latency-sensitive job willing to retry with backoff when a row is busy.
- An administrative transaction needing to **attempt acquiring a lock** before executing a brief step.
- When the application can return "resource busy" and retry safely.

**Unreasonable** example: using `NOWAIT` to turn every brief write contention into an error even when waiting a few milliseconds would succeed. That can trigger retry storms, waste CPU, and reduce throughput.

### 3.2. How a NOWAIT Error Affects the Transaction

If `SELECT ... FOR UPDATE NOWAIT` fails inside `BEGIN`, PostgreSQL puts the current transaction into an aborted error state. Subsequent SQL statements cannot proceed until you either:

- `ROLLBACK` the entire transaction, or
- `ROLLBACK TO SAVEPOINT` if a savepoint was created before the failing statement.

Do not catch the exception in Java and keep running on the same connection/transaction as if the error left transaction state intact.

## 4. SKIP LOCKED: Skip Rows Currently Locked

Syntax:

```sql
SELECT column_list
FROM some_table
WHERE ...
ORDER BY ...
LIMIT ...
FOR UPDATE SKIP LOCKED;
```

When a row matches the condition but holds an incompatible row lock, PostgreSQL **skips that row** instead of waiting. Other eligible rows are selected and locked normally.

Example:

```text
Job #1: PENDING, worker A holds the lock
Job #2: PENDING, unlocked
Job #3: PENDING, unlocked

Worker B SELECT ... LIMIT 2 FOR UPDATE SKIP LOCKED
    -> picks #2 and #3
    -> does not wait on #1
```

### 4.1. Why Is This an "Inconsistent View"?

A normal read query sees rows #1, #2, and #3 in its snapshot. Yet `SKIP LOCKED` decides **not to return #1 because at the moment it attempts to lock the row, that row is locked**.

Thus the output depends on concurrent contention, not only committed data. Two runs with the same predicate can return **different sets of rows**.

This is intentional for **work queues**: a worker does not need every pending job, just **jobs it can claim right now**. However, it is generally **unsuitable for financial reports, inventory totals, stock checks, or queries requiring a complete, consistent data set**.

### 4.2. SKIP LOCKED Is Not "Lock-Free SELECT"

The rows that **are selected** are still locked under `FOR UPDATE` or the specified locking clause.

```sql
BEGIN;

SELECT job_id
FROM lock_wait_lab.jobs
WHERE status = 'PENDING'
ORDER BY priority DESC, job_id
LIMIT 2
FOR UPDATE SKIP LOCKED;

-- The two selected rows stay locked until COMMIT/ROLLBACK.

COMMIT;
```

If a worker only runs `SELECT` and commits **without marking the job as claimed**, the job remains `PENDING` and another worker can pick it up after commit. A proper queue must **update claim status in the same transaction**.

## 5. Three Approaches to Handling Lock Contention

| Option | When target row is locked | Typical outcome | Use when |
| --- | --- | --- | --- |
| `FOR UPDATE` | Waits until lock can be acquired | Reads/locks row after wait, or hits another error | Need the exact target row; waiting is acceptable |
| `FOR UPDATE NOWAIT` | Does not wait for row lock | `55P03` error on conflict | Need "try now" and fail fast |
| `FOR UPDATE SKIP LOCKED` | Skips locked row | Gets other rows; may return 0 rows | Worker can process alternative work |
| Wait with `lock_timeout` | Waits up to threshold | Acquires lock if freed in time; errors on timeout | Want bounded waiting |

No single option is universally best. **Right vs. wrong depends on whether "skipping a busy item" makes sense for the business logic.**

For example, a user withdrawing from account #1 cannot be switched to account #2 just because #1 is locked. For that workflow, `SKIP LOCKED` is dangerously wrong. Conversely, a worker sending queued emails can pick another job if one job is held by another worker.

## 6. Creating a Test Database: Accounts Table

All examples can be run in PostgreSQL on a **dedicated learning database**. Never create test data or hold locks on a production system.

### 6.1. Creating the Schema

```sql
CREATE SCHEMA IF NOT EXISTS lock_wait_lab;
```

### 6.2. Accounts Table

```sql
CREATE TABLE lock_wait_lab.accounts (
    account_id   INTEGER PRIMARY KEY,
    owner_name   TEXT NOT NULL,
    balance      NUMERIC(14, 2) NOT NULL
        CHECK (balance >= 0)
);

INSERT INTO lock_wait_lab.accounts
    (account_id, owner_name, balance)
VALUES
    (1, 'An', 1000.00),
    (2, 'Bình', 500.00),
    (3, 'Chi', 750.00);
```

Expected data:

| account_id | owner_name | balance |
| ---: | --- | ---: |
| 1 | An | 1000.00 |
| 2 | Bình | 500.00 |
| 3 | Chi | 750.00 |

In this lesson, `accounts` is used solely to observe locking. This is **not a real financial ledger**; real monetary workflows must verify affected row counts, enforce balance invariants, ensure idempotency, and keep an immutable transaction ledger.

## 7. Two-Session Practice: Default Waiting

Open **Session A** and **Session B** connected to **the same database** using two separate connections. Do not run steps from both sessions in a single transaction.

**Session A – hold lock on row #1:**

```sql
BEGIN;

SELECT
    account_id,
    balance
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE;

-- Do not COMMIT/ROLLBACK yet; A holds the row lock on account #1.
```

**Session B – attempt to acquire the same lock:**

```sql
BEGIN;

SELECT
    account_id,
    balance
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE;

-- B waits because A has not released the lock.
```

At this moment, B is waiting. Return to **Session A**:

```sql
COMMIT;
```

B resumes and acquires the row lock on #1. Finally in **Session B**:

```sql
COMMIT;
```

**Remember to end both transactions** before moving on to the next example.

### 7.1. Using Plain SELECT Instead of FOR UPDATE

Repeat Session A's step, but in B run:

```sql
SELECT account_id, balance
FROM lock_wait_lab.accounts
WHERE account_id = 1;
```

Normally this **does not wait on A's `FOR UPDATE` row lock**, because a non-locking `SELECT` reads a version matching its MVCC snapshot.

That does not mean reads can never wait on anything: an `ACCESS EXCLUSIVE` table lock or other resources can still block `SELECT`.

## 8. Two-Session Practice: NOWAIT

**Session A – hold the lock:**

```sql
BEGIN;

SELECT account_id, balance
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE;
```

**Session B – request without waiting:**

```sql
BEGIN;

SELECT account_id, balance
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE NOWAIT;
```

Because A holds an incompatible lock, B receives an error similar to:

```text
ERROR:  could not obtain lock on row in relation "accounts"
SQLSTATE: 55P03
```

The exact message text may vary by version and condition, but SQLSTATE `55P03` is the reliable indicator applications use to classify lock unavailability.

**Session B – clean up aborted transaction:**

```sql
ROLLBACK;
```

**Session A – release lock:**

```sql
COMMIT;
```

Now re-run in B:

```sql
BEGIN;
SELECT account_id, balance
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE NOWAIT;
COMMIT;
```

Once no conflicting transaction holds the lock, `NOWAIT` succeeds.

### 8.1. Handling the Error and Continuing in the Same Transaction

You can use a savepoint:

```sql
BEGIN;
SAVEPOINT before_try_lock;

SELECT account_id
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE NOWAIT;

-- If the SELECT above raises 55P03:
ROLLBACK TO SAVEPOINT before_try_lock;

-- After rolling back to the savepoint, the transaction can continue.
SELECT current_database();
COMMIT;
```

**Execute `ROLLBACK TO SAVEPOINT` only on the error branch.** If the `SELECT` succeeds, the application can `RELEASE SAVEPOINT before_try_lock` and continue or commit depending on the workflow.

In Java/JDBC, when catching `SQLException` with SQLSTATE `55P03`, roll back the transaction or roll back to a previously created savepoint; never keep running arbitrary SQL in an aborted transaction.

## 9. Two-Session Practice: SKIP LOCKED

**Session A – hold lock on account #1:**

```sql
BEGIN;

SELECT account_id
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE;
```

**Session B – attempt to lock all immediately lockable accounts:**

```sql
BEGIN;

SELECT account_id, balance
FROM lock_wait_lab.accounts
ORDER BY account_id
FOR UPDATE SKIP LOCKED;
```

While A holds the lock on account #1, B receives:

| account_id | balance |
| ---: | ---: |
| 2 | 500.00 |
| 3 | 750.00 |

Account #1 **does not appear** in B's result set because its lock is unavailable. B holds locks on rows #2 and #3 until its transaction ends.

**Session B:**

```sql
COMMIT;
```

**Session A:**

```sql
COMMIT;
```

Retry `FOR UPDATE SKIP LOCKED` after A has committed; this time all three rows are returned.

**Note:** `SKIP LOCKED` does not return a "skipped 1 row" flag; it simply **omits that row**. Do not use the returned row count to infer how many rows actually satisfy `WHERE`.

## 10. NOWAIT and SKIP LOCKED Do Not Apply Directly to UPDATE/DELETE

PostgreSQL supports these options through `SELECT` locking clauses. You cannot arbitrarily attach them to `UPDATE` or `DELETE`:

```sql
-- NOT valid PostgreSQL syntax:
-- UPDATE lock_wait_lab.accounts
-- SET balance = balance + 1
-- WHERE account_id = 1
-- NOWAIT;

-- NOT valid PostgreSQL syntax:
-- DELETE FROM lock_wait_lab.accounts
-- WHERE account_id = 1
-- SKIP LOCKED;
```

To **try acquiring the lock first and then `UPDATE`**, run both in the same transaction:

```sql
BEGIN;

SELECT account_id
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE NOWAIT;

-- Reached only if SELECT acquires the lock successfully.
UPDATE lock_wait_lab.accounts
SET balance = balance + 10
WHERE account_id = 1;

COMMIT;
```

If `SELECT` errors, the application must roll back or roll back to a savepoint and skip the `UPDATE`. When `SELECT` succeeds, the row lock is held until commit, preventing other transactions from intervening to modify the same row before `UPDATE`.

### 10.1. Longer Lock Hold Time Reduces Concurrency

Avoid:

```text
BEGIN
SELECT ... FOR UPDATE NOWAIT
call external HTTP API for 20 seconds
UPDATE ...
COMMIT
```

For 20 seconds, competing requests must wait or fail with `NOWAIT` on that row. If external systems must be called, split the workflow into short transactions with durable state/reservations instead of holding row locks across slow I/O.

## 11. Bounded Waiting Option: lock_timeout

Not every application wants to fail **immediately** or skip rows. Sometimes you want to wait up to a cap:

```sql
BEGIN;

SET LOCAL lock_timeout = '2s';

SELECT account_id, balance
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE;

COMMIT;
```

If the lock is released before the limit, the statement proceeds. If waiting to acquire the lock exceeds the limit, PostgreSQL throws a lock-unavailable error, typically SQLSTATE `55P03`.

`SET LOCAL` applies only to the current transaction. A session-level `SET lock_timeout = '2s'` can leak to subsequent statements in a connection pool unless reset properly; therefore `SET LOCAL` or explicit pool configuration is safer.

### 11.1. lock_timeout Is Not NOWAIT

- `NOWAIT`: never wait on a conflicting **row lock** in a locking clause.
- `lock_timeout`: wait up to the configured limit **when attempting to acquire a lock**, across lock types per PostgreSQL rules.
- One statement can acquire **multiple different locks**; `lock_timeout` applies to **each lock wait attempt**, not necessarily as a single cumulative budget for the entire statement.

For example, to avoid waiting indefinitely on a **table-level lock**, `lock_timeout` helps more than relying solely on row-level `NOWAIT`.

### 11.2. statement_timeout

`statement_timeout` bounds **total execution duration of a statement** per PostgreSQL rules, not just lock wait time:

```sql
BEGIN;

SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '10s';

SELECT account_id
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE;

COMMIT;
```

If a query runs slowly due to I/O, joins/sorts, or other causes, `statement_timeout` triggers as well. The error uses SQLSTATE `57014` (*query_canceled*), distinct from lock timeout.

**Precedence:** if `lock_timeout` is greater than or equal to `statement_timeout`, `lock_timeout` may have little or no independent effect in that statement because `statement_timeout` fires first.

### 11.3. idle_in_transaction_session_timeout

A session with an open transaction that sits **idle** can hold locks unnecessarily. PostgreSQL provides `idle_in_transaction_session_timeout` to terminate connections left idle in transaction too long per configured policy.

It is **not a timeout for a single row-lock wait** and should not replace `lock_timeout`. A session actively executing a query and waiting on a lock is `active`, not `idle in transaction`.

### 11.4. deadlock_timeout

`deadlock_timeout` controls how long PostgreSQL waits before running deadlock detection on a lock wait—not "a timeout that cancels every query waiting on a lock." DBAs tune it for workload and logging requirements; applications should not treat it as a replacement for `lock_timeout` or `statement_timeout`.

## 12. When NOWAIT Can Still Wait: Table Locks

An easily overlooked detail:

```sql
SELECT *
FROM lock_wait_lab.accounts
FOR UPDATE NOWAIT;
```

This statement needs a table-level `ROW SHARE` lock, and `NOWAIT` **does not apply** to acquiring that table lock. If another session holds `ACCESS EXCLUSIVE`:

```sql
-- Session A (isolated demo, never run in production):
BEGIN;
LOCK TABLE lock_wait_lab.accounts IN ACCESS EXCLUSIVE MODE;
-- Not committed yet.
```

then Session B waits at the table level before ever reaching the per-row `NOWAIT` step.

### 12.1. LOCK TABLE ... NOWAIT

When you want to attempt acquiring a table-level lock without waiting, PostgreSQL supports:

```sql
BEGIN;

LOCK TABLE lock_wait_lab.accounts
IN ROW SHARE MODE NOWAIT;

SELECT *
FROM lock_wait_lab.accounts
FOR UPDATE NOWAIT;

COMMIT;
```

Here:

- `LOCK TABLE ... IN ROW SHARE MODE NOWAIT` attempts to acquire the **table-level lock** without waiting.
- `FOR UPDATE NOWAIT` attempts to acquire **row-level locks** without waiting.
- Both must be considered if you want "fail fast" across multiple lock layers.

**Do not interpret this as guaranteeing a transaction can never block on anything:** other DDL, I/O, network stalls, secondary relations, triggers, and other locks can still apply.

### 12.2. A Practical Alternative

If you prefer not to split into two explicit lock statements, combine:

```sql
BEGIN;
SET LOCAL lock_timeout = '1s';

SELECT *
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE NOWAIT;

COMMIT;
```

Here, row-lock conflicts use `NOWAIT`, while table-level lock acquisition is bounded by `lock_timeout`. They are **two complementary mechanisms**, not synonymous keywords.

## 13. Creating a Job Queue Table

The classic use case for `SKIP LOCKED` is **multiple workers pulling jobs from a PostgreSQL table**. The following test table includes status, priority, readiness timestamp, attempt counts, and leases.

### 13.1. Defining the jobs Table

```sql
CREATE TABLE lock_wait_lab.jobs (
    job_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'RUNNING', 'DONE', 'FAILED')),
    priority INTEGER NOT NULL DEFAULT 0,
    ready_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    attempt_count INTEGER NOT NULL DEFAULT 0
        CHECK (attempt_count >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 3
        CHECK (max_attempts > 0),
    claimed_by TEXT,
    claimed_at TIMESTAMPTZ,
    lease_until TIMESTAMPTZ,
    lease_token BIGINT NOT NULL DEFAULT 0,
    completed_at TIMESTAMPTZ,
    last_error TEXT
);
```

Column explanations:

| Column | Purpose |
| --- | --- |
| `job_id` | Unique identifier |
| `job_type`, `payload` | Job category and data |
| `status` | Pending, running, completed, or failed state |
| `priority` | Higher priority jobs are picked first |
| `ready_at` | Job is eligible only once its scheduled time arrives |
| `attempt_count` / `max_attempts` | Bounded retry tracking |
| `claimed_by` | Worker currently recorded as job owner |
| `claimed_at` / `lease_until` | Claim timestamp and processing deadline |
| `lease_token` | Monotonic version incremented per claim to block stale workers from completing |
| `completed_at`, `last_error` | Completion timestamp and diagnostics |

**Row locks** protect only the claim phase inside a transaction. **Leases and durable state** allow workers to process outside the transaction without holding transactions open for the entire job duration.

### 13.2. Inserting Six Jobs

```sql
INSERT INTO lock_wait_lab.jobs
    (job_type, payload, priority, ready_at)
VALUES
    ('email', '{"recipient":"a@example.test"}'::jsonb,
     10, clock_timestamp() - INTERVAL '1 minute'),
    ('email', '{"recipient":"b@example.test"}'::jsonb,
      9, clock_timestamp() - INTERVAL '1 minute'),
    ('report', '{"month":"2026-10"}'::jsonb,
      8, clock_timestamp() - INTERVAL '1 minute'),
    ('email', '{"recipient":"c@example.test"}'::jsonb,
      5, clock_timestamp() - INTERVAL '1 minute'),
    ('report', '{"month":"2026-09"}'::jsonb,
      5, clock_timestamp() - INTERVAL '1 minute'),
    ('cleanup', '{"scope":"demo"}'::jsonb,
      2, clock_timestamp() - INTERVAL '1 minute');
```

On a freshly created table with an unused identity sequence, jobs receive IDs 1–6. If you have inserted multiple times or reset sequences, **check the actual IDs** rather than assuming IDs 1–6.

### 13.3. Index for Workers

```sql
CREATE INDEX idx_lock_wait_jobs_ready
ON lock_wait_lab.jobs
    (priority DESC, ready_at, job_id)
WHERE status = 'PENDING';
```

This partial index narrows lookups to `PENDING` jobs and provides common ordering keys. However, due to `ORDER BY priority DESC, ready_at, job_id` and `ready_at <= now()`, the planner may still sort or choose another plan depending on table size and data distribution.

An index alone does not guarantee `SKIP LOCKED` is always fast, because row locks, heap fetches, bloat, worker count, job state churn, and concurrency all matter. Measure under realistic load.

## 14. Two-Worker Example Using SKIP LOCKED

Assume the `jobs` table was just seeded and all jobs are `PENDING`.

**Session A – worker A locks the highest-priority job:**

```sql
BEGIN;

SELECT job_id, priority, status
FROM lock_wait_lab.jobs
WHERE status = 'PENDING'
ORDER BY priority DESC, ready_at, job_id
LIMIT 1
FOR UPDATE SKIP LOCKED;

-- On the freshly seeded schema, picks job #1.
-- Do not COMMIT yet, to observe contention.
```

**Session B – worker B picks another job:**

```sql
BEGIN;

SELECT job_id, priority, status
FROM lock_wait_lab.jobs
WHERE status = 'PENDING'
ORDER BY priority DESC, ready_at, job_id
LIMIT 1
FOR UPDATE SKIP LOCKED;

-- While A holds #1, B picks #2.

ROLLBACK;
```

**Session A – clean up example:**

```sql
ROLLBACK;
```

Because A and B only ran `SELECT` and rolled back, **no job transitioned to `RUNNING`**. This is a row-lock experiment, not a complete job processor.

### 14.1. Why Did B Not See Job #1?

`SKIP LOCKED` skips rows holding an incompatible lock from A, even though job #1's committed status is still `PENDING`.

### 14.2. Why Not Simply SELECT and Hand the Job to the Worker?

If A runs `SELECT` and commits before updating status, worker C can pick the exact same job #1 as soon as the lock is released. Therefore, **selecting and marking the job as "claimed" must happen in the same transaction**, ideally as an atomic claim operation.

## 15. Atomic Claim Pattern: CTE + UPDATE ... RETURNING

Goal: multiple workers run concurrently; each takes **up to two unlocked, ready jobs**, marks them `RUNNING` in the same transaction, and returns their payloads and tokens.

```sql
BEGIN;

WITH candidates AS (
    SELECT job_id
    FROM lock_wait_lab.jobs
    WHERE status = 'PENDING'
      AND ready_at <= now()
      AND attempt_count < max_attempts
    ORDER BY priority DESC, ready_at, job_id
    LIMIT 2
    FOR UPDATE SKIP LOCKED
)
UPDATE lock_wait_lab.jobs AS j
SET
    status = 'RUNNING',
    claimed_by = 'worker-A',
    claimed_at = clock_timestamp(),
    lease_until = clock_timestamp() + INTERVAL '2 minutes',
    attempt_count = j.attempt_count + 1,
    lease_token = j.lease_token + 1,
    last_error = NULL
FROM candidates AS c
WHERE j.job_id = c.job_id
RETURNING
    j.job_id,
    j.job_type,
    j.payload,
    j.priority,
    j.attempt_count,
    j.lease_token,
    j.lease_until;

COMMIT;
```

### 15.1. Why Does This Pattern Prevent Two Workers from Claiming the Same Job?

1. The CTE selects eligible `PENDING` rows.
2. `FOR UPDATE SKIP LOCKED` attempts to lock each selected row; jobs locked by another worker are skipped.
3. `UPDATE ... FROM candidates` updates the rows **locked in the same transaction** to `RUNNING`.
4. `RETURNING` hands back the claimed jobs and their lease tokens.
5. `COMMIT` publishes the `RUNNING` state; other workers querying `status = 'PENDING'` will no longer see those rows.

Between the CTE's `SELECT` and the `UPDATE`, there is no "unlocked gap" where another worker could slip in and claim the same row; the lock is held until commit.

### 15.2. Why COMMIT Before Processing the External Payload?

An error-prone design:

```text
BEGIN
SELECT job FOR UPDATE SKIP LOCKED
send email for 30 seconds
UPDATE job to DONE
COMMIT
```

For the entire 30 seconds, a connection and row lock are pinned. With many workers or slow jobs, long transactions hinder `VACUUM` and increase contention.

Usually a much better design:

```text
Short transaction:
    pick job + UPDATE status RUNNING + lease_token
    COMMIT

External processing outside transaction:
    call API / send email / generate report

Another short transaction:
    UPDATE status DONE if worker and token still valid
    COMMIT
```

This is a **claim + lease** pattern, not an exactly-once delivery guarantee. A worker can crash after performing the side effect but before writing `DONE`; idempotency is required.

### 15.3. Why Have attempt_count and lease_token?

- `attempt_count` increments on every claim to cap retries.
- `lease_token` increments on every claim to identify the **claim generation**. An old worker holding token 3 is prevented from marking `DONE` after a new worker claimed the job with token 4.

If jobs have high latency or complex retries, pass the token downstream for **fencing** or as an idempotency key; checking the token in the DB alone cannot undo an email or API call already sent by a stale worker.

## 16. Completing a Job with the Matching Token

Suppose `RETURNING` from the claim step returned:

```text
job_id = 1
claimed_by = worker-A
lease_token = 1
```

After successful processing:

```sql
UPDATE lock_wait_lab.jobs
SET
    status = 'DONE',
    completed_at = clock_timestamp(),
    claimed_by = NULL,
    claimed_at = NULL,
    lease_until = NULL
WHERE job_id = 1
  AND status = 'RUNNING'
  AND claimed_by = 'worker-A'
  AND lease_token = 1
RETURNING job_id, status, completed_at;
```

Expect **exactly one row** if the worker still owns a valid claim. If `RETURNING` yields **0 rows**, the worker must not assume success. Possible causes:

- The job was reclaimed by another worker.
- The lease/token changed.
- The job was already completed or moved to `FAILED`.
- The worker passed the wrong `job_id` or token.

The application must inspect state and apply appropriate retry/reconciliation handling.

### 16.1. Do Not Rely on Worker ID Alone

A worker ID may be reused after a restart, or the same worker may reclaim the same job a second time. In that case, `claimed_by = 'worker-A'` alone cannot distinguish the two attempts.

Checking `(job_id, claimed_by, lease_token)` prevents **stale completions**. For external side effects, combine with idempotent processing and downstream fencing.

### 16.2. Heartbeat Lease Extension

If a job takes longer than expected, the worker can periodically extend its lease while it still owns it:

```sql
UPDATE lock_wait_lab.jobs
SET lease_until = clock_timestamp() + INTERVAL '2 minutes'
WHERE job_id = 1
  AND status = 'RUNNING'
  AND claimed_by = 'worker-A'
  AND lease_token = 1
  AND lease_until > clock_timestamp()
RETURNING job_id, lease_until;
```

The unexpired check is an illustrative lease policy; real systems must define clock sources, heartbeat intervals, failover, and network-partition handling.

**Never extend a lease indefinitely** if the worker is no longer genuinely making progress.

## 17. When a Worker Crashes: Reclaiming Expired Leases

If worker A commits `RUNNING` and then crashes before writing `DONE`, its row lock was released long ago; `SKIP LOCKED` **will not reclaim the job** because it no longer satisfies `status = 'PENDING'`.

Thus, the system needs a **reaper/recovery job** that scans expired leases and transitions jobs back to a claimable or failed state.

```sql
BEGIN;

WITH expired AS (
    SELECT job_id
    FROM lock_wait_lab.jobs
    WHERE status = 'RUNNING'
      AND lease_until < clock_timestamp()
    ORDER BY lease_until, job_id
    LIMIT 50
    FOR UPDATE SKIP LOCKED
)
UPDATE lock_wait_lab.jobs AS j
SET
    status = CASE
        WHEN j.attempt_count >= j.max_attempts THEN 'FAILED'
        ELSE 'PENDING'
    END,
    ready_at = clock_timestamp() + INTERVAL '10 seconds',
    claimed_by = NULL,
    claimed_at = NULL,
    lease_until = NULL,
    last_error = 'Lease expired before completion'
FROM expired AS e
WHERE j.job_id = e.job_id
RETURNING
    j.job_id,
    j.status,
    j.attempt_count,
    j.max_attempts,
    j.lease_token;

COMMIT;
```

### 17.1. Why Does the Reaper Also Use SKIP LOCKED?

Multiple reapers or workers might update a job concurrently. `SKIP LOCKED` lets the reaper **avoid waiting on rows locked by other transactions**, handling other expired rows first.

If a worker just extended its lease in an uncommitted transaction, the reaper should not block waiting for that job; skipping it reduces contention. On the next sweep, timestamps and statuses are re-evaluated.

### 17.2. Tokens Prevent Stale DB Completion, Not Every External Side Effect

Example:

1. Worker A claims a job with token 3 and begins sending an email.
2. A loses connectivity; the lease expires.
3. The reaper moves the job back to `PENDING`.
4. Worker B claims the job with token 4.
5. A finishes sending the email and tries `UPDATE ... DONE` with token 3.

A's `UPDATE ... DONE` is rejected because the token mismatches. **However, the email A sent already exists outside the database.** If B also sends the email, the recipient receives two messages.

To prevent duplicate side effects, use **idempotency keys**, deduplication support from external providers, or fencing checks in downstream systems. `SKIP LOCKED` solves **row selection and locking in PostgreSQL**, not end-to-end exactly-once processing across external systems.

### 17.3. Lease Time Is Not Transaction Lock Time

Two distinct durations:

- **Row lock:** from when `SELECT FOR UPDATE` picks the job until the claim transaction commits or rolls back; should be very brief.
- **Lease:** the application-level deadline stored in `lease_until`, which can be much longer while the worker executes the job; it is not a PostgreSQL row lock.

Confusing these two durations is a common cause of long-running transactions and database stalls.

## 18. Controlled Retry on Failure

If a worker hits a transient failure, rather than waiting for the lease to expire, it can update immediately:

```sql
UPDATE lock_wait_lab.jobs
SET
    status = CASE
        WHEN attempt_count >= max_attempts THEN 'FAILED'
        ELSE 'PENDING'
    END,
    ready_at = clock_timestamp() + INTERVAL '30 seconds',
    claimed_by = NULL,
    claimed_at = NULL,
    lease_until = NULL,
    last_error = 'Temporary provider failure'
WHERE job_id = 1
  AND status = 'RUNNING'
  AND claimed_by = 'worker-A'
  AND lease_token = 1
RETURNING job_id, status, attempt_count, max_attempts;
```

If 0 rows return, the worker no longer owns the claim or the job changed state. Never overwrite another worker's newer state.

### 18.1. Retries with Backoff and Jitter

If many workers fail against an external service simultaneously, retrying all of them after an exact 30 seconds can cause a **thundering herd**. In real systems, consider exponential backoff, jitter, concurrency limits, and dead-letter/`FAILED` policies.

Conceptual formula example:

```text
retry_delay = min(base_delay * 2^(attempt-1), max_delay)
             + jitter
```

Do not use PostgreSQL's `^` as bitwise XOR when porting formulas from Java or other languages. This formula illustrates strategy; actual bounds must prevent integer overflow or excessively long delays.

### 18.2. Avoid Blindly Retrying Non-Idempotent Operations After Timeouts

A worker timing out when calling an external system **does not prove the external system did not execute the request**. Use idempotency keys or query external operation status before re-issuing a side-effecting call.

## 19. Fairness and Starvation: SKIP LOCKED Does Not Guarantee Strict FIFO

`ORDER BY priority DESC, ready_at, job_id` expresses preference **among lockable rows**, yet `SKIP LOCKED` is free to skip locked rows.

Example:

```text
Job #1: priority 100, locked for several minutes
Job #2: priority  90, free
Job #3: priority  80, free
```

A worker using `SKIP LOCKED` can process #2 and #3 before #1. Actual execution order is no longer strict FIFO/priority order.

This usually **helps throughput**, but is unsuitable if business rules require an earlier job to finish strictly before a later job.

### 19.1. Starvation

A repeatedly locked row, or low-priority jobs continually overtaken by incoming high-priority jobs, can be delayed indefinitely.

Mitigation techniques include:

- Keeping lock-holding transactions short.
- Monitoring oldest `PENDING` job age and `RUNNING` lease age.
- Priority aging by wait time, with clear fairness rules.
- Splitting queues into separate priority lanes or partitioned work queues.
- Dedicating worker capacity/quotas to lower-priority jobs.
- Bounding batch size so one worker does not hoard jobs.

Do not assume `SKIP LOCKED` guarantees **eventual fairness** for every row automatically.

### 19.2. ORDER BY and Locking Reads Under READ COMMITTED

In PostgreSQL under `READ COMMITTED`, a locking `SELECT` with `ORDER BY` may sort based on data visible initially and then re-read a column updated by another transaction after waiting for a lock, causing the final output to **deviate from strict newest-value order** in certain cases.

With `SKIP LOCKED`, the business effect is even more direct: locked high-priority rows are skipped, so claim order is **not a globally immutable ranking**.

If strict ordering is required, design **explicit serialization, partition ownership, or appropriate transaction isolation and retries** rather than expecting `ORDER BY` alone to guarantee it.

## 20. LIMIT, OFFSET, and Batch Selection Correctness

A queue worker commonly uses:

```sql
ORDER BY priority DESC, ready_at, job_id
LIMIT 10
FOR UPDATE SKIP LOCKED
```

This means **select up to 10 lockable rows** per the query rules—it neither guarantees always getting 10 rows nor that they are the globally first 10 rows under contention.

### 20.1. OFFSET in Locking Queries Is a Trap

Example:

```sql
SELECT job_id
FROM lock_wait_lab.jobs
WHERE status = 'PENDING'
ORDER BY job_id
OFFSET 10
LIMIT 5
FOR UPDATE SKIP LOCKED;
```

In PostgreSQL, rows scanned and skipped to satisfy `OFFSET` **can still be locked** even though they are omitted from the output. This increases contention and makes no sense for worker queues.

Therefore, **never use `OFFSET` to paginate work** in a job-claiming system. Each worker should take a batch from the front of eligible rows, claim, and commit; on the next pass, `RUNNING` rows no longer match `status = 'PENDING'`.

### 20.2. LIMIT Does Not Eliminate All Scanning Cost

PostgreSQL may still read, filter, or sort many rows to find N unlocked rows, especially under heavy contention or suboptimal indexes. `LIMIT 10` does not mean the query only ever touches 10 tuples.

### 20.3. Locking Rows Inside a Subquery and Applying LIMIT Outside

Placing the locking clause **inside a subquery** and `LIMIT` in an outer layer can change how many rows get locked. A subquery that locks broadly before an outer `LIMIT` is not equivalent to `ORDER BY ... LIMIT ... FOR UPDATE SKIP LOCKED` at the same level.

Keep the locking clause and `LIMIT` **together in the candidate-selection step** as shown in the claim pattern; check execution plans and locked-row behavior whenever writing nested queries.

## 21. Joining Multiple Tables: FOR UPDATE OF table_alias

A query may join multiple tables while needing to lock only rows in the job table.

For example, create a worker-group config table:

```sql
CREATE TABLE lock_wait_lab.job_types (
    job_type TEXT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT INTO lock_wait_lab.job_types (job_type, enabled)
VALUES
    ('email', TRUE),
    ('report', TRUE),
    ('cleanup', FALSE);
```

A worker wants to claim jobs whose type is enabled:

```sql
SELECT
    j.job_id,
    j.job_type,
    j.priority
FROM lock_wait_lab.jobs AS j
JOIN lock_wait_lab.job_types AS t
  ON t.job_type = j.job_type
WHERE j.status = 'PENDING'
  AND t.enabled = TRUE
ORDER BY j.priority DESC, j.job_id
LIMIT 5
FOR UPDATE OF j SKIP LOCKED;
```

`FOR UPDATE OF j` specifies **locking rows from table alias `j`**, without requesting row locks on `job_types` merely because it appears in the `JOIN`.

### 21.1. Do Not Lock Every Joined Table Unnecessarily

Omitting `OF j` in a `JOIN` applies the locking clause to **multiple tables in the `SELECT`**, creating unintended contention.

For instance, the configuration row `job_types('email')` is read by many workers: you must not exclusively lock it just to claim distinct email jobs. Using `OF j` accurately scopes the rows that need protection.

### 21.2. Check Which Table Gets Locked in OUTER JOINs

PostgreSQL disallows applying `FOR UPDATE` directly to the **nullable side of an outer join** because rows on that side may be NULL-extended. When locking is needed, specify the valid relation via `OF`, or select candidates from the main table first and join supplementary data afterward.

Do not use complex `LEFT JOIN`s in a way that obscures which table is actually being locked.

## 22. Do Not Arbitrarily Apply Locking Clauses After Aggregates

Locking clauses like `FOR UPDATE` are incompatible at the same query level with constructs that lose the 1-to-1 link to a source row, such as `GROUP BY`, aggregates, or `DISTINCT`, per PostgreSQL rules.

Wrong idea:

```sql
-- Not how to lock individual jobs:
-- SELECT status, COUNT(*)
-- FROM lock_wait_lab.jobs
-- GROUP BY status
-- FOR UPDATE SKIP LOCKED;
```

A grouped `COUNT(*)` row can represent thousands of source rows. PostgreSQL cannot treat that aggregated row as a row lock on a specific job.

### 22.1. Right Way: Lock in a Subquery/CTE, Aggregate Outside If Needed

If a task genuinely needs to lock a set of rows and then compute summary info over them, select **the concrete source rows** inside a CTE:

```sql
BEGIN;

WITH selected_jobs AS (
    SELECT
        job_id,
        job_type
    FROM lock_wait_lab.jobs
    WHERE status = 'PENDING'
    ORDER BY priority DESC, job_id
    LIMIT 5
    FOR UPDATE SKIP LOCKED
)
SELECT
    job_type,
    COUNT(*) AS selected_count
FROM selected_jobs
GROUP BY job_type;

ROLLBACK;
```

This counts **only the jobs selected and locked in this transaction**, not all `PENDING` jobs in the database. Do not use it for a dashboard showing total queued jobs.

## 23. READ COMMITTED, REPEATABLE READ, and SERIALIZABLE

Most SQL job queues like this are designed for **`READ COMMITTED`**, combining atomic claiming, status checks, and retries.

### 23.1. READ COMMITTED

In PostgreSQL, each statement in a `READ COMMITTED` transaction takes a fresh snapshot per its rules. A worker:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

-- Select and claim job with SKIP LOCKED.

COMMIT;
```

sees committed updates from other workers on the next statement. When a row is held by another transaction, `SKIP LOCKED` skips it.

### 23.2. REPEATABLE READ and SERIALIZABLE

At stricter isolation levels, if a row has changed since the transaction's snapshot and the transaction attempts to lock or modify it, PostgreSQL raises a serialization error instead of waiting and proceeding.

SQLSTATE **`40001`** (*serialization_failure*) signals the application to **retry the entire transaction** using an idempotent retry strategy.

Do not assume `SKIP LOCKED` prevents all serialization failures or deadlocks in multi-statement transactions.

### 23.3. Why Not Choose SERIALIZABLE Just to Make a "Safer Queue"?

`SERIALIZABLE` enforces isolation invariants, not a magic exactly-once job queue. Under high contention it increases transaction aborts and retries, and worker crashes after external side effects still require idempotency.

Choose the isolation level based on whole-transaction invariants, then validate the claim algorithm under realistic concurrency.

## 24. NOWAIT Does Not Replace Deadlock Detection

Deadlocks happen when transactions hold locks and wait on each other in a cycle.

Example:

```text
Transaction A holds account #1, wants to lock #2
Transaction B holds account #2, wants to lock #1
```

If both wait, PostgreSQL's deadlock detector detects the cycle and aborts one transaction, typically with SQLSTATE **`40P01`** (*deadlock_detected*).

### 24.1. Preventing Deadlocks with Consistent Lock Ordering

When locking multiple accounts, acquire locks **in a consistent primary-key order**:

```sql
BEGIN;

SELECT account_id
FROM lock_wait_lab.accounts
WHERE account_id IN (1, 2)
ORDER BY account_id
FOR UPDATE;

-- Only after acquiring needed locks, perform modifications.

COMMIT;
```

Consistent ordering reduces cycle risk when all transactions follow the same convention. Still, under concurrency with other row locks, triggers/FKs, or query plans, you must still handle deadlocks and serialization failures.

### 24.2. NOWAIT Fails Early, Not Deadlock-Proof Everywhere

If every row-lock acquisition uses `NOWAIT` properly, conflicts at those steps return errors instead of waiting. Yet a transaction can still acquire **other** locks outside locking clauses, and deadlocks can occur during `UPDATE`s, FKs, or DDL.

Therefore, still catch `40P01` and `40001` where appropriate, roll back, and retry with bounds.

## 25. Retrying Properly on 55P03

When `NOWAIT` or `lock_timeout` returns `55P03`, an application can:

1. Roll back the transaction (or roll back to an appropriate savepoint).
2. Choose to **retry** or return "resource busy" depending on the use case.
3. If retrying, use exponential backoff, jitter, and a max retry cap.
4. Attach idempotency keys for operations with side effects.
5. Emit contention metrics, without unconditionally logging sensitive payloads.

### 25.1. Java/JDBC Pseudo-Code

```java
int maxAttempts = 3;
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
        connection.setAutoCommit(false);

        try (PreparedStatement lockStmt =
                 connection.prepareStatement("""
                     SELECT account_id
                     FROM lock_wait_lab.accounts
                     WHERE account_id = ?
                     FOR UPDATE NOWAIT
                     """)) {
            lockStmt.setInt(1, 1);
            try (ResultSet rs = lockStmt.executeQuery()) {
                if (!rs.next()) {
                    throw new IllegalStateException("Account not found");
                }
            }
        }

        try (PreparedStatement updateStmt =
                 connection.prepareStatement("""
                     UPDATE lock_wait_lab.accounts
                     SET balance = balance + ?
                     WHERE account_id = ?
                     """)) {
            updateStmt.setBigDecimal(
                1, new java.math.BigDecimal("10.00")
            );
            updateStmt.setInt(2, 1);
            if (updateStmt.executeUpdate() != 1) {
                throw new IllegalStateException("Unexpected row count");
            }
        }

        connection.commit();
        break;
    } catch (java.sql.SQLException ex) {
        connection.rollback();
        if (!"55P03".equals(ex.getSQLState())
                || attempt == maxAttempts) {
            throw ex;
        }
        // Production code: backoff + jitter before next attempt.
    } catch (RuntimeException ex) {
        connection.rollback();
        throw ex;
    } finally {
        connection.setAutoCommit(true);
    }
}
```

This snippet assumes an existing `java.sql.Connection`, JDBC imports, and application-managed connections. It illustrates `55P03` classification, **not a complete production retry framework**:

- Never re-send an operation with external side effects without idempotency.
- Restoring connection state must match the connection pool or transaction manager in use.
- If using Spring/JTA transaction management, do not call `setAutoCommit`/`commit` directly against framework rules.
- Retry rules for `40P01`/`40001` may differ and generally require retrying the entire transaction.

### 25.2. Should You Return HTTP 409 or 423?

That belongs to your application's **API contract**, not a mandatory PostgreSQL rule. You may return `409 Conflict`, `423 Locked`, or a domain-specific status code depending on design, with `Retry-After` where appropriate. Never leak table names, raw SQL, or internal lock details to clients unnecessarily.

## 26. Monitoring Lock Waits

When a worker queue slows down or an API emits many `55P03` errors, do not just raise timeouts. Inspect **who holds the locks and which transactions are waiting**.

### 26.1. pg_stat_activity and pg_blocking_pids

```sql
SELECT
    a.pid,
    a.datname,
    a.usename,
    a.state,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blocked_by,
    a.query
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
  AND a.wait_event_type = 'Lock'
ORDER BY a.pid;
```

`pg_blocking_pids(pid)` returns the PIDs blocking a backend according to PostgreSQL, which is far better than guessing blockers solely from session SQL. System monitoring permissions may restrict visible fields.

### 26.2. pg_locks

```sql
SELECT
    pid,
    locktype,
    relation::regclass AS relation_name,
    mode,
    granted,
    waitstart
FROM pg_locks
WHERE database = (
    SELECT oid
    FROM pg_database
    WHERE datname = current_database()
)
ORDER BY granted, relation::text, pid;
```

`pg_locks` records many lock types, yet **row-level lock state does not always appear as an obvious tuple lock row**. When a transaction waits on a locked row, the wait is often shown via `transactionid`, so do not rely solely on rows with `locktype = 'tuple'`.

### 26.3. Metrics Worth Tracking

| Metric | Question |
| --- | --- |
| `55P03` count per endpoint/job | How often do `NOWAIT` or `lock_timeout` fail? |
| Lock wait duration | How long does each request wait? |
| `PENDING`/`RUNNING` row counts | Is the queue backing up? |
| Oldest `PENDING` job age | Is starvation happening? |
| Expired leases and reclaimed jobs | Are workers crashing or stalling? |
| Retry / `FAILED` counts | Is a downstream service failing persistently? |
| `idle in transaction` connection count | Are locks held while clients sit idle? |
| Deadlocks / serialization failures | Should lock ordering or transaction design be revised? |

These signals separate **normal contention errors** from **designs holding transactions open too long**.

## 27. Performance of SKIP LOCKED: Not Just Indexes

A queue with hundreds of workers can face bottlenecks:

- Many workers hitting the high-priority head of the same index simultaneously.
- Selected rows living on the same heap page or undergoing rapid updates.
- Large CTE claim batches locking too many rows at once.
- Frequent `RUNNING`/`PENDING` transitions generating dead tuples and index churn.
- Many leases expiring at once causing reaper spikes.
- `ORDER BY` and `WHERE` predicates not matching the index well.
- Claim transactions held open while workers perform external I/O.

### 27.1. EXPLAIN on Locking Queries

```sql
EXPLAIN
SELECT job_id, priority
FROM lock_wait_lab.jobs
WHERE status = 'PENDING'
  AND ready_at <= now()
ORDER BY priority DESC, ready_at, job_id
LIMIT 10
FOR UPDATE SKIP LOCKED;
```

The plan may show `LockRows`, `Limit`, `Sort`, `Index Scan`, or `Seq Scan` depending on data and statistics. On a tiny demo table of a few rows, `Seq Scan` is often optimal for the planner.

**Measuring caveat:**

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT job_id
FROM lock_wait_lab.jobs
WHERE status = 'PENDING'
ORDER BY priority DESC, job_id
LIMIT 10
FOR UPDATE SKIP LOCKED;
```

`EXPLAIN ANALYZE` **actually executes the `SELECT` and acquires the locks**, rather than just estimating a plan. Use it to learn in a lab, never casually on production if the query will take row locks, create contention, or disrupt traffic.

### 27.2. B-Trees Do Not Index Row Lock State

Indexes help locate candidate rows matching predicates, but **row lock ownership is concurrent runtime state**—not a column stored in a B-tree index.

Even with an ideal index, workers may still skip many locked rows. Capacity planning must account for lock-contention rates, batch sizes, transaction duration, and worker concurrency.

### 27.3. Batch Size

- Too small: excessive round trips and transaction overhead.
- Too large: one worker hoards many jobs, hurting fairness and delaying other workers.
- Claiming 1–20 jobs may fit certain workloads, though **no single number fits every system**.

Pick batch sizes through benchmarks and SLAs, and never hold row locks across job processing time.

## 28. Advisory Locks and NOWAIT/SKIP LOCKED

PostgreSQL also offers **advisory locks**, where the application assigns lock meaning to an integer or pair of integers:

```sql
SELECT pg_try_advisory_xact_lock(12345);
```

This returns a boolean:

- `TRUE` if the requested advisory lock was acquired.
- `FALSE` if a conflict prevented immediate acquisition.

This is a "try-lock" at the advisory-lock level, **not `FOR UPDATE ... NOWAIT` syntax**, and it does not automatically lock a table row by primary key.

### 28.1. When Are Advisory Locks Appropriate?

For example, ensuring only one worker runs a **logical maintenance task keyed by an application ID** when there is no concrete table row to `UPDATE`.

However, advisory locks require participating code paths to **voluntarily follow the same convention**; they do not replace constraints or row locks to protect data from other SQL statements.

### 28.2. Do Not Mix Lock Types Without a Design

A system combining advisory locks, `FOR UPDATE NOWAIT`, and multi-table FK updates can create complex lock-acquisition orders. If transactions acquire locks in differing orders, deadlocks can still happen.

Choose the simplest mechanism that enforces the invariant, and document lock ordering and retry behavior clearly.

## 29. NOWAIT/SKIP LOCKED in Financial and Inventory Workflows

### 29.1. Account Balances

If the goal is to **withdraw 80 from specifically account #1**, this query:

```sql
SELECT account_id
FROM lock_wait_lab.accounts
WHERE account_id = 1
FOR UPDATE SKIP LOCKED;
```

will return **0 rows** whenever account #1 is locked by another transaction. That **does not mean the account does not exist** or lacks funds.

If the application returns "account not found" on 0 rows, that is a business bug. Use `NOWAIT` to detect busy state, or wait with a bounded timeout when that exact account is required.

### 29.2. Inventory

A query like:

```sql
SELECT product_id, stock
FROM inventory
WHERE product_id = 100
FOR UPDATE SKIP LOCKED;
```

does not mean "out of stock" when empty. The product row may simply **be locked**. Skipping a locked inventory row and allowing orders without proper inventory checks causes overselling or data corruption.

For inventory reservations, use an atomic `UPDATE ... WHERE stock >= quantity RETURNING ...`, or lock the exact row and check with `NOWAIT`/timeout per defined rules.

### 29.3. A Conditional UPDATE Can Be Simpler

Inventory deduction example on a hypothetical schema:

```sql
UPDATE inventory
SET stock = stock - 2
WHERE product_id = 100
  AND stock >= 2
RETURNING product_id, stock;
```

When operating cleanly on a single table within a transaction, such a conditional update can eliminate a preceding `SELECT FOR UPDATE`. Check the **affected row count**; do not treat 0 rows as proof the product doesn't exist, since stock may simply be insufficient.

**`SKIP LOCKED` fits "pick any interchangeable task," not "skip a mandatory entity that must be processed."**

## 30. Common Mistakes

| Mistake | Why it is wrong | Proper approach |
| --- | --- | --- |
| Thinking `NOWAIT` means "never blocks" | Only affects row-lock waits in the locking clause | Account for table locks; use `LOCK TABLE ... NOWAIT` or `lock_timeout` if needed |
| Thinking `SKIP LOCKED` takes no locks | Selected rows are still locked | Keep transactions short |
| Using `SKIP LOCKED` for total count reports | Omits currently locked rows | Use a plain snapshot `SELECT` |
| Using `SKIP LOCKED` to check "account does not exist" | Locked rows are also omitted | Use `NOWAIT`/waiting; distinguish busy vs. missing |
| Only `SELECT`ing a job then `COMMIT`ting | After commit the job stays `PENDING` and another worker grabs it | Select and `UPDATE` to `RUNNING` in the same transaction |
| Holding transaction open while sending email | Long locks stall `VACUUM` and concurrency | Claim+commit, process externally, finalize in a new transaction |
| Thinking `SKIP LOCKED` guarantees exactly-once | Worker crash after side effect still causes retries | Add idempotency and lease/fencing |
| Using `OFFSET` to paginate queues | Rows skipped by `OFFSET` can still be locked | Claim batches without `OFFSET` |
| Believing `ORDER BY` guarantees strict FIFO | Locked high-priority rows get skipped | Design explicit ordering/ownership rules |
| Assuming `LIMIT 10` touches only 10 tuples | May scan past locked tuples | Benchmark under real workload |
| Using `FOR UPDATE` across all joined tables | Locks shared config tables unnecessarily | `FOR UPDATE OF j` |
| Locking clause after `GROUP BY` | No single source row left to lock | Lock row IDs in a CTE first |
| Catching `55P03` and continuing the failed transaction | PostgreSQL rejects SQL after an error | `ROLLBACK` or roll back to savepoint |
| Immediate infinite retries | Retry storms increase contention | Backoff, jitter, and retry cap |
| Treating `55P03`, `40P01`, `40001` identically | Require different recovery scopes | Classify SQLSTATE and retry at the right boundary |
| Raising `lock_timeout` indefinitely | Masks transactions holding locks too long | Monitor blockers and fix workflows |
| Using `lock_timeout` as a full statement cap | Caps each lock wait, not total execution | Add `statement_timeout` as needed |
| Thinking `idle_in_transaction_session_timeout` fixes all lock waits | Targets only idle-in-transaction sessions | Understand session states and timeout types |
| Treating `lease_until` as a PostgreSQL row lock | Lease is just a data column | Validate token and state on completion |
| Using worker ID alone to verify ownership | Worker IDs can be reused | Use monotonic claim/lease tokens |
| Assuming DB token stops duplicate emails | External side effects cannot be rolled back | Downstream fencing/idempotency |
| Running `EXPLAIN ANALYZE` carelessly on production locking queries | Executes the query and takes real locks | Measure in lab/staging or controlled maintenance |
| Using advisory locks to replace PK/FK | Only enforced voluntarily by cooperating code | Use constraints and row locks where appropriate |

## 31. Process for Choosing a Lock-Waiting Strategy

When designing a contended query, answer in order:

1. **Do you need this exact row, or will any eligible row do?** If exact, never use `SKIP LOCKED` to pretend a locked row doesn't exist.
2. **Is waiting acceptable?** If yes, what is the maximum tolerable wait?
3. **What should the application do if the lock is unavailable?** Retry, return busy, pick another job, or enqueue?
4. **Which lock types could cause waiting?** Row locks, table locks, advisory locks, FKs/DDL?
5. **Which locking clause fits?** `FOR UPDATE`, `FOR NO KEY UPDATE`, `FOR SHARE`, or `FOR KEY SHARE`?
6. **Is `OF alias` needed in a `JOIN`?** Avoid locking unrelated tables.
7. **Which isolation level is used?** `READ COMMITTED`, `REPEATABLE READ`, or `SERIALIZABLE`?
8. **Are affected row counts checked?** Zero rows can mean "not found," "condition failed," or "skipped."
9. **How long will the transaction hold locks?** Is there external I/O inside the transaction?
10. **Are `lock_timeout`/`statement_timeout` set?** Does code roll back cleanly on error?
11. **What if a worker crashes?** Are leases, a reaper, and claim tokens in place?
12. **Are external side effects idempotent?** Is duplicate execution safe?
13. **Is strict ordering or fairness required?** `SKIP LOCKED` can allow starvation.
14. **Are indexes appropriate?** Are execution plans and dead-tuple rates healthy?
15. **Are metrics/alerts in place to observe contention?** Do you know who holds locks and who is waiting?

### 31.1. Quick Decision Table

| Goal | Typical right choice |
| --- | --- |
| Modify a specific row; waiting is fine | Atomic `UPDATE` or default `SELECT FOR UPDATE` |
| Need a specific row; fail fast if busy | `SELECT FOR UPDATE NOWAIT` |
| Allow brief wait, but not forever | `SET LOCAL lock_timeout` + locking `SELECT`/`UPDATE` |
| Multiple workers picking any eligible job | `SELECT FOR UPDATE SKIP LOCKED` + `UPDATE` in one transaction |
| Read consistent snapshot for reporting | Plain `SELECT`, no `SKIP LOCKED` |
| Try table lock without waiting | `LOCK TABLE ... IN ... MODE NOWAIT` |
| Hold a reservation for minutes | Committed state/lease column, not long-held row locks |
| Serialize a logical task by app key | Consider `pg_try_advisory_xact_lock` with clear conventions |

## 32. Practice Exercises

Use the `lock_wait_lab` schema. Two-session exercises require connecting to the same database and **ending every test transaction with `COMMIT`/`ROLLBACK`**; never walk away leaving locks open.

1. **Basic locks:** create three accounts and explain which main lock types `SELECT ... FOR UPDATE` acquires.
2. **Default wait:** Session A locks account 1; B uses `FOR UPDATE`. Why does B wait? What lets B resume?
3. **NOWAIT:** change B's query to `FOR UPDATE NOWAIT`. Record the SQLSTATE returned and transaction state.
4. **Cleanup after error:** after B hits `55P03`, try running another `SELECT` before `ROLLBACK`; observe why rollback is required.
5. **Savepoint:** create a `SAVEPOINT` before `NOWAIT`, roll back to the savepoint on error, then continue with another `SELECT`.
6. **SKIP LOCKED:** A locks account 1; B runs `FOR UPDATE SKIP LOCKED` across all three accounts. Predict the returned accounts.
7. **Plain SELECT:** A holds `FOR UPDATE`; B runs a `SELECT` with no locking clause. Why can B still read?
8. **Lock modes:** compare the compatibility of `FOR SHARE` and `FOR KEY SHARE` with `FOR NO KEY UPDATE`.
9. **Bounded wait:** B sets `SET LOCAL lock_timeout='1s'` and waits on account 1; compare with `NOWAIT`.
10. **statement_timeout:** set both `lock_timeout` and `statement_timeout`, and explain what each controls.
11. **Table locks:** A holds `ACCESS EXCLUSIVE` on `accounts`; B runs `FOR UPDATE NOWAIT`. Why does B still wait?
12. **LOCK TABLE NOWAIT:** try acquiring a `ROW SHARE` table lock with `NOWAIT` in B while A holds `ACCESS EXCLUSIVE`.
13. **DDL and locks:** describe why a long-running transaction holding row locks can stall maintenance/`ALTER TABLE`.
14. **Queue:** create `jobs` and insert six jobs with varying priorities. Write a query listing `PENDING` jobs by priority.
15. **Two workers:** A takes the highest-priority job with `FOR UPDATE SKIP LOCKED` and keeps the transaction open; B claims one job with the same criteria. How do the two jobs differ?
16. **Atomic claim:** write a CTE selecting two `PENDING` jobs with `FOR UPDATE SKIP LOCKED` and `UPDATE`ing them to `RUNNING` with `RETURNING`.
17. **Claim contention:** run the claim query concurrently from two workers. Explain why neither writes `RUNNING` to the same row simultaneously.
18. **Not just SELECT:** explain why merely `SELECT`ing a job and `COMMIT`ting without updating to `RUNNING` lets the job be picked again.
19. **Leases:** after claiming, why commit immediately before processing the payload? How does `lease_until` differ from a row lock?
20. **Tokens:** complete a job with `WHERE` checking `job_id`, `claimed_by`, and `lease_token`; what happens if the token is stale?
21. **Heartbeat:** write an `UPDATE` extending the lease only when owner/token match and the lease is still valid.
22. **Worker crash:** a `RUNNING` job's lease expires; write a reaper picking up to 50 jobs and moving them to `PENDING` or `FAILED`.
23. **Retry:** on transient failure, use `attempt_count`/`max_attempts` to decide `PENDING` vs. `FAILED` with backoff.
24. **Exactly-once:** describe a case where an email is sent but the DB does not record `DONE`. Why does `SKIP LOCKED` not prevent duplicate emails?
25. **Starvation:** create a low-priority job and continuously insert high-priority jobs. List ways to mitigate starvation.
26. **Ordering:** A locks the highest-priority job; B runs `ORDER BY priority DESC SKIP LOCKED`. Why is strict FIFO not guaranteed?
27. **OFFSET:** test `OFFSET 2 LIMIT 2 FOR UPDATE SKIP LOCKED` and explain why rows skipped by `OFFSET` can still get locked.
28. **JOIN OF:** join `jobs` with `job_types` and use `FOR UPDATE OF j SKIP LOCKED`. Why avoid locking `job_types` rows?
29. **GROUP BY:** why is `SELECT COUNT(*) GROUP BY status FOR UPDATE` invalid? Fix it with a CTE locking row IDs.
30. **SQLSTATE:** distinguish `55P03`, `40P01`, `40001`, and `57014`; which errors require retrying the entire transaction?
31. **pg_stat_activity:** create a lock wait in the lab and use `pg_blocking_pids` to identify the blocker.
32. **pg_locks:** why does not seeing an explicit `tuple` lock fail to prove there is no row-lock contention?
33. **EXPLAIN:** inspect the plan for selecting jobs with `LIMIT 10 FOR UPDATE SKIP LOCKED`. Which `LockRows`/`Sort`/`Scan` nodes appear?
34. **Indexes:** create a partial index for `status = 'PENDING'` and observe its effect on sufficient data; why does an index not eliminate contention?
35. **READ COMMITTED:** once one worker commits `RUNNING` status, what does another worker see in its next claim query?
36. **SERIALIZABLE:** if receiving SQLSTATE `40001`, why should you retry the entire transaction instead of just one `UPDATE`?
37. **Busy API:** design the response when `NOWAIT` reports busy on a requested account; do not confuse busy with not found.
38. **Inventory:** why is using `SKIP LOCKED` to check for out-of-stock wrong? Propose a conditional `UPDATE` or proper transaction locking.
39. **Advisory locks:** compare `pg_try_advisory_xact_lock` with `SELECT ... FOR UPDATE NOWAIT` in scope and enforcement.
40. **Production design:** a queue has 100 workers, jobs take 30 seconds and occasionally time out. Propose batch size, lease, heartbeat, retry/idempotency, metrics, and recovery procedures.

## 33. Summary

In PostgreSQL, choosing how to wait on locks must be driven by **what the result means under contention**, not merely single-query speed.

```text
A needed row is currently locked by another transaction
    |
    +--> FOR UPDATE (default)
    |       Wait for the lock to be released
    |
    +--> FOR UPDATE NOWAIT
    |       Do not wait on the row lock
    |       Return error 55P03 if unavailable immediately
    |
    +--> FOR UPDATE SKIP LOCKED
    |       Skip locked rows
    |       Pick other rows or return 0 rows
    |
    +--> Wait with lock_timeout
            Wait up to the limit per lock wait
            Applies beyond row locks alone
```

Principles to remember:

- **`NOWAIT` and `SKIP LOCKED` govern row-level locks in the locking clause**; they do not make table-level locks or every execution step non-blocking.
- **`NOWAIT` fits workflows needing a specific row and fast busy reporting**. Handle SQLSTATE `55P03` and roll back/use savepoints properly.
- **`SKIP LOCKED` fits interchangeable work items**. It is **unsuitable for reports needing complete data sets** and does not prove skipped rows do not exist.
- **A proper queue worker selects and marks the job as claimed in the same transaction**; `WITH candidates AS (... FOR UPDATE SKIP LOCKED) UPDATE ... RETURNING` is an effective PostgreSQL pattern.
- **After claiming, commit quickly; process externally using leases and tokens**. Never hold row locks across API calls or user input.
- **`SKIP LOCKED` does not guarantee FIFO, fairness, or exactly-once side effects**. Retries, reapers, backoff, fencing, and idempotency must be built explicitly.
- **`lock_timeout`, `statement_timeout`, and deadlock detection serve distinct roles**; never rely on one parameter to replace all time controls.
- **Monitor who is waiting on whom via `pg_stat_activity`, `pg_blocking_pids`, and `pg_locks`**, then tune transaction duration, indexes, and concurrency from real evidence.

Quick selection rule: **need the exact row → wait or `NOWAIT`; fine doing other work → `SKIP LOCKED`; need bounded waits → `lock_timeout`; need slow work → persist state/lease and commit short locks.** Keeping those cases distinct lets PostgreSQL maintain both data consistency and high throughput under concurrent load.
