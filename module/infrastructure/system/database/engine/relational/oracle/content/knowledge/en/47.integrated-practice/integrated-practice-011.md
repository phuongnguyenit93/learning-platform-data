# Rehearsing Accidental Deletion, Datafile Loss, and Choosing a Recovery Strategy

An accidental deletion incident in Oracle Database can take the form of a committed `DELETE`, a `TRUNCATE`, a `DROP TABLE`, a `DROP TABLESPACE`, or a datafile missing from storage. These scenarios cannot be resolved with a single command. One case needs only Flashback Table; another uses the recycle bin; another requires RMAN restore and recovery; and another requires recovering an entire database or tablespace to a point in time before the mistake.

The goal of this hands-on drill is to help DBAs accurately identify the blast radius, preserve evidence, choose a method aligned with RPO and RTO, execute recovery in the proper database state, and validate data afterward. All destructive simulations must run on an isolated lab or clone—never test by deleting real files in production.

## 1. Mental Model When an Incident Occurs

### 1.1. Identifying What Changed

Before running recovery, confirm the exact operation that caused data loss:

| Incident | Impact | Typical Options to Evaluate |
|---|---|---|
| Uncommitted `DELETE` | DML still inside open transaction | `ROLLBACK` transaction |
| Committed `DELETE` | Partial or total row loss | Flashback Table/Query, RMAN table recovery, PITR |
| `TRUNCATE TABLE` | Table data removed by DDL | RMAN `RECOVER TABLE`, Flashback Database, PITR |
| `DROP TABLE` | Object dropped | Flashback Drop from recycle bin, RMAN table recovery |
| `DROP TABLE PURGE` | Object bypassed/purged from recycle bin | RMAN table recovery or PITR |
| `DROP TABLESPACE` | Tablespace metadata and possibly datafiles removed | TSPITR, database PITR, restore/recover |
| Single datafile lost | Physical file inaccessible | RMAN `RESTORE DATAFILE` and `RECOVER DATAFILE` |
| `SYSTEM`/`UNDO` datafile lost | Database may fail to open or operate | Mount-level database recovery per requirements |
| Multiple datafiles/database lost | Broad physical recovery scope | RMAN database restore/recovery, Data Guard, or DR |
| Block corruption | One or more physical blocks damaged | RMAN block media recovery or datafile recovery |

Relying on what a user remembers running is not enough. Verify the actual statement, whether the transaction committed, which objects were impacted, whether the database is in `ARCHIVELOG` or `NOARCHIVELOG` mode, and which backups and redo logs are available.

### 1.2. Distinguishing Logical Loss from Physical Loss

- **Logical loss:** rows or objects were removed via SQL while datafiles remain intact and the database stays readable. Flashback or the recycle bin may fit.
- **Physical loss:** a datafile was deleted, a volume failed to mount, storage failed, or blocks are unreadable. Requires media recovery from backups and redo.
- **Database-wide logical error:** valid SQL damaged data broadly, such as an unfiltered `DELETE` or `DROP TABLESPACE`. May require point-in-time recovery before the error.
- **Infrastructure failure:** host, storage, network, or instance failed. Determine whether database files and redo remain consistent.

Never try Flashback Table instead of RMAN when a physical file is missing; conversely, do not restore an entire database just to recover one table if a safer table recovery option exists.

### 1.3. Recovery Always Has a Target Point in Time

Every recovery plan must answer:

- When was the last point at which data was definitely valid?
- Can an exact SCN or timestamp be identified?
- Which backup covers that target point?
- Are archived redo logs contiguous up to the recovery target?
- Were valid transactions committed after that point that must be retained?
- Does the RPO tolerate losing those subsequent transactions?

Until the target point is confirmed, do not reopen traffic or discard existing copies.

## 2. Before Executing Recovery

### 2.1. Halt Changes That Could Worsen the Situation

Upon detecting an accidental deletion or missing datafile:

1. Declare the incident and record the detection timestamp.
2. Pause related batch jobs or write traffic if needed.
3. Stop running additional DDL/DML on affected objects.
4. Never drop/recreate tablespaces or datafiles to mask errors.
5. Never delete backups, archived logs, flashback logs, or trace files.
6. Preserve SQL text, application logs, audit trails, and session details.
7. Identify who approves recovery and the acceptable downtime window.

If applications keep writing to related tables, identifying which rows to keep versus restore becomes significantly harder.

### 2.2. Record Database Identity and State

§§§sql
SELECT dbid,
       name,
       db_unique_name,
       database_role,
       open_mode,
       log_mode,
       flashback_on,
       current_scn
FROM v$database;

SELECT instance_name,
       host_name,
       status,
       database_status,
       startup_time
FROM v$instance;

SELECT name, value
FROM v$parameter
WHERE name IN (
    'compatible',
    'db_recovery_file_dest',
    'db_recovery_file_dest_size',
    'db_flashback_retention_target'
);
§§§

Save outputs with timestamps and timezones. In RAC, query `GV$` views to capture all instances where needed.

### 2.3. Check ARCHIVELOG Mode and Backups

§§§sql
ARCHIVE LOG LIST;

SELECT log_mode,
       open_mode,
       database_role
FROM v$database;
§§§

In RMAN:
§§§text
RMAN> SHOW ALL;
RMAN> REPORT SCHEMA;
RMAN> LIST BACKUP SUMMARY;
RMAN> LIST BACKUP OF DATABASE;
RMAN> LIST BACKUP OF ARCHIVELOG ALL;
§§§

Confirm backup pieces are readable, control file/SPFILE backups exist, archived logs have no gaps, and the TDE wallet/keystore is available. A successful backup job report does not replace restore validation or restore rehearsals.

### 2.4. Record the SCN and Incident Timestamp

Fetch the current SCN to record the present state:
§§§sql
SELECT current_scn
FROM v$database;
§§§

If audit logs or application logs record the timestamp of the mistake, convert it to a standard timezone and pinpoint the closest SCN prior to the mistake. You can use LogMiner, audit trails, or Flashback Transaction Query if configured and within retention.

Never borrow an SCN from another database to infer an SCN on this database. An SCN is strictly internal to a single database.

### 2.5. Inspect the Fast Recovery Area

§§§sql
SELECT name,
       space_limit,
       space_used,
       space_reclaimable,
       number_of_files
FROM v$recovery_file_dest;
§§§

The FRA can store flashback logs, archived redo logs, and backups. Running low on FRA space can jeopardize flashback windows or archiving. Never delete files inside the FRA via OS commands; use RMAN and proper retention policies.

## 3. Recovering DROP TABLE Using the Recycle Bin

