# Collecting the alert log, trace, SQL_ID, and context before remediation

When Oracle Database raises an error, the first step is to preserve enough evidence to reproduce the issue and determine its scope. A single `ORA-` error message is usually not enough to identify the root cause. You need to correlate the time of the error with the alert log, trace files, `SQL_ID`, session, service, PDB, instance, host, and the application operation being performed.

Collecting diagnostic data before changing the database state helps prevent losing evidence. Actions such as restarting an instance, killing a session, flushing the shared pool, changing parameters, recompiling packages, or re-running transactions can alter or destroy evidence. Therefore, record the context and save logs before starting remediation, except when emergency action is required to protect data or restore service.

## 1. Collection goals and principles

A good incident evidence package should help answer:

- When did the error occur, in what timezone, and how long did it last?
- Which database, instance, host, container/PDB, and service are involved?
- Which user, application, module, action, and client executed the operation?
- Which SQL statement, SQL_ID, and child cursor was the session running?
- Were there accompanying blocking sessions, wait events, I/O errors, memory errors, or OS-level incidents?
- Which alert log and trace files contain the corresponding information?
- Is the error reproducible, and do the reproduction steps modify data?

You should follow these principles:

1. Record timestamps with timezone and synchronize with the clocks of the application, database server, and operating system.
2. Record environment identifiers before running queries: database, instance, PDB, service, and host.
3. Capture logs, SQL_ID, session details, and wait states before terminating a session or restarting.
4. Store SQL text, bind variables, and sensitive data in accordance with security policies.
5. Keep the original alert log and trace files intact; analyze copies instead.
6. Document who collected the data, where it was collected, start/end timestamps, and every change performed.
7. Enable tracing only with a clear scope and time limit; disable tracing as soon as sufficient data has been collected.

## 2. Identifying the right database, instance, and PDB

Before reading logs or looking up a SQL_ID, confirm that your connection session points to the correct environment. An error may be reported by an application through a service while the investigator connects to the CDB root or a different PDB.

### 2.1. Current session information

Run the following query in the exact application connection or administrative connection used to reproduce the error:

```sql
SELECT
  SYS_CONTEXT('USERENV', 'DB_NAME')          AS db_name,
  SYS_CONTEXT('USERENV', 'CON_NAME')          AS container_name,
  SYS_CONTEXT('USERENV', 'CON_ID')            AS con_id,
  SYS_CONTEXT('USERENV', 'SERVICE_NAME')      AS service_name,
  SYS_CONTEXT('USERENV', 'INSTANCE_NAME')     AS instance_name,
  SYS_CONTEXT('USERENV', 'SERVER_HOST')       AS server_host,
  SYS_CONTEXT('USERENV', 'SESSION_USER')      AS session_user,
  SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')    AS current_schema,
  SYS_CONTEXT('USERENV', 'MODULE')            AS module,
  SYS_CONTEXT('USERENV', 'ACTION')            AS action,
  SYS_CONTEXT('USERENV', 'CLIENT_IDENTIFIER') AS client_identifier
FROM dual;
```

`MODULE`, `ACTION`, and `CLIENT_IDENTIFIER` may be empty if the application does not instrument its sessions. Record empty values as well rather than guessing from the client program name.

### 2.2. Database and instance information

```sql
SELECT name, dbid, db_unique_name, database_role, open_mode
FROM v$database;

SELECT instance_name,
       host_name,
       version,
       startup_time,
       status,
       thread#
FROM v$instance;
```

In a RAC environment, querying `V$INSTANCE` reflects only the current instance. Use `GV$INSTANCE` to inspect all instances returned by the cluster view:

```sql
SELECT inst_id,
       instance_name,
       host_name,
       version,
       startup_time,
       status,
       thread#
FROM gv$instance
ORDER BY inst_id;
```

If investigating a specific PDB, save the PDB name and `CON_ID`. With appropriate privileges, you can list the containers:

```sql
SELECT con_id, name, open_mode
FROM v$containers
ORDER BY con_id;
```

