# Retention Policy, Redundancy, Recovery Window, and Deletion Policy

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Backup and Recovery  
> **Goal:** Understand how RMAN decides which backups are still needed for recoverability; distinguish retention policy from archived log deletion policy; choose REDUNDANCY or RECOVERY WINDOW based on RPO/RTO; understand OBSOLETE and EXPIRED; manage archived redo logs in standalone and Data Guard environments; inspect configuration, forecast capacity, and build a safe deletion procedure.

## 1. Two distinct policies in the backup lifecycle

RMAN has multiple rules to determine which backup data must be retained and when files may be deleted. Two policies are frequently confused:

- **Backup retention policy:** specifies which backups are still needed to meet recovery objectives. Backups no longer required under this policy are marked OBSOLETE.
- **Archived log deletion policy:** specifies conditions archived redo logs must satisfy before RMAN permits deleting them from managed storage locations.

The two policies are related, but do not replace each other.

Example:

- The retention policy requires maintaining recoverability to any point within the last 7 days.
- The deletion policy requires archived redo logs to be backed up at least once to DISK before deletion.
- If the database uses Data Guard, the deletion policy may also require logs to be shipped or applied to standbys.

An archived log may no longer be needed for a specific backup yet still not be eligible for deletion under the deletion policy. Conversely, a log that has been backed up the required number of times may still be needed to recover to a point inside the recovery window.

**Never run a DELETE command based solely on file age or space usage.** Before deleting, determine which backups are still needed, which logs are still needed for recovery, how far standbys have received/applied logs, and whether existing backups are readable.

## 2. Foundational concepts

### 2.1. Backup retention

Retention is the time span or number of backups the system must maintain to satisfy recovery requirements.

RMAN supports two main configuration modes:

- REDUNDANCY: retain a minimum number of backups.
- RECOVERY WINDOW: maintain recoverability to any point within a recent number of days.

These represent objectives differently. Choose a policy that aligns with operational requirements, not just because the syntax is easy to remember.

### 2.2. Archived redo logs

Archived redo logs contain redo changes archived from online redo logs. These logs are required for media recovery and point-in-time recovery past a backup's timestamp.

An older datafile backup may need a continuous chain of archived redo logs to recover to the desired time. Having a full backup while missing required logs can still prevent reaching the requested recovery point.

### 2.3. Recovery window

A recovery window is the time span into which the DBA wants to be able to recover the database to any point in time, counting backward from the present.

For example, `RECOVERY WINDOW OF 7 DAYS` means the objective is to recover to any point within the last 7 days, provided the required backups, archived logs, control files, encryption keys, and dependencies remain available.

A recovery window does not mean "keep only backup files created in the last 7 days." A backup older than 7 days may need to be retained as a baseline, along with the archived logs from that backup up to the recovery point.

### 2.4. Redundancy

Redundancy is the number of backups to retain per datafile/control file to satisfy the policy. For instance, `REDUNDANCY 2` requires maintaining two valid backups as evaluated by RMAN's dependency logic and repository metadata.

Redundancy does not represent a number of days. If backups run nightly, redundancy 2 may protect only a short period; if backups run weekly, the same value of 2 can span a much longer window.

### 2.5. Obsolete and expired

These are two distinct states:

- **OBSOLETE:** the backup file is no longer needed to satisfy the current retention policy.
- **EXPIRED:** RMAN checked the repository and could not find the file at the recorded location, or its existence could not be confirmed during crosscheck.

Obsolete describes whether a file is still needed for recovery. Expired describes whether a file is physically present/confirmed on storage.

A backup can be `AVAILABLE` yet `OBSOLETE`. A backup can be `EXPIRED` because storage was temporarily unreachable; never delete records immediately before verifying storage.

## 3. Configuring the retention policy in RMAN

View current settings:

~~~text
RMAN> SHOW RETENTION POLICY;
RMAN> SHOW ALL;
~~~

RMAN typically defaults the retention policy to `REDUNDANCY 1` if not configured otherwise. Do not rely on defaults: always inspect the actual configuration of your database and backup environment.

### 3.1. Configuring by redundancy

Example keeping redundancy 2:

~~~text
RMAN> CONFIGURE RETENTION POLICY TO REDUNDANCY 2;
~~~

This configuration instructs RMAN to retain the specified number of backups according to redundancy rules. Backups exceeding the required count can become `OBSOLETE` if no other dependencies/recoveries require them.

Use redundancy when the objective is defined by backup count, such as keeping two valid independent backup copies per policy.

Remember:

- Backup count alone does not indicate how many days of recovery exist.
- Irregular backup schedules cause the effective protection span to vary.
- Incremental backups depend on a level 0 or backup chain.
- Archived logs needed to recover backups must still be retained.
- An unreadable backup or one missing an encryption key provides no actual recoverability.

### 3.2. Configuring by recovery window

Example maintaining a 7-day recovery window:

~~~text
RMAN> CONFIGURE RETENTION POLICY TO RECOVERY WINDOW OF 7 DAYS;
~~~

RMAN evaluates backups based on being able to recover to any point within the requested window. Older backups may still be needed as base backups to recover up to the start of the window.

