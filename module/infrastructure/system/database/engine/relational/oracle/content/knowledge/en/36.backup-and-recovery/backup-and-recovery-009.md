# LIST, REPORT, CROSSCHECK, EXPIRED, and OBSOLETE in RMAN

Oracle Recovery Manager (RMAN) stores information about database backups and copies in the **RMAN repository**. The repository records which backups were created, where backup pieces reside, which database a backup belongs to, completion times, storage devices, status, and metadata required by RMAN to locate files during `RESTORE` or `RECOVER`.

Information in the repository can diverge from the physical state of files on disk or tape. For example, an administrator might delete a backup file using an OS command without notifying RMAN. The repository continues to mark the file `AVAILABLE`, even though the file is gone. The reverse can also happen: the backup file still exists, but the storage device or media manager is temporarily unreachable.

RMAN provides **LIST**, **REPORT**, and **CROSSCHECK** commands to inspect inventory, evaluate compliance with the retention policy, and synchronize backup statuses with storage devices. After `CROSSCHECK`, a backup that cannot be found may enter the **EXPIRED** state. A backup that still exists physically yet is no longer needed under the retention policy is considered **OBSOLETE**. These are two different concepts leading to two different cleanup commands: `DELETE EXPIRED` and `DELETE OBSOLETE`.

This lesson belongs to the **Backup and Recovery** chapter of Database Engine Relational Oracle. It focuses on reading the RMAN repository, `LIST` and `REPORT` syntax, verifying backups with `CROSSCHECK`, the meaning of `AVAILABLE`/`EXPIRED`/`UNAVAILABLE`, retention policies, identifying `OBSOLETE` backups, and safe cleanup procedures.

After this lesson, you will be able to:

- Explain where the RMAN repository stores metadata and the role of a recovery catalog.
- Use `LIST BACKUP`, `LIST BACKUP SUMMARY`, `LIST BACKUP BY FILE`, and `LIST COPY`.
- List archived redo logs, control files, SPFILE, incarnations, and backups by tag.
- Use `LIST EXPIRED` to view records marked `EXPIRED`.
- Distinguish `LIST` from `REPORT` and `CROSSCHECK`.
- Use `REPORT SCHEMA`, `REPORT NEED BACKUP`, `REPORT UNRECOVERABLE`, and `REPORT OBSOLETE`.
- Understand retention policies using `RECOVERY WINDOW` and `REDUNDANCY`.
- Choose the appropriate `CROSSCHECK BACKUP`, `CROSSCHECK COPY`, and `DEVICE TYPE`.
- Understand `AVAILABLE`, `EXPIRED`, and `UNAVAILABLE` states.
- Know that `CROSSCHECK` only updates the repository and never deletes files or records.
- Distinguish `EXPIRED` from `OBSOLETE`.
- Use `DELETE EXPIRED` to clean up records that are no longer found.
- Use `DELETE OBSOLETE` to delete backups no longer required under the retention policy.
- Check SBT channels, media managers, FRA, Data Guard, and CDB/PDB before maintenance.
- Preview restores and validate backups before relying on them for a recovery plan.

> **Example scope:** Commands and examples are primarily based on Oracle Database 19c RMAN. Run them at the RMAN prompt, connected to the right `TARGET` and recovery catalog if used. `DELETE` commands can remove physical files; execute them only after verifying retention policies, restore capability, and organizational retention requirements.

## 1. What is the RMAN repository?

The RMAN repository is the collection of metadata RMAN uses to track backups, image copies, archived redo logs, and recovery-related objects.

### 1.1. Repository in the control file

RMAN always maintains a repository in the target database's control file. Whenever RMAN creates a backup, the control file records metadata about that backup. This metadata helps RMAN determine:

- Which backup sets and backup pieces were created.
- Which data files, control files, SPFILE, or archived logs are protected.
- When the backup completed.
- Whether the backup resides on `DISK` or an `SBT`/tape device.
- The backup piece handle or file location.
- The status of the backup.
- Whether the backup satisfies recovery requirements.

If the control file is lost, backup metadata can be partially or wholly lost depending on autobackup timing and storage configuration. Therefore, control file autobackup is a critical part of any RMAN strategy.

### 1.2. Recovery catalog

In addition to the control file, a recovery catalog can be configured in a separate database. The catalog stores RMAN metadata inside tables belonging to the catalog schema.

| Storage location | Characteristics |
| --- | --- |
| Target control file | Always present; stores repository for the target database itself |
| Recovery catalog | Optional; centrally stores metadata for one or more target databases |

A recovery catalog is useful when:

- Managing backups for multiple databases.
- Retaining history longer than control file record limits allow.
- Centrally tracking database incarnations and backup history.
- Supporting certain administrative operations and reporting across multiple databases.

`LIST`, `REPORT`, and `CROSSCHECK` can be used with or without a recovery catalog, depending on connection requirements for each command. Having no catalog does not mean RMAN lacks a repository.

### 1.3. The repository is metadata, not the backup itself

A record in the repository does not prove the backup file still exists or is readable. For example:

1. RMAN creates a backup piece at `/backup/db/full_01.bkp`.
2. The control file records the backup as `AVAILABLE`.
3. An administrator deletes the file using an OS command.
4. The repository still holds an `AVAILABLE` record because RMAN was not notified.
5. `CROSSCHECK` checks the device, fails to find the file, and updates the record to `EXPIRED`.

This is why `CROSSCHECK` must be run periodically, especially when backups are moved, deleted, or managed by tools outside RMAN.

## 2. Four concepts to keep distinct

| Command/concept | Question answered | Does it delete files? |
| --- | --- | --- |
| LIST | Which backups/objects does RMAN currently record? | No |
| REPORT | Do current backups satisfy recovery policies? | No |
| CROSSCHECK | Are files recorded in the repository still found on the device? | No |
| DELETE EXPIRED / DELETE OBSOLETE | Which records or backups should be cleaned up under defined rules? | `DELETE OBSOLETE` deletes physical files; `DELETE EXPIRED` mainly cleans `EXPIRED` records |

You can visualize the workflow as:

~~~text
LIST
  |
  v
Inspect what the RMAN repository currently records
  |
  v
CROSSCHECK
  |
  v
Reconcile repository against DISK / SBT
  |
  +------ Not found ------------> EXPIRED
  |
  +------ Found ----------------> AVAILABLE
  |
  v
REPORT OBSOLETE
  |
  v
Evaluate against retention policy
  |
  +------ No longer needed -----> OBSOLETE
  |
  v
Review results and recoverability
  |
  v
DELETE EXPIRED or DELETE OBSOLETE
~~~

`LIST`, `REPORT`, and `CROSSCHECK` are inspection/evaluation operations. `DELETE` is a maintenance step that alters files or metadata.

## 3. LIST: viewing backups in the repository

`LIST` displays backups and related objects recorded by RMAN.

### 3.1. Listing all backups

At the RMAN prompt:

~~~text
RMAN> LIST BACKUP;
~~~

`LIST BACKUP` displays details of backup sets, backup pieces, and proxy copies within the default scope. Output typically includes:

- Backup set key.
- Backup type.
- Backup level.
- Status.
- Device type.
- Completion time.
- Size and elapsed time.
- Backup piece handle.
- Tag.
- Data files or archived logs included in the backup set.

This command is suitable when you need detailed backup inventory information.

### 3.2. Backup summary

~~~text
RMAN> LIST BACKUP SUMMARY;
~~~

`SUMMARY` shows one line per backup, suitable for quick checks:

| Common column | Meaning |
| --- | --- |
| Key | Identifier key of the backup set in the repository |
| TY | Backup type, e.g., backup set or proxy copy |
| LV | Backup level |
| S | Status |
| Device Type | `DISK` or `SBT_TAPE` |
| Completion Time | Time of completion |
| #Pieces | Number of backup pieces |
| #Copies | Number of copies |
| Compressed | Whether the backup was compressed by RMAN |
| Tag | Tag attached to the backup |

