# Event Scheduler, One-Time or Recurring Schedules, and Time Zones

## Objectives

After this lesson, you will be able to:

- Explain the Event Scheduler and how MySQL executes events without requiring an application to keep a connection open waiting on a schedule.
- Inspect and enable/disable `event_scheduler`.
- Create one-time events with `AT` and recurring events with `EVERY`.
- Choose appropriate `STARTS`, `ENDS`, `ON COMPLETION PRESERVE`, and `ENABLE`/`DISABLE` states.
- Distinguish server, session, and event time zones.
- Choose UTC or named time zones for schedules running on real elapsed time versus local wall-clock time.
- Understand the impact of daylight saving time (DST) and loading time zone tables.
- Inspect event definitions, schedules, last execution times, and status.
- Manage `DEFINER`, privileges, and replication to avoid events running on the wrong node.
- Design jobs that can rerun safely, log outcomes, prevent overlapping runs, and recover after scheduler pauses.

Examples target MySQL 8.0/8.4. The Event Scheduler is an in-server task-execution mechanism inside MySQL Server; it does not replace external orchestration systems when complex retries, distributed monitoring, or multi-service coordination are needed.

## 1. What Is the Event Scheduler?

An event is a schema object storing a schedule to execute one or more SQL statements. When the Event Scheduler is enabled, MySQL monitors enabled events and executes their bodies when the scheduled time arrives.

For example, suppose a system needs to summarize paid orders every night. You can create an event calling a stored procedure:

```sql
CREATE EVENT ev_refresh_daily_sales
ON SCHEDULE EVERY 1 DAY
STARTS CURRENT_TIMESTAMP + INTERVAL 1 DAY
DO
    CALL sp_refresh_daily_sales();
```

The event is stored in the schema and managed by the server. The application does not need to hold a thread or connection waiting until the scheduled time to send the command.

### 1.1. Components of an Event

An event has these main components:

- **Name and schema:** identifies the event in the database.
- **Schedule:** one-time (`AT`) or recurring (`EVERY`).
- **Completion policy:** whether to keep or automatically drop the event after the schedule finishes.
- **Status:** enabled or disabled.
- **Definer:** the account whose privileges are used when the event executes.
- **Body:** the SQL statement or compound statement executed on schedule.
- **Time zone:** the time zone associated with the event when created or altered.

### 1.2. How Events Differ from Cron Jobs

| Criterion | MySQL Event Scheduler | External Cron / Job Scheduler |
|---|---|---|
| Where schedule is stored | Inside a MySQL schema | In the OS or orchestration platform |
| Execution | SQL inside MySQL Server | Can invoke scripts, APIs, multiple services |
| Dependency | Running server and enabled scheduler | Active agent/daemon or scheduler platform |
| Observability | `INFORMATION_SCHEMA.EVENTS`, application-designed logs | Logs and dashboards of the external system |
| Distributed coordination | Limited; must be designed manually | Usually provides retries, leases, queues, HA |
| Best suited for | Compact SQL jobs close to data on simple schedules | Multi-step workflows, service integrations, complex retries |

Choose the Event Scheduler when the work is primarily SQL and its operational lifecycle can be managed inside MySQL. Choose an external scheduler when you need multi-system workflows, controlled retries, alerting, or multi-worker coordination.

## 2. Checking Event Scheduler Status

### 2.1. Inspecting the System Variable

```sql
SHOW GLOBAL VARIABLES LIKE 'event_scheduler';
```

Or:

```sql
SELECT @@GLOBAL.event_scheduler;
```

Possible values are:

| Value | Meaning |
|---|---|
| `ON` | The Event Scheduler is active and can execute enabled events |
| `OFF` | The scheduler does not execute events; events remain stored in the schema |
| `DISABLED` | The scheduler was disabled at server startup and cannot be enabled with `SET GLOBAL` at runtime |

If the value is `OFF`, events do not run automatically until the scheduler is turned back on. If it is `DISABLED`, you must update the server startup configuration and restart following operational procedures.

### 2.2. Enabling the Scheduler at Runtime

When the server allows changing this variable:

```sql
SET GLOBAL event_scheduler = ON;
```

This command requires appropriate global system variable administration privileges. Never grant global administrative privileges to an application account solely to create an event.

### 2.3. Configuring at Server Startup

Can be configured in the MySQL configuration file:

```ini
[mysqld]
event_scheduler=ON
```

If configured as:

```ini
[mysqld]
event_scheduler=DISABLED
```

then the scheduler is locked in the disabled state for that server run. `OFF` and `DISABLED` are not equivalent: `OFF` can be turned back on at runtime if the server permits; `DISABLED` cannot be turned on via SQL while the server is running.

