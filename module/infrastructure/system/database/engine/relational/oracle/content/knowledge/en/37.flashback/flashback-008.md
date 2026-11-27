# Restore Points, Guaranteed Restore Points, and Space Pressure

Oracle Database supports **restore points** to mark a meaningful SCN milestone in the database's lifecycle. DBAs commonly create a restore point before an upgrade, major deployment, migration, or risky operation. If you need to return to the pre-change state, the restore point can serve as the target for Flashback Database or certain RMAN point-in-time recovery procedures.

Two types of restore points must be distinguished:

- **Normal restore point:** Stores the name and SCN of the marked milestone. It makes referencing that milestone convenient, yet does not guarantee that the required flashback logs will be retained.
- **Guaranteed restore point (GRP):** Instructs Oracle to retain the flashback logs required to flashback the database to that milestone until the restore point is dropped. This guarantee creates storage pressure inside the Fast Recovery Area (FRA).

A GRP is very helpful prior to a change that may require rollback, yet if kept too long, flashback logs cannot be deleted while still needed for the restore point. The FRA can fill up, disrupting archive logs, backups, and database availability. Therefore, creating a GRP must always be accompanied by a clear capacity monitoring plan and drop schedule.

## 1. What is a restore point?

A restore point is a named label bound to an SCN (System Change Number) in the database. The SCN establishes the order of database changes. When a restore point is created, Oracle records its name, SCN, and related metadata in the control file.

Example:

~~~sql
CREATE RESTORE POINT before_release;
~~~

The statement above creates a normal restore point named BEFORE_RELEASE. You can inspect this milestone with:

~~~sql
SELECT name,
       scn,
       time,
       guarantee_flashback_database
  FROM v$restore_point
 ORDER BY time DESC;
~~~

A restore point is not an independent backup. It does not copy datafiles, control files, or redo logs. It simply marks a milestone that recovery procedures can reference.

A restore point can be used to:

- Capture the SCN prior to a release or migration.
- Specify the target for Flashback Database if sufficient flashback logs and prerequisites exist.
- Serve as a target anchor in an RMAN point-in-time recovery workflow.
- Help DBAs record the database state before a critical change.

A restore point name is easier to remember than a long SCN number. Still, record the name, SCN, timestamp, and database incarnation in the runbook to avoid confusion across environments or deployments.

## 2. Normal restore points

A normal restore point stores the SCN milestone metadata in the control file. It does not force Oracle to retain all flashback logs needed to return to that point.

Create a restore point:

~~~sql
CREATE RESTORE POINT before_patch;
~~~

Check:

~~~sql
SELECT name,
       scn,
       time,
       guarantee_flashback_database,
       preserved
  FROM v$restore_point
 WHERE name = 'BEFORE_PATCH';
~~~

GUARANTEE_FLASHBACK_DATABASE indicates whether the restore point is a GRP. PRESERVED provides restore point retention metadata in releases that include this column; verify against the data dictionary of your running release if the view structure differs.

A normal restore point is useful when:

- You only need to record an SCN milestone for reference or RMAN PITR.
- You do not require a guarantee that flashback logs remain available.
- You maintain backups and archived redo under a separate recovery strategy.
- You want to avoid the long-term storage lock created by a GRP.

If after some time the required flashback logs have been reused or deleted by Oracle, the normal restore point may still retain its metadata yet no longer guarantee Flashback Database to that milestone. The DBA must verify actual feasibility before relying on it.

### Dropping a normal restore point

When the milestone is no longer needed:

~~~sql
DROP RESTORE POINT before_patch;
~~~

Dropping a restore point deletes the milestone metadata. It does not delete datafiles or backups. Before dropping, confirm no runbook, release rollback, or RMAN operation still references that milestone.

## 3. Guaranteed restore points (GRP)

A guaranteed restore point also marks an SCN, but adds a guarantee to retain the flashback logs required to flashback the database to that milestone. Oracle will not automatically purge flashback logs still needed for a GRP merely because they are older than DB_FLASHBACK_RETENTION_TARGET.

Create a GRP:

~~~sql
CREATE RESTORE POINT before_upgrade
  GUARANTEE FLASHBACK DATABASE;
~~~

Check:

~~~sql
SELECT name,
       scn,
       time,
       guarantee_flashback_database,
       storage_size
  FROM v$restore_point
 WHERE name = 'BEFORE_UPGRADE';
~~~

