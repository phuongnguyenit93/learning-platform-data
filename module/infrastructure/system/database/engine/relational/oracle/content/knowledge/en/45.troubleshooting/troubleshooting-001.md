# Procedure for Determining Timestamp, Scope, Recent Changes, and Evidence

When an Oracle Database incident occurs, the hardest part is usually not running an immediate fix command, but reconstructing exactly what happened: when it started, how far the impact reached, what changes occurred immediately prior, which components are involved, and what evidence is reliable enough to confirm the root cause.

A sound troubleshooting procedure should follow this order:

1. **Standardize time:** align timezones, timestamps, SCN, and clock skew.
2. **Isolate scope:** identify the affected database, PDB, instance, service, schema, object, session, SQL, and user group.
3. **Reconstruct recent changes:** cross-reference deployments, DDL, configuration, jobs, privileges, statistics, patches, services, and infrastructure changes.
4. **Collect evidence:** capture runtime state, audit records, alert logs, traces, execution plans, transaction metadata, and application logs.
5. **Build a timeline and test hypotheses:** correlate events using time, SCN, SQL_ID, XID, session, and object.
6. **Preserve evidence and choose actions:** keep original copies, record the source, collector, timestamp, and every change made during remediation.

Do not conclude the root cause from a single error message or a single change appearing near the incident time. An event occurring before an incident is an investigative lead, not proof of causation.

## 1. Investigation Objectives and Principles

### 1.1 Four Questions That Must Be Answered

| Question | Required Output |
|---|---|
| When? | Start time, detection time, affected time window, timezone, and SCN reference if available |
| What scope? | Affected database/PDB/instance/service, application, schema/object, data, sessions, and users |
| What were the recent changes? | List of changes with timestamp, human/automation actor, content, and result |
| What is the evidence? | Logs, audit records, SQL/plan, transaction ID, traces, metrics, state snapshots, and checksums |

### 1.2 Distinguishing Facts, Inferences, and Hypotheses

In an incident report, label these clearly:

- **Fact:** a direct observation from a verifiable source, for example the alert log recorded ORA-00600 at 10:04:31 UTC.
- **Inference:** a reasonable conclusion drawn from multiple facts, for example errors started after the service relocated instances and existing connections were dropped.
- **Hypothesis:** a possibility under verification, for example a firewall change may have disrupted ONS.
- **Unknown:** information not yet available or where the data source is insufficient to determine.

Do not turn a hypothesis into a root cause simply because it fits the initial narrative.

### 1.3 Preserve State Before Making Changes

Before restarting an instance, killing sessions, flushing the shared pool, clearing logs, gathering statistics, changing parameters, or running DDL:

- Record the timestamp and current state.
- Collect the alert log, error stack, and required runtime views.
- Save the SQL_ID, child number, plan hash, session identifiers, and wait event.
- Capture counter snapshots if delta comparison is needed.
- Record who performed the action, which command was run, where, and when.

If emergency containment is required to reduce impact, prioritize service safety per the runbook; at the same time, record whatever evidence can be collected beforehand and the exact time the action started.

## 2. Standardizing Time

A timeline with the wrong timezone or skewed clocks can cause a DBA to correlate the wrong deployment, log, and transaction. First, standardize the time reference used in the incident.

### 2.1 Choose a Single Time Standard

Store timestamps in ISO 8601 with a UTC offset, and use UTC as the standard when correlating multiple systems:

~~~text
2026-11-14T10:25:31.482Z
2026-11-14T17:25:31.482+07:00
~~~

Both values represent the exact same point in time. Do not store local time strings without a timezone, because the exact offset cannot be determined later.

In the incident report, record:

- The standard timezone, for example UTC.
- The DBA/operator's timezone.
- The database host's timezone.
- The application host's timezone.
- The time synchronization source (NTP/chrony/Windows Time or infrastructure service).
- The known clock offset at the time of investigation.

### 2.2 Distinguish Oracle Time Functions

~~~sql
SELECT SYSTIMESTAMP              AS database_host_time,
       CURRENT_TIMESTAMP         AS session_time,
       LOCALTIMESTAMP            AS session_local_timestamp,
       DBTIMEZONE                AS database_time_zone,
       SESSIONTIMEZONE            AS session_time_zone,
       SYS_EXTRACT_UTC(SYSTIMESTAMP) AS systimestamp_utc
FROM dual;
~~~

| Function/Value | Meaning |
|---|---|
| SYSTIMESTAMP | Operating system timestamp of the database host, including fractional seconds and timezone offset |
| CURRENT_TIMESTAMP | Current timestamp in the session's timezone |
| LOCALTIMESTAMP | Timestamp in the session's timezone without a timezone in the return type |
| DBTIMEZONE | Database time zone, mainly relevant to timezone-aware data types and storage |
| SESSIONTIMEZONE | Time zone configured for the current session |
| SYS_EXTRACT_UTC | Converts a timestamp with time zone to UTC |

Do not assume DBTIMEZONE is the host's timezone. SYSTIMESTAMP reflects the host clock; CURRENT_TIMESTAMP depends on SESSIONTIMEZONE. When comparing logs from the application and the database, convert them to the same timezone.

### 2.3 Check Time at the Session Level

~~~sql
SELECT sys_context('USERENV', 'SESSION_USER') AS session_user,
       sys_context('USERENV', 'CURRENT_SCHEMA') AS current_schema,
       sys_context('USERENV', 'CON_NAME') AS con_name,
       sys_context('USERENV', 'SERVICE_NAME') AS service_name,
       sys_context('USERENV', 'INSTANCE_NAME') AS instance_name,
       SESSIONTIMEZONE AS session_time_zone,
       CURRENT_TIMESTAMP AS current_timestamp
FROM dual;
~~~

A session can use ALTER SESSION SET TIME_ZONE to change SESSIONTIMEZONE. Therefore, one session may display a different timestamp than another even when running on the same database host.

