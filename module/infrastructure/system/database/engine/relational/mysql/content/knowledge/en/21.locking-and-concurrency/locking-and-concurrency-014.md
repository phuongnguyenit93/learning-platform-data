# GET_LOCK, RELEASE_LOCK, and connection-scoped advisory lock lifecycles

MySQL provides advisory lock functions so multiple sessions can coordinate access to a logical resource. The two primary functions are `GET_LOCK()` to request a lock by name and `RELEASE_LOCK()` to release it. Unlike InnoDB row locks, named locks are tied to the connection session, not to a row or a transaction.

The most important point when using these functions is connection lifecycle. Locks remain held after `COMMIT` and `ROLLBACK`; they are released only when the session calls the corresponding `RELEASE_LOCK()` or when the session terminates. If an application uses a connection pool and returns a connection to the pool while still holding a lock, the underlying physical session can keep holding the lock and block other requests.

In the **DATABASE_MYSQL** module, named locks are useful when protecting a logical task such as running a scheduled job, generating an invoice for the same order, or allowing only one process to rebuild a resource at a time. This lesson covers how they work, return values, lock scope, managing multiple locks, Java/JDBC integration, monitoring, and limitations to understand before deploying.

## 1. What is an advisory lock?

An advisory lock is a voluntary coordination mechanism among application components. One session requests a lock by name; another session requesting the same name must wait or receive a timeout result until the lock is released.

For example, two workers both want to process the resource `invoice:9001`:

- Worker A calls `GET_LOCK('billing:invoice:9001', 10)` and obtains the lock.
- Worker B calls `GET_LOCK()` with the same name and must wait.
- Once A finishes, A calls `RELEASE_LOCK()`.
- B can obtain the lock if its timeout has not expired.

Advisory locks do not automatically block `UPDATE` or `DELETE`. They only coordinate clients that follow the shared convention of calling `GET_LOCK()` before executing the protected work. Another application with write privileges on the table that ignores this convention can still modify data.

Therefore, advisory locks complement transactions, row locks, and constraints; they do not replace `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY`, or InnoDB's data protection mechanisms.

## 2. Scope and properties of named locks

Named locks are managed at the level of a single MySQL server instance:

- Lock names are shared across all sessions on the same `mysqld`.
- Lock names do not belong to a specific schema or table.
- Two applications on different databases using the same lock name still contend on the same lock.
- Locks are exclusive: at any given time only one session can hold that named lock.
- Locks are released via `RELEASE_LOCK()` or when the session terminates.
- `COMMIT` and `ROLLBACK` do not release named locks.
- `GET_LOCK()` does not create a data row or schema constraint.

Lock names can be up to 64 characters and must be non-empty. Lock name comparisons are case-insensitive; normalize names to lowercase to prevent two modules from accidentally using different casings for the same resource.

Example with an application-namespaced name:

```sql
SELECT GET_LOCK('billing:invoice:9001', 10);
```

Prefix with the application or module, followed by resource type and a stable identifier. Avoid generic names like `lock`, `job`, or `process`, as they easily collide with other components on the same server.

Lock names can appear in Performance Schema. Never include passwords, tokens, emails, or sensitive data in lock names.

## 3. GET_LOCK(): requesting a lock by name

Syntax:

```sql
GET_LOCK(lock_name, timeout)
```

Where:

- `lock_name` is the name of the lock to request.
- `timeout` is the wait duration in seconds.
- `timeout` equal to `0` means do not wait; if the lock is busy, return timeout immediately.
- Positive `timeout` allows waiting up to the specified number of seconds.
- Negative `timeout` means wait indefinitely; avoid using this in requests requiring bounded response times.

Example:

```sql
SELECT GET_LOCK('billing:invoice:9001', 10) AS lock_result;
```

Return values:

| Result | Meaning | Application action |
|---:|---|---|
| 1 | Lock acquired | Safe to run the protected work |
| 0 | Timed out without acquiring lock | Do not run the work; return busy status or retry per policy |
| NULL | Error occurred while requesting lock | Handle as an error; do not assume lock was acquired |

Never proceed with the protected work merely because the `SELECT` executed without throwing an exception. The application must explicitly verify that the result equals `1`.

Non-waiting example:

```sql
SELECT GET_LOCK('scheduler:daily-reconcile', 0) AS acquired;
```

This fits tasks that can skip a run if another worker is already processing. If the result is `0`, the worker logs skipped/busy and exits or reschedules per policy.

## 4. RELEASE_LOCK(): releasing a lock

Syntax:

```sql
RELEASE_LOCK(lock_name)
```

Return values:

| Result | Meaning |
|---:|---|
| 1 | Current session successfully released one lock hold |
| 0 | Current session does not own that lock; another session may hold it |
| NULL | Lock name does not exist |

Example:

```sql
SELECT RELEASE_LOCK('billing:invoice:9001') AS release_result;
```

Only the session owning the lock can release it. Another administrative session cannot use `RELEASE_LOCK()` to release a lock held by a running session. If a lock-holding session must be terminated, an authorized operator can identify the connection and handle the session per operational procedures; killing a connection affects all other work on that session.

### 4.1. Pairing GET_LOCK and RELEASE_LOCK properly

Basic SQL pattern:

Example using a simple inventory table:

```sql
CREATE TABLE inventory (
    sku VARCHAR(32) NOT NULL,
    reserved_quantity INT NOT NULL DEFAULT 0,
    PRIMARY KEY (sku)
) ENGINE = InnoDB;
```

```sql
-- Step 1: proceed only if the result is 1
SELECT GET_LOCK('inventory:sku:ABC-123', 10) AS acquired;

-- Step 2: execute work inside a transaction
START TRANSACTION;

UPDATE inventory
SET reserved_quantity = reserved_quantity + 1
WHERE sku = 'ABC-123';

COMMIT;

-- Step 3: release the advisory lock
SELECT RELEASE_LOCK('inventory:sku:ABC-123') AS released;
```

The statements above form a conditional workflow: if `GET_LOCK()` returns `0` or `NULL`, do not run the transaction. If `UPDATE` or `COMMIT` fails, the application must roll back as needed and still run `RELEASE_LOCK()` in its cleanup branch.

Release the lock after the transaction has run `COMMIT` or `ROLLBACK`. That way, another session obtains the lock only after the previous work's data changes have completed.

### 4.2. Re-acquiring the same lock name within one session

Since MySQL 5.7.5, a single session can hold multiple named locks concurrently and can acquire the same lock name multiple times. Each successful `GET_LOCK()` requires a matching `RELEASE_LOCK()`.

Example:

```sql
SELECT GET_LOCK('app:resource:42', 0); -- 1
SELECT GET_LOCK('app:resource:42', 0); -- 1, same session re-acquires

SELECT RELEASE_LOCK('app:resource:42'); -- 1 hold released
SELECT RELEASE_LOCK('app:resource:42'); -- remaining hold released
```

After the first `RELEASE_LOCK()`, another session still cannot acquire the lock because the current session retains one lock hold. Only after every hold on that name is released can another session acquire the lock.

This is a common cause of locks lingering too long: a code path calls `GET_LOCK()` repeatedly but only calls `RELEASE_LOCK()` once. Applications should track successful acquisition counts and guarantee matching release counts.

Prior to MySQL 5.7.5, a session could not hold multiple named locks simultaneously the way newer versions do. If supporting older servers, verify exact version behavior and design to hold only one lock at a time.

## 5. Lock lifecycle: session, transaction, and connection pool

Named locks follow a session-scoped lifecycle:

| Event | Is the named lock released? |
|---|---|
| `COMMIT` | No |
| `ROLLBACK` | No |
| End of a `SELECT`/`UPDATE` statement | No |
| Successful `RELEASE_LOCK()` call | Yes, releases one lock hold |
| `RELEASE_ALL_LOCKS()` call | Yes, releases the session's named locks |
| Normal session termination | Yes |
| Session closed or connection killed | Yes, once the server terminates the session |
| Server restart | Locks in the old instance no longer exist |

### 5.1. COMMIT does not release GET_LOCK

Test in Session A:

```sql
SELECT GET_LOCK('demo:commit-lifecycle', 0);

START TRANSACTION;
SELECT 1;

COMMIT;

-- Lock is still held by Session A
SELECT IS_USED_LOCK('demo:commit-lifecycle');

SELECT RELEASE_LOCK('demo:commit-lifecycle');
```

