# lock_timeout, statement_timeout, and Their Different Effects in PostgreSQL

In PostgreSQL, an SQL statement can be slow for many reasons: reading too many rows, planning or sorting large data sets, running CPU-heavy functions, waiting on I/O, or **waiting for another transaction to release a lock**. From the application side, they look alike: the request has not returned yet. Yet the fix for a slow analytical query is completely different from the fix for an `UPDATE` blocked by a row lock.

Two parameters commonly used to control these situations are:

- **`lock_timeout`**: limits how long a statement may **wait to acquire a lock**.
- **`statement_timeout`**: limits total execution time for **the entire statement** in PostgreSQL, including any time spent waiting for locks.

For example, a query taking four seconds for computation without waiting on locks will not be canceled by `lock_timeout = '500ms'` just for running long; it would be canceled by `statement_timeout = '2s'`. Conversely, an `UPDATE` waiting on a row held by another transaction will be canceled by `lock_timeout = '500ms'` even while `statement_timeout = '10s'` has not expired.

This lesson belongs to the **Locks** chapter of the *Database Engine Relational PostgreSQL* module. The goal is not merely memorizing `SET` syntax, but understanding **which timer is running, which error is raised, the transaction state afterward, how to find the blocker, and how to align database timeouts with applications and migrations**.

## 1. Distinguishing Execution Time, Lock Wait, and Transaction Time

Suppose the following statement is sent to PostgreSQL:

~~~sql
UPDATE inventory
SET stock = stock - 1
WHERE sku = 'BOOK-001'
  AND stock > 0;
~~~

The `inventory` table here is a structural example; the lab section creates tables in a dedicated schema.

A conceptual execution timeline:

~~~text
Statement start                                       End
|--------------------------------------------------------|
| Parse/plan | Lock wait | Read, check, UPDATE, write WAL |
|    20ms    |  2400ms   |             1580ms             |
             |<--------->|
               lock wait
|<--------------------- 4000ms ------------------------->|
                   statement duration
~~~

If it waits 2400ms on a single lock and:

- `lock_timeout='500ms'`, the statement is canceled after ~500ms of waiting for the lock.
- `statement_timeout='2s'`, the statement is canceled once the statement time budget expires, whether or not a lock wait occurred.
- A 5s HTTP timeout measured from when the request hits the gateway has a different scope: it includes routing, pool wait, and network overhead before PostgreSQL even receives the SQL.

### 1.1. A Statement Is Not a Transaction

~~~sql
BEGIN;
SELECT ...;
UPDATE ...;
SELECT ...;
COMMIT;
~~~

A transaction can contain multiple statements. If each takes 1.5 seconds and `statement_timeout` is 2 seconds, the total transaction duration can exceed 2 seconds without any individual statement hitting the limit.

### 1.2. Lock Wait vs. Lock Hold

- **Lock wait**: a transaction requests a lock and has not yet been granted it due to conflict.
- **Lock hold**: a transaction has acquired the lock and holds it until released under PostgreSQL semantics.

`lock_timeout` targets **wait**, not **hold**. This is the single most important distinction in this lesson.

## 2. What Is lock_timeout?

`lock_timeout` is the PostgreSQL parameter that limits how long a statement waits while attempting to acquire a contended lock.

~~~sql
SET lock_timeout = '750ms';
~~~

If the lock is not granted within the allowed time, PostgreSQL cancels the statement with a message like:

~~~text
ERROR: canceling statement due to lock timeout
~~~

The typical SQLSTATE is **`55P03`** (`lock_not_available`).

### 2.1. Where Does It Apply?

Not only with explicit `LOCK TABLE`. PostgreSQL acquires locks in many operations:

- Updating or deleting the same row in different transactions.
- `SELECT ... FOR UPDATE` on a locked row.
- `INSERT/UPDATE/DELETE` needing appropriate table-level locks.
- `ALTER TABLE` or DDL needing strong locks.
- Plain `SELECT` needing a relation lock and blocked by a held `ACCESS EXCLUSIVE`.
- Operations acquiring locks via PostgreSQL's Lock Manager.

Not every operation on the same table conflicts. PostgreSQL uses MVCC and distinct lock modes to let compatible reads and writes run concurrently.

### 2.2. Does Not Limit Statement Runtime

~~~sql
SET lock_timeout = '100ms';

SELECT pg_sleep(2);
~~~

Without lock contention, `pg_sleep(2)` completes normally because that delay is not spent waiting to acquire a lock.

### 2.3. Does Not Limit Lock Hold Time

If T1 runs:

~~~sql
BEGIN;
UPDATE inventory SET stock = stock + 1 WHERE sku = 'BOOK-001';
-- Application forgets to COMMIT.
~~~

then `lock_timeout='500ms'` **set on T1 itself** does not force T1 to end after holding the lock for 500ms. Other sessions waiting on it may time out, while the blocker keeps holding the lock until `COMMIT`, `ROLLBACK`, or termination via another mechanism.

### 2.4. Measured Per Lock Acquisition Attempt

One statement may acquire multiple locks sequentially. The timeout applies to **each lock wait attempt**, rather than summing all lock waits into a single cumulative budget.

Example:

~~~text
wait lock A = 400ms
wait lock B = 400ms
wait lock C = 400ms

lock_timeout = 500ms
~~~

Each individual wait is under 500ms. You cannot assume `lock_timeout` will fire simply because total wait is 1200ms. Meanwhile, `statement_timeout='1s'` would cancel it because total statement time exceeded its budget.

## 3. What Is statement_timeout?

`statement_timeout` limits **total SQL statement execution time** on the server.

~~~sql
SET statement_timeout = '3s';
~~~

When exceeded, the typical message is:

~~~text
ERROR: canceling statement due to statement timeout
~~~

The typical SQLSTATE is **`57014`** (`query_canceled`).

### 3.1. Includes Lock Wait Time

If an `UPDATE` waits on a row lock for 5 seconds while `statement_timeout` is 2 seconds, it is canceled by `statement_timeout` even when `lock_timeout=0`.

### 3.2. Includes Other Activities

`statement_timeout` can cancel an SQL statement running long due to:

- Large scans or joins.
- Large sorts, aggregations, or bulk data operations.
- Function or extension execution.
- Waiting on I/O.
- Waiting on locks.
- A `pg_sleep()` call.
- DDL or utility statements running under its scope.

### 3.3. Not a Total Transaction Timeout

~~~sql
BEGIN;
SELECT pg_sleep(0.4);
SELECT pg_sleep(0.4);
SELECT pg_sleep(0.4);
COMMIT;
~~~

With `statement_timeout` at 500ms, each `SELECT` succeeds even though total transaction time exceeds 500ms.

### 3.4. Not Measured From User Button Click