### 2.4. Scheduler OFF Does Not Drop Events

Turning off the scheduler only stops dispatching events. Event definitions, schedules, and enable/disable statuses remain in metadata. Re-enabling the scheduler is not a reliable catch-up retry mechanism for all missed runs.

Do not assume every occurrence missed while the scheduler was off will be replayed completely. Design jobs to reconcile over a range—for instance, processing all unsummarized dates—rather than processing only "today". After re-enabling the scheduler, inspect `LAST_EXECUTED`, job status, and actual data.

## 3. One-Time Schedule Syntax with AT

One-time events use `ON SCHEDULE AT`:

```sql
CREATE EVENT ev_close_expired_campaign
ON SCHEDULE AT CURRENT_TIMESTAMP + INTERVAL 2 HOUR
DO
    CALL sp_close_expired_campaigns();
```

The time expression is evaluated when creating or altering the event to determine the execution timestamp. The event is not a statement recomputing `CURRENT_TIMESTAMP + INTERVAL 2 HOUR` every second.

### 3.1. Running at a Fixed Timestamp

```sql
CREATE EVENT ev_archive_2026_12_01
ON SCHEDULE AT '2026-12-01 01:30:00'
DO
    CALL sp_archive_orders_for_date('2026-11-30');
```

The literal timestamp is interpreted in the session's time zone when the event is created. Therefore, explicitly set session `time_zone` before creating the schedule and record that time zone in the deployment procedure.

### 3.2. ON COMPLETION NOT PRESERVE and PRESERVE

After a one-time event finishes, it can be automatically dropped or kept:

```sql
CREATE EVENT ev_send_month_end_report
ON SCHEDULE AT '2026-12-01 08:00:00'
ON COMPLETION PRESERVE
DO
    CALL sp_send_month_end_report();
```

- `ON COMPLETION NOT PRESERVE`: one-time events are automatically dropped upon completion; this is the default.
- `ON COMPLETION PRESERVE`: keeps the event definition after the schedule completes. An event does not repeat merely because it is preserved.

If auditing is needed, preserving event definitions can be useful, though you should have a cleanup workflow for completed events. If retaining definitions after execution is unnecessary, the default `NOT PRESERVE` is usually appropriate.

### 3.3. One-Time Schedules in the Past

Do not create an event with a timestamp in the past assuming it will immediately run as desired. Check the schedule, scheduler state, and exact version behavior. For backfill tasks, build a parameterized reconciliation workflow rather than relying on an overdue event.

## 4. Recurring Schedules with EVERY

Recurring events use `EVERY` with an interval:

```sql
CREATE EVENT ev_refresh_hourly_metrics
ON SCHEDULE EVERY 1 HOUR
DO
    CALL sp_refresh_hourly_metrics();
```

Common units include `SECOND`, `MINUTE`, `HOUR`, `DAY`, `WEEK`, `MONTH`, `QUARTER`, `YEAR`, and compound intervals supported by MySQL.

### 4.1. EVERY with STARTS

`STARTS` specifies when the recurring schedule begins:

```sql
CREATE EVENT ev_daily_cleanup
ON SCHEDULE EVERY 1 DAY
STARTS '2026-12-01 02:00:00'
DO
    CALL sp_cleanup_expired_sessions();
```

If `STARTS` is omitted, the schedule starts according to MySQL's default rule from creation time. For production jobs, specify an explicit start time so the schedule is predictable and reproducible across deployments.

### 4.2. EVERY with ENDS

`ENDS` specifies when the recurring schedule stops:

```sql
CREATE EVENT ev_campaign_reminder
ON SCHEDULE EVERY 1 DAY
STARTS '2026-12-01 09:00:00'
ENDS '2026-12-31 09:00:00'
ON COMPLETION PRESERVE
DO
    CALL sp_send_campaign_reminder();
```

After the end timestamp, the event stops being scheduled. `ON COMPLETION PRESERVE` retains the definition after the schedule ends; without preserve, the event may be automatically dropped upon schedule completion.

### 4.3. Weekly or Monthly Schedules

Example running every Monday based on a start timestamp:

```sql
CREATE EVENT ev_weekly_inventory_report
ON SCHEDULE EVERY 1 WEEK
STARTS '2026-12-07 07:00:00'
DO
    CALL sp_build_inventory_report();
```

Example running monthly:

```sql
CREATE EVENT ev_monthly_billing_close
ON SCHEDULE EVERY 1 MONTH
STARTS '2027-01-01 01:00:00'
DO
    CALL sp_close_previous_billing_period();
```

