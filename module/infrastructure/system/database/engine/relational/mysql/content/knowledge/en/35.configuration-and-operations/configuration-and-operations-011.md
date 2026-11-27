# Configuration and Operations

## Event Scheduler, Maintenance Tasks, and External Scheduling

MySQL provides the Event Scheduler to run SQL statements on a schedule directly inside the database server. It is a convenient choice for small, data-local tasks requiring only SQL operations, such as purging batches of expired logs or updating summary tables. For workflows that must call APIs, run backups, export files, coordinate across services, perform controlled retries, or orchestrate across multiple hosts, use an external scheduler such as cron, systemd timers, Windows Task Scheduler, or an orchestration platform.

Choosing the right scheduling location is an operational decision. The Event Scheduler keeps tasks close to the data and reduces deployed components; external schedulers provide better dependency management, observability, job distribution, and recovery. Regardless of the choice, tasks still require idempotency, time bounds, overlap prevention, outcome logging, and a handling plan when MySQL or workers are interrupted.

### 1. Two Places to Coordinate Periodic Jobs

The Event Scheduler is a built-in component of MySQL Server. An event contains a schedule and an SQL statement or stored procedure call. The server checks the schedule and executes the event when due.

An external scheduler runs independently of MySQL. It can invoke a MySQL client, an application program, a script, an API, or a multi-step workflow. Common examples include cron on Linux, systemd timers, Windows Task Scheduler, Kubernetes CronJobs, or orchestration platforms like Airflow.

| Criterion | MySQL Event Scheduler | External Scheduler |
| --- | --- | --- |
| Execution location | Inside `mysqld` | A separate host, container, or orchestration service |
| Suitable jobs | Short SQL, local data maintenance, updating summary tables | Backups, ETL, file exports, API calls, multi-system or long workflows |
| Dependencies | MySQL running and `event_scheduler` enabled | Scheduler/worker and connectivity to required systems |
| Transactions | Can use transactions in stored procedures; must be designed explicitly | Workers can coordinate multiple transactions and multiple services |
| Retries and dependencies | Must be built manually in SQL or state tables | Typically has built-in retries, dependencies, queues, and alerting |
| Multi-host coordination | Requires topology control and designating the executing instance | Can use distributed schedulers, leader election, or shared locks |
| Observability | Event metadata, error log, and application-created audit tables | Platform job history, logs, metrics, and alerts |
| Non-SQL operations | Cannot directly run shell commands, make HTTP calls, or write arbitrary files | Can invoke binaries, APIs, object storage, and other services |

No single option is best for every task. Choose based on job scope, recovery requirements, and system observability.

### 2. When to Use the Event Scheduler?

The Event Scheduler is suitable when a task:

- Primarily reads or writes data within the same MySQL instance.
- Has a short duration and resource usage can be bounded via batching.
- Can be safely rerun if a previous execution was interrupted.
- Does not need to wait for an external workflow to complete.
- Can be observed via status tables or server logs.

Suitable examples include purging a batch of expired audit logs, updating hourly aggregate metrics, marking expired orders, or creating small in-database business snapshots.

Do not use the Event Scheduler as the primary tool for physical backups, compressing/uploading files to object storage, sending bulk emails, calling payment APIs, running cross-service migrations, or executing multi-hour workflows. Events only execute SQL inside MySQL; they are not an OS-level process runner.

### 3. When to Use an External Scheduler?

An external scheduler is usually better suited when a task requires one or more of the following:

1. Running external programs outside MySQL, such as `mysqlsh`, backup tools, verification scripts, or application workers.
2. Coordinating multiple data sources or services in dependency order.
3. Retries with exponential backoff, timeouts, retry caps, and dead-letter workflows.
4. Run history, centralized logs, metrics, alerts, and an operational UI.
5. Running across multiple workers, horizontal scaling, or sharding by partition/tenant.
6. Scheduling based on complex business calendars, holiday schedules, or triggers from other systems.

