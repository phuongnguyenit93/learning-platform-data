# Impact Assessment Before KILL QUERY, KILL CONNECTION, or Restart

When MySQL slows down, a query hangs, or connections surge abnormally, DBAs often consider stopping a statement, terminating a session, or restarting the server. Each action carries a different blast radius. Picking the wrong session can lose an in-flight transaction, prolong a rollback, delay lock release, or disrupt the entire application. Restarting affects every client, replica, background job, and dependent service.

This lesson establishes an impact-assessment procedure before running **KILL QUERY**, **KILL CONNECTION**, or restarting MySQL. The focus is on identifying the exact target, understanding active transactions and held locks, estimating blast radius, picking the least-disruptive action, and verifying the system afterward.

Within **DATABASE_MYSQL**, this assessment builds on table design, data types, keys, SQL queries, indexes, transactions, and concurrency control. Combine it with reading execution plans, query tuning, privilege management, backups, and operational knowledge of relational database architecture.

## 1. Principles Before Intervening

Never run `KILL` or restart merely because one processlist row shows a high elapsed time. Answer these questions first:

1. Which session is causing the problem? Is it a blocker, victim, read query, write query, or system thread?
2. Which database is the statement running against, which user/service initiated it, and which business flow owns it?
3. Does the session hold an open transaction? How many rows has it modified, which locks does it hold, and how long could rollback take?
4. If the statement or session is stopped, will the application retry? Could retries cause duplicate transactions or indeterminate outcomes?
5. Will it affect replication, backups, migrations, failover, or operational jobs?
6. Is there a lower-impact way to shed load, stop the job from the application side, or let the transaction finish?

A sound intervention workflow has four steps:

~~~mermaid
flowchart TD
    A[Incident detected] --> B[Collect state and identify session]
    B --> C[Assess transaction, locks, and blast radius]
    C --> D{Required intervention level?}
    D -->|Single statement| E[KILL QUERY]
    D -->|Impacting session| F[KILL CONNECTION]
    D -->|Server/topology needs recovery| G[Restart per runbook]
    E --> H[Monitor rollback, locks, and application]
    F --> H
    G --> I[Check recovery, replication, and clients]
    H --> J[Verify and document]
    I --> J
~~~

Gather evidence before intervening. Record timestamp, processlist ID, user, host, database, SQL statement, transaction state, lock waits, and related metrics. Even when immediate action is urgent, record at minimum identifying details and rationale.

## 2. Identifying the Exact Session and Statement

### 2.1. Inspecting the Process List

Basic command:

~~~sql
SHOW FULL PROCESSLIST;
~~~

Use `FULL` to view the entire SQL statement in `Info` without truncation. Key columns:

| Column | Meaning | Operational Question |
|---|---|---|
| `Id` | Connection processlist ID | Is this the exact session we intend to act on? |
| `User` | MySQL account | Does it belong to an app, DBA, backup, or replication? |
| `Host` | Client host and source port | Which instance/pod/job does it map to? |
| `db` | Default database | Which schema is affected? |
| `Command` | Command type, usually `Query` or `Sleep` | Actively running SQL or idle? |
| `Time` | Seconds spent in the current state | How long has the query or idle state lasted? |
| `State` | Detailed thread state | Waiting on locks, sending data, or executing? |
| `Info` | Current SQL statement if any | Does it modify data or run DDL? |

You can filter active sessions:

~~~sql
SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE, INFO
FROM INFORMATION_SCHEMA.PROCESSLIST
WHERE COMMAND <> 'Sleep'
ORDER BY TIME DESC;
~~~

`TIME` is not always total time since connection creation. For threads running queries, it usually reflects duration in the current state. For `Sleep` sessions, it reflects idle duration in that state. Cross-check application logs and query metrics for full context.

Never pick a target solely by largest `TIME`. A long `Sleep` session can be completely normal; conversely, an open transaction sitting in `Sleep` can hold locks and cause major disruption.

### 2.2. Distinguishing Processlist ID from Performance Schema Thread ID

`KILL` takes the **processlist ID**, not Performance Schema's internal `THREAD_ID`. Map between the two IDs as follows:

~~~sql
SELECT
  THREAD_ID,
  PROCESSLIST_ID,
  PROCESSLIST_USER,
  PROCESSLIST_HOST,
  PROCESSLIST_DB,
  PROCESSLIST_COMMAND,
  PROCESSLIST_TIME,
  PROCESSLIST_STATE,
  PROCESSLIST_INFO
FROM performance_schema.threads
WHERE TYPE = 'FOREGROUND'
ORDER BY PROCESSLIST_TIME DESC;
~~~

Right before running `KILL`, re-verify `PROCESSLIST_ID`, user, host, and statement. A connection may have ended and its processlist ID could be reused later; never run `KILL` from a stale list without re-checking the target.

### 2.3. Identifying Workload Type

Classify which workload the session belongs to:

- API request or application worker.
- Reporting/BI query or ad-hoc query.
- Migration, DDL, index build, or backfill.
- Backup/restore or administrative utility.
- Replication receiver/applier.
- Event scheduler, monitoring, or DBA account.
- Administrative session investigating an incident.

The same SQL statement can carry vastly different impact depending on its business context. For instance, one `UPDATE` might be a safely repeatable backfill job, while another might be an irreversible payment ledger entry.

## 3. Assessing Transactions and Locks Before KILL

### 3.1. Checking InnoDB Transactions

List open transactions:

~~~sql
SELECT
  trx_id,
  trx_state,
  trx_started,
  TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS trx_age_seconds,
  trx_mysql_thread_id AS processlist_id,
  trx_rows_locked,
  trx_rows_modified,
  trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Key fields:

- `trx_started`: timestamp when the transaction began.
- `trx_state`: transaction state.
- `trx_mysql_thread_id`: corresponding processlist ID.
- `trx_rows_locked`: number of rows currently locked per InnoDB state.
- `trx_rows_modified`: number of rows modified within the transaction.
- `trx_query`: current SQL statement; may be `NULL` if idle between statements.

`trx_rows_modified` indicates the scale of work to roll back, though it is not an exact measure of rollback duration. Undo logs, index counts, I/O, contention, and storage health all affect actual rollback time.

A transaction may modify many rows and then go to `Sleep` while the application leaves the transaction open. That session shows no running query yet continues holding row locks that block other transactions.

### 3.2. Finding Blockers and Victims

In lock wait situations, distinguish:

- **Waiting session (victim):** transaction waiting for a lock.
- **Blocking session (blocker):** transaction holding the lock preventing others from advancing.

View lock wait overview via the `sys` schema:

~~~sql
SELECT
  wait_age,
  locked_table,
  locked_index,
  waiting_pid,
  waiting_query,
  blocking_pid,
  blocking_query,
  blocking_trx_age,
  blocking_trx_rows_locked,
  blocking_trx_rows_modified
FROM sys.innodb_lock_waits
ORDER BY wait_age_secs DESC;
~~~

If the `sys` schema or view is unavailable, query Performance Schema directly:

~~~sql
SELECT
  REQUESTING_ENGINE_TRANSACTION_ID AS waiting_trx_id,
  REQUESTING_THREAD_ID AS waiting_thread_id,
  BLOCKING_ENGINE_TRANSACTION_ID AS blocking_trx_id,
  BLOCKING_THREAD_ID AS blocking_thread_id
FROM performance_schema.data_lock_waits;
~~~

Join with `performance_schema.data_locks`, `performance_schema.threads`, and `information_schema.innodb_trx` to map sessions, tables, indexes, and transactions.

Killing the victim is not always right. Stopping a waiting query usually fails only that request while the blocker stays and other sessions keep waiting. Conversely, killing the blocker can unblock many sessions, yet forces rolling back the blocker's transaction—generating extra I/O and delay. Pick the target based on recovery goals and business impact.

### 3.3. Checking Metadata Locks

DDL like `ALTER TABLE`, `RENAME TABLE`, or `DROP TABLE` can wait on metadata locks held by other transactions. While DDL waits, incoming queries can also pile up in the lock queue.

Inspect metadata locks for a schema:

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
  t.PROCESSLIST_INFO
FROM performance_schema.metadata_locks AS ml
LEFT JOIN performance_schema.threads AS t
  ON t.THREAD_ID = ml.OWNER_THREAD_ID
WHERE ml.OBJECT_SCHEMA = 'appdb'
  AND ml.LOCK_STATUS IN ('PENDING', 'GRANTED')