For monthly schedules, check month-end rules and the actual start anchor. Do not assume every month has the same number of days or that a schedule will always land on the 31st.

### 4.4. Changing a Schedule After Creation

Use `ALTER EVENT` to change schedule, status, or attributes:

```sql
ALTER EVENT ev_refresh_hourly_metrics
ON SCHEDULE EVERY 2 HOUR
STARTS CURRENT_TIMESTAMP + INTERVAL 2 HOUR
ENABLE;
```

Inspect `SHOW CREATE EVENT` and metadata after altering to confirm the new schedule. `ALTER EVENT` is not a way to run an event immediately; if a manual run is needed, invoke the underlying procedure directly through a defined workflow.

## 5. ENABLE, DISABLE, and Event Status

The scheduler can be ON while a specific event is disabled. These two states are independent.

### 5.1. Creating an Event Without Running It Yet

```sql
CREATE EVENT ev_rebuild_search_summary
ON SCHEDULE EVERY 1 DAY
STARTS CURRENT_TIMESTAMP + INTERVAL 1 DAY
DISABLE
DO
    CALL sp_rebuild_search_summary();
```

`DISABLE` is helpful when deploying ahead of time, verifying privileges and metadata, and then enabling after approval.

### 5.2. Enabling and Disabling Events

```sql
ALTER EVENT ev_rebuild_search_summary ENABLE;

ALTER EVENT ev_rebuild_search_summary DISABLE;
```

Disabling an event does not drop its definition and does not necessarily terminate an execution already in progress. When you need to stop a running job, inspect the corresponding session/thread and follow a safe termination procedure.

### 5.3. DISABLE ON SLAVE

In a replication topology, events created on the source can replicate to replicas. If only the primary is allowed to execute jobs, you can use:

```sql
CREATE EVENT ev_primary_daily_rollup
ON SCHEDULE EVERY 1 DAY
STARTS CURRENT_TIMESTAMP + INTERVAL 1 DAY
DISABLE ON SLAVE
DO
    CALL sp_refresh_daily_rollup();
```

`DISABLE ON SLAVE` sets the event status so the replica's event scheduler does not execute it. Verify actual status on every node after DDL replication and after failover. Never rely on hostname checks or assume only one server has the scheduler ON.

## 6. Server, Session, and Event Time Zones

MySQL has multiple time zone layers. Confusing them can make events run off-schedule or record unexpected timestamps.

### 6.1. Server Time Zone

Inspect:

```sql
SELECT
    @@GLOBAL.time_zone AS global_time_zone,
    @@SYSTEM_TIME_ZONE AS system_time_zone;
```

- `@@GLOBAL.time_zone` is the default time zone for new sessions.
- `@@SYSTEM_TIME_ZONE` reflects the operating system time zone detected when the server started.

If `time_zone = 'SYSTEM'`, sessions use the system time zone. This can depend on OS/container configuration and make schedules unpredictable across environment moves.

### 6.2. Session Time Zone

Inspect current session:

```sql
SELECT @@SESSION.time_zone;
```

Set session time zone:

```sql
SET time_zone = '+00:00';
```

Or use a named time zone if time zone tables are loaded:

```sql
SET time_zone = 'Asia/Ho_Chi_Minh';
```

The session's `time_zone` at the moment an event is created is stored as the event's time zone. Therefore, never create an event in a session with an unknown time zone or one dependent on client defaults.

### 6.3. Event Time Zone

An event stores its own time zone, visible in `INFORMATION_SCHEMA.EVENTS.TIME_ZONE` and `SHOW CREATE EVENT`.

When an event executes, MySQL sets the execution session to the event's stored time zone. Session time functions like `CURRENT_TIMESTAMP`, `CURRENT_DATE`, and `NOW()` are therefore evaluated in the event's time zone. If an absolute UTC timestamp is needed, use `UTC_TIMESTAMP()` or convert explicitly.

### 6.4. Setting the Time Zone Explicitly Before CREATE EVENT

Example creating a schedule in UTC:

```sql
SET time_zone = '+00:00';

CREATE EVENT ev_utc_hourly_rollup
ON SCHEDULE EVERY 1 HOUR
STARTS '2026-12-01 00:00:00'
DO
    CALL sp_refresh_hourly_rollup();
```

Example creating a schedule in Vietnam time:

```sql
SET time_zone = 'Asia/Ho_Chi_Minh';

CREATE EVENT ev_vietnam_morning_report
ON SCHEDULE EVERY 1 DAY
STARTS '2026-12-01 07:00:00'
DO
    CALL sp_send_morning_report();
```

