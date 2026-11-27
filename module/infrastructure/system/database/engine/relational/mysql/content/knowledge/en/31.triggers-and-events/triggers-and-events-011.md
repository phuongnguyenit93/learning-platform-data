# Tracking Failed Events and Designing Retryable Jobs

This lesson belongs to the **Triggers and Events** chapter of the **DATABASE_MYSQL** module. The module aims to master MySQL from table design, data types, keys, and SQL queries through indexing, transactions, concurrency control, execution plan reading, query tuning, privilege management, backups, and relational database operational troubleshooting. The Event Scheduler runs scheduled tasks directly inside MySQL, yet event metadata is not a complete execution history, and a failed run does not automatically become a safely replayable transaction. Reliable operations require combining the error log, metadata, a job state table, overlap-prevention locks, idempotency, backoff retries, and recovery procedures.

After this lesson, you will be able to verify whether the Event Scheduler is genuinely running, detect failed events via the error log, distinguish STATUS from business outcomes, read INFORMATION_SCHEMA.EVENTS, verify DEFINER and execution privileges, prevent overlapping runs, design unique run keys, store attempt/error/next_retry_at, roll back failed work, replay safely, and handle tasks exceeding retry limits.

## 1. The Event Scheduler Is Not a Complete Job Queue System

The MySQL Event Scheduler executes SQL statements on a schedule. An event can run once or repeat:

~~~sql
CREATE EVENT ev_cleanup_sessions
ON SCHEDULE EVERY 1 HOUR
DO
    DELETE FROM sessions
    WHERE expires_at < CURRENT_TIMESTAMP;
~~~

The Event Scheduler fits tasks such as:

- Cleaning up expired data.
- Aggregating daily reports.
- Checking and marking overdue records.
- Creating periodic snapshots.
- Calling a stored procedure to process a batch of work.

However, an event itself does not provide all the capabilities of a job queue:

- Does not store detailed business history per execution.
- Does not store checkpoints for individual processed records.
- Has no built-in business-level retry/backoff policy per run.
- Does not guarantee a recurring event will never overlap with itself.
- Does not automatically make statements inside the event idempotent.
- Does not know whether sending an email, calling an HTTP API, or writing to another system succeeded.

The Event Scheduler is a scheduled trigger. Job state and history should be stored in application-designed tables.

When an execution of a recurring event fails, the Event Scheduler writes diagnostics to the error log; it does not turn that failed run into a backoff-scheduled retry item to replay immediately. The next invocation still follows the event schedule. To retry the same logical run, the procedure must recognize the old run key and check next_retry_at/status in a job table.

A practical architecture:

~~~text
Event Scheduler
      |
      v
Stored procedure / Job dispatcher
      |
      +----> Job run table
      |        - run key
      |        - status
      |        - attempts
      |        - next retry
      |        - last error
      |
      +----> Business processing transaction
      |        - summary
      |        - ledger
      |        - checkpoint
      |
      +----> Outbox table
               - message key
               - payload
               - delivery status
~~~

When an event fails, the error log helps pinpoint the technical cause. The job run table reveals which business job remains incomplete and where replay can resume.

## 2. Verifying Whether the Event Scheduler Is Active

The global variable event_scheduler determines whether the Event Scheduler is enabled.

~~~sql
SHOW GLOBAL VARIABLES LIKE 'event_scheduler';
~~~

Meaningful values:

| Value | Meaning |
|---|---|
| ON | Scheduler is enabled and the scheduler thread is running |
| OFF | Scheduler is currently stopped; can be toggled at runtime with sufficient privileges |
| DISABLED | Scheduler was disabled at startup; cannot be re-enabled via SET GLOBAL alone at runtime |

Enable the scheduler when its value is OFF:

~~~sql
SET GLOBAL event_scheduler = ON;
~~~

This command requires sufficient privileges to modify global system variables. To persist across restarts, configure it in the server configuration file, such as my.cnf or my.ini:

~~~ini
[mysqld]
event_scheduler=ON
~~~

If the server started with event_scheduler=DISABLED, you must update the startup configuration and restart following operational procedures.

### Checking the Scheduler Thread

~~~sql
SHOW PROCESSLIST;
~~~

When the scheduler is running, the process list includes the Event Scheduler daemon thread. A user needs the PROCESS privilege to view all server processes.

You can also inspect status alongside other summary diagnostics with an administrative command:

~~~text
mysqladmin debug
~~~

This command writes Event Scheduler debug information to the error log. Use it only for deep diagnostics with appropriate administrative privileges.

Never conclude the scheduler is working solely because event_scheduler equals ON. Check the thread, event schedules, error log, and business outcomes.

## 3. Reading Event Metadata in INFORMATION_SCHEMA.EVENTS

INFORMATION_SCHEMA.EVENTS provides metadata for defined events.

~~~sql
SELECT
    EVENT_SCHEMA,
    EVENT_NAME,
    DEFINER,
    TIME_ZONE,
    EVENT_TYPE,
    EXECUTE_AT,
    INTERVAL_VALUE,
    INTERVAL_FIELD,
    STATUS,
    LAST_EXECUTED,
    LAST_ALTERED,
    ON_COMPLETION,
    EVENT_COMMENT
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA = DATABASE()
ORDER BY EVENT_NAME;
~~~

Key fields:

| Field | Meaning |
|---|---|
| EVENT_SCHEMA | Schema containing the event |
| EVENT_NAME | Event name |
| DEFINER | Account used when the event executes |
| TIME_ZONE | Time zone used for the schedule and event execution session |
| EVENT_TYPE | ONE TIME or RECURRING |
| EXECUTE_AT | Timestamp for a one-time event |
| INTERVAL_VALUE / INTERVAL_FIELD | Interval for a recurring event |
| STARTS / ENDS | Schedule start and end bounds |
| STATUS | ENABLED, DISABLED, or REPLICA_SIDE_DISABLED |
| LAST_EXECUTED | Timestamp when the event most recently started executing |
| LAST_ALTERED | Timestamp when the event definition was last modified |
| ON_COMPLETION | PRESERVE or NOT PRESERVE |
| EVENT_COMMENT | Event comment |

