# Releasing Locks, Canceling Queries, and Safely Terminating Sessions in PostgreSQL

## 1. Scenario: An `UPDATE` Statement Hangs Because of Another Transaction

An application has an `orders` table. An operator notices an `UPDATE` statement has been running for nearly a minute without completing:

```sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = 1001;
```

An impulsive reaction might be to grab a PostgreSQL PID and call `pg_terminate_backend(pid)`. But what happens if that PID is processing an uncommitted money transfer? What if the terminated PID is a critical worker? What if the waiting query is merely the **victim**, while the real lock is held by another session sitting `idle in transaction`?

Three actions must be distinguished:

1. **Releasing a lock**: properly ending the transaction, releasing a session-level advisory lock, or using the appropriate mechanism for that lock type.
2. **Canceling a running query**: asking PostgreSQL to stop the current statement, typically with `pg_cancel_backend(pid)`.
3. **Terminating a session/backend**: forcefully disconnecting the client and aborting uncommitted transactions, typically with `pg_terminate_backend(pid)`.

These three actions **are not synonymous**.

A session waiting on a lock can have its query canceled while the lock holder keeps running. A session holding a transaction lock can continue holding that lock after its current query ends. A **session-level advisory lock** can even survive both `COMMIT` and `ROLLBACK` if not explicitly unlocked.

> **Operational principle:** before intervening, determine **who is waiting, who is blocking, what type of lock it is, which transaction is still open, and the consequences of canceling or closing the connection**.

This lesson explains those mechanisms in PostgreSQL and provides reproducible experiments in a test database.

## 2. Learning Objectives

After this lesson, you will be able to:

1. Distinguish the lifecycles of table locks, row locks, transaction advisory locks, and session advisory locks.
2. Understand when `COMMIT`, `ROLLBACK`, `ROLLBACK TO SAVEPOINT`, `UNLOCK`, or backend termination releases locks.
3. Distinguish `pg_cancel_backend` and `pg_terminate_backend` in terms of target, transaction state, and outcome.
4. Query `pg_stat_activity`, `pg_locks`, and `pg_blocking_pids` to identify blockers and waiters.
5. Recognize an `active` session waiting on a lock vs. an `idle in transaction` session holding a lock.
6. Use `lock_timeout`, `statement_timeout`, and `idle_in_transaction_session_timeout` intentionally.
7. Understand common SQLSTATE errors after statement cancellation, timeout, deadlock, or connection loss.
8. Practice canceling a **waiter** without affecting the **blocker**, and vice versa.
9. Choose a safe course of action: wait, ask the client to commit/roll back, cancel, terminate, or investigate further.
10. Understand the impact on JDBC, connection pools, multi-step transactions, and idempotency requirements.
11. Recognize prepared transactions, special backends, and cases where you cannot simply "kill PID."
12. Establish an auditable incident response workflow that avoids business data loss.

## 3. How Long Do Locks in PostgreSQL Persist?

PostgreSQL has multiple locking mechanisms. When a lock is released depends on **how it was acquired** and **its ownership scope**.

| Lock Type / Acquisition Method | Typical Lifecycle | Appropriate Release Mechanism |
| --- | --- | --- |
| Table locks from `SELECT`, `INSERT`, `UPDATE`, `DELETE` | Transaction-scoped | `COMMIT` or `ROLLBACK`; autocommit releases when the statement's implicit transaction ends |
| Row locks from `UPDATE`/`DELETE`/`SELECT FOR UPDATE` | Transaction-scoped | End the transaction; subject to savepoint rules |
| `LOCK TABLE ... IN ... MODE` | Transaction-scoped | `COMMIT` or `ROLLBACK` |
| `pg_advisory_xact_lock(...)` | Transaction-scoped | End the transaction; there is no separate unlock function |
| `pg_advisory_lock(...)` | **Session**-scoped | `pg_advisory_unlock(...)`, `pg_advisory_unlock_all()` on the same session, or session end |
| `pg_advisory_lock_shared(...)` | **Session**-scoped | Matching `pg_advisory_unlock_shared(...)` or session end |
| Locks tied to a prepared transaction | After `PREPARE TRANSACTION`, may persist with no active regular backend | Decide `COMMIT PREPARED` or `ROLLBACK PREPARED` via 2PC procedure |
| Locks inside a subtransaction/savepoint | Depends on acquisition point and rollback to savepoint | Certain locks acquired after a savepoint are released when rolling back to it |

The table above covers common cases. Internally, the lock manager has many lock types and edge cases, so you should not infer from a single `pg_locks` row that every lock belongs to a single statement or transaction.

### 3.1. Autocommit Easily Confuses Beginners

With autocommit enabled in a client:

```sql
UPDATE lock_ops_lab.accounts
SET balance = balance + 5
WHERE account_id = 101;
```

the statement typically runs in its own implicit transaction. When the statement finishes and autocommits, its row and table locks are released.

If the client runs:

```sql
BEGIN;

UPDATE lock_ops_lab.accounts
SET balance = balance + 5
WHERE account_id = 101;

-- Neither COMMIT nor ROLLBACK.
```

then after `UPDATE` returns, the transaction remains open and locks required until transaction end **can still persist**.

Therefore, the right question is not "has the UPDATE finished?", but **"has the transaction containing the UPDATE ended?"**.

### 3.2. Locks Are Not Created Only by `LOCK` Statements

`UPDATE` can acquire row locks, necessary table-level locks, and wait on other transactions. Even an ordinary `SELECT` acquires an appropriate table lock to protect its access against incompatible DDL.

Thus, operators can encounter lock waits even when the application **never writes `LOCK TABLE`**.

## 4. Setting Up the Three-Connection Lab

Practice in a dedicated database; **never run lock-blocking, cancel, or terminate experiments on production**.

### 4.1. Create Schema and Sample Data

```sql
CREATE SCHEMA IF NOT EXISTS lock_ops_lab;

CREATE TABLE lock_ops_lab.accounts (
    account_id integer PRIMARY KEY,
    owner_name text NOT NULL,
    balance numeric(12,2) NOT NULL
        CHECK (balance >= 0)
);

INSERT INTO lock_ops_lab.accounts
    (account_id, owner_name, balance)
VALUES
    (101, 'An',   500.00),
    (202, 'Bình', 200.00),
    (303, 'Chi',  100.00);
```

Create a jobs table to illustrate logical lock contention:

```sql
CREATE TABLE lock_ops_lab.jobs (
    job_id integer PRIMARY KEY,
    status text NOT NULL
        CHECK (status IN ('PENDING', 'RUNNING', 'DONE')),
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO lock_ops_lab.jobs (job_id, status)
VALUES
    (1, 'PENDING'),
    (2, 'PENDING');
```

Verification queries:

```sql
SELECT * FROM lock_ops_lab.accounts ORDER BY account_id;
SELECT * FROM lock_ops_lab.jobs ORDER BY job_id;
```

Re-running `INSERT` on an already populated schema will raise a primary key duplicate error. Reinitialize a fresh database or reset cleanly before each test.

### 4.2. Open Three Independent Sessions

- **Session A**: lock holder (*holder*).
- **Session B**: blocked session (*waiter*).
- **Session C**: observer or signaling session.

In each `psql`/SQL client window, record its PID:

```sql
SELECT
    pg_backend_pid() AS my_pid,
    current_database() AS db_name,
    current_user AS db_user;
```

The three sessions must have **distinct backend PIDs** to test one session locking another. If your client tool shares one connection across tabs, results will be invalid because two real backends are not competing.

### 4.3. Set `application_name` for Easier Observation

In each test session, you can set:

```sql
SET application_name = 'lock-lab-A';
```

Replace `A` with `B` or `C` in the corresponding window. `application_name` makes `pg_stat_activity` easier to read, but **never replaces** checking PID, user, database, and backend start time.

In real systems, `application_name` is client-supplied and can be spoofed or misconfigured; never decide to terminate a session solely based on an application name string.

## 5. Basic Experiment: An `UPDATE` Holding Locks After the Statement Finishes

This is a controlled example creating a lock wait via a **row update**.

### 5.1. Session A Updates Without Committing

Ensure account 101 has a suitable balance.

**Session A:**

```sql
BEGIN;

UPDATE lock_ops_lab.accounts
SET balance = balance + 10.00
WHERE account_id = 101
RETURNING account_id, balance;

-- PAUSE here; do NOT COMMIT or ROLLBACK yet.
```

The `UPDATE` statement has completed in Session A, but transaction A has not ended.

### 5.2. Session B Attempts to Update the Same Row

**Session B:**

```sql
BEGIN;

SET LOCAL statement_timeout = '30s';

UPDATE lock_ops_lab.accounts
SET balance = balance + 20.00
WHERE account_id = 101
RETURNING account_id, balance;
```

While A has not released the lock, B's `UPDATE` will **wait**.

Session B will not necessarily see a "waiting on lock" message in the UI; the client may simply show the SQL query as still running.

### 5.3. Session C Observes

**Session C:**

```sql
SELECT
    a.pid,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.xact_start,
    clock_timestamp() - a.xact_start AS transaction_age,
    pg_blocking_pids(a.pid) AS blocking_pids
FROM pg_stat_activity AS a
WHERE a.application_name IN ('lock-lab-A', 'lock-lab-B')
ORDER BY a.pid;
```

Expected output while blocked:

- Session A shows `state = 'idle in transaction'` because its `UPDATE` finished but the transaction remains open.
- Session B shows `state = 'active'` and `wait_event_type = 'Lock'`.
- `pg_blocking_pids(B_PID)` contains A's PID.

### 5.4. Release from Session A

**Session A:**

```sql
ROLLBACK;
```

When transaction A rolls back, the `+10` change is discarded and transaction locks are released. Session B can proceed with its `UPDATE`, provided it has not timed out or been canceled.

Once B finishes, if you want to preserve the initial lab data:

**Session B:**

```sql
ROLLBACK;
```

Note: if B previously hit `statement_timeout`, transaction B will be in an aborted state; `ROLLBACK` is required then.

**Conclusion:** finishing A's `UPDATE` did not release the lock; **ending transaction A** is what released its transaction-scoped locks.

