# Waiting for Table Metadata Lock and Abandoned Transactions

An `ALTER TABLE` statement can hang for a very long time even when CPU is low, disk is healthy, and no `SELECT` query appears slow. The usual cause is another session holding a metadata lock on the table. That lock-holding session may be running a normal transaction, or it may have transitioned to `Sleep` while leaving its transaction open because the application forgot to commit or roll back. Without recognizing abandoned transactions, operators may see only the waiting DDL and a pile-up of newly timing-out queries.

This lesson belongs to the **Troubleshooting** chapter of the **DATABASE_MYSQL** module. On the path to mastering MySQL—from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, authorization, backup, and operations—understanding metadata locks explains why DDL blocks and why an apparently idle connection can still freeze schema changes.

## 1. What Is a Metadata Lock?

MySQL uses **metadata locks (MDLs)** to protect the metadata of database objects such as schemas, tables, views, stored programs, and other objects. When a statement accesses a table, MySQL acquires an appropriate metadata lock to prevent incompatible structural changes while the statement uses that object.

Examples:

- `SELECT` acquires a shared read metadata lock on the table.
- `INSERT`, `UPDATE`, and `DELETE` acquire metadata locks appropriate for write operations.
- `ALTER TABLE` needs an exclusive metadata lock during metadata modification phases.
- `DROP TABLE`, `RENAME TABLE`, and several other DDL operations also require metadata locks that conflict with active usage of the object.

MDL differs from InnoDB row locks. Row locks protect data rows within a transaction; metadata locks protect object definitions and metadata. A query may wait on zero row locks yet still hold an MDL, and DDL can be blocked by an MDL even when no rows are locked.

### Lifecycle of an MDL Inside a Transaction

For transactional tables like InnoDB, a metadata lock is acquired when a statement accesses the table and is normally held until the transaction ends. If a transaction executes `SELECT` and never calls `COMMIT` or `ROLLBACK`, the MDL persists even after the `SELECT` finishes.

Example:

~~~sql
-- Session A
SET autocommit = 0;
START TRANSACTION;

SELECT *
FROM customers
WHERE id = 1001;

-- Session A has not issued COMMIT or ROLLBACK yet.
-- The connection may return to Sleep state while the transaction stays open.
~~~

Meanwhile, Session B runs:

~~~sql
-- Session B
ALTER TABLE customers
  ADD COLUMN source_system VARCHAR(32) NULL;
~~~

`ALTER TABLE` requires an exclusive MDL to finalize the change. It must wait for compatible metadata locks from sessions currently holding locks on the table. Session A may no longer have an actively executing SQL statement, yet because its transaction has not ended, it still holds the lock.

When Session A executes `COMMIT` or `ROLLBACK`, the MDL is released and the DDL can proceed if no other blocker remains.

### Why Can One Waiting DDL Block Many Subsequent Queries?

When DDL requests an exclusive lock and queues behind existing locks, new metadata lock requests on the same object may queue behind that waiting DDL depending on lock manager priority rules. Thus, a single abandoned transaction can block a DDL; then the waiting DDL forces subsequent read/write queries to queue behind it. Users see the entire table "freeze", even though the original blocker is just one session.

Not every DDL wait stalls all queries. Impact depends on lock type, request order, and exact operations. Inspect the list of pending and granted locks rather than guessing from a single processlist row.

## 2. Distinguishing Metadata Locks from InnoDB Row Locks

These two lock types differ in origin and investigation tools:

| Indicator | Metadata Lock | InnoDB Row Lock |
|---|---|---|
| Protects | Object metadata/definition | Data rows and related index ranges |
| Typical scenario | `ALTER TABLE` waiting on an open `SELECT`/transaction | `UPDATE` waiting on another transaction modifying the same row |
| Processlist state | Often shows `Waiting for table metadata lock` | May show `Waiting for row lock` or other lock wait states |
| Observation source | `performance_schema.metadata_locks`, `sys.schema_table_lock_waits` | `performance_schema.data_locks`, `data_lock_waits` |
| Primary timeout | `lock_wait_timeout` | `innodb_lock_wait_timeout` for InnoDB row locks |
| How to release | End the session/transaction holding the MDL or finish the blocking statement | Commit/roll back the transaction holding the row lock |

