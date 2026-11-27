# Concurrency Testing with Multiple Connections and Controlled Schedules

Concurrency testing checks what happens when multiple transactions simultaneously read or modify data in PostgreSQL. A concurrency bug rarely appears when running individual statements sequentially: it surfaces only when operations interleave in a specific order. Therefore, a good test must control when each connection begins, reads, writes, waits for locks, and commits.

The goal of a solid test is to reproduce the execution schedule, observe intermediate states, and assert either the final outcome or the error PostgreSQL must return. This lesson uses two primary connections, denoted **A** and **B**, plus an observer connection **M** when needed.

## 1. Mechanisms to Understand Before Testing

Each PostgreSQL connection has its own backend process. Two concurrent connections can run two independent transactions, each with its own data snapshot and lock state. Opening two **psql** terminals, or checking out two distinct connections from a connection pool, is a simple way to simulate two concurrent users.

PostgreSQL uses MVCC (Multi-Version Concurrency Control). When a transaction updates a row, PostgreSQL creates a new row version; another transaction may still see the old version depending on its isolation level and when its snapshot was taken. This mechanism lets many read and write queries proceed concurrently without locking every read operation.

The isolation level governs how a transaction sees changes made by other transactions:

| Isolation level | Key observable behavior in PostgreSQL |
|---|---|
| **READ COMMITTED** | Default level. Each ordinary statement takes a new snapshot; two reads in the same transaction can see different committed states. |
| **REPEATABLE READ** | Statements within a transaction share the same snapshot. Changes committed after the snapshot begins are not visible. PostgreSQL also prevents phantom reads at this level, though serialization anomalies can still occur. |
| **SERIALIZABLE** | Guarantees outcomes equivalent to some serial execution order. PostgreSQL uses Serializable Snapshot Isolation (SSI) and may abort a transaction with a serialization error to preserve correctness. |

In PostgreSQL, **READ UNCOMMITTED** behaves identically to **READ COMMITTED**; there are no dirty reads in the sense of one transaction reading another transaction's uncommitted data.

MVCC does not eliminate the need for locks. **UPDATE**, **DELETE**, and **SELECT ... FOR UPDATE** can acquire row locks. When two transactions require conflicting locks on the same row, one must wait for the other to finish. An ordinary **SELECT** generally does not block an **UPDATE** on the same row, though it still acquires appropriate table-level locks to protect table structure.

Phenomena to include in your test suite:

- **Lost update:** two transactions read the same value and then write back a value computed from the stale read, causing one update to be overwritten.
- **Non-repeatable read:** a single transaction reads the same row twice and gets two different values.
- **Write skew:** two transactions read the same business condition and update different rows; each update is valid individually, but the combined outcome violates an invariant.
- **Lock wait:** one transaction waits for a row lock or table lock held by another transaction.
- **Deadlock:** transactions wait for each other's locks in a cycle; PostgreSQL must abort one transaction to break the cycle.

## 2. Preparing the Environment and Two Independent Connections

Run examples in a test database or dedicated schema. Never use data serving real users. Create explicit input data so every run can reset the database to the exact same state.

Example creating test tables:

~~~sql
CREATE SCHEMA concurrency_lab;

CREATE TABLE concurrency_lab.counter (
    id      integer PRIMARY KEY,
    value   integer NOT NULL
);

INSERT INTO concurrency_lab.counter (id, value)
VALUES (1, 10);

CREATE TABLE concurrency_lab.lock_demo (
    id      integer PRIMARY KEY,
    note    text NOT NULL
);

INSERT INTO concurrency_lab.lock_demo (id, note)
VALUES (1, 'initial');

CREATE TABLE concurrency_lab.accounts (
    id          integer PRIMARY KEY,
    balance     numeric(12, 2) NOT NULL
);

INSERT INTO concurrency_lab.accounts (id, balance)
VALUES (1, 1000.00), (2, 1000.00);

