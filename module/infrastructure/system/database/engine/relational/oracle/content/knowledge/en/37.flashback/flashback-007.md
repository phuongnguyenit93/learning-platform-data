# Flashback Database, Flashback Logs, and Recovery Area Configuration

Flashback Database is the ability to return an entire Oracle database to an earlier point in time or SCN using flashback logs combined with redo. This feature is useful when a deployment, data update, or configuration change produces unintended results. Instead of restoring all datafiles from backups and performing media recovery, the DBA can revert data blocks to their prior state if the required flashback logs remain available.

Flashback Database must be prepared prior to an incident. The database must run in ARCHIVELOG mode, the recovery area must be configured with sufficient capacity, and the feature must be enabled before the point in time to which you want to rewind. Flashback logs are not backups and do not replace an RMAN backup strategy.

## 1. Key concepts

### Flashback Database

Flashback Database returns the state of the entire database to a point in time, SCN, or restore point. The scope of impact is database-wide: changes after the chosen anchor are removed from the database state once reopened.

For example, before deploying a new application release, the DBA creates a restore point. If the deployment fails and corrupts data unexpectedly, the DBA can flashback the database to that restore point.

Flashback Database differs from narrower Flashback features:

| Feature | Scope and purpose |
|---|---|
| Flashback Database | Returns the entire database to a timestamp or SCN |
| Flashback Table | Returns one or more tables to a prior state when feature prerequisites are met |
| Flashback Query | Queries data at a past point in time using syntax such as `AS OF TIMESTAMP` |
| Flashback Transaction | Analyzes or generates compensating statements for a previously executed transaction |
| RMAN point-in-time recovery | Recovers a database or tablespace using backups and redo to a specified point |

Choose Flashback Table or Flashback Query when you only need to inspect or recover part of the data. Flashback Database is appropriate when you need to rewind the state of the entire database.

### Flashback logs

Flashback logs store before-images of blocks prior to modification, enabling Oracle to reconstruct earlier block states. The RVWR (Recovery Writer) background process writes flashback data to flashback logs during database operation whenever Flashback Database is enabled.

When executing Flashback Database, Oracle uses flashback logs to revert blocks to their prior state and applies the necessary redo to ensure database consistency at the target point. Flashback logs serve a different purpose and format from online redo logs or archived redo logs:

- Online redo logs record changes to support instance recovery and recovery processing.
- Archived redo logs are archived copies of filled redo logs, used in media recovery, backups, and restore operations.
- Flashback logs store pre-change block images to support rewinding the database backward in time.

Flashback logs are managed by Oracle inside the Fast Recovery Area (FRA). DBAs should never manually move, rename, or delete these files via the operating system.

### SCN, timestamp, and restore points

An SCN (System Change Number) is the change sequence number Oracle uses to identify a consistent point. You can request flashback by SCN or timestamp. SCN is generally preferred when an exact anchor recorded in logs or during incident investigation is required.

A restore point is a named label attached to an SCN for easy DBA reference. Two types are commonly used:

- A normal restore point records an SCN milestone. It does not force Oracle to retain all flashback logs indefinitely; usability depends on whether flashback logs remain available.
- A guaranteed restore point instructs Oracle to retain the flashback logs required to rewind to that milestone, as long as the restore point exists and the database can continue creating and storing necessary logs. It can cause the FRA to grow rapidly if kept too long.

## 2. Fast Recovery Area (FRA)

The Fast Recovery Area is a storage area managed by Oracle for backup and recovery files. Depending on configuration, the FRA can contain:

- Flashback logs.
- Archived redo logs.
- RMAN backup pieces and image copies.
- Control file autobackups and SPFILE autobackups.
- Copies of control files or online redo logs if configured inside the FRA.

The FRA helps Oracle and RMAN manage space utilization, identify reusable files, and reclaim files when needed according to recovery policies. Whether a file can be reclaimed depends on recovery state, RMAN policies, Data Guard needs, and active restore points.

The two most important parameters for configuring the FRA are:

| Parameter | Meaning |
|---|---|
| `DB_RECOVERY_FILE_DEST` | Directory path or disk group used as the FRA |
| `DB_RECOVERY_FILE_DEST_SIZE` | Upper size limit on the FRA that Oracle is permitted to use |