Do not adjust `innodb_lock_wait_timeout` to fix DDL waiting on a metadata lock. These two timeouts govern different wait types.

`SHOW ENGINE INNODB STATUS` helps inspect InnoDB transactions and row locks, but it does not replace checking `performance_schema.metadata_locks` when investigating MDLs.

## 3. Identifying Statements Waiting on Metadata Locks

Start with the processlist:

~~~sql
SHOW FULL PROCESSLIST;
~~~

Look for sessions with states such as:

- `Waiting for table metadata lock`.
- Queries executing `ALTER TABLE`, `CREATE INDEX`, `DROP TABLE`, or `RENAME TABLE`.
- Other queries on the same table whose wait times climb after the DDL started.

The `Time` column in processlist shows time spent in the current state, not always total elapsed time since the application sent the request. Record `Id`, `User`, `Host`, `db`, `Command`, `Time`, `State`, and `Info`.

You can filter via Performance Schema:

~~~sql
SELECT
  PROCESSLIST_ID,
  PROCESSLIST_USER,
  PROCESSLIST_HOST,
  PROCESSLIST_DB,
  PROCESSLIST_COMMAND,
  PROCESSLIST_TIME,
  PROCESSLIST_STATE,
  LEFT(PROCESSLIST_INFO, 300) AS statement_sample
FROM performance_schema.threads
WHERE TYPE = 'FOREGROUND'
  AND PROCESSLIST_STATE LIKE '%metadata lock%'
ORDER BY PROCESSLIST_TIME DESC;
~~~

A waiting statement usually shows a clear processlist state. However, the blocker may be in `Sleep` state with empty `PROCESSLIST_INFO`. Therefore, filtering only for sessions whose state contains `metadata lock` finds waiters while potentially missing the blocker.

## 4. Inspecting Pending and Granted Locks

`performance_schema.metadata_locks` records granted and pending metadata locks. The query below lists locks on objects in the current schema:

~~~sql
SELECT
  ml.OBJECT_TYPE,
  ml.OBJECT_SCHEMA,
  ml.OBJECT_NAME,
  ml.LOCK_TYPE,
  ml.LOCK_DURATION,
  ml.LOCK_STATUS,
  t.PROCESSLIST_ID,
  t.PROCESSLIST_USER,
  t.PROCESSLIST_HOST,
  t.PROCESSLIST_DB,
  t.PROCESSLIST_COMMAND,
  t.PROCESSLIST_TIME,
  t.PROCESSLIST_STATE,
  LEFT(t.PROCESSLIST_INFO, 250) AS statement_sample
FROM performance_schema.metadata_locks AS ml
LEFT JOIN performance_schema.threads AS t
  ON t.THREAD_ID = ml.OWNER_THREAD_ID
WHERE ml.OBJECT_SCHEMA = DATABASE()
ORDER BY
  ml.OBJECT_NAME,
  CASE ml.LOCK_STATUS
    WHEN 'PENDING' THEN 0
    ELSE 1
  END,
  t.PROCESSLIST_TIME DESC;
~~~

Key columns:

- `OBJECT_TYPE`, `OBJECT_SCHEMA`, `OBJECT_NAME`: type and name of the locked object.
- `LOCK_TYPE`: type of MDL requested or held by the thread.
- `LOCK_DURATION`: lock lifetime, typically `STATEMENT`, `TRANSACTION`, or `EXPLICIT`.
- `LOCK_STATUS`: `GRANTED` means the lock has been acquired; `PENDING` means waiting.
- `OWNER_THREAD_ID`: Performance Schema thread owning the lock request.

When investigating, locate `PENDING` entries first, then inspect `GRANTED` locks on the same object. Not every `GRANTED` lock is a blocker; verify whether its lock type conflicts with the waiting lock and trace its transaction/session. Use the `sys` view in the next section to inspect MySQL's pre-joined waiting/blocking pairs.

If the query returns no data, check MDL instrumentation:

~~~sql
SELECT
  NAME,
  ENABLED,
  TIMED