### 2.4 Cross-Check with the Operating System

The DBA must check the clock on the exact host/VM/container running the database and on the application servers. Linux example:

~~~bash
date -u --iso-8601=ns
timedatectl status
chronyc tracking
~~~

Windows PowerShell example:

~~~powershell
Get-Date -AsUTC -Format o
Get-TimeZone
w32tm /query /status
~~~

Run these commands on the respective host according to operational privileges. Do not treat the time on the DBA's laptop as the authoritative source for database server timestamps.

### 2.5 Clock Drift and Delayed Logs

A system may log timestamps based on when the collector received the message rather than when it originated at the source. A log agent may buffer messages and send them later when the network recovers. Therefore, distinguish between:

- Event time: when the component recorded the event.
- Ingest/receive time: when the logging system received the event.
- Processing time: when the monitoring system processed or displayed the event.

If timestamps do not align, check clock drift, buffering, queue backlog, and timezone conversion before concluding the order of events.

## 3. Using SCN to Correlate Data Changes

Timestamps are useful for humans, but SCN (System Change Number) is Oracle's logical marker for ordering changes within the database.

### 3.1 Get the Current SCN

~~~sql
SELECT current_scn
FROM v$database;
~~~

Or in PL/SQL:

~~~sql
SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS current_scn
FROM dual;
~~~

Record the SCN along with the timestamp, DBID, instance, and container in the investigation snapshot. SCN helps correlate Flashback Query, redo/archive logs, and recovery operations.

### 3.2 Timestamp and SCN Are Not Interchangeable

- A timestamp is wall-clock time, affected by timezone and clock synchronization.
- SCN is the logical order of changes in the database.
- Many changes can occur within a very short interval; displayed timestamps may lack sufficient precision to distinguish them.
- An SCN can be mapped approximately to a timestamp, but should not be treated as an exact wall-clock timestamp.

### 3.3 SCN_TO_TIMESTAMP and TIMESTAMP_TO_SCN

~~~sql
SELECT SCN_TO_TIMESTAMP(:p_scn) AS approximate_time
FROM dual;
~~~

~~~sql
SELECT TIMESTAMP_TO_SCN(
           TO_TIMESTAMP_TZ(
               '2026-11-14 10:00:00 +00:00',
               'YYYY-MM-DD HH24:MI:SS TZH:TZM'
           )
       ) AS approximate_scn
FROM dual;
~~~

These functions provide an approximate mapping within the range of retained mapping metadata. Do not assume they can convert every SCN/timestamp over a long history. Errors can occur when the point falls outside the available mapping range.

### 3.4 ORA_ROWSCN Is Not an Audit Trail

ORA_ROWSCN can help identify the SCN associated with a row change, but by default it may reflect the block level rather than individual rows. If a table is created with ROWDEPENDENCIES, Oracle can track it at the row level with additional storage overhead.

ORA_ROWSCN does not reveal the user, SQL statement, old values, or exact time of change. Do not use it as a replacement for unified auditing, Flashback Version Query, or transaction metadata.

### 3.5 Notes on Using Flashback Query

~~~sql
SELECT *
FROM app.orders AS OF SCN :p_scn
WHERE order_id = :p_order_id;
~~~

Flashback Query can help view data state at an earlier point in time. Query availability depends on retained undo, privileges, and object restrictions. If required undo has been overwritten, the query may fail with snapshot too old.

## 4. Determining Impact Scope

Do not start with the question "Which SQL failed?"; instead, determine which layer is affected. An incident may affect only one session, one service, one PDB, one object, or the entire cluster.

### 4.1 Scope Dimensions to Record

| Dimension | Questions to Answer |
|---|---|
| Database | What are the DBID, DB_UNIQUE_NAME, database role, and open mode? |
| Container | Is the issue in CDB root or which PDB? |
| Instance/node | One instance or all instances? Which host? |
| Service | Which service is failing, relocated, or overloaded? |
| Application | Which application, module, endpoint, batch, or client is affected? |
| Schema/object | Which schema, table, index, package, job, or database link is involved? |
| Data | Which record type, key range, tenant, or partition is affected? |
| Session/SQL | Which SID/SERIAL#, SQL_ID, child cursor, and XID are involved? |
| User/tenant | One user, a group, or all tenants? |
| Time window | Start, end, and any window with unreliable data? |

### 4.2 Identify Database and Instance

~~~sql
SELECT name,
       dbid,
       db_unique_name,
       database_role,
       open_mode,
       log_mode,
       current_scn
FROM v$database;
~~~

~~~sql
SELECT instance_number,
       instance_name,
       host_name,
       version,
       startup_time,
       status,
       database_status
FROM v$instance;
~~~

In RAC:

~~~sql
SELECT inst_id,
       instance_name,
       host_name,
       startup_time,
       status
FROM gv$instance
ORDER BY inst_id;
~~~

STARTUP_TIME is critical when comparing cumulative counters: after a restart, many in-memory counters are reset.

### 4.3 Identify Container/PDB

~~~sql
SELECT con_id,
       name,
       open_mode,
       restricted
FROM v$containers
ORDER BY con_id;
~~~

From CDB root, CDB_*/GV$ views can span multiple containers. Keep CON_ID when joining or aggregating; do not merge data for objects with the same name from different PDBs.

### 4.4 Identify Service

~~~sql
SELECT inst_id,
       name,
       network_name,
       goal,
       clb_goal,
       aq_ha_notification
FROM gv$services
ORDER BY name, inst_id;
~~~

Cross-check the service name in the application's connection string, the cluster service configuration, and SERVICE_NAME in V$SESSION.

### 4.5 Identify Relevant Sessions

~~~sql
SELECT inst_id,
       sid,
       serial#,
       username,
       status,
       service_name,
       machine,
       program,
       module,
       action,
       client_identifier,
       sql_id,
       sql_child_number,
       prev_sql_id,
       event,
       wait_class,
       blocking_instance,
       blocking_session,
       logon_time
