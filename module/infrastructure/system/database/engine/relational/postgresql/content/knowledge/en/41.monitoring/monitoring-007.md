# Connection, Error, Deadlock, and Checkpoint Logs in PostgreSQL

Monitoring PostgreSQL is not just about watching CPU, memory, and connection counts. When an application slows down, fails to connect, or transactions hang, server logs and runtime statistics provide the essential evidence needed to uncover root causes.

This lesson focuses on four operational information groups:

- **Connection logs** show which clients connected and disconnected, which database and role they used, and how long sessions lasted.
- **Error logs** record failed statements, SQLSTATE codes, context, and when incidents occurred.
- **Deadlock and lock-wait logs** help identify transactions blocking one another, lock wait durations, and the queries involved.
- **Checkpoint logs and statistics** show how PostgreSQL flushes dirty buffers to storage, whether checkpoints are triggered by timeout or WAL pressure, and whether I/O bottlenecks are forming.

Logs must be detailed enough to investigate issues while remaining bounded in volume, cost, and sensitive data exposure. A configuration logging every statement along with every parameter can leak sensitive information and sharply raise I/O. Conversely, logging too little leaves operations unable to reconstruct incidents.

~~~mermaid
flowchart TD
    A["PostgreSQL workload"] --> B["Logging configuration"]
    B --> C["Connection / session logs"]
    B --> D["Errors / SQLSTATE / statements"]
    B --> E["Lock waits / deadlocks"]
    B --> F["Checkpoint / WAL logs"]
    C --> G["Log collector / rotation"]
    D --> G
    E --> G
    F --> G
    G --> H["Central log store"]
    H --> I["Correlation and incident analysis"]
    J["pg_stat_activity / pg_locks"] --> I
    K["pg_stat_checkpointer / pg_stat_wal"] --> I
~~~

This lesson belongs to the **Monitoring** chapter of the **Database Engine Relational PostgreSQL** module. We will explore log destinations, the logging collector, connection and error logging, log prefixes, lock diagnostics, deadlock detection, checkpoint behavior, WAL metrics, statistics queries, and incident investigation workflows.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the role of PostgreSQL server logs in monitoring and troubleshooting.
2. Distinguish the logging collector from log destinations.
3. Configure `stderr`, `csvlog`, `jsonlog`, and `syslog` to fit your environment.
4. Set up log directory, filename, rotation, and retention.
5. Record connections, disconnections, and session durations.
6. Use `log_line_prefix` to correlate logs with session, user, database, and application.
7. Choose `log_min_messages`, `log_min_error_statement`, and `log_error_verbosity`.
8. Control logging of SQL statements and execution durations.
9. Classify errors using SQLSTATE codes and context.
10. Distinguish lock waits from deadlocks.
11. Configure `deadlock_timeout` and `log_lock_waits`.
12. Query `pg_stat_activity`, `pg_locks`, and `pg_blocking_pids`.
13. Read deadlock reports and identify conflicting transactions.
14. Explain checkpoints, dirty buffers, and WAL pressure.
15. Configure `log_checkpoints` and checkpoint tuning parameters.
16. Monitor checkpoint statistics according to PostgreSQL major version.
17. Combine checkpoint, WAL, and I/O metrics to locate bottlenecks.
18. Manage log volume, retention, and sensitive data exposure.
19. Build investigation workflows for connections, errors, deadlocks, and checkpoints.
20. Propose configuration changes backed by evidence and testing.

## 2. How Does PostgreSQL Write Logs?

PostgreSQL backends emit log messages according to severity and event type. Messages can be written to standard error (`stderr`), then captured by the logging collector into files, or forwarded to an external logging service such as syslog.

Overall flow:

~~~text
Client / SQL / Backend event
          |
          v
PostgreSQL backend
          |
          +-- severity, timestamp, SQLSTATE, context
          |
          v
log destination
          |
          +-- stderr
          +-- csvlog
          +-- jsonlog
          +-- syslog
          +-- eventlog (Windows)
          |
          v
logging collector / OS logging service
          |
          v
log files / central logging
~~~

### What is the logging collector?

The **logging_collector** parameter enables a background process that captures messages sent to `stderr` and writes them to log files. The collector supports file management and rotation based on PostgreSQL configuration.

Example:

~~~conf
logging_collector = on
log_directory = 'log'
log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log'
~~~

Changing `logging_collector` requires a server restart to take effect. Not every logging parameter requires a restart; many log settings can be applied via reload.

### The logging collector is not the log destination

- **log_destination** chooses the output format/target.
- **logging_collector** determines whether PostgreSQL captures `stderr` into files.
- Syslog or Windows Event Log are mechanisms that forward logs to OS-level logging services.
- Central logging is the external layer that ingests, stores, searches, and alerts on logs outside PostgreSQL.

## 3. Choosing a Log Destination

Parameter:

~~~conf
log_destination = 'stderr'
~~~

Common destinations:

| Destination | Characteristics | When Suitable |
| --- | --- | --- |
| stderr | Plain-text logs to standard error | Containers, systemd, collectors, or logging collector |
| csvlog | CSV with structured columns | Analysis with tabular/log tools |
| jsonlog | Structured JSON | Central log pipelines and field-based queries |
| syslog | Sends messages to syslog | Linux/Unix centralized logging systems |
| eventlog | Windows Event Log | Windows environments |

Multiple destinations can be combined depending on version and OS, for example:

~~~conf
log_destination = 'stderr,csvlog'
logging_collector = on
~~~

CSV/JSON file logging via the logging collector requires the collector to be enabled. Consult the documentation for your exact major version to confirm supported destinations and configuration details.

### stderr

Simple plain-text logs, easy to read directly and widely used in containers. When PostgreSQL runs under systemd, `stderr` can be captured by the systemd journal. In other environments, the service manager or container runtime handles stdout/stderr.

### csvlog

CSV logs include columns such as timestamp, user, database, process ID, client address, session ID, SQLSTATE, message, detail, hint, query, and context. Exact column structure depends on PostgreSQL version.

Advantages:

- Dedicated fields make importing straightforward.
- Easy filtering by SQLSTATE, user, and database.
- Helpful for time-based analysis.

### jsonlog

JSON logs emit structured fields for modern pipelines. Log systems can parse JSON directly without brittle regex message parsing.

Advantages:

- Easy key-based search.
- Clean correlation across timestamp, process, session, and SQLSTATE.
- Works cleanly with OpenSearch, Elasticsearch, Loki, or similar log platforms when supported by the pipeline.

### syslog

When using syslog, PostgreSQL forwards logs to the syslog service. Configure facility, identifier, and severity appropriate for your environment.

~~~conf
log_destination = 'syslog'
syslog_facility = 'LOCAL0'
syslog_ident = 'postgres'
~~~

Not every OS or container runtime runs a syslog daemon. Verify the log pipeline end-to-end so you do not assume PostgreSQL is logging while messages are silently dropped.

## 4. Configuring Log Files and Rotation

When using the logging collector, you can configure:

~~~conf
log_directory = 'log'
log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log'
log_file_mode = 0600
log_rotation_age = '1d'
log_rotation_size = '100MB'
log_truncate_on_rotation = on
~~~

Meaning:

- **log_directory**: directory holding log files, relative to the data directory or an absolute path.
- **log_filename**: filename pattern supporting time-based placeholders.
- **log_file_mode**: file permission mode on supported systems.
- **log_rotation_age**: maximum elapsed time before rotation.
- **log_rotation_size**: maximum file size before rotation.
- **log_truncate_on_rotation**: whether to truncate an existing file of the same name during time-based rotation.

### Time-based and size-based rotation