### STATUS Is Not a Success State

STATUS only indicates whether the event is enabled for the scheduler to execute. It does not indicate that statements inside the event succeeded.

For example:

- ENABLED: event is enabled, yet may fail because DEFINER lacks privileges.
- DISABLED: event is disabled; the scheduler does not execute it.
- REPLICA_SIDE_DISABLED: event was replicated from source to replica and does not execute on the replica under MySQL's replication rules.

LAST_EXECUTED is also not a completion timestamp. This field represents when the event began executing. It does not record duration, rows processed, SQLSTATE, or business outcomes.

If LAST_EXECUTED is NULL, the event has no recorded execution yet. When an event is ENABLED with no recorded runs, check event_scheduler, STARTS/ENDS, time zone, DEFINER, and the error log.

To view the full definition:

~~~sql
SHOW CREATE EVENT ev_cleanup_sessions;
~~~

To list events:

~~~sql
SHOW EVENTS FROM app_db;
~~~

Do not use LAST_EXECUTED or STATUS alone as a success/failure dashboard. Store job execution state in a dedicated table.

## 4. Where Are Failed Events Logged?

The MySQL Event Scheduler writes information about event executions ending with errors or warnings to the MySQL Server error log.

A message may look like:

~~~text
[ERROR] Event Scheduler: [job_runner@localhost][app_db.ev_daily_report]
INSERT command denied to user ...
[Note] Event Scheduler: [app_db.ev_daily_report] event execution failed.
~~~

The error log is the first place to check when an enabled event produces no results.

### Reading the Error Log via Performance Schema

In MySQL 9.7, if the error log sink is configured to support Performance Schema, recent messages can be queried from performance_schema.error_log.

~~~sql
SELECT
    LOGGED,
    THREAD_ID,
    PRIO,
    ERROR_CODE,
    SUBSYSTEM,
    DATA
FROM performance_schema.error_log
WHERE DATA LIKE '%Event Scheduler%'
   OR DATA LIKE '%event execution failed%'
ORDER BY LOGGED DESC
LIMIT 100;
~~~

Commonly used columns:

- LOGGED: timestamp when the message was logged.
- THREAD_ID: logging thread; for background threads, this may be 0.
- PRIO: System, Error, Warning, or Note.
- ERROR_CODE: server error code.
- SUBSYSTEM: subsystem that emitted the message.
- DATA: message text.

performance_schema.error_log is a view over a fixed-size in-memory ring buffer. When the buffer fills, older messages are evicted to make room for newer ones. It does not replace long-term log retention systems.

### If error_log Has No Rows

Not every error log configuration writes events to Performance Schema. Traditional and JSON sinks support this capability, while log_error_services controls which sinks are active.

Check:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'log_error_services';
SHOW GLOBAL VARIABLES LIKE 'log_error';
~~~

If error_log has no rows, read the error log file on the host or your centralized log aggregation system per organizational procedures. Never require the FILE privilege for an application just to read error logs.

### Warnings Are Also Logged

The Event Scheduler also logs warning-level diagnostics. For instance, SELECT ... INTO returning zero rows can emit a No data warning; returning more than one row raises Result consisted of more than one row.

For frequently running events, unhandled warnings can create substantial log noise.

Example handling NOT FOUND inside a stored program:

~~~sql
DECLARE v_value BIGINT DEFAULT NULL;
DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_value = NULL;

SELECT id
INTO v_value
FROM source_queue
WHERE status = 'READY'
ORDER BY id
LIMIT 1;
~~~

If business logic only needs one row, LIMIT 1 and an explicit ORDER BY prevent multi-row errors. If missing data must be detected, handle NOT FOUND explicitly.

Do not mask important warnings with a catch-all handler. Handle only understood conditions with clear business behavior.

## 5. Checking DEFINER and Execution Privileges

An event can succeed during CREATE EVENT yet fail inside its DO statement when the scheduler runs it.

Common causes:

- The DEFINER account lacks required SELECT, INSERT, UPDATE, or DELETE privileges.
- The DEFINER was deleted or altered.
- A stored procedure called by the event has an unexpected DEFINER or SQL SECURITY setting.
- Tables, schemas, or privileges depended upon by the routine changed.
- The event runs in a different schema or time zone than the operator assumed.

Check:

~~~sql
SELECT
    EVENT_SCHEMA,
    EVENT_NAME,
    DEFINER,
    STATUS,
    EVENT_DEFINITION
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA = 'app_db';
~~~

Inspect definition:

~~~sql
SHOW CREATE EVENT app_db.ev_daily_report;
~~~

Check the DEFINER account's privileges using an administrative account:

~~~sql
SHOW GRANTS FOR 'job_runner'@'localhost';
~~~

### Two Privilege Layers to Distinguish

- The EVENT privilege allows creating, altering, dropping, and displaying events at schema or global scope.
- Privileges to execute statements inside the event must be held by the executing account per DEFINER.
- If the event calls a stored procedure, also verify EXECUTE privilege and the procedure's security context.
- Toggling event_scheduler modifies a global system variable and requires the corresponding variable administration privilege.

Example granting event management on a schema:

~~~sql
GRANT EVENT ON app_db.* TO 'scheduler_admin'@'localhost';
~~~

Do not grant broader privileges than necessary to job accounts. Use a dedicated DEFINER account with least privilege on the exact tables and routines required.

Deleting a DEFINER account can leave stored objects orphaned. Before dropping or modifying an account, review all events, routines, triggers, and views referencing that account.

## 6. Time Zones and Execution Schedules

Timestamps in an event are interpreted in the session time_zone active at CREATE EVENT or ALTER EVENT time. That time zone becomes the event's TIME_ZONE and applies inside the event execution session.

Check:

~~~sql
SELECT
    EVENT_SCHEMA,
    EVENT_NAME,
    TIME_ZONE,
    STARTS,
    ENDS,
    EXECUTE_AT,
    LAST_EXECUTED
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA = DATABASE();
~~~

If reporting follows Vietnam business days, standardize on Asia/Ho_Chi_Minh rather than mixing UTC and local time.