CREATE TABLE concurrency_lab.on_call (
    doctor_id   integer PRIMARY KEY,
    on_call     boolean NOT NULL
);

INSERT INTO concurrency_lab.on_call (doctor_id, on_call)
VALUES (1, true), (2, true);
~~~

When re-running examples, restore the data before each scenario. For example:

~~~sql
UPDATE concurrency_lab.counter SET value = 10 WHERE id = 1;
UPDATE concurrency_lab.lock_demo SET note = 'initial' WHERE id = 1;
UPDATE concurrency_lab.accounts SET balance = 1000.00;
UPDATE concurrency_lab.on_call SET on_call = true;
~~~

Open two **psql** terminals pointing to the same database. Set an application name to distinguish connections when inspecting **pg_stat_activity**:

~~~sql
-- Run on connection A
SET application_name = 'concurrency-test-A';
SELECT pg_backend_pid();

-- Run on connection B
SET application_name = 'concurrency-test-B';
SELECT pg_backend_pid();
~~~

The two **pg_backend_pid()** values must differ. When writing application-level tests, hold both connections checked out from the pool simultaneously and verify distinct PIDs. Checking out sequentially and returning each connection to the pool may accidentally reuse the same backend and fail to create true concurrency.

Each scenario needs four parts: initial state, A/B operation schedule, expected outcome, and data reset step. Document the isolation level and transaction boundaries explicitly. Never rely on random test-suite execution order to trigger a specific concurrency scenario.

## 3. Testing Lost Updates

Suppose a counter starts at **10**. Two users read this value concurrently, each intending to decrement it by one. If the application computes the result client-side and writes a constant back to the database, the later write can overwrite the earlier one.

Reset the data:

~~~sql
UPDATE concurrency_lab.counter SET value = 10 WHERE id = 1;
~~~

Execute the following schedule under **READ COMMITTED**:

| Step | Connection A | Connection B |
|---|---|---|
| 1 | **BEGIN;** | |
| 2 | | **BEGIN;** |
| 3 | **SELECT value FROM concurrency_lab.counter WHERE id = 1;** → **10** | |
| 4 | | **SELECT value FROM concurrency_lab.counter WHERE id = 1;** → **10** |
| 5 | **UPDATE concurrency_lab.counter SET value = 9 WHERE id = 1;** | |
| 6 | **COMMIT;** | |
| 7 | | **UPDATE concurrency_lab.counter SET value = 9 WHERE id = 1;** |
| 8 | | **COMMIT;** |

Check the result:

~~~sql
SELECT value
FROM concurrency_lab.counter
WHERE id = 1;
~~~

The result is **9**, whereas two independent decrements should yield **8**. B's write overwrote A's result. This is an application-level lost update: B used the stale value it had read earlier.

**First fix: perform the arithmetic directly inside the UPDATE statement.**

~~~sql
UPDATE concurrency_lab.counter
SET value = value - 1
WHERE id = 1;
~~~

Run this statement once per transaction. PostgreSQL serializes conflicting updates on the same row; each statement applies the subtraction to the current row version after acquiring the lock. Two updates will produce a final value of **8**.

If there is a business condition, include it in the same statement and check the updated row count:

~~~sql
UPDATE concurrency_lab.counter
SET value = value - 1
WHERE id = 1
  AND value > 0
RETURNING value;
~~~

Zero returned rows means either the condition was not satisfied or the row does not exist. The application must handle that case instead of assuming the operation succeeded.

**Second fix: lock the row before reading and computing.**

~~~sql
BEGIN;

SELECT value
FROM concurrency_lab.counter
WHERE id = 1
FOR UPDATE;

-- Calculate based on the value just read and update within the same transaction.
UPDATE concurrency_lab.counter
SET value = value - 1
WHERE id = 1;

COMMIT;
~~~

