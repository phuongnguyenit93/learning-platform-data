# Capacity Planning, Alert Thresholds, and Handling Resource Exhaustion

Operating Oracle Database is not only about keeping instances up. DBAs must also anticipate when resources will hit limits, spot trends early enough to act, and maintain response procedures when a resource actually runs out. A database can remain OPEN while applications fail to write data because a tablespace is full, fail to generate archive logs because the FRA is full, fail to allocate temporary extents, or fail to spawn additional sessions/processes.

**Capacity planning** is the practice of measuring current consumption, understanding growth rates, forecasting demand, and preserving adequate headroom for both workloads and maintenance activities. **Alert thresholds** convert those measurements into actionable signals. **Handling resource exhaustion** requires identifying the exact resource, protecting data, restoring service availability, and eliminating the root cause of recurrence.

No single percentage threshold applies across every database. A tablespace at 90% may still be safe if hundreds of GB remain and growth is slow; a filesystem at 70% may already be dangerous if write velocity is surging and expansion is impossible. Combine utilization percentage, remaining free capacity, maximum limits, growth rate, response lead time, and physical expansion capability.

## 1. Resource Layers Requiring Capacity Planning

Oracle capacity spans multiple interconnected yet distinct layers. Monitoring one layer never substitutes for another.

| Resource Layer | Components to Monitor | Risk When Exhausted |
| --- | --- | --- |
| Database storage | Datafiles, tablespaces, tempfiles | Cannot allocate extents or write data |
| ASM/storage | Disk groups, filesystems, volumes, SAN | Datafiles/redo/archives cannot extend or write |
| Recovery storage | Fast Recovery Area, archived redo, backups | Archiver stalls; backup/recovery impacted |
| Temporary space | TEMP tablespace, tempfiles, temp segments | Sorts, hash joins, index builds, or large queries fail |
| Undo | Undo tablespace, undo extents, retention | Transactions lack undo; queries risk snapshot too old |
| Redo | Online redo log groups, archive throughput | Log switches stall, archiver bottlenecks, or database hangs on archive destination |
| Memory | SGA, PGA, process memory, OS memory | Cannot allocate shared memory or process memory |
| Process/session | PROCESSES, SESSIONS, transactions | Cannot spawn new processes/sessions |
| CPU/I/O capacity | CPU run queue, IOPS, latency, throughput | Queues build up and response times degrade even with free storage |
| Operational capacity | Backup window, maintenance window, recovery time | Insufficient time or resources to complete administrative tasks |

### 1.1. Distinguishing Logical Capacity from Physical Capacity

A datafile may be configured with AUTOEXTEND up to 100 GB while the underlying filesystem only has 5 GB free. According to Oracle metadata, the file has 70 GB of headroom; according to real storage, it can grow at most roughly 5 GB before the filesystem fills up.

Conversely, an ASM disk group may still have ample free space while a datafile has reached MAXSIZE or the tablespace hit a structural limit. In that case, adding underlying storage will not automatically let the datafile extend.

Therefore, monitor at least three levels:

1. **Logical usage:** extents used inside the tablespace or resources consumed.
2. **File/database expansion limits:** BYTES, MAXBYTES, AUTOEXTENSIBLE, and tablespace limits.
3. **Physical storage:** ASM usable space, filesystem/volume free space, and infrastructure-level quotas.

### 1.2. Allocated Space Is Not Used Space

A 500 GB datafile may currently use only 300 GB, leaving 200 GB free inside the file. That internal free space is still already allocated from underlying storage. If the datafile has AUTOEXTEND, Oracle can grow the file when needed, but only as long as headroom exists under both MAXSIZE and physical storage.

Reports should distinguish:
- Allocated bytes: current size of the datafile.
- Used bytes: space consumed by allocated extents.
- Free bytes inside files: free space within existing datafiles.
- Autoextend headroom: remaining room up to MAXSIZE.
- Physical free bytes: space remaining on ASM/filesystems.

Do not sum these quantities together as if they were independent pools of free space. Free space inside a datafile is already part of allocated bytes; autoextend headroom still depends on physical storage to materialize.

## 2. Building a Capacity Baseline

Before forecasting, establish a consistent baseline. A baseline is a snapshot with clear identity, timestamp, units, and scope.

### 2.1. Collecting Database Metadata

Information to record:

- DB_NAME and DB_UNIQUE_NAME.
- DBID and database role.
- Oracle version and COMPATIBLE.
- Instance, host, and INST_ID if using RAC.
- CDB/PDB and CON_ID if using multitenant.
- Tablespaces, datafiles, tempfiles, and block sizes.
- ASM disk group or filesystem hosting each file.
- FRA size and archive destinations.
- SGA/PGA/process/session limits.
- Backup retention, archive deletion policy, and data retention timelines.
- Daily/weekly/monthly growth and scheduled batch surges.

Example database query:

~~~sql
SELECT name,
       dbid,
       open_mode,
       database_role,
       log_mode
FROM v$database;
~~~

Instance details:

~~~sql
SELECT instance_name,
       host_name,
       version,
       startup_time
FROM v$instance;
~~~

In RAC, use GV$INSTANCE and preserve INST_ID when aggregating.

### 2.2. Periodic Collection

A single snapshot only shows current state. To forecast, you need a time series of snapshots—for instance, every 15 minutes or hourly depending on rate of change and monitoring overhead.

Store:
- Timestamp with timezone.
- Resource name and scope.
- Allocated, used, free, and maximum values.
- Growth over the interval.
- Alert state.
- SQL_ID/session/module if consumption sources can be attributed.
- Maintenance events, purges, partition drops, backups, and batch jobs.

Never overwrite old snapshots. History is essential for identifying trends, seasonality, and the impact of expansion actions.

### 2.3. Baselines Must Capture Peaks

Averages often mask peaks. For TEMP, PGA, processes, and I/O, hourly or batch-window peaks dictate service availability.

Record:
- Normal steady-state levels.
- Intraday peaks.
- Month-end / period-end peaks.
- Peaks during backups, index rebuilds, ETL, or reporting.
- Growth spikes during abnormal incidents.
- Remaining headroom at peak times.

Never size capacity based solely on off-peak troughs.

## 3. Growth Planning

Forecasts must combine historical data, business plans, and technical operations. Never extrapolate solely from the most recent day.

### 3.1. Simple Growth Rate

If used space grows from 400 GB to 430 GB over 10 days:

\[
Growth/day = \frac{430 - 400}{10} = 3\ GB/day
\]

If 90 GB of usable space remains:

\[
Time\ to\ full = \frac{90}{3} = 30\ days
\]

This is a simple linear projection. It assumes steady growth with no workload shifts, purges, partition maintenance, or new data campaigns.

### 3.2. Use Multiple Time Windows

Compare:
- 24-hour growth.
- 7-day rolling average.
- 30-day rolling average.
- Same day/hour of the previous week.
- Business-cycle peaks.

