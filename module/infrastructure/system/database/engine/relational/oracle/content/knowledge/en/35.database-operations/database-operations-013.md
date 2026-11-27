# Periodic Health Checks and Building Operational Runbooks

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Operations  
> **Objective:** Build a repeatable Oracle Database health-check schedule; monitor availability, capacity, performance, backup/recovery, high availability, security, and jobs; write runbooks with triggers, diagnostic steps, actions, verification, escalation, and rollback; and record evidence to detect trends before incidents impact users.

## 1. Health Checks and Runbooks Solve Two Different Problems

A **health check** is a scheduled observation activity to determine whether the database is operating normally, showing signs of anomaly, or trending toward resource exhaustion.

A **runbook** is a pre-prepared operational procedure for a specific scenario. A runbook answers: when to trigger, who owns it, what to verify, which actions are permitted, stop conditions, how to confirm recovery, and when to escalate.

The two complement each other:

- Health checks detect signals: FRA growing rapidly, tablespaces nearing capacity, backup jobs failing, Data Guard apply lag rising.
- Runbooks turn signals into action: verify root cause, assess impact, pick a safe remediation, verify outcomes, and document the incident.

A green dashboard cannot replace a recovery procedure. Likewise, a thorough runbook cannot help if monitoring fails to detect issues in time.

### 1.1. Health Check Scope

An Oracle operational check suite should cover at least the following categories:

| Category | Questions to Answer |
|---|---|
| Availability | Are the instance, database, services, and PDBs open in the expected state? |
| Capacity | Do data tablespaces, TEMP, UNDO, FRA, filesystems, and processes/sessions have enough headroom? |
| Performance | Are latency, throughput, CPU, I/O, waits, and SQL workloads abnormal? |
| Backup/recovery | Are backups completing, usable, and verified for restore/recovery? |
| High availability | Are RAC, Data Guard, service failover, and replication healthy? |
| Database objects | Are there INVALID objects, failed jobs, or abnormal constraints/indexes? |
| Security | Do accounts, privileges, auditing, credentials, and database links comply with policy? |
| Change/patch | Are versions, patches, parameters, and recent changes tracked? |
| Operations | Do alert logs, incidents, batches, schedulers, and capacity trends have assigned owners? |

Not every database uses RAC, Data Guard, multitenant, SecureFiles, or the same backup tool. Runbooks must clearly mark which sections apply and which do not apply to the target architecture.

## 2. Building a Cadence-Based Check Schedule

Not every query should run daily. Some checks must run continuously, while others are meaningful only when compared weekly or monthly.

| Cadence | Typical Scope | Objective |
|---|---|---|
| Continuous / alert-driven | Instance/service down, tablespace/FRA thresholds, critical job failure, Data Guard lag, prolonged blocking | Early incident detection |
| Per shift / daily | Database/PDB status, alert log, overnight backups, FRA/TEMP/UNDO, scheduler failures, active blockers | Start-of-shift health verification |
| Weekly | Capacity growth, top SQL trends, invalid objects, job duration, Data Guard transport/apply trends, account reviews | Trend identification |
| Monthly | Restore validation, DR readiness, patch inventory, privilege reviews, retention, capacity forecasts, runbook reviews | Operational risk reduction |
| Event-driven | Pre/post-patch, migration, data load, switchover, storage change | Safe change verification |

### 2.1. Defining Owners and Response SLAs

Each check needs:

- Primary owner: DBA, SRE, platform team, or application owner.
- Backup owner: delegate when the primary owner is unavailable.
- Frequency and execution schedule.
- Severity level.
- Acknowledgment and escalation deadlines.
- Where results are stored.
- Alert closure criteria.

Never assign ownership vaguely to "the DBA team." Every alert must have an assigned recipient, responsible group, and escalation contact when SLAs are breached.

### 2.2. Baselines and Alert Thresholds

No single percentage threshold fits every database. For example, 85% tablespace utilization may be acceptable if growth is slow and ample expansion space exists; 70% may be urgent if growing by tens of GB per hour and datafiles cannot autoextend.

Set thresholds based on:

- Current utilization.
- Growth rate.
- Available expansion capacity.
- Storage/quota/cloud service limits.
- Lead time needed for approval and expansion.
- RTO/RPO and business criticality.
- Batch schedules and peak seasons.

Maintain at least two levels: warning for proactive remediation and critical for urgent escalation. Record absolute values, percentages, and growth rates.

## 3. Preparing the Environment and Verification Privileges

Queries in this guide reference views such as V$DATABASE, V$INSTANCE, V$SESSION, V$SYSSTAT, DBA_TABLESPACES, and DBA_DATA_FILES. Operational accounts require appropriate privileges.

Principles:

- Use a dedicated monitoring account with read-only access to the required views.
- Do not use SYSDBA for routine application health checks.
- Separate read-only observability privileges from change-execution privileges.
- Grant catalog roles/dictionary read access per DBA policy; never grant SELECT ANY TABLE solely so a dashboard can read metadata.
- Record container, instance, and database role when running queries.
- In RAC, use GV$ views and keep INST_ID so instances are not mixed up.
- In CDB/PDB, record CON_ID or container name to know which container data belongs to.

Example identifying the database and instance:

~~~sql
SELECT name,
       dbid,
       database_role,
       open_mode,
       log_mode,
       protection_mode,
       protection_level
FROM v$database;

SELECT instance_name,
       host_name,
       version,
       startup_time,
       status,
       database_status
FROM v$instance;
~~~

Querying V$DATABASE describes database status and role; V$INSTANCE describes the current instance. In RAC, each instance has its own state.

### 3.1. Identifying the Current Container