## 6. How Do `COMMIT` and `ROLLBACK` Release Locks?

### 6.1. `COMMIT`

When a transaction commits successfully:

- Changes are persisted according to transactional rules.
- Transaction-scoped locks are released.
- Other transactions can proceed once no incompatible blockers remain.

Example:

```sql
BEGIN;

SELECT account_id, balance
FROM lock_ops_lab.accounts
WHERE account_id = 101
FOR UPDATE;

COMMIT;
```

The row lock from `FOR UPDATE` no longer belongs to the transaction after `COMMIT`.

### 6.2. `ROLLBACK`

When rolling back:

- Uncommitted data changes in the transaction are discarded.
- Transaction-scoped locks are released.
- Other transactions can proceed or re-evaluate appropriate conditions.

```sql
BEGIN;

UPDATE lock_ops_lab.accounts
SET balance = balance - 10
WHERE account_id = 101;

ROLLBACK;
```

The balance returns to its pre-transaction value, unless other transactions independently committed changes.

### 6.3. Do Not Confuse "Rollback Transaction" with "Undo All External Effects"

Suppose an application:

1. Begins a PostgreSQL transaction.
2. Updates an order status.
3. Calls an external API to send an email.
4. Rolls back due to another error.

Uncommitted PostgreSQL data is rolled back; **the sent email is not recalled**. Terminating the backend while a transaction is interacting with an external system does not undo that side effect either.

When designing recovery for lock incidents, you must account for idempotency and side-effect coordination rather than looking solely at table state.

### 6.4. Never Use `COMMIT` to "Release Locks" When Business Logic Is Incomplete

A lock-holding transaction may be partway through a multi-step business workflow. Running `COMMIT` just to clear contention risks **persisting an incomplete or inconsistent state**.

Operators should ask the application owner to complete or roll back properly instead of forcing a commit on an unfamiliar transaction.

## 7. `SAVEPOINT` and Partial Lock Release

In PostgreSQL, rolling back to a savepoint can release locks **acquired after that savepoint**, subject to subtransaction rules.

### 7.1. Experiment with a Table Lock

```sql
BEGIN;

SAVEPOINT before_extra_lock;

LOCK TABLE lock_ops_lab.jobs
IN SHARE ROW EXCLUSIVE MODE;

ROLLBACK TO SAVEPOINT before_extra_lock;

-- The table lock acquired after the savepoint is undone
-- according to lock/subtransaction rules.

ROLLBACK;
```

Key takeaways:

- A savepoint is not an independent transaction that can commit permanently.
- Transaction-scoped locks acquired **before** a savepoint are not dropped when rolling back to the savepoint.
- Eligible locks acquired **after** a savepoint are generally released when rolling back to that savepoint.

### 7.2. Handling Errors with `ROLLBACK TO SAVEPOINT`

```sql
BEGIN;

SAVEPOINT try_step;

UPDATE lock_ops_lab.accounts
SET balance = -1
WHERE account_id = 101;
-- Violates CHECK (balance >= 0).

ROLLBACK TO SAVEPOINT try_step;

SELECT account_id, balance
FROM lock_ops_lab.accounts
WHERE account_id = 101;

ROLLBACK;
```

An error in an `UPDATE` statement does not have to abort the entire transaction if the application set a savepoint and handles `ROLLBACK TO SAVEPOINT` appropriately.

### 7.3. Critical Difference with Session Advisory Locks

`pg_advisory_lock(...)` is **session**-scoped, so rolling back a transaction or savepoint **is not a mechanism for releasing session-level locks**.

With `pg_advisory_xact_lock(...)`, the lock is transaction-scoped; rolling back to a savepoint interacts with subtransaction lock scope and the corresponding release rules.

**In production code**, avoid using savepoints as a tricky mechanism to manage advisory locks. When transaction ownership is needed, let the transaction manager control commit/rollback boundaries; when session-level locks are needed, implement explicit cleanup.

## 8. Advisory Locks: The Major Exception to "`ROLLBACK` Releases Locks"

There are two advisory lock scopes:

| Example | Scope | After `ROLLBACK`? |
| --- | --- | --- |
| `pg_advisory_lock(247, 1)` | Session | **Still held** unless explicitly unlocked by the session |
| `pg_advisory_lock_shared(247, 1)` | Session | **Still held** |
| `pg_advisory_xact_lock(247, 1)` | Transaction | **Released** when transaction ends |
| `pg_advisory_xact_lock_shared(247, 1)` | Transaction | **Released** when transaction ends |

### 8.1. Testing a Session-Level Lock

**Session A:**

```sql
SELECT pg_advisory_lock(247, 1);

BEGIN;

UPDATE lock_ops_lab.jobs
SET status = 'RUNNING'
WHERE job_id = 1;

ROLLBACK;
```

Even though the `UPDATE` rolled back, Session A **still holds** advisory lock `(247,1)`.

**Session B:**

```sql
SELECT pg_try_advisory_lock(247, 1) AS acquired;
-- false while A holds the exclusive lock on the same key.
```

**Session A unlocks:**

```sql
SELECT pg_advisory_unlock(247, 1) AS released;
-- true if A holds a corresponding lock count.
```

Then B can retry. If B receives `true` from `pg_try_advisory_lock`, B must also unlock:

```sql
SELECT pg_try_advisory_lock(247, 1) AS acquired;
SELECT pg_advisory_unlock(247, 1);
```

### 8.2. Session Locks Can Be Acquired Reentrantly

The same backend can acquire a session advisory key multiple times reentrantly. It must unlock as many times as it acquired:

```sql
SELECT pg_advisory_lock(247, 2);
SELECT pg_advisory_lock(247, 2);

SELECT pg_advisory_unlock(247, 2);
-- One lock count may still remain held.

SELECT pg_advisory_unlock(247, 2);
-- Releases the remaining count.
```

A single unlock call does not guarantee the key is completely free if the session acquired it multiple times.

### 8.3. `pg_advisory_unlock_all()`

```sql
SELECT pg_advisory_unlock_all();
```

This function releases **all session-level advisory locks held by the calling backend**. It is not a tool to arbitrarily release locks in another backend, and it **does not release transaction-level advisory locks**.

Never call `pg_advisory_unlock_all()` on a pooled connection without knowing what other components share that session, as doing so can break another library's lock invariants.

### 8.4. Transaction-Level Locks Fit Connection Pools Better

```sql
BEGIN;

SELECT pg_advisory_xact_lock(247, 3);

SELECT status
FROM lock_ops_lab.jobs
WHERE job_id = 1;

COMMIT;
```

Lock `(247,3)` is automatically released when the transaction commits. There is no `pg_advisory_xact_unlock` function to call.

**Remember:** in autocommit mode, a transaction-level advisory lock is acquired and immediately released as soon as the single statement finishes; to guard multiple SQL statements, open an explicit transaction.

## 9. What Does `pg_cancel_backend(pid)` Actually Do?

The function:

```sql
SELECT pg_cancel_backend(12345);
```

asks PostgreSQL to send a signal to **cancel the current query/statement** on the backend with that PID, subject to permissions.

Conceptually:

```text
Session B is running SELECT/UPDATE and waiting for a lock
            |
Session C calls pg_cancel_backend(B_PID)
            |
            v
Session B receives the cancel request
            |
            v
Current statement is canceled
            |
            +-- Explicit transaction may enter failed/aborted state
            |   requiring ROLLBACK
            |
            +-- Transaction does not disappear from cancel alone
            |
            +-- Session B stays alive for the application to continue handling
```

### 9.1. Core Takeaways

- **Cancel targets the currently executing statement**, not "release all locks held by the session."
- **The backend stays alive**; the connection is not closed merely by canceling.
- If the statement belonged to an explicit transaction, a cancel error puts the transaction into an aborted state; the client must `ROLLBACK` or handle a savepoint as designed.
- Transaction locks can remain held **until the transaction actually ends**.
- Held session-level advisory locks also survive cancellation.

### 9.2. A Boolean Return Does Not Mean Business Recovery

`pg_cancel_backend(pid)` returns a boolean indicating whether the signal request was sent. `true` **does not prove** that all locks were released, the transaction rolled back, or the blocker disappeared.

After canceling, you must **re-inspect** session states and the blocker list.

### 9.3. Canceling an Idle Backend Often Accomplishes Nothing

If Session A finished its `UPDATE` and is in state:

```text
idle in transaction
```

then there is **no currently executing query to cancel in the usual sense**. Calling `pg_cancel_backend(A_PID)` is not a reliable way to end A's uncommitted transaction.

The appropriate workflow is usually:

1. Ask the application/client owning the connection to **COMMIT or ROLLBACK** according to its logic.
2. If coordination is impossible, evaluate safety before resorting to **session termination** as a stronger measure.

Never treat a `true` return from `pg_cancel_backend` as proof that an idle session's locks are gone.

## 10. Experiment: Cancel the Waiter While the Blocker Keeps Holding the Lock

This is an important and relatively safe lab experiment.

### 10.1. Session A Holds a Row Lock

```sql
BEGIN;

UPDATE lock_ops_lab.accounts
SET balance = balance + 10
WHERE account_id = 101;

-- Keep transaction A open.
```

### 10.2. Session B Records Its PID and Begins Waiting

**Session B:**

```sql
SELECT pg_backend_pid() AS waiter_pid;
```

Record the PID returned by B, for example `34567`. This is **only an example**; never paste sample PIDs into production.

Continue:

```sql
BEGIN;

SET LOCAL statement_timeout = '60s';

UPDATE lock_ops_lab.accounts
SET balance = balance + 20
WHERE account_id = 101;
-- Will be blocked by A.
```

### 10.3. Session C Sends a Cancel Request to B

Before signaling, confirm B's PID in monitoring:

```sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE pid = 34567;
```

After confirming the exact **lab Session B PID**:

```sql
SELECT pg_cancel_backend(34567) AS signal_sent;
```

Replace `34567` with the real PID you recorded and verified. In the experiment, B receives an error:

```text
ERROR: canceling statement due to user request
SQLSTATE: 57014
```

### 10.4. Session B Cleans Up Its Failed Transaction

**Session B:**

```sql
ROLLBACK;
```