FROM performance_schema.setup_instruments
WHERE NAME = 'wait/lock/metadata/sql/mdl';
~~~

If the instrument is disabled, enabling it must be evaluated against monitoring policies and operational permissions. Never toggle instrumentation in production during an incident without knowing its impact and rollback procedure.

## 5. Using `sys.schema_table_lock_waits` to Find Blockers

MySQL provides the `sys.schema_table_lock_waits` view to join waiting requests with threads holding blocking locks. If the view is available and readable, this is usually the fastest approach:

~~~sql
SELECT
  object_schema,
  object_name,
  waiting_pid,
  waiting_account,
  waiting_lock_type,
  waiting_lock_duration,
  waiting_query,
  waiting_query_secs,
  blocking_pid,
  blocking_account,
  blocking_lock_type,
  blocking_lock_duration,
  blocking_query,
  blocking_query_secs
FROM sys.schema_table_lock_waits
ORDER BY waiting_query_secs DESC;
~~~

Meaning:

- `waiting_pid`: connection ID of the waiting session.
- `waiting_query`: statement waiting on the metadata lock.
- `blocking_pid`: connection ID of the identified blocking session.
- `blocking_query`: current statement of the blocker; may be `NULL` if the blocker is sleeping.
- `blocking_query_secs`: elapsed time of the blocker's current statement, if any.

If `blocking_query` is `NULL` while `blocking_pid` still exists, inspect that connection's transaction. This is the classic signature of a transaction that ran a `SELECT` and left the session idle.

`sys` views are a convenience layer over Performance Schema. If the view is unavailable or restricted in your environment, query `metadata_locks` and `threads` directly.

## 6. Finding Abandoned InnoDB Transactions

`INFORMATION_SCHEMA.INNODB_TRX` shows active InnoDB transactions, including transactions with no currently executing SQL statement. Query:

~~~sql
SELECT
  trx_id,
  trx_state,
  trx_started,
  TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS trx_age_seconds,
  trx_mysql_thread_id AS connection_id,
  trx_query,
  trx_operation_state,
  trx_tables_locked,
  trx_rows_locked,
  trx_rows_modified,
  trx_isolation_level,
  trx_is_read_only
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Fields to inspect:

- `trx_started`: timestamp when the transaction began.
- `trx_age_seconds`: age of the transaction at observation time.
- `connection_id`: MySQL connection ID corresponding to the session.
- `trx_query`: current SQL statement; `NULL` appears when the session has no statement actively running.
- `trx_rows_locked` and `trx_rows_modified`: rows locked or modified per InnoDB state.
- `trx_operation_state`: current operation state if active.

A long-lived transaction is not automatically an abandoned transaction. A legitimate batch job may run long; a read-only transaction may be intentionally held. Always verify owner, request, timing, and business purpose.

### Joining Transactions with Processlist

~~~sql
SELECT
  it.trx_id,
  it.trx_started,
  TIMESTAMPDIFF(SECOND, it.trx_started, NOW()) AS trx_age_seconds,
  it.trx_state,
  it.trx_query,
  it.trx_rows_locked,
  it.trx_rows_modified,
  p.ID AS connection_id,
  p.USER,
  p.HOST,
  p.DB,
  p.COMMAND,
  p.TIME AS processlist_time,
  p.STATE,
  p.INFO
FROM information_schema.innodb_trx AS it
LEFT JOIN information_schema.PROCESSLIST AS p
  ON p.ID = it.trx_mysql_thread_id
ORDER BY it.trx_started;
~~~

A transaction with `trx_query` `NULL` and processlist `COMMAND = 'Sleep'` is a prime suspect. Yet never conclude solely from `Sleep`: the connection may be sitting briefly between statements inside a properly designed transaction. Trace the application request ID, pool metrics, transaction logs, and session owner.

### How Do Abandoned Transactions Happen?

Common causes:

- Code calls `setAutoCommit(false)` but forgets commit/rollback in an exception branch.
- A `@Transactional` method holds a transaction open while waiting on HTTP calls, message brokers, or file I/O.
- An application opens a transaction and returns a response early without running cleanup.
- Connections are held too long or leaked from the pool.
- A batch job processes a massive dataset inside one giant transaction.
- A DBA script runs `START TRANSACTION` to inspect data and forgets to finish it.
- Framework transaction management is bound to the wrong `DataSource` or transaction manager.
- A session uses `autocommit=0` and never closes the transaction after a `SELECT`.