`log_rotation_age` and `log_rotation_size` work together. When either rotation condition triggers, the collector opens the next file using the configured naming pattern.

If `log_filename` contains only the date and size-based rotation occurs multiple times within the same day, design the naming pattern and rotation settings carefully to avoid unintended overwrites.

`log_truncate_on_rotation` applies only when opening an existing file during time-based rotation; it is not a general retention mechanism.

### Rotation is not retention

Rotation creates new files. It does not delete old files after a set number of days per a retention policy. Retention must be handled by:

- `logrotate` or OS tooling.
- Central logging retention rules.
- Object storage lifecycle policies.
- Controlled archive/deletion workflows.

Never delete a log file currently held open by PostgreSQL. If using external tools, follow rotation/reopen mechanisms supported by PostgreSQL and the OS.

### current_logfiles and pg_current_logfile

When the logging collector is active, PostgreSQL can maintain a `current_logfiles` file listing active log files. The `pg_current_logfile()` function returns the current log file path for the specified destination, depending on version and configuration.

~~~sql
SELECT pg_current_logfile();
~~~

If targeting a specific destination, check the function signature for your running server version.

## 5. Time, Timezones, and Log Prefixes

Timestamps anchor correlations across PostgreSQL logs, application logs, proxy logs, OS logs, and distributed tracing.

Example:

~~~conf
log_timezone = 'UTC'
log_line_prefix = '%m [%p] %q%u@%d/%a %r '
~~~

Commonly used placeholders:

| Placeholder | Meaning |
| --- | --- |
| %m | Timestamp with milliseconds |
| %t | Timestamp without milliseconds |
| %n | Unix epoch timestamp |
| %p | Process ID |
| %u | User/role |
| %d | Database |
| %r | Remote host and port |
| %h | Remote host |
| %a | Application name |
| %c | Session ID |
| %l | Log line sequence number within session |
| %e | SQLSTATE |
| %i | Command tag |
| %x | Transaction ID |
| %v | Virtual transaction ID |
| %s | Session start timestamp |
| %b | Backend type |

Available placeholders can vary by version; consult the runtime logging configuration documentation.

### Traceable prefix example

~~~conf
log_line_prefix = '%m [%p] session=%c user=%u db=%d app=%a client=%r sqlstate=%e '
~~~

A single log line reveals:

- Exact time of occurrence.
- Backend PID.
- Session ID.
- Role and database.
- Application name.
- Client address and port.
- SQLSTATE if applicable.

### Application name

Clients can set `application_name` in their connection string:

~~~text
host=db.example.net dbname=appdb user=app_user application_name=orders-api
~~~

Then `%a` in logs and `pg_stat_activity.application_name` distinguish applications, workers, ETL jobs, and administrative tools.

Do not let all services share a generic `application_name` if you need per-workload investigation.

## 6. Recording Connections and Disconnections

Two parameters:

~~~conf
log_connections = on
log_disconnections = on
~~~

`log_connections` logs connection attempts, including authentication/authorization steps and connection establishment depending on version. `log_disconnections` logs session termination, typically with session duration and related session metrics.

### When to enable them?

- Investigating connection spikes.
- Tracking unexpected clients.
- Analyzing rejected connections.
- Identifying services opening too many sessions.
- Investigating connection pools failing to reuse connections.
- Detecting long-lived sessions or abnormal disconnects.

### Cost

In environments experiencing tens of thousands of short connections per minute, logging every connect and disconnect can generate huge log volume. Measure disk space and CPU impact, and pair with connection pooling to curb churn.

### log_hostname

`log_hostname` instructs PostgreSQL to resolve hostnames for client IP addresses in certain log messages. Reverse DNS lookups can add latency to connection setup if DNS is slow. If hostnames are unnecessary, log IP addresses and resolve them via inventory or network logs.

## 7. Tracking Sessions with pg_stat_activity

`pg_stat_activity` reflects current session state, not historical closed connections.

~~~sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    client_addr,
    client_port,
    backend_start,
    xact_start,
    query_start,
    state_change,
    state,
    wait_event_type,
    wait_event,
    left(query, 180) AS query_sample
FROM pg_stat_activity
ORDER BY backend_start;
~~~

Common states:

- `active`: backend is executing a query.
- `idle`: session has no currently running query.
- `idle in transaction`: a transaction is open, though the session is not executing a query.
- `idle in transaction (aborted)`: the transaction errored and has not yet been rolled back or ended.

### Counting sessions by database and state

~~~sql
SELECT
    datname,
    usename,
    application_name,
    state,
    count(*) AS sessions
FROM pg_stat_activity
GROUP BY datname, usename, application_name, state
ORDER BY sessions DESC;
~~~

### Why does idle in transaction matter?

A long-open transaction can:

- Hold locks.
- Hold old snapshots.
- Prevent vacuum from reclaiming dead tuple versions.
- Increase table and index bloat.
- Block DDL or other transactions.
- Impede replication or maintenance progress in certain situations.

Find long-open transactions:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    now() - xact_start AS transaction_age,
    state,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

`pg_stat_activity` can expose sensitive query text. Visibility into other users' sessions depends on monitoring privileges and roles.

## 8. Recording SQL Errors

Key parameters:

~~~conf
log_min_messages = warning
log_min_error_statement = error
log_error_verbosity = default
~~~

### log_min_messages

Controls the minimum severity written to the server log. Common levels:

| Level | General Meaning |
| --- | --- |
| DEBUG5 ... DEBUG1 | Debug details; lower levels emit progressively more detail |
| INFO | Informational |
| NOTICE | Notice |
| WARNING | Warning |
| ERROR | Statement/session error |
| LOG | Operational message |
| FATAL | Error causing session termination |
| PANIC | Critical error causing server shutdown/recovery |

Consult PostgreSQL documentation for exact severity ordering and valid levels. Because this setting is a threshold, choosing a lower level in the severity hierarchy emits more messages.

### log_min_error_statement

Controls the minimum error severity at which PostgreSQL logs the offending SQL statement. For instance, `error` logs statements causing `ERROR` or higher. Statements can contain sensitive literals or parameters, so apply appropriate policies.

### log_error_verbosity

- `terse`: omits detail, hint, and context lines.
- `default`: standard level of detail.
- `verbose`: adds fields such as SQLSTATE and internal source location where supported by version.

`verbose` helps during debugging, though it lengthens logs.

## 9. SQLSTATE and Error Classification

SQLSTATE is a standardized five-character code that classifies errors reliably without depending solely on message wording.

Common codes:

| SQLSTATE | Name | Meaning |
| --- | --- | --- |
| 23505 | unique_violation | Unique constraint violation |
| 23503 | foreign_key_violation | Foreign key violation |
| 40001 | serialization_failure | Transaction requires retry due to serialization conflict |
| 40P01 | deadlock_detected | Deadlock detected |
| 55P03 | lock_not_available | Requested lock could not be acquired |
| 57014 | query_canceled | Query canceled or timed out per context |
| 53300 | too_many_connections | Standard connection slots exhausted |
| 57P01 | admin_shutdown | Server shutting down by administrative command |

The first two characters form the SQLSTATE class for broad grouping. When `%e` is in `log_line_prefix`, logs can be filtered and aggregated cleanly by code.

Example filter for deadlock errors in a log system:

~~~text
sqlstate = "40P01"
~~~

Do not alert solely on message text, as messages can be localized or vary across releases.

## 10. Logging SQL Statements and Execution Durations

Several levels of statement logging exist:

~~~conf
log_statement = 'none'
~~~

Options:

- `none`: do not log statements via this setting.
- `ddl`: log DDL commands.
- `mod`: log DDL and data-modifying statements such as INSERT/UPDATE/DELETE.
- `all`: log every statement.