`COMMIT` ends the transaction but does not release the advisory lock. This differs from InnoDB row locks, which are released when the transaction ends.

### 5.2. ROLLBACK also does not release GET_LOCK

```sql
SELECT GET_LOCK('demo:rollback-lifecycle', 0);

START TRANSACTION;

UPDATE inventory
SET reserved_quantity = reserved_quantity + 1
WHERE sku = 'ABC-123';

ROLLBACK;

-- Advisory lock still remains
SELECT IS_USED_LOCK('demo:rollback-lifecycle');

SELECT RELEASE_LOCK('demo:rollback-lifecycle');
```

Rollback undoes data changes inside the InnoDB transaction. It does not alter the session's named lock state.

### 5.3. Risks when using connection pools

Connection pools normally return a logical connection to the pool when the application calls `close()`. A logical close does not necessarily close the TCP connection or physical MySQL session.

If an application:

1. Borrows a connection from the pool.
2. Acquires `GET_LOCK()`.
3. Finishes work but forgets `RELEASE_LOCK()`.
4. Calls `close()` to return the connection to the pool.

then the physical session can keep holding the named lock. A subsequent request might receive that exact session, or other sessions may be blocked by the leaked lock.

Operational rules:

- Acquire and release on the exact same physical MySQL session.
- Place `RELEASE_LOCK()` inside `finally` or an equivalent cleanup mechanism.
- Return the connection to the pool only after releasing every lock owned by that code path.
- If release cannot be confirmed due to a connection error, evict/discard the physical connection via the pool API; never reuse a session with unknown lock state.
- Never call `RELEASE_ALL_LOCKS()` arbitrarily on a connection shared across multiple components.

If a network drop occurs and the server has not yet detected the lost session, the lock can persist until the server detects and closes the session. `GET_LOCK` has no time-based auto-expiring lease; `timeout` only bounds how long to wait for acquisition, not how long the lock can be held afterward.

## 6. Inspecting lock status

MySQL provides helper functions:

### 6.1. IS_FREE_LOCK()

```sql
SELECT IS_FREE_LOCK('billing:invoice:9001') AS is_free;
```

- `1`: no session currently holds the lock.
- `0`: lock is currently in use.
- `NULL`: an error occurred while checking.

### 6.2. IS_USED_LOCK()

```sql
SELECT IS_USED_LOCK('billing:invoice:9001') AS owner_connection_id;
```

If the lock is held, the function returns the connection ID of the owning session. If no session holds the lock, it returns `NULL`.

You can compare with:

```sql
SELECT CONNECTION_ID() AS current_connection_id;
```

### 6.3. Never use IS_FREE_LOCK() in place of GET_LOCK()

The following pattern has a race condition:

```sql
-- Do not use these two steps as an acquire mechanism
SELECT IS_FREE_LOCK('billing:invoice:9001');

-- Another session can acquire the lock between the two statements
SELECT GET_LOCK('billing:invoice:9001', 10);
```

`IS_FREE_LOCK()` only reflects state at the instant it was checked. Another session can grab the lock immediately afterward. Call `GET_LOCK()` directly and rely on its return value to decide whether to run the work.

## 7. RELEASE_ALL_LOCKS() and managing multiple locks

`RELEASE_ALL_LOCKS()` releases all named locks held by the current session and returns the number of lock holds released:

```sql
SELECT RELEASE_ALL_LOCKS() AS released_count;
```

This function can be useful in a dedicated test session or a cleanup routine that owns all named locks on the session.

Do not call `RELEASE_ALL_LOCKS()` in a connection pool or on a connection shared by multiple components. The session may hold locks belonging to another module; releasing everything breaks that module's coordination.

In applications, prefer tracking the list of lock names acquired by the current workflow and calling `RELEASE_LOCK()` for each name individually. Only use `RELEASE_ALL_LOCKS()` when guaranteed a dedicated session with no other lock owners on the same session.

## 8. Deadlocks when holding multiple named locks

Since MySQL 5.7.5, a session can hold multiple named locks. That introduces deadlock risk if multiple sessions acquire locks in different orders.

Example:

- Session A acquires `resource:A`, then waits for `resource:B`.
- Session B acquires `resource:B`, then waits for `resource:A`.
- A and B form a wait cycle.