### 3.1. How Does the Recycle Bin Work?

When the recycle bin is enabled and the object type is supported, a standard `DROP TABLE` renames the object to a `BIN$` name and retains it for flashback. It is not an independent backup; the object remains recoverable only until purged or reclaimed under space pressure.

Check status:
§§§sql
SHOW PARAMETER recyclebin;

SELECT original_name,
       object_name,
       type,
       droptime,
       dropscn
FROM user_recyclebin
ORDER BY droptime DESC;
§§§

DBAs can query `DBA_RECYCLEBIN` if authorized. Exact column names and visibility depend on the view and Oracle release.

### 3.2. Restoring the Table to Before Drop

Example:
§§§sql
FLASHBACK TABLE APP.ORDERS
TO BEFORE DROP;
§§§

If the name `ORDERS` has already been reused, rename the restored object:
§§§sql
FLASHBACK TABLE APP.ORDERS
TO BEFORE DROP
RENAME TO ORDERS_RECOVERED;
§§§

Then verify the object:
§§§sql
SELECT owner, table_name, status
FROM dba_tables
WHERE owner = 'APP'
  AND table_name IN ('ORDERS', 'ORDERS_RECOVERED');
§§§

If multiple versions with the same original name exist in the recycle bin, pick the exact one by drop time or object name. You can specify the exact `BIN$` object name when targeting a specific drop event.

### 3.3. Limitations of Flashback Drop

Flashback Drop does not apply to every object or scenario. Cases where it typically cannot be used include:
- `DROP TABLE PURGE`.
- Objects removed via `PURGE RECYCLEBIN` or reclaimed due to space pressure.
- Recycle bin disabled at the time of the drop.
- Object types unsupported by the recycle bin.
- Dependent objects or schema features with specific restrictions.

If the table is gone from the recycle bin, switch to RMAN table recovery, PITR, or an appropriate backup copy.

### 3.4. Verifying Dependent Objects After Flashback

Do not check only the table name. Verify:
- Data and row counts.
- Indexes and index statuses.
- Constraints and `ENABLED`/`VALIDATED` status.
- Triggers.
- Grants.
- Synonyms.
- Dependent views and packages.
- Sequences or identity columns if auto-generated keys are used.

A table returning via flashback does not guarantee every dependent consumer works automatically. Run application tests before reopening traffic.

## 4. Recovering a Committed DELETE

### 4.1. If the Transaction Has Not Committed

If the `DELETE` remains inside an uncommitted transaction and the session is still alive, simply run `ROLLBACK`:
§§§sql
ROLLBACK;
§§§

This is the simplest case. If the application connection dropped, never guess the transaction outcome solely because the client saw an error. The database may have committed or rolled back; inspect transaction/business records before acting.

### 4.2. Flashback Table to an SCN or Timestamp

Flashback Table restores an entire table to a prior point if sufficient undo exists and the object meets prerequisites. Example:
§§§sql
ALTER TABLE APP.ORDERS ENABLE ROW MOVEMENT;

FLASHBACK TABLE APP.ORDERS
TO TIMESTAMP (SYSTIMESTAMP - INTERVAL '10' MINUTE);
§§§

Or using an SCN:
§§§sql
FLASHBACK TABLE APP.ORDERS
TO SCN 123456789;
§§§

Replace the example point with the investigated SCN or timestamp. Requires appropriate privileges, sufficient undo, and checking Flashback Table limits for your release.

### 4.3. Watch Out for Valid Transactions After That Point

Flashback Table rolls the entire table back to the target point. If valid transactions occurred afterward that must be kept, flashing back the whole table wipes them out.

When only a subset of rows was deleted accidentally, consider Flashback Query to read old rows and selectively restore them into the current table. Never replace the whole table without a plan to reconcile post-target changes.

### 4.4. Using Flashback Query to Extract Historical Data

Example creating a copy of rows as of an SCN prior to `DELETE`:
§§§sql
CREATE TABLE APP.ORDERS_RECOVERY AS
SELECT *
FROM APP.ORDERS AS OF SCN 123456789;
§§§

Then compare the snapshot against the live table by primary key, isolate the exact rows to restore, and reinsert them per business rules. Never blindly `INSERT` the entire snapshot back if doing so causes duplicates or overwrites valid updates.

Flashback Query depends on undo still retaining the required blocks. `UNDO_RETENTION` is a retention target, not an absolute guarantee without retention guarantee and adequate space. It can hit `ORA-01555` snapshot too old.

### 4.5. Flashback Transaction Query

If you need to identify which transaction deleted rows, inspect flashback transaction views when supplemental logging/undo and required privileges are configured:
§§§sql
SELECT xid,
       start_scn,
       commit_scn,
       logon_user,
       operation,
       table_name,
       undo_sql
FROM flashback_transaction_query
WHERE table_owner = 'APP'
  AND table_name = 'ORDERS'
ORDER BY commit_scn DESC;
§§§

Available views and details depend on configuration, privileges, and undo retention. `UNDO_SQL` is an investigative aid; never blindly execute bulk generated SQL without review.

## 5. Recovering TRUNCATE TABLE

### 5.1. Why Is TRUNCATE Different from DELETE?

`TRUNCATE` is DDL and does not generate row-by-row undo like a standard `DELETE`. It deallocates or reuses segment extents per Oracle semantics and performs an implicit commit. Therefore, `ROLLBACK` cannot undo a truncate.

### 5.2. Flashback Table Is Not the Default Solution for TRUNCATE

Never assume Flashback Table can rewind across arbitrary DDL. `TRUNCATE` alters segment metadata/extents and typically falls outside direct Flashback Table recovery. Check your specific release and operation; for standard drills, use RMAN `RECOVER TABLE`, Flashback Database, or PITR.

### 5.3. RMAN RECOVER TABLE

In supported releases, RMAN can recover a table or table partition to a point in time by spinning up an auxiliary database and using Data Pump to import the recovered object back into the target database.

Illustrative syntax:
§§§text
RMAN> RECOVER TABLE APP.ORDERS
      UNTIL TIME "TO_DATE('2026-11-14 10:15:00',
                          'YYYY-MM-DD HH24:MI:SS')"
      AUXILIARY DESTINATION '/u02/rman_aux';
§§§

Exact syntax, prerequisites, and supported features depend on Oracle release, object type, and configuration. Check the Recovery Manager Reference for your version. You need backups and archived redo covering the target time, disk space for the auxiliary instance, and required privileges.

If the current table still exists, use `REMAP TABLE` or a new target name per release syntax to avoid overwriting the live object. After import, verify indexes, constraints, triggers, grants, dependent objects, and data.