Do not merge data from multiple instances into a single event. In RAC, the same SQL_ID can appear on multiple instances, whereas sessions and trace files belong to a specific instance. Always save `INST_ID` alongside `SID`, `SERIAL#`, and `CON_ID` when querying `GV$` views.

## 3. Locating the alert log and ADR

Oracle stores diagnostic information in the Automatic Diagnostic Repository (ADR). ADR is structured by product, database, and instance, and includes the alert log, trace files, incidents, and related diagnostic data.

### 3.1. Determining diagnostic paths using SQL

Query `V$DIAG_INFO` to locate ADR paths:

```sql
SELECT name, value
FROM v$diag_info
ORDER BY name;
```

Rows commonly of interest:

| Name | Content |
|---|---|
| `Diag Enabled` | Indicates whether ADR is enabled |
| `ADR Home` | ADR directory for the database/instance |
| `Diag Trace` | Directory containing text trace files |
| `Diag Alert` | Directory containing XML alert logs |
| `Default Trace File` | Default trace file of the current session |
| `Active Problem Count` | Number of active problems in ADR |
| `Active Incident Count` | Number of active incidents in ADR |

Row names and counts may vary by release or configuration. Use the actual values returned by the database instead of guessing paths such as `$ORACLE_BASE/diag/rdbms`.

### 3.2. Reading the alert log

The alert log records major instance events, such as startup/shutdown, internal errors, process errors, parameter/configuration changes, checkpoints, redo/archive errors, tablespace issues, and other operational messages.

You can read the alert log using ADRCI on the database host:

```text
adrci
show homes
set homepath diag/rdbms/<db_unique_name>/<instance_name>
show alert -tail 200
```

Replace the angle-bracketed parts with the actual ADR home. If you need to view older entries, use time-based filtering options or open the alert log file in the identified ADR directory. Do not assume the database directory name always matches `DB_NAME`; in Data Guard or multi-instance environments, use the ADR home shown on the host.

In releases that provide this view, you can query the alert log from SQL:

```sql
SELECT originating_timestamp,
       message_type,
       message_level,
       problem_key,
       message_text
FROM v$diag_alert_ext
WHERE originating_timestamp >=
      SYSTIMESTAMP - INTERVAL '2' HOUR
ORDER BY originating_timestamp;
```

This view helps filter events by time and content without reading the entire file. Choose a time window appropriate for the incident, then save lines before and after the error to preserve context. If querying across multiple days, mind result size and access privileges.

### 3.3. Reading the alert log by timeline

Do not capture only the exact line containing `ORA-`. Collect a window before and after the event:

- Before the error: did the database just start up, or were there parameter changes, archive destination changes, tablespace events, or sudden workload spikes?
- At the time of the error: which message appeared first, and is there an incident ID or process ID?
- After the error: did the instance remain running, did processes terminate, did recovery run, or did the error repeat?

Explicitly record the timezone and any time conversion applied. The alert log may store timestamps with timezone information, while traces and application logs may use different formats. When correlating, standardize on a single reference, typically UTC or the timezone defined by the operations team.

## 4. Finding trace files

Trace files contain technical details of processes/sessions, such as internal errors, stacks, waits, SQL trace data, and diagnostic dumps. A single event can generate multiple trace files: server process traces, background process traces, incident traces, or SQL trace files for an enabled session.

### 4.1. Trace file of the current session

In the session under investigation:

```sql
SELECT value AS default_trace_file
FROM v$diag_info
WHERE name = 'Default Trace File';
```

The result is the default trace file path for the current session on the database host. Client users do not necessarily have permission to read this file directly; ask a DBA or operations team member to retrieve the file from the server.

### 4.2. Finding the trace file of another session

Once you know `SID` and `SERIAL#`, you can look up the server process:

```sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.status,
       s.machine,
       s.program,
       s.module,
       s.action,
       s.client_identifier,
       s.sql_id,
       s.prev_sql_id,
       p.spid,
       p.tracefile
FROM v$session s
JOIN v$process p
  ON p.addr = s.paddr
WHERE s.sid = :sid
  AND s.serial# = :serial_no;
```

In RAC, specify the instance as well:

```sql
SELECT s.inst_id,
       s.sid,
       s.serial#,
       s.username,
       s.module,
       s.action,
       s.sql_id,
       s.prev_sql_id,
       p.spid,
       p.tracefile
FROM gv$session s
JOIN gv$process p
  ON p.inst_id = s.inst_id
 AND p.addr = s.paddr
WHERE s.inst_id = :inst_id
  AND s.sid = :sid
  AND s.serial# = :serial_no;
```

Availability of the `TRACEFILE` column and access privileges can depend on the release, privileges, and process type. If the query does not return a path, use `V$DIAG_INFO`, ADRCI, and the process ID so the DBA can locate the trace file in the right ADR home.

### 4.3. Incident and background process traces

For severe errors such as `ORA-00600`, `ORA-07445`, process crashes, or background process errors, traces may be generated automatically. The alert log usually logs the file path or incident ID. Save all related traces, the incident ID, and supporting files from the same time window.

Do not collect only foreground session traces. An I/O, redo, archive, or recovery error may be written in the trace of a background process such as DBWn, LGWR, ARCn, or another process. Search by timestamp, process ID, and incident ID in ADR.

## 5. Using ADRCI and Incident Packaging

ADRCI lets you browse ADR homes, filter alerts, list problems/incidents, and package diagnostic data for investigation.

A common interactive session:

```text
adrci
show homes
set homepath diag/rdbms/<db_unique_name>/<instance_name>
show problem
show incident
show alert -tail 200
```

When Oracle creates an incident, note the incident ID and problem key. For incidents that need to be sent to Oracle Support, IPS can create a diagnostic package:

```text
ips create package incident <incident_id>
ips show packages
ips generate package <package_id> in <output_directory>
```

IPS command names and options may differ across releases. Verify the syntax using ADRCI help on the running host. Diagnostic packages may contain SQL statements, schema names, file paths, system information, and sensitive data; control where they are stored, who can access them, and how they are shared.

Do not delete incidents or purge ADR simply to free disk space before confirming that required packages have been created and stored safely. ADR retention/purge policies should be managed by DBAs based on disk capacity and support requirements.

## 6. Collecting SQL_ID and related SQL statements

### 6.1. What is SQL_ID?

`SQL_ID` is the identifier of a SQL statement in the shared SQL area. It helps locate the corresponding cursor and execution plan. However, a SQL_ID does not identify a single execution:

- One SQL_ID can have multiple child cursors.
- Each child cursor can have a different plan hash value, bind metadata, or cursor sharing mismatch reason.
- The same SQL_ID can be executed by multiple sessions and on multiple instances.
- A cursor can be aged out of the shared pool before the investigator queries it.
- SQL_ID does not replace timestamp, SID/SERIAL#, instance, PDB, or execution ID.

When recording SQL details, capture the SQL_ID, child number, plan hash value, active timestamps, parsing schema, and executing session if available.

### 6.2. Getting SQL_ID from an active session

Query the target session:

```sql
SELECT sid,
       serial#,
       username,
       status,
       sql_id,
       sql_child_number,
       sql_exec_start,
       sql_exec_id,
       prev_sql_id,
       prev_child_number,
       event,
       wait_class,
       seconds_in_wait,
       blocking_session,
       blocking_instance
FROM v$session
WHERE sid = :sid;
```

`SQL_ID` is typically the session's current SQL; `PREV_SQL_ID` is the previous SQL. If the error occurred right after a statement completed, `PREV_SQL_ID` may be more useful. Execution fields can be empty if the session is not executing SQL at the moment of the query.

For RAC:

```sql
SELECT inst_id,
       sid,
       serial#,
       username,
       status,
       sql_id,
       sql_child_number,
       sql_exec_start,
       sql_exec_id,
       prev_sql_id,
       event,
       wait_class,
       blocking_session,
       blocking_instance,
       con_id
FROM gv$session
WHERE inst_id = :inst_id
  AND sid = :sid;
```

If the session is not yet known, search by username, module, machine, client identifier, or timestamp:

```sql
SELECT inst_id,
       sid,
       serial#,
       username,
       machine,
       program,
       service_name,
       module,
       action,
       client_identifier,
       sql_id,
       prev_sql_id,
       event,
       wait_class,
       logon_time,
       con_id
FROM gv$session
WHERE username = UPPER(:username)
ORDER BY inst_id, logon_time DESC;
```

Narrow down using known criteria. Do not put credentials or personal data into search predicates or collected logs.

### 6.3. Getting SQL text and child cursors

Once you have the SQL_ID:

```sql
SELECT inst_id,
       sql_id,
       child_number,
       plan_hash_value,
       parsing_schema_name,
       module,
       action,
       executions,
       last_active_time,
       sql_fulltext
FROM gv$sql
WHERE sql_id = :sql_id
ORDER BY inst_id, child_number;
```

`SQL_FULLTEXT` holds the SQL text as a CLOB. If client permissions or tools truncate the output, export the CLOB to a file safely. If the SQL_ID is no longer in the shared pool, look for it in collected trace files or historical sources that your organization is licensed and permitted to use.

Do not draw conclusions from SQL text alone. Record the child cursor, plan hash, and executing session. If multiple child cursors exist, determine which child the session used via `SQL_CHILD_NUMBER` or `PREV_CHILD_NUMBER`.

### 6.4. Getting the execution plan

You can view the plan of a cursor still in the shared pool:

```sql
SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    sql_id          => :sql_id,
    cursor_child_no => :child_no,
    format          => 'TYPICAL'
  )
);
```

If appropriate runtime statistics were collected, you can use the `ALLSTATS LAST` format to inspect actual metrics from the most recent execution. Only use bind-displaying options when there is a clear investigative need and sensitive data is properly controlled. Bind values can contain customer information, tokens, email addresses, or business data.

Plans can vary by child cursor, bind peeking, statistics, optimizer parameters, schema, and time. Save the plan hash along with the plan text, SQL_ID, child number, timestamp, and instance for accurate comparison.

### 6.5. SQL_ID and historical data

If a cursor has already aged out of the shared pool, historical data may help recover the SQL and execution details. However, AWR, ASH, ADDM, SQL Monitor, and related views/packages require licensing under Oracle Diagnostics Pack or Tuning Pack depending on the feature and release.

Do not query `DBA_HIST_*`, `V$ACTIVE_SESSION_HISTORY`, AWR reports, SQL Monitor, or call pack APIs unless your organization has confirmed entitlement to use them. Check your licensing documentation and active agreements. When not licensed, rely on the alert log, trace files, `V$SESSION`, `V$SQL`, and legitimately collected observational data.

## 7. Collecting session, wait event, and blocking details

SQL_ID identifies the SQL statement; session state explains why the statement is slow or hung.

### 7.1. Session state

Capture at minimum:

- `SID`, `SERIAL#`, `INST_ID`, `CON_ID`.
- Username, machine, program, service, module, action, and client identifier.
- SQL_ID, child number, previous SQL_ID.
- Event, wait class, wait time, and blocking session.
- Logon time, session status, and SQL execution start time if available.

Do not capture only a single snapshot when an incident persists. For intermittent issues, collect snapshots at controlled intervals to observe sessions transitioning between active, waiting, blocking, and idle states.

### 7.2. Finding blockers and waiters

Example query:

```sql
SELECT inst_id,
       sid,
       serial#,
       username,
       blocking_instance,
       blocking_session,
       event,
       wait_class,
       seconds_in_wait,
       sql_id,
       module,
       action
FROM gv$session
WHERE blocking_session IS NOT NULL
   OR status = 'ACTIVE'
ORDER BY inst_id, seconds_in_wait DESC;
```

A session in the `ACTIVE` state is not necessarily failing; it may be processing normally or waiting on a resource. Record the event and wait class along with any blocker. Before killing a session, determine the open transaction, affected users, and rollback impact.

### 7.3. Locks and involved objects

When an incident involves locking, you can join `GV$LOCK`, `GV$SESSION`, and `DBA_OBJECTS` to identify lock types and affected objects. Object IDs in `V$LOCKED_OBJECT` can be joined with `DBA_OBJECTS.OBJECT_ID`:

```sql
SELECT lo.inst_id,
       lo.session_id AS sid,
       s.serial#,
       s.username,
       o.owner,
       o.object_name,
       o.object_type,
       lo.locked_mode
FROM gv$locked_object lo
JOIN gv$session s
  ON s.inst_id = lo.inst_id
 AND s.sid = lo.session_id
JOIN dba_objects o
  ON o.object_id = lo.object_id
ORDER BY lo.inst_id, lo.session_id;
```

Views and access privileges may vary by release. If the query returns multiple rows, distinguish sessions holding locks from sessions waiting on locks; do not assume every lock contention is a deadlock. Oracle typically detects deadlocks automatically and writes the related error to trace files and the alert log.

## 8. Enabling SQL trace in a controlled manner

SQL trace records SQL statements, parse/execute/fetch phases, wait events, and timing statistics. Tracing is useful when you need to know which statements a session runs and where time is spent. Tracing can generate large volumes of data and may contain sensitive SQL text or bind values.

### 8.1. Tracing the current session

You can enable tracing for the current session using `DBMS_MONITOR`:

```sql
BEGIN
  DBMS_MONITOR.SESSION_TRACE_ENABLE(
    waits => TRUE,
    binds => FALSE
  );
END;
/
```

After reproducing the error once, disable tracing:

```sql
BEGIN
  DBMS_MONITOR.SESSION_TRACE_DISABLE;
END;
/
```

The `waits => TRUE` parameter records wait events. `binds => FALSE` avoids logging bind values by default in this example. Only enable bind tracing when necessary, approved, and with trace file protections in place.

### 8.2. Tracing another session

A DBA can enable tracing for an identified session using SID and SERIAL#:

```sql
BEGIN
  DBMS_MONITOR.SESSION_TRACE_ENABLE(
    session_id => :sid,
    serial_num => :serial_no,
    waits      => TRUE,
    binds      => FALSE
  );
END;
/
```

When finished, call `SESSION_TRACE_DISABLE` with the same SID and SERIAL#. In RAC, identify the correct instance before enabling trace and use the overload/arguments matching your Oracle version. If a session disconnects or is recreated, its SID may be reused; always re-verify SERIAL# and session identity before acting.

### 8.3. Tracing by client identifier, service, module, or action

In systems using connection pools, the database session can change across requests. Tracing by client identifier or service/module/action allows tracking an application flow without guessing which session will pick up the next request.

Oracle provides procedures in `DBMS_MONITOR` such as:

- `CLIENT_ID_TRACE_ENABLE` and `CLIENT_ID_TRACE_DISABLE`.
- `SERV_MOD_ACT_TRACE_ENABLE` and `SERV_MOD_ACT_TRACE_DISABLE`.

These procedures let you scope tracing by client identifier or a combination of service, module, and action. Check the exact signature for your running release before use, and choose values specific enough to avoid tracing the entire production workload.

Applications should set identification metadata via `DBMS_APPLICATION_INFO.SET_MODULE`, `DBMS_APPLICATION_INFO.SET_ACTION`, and `DBMS_SESSION.SET_IDENTIFIER` at the start of request handling. Upon completion, reset these values according to connection pool conventions so the next request does not inherit context from the previous request.

Example:

```sql
BEGIN
  DBMS_APPLICATION_INFO.SET_MODULE(
    module_name => 'ORDER_API',
    action_name => 'CREATE_ORDER'
  );
  DBMS_SESSION.SET_IDENTIFIER('request-20261114-00042');
END;
/
```

The client identifier value should be a correlation ID containing no secrets. Do not use access tokens, passwords, or personal data as the identifier.

### 8.4. Analyzing traces with TKPROF

Raw trace files can be formatted with TKPROF on a host that has the corresponding Oracle client/tools installed:

```text
tkprof input_trace.trc output_trace.txt waits=yes sort=exeela,fchela
```

TKPROF summarizes parse/execute/fetch counts, CPU, elapsed time, logical reads, physical reads, and waits depending on trace content. Keep the raw trace alongside the generated TKPROF output so others can verify the analysis.