If GUARANTEE_FLASHBACK_DATABASE is YES, the restore point is guaranteed. STORAGE_SIZE indicates the amount of flashback log storage attributed to the restore point as calculated by Oracle in that release. This value can grow over time as the database changes.

### Does a GRP require Flashback Database to be enabled beforehand?

An important Oracle characteristic is that you can create a guaranteed restore point even when Flashback Database is not yet turned on, provided prerequisites such as Fast Recovery Area configuration are met. When the GRP is created, Oracle begins maintaining the flashback logs required to guarantee rewinding to that milestone.

This does not mean every recovery prerequisite is automatically satisfied. The DBA must still verify ARCHIVELOG mode, FRA, storage, control files, privileges, release behavior, and the overall recovery plan.

### GRPs do not expire automatically

A guaranteed restore point is kept until explicitly dropped. Do not expect a normal retention policy to automatically delete a GRP to free space.

Once a GRP is no longer needed, drop it:

~~~sql
DROP RESTORE POINT before_upgrade;
~~~

After dropping, flashback logs no longer needed for that GRP can become reclaimable under FRA management rules. Space usage does not necessarily drop immediately back to baseline; Oracle manages file reuse and deletion as needed.

## 4. Comparing normal restore points and guaranteed restore points

| Criterion | Normal restore point | Guaranteed restore point |
|---|---|---|
| Stores name and SCN | Yes | Yes |
| Guarantees flashback log retention | No | Yes, until dropped |
| Automatically expires with flashback retention | Do not rely on retention as a guarantee; metadata and logs are separate concerns | No; must be dropped explicitly |
| FRA capacity impact | Does not force long-term log retention | Can retain large amounts of flashback logs and grow the FRA |
| Best suited for | Marking an SCN, RMAN PITR, reference milestone | A rollback window that must be guaranteed via Flashback Database |
| Primary operational risk | Required flashback logs may be missing when needed | Keeping it too long can fill the FRA |

Core takeaway: a normal restore point keeps the milestone; a GRP keeps the milestone and forces Oracle to preserve the flashback logs needed to rewind to it.

## 5. Flashback Database and its relationship with restore points

Flashback Database is the mechanism that brings the database back to an earlier timestamp or SCN using flashback logs and redo following Oracle procedures. It is typically faster than restoring all datafiles from backups and applying redo, though it does not replace backups.

Key prerequisites for using Flashback Database:

- The database must be in ARCHIVELOG mode.
- The Fast Recovery Area must be configured.
- Flashback Database must be enabled, or a GRP must exist to guarantee flashback logs under the corresponding mechanism.
- Required flashback logs must still be available.
- The database must be placed in the appropriate state to run Flashback Database, typically MOUNT.
- Appropriate DBA privileges and procedures must be in place.

Check ARCHIVELOG mode:

~~~sql
SELECT log_mode
  FROM v$database;
~~~

Check related parameters:

~~~sql
SHOW PARAMETER db_recovery_file_dest;
SHOW PARAMETER db_recovery_file_dest_size;
SHOW PARAMETER db_flashback_retention_target;
SHOW PARAMETER db_flashback;
~~~

DB_FLASHBACK_RETENTION_TARGET is the retention target in minutes. It is a target Oracle attempts to satisfy when managing flashback logs, not a guarantee to retain logs in every circumstance. A GRP establishes the guarantee to retain logs needed for a specific milestone until dropped.

### Enabling Flashback Database

Enabling Flashback Database typically requires the database in MOUNT and ARCHIVELOG mode:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
ALTER DATABASE FLASHBACK ON;
ALTER DATABASE OPEN;
~~~

This operation changes database state and requires a maintenance window and operational plan. Do not run it verbatim in production without verifying Data Guard, RAC, PDBs, backups, and release requirements.

Check status:

~~~sql
SELECT flashback_on,
       log_mode,
       open_mode
  FROM v$database;
~~~

FLASHBACK_ON shows whether Flashback Database is enabled in configuration. If using a GRP while Flashback Database is not globally enabled, clearly distinguish GRP log retention from global Flashback Database enablement.

## 6. What is the FRA?

The Fast Recovery Area (FRA) is an Oracle-managed storage area for backup and recovery files. Depending on configuration, the FRA can reside on a filesystem or an ASM disk group.

Common file types in the FRA:

- Flashback logs.
- Archived redo logs.
- RMAN backup pieces.
- Image copies.
- Control file autobackups.
- Other recovery files depending on configuration.

The FRA has a logical capacity limit configured via DB_RECOVERY_FILE_DEST_SIZE. Oracle manages reuse and deletion of eligible files according to retention policies, archived log deletion policies, and recovery dependencies.

