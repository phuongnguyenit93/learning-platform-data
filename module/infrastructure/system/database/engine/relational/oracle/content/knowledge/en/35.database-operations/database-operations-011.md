# Maintenance Windows, Auto Tasks, and Controlling Maintenance Schedules in Oracle Database

Oracle Database includes built-in scheduling mechanisms for executing periodic maintenance work. A maintenance window is a time interval defined by Scheduler during which automatic maintenance tasks can run under a resource policy. Automatic Maintenance Tasks use these windows to gather optimizer statistics, analyze segments, and perform configured SQL tuning tasks.

In real-world operations, DBAs also coordinate tasks executed by people or deployment systems: backups, patching, schema changes, index rebuilds, recovery drills, service failovers, and operating system maintenance. These activities require a clear maintenance schedule with an owner, time limits, stop criteria, and a rollback plan.

Distinguish three layers:

- **Scheduler maintenance window:** a schedule object in Oracle Scheduler with a start time, duration, resource plan, and status.
- **Automatic Maintenance Tasks:** Oracle-managed maintenance clients permitted to run inside maintenance windows when both the client and window are enabled.
- **Organizational maintenance window:** a time period agreed upon by DBA/operations with application teams, users, backup, network, and OS teams to deploy changes.

Opening a Scheduler window does not automatically put the application into maintenance mode, block DML/DDL, or guarantee every job finishes. It is a scheduling and resource management mechanism; service coordination still requires a dedicated runbook.

This lesson uses Oracle Database 19c as its baseline, explaining default window schedules, window groups, auto tasks, inspecting schedules and history, adjusting maintenance timing, resolving conflicts, managing timezones, and building a controllable maintenance workflow.

## 1. What Is a Maintenance Window?

### 1.1. Scheduler Windows

Oracle Scheduler manages a window as a schedule object. A window defines:
- When the window starts.
- Which recurrence schedule it follows.
- How long the window remains open.
- Which Resource Manager plan is activated when the window opens.
- Window priority when schedules overlap.
- Enabled/disabled state and open/close history.

Windows can be used to define when window-dependent jobs run, including automatic maintenance tasks.

### 1.2. A Window Is Not a Database Lockout Period

While a maintenance window is open:
- The database can still serve applications.
- User sessions can still connect and run SQL if the service/database is open.
- Eligible auto tasks can be launched by Scheduler.
- Resource Manager can activate the resource plan attached to the window.
- Other Scheduler jobs can run according to their own rules.

A window does not automatically:
- Block user logins.
- Stop running transactions.
- Prevent applications from writing data.
- Shut down services or listeners.
- Take backups.
- Patch the Oracle home.
- Guarantee that all maintenance jobs run.

If downtime is needed, the DBA must coordinate with application/service management, drain connections, verify transactions, take backups, and follow change procedures.

### 1.3. Three Time Layers to Manage

| Layer | Examples | Tools/Processes |
| --- | --- | --- |
| Oracle auto maintenance | Statistics collection, Segment Advisor | Scheduler windows, DBMS_AUTO_TASK_ADMIN |
| DBA-created operational jobs | Backup checks, staging purges, data validation | DBMS_SCHEDULER, runbook |
| Full-system maintenance | Database/OS patching, upgrades, storage migration | Change management, application downtime, backup/recovery plan |

Do not lump every activity into a single Scheduler window. Each task can have different durations, risk levels, privileges, and downtime requirements.

## 2. Default Maintenance Windows in Oracle

### 2.1. Maintenance Window Groups

Oracle provides default Scheduler windows and window groups for maintenance. Common names in 19c databases include:
- MONDAY_WINDOW through FRIDAY_WINDOW.
- SATURDAY_WINDOW and SUNDAY_WINDOW.
- WEEKNIGHT_WINDOW.
- WEEKEND_WINDOW.
- MAINTENANCE_WINDOW_GROUP.

Weekday windows are typically grouped into WEEKNIGHT_WINDOW; weekend windows are grouped into WEEKEND_WINDOW. MAINTENANCE_WINDOW_GROUP aggregates the groups/windows used by automatic maintenance tasks.

Do not assume default schedules have not been modified by a DBA. Always query metadata in the current database before scheduling.

### 2.2. Common Default Schedule Patterns

Many databases keep Oracle's default pattern:
- Weekdays starting around 22:00, lasting roughly 4 hours.
- Saturday and Sunday starting around 06:00, lasting roughly 20 hours.

This is a common default pattern, not a guarantee of the current state in every system. Schedules may have been adjusted for timezones, application needs, or version/configuration. The Scheduler queries below are the authoritative source.

### 2.3. Viewing the List of Windows

~~~sql
SELECT window_name,
       resource_plan,
       duration,
       repeat_interval,
       enabled,
       active,
       next_start_date,
       last_start_date
FROM   dba_scheduler_windows
ORDER  BY window_name;
~~~

The columns show:
- WINDOW_NAME: name of the window.
- RESOURCE_PLAN: Resource Manager plan attached to the window.
- DURATION: length of each open window.
- REPEAT_INTERVAL: recurrence expression.
- ENABLED: whether the window is enabled.
- ACTIVE: whether the window is currently open.
- NEXT_START_DATE/LAST_START_DATE: next scheduled start and most recent start time.

Some columns may show NULL if the window has never run or has no upcoming schedule. Access to DBA_SCHEDULER_WINDOWS depends on account privileges.

### 2.4. Viewing Members of Window Groups

~~~sql
SELECT window_group_name,
       window_name
FROM   dba_scheduler_wingroup_members
WHERE  window_group_name IN (
           'MAINTENANCE_WINDOW_GROUP',
           'WEEKNIGHT_WINDOW',
           'WEEKEND_WINDOW'
       )