If B tries to run a normal `SELECT` before rolling back, it gets:

```text
ERROR: current transaction is aborted,
commands ignored until end of transaction block
SQLSTATE: 25P02
```

### 10.5. Session A Still Holds Its Lock

After C cancels B, A still holds an uncommitted transaction. You must end A:

```sql
ROLLBACK;
```

**Observation summary:**

- Canceling **B** aborted B's waiting `UPDATE`.
- It did **not** make A roll back automatically.
- A's row lock is released only when transaction A ends (or backend A is terminated via another mechanism).
- After B rolls back, B's lock wait disappears, yet transaction A can still block others.

## 11. How Does `pg_terminate_backend(pid)` Differ from `pg_cancel_backend(pid)`?

The function:

```sql
SELECT pg_terminate_backend(12345);
```

asks PostgreSQL to **terminate the backend/session** rather than merely canceling the running statement.

Typical effects:

- The client's connection is severed.
- Any uncommitted transaction in that session is rolled back as the backend exits.
- Transaction-level locks are released when the transaction/backend ends.
- Session-level advisory locks are also released when the session actually terminates.
- Previously committed transactions are **not undone** just because the session is terminated later.

### 11.1. Direct Comparison Table

| Criterion | `pg_cancel_backend` | `pg_terminate_backend` |
| --- | --- | --- |
| Target | Stop the **current statement** | End the **backend/session** |
| Connection stays open? | Typically **yes** | **No**, once the backend exits |
| Uncommitted transaction | Enters aborted state; still requires rollback | Rolled back when backend terminates |
| Transaction-level locks | Not guaranteed released immediately | Released when transaction/backend exits |
| Session-level advisory locks | Not automatically released | Released when session actually exits |
| Client impact | Statement error; client can recover via rollback | Connection lost error; client must reconnect |
| Business impact risk | Usually smaller, though still impactful | Larger; aborts all uncommitted work |
| Preferred situation | Long-running or waiting query needs statement stopped | Uncooperative session holding locks long-term must be ended |

### 11.2. What Does `true` from `pg_terminate_backend` Mean?

Depending on PostgreSQL version and signature:

```sql
SELECT pg_terminate_backend(12345);
```

with no timeout argument may return `true` merely when **the termination signal was sent successfully**, not as proof that the backend already finished exiting before the function returned.

PostgreSQL versions supporting a timeout parameter allow:

```sql
SELECT pg_terminate_backend(12345, 5000);
```

where the timeout is in **milliseconds**; the return value can reflect whether the backend actually terminated within that window. Always check the syntax for your **running PostgreSQL version**.

**After terminating, still verify** that the PID is gone or the session genuinely ended; never rely on a single `true` return.

### 11.3. Aborting a Transaction Is Not Canceling External Work

If backend A holds a lock while calling an external system (via application logic), terminating A rolls back uncommitted PostgreSQL changes; it **does not recall** messages already sent, emails dispatched, or external API side effects.

A client hitting a dropped connection may retry automatically. Without idempotent operations, retries can duplicate side effects.

## 12. Experiment: Terminating a Holder to Clear an Uncommitted Transaction

**This is a destructive session operation**; practice only on lab backends with disposable data.

### 12.1. Session A Starts a Transaction and Holds a Row Lock

```sql
SELECT pg_backend_pid() AS holder_pid;

BEGIN;

UPDATE lock_ops_lab.accounts
SET balance = balance + 10
WHERE account_id = 101;

-- Do not COMMIT or ROLLBACK.
```

### 12.2. Session B Starts Waiting

```sql
BEGIN;

SET LOCAL statement_timeout = '60s';

UPDATE lock_ops_lab.accounts
SET balance = balance + 20
WHERE account_id = 101;

-- Waiting on A while A holds the lock.
```

### 12.3. Session C Verifies and Terminates Holder A

The following is illustrative; replace the PID with the real lab value:

```sql
SELECT
    pid,
    application_name,
    state,
    xact_start,
    backend_start,
    query
FROM pg_stat_activity
WHERE pid = 23456;
```

After verifying it is indeed lab Session A:

```sql
SELECT pg_terminate_backend(23456) AS signal_sent;
```

Session A loses its connection when the backend terminates. A's uncommitted transaction is rolled back. Locks held by A are released during cleanup, allowing B to proceed if B has not yet timed out or been canceled.

### 12.4. Session B Finishes

If B completed successfully:

```sql
ROLLBACK;
```

Use `ROLLBACK` to leave the lab data unchanged.

If B timed out, roll back the failed transaction and retry from scratch in a new transaction if continuing experiments.

### 12.5. What You Cannot Conclude from This Experiment

Terminating A **does not mean** "every query in the database will stop waiting." Other blockers or unrelated locks may still exist.

Nor does it prove termination is always safe in production. In a multi-table transaction, rolling back can alter pending business outcomes, disrupt applications, and trigger retries.

## 13. When to Cancel a Waiter vs. Handle a Blocker?

Two roles are easily confused:

- **Waiter**: a session requesting a lock that cannot acquire it yet.
- **Blocker**: a session/transaction holding a lock or standing ahead in the queue preventing the waiter from acquiring it.

Diagram:

```text
Holder A ----------------> holds lock X
                              |
                              v
Waiter B ----------------> waits for lock X
                              |
                              v
Waiter C ----------------> may also wait behind B
```

### 13.1. Canceling Waiter B

Effect:

- B stops its waiting statement.
- Reduces the wait queue.
- Does not directly touch transaction A.
- Other waiters may still wait on A.

Appropriate when request B has already breached its SLA or the user canceled B's task.

### 13.2. Canceling Blocker A's Query

If A **is actively executing a long statement** and has not gone idle, canceling A's statement makes the statement fail. However, if A is inside an explicit transaction, you must confirm the client **rolls back** so transaction locks are actually released.

If A is already `idle in transaction`, there is generally no running statement to cancel.

### 13.3. Terminating Blocker A

Stronger effect:

- A's uncommitted transaction is rolled back when the backend exits.
- A's locks are released.
- B and C get a chance to proceed.
- The application owning A receives a connection loss error and must handle retry/recovery.

This is a **higher-risk intervention**, so perform it only after verifying the exact session, understanding the transaction involved, confirming operational authorization, and assessing business impact.

### 13.4. Fix Root Causes, Not Just Symptoms

If A frequently sits `idle in transaction` because the application forgets to `COMMIT`, terminating it once gives temporary relief. The incident will recur until transaction boundaries, timeouts, exception handling, or connection pool behavior are fixed.

## 14. Monitoring Query #1: Finding Waiting Sessions

PostgreSQL exposes `pg_stat_activity` for inspecting sessions/backends.

```sql
SELECT
    a.pid,
    a.datname,
    a.usename,
    a.application_name,
    a.client_addr,
    a.backend_start,
    a.state,
    a.xact_start,
    a.query_start,
    a.wait_event_type,
    a.wait_event,
    clock_timestamp() - a.query_start AS query_age,
    clock_timestamp() - a.xact_start AS transaction_age,
    pg_blocking_pids(a.pid) AS blocking_pids
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
ORDER BY a.xact_start NULLS LAST, a.pid;
```

Useful columns:

| Column | Question Answered |
| --- | --- |
| `pid` | Which backend? |
| `datname` | Which database? |
| `usename` | Which role? |
| `application_name` | What name did the client report? |
| `client_addr` | Connecting from which address, if any? |
| `backend_start` | When was the backend created? |
| `state` | Active, idle, idle in transaction, or another state? |
| `xact_start` | When did the open transaction begin? |
| `query_start` | When did the current or last recorded statement start? |
| `wait_event_type` / `wait_event` | What event type is the backend waiting on? |
| `pg_blocking_pids(pid)` | Which PIDs are blocking it according to the lock manager? |

### 14.1. `state = 'active'` Does Not Mean Burning CPU

A backend with `state = 'active'` and `wait_event_type = 'Lock'` is **waiting on a lock**, not computing.

A backend with `active` and `wait_event_type = 'IO'` may be waiting on I/O. Never kill a query just because it has been `active` for a long time; first check **what it is actually doing**.

### 14.2. Watch Out for `idle in transaction`

A backend in `idle in transaction` finished its last statement yet kept the transaction open, prolonging transaction-held locks.

The `query` column in `pg_stat_activity` then displays the **most recent statement**, not a currently executing one. Do not assume that text directly represents "the exact command holding every lock."

### 14.3. `idle in transaction (aborted)`

This state indicates a transaction errored out, yet the client **never rolled back or ended the transaction**. Some resources/locks can still persist until cleanup happens; inspect actual state and lock types instead of assuming every lock vanished.

Applications must roll back immediately after errors, never leaving aborted connections waiting on user input or returning them to a pool.

### 14.4. Do Not Pick Victims Using `query_age` Alone

A long-running query might be an approved backup, migration, or maintenance task. Meanwhile, a brand-new query might be blocking everyone because it requested a strong lock.

Combine:

- Dependency data from `pg_blocking_pids`.
- Transaction age from `xact_start`.
- Role / application / client.
- Workload type and business impact.
- Client retry and recovery behavior.

## 15. Using `pg_blocking_pids` to Identify Blockers

`pg_blocking_pids(pid)` returns an array of backend PIDs blocking a given backend according to PostgreSQL's lock manager. It is usually a better starting point than hand-joining `pg_locks` on complex lock conditions.

### 15.1. List Only Sessions That Have Blockers

```sql
SELECT
    a.pid AS waiting_pid,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blockers,
    a.query
FROM pg_stat_activity AS a
WHERE cardinality(pg_blocking_pids(a.pid)) > 0
ORDER BY a.pid;
```

Example output:

| waiting_pid | application_name | blockers |
| ---: | --- | --- |
| 34567 | order-api | {23456} |
| 34568 | invoice-api | {23456} |

This suggests backend 23456 is blocking two sessions; you **still need to inspect backend 23456 itself** before deciding to intervene.

### 15.2. Display Waiter and Blocker Details Side by Side