### 5.4. Flashback Database or Database PITR

If a `TRUNCATE` affected many tables or the whole database must rewind before the DDL, evaluate Flashback Database or DBPITR. Both are database-wide operations that rewind everything to an earlier point and discard subsequent transactions. Choose them only when RPO and reconciliation permit.

## 6. Recovering DROP TABLESPACE or DROP USER

### 6.1. DROP TABLESPACE

`DROP TABLESPACE` removes metadata and, depending on clauses, deletes OS datafiles. The recycle bin does not recover dropped tablespaces. To recover data:
- Use TSPITR if tablespace scope and dependencies allow.
- Restore and recover the database or tablespace with RMAN per design.
- Restore into an auxiliary/clone and Data Pump the needed data back.
- Restore from logical backups if available.

### 6.2. DROP USER CASCADE

`DROP USER CASCADE` wipes out all objects in a schema. There is no single Flashback Drop command to reconstruct an entire schema intact. Choose RMAN `RECOVER TABLE` for individual critical tables, PITR/clone recovery, or import from logical backups.

### 6.3. Mapping Dependencies

Before choosing TSPITR or table recovery, map all dependencies:
- Foreign keys spanning tablespaces.
- Indexes and LOB segments residing in other tablespaces.
- Materialized views and materialized view logs.
- Partitions and subpartitions.
- Procedures, views, and triggers.
- Grants, synonyms, and scheduler jobs.

TSPITR has restrictions regarding `SYSTEM`, `SYSAUX`, active undo, and non-self-contained tablespace dependencies. Review TSPITR restrictions for your Oracle release before proceeding.

## 7. Datafile Loss: Investigating Before Restoring

### 7.1. Distinguishing Deleted Files from Inaccessible Storage

A datafile may appear missing because:
- The file was deleted or renamed at the OS level.
- A mount point or ASM disk group is offline.
- Storage paths or network filesystems were interrupted.
- File permissions or ownership changed.
- The control file points to an old path.
- The file header is corrupt or unreadable.

If storage is only temporarily unreachable, restoring storage access/paths is far less risky than restoring from backup. Never create an empty file with the same name to silence errors; that will not restore data blocks.

### 7.2. Inspecting the Datafile List

§§§sql
SELECT file#,
       name,
       status,
       enabled,
       checkpoint_change#
FROM v$datafile
ORDER BY file#;
§§§

Inspect headers:
§§§sql
SELECT file#,
       status,
       error,
       recover,
       fuzzy,
       checkpoint_change#,
       creation_change#
FROM v$datafile_header
ORDER BY file#;
§§§

Check files needing recovery:
§§§sql
SELECT file#,
       online_status,
       error,
       change#,
       time
FROM v$recover_file
ORDER BY file#;
§§§

These views require access to dynamic performance views. Zero rows in `V$RECOVER_FILE` does not alone guarantee physical files are healthy; cross-check headers, OS/storage state, and RMAN validation.

### 7.3. Identifying Tablespace and Datafile Role

§§§sql
SELECT d.file_id,
       d.file_name,
       d.tablespace_name,
       d.status,
       t.contents,
       t.status AS tablespace_status
FROM dba_data_files d
JOIN dba_tablespaces t
  ON t.tablespace_name = d.tablespace_name
ORDER BY d.file_id;
§§§

Identify whether the file belongs to:
- `SYSTEM`.
- `SYSAUX`.
- `UNDO`.
- `TEMP`.
- A user tablespace.
- A read-only tablespace.
- A tablespace holding critical application data.

A `TEMPFILE` is not a regular datafile and follows different recovery handling; never apply datafile restore commands to tempfiles as though they were identical.

### 7.4. SYSTEM and UNDO Datafiles

You cannot casually take a `SYSTEM` datafile offline while the database is open. Losing `SYSTEM` or an active `UNDO` datafile can prevent normal database operation; recovery generally requires mounting the database (`MOUNT`) and running restore/recover per official procedures.

Never apply user-datafile offline commands to `SYSTEM` or active `UNDO`. Verify the exact file number and role before issuing commands.

### 7.5. If the File Exists but the Path Failed

Inspect OS mounts, ASM, permissions, ownership, symbolic links, storage paths, and the alert log. Restore storage connectivity before running RMAN if the original file is actually intact. Restoring over an intact file can overwrite recent changes you wanted to keep.

## 8. Restoring and Recovering a Datafile in ARCHIVELOG Mode

### 8.1. Prerequisites

Typically required:
- Database running in `ARCHIVELOG` mode.
- Valid backup covering the datafile.
- Contiguous archived redo logs from backup checkpoint through recovery target.
- Control file or recovery catalog containing metadata.
- Sufficient storage for restore.
- TDE wallet/keystore if the datafile is encrypted.

If archived redo logs have gaps, you may only be able to recover up to the last SCN covered by contiguous redo; never claim the database was recovered to current time.

### 8.2. Missing User Tablespace Datafile

Suppose datafile 7 belongs to an application tablespace while the database remains open:
1. Confirm file 7 is inaccessible.
2. Check affected sessions and workloads.
3. Take the datafile offline per DBA runbook if the database permits.
4. Restore the file using RMAN.
5. Apply archived redo with `RECOVER`.
6. Bring the datafile/tablespace online.
7. Verify data and application access.

Example statement:
§§§sql
ALTER DATABASE DATAFILE 7 OFFLINE IMMEDIATE;
§§§

`OFFLINE IMMEDIATE` has prerequisites and media-recovery consequences; use it only under a verified runbook, ensuring the database is in `ARCHIVELOG` mode and the file is neither `SYSTEM` nor active `UNDO`.

### 8.3. RMAN RESTORE and RECOVER

§§§text
RMAN> RESTORE DATAFILE 7;
RMAN> RECOVER DATAFILE 7;
§§§

`RESTORE` copies the datafile from a suitable backup. `RECOVER` applies redo needed to bring the datafile to a consistent state. Neither step replaces the other.

Once complete:
§§§sql
ALTER DATABASE DATAFILE 7 ONLINE;
§§§

If the entire tablespace was taken offline, verify all datafile statuses and bring the tablespace online per runbook. Never bring a file online before media recovery completes.

### 8.4. Restoring to an Alternate Path

If the original path is unavailable or you want to relocate the file to new storage:
§§§text
RMAN> RUN {
  SET NEWNAME FOR DATAFILE 7
    TO '/u02/oradata/APPDB/users07.dbf';
  RESTORE DATAFILE 7;
  SWITCH DATAFILE 7;
  RECOVER DATAFILE 7;
}
§§§