FROM gv$session
WHERE type = 'USER'
ORDER BY inst_id, status, username;
~~~

This is a current snapshot. Disconnected sessions are no longer in V$SESSION; historical investigation requires audit records, ASH/AWR if licensed, application logs, or saved traces.

### 4.6 Identify Objects and Dependencies

~~~sql
SELECT owner,
       object_name,
       subobject_name,
       object_type,
       status,
       created,
       last_ddl_time
FROM dba_objects
WHERE owner = UPPER(:p_owner)
  AND object_name = UPPER(:p_object)
ORDER BY object_type, subobject_name;
~~~

LAST_DDL_TIME indicates that DDL has affected the object, but does not tell you the exact DDL statement, who ran it, or all related changes. Combine it with the audit trail, deployment records, and administrative logs.

### 4.7 Identify Data Range

If the incident involves data, record:

- Primary keys or business keys of sample rows.
- Relevant partitions/subpartitions.
- SCN/timestamp range before and after the change.
- Number of affected rows and number of rows subsequently corrected.
- Related tables via foreign keys or business workflows.
- Affected tenants/customers/accounts.

Do not save just one sample row and conclude the scope is a single row. Use a query with explicit conditions to count the scope and save the result at investigation time.

## 5. Identifying Recent Changes

Recent changes may be DDL, DML, deployments, database configuration, service changes, patches, jobs, statistics, network, or OS changes. Build a chronological list of changes rather than simply asking the DBA if they ran any commands.

### 5.1 Change Categories to Review

| Category | Examples |
|---|---|
| Application deployment | New release, hotfix, migration script, connection pool change |
| Database DDL | CREATE/ALTER/DROP TABLE, INDEX, VIEW, PACKAGE, TRIGGER |
| DML/data load | Bulk load, ETL, import, batch update/delete |
| Security | GRANT/REVOKE, user/role/profile, password rotation |
| Initialization parameters | SGA/PGA, optimizer, cursor, parallelism, undo, archive |
| Optimizer statistics | DBMS_STATS gather, histogram, extended stats, locked stats |
| Scheduler | New job, schedule change, credential, destination |
| Service/RAC | Start/stop/relocate service, instance maintenance, node eviction |
| Storage | ASM disk group, filesystem, mount, capacity, latency |
| Network | DNS, firewall, load balancer, SCAN/listener, TLS certificate |
| Database patch/upgrade | RU, one-off patch, OPatch, datapatch, COMPATIBLE/OFE |
| External systems | API, message broker, file transfer, identity provider |

### 5.2 Check Most Recent DDL Time

~~~sql
SELECT owner,
       object_name,
       object_type,
       created,
       last_ddl_time,
       status
FROM dba_objects
WHERE last_ddl_time >= :p_from_time
ORDER BY last_ddl_time DESC;
~~~

This query produces a candidate list, not a complete DDL history. An object can be marked as modified by several types of DDL or administrative operations. It does not identify the actor.

### 5.3 Check DDL and Audit Trail

If Unified Auditing is configured to record DDL, you can query:

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       object_schema,
       object_name,
       return_code,
       client_program_name,
       userhost,
       sql_text
FROM unified_audit_trail
WHERE event_timestamp >= :p_from_time
  AND action_name IN (
      'CREATE TABLE',
      'ALTER TABLE',
      'DROP TABLE',
      'CREATE INDEX',
      'ALTER INDEX',
      'DROP INDEX',
      'CREATE PROCEDURE',
      'ALTER PROCEDURE',
      'DROP PROCEDURE',
      'GRANT',
      'REVOKE'
  )
ORDER BY event_timestamp;
~~~

Action names may vary by statement type, audit policy, and release. Before using, verify the actual columns and policies. If the database uses traditional auditing or mixed mode, the audit sources may differ.

The absence of an audit record does not prove no change occurred. The policy may not have been enabled, auditing may not apply to the user/action, records may have been purged, or the event occurred before logging was configured.

### 5.4 Check Parameter Changes

~~~sql
SELECT name,
       value,
       isdefault,
       issys_modifiable,
       isses_modifiable,
       ispdb_modifiable,
       con_id
FROM v$parameter
WHERE name IN (
    'memory_target',
    'sga_target',
    'pga_aggregate_target',
    'processes',
    'sessions',
    'open_cursors',
    'optimizer_features_enable',
    'optimizer_mode',
    'undo_retention',
    'log_buffer',
    'parallel_max_servers'
)
ORDER BY name, con_id;
~~~

V$PARAMETER reflects effective values in the current instance/session according to the view's scope. To find out who changed a parameter and when, cross-check the alert log, audit trail, SPFILE history/configuration management, and change records.

Check values stored in SPFILE:

~~~sql
SELECT sid,
       name,
       value,
       isspecified,
       update_comment
FROM v$spparameter
WHERE isspecified = 'TRUE'
ORDER BY name, sid;
~~~

V$SPPARAMETER describes the configuration in the SPFILE; it is not an audit trail of modification history.

### 5.5 Check Optimizer Statistics Changes

~~~sql
SELECT owner,
       table_name,
       object_type,
       last_analyzed,
       stale_stats,
       stattype_locked
FROM dba_tab_statistics
WHERE last_analyzed >= :p_from_time
ORDER BY last_analyzed DESC;
~~~

Cross-check with DBMS_STATS logs, scheduler jobs, maintenance windows, and deployments. Fresh statistics can cause an execution plan to change, but LAST_ANALYZED alone does not prove a statistics change is the root cause.

### 5.6 Check New or Modified Objects

~~~sql
SELECT owner,
       object_name,
       object_type,
       created,
       last_ddl_time,
       status
