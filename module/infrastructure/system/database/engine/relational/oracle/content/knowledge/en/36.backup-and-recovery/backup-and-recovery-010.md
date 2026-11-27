# RESTORE VALIDATE, Block Corruption Checks, and Recovery Rehearsals

A backup is only valuable if it is readable, contains all required data, and can be recovered into a properly functioning database within target timeframes. A backup job finishing without error does not prove that every backup piece is readable or that sufficient archived redo exists to recover to the desired point in time.

Oracle Recovery Manager (RMAN) provides commands to verify backups and data without restoring over a running database. Two key operations are **RESTORE ... VALIDATE**, which checks the backups RMAN would select for a restore operation, and **VALIDATE**, which reads and checks datafiles or backups to detect block corruption. Beyond those, DBAs must rehearse restore/recovery in an isolated environment to prove the end-to-end process meets RTO and RPO.

## 1. Distinguishing Successful Backups, Validation, and Restore Drills

These three activities verify different levels of assurance:

| Activity | What Is Verified | What Remains Unproven |
|---|---|---|
| Backup job completes | RMAN wrote the backup per configuration and reported success | Whether the backup can fully recover to the point the business needs |
| RMAN `VALIDATE` / `RESTORE VALIDATE` | Datafiles or backup pieces are readable and pass requested checks | That the whole database has been recovered, opened, and applications work |
| Restore drill | Backups, control file, SPFILE, archived redo, passwords/keystore, and recovery workflow combine into a working database | Does not automatically prove every disaster scenario or every point in time has been tested |

In short:

- Backups produce recoverable copies.
- Validation verifies readability and catches certain forms of data corruption.
- Restore drills perform an actual recovery in a test environment, followed by database and application verification.

None of these replaces the others. A backup can pass validation yet a restore drill can still fail due to missing archived redo, a missing TDE wallet, missing storage setup, or an incorrect database open procedure.

## 2. What Is RESTORE VALIDATE?

In RMAN, `RESTORE ... VALIDATE` instructs RMAN to determine the backups needed for a restore operation and then read the corresponding backup pieces to verify they are usable. RMAN does not overwrite target datafiles and does not perform an actual restore.

Example:

~~~text
RMAN> RESTORE DATABASE VALIDATE;
~~~

This command checks the backups RMAN selects to restore the database based on the repository and current state. It is useful for confirming required backup pieces are readable, though it produces no restored datafiles.

You can validate a specific datafile:

~~~text
RMAN> RESTORE DATAFILE 7 VALIDATE;
~~~

Or validate a tablespace:

~~~text
RMAN> RESTORE TABLESPACE USERS VALIDATE;
~~~

Exact command scope depends on the database, recovery catalog/control file repository, channel configuration, restore point, and available backups. To validate recoverability to a specific SCN or point in time, specify the same `UNTIL` clause planned for the actual restore.

### RESTORE VALIDATE Does Not Restore Files

After `RESTORE DATABASE VALIDATE`:

- Target datafiles are neither created nor overwritten as in a normal restore.
- The database is not rolled back to another SCN.
- No `RECOVER DATABASE` operation runs.
- The database is not opened with `RESETLOGS`.
- It does not prove applications can start after recovery.

This is a backup readability check, not a complete recovery rehearsal.

## 3. RESTORE PREVIEW and RESTORE VALIDATE Differ

RMAN provides `PREVIEW` to list the backups it plans to use for a restore:

~~~text
RMAN> RESTORE DATABASE PREVIEW;
RMAN> RESTORE DATABASE PREVIEW SUMMARY;
~~~

`PREVIEW` shows which backup sets, datafile copies, or related artifacts RMAN selects based on the repository, target time, and configuration. It does not read the full contents of backup pieces to verify readability.

`RESTORE VALIDATE` takes the extra step of reading and checking the selected backup pieces:

~~~text
RMAN> RESTORE DATABASE VALIDATE;
~~~

A verification workflow can combine both:

~~~text
RMAN> RESTORE DATABASE PREVIEW SUMMARY;
RMAN> RESTORE DATABASE VALIDATE;
~~~

Reading `PREVIEW` first tells the DBA which backups RMAN intends to use. `VALIDATE` then verifies whether the required backup pieces can actually be read.

A successful `PREVIEW` does not prove backup pieces are uncorrupted. Conversely, a successful `VALIDATE` does not prove external requirements—such as target disk space, filesystem permissions, passwords, wallets, or application connectivity—are ready.

## 4. Specifying Time or SCN When Validating a Restore

Database recovery often requires targeting a specific point:

- A time just before a logical error occurred.
- An SCN recorded in a recovery plan.
- The last applicable archived redo sequence.
- A target point for a PITR drill.

