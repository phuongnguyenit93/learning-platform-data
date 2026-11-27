# DEFINER, Execution Privileges, and Event Status

Triggers and Events are two automation mechanisms in MySQL. A Trigger runs when an INSERT, UPDATE, or DELETE operation acts on a table; an Event is executed by the Event Scheduler on a schedule. Both can run SQL without the caller explicitly sending each statement.

Because they execute automatically, a critical security question is: **whose privileges are used to execute the SQL inside?** MySQL stores a DEFINER account for triggers and events. When a trigger fires or an event reaches its scheduled time, the object body executes in the definer's security context. The privileges of the user running UPDATE or the administrator inspecting events do not automatically replace the definer's privileges.

In addition to definer privileges, an Event depends on its own per-event status and the `event_scheduler` system variable. An event may be marked ENABLE yet not run because the scheduler is OFF; the scheduler may be ON yet the event remains DISABLED. Both layers of state must be checked.

This lesson belongs to the **Triggers and Events** chapter of the DATABASE_MYSQL module. It focuses on DEFINER, creation and execution privileges, definer account lifecycle, event status, the Event Scheduler, metadata, and common operational scenarios.

## 1. What Is DEFINER?

DEFINER is a MySQL account bound to a stored object. For triggers and events, the definer determines the security context used to execute the object body.

A MySQL account has both a user and a host:

~~~sql
'app_trigger'@'localhost'
'app_trigger'@'%'
~~~

The two accounts above are distinct principals. Privileges granted to app_trigger@localhost do not automatically apply to app_trigger@%. When declaring DEFINER, specify both user and host accurately.

If DEFINER is omitted when creating an object, MySQL defaults to the current account at creation time. You can inspect the current account with:

~~~sql
SELECT CURRENT_USER(), USER();
~~~

Inside a stored object running with definer security context, CURRENT_USER() reflects the account used for privilege checking of the object. USER() reflects the connecting session identity. Do not use these two functions as a substitute for inspecting DEFINER metadata.

### DEFINER Is Not the Caller

Example:

1. Account app_writer has UPDATE privilege on table orders.
2. An AFTER UPDATE trigger on orders is created with DEFINER set to audit_trigger.
3. When app_writer updates a row, the trigger runs.
4. SQL statements inside the trigger are checked against audit_trigger's privileges.

Consequently, app_writer does not necessarily need INSERT privilege on audit_log if the trigger definer already holds the required INSERT privilege. This encapsulates privileges, yet also makes the definer an important security boundary.

## 2. Which Security Context Do Triggers and Events Use?

Triggers and Events both bind to a DEFINER, though their syntax and operation differ.

| Object | Runtime Security Context | SQL SECURITY INVOKER Option? |
|---|---|---|
| Trigger | Privileges of DEFINER stored in trigger metadata. | No. Triggers have no SQL SECURITY INVOKER option. |
| Event | Privileges of DEFINER stored in event metadata. | No. Events have no SQL SECURITY INVOKER option. |
| Stored procedure | Depends on declared SQL SECURITY DEFINER or INVOKER. | Yes. |
| Stored function | Depends on declared SQL SECURITY DEFINER or INVOKER. | Yes. |

Do not write SQL SECURITY INVOKER in trigger or event definitions. If a routine is called from a trigger/event, that routine may carry its own security characteristic; evaluate the security context chain of the entire call path.

### Triggers Do Not Run with the Updating User's Privileges

The caller needs privileges to execute the base operation on the table. When the operation fires a trigger, MySQL executes the trigger as the definer. Therefore, check two parts:

- The caller's privileges for INSERT/UPDATE/DELETE on the table manipulated by the application.
- The trigger definer's privileges on tables, views, or routines used inside the trigger body.

### Events Do Not Run with the Scheduler-Enabling Admin's Privileges

The Event Scheduler is an internal server component. When the scheduled time arrives, the scheduler executes the event using the definer stored in event metadata. The account that enabled event_scheduler or a user running SHOW EVENTS does not automatically become the executor of the body.

## 3. Privileges at Creation Time vs. Execution Time

Do not lump all privileges into a single requirement. At least two points in time must be distinguished:

1. **Creating or altering the object:** the deployment account needs the TRIGGER privilege on the table when creating a trigger, the EVENT privilege on the schema when creating an event, and special privileges if specifying a DEFINER other than the current account.
2. **Firing/executing the object:** the definer needs privileges for operations performed in the body. If privileges are revoked or the account is no longer valid, the object can fail at runtime.

### Privileges Typically Needed for Triggers

- The account creating the trigger needs the TRIGGER privilege on the attached table.
- If creating a trigger with a DEFINER other than CURRENT_USER, the deployment account needs the appropriate dynamic privilege to specify another definer; privilege names vary across MySQL versions.
- The trigger definer needs data privileges used by the trigger body, such as SELECT, INSERT, or UPDATE on involved tables.

### Privileges Typically Needed for Events

- The account creating the event needs the EVENT privilege on the schema containing the event.
- If specifying a DEFINER other than CURRENT_USER, the deployment account needs the special privilege to set another definer according to the MySQL version.
- The event definer needs data privileges required to run the event body, such as SELECT, UPDATE, or DELETE on processed tables.
- Enabling/disabling the scheduler is a server administration operation and requires the corresponding system variable administration privilege.

### Creation Account Need Not Be the Execution Account

A deployment account can create the object and assign a service account as definer. After deployment, the service account owns the runtime security context. The deployment account does not need to serve as the application account or scheduler account.

That is why you should separate:

- Deployment account: creates/alters objects during releases.
- Definer account: holds least privilege required for the body to run.
- Application account: holds only required business operation privileges.
- Operator account: monitors status, toggles scheduler, or troubleshoots per operational roles.

## 4. Creating Definer Accounts with Least Privilege

Do not use root or a full-privilege DBA account as definer for all triggers/events. If an object is exploited or misdefined, overly broad privileges widen the blast radius.

Example creating a dedicated service account for a trigger:

~~~sql
CREATE USER 'orders_trigger'@'localhost'
IDENTIFIED BY '<managed-secret>';
~~~

Suppose the trigger updates an audit table when order status changes. Grant only the required privileges:

~~~sql
GRANT TRIGGER ON shop.orders
TO 'orders_trigger'@'localhost';

GRANT INSERT ON shop.order_audit
TO 'orders_trigger'@'localhost';
~~~

The trigger definer needs the TRIGGER privilege on the attached table and privileges for tables accessed in the body. OLD and NEW are row values provided by the trigger context; they do not issue a separate SELECT against the source table. Only grant SELECT if the body actually runs queries reading that table.

The deployment account needs the TRIGGER privilege on the table:

~~~sql
GRANT TRIGGER ON shop.orders
TO 'schema_deployer'@'localhost';
~~~

If deployment specifies a definer other than the current account, a special dynamic privilege is required. In some MySQL 8.0 releases, the relevant privilege is SET_USER_ID; newer versions have changes/deprecations and may use SET_ANY_DEFINER. Verify the exact privilege name for your server version and grant it only to controlled deployment accounts.

Never grant definer-setting privileges to ordinary application accounts.

## 5. Creating a Trigger with DEFINER

Suppose there are orders and audit tables:

~~~sql
CREATE TABLE shop.orders (
    order_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    updated_at TIMESTAMP NOT NULL
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (order_id)
) ENGINE=InnoDB;

CREATE TABLE shop.order_audit (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    old_status VARCHAR(20) NOT NULL,
    new_status VARCHAR(20) NOT NULL,
    changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (audit_id),
    KEY idx_order_audit_order (order_id)
) ENGINE=InnoDB;
~~~

Create the trigger:

~~~sql
DELIMITER //

CREATE DEFINER = 'orders_trigger'@'localhost'
TRIGGER shop.trg_orders_status_audit
AFTER UPDATE ON shop.orders
FOR EACH ROW
BEGIN
    IF NOT (OLD.status <=> NEW.status) THEN
        INSERT INTO shop.order_audit (
            order_id,
            old_status,
            new_status
        )
        VALUES (
            NEW.order_id,
            OLD.status,
            NEW.status
        );
    END IF;
END//

DELIMITER ;
~~~

The trigger only writes an audit when status actually changes. The null-safe equality operator <=> compares safely even when either side could be NULL; in the sample schema status is NOT NULL, so the comparison remains clean.

