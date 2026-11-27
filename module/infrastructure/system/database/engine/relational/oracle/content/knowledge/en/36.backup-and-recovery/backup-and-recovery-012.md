# Point-in-Time Recovery, RESETLOGS, and Database Incarnations

Point-in-time recovery (PITR) is the process of returning an Oracle Database to a selected point in time or System Change Number (SCN). This technique is commonly used when data is accidentally deleted, a batch job writes bulk erroneous data, an application deployment causes logical data corruption, or a database must be restored to a state prior to an incident.

In Oracle, whole-database PITR is usually performed with RMAN: select the target point, restore datafiles from appropriate backups, apply archived redo and incremental backups up to that point, and open the database with `RESETLOGS`. Opening with `RESETLOGS` creates a new redo branch, which Oracle calls a new **database incarnation**.

Three concepts must be understood together:

- **PITR:** determining which point the database must return to and recovering data to that point.
- **RESETLOGS:** opening the database after incomplete recovery or certain special recovery cases while initializing a new redo stream.
- **Database incarnation:** a branch of redo history defined by openings of the database with `RESETLOGS`.

PITR can discard committed transactions after the recovery point across the entire database. Therefore, selecting the right SCN/time and determining recovery scope is the most important decision before running any commands.

## 1. What Is PITR?

PITR brings the database to a consistent state at a point in the past. That point can be specified using:

- An SCN.
- A timestamp.
- A log sequence, in certain RMAN scenarios.
- A guaranteed restore point or normal restore point as a reference marker.

For example, an accidental deletion was committed at 10:15. If required backups and redo exist, the DBA can recover the database to an SCN immediately before that transaction. Valid changes committed after that SCN will also be absent from the database once PITR completes.

PITR is not a selective undo of one SQL statement. When performing whole-database point-in-time recovery, every datafile belonging to the database is returned to the same consistent point. This can affect multiple schemas and applications sharing the database.

### 1.1 Types of Point-in-Time Recovery

Oracle provides several point-in-time recovery options depending on scope:

| Type | Scope | Primary Impact |
|---|---|---|
| Database PITR (DBPITR) | Entire database | Returns the whole database to a point; requires `OPEN RESETLOGS` afterward |
| Tablespace PITR (TSPITR) | One or more tablespaces | Recovers tablespace via an auxiliary instance while the main database stays at present |
| PDB PITR | One pluggable database in a CDB | Recovers the PDB via multitenant procedures; do not blindly apply whole-CDB steps |
| Flashback Database | Entire database or supported scope | Uses flashback logs to rewind the database to a prior point |
| Flashback Table | One or more tables | Returns tables to an earlier state if conditions and undo allow |

DBPITR is appropriate when restoring a consistent state across the entire database. If only one table or one tablespace is affected, TSPITR, Flashback Table, RMAN `RECOVER TABLE`, or individual object recovery can minimize disruption to unrelated transactions.

PDB PITR has its own syntax and requirements for multitenant environments. Clearly distinguish whether you are recovering a CDB or a single PDB; never treat whole-database `ALTER DATABASE OPEN RESETLOGS` as the complete procedure for all PDB cases.

### 1.2 How Does PITR Differ from Complete Recovery?

**Complete recovery** applies all required redo to bring datafiles to the current state or the latest recoverable point, without intentionally stopping at a past marker.

**Incomplete recovery** stops before applying all available redo. PITR is a form of incomplete recovery when using RMAN restore/recover to a target time or SCN.

| Criterion | Complete Recovery | Incomplete Recovery / PITR |
|---|---|---|
| Goal | Recover to the present or latest point | Recover to a selected past point |
| Redo | Applies all required redo | Stops at the target |
| Transactions after target | Preserved if redo is valid | Excluded from the database state past the target |
| Opening the database | Usually no `RESETLOGS` unless special conditions apply | Usually requires `OPEN RESETLOGS` |
| Incarnation | Continues the current branch | Creates a new branch upon `OPEN RESETLOGS` |

If recovery uses a backup control file or performs incomplete recovery, the database normally requires `OPEN RESETLOGS`. Identify the exact recovery type and control file in use before choosing how to open the database.

## 2. SCN and Recovery Time

An SCN (System Change Number) is the logical sequential number Oracle uses to pinpoint changes in the database. An SCN is more precise than a timestamp when defining recovery boundaries.

### 2.1 Choosing a Target SCN