Example validating backups usable for restoring to a point in time:

~~~text
RMAN> RUN {
  SET UNTIL TIME "TO_DATE('2026-11-14 02:00:00',
                          'YYYY-MM-DD HH24:MI:SS')";
  RESTORE DATABASE PREVIEW SUMMARY;
  RESTORE DATABASE VALIDATE;
}
~~~

The timestamp in the example is illustrative. Align timezone, database host clock, session timezone, and how RMAN interprets timestamps. Where high precision is required, an SCN is typically less ambiguous than wall-clock time if the SCN was accurately recorded.

Example using SCN:

~~~text
RMAN> RUN {
  SET UNTIL SCN 123456789;
  RESTORE DATABASE PREVIEW;
  RESTORE DATABASE VALIDATE;
}
~~~

The SCN must be valid for the recovery goal and available backups/redo. Specifying `UNTIL` during restore validation checks the exact set of backups matching the recovery plan.

## 5. VALIDATE Database and Datafiles

The `VALIDATE` command reads blocks of the database or specified scope to check for errors. Example:

~~~text
RMAN> VALIDATE DATABASE;
~~~

Validate a tablespace:

~~~text
RMAN> VALIDATE TABLESPACE USERS;
~~~

Validate a datafile:

~~~text
RMAN> VALIDATE DATAFILE 7;
~~~

Validate a specific block:

~~~text
RMAN> VALIDATE DATAFILE 7 BLOCK 12345;
~~~

By default, `VALIDATE` focuses on physical corruption such as unreadable blocks, checksum mismatches, or inconsistent block headers/bodies under physical checks. It detects errors encountered while reading blocks.

### Logical Checking with CHECK LOGICAL

You can instruct RMAN to perform additional checks on internal logical structures within blocks:

~~~text
RMAN> VALIDATE DATABASE CHECK LOGICAL;
~~~

Or narrow the scope:

~~~text
RMAN> VALIDATE DATAFILE 7 CHECK LOGICAL;
~~~

`CHECK LOGICAL` adds structural block verification, such as checking the consistency of internal block data structures. This consumes extra CPU and can lengthen validation duration.

Do not equate a logical block check with business-logic correctness. A block can be structurally valid to Oracle while holding wrong business values—for example, an erroneously updated balance or a structurally valid deletion that violated business rules. RMAN `CHECK LOGICAL` does not replace data reconciliation, constraints, application validation, or business audits.

## 6. BACKUP VALIDATE and VALIDATE BACKUPSET

Beyond `RESTORE VALIDATE`, RMAN offers other validation commands for distinct purposes.

### BACKUP VALIDATE

~~~text
RMAN> BACKUP VALIDATE DATABASE;
~~~

`BACKUP VALIDATE` reads datafiles like a backup operation without producing new backup pieces. It checks the source data that a backup would read. You can add `CHECK LOGICAL`:

~~~text
RMAN> BACKUP VALIDATE CHECK LOGICAL DATABASE;
~~~

`BACKUP VALIDATE` does not replace checking existing backups. It inspects current source datafiles, whereas `RESTORE VALIDATE` inspects the backups RMAN plans to restore from.

### VALIDATE BACKUPSET

To check a specific backup set:

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> VALIDATE BACKUPSET 123;
~~~

Replace `123` with the backup set key from the repository. `VALIDATE BACKUPSET` reads the specified backup set and checks integrity within RMAN's capabilities.

A backup set can span multiple backup pieces. If a backup set spans multiple pieces or devices, ensure RMAN can access every piece required.

## 7. Distinguishing VALIDATE, CROSSCHECK, and RESTORE VALIDATE

Three commands are frequently confused:

| Command | Purpose | Reads Backup Block Contents? |
|---|---|---|
| `CROSSCHECK BACKUP` | Reconciles repository with backup existence/accessibility on devices | Not a full block-content check |
| `VALIDATE BACKUPSET` | Reads and checks a specific backup set | Yes |
| `RESTORE DATABASE VALIDATE` | Checks backups selected for a restore operation | Yes, for the required backup pieces |

`CROSSCHECK` example:

~~~text
RMAN> CROSSCHECK BACKUP;
RMAN> LIST EXPIRED BACKUP;
~~~

`CROSSCHECK` updates repository status when backups are no longer present or reachable as RMAN checks them. It does not prove remaining backup pieces are free of corrupted blocks.

Never run `DELETE EXPIRED` or `DELETE OBSOLETE` merely to tidy up lists without understanding retention policies, backup dependencies, and copy preservation procedures. Backup deletion commands can reduce recoverability.