### Caution with log_statement=all

Log volume can balloon rapidly while capturing sensitive data such as emails, tokens, PII, or business payloads. Never leave it enabled long-term in production without verified capacity and data-handling policies.

### log_duration

~~~conf
log_duration = on
~~~

Logs statement execution durations per configuration, though it does not necessarily include query text unless paired with another setting.

### log_min_duration_statement

Example logging only statements taking 1 second or longer:

~~~conf
log_min_duration_statement = '1s'
~~~

Values:

- `-1`: disables threshold-based logging.
- `0`: logs durations of all statements.
- Positive value: logs statements meeting or exceeding that duration.

This is a practical way to catch slow queries without logging every single statement.

### Sampling

Some PostgreSQL versions support sampling settings for statement logging. Check version documentation before enabling; sampling trims log volume at the risk of missing infrequent slow queries.

### Combining log_statement and log_min_duration_statement

One filters by statement type while the other filters by duration. Understand potential log duplication and total volume when enabling both.

## 11. Parameter Logging and Sensitive Data

SQL logs can capture parameter values, which may include:

- Passwords or tokens passed improperly.
- Emails, phone numbers, and street addresses.
- Payment identifiers.
- Customer content.
- Internal records.
- Application search inputs.

Some versions expose `log_parameter_max_length` and `log_parameter_max_length_on_error` to limit bind-parameter logging. Behavior and defaults vary by version.

Principles:

1. Never log plaintext secrets without valid necessity.
2. Restrict who can read logs.
3. Encrypt logs in transit and at rest.
4. Enforce policy-driven retention.
5. Treat logs as potentially containing PII.
6. Use query fingerprints/normalized queries for workload analysis instead of storing raw literals.

## 12. Slow Query Logs and Time-Based Queries

A practical starting configuration might look like:

~~~conf
log_min_duration_statement = '500ms'
log_line_prefix = '%m [%p] session=%c user=%u db=%d app=%a client=%r sqlstate=%e '
log_error_verbosity = default
~~~

`500ms` is only an example. An API with a 50 ms SLA needs a lower threshold; a multi-minute batch job may need a higher one.

Analyze slow query logs by:

- Query fingerprint.
- Database, user, and application.
- Execution duration.
- Frequency of occurrence.
- Peak hours.
- Lock waits.
- Buffer and cache behavior.
- Execution plans via `EXPLAIN (ANALYZE, BUFFERS)` in an appropriate environment.

Logged duration alone does not establish root cause. A slow query can result from CPU, I/O, locks, network, plan regressions, or resource contention.

## 13. Log Context and Error Location

ERROR messages can include:

- SQLSTATE.
- DETAIL.
- HINT.
- CONTEXT.
- STATEMENT.
- PL/pgSQL function and line context.
- Process and session metadata.

Illustrative example:

~~~text
ERROR:  duplicate key value violates unique constraint "orders_pkey"
DETAIL:  Key (order_id)=(42) already exists.
STATEMENT: INSERT INTO orders(order_id) VALUES (42);
~~~

In production, query text may be truncated or parameters masked by policy. During investigations, match session ID, PID, timestamp, `application_name`, and SQLSTATE to stitch related log lines together.

## 14. What Is a Deadlock?

A deadlock occurs when two or more transactions wait on resources held by one another, forming a dependency cycle where none can proceed.

Example:

- Transaction A locks row 1, then waits for row 2.
- Transaction B locks row 2, then waits for row 1.
- A waits for B and B waits for A.
- Neither transaction can move forward.

PostgreSQL detects the cycle in the wait-for graph and aborts one transaction to break the deadlock. The aborted transaction receives SQLSTATE `40P01`.

~~~mermaid
flowchart LR
    A["Transaction A"] -->|"holds lock on row 1"| R1["Row 1"]
    B["Transaction B"] -->|"holds lock on row 2"| R2["Row 2"]
    A -->|"waiting for row 2"| R2
    B -->|"waiting for row 1"| R1
    A -. "waits for B" .-> B
    B -. "waits for A" .-> A
~~~

### Deadlocks differ from lock waits

A simple lock wait occurs when one transaction waits for another transaction to commit or roll back. A deadlock is a mutual wait cycle.

- A lock wait clears naturally when the blocker commits.
- A deadlock requires PostgreSQL to abort one transaction to break the cycle.
- A long lock wait does not automatically imply a deadlock.

## 15. Reproducing a Deadlock

Create a test table:

~~~sql
CREATE TABLE account_demo (
    account_id integer PRIMARY KEY,
    balance numeric(12,2) NOT NULL
);

INSERT INTO account_demo VALUES
    (1, 1000),
    (2, 1000);
~~~

Session A:

~~~sql
BEGIN;
UPDATE account_demo SET balance = balance - 10 WHERE account_id = 1;
-- Wait briefly before running the next statement.
UPDATE account_demo SET balance = balance + 10 WHERE account_id = 2;
COMMIT;
~~~

Session B, interleaved after A's first UPDATE:

~~~sql
BEGIN;
UPDATE account_demo SET balance = balance - 20 WHERE account_id = 2;
UPDATE account_demo SET balance = balance + 20 WHERE account_id = 1;
COMMIT;
~~~

When A and B lock the two rows in opposite orders, PostgreSQL aborts one transaction with `deadlock detected`.

Run this example in a test database and coordinate execution timing to create interleaving. Never deliberately trigger deadlocks on production tables.

## 16. deadlock_timeout

Parameter:

~~~conf
deadlock_timeout = '1s'
~~~

`deadlock_timeout` determines how long PostgreSQL waits on a lock before running deadlock detection. It is not the maximum time a transaction is allowed to wait for a lock.

Once a lock wait crosses this threshold, PostgreSQL scans for cycles. Deadlock checking has overhead; do not set it overly low on lock-heavy workloads without benchmarking.

### deadlock_timeout is not lock_timeout

- `deadlock_timeout`: delay before checking for deadlocks.
- `lock_timeout`: maximum duration a statement waits for a lock before aborting.
- `statement_timeout`: maximum statement execution duration.
- `idle_in_transaction_session_timeout`: maximum duration a session may stay idle inside a transaction.

Example:

~~~conf
deadlock_timeout = '1s'
lock_timeout = '5s'
statement_timeout = '30s'
idle_in_transaction_session_timeout = '60s'
~~~

These values are illustrative. If `lock_timeout` is shorter than `deadlock_timeout`, a statement may abort with a lock timeout before the deadlock detector runs its scheduled check.

## 17. Enabling log_lock_waits

Example:

~~~conf
log_lock_waits = on
deadlock_timeout = '1s'
~~~

`log_lock_waits` instructs PostgreSQL to emit log entries whenever a session waits for a lock longer than `deadlock_timeout`.

This surfaces prolonged lock waits even when no deadlock occurs.

### How to read the log?

Lock-wait log entries typically report:

- Which process is waiting.
- Lock type and mode requested.
- Related relation/object if applicable.
- Transactions or processes currently holding conflicting locks per available context.
- Wait duration.

Correlate the PID with `pg_stat_activity` and `pg_locks` at the time of the incident. Because sessions often finish before an operator runs diagnostic queries, logs preserve crucial historical evidence.

## 18. Finding Sessions Waiting on Locks

Simple query:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE wait_event_type = 'Lock'
ORDER BY query_start;
~~~

Any returned rows indicate backends waiting on locks. Next, identify the blockers.

### Using pg_blocking_pids

