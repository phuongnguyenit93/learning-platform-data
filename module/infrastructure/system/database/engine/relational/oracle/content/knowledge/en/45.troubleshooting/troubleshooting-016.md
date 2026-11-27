# Slow Commits, Redo Log Switches, and Recovery Area Bottlenecks

Slow commits, stalled redo log switches, and a full Fast Recovery Area (FRA) frequently appear together in Oracle Database incidents. They are linked because Oracle must write redo to ensure transactions are recoverable, switch to the next redo log group, and archive redo logs when running in `ARCHIVELOG` mode. However, each symptom has its own causes and remedies.

When an application reports commits taking multiple seconds, determine whether foreground sessions are waiting on LGWR to flush redo, LGWR is slowed by storage, the database cannot switch logs fast enough, or synchronous Data Guard is waiting for standby acknowledgment. When log switches stall, distinguish incomplete checkpoints from failed archive destinations. When the FRA fills up, identify which file types consume space and which files can actually be reclaimed under backup, archive, and flashback policies.

Core principles:

- `COMMIT` must ensure required redo is written durably under the configured commit semantics.
- The `log file sync` wait event typically indicates foreground sessions waiting for LGWR to finish flushing commit redo.
- The `log file parallel write` wait event reflects LGWR waiting on redo log writes to storage.
- Log switches are normal; overly frequent switches or inability to reuse log groups require investigation.
- A full FRA blocks archive log writes, preventing log groups from being reused and impacting transactions or halting the database.
- Never delete files inside the FRA using OS commands to free space. Use RMAN and proper retention/deletion policies.
- Never switch `COMMIT` to `NOWAIT`, disable `ARCHIVELOG`, or weaken Data Guard protection merely to mask symptoms.

## 1. The Path of a COMMIT in Oracle

Oracle uses redo to record information needed to recover changes. As a transaction modifies data blocks, redo entries are generated in the SGA redo log buffer. When the transaction commits, Oracle writes a commit record into redo and signals LGWR to flush the required redo to the online redo log.

Simplified model:

    Client application
          |
          | COMMIT
          v
    Foreground server process
          |
          | commit record / redo
          v
    Redo log buffer (SGA)
          |
          | request LGWR flush
          v
    LGWR process
          |
          | synchronous write
          v
    Online redo log files
          |
          | durable commit acknowledgment
          v
    Foreground returns success
          |
          v
    Client receives COMMIT success

Under the common default `WAIT` commit semantics, the foreground returns success only after LGWR writes the required redo per Oracle durability guarantees. Oracle can group multiple concurrent commits into a single write (group commit), so not every transaction triggers a separate I/O.

### 1.1. Redo Log Buffer

The redo log buffer is an SGA memory area holding redo entries before LGWR writes them to online redo logs. Foreground processes generate redo during data changes and place it into the buffer.

The redo buffer is not durable storage. If an instance fails before required redo is written to the online redo log, changes not yet protected by durable redo are lost; Oracle uses redo and undo to recover database state after a crash.

If LGWR cannot keep up with redo generation, foreground sessions wait for space in the redo log buffer. The typical wait event is `log buffer space`. This differs from `log file sync`: one waits for buffer space to write redo, while the other waits for LGWR to complete a commit flush.

### 1.2. LGWR

LGWR (Log Writer) writes redo from the redo log buffer to online redo log files. LGWR triggers on several conditions, including commit requests, buffer space pressure, and internal thresholds.

When a transaction commits, the foreground signals LGWR that redo up through the commit record must be flushed. LGWR can batch requests from multiple transactions into one write—group commit—reducing total I/O when many sessions commit close together.

If redo storage has high latency, LGWR writes slowly and foreground sessions wait longer. If LGWR suffers CPU starvation, scheduling delays, or resource contention, commits also slow down even when storage is not the sole culprit.

### 1.3. Online Redo Logs

Online redo logs consist of multiple groups, each with one or more members. Oracle writes redo to the current group per thread; when a group fills or a switch is requested, the database moves to the next group.

Members within the same group are multiplexed copies protecting against single-file/member failures. Adding members does not increase a group's redo capacity; it increases redo log fault tolerance. Only increasing group size or adding groups changes how long before a group is reused.

### 1.4. Archived Redo Logs

In `ARCHIVELOG` mode, before an online redo log group can be reused, Oracle must archive that group's redo per archive destination policies. `ARCn` or the appropriate archiving process reads the online redo log and produces an archived redo log.

Archived redo logs are vital for media recovery, backups, and Data Guard. If an archive destination becomes unavailable or runs out of space, Oracle cannot reuse needed log groups.

### 1.5. Fast Recovery Area (FRA)

The Fast Recovery Area is an Oracle-managed storage area for recovery-related files such as archived redo logs, flashback logs, RMAN backup pieces, control file autobackups, and other recovery files depending on configuration.

The FRA has a configured size limit. Upon reaching capacity, Oracle attempts to reclaim eligible files per retention and deletion policies. If no reclaimable files remain and new files cannot be written, archiving or backups fail.

## 2. Understanding Commit and Redo Wait Events

To diagnose accurately, first distinguish foreground waits, LGWR I/O, and log switch/archive waits.

| Wait Event | Common Meaning | Investigation Focus |
|---|---|---|
| `log file sync` | Foreground waiting for LGWR to finish flushing commit redo | Commit frequency, LGWR latency, storage, CPU scheduling, Data Guard |
| `log file parallel write` | LGWR waiting on online redo log writes to storage | Redo storage latency, I/O path, multipath/ASM, devices |
| `log buffer space` | Foreground waiting for space in redo log buffer | Redo generation rate, LGWR throughput, buffer pressure |
| `log file switch (checkpoint incomplete)` | Cannot reuse group because checkpoint is incomplete | Checkpoints, DBWR, datafile I/O, log size/group count |
| `log file switch (archiving needed)` | Group cannot be reused because archiving has not finished | ARCn, archive destinations, FRA, Data Guard/archive policies |
| `log file switch completion` | Foreground waiting for a log switch to complete | Switch operation, checkpoints, archiving, group availability |