Substitute a valid path and verify permissions, capacity, ASM/filesystem conventions, and naming standards. After `SWITCH`, the control file points to the new path. Check `DBA_DATA_FILES`/`V$DATAFILE` before bringing it online.

### 8.5. Validating Backups Before Restoring

Check available backups:
§§§text
RMAN> LIST BACKUP OF DATAFILE 7;
RMAN> RESTORE VALIDATE DATAFILE 7;
§§§

`RESTORE VALIDATE` verifies that required backups are readable without writing restored files to target locations. Scope varies by backup type, RMAN settings, and Oracle release; read the full output carefully.

### 8.6. Do Not Use OPEN RESETLOGS for Routine Single-Datafile Recovery

After restoring and fully recovering one datafile within the current database incarnation with complete redo, you normally only bring the datafile or tablespace online. `OPEN RESETLOGS` is associated with incomplete database recovery, backup control file recovery, or specific procedures. Never run `RESETLOGS` out of habit after every `RESTORE DATAFILE`.

## 9. Losing SYSTEM, UNDO, or Multiple Datafiles

### 9.1. SYSTEM Datafile

If `SYSTEM` is lost, the database cannot operate normally. The DBA generally shuts down or mounts the database (`MOUNT`), restores and recovers the datafile, and opens the database once recovery finishes. Follow procedures specific to your release and control file state.

### 9.2. UNDO Datafile

Losing a datafile containing active undo affects transaction recovery and opening the database. Never create a brand-new undo tablespace and drop the old datafile without an Oracle-supported plan. Identify the active undo tablespace, open transactions, and release-specific recovery procedures.

### 9.3. Losing Multiple Datafiles

If many files or an entire disk group are lost, evaluate restoring/recovering the tablespace or whole database via RMAN, Data Guard, or storage snapshots. Recalculate RTO; recovering numerous files individually is often no simpler than full database recovery.

### 9.4. NOARCHIVELOG Mode

In `NOARCHIVELOG` mode, archived redo logs are not preserved across log switches. If a read-write datafile is lost after the database has changed since the last backup, you generally cannot roll that single file forward to current time with full redo.

The standard approach is restoring a consistent whole-database backup and accepting data loss since that backup, barring Oracle-documented special cases such as a cleanly offlined file/tablespace with no subsequent writes. Never assume you can plug an old datafile into a database alongside newer datafiles.

### 9.5. Restoring a Whole Database from a Consistent Backup

At a high level:
1. Shut down the database and identify a consistent backup.
2. Restore the control file/SPFILE if needed.
3. Restore all datafiles from the same consistent backup.
4. Recover within available redo scope and proper mode.
5. Open the database as required by the recovery path, potentially with `RESETLOGS`.
6. Validate the entire database and accept the actual RPO.

Illustrative commands depend on DBID, control file, backup location, and state:
§§§text
RMAN> STARTUP MOUNT;
RMAN> RESTORE DATABASE;
RMAN> RECOVER DATABASE;
§§§

Never run this snippet blindly as a generic production script. You need a detailed runbook covering control file autobackup, DBID, channels, catalog, backup pieces, archived logs, TDE, and `OPEN RESETLOGS`.

## 10. Choosing the Recovery Method

### 10.1. Flashback Drop

Use when:
- Standard `DROP TABLE`.
- Object remains in the recycle bin.
- Object type is supported.
- Only the dropped table needs restoration.

Pros: fast, narrow scope. Limit: cannot recover `PURGE` drops or objects already evicted from the recycle bin.

### 10.2. Flashback Table/Query

Use when:
- Accidental DML was committed.
- Sufficient undo remains.
- Need to restore one table or extract historical rows.
- No intervening DDL broke flashback capability.
- Subsequent valid changes can be handled or reconciled.

Flashback Table rewinds the whole table; Flashback Query reads historical rows for selective reconciliation.

### 10.3. RMAN RECOVER TABLE

Use when:
- Table suffered `DROP PURGE` or `TRUNCATE`.
- Need to recover one table or partition without rewinding the entire database.
- Backups, archived redo, and auxiliary space satisfy prerequisites.
- Oracle release supports table recovery.

RMAN creates an auxiliary recovery instance and uses Data Pump to import the recovered table. Verify constraints, indexes, grants, and dependencies afterward.

### 10.4. Tablespace Point-in-Time Recovery (TSPITR)

Use when:
- Logical error is isolated to one or a small set of tablespaces.
- The tablespace set can be rewound to before the error.
- Tablespaces and dependencies meet TSPITR restrictions.
- Avoiding full database rewind.

TSPITR uses an auxiliary instance and enforces strict requirements around self-containment, dependencies, `SYSTEM`/`UNDO`/`SYSAUX`, and related objects. Do not pick it solely because the lost object lived in one tablespace; analyze dependencies first.

### 10.5. Database Point-in-Time Recovery (DBPITR)

Use when:
- Database-wide logical error or widespread object loss.
- Entire database must rewind prior to the incident.
- RPO allows losing post-target changes or replaying them.

DBPITR affects the entire database, typically concludes with `OPEN RESETLOGS`, and creates a new database incarnation. Valid transactions committed after the recovery point will be absent from the recovered database.

### 10.6. Flashback Database

Use when:
- Flashback Database was enabled prior to the incident.
- Flashback logs cover the target recovery point.
- Database-wide recovery scope is appropriate.
- Post-target data loss or replay is acceptable.

Flashback Database is often faster than full database restore in suitable scenarios, though it does not replace backups. Do not treat it as a single-datafile restore tool for a deleted physical file without verifying prerequisites.

### 10.7. Block Media Recovery

Use when specific blocks are corrupt and database, backups, and redo support block recovery. It repairs physical blocks—it does not undo a SQL-valid `DELETE` or `DROP`.

## 11. Flashback Database and Restore Points

### 11.1. Checking Flashback Database

§§§sql
SELECT flashback_on
FROM v$database;

SELECT name,
       guarantee_flashback_database,
       time,
       scn,
       storage_size
FROM v$restore_point
ORDER BY time DESC;
§§§

Check flashback status, restore points, and FRA capacity. Normal restore points do not guarantee flashback log retention unless guaranteed; verify exact status.

### 11.2. Creating a Guaranteed Restore Point Before Changes

Example in a maintenance plan:
§§§sql
CREATE RESTORE POINT BEFORE_CHANGE
GUARANTEE FLASHBACK DATABASE;
§§§

