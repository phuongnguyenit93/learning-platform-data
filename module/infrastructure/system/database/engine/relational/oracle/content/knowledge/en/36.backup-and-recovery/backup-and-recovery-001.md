# Distinguishing Backup, Restore, Recovery, and RPO/RTO Requirements in Oracle

## 1. Four Concepts That Must Be Distinguished

In Oracle Database operations, backup, restore, and recovery are related steps, not synonyms. RPO and RTO are two business objectives used to design and evaluate recoverability.

- **Backup:** creating a copy of the data and metadata needed to recover in the event of a failure.
- **Restore:** copying data from a backup back to the recovery location, such as restoring a datafile or control file.
- **Recovery:** applying the necessary redo, archived redo logs, and incremental backups to bring a database or part of a database to a desired consistent state.
- **RPO (Recovery Point Objective):** the maximum amount of data an organization is willing to lose, usually expressed as a time interval.
- **RTO (Recovery Time Objective):** the maximum acceptable time to restore a service to its defined operating level.

Example: a system has an RPO of 15 minutes and an RTO of 2 hours. If an incident occurs at 10:00, the organization targets data recovered to no older than around 9:45 and service restored within 2 hours. These are design targets; only recovery testing proves whether the system actually meets them.

This lesson belongs to the **Backup and Recovery** chapter in the **Database Engine Relational Oracle** module. It explains how RMAN creates backups, restores datafiles/control files, recovers using redo, selects a recovery point, designs for RPO/RTO, prepares for disaster recovery, and conducts periodic testing.

## 2. Backup: Creating a Recoverable Copy

A backup is data stored separately from the active dataset to protect against hardware failures, human error, block corruption, software bugs, site loss, or destructive attacks.

A backup is only valuable when:
- It contains all components needed for recovery.
- It is stored on appropriate, accessible storage.
- Metadata exists to locate and identify its contents.
- Decryption keys are available if the backup is encrypted.
- Necessary archived redo logs exist for the recovery target.
- It has been verified and tested through restore/recovery.

A successful backup command alone does not prove that a database can be recovered to any point in time. You must account for datafiles, control files, SPFILE, archived redo logs, TDE keystore/wallet, Oracle Net configuration, and external dependencies.

### 2.1. What Needs to Be Backed Up?

| Component | Role During Recovery |
|---|---|
| Datafiles | Store data and database structure |
| Control file | Records database structure, datafiles, checkpoints, and backup metadata |
| SPFILE or PFILE | Holds instance startup configuration |
| Archived redo logs | Allow rolling forward past the backup point in time |
| Online redo logs | Contain the most recent redo; their condition can determine data salvageability |
| TDE keystore/wallet | Provides keys to open encrypted data |
| RMAN recovery catalog | Stores long-term backup metadata and repository information if used |
| Password file | May be required for remote administrative authentication |
| Oracle Net/configuration | Enables applications and tools to reconnect |
| External dependencies | Wallets, credentials, external files outside the database, application and storage configurations |

RMAN focuses on backing up database files and archived redo. Components such as application configurations, secret managers, external files, and service startup procedures must be protected in the overall plan.

### 2.2. Physical Backup vs. Logical Backup

**Physical backup** stores the physical components of the database, such as datafiles, control files, and archived redo. Oracle Recovery Manager (RMAN) is the primary tool for performing physical backup and recovery.

**Logical backup** exports objects and data at the logical level, such as Oracle Data Pump `expdp`. Logical exports are useful for schema migration, object recovery, or data exchange, but they do not replace RMAN for full database recovery after losing datafiles or control files.

Both types may be needed:
- RMAN for disaster recovery and media recovery.
- Data Pump for object recovery, data migration, or selective business-level recovery.

### 2.3. A Backup Is Not a Live Synchronized Copy

A backup typically reflects data at a specific point in time or across a time window with a consistency mechanism. It does not necessarily contain the latest changes.

If the last backup was taken at 01:00 and the database fails at 10:00, recovering close to 10:00 requires complete redo/archived redo from the backup up to the target point. Missing logs can cause the actual RPO to exceed the target.

## 3. Restore: Bringing the Backup Back to the Recovery Location

Restore is the operation of retrieving files from a backup or image copy and placing them back into the location Oracle will use.

Examples:
- Restoring a lost datafile.
- Restoring the entire database after storage failure.
- Restoring the control file when the control file is lost.
- Restoring the SPFILE to start the instance.
- Restoring a tablespace as part of an appropriate recovery procedure.

Restore only returns files to their backed-up state. If the database had changes after the backup time, those changes do not automatically appear in the restored files.

### 3.1. Example RMAN RESTORE Commands

In RMAN, the general syntax is:

```sql
RESTORE DATABASE;
```

This command instructs RMAN to select appropriate backups and restore the database datafiles according to the repository, configuration, and current state.

Restore the control file:

```sql
RESTORE CONTROLFILE FROM AUTOBACKUP;
```

Restore the SPFILE:

```sql
RESTORE SPFILE FROM AUTOBACKUP;
```

These commands are examples for an environment where autobackup is configured and backup pieces are accessible. If both the control file and SPFILE are lost, you may need to start the instance in the appropriate state, specify the DBID, and configure channels/paths according to Oracle documentation.

### 3.2. Restore Does Not Mean the Database Can Be Opened

After a restore, datafiles are typically at the backup's checkpoint time. Files may not yet be synchronized to the same SCN. Oracle requires recovery to apply redo and bring the files to a consistent state.