A large one-time import can inflate 24-hour growth well above the monthly trend. Conversely, a quiet week can make a 7-day forecast overly optimistic.

### 3.3. Forecasting with Seasonality

Systems often surge at end-of-day, month-end, or seasonal peaks. Plan around cycles:
- Daily transaction volumes.
- Monthly data growth.
- Log and audit data retention.
- Partition lifecycles.
- Archive/purge batch schedules.
- Customer onboarding or new feature launch plans.

When workloads exhibit seasonality, model observed peak scenarios or business projections rather than relying on a flat linear average.

### 3.4. Calculating Time-to-Full

\[
TimeToFull = \frac{UsableHeadroom}{ExpectedGrowthRate}
\]

UsableHeadroom must be bounded by the lowest real constraint among:
- Tablespace/datafile headroom.
- ASM/filesystem capacity available to files.
- Storage quotas or limits.
- Operational limits and provisioning lead time for additional capacity.

If the growth rate is zero or negative, time-to-full is undefined under a linear model. Never display infinity as a safety guarantee; keep absolute thresholds and change monitoring in place.

### 3.5. Growth Scenarios

Model at least three scenarios:

| Scenario | Assumption | Purpose |
| --- | --- | --- |
| Base | Observed normal growth rate | Routine operational planning |
| High | Peak growth or increased workload | Preparation for peak seasons |
| Stress | Bulk import, extended retention, failed purge, or runaway batch | Stress-testing limits and response plans |

Provisioning plans should satisfy the High scenario or the organization's accepted risk tolerance, while maintaining contingency plans for Stress.

## 4. Estimating Demand by Workload

Storage does not grow linearly with row counts alone. Indexes, LOBs, undo, redo, temporary segments, and backups each scale differently.

### 4.1. Table and Index Data

Estimate from:
- New rows per day.
- Average row size.
- Update/delete rates.
- Number of indexes and index key widths.
- LOB sizes and out-of-line storage ratios.
- Partitioning and retention.
- Compression and deduplication if enabled.

Rough formulas:

\[
TableGrowth \approx NewRows \times AverageStoredRowBytes
\]

\[
IndexGrowth \approx NewRows \times AverageIndexEntryBytes
\]

These are initial approximations; block overhead, PCTFREE, row migration, index splits, compression, and segment allocation cause real numbers to vary.

### 4.2. LOBs and Large Data

CLOB/BLOB segments can grow far faster than the metadata table storing the locators. Track LOB segments and LOB indexes separately, and audit retention for files, images, PDFs, and payloads.

### 4.3. Partition Lifecycle

Partition exchanges, partition truncates/drops, and interval partitioning create step-wise capacity jumps and drops. Linear forecasts must incorporate new partition creation and old partition purge schedules.

### 4.4. Index Maintenance

Index rebuilds can require substantial temporary space. Depending on the operation and options, Oracle may have to keep the old index while building the new structure. Size not only for the final index footprint, but also for peak usage during maintenance windows.

### 4.5. Undo and Redo

Undo depends on transaction concurrency, transaction duration, query duration, and retention. Redo depends on data modification volume, index maintenance, batch jobs, and workload mix. Never derive undo/redo solely from table size.

### 4.6. Backups and Archived Redo

Full backups, incremental backups, archived redo, and backup copies have distinct retention lifecycles. FRA forecasting must factor in hourly archive generation, backup frequency, deletion policies, standby apply lag, and required recovery retention windows.

## 5. Monitoring Tablespaces and Datafiles

Tablespaces are the logical management layer. Datafiles are physical files or ASM/OMF-managed files. Track both tablespace used/free space and individual datafile expansion limits.

### 5.1. Inspecting Datafiles and Autoextend

~~~sql
SELECT tablespace_name,
       file_name,
       bytes / 1024 / 1024 AS allocated_mb,
       maxbytes / 1024 / 1024 AS max_mb,
       autoextensible,
       increment_by
FROM dba_data_files
ORDER BY tablespace_name, file_name;
~~~

DBA_TEMP_FILES provides equivalent metadata for tempfiles.

Columns:
- BYTES: current file size.
- MAXBYTES: declared expansion ceiling.
- AUTOEXTENSIBLE: whether automatic extension is enabled.
- INCREMENT_BY: blocks added per increment; multiply by block size for bytes.

If AUTOEXTENSIBLE = NO, do not count MAXBYTES as usable headroom.

### 5.2. Inspecting Free Extents in Permanent Tablespaces

~~~sql
SELECT tablespace_name,
       SUM(bytes) AS free_bytes,
       MAX(bytes) AS largest_free_extent
FROM dba_free_space
GROUP BY tablespace_name
ORDER BY tablespace_name;
~~~

FREE_BYTES is total free extent space. LARGEST_FREE_EXTENT helps spot situations where operations requiring contiguous extents might fail despite high total free space. With locally managed tablespaces and autoallocate, allocations follow Oracle-managed extent sizes; do not assume every segment needs a single extent equal to the largest request.

### 5.3. Summarizing Allocated, Used, and Theoretical Maximum

Example for permanent tablespaces:

~~~sql
WITH datafiles AS (
    SELECT
        tablespace_name,
        SUM(bytes) AS allocated_bytes,
        SUM(
            CASE
                WHEN autoextensible = 'YES'
                THEN GREATEST(maxbytes, bytes)
                ELSE bytes
            END
        ) AS configured_max_bytes
    FROM dba_data_files
    GROUP BY tablespace_name
),
free_space AS (
    SELECT
        tablespace_name,
        SUM(bytes) AS free_bytes
    FROM dba_free_space
    GROUP BY tablespace_name
)
SELECT
    d.tablespace_name,
    d.allocated_bytes,
    NVL(f.free_bytes, 0) AS free_bytes_inside_files,
    d.allocated_bytes - NVL(f.free_bytes, 0) AS used_bytes,
    d.configured_max_bytes,
    d.configured_max_bytes -
        (d.allocated_bytes - NVL(f.free_bytes, 0))
        AS theoretical_headroom_bytes,
    ROUND(
        100 * (d.allocated_bytes - NVL(f.free_bytes, 0))
        / NULLIF(d.allocated_bytes, 0),
        2
    ) AS used_pct_of_allocated
FROM datafiles d
LEFT JOIN free_space f
  ON f.tablespace_name = d.tablespace_name
ORDER BY d.tablespace_name;
~~~

THEORETICAL_HEADROOM_BYTES reflects configured datafile headroom, not a physical storage guarantee. It can exceed the space actually free on ASM/filesystems. Also account for block/file size ceilings and tablespace limits.

### 5.4. Using DBA_TABLESPACE_USAGE_METRICS

In supported releases, DBA_TABLESPACE_USAGE_METRICS provides tablespace usage and utilization percentages. TABLESPACE_SIZE and USED_SPACE are reported in blocks; join DBA_TABLESPACES to get BLOCK_SIZE when converting to bytes.