```sql
SELECT
    w.pid AS waiting_pid,
    w.application_name AS waiting_app,
    w.state AS waiting_state,
    w.query AS waiting_query,
    p.blocking_pid,
    b.application_name AS blocking_app,
    b.usename AS blocking_user,
    b.state AS blocking_state,
    b.xact_start AS blocking_xact_start,
    b.query AS blocking_last_query
FROM pg_stat_activity AS w
CROSS JOIN LATERAL
    unnest(pg_blocking_pids(w.pid)) AS p(blocking_pid)
LEFT JOIN pg_stat_activity AS b
    ON b.pid = p.blocking_pid
ORDER BY w.pid, p.blocking_pid;
```

Benefits:

- Eliminates guesswork from table names or SQL text alone.
- Shows when one blocker blocks **multiple waiters**.
- Reveals whether the blocker is `idle in transaction` or actively running.
- Identifies which application/role to contact for resolution.

### 15.3. A Blocker Can Also Be Waiting on Another Blocker

Example:

```text
Session C waits for B's lock
Session B waits for A's lock
Session A holds the lock and sits idle
```

Terminating only B might unblock B's queue entry while leaving C exposed to other issues; the root cause is A. Before acting, follow the `pg_blocking_pids` chain to find the **root blocker** and understand the full graph.

### 15.4. Soft Blockers and the Wait Queue

A PID can appear in `pg_blocking_pids` not only because it already holds a conflicting lock, but also because of its position/relationship in the lock manager's **wait queue**. Therefore, do not always interpret every returned PID as holding a granted lock.

Also examine `pg_locks.granted`, `wait_event`, and all related sessions.

### 15.5. Prepared Transactions May Lack a Normal PID

A prepared transaction can hold locks without any regular query backend running it. In such cases, blocker inspection can show special identifiers (for example, PID 0 representing a prepared transaction).

If no matching row exists in `pg_stat_activity`, **do not assume the blocker vanished**; check prepared transactions as covered later.

## 16. `pg_locks`: Inspecting Lock Types, Modes, and Grant Status

`pg_locks` exposes the lock manager's state.

```sql
SELECT
    l.pid,
    l.locktype,
    l.mode,
    l.granted,
    l.waitstart,
    l.database,
    l.relation,
    l.transactionid,
    l.virtualxid,
    l.classid,
    l.objid,
    l.objsubid
FROM pg_locks AS l
WHERE l.pid IN (
    SELECT pid
    FROM pg_stat_activity
    WHERE datname = current_database()
)
ORDER BY l.pid NULLS LAST, l.granted, l.locktype;
```

Key columns:

- `locktype`: type of locked object, such as `relation`, `transactionid`, `virtualxid`, `advisory`.
- `mode`: lock mode, e.g. `RowExclusiveLock`, `AccessExclusiveLock`, `ShareLock`, `ExclusiveLock`.
- `granted = true`: lock has been granted.
- `granted = false`: lock request is waiting.
- `waitstart`: timestamp when waiting began; may be NULL briefly or in special cases.
- Lock identifiers: `relation`, `transactionid`, `classid/objid/objsubid` depending on type.

### 16.1. Do Not Look Only for `locktype = 'tuple'`

When a transaction waits to update a row modified by another transaction, the wait often appears as a **transaction ID lock**, rather than a single persistent `tuple` row representing the blocked tuple.

PostgreSQL generally does not list every held row-level lock as individual rows in `pg_locks`.

Thus, if you see no `locktype = 'tuple'`, never conclude "there is no row lock contention."

### 16.2. Inspecting Locks Held by Your Current Session

```sql
SELECT
    pid,
    locktype,
    mode,
    granted,
    relation,
    transactionid
FROM pg_locks
WHERE pid = pg_backend_pid()
ORDER BY locktype, mode;
```

This query also shows locks held by the `SELECT` itself and catalog accesses, so not every row indicates a "lock leak."

### 16.3. Resolving Table Names for Relation Locks in the Current Database

```sql
SELECT
    l.pid,
    l.relation::regclass AS relation_name,
    l.mode,
    l.granted,
    l.waitstart
FROM pg_locks AS l
WHERE l.locktype = 'relation'
  AND l.database = (
      SELECT oid
      FROM pg_database
      WHERE datname = current_database()
  )
  AND l.relation IS NOT NULL
ORDER BY l.relation, l.pid;
```

Filtering by database ensures casting `relation` OID to `regclass` resolves meaningfully in the connected database.

### 16.4. `mode` Alone Does Not Tell You How to Release the Lock

An `AccessExclusiveLock` taken by `ALTER TABLE` inside a transaction is released when that transaction ends. An `ExclusiveLock` with `locktype='advisory'` might be session-scoped or transaction-scoped.

To determine lifecycle, you must know **how the lock was acquired**, its transaction/session ownership, and how the application behaves.

## 17. Identifying Table Locks and DDL Blocking Transactions

Not only `UPDATE` statements cause waits. Certain DDL operations require strong locks.

Lab example:

### 17.1. Session A Intentionally Holds a Table Lock

```sql
BEGIN;

LOCK TABLE lock_ops_lab.jobs
IN ACCESS EXCLUSIVE MODE;

-- Leave transaction open in the lab.
```

### 17.2. Session B Attempts a `SELECT`

```sql
BEGIN;

SET LOCAL lock_timeout = '3s';

SELECT COUNT(*) FROM lock_ops_lab.jobs;
```

`ACCESS EXCLUSIVE` conflicts with all other lock modes, including `ACCESS SHARE` required by ordinary `SELECT`s. Session B waits and then fails with `lock_timeout`.

### 17.3. End and Clean Up

**Session B:**

```sql
ROLLBACK;
```

**Session A:**

```sql
ROLLBACK;
```

Once A rolls back, the strong table lock is released.

### 17.4. Why DDL Needs an Explicit Locking Plan

A schema change may wait on a long read/write transaction. While DDL waits for a strong lock, newly arriving queries can queue up behind it and stall too.

For production migrations, consider:

- Exact lock mode of each DDL command.
- An appropriate `lock_timeout`.
- Maintenance windows and request traffic.
- Rollback/recovery capability.
- Any long-running open transactions.
- Online/concurrent strategies where supported.
- Retry plans instead of letting DDL hold the wait queue indefinitely.

Never run DDL capable of acquiring strong locks during peak traffic without understanding the consequences.

## 18. Timeouts Help Avoid Manual Intervention

A strong preventive measure is setting sensible limits **before an incident occurs**.

### 18.1. `lock_timeout`

```sql
BEGIN;

SET LOCAL lock_timeout = '2s';

UPDATE lock_ops_lab.accounts
SET balance = balance + 10
WHERE account_id = 101;

COMMIT;
```

If the statement waits for a lock longer than the configured threshold, PostgreSQL aborts the statement with a lock timeout error.

If inside an explicit transaction when a statement errors, the application must handle the transaction (typically `ROLLBACK`) instead of leaving the session aborted.

### 18.2. `statement_timeout`

```sql
BEGIN;

SET LOCAL statement_timeout = '5s';

SELECT COUNT(*) FROM lock_ops_lab.accounts;

COMMIT;
```

`statement_timeout` caps the execution duration of a **statement**, which includes lock wait time.

When both are set:

```sql
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '5s';
```

`lock_timeout` cuts off a lock-waiting statement sooner than `statement_timeout`.

Setting `lock_timeout` equal to or higher than `statement_timeout` rarely adds value because `statement_timeout` triggers first.

### 18.3. `idle_in_transaction_session_timeout`

```sql
SHOW idle_in_transaction_session_timeout;
```

This setting allows PostgreSQL to terminate a **session sitting idle in a transaction** for too long, reducing the risk of forgotten transactions holding locks/snapshots and blocking `VACUUM`.

Do not confuse it with `statement_timeout`:

- `statement_timeout` limits long-running statements.
- `idle_in_transaction_session_timeout` limits time spent **with no statement running** while a transaction stays open.
- Sessions not idle inside a transaction are unaffected by it.

### 18.4. `idle_session_timeout`

Some PostgreSQL versions also provide `idle_session_timeout` to close idle sessions outside transactions. With connection pools, evaluate this carefully because pools typically expect to keep physical connections open for reuse.

Do not set overly aggressive timeouts system-wide and dismiss unexpected client disconnections as harmless.

### 18.5. `SET LOCAL` Reduces Session-Level Setting Leaks

```sql
BEGIN;

SET LOCAL lock_timeout = '1s';
SET LOCAL statement_timeout = '5s';

-- Transaction-specific queries.

ROLLBACK;
```

`SET LOCAL` applies only for the current transaction, reverting afterward to the enclosing scope. This is usually safer than session-level `SET` when connections are reused by a pool and applications do not fully reset session state.

## 19. Distinguishing Cancel, Timeout, Deadlock, and Aborted Transaction Errors

Common errors:

| SQLSTATE | Typical Meaning | Response Strategy |
| --- | --- | --- |
| `57014` | `query_canceled`, including user cancel or statement timeout | Investigate cause, roll back failed transaction if any, evaluate retry |
| `55P03` | `lock_not_available`, e.g., `NOWAIT` or lock timeout | Check lock wait cause, retry/fail according to business logic |
| `40P01` | `deadlock_detected` | Roll back and consider retrying the entire transaction |
| `40001` | `serialization_failure` | Retry **the entire transaction** from the initial reads |
| `25P02` | `in_failed_sql_transaction` | Transaction already failed; roll back or roll back to a valid savepoint |
| `08006` | `connection_failure` | Connection failed; assess transaction state and ambiguous commit outcome |

### 19.1. A Cancel Is Not a Deadlock

If Session B waits on A and you run `pg_cancel_backend(B_PID)`, the resulting error is a cancellation—an explicit decision to stop a query.

If two transactions hold locks needed by each other in a cycle, PostgreSQL's deadlock detector intervenes and aborts one transaction with `40P01`.

The two situations call for different investigations:

- Operational cancel or timeout: why did the statement run or wait so long?
- Deadlock: why are transactions acquiring locks in inconsistent orders?

### 19.2. Do Not Blindly Retry Every Error

If a transaction is aborted mid-payment, a careless retry can duplicate payments, send two emails, or trigger external side effects twice.

Retry policies must account for SQLSTATE, business semantics, idempotency, and whether a commit outcome is known.