Therefore, a media recovery workflow typically looks like:

```sql
RESTORE DATABASE;
RECOVER DATABASE;
```

Only after recovery meets the appropriate condition to open the database should you execute the open command suitable for the situation.

### 3.3. Restore Can Take Significant Time

Restore duration depends on:
- The volume of backup data to read.
- Backup storage and network throughput.
- The number of RMAN channels.
- Backup set vs. image copy format.
- Compression/encryption overhead.
- Parallel read capability.
- Target datafile location and storage write speed.

RTO must account for actual restore time, not just the recovery command execution time.

## 4. Recovery: Applying Changes to Reach a Consistent Database State

Recovery is the process of using redo and required backups to bring a database or datafile to a consistent point. Oracle can apply:
- Archived redo logs.
- Usable online redo logs.
- Incremental backups.
- Redo generated after the incremental backup.

During media recovery, RMAN or Oracle recovers datafiles by rolling forward the required changes. When necessary, Oracle also applies undo to ensure uncommitted transactions do not appear as committed data.

### 4.1. Example RMAN RECOVER

```sql
RESTORE DATABASE;
RECOVER DATABASE;
```

`RESTORE DATABASE` retrieves the datafiles from backup. `RECOVER DATABASE` applies the necessary incremental backups and redo to synchronize the datafiles to the chosen recovery point.

### 4.2. Complete Recovery

Complete recovery brings the database/datafile to the latest possible point based on available redo, typically the current time or the last point where complete redo exists.

For example, if the database loses one datafile while the control file and archived redo remain intact, the DBA restores that datafile from an older backup and applies archived redo and online redo to bring it to the same state as the rest of the database.

### 4.3. Incomplete Recovery and Point-in-Time Recovery

Incomplete recovery stops at a point prior to the current time, for example:
- Before a user accidentally deleted data.
- Before a transaction that caused a logical error.
- Before an application deployment corrupted data.
- A chosen SCN, timestamp, or log sequence.

After incomplete recovery, the database typically needs to be opened with `RESETLOGS` per Oracle procedure. This creates a new database incarnation. Subsequent backups and incarnation history must be managed carefully.

### 4.4. Recovery Does Not Always Require Restoring the Entire Database

If only one datafile is damaged and other files are intact, you can restore/recover just that datafile. If an error is confined to a single tablespace, you can consider tablespace point-in-time recovery or an appropriate recovery procedure. If only a single table is lost, you can use RMAN table recovery on supported releases, or Data Pump/Flashback depending on the scenario.

Choose the smallest recovery scope that meets the requirement without compromising database consistency.

## 5. ARCHIVELOG and NOARCHIVELOG

The logging mode directly affects the ability to perform online backups and recover to the most recent point in time.

### 5.1. ARCHIVELOG Mode

In `ARCHIVELOG` mode, Oracle saves filled online redo logs as archived redo logs before reusing those redo groups. Archived logs enable recovery across multiple points in time after a backup.

Benefits:
- Supports online backups with RMAN per Oracle procedures.
- Supports media recovery up to the point where complete redo exists.
- Supports Data Guard and other data protection architectures.
- Can meet an RPO smaller than the interval between database backups.

In return, you must provision storage capacity and manage archived logs. If the archive destination fills up, the database can be severely impacted when it can no longer archive redo.

Check the mode:

```sql
SELECT log_mode
FROM v$database;
```

### 5.2. NOARCHIVELOG Mode

In `NOARCHIVELOG` mode, Oracle does not retain archived redo logs for filled online redo logs. Recoverability is generally limited to consistent offline backups and whatever redo still remains.

For critical databases requiring continuous operation and low RPO, NOARCHIVELOG is usually unsuitable. A consistent offline backup can restore the database to the backup point, but you cannot roll forward across periods without archived redo.

### 5.3. Switching to ARCHIVELOG

Changing archive mode requires stopping and mounting the database per DBA procedure. General example:

```sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
ALTER DATABASE ARCHIVELOG;
ALTER DATABASE OPEN;
```

After switching modes, verify archive destination configuration, disk space, monitoring, and take a new baseline backup. Do not run this on production without a change plan, maintenance window, and appropriate backups.

### 5.4. Online Backup and Consistency

In ARCHIVELOG mode, RMAN can back up the database while it is open using the hot backup mechanism. RMAN manages consistency using checkpoints and required redo.

In NOARCHIVELOG mode, obtaining a consistent database backup typically requires a clean shutdown and backing up while the database is in the appropriate mount state. Details depend on architecture and version; never treat OS-level copying of open datafiles as a valid backup.

## 6. RMAN: Oracle's Primary Backup and Recovery Tool

Recovery Manager (RMAN) is the Oracle tool provided to:
- Back up databases, tablespaces, datafiles, and archived redo.
- Restore from backup sets or image copies.
- Recover using incremental backups and redo.
- Validate backups and check for block corruption.
- Manage retention and obsolete backups.
- Track repository metadata.

RMAN can use the control file as its repository or use a separate recovery catalog.

### 6.1. Connecting to RMAN

Local connection example:

```text
rman target /
```

Connects to the target database using OS authentication when the environment permits. You can connect to a recovery catalog if your organization deploys one. Do not pass real passwords on the command line or leave them in shell history.

### 6.2. Backing Up the Database and Archived Logs

Example:

```sql
BACKUP DATABASE PLUS ARCHIVELOG;
```

This command instructs RMAN to back up the database along with the required archived redo logs according to its workflow. Ensure the archive destination has enough free space and the backup destination is operational.

You can specify a tag:

```sql
BACKUP DATABASE TAG 'WEEKLY_DB_BACKUP';
```

Tags help identify backup groups in the repository; tags do not replace a retention policy or backup catalog.

### 6.3. Backing Up the Control File and SPFILE

```sql
BACKUP CURRENT CONTROLFILE;
BACKUP SPFILE;
```

You can configure autobackup:

```sql
CONFIGURE CONTROLFILE AUTOBACKUP ON;
```

Control file autobackup is critical because the control file contains database structure and backup metadata. The SPFILE is needed to start the instance with the correct configuration. For databases using an SPFILE, RMAN autobackup can include the SPFILE according to Oracle configuration and rules.

### 6.4. Backing Up Archived Redo Logs

```sql
BACKUP ARCHIVELOG ALL;
```

Do not delete archived redo logs merely because files were copied elsewhere. Use RMAN to manage backups, retention, and log deletion according to an approved policy. Deleting logs that have not been backed up or are still needed for standby/recovery can destroy recoverability.

## 7. RMAN Backup Types

### 7.1. Backup Set

A backup set is an RMAN format that packages data blocks into one or more backup pieces. This is the common format used by `BACKUP`.

Advantages:
- Can skip certain unused blocks per RMAN mechanisms.
- Supports compression and encryption depending on configuration/edition.
- Can be split into multiple backup pieces.
- Managed through the RMAN repository.

### 7.2. Image Copy

An image copy is a file copy corresponding to a datafile/control file in a format that can be used directly as a database file once switched/placed in the proper location.

Advantages:
- Can switch the database to an image copy in certain workflows.
- Useful for incremental merge strategies.
- Avoids unpacking backup sets in certain restore scenarios.

Image copies typically consume space close to the size of the copied file. Plan storage capacity and creation time accordingly.

### 7.3. Full Backup and Level 0

In RMAN, distinguish between:
- **Full backup:** backs up all required blocks per RMAN semantics, but does not serve as the base for level 1 incremental backups.
- **Incremental level 0:** a baseline backup containing used blocks that can serve as the base for subsequent level 1 incremental backups.

Level 0 example:

```sql
BACKUP INCREMENTAL LEVEL 0 DATABASE;
```

If you want to build an incremental strategy, level 0 is the appropriate baseline.

### 7.4. Incremental Level 1 Differential

A level 1 differential backup contains blocks changed since the most recent level 0 or level 1 backup, depending on the incremental strategy. This is the default choice when `CUMULATIVE` is not specified.

```sql
BACKUP INCREMENTAL LEVEL 1 DATABASE;
```

During restore, RMAN needs the level 0 backup, the relevant level 1 backups, and redo to roll forward.

### 7.5. Incremental Level 1 Cumulative

A level 1 cumulative backup contains blocks changed since the most recent level 0 backup.

```sql
BACKUP INCREMENTAL LEVEL 1 CUMULATIVE DATABASE;
```

Cumulative backups typically grow larger than differential backups over time, but can reduce the number of incremental backups that need to be applied during recovery.

### 7.6. Comparing Differential and Cumulative

| Criterion | Level 1 Differential | Level 1 Cumulative |
|---|---|---|
| Comparison base | Most recent level 0 or level 1 | Most recent level 0 |
| Size per backup | Usually smaller | Usually larger |
| Backups to apply | Potentially more | Usually fewer |
| Backup duration | Usually shorter | Potentially longer |
| Recovery time | May need to apply multiple levels | Usually fewer levels |
| Best suited for | Saving storage and backup window | Prioritizing fewer apply steps during restore |

Actual results depend on block change rate, backup schedule, and workload.

### 7.7. Block Change Tracking

Block Change Tracking (BCT) helps RMAN identify changed blocks to accelerate incremental backups in supported configurations. BCT reduces the work of scanning for changed blocks, though it does not eliminate reading the data to be backed up.

BCT requires a tracking file and capacity/location management. Enable or relocate the tracking file according to release documentation and DBA procedures.

## 8. Designing a Backup Schedule

A backup schedule should reflect RPO, RTO, data change rate, and restore time.

Illustrative schedule example:
- Sunday: level 0.
- Monday through Saturday: level 1 differential.
- Every 15 minutes: back up archived redo logs.
- Daily: back up control file/SPFILE via autobackup or controlled job.
- Weekly: run restore validate checks.
- Quarterly: conduct recovery drills in an isolated environment.

This is not a universal schedule for all systems. If the RPO is 5 minutes, backing up archived redo every 15 minutes does not meet that objective. More frequent log backups, Data Guard, or another protection solution may be required.

### 8.1. Example RMAN Retention Configuration

```sql
CONFIGURE RETENTION POLICY TO RECOVERY WINDOW OF 14 DAYS;
```

A recovery window is the period over which the backup strategy must allow recovery to any point in time within that window, provided the required backups and redo remain available.

Another option is redundancy:

```sql
CONFIGURE RETENTION POLICY TO REDUNDANCY 2;
```

Redundancy retains the required number of backup copies according to policy. Do not configure retention based solely on disk space; consider RPO/RTO, regulatory retention requirements, and offsite backups.

### 8.2. Backup Destination and FRA