Guaranteed restore points require Flashback Database prerequisites and sufficient FRA space. The longer a restore point is kept, the more flashback logs accumulate; monitor the FRA continuously.

### 11.3. Flashing Back to a Restore Point

A general workflow may require:
§§§sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
FLASHBACK DATABASE TO RESTORE POINT BEFORE_CHANGE;
ALTER DATABASE OPEN RESETLOGS;
§§§

Actual commands depend on database architecture, release, RAC/CDB/PDB, and recovery state. Execute only after the DBA confirms the target restore point and data-loss impact. After `OPEN RESETLOGS`, the database enters a new incarnation; take a fresh backup per policy immediately afterward.

### 11.4. Dropping a Restore Point

Drop a guaranteed restore point only after the rollback window closes and approval is granted:
§§§sql
DROP RESTORE POINT BEFORE_CHANGE;
§§§

Never drop a GRP while fallback may still be needed, and never leave GRPs lingering indefinitely without FRA monitoring.

## 12. RMAN RECOVER TABLE and TSPITR

### 12.1. How Does RMAN Table Recovery Work?

RMAN restores an auxiliary copy of the database to a point before the mistake, exports the target table from the auxiliary database, and imports it into the target database. Production does not need to rewind as a whole.

Logical steps:
1. Identify the table/partition and target recovery time.
2. Verify backups and archived redo logs.
3. Provision auxiliary destination and disk space.
4. Run `RECOVER TABLE`.
5. RMAN builds the auxiliary instance, restores, and recovers.
6. RMAN exports the table and imports it into the target database.
7. Validate recovered objects and data.

### 12.2. Illustrative Syntax

§§§text
RMAN> RECOVER TABLE APP.ORDERS
      UNTIL SCN 123456789
      AUXILIARY DESTINATION '/u02/rman_aux';
§§§

Substitute your environment's SCN, schema/table, and path. To rename the recovered table, use `REMAP TABLE` per release syntax. Verify support for partitions, object types, encrypted tablespaces, and multitenant setups.

### 12.3. RMAN Table Recovery Is Not a Logical Backup

RMAN requires backups and redo to build the auxiliary instance. Verify the imported table afterward for:
- Row counts and business totals.
- Primary, unique, and foreign keys.
- Indexes and index statuses.
- Triggers.
- Grants and synonyms.
- LOB data.
- Dependencies and application behavior.

### 12.4. TSPITR

TSPITR recovers a tablespace set to a target time using an auxiliary instance, then reintegrates the tablespace set into the target database via Oracle's transport process. Check:
- The target tablespace set.
- Objects with cross-tablespace dependencies.
- Referential integrity and foreign keys.
- Ensure no `SYSTEM`/`UNDO`/`SYSAUX` involvement.
- Read-only tablespaces and transportable dependencies.
- Backup/redo availability and auxiliary destination space.

### 12.5. When to Choose RMAN RECOVER TABLE Over TSPITR?

If only one table was truncated or dropped with `PURGE`, RMAN `RECOVER TABLE` usually has a narrower blast radius. If multiple objects across a tablespace were altered and must revert together, TSPITR may fit better. If damage spans the whole database, evaluate DBPITR or Flashback Database.

## 13. Does Data Guard Replace Backups?

### 13.1. Physical Standby Applies Redo

A physical standby applies redo shipped from the primary. If a user executes a valid `DROP TABLE` or `DELETE` on the primary, the corresponding redo is applied to the standby as well. Thus, a standby does not automatically protect against logical deletions.

### 13.2. Delayed Apply

Some architectures configure an apply delay so the standby trails the primary by a fixed window. Upon catching an error early, you can halt apply before faulty redo arrives. Still, understand lag, role transitions, and standby recovery workflows; delayed standbys do not replace backups.

### 13.3. Snapshot Standby

A snapshot standby can open read-write temporarily and later revert to a physical standby via supported procedures. It is a testing/operational mode, not an independent backup.

### 13.4. DR Design

Combine:
- RMAN backups.
- Archived redo logs and offsite/immutable copies.
- Data Guard.
- Flashback Database / restore points where appropriate.
- Logical exports for critical objects.
- Periodic restore rehearsals.
- Tested runbooks and verified RPO/RTO.

## 14. Standard Drill Procedure

### Phase A — Prepare the Lab

1. Use an isolated lab/clone database, never production.
2. Create a dedicated tablespace `RECOVERY_LAB`.
3. Create sample tables and load data with business keys.
4. Create necessary indexes, constraints, triggers, and sequences.
5. Enable `ARCHIVELOG` if rehearsing media recovery.
6. Configure backups and archived logs.
7. Record baseline SCN and timestamps.
8. Confirm RMAN restore validation and sufficient disk space.

### Phase B — Rehearse Logical Deletion

Run a regular `DROP TABLE` and recover via the recycle bin. Repeat with `PURGE` to prove the recycle bin no longer holds it. Create another table, run a committed `DELETE`, and practice Flashback Table or Flashback Query.

### Phase C — Rehearse TRUNCATE

Create a copy of a test table, record the SCN, back up the database, and run `TRUNCATE` on the lab table. Practice RMAN `RECOVER TABLE` under a new name. Compare recovered data against baseline.

### Phase D — Rehearse Datafile Loss

Use only a datafile belonging to a non-critical lab tablespace:
1. Back up the tablespace/datafile and archived logs.
2. Take the tablespace cleanly offline per runbook.
3. Move/hide the file safely in the lab, keeping a quarantined copy.
4. Attempt to bring it online to observe the missing-file error.
5. Run RMAN `RESTORE DATAFILE` and `RECOVER DATAFILE`.
6. Bring the file/tablespace online.
7. Verify headers, row counts, and application access.

Never delete an online datafile via OS commands, and never simulate using `SYSTEM` or active `UNDO` datafiles.

### Phase E — Measure Results

Record:
- Detection time.
- Decision time.
- Recovery start/end timestamps.
- Data loss or transactions requiring replay.
- Actual RTO.
- Actual RPO.
- Errors encountered during recovery.
- Evidence and approver sign-off.

## 15. Lab 1: DROP TABLE and Flashback Drop

### Step 1 — Create Sample Table

§§§sql
CREATE TABLE APP.RECOVERY_DROP_LAB (
    ID NUMBER PRIMARY KEY,
    DESCRIPTION VARCHAR2(100 CHAR),
    CREATED_AT TIMESTAMP DEFAULT SYSTIMESTAMP
);

INSERT INTO APP.RECOVERY_DROP_LAB (ID, DESCRIPTION)
VALUES (1, 'before drop');

COMMIT;
§§§

### Step 2 — Capture Baseline