For example, a backup workflow may involve checking disk space, taking a consistent backup, verifying output, encrypting, uploading to object storage, verifying checksums, and sending alerts. The Event Scheduler is not the right place to orchestrate this entire chain; an external scheduler can invoke specialized tools and record step-by-step state.

### 4. Checking and Enabling the Event Scheduler

Check the current status:

```sql
SHOW GLOBAL VARIABLES LIKE 'event_scheduler';
```

Common states:

| Value | Operational Meaning |
| --- | --- |
| `ON` | The Event Scheduler is active and can execute enabled events when scheduled |
| `OFF` | The scheduler is stopped; it can be enabled again if server configuration permits |
| `DISABLED` | The scheduler was disabled at startup; it cannot be enabled at runtime with `SET GLOBAL` alone |

Where permitted, enable at runtime:

```sql
SET GLOBAL event_scheduler = ON;
```

To persist across restarts, configure the server in the appropriate option file:

```ini
[mysqld]
event_scheduler = ON
```

Or use the corresponding MySQL startup option. Enabling the scheduler is an instance-level change that must be coordinated with administrators and deployment procedures. Do not enable it blindly across every replica without determining which instances are allowed to run jobs.

### 5. Events Calling Stored Procedures to Keep Schedules Simple

For tasks with multiple SQL steps, put the logic in a stored procedure and let the event handle only scheduling. This makes it easy to run manually for testing, reuse logic, and manage privileges cleanly.

Example audit log table:

```sql
CREATE TABLE audit_log (
    id BIGINT NOT NULL AUTO_INCREMENT,
    created_at DATETIME NOT NULL,
    actor_id BIGINT NULL,
    action_name VARCHAR(100) NOT NULL,
    details JSON NULL,
    PRIMARY KEY (id),
    KEY idx_audit_created_id (created_at, id)
) ENGINE = InnoDB;
```

Stored procedure deleting at most 5,000 expired rows per run:

```sql
DELIMITER //
CREATE PROCEDURE purge_old_audit_batch()
BEGIN
    DELETE FROM audit_log
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL 90 DAY
    ORDER BY created_at ASC, id ASC
    LIMIT 5000;
END//
DELIMITER ;
```

Create an hourly event:

```sql
CREATE EVENT ev_purge_old_audit
ON SCHEDULE EVERY 1 HOUR
STARTS CURRENT_TIMESTAMP + INTERVAL 1 HOUR
ON COMPLETION PRESERVE
ENABLE
DO CALL purge_old_audit_batch();
```

This example deletes only one batch per run. The next run continues processing remaining eligible rows. This approach caps work per execution, avoids long transactions, and leaves breathing room for application workloads. If multiple consecutive batches must run, place a time limit or maximum batch count inside the procedure so the event does not monopolize resources for too long.

`DELIMITER` is a MySQL client command used to change the statement terminator when entering routines containing semicolons; it is not an SQL statement sent verbatim to the server. In migration tools, use the delimiter or routine statement mechanism supported by the tool.

### 6. Designing Maintenance Tasks in Batches

Never delete millions of records in a single transaction merely because the job runs during off-peak hours. Large transactions can hold locks for a long time, generate heavy undo/redo, slow down purge, increase replica lag, and make rollbacks expensive.

For large log tables, you should:

1. Have an index supporting the filter condition and processing order, such as `(created_at, id)`.
2. Delete a bounded number of rows per execution, such as `LIMIT 5000`.
3. Commit each batch if a procedure processes multiple batches.
4. Cap the number of batches or runtime per invocation.
5. Record the number of processed rows and progress watermark to resume on the next run.
6. Monitor lock time, deadlocks, history list length, I/O, and replica lag.

Never use `OFFSET` to skip processed batches in a changing table. For archival or data-movement jobs, use keyset/watermark pagination over a stable key—for example, resuming from the last completed `id`. Filtering conditions must ensure newly inserted or updated rows are not skipped.