~~~sql
SELECT m.tablespace_name,
       t.block_size,
       m.tablespace_size,
       m.used_space,
       m.used_percent
FROM dba_tablespace_usage_metrics m
JOIN dba_tablespaces t
  ON t.tablespace_name = m.tablespace_name
ORDER BY m.used_percent DESC;
~~~

This view is handy for monitoring, yet storage and datafile limits still require verification. Never interpret USED_PERCENT in isolation from autoextend configuration and physical storage.

### 5.5. Bigfile vs. Smallfile Tablespaces

Smallfile tablespaces can contain multiple datafiles. Bigfile tablespaces contain one very large datafile. Expansion methods differ:
- Smallfile: can add additional datafiles subject to file count and storage limits.
- Bigfile: typically resized or autoextended on the single datafile; you cannot add a second datafile to a bigfile tablespace.

Identify the tablespace type before choosing an expansion command.

## 6. AUTOEXTEND and Expansion Limits

AUTOEXTEND allows Oracle to grow datafiles automatically when extents are needed. It does not replace capacity planning.

### 6.1. Enabling Bounded AUTOEXTEND

~~~sql
ALTER DATABASE DATAFILE
    '/u02/oradata/app/app_data01.dbf'
AUTOEXTEND ON
NEXT 512M
MAXSIZE 40G;
~~~

This example uses a filesystem path. In ASM/OMF, syntax and filenames may differ. Choose NEXT based on growth patterns and management overhead; MAXSIZE must fit within the storage budget.

### 6.2. Disabling AUTOEXTEND

~~~sql
ALTER DATABASE DATAFILE
    '/u02/oradata/app/app_data01.dbf'
AUTOEXTEND OFF;
~~~

Disabling autoextend can be useful when strict storage governance is needed, provided alerts and proactive expansion workflows are active. If a file fills without intervention, applications will hit extent allocation errors.

### 6.3. Resizing a Datafile

~~~sql
ALTER DATABASE DATAFILE
    '/u02/oradata/app/app_data01.dbf'
RESIZE 30G;
~~~

RESIZE succeeds only if it does not truncate space holding active extents. When shrinking, if extents sit near the end of the file, Oracle may return ORA-03297. Never drop segments or shrink files haphazardly to force a resize.

### 6.4. Adding a Datafile to a Smallfile Tablespace

~~~sql
ALTER TABLESPACE app_data
ADD DATAFILE '/u02/oradata/app/app_data02.dbf'
SIZE 10G
AUTOEXTEND ON
NEXT 512M
MAXSIZE 30G;
~~~

For OMF/ASM, Oracle can generate filenames according to configuration. Example:

~~~sql
ALTER TABLESPACE app_data
ADD DATAFILE '+DATA'
SIZE 10G
AUTOEXTEND ON
NEXT 512M
MAXSIZE 30G;
~~~

Use ASM syntax only when the disk group is ready and OMF policies align.

### 6.5. Why Might AUTOEXTEND Fail to Save a Tablespace?

Common causes:
- File already reached MAXSIZE.
- Filesystem/ASM disk group ran out of space.
- File size hit platform or block-size maximums.
- Insufficient permissions or storage path unavailable.
- Tablespace is bigfile and reached its ceiling.
- Storage quota or thin-provisioned pool is exhausted.
- Autoextend increment exceeds remaining free space.

Inspect DBA_DATA_FILES, the alert log, and the storage layer together.

## 7. Monitoring ASM and Filesystems

A tablespace may still report free extents while datafiles cannot grow because underlying storage is full. This is one reason forecasts relying solely on DBA_FREE_SPACE fail.

### 7.1. ASM Disk Groups

From the ASM instance or an account with dynamic performance view access:

~~~sql
SELECT name,
       state,
       type,
       total_mb,
       free_mb,
       required_mirror_free_mb,
       usable_file_mb
FROM v$asm_diskgroup
ORDER BY name;
~~~

USABLE_FILE_MB matters because it accounts for redundancy/mirroring requirements and reserved space. FREE_MB does not necessarily equal the safe space available for new files.

In RAC/ASM, use GV$ASM_DISKGROUP when appropriate and retain INST_ID. One disk group may be visible across multiple instances; never double-count rows for the same disk group across instances.

### 7.2. Filesystems and Volumes

Track:
- Total bytes.
- Used/free bytes.
- Inode usage.
- Mount points.
- Quotas.
- Storage latency and throughput.
- Thin pool or SAN capacity if applicable.

A filesystem can exhaust inodes before running out of bytes. A thin-provisioned volume can report abundant logical free space while its backing physical pool is nearly full.

### 7.3. Do Not Substitute df for Oracle Metadata

OS commands show filesystem health but cannot tell which extents inside a tablespace are used. Conversely, DBA_DATA_FILES has no visibility into other storage consumers sharing the same filesystem. Both layers must be combined.

## 8. Fast Recovery Area and Archived Redo

The FRA holds recovery-related files such as archived redo logs, backup pieces, image copies, flashback logs, and control file/autobackups depending on configuration.

### 8.1. Checking the FRA

~~~sql
SELECT name,
       space_limit,
       space_used,
       space_reclaimable,
       number_of_files
FROM v$recovery_file_dest;
~~~

Space values are in bytes. SPACE_RECLAIMABLE is the space Oracle can reclaim under FRA management rules; never treat that entire figure as files you can arbitrarily delete immediately.

### 8.2. Breaking Down FRA Usage

~~~sql
SELECT file_type,
       percent_space_used,
       percent_space_reclaimable,
       number_of_files
FROM v$flash_recovery_area_usage
ORDER BY percent_space_used DESC;
~~~

This view identifies which file types dominate the FRA. If archived logs spike, investigate archive generation, backups, standby apply, and deletion policies. If flashback logs grow, check Flashback Database and retention targets. If backup pieces grow, check retention policies and backup schedules.

### 8.3. Raising FRA Size Does Not Create Physical Storage

You can adjust the FRA limit:

~~~sql
ALTER SYSTEM SET db_recovery_file_dest_size = 200G
SCOPE = BOTH;
~~~

This is an example only. Increase it only when backing physical storage has ample free space and budget is approved. Setting SPACE_LIMIT above filesystem/ASM capacity allows Oracle to keep writing until physical storage hits 100%.

### 8.4. Archived Logs and ORA-00257

When the archive destination fills or the archiver cannot write archive logs, database operations may stall. ORA-00257 typically signals an archiver error requiring immediate destination remediation.

Procedure:
1. Check V$ARCHIVE_DEST_STATUS and the alert log.
2. Identify which destination is failing.
3. Inspect the FRA or archive filesystem.
4. Verify the most recent archive backups.
5. Verify standby has received/applied redo per policy.
6. Use RMAN and deletion policies to reclaim eligible files.
7. Expand storage or fix the destination if needed.
8. Confirm the archiver resumes normal operation.

Never delete archived redo with OS commands to free space. Manual deletion can break the recovery chain or Data Guard.