In the second example, `07:00:00` is local wall-clock time in the time zone saved for the event. Ensure the named time zone exists in MySQL's time zone tables.

### 6.5. Do Not Rely on Connection Pool Default Time Zones

Connection pools may reuse a session whose `time_zone` was altered by a previous request. When deploying events, set session timezone directly inside the migration script and verify it right before `CREATE EVENT` or `ALTER EVENT`.

Document the chosen time zone in migration reviews so operators know whether a schedule is evaluated in UTC, server time, or local time.

## 7. UTC or Named Time Zone?

Choose the time zone based on the business meaning of the schedule.

| Requirement | Suitable Choice | Reason |
|---|---|---|
| Run every 60 elapsed minutes | UTC or fixed offset | Avoids dependence on local clock changes |
| Run daily at 02:00 local wall-clock time | Named time zone | Schedule follows the local clock |
| Synchronized across multiple regions | UTC | One shared time reference |
| Reporting by business day in Vietnam | `Asia/Ho_Chi_Minh` | Day boundaries follow local business calendar |
| Recording event timestamps across systems | UTC | Easy log correlation and replication |
| Statutory schedule in a country with DST | Tested named time zone | Preserves local wall-clock meaning across DST changes |

No single time zone choice fits every event. Jobs scheduled by elapsed intervals and jobs scheduled by local business hours have different semantics.

## 8. Daylight Saving Time and Time Zone Tables

### 8.1. Fixed Offsets Differ from Named Time Zones

An offset like `'+07:00'` always represents a fixed offset from UTC. A named time zone like `'America/New_York'` contains historical and DST transition rules loaded into MySQL.

In regions with DST, a fixed offset does not shift when local rules switch between standard time and daylight saving time. If a schedule must stay at the same local wall-clock hour, use a named time zone.

### 8.2. Loading Time Zone Tables

Check available named zones:

```sql
SELECT Name
FROM mysql.time_zone_name
WHERE Name IN (
    'UTC',
    'Asia/Ho_Chi_Minh',
    'America/New_York'
);
```

If there are no rows, the time zone tables may not be loaded or may be outdated. A DBA must load time zone data following OS and MySQL guidelines, typically using `mysql_tzinfo_to_sql` on Unix-like systems, then restart/flush as appropriate.

Never edit `mysql.time_zone*` tables directly with ordinary DML. Update from trusted time zone datasets and test after loading.

### 8.3. DST Can Create Skipped or Repeated Hours

In DST regions, when clocks spring forward, certain local times do not exist; when clocks fall back, a local hour can occur twice. Schedules running on local time must be tested across DST transition dates.

If a job must run strictly once per UTC interval or process data by absolute timestamps, using UTC is usually easier to control. If business rules require local wall-clock execution, keep the named zone and design an idempotency key per business period to prevent duplicate runs or gaps.

### 8.4. Testing DST Transitions

For schedules in DST regions, verify:

- Corresponding UTC timestamps before and after the DST switch.
- Whether the event fires during a repeated local hour.
- What policy applies when a local hour is skipped.
- Whether jobs can backfill by `business_date` or `period_key`.
- Whether source and replica nodes have identical time zone data.

Never test a single run in a normal month and assume a DST schedule is safe.

## 9. TIMESTAMP, DATETIME, and Time Functions in Events

### 9.1. TIMESTAMP

MySQL converts `TIMESTAMP` values from session time zone to UTC on storage and back from UTC to session time zone on retrieval. Consequently, the same stored instant can display differently under different session time zones.

### 9.2. DATETIME

`DATETIME` stores date and time components as supplied without automatic session time zone conversion. Applications must define clearly whether values represent UTC or local time.

### 9.3. Comparison

| Type | Automatic time zone conversion | Common usage |
|---|---|---|
| `TIMESTAMP` | Yes, between session time zone and UTC | Instants that should render in session time zone |
| `DATETIME` | No | Business calendar times or values standardized by explicit convention |

Event example:

```sql
INSERT INTO event_run_log (
    event_name,
    started_at_utc,
    started_at_session
)
VALUES (
    'ev_vietnam_morning_report',
    UTC_TIMESTAMP(6),
    CURRENT_TIMESTAMP(6)
);
```

If `started_at_session` uses `DATETIME`, the stored value is in the event's session time zone. The `started_at_utc` column records the UTC instant. Name columns and document clearly to avoid comparing values with different time zone semantics.

### 9.4. Computing Time Ranges

When measuring elapsed time, prefer comparing UTC instants or normalized timestamps. When computing a "business day" in Vietnam time, convert timestamps to `Asia/Ho_Chi_Minh` before extracting the date, or maintain a dedicated, clearly defined `business_date` column.