Use a recovery window when business requirements are expressed in time, such as:

- Ability to restore the database to any point within the last 7 days.
- Ability to investigate erroneous data for 14 days.
- Ability to recover accidentally deleted transactions within 30 days.

A recovery window requires continuous archived redo log coverage from a valid backup up to the recovery point. If there is a gap, missing logs, or a corrupted backup, a properly configured policy still cannot guarantee recovery.

### 3.3. Comparing the two options

| Criterion | REDUNDANCY n | RECOVERY WINDOW OF n DAYS |
|---|---|---|
| Objective | Number of backups | Recovery time span |
| Backup schedule dependency | Yes, affects actual days of protection | Yes, backups/logs must cover the window |
| Business interpretability | Less intuitive | Directly expressed in days |
| Older base backups | RMAN evaluates dependencies | May retain backups older than window start |
| Best suited for | Copy-count policies | Time-based RPO/PITR policies |
| Guarantees restore success | Not automatically | Not automatically |

No value of `n` always equals a fixed recovery window. For example, `REDUNDANCY 2` does not equal `RECOVERY WINDOW OF 2 DAYS`.

### 3.4. NONE and changing policy

RMAN allows setting the retention policy to `NONE` when disabling retention-based obsolete marking is required:

~~~text
RMAN> CONFIGURE RETENTION POLICY TO NONE;
~~~

This is not a safe default for normal operations. When the retention policy is `NONE`, RMAN does not mark backups obsolete under that policy. This can cause backups to grow indefinitely if no other cleanup process exists.

If changing the policy, record:

- Old and new values.
- Approver.
- Effective time.
- Impact on the FRA and backup storage.
- Rollback plan.
- How to verify backups still meet RPO/RTO.

## 4. Recovery window in practice

Suppose today is day 14 and the required recovery window is 7 days. The objective is to recover to any point from day 7 to the present.

If the latest full backup was taken on day 10, recovering to day 8 cannot use day 10's backup because it is newer than the target point. RMAN needs a suitable backup taken before day 8 plus the archived logs from that backup up to day 8.

Thus, the policy may retain a backup older than the start of the window. This is necessary to satisfy the recovery window, not wasted redundancy.

### 4.1. Backup chains and incrementals

Example schedule:

- Sunday: incremental level 0.
- Monday through Saturday: incremental level 1.
- Continuous archived redo log backups.

Recovering to an SCN requires the proper base backup, required incremental backups, and continuous archived redo logs up to that SCN.

Never manually delete a level 0 simply because it is older than 7 days if level 1s or the recovery window still depend on it.

### 4.2. Archived redo log coverage

A recovery window requires continuous log coverage. Verify:

- Archived logs are generated completely on all threads.
- Backup jobs back up the logs.
- Logs are not deleted before standby apply if required.
- Logs remain accessible on storage.
- The RMAN repository holds accurate metadata.
- Log/backup copies exist in a recoverable location.

In RAC, each redo thread has its own sequence. Do not inspect only thread 1.

### 4.3. Recovery window does not cover all data retention types

RMAN's retention policy manages backups according to RMAN rules. It does not replace:

- Application audit retention.
- Legal/regulatory archive log retention policies.
- Export/Data Pump retention.
- Storage snapshot retention.
- Flashback Data Archive retention.
- Guaranteed restore point / flashback log retention.
- Offsite or immutable backup copy retention.

These storage layers may have their own policies and owners.

## 5. Archived log deletion policy

The archived log deletion policy specifies the conditions an archived redo log must meet before RMAN allows deleting it.

View the policy:

~~~text
RMAN> SHOW ARCHIVELOG DELETION POLICY;
~~~

Or view the entire configuration:

~~~text
RMAN> SHOW ALL;
~~~

### 5.1. Deleting after backing up a specified number of times

Example requiring each archived log to be backed up at least once to DISK:

~~~text
RMAN> CONFIGURE ARCHIVELOG DELETION POLICY
      TO BACKED UP 1 TIMES TO DEVICE TYPE DISK;
~~~

If using SBT/tape:

~~~text
RMAN> CONFIGURE ARCHIVELOG DELETION POLICY
      TO BACKED UP 1 TIMES TO DEVICE TYPE SBT;
~~~

This condition enforces backup count to the specified device type. It does not prove the backup was copied offsite, is immutable, or passed a restore test.

If the backup job writes a copy onto the same storage as the archive logs, losing that storage destroys both. Distinguish RMAN copy counts from independent failure domains.

### 5.2. Deleting only after standby applies redo

In Data Guard, the primary can require archived logs to be applied to standbys before becoming eligible for deletion:

~~~text
RMAN> CONFIGURE ARCHIVELOG DELETION POLICY
      TO APPLIED ON ALL STANDBY;
~~~

The `APPLIED ON STANDBY` condition prevents deleting logs before standbys apply them. Depending on configuration and standby count, `ALL` requires satisfying the condition for every standby in scope.

If a standby goes down or experiences prolonged apply lag, archived logs may not be deleted and the FRA may grow. That is a signal to fix Data Guard, not a reason to blindly drop the deletion policy.

### 5.3. Deleting only after shipping to standby

You can require logs to have been shipped to standbys:

~~~text
RMAN> CONFIGURE ARCHIVELOG DELETION POLICY
      TO SHIPPED TO ALL STANDBY;
~~~

`SHIPPED` and `APPLIED` are different states:

- Shipped: redo has been transferred to the standby.
- Applied: redo has been applied to the standby's datafiles.

If protection requires the standby to have applied the changes, shipping alone is not enough. Choose the condition based on RPO, transport/apply mode, and HA design.

### 5.4. Combining conditions

A policy may require multiple conditions, such as logs being applied on standbys and backed up to a required device type. Exact combined syntax depends on the Oracle release and RMAN configuration grammar; check the SQL/RMAN Reference for your running version before deploying.

Never modify a production policy with an untested combined clause. After configuring, run `SHOW ARCHIVELOG DELETION POLICY` and verify behavior with backup/delete tests in a lab.

### 5.5. Deletion policy is not backup retention policy

Example:

- Backup retention: `RECOVERY WINDOW OF 14 DAYS`.
- Archive deletion: `BACKED UP 1 TIMES TO DEVICE TYPE DISK`.
- Data Guard: requires `APPLIED ON ALL STANDBY`.

These three rules answer three different questions: which backups to retain, whether logs have been backed up, and whether standbys have applied them.

## 6. OBSOLETE: backups no longer needed by retention policy

RMAN marks a backup `OBSOLETE` when it is no longer required to satisfy the active retention policy, taking dependencies and repository metadata into account.

List obsolete backups:

~~~text
RMAN> REPORT OBSOLETE;
~~~

This command only reports. It does not delete files.

You can list backups:

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> LIST BACKUP OF DATABASE;
RMAN> LIST BACKUP OF ARCHIVELOG ALL;
~~~

Cross-reference against your backup schedule, recovery window, redundancy, and actual restore requirements.

### 6.1. Deleting obsolete backups

After reviewing the report and obtaining cleanup authorization:

~~~text
RMAN> DELETE OBSOLETE;
~~~

RMAN prompts for confirmation in normal interactive mode. The command deletes backups evaluated as obsolete under the retention policy and updates the repository.

In automation, never bypass prompts or use `NOPROMPT` unless you have:

- An approved policy.
- Saved obsolete reports.
- Verified remaining backups.
- Confirmed the recovery window remains satisfied.
- Checked standby and archive log deletion policies.
- Auditing/logging of command output.

### 6.2. OBSOLETE does not mean corrupted

An obsolete backup may still be completely readable. It is simply no longer required under the current retention policy.

An `AVAILABLE` backup can be `OBSOLETE`. An `EXPIRED` backup may still be considered needed by the repository even though the file is missing. These two statuses are not interchangeable.

### 6.3. Changing retention changes the obsolete list

Switching from a 30-day recovery window to 7 days can immediately mark many backups obsolete. Conversely, extending from 7 to 30 days cannot bring back backups or logs that were already deleted.

Before shortening retention, review legal obligations, business recovery requirements, offsite copies, and remaining backups. A new policy can alter `REPORT OBSOLETE` results immediately.

## 7. EXPIRED: repository cannot locate the file

`CROSSCHECK` checks repository metadata against storage.

~~~text
RMAN> CROSSCHECK BACKUP;
RMAN> CROSSCHECK ARCHIVELOG ALL;
~~~

Results can update a backup's status from `AVAILABLE` to `EXPIRED` if the file is not found. If the file becomes accessible again, a subsequent crosscheck marks it `AVAILABLE`.

### 7.1. Why can a file become EXPIRED?

- Backup mount or NFS share is temporarily unavailable.
- Object storage/network error.
- Tape library media is not mounted.
- File was moved or deleted outside RMAN.
- Incorrect path, credentials, or storage configuration.
- Backup piece was genuinely deleted.
- Control file/catalog metadata no longer matches storage.

`EXPIRED` alone does not state the root cause. Before purging records, verify storage and backup locations.

### 7.2. DELETE EXPIRED

After confirming files are genuinely gone and assessing recovery impact:

~~~text
RMAN> DELETE EXPIRED BACKUP;
RMAN> DELETE EXPIRED ARCHIVELOG ALL;
~~~

`DELETE EXPIRED` deletes repository records for files RMAN marked expired. It does not delete physical files sitting somewhere else.

Do not use `DELETE EXPIRED` to clean up backups that still exist on temporarily offline storage. If you delete those records, you will need to resync or re-catalog the files once storage returns.

### 7.3. Summary of differences

| Status/command | Meaning | Effect |
|---|---|---|
| AVAILABLE | RMAN believes file is present per repository | Can be used in restore if physically readable |
| EXPIRED | CROSSCHECK did not find the file | Repository marks file unavailable |
| OBSOLETE | No longer needed under retention policy | Eligible for removal via DELETE OBSOLETE |
| CROSSCHECK | Reconciles repository against storage | Updates statuses; does not clean files |
| DELETE EXPIRED | Removes expired records | Does not delete physical files |
| DELETE OBSOLETE | Deletes obsolete backups | Deletes backup files and updates repository |

## 8. Safe cleanup procedure

An operational procedure should separate observation, decision-making, and deletion.