## 8. Physical Block Corruption vs. Logical Block Corruption

An Oracle block can become corrupted in multiple ways. Distinguish:

### Physical Corruption

Physical corruption occurs when a block cannot be read properly or its physical structure fails Oracle checks. Examples:

- Checksum mismatch.
- Partially written or fractured block.
- Inconsistent block header/body.
- I/O returning bad data or unreadable blocks.

Physical corruption can stem from storage, controllers, memory, filesystems, write errors, firmware, or software bugs.

### Logical Corruption

Logical corruption means a block is physically readable, yet its internal logical structure fails validation rules. Examples may involve row directories, row pieces, or index structures.

Logical corruption can be caught when `CHECK LOGICAL` is enabled or when the database encounters errors during reads/checks. Not all logical errors share the same root cause or fix.

### Business Logic Errors Are Not Block Corruption

Examples:

- A product price updated incorrectly.
- A customer record deleted by mistake.
- A business transaction committed in error.
- Data out of sync between two systems.

These cases may require Flashback, PITR, auditing, application recovery, or business reconciliation. RMAN block validation cannot determine whether data is business-correct.

## 9. Views for Monitoring Block Corruption

When RMAN or database operations detect corruption, details can be recorded in dynamic performance views.

### V$DATABASE_BLOCK_CORRUPTION

~~~sql
SELECT file#,
       block#,
       blocks,
       corruption_change#,
       corruption_type
  FROM v$database_block_corruption
 ORDER BY file#, block#;
~~~

Key columns:

- `FILE#`: datafile number containing the block.
- `BLOCK#`: first block in the reported corrupted range.
- `BLOCKS`: number of contiguous blocks in the range.
- `CORRUPTION_CHANGE#`: SCN associated with the corruption per metadata.
- `CORRUPTION_TYPE`: type of error recorded.

`CORRUPTION_TYPE` may report values such as `CHECKSUM`, `FRACTURED`, `CORRUPT`, `LOGICAL`, or others depending on release and detection method.

A row with `BLOCKS` greater than 1 represents a multi-block range, not just a single block. Account for the entire range when planning repairs.

### V$BACKUP_CORRUPTION and V$COPY_CORRUPTION

~~~sql
SELECT file#,
       block#,
       blocks,
       corruption_change#,
       corruption_type
  FROM v$backup_corruption
 ORDER BY file#, block#;

SELECT file#,
       block#,
       blocks,
       corruption_change#,
       corruption_type
  FROM v$copy_corruption
 ORDER BY file#, block#;
~~~

These views reflect corruption detected inside backup sets or image copies respectively. A clean source datafile can still yield a corrupted backup copy due to device, write, or transfer errors. Conversely, an older backup may contain blocks that were already corrupted earlier.

### Identifying Datafile Names

~~~sql
SELECT file#,
       name
  FROM v$datafile
 ORDER BY file#;
~~~

Joining `FILE#` with datafile names identifies the affected tablespace and objects:

~~~sql
SELECT d.file#,
       d.name,
       t.name AS tablespace_name
  FROM v$datafile d
  JOIN v$tablespace t
    ON t.ts# = d.ts#
 ORDER BY d.file#;
~~~

If you need to identify the segment containing a block, query `DBA_EXTENTS`:

~~~sql
SELECT owner,
       segment_name,
       partition_name,
       segment_type,
       tablespace_name,
       file_id,
       block_id,
       blocks
  FROM dba_extents
 WHERE file_id = 7
   AND 12345 BETWEEN block_id AND block_id + blocks - 1;
~~~

Replace `FILE_ID` and block number with real values. `DBA_EXTENTS` describes extents allocated to segments; a block may belong to segment metadata, bitmaps, undo, or special block types that do not map neatly to a single `DBA_EXTENTS` row. No rows returned does not prove a block is unimportant.

## 10. Detecting Corruption via RMAN and the Database

Common detection methods:

1. RMAN `VALIDATE` reads datafiles or backups.
2. RMAN `RESTORE VALIDATE` reads backup pieces needed for restore.
3. Database encounters errors reading blocks during queries or background activity.
4. `DBVERIFY` checks files/blocks via an external tool where applicable.
5. Oracle logs errors in the alert log or trace files.

Common error codes:

| Error Code | General Meaning |
|---|---|
| `ORA-01578` | Oracle detected a corrupted data block |
| `ORA-01110` | Identifies the datafile associated with another error |
| `ORA-19566` | RMAN encountered corrupt blocks exceeding the threshold during a backup |
| `ORA-19624` | Error during backup/restore operation; check accompanying errors |
| `ORA-270xx` | I/O or OS-layer error, typically requiring inspection of OS error details |