ORDER BY ml.OBJECT_NAME, ml.LOCK_STATUS;
~~~

Output shows pending (`PENDING`) and granted (`GRANTED`) locks. Match rows on the same object to locate the transaction or statement holding the lock. With many objects and sessions, combine process list, transactions, and migration logs to trace the wait chain.

Before killing a waiting DDL, check whether that waiting DDL itself is queuing incoming requests. You may cancel the waiting DDL first to relieve pressure, then handle the transaction holding the metadata lock in a controlled window.

### 3.4. Saving InnoDB Status

When locks or rollbacks are unclear, also save:

~~~sql
SHOW ENGINE INNODB STATUS\G
~~~

The `TRANSACTIONS` section and deadlock details help identify transactions, locks, and recent activity. This is a point-in-time snapshot; if the incident evolves quickly, capture multiple timestamped samples to compare.

## 4. Estimating Blast Radius

Before stopping a session, evaluate at least five impact areas.

### 4.1. Data and Transactions

- Is the query read-only or modifying data?
- Is the transaction using autocommit or an explicit transaction?
- How many rows are modified and locked?
- Will stopping the query leave the transaction open?
- Did the application already receive the commit response?
- Can the business operation be verified or replayed safely with an idempotency key?

If a client loses connection during `COMMIT`, the outcome is indeterminate from the application's viewpoint: the server may have committed while the response never arrived. Never blindly retry write commands.

### 4.2. Locks and Cascading Effects

One blocker can stall dozens or hundreds of transactions. Stopping the blocker can shrink the queue, yet the blocker's rollback may continue holding resources for some time.

Count waiting sessions and inspect affected tables/records. Evaluate both row locks and metadata locks; do not rely solely on `Locked` state in the process list.

### 4.3. Load and Resources

- Is the query consuming heavy CPU or I/O?
- Is it creating temporary tables, sorting, or scanning whole tables?
- Will stopping the query free resources immediately or wait for rollback?
- Will restarting trigger a simultaneous reconnect surge (connection storm) from clients?
- Does storage have enough space for rollback, crash recovery, and binary logs?

If the root cause is a slow query missing an index, `KILL` provides only temporary relief without fixing the problem. Save the SQL and execution plan, then inspect indexes, cardinality, predicates, and statistics.

### 4.4. Applications and Business Operations

Identify the session owner via user/host, request ID, application name, or logs. Evaluate:

- Which APIs will return errors?
- Will workers retry automatically?
- Do batch jobs have checkpoints to resume?
- Are write requests idempotent?
- Does one transaction update multiple tables or invoke external services?
- Could the action disrupt an active migration, backup, or reconciliation job?

### 4.5. Replication and Availability

If the target is the primary:

- Are replicas healthy and caught up?
- Has the stopped transaction already been written to the binary log?
- Will `KILL` or restart spike replica lag?
- Is there a risk of triggering automatic failover during the action?

If the target is a replica:

- Is the session a replication applier/receiver?
- Will stopping the thread or restarting stop the replica from applying logs?
- Do required binary logs remain within retention?
- Will it impact read traffic routed to that replica?

Never `KILL` system or replication threads merely for long runtime. Identify the topology and follow the appropriate replication/cluster administration runbook.

## 5. `KILL QUERY`: Stopping the Current Statement

### 5.1. Syntax and Behavior

Syntax:

~~~sql
KILL QUERY 12345;
~~~

`12345` is the processlist ID of the target connection.

`KILL QUERY` asks MySQL to stop the statement currently executing on that session. The connection remains open so the client can issue subsequent statements. This fits cases where a specific statement must stop while preserving the session.

However, do not assume every effect of the session disappears:

- The interrupted statement may still need to roll back its own partial work.
- If the session is inside an explicit transaction, that transaction can stay open.
- Locks acquired by earlier statements in the transaction can remain held.
- The application must handle the statement error and explicitly roll back or close the transaction.
- MySQL may take time before the thread reaches a safe cancellation checkpoint.

`KILL QUERY` does not guarantee instantaneous termination in every state. Some operations need time to abort cleanly or complete cleanup.

### 5.2. When to Consider `KILL QUERY`

- A reporting or ad-hoc query runs too long and stopping just the statement suffices.
- A `SELECT` drives high CPU/I/O without needing to tear down the entire session.
- A DDL waiting on a metadata lock is building a request queue behind itself.
- A statement was run by mistake while the session must stay open for error handling or explicit rollback.

