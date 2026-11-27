# AWR, ASH, ADDM, and Verifying Diagnostics Pack Entitlements

Oracle Database provides several tools to help DBAs and developers understand system performance. Three components frequently used together are **Automatic Workload Repository (AWR)**, **Active Session History (ASH)**, and **Automatic Database Diagnostic Monitor (ADDM)**. They answer different questions:

- AWR captures and stores workload statistics over time intervals for performance comparison.
- ASH samples active sessions to pinpoint the sessions, SQL, wait events, and objects involved during a problem window.
- ADDM analyzes workload data in AWR and produces findings along with investigation recommendations.

These features belong to the **Oracle Diagnostics Pack**. Before accessing AWR, ASH, or ADDM, verify Diagnostics Pack licensing entitlements based on your contract and actual deployment terms. The `CONTROL_MANAGEMENT_PACK_ACCESS` parameter shows whether management pack features are enabled or disabled in the database; its parameter value **is not proof that the organization has purchased or is licensed to use them**.

## 1. What Problems Do AWR, ASH, and ADDM Solve?

When users report system slowness, you need to know when the problem occurred, which sessions were active, which SQL consumed resources, and whether the bottleneck lies in CPU, I/O, concurrency, or another cause. AWR, ASH, and ADDM complement each other:

| Tool | Primary Data | Typical Questions Answered |
|---|---|---|
| AWR | Workload statistics and snapshots over time | How much work did the database perform during the problem window? |
| ASH | Samples of active sessions | Which sessions/SQL were consuming time and what were they waiting on? |
| ADDM | AWR-based workload analysis | Which bottlenecks did Oracle identify and what investigation or improvement does it suggest? |

You can visualize the analysis flow as:

~~~text
Database activity
        |
        v
  AWR snapshots ---------> Historical data by time interval
        |                               |
        |                               v
        |                         ADDM analysis
        |                               |
        v                               v
  ASH samples                    Findings / recommendations
        |
        v
 Session, SQL, wait event
        |
        v
 Identify timeframe and objects to investigate
~~~

AWR places the issue into overall workload context. ASH narrows down session activity over a short interval. ADDM provides automated analysis and investigation leads. No tool replaces reading SQL, execution plans, application data, and system configuration.

## 2. Automatic Workload Repository (AWR)

AWR is Oracle Database's performance statistics repository. Oracle periodically collects metrics on instances, sessions, wait events, SQL, I/O, segments, and other workload components, storing snapshots for historical analysis.

A snapshot is a collection of statistical data at a point in time. Comparing two snapshots enables AWR to compute deltas of cumulative counters across the interval between them. This lets DBAs see how workload behavior changed during a specific timeframe.

### Types of Information in AWR

Depending on version and configuration, an AWR report may contain:

- Load Profile: transactions, user calls, parses, executions, logical reads, and metrics normalized per second or per transaction.
- Instance Efficiency Percentages: various instance operational efficiency ratios.
- Top Timed Events: wait events and time components accounting for the largest share.
- Host CPU and Instance CPU: host-level and database-level CPU utilization.
- I/O Statistics: read/write activity and I/O-related timing.
- SQL Statistics: SQL statements consuming top elapsed time, CPU, buffer gets, disk reads, or executions.
- Segment Statistics: segments with notable activity.
- Memory Statistics: information on PGA, SGA, and workareas.
- Wait Statistics: session and instance wait breakdowns.

Sections appearing depend on release, workload, access privileges, and report type. Do not assume every report includes every section.

### Snapshots and Intervals

Oracle typically creates AWR snapshots automatically on a periodic schedule via a background process. Snapshot intervals and retention are configurable; defaults vary by version or deployment environment. Do not treat one hour or eight days as a fixed limit for every database.

When properly authorized and licensed, AWR control settings can be viewed via:

~~~sql
SELECT snap_interval,
       retention,
       topnsql
  FROM dba_hist_wr_control;
~~~

The `DBA_HIST_WR_CONTROL` view and AWR data are part of Diagnostics Pack functionality. Only query them in environments where corresponding usage rights have been verified.

Snapshots are not complete recordings of every SQL operation. AWR stores selected, aggregated, or sampled historical statistics. Therefore, a brief query occurring between two snapshots may not be captured in as much detail as a dedicated trace.