## 10. Event Bodies and Stored Procedures

An event can contain a single statement or a compound statement. For longer business logic, extract it into a stored procedure so it is easy to test and invoke manually.

### 10.1. Event Calling a Procedure

```sql
CREATE EVENT ev_nightly_cleanup
ON SCHEDULE EVERY 1 DAY
STARTS '2026-12-01 02:30:00'
DO
    CALL sp_cleanup_expired_sessions();
```

The procedure can encapsulate transactions, handlers, logging, and idempotent logic under its own contract.

### 10.2. Compound Statement Inside an Event

```sql
DELIMITER $$

CREATE EVENT ev_mark_stale_jobs
ON SCHEDULE EVERY 10 MINUTE
DO
BEGIN
    UPDATE background_jobs
    SET status = 'STALE',
        updated_at = CURRENT_TIMESTAMP(6)
    WHERE status = 'RUNNING'
      AND heartbeat_at < CURRENT_TIMESTAMP - INTERVAL 30 MINUTE;

    INSERT INTO event_run_log (
        event_name,
        affected_rows,
        executed_at
    )
    VALUES (
        'ev_mark_stale_jobs',
        ROW_COUNT(),
        CURRENT_TIMESTAMP(6)
    );
END$$

DELIMITER ;
```

`DELIMITER` is a MySQL client directive to separate statements; it is not an SQL statement sent to the server. In applications or migration tools, send the entire `CREATE EVENT ... BEGIN ... END` statement using whatever multi-statement/routine delimiter mechanism the tool supports.

Note on the example above: `ROW_COUNT()` must be called immediately after the UPDATE if you want to record the number of rows modified by that UPDATE. If another statement intervenes, the value reflects that statement instead. In practice, assign it right away to a local variable and then INSERT the log.

### 10.3. Event Bodies Do Not Return Result Sets to Clients

Events run in background threads with no client waiting for a result set. Do not design event bodies around returning `SELECT` output to a user. If results must be stored, INSERT into a log/summary table or call a procedure that writes status.

## 11. DEFINER and Execution Privileges

An event executes in the security context of its `DEFINER`. This is the account attached to the event when created or altered.

### 11.1. Creating an Event with an Explicit Definer

```sql
CREATE DEFINER = 'job_runner'@'localhost'
EVENT ev_refresh_customer_summary
ON SCHEDULE EVERY 1 DAY
STARTS '2026-12-01 03:00:00'
DO
    CALL app_db.sp_refresh_customer_summary();
```

The definer account must exist and have the privileges needed to execute the body, including `EXECUTE` on called procedures and data privileges required by the procedure according to its security context.

Never use `root` as the definer for application jobs. Create a dedicated account with least privilege, manage its lifecycle, and verify definers during restores or failovers to other servers.

### 11.2. Event Management Privileges

Relevant privileges typically include:

- `EVENT` on the schema to create, alter, or drop events.
- Appropriate system variable privileges to enable/disable `event_scheduler`.
- `EXECUTE` on stored procedures called by the event.
- `SELECT`/`INSERT`/`UPDATE`/`DELETE` on tables touched by the routine, depending on the routine's `SQL SECURITY`.
- Appropriate metadata visibility to inspect events.

Example granting EVENT on a schema:

```sql
GRANT EVENT ON app_db.* TO 'job_deployer'@'localhost';
```

This privilege allows managing events in the schema; it does not automatically grant the definer privileges to run SQL statements inside the event body.

### 11.3. Checking Definers After Restore/Migration

```sql
SELECT
    EVENT_SCHEMA,
    EVENT_NAME,
    DEFINER,
    STATUS,
    TIME_ZONE
FROM information_schema.EVENTS
WHERE EVENT_SCHEMA = 'app_db'
ORDER BY EVENT_NAME;
```

If a definer is missing or lacks privileges, the event may fail to execute. Check the server error log and the privileges of the account recorded in metadata.

## 12. Managing Events: SHOW, ALTER, and DROP

### 12.1. Listing Events

```sql
SHOW EVENTS FROM app_db;
```

Or:

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
    ON_COMPLETION,
    LAST_EXECUTED