As long as the transaction stays open, even a completed `SELECT` can retain its MDL on the read table. That is why a `Sleep` session sometimes blocks `ALTER TABLE`.

## 7. Identifying Which Session Is Blocking DDL

Correlation workflow:

1. From processlist, grab the connection ID of the DDL in `Waiting for table metadata lock`.
2. From `sys.schema_table_lock_waits` or `metadata_locks`, grab `blocking_pid` or `OWNER_THREAD_ID`.
3. Join the connection ID with `INNODB_TRX` to find transaction start time and state.
4. Join the thread with processlist to get user, host, command, and idle duration.
5. Check application logs or pool metrics to identify the owning service/request.
6. Verify the target table/object and preceding statements relate to the waiting DDL.

You can look up thread IDs and connection IDs from Performance Schema:

~~~sql
SELECT
  t.THREAD_ID,
  t.PROCESSLIST_ID,
  t.PROCESSLIST_USER,
  t.PROCESSLIST_HOST,
  t.PROCESSLIST_DB,
  t.PROCESSLIST_COMMAND,
  t.PROCESSLIST_TIME,
  t.PROCESSLIST_STATE,
  t.PROCESSLIST_INFO
FROM performance_schema.threads AS t
WHERE t.PROCESSLIST_ID IN (12345, 12346);
~~~

Replace `12345` and `12346` with the observed connection IDs. `THREAD_ID` is Performance Schema's internal ID; `PROCESSLIST_ID` is the connection ID used with `KILL`.

If the blocker is already in `Sleep`, `PROCESSLIST_INFO` usually no longer shows the earlier `SELECT`. Statement history may be available in `events_statements_history` or `events_statements_history_long` if consumers are enabled and events have not been overwritten. History is not guaranteed to hold the exact SQL that acquired the MDL; supplement with transaction age, application logs, and connection pool telemetry.

## 8. `lock_wait_timeout` vs. `innodb_lock_wait_timeout`

This confusion frequently prolongs incidents:

| Variable | Controls | Scope |
|---|---|---|
| `lock_wait_timeout` | Wait time for metadata locks | MDLs on metadata objects |
| `innodb_lock_wait_timeout` | Wait time for InnoDB row locks | InnoDB data locks |

In MySQL, `lock_wait_timeout` defaults to a very large value—typically 31,536,000 seconds (one year). Consequently, an `ALTER TABLE` can wait almost indefinitely unless given an explicit timeout.

You can bound the wait time specifically for the migration session:

~~~sql
SET SESSION lock_wait_timeout = 30;

ALTER TABLE customers
  ADD COLUMN source_system VARCHAR(32) NULL;
~~~

If the MDL is not granted within 30 seconds, the statement fails with a timeout instead of hanging indefinitely. This bounds lock acquisition wait time, not total DDL execution time once the lock is acquired.

`innodb_lock_wait_timeout` does not substitute for `lock_wait_timeout`. If the issue is `ALTER TABLE` waiting for a metadata lock, lowering `innodb_lock_wait_timeout` does not address the cause.

Set the timeout in the migration runner or in the exact same session executing the DDL. If `SET SESSION` runs on a different connection than `ALTER TABLE`, the timeout will not apply to the target statement.

## 9. Safe Handling When an Abandoned Transaction Is Found

Never start with `KILL`. First determine:

- Does the session belong to the production app, a batch job, or a DBA?
- How long has the transaction been open?
- Is it modifying data or read-only?
- Are rows locked or uncommitted changes present?
- Must the waiting DDL run immediately or can it be deferred?
- Does an active business request depend on that transaction?
- If rolled back, how large could the undo volume and rollback duration be?

Choose the action based on context:

### If the Transaction Belongs to the App and the Request Is Active

Contact the service owner or check request traces. If a legitimate request is nearly done, letting it finish may be safest. If code is hung, handle it at the application tier per runbook and assess impact before terminating the session.