Before running it, verify processlist ID, SQL, user, host, transaction, and owner. If the query belongs to a critical write transaction, coordinate with the owner or follow the runbook on how to handle the remaining open transaction.

### 5.3. Checking After `KILL QUERY`

~~~sql
SHOW FULL PROCESSLIST;
~~~

Verify:

- Whether the target SQL disappeared.
- Whether the connection remains alive or closed.
- Whether the transaction still appears in `information_schema.innodb_trx`.
- Whether lock-waiting sessions resumed.
- Whether the application rolled back or handled the error properly.

If the session still holds an open transaction, resolve that transaction with the owner or business procedure. Never assume locks cleared merely because the query vanished from the process list.

## 6. `KILL CONNECTION`: Terminating the Entire Session

### 6.1. Syntax and Behavior

Syntax:

~~~sql
KILL CONNECTION 12345;
~~~

Short form:

~~~sql
KILL 12345;
~~~

When omitted, `KILL` defaults to `KILL CONNECTION`.

This command terminates the session. Upon termination, any uncommitted InnoDB transaction rolls back. Rollback can take considerable time if the transaction modified many rows or updated many indexes.

Impacts to account for:

- Physical connection closes; the application receives connection or execution errors.
- Uncommitted transactions roll back.
- Locks are released only as termination/rollback releases them; never assume all locks vanish the instant `KILL` returns.
- Connection pools may open replacement connections.
- Applications may retry, so evaluate duplicate-write risks.
- The session might be running a critical backup, migration, or admin task.

### 6.2. When to Consider `KILL CONNECTION`

- An abandoned session holds an open transaction and locks long-term and the owner cannot close it.
- A connection is hung or orphaned by the application, after confirming no critical work must be preserved.
- The entire session must be ended to free resources and transaction rollback impact has been assessed.
- A misbehaving session must be isolated per incident response procedures.

If the goal is merely stopping a `SELECT` while keeping the session, `KILL QUERY` has a narrower blast radius. If a session holds a blocking transaction, `KILL CONNECTION` may be required once rollback cost is accounted for.

### 6.3. Monitoring Rollback

After `KILL CONNECTION`, inspect the process list and active transactions:

~~~sql
SHOW FULL PROCESSLIST;

SELECT
  trx_id,
  trx_state,
  trx_started,
  trx_mysql_thread_id,
  trx_rows_locked,
  trx_rows_modified,
  trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Look for rollback states in the process list or InnoDB status. Monitor CPU, I/O, lock waits, and rollback duration. Large transactions continue consuming resources after session termination is requested.

Never repeatedly `KILL` a vanished ID or a new ID without re-verifying. The old session may have exited and its ID could already be reassigned.

## 7. Restarting MySQL: Server-Wide Impact

### 7.1. Restart Has Far Broader Impact Than Killing One Session

A restart affects every connection and operation on the instance:

- Every connected client is disconnected.
- Running queries are aborted.
- Uncommitted transactions must roll back or process during shutdown/recovery.
- Connection pools must rebuild all connections.
- Replicas lose connection and must catch up once the server returns.
- Backups, migrations, events, and background jobs are interrupted.
- Applications can trigger a connection storm when all instances reconnect simultaneously.
- If the instance is a primary or cluster member, HA topology may fail over or lose quorum.

Restarting may be necessary when the server process is unresponsive, configuration changes require a restart, a plugin/component is wedged, or recovery runbooks call for it. Restarting does not fix missing indexes, long transactions, lock contention, or buggy retry loops.

### 7.2. Pre-Restart Checks

**Role and topology**

- Confirm exact instance, hostname, port, and environment.
- Confirm whether the node is primary, replica, standalone, or a Group Replication / InnoDB Cluster member.
- Check automatic failover, quorum, Router, and standby nodes.
- Confirm the old primary will not continue accepting writes if topology fails over.

**Transactions and workload**

- Capture process list, transactions, lock waits, and active queries.
- Identify active backups, restores, migrations, DDL, or batch jobs.
- Halt incoming workloads or switch applications to maintenance mode if required by runbook.
- Drain requests and let short transactions finish when possible.
- Identify transactions that could be lost or need reconciliation.

