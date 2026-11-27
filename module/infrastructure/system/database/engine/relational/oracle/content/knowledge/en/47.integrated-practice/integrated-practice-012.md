# Finalizing a Runbook with Architecture Diagrams, Monitoring Metrics, and Test Evidence

An Oracle Database runbook is truly usable during an incident only when the on-call engineer understands how the system runs, knows which signals to monitor, can follow step-by-step procedures in order, and can prove that recovery procedures have been tested. A document that merely lists SQL commands or claims “backups succeeded” is not enough to operate a production system.

A complete runbook connects four pillars:

1. **Architecture diagrams:** depicting applications, databases, storage, backups, standbys, networks, monitoring, and failure domains.
2. **Monitoring metrics:** specifying each metric, data source, sampling interval, alert thresholds, recipients, and next actions.
3. **Operational procedures:** detailing pre-checks, execution steps, verification, rollback/escalation paths, and exit criteria.
4. **Test evidence:** archiving environment details, configurations, executed steps, actual outcomes, timestamps, logs, query outputs, and sign-offs.

This lesson uses Oracle Database 19c as its primary example. The concepts apply equally to newer releases, RAC, Data Guard, multitenant architectures, and on-premises or cloud deployments. Service names, views, privileges, Broker commands, and monitoring settings must be verified against the real environment before entering a production runbook.

## 1. Objectives and Scope of a Runbook

A runbook is an operational manual for DBAs, SREs, application operators, infrastructure teams, and incident responders. Every procedure must answer:

- When should it be executed?
- Who is authorized to execute it and who approves it?
- Which systems, databases, and services are impacted?
- Which preconditions must be verified before starting?
- In what order must steps be executed?
- What is the expected outcome?
- Which metrics, logs, or queries confirm success?
- If any step fails, where do you stop, roll back, or escalate—and to whom?
- What evidence must be archived for audits and future improvements?

### 1.1. Example Scope

A reference system may consist of:
- Java/API applications and connection pools.
- Primary Oracle Database.
- Oracle Data Guard standby at a separate site.
- Storage for datafiles, online redo logs, and control files.
- Fast Recovery Area (FRA).
- RMAN backups on independent storage.
- Monitoring, alerting, log collection, and ticketing.
- DNS/service discovery, load balancers, and network firewalls.

Not every system has a standby or RAC. A runbook must explicitly state which components actually exist and mark inapplicable procedures. Never retain sample diagrams that do not match the live topology.

### 1.2. Defining Operational States

| State | Meaning | Action |
| --- | --- | --- |
| Healthy | Components operate within SLOs | Continue routine monitoring |
| Warning | Metrics drift from baseline without breaching incident thresholds | Investigate trends, increase observation frequency |
| Degraded | A component failed or redundancy is reduced | Open an incident, assess risk, and restore redundancy |
| Critical | Service outage or data-loss risk exceeding policy | Activate incident commander and DR procedures |
| Recovering | Actively restoring, failing over, or recovering workload | Track recovery steps and capture evidence |
| Closed | Service stabilized, data reconciled, incident owned | Finalize report and action items |

A database being `OPEN` does not guarantee the entire service is Healthy. Check services, PDBs, listeners, application connections, storage, standbys, and backups.

## 2. Overall Architecture Diagram

Diagrams must illustrate request flow, redo flow, backup flow, and telemetry flow. Use logical names consistent with the inventory, such as `APP_SERVICE`, `ORCL_PRD`, `ORCL_STBY`, and `FRA`.

~~~mermaid
flowchart LR
    U[Users and batch clients] --> LB[Load balancer or API gateway]
    LB --> APP[Application nodes]
    APP --> POOL[JDBC connection pools]
    POOL --> SVC[Oracle database service]
    SVC --> PRI[(Primary database)]
    PRI --> STG[Datafiles and online redo storage]
    PRI --> FRA[(Fast Recovery Area)]
    PRI -->|Redo transport| STBY[(Data Guard standby)]
    PRI -->|RMAN backup| BKP[(Independent backup storage)]
    PRI --> MET[Metrics and alert collection]
    APP --> APM[Application logs and traces]
    MET --> OBS[Monitoring dashboard and alert manager]
    APM --> OBS
    STBY --> MET
    BKP --> CAT[Backup catalog and inventory]
    OBS --> ONCALL[On-call and incident process]
~~~

### 2.1. Failure Domains to Capture

Production diagrams must show:
- Site or availability zone of primary and standby.
- Storage arrays, ASM disk groups, or cloud volumes hosting datafiles.
- Storage/FRA and backup repositories.
- Network routes linking primary, standby, applications, and backups.
- DNS, listeners, service names, and load balancers.
- Whether the monitoring plane and log aggregation share failure domains.
- Access paths for DBAs, OS admins, secret stores, and key management.

If primary and backups reside on the same storage array or site, a single storage or site outage can destroy both. A backup is truly independent only when failure domains and deletion permissions are properly isolated.

### 2.2. Recovery Decision Flow Diagram

~~~mermaid
flowchart TD
    A[Incident detected] --> B{Primary database usable?}
    B -->|Yes| C{Datafiles healthy?}
    B -->|No| D{Standby available and eligible?}
    C -->|Yes| E[Resolve service or SQL issue]
    C -->|No| F[RMAN restore and recover]
    D -->|Yes| G[Validate lag and DR approval]
    D -->|No| H[Restore from independent backup]
    G --> I[Switchover or failover]
    F --> J[Open and validate database]
    H --> J
    I --> K[Validate new primary and application]
    E --> L[Monitor and reconcile]
    J --> L
    K --> L
    L --> M[Capture evidence and close incident]
~~~

This diagram shows conceptual decision paths only. Failover decisions must rely on Data Guard state, redo gaps, RPO, primary reachability, formal approvals, and specific DR runbooks. Never trigger failover just because a dashboard turns red.

## 3. Architecture Inventory and Required Metadata

Every environment requires a versioned inventory with an owner. Never place IP addresses, passwords, or secrets directly in Markdown; reference secret vaults or CMDB entries by ID.