When the SCN before the offending transaction is known, recover using the target SCN:

~~~sql
SELECT current_scn
FROM v$database;
~~~

The query above only shows the current SCN at query time. During incident investigation, obtain the target SCN from reliable sources: application logs, audit records, LogMiner, transaction investigations, restore points, or recorded operational metrics.

For example, to stop recovery at SCN 987654321:

~~~rman
RUN {
  SET UNTIL SCN 987654321;
  RESTORE DATABASE;
  RECOVER DATABASE;
}
~~~

The target SCN acts as the recovery boundary. Check the exact `UNTIL SCN` semantics in the RMAN documentation for your running release and verify actual data around the boundary, especially when targeting a specific transaction. Never pick an arbitrary SCN merely because it looks close to the incident time.

### 2.2 Choosing a Target Time

RMAN also allows specifying a time:

~~~rman
RUN {
  SET UNTIL TIME
    "TO_DATE('2026-11-14 09:30:00','YYYY-MM-DD HH24:MI:SS')";
  RESTORE DATABASE;
  RECOVER DATABASE;
}
~~~

Using `TO_DATE` with an explicit format avoids dependence on `NLS_DATE_FORMAT`. Confirm the timezone of the incident and how timestamps are recorded by applications and the database. `DATE` carries no timezone, so align server clock, application clock, and investigator timezone.

When incidents occur around a tight window, timestamps may lack the precision to separate consecutive transactions. Whenever possible, find the corresponding SCN and use the SCN as the target.

### 2.3 Converting Between SCN and Timestamp

Oracle provides conversion functions:

~~~sql
SELECT SCN_TO_TIMESTAMP(987654321)
FROM dual;

SELECT TIMESTAMP_TO_SCN(
         TO_TIMESTAMP('2026-11-14 09:30:00',
                      'YYYY-MM-DD HH24:MI:SS')
       )
FROM dual;
~~~

These functions rely on an SCN/time mapping retained by Oracle for a limited time window. Do not assume the mapping exists indefinitely or offers absolute precision for arbitrarily old points. `TIMESTAMP_TO_SCN` may fail to find a mapping outside the retained range.

When recovering from historical events, prefer an SCN logged at the time of the event. If only a timestamp is available, use RMAN `SET UNTIL TIME` and verify the resulting state against real data.

### 2.4 Target Must Be Recoverable

To recover to a target, you need:

- Datafile backups old enough to start recovery from.
- Continuous archived redo logs from the backup to the target.
- Incremental backups if the strategy relies on incrementals.
- A control file or recovery catalog holding matching metadata.
- SPFILE/parameter file and password file as needed to start the instance.
- All relevant redo threads if the database runs on RAC.

If required archived redo is missing, the database cannot apply changes past that gap. The DBA may have to pick an earlier target, locate archived logs in another backup or storage source, or use a different recovery approach.

## 3. When Should PITR Be Used?

Typical scenarios:

- A user accidentally deletes or updates data and commits.
- A batch job runs with flawed logic and writes mass incorrect data.
- A deployment alters data in a way not reversible at the application level.
- A schema or dataset becomes logically corrupted and needs rebuilding to pre-incident state.
- A test environment needs restoring to a known baseline point.
- Creating a database copy as of a time prior to an event.

Not every data error warrants DBPITR. If only one table is affected, rolling the entire database back in time discards valid transactions from every other application.

Before choosing DBPITR, consider:

- Flashback Table if undo and prerequisites remain intact.
- Flashback Database if flashback logs cover the needed range.
- RMAN `RECOVER TABLE` to recover a table into an alternate schema or auxiliary database.
- Tablespace PITR if the error is confined to one tablespace and dependencies allow.
- Data Pump or a recovered clone to extract data and merge it back into the live database.
- Logical repair from application logs or controlled data sources.

## 4. Prerequisites and Preparation Before DBPITR

PITR has broad impact. Prepare both technical and business aspects beforehand.

### 4.1 Database in ARCHIVELOG Mode

Whole-database PITR relies on archived redo to apply changes from backup up to the target. Production databases normally require `ARCHIVELOG` mode and an archived log backup process.

Verify:

~~~sql
SELECT name, log_mode, open_mode, current_scn
FROM v$database;
~~~

If the database is in `NOARCHIVELOG`, recoverability relies heavily on offline or consistent backups. Never assume you can PITR to an arbitrary point in time without required redo.