**Recoverability**

- Verify the latest backup and restore validation.
- Verify binary logs/GTIDs and retention if PITR or resync is needed.
- Check disk space, logs, and filesystem health.
- Read the error log to verify whether a restart helps or worsens the incident.
- Estimate InnoDB recovery duration from data volume and recent drills.

**Applications and connections**

- Check timeouts and reconnect policies on HikariCP/JDBC.
- Verify whether retries are idempotent.
- Prepare health/readiness checks and phased traffic ramp-up.
- Ensure connection pools do not concentrate all reconnect retries at the exact same instant.

### 7.3. Controlled Restart

Exact steps depend on OS, managed service, and topology. On self-managed MySQL, controlled shutdown uses service management or `mysqladmin shutdown`, followed by starting via the environment's service manager using the exact service unit name.

General operational sequence:

1. Announce the maintenance window per internal process and record the operator.
2. Put applications in maintenance mode or stop new writes.
3. Drain connections and inspect remaining open transactions.
4. Confirm replica/HA readiness if a role switch will occur.
5. Execute graceful shutdown per runbook.
6. Start MySQL and tail the error log until recovery completes.
7. Verify server status, data, replication, and privileges.
8. Test applications under limited traffic.
9. Gradually ramp up traffic while monitoring errors, latency, and connection counts.

Never run restart commands directly on a production node without confirming the exact node and topology impact. On managed MySQL services, restarts may be orchestrated via the provider's control plane; follow the service's runbook and failover mechanisms.

### 7.4. When Can Restarting Make Things Worse?

- Disk full: the server may fail to start or write required logs.
- Data corruption or tablespace errors: restarting does not repair damaged data and can complicate forensics.
- Large transaction rollback: crash recovery after restart can be prolonged.
- Primary with unhealthy replicas: restarting can cause downtime without a healthy standby.
- Uncontrolled application retries: when the server comes back up, flooded retries cause immediate overload.
- Auto-starting buggy jobs/queries: right after restart, the offending workload can immediately re-trigger the incident.

When corruption, data loss, or storage faults are suspected, capture logs and evidence before restarting; follow data-incident response procedures instead of repeated restarts.

## 8. Comparing the Options

| Action | Scope | Transaction | Connection | Primary Risk |
|---|---|---|---|---|
| Wait for query completion | Single statement | Can commit normally | Preserved | Incident continues while waiting |
| `KILL QUERY` | Current statement | Statement aborted; explicit transaction may stay open | Session kept | Locks from earlier statements in the transaction may persist |
| `KILL CONNECTION` | Entire session | Uncommitted transaction rolls back | Session closed | Long rollback, app retries, lost session state |
| Restart MySQL | Entire instance | Queries aborted; uncommitted transactions roll back/recover | All connections dropped | Service outage, replica lag, reconnect storm, long recovery |

Choose the action matching your goal:

- Need to stop a statement while keeping the session: consider `KILL QUERY`.
- Need to end a session holding a transaction: consider `KILL CONNECTION`, after factoring rollback cost.
- Need to recover a wedged instance or apply a restart-required change: follow the restart runbook and check HA.
- If it is simply a slow query, investigate execution plan, indexes, data, locks, and load first.

## 9. Real-World Scenario Matrix

| Scenario | What to Verify | Typical Remediation Path |
|---|---|---|
| Reporting `SELECT` doing full scan, spiking CPU | Owner, SQL, execution plan, remaining work, user impact | Ask owner to stop; if needed, `KILL QUERY` that statement; then optimize indexes/filters |
| Long `Sleep` session with no transaction | Is it a normal pooled idle connection? | Do not `KILL` solely for `Sleep`; inspect pool sizing and timeouts |
| `Sleep` session with open transaction holding row locks | `innodb_trx`, transaction age, modified rows, owner | Contact owner; if uncloseable and locks must clear, evaluate `KILL CONNECTION` and rollback |
| Many queries waiting on one blocking transaction | Waiting/blocking graph, affected session count, rollback cost | Identify blocker; stop upstream job or terminate blocker per runbook |
| `ALTER TABLE` waiting on metadata lock | Is DDL building a queue? Which transaction holds the MDL? | Consider canceling waiting DDL first, then handle blocker in a controlled window |
| Replica applier errored | Channel, SQL error, GTID, data impact | Follow replication runbook; never `KILL` threads arbitrarily |
| MySQL unresponsive and health checks failing | Error log, CPU, disk, network, HA, and node state | Evaluate failover/restart per runbook; preserve evidence before acting |
| Server reports disk full | Filesystem, binlogs, `tmpdir`, data volume | Free or expand space per runbook; restarting does not free disk |
| Connection count spikes right after restart | Pool reconnects, retries, `max_connections`, readiness | Pace rollouts/reconnects, check pools, and ramp traffic gradually |