If A has locked the row, B waits at **SELECT ... FOR UPDATE**. Once A commits, B acquires the lock and reads the latest version of the row. This approach is useful when business logic must read multiple fields or apply complex calculations before updating. Keep transactions short so other connections are not blocked for long.

## 4. Testing Lock Waits and Timeouts

This scenario confirms that one transaction blocks when another transaction holds a row lock.

Reset the test row:

~~~sql
UPDATE concurrency_lab.lock_demo
SET note = 'initial'
WHERE id = 1;
~~~

**Connection A** acquires the lock:

~~~sql
BEGIN;

SELECT *
FROM concurrency_lab.lock_demo
WHERE id = 1
FOR UPDATE;
~~~

Keep transaction A open. **Connection B** tries to update the same row:

~~~sql
BEGIN;

UPDATE concurrency_lab.lock_demo
SET note = 'updated by B'
WHERE id = 1;
~~~

B's **UPDATE** waits. Meanwhile, open **connection M** to observe:

~~~sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids,
    query
FROM pg_stat_activity
WHERE datname = current_database()
  AND application_name LIKE 'concurrency-test-%';
~~~

While B is waiting on the lock, **wait_event_type** is typically **Lock**, and **pg_blocking_pids(pid)** returns the PID of the connection blocking B. The exact value of **wait_event** depends on the lock type and PostgreSQL version.

Switch back to A and commit:

~~~sql
COMMIT;
~~~

B resumes execution. Then commit B:

~~~sql
COMMIT;
~~~

Check the new value:

~~~sql
SELECT note
FROM concurrency_lab.lock_demo
WHERE id = 1;
~~~

You can test timeouts using **lock_timeout**. Set a limit in transaction B:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '500ms';

UPDATE concurrency_lab.lock_demo
SET note = 'timeout test'
WHERE id = 1;
~~~

If A holds the lock longer than allowed, PostgreSQL aborts B's statement with a lock timeout error. Transaction B is now in an aborted state; you must run **ROLLBACK** before reusing the connection:

~~~sql
ROLLBACK;
~~~

**lock_timeout** limits how long each lock acquisition attempt waits. **statement_timeout** limits the total execution time of a statement. The two settings address different concerns. **SET LOCAL** takes effect only for the current transaction and automatically expires when the transaction ends.

## 5. Testing Deadlocks with Opposite Lock Ordering

A deadlock occurs when A holds a lock that B needs while B holds a lock that A needs. PostgreSQL detects the wait cycle and aborts one transaction so the remaining transaction can proceed.

Reset both accounts:

~~~sql
UPDATE concurrency_lab.accounts
SET balance = 1000.00;
~~~

Execute the following steps in order, keeping transactions open between steps:

| Step | Connection A | Connection B |
|---|---|---|
| 1 | **BEGIN;** | |
| 2 | | **BEGIN;** |
| 3 | Update row **id = 1** | |
| 4 | | Update row **id = 2** |
| 5 | Update row **id = 2** and wait on B | |
| 6 | | Update row **id = 1**, creating a cycle |

Update statements on each connection:

~~~sql
-- Connection A: run step 3, then step 5
UPDATE concurrency_lab.accounts
SET balance = balance - 10
WHERE id = 1;

UPDATE concurrency_lab.accounts
SET balance = balance - 10
WHERE id = 2;

-- Connection B: run step 4, then step 6
UPDATE concurrency_lab.accounts
SET balance = balance - 10
WHERE id = 2;

UPDATE concurrency_lab.accounts
SET balance = balance - 10
WHERE id = 1;
~~~

Once the wait cycle forms, PostgreSQL detects the deadlock and returns SQLSTATE **40P01** to one of the two transactions. The chosen victim transaction enters an aborted state and must **ROLLBACK**. The surviving transaction can proceed once the locks are released and then commit.

Do not assert that A or B will always be the aborted transaction. Victim selection depends on actual runtime state when PostgreSQL runs deadlock detection. Tests should verify that one transaction receives **40P01**, the cycle clears, and final data satisfies invariants.