ORDER  BY window_group_name, window_name;
~~~

This query shows which windows or groups belong to each group. A group can contain another group, so inspect the full hierarchy if schedules have been customized.

### 2.5. Viewing Window Groups

~~~sql
SELECT group_name,
       enabled,
       number_of_members
FROM   dba_scheduler_window_groups
ORDER  BY group_name;
~~~

If a view or column differs in your release or under your privileges, run DESC on the corresponding view and check Oracle Database Reference. Do not alter default groups before confirming membership and auto task impact.

## 3. Automatic Maintenance Tasks

### 3.1. Three Common Maintenance Clients

Oracle 19c provides three primary automatic maintenance task clients:

| Automatic task | Common client name | Purpose |
| --- | --- | --- |
| Automatic Optimizer Statistics Collection | auto optimizer stats collection | Gathers statistics on stale/missing objects for better optimizer estimates |
| Automatic Segment Advisor | auto space advisor | Analyzes segments and recommends space reclamation or management actions |
| Automatic SQL Tuning Advisor | sql tuning advisor | Analyzes SQL and produces tuning recommendations per configuration/licensing |

Client names must be verified from DBA_AUTOTASK_CLIENT in the target database. Do not hardcode client names from another environment if the dictionary returns different names.

### 3.2. Automatic Optimizer Statistics Collection

Optimizer statistics describe tables, columns, indexes, and data distributions. When statistics are stale or missing, the optimizer may misestimate cardinalities and choose suboptimal execution plans.

Automatic Optimizer Statistics Collection can:
- Identify objects needing statistics collection or refresh.
- Gather table/index/column statistics according to Oracle policies.
- Consume resources during maintenance windows.
- Introduce statistics updates that can affect SQL execution plans.

Operational impact:
- Consumes CPU and I/O while running.
- Fresh statistics may invalidate/reoptimize certain cursors.
- Execution plans may change after statistics are refreshed.
- Objects with locked statistics or custom preferences are handled according to those settings.

Do not disable auto stats simply because a single plan changed. Identify the affected objects, statistics, and SQL, and compare plans/runtimes before deciding.

### 3.3. Automatic Segment Advisor

Segment Advisor analyzes segment space usage and recommends space reclamation opportunities. It is useful when:
- Tables/indexes have large free space pockets from deletes/updates.
- Segments grow rapidly.
- DBAs need to evaluate shrink or reorganization candidates.
- Planning tablespace capacity management.

Advisor recommendations do not mean Oracle automatically shrinks every segment. The DBA must evaluate segment type, row movement, index dependencies, locks, downtime, and suitability before performing reclamation.

### 3.4. Automatic SQL Tuning Advisor

SQL Tuning Advisor analyzes selected SQL statements and can produce recommendations such as statistics, access paths, SQL profiles, or query rewrites. Automation level and implementation depend on configuration, privileges, and version.

Automatic SQL Tuning/SQL Tuning Advisor features require the corresponding Oracle Diagnostics Pack/Tuning Pack licenses. Verify contractual licensing entitlement before enabling or using reports covered by those packs.

### 3.5. Auto Tasks Are Not All Jobs in the Database

Jobs created by DBAs or applications with DBMS_SCHEDULER do not automatically become Automatic Maintenance Tasks. They have their own schedules, owners, credentials, job classes, and failure policies.

Therefore:
- DBA_AUTOTASK_CLIENT describes auto task clients.
- DBA_SCHEDULER_JOBS describes Scheduler jobs.
- DBA_SCHEDULER_JOB_RUN_DETAILS records Scheduler job execution history.
- DBA_AUTOTASK_JOB_HISTORY provides job history belonging to automatic tasks when data exists.

Use the right view for the type of job under investigation.

## 4. Checking Auto Task Status

### 4.1. Listing Clients

~~~sql
SELECT client_name,
       status,
       resource_consumer_group,
       window_group
FROM   dba_autotask_client
ORDER  BY client_name;
~~~

STATUS typically shows whether the client is ENABLED or DISABLED. RESOURCE_CONSUMER_GROUP and WINDOW_GROUP show the resource group/schedule attached to the client per metadata.

If a client is not running, check client status, window group, window schedule, resource plan, and job history.

### 4.2. Viewing Clients by Window

~~~sql
SELECT window_name,
       window_next_time,
       window_start_time,
       window_duration,
       window_active,
       optimizer_stats,
       segment_advisor,
       sql_tune_advisor
FROM   dba_autotask_window_clients
ORDER  BY window_name;
~~~

This view is useful to see which auto task clients are enabled or disabled in each window. It shows upcoming windows and which tasks are permitted to run.

### 4.3. Viewing Auto Task History

~~~sql
SELECT client_name,
       job_name,
       job_start_time,
       job_duration,
       job_status,
       job_error,
       job_info
FROM   dba_autotask_job_history
ORDER  BY job_start_time DESC
FETCH FIRST 100 ROWS ONLY;
~~~

History helps determine whether a task:
- Ran or did not run.
- Started at what time.
- Ran for how long.
- Succeeded, failed, or was stopped.
- Logged any additional info.

Columns may vary by release. If a query does not match your environment's dictionary, run DESC DBA_AUTOTASK_JOB_HISTORY to inspect the view schema.

### 4.4. Viewing Currently Running Scheduler Jobs

~~~sql
SELECT owner,
       job_name,
       job_subname,
       session_id,
       running_instance,
       elapsed_time,
       cpu_used
FROM   dba_scheduler_running_jobs
ORDER  BY elapsed_time DESC;
~~~