FROM information_schema.EVENTS
WHERE EVENT_SCHEMA = 'app_db'
ORDER BY EVENT_NAME;
```

### 12.2. Viewing an Event Definition

```sql
SHOW CREATE EVENT app_db.ev_refresh_customer_summary;
```

Compare schedule, time zone, definer, status, completion policy, and body against migration source control.

### 12.3. Pausing an Event

```sql
ALTER EVENT app_db.ev_refresh_customer_summary DISABLE;
```

After resolving the incident:

```sql
ALTER EVENT app_db.ev_refresh_customer_summary ENABLE;
```

Before re-enabling, confirm the job is not already running from another scheduler and data has not already been processed twice.

### 12.4. Dropping an Event

```sql
DROP EVENT IF EXISTS app_db.ev_old_monthly_report;
```

`DROP EVENT` removes the event definition. It does not roll back data previously written by the event.

## 13. Monitoring Schedules and Executions

### 13.1. LAST_EXECUTED

`INFORMATION_SCHEMA.EVENTS.LAST_EXECUTED` shows when the event was last executed according to server metadata. It is a helpful indicator, yet does not replace business logs recording success or failure.

### 13.2. Creating a Dedicated Run Log Table

```sql
CREATE TABLE event_run_log (
    run_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_name VARCHAR(128) NOT NULL,
    started_at_utc DATETIME(6) NOT NULL,
    finished_at_utc DATETIME(6) NULL,
    status VARCHAR(20) NOT NULL,
    affected_rows BIGINT NULL,
    error_message TEXT NULL,
    PRIMARY KEY (run_id),
    KEY idx_event_run_name_started (event_name, started_at_utc)
) ENGINE = InnoDB;
```

The event or called procedure can insert a start row and update it on completion. If error logs must survive rollback, design a separate logging target and transaction boundary; logs inside the same transaction as business data roll back with that transaction.

### 13.3. Distinguishing Dispatched vs. Succeeded

An event can be dispatched yet fail inside its body. `LAST_EXECUTED` is not a business status. Record explicitly:

- `STARTED` upon starting.
- `SUCCEEDED` after work completes.
- `FAILED` when a handler catches an error.
- UTC start/finish timestamps.
- Processed data period or `business_date`.
- Rows read/written and error code if any.

### 13.4. Inspecting Threads and Server Status

You can inspect the process list for the event scheduler or event worker threads:

```sql
SHOW PROCESSLIST;
```

Thread names vary by version and state. When investigating, combine process list output, the server error log, `INFORMATION_SCHEMA.EVENTS`, and the application's run log table.

## 14. Preventing Overlap and Ensuring Idempotency

Never assume one event run will always finish before the next occurrence. If a procedure runs longer than the interval, runs can overlap depending on schedule and server state.

### 14.1. Designing Idempotency by Period

Instead of "add yesterday's revenue" every time the event runs, recompute or upsert by a unique key `(business_date, customer_id)`. That way, retrying the same period will not create duplicate records or double-count metrics.

### 14.2. Using a Job State Table

A state table can track:

- Job name.
- Period to process (`period_key`).
- Status (`READY`, `RUNNING`, `SUCCEEDED`, `FAILED`).
- Claim timestamp and lease expiration.
- Attempt count and error message.

Claiming a period must be atomic via transaction and unique key/row lock so two event runs or two nodes never accidentally process the same period simultaneously.

### 14.3. Advisory Locks When Locking by Job Name

MySQL provides `GET_LOCK()` and `RELEASE_LOCK()` for connection-scoped named locks. For example, a procedure can attempt a non-blocking lock:

```sql
SET v_lock_result = GET_LOCK('app_db:daily_sales', 0);

IF v_lock_result = 1 THEN
    -- Execute the job.
    DO RELEASE_LOCK('app_db:daily_sales');
ELSE
    -- Another session holds the lock or an error occurred while acquiring the lock.
    -- Record skipped/lock-not-acquired status per convention.
END IF;
```

The snippet above illustrates logic inside a procedure; declare variables, handlers, and cleanup in an `EXIT HANDLER` so the lock is always released on error. `GET_LOCK()` is tied to the connection, not the transaction; `COMMIT` or `ROLLBACK` does not automatically release a named lock. When the connection closes, the lock is released.

Named locks only coordinate sessions using the same lock name on the same MySQL server. They do not automatically create a distributed lock across independent servers. With replication/failover, enforce a single active node rule and fencing/leasing at the orchestration layer when strict guarantees are needed.

## 15. Event Scheduler in Replication and Failover

In a replication topology, event DDL can replicate with the schema. If an event runs on both source and replica, jobs can execute twice and write unwanted data.

Checklist for primary-only jobs:

1. Identify which node is allowed to run events.
2. Create events with `DISABLE ON SLAVE` if suitable for the topology.
3. Verify `STATUS` on source and replica after replication.
4. Check `event_scheduler` on each node.
5. Confirm definers and privileges exist on any node that will execute the job.
6. On failover, follow a procedure to enable events on the new primary and disable on the old node.
7. Use idempotency/unique period keys to limit impact if a duplicate run occurs.

`DISABLE ON SLAVE` does not replace failover procedures. Whenever source/replica roles change, re-verify event statuses and scheduler settings rather than assuming metadata automatically reflects application roles.

## 16. Complete Example: Daily Report in Vietnam Time

### 16.1. Stored Procedure Processing a Single Day

The procedure accepts an explicit business date so it can be run manually or backfilled:

```sql
DELIMITER $$