For time-partitioned tables, consider dropping old partitions instead of deleting row by row. This is a DDL change requiring assessment of constraints, backups, replication, and operational rollback; the scheduler should only invoke a tested procedure.

### 7. Preventing Overlapping Executions of the Same Task

A long-running event may collide with the next scheduled trigger before the previous run finishes. Do not rely on the assumption that a scheduler automatically prevents all overlap scenarios, especially across multiple instances, failovers, or when the same logic can be invoked by both an event and an external scheduler.

For SQL tasks on a single MySQL instance, you can use a named lock via `GET_LOCK()`:

```sql
DELIMITER //
CREATE PROCEDURE run_purge_with_lock()
BEGIN
    DECLARE v_lock INT DEFAULT 0;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        IF v_lock = 1 THEN
            DO RELEASE_LOCK('maintenance.purge_old_audit');
        END IF;
        RESIGNAL;
    END;

    SELECT GET_LOCK('maintenance.purge_old_audit', 0)
    INTO v_lock;

    IF v_lock = 1 THEN
        CALL purge_old_audit_batch();
        DO RELEASE_LOCK('maintenance.purge_old_audit');
        SET v_lock = 0;
    END IF;
END//
DELIMITER ;
```

If the lock is held by another session, `GET_LOCK(..., 0)` returns immediately and the current run skips work. The handler releases the lock if the routine hits an exception and then rethrows the error. For more complex workflows, log skipped runs as well.

Named locks are scoped to a single MySQL server, not a distributed lock across independent hosts. If the same job could run on source and replica or across multiple cluster nodes, you need system-level coordination, a single leader, or a claim table with a unique key in shared storage.

### 8. Idempotency and Rerunnability

A scheduler generally triggers a job; it does not guarantee exactly-once execution. After a timeout or lost connection, a worker may not know whether a transaction committed. During retries, the same unit of work can be executed again.

Idempotent design means rerunning the same unit of work does not cause incorrect or unintended duplicate side effects. Common techniques:

- Use explicit state transitions, such as processing only rows with `status = 'pending'` and transitioning them to `processed` in the same transaction.
- Use a unique key on `job_name` and `run_key` to prevent the same job period from being recorded twice.
- Use `INSERT ... ON DUPLICATE KEY UPDATE` for summary tables when aggregations can be safely recomputed.
- Store watermarks or checkpoints and advance them only after the batch commits.
- Separate claiming from processing; include lease expiration to reclaim work abandoned by a crashed worker.

Example table recording a run period:

```sql
CREATE TABLE maintenance_job_run (
    job_name VARCHAR(100) NOT NULL,
    run_key VARCHAR(100) NOT NULL,
    started_at DATETIME NOT NULL,
    finished_at DATETIME NULL,
    status VARCHAR(20) NOT NULL,
    affected_rows BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (job_name, run_key)
) ENGINE = InnoDB;
```

The composite primary key prevents creating two rows for the same job and period. Workers can attempt to claim via `INSERT` and handle a duplicate key as an already-claimed run. You must also define how to recover stale `running` states, timeouts/leases, and result verification before permitting reruns.

### 9. Logging Outcomes and Monitoring the Event Scheduler

Never rely solely on an event existing to conclude that the job ran successfully. Monitor the latest execution, event status, and business outcome.

List events:

```sql
SHOW EVENTS FROM app_db;
```

Inspect event definition and schedule:

```sql
SHOW CREATE EVENT app_db.ev_purge_old_audit;
```

Query event metadata:

```sql
SELECT
    EVENT_SCHEMA,
    EVENT_NAME,
    DEFINER,
    TIME_ZONE,
    EVENT_TYPE,
    EXECUTE_AT,
    INTERVAL_VALUE,
    INTERVAL_FIELD,
    STARTS,
    ENDS,
    STATUS,
    LAST_EXECUTED,
    EVENT_DEFINITION
FROM information_schema.events
WHERE EVENT_SCHEMA = 'app_db';
```