### If the Transaction Is Truly Abandoned and Safe to End

Prefer letting the application commit/roll back via its transaction manager if the request is still controllable. If the session must be terminated, record connection ID, owner, transaction age, SQL/lock info, and approver per operational procedures.

### If the Waiting DDL Is Causing Query Queuing

If the DDL can wait, cancel the waiting DDL statement to relieve pressure on incoming requests; then resolve the blocker and reschedule the DDL with a bounded timeout. Canceling the waiting DDL does not automatically free the blocking transaction.

### If a Session Must Be Killed

There are two distinct statements:

~~~sql
-- Stops only the connection's currently executing statement
KILL QUERY 12345;

-- Disconnects the connection, ends the session, and triggers rollback of any open transaction
KILL CONNECTION 12345;
~~~

`KILL QUERY` on a `Sleep` session does not end the transaction; it only interrupts an active statement if one exists. To release an abandoned transaction, either the owner must `COMMIT`/`ROLLBACK` or you must terminate the connection after assessing impact.

`KILL CONNECTION` does not mean rollback finishes instantly. InnoDB may take considerable time to roll back prior changes; during rollback, associated resources and locks may remain held. Monitor state after intervening rather than repeatedly running `KILL` just because the DDL does not resume instantaneously.

Never run `KILL` on a connection ID taken from a stale snapshot. The connection ID might have ended and been reused; re-verify owner and state right before acting.

## 10. Procedure to Unblock a Stuck `ALTER TABLE`

Suppose a migration needs to add an index to `orders`, but processlist shows `Waiting for table metadata lock`.

**Step 1 — Record the DDL waiter**

Save connection ID, user, host, `ALTER` statement, wait duration, and start timestamp.

**Step 2 — Identify the object**

Extract schema/table from the DDL and `metadata_locks`. Do not rely only on the diagnostic session's `DATABASE()`, as the DDL may target a different schema.

**Step 3 — Locate the blocker**

Use `sys.schema_table_lock_waits`; if unavailable, match `PENDING` and `GRANTED` entries in `metadata_locks` for the same object.

**Step 4 — Inspect the transaction**

Check `INNODB_TRX` and processlist. If the blocker is `Sleep`, determine transaction age, host, and owning application.

**Step 5 — Assess impact**

Check whether incoming queries are queuing behind the DDL. Compare request timeouts, pool pending counts, and health of endpoints touching the table.

**Step 6 — Choose mitigation**

If the DDL is non-urgent and causing a queue, consider canceling the waiter. If the blocker is an abandoned transaction, coordinate with its owner to roll back or terminate the session safely.

**Step 7 — Re-run with timeout**

Once the blocker clears and the system stabilizes, re-run the migration with an appropriate `lock_wait_timeout`. Verify the schema after DDL completes.

**Step 8 — Monitor recovery**

Confirm no waiters remain in processlist, application queries resume normally, pool pending counts drop, and migration history records the accurate outcome.

Never automatically re-run `ALTER TABLE` after a timeout without verifying schema state. The DDL might have finished just before the client disconnected or failed on a subsequent step; check `SHOW CREATE TABLE` and migration history before retrying.

## 11. Preventing Abandoned Transactions in Applications

### Keep Transactions Short

Keep only database operations needing atomicity inside the transaction. Avoid HTTP calls, sending emails, waiting on user input, file uploads, or waiting on message brokers while a transaction is open.

Bad example:

~~~java
@Transactional
public void createOrder(CreateOrderRequest request) {
    Order order = repository.save(toOrder(request));

    // Calling an external service while the transaction and MDL remain held.
    paymentClient.authorize(order);

    orderRepository.markAuthorized(order.getId());
}
~~~

If the payment service takes 20 seconds, the database transaction can hold its connection, row locks, and MDLs for the entire wait.

A better design splits boundaries: write the initial state in a short transaction, commit, call the external service outside any transaction, and then open another short transaction to record the outcome. For cross-system consistency, use an outbox/saga or proper orchestration instead of holding SQL transactions open across network waits.

### Close Transactions on Every Path