In `LIST BACKUP SUMMARY` output, common status codes are:

- `A`: `AVAILABLE`.
- `U`: `UNAVAILABLE`.
- `X`: backup pieces in the backup set are `EXPIRED`.

`SUMMARY` helps spot abnormal backup statuses quickly, but does not replace viewing piece handles or verifying restore capability.

### 3.3. Listing by individual data file

~~~text
RMAN> LIST BACKUP BY FILE;
~~~

`BY FILE` groups backups by individual data file, archived redo log, control file, and SPFILE. This view is helpful to confirm:

- Which data files have been backed up.
- Which files lack a recent backup.
- Which backup sets contain a specific data file.
- Which archived log sequences have backups.
- Backup status per file.

### 3.4. Listing database backups

~~~text
RMAN> LIST BACKUP OF DATABASE;
~~~

This command restricts output to backups of database data files.

### 3.5. Listing control file backups

~~~text
RMAN> LIST BACKUP OF CONTROLFILE;
~~~

Control file backups are vital when restoring the repository or mounting the database after losing the current control file.

### 3.6. Listing SPFILE backups

~~~text
RMAN> LIST BACKUP OF SPFILE;
~~~

The SPFILE holds instance startup parameters. If the SPFILE is lost, an SPFILE backup restores database configuration.

### 3.7. Listing archived redo log backups

~~~text
RMAN> LIST BACKUP OF ARCHIVELOG ALL;
~~~

This command shows backup sets containing archived redo logs. When checking point-in-time recovery readiness, identify both data file backups and the chain of archived logs usable to recover to the desired time.

### 3.8. Listing archived redo logs

~~~text
RMAN> LIST ARCHIVELOG ALL;
~~~

`LIST ARCHIVELOG ALL` displays archived logs known to the repository, not just backup sets containing archived logs. You can inspect sequence, thread, timestamps, status, and locations.

### 3.9. Listing image copies

~~~text
RMAN> LIST COPY;
~~~

`LIST COPY` displays file copies, including data file copies and archived log copies. An image copy is a file-level copy, distinct from a backup set containing RMAN-formatted backup pieces.

You can narrow the scope:

~~~text
RMAN> LIST COPY OF DATABASE;
RMAN> LIST COPY OF DATAFILE 1;
RMAN> LIST COPY OF ARCHIVELOG ALL;
~~~

### 3.10. Listing by tag

~~~text
RMAN> LIST BACKUP TAG 'WEEKLY_FULL';
~~~

Tags help identify backup groups by schedule or purpose. A tag is not a retention policy and does not determine whether a backup is obsolete.

### 3.11. Listing backups by time

~~~text
RMAN> LIST BACKUP COMPLETED AFTER 'SYSDATE-7';
~~~

This example filters backups completed within the last seven days. Supported time expressions can be combined to find backups within a specific range.

### 3.12. Listing EXPIRED records

~~~text
RMAN> LIST EXPIRED BACKUP;
~~~

Or:

~~~text
RMAN> LIST EXPIRED COPY;
~~~

`LIST EXPIRED` shows only repository records currently in the `EXPIRED` state. If `CROSSCHECK` has not been run recently, results may not reflect the latest physical file state on devices.

### 3.13. Listing database incarnations

~~~text
RMAN> LIST INCARNATION;
~~~

Incarnations change when the database executes `OPEN RESETLOGS`. When recovering to a prior incarnation or working with backups from an earlier database branch, incarnation information identifies the right recovery history.

### 3.14. LIST FAILURE in Oracle 19c

In earlier releases, RMAN included `LIST FAILURE` as part of Data Recovery Advisor. However, Oracle Database 19c deprecated Data Recovery Advisor, and `LIST FAILURE`, `ADVISE FAILURE`, `REPAIR FAILURE`, and `CHANGE FAILURE` are no longer offered as the standard workflow. Do not confuse `LIST FAILURE` with `LIST BACKUP` or `LIST EXPIRED`.

## 4. REPORT: evaluating backup status and recoverability

`REPORT` answers questions about database protection coverage and which backups must be created or can be cleaned up under the retention policy.

Common `REPORT` commands:

- `REPORT SCHEMA`.
- `REPORT NEED BACKUP`.
- `REPORT UNRECOVERABLE`.
- `REPORT OBSOLETE`.

### 4.1. REPORT SCHEMA

~~~text
RMAN> REPORT SCHEMA;
~~~

`REPORT SCHEMA` lists tablespaces and data files belonging to the database at the requested point. Output typically shows:

- File number.
- Tablespace name.
- Data file name.
- Size.
- Online/offline status per metadata.

This command is useful when:

- Checking which data files exist in the database.
- Cross-referencing file numbers and tablespaces.
- Preparing for restore/recover.
- Identifying newly added files that do not yet have backups.

In Data Guard, `FOR DB_UNIQUE_NAME` can report the schema of a specific database in the environment.

### 4.2. REPORT NEED BACKUP

~~~text
RMAN> REPORT NEED BACKUP;
~~~

This command reports data files that need additional backups to satisfy the current retention policy.

Example checking a single data file:

~~~text
RMAN> REPORT NEED BACKUP DATAFILE 1;
~~~

Or checking a tablespace:

~~~text
RMAN> REPORT NEED BACKUP TABLESPACE USERS;
~~~

You can specify criteria:

~~~text
RMAN> REPORT NEED BACKUP RECOVERY WINDOW OF 7 DAYS;
RMAN> REPORT NEED BACKUP REDUNDANCY 2;
RMAN> REPORT NEED BACKUP DAYS 3;
RMAN> REPORT NEED BACKUP INCREMENTAL 2;
~~~

Meanings:

| Condition | Purpose |
| --- | --- |
| `RECOVERY WINDOW OF n DAYS` | Identifies files needing backup to satisfy the recovery window |
| `REDUNDANCY n` | Identifies files lacking the required number of backups under redundancy |
| `DAYS n` | Identifies files needing more than `n` days of archived redo logs to recover |
| `INCREMENTAL n` | Identifies files requiring more than `n` incremental backups to apply |

If the retention policy is set to `NONE`, `REPORT NEED BACKUP` cannot determine which files need backup under policy and will return an error.

### 4.3. REPORT UNRECOVERABLE

~~~text
RMAN> REPORT UNRECOVERABLE;
~~~

This command finds data files affected by `NOLOGGING` or unrecoverable operations since the most recent applicable backup.

Examples:

- Direct-path `INSERT` with `NOLOGGING`.
- Certain data loading operations that do not generate full redo.

Because `NOLOGGING` operations do not log the redo needed to reconstruct changed blocks, archived redo logs alone cannot recover those blocks. Take a suitable full or incremental backup after such operations to protect the data.

`REPORT UNRECOVERABLE` helps DBAs identify files needing re-backup.

### 4.4. REPORT OBSOLETE

~~~text
RMAN> REPORT OBSOLETE;
~~~

This command reports backups and copies no longer required to satisfy the current retention policy.

Example:

~~~text
RMAN> REPORT OBSOLETE;
RMAN retention policy will be applied to the command
RMAN retention policy is set to redundancy 1
Report of obsolete backups and copies
...
~~~

`REPORT OBSOLETE` does not delete files. It only shows which backups RMAN considers obsolete under the policy.

You can evaluate against another policy without changing the default configuration:

~~~text
RMAN> REPORT OBSOLETE RECOVERY WINDOW OF 7 DAYS;
RMAN> REPORT OBSOLETE REDUNDANCY 2;
~~~

