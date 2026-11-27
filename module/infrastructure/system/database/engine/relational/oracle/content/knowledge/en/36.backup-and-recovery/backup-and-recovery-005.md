# Full backup, incremental level 0/1, and block change tracking

Oracle Recovery Manager (RMAN) supports several ways to back up a database. For large databases, taking a full backup every day can be time-consuming and storage-intensive. Incremental backups help reduce the amount of data that must be read and written by backing up only the blocks that have changed since a previous backup point. Block Change Tracking (BCT) further optimizes this process by helping RMAN locate changed blocks without scanning every datafile to identify them.

Key concepts to distinguish:

- **Full backup:** a complete backup as requested by RMAN, but it does not serve as a parent for an incremental level 1 backup.
- **Incremental level 0:** a baseline containing the used blocks of a datafile, which can serve as the parent for subsequent incremental level 1 backups.
- **Incremental level 1:** backs up only blocks that have changed since a previous level 0 or level 1 backup, in either differential or cumulative mode.
- **Block Change Tracking:** a bitmap file maintained by Oracle to record changed block locations, enabling RMAN to quickly identify which blocks need to be read for an incremental backup.

Choosing a strategy must be based on RPO, RTO, redo generation rate, database size, backup window, bandwidth, and restore time. A smaller backup does not necessarily recover faster; both backup and restore/recover must be tested.

## 1. RMAN and backup components

RMAN is the Oracle tool used to back up, restore, and recover a database. RMAN understands database structure, datafiles, control files, archived redo logs, and backup metadata.

A backup plan typically protects:

- Database datafiles.
- Control file.
- SPFILE.
- Archived redo logs when the database is in ARCHIVELOG mode.
- Keystore if the database uses TDE.
- Recovery catalog if the organization uses a catalog.
- Configurations, password file, wallet, and artifacts needed for the recovery procedure.

RMAN can write backups to disk or a media manager/tape through the appropriate channels and device types.

### 1.1 Backup sets and image copies

RMAN supports two primary backup formats:

**Backup set**

- An RMAN-proprietary backup format.
- Contains backup pieces.
- Can store only the used blocks of a datafile.
- Can use compression and encryption depending on supported configuration.
- Usually the default format for RMAN backups.

**Image copy**

- A file copy in the exact format of the original datafile or control file.
- Can be used directly in certain restore/switch procedures.
- Well-suited for incremental merge when updating an image copy with level 1 backups.
- Typically occupies storage space close to the source file size.

Do not confuse an image copy with an arbitrary OS file copy. An image copy is managed by RMAN and recorded in the repository.

### 1.2 RMAN repository

RMAN stores backup metadata in:

- The target database's control file.
- A recovery catalog, if configured.

Metadata may include backup pieces, datafiles, archived logs, checkpoint SCN, tags, completion time, and status. Metadata does not replace physical backup files. If a backup file is lost, the repository may still hold stale records until a crosscheck is run.

### 1.3 Channel

A channel is an RMAN connection used to read and write backups. Channels can be configured for DISK or SBT_TAPE and can run in parallel.

Example:

~~~text
RMAN> CONFIGURE DEVICE TYPE DISK PARALLELISM 2;
~~~

Higher parallelism can increase throughput, but it also consumes more CPU, I/O, memory, and network bandwidth. Always benchmark on real storage.

## 2. What is a full backup?

A full backup is a complete backup of the required blocks of the target object. For datafiles, RMAN normally backs up only the used blocks and does not necessarily write all empty blocks like a byte-for-byte physical copy.

Example:

~~~text
RMAN> BACKUP DATABASE;
~~~

This command creates a full database backup according to RMAN configuration. If no incremental level is specified, it is a full backup, not a level 0 backup.

### 2.1 A full backup is not an incremental level 0

This is a critical distinction:

- A full backup can be used to restore the database.
- A full backup cannot be used as the parent for an incremental level 1 backup.
- A level 0 backup is the baseline used by RMAN in an incremental backup strategy.

Example:

~~~text
RMAN> BACKUP DATABASE;
RMAN> BACKUP INCREMENTAL LEVEL 1 DATABASE;
~~~

The first full backup does not become a level 0 merely because it contains all the data. If no suitable level 0 exists, RMAN may have to create a level 0 when executing an incremental strategy. Never build a plan assuming that a standard full backup will act as the parent for level 1.

### 2.2 When is a full backup appropriate?

- Small databases where the backup window permits.
- When an independent full backup is needed for simple restores.
- As a periodic baseline per policy.
- Before/after a major change if required by procedures.
- Environments that do not require a complex incremental chain.

### 2.3 Full backup and restore time

A full backup can simplify the restore procedure because it has fewer dependencies on an incremental chain. However, restoring still requires archived redo logs to recover to the desired point in time in ARCHIVELOG mode.