| Group | Fields to Record | Illustrative Example Values |
| --- | --- | --- |
| Environment | Environment, region, site | PROD / site-a |
| Database | `DB_NAME`, `DB_UNIQUE_NAME`, `DBID` | `ORCL` / `ORCL_PRD` / inventory reference |
| Release | Oracle version, RU, `COMPATIBLE` | Specific 19c RU |
| Topology | Single instance/RAC, CDB/PDB | 2-node RAC, CDB with `APP_PDB` |
| Role | `PRIMARY`/`PHYSICAL STANDBY` | `PRIMARY` |
| Service | Service name, PDB, preferred/available instances | `APP_SERVICE` |
| Network | Listener, SCAN, VIP, DNS, port | Per CMDB |
| Storage | ASM disk groups, volumes, mounts, capacity | `DATA`, `FRA` |
| Backup | RMAN device, repository, retention, encryption | Disk/SBT, recovery catalog |
| DR | Standby `DB_UNIQUE_NAME`, transport mode, apply mode | `ORCL_STBY` |
| Security | Wallet/keystore, credential vault reference | Secret IDs |
| Monitoring | Metric sources, dashboards, alert routes | Observability project |
| Ownership | DBA, app owner, storage, network, security | Team/on-call reference |

### 3.1. Collecting Database Metadata

~~~sql
SELECT
    name,
    dbid,
    db_unique_name,
    open_mode,
    database_role,
    log_mode,
    protection_mode,
    current_scn
FROM v$database;
~~~

Version and SQL patch level:

~~~sql
SELECT banner
FROM v$version
ORDER BY banner;

SELECT
    patch_id,
    patch_type,
    action,
    status,
    action_time,
    description
FROM dba_registry_sqlpatch
ORDER BY action_time DESC;
~~~

Inspect instances:

~~~sql
SELECT
    instance_name,
    host_name,
    version,
    status,
    database_status,
    startup_time
FROM v$instance;
~~~

In RAC, query `GV$` views and retain `INST_ID` to observe each instance's state.

### 3.2. Keeping the Inventory Updated

Update the inventory whenever you:
- Add or remove instances, PDBs, services, or standbys.
- Modify listeners, SCAN, DNS, firewalls, or network routes.
- Change storage, ASM disk groups, FRA, or backup targets.
- Upgrade Oracle Home, RU, or `COMPATIBLE`.
- Change retention, encryption, keystores, or backup catalogs.
- Update owners, on-call rotations, escalations, or access privileges.

Every update must carry an effective date, author, and ticket/change ID. Mark obsolete diagrams clearly so on-call responders never follow outdated maps.

## 4. RACI and Execution Authority

A runbook should not grant unilateral authority to an on-call responder for operations impacting data integrity or DR.

| Activity | On-Call DBA | Incident Commander | App Owner | Infrastructure | Security |
| --- | --- | --- | --- | --- | --- |
| Investigate database alerts | R | I | C | C | I |
| Restart application pool | C | A | R | C | I |
| Modify database parameters | R | A | C | C | I |
| RMAN restore/recover | R | A | C | C | C |
| Data Guard failover | R | A | C | C | I |
| Storage/network repair | C | A | I | R | I |
| Grant emergency access/recovery secrets | C | A | I | C | R |
| Reconcile data post-recovery | R | A | R | C | I |
| Close incident | C | A | R | C | C |

R = Responsible, A = Accountable, C = Consulted, I = Informed. Organizations must fill in actual team names, on-call contacts, escalation channels, and backups. This matrix is a template, not a default assignment.

### 4.1. Least Privilege

- Application users hold only required object privileges.
- Monitoring accounts have read-only access to approved views and metrics.
- RMAN operators hold backup/restore privileges scoped by role.
- `SYSDBA` is used strictly when required by procedure.
- OS accounts managing Oracle Home and storage are separate from application accounts.
- Secrets, wallets, and encryption keys are retrieved from an audited secret manager.
- Failover and service-management privileges are role-restricted.

Never place passwords, wallet passwords, private keys, or connection strings containing credentials into runbooks, log evidence, or shared screenshots.

## 5. RPO, RTO, SLOs, and Recovery Criteria

### 5.1. RPO

Recovery Point Objective is the maximum tolerable data loss. RPO must be measured as the gap between the last recoverable data timestamp and the time of the incident.

Examples:
- 5-minute RPO: the recovery point must be no older than 5 minutes.
- Zero RPO for certain committed transactions: requires architectural guarantees on commit/redo synchronization, which cannot be inferred from RMAN backup frequency alone.

### 5.2. RTO

Recovery Time Objective is the maximum time allowed from service disruption until the service is restored to a defined operational level.

RTO must define exact start and end markers:
- Start: incident confirmation or first failing health check?
- End: database `OPEN`, service accepting connections, or business transactions succeeding?
- Does it include DNS/cache propagation, application warm-up, and data reconciliation?

### 5.3. Operational SLOs

Examples of organizationally approved SLOs:
- Business transaction success rate.
- API P95/P99 response latency.
- Database availability.
- Maximum redo apply lag.
- Age of most recent backup.
- Recovery duration demonstrated in drills.

Do not use one blanket SLO across all services. Specify measurement windows, request classes, maintenance exclusions, and telemetry sources.

### 5.4. Targets and Drill Results

| Metric | Illustrative Target | Drill Result | Pass Condition |
| --- | --- | --- | --- |
| RPO | 5 minutes | Fill after test | Actual loss does not exceed target |
| RTO | 60 minutes | Fill after test | Service business-ready within target |
| Standby apply lag | 60 seconds | Fill after test | Within policy at role transition |
| Backup age | Per backup schedule | Fill after test | Complete recovery chain exists |
| Restore validation | Monthly schedule | Fill after test | All required files and redo readable |
| Application smoke tests | 100% critical tests | Fill after test | Zero critical failures |

Targets above are illustrative templates for runbook construction; replace them with real commitments. Never mistake illustrative numbers for production SLAs.

## 6. Catalog of Metrics to Monitor

Organizing metrics by layer helps responders quickly isolate issues across application, database, storage, network, standby, or backups.

