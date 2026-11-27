# Recovering CDB/PDBs and Checking Oracle Release Prerequisites

## 1. Multitenant Architecture and Recovery Scope

Oracle Multitenant organizes databases using a **container database (CDB)** model. A CDB contains the root container `CDB$ROOT`, the template pluggable database `PDB$SEED`, and one or more PDBs serving applications.

- `CDB$ROOT` stores shared metadata and common components to manage the CDB.
- `PDB$SEED` is a read-only template PDB used by Oracle as a blueprint to provision new PDBs.
- Each PDB is a container with its own data dictionary and application data managed inside the CDB.

Recovery in a multitenant environment requires clearly identifying the scope of damage:

| Scope | Recovery Goal | Impact |
|---|---|---|
| Whole CDB | Restore root, seed, and CDB PDBs to a consistent state | Can affect every PDB and service in the CDB |
| Single PDB | Recover data for the selected PDB | Other PDBs normally remain online, depending on operation and recovery conditions |
| Tablespace/datafile in a PDB | Recover part of a PDB's data | Narrower scope, yet must stay consistent with the rest of the PDB |
| Control file / SPFILE | Restore control metadata and instance configuration | May require mount/restart and re-running restore/recovery steps |

Never start with `RESTORE DATABASE` when only a single PDB is damaged. Whole-CDB recovery has a much broader blast radius than recovering one PDB. First identify the container, datafiles, failure timestamp, and business recovery target.

## 2. Checking Oracle Release and Prerequisites Before Recovery

### 2.1. Identify the Running Oracle Release

Connect to the database and check version details:

```sql
SELECT banner
FROM v$version
ORDER BY banner;

SELECT instance_name,
       version,
       status,
       database_status
FROM v$instance;
```

`V$VERSION` displays Oracle version and components; `V$INSTANCE` shows the instance version and current status. When planning a restore to another host or after an upgrade, record the exact release, Release Update (RU), platform, and Oracle Home in use.

At the OS level, DBAs can check the Oracle Home patch inventory using `opatch lsinventory`. After installing patches containing SQL changes, check datapatch execution and database history:

```sql
SELECT patch_id,
       patch_type,
       action,
       status,
       action_time,
       description
FROM dba_registry_sqlpatch
ORDER BY action_time DESC;
```

Oracle Home binary patches and the SQL patch registry are two different pieces of information. An Oracle Home may have updated binaries without the SQL patch having been successfully applied yet. Before restoring/upgrading or diagnosing dictionary errors, verify both.

### 2.2. Confirm Whether the Database Is a CDB

```sql
SELECT name,
       dbid,
       cdb,
       open_mode,
       log_mode,
       database_role
FROM v$database;
```

`CDB='YES'` indicates the database uses container architecture. If it is non-CDB, PDB recovery commands and workflows do not apply. Never assume a database is a CDB simply because the Oracle release supports multitenant.

List containers and PDB status:

```sql
SHOW CON_NAME;

SELECT con_id,
       name,
       open_mode,
       restricted
FROM v$containers
ORDER BY con_id;

SELECT name,
       open_mode,
       restricted,
       recovery_status
FROM v$pdbs
ORDER BY con_id;
```

`SHOW CON_NAME` shows the session's current container. CDB-wide administrative queries should run from `CDB$ROOT` with appropriate privileges; never accidentally connect inside a PDB and run whole-database RMAN commands.

### 2.3. Check COMPATIBLE

The `COMPATIBLE` parameter defines the permitted disk format compatibility level and database behavior. It affects feature availability and file/database compatibility across releases.

```sql
SELECT name, value, isdefault, issys_modifiable
FROM v$parameter
WHERE name = 'compatible';
```

Do not automatically set `COMPATIBLE` to match the Oracle Home release number. A database that underwent a software upgrade may deliberately keep `COMPATIBLE` at an older level to preserve downgrade compatibility during a transition period. Raising this value can permanently alter downgrade options; read the upgrade guide for your release and have a backup/rollback plan before changing it.

`COMPATIBLE` is not the sole check for restorability. Also verify backup version, control file, platform, endianness, encryption wallet, CDB/PDB configuration, and Oracle-supported upgrade paths.