### 8.5. RMAN and Safe Cleanup

Execute RMAN commands strictly under the system's retention/deletion policies. Inspection example:

~~~text
RMAN> SHOW RETENTION POLICY;
RMAN> SHOW ARCHIVELOG DELETION POLICY;
RMAN> CROSSCHECK ARCHIVELOG ALL;
RMAN> REPORT OBSOLETE;
~~~

CROSSCHECK reconciles RMAN metadata with physical files; REPORT OBSOLETE lists backups no longer required under the retention policy. After verifying backups, standby status, and policies, the DBA can run DELETE OBSOLETE or back up archived logs with DELETE INPUT per an approved runbook.

Never use DELETE EXPIRED to clean up files that still exist; EXPIRED means RMAN could not locate the file during crosscheck. Never delete logs that have not been backed up or applied on standby if the deletion policy requires keeping them.

## 9. TEMP Tablespace

TEMP is used for sorts, hash joins, bitmap operations, index builds, and operations needing temporary segments. TEMP can spike sharply during a single query even while permanent tablespaces have ample free space.

### 9.1. Monitoring Tempfiles

~~~sql
SELECT tablespace_name,
       file_name,
       bytes / 1024 / 1024 AS allocated_mb,
       maxbytes / 1024 / 1024 AS max_mb,
       autoextensible
FROM dba_temp_files
ORDER BY tablespace_name, file_name;
~~~

### 9.2. Monitoring TEMP Usage

~~~sql
SELECT tablespace_name,
       SUM(bytes_used) / 1024 / 1024 AS used_mb,
       SUM(bytes_free) / 1024 / 1024 AS free_mb
FROM v$temp_space_header
GROUP BY tablespace_name
ORDER BY tablespace_name;
~~~

Numbers are a point-in-time snapshot. Temp segments are reusable; a single high-usage reading does not prove a leak.

### 9.3. Finding Sessions Using TEMP

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.module,
       u.tablespace,
       u.segtype,
       u.blocks,
       u.sql_id
FROM v$tempseg_usage u
JOIN v$session s
  ON s.saddr = u.session_addr
ORDER BY u.blocks DESC;
~~~

In RAC, use GV$TEMPSEG_USAGE and GV$SESSION, joining on INST_ID. Inspect SQL_ID and module to pinpoint the workload driving consumption.

### 9.4. Expanding TEMP

You can add a tempfile:

~~~sql
ALTER TABLESPACE temp
ADD TEMPFILE '/u02/oradata/app/temp02.dbf'
SIZE 10G
AUTOEXTEND ON
NEXT 512M
MAXSIZE 30G;
~~~

Verify physical storage before adding. High TEMP usage does not always warrant expansion: a single SQL query may spill sorts/hashes due to a bad plan, misestimated cardinality, or insufficient PGA. Investigate the SQL before provisioning massive extra temp space.

### 9.5. Handling TEMP Exhaustion

When encountering ORA-01652:
1. Identify the tablespace/tempfile and involved session/SQL_ID.
2. Check current and peak usage.
3. Inspect execution plan, sort/hash steps, parallelism, and cardinality.
4. If the workload is legitimate and storage permits, add a tempfile or extend in a controlled manner.
5. If the SQL is runaway, cancel it per procedure and fix the query/plan.
6. Confirm usage drops after the statement finishes.
7. Set alerts based on peak usage and concurrency.

Never kill a session immediately upon seeing high TEMP without verifying whether it is a critical batch job or a runaway query. Terminating a session forces rollback and can add extra load.

## 10. UNDO Tablespace and Retention

UNDO stores before-images of data for transaction rollback, read consistency, and certain recovery operations. Undo demand depends on data change rate, concurrency, transaction duration, query duration, and UNDO_RETENTION.

### 10.1. Checking Undo Configuration

~~~sql
SHOW PARAMETER undo_tablespace;
SHOW PARAMETER undo_retention;
SHOW PARAMETER undo_management;
~~~

With automatic undo management, Oracle manages extents across ACTIVE, UNEXPIRED, and EXPIRED states.

### 10.2. Monitoring Undo Extents

~~~sql
SELECT tablespace_name,
       status,
       SUM(bytes) / 1024 / 1024 AS size_mb
FROM dba_undo_extents
GROUP BY tablespace_name, status
ORDER BY tablespace_name, status;
~~~

ACTIVE extents belong to ongoing transactions. UNEXPIRED extents remain within the retention period; EXPIRED extents can be reused. Reclaiming UNEXPIRED extents depends on configuration, retention guarantee, and space pressure.

### 10.3. Monitoring V$UNDOSTAT

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
ORDER BY begin_time DESC;
~~~

V$UNDOSTAT provides interval-based statistics commonly used to track undo generation, query lengths, tuned retention, and undo errors. Inspect multiple intervals, not just the latest row.

### 10.4. ORA-30036 and ORA-01555

- ORA-30036: unable to extend segment in undo tablespace.
- ORA-01555: snapshot too old; query cannot read required older data version.

Both errors relate to undo pressure, yet have different triggers. ORA-01555 can result from long-running queries, overwritten undo, heavy DML, or mismatched retention/space sizing. Increasing UNDO_RETENTION alone without adding space or tuning workloads may fail to solve it.

### 10.5. Remediation Approach

- Measure hourly/daily undo generation.
- Identify long-running transactions and long-running queries.
- Check UNDO_RETENTION and retention guarantee.
- Check free space and active/unexpired extent distribution.
- Expand the undo tablespace when storage allows and demand justifies it.
- Adjust batch/commit strategies if transactions are oversized, without breaking transactional semantics arbitrarily.
- Tune queries to shorten snapshot read durations where feasible.

Never manually drop undo segments or attempt to free ACTIVE extents.

## 11. Redo Logs and Archive Throughput

Redo logs directly affect write throughput and recoverability.

### 11.1. Monitoring Online Redo Logs

~~~sql
SELECT group#,
       thread#,
       sequence#,
       bytes / 1024 / 1024 AS size_mb,
       members,
       archived,
       status
FROM v$log
ORDER BY thread#, group#;
~~~

Redo log members:

~~~sql
SELECT group#,
       type,
       member,
       status
FROM v$logfile
ORDER BY group#, member;
~~~

### 11.2. Overly Frequent Log Switches

Rapid log switching creates archive and checkpoint pressure. Monitor V$LOG_HISTORY over time:

~~~sql
SELECT TRUNC(first_time, 'HH24') AS hour_start,
       COUNT(*) AS log_switches
FROM v$log_history
WHERE first_time >= SYSDATE - 1
GROUP BY TRUNC(first_time, 'HH24')
ORDER BY hour_start;
~~~

Switch counts must be interpreted alongside workload and redo log size. No single switches-per-hour target fits every database.

### 11.3. Never Delete Online Redo Logs for Space

Online redo logs are part of the active recovery lifecycle. Never delete files via the OS. To change sizes or group counts, follow proper add/drop log group procedures ensuring safe thread and log states.