Exact event names and instrumentation details may vary by Oracle release. Verify the exact events appearing in `V$SESSION`, `V$SYSTEM_EVENT`, and release documentation.

### 2.1. log file sync

This is the classic wait event observed when applications report slow commits. Foreground sessions wait for LGWR confirmation that redo was flushed per commit mode.

Possible causes:

- High latency on redo log storage.
- LGWR CPU scheduling delays or resource contention.
- Application committing overly frequently, generating many tiny requests.
- High concurrency of committing sessions generating heavy redo loads.
- Data Guard synchronous transport adding acknowledgment latency.
- Virtualization or storage issues affecting synchronous writes.
- Contention or queuing at the I/O layer.

Do not conclude storage is slow solely because `log file sync` rises. Cross-check with `log file parallel write` and storage I/O metrics.

### 2.2. log file parallel write

This event measures how long LGWR waits on redo log write I/Os. If this event spikes at the exact same time as `log file sync`, the redo storage path is a primary suspect.

Check:

- Write latency of the volume or ASM disk group hosting redo logs.
- IOPS and queue depth.
- Throughput and write-cache policy.
- SAN/NVMe/virtual disk health.
- Multipath path failovers or degraded paths.
- Storage contention with datafiles, archive logs, and backups.
- Latency differences across members of the same log group.

Redo logs are far more sensitive to write latency than raw throughput. Workloads with many small commits issue frequent synchronous writes; high-latency storage degrades response times even when bandwidth looks idle.

### 2.3. log buffer space

This event indicates foregrounds cannot allocate space in the redo buffer fast enough. It occurs when redo generation outpaces LGWR flushing the buffer.

Investigate:

- Whether LGWR is stalled on storage.
- Redo generation spikes from bulk DML, index maintenance, or batches.
- Whether `redo buffer allocation retries` is climbing.
- Transactions or workloads generating massive redo.
- Storage or CPU saturation.

Increasing `LOG_BUFFER` is not the first fix. If LGWR cannot flush redo fast enough, a larger buffer only delays the bottleneck while consuming more memory. Find why LGWR throughput is low first.

### 2.4. log file switch (checkpoint incomplete)

Oracle tries to advance to the next group, yet that group cannot be reused because the checkpoint associated with its earlier cycle has not finished. DBWR must flush the corresponding dirty buffers to datafiles for the checkpoint to advance.

Possible causes:

- Redo log groups are too small for the redo generation rate.
- Too few log groups, leaving short intervals before reuse.
- Slow datafile storage writes.
- DBWR facing CPU/I/O contention.
- Workloads generating sharp redo bursts.

Increasing redo log size lengthens the interval between switches; adding groups extends the time before a group is reused. However, if datafile I/O or DBWR is the bottleneck, address checkpoint/storage throughput rather than just adding log groups.

### 2.5. log file switch (archiving needed)

Oracle needs to reuse a group, yet archiving for that group has not completed or the archive destination cannot accept files.

Common causes:

- FRA is full.
- Archive destination filesystem or ASM disk group is full.
- Archive destination failed or unmounted.
- ARCn lacks capacity for the redo generation rate.
- Network destination or standby archive transport is failing.
- Deletion policy blocks deleting archived logs because they are not yet backed up or applied on standby.

In this case, adding redo log groups only postpones the stall without fixing why the archive destination cannot write. Restore archiving immediately.

## 3. Measuring Commit Latency and Redo I/O

Never rely on a single snapshot. Collect metrics over intervals to spot trends, compare normal hours against incident hours, and distinguish isolated sessions from instance-wide bottlenecks.

### 3.1. View Waiting Foreground Sessions

    SELECT
        sid,
        serial#,
        username,
        module,
        action,
        event,
        wait_class,
        state,
        seconds_in_wait,
        blocking_session
    FROM v$session
    WHERE wait_class <> 'Idle'
      AND event IN (
        'log file sync',
        'log file switch completion',
        'log file switch (checkpoint incomplete)',
        'log file switch (archiving needed)',
        'log buffer space'
      )
    ORDER BY seconds_in_wait DESC;

This query shows sessions waiting at the moment of execution; it is not a wait history. Brief waits may finish before the DBA runs the query.

Instrumenting `MODULE`/`ACTION` in applications identifies which service or code path drives commits. If every session shares one database user with no module set, pinpointing the caller becomes much harder.

### 3.2. Compare Total Waits and Average Wait

    SELECT
        event,
        total_waits,
        ROUND(time_waited_micro / 1000000, 2) AS total_wait_seconds,
        ROUND(
          time_waited_micro / NULLIF(total_waits, 0) / 1000,
          3
        ) AS average_wait_ms
    FROM v$system_event
    WHERE event IN (
      'log file sync',
      'log file parallel write',
      'log buffer space',
      'log file switch completion',
      'log file switch (checkpoint incomplete)',
      'log file switch (archiving needed)'
    )
    ORDER BY time_waited_micro DESC;

Values in `V$SYSTEM_EVENT` are cumulative counters since instance startup or counter reset. Taking two snapshots apart and computing deltas is far more informative than reading totals since startup.

Average wait times can mask tail latency. When wait histograms or wait history are available, inspect p95/p99 distributions instead of averages alone.

### 3.3. Wait Event Histograms

    SELECT
        event,
        wait_time_milli,
        wait_count
    FROM v$event_histogram
    WHERE event IN (
      'log file sync',
      'log file parallel write'
    )
    ORDER BY event, wait_time_milli;

Histograms show wait counts across latency buckets, exposing high-latency commit spikes even when averages look modest. Exact bucket interpretation depends on view and release; check documentation accordingly.

### 3.4. Redo and Commit Statistics

    SELECT
        name,
        value
    FROM v$sysstat
    WHERE name IN (
      'user commits',
      'user rollbacks',
      'redo size',
      'redo entries',
      'redo writes',
      'redo write time',
      'redo log space requests',
      'redo log space wait time',
      'redo buffer allocation retries'
    )
    ORDER BY name;