Example configuring the session before creating an event:

~~~sql
SET time_zone = 'Asia/Ho_Chi_Minh';

CREATE EVENT ev_daily_report_retry
ON SCHEDULE EVERY 5 MINUTE
STARTS CURRENT_TIMESTAMP + INTERVAL 1 MINUTE
DO
    CALL app_db.sp_refresh_daily_sales(CURRENT_DATE - INTERVAL 1 DAY);
~~~

Named time zones must exist in MySQL's time zone tables. If time zone tables have not been loaded, a fixed offset can be used, taking into account environmental clock-change rules.

Never assume timestamps in CREATE EVENT are interpreted in the client machine's local time zone. Check TIME_ZONE after creating the event.

## 7. The Event Scheduler Can Create Overlapping Runs

If an event repeats every 5 minutes but each run takes 8 minutes, multiple instances can run concurrently.

Example:

~~~text
12:00  Instance A starts
12:05  Instance B starts while A is not finished
12:08  Instance A finishes
12:10  Instance C may start while B is not finished
~~~

This can cause:

- The same reporting period being computed twice.
- Two workers grabbing the same queue row.
- Two transactions updating the same aggregate.
- Duplicate notifications sent.
- Increased lock waits and deadlocks.
- CPU/I/O resource pileups.

MySQL recommends using a concurrency guard if an event may exceed its schedule interval. You can use GET_LOCK(), row locks, or table locks.

### Using a Named Lock for a Single Job Type

~~~sql
SELECT GET_LOCK('app_db.daily_sales_refresh', 0);
~~~

Results:

- 1: lock acquired.
- 0: lock is held by another session or timed out.
- NULL: an error occurred.

Once acquired, perform the work and release:

~~~sql
SELECT RELEASE_LOCK('app_db.daily_sales_refresh');
~~~

Named locks belong to the session, not the transaction. COMMIT or ROLLBACK does not automatically release a named lock. You must call RELEASE_LOCK or close the connection.

If a procedure errors, ensure a handler releases the lock before RESIGNAL. If the connection closes, MySQL releases that session's named locks.

GET_LOCK only coordinates within the same MySQL server. Do not treat it as a distributed lock across multiple servers or a replacement for leader election in multi-primary architectures.

### Using a Row Lock by Run Key

For daily jobs, a row in job_run has primary key (job_name, run_date). The procedure acquires that row with SELECT ... FOR UPDATE. Two runs with the same run key serialize on that locked row; the second run reads status SUCCEEDED and exits.

Row locks fit well when job state already lives in InnoDB and locking must be coupled with state updates.

## 8. Idempotency: The Prerequisite for Safe Retries

An idempotent job can be rerun with the same input without duplicating or skewing the final outcome.

Not every SQL statement is idempotent.

Non-retry-safe example:

~~~sql
UPDATE account_balance
SET balance = balance + 100
WHERE account_id = 42;
~~~

If the first run committed yet the event lost connection before recording success, a retry adds another 100.

More idempotent example:

~~~sql
UPDATE account_balance
SET balance = 1500
WHERE account_id = 42;
~~~

If the target value is always 1500 from a fixed snapshot, rerunning does not accumulate. However, you must ensure that value is correct and does not overwrite a newer update.

Design principles:

1. Every logical run has a deterministic run key, such as daily_sales:2026-11-18.
2. Put a UNIQUE or PRIMARY KEY on the run key to prevent creating two identical logical runs.
3. Record SUCCEEDED in the same transaction as the business data.
4. On failure, roll back business data before recording FAILED status.
5. Do not use unguarded incremental addition in retryable jobs.
6. If writing a ledger, each business operation must carry a unique operation_id.
7. When calling external systems, use an outbox and an idempotency key on the receiver.
8. Multi-batch jobs need durable checkpoints, and each batch itself must be idempotent.

### At-Least-Once and Exactly-Once

With event schedulers, timeouts, crashes, retries, and external systems, never assume an action occurs strictly once across the entire system.

Practical designs usually combine at-least-once delivery/execution with idempotency or deduplication. A request may be retried, while business keys ensure the effect is applied only once.

End-to-end exactly-once requires coordinated transactions and deduplication across all participating systems; a MySQL COMMIT cannot by itself guarantee an email or HTTP request executes only once.

## 9. Designing a Run-Tracking Table

Example job_run table storing job state by business date:

~~~sql
CREATE TABLE scheduled_job_run (
    job_name VARCHAR(64) NOT NULL,
    run_date DATE NOT NULL,
    status ENUM(
        'PENDING',
        'RUNNING',
        'SUCCEEDED',
        'FAILED',
        'DEAD'
    ) NOT NULL,
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    max_attempts INT UNSIGNED NOT NULL DEFAULT 5,
    next_retry_at DATETIME(6) NULL,
    started_at DATETIME(6) NULL,
    finished_at DATETIME(6) NULL,
    last_sqlstate CHAR(5) NULL,
    last_error_code INT NULL,
    last_error_message VARCHAR(1000) NULL,
    PRIMARY KEY (job_name, run_date),
    KEY idx_job_retry (status, next_retry_at)
) ENGINE=InnoDB;
~~~

Column meanings:

| Column | Purpose |
|---|---|
| job_name | Identifies the job type |
| run_date | Run key by business date |
| status | Processing state |
| attempt_count | Number of attempts tried |
| max_attempts | Retry limit |
| next_retry_at | Earliest timestamp eligible for retry |
| started_at | Start time of most recent attempt |
| finished_at | End time of most recent attempt |
| last_sqlstate | SQLSTATE of most recent error |
| last_error_code | MySQL error code |
| last_error_message | Text of most recent error |

PRIMARY KEY (job_name, run_date) prevents two records for the same job and date. If business rules allow multiple independent runs in one day, the run key must include period, batch id, or version.

### Inspecting Status

~~~sql
SELECT
    job_name,
    run_date,
    status,
    attempt_count,
    max_attempts,
    next_retry_at,
    started_at,
    finished_at,
    last_sqlstate,
    last_error_code,
    last_error_message