### When the Trigger Fires

~~~sql
UPDATE shop.orders
SET status = 'PAID'
WHERE order_id = 1001;
~~~

If the UPDATE succeeds, the AFTER UPDATE trigger fires for each updated row. The trigger writes a row into order_audit using the privileges of orders_trigger@localhost.

The caller needs UPDATE privilege on shop.orders. The caller does not need direct INSERT privilege on shop.order_audit if the trigger's security context holds the required privilege and all other conditions are valid.

### Trigger Errors Affect the Triggering Statement

If INSERT into order_audit fails, the UPDATE statement that fired the trigger also fails. With InnoDB, statement changes roll back on trigger error. If the caller is inside a transaction with earlier statements, the entire transaction is not automatically rolled back solely due to the trigger error; the caller must decide on rollback per the transaction contract.

Do not use triggers to hide audit errors by ignoring exceptions when auditing is a mandatory business requirement.

## 6. Definer Accounts Must Exist and Have Managed Lifecycles

Definer is a reference to a MySQL account, not a snapshot of privileges permanently embedded inside the trigger/event. If the account is removed with DROP USER, changes host, or loses required privileges, the object can fail to execute.

Common risks:

- The definer account is deleted during stale-user cleanup.
- The account is recreated with a different host, causing the account name to no longer match.
- SELECT/INSERT/UPDATE/DELETE privileges needed by the body are revoked.
- The definer was a personal account of an employee who left the organization.
- Objects are restored/migrated to another server without creating the corresponding definer account.

### Never Delete a Definer Before Transferring Objects

Before running DROP USER, list triggers and events referencing that account. Transfer objects to a managed service account, verify grants, redeploy or run ALTER EVENT appropriately, and only then drop the old account.

Never assume DROP USER automatically updates the DEFINER of triggers/events. Deleting an account is not a security context handoff procedure.

## 7. Changing the DEFINER of Triggers and Events

### Triggers

MySQL does not provide ALTER TRIGGER to change only the DEFINER. The standard management approach is to capture the existing definition and recreate the trigger with the new DEFINER in a controlled migration.

Workflow:

1. Save the definition using SHOW CREATE TRIGGER.
2. Identify the new definer and required grants.
3. Prepare the CREATE TRIGGER statement with the new DEFINER.
4. Execute DROP TRIGGER and CREATE TRIGGER within an appropriate migration window.
5. Inspect TRIGGERS metadata and run test UPDATE/INSERT/DELETE statements that fire the trigger.

DROP followed by CREATE creates a window where the trigger does not exist if deployment is not atomic from the application's perspective. Evaluate write impact during migration, metadata locks, and deployment steps.

### Events

An event can be modified with ALTER EVENT, including DEFINER:

~~~sql
ALTER DEFINER = 'archive_scheduler'@'localhost'
EVENT shop.evt_archive_expired;
~~~

After changing it, verify metadata and the new definer's privileges. Do not check only that the ALTER statement succeeded; an event might only fail at its next scheduled run if the definer lacks table privileges.

### Inspecting Current Definitions

~~~sql
SHOW CREATE TRIGGER shop.trg_orders_status_audit;
SHOW CREATE EVENT shop.evt_archive_expired;
~~~

SHOW CREATE displays the DDL statement and attributes such as DEFINER, schedule, status, or SQL body. Metadata visibility depends on the inspecting user's privileges and server configuration.

## 8. What Is an Event and What Does the Event Scheduler Do?

An Event is an object storing an SQL execution schedule. The Event Scheduler is an internal MySQL thread that checks schedules and triggers enabled events when their scheduled time arrives.

An event has:

- Name and schema.
- DEFINER.
- One-time or recurring schedule.
- Start/end timestamps if configured.
- ENABLE/DISABLE status.
- Post-completion behavior with ON COMPLETION.
- SQL body in the DO clause.
- Time zone used to interpret the schedule.

An event does not run merely because it exists. An active scheduler and an event status permitting execution are both required.

### Recurring Event Example

Create a table storing expired sessions:

~~~sql
CREATE TABLE shop.user_sessions (
    session_id BIGINT UNSIGNED NOT NULL,
    expires_at DATETIME NOT NULL,
    PRIMARY KEY (session_id),
    KEY idx_user_sessions_expires (expires_at)
) ENGINE=InnoDB;
~~~