`DB_RECOVERY_FILE_DEST_SIZE` must be set before setting `DB_RECOVERY_FILE_DEST`. The SIZE value is an Oracle-managed quota, not a guarantee that the storage device actually has that amount of free space. The DBA must verify physical capacity, filesystem or ASM overhead, and leave headroom for growth.

For example, configuring the FRA on ASM disk group `+RECO` with a 120 GB limit:

```sql
ALTER SYSTEM SET DB_RECOVERY_FILE_DEST_SIZE = 120G SCOPE=BOTH;
ALTER SYSTEM SET DB_RECOVERY_FILE_DEST = '+RECO' SCOPE=BOTH;
```

If using a filesystem, replace `+RECO` with a valid path such as `/u01/app/oracle/fast_recovery_area`. The directory must exist and the Oracle Database software owner must have appropriate permissions.

`SCOPE=BOTH` assumes the database uses an SPFILE and applies the change to both memory and persistent configuration. If the database starts with a PFILE, update the parameter file appropriately and follow that environment's restart procedure. In Oracle RAC, the FRA must reside on shared storage accessible to all instances, and parameter configuration must be consistent across instances.

## 3. Configuring retention and enabling Flashback Database

### Prerequisites before enabling

Before configuring, the DBA must confirm:

1. The database is in ARCHIVELOG mode.
2. The FRA is configured and has sufficient free space.
3. Storage provides performance and reliability suited to the database's write workload.
4. RMAN, archived log, and Data Guard (if any) policies do not conflict with flashback log retention needs.
5. Valid backups exist. Flashback Database does not replace backups when datafiles or storage are lost.

Check current status:

```sql
SELECT name, log_mode, flashback_on, open_mode
FROM v$database;
```

If `LOG_MODE` is `NOARCHIVELOG`, switch the database to ARCHIVELOG. This operation requires the database to be in MOUNT state:

```sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
ALTER DATABASE ARCHIVELOG;
```

Flashback Database can be enabled immediately while the database remains in MOUNT state:

```sql
ALTER DATABASE FLASHBACK ON;
ALTER DATABASE OPEN;
```

If the database is already in ARCHIVELOG mode, simply bring the database to MOUNT before enabling Flashback Database:

```sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
ALTER DATABASE FLASHBACK ON;
ALTER DATABASE OPEN;
```

In a live environment, schedule operations requiring shutdown and follow the system's operational procedures. The commands above illustrate a single-instance database; RAC or Data Guard environments must follow their corresponding procedures.

### Setting the flashback log retention target

The `DB_FLASHBACK_RETENTION_TARGET` parameter sets the target retention window for flashback logs, measured in minutes. The default value is typically 1440 minutes (24 hours).

```sql
ALTER SYSTEM SET DB_FLASHBACK_RETENTION_TARGET = 1440 SCOPE=BOTH;
```

Setting a target of 1440 minutes means Oracle attempts to retain enough flashback logs to support rewinding roughly 24 hours. This is not an absolute guarantee that the database can always flashback a full 24 hours. Actual retention depends on block modification rate, FRA capacity, files needed for recovery, and restore points.

To estimate capacity, monitor the volume of flashback data generated during peak load periods, scale by the target retention, and add space for archived logs, backups, restore points, and headroom. Do not size the FRA solely by database size; block change rate and log generation velocity are the decisive factors.

### Verifying the feature is enabled

```sql
SELECT log_mode, flashback_on
FROM v$database;

SHOW PARAMETER db_recovery_file_dest;
SHOW PARAMETER db_recovery_file_dest_size;
SHOW PARAMETER db_flashback_retention_target;
```

`FLASHBACK_ON` typically shows `YES` when Flashback Database is enabled. Also check the available flashback window in `V$FLASHBACK_DATABASE_LOG` and FRA status; looking solely at configuration parameters is insufficient to conclude the database can rewind to any desired milestone.

## 4. Creating and managing restore points

Create a normal restore point before a major operation:

```sql
CREATE RESTORE POINT before_release;
```