FROM dba_objects
WHERE created >= :p_from_time
   OR last_ddl_time >= :p_from_time
ORDER BY GREATEST(created, last_ddl_time) DESC;
~~~

This is a quick way to find objects with recent timestamps. Combine with DBA_DEPENDENCIES, source control, and auditing to determine the actual content and impact.

### 5.7 Check Scheduler Jobs

~~~sql
SELECT owner,
       job_name,
       enabled,
       state,
       job_type,
       job_action,
       repeat_interval,
       last_start_date,
       next_run_date
FROM dba_scheduler_jobs
ORDER BY owner, job_name;
~~~

Run history:

~~~sql
SELECT log_date,
       owner,
       job_name,
       status,
       error#,
       actual_start_date,
       run_duration,
       additional_info
FROM dba_scheduler_job_run_details
WHERE log_date >= :p_from_time
ORDER BY log_date DESC;
~~~

Check disabled jobs, newly added jobs, abnormally long-running jobs, and jobs coinciding with the incident time. A job action may invoke a package or external procedure; trace the dependencies.

### 5.8 Check Application Deployments and Changes

The database cannot know every application release on its own. Gather information from:

- CI/CD deployment history: release ID, commit SHA, pipeline run, start/end time.
- Migration tool: schema version before/after, scripts executed, checksum, and result.
- Application logs: build/version, pod/container, endpoint, request ID.
- Configuration management: changes to datasource URL, pool size, timeout, retry, TLS, feature flags.
- Secret manager: time of credential or certificate rotation; do not include secret values in incident evidence.

Correlate deployment times with database DDL, package invalidation, connection errors, and SQL plan changes.

## 6. Collecting Runtime Evidence in Oracle

Runtime views reflect current state or cumulative counters. Clearly record the data type and snapshot timestamp.

### 6.1 Active Sessions

~~~sql
SELECT inst_id,
       sid,
       serial#,
       username,
       status,
       service_name,
       module,
       action,
       client_identifier,
       sql_id,
       sql_child_number,
       sql_exec_start,
       last_call_et,
       event,
       wait_class,
       state,
       blocking_instance,
       blocking_session
FROM gv$session
WHERE type = 'USER'
  AND status = 'ACTIVE'
ORDER BY last_call_et DESC;
~~~

STATUS ACTIVE does not necessarily mean the session is consuming CPU; the session may be waiting. Read EVENT, WAIT_CLASS, STATE, and blocker information alongside SQL_ID.

### 6.2 SQL Cursor and Plan

~~~sql
SELECT inst_id,
       sql_id,
       child_number,
       plan_hash_value,
       executions,
       parse_calls,
       buffer_gets,
       disk_reads,
       rows_processed,
       cpu_time,
       elapsed_time,
       last_active_time,
       module,
       action,
       sql_text
FROM gv$sql
WHERE sql_id = :p_sql_id
ORDER BY inst_id, child_number;
~~~

CPU_TIME and ELAPSED_TIME in SQL views are in microseconds. These are typically cumulative counters per cursor, not metrics for a single execution. Parallel execution can make total elapsed database time larger than wall-clock duration.

View the actual plan:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :p_sql_id,
        :p_child_number,
        'ALLSTATS LAST +PEEKED_BINDS +PREDICATE +NOTE'
    )
);
~~~

Only inspect bind values if authorized; binds may contain PII, credentials, tokens, or sensitive data. Redact before placing into tickets or sharing outside the authorized group.

### 6.3 Wait Events and Blockers

~~~sql
SELECT inst_id,
       sid,
       serial#,
       event,
       wait_class,
       total_waits,
       time_waited_micro,
       average_wait
FROM gv$session_event
WHERE time_waited_micro > 0
ORDER BY time_waited_micro DESC;
~~~

V$SESSION_EVENT/GV$SESSION_EVENT contains cumulative per-session metrics. To see the wait currently happening, check GV$SESSION.EVENT/STATE; to determine the increase during the incident window, take two snapshots.

### 6.4 Open Transactions

~~~sql
SELECT s.inst_id,
       s.sid,
       s.serial#,
       s.username,
       s.sql_id,
       t.xidusn,
       t.xidslot,
       t.xidsqn,
       t.start_scn,
       t.start_time,
       t.used_ublk,
       t.used_urec
FROM gv$session s
JOIN gv$transaction t
  ON t.inst_id = s.inst_id
 AND t.ses_addr = s.saddr
ORDER BY t.start_time;
~~~

Open transactions can hold locks or generate large amounts of undo/redo. XID in GV$TRANSACTION helps correlate with Flashback Transaction Query when configuration and privilege requirements are met.

### 6.5 Cumulative Counters: Always Take Snapshots

V$SYSSTAT, V$SESSTAT, V$SQL, and wait views typically hold cumulative counters. Capture snapshots T0 and T1, then calculate:

\[
\Delta C = C_{T1} - C_{T0}
\]

\[
\text{Rate} = \frac{\Delta C}{\text{seconds between samples}}
\]

When comparing, keep the same INST_ID, CON_ID, SID/SERIAL#, SQL_ID/CHILD_NUMBER, and the same instance/cursor lifecycle. If the instance restarts or a cursor is aged out/reloaded, deltas may become negative or discontinuous.

## 7. Logs and Audits as Time-Based Evidence

### 7.1 Alert Log

The alert log records important instance/database events such as startup/shutdown, checkpoints, archive errors, ORA errors, recovery, parameter changes, and certain administrative events.

Query the alert log via the ADR view:

~~~sql
SELECT originating_timestamp,
       normalized_timestamp,
       message_type,
       message_level,
       process_id,
       message_text
FROM v$diag_alert_ext
WHERE originating_timestamp >=
      TO_TIMESTAMP_TZ(
          '2026-11-14 09:00:00 +00:00',
          'YYYY-MM-DD HH24:MI:SS TZH:TZM'
      )