Never diagnose root cause from a single error code. Read the full error stack, alert log, trace files, OS/storage logs, and RMAN output.

## 11. Check Blocks at a Narrow Scope First

When corruption is suspected in a datafile or block range, run targeted validation:

~~~text
RMAN> VALIDATE DATAFILE 7;
~~~

Or:

~~~text
RMAN> VALIDATE DATAFILE 7 BLOCK 12345;
~~~

If logical checking is needed:

~~~text
RMAN> VALIDATE DATAFILE 7 CHECK LOGICAL;
~~~

A narrow scope speeds up investigation and reduces I/O compared to validating the entire database. However, if corruption may exist elsewhere, checking one block does not replace a comprehensive validation schedule.

After validation, query `V$DATABASE_BLOCK_CORRUPTION` and inspect the alert log/RMAN output. Record the file number, block range, corruption type, detection time, and commands run.

## 12. Repairing Blocks with Block Media Recovery

When corruption is recoverable at the block level and valid backups/redo exist, RMAN can perform block media recovery. Instead of restoring the entire datafile, RMAN restores only the damaged blocks from backup and applies necessary redo.

Example:

~~~text
RMAN> RECOVER DATAFILE 7 BLOCK 12345;
~~~

Or recover all blocks listed in the corruption list:

~~~text
RMAN> RECOVER CORRUPTION LIST;
~~~

Block media recovery is typically useful when:

- Only a few blocks are corrupted.
- The database has a valid backup containing the needed blocks.
- Required archived redo exists to roll the blocks forward to a consistent state.
- The database mode and configuration support the operation.

Not every corruption can be repaired with block media recovery. Logical corruption, blocks in special structures, missing backups/redo, or widespread corruption may require different approaches. Check RMAN documentation for your exact release and assess the error type before executing.

### Why Does Block Media Recovery Reduce Downtime?

If only one block of a large datafile is corrupted, restoring the whole datafile requires far more I/O and time. Block media recovery repairs only the specified blocks, while other blocks in the datafile can remain accessible under supported conditions.

However, the operation still consumes resources, requires backups and redo, and must be monitored. Never treat it as risk-free.

### After Block Recovery

Check:

~~~sql
SELECT file#,
       block#,
       blocks,
       corruption_type
  FROM v$database_block_corruption
 ORDER BY file#, block#;
~~~

Re-validate the repaired range:

~~~text
RMAN> VALIDATE DATAFILE 7 BLOCK 12345;
~~~

Inspect the alert log, RMAN output, application behavior, and related data reconciliation. The corruption list clearing is a positive sign, yet actual queries and business correctness must still be verified.

## 13. When Is Datafile or Tablespace Restore Needed?

Block media recovery is not always suitable. Restoring/recovering a datafile or tablespace may be needed when:

- Many blocks are corrupted or corruption is widespread.
- Backups/redo do not satisfy block recovery prerequisites.
- A datafile is lost or unreadable at the file level.
- Corruption affects structures requiring broader-scope recovery.
- The recovery plan requires restoring to a specific SCN/point in time.

Example datafile recovery command structure:

~~~text
RMAN> RESTORE DATAFILE 7;
RMAN> RECOVER DATAFILE 7;
~~~

This is only a conceptual outline, not a sequence safe to run blindly in every database state. If the datafile belongs to `SYSTEM`, `UNDO`, is currently online, the database is in `NOARCHIVELOG`, or the file is actively in use, the procedure differs considerably. Check file status, backups, redo, control file, datafile path, and release documentation beforehand.

After recovering a datafile, you may need to bring the file online or open the database appropriately. Never treat `ALTER DATABASE OPEN RESETLOGS` as a default step for every datafile recovery.

## 14. Readable Backups Can Still Be Insufficient for Recovery

A passing `RESTORE VALIDATE` does not prove every component needed to open the database at the target point is present. Frequently overlooked dependencies include:

- Control file or recovery catalog.
- SPFILE and required parameters.
- All required datafiles.
- Continuous archived redo logs up to the target time.
- Online redo needed in specific scenarios.
- TDE keystore/wallet and passwords.
- Backup encryption password or Oracle key material.
- Password file and listener/service configuration.
- Target filesystem/ASM disk groups and permissions.
- External tables, `DIRECTORY` objects, `BFILE`s, external procedures, or out-of-database files.
- Data Guard/RAC configuration if within recovery scope.

A healthy datafile backup missing required archived redo cannot recover to the desired SCN. A TDE-encrypted database may restore files cleanly yet fail to open if the keystore is unavailable.

Therefore, the backup plan must retain and test restoring supporting components as well, not just datafiles.

## 15. Checking Archived Redo and Recovery Readiness