Create a guaranteed restore point when the ability to return to the pre-change milestone must be guaranteed:

```sql
CREATE RESTORE POINT before_upgrade
GUARANTEE FLASHBACK DATABASE;
```

Restore point names should clearly describe their purpose and creation context. Once the work is complete and rollback capability is no longer needed, drop the restore point:

```sql
DROP RESTORE POINT before_upgrade;
```

You can inspect existing restore points:

```sql
SELECT name,
       scn,
       time,
       guarantee_flashback_database,
       storage_size
FROM v$restore_point
ORDER BY time;
```

Guaranteed restore points can retain flashback logs beyond the target retention window. If you forget to drop a restore point after deployment, the FRA may fill up even if the DBA configured a relatively short retention target. When the FRA runs out of space to write required files, the database may fail to archive redo logs or other recovery operations may be affected. Therefore, every restore point must have a clear owner, purpose, and planned drop time.

## 5. Monitoring flashback logs and FRA capacity

DBAs should monitor both the effective flashback window and FRA capacity. Useful dynamic views include:

| View | Key information |
|---|---|
| `V$DATABASE` | ARCHIVELOG mode, Flashback Database status, and open mode |
| `V$FLASHBACK_DATABASE_LOG` | Oldest flashback milestone, retention target, flashback log size, and estimated size |
| `V$FLASHBACK_DATABASE_STAT` | Volume of flashback data, database data, and redo across statistical intervals |
| `V$RECOVERY_FILE_DEST` | FRA limit, space used, and reclaimable space |
| `V$FLASH_RECOVERY_AREA_USAGE` | Percentage of FRA space used by each file type |
| `V$RESTORE_POINT` | Restore points and associated storage usage |

Check the oldest timestamp currently supported by available flashback logs:

```sql
SELECT oldest_flashback_scn,
       oldest_flashback_time,
       retention_target,
       flashback_size,
       estimated_flashback_size
FROM v$flashback_database_log;
```

Check overall FRA capacity:

```sql
SELECT name,
       space_limit,
       space_used,
       space_reclaimable,
       number_of_files
FROM v$recovery_file_dest;
```

Check which file types occupy the FRA:

```sql
SELECT file_type,
       percent_space_used,
       percent_space_reclaimable,
       number_of_files
FROM v$flash_recovery_area_usage
ORDER BY percent_space_used DESC;
```

Monitor flashback data generation rate over time:

```sql
SELECT begin_time,
       end_time,
       flashback_data,
       db_data,
       redo_data,
       estimated_flashback_size
FROM v$flashback_database_stat
ORDER BY begin_time;
```

Size columns in these views are typically expressed in bytes. Convert them to MB or GB when building monitoring reports. Observe multiple workload cycles, including peak hours and major batch runs, to size the FRA properly.

A high FRA utilization percentage does not necessarily mean an immediate incident if plenty of files are reclaimable. Conversely, low `SPACE_RECLAIMABLE` paired with utilization near the limit is a warning sign requiring prompt action. Guaranteed restore points can prevent needed flashback logs from being reclaimed, so monitor existing restore points separately.

## 6. Flashbacking the entire database to a milestone

Flashback Database is an operation that impacts the entire database. Determine the exact target point and assess data impact before executing.

General workflow:

1. Determine the SCN, timestamp, or restore point to rewind to. Cross-check against the incident start time and the scope of changes to discard.
2. Check `V$FLASHBACK_DATABASE_LOG` to confirm the target point lies within the available log window. If using a restore point, verify that the restore point exists.
3. Stop applications or data-writing jobs per the system runbook.
4. Shut down the database and start it in MOUNT state.
5. Run the Flashback Database command to the chosen milestone.
6. Open the database with `RESETLOGS`.
7. Verify data, application status, and take a new backup according to RMAN policy.

Example flashback by SCN:

```sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;

FLASHBACK DATABASE TO SCN 123456789;

ALTER DATABASE OPEN RESETLOGS;
```

Example flashback by timestamp:

```sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;

FLASHBACK DATABASE TO TIMESTAMP
  (SYSTIMESTAMP - INTERVAL '30' MINUTE);

ALTER DATABASE OPEN RESETLOGS;
```