`LAST_EXECUTED` identifies the most recent metadata execution timestamp; it does not replace a detailed per-batch log table. Have the procedure record `started_at`, `finished_at`, rows processed, status, and error details in a dedicated operational table. Simultaneously monitor the MySQL error log and alert when an event misses its schedule or runs abnormally long.

For external schedulers, record run ID, scheduled time, actual start/end, exit code, retry count, and logs. Synchronize server clocks and use a consistent standard time zone to correlate schedules between the scheduler and database.

### 10. Execution Privileges and Job Accounts

Events run under the security context of their `DEFINER`. Creating an event requires the `EVENT` privilege on the target schema; calling a routine requires `EXECUTE`; the definer must hold the minimum privileges required to execute SQL statements inside the routine. If the definer is dropped or privileges are revoked, the event may still exist yet fail at runtime.

Use a dedicated service account granted privileges only on necessary tables and routines. Never use `root` for maintenance events or external schedulers. When changing definers, migrating environments, or restoring databases, verify that the account and privileges exist on the target server.

External schedulers also need a dedicated database account with least privilege. Never put passwords directly on the command line, in scripts committed to Git, or in logs. Use login paths, permission-restricted option files, a secrets manager, or platform credential mechanisms; remote connections should use TLS with certificate verification per security policy.

### 11. Time Zones and Execution Timing

Events store time zone metadata attached at creation time; external schedulers depend on host or workflow time zone configuration. Without explicit alignment, schedules can drift when deploying across environments or switching regions.

Before creating an event, set the session time zone intentionally and inspect `TIME_ZONE` in `INFORMATION_SCHEMA.EVENTS`. For technical periodic jobs, UTC is usually easiest to operate and correlate in logs. For business jobs requiring local time, define how to handle Daylight Saving Time (DST), holidays, and skipped or repeated wall-clock times during clock shifts.

Check time configuration:

```sql
SELECT
    @@GLOBAL.time_zone,
    @@SESSION.time_zone,
    @@system_time_zone,
    UTC_TIMESTAMP(),
    CURRENT_TIMESTAMP();
```

Do not assume an external scheduler and MySQL use the same time zone merely because both run on the same host. Configure them explicitly and log execution times in UTC for cross-system comparison.

### 12. Event Scheduler in Replication and Failover

Events are database objects, and event definitions can be written to the binary log and replicated depending on configuration. That does not mean every replica should execute the same maintenance job. If source and replica simultaneously run purge, archival, or summary jobs, they can create duplicate load, data divergence, or execute writes on non-writer nodes.

For replication/failover systems:

1. Define which node is allowed to run each job; typically only the current writer/primary performs write jobs.
2. Check `event_scheduler`, `STATUS`, and event state on both source and replicas.
3. Use appropriate state configuration so events do not execute on replicas; re-verify after promotion/failover.
4. After changing primary, enable jobs on the new node only after confirming the old node has stopped or lost execution authority.
5. Use idempotency and appropriately scoped locks/claims to reduce the risk of two nodes claiming the same job period.
6. Monitor replica lag because write-heavy maintenance jobs can generate large amounts of binlogs.

The `DISABLE ON SLAVE` status appears in syntax/documentation in some versions, and metadata status may display as `SLAVESIDE_DISABLED`. Check the syntax, terminology, and behavior for your exact running MySQL version. Never rely on a single disable clause in place of a verified failover procedure.

External schedulers can also double-run after failover if multiple workers see the schedule. Use leader election, distributed locks, or atomic claims in a shared data store; `GET_LOCK()` on one server does not protect independent MySQL instances.

### 13. Example External Scheduler Calling MySQL

For tasks requiring scripts, an external scheduler can invoke the MySQL client or an application worker. Example cron job running a tested script:

```cron
15 2 * * * /usr/local/bin/run-db-maintenance.sh
```