A trace alone does not automatically reveal the entire root cause. For instance, high elapsed time could stem from I/O waits, locks, network delays, or CPU saturation; correlate it with the alert log, session snapshots, and OS metrics.

## 9. Capturing errors from applications and PL/SQL

When an application catches an error and logs only `ORA-xxxxx`, critical context is usually lost. You should log the full error stack, backtrace, and request metadata at the application or PL/SQL layer.

In PL/SQL, you can capture:

```sql
EXCEPTION
  WHEN OTHERS THEN
    DBMS_OUTPUT.PUT_LINE('SQLCODE=' || SQLCODE);
    DBMS_OUTPUT.PUT_LINE('SQLERRM=' || SQLERRM);
    DBMS_OUTPUT.PUT_LINE(DBMS_UTILITY.FORMAT_ERROR_STACK);
    DBMS_OUTPUT.PUT_LINE(DBMS_UTILITY.FORMAT_ERROR_BACKTRACE);
    DBMS_OUTPUT.PUT_LINE(DBMS_UTILITY.FORMAT_CALL_STACK);
    RAISE;
```

This is an illustrative example; in real applications, write this information to a structured logger rather than relying on `DBMS_OUTPUT`. Do not swallow exceptions with `WHEN OTHERS THEN NULL`. If you need to enrich context, preserve the original error code and backtrace and re-raise an appropriate error.

Application logs should include:

- Timestamp with timezone or UTC.
- Correlation/request ID.
- Service, module, action, and client identifier.
- Business operation name and application version.
- Database service, PDB if known to the application, and connection pool identity.
- SQL_ID if the driver or observability layer can obtain it safely.
- ORA error code, stack, backtrace, and execution duration.

Do not log passwords, access tokens, card data, personally identifiable information, or sensitive bind values. If SQL/binds must be saved for investigation, apply masking, encryption, access controls, and retention limits.

## 10. Collecting OS and network context

Database traces capture only part of an incident. For connectivity errors, process crashes, I/O stalls, or latency issues, collect additional host-level data:

| Category | Evidence to collect |
|---|---|
| Operating system | Hostname, timestamp, uptime, CPU, memory, swap, processes, and system logs |
| Storage | Filesystem capacity, IOPS/latency, mount errors, multipath or storage path issues |
| Network | Packet loss, resets, timeouts, DNS, listener logs, and firewall/load balancer events |
| Oracle process | PID/SPID, trace file, process state, and process termination time |
| Client | Driver/JDBC version, connect descriptor, timeouts, pool metrics, and exception stack |
| Cluster | Node/instance, service relocation, resource restarts, and clusterware events |

For connectivity errors, collect listener logs and client-side logs over the same time range as the alert log. Do not share entire connection configuration files if they contain passwords or secrets. You can redact sensitive values while keeping the host/service/port needed for analysis.

## 11. Pre-remediation collection workflow template

### Step 1: Record the event

Create an incident ticket/ID and record the start time, detection time, reporter, environment, impact level, business operation, and reproduction steps. Specify whether the error occurred once or repeatedly.

### Step 2: Capture database context

Collect database name/DBID/DB_UNIQUE_NAME, instance, host, PDB/CON_ID, service, session user, schema, module, action, and client identifier. In RAC, record `INST_ID` for each session.

### Step 3: Save the alert log and incidents

Identify the ADR home from `V$DIAG_INFO`. Save the alert log covering the period before and after the event, problem key, incident ID, and related messages. For severe incidents, generate a diagnostic package per support procedures.

### Step 4: Locate the session and SQL

Record SID/SERIAL#, SQL_ID/PREV_SQL_ID, child number, plan hash, execution start/ID, wait event, wait class, and blocker. Save the SQL text if it is still in the shared pool, along with the instance and timestamp.

### Step 5: Collect trace when needed

Select the right session or client/module/action. Enable time-bounded tracing, reproduce once, disable tracing, and note the file path. If the error has already occurred, check for automatic traces in ADR before enabling new tracing.