## 12. Process, Session, and Transaction Limits

A database can have plenty of storage yet reject new connections due to process/session caps.

### 12.1. Checking Resource Limits

~~~sql
SELECT resource_name,
       current_utilization,
       max_utilization,
       limit_value
FROM v$resource_limit
WHERE resource_name IN (
    'processes',
    'sessions',
    'transactions'
)
ORDER BY resource_name;
~~~

MAX_UTILIZATION shows the peak since instance startup or reset. It is not current usage.

### 12.2. ORA-00020 and ORA-00018

- ORA-00020: maximum number of processes exceeded (PROCESSES).
- ORA-00018: maximum number of sessions exceeded (SESSIONS).

Investigate:
- Are connection pools opening too many connections?
- Are idle sessions failing to return to pools?
- Are jobs/batches spawning excessive processes?
- Is there a connection leak or retry storm?
- Are background or parallel execution processes spiking abnormally?

Do not simply raise PROCESSES blindly. Every process consumes OS resources and can increase PGA; raising limits without checking memory and OS limits can shift failures to another layer.

### 12.3. Modifying Limits

PROCESSES generally requires an instance restart to take effect. Check ISSES_MODIFIABLE/ISSYS_MODIFIABLE in V$PARAMETER or release documentation before planning.

~~~sql
SELECT name,
       value,
       issys_modifiable,
       isinstance_modifiable
FROM v$parameter
WHERE name IN ('processes', 'sessions');
~~~

Check exact column names in V$PARAMETER for your release; ISSES_MODIFIABLE and ISSYS_MODIFIABLE are commonly available. Never alter parameters without knowing restart requirements and impact.

## 13. SGA, PGA, and Operating System Memory

Memory pressure causes failures even with abundant disk space. Distinguish shared SGA from process-private PGA.

### 13.1. Monitoring SGA

~~~sql
SELECT name,
       bytes / 1024 / 1024 AS mb
FROM v$sgainfo
ORDER BY name;
~~~

V$SGAINFO reports SGA component sizes. Inspect alongside V$SGASTAT, shared pool, buffer cache, and the alert log to identify which component is growing.

### 13.2. Monitoring PGA

~~~sql
SELECT name,
       value,
       unit
FROM v$pgastat
ORDER BY name;
~~~

Metrics such as total PGA allocated, maximum PGA allocated, aggregate PGA target parameter, and over allocation count help evaluate PGA pressure. Always read units from the UNIT column.

### 13.3. ORA-04031 and ORA-04030

- ORA-04031: Oracle could not allocate requested shared memory, typically involving SGA/shared pool or a specific pool.
- ORA-04030: OS process could not allocate private memory/PGA.

Investigate:
- Alert log and trace files.
- V$SGASTAT or V$PGASTAT.
- SQL with massive sorts/hashes.
- Process/session counts and parallelism.
- OS memory, swap/pagefile, and OS process limits.
- SGA/PGA configuration and memory target.

Never raise SGA/PGA by guesswork. Expanding one area can starve another or push the OS into heavy swapping.

## 14. CPU and I/O Are Also Capacity

Capacity planning is not solely about gigabytes. CPU and storage throughput can saturate well before disk capacity runs out.

### 14.1. CPU

Monitor:
- Host CPU utilization.
- Run queue and CPU saturation.
- DB CPU and DB time.
- Parallel execution.
- Runnable process count.
- Throughput and response time per service.

A host at 90% CPU may be efficiently serving load or severely overloaded; inspect latency, run queues, and SLAs. Low average CPU can conceal a single hot core or brief bursty peaks.

### 14.2. I/O

Monitor:
- IOPS and MB/s.
- Read/write latency.
- Queue depth.
- ASM disk group throughput.
- Datafile/redo/archive I/O.
- Storage paths and multipath health.

Abundant free space does not guarantee fast I/O. When latency rises, queries slow down even without ORA-01653 or a full filesystem.

### 14.3. Backup Window and Recovery Capacity

Backups consume I/O, CPU, network, and FRA space. Schedule backups so they do not breach application SLAs while still finishing inside the allotted window and meeting RPO/RTO.

Recovery capacity includes:
- Available backup sets and archived redo.
- Space required to restore/recover.
- Restore throughput from storage/network.
- Staffing and tested runbooks.
- Ability to open the database after recovery.

Never treat a successful backup as proof that recovery meets RTO; conduct periodic restore/recovery drills.

## 15. Designing Alert Thresholds

Effective thresholds create enough lead time to act, avoid false alarms, and point directly to next steps.

### 15.1. Combining Multiple Threshold Types

Use them together:

1. **Percentage threshold:** proportion used.
2. **Absolute free threshold:** minimum remaining free capacity.
3. **Time-to-full threshold:** days/hours remaining at current growth rate.
4. **Growth-rate threshold:** abnormal surge in growth velocity.
5. **Operational threshold:** time remaining before maintenance/backup windows or business deadlines.

For example, a tablespace at 85% with 500 GB free growing at 1 GB/month is less urgent than a tablespace at 65% with only 2 GB usable growing at 1 GB/hour.

### 15.2. Warning and Critical

Illustrative thresholds:

| Level | Example Condition | Action |
| --- | --- | --- |
| Normal | Below warning with sufficient runway | Routine monitoring |
| Warning | 80% used or time-to-full under 30 days | Open ticket, assign owner, plan expansion |
| Critical | 90% used or time-to-full under 7 days | Escalate immediately, provision capacity, or curb growth |
| Emergency | Minimal headroom left or resource hit limit | Trigger incident runbook |

Percentages and day counts are examples only. Calibrate to growth rate, infrastructure team response time, storage procurement/provisioning lead time, workload peaks, and database criticality.

### 15.3. Hysteresis to Prevent Flapping

If an alert triggers at 80% and clears immediately at 79.9%, oscillating usage causes continuous alert flapping.

Example:
- Warning triggers at 80%, clears at 75%.
- Critical triggers at 90%, clears at 85%.

Setting the clear threshold below the trigger threshold creates hysteresis. You can also require multiple consecutive samples above threshold to fire and multiple consecutive samples below the clear threshold to resolve.

### 15.4. Using Observation Windows

A 10-second spike rarely warrants paging. You can require:
- Threshold breached for 2–3 consecutive samples.
- Or immediate alert if an absolute free-space danger threshold is crossed.
- Critical alerts bypass delay timers when a resource is exhausted or writes fail.

Tune observation periods to how fast each resource moves. TEMP can saturate in minutes; daily-growing tablespaces can use longer windows.

### 15.5. Alerts Must Include Owner and Action

An actionable alert includes:
- Database/instance/PDB.
- Resource/tablespace/disk group.
- Current used/free/max values.
- Growth rate and time-to-full.
- Metric observation window.
- Alert timestamp and severity.
- Runbook link or recommended action.
- Owner and escalation target.

An alert saying merely "Tablespace 90%" forces the responder to hunt down all context manually.