This lets you preview the impact of a different retention policy before deciding to change configuration or run `DELETE OBSOLETE`.

### 4.5. How REPORT differs from LIST

| LIST | REPORT |
| --- | --- |
| Lists objects and metadata in the repository | Evaluates backup status against policy or schema |
| Displays backup sets, pieces, copies, archived logs | Displays files needing backup, unrecoverable files, obsolete backups |
| Useful for finding keys/handles/tags | Useful for making backup/retention decisions |
| Does not conclude whether a file meets a recovery window | Evaluates recoverability conditions against policy |

## 5. CROSSCHECK: reconciling the repository with storage devices

`CROSSCHECK` checks whether backups/copies recorded by RMAN are still found on their respective storage devices.

### 5.1. Purpose

The repository can drift out of sync with physical reality:

- Backup files deleted via OS commands.
- Disk mount unmounted or unreachable.
- Tapes moved to an offsite vault.
- Media manager catalog missing a backup piece.
- Backup storage relocated.
- Temporary media manager or channel configuration failure.

`CROSSCHECK` updates record statuses so RMAN knows which backups are currently accessible.

### 5.2. CROSSCHECK BACKUP

~~~text
RMAN> CROSSCHECK BACKUP;
~~~

Checks backup sets, proxy copies, and image copies recorded in the repository, according to object scope and configured device channels.

### 5.3. CROSSCHECK BACKUP DEVICE TYPE DISK

~~~text
RMAN> CROSSCHECK BACKUP DEVICE TYPE DISK;
~~~

Checks only backups residing on `DISK` devices.

### 5.4. CROSSCHECK BACKUP DEVICE TYPE SBT

~~~text
RMAN> CROSSCHECK BACKUP DEVICE TYPE SBT;
~~~

`SBT` typically represents a media manager/tape library or backup appliance integrated via the SBT interface. RMAN requires proper channel and media manager configuration to query the device catalog.

If automatic SBT channels are not configured, you may need to allocate a maintenance channel:

~~~text
RMAN> ALLOCATE CHANNEL FOR MAINTENANCE DEVICE TYPE SBT;
RMAN> CROSSCHECK BACKUP;
RMAN> RELEASE CHANNEL;
~~~

In practice, syntax and channel allocation must match your deployed media manager. Never crosscheck tape using an incorrect SBT configuration and then delete records marked `EXPIRED`.

### 5.5. CROSSCHECK COPY

~~~text
RMAN> CROSSCHECK COPY;
~~~

Checks image copies and file copies recorded in the repository.

### 5.6. CROSSCHECK by object type

~~~text
RMAN> CROSSCHECK COPY OF DATABASE;
RMAN> CROSSCHECK BACKUP OF DATABASE;
RMAN> CROSSCHECK BACKUP OF ARCHIVELOG ALL;
RMAN> CROSSCHECK BACKUP OF DATAFILE 1;
~~~

You can narrow the scope to verify a specific backup group prior to maintenance.

### 5.7. CROSSCHECK by backup set or tag

~~~text
RMAN> CROSSCHECK BACKUPSET 1338, 1339, 1340;
RMAN> CROSSCHECK BACKUPPIECE TAG 'NIGHTLY_BACKUP';
~~~

Use `LIST` to obtain exact keys, tags, or handles before running a targeted crosscheck.

## 6. What does CROSSCHECK do and not do?

### 6.1. If the file is found

If `CROSSCHECK` locates the backup file or the media manager confirms the backup exists in its catalog, the repository updates the status to `AVAILABLE`.

For example, a backup previously marked `EXPIRED` due to temporarily unreachable storage returns to `AVAILABLE` once storage recovers and `CROSSCHECK` finds the file.

### 6.2. If the file is not found

If `CROSSCHECK` cannot find the file or the media manager reports the backup missing, the repository record is updated to `EXPIRED`.

### 6.3. CROSSCHECK does not delete physical files

`CROSSCHECK` neither deletes files on disk/tape nor deletes records from the repository. It only synchronizes status.

To delete `EXPIRED` records, use `DELETE EXPIRED`. To delete existing backups no longer needed under the retention policy, use `DELETE OBSOLETE`.

### 6.4. CROSSCHECK only inspects recorded objects

`CROSSCHECK` does not scan directories or tape libraries for arbitrary uncataloged backup files. It checks only objects RMAN already knows about in the repository.

If backups were manually copied to storage without being cataloged, use `CATALOG` to register them before RMAN can manage them via the repository.

### 6.5. CROSSCHECK is not VALIDATE

`CROSSCHECK` checks file availability/metadata on the device. It does not read the entire backup to verify every block is free of corruption.

To verify physical integrity, use:

~~~text
RMAN> VALIDATE BACKUPSET 123;
~~~

Or:

~~~text
RMAN> BACKUP VALIDATE DATABASE;
~~~

To confirm backups can be used for a restore, run `RESTORE ... VALIDATE` or `RESTORE ... PREVIEW` for your target.

## 7. AVAILABLE, EXPIRED, and UNAVAILABLE states

These are the availability states in the RMAN repository.

### 7.1. AVAILABLE

`AVAILABLE` means the RMAN repository considers the backup accessible for `RESTORE`/`RECOVER` in its current state.

It is not proof that:

- Every block in the backup is readable.
- Media is free of corruption.
- Sufficient archived logs exist to recover to any point in time.
- The backup satisfies every business requirement.

For deeper verification, use `VALIDATE` and restore testing.

### 7.2. EXPIRED

`EXPIRED` means `CROSSCHECK` could not locate the file or the media manager could not confirm the backup.

`EXPIRED` is a repository status. It neither deletes the file nor proves the file is corrupted. A backup can be marked `EXPIRED` because:

- Storage is temporarily offline.
- An NFS mount is detached.
- Tape is not mounted or the media manager is unreachable.
- SBT channel `PARMS` are wrong.
- Credentials or media manager settings are incorrect.
- The file was genuinely deleted.

Before deleting `EXPIRED` records, verify why the file was not found.

### 7.3. UNAVAILABLE

`UNAVAILABLE` is a status explicitly set by the DBA to tell RMAN a backup is temporarily unusable or moved outside current reach.

Examples:

- The backup was shipped to an offsite vault.
- A disk volume is undergoing maintenance.
- Tape is stored in an archive vault and not currently mountable.

Mark as `UNAVAILABLE`:

~~~text
RMAN> CHANGE BACKUPSET 12 UNAVAILABLE;
~~~

When the backup returns:

~~~text
RMAN> CHANGE BACKUPSET 12 AVAILABLE;
~~~

RMAN does not use `UNAVAILABLE` files for `RESTORE` or `RECOVER`. Files in the Fast Recovery Area cannot be marked `UNAVAILABLE` via this mechanism.

### 7.4. Comparing statuses

| Status | Meaning | Action |
| --- | --- | --- |
| `AVAILABLE` | Repository considers backup usable | Eligible for restore; validate when needed |
| `EXPIRED` | `CROSSCHECK` could not find backup | Inspect storage/channel; re-crosscheck or `DELETE EXPIRED` record |
| `UNAVAILABLE` | DBA intentionally marked temporarily unusable | When backup returns, run `CHANGE ... AVAILABLE` |

### 7.5. Availability status differs from OBSOLETE

`AVAILABLE`/`EXPIRED`/`UNAVAILABLE` describe accessibility or file presence in the repository.

`OBSOLETE` describes retention need under the retention policy. A backup can be:

- `AVAILABLE` and `OBSOLETE`.
- `AVAILABLE` and not `OBSOLETE`.
- `EXPIRED` with its record still present.
- `UNAVAILABLE` even though the physical file safely resides offsite.

Therefore, you cannot infer `OBSOLETE` solely from `AVAILABLE` or `EXPIRED`.