FROM scheduled_job_run
ORDER BY run_date DESC, job_name;
~~~

Find jobs awaiting retry:

~~~sql
SELECT
    job_name,
    run_date,
    attempt_count,
    max_attempts,
    next_retry_at,
    last_error_message
FROM scheduled_job_run
WHERE status = 'FAILED'
  AND next_retry_at <= CURRENT_TIMESTAMP(6)
ORDER BY next_retry_at;
~~~

Find jobs that exceeded retry limits:

~~~sql
SELECT
    job_name,
    run_date,
    attempt_count,
    last_error_message
FROM scheduled_job_run
WHERE status = 'DEAD'
ORDER BY run_date DESC;
~~~

## 10. Error Handling and Retry Workflow in Transactions

For a job that can recompute all data for a date, you can use this pattern:

1. Insert or locate the job_run record with the unique run key.
2. Commit the coordination record so it exists independently of the processing transaction.
3. Start the processing transaction.
4. Lock the job_run record with SELECT ... FOR UPDATE.
5. If already SUCCEEDED or before next_retry_at, exit early.
6. Mark RUNNING and increment attempt_count.
7. Delete old summary data for the date range.
8. Recompute and INSERT new data.
9. Mark SUCCEEDED in the same transaction.
10. COMMIT.
11. On error: ROLLBACK business data, then write FAILED/DEAD and error details in a new transaction, and RESIGNAL so the Event Scheduler logs the error.

The key point is that summary data and SUCCEEDED status must commit together. If summary updates commit while SUCCEEDED is written in a separate transaction, a crash between the two steps can cause the job to rerun and duplicate effects.

### Example Summary Table

~~~sql
CREATE TABLE daily_sales_summary (
    sales_date DATE NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    order_count BIGINT UNSIGNED NOT NULL,
    revenue DECIMAL(18,2) NOT NULL,
    refreshed_at DATETIME(6) NOT NULL,
    PRIMARY KEY (sales_date, product_id),
    KEY idx_summary_product_date (product_id, sales_date)
) ENGINE=InnoDB;
~~~

Each row represents one product on one day. The primary key defines the report grain.

## 11. Example Retry-Safe Stored Procedure

The following example assumes these InnoDB tables exist:

- orders(order_id, status, created_at).
- order_items(order_item_id, order_id, product_id, quantity, unit_price).
- scheduled_job_run as defined above.
- daily_sales_summary as defined above.

The procedure recomputes the entire summary for a day. Each day has one unique run key.

~~~sql
DELIMITER //

CREATE PROCEDURE sp_refresh_daily_sales(IN p_sales_date DATE)
main: BEGIN
    DECLARE v_status VARCHAR(16);
    DECLARE v_retry_at DATETIME(6);
    DECLARE v_sqlstate CHAR(5);
    DECLARE v_error_code INT;
    DECLARE v_error_message TEXT;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1
            v_sqlstate = RETURNED_SQLSTATE,
            v_error_code = MYSQL_ERRNO,
            v_error_message = MESSAGE_TEXT;

        ROLLBACK;

        START TRANSACTION;

        UPDATE scheduled_job_run
        SET
            status = CASE
                WHEN attempt_count + 1 >= max_attempts THEN 'DEAD'
                ELSE 'FAILED'
            END,
            next_retry_at = CASE
                WHEN attempt_count + 1 >= max_attempts THEN NULL
                ELSE CURRENT_TIMESTAMP(6) + INTERVAL 5 MINUTE
            END,
            finished_at = CURRENT_TIMESTAMP(6),
            last_sqlstate = v_sqlstate,
            last_error_code = v_error_code,
            last_error_message = LEFT(v_error_message, 1000),
            attempt_count = LEAST(attempt_count + 1, max_attempts)
        WHERE job_name = 'daily_sales'
          AND run_date = p_sales_date;

        COMMIT;
        RESIGNAL;
    END;

    IF p_sales_date IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Sales date is required';
    END IF;

    INSERT INTO scheduled_job_run (
        job_name,
        run_date,
        status,
        attempt_count,
        max_attempts
    )
    VALUES (
        'daily_sales',
        p_sales_date,
        'PENDING',
        0,
        5
    ) AS incoming
    ON DUPLICATE KEY UPDATE
        job_name = incoming.job_name;

    COMMIT;

    START TRANSACTION;

    SELECT status, next_retry_at
    INTO v_status, v_retry_at
    FROM scheduled_job_run
    WHERE job_name = 'daily_sales'
      AND run_date = p_sales_date
    FOR UPDATE;

    IF v_status IN ('SUCCEEDED', 'DEAD') THEN
        COMMIT;
        LEAVE main;
    END IF;

    IF v_status = 'FAILED'
       AND v_retry_at IS NOT NULL
       AND v_retry_at > CURRENT_TIMESTAMP(6) THEN
        COMMIT;
        LEAVE main;
    END IF;

    UPDATE scheduled_job_run
    SET
        status = 'RUNNING',
        attempt_count = attempt_count + 1,
        started_at = CURRENT_TIMESTAMP(6),
        finished_at = NULL,
        last_sqlstate = NULL,
        last_error_code = NULL,
        last_error_message = NULL
    WHERE job_name = 'daily_sales'
      AND run_date = p_sales_date;

    DELETE FROM daily_sales_summary
    WHERE sales_date = p_sales_date;

    INSERT INTO daily_sales_summary (
        sales_date,
        product_id,
        order_count,
        revenue,
        refreshed_at
    )
    SELECT
        p_sales_date,
        oi.product_id,
        COUNT(DISTINCT o.order_id),
        SUM(oi.quantity * oi.unit_price),
        CURRENT_TIMESTAMP(6)
    FROM orders AS o
    JOIN order_items AS oi
        ON oi.order_id = o.order_id
    WHERE o.status = 'PAID'
      AND o.created_at >= p_sales_date
      AND o.created_at < p_sales_date + INTERVAL 1 DAY
    GROUP BY oi.product_id;

    UPDATE scheduled_job_run
    SET
        status = 'SUCCEEDED',
        next_retry_at = NULL,
        finished_at = CURRENT_TIMESTAMP(6),
        last_sqlstate = NULL,
        last_error_code = NULL,
        last_error_message = NULL
    WHERE job_name = 'daily_sales'
      AND run_date = p_sales_date;

    COMMIT;