The Fast Recovery Area (FRA) can store backups, archived redo, flashback logs, and other recovery files. Monitor:
- Total capacity and used space.
- Archived redo generation rate.
- Old/obsolete backup pieces.
- Flashback logs.
- Archive destination status.
- Low-space alerts.

Do not treat the FRA as the sole backup location. If storage/FRA is lost along with the database, backups stored there can also be lost. An independent copy on separate storage or another site is needed per disaster recovery requirements.

## 9. RPO and RTO: Two Distinct Objectives

### 9.1. RPO — Recovery Point Objective

RPO is the maximum amount of data an organization accepts losing after an incident, expressed as the time interval from the recovered data point to the time of the incident.

Examples:
- 24-hour RPO: acceptable to recover to the previous day's backup in defined scenarios.
- 1-hour RPO: requires backups/redo or data protection mechanisms ensuring the recovery point does not fall back more than one hour.
- Near-zero RPO: requires appropriate replication/standby solutions and operations; periodic backups alone are usually insufficient to guarantee this.

RPO is not the same as database backup frequency. With ARCHIVELOG and complete archived redo, you can recover to a point in time after the database backup. Conversely, if a segment of archived redo is missing, the recovery point may have to roll back prior to that gap.

### 9.2. RTO — Recovery Time Objective

RTO is the maximum time allowed to restore a service to its defined operating level after an incident.

RTO is not just the execution time of `RESTORE DATABASE`. You must include:
- Incident detection and triage.
- Decision to fail over or restore.
- Infrastructure/storage provisioning.
- Restoring datafiles and control files.
- Applying incremental backups and redo.
- Opening the database and verifying consistency.
- Starting listeners, services, and applications.
- Verifying data and business logic.
- Gradually restoring user traffic.

If the database opens after 45 minutes but the application takes another 90 minutes to verify and reconnect, service RTO must include that entire duration.

### 9.3. RPO/RTO Examples

| System | Target RPO | Target RTO | Design Suggestion |
|---|---:|---:|---|
| Internal reporting | 24 hours | 8 hours | Scheduled backups, restore tests |
| Business application | 15 minutes | 2 hours | ARCHIVELOG, frequent log backups, restore rehearsals |
| Critical transactions | 1 minute | 15 minutes | Consider standby, redo transport/apply, failover runbook |
| Near-continuous service | Near 0 | A few minutes | Dedicated HA/DR architecture, failover testing |

These figures are illustrative examples. RPO/RTO must be approved by system owners and the business based on the cost of downtime and data loss.

### 9.4. RPO and RTO Can Have Cost Trade-offs

Lower RPO typically requires more frequent or synchronous redo protection. Lower RTO typically requires standby infrastructure, copies at another site, automation, and testing. Lowering both targets increases operational cost.

Do not set RPO/RTO based purely on technical preference. The organization must evaluate acceptable loss, compliance requirements, SLAs, and budget.

## 10. Mapping RPO/RTO to an Oracle Strategy

### 10.1. RPO Is Primarily Determined by Redo Preservation

A nightly database backup can meet a 24-hour RPO if the organization accepts losing a day's data. For a 15-minute RPO, archived redo must be backed up or shipped to a safe site at a suitable frequency and latency.

If near-zero RPO is required, evaluate Data Guard synchronous transport or another protection solution suited to the architecture. Never claim zero RPO simply because a standby exists; verify transport mode, protection mode, network, and apply status.

### 10.2. RTO Is Primarily Determined by Recovery Speed and Readiness

RTO can be reduced through:
- High-throughput backup storage.
- Benchmarked RMAN channels/parallelism.
- Image copies or incremental merge where appropriate.
- A ready standby database.
- Automated runbooks.
- Pre-provisioned DR infrastructure.
- Regular failover/restore testing.
- Clear application and DNS/network procedures.

Increasing RMAN parallelism does not automatically make restores faster if storage, CPU, network, or encryption is already the bottleneck.

### 10.3. Selection Matrix

| Objective | Components to Evaluate |
|---|---|
| RPO of several hours | Scheduled database and archived redo backups |
| RPO of a few minutes | Frequent archived redo backup/transport, archive gap monitoring |
| Near-zero RPO | Data Guard protection mode and synchronous transport as required |
| RTO of several hours | Rehearsed RMAN restore/recovery, ready storage |
| RTO under one hour | Restore acceleration, image copies, or standby/failover |
| RTO of a few minutes | HA/DR with automatic or semi-automatic failover and tested runbooks |

HA/DR solutions do not replace backups. Logical corruption or accidental deletions can be replicated to the standby, so independent backups and point-in-time recovery capabilities remain essential.

## 11. Restoring and Recovering a Database with RMAN

### 11.1. Scenario: Losing a Datafile

Suppose one datafile is lost while the control file, SPFILE, and archived redo remain usable.

General procedure:
1. Identify the damaged/lost datafile.
2. Identify valid backups and required archived redo.
3. Restore the datafile.
4. Recover the datafile.
5. Verify online status and database consistency.
6. Check the application and alert log.

Example:

```sql
RESTORE DATAFILE 7;
RECOVER DATAFILE 7;
```

Number 7 is an example. Confirm the exact file number, file name, and status before executing.

### 11.2. Scenario: Losing All Database Files

When datafiles are widely lost:
1. Restore the control file if necessary.
2. Mount the database.
3. Catalog backup pieces if the repository is unaware of the backup location.
4. Restore the database.
5. Recover the database.
6. Open the database via the appropriate complete/incomplete recovery path.
7. Verify the database and application.