## 8. EXPIRED: handling and cleaning up records

### 8.1. Finding EXPIRED records

~~~text
RMAN> LIST EXPIRED BACKUP;
RMAN> LIST EXPIRED COPY;
~~~

You can also query RMAN repository views:

~~~sql
SELECT
    recid,
    stamp,
    status,
    device_type,
    handle
FROM v$backup_piece
WHERE status = 'X'
ORDER BY completion_time DESC;
~~~

`V$BACKUP_PIECE` contains backup piece metadata; status codes in the view use internal characters such as `A`, `X`, and `D`. Check the release reference before writing automation based on status codes.

Another view in Oracle 19c:

~~~sql
SELECT
    file#,
    status,
    device_type,
    filename
FROM v$backup_files
WHERE status = 'EXPIRED';
~~~

Column names and returned rows vary by record type; check the `V$BACKUP_FILES` reference before using it in administrative scripts.

### 8.2. Why not delete EXPIRED immediately?

A record can be marked `EXPIRED` due to a transient fault. Example:

1. An NFS backup mount loses connectivity.
2. The DBA runs `CROSSCHECK`.
3. RMAN cannot access files and marks them `EXPIRED`.
4. The NFS mount is restored.
5. Physical backup files still exist intact.

If records are deleted immediately, RMAN loses the metadata needed to use those files via the old records. Restore storage connectivity and re-run `CROSSCHECK` first.

### 8.3. Re-running CROSSCHECK after fixing storage

~~~text
RMAN> CROSSCHECK BACKUP DEVICE TYPE DISK;
RMAN> LIST EXPIRED BACKUP;
~~~

If files are found again, their status returns to `AVAILABLE`. If still missing, verify handles, mounts, permissions, and backup destination configuration.

### 8.4. DELETE EXPIRED

After confirming backups are genuinely gone and records should be purged:

~~~text
RMAN> DELETE EXPIRED BACKUP;
~~~

Or clean only expired copies:

~~~text
RMAN> DELETE EXPIRED COPY;
~~~

`DELETE EXPIRED` removes `EXPIRED` records from the repository. If a file marked `EXPIRED` actually still exists physically, RMAN issues a warning and does not delete that physical file.

### 8.5. DELETE EXPIRED is not a tool to delete existing files

Never run `DELETE EXPIRED` expecting to free disk space occupied by existing backup files. If files exist and should be removed under the retention policy, evaluate with `REPORT OBSOLETE` and use `DELETE OBSOLETE` when appropriate.

## 9. OBSOLETE: backups no longer needed by retention policy

`OBSOLETE` is the outcome of evaluating backups against the configured retention policy or one specified in `REPORT`/`DELETE`.

### 9.1. Example of an existing backup that is obsolete

Suppose:

- Retention policy is `REDUNDANCY 1`.
- Three successful full backups exist.
- The oldest backup is no longer needed to keep one backup meeting the policy.
- The old file still exists on disk.

The older backup is evaluated as `OBSOLETE` even though the physical file is intact and the repository still lists it `AVAILABLE`.

### 9.2. OBSOLETE does not mean faulty

An `OBSOLETE` backup may still be completely readable and restorable. It is simply no longer required to satisfy the current retention policy.

### 9.3. REPORT OBSOLETE

~~~text
RMAN> REPORT OBSOLETE;
~~~

This command shows which backup sets, backup pieces, data file copies, and archived logs are considered obsolete under the policy.

### 9.4. DELETE OBSOLETE

~~~text
RMAN> DELETE OBSOLETE;
~~~

`DELETE OBSOLETE` deletes physical backups from disk or requests the media manager to delete backups on SBT, while updating the repository:

- Backup files are deleted from media.
- Corresponding records are marked `DELETED` in the control file.
- Records in the recovery catalog are updated/removed accordingly.

`DELETE OBSOLETE` is destructive. Run `REPORT OBSOLETE` first, inspect the output, and confirm the policy is accurate.

## 10. Retention policy: basis for determining OBSOLETE

The RMAN retention policy defines which backups must be retained to satisfy recovery requirements.

There are two main modes:

- `REDUNDANCY`.
- `RECOVERY WINDOW`.

You can also set `NONE` to disable the retention policy.

### 10.1. REDUNDANCY

`REDUNDANCY` specifies how many backups of each data file must be retained.

Example:

~~~text
RMAN> CONFIGURE RETENTION POLICY TO REDUNDANCY 2;
~~~

RMAN retains at least two eligible backups for each data file per retention rules. Older backups become obsolete once no longer needed to maintain redundancy.

Oracle's documented default retention policy is `REDUNDANCY 1`, though the active configuration may have been changed by a DBA.

### 10.2. RECOVERY WINDOW

`RECOVERY WINDOW` specifies how far back in time the database must be recoverable.

Example:

~~~text
RMAN> CONFIGURE RETENTION POLICY TO RECOVERY WINDOW OF 7 DAYS;
~~~

This means sufficient backups and archived redo logs must be retained to recover to any point within a seven-day recovery window, subject to RMAN recovery rules.

Do not misinterpret `RECOVERY WINDOW OF 7 DAYS` as keeping only backups created in the last seven days. To recover to the start of the window, RMAN may have to retain a full backup taken before that window along with the required archived redo log chain.

### 10.3. Comparing REDUNDANCY and RECOVERY WINDOW

| Policy | Configured by | Core question |
| --- | --- | --- |
| `REDUNDANCY 2` | Number of backups | How many backup copies must be kept? |
| `RECOVERY WINDOW OF 7 DAYS` | Recovery time span | How far back in time must recovery be possible? |

`REDUNDANCY` fits when requirements are defined by copy count. `RECOVERY WINDOW` fits when business requirements specify a rollback timeframe.

### 10.4. NONE

~~~text
RMAN> CONFIGURE RETENTION POLICY TO NONE;
~~~

`NONE` disables the retention policy. With no retention policy, RMAN cannot evaluate which backups are obsolete under a default policy. `REPORT OBSOLETE` fails when there is no policy to evaluate against.

Never set `NONE` just to suppress obsolete reporting. An approved alternative retention process must be established by the DBA and business owner.

### 10.5. Checking the current policy

~~~text
RMAN> SHOW RETENTION POLICY;
~~~

Or:

~~~text
RMAN> SHOW ALL;
~~~

`SHOW ALL` displays other critical RMAN settings such as device types, control file autobackup, channels, backup optimization, and archived log deletion policy.

### 10.6. Testing a different policy in REPORT

~~~text
RMAN> REPORT OBSOLETE REDUNDANCY 2;
RMAN> REPORT OBSOLETE RECOVERY WINDOW OF 14 DAYS;
~~~

These clauses override only how `REPORT` evaluates that single command. They do not permanently change the configured retention policy.

### 10.7. Caution with policy overrides in DELETE

Suppose the configured policy is:

~~~text
CONFIGURE RETENTION POLICY TO RECOVERY WINDOW OF 14 DAYS;
~~~

If you run:

~~~text
RMAN> DELETE OBSOLETE RECOVERY WINDOW OF 7 DAYS;
~~~

RMAN may delete backups according to a seven-day recovery window, eliminating recoverability between seven and fourteen days back. This override has real impact on recoverability—it is not merely a reporting option.

## 11. Why run CROSSCHECK before REPORT OBSOLETE?

Oracle recommends crosschecking so the repository accurately reflects physical backup state before evaluating and purging obsolete backups.

If the repository still marks a file `AVAILABLE` after it was deleted outside RMAN:

- `LIST` may display the file as if it still exists.
- `REPORT OBSOLETE` may evaluate against stale metadata.
- `DELETE` may encounter mismatches between the repository and physical media.

Standard workflow:

~~~text
RMAN> CROSSCHECK BACKUP;
RMAN> CROSSCHECK COPY;
RMAN> LIST EXPIRED BACKUP;
RMAN> REPORT OBSOLETE;
~~~

Only after reviewing should you decide:

~~~text
RMAN> DELETE EXPIRED BACKUP;
RMAN> DELETE EXPIRED COPY;
RMAN> DELETE OBSOLETE;
~~~

Not every command is needed in every maintenance run. Choose the scope suited to your devices and retention policy.

## 12. How do DELETE EXPIRED and DELETE OBSOLETE differ?

| Criterion | DELETE EXPIRED | DELETE OBSOLETE |
| --- | --- | --- |
| Condition | Record is in `EXPIRED` status | Backup no longer needed under retention policy |
| Status source | `CROSSCHECK` | Retention policy |
| Physical file | If file still exists physically, RMAN warns and does not delete it | Deletes backup file from media on success |
| Repository | Removes `EXPIRED` record | Updates record to `DELETED` and syncs catalog |
| Goal | Clean metadata for unlocatable backups | Reclaim storage from unneeded backups |
| Might backup still exist? | Yes, if crosscheck was wrong or storage had transient error | Yes, usually intact files no longer needed per policy |

### 12.1. DELETE EXPIRED BACKUP

~~~text
RMAN> DELETE EXPIRED BACKUP;
~~~

Cleans `EXPIRED` records. If a file physically exists on media, RMAN warns of the mismatch and leaves the physical file intact.

### 12.2. DELETE OBSOLETE

~~~text
RMAN> DELETE OBSOLETE;
~~~

Deletes backups no longer required under the retention policy. For tape/SBT backups, RMAN instructs the media manager to handle deletion.

### 12.3. NOPROMPT

~~~text
RMAN> DELETE NOPROMPT OBSOLETE;
~~~

`NOPROMPT` skips listing items and asking for interactive confirmation. It does not make the command safer; it simply bypasses the prompt. In command files or schedulers, RMAN does not prompt interactively, so review scripts and policies thoroughly beforehand.

### 12.4. FORCE

~~~text
RMAN> DELETE FORCE EXPIRED BACKUP;
~~~

`FORCE` bypasses certain checks and removes metadata regardless of media state; for `DELETE` generally, `FORCE` can override I/O errors and archived log deletion policies. Never use `FORCE` as a default error-fixing tool. Only use it with approval when you know the exact record/file to purge.

## 13. CROSSCHECK with DISK and SBT

Different storage devices are checked differently.

### 13.1. DISK

For disk backups, RMAN checks the file at the path recorded in the repository and can verify backup file headers.

Example:

~~~text
RMAN> CROSSCHECK BACKUP DEVICE TYPE DISK;
~~~

If backups reside on NFS or ASM-related storage, ensure mounts and permissions are intact when crosschecking.

### 13.2. SBT/TAPE

For SBT, RMAN interacts with media management software to confirm backups exist in the media catalog.

Example:

~~~text
RMAN> CROSSCHECK BACKUP DEVICE TYPE SBT;
~~~

If the media manager is unreachable or channel `PARMS` are wrong, backups may be marked `EXPIRED` even though the tapes still hold the data.

### 13.3. Channel must match the backup's device type

RMAN uses a channel matching the backup's device type. If backups were created on SBT but only disk channels are configured, allocate/configure an SBT maintenance channel.

### 13.4. Never purge EXPIRED tape records during a media manager outage

If many tape backups suddenly turn `EXPIRED`:

1. Halt automated `DELETE EXPIRED` jobs.
2. Check the media manager service.
3. Check the SBT library and credentials.
4. Check channel `PARMS`.
5. Confirm the tape catalog is reachable.
6. Re-run `CROSSCHECK`.
7. Purge records only after verifying backups truly no longer exist.

This is a common pitfall that destroys metadata required to locate tape backups.

## 14. Data Guard and DB_UNIQUE_NAME

In Data Guard, every backup is associated with the database that created it. Primary and standby databases share the same DBID but have different `DB_UNIQUE_NAME` values.

### 14.1. LIST by database unique name

~~~text
RMAN> LIST BACKUP FOR DB_UNIQUE_NAME 'STANDBY1';
~~~

Or:

~~~text
RMAN> LIST ARCHIVELOG ALL FOR DB_UNIQUE_NAME 'STANDBY1';
~~~

### 14.2. Crosscheck in Data Guard

In Data Guard, RMAN can only transition a file's status from `AVAILABLE` to `EXPIRED` when connected as `TARGET` to the database associated with that file. If a file belongs to another database in the Data Guard environment, RMAN may require running `CROSSCHECK` while connected to that target.

### 14.3. Disk and tape accessibility

RMAN enforces accessibility rules:

- Tape backups can be considered accessible across databases in the same Data Guard environment depending on media manager setup.
- Disk backups are generally accessible only to the database that created them.

Never assume every backup on the primary can be crosschecked or directly restored by a standby.

### 14.4. Verify before DELETE

If a backup was taken on a standby or another primary, check `DB_UNIQUE_NAME` and storage location before running `DELETE`. Deleting the wrong backup can jeopardize another database's recovery plan.

## 15. CDB/PDB and backup metadata

In Oracle Multitenant, RMAN manages backups at both CDB and PDB scopes.

### 15.1. Connecting to the CDB root

To report CDB-wide backup information, connect to the root as a common user with `SYSDBA` or `SYSBACKUP` privileges:

~~~text
RMAN> CONNECT TARGET /;
RMAN> LIST BACKUP SUMMARY;
RMAN> REPORT NEED BACKUP;
~~~

`LIST BACKUP` from the root displays backups for the entire CDB.

### 15.2. Reporting obsolete PDB backups

In Oracle 19c, reporting/deleting obsolete backups when connected directly to a PDB has restrictions. For PDB obsolete backup management, check release documentation and run supported commands from the root.

### 15.3. Do not confuse PDB name with DB_UNIQUE_NAME

A PDB is a pluggable database inside a CDB. `DB_UNIQUE_NAME` identifies a database in Data Guard or a recovery catalog. These are two different scopes.

## 16. Fast Recovery Area and maintenance

The Fast Recovery Area (FRA) is an Oracle-managed storage area for backup and recovery files, such as:

- Archived redo logs.
- RMAN backups.
- Control file autobackups.
- Flashback logs.
- Certain other recovery files.

### 16.1. Checking the FRA

~~~sql
SELECT
    name,
    space_limit,
    space_used,
    space_reclaimable,
    number_of_files
FROM v$recovery_file_dest;
~~~

### 16.2. Checking usage by file type

~~~sql
SELECT
    file_type,
    percent_space_used,
    percent_space_reclaimable,
    number_of_files
FROM v$recovery_area_usage
ORDER BY percent_space_used DESC;
~~~

### 16.3. The FRA auto-manages eligible files

When configured, Oracle can automatically delete eligible files from the FRA when space is needed. However, the database will not violate the retention policy merely to free quota. If the FRA fills up, check:

- Which backups are obsolete.
- Which archived logs are eligible for deletion under the archived log deletion policy.
- Flashback logs and guaranteed restore points.
- FRA space limit and physical storage capacity.
- Files deleted outside RMAN causing stale repository records.

### 16.4. Deleting files via the OS makes the repository stale

If OS commands delete files in the FRA or backup directories, Oracle does not immediately update all RMAN repository records. `CROSSCHECK` detects missing files and `DELETE EXPIRED` cleans their records.

### 16.5. Never delete archived logs solely because they were backed up once

The archived log deletion policy may require backups on specific devices or standby application in Data Guard. Check:

~~~text
RMAN> SHOW ARCHIVELOG DELETION POLICY;
~~~