END//

DELIMITER ;
~~~

In a single-table UPDATE, MySQL evaluates assignments left to right. Therefore status and next_retry_at are computed from the prior attempt_count plus 1; the attempt_count assignment is placed last. Preserve this order when editing the example so the max_attempts threshold does not skew.

### Why Is This Procedure Retryable?

- The run key (daily_sales, run_date) is unique.
- If already SUCCEEDED, subsequent calls skip.
- If FAILED and before next_retry_at, subsequent calls skip.
- When retried, DELETE and INSERT execute inside the same transaction.
- If INSERT fails, ROLLBACK restores the previously committed summary.
- The handler records FAILED or DEAD after rollback.
- RESIGNAL causes the Event Scheduler to log the error to the error log.
- When attempt count reaches max_attempts, the job transitions to DEAD and requires operator intervention.

This procedure owns its transactions. It issues COMMIT before starting the processing transaction to persist the coordination record, so it must never be called inside a caller's business transaction that the caller expects to keep open. In the event example, the procedure is called from a dedicated session created by the Event Scheduler.

The pattern above illustrates a daily job on a single server. For multi-batch jobs, maintain per-batch checkpoints and batch-level overlap locks.

## 12. Creating an Event to Re-Invoke the Same Run Key

Create an event repeating every 5 minutes to call the procedure for the previous business day:

~~~sql
SET time_zone = 'Asia/Ho_Chi_Minh';

CREATE EVENT ev_retry_daily_sales
ON SCHEDULE EVERY 5 MINUTE
STARTS CURRENT_TIMESTAMP + INTERVAL 1 MINUTE
COMMENT 'Retry daily sales summary until success or DEAD'
DO
    CALL sp_refresh_daily_sales(CURRENT_DATE - INTERVAL 1 DAY);
~~~

Mechanism:

- Every time the event runs, the run key is yesterday according to the event's TIME_ZONE.
- If the job already SUCCEEDED, the procedure skips.
- If the previous run FAILED and next_retry_at has not been reached, the procedure skips.
- Once the retry time arrives, the procedure tries again.
- On success, status becomes SUCCEEDED.
- If max_attempts is exceeded, status becomes DEAD and subsequent calls stop processing.

This is a simple retry pump for a single job type. In systems with many jobs, build a dispatcher reading a queue of due run keys and processing them in batches.

This example assumes yesterday's data is complete when the first run succeeds. If late-arriving orders or post-hoc edits occur, SUCCEEDED status will cause the same run key to be skipped. In that case, you need a close watermark/cutoff lag, a new revision key, or an audited process to explicitly reopen affected date ranges.

### Enabling and Inspecting the Event

~~~sql
ALTER EVENT ev_retry_daily_sales ENABLE;

SHOW CREATE EVENT ev_retry_daily_sales;

SELECT
    EVENT_NAME,
    STATUS,
    DEFINER,
    TIME_ZONE,
    LAST_EXECUTED
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA = DATABASE()
  AND EVENT_NAME = 'ev_retry_daily_sales';
~~~

The event only executes when the Event Scheduler is enabled. Check both event_scheduler and the error log after deployment.

## 13. Classifying Errors Before Retrying

Not every error should be retried endlessly.

| Error Category | Examples | Handling Strategy |
|---|---|---|
| Transient | Deadlock, lock wait timeout, temporary resource contention | Retry with backoff and attempt limit |
| Connection loss | Connection dropped mid-execution | Check whether transaction committed; retry using idempotent run key |
| Privileges | DEFINER lacks INSERT/UPDATE/EXECUTE | Fix grants, then perform controlled retry |
| Schema | Column renamed, table dropped | Stop retries, fix migration or routine |
| Data | Invalid value, constraint violation | Move to DEAD or quarantine for remediation |
| Logic | Division by zero, broken business assumption | Fix code; do not retry unchanged |
| Configuration | Scheduler OFF, wrong time zone, event DISABLED | Fix configuration and verify schedule |

Retrying a syntax error or missing privilege will not make it heal itself. Continuous retries create log spam, extra load, and obscure the root error.

### Backoff

Instead of retrying back-to-back, increase the delay between attempts:

- Attempt 1: short wait.
- Attempt 2: longer wait.
- Subsequent attempts: exponential backoff capped at a maximum interval.
- Optionally add jitter so many jobs do not retry at the exact same instant.

The simple example in this lesson uses a fixed 5-minute interval. Production should choose backoff based on SLA, error class, and system load.

## 14. Preventing Two Event Instances from Processing the Same Job

An event may run longer than its schedule interval. Use one of these approaches:

### Approach A: Lock the job_run Row

SELECT ... FOR UPDATE on PRIMARY KEY (job_name, run_date) serializes executions for the same run key. After the first worker commits SUCCEEDED, the second worker reads that status and exits.

### Approach B: Named Lock

GET_LOCK fits when locking an entire job type on a single server. Call RELEASE_LOCK on both success and failure paths.

### Approach C: Leases for Long-Running Jobs

If a job must commit in batches and cannot hold a single long transaction, use a lease:

- owner_id identifies the worker.
- lease_until defines how long ownership is valid.
- heartbeat_at shows the worker is still alive.
- another worker only claims the job once the lease expires.
- every update checks owner_id so a stale worker cannot overwrite a newer worker.

Leases enable recovery when a worker dies, yet you must handle a stalled old worker waking up after lease expiration. Use a monotonically increasing fencing token to reject operations from old workers.

Never hold an InnoDB transaction open for hours just to lock a large job. Split into batches, checkpoint progress, and ensure every batch is retryable.

## 15. Tasks with External Side Effects: Use an Outbox

A MySQL transaction cannot be atomic with an external HTTP request or email send.

Example:

1. Procedure updates order to PAID.
2. Procedure sends email.
3. Connection drops before recording that the email was sent.
4. Retrying the procedure sends the email a second time.