### 4.2 Confirm Usable Backups

In RMAN:

~~~rman
LIST BACKUP SUMMARY;
LIST BACKUP OF DATABASE;
LIST BACKUP OF ARCHIVELOG ALL;
~~~

Use `RESTORE DATABASE PREVIEW` to inspect which backups RMAN plans to select for a restore scenario. `RESTORE ... VALIDATE` checks backup piece readability without overwriting target datafiles.

Example:

~~~rman
RESTORE DATABASE VALIDATE;
~~~

This command does not replace a full recovery drill. Backups can be readable while still missing archived logs, the control file, or other components needed for a specific target.

### 4.3 Inspect Archived Redo Logs

Query archived log metadata:

~~~sql
SELECT thread#,
       sequence#,
       first_change#,
       next_change#,
       resetlogs_change#,
       name,
       deleted,
       status
FROM v$archived_log
ORDER BY thread#, sequence#;
~~~

Verify redo continuity within each thread and the right incarnation. In RAC, each redo thread has its own sequence numbers. A gap in any active thread can prevent recovery to the target.

Multiple rows in `V$ARCHIVED_LOG` may represent multiple copies of the same sequence. Check `NAME`, `STATUS`, `DELETED`, backup metadata, and actual storage—do not simply count rows.

### 4.4 Preserve Current State

Before rewinding the database into the past, preserve a copy of the current state if possible:

- Back up the current database and archived redo.
- Record the `SQL_ID`/SCN, timestamp, and incident description.
- Save copies of the control file and SPFILE per procedure.
- Record configuration, incarnation, and datafile/tablespace inventory.
- If resources permit, stand up an auxiliary database to verify the target or extract data.

Preserving current state helps salvage valid transactions committed after the target if the business needs to merge them back. Never start DBPITR before deciding how post-target transactions will be handled.

### 4.5 Check Storage Space and Paths

RMAN needs enough space for restored datafiles, archived redo, backup pieces, and an auxiliary area if used. Check the FRA, ASM disk groups, filesystems, write permissions, filenames, and datafile mappings.

When using `SET NEWNAME`, `DB_FILE_NAME_CONVERT`, or `SWITCH DATAFILE ALL`, confirm new paths will not overwrite files belonging to another database.

## 5. Whole-Database PITR Workflow with RMAN

A common workflow follows these steps:

1. Select the target SCN or time.
2. Confirm required backups and redo.
3. Stop applications and the database.
4. Start the database in `MOUNT`.
5. Set the target via `SET UNTIL`.
6. Restore the database.
7. Recover the database to the target.
8. Open the database with `RESETLOGS`.
9. Verify the database and applications.
10. Take a fresh backup after `RESETLOGS`.

The example below assumes the current control file remains usable, valid backups exist, and archived redo is continuous.

### 5.1 Shut Down and Mount the Database

In SQL*Plus as `SYSDBA`:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
~~~

If the database is already mounted, do not restart it. Never allow applications to continue writing data during whole-database PITR.

### 5.2 Restore and Recover to SCN

Connect to RMAN:

~~~text
rman target /
~~~

Run:

~~~rman
RUN {
  SET UNTIL SCN 987654321;
  RESTORE DATABASE;
  RECOVER DATABASE;
}
~~~

`SET UNTIL` must appear before `RESTORE` so RMAN selects backups compatible with the target, and then applies the same boundary to recovery inside the `RUN` block.

RMAN restores datafiles from backup and applies incrementals/archived redo using available repository records and backup sources. RMAN messages show which backup pieces and archived logs are used.

If using a target time, replace `SET UNTIL SCN` with `SET UNTIL TIME` using an explicit time expression.

### 5.3 Open RESETLOGS

Once recovery finishes to the target, exit RMAN and open the database:

~~~sql
ALTER DATABASE OPEN RESETLOGS;
~~~

After incomplete recovery, `OPEN RESETLOGS` creates a new redo branch. The database does not continue writing redo on the old branch.

If recovery used a backup control file, `RESETLOGS` is also normally required. Always verify control file state and recovery type before opening.

### 5.4 Post-Open Verification

~~~sql
SELECT name,
       open_mode,
       log_mode,
       resetlogs_change#,
       resetlogs_time,
       current_scn
FROM v$database;
~~~

Check datafiles:

~~~sql
SELECT file#,
       name,
       status,
       checkpoint_change#
FROM v$datafile
ORDER BY file#;
~~~

Check tablespaces:

~~~sql
SELECT tablespace_name,
       status,
       contents
FROM dba_tablespaces
ORDER BY tablespace_name;
~~~

Beyond database state, verify invalid objects, jobs, sequences, application services, privileges, database links, and business data at the chosen point. An `OPEN` database does not by itself prove applications are ready.

## 6. Time-Based PITR Example

Suppose a batch job misfired at 09:30 and committed widespread changes. Investigation determines data must be kept up to just before 09:30:00.

After confirming backups and archived logs, the DBA executes:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
~~~

RMAN:

~~~rman
RUN {
  SET UNTIL TIME
    "TO_DATE('2026-11-14 09:29:59','YYYY-MM-DD HH24:MI:SS')";
  RESTORE DATABASE;
  RECOVER DATABASE;
}
~~~

Open the database:

~~~sql
ALTER DATABASE OPEN RESETLOGS;
~~~

The timestamp in the example is illustrative. In practice, verify timezone and transaction boundaries. If the batch committed multiple times, `09:29:59` may be too coarse to isolate exact transactions to exclude. An SCN from LogMiner, auditing, or application logs usually provides a sharper target.

### 6.1 Post-Recovery Data Validation

Do not check only that deleted rows reappeared. Verify valid transactions right before the target and confirm transactions after the target were excluded as intended.

Run business reconciliation queries:

- Order counts by status.
- Monetary totals by day or business unit.
- Transaction counts across time windows.
- Foreign keys and cross-table integrity.
- Records touched by the batch/job.
- Data synchronized to external systems.

In particular, database PITR does not automatically rewind external systems such as message queues, caches, exported files, sent reports, or transactions in other databases. Plan synchronization or compensating actions for integrated systems.

## 7. PITR When the Control File Is Lost

If the current control file is lost, restore the control file from backup or autobackup before mounting and recovering. This is a disaster recovery scenario with additional steps beyond the current-control-file example.

General workflow:

1. Identify the database DBID.
2. Start the instance in `NOMOUNT` with a suitable SPFILE/PFILE.
3. Configure autobackup location if needed.
4. Restore the control file from autobackup.
5. Mount the database.
6. Set the target and restore/recover datafiles.
7. Open `RESETLOGS`.

Example RMAN command structure:

~~~rman
rman target /

SET DBID 1234567890;

STARTUP NOMOUNT;

RESTORE CONTROLFILE FROM AUTOBACKUP;

ALTER DATABASE MOUNT;

RUN {
  SET UNTIL SCN 987654321;
  RESTORE DATABASE;
  RECOVER DATABASE;
}
~~~

Then in SQL*Plus:

~~~sql
ALTER DATABASE OPEN RESETLOGS;
~~~

This is an illustrative framework, not a verbatim runbook for every system. When the control file is lost, verify autobackup format, DBID, backup location, channel configuration, SPFILE, ASM, and permissions. If RMAN cannot locate the autobackup automatically, specify the format or exact handle.

When using a backup control file, metadata for newer backups/archived logs may be absent from the restored control file. A recovery catalog or cataloging backup pieces and archived logs may be needed so RMAN finds the full redo chain.

## 8. Why Is OPEN RESETLOGS Required?

After incomplete recovery, the database lacks all redo needed to continue the old branch to the present. `OPEN RESETLOGS` establishes a new starting point for redo.

When opening with `RESETLOGS`, Oracle:

- Starts a new redo stream.
- Resets log sequence numbering for the new branch.
- Records the resetlogs SCN and resetlogs timestamp.
- Creates a new database incarnation.
- Preserves parent-incarnation links in metadata so RMAN can manage recovery history.

`RESETLOGS` does not change the DBID in normal operations. The DBID identifies the database; an incarnation identifies one branch of redo history for that database. Never confuse a new incarnation with creating an entirely new database.

### 8.1 RESETLOGS Does Not Wipe All Data

The command name can mislead newcomers into thinking Oracle wipes redo or data. In reality, `RESETLOGS` opens the database after recovery using new redo rules. Datafiles retain the recovered state as of the target; Oracle initializes redo logs so the database can continue operating on the new branch.

Never run `RESETLOGS` just to see whether a database will open. It is a major boundary in recovery history. Only open once restore/recovery has finished and database state is verified.