ORDER BY originating_timestamp;
~~~

Adjust the timestamp to match the actual incident. V$DIAG_ALERT_EXT can read the XML alert log in ADR; access depends on the account's dictionary/diagnostic privileges.

### 7.2 ADRCI

ADRCI can view the alert log and manage incidents/traces:

~~~text
adrci
show homes
set home diag/rdbms/<db_unique_name>/<instance_name>
show alert -tail 200
show incident
show problem
~~~

ADR home names vary by database, instance, and host. Do not assume the same ADR home path across all RAC nodes.

### 7.3 Trace Files

When ORA-00600, ORA-07445, process crashes, or internal errors occur, Oracle may generate trace files in ADR. Record:

- Timestamp and process ID.
- Incident ID/problem key if present.
- File path and size.
- Stack/error arguments.
- SQL_ID/session if provided in the trace.
- Host name, instance, database, and version/RU.

Do not modify original trace files. If sensitive data needs redacting, create a redacted copy and preserve the original per security policy.

### 7.4 Unified Audit Trail

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       object_schema,
       object_name,
       system_privilege_used,
       return_code,
       userhost,
       client_program_name,
       client_identifier,
       sql_text
FROM unified_audit_trail
WHERE event_timestamp >= :p_from_time
ORDER BY event_timestamp;
~~~

Audit records exist only if the action/user/object is covered by an active audit policy and the records have not been purged. Missing records do not imply the event did not happen.

### 7.5 Fine-Grained Auditing

Fine-Grained Auditing (FGA) can record data access based on policies on tables/views, conditions, and columns. Check DBA_FGA_AUDIT_TRAIL or the corresponding view when the application has FGA policies.

FGA is useful for tracking access to sensitive data subsets, but is not automatically enabled on all tables. Verify the policy and predicate scope before using it as evidence.

### 7.6 Listener and Network Logs

When applications cannot connect to the database, cross-check:

- Listener log: connection requests, service registration, refused connections.
- SCAN listener and local listener in RAC.
- ONS client/server logs: FAN notifications, SSL, topology.
- Firewall/load balancer logs: resets, timeouts, denies, route changes.
- DNS logs and certificate/TLS rotation.
- Application pool logs: borrow timeouts, validation failures, reconnects.

Connection errors can originate from the network, DNS, TLS, service registration, or the pool; do not default to assuming a database engine failure.

## 8. Flashback and Transaction Evidence

When data modification or deletion is suspected, Flashback can help locate row versions and transactions.

### 8.1 Flashback Version Query

~~~sql
SELECT versions_startscn,
       versions_endscn,
       versions_starttime,
       versions_endtime,
       versions_xid,
       versions_operation,
       order_id,
       status,
       total_amount
FROM app.orders
VERSIONS BETWEEN TIMESTAMP
    TO_TIMESTAMP('2026-11-14 09:00:00', 'YYYY-MM-DD HH24:MI:SS')
AND TO_TIMESTAMP('2026-11-14 11:00:00', 'YYYY-MM-DD HH24:MI:SS')
WHERE order_id = :p_order_id
ORDER BY versions_startscn;
~~~

VERSIONS_XID links a row version to a transaction. Version Query requires available undo; UNDO_RETENTION is a target and is not strictly guaranteed if the undo tablespace runs out of space.

### 8.2 Flashback Transaction Query

~~~sql
SELECT xid,
       start_scn,
       start_timestamp,
       commit_scn,
       commit_timestamp,
       logon_user,
       operation,
       table_owner,
       table_name,
       row_id,
       undo_sql
FROM flashback_transaction_query
WHERE xid = :p_xid
ORDER BY undo_change#;
~~~

This view provides metadata and logical reverse SQL. Configuration/privilege prerequisites include an appropriate COMPATIBLE setting, minimal supplemental logging, and SELECT ANY TRANSACTION. UNDO_SQL is not a flawless recovery script; review it before executing.

### 8.3 Redo Logs and Archived Logs

~~~sql
SELECT thread#,
       sequence#,
       first_time,
       next_time,
       archived,
       status
FROM v$log_history
WHERE first_time BETWEEN :p_from_time AND :p_to_time
ORDER BY thread#, sequence#;
~~~

~~~sql
SELECT thread#,
       sequence#,
       first_time,
       completion_time,
       archived,
       deleted,
       status,
       name
FROM v$archived_log
WHERE first_time BETWEEN :p_from_time AND :p_to_time
ORDER BY thread#, sequence#;
~~~

Redo/archive evidence helps correlate timestamps and SCNs. If detailed redo analysis is needed, LogMiner can assist, provided the required archived/online redo logs, appropriate supplemental logging, privileges, and dedicated procedures are in place.

## 9. AWR, ASH, and Performance History

Dynamic performance views show current state and some in-memory counters. For historical investigation, DBAs may need AWR, ASH, or a monitoring repository.

### 9.1 AWR

AWR stores periodic performance statistics snapshots, supporting comparisons of workload, top SQL, wait events, load profile, and resource usage over time.

Common views:

- DBA_HIST_SNAPSHOT
- DBA_HIST_SQLSTAT
- DBA_HIST_SYSSTAT
- DBA_HIST_SYSTEM_EVENT
- DBA_HIST_ACTIVE_SESS_HISTORY

Match DBID, INSTANCE_NUMBER, SNAP_ID, and snapshot times. An AWR report covering a wide time window can mask a very brief spike; combine it with logs and finer-grained snapshots.

### 9.2 ASH

Active Session History samples active sessions over time, useful for analyzing past sessions, SQL_IDs, wait events, modules, and blocking.

Sources:

- V$ACTIVE_SESSION_HISTORY: ASH data in memory.
- DBA_HIST_ACTIVE_SESS_HISTORY: ASH data persisted in AWR.

ASH is sampled data, not a complete record of every SQL execution. Very short events may not be sampled.