PostgreSQL measures statements at the server protocol level. In the simple-query protocol, modern versions apply the timeout per individual statement within a multi-statement query string; exact historical behavior varied across versions. In the extended-query protocol, `Parse`, `Bind`, `Execute`, `Describe` messages and completion boundaries govern timing.

Practical point: `statement_timeout` **does not include** gateway queuing, connection pool checkout wait, or application processing before SQL reaches PostgreSQL.

## 4. Direct Comparison

| Aspect | `lock_timeout` | `statement_timeout` |
|---|---|---|
| Scope | Waiting to acquire a lock | Entire statement |
| Requires lock contention? | Yes, for the lock-wait timer to matter | No |
| Row/table lock waits | Yes | Yes |
| CPU/I/O query work | Not targeted | Yes |
| Multiple lock waits | Caps each wait | Caps total statement |
| Hold time after lock granted | Does not limit | Does not directly limit entire transaction |
| Total transaction time | No | No |
| Typical error | `55P03` | `57014` |
| Use in DDL | Fail fast on lock wait | Bounds total runtime as well |
| Value `0` | Disables this timeout | Disables this timeout |
| Unitless integer | Milliseconds | Milliseconds |

Easy rule of thumb: **`lock_timeout` says "don't wait too long for a lock"; `statement_timeout` says "don't let one SQL statement run too long."**

## 5. Both Timeouts Active: Which Fires First?

Suppose an SQL statement waits on a lock that is not released.

### 5.1. lock_timeout Is Smaller

~~~sql
SET lock_timeout = '400ms';
SET statement_timeout = '5s';
~~~

If the lock is held longer than 400ms, `55P03` fires first. This separates a short **lock-wait budget** from a longer **total execution budget**.

### 5.2. statement_timeout Is Smaller

~~~sql
SET lock_timeout = '5s';
SET statement_timeout = '400ms';
~~~

`statement_timeout` cancels the SQL after ~400ms right while it is waiting for the lock. The application then receives `57014` without waiting for `55P03`.

### 5.3. lock_timeout Equal to or Larger Than statement_timeout

Usually this setup **makes little sense** because `statement_timeout` already covers lock wait time and fires earlier or at the same time. If your goal is to distinguish lock contention, keep the two thresholds clearly separated.

### 5.4. Do Not Rely on Error Ordering When Thresholds Are Close

Scheduling jitter, lock release timing, and cancel signals can race closely. Never build business logic assuming two nearly equal timeouts always yield one specific SQLSTATE.

### 5.5. Multi-Lock Example

~~~text
lock_timeout = 700ms
statement_timeout = 1600ms

wait A 600ms
CPU    250ms
wait B 600ms
CPU    250ms

Total = 1700ms
~~~

Each individual lock wait is under 700ms, yet total statement duration exceeds 1600ms. Here `statement_timeout` fires without `lock_timeout` firing.

## 6. Values, Units, and Inspecting Configuration

~~~sql
SHOW lock_timeout;
SHOW statement_timeout;

SELECT name, setting, unit, source
FROM pg_settings
WHERE name IN ('lock_timeout', 'statement_timeout')
ORDER BY name;
~~~

### 6.1. Units

~~~sql
SET lock_timeout = '250ms';
SET statement_timeout = '3s';
~~~

You can use PostgreSQL-supported time units such as `ms`, `s`, or `min`.

### 6.2. Plain Integers Default to Milliseconds

~~~sql
SET lock_timeout = 500;
SET statement_timeout = 4000;
~~~

Equivalent to 500ms and 4000ms. **`SET statement_timeout = 5` is 5ms, not 5 seconds.**

### 6.3. Value 0

~~~sql
SET lock_timeout = 0;
SET statement_timeout = 0;
~~~

Disables the respective limit; it does not mean statements can never be canceled by client disconnect, administrators, transaction errors, system safeguards, or other timers.

### 6.4. Effective Settings Can Differ from Config Files

A session's setting may come from `ALTER ROLE`, `ALTER DATABASE`, connection startup parameters, or runtime `SET`. When investigating a specific request, run `SHOW` on the relevant connection and check `pg_settings.source`.

## 7. SET, SET LOCAL, RESET

### 7.1. Session-Scoped SET

~~~sql
SET lock_timeout = '500ms';
SET statement_timeout = '3s';
~~~

Values persist for the session until changed/reset or the session ends, following PostgreSQL transaction semantics.

### 7.2. Transaction-Scoped SET LOCAL

~~~sql
BEGIN;
SET LOCAL lock_timeout = '500ms';
SET LOCAL statement_timeout = '3s';

SELECT COUNT(*) FROM pg_class;

COMMIT;
~~~

`SET LOCAL` is ideal when only one workflow needs custom budgets. Once the transaction ends, local settings revert to the session's active defaults.

### 7.3. Never Use SET LOCAL Outside a Transaction Expecting It to Stick

`SET LOCAL` only applies inside a transaction block. Under autocommit, do not run it as a standalone statement expecting a following `SELECT` to inherit it.

### 7.4. RESET to Effective Default

~~~sql
RESET lock_timeout;
RESET statement_timeout;
~~~

`RESET` does not automatically mean `0` if a role or database default was configured otherwise.

### 7.5. SET Inside a Transaction and Rollback

If you change a value using `SET` inside a transaction and the transaction rolls back, the configuration change rolls back too per PostgreSQL semantics. For a business transaction, `SET LOCAL` expresses the intended scope much more clearly.

## 8. Role- and Database-Level Configuration

The following are structural examples; run only with matching roles/databases and privileges:

~~~sql
ALTER ROLE app_writer
SET lock_timeout = '500ms';

ALTER ROLE app_writer
SET statement_timeout = '8s';

ALTER DATABASE app_db
SET statement_timeout = '10s';

ALTER ROLE app_writer IN DATABASE app_db
SET lock_timeout = '700ms';
~~~

### 8.1. Impact on Connections

Role/database defaults apply when new sessions start. Already-open pooled connections do not pick up new defaults until reconnected or updated directly.

### 8.2. Scope Matters

A fast OLTP endpoint differs from hourly reporting or schema migrations. Do not force every workload under an overly tight `statement_timeout` without justification.

### 8.3. Risk of Session Leaks in Pools

If one request runs:

~~~sql
SET statement_timeout = '200ms';
~~~

and returns the connection to the pool without resetting, subsequent requests hit unexpected timeouts. Use `SET LOCAL` inside transactions or standardized transaction manager / pool initialization hooks.

### 8.4. Privileges to Adjust

Server/role/database settings require appropriate privileges. Never widen production privileges just so an endpoint can tune timeouts itself; manage settings via migrations/ops or controlled APIs.

## 9. Setting Up the Two-Session PostgreSQL Lab