### 2.4. Check PDB Status and Plug-in Compatibility

For PDBs plugged into a CDB, inspect compatibility issues:

```sql
SELECT name,
       cause,
       type,
       status,
       message,
       action
FROM pdb_plug_in_violations
ORDER BY name, time;
```

This view records violations or warnings raised when plugging a PDB or checking compatibility. Distinguish errors that must be resolved from warnings deemed acceptable by release documentation. Never delete or ignore violations merely to force a PDB open.

When preparing to plug in a PDB from an XML manifest, invoke `DBMS_PDB.CHECK_PLUG_COMPATIBILITY` before creating the PDB:

```sql
SET SERVEROUTPUT ON
DECLARE
  l_compatible BOOLEAN;
BEGIN
  l_compatible := DBMS_PDB.CHECK_PLUG_COMPATIBILITY(
    pdb_descr_file => '/u01/backup/pdb1.xml',
    pdb_name       => 'PDB1'
  );

  IF l_compatible THEN
    DBMS_OUTPUT.PUT_LINE('PDB is compatible');
  ELSE
    DBMS_OUTPUT.PUT_LINE('PDB has compatibility violations');
  END IF;
END;
/
```

This is a plug-in compatibility check, not an integrity check of RMAN backups. After plugging in, still check `PDB_PLUG_IN_VIOLATIONS` and resolve any remaining entries.

### 2.5. Release and Platform Prerequisites

Before restoring or relocating a CDB/PDB across hosts, verify:

- Whether source and target releases sit on an Oracle-supported restore/upgrade/plug path.
- Which release created the backup, and whether the target RMAN is compatible with that metadata/backup.
- Whether `COMPATIBLE` on source and target databases meets feature/migration requirements.
- Whether platform and endianness match; if different, whether cross-platform conversion or transportable database/tablespace is required.
- Whether the CDB/PDB architecture and state match the planned operation.
- Whether Oracle Home, RU, timezone files, character set, national character set, and TDE wallet/keys are available and compatible.

Never assume a newer release's backup can be restored directly into an older Oracle Home. For cross-version operations, follow the exact upgrade, downgrade, transport, or plug/unplug guide for each release. Restoring a backup and upgrading a database are separate processes; never use a single RMAN command as a substitute for a supported upgrade procedure.

## 3. Prerequisites Required for RMAN Recovery

### 3.1. Backups and Archived Redo

To recover to a point in time after a backup, you need valid backups and archived redo logs covering the span from the backup to the recovery target. If an archived log in the middle of the chain is missing, recovery stops before the target.

Check archive mode:

```sql
ARCHIVE LOG LIST;

SELECT log_mode
FROM v$database;
```

A database in `ARCHIVELOG` mode saves filled redo logs for media recovery to an appropriate point in time. In `NOARCHIVELOG`, recovery options are limited; you normally rely on consistent backups and risk losing post-backup changes. Never use `NOARCHIVELOG` for systems requiring transactional recovery close to the present.

Example CDB backup:

```rman
CONFIGURE CONTROLFILE AUTOBACKUP ON;
BACKUP DATABASE PLUS ARCHIVELOG;
```

When RMAN connects to a CDB, backing up `DATABASE` from root covers the database across CDB scope as defined by RMAN—including root, seed, and PDBs. You can also back up a single PDB:

```rman
BACKUP PLUGGABLE DATABASE salespdb;
```

Backing up an individual PDB does not replace protecting the control file, SPFILE, archived redo, and shared components needed for recovery. Maintain both whole-CDB and PDB-level backup strategies if RPO/RTO require independent recovery.

### 3.2. Control File, SPFILE, and DBID

The control file stores database structure, checkpoints, datafiles, redo logs, and backup metadata. The SPFILE stores instance initialization parameters. If the control file or SPFILE is lost, recovery requires corresponding backups or autobackups.

The DBID is a database identifier required in certain scenarios to restore the control file/SPFILE from autobackup when no control file remains to look up metadata. DBAs must record the DBID in operational documentation.

Example querying DBID:

```sql
SELECT name, dbid
FROM v$database;
```

### 3.3. Other Operational Prerequisites

Before executing restore/recover, verify:

- Backup pieces and archived logs exist and are readable from disk, tape, or object storage.
- RMAN target connects to the right CDB and right DBID.
- Sufficient disk space exists for datafiles, control files, redo logs, FRA, and an auxiliary destination if PITR requires an auxiliary instance.
- File paths, ASM disk groups, channels, SBT libraries, and storage credentials are properly configured.
- Password file, TDE keystore/wallet, and encryption keys are ready if the database uses encryption.
- `SYSDBA`/`SYSBACKUP` privileges and OS permissions are available for the operation.
- Target point is explicitly chosen: SCN, timestamp, or log sequence—avoid arbitrary guesses.
- A safety backup exists before changing settings or running operations that can overwrite data.

## 4. Verifying Recoverability Before Restoring

### 4.1. Checking the Repository and Backups

Connect RMAN to the target CDB, typically with `SYSBACKUP` or appropriate administrative privileges, then inspect:

```rman
LIST BACKUP SUMMARY;
LIST BACKUP OF DATABASE;
LIST ARCHIVELOG ALL;
REPORT SCHEMA;
```

For a specific PDB:

```rman
LIST BACKUP OF PLUGGABLE DATABASE salespdb;
```

The repository may reside in the control file or a recovery catalog. With a control-file repository, older backup metadata can be overwritten over time; a recovery catalog retains longer history and manages multiple databases.

### 4.2. CROSSCHECK

`CROSSCHECK` reconciles metadata in the RMAN repository against physical existence of backup pieces/archived logs on storage:

```rman
CROSSCHECK BACKUP;
CROSSCHECK ARCHIVELOG ALL;
```

This updates repository status to `AVAILABLE` or `EXPIRED` based on check results. It does not delete physical backups. Never run `DELETE EXPIRED` as a mechanical cleanup step without confirming backup pieces are truly no longer needed.

### 4.3. PREVIEW and VALIDATE

Inspect which backups RMAN plans to use:

```rman
RESTORE DATABASE PREVIEW;
```

Check whether RMAN can read the required backup pieces:

```rman
RESTORE DATABASE VALIDATE;
```

For a PDB:

```rman
RESTORE PLUGGABLE DATABASE salespdb PREVIEW;
RESTORE PLUGGABLE DATABASE salespdb VALIDATE;
```

`PREVIEW` displays backup selection from the repository; `VALIDATE` reads/checks selected backups without overwriting target datafiles like an actual restore. Additionally, `VALIDATE DATABASE` checks database blocks per supported RMAN syntax. A passing validation increases confidence in backups, though it does not replace a full restore rehearsal.

## 5. Recovering the Whole CDB

### 5.1. When Is Whole-CDB Restore/Recovery Needed?

Whole-CDB recovery is considered when failures impact shared components or multiple PDBs, such as:

- Loss/corruption of the control file or critical system datafiles.
- Loss of multiple datafiles across multiple containers.
- Returning the CDB to a point in time before a container-wide corrupting operation.
- Loss or corruption of the database on the host requiring full rebuild from backup.

If only one PDB has a logical error or lost its own datafile, evaluate PDB-level recovery first to avoid rolling back unrelated PDBs.

### 5.2. Connecting to the Right Container and Mounting the Database

To restore/recover the entire CDB, RMAN must connect to the target CDB; startup/mount actions are controlled at the instance/CDB level. If the database is open and requires a full restore, the DBA may need to shut down and startup mount depending on error state and recovery type.

```sql
SHOW CON_NAME;
-- Must be in CDB$ROOT when performing CDB-wide administrative tasks.
```

In RMAN, the general flow when the current control file remains usable:

```rman
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
RESTORE DATABASE;
RECOVER DATABASE;
```

Once media recovery completes, open the database matching the recovery type. If this was complete recovery with the current control file, normal open applies; if incomplete recovery or using a backup control file, `OPEN RESETLOGS` is typically required. Never apply `RESETLOGS` mechanically; verify recovery state and Oracle guidance for the exact scenario.

### 5.3. Lost Control File

If the control file is lost and a control file autobackup exists, the DBA starts the instance in `NOMOUNT`, sets the DBID, and restores the control file:

```rman
SET DBID 1234567890;
STARTUP NOMOUNT;
RESTORE CONTROLFILE FROM AUTOBACKUP;
ALTER DATABASE MOUNT;
RESTORE DATABASE;
RECOVER DATABASE;
```

`1234567890` is an illustrative value; use the real DBID. If the SPFILE is also lost, start with a minimal PFILE or restore the SPFILE properly before mounting the database. After recovery with a backup control file, opening with `RESETLOGS` is normally required:

```sql
ALTER DATABASE OPEN RESETLOGS;
```

After opening, verify all PDBs, datafiles, services, invalid objects, and take a fresh backup per post-`RESETLOGS` strategy. Opening `RESETLOGS` creates a new database incarnation; old backups and archived logs must be tracked cleanly in the RMAN recovery catalog.

### 5.4. Incomplete Recovery / CDB Point-in-Time Recovery

To rewind the whole CDB to an earlier point, specify a target SCN or time:

```rman
RUN {
  SET UNTIL SCN 123456789;
  RESTORE DATABASE;
  RECOVER DATABASE;
}
```

Then:

```sql
ALTER DATABASE OPEN RESETLOGS;
```

This recovers the entire database to the target, so every PDB is affected at the same recovery point. Transactions committed after the target SCN are excluded from the recovered state. Base target selection on incident evidence and business requirements; verify timezone when using timestamps and prefer SCNs when exact precision is needed.

## 6. Recovering a Single PDB

### 6.1. When to Use PDB-Level Recovery?

PDB-level recovery fits when an incident is isolated to one PDB, for example:

- Loss or corruption of a datafile belonging to that PDB.
- Operational data errors affecting only that PDB requiring point-in-time recovery.
- Restoring a PDB from its own backup while sibling PDBs remain online.

RMAN PDB operations are executed from the CDB root. Before running, verify PDB name, `CON_ID`, datafiles, and open state. Never confuse a PDB name with a service name or schema name.

### 6.2. Restoring/Recovering a PDB to the Present

Connect SQL*Plus to `CDB$ROOT` with appropriate privileges and close the affected PDB:

```sql
ALTER PLUGGABLE DATABASE salespdb CLOSE IMMEDIATE;
```

In RMAN connected to the target CDB:

```rman
RESTORE PLUGGABLE DATABASE salespdb;
RECOVER PLUGGABLE DATABASE salespdb;
```

After complete recovery, reopen the PDB:

```sql
ALTER PLUGGABLE DATABASE salespdb OPEN;
```

These commands apply when PDB metadata remains in the CDB and required backups/archived logs exist. PDB state, lost file types, and specific releases may require extra steps. Always check RMAN output and datafile status before opening the PDB to applications.

### 6.3. PDB Point-in-Time Recovery (PDB PITR)

PDB PITR recovers a single PDB to a target SCN/time without rewinding the entire CDB. RMAN can use an auxiliary destination to spin up an auxiliary environment for PITR:

```rman
RECOVER PLUGGABLE DATABASE salespdb
  UNTIL SCN 123456789
  AUXILIARY DESTINATION '/u02/rman_aux';
```

The auxiliary destination path must exist, have sufficient disk space, and be accessible by Oracle/RMAN. Replace the illustrative SCN with the real recovery target. For PDB PITR, Oracle places the PDB onto a new incarnation; after RMAN finishes, open the PDB per PITR procedure, typically:

```sql
ALTER PLUGGABLE DATABASE salespdb OPEN RESETLOGS;
```

Do not confuse PDB PITR with complete restore/recovery to the present. PDB PITR discards changes in that PDB after the chosen point. Consult release-specific documentation regarding auxiliary instance requirements, PDB state, local undo vs. shared undo, application containers, and related restrictions.

### 6.4. PDB Tablespace/Datafile Recovery

If only one datafile or tablespace within a PDB is damaged, consider a narrower recovery scope. RMAN provides syntax supporting PDB, tablespace, or datafile targets; general example:

```rman
RESTORE DATAFILE 17;
RECOVER DATAFILE 17;
```

Obtain the datafile number from `V$DATAFILE`/`CDB_DATA_FILES` and verify `CON_ID` mapping—never use sample numbers. When working on a PDB, verify container context and file state; you may need to close the PDB or take the datafile/tablespace offline per release guidelines. Never restore a PDB's datafile without confirming which container owns it.