MySQL can detect deadlocks while requesting named locks and abort one lock request with error `ER_USER_LOCK_DEADLOCK`. This does not automatically roll back the session's InnoDB transaction. The application must handle the error, release locks it already acquired, and decide whether to roll back/retry the transaction appropriately.

How to reduce deadlocks:

1. Define a global ordering for lock names, such as alphabetical string sort or ascending ID.
2. Have every code flow acquire locks in that exact same order.
3. Keep the number of concurrently held locks small.
4. Never wait on network I/O or user interaction while holding locks.
5. Use finite timeouts with a retry/backoff policy.
6. Release in `finally` as soon as work finishes.

When multiple sessions wait on the same named lock, grant order is not guaranteed to match the order in which they called `GET_LOCK()`. Never build business logic assuming FIFO ordering.

### 8.1. Avoid acquiring locks per row inside a single SQL query

Avoid calling `GET_LOCK()` as an expression evaluated across multiple rows, such as:

```sql
-- Not recommended: one statement can acquire multiple named locks
SELECT GET_LOCK(resource_name, 5)
FROM job_queue;
```

The optimizer does not guarantee expression evaluation order matches the row order an application expects. If the statement errors midway, named locks acquired before the error can remain held by the session. Rolling back the statement or transaction does not automatically release them.

Acquire each lock explicitly in application control flow in a deterministic order, record each successful acquisition, and release all of them in cleanup. If business logic must process multiple resources, consider grouping into a batch-level lock instead of acquiring an uncontrolled number of named locks.

## 9. How do named locks differ from row locks and table locks?

| Characteristic | `GET_LOCK()` | InnoDB row lock | `LOCK TABLES` |
|---|---|---|---|
| Target | Application-defined logical resource name | Index records and related gaps | Tables |
| Scope | One `mysqld` instance | Transaction on InnoDB data | Session and locked tables |
| Needs a transaction? | No | Yes, within transaction/locking read context | Has its own rules with autocommit and transactions |
| Released by COMMIT/ROLLBACK? | No | Yes | Do not reason like row locks; follows `LOCK TABLES` rules |
| Are non-conforming clients blocked? | No | Yes, if operations conflict on data | Conflicting accesses are restricted by table locks |
| Used to enforce constraints? | No | Does not replace constraints | Does not replace constraints |
| Useful when | Protecting logical work not tied to a single row | Protecting data rows inside a transaction | Table-wide locking needed for business/admin tasks |

Row lock example:

```sql
START TRANSACTION;

SELECT *
FROM inventory
WHERE sku = 'ABC-123'
FOR UPDATE;

UPDATE inventory
SET reserved_quantity = reserved_quantity + 1
WHERE sku = 'ABC-123';

COMMIT;
```

Row locks protect row data via InnoDB mechanisms and are released when the transaction finishes. `GET_LOCK()` protects a logical name agreed upon by clients; it can exist even when no corresponding row exists in any table.

If the goal is preventing two rows from sharing the same email, use a `UNIQUE` constraint. Never rely on named locks as the sole data protection layer because another client might not call the same lock name.

## 10. Named locks are not distributed locks

`GET_LOCK()` coordinates sessions only within a single MySQL server instance. If an application runs multiple independent MySQL primaries, each server can grant the same named lock to a session on that server.

Example:

- Worker A acquires `billing:daily-close` on MySQL primary A.
- Worker B acquires `billing:daily-close` on MySQL primary B.
- The two servers do not share a lock manager; both can grant the lock simultaneously.

Therefore, `GET_LOCK()` is not a distributed lock across multi-server clusters, not a leader-election mechanism, and provides no lease/fencing tokens. In failover scenarios, locks on the old server do not automatically transfer to the new primary.

If coordination across multiple nodes is needed, choose an appropriate distributed coordination mechanism with leases, fencing tokens, or consensus/transaction semantics per system requirements. If jobs run against a single `mysqld` and all workers connect to that exact instance, `GET_LOCK()` can be a simple option.