~~~sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.usename AS blocked_user,
    blocked.application_name AS blocked_app,
    now() - blocked.query_start AS wait_duration,
    left(blocked.query, 160) AS blocked_query,
    blocker.pid AS blocker_pid,
    blocker.usename AS blocker_user,
    blocker.application_name AS blocker_app,
    blocker.state AS blocker_state,
    now() - blocker.xact_start AS blocker_xact_age,
    left(blocker.query, 160) AS blocker_query
FROM pg_stat_activity AS blocked
JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS p(blocker_pid)
    ON true
JOIN pg_stat_activity AS blocker
    ON blocker.pid = p.blocker_pid
WHERE blocked.wait_event_type = 'Lock'
ORDER BY blocked.query_start;
~~~

`pg_blocking_pids(pid)` returns PIDs currently blocking the specified process. Multiple blockers may exist.

### Why can a blocker be idle?

A session may have run an `UPDATE` and then gone `idle` while leaving its transaction open and holding locks. Its current `query` field might show `COMMIT`, `ROLLBACK`, or an earlier statement that does not reflect which statement acquired the lock. Inspect `xact_start`, `application_name`, and prior logs.

## 19. Inspecting pg_locks

`pg_locks` exposes held and requested locks.

~~~sql
SELECT
    l.pid,
    a.usename,
    a.application_name,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name,
    l.page,
    l.tuple,
    l.transactionid,
    a.state,
    a.wait_event_type,
    a.wait_event,
    left(a.query, 160) AS query_sample
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
    ON a.pid = l.pid
ORDER BY l.granted, l.pid;
~~~

Columns:

- `locktype`: category of lockable object.
- `mode`: lock mode.
- `granted`: whether the lock is held (`true`) or awaited (`false`).
- `relation`: relation OID when the lock targets a relation.
- `transactionid`: transaction ID when waiting on or holding a transaction lock.

Not every lock has a `relation`. Internal locks and advisory locks have different structures.

### Lock modes

PostgreSQL defines multiple lock modes. For table locks, examples include `AccessShareLock`, `RowShareLock`, `RowExclusiveLock`, `ShareLock`, `ShareRowExclusiveLock`, `ExclusiveLock`, and `AccessExclusiveLock`, governed by a conflict matrix.

Never guess whether two modes conflict from their names alone. Check the lock compatibility matrix in the PostgreSQL documentation.

## 20. Reading a Deadlock Report

An illustrative deadlock report looks like:

~~~text
ERROR:  deadlock detected
DETAIL: Process 12345 waits for ShareLock on transaction 67890;
        blocked by process 12346.
        Process 12346 waits for ShareLock on transaction 67891;
        blocked by process 12345.
HINT:  See server log for query details.
CONTEXT: while updating tuple (...) in relation "account_demo"
~~~

Key components:

- PIDs of involved processes.
- Requested lock modes.
- Blocked transaction IDs or objects.
- Blocking PIDs.
- Query and context details where PostgreSQL can supply them.
- HINT pointing to the server log for full query context.

### Analysis

1. Locate the PIDs using log prefixes.
2. Find the preceding statements leading up to the deadlock.
3. Determine the object lock order used by each transaction.
4. Identify which transaction PostgreSQL aborted.
5. Check whether the surviving transaction committed or rolled back.
6. Standardize lock acquisition ordering or shorten transactions.
7. Verify application retry handling.

## 21. Reducing Deadlocks

### Acquire resources in a consistent order

If multiple transactions update accounts A and B, acquire locks in ascending account ID order across all code paths.

Example:

~~~sql
BEGIN;
SELECT account_id
FROM account_demo
WHERE account_id IN (1, 2)
ORDER BY account_id
FOR UPDATE;
-- Perform updates in the same order.
COMMIT;
~~~

Consistent pre-locking reduces cycles, though you must still check other locks and real-world code paths.

### Keep transactions short

- Never call external APIs while a transaction holds locks.
- Never wait on user interaction mid-transaction.
- Commit or roll back promptly.
- Prevent prolonged `idle-in-transaction` states.
- Lock only the rows actually needed.

### Appropriate indexes

`UPDATE`/`DELETE` or `SELECT FOR UPDATE` scanning many rows can acquire far more locks than necessary. Proper indexes narrow scans and shorten lock hold times, though indexes alone cannot eliminate all deadlocks.

### Application-level deadlock retries

PostgreSQL aborts one transaction upon deadlock detection. Applications can retry that transaction when safe to repeat:

- Retry SQLSTATE `40P01` only per policy.
- Retry the entire transaction from the beginning; never continue mid-transaction after an abort.
- Use bounded retries with exponential backoff and jitter.
- Ensure operations are idempotent or protected by idempotency keys.
- Track retry counts to detect rising deadlock rates.

Never retry infinitely, as that turns deadlocks into retry storms.

## 22. What Is a Checkpoint?

A checkpoint is the process by which PostgreSQL ensures dirty data pages in shared buffers have been flushed to data files and writes a checkpoint record to WAL. Checkpoints establish a safe starting point for crash recovery so PostgreSQL does not have to replay WAL infinitely from the beginning of time.

Checkpoints can be triggered by:

- Elapsed time since the previous checkpoint reaching `checkpoint_timeout`.
- WAL usage reaching the threshold tied to `max_wal_size`.
- An administrator issuing `CHECKPOINT`.
- Other operational, backup, or recovery conditions depending on version.

### Dirty buffers

A data page modified in memory becomes a dirty buffer. PostgreSQL writes dirty pages asynchronously in the background or during checkpoints. Checkpoints guarantee required data is flushed according to durability rules.

### A checkpoint is not a backup

Checkpoints support crash recovery. They do not create standalone backups and never replace base backups and WAL archives.

## 23. Checkpoints and WAL

Every data-modifying transaction generates WAL records. PostgreSQL relies on WAL to redo changes after a crash.

During a checkpoint:

1. PostgreSQL determines the checkpoint position.
2. Dirty buffers are written to data files on schedule.
3. WAL flushes are coordinated.
4. A checkpoint record is written to WAL.
5. Crash recovery can begin from the appropriate checkpoint.

Old WAL segments are recycled or removed only when no longer required for crash recovery, replication slots, WAL archiving, backups, or other consumers.

### max_wal_size is not a hard cap

`max_wal_size` is a soft target guiding checkpoint pacing. Total WAL on disk can exceed it due to bursty workloads, replication slots, archiving failures, or other conditions retaining WAL.

Never treat `max_wal_size` as a hard filesystem quota.

## 24. Enabling log_checkpoints

Configuration:

~~~conf
log_checkpoints = on
~~~

When enabled, PostgreSQL logs details about checkpoints and restartpoints to the server log, which can include:

- Checkpoint trigger reason.
- Buffers written.
- Write duration.
- Sync duration.
- Processed file counts or related WAL details.
- Restartpoint details on standbys.

Exact log wording varies across major versions. Use these logs to determine whether checkpoints are firing due to timeout or WAL pressure, and how long each phase takes.

### Illustrative log example

~~~text
LOG: checkpoint starting: time
LOG: checkpoint complete: wrote 12000 buffers (...);
     write=... s, sync=... s, total=... s;
     distance=... kB, estimate=... kB
~~~

This is illustrative rather than a fixed format across all versions. Inspect actual logs for your version.

### Checkpoints vs. restartpoints

Primaries perform checkpoints. Standbys in recovery perform restartpoints, which bound how much WAL the standby must replay after a crash. Logs and statistics distinguish checkpoints from restartpoints.

## 25. Tracking Checkpoint Statistics by Version

PostgreSQL reorganized how these statistics views are structured.

### PostgreSQL 17 and later

Checkpoint statistics live in `pg_stat_checkpointer`.

~~~sql
SELECT *
FROM pg_stat_checkpointer;
~~~

