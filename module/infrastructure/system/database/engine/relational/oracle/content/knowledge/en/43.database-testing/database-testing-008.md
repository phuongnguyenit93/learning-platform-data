# Concurrency Testing with Multiple Sessions and Controlled Execution Schedules

## 1. Goals of concurrency testing

Concurrency testing verifies that multiple transactions can access data simultaneously while preserving business invariants. In Oracle Database, each JDBC connection typically corresponds to a separate database session in dedicated server mode. Therefore, to test genuine contention, use multiple independent connections/sessions and actively control operation ordering.

Common bugs to reproduce include:

- **Lost update:** a transaction overwrites another transaction's change because both read the same stale value.
- **Dirty read:** a transaction reads uncommitted data from another transaction. Oracle does not permit dirty reads under standard read models.
- **Non-repeatable read:** the same transaction reads a row twice and sees different values because another transaction committed in between.
- **Write/write conflict:** multiple transactions update the same row or set of rows concurrently.
- **Lock wait/timeout:** a transaction waits on a row locked by another session.
- **Deadlock:** transactions wait on each other in a lock cycle.
- **Serialization conflict:** a transaction running under `SERIALIZABLE` isolation cannot proceed because concurrent changes prevent serializing its snapshot.
- **Queue race:** multiple workers attempt to claim the same task, leading to duplicate processing without proper locking/claiming mechanisms.

The goal is not merely generating heavy load. A valuable concurrency test must reproduce an execution schedule, define synchronization points across sessions, predict outcomes, and verify actual state after commit/rollback.

## 2. Sessions, connections, and transactions in tests

### 2.1. Every session must be an independent connection

Two SQL Developer tabs are not necessarily two sessions if they share the same connection. When testing, open two separate connections or two separate SQL*Plus processes. Verify session identity with:

```sql
SELECT sys_context('USERENV', 'SID') AS sid,
       sys_context('USERENV', 'SESSION_USER') AS session_user,
       sys_context('USERENV', 'SERVICE_NAME') AS service_name,
       sys_context('USERENV', 'INSTANCE_NAME') AS instance_name
FROM dual;
```

Two independent sessions must show distinct `SID`s on the same instance. On RAC, `SID`s can overlap across instances; combine `INST_ID` and `SID` to identify sessions.

In Java, each test thread must borrow its own connection from the pool. Never share a single JDBC `Connection`, `EntityManager`, or Hibernate `Session` across threads. Those objects are not designed for concurrent multi-threaded access.

### 2.2. Distinguishing sessions from transactions

One session can execute many transactions over time. In Oracle, a transaction begins when a session executes an operation requiring a transaction and ends on `COMMIT` or `ROLLBACK`. An `INACTIVE` session may still hold an uncommitted transaction and row locks.

When designing a test schedule, explicitly document:

- Which session performs each operation.
- When each transaction starts.
- Which rows/tablespaces/resources are accessed or locked.
- Which statement causes a wait.
- When commit/rollback occurs and releases locks.

Do not use `ACTIVE`/`INACTIVE` status alone to conclude whether a session holds locks. Inspect the corresponding transaction, locks, and wait events.

## 3. Preparing a repeatable test environment

### 3.1. Creating dedicated test tables

Use a dedicated schema or table for concurrency tests; never run destructive contention scenarios against production business tables.

```sql
CREATE TABLE concurrency_account (
    account_id NUMBER(10) PRIMARY KEY,
    balance    NUMBER(12, 2) NOT NULL,
    version_no NUMBER(10) DEFAULT 0 NOT NULL
);

INSERT INTO concurrency_account(account_id, balance, version_no)
VALUES (1, 1000, 0);

INSERT INTO concurrency_account(account_id, balance, version_no)
VALUES (2, 1000, 0);

COMMIT;
```

Before each test run, reset the fixture to a known state:

```sql
UPDATE concurrency_account
SET balance = 1000,
    version_no = 0
WHERE account_id IN (1, 2);

COMMIT;
```

Reset data before starting the schedule, never between steps being observed. If multiple tests run concurrently, use distinct account IDs/test run IDs so tests do not interfere with one another.

### 3.2. Recording version and environment details

Before comparing results across runs, record:

```sql
SELECT banner FROM v$version ORDER BY banner;

SELECT name, value
FROM v$parameter
WHERE name IN ('compatible', 'transactions', 'processes', 'sessions');

SELECT name, open_mode, database_role
FROM v$database;
```

Also record the JDBC driver, JDK, Hibernate/Spring version if testing from an application, isolation level, pool size, service name, RAC instance, and timeout configuration. These differences can alter behavior or wait durations.

### 3.3. Creating a test event log

To trace execution schedules, record timestamps, sessions, transaction steps, and outcomes. A simple log table:

```sql
CREATE TABLE concurrency_test_log (
    run_id       VARCHAR2(64) NOT NULL,
    step_name    VARCHAR2(100) NOT NULL,
    session_sid  NUMBER,
    event_time   TIMESTAMP(6) DEFAULT SYSTIMESTAMP NOT NULL,
    details      VARCHAR2(1000)
);
```

Logs can be written from the test harness or the application. If written within the transaction under test, logs roll back with the transaction—which is occasionally useful for testing atomicity, though unsuitable for preserving failure traces. For audit logs that must survive rollbacks, write logs over a separate connection or in the test runner, ensuring logging does not alter the lock schedule under measurement.

## 4. Designing controlled execution schedules

### 4.1. Execution schedules

An execution schedule specifies the step order across sessions. For example, two sessions reading the same account:

| Order | Session A | Session B |
|---:|---|---|
| 1 | `SELECT balance` | |
| 2 | | `SELECT balance` |
| 3 | Compute new balance from read value | |
| 4 | `UPDATE` and `COMMIT` | |
| 5 | | `UPDATE` using stale read value and `COMMIT` |
| 6 | Check final balance | Check final balance |

Without enforcing this ordering, tests may interleave differently on each run and fail to reproduce the race condition.

### 4.2. Use barriers instead of fixed sleeps

In Java, `CountDownLatch`, `CyclicBarrier`, or `Phaser` synchronize threads at deterministic points. For example:

1. Both A and B finish reading data.
2. Both signal `readComplete`.
3. The test runner allows A to update and commit.
4. Only after A commits does the runner allow B to proceed with its update.
5. Verify results and row counts.

Avoid `Thread.sleep(1000)` as the primary synchronization mechanism. Sleeps only introduce relative delays; on slower machines or under different OS scheduling, the intended interleaving may still fail to occur. Barriers/latches establish explicit happens-before edges and make tests repeatable.

Every barrier must specify a timeout so the test never hangs indefinitely if a thread fails before reaching the synchronization point. When a participant fails, the test runner must release remaining participants, roll back transactions, and close connections.

### 4.3. Separating preparation, execution, and verification

A scenario can be divided into three phases:

```text
PREPARE
  Reset fixture, seed data, verify schema and sessions
       |
       v
EXECUTE SCHEDULE
  Execute each operation per defined barriers/latches
       |
       v
VERIFY
  Wait for all transactions to finish, read final data,
  check row counts, exceptions, locks, and event logs
```

Never read final results while involved transactions are still open. Before running the next schedule, verify all sessions have committed/rolled back and returned connections to the pool.

## 5. Scenario 1: reproducing a lost update

### 5.1. Execution schedule

Suppose the initial balance is 1,000. A wants to subtract 100, and B wants to subtract 50. Both read the stale value before either writes:

| Step | Session A | Session B |
|---:|---|---|
| 1 | Read `balance = 1,000` | |
| 2 | | Read `balance = 1,000` |
| 3 | Compute `900` | Compute `950` |
| 4 | Write `900`, commit | |
| 5 | | Write `950` based on stale value, commit |

The final result is 950, whereas business logic expects 850. A's change was overwritten by B.

### 5.2. Manual execution with two sessions

Reset the fixture first:

```sql
UPDATE concurrency_account
SET balance = 1000, version_no = 0
WHERE account_id = 1;
COMMIT;
```

**Session A:**

```sql
SELECT balance FROM concurrency_account WHERE account_id = 1;
-- Observes 1000, does not update yet.
```

**Session B:**

```sql
SELECT balance FROM concurrency_account WHERE account_id = 1;
-- Also reads 1000, does not update yet.
```