The named-lock functions `GET_LOCK()`, `RELEASE_LOCK()`, `IS_FREE_LOCK()`, `IS_USED_LOCK()`, and `RELEASE_ALL_LOCKS()` are unsafe for statement-based replication. MySQL emits warnings if these functions are called when `binlog_format` is set to `STATEMENT`. Never rely on replaying statements containing these functions to synchronize lock state between source and replica; locks exist solely on the instance where the function executed.

## 11. Monitoring named locks with Performance Schema

In MySQL 5.7+ and MySQL 8.0, named locks are implemented on top of the metadata locking subsystem. Locks appear in `performance_schema.metadata_locks` with `OBJECT_TYPE` equal to `USER LEVEL LOCK`.

Query held or waiting named locks:

```sql
SELECT
    ml.OBJECT_TYPE,
    ml.OBJECT_NAME,
    ml.LOCK_TYPE,
    ml.LOCK_DURATION,
    ml.LOCK_STATUS,
    ml.OWNER_THREAD_ID,
    th.PROCESSLIST_ID AS connection_id,
    th.PROCESSLIST_USER AS user_name,
    th.PROCESSLIST_HOST AS client_host
FROM performance_schema.metadata_locks AS ml
LEFT JOIN performance_schema.threads AS th
    ON th.THREAD_ID = ml.OWNER_THREAD_ID
WHERE ml.OBJECT_TYPE = 'USER LEVEL LOCK';
```

Notable columns:

| Column | Meaning |
|---|---|
| `OBJECT_TYPE` | `USER LEVEL LOCK` identifies a named lock from `GET_LOCK()` |
| `OBJECT_NAME` | Lock name |
| `LOCK_TYPE` | Metadata lock mode, typically `EXCLUSIVE` |
| `LOCK_DURATION` | Named locks normally have `EXPLICIT` duration |
| `LOCK_STATUS` | `GRANTED` or `PENDING` for acquired/waiting state |
| `OWNER_THREAD_ID` | Internal thread owning the lock request |
| `PROCESSLIST_ID` | Corresponding connection ID of the session |

`LOCK_DURATION = EXPLICIT` indicates the lock persists until explicitly released or session termination, matching `GET_LOCK()`'s lifecycle.

If one session calls `GET_LOCK()` multiple times with the same name, Performance Schema displays only one row for that name; subsequent acquisitions increment an internal counter. Thus, the row count in `metadata_locks` does not necessarily equal the number of `GET_LOCK()` calls.

You can check the owner using:

```sql
SELECT
    IS_USED_LOCK('billing:invoice:9001') AS owner_connection_id;
```

When investigating a long-held lock, correlate `connection_id` with the processlist and application logs to pinpoint which request acquired it without releasing.

## 12. Two-session experiment

Run the following steps in a lab database using two separate connection windows.

### 12.1. Session A acquires the lock

```sql
SELECT CONNECTION_ID() AS session_a_id;

SELECT GET_LOCK('lab:invoice:1001', 0) AS acquired;
```

Expected result is `1`. Session A now holds the lock.

### 12.2. Session B tries to acquire the same lock

```sql
SELECT CONNECTION_ID() AS session_b_id;

SELECT GET_LOCK('lab:invoice:1001', 3) AS acquired;
```

Session B waits up to three seconds and then receives `0` if Session A still holds the lock. Session B must not run the protected work.

### 12.3. Session A commits without releasing

In Session A:

```sql
START TRANSACTION;
SELECT 1;
COMMIT;

SELECT IS_USED_LOCK('lab:invoice:1001') AS owner_after_commit;
```

`IS_USED_LOCK()` still returns Session A's connection ID. `COMMIT` does not release the named lock.

### 12.4. Session A releases and Session B retries

In Session A:

```sql
SELECT RELEASE_LOCK('lab:invoice:1001') AS released;
```

Then in Session B:

```sql
SELECT GET_LOCK('lab:invoice:1001', 3) AS acquired;
```

If Session B receives `1`, it has acquired the lock. Finish the experiment with:

```sql
SELECT RELEASE_LOCK('lab:invoice:1001');
```

### 12.5. Observing Performance Schema

In a third session or before releasing, run the query from the previous section to observe the `USER LEVEL LOCK` row. You can keep the lock held in Session A and inspect `LOCK_STATUS`, `OBJECT_NAME`, and `PROCESSLIST_ID`.

Never run experiments with lock names used by a live system. Use a lab prefix to avoid colliding with applications.