**Common prevention technique:** every code path updating multiple rows should acquire locks in the same consistent order. For example, if an operation needs to lock two accounts, always lock the smaller **id** first and then the larger **id**. Consistent ordering reduces deadlock risk. Applications should still implement full-transaction retry logic for retryable errors rather than retrying only the final statement.

## 6. Comparing READ COMMITTED and REPEATABLE READ

The non-repeatable read scenario verifies whether snapshots are taken per statement or held for the entire transaction.

Reset the data:

~~~sql
UPDATE concurrency_lab.counter
SET value = 100
WHERE id = 1;
~~~

**On connection A**, start a **READ COMMITTED** transaction and read the first time:

~~~sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT value
FROM concurrency_lab.counter
WHERE id = 1;
~~~

The result is **100**. While A's transaction remains open, **connection B** updates and commits:

~~~sql
BEGIN;

UPDATE concurrency_lab.counter
SET value = 120
WHERE id = 1;

COMMIT;
~~~

A reads again:

~~~sql
SELECT value
FROM concurrency_lab.counter
WHERE id = 1;
~~~

A receives **120**, because the second **SELECT** under **READ COMMITTED** takes a new snapshot and sees B's committed change. Finish A:

~~~sql
COMMIT;
~~~

Repeat the exact same schedule, changing transaction A to **REPEATABLE READ**:

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT value
FROM concurrency_lab.counter
WHERE id = 1;
~~~

After B updates and commits, the next **SELECT** in A still sees the value from its initial snapshot. That is the expected behavior of **REPEATABLE READ**.

If A attempts to update the exact row that B modified after A's snapshot was established, PostgreSQL may abort transaction A with a serialization error (**40001**, usually accompanied by a concurrent update message). The application must roll back and retry the entire transaction with a new snapshot if business rules permit.

Do not assume **REPEATABLE READ** guarantees all concurrent transactions are equivalent to a serial execution order. PostgreSQL uses snapshot isolation at this level; certain serialization anomalies can still happen. The write skew scenario below illustrates that limitation.

## 7. Testing Write Skew and SERIALIZABLE

Suppose two doctors are on call. The business rule requires at least one doctor to remain on call at all times. Each transaction checks how many doctors are on call and then takes one doctor off call. Two transactions can read the same valid state and update two different rows, causing the final outcome to violate the rule.

Reset the data:

~~~sql
UPDATE concurrency_lab.on_call
SET on_call = true;
~~~

**Try with REPEATABLE READ.** Both A and B begin transactions before updating:

~~~sql
-- Connection A
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT count(*)
FROM concurrency_lab.on_call
WHERE on_call;
-- Result: 2
~~~

~~~sql
-- Connection B
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT count(*)
FROM concurrency_lab.on_call
WHERE on_call;
-- Result: 2
~~~

Then update different rows:

~~~sql
-- Connection A
UPDATE concurrency_lab.on_call
SET on_call = false
WHERE doctor_id = 1;

COMMIT;
~~~

~~~sql
-- Connection B
UPDATE concurrency_lab.on_call
SET on_call = false
WHERE doctor_id = 2;

COMMIT;
~~~

Both transactions can commit because they modify different rows and each uses its own snapshot. Check the result:

~~~sql
SELECT count(*)
FROM concurrency_lab.on_call
WHERE on_call;
~~~

The result is **0**, violating the "at least one doctor on call" invariant. This is write skew.

**Repeat with SERIALIZABLE.** Restore both rows to **true**, then run the exact same read-first, update-later schedule above, starting each transaction with:

~~~sql
BEGIN ISOLATION LEVEL SERIALIZABLE;
~~~

PostgreSQL tracks read/write dependencies via SSI. When it detects that an execution schedule cannot be equivalent to any valid serial order, PostgreSQL aborts at least one transaction. Serialization errors carry SQLSTATE **40001**; the error may occur on the update statement or at commit. After rolling back the aborted transaction, inspecting the data must show that the invariant remains intact.