`DELETE ARCHIVELOG` and `BACKUP ... DELETE INPUT` enforce this policy when set to something other than `NONE`, unless `FORCE` is used. Never run `DELETE ARCHIVELOG ALL` to relieve a full FRA without checking standbys and recovery requirements.

## 17. Previewing restore before cleaning up backups

`LIST` and `REPORT` show metadata and retention status. Before deleting important backups, verify that RMAN can still select backups for a restore.

### 17.1. RESTORE DATABASE PREVIEW

~~~text
RMAN> RESTORE DATABASE PREVIEW;
~~~

`PREVIEW` queries the repository and lists the backups RMAN would use for restore/recovery right now. It does not read the entire backup files.

### 17.2. PREVIEW SUMMARY

~~~text
RMAN> RESTORE DATABASE PREVIEW SUMMARY;
~~~

`SUMMARY` gives a more compact output of selected backups.

### 17.3. RESTORE VALIDATE

~~~text
RMAN> RESTORE DATABASE VALIDATE;
~~~

`VALIDATE` verifies backups RMAN would use by reading backup blocks and detecting unreadable files or blocks.

### 17.4. VALIDATE BACKUPSET

~~~text
RMAN> VALIDATE BACKUPSET 123;
~~~

Use this when validating a specific backup set.

### 17.5. PREVIEW is not the same as VALIDATE

| Command | Reads backup files? | Goal |
| --- | --- | --- |
| `RESTORE ... PREVIEW` | Does not read backup contents | See which backups RMAN plans to select |
| `RESTORE ... VALIDATE` | Reads/checks backup data per validation | Verify backups are physically readable |
| `VALIDATE BACKUPSET` | Yes | Verify a specific backup set |

`PREVIEW` is useful before `DELETE OBSOLETE` to ensure remaining backups support restore. However, `PREVIEW` only reflects existing metadata; for stronger assurance, run `VALIDATE` and periodic restore tests.

## 18. Safe maintenance procedure

A practical workflow includes these steps:

### Step 1 — Identify the right database

Connect to the right `TARGET`, DBID, `DB_UNIQUE_NAME`, and recovery catalog if used. In RAC/Data Guard, confirm which instance/database owns the backups.

### Step 2 — Inspect RMAN configuration

~~~text
RMAN> SHOW ALL;
RMAN> SHOW RETENTION POLICY;
RMAN> SHOW ARCHIVELOG DELETION POLICY;
~~~

### Step 3 — Inspect backup inventory

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> LIST BACKUP;
RMAN> LIST COPY;
RMAN> LIST ARCHIVELOG ALL;
~~~

### Step 4 — CROSSCHECK the right devices

~~~text
RMAN> CROSSCHECK BACKUP DEVICE TYPE DISK;
RMAN> CROSSCHECK COPY;
~~~

If SBT exists:

~~~text
RMAN> CROSSCHECK BACKUP DEVICE TYPE SBT;
~~~

### Step 5 — Check EXPIRED items

~~~text
RMAN> LIST EXPIRED BACKUP;
RMAN> LIST EXPIRED COPY;
~~~

Investigate missing files before deleting records.

### Step 6 — Report needed backups

~~~text
RMAN> REPORT NEED BACKUP;
RMAN> REPORT UNRECOVERABLE;
RMAN> REPORT OBSOLETE;
~~~

### Step 7 — Verify restore capability

~~~text
RMAN> RESTORE DATABASE PREVIEW SUMMARY;
~~~

For critical databases, run `RESTORE ... VALIDATE` or perform a restore test in a recovery environment.

### Step 8 — Clean EXPIRED records

Only after confirming files are genuinely gone:

~~~text
RMAN> DELETE EXPIRED BACKUP;
RMAN> DELETE EXPIRED COPY;
~~~

### Step 9 — Clean OBSOLETE backups

Only when the retention policy is verified and remaining backups meet recovery requirements:

~~~text
RMAN> DELETE OBSOLETE;
~~~

### Step 10 — Verify after maintenance

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> LIST EXPIRED BACKUP;
RMAN> REPORT OBSOLETE;
RMAN> RESTORE DATABASE PREVIEW SUMMARY;
~~~

Record the number of deleted backups, space freed, any remaining `EXPIRED` records, and preview results.

## 19. Scheduling maintenance

Maintenance can be scheduled periodically, but inspection must remain separated from deletion.

### 19.1. Daily inspection tasks

- `LIST BACKUP SUMMARY`.
- `CROSSCHECK BACKUP DEVICE TYPE DISK`.
- `CROSSCHECK BACKUP DEVICE TYPE SBT` if applicable.
- Check `LIST EXPIRED BACKUP`.
- Check FRA usage.
- Check backup job statuses.

### 19.2. Weekly tasks

- `REPORT OBSOLETE`.
- `REPORT NEED BACKUP`.
- `REPORT UNRECOVERABLE`.
- Check restore preview.
- Review expired records and storage errors.
- Delete obsolete backups only after policy verification and appropriate approval.

### 19.3. Automation

A maintenance RMAN script might look like:

~~~text
RUN {
    CROSSCHECK BACKUP DEVICE TYPE DISK;
    CROSSCHECK COPY;
    LIST EXPIRED BACKUP;
    REPORT OBSOLETE;
}
~~~

This is an inspection script; it deletes no backups. When automating `DELETE`, log output, verify policy, review scope, and configure alerts if obsolete/expired counts spike abnormally.

### 19.4. Never use NOPROMPT to mask risk

`NOPROMPT` is handy for schedulers, but removes confirmation prompts. Before automating `DELETE OBSOLETE`, verify:

- The retention policy is approved.
- The archived log deletion policy is checked.
- Offsite/tape copies are checked.
- Guaranteed restore points and flashback requirements are checked.
- The business recovery window is verified.
- Logging and alerting run after every execution.

## 20. Useful repository queries for inspection

Beyond RMAN `LIST`/`REPORT`, you can inspect the repository via dynamic performance views and recovery catalog views.

### 20.1. V$BACKUP_SET

~~~sql
SELECT
    recid,
    stamp,
    set_stamp,
    set_count,
    backup_type,
    incremental_level,
    pieces,
    start_time,
    completion_time
FROM v$backup_set
ORDER BY completion_time DESC;
~~~

### 20.2. V$BACKUP_PIECE

~~~sql
SELECT
    recid,
    stamp,
    set_stamp,
    set_count,
    piece#,
    status,
    device_type,
    handle,
    bytes,
    completion_time
FROM v$backup_piece
ORDER BY completion_time DESC;
~~~

### 20.3. V$BACKUP_FILES

~~~sql
SELECT
    file#,
    file_type,
    status,
    device_type,
    completion_time,
    filename
FROM v$backup_files
ORDER BY completion_time DESC;
~~~

`V$BACKUP_FILES` consolidates metadata across backup/copy types. Do not assume every column is populated for every file type.

### 20.4. Recovery catalog views

When using a recovery catalog, you can query `RC_` views such as:

- `RC_BACKUP_SET`.
- `RC_BACKUP_PIECE`.
- `RC_DATAFILE_COPY`.
- `RC_ARCHIVED_LOG`.
- `RC_DATABASE`.

These views provide metadata across multiple target databases registered in the catalog. Filter carefully by `DB_KEY`, `DBID`, and `DB_UNIQUE_NAME` to avoid mixing backups across databases.

## 21. Practical scenarios

### 21.1. Backup file deleted via OS

Symptoms:

- `LIST BACKUP SUMMARY` still displays `AVAILABLE`.
- File does not exist on disk.

Handling:

~~~text
RMAN> CROSSCHECK BACKUP DEVICE TYPE DISK;
RMAN> LIST EXPIRED BACKUP;
~~~

After confirming the file is genuinely deleted:

~~~text
RMAN> DELETE EXPIRED BACKUP;
~~~