These are also cumulative counters. Compare deltas between two timestamps to see how workload shifts. Some timing statistics are measured in centiseconds or specific units; check Oracle documentation before computing latency from raw numbers.

Key metrics:

- Rapidly rising `user commits` shows commit transaction volume.
- `redo size` shows total redo bytes generated.
- `redo writes` and `redo write time` reflect LGWR write activity.
- `redo log space requests`/`wait time` indicate foregrounds waiting on redo buffer or log space.
- Rising `redo buffer allocation retries` signals LGWR and redo buffer pressure.

Look beyond total `redo size`. A system generating heavy redo with few commits exhibits a very different latency profile from one generating little redo yet committing thousands of times per second.

### 3.5. Inspect LGWR Process and I/O

    SELECT
        p.spid,
        p.program,
        s.event,
        s.state,
        s.seconds_in_wait
    FROM v$process p
    JOIN v$session s
      ON s.paddr = p.addr
    WHERE UPPER(p.program) LIKE '%LGWR%';

Process naming varies by platform and release. Check background processes via `V$BGPROCESS` or the OS as needed. Correlate with OS/storage metrics to determine whether LGWR is waiting on I/O, CPU, or another condition.

## 4. Checking Redo Log Groups and Log Switch Frequency

### 4.1. View Online Redo Log Groups

    SELECT
        group#,
        thread#,
        sequence#,
        ROUND(bytes / 1024 / 1024) AS size_mb,
        members,
        archived,
        status,
        first_time
    FROM v$log
    ORDER BY thread#, group#;

Common statuses are `CURRENT`, `ACTIVE`, `INACTIVE`, and `UNUSED`. `CURRENT` is the group actively receiving redo. `ACTIVE` may still be needed for instance recovery/checkpointing; `INACTIVE` is no longer needed for instance recovery and is eligible for reuse once archived.

`ARCHIVED` shows group archival status in the view's context. Combine it with log history and archive destination status to get the full picture.

### 4.2. View Redo Log Members and Paths

    SELECT
        group#,
        type,
        member,
        status,
        is_recovery_dest_file
    FROM v$logfile
    ORDER BY group#, member;

Verify each group has the required members per redundancy architecture. Members of the same group should reside on separate failure domains if single-device failure protection is required. Placing two members on the exact same filesystem or disk group defeats multiplexing protection.

Adding members does not increase group size or extend switch intervals; it provides log-file multiplexing redundancy.

### 4.3. Count Log Switches per Hour

    SELECT
        TRUNC(first_time, 'HH24') AS switch_hour,
        thread#,
        COUNT(*) AS switch_count
    FROM v$log_history
    WHERE first_time >= SYSDATE - 2
    GROUP BY TRUNC(first_time, 'HH24'), thread#
    ORDER BY switch_hour, thread#;

Compare switch frequency against redo generation and workload. No single switch interval fits every database; switches packed closely together under normal load suggest log groups are undersized or workloads spiked.

### 4.4. Measure Time Between Log Switches

    SELECT
        thread#,
        sequence#,
        first_time,
        first_time - LAG(first_time) OVER (
          PARTITION BY thread#
          ORDER BY first_time
        ) AS interval_days
    FROM v$log_history
    WHERE first_time >= SYSDATE - 1
    ORDER BY thread#, first_time;

`INTERVAL_DAYS` is expressed in days; multiply by 1440 for minutes. Inspect both the shortest switch intervals and peak workload timestamps.

### 4.5. Normal Log Switches vs. Problematic Log Switches

Log switches occur whenever a redo log group fills or a switch is requested. Switching is normal. Investigate when:

- Switches happen excessively fast under routine load.
- Foregrounds experience long waits during switches.
- The next group is not ready for reuse.
- Archive logs cannot be written in time.
- Checkpoints fail to complete before the group is needed again.

Never try to eliminate log switches completely. The goal is sizing and provisioning enough groups so archiving and checkpoints keep pace with redo generation.

## 5. Diagnosing Each Type of Log Switch Wait

### 5.1. Checkpoint Incomplete

Check wait events and log group states:

    SELECT
        group#,
        thread#,
        sequence#,
        status,
        archived,
        ROUND(bytes / 1024 / 1024) AS size_mb
    FROM v$log
    ORDER BY thread#, group#;

If Oracle waits on `checkpoint incomplete`, the target group is not ready for reuse. Check datafile I/O, DBWR, and checkpoint progress.

Useful statistics to monitor:

    SELECT
        name,
        value
    FROM v$sysstat
    WHERE name IN (
      'background checkpoints started',
      'background checkpoints completed',
      'DBWR checkpoint buffers written',
      'physical writes',
      'physical writes from cache'
    )
    ORDER BY name;

These statistics are cumulative and require delta comparison. For deeper analysis, inspect storage metrics, DBWR waits, and release-specific checkpoint views.

Typical remediation options:

- Increase redo log group sizes to reduce switch frequency.
- Add log groups to give checkpoints more time before reuse.
- Address DBWR and datafile storage write latency.
- Check workloads dirtying buffers excessively fast.
- Review checkpoint targets and recovery-time settings per policy.
- Never force frequent manual checkpoints as a Band-Aid without understanding I/O impact.

### 5.2. Archiving Needed

Check archive destinations:

    SELECT
        dest_id,
        status,
        target,
        destination,
        error
    FROM v$archive_dest
    WHERE status <> 'INACTIVE'
    ORDER BY dest_id;

If `ERROR` appears, check paths, mounts, ASM disk groups, permissions, networking, and standby/destination status. Inspect recent archived logs:

    SELECT
        thread#,
        sequence#,
        dest_id,
        first_time,
        completion_time,
        archived,
        applied,
        deleted,
        status,
        name
    FROM v$archived_log
    WHERE completion_time >= SYSDATE - 1
    ORDER BY completion_time DESC;

For remote destinations, check network connectivity, services, and Data Guard transport. For local destinations, check filesystem/ASM free capacity and write permissions.