The script can invoke the MySQL client using a login path configured for the service account:

```bash
mysql --login-path=maintenance app_db < /opt/db-jobs/rebuild_daily_summary.sql
```

Never place passwords directly in the command. The SQL file should include proper transactions, filtering, and error handling; the script must check the client exit code and return failure status to the scheduler to trigger alerts or retries.

On Windows, Task Scheduler can invoke a PowerShell script; on Kubernetes, a CronJob can launch a worker pod. Regardless of platform, configure concurrency policy, deadlines, retry/backoff, secrets, and logging. Local locks like `flock` only prevent two processes on the same host; they do not replace distributed locks if jobs can run across multiple hosts.

### 14. Comparing Implementation Approaches for Common Maintenance Tasks

| Task | Typical Suitable Choice | Reason |
| --- | --- | --- |
| Hourly batch deletion of expired logs | Event Scheduler or external worker | Short SQL, runs close to data; requires batching and logging |
| Hourly update of small summary tables | Event Scheduler | Local SQL computation, easy to rerun |
| Physical backup and object storage upload | External scheduler | Needs backup tools, files, encryption, upload, and verification |
| CSV export and delivery to partners | External scheduler | Needs filesystem/network/API access and dedicated credentials |
| Cross-database ETL | External scheduler | Needs dependencies, checkpoints, and multi-step retries |
| Sending reminder emails | External scheduler or app queue | MySQL is not an email service; needs deduplication and retries |
| Index rebuild / large-table DDL maintenance | External operational procedure | Needs maintenance window, disk checks, lock/replication monitoring |
| Jobs that must run only on primary post-failover | Topology-aware scheduler | Must guarantee single execution location and post-promotion recovery |

### 15. Procedure for Deploying a Scheduled Job

1. **Define requirements:** schedule, time zone, SLA, volume, max runtime, and behavior on missed runs.
2. **Choose execution location:** Event Scheduler for local SQL; external scheduler for multi-step or cross-system workflows.
3. **Design data handling:** indexes, batch size, watermarks, job state, overlap lock, and audit table.
4. **Design failure handling:** timeouts, retries, idempotency, deadlock handling, lease recovery, and alerts.
5. **Design privileges:** dedicated definer/service account, least privilege, securely managed secrets.
6. **Test manually:** run the routine/script against test data, verify output, and test rerunnability.
7. **Enable schedule:** deploy on one instance first, verify time zone, scheduler state, and first run.
8. **Monitor:** duration, row counts, errors, lock waits, I/O, replica lag, and schedule drift.
9. **Test recovery:** simulate worker crashes, MySQL restarts, delayed runs, and failover in a test environment.
10. **Manage lifecycle:** establish procedures to disable, reschedule, transfer definer, rotate secrets, and retire unused jobs.

### 16. Checklist Before Choosing Event Scheduler vs. External Scheduler

1. Does the job consist solely of SQL inside one MySQL instance, or does it call external systems?
2. Are duration and row counts bounded by batching?
3. Can it be safely rerun after a timeout or lost connection?
4. Are both concurrent-run prevention and multi-node execution prevention in place?
5. Are timestamps, outcomes, row counts, errors, and checkpoints logged?
6. Are time zones, DST, and behavior during MySQL/scheduler downtime clearly defined?
7. Does the definer or service account follow least privilege with protected credentials?
8. Have replication, failover, replica lag, and writer placement been verified?
9. Are timeouts, retry/backoff, alerts, and failure runbooks configured?
10. Is there an owner responsible for disabling or updating the job when business requirements change?

The Event Scheduler is a compact choice for short, local, rerunnable SQL tasks. External schedulers suit backups, ETL, APIs, and workflows requiring observability or cross-component orchestration. In either case, a reliable job must have bounded batches, idempotency, overlap protection, least privilege, operational logging, and a recovery procedure when schedules fail to run as planned.