## 13. Safe Java/JDBC integration

JDBC must invoke `GET_LOCK()` and `RELEASE_LOCK()` on the exact same physical connection. Use `PreparedStatement` to pass lock names:

```java
String lockName = "billing:invoice:" + invoiceId;
int timeoutSeconds = 10;

try (Connection connection = dataSource.getConnection()) {
    if (!acquireNamedLock(connection, lockName, timeoutSeconds)) {
        throw new IllegalStateException(
            "Resource is busy: " + lockName
        );
    }

    try {
        // This helper manages its own transaction and connection state.
        updateInvoiceInTransaction(connection, invoiceId);
    } finally {
        // Must release before returning the connection to the pool.
        releaseNamedLock(connection, lockName);
    }
}
```

Here `acquireNamedLock()` executes `SELECT GET_LOCK(?, ?)` and returns `true` only when the value is `1`; `releaseNamedLock()` executes `SELECT RELEASE_LOCK(?)` and verifies the result is `1`. `updateInvoiceInTransaction()` is responsible for commit/rollback and restoring autocommit state before returning. All three operations must use the same physical connection.

The two lock helpers can be implemented as:

```java
static boolean acquireNamedLock(
        Connection connection, String lockName, int timeoutSeconds
) throws SQLException {
    try (PreparedStatement ps =
             connection.prepareStatement("SELECT GET_LOCK(?, ?)")) {
        ps.setString(1, lockName);
        ps.setInt(2, timeoutSeconds);

        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                throw new SQLException("GET_LOCK returned no row");
            }
            int result = rs.getInt(1);
            if (rs.wasNull()) {
                throw new SQLException("GET_LOCK returned NULL");
            }
            return result == 1;
        }
    }
}

static void releaseNamedLock(
        Connection connection, String lockName
) throws SQLException {
    try (PreparedStatement ps =
             connection.prepareStatement("SELECT RELEASE_LOCK(?)")) {
        ps.setString(1, lockName);

        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                throw new SQLException("RELEASE_LOCK returned no row");
            }
            int result = rs.getInt(1);
            if (rs.wasNull() || result != 1) {
                throw new SQLException("Named lock was not released");
            }
        }
    }
}
```

In production applications, also handle rollback failures, release failures, and rules to evict the connection from the pool if session state becomes indeterminate. If release fails due to a dropped connection, never return a physical connection with unknown state to the pool for reuse.

Integration principles:

- Never acquire on connection A and release on connection B.
- Never close/return the connection before releasing.
- Never let the connection pool pick a different session for `RELEASE_LOCK()`.
- Use a finite timeout aligned with the request SLA.
- Never ignore `0` or `NULL` return values.
- Log non-sensitive resource names, wait time, connection ID, and acquire/release outcomes.
- If holding multiple named locks, track the list and acquisition counts to release the exact number of times.

## 14. Situations where GET_LOCK() should NOT be used

| Situation | Better alternative |
|---|---|
| Ensuring unique emails | `UNIQUE` constraint |
| Updating inventory on a row in a transaction | `SELECT ... FOR UPDATE` or atomic `UPDATE` |
| Coordinating workers across multiple MySQL primaries | Appropriate distributed lock/coordination service |
| Needing a lock that auto-expires after a duration | Lease mechanism with fencing tokens |
| Preventing all clients from writing to a table | Constraints, privileges, or appropriate data locks |
| Only checking whether a row exists | `EXISTS` or appropriate `SELECT` |
| Only locking one row inside a transaction | InnoDB row lock |

`GET_LOCK` fits when multiple application threads must coordinate voluntarily around a logical resource, especially when that resource lacks a clear single representative row. Never use it to replace database-enforced data integrity.