These paths are starting points for investigation, not automatic commands. Always verify target and post-conditions before executing.

## 10. Safe Decision and Execution Procedure

### 10.1. Before Acting

- [ ] Confirmed environment, hostname, port, and instance role.
- [ ] Saved `SHOW FULL PROCESSLIST`.
- [ ] Recorded target processlist ID, user, host, database, and SQL.
- [ ] Cross-checked `performance_schema.threads` if pulling from Performance Schema.
- [ ] Checked `information_schema.innodb_trx`.
- [ ] Checked row lock waits and metadata locks if relevant.
- [ ] Identified owner and business flow.
- [ ] Estimated affected waiting sessions and rollback cost.
- [ ] Checked replication, backups, migrations, and HA state.
- [ ] Chose the narrowest action meeting the goal.

### 10.2. During Execution

1. Re-verify processlist ID immediately before `KILL`.
2. Confirm user/host/SQL still match the intended target.
3. Record operator, timestamp, and rationale.
4. Execute the right statement: `KILL QUERY` or `KILL CONNECTION`.
5. If restarting, follow the exact runbook for your topology and service type.
6. Never repeat `KILL` or restart blindly without checking the prior action's state.

For example, after confirming session ID 12345 is running an ad-hoc query to stop:

~~~sql
KILL QUERY 12345;
~~~

If session 12345 holds a blocking transaction the owner cannot close and rollback cost is acceptable:

~~~sql
KILL CONNECTION 12345;
~~~

Both commands are syntax examples only. Never copy illustrative IDs into production; always fetch fresh IDs from the process list and re-verify.

### 10.3. After Acting

**After `KILL QUERY`**

- Confirm the statement stopped.
- Check whether the session remains alive.
- Check whether the transaction remains open and locks remain held.
- Confirm the application rolled back or handled the error properly.
- Monitor previously waiting sessions.

**After `KILL CONNECTION`**

- Confirm the session ended.
- Monitor rollback until completion and confirm locks release.
- Check application/pool replacement connections.
- Reconcile business state if any commit outcome was indeterminate.
- Monitor retry errors, duplicate keys, and connection counts.

**After Restart**

- Confirm MySQL booted and finished crash recovery.
- Check error log, version, uptime, and `read_only`/`super_read_only` status.
- Check databases, tablespaces, and critical queries.
- Check GTIDs, replication channels, lag, and HA state.
- Check application reconnects, connection pools, and health checks.
- Ramp traffic gradually and monitor latency, error rate, CPU, and I/O.

## 11. Privileges and Auditing

### 11.1. Privileges to Inspect and Terminate Sessions

Users without `PROCESS` see only partial process lists; other users' sessions may be hidden. Stopping another user's thread requires appropriate connection admin privileges, typically `CONNECTION_ADMIN` in MySQL 8.0/8.4; `SUPER` is a legacy monolithic privilege that should not be broadly granted just for incident handling.

If the target thread holds `SYSTEM_USER`, the operator also needs `SYSTEM_USER` to terminate it. An account can kill its own sessions per MySQL rules, while managing system threads requires dedicated privileges.

Check privileges:

~~~sql
SHOW GRANTS FOR CURRENT_USER();
~~~

Grant privileges following least privilege and organizational DBA policy. Never grant `SUPER` or broad privileges to application accounts just for convenient `KILL`ing.

### 11.2. Auditing Actions

Audit logs should record:

- Operator and related ticket/incident.
- Host, port, role, and MySQL environment.
- Processlist ID, user, host, and SQL (sanitized of sensitive data if needed).
- Transaction, lock, and replica state prior to action.
- Action type and timestamp.
- Rationale for choosing `KILL QUERY`, `KILL CONNECTION`, or restart.
- Rollback/recovery status and post-action verification.
- Business impact and follow-up remediation.