### AWR Report

An AWR report compares statistics between a start snapshot and an end snapshot. The report helps determine:

- Periods when the database experienced heavy load.
- How CPU time and DB time shifted.
- Which wait events consumed the most time.
- Which SQL had high total elapsed time or CPU.
- Abnormal spikes in logical reads, physical reads, and I/O.
- Which segments or operations had notable access volume.

An AWR report is not merely a list of slow SQL. It describes the workload of the entire instance over a time interval, so choose snapshots matching the exact timeframe when users experienced issues.

## 3. DB Time and Reading Workload in AWR

DB Time is the total active time of foreground sessions, including time running on CPU and time waiting on non-idle wait events. DB Time accumulates across sessions, so it can exceed the wall-clock duration of the measurement window.

For example, if 20 sessions are each active for an average of 30 seconds during one minute, total DB Time can reach roughly 600 seconds. This does not mean 10 minutes elapsed on the clock; it reflects total combined activity across multiple sessions.

DB CPU is the portion of DB Time during which foreground sessions actually used CPU. The remainder typically relates to I/O waits, concurrency waits, network, or other wait events.

When reading an AWR report:

1. Determine DB Time and DB CPU for the interval.
2. Compare against elapsed wall-clock time and transaction counts to gauge workload intensity.
3. Review Top Timed Events to identify dominant wait categories.
4. Check SQL Statistics to find which SQL contributed most DB Time or CPU.
5. Cross-check Host CPU to distinguish database CPU from total host CPU.

Never conclude root cause from a single ratio or single wait event alone. For example, an I/O-related wait event may be a symptom of SQL reading too many blocks, slow storage, or both.

## 4. Generating and Reading an AWR Report

In SQL*Plus or SQLcl, Oracle provides AWR report generation scripts in the Oracle Home admin directory. In environments licensed for Diagnostics Pack, you can run:

~~~sql
@?/rdbms/admin/awrrpt.sql
~~~

The script typically prompts for report format, DBID, instance number, start snapshot, and end snapshot. Choose two snapshots bracketing the exact timeframe to analyze.

Key considerations when generating a report:

- Select the same database and instance if creating an instance-level report.
- Choose a start snapshot before the incident began and an end snapshot after it ended.
- Avoid overly wide windows if hunting a brief spike; long intervals dilute transient signals.
- Avoid overly short windows if workload is sparse or deltas are not yet stable.
- Record the timezone and actual timestamps reported by users.

In RAC environments, distinguish per-instance reports from cluster-wide reports. Oracle provides corresponding global report scripts; choose the report type matching your investigation scope and release.

### Sections to Read First

| AWR Section | What to Look For |
|---|---|
| Report Summary | Measurement window, DB Time, DB CPU, and instance details |
| Load Profile | Transactions, user calls, executions, logical reads per workload unit |
| Top Timed Events | Prominent wait events and DB Time components |
| SQL ordered by Elapsed Time | SQL contributing the most elapsed time |
| SQL ordered by CPU Time | SQL consuming the most CPU |
| SQL ordered by Gets/Reads | SQL reading many buffers or blocks from storage |
| I/O Statistics | I/O volume and latency |
| Instance Activity Stats | Instance activity counters |
| Segment Statistics | Segments with heavy read/write activity |

A SQL statement with high total elapsed time is not automatically the root cause. It might run very frequently with tiny per-execution time, or be delayed by contention. Examine executions, elapsed time per execution, CPU, buffer gets, and wait profiles together.

## 5. Active Session History (ASH)

ASH is a sampling mechanism for active sessions. A session is considered active when running on CPU or waiting on a non-idle wait event. ASH records state at each sampling instant so DBAs can examine activity over short time periods.

Common fields in ASH include:

- SAMPLE_TIME: timestamp when the sample was taken.
- SESSION_ID and SESSION_SERIAL#: session identifiers in the sample.
- SQL_ID and SQL_EXEC_ID: associated SQL and execution identifier when available.
- SESSION_STATE: ON CPU or WAITING state.
- EVENT and WAIT_CLASS: wait event and wait class.
- MODULE, ACTION, PROGRAM, MACHINE: application or client identifiers.
- BLOCKING_SESSION: blocking session if present.
- CURRENT_OBJ#: object involved in the activity when available.
- INSTANCE_NUMBER: instance in RAC environments.