With manual JDBC, use `try/catch/finally` or a transaction manager to guarantee commit/rollback:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        updateCustomer(connection);
        insertAuditRecord(connection);
        connection.commit();
    } catch (Exception error) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            error.addSuppressed(rollbackError);
        }
        throw error;
    }
}
~~~

In Spring applications, place `@Transactional` at proper business boundaries and let the transaction manager handle commit/rollback. Avoid catching and swallowing exceptions inside transactional methods if that prevents the framework from triggering rollback. Also verify self-invocation, propagation settings, and binding to the correct transaction manager/`DataSource`.

### Bound Batch Transactions

Do not hold a single transaction across hundreds of thousands or millions of rows unless full-batch atomicity is strictly required. Chunk batches by primary key or data range, commit per batch, persist checkpoints, and design idempotent retries. This limits MDL duration, undo log growth, and row lock lifetimes.

### Monitor Connection Pools

Track active, idle, pending connections, acquisition time, and leak detection. Pools can flag connections held too long, yet an idle connection returned to the pool does not automatically guarantee its transaction was closed. Ensure transactions are ended before logical connections return to the pool.

## 12. Preventing Production Disruptions from DDL

- Schedule DDL outside peak traffic when operations may require extended MDLs.
- Before migrating, check for long-running transactions and sessions idle in transaction.
- Set `lock_wait_timeout` on the DDL session to avoid indefinite waits.
- Dry-run on a replica/copy with production-like data and workload.
- Estimate rebuild time, temporary disk space, I/O, and replication impact.
- Use native online DDL or tools like `gh-ost`/`pt-online-schema-change` when appropriate, while still expecting brief metadata locks at key moments, especially table rename/swap during cutover.
- Monitor metadata locks throughout the migration, not just at the start.
- Have a plan to abort the DDL waiter if it builds a queue impacting the application.

Online DDL reduces DML blocking in many scenarios but does not eliminate all MDL requirements. An old transaction can stall both the start and completion phases of DDL. Online schema change tools also require metadata locks during cutover operations.

## 13. Proactive Transaction and Metadata Lock Monitoring

Set alerts based on transaction age and lock state, not just connection counts.

Useful metrics:

- Oldest active InnoDB transaction.
- Count of open transactions with `trx_query` `NULL`.
- Count of `PENDING` metadata locks per object.
- Age of MDL waiters.
- Count of `Sleep` sessions holding open transactions.
- Active/pending counts in connection pools.
- Requests waiting on database and p95/p99 latency.
- Counts of DDL timeouts and lock wait timeouts.

You can retrieve the oldest transactions:

~~~sql
SELECT
  trx_mysql_thread_id AS connection_id,
  trx_started,
  TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS age_seconds,
  trx_state,
  trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started
LIMIT 20;
~~~

Alert thresholds must fit workload characteristics. A 5-minute reporting transaction may be legitimate; an OLTP transaction usually lasts milliseconds. Categorize alerts by application account, schema, service, and job type rather than applying a single global threshold.

You can use Performance Schema/`sys` views to detect waiters and emit alerts containing object, waiting PID, blocking PID, and transaction age. Never auto-kill blockers solely for crossing a threshold; automation should only gather data and alert unless the organization has an approved, tested remediation policy.

## 14. Symptom and Investigation Table

| Symptom | Likely Cause | Next Evidence to Check |
|---|---|---|
| `ALTER TABLE` in `Waiting for table metadata lock` | Another transaction holds a conflicting MDL | `sys.schema_table_lock_waits`, `metadata_locks` |
| Blocker has `COMMAND=Sleep` | Session is idle, but its transaction may still be open | `INNODB_TRX`, transaction logs, connection owner |
| Many `SELECT`s start waiting after DDL waits | Lock queue building on the same object | Processlist over time, `PENDING`/`GRANTED` MDLs |
| `innodb_lock_wait_timeout` has no effect on DDL | Waiting on MDL, not row locks | Check `lock_wait_timeout` |
| `KILL QUERY` does not free a `Sleep` blocker | No active statement to interrupt; transaction stays open | Close transaction or `KILL CONNECTION` after assessment |
| DDL still waits after `KILL CONNECTION` | Rollback still in progress or another blocker exists | Monitor `INNODB_TRX`, `metadata_locks` |
| DDL timed out yet schema seems changed | Actual schema state needs verification | `SHOW CREATE TABLE`, `information_schema`, migration history |