### Step 1 — Confirm the right database

Check DBID, `DB_NAME`, `DB_UNIQUE_NAME`, role, instance, and environment. Avoid running RMAN against the wrong database or wrong catalog.

In SQL:

~~~sql
SELECT dbid,
       name,
       db_unique_name,
       database_role,
       open_mode
FROM v$database;
~~~

### Step 2 — Inspect configuration

~~~text
RMAN> SHOW RETENTION POLICY;
RMAN> SHOW ARCHIVELOG DELETION POLICY;
RMAN> SHOW ALL;
~~~

Record the policies and device types. Check Data Guard-specific settings if applicable.

### Step 3 — Check backup inventory

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> LIST BACKUP OF DATABASE;
RMAN> LIST BACKUP OF ARCHIVELOG ALL;
RMAN> REPORT NEED BACKUP;
~~~

Identify the most recent backups, level 0/incremental chains, archived log coverage, control file/SPFILE backups, and storage locations.

### Step 4 — Crosscheck when needed

~~~text
RMAN> CROSSCHECK BACKUP;
RMAN> CROSSCHECK ARCHIVELOG ALL;
~~~

`CROSSCHECK` gives an up-to-date repository state. If storage is unavailable, stop here and restore connectivity before running `DELETE EXPIRED`.

### Step 5 — Report obsolete

~~~text
RMAN> REPORT OBSOLETE;
~~~

Review the list and verify remaining backups satisfy retention, recovery window, and restore needs. If results look unexpected after a policy change, do not proceed with deletion until you understand why.

### Step 6 — Check archived log deletion policy

~~~text
RMAN> SHOW ARCHIVELOG DELETION POLICY;
RMAN> LIST ARCHIVELOG ALL;
~~~

With Data Guard, check transport/apply lag, gaps, and standby status. With backup-count policies, verify logs were backed up to the right device type.

### Step 7 — Perform controlled deletion

Only after review and approval:

~~~text
RMAN> DELETE OBSOLETE;
~~~

If expired records truly correspond to missing files and impact has been assessed:

~~~text
RMAN> DELETE EXPIRED BACKUP;
RMAN> DELETE EXPIRED ARCHIVELOG ALL;
~~~

Never combine obsolete and expired deletions into one step without reporting first.

### Step 8 — Verify after cleanup

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> REPORT NEED BACKUP;
RMAN> SHOW RETENTION POLICY;
RMAN> SHOW ARCHIVELOG DELETION POLICY;
~~~

Verify FRA/storage, archived log backlog, Data Guard lag, and the next backup job result. Save the RMAN log and approver details.

## 9. FRA and automatic reclaimable space

The Fast Recovery Area (FRA) is an Oracle-managed location for recovery files such as backup pieces, archived redo logs, flashback logs, and control file autobackups depending on configuration.

View the FRA:

~~~sql
SELECT name,
       space_limit,
       space_used,
       space_reclaimable,
       number_of_files
FROM v$recovery_file_dest;
~~~

View usage by file type:

~~~sql
SELECT file_type,
       percent_space_used,
       percent_space_reclaimable,
       number_of_files
FROM v$recovery_area_usage
ORDER BY file_type;
~~~

`SPACE_RECLAIMABLE` is the space Oracle estimates can be reclaimed under FRA management rules; it does not mean every file can be deleted immediately.

### 9.1. FRA reclamation and retention

When the FRA needs space, Oracle can reclaim eligible files according to recovery area rules. Retention policies and archived log deletion policies govern which files are eligible.

If no files are reclaimable, the database may raise errors due to a full FRA. Increasing `SPACE_LIMIT` helps only if the underlying filesystem/ASM/cloud storage actually has free capacity.

### 9.2. Flashback logs and guaranteed restore points

A guaranteed restore point can retain the flashback logs required to flash back to that point. Those logs may not be reclaimed like ordinary logs, causing the FRA to fill rapidly.

Inspect restore points:

~~~sql
SELECT name,
       scn,
       time,
       guarantee_flashback_database,
       storage_size
FROM v$restore_point
ORDER BY time;
~~~

Never drop a guaranteed restore point solely to free FRA space without confirming the owner, expiration, and recovery goal. Doing so can eliminate the ability to flash back to a committed milestone.

### 9.3. Handling a nearly full FRA

1. Identify which file types consume space.
2. Check backup retention and obsolete reports.
3. Check archive deletion policy and Data Guard apply status.
4. Check guaranteed restore points and flashback logs.
5. Verify underlying storage headroom.
6. Choose a remediation: fix standby lag, back up logs, clean obsolete backups via RMAN, expand storage, or adjust policy with approval.
7. Confirm the FRA has headroom and recovery protection remains intact.

Never delete files directly in the FRA using OS commands.

## 10. Backup optimization is not a retention policy

RMAN provides the `BACKUP OPTIMIZATION` setting:

~~~text
RMAN> CONFIGURE BACKUP OPTIMIZATION ON;
~~~

Backup optimization allows RMAN to skip backing up certain files that already have a valid backup on the device type according to optimization rules. It can reduce redundant backup time and space.

However:

- It does not determine which backups are obsolete.
- It does not replace the retention policy.
- It does not replace the archived log deletion policy.
- It does not prove existing backups are still readable.
- It does not create independent copies in another failure domain.

If enabling optimization, understand the conditions RMAN uses to consider a file already backed up. Whenever your backup strategy changes, re-verify device types, retention, and availability.

## 11. Data Guard: coordinating retention and deletion

In Data Guard, the primary may generate archived redo logs faster than a standby receives or applies them. If the deletion policy requires `APPLIED ON ALL STANDBY`, unapplied logs will not be eligible for deletion under the policy.

### 11.1. Monitoring transport/apply lag

On the standby or a database with appropriate access:

~~~sql
SELECT name,
       value,
       unit,
       time_computed,
       datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag', 'apply finish time');
~~~

Inspect archive destinations:

~~~sql
SELECT dest_id,
       status,
       error,
       destination
FROM v$archive_dest_status
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
~~~

And archive gaps:

~~~sql
SELECT thread#,
       low_sequence#,
       high_sequence#
FROM v$archive_gap;
~~~

### 11.2. What happens when a standby stops applying?

If a standby disconnects or experiences prolonged apply lag:

- Archived logs on the primary may not be deleted.
- The FRA can grow rapidly.
- The primary may face storage pressure.
- RPO/HA protection may degrade.
- Using `FORCE` to delete logs can prevent the standby from catching up.

Never drop the `APPLIED` requirement just to shrink the FRA. Restore transport/apply first, or evaluate the standby against DR policy.

### 11.3. Multiple standbys

When using `ALL STANDBY`, a single lagging standby can hold logs back even if other standbys have already applied them. This may be desirable behavior to ensure every required standby can recover.

If a standby is permanently retired, decommission it properly following Data Guard procedures and update policies/topology. Never strip configurations or bypass a standby just to clear a backlog without DR assessment.

## 12. Sample backup strategy configuration

Suppose a system needs:

- 14-day PITR capability.
- Daily scheduled full/incremental backups.
- Archived logs backed up to DISK at least once before deletion.
- Standby protection where logs are deleted only after standby apply.
- Control file autobackup always enabled.

A starting configuration to review:

~~~text
RMAN> CONFIGURE RETENTION POLICY
      TO RECOVERY WINDOW OF 14 DAYS;

RMAN> CONFIGURE ARCHIVELOG DELETION POLICY
      TO APPLIED ON ALL STANDBY;

RMAN> CONFIGURE CONTROLFILE AUTOBACKUP ON;
~~~

If you also need a backup-count requirement for archived logs, configure the combined syntax for your exact Oracle release and test in a lab.

The configuration above does not replace a backup schedule. Jobs must actually execute database backups, archived log backups, controlfile/SPFILE autobackups, and offsite copies.

### 12.1. Backing up the database and archived logs

Example backup command:

~~~text
RMAN> BACKUP DATABASE PLUS ARCHIVELOG;
~~~

This illustrates backing up the database alongside archived redo logs; a production schedule must consider incremental levels, channels, compression, encryption, parallelism, storage, and workload.

### 12.2. Backing up archived logs and DELETE INPUT

Example:

~~~text
RMAN> BACKUP ARCHIVELOG ALL DELETE INPUT;
~~~

`DELETE INPUT` instructs RMAN to delete backed-up input archived logs when conditions permit. The archived log deletion policy still governs deletion operations unless overridden with force.

Never use `DELETE INPUT` without understanding:

- Backup destination.
- Device type and backup copy counts.
- Data Guard apply/ship requirements.
- Archive logs still needed for the recovery window.
- Storage failure domains and offsite copies.

`DELETE INPUT` is not a command meaning "back up and delete unconditionally."

### 12.3. Control file and SPFILE

The control file stores backup metadata and database structure. Enable autobackup:

~~~text
RMAN> CONFIGURE CONTROLFILE AUTOBACKUP ON;
~~~

Verify backup output includes control file/SPFILE autobackups and know how to restore when the control file is lost. If using a recovery catalog, still protect the catalog database separately.

### 12.4. Encryption and key management

Encrypted backups can only be restored with the matching key/wallet/keystore. Your runbook must specify:

- TDE keystore/wallet location.
- Keystore backup per policy.
- Password/secret escrow.
- Procedure for opening the keystore during disaster recovery.
- Authorized personnel.
- How to verify key availability in the restore environment.

Never store passwords or raw key material directly inside an unprotected runbook.

## 13. Retention policy and recovery catalog

RMAN can store repository metadata in the control file or a recovery catalog. A recovery catalog retains longer backup history and manages multiple databases depending on design.

Keep in mind:

- The control file has configured/time limits on metadata retention.
- Old records can be reused per control file record keep time behavior.
- The recovery catalog must be backed up and protected.
- Catalog resyncs must run on schedule.
- Backups existing on storage without repository records may need to be re-cataloged.
- An `AVAILABLE` record does not guarantee storage/files are readable; validation is necessary.

The retention policy is evaluated using repository metadata and dependencies. An inaccurate repository can cause wrong reports and faulty cleanup decisions.

### 13.1. SHOW and REPORT as observation steps

Before modifying policies or deleting:

~~~text
RMAN> SHOW ALL;
RMAN> REPORT OBSOLETE;
RMAN> REPORT NEED BACKUP;
RMAN> LIST BACKUP SUMMARY;
~~~

Save the output prior to making changes for evidence and troubleshooting.

## 14. Recovery window, redundancy, and RPO/RTO

Retention policies must originate from business requirements.

| Requirement | Backup implication |
|---|---|
| 15-minute RPO | Archived redo logs must be protected frequently enough to cap data loss |
| 7-day PITR | Base backups and archived logs must cover every point in the 7-day window |
| Retain 2 backup copies | Can use REDUNDANCY 2, but failure domains must be defined |
| 1-hour RTO | Restore/recover must be tested and timed to complete within 1 hour |
| DR standby | Transport/apply and deletion policies must retain logs needed by standbys |
| Immutable/offsite | Requires storage policies and independent copies beyond basic RMAN retention |

A retention policy does not guarantee RTO. A backup may satisfy age criteria yet take 12 hours to restore due to large size or slow networking.

Likewise, a recovery window is not RPO. A recovery window defines how far back you can pick a recovery point; RPO defines the maximum tolerable data loss during an incident.

### 14.1. Backup count and failure domains

Two backup copies on the same disk array do not equal two independent copies if that array fails. Consider:

- Primary backup storage.
- Secondary/offsite copy.
- Object lock/immutability.
- Tape or cloud archive.
- Isolated credentials and accounts.
- Testing restores from the offsite copy.

RMAN redundancy count alone does not define your failure-domain architecture.

### 14.2. Setting retention to practical timeframes

Example:

- Online PITR: 14 days.
- Weekly long-term backup: 8 weeks.
- Monthly archive: 12 months.
- Immutable copy: per compliance retention.
- Audit/application logs: per separate policy.

Not every tier needs to be governed by the exact same RMAN retention policy. Separate operational backups, long-term archives, and compliance copies to prevent accidental deletion.

## 15. Changing the retention policy: change procedure

Shortening retention can immediately mark many backups obsolete. Extending retention cannot restore files deleted earlier.

Before changing:

1. Confirm database/DBID/`DB_UNIQUE_NAME` and RMAN target.
2. Save `SHOW ALL` and `SHOW RETENTION POLICY`.
3. Save `LIST BACKUP SUMMARY` and `REPORT OBSOLETE`.
4. Verify RPO/RTO and compliance retention.
5. Verify offsite/immutable copies.
6. Check Data Guard topology and deletion policy.
7. Calculate storage headroom and growth.
8. Obtain change approval and prepare a rollback plan.

Apply the new configuration:

~~~text
RMAN> CONFIGURE RETENTION POLICY
      TO RECOVERY WINDOW OF 14 DAYS;
~~~

Then verify:

~~~text
RMAN> SHOW RETENTION POLICY;
RMAN> REPORT OBSOLETE;
~~~

Do not delete immediately if the obsolete list grows unexpectedly. Compare against the old policy, backup chains, and recovery scenarios.

### 15.1. Policy rollback

If the new policy is unsuitable, restore the previous value:

~~~text
RMAN> CONFIGURE RETENTION POLICY
      TO REDUNDANCY 2;
~~~

Rolling back configuration does not restore deleted files. Therefore, policy changes and `DELETE` executions must be separated into distinct change steps/checkpoints.

## 16. Runbook: FRA growing rapidly or unable to reclaim space

**Trigger:** FRA exceeds warning threshold, `SPACE_RECLAIMABLE` is low, `ORA-19809`/`ORA-19804`, or archive destination errors occur.

### Step 1 — Confirm status

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
FROM v$recovery_area_usage;
~~~

### Step 2 — Check policies and backup inventory

~~~text
RMAN> SHOW RETENTION POLICY;
RMAN> SHOW ARCHIVELOG DELETION POLICY;
RMAN> REPORT OBSOLETE;
RMAN> LIST BACKUP SUMMARY;
~~~

### Step 3 — Identify growth cause

- Backup jobs creating more copies than intended.
- Archived logs not being backed up.
- Standby not applying or transport broken.
- Guaranteed restore point pinning flashback logs.
- Backup pieces non-reclaimable due to retention.
- FRA limit smaller than generation rate.
- Underlying storage out of headroom.

### Step 4 — Safe remediation

Choose one of the following based on root cause:

- Restore archive transport/apply.
- Run archived log backups per policy.
- Delete obsolete backups after review.
- Increase storage/FRA limit if physical capacity permits.
- Review guaranteed restore points with owners.
- Adjust backup schedule or retention via change approval.

Never delete files via OS commands and never use `DELETE FORCE` to bypass policy just to shrink usage.

### Step 5 — Verify

- FRA usage and growth rate drop.
- No remaining archive destination errors.
- Backup and archived log coverage remain intact.
- Data Guard lag is within thresholds.
- Restore window/RPO/RTO remain intact.
- Close the alert with documented evidence.

## 17. Runbook: backup marked EXPIRED

**Trigger:** `CROSSCHECK` marks backups `EXPIRED` or RMAN reports missing files.