This is a point-in-time snapshot of running Scheduler jobs. Not all auto tasks appear under an immediately obvious name; correlate with client/job history and sessions when needed.

### 4.5. Viewing Scheduler Job History

~~~sql
SELECT log_date,
       owner,
       job_name,
       status,
       error#,
       actual_start_date,
       run_duration,
       additional_info
FROM   dba_scheduler_job_run_details
WHERE  log_date >= SYSTIMESTAMP - INTERVAL '7' DAY
ORDER  BY log_date DESC;
~~~

This view includes Scheduler job history within the Scheduler log retention window. Use JOB_NAME, OWNER, and timestamps to match the target job; do not assume all auto tasks follow the same naming pattern.

## 5. Relationship Between Maintenance Windows and Resource Manager

### 5.1. Window Resource Plans

A Scheduler window can have a Resource Manager plan attached. When the window opens, Oracle can activate the specified plan to govern resource allocation for workloads during that period.

Default maintenance windows commonly attach DEFAULT_MAINTENANCE_PLAN. This plan is designed to balance resources between maintenance consumer groups and other workloads per Oracle design.

### 5.2. Viewing a Window's Resource Plan

~~~sql
SELECT window_name,
       resource_plan,
       active,
       enabled,
       duration,
       repeat_interval
FROM   dba_scheduler_windows
ORDER  BY window_name;
~~~

Check the currently active plan:

~~~sql
SELECT name,
       is_top_plan
FROM   v$rsrc_plan;
~~~

If no rows return, either no Resource Manager plan is active or the account lacks visibility privileges. Correlate with window open times and instance configuration.

### 5.3. Why Does a Maintenance Plan Matter?

During maintenance windows, optimizer stats jobs or Segment Advisor can consume CPU/I/O. Resource Manager caps/allocates resources by consumer group, reducing the risk of maintenance tasks starving application workloads.

However, a resource plan does not replace capacity planning. If CPU/I/O is already saturated, a maintenance plan cannot manufacture extra physical hardware capacity.

### 5.4. Do Not Change Resource Plans Without Understanding Consumer Groups

Before changing DEFAULT_MAINTENANCE_PLAN or assigning a custom plan:
- Review plan directives and consumer groups.
- Identify which consumer group auto task users/sessions map to.
- Check CPU utilization and active session pools.
- Evaluate relative priorities between OLTP and maintenance.
- Test in an equivalent environment.
- Prepare a rollback plan.

A misconfigured resource plan can prevent tasks from finishing or degrade application responsiveness.

## 6. Checking Schedules, Timezones, and Window Opening Times

### 6.1. Repeat Intervals

Scheduler uses calendaring syntax for recurrence schedules. Example:

~~~text
freq=weekly;byday=SAT;byhour=1;byminute=0;bysecond=0
~~~

This means a weekly schedule every Saturday at 01:00. Actual execution times also depend on the schedule's start_date and timezone.

### 6.2. Checking Current Time and Timezones

~~~sql
SELECT SYSTIMESTAMP AS database_host_timestamp,
       CURRENT_TIMESTAMP AS session_timestamp,
       DBTIMEZONE AS database_timezone,
       SESSIONTIMEZONE AS session_timezone
FROM   dual;
~~~

SYSTIMESTAMP reflects the host/database system time with timezone offset. CURRENT_TIMESTAMP uses the session timezone. DBTIMEZONE and SESSIONTIMEZONE serve distinct purposes; never assume they match.

### 6.3. Scheduler Timezones

Scheduler stores scheduled times and repeat intervals in the timezone context of the schedule/start date. For long-term scheduling:
- Prefer named timezone regions such as Asia/Ho_Chi_Minh or the appropriate operational region when adhering to local wall-clock time.
- Avoid assuming a fixed offset stays accurate in regions observing daylight saving time.
- Check NEXT_START_DATE after changing repeat intervals.
- Verify schedules across DST transition dates if hosted in a DST region.
- Synchronize clocks across database hosts, application hosts, and monitoring systems.

If a schedule must follow UTC, define and document UTC explicitly in the change record.

### 6.4. Checking Next Scheduled Runs

~~~sql
SELECT window_name,
       repeat_interval,
       duration,
       next_start_date,
       last_start_date,
       enabled,
       active
FROM   dba_scheduler_windows
ORDER  BY next_start_date NULLS LAST;
~~~

After modifying a schedule, inspect NEXT_START_DATE and confirm it falls inside the operations-approved maintenance window.

### 6.5. Overlapping Windows

Multiple windows can be scheduled close together or overlap. Scheduler uses window priority and window rules to determine the active window. Check PRIORITY, repeat intervals, durations, and window logs to understand conflict resolution.

Do not create new windows with long durations without inspecting existing schedules. Overlaps can cause one window to be superseded/closed by Scheduler rules or shift resource plans unexpectedly.

## 7. Adjusting Default Maintenance Schedules

### 7.1. Changing the Repeat Interval

Example shifting MONDAY_WINDOW to start at 01:00 on Mondays:

~~~sql
BEGIN
    DBMS_SCHEDULER.SET_ATTRIBUTE(
        name      => 'MONDAY_WINDOW',
        attribute => 'REPEAT_INTERVAL',
        value     => 'freq=daily;byday=MON;byhour=1;byminute=0;bysecond=0'
    );
END;
/
~~~

This alters the schedule of an existing window. Confirm the window name, privileges, and new timing with operations before running.

### 7.2. Changing the Duration

Example setting duration to three hours:

~~~sql
BEGIN
    DBMS_SCHEDULER.SET_ATTRIBUTE(
        name      => 'MONDAY_WINDOW',
        attribute => 'DURATION',
        value     => NUMTODSINTERVAL(3, 'HOUR')
    );