RMAN needs matching archived redo to recover a datafile or database to the target point. You can list archived logs:

~~~text
RMAN> LIST ARCHIVELOG ALL;
~~~

Check backups of archived logs:

~~~text
RMAN> LIST BACKUP OF ARCHIVELOG ALL;
~~~

And validate required backups via restore validate:

~~~text
RMAN> RESTORE ARCHIVELOG ALL VALIDATE;
~~~

Command scope and log selection depend on target time, repository, and configuration. In practice, validate logs needed for a specific SCN/time range rather than blindly reading entire history.

A SQL check of archived logs in the database:

~~~sql
SELECT thread#,
       sequence#,
       first_change#,
       next_change#,
       archived,
       deleted,
       status,
       name
  FROM v$archived_log
 ORDER BY thread#, sequence#;
~~~

In RAC, each thread has its own sequences. When checking continuity, inspect all relevant threads, not just one thread. Some rows may represent multiple archived log copies; interpret `status`/`name` accurately against the repository and control file.

## 16. Checking Backup Pieces and Storage Devices

Backups can reside on disk, tape, or a media manager. `RESTORE VALIDATE` must be able to read backup pieces via the corresponding channels and devices.

Before validating:

- Check channel configuration.
- Check read permissions on backup files.
- Check mount points or ASM disk groups.
- Check media manager/SBT library if using tape.
- Check credentials and network connectivity to the backup appliance.
- Confirm encryption passwords or keystores are available when needed.

Example SBT channel configuration (media-manager dependent):

~~~text
RMAN> RUN {
  ALLOCATE CHANNEL c1 DEVICE TYPE SBT_TAPE;
  RESTORE DATABASE VALIDATE;
  RELEASE CHANNEL c1;
}
~~~

This is an illustrative skeleton only. Tape systems typically require `PARMS`, `ENV`, or vendor-supplied channel configuration. Never copy SBT settings from another environment without verifying the library and credentials.

For disk backups, RMAN can use the default `DISK` channel or configured channels. When validation fails, distinguish:

- Backup piece missing.
- Wrong read permissions or path.
- Device unmounted.
- Media manager error.
- Corrupted backup piece.
- Missing encryption key/password.

Do not conclude a backup is corrupted if the real root cause is an unreachable media manager.

## 17. Periodic Verification Schedule with RMAN

An operational schedule can combine:

### After Every Critical Backup

- Confirm the job completed and backup pieces were written.
- Review RMAN output and warnings/errors.
- Crosscheck per device policy.
- Record DBID, timestamp, backup tag, and storage location.

### On a Validation Schedule

- Run `RESTORE DATABASE VALIDATE` on a defined schedule and scope.
- Run `VALIDATE DATABASE` or `VALIDATE DATAFILE` on schedule to check source data.
- Add `CHECK LOGICAL` at a frequency suited to resource budgets.
- Check the corruption list and RMAN output.

### On a Restore Drill Schedule

- Select a representative backup set or point in time.
- Restore into an isolated environment.
- Recover to a target SCN/time.
- Open the database per proper procedure.
- Verify applications and data.
- Measure actual RTO/RPO.

Exact frequency must align with SLAs, data criticality, size, backup storage costs, and organizational policy. Avoid running frequent whole-database validations if they introduce I/O contention with production workloads.

## 18. Designing Safe Restore Drills

A restore drill is an actual recovery rehearsal, but it must be isolated from production. The objective is to prove a database can be recovered from backups and redo—not to test by overwriting production files.

### Preparing the Environment

Before restoring:

1. Provision an isolated test machine or environment.
2. Ensure no datafile paths overlap with production.
3. Provision sufficient space for datafiles, FRA/TEMP, and archived redo.
4. Prepare a compatible Oracle Home, patch level, and configuration.
5. Prepare the password file, SPFILE, control file, and DBID.
6. Prepare the TDE wallet/keystore and passwords if encrypted.
7. Prepare access to backup storage/media manager.
8. Determine the target SCN or point in time to recover.
9. Define database name, `DB_UNIQUE_NAME`, listener/services, and network isolation.

The drill environment must never accidentally advertise production-identical services or send real emails, messages, payments, or scheduled jobs. Disable outbound integrations and inappropriate scheduler jobs before opening test applications.

### Preparing the Backup Set

Check:

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> RESTORE DATABASE PREVIEW SUMMARY;
RMAN> RESTORE DATABASE VALIDATE;
~~~

If the drill targets PITR, run `PREVIEW` and `VALIDATE` with the exact planned `UNTIL SCN` or `UNTIL TIME`. Verify archived redo, control file, and encryption components.