## 20. When a Query Is Canceled Inside a Transaction, Why Is `ROLLBACK` Required?

An explicit transaction might look like:

```sql
BEGIN;

UPDATE lock_ops_lab.accounts
SET balance = balance + 5
WHERE account_id = 202;

-- Next SQL statement gets canceled or times out.
SELECT pg_sleep(60);

-- Transaction has not ended yet.
```

If `pg_sleep(60)` is canceled, PostgreSQL marks the explicit transaction as failed. When the application next sends:

```sql
SELECT * FROM lock_ops_lab.accounts;
```

it receives:

```text
ERROR: current transaction is aborted,
commands ignored until end of transaction block
```

It must run:

```sql
ROLLBACK;
```

At that point, uncommitted changes in the transaction, including the earlier `+5`, are undone and transaction locks are released.

### 20.1. Why Not Just Cancel the `SELECT` and Move On?

Because the transaction remains open, which:

- Leaves the connection in an unhealthy state.
- Holds or affects transaction-tied resources.
- Blocks subsequent SQL statements on the same session.
- Keeps transaction age climbing in monitoring.
- Breaks the next request if a pool returns an unreset connection.

### 20.2. Savepoints in Application Code

If you intentionally set a savepoint, rolling back to it can recover a transaction after an optional step is canceled or errors out, provided:

- You never use it to silently skip a mandatory business step.
- You understand which locks existed before vs. after the savepoint.
- You deliberately decide whether continuing or rolling back completely is safer.

For critical multi-table operations, rolling back the whole transaction and performing a controlled retry is usually much easier to reason about than trying to salvage a transaction after an uncertain error.

## 21. `pg_terminate_backend` and Ambiguous Commit Outcomes

A tricky scenario:

```text
Application                    PostgreSQL
   |                               |
   | COMMIT ----------------------> |
   |                               | May have recorded the commit
   |  (connection lost here)        |
   X                               |
   | No response received           |
```

An application cannot infer solely from a connection error that a transaction **definitely did not commit**.

If the backend finished `COMMIT` just before being disconnected, the committed changes persist. If the backend was terminated before commit while the transaction was still open, uncommitted changes roll back.

### 21.1. Why Does This Matter Operations-Wise?

If an operator terminates a backend right around commit time, the client gets a connection error and may automatically resend the request.

If the request is "transfer 100.00" without an idempotency key, a blind retry can execute **two separate transfers**, even though each individual transaction is ACID.

### 21.2. Safe Design Pattern

For critical workflows:

1. Every business action carries a **stable request ID**.
2. The database records processing status keyed by request ID with a unique constraint.
3. On connection loss or ambiguous commit outcome, the application **queries/reconciles** before creating a new action.
4. Retries reuse the same request ID and verify payload consistency.
5. External side effects use idempotency or an outbox/fencing mechanism.

### 21.3. Never Treat Terminate as a Guaranteed Business Rollback API

`pg_terminate_backend` requests backend shutdown. It does not provide a "roll back all related business changes across services" protocol, nor does it let clients distinguish commit success from failure when a response is lost.

## 22. Principles for Safely Intervening on a PID

Before sending any signal, verify **at least**:

- The target PID matches the exact backend to act on.
- Database, role, application, and client match the incident.
- `backend_start` matches, avoiding PID reuse mistakes.
- Whether the backend is a normal client session or a special system process.
- `state`: active, idle, idle in transaction, aborted?
- `xact_start` and `query_start`.
- What the query is actually waiting on.
- `pg_blocking_pids` for waiters.
- What critical uncommitted transactions the blocker may hold.
- Impact on applications, connection pools, retries, and external systems.

### 22.1. Inspecting a Single PID

A **read-only** example (no signal sent):

```sql
SELECT
    pid,
    backend_start,
    backend_type,
    datname,
    usename,
    application_name,
    client_addr,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids,
    query
FROM pg_stat_activity
WHERE pid = 23456;
```

Replace `23456` with the PID gathered from monitoring; numbers in this lesson are illustrative.

### 22.2. Why Check `backend_start`?

OS PIDs can be **reused** after an old backend exits. A PID copied from an old snapshot may no longer belong to the same session by the time you run terminate.

Recheck PID + `backend_start` and owner details **right before acting**. This reduces the risk, even though a tiny race window between check and signal cannot be eliminated completely.

### 22.3. Avoid Broad Bulk Operations

Running a statement like this is very dangerous:

```sql
-- DO NOT RUN IN PRODUCTION:
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'active';
```

It can abort legitimate workloads, migrations, critical jobs, or backends essential for keeping the system healthy.

Even filtering by `state = 'idle in transaction'` is unsafe for bulk termination: valid transactions, prepared work, or specially coordinated sessions may be running.

### 22.4. Never Blindly Terminate System / Replication / Autovacuum Backends

`pg_stat_activity.backend_type` distinguishes client backends from other backend types. Accidentally terminating replication, autovacuum, or administrative processes can trigger consequences far worse than the original incident.

Act only on **specifically verified backends** within approved operational authority.

## 23. Privileges Required to Cancel or Terminate

Not every user with `SELECT` access can send signals to another backend.

In PostgreSQL, signaling permissions are governed by role membership and administrative privileges. Appropriately privileged roles—such as members of `pg_signal_backend` or superusers within allowed scope—can signal permitted backends.

Keep in mind:

- A normal user cannot arbitrarily terminate sessions owned by another role.
- `pg_signal_backend` does not allow terminating superuser backends without restriction.
- Exact permission rules depend on PostgreSQL version and backend type.
- Having `SELECT` on `pg_stat_activity` does not grant termination rights.

### 23.1. Do Not Grant Broad Terminate Privileges to Web Apps

An ordinary HTTP request should never be able to invoke `pg_terminate_backend` on arbitrary user-supplied PIDs.

For incident administration, use dedicated roles and workflows with:

- Authentication and authorization.
- Audit logs.
- Target verification.
- Scoped allowable targets.
- Escalation procedures for production impact.

### 23.2. Separate Monitoring Roles from Intervention Roles

A monitoring role may only need visibility into sessions within permitted bounds. Cancel/terminate privileges should be far more restricted.

Avoid storing superuser credentials in a service merely to cancel slow user queries.

## 24. Prepared Transactions: Locks Not Tied to a Live PID

This is an advanced but vital case when troubleshooting "I cannot find the blocker in `pg_stat_activity`."

PostgreSQL supports **two-phase commit (2PC)**, where a transaction can enter a prepared state:

```sql
PREPARE TRANSACTION 'some-gid';
```

Once prepared, the transaction continues holding its locks even though no active backend is directly executing it anymore.

### 24.1. Inspecting Prepared Transactions

```sql
SELECT
    gid,
    prepared,
    owner,
    database,
    transaction
FROM pg_prepared_xacts
ORDER BY prepared;
```

If a prepared transaction lingers in the system, it holds onto its locks and blocks other workloads.

### 24.2. No Regular PID to Simply Cancel or Terminate

A prepared transaction appears in the lock manager without being bound to a normal running client PID. Therefore:

- You cannot just find a PID in `pg_stat_activity` and cancel it.
- Do not assume `pg_locks.pid IS NULL` is a display glitch.
- Check whether the blocker is a prepared transaction.

### 24.3. Resolving 2PC Requires a Business Decision

The two commands:

```sql
COMMIT PREPARED 'some-gid';
ROLLBACK PREPARED 'some-gid';
```

**are not casual cleanup commands to try blindly.**

- `COMMIT PREPARED` commits the prepared transaction's changes.
- `ROLLBACK PREPARED` discards those changes.
- Under 2PC, the commit/rollback decision belongs to an external **transaction coordinator** alongside other participating resources.

An operator lacking full coordinator context must never arbitrarily commit or roll back just to clear a lock. Investigate the owner, GID, coordinator state, and cross-system consistency, and obtain the proper operational decision.

### 24.4. Do Not Enable 2PC Just to Lab-Test It

`max_prepared_transactions` can be `0` when a system does not use prepared transactions. Never alter settings or create prepared transactions in a shared environment just to test this section.

In production, a **lingering prepared transaction** requires dedicated inspection and 2PC handling, distinct from a stuck HTTP session.

## 25. Sample Lock-Wait Incident Runbook

A clear procedure avoids killing the wrong backend:

<escape>**Step 1. Confirm symptoms.**</escape>

- Which requests are slow or timing out?
- Do we see `wait_event_type = 'Lock'`?
- Are `55P03`, `57014`, or `40P01` errors occurring?
- How many users/jobs are impacted, and which SLAs are breaching?

<escape>**Step 2. Gather evidence before intervening.**</escape>

- `pg_stat_activity` for involved backends.
- `pg_blocking_pids` to map waiters and blockers.
- `pg_locks` with lock modes and `granted` flags.
- PID, database, user, application, `backend_start`, `xact_start`.
- Query text and connection owner if available.

<escape>**Step 3. Classify the blocker.**</escape>

- Actively running statement?
- `idle in transaction`?
- Session advisory lock?
- Prepared transaction?
- Planned DDL/migration?
- Deadlock cycle already resolved by PostgreSQL?

<escape>**Step 4. Choose the least destructive action.**</escape>

- If the waiting request was already canceled by the user, canceling the **waiter** may suffice.
- If the app owning the blocker transaction is alive, ask it to commit or roll back.
- If a transaction was leaked, fix/recover the client and consider timeouts.
- If the session is uncooperative and impact is severe, **consider terminating the verified backend** after risk assessment.
- If it is a prepared transaction, follow the 2PC procedure.
- If it is a live session advisory lock, prefer having the owner unlock it.

<escape>**Step 5. Verify the outcome.**</escape>

- Did lock waits drop?
- Did the intended backend exit?
- Did affected transactions roll back or commit as expected?
- How did the application retry or recover?
- Are new transactions/locks still blocking?

<escape>**Step 6. Remediate the root cause.**</escape>

- Transaction too long?
- Missing rollback on exception?
- Session advisory lock leak?
- Migration using an overly strong lock mode?
- Missing index prolonging lock hold times?
- Lock-ordering deadlock?
- Connection pool returning unreset connections?
- Retries lacking idempotency?