You cannot use ROLLBACK to recall an email already sent.

The standard solution is a transactional outbox:

~~~sql
CREATE TABLE event_outbox (
    message_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    message_key VARCHAR(128) NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    payload JSON NOT NULL,
    status ENUM('PENDING', 'PROCESSING', 'SENT', 'FAILED') NOT NULL,
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    created_at DATETIME(6) NOT NULL,
    sent_at DATETIME(6) NULL,
    UNIQUE KEY uq_outbox_message_key (message_key),
    KEY idx_outbox_pending (status, created_at)
) ENGINE=InnoDB;
~~~

In the same transaction that updates the order:

~~~sql
START TRANSACTION;

UPDATE orders
SET status = 'PAID'
WHERE order_id = 1001;

INSERT INTO event_outbox (
    message_key,
    event_type,
    payload,
    status,
    created_at
)
VALUES (
    'order-paid:1001',
    'ORDER_PAID',
    JSON_OBJECT('order_id', 1001),
    'PENDING',
    CURRENT_TIMESTAMP(6)
);

COMMIT;
~~~

A separate worker reads the outbox, sends the message, and marks it SENT. If sending succeeds yet connection drops before updating SENT, the worker may send again. The receiving system should support idempotency key message_key or deduplicate on that key.

An outbox guarantees recording the intent to publish in the same business transaction. It does not by itself guarantee the external system receives the message only once.

## 16. Recovery and Manual Retry

When a job transitions to FAILED:

1. Read last_error_message, SQLSTATE, and error code.
2. Cross-check the Event Scheduler error log.
3. Determine whether the error is transient or requires config/code/data fixes.
4. Verify whether previous summary data remained intact.
5. Fix the root cause.
6. Set next_retry_at to the current time if you want the dispatcher to retry immediately.
7. Keep attempt_count intact for auditing.

Example making a FAILED job immediately eligible for retry:

~~~sql
UPDATE scheduled_job_run
SET next_retry_at = CURRENT_TIMESTAMP(6)
WHERE job_name = 'daily_sales'
  AND run_date = '2026-11-18'
  AND status = 'FAILED';
~~~

Never blindly reset DEAD back to PENDING without reviewing the error and deciding whether extra attempts are permitted. If reopening, log the operator, timestamp, reason, and new attempt policy.

### If the Event Is DISABLED

After verifying root cause and privileges:

~~~sql
ALTER EVENT ev_retry_daily_sales ENABLE;
~~~

To pause an event while fixing an issue:

~~~sql
ALTER EVENT ev_retry_daily_sales DISABLE;
~~~

Disabling an event does not delete job_run. When re-enabled, the procedure can resume from durable state in the job table.

### If the Scheduler Is OFF

~~~sql
SET GLOBAL event_scheduler = ON;
~~~

Verify global variable privileges and persistence across restarts.

## 17. Running Events on Replicas and HA Environments

Events are stored in metadata and replicate according to MySQL replication rules. On a replica, events created on the source normally carry status REPLICA_SIDE_DISABLED to prevent duplicate execution.

Inspect:

~~~sql
SELECT
    EVENT_SCHEMA,
    EVENT_NAME,
    DEFINER,
    STATUS,
    ORIGINATOR
FROM INFORMATION_SCHEMA.EVENTS
ORDER BY EVENT_SCHEMA, EVENT_NAME;
~~~

In versions prior to MySQL 8.2.0, this status name was SLAVESIDE_DISABLED; starting in MySQL 8.2.0 it is REPLICA_SIDE_DISABLED.

In an HA architecture:

- Designate which server is the writer/primary.
- Allow write-producing jobs to run only on the designated node.
- Do not blindly enable events across all replicas.
- During failover, clearly coordinate the handoff of job execution rights.
- Use unique run keys and idempotency to protect against reruns during failover.
- Monitor event DEFINER and privileges on the new node.

The Event Scheduler does not automatically elect a leader across independent MySQL servers. If multiple primaries could run the same job, implement system-level coordination or cross-node deduplication in data design.

## 18. Steps to Investigate an Event Producing No Results

When a dashboard shows no new data, proceed in order:

1. Verify event_scheduler is ON.
2. Check for the scheduler thread in SHOW PROCESSLIST.
3. Verify the event exists in INFORMATION_SCHEMA.EVENTS.
4. Check STATUS, STARTS, ENDS, TIME_ZONE, and next schedule.
5. Check LAST_EXECUTED without treating it as success.
6. Check DEFINER and SHOW GRANTS.
7. Check the routine called by the event, its SQL SECURITY, and EXECUTE privilege.
8. Read the error log file or performance_schema.error_log.
9. Invoke the procedure directly in a test session with exact parameters.
10. Inspect job_run by run key.
11. Cross-check summary, checkpoint, outbox, and source data.
12. Check for overlapping runs, lock waits, deadlocks, or run-time overruns.
13. Verify time zone and business date.
14. Fix the root cause and retry according to policy.

If calling the procedure directly succeeds while the event fails, prioritize checking DEFINER, grants, the SQL mode stored at CREATE/ALTER EVENT time, time_zone, and the event's session context.

## 19. Lab: Tracking Failed Events and Retrying Summaries

This lab creates an event that reruns a daily summary. The goal is to observe metadata, errors, job states, and idempotency mechanisms.

### Step 1: Create Database and Source Tables

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_event_retry_lab;
USE mysql_event_retry_lab;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME(6) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE order_items (
    order_item_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    order_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity DECIMAL(12,3) NOT NULL,
    unit_price DECIMAL(12,2) NOT NULL,
    KEY idx_items_order (order_id)
) ENGINE=InnoDB;

CREATE TABLE daily_sales_summary (
    sales_date DATE NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    order_count BIGINT UNSIGNED NOT NULL,
    revenue DECIMAL(18,2) NOT NULL,
    refreshed_at DATETIME(6) NOT NULL,
    PRIMARY KEY (sales_date, product_id)
) ENGINE=InnoDB;