### Executing Restore and Recovery

In the test environment, the workflow may include:

1. Start the instance in `NOMOUNT` with the proper SPFILE/PFILE.
2. Restore the control file if required.
3. Mount the database.
4. Catalog backups if they are absent from the current repository.
5. Restore datafiles to mapped target paths.
6. Recover the database to the target SCN/time.
7. Open the database in the proper mode, typically `RESETLOGS` after incomplete recovery.
8. Check PDBs and services.
9. Run smoke tests and data reconciliation.

Exact steps and commands depend on backup type, control file availability, ASM/filesystem, DBID, CDB/PDB, RAC, and recovery type. Never use one generic restore script for all databases.

## 19. Restore Rehearsal Framework in an Isolated Environment

The example below illustrates the conceptual sequence for a database with RMAN backups on disk. Paths, DBID, database name, SPFILE, control file, and SCN must be substituted from the real runbook.

~~~text
RMAN> STARTUP NOMOUNT;
RMAN> SET DBID 1234567890;
RMAN> RESTORE SPFILE FROM AUTOBACKUP;
~~~

If using the restored SPFILE, restart the instance per procedure to load it. If the control file also needs restoring:

~~~text
RMAN> STARTUP NOMOUNT;
RMAN> RESTORE CONTROLFILE FROM AUTOBACKUP;
RMAN> ALTER DATABASE MOUNT;
~~~

After mounting, if backup pieces are absent from the current repository, catalog the appropriate directory:

~~~text
RMAN> CATALOG START WITH '/backup/stage/';
RMAN> LIST BACKUP SUMMARY;
~~~

Restore and recover:

~~~text
RMAN> RUN {
  SET UNTIL SCN 123456789;
  RESTORE DATABASE;
  RECOVER DATABASE;
}
~~~

For incomplete recovery to an SCN/time, open the database with `RESETLOGS` per the corresponding recovery procedure:

~~~text
RMAN> ALTER DATABASE OPEN RESETLOGS;
~~~

Never run the commands above on production. `STARTUP`, `RESTORE CONTROLFILE`, `SET DBID`, `CATALOG`, `SET UNTIL`, and `OPEN RESETLOGS` must be sequenced accurately for the scenario. If the database is a CDB, verify PDBs after opening the CDB and perform PDB recovery steps if included in drill scope.

### Post-Open Checks

~~~sql
SELECT name,
       open_mode,
       database_role
  FROM v$database;

SELECT name,
       open_mode,
       restricted
  FROM v$pdbs
 ORDER BY name;
~~~

Then verify:

- Datafiles and tablespaces are in expected states.
- Application PDBs are open in the right mode.
- Invalid objects and component statuses.
- Inappropriate jobs are disabled in the drill environment.
- Test services point to the recovered database, not production.
- Applications can log in and run basic business queries.
- Data matches the expected target point in time.

## 20. Measuring RTO and RPO

A restore drill should measure real metrics rather than merely marking pass/fail.

**RTO (Recovery Time Objective)** is the target time to restore service operation after an incident. During a drill, record elapsed time from starting the recovery procedure until the application passes defined readiness checks.

**RPO (Recovery Point Objective)** is the maximum acceptable data loss, usually expressed as a time span of data. During a drill, record the timestamp/SCN of the latest recoverable data and compare it against the simulated incident timestamp.

Example:

| Metric | Target | Drill Result |
|---|---|---|
| RTO | 2 hours | 1 hour 35 minutes |
| RPO | 15 minutes | 8 minutes |
| Restore validate | Success | Success |
| Recovery to target SCN | Success | Success |
| PDB open mode | `READ WRITE` | `READ WRITE` |
| Application smoke test | Success | Success |

These numbers are illustrative. RTO/RPO must be established from business requirements, not copied from examples as default SLAs.

If `RESTORE VALIDATE` takes 30 minutes while a restore drill takes 4 hours, hunt for bottlenecks in datafile restore, archived redo apply, storage throughput, channel configuration, network, or application checks.

## 21. Rehearsing Different Scenarios

Do not test whole-database restore once and assume every scenario is proven. Consider rehearsing:

| Scenario | What to Test |
|---|---|
| Loss of one datafile | Restore/recover datafile and verify tablespace operation |
| Corruption of several blocks | Validate, detect corruption, and run block media recovery if applicable |
| Loss of control file | Restore control file, mount, and continue recovery |
| Loss of SPFILE | Restore SPFILE or build a minimal PFILE to recover |
| Logical error from human mistake | PITR to before the error; verify data |
| Loss of entire host | Recover onto another host/environment with remapped paths |
| Loss of primary in Data Guard | Test dedicated switchover/failover procedures per architecture |
| Loss of PDB or data inside a PDB | Rehearse release-appropriate PDB restore/recovery |
| Missing TDE wallet | Verify ability to retrieve keystore and open encrypted data |
| Loss of backup storage/site | Recover from copies at another location or offsite media |