1. Confirm the right database, DBID, `DB_UNIQUE_NAME`, and catalog.
2. Check mount points, NFS/object storage/tape, and credentials.
3. Verify whether the file exists at the expected location.
4. If storage was temporarily unavailable, restore connectivity and re-run `CROSSCHECK`.
5. If files are genuinely lost, identify affected backup chains and recovery points.
6. Determine whether other copies or offsite copies exist.
7. Run replacement backups if needed and assess RPO/RTO.
8. Only run `DELETE EXPIRED` after confirming the records truly have no remaining value.
9. Save RMAN output and incident records.

Never use `DELETE EXPIRED` to mask mount or permission failures.

## 18. Runbook: verifying the recovery window before restore

When a recovery request arrives:

1. Identify target time/SCN and business owner.
2. Confirm database incarnation and DBID.
3. Identify a suitable base backup prior to the target.
4. Identify the incremental chain.
5. Verify continuous archived logs up to the target.
6. Confirm control file/SPFILE and encryption keys.
7. Confirm destination/host has enough space.
8. Use `RESTORE ... PREVIEW` to inspect which files RMAN plans to use if appropriate.
9. Use `RESTORE ... VALIDATE` or `VALIDATE BACKUPSET` in an appropriate environment.
10. Execute restore/recover following the approved runbook.
11. Verify database, schema, and business data after recovery.
12. Record actual RTO/RPO and any data loss window.

Example RMAN commands to inspect restore paths:

~~~text
RMAN> RESTORE DATABASE PREVIEW;
RMAN> RESTORE DATABASE VALIDATE;
~~~

`PREVIEW` displays the backups RMAN plans to use; `VALIDATE` checks readability of backups needed for restore. Neither replaces a full restore test.

## 19. Common errors and misconceptions

| Mistake | Consequence | Proper approach |
|---|---|---|
| Thinking RECOVERY WINDOW 7 DAYS keeps only files created in the last 7 days | Accidentally deleting an older required base backup | Understand recovery window in terms of PITR capability |
| Thinking REDUNDANCY 2 equals 2 days | Protection window differs from expectations | Cross-check backup schedule and archived logs |
| Using retention policy instead of deletion policy | Archive logs retained/deleted under wrong conditions | Configure both policies separately |
| Thinking OBSOLETE means corrupted file | Wrongful deletion or misdiagnosis | OBSOLETE simply means no longer needed by retention |
| Thinking EXPIRED means obsolete backup | Deleting repository records while storage is temporarily offline | Check storage and re-run crosscheck |
| Running DELETE OBSOLETE without review | Deleting backups needed for other purposes | Run REPORT OBSOLETE and get approval |
| Running DELETE EXPIRED while mount is offline | Losing metadata for files that still exist | Restore storage connectivity first |
| Backing up logs once onto the same storage | Losing both logs and backups on storage failure | Maintain independent/offsite copies |
| Deleting logs before standby apply | Standby cannot catch up | Use APPLIED deletion policy |
| Dropping deletion policy to fix a full FRA | Can break RPO/DR | Fix transport/apply or storage instead |
| Thinking BACKUP OPTIMIZATION is retention | Missing required backups | Separate optimization from retention |
| Raising FRA quota without enough physical disk | Allocation failures persist | Check ASM/filesystem/cloud capacity |
| Deleting archives via OS | RMAN repository and recovery fall out of sync | Always use RMAN |
| Increasing retention after files were already deleted | Cannot recover deleted backups | Maintain offsite/immutable copies and restore plans |
| Checking only backup SUCCESS | Unknown whether restore works | Validate and run restore tests |
| Forgetting encryption keys/control file | Backups cannot be restored | Protect metadata and key material |

## 20. Practice labs

Perform in a lab database with dedicated backup storage. Never practice backup deletion on production.

### Exercise 1 — Inspect default retention

Run `SHOW RETENTION POLICY` and `SHOW ALL`. Note the current policy, device type, and archived log deletion policy.

### Exercise 2 — Redundancy

Configure `REDUNDANCY 2` in the lab, create multiple backups on a schedule, and run `REPORT OBSOLETE`. Observe which backups RMAN marks obsolete and why.

### Exercise 3 — Recovery window

Configure `RECOVERY WINDOW OF 7 DAYS`, create backups and archived logs over simulated days. Run `REPORT OBSOLETE` and identify which base backup must be kept.

### Exercise 4 — Comparing redundancy and recovery window

Keep the same backup schedule while switching policies between runs. Compare the obsolete lists. Explain why backup count does not equal day count.

### Exercise 5 — Crosscheck

Move a backup piece in the lab, run `CROSSCHECK BACKUP`, and observe the `EXPIRED` status. Move the file back, re-run crosscheck, and observe its status.

### Exercise 6 — Delete expired

Only after confirming a test file is genuinely gone, run `DELETE EXPIRED BACKUP`. Confirm the repository record is removed and explain why this command does not delete physical files.

### Exercise 7 — Delete obsolete

Run `REPORT OBSOLETE`, save the output, review dependencies, then run `DELETE OBSOLETE` in the lab. Check `LIST BACKUP SUMMARY` afterward.

### Exercise 8 — Archived log deletion policy