| Layer | Metrics | Primary Source | Impact |
| --- | --- | --- | --- |
| Application | Request rate, error rate, P95/P99 latency | APM / API gateway | Are end users affected? |
| Connection pool | Active/idle/waiting, timeouts, borrow latency | JVM / pool metrics | Can the app acquire connections? |
| Database | Availability, active sessions, DB time, CPU | `V$INSTANCE`, `V$SYSMETRIC` | Is the database serving? |
| SQL | Top SQL, elapsed time, buffer gets, executions | AWR/ASH per privileges and licensing | Which queries drive load? |
| Concurrency | Blocking sessions, lock waits, deadlocks | `V$SESSION`, alert log | Are transactions blocked? |
| Storage | Tablespace, ASM, filesystems, IOPS/latency | DBA views and OS/storage monitoring | Risk of running out of space or slow I/O |
| Recovery | FRA, archive destinations, redo generation | `V$RECOVERY_FILE_DEST`, `V$ARCHIVE_DEST_STATUS` | Ability to archive and recover |
| Backup | Last successful backup, duration, bytes, validation | `V$RMAN_BACKUP_JOB_DETAILS` | Can we restore? |
| Data Guard | Transport lag, apply lag, gaps, role | `V$DATAGUARD_STATS`, `V$ARCHIVE_DEST_STATUS` | RPO and DR readiness |
| Security | Failed logons, privilege changes, audit events | Unified audit / monitoring | Access risk |
| Platform | Host CPU, memory, filesystems, network | OS / cloud monitoring | Infrastructure outside database |

### 6.1. Availability and Role

~~~sql
SELECT
    name,
    open_mode,
    database_role,
    log_mode,
    protection_mode,
    switchover_status
FROM v$database;
~~~

~~~sql
SELECT
    instance_name,
    host_name,
    status,
    database_status,
    logins,
    active_state
FROM v$instance;
~~~

For CDBs:

~~~sql
SELECT
    name,
    open_mode,
    restricted
FROM v$pdbs
ORDER BY name;
~~~

A CDB may be `OPEN` while an application PDB is closed or its service is unregistered. Dashboards must track both PDB and service readiness.

### 6.2. System Metrics

~~~sql
SELECT
    metric_name,
    value,
    metric_unit,
    begin_time,
    end_time
FROM v$sysmetric
WHERE metric_name IN (
    'Database CPU Time Ratio',
    'Database Wait Time Ratio',
    'Average Active Sessions',
    'Executions Per Sec',
    'Physical Reads Per Sec',
    'Redo Generated Per Sec',
    'User Transaction Per Sec',
    'Current Logons Count'
)
ORDER BY metric_name, end_time DESC;
~~~

`V$SYSMETRIC` exposes metrics by sampling interval. Metrics can appear across multiple interval groups; collectors must filter on the intended interval/group and never sum or mix short and long intervals.

### 6.3. Waiting and Blocking Sessions

~~~sql
SELECT
    sid,
    serial#,
    username,
    status,
    blocking_session_status,
    blocking_instance,
    blocking_session,
    wait_class,
    event,
    seconds_in_wait,
    sql_id
FROM v$session
WHERE blocking_session IS NOT NULL
   OR (status = 'ACTIVE' AND wait_class <> 'Idle')
ORDER BY seconds_in_wait DESC;
~~~

In RAC, query `GV$SESSION` and include `INST_ID`. Do not treat every wait as an error; inspect duration, wait class, SQL, blocking chains, and business transaction impact.

### 6.4. Tablespace Usage

~~~sql
WITH free_space AS (
    SELECT tablespace_name, SUM(bytes) AS free_bytes
    FROM dba_free_space
    GROUP BY tablespace_name
),
file_space AS (
    SELECT
        tablespace_name,
        SUM(bytes) AS allocated_bytes,
        SUM(
            CASE
                WHEN autoextensible = 'YES' THEN maxbytes
                ELSE bytes
            END
        ) AS potential_max_bytes
    FROM dba_data_files
    GROUP BY tablespace_name
)
SELECT
    f.tablespace_name,
    ROUND(f.allocated_bytes / 1024 / 1024) AS allocated_mb,
    ROUND(NVL(s.free_bytes, 0) / 1024 / 1024) AS free_mb,
    ROUND(
        (f.allocated_bytes - NVL(s.free_bytes, 0))
        / NULLIF(f.allocated_bytes, 0) * 100,
        1
    ) AS used_allocated_pct,
    ROUND(
        (f.allocated_bytes - NVL(s.free_bytes, 0))
        / NULLIF(f.potential_max_bytes, 0) * 100,
        1
    ) AS used_potential_max_pct
FROM file_space f
LEFT JOIN free_space s
    ON s.tablespace_name = f.tablespace_name
ORDER BY used_allocated_pct DESC;
~~~

This query covers permanent datafiles. `TEMP` tablespaces, undo, bigfile tablespaces, PDBs, and autoextend policies need dedicated dashboard queries. Always monitor underlying filesystem/ASM capacity as well, because autoextend cannot exceed physical storage.

### 6.5. TEMP Usage

~~~sql
SELECT
    tablespace_name,
    ROUND(tablespace_size / 1024 / 1024) AS tablespace_mb,
    ROUND(allocated_space / 1024 / 1024) AS allocated_mb,
    ROUND(free_space / 1024 / 1024) AS free_mb
FROM dba_temp_free_space;
~~~

If `TEMP` spikes abnormally, identify the consuming sessions and SQL, sort/hash spills, parallel queries, and duration. Never just grow tempfiles without finding the root cause.

### 6.6. Fast Recovery Area

~~~sql
SELECT
    name,
    ROUND(space_limit / 1024 / 1024 / 1024, 2) AS limit_gb,
    ROUND(space_used / 1024 / 1024 / 1024, 2) AS used_gb,
    ROUND(space_reclaimable / 1024 / 1024 / 1024, 2) AS reclaimable_gb,
    number_of_files,
    ROUND(space_used / NULLIF(space_limit, 0) * 100, 1) AS used_pct
FROM v$recovery_file_dest;
~~~

Track FRA growth rate, archived log generation rate, and reclaimable space. Reclaimable space does not mean files can be deleted directly via OS commands; RMAN and FRA manage files according to retention and backup policies.

### 6.7. Archive Destinations

~~~sql
SELECT
    dest_id,
    status,
    type,
    destination,
    error,
    gap_status,
    synchronization_status
FROM v$archive_dest_status
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
~~~

Columns may vary by release and configuration; verify the view definition on your target. Alert if a destination reports `ERROR`, exhibits a gap, or falls behind synchronization policy.

### 6.8. Data Guard Lag

~~~sql
SELECT
    name,
    value,
    unit,
    time_computed,
    datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag', 'apply finish time');
~~~

Run on the standby as documented by Oracle. Missing values or stale `datum_time` timestamps are themselves signals to investigate. Cross-check Broker status, archive gaps, and alert logs before declaring a standby healthy.

### 6.9. RMAN Backup History

~~~sql
SELECT
    session_key,
    input_type,
    status,
    start_time,
    end_time,
    elapsed_seconds,
    output_bytes_display,
    output_device_type