ASH helps answer: during the 10-minute window when the application slowed down, which sessions were active, what SQL were they running, what were they waiting on, and were they blocked?

### In-Memory ASH and Historical ASH

Oracle provides two common data sources:

- V$ACTIVE_SESSION_HISTORY: ASH samples still retained in instance memory. This is short-term data and gets overwritten as the circular buffer wraps.
- DBA_HIST_ACTIVE_SESS_HISTORY: ASH data persisted in AWR via selective sampling/flushing. It is typically sparser than in-memory data and depends on AWR retention.

Do not assume historical data retains every sample from V$ACTIVE_SESSION_HISTORY. When investigating older incidents, granularity may be lower than in-memory data captured during the live incident.

ASH belongs to the Diagnostics Pack. Querying V$ACTIVE_SESSION_HISTORY or DBA_HIST_ACTIVE_SESS_HISTORY for workload analysis requires verifying usage rights under applicable licensing terms.

### Counting ASH Samples by SQL and Wait Event

The following example illustrates grouping in-memory samples by SQL and wait event over the past 10 minutes:

~~~sql
SELECT sql_id,
       session_state,
       wait_class,
       event,
       COUNT(*) AS sample_count
  FROM v$active_session_history
 WHERE sample_time >= SYSTIMESTAMP - INTERVAL '10' MINUTE
   AND session_type = 'FOREGROUND'
 GROUP BY sql_id,
          session_state,
          wait_class,
          event
 ORDER BY sample_count DESC;
~~~

The output helps identify SQL statements and activity types appearing most frequently in samples. `COUNT(*)` is the sample count, not the SQL execution count and not exact wall-clock timing. ASH is sampled data, so conclusions should be corroborated with AWR, SQL statistics, and application data.

### Viewing Active Sessions

~~~sql
SELECT sample_time,
       session_id,
       session_serial#,
       sql_id,
       session_state,
       wait_class,
       event,
       module,
       action,
       blocking_session
  FROM v$active_session_history
 WHERE sample_time >= SYSTIMESTAMP - INTERVAL '5' MINUTE
 ORDER BY sample_time DESC;
~~~

This query helps observe which sessions are ON CPU, which are WAITING, and blocking relationships if present. If the target window is older than the in-memory ASH buffer, check historical ASH in AWR when authorized and licensed.

### ASH Report

Oracle provides a script to generate an ASH report:

~~~sql
@?/rdbms/admin/ashrpt.sql
~~~

The script typically prompts for report type, time range, and related parameters. An ASH report focuses on sampled session activity, making it effective for investigating brief spikes, wait events, SQL, and modules over narrow timeframes.

In RAC, you may need a global report or to select the relevant instance. Choose the report matching the incident scope rather than defaulting to a single instance.

## 6. Automatic Database Diagnostic Monitor (ADDM)

ADDM is an automated performance diagnostic tool built on AWR data. ADDM examines workload across a snapshot interval, detects issues significantly impacting DB Time, and outputs findings and recommendations.

ADDM can identify problem categories such as:

- CPU bottlenecks.
- I/O bottlenecks.
- SQL consuming excessive DB Time.
- Concurrency or contention.
- Resource shortages or memory pressure.
- Certain instance configuration and operational issues.

ADDM typically runs automatically after AWR snapshots per Oracle's scheduling mechanism. DBAs can also view an ADDM report for a snapshot range using the admin script:

~~~sql
@?/rdbms/admin/addmrpt.sql
~~~

The script prompts for parameters to select the analysis interval. Use only in environments with verified Diagnostics Pack entitlements.

### Findings and Recommendations

A finding typically describes:

- Issue name or category.
- Estimated impact on DB Time.
- Associated causes or objects.
- Related SQL, wait events, or system components.
- Recommendations for investigation or remediation.

ADDM recommendations are analytical guidance, not commands to apply blindly. For instance, ADDM may suggest SQL tuning, configuration adjustments, or I/O investigation. Before making changes, DBAs must validate them against execution plans, runtime statistics, workload behavior, and business requirements.