This runbook keeps interventions controlled instead of "killing all slow queries" while leaving the underlying bug intact.

## 26. When Should You NOT Cancel or Terminate?

### 26.1. A Query Is Just Slow, Not Waiting on Locks

If `wait_event_type` is not `Lock`, the query may be waiting on I/O, computing, streaming results to the client, or doing legitimate work.

Never treat every "query over 30 seconds" as a lock problem.

### 26.2. A User Transaction Is Near a Sensitive Commit Point

Terminating close to commit time leaves the client uncertain whether changes committed.

For payments, reconciliation, or ledger entries, understand idempotency and recovery flows before intervening.

### 26.3. Planned Backups, Migrations, or Maintenance

A backend with a long query may be part of an approved maintenance task. If it must stop, coordinate with the owner or deployment tooling that provides proper rollback and cleanup.

### 26.4. When You Do Not Understand the Lock Type

Seeing `pg_locks` with `locktype = 'transactionid'` is not enough on its own to deduce the exact blocking statement. Inspect the wait graph and full context.

If a prepared transaction is involved, you cannot resolve it by terminating a random PID.

### 26.5. Without Fresh Evidence of Session Ownership

A pooled connection may have been reassigned; a PID from an old log entry is not guaranteed to belong to the same request. Re-verify right at the moment of intervention.

## 27. Using `NOWAIT` and `SKIP LOCKED` to Avoid Unnecessary Waits

In some workflows, it is better **not to wait** at all rather than hanging and needing manual cancellation later.

### 27.1. `FOR UPDATE NOWAIT`

```sql
BEGIN;

SELECT account_id, balance
FROM lock_ops_lab.accounts
WHERE account_id = 101
FOR UPDATE NOWAIT;

ROLLBACK;
```

If the row holds an incompatible lock, PostgreSQL returns `lock_not_available` immediately instead of waiting.

The application must implement a clear policy when `NOWAIT` fails to acquire the lock.

### 27.2. `FOR UPDATE SKIP LOCKED`

Suitable for certain job queues:

```sql
BEGIN;

SELECT job_id, status
FROM lock_ops_lab.jobs
WHERE status = 'PENDING'
ORDER BY job_id
FOR UPDATE SKIP LOCKED
LIMIT 1;

ROLLBACK;
```

A worker skips rows locked by another worker and picks a different available row.

### 27.3. Do Not Use `SKIP LOCKED` Everywhere

If you need the sum of balances across **all accounts**, skipping locked accounts yields wrong totals.

`SKIP LOCKED` intentionally provides an incomplete view of candidate rows; it suits worker queues, not financial reports requiring complete rows.

### 27.4. Distinguishing `NOWAIT` from Timeouts and Signals

- `NOWAIT`: zero wait for the corresponding row lock.
- `lock_timeout`: permits a bounded wait.
- `pg_cancel_backend`: external signal to a running backend.
- `pg_terminate_backend`: kills the backend, stronger than cancel.

Designing controls directly into queries and application logic is almost always better than relying on signal-based firefighting.

## 28. Connection Pools: Why Leaked Transactions Block Subsequent Requests

A connection pool keeps physical PostgreSQL connections open for reuse. If application code does:

```text
getConnection()
setAutoCommit(false)
UPDATE ...
exception occurs
no rollback
return connection to pool
```

the connection can return to the pool with an unfinished or broken transaction, depending on the library/pool and usage.

Consequences:

- Another request borrowing that connection hits an aborted transaction.
- The backend retains unintended locks and resources.
- `pg_stat_activity` fills with `idle in transaction`.
- Other workloads queue behind locks left over from the earlier request.

### 28.1. Always Roll Back in Error Paths

Java/JDBC example:

```java
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class AccountService {
    private final DataSource dataSource;

    public AccountService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void applyChange() throws SQLException {
        try (Connection conn = dataSource.getConnection()) {
            conn.setAutoCommit(false);

            try {
                // PreparedStatements use this exact conn
                // and run the workflow within this transaction.
                executeBusinessStatements(conn);

                conn.commit();
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

    private void executeBusinessStatements(Connection conn)
            throws SQLException {
        try (var ps = conn.prepareStatement(
                "UPDATE lock_ops_lab.accounts " +
                "SET balance = balance + 1 " +
                "WHERE account_id = ?")) {
            ps.setInt(1, 101);
            int updated = ps.executeUpdate();
            if (updated != 1) {
                throw new SQLException(
                    "Exactly one account not found"
                );
            }
        }
    }
}
```

This example illustrates **transaction cleanup**. In production, align with your business logic and framework transaction management; never mix manual commits with a framework transaction manager on the same connection unless you understand its contract.

### 28.2. JDBC Cancellation vs. Backend Termination

`Statement.cancel()` in JDBC asks the driver to cancel an active statement using its supported protocol. `Connection.close()` on a pooled connection often **only returns the connection to the pool**, without disconnecting the physical backend right away.

Never treat client-side `close()` as proof that a PostgreSQL session and all session-level advisory locks vanished. Understand your pool/driver contracts and connection reset behavior.

### 28.3. JDBC Transaction Timeouts vs. Lock Timeouts

Frameworks often define their own transaction timeouts. However:

- An HTTP request timeout does not automatically cancel running SQL in PostgreSQL.
- A pool checkout timeout is not a server-side lock timeout.
- A framework transaction timeout may mark rollback-only or close connections depending on configuration.
- Protecting against lock waits still requires proper server-side timeouts and monitoring.

### 28.4. After `pg_terminate_backend`, the Pool Must Discard the Dead Connection

If an operator terminates a pooled backend, the driver receives a connection error. The pool must recognize the broken connection and supply a fresh one.

Never try to continue the old transaction after backend termination. Any retry must open a new transaction, re-read business state, and handle ambiguous commits if applicable.

## 29. Advisory Locks with Connection Pools and Transaction Pooling

### 29.1. Session Advisory Locks Are Not Bound to HTTP Requests

`pg_advisory_lock(...)` binds to the **physical backend**. Even after an HTTP request returns, if the pooled backend stays alive, the lock remains held.

Example:

```text
Request A borrows connection #7
A calls pg_advisory_lock(247,1001)
A hits an exception and forgets to unlock
Pool returns connection #7 to idle pool

Request B borrows connection #7
Backend still holds the session advisory lock
```

A single `ROLLBACK` does not fix this if the lock is session-scoped. Cleanup must explicitly unlock on that exact backend.

### 29.2. Transaction-Level Advisory Locks Have Clearer Lifecycles

```sql
BEGIN;

SELECT pg_advisory_xact_lock(247, 1001);

-- Database operations requiring exclusivity.

COMMIT;
```

When the transaction actually ends, the `xact` advisory lock is released automatically. This usually fits short pooled transactional workflows much better.

### 29.3. PgBouncer Transaction Pooling

Under transaction pooling, the same client flow can execute across **different PostgreSQL backends** in two consecutive transactions.

Thus, this pattern:

```text
Transaction 1: session lock acquired on backend A
Transaction 2: unlock runs on backend B
```

is unsafe. Backend B does not own A's session advisory lock.

Use transaction-level locks **within the same transaction** where supported by your pooling mode, or move coordination externally / adjust pooling configuration as needed.

### 29.4. Never Use Terminate to Bulk-"Flush a Pool"

If a pool leaks transactions or session locks, fix the root cause in the application or pool settings. Terminating every connection matching an `application_name` in production can sever healthy requests, trigger retry storms, and spike database load.

A controlled recovery may require draining traffic, rolling back or canceling per owner, verifying state, and only then terminating specific verified sessions.

## 30. Deadlocks: PostgreSQL Can Abort a Transaction Automatically

A deadlock is a cyclic lock wait:

```text
T1 holds row A ------> wants row B
    ^                      |
    |                      v
T2 wants row A <------ holds row B
```

PostgreSQL detects deadlocks and aborts one transaction to break the cycle, reporting:

```text
SQLSTATE 40P01: deadlock_detected
```

### 30.1. Two-Session Experiment

**Session A:**

```sql
BEGIN;

UPDATE lock_ops_lab.accounts
SET balance = balance + 1
WHERE account_id = 101;
```

**Session B:**

```sql
BEGIN;

UPDATE lock_ops_lab.accounts
SET balance = balance + 1
WHERE account_id = 202;
```

Then A attempts to update account 202 while B attempts to update account 101 in coordinated steps:

```sql
-- A:
UPDATE lock_ops_lab.accounts
SET balance = balance + 1
WHERE account_id = 202;

-- B:
UPDATE lock_ops_lab.accounts
SET balance = balance + 1
WHERE account_id = 101;
```

One of the two transactions hits a deadlock error. Finish or roll back any remaining transaction per your lab plan.

### 30.2. Why Operators Rarely Need to Terminate Both

PostgreSQL runs a deadlock detector. Upon finding a true wait cycle, it chooses one victim transaction so the other can proceed.

Operators should:

- Inspect logs and SQLSTATE codes.
- Check the order in which transactions acquire locks.
- Reduce lock hold durations.
- Add bounded whole-transaction retries for `40P01` where business-safe.
- Avoid mass interventions simply because a deadlock was already resolved.

### 30.3. `deadlock_timeout` Is Not a General Lock Wait Timeout

`deadlock_timeout` governs how long PostgreSQL waits before checking for deadlocks (and logging lock waits). It is **not** a cap on total lock wait duration like `lock_timeout`.

Do not set `deadlock_timeout` expecting every lock-waiting query to cancel after that interval.

## 31. Logging and Monitoring Lock Incidents

Settings worth knowing:

```sql
SHOW log_lock_waits;
SHOW deadlock_timeout;
SHOW lock_timeout;
SHOW statement_timeout;
SHOW idle_in_transaction_session_timeout;
```

### 31.1. `log_lock_waits`

When lock-wait logging is enabled and a wait exceeds the relevant threshold, PostgreSQL logs detailed lock-wait diagnostics for investigation.

This reveals:

- Which query waited.
- When and how long it waited.
- Which lock object and mode were involved.
- Blocker details depending on log configuration.

Avoid enabling overly verbose logging on busy systems without weighing disk volume, SQL query sensitivity, and operational overhead.