Never add log groups endlessly to dodge an archive failure. Once the new groups fill without archiving, the database will still stall.

### 5.3. Log File Switch Completion

This event reflects foregrounds waiting for a log group switch to finish. Correlate at the exact timestamp with:

- `checkpoint incomplete`.
- `archiving needed`.
- LGWR I/O.
- Log switch frequency.
- Group count and per-group status.

Looking only at the completion wait event can obscure whether the root bottleneck is checkpointing or archiving.

## 6. Sizing and Counting Redo Log Groups

### 6.1. Why Undersized Logs Cause Frequent Switches

A redo log group has fixed capacity. Under high redo generation rates, small groups fill quickly and force frequent switches. If the next group cannot be reused because checkpointing or archiving is behind, foregrounds stall.

Estimate group fill time:

    Approximate switch interval
      = usable redo bytes per group
        / redo generation rate per second

For example, a 1 GB group under an average redo generation rate of 20 MB/s:

    1,024 MB / 20 MB/s ≈ 51 seconds

This is a simplified estimate. Redo rates fluctuate by workload, thread, and overhead; usable bytes and switch triggers also factor in. Always size using peak or representative heavy redo rates rather than off-peak averages.

### 6.2. Increasing Group Size

Larger groups lengthen switch intervals and reduce archive/checkpoint transitions. However, larger groups mean each archive operation handles more redo and takes longer per file.

Group size must fit:

- Peak redo generation rate.
- Time to archive a single group.
- Checkpoint throughput.
- Recovery time requirements.
- FRA capacity and archive destination throughput.
- Data Guard transport and apply capacity.

Never pick a size solely to hit a fixed switch-count target while ignoring archiving or recovery capacity.

### 6.3. Increasing Group Count

Adding groups increases the rotation pool before an older group is reused, giving checkpoints and archiving more headroom to finish.

In RAC, each redo thread owns its own set of redo log groups; identify which thread is bottlenecked and provision groups per thread per architecture.

Adding groups does not reduce redo generation or speed up storage. If an archive destination is persistently full, extra groups merely delay when the database blocks.

### 6.4. Adding Groups Planned Properly

Example creating a new group:

    ALTER DATABASE ADD LOGFILE GROUP 4 (
      '/u02/oradata/DB/redo04a.log',
      '/u03/oradata/DB/redo04b.log'
    ) SIZE 2G;

Paths, group number, size, and member count are illustrative. Verify naming conventions, storage redundancy, OMF/ASM settings, block size, thread, and release limits before executing.

Never add duplicate group numbers or place members on the same failure domain when multiplexing requires storage isolation.

### 6.5. Resizing Existing Groups

Oracle does not resize an online redo log group directly the way it resizes a datafile. The standard procedure is to add new groups at the target size, switch logs onto the new groups, wait until older groups are no longer `CURRENT`/`ACTIVE` and are archived, and then drop the old groups once eligible.

Example dropping a group:

    ALTER DATABASE DROP LOGFILE GROUP 1;

Execute only when Oracle status and archiving rules allow dropping the group. Never drop a `CURRENT` group or one that is `ACTIVE`/unarchived. In RAC, verify thread and group status carefully. Perform changes in a maintenance window while keeping the minimum required group count.

### 6.6. Multiplexing Members Properly

Multiple members in a group protect against single-member failures. If one member fails, Oracle can continue using surviving members depending on state and accessibility.

Multiplexing is not a backup. If all members sit on one device or failure domain, one storage failure destroys every copy. Place members across independent disk groups or storage devices per design.

## 7. FRA and Why the Recovery Area Fills Up

The FRA is managed by Oracle to hold recovery-related files. Space can be consumed by several file categories:

- Archived redo logs.
- Flashback logs.
- RMAN backup pieces.
- Control file autobackups.
- Image copies or related backup files.
- Foreign archived logs in certain Data Guard setups.
- Other recovery files depending on version and configuration.

A full FRA does not mean every file inside can be deleted. Oracle determines eligibility for reclamation based on retention policies, backup status, archive deletion policies, flashback requirements, and recovery dependencies.

### 7.1. Check FRA Usage

    SELECT
        name,
        ROUND(space_limit / 1024 / 1024 / 1024, 2) AS limit_gb,
        ROUND(space_used / 1024 / 1024 / 1024, 2) AS used_gb,
        ROUND(space_reclaimable / 1024 / 1024 / 1024, 2) AS reclaimable_gb,
        number_of_files
    FROM v$recovery_file_dest;

Key metrics:

- `SPACE_LIMIT`: configured FRA ceiling.
- `SPACE_USED`: space currently managed in the FRA.
- `SPACE_RECLAIMABLE`: space Oracle deems reclaimable under current policies.
- `NUMBER_OF_FILES`: number of files managed in the FRA.

If reclaimable is near 0 while used approaches the limit, the database risks failing new archives or backups. If reclaimable is large yet space is not freeing, inspect reclamation rules, retention, and RMAN operations.

### 7.2. Breakdown by File Type

    SELECT
        file_type,
        percent_space_used,
        percent_space_reclaimable,
        number_of_files
    FROM v$flash_recovery_area_usage
    ORDER BY percent_space_used DESC;

This view reveals whether archived logs, flashback logs, or backup pieces dominate usage. Exact view/column names and file types vary by release; verify in your version's data dictionary.

### 7.3. Check FRA Destination and Size

    SHOW PARAMETER db_recovery_file_dest;
    SHOW PARAMETER db_recovery_file_dest_size;

Or:

    SELECT name, value
    FROM v$parameter
    WHERE name IN (
      'db_recovery_file_dest',
      'db_recovery_file_dest_size'
    )
    ORDER BY name;

`DB_RECOVERY_FILE_DEST` points to the FRA location; `DB_RECOVERY_FILE_DEST_SIZE` sets the logical ceiling. Raising the parameter creates no physical storage. With ASM, check disk group free space; with filesystems, check mount capacity and inodes.

### 7.4. Guaranteed Restore Points and Flashback Logs