With **SERIALIZABLE**, applications must actively handle serialization failures by retrying the **entire transaction** from the start. Do not retry only the failing statement, because earlier decisions were made from a stale snapshot. On retry, the transaction must re-read business conditions and recompute actions.

If an invariant must be protected across isolation levels, consider explicit locking or appropriate data constraints. For example, you can lock a row representing the shared resource before checking and modifying related rows. Choose the protection mechanism based on the specific invariant, not merely on whether a single statement succeeds.

## 8. Observing Transactions and Locks During Tests

**pg_stat_activity** shows which statement a backend is running, its state, and its wait event. **pg_blocking_pids()** identifies the connections blocking a backend.

The following query displays pairs of blocked and blocking connections:

~~~sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.application_name AS blocked_app,
    blocker.pid AS blocker_pid,
    blocker.application_name AS blocker_app,
    blocked.wait_event_type,
    blocked.wait_event,
    blocked.query AS blocked_query
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL
    unnest(pg_blocking_pids(blocked.pid)) AS p(blocker_pid)
JOIN pg_stat_activity AS blocker
    ON blocker.pid = p.blocker_pid
WHERE blocked.datname = current_database();
~~~

You can inspect locks held or awaited by both backends:

~~~sql
SELECT
    pid,
    locktype,
    relation::regclass AS relation,
    mode,
    granted
FROM pg_locks
WHERE pid IN (
    SELECT pid
    FROM pg_stat_activity
    WHERE application_name IN (
        'concurrency-test-A',
        'concurrency-test-B'
    )
)
ORDER BY pid, granted, locktype;
~~~

**granted = false** indicates a lock waiting to be granted. **relation** may be **NULL** for lock types not tied directly to a relation. Visibility into other sessions' details depends on database privileges; the test account may require appropriate monitoring privileges such as **pg_read_all_stats**.

When logging a test run, record at least **application_name**, backend PID, isolation level, start/end timestamps of each step, involved statements, and error SQLSTATE. This data helps separate business bugs from timeouts, deadlocks, or serialization failures.

## 9. Controlling Execution Schedules in Automated Tests

An automated test should never hope two threads "happen" to interleave in the right order. Use your framework's synchronization primitives to control each milestone:

1. Create two independent connections and verify distinct PIDs.
2. Have A and B begin transactions, then wait until both signal readiness.
3. Let A execute its first operation; only after A signals completion allow B to proceed.
4. When testing lock waits, confirm B is actually blocked via **pg_blocking_pids()** or the appropriate wait state before releasing A.
5. Collect results, assert SQLSTATE or final data, then commit/roll back and restore fixtures.

Primitives such as barriers, latches, semaphores, channels, or messages between workers work well for synchronization. A third observer connection can verify database state before letting the next step run.

**pg_sleep()** is useful to introduce a pause for manual observation, but it should not be the primary synchronization mechanism in automated tests. For example, "A sleeps 1 second then B updates" depends on machine load, latency, and CPU scheduling; in CI, execution order can flip. A barrier that releases B only after A's condition is confirmed is far more reliable.

If an application-level workflow needs locking, PostgreSQL provides advisory locks. Transaction-level advisory locks are automatically released when the transaction ends:

~~~sql
BEGIN;

-- Two integers forming an application lock key.
SELECT pg_advisory_xact_lock(42, 1001);

-- Perform the work that needs protection.

COMMIT;
~~~

Another transaction using the same key pair must wait. You can use **pg_try_advisory_xact_lock(42, 1001)** to probe and receive a boolean result instead of waiting. Advisory locks do not automatically protect rows or enforce data constraints; every coordinating code path must adhere to the same lock convention and key identifiers.

When building automated tests, keep these principles in mind:

- Give each test its own data or an explicit reset step; avoid two tests modifying the same row.
- Use bounded timeouts so tests never hang indefinitely. On timeout, roll back any open transactions and close or return connections to the pool cleanly.
- Hold connections A and B simultaneously to guarantee two backends truly coexist concurrently.
- Assert outcomes using invariants and SQLSTATE rather than depending on which backend is chosen as the deadlock victim.
- For **40001** and **40P01**, if the application supports retries, test the retry logic at the transaction boundary as well.
- Avoid external side effects before transaction commit unless those side effects have their own consistency guarantees; otherwise retries can send duplicate emails or create duplicate tasks.
- Run tests against a dedicated database/schema and never leave test transactions open after tests finish.

## 10. Scenario Matrix to Include

| Scenario | Core execution schedule | Outcomes to verify |
|---|---|---|
| Lost update | A and B read the same value; each writes back a result computed from the stale read | Test detects overwritten result; atomic update version yields the right value |
| Row lock wait | A runs **SELECT ... FOR UPDATE**; B updates the same row | B waits, **pg_blocking_pids()** identifies A, B proceeds after A finishes |
| Lock timeout | A holds lock longer than B's **lock_timeout** | B receives a timeout error and the transaction is rolled back |
| Deadlock | A locks row 1 then requests row 2; B locks row 2 then requests row 1 | One transaction receives **40P01**, the wait cycle clears |
| Non-repeatable read | B commits a change between two reads by A | **READ COMMITTED** sees the new value; **REPEATABLE READ** keeps the old snapshot |
| Write skew | A and B both read an invariant and update two different rows | **REPEATABLE READ** can violate the invariant; **SERIALIZABLE** aborts the transaction causing non-serializable schedule |
| Transaction retry | Deterministically trigger **40001** or **40P01** | Application rolls back and retries the entire transaction; final data remains valid |

## 11. Common Mistakes That Make Tests Unreliable

**Sharing one connection for both A and B.** One PostgreSQL connection executes only one transaction stream at a time. Sharing a connection invalidates the concurrency model. Confirm two distinct backend PIDs.

**Not keeping transactions open long enough.** If A commits immediately after acquiring a lock, B might never enter a waiting state. Tests need a controlled pause keeping A open until B is observed blocking.

**Using pg_sleep() to guess ordering.** Sleep durations do not prove a transaction has reached the target checkpoint. Use barriers or confirm state via monitoring queries.

**Checking only that statements returned no errors.** Transactions can commit without SQL errors yet still violate a global invariant, such as write skew. Always inspect final state and business rules.

**Retrying a single statement instead of the entire transaction.** After **40001**, earlier decisions may have relied on a stale snapshot. Roll back and restart from the beginning with fresh reads.

**Forgetting to roll back after an error.** After a SQL error inside a transaction, PostgreSQL marks the transaction as aborted. Subsequent statements will not run normally until a rollback or rollback to an appropriate savepoint.

**Leaving dangling transactions in tests.** A transaction forgotten without commit/rollback can hold locks and stall later tests. Use cleanup in test harness **finally** blocks, explicit timeouts, and PID logging for tracing.

## 12. Checklist to Complete a Concurrency Test

Before considering a scenario reproducible, verify:

- [ ] Initial data is explicitly initialized and resettable.
- [ ] A and B use two distinct PostgreSQL backends.
- [ ] Isolation level and transaction boundaries are documented.
- [ ] The operation schedule has a deterministic order, including wait points and commit points.
- [ ] There is a mechanism to observe waiting states or emitted errors.
- [ ] Expected outcomes include final data, invariants, or SQLSTATE.
- [ ] All transactions are committed or rolled back, even when tests fail.
- [ ] Tests do not depend on fixed sleep durations or random execution order.

By testing concurrency with controlled schedules, engineering teams can reliably reproduce rare bugs, pinpoint which transaction sees which data, and verify that locking, isolation levels, and retry handling preserve business rules when multiple connections operate simultaneously.