## 7. Checking PDB and Datafile Mapping

From root, list PDBs:

```sql
SELECT con_id,
       name,
       open_mode,
       restricted
FROM v$pdbs
ORDER BY con_id;
```

Inspect datafiles by container:

```sql
SELECT con_id,
       file_id,
       tablespace_name,
       file_name,
       status
FROM cdb_data_files
ORDER BY con_id, file_id;
```

For tempfiles:

```sql
SELECT con_id,
       file_id,
       tablespace_name,
       file_name,
       status
FROM cdb_temp_files
ORDER BY con_id, file_id;
```

Inspect files at the database level:

```sql
SELECT file#, name, status, enabled
FROM v$datafile
ORDER BY file#;
```

Query `CDB_*` views from root with proper privileges. When connected inside a PDB, `CDB_*` views may not show full CDB-wide data as expected.

## 8. TDE, Wallets, and Security Prerequisites

If a CDB/PDB uses Transparent Data Encryption (TDE), datafile backups alone cannot decrypt data without the required keystore/wallet and encryption keys. Before restoring to a new host or opening a PDB after recovery:

- Identify the keystore type and configured location.
- Restore or stage the wallet or external keystore in the target environment per security procedures.
- Confirm required master encryption keys still exist and can be opened.
- Check keystore status inside the appropriate container.
- Never place wallet passwords or key material in unprotected scripts, logs, or chats.

A PDB opening cleanly does not always prove all encrypted objects are readable. Test querying TDE-encrypted objects post-recovery using a controlled test account.

## 9. Differences Among Restore, Recover, Flashback, and Plug/Unplug

| Mechanism | Function | When to Use |
|---|---|---|
| RMAN `RESTORE` | Copies backup datafiles/control file/SPFILE to target locations | Files are lost/damaged or must be rebuilt from backup |
| RMAN `RECOVER` | Applies archived redo/redo to bring files/database to a consistent target | After restore or when media recovery is required |
| Flashback Database | Rewinds the database to an earlier time using flashback logs when configured | Fast recovery from certain logical errors without restoring whole backups |
| PDB PITR | Returns a single PDB to a target SCN/time via RMAN | Logical errors confined to one PDB |
| Unplug/plug PDB | Moves a PDB using an XML manifest/datafiles or archive | Moving/cloning a PDB between compatible CDBs |
| Data Pump | Exports/imports logical objects and data | Logical migration or schema/table-level object recovery |

`RESTORE` and `RECOVER` are two distinct steps: restore retrieves copies from backup; recover applies redo to reach the target. `FLASHBACK` does not replace a backup strategy. Unplug/plug is a container relocation mechanism requiring compatibility checks, not a substitute for RMAN media recovery.

## 10. Reopening CDB/PDB and Post-Recovery Verification

After RMAN completes, verify database status:

```sql
SELECT name,
       open_mode,
       database_role,
       log_mode,
       resetlogs_change#,
       resetlogs_time
FROM v$database;

SELECT con_id,
       name,
       open_mode,
       restricted
FROM v$pdbs
ORDER BY con_id;
```

Check datafiles:

```sql
SELECT con_id,
       file#,
       status,
       error,
       recover
FROM v$datafile_header
ORDER BY con_id, file#;
```

Check recovery status and remaining violations:

```sql
SELECT *
FROM v$recover_file;

SELECT name, cause, type, status, message, action
FROM pdb_plug_in_violations
ORDER BY name, time;
```

Then confirm:

- The recovered PDB is open in the proper mode (`READ WRITE` or requested mode).
- Unrelated PDBs remain in their expected states.
- No unexpected datafiles still require recovery.
- Services are registered and applications connect to the right PDB/service.
- The TDE keystore is open and encrypted data is readable.
- Critical business SQL queries return expected data as of the recovery point.
- Jobs, schedulers, database links, directories, and external dependencies work normally.
- A fresh backup is taken after PITR/`RESETLOGS` per backup policy.

If a CDB/PDB just opened after incomplete recovery or resetlogs, verify database incarnation and catalog metadata so RMAN selects the right backups/archived logs for subsequent backups.

## 11. Common Errors and Edge Cases to Watch