FROM v$rman_backup_job_details
ORDER BY start_time DESC
FETCH FIRST 30 ROWS ONLY;
~~~

A completed job does not by itself prove restorability. Verify backup pieces, archived redo coverage, control file autobackups, encryption keys, and validation/restore drills.

### 6.10. Invalid Objects

~~~sql
SELECT
    owner,
    object_type,
    COUNT(*) AS invalid_count
FROM dba_objects
WHERE status = 'INVALID'
GROUP BY owner, object_type
ORDER BY invalid_count DESC;
~~~

Track invalid-object baselines before and after releases. Not every `INVALID` object is an incident; some objects may be intentionally invalid or compiled on demand. Distinguish newly invalidated objects, critical objects, and genuine compilation errors.

## 7. Alert Thresholds and Avoiding False Positives

Thresholds must be calibrated to baseline behavior, capacity, workload, RPO/RTO, and response capability. The numbers below are starting points for designing alerts, not mandatory Oracle defaults.

| Metric | Illustrative Warning | Illustrative Critical | First Action |
| --- | --- | --- | --- |
| Tablespace used | Above 80% | Above 90% or projected full within ops window | Check growth, free space, autoextend, and storage |
| FRA used | Above 80% | Above 90% or archiving stalled | Check reclaimable space, backups, and archive dests |
| Data Guard apply lag | Above 30 seconds | Exceeding RPO or > 5 minutes per policy | Check transport/apply, network, and standby workload |
| Backup age | Approaching next scheduled run | Exceeds RPO or broken recovery chain | Check RMAN jobs, media, and archived logs |
| Blocking | Blocking longer than 30 seconds | Critical transaction blocked > 2 minutes | Identify blocker, SQL, and business owner |
| API error rate | Above baseline | Breaches SLO / critical transaction failure | Correlate APM, pools, and DB |
| API P95 latency | Above baseline across multiple intervals | Sustained SLO breach | Analyze traces and SQL |
| Invalid objects | Increase over baseline | Critical package/view invalid | Check compile errors and recent releases |
| Archive destination | Signs of slowdown/gap | `STATUS = ERROR` or unable to archive | Check storage, network, and alert log |
| Host storage | Projected full within maintenance window | Filesystem/ASM nearly full | Expand or reclaim per procedure |

### 7.1. Use Multi-Condition Rules Instead of Single Data Points

Effective alerts generally require:
- Breaching the threshold across multiple consecutive samples.
- Minimum sustained duration.
- Suppression during registered maintenance windows.
- Hysteresis (recovery threshold lower than alert threshold) to prevent flapping.
- Correlation with error rates, queue depth, or user impact.
- Explicit owner, severity, and runbook link.

For instance, 85% tablespace utilization can be normal when autoextend headroom is ample and growth is slow; 70% can be critical if rapid batch growth will fill the volume before the next maintenance window.

### 7.2. Capacity Forecasting

Track daily and weekly growth rates:

~~~text
days_to_full = usable_capacity_remaining / average_daily_growth
~~~

Use both average growth and high-percentile peak rates. If storage grows in batch spikes, forecasting solely by long-term averages underestimates exhaustion risk.

## 8. Operational Dashboards

A primary dashboard should organize panels into clear sections:

| Dashboard Section | Contents | Question Answered |
| --- | --- | --- |
| Service health | API success, errors, latency, availability | Are users impacted? |
| Database state | Role, open mode, instances, PDBs, services | Is the database available? |
| Load | DB time, AAS, CPU, transactions, executions | Is load spiking abnormally? |
| Waits/concurrency | Blocking, top waits, deadlocks | Is there contention? |
| Capacity | Tablespaces, `TEMP`, undo, FRA, ASM/filesystems | Is anything nearing exhaustion? |
| Recovery | Backup age, backup status, archive gaps | Can we recover? |
| Data Guard | Role, transport/apply lag, gaps | Does DR meet RPO? |
| Changes | Releases, RUs, invalid objects, deployments | Did anything change recently? |
| Evidence | Last restore drill, test result, runbook version | Is recoverability proven? |

### 8.1. Per-Service Dashboards

Do not display only database-wide metrics. If a CDB hosts multiple PDBs or services, break down by:
- Service name.
- PDB.
- Instance.
- Application module/action.
- Business transaction.
- Database user/schema.

Use `MODULE`, `ACTION`, and `CLIENT_IDENTIFIER` from the application to correlate SQL and sessions with business requests wherever feasible. Never put PII or secrets into client identifiers.

### 8.2. AWR/ASH and Licensing

AWR, ASH, and certain Diagnostic/Tuning Pack features carry licensing requirements. Verify organizational licensing before embedding pack queries or reports into runbooks. You can use `V$SYSMETRIC`, `V$SESSION`, SQL monitoring, or approved observability tools per your privileges and licenses.

## 9. Daily Operational Procedures

### 9.1. Start-of-Shift Checks

1. Review service health dashboards and active alerts.
2. Confirm database roles/open modes, instances, and PDBs.
3. Inspect alert log errors since the previous handover.
4. Check tablespace, `TEMP`, FRA, and ASM/filesystem utilization.
5. Check archive destinations and Data Guard lag.
6. Check the latest RMAN jobs and backup age.
7. Check for newly invalidated objects.
8. Confirm ongoing changes or maintenance windows.
9. Record timestamp, on-call engineer, and status in the shift log.

### 9.2. End-of-Shift Handover

- Document unresolved alerts and owners.
- Document long-running transactions/jobs or unusual storage growth.
- Document backup/standby issues and remediation deadlines.
- Document changes executed, command logs, and tickets.
- Hand over open incidents with clear severity and next actions.
- Confirm acknowledgment from the incoming engineer.

### 9.3. Sample Shift Log

~~~text
Date/time (timezone):
Environment / DB_UNIQUE_NAME:
Current role / open mode:
On-call owner:
Service health:
Active incidents:
Backup last success:
Archive / FRA status:
Data Guard lag:
Capacity risks:
Changes in progress:
Actions performed:
Next action / due time:
Evidence references:
Handover accepted by:
~~~

## 10. Database Unavailable Runbook

### Triggers

- Application fails to connect to the database service.
- Database health checks fail continuously.
- Listener/service unregistered.
- Database or instance not in serving state.
- Application PDB or service is closed.

### Procedure