Check configuration:

~~~sql
SHOW PARAMETER db_recovery_file_dest;
SHOW PARAMETER db_recovery_file_dest_size;
~~~

Example:

~~~sql
ALTER SYSTEM SET db_recovery_file_dest = '+FRA'
  SCOPE=BOTH;

ALTER SYSTEM SET db_recovery_file_dest_size = 500G
  SCOPE=BOTH;
~~~

The values above are illustrative. Before changing them, verify that the ASM disk group or filesystem has sufficient physical capacity, a capacity plan exists, and the change is approved. Raising the logical quota without sufficient underlying storage merely pushes the failure down to the storage layer.

### FRA quota is not physical capacity

DB_RECOVERY_FILE_DEST_SIZE is the FRA capacity limit Oracle is allowed to use by configuration. It does not automatically expand the filesystem or ASM disk group.

For example, the FRA is configured to 500 GB while the disk group only has 100 GB free. Increasing the quota to 800 GB creates zero physical disk space. Monitor all of the following:

- The FRA limit in Oracle.
- Physical free space on the filesystem/ASM.
- Used space and reclaimable space.
- Growth rates of flashback logs, archived redo, and backups.
- Impact of active GRPs.

## 7. Why do GRPs create space pressure?

Flashback logs store the information required to revert blocks to prior states. When a GRP exists, Oracle must keep the flashback logs required to rewind to the GRP's SCN. Those logs cannot be reclaimed simply because they exceed the normal retention target.

Suppose:

1. The DBA creates a GRP before an upgrade on Monday.
2. The database continues running with heavy DML over the following days.
3. Modified blocks generate flashback logs.
4. The GRP still requires rewinding back to Monday.
5. Oracle must retain the necessary flashback logs starting from that milestone.
6. The FRA continues accumulating new flashback logs, archived redo, and backups.
7. Available free space shrinks if log generation exceeds reclamation capacity.

The longer a GRP exists and the higher the write workload, the larger the retained flashback log volume can become. Time alone does not determine size; block change rate, block size, batch workloads, bulk loads, and write activity all contribute.

### Multiple coexisting GRPs

If multiple guaranteed restore points exist, the oldest GRP can force Oracle to retain flashback logs over an even longer span. Creating additional GRPs does not release older logs; it can compound preservation requirements across milestones.

Do not create GRPs for every release and leave them sitting indefinitely. Every GRP must have an owner, purpose, creation time, rollback window, and designated drop responsibility.

## 8. Monitoring FRA capacity

### V$RECOVERY_FILE_DEST

This view shows the FRA limit and utilization:

~~~sql
SELECT name,
       space_limit,
       space_used,
       space_reclaimable,
       number_of_files
  FROM v$recovery_file_dest;
~~~

Key columns:

- NAME: FRA location.
- SPACE_LIMIT: Configured size limit.
- SPACE_USED: Space recorded by Oracle as used.
- SPACE_RECLAIMABLE: Space eligible to be reclaimed under FRA rules at query time.
- NUMBER_OF_FILES: Number of files in the FRA.

Calculate usage percentage:

~~~sql
SELECT name,
       ROUND(space_used / NULLIF(space_limit, 0) * 100, 2)
         AS used_pct,
       ROUND(space_reclaimable / NULLIF(space_limit, 0) * 100, 2)
         AS reclaimable_pct,
       ROUND((space_limit - space_used) / 1024 / 1024 / 1024, 2)
         AS free_gb
  FROM v$recovery_file_dest;
~~~

SPACE_RECLAIMABLE does not mean all of that space is guaranteed to be freed instantaneously. Dependencies and file states can affect reclaimability. Correlate with the alert log and usage by file type.

### V$FLASH_RECOVERY_AREA_USAGE

This view breaks down usage by file type:

~~~sql
SELECT file_type,
       percent_space_used,
       percent_space_reclaimable,
       number_of_files
  FROM v$flash_recovery_area_usage
 ORDER BY percent_space_used DESC;
~~~

File types can include:

- CONTROLFILE.
- ONLINELOG.
- ARCHIVELOG.
- BACKUPPIECE.
- IMAGECOPY.
- FLASHBACKLOG.
- Other file types depending on release.

If FLASHBACKLOG accounts for a high percentage and an old GRP exists, inspect active restore points and milestone ages before deciding on cleanup.

### Inspecting existing GRPs