### 11.1. Missing Required Archived Logs

If a log is missing from the chain between backup and target SCN, RMAN cannot complete recovery to the target. You can recover to an earlier SCN/time where logs are intact, provided data loss and application consistency are evaluated.

### 11.2. Backups Belonging to a Different DBID or Incarnation

Backup pieces may belong to another database or incarnation. Verify DBID, `LIST INCARNATION`, repository, and catalog configuration before use. Never catalog or restore backups of unknown origin into production.

### 11.3. Wrong Paths or Insufficient Space

Restores fail if ASM disk groups, filesystems, channels, or auxiliary destinations are unavailable. Provision ample space for datafiles, archived logs, FRA, and auxiliary files; check OS permissions and storage mounts before starting.

### 11.4. PDB Incompatible with Target CDB

PDB plug-in can be blocked by release, option, character set, endianness, or component mismatches. Use `DBMS_PDB.CHECK_PLUG_COMPATIBILITY` and `PDB_PLUG_IN_VIOLATIONS`; resolve violations per Oracle guidelines instead of bypassing them.

### 11.5. CDB/PDB Not in the Required State

Whole-CDB restore normally requires the instance in `MOUNT`; PDB-specific recovery may require the PDB closed. Check current state before running. Never perform recovery on a PDB actively taking transactions if release procedures require it closed.

## 12. Recovery Rehearsal Procedure

A backup is only truly useful when it can be restored/recovered within RTO. Rehearse in a non-production environment:

1. Record Oracle release, RU, DBID, CDB/PDB list, `COMPATIBLE`, platform, and TDE configuration.
2. Create CDB/PDB backups with archived logs; preserve control file/SPFILE autobackups and RMAN metadata.
3. Verify backups with `CROSSCHECK`, `PREVIEW`, and `RESTORE ... VALIDATE`.
4. Simulate losing a datafile inside a PDB and execute PDB recovery.
5. Simulate a logical error and execute PDB PITR to a known SCN/time.
6. Simulate losing the control file or host and rehearse whole-CDB restore/recovery.
7. Measure duration of each step, auxiliary space usage, PDB open time, and application reconnection time.
8. Verify post-recovery data, PDB violations, TDE, services, and jobs.
9. Document errors encountered, commands used, required privileges, actual timings, and automation candidates.
10. Update runbooks for the exact release/RU and re-verify after major upgrades.

## 13. Principles to Remember

- Always determine whether recovery scope is CDB, PDB, tablespace, or datafile before restoring.
- Execute CDB/PDB administrative actions from the proper container with appropriate privileges; RMAN PDB operations are controlled from CDB root.
- Verify release, RU, `COMPATIBLE`, DBID, incarnation, platform/endianness, and PDB plug-in compatibility before restoring or migrating.
- Ensure valid backups and archived redo logs cover up to the target SCN/time; verify control file, SPFILE, and TDE keys.
- `RESTORE` retrieves files from backup; `RECOVER` applies redo; `OPEN RESETLOGS` is used only when required by the recovery type.
- PDB PITR confines blast radius to the selected PDB, though it discards changes past the recovery point within that PDB.
- `PREVIEW` verifies backup selection; `VALIDATE` verifies readability/restorability; only restore rehearsals prove operational readiness.
- Post-recovery, verify datafiles, PDBs, services, TDE, and business data, and take a fresh backup per policy.

## Oracle Reference Documentation

- [Oracle Database 19c Backup and Recovery User's Guide — RMAN Backup and Recovery of CDBs and PDBs](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/)
- [Oracle Database 19c Backup and Recovery Reference — RMAN Commands](https://docs.oracle.com/en/database/oracle/oracle-database/19/rcmrf/)
- [Oracle Database 19c Multitenant Administrator's Guide — Managing PDBs](https://docs.oracle.com/en/database/oracle/oracle-database/19/multi/)
- [Oracle Database 19c Reference — V$DATABASE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-DATABASE.html)
- [Oracle Database 19c Reference — V$PDBS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-PDBS.html)
- [Oracle Database 19c Reference — PDB_PLUG_IN_VIOLATIONS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/PDB_PLUG_IN_VIOLATIONS.html)
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_PDB](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_PDB.html)