### 9.3 Licensing

AWR, ASH, ADDM, and certain SQL Tuning/SQL Monitor capabilities may require the Oracle Diagnostics Pack or Tuning Pack depending on the feature and release. Before using them in production, verify your organization's license entitlements. The mere existence or queryability of a view does not prove entitlement to use the feature.

If you are not licensed for those packs, use dynamic performance views, the alert log, audit trails, application logs, and properly licensed monitoring tools.

## 10. Building a Multi-Source Timeline

A timeline is a list of events normalized to a single timezone, with each row containing a timestamp, source, related object/session, and confidence level.

### 10.1 Timeline Structure

| UTC time | Source | Event | Scope | Evidence ID | Confidence |
|---|---|---|---|---|---|
| 09:48:12Z | CI/CD | Release R2026.11.14.2 completed | API service | DEP-1821 | Verified |
| 09:52:04Z | Unified Audit | ALTER TABLE APP.ORDERS | APP.ORDERS | AUD-771 | Verified |
| 10:01:18Z | App log | Error rate begins to rise | orders-api | APP-2201 | Verified |
| 10:02:07Z | Alert log | ORA-00060 detected | DB instance 1 | ADR-031 | Verified |
| 10:04:30Z | DBA observation | Blocking chain captured | PDB SALES | SNAP-009 | Verified |

The times in this table are illustrative only. In practice, take them from their respective sources and specify the timezone clearly.

### 10.2 Determining the Start Point

Several milestones can be identified:

- First known bad: the earliest timestamp with evidence of failure.
- First customer impact: the earliest time a user was affected.
- Detection time: when monitoring or an operator detected the issue.
- Start of degradation: when metrics began diverging from baseline.
- Change time: when a deployment/configuration/DDL change occurred.

These milestones may differ. Do not use detection time in place of when the incident actually began.

### 10.3 Correlation IDs

Prioritize identifiers that link across systems:

- Request ID/trace ID from application logs.
- DB session SID/SERIAL# and INST_ID.
- SQL_ID/CHILD_NUMBER/PLAN_HASH_VALUE.
- Transaction XID/LTXID if available.
- Service, module, action, and client identifier.
- DBID, CON_ID, instance, host.
- SCN and redo thread/sequence.

Close timestamps alone without a linking identifier are insufficient to confirm that two events belong to the same request or transaction.

### 10.4 Confidence Classification

| Level | Criteria |
|---|---|
| High | Direct source, clear timestamp/identity, independently verifiable |
| Medium | Indirect source supported by at least one independent source |
| Low | Inferred from aggregated metrics, uncertain timestamp, or missing identity |
| Unknown | No data available or logs past retention |

## 11. Evidence Preservation and Chain of Custody

Investigation evidence must be re-verifiable. Do not edit original log files, do not overwrite copies, and do not simply paste fragments into chat while dropping metadata.

### 11.1 Maintain an Evidence Register

Each artifact should include:

| Field | Content |
|---|---|
| Evidence ID | Unique identifier |
| Source | Database view, ADR, listener, app log, CI/CD, OS |
| Original path/query | File path or SQL query used |
| Host/DB/instance/PDB | Where the data was captured |
| Collected by | Person or service account that collected it |
| Collected at | UTC timestamp and original offset if applicable |
| Time range | Time window covered by the content |
| Size/row count | File size or line/row count |
| SHA-256 | Hash of the original artifact |
| Redaction | Redacted content and reason |
| Storage location | Controlled storage location |

### 11.2 Hash Files to Verify Integrity

Linux:

~~~bash
sha256sum alert.log listener.log incident-trace.trc
~~~

Windows PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath 'C:\evidence\alert.log'
~~~

Record the hash, capture time, and path in the evidence register. If you create a redacted copy, hash the original and redacted versions separately; do not overwrite the original.

### 11.3 Save Database Query Results

When spooling SQL output:

- Record the exact SQL statement, redacted bind values, user, container, and execution time.
- Save column headings and row counts.
- Record timezone/session settings.
- Record any SQL errors; do not omit error output.
- Record DBID, instance, startup time, and current SCN.

SQL*Plus example:

~~~sql
SET ECHO ON
SET FEEDBACK ON
SET TIMING ON
SET LINESIZE 250
SET PAGESIZE 500
SPOOL incident_session_snapshot.txt

SELECT SYSTIMESTAMP AS collected_at,
       SYS_CONTEXT('USERENV', 'DB_NAME') AS db_name,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
       SYS_CONTEXT('USERENV', 'INSTANCE_NAME') AS instance_name
FROM dual;

SELECT current_scn FROM v$database;

SPOOL OFF
~~~

Do not include passwords, tokens, private keys, or unnecessary personal data in spool files.

### 11.4 Redaction and Sensitive Data

SQL text, bind values, traces, audit trails, and application logs may contain:

- Email addresses, phone numbers, physical addresses, or identifying information.
- Access tokens, session tokens, credentials.
- Financial data or customer data.
- Sensitive business literals in SQL.

Share only with authorized groups. When sharing outside the incident team is required, create a redacted copy and keep the original in a controlled evidence repository.

### 11.5 Retention and Access Control

Configure restricted read permissions, a retention period, encryption at rest/in transit, and an approved deletion process. Incident evidence can contain more sensitive information than routine operational logs.

## 12. Phased Incident Handling Procedure

### Phase A — Stabilize and Open Incident

1. Assign an incident ID and incident commander.
2. Record detection time, reporting system, and user symptoms.
3. Determine severity and which services are degraded/down.
4. Document containment actions taken or proposed.
5. Designate a single timeline standard (UTC).

### Phase B — Capture Initial State