### 31.2. Finding Long Transactions

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    clock_timestamp() - xact_start AS age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

A long transaction is not necessarily blocking anyone right now, yet it is **worth watching**, especially if `idle in transaction` or holding old snapshots that hinder `VACUUM`.

### 31.3. Look Beyond Raw Lock Counts

A backend running a complex query may legitimately hold dozens of relation locks. Another backend holding **a single lock**—an `ACCESS EXCLUSIVE` lock on a hot table—can cause far greater disruption.

Evaluate lock mode, wait graph, duration, frequency, business criticality, and blast radius together.

### 31.4. Monitoring Snapshots Are Not Permanently Accurate

`pg_stat_activity` and `pg_locks` capture instantaneous state that can change moments later. Query text may also be truncated by `track_activity_query_size` or hidden by permissions.

Always collect evidence and re-verify immediately before intervening. Never base a terminate decision on an old screenshot.

## 32. Safe Operational Playbook by Impact Tier

There is no single "magic command" for every situation. Structure responses into tiers:

| Tier | Action | Risk |
| --- | --- | --- |
| 0 | Observe `pg_stat_activity` / `pg_locks` only | Low |
| 1 | Wait briefly, contact owner, ask client to end transaction | Usually low in managed workflows |
| 2 | Cancel **only the waiter statement** exceeding its SLA | Impacts only the canceled request |
| 3 | Ask owner to roll back the blocker transaction cleanly | Undoes uncommitted work |
| 4 | Cancel the blocker's active statement and verify rollback | Impacts blocker transaction |
| 5 | Terminate the verified blocker backend | Drops connection, rolls back uncommitted work, affects retries/side effects |
| Special | Handle a 2PC prepared transaction | Requires coordinator decision; distributed consistency risk |

**Never auto-escalate just because a command did not instantly change state.** For example, canceling an `idle in transaction` blocker is inherently ineffective; re-assess the root cause first.

### 32.1. After Terminating, Do Not Assume the Incident Is Over

Verify:

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE datname = current_database();
```

Check how many waiters remain blocked, whether the old backend truly exited, and whether the application immediately opened another blocking transaction.

### 32.2. Record an Audit Trail

For production incidents, record:

- Detection timestamp and business impact.
- Waiting PID, blocking PID, `backend_start`.
- Database, role, application.
- Lock type and mode.
- Pre-intervention evidence.
- Who or what process approved the action.
- Exact cancel/terminate command executed.
- Post-intervention outcome.
- Root-cause remediation plan.

This standard operational record separates deliberate actions from follow-on incidents.

## 33. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Immediately terminating slow queries | Kills valid work, triggers retries | Inspect wait events and blockers |
| Inspecting only waiters, ignoring blockers | Incident recurs while root blocker holds lock | Use `pg_blocking_pids` |
| Assuming canceling a waiter frees the blocker's lock | Other requests remain blocked | End or investigate the holder |
| Canceling `idle in transaction` to release locks | Transaction stays open | Request commit/rollback or consider terminate |
| Assuming `pg_cancel_backend` returning true freed locks | Only confirms signal delivery | Recheck `pg_locks`/`pg_stat_activity` |
| Assuming `pg_terminate_backend` returning true means session already exited | Signal may still be processing | Verify backend actually terminated |
| Terminating a PID from stale logs | PID may have been reused | Recheck PID + `backend_start` |
| Bulk-terminating all active backends | Disrupts valid workloads | Act only on verified PIDs |
| Relying solely on `application_name` | Names collide or are client-supplied | Verify database/user/`backend_start` |
| Assuming `state='active'` means high CPU | Might be waiting on Lock/IO | Check `wait_event_type` |
| Assuming every `idle in transaction` holds critical locks | May have low actual impact | Analyze wait graph and lock modes |
| Not rolling back after query cancellation | Transaction stays aborted holding resources | Roll back or use savepoints properly |
| Running `COMMIT` on unfinished work just to clear locks | Persists inconsistent business data | Ask owning workflow to commit/roll back properly |
| Thinking `ROLLBACK` releases session advisory locks | Session lock persists | Unlock on the owning backend |
| Assuming one unlock always clears an advisory lock | Lock may be reentrant | Balance acquire/unlock counts |
| Calling `pg_advisory_unlock_all` on shared connections | Releases locks owned by other code | Unlock only your specific keys |
| Expecting `pg_advisory_unlock` to release xact locks | Only affects session advisory locks | Commit or roll back the transaction |
| Using `pg_advisory_xact_lock` in standalone autocommit | Lock releases before subsequent work | Wrap critical section in one transaction |
| Expecting every row lock to show as `tuple` in `pg_locks` | Misses waits on `transactionid` | Inspect blocker graph across lock types |
| Over-simplifying manual `pg_locks` joins | Mismatches lock modes or IDs | Prefer `pg_blocking_pids` |
| Trying to terminate a prepared transaction via random PID | Misses 2PC ownership | Check `pg_prepared_xacts` and coordinator |
| Blindly running `ROLLBACK PREPARED` to clear locks | Breaks 2PC protocol consistency | Follow business/coordinator decision process |
| Treating `deadlock_timeout` as a lock timeout | Queries keep waiting indefinitely | Configure `lock_timeout` |
| Using `SKIP LOCKED` where full row coverage is required | Drops locked rows silently | Use only where skipping rows is valid |
| Retrying payment requests right after connection drop | Risks double execution | Use idempotency keys and reconciliation |
| Setting timeouts without JDBC cleanup | Pool keeps aborted transactions | Roll back and return clean connections |
| Not verifying state after canceling a query | Root cause persists | Re-observe, investigate, and fix |

## 34. Practice Exercises and Answers

Exercises below use `lock_ops_lab` unless operational knowledge is noted. Never run cancel/terminate outside a lab environment.

### Exercise 1. When Is a Row Lock from `UPDATE` Released?

**Answer:** normally when its owning transaction ends via `COMMIT` or `ROLLBACK`, not immediately when the `UPDATE` finishes if an explicit transaction remains open.

### Exercise 2. What Changes Between Autocommit and an Explicit Transaction?

**Answer:** under autocommit, each standalone statement finishes its own transaction; in an explicit transaction, transaction-scoped locks persist across multiple statements until commit or rollback.

### Exercise 3. How Can a Table Lock Inside a Transaction Be Released?

```sql
BEGIN;

LOCK TABLE lock_ops_lab.jobs
IN SHARE ROW EXCLUSIVE MODE;

ROLLBACK;
```

**Answer:** `ROLLBACK` ends the transaction and releases the table lock held by that transaction.

### Exercise 4. Does Canceling a Statement Automatically `COMMIT`?

**Answer:** no. Canceling stops the current statement; it never commits pending changes.

### Exercise 5. How Does `pg_cancel_backend` Differ from `pg_terminate_backend`?

**Answer:** cancel asks to abort the currently running statement while keeping the connection alive; terminate asks to end the entire session, closing the connection and rolling back uncommitted transactions when the backend exits.

### Exercise 6. Session B Waits on A. Does Canceling B Release A's Lock?

**Answer:** no. B stops waiting on the canceled statement, while A remains the lock holder until A's transaction/session ends or unlocks properly.

### Exercise 7. A Ran an `UPDATE` and Is Now `idle in transaction`. Does Canceling A Guarantee Releasing the Row Lock?

**Answer:** no. There is no active statement to cancel; transaction A must commit/roll back or its backend must terminate.

### Exercise 8. If `pg_cancel_backend(pid)` Returns `true`, Can We Conclude All Locks Are Released?

**Answer:** no. It does not guarantee the transaction has ended. Re-inspect `pg_stat_activity`, `pg_locks`, and blockers.

### Exercise 9. Does Terminating a Backend Roll Back Transactions Committed Yesterday?

**Answer:** no. It affects only the active session and its uncommitted transaction upon exit; previously committed transactions remain durable.

### Exercise 10. If a Client Loses Its Connection Right at `COMMIT`, Is Rollback Guaranteed?

**Answer:** no. `COMMIT` may have completed on the server before the response was lost; idempotency and reconciliation are required before business retries.

### Exercise 11. Find Your Own Connection's PID

```sql
SELECT pg_backend_pid();
```

**Answer:** returns the current PostgreSQL backend PID. Two independent connections must have distinct PIDs when testing contention.

### Exercise 12. Find Backends Waiting on Locks

```sql
SELECT
    pid,
    application_name,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE wait_event_type = 'Lock';
```

**Answer:** lists sessions waiting on `Lock`-class wait events at the time of observation.

### Exercise 13. Find Which PIDs Are Blocking a Waiter

```sql
SELECT pg_blocking_pids(34567);
```

**Answer:** replace `34567` with the real waiter PID; returns an array of blocker PIDs according to the lock manager.

### Exercise 14. Inspect Details of a Blocker

```sql
SELECT
    pid,
    backend_start,
    datname,
    usename,
    application_name,
    state,
    xact_start,
    query
FROM pg_stat_activity
WHERE pid = 23456;
```

**Answer:** verifies the target session before taking action; always recheck right before signaling.

### Exercise 15. Why Should You Check `backend_start`?

**Answer:** OS PIDs can be reused after an old backend exits. Combining PID with `backend_start` and owner details reduces the risk of signaling the wrong session.

### Exercise 16. What Does `pg_locks.granted = false` Indicate?

**Answer:** the lock request has not been granted yet, usually meaning the session is waiting; examine alongside `locktype`, `mode`, `waitstart`, and the blocker graph.

### Exercise 17. Why Aren't Row-Level Locks Always Shown in `pg_locks`?

**Answer:** PostgreSQL does not expose all granted row locks as readable `tuple` rows. A waiter often shows a wait on the modifying transaction's `transactionid`.

### Exercise 18. What Is the SQLSTATE When a Statement Is Canceled by User Request?

**Answer:** usually `57014` (`query_canceled`).

### Exercise 19. What Is the SQLSTATE When Running a `SELECT` After a Transaction Error?

**Answer:** `25P02` (`in_failed_sql_transaction`). Roll back or roll back to a valid savepoint.

### Exercise 20. What Is the SQLSTATE for a Deadlock?

**Answer:** `40P01`. PostgreSQL aborts one transaction to break the cycle; applications usually roll back and retry the entire transaction when business-safe.

### Exercise 21. What Is the SQLSTATE for Lock Timeout or `NOWAIT` Failure?

**Answer:** usually `55P03` (`lock_not_available`), to be handled per SLA and business rules.

### Exercise 22. Does a Session Advisory Lock Auto-Release on `ROLLBACK`?

```sql
SELECT pg_advisory_lock(247, 11);