The next sections require **two independent connections** to the same database: Session A and Session B. Use a **test** database—never production. If `timeout_lab` already exists, pick another database or schema name; do not delete non-lab data.

### 9.1. Create Schema

~~~sql
CREATE SCHEMA timeout_lab;
~~~

### 9.2. Create Inventory Table

~~~sql
CREATE TABLE timeout_lab.inventory (
    sku TEXT PRIMARY KEY,
    stock INTEGER NOT NULL CHECK (stock >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO timeout_lab.inventory (sku, stock)
VALUES ('BOOK-001', 10), ('BOOK-002', 20);
~~~

### 9.3. Create Notes Table

~~~sql
CREATE TABLE timeout_lab.notes (
    note_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    content TEXT NOT NULL
);

INSERT INTO timeout_lab.notes (content)
VALUES ('A'), ('B'), ('C');
~~~

### 9.4. How to Run

- Session A holds a lock without committing right away.
- Session B runs an SQL statement needing the lock with timeouts set.
- Optionally open Session C to observe while B is waiting.
- Always end test transactions with `COMMIT` or `ROLLBACK`.
- If B errors inside an explicit `BEGIN`, roll back B before running anything else.
- In a GUI tool, verify A and B truly use **two distinct backend connections**, not two editor tabs sharing one connection.

## 10. Lab 1: lock_timeout on a Row UPDATE

### 10.1. Session A — Hold the Row Lock

~~~sql
BEGIN;

UPDATE timeout_lab.inventory
SET stock = stock + 1
WHERE sku = 'BOOK-001';

-- Do not COMMIT/ROLLBACK yet.
~~~

### 10.2. Session B — Wait for the Lock

~~~sql
BEGIN;

SET LOCAL lock_timeout = '500ms';
SET LOCAL statement_timeout = '10s';

UPDATE timeout_lab.inventory
SET stock = stock - 1
WHERE sku = 'BOOK-001';
~~~

B tries to update the same row currently modified by A's uncommitted transaction.

After ~500ms of lock waiting, B receives:

~~~text
ERROR: canceling statement due to lock timeout
SQLSTATE 55P03
~~~

### 10.3. Cleanup

Session B:

~~~sql
ROLLBACK;
~~~

Session A:

~~~sql
ROLLBACK;
~~~

Using `ROLLBACK` in A returns stock to pre-lab state. If A ran `COMMIT`, the stock increment persists.

### 10.4. Takeaways

- B failed because it **could not acquire the lock in time**.
- A was not canceled by B's `lock_timeout`.
- B did not force A to release its lock.
- If A releases the lock before 500ms elapses, B proceeds and succeeds.

## 11. Lab 2: statement_timeout Without Lock Contention

On a connection without an explicit `BEGIN`:

~~~sql
SET lock_timeout = '200ms';
SET statement_timeout = '500ms';

SELECT pg_sleep(2);
~~~

PostgreSQL returns:

~~~text
ERROR: canceling statement due to statement timeout
SQLSTATE 57014
~~~

`pg_sleep(2)` simulates a slow-running statement, not waiting on a row lock held by another session.

### 11.1. Why Not 55P03?

`lock_timeout` does not measure general statement runtime. No lock request was blocked long enough to trigger `lock_timeout`.

### 11.2. Cleanup

~~~sql
RESET lock_timeout;
RESET statement_timeout;
~~~

Never run long `pg_sleep` calls in production. Labs only need short durations to observe behavior.

## 12. Lab 3: statement_timeout Wins Even While Waiting on a Lock

### 12.1. Session A

~~~sql
BEGIN;

UPDATE timeout_lab.inventory
SET stock = stock + 1
WHERE sku = 'BOOK-001';

-- Keep transaction open.
~~~

### 12.2. Session B

~~~sql
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '500ms';

UPDATE timeout_lab.inventory
SET stock = stock - 1
WHERE sku = 'BOOK-001';
~~~

B is waiting for the lock, yet the overall 500ms statement timer expires first. The error is:

~~~text
ERROR: canceling statement due to statement timeout
SQLSTATE 57014
~~~

### 12.3. Cleanup

In B:

~~~sql
ROLLBACK;
~~~

In A:

~~~sql
ROLLBACK;
~~~

### 12.4. Comparing the Three Labs

| Lab | `lock_timeout` | `statement_timeout` | Scenario | Expected |
|---|---:|---:|---|---|
| 1 | 500ms | 10s | Waiting on row lock | `55P03` |
| 2 | 200ms | 500ms | `pg_sleep(2)` | `57014` |
| 3 | 5s | 500ms | Waiting on row lock | `57014` |

Exact firing times vary slightly under server load. When two timers are close together, never rely on millisecond-exact error ordering.

## 13. Lab 4: Plain SELECT Can Still Hit lock_timeout

A plain `SELECT` does not block normal `UPDATE`s thanks to MVCC and lock compatibility, yet it still needs a table lock and can be blocked by `ACCESS EXCLUSIVE`.

### 13.1. Session A

~~~sql
BEGIN;

LOCK TABLE timeout_lab.notes IN ACCESS EXCLUSIVE MODE;

-- Keep transaction open.
~~~

### 13.2. Session B

~~~sql
BEGIN;

SET LOCAL lock_timeout = '600ms';
SET LOCAL statement_timeout = '5s';

SELECT COUNT(*)
FROM timeout_lab.notes;
~~~

While A holds the lock, B's `SELECT` hits `55P03`.

### 13.3. Cleanup

Session B:

~~~sql
ROLLBACK;
~~~

Session A:

~~~sql
ROLLBACK;
~~~

### 13.4. Meaning

It is wrong to say **"SELECTs never block on locks."** Always consider the requested lock mode and currently held locks, especially around DDL or explicit `LOCK TABLE`.

## 14. What State Is a Transaction In After a Timeout?

### 14.1. Autocommit

When `SELECT pg_sleep(2)` hits `statement_timeout` without an explicit `BEGIN`, that statement's implicit transaction is aborted. The connection normally remains usable for the next statement if still healthy.

### 14.2. Explicit Transaction

~~~sql
BEGIN;

SET LOCAL statement_timeout = '400ms';

SELECT pg_sleep(2);
-- ERROR 57014

SELECT 1;
-- Reports: current transaction is aborted.

ROLLBACK;
~~~

Any failed statement inside an explicit transaction puts the transaction into a failed/aborted state. Running another `SELECT` does not heal it.

### 14.3. An UPDATE Before the Timeout Does Not Commit Automatically

~~~sql
BEGIN;

UPDATE timeout_lab.inventory
SET stock = stock + 1
WHERE sku = 'BOOK-002';

SELECT pg_sleep(2);
-- If this times out, the transaction is aborted.

ROLLBACK;
~~~

The earlier `UPDATE` is never committed. If the application reported success **before `COMMIT`**, it lied.

### 14.4. SAVEPOINT

PostgreSQL supports `SAVEPOINT` and `ROLLBACK TO SAVEPOINT` to recover from statement errors inside a transaction:

~~~sql
BEGIN;

SAVEPOINT before_optional_step;

-- Optional step that might fail.
-- On error: ROLLBACK TO SAVEPOINT before_optional_step.

COMMIT;
~~~

Yet a savepoint does not guarantee earlier business decisions remain valid after a failure. Workflows depending on read state should roll back and re-evaluate the entire transaction.

## 15. Timeouts Do Not Fix the Blocker

Scenario:

~~~text
Session A:
  BEGIN
  UPDATE inventory WHERE sku='BOOK-001'
  waits 20s on payment API without COMMITting

Session B:
  UPDATE same SKU
  lock_timeout 500ms
  => B fails with 55P03

Session A remains open.
~~~

B's error **does not automatically roll back A**. So if many requests keep hitting `55P03`, do not simply raise B's retries—find out why A is holding the lock so long.

### 15.1. Common Bug Patterns

- Forgetting `COMMIT`/`ROLLBACK` in exception branches.
- Calling external services inside an open transaction.
- Keeping one transaction open across multiple user interactions.
- Workers holding connections open while waiting on queues.
- DDL/migrations opening `BEGIN` and getting abandoned.
- Connection pools returning connections still inside an open transaction.

### 15.2. Short Transactions Are Crucial

Keep transactions open only for the atomic DB work, avoiding slow network calls while holding row locks. Timeouts are guardrails, not substitutes for sound transaction boundaries.

## 16. pg_stat_activity: Which Backend Is Waiting on a Lock?

From an observer connection:

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
    now() - xact_start AS transaction_age
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
ORDER BY xact_start NULLS LAST;
~~~

### 16.1. wait_event_type='Lock'

This indicates the backend is waiting on a lock. However, a slow query does not necessarily show `wait_event_type='Lock'`: it might be waiting on I/O, WAL, client, or burning CPU.

### 16.2. state='idle in transaction'

A session sitting idle between SQL statements **still keeps its transaction open** and holds previously acquired locks. This is one of the most common causes of contention.

### 16.3. xact_start Differs from query_start

- `xact_start`: when the currently open transaction started.
- `query_start`: when the tracked SQL statement started.
- A transaction can live much longer than its last statement.

Searching only for "long-running active queries" misses blockers sitting `idle in transaction`.

### 16.4. Monitoring Privileges

Roles lacking privileges to inspect other sessions see limited details. Use an appropriate monitoring role without over-granting unnecessary privileges.

## 17. pg_blocking_pids: Who Is Blocking Whom?

~~~sql
SELECT
    a.pid,
    a.state,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blocking_pids,
    a.query
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
  AND a.wait_event_type = 'Lock'
ORDER BY a.pid;
~~~

When B waits on a row lock held by A, `blocking_pids` contains A's PID.

### 17.1. Capture State While Waiting

If B times out after 500ms and you run your monitoring query afterward, B is no longer waiting on the lock. Thus an empty snapshot **does not prove contention never happened**.

### 17.2. Blockers Can Be Idle

A transaction holding locks while `idle in transaction` still appears in B's blocking PIDs even though A is running no SQL at the moment of inspection.

### 17.3. Lock Queues Matter Too

A backend can be blocked by an active lock holder or by another waiting request ahead in the queue, depending on lock semantics. Do not rely on simple PID pairs alone to infer every lock dependency.

## 18. pg_locks: Reading mode and granted

~~~sql
SELECT
    pid,
    locktype,
    mode,
    granted,
    relation::regclass AS relation_name,
    page,
    tuple
FROM pg_locks
WHERE pid IS NOT NULL
ORDER BY pid, locktype, mode;
~~~

| Column | Meaning |
|---|---|
| `pid` | Associated backend |
| `locktype` | Lock object type |
| `mode` | Lock mode |
| `granted` | Granted or waiting |
| `relation_name` | Related relation when applicable |
| `page`, `tuple` | Details for certain lock types |

### 18.1. Do Not Look for Row Locks via a Single Row Type

During same-row `UPDATE` contention, the waiting backend typically shows a lock on `transactionid`, not simply a `tuple` row naming the row. Combining `pg_blocking_pids` and `pg_stat_activity` is usually much easier for diagnosis.

### 18.2. pg_locks Is Current State

It is not a historical table of `55P03`/`57014` errors. Tracking error rates over time requires application metrics or server logs.

## 19. FOR UPDATE NOWAIT and SKIP LOCKED

Sometimes you want contention behavior based on workflow semantics rather than a time wait.

### 19.1. NOWAIT

~~~sql
BEGIN;

SELECT sku, stock
FROM timeout_lab.inventory
WHERE sku = 'BOOK-001'
FOR UPDATE NOWAIT;

COMMIT;
~~~

If the row holds a conflicting lock, `NOWAIT` fails immediately instead of waiting on the row lock.

### 19.2. SKIP LOCKED

~~~sql
BEGIN;

SELECT sku, stock
FROM timeout_lab.inventory
WHERE stock > 0
ORDER BY sku
FOR UPDATE SKIP LOCKED
LIMIT 1;

COMMIT;
~~~

`SKIP LOCKED` skips currently locked rows. Useful for worker queues where **any available job** can be picked.

### 19.3. Never Use SKIP LOCKED When You Need One Exact Row

If a request must update specifically `BOOK-001`, skipping the locked row and returning empty can mislead the application into thinking "product not found."

### 19.4. NOWAIT Does Not Fully Replace lock_timeout

`NOWAIT` applies to supported locking clauses. A statement can still wait on table-level locks or other lock types. `lock_timeout` caps lock waits across relevant requests generally.

### 19.5. SKIP LOCKED Does Not Bypass Every Lock Type

`FOR UPDATE SKIP LOCKED` still acquires required table locks; never assume it is immune to DDL contention.

## 20. lock_timeout in Migrations and DDL

Some `ALTER TABLE` commands require strong locks. Waiting too long causes lock queues and latency spikes for applications.

### 20.1. Fail Fast When Unable to Acquire the Lock

~~~sql
BEGIN;

SET LOCAL lock_timeout = '1s';
SET LOCAL statement_timeout = '30s';

ALTER TABLE timeout_lab.inventory
ADD COLUMN warehouse_note TEXT;

COMMIT;
~~~

In the lab, this adds a new column. Do not re-run verbatim once the column exists, and never run directly in production without a migration plan.

### 20.2. Two Separate Budgets

- `lock_timeout='1s'`: if the lock cannot be acquired promptly, abort early.
- `statement_timeout='30s'`: once the lock is acquired, still caps total execution time.

### 20.3. DDL Can Both Wait and Run Long

Some schema changes must scan, validate, or rewrite tables. `lock_timeout` does not bound that execution work. Choose timeouts per migration type, data size, and SLA.

### 20.4. CREATE INDEX CONCURRENTLY

`CREATE INDEX CONCURRENTLY` cannot run inside an explicit transaction block. Never copy a `BEGIN` + `SET LOCAL` template blindly for every migration. Migration tools must scope settings appropriately for each command and transaction context.

### 20.5. Retrying Migrations Differs from Retrying Requests

A migration may have earlier committed steps. After a timeout, verify actual schema state and checkpoints/idempotency before retrying instead of blindly re-running an entire SQL script.

## 21. idle_in_transaction_session_timeout

This parameter addresses a completely different problem from the main two:

~~~sql
SHOW idle_in_transaction_session_timeout;
~~~

It targets **sessions sitting idle while still inside a transaction** for too long. Once triggered, PostgreSQL terminates the session to free resources and locks.

### 21.1. Comparison

| Parameter | Targets |
|---|---|
| `lock_timeout` | A single lock-wait attempt |
| `statement_timeout` | SQL statement execution time |
| `idle_in_transaction_session_timeout` | Session idle inside a transaction |
| `idle_session_timeout` | Session idle outside a transaction per config |
| `deadlock_timeout` | Threshold before deadlock check, not a general kill-after-wait timer |

### 21.2. Pool Impact

If PostgreSQL terminates an idle session, the connection pool must recognize that the connection is dead. Configure validation/recovery so subsequent requests do not use a closed connection.

### 21.3. Never Use Timeouts to Replace Proper Transaction Closing

Code must still `COMMIT` or `ROLLBACK` in `finally`/transaction managers. Session timeouts are safety nets, not normal business control flow.

## 22. transaction_timeout on Supported Versions

Newer PostgreSQL versions offer `transaction_timeout` to bound total transaction duration via server semantics. Because not all versions support it, check **`server_version`** and `pg_settings` before using it.

~~~sql
SHOW server_version;

SELECT name, setting, unit
FROM pg_settings
WHERE name = 'transaction_timeout';
~~~

If the `SELECT` returns no rows, your server version does not expose this parameter.

### 22.1. Differs from statement_timeout

A transaction can run multiple statements; `transaction_timeout` targets transaction lifetime per version semantics, not a single `SELECT` or `UPDATE`.

### 22.2. Does Not Replace Application Deadline Management

A transaction staying open because it waits on an external API still needs to be shortened. Timeouts only clean up the aftermath; the application must define when to abort, retry, and respond.

### 22.3. Operational Rule

Never put a parameter missing from your running server version into production config scripts without checking. Server/role/database GUC changes require rollout plans and privilege checks.

## 23. deadlock_timeout Is Not lock_timeout

A **deadlock** is a lock-wait cycle:

~~~text
T1 holds lock A, waits for lock B.
T2 holds lock B, waits for lock A.
~~~

PostgreSQL detects this and aborts one transaction, typically with **SQLSTATE `40P01`**.

`deadlock_timeout` is the **wait duration before running deadlock detection**, and also governs lock-wait logging when `log_lock_waits` is enabled. It **does not mean every lock wait exceeding that value is canceled**.

### 23.1. Three Errors to Distinguish

| SQLSTATE | Context |
|---|---|
| `55P03` | Lock unavailable per rules, including `lock_timeout`/`NOWAIT` |
| `57014` | Query canceled, including `statement_timeout` |
| `40P01` | Deadlock detected |

### 23.2. Preventing Deadlocks Properly

Keep transactions short, acquire locks in consistent order, narrow lock scope, and retry the entire transaction when a deadlock occurs.

Never drop `lock_timeout` to a few milliseconds to mask an unordered locking protocol.

## 24. Client Timeouts vs. Server Timeouts

A request spans multiple timer layers:

~~~text
Browser
  |
API gateway                -> request timeout
  |
Application service        -> business deadline
  |
Connection pool            -> pool acquire timeout
  |
JDBC driver                -> query timeout / socket timeout
  |
PostgreSQL
  |-- lock_timeout
  |-- statement_timeout
  |-- other session/transaction timers
~~~

### 24.1. JDBC setQueryTimeout

~~~java
PreparedStatement ps = connection.prepareStatement(sql);
ps.setQueryTimeout(5);
~~~

In JDBC, `setQueryTimeout` takes **seconds**, whereas PostgreSQL GUCs take milliseconds when given unitless integers. Drivers implement query cancellation via their own mechanism.

`ps.setQueryTimeout(5)` **should not be treated as strictly identical** to `SET statement_timeout='5s'` in every respect.

### 24.2. Pool Wait Is Outside statement_timeout

If a request waits 2 seconds to borrow a connection and the SQL takes 1 second, `statement_timeout=2s` will not cancel the SQL even though total request latency is 3 seconds.

### 24.3. HTTP Timeouts Do Not Guarantee Database Rollback

A gateway returning 504 does not prove the SQL stopped immediately. The driver must cancel or the connection/transaction manager must roll back per protocol.

### 24.4. Layered Deadline Design

Illustrative guidance for one small `UPDATE`:

~~~text
lock_timeout         300ms
statement_timeout   2500ms
API request limit   5000ms
~~~

For requests with multiple statements and retries, budget total time accordingly. Never apply one fixed set of numbers to every workload.

## 25. Java/JDBC: Setting Per-Transaction Timeouts and Handling SQLSTATE

Example inventory reservation transaction:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public class StockService {
    private final DataSource dataSource;

    public StockService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean reserveOne(String sku) throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                try (PreparedStatement settings =
                        connection.prepareStatement(
                            "SELECT set_config('lock_timeout', '500ms', true), " +
                            "set_config('statement_timeout', '3s', true)")) {
                    settings.execute();
                }

                try (PreparedStatement update =
                        connection.prepareStatement(
                            "UPDATE timeout_lab.inventory " +
                            "SET stock = stock - 1 " +
                            "WHERE sku = ? AND stock >= 1")) {
                    update.setString(1, sku);
                    int changed = update.executeUpdate();

                    if (changed != 1) {
                        connection.rollback();
                        return false;
                    }
                }

                connection.commit();
                return true;

            } catch (SQLException error) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }

                switch (error.getSQLState()) {
                    case "55P03":
                        // Lock timeout or lock-not-available.
                        break;
                    case "57014":
                        // Query canceled: timeout or external cancellation.
                        break;
                    case "40P01":
                        // Deadlock; may need transaction retry.
                        break;
                    default:
                        // Other errors need dedicated handling.
                }
                throw error;
            }
        }
    }
}
~~~