1. Confirm blast radius via APM, API metrics, and multiple clients.
2. Check DNS, network routes, listener, and service registration.
3. Connect as DBA through approved administrative channels.
4. Inspect `V$INSTANCE`, `V$DATABASE`, and PDB states.
5. Read the alert log / ADR for the earliest error.
6. Check storage, ASM, filesystems, FRA, and archive destinations.
7. Isolate whether the fault lies in database, instance, service, host, or network.
8. If the instance is up, restore the service or PDB per approved procedures.
9. If the database cannot recover at the primary site, initiate DR decision-making.
10. Once the service returns, run application smoke tests and reconcile transactions.

### Evidence to Preserve

- Timestamps of first detection and confirmation.
- Relevant alert logs and incident traces.
- Instance, database, PDB, and service query outputs.
- Network and listener checks.
- Timestamp when the service resumed accepting connections.
- Post-recovery API success/error rates and P95 latency.
- Business transaction test results.
- Measured end-to-end RTO.

Never restart a database repeatedly before reading the alert log; repeated restarts can destroy diagnostic evidence and prolong recovery.

## 11. Tablespace / FRA / Archive Destination Near Full Runbook

### Triggers

- Tablespace or FRA exceeds alert threshold.
- Archive destination reports `ERROR`.
- Database cannot archive redo logs or sessions stall.
- Filesystem or ASM runs out of free capacity.

### Procedure

1. Identify affected container, tablespace, datafiles, destinations, and filesystems/ASM disk groups.
2. Check growth rate and projected time to exhaustion.
3. Check autoextend settings, `maxbytes`, and physical storage headroom.
4. Check RMAN retention, backup status, and archived log coverage.
5. Identify reclaimable files via Oracle/RMAN metadata.
6. Choose an approved action: expand storage/datafiles, adjust backup destinations, or clean up via RMAN.
7. Never delete archived logs or backup pieces directly via OS commands.
8. Monitor archiving resumption and FRA utilization stabilization.
9. Confirm zero remaining archive-related errors.
10. Record before/after utilization and root cause of growth.

### Verification Queries

~~~sql
SELECT
    name,
    space_limit,
    space_used,
    space_reclaimable,
    number_of_files
FROM v$recovery_file_dest;
~~~

~~~sql
SELECT
    dest_id,
    status,
    destination,
    error
FROM v$archive_dest
WHERE status <> 'INACTIVE';
~~~

All backup deletions must comply with retention and recovery policies. Verify sufficient backup copies and archived redo coverage before deleting inputs.

## 12. Blocking Session Runbook

### Triggers

- Business transactions stall for extended durations.
- Connection pools exhaust due to hung sessions.
- Lock waits rise and API latency breaches SLOs.

### Procedure

1. Identify impacted requests/transactions and business severity.
2. Capture the blocking chain, `SID`/`SERIAL#`, and `INST_ID` in RAC.
3. Collect `SQL_ID`, module, action, username, and wait duration.
4. Determine whether the blocker is a batch job, DDL, or deployment.
5. Contact the application owner if the blocker belongs to an app transaction.
6. Prefer letting the transaction complete or letting the app resolve per policy.
7. Terminate a session only after assessing rollback time, data impact, and approvals.
8. Monitor lock waits, active sessions, and API latency afterward.
9. Archive SQL, session identifiers, timestamps, and approvers.

Never kill a session blindly just because it sits at the head of a blocking tree. That session may be executing a critical transaction whose rollback could take longer than letting it finish.

## 13. Backup Failure and Recovery Verification Runbook

### Triggers

- RMAN job `FAILED` or `COMPLETED WITH WARNINGS`.
- Backup age exceeds schedule.
- Backup pieces inaccessible.
- Missing control file autobackup or archived log backup.
- `RESTORE VALIDATE` fails.

### Procedure

1. Save full RMAN logs and job keys.
2. Identify input type, channel, device, piece, and first error.
3. Check storage, media manager, credentials, and encryption wallet.
4. Check archived log sequence and thread coverage.
5. Check control file autobackup and SPFILE backups.
6. Fix root cause and re-run required backups.
7. Run `LIST BACKUP` and `CROSSCHECK` per procedure.
8. Run `RESTORE PREVIEW`/`VALIDATE` across the target scope.
9. Schedule a full restore drill if the backup chain was disrupted.
10. Update backup age/RPO status and the incident ticket.

### RMAN Verification Commands

~~~text
SHOW ALL;
LIST BACKUP SUMMARY;
LIST BACKUP OF DATABASE;
LIST BACKUP OF CONTROLFILE;
LIST BACKUP OF SPFILE;
LIST BACKUP OF ARCHIVELOG ALL;
RESTORE DATABASE PREVIEW;
RESTORE DATABASE VALIDATE;
~~~

`RESTORE VALIDATE` verifies that RMAN can read the backup pieces it expects to use. It does not replace restoring the database onto an isolated host and running application tests.

## 14. Data Guard Lag and DR Readiness Runbook

### 14.1. Investigating Lag

1. Verify primary and standby roles.
2. Capture transport lag and apply lag with timestamps.
3. Check archive destinations, gaps, and network health.
4. Check standby redo logs and managed recovery status.
5. Inspect standby storage, CPU, and I/O.
6. Read Broker status and alert logs on both sites.
7. Isolate whether lag stems from transport, apply throughput, or primary workload spikes.
8. Compare lag against RPO; notify owners if RPO breach threatens.
9. Record the exact time lag returns to normal.

### 14.2. Planned Switchover

Before switchover:
- Confirm change window and approvals.
- Confirm both primary and standby are healthy.
- Confirm transport/apply have zero policy-violating gaps.
- Verify standby readiness for role transition.
- Verify application connection strings and service routing.
- Confirm backups and rollback/reversal plans.
- Notify application owners.

Use Data Guard Broker when configured. Illustrative DGMGRL commands:

~~~text
SHOW CONFIGURATION;
SHOW DATABASE VERBOSE '<standby_db_unique_name>';
VALIDATE DATABASE VERBOSE '<standby_db_unique_name>';
SWITCHOVER TO '<standby_db_unique_name>';
SHOW CONFIGURATION;
~~~

Exact commands and validation options depend on Broker version and configuration. Execute only after verifying `DB_UNIQUE_NAME`, roles, states, and approvals.

After switchover:
- Confirm swapped roles on both databases.
- Confirm services and PDBs are open and registered.
- Confirm application pools connect to the new primary site.
- Run business smoke tests.
- Verify redo transport and apply in the reverse direction.
- Record start/end timestamps and measured RPO/RTO.