END;
/
~~~

Duration is how long the window stays open per scheduled run. If shorter than needed, auto tasks may not finish inside the window. If too long, maintenance may contend with business-hour workloads.

### 7.3. Verifying After Changes

~~~sql
SELECT window_name,
       repeat_interval,
       duration,
       next_start_date,
       resource_plan,
       enabled
FROM   dba_scheduler_windows
WHERE  window_name = 'MONDAY_WINDOW';
~~~

After changing attributes, verify repeat interval, duration, next start date, and resource plan. Record before/after values in the change ticket.

### 7.4. Disabling and Enabling a Window

Temporarily disabling a window:

~~~sql
BEGIN
    DBMS_SCHEDULER.DISABLE('MONDAY_WINDOW');
END;
/
~~~

Re-enabling:

~~~sql
BEGIN
    DBMS_SCHEDULER.ENABLE('MONDAY_WINDOW');
END;
/
~~~

DISABLE prevents Scheduler from opening the window on future scheduled runs once effective. It does not automatically cancel every job already running inside the window. Check running jobs and job logs before assuming work has stopped.

### 7.5. Do Not Modify System Schedules Arbitrarily

Default windows are part of the database's administrative configuration. Before changing them:
- Back up current repeat interval, duration, resource plan, and group membership.
- Identify which auto tasks depend on the window.
- Review backup, batch, ETL, and application schedules.
- Evaluate PDB/CDB scope in multitenant setups.
- Execute within an approved change window.
- Verify next scheduled runs and history afterward.
- Prepare rollback commands to restore original values.

## 8. Creating Custom Maintenance Windows

### 8.1. When Should You Create a Custom Window?

Create a custom window when:
- Default schedules do not align with low-traffic hours.
- You need a dedicated maintenance slot for a specific group of jobs.
- A different resource plan or duration is required.
- You want to isolate maintenance tasks from an existing operational schedule.

First decide whether the custom window is only for DBA-managed jobs or also for automatic maintenance tasks. If auto tasks should run inside the new window, configure membership in MAINTENANCE_WINDOW_GROUP and check client/window status.

### 8.2. Creating a Window

Example creating a Saturday window at 01:00 lasting four hours:

~~~sql
BEGIN
    DBMS_SCHEDULER.CREATE_WINDOW(
        window_name     => 'SATURDAY_CUSTOM_WINDOW',
        resource_plan   => 'DEFAULT_MAINTENANCE_PLAN',
        start_date      => SYSTIMESTAMP,
        repeat_interval => 'freq=weekly;byday=SAT;byhour=1;byminute=0;bysecond=0',
        duration        => NUMTODSINTERVAL(4, 'HOUR'),
        window_priority => 'HIGH',
        comments        => 'Custom maintenance window for approved tasks'
    );
END;
/
~~~

Adjust this example for timezone, backup windows, and maintenance policy. DEFAULT_MAINTENANCE_PLAN must exist and be appropriately configured in the database.

### 8.3. Adding a Window to the Maintenance Group

If you want automatic maintenance tasks to treat the custom window as a member of the maintenance window group:

~~~sql
BEGIN
    DBMS_SCHEDULER.ADD_GROUP_MEMBER(
        group_name => 'MAINTENANCE_WINDOW_GROUP',
        member     => 'SATURDAY_CUSTOM_WINDOW'
    );
END;
/
~~~

This changes the schedule available to auto tasks. Do not add the custom window to the group if you only intend to run a standalone DBA job.

Before adding, inspect existing membership to avoid duplicates or extending maintenance windows beyond intended limits.

### 8.4. Enabling and Verifying the Window

~~~sql
BEGIN
    DBMS_SCHEDULER.ENABLE('SATURDAY_CUSTOM_WINDOW');
END;
/
~~~

Verify:

~~~sql
SELECT window_name,
       resource_plan,
       duration,
       repeat_interval,
       enabled,
       active,
       next_start_date
FROM   dba_scheduler_windows
WHERE  window_name = 'SATURDAY_CUSTOM_WINDOW';
~~~

### 8.5. Removing a Window When No Longer Used

If the window belongs to a group, remove its membership first:

~~~sql
BEGIN
    DBMS_SCHEDULER.REMOVE_GROUP_MEMBER(
        group_name => 'MAINTENANCE_WINDOW_GROUP',
        member     => 'SATURDAY_CUSTOM_WINDOW'
    );
END;
/
~~~

Then disable/drop the window per procedure:

~~~sql
BEGIN
    DBMS_SCHEDULER.DISABLE('SATURDAY_CUSTOM_WINDOW');
    DBMS_SCHEDULER.DROP_WINDOW(
        window_name => 'SATURDAY_CUSTOM_WINDOW',
        force       => TRUE
    );
END;
/
~~~

Use DROP_WINDOW force cautiously. Check whether the window is currently active or referenced by other jobs/groups before dropping.

## 9. Enabling and Disabling Individual Automatic Maintenance Tasks

### 9.1. Disabling a Client Across All Windows

Example temporarily disabling Automatic Segment Advisor:

~~~sql
BEGIN
    DBMS_AUTO_TASK_ADMIN.DISABLE(
        client_name => 'auto space advisor',
        operation   => NULL,
        window_name => NULL
    );
END;
/
~~~

Example disabling automatic optimizer stats collection:

~~~sql
BEGIN
    DBMS_AUTO_TASK_ADMIN.DISABLE(
        client_name => 'auto optimizer stats collection',
        operation   => NULL,
        window_name => NULL
    );
END;
/
~~~