CREATE PROCEDURE sp_refresh_daily_sales(IN p_business_date DATE)
BEGIN
    IF p_business_date IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'business date is required';
    END IF;

    START TRANSACTION;

    DELETE FROM daily_customer_sales
    WHERE sales_date = p_business_date;

    INSERT INTO daily_customer_sales (
        sales_date,
        customer_id,
        order_count,
        total_amount
    )
    SELECT
        p_business_date,
        customer_id,
        COUNT(*),
        SUM(total_amount)
    FROM orders
    WHERE status = 'PAID'
      AND created_at >= CONVERT_TZ(
          CONCAT(p_business_date, ' 00:00:00'),
          'Asia/Ho_Chi_Minh', '+00:00'
      )
      AND created_at < CONVERT_TZ(
          CONCAT(p_business_date + INTERVAL 1 DAY, ' 00:00:00'),
          'Asia/Ho_Chi_Minh', '+00:00'
      )
    GROUP BY customer_id;

    COMMIT;
END$$

DELIMITER ;
```

This example assumes `orders.created_at` stores UTC instants by a consistent convention. If the column is `TIMESTAMP`, comparisons are also affected by session time zone; verify column type and semantics before applying. If time zone tables are not loaded, `CONVERT_TZ()` with a named zone can return `NULL`.

In production, the procedure needs an `SQLEXCEPTION` handler to roll back on error. The example is trimmed to highlight passing `business_date`; do not deploy verbatim without adding handlers and proper privileges.

### 16.2. Creating the Event in Vietnam Time Zone

Set the session time zone before creating the event:

```sql
SET time_zone = 'Asia/Ho_Chi_Minh';

CREATE DEFINER = 'job_runner'@'localhost'
EVENT ev_daily_sales_vietnam
ON SCHEDULE EVERY 1 DAY
STARTS '2026-12-01 02:15:00'
ON COMPLETION PRESERVE
ENABLE
DO
    CALL sp_refresh_daily_sales(CURRENT_DATE - INTERVAL 1 DAY);
```

The event runs at 02:15 in the stored time zone. `CURRENT_DATE` inside the event is evaluated in the event's time zone, so the argument is the previous local calendar date.

If source data stores UTC in `DATETIME`, the procedure must convert local day boundaries to UTC as shown. If source data uses `TIMESTAMP`, check the event's session time zone and compare with matching semantics; never double-convert.

### 16.3. Inspecting After Creation

```sql
SHOW CREATE EVENT ev_daily_sales_vietnam;

SELECT
    EVENT_NAME,
    TIME_ZONE,
    EVENT_TYPE,
    STARTS,
    ENDS,
    STATUS,
    ON_COMPLETION,
    LAST_EXECUTED,
    DEFINER
FROM information_schema.EVENTS
WHERE EVENT_SCHEMA = DATABASE()
  AND EVENT_NAME = 'ev_daily_sales_vietnam';