CREATE TABLE scheduled_job_run (
    job_name VARCHAR(64) NOT NULL,
    run_date DATE NOT NULL,
    status ENUM(
        'PENDING',
        'RUNNING',
        'SUCCEEDED',
        'FAILED',
        'DEAD'
    ) NOT NULL,
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    max_attempts INT UNSIGNED NOT NULL DEFAULT 5,
    next_retry_at DATETIME(6) NULL,
    started_at DATETIME(6) NULL,
    finished_at DATETIME(6) NULL,
    last_sqlstate CHAR(5) NULL,
    last_error_code INT NULL,
    last_error_message VARCHAR(1000) NULL,
    PRIMARY KEY (job_name, run_date),
    KEY idx_job_retry (status, next_retry_at)
) ENGINE=InnoDB;
~~~

### Step 2: Load Source Data

~~~sql
INSERT INTO orders (order_id, status, created_at)
VALUES
    (1, 'PAID', CURRENT_TIMESTAMP(6) - INTERVAL 1 DAY),
    (2, 'PAID', CURRENT_TIMESTAMP(6) - INTERVAL 1 DAY),
    (3, 'PENDING', CURRENT_TIMESTAMP(6) - INTERVAL 1 DAY);

INSERT INTO order_items (
    order_item_id,
    order_id,
    product_id,
    quantity,
    unit_price
)
VALUES
    (101, 1, 10, 2.000, 100.00),
    (102, 1, 20, 1.000, 250.00),
    (103, 2, 10, 3.000, 100.00),
    (104, 3, 20, 2.000, 250.00);
~~~

### Step 3: Create the Retry Procedure

Use the sp_refresh_daily_sales procedure from section 11. When creating in the lab, adjust schema/table names if you are not using the mysql_event_retry_lab database.

### Step 4: Invoke the Procedure Manually First

~~~sql
CALL sp_refresh_daily_sales(CURRENT_DATE - INTERVAL 1 DAY);
~~~

Check:

~~~sql
SELECT *
FROM scheduled_job_run
WHERE job_name = 'daily_sales';

SELECT *
FROM daily_sales_summary
ORDER BY sales_date, product_id;
~~~

Expected status is SUCCEEDED. Summary contains products 10 and 20; the PENDING order is excluded.

### Step 5: Re-Invoke the Same Run Key

~~~sql
CALL sp_refresh_daily_sales(CURRENT_DATE - INTERVAL 1 DAY);
~~~

Check attempt_count and summary. Because status is already SUCCEEDED, the procedure skips and does not recompute.

### Step 6: Simulate a Retryable Error

In the lab environment, temporarily make the summary INSERT fail—for example, by altering a target column name in the procedure and recreating the routine. Never do this in production.

Re-invoke the procedure:

~~~sql
CALL sp_refresh_daily_sales(CURRENT_DATE - INTERVAL 1 DAY);
~~~

Observe:

- Statement fails.
- Summary transaction rolls back.
- Handler records FAILED or DEAD status.
- SQLSTATE, error code, and error message are saved.
- The Event Scheduler logs an error message when the procedure is invoked from an event and RESIGNALs the error outward.

After verifying the error in the error log, restore the procedure definition.

### Step 7: Inspect Retry Time

~~~sql
SELECT
    job_name,
    run_date,
    status,
    attempt_count,
    max_attempts,
    next_retry_at,
    last_sqlstate,
    last_error_code,
    last_error_message
FROM scheduled_job_run
WHERE job_name = 'daily_sales';
~~~

If status is FAILED and next_retry_at has not arrived yet, the procedure skips the current invocation. Once retry time is reached, the procedure retries.

### Step 8: Create the Event

~~~sql
SET time_zone = 'Asia/Ho_Chi_Minh';

CREATE EVENT ev_retry_daily_sales_lab
ON SCHEDULE EVERY 1 MINUTE
STARTS CURRENT_TIMESTAMP + INTERVAL 1 MINUTE
COMMENT 'Lab: retry daily sales'
DO
    CALL sp_refresh_daily_sales(CURRENT_DATE - INTERVAL 1 DAY);
~~~

If the Event Scheduler is OFF, enable it in the lab environment with a privileged account:

~~~sql
SET GLOBAL event_scheduler = ON;
~~~

### Step 9: Monitor the Event and Error Log

~~~sql
SELECT
    EVENT_NAME,
    STATUS,
    DEFINER,
    TIME_ZONE,
    LAST_EXECUTED
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA = 'mysql_event_retry_lab';
~~~

~~~sql
SELECT
    LOGGED,
    PRIO,
    ERROR_CODE,
    SUBSYSTEM,
    DATA
FROM performance_schema.error_log
WHERE DATA LIKE '%ev_retry_daily_sales_lab%'
   OR DATA LIKE '%Event Scheduler%'
ORDER BY LOGGED DESC
LIMIT 50;
~~~

If error_log has no data, read the server error log per environment configuration.

### Step 10: Test Idempotency

Run the procedure multiple times for the same date. Confirm:

- Only one job_run row exists for job_name + run_date.
- Once SUCCEEDED, later calls do not increment attempt_count.
- Summary does not double-count.
- Summary data stays unchanged when source data is unchanged.

### Step 11: Disable Event and Clean Up Lab

~~~sql
ALTER EVENT ev_retry_daily_sales_lab DISABLE;

DROP EVENT ev_retry_daily_sales_lab;

DROP DATABASE mysql_event_retry_lab;
~~~

Only run DROP DATABASE on the newly created lab database. Do not disable the Event Scheduler server-wide if other events depend on it.

## 20. Common Errors and Remediation