## 16. Thresholds by Resource Type

### 16.1. Permanent Tablespaces

Monitor:
- Used percent of allocated.
- Used percent of maximum usable.
- Free bytes.
- Largest free extent when relevant.
- Datafile maxsize.
- ASM/filesystem headroom.
- Time-to-full.

### 16.2. TEMP

Monitor:
- Current/peak usage.
- Free tempfile capacity.
- Autoextend headroom.
- Active sessions/SQL_IDs consuming TEMP.
- Hourly growth rate and peak concurrency.

TEMP alerts should distinguish single-query spikes from rising baseline usage. If TEMP hits 100% in minutes, daily warnings arrive too late.

### 16.3. UNDO

Monitor:
- Undo tablespace usage.
- ACTIVE/UNEXPIRED/EXPIRED extents.
- Undo generation rate.
- Longest query and longest transaction.
- SSOLDERRCNT and NOSPACEERRCNT.
- Tuned undo retention.

### 16.4. FRA and Archive Destinations

Monitor:
- SPACE_USED / SPACE_LIMIT.
- SPACE_RECLAIMABLE.
- Archive generation rate.
- Backup age and backup success.
- Standby transport/apply lag.
- Destination STATUS/ERROR.
- Remaining hours until FRA is full.

### 16.5. ASM/Filesystems

Monitor:
- Usable_file_mb and free_mb.
- Filesystem bytes and inodes.
- Volume growth.
- Latency and errors.
- Space reserved for mirroring/rebalancing.
- Thin pool/SAN capacity.

### 16.6. Processes/Sessions

Monitor:
- Current utilization.
- Max utilization.
- Limit value.
- Connection pool active/idle/wait counts.
- Sessions grouped by username/module/program.
- Login rates and retry storms.

### 16.7. PGA/SGA/CPU/I/O

Monitor:
- PGA allocation and over allocation.
- SGA component allocation.
- OS available memory/swap.
- CPU utilization and run queue.
- I/O latency/throughput.
- DB time, DB CPU, and response time.

Never apply a single universal memory percentage threshold across every setup. Account for OS, agents, backups, Grid Infrastructure, and other instances sharing the host.

## 17. Oracle Alerting and Monitoring Tools

### 17.1. Enterprise Manager

Oracle Enterprise Manager can monitor tablespaces, FRA, host filesystems, ASM, sessions/processes, availability, and more. Configure:
- Warning/critical thresholds.
- Metric collection intervals.
- Notification rules.
- Incident rules.
- Escalation and suppression.
- Alert owner/team.

Do not enable every metric at high frequency without evaluating overhead and alert noise.

### 17.2. DBMS_SERVER_ALERT

Oracle provides DBMS_SERVER_ALERT to configure certain server-generated metric thresholds. Look up supported metrics in V$METRICNAME and your exact release's package documentation.

Fields to confirm before calling the API:
- Metric ID.
- Object type and object name.
- Instance scope.
- Warning/critical operators and values.
- Observation period.
- Consecutive occurrences.
- Message and threshold status.

Syntax and supported metrics vary by release. Check the package specification in the target database and its release documentation; never copy metric IDs or parameters unverified from another version.

### 17.3. Viewing Outstanding Alerts

~~~sql
SELECT reason,
       suggested_action,
       object_type,
       object_name,
       message_level,
       creation_time
FROM dba_outstanding_alerts
ORDER BY creation_time DESC;
~~~

This view shows unresolved alerts. Verify privileges and column names for your release. Never clear/delete alerts just to turn a dashboard green; resolve the root cause and confirm metrics return to safe levels.

### 17.4. Alert Log

Check diagnostic locations:

~~~sql
SELECT name,
       value
FROM v$diag_info
WHERE name IN ('Diag Trace', 'Diag Alert');
~~~

The alert log records critical events such as archive errors, datafile errors, recovery, space-related errors, and startup/shutdown. During a capacity incident, record the ORA code, file path, tablespace, process, and timestamp.

### 17.5. External Monitoring

Metrics can be shipped to centralized monitoring platforms. Collector design:
- Run read-only queries at reasonable intervals.
- Record timestamps and instance identity.
- Do not open a separate connection per metric.
- Enforce query timeouts.
- Implement timeouts and retries with backoff.
- Retain telemetry when the database is temporarily unreachable.
- Detect missing collector heartbeats.

If monitoring stops collecting, a dashboard showing "zero alerts" does not mean the database is healthy. Alert on the monitoring pipeline itself.

## 18. Resource Exhaustion Response Workflow

During an incident, the primary goal is restoring safe operation. Never change multiple parameters simultaneously, as that obscures root cause and can worsen the outage.

### 18.1. Step 1 — Identify Resource and Scope

Record:
- ORA error and SQL_ID if available.
- DBID, DB_UNIQUE_NAME, instance, host.
- PDB/container and service.
- Exact tablespace/file/disk group/destination.
- Start time and associated workload.
- Blast radius: single batch, single PDB, or entire database.

### 18.2. Step 2 — Verify Actual State

Check:
- Current used/free space.
- AUTOEXTEND and MAXSIZE.
- Physical storage headroom.
- Resource limits.
- Growth rate.
- Alert log and monitoring history.
- Whether backup/recovery files must be retained.

Never perform cleanup based solely on an old alert. Space may already have been released or the alert may reflect a finished spike.

### 18.3. Step 3 — Choose Low-Risk Containment

Options depending on resource:
- Add a datafile/tempfile if storage has space.
- Raise the FRA limit after confirming physical storage capacity.
- Reclaim eligible backups/archives via RMAN.
- Stop or throttle abnormal jobs/queries per change/incident policy.
- Lower concurrency or defer non-essential batches.
- Expand ASM/filesystems/volumes through the infrastructure team.
- Raise process/session limits per plan if sufficient memory and OS limits exist.

Never delete database files directly via OS commands, delete active online redo logs, or truncate business data without authorization.

### 18.4. Step 4 — Verify Recovery

After containment:
- Does the failing statement now succeed?
- Is the archive destination functioning?
- Has TEMP usage dropped or does ample headroom exist?
- Can the tablespace allocate new extents?
- Can new sessions/processes connect?
- Have fresh alerts stopped firing?
- Have application latency and throughput recovered?

### 18.5. Step 5 — Determine Root Cause

Categorize:
- Normal organic growth lacking capacity planning.
- Misconfigured autoextend/MAXSIZE.
- Physical storage exhausted.
- Failed retention/cleanup jobs.
- Runaway query/job.
- Connection leak or retry storm.
- Changed data load/partition lifecycle.
- Backup/standby lag.
- Delayed monitoring/alerting.

Post-incident, update forecasts, thresholds, runbooks, and ownership.

## 19. Runbook: Tablespace Exhausted

Common errors:
- ORA-01653: unable to extend table.
- ORA-01654: unable to extend index.
- ORA-01658: unable to create initial extent.

### 19.1. Identify Tablespace and Files