**Session A:**

```sql
UPDATE concurrency_account
SET balance = 900
WHERE account_id = 1;
COMMIT;
```

**Session B:**

```sql
UPDATE concurrency_account
SET balance = 950
WHERE account_id = 1;
COMMIT;
```

Verify:

```sql
SELECT balance
FROM concurrency_account
WHERE account_id = 1;
```

The result `950` demonstrates that B wrote a value calculated from a stale snapshot. Note that Oracle has no dirty reads; both A and B read the committed value of 1,000. The lost update stems from the application's read-modify-write pattern.

### 5.3. Protecting with optimistic version checks

Reset the fixture. Both sessions read `balance=1000`, `version_no=0`. After A commits:

**Session A:**

```sql
UPDATE concurrency_account
SET balance = 900,
    version_no = version_no + 1
WHERE account_id = 1
  AND version_no = 0;

-- Verify SQL%ROWCOUNT = 1, then:
COMMIT;
```

**Session B** uses the previously read version:

```sql
UPDATE concurrency_account
SET balance = 950,
    version_no = version_no + 1
WHERE account_id = 1
  AND version_no = 0;

-- SQL%ROWCOUNT must be 0 because current version is already 1.
ROLLBACK;
```

The application must treat `rowcount=0` as an optimistic conflict rather than reporting success. With JPA, `@Version` causes Hibernate to auto-generate the version predicate and translate mismatches into an optimistic locking exception.

### 5.4. Protecting with atomic updates

If the operation only deducts balance without complex logic relying on a prior read, push the calculation into a single SQL statement:

```sql
UPDATE concurrency_account
SET balance = balance - 100
WHERE account_id = 1
  AND balance >= 100;
```

Check `SQL%ROWCOUNT` to see whether a row was updated. This atomic SQL lets Oracle compute the subtraction against the current row value in row-lock order, avoiding the read-stale-balance-then-overwrite pattern. Transactions and appropriate business checks are still required.

## 6. Scenario 2: observing row locks and lock waits

### 6.1. Session A acquires a row lock

```sql
SELECT account_id, balance
FROM concurrency_account
WHERE account_id = 1
FOR UPDATE;
```

Session A holds the row lock until commit or rollback. You can also test:

```sql
UPDATE concurrency_account
SET balance = balance - 10
WHERE account_id = 1;
-- Not committed yet.
```

### 6.2. Session B attempts to update the same row

While A has not committed:

```sql
UPDATE concurrency_account
SET balance = balance - 20
WHERE account_id = 1;
```

B blocks waiting on the lock held by A. Once A commits/rolls back, B proceeds according to the predicate and current data state. Record when B began waiting and when A released the lock.

### 6.3. Testing NOWAIT and WAIT

While A still holds the lock, Session B runs:

```sql
SELECT account_id
FROM concurrency_account
WHERE account_id = 1
FOR UPDATE NOWAIT;
```

Oracle raises `ORA-00054` if the lock cannot be acquired immediately.

Or:

```sql
SELECT account_id
FROM concurrency_account
WHERE account_id = 1
FOR UPDATE WAIT 3;
```

Oracle waits up to roughly three seconds and then raises an error if the lock is not released. A common error code upon wait timeout is `ORA-30006`.

### 6.4. Testing SKIP LOCKED

While A locks account 1, B runs:

```sql
SELECT account_id
FROM concurrency_account
WHERE account_id IN (1, 2)
ORDER BY account_id
FOR UPDATE SKIP LOCKED;
```

B can claim account 2 and skip locked account 1. This technique is useful when multiple workers claim queue rows concurrently. The result can be empty if all matching rows are locked; never interpret an empty result as meaning the queue has no work.

## 7. Scenario 3: reproducing a controlled deadlock

### 7.1. Setup

Reset data and commit. Two sessions lock two different rows:

**Session A:**

```sql
SELECT account_id
FROM concurrency_account
WHERE account_id = 1
FOR UPDATE;
```

**Session B:**

```sql
SELECT account_id
FROM concurrency_account
WHERE account_id = 2
FOR UPDATE;
```

### 7.2. Creating a wait cycle

**Session A** requests row 2:

```sql
UPDATE concurrency_account
SET balance = balance + 1
WHERE account_id = 2;
```

A waits on B.

**Session B** requests row 1:

```sql
UPDATE concurrency_account
SET balance = balance + 1
WHERE account_id = 1;
```

B waits on A. Oracle detects the deadlock and returns `ORA-00060` to one statement selected to break the cycle. The selected statement is rolled back; the other transaction can proceed once locks are released.

After observing, explicitly roll back both sessions to return the fixture to a known state. In applications, upon receiving a deadlock, roll back the failed transaction and retry only if safe for business logic.

### 7.3. Preventing deadlocks with consistent lock ordering

If all transactions always lock accounts in ascending `ACCOUNT_ID` order, A and B request locks in the same order. One transaction may wait on the other, but a wait cycle is far less likely to form.

For multi-row updates, define a consistent lock ordering and keep transactions short. Never rely on incidental query plan ordering; acquire locks explicitly in sorted key order when necessary.

## 8. Scenario 4: READ COMMITTED and SERIALIZABLE

### 8.1. Oracle's default READ COMMITTED

Oracle defaults to `READ COMMITTED`. Each SQL statement sees data committed before the statement began. Thus, two `SELECT` statements in the same transaction can observe two different snapshots if another transaction commits in between.

Illustrative schedule:

| Order | Session A | Session B |
|---:|---|---|
| 1 | `SELECT balance` sees `1,000` | |
| 2 | | `UPDATE ... SET balance=900; COMMIT;` |
| 3 | Second `SELECT balance` sees `900` | |

This is a non-repeatable read at the transaction level, though each `SELECT` still reads consistent data as of its own statement start time.

### 8.2. SERIALIZABLE

Set the isolation level before the transaction executes DML/queries:

```sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
```

The transaction sees a consistent snapshot as of the transaction start time. If another transaction modifies a row after that snapshot and the current transaction attempts to modify the same row, Oracle can return `ORA-08177: can't serialize access for this transaction`.

Test schedule:

1. A begins a `SERIALIZABLE` transaction and reads account 1.
2. B begins a transaction, updates account 1, and commits.
3. A updates account 1 based on its older snapshot.
4. Oracle may raise `ORA-08177`; A must roll back and start a new transaction if retrying.

Never run `SET TRANSACTION` after a transaction has already begun data operations. To compare isolation levels, reset the fixture and use a fresh session or fresh transaction for each run.

### 8.3. Do not confuse SERIALIZABLE with table-wide locking

Oracle `SERIALIZABLE` uses read consistency and serialization conflict checks; it does not simply lock every row a transaction reads. Other transactions can still make certain modifications; conflicts are detected per Oracle rules when a transaction attempts a write that cannot be serialized.

## 9. Scenario 5: multiple workers claiming jobs with SKIP LOCKED

### 9.1. Creating a test queue

```sql
CREATE TABLE concurrency_job (
    job_id       NUMBER(10) PRIMARY KEY,
    status       VARCHAR2(20) NOT NULL,
    payload      VARCHAR2(200),
    claimed_by   VARCHAR2(50),
    claimed_at   TIMESTAMP(6)
);

INSERT INTO concurrency_job(job_id, status, payload)
VALUES (1, 'READY', 'job-one');

INSERT INTO concurrency_job(job_id, status, payload)
VALUES (2, 'READY', 'job-two');

INSERT INTO concurrency_job(job_id, status, payload)
VALUES (3, 'READY', 'job-three');

COMMIT;
```

### 9.2. Worker A locks and claims one job

```sql
SELECT job_id, payload
FROM concurrency_job
WHERE status = 'READY'
ORDER BY job_id
FETCH FIRST 1 ROW ONLY
FOR UPDATE SKIP LOCKED;
```

After claiming the job, A updates its status and commits:

```sql
UPDATE concurrency_job
SET status = 'RUNNING',
    claimed_by = 'WORKER_A',
    claimed_at = SYSTIMESTAMP
WHERE job_id = :job_id;

COMMIT;
```

Worker B runs the same `SELECT` while A holds the lock. B skips the row A locked and can claim the next job. After commit, other workers no longer see the claimed job as `READY`.

### 9.3. Claiming and updating must share an appropriate transaction