A full backup does not mean archive logs are unnecessary, nor does it provide point-in-time recovery on its own if redo is missing.

## 3. What is an incremental backup?

An incremental backup stores only blocks that have changed relative to a previous backup point. Instead of reading and writing all data every time, RMAN backs up only the blocks identified as changed.

Benefits:

- Reduces backup size.
- Reduces backup duration when the block change rate is low.
- Reduces backup transfer bandwidth.
- Can shorten the backup window.

Costs:

- Requires managing the baseline and incremental chain.
- Restore/recover may need to apply multiple incremental backups.
- More complex backup strategy and retention management.
- If the block change rate is high, an incremental backup can approach the size of a full backup.

## 4. Incremental level 0

An incremental level 0 backup is the baseline of an incremental backup strategy. It backs up all used blocks of a datafile and can serve as the parent for level 1 backups.

Example:

~~~text
RMAN> BACKUP INCREMENTAL LEVEL 0 DATABASE;
~~~

A level 0 backup can be created as a backup set or an image copy depending on syntax and configuration.

### 4.1 What does level 0 contain?

Conceptually, level 0 contains the required datafile data at the backup point. RMAN records the backup's checkpoint/SCN to determine the range of changes for subsequent incremental backups.

Level 0 is not a logical copy of individual SQL rows. It is a block-level physical backup.

### 4.2 Level 0 as the parent for level 1

Example:

~~~text
Day 1: Incremental level 0
Day 2: Incremental level 1
Day 3: Incremental level 1
Day 4: Incremental level 1
~~~

The level 1 backups rely on the preceding level 0 and/or level 1 point depending on whether they are differential or cumulative.

### 4.3 Creating a new level 0

When the database undergoes major changes, the incremental chain becomes too long, or the backup schedule requires it, a new level 0 can be created. The new level 0 becomes the baseline for subsequent level 1 backups.

Do not create level 0 backups too frequently if the goal of incremental backups is to reduce time and storage. Balance baseline refresh frequency against restore chain length.

## 5. Incremental level 1: differential and cumulative

RMAN supports two types of level 1 backups:

- Differential level 1: backs up blocks changed since the most recent incremental backup at level 0 or level 1.
- Cumulative level 1: backs up blocks changed since the most recent incremental level 0 backup.

### 5.1 Differential level 1

Command:

~~~text
RMAN> BACKUP INCREMENTAL LEVEL 1 DATABASE;
~~~

Suppose the schedule is:

| Day | Backup |
|---|---|
| Monday | Level 0 |
| Tuesday | Level 1 differential |
| Wednesday | Level 1 differential |
| Thursday | Level 1 differential |

Wednesday's level 1 only needs to contain blocks changed since the most recent previous incremental backup—Tuesday's level 1 in this example.

Advantages:

- Each incremental backup is typically smaller than cumulative if daily change volume is moderate.
- Faster backups when the daily change rate is low.

Disadvantages:

- Restore may have to apply multiple consecutive level 1 backups after level 0.
- If a required incremental backup in the chain is missing, another restore path or baseline may be needed.

### 5.2 Cumulative level 1

Command:

~~~text
RMAN> BACKUP INCREMENTAL LEVEL 1 CUMULATIVE DATABASE;
~~~

A cumulative level 1 backs up all blocks changed since the most recent level 0 backup.

Example:

| Day | Backup |
|---|---|
| Monday | Level 0 |
| Tuesday | Level 1 cumulative |
| Wednesday | Level 1 cumulative |
| Thursday | Level 1 cumulative |

Thursday's cumulative level 1 contains all blocks changed since Monday's level 0, including blocks already backed up in Tuesday's and Wednesday's cumulative backups.

Advantages:

- Restore typically only needs level 0 and the latest cumulative level 1 to bring datafiles up to that cumulative point.
- Fewer dependencies on intermediate incremental backups.

Disadvantages:

- Daily backup size grows over time until the next level 0.
- Blocks changed early in the cycle are read and written repeatedly.
- Backup windows and backup/archive storage consumption may increase.

### 5.3 Comparing differential and cumulative

| Criterion | Differential level 1 | Cumulative level 1 |
|---|---|---|
| Comparison point | Most recent level 0 or level 1 | Most recent level 0 |
| Size per backup | Usually smaller | Usually grows over time since level 0 |
| Number of incrementals to apply | May require multiple level 1s | May require only the latest cumulative level 1 |
| Backup window | Usually shorter | Can be longer |
| Restore complexity | Longer chain | Simpler chain |
| Best suited for | Reducing storage/backup time | Simplifying restores |

No single choice fits every database. Measure change rate, backup time, restore time, and RTO requirements.

## 6. Example incremental chain

Suppose a database has 1 TB of used blocks and about 2% changes per day:

~~~text
Monday: Level 0
   |
   +-- Tuesday: Level 1
   |
   +-- Wednesday: Level 1
   |
   +-- Thursday: Level 1
   |
   +-- Friday: Level 1
~~~

If differential, each level 1 generally contains only changes since the previous incremental. If cumulative, a late-week level 1 contains the aggregated changes since level 0.

The 2% and 1 TB figures are illustrative examples only. Actual backup size also depends on block size, unused blocks, compression, block change patterns, and overhead.

### 6.1 Differential restore chain

~~~text
Restore Level 0
      |
      v
Apply Level 1 (Tue)
      |
      v
Apply Level 1 (Wed)
      |
      v
Apply Level 1 (Thu)
      |
      v
Apply archived redo logs
      |
      v
Recover to target SCN/time
~~~

### 6.2 Cumulative restore chain

~~~text
Restore Level 0
      |
      v
Apply latest Level 1 CUMULATIVE
      |
      v
Apply archived redo logs
      |
      v
Recover to target SCN/time
~~~

These diagrams illustrate concepts. RMAN automatically selects required backups based on the repository and RESTORE/RECOVER commands; operators must inspect the preview and actual output.

## 7. What is Block Change Tracking (BCT)?

Block Change Tracking is an Oracle mechanism that records changed blocks in a dedicated bitmap file. When RMAN performs an incremental backup, BCT helps RMAN identify regions with changed blocks without scanning every datafile to find them.

Without BCT:

- RMAN may have to read many blocks across the datafile to determine which blocks changed since the reference backup.
- After identifying them, RMAN backs up only the necessary changed blocks.

With BCT:

- Oracle maintains a bitmap of changed blocks.
- RMAN uses the bitmap to identify regions to read.
- RMAN still reads the required data blocks and writes the backup as usual.

### 7.1 BCT is not an incremental backup

BCT does not create backups, does not store copies of data, and does not replace RMAN. It only accelerates the step of identifying changed blocks.

### 7.2 BCT does not alter backup contents

BCT does not cause incremental backups to omit blocks and does not reduce recovery requirements. RMAN still backs up all blocks required for the specified level and SCN point.

### 7.3 When is BCT most beneficial?

- Large databases.
- Frequent incremental level 1 backups.
- Low block change rate relative to datafile size.
- Reading datafiles to locate changed blocks is the bottleneck.
- Sufficient storage space and I/O capacity exist to maintain the BCT file.

BCT may not provide significant benefits when:

- Only full or level 0 backups are run.
- Most blocks change in every cycle.
- The database is small.
- Storage can already read entire datafiles fast enough.
- The backup bottleneck is in the network, compression, output device, or media manager.

## 8. Enabling Block Change Tracking

Before enabling BCT, the DBA must determine the BCT file location, filesystem permissions, storage redundancy, and backup policy.

Example:

~~~sql
ALTER DATABASE ENABLE BLOCK CHANGE TRACKING
USING FILE '/u02/oradata/ORCL/bct01.ctf';
~~~

The path is an example only. The file should reside on reliable storage with sufficient space and be accessible to the Oracle software owner.

Verification:

~~~sql
SELECT status,
       filename,
       bytes
FROM v$block_change_tracking;
~~~

Common columns:

- STATUS: tracking status.
- FILENAME: BCT file location.
- BYTES: file size.

Metadata views may vary by version.

### 8.1 Disabling BCT

~~~sql
ALTER DATABASE DISABLE BLOCK CHANGE TRACKING;
~~~

Disable BCT only when operationally necessary or when changing the file according to a procedure. When BCT is disabled, incremental backups still run, but may have to scan many blocks to locate changes.

### 8.2 Relocating the BCT file

How to move the file depends on the release. A widely compatible approach is:

1. Confirm the backup window and workload.
2. Disable BCT.
3. Prepare the new location.
4. Enable BCT with the new file.
5. Check STATUS and FILENAME.
6. Run a test incremental backup and monitor elapsed time.

Some releases support `MOVE BLOCK CHANGE TRACKING FILE` syntax. Check the documentation for your exact release before using it. Never delete a file currently in use by the database.

## 9. BCT file and lifecycle

The BCT file is an auxiliary file used to speed up incremental backups, not a datafile holding business data.

Key points to remember:

- The BCT file can be recreated if lost; the next incremental backup may have to perform a full datafile scan to reinitialize tracking.
- The BCT file does not replace datafile backups or archived redo logs.
- The BCT file should not be treated as a mandatory component for restoring a database from RMAN backups; after restore/recovery, verify its status and reconfigure it per your release.
- Never OS-copy an open BCT file and treat the copy as a valid backup.
- If the database uses RAC, the BCT file must be placed on storage supported by the cluster configuration and managed appropriately for the release.

### 9.1 BCT and restore/resetlogs

After a restore, duplicate, resetlogs, or architectural change, verify the BCT status. Some operations can make the BCT file unsuitable or require recreating it. Never assume a BCT file from a source database can always be reused on a cloned/target database.