Configure `BACKED UP 1 TIMES TO DEVICE TYPE DISK`. Back up archive logs and verify `DELETE INPUT` behavior.

### Exercise 9 — Data Guard apply policy

In a Data Guard lab, configure `APPLIED ON STANDBY`. Pause apply per lab procedure, generate archives, and observe logs becoming ineligible for deletion. Resume apply and verify.

### Exercise 10 — FRA pressure

Generate enough backups/archive logs to grow FRA usage. Inspect `V$RECOVERY_FILE_DEST` and `V$RECOVERY_AREA_USAGE`. Identify file types and reclaimability conditions.

### Exercise 11 — Restore validation

Run `RESTORE DATABASE PREVIEW` and `RESTORE DATABASE VALIDATE`. Then restore into a test environment and measure actual duration.

### Exercise 12 — Recovery point

Choose an SCN within the recovery window, identify the base backup and archived log coverage, test recovery in a clone, and record actual RPO/RTO.

## 21. Checklist before deleting backups or archived logs

- [ ] Confirm the exact DBID, `DB_UNIQUE_NAME`, database role, and RMAN catalog.
- [ ] Record the current retention policy.
- [ ] Record the archived log deletion policy.
- [ ] Confirm RPO/RTO, PITR, and compliance requirements.
- [ ] Inspect `LIST BACKUP SUMMARY` and backup chains.
- [ ] Verify archived log coverage across all redo threads.
- [ ] Verify control file/SPFILE autobackup.
- [ ] Verify encryption wallet/keystore availability.
- [ ] Check Data Guard transport/apply/gaps if present.
- [ ] Run `CROSSCHECK` when needed and confirm storage availability.
- [ ] Distinguish `EXPIRED` from `OBSOLETE`.
- [ ] Run `REPORT OBSOLETE` and save the output.
- [ ] Review the list of files to be deleted and remaining backups.
- [ ] Confirm offsite/immutable copies if required.
- [ ] Obtain change approval and have a rollback/restore plan.
- [ ] Run `DELETE OBSOLETE` or `DELETE EXPIRED` for its proper purpose.
- [ ] Check `LIST BACKUP SUMMARY` and `REPORT NEED BACKUP` afterward.
- [ ] Verify FRA, archive destinations, and Data Guard after cleanup.
- [ ] Log RMAN output, operator, and timestamp.

## 22. Key takeaways

- The retention policy determines which backups are still needed to meet recovery goals; the archived log deletion policy governs conditions for deleting archived redo logs.
- `REDUNDANCY n` keeps a specific number of backups per RMAN rules; `RECOVERY WINDOW OF n DAYS` maintains recoverability to any point within that day window.
- `REDUNDANCY 2` does not mean a 2-day recovery window.
- A recovery window may require keeping a base backup older than the window start along with continuous archived logs up to the recovery point.
- Having backups on storage is not enough; control file/catalog metadata, encryption keys, and restore readability are also required.
- `OBSOLETE` means a backup is no longer needed under the retention policy; `EXPIRED` means crosscheck did not find the file.
- `CROSSCHECK` updates repository status; `DELETE EXPIRED` removes expired records; `DELETE OBSOLETE` removes backups no longer needed.
- Never delete expired records when storage is merely temporarily offline.
- Deletion policies can require archive logs to be backed up a specified number of times or shipped/applied to standbys.
- `SHIPPED` does not equal `APPLIED`; choose the condition based on RPO and Data Guard design.
- Backup optimization does not replace retention or deletion policies.
- The FRA automatically reclaims eligible files, but cannot guarantee free space if files are still needed for recovery or standbys.
- Guaranteed restore points can pin flashback logs and cause the FRA to grow.
- Never delete archived logs, backup pieces, or FRA files via OS commands.
- Extending retention after files have been deleted cannot recover those files; rolling back policy does not roll back a `DELETE`.
- `REPORT OBSOLETE`, `SHOW ALL`, `LIST BACKUP`, and restore validation must be part of the cleanup workflow.
- Backup `SUCCESS` does not prove RTO/RPO; test and rehearse actual restores.
- Design retention around business recovery windows, RPO/RTO, failure domains, compliance, and storage capacity.

### Oracle reference documentation

- [Oracle Database Backup and Recovery User's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/) — RMAN retention policy, redundancy, recovery window, obsolete backups, archived log deletion policy and FRA.
- [Oracle Database Backup and Recovery Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/rcmrf/) — CONFIGURE, REPORT, CROSSCHECK, DELETE, LIST, RESTORE and VALIDATE commands.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — V$RECOVERY_FILE_DEST, V$RECOVERY_AREA_USAGE, V$ARCHIVED_LOG and Data Guard views.
- [Oracle Data Guard Concepts and Administration](https://docs.oracle.com/en/database/oracle/oracle-database/19/sbydb/) — Redo transport, apply, standby availability and archive log management.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/) — Fast Recovery Area, archived redo logs, control files and database recovery configuration.

RMAN syntax, Data Guard deletion-policy options, multitenant behavior and repository metadata can vary by Oracle release. Verify the exact release reference and test retention changes, crosschecks, deletion and restore validation in a non-production environment before changing production backup policy.