This view reports timed and requested checkpoint counts, buffers written, write/sync times, and additional stats depending on version.

### PostgreSQL 16 and earlier

Checkpoint statistics live in `pg_stat_bgwriter`.

~~~sql
SELECT *
FROM pg_stat_bgwriter;
~~~

In these versions, the view exposes fields such as `checkpoints_timed`, `checkpoints_req`, `checkpoint_write_time`, `checkpoint_sync_time`, `buffers_checkpoint`, and background writer metrics.

Starting in PostgreSQL 17, checkpoint-related statistics moved into `pg_stat_checkpointer`; never copy PostgreSQL 16 column queries blindly onto 17+ servers without checking view schemas.

### Checking server version

~~~sql
SHOW server_version;
SHOW server_version_num;
~~~

When building monitoring dashboards, maintain version-aware queries and metric mappings per major version.

## 26. Reading Checkpoint Metrics

Key metrics to watch:

- Timed checkpoints (by timeout).
- Requested checkpoints (due to WAL pressure).
- Buffers written by the checkpointer.
- Write time.
- Sync time.
- Total checkpoint duration.
- WAL distance between checkpoints.
- In-progress checkpoints/restartpoints.

### Timed vs. requested checkpoints

- Timed checkpoints fire on `checkpoint_timeout`.
- Requested checkpoints trigger when WAL volume crosses thresholds or via explicit requests.

If requested checkpoints climb steadily, `max_wal_size` may be too small for your WAL generation rate, or write workloads surged. Inspect logs alongside disk and replication state before raising parameters.

### Checkpoint write time and sync time

Write time reflects time spent writing buffers in checkpoint stats. Sync time reflects file sync durations to storage per PostgreSQL accounting. Both help flag storage latency, though they must be paired with OS I/O metrics.

Never sum or read these counters as single-transaction latency; they accumulate across many checkpoints.

## 27. Tuning Checkpoints

Common settings:

~~~conf
checkpoint_timeout = '15min'
max_wal_size = '4GB'
min_wal_size = '1GB'
checkpoint_completion_target = 0.9
log_checkpoints = on
~~~

These numbers are examples, not universal defaults.

### checkpoint_timeout

Maximum interval between time-triggered checkpoints. Raising timeout reduces timed checkpoint frequency while increasing the amount of WAL crash recovery must replay.

### max_wal_size

WAL threshold triggering earlier checkpoints. Raising it can reduce requested checkpoints on WAL-intensive workloads while increasing disk/WAL retention needs and impacting replication/archiving headroom.

### min_wal_size

Amount of WAL PostgreSQL aims to retain for segment reuse. Adequate sizing reduces constant segment creation and removal churn.

### checkpoint_completion_target

Target fraction of the checkpoint interval over which dirty buffer writes are spread. Higher values smooth I/O bursts, though you must monitor total checkpoint duration and storage throughput.

### Never disable durability to chase speed

Never turn off `fsync` or `full_page_writes` in production just to cut checkpoint I/O. Those settings directly protect durability and crash recovery. Any change requires thorough understanding of risk and policy.

## 28. Checkpoints and Full-Page Writes

After a checkpoint, the first modification to a page under applicable conditions writes a full-page image to WAL when `full_page_writes` is enabled. This protects against torn pages during a crash.

Implications:

- Frequent checkpoints increase full-page images in WAL.
- WAL volume can spike right after checkpoints when workloads touch many distinct pages.
- `wal_compression` can shrink full-page images on certain workloads at the cost of extra CPU.
- Never disable `full_page_writes` solely to shrink WAL without verified storage-level torn-page guarantees.

When WAL volume jumps after checkpoints, inspect `pg_stat_wal`, workload patterns, and FPI counts before concluding.

## 29. Monitoring WAL Statistics

`pg_stat_wal` provides server-wide WAL statistics on modern PostgreSQL versions.

~~~sql
SELECT *
FROM pg_stat_wal;
~~~

Fields can include:

- `wal_records`: WAL records generated.
- `wal_fpi`: full-page images generated.
- `wal_bytes`: total WAL bytes generated.
- `wal_buffers_full`: times WAL buffers filled up per stats accounting.
- `wal_write`: number of WAL write calls.
- `wal_sync`: number of WAL sync calls.
- `wal_write_time`: time spent writing WAL when timing is enabled.
- `wal_sync_time`: time spent syncing WAL when timing is enabled.
- `stats_reset`: timestamp of last statistics reset.

Exact columns depend on version. `track_wal_io_timing` must be enabled for useful WAL timing fields where supported.

### Measuring WAL generation rate

Counters are cumulative. Sample twice over an interval and compute the delta:

\[
WAL\ rate = \frac{wal\_bytes_{t2} - wal\_bytes_{t1}}{t2 - t1}
\]

This estimates average WAL generation rate over the sampling window. Account for statistics resets, server restarts, and counter resets when computing deltas.

## 30. Monitoring I/O

`track_io_timing` enables I/O timing collection in supported statistics views.

~~~conf
track_io_timing = on
track_wal_io_timing = on
~~~

Availability and overhead depend on version and hardware. Timing introduces small clock-read overhead; benchmark on a representative workload.

### pg_stat_io

PostgreSQL 16 and later provide `pg_stat_io` to inspect I/O statistics by backend, object, and context.

~~~sql
SELECT *
FROM pg_stat_io
ORDER BY backend_type, object, context;
~~~

This view breaks down reads, writes, extends, fsyncs, and timings by activity class. Not all columns exist across all major versions; check the schema of your live server.

### Combining OS metrics

Pair PostgreSQL metrics with:

- Disk utilization and queue depth.
- Read/write throughput.
- p95/p99 latency.
- Filesystem free space.
- WAL volume.
- CPU `iowait`.
- Storage service metrics.
- Cloud volume burst credits if applicable.

Checkpoint logs describe PostgreSQL-side behavior; OS metrics prove whether underlying storage is actually saturating.

## 31. Distinguishing Checkpoint Pressure from WAL Retention

A large WAL directory does not automatically mean checkpoints are slow.

Other causes:

- A replication slot retaining WAL.
- Failing WAL archiving.
- Standby lag.
- A running backup requiring WAL segments.
- A stalled logical decoding consumer.
- A high `max_wal_size` setting.
- A sudden write-workload spike.

Inspect slots:

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status
FROM pg_replication_slots
ORDER BY slot_type, slot_name;
~~~

Inspect the archiver:

~~~sql
SELECT *
FROM pg_stat_archiver;
~~~

Views and columns vary by version. Rising archive failures can cause WAL to accumulate even while checkpoints run smoothly.

## 32. Investigating Connection Spikes

When connection counts spike abruptly:

1. Group session counts by database, role, and application.
2. Inspect connection logs around the spike window.
3. Identify client IPs, `application_name`, and session start times.
4. Distinguish steady pooled connections from rapid short-lived churn.
5. Check for `idle-in-transaction` sessions.
6. Check `max_connections` and reserved slots.
7. Check for authentication failures or retry storms.
8. Audit connection pool sizing and timeouts.

Counting query:

~~~sql
SELECT
    datname,
    usename,
    application_name,
    client_addr,
    state,
    count(*) AS sessions
FROM pg_stat_activity
GROUP BY datname, usename, application_name, client_addr, state
ORDER BY sessions DESC;
~~~

Never raise `max_connections` immediately upon hitting `too_many_connections`. Each connection carries memory and CPU overhead; raising the cap blindly can destabilize the server. Fix pooling and connection leaks first.

## 33. Investigating Rising SQL Errors

Workflow:

1. Filter logs by severity and SQLSTATE.
2. Group by database, user, and application.
3. Inspect offending statements and context.
4. Correlate with deployment or config change timelines.
5. Check constraint or schema changes.
6. Determine whether errors stem from client input, concurrency, timeouts, or server resources.
7. Measure error rates before and after changes.
8. Fix the root cause and monitor recovery.

Helpful codes:

- `23505`: duplicate key.
- `23503`: foreign key violation.
- `40001`: serialization failure.
- `40P01`: deadlock.
- `55P03`: lock unavailable.
- `57014`: query canceled.
- `53300`: too many connections.

Never lump every `ERROR` into a single generic alert. Different codes call for different responses: `40001` may merit a retry, whereas `23503` usually requires fixing application logic or data.

## 34. Investigating Deadlocks in Production

When logs show SQLSTATE `40P01`:

1. Record timestamp, PID, session ID, and `application_name`.
2. Pull the full deadlock report for that timestamp.
3. Identify involved relations, transaction IDs, and lock modes.
4. Trace preceding queries for each PID in the logs.
5. Map the resource lock acquisition order.
6. Check transaction durations and `idle-in-transaction` behavior.
7. Reproduce in staging using identical operation ordering.
8. Fix code, lock ordering, indexes, or transaction boundaries.
9. Add bounded retries.
10. Track deadlock rates after deployment.

Never raise `deadlock_timeout` simply to suppress log noise. That delays detection without resolving the underlying cycle.

## 35. Investigating Overly Frequent Checkpoints

Symptoms:

- Frequent checkpoint log entries.
- Many checkpoints triggered with reason `requested`.
- High WAL generation rate.
- Disk write bursts.
- Query latency spikes coinciding with checkpoints.
- Rapidly climbing `pg_stat_checkpointer`/`pg_stat_bgwriter` counters.

Steps:

1. Determine whether checkpoints are timed or requested.
2. Measure WAL bytes/second.
3. Inspect `max_wal_size`, `checkpoint_timeout`, and `checkpoint_completion_target`.
4. Check replication slots and the archiver.
5. Cross-check disk throughput and latency.
6. Check buffers written and checkpoint duration.
7. Test tuning one parameter at a time in staging.
8. Compare WAL, I/O, and latency before and after.

If requested checkpoints are driven by high WAL volume, raising `max_wal_size` can lower frequency provided you have adequate disk and slot retention headroom. If storage is already saturated, raising the cap alone may prolong bursts or defer symptoms.

## 36. Log Rotation and Retention in Production

An operational policy should define:

- File naming and timestamp timezone.
- Time-based and size-based rotation.
- Retention by days or storage budget.
- Compression.
- Shipping to central logging.
- Access controls.
- Encryption at rest and in transit.
- Backup and auditing.
- Handling when the log disk fills up.
- Ensuring logs are not lost during collector or server restarts.

### Dedicated disk for logs

Separating log storage from data and WAL volumes reduces the risk of log growth filling database filesystems. Still, ensure the logging collector handles dedicated-disk exhaustion gracefully and trigger alerts beforehand.

### Slow log pipelines

If a central log collector stops accepting events, local logs accumulate. Cap queue/buffer sizes and define fallback policies. Never allow a failing log pipeline to break PostgreSQL logging or silently fill disks without alerting.

## 37. Essential Logging Parameters to Know

The table below lists common parameters. Context and reloadability vary by version, and some settings require a restart.

| Parameter | Purpose |
| --- | --- |
| logging_collector | Captures stderr into log files |
| log_destination | Selects stderr/csvlog/jsonlog/syslog/eventlog |
| log_directory | Directory for log files |
| log_filename | Filename pattern |
| log_rotation_age | Time-based rotation interval |
| log_rotation_size | Size-based rotation threshold |
| log_truncate_on_rotation | Truncates matching file on time-based rotation |
| log_line_prefix | Metadata prefix per log line |
| log_timezone | Timezone for log timestamps |
| log_connections | Logs incoming connections |
| log_disconnections | Logs session terminations |
| log_min_messages | Minimum message severity |
| log_min_error_statement | Minimum severity to log offending SQL |
| log_error_verbosity | Level of error detail |
| log_statement | Logs DDL/mod/all statements |
| log_duration | Logs statement durations |
| log_min_duration_statement | Duration threshold for logging statements |
| log_lock_waits | Logs prolonged lock waits |
| deadlock_timeout | Wait delay before deadlock detection |
| log_checkpoints | Logs checkpoints and restartpoints |
| log_temp_files | Logs temporary files above threshold |
| log_autovacuum_min_duration | Logs autovacuum runs above threshold |

Never enable all settings at maximum verbosity without measuring log volume and performance overhead.

## 38. Verifying Effective Configuration

Use `pg_settings` to inspect values, sources, and contexts:

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    context,
    pending_restart
FROM pg_settings
WHERE name LIKE 'log_%'
   OR name IN (
       'logging_collector',
       'deadlock_timeout',
       'checkpoint_timeout',
       'checkpoint_completion_target',
       'max_wal_size',
       'min_wal_size',
       'track_io_timing',
       'track_wal_io_timing'
   )
ORDER BY name;
~~~

Useful columns:

- `setting`: current active value.
- `source`: configuration origin.
- `context`: setting context indicating whether reload, restart, or runtime change applies.
- `pending_restart`: whether a change awaits a server restart.

Check individual settings:

~~~sql
SHOW log_line_prefix;
SHOW log_connections;
SHOW log_lock_waits;
SHOW log_checkpoints;
~~~

### Reloading configuration

For reloadable settings:

~~~sql
SELECT pg_reload_conf();
~~~

Toggling `logging_collector` requires a restart. Inspect `context` and `pending_restart` instead of assuming a reload applied everything.

## 39. Practical Logging Configuration Example

A reasonable starting configuration:

~~~conf
# Log destination and collection
logging_collector = on
log_destination = 'stderr,csvlog'
log_directory = 'log'
log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log'
log_rotation_age = '1d'
log_rotation_size = '100MB'
log_truncate_on_rotation = on

# Session context
log_timezone = 'UTC'
log_line_prefix = '%m [%p] session=%c user=%u db=%d app=%a client=%r sqlstate=%e '

# Connections and errors
log_connections = on
log_disconnections = on
log_min_messages = warning
log_min_error_statement = error
log_error_verbosity = default

# Slow statements and lock waits
log_min_duration_statement = '1s'
log_lock_waits = on
deadlock_timeout = '1s'

# Checkpoints
log_checkpoints = on
~~~

This is an example for discussion, not a universal optimal config. Weigh connection volume, sensitivity of query parameters, log retention, storage capacity, and security requirements.

## 40. Combining Logs with Monitoring Dashboards

An operational dashboard should cover:

### Connections

- Current sessions.
- Connections by database/user/application.
- Connection failures.
- Connection and disconnection rates.
- `idle-in-transaction` count.
- Sessions approaching `max_connections`.

### Errors

- Error counts by SQLSTATE.
- Error rates by application.
- FATAL and PANIC events.
- Authentication failures.
- Query cancellations and timeouts.
- Top error messages/fingerprints.

### Locks

- Current lock waits.
- Longest wait duration.
- Blocking PID counts.
- Deadlocks per time window.
- Long-running transactions.
- `idle-in-transaction` sessions.

### Checkpoints/WAL

- Timed vs. requested checkpoint counts.
- Checkpoint write and sync times.
- Buffers written.
- WAL bytes per second.
- WAL archive failures.
- Replication slot retention.
- Disk free space and I/O latency.

Configure alerts on trends and SLO thresholds. For instance, a single deadlock may be retried cleanly by the application, whereas a steadily climbing deadlock rate demands investigation.

## 41. Correlating PostgreSQL Logs and Application Logs