### 8.2 When Is RESETLOGS Required?

Cases that normally require `OPEN RESETLOGS`:

- Incomplete recovery, including DBPITR.
- Recovery using a backup control file.
- Certain Flashback Database workflows into the past.
- Special recovery scenarios explicitly requiring resetlogs per Oracle.

Complete recovery with a current control file normally opens the database regularly without `RESETLOGS`. Never apply `RESETLOGS` blindly to every recovery.

## 9. What Is a Database Incarnation?

A database incarnation is a branch of redo history starting at an `OPEN RESETLOGS`. Each incarnation has:

- An incarnation number.
- A resetlogs SCN.
- A resetlogs timestamp.
- A link to the preceding incarnation (parent/ancestor).
- Its own redo branch following the resetlogs point.

Visualize database history as a tree:

~~~text
Incarnation 1
    |
    | OPEN RESETLOGS at SCN 5000
    v
Incarnation 2
    |
    | OPEN RESETLOGS at SCN 8200
    v
Incarnation 3
~~~

For example, the database runs in incarnation 1 up to SCN 5000. The DBA performs PITR back to SCN 4500 and opens `RESETLOGS`. From there, incarnation 2 begins. Changes generated after SCN 4500 in incarnation 1 do not belong to incarnation 2's new redo branch.

If later incarnation 2 is recovered back to SCN 7000 and opened with `RESETLOGS`, incarnation 3 is created. Incarnations 1 and 2 remain ancestors in history, while the database currently runs on branch 3.

### 9.1 Viewing the Current Incarnation

In SQL:

~~~sql
SELECT incarnation#,
       resetlogs_change#,
       resetlogs_time,
       prior_incarnation#,
       status
FROM v$database_incarnation
ORDER BY incarnation#;
~~~

In RMAN:

~~~rman
LIST INCARNATION OF DATABASE;
~~~

RMAN typically marks the active incarnation as `CURRENT`. Other incarnations may show `PARENT` or `ORPHAN` depending on ancestry and repository state.

Verify displayed columns and status values against your release. When identifying a branch, compare incarnation numbers with resetlogs SCN/time rather than relying on sequence order alone.

### 9.2 DBID and Incarnation Are Different

| Attribute | DBID | Incarnation |
|---|---|---|
| Purpose | Identifies the database | Identifies a redo branch |
| Changes on `OPEN RESETLOGS`? | Normally no | Yes, creates a new incarnation |
| Role in RMAN | Identifies repository/database | Selects history branch during restore/recover |
| Scope | Database identity | One branch within database history |

DBID can change during operations such as `NID` to change database identity, though that is a separate operation and not a normal consequence of `RESETLOGS`.

## 10. How Does RMAN Manage Incarnations?

RMAN stores incarnation relationships in the control file or recovery catalog. This enables RMAN to identify which branch each backup and archived redo log belongs to.

Common commands:

~~~rman
LIST INCARNATION OF DATABASE;
LIST BACKUP SUMMARY;
LIST BACKUP OF DATABASE;
LIST ARCHIVELOG ALL;
~~~

When the database opens with `RESETLOGS`, RMAN registers the new incarnation. Older backups do not automatically become useless. RMAN can use backups from a parent incarnation as long as they are valid ancestors of the recovery branch and the redo chain matches.

However, do not assume every archived log or backup from an old branch applies to a new branch. Beyond a `RESETLOGS` point, redo from parallel branches cannot be mixed arbitrarily. Rely on incarnation metadata and RMAN to select the valid chain.

### 10.1 Switching RMAN to a Parent Incarnation

If you need to recover to a point located in an earlier incarnation, RMAN may need its recovery context switched to that incarnation:

~~~rman
LIST INCARNATION OF DATABASE;

RESET DATABASE TO INCARNATION 2;
~~~

In the example, `2` is an incarnation number taken from `LIST` output, not a fixed constant across databases.

This command changes the incarnation RMAN uses as context for restore/recover operations. It is not an arbitrary command to switch an open database to another branch; run it inside a proper recovery workflow, typically with the database mounted and a control file/recovery catalog containing the incarnation tree.

After selecting the right incarnation, set the target SCN/time within that branch, restore/recover using the matching backups and redo, and open `RESETLOGS` if required by the workflow. Upon opening, a new incarnation may be created off the selected branch.