Guaranteed restore points force Oracle to retain flashback logs needed to flash back to that point. If a restore point stays active for a long time while the database generates heavy redo, flashback logs can consume massive FRA space.

Check:

    SELECT
        name,
        time,
        guarantee_flashback_database,
        storage_size
    FROM v$restore_point
    ORDER BY time;

Never drop a guaranteed restore point solely to free space without confirming its purpose and protection window. Dropping it removes the ability to flash back to that committed point. Obtain approval from the change/recovery owner first.

## 8. How a Full FRA Impacts Archiving and Commits

A common failure cascade:

    FRA or archive destination fills up
                |
                v
    ARCn cannot write archived redo logs
                |
                v
    Online redo groups cannot be reused
                |
                v
    Database waits on log switch / archiving
                |
                v
    Foreground DML and commits slow down or stall
                |
                v
    Applications time out or fail to write data

Not every slow commit is caused by the FRA. However, when archive destinations fail and redo log groups run out, log switch waits block the database once no free redo log groups remain.

### 8.1. Common Errors When FRA/Archiving Fills

Common Oracle errors:

| Oracle Error | Common Meaning |
|---|---|
| `ORA-19809` | `DB_RECOVERY_FILE_DEST_SIZE` limit exceeded |
| `ORA-19804` | Cannot reclaim enough space in FRA for request |
| `ORA-00257` | Archiver error; new connections may be restricted until resolved |
| `ORA-16038` | Unable to archive redo log sequence |
| `ORA-16014` | No available destinations to archive log |
| `ORA-19504` | Failed to create file |
| `ORA-270xx` | OS/storage error accessing file |

Exact messages depend on root cause. Inspect the alert log, ARCn traces, and archive destination errors to determine whether the cause is filesystem, ASM, network, or policy.

### 8.2. ORA-00257

ORA-00257 occurs when the archiver cannot archive redo. The database may restrict connections to `SYSDBA` only or block normal client activity.

Never simply restart the database to clear the error. Restarting neither creates disk space nor fixes a broken destination. Restore the archive destination/FRA, handle reclaimable files, and confirm ARCn resumes archiving.

### 8.3. ORA-19809 and ORA-19804

ORA-19809 indicates the FRA limit is exceeded. ORA-19804 indicates Oracle cannot reclaim enough bytes to satisfy the write. Check used vs. reclaimable space by file type, retention policies, guaranteed restore points, and destination capacity.

If physical storage has free space, consider increasing `DB_RECOVERY_FILE_DEST_SIZE`. If physical storage is full, raising the logical limit pushes configuration past physical capacity and triggers lower-level filesystem/ASM errors.

## 9. Checking Archive Destinations and Archived Logs

### 9.1. Destination Status

    SELECT
        dest_id,
        status,
        target,
        destination,
        error
    FROM v$archive_dest
    WHERE status <> 'INACTIVE'
    ORDER BY dest_id;

`VALID`/`ERROR` status and `ERROR` text pinpoint which destination is failing. Databases often have multiple destinations; distinguish mandatory destinations from optional ones per policy.

### 9.2. Destination Runtime Status

    SELECT
        dest_id,
        status,
        type,
        database_mode,
        recovery_mode,
        destination,
        error,
        gap_status
    FROM v$archive_dest_status
    WHERE status <> 'INACTIVE'
    ORDER BY dest_id;

Available columns depend on release and privileges. If a column is absent, inspect the view definition on your release and adjust the query. In Data Guard setups, check transport/apply status and `gap_status`.

### 9.3. Recent Archived Logs

    SELECT
        thread#,
        sequence#,
        dest_id,
        first_time,
        completion_time,
        archived,
        applied,
        deleted,
        status,
        name
    FROM v$archived_log
    WHERE first_time >= SYSDATE - 1
    ORDER BY completion_time DESC;

Multiple rows may exist for the same thread/sequence across multiple destinations or copies. Do not count every row as a unique sequence. For standbys, `APPLIED` is meaningful in its proper context and does not always mirror primary status directly.

### 9.4. Archiver Processes and Alert Log

Check the alert log for file creation errors, permissions, disk full messages, ASM dismounts, network failures, or standby transport errors. Confirm `ARCn` processes are running without process/resource starvation. Never assume archiving is healthy from a single destination query alone.

## 10. Reclaiming FRA Space Safely with RMAN

The FRA is managed by Oracle; never delete archived logs or backup pieces directly using `rm`, `del`, or OS filesystem tools. Deleting outside RMAN desynchronizes repository metadata from disk files and breaks restore/recovery capability.

### 10.1. View RMAN Configuration

In RMAN:

    SHOW ALL;

Inspect key policies:

- Retention policy.
- Archived log deletion policy.
- Control file autobackup.
- Backup optimization.
- Channel/device configuration.
- Recovery window or redundancy.

Never weaken retention policies just to free FRA space without validating RPO/RTO and recovery mandates.

### 10.2. CROSSCHECK

`CROSSCHECK` reconciles RMAN repository metadata with physical backup/archive files on disk:

    CROSSCHECK BACKUP;
    CROSSCHECK ARCHIVELOG ALL;

Missing files are marked `EXPIRED`. `CROSSCHECK` neither deletes valid files nor deletes files physically.

After `CROSSCHECK`, inspect the `EXPIRED` list and understand why files vanished before running `DELETE EXPIRED`.

### 10.3. DELETE EXPIRED vs. DELETE OBSOLETE

- `DELETE EXPIRED` removes repository metadata for files RMAN confirmed are already missing on disk.
- `DELETE OBSOLETE` deletes backups no longer needed under the retention policy, with RMAN deleting the physical files cleanly.

Examples:

    DELETE EXPIRED BACKUP;
    DELETE EXPIRED ARCHIVELOG ALL;

    REPORT OBSOLETE;
    DELETE OBSOLETE;

Always run `REPORT OBSOLETE` first to preview which files are considered obsolete. `DELETE OBSOLETE` must align with approved retention policies and recovery requirements.