~~~sql
SELECT sys_context('USERENV', 'DB_NAME') AS db_name,
       sys_context('USERENV', 'CON_NAME') AS con_name,
       sys_context('USERENV', 'CON_ID') AS con_id,
       sys_context('USERENV', 'SESSION_USER') AS session_user,
       sys_context('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

In multitenant setups, running queries in the root vs. a PDB can return different results. DBAs must know whether a query uses CDB_* views, local DBA_* views in the current container, or CONTAINER_DATA privileges. Never conclude "no data" while connected to the wrong container.

### 3.2. Identifying Version

~~~sql
SELECT banner
FROM v$version
ORDER BY banner;
~~~

Record the release, RU/patch level, and platform in the report. Dictionary columns, features, and management behaviors vary across releases.

## 4. Availability Checks

### 4.1. Instance and Database Open Mode

~~~sql
SELECT instance_name,
       status,
       database_status,
       logins,
       active_state,
       startup_time
FROM v$instance;

SELECT name,
       database_role,
       open_mode,
       log_mode,
       switchover_status
FROM v$database;
~~~

Key states to verify:

- Instance OPEN and database READ WRITE on primary when required by architecture.
- Standby may be READ ONLY WITH APPLY, MOUNTED, or another state depending on Data Guard mode.
- PDBs must be open in the mode required by services/applications.
- LOGINS may show RESTRICTED if the database is under maintenance.

Do not expect the exact same state across primary, physical standby, snapshot standby, and lab databases.

### 4.2. PDB Status

~~~sql
SELECT con_id,
       name,
       open_mode,
       restricted
FROM v$pdbs
ORDER BY con_id;
~~~

Cross-check each PDB against the list of services that must be active. An OPEN PDB alone does not guarantee applications can connect via the service; listener, service registration, network, and authentication must also be verified.

### 4.3. Services and Listeners

On the host, inspect using the appropriate Oracle Net/Clusterware utilities:

~~~text
lsnrctl status
lsnrctl services
srvctl status service -db <db_unique_name>
srvctl status database -db <db_unique_name>
~~~

SRVCTL commands apply in environments managed by Oracle Restart/Grid Infrastructure; option syntax can vary by release. Status commands are read-only checks. Do not run START/STOP/RELOCATE during routine health checks without change/incident authorization.

TNSping only verifies connect descriptor resolution and listener reachability per its protocol; it does not prove database login or query execution succeeds.

### 4.4. Application Connectivity Checks

From the actual application path, verify:

- DNS/connect descriptor.
- Listener and service name.
- Authentication.
- Whether the connection pool can check out a connection.
- Execution of a lightweight health query.
- PDB/service routing to the expected container.
- TLS/TCPS if mandated.
- Absence of connection pool waits or login storms.

Never simply ping the database host and mark the service healthy.

## 5. Checking Alert Logs and Incidents

The alert log records major events such as startup/shutdown, internal errors, checkpoints, redo/archiving, recovery, tablespace events, and operational warnings.

Using ADRCI on the host:

~~~text
adrci
show homes
set homepath <adr_home>
show alert -tail 100
~~~

The specific ADR home can be identified via ADRCI and Oracle configuration. You can also use Oracle Enterprise Manager or centralized logging systems to search by timestamp, instance, and incident.

### 5.1. Signals to Watch For

- ORA-00600, ORA-07445, or severe internal errors.
- ORA-01555 snapshot too old.
- ORA-01652 unable to extend temp segment.
- ORA-01653/ORA-01654 unable to extend table/index.
- ORA-19809/ORA-19804 related to FRA/recovery area.
- Archive destination errors or inability to write archives.
- Control file, redo log, or datafile errors.
- Unplanned startup/shutdown events.
- Data Guard gaps or apply errors.
- Critical jobs failing repeatedly.

A single ORA error is not always a widespread outage. Record timestamp, container, instance, SQL_ID, trace/incident ID, and actual impact before escalating.

### 5.2. The Alert Log Is Not the Only Log

Also inspect:

- Listener log.
- ASM/Clusterware alert logs in RAC/ASM.
- RMAN job output.
- Scheduler job logs.
- Application logs and connection pool logs.
- OS kernel/system logs.
- Storage/network telemetry.

Synchronize clocks across database hosts, application hosts, and monitoring systems. Skewed clocks lead to faulty event correlation.

## 6. Capacity Checks: Tablespaces and Datafiles

### 6.1. Tablespace Usage

An overview query for permanent tablespaces:

~~~sql
WITH df AS (
    SELECT tablespace_name,
           SUM(bytes) AS allocated_bytes,
           SUM(CASE
                   WHEN autoextensible = 'YES' THEN maxbytes
                   ELSE bytes
               END) AS configured_max_bytes
    FROM dba_data_files
    GROUP BY tablespace_name
),
fs AS (
    SELECT tablespace_name,
           SUM(bytes) AS free_bytes
    FROM dba_free_space
    GROUP BY tablespace_name
)
SELECT t.tablespace_name,
       ROUND(NVL(df.allocated_bytes, 0) / 1024 / 1024, 1) AS allocated_mb,
       ROUND(NVL(fs.free_bytes, 0) / 1024 / 1024, 1) AS free_mb,
       ROUND(
           (NVL(df.allocated_bytes, 0) - NVL(fs.free_bytes, 0))
           / NULLIF(df.allocated_bytes, 0) * 100,
           1
       ) AS used_pct_of_allocated,
       ROUND(NVL(df.configured_max_bytes, 0) / 1024 / 1024, 1) AS configured_max_mb
FROM dba_tablespaces t
LEFT JOIN df ON df.tablespace_name = t.tablespace_name
LEFT JOIN fs ON fs.tablespace_name = t.tablespace_name
WHERE t.contents = 'PERMANENT'
ORDER BY used_pct_of_allocated DESC NULLS LAST;
~~~

This provides an overview calculation. Inspect individual datafiles, autoextend settings, maxsize, bigfile/smallfile, quotas, and the storage layer separately. If datafiles have autoextend enabled while the filesystem/ASM disk group is out of space, expansion will still fail in practice.

### 6.2. Datafile and Autoextend Details

~~~sql
SELECT tablespace_name,
       file_id,
       file_name,
       ROUND(bytes / 1024 / 1024, 1) AS current_mb,
       autoextensible,
       ROUND(maxbytes / 1024 / 1024, 1) AS max_mb,
       increment_by
FROM dba_data_files
ORDER BY tablespace_name, file_id;
~~~

Compare datafile sizes against filesystem or ASM disk group free capacity. MAXBYTES is a configured datafile ceiling, not a guarantee that underlying storage can actually supply that space.

### 6.3. Free Space Can Be Fragmented

Total FREE_BYTES does not guarantee a single contiguous extent large enough in every segment/tablespace management scenario. With locally managed tablespaces and ASSM, Oracle manages extents/blocks with specific rules; inspect actual error messages, extent requirements, datafiles, and segment types before concluding.

### 6.4. User Quotas

~~~sql
SELECT username,
       tablespace_name,
       bytes,
       max_bytes
FROM dba_ts_quotas
ORDER BY username, tablespace_name;
~~~

A user can hit quota exceeded even when the tablespace still has plenty of free space. Check user quotas explicitly rather than checking total tablespace space alone.

## 7. Checking TEMP and UNDO

### 7.1. Current TEMP Usage

~~~sql
SELECT tablespace_name,
       ROUND(SUM(bytes_used) / 1024 / 1024, 1) AS used_mb,
       ROUND(SUM(bytes_free) / 1024 / 1024, 1) AS free_mb
FROM v$temp_space_header
GROUP BY tablespace_name
ORDER BY tablespace_name;
~~~

View sessions currently consuming temporary segments:

~~~sql
SELECT username,
       session_addr,
       session_num,
       sql_id,
       tablespace,
       segtype,
       blocks,
       extents
FROM v$tempseg_usage
ORDER BY blocks DESC;
~~~

TEMP growth may stem from sorts, hash joins, parallel queries, temporary tables, or temporary LOBs. Never diagnose a leak from a single snapshot; check SQL_ID, session details, and historical trends.

### 7.2. UNDO Pressure

~~~sql
SELECT begin_time,
       end_time,
       undoblks,
       txncount,
       maxquerylen,
       tuned_undoretention,
       ssolderrcnt,
       nospaceerrcnt
FROM v$undostat
ORDER BY begin_time DESC
FETCH FIRST 24 ROWS ONLY;
~~~

Key signals:

- Rising SSOLDERRCNT: snapshot too old errors occurred during the interval.
- Rising NOSPACEERRCNT: out-of-undo-space conditions recorded during the interval.
- High MAXQUERYLEN: long-running queries needing undo for read consistency.
- TUNED_UNDORETENTION: retention automatically tuned by Oracle under runtime conditions.

Do not blindly increase UNDO_RETENTION; inspect undo tablespace size, workload, retention guarantee, and storage expansion headroom.

### 7.3. When TEMP/UNDO Approaches Capacity

Before making changes:

1. Identify the tablespace, tempfile/datafile, and current utilization.
2. Locate top consuming SQL/sessions.
3. Inspect execution plans, sorts/hashes, parallelism, and runtime.
4. Confirm whether any session/job is abnormal or runaway.
5. Check filesystem/ASM headroom.
6. Choose remediation per change policy: tune SQL, adjust workload, add tempfile/space, or intervene on sessions with owner confirmation.
7. Monitor after the change.

Never drop tempfiles or kill sessions just to make a dashboard metric drop.

## 8. Fast Recovery Area and Archive Logs

The FRA stores recovery files such as archived redo logs, backup pieces, flashback logs, and control file autobackups depending on configuration.

~~~sql
SELECT name,
       ROUND(space_limit / 1024 / 1024 / 1024, 2) AS limit_gb,
       ROUND(space_used / 1024 / 1024 / 1024, 2) AS used_gb,
       ROUND(space_reclaimable / 1024 / 1024 / 1024, 2) AS reclaimable_gb,
       ROUND(space_used / NULLIF(space_limit, 0) * 100, 1) AS used_pct,
       number_of_files
FROM v$recovery_file_dest;
~~~

SPACE_RECLAIMABLE does not mean files can be arbitrarily deleted right away. Oracle manages retention, backup status, and file eligibility.

### 8.1. Archive Destinations

~~~sql
SELECT dest_id,
       status,
       target,
       destination,
       error,
       transmit_mode,
       affirm
FROM v$archive_dest
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
~~~

Check runtime status:

~~~sql
SELECT dest_id,
       status,
       type,
       database_mode,
       recovery_mode,
       error,
       destination
FROM v$archive_dest_status
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
~~~

Displayed columns and values depend on configuration and version. If a destination reports an error, verify storage, network, remote standby, quota, and specific error text before modifying parameters.

### 8.2. Redo Logs and Archive Generation

~~~sql
SELECT thread#,
       group#,
       sequence#,
       bytes,
       members,
       archived,
       status
FROM v$log
ORDER BY thread#, group#;
~~~

Check recent archives:

~~~sql
SELECT thread#,
       sequence#,
       first_time,
       next_time,
       archived,
       applied,
       status,
       deleted
FROM v$archived_log
WHERE first_time >= SYSDATE - 1
ORDER BY thread#, sequence#;
~~~

In RAC, multiple redo threads exist. Do not inspect thread 1 alone when the database has multiple instances.

Sudden spikes in log switch frequency may come from elevated redo generation, batch runs, index rebuilds, or transaction pattern changes. Correlate with workload and archive destinations.

### 8.3. Do Not Delete Archives with Filesystem Commands

Never delete archived redo logs directly via OS commands to free FRA space. Doing so desynchronizes the RMAN repository and can break recovery/Data Guard.

Use RMAN according to retention policies and approved procedures. Before deleting, verify backups, standby applied status if applicable, deletion policy, and PITR requirements.

## 9. Checking Backups and Recoverability

A successful backup job is only one signal. A database is truly protected only when data can be restored within required RTO/RPO targets.

### 9.1. Checking the RMAN Repository

In RMAN:

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> REPORT NEED BACKUP;
RMAN> SHOW ALL;
~~~

Verify:

- Database/datafile backups.
- Archived redo log backups.
- Control file/SPFILE autobackups.
- Backup status, completion time, and device type.
- Retention policy.
- Encryption wallet/key availability per policy.
- Off-site/object storage copies if required.

### 9.2. Checking Backup Jobs

Record results of every run:

- Job ID and start/end timestamps.
- Database/DBID and DB_UNIQUE_NAME.
- Backup type and level.
- Datafile/archive log coverage.
- RMAN exit status.
- Error stack.
- Size and throughput.
- Storage location and retention duration.

Do not rely on job scheduler SUCCESS alone. Verify RMAN output and backup piece availability.

### 9.3. Validating Backups

You can use RMAN to validate backups:

~~~text
RMAN> RESTORE DATABASE VALIDATE;
~~~

This checks readability of required backups per RMAN selection and repository metadata. It does not replace a full restore into an isolated environment and does not prove the full post-recovery application startup workflow.

Validation can generate significant I/O. Schedule it carefully, scope it appropriately, and monitor impact.

### 9.4. Restore Tests

On schedule, restore a backup to an isolated test environment:

1. Identify backup pieces and target recovery point.
2. Prepare compatible host/storage and Oracle software.
3. Restore control file/SPFILE per runbook.
4. Restore datafiles.
5. Recover to target SCN/time.
6. Open the database in the appropriate mode.
7. Verify objects, row counts, and application checks.
8. Measure actual elapsed time.
9. Record errors, dependencies, and per-step timings.

Only an actual restore test provides real evidence of RTO and operational readiness. Never test restoring over production.

### 9.5. RPO and RTO

- **RPO (Recovery Point Objective):** maximum acceptable data loss, measured in time or transaction point.
- **RTO (Recovery Time Objective):** maximum acceptable time to restore service.

Backup schedules, archive log backup frequency, Data Guard protection mode, storage replication, and restore procedures must satisfy these objectives.

## 10. Data Guard Health Checks

Applies only to Data Guard architectures. Confirm whether the database is PRIMARY, PHYSICAL STANDBY, LOGICAL STANDBY, or another role before evaluating.

### 10.1. Database Role and Protection

~~~sql
SELECT database_role,
       open_mode,
       protection_mode,
       protection_level,
       switchover_status
FROM v$database;
~~~

### 10.2. Transport Lag and Apply Lag

~~~sql
SELECT name,
       value,
       unit,
       time_computed,
       datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag', 'apply finish time');
~~~

Compare lag against SLA/RPO and workload. A stale lag value or un-updated DATUM_TIME can indicate stale monitoring data; never read VALUE in isolation.

### 10.3. Archive Gaps

~~~sql
SELECT thread#,
       low_sequence#,
       high_sequence#
FROM v$archive_gap;
~~~

V$ARCHIVE_GAP identifies gaps requiring attention on a physical standby. An empty result does not replace checking transport/apply status and the alert log.

### 10.4. Broker

If using Data Guard Broker:

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW DATABASE VERBOSE '<db_unique_name>';
~~~

Check configuration status, database status, transport/apply, warnings, and errors. DGMGRL provides clearer visibility into broker-managed configurations.

Do not run switchover/failover during a health check. Those are role-transition operations requiring dedicated runbooks, prechecks, approvals, client routing verification, and post-checks.

## 11. RAC and Clusterware Health Checks

Applies only if the database runs on RAC/Oracle Restart/Grid Infrastructure.

### 11.1. Cluster Instances

~~~sql
SELECT inst_id,
       instance_name,
       host_name,
       status,
       startup_time
FROM gv$instance
ORDER BY inst_id;
~~~

Inspect services:

~~~sql
SELECT inst_id,
       name,
       network_name,
       pdb
FROM gv$services
ORDER BY inst_id, name;
~~~

### 11.2. Clusterware Resources

On the host with appropriate privileges:

~~~text
crsctl stat res -t
srvctl status database -db <db_unique_name>
srvctl status service -db <db_unique_name>
~~~

Check database, instance, listener, ASM, disk group, and service resources. If a resource is OFFLINE/INTERMEDIATE, check dependencies and alert logs before restarting.

### 11.3. ASM Capacity

If using ASM, inspect disk groups:

~~~sql
SELECT name,
       state,
       type,
       total_mb,
       free_mb,
       usable_file_mb,
       required_mirror_free_mb
FROM v$asm_diskgroup
ORDER BY name;
~~~

USABLE_FILE_MB accounts for redundancy and mirror requirements; do not look only at FREE_MB. A disk group with raw physical free space but low usable space may still fail new allocations.

## 12. Performance Health Checks

Performance health checks must combine snapshots/deltas with workload context. Cumulative counters cannot be interpreted as instantaneous metrics.

### 12.1. System Time Model

~~~sql
SELECT stat_name,
       value
FROM v$sys_time_model
WHERE stat_name IN ('DB time', 'DB CPU')
ORDER BY stat_name;
~~~

Take start/end snapshots and compute the delta. DB time is total foreground database activity time; it can exceed wall-clock elapsed time when multiple sessions run concurrently.

### 12.2. System Statistics

~~~sql
SELECT name,
       value
FROM v$sysstat
WHERE name IN (
    'session logical reads',
    'physical reads',
    'physical writes',
    'redo size',
    'user commits',
    'execute count',
    'parse count (total)',
    'parse count (hard)'
)
ORDER BY name;
~~~

Compare deltas over matching intervals and equivalent workloads. In RAC, use GV$SYSSTAT and group by INST_ID.

### 12.3. Current Active Sessions

~~~sql
SELECT sid,
       serial#,
       username,
       sql_id,
       event,
       wait_class,
       state,
       seconds_in_wait,
       blocking_session,
       module,
       action
FROM v$session
WHERE type = 'USER'
  AND status = 'ACTIVE'
ORDER BY seconds_in_wait DESC;
~~~

V$SESSION is a current snapshot, not full history. Short-lived queries may finish between samples.

### 12.4. Resource Limits

~~~sql
SELECT resource_name,
       current_utilization,
       max_utilization,
       limit_value
FROM v$resource_limit
WHERE resource_name IN ('processes', 'sessions', 'transactions')
ORDER BY resource_name;
~~~

MAX_UTILIZATION tracks the high-water mark since instance startup or corresponding reset. Compare against LIMIT_VALUE and headroom; review processes/sessions sizing as load grows.

### 12.5. Top SQL by Resource Consumption

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       ROUND(elapsed_time / 1e6, 2) AS elapsed_seconds,
       ROUND(cpu_time / 1e6, 2) AS cpu_seconds,
       buffer_gets,
       disk_reads,
       rows_processed,
       last_active_time
FROM v$sql
WHERE executions > 0
ORDER BY buffer_gets DESC
FETCH FIRST 20 ROWS ONLY;
~~~

V$SQL statistics are generally cumulative per child cursor. Do not treat elapsed_time as the last execution's duration; dividing by executions yields only a coarse average that can hide tail latency or bind skew.

### 12.6. Runtime Plans

For a target SQL statement, capture runtime statistics in a test session:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       ...
FROM ...;
~~~

After fetching all rows:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

Compare E-Rows, A-Rows, Starts, Buffers, Reads, and A-Time. When Starts is greater than 1, check A-Rows/Starts before concluding estimates are wrong.

### 12.7. AWR, ASH, and SQL Monitor

AWR, ASH, ADDM, and certain SQL Monitor features belong to the Diagnostics/Tuning Packs under Oracle licensing terms. Verify entitlement before enabling or using them in production.

Without those licenses, rely on dynamic performance views, SQL Trace/TKPROF, OS metrics, application telemetry, and approved snapshot/deltas. Having SELECT privileges on a view does not automatically grant licensing rights to use pack-licensed features.

## 13. Scheduler Jobs and Maintenance Windows

### 13.1. Job Status

~~~sql
SELECT owner,
       job_name,
       enabled,
       state,
       last_start_date,
       next_run_date,
       failure_count,
       run_count
FROM dba_scheduler_jobs
ORDER BY owner, job_name;
~~~

### 13.2. Job Run Failures

~~~sql
SELECT owner,
       job_name,
       status,
       error#,
       actual_start_date,
       run_duration,
       additional_info
FROM dba_scheduler_job_run_details
WHERE log_date >= SYSTIMESTAMP - INTERVAL '7' DAY
  AND status <> 'SUCCEEDED'
ORDER BY log_date DESC;
~~~

Check:

- Are critical jobs ENABLED with the expected schedule?
- Did the last run succeed?
- Is duration trending abnormally upward?
- Is failure_count accumulating?
- Is the job overlapping with another batch or maintenance window?
- Are credentials, external jobs, and destinations still valid?
- Is the job running in the right PDB/service?

### 13.3. Maintenance Tasks

Review maintenance windows and automatic tasks per Oracle policy. Do not disable auto stats, advisors, or maintenance windows simply because they consume resources; inspect the task, schedule, and impact first.

If a job spills into peak hours, adjust its schedule via change control and verify impact on optimizer statistics/maintenance coverage.

## 14. Database Objects and Structure

### 14.1. Invalid Objects

~~~sql
SELECT owner,
       object_type,
       object_name,
       status,
       last_ddl_time
FROM dba_objects
WHERE status = 'INVALID'
ORDER BY owner, object_type, object_name;
~~~

View compilation errors:

~~~sql
SELECT owner,
       name,
       type,
       line,
       position,
       text
FROM dba_errors
ORDER BY owner, name, sequence;
~~~

Do not bulk-recompile invalid objects during peak hours without understanding dependencies and impact. Identify which application owns the object and whether a recent deployment occurred.

### 14.2. Unusable or Abnormal Indexes

~~~sql
SELECT owner,
       index_name,
       table_name,
       status,
       visibility,
       last_analyzed
FROM dba_indexes
WHERE status <> 'VALID'
ORDER BY owner, table_name, index_name;
~~~

For partitioned indexes, check partition/subpartition status:

~~~sql
SELECT index_owner,
       index_name,
       partition_name,
       status
FROM dba_ind_partitions
WHERE status <> 'USABLE'
ORDER BY index_owner, index_name, partition_name;
~~~

Status names/values can vary by index type and release. Do not automatically rebuild every flagged index; determine the root cause and required action first.

### 14.3. Disabled or Unvalidated Constraints

~~~sql
SELECT owner,
       table_name,
       constraint_name,
       constraint_type,
       status,
       validated
FROM dba_constraints
WHERE status <> 'ENABLED'
   OR validated <> 'VALIDATED'
ORDER BY owner, table_name, constraint_name;
~~~

Some constraints may be intentionally disabled during ETL loads. Compare against the deployment baseline and confirm with the owner before enabling/validating.

## 15. Security and Access Reviews

Security health checks should focus on changes and drift from policy.

### 15.1. Account Status

~~~sql
SELECT username,
       account_status,
       lock_date,
       expiry_date,
       profile,
       authentication_type
FROM dba_users
ORDER BY username;
~~~

Do not automatically unlock an account or reset a password solely because it is LOCKED. Check the owner, reason, audit trail, and identity process first.

### 15.2. Broad System Privileges

~~~sql
SELECT grantee,
       privilege,
       admin_option
FROM dba_sys_privs
WHERE privilege LIKE '%ANY%'
   OR privilege IN (
       'DBA',
       'SELECT ANY DICTIONARY',
       'BECOME USER',
       'EXEMPT ACCESS POLICY'
   )
ORDER BY grantee, privilege;
~~~

This is a review list, not an assertion that every returned grant is improper. Compare against the approved access matrix and check indirect grants via roles.

### 15.3. Roles and Object Grants

~~~sql
SELECT grantee,
       granted_role,
       admin_option,
       default_role
FROM dba_role_privs
ORDER BY grantee, granted_role;
~~~

~~~sql
SELECT owner,
       table_name,
       grantee,
       privilege,
       grantable
FROM dba_tab_privs
WHERE grantee IN ('PUBLIC', 'APP_USER', 'APP_READ', 'APP_WRITE')
ORDER BY grantee, owner, table_name, privilege;
~~~

Review PUBLIC grants, ANY privileges, GRANT OPTION, and nested roles against policy.

### 15.4. Auditing

If using Unified Auditing, inspect enabled policies and audit records within your privilege scope:

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       object_schema,
       object_name,
       return_code
FROM unified_audit_trail
WHERE event_timestamp >= SYSTIMESTAMP - INTERVAL '1' DAY
ORDER BY event_timestamp DESC;
~~~

Audit views can contain sensitive data; restrict read access and manage retention. Do not enable overly broad policies or log all SQL bind values without assessing storage and privacy impact.

## 16. Patch, Configuration, and Change Inventory

A health report should track:

- Oracle Database version and RU.
- OPatch inventory from the host.
- SQL patch registry.
- Non-default parameters.
- Component/option registry.
- DDL, index, statistics, and service changes.
- Deployment timestamp and operator.

### 16.1. SQL Patch Registry

~~~sql
SELECT patch_id,
       patch_type,
       action,
       status,
       action_time,
       description
FROM dba_registry_sqlpatch
ORDER BY action_time DESC;
~~~

Inspect STATUS, ACTION, and timestamps to verify patches applied at the SQL layer. Combine with OPatch inventory on the Oracle Home; the SQL registry does not replace the binary inventory.

### 16.2. Non-Default Parameters

~~~sql
SELECT name,
       value,
       isdefault,
       issys_modifiable,
       ispdb_modifiable
FROM v$parameter
WHERE isdefault = 'FALSE'
ORDER BY name;
~~~

Save before/after snapshots for every change. A non-default parameter may be an intentional production tuning setting; never reset parameters to default without knowing why they were set.

### 16.3. Component Registry

~~~sql
SELECT comp_id,
       comp_name,
       version,
       status
FROM dba_registry
ORDER BY comp_id;
~~~

INVALID components or inconsistent versions require DBA investigation before running repair scripts.

## 17. Building a Standardized Runbook Structure

Every runbook should follow a consistent template so on-call engineers can execute it reliably under pressure.

| Section | Contents |
|---|---|
| ID and title | Unique identifier and incident/procedure name |
| Purpose | Goal and expected outcome |
| Scope | Database, instance, PDB, service, environment |
| Trigger | Alert, metric, ticket, or triggering event |
| Severity | Level and business impact |
| Owner | Primary, backup, approver, escalation contacts |
| Preconditions | Privileges, backups, capacity, maintenance window |
| Diagnostics | Read-only queries/commands and interpretation |
| Actions | Ordered execution steps |
| Guardrails | Conditions under which you must stop |
| Validation | Evidence confirming recovery |
| Rollback | Reversal steps and when to invoke them |
| Communication | Who to notify and when |
| Evidence | Logs, SQL outputs, timestamps, ticket, change ID |
| Revision | Version, review date, approver |

### 17.1. Distinguish Observation Steps from Mutation Steps

Tag every command:

- **READ:** read-only status inspection.
- **CHANGE:** modifies configuration or metadata.
- **DISRUPTIVE:** can interrupt sessions/services or impact users.
- **RECOVERY:** data/instance/role recovery operation.

On-call operators must immediately see which commands merely observe and which alter the system. Never mix SELECT queries and ALTER SYSTEM statements into an automated health-check script.

### 17.2. Mandatory Preconditions for Risky Actions

Before any CHANGE/DISRUPTIVE/RECOVERY action, the runbook must require:

1. Confirming exact DB_UNIQUE_NAME, DBID, host, instance, and PDB.
2. Confirming the incident/change ticket and approver.
3. Confirming required backups/recovery points.
4. Checking primary/standby roles and RAC topology.
5. Checking dependencies and impacted users.
6. Capturing a pre-action state snapshot.
7. Defining stop conditions and rollback steps.
8. Obtaining peer review if required by policy.

Never execute an impactful command based on a single isolated alert.

## 18. Sample Runbook: Database/Service Unreachable

<badge color="warning">Incident runbook</badge>

**Trigger:** Application health check fails, listener/service stops responding, or database is not in its expected state.

**Objective:** Pinpoint the failing layer and restore connectivity in alignment with the architecture.

### Step 1 — Confirm Scope

- Only one application or all consumers?
- One PDB/service or the whole database?
- One instance or all RAC nodes?
- Only one network zone or everywhere?
- Any recent deployment, patch, failover, or network change?

### Step 2 — Check from the Application Side

- Connection pool state and timeouts.
- DNS/connect descriptor.
- Service name and credentials.
- Network/TLS.
- One lightweight health request.
- Timestamps and full error stack.

### Step 3 — Check Host/Listener

~~~text
lsnrctl status
lsnrctl services
~~~

In clustered environments, inspect SRVCTL/CRSCTL status per environment runbook.

### Step 4 — Check Database

If reachable using an operational account:

~~~sql
SELECT instance_name, status, database_status
FROM v$instance;

SELECT name, open_mode, database_role
FROM v$database;
~~~

If the database is not open, retrieve the alert log, traces, and host/storage status. Do not execute STARTUP/SHUTDOWN or restart resources before establishing current state and the appropriate recovery procedure.

### Step 5 — Action and Verification

Start/restart/relocate actions belong to authorized operators per architecture. Once service returns:

- Confirm database/PDB open mode is correct.
- Confirm listener service registration.
- Test connecting along the application path.
- Execute a lightweight health query.
- Check error rates and connection pool health.
- Monitor the alert log and session load.
- Record start time, recovery time, and root cause.

## 19. Sample Runbook: Tablespace or FRA Nearly Full

**Trigger:** Warning/critical threshold breach, unable to extend errors, or FRA approaching its limit.

### Step 1 — Identify the Resource

- Permanent tablespace, TEMP, UNDO, or FRA?
- Steady growth or sudden spike?
- Single datafile/tempfile or whole storage tier?
- Is autoextend enabled?
- Does filesystem/ASM still have usable space?
- Is a batch job, data load, index rebuild, or archive backlog running?

### Step 2 — Gather Evidence

Run the queries from the tablespace, TEMP/UNDO, and FRA sections. Capture two or more snapshots to measure growth rate.

### Step 3 — Identify Top Consumers

- Largest segments and growth rate.
- SQL/sessions consuming TEMP.
- Long-running UNDO transactions.
- Archive generation rate and destination errors.
- Backup/retention policies.
- Datafile maxsize and storage headroom.

### Step 4 — Select Remediation

Options may include tuning SQL, pausing/adjusting batch jobs with owner approval, expanding storage/datafiles/tempfiles, resolving archive destination issues, or adjusting retention per procedure.

Never delete archive/backup files with OS commands. Never shrink or drop datafiles just to silence an alert. Every storage change must verify capacity, filesystem/ASM headroom, and backup impact.

### Step 5 — Verify

- Free space increased or consumption rate dropped.
- No further unable to extend errors.
- FRA has headroom and archive destinations are VALID.
- Backup/recovery still satisfies retention.
- No adverse application impact.
- Record before/after capacity and root cause.

## 20. Sample Runbook: Blocking and Slow SQL

**Trigger:** Rising p95/p99 latency, request timeouts, prolonged blocking sessions, or abnormal CPU/I/O spikes.

### Step 1 — Identify Scope and SQL

Record SQL_ID, module/action, service, user, instance, plan hash, and timestamp.

### Step 2 — Inspect Blockers

~~~sql
SELECT sid,
       serial#,
       username,
       sql_id,
       event,
       wait_class,
       seconds_in_wait,
       blocking_instance,
       blocking_session,
       module,
       action
FROM gv$session
WHERE blocking_session IS NOT NULL
ORDER BY seconds_in_wait DESC;
~~~

In non-RAC environments, use V$SESSION and BLOCKING_SESSION. Trace the blocker chain, transaction age, and lock-holding SQL.

### Step 3 — Inspect SQL and Execution Plan

- Check V$SQL elapsed/CPU/buffer gets/disk reads.
- Gather DBMS_XPLAN runtime statistics when appropriate.
- Compare E-Rows/A-Rows/Starts.
- Inspect access/filter predicates.
- Correlate wait events with application traces.

### Step 4 — Take Action

First identify the transaction owner, query, lock scope, and business impact. Contact the application owner before terminating any session. Killing/disconnecting a session is disruptive; do so only per policy, with approval, and understanding rollback/transaction impact.

Never kill a session simply because it tops the active list or has a long elapsed time.

### Step 5 — Verify

- Blocking chain is cleared.
- Request latency/error rate returned to baseline.
- Transaction committed or rolled back cleanly.
- No new sessions recreating the same contention.
- Record SQL_ID, blocker, root cause, and action taken.

## 21. Sample Runbook: Backup Failed or Unproven Restore

**Trigger:** RMAN job failed, backup missing from repository, archive backups lagging, or restore test failed.

### Step 1 — Establish Recovery Objectives

- Database and DBID.
- RPO/RTO.
- Required recovery points.
- Primary/standby role.
- Backup destination and encryption dependencies.

### Step 2 — Check Repository/Output

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> REPORT NEED BACKUP;
RMAN> SHOW ALL;
~~~

Read the job log and error stack. Confirm datafile, control file, SPFILE, and archived redo coverage.

### Step 3 — Investigate Cause

- Storage/object store/network.
- Expired credentials/secrets.
- RMAN channel/device configuration.
- Full FRA.
- Archive destination errors.
- Expired/missing backup pieces.
- Encryption wallet/key availability.
- Retention/deletion policies.

### Step 4 — Controlled Retry

Do not retry blindly in an infinite loop. Confirm the cause is resolved, capacity is adequate, and retrying will not overload production. Record the new job ID and backup pieces.

### Step 5 — Verify Recoverability

Run appropriate validation during an approved window and maintain periodic restore tests. If a restore test fails, open an incident, evaluate real RPO/RTO exposure, and remediate before declaring the database protected.

## 22. Sample Runbook: Data Guard Lag or Archive Gap

**Trigger:** Transport/apply lag breaches SLA, standby stops applying redo, or broker reports WARNING/ERROR.

### Step 1 — Check Role and Data Freshness

~~~sql
SELECT database_role, open_mode, protection_mode
FROM v$database;

SELECT name, value, unit, time_computed, datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag');
~~~

### Step 2 — Check Transport and Gaps

- V$ARCHIVE_DEST_STATUS.
- V$ARCHIVE_GAP.
- Primary and standby alert logs.
- DGMGRL SHOW CONFIGURATION if using Broker.
- Network, storage, and archive destinations.

### Step 3 — Classify

- Transport lag: redo has not yet reached the standby.
- Apply lag: redo arrived on standby, but apply is behind.
- Archive gap: required log sequence(s) are missing.
- Stale datum: metrics have not updated recently.

### Step 4 — Take Action

Never delete archives, alter protection mode, defer destinations, or fail over on guesswork. Follow the version-, transport-mode-, broker-, and topology-specific Data Guard runbook. Escalate to the HA-responsible DBA if RPO is threatened.

### Step 5 — Verify

- Transport/apply lag back within thresholds.
- Gaps resolved.
- Broker configuration reports SUCCESS if applicable.
- Standby role/open mode is accurate.
- Client/service routing and protection level confirmed.

## 23. Sample Runbook: Critical Job Failed

**Trigger:** Critical Scheduler job fails to start, terminates with FAILED, or exceeds expected duration.

1. Identify owner, job name, schedule, last start, next run, and failure_count.
2. Read DBA_SCHEDULER_JOB_RUN_DETAILS and additional_info.
3. Check credentials, destinations, privileges, dependencies, and resource pressure.
4. Check whether the job collided with another batch or maintenance window.
5. Inspect input data and checkpoint/idempotency state.
6. Retry only after confirming retrying is safe and will not produce duplicate side effects.
7. If disabling/enabling/running the job is needed, record change/incident and owner approval per policy.
8. Confirm job success, row counts, business reconciliation, and downstream completion.

Never treat SUCCEEDED status alone as sufficient if the job failed to process the expected rows or business data.

## 24. Severity, Escalation, and Communication

An example severity matrix:

| Level | Examples | Response |
|---|---|---|
| SEV1 / Critical | Production database down, suspected data corruption, RPO threatened, primary/standby protection lost | Open incident bridge, engage DBA lead and service owner immediately |
| SEV2 / High | Critical service severely degraded, FRA/tablespace near full, critical backup failed, lag past RPO guardrail | Acknowledge urgently, assign owner, provide frequent updates |
| SEV3 / Medium | Failed job with workaround, capacity warning with remaining headroom, localized SQL regression | Handle within shift, monitor, and plan remediation |
| SEV4 / Low | Trend warnings, unused invalid objects, routine cleanup/reviews | Log ticket and schedule normally |

Thresholds and response SLAs must be defined by the organization per SLA. Do not use this sample table in place of official incident policy.

### 24.1. Incident Update Contents

Each update should include:

- User and system impact.
- Start/detection time.
- Scope across database/service/PDB/instance.
- What is confirmed vs. still hypothesized.
- Current actions and owner.
- RPO/RTO risk.
- Time of next update.

Avoid posting credentials, secrets, raw personal data, or sensitive bind values in tickets/chat.

### 24.2. Incident Closure Criteria

Close only when:

- Service is confirmed operational from the application perspective.
- Error rates and latency have returned to acceptable levels.
- Backup/HA protection is verified if impacted.
- No unresolved critical alerts remain.
- Root cause or next investigation owner is recorded.
- Evidence and timeline are archived.
- Follow-up actions have owners and due dates.

## 25. Saving Evidence and Building Dashboards

Every health check should store a timestamped snapshot recording database, instance, container, and operator/automation identity.

Suggested schema fields:

| Field | Example |
|---|---|
| captured_at | 2026-11-14T20:00:00+07:00 |
| db_unique_name | PRODDB |
| dbid | DBID value |
| instance | PRODDB1 |
| con_name | APP_PDB |
| check_id | FRA_CAPACITY |
| status | OK / WARN / CRITICAL |
| observed_value | 72.4 |
| threshold | 80 |
| unit | percent |
| trend | +3.2 percentage points/day |
| owner | DBA_ON_CALL |
| ticket | Incident/change reference |

Do not store only the latest point-in-time value. Trends reveal when the FRA or a tablespace will fill up before thresholds are breached.

### 25.1. Role-Based Dashboards

- DBA: instances, tablespaces, FRA, backups, waits, SQL, jobs.
- Application owner: endpoint latency, errors, throughput, connection pools.
- Service owner: availability, RTO/RPO, incidents, capacity forecasts.
- Security: account/privilege/audit drift, patch status.
- Management: SLAs, trends, risks, remediation due dates.

### 25.2. Data Retention and Telemetry Protection

Retain enough history for trend comparisons and incident forensics under a defined retention policy. Restrict read access because SQL text, modules, client identifiers, and audit records may contain sensitive information.

## 26. Sample Daily Health Check Report

~~~text
ORACLE DAILY HEALTH REPORT
Date/time:
Database / DB_UNIQUE_NAME:
DBID:
Instance(s):
PDB / Service:
Role: PRIMARY / STANDBY
Oracle version / RU:
Operator / Automation run ID:

1. AVAILABILITY
   Instance status:
   Database open mode / role:
   PDB status:
   Listener / service:
   Application connectivity:
   Result: OK / WARN / CRITICAL

2. CAPACITY
   Permanent tablespace:
   TEMP:
   UNDO:
   FRA:
   ASM/filesystem:
   Processes/sessions headroom:
   Growth trend:
   Result:

3. PERFORMANCE
   DB time / DB CPU delta:
   Throughput:
   p95 / p99 application latency:
   Top SQL:
   Wait/blocking:
   I/O and redo:
   Result:

4. BACKUP / RECOVERY
   Last full/incremental backup:
   Archived redo coverage:
   RMAN status:
   Validation / restore-test date:
   RPO/RTO status:
   Result:

5. HIGH AVAILABILITY
   RAC resources:
   Data Guard transport/apply lag:
   Archive gap:
   Broker status:
   Result:

6. JOBS / OBJECTS
   Critical scheduler failures:
   Invalid objects:
   Unusable indexes/partitions:
   Maintenance task:
   Result:

7. SECURITY / CHANGE
   Account/privilege drift:
   Audit alerts:
   Patch/config change:
   Result:

OPEN ITEMS
- Finding:
- Impact:
- Owner:
- Ticket:
- Due date:
- Escalation:
~~~

## 27. Frequency-Based Operational Checklists

### Continuous / Alert-Driven

- [ ] Instance/database/service down.
- [ ] Critical PDB closed or unexpectedly restricted.
- [ ] Tablespace/FRA/TEMP/ASM threshold breached.
- [ ] Archive destination error.
- [ ] Data Guard lag/gap exceeds guardrail.
- [ ] Critical backup failure.
- [ ] Prolonged blocking/deadlocks.
- [ ] Application error rate/latency breaches SLO.

### Daily

- [ ] Confirm database role and open mode.
- [ ] Confirm PDB/service/listener and application connectivity.
- [ ] Review alert log and new incidents.
- [ ] Check RMAN jobs and archived redo coverage.
- [ ] Check FRA, tablespaces, TEMP, and UNDO.
- [ ] Check scheduler failures.
- [ ] Check active blockers and resource limits.
- [ ] Check Data Guard/RAC if applicable.
- [ ] Save health report and assign owners to warnings.

### Weekly

- [ ] Analyze capacity growth and forecasts.
- [ ] Review top SQL by elapsed time, CPU, and buffer gets.
- [ ] Review p95/p99 and throughput trends.
- [ ] Check invalid objects and index states.
- [ ] Review job duration and failure trends.
- [ ] Review Data Guard lag and standby health.
- [ ] Check user/role/privilege drift.
- [ ] Review alert noise and threshold effectiveness.

### Monthly / Per Maintenance Cycle

- [ ] Restore/validate backups per schedule.
- [ ] Verify RTO/RPO via drills.
- [ ] Review patch/RU inventory and vulnerability advisories.
- [ ] Review capacity forecasts and storage procurement.
- [ ] Review privileged access, database links, and credential rotation.
- [ ] Review audit policies and log retention.
- [ ] Review runbooks, contacts, and escalation trees.
- [ ] Audit change records and post-change performance.
- [ ] Verify monitoring coverage and alert delivery.

## 28. Operational Safety Principles

1. Verify exact database, DBID, DB_UNIQUE_NAME, host, instance, PDB, and role before every action.
2. Start by observing and collecting evidence; never alter state just to make an alert disappear.
3. Never run disruptive commands without confirming impact, owner, approval, and rollback.
4. Never delete datafiles, redo logs, archive logs, backup pieces, or FRA files using OS commands.
5. Never kill sessions solely for long runtime; identify the transaction and application owner first.
6. Never restart databases/listeners/ASM or relocate services during routine health checks.
7. Never alter Data Guard protection mode, switchover, or failover outside the HA runbook.
8. Never disable constraints, triggers, auditing, or maintenance tasks as a quick symptom workaround.
9. Never grant broad privileges just to make a monitoring query work; grant least-privilege read access.
10. Never place passwords, wallet secrets, tokens, or sensitive data into scripts, tickets, or reports.
11. Use maintenance windows and change records for impactful operations.
12. After every action, verify both database health and application experience.

## 29. Designing Runbooks That Anyone Can Execute

A good runbook must be clear enough for another on-call DBA to execute without guesswork.

- Use actual database/service/PDB names in the environment-specific runbook.
- Place configuration variables at the top rather than hardcoding hosts/credentials throughout.
- Specify minimum privileges required for each step.
- Clearly label read-only commands vs. state-changing commands.
- Provide expected output or evaluation criteria.
- Explicitly state stop/abort conditions.
- Include checkpoints after each critical step.
- Document rollback commands and side effects.
- Link relevant monitoring/dashboards/tickets in internal documentation.
- Record Oracle version and last runbook test date.
- Review after every incident, patch, or topology change.

### 29.1. Testing Runbooks

Before marking a runbook production-ready:

1. Have someone other than the author read and execute it in a lab environment.
2. Verify every query and command matches the target release and privileges.
3. Simulate trigger conditions.
4. Confirm expected outputs.
5. Test stop/escalation steps.
6. Test rollback or restore in a safe environment.
7. Measure execution duration.
8. Clarify any ambiguous phrasing.
9. Periodically review owners/contacts and dependencies.

Never test a runbook by intentionally causing an outage or filling up production storage.

## 30. Core Takeaways

- Health checks detect current state and trends; runbooks guide controlled actions.
- Cover availability, capacity, performance, backup/recovery, HA, jobs, objects, security, and change inventory.
- Split schedules into continuous alerts, daily, weekly, monthly, and event-driven checks.
- Every check needs an owner, cadence, thresholds, escalation path, and recorded evidence.
- Never apply one universal percentage threshold across all databases; weigh growth rate, headroom, storage limits, and response lead time.
- Distinguish primary/standby, RAC/non-RAC, and CDB/PDB when interpreting status.
- V$SYSSTAT, V$SYS_TIME_MODEL, and V$SQL contain cumulative counters; use snapshots/deltas with workload context.
- Tablespaces, TEMP, UNDO, FRA, and ASM are distinct resource types; identify top consumers before expanding or cleaning up.
- Backup SUCCESS does not prove recoverability; validate and run scheduled restore tests.
- Never delete archives/backups with OS commands; use RMAN and retention/deletion policies.
- Data Guard transport lag differs from apply lag; inspect datum freshness, archive gaps, and broker status.
- AWR/ASH/SQL Monitor and certain tuning features require licenses; verify entitlement.
- Scheduler job SUCCESS must be cross-checked against business results and processed row counts.
- Security reviews must audit accounts, privileges, roles, auditing, and database links under least privilege.
- Runbooks require triggers, preconditions, diagnostics, actions, guardrails, validation, rollback, owners, and evidence.
- Start with read-only diagnostics; all disruptive operations require approval and change/incident procedures.
- Post-change, confirm database, service, and application recovery together; archive the timeline and root cause.

### Oracle Reference Documentation

- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/) — Database lifecycle, tablespaces, datafiles, redo, archive, users and maintenance.
- [Oracle Database Backup and Recovery User's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/) — RMAN backup, validation, restore, recovery and retention.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — V$DATABASE, V$INSTANCE, V$SESSION, V$RECOVERY_FILE_DEST, V$UNDOSTAT and dictionary views.
- [Oracle Data Guard Concepts and Administration](https://docs.oracle.com/en/database/oracle/oracle-database/19/sbydb/) — Transport/apply, role transition, broker and standby monitoring.
- [Oracle Real Application Clusters Administration and Deployment Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/racad/) — RAC, services, instances and Clusterware operations.
- [Oracle Database Security Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/) — Users, roles, auditing and privilege management.
- [Oracle Database Licensing Information User Manual](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/) — Diagnostics Pack and Tuning Pack licensing.

Dictionary columns, utility syntax, HA features and licensing terms can vary by release and deployment. Confirm the exact Oracle version, topology, privileges and support contract; test operational commands and restore procedures in a representative non-production environment before relying on them during an incident.