| Symptom | Cause | Remediation |
|---|---|---|
| Event ENABLED yet does not run | event_scheduler OFF/DISABLED or schedule not yet due | Check global variable, thread, STARTS/ENDS |
| Event has LAST_EXECUTED yet no output data | Action failed after starting | Read error log and inspect job_run |
| LAST_EXECUTED is NULL | Event has no recorded run; schedule not due or failed before action | Check DEFINER, privileges, scheduler, and error log |
| STATUS stays ENABLED after failed run | STATUS only reflects enabled/disabled state | Track business status separately |
| CREATE EVENT succeeded yet INSERT fails | DEFINER lacks INSERT privilege | Check SHOW GRANTS and security context |
| Error log shows nothing in Performance Schema | Log sink unsupported or not writing to error_log | Check log_error_services and read log file |
| Error log flooded with warnings | SELECT INTO raising No data or multiple rows | Use proper condition handlers and LIMIT 1 when appropriate |
| Event runs twice concurrently | Execution time exceeds interval | Use GET_LOCK or row lock per run key |
| Retry creates duplicate data | Job is not idempotent | Use unique keys, absolute-value upserts, or ledger dedup |
| Job stuck in FAILED indefinitely | Unfixed logic/privilege/schema error | Classify error, fix root cause, retry with limit |
| Job stuck in RUNNING after worker died | RUNNING status committed earlier | Use leases/heartbeats and stale job reclamation |
| Event runs on replica | Event enabled on wrong node | Check REPLICA_SIDE_DISABLED and writer role |
| Report covers wrong date | Inconsistent TIME_ZONE or business date | Standardize business time zone and verify TIME_ZONE |
| Duplicate emails/API calls | Retries cannot roll back external side effects | Use outbox, message key, and consumer deduplication |
| Retries cause load spikes | Many jobs retrying simultaneously | Exponential backoff, jitter, and concurrency limits |
| Event runs yet produces no visible output | SELECT/SHOW returns result set that gets discarded | Use SELECT ... INTO, INSERT ... SELECT, or state table |

## 21. Event and Retry Operations Checklist

- [ ] event_scheduler is ON and the scheduler thread exists.
- [ ] Event has the intended STATUS.
- [ ] STARTS, ENDS, TIME_ZONE, and interval are verified.
- [ ] LAST_EXECUTED is understood as start time, not success confirmation.
- [ ] Error logs are collected and retained long enough.
- [ ] performance_schema.error_log has a supporting sink or an alternative log path exists.
- [ ] DEFINER exists and holds minimum required privileges.
- [ ] Routine called by the event has EXECUTE privilege and proper security context.
- [ ] Event cannot run concurrently for the same run key when disallowed by business rules.
- [ ] Each logical run has a unique key.
- [ ] Jobs can be retried without double-counting or duplicate sending.
- [ ] Business data and SUCCEEDED status commit in the same transaction.
- [ ] Handler rolls back failed work before recording FAILED status.
- [ ] Errors store SQLSTATE, error code, and message.
- [ ] Retries track next_retry_at, backoff, and max_attempts.
- [ ] Jobs exceeding thresholds transition to DEAD and trigger alerts.
- [ ] Long jobs have checkpoints, leases, or idempotent batches.
- [ ] External side effects use an outbox and idempotency keys.
- [ ] Manual retry workflow and operator auditing exist.
- [ ] Failover plan ensures only one node is authorized to run write-producing jobs.

## 22. Key Principles to Remember

1. The Event Scheduler triggers SQL on a schedule; it does not replace a durable job queue.
2. Event executions ending with errors or warnings are written to the server error log.
3. INFORMATION_SCHEMA.EVENTS describes the event, not business execution history.
4. STATUS ENABLED does not prove the latest run succeeded.
5. LAST_EXECUTED indicates when the event started, not when it finished.
6. performance_schema.error_log only has rows if the log sink supports it; it is a ring buffer, not long-term log storage.
7. Events run with DEFINER and the associated security context's privileges; CREATE EVENT succeeding does not guarantee the action has sufficient privileges.
8. Events execute in their own connections; do not rely on temporary tables or session variables from application connections.
9. Events can overlap if execution duration exceeds the schedule interval.
10. GET_LOCK is a session/server-scoped named lock, not a distributed lock across multiple servers.
11. Every logical job needs a unique run key and idempotency.
12. Retries should be at-least-once paired with deduplication; never assume exactly-once by default.
13. Business data and SUCCEEDED status should commit in the same transaction.
14. On error, roll back the work first, then record FAILED in a new transaction.
15. Classify errors before retrying; use backoff, max attempts, and a DEAD state.
16. Use an outbox for side effects outside the database.
17. Monitor time zones, replication, failover, and DEFINER privileges as part of operations.

## Official References

Behavior in this lesson is aligned with the **MySQL 9.7 Reference Manual**:

1. [Event Scheduler Overview](https://dev.mysql.com/doc/refman/9.7/en/events-overview.html): event lifecycle, DEFINER privileges, and potential overlapping instances.
2. [Event Scheduler Configuration](https://dev.mysql.com/doc/refman/9.7/en/events-configuration.html): event_scheduler ON/OFF/DISABLED, scheduler thread, and startup settings.
3. [Event Scheduler Status](https://dev.mysql.com/doc/refman/9.7/en/events-status-info.html): errors and warnings during event execution logged to the server error log.
4. [The Event Scheduler and MySQL Privileges](https://dev.mysql.com/doc/refman/9.7/en/events-privileges.html): EVENT privilege, DEFINER privileges, and privilege errors in actions.
5. [Event Metadata](https://dev.mysql.com/doc/refman/9.7/en/events-metadata.html): SHOW EVENTS, SHOW CREATE EVENT, and event time zones.
6. [INFORMATION_SCHEMA EVENTS Table](https://dev.mysql.com/doc/refman/9.7/en/information-schema-events-table.html): STATUS, DEFINER, TIME_ZONE, and LAST_EXECUTED.
7. [CREATE EVENT Statement](https://dev.mysql.com/doc/refman/9.7/en/create-event.html): schedule syntax, EVERY, STARTS, ENDS, and event actions.
8. [The Performance Schema error_log Table](https://dev.mysql.com/doc/refman/9.7/en/performance-schema-error-log-table.html): querying the error log via SQL, log sinks, and the ring buffer.
9. [Error Log Configuration](https://dev.mysql.com/doc/refman/9.7/en/error-log-configuration.html): log_error_services and log sinks.
10. [MySQL Privileges](https://dev.mysql.com/doc/refman/9.7/en/privileges-provided.html): EVENT, EXECUTE, and stored object management privileges.