Create a service account for the event:

~~~sql
CREATE USER 'session_cleanup'@'localhost'
IDENTIFIED BY '<managed-secret>';

GRANT DELETE ON shop.user_sessions
TO 'session_cleanup'@'localhost';
~~~

The deployment account needs EVENT privilege on the schema:

~~~sql
GRANT EVENT ON shop.*
TO 'event_deployer'@'localhost';
~~~

Create the event:

~~~sql
CREATE DEFINER = 'session_cleanup'@'localhost'
EVENT shop.evt_delete_expired_sessions
ON SCHEDULE EVERY 1 HOUR
STARTS CURRENT_TIMESTAMP + INTERVAL 1 HOUR
ON COMPLETION PRESERVE
ENABLE
DO
    DELETE FROM shop.user_sessions
    WHERE expires_at < CURRENT_TIMESTAMP;
~~~

The event runs hourly. When scheduled, the Event Scheduler executes DELETE using the privileges of session_cleanup@localhost. The event definer account only needs DELETE privilege on this table for the simple body in this example.

In large data environments, an unbounded DELETE can generate a huge transaction, undo logs, locks, and replication lag. Design batch cleanup, an index on expires_at, and runtime monitoring if the table is large.

## 9. Two Layers of Status: event_scheduler and Per-Event Status

For an event to execute, both conditions are required:

1. The event_scheduler system variable allows the scheduler to run.
2. The specific event is in ENABLED status.

| event_scheduler | Event Status | Result |
|---|---|---|
| ON | ENABLED | Scheduler can run the event when scheduled. |
| ON | DISABLED | Event is not executed. |
| OFF | ENABLED | Event is enabled, but scheduler does not trigger it while OFF. |
| OFF | DISABLED | Event does not run. |
| DISABLED | ENABLED | Scheduler is disabled at server level; event does not run. |

### Checking event_scheduler

~~~sql
SHOW GLOBAL VARIABLES LIKE 'event_scheduler';
~~~

Meaningful values:

- ON: Event Scheduler is running.
- OFF: Scheduler is not running; can be turned back on if configuration and privileges allow.
- DISABLED: Scheduler is disabled at server level and cannot be re-enabled with SET GLOBAL alone at runtime.

To enable the scheduler at runtime:

~~~sql
SET GLOBAL event_scheduler = ON;
~~~

This requires the appropriate system variable privilege, typically SYSTEM_VARIABLES_ADMIN in MySQL 8.0; SUPER is the older privilege replaced/deprecated in many contexts. If the server started with event_scheduler=DISABLED, you must update startup configuration and restart following operational procedures.

Never enable the scheduler on a replica or every node in a cluster without first verifying which node is allowed to run events.

## 10. ENABLE, DISABLE, and Replica Status

An individual event's status can be changed with ALTER EVENT:

~~~sql
ALTER EVENT shop.evt_delete_expired_sessions DISABLE;

ALTER EVENT shop.evt_delete_expired_sessions ENABLE;
~~~

ENABLE allows the scheduler to consider the event for execution. DISABLE keeps the definition while preventing execution. This pauses a schedule without dropping and recreating it.

### DISABLE ON SLAVE / DISABLE ON REPLICA and Replication

MySQL includes DISABLE ON SLAVE syntax for events in certain versions and replication contexts; newer releases use DISABLE ON REPLICA terminology. The DISABLE ON SLAVE syntax is deprecated in newer MySQL 8.0 releases. Metadata may still display SLAVESIDE_DISABLED status. Check the manual for your exact version before creating or altering events.

Do not rely on DISABLE ON SLAVE as the sole safeguard against duplicate execution. Design the topology explicitly:

- Define which primary node is permitted to run scheduled jobs.
- Set event_scheduler OFF or ensure events are disabled on replicas per policy.
- Verify event statuses after failover.
- When a replica is promoted, confirm only the new node is permitted to run jobs.
- For jobs with external side effects, use coordination locks/idempotency to prevent duplicate execution.

### Replicated Events Do Not Mean Events Should Run on Every Node