Example command structure:

```sql
STARTUP MOUNT;
RESTORE DATABASE;
RECOVER DATABASE;
```

If the control file is lost, the procedure requires restoring the control file first and remounting per Oracle guidelines. Do not run example commands verbatim in production without confirming the current state and recovery target.

### 11.3. Cataloging Backup Pieces

If backups were copied to a new location and the RMAN repository lacks metadata, you may need to catalog the files:

```sql
CATALOG START WITH '/backup/restore_area/';
```

The path is an example. Verify the exact directory and only catalog valid backup pieces. Do not use this command as a substitute for verifying backup identity or integrity.

### 11.4. Checking Whether Backups Can Be Restored

```sql
RESTORE DATABASE PREVIEW;
```

PREVIEW shows which backups RMAN plans to use and related requirements; it does not restore files.

```sql
RESTORE DATABASE VALIDATE;
```

VALIDATE checks readability/availability of the required backups within the command scope; it does not replace an actual restore/recovery. Certain classes of failure only surface during a full rehearsal in a recovery environment.

## 12. Point-in-Time Recovery (PITR)

PITR recovers a database or supported scope to a point prior to the present, typically to undo an incorrect logical change or operational error.

### 12.1. Selecting a Point by Time or SCN

RMAN supports specifying the target point with `UNTIL TIME`, `UNTIL SCN`, or appropriate options such as sequence. Illustrative example:

```sql
RUN {
    SET UNTIL TIME
        "TO_DATE('2026-11-14 09:30:00',
                 'YYYY-MM-DD HH24:MI:SS')";
    RESTORE DATABASE;
    RECOVER DATABASE;
}
```

The timestamp and timezone must be verified accurately. For logical data incidents, identify the SCN or time of the offending transaction to avoid recovering farther back than necessary.

### 12.2. Opening the Database After Incomplete Recovery

After database point-in-time recovery, the procedure typically requires:

```sql
ALTER DATABASE OPEN RESETLOGS;
```

`RESETLOGS` starts a new incarnation. Immediately afterward, take a new backup and verify the RMAN repository/incarnation state. Never use `OPEN RESETLOGS` as a generic fix when a database fails to open.

### 12.3. TSPITR and Table Recovery

- **Tablespace point-in-time recovery (TSPITR):** recovers a single tablespace to a prior point in time while the rest of the database remains at the current state, subject to Oracle's conditions and procedures.
- **RMAN table recovery:** some releases support recovering a table or table partition to a point in time by creating an auxiliary instance and re-importing the object. Syntax and limitations depend on release.
- **Data Pump:** can re-import objects from a logical export.
- **Flashback:** can recover certain operational errors without a full database restore if sufficient undo data and flashback logs remain.

Choose the right tool based on incident scope. Recovering a single table to an older point is not the same as recovering the whole database; you must evaluate foreign keys, dependencies, transactions, and data created after that point.

## 13. Control File, SPFILE, and Recovery Catalog

### 13.1. Control File

The control file records database structure, checkpoints, datafiles, redo logs, and backup metadata. Losing the control file can prevent the database from mounting.

Protect it using:
- Multiplexing control files across separate locations/storage.
- RMAN autobackup.
- Frequent control file backups.
- Offsite copies.
- A runbook for restoring the control file and mounting the database.

Multiplexing protects against losing a single control file copy, but does not protect against losing an entire storage system/site if all copies share the same failure domain.

### 13.2. SPFILE

The SPFILE stores startup parameters. A lost SPFILE can be recovered from autobackup or a managed PFILE. Maintain configuration copies and document critical parameter changes.

### 13.3. Recovery Catalog

The RMAN repository can reside in the control file or in a separate recovery catalog. A catalog stores backup metadata and longer history depending on configuration.

A recovery catalog is useful when:
- Managing multiple databases.
- Retaining long-term backup metadata.
- Tracking incarnations and backup history.
- Supporting certain centralized management features.

The catalog does not contain datafile copies and does not replace backup storage. Protect the catalog database itself like any other critical system.

## 14. Archived Redo Logs: The Critical Link in Recovery

### 14.1. Backing Up Archived Redo Frequently

Example:

```sql
BACKUP ARCHIVELOG ALL;
```

You can use `BACKUP DATABASE PLUS ARCHIVELOG` in jobs to combine database and log backups. Log backup frequency must satisfy RPO and redo generation rate.

### 14.2. Archive Gap

If an archived redo log is missing from the required sequence, recovery may not be able to advance past that gap. DBAs must monitor:
- Archive destination status.
- Sequences generated and backed up.
- Log deletion policy.
- Standby archive gaps if using Data Guard.
- Network transfer and apply lag.
- FRA and filesystem capacity.

### 14.3. Do Not Delete Logs Using OS Commands

Do not manually delete archived redo files with `rm` or `del` while RMAN/the database still manages them. Use RMAN and a deletion policy to remove logs only when backup/standby conditions are met.

Example repository check:

```sql
LIST ARCHIVELOG ALL;
```

Check backups:

```sql
LIST BACKUP OF ARCHIVELOG ALL;
```

## 15. Verifying Backups and Recoverability

### 15.1. CROSSCHECK

```sql
CROSSCHECK BACKUP;
CROSSCHECK ARCHIVELOG ALL;
```