Client names must be taken from DBA_AUTOTASK_CLIENT. Disabling a client affects every maintenance window within the specified scope; assess consequences beforehand.

### 9.2. Disabling a Client in a Specific Window

To disable a client in just one window:

~~~sql
BEGIN
    DBMS_AUTO_TASK_ADMIN.DISABLE(
        client_name => 'auto optimizer stats collection',
        operation   => NULL,
        window_name => 'MONDAY_WINDOW'
    );
END;
/
~~~

This preserves auto stats in all other windows. Check DBA_AUTOTASK_WINDOW_CLIENTS after making the change.

### 9.3. Re-Enabling a Client

~~~sql
BEGIN
    DBMS_AUTO_TASK_ADMIN.ENABLE(
        client_name => 'auto optimizer stats collection',
        operation   => NULL,
        window_name => NULL
    );
END;
/
~~~

If the client was only disabled for a single window, pass that exact window_name to restore the matching scope. Do not enable the entire client across all windows when policy expects only a single-window restore.

### 9.4. Disabling an Auto Task vs. Disabling a Scheduler Window

| Action | Effect |
| --- | --- |
| DBMS_AUTO_TASK_ADMIN.DISABLE | Prevents the specified auto task client from running within the targeted scope |
| DBMS_SCHEDULER.DISABLE(window) | Prevents Scheduler from opening the window on schedule |
| DBMS_SCHEDULER.CLOSE_WINDOW | Closes a currently active window |
| DBMS_SCHEDULER.STOP_JOB | Requests stopping a specific Scheduler job |

Do not substitute these operations for one another. Disabling a window can affect every job tied to that window; disabling one client still lets other clients run.

### 9.5. Do Not Leave Auto Stats Disabled Indefinitely

If you must temporarily disable Automatic Optimizer Statistics Collection during an incident:
- Record the reason and start time.
- Identify tables/objects requiring statistics.
- Schedule manual gathering or a target re-enable time.
- Monitor for stale statistics and plan regressions.
- Assign an owner and restoration deadline.

Prolonged stale statistics can cause the optimizer to select poor execution plans as data evolves.

## 10. Manually Opening and Closing Windows

### 10.1. OPEN_WINDOW

Scheduler supports opening a window on demand:

~~~sql
BEGIN
    DBMS_SCHEDULER.OPEN_WINDOW(
        window_name => 'SATURDAY_CUSTOM_WINDOW',
        duration    => NUMTODSINTERVAL(2, 'HOUR'),
        force       => TRUE
    );
END;
/
~~~

OPEN_WINDOW can be used for an approved operational situation, but should not be used to trigger auto tasks casually. Check the window, resource plan, overlapping schedules, and dependent jobs before opening.

### 10.2. CLOSE_WINDOW

~~~sql
BEGIN
    DBMS_SCHEDULER.CLOSE_WINDOW('SATURDAY_CUSTOM_WINDOW');
END;
/
~~~

CLOSE_WINDOW closes a currently open window. Closing a window does not necessarily kill every job already started; job behavior depends on Scheduler attributes and task type. Check DBA_SCHEDULER_RUNNING_JOBS and history afterward.

### 10.3. OPEN_WINDOW Does Not Replace Downtime

When database or OS patching is needed:
- Stop/drain application services per runbook.
- Verify transactions and active sessions.
- Verify backup/recovery readiness.
- Apply patches per Oracle procedures.
- Validate database/services post-maintenance.
- Reopen traffic once acceptance criteria pass.

Opening a Scheduler window only governs schedules/resource plans; it does not establish application downtime.

## 11. Monitoring Window History

### 11.1. Window Log

~~~sql
SELECT log_date,
       window_name,
       operation,
       status,
       actual_start_date,
       actual_duration
FROM   dba_scheduler_window_log
ORDER  BY log_date DESC
FETCH FIRST 100 ROWS ONLY;
~~~

The window log shows when windows opened/closed, actual start times, and operation statuses. If a window did not run as expected, inspect:
- ENABLED and ACTIVE.
- REPEAT_INTERVAL.
- NEXT_START_DATE.
- Window group membership.
- Scheduler logs.
- Resource plans.
- Other overlapping windows.

### 11.2. Finding Failed Auto Tasks

~~~sql
SELECT client_name,
       job_name,
       job_start_time,
       job_duration,
       job_status,
       job_error,
       job_info
FROM   dba_autotask_job_history
WHERE  job_status <> 'SUCCEEDED'
ORDER  BY job_start_time DESC;
~~~

If the view records multiple statuses or differing status values, inspect actual rows and filter appropriately. Task failures may result from resource limits, object locks, space issues, privileges, or interruption when a window closed.

### 11.3. Checking Failed Scheduler Jobs

~~~sql
SELECT log_date,
       owner,
       job_name,
       status,
       error#,
       actual_start_date,
       run_duration,
       additional_info
FROM   dba_scheduler_job_run_details
WHERE  status <> 'SUCCEEDED'
ORDER  BY log_date DESC;
~~~

When a job fails, examine ERROR#, ADDITIONAL_INFO, and job_action. Do not simply re-enable a failing job repeatedly without diagnosing the root error.

### 11.4. Monitoring Auto Task Sessions

~~~sql
SELECT sid,
       serial#,
       username,
       module,
       action,
       client_identifier,
       sql_id,
       event,
       wait_class,
       status
FROM   v$session
WHERE  status = 'ACTIVE'
ORDER  BY username, module, action;
~~~

Module/action values help identify the job or component. Actual values depend on version and task; correlate with SQL_ID, job metadata, and session program.

## 12. Controlling Conflicts with Other Workloads

### 12.1. Maintenance and Batch Windows