Event DDL can replicate across replication links. If multiple servers simultaneously have scheduler ON and events ENABLED, the same job can run in multiple places depending on topology and event status. This is a major risk for jobs sending emails, deleting data, generating invoices, or calling external systems.

## 11. ON COMPLETION and Event Lifecycle

A one-time event can be configured to auto-delete upon completion or be retained:

~~~sql
CREATE DEFINER = 'session_cleanup'@'localhost'
EVENT shop.evt_one_time_cleanup
ON SCHEDULE AT CURRENT_TIMESTAMP + INTERVAL 1 DAY
ON COMPLETION NOT PRESERVE
ENABLE
DO
    DELETE FROM shop.user_sessions
    WHERE expires_at < CURRENT_TIMESTAMP;
~~~

ON COMPLETION NOT PRESERVE is the default behavior for one-time events unless specified otherwise: after completion, the event is dropped automatically. ON COMPLETION PRESERVE keeps the event in metadata after the one-time schedule completes and transitions the event to DISABLED status; it will not rerun without a new schedule.

For recurring events, ON COMPLETION PRESERVE is commonly used to retain the schedule definition. Inspect SHOW CREATE EVENT and metadata to confirm the intended behavior.

## 12. Event Time Zone

An event stores the time zone used to interpret its schedule. If not specified otherwise, the creating session's time zone is recorded at creation time. Thus, two operators running the same schedule expression in two sessions with different time zones can produce different execution schedules.

Inspect:

~~~sql
SHOW CREATE EVENT shop.evt_delete_expired_sessions;

SELECT
    EVENT_SCHEMA,
    EVENT_NAME,
    TIME_ZONE,
    STARTS,
    ENDS,
    LAST_EXECUTED
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA = 'shop';
~~~

For business schedules following local time, make explicit decisions about daylight saving time, server time zone, and session time zone. If business rules call for UTC schedules, create and manage events inside a UTC session and verify the stored TIME_ZONE. Never assume CURRENT_TIMESTAMP inside the body always matches the operator's client machine time zone.

## 13. Monitoring Trigger Metadata

List triggers in a schema:

~~~sql
SELECT
    TRIGGER_SCHEMA,
    TRIGGER_NAME,
    EVENT_MANIPULATION,
    EVENT_OBJECT_TABLE,
    ACTION_TIMING,
    DEFINER,
    ACTION_ORDER,
    SQL_MODE
FROM INFORMATION_SCHEMA.TRIGGERS
WHERE TRIGGER_SCHEMA = 'shop'
ORDER BY EVENT_OBJECT_TABLE, ACTION_TIMING, EVENT_MANIPULATION, ACTION_ORDER;
~~~

Key columns:

- TRIGGER_NAME: trigger name.
- EVENT_MANIPULATION: INSERT, UPDATE, or DELETE.
- EVENT_OBJECT_TABLE: table monitored by the trigger.
- ACTION_TIMING: BEFORE or AFTER.
- DEFINER: security context account.
- ACTION_ORDER: ordering when multiple triggers share the same timing and event on a table.
- SQL_MODE: SQL mode stored when the trigger was created.

Inspect definition:

~~~sql
SHOW CREATE TRIGGER shop.trg_orders_status_audit;
~~~

When investigating errors, compare DEFINER against existing accounts and run SHOW GRANTS for that account. Do not check only the application account's privileges.

## 14. Monitoring Event Metadata

List events:

~~~sql
SHOW EVENTS FROM shop;
~~~

Or query INFORMATION_SCHEMA:

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
    STARTS,
    ENDS,
    STATUS,
    ON_COMPLETION,
    LAST_EXECUTED,
    SQL_MODE
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA = 'shop'
ORDER BY EVENT_NAME;
~~~

Common metadata statuses:

| STATUS | Meaning |
|---|---|
| ENABLED | Event is enabled and eligible at the event level for the scheduler to run. |
| DISABLED | Event is disabled. |
| SLAVESIDE_DISABLED | Event is disabled on the replica side per the applicable replication/version mechanism. |

LAST_EXECUTED shows the most recent recorded execution time; NULL usually means the event has never run or no execution has been recorded. It does not by itself prove the run succeeded. Check the error log, business outcomes, or an application-designed run history table.

Inspect DDL:

~~~sql
SHOW CREATE EVENT shop.evt_delete_expired_sessions;
~~~

### Monitoring the Scheduler Thread

~~~sql
SHOW PROCESSLIST;
~~~

When the Event Scheduler is active, the process list may display the event_scheduler thread. Not seeing this thread can indicate the scheduler is OFF/DISABLED or another server state; verify using system variables before concluding.

## 15. Checking Definer and Privileges on Failure

When a trigger or event does not run as expected, check in order:

1. Does the object exist?
2. Which account and host is recorded as DEFINER in metadata?
3. Does that account still exist?
4. Is the account locked or has its authentication policy changed?
5. Are SELECT/INSERT/UPDATE/DELETE privileges needed by the body still sufficient?
6. Does the body call another routine with its own security context?
7. Is the event ENABLED?
8. Is event_scheduler ON?
9. Are schedule, STARTS, ENDS, and TIME_ZONE accurate?
10. Does the error log record an error from the event run?

Inspect accounts:

~~~sql
SHOW GRANTS FOR 'orders_trigger'@'localhost';
SHOW GRANTS FOR 'session_cleanup'@'localhost';
~~~

Check account existence:

~~~sql
SELECT User, Host
FROM mysql.user
WHERE User IN ('orders_trigger', 'session_cleanup');
~~~

Querying mysql.user requires appropriate administrative privileges. In administrative applications, use account management tools rather than granting SELECT on mysql.* to regular operators.

## 16. Auditing Objects with Orphan Definers

When migrating or cleaning up accounts, locate objects whose DEFINER no longer matches an account in mysql.user. The queries below are for DBAs with privileges to read system metadata.

Triggers:

~~~sql
SELECT
    t.TRIGGER_SCHEMA,
    t.TRIGGER_NAME,
    t.DEFINER
FROM INFORMATION_SCHEMA.TRIGGERS AS t
LEFT JOIN mysql.user AS u
  ON t.DEFINER = CONCAT(u.User, '@', u.Host)
WHERE u.User IS NULL;
~~~

Events:

~~~sql
SELECT
    e.EVENT_SCHEMA,
    e.EVENT_NAME,
    e.DEFINER,
    e.STATUS
FROM INFORMATION_SCHEMA.EVENTS AS e
LEFT JOIN mysql.user AS u
  ON e.DEFINER = CONCAT(u.User, '@', u.Host)
WHERE u.User IS NULL;
~~~

These queries are preliminary checks on the DEFINER string; pay attention to account formatting, host matching, and metadata privileges on your specific version. Never bulk-assign all orphans to one shared definer automatically. Each object requires distinct privileges; identify the owner, review the body, and grant least privilege to the new definer.

## 17. Event Scheduler Administration Privileges

Event Scheduler is a GLOBAL system variable. Regular application accounts should not have privileges to change it.

Check:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'event_scheduler';
~~~

The event_scheduler variable is a system variable, not an execution history. Metadata in INFORMATION_SCHEMA.EVENTS and the server error log are the primary sources for inspecting definitions/status and execution errors.

Toggle at runtime:

~~~sql
SET GLOBAL event_scheduler = OFF;
SET GLOBAL event_scheduler = ON;
~~~

This is an operational action affecting every event on the instance. Before setting OFF, identify which jobs depend on the scheduler, the impact of missed runs, and how to backfill. Before setting ON, verify no stale or replicated events will fire unexpectedly.

### Startup Configuration

event_scheduler can be configured in the server configuration file or startup parameters:

~~~ini
[mysqld]
event_scheduler=ON
~~~

If set to DISABLED at server startup, the scheduler is disabled server-wide and cannot be switched to ON with SET GLOBAL during the running session. Changing startup configuration requires a controlled restart procedure.

## 18. Replication, Failover, and Scheduled Jobs

An event is a schema object and can participate in replication. If the source creates an event, the DDL can be written to the binary log and applied on replicas. Event status on a replica depends on event creation syntax, replication behavior, and server version.

In systems with failover:

- Designate clearly which node is the scheduler owner.
- Prevent events from running on replicas serving read traffic unless permitted.
- After promotion, check event_scheduler and each event's status.
- Avoid windows where both old primary and new primary run jobs simultaneously.
- Design jobs to be idempotent or use distributed locks/leases if duplicate execution is possible.
- Log executions with job ID, timestamp, status, and affected row counts.