### 10.2 When Is RESET DATABASE TO INCARNATION Needed?

Common situations:

- After opening `RESETLOGS` following PITR, realizing you must return to a point prior to that `RESETLOGS`.
- Restoring an ancestor branch to retrieve an earlier state or dataset.
- Directing RMAN to recognize backups and archived logs from an older branch when the target precedes the current incarnation's resetlogs SCN.

Never use this command as a generic fix for unrelated backup errors. First confirm which branch contains the target and whether backups/redo for that branch remain intact.

### 10.3 ORPHAN Incarnations

An incarnation may be shown as `ORPHAN` when it no longer lies on the active path selected by RMAN—for example, after subsequent resetlogs created a different branch. `ORPHAN` does not mean backups from that incarnation were deleted or are definitely unusable.

RMAN can still recover from an ancestor/old branch if you select the right incarnation and sufficient backups/redo exist. Inspect resetlogs SCN/time relationships and test exact restore/recover feasibility.

## 11. Backing Up After RESETLOGS

After `OPEN RESETLOGS` succeeds, take a fresh backup of the database and archived redo per operational policy.

Reasons:

- The database is now running on a new incarnation.
- A fresh backup establishes a clear recovery baseline for the new branch.
- Reduces reliance on stitching together backups/redo from older branches.
- Simplifies subsequent disaster recovery procedures.
- Provides proof that post-recovery backups are readable and usable.

Example:

~~~rman
BACKUP DATABASE PLUS ARCHIVELOG;
~~~

Depending on policy, also back up the control file and SPFILE explicitly or verify autobackup:

~~~rman
CONFIGURE CONTROLFILE AUTOBACKUP ON;
~~~

Check current configuration:

~~~rman
SHOW ALL;
~~~

Some systems use backup optimization, compression, encryption, SBT, or media managers. Confirm post-`RESETLOGS` backups register in the right repository and that retention policies do not prematurely delete needed backups.

After backing up, verify:

~~~rman
LIST BACKUP SUMMARY;
RESTORE DATABASE VALIDATE;
~~~

`RESTORE ... VALIDATE` checks backup readability, though periodic recovery rehearsals remain necessary to prove the full workflow works.

## 12. PITR and Flashback Database

Flashback Database is a mechanism that rewinds the database to a prior point using flashback logs. It can be faster than restoring all datafiles and applying archived redo from backups when sufficient flashback logs cover the target.

Command structure example:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;

FLASHBACK DATABASE TO SCN 987654321;

ALTER DATABASE OPEN RESETLOGS;
~~~

Or:

~~~sql
FLASHBACK DATABASE TO TIMESTAMP
  TO_TIMESTAMP('2026-11-14 09:30:00',
               'YYYY-MM-DD HH24:MI:SS');
~~~

Exact syntax and database states must follow your Oracle release documentation. Flashback Database normally runs while the database is in `MOUNT`. After flashing back to the past, the database opens with `RESETLOGS` to start a new redo branch.

### 12.1 Flashback Logs and the Fast Recovery Area

Flashback Database must be enabled with adequate flashback logs. Verify:

~~~sql
SELECT flashback_on
FROM v$database;

SELECT name,
       space_limit,
       space_used,
       space_reclaimable
FROM v$recovery_file_dest;
~~~

`DB_FLASHBACK_RETENTION_TARGET` sets a retention target, not a guarantee that every past time has flashback logs. FRA capacity, workload, archived logs, and guaranteed restore points all affect flashback log retention.

### 12.2 Guaranteed Restore Points

A guaranteed restore point ensures Oracle retains enough flashback logs to flash back the database to that marker, provided the FRA has sufficient space and proper configuration.

Create a restore point:

~~~sql
CREATE RESTORE POINT BEFORE_RELEASE GUARANTEE FLASHBACK DATABASE;
~~~

View restore points:

~~~sql
SELECT name,
       scn,
       time,
       guarantee_flashback_database
FROM v$restore_point;
~~~

Once no longer needed, drop the restore point:

~~~sql
DROP RESTORE POINT BEFORE_RELEASE;
~~~

Guaranteed restore points retain flashback logs and can fill the FRA quickly. Monitor capacity, enforce expiration limits, and drop them once their purpose is complete. They do not replace RMAN backups.

### 12.3 Comparing Flashback Database and RMAN DBPITR