CROSSCHECK reconciles RMAN metadata with file existence on storage or media manager. It does not read the entire backup contents to prove recoverability.

### 15.2. REPORT OBSOLETE and DELETE OBSOLETE

```sql
REPORT OBSOLETE;
```

This command lists backups no longer needed under the current retention policy.

After DBA review:

```sql
DELETE OBSOLETE;
```

Do not delete backups based solely on file age or filesystem operations. You must understand retention, redundancy, recovery window, and legal/compliance retention requirements.

### 15.3. VALIDATE

```sql
VALIDATE DATABASE;
```

VALIDATE checks files/blocks within the scope and capabilities of the command. You can use:

```sql
BACKUP VALIDATE CHECK LOGICAL DATABASE;
```

`CHECK LOGICAL` requests additional checking for logical block corruption and incurs CPU overhead. Schedule appropriately, monitor output, and handle any corruption per Oracle guidelines.

### 15.4. Restore Rehearsal

The most valuable test is an actual restore/recovery into an isolated environment:
1. Prepare the recovery server/storage.
2. Retrieve backups from independent storage.
3. Restore the control file/SPFILE if needed.
4. Restore datafiles.
5. Apply archived redo.
6. Open the database per procedure.
7. Verify objects and business data.
8. Measure the duration of each phase.
9. Document errors, missing permissions, missing keys, and dependencies.
10. Clean up the environment per procedure.

VALIDATE is helpful, but it does not replace a restore rehearsal. Only a full rehearsal tests backup media, network, keys, configuration, runbooks, and operational skills end to end.

## 16. Protecting Backups and Encryption Keys

A backup can contain all production data, so it must be protected just as strictly as the running database.

### 16.1. Encryption

RMAN supports backup encryption depending on configuration and version/edition requirements. If backups are encrypted, you must protect the password or keystore needed for decryption.

Do not store encryption passwords next to backup pieces in the same directory or with the same access permissions. Manage keys under a secret management policy and maintain a tested key recovery procedure.

### 16.2. TDE Keystore

If datafiles use TDE, restoring files without the appropriate keystore/master key can render the data unreadable. The backup plan must cover:
- Keystore/wallet.
- Passwords/secrets to open the keystore.
- Key history needed for older backups.
- Key restoration procedures on the DR host/site.
- Restore testing for encrypted databases.

Do not delete old keys simply because the master key was rotated. Older backups may still depend on those keys.

### 16.3. Offsite and Immutable Backups

Maintain at least one backup copy in a separate failure domain:
- Storage or object store at another site.
- Separate administrative accounts/privileges.
- Immutable/WORM or object lock when supported by the architecture.
- Backup credentials separated from database credentials.
- Monitoring of backup deletion/modification.
- Access testing from the DR site.

If ransomware can delete both the database and backups using the same administrative account, the backup is no longer an independent layer of protection.

## 17. Data Guard, Flashback, and Other Protection Layers

### 17.1. Data Guard Does Not Replace Backups

Data Guard maintains a standby by shipping and applying redo. It can reduce RPO/RTO during a site or instance failure depending on protection mode and configuration.

However, logical errors, accidental deletions, or bad data can be replicated to the standby. Independent backups and PITR remain necessary.

### 17.2. Flashback Database

Flashback Database can return a database to an earlier point in time using flashback logs when enabled and sufficient flashback data exists. It can be faster than traditional restore/recovery in certain scenarios.

Flashback does not replace backups because flashback logs have limited retention and storage space, and do not fully protect against total storage or site loss.

### 17.3. Flashback Table and Data Pump

Flashback Table can restore a table to a prior state within supported limits. Data Pump can recover objects from an export. Both are useful for narrow-scope errors, but require checking dependencies, constraints, transactions, and application consistency.

## 18. Calculating RTO from Real Steps

Example stages from a restore rehearsal:

| Stage | Measured Time |
|---|---:|
| Detection and decision | 10 minutes |
| Storage/host provisioning | 15 minutes |
| Restore control file and SPFILE | 5 minutes |
| Restore datafiles | 45 minutes |
| Apply incremental backups and archived redo | 25 minutes |
| Open database and verify | 10 minutes |
| Start applications / switch traffic | 15 minutes |
| Total | 125 minutes |

If the RTO is 2 hours (120 minutes), this runbook misses the target. You must shorten one or more stages, pre-provision infrastructure, or choose a DR architecture with shorter failover time.

This is an illustrative example. Times must be measured using real data and storage, including approval wait times, privilege elevation, and business validation.

### 18.1. Allocating the RTO Budget

Do not spend the entire RTO budget on restore alone. Allocate time for:
- Detection.
- Decision/authorization.
- Infrastructure.
- Database restore/recovery.
- Application startup.
- Validation.
- Traffic restoration.

Include a time buffer because real incidents may progress more slowly than rehearsals.

### 18.2. Service RTO Differs from Database RTO

The database may be open while the application is still unavailable because:
- Listener/services are not yet registered.
- DNS or load balancer has not updated.
- Secrets/wallets are missing on the DR host.
- Jobs or schedulers are not yet enabled.
- Queues/message brokers are still failing.
- Caches or session state need initialization.
- User traffic has not been routed over.

SLAs should clearly define what "service recovered" means: database OPEN, health checks passing, or the first business transaction completing.

## 19. Calculating RPO from Backups and Redo