### 25.1. set_config with is_local=true

Running:

~~~sql
SELECT
    set_config('lock_timeout', '500ms', true),
    set_config('statement_timeout', '3s', true);
~~~

**inside a transaction** sets local config for that transaction only. It behaves like two `SET LOCAL` calls, avoiding leaked session timeouts in connection pools.

### 25.2. Never Return Success Before COMMIT

`executeUpdate()` returns the affected row count, yet the transaction is not committed yet. Return `true` only after `connection.commit()` succeeds.

### 25.3. SQLException Can Come From Many Sources

`57014` is query-canceled, not exclusively `statement_timeout`. Check context and server messages. Network/pool errors have completely different codes and cannot simply be solved by SQL retries.

### 25.4. Production Needs Managed Connection State

A framework transaction manager or pool provides safer handling for `autoCommit`, isolation, and rollback. Sample code does not replace full connection lifecycle governance in production.

## 26. Retries: When Should You Retry?

| Situation | Typical response to consider |
|---|---|
| `55P03` from a short transaction holding a lock | Bounded retry with backoff/jitter |
| `55P03` from a blocker idle for minutes | Investigate and fix the blocker |
| `57014` from heavy join/sort query | Optimize query or justify a larger budget |
| `57014` from long lock wait | Analyze contention, tune thresholds |
| `40P01` deadlock | Roll back and retry entire transaction |
| `40001` serialization failure | Retry entire transaction, re-read/re-evaluate |
| `23505` unique violation | Usually handle business conflict |
| Client timeout with unknown `COMMIT` | Check idempotency/reconciliation |