If ETL, backups, index maintenance, and auto stats run in the same window, they may contend for:
- CPU.
- Datafile I/O.
- Redo log I/O.
- TEMP.
- PGA.
- Undo.
- Network or storage bandwidth.

Schedule by dependency rather than simply picking an hour when fewer users are logged in.

### 12.2. Time-Mapped Task Schedule

Illustrative schedule:

| Time | Task | Resources to Watch |
| --- | --- | --- |
| 00:00–01:00 | Incremental backup | Datafile reads, storage/network |
| 01:00–02:00 | Auto optimizer stats | CPU, I/O, cursor invalidation |
| 02:00–03:00 | ETL batch | CPU, redo, undo, TEMP |
| 03:00–04:00 | Approved segment review/reclaim | I/O, locks, space |
| 04:00–05:00 | Validation and backup verification | I/O, CPU |

This is an example only. Real schedules must reflect measured durations, dependencies, and capacity.

### 12.3. Backups and Auto Stats

Full/incremental backups read many data blocks. Auto stats also reads tables/indexes. Running both concurrently can elevate I/O and slow both down.

Separate schedules or enforce resource plan limits if contention is measured. Do not disable auto stats long term solely to speed up backups without an alternative plan.

### 12.4. Batch DML and Undo/Redo

Large batch DML generates heavy redo/undo. Running concurrently with backups, archiving, or other heavy tasks can cause:
- log file sync/log file parallel write pressure.
- Archive destination pressure.
- Undo tablespace pressure.
- TEMP spills from sorts/hashes.
- Rising storage queues.

Schedule batches according to capacity and break transactions into reasonable chunks.

### 12.5. Index Rebuilds and Schema Changes

Index rebuilds can consume CPU, I/O, TEMP, and extra space. Some operations acquire locks or impact DML depending on options and edition/licensing.

Before placing them into a maintenance window, calculate:
- Segment size and free space.
- Online/offline requirements.
- Lock impact.
- Redo/undo generation.
- Backup and rollback plans.
- Actual runtime on representative data.

## 13. Maintenance Windows in CDB/PDB

### 13.1. Identifying the Container

~~~sql
SELECT sys_context('USERENV', 'CON_NAME') AS con_name,
       sys_context('USERENV', 'CON_ID') AS con_id
FROM   dual;
~~~

In a multitenant database, confirm whether you are operating in the CDB root or a PDB. Auto tasks and Scheduler objects have container-specific administrative scopes and configuration.

### 13.2. Do Not Assume One Window Affects Every PDB Identically

Some tasks are managed at the CDB level while objects/tasks belong to individual PDBs. When changing schedules:
- Verify common vs. local administration policies.
- Confirm the current container.
- Check whether individual PDBs have distinct maintenance workloads.
- Evaluate resource plans at both CDB and PDB levels.
- Check status and history inside the right container.

### 13.3. CDB Views

DBAs can use CDB-level views to aggregate Scheduler/auto task metadata across containers when appropriately privileged. Include CON_ID in reports to distinguish PDBs that share identical job or user names.

Never execute modification statements in the root assuming they affect only one PDB. Always verify CON_NAME before acting.

## 14. Managing Custom Operational Jobs

### 14.1. Creating a Scheduler Job

Example creating a job running a data-validation procedure every Sunday at 02:00:

~~~sql
BEGIN
    DBMS_SCHEDULER.CREATE_JOB(
        job_name        => 'OPS_WEEKLY_VALIDATION',
        job_type        => 'STORED_PROCEDURE',
        job_action      => 'OPS_VALIDATE_DATA',
        start_date      => SYSTIMESTAMP,
        repeat_interval => 'freq=weekly;byday=SUN;byhour=2;byminute=0;bysecond=0',
        enabled         => FALSE,
        auto_drop       => FALSE,
        comments        => 'Weekly validation during approved maintenance period'
    );
END;
/
~~~

The job is created disabled so the DBA can inspect action, owner, privileges, and schedule before enabling.

### 14.2. Enabling the Job

~~~sql
BEGIN
    DBMS_SCHEDULER.ENABLE('OPS_WEEKLY_VALIDATION');
END;
/
~~~

Verify:

~~~sql
SELECT owner,
       job_name,
       job_type,
       job_action,
       repeat_interval,
       enabled,
       state,
       next_run_date
FROM   dba_scheduler_jobs
WHERE  job_name = 'OPS_WEEKLY_VALIDATION';
~~~

### 14.3. Assigning Jobs to Job Classes

Job classes group jobs by resource consumer group and logging policy. DBAs can create tailored job classes to isolate batch/maintenance workloads. Resource Manager plans and job classes must be designed together; never assign a job to a nonexistent consumer group.

### 14.4. Scheduling Jobs Dependent on a Window

Scheduler jobs can be scheduled against a window or window group using an appropriate schedule. Using a window or window group restricts the job to run only during permitted periods. Verify release-specific CREATE_JOB/CREATE_SCHEDULE syntax and ensure the window group is enabled.

A job with a pure time-based schedule is not automatically constrained to a maintenance window. If it must depend on a window, declare that dependency explicitly.

### 14.5. Retry and Failure Handling

For critical jobs:
- Define appropriate retry/event-raising rules.
- Record application-level logs and outcomes.
- Ensure actions are idempotent when retries are enabled.
- Prevent retries from creating duplicate data.
- Alert owners when a job fails.
- Define skip cutoffs so delayed jobs do not spill into production hours.

## 15. Maintenance Window Design Process

### 15.1. Gathering Requirements