### 14.3. Unplanned Failover

Failover risks losing data not yet transported or applied to the standby. The incident commander and DBA must assess:
- Is the primary completely unreachable?
- Does the standby have a redo gap?
- What are the Data Guard protection mode and transport state?
- What actual RPO can be guaranteed?
- Is there any split-brain risk from the old primary still serving?
- Can the old primary be reinstated or must it be rebuilt?

Never invoke failover as a shortcut for fixing routine listener or service errors. Follow rehearsed DR runbooks with documented approvals.

## 15. Database Restore/Recover Runbook

### 15.1. Pre-Restore Prerequisites

- Confirm `DBID`, `DB_UNIQUE_NAME`, and target SCN/timestamp.
- Confirm required backup pieces and archived redo logs exist.
- Locate control file/SPFILE backups or staging PFILE.
- Confirm passwords/keystores for encrypted/TDE backups.
- Prepare Oracle Home and target storage.
- Verify file-name mappings, ASM disk groups, or OMF settings.
- Confirm recovery catalog and autobackup format.
- Isolate the restored database from live production services.
- Confirm approvers and business owners.

### 15.2. Restore/Recover Flow

~~~mermaid
flowchart TD
    A[Identify incident and recovery target] --> B[Locate DBID, control file and SPFILE]
    B --> C[Verify backup pieces and keys]
    C --> D[Prepare host, Oracle Home and storage]
    D --> E[Restore control file and mount]
    E --> F[Restore datafiles]
    F --> G[Apply archived redo to target]
    G --> H[Open according to recovery path]
    H --> I[Validate files, objects and application]
    I --> J[Record RPO/RTO and evidence]
~~~

### 15.3. Illustrative RMAN Commands

~~~text
STARTUP MOUNT;
RESTORE DATABASE;
RECOVER DATABASE;
ALTER DATABASE OPEN;
~~~

This represents the general flow when the current control file and recovery path allow it. When restoring a control file from backup or performing incomplete recovery/PITR, opening may require `RESETLOGS`. Choose the exact procedure for your state; never run `OPEN RESETLOGS` indiscriminately.

### 15.4. Post-Restore Checks

- Verify database role, open mode, and incarnation.
- Verify all datafiles are online and read-write as expected.
- Check invalid objects and compilation errors.
- Check sequences, scheduler jobs, database links, and credential dependencies.
- Verify PDBs and services.
- Run sample business transactions.
- Reconcile data against checkpoints.
- Take a fresh post-recovery backup per policy.
- Re-sync Data Guard or replication if present.

## 16. Testing Plan and Evidence

Every test case must have an ID, objective, prerequisites, execution steps, expected result, actual result, and evidence reference. Mark `PASS` only after evidence has been archived.

### 16.1. Test Matrix

| Test ID | Group | Objective | Expected Result | Evidence |
| --- | --- | --- | --- | --- |
| DB-AV-01 | Availability | Connect to service/PDB | Login and health query succeed | SQL output, app log |
| DB-AV-02 | Availability | Planned instance restart | Instance/service returns within RTO | Alert log, timestamps |
| DB-BK-01 | Backup | RMAN database backup | Job finishes, pieces cataloged | RMAN log, `LIST BACKUP` |
| DB-BK-02 | Backup | Control file/SPFILE autobackup | Readable autobackup present | RMAN log, backup listing |
| DB-BK-03 | Backup | Restore validation | All required backup pieces readable | RMAN validate log |
| DB-RC-01 | Recovery | Restore database on lab host | Database opens and business tests pass | Restore log, smoke tests |
| DB-RC-02 | Recovery | Point-in-time recovery | Recovers to target SCN/timestamp | RMAN log, SCN query |
| DB-DG-01 | Data Guard | Redo transport/apply | Lag within target, zero gaps | Broker output, lag metrics |
| DB-DG-02 | DR | Rehearsed switchover | Roles/services swap cleanly, app works | Broker log, app tests |
| DB-CAP-01 | Capacity | Tablespace/FRA alerts | Alert fires with right severity and owner | Alert event, dashboard |
| DB-PERF-01 | Performance | Peak workload | Latency/throughput within SLO | APM report, DB metrics |
| DB-SEC-01 | Security | Least privilege | Users lack out-of-scope privileges | Grant report, audit |
| DB-CHG-01 | Change | Apply RU in staging | Components valid, regression passes | Patch inventory, test report |
| DB-APP-01 | Application | Critical business flow | Create/read/update/commit succeed | API trace, SQL evidence |

### 16.2. Evidence Package

A test evidence package should contain:
- Test ID and test case version.
- Environment, `DB_UNIQUE_NAME`, release/RU, `COMPATIBLE`.
- Host, instance, PDB, and service.
- Start and end timestamps with timezone.
- Executor and reviewer.
- Change or ticket ID.
- Preconditions and test dataset details.
- Commands and scripts executed.
- Expected versus actual results.
- Exit codes and complete logs.
- Query outputs and metric snapshots.
- Screenshots or dashboard permalinks where helpful.
- File checksums and artifact storage paths.
- `PASS`/`FAIL`/`BLOCKED` status with rationale.
- Defect/incident links and retest references.

Never archive only green screenshots. Evidence must allow another engineer to reproduce or independently verify the result.

### 16.3. Test Report Template

~~~text
TEST ID:
Test name:
Runbook version:
Environment:
DB_UNIQUE_NAME / PDB / Service:
Oracle release / RU / COMPATIBLE:
Host / Instance:
Change or incident ID:
Executor:
Reviewer:
Start time (timezone):
End time (timezone):
Preconditions:
Test data:
Steps and commands:
Expected result:
Actual result:
Metrics before:
Metrics during:
Metrics after:
Log/artifact references:
Checksum:
Result: PASS / FAIL / BLOCKED
Defect or follow-up:
Approval:
~~~

### 16.4. Evidence Naming Convention

Use a predictable layout free of secrets:

~~~text
<environment>/<year>/<month>/<test-id>/<run-id>/
    metadata.txt
    commands.log
    database-state.txt
    metrics-before.csv
    metrics-during.csv
    metrics-after.csv
    application-smoke-test.log
    rman-output.log
    broker-status.log
    screenshots/
    checksums.sha256
~~~

Store artifacts in an approved evidence repository, object storage, or test management system. The runbook itself stores only references—never embed database dumps or personal data.

## 17. Measuring RPO and RTO During Drills

### 17.1. Actual RPO