Each scenario has its own prerequisites and procedures. In particular, Data Guard switchover/failover is distinct from an RMAN restore drill; each needs separate runbooks and rehearsals.

## 22. Monitoring Performance and Impact of VALIDATE

`VALIDATE` and `RESTORE VALIDATE` read large volumes of data and can generate substantial I/O. Before running in production:

- Check database and backup sizes.
- Estimate read duration and storage speed.
- Check peak workload hours.
- Cap channel parallelism appropriately.
- Pick a suitable run window and monitor latency.
- Assess impact on the FRA, tape library, or backup appliance.
- Avoid running too many concurrent validate/backup/restore jobs that compete for resources.

RMAN can use multiple channels to read in parallel. Adding channels can shorten runtime if storage handles it, or slow down production via I/O contention.

Example limiting channels:

~~~text
RMAN> RUN {
  ALLOCATE CHANNEL c1 DEVICE TYPE DISK;
  ALLOCATE CHANNEL c2 DEVICE TYPE DISK;
  RESTORE DATABASE VALIDATE;
  RELEASE CHANNEL c1;
  RELEASE CHANNEL c2;
}
~~~

Tune channel count according to throughput, CPU, backup device, and load. Never assume more channels are always better.

## 23. Checking Block Protection Settings

Several parameters affect block error detection:

~~~sql
SHOW PARAMETER db_block_checksum;
SHOW PARAMETER db_block_checking;
~~~

`DB_BLOCK_CHECKSUM` controls whether Oracle calculates and verifies block checksums per configuration. `DB_BLOCK_CHECKING` controls certain logical block checks as the database processes blocks. Levels and overhead depend on release, workload, and settings.

Do not alter these parameters in production merely because corruption was just detected. First review current values, Oracle recommendations for your release, CPU/I/O cost, and change control procedures. Checksums help detect certain corruption types; they do not guarantee catching every hardware fault or business-logic error.

## 24. Interpreting Validation Results

When RMAN validation finishes, read both the summary and detailed errors:

- Number of datafiles/backup pieces checked.
- Number of blocks read.
- Execution duration.
- Block corruption detected.
- Inaccessible or unreadable backup pieces.
- I/O, media manager, or encryption errors.
- Affected datafile/backup piece and block ranges.

An RMAN completion message without errors proves the selected scope passed the requested check type. It does not prove every backup in the repository is healthy or every PITR target has complete redo.

If corruption is found:

1. Stop deleting backups or running related cleanups.
2. Save RMAN output and the alert log.
3. Query the corruption views.
4. Identify the file, block range, and corruption type.
5. Determine whether the corruption is in the source datafile or the backup piece.
6. Check other backups and archived redo.
7. Choose block recovery, datafile restore/recovery, or another appropriate method.
8. Re-validate and test the application.
9. Investigate the underlying infrastructure root cause to prevent recurrence.

Never ignore corruption merely because applications have not reported errors yet. A block may sit untouched by current workloads and only fail later when a query or batch job reads it.

## 25. Common Mistakes

**Treating `RESTORE VALIDATE` as a real restore:** the command does not create restored datafiles or open the database. A separate restore drill is required.

**Treating `PREVIEW` as checking backup contents:** `PREVIEW` lists which backups RMAN plans to select; `VALIDATE` is required to read backup pieces.

**Treating `CROSSCHECK` as checking blocks:** `CROSSCHECK` mainly reconciles the repository with backup existence/accessibility; it does not read full contents like `VALIDATE`.

**Running only `VALIDATE DATABASE` without checking backups:** the source database may be clean while backup pieces are corrupted. Run `RESTORE VALIDATE` or `VALIDATE BACKUPSET` as well.

**Running only `RESTORE VALIDATE` without checking source datafiles:** backups may be readable while live source datafiles already have new corruption. Schedule `VALIDATE DATABASE` as well.

**Skipping `CHECK LOGICAL`:** some logical structural errors go undetected under physical-only checks. Schedule logical checks at an appropriate cadence.

**Assuming `CHECK LOGICAL` checks business data:** it checks block structure, not business rules.

**Failing to preserve the TDE wallet or backup encryption password:** datafiles/backups may be readable yet impossible to decrypt during recovery.

**Failing to verify archived redo:** datafile restore succeeds, yet recovery cannot reach the target SCN/time.

**Rehearsing on production paths:** risks overwriting live files. Use an isolated environment and separate target paths.