### 26.1. Retries Must Not Be Immediate and Infinite

On a hot row, hundreds of immediate retries worsen contention. Use attempt caps, exponential backoff/jitter, deadlines, and metrics.

### 26.2. Retry the Whole Transaction When Decisions Depend on Read Data

If a workflow `SELECT`s stock then `UPDATE`/`INSERT`s an order, after an error it must roll back and re-read data in a new attempt. Never repeat only the last SQL statement using stale read decisions.

### 26.3. External Side Effects Require Idempotency

If a service already called a payment API or sent an email before PostgreSQL timed out or rolled back, uncontrolled retries cause duplicate charges or notifications. Use idempotency keys, outbox/inbox, and reconciliation.

### 26.4. Do Not Stretch SLAs Just to Hide Errors

Raising `lock_timeout` from 500ms to 30 seconds reduces `55P03` counts while ruining P99 latency, exhausting connection pools, and piling up queued requests. Measure overall impact.

## 27. Timeouts in Multi-Statement Transactions

A workflow may need:

1. Read customer.
2. Check duplicate order.
3. Deduct stock.
4. Insert order.
5. Insert `order_items`.
6. `COMMIT`.

If each takes 1.5s under `statement_timeout=2s`, total transaction time exceeds 7s even though no single statement times out.