§§§sql
SELECT COUNT(*) AS row_count,
       MIN(id) AS min_id,
       MAX(id) AS max_id
FROM app.recovery_drop_lab;

SELECT current_scn
FROM v$database;
§§§

### Step 3 — Drop Without Purge

§§§sql
DROP TABLE APP.RECOVERY_DROP_LAB;
§§§

### Step 4 — Inspect the Recycle Bin

§§§sql
SELECT original_name, object_name, droptime
FROM user_recyclebin
WHERE original_name = 'RECOVERY_DROP_LAB';
§§§

### Step 5 — Flashback

§§§sql
FLASHBACK TABLE APP.RECOVERY_DROP_LAB
TO BEFORE DROP;
§§§

### Step 6 — Verify

§§§sql
SELECT * FROM APP.RECOVERY_DROP_LAB;
§§§

Inspect constraints, indexes, and grants, and record recovery duration. Repeat with `DROP TABLE ... PURGE` on another test table to compare.

## 16. Lab 2: Committed DELETE and Flashback

### Step 1 — Create Data

§§§sql
CREATE TABLE APP.RECOVERY_DELETE_LAB (
    ID NUMBER PRIMARY KEY,
    AMOUNT NUMBER(12,2),
    STATUS VARCHAR2(20 CHAR)
);

INSERT INTO APP.RECOVERY_DELETE_LAB VALUES (1, 100, 'NEW');
INSERT INTO APP.RECOVERY_DELETE_LAB VALUES (2, 200, 'NEW');
INSERT INTO APP.RECOVERY_DELETE_LAB VALUES (3, 300, 'NEW');
COMMIT;
§§§

### Step 2 — Record SCN

§§§sql
SELECT current_scn
FROM v$database;
§§§

Save the SCN prior to the `DELETE`.

### Step 3 — Accidental Delete

§§§sql
DELETE FROM APP.RECOVERY_DELETE_LAB;
COMMIT;
§§§

### Step 4 — Flashback Table

§§§sql
ALTER TABLE APP.RECOVERY_DELETE_LAB ENABLE ROW MOVEMENT;

FLASHBACK TABLE APP.RECOVERY_DELETE_LAB
TO SCN 123456789;
§§§

Substitute the actual SCN captured in the lab. If valid DML occurred after that SCN, test Flashback Query into a separate recovery table and reinsert only the needed keys.

### Step 5 — Verify

§§§sql
SELECT COUNT(*) AS row_count,
       SUM(amount) AS amount_total
FROM app.recovery_delete_lab;
§§§

Compare with baseline. Record undo retention and the elapsed time between delete and flashback.

## 17. Lab 3: TRUNCATE and RMAN RECOVER TABLE

### Step 1 — Prepare Backup

Create the lab table and record baseline. Run an RMAN database plus archived log backup per lab policy. Verify the backup is readable.

### Step 2 — Record Recovery Point

Record the SCN or timestamp immediately prior to `TRUNCATE`.

### Step 3 — TRUNCATE

§§§sql
TRUNCATE TABLE APP.RECOVERY_TRUNCATE_LAB;
§§§

### Step 4 — RMAN Recover Table

Example:
§§§text
RMAN> RECOVER TABLE APP.RECOVERY_TRUNCATE_LAB
      UNTIL SCN 123456789
      AUXILIARY DESTINATION '/u02/rman_aux'
      REMAP TABLE 'APP'.'RECOVERY_TRUNCATE_LAB':'RECOVERY_TRUNCATE_RESTORED';
§§§

Verify `REMAP TABLE` syntax for your Oracle release. Use a different target name to preserve the existing table and avoid overwriting it.

### Step 5 — Compare

§§§sql
SELECT COUNT(*) AS row_count,
       SUM(amount) AS amount_total
FROM app.recovery_truncate_restored;
§§§

Verify indexes, constraints, grants, triggers, and dependent objects after import.

## 18. Lab 4: Single Datafile Loss

### Step 1 — Create Lab Tablespace

§§§sql
CREATE TABLESPACE RECOVERY_LAB
DATAFILE '/u02/oradata/APPDB/recovery_lab01.dbf'
SIZE 200M
AUTOEXTEND ON NEXT 20M MAXSIZE 1G;
§§§

The path is an example. Use a valid path on your lab host.

### Step 2 — Create Data

§§§sql
CREATE TABLE APP.RECOVERY_FILE_LAB (
    ID NUMBER PRIMARY KEY,
    DESCRIPTION VARCHAR2(100 CHAR)
) TABLESPACE RECOVERY_LAB;

INSERT INTO APP.RECOVERY_FILE_LAB
VALUES (1, 'file recovery test');

COMMIT;
§§§

### Step 3 — Identify File Number

§§§sql
SELECT file_id, file_name, tablespace_name
FROM dba_data_files
WHERE tablespace_name = 'RECOVERY_LAB';
§§§

Record the file number. Back up the datafile/tablespace and archived logs.

### Step 4 — Clean Offline

§§§sql
ALTER TABLESPACE RECOVERY_LAB OFFLINE NORMAL;
§§§

Verify the tablespace is offline and checkpointing completed. In the lab, move the file to a quarantine folder after offlining it. Never delete it; keep a copy to revert if the exercise fails.

### Step 5 — Attempt Online

§§§sql
ALTER TABLESPACE RECOVERY_LAB ONLINE;
§§§

Record the missing-file error. Return the state per runbook before restoring.

### Step 6 — Restore/Recover

§§§text
RMAN> RESTORE DATAFILE 7;
RMAN> RECOVER DATAFILE 7;
§§§

Replace `7` with the actual file number. If restoring to a new path, use `SET NEWNAME` and `SWITCH DATAFILE` per runbook.

### Step 7 — Bring Online and Verify

§§§sql
ALTER TABLESPACE RECOVERY_LAB ONLINE;

SELECT COUNT(*)
FROM APP.RECOVERY_FILE_LAB;

SELECT file_id, file_name, tablespace_name, status
FROM dba_data_files
WHERE tablespace_name = 'RECOVERY_LAB';
§§§

Verify datafile headers, RMAN output, and application queries. Do not rely solely on `ONLINE` status.

## 19. Post-Recovery Verification

### 19.1. Checking Datafiles and Headers

§§§sql
SELECT file#,
       name,
       status,
       enabled,
       checkpoint_change#
FROM v$datafile
ORDER BY file#;

SELECT file#,
       status,
       error,
       recover,
       fuzzy,
       checkpoint_change#
FROM v$datafile_header
ORDER BY file#;