| Criterion | Flashback Database | RMAN DBPITR |
|---|---|---|
| Mechanism | Applies flashback logs to reverse changes | Restores backups and applies redo up to target |
| Prerequisites | Flashback Database enabled and logs intact | Backups and continuous archived redo |
| Duration | Often fast for recent targets with logs available | Can take long when restoring many datafiles |
| Scope | Whole database | Whole database |
| `RESETLOGS` | Normally needed after flashing back to the past | Required after incomplete recovery |
| Role of backups | Does not replace backups | Relies directly on backups and redo |

If flashback logs are insufficient or datafiles suffered severe loss, RMAN restore/recover remains the primary path. Maintain both backups and flashback per RPO/RTO needs.

## 13. PITR and TSPITR: Avoiding Overly Broad Recovery

Tablespace Point-in-Time Recovery returns one or more tablespaces to a past point in time while the rest of the database stays at the present.

RMAN normally uses an auxiliary instance to recover the tablespace to the target and then integrates the recovered datafiles back into the primary database. This requires an auxiliary destination, extra disk space, and verifying cross-tablespace dependencies.

Command structure example:

~~~rman
RECOVER TABLESPACE users
  UNTIL SCN 987654321
  AUXILIARY DESTINATION '/u02/aux';
~~~

Syntax and restrictions depend on Oracle release. TSPITR is not always viable if objects span multiple tablespaces via dependencies, foreign keys, partitioning, or linked structures. Check self-containment and tablespace recovery prerequisites beforehand.

If only a single table is needed, consider RMAN `RECOVER TABLE` or recovering into an auxiliary database and extracting the rows. The chosen method must balance blast radius against the effort of merging valid post-target changes.

## 14. PITR in CDB/PDB Environments

In multitenant architecture, determine whether the scope is:

- The entire CDB.
- A single PDB.
- A tablespace inside a PDB.
- A table inside a PDB.

CDB PITR affects the entire container database and all PDBs within scope. PDB PITR can recover a single PDB independently per release capabilities and procedures, avoiding rewinding other PDBs.

Before running recovery, verify:

~~~sql
SHOW CON_NAME;

SELECT con_id,
       name,
       open_mode
FROM v$pdbs
ORDER BY con_id;
~~~

For a PDB, verify backups/archived redo, auxiliary requirements, PDB status, common/local users, services, and external dependencies. Recovery and `OPEN RESETLOGS` commands at the PDB level differ from whole-CDB DBPITR. Never copy whole-database examples verbatim for a PDB without checking your exact release documentation.

## 15. Handling Missing Archived Redo Logs

A common failure occurs when RMAN requests an archived log that cannot be found.

The message usually specifies the required sequence or SCN. Check:

- Does the log exist in the FRA or another archive destination?
- Does a backup of that archived log exist?
- Can the media manager/SBT restore the log?
- Does the log exist on another RAC instance or external storage?
- Does the log belong to the right thread and incarnation?
- Did filenames or archive destinations change?
- Do the recovery catalog and control file hold matching metadata?

Never fabricate a dummy file or rename a different archive log to fill a gap. Archived redo carries its own header, sequence, and SCN; the wrong file cannot substitute for a missing log.

If the required log cannot be obtained, choose a target earlier than the missing redo or use an alternate backup/recovery source. A database can only open consistently at a point where all relevant datafiles recover compatibly.

## 16. Common Operational Errors and Troubleshooting Reasoning

| Symptom | Investigation Path |
|---|---|
| RMAN reports missing archived log | Identify thread, sequence, SCN, incarnation, and locate backup/archive copies |
| Cannot restore backup piece | Check permissions, media manager, paths, encryption wallet, and backup integrity |
| Database asks for media recovery on open | Check datafile checkpoints and missing redo |
| `OPEN RESETLOGS` rejected | Confirm recovery finished, database is in the right state, and control file matches |
| Database opens but application fails | Check objects, jobs, sequences, services, external systems, and target data |
| RMAN selects unexpected backup | Confirm `SET UNTIL` precedes `RESTORE`, check incarnation, tags, and repository |
| Cannot find old incarnation | Check control file/recovery catalog and incarnation metadata |
| Flashback Database cannot reach target | Check flashback logs, retention, FRA, and restore points |
| Duplicate archive sequences or multiple copies | Inspect thread, resetlogs ID, SCN range, status, and physical files |