1. Record DBID, DB_UNIQUE_NAME, role, open mode, version/RU.
2. Record instance, host, startup time, and PDB.
3. Record current SCN and timestamp.
4. Capture V$SESSION/GV$SESSION, wait events, blockers, and SQL_IDs.
5. Capture V$SQL/GV$SQL for relevant SQL statements.
6. Save alert logs, listener logs, ONS logs, and available traces.
7. Capture counter snapshots if delta comparisons are needed.

### Phase C — Isolate Scope

1. Identify service, instance, PDB, schema, and objects.
2. Compare affected nodes/instances with healthy ones.
3. Identify affected tenants, users, requests, data range, and time window.
4. Check open transactions, blockers, and dependencies.
5. Quantify failing requests, affected rows, and blast radius.

### Phase D — Reconstruct Recent Changes

1. Retrieve deployment/migration history.
2. Query DDL audit, GRANT/REVOKE, and user changes.
3. Compare parameters/SPFILE and service configuration.
4. Check object LAST_DDL_TIME, invalid objects, and dependencies.
5. Check statistics, scheduler jobs, and data loads.
6. Cross-check OS, storage, DNS, firewall, listener, and certificate changes.
7. Record each change with its source, actor, and confidence level.

### Phase E — Verify Hypotheses

1. Select the hypothesis that explains the most facts.
2. Look for independent supporting evidence.
3. Look for contradicting evidence or alternative explanations.
4. Compare against baselines and unaffected nodes/services.
5. Test in a safe environment if needed.
6. Confirm root cause only when evidence is sufficiently strong.

### Phase F — Remediate and Validate

1. Choose the smallest-scope action that meets the objective.
2. Record pre-change snapshots and approver.
3. Execute per runbook/change control.
4. Re-measure error rate, latency, waits, resource usage, and data correctness.
5. Verify there is no regression in other workloads.
6. Save post-change snapshots and document results.

### Phase G — Close Incident

1. Document the root cause or undetermined status.
2. Document the verified timeline.
3. Document impact scope and data needing verification/recovery.
4. Document remediation actions, rollback plan, and results.
5. Document follow-up actions, owners, and deadlines.
6. Preserve evidence per retention policy.

## 13. Incident Report Template

~~~text
Incident ID:
Severity:
Incident commander:
Database / DBID / DB_UNIQUE_NAME:
Database role / open mode:
Version / RU:
PDB / CON_ID:
RAC instances / service:
Application / module:

Time standard:
Database host timezone:
Application timezone:
Known clock drift:

First known bad (UTC):
First customer impact (UTC):
Detection time (UTC):
Containment time (UTC):
Recovery time (UTC):

Symptoms:
Scope:
Affected users / tenants:
Affected objects / data range:
SQL_ID / child / plan hash:
Session / XID / SCN:

Recent changes:
1.
2.
3.

Verified facts:
1.
2.
3.

Hypotheses:
1.
Evidence supporting:
Evidence against:

Containment:
Remediation:
Validation:
Data integrity check:

Evidence register:
1.
2.
3.

Root cause:
Contributing factors:
Unknowns:
Follow-up actions / owners / due dates:
~~~

## 14. Common Investigation Mistakes

| Mistake | Why It Is Dangerous | Better Practice |
|---|---|---|
| Using laptop time as the common reference | Hosts/sessions may have different timezones or clock drift | Standardize on UTC and record clock sources |
| Relying solely on timestamps | Timestamps may lack precision or logs may arrive delayed | Combine with SCN, XID, SQL_ID, and request ID |
| Treating LAST_DDL_TIME as an audit trail | Does not identify the actor or full DDL content | Combine Unified Audit, deployment logs, and source control |
| Treating ORA_ROWSCN as exact per-row time | May be block-level and does not record actor/SQL | Use Flashback Version Query and auditing |
| Treating V$SESSION as history | Disconnected sessions disappear from the view | Use ASH/audit/application logs if licensed/available |
| Treating V$SQL counters as last-run metrics | Counters accumulate per cursor | Take snapshots and calculate deltas |
| Treating missing audit records as no change | Policies may not be enabled or records may be purged | Check policies, retention, and other sources |
| Investigating only the database | Issues may originate from app, network, DNS, storage, or certificates | Cross-check all dependencies |
| Restarting before collecting evidence | Loses session state and in-memory counters | Capture first, contain per runbook |
| Fixing data before determining scope | May overwrite evidence or corrupt valid data | Build timeline and data range first |
| Running UNDO_SQL immediately | Reverse SQL may no longer match current state | Review transactions, dependencies, and test |
| Sending raw traces/logs externally | May expose sensitive data and credentials | Keep original under access control, share redacted copy |
| Merging RAC/PDB metrics | May misattribute instances or tenants | Preserve INST_ID, CON_ID, and service |

## 15. Lab: Building a Timeline from DDL and Data

This lab demonstrates saving timestamp/SCN markers, modifying a table, and observing LAST_DDL_TIME and row versions. Run it in a lab schema on a database that meets Flashback Version Query prerequisites.

### 15.1 Record Initial Marker

~~~sql
SELECT SYSTIMESTAMP AS captured_at,
       DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS captured_scn,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
       SYS_CONTEXT('USERENV', 'INSTANCE_NAME') AS instance_name
FROM dual;
~~~

Save the output to an evidence file along with the collection timestamp.

### 15.2 Create Table and Data

~~~sql
CREATE TABLE incident_timeline_lab (
    id          NUMBER PRIMARY KEY,
    status      VARCHAR2(20),
    amount      NUMBER
);
~~~

Wait at least 15 seconds after creating the table before running the transaction you want to observe with Flashback Version Query.

~~~sql
INSERT INTO incident_timeline_lab VALUES (1, 'NEW', 100);
INSERT INTO incident_timeline_lab VALUES (2, 'NEW', 200);
COMMIT;
~~~

### 15.3 Record SCN Before and After DML

~~~sql
SELECT SYSTIMESTAMP AS before_change_time,
       DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS before_change_scn
FROM dual;