To link logs across tiers, standardize:

- UTC or a consistent timezone policy.
- Request ID / correlation ID.
- `application_name`.
- Database user / service account.
- Client address.
- Session ID / PID.
- Timestamps with milliseconds.

PostgreSQL does not automatically receive every application trace ID. Applications can pass `application_name` per service/instance or use controlled session-level metadata. Never put secrets or sensitive user details in `application_name`.

When tracing a request:

1. Find the request ID in application logs.
2. Identify timestamp, service, and database connection details.
3. Filter PostgreSQL logs by session/app/client.
4. Match PID/session ID and SQLSTATE.
5. Check lock, checkpoint, and I/O metrics for that window.
6. Isolate whether the failure occurred in the app, database, network, or storage.

## 42. Troubleshooting Procedure: Connection Failures

**Symptom:** Application cannot connect or receives `too many connections`.

- Verify PostgreSQL process and listener status.
- Check network, DNS, and firewalls.
- Search FATAL log entries around the incident timestamp.
- Check `pg_hba.conf` and authentication if auth errors appear.
- Count sessions in `pg_stat_activity`.
- Group by application, user, and client.
- Inspect connection pools and check for retry storms.
- Check `max_connections` and reserved slots.
- Fix client connection leaks or pooling before raising connection limits.

## 43. Troubleshooting Procedure: Query Errors

**Symptom:** Rising SQL error rate.

- Group errors by SQLSTATE.
- Identify affected applications and databases.
- Inspect offending statements and context.
- Compare against deployment and migration timelines.
- Verify constraints, data types, and schemas.
- Determine whether errors are retryable or deterministic.
- Fix application logic or data.
- Monitor error rates after changes.

## 44. Troubleshooting Procedure: Deadlocks

**Symptom:** Application receives SQLSTATE `40P01`.

- Ensure `log_lock_waits` is enabled and `log_line_prefix` includes PID, session, and app.
- Read the deadlock report.
- Map the transaction wait cycle.
- Review row/table lock acquisition order.
- Check for long transactions and `idle-in-transaction` sessions.
- Standardize lock acquisition ordering.
- Shorten transactions and add suitable indexes where helpful.
- Add bounded transaction retries.
- Track deadlock rate after deploying fixes.

## 45. Troubleshooting Procedure: Checkpoints and I/O

**Symptom:** Periodic latency spikes, frequent checkpoint logs, growing WAL/disk usage.

- Inspect checkpoint trigger reasons in logs.
- Read checkpoint statistics for your version.
- Measure WAL generation rate.
- Review `max_wal_size` and `checkpoint_timeout`.
- Check replication slots and archiver health.
- Cross-check storage throughput and latency.
- Inspect `pg_stat_io` if supported by version.
- Test tuning one parameter in staging.
- Compare latency, WAL rate, and checkpoint frequency.

## 46. Log Security and Access Control

Logs can contain:

- SQL statements.
- Parameter values.
- Client IP addresses and hostnames.
- User and database names.
- Error context.
- Business identifiers.
- Accidental PII or secrets.

Requirements:

- Restrict log read access by role and team.
- Never allow applications to write or tamper with PostgreSQL logs.
- Protect logs with encryption at rest and in transit.
- Enforce retention and deletion policies.
- Mask or redact sensitive data in the pipeline where required.
- Audit log access.
- Never forward raw logs to external systems without authorization.
- Protect passwords in connection strings and query parameters.

Full logging does not mean everyone gets read access. Log governance must follow organizational data policies.

## 47. Common Mistakes

1. **Enabling `log_statement = all` long-term without sizing log volume**, filling disks and adding overhead.
2. **Enabling `log_connections`/`log_disconnections` under heavy connection churn without retention**, generating massive logs.
3. **Using a log prefix missing PID/session/application**, making request correlation difficult.
4. **Using inconsistent timezones**, breaking correlation with app and OS logs.
5. **Confusing `logging_collector` with `log_destination`**, misconfiguring files or syslog.
6. **Enabling `logging_collector` with only a reload**, when a restart is required.
7. **Confusing rotation with retention**, letting old log files pile up until disk fills.
8. **Relying on `log_truncate_on_rotation` as cleanup**, risking unintended file overwrites.
9. **Failing to restrict log file permissions**, exposing SQL and customer data.
10. **Enabling reverse DNS logging without measuring DNS latency**, slowing connection establishment.
11. **Reading an ERROR message without checking SQLSTATE/context**, missing error class and cause.
12. **Confusing lock waits with deadlocks**, tuning the wrong timeout.
13. **Increasing `deadlock_timeout` to reduce deadlocks**, when it only delays detection.
14. **Leaving `log_lock_waits` off**, losing historical evidence of prolonged lock waits.
15. **Checking `pg_stat_activity` only after an incident ends**, after sessions have closed.
16. **Ignoring `pg_blocking_pids`**, making manual blocker tracing slow and error-prone.
17. **Retrying deadlocks infinitely**, causing retry storms.
18. **Failing to enforce consistent lock order**, letting deadlocks recur.
19. **Treating checkpoints as backups**, leaving no independent backup copy.
20. **Raising `max_wal_size` without checking disk/slot retention**, letting WAL consume excessive space.
21. **Blaming storage for checkpoints without reading checkpoint reasons**, overlooking WAL pressure or slot retention.
22. **Assuming `pg_stat_bgwriter` holds checkpoint stats on all versions**, running broken queries on PostgreSQL 17+.
23. **Reading cumulative counters as instantaneous latency**, misinterpreting trends.
24. **Disabling `fsync`/`full_page_writes` to reduce I/O**, jeopardizing durability.
25. **Failing to monitor log disks and pipelines**, losing logs during incidents.
26. **Overlooking parameter logging**, inadvertently leaking secrets or PII into logs.
27. **Alerting identically on every ERROR**, creating noise and burying critical failures.
28. **Omitting `application_name` and request context**, dragging out investigations.

## 48. Practice Exercises with Answers

### Exercise 1. What role do server logs play?

**Answer:** They record connections, errors, statements, lock waits, deadlocks, checkpoints, and diagnostic context for investigations.

### Exercise 2. How does logging_collector differ from log_destination?

**Answer:** `logging_collector` captures `stderr` into files; `log_destination` selects output targets and formats.

### Exercise 3. Can logging_collector be toggled with only a reload?

**Answer:** No. Changing this setting requires restarting PostgreSQL.

### Exercise 4. Which settings enable CSV logs?

~~~conf
log_destination = 'stderr,csvlog'
logging_collector = on
~~~

**Answer:** Include `csvlog` in `log_destination` and enable `logging_collector` to write CSV files.

### Exercise 5. How do you enable JSON logs?

~~~conf
log_destination = 'jsonlog'
logging_collector = on
~~~

**Answer:** Use `jsonlog` on a supported PostgreSQL version with the collector enabled.

### Exercise 6. What do log_connections and log_disconnections do?

**Answer:** They log connection attempts/completions and disconnections/session durations depending on version.

### Exercise 7. Which placeholder logs the application name?

**Answer:** `%a`.

### Exercise 8. Which placeholder logs SQLSTATE?

**Answer:** `%e`.

### Exercise 9. Which placeholder logs PID?

**Answer:** `%p`.

### Exercise 10. What does log_min_duration_statement=1s mean?

**Answer:** Log statements whose execution duration reaches or exceeds one second.

### Exercise 11. What risks come with log_statement=all?

**Answer:** High log volume and potential exposure of sensitive SQL literals and parameters.

### Exercise 12. What error is SQLSTATE 40P01?

**Answer:** Deadlock detected.

### Exercise 13. What error is SQLSTATE 23505?