## 15. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Thinking `COMMIT` auto-releases `GET_LOCK` | Lock continues blocking other sessions | Call `RELEASE_LOCK()` explicitly |
| Releasing only in the success branch | Exceptions leave locks held long | Put cleanup in `finally` |
| Acquiring and releasing on two different connections | Owning session still holds the lock | Use the same physical connection |
| Returning connection to pool before releasing | Physical session can keep holding the lock | Release before logical close; evict if state is unknown |
| Not checking `GET_LOCK` return value | Runs work without owning the lock | Proceed only when result equals `1` |
| Calling `IS_FREE_LOCK` before `GET_LOCK` | Race condition between the two statements | Call `GET_LOCK` directly |
| Forgetting repeated acquisitions of the same name | One lock hold remains unreleased | Track acquire/release counts |
| Using generic lock names | Unrelated modules accidentally block each other | Namespace by application and resource |
| Waiting indefinitely | Requests/workers can hang forever | Use finite timeouts and backoff |
| Treating `GET_LOCK` as a distributed lock | Independent `mysqld` servers do not share locks | Use a distributed coordination system |
| Calling `RELEASE_ALL_LOCKS` on a shared connection | Releases locks owned by other modules | Release each owned lock name individually |
| Acquiring multiple locks in inconsistent orders | Can deadlock | Sort lock names in a global order |

## 16. Deployment and operational workflow

Before deploying:

1. Identify the logical resource to protect and define a unique naming convention.
2. Ensure names are non-empty, at most 64 characters, and application-namespaced.
3. Choose an appropriate timeout; never wait indefinitely for normal requests.
4. Clearly define behavior when `GET_LOCK` returns `0` or `NULL`.
5. Structure flow to acquire before the transaction, and release only after commit/rollback.
6. If using multiple locks, enforce a consistent acquisition order.
7. Verify all exit paths release in `finally`.
8. Test with connection pools, timeouts, exceptions, and dropped connections.

During operations:

1. Monitor named locks via `performance_schema.metadata_locks`.
2. Correlate `OWNER_THREAD_ID` with `PROCESSLIST_ID` and application logs.
3. Detect sessions holding `USER LEVEL LOCK` for abnormally long periods.
4. Check whether connection pools return connections while locks remain active.
5. Track `GET_LOCK` timeouts and `ER_USER_LOCK_DEADLOCK`.
6. Check `binlog_format` if binary logging uses `STATEMENT`.
7. Confirm failover mechanisms do not rely on named locks as distributed locks.
8. Kill a connection only after assessing other transactions and tasks running on that session.

## 17. Key takeaways

- `GET_LOCK(name, timeout)` requests an exclusive advisory lock by name on a single MySQL server instance.
- `GET_LOCK` returns `1` on acquisition, `0` on timeout, and `NULL` on error.
- `RELEASE_LOCK` returns `1` on successful release, `0` if the current session does not own the lock, and `NULL` if the lock name does not exist.
- Lock names are at most 64 characters, shared across schemas on the same server, and compared case-insensitively.
- Named locks are bound to the session, not to transactions; `COMMIT` and `ROLLBACK` do not release them.
- Locks are released explicitly or upon session termination; `GET_LOCK` does not provide an auto-expiring lease.
- Starting in MySQL 5.7.5, a session can hold multiple named locks; repeated acquisitions of the same name require matching release counts.
- Use `IS_FREE_LOCK` and `IS_USED_LOCK` for inspection; never use `IS_FREE_LOCK` in place of atomic acquisition.
- Named locks appear in Performance Schema `metadata_locks` with `OBJECT_TYPE = USER LEVEL LOCK` and typically `LOCK_DURATION = EXPLICIT`.
- `GET_LOCK` coordinates only clients following the convention; it does not replace row locks, unique constraints, or distributed locks.
- With connection pools, acquire and release on the same physical connection, releasing before returning the connection to the pool.
- Use finite timeouts, stable acquisition ordering, and cleanup in `finally` to minimize leaked locks and deadlocks.

`GET_LOCK` and `RELEASE_LOCK` are straightforward tools for coordinating work by logical resource within a single MySQL instance. When combined with a proper understanding of session lifecycles, transactions, constraints, and connection pool management, applications can prevent duplicate task execution without leaving advisory locks behind unexpectedly.

## References

- MySQL 8.0 Reference Manual — Locking Functions: https://dev.mysql.com/doc/refman/8.0/en/locking-functions.html
- MySQL 8.0 Reference Manual — The metadata_locks Table: https://dev.mysql.com/doc/refman/8.0/en/performance-schema-metadata-locks-table.html
- MySQL 8.0 Reference Manual — Metadata Locking: https://dev.mysql.com/doc/refman/8.0/en/metadata-locking.html