### 21.2. Tape media manager temporarily failing

Symptoms:

- Many SBT backups turn `EXPIRED`.
- The media manager's own catalog still shows records.
- Channels report connection errors.

Handling:

1. Stop `DELETE EXPIRED` jobs.
2. Fix the media manager/channel.
3. Verify `PARMS` and credentials.
4. Re-run `CROSSCHECK` on SBT.
5. Confirm backups return to `AVAILABLE`.

### 21.3. Disk backup moved offsite

If files are no longer at the path RMAN accesses, yet remain stored in an offsite vault:

~~~text
RMAN> CHANGE BACKUPSET 12 UNAVAILABLE;
~~~

When backups return:

~~~text
RMAN> CHANGE BACKUPSET 12 AVAILABLE;
RMAN> CROSSCHECK BACKUPSET 12;
~~~

`UNAVAILABLE` reflects a temporary DBA-managed state; `EXPIRED` is the result of a failed lookup.

### 21.4. FRA full

Never delete files manually right away. Instead:

1. Check `V$RECOVERY_FILE_DEST` and `V$RECOVERY_AREA_USAGE`.
2. Check the retention policy.
3. Run `CROSSCHECK` to update records.
4. Run `REPORT OBSOLETE`.
5. Check archived log deletion policy and standby apply status.
6. Verify restore preview.
7. Delete obsolete backups or increase FRA quota/storage per plan.

### 21.5. Retaining month-end backups long-term

You can create archival backups using the `KEEP` clause or use `CHANGE ... KEEP` to adjust retention status per documentation. Backups marked `KEEP` can be exempted from the normal retention policy for a specified duration.

Illustrative example:

~~~text
RMAN> CHANGE BACKUPSET 231 KEEP UNTIL TIME 'SYSDATE+180';
~~~

`KEEP FOREVER` requires a recovery catalog because the control file cannot retain repository records indefinitely. Do not use `KEEP` indiscriminately, as it can substantially increase storage consumption.

## 22. Common errors and troubleshooting

| Symptom | Possible cause | Troubleshooting direction |
| --- | --- | --- |
| `LIST` still shows deleted backups | Repository not crosschecked | `CROSSCHECK` the matching device type |
| `CROSSCHECK` marks many SBT backups `EXPIRED` | Media manager/channel unreachable | Stop deletions, fix media manager, and re-crosscheck |
| `DELETE EXPIRED` frees no disk space | Physical file still exists while record was `EXPIRED` | Use `REPORT OBSOLETE` and `DELETE OBSOLETE` if unneeded |
| `REPORT OBSOLETE` reports no retention policy | `CONFIGURE RETENTION POLICY TO NONE` | Configure an approved policy |
| Backup `AVAILABLE` yet restore fails | File corruption, missing logs, or invalid backup | Run `RESTORE VALIDATE`, `VALIDATE BACKUPSET`, and check archived logs |
| `OBSOLETE` backups remain on disk | RMAN was not told `DELETE OBSOLETE` or FRA has not reclaimed | Run `REPORT` then `DELETE OBSOLETE` if eligible |
| Backup marked `UNAVAILABLE` | DBA ran `CHANGE UNAVAILABLE` or offsite storage | Verify location and run `CHANGE AVAILABLE` when back |
| `CROSSCHECK` misses files in RAC | Inconsistent mounts/storage across nodes | Verify paths and storage visibility |
| Cannot crosscheck SBT | Missing maintenance channel or wrong SBT parameters | Configure channel for the media manager |
| `LIST EXPIRED` does not reflect latest state | `CROSSCHECK` not run after storage changes | Run `CROSSCHECK` then `LIST` again |
| `DELETE OBSOLETE` removes backups needed for recovery window | Policy or override shorter than required | Check `SHOW RETENTION POLICY` and `REPORT OBSOLETE` |
| Archived logs deleted too early | Archive log deletion policy/Data Guard not accounted for | Check policy and standby apply status |
| `LIST BACKUP` omits files copied outside RMAN | Backup lacks repository record | Run `CATALOG` when appropriate |

## 23. Common misconceptions

| Misconception | Reality |
| --- | --- |
| `LIST` confirms physical files still exist | `LIST` reads the repository; use `CROSSCHECK` to verify media |
| `REPORT OBSOLETE` deletes backups | `REPORT` only reports |
| `CROSSCHECK` deletes missing files | `CROSSCHECK` only updates repository status |
| `EXPIRED` means backup is obsolete | `EXPIRED` means unlocatable; `OBSOLETE` means unneeded by retention |
| `OBSOLETE` means backup is corrupted | The backup may be intact and restorable |
| `DELETE EXPIRED` frees space from existing files | It mainly cleans `EXPIRED` records; existing files trigger a warning and remain |
| `DELETE OBSOLETE` deletes only metadata | It deletes backups on media and updates the repository |
| `AVAILABLE` proves a backup can fully restore | Validation and restore testing are still required |
| `UNAVAILABLE` is the same as `EXPIRED` | `UNAVAILABLE` is set intentionally by the DBA; `EXPIRED` comes from crosscheck |
| `RECOVERY WINDOW` 7 days keeps only backups made in the last 7 days | Base backups prior to the window plus archived redo logs may be needed |
| `REPORT OBSOLETE RECOVERY WINDOW` alters default policy | It overrides evaluation only for that single command |
| `DELETE OBSOLETE RECOVERY WINDOW` with a shorter window is harmless | It can shrink your actual recovery window |
| `CROSSCHECK` automatically discovers all files in a directory | It checks only records already known to RMAN |
| `CROSSCHECK` and `VALIDATE` are identical | `CROSSCHECK` checks availability; `VALIDATE` reads and checks backup data |
| FRA deletes any file when full | It deletes only files eligible under retention/deletion rules |

## 24. Checklist before running maintenance

**Connection and scope**

- Connected to the right target database?
- Are DBID and `DB_UNIQUE_NAME` correct?
- Is a recovery catalog used?
- Is this Data Guard or RAC?
- Connected to CDB root or a PDB?

**Repository and devices**

- Checked `SHOW ALL` and retention policy?
- Checked `LIST BACKUP SUMMARY`?
- Are `DISK` mounts and permissions valid?
- Is the SBT/media manager healthy?
- Are maintenance channels properly configured?
- Are any backups stored offsite?

**Evaluating recoverability**

- What does `REPORT NEED BACKUP` report?
- Does `REPORT UNRECOVERABLE` list any files?
- Does `REPORT OBSOLETE` match the business recovery window?
- Does the archived log deletion policy protect standbys?
- Does `RESTORE DATABASE PREVIEW` select required backups?
- Has `RESTORE VALIDATE` been tested recently?

**Before deleting**

- Verified `EXPIRED` items are truly gone?
- Reviewed each `OBSOLETE` backup?
- Any `KEEP` or archival backups that must remain?
- Any audit/legal retention requirements?
- Approval obtained for `DELETE`?
- Output logging and rollback/restore plan ready?

## 25. Comprehensive practice lab

This lab uses RMAN to inspect backups, crosscheck, report expired/obsolete items, and practice maintenance. Run only on a lab database with test backups.

### Step 1 — Connect to RMAN

~~~text
$ rman target /
RMAN> SHOW ALL;
RMAN> SHOW RETENTION POLICY;
~~~

If using a recovery catalog, connect to the proper catalog schema per DBA procedure.

### Step 2 — List backups

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> LIST BACKUP;
RMAN> LIST COPY;
RMAN> LIST ARCHIVELOG ALL;
~~~

Note backup keys, completion times, device types, tags, and statuses.

### Step 3 — Check schema and needed backups

~~~text
RMAN> REPORT SCHEMA;
RMAN> REPORT NEED BACKUP;
RMAN> REPORT UNRECOVERABLE;
~~~