Example flashback to a guaranteed restore point:

```sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;

FLASHBACK DATABASE TO RESTORE POINT before_upgrade;

ALTER DATABASE OPEN RESETLOGS;
```

After Flashback Database, the database must be opened with `RESETLOGS`. This creates a new database incarnation. The DBA must check the incarnation in RMAN and take a new backup to establish a recovery baseline for the post-flashback database state.

Never run a flashback command merely because a timestamp looks plausible. If you pick a point too early, all valid changes after that point are also discarded from the database state. Clearly determine which data will be lost, inform application owners, and prepare verification checks after opening the database.

## 7. Operations, troubleshooting, and limitations

### FRA nearly full or full

When the FRA approaches its limit, identify which file types consume space using `V$FLASH_RECOVERY_AREA_USAGE`, then review RMAN policies and restore points. Typical remediation steps include:

- Confirm `DB_RECOVERY_FILE_DEST_SIZE` and actual physical space on the filesystem or ASM.
- Check whether restore points are still needed; drop expired restore points once confirmed by their owners.
- Check backup retention policies, archived log deletion policies, and backup status.
- Use RMAN to manage obsolete or expired files according to established policy, such as `DELETE OBSOLETE` after verifying the retention policy.
- Increase the FRA limit or expand storage when actual storage demand grows.

Never delete flashback logs, archived redo logs, or backup files directly via OS commands. Deleting files outside Oracle's management can desynchronize metadata and recovery state. Likewise, do not delete archived logs merely to free space without checking recovery and Data Guard requirements.

### Unable to flashback to the requested milestone

If the target point is older than `OLDEST_FLASHBACK_TIME`, the required flashback logs may have been reclaimed or never existed. Re-verify the SCN, timestamp, actual retention, and restore points. If sufficient flashback logs no longer exist, evaluate RMAN point-in-time recovery from backups and archived redo logs.

If Flashback Database was not enabled at the time the incident occurred, flashback logs cannot be retroactively generated for that earlier period. Increasing `DB_FLASHBACK_RETENTION_TARGET` after the incident also cannot restore lost logs.

### Limitations to remember

- Flashback Database is only effective when the required flashback logs remain available and the database satisfies feature prerequisites.
- It is not a recovery solution when datafiles or storage devices are lost. That case still requires backups and media recovery.
- `NOLOGGING` operations and certain structural operations or changes can impose limitations on flashback capability or require additional handling. Check documentation for your exact Oracle release and test in a similar environment.
- Flashback Database rewinds the entire database. If only a single table is affected, consider a narrower Flashback feature.
- After `OPEN RESETLOGS`, the database moves to a new incarnation. Update backup plans and verify RMAN status.
- The retention target is a goal, not a guarantee. High write rates, insufficient FRA space, or long-lived guaranteed restore points can substantially alter storage usage.

## 8. Configuration and operations checklist

Before relying on Flashback Database, a DBA can verify each item in order:

- [ ] The database is in ARCHIVELOG mode.
- [ ] `DB_RECOVERY_FILE_DEST_SIZE` is set before `DB_RECOVERY_FILE_DEST`.
- [ ] The FRA points to valid storage with sufficient physical capacity and headroom.
- [ ] `DB_FLASHBACK_RETENTION_TARGET` reflects operational objectives.
- [ ] `V$DATABASE.FLASHBACK_ON` confirms the feature is enabled.
- [ ] `V$FLASHBACK_DATABASE_LOG` shows an adequate effective flashback window.
- [ ] Monitoring alerts are configured for the FRA, archived logs, and guaranteed restore points.
- [ ] Every restore point has a clear purpose, owner, and drop plan.
- [ ] RMAN backups and media recovery procedures remain maintained.
- [ ] The flashback procedure has been rehearsed, including data verification after `OPEN RESETLOGS`.

Flashback Database provides a fast rewind path when logical changes or data operations cause an incident. Its effectiveness depends on proper FRA configuration, maintaining ARCHIVELOG mode, monitoring flashback logs, and disciplined restore point management. DBAs should treat Flashback Database as one layer in an overall data protection strategy, working alongside RMAN backups, archived redo logs, and recovery testing procedures.