### 10.4. Backing Up Archived Logs and Deleting Input

A standard workflow backs up archived logs and deletes input only after successful backup:

    BACKUP ARCHIVELOG ALL DELETE INPUT;

Coordinate this command with archived log deletion policies, Data Guard requirements, and backup policies. With multiple archive destinations, `DELETE INPUT` and `DELETE ALL INPUT` behave differently; read RMAN documentation before choosing. Never run this if deletion policies require standbys to receive/apply logs first and standbys are lagging.

### 10.5. Data Guard Deletion Policy

When standbys exist, archived logs must often remain until applied on standbys or backed up per policy. RMAN configures archived log deletion policies accordingly, such as requiring logs to be applied on all required standbys.

Check:

    SHOW ARCHIVELOG DELETION POLICY;

Never relax the deletion policy just to delete logs faster while a standby is lagging or has a gap. Doing so can delete redo before the standby catches up, stranding the standby.

### 10.6. Never Delete Archived Logs Manually

Never use OS filesystem commands to remove files in the FRA. If RMAN cannot reclaim files, check whether:

- Files are still required by retention policy.
- Archived logs have not yet been backed up or applied.
- A guaranteed restore point retains flashback logs.
- Obsolete backup pieces have not been cleaned in the repository.
- Files belong to Data Guard / foreign archives.
- The destination or ASM disk group has errors.

When files must be removed, use RMAN commands per policy with proper logging and approval.

## 11. Expanding FRA Capacity and Changing Archive Destinations

### 11.1. Increasing DB_RECOVERY_FILE_DEST_SIZE

When physical storage has spare room and the FRA needs more capacity, a DBA can raise the limit:

    ALTER SYSTEM SET db_recovery_file_dest_size = 500G
      SCOPE = BOTH;

`500G` is an example only. Verify online modifiability for your release and setup. Confirm ASM/filesystem headroom covers ongoing backups, flashback, and archives without starving co-located workloads.

Expanding FRA size does not replace reviewing retention policies and archive generation rates. If redo generation persistently outpaces backups and cleanup, the FRA will fill again.

### 11.2. Inspect Actual Physical Storage

For filesystems, check free bytes, inodes, mount state, permissions, and quotas. For ASM, check disk group free space, `usable_file_mb`, redundancy, and rebalance status. Never inspect only `DB_RECOVERY_FILE_DEST_SIZE`, which is a logical cap rather than physical capacity.

### 11.3. Relocating Archive Destinations

If the current archive destination is full or unsuitable, another destination can be configured. Changing `LOG_ARCHIVE_DEST_n` or the FRA path requires DBA review, especially with Data Guard, RAC, and recovery tooling.

Illustrative local destination example:

    ALTER SYSTEM SET log_archive_dest_1 =
      'LOCATION=/u04/archivelog'
      SCOPE = BOTH;

Never copy example paths into production. Verify path existence, Oracle ownership/permissions, mount health, backup/retention integration, destination state, and Data Guard rules. A new destination without backup and cleanup automation merely moves the outage to a different filesystem.

## 12. Slow Commits: Addressing the Application Layer

When `log file sync` is the dominant wait, examine the application's transaction patterns.

### 12.1. Avoid Row-by-Row Commits When Unnecessary

High-commit anti-pattern:

    FOR each row:
        INSERT one row
        COMMIT

If business requirements dictate each row is an independent transaction, preserve those semantics. However, when rows belong to one logical batch, committing per row generates excessive commit requests and overhead.

Batch multiple DML operations into a single transaction:

    BEGIN
      INSERT INTO staging_table ...;
      INSERT INTO target_table ...;
      UPDATE summary_table ...;
      COMMIT;
    END;

Choose batch sizes balancing commit overhead, undo consumption, lock duration, retry cost, and rollback impact. Overly huge transactions hold locks too long, generate massive undo, and slow down recovery.

### 12.2. Group Commit

Oracle coalesces closely timed commit requests into a single redo flush. Group commit reduces I/O per transaction. However, if an application commits sequentially from a single thread, commits cannot benefit much from group commit.

Increasing concurrency is not a magic bullet: it can boost group commit while also raising lock contention and redo volume. Benchmark against realistic workloads.

### 12.3. Review Transaction Boundaries

A service might open a transaction before calling an external API, wait for the response, and only then commit. This stretches connection/lock hold times and increases concurrency pressure.

Keep transactions short, define atomicity boundaries cleanly, and use outbox or saga patterns for distributed integrations where appropriate. Never alter commit scope purely to cut waits if doing so breaks business consistency.

### 12.4. Check ORMs and Auto-Commit

In Spring/JPA, inspect transaction managers, `@Transactional` boundaries, flush modes, and batching configuration. Hibernate may flush DML before commit; Java-observed commit duration can include flush, constraint checks, triggers, network round-trips, and commit wait.

Separate time spent:
- Before calling commit.
- Flushing SQL.
- Database commit processing.
- JDBC network round-trips.
- Client response handling.

Never blame `log file sync` for the entire Java commit method duration without traces or metrics breaking down each phase.

## 13. Slow Commits: Addressing Storage and the Database

### 13.1. Measure Redo Storage Latency

Redo log writes are latency-critical synchronous I/O. Partner with storage teams to measure latency on the exact redo volume/disk group during slow-commit windows. Check both read and write paths if storage pools are shared.

Inspect:

- Average and tail write latency.
- Queue depth.
- IOPS and throughput.
- Storage cache and battery-backed/write-through policies.
- Multipath path health.
- Hypervisor/virtual disk latency.
- ASM disk group load.
- Contention from datafiles, archives, and backups.

Never move redo logs to another volume on the assumption it is faster without verifying latency, redundancy, and failure domains.

### 13.2. Isolate Redo Logs from Contending Workloads

If redo logs, datafiles, and RMAN backups share a saturated storage pool, I/O contention ensues. Storage design can isolate redo logs from heavy sequential workloads depending on architecture and platform capabilities.

Multiplex redo members against file loss without putting all members in the same storage failure domain. Balance durability, latency, and availability.