Never include passwords, tokens, or personal data in incident logs. Retain enough evidence to justify the decision and improve runbooks.

## 12. Self-Check

**Scenario 1:** A session shows `Command=Sleep` for 25 minutes. Should you `KILL` it immediately?

**Hint:** Not yet. Check whether it holds an open transaction, holds locks, belongs to a connection pool, and is simply a normal idle connection. Long `Sleep` alone does not prove a problem.

**Scenario 2:** A query received `KILL QUERY`, yet other transactions still wait on locks. Why?

**Hint:** The session may still hold an open explicit transaction; locks from earlier statements remain held. Check `innodb_trx` and ask the application to roll back or close the session per procedure.

**Scenario 3:** `KILL CONNECTION` returned success, yet locks did not vanish immediately. Did the command fail?

**Hint:** Not necessarily. An uncommitted transaction may still be rolling back. Monitor rollback state and InnoDB status until rollback completes.

**Scenario 4:** A replica shows `Replica_IO_Running=Yes` but `Replica_SQL_Running=No`. Should you `KILL` the thread and restart MySQL?

**Hint:** Not automatically. Inspect the applier error, GTIDs, and data first. Follow the replication runbook to fix the root cause; restarting causes further disruption without fixing data errors.

**Scenario 5:** After restarting the primary, some write requests were retried and created duplicate orders. Why?

**Hint:** Clients may have lost connection after the server committed but before receiving the response. Non-idempotent retries create duplicate records. Use idempotency keys or business-state verification steps.

**Scenario 6:** MySQL reports disk full and stops responding. Is restarting the first step?

**Hint:** No. Inspect filesystems, data, binary logs, and `tmpdir`; preserve logs and expand or free space per runbook. Restarting while disk remains full can prevent the server from booting.

## 13. Key Takeaways

- Verify processlist ID, user, host, SQL, and owner before any `KILL` command.
- `KILL QUERY` stops the current statement while keeping the connection; explicit transactions may remain open and keep holding locks.
- `KILL CONNECTION` closes the session and rolls back uncommitted transactions; rollback can take significant time.
- Distinguish blockers from victims before acting on lock waits.
- `Sleep` sessions can be normal or hold open transactions; always check `innodb_trx`.
- DDL can hold metadata locks and create queues; identify both the waiting DDL and the lock-holding transaction.
- Restarting disrupts every client, transaction, replication stream, job, and connection pool on the instance.
- Never restart to "cure" slow queries, missing indexes, full disks, or corruption without assessing root cause and recovery runbooks.
- `COMMIT` outcomes can be indeterminate after network loss; write retries require idempotency or state verification.
- Collect evidence before acting, monitor rollback/recovery, and verify applications afterward.

## References

- [MySQL 8.4 Reference Manual: KILL Statement](https://dev.mysql.com/doc/refman/8.4/en/kill.html) — behavior of `KILL QUERY` and `KILL CONNECTION`.
- [MySQL 8.4 Reference Manual: SHOW PROCESSLIST](https://dev.mysql.com/doc/refman/8.4/en/show-processlist.html) — inspecting sessions and running statements.
- [MySQL 8.4 Reference Manual: InnoDB Transaction Model](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-model.html) — transactions, commits, and rollbacks.
- [MySQL 8.4 Reference Manual: InnoDB Locking](https://dev.mysql.com/doc/refman/8.4/en/innodb-locking.html) — InnoDB locking mechanics.
- [MySQL 8.4 Reference Manual: Performance Schema data_lock_waits](https://dev.mysql.com/doc/refman/8.4/en/performance-schema-data-lock-waits-table.html) — relationship between waiting and blocking transactions.
- [MySQL 8.4 Reference Manual: Metadata Locking](https://dev.mysql.com/doc/refman/8.4/en/metadata-locking.html) — metadata locks and DDL impact.
- [MySQL 8.4 Reference Manual: Server Shutdown Process](https://dev.mysql.com/doc/refman/8.4/en/server-shutdown.html) — MySQL shutdown phases.
- [MySQL 8.4 Reference Manual: Privileges Provided by MySQL](https://dev.mysql.com/doc/refman/8.4/en/privileges-provided.html) — `PROCESS`, `CONNECTION_ADMIN`, and `SYSTEM_USER`.