ADDM relies on data within the chosen analysis window. If wrong snapshots are picked, workload shifts sharply, or an incident is too brief, findings may not reflect the issue users experienced.

## 7. Combining AWR, ASH, and ADDM in an Investigation

A practical workflow can follow this order:

1. Establish the incident start/end timestamps from application logs, monitoring, or user feedback.
2. Select AWR snapshots spanning that timeframe.
3. Read the AWR report to determine workload, DB Time, CPU, top wait events, and prominent SQL.
4. Use ASH to isolate specific sessions, SQL, modules, wait events, and blocking at exact moments.
5. Read ADDM findings to see which bottlenecks Oracle detected and what recommendations apply.
6. Retrieve notable SQL_IDs and inspect execution plans and runtime statistics using appropriate tools.
7. Correlate with application logs, configuration changes, deployments, and infrastructure metrics.
8. Propose a change with a clear hypothesis, test in a suitable environment, and re-measure.

For example, AWR shows DB Time spiked and I/O-related wait events dominate. ASH reveals a single SQL_ID appearing in many WAITING samples on data read events. ADDM also flags that SQL as a major contributor. Next, inspect the SQL text, execution plan, A-Rows, Buffers, and Reads to check whether the query reads too much data or storage is genuinely slow.

If AWR shows DB CPU dominates DB Time, ASH helps pinpoint which SQL is frequently ON CPU. Then examine CPU time, executions, plans, expressions, joins, and rows processed.

If ASH shows sessions WAITING with a `blocking_session`, investigate the locking transaction and SQL involved. AWR/ADDM supply context, while resolving blocking requires examining the specific session, SQL, and transaction.

## 8. Distinguishing Diagnostics Pack and Tuning Pack

Oracle separates advanced management capabilities into management packs. Within this lesson's scope, keep in mind:

| Component/Feature | Associated Pack |
|---|---|
| AWR and AWR reports | Diagnostics Pack |
| ASH and ASH reports | Diagnostics Pack |
| ADDM | Diagnostics Pack |
| SQL Tuning Advisor | Tuning Pack |
| SQL Access Advisor | Tuning Pack |
| Certain advanced SQL Monitoring capabilities | Tuning Pack under applicable terms |

Tuning Pack has a dependency relationship with Diagnostics Pack under Oracle's licensing policy. Do not assume having Diagnostics Pack automatically grants Tuning Pack rights.

Feature lists, usage rights, editions, and licensing terms can vary by version, deployment model, and contract. For official confirmation, consult current licensing documentation and your organization's specific contracts.

## 9. Checking CONTROL_MANAGEMENT_PACK_ACCESS

Oracle provides the `CONTROL_MANAGEMENT_PACK_ACCESS` initialization parameter to control enablement of management pack features in the database. You can check the current setting in SQL*Plus:

~~~sql
SHOW PARAMETER control_management_pack_access;
~~~

Or via query:

~~~sql
SELECT name,
       value,
       issys_modifiable
  FROM v$parameter
 WHERE name = 'control_management_pack_access';
~~~

Common values:

| Value | Meaning |
|---|---|
| NONE | Disables access to Diagnostics Pack and Tuning Pack features via this control |
| DIAGNOSTIC | Enables Diagnostics Pack features |
| DIAGNOSTIC+TUNING | Enables Diagnostics Pack and Tuning Pack features |

Oracle normally displays these values in uppercase. The parameter value only indicates that the database configuration allows exposing/using pack features; it does not confirm a license was purchased.

### Two-Layer Entitlement Verification

To determine whether you are permitted to use AWR, ASH, and ADDM, separate two questions:

1. **Does the database configuration enable the features?** Check `CONTROL_MANAGEMENT_PACK_ACCESS`.
2. **Does the organization hold license entitlements to use the features?** Check contracts, order documents, license metrics, edition, deployment model, and applicable licensing terms.

These two questions are independent. A database may be set to `DIAGNOSTIC+TUNING` even though the organization has not licensed the packs. Conversely, the organization may hold licenses while the database is configured as `NONE`.

Never treat successful query execution, visible OEM menus, or runnable scripts as proof of licensing.

### If Diagnostics Pack Is Not Licensed