Document:
- Affected services/databases/PDBs.
- Tasks to execute.
- Frequency.
- Average and p95 durations.
- CPU, I/O, TEMP, undo, and redo profiles.
- Dependencies with backups, ETL, and applications.
- Whether downtime is required.
- Maximum permitted duration.
- Approvers and operators.

### 15.2. Choosing Timing

Select timing based on:
- Actual workload troughs.
- Batch and backup schedules.
- User and data center timezones.
- SLAs and RPO/RTO.
- Schedules of other PDBs/services.
- Buffer for validation/rollback.

Do not pick a slot merely assuming "midnight has few users"; batches, backups, and ETL often concentrate right there.

### 15.3. Sizing Duration with a Buffer

If a job normally runs 90 minutes, do not set an exact 90-minute window. Include buffer for:
- Data volume growth/variance.
- Slow I/O.
- Retries.
- Validation.
- Cleanup.
- Rollback.

Too short a duration prevents completion; too long a duration risks encroaching on production hours. Size from runtime percentiles rather than a single best-case run.

### 15.4. Controlling Concurrency

Determine concurrent job limits and total resource budget. Run jobs sequentially when they contend for the same I/O or TEMP resources. Resource Manager enforces caps, while sequential scheduling still helps avoid overlapping peaks.

### 15.5. Defining Success Criteria

Every task should define:
- Entry criteria.
- Expected duration.
- Expected outcome.
- Post-run checks.
- Stop conditions.
- Rollback/compensation steps.
- Alert recipients.

Do not mark maintenance complete solely because Scheduler job status says SUCCEEDED; validate business state and database health.

## 16. Pre-, During-, and Post-Maintenance Runbook

### Before the Window

1. Confirm change ticket, owner, and approvers.
2. Confirm exact database, CDB/PDB, service, and host.
3. Inspect Scheduler windows, group memberships, and auto task clients.
4. Confirm backups completed and restore capability meets requirements.
5. Check tablespace, TEMP, undo, archive destination, and filesystem space.
6. Confirm no conflicting jobs/batches.
7. Check resource plans and concurrency settings.
8. Record baseline DB time, CPU, I/O, redo, undo, and TEMP.
9. Prepare scripts, rollback commands, and validation queries.
10. Notify application owners if connection draining or downtime is needed.

### During the Window

1. Confirm the expected window opened or the job is authorized to start.
2. Check active sessions/transactions and service state.
3. Monitor running jobs, SQL_IDs, wait events, and resource usage.
4. Inspect the alert log, Scheduler job logs, and application logs.
5. Record actual start/end times and applied changes.
6. Stop/defer work if thresholds are breached or SLAs are threatened.
7. Do not run unapproved extra tasks outside scope.

### After the Window

1. Confirm jobs finished and no unexpected sessions/jobs remain.
2. Verify database open mode, services, listeners, and PDBs.
3. Verify backups/archives/standby status within change scope.
4. Check for invalid objects, job failures, and alert log errors.
5. Verify auto tasks/windows were re-enabled if temporarily changed.
6. Re-measure DB time, CPU, I/O, redo, undo, and TEMP.
7. Confirm application smoke tests and latency.
8. Document results, incidents, actual duration, and follow-ups.

## 17. Change Control and Rollback

### 17.1. Export Configuration Before Changes

Before modifying a window, export current metadata from:
- DBA_SCHEDULER_WINDOWS.
- DBA_SCHEDULER_WINGROUP_MEMBERS.
- DBA_AUTOTASK_CLIENT.
- DBA_AUTOTASK_WINDOW_CLIENTS.
- Related resource plans and job classes.

Save query outputs in the change record so exact baseline values are preserved.

### 17.2. Rolling Back Window Schedules

If repeat interval or duration was altered, roll back using the saved prior values. Do not reset to "default" from memory; the database may already have been customized earlier.

### 17.3. Rolling Back Auto Task Status

If a client was temporarily disabled, record:
- Client name.
- Window scope.
- Time disabled.
- Operator.
- Planned re-enable time.

After maintenance, run ENABLE with the matching scope and verify DBA_AUTOTASK_CLIENT/DBA_AUTOTASK_WINDOW_CLIENTS.

### 17.4. Jobs Exceeding Duration

If a job overruns its window:
- Check whether the job is still running or already stopped.
- Inspect DBA_SCHEDULER_RUNNING_JOBS and job run details.
- Check STOP_ON_WINDOW_CLOSE and relevant job attributes.
- Assess whether the job can finish safely past the window or must be stopped.
- Evaluate transaction/rollback impact before stopping.
- Never kill a session solely because the wall clock passed the maintenance window.

### 17.5. Rolling Back Database Changes

For patching, schema changes, or data migrations, rollback may require restore, flashback, reverse scripts, or failback. A maintenance window is only a time schedule; it does not provide rollback automatically. Design the rollback mechanism per change type before starting.

## 18. Common Errors and Misconceptions

**"A maintenance window means database downtime."** No. A Scheduler window does not close the database or block application connections.

**"An open window means every auto task will run."** No. Client, window, group, resource, and task eligibility conditions all determine execution.

**"DBMS_AUTO_TASK_ADMIN.DISABLE turns off all of Scheduler."** No. It only controls the specified auto task client within the given scope.

**"DBMS_SCHEDULER.DISABLE(window) stops all running jobs."** Do not assume that. Check running jobs and job attributes.

**"Auto stats runs at the exact same fixed time on every database."** No. Window schedules may have been customized; check DBA_SCHEDULER_WINDOWS.

**"Segment Advisor automatically shrinks every segment."** No. The advisor generates recommendations; the DBA evaluates and performs appropriate actions.

**"SQL Tuning Advisor is always enabled and license-free."** No. Configuration status and licensing entitlements must be verified.