SELECT *
FROM v$recover_file;
§§§

The objective is confirming exact file paths, readable headers, and zero unresolved media recovery requirements.

### 19.2. Checking Objects

§§§sql
SELECT owner, object_type, object_name, status
FROM dba_objects
WHERE owner = 'APP'
  AND status <> 'VALID'
ORDER BY object_type, object_name;
§§§

Also verify related constraints, indexes, triggers, grants, synonyms, and materialized views. A recovered table does not automatically mean all dependencies are ready.

### 19.3. Reconciling Data

Compare:
- Exact row counts.
- Min/max keys.
- Business aggregates.
- Null counts.
- Duplicate keys.
- Orphan references.
- LOB lengths/contents where relevant.
- Transactions occurring after the recovery point.

Use clear snapshots and business cutoffs. Never compare a live source against a rewound target without accounting for the delta.

### 19.4. Application Verification

- Connect as the runtime user.
- Run critical read queries.
- Run controlled writes if approved.
- Verify sequences and identity columns.
- Check batch jobs and integrations.
- Monitor error rates and latencies.
- Confirm no unintended duplicate writers exist.

### 19.5. Post-Recovery Backup

After incomplete recovery or `OPEN RESETLOGS`, the database enters a new incarnation. Run a fresh backup per policy and verify archived redo and backup jobs continue operating. Record the incarnation, recovery SCN/time, and Data Guard status.

## 20. Common Mistakes and Pitfalls

### 20.1. Running CREATE DATAFILE to Replace a Missing File

Creating an empty datafile does not restore historical data blocks. Always run RMAN restore from a valid backup; never create an empty file with the same name just to get the database open.

### 20.2. Bringing a Datafile ONLINE Before Recovering

If a file needs media recovery, bringing it online early fails or complicates recovery. Always run `RESTORE`, then `RECOVER`, and only then `ONLINE`.

### 20.3. Using Flashback Table for TRUNCATE

Never assume Flashback Table rewinds across arbitrary DDL. For `TRUNCATE`, use verified methods such as RMAN `RECOVER TABLE`, Flashback Database, or PITR.

### 20.4. Confusing DROP with DROP PURGE

Standard `DROP` can place objects into the recycle bin. `PURGE` bypasses or removes objects from the recycle bin. Check the recycle bin before choosing a recovery path.

### 20.5. Restoring a Datafile Without Applying Redo

`RESTORE` only copies the backup image. `RECOVER` applies redo to reach the recovery target. Skipping `RECOVER` leaves the file inconsistent with the rest of the database.

### 20.6. Mixing Old NOARCHIVELOG Backups with Newer Datafiles

An older datafile will be inconsistent with newer datafiles. In `NOARCHIVELOG`, you typically must restore a consistent whole-database backup to guarantee consistency.

### 20.7. Running OPEN RESETLOGS After Every Recovery

`RESETLOGS` is not a universal finisher for all media recovery. Use it only when required by the recovery path; routine single-datafile recovery normally does not require `RESETLOGS`.

### 20.8. Ignoring Post-Target Transactions

Flashback or PITR discards valid transactions committed after the recovery point. Catalog transactions needing replay or reconciliation before locking in a target point.

### 20.9. Treating Data Guard as a Backup

Logical deletions replicate to standbys via redo. Maintain independent backups, delayed apply, or dedicated protection mechanisms per design.

### 20.10. Deleting FRA Files via OS Commands

Never remove flashback logs, archived logs, or backups directly from the filesystem. Use RMAN retention policies and management commands.

### 20.11. Neglecting TDE Wallets

Encrypted datafile backups cannot be recovered without the corresponding keystore/wallet. Verify wallet backups, passwords, and access permissions before an incident occurs.

### 20.12. Never Rehearsing

An untested runbook may lack privileges, paths, storage space, archived logs, or realistic timing. Measure real RTO periodically in a lab or clone.

## 21. Recovery Strategy Decision Matrix

| Scenario | Preferred Recovery | Scope | Watch-Outs |
|---|---|---|---|
| Uncommitted `DELETE` | `ROLLBACK` | Transaction | Verify session is still active |
| Committed `DELETE`, undo available | Flashback Table/Query | Table/rows | Reconcile post-target changes |
| `DROP TABLE`, in recycle bin | Flashback Drop | Table | Pick the exact drop version |
| `DROP TABLE PURGE` | RMAN `RECOVER TABLE` | Table | Auxiliary space, backups, redo |
| `TRUNCATE TABLE` | RMAN `RECOVER TABLE` or PITR | Table/database | Cannot rely on rollback |
| `DROP TABLESPACE` | TSPITR or database recovery | Tablespace/database | Dependency restrictions |
| User datafile lost, `ARCHIVELOG` | `RESTORE` + `RECOVER DATAFILE` | Datafile | Backups and contiguous redo |
| `SYSTEM`/`UNDO` file lost | Mount-level database recovery | Database-critical file | Never offline casually |
| Isolated corrupt blocks | Block media recovery | Blocks | Requires backups and redo |
| Database-wide logical error | Flashback Database / DBPITR | Whole database | Discards post-target changes |
| `NOARCHIVELOG` and read-write file lost | Restore consistent database backup | Whole database | RPO typically reverts to backup |
| Primary lost, standby ready | Data Guard failover | Database role | Does not replace logical recovery |

This matrix is a starting point. Final selection depends on Oracle release, database architecture, actual backup/redo availability, RPO/RTO, and business impact.

## 22. Production Recovery Runbook

### Pre-Execution

- Confirm database identity and environment.
- Confirm affected object names or file numbers.
- Capture current state and logs.
- Pause workloads that worsen data divergence.
- Verify backups, redo, FRA, and wallets.
- Lock in the recovery point.
- Select the recovery method and assess blast radius.
- Obtain approval from the DBA lead and change owner.
- Document commands, expected results, and abort criteria.

### During Recovery

1. Execute commands step by step rather than running a blind monolithic script.
2. Save all RMAN and SQL outputs.
3. Stop immediately if any backup piece or archived log is missing.
4. Stop if the SCN or timestamp looks wrong.
5. Keep traffic blocked until recovery is fully verified.
6. Record start/end timestamps and operator names.

### Post-Recovery

1. Verify file and object states.
2. Reconcile data.
3. Verify constraints, indexes, and dependencies.
4. Run application smoke tests.
5. Identify transactions requiring replay.
6. Take a fresh backup if required.
7. Verify standby and replication health.
8. Obtain business owner sign-off.
9. Archive evidence and update the RCA.

## 23. RPO, RTO, and Business Impact

### 23.1. RPO