### 13.3. Check LGWR CPU and Scheduling

If `log file sync` is high while `log file parallel write` stays low, check CPU scheduling, the LGWR process, OS run queues, virtualization steal time, and background processes. A delayed LGWR process stalls foreground commits even when storage writes finish rapidly once dispatched.

### 13.4. Do Not Raise LOG_BUFFER Arbitrarily

`LOG_BUFFER` sets the redo log buffer size. Raising it helps specific buffer-contention workloads, yet will not cure slow redo storage writes or high commit I/O latency. Require evidence of `log buffer space` waits or redo allocation pressure and check Oracle documentation before changing it.

### 13.5. Never Use COMMIT NOWAIT as an Emergency Workaround

Oracle supports `COMMIT WRITE` options controlling `WAIT`/`NOWAIT` and `IMMEDIATE`/`BATCH`. With `WAIT`, foregrounds wait for durable redo writes. With `NOWAIT`, applications receive commit confirmation before redo is written durably; if the instance or host crashes in that gap, transactions the client believes committed can be lost.

`NOWAIT` alters the durability contract and can cause serious divergence between client and database state. Consider it only when business owners explicitly accept data-loss risk under an approved design—never to mask storage or LGWR problems.

`BATCH` allows buffering/grouping redo writes per supported semantics; when paired with `WAIT`, foregrounds still wait for durability per commit mode. Defaults and exact behavior vary by version/configuration; verify against release documentation.

## 14. Data Guard Synchronous Commits and Network Latency

In Data Guard synchronous transport, commit latency can depend on redo reaching the standby and being acknowledged under the protection mode and transport attributes. Commit latency rises due to:

- Network round-trip time between primary and standby.
- Redo write latency on the standby.
- Overloaded standby or redo transport lag.
- Packet loss, retransmissions, or network congestion.
- Standby destination or service outages.

Under `SYNC`/`AFFIRM`, commit acknowledgment waits for standby redo disk writes per semantics. `NOAFFIRM` uses different acknowledgment rules and alters durability guarantees. Never switch `SYNC` to `ASYNC` or `AFFIRM` to `NOAFFIRM` just to trim commit latency without evaluating protection mode, RPO, and HA policies.

Check Data Guard:

    SELECT
        dest_id,
        status,
        target,
        destination,
        error,
        gap_status
    FROM v$archive_dest_status
    WHERE target = 'STANDBY'
    ORDER BY dest_id;

Inspect Data Guard statistics:

    SELECT
        name,
        value,
        unit,
        time_computed,
        datum_time
    FROM v$dataguard_stats
    ORDER BY name;

Column/view availability and privileges depend on release and role. Correlate transport/apply lag, alert logs, network metrics, and wait events to pinpoint where commit acknowledgment slows down.

## 15. Sample Incident Scenarios

### 15.1. Application Commits Take 2 Seconds with High log file sync

Investigate:

1. Identify affected services/modules and sessions hitting `log file sync`.
2. Compare averages and histograms of `log file sync` vs. `log file parallel write`.
3. Measure redo storage latency over the exact window.
4. Check commit rate, redo generation rate, and transaction durations.
5. Check Data Guard synchronous transport if configured.
6. Check LGWR CPU/scheduling.

If `log file parallel write` is high, prioritize storage investigation. If parallel write is low while `log file sync` is high, examine CPU scheduling, group commit patterns, CPU contention, and remote acknowledgments.

### 15.2. Log Switches Every Few Tens of Seconds

Investigate:

1. Calculate redo generation rate over time.
2. Check group sizes and counts per thread.
3. Review hourly switch history.
4. Check archive throughput and checkpoint completion.
5. Check for `checkpoint incomplete` or `archiving needed` waits.

If switches happen often without foreground waits and archiving/checkpoints keep up, it is simply a sizing review item. If switches trigger waits, resolve whichever bottleneck—checkpointing or archiving—blocks reuse before expanding sizes/groups.

### 15.3. ORA-00257 with FRA Near 100%

Investigate:

1. Query `V$RECOVERY_FILE_DEST`.
2. Query `V$FLASH_RECOVERY_AREA_USAGE`.
3. Check archive destination status and errors.
4. Check RMAN retention/deletion policies.
5. Check archive backups and Data Guard apply status.
6. Check guaranteed restore points and flashback log usage.
7. Verify underlying physical storage capacity.

Repair archive destinations, run RMAN backup/cleanup per policy, or increase the FRA limit if physical storage truly has room. Afterward, verify ARCn archives the latest sequence and redo groups become reusable.

### 15.4. log file switch (checkpoint incomplete)

Investigate datafile I/O, DBWR, redo generation bursts, log sizes, and group counts. Increase log size or group count only after confirming checkpoints are lagging and datafile storage has matching capacity.

### 15.5. Remote Archive Destination Failing

If a Data Guard or remote archive destination fails, inspect networking, listeners/services, credentials, destination state, standby role, and transport gaps. Never delete archived logs needed by a standby to free space before establishing a recovery plan for transport/apply.

## 16. Ordered Incident Response Procedure

When production suffers slow commits or archive/FRA stalls, follow this order to isolate the bottleneck.

### Step 1: Define Scope

- One service or all services?
- One database instance or the entire cluster?
- When did it start?
- Were there recent deployments, batches, backups, ETL, or storage changes?
- Does the database use `ARCHIVELOG` and Data Guard?
- Is it CDB/PDB or RAC?

### Step 2: Check Wait Events

Capture snapshots of `V$SESSION` and `V$SYSTEM_EVENT`. Determine whether foregrounds wait on `log file sync`, log switches, `log buffer space`, or unrelated events.

### Step 3: Check Redo Log Groups

Inspect `V$LOG` and `V$LOGFILE`. Identify `CURRENT`, `ACTIVE`, `INACTIVE` groups, archive statuses, and member paths. Check switch frequency per thread.

### Step 4: Check Archive Destinations