Suppose:
- Last database backup was at 01:00.
- Archived redo is backed up every 10 minutes.
- An incident occurs at 10:00.
- The archived redo chain is complete and accessible.

If the last redo backup completed at 09:50, the recovery point might advance beyond 09:50 if newer archived logs remain on accessible storage or a standby. Actual RPO must be based on the latest recoverable redo, not just the backup job timestamp.

### 19.1. Archive Backup Frequency Is Not Archive Generation Frequency

Oracle may archive redo frequently depending on log switch rates. A job backing up archived redo every 10 minutes does not guarantee every log is backed up exactly every 10 minutes if a job is delayed or fails.

Monitor:
- When logs are archived.
- When log backups complete.
- Sequence gaps.
- Logs remaining on disk.
- Logs shipped offsite.
- Standby apply lag if using Data Guard.

### 19.2. Near-Zero RPO Requires Measuring Lag

With Data Guard, monitor transport lag and apply lag, destination status, and protection mode. Synchronous transport can reduce data loss under certain conditions, but still depends on commit acknowledgment, network, standby availability, and configuration. Never infer RPO from the mode name without verifying operations.

## 20. Common Recovery Scenarios

| Incident | Initial Handling Approach |
|---|---|
| Loss of one datafile | Restore/recover datafile |
| Loss of control file | Restore control file, mount, and perform recovery |
| Loss of SPFILE | Restore SPFILE or use a controlled PFILE |
| Loss of entire database storage | Restore database from independent backup and recover |
| Accidental data deletion | Flashback/PITR/table recovery/Data Pump depending on scope |
| Bad data from deployment | Identify point before error; consider PITR or object recovery |
| Site loss | Data Guard failover or restore at DR site |
| Block corruption | RMAN block media recovery if conditions allow |
| Lost/corrupted backup piece | Select another backup; verify redo chain and retention |
| Loss of TDE keystore | Restore appropriate keystore/keys before reading encrypted data |

There is no single command for all incidents. Before running restore/recover, determine the damage scope, the state of the control file, datafiles, redo, incarnation, and the desired recovery point.

## 21. What Should a Recovery Runbook Include?

A good runbook must be written so an on-call engineer can follow it under pressure.

Minimum contents:
1. Diagram of database, storage, RAC/standby, and dependencies.
2. Owners, escalation path, and authorized approvers.
3. Locations of backups, control file autobackup, SPFILE, and recovery catalog.
4. How to obtain the DBID and identify the incarnation.
5. Procedure for accessing offsite backups.
6. Procedure for restoring the TDE keystore.
7. Tested RMAN commands for each scenario.
8. How to determine the target SCN/time/sequence.
9. How to resolve archive gaps.
10. Open/resetlogs procedure when applicable.
11. Database and application verification checks.
12. Traffic cutover and notification plan.
13. Recovery evidence and per-step timings.
14. Rollback or fallback procedure if recovery fails.

Do not store plaintext passwords, private keys, or wallet passwords in the runbook. Use a secret manager and controlled-access instructions.

## 22. RMAN Lab Exercise

The commands below illustrate the workflow. You need a lab database, appropriate SYSBACKUP/SYSDBA privileges, sufficient backup storage, and a valid RMAN configuration. Never run restore/recovery or delete backups in production just to practice.

### Step 1. Check Database Mode

```sql
SELECT name, open_mode, log_mode
FROM v$database;
```

### Step 2. Connect to RMAN

```text
rman target /
```

### Step 3. Configure Control File Autobackup

```sql
CONFIGURE CONTROLFILE AUTOBACKUP ON;
```

### Step 4. Create a Database and Archived Log Backup

```sql
BACKUP DATABASE PLUS ARCHIVELOG;
```

### Step 5. View Backups

```sql
LIST BACKUP SUMMARY;
LIST BACKUP OF DATABASE;
LIST BACKUP OF ARCHIVELOG ALL;
```

### Step 6. Check Repository and Obsolete Backups

```sql
CROSSCHECK BACKUP;
REPORT OBSOLETE;
```

Only run `DELETE OBSOLETE` after confirming retention and which backups must be kept.

### Step 7. Preview Restore

```sql
RESTORE DATABASE PREVIEW;
```

### Step 8. Validate Backups

```sql
RESTORE DATABASE VALIDATE;
```

### Step 9. Rehearse on an Auxiliary Host/Database

Perform restore/recovery following the runbook in an isolated environment. Measure timings and verify keys, archived logs, objects, and applications. Do not intentionally delete a datafile in a shared lab database.

### Step 10. Produce an RPO/RTO Report

Record:
- Timestamp of the last backup.
- Last recoverable redo.
- Achieved recovery point.
- Detection time.
- Restore time.
- Recovery time.
- Verification time.
- Time service became ready.
- Variance against targets.

## 23. Common Mistakes