~~~sql
SELECT name,
       scn,
       time,
       guarantee_flashback_database,
       storage_size
  FROM v$restore_point
 WHERE guarantee_flashback_database = 'YES'
 ORDER BY time;
~~~

This is an essential query for identifying stale or unowned GRPs. If multiple GRPs exist, note the oldest milestone, its purpose, and the responsible owner before dropping.

## 9. Monitoring flashback logs and estimated needs

V$FLASHBACK_DATABASE_LOG provides information on flashback logs:

~~~sql
SELECT oldest_flashback_scn,
       oldest_flashback_time,
       retention_target,
       flashback_size,
       estimated_flashback_size
  FROM v$flashback_database_log;
~~~

Fields help explain:

- OLDEST_FLASHBACK_SCN/TIME: The oldest milestone currently available in flashback logs according to the view.
- RETENTION_TARGET: Retention target in minutes.
- FLASHBACK_SIZE: Currently recorded flashback log size.
- ESTIMATED_FLASHBACK_SIZE: Estimated size needed for the retention target based on current workload and metrics.

The estimate is a projection, not an exact future capacity guarantee. Workloads can shift sharply after deployments or batch runs.

V$FLASHBACK_DATABASE_STAT can be used to observe flashback data and redo volume across intervals:

~~~sql
SELECT begin_time,
       end_time,
       flashback_data,
       db_data,
       redo_data,
       estimated_flashback_size
  FROM v$flashback_database_stat
 ORDER BY begin_time DESC;
~~~

This view helps DBAs estimate the flashback data generation rate under load. Columns and metrics can vary by release; verify against the dictionary of your running version.

### Estimating GRP retention duration

Suppose flashback logs grow by an average of 12 GB per hour in a test workload. If 120 GB of FRA space remains available for flashback logs, the theoretical window is 10 hours. This is only a rough estimate:

\[
\text{Estimated duration} \approx
\frac{\text{Available space}}{\text{Flashback log generation rate}}
\]

Do not use this calculation as a sole operational threshold. Budget headroom for archived redo, backups, workload spikes, other FRA files, and physical storage limits. Use historical peak-hour data for more conservative estimates.

## 10. Alerts when the FRA approaches full

Oracle can log warnings when the FRA crosses utilization thresholds. In the alert log, you may see messages regarding FRA usage, such as high-utilization warnings or notices that files cannot be reclaimed.

Common errors:

| Error code | General meaning |
|---|---|
| ORA-19809 | Limit exceeded for recovery files |
| ORA-19804 | Cannot reclaim the required amount of space within the FRA limit |
| ORA-19815 | Warning that FRA is approaching or exceeding a reported usage threshold |
| ORA-00257 | Archiver error; typically requires inspecting FRA/archive destinations and freeing valid space |
| ORA-38786 | May relate to Flashback Database enablement/operation conditions; inspect full error stack |

Error codes are only initial indicators. Read the full alert log and RMAN output to identify the file type, destination, space requirement, and failing operation.

### Why can a full FRA impact the database?

If the FRA cannot reclaim required files, Oracle may be unable to write additional archived redo to the FRA or create new flashback logs. Specific impact depends on file types, destinations, archive configuration, and workload:

- Archiving can fail if the archive destination is full.
- The database can be severely impacted when log switches cannot complete because archived redo cannot be saved.
- Flashback logging may be unable to continue as required.
- Backup jobs can fail because no space remains for backup pieces.
- Recovery or maintenance operations may become impossible.

Never wait until the FRA hits 100% before acting. Configure early alerts and keep a safe space-reclamation runbook ready.

## 11. Why should you never delete FRA files via the OS?

The FRA is managed by Oracle, and files within it have dependencies with the control file, recovery catalog, backups, archived redo, and restore points. Deleting files directly with rm, del, or filesystem tools can leave the repository believing the files still exist, breaking recoverability or causing errors in later RMAN operations.

Do not do:

~~~text
rm /fra/ORCL/archivelog/...
del D:\FRA\ORCL\...
~~~

Instead:

- Use RMAN CROSSCHECK to reconcile the repository with physical files on disk.
- Use DELETE EXPIRED once you confirm files no longer exist.
- Use DELETE OBSOLETE according to an approved retention policy.
- Use BACKUP ARCHIVELOG and DELETE INPUT according to appropriate backup/deletion policies.
- Drop unneeded guaranteed restore points so Oracle can reclaim unprotected flashback logs.