~~~sql
SELECT tablespace_name,
       file_name,
       bytes,
       autoextensible,
       maxbytes
FROM dba_data_files
WHERE tablespace_name = :tablespace_name
ORDER BY file_name;
~~~

~~~sql
SELECT tablespace_name,
       SUM(bytes) AS free_bytes,
       MAX(bytes) AS largest_free_extent
FROM dba_free_space
WHERE tablespace_name = :tablespace_name
GROUP BY tablespace_name;
~~~

### 19.2. Check Physical Storage

If files sit on ASM, check disk group usable capacity. If on a filesystem, check mount point, inodes, and quotas. Confirm storage can accommodate expansion before running ALTER DATABASE.

### 19.3. Choose Remediation

- Resize files if physical headroom exists and files have not hit limits.
- Enable AUTOEXTEND with controlled NEXT/MAXSIZE.
- Add a datafile for smallfile tablespaces.
- For bigfile, resize the single datafile within limits.
- Review purge/archive/partition lifecycle if expired data exists.
- Investigate abnormally growing segments via DBA_SEGMENTS.

Never drop segments to free space without owner confirmation and retention clearance.

## 20. Runbook: FRA or Archive Destination Full

Errors may include ORA-19809, ORA-19804, and ORA-00257.

### 20.1. Identify Space Consumers

~~~sql
SELECT name,
       space_limit,
       space_used,
       space_reclaimable,
       number_of_files
FROM v$recovery_file_dest;
~~~

~~~sql
SELECT file_type,
       percent_space_used,
       percent_space_reclaimable,
       number_of_files
FROM v$flash_recovery_area_usage;
~~~

### 20.2. Check Archive Destinations

~~~sql
SELECT dest_id,
       status,
       destination,
       error
FROM v$archive_dest_status
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
~~~

Check failing destinations, network/standby status, and archive generation rate.

### 20.3. Reclaim per RMAN Policy

- Check the latest backup and retention policy.
- Confirm archived logs are backed up and applied on standby if required by deletion policy.
- Use RMAN REPORT OBSOLETE and DELETE OBSOLETE per policy.
- If archives must be backed up before deletion, ensure the backup succeeds and is verified.
- If storage is insufficient, provision more space or adjust destinations in a controlled manner.

Never delete archived logs via OS commands, and never loosen deletion policies merely to clear alerts.

## 21. Runbook: TEMP Exhausted

Common error: ORA-01652, unable to extend temp segment.

1. Identify the TEMP tablespace and tempfiles.
2. Query V$TEMP_SPACE_HEADER.
3. Query V$TEMPSEG_USAGE to find sessions/SQL_IDs.
4. Inspect execution plan, sort/hash operations, parallelism, and intermediate data volumes.
5. If the query is valid and storage permits, add a tempfile or extend existing ones.
6. If the query is runaway, coordinate with the owner to cancel or adjust workload.
7. Confirm temp segments are released/reused after statement completion.
8. Configure alerts on peak usage and growth rate.

Do not confuse a full TEMP tablespace with a full permanent tablespace. Adding a permanent datafile will not resolve TEMP exhaustion.

## 22. Runbook: UNDO Exhausted or Snapshot Too Old

Common errors:
- ORA-30036.
- ORA-01555.

1. Inspect DBA_UNDO_EXTENTS by status.
2. Inspect V$UNDOSTAT by interval.
3. Identify long-running transactions and long-running queries.
4. Check undo generation rate and peaks.
5. Check UNDO_RETENTION and RETENTION GUARANTEE.
6. Expand capacity if the workload is valid and storage permits.
7. Tune queries/batches/transactions per business requirements.
8. Monitor SSOLDERRCNT and NOSPACEERRCNT after changes.

Never kill transactions or alter retention guarantee without understanding the impact on read consistency and active transactions.

## 23. Runbook: Process/Session Limits

Common errors: ORA-00020 or ORA-00018.

1. Query V$RESOURCE_LIMIT.
2. Group sessions by username, machine, program, module, and status.
3. Inspect connection pool active/idle/wait counts.
4. Look for retry storms, leaks, or jobs spawning excessive processes.
5. Throttle connection creation/concurrency if needed.
6. Raise PROCESSES/SESSIONS only after evaluating memory, OS limits, and restart requirements.
7. Monitor peak utilization after recovery.

Never just raise the limit while ignoring a connection leak; the system will simply hit the new ceiling.

## 24. Runbook: Memory Exhaustion

Errors may include ORA-04031 or ORA-04030.

1. Collect the alert log and trace files.
2. Determine whether the error occurred in SGA or process PGA.
3. Inspect V$SGASTAT/V$SGAINFO or V$PGASTAT.
4. Check process/session counts, parallelism, and high-allocation SQL.
5. Check OS memory/swap.
6. Check memory targets and actual OS limits.
7. Throttle abnormal workloads or tune queries if needed.
8. Adjust memory parameters per plan and confirm restart requirements.

Never size SGA/PGA beyond OS physical capacity. Heavy swapping degrades database performance far worse.

## 25. Common Errors and Operational Meaning

| Error Code | Common Context | First Investigation Path |
| --- | --- | --- |
| ORA-01653 | Unable to extend table | Tablespace, datafile, free extents, MAXSIZE, and storage |
| ORA-01654 | Unable to extend index | Index tablespace, rebuild/maintenance, and file headroom |
| ORA-01658 | Unable to create initial extent | Tablespace and requested extent size |
| ORA-01652 | Unable to extend temporary segment | TEMP usage, SQL_ID, tempfiles, and sorts/hashes |
| ORA-30036 | Unable to extend undo segment | Undo extents, transactions, retention, and capacity |
| ORA-01555 | Snapshot too old | Query duration, undo generation, and retention |
| ORA-19809 | Limit exceeded for FRA | FRA usage, reclaimable space, backups, and archives |
| ORA-19804 | Cannot reclaim sufficient FRA space | Retention/deletion policies and retained files |
| ORA-00257 | Archiver error | Archive destinations, FRA/filesystem, and standby |
| ORA-00020 | Maximum number of processes exceeded | PROCESSES, connection pools, and process leaks |
| ORA-00018 | Maximum number of sessions exceeded | SESSIONS, pools, and session leaks |
| ORA-04031 | Unable to allocate shared memory | SGA/pools, fragmentation, and alert/trace logs |
| ORA-04030 | Process out of memory | PGA, OS memory, queries, and parallelism |
| ORA-270xx | OS I/O error | File path, permissions, storage, and OS errors |

Error codes are only a starting point. Read the full error stack, alert log, and traces to pinpoint the exact resource, file, and operation.

## 26. Governance: Ownership, Budgets, and Expansion Workflows

Capacity planning requires clear ownership across DBA, storage, OS, application, and business teams.

### 26.1. Responsibility Matrix