### 9.2 BCT is not part of the recovery chain

RMAN restore/recover requires appropriate backups and redo. BCT only helps create future incremental backups faster. Losing the BCT file does not mean losing the ability to restore from existing backups.

## 10. How can BCT improve incremental backups?

Suppose:

- A datafile has 500 GB of used blocks.
- Only 1% of blocks change per day.
- A level 1 backup needs roughly 5 GB of changed blocks before compression.

Without BCT, RMAN may have to read many blocks across the 500 GB datafile to find changed blocks. With BCT, RMAN can rely on the bitmap to read only the regions with changes and back up the roughly 5 GB of needed blocks.

These numbers are illustrative. BCT does not guarantee an exact 100:1 I/O reduction because actual results depend on block distribution, bitmap granularity, file layout, backup type, and other factors.

### 10.1 BCT primarily reduces reads when identifying blocks

BCT does not necessarily make backup pieces smaller than an identical incremental backup without BCT. The actual block contents backed up are still determined by data changes. The primary benefit is reducing the read/scan workload to locate changed blocks.

### 10.2 BCT does not speed up full/level 0 backups in the same way

A full backup or incremental level 0 backup must read all blocks required for the baseline. BCT does not allow skipping blocks unchanged since a previous baseline because the baseline must contain the current data.

The primary benefit of BCT is for incremental level 1 backups.

## 11. Configuring and monitoring BCT

### 11.1 Checking status

~~~sql
SELECT status,
       filename,
       bytes
FROM v$block_change_tracking;
~~~

### 11.2 Checking the file at the OS level

The DBA can verify file existence, ownership, and size at the OS level. Do not modify the contents or move the file without notifying the database using the appropriate command.

### 11.3 Monitoring incremental backups

RMAN output and backup metadata show duration, bytes, datafiles, and backup sets. You can query:

~~~sql
SELECT session_key,
       input_type,
       status,
       start_time,
       end_time,
       elapsed_seconds,
       input_bytes,
       output_bytes,
       input_bytes_per_sec,
       output_bytes_per_sec
FROM v$rman_backup_job_details
ORDER BY start_time DESC;
~~~

Columns may vary by version and privileges. Compare level 1 jobs before and after enabling BCT under the same workload; do not compare two jobs with different workloads.

## 12. Creating full and incremental backups with RMAN

### 12.1 Full backup

~~~text
RMAN> BACKUP DATABASE;
~~~

Creates a full database backup. This is not a level 0 baseline for an incremental chain.

### 12.2 Incremental level 0

~~~text
RMAN> BACKUP INCREMENTAL LEVEL 0 DATABASE;
~~~

Creates the baseline for level 1 backups.

### 12.3 Incremental level 1 differential

~~~text
RMAN> BACKUP INCREMENTAL LEVEL 1 DATABASE;
~~~

Without the CUMULATIVE keyword, level 1 defaults to differential.

### 12.4 Incremental level 1 cumulative

~~~text
RMAN> BACKUP INCREMENTAL LEVEL 1 CUMULATIVE DATABASE;
~~~

Backs up blocks changed since the most recent level 0 backup.

### 12.5 Including archived redo logs

~~~text
RMAN> BACKUP DATABASE PLUS ARCHIVELOG;
~~~

Or:

~~~text
RMAN> BACKUP INCREMENTAL LEVEL 1 DATABASE PLUS ARCHIVELOG;
~~~

PLUS ARCHIVELOG instructs RMAN to handle archived redo logs as part of the command flow. Check output to confirm required sequences were backed up.

## 13. Example differential backup schedule

Suppose a database runs in ARCHIVELOG mode with level 0 on Sunday and level 1 differential daily:

| Day | Backup command/type | Purpose |
|---|---|---|
| Sunday | Level 0 | Weekly baseline |
| Monday | Level 1 differential | Blocks changed since level 0 |
| Tuesday | Level 1 differential | Blocks changed since Monday's level 1 |
| Wednesday | Level 1 differential | Blocks changed since Tuesday's level 1 |
| Thursday | Level 1 differential | Blocks changed since Wednesday's level 1 |
| Friday | Level 1 differential | Blocks changed since Thursday's level 1 |
| Saturday | Level 1 differential | Blocks changed since Friday's level 1 |

Archived redo logs are backed up frequently between datafile backups to meet the RPO.

## 14. Example cumulative backup schedule

| Day | Backup command/type | Purpose |
|---|---|---|
| Sunday | Level 0 | Weekly baseline |
| Monday | Level 1 cumulative | Changes since Sunday |
| Tuesday | Level 1 cumulative | All changes since Sunday |
| Wednesday | Level 1 cumulative | All changes since Sunday |
| Thursday | Level 1 cumulative | All changes since Sunday |
| Friday | Level 1 cumulative | All changes since Sunday |
| Saturday | Level 1 cumulative | All changes since Sunday |