Never run DELETE OBSOLETE or DELETE ARCHIVELOG ALL solely to free FRA space without verifying backups, archived log deletion policies, Data Guard, and PITR requirements.

## 12. Managing the GRP lifecycle

A GRP should follow a well-defined lifecycle:

1. Identify the risky change and rollback need.
2. Confirm the database meets prerequisites to create a GRP.
3. Check FRA capacity and log generation rate.
4. Create the GRP immediately before the change window.
5. Record the name, SCN, timestamp, owner, and internal expiration time.
6. Execute the release/migration.
7. Validate the application and data.
8. Keep the GRP for the approved observation window.
9. Once the rollback window closes and the milestone is no longer needed, drop the GRP.
10. Monitor the FRA after dropping and archive evidence.

Example creating a restore point named after the release:

~~~sql
CREATE RESTORE POINT before_release_2026_11_14
  GUARANTEE FLASHBACK DATABASE;
~~~

Record details:

~~~sql
SELECT name,
       scn,
       time,
       guarantee_flashback_database,
       storage_size
  FROM v$restore_point
 WHERE name = 'BEFORE_RELEASE_2026_11_14';
~~~

Once the release is stable and the rollback window ends:

~~~sql
DROP RESTORE POINT before_release_2026_11_14;
~~~

Restore point names must comply with Oracle naming rules and internal conventions. Never reuse names arbitrarily, as that causes confusion in runbooks and audits.

### Who is responsible for dropping?

Every GRP needs clear ownership:

- The DBA creates the restore point.
- The release owner confirms the change is stable.
- The DBA verifies no rollback request remains.
- An authorized operator runs DROP RESTORE POINT.
- Monitoring confirms the FRA begins reclaiming space as needed.

Never leave dropping a GRP to personal memory. Create a ticket or scheduled reminder with an internal expiration date.

## 13. Flashback Database to a restore point

When returning to a marked milestone is necessary, the DBA can use Flashback Database. Typical procedure:

1. Stop applications and data-writing connections.
2. Confirm the exact database, restore point, and SCN.
3. Place the database in MOUNT state as required.
4. Execute FLASHBACK DATABASE TO RESTORE POINT.
5. Open the database with RESETLOGS per procedure.
6. Verify the database, PDBs, services, and data.
7. Take a new backup after creating the new incarnation per policy.

Example operational skeleton:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;

FLASHBACK DATABASE TO RESTORE POINT
  before_release_2026_11_14;

ALTER DATABASE OPEN RESETLOGS;
~~~

This is a major state- and data-altering operation. Never run example commands verbatim in production. Before executing, confirm:

- The exact restore point and database incarnation.
- That required flashback logs remain available.
- That the database is in ARCHIVELOG mode and meets Flashback Database prerequisites.
- That all applications are stopped or isolated.
- That rollback approval and a post-recovery verification plan exist.
- That suitable backups exist to handle failures if flashback fails.

### OPEN RESETLOGS and database incarnation

After Flashback Database to an earlier point, the database typically must be opened with RESETLOGS. This creates a new database incarnation. Backups and archived redo from the prior incarnation must be managed properly by RMAN.

After opening with RESETLOGS:

- Verify the database and PDBs.
- Verify services.
- Run smoke tests and data reconciliation.
- Record the new incarnation.
- Take backups according to policy.
- Verify the RMAN repository and subsequent backup strategy.

Do not assume older backups automatically become unusable; RMAN tracks incarnations and can use backups according to recovery rules. The DBA must understand the current incarnation and recovery objectives.

## 14. Guaranteed restore points do not replace backups

A GRP can guarantee Flashback Database back to a milestone while flashback logs remain protected, yet it does not protect against every kind of disaster:

- Loss of the entire storage holding datafiles and the FRA.
- Loss of control files or required metadata without suitable copies.
- Failure of a device hosting both the database and flashback logs.
- Loss of the encryption wallet/keystore.
- Infrastructure failures rendering both database and FRA inaccessible.
- Business or application errors requiring partial data recovery rather than rewinding the entire database.

A GRP is not an independent off-site copy. If both the database and FRA reside on the same storage domain and that storage fails, the GRP can be lost as well.

You still need:

- Scheduled RMAN backups.
- Control file and SPFILE backups.
- Archived redo backups.
- Backup copies on an independent storage/domain/site.
- Restore validate checks.
- Restore drills.
- Protection for TDE wallets/keystores.
- Data Guard or DR runbooks if applicable.

Treat a GRP as a fast rollback tool for a change window, while backups/DR remain the foundation protecting against physical loss and disasters.