**Answer:** Unique violation.

### Exercise 14. What error is SQLSTATE 53300?

**Answer:** Too many connections.

### Exercise 15. How do deadlocks differ from lock waits?

**Answer:** A lock wait is waiting on a held lock; a deadlock is a mutual wait cycle among transactions that cannot resolve on its own.

### Exercise 16. What does deadlock_timeout do?

**Answer:** Sets how long PostgreSQL waits before checking for deadlocks; it is not a lock-wait timeout limit.

### Exercise 17. What does log_lock_waits log?

**Answer:** Lock waits lasting longer than `deadlock_timeout`.

### Exercise 18. What is pg_blocking_pids used for?

**Answer:** Returning the PIDs of backends currently blocking a given PID.

### Exercise 19. What does pg_locks show?

**Answer:** Lock types, modes, granted status, and associated objects or transactions.

### Exercise 20. How does PostgreSQL resolve a deadlock?

**Answer:** It detects the cycle and aborts one transaction to break the wait loop.

### Exercise 21. What is an effective way to reduce deadlocks?

**Answer:** Access resources in a consistent order and keep transactions short.

### Exercise 22. What is a checkpoint?

**Answer:** Flushing dirty buffers and writing a checkpoint record to establish a safe starting point for crash recovery.

### Exercise 23. What does log_checkpoints do?

**Answer:** Writes checkpoint and restartpoint details to server logs.

### Exercise 24. Is max_wal_size a hard limit?

**Answer:** No. It is a soft target; WAL can exceed it due to workloads, slots, and archiving.

### Exercise 25. Where are checkpoint statistics viewed in PostgreSQL 17?

**Answer:** `pg_stat_checkpointer`.

### Exercise 26. Where are checkpoint statistics viewed in PostgreSQL 16 and earlier?

**Answer:** `pg_stat_bgwriter`.

### Exercise 27. What is pg_stat_wal used for?

**Answer:** Tracking WAL records, bytes, writes, syncs, and related WAL statistics.

### Exercise 28. Why can the WAL directory grow large even when checkpoints run normally?

**Answer:** Replication slots, archiving failures, standby lag, or logical decoding can retain WAL.

### Exercise 29. Why does rotation not replace retention?

**Answer:** Rotation creates new log files; retention governs when old files are archived or deleted.

### Exercise 30. When should log_statement=all be enabled?

**Answer:** Primarily during time-bounded, tightly controlled investigations after assessing volume, overhead, and sensitive data exposure.

## 49. Monitoring and Troubleshooting Checklist

- [ ] Choose log destinations suited to OS, containers, and log pipelines.
- [ ] Verify `logging_collector` and restart requirements.
- [ ] Configure `log_directory`, filename pattern, and file permissions.
- [ ] Configure time-based and size-based rotation.
- [ ] Enforce a retention policy and disk usage alerts.
- [ ] Use a consistent `log_timezone`.
- [ ] Set `log_line_prefix` with PID, session, user, database, application, and client.
- [ ] Assign clear `application_name` values per service.
- [ ] Enable connection/disconnection logging when needed.
- [ ] Choose appropriate `log_min_messages` and `log_min_error_statement`.
- [ ] Classify errors with SQLSTATE.
- [ ] Set slow-query thresholds aligned with SLAs.
- [ ] Avoid logging all statements long-term without assessment.
- [ ] Control parameter logging and protect PII/secrets.
- [ ] Enable `log_lock_waits` when analyzing lock contention.
- [ ] Understand how `deadlock_timeout` differs from `lock_timeout`.
- [ ] Use `pg_stat_activity`, `pg_locks`, and `pg_blocking_pids` to locate blockers.
- [ ] Review deadlock reports and standardize lock ordering.
- [ ] Implement bounded retries for SQLSTATE `40P01`.
- [ ] Enable `log_checkpoints`.
- [ ] Monitor checkpoint statistics using views matching your major version.
- [ ] Track WAL generation alongside replication and archive retention.
- [ ] Monitor `pg_stat_wal`, `pg_stat_archiver`, and slots.
- [ ] Use `pg_stat_io` when supported by your version.
- [ ] Correlate PostgreSQL logs with OS/storage metrics.
- [ ] Verify `pg_settings` and `pending_restart` after changes.
- [ ] Test logging pipelines and retention before production rollout.
- [ ] Maintain runbooks for connection spikes, SQL errors, deadlocks, and checkpoint pressure.

## 50. Official PostgreSQL Documentation

Consult documentation matching your deployed major version:

- [Error Reporting and Logging](https://www.postgresql.org/docs/current/runtime-config-logging.html) — log destinations, collector, prefixes, connection/error/statement logging, and rotation.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — `pg_stat_activity`, `pg_locks`, `pg_stat_wal`, and statistics views.
- [Viewing Locks](https://www.postgresql.org/docs/current/monitoring-locks.html) — `pg_locks`, lock waits, and blocking sessions.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — lock modes, deadlocks, and prevention.
- [Lock Management](https://www.postgresql.org/docs/current/runtime-config-locks.html) — `deadlock_timeout` and lock-related settings.
- [Write Ahead Log](https://www.postgresql.org/docs/current/wal.html) — WAL and crash recovery.
- [WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html) — `checkpoint_timeout`, `max_wal_size`, `checkpoint_completion_target`, and durability settings.
- [Background Writer](https://www.postgresql.org/docs/current/runtime-config-resource.html) — background writer and related resource settings.
- [ALTER SYSTEM](https://www.postgresql.org/docs/current/sql-altersystem.html) — managing persistent configuration.
- [Configuration File](https://www.postgresql.org/docs/current/config-setting.html) — setting contexts, reloads, and restart behavior.

`/current/` URLs point to the latest PostgreSQL release. Statistics view names/columns, log destinations, parameter defaults, and setting contexts can vary across major versions; verify documentation for your exact server release before applying changes.

## 51. Summary

**PostgreSQL logs and runtime statistics complement each other: logs preserve historical evidence while system views expose live state.** Combining both enables systematic investigation of connection failures, SQL errors, deadlocks, and checkpoint pressure.

1. **The logging collector and log destinations are separate concepts.** Choose destinations and pipelines fitting your environment.
2. **Connection logs and `log_line_prefix` enable session tracing.** `application_name`, PID, session ID, and client address are key correlation fields.
3. **SQLSTATE classifies errors reliably.** Do not rely solely on message text.
4. **Statement logging must be controlled.** Account for log volume, overhead, and PII/secrets.
5. **Deadlocks differ from lock waits.** `deadlock_timeout` governs cycle checks; `log_lock_waits` captures prolonged waits.
6. **`pg_stat_activity`, `pg_locks`, and `pg_blocking_pids` pinpoint blockers.** Deadlock reports provide evidence of past cycles.
7. **Reduce deadlocks with short transactions and consistent lock ordering.** Retries must be bounded and safe.
8. **Checkpoints anchor crash recovery.** They are not backups.
9. **`log_checkpoints`, `pg_stat_checkpointer`/`pg_stat_bgwriter`, and `pg_stat_wal` help analyze checkpoint/WAL activity.** Select views matching your major version.
10. **`max_wal_size` is a soft threshold.** Replication slots and archiving can retain WAL beyond it.
11. **Rotation does not replace retention.** Manage disk space, read permissions, and log lifecycles.
12. **Monitoring must combine database, OS, and application layers.** No single metric proves root cause.
13. **Every logging or checkpoint change must be verified for activation and measured before/after.** Never sacrifice durability to mask I/O pressure.

A solid monitoring practice shows operations which clients drive load, which errors recur, which transactions block others, and whether checkpoints or WAL are pressuring storage.