## 15. Incident Checklist

**When a waiting DDL is detected**

- [ ] Recorded DDL statement, connection ID, object, and wait duration.
- [ ] Captured `SHOW FULL PROCESSLIST`.
- [ ] Checked `sys.schema_table_lock_waits`.
- [ ] If needed, inspected `performance_schema.metadata_locks` and `threads`.
- [ ] Identified `GRANTED` locks on the same object.
- [ ] Checked `information_schema.innodb_trx` for long-running transactions.
- [ ] Checked whether the blocker is a `Sleep` session.
- [ ] Traced the owner via host, account, application trace, and pool metrics.
- [ ] Assessed whether the DDL waiter is queuing incoming requests.

**Before terminating a session**

- [ ] Re-verified connection ID and owner right before acting.
- [ ] Checked how many rows the transaction modified and its business impact.
- [ ] Coordinated with the owner to commit/roll back if possible.
- [ ] Ran `KILL CONNECTION` only after assessing rollback and per runbook approval.
- [ ] Monitored until rollback completed and locks were truly released.

**After recovery**

- [ ] Verified the DDL either completed or was cleanly aborted.
- [ ] Checked `SHOW CREATE TABLE` and migration history.
- [ ] Confirmed no related waiters remain in processlist.
- [ ] Confirmed pool pending, latency, and error rates returned within thresholds.
- [ ] Documented root cause and added transaction/MDL alerts.

## 16. Key Takeaways

- Metadata locks protect table and object metadata; they are distinct from InnoDB row locks.
- InnoDB transactions can hold MDLs until `COMMIT`/`ROLLBACK`, even when the session is in `Sleep`.
- DDL like `ALTER TABLE` can wait on old transactions; new requests on the same object can then queue behind it.
- Use `sys.schema_table_lock_waits` and `performance_schema.metadata_locks` to find waiters and blockers.
- Use `information_schema.innodb_trx` to find long or idle transactions; join with processlist to identify owners.
- `lock_wait_timeout` governs MDLs; `innodb_lock_wait_timeout` governs InnoDB row locks.
- `KILL QUERY` does not end an idle transaction; `KILL CONNECTION` triggers rollback, and rollback takes time.
- Never kill a session based solely on `Sleep` state or transaction age; verify owner and impact first.
- Keep transactions short, never wait on external services inside transactions, and commit/roll back on all branches.
- Online DDL and schema change tools can still require MDLs during critical phases.

When a DDL blocks, find the session holding the metadata lock and inspect its transaction before intervening. Recording waiter, blocker, transaction age, owner, and post-mitigation state resolves the immediate incident cleanly while exposing recurring transaction management bugs.

## References

- [MySQL 8.0 Reference Manual: Metadata Locking](https://dev.mysql.com/doc/refman/8.0/en/metadata-locking.html)
- [MySQL 8.0 Reference Manual: Performance Schema metadata_locks Table](https://dev.mysql.com/doc/refman/8.0/en/performance-schema-metadata-locks-table.html)
- [MySQL 8.0 Reference Manual: sys.schema_table_lock_waits View](https://dev.mysql.com/doc/refman/8.0/en/sys-schema-table-lock-waits.html)
- [MySQL 8.0 Reference Manual: INFORMATION_SCHEMA INNODB_TRX](https://dev.mysql.com/doc/refman/8.0/en/information-schema-innodb-trx-table.html)
- [MySQL 8.0 Reference Manual: lock_wait_timeout](https://dev.mysql.com/doc/refman/8.0/en/server-system-variables.html#sysvar_lock_wait_timeout)
- [MySQL 8.0 Reference Manual: InnoDB Lock Wait Timeout](https://dev.mysql.com/doc/refman/8.0/en/innodb-parameters.html#sysvar_innodb_lock_wait_timeout)
- [MySQL 8.0 Reference Manual: KILL Statement](https://dev.mysql.com/doc/refman/8.0/en/kill.html)