### 27.1. Need a Transaction-Level Deadline

Combine application deadlines, server `transaction_timeout` (if supported), and short transactions by moving non-atomic work outside the transaction.

### 27.2. Timeouts Do Not Replace Invariants

For inventory, enforce:

~~~sql
UPDATE timeout_lab.inventory
SET stock = stock - 2
WHERE sku = 'BOOK-001'
  AND stock >= 2
RETURNING stock;
~~~

A lock timeout will not prevent negative stock if code writes bad values. `CHECK` constraints and atomic predicates protect data invariants; timeouts protect resources and latency.

## 28. Performance: When to Tune Queries vs. Locks?

### 28.1. Query Slow From Reading Too Much Data

~~~sql
EXPLAIN
SELECT sku, SUM(stock)
FROM timeout_lab.inventory
GROUP BY sku;
~~~

`EXPLAIN` shows the estimated plan. In a test database you can measure:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sku, SUM(stock)
FROM timeout_lab.inventory
GROUP BY sku;
~~~

`EXPLAIN ANALYZE` **actually executes the query**, so never run it carelessly on DML or heavy production queries.

### 28.2. Query Slow Due to a Blocker

An indexed `UPDATE` finds the SKU quickly yet still waits on a row lock if another transaction is updating that SKU. Indexes do not eliminate writer coordination.

### 28.3. Reducing Lock Contention

- Keep transactions short.
- Avoid external API calls inside transactions.
- Update rows in small batches when appropriate.
- Acquire locks in consistent order.
- Reduce concurrent writers hitting hot rows.
- Consider worker queues or sharding/partitioning load.
- Consider `NOWAIT`/`SKIP LOCKED` where semantics allow.

### 28.4. Improving Slow Execution

- Refresh statistics and inspect query plans.
- Add indexes matching filter predicates.
- Simplify queries and reduce join fanout.
- Paginate or bound returned data.
- Use pre-aggregation/materialized views for reports where appropriate.
- Size resources and manage workload.

Apply both checklists based on **evidence**, not a hunch that "the query timed out."

## 29. Logging and Metrics

~~~sql
SHOW log_lock_waits;
SHOW deadlock_timeout;
~~~

When `log_lock_waits` is enabled, PostgreSQL logs lock waits exceeding the threshold determined by `deadlock_timeout`. This is observability, not a query-canceling timeout.

### 29.1. Why Absence of Logs Doesn't Prove Absence of Lock Waits?

If `lock_timeout` is 300ms while the logging threshold is 1 second, statements fail **before** long-wait logs ever emit.

### 29.2. pg_stat_database Does Not Count 55P03/57014 Separately

~~~sql
SELECT
    datname,
    xact_commit,
    xact_rollback,
    deadlocks
FROM pg_stat_database
WHERE datname = current_database();
~~~

`deadlocks` counts deadlocks, not all timeouts. `xact_rollback` aggregates all rollback causes.

### 29.3. Track SQLSTATE by Operation

A system can emit metrics like:

~~~text
db_error_total{operation="reserve_stock", sqlstate="55P03"}
db_error_total{operation="orders_report", sqlstate="57014"}
db_transaction_duration_seconds{operation="checkout"}
db_retry_attempts_total{operation="reserve_stock"}
~~~

These are illustrative metric names. Never put emails, account IDs, or sensitive values in high-cardinality metric labels.

### 29.4. Pair Error Counts with Impact

What matters is not just timeout counts, but:

- Request failure rate after retries.
- P95/P99 latency.
- Waiting connection count.
- Transaction durations.
- Idle-blocker frequency.
- Deadlock and serialization failure counts.
- Impact on data correctness.

## 30. Real-World Scenarios

### 30.1. DDL Waiting on Locks During Deploy

A migration requests `ACCESS EXCLUSIVE` during peak traffic. A short `lock_timeout` makes the migration fail fast instead of piling up a lock queue. Still pair it with rollback/retry plans and per-DDL lock mode analysis.