Never read the job, commit, and then update its status in another transaction. The window between the two operations allows another worker to read the same job and double-claim it. Locking the row, updating status, and committing must occur within the same short transaction.

In production systems, also add leases/heartbeats, retries, and handling for jobs abandoned when a worker dies mid-execution. `SKIP LOCKED` prevents multiple workers from claiming locked rows at claim time; it does not automatically recover jobs left orphaned after committing `RUNNING`.

## 10. Coordinating execution schedules from Java

### 10.1. Using an independent connection per worker

A Java test can use `ExecutorService` to run two transactions in parallel and `CountDownLatch` to enforce ordering. The example below demonstrates a lost-update schedule using plain JDBC:

```java
ExecutorService executor = Executors.newFixedThreadPool(2);
CountDownLatch bothRead = new CountDownLatch(2);
CountDownLatch aCommitted = new CountDownLatch(1);

Callable<Void> sessionA = () -> {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);
        try {
            int oldBalance = readBalance(connection, 1);
            bothRead.countDown();
            await(bothRead, 5, TimeUnit.SECONDS);

            updateBalance(connection, 1, oldBalance - 100);
            connection.commit();
            aCommitted.countDown();
            return null;
        } catch (Exception ex) {
            connection.rollback();
            aCommitted.countDown();
            throw ex;
        }
    }
};

Callable<Void> sessionB = () -> {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);
        try {
            int oldBalance = readBalance(connection, 1);
            bothRead.countDown();
            await(bothRead, 5, TimeUnit.SECONDS);
            await(aCommitted, 5, TimeUnit.SECONDS);

            updateBalance(connection, 1, oldBalance - 50);
            connection.commit();
            return null;
        } catch (Exception ex) {
            connection.rollback();
            throw ex;
        }
    }
};

Future<Void> a = executor.submit(sessionA);
Future<Void> b = executor.submit(sessionB);
try {
    a.get(15, TimeUnit.SECONDS);
    b.get(15, TimeUnit.SECONDS);
} finally {
    executor.shutdownNow();
}
```

`readBalance`, `updateBalance`, and `await` are test-defined helpers; `await` must throw an error on timeout or thread interruption. This example illustrates coordination only: add imports, exception handling, and ensure latches are released across all failure branches. In real tests, use `try/finally` to always count down latches/shut down the executor, and put timeouts on both `Future.get` and barriers.

Key points:

- Both callables acquire separate connections from `DataSource`.
- Both complete reading before A writes.
- B writes only after A commits.
- B writes an absolute value computed from stale data to intentionally reproduce the lost update.
- The test verifies a final balance of `950` in the buggy scenario, then re-runs with version checking to verify B is rejected.

### 10.2. Never share one EntityManager across threads

`EntityManager` and Hibernate `Session` are not thread-safe. Each thread/transaction needs its own persistence context. If a test places Spring `@Transactional` on the test method, that transaction is bound to the test thread; worker threads do not automatically join it. Create separate transactions inside each worker and commit fixtures before starting.

With Spring, use `TransactionTemplate` inside each worker or invoke a service through a Spring proxy to start real transactions. When using `REQUIRES_NEW`, avoid self-invocation inside the same bean because the proxy may be bypassed.

### 10.3. Multi-stage barriers

A complex schedule can use multiple barriers:

```text
Barrier 1: all sessions connected and SIDs verified
Barrier 2: all sessions finished reading initial data
Gate A: allow session A to write/commit
Gate B: open only after A commits
Barrier 3: all sessions completed or received expected errors
Verify: test runner reads final outcome
```

Record durations within the same JVM using `System.nanoTime()`; use database timestamps such as `SYSTIMESTAMP` when correlating Oracle-side timings. Never compare `nanoTime` directly across different JVMs because it is not a wall-clock time.

## 11. Coordinating sessions manually with SQL Developer/SQL*Plus

### 11.1. Preparing two session windows

1. Open two separate connections to the same service/PDB.
2. Run the `SID` query in both windows and confirm they differ.
3. Reset the fixture from an admin session and commit.
4. Execute step-by-step according to the schedule table; do not run all of script A before script B if the schedule requires interleaving.
5. Record start/end timestamps and the outcome of each statement.
6. Afterward, commit/roll back both sessions and verify no open transactions or locks remain.