**"Increasing duration guarantees job completion."** No. Completion also depends on workload, resource plans, errors, and data conditions.

**"Adding a custom window automatically routes auto tasks into that schedule."** No. Verify MAINTENANCE_WINDOW_GROUP membership and client status.

**"A Scheduler window replaces the organization's maintenance change window."** No. Application draining, downtime, backups, patching, and approvals still require separate processes.

**"Disabling auto stats for a few days has no impact."** It can affect cardinality estimates and execution plans as data changes; maintain an alternative plan and re-enable target.

**"Seeing no jobs in a window means Scheduler is broken."** Not necessarily. Clients may be disabled, tasks may have no work needed, jobs may not be eligible, or window/resource policies may defer execution.

## 19. Practice Exercises

Run exercises only in a test database or an environment authorized by the DBA. Do not alter default production maintenance schedules just to practice.

### Exercise 1 — Explore Windows

Query DBA_SCHEDULER_WINDOWS. Record repeat interval, duration, resource plan, enabled state, and next start date.

### Exercise 2 — Explore Window Groups

Query DBA_SCHEDULER_WINDOW_GROUPS and DBA_SCHEDULER_WINGROUP_MEMBERS. Diagram the relationships among MAINTENANCE_WINDOW_GROUP, WEEKNIGHT_WINDOW, and WEEKEND_WINDOW.

### Exercise 3 — Verify Timezones

Compare SYSTIMESTAMP, CURRENT_TIMESTAMP, DBTIMEZONE, SESSIONTIMEZONE, and NEXT_START_DATE. Explain how timezones affect scheduling.

### Exercise 4 — Inspect Auto Task Clients

Query DBA_AUTOTASK_CLIENT and classify enabled/disabled clients. Record each client's window group.

### Exercise 5 — Inspect Tasks per Window

Use DBA_AUTOTASK_WINDOW_CLIENTS to see which windows have optimizer stats, Segment Advisor, and SQL Tuning Advisor enabled.

### Exercise 6 — Review Auto Task History

Query DBA_AUTOTASK_JOB_HISTORY. Identify long-running or failed tasks and correlate timestamps with the window log.

### Exercise 7 — Observe Resource Manager

While a window is active in a test environment, query DBA_SCHEDULER_WINDOWS and V$RSRC_PLAN. Identify which resource plan is active.

### Exercise 8 — Create a Custom Window

Create a test window at an approved time, verifying next_start_date and duration. Do not add it to MAINTENANCE_WINDOW_GROUP if your goal is only to run an isolated test job.

### Exercise 9 — Change Duration

Change the custom window duration from four hours to two hours. Re-read metadata and restore the original value.

### Exercise 10 — Toggle an Auto Task in Test

Disable one client in a single test window, query DBA_AUTOTASK_WINDOW_CLIENTS, and then re-enable it. Note the difference between client status and window status.

### Exercise 11 — Scheduled Operational Job

Create a disabled test Scheduler job, verify action/owner/repeat interval, then enable it and inspect job run details.

### Exercise 12 — Workload Contention

Run two test jobs with differing I/O or CPU profiles in the same window. Observe elapsed time, CPU, I/O, and the effect of separating their schedules.

### Exercise 13 — Inspect Window Logs

Check DBA_SCHEDULER_WINDOW_LOG before and after opening/closing a test window. Compare scheduled times with actual times.

### Exercise 14 — Write a Runbook

Design a maintenance window for a schema update. Document schedule, backups, dependencies, resource budget, downtime, validation, rollback, and owners.

## 20. Oracle Reference Documentation

- [Oracle Database Administrator's Guide 19c — Managing Automatic Maintenance Tasks](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-automatic-maintenance-tasks.html): automatic maintenance tasks and administration.
- [Oracle Database Administrator's Guide 19c — Managing Scheduler Windows](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/scheduling-jobs-with-oracle-scheduler.html): windows, schedules, jobs, and Scheduler administration.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_AUTO_TASK_ADMIN](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_AUTO_TASK_ADMIN.html): enabling/disabling automatic maintenance task clients.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_SCHEDULER](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_SCHEDULER.html): creating/altering/enabling/disabling/opening/closing Scheduler windows and jobs.
- [Oracle Database Reference — DBA_SCHEDULER_WINDOWS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_SCHEDULER_WINDOWS.html): Scheduler window metadata.
- [Oracle Database Reference — DBA_AUTOTASK_CLIENT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_AUTOTASK_CLIENT.html): automatic maintenance client status.
- [Oracle Database Reference — DBA_AUTOTASK_WINDOW_CLIENTS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_AUTOTASK_WINDOW_CLIENTS.html): client status per maintenance window.
- [Oracle Database Reference — DBA_AUTOTASK_JOB_HISTORY](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_AUTOTASK_JOB_HISTORY.html): automatic maintenance task job history.
- [Oracle Database Administrator's Guide — Managing Resource Manager](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-resources-with-oracle-database-resource-manager.html): resource plans and resource governance.
- [Oracle Database Licensing Information User Manual 19c](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/): licensing requirements for management and tuning features.

Maintenance windows determine when Scheduler allows scheduled maintenance tasks to run; Automatic Maintenance Tasks use windows to run statistics collection, Segment Advisor, and SQL Tuning Advisor according to their state and configuration. DBAs must inspect windows, group membership, client status, resource plans, timezones, and job history before making adjustments. For system maintenance, Scheduler is only one piece of the plan: backups, application coordination, downtime, validation, and rollback must still be managed separately. **Good maintenance scheduling means choosing the right time, bounding the right resources, observing outcomes, and restoring configurations in a controlled way.**