If the organization is not licensed for Diagnostics Pack, do not use AWR, ASH, or ADDM simply because the views and scripts exist. The DBA/licensing owner should verify applicable policy and configure `CONTROL_MANAGEMENT_PACK_ACCESS` appropriately, typically `NONE` if neither Diagnostics Pack nor Tuning Pack is permitted.

Changing parameters must be performed by an authorized DBA following environment change control. Never modify parameters in production just to test a query.

## 10. License Verification Process Before Running Reports

Before generating AWR/ASH/ADDM reports, follow these steps:

1. Identify the Oracle Database release, edition, and deployment platform.
2. Check the `CONTROL_MANAGEMENT_PACK_ACCESS` value.
3. Verify the organization's contract and entitlements for Diagnostics Pack.
4. Check special terms if the database runs on cloud or managed services.
5. Consult the Oracle Licensing Information User Manual for your exact version and applicable agreement.
6. Confirm with the DBA, licensing administrator, or procurement team if anything is unclear.
7. Only use AWR, ASH, or ADDM after confirming proper authorization.

Do not rely on an in-database query alone to conclude whether the organization holds a license. The database is not an authoritative record of commercial contracts, license metrics, cloud usage rights, or negotiated exceptions.

### Example Pre-Use Verification Table

| Item | Value to Confirm | Source |
|---|---|---|
| Database release | Version and Release Update | Database inventory/DBA |
| Edition | Enterprise Edition or deployed edition | Database inventory and contract |
| Deployment | On-premises, OCI, or other service | Deployment architecture/contract |
| Pack access parameter | NONE / DIAGNOSTIC / DIAGNOSTIC+TUNING | V$PARAMETER or SHOW PARAMETER |
| Diagnostics Pack entitlement | Yes/No/specific scope | License agreement, order documents |
| Tuning Pack entitlement | Yes/No/specific scope | License agreement, order documents |
| Usage approval | Responsible person/team confirming | DBA/licensing owner |

This is administrative verification data; it does not replace legal documents or licensing team guidance.

## 11. Queries Requiring Licensing Caution

The following views and scripts are tied to Diagnostics Pack functionality:

- `DBA_HIST_*` views and AWR reports.
- `V$ACTIVE_SESSION_HISTORY` and `DBA_HIST_ACTIVE_SESS_HISTORY`.
- ADDM reports and analyses.
- Certain OEM tools or pages built on Diagnostics Pack data.

If entitlements are unverified, do not run these queries just to test whether they return data. A view existing in the data dictionary or an account having SELECT privileges does not prove license rights.

Configuration queries such as V$PARAMETER can be used to read `CONTROL_MANAGEMENT_PACK_ACCESS`. However, reading the parameter still does not replace contract verification.

## 12. Alternatives and Data Outside Diagnostics Pack

If Diagnostics Pack is unavailable, other performance investigation methods remain depending on version and privileges:

- `EXPLAIN PLAN` and `DBMS_XPLAN.DISPLAY` to inspect estimated execution plans.
- SQL Trace and TKPROF within authorized privileges and procedures.
- `V$SESSION` to view current session state, SQL_ID, and active wait information.
- `V$SQL` to inspect available cursor statistics such as executions, elapsed time, CPU time, buffer gets, and disk reads, subject to access rights and applicable terms.
- AWR/ASH/ADDM are not free substitutes; they are Diagnostics Pack features.
- OS-, storage-, application-, and middleware-tier monitoring to measure CPU, memory, disk latency, network, and request latency.

Usage rights for each view, package, or tool must be checked against your Oracle version and applicable policy. Never assume every V$ view is free or that external tools fully replicate historical AWR/ASH data.

### EXPLAIN PLAN

`EXPLAIN PLAN` generates an estimated plan:

~~~sql
EXPLAIN PLAN FOR
SELECT department_id,
       COUNT(*)
  FROM employees
 GROUP BY department_id;

SELECT *
  FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

This does not execute the SQL statement and provides no runtime A-Rows. It is useful for reviewing expected access paths and join methods, but does not replace runtime statistics.

### SQL Trace and TKPROF