In SQL*Plus, you can use `PROMPT` to mark steps and run commands incrementally. `PAUSE` works for interactive scripts, but does not synchronize two processes automatically; the tester must still control ordering across windows.

### 11.2. Checking session identity

```sql
SELECT sid,
       serial#,
       username,
       status,
       module,
       action,
       client_identifier
FROM v$session
WHERE audsid = SYS_CONTEXT('USERENV', 'SESSIONID');
```

Record `SID`/`SERIAL#` for each window. On RAC, query `GV$SESSION` and include `INST_ID`.

## 12. Observing blocking sessions and locks in Oracle

### 12.1. Viewing waiting sessions and blockers

```sql
SELECT sid,
       serial#,
       username,
       status,
       sql_id,
       event,
       wait_class,
       seconds_in_wait,
       blocking_session_status,
       blocking_instance,
       blocking_session,
       final_blocking_session,
       module,
       action
FROM v$session
WHERE username IS NOT NULL
ORDER BY seconds_in_wait DESC;
```

`BLOCKING_SESSION` and `FINAL_BLOCKING_SESSION` help identify the blocking session when Oracle detects a blocker. `EVENT` shows what resource type the session is waiting on; not every wait is a row lock.

### 12.2. Viewing TX/TM locks

```sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.event,
       l.type,
       l.id1,
       l.id2,
       l.lmode,
       l.request,
       l.block
FROM v$lock l
JOIN v$session s
  ON s.sid = l.sid
ORDER BY s.sid, l.type;
```

Common lock types:

- `TX`: transaction enqueue, typically associated with transaction/row-level contention.
- `TM`: DML enqueue on an object/table.

`LMODE` is the held mode; `REQUEST` is the requested mode. Mode numbers are Oracle-defined codes—consult `V$LOCK` documentation to interpret them accurately.

### 12.3. Viewing open transactions

```sql
SELECT s.sid,
       s.serial#,
       s.username,
       t.start_time,
       t.used_ublk,
       t.used_urec
FROM v$transaction t
JOIN v$session s
  ON s.taddr = t.addr
ORDER BY t.start_time;
```

Sessions with long-running transactions are prime investigation candidates when locks are held. Inspect application module/action, active SQL, and transaction start time before requesting session termination.

### 12.4. Tagging module/action from the application

Applications can tag sessions with business identifiers:

```sql
BEGIN
  DBMS_APPLICATION_INFO.SET_MODULE(
    module_name => 'ConcurrencyTest',
    action_name => 'SessionA_UpdateAccount'
  );
  DBMS_SESSION.SET_IDENTIFIER('TEST_RUN_2026_001');
END;
/
```

These values help DBAs correlate `V$SESSION` entries with test cases and execution steps. When a connection is returned to the pool, reset module/action/client identifier so subsequent requests do not inherit stale tags.

## 13. Timeouts and post-test cleanup

### 13.1. Test runner timeouts

Set timeouts for:

- Acquiring a connection from the pool.
- Waiting on barriers/latches.
- `Future.get()` or task completion.
- Queries/statements.
- Transactions.
- Lock waits when scenarios intentionally wait.

A test runner timeout does not automatically roll back the database-side transaction if a thread is interrupted mid-JDBC call. Inside `finally`, attempt to roll back, close `ResultSet`/`Statement`/`Connection`, and release latches. If a connection is lost, inspect sessions/transactions on Oracle before re-running.

### 13.2. Cleaning up data

After the test:

```sql
ROLLBACK;

SELECT account_id, balance, version_no
FROM concurrency_account
ORDER BY account_id;
```

`ROLLBACK` affects only the current session's transaction. The DBA/test runner must verify other sessions have ended and reset fixture data in a separate transaction. Never drop test tables while sessions still hold locks or uncommitted transactions.

### 13.3. Do not kill sessions as a default cleanup step

`ALTER SYSTEM KILL SESSION` or terminating processes should only be used when a session is genuinely hung and impact has been assessed. Killing a session can trigger lengthy rollbacks, affect other users, and generate extra undo load. Prefer rolling back and closing connections from the test harness; if DBA intervention is required, record `SID`, `SERIAL#`, `INST_ID`, and the reason.