## 15. Restore points and RMAN point-in-time recovery

RMAN can use a restore point as a named reference for a recovery target. Example:

~~~text
RMAN> RUN {
  SET UNTIL RESTORE POINT before_release_2026_11_14;
  RESTORE DATABASE;
  RECOVER DATABASE;
}
~~~

This is an illustrative skeleton for an RMAN PITR workflow. RMAN needs suitable backups and archived redo to recover to the restore point's SCN. A normal restore point can serve as an RMAN reference even without a GRP's flashback log guarantee, though complete backups/redo are still required.

Difference:

- Flashback Database uses flashback logs and redo via the Flashback mechanism to rewind to the milestone.
- RMAN PITR restores datafiles from backups and applies redo to the target point.
- A GRP guarantees retention of flashback logs needed for Flashback Database; it does not create extra datafile backups.

Choose the method based on incident type, RTO/RPO, capacity, blast radius, and backup/redo availability.

## 16. Restore points in CDB and PDB

In Oracle Multitenant, restore points can be created at CDB or PDB scope depending on release and restore point type. Clearly determine:

- Whether you are connected to the CDB root or a PDB.
- Whether the restore point is CDB-wide or PDB-specific.
- Whether your Oracle release supports PDB restore points and guaranteed PDB restore points in the way needed.
- Whether the PDB is in an appropriate state.
- What scope the Flashback/restore command affects.

Do not assume a restore point created in the root guarantees every PDB can be recovered independently in the same way. Consult the Multitenant/Flashback documentation for your specific release before designing runbooks.

When creating or using restore points in a CDB environment, record CON_ID/PDB, SCN, timestamp, and scope. If only one PDB needs rollback, evaluate Flashback PDB or PDB PITR supported in your release instead of needlessly flashbacking the entire CDB.

## 17. Assessing space before creating a GRP

Before creating a guaranteed restore point, gather:

~~~sql
SELECT name,
       space_limit,
       space_used,
       space_reclaimable,
       number_of_files
  FROM v$recovery_file_dest;

SELECT file_type,
       percent_space_used,
       percent_space_reclaimable,
       number_of_files
  FROM v$flash_recovery_area_usage
 ORDER BY percent_space_used DESC;

SELECT oldest_flashback_time,
       retention_target,
       flashback_size,
       estimated_flashback_size
  FROM v$flashback_database_log;
~~~

Check existing GRPs:

~~~sql
SELECT name,
       time,
       scn,
       storage_size
  FROM v$restore_point
 WHERE guarantee_flashback_database = 'YES'
 ORDER BY time;
~~~

Evaluate:

- How much available capacity remains in the FRA?
- Which file types consume most of the space?
- Do any old GRPs still exist?
- Does the upcoming workload include bulk loads or major batches?
- How long must the GRP be retained?
- Is there sufficient physical disk capacity beneath the FRA?
- Are archived redo and backups growing abnormally?
- Are there any capacity alerts or failing backup jobs?

If space is insufficient, resolve capacity before creating the GRP. Never create a GRP and only afterward scramble to free space while production is nearly full.

## 18. Designing FRA pressure alerts

A monitoring system should alert across multiple thresholds rather than only when the FRA is full:

| Level | Example threshold | Action |
|---|---|---|
| Info | FRA usage exceeds 70% | Review trend and growth rate |
| Warning | Exceeds 80% or abnormal rapid growth | Inspect GRPs, flashback logs, archives, and backups |
| Critical | Exceeds 90% or zero reclaimable space remains | DBA acts immediately per runbook; assess archive impact |
| Emergency | ORA-19809/ORA-19804 or archive destination full | Trigger incident and resolve capacity/dependencies |

Thresholds are examples only. Tune them based on data growth rate, capacity, SLAs, and operations team response time.

Monitoring should track over time:

- SPACE_USED.
- SPACE_RECLAIMABLE.
- SPACE_LIMIT.
- Percentage by file type.
- Count and age of GRPs.
- STORAGE_SIZE of each GRP.
- Flashback log generation rate.
- Archived redo generation rate.
- Backup growth and job failures.

An FRA with 20% free space can still be dangerous if growth rate is high and a GRP is scheduled to stay for another 24 hours. Trend matters just as much as current percentage.

## 19. Handling a nearly full or full FRA

When the FRA grows rapidly, never delete files via the OS and never drop a GRP automatically. Follow an orderly sequence:

### Step 1: identify the cause