Record:
- Timestamp of the last committed transaction confirmed on primary before the fault.
- Last timestamp/SCN present and recoverable on the target.
- Data Guard transport/apply lag or archive sequences.
- Post-recovery reconciliation results.

Actual RPO is the delta between the last confirmed pre-incident data point and the last recovered data point. For business workloads, verify transaction IDs or business sequence numbers rather than relying purely on SCNs.

### 17.2. Actual RTO

Break RTO down into milestones:
1. Detection.
2. Triage and declaration.
3. Decision and approval.
4. Database recovery or role transition.
5. Service and network routing.
6. Application warm-up.
7. Business validation.
8. Service declared restored.

Record every timestamp. Doing so reveals whether bottlenecks sit in waiting for approval, restoring datafiles, applying redo, DNS TTLs, connection pools, or validation.

### 17.3. Timeline Template

| Milestone | Timestamp | Elapsed Since Incident | Evidence |
| --- | --- | --- | --- |
| Alert fired | Fill in | 0 | Monitoring event |
| Incident declared | Fill in | Fill in | Ticket |
| Recovery approved | Fill in | Fill in | Approval record |
| Database available | Fill in | Fill in | SQL health query |
| Service available | Fill in | Fill in | Listener/service check |
| Application smoke tests pass | Fill in | Fill in | API test |
| Business owner accepts | Fill in | Fill in | Sign-off |
| Incident closed | Fill in | Fill in | Post-incident report |

## 18. Performance and Capacity Testing

### 18.1. Baselines

Collect baselines across:
- Normal workload.
- Peak workload.
- Batch windows.
- Backup windows.
- Reporting/ETL windows.
- Maintenance and recovery drills.

Record throughput, P95/P99 latency, error rate, DB time, AAS, CPU, I/O latency, redo rate, `TEMP`, active sessions, and connection pool utilization.

### 18.2. Load Testing

Tests should specify:
- Workload mix and read/write ratio.
- Virtual users / concurrent sessions.
- Ramp-up and steady-state duration.
- Dataset size and data distribution.
- Cache warmth state.
- Concurrent background jobs.
- Warm-up phase.
- Pass/fail criteria.

Never benchmark with just a trivial `SELECT`. Use representative business transactions testing commits, rollbacks, and lock contention.

### 18.3. Capacity Forecasting

Track:
- Datafile growth.
- FRA and archive growth.
- Peak `TEMP` usage.
- Undo usage.
- ASM/filesystem headroom.
- Backup repository capacity.
- Maximum connection pool footprint.
- Process and session limits.
- Standby apply throughput.

Capacity plans must forecast through the next expansion cycle with buffers for peaks and maintenance.

## 19. Security and Change Management Testing

### 19.1. Security Evidence

- Inventory of accounts and service accounts.
- Roles and system privileges.
- Object grants.
- Failed logon and privileged access audits.
- Wallet/keystore status.
- TLS / network encryption verification.
- Backup encryption status.
- Access controls on backup and evidence repositories.
- Scan results confirming zero secrets or credentials in scripts.

### 19.2. Change Evidence

Every database change requires:
- Change ID and owner.
- DDL/script version.
- Pre-change backup or restore point.
- Impact assessment.
- Maintenance window.
- Pre-check outputs.
- Execution logs.
- Post-check outputs.
- Rollback / forward-fix criteria.
- Approvals and sign-off.

### 19.3. Patch/RU Runbook

Before applying a Release Update (RU):
1. Check Oracle Home inventory and SQL patch registry.
2. Capture component statuses and invalid-object baseline.
3. Confirm backup and recovery readiness.
4. Verify Data Guard / standby compatibility.
5. Rehearse on staging.
6. Verify application and JDBC driver compatibility.
7. Define rollback/restore strategy.
8. After patching, run `datapatch` per release procedure.
9. Verify registry, components, invalid objects, and alert log.
10. Run regression tests, smoke tests, and performance comparisons.

## 20. Runbook Versioning and Change History

The runbook itself is a controlled artifact. Every version requires:
- Runbook ID and version number.
- Owner and approver.
- Effective date.
- Applicable database and environment.
- Oracle release and RU.
- Link to architecture diagram.
- Links to dashboards and alerts.
- Links to test evidence.
- Change history.
- Next scheduled review date.

Example change log:

| Version | Date | Change | Owner | Approval |
| --- | --- | --- | --- | --- |
| 1.0 | Fill in | Initial version | DBA team | Fill in |
| 1.1 | Fill in | Added FRA and archive lag metrics | DBA/SRE | Fill in |
| 1.2 | Fill in | Updated DR drill and measured RTO | DBA/App | Fill in |

After any incident, update the runbook if missing steps, inaccurate metrics, or insufficient evidence were uncovered. Never edit approved runbook content without incrementing the version and logging the change.

## 21. Post-Incident Review and Continuous Improvement

After an incident or DR drill:
1. Build a timeline from monitoring, alert logs, app logs, and tickets.
2. Quantify impact and affected data.
3. Calculate actual RPO and RTO.
4. Identify detection gaps and approval/waiting delays.
5. Identify which actions succeeded or failed.
6. Identify missing evidence.
7. Create action items with owners and due dates.
8. Update dashboards, alerts, and runbooks.
9. Retest critical action items.
10. Close the incident once the business owner signs off.

Focus reviews on systems and processes rather than blaming individuals. Action items must be measurable, assigned, and time-bound.

## 22. Complete Example Runbook for Rapid FRA Growth

### Context

Database `ORCL_PRD` is in `ARCHIVELOG` mode. FRA utilization spikes rapidly during the nightly batch window and threatens to fill up. Applications continuously write transactions; the Data Guard standby is actively applying redo.

### Triggers and Impact

- FRA warning breaches internal threshold.
- Archive generation rate exceeds baseline.
- Reclaimable space is low.
- Archive destinations risk entering `ERROR` if unaddressed.

### Pre-Checks

~~~sql
SELECT
    name,
    space_limit,
    space_used,
    space_reclaimable
FROM v$recovery_file_dest;

SELECT
    dest_id,
    status,
    destination,
    error
FROM v$archive_dest
WHERE status <> 'INACTIVE';

SELECT
    name,
    value,
    unit,
    time_computed
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag');
~~~

### Actions