## 14. Test design flaws that produce unreliable results

### 14.1. Sharing one connection across multiple threads

Operations are not truly independent; results do not represent two Oracle sessions. Use a separate connection per worker and verify `SID`s.

### 14.2. Using sleep instead of barriers

Execution order depends on machine speed and system load. Use latches/barriers or manual step-by-step control.

### 14.3. Wrapping the test method in an outer transaction

Worker threads may not see uncommitted fixtures from the test transaction, and the main thread's transaction does not wrap worker transactions. Commit fixtures before running workers and manage transactions independently inside each worker.

### 14.4. Failing to assert row counts or final state

A statement throwing no exceptions does not prove business correctness. For optimistic updates, check updated row counts. For queues, verify each job was claimed once. For lost updates, calculate the expected final balance from the business operations.

### 14.5. Test data creates no contention

If each session updates a different account, the test never exercises row locks or lost updates. Intentionally point sessions at the same target key/row while isolating each test run with its own IDs.

### 14.6. Failing to verify open transactions are closed

A session may still hold locks after a test ends if code forgets to commit/roll back. Always verify transactions have ended and connections returned to the pool.

## 15. Controlled concurrency testing workflow

1. Clearly state the business invariant and bug to reproduce—for example, no lost updates, non-negative inventory, or single-worker claim per job.
2. Create isolated fixtures and commit initial state; record Oracle release, isolation level, schema, service, and driver.
3. Open multiple independent connections; verify `SID`/`SERIAL#`/`INST_ID` and tag `MODULE`, `ACTION`, `CLIENT_IDENTIFIER`.
4. Define the schedule as ordered steps; specify which session reads, writes, waits, commits, or rolls back.
5. Use barriers/latches in Java or manual step control in SQL Developer/SQL*Plus; avoid `sleep` for synchronization.
6. Set timeouts on every wait point and ensure all error paths roll back and close resources.
7. Run scenarios for lost updates, optimistic version conflicts, pessimistic lock waits, `NOWAIT`/`WAIT`/`SKIP LOCKED`, deadlocks, and `SERIALIZABLE` where relevant.
8. Inspect `V$SESSION`, `V$LOCK`, `V$TRANSACTION`, and events/blockers to confirm the database actually experienced the expected waits/locks.
9. Verify row counts, exceptions, final state, and event logs after all transactions complete.
10. Reset fixtures and repeat; archive schedules, results, and environment details to reproduce regressions.

## 16. Principles to remember

- Concurrency testing requires multiple real Oracle sessions; two threads sharing one connection are not two independent database sessions.
- Execution schedules must be deterministic; use barriers/latches instead of relying on `sleep`.
- Commit fixtures before starting workers; give each worker its own connection, transaction, and persistence context.
- Oracle `READ COMMITTED` prevents dirty reads, yet lost updates can still occur via read-modify-write logic and non-repeatable reads between statements.
- `@Version`/version predicates detect lost updates; `SELECT FOR UPDATE` holds row locks until commit/rollback.
- `NOWAIT`, `WAIT n`, and `SKIP LOCKED` behave differently; verify both errors and returned row sets.
- Deadlocks must be reproduced using opposing lock orders; reduce risk via consistent lock ordering and short transactions.
- `SERIALIZABLE` can raise `ORA-08177`; retries must start a fresh transaction.
- Inspect blockers, wait events, TX/TM locks, and transaction age to verify root causes rather than relying solely on test timings.
- Clean up with controlled rollbacks and connection closes; never kill sessions or drop fixtures before confirming transactions have ended.

## Oracle and Java reference documentation

- [Oracle Database 19c Concepts — Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html)
- [Oracle Database 19c SQL Language Reference — SELECT and FOR UPDATE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html)
- [Oracle Database 19c Reference — V$SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION.html)
- [Oracle Database 19c Reference — V$LOCK](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOCK.html)
- [Oracle Database 19c Reference — V$TRANSACTION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-TRANSACTION.html)
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_APPLICATION_INFO](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_APPLICATION_INFO.html)
- [Java SE API — CountDownLatch](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [Java SE API — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