### Step 6: Preserve the evidence

Copy the alert log, trace files, listener logs, application logs, and query outputs into an access-controlled incident directory. Preserve originals, record checksums if required by policy, and document the source of each file.

### Step 7: Begin remediation

Once sufficient evidence is secured, analyze the root cause and choose the smallest-scope corrective action. Record every change, execution time, operator, and post-change outcome. If an emergency restart or session kill is necessary, capture whatever data can be gathered immediately prior to that action.

## 12. Incident collection form template

You can use the following template in a ticket or operations record:

```text
Incident ID:
Short description:
Impact level:
Start time (timezone/UTC):
End time:
Frequency / reproducibility:

Database / DBID / DB_UNIQUE_NAME:
Release / RU / patch:
Instance / host:
PDB / CON_ID:
Service:
Schema / user:
Application version / driver:
Module / action / client identifier:

ORA error / full error stack:
SID / SERIAL# / INST_ID:
SQL_ID / PREV_SQL_ID:
Child number / plan hash:
SQL execution start / ID:
Wait event / wait class:
Blocking session / instance:

ADR home:
Alert log path / time range:
Incident ID / problem key:
Trace file path:
Listener log:
Application log / correlation ID:
OS / storage / network evidence:

Actions taken:
Outcome after each action:
Collected by / timestamp:
Evidence storage location:
```

Do not include passwords, secrets, or unnecessary personal data in the form. Apply the same protection policies to SQL text and trace files as to production data.

## 13. Common investigation mistakes

| Mistake | Why it hinders investigation | Recommended approach |
|---|---|---|
| Capturing only a single ORA error line | Loses error stack, timestamp, and preceding errors | Save the full error stack, alert log, and related traces |
| Omitting the timezone | Cannot correlate application and database logs | Record UTC or an explicit offset |
| Saving only SQL_ID | Does not identify which child cursor, instance, or execution was involved | Save SQL_ID, child number, plan hash, SID/SERIAL#, INST_ID, and timestamp |
| Querying V$SESSION after the session ended | The session is no longer in the view | Take snapshots while the error is active and preserve trace files |
| Restarting immediately before pulling logs | Can lose session state and transient evidence | Collect alert log, traces, and session context first if the situation permits |
| Enabling system-wide tracing | Causes overhead and huge trace volumes | Scope by session, client, service, module, or action |
| Enabling bind tracing indiscriminately | May expose sensitive data | Keep binds off by default; enable only when approved |
| Using AWR/ASH without verifying licensing | May violate licensing terms | Verify Diagnostics/Tuning Pack entitlements first |
| Collecting only foreground traces | Misses background, I/O, or recovery errors | Search additional traces by incident, process, and alert log |
| Running repairs or changing parameters before saving state | Alters metadata or overwrites evidence | Record initial state and logs before taking action |

## 14. Protecting and storing evidence

Alert logs and trace files can contain SQL text, schema/object names, server paths, hostnames, client identifiers, bind values, and operational details. Treat them as potentially sensitive internal data.

- Store evidence in areas with role-based access control.
- Use encryption when storing or transferring files off the database server.
- Do not attach raw trace files to public tickets or unapproved chat channels.
- Mask sensitive details in shared copies while keeping originals in a secure repository.
- Enforce retention periods and deletion procedures according to organizational policy.
- Log who accesses or downloads diagnostic packages when audit requirements apply.
- When sending data to Oracle Support, use organization-approved support channels and review package contents before uploading.

## 15. Investigation principles

The alert log shows what happened at the database level; traces provide process- or session-level details; `SQL_ID` pinpoints the cursor; and session, service, PDB, instance, host, and correlation ID link those pieces into a single analyzable event. No single source on its own is enough to conclude the root cause.

Before applying a fix, collect data within the same time window, confirm the exact instance and container, save the SQL along with its child cursor, preserve the original trace files, and record all actions already taken. Only with complete context can the operations team distinguish SQL bugs, concurrency issues, execution plan changes, configuration problems, resource exhaustion, network faults, or internal Oracle errors, and thereby choose a controlled and verifiable remediation.