Restoring to Saturday can use Sunday's level 0 and Saturday's cumulative level 1, followed by applying the required archived redo logs.

## 15. Choosing differential vs. cumulative

Consider the following:

**Differential**

- Small daily change rate.
- Tight backup window.
- Want to minimize daily incremental storage.
- Acceptable to apply multiple incrementals during restore.
- Reliable tooling and processes for automatic chain selection.

**Cumulative**

- Want to reduce the number of incrementals to apply during restore.
- Restore time matters more than growing backup size.
- Sufficient storage capacity.
- Level 0 cycle is not overly long.
- Change rate does not make cumulative backups prohibitively large.

You can combine daily differential backups with periodic cumulative backups to balance backup windows and restore times. Always test the actual chain before deciding.

## 16. Incremental merge with image copies

Incremental merge is a strategy that updates an image copy using incremental backups to maintain a copy close to the current state.

Concept:

1. Create an image copy baseline.
2. Create level 1 incrementals for changed blocks.
3. Use RECOVER COPY to merge incrementals into the image copy.
4. The image copy is updated incrementally over time.

Skeleton example:

~~~text
RMAN> BACKUP INCREMENTAL LEVEL 0
      FOR RECOVER OF COPY WITH TAG 'DAILY_MERGE'
      DATABASE;

RMAN> RECOVER COPY OF DATABASE
      WITH TAG 'DAILY_MERGE';

RMAN> BACKUP INCREMENTAL LEVEL 1
      FOR RECOVER OF COPY WITH TAG 'DAILY_MERGE'
      DATABASE;
~~~

This is a skeleton example for incremental merge. The full order and scheduling must follow your release's RMAN runbook, since the first run creates the baseline image copy and subsequent runs produce incrementals to merge.

### 16.1 Benefits

- Maintains a near-current image copy.
- Can reduce the time needed to restore datafiles because the copy is already updated.
- Well-suited when RTO is critical and sufficient disk space is available.

### 16.2 Costs

- Requires storage for both the image copy and incrementals.
- Requires scheduling the merge step.
- Requires managing tags and checkpoints.
- Must verify that the image copy is recoverable and at the expected point.

Incremental merge does not replace archived redo logs if you need to recover to a point after the image copy.

## 17. RMAN CONFIGURE and backup scripts

RMAN allows saving default configurations:

~~~text
RMAN> CONFIGURE RETENTION POLICY TO RECOVERY WINDOW OF 14 DAYS;
RMAN> CONFIGURE CONTROLFILE AUTOBACKUP ON;
RMAN> CONFIGURE DEVICE TYPE DISK PARALLELISM 2;
RMAN> CONFIGURE BACKUP OPTIMIZATION ON;
~~~

BACKUP OPTIMIZATION can skip re-backing up certain files already backed up according to RMAN rules. Understand its impact on archive logs and retention before enabling it.

### 17.1 Example level 0 script

~~~text
RUN {
  BACKUP INCREMENTAL LEVEL 0
    DATABASE
    TAG 'WEEKLY_L0';

  BACKUP ARCHIVELOG ALL
    TAG 'ARCHIVE_WEEKLY';

  BACKUP CURRENT CONTROLFILE;
}
~~~

### 17.2 Example level 1 differential script

~~~text
RUN {
  BACKUP INCREMENTAL LEVEL 1
    DATABASE
    TAG 'DAILY_L1_DIFF';

  BACKUP ARCHIVELOG ALL
    TAG 'DAILY_ARCH';
}
~~~

### 17.3 Example level 1 cumulative script

~~~text
RUN {
  BACKUP INCREMENTAL LEVEL 1 CUMULATIVE
    DATABASE
    TAG 'DAILY_L1_CUM';

  BACKUP ARCHIVELOG ALL
    TAG 'DAILY_ARCH';
}
~~~

Production scripts must add channels, format strings, encryption, logging, deletion policies, and error handling per organizational standards. Never run a production script without testing it in an equivalent environment first.

## 18. Backup compression and encryption

RMAN backup sets can use compression:

~~~text
RMAN> BACKUP AS COMPRESSED BACKUPSET DATABASE;
~~~

Compression can reduce storage footprint but consumes CPU and can slow down backup/restore. Choose the algorithm/level based on licensing and version.

Backup encryption is a separate mechanism:

- Transparent encryption can rely on a keystore.
- Password encryption requires a password during restore.
- Dual mode combines mechanisms as supported by the release.

If the database uses TDE, do not assume every backup file or export is encrypted the same way. Verify both the backup type and RMAN encryption configuration.

## 19. Restoring and recovering from level 0/1

Restore retrieves datafiles from backups. Recover applies incremental backups and redo to bring datafiles to a consistent state.