The Event Scheduler is not a distributed orchestration system. It does not automatically guarantee that only one instance among multiple independent servers runs the same logic. Failover policy must be part of operational design.

### Never Run Events Solely Because a Node Is a Replica

Do not infer node role from hostname or schema name. Use system topology/role metadata, replication state, and managed failover workflows. Enabling the scheduler is an operational decision with data impact.

## 19. Logging and Observability for Event Runs

MySQL does not provide a complete business run table for every event execution. For critical jobs, record run history using an appropriate design:

~~~sql
CREATE TABLE shop.event_run_log (
    run_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_name VARCHAR(128) NOT NULL,
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP NULL,
    status VARCHAR(20) NOT NULL,
    affected_rows BIGINT NULL,
    error_code INT NULL,
    error_message VARCHAR(512) NULL,
    PRIMARY KEY (run_id),
    KEY idx_event_run_log_name_started (event_name, started_at)
) ENGINE=InnoDB;
~~~

A stored procedure called by an event can log start/finish states and catch exceptions to record failures. Decide clearly on transaction boundaries between job and log: if the entire body rolls back, logs inside the same transaction also roll back. You can use application/observability-layer logging or design an appropriate logging boundary.

Never log passwords, tokens, personal data, or sensitive SQL text. Record only error codes, event names, run IDs, and metadata sufficient for investigation.

## 20. Common Operational Issues

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Trigger reports privilege error on UPDATE | Definer lacks privileges on tables used in trigger body | SHOW CREATE TRIGGER, INFORMATION_SCHEMA.TRIGGERS, SHOW GRANTS. |
| Trigger stops running after migration | Trigger omitted during dump/restore or definer missing | Inspect trigger metadata and definer account. |
| Event ENABLED yet does not run | event_scheduler OFF/DISABLED, schedule not reached, or event expired | Check system variable, STATUS, STARTS/ENDS/TIME_ZONE. |
| Event runs then errors | Definer lacks privileges, table schema changed, body raises error | Check error log, SHOW CREATE EVENT, and grants. |
| Event runs twice on two servers | Scheduler enabled on multiple nodes or failover overlap | Check topology, scheduler owner, replication, and idempotency. |
| Event runs at wrong time | Creating session's time zone differed from expected | Check TIME_ZONE and SHOW CREATE EVENT. |
| Event disappears after running | ON COMPLETION NOT PRESERVE on one-time event | Check ON_COMPLETION and schedule definition. |
| Event does not run after restore | Scheduler OFF, definer not recreated, or event DISABLED | Check event_scheduler, account, metadata, and grants. |
| Trigger slows down UPDATE | Trigger body reads/writes extra tables, lacks indexes, or processes many rows | Profile statement, inspect body, indexes, and lock waits. |
| DROP USER breaks stored objects | Account was definer of triggers/events | Audit DEFINER before deleting accounts. |

## 21. Safe Deployment Checklist

### Before Creating Triggers/Events

- [ ] Identified the exact table or schedule requiring automation.
- [ ] Selected a dedicated service account definer, never root.
- [ ] Granted least privilege required for the body.
- [ ] Granted object creation privileges to the deployment account.
- [ ] If specifying a different definer, verified the dynamic privilege appropriate for the version.
- [ ] Reviewed body to avoid unnecessary dynamic SQL and out-of-scope operations.
- [ ] Defined transaction behavior and error handling.
- [ ] For events, defined scheduler owner and time zone.

### After Deployment

- [ ] Executed SHOW CREATE TRIGGER/EVENT.
- [ ] Verified DEFINER in INFORMATION_SCHEMA.
- [ ] Confirmed the definer account exists and holds required grants.
- [ ] For triggers, tested corresponding INSERT/UPDATE/DELETE operations.
- [ ] For events, verified event_scheduler and STATUS.
- [ ] Checked STARTS/ENDS/TIME_ZONE schedule settings.
- [ ] Checked logs and business results after initial execution.
- [ ] Confirmed replicas do not run unintended jobs.
- [ ] Documented owner and procedure to rotate definer when accounts are replaced.