~~~sql
SELECT name,
       space_limit,
       space_used,
       space_reclaimable
  FROM v$recovery_file_dest;

SELECT file_type,
       percent_space_used,
       percent_space_reclaimable
  FROM v$flash_recovery_area_usage
 ORDER BY percent_space_used DESC;

SELECT name,
       time,
       storage_size
  FROM v$restore_point
 WHERE guarantee_flashback_database = 'YES'
 ORDER BY time;
~~~

### Step 2: check GRPs and rollback windows

Contact release owners to confirm which GRPs are still required. If a change is still inside its rollback window, do not drop the GRP just to reclaim space unless a business decision and alternative recovery plan are approved.

### Step 3: check files eligible for valid reclamation

Use RMAN to crosscheck and evaluate backups/archived logs:

~~~text
RMAN> CROSSCHECK BACKUP;
RMAN> CROSSCHECK ARCHIVELOG ALL;
RMAN> REPORT OBSOLETE;
~~~

These commands do not delete backups by themselves. REPORT OBSOLETE shows which backups are no longer needed under the current retention policy. Confirm policies, Data Guard, and PITR needs before deleting.

### Step 4: free space according to policy

Once obsolete backups are confirmed:

~~~text
RMAN> DELETE OBSOLETE;
~~~

If a GRP is no longer needed and approved for removal:

~~~sql
DROP RESTORE POINT before_upgrade;
~~~

If archived redo has been backed up completely and the deletion policy permits, use the appropriate RMAN workflow to delete eligible logs. Never delete archive logs still needed by a standby or for PITR.

### Step 5: increase capacity if needed

If physical storage has sufficient room, the DBA can increase DB_RECOVERY_FILE_DEST_SIZE per procedure:

~~~sql
ALTER SYSTEM SET db_recovery_file_dest_size = 700G
  SCOPE=BOTH;
~~~

The figure is illustrative only. Confirm physical space remains on the filesystem/ASM before increasing the quota.

### Step 6: verify normal operation

- Confirm the alert log shows no remaining FRA errors.
- Confirm archive logging can proceed.
- Check backup jobs.
- Check flashback logging.
- Verify applications and sessions.
- Record before/after capacity and actions taken.

## 20. Does dropping a GRP immediately free space?

Dropping a GRP removes the preservation requirement on flashback logs for that milestone. Flashback logs held solely for that GRP can become reclaimable files. However, Oracle may not delete all of them immediately; reclamation depends on space demand, dependencies from other restore points, and FRA management rules.

If an older GRP still exists, flashback logs required for that older GRP may continue to be retained. Therefore, after dropping a GRP, re-check the GRP list and FRA usage:

~~~sql
SELECT name,
       time,
       storage_size
  FROM v$restore_point
 WHERE guarantee_flashback_database = 'YES'
 ORDER BY time;

SELECT file_type,
       percent_space_used,
       percent_space_reclaimable
  FROM v$flash_recovery_area_usage;
~~~

Do not expect SPACE_USED to drop straight to 0 immediately. The goal is that files no longer needed for recovery become eligible for Oracle to reclaim per policy.

## 21. Common misconceptions

**A restore point is a backup:** False. A restore point primarily records an SCN milestone and metadata; it does not create copies of datafiles.

**A normal restore point guarantees flashback works:** False. A normal restore point does not guarantee flashback logs are preserved.

**A GRP expires automatically according to DB_FLASHBACK_RETENTION_TARGET:** False. A GRP must be dropped explicitly.

**Creating a GRP does not require an FRA:** False. A GRP requires a suitable environment for storing flashback logs, including a configured FRA.

**Flashback Database must always be enabled before creating a GRP:** Not necessarily. Oracle permits creating a GRP while Flashback Database is not yet enabled if prerequisites are met; the GRP triggers retention of flashback logs for that milestone.

**A GRP replaces RMAN backups:** False. A GRP does not protect against loss of storage, site, or backup components.

**If the FRA is full, delete old files using the OS:** Very dangerous. Use RMAN and Oracle's management mechanisms.

**Increasing DB_RECOVERY_FILE_DEST_SIZE automatically creates more disk:** False. It is a logical quota, not physical capacity.

**Dropping one GRP always frees all flashback logs immediately:** False. Other GRPs or dependencies may keep holding logs.

**FLASHBACK RETENTION TARGET is a retention guarantee:** False. It is a best-effort target; only a GRP provides guaranteed log retention for a specific milestone.

## 22. Example workflow before and after a release