| Misconception | Reality |
|---|---|
| Backup and restore are the same thing | Backup creates a copy; restore brings files from the copy back to the recovery location |
| After restore, the database is ready | Datafiles may still require media recovery |
| Recovery is just copying files | Recovery applies redo/incremental backups to bring data to a consistent point |
| Full backup and level 0 are identical in every context | Level 0 serves as the base for level 1 incremental backups; full backups do not act as an incremental base |
| Daily backups satisfy every RPO | RPO also depends on archived redo and a recoverable log chain |
| A successful backup job proves restore works | Validation and restore rehearsals are required |
| FRA is an offsite backup | FRA can be lost together with storage/site |
| Data Guard replaces RMAN | Standby does not fully protect against replicated logical corruption or user errors |
| TDE backups do not need keys | The corresponding keystore/master key is required to decrypt |
| RTO is just datafile restore time | It also includes detection, infrastructure, recovery, application startup, and validation |
| RPO equals backup frequency | You must account for the latest recoverable redo |
| `CROSSCHECK` reads the entire backup to verify it | It checks repository metadata against media existence/availability, not a substitute for restore testing |
| `REPORT OBSOLETE` means all old files can be deleted | Must follow retention policy and dependencies |
| `OPEN RESETLOGS` is a fix for a database that won't open | Only use per proper incomplete recovery/incarnation procedures |
| Data Pump replaces RMAN | Logical exports do not replace full physical database recovery |

## 24. Backup and DR Design Checklist

### Business Objectives
- RPO approved by the owner.
- RTO defined at the service level.
- Dependent systems identified.
- Maximum recovery time defined for each stage.

### Backup
- Database in ARCHIVELOG if online backup/PITR is required.
- Appropriate level 0/full and incremental schedule in place.
- Archived redo backed up/transported frequently enough.
- Control file and SPFILE protected.
- Recovery catalog backed up if used.
- TDE keystore and key history protected.
- Offsite/immutable backup copy maintained per policy.

### Verification
- RMAN CROSSCHECK and VALIDATE run on schedule.
- Periodic restore rehearsals conducted.
- Encrypted database recovery tested.
- Actual restore/recovery times measured.
- Archive gaps and backup retention checked.

### DR
- Runbook and owners assigned.
- DR infrastructure ready.
- Access to backups and keys verified.
- Data Guard/failover plan ready if used.
- Post-recovery application checks defined.
- Failover/restore decision thresholds defined.
- Drills conducted and runbook updated after each test.

## 25. Self-Check Questions

**Question 1.** What is a backup?

**Answer:** A copy of data and metadata created to enable recovery of a database or object when a failure occurs.

**Question 2.** How does restore differ from recovery?

**Answer:** Restore brings files from a backup back to the recovery location; recovery applies incremental backups and redo to bring files/databases to a consistent state at the target point.

**Question 3.** What is RPO?

**Answer:** The maximum data loss an organization accepts, typically expressed as the time interval from the recovery point to the time of the incident.

**Question 4.** What is RTO?

**Answer:** The maximum time allowed to restore a service to its defined operating level.

**Question 5.** Why is ARCHIVELOG important?

**Answer:** Archived redo allows rolling forward past a backup and recovering to points in time newer than the backup if the log chain is complete.

**Question 6.** How does a full backup differ from an incremental level 0 backup?

**Answer:** Level 0 is the baseline for level 1 incremental backups; a full backup does not serve as an incremental base under RMAN strategy.

**Question 7.** How do differential and cumulative level 1 differ?

**Answer:** Differential captures changes since the most recent level 0 or level 1; cumulative captures changes since the most recent level 0.

**Question 8.** Why must the control file and SPFILE be backed up?

**Answer:** The control file describes database structure and backup metadata; the SPFILE holds parameters required to start the instance.

**Question 9.** Why is archived redo backup needed?

**Answer:** To be able to recover past the database backup timestamp and meet the defined RPO.

**Question 10.** Does CROSSCHECK prove a restore will succeed?

**Answer:** No. It reconciles the repository and media; VALIDATE and restore rehearsals are required for deeper verification.

**Question 11.** Does Data Guard replace backups?

**Answer:** No. Logical errors can be replicated to the standby; independent backups and PITR are still needed.

**Question 12.** Why do TDE backups require the keystore?

**Answer:** Encrypted data requires the corresponding master key to decrypt after restore.

**Question 13.** Does RTO include application verification?

**Answer:** Yes, if the objective is defined at the service level. An open database does not guarantee the business service is working.

**Question 14.** Is RPO equal to database backup frequency?

**Answer:** No. You must consider the latest recoverable archived redo and any missing log segments.

**Question 15.** When is PITR used?

**Answer:** When you need to return the database to a point prior to the present, such as before an accidental deletion or logical error.

**Question 16.** Why must `RESETLOGS` be used to open after certain incomplete recoveries?

**Answer:** Because Oracle starts a new incarnation after the database is recovered to a point that no longer follows the current redo stream; subsequent backups/incarnations must be managed properly.

## 26. Conclusion

Backup, restore, and recovery are three parts of a single data protection workflow. Backup creates usable copies; restore brings files back from backups; recovery applies incremental backups and redo to bring the database to the desired consistent point. RMAN is the central tool for physical backup and media recovery, while Data Pump, Flashback, and Data Guard address different protection scopes.

RPO defines how much data loss the organization accepts; RTO defines how long it takes for the service to resume operation. RPO depends on backups, archived redo, log completeness, and standby/replication mechanisms. RTO depends on restore/recovery speed, DR infrastructure, keys, applications, and runbook execution. Neither objective can be assumed solely from a backup schedule or a single successful RMAN command.

A sound design protects datafiles, control files, SPFILE, archived redo, the recovery catalog if present, the TDE keystore, and external dependencies, while maintaining at least one backup independent of the database's failure domain. Verify with CROSSCHECK/VALIDATE and, most importantly, rehearse real restore/recovery, measure each step's duration, and validate data and applications. Only when testing proves RPO/RTO compliance does a backup and disaster recovery plan have operational evidence.