Inspect `V$ARCHIVE_DEST`, `V$ARCHIVE_DEST_STATUS`, recent archived logs, the alert log, and ARCn errors. If a destination is broken, restore write capability before proceeding.

### Step 5: Check FRA

Inspect limit, used, reclaimable, and usage by file type. Determine whether archives, backups, or flashback logs consume space.

### Step 6: Apply Targeted Remediation

- Slow redo storage: fix I/O path/latency.
- Excessive commits: optimize transaction boundaries/batching preserving semantics.
- Checkpoint incomplete: check DBWR/datafile I/O, log sizes/group counts.
- Archiving needed: fix destinations/FRA/ARCn/Data Guard.
- Full FRA: run RMAN backup/cleanup per policy or expand physical capacity safely.
- Data Guard sync latency: fix network/standby while keeping required protection semantics.
- Redo buffer space: fix LGWR throughput and redo bursts.

### Step 7: Post-Fix Verification

- Log switches resume smoothly.
- New archived logs are generated.
- FRA used/reclaimable metrics stabilize.
- Wait events drop under matching load.
- Commit latency and application error rates return to baseline.
- Data Guard transport/apply maintains no unexpected gaps.
- Backup and recovery policies remain intact.

## 17. Actions to Avoid

### 17.1. Deleting Archived Logs via OS Commands

Deleting files in the FRA with `rm`/`del` desynchronizes the RMAN repository from actual files and breaks recoverability. Always use RMAN for crosschecks, backups, deleting expired/obsolete files, or managing archives per deletion policy.

### 17.2. Raising the FRA Limit Beyond Physical Capacity

`DB_RECOVERY_FILE_DEST_SIZE` is only an Oracle ceiling. If the filesystem or ASM disk group lacks space, raising the limit pushes failures down to the storage layer.

### 17.3. Adding Redo Log Groups Without Fixing Archiving

Adding groups buys temporary buffer time without fixing a full destination or stalled ARCn. Once the extra groups fill, the database stalls again.

### 17.4. Forcing Continuous Log Switches

`ALTER SYSTEM SWITCH LOGFILE` or `ARCHIVE LOG CURRENT` is useful for specific DBA/backup steps, yet running it repeatedly in production generates extra archive/checkpoint work and worsens stalls. Use only with clear intent.

### 17.5. Disabling ARCHIVELOG or Weakening Protection Mode to Clear Errors

Disabling `ARCHIVELOG` alters media recovery capability and backup strategy. Weakening Data Guard protection/transport modes alters durability and availability guarantees. Those are architectural and recovery-objective changes, not routine FRA cleanup steps.

### 17.6. Raising LOG_BUFFER or Pool Sizes by Gut Feel

These adjustments do not fix slow redo storage latency or broken archive destinations. Measure the actual bottleneck before tuning parameters.

## 18. Operational Checklists

### When Commits Are Slow

- Identify committing sessions, services, and modules.
- Inspect `log file sync` and `log file parallel write`.
- Compare wait deltas, histograms, and redo write stats.
- Measure redo log storage latency.
- Check LGWR CPU/scheduling.
- Audit commit frequency and transaction boundaries.
- Check synchronous Data Guard transport.
- Never alter durability modes without risk assessment.

### When Log Switches Stall

- Inspect `V$LOG` and `V$LOGFILE`.
- Measure switch frequency per thread.
- Distinguish `checkpoint incomplete` from `archiving needed`.
- Check DBWR and datafile I/O.
- Check archive destinations and ARCn.
- Calculate redo generation rates before resizing logs.
- Provision enough groups for checkpoints/archiving to keep pace.
- Keep multiplexed members across independent failure domains.

### When the FRA Is Full

- Inspect `DB_RECOVERY_FILE_DEST` and size.
- Inspect used/reclaimable space in `V$RECOVERY_FILE_DEST`.
- Categorize files via `V$FLASH_RECOVERY_AREA_USAGE`.
- Check archive destination errors.
- Review RMAN retention/deletion policies.
- Check backup and Data Guard apply statuses.
- Check guaranteed restore points and flashback log usage.
- Reclaim files only via RMAN per policy.
- Raise FRA size only when physical storage has verified room.

### After Recovery

- Confirm new archived logs are generated and archive destinations are `VALID`.
- Confirm log groups switch and recycle cleanly.
- Verify FRA usage stops climbing unchecked.
- Verify commit latency and wait events under load.
- Verify Data Guard transport/apply and backup jobs.
- Save alert logs, RMAN output, and before/after incident metrics.

## 19. Principles to Remember

- `COMMIT` typically waits on LGWR to write redo; `log file sync` is the key foreground wait event to inspect.
- `log file parallel write` measures LGWR's storage write latency for redo.
- `log buffer space` indicates the redo buffer is not draining fast enough.
- `log file switch (checkpoint incomplete)` points to checkpointing/DBWR; `log file switch (archiving needed)` points to archive destinations.
- Log switching is normal; excessive switch frequency or blocked group reuse is the real issue.
- Group size governs redo per switch; group count provides time before reuse; extra members protect redundancy without adding capacity.
- The FRA holds multiple recovery file types; identify what consumes space before cleaning up.
- Use RMAN and deletion policies to manage archived logs and backups; never delete recovery files directly via the OS.
- Guaranteed restore points retain flashback logs; drop them only after confirming recovery requirements.
- Raise the FRA limit only when filesystem/ASM has physical capacity.
- Data Guard `SYNC`/`AFFIRM` impacts commit acknowledgment; never downgrade protection modes solely to reduce latency.
- Never use `COMMIT NOWAIT`, disable `ARCHIVELOG`, or force log switches as emergency Band-Aids.
- Measure waits, redo, archiving, FRA, and storage over matching intervals to find the true bottleneck.

Commits, redo log switches, and the FRA are interconnected links in Oracle's data-protection chain. Effective troubleshooting connects foreground wait events to LGWR activity, checkpoints, ARCn, archive destinations, and storage performance. Once the exact bottleneck is identified, DBAs can restore commit latency and archiving throughput without compromising durability, backup integrity, or recovery guarantees.