### 19.1 Complete recovery

~~~text
RMAN> STARTUP MOUNT;
RMAN> RESTORE DATABASE;
RMAN> RECOVER DATABASE;
RMAN> ALTER DATABASE OPEN;
~~~

RMAN automatically selects the appropriate backups, incrementals, and archive logs based on the repository and recovery target. In practice, you may need to restore the control file, catalog, SPFILE, and keystore first.

### 19.2 Previewing a restore

~~~text
RMAN> RESTORE DATABASE PREVIEW;
~~~

PREVIEW lists the backups RMAN plans to use, helping verify the chain and required files.

### 19.3 Validating backup readability

~~~text
RMAN> RESTORE DATABASE VALIDATE;
~~~

VALIDATE reads and checks backups within scope, but does not produce restored datafiles and does not prove that full recovery and open will succeed.

### 19.4 Point-in-time recovery

~~~text
RMAN> RUN {
  SET UNTIL TIME
    "TO_DATE('2026-11-14 10:30:00',
             'YYYY-MM-DD HH24:MI:SS')";
  RESTORE DATABASE;
  RECOVER DATABASE;
}
RMAN> ALTER DATABASE OPEN RESETLOGS;
~~~

This is an example of incomplete recovery. The target time must be specified according to the database's timezone and clock. After OPEN RESETLOGS, the database creates a new incarnation and requires a new backup plan.

## 20. Level 1 backups and archived redo logs have distinct roles

An incremental level 1 backup contains blocks changed since a previous incremental backup. Archived redo logs contain redo records to replay changes by SCN.

These two file types do not replace each other:

- Incremental backups quickly advance datafiles to a backup checkpoint.
- Archived redo logs apply changes after the backup checkpoint up to the recovery target time.

Example:

~~~text
Level 0 (Sunday)
      |
      v
Level 1 (Wednesday)
      |
      v
Archived redo logs (Wed -> Fri 14:30)
      |
      v
Target recovery point: Friday 14:30
~~~

If required archived redo logs after an incremental backup are missing, the database may fail to recover to the target SCN.

## 21. Block Change Tracking and restore/recovery

BCT is not used to reconstruct data during a restore. When restoring a database, RMAN uses datafile backups and redo. The BCT file is acceleration metadata for future incremental backups.

After a restore:

- Check V$BLOCK_CHANGE_TRACKING.
- If the status is not ENABLED or the file is invalid, reconfigure it.
- Do not let a missing BCT file block a restore if backups and redo are complete.
- The first incremental backup after recreating BCT may need to read more datafile blocks.

## 22. Checking backup metadata

### 22.1 LIST BACKUP

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> LIST BACKUP OF DATABASE;
RMAN> LIST BACKUP OF ARCHIVELOG ALL;
~~~

### 22.2 REPORT NEED BACKUP

~~~text
RMAN> REPORT NEED BACKUP;
~~~

Reports datafiles needing backup according to the retention policy/configuration. Interpret the output in the context of your policy and RPO.

### 22.3 CROSSCHECK

~~~text
RMAN> CROSSCHECK BACKUP;
RMAN> CROSSCHECK ARCHIVELOG ALL;
~~~

CROSSCHECK reconciles the repository with physical files on disk/media. It does not re-back up missing files.

### 22.4 DELETE EXPIRED

~~~text
RMAN> DELETE EXPIRED BACKUP;
RMAN> DELETE EXPIRED ARCHIVELOG ALL;
~~~

DELETE EXPIRED removes expired records from the repository after crosscheck finds that the physical files no longer exist. It is not a command to delete all old backups based on retention.

### 22.5 DELETE OBSOLETE

~~~text
RMAN> REPORT OBSOLETE;
RMAN> DELETE OBSOLETE;
~~~

DELETE OBSOLETE deletes backups no longer required under the retention policy. Before running it, verify your policy, off-site copies, standby requirements, and restore chains.

## 23. Designing retention for an incremental chain

Retention must be sufficient to keep:

- The level 0 baseline.
- Necessary differential/cumulative level 1 backups.
- Archived redo logs to recover to the target.
- Control file/SPFILE backups.
- Off-site backups.

If retention deletes level 0 too early, level 1 backups may lose a valid restore path. If archive logs are kept for too short a period, PITR to an older target may fail.

### 23.1 Recovery window

Example:

~~~text
RMAN> CONFIGURE RETENTION POLICY
     TO RECOVERY WINDOW OF 14 DAYS;
~~~

A 14-day recovery window does not simply mean deleting every file older than 14 days. RMAN must retain the backups required to guarantee recoverability across the window, including older baseline backups.

### 23.2 Redundancy

~~~text
RMAN> CONFIGURE RETENTION POLICY TO REDUNDANCY 2;
~~~

Redundancy 2 keeps enough backups according to RMAN rules to maintain two required copies. It is not equivalent to a day-based recovery window.