### 30.2. Idle Transaction Holding a Hot Row

One request updates an SKU and waits on an external service. Other requests hit `lock_timeout`. The real fix is shortening the transaction or decoupling the external call; raising timeouts only worsens load.

### 30.3. Reports Hitting statement_timeout

A reporting query with heavy joins/aggregations needs 30 seconds while the role has `statement_timeout` set to 5 seconds. This is not necessarily a lock issue. Inspect the query plan and consider a dedicated reporting role/timeout.

### 30.4. Queue Workers Contending on Jobs

If workers may pick any ready job, `FOR UPDATE SKIP LOCKED` cuts busy-row waits. If a specific job is mandatory, `NOWAIT` or `lock_timeout` is clearer.

### 30.5. JDBC Reports Timeout While Backend Keeps Running

Client timeouts do not guarantee instant server cancellation. Audit driver behavior, connection state, `pg_stat_activity`, and transaction cleanup instead of blindly raising socket timeouts.

### 30.6. Migration Running in an Inappropriate Transaction

`CREATE INDEX CONCURRENTLY` cannot run inside an explicit transaction block. Configure timeouts and migration runners per command rather than forcing one `BEGIN`/`SET LOCAL` wrapper on everything.

## 31. Common Misconceptions

### 31.1. "lock_timeout is the maximum runtime of a query"

False. It limits time spent **waiting to acquire locks**.

### 31.2. "statement_timeout only counts CPU"

False. It counts total server-side statement processing time, including lock waits.

### 31.3. "lock_timeout 500ms means total lock wait time cannot exceed 500ms"

False. Each lock acquisition wait is timed independently.

### 31.4. "statement_timeout 2s means a transaction can run at most 2s"

False. It applies per statement.

### 31.5. "A transaction holding a lock will release it after 500ms due to lock_timeout"

False. There is no such hold-time cap.

### 31.6. "SELECTs are never blocked by locks"

False. `SELECT` can wait on table locks conflicting with `ACCESS EXCLUSIVE`.

### 31.7. "UPDATE always blocks every SELECT on the same table"

False. MVCC and lock modes let compatible reads and writes run concurrently.

### 31.8. "Set lock_timeout >= statement_timeout to distinguish lock errors"

Usually pointless because `statement_timeout` expires first.

### 31.9. "SET LOCAL in autocommit affects the next request"

False. `SET LOCAL` requires an explicit transaction block.

### 31.10. "RESET always sets it back to 0"

False. It restores the effective role/database/server default.

### 31.11. "SET in a connection pool doesn't affect future requests"

False if session-level `SET` is not reset.

### 31.12. "55P03 and 57014 are the same error"

False. They represent different cancellation causes and mechanisms.

### 31.13. "Every 57014 is definitely statement_timeout"

False. `query_canceled` also fires on client or admin cancellation.

### 31.14. "deadlock_timeout cancels all long lock waits"

False. It governs deadlock-check timing, not normal lock wait limits.

### 31.15. "NOWAIT and lock_timeout are identical"

False. `NOWAIT` fails fast on supported lock requests; `lock_timeout` allows bounded waiting.

### 31.16. "SKIP LOCKED works for every query"

False. It changes which rows are processed and breaks queries needing an exact row.

### 31.17. "One statement timing out inside BEGIN doesn't affect prior statements"

The transaction enters an aborted state and prior uncommitted changes roll back.

### 31.18. "RETURNING succeeding means the transaction committed"

False. Only a successful `COMMIT` confirms transaction persistence.

### 31.19. "Just raising timeouts reduces risk"

False. It often worsens P99 latency, connection exhaustion, and lock queues.

### 31.20. "Seeing no blocker after a timeout means no blocker existed"

False. The lock wait may have ended before sampling.

### 31.21. "pg_locks is a historical log of all lock timeouts"

False. It shows current lock state only.

### 31.22. "HTTP 504 means PostgreSQL rolled back"

False. Check cancellation, driver state, session state, and commit status.

### 31.23. "Timeouts replace stock >= 0 checks"

False. Timeouts control time, not data invariants.

## 32. Practice Exercises

### Exercise 1 — Measurement

A `SELECT` takes 8 seconds sorting without waiting on locks. Will `lock_timeout='500ms'` cancel it for running long?

**Hint:** No; `statement_timeout` measures total SQL statement duration.

### Exercise 2 — 3-Second Row Lock

T1 holds a row lock for 3 seconds. T2 has `lock_timeout='400ms'` and `statement_timeout='5s'`. Expected SQLSTATE?

**Answer:** `55P03`.

### Exercise 3 — Shorter Statement Timeout

T2 waits 3 seconds on a lock, with `lock_timeout='5s'` and `statement_timeout='600ms'`. Expected SQLSTATE?

**Answer:** `57014`.

### Exercise 4 — Multiple Lock Waits

Three 400ms lock waits occur with `lock_timeout=500ms`. Is `lock_timeout` guaranteed to cancel because the total is 1.2s?

**Hint:** No.

### Exercise 5 — Units

Is `SET statement_timeout = 5` equal to 5ms or 5s?

**Answer:** 5ms.

### Exercise 6 — Value 0

Does setting `lock_timeout = 0` turn every lock request into `NOWAIT`?

**Answer:** No; it disables `lock_timeout`.

### Exercise 7 — SET LOCAL

Why is `SET LOCAL` safer than session `SET` for one transaction in a connection pool?

**Hint:** The setting ends with the transaction, avoiding session leaks.

### Exercise 8 — RESET

Does `RESET` always restore the value to 0?

**Hint:** No, it restores the effective default.

### Exercise 9 — pg_sleep Lab

What does `SELECT pg_sleep(2)` with `statement_timeout` 500ms normally raise?

**Answer:** `57014`.

### Exercise 10 — Autocommit

A statement times out outside an explicit `BEGIN`, leaving the connection healthy. Can you run the next `SELECT`?

**Hint:** Usually yes.

### Exercise 11 — Inside BEGIN

A `SELECT` times out mid-transaction. What must you do before starting a new transaction?

**Answer:** `ROLLBACK` before starting fresh.

### Exercise 12 — Idle Blocker

Session A sits `idle in transaction` holding a row lock. Which timeout targets Session A if it stays idle too long?

**Answer:** `idle_in_transaction_session_timeout`.

### Exercise 13 — DDL

Why is a short `lock_timeout` helpful for certain `ALTER TABLE` migrations?

**Hint:** Fails fast instead of waiting long for a strong lock and stalling traffic.

### Exercise 14 — CREATE INDEX CONCURRENTLY

Can it run inside an explicit `BEGIN`?

**Answer:** No.

### Exercise 15 — ACCESS EXCLUSIVE