Recovery Point Objective defines maximum tolerable data loss. Examples:
- Flashing back a table 10 minutes can lose valid changes to that table over those 10 minutes.
- DBPITR to an SCN before an error loses all database transactions after that SCN.
- `NOARCHIVELOG` restore from a consistent backup loses all transactions since that backup.

### 23.2. RTO

Recovery Time Objective defines target time to restore service. Measure:
- Incident detection.
- Recovery decision time.
- Locating backups and redo.
- Restore / auxiliary setup.
- Redo application.
- Validation and reconciliation.
- Application reconnection.
- Business sign-off.

### 23.3. Blast Radius

Estimate the impact scope:
- Single table.
- Single schema.
- Single tablespace.
- Single PDB.
- Whole CDB/database.
- Multiple databases or external systems.

Always choose the narrowest scope that restores consistency. Never run full database PITR if one table can be recovered safely using RMAN `RECOVER TABLE`.

### 23.4. Out-of-Database Side Effects

Payments, emails, message queues, files, and external API side effects do not vanish when a database flashes back. Handle them with idempotency, outbox/inbox patterns, compensation, and reconciliation. Before replaying transactions, determine which actions already executed externally.

## 24. Integrated Exercises

Assume an application database containing:
- `APP.ORDERS` in tablespace `APP_DATA`.
- `APP.CUSTOMER` in the same tablespace.
- One datafile backing `APP_DATA`.
- Nightly RMAN backups and archived redo logs.
- Flashback Database enabled.
- A Spring Boot application with a connection pool.

Execute these scenarios in a lab:
1. `DROP APP.ORDERS` without `PURGE`.
2. `DROP` another table with `PURGE`.
3. `DELETE` all rows of a table and `COMMIT`.
4. `TRUNCATE` a table.
5. Lose the `APP_DATA` datafile after cleanly offlining the tablespace in the lab.
6. Commit a valid transaction after the recovery point and assess transaction loss risk.
7. Simulate a database-wide logical error and compare Flashback Database against DBPITR.
8. Run restore validation prior to recovery.
9. Measure RPO and RTO for each option.
10. Present the rationale for the chosen recovery method and required approvers.

For every scenario, archive command logs, start/end timestamps, SCNs, backup identifiers, reconciliation outputs, and lessons learned.

## 25. Drill Checklist

- [ ] Isolated lab/clone verified.
- [ ] Zero production datafiles used for destructive tests.
- [ ] Database identity, release, `ARCHIVELOG` status, and role recorded.
- [ ] Database/datafile backups and archived logs verified readable.
- [ ] Control file, SPFILE, and TDE wallet backups verified.
- [ ] FRA and auxiliary destination have sufficient space.
- [ ] Recovery SCN/timestamp documented.
- [ ] Distinguished `DELETE`, `TRUNCATE`, `DROP`, and `DROP PURGE`.
- [ ] Recycle bin inspected.
- [ ] Flashback Table/Query prerequisites confirmed.
- [ ] RMAN `RECOVER TABLE` rehearsed if supported by release.
- [ ] TSPITR dependencies and restrictions reviewed.
- [ ] Datafile number, tablespace, and file role identified.
- [ ] `SYSTEM`/`UNDO` datafiles never offlined casually.
- [ ] RMAN `RESTORE` and `RECOVER` executed in proper order.
- [ ] `ARCHIVELOG` vs. `NOARCHIVELOG` implications understood.
- [ ] `OPEN RESETLOGS` avoided for routine single-file media recovery.
- [ ] Datafile headers and `V$RECOVER_FILE` verified.
- [ ] Rows, keys, totals, and dependencies reconciled.
- [ ] Post-recovery-point transactions identified.
- [ ] Confirmed Data Guard/standbys did not replicate logical errors blindly.
- [ ] Actual RPO/RTO measured.
- [ ] Business sign-off and recovery evidence archived.
- [ ] Fresh post-recovery backup taken if required.

## 26. Self-Check Questions

1. How does logical data loss differ from physical datafile loss?
2. Why must you determine whether a transaction committed before choosing recovery?
3. How does the recycle bin help recover `DROP TABLE`?
4. How does `DROP TABLE PURGE` differ from a regular `DROP TABLE`?
5. Why does Flashback Drop not replace RMAN backups?
6. What undo and row-movement prerequisites does Flashback Table require?
7. Why can whole-table Flashback Table lose valid post-target changes?
8. How does Flashback Query support selective recovery?
9. Why can `TRUNCATE` not be undone with `ROLLBACK`?
10. When should you use RMAN `RECOVER TABLE`?
11. How does RMAN `RECOVER TABLE` leverage an auxiliary database and Data Pump?
12. What kinds of incidents suit TSPITR?
13. Why must TSPITR verify tablespace dependencies?
14. How does DBPITR impact database-wide data?
15. How does Flashback Database differ from RMAN restore/recover?
16. Which resource must be monitored closely with guaranteed restore points?
17. Why can a Data Guard physical standby also receive an accidental `DROP`?
18. How do you distinguish a genuinely deleted datafile from a lost storage mount?
19. What information do `V$DATAFILE_HEADER` and `V$RECOVER_FILE` provide?
20. Why must you never create an empty datafile to replace a missing file?
21. Why must `RESTORE` precede `RECOVER`?
22. When can a datafile be recovered online versus requiring `MOUNT`?
23. Why can you not casually take `SYSTEM` or active `UNDO` datafiles offline?
24. How do `ARCHIVELOG` and `NOARCHIVELOG` differ when a datafile is lost?
25. When must you restore a consistent whole-database backup?
26. Why does routine single-datafile media recovery not need `OPEN RESETLOGS`?
27. How does block media recovery differ from recovering logical deletions?
28. Which prerequisites must be verified before RMAN `RECOVER TABLE`?
29. How do RPO and RTO shape the choice of recovery method?
30. What must be verified after recovery before reopening traffic?

**Key Principle to Remember:** Select your recovery method according to incident type and blast radius. Standard `DROP TABLE` can use the recycle bin; committed `DELETE` can use Flashback Table/Query while undo remains; `TRUNCATE` or `DROP PURGE` typically needs RMAN table recovery or PITR; and datafile loss requires `RESTORE` and `RECOVER` from backups and redo. `ARCHIVELOG` enables rolling forward when redo is complete, whereas `NOARCHIVELOG` usually forces restoring a consistent whole-database backup if a read-write datafile is lost. Always pinpoint the recovery target, evaluate RPO/RTO and post-target transactions, verify dependencies, and reopen traffic only after validation and business sign-off are complete.