## 24. Performance: measuring incremental and BCT effectiveness

To evaluate BCT, compare incremental backups before and after enabling it under equivalent workloads:

- Backup duration.
- Input bytes.
- Output bytes.
- Read throughput.
- CPU.
- Storage IOPS/latency.
- Block change ratio.
- Backup piece size.

Do not compare a level 0 backup with a level 1 backup to conclude how much BCT improved performance; these are two backup types with different data volumes.

### 24.1 Reading RMAN job details

~~~sql
SELECT session_key,
       input_type,
       status,
       start_time,
       end_time,
       elapsed_seconds,
       input_bytes,
       output_bytes,
       input_bytes_per_sec,
       output_bytes_per_sec
FROM v$rman_backup_job_details
ORDER BY start_time DESC;
~~~

### 24.2 Reading RMAN backup sets

~~~sql
SELECT set_stamp,
       set_count,
       backup_type,
       incremental_level,
       pieces,
       start_time,
       completion_time
FROM v$backup_set
ORDER BY completion_time DESC;
~~~

View names/columns may vary by version. RMAN `LIST BACKUP` is a direct check and is often easier for operators to read.

## 25. BCT in RAC and Data Guard environments

### 25.1 RAC

The BCT file must reside on storage appropriate for the RAC architecture and be managed by the database. DBAs must check its status while instances are active, verify the shared path, and ensure accessibility from all nodes as required by the release.

Do not place the BCT file on a single node's local filesystem if the database/backup architecture requires other instances to access it.

### 25.2 Data Guard

Primary and standby databases can each have their own BCT file to accelerate incremental backups taken on each database. The BCT file is not redo transported like archived logs.

After a switchover/failover, check the BCT status on the new primary and wherever backups are taken. Do not assume the primary's BCT file automatically becomes a valid BCT file on the standby.

## 26. Common incremental backup issues

| Symptom | Possible cause | Troubleshooting direction |
|---|---|---|
| Level 1 is nearly as large as level 0 | Many blocks changed or different compression | Measure changed-block ratio and backup type |
| RMAN creates a level 0 when level 1 was requested | No suitable level 0 exists | Check LIST BACKUP and baseline |
| Restore requires many incrementals | Differential chain | Consider cumulative or more frequent level 0s |
| Incremental backup still reads many datafiles | BCT disabled, unavailable, or high change rate | Check V$BLOCK_CHANGE_TRACKING |
| BCT status is DISABLED | Not enabled or was disabled | Re-enable after verifying file location |
| BCT file lost | Filesystem/storage issue | Recreate BCT; next incremental may scan heavily |
| Restore validate succeeds but recovery fails | Missing archive logs or backup chain | Run RESTORE PREVIEW, check thread/sequence/SCN |
| Backup piece marked EXPIRED | File missing or inaccessible | Run CROSSCHECK, inspect storage and repository |
| FRA full | Archive logs/backups/flashback consuming space | Use RMAN policies, increase capacity, never delete via OS |
| Backup job slows down after increasing parallelism | I/O/CPU/network contention | Tune channels/parallelism |

## 27. Common mistakes

| Mistake | Consequence | Correct practice |
|---|---|---|
| Treating a full backup as level 0 | Incremental chain lacks a valid baseline | Run BACKUP INCREMENTAL LEVEL 0 |
| Assuming level 1 is always cumulative | Misunderstood restore dependencies | Explicitly specify differential or cumulative |
| Thinking BCT creates backups | Real RMAN backups are skipped | Use BCT alongside RMAN incremental backups |
| Thinking BCT makes backups smaller | Misunderstanding BCT's role | BCT mainly reduces scanning to find changed blocks |
| Thinking BCT is required for restore | Assuming losing BCT means losing data | BCT is not part of the recovery chain |
| Keeping level 1s while deleting level 0 | No baseline left for restore | Retain chains via retention policy |
| Deleting intermediate differentials | Can break a required restore chain | Use RMAN retention and verify with restore preview |
| Backing up only datafiles, not archive logs | Cannot recover to a target time | Back up archived redo logs |
| Not backing up control file/SPFILE | Difficult to rebuild database | Enable control file autobackup |
| Not backing up the TDE keystore | Cannot decrypt data | Protect the keystore alongside backups |
| Setting maximum parallelism blindly | Causes I/O/CPU contention | Benchmark and limit channels |
| Running only RESTORE VALIDATE | Does not prove complete recovery works | Practice full restore/recover/open drills |
| Using BCT without checking status | Assuming BCT is active while disabled | Monitor V$BLOCK_CHANGE_TRACKING |
| Assuming small incrementals mean fast restore | May have to apply a long chain | Measure both backup and restore times |

## 28. Self-check practice exercises

Exercises should be performed in a lab database or an environment approved by the DBA.