Suppose an application plans a weekend schema upgrade and needs rapid rollback capability for 6 hours post-deployment.

### Before release

1. Verify the latest RMAN backup and archived redo.
2. Check restore validate per plan.
3. Inspect FRA usage and any existing GRPs.
4. Estimate flashback log generation over 6 peak hours.
5. Confirm the FRA has sufficient headroom and physical storage.
6. Create a GRP named after the release.

~~~sql
CREATE RESTORE POINT before_app_release_2026_11_14
  GUARANTEE FLASHBACK DATABASE;
~~~

7. Record the SCN/time and notify the release owner.

### During release

- Monitor the FRA, flashback logs, archive logs, and alert log.
- Do not create extra GRPs without justification.
- Monitor application health, error rates, and data.
- If a critical error occurs, evaluate rollback via Flashback Database per runbook.

### After release

- Run smoke tests.
- Reconcile key row counts and totals.
- Monitor workload throughout the observation period.
- Once the release owner confirms the rollback window is closed, drop the GRP.

~~~sql
DROP RESTORE POINT before_app_release_2026_11_14;
~~~

- Check FRA usage and backup jobs.
- Archive release outcomes, SCN, drop time, and evidence.

If a release requires rollback after the GRP has already been dropped, use the appropriate backup/RMAN/Data Guard procedure. Never assume you can rewind to a milestone simply because a restore point name once existed.

## 23. Dedicated restore drill for GRPs

Before using GRPs in production, rehearse the workflow in a test environment:

1. Prepare a test database with proper FRA and ARCHIVELOG configuration.
2. Create a representative dataset.
3. Create a GRP.
4. Execute DML and schema changes per scenario.
5. Monitor flashback logs and FRA usage.
6. Stop the application and execute Flashback Database to the GRP.
7. Open the database with RESETLOGS per procedure.
8. Verify pre-milestone data and confirm post-milestone changes were reverted.
9. Verify PDBs/services and the application.
10. Take a new backup per policy and drop the GRP once testing finishes.

During the drill, record:

- Time to create the GRP.
- SCN of the GRP.
- FRA space before/after.
- Flashback log generation rate.
- Flashback duration.
- Database and PDB open time.
- Achieved RTO/RPO.
- Smoke test and data reconciliation results.

Never rehearse by flashbacking a production database without approval and a planned service outage. A GRP is not a zero-disruption rollback mechanism.

## 24. GRP and FRA operations checklist

- [ ] Confirm ARCHIVELOG mode.
- [ ] Confirm FRA is configured with sufficient physical space.
- [ ] Check DB_RECOVERY_FILE_DEST_SIZE.
- [ ] Check DB_FLASHBACK_RETENTION_TARGET and FLASHBACK_ON status.
- [ ] Inspect the current list of restore points.
- [ ] Identify the owner and rollback window for every GRP.
- [ ] Check V$RECOVERY_FILE_DEST.
- [ ] Check V$FLASH_RECOVERY_AREA_USAGE.
- [ ] Check V$FLASHBACK_DATABASE_LOG and log generation rate.
- [ ] Estimate space needed for the entire GRP window.
- [ ] Confirm independent RMAN backups and archived redo.
- [ ] Record the restore point's SCN/time.
- [ ] Create the GRP right before the change requiring protection.
- [ ] Monitor the FRA throughout the rollback window.
- [ ] Drop the GRP once confirmed by the release owner.
- [ ] Verify space reclamation and archive/backup status after dropping.
- [ ] Save evidence and drill results.

## 25. Conclusion

Restore points mark an SCN so recovery procedures can reference it. A normal restore point records the milestone without guaranteeing flashback log retention. A guaranteed restore point forces Oracle to retain the necessary flashback logs until dropped, making it highly valuable before risky releases or migrations.

In return, a GRP can cause flashback logs to grow continuously and fill the FRA. If the FRA cannot reclaim files, archive logs, backups, and database operations can be affected. Monitor V$RESTORE_POINT, V$RECOVERY_FILE_DEST, V$FLASH_RECOVERY_AREA_USAGE, and V$FLASHBACK_DATABASE_LOG; forecast capacity based on workload and GRP retention duration; and assign clear ownership and drop deadlines.

GRPs do not replace RMAN backups or DR. Before relying on them in production, rehearse Flashback Database in an isolated environment, verify PDBs/services, measure RTO/RPO, and confirm independent backup/recovery procedures continue to meet requirements. Once the rollback window closes, drop the GRP upon approval and confirm the FRA returns to a healthy state.