### Before Dropping or Locking an Account

- [ ] Found all triggers and events using the account.
- [ ] Identified replacement service account.
- [ ] Reviewed body privileges and granted least privilege.
- [ ] Updated definers through an appropriate migration workflow.
- [ ] Tested objects after the change.
- [ ] Executed DROP USER only after zero dependent objects remain.

## 22. Practice Exercises

### Exercise A — Observing Trigger DEFINER

1. Create orders and order_audit tables.
2. Create an orders_trigger service account with required privileges.
3. Create a trigger with an explicit DEFINER.
4. Run SHOW CREATE TRIGGER and query INFORMATION_SCHEMA.TRIGGERS.
5. Use an application account with only UPDATE privilege on orders to fire the trigger.
6. Confirm the audit row is written under the definer's security context.

### Exercise B — Missing Definer Privileges

1. Revoke INSERT privilege on order_audit from orders_trigger.
2. Run an UPDATE on orders that changes status.
3. Observe the statement fail because the trigger cannot INSERT.
4. Inspect the state of orders and audit_log in InnoDB.
5. Re-grant least privileges and rerun the test.

### Exercise C — Creating and Enabling an Event

1. Create user_sessions and service account session_cleanup.
2. Grant DELETE on user_sessions.
3. Create a one-time event scheduled shortly in the future in a test environment.
4. Check SHOW EVENTS and INFORMATION_SCHEMA.EVENTS.
5. Monitor LAST_EXECUTED and data results.
6. Try DISABLE and then ENABLE on the event.

### Exercise D — Distinguishing Scheduler and Event Status

1. Set event_scheduler=OFF in a test environment with admin privileges.
2. Keep the event in ENABLED state.
3. Observe that the event does not run while the scheduler is OFF.
4. Turn the scheduler ON.
5. Create a DISABLED event and confirm it still does not run.
6. Explain why both status layers must be checked.

### Exercise E — Orphan Definers and Handoff

1. Create a trigger/event using a dedicated service account.
2. Query INFORMATION_SCHEMA to list DEFINERs.
3. In a test environment, simulate the account being dropped or mismatched in host.
4. Identify affected objects.
5. Create a replacement account, grant least privilege, and transfer definers per workflow.
6. Retest the trigger/event to confirm.

### Exercise F — Replication and Failover

1. Deploy an event on the source and observe metadata on the replica.
2. Confirm replica event status per version/configuration.
3. Ensure only the designated node runs the scheduler.
4. Simulate failover in a staging environment.
5. Verify jobs do not run twice and can retry safely.

You have completed this lesson when you can explain that triggers/events run under the definer's privileges, distinguish creation privileges from execution privileges, diagnose a definer lacking privileges or orphaned, and inspect both event_scheduler and per-event status accurately.

## 23. Principles to Remember

- DEFINER determines the security context of triggers and events at runtime.
- Triggers and Events do not have an SQL SECURITY INVOKER option.
- The caller needs privileges for the base operation; the definer needs privileges for statements inside the body.
- The deployment account needs object-creation privileges and special privileges if specifying a definer other than the current account.
- Use dedicated service accounts with least privilege; avoid root or personal accounts.
- A trigger definer lacking privileges can cause triggering INSERT/UPDATE/DELETE statements to fail.
- An event requires both event_scheduler allowing execution and event status ENABLED.
- event_scheduler has ON, OFF, and DISABLED; DISABLED cannot be re-enabled via SET GLOBAL at runtime.
- ENABLE/DISABLE is per-event status, independent of the server-wide scheduler variable.
- Events store a time zone; check TIME_ZONE before concluding a schedule is wrong.
- ON COMPLETION affects the lifecycle of one-time events.
- Inspect DEFINER via INFORMATION_SCHEMA and SHOW CREATE.
- Never DROP USER before auditing triggers/events dependent on that account.
- Event replication and failover require a clear scheduler owner plus duplicate-run protection.
- Use controlled run history/logging for critical jobs; do not rely solely on LAST_EXECUTED to conclude success.

When DEFINER, grants, and Event Scheduler status are properly managed, triggers and events can automate tasks while maintaining clear privilege boundaries. Verify the executing account, body privileges, event status, and server role before putting any automation into production.