T1 runs `LOCK TABLE notes ACCESS EXCLUSIVE`; can T2's `SELECT COUNT(*)` be blocked?

**Answer:** Yes.

### Exercise 16 — SHOW

Write SQL to inspect effective timeouts:

~~~sql
SHOW lock_timeout;
SHOW statement_timeout;
~~~

### Exercise 17 — pg_settings

Which column identifies where a parameter's value came from?

**Hint:** `source`.

### Exercise 18 — pg_stat_activity

What does `wait_event_type='Lock'` indicate?

**Hint:** The backend is waiting on a lock object.

### Exercise 19 — Blocking PIDs

Which function returns the PIDs blocking a backend?

**Answer:** `pg_blocking_pids(pid)`.

### Exercise 20 — pg_locks

Which column shows whether a lock request has been granted?

**Answer:** `granted`.

### Exercise 21 — NOWAIT

An application needs one exact locked SKU and refuses to wait. Choose `NOWAIT` or `SKIP LOCKED`?

**Hint:** `NOWAIT` to detect contention on that exact SKU.

### Exercise 22 — SKIP LOCKED

A queue worker takes any unlocked job. Which mechanism fits?

**Hint:** `FOR UPDATE SKIP LOCKED` with a proper transaction claim protocol.

### Exercise 23 — Deadlock

Two transactions acquire A and B in reverse order. Typical SQLSTATE?

**Answer:** `40P01`.

### Exercise 24 — Log Lock Waits

Does `log_lock_waits` automatically cancel queries?

**Answer:** No; it is for logging.

### Exercise 25 — Metrics

Does `pg_stat_database.deadlocks` count all `55P03` errors?

**Answer:** No.

### Exercise 26 — Retry

When `55P03` occurs on a hot row, should you retry infinitely right away?

**Hint:** No, use bounded retries, backoff, and deadlines.

### Exercise 27 — Client Deadline

HTTP timeout is 1s and `statement_timeout` is 10s. Is the database guaranteed to cancel SQL before HTTP 504?

**Answer:** No.

### Exercise 28 — Multi-Statement Transaction

Three `SELECT`s take 1.5s each under `statement_timeout` 2s. Can total transaction time exceed 2s?

**Answer:** Yes.

### Exercise 29 — Invariant

Write an `UPDATE` deducting 3 units of stock only if enough remains:

~~~sql
UPDATE timeout_lab.inventory
SET stock = stock - 3
WHERE sku = 'BOOK-001'
  AND stock >= 3
RETURNING stock;
~~~

### Exercise 30 — Idempotency

Why does a client retrying order creation after a network timeout need an idempotency key?

**Hint:** The prior request may have committed, so you must avoid creating duplicates.

### Exercise 31 — Role Defaults

Does `ALTER ROLE` setting a new `statement_timeout` immediately update open pooled connections?

**Hint:** No; consider reconnects or direct session config.

### Exercise 32 — Tracing Root Causes

A request fails with `57014`. Which cause categories must you distinguish?

**Hint:** Lock waits, heavy execution, I/O, function delays, and external cancellations.

### Exercise 33 — Good Query Still Blocked

An `UPDATE` uses an index to find the row in 1ms, yet T1 holds the row lock for 10s. Does the index remove contention?

**Answer:** No.

### Exercise 34 — Lock Hold

T1 holds a lock for 30s while T1 has `lock_timeout=500ms`. Does T1 automatically release its lock after 500ms?

**Answer:** No.

### Exercise 35 — Proposing Configuration

For a fast OLTP update, suppose you try `lock_timeout` 300ms and `statement_timeout` 3s. Explain the two budgets and what metrics to measure for tuning.

**Hint:** One caps lock waiting, the other caps the entire statement; measure latency, contention, retries, and real errors.

## 33. Quick Reference Table

| Need | PostgreSQL feature or approach |
|---|---|
| Limit lock wait time | `lock_timeout` |
| Limit entire statement time | `statement_timeout` |
| Inspect settings | `SHOW lock_timeout; SHOW statement_timeout;` |
| Disable respective limit | `SET ... = 0` |
| Scope temporarily to transaction | `SET LOCAL ...` |
| Set for session | `SET ...` |
| Revert to effective default | `RESET ...` |
| Set role default | `ALTER ROLE ... SET ...` |
| Set database default | `ALTER DATABASE ... SET ...` |
| Error on excessive lock wait | `55P03` |
| Error on canceled query | `57014` |
| Error on deadlock | `40P01` |
| Detect locked row without waiting | `FOR UPDATE NOWAIT` |
| Skip locked rows in a queue | `FOR UPDATE SKIP LOCKED` |
| Limit idle time inside transaction | `idle_in_transaction_session_timeout` |
| Limit entire transaction | `transaction_timeout` if version supports it |
| Deadlock check threshold | `deadlock_timeout` |
| Log long lock waits | `log_lock_waits` |
| Monitor backends | `pg_stat_activity` |
| Find blockers | `pg_blocking_pids(pid)` |
| Inspect lock modes | `pg_locks` |
| Analyze query plan | `EXPLAIN` |
| Timeout in explicit transaction | `ROLLBACK` or savepoint handling |
| Retry on transient lock contention | Bounded, backoff, re-check conditions |
| JDBC/HTTP timeouts | Separate from server timeouts; coordinate deadlines |
| Operations with external side effects | Idempotency / outbox / reconciliation |

---

## Conclusion

**`lock_timeout` and `statement_timeout` solve two distinct problems.** `lock_timeout` caps **each wait to acquire a lock**, whereas `statement_timeout` caps **the total server processing time of an SQL statement**, including lock wait time. When used together, `lock_timeout` is usually set **smaller** than `statement_timeout` so a statement does not wait too long for a lock while still getting normal execution time once the lock is granted.

SQLSTATE **`55P03`** reflects lock unavailability/lock timeout, whereas **`57014`** reflects query cancellation, including statement timeout. A timeout on a waiting session **does not cancel the other transaction holding the lock**, and neither parameter is a **whole-transaction deadline**. Inside an explicit transaction, a timed-out statement puts the transaction into an aborted state requiring rollback before retrying.

In practice, use **`SET LOCAL`** to scope timeouts per transaction, combine **`pg_stat_activity`**, **`pg_blocking_pids`**, and **`pg_locks`** to locate blockers, use **`EXPLAIN`** for slow execution, and configure **`idle_in_transaction_session_timeout`** to contain abandoned transactions. Under high concurrency, keep retries bounded and idempotent; for migrations, choose timeouts and rollback plans suited to each DDL operation.

The golden rule: **before raising a timeout, check whether the SQL is waiting on a lock or genuinely running slow; before retrying, verify the old transaction ended and business conditions still hold.** Keeping those two timers clear lets your system fail fast where needed while allowing healthy queries to finish.