UPDATE incident_timeline_lab
SET status = 'SHIPPED',
    amount = 125
WHERE id = 1;

COMMIT;

SELECT SYSTIMESTAMP AS after_change_time,
       DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS after_change_scn
FROM dual;
~~~

### 15.4 View Row Version History

~~~sql
SELECT versions_startscn,
       versions_endscn,
       versions_starttime,
       versions_endtime,
       versions_xid,
       versions_operation,
       id,
       status,
       amount
FROM incident_timeline_lab
VERSIONS BETWEEN SCN MINVALUE AND MAXVALUE
WHERE id = 1
ORDER BY versions_startscn;
~~~

The results show the row versions still available in undo. Record the XID, operation, and SCN of the version under investigation.

### 15.5 View Object Metadata

~~~sql
SELECT owner,
       object_name,
       object_type,
       created,
       last_ddl_time,
       status
FROM user_objects
WHERE object_name = 'INCIDENT_TIMELINE_LAB';
~~~

LAST_DDL_TIME illustrates the most recent DDL time of the object. The DML UPDATE in the previous step did not change LAST_DDL_TIME to the UPDATE time. This demonstrates that object metadata is not data change history.

### 15.6 Clean Up Lab

~~~sql
DROP TABLE incident_timeline_lab PURGE;
~~~

Run DROP only if this is the newly created lab table and contains no data that must be kept.

## 16. Incident Investigation Checklist

### Time

1. Are first known bad, detection, and customer impact times recorded?
2. Do timestamps include a timezone/UTC offset?
3. Have database host, application host, and collector clocks been cross-checked?
4. Is there any clock drift or log ingest delay?
5. Are current SCN and startup time recorded?

### Scope

1. Are DBID, DB_UNIQUE_NAME, role, and open mode identified?
2. Are PDB/CON_ID and RAC INST_ID identified?
3. Are service, host, application version, and module identified?
4. Are schema, object, partition, and data range identified?
5. Are SQL_ID, child cursor, plan hash, session, and XID identified?
6. Are affected users/tenants/requests quantified?

### Recent Changes

1. Have deployment and migration histories been retrieved?
2. Have DDL/audit trails been checked?
3. Have parameter/SPFILE/service changes been reviewed?
4. Have statistics and scheduler jobs been checked?
5. Have grants, users, roles, and credential rotations been checked?
6. Have OS, storage, DNS, firewall, listener, and TLS changes been cross-checked?

### Evidence

1. Have alert logs and traces been saved?
2. Have runtime sessions, waits, blockers, and SQL cursors been captured?
3. Have counter snapshots at two points in time been taken where deltas are needed?
4. Have audit/FGA and licensed historical sources been checked?
5. Have query, output, row count, timezone, and collection time been saved?
6. Have an evidence register and SHA-256 hashes been created?
7. Has sensitive data been redacted in shared copies?

### Conclusion and Actions

1. Are facts, inferences, hypotheses, and unknowns separated?
2. Is there independent evidence supporting the root cause?
3. Is there evidence refuting the hypothesis?
4. Was evidence preserved before state-destroying actions?
5. Have containment/remediation actions been approved?
6. Has data integrity been verified after remediation?
7. Have post-change evidence and follow-up owners been recorded?

## 17. Summary

An effective Oracle investigation procedure begins by aligning time and SCN, then defining scope across database/PDB/instance/service/application/object/data. Next, cross-reference deployments, DDL, parameters, statistics, jobs, security, and infrastructure changes. Evidence must be collected from runtime views, alert/trace logs, audits, Flashback, redo/archive logs, and application and infrastructure logs.

- Timestamps must include a timezone; SCN helps link the logical order of changes.
- Scope must preserve DBID, CON_ID, INST_ID, service, schema, object, SQL_ID, and XID when available.
- LAST_DDL_TIME, V$SESSION, and V$SQL are useful indicators but not complete histories.
- Auditing only proves events recorded by enabled policies; missing records do not prove an event did not happen.
- AWR/ASH are valuable for performance history, but licensing must be verified.
- Cumulative counters must be compared using snapshots/deltas within the same lifecycle.
- Original evidence must be preserved, registered, and integrity-checked with hashes.
- Root cause is confirmed only when the timeline and independent sources support it; unknowns must be explicitly stated.

The outcome of an investigation is not just an answer to "why did the database fail," but a re-verifiable timeline, a quantified impact scope, clearly sourced evidence, and a verifiable remediation plan.

## 18. Oracle References

- Oracle Database 19c Database Reference, “V$DATABASE”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-DATABASE.html
- Oracle Database 19c Database Reference, “V$INSTANCE”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-INSTANCE.html
- Oracle Database 19c Database Reference, “V$SESSION”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION.html
- Oracle Database 19c Database Reference, “V$DIAG_ALERT_EXT”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-DIAG_ALERT_EXT.html
- Oracle Database 19c Database Reference, “UNIFIED_AUDIT_TRAIL”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/UNIFIED_AUDIT_TRAIL.html
- Oracle Database 19c Database Reference, “SCN_TO_TIMESTAMP”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/SCN_TO_TIMESTAMP.html
- Oracle Database 19c Database Reference, “TIMESTAMP_TO_SCN”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/TIMESTAMP_TO_SCN.html
- Oracle Database 19c Database Reference, “V$UNDOSTAT”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-UNDOSTAT.html
- Oracle Database 19c Development Guide, “Using Oracle Flashback Technology”: https://docs.oracle.com/en/database/oracle/oracle-database/19/adfns/flashback.html
- Oracle Database 19c Administrator's Guide, “Managing Diagnostic Data”: https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-diagnostic-data.html
- Oracle Database 19c Database Reference, “V$ACTIVE_SESSION_HISTORY”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-ACTIVE_SESSION_HISTORY.html
- Oracle Database Licensing Information User Manual: https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/Licensing-Information.html