### Step 4 — CROSSCHECK disk

~~~text
RMAN> CROSSCHECK BACKUP DEVICE TYPE DISK;
RMAN> CROSSCHECK COPY;
~~~

If the lab has SBT, crosscheck using the corresponding media manager channel.

### Step 5 — View EXPIRED

~~~text
RMAN> LIST EXPIRED BACKUP;
RMAN> LIST EXPIRED COPY;
~~~

Never delete records before verifying why files could not be found.

### Step 6 — Report OBSOLETE

~~~text
RMAN> REPORT OBSOLETE;
~~~

Compare against other policies:

~~~text
RMAN> REPORT OBSOLETE REDUNDANCY 2;
RMAN> REPORT OBSOLETE RECOVERY WINDOW OF 14 DAYS;
~~~

### Step 7 — Preview restore

~~~text
RMAN> RESTORE DATABASE PREVIEW SUMMARY;
~~~

Confirm RMAN still finds the backups required for recovery.

### Step 8 — Clean EXPIRED in the lab

Only execute if files were verified gone:

~~~text
RMAN> DELETE EXPIRED BACKUP;
RMAN> DELETE EXPIRED COPY;
~~~

### Step 9 — Clean OBSOLETE in the lab

Only execute once the lab retention policy is verified:

~~~text
RMAN> DELETE OBSOLETE;
~~~

### Step 10 — Verify after maintenance

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> LIST EXPIRED BACKUP;
RMAN> REPORT OBSOLETE;
RMAN> RESTORE DATABASE PREVIEW SUMMARY;
~~~

Record the results and confirm remaining backups still meet lab recovery goals.

## 26. Self-check questions

1. Where does the RMAN repository store information?
2. How does a recovery catalog differ from the control file repository?
3. What is `LIST BACKUP SUMMARY` used for?
4. How does `LIST BACKUP BY FILE` differ from `LIST BACKUP SUMMARY`?
5. What object types does `LIST COPY` display?
6. What does `LIST EXPIRED` show?
7. What does `REPORT NEED BACKUP` check?
8. What types of operations does `REPORT UNRECOVERABLE` detect?
9. Does `REPORT OBSOLETE` delete files?
10. What does `CROSSCHECK` verify?
11. How do `CROSSCHECK BACKUP` and `CROSSCHECK COPY` differ?
12. When is an SBT maintenance channel needed?
13. Does `CROSSCHECK` delete physical files?
14. Does `EXPIRED` mean a backup is corrupted?
15. Does `AVAILABLE` guarantee a restore will succeed?
16. Who sets `UNAVAILABLE`, and when is it used?
17. What determines whether a backup is `OBSOLETE`?
18. Does `DELETE EXPIRED` delete physical files that still exist?
19. What does `DELETE OBSOLETE` do?
20. What does `REDUNDANCY 2` mean?
21. What does `RECOVERY WINDOW OF 7 DAYS` mean?
22. Why is a recovery window not simply keeping backups created in the last seven days?
23. Does `REPORT OBSOLETE RECOVERY WINDOW` change the configured retention policy?
24. What risk comes with running `DELETE OBSOLETE RECOVERY WINDOW` using a shorter window?
25. Why run `CROSSCHECK` before `REPORT OBSOLETE`?
26. How does `CROSSCHECK` differ from `VALIDATE`?
27. When should you use `RESTORE DATABASE PREVIEW`?
28. When should you use `RESTORE DATABASE VALIDATE`?
29. Why must you check the archived log deletion policy in Data Guard?
30. Why should you not run `DELETE NOPROMPT OBSOLETE` without reviewing first?

**Suggested answers:**

1. Always in the target control file; optionally also in a recovery catalog.
2. A recovery catalog is an optional centralized repository, whereas the control file repository always exists.
3. To view a one-line summary for each backup.
4. `BY FILE` groups backups by individual data file/log; `SUMMARY` gives an overview per backup set.
5. Data file copies, archived log copies, and image copies.
6. Repository records marked `EXPIRED`.
7. Data files needing additional backups to satisfy the retention policy.
8. `NOLOGGING`/unrecoverable operations such as direct-path loads.
9. No, it only reports.
10. Reconciles repository records with files on disk or in a media manager.
11. `BACKUP` checks backup sets/copies; `COPY` checks image copies and file copies.
12. When checking/deleting SBT backups without an appropriate automatic SBT channel.
13. No.
14. No; it only means `CROSSCHECK` could not find or access the file.
15. No; validation and restore testing are needed.
16. Set intentionally by the DBA when files are temporarily inaccessible or moved offsite.
17. The retention policy.
18. No; if the file still exists, RMAN warns and does not delete the physical file.
19. Deletes physical backups no longer needed by policy and updates the repository.
20. Retain two eligible backups for each data file.
21. Recoverability to any point in time within the last seven days must be maintained per policy conditions.
22. A full backup prior to the window start and archived logs may be needed to recover to the start of the window.
23. No; it overrides evaluation only for that single `REPORT` command.
24. It can reduce actual recoverability relative to the configured policy.
25. So the repository reflects actual physical file states.
26. `CROSSCHECK` checks availability; `VALIDATE` reads and checks backup data.
27. To see which backups RMAN plans to use without reading backup contents.
28. To verify that backups selected by RMAN are readable and valid.
29. To avoid deleting logs that a standby has not applied or that policy forbids deleting.
30. Because `NOPROMPT` skips confirmation and can delete backups unintentionally.

## Oracle Reference Documentation

- [Oracle Database 19c Backup and Recovery User's Guide — Reporting on RMAN Operations](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/reporting-rman-operations.html): LIST, REPORT, REPORT NEED BACKUP, REPORT UNRECOVERABLE and REPORT OBSOLETE.
- [Oracle Database 19c Backup and Recovery User's Guide — Maintaining RMAN Backups and Repository Records](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/maintaining-rman-backups.html): CROSSCHECK, AVAILABLE/EXPIRED, DELETE EXPIRED and DELETE OBSOLETE.
- [Oracle Database 19c Backup and Recovery User's Guide — RMAN Backup Concepts](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/rman-backup-concepts.html): retention policy, redundancy and recovery window.
- [Oracle Database 19c Backup and Recovery Reference — LIST](https://docs.oracle.com/en/database/oracle/oracle-database/19/rcmrf/LIST.html): LIST syntax and output.
- [Oracle Database 19c Backup and Recovery Reference — DELETE](https://docs.oracle.com/en/database/oracle/oracle-database/19/rcmrf/DELETE.html): DELETE, EXPIRED, OBSOLETE, FORCE and NOPROMPT semantics.
- [Oracle Database 19c Backup and Recovery Reference — CROSSCHECK](https://docs.oracle.com/en/database/oracle/oracle-database/19/rcmrf/CROSSCHECK.html): crosscheck syntax and repository states.
- [Oracle Database 19c Backup and Recovery Reference — REPORT](https://docs.oracle.com/en/database/oracle/oracle-database/19/rcmrf/REPORT.html): REPORT syntax and reporting criteria.
- [Oracle Database 19c Database Reference — V$BACKUP_FILES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-BACKUP_FILES.html): querying backup metadata.

**Key rule to remember:** `LIST` shows what the RMAN repository currently records; `REPORT` evaluates whether backups satisfy recovery requirements and retention policy; `CROSSCHECK` reconciles records against `DISK`/`SBT`. `EXPIRED` means a backup was not found during crosscheck, whereas `OBSOLETE` means it is no longer needed under the retention policy. `DELETE EXPIRED` cleans `EXPIRED` records; `DELETE OBSOLETE` deletes unneeded physical backups. Always verify your retention policy, storage devices, archived log deletion policy, and `RESTORE` capability before running deletion commands.