SQL Trace records parse, execute, fetch, CPU, elapsed time, reads, and waits at the session or call level as configured. TKPROF formats the trace into a more readable report. Use proper privileges, protect trace files because they may contain SQL text and sensitive data, and control overhead and storage consumption.

## 13. Common Mistakes When Reading AWR, ASH, and ADDM

**Choosing the wrong snapshot range:** the report may span both normal workload hours and incident hours, diluting the root cause. Align exact timestamps.

**Treating DB Time as wall-clock time:** DB Time sums across sessions and can exceed the interval's elapsed wall-clock time.

**Treating ASH sample counts as SQL execution counts:** ASH is sampled active session data, not a complete log of every execution.

**Concluding from a single wait event:** a top wait event may be a symptom of SQL reading too much data, contention, or infrastructure issues. Inspect the associated SQL and plans.

**Treating ADDM recommendations as mandatory commands:** recommendations must be validated against workload behavior and testing.

**Comparing two intervals with different workloads:** differing transaction volumes, user counts, batch jobs, and datasets can render deltas incomparable.

**Using AWR to diagnose every application issue:** AWR describes database workload; latency in the application, network, or middleware requires other tools.

**Confusing pack access parameters with licenses:** `DIAGNOSTIC+TUNING` does not mean the organization purchased those packs.

**Using script success as proof of compliance:** a script may succeed due to database configuration and privileges, yet commercial licensing must still be verified independently.

## 14. Example Investigation of a Slowdown Incident

Suppose users report that report generation was slow between 14:00 and 14:20:

**Step 1: Establish the timeframe.** Record timezone, database instance, module, and request start/end timestamps. Check for overlapping deployments or batch jobs.

**Step 2: Verify Diagnostics Pack.** Check `CONTROL_MANAGEMENT_PACK_ACCESS` and confirm entitlements with the licensing owner before opening AWR/ASH/ADDM.

**Step 3: Select AWR snapshots.** Pick snapshots spanning 14:00–14:20 and review the report for DB Time, DB CPU, Top Timed Events, and prominent SQL.

**Step 4: Isolate with ASH.** If one wait class dominates, filter ASH by timestamp and inspect SQL_ID, session, module, event, and `blocking_session`. Remember this is sampled data and may miss very brief events.

**Step 5: Read ADDM.** Review findings for the matching snapshot range and cross-reference SQL or wait events highlighted by ADDM.

**Step 6: Inspect SQL.** Retrieve SQL text, execution plan, and runtime row-source statistics with appropriate tools, analyzing cardinalities, I/O, joins, and filters.

**Step 7: Check outside the database.** Correlate application logs, host CPU, memory, storage latency, and network metrics.

**Step 8: Test a remediation.** Change one factor in an appropriate environment, re-measure under the same workload, and verify no regressions on other queries.

If Diagnostics Pack is not licensed, skip the steps using AWR/ASH/ADDM and rely on permitted alternatives such as execution plans, SQL Trace/TKPROF, session/cursor views, and application/OS-level monitoring.

## 15. Operational and Data Protection Checklist

When generating or sharing performance reports:

- Select the exact database, instance, and snapshot range.
- Clearly document the timezone and workload conditions.
- Retain SQL_ID, child number, and execution timestamps for correlation.
- Do not share reports containing sensitive literals, schema names, object names, or SQL text without proper sanitization.
- Store reports according to retention and internal access policies.
- Never alter instance-wide parameters without DBA approval.
- Never run AWR/ASH/ADDM scripts before verifying Diagnostics Pack entitlements.
- Keep technical conclusions separate from licensing conclusions.

## 16. Conclusion

AWR stores workload statistics by snapshot, ASH samples active sessions, and ADDM analyzes AWR data to produce findings and recommendations. Combining all three helps DBAs identify problematic timeframes, involved SQL and sessions, prominent wait events, and next investigation steps.

AWR, ASH, and ADDM belong to the Oracle Diagnostics Pack. Before using them, check `CONTROL_MANAGEMENT_PACK_ACCESS` to inspect database configuration, then verify actual usage rights through contracts, license metrics, edition, deployment platform, and applicable Oracle documentation. An enabled parameter or successfully executing script does not prove licensing. If proper entitlements are absent, use other permitted diagnostic methods and consult the DBA/licensing owner before accessing pack features.