BEGIN;
SELECT 1;
ROLLBACK;
```

**Answer:** no. Within the same owning session, you must call:

```sql
SELECT pg_advisory_unlock(247, 11);
```

### Exercise 23. Does a Transaction Advisory Lock Auto-Release on `COMMIT`?

```sql
BEGIN;

SELECT pg_advisory_xact_lock(247, 12);

COMMIT;
```

**Answer:** yes. No `pg_advisory_xact_unlock` call is needed.

### Exercise 24. Does `pg_advisory_unlock_all()` Release Another Backend's Session Locks?

**Answer:** no. It applies only to session-level advisory locks held by the calling backend, and can be dangerous if other libraries on that backend also use advisory locks.

### Exercise 25. Why Might One `pg_advisory_unlock` Not Fully Free the Lock?

**Answer:** the session can acquire the same key multiple times reentrantly; each unlock releases only one acquisition level.

### Exercise 26. When Rolling Back to a Savepoint, Are All Transaction Locks Always Lost?

**Answer:** no. Locks acquired before the savepoint remain held by the parent transaction; eligible locks acquired after the savepoint are released upon rollback to that point.

### Exercise 27. How Does `lock_timeout` Differ from `statement_timeout`?

**Answer:** `lock_timeout` caps lock wait duration, whereas `statement_timeout` caps total statement execution time (including lock wait). They are distinct settings.

### Exercise 28. What Does `idle_in_transaction_session_timeout` Help Prevent?

**Answer:** it terminates sessions idling inside transactions for too long, curbing forgotten transactions that hold locks/snapshots and hinder `VACUUM`; tune carefully for apps and pools.

### Exercise 29. Is `deadlock_timeout` a Timeout for Canceling All Lock Waits?

**Answer:** no. It controls deadlock detection delay and lock-wait logging; to cap lock waits, use `lock_timeout` or another appropriate mechanism.

### Exercise 30. When Should You Use `FOR UPDATE NOWAIT`?

**Answer:** when the application needs to know immediately if a row is locked and prefers failing fast ("busy") over waiting. Handle the failure explicitly in business logic.

### Exercise 31. When Is `SKIP LOCKED` Appropriate?

**Answer:** in worker queues where skipping rows locked by other workers to pick other available tasks is valid. Unsuitable when full row coverage is mandatory.

### Exercise 32. What Are Common Causes of Long `idle in transaction` Sessions?

**Answer:** applications opening transactions and forgetting to commit/roll back, holding connections during user input or external API calls, or failing to roll back/clean up in exception handlers.

### Exercise 33. Why Shouldn't You Assume Calling `Connection.close()` Kills the PostgreSQL Session?

**Answer:** with connection pooling, `close()` often just returns the physical connection to the pool. Verify how your pool resets transactions and whether session-level locks are cleared.

### Exercise 34. How Should You Handle a Prepared Transaction Holding Locks Without a Regular PID?

**Answer:** inspect `pg_prepared_xacts` and the transaction coordinator. Never send `pg_terminate_backend` to random PIDs; only execute `COMMIT PREPARED`/`ROLLBACK PREPARED` via verified 2PC procedures.

### Exercise 35. Should You Automatically Terminate Every `idle in transaction` Over 60 Seconds?

**Answer:** not blindly. Classify workloads, SLAs, owners, and business impacts, and consider server-side timeouts after evaluation—while still fixing the underlying transaction-boundary bugs.

### Exercise 36. Why Is Canceling a Waiter Usually Less Destructive Than Terminating a Blocker?

**Answer:** canceling a waiter only aborts one waiting request; terminating a blocker drops another connection and rolls back uncommitted work that may belong to a critical workflow. Always assess actual impact per incident.

### Exercise 37. If B Is Canceled While A Still Holds the Lock, Is the Incident Resolved?

**Answer:** no. Check remaining waiters, resolve A with its owner, and fix why A held the lock too long.

### Exercise 38. Why Shouldn't You Blindly Retry Payments After Terminating a Backend?

**Answer:** if disconnected around `COMMIT`, the client may not know whether the transaction committed. Retrying without idempotency can charge twice.

### Exercise 39. Why Trace the Root Blocker Instead of Looking at Just One Waiting Query?

**Answer:** multiple waiters can block behind one holder or form a chain. Removing one waiter leaves the root blocking transaction untouched.

### Exercise 40. Outline the Handling Order for a Production Lock-Wait Incident

**Suggested answer:**

1. Confirm symptoms and impact.
2. Collect `pg_stat_activity`, `pg_locks`, and `pg_blocking_pids`.
3. Verify exact PID, `backend_start`, role/application, and transaction state.
4. Identify waiters, blockers, root blocker, and lock types.
5. Contact owner / prefer clean waiting or rollback where appropriate.
6. Cancel the specific target statement when appropriate.
7. Terminate only a verified backend after risk assessment when necessary.
8. Re-verify the lock graph, handle ambiguous commits/retries, and fix the root cause.

## 35. Safe Intervention Checklist

| Question | What to Verify |
| --- | --- |
| Is this genuinely a lock wait? | `wait_event_type` / `pg_blocking_pids` |
| Which backend is waiting? | Waiting PID, query, SLA |
| Which backend is blocking? | Blocker / root blocker |
| Is the PID still the same session? | `backend_start`, role, database, app |
| Is the blocker executing a statement? | `state` and `wait_event` |
| Is it `idle in transaction`? | Client must commit or roll back |
| Is there an uncleaned aborted transaction? | Rollback / savepoint |
| What kind of lock is held? | Relation / transactionid / advisory / ... |
| What lifecycle governs the lock? | Transaction vs. session |
| Is a session advisory lock leaked? | Unlock on owning backend |
| Is a prepared transaction involved? | `pg_prepared_xacts` / coordinator |
| Whom will `CANCEL` affect? | Target statement |
| Will cancel release the locks? | Usually not if transaction stays open |
| What will `TERMINATE` roll back? | Uncommitted transaction and app work |
| Do you have proper signal scope/privileges? | Role / permissions |
| Is it a system backend? | `backend_type` |
| Might a transaction have committed unbeknownst to client? | Idempotency / reconciliation |
| Are external side effects involved? | Email / API / broker |
| Can timeouts replace manual signals? | `lock_timeout` / `statement_timeout` |
| Should `NOWAIT`/`SKIP LOCKED` be used? | Business semantics |
| Is the transaction held open across HTTP/UI? | Shrink transaction scope |
| Is it a deadlock? | SQLSTATE `40P01`, lock ordering |
| Is there a multi-hop lock chain? | Trace `pg_blocking_pids` |
| Is a migration running? | Coordinate with change owner |
| Are multiple waiters blocked by one blocker? | Assess blast radius |
| Did recovery succeed afterward? | Recheck backends / lock waits |
| Are actions logged and audited? | Record reason, action, outcome |
| Is there a connection pool bug? | Rollback/reset cleanup |
| Is a design fix needed? | Constraints, isolation, indexes, transactions |
| Were two concurrent sessions tested post-fix? | Verify non-recurrence |

## 36. Summary

**Releasing locks, canceling queries, and terminating sessions are three distinct operations** in PostgreSQL:

1. Row/table locks and transaction advisory locks are normally released when **the transaction ends** via `COMMIT` or `ROLLBACK`.
2. **Session-level advisory locks** survive commit and rollback and require explicit `pg_advisory_unlock`, `pg_advisory_unlock_all()` on the owning session, or session termination.
3. **`pg_cancel_backend(pid)`** only requests canceling the **current statement**; it does not guarantee the transaction rolled back or locks vanished.
4. **`pg_terminate_backend(pid)`** terminates the **backend/session**, closing the connection and rolling back uncommitted transactions upon exit. Its blast radius is wider than cancel.
5. **`idle in transaction`** is a red flag: the last statement finished, yet the transaction still holds locks/snapshots. Statement cancellation rarely fixes it.
6. **`pg_blocking_pids`** reveals who blocks whom. Combine it with `pg_stat_activity`, `pg_locks`, and ownership checks to understand the full picture.
7. **Canceling a waiter differs from handling a blocker.** Canceling a waiter trims queued requests without resolving a holder blocking everyone else.
8. **SQLSTATE `57014`/`55P03`/`40P01`/`40001`/`25P02`** signify distinct failures; handle transaction cleanup and retries accordingly.
9. **`lock_timeout`, `statement_timeout`, and `idle_in_transaction_session_timeout`** enforce self-healing bounds, though they never replace proper transaction and pool design.
10. **Prepared transactions** can hold locks with no regular backend PID; handle them under 2PC protocols, never by blindly terminating PIDs.
11. **Re-inspect after signaling**: returning `true` does not prove the session exited or locks were released.
12. **Prefer the least destructive path**, verify PID + `backend_start`, understand business impact, and use terminate only when necessary and authorized.

A memorable trio of diagnostic queries:

```sql
-- 1. Who is waiting and who is blocking?
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE datname = current_database();

-- 2. What locks are held and what locks are waiting?
SELECT pid, locktype, mode, granted, waitstart
FROM pg_locks
WHERE locktype IN ('relation', 'transactionid', 'advisory');

-- 3. Is the target backend really the session to intervene on?
SELECT
    pid,
    backend_start,
    backend_type,
    datname,
    usename,
    application_name,
    state,
    xact_start,
    query
FROM pg_stat_activity
WHERE pid = 23456;
```

The third query uses a **sample** PID; in practice, substitute the freshly verified PID and never act on stale monitoring data.

**Core rule:** before running `pg_cancel_backend` or `pg_terminate_backend`, answer: **who is waiting on whom, are the locks transaction- or session-scoped, and what data or workflow will abort if we intervene?** Until you know those answers, **observe and verify first** rather than escalating destructiveness.