```

Compare `TIME_ZONE`, `STARTS`, `STATUS`, and `DEFINER` against operational requirements. Also inspect `@@GLOBAL.event_scheduler` and procedure logs.

### 16.4. Backfilling a Missed Day

There is no need to create a past event to backfill. Call the procedure directly with the target date:

```sql
CALL sp_refresh_daily_sales('2026-11-30');
```

Because the procedure takes `business_date`, the same day can be rerun idempotently. Before backfilling, verify transaction state, completeness of source data, and that no concurrent job is running for the same period.

## 17. Common Errors and Troubleshooting

| Symptom | Possible Cause | How to Handle |
|---|---|---|
| Event does not run | `event_scheduler=OFF` or `DISABLED` | Check global variable and startup configuration |
| Event is DISABLED | Individual event disabled even though scheduler is ON | `SHOW CREATE EVENT`, then `ALTER EVENT ... ENABLE` after verification |
| Event runs at wrong hour | Session time zone at creation differed from expected | Check `TIME_ZONE`, `STARTS`, and server/session time zone |
| Named zone unavailable | Time zone tables not loaded or outdated | Load/update time zone tables per DBA procedure |
| `CONVERT_TZ()` returns NULL | Named zone missing in time zone tables or invalid arguments | Check `mysql.time_zone_name` and inputs |
| Event fails to execute procedure | Definer lacks `EXECUTE` or routine privileges | Check `DEFINER`, `SHOW CREATE EVENT`, and routine privileges |
| Event runs on replica | Incorrect event/scheduler status on replica | Check `DISABLE ON SLAVE`, event status, and failover policy |
| Job runs twice | Event overlap, multiple active nodes, or non-idempotent retries | Unique period key, atomic claim, named lock, and fencing |
| Unsure if job succeeded | Relying only on `LAST_EXECUTED` | Write run log with business status and errors |
| Scheduler re-enabled but period missing | No catch-up mechanism per business period | Reconcile missing periods and invoke backfill procedure |
| One-time event vanished | `ON COMPLETION NOT PRESERVE` | Use `PRESERVE` if metadata must remain or keep migration source |
| Event disabled yet job still running | DISABLE does not kill active execution | Find session/thread and stop safely |

## 18. Production Event Deployment Checklist

- [ ] Determined whether the job belongs in MySQL or requires an external scheduler.
- [ ] Checked `@@GLOBAL.event_scheduler`.
- [ ] Selected one-time (`AT`) or recurring (`EVERY`) schedule.
- [ ] Defined `STARTS`, `ENDS`, and `ON COMPLETION` explicitly.
- [ ] Chose `ENABLE` or `DISABLE` at deployment time.
- [ ] Set session `time_zone` explicitly before CREATE/ALTER EVENT.
- [ ] Verified `INFORMATION_SCHEMA.EVENTS.TIME_ZONE`.
- [ ] Loaded and updated named time zone tables if using named zones.
- [ ] Determined whether schedule needs UTC, fixed offset, or local time with DST.
- [ ] Tested skipped/repeated hours if the time zone observes DST.
- [ ] Verified `TIMESTAMP`/`DATETIME` and UTC/local conventions of source data.
- [ ] Created a dedicated definer with least privilege and verified existence on execution nodes.
- [ ] Verified EVENT, EXECUTE, and required data access privileges.
- [ ] Identified which nodes are permitted to execute events during replication/failover.
- [ ] Verified `DISABLE ON SLAVE` if the job should run only on primary.
- [ ] Procedure has appropriate transactions/handlers and can be invoked manually.
- [ ] Job is idempotent per period and protected against overlapping runs.
- [ ] Run log table or observability mechanism tracks success/failure.
- [ ] Reconciliation and backfill process exists if scheduler pauses or a run fails.
- [ ] Verified definition via `SHOW CREATE EVENT` and metadata after deployment.

## 19. Conclusion

The Event Scheduler enables MySQL to execute SQL tasks on a one-time or recurring schedule. `AT` defines a single execution timestamp; `EVERY` combined with `STARTS` and `ENDS` defines a recurring schedule. `ON COMPLETION` determines whether the event is retained after its schedule finishes; `ENABLE`/`DISABLE` controls each event's status independently of the global `event_scheduler` variable.

The session time zone at the moment an event is created or altered is stored as the event's time zone. When running, the event uses that time zone for session time functions. Choose UTC for absolute-interval schedules and named time zones for local wall-clock schedules; load time zone tables and test DST transitions where applicable. Manage definers, privileges, replication, idempotency, logging, and backfill workflows so events operate safely across server restarts, scheduler pauses, and individual execution failures.

## References

- [MySQL 8.4 Reference Manual: Using the Event Scheduler](https://dev.mysql.com/doc/refman/8.4/en/events.html)
- [MySQL 8.4 Reference Manual: CREATE EVENT Statement](https://dev.mysql.com/doc/refman/8.4/en/create-event.html)
- [MySQL 8.4 Reference Manual: ALTER EVENT Statement](https://dev.mysql.com/doc/refman/8.4/en/alter-event.html)
- [MySQL 8.4 Reference Manual: The INFORMATION_SCHEMA EVENTS Table](https://dev.mysql.com/doc/refman/8.4/en/information-schema-events-table.html)
- [MySQL 8.4 Reference Manual: Time Zone Support](https://dev.mysql.com/doc/refman/8.4/en/time-zone-support.html)
- [MySQL 8.4 Reference Manual: Time Zone Variables](https://dev.mysql.com/doc/refman/8.4/en/time-zone-variables.html)
- [MySQL 8.4 Reference Manual: Replication and Events](https://dev.mysql.com/doc/refman/8.4/en/replication-features-events.html)