### Exercise 1 — Full backup

Run BACKUP DATABASE. Use LIST BACKUP to identify the backup type and explain why it is not a level 0.

### Exercise 2 — Level 0 baseline

Run BACKUP INCREMENTAL LEVEL 0 DATABASE. Inspect the incremental_level and tag metadata in the RMAN repository.

### Exercise 3 — Differential level 1

Modify data between two backups. Run differential level 1 backups across several days and diagram the parent/child chain.

### Exercise 4 — Cumulative level 1

Create a level 0 and then run cumulative level 1 backups across several days. Compare the volume of blocks backed up and the restore chain.

### Exercise 5 — Enable BCT

Enable BCT in the lab, check V$BLOCK_CHANGE_TRACKING and the file location.

### Exercise 6 — Measure incremental before/after BCT

Run a workload that changes a small percentage of blocks. Compare elapsed time and input bytes of incremental level 1 before and after enabling BCT.

### Exercise 7 — Disable and re-enable BCT

Disable BCT and verify its status. Re-enable it with a new file and check the next incremental backup.

### Exercise 8 — Restore preview

Run RESTORE DATABASE PREVIEW. Note the backup pieces and incrementals required for the restore.

### Exercise 9 — Restore validate

Run RESTORE DATABASE VALIDATE and distinguish its result from an actual restore/recover.

### Exercise 10 — Incremental merge

In the lab, create an image copy baseline and run RECOVER COPY along with level 1 FOR RECOVER OF COPY. Verify that the image copy is updated.

### Exercise 11 — Retention

Test REPORT OBSOLETE and REPORT NEED BACKUP. Explain why an older level 0 backup might still need to be retained.

### Exercise 12 — Recovery drill

Restore a level 0 backup, apply the incremental chain and archived redo logs up to a target time. Record the restore, recover, and open durations.

## 29. Backup design checklist

**Business requirements**

- Are RPO and RTO approved?
- How many days of PITR are required?
- Does the database use Data Guard/RAC/TDE?
- Are there off-site/immutable backup requirements?

**Level strategy**

- Full backup or level 0 baseline?
- Differential or cumulative level 1?
- Level 0 frequency?
- Is incremental merge needed?
- What is the maximum acceptable restore chain length?

**BCT**

- Are incremental level 1 backups frequent?
- Is the changed-block ratio low enough for BCT to help?
- Is the BCT file on appropriate storage?
- Are STATUS/FILENAME monitored?
- Is there a post-restore/clone/resetlogs plan?

**RMAN**

- Are both database and archive logs backed up?
- Control file autobackup enabled?
- SPFILE backed up?
- Retention/deletion policy configured?
- Channels/parallelism tuned?
- Backup encryption/compression configured?
- Recovery catalog used?

**Recoverability**

- RESTORE PREVIEW checked?
- RESTORE VALIDATE checked?
- Sufficient archive sequences/threads?
- TDE keystore available?
- Restore/recover/open drilled?
- Does actual RTO meet targets?

## 30. Key takeaways

| Concept | What to remember |
|---|---|
| Full backup | Complete backup, not a parent for level 1 |
| Incremental level 0 | Baseline for an incremental strategy |
| Incremental level 1 | Backs up blocks changed since a prior reference point |
| Differential level 1 | Changes since the most recent level 0 or level 1 |
| Cumulative level 1 | Changes since the most recent level 0 |
| BCT | Bitmap recording changed blocks to help RMAN locate them faster |
| BCT file | Auxiliary file, not a data backup |
| BACKUP DATABASE | Creates a full backup |
| BACKUP INCREMENTAL LEVEL 0 | Creates an incremental baseline |
| BACKUP INCREMENTAL LEVEL 1 | Creates a differential level 1 |
| BACKUP INCREMENTAL LEVEL 1 CUMULATIVE | Creates a cumulative level 1 |
| FOR RECOVER OF COPY | Supports incremental merge with image copies |
| RESTORE | Restores files from backups |
| RECOVER | Applies incrementals and redo |
| RESTORE PREVIEW | Previews backups needed for restore |
| RESTORE VALIDATE | Checks backup readability, does not replace a restore drill |
| Retention policy | Determines which backups must be retained |
| Archived redo log | Enables recovery past the backup checkpoint |
| RPO/RTO | Data loss and recovery time objectives |

A full backup is an independent backup, whereas an incremental level 0 is the baseline for level 1 backups. Differential level 1 typically saves more storage but may require applying multiple incrementals during restore; cumulative level 1 simplifies restores but grows larger throughout the cycle. BCT tracks changed blocks to reduce the scanning work of incremental backups, does not create backups itself, and does not replace archived redo logs. Design your schedule around RPO/RTO, measure both backup and restore times, retain all required level 0/1 backups and archive logs, protect control files/SPFILE/keystores, and validate everything with regular restore drills.