| Team | Responsibilities |
| --- | --- |
| DBA | Tablespaces, datafiles, TEMP, UNDO, redo, FRA, and database thresholds |
| Storage/Infrastructure | ASM backing storage, filesystems, SAN, volumes, IOPS, and capacity provisioning |
| Application team | Connection pools, queries, batches, data retention, and workload forecasts |
| Security/Compliance | Retention, auditing, backup protection, and regulated data preservation |
| Operations/NOC | Alert intake, incident routing, escalation, and tracking |
| Business owner | Growth forecasts, seasonal peaks, and retention requirements |

### 26.2. Periodic Capacity Reviews

A monthly review can cover:
- Top tablespaces by used/free/time-to-full.
- Daily/weekly/monthly growth rates.
- FRA/archive/backup retention.
- TEMP and UNDO peaks.
- ASM/filesystem headroom.
- Process/session peaks.
- CPU/I/O saturation.
- 30/60/90-day forecasts.
- Storage provisioning lead times.
- Action items and owners.

### 26.3. Expansion Request Workflow

An expansion request should state:
- Target resource to expand.
- Current used/allocated/max.
- Growth rate and forecast.
- Business justification.
- Requested additional capacity.
- Storage tier/location and redundancy.
- Backup/recovery impact.
- Cost and provisioning lead time.
- Rollback/validation plan.
- Approvers and owner.

Never bypass shared storage provisioning governance with an ad-hoc ALTER TABLESPACE command.

## 27. Alert Design Checklist

Before promoting a threshold to production, confirm:

1. Metric accurately represents the target resource.
2. Units and scope are unambiguous.
3. Absolute free threshold is defined.
4. Percentage threshold is defined.
5. Time-to-full threshold is defined where growth is measurable.
6. Peak baseline is factored in.
7. Warning fires early enough for provisioning lead time.
8. Critical fires early enough for containment.
9. Hysteresis and consecutive sample rules are configured.
10. Known maintenance windows have appropriate exceptions.
11. Owner and escalation path are defined.
12. Linked runbook exists.
13. Collector/monitoring pipeline failures trigger alerts.
14. Alert delivery has been tested.
15. False positives/false negatives are reviewed periodically.

## 28. Resource Exhaustion Checklist

- [ ] Identify exact database, instance, PDB, and host.
- [ ] Record ORA error, timestamp, and SQL_ID/session if available.
- [ ] Verify current used/free values and peak levels.
- [ ] Check AUTOEXTEND, MAXSIZE, and file states.
- [ ] Check ASM/filesystem/quotas/inodes.
- [ ] Check growth rate and time-to-full.
- [ ] Identify segments/jobs/queries driving growth.
- [ ] Verify backup, archive, and standby retention before any cleanup.
- [ ] Choose low-risk containment.
- [ ] Notify owners and log the change.
- [ ] Confirm database/application recovery.
- [ ] Re-verify metrics post-incident.
- [ ] Update forecasts, thresholds, and runbooks.

## 29. Practical Example: Calculating Time-to-Full for a Tablespace

Suppose a tablespace has:
- Current used: 720 GB.
- Configured usable ceiling: 900 GB.
- Physical storage still available to grant to datafiles: 120 GB.
- 7-day average growth rate: 4 GB/day.
- Storage provisioning lead time: 10 business days.

File/database headroom is 180 GB, yet physical headroom is only 120 GB. The lower usable headroom is 120 GB.

\[
TimeToFull = 120 / 4 = 30\ days
\]

Accounting for 10 business days to provision, plus change/validation time and peak buffers, warnings must trigger earlier than 30 days. A flat 80% threshold alone may misrepresent actual remaining runway.

If the high-scenario growth rate is 8 GB/day:

\[
TimeToFull_{high} = 120 / 8 = 15\ days
\]

Planning should follow the High scenario whenever that workload is plausible.

## 30. Practical Example: Designing Thresholds for the FRA

Suppose:
- FRA limit: 2 TB.
- Used: 1.2 TB.
- Reclaimable: 300 GB.
- Archive generation: 80 GB/day.
- Nightly backups.
- Storage provisioning lead time: 5 days.

Do not assume 300 GB reclaimable equals 300 GB guaranteed deletable immediately. Check file types, backup policies, and standby apply. If only 500 GB of non-reclaimable headroom remains, time-to-full at the archive generation rate is roughly 6.25 days. Warnings must fire promptly so DBAs can verify backup/archive policies and storage teams can prepare expansion.

Alerts should include:
- FRA used percent.
- Non-reclaimable bytes.
- Archive generation rate.
- Backup age/success.
- Standby apply lag.
- Forecast time-to-full.

## 31. Self-Practice Exercises

1. Distinguish logical capacity from physical capacity.
2. Explain why AUTOEXTEND does not guarantee a datafile can grow.
3. List the components required in a capacity baseline.
4. Calculate growth/day when used space increases by 60 GB over 12 days.
5. Calculate time-to-full given 240 GB headroom and 8 GB/day growth.
6. Why model base, high, and stress scenarios?
7. List factors affecting table/index growth.
8. Why do index rebuilds require peak storage sizing?
9. Write a query inspecting datafiles, MAXBYTES, and AUTOEXTENSIBLE.
10. Write a query summarizing free extents for permanent tablespaces.
11. Explain the limitations of theoretical autoextend headroom.
12. Distinguish bigfile and smallfile tablespaces during expansion.
13. Write the command to add a datafile to a smallfile tablespace.
14. Why must datafiles never be deleted via OS commands?
15. Explain how ASM USABLE_FILE_MB differs from FREE_MB.
16. Write a query checking FRA usage and reclaimable space.
17. Why must archived redo logs never be deleted directly via OS commands?
18. Distinguish TEMP exhaustion from permanent tablespace exhaustion.
19. Write a query finding sessions consuming TEMP by SQL_ID.
20. Distinguish ACTIVE, UNEXPIRED, and EXPIRED undo extents.
21. Explain the relationship between ORA-30036 and ORA-01555.
22. Write a query inspecting V$UNDOSTAT.
23. Write a query checking current and peak PROCESSES/SESSIONS utilization.
24. Why can increasing PROCESSES trigger memory pressure?
25. Distinguish ORA-04031 from ORA-04030.
26. Design warning/critical thresholds with hysteresis for a tablespace.
27. Why is time-to-full often more informative than percentage alone?
28. Draft a runbook for handling ORA-00257.
29. Design a monthly capacity review for a RAC database with multiple PDBs.
30. Write a 90-day plan combining growth forecasts, storage lead times, alerts, owners, and expansion actions.

**Capacity planning must connect Oracle metrics with physical storage limits, growth velocity, and operational response times.** Track allocated/used/free space, autoextend/MAXSIZE, ASM/filesystems, FRA, TEMP, UNDO, processes, and memory at the proper scope; configure thresholds combining percentage, remaining capacity, and time-to-full. When a resource is exhausted, identify the exact resource and cause, apply safe containment, confirm service recovery, and then update forecasts, alerts, and runbooks so the incident does not recur.