**Measuring only RMAN restore time:** RTO also includes startup, recovery, opening PDBs/services, verifying data, and bringing applications online.

**Not verifying after recovery:** an `OPEN` database does not mean applications are ready or data is accurate.

## 26. Sample Schedule and Operational Evidence

A recoverability assurance schedule might include:

| Activity | Purpose | Evidence to Retain |
|---|---|---|
| After every backup | Confirm backup job completed | RMAN log, tag, timestamp, backup location |
| Scheduled crosscheck | Detect missing/unreachable backups | `CROSSCHECK` output and expired list |
| Scheduled restore validate | Verify backups are readable for restore | RMAN log, selected backup pieces, result |
| Scheduled database validate | Detect corruption in source datafiles | RMAN output, before/after corruption views |
| Scheduled logical validate | Extra verification of logical block structure | `CHECK LOGICAL` output and resource usage |
| Scheduled restore drill | Prove real recovery workflow | Target SCN/time, restore/recover logs, smoke test, RTO/RPO |
| After infrastructure changes | Confirm backup/restore paths still work | Targeted validation and drill results |

For every check, record:

- DBID, `DB_UNIQUE_NAME`, database role, and release.
- Start/end times with timezone.
- Backup tag, backup set key, and device type.
- Target SCN/time if applicable.
- Channels and media manager configuration.
- RMAN output, warnings, and error stacks.
- Corruption list.
- RTO/RPO and smoke test results.
- Operator, reviewer, and change ticket.

RMAN logs can contain sensitive paths, hostnames, object names, and metadata. Protect access permissions and retention per organizational policy.

## 27. Sample Runbook: From Detecting a Corrupted Block to Verifying Recovery

Suppose RMAN validate detects a corrupted block in datafile 7:

**Step 1: Record the output and halt backup deletions**

Save RMAN output, timestamp, full error stack, and database state.

**Step 2: Check the corruption list**

~~~sql
SELECT file#,
       block#,
       blocks,
       corruption_change#,
       corruption_type
  FROM v$database_block_corruption
 WHERE file# = 7
 ORDER BY block#;
~~~

**Step 3: Identify the datafile and segment**

~~~sql
SELECT file#,
       name
  FROM v$datafile
 WHERE file# = 7;
~~~

If the block belongs to a segment, cross-check `DBA_EXTENTS` and related metadata.

**Step 4: Check available backups**

~~~text
RMAN> LIST BACKUP OF DATAFILE 7;
RMAN> RESTORE DATAFILE 7 PREVIEW;
RMAN> RESTORE DATAFILE 7 VALIDATE;
~~~

Confirm RMAN has valid, readable backups and verify required archived redo.

**Step 5: Choose the recovery method**

If the corruption is eligible for block media recovery and backups/redo exist:

~~~text
RMAN> RECOVER DATAFILE 7 BLOCK 12345;
~~~

If the file is lost or corruption is widespread, plan datafile or tablespace restore/recovery according to database state.

**Step 6: Re-validate**

~~~text
RMAN> VALIDATE DATAFILE 7 BLOCK 12345;
~~~

Re-check `V$DATABASE_BLOCK_CORRUPTION`, the alert log, and RMAN output.

**Step 7: Verify the application and root cause**

Run relevant queries, smoke tests, data reconciliation, and inspect storage/OS logs. If the root cause lies in a device or I/O path, resolve the infrastructure issue before closing the incident.

The commands above represent a workflow template, not a script to run verbatim in every database. Verify the exact block, backups, redo, corruption type, and file status before executing recovery.

## 28. Conclusion

`RESTORE DATABASE VALIDATE` checks the backups RMAN selects to restore a database and reads the required backup pieces without overwriting target datafiles. `RESTORE PREVIEW` shows which backups RMAN plans to use; `VALIDATE DATABASE` and `CHECK LOGICAL` inspect source database blocks; `VALIDATE BACKUPSET` checks a specific backup set; `CROSSCHECK` only reconciles the repository with backup presence/accessibility.

When block corruption is detected, inspect RMAN output, `V$DATABASE_BLOCK_CORRUPTION`, `V$BACKUP_CORRUPTION`, and `V$COPY_CORRUPTION` to determine the file, block range, and error type. Block media recovery can repair qualifying corruption when backups and redo exist, while widespread or unsupported corruption may require broader restore/recovery.

Finally, validation does not replace a restore drill. Rehearse in an isolated environment, verify the control file, SPFILE, datafiles, archived redo, TDE keystore, services, and PDBs, then open the database and run smoke tests. Measure RTO/RPO and retain evidence so you know your recovery process genuinely satisfies business requirements.