1. Acknowledge alert and measure growth rate.
2. Inspect recent RMAN jobs, archived log backups, and backup destinations.
3. Check Data Guard transport/apply health and archive gaps.
4. Verify retention policy and deletion policy.
5. Identify reclaimable files via RMAN/FRA metadata.
6. If expanding capacity, confirm physical storage headroom and execute an approved change.
7. If a backup job failed, resolve media/permission/space issues before purging anything.
8. Run `RMAN DELETE OBSOLETE` per retention policy after DBA reviews the report.
9. Never delete FRA files via OS commands.
10. Monitor FRA and archive destinations post-remediation.

### Verification

- FRA utilization returns to safe levels or runway extends comfortably.
- Zero archive destinations in `ERROR`.
- Archived redo continues generating normally.
- Data Guard lag stays within target.
- A fresh RMAN backup completes cleanly.
- Application error rates and latency show no degradation.
- Zero archived log gaps outside policy.

### Evidence

- Before/after dashboard snapshots.
- `V$RECOVERY_FILE_DEST` output.
- `V$ARCHIVE_DEST_STATUS` output.
- `RMAN SHOW ALL`, `REPORT OBSOLETE`, and backup/delete logs.
- Data Guard lag snapshot.
- Ticket/change ID and approver.
- Start and end timestamps.
- Space freed and post-remediation growth rate.

## 23. Runbook Handover Checklist

### Architecture
- [ ] Primary/standby and application path diagrams match production.
- [ ] Services, listeners, PDBs, storage, and backup targets documented.
- [ ] Failure domains and network dependencies documented.
- [ ] Owners and escalation contacts listed.

### Metrics
- [ ] Every metric lists name, source, unit, and interval.
- [ ] Thresholds define warning, critical, and recovery conditions.
- [ ] Dashboards and alert routes linked.
- [ ] Baselines and capacity forecasts recorded.
- [ ] Metrics verified across RAC/PDBs if applicable.

### Procedures
- [ ] Triggers, pre-checks, steps, and expected results defined.
- [ ] Abort criteria and escalation paths defined.
- [ ] Rollback, forward-fix, or DR decisions documented.
- [ ] Verification and post-checks included.
- [ ] Required privileges and approvals defined for risky actions.

### Evidence
- [ ] Test ID and test case version recorded.
- [ ] Environment, version, RU, and `COMPATIBLE` recorded.
- [ ] Timestamps include timezones.
- [ ] Commands, logs, SQL outputs, and metrics archived.
- [ ] Expected vs. actual and `PASS`/`FAIL`/`BLOCKED` recorded.
- [ ] Actual RPO/RTO measured.
- [ ] Artifacts carry checksums and owners.
- [ ] Reviewer and approver sign-offs attached.

### Governance
- [ ] Runbook carries version, owner, approval, and review date.
- [ ] Zero secrets stored inside documents.
- [ ] Change history maintained.
- [ ] Post-incident update workflow defined.
- [ ] Next drill scheduled.

## 24. Lab: Building a Runbook from a Lab Database

Perform this in an Oracle lab environment with appropriate dictionary read and RMAN privileges. Never run destructive operations on production.

### Step 1: Record Baseline

~~~sql
SELECT name, dbid, db_unique_name, open_mode, database_role, log_mode
FROM v$database;

SELECT instance_name, host_name, status, startup_time
FROM v$instance;

SELECT name, space_limit, space_used, space_reclaimable
FROM v$recovery_file_dest;
~~~

Save outputs with timestamps and Oracle release/RU details.

### Step 2: Create Architecture Diagram

Diagram application, service, database, storage, FRA, backup, standby, and monitoring components. Clearly mark any components absent in the lab.

### Step 3: Build Metric Inventory

Select at least one metric each for:
- Availability.
- Database load.
- Blocking.
- Tablespace/FRA.
- Backups.
- Data Guard, if the lab has a standby.
- Application success/latency, if an API exists.

For each metric, document source, unit, interval, owner, threshold, and runbook link.

### Step 4: Verify Backup Evidence

In RMAN:

~~~text
SHOW ALL;
LIST BACKUP SUMMARY;
LIST BACKUP OF DATABASE;
RESTORE DATABASE PREVIEW;
RESTORE DATABASE VALIDATE;
~~~

Save logs, durations, and outcomes. If backups or validate privileges are unavailable, record `BLOCKED` with the exact reason—never fabricate `PASS`.

### Step 5: Test Alert Routing

In a test environment, trigger an approved safe alert condition or replay synthetic metrics in a test monitoring project. Confirm the alert carries the right severity, owner, route, and runbook link.

Never intentionally fill a production tablespace or FRA just to test an alert.

### Step 6: Rehearse Restore or Data Guard

Pick one drill suited to your environment:
- Restore the database onto an isolated lab host.
- Restore a single lab datafile.
- Perform a Data Guard switchover within a maintenance window.
- Verify application reconnection after a service transition.

Record timestamps, RPO/RTO, SQL health checks, and application smoke tests.

### Step 7: Assemble Evidence Package

Archive metadata, logs, query outputs, metrics, checksums, and reviewer sign-offs. Link the evidence package to the test ID and runbook version.

### Step 8: Sign-Off and Handover

DBA, application owner, and infrastructure owner confirm:
- Diagrams are accurate.
- Alert routes work.
- Procedures are executable.
- Evidence is sufficient for review.
- Remaining action items have owners and due dates.

## 25. Oracle Reference Documentation

- [Oracle Database 19c Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/) — database, instance, service, storage, and operational administration.
- [Oracle Database 19c Backup and Recovery User's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/) — RMAN, backups, restores, recovery, and validation.
- [Oracle Database 19c Data Guard Concepts and Administration](https://docs.oracle.com/en/database/oracle/oracle-database/19/sbydb/) — redo transport, apply, switchover, failover, and Broker.
- [Oracle Database 19c Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — dynamic performance views, initialization parameters, and dictionary reference.
- [Oracle Database 19c Performance Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgdba/) — database performance monitoring and tuning.
- [Oracle Database 19c Licensing Information User Manual](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/) — licensing requirements for optional packs and features.
- [Oracle Database 19c Automatic Diagnostic Repository](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/diagnosing-and-resolving-problems.html) — alert logs, incidents, and diagnostic data.
- [Oracle Data Guard Broker](https://docs.oracle.com/en/database/oracle/oracle-database/19/dgbkr/) — Data Guard configuration management and role transitions.

When finalizing a runbook for production, replace all illustrative names, thresholds, RPO/RTO targets, services, owners, and storage paths with verified system facts. Every restore, failover, cleanup, and configuration change must comply with your organization's release version, privileges, change approvals, and DR procedures.