Never troubleshoot errors by blindly re-running the same command without reading RMAN/Oracle messages. Save full RMAN logs and the alert log to pinpoint how far recovery progressed.

## 17. Preserving Post-Target Transactions

Whole-database PITR discards changes after the target from the recovered database. Some of those changes may be valid transactions unrelated to the incident.

Example:

- 09:00: user creates a valid order.
- 09:30: faulty batch updates wrong data.
- 09:45: user pays for a different order.
- 10:00: DBA recovers the database back to 09:29:59.

After PITR, transactions from 09:30 onward are absent from the database, including the valid 09:45 payment. Without a plan, the application loses valid business data outside the incident scope.

A common strategy:

1. Preserve the current database or back up the current state.
2. Recover the primary back to the target in a controlled environment.
3. Identify valid transactions committed after the target.
4. Extract needed rows from the preserved current database or application logs.
5. Check primary key conflicts, sequences, foreign keys, and business ordering.
6. Selectively merge valid data into the recovered database.
7. Reconcile with external systems before re-enabling traffic.

Never copy all post-target data mechanically. Distinguish faulty transactions, transactions dependent on faulty ones, and independent valid transactions.

## 18. Recovery Testing and Rehearsals

Backups only have value when restore/recovery capability is proven. Organizations should rehearse PITR in an environment isolated from production.

A drill may include:

- Creating test data and recording the SCN.
- Backing up the database and archived redo.
- Making a reversible change in the test environment.
- Selecting a target prior to the change.
- Restoring/recovering to the target.
- Opening `RESETLOGS`.
- Verifying data, objects, and applications.
- Checking the new incarnation in `V$DATABASE_INCARNATION`.
- Taking a fresh backup after `RESETLOGS`.
- Timing every step to evaluate RTO.

Measure both RPO and RTO:

- **RPO (Recovery Point Objective):** maximum data loss accepted by the business, usually expressed in time or transaction point.
- **RTO (Recovery Time Objective):** target time to restore service operation.

An accurate PITR process that takes too many hours may fail RTO. Conversely, recovering quickly to the wrong target can violate RPO and discard valid transactions.

## 19. Pre-, During-, and Post-PITR Checklist

### Before Recovery

- [ ] Confirmed exact DBID, database, CDB/PDB, and current incarnation.
- [ ] Determined target SCN/time and timezone.
- [ ] Identified transactions or events to exclude.
- [ ] Confirmed database is `ARCHIVELOG` with valid backups.
- [ ] Confirmed continuous archived redo across all required threads.
- [ ] Checked control file, SPFILE, password file, and recovery catalog.
- [ ] Preserved current state and post-target transactions if needed.
- [ ] Verified disk space for datafiles, FRA, auxiliary destination, and backup storage.
- [ ] Defined downtime, RPO/RTO, and application communication plan.

### During Recovery

- [ ] Stopped application writes.
- [ ] Started the database in `MOUNT` properly.
- [ ] Placed `SET UNTIL` before `RESTORE` inside the `RUN` block.
- [ ] Monitored every datafile and archived log restored/applied.
- [ ] Confirmed recovery stopped at the intended target.
- [ ] Saved RMAN output and alert log.
- [ ] Executed `OPEN RESETLOGS` only after recovery finished and state was verified.

### After Recovery

- [ ] Verified `OPEN_MODE` and `RESETLOGS_CHANGE#`/`TIME`.
- [ ] Verified the new incarnation.
- [ ] Checked datafiles, tablespaces, and invalid objects.
- [ ] Reconciled business data and transaction boundaries.
- [ ] Checked sequences, scheduler jobs, services, and external systems.
- [ ] Backed up the database and archived redo on the new incarnation.
- [ ] Scheduled backup validation and restore drills.
- [ ] Archived incident records, target, backups, incarnation, and outcomes.

## 20. Conclusion

Point-in-time recovery returns a database to a chosen SCN or point in time by restoring backups and applying redo up to the target. For whole-database incomplete recovery, Oracle normally requires opening with `RESETLOGS`. This creates a new redo branch and a new database incarnation while normally preserving the DBID.

RMAN tracks relationships across incarnations so recovery can operate on the current branch or an ancestor branch when sufficient backups and redo exist. After `RESETLOGS`, take a fresh backup on the new branch and verify recoverability. Before executing PITR, verify the exact target, preserve current state, evaluate post-target transactions, and choose the narrowest recovery scope that meets recovery goals.
