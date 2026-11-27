# Managing Redo Log Groups, Members, and Log Switches in Oracle Database

Online redo logs record changes made to the database. When a user transaction modifies data, Oracle generates redo records describing the changes required for recovery. LGWR (Log Writer) writes redo from the redo log buffer in the SGA to the online redo log files. Thanks to redo, Oracle can recover committed changes after an instance failure and work with media recovery mechanisms.

Online redo logs are organized into **redo log groups**. Each group has one or more **members**. Members within the same group are multiplexed copies of the same redo stream. When a group is being written to, LGWR writes the same redo to all members of that group.

A **log switch** occurs when Oracle shifts redo writing from the current group to the next group. A group that has just left the CURRENT state may remain ACTIVE because it is still needed for instance recovery, or become INACTIVE once checkpoints have advanced far enough. In ARCHIVELOG mode, the group must also be archived before it can be reused.

Redo log management therefore involves four interrelated tasks:

- Maintaining a sufficient number of groups for each redo thread.
- Multiplexing members across independent storage locations to reduce the risk of single-file corruption.
- Monitoring CURRENT/ACTIVE/INACTIVE status and archiving/checkpoints.
- Tuning group size, group count, and log switch frequency based on the workload's redo generation rate.

This document guides you through inspecting configurations, adding/dropping groups and members, performing log switches, diagnosing related wait events, and specific considerations for ARCHIVELOG, RAC, and Data Guard.

## 1. Online Redo Logs in Oracle Architecture

### 1.1 Redo Log Buffer and LGWR

When a transaction modifies a data block, Oracle generates redo entries and places them in the redo log buffer in the SGA. LGWR writes redo sequentially to online redo log files.

LGWR can be triggered by several conditions, such as:

- A user session commits.
- The redo log buffer needs space freed.
- A specific amount of time has elapsed or a threshold amount of redo has been generated.
- DBWR needs to write dirty buffers under certain conditions and the corresponding redo must be written first (write-ahead logging).
- A log switch or related administrative requests.

Redo is written to the online redo log before the corresponding data blocks are required to be written to datafiles. This is the write-ahead logging principle: to recover a data block, Oracle must first have the necessary redo durably stored.

### 1.2 Online Redo Log Files

Online redo log files are physical files used cyclically by the database. A database requires at least two redo log groups per redo thread so it can continue writing while one group is being processed/prepared for reuse.

At any given time, each thread has one group in the CURRENT state. When that group fills up, Oracle switches to another group. Once the old group is no longer needed for instance recovery and has satisfied archiving requirements (if in ARCHIVELOG mode), it can be reused in a subsequent cycle.

### 1.3 Redo Log Groups and Members

Example of a database with two groups, each having two members:

~~~text
Redo thread 1

       +-------------------------------+
       | Group 1  (CURRENT)             |
       |                               |
LGWR --+--> redo01a.log                |
       +--> redo01b.log                |
       +-------------------------------+

       +-------------------------------+
       | Group 2  (INACTIVE)            |
       |                               |
       +--> redo02a.log                |
       +--> redo02b.log                |
       +-------------------------------+
~~~

In this example, redo01a.log and redo01b.log are two members of the same group 1. They contain the exact same redo content and are not two separate log streams.

| Concept | Meaning |
|---|---|
| Redo log group | The unit Oracle selects as the CURRENT group for writing redo |
| Redo log member | A file belonging to a group; members within a group are multiplexed copies |
| Thread | An independent redo stream; in RAC, each instance typically has one redo thread |
| Sequence# | Log sequence number within a thread |
| Log switch | Shifting CURRENT to another group and incrementing sequence# |

### 1.4 Multiplexing

Multiplexing means a group has multiple members across different storage locations. LGWR writes identical redo to all members of the group.

The goal is to protect against the failure of a single file or storage device. If one member becomes corrupted while another member remains usable, the database can continue operating in many cases; the DBA must fix the configuration and restore redundancy promptly.

Placing two members in two different directories on the same disk does not provide disk-level fault tolerance. Members should be placed on independent disk groups, ASM failure groups, or storage failure domains according to the infrastructure architecture.

## 2. CURRENT, ACTIVE, INACTIVE, and Other States

Group status is viewed in V$LOG.STATUS.

| STATUS | Meaning |
|---|---|
| CURRENT | The group is currently being used by LGWR to write active redo |
| ACTIVE | The group is no longer CURRENT, but is still needed for instance recovery |
| INACTIVE | The group is no longer needed for instance recovery; it can be reused once other conditions are met |
| UNUSED | The group has never been written to or has not been used since creation |
| CLEARING | Oracle is clearing the group |
| CLEARING_CURRENT | Oracle is clearing a group that is currently CURRENT in a special situation |

Do not confuse ACTIVE with "currently being written." The group currently being written to is CURRENT. ACTIVE means the redo in the group may still be required for instance recovery to complete.

### 2.1 CURRENT

Each enabled redo thread has one CURRENT group at a time. V$LOG shows the active group number, thread number, and sequence number.

### 2.2 ACTIVE

A group may have been switched away from CURRENT, but checkpoints have not yet written enough dirty buffers for the group to no longer be needed for instance recovery. While a group remains ACTIVE, Oracle cannot reuse it as a normal log group.

### 2.3 INACTIVE

An INACTIVE group is no longer needed for instance recovery. In ARCHIVELOG mode, the group must also be successfully archived before reuse. INACTIVE does not automatically mean archiving has completed in every situation; always check the ARCHIVED column and related archive status.

### 2.4 UNUSED

A newly added or never-used group may be in the UNUSED state. Once the group is used and switched out of, it transitions to other states depending on checkpointing/archiving.

### 2.5 Member Status

V$LOGFILE.STATUS describes member condition, not group status:

| STATUS | Meaning |
|---|---|
| NULL/blank | The member is in normal use |
| INVALID | The file is inaccessible or not validated as a valid member |
| STALE | The member's contents are incomplete or out of sync with active redo |
| DELETED | The member has been dropped from the database configuration |

Do not confuse V$LOG.STATUS with V$LOGFILE.STATUS. A group can be ACTIVE while one of its members is INVALID.

## 3. ARCHIVELOG and NOARCHIVELOG

A database can operate in ARCHIVELOG or NOARCHIVELOG mode.

### 3.1 ARCHIVELOG Mode

In ARCHIVELOG mode, once a redo log group fills up and is switched out, ARCn (Archiver processes) or the configured archiving mechanism copies the redo log into an archived redo log. Once the group is INACTIVE and archived, Oracle can reuse that group.

Archived redo logs support:

- Media recovery after a datafile or storage failure.
- Point-in-time recovery.
- Consistent online backups.
- Data Guard redo transport/apply.

ARCHIVELOG mode does not mean every group is archived instantaneously at switch time. Archiving may occur asynchronously after the switch.

### 3.2 NOARCHIVELOG Mode

In NOARCHIVELOG mode, redo log groups are reused once they are no longer needed for instance recovery/checkpointing. Oracle does not retain archived redo logs across normal switch cycles.

Media recovery capability is limited; the backup strategy must be aligned accordingly and typically requires consistent backups taken while the database is shut down using an appropriate procedure.

### 3.3 Checking Archive Mode

~~~sql
ARCHIVE LOG LIST;
~~~

Or:

~~~sql
SELECT log_mode,
       force_logging,
       open_mode,
       database_role
FROM v$database;
~~~

LOG_MODE indicates ARCHIVELOG or NOARCHIVELOG. DATABASE_ROLE helps distinguish PRIMARY from STANDBY in Data Guard environments.

## 4. Inspecting Current Redo Log Configuration

### 4.1 Viewing Groups

~~~sql
SELECT group#,
       thread#,
       sequence#,
       bytes,
       blocks,
       members,
       archived,
       status,
       first_change#,
       first_time,
       next_change#,
       next_time
FROM v$log
ORDER BY thread#, group#;
~~~

Key columns:

- GROUP#: group number.
- THREAD#: redo thread containing the group.
- SEQUENCE#: sequence number of the log.
- BYTES: group size in bytes.
- MEMBERS: number of declared members.
- ARCHIVED: archive status of the log.
- STATUS: CURRENT/ACTIVE/INACTIVE/UNUSED and clearing states.
- FIRST_CHANGE#/FIRST_TIME: starting SCN/timestamp of the log.
- NEXT_CHANGE#/NEXT_TIME: ending point in log metadata when available.

### 4.2 Viewing Individual Members

~~~sql
SELECT group#,
       type,
       member,
       status,
       is_recovery_dest_file,
       con_id
FROM v$logfile
ORDER BY group#, member;
~~~

GROUP# joins with V$LOG.GROUP#. MEMBER is the file path or ASM disk group/file name. TYPE is typically ONLINE or STANDBY. STATUS helps identify INVALID, STALE, or DELETED members.

### 4.3 Viewing Groups and Members in One Query

~~~sql
SELECT l.thread#,
       l.group#,
       l.sequence#,
       l.bytes,
       l.status AS group_status,
       l.archived,
       f.member,
       f.status AS member_status,
       f.type
FROM v$log l
JOIN v$logfile f
  ON f.group# = l.group#
ORDER BY l.thread#, l.group#, f.member;
~~~

A group appears in multiple rows if it has multiple members. This is expected, not a duplicate error.

### 4.4 Counting Groups per Thread

~~~sql
SELECT thread#,
       COUNT(*) AS group_count,
       MIN(bytes) AS min_group_bytes,
       MAX(bytes) AS max_group_bytes,
       SUM(members) AS total_members
FROM v$log
GROUP BY thread#
ORDER BY thread#;
~~~

Groups within the same thread should be configured with uniform sizes so log switches and reuse occur predictably. Check both the member count and size of each group.

### 4.5 Checking Redo Threads

~~~sql
SELECT thread#,
       status,
       enabled,
       instance,
       groups,
       current_group#
FROM v$thread
ORDER BY thread#;
~~~

V$THREAD shows the thread, status, and associated instance. In RAC, verify that each thread is enabled and has enough groups per the desired configuration.

## 5. Adding Redo Log Groups

You can add redo log groups while the database is OPEN under normal circumstances. Choose an unused group number, an appropriate size, and file locations with sufficient space and IOPS.

### 5.1 Adding a Group with Explicit File Names

~~~sql
ALTER DATABASE ADD LOGFILE GROUP 4
(
    '/u02/oradata/ORCL/redo04a.log',
    '/u03/oradata/ORCL/redo04b.log'
)
SIZE 1G;
~~~

This command creates group 4 with two members. Both files in the same group have the same size and the same redo content. The paths must exist or be creatable by Oracle according to the storage mechanism in use; the Oracle OS user needs appropriate permissions.

### 5.2 Adding a Group Using Oracle Managed Files

If the database has configured online redo log file locations using DB_CREATE_ONLINE_LOG_DEST_n or appropriate OMF settings, Oracle can generate the filenames automatically:

~~~sql
ALTER DATABASE ADD LOGFILE GROUP 5 SIZE 1G;
~~~

Oracle creates the members according to the OMF configuration. Query V$LOGFILE afterward to see the actual filenames and locations.

### 5.3 Adding a Group for a Specific Redo Thread

In RAC, specify the thread when adding a group for the corresponding instance/thread:

~~~sql
ALTER DATABASE ADD LOGFILE THREAD 2 GROUP 6
(
    '+DATA/ORCL/ONLINELOG/redo_t2_g6a.log',
    '+FRA/ORCL/ONLINELOG/redo_t2_g6b.log'
)
SIZE 1G;
~~~

ASM path examples are illustrative only. With OMF/ASM, follow the system's naming and failure-group design. Group numbers must be unique across the database.

### 5.4 Verifying After Addition

~~~sql
SELECT group#,
       thread#,
       bytes,
       members,
       status
FROM v$log
WHERE group# IN (4, 5, 6)
ORDER BY thread#, group#;

SELECT group#,
       member,
       status,
       type
FROM v$logfile
WHERE group# IN (4, 5, 6)
ORDER BY group#, member;
~~~

New groups typically remain in the UNUSED state until they are written to. Verify the actual member count, size, and paths before relying on them in production.

## 6. Adding a Member to a Group

Add a member to increase redundancy for an existing group. The new member must have a valid name/path, match the size of the existing members in the group, and reside on an appropriate failure domain.

### 6.1 Adding a Member by File Name

~~~sql
ALTER DATABASE ADD LOGFILE MEMBER
    '/u04/oradata/ORCL/redo01c.log'
TO GROUP 1;
~~~

Oracle creates a new member belonging to group 1. Do not specify SIZE because the size is inherited from the group.

### 6.2 Adding a Member Using OMF

When OMF is configured, you can let Oracle choose the filename:

~~~sql
ALTER DATABASE ADD LOGFILE MEMBER TO GROUP 1;
~~~

Verify the new path in V$LOGFILE. Exact syntax depends on OMF configuration and release; if the system requires a filename, provide one created according to storage standards.

### 6.3 Verifying the New Member

~~~sql
SELECT l.group#,
       l.thread#,
       l.status AS group_status,
       f.member,
       f.status AS member_status
FROM v$log l
JOIN v$logfile f
  ON f.group# = l.group#
WHERE l.group# = 1
ORDER BY f.member;
~~~

After addition, the member may not be fully validated until Oracle initializes/synchronizes it during the next log lifecycle. If V$LOGFILE.STATUS is INVALID or STALE, check the alert log and handle the member based on actual status; do not drop a valid member just because the new member is not ready yet.

### 6.4 Proper Multiplexing

Example where group 1 has two members:

~~~text
+----------------------+       +----------------------+
| Storage failure A    |       | Storage failure B    |
| redo01a.log          |       | redo01b.log          |
+----------------------+       +----------------------+
             \                       /
              \                     /
               +-------------------+
               | Redo log group 1  |
               | same redo stream  |
               +-------------------+
~~~

Members of the same group should be placed on independent devices or failure groups. Two different paths on the same filesystem/device do not protect against a failure of that device.

## 7. Dropping a Member or Dropping a Group

Never drop a redo log based solely on its filename. First identify the group, thread, status, archive status, and member list.

### 7.1 Conditions for Dropping a Member

You can drop a member when the group still has at least one other valid member. A group cannot be left with zero members. Do not drop a member needed to maintain redo-writing availability.

~~~sql
ALTER DATABASE DROP LOGFILE MEMBER
    '/u04/oradata/ORCL/redo01c.log';
~~~

After the command, Oracle removes the member from the control file. Removing the physical file from the filesystem/ASM depends on storage status and procedures; check V$LOGFILE before deleting manually. Do not delete the file while the database still references it.

### 7.2 Conditions for Dropping a Group

Before dropping a group:

1. The group must not be CURRENT.
2. The group must no longer be ACTIVE; it must be INACTIVE so it is no longer needed for instance recovery.
3. In ARCHIVELOG mode, the log must be archived as required.
4. The thread must still have enough groups remaining after the drop; do not drop the last group or leave the configuration unable to continue operating.
5. Ensure backup/recovery policies and remaining member counts still meet requirements.

Example:

~~~sql
ALTER DATABASE DROP LOGFILE GROUP 4;
~~~

If the group is CURRENT, perform a log switch and wait for the group to transition to a droppable state. If the group is ACTIVE, wait for the checkpoint to complete or resolve whatever is keeping the group needed for instance recovery. In ARCHIVELOG mode, confirm archiving has completed.

### 7.3 Checking Before and After Dropping

~~~sql
SELECT group#,
       thread#,
       sequence#,
       archived,
       status
FROM v$log
ORDER BY thread#, group#;

SELECT group#,
       member,
       status
FROM v$logfile
ORDER BY group#, member;
~~~

After dropping, confirm the group/member no longer appears in the control file. If physical files remain on disk, clean them up only after confirming they are not used by another database or configuration.

### 7.4 Why Should You Not Drop a CURRENT or ACTIVE Group?

- CURRENT is actively being used by LGWR to write redo.
- ACTIVE may contain redo required for instance recovery.
- Dropping in the wrong state can be rejected by Oracle or break recovery capability if improper clear operations are used.

Do not try to bypass checks by clearing or deleting files at the OS level. Switch, archive, and wait for checkpoints following proper procedure.

## 8. Log Switches

A log switch is the process where Oracle switches the CURRENT group to another group within the same redo thread. During a switch:

- The new group becomes CURRENT.
- SEQUENCE# increments in the thread.
- The old group is no longer CURRENT; it may be ACTIVE or INACTIVE depending on checkpoints.
- In ARCHIVELOG mode, the old group is archived asynchronously.

### 8.1 When Does Automatic Switching Occur?

LGWR switches to another group when the CURRENT group fills up. Oracle continues writing redo into the next available group.

If the next group is not ready because a checkpoint has not finished or archiving is incomplete, the database may have to wait. This is why having enough groups and proper group sizing is essential.

### 8.2 Forcing a Manual Log Switch

~~~sql
ALTER SYSTEM SWITCH LOGFILE;
~~~

This command requests a redo log switch for the thread of the current instance. It is useful for testing configuration, archiving, or moving the current group out of the CURRENT state before administrative operations. In RAC, identify which instance/thread you are operating on.

### 8.3 Forcing Archiving of the Current Log

~~~sql
ALTER SYSTEM ARCHIVE LOG CURRENT;
~~~

In ARCHIVELOG mode, this command requests archiving of the current redo log; this operation includes switching the log so the log can be archived. It is often used in backup procedures or when you need to guarantee the current log is archived.

SWITCH LOGFILE and ARCHIVE LOG CURRENT are not identical in intent:

| Command | Objective |
|---|---|
| ALTER SYSTEM SWITCH LOGFILE | Requests switching to another redo log group |
| ALTER SYSTEM ARCHIVE LOG CURRENT | Requests archiving the current redo log; typically includes a log switch |

Switching does not guarantee archiving has finished. Afterward, check V$LOG.ARCHIVED, V$ARCHIVED_LOG, and the alert log.

### 8.4 Tracking Sequences Before and After a Switch

~~~sql
SELECT thread#,
       group#,
       sequence#,
       status,
       archived,
       first_time
FROM v$log
ORDER BY thread#, group#;
~~~

After the switch, the CURRENT group has a new sequence. The old group transitions to ACTIVE or INACTIVE.

### 8.5 Tracking Switch History

~~~sql
SELECT thread#,
       sequence#,
       first_time,
       first_change#
FROM v$log_history
ORDER BY first_time DESC
FETCH FIRST 50 ROWS ONLY;
~~~

V$LOG_HISTORY records log switch history by thread/sequence. You can use FIRST_TIME to calculate the interval between consecutive switches.

~~~sql
SELECT thread#,
       sequence#,
       first_time,
       ROUND(
           (first_time - LAG(first_time) OVER (
               PARTITION BY thread#
               ORDER BY first_time
           )) * 1440,
           2
       ) AS minutes_since_previous_switch
FROM v$log_history
ORDER BY thread#, first_time DESC;
~~~

Very short intervals between consecutive switches may indicate groups are too small or redo generation has spiked. Compare against workload patterns and batch/ETL schedules.

## 9. Checkpoints, Archiving, and Group Reusability

A log switch only changes the CURRENT group; it does not immediately make the old group INACTIVE.

### 9.1 Checkpoint

Checkpoints write dirty buffers from the buffer cache to datafiles and update checkpoint information in control file/datafile headers. Once a checkpoint advances past the redo range of a group, that group may no longer be needed for instance recovery.

If the checkpoint has not finished, the old group may remain ACTIVE.

### 9.2 Archive

In ARCHIVELOG mode, a redo log must be archived before the group can be reused. ARCn reads the online redo log and creates an archived redo log at the archive destination.

### 9.3 Conditions for Group Reuse

In ARCHIVELOG mode, a group typically must:

- No longer be CURRENT.
- No longer be ACTIVE (checkpoint requirements satisfied).
- Have been successfully archived.

In NOARCHIVELOG mode, the archiving condition does not apply; the group still must no longer be needed for instance recovery before reuse.

### 9.4 Checking Archive Destinations

~~~sql
SELECT dest_id,
       status,
       destination,
       error,
       recovery_mode,
       synchronization_status
FROM v$archive_dest_status
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
~~~

Some columns may differ across releases/roles; if a view lacks a column in your version, check the corresponding Database Reference. Check ERROR and destination whenever archiving stalls.

### 9.5 Checking Archived Redo Logs

~~~sql
SELECT thread#,
       sequence#,
       first_time,
       completion_time,
       archived,
       deleted,
       status,
       name
FROM v$archived_log
ORDER BY thread#, sequence# DESC
FETCH FIRST 100 ROWS ONLY;
~~~

V$ARCHIVED_LOG can contain multiple rows for the same thread/sequence when logs are stored in multiple destinations or copied/restored. Do not assume each sequence has only one row.

## 10. Handling Failed or Missing Redo Log Members

Redo log members are copies of a group. If one member becomes inaccessible, Oracle can continue writing to the remaining member(s) of the group in many cases, though redundancy is degraded. Check the alert log, fix the storage/path issue, and restore the member promptly.

### 10.1 Identifying Failed Members

~~~sql
SELECT group#,
       member,
       status,
       type
FROM v$logfile
WHERE status IS NOT NULL
ORDER BY group#, member;
~~~

INVALID or STALE statuses must be investigated. A NULL/blank STATUS generally indicates a healthy member. Cross-check with the alert log for file open errors, I/O errors, permissions, or storage issues.

### 10.2 One Member Failed, Another Member Still Active

Overview procedure:

1. Identify the group and thread containing the failed member.
2. Verify the group still has a valid member and the database is still writing redo.
3. Determine the storage/path/permission root cause.
4. Add a new member to the same group in an independent storage location.
5. Check the new member's status and the alert log.
6. Once the new member is active, drop the failed member from the control file.
7. Re-verify member count and file paths.

Example:

~~~sql
ALTER DATABASE ADD LOGFILE MEMBER
    '/u04/oradata/ORCL/redo01c.log'
TO GROUP 1;

SELECT group#,
       member,
       status
FROM v$logfile
WHERE group# = 1;
~~~

Once the new member is valid and the group has enough working members:

~~~sql
ALTER DATABASE DROP LOGFILE MEMBER
    '/u02/oradata/ORCL/redo01a.log';
~~~

Filenames and group numbers in the example must be replaced with verified values from your environment. Do not drop a valid member if the group would be left with only one writable member or none.

### 10.3 If All Members of the CURRENT Group Are Lost

This is a critical incident because LGWR has nowhere left to write active redo. The database may hang or experience instance termination depending on the situation. Do not delete files, clear groups, or restart arbitrarily.

Do the following:

- Preserve the alert log and diagnose the storage failure.
- Determine whether any member can be recovered from a copy/storage snapshot.
- Execute recovery procedures per Oracle Support/your environment's DBA runbook.
- Assess potential redo loss and database consistency before reopening.

If the CURRENT group no longer has any valid redo copy, this becomes a recovery incident rather than a routine member-addition task.

### 10.4 New Member Shows INVALID or STALE Status

Do not assume a member is synchronized merely because ADD LOGFILE MEMBER succeeded. Check V$LOGFILE.STATUS, the alert log, and the log switch lifecycle. If the member is not initialized properly, fix the path/permissions or drop the failed member and re-add it using the proper procedure.

## 11. CLEAR LOGFILE and Recovery Warnings

ALTER DATABASE CLEAR LOGFILE is used in special situations when you need to reinitialize the contents of a redo log group, such as when a log is corrupted or unusable through normal procedures.

### 11.1 Basic Syntax

~~~sql
ALTER DATABASE CLEAR LOGFILE GROUP 4;
~~~

This command is not a standard way to free an ACTIVE group or force a log switch. Before clearing, determine whether the group is still needed for instance/media recovery and check its archive status.

### 11.2 CLEAR UNARCHIVED LOGFILE

In certain recovery scenarios, Oracle allows clearing an unarchived log:

~~~sql
ALTER DATABASE CLEAR UNARCHIVED LOGFILE GROUP 4;
~~~

This is a high-risk operation. When an unarchived log is cleared, redo needed for recovery may be lost. Existing backups may no longer be recoverable across the cleared redo; a new backup must be taken and the recovery strategy reviewed.

Do not use CLEAR UNARCHIVED as a quick workaround when ARCn is slow or the archive destination is full. Fix the archiving/checkpoint root cause first.

### 11.3 When Is Specialized Recovery Support Needed?

If a group is CURRENT, ACTIVE, or contains redo needed for crash/media recovery, Oracle may reject clear/drop operations. When logs are corrupted or lost, determine the database state, thread, sequence, archive status, and backup availability. Execute recovery strictly per documentation/Oracle Support rather than experimenting with multiple ALTER DATABASE commands.

## 12. Moving Redo Log Members

Do not move or rename redo log files solely by renaming files at the OS level while the database is using them. The control file stores member names/paths; database metadata must be updated.

### 12.1 Offline Procedure Using RENAME FILE

General procedure for a non-RAC database or an operation properly coordinated with RAC:

1. Plan a downtime window and identify all members to move.
2. Shut down the database cleanly per the runbook.
3. Copy the files from the old location to the new location at the storage layer.
4. Start up in MOUNT state, without OPENing the database.
5. Use ALTER DATABASE RENAME FILE to update the names in the control file.
6. Open the database and check V$LOGFILE.

Example:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;

ALTER DATABASE RENAME FILE
    '/u02/oradata/ORCL/redo01a.log'
TO  '/u05/oradata/ORCL/redo01a.log';

ALTER DATABASE OPEN;
~~~

The file must be completely copied to the new location before renaming metadata. In RAC, coordinate across instances/threads and follow the cluster runbook; do not run an offline command for a file and assume other instances are unaffected.

### 12.2 Moving by Adding a Member Then Dropping the Old Member

If the database has other working members and the architecture allows, you can:

1. ADD LOGFILE MEMBER on the new storage.
2. Verify the new member is valid.
3. DROP LOGFILE MEMBER for the old path.
4. Clean up the old file once the database no longer references it.

This approach can avoid downtime for some storage migrations, but verify group status and release/ASM operational rules. Never use it as a substitute for recovery when all members are lost.

## 13. Resizing Redo Log Groups

There is no in-place resize operation for an active online redo log group. The standard method is to create new groups at the desired size, shift workload onto them, and then drop the old groups once they become eligible.

### 13.1 The Add–Switch–Drop Procedure

Suppose old groups are 100 MB and you want to move to 1 GB:

~~~sql
ALTER DATABASE ADD LOGFILE GROUP 10
(
    '/u02/oradata/ORCL/redo10a.log',
    '/u03/oradata/ORCL/redo10b.log'
)
SIZE 1G;
~~~

Then:

1. Verify group 10 has sufficient members and capacity.
2. Perform log switches according to plan.
3. Monitor until the old groups become INACTIVE and archived (if ARCHIVELOG).
4. Drop each old group when eligible.
5. Verify all remaining groups have uniform size per thread and adequate redundancy.

Do not drop all old groups before ensuring the database has enough new groups to continue operating.

### 13.2 Why Should Groups in the Same Thread Have the Same Size?

If groups have different sizes, the intervals between log switches will be uneven and Oracle may cycle through smaller groups more frequently. Uniform sizing makes switch intervals and archive capacity easier to predict.

### 13.3 How Many Groups Are Enough?

Oracle requires a minimum of two groups per thread. Production environments typically need more to allow time for checkpoints and archiving to complete before a group is needed again. Three or more is a common starting point, though the right count depends on redo rate, archive throughput, checkpointing, and switch intervals.

If groups are consistently reused before checkpoint/archive finishes, adding more groups can reduce LGWR reuse waits. However, adding more groups will not fix a full archive destination or persistently slow storage I/O.

## 14. Choosing Redo Log Size

Group size affects log switch frequency and the amount of redo to archive per file.

### 14.1 Groups Too Small

Consequences may include:

- Log switches occur too frequently.
- ARCn must archive many small files.
- Checkpoints must process continuously.
- Wait events such as log file switch (checkpoint incomplete) or log file switch (archiving needed) may appear.
- Higher overhead for managing archive logs and backups.

### 14.2 Groups Too Large

Oversized groups also carry trade-offs:

- Larger archive log generated per switch.
- Archiving/backup/transport may require more time and space per file.
- When a switch is needed to create an archive point, more redo must be written first.
- May complicate retention/storage management without aligned policies.

There is no single right size for every database. Size according to peak-hour redo generation rate, desired switch interval, archive speed, and recovery capability.

### 14.3 Estimating Size from Redo Rate

You can use a starting formula:

\[
\text{Group size} \approx
\text{Peak redo bytes per second}
\times
\text{Target switch interval in seconds}
\]

For example, peak redo generation of about 8 MB/s and a target switch interval of about 15 minutes:

\[
8 \times 900 = 7,200\ \text{MB} \approx 7.2\ \text{GB}
\]

This is an initial estimate, not a mandatory configuration. Check archive throughput, storage, group count, and checkpoint duration. You may choose a smaller or larger size depending on operational targets.

### 14.4 Calculating Redo Generation Rate with V$SYSSTAT

The redo size statistic is the cumulative number of redo bytes generated at the instance scope:

~~~sql
SELECT name,
       value
FROM v$sysstat
WHERE name = 'redo size';
~~~

Take snapshots T0 and T1:

\[
\text{Redo rate} =
\frac{\text{redo size}_{T1}-\text{redo size}_{T0}}
{\text{seconds between snapshots}}
\]

In RAC, use GV$SYSSTAT and calculate per INST_ID. If summing across the cluster, add the deltas of each instance after confirming identical snapshot intervals.

### 14.5 Monitoring Actual Switch Intervals

~~~sql
SELECT thread#,
       COUNT(*) AS switches,
       MIN(first_time) AS first_switch_time,
       MAX(first_time) AS last_switch_time
FROM v$log_history
WHERE first_time >= SYSDATE - 1
GROUP BY thread#
ORDER BY thread#;
~~~

To view intervals between switches:

~~~sql
WITH history AS (
    SELECT thread#,
           sequence#,
           first_time,
           LAG(first_time) OVER (
               PARTITION BY thread#
               ORDER BY first_time
           ) AS previous_time
    FROM v$log_history
    WHERE first_time >= SYSDATE - 1
)
SELECT thread#,
       sequence#,
       first_time,
       ROUND((first_time - previous_time) * 1440, 2)
           AS minutes_since_previous
FROM history
WHERE previous_time IS NOT NULL
ORDER BY thread#, first_time;
~~~

Many systems use 15–30 minutes as an initial reference switch interval; this is not a hard limit or strict Oracle requirement. Measure against actual workload, redo rate, and archive/checkpoint capacity.

## 15. Diagnosing Log Switch Waits and LGWR

Redo-related wait events typically point to unavailable groups, slow archiving, or slow redo write I/O.

### 15.1 log file switch (checkpoint incomplete)

Sessions or LGWR wait because the next group cannot be reused yet; the checkpoint has not finished writing the required dirty buffers.

Investigation path:

- Check V$LOG to see if many groups remain ACTIVE.
- Inspect DBWR/checkpoint workload and datafile I/O.
- Check whether the number of groups is sufficient.
- Evaluate group size and redo rate.
- Inspect storage latency for datafiles.

Increasing group count or size can help if logs are cycling too fast, but it will not fix prolonged datafile I/O bottlenecks.

### 15.2 log file switch (archiving needed)

A group must be archived before reuse, but archiving has not completed.

Investigation path:

- Check LOG_MODE.
- Check V$ARCHIVE_DEST_STATUS.ERROR and destination.
- Verify whether the FRA/destination has sufficient free space.
- Check ARCn and archive write throughput.
- Check Data Guard transport if archiving/redo is blocked by related configuration.

Do not simply add more groups to mask a full archive destination error. Free/expand the destination or fix the archiving error.

### 15.3 log file switch completion

Sessions are waiting for a log switch to complete. Inspect group status, LGWR, checkpointing, and archiving to find why the switch has not finished.

### 15.4 log file parallel write

LGWR is waiting for I/O completion while writing redo log members. This may relate to storage latency, member count, I/O paths, or device contention.

If a group has multiple members on devices with different speeds, the group's write speed can be bottlenecked by the slowest member. Multiplexing should use storage with appropriate performance, not just different paths.

### 15.5 log file sync

Foreground sessions wait for LGWR to flush redo to complete a COMMIT. This represents commit latency, not necessarily a log switch wait. Investigate:

- log file parallel write.
- Redo log storage latency.
- Commit frequency and overly chatty application commits.
- Network/application behavior if clients respond slowly after commit.

Increasing redo log group size generally does not directly solve log file sync.

### 15.6 log buffer space

Sessions wait because there is not enough space in the redo log buffer to write new redo. This can happen when redo generation exceeds LGWR's rate of flushing the buffer or when there is a redo write bottleneck. Inspect redo rate, LGWR I/O, and related waits; do not blindly increase LOG_BUFFER without measuring the root cause.

### 15.7 Viewing Instance-Level Wait Events

~~~sql
SELECT event,
       total_waits,
       ROUND(time_waited_micro / 1000000, 2) AS total_wait_seconds,
       ROUND(average_wait, 3) AS average_wait_centiseconds
FROM v$system_event
WHERE event IN (
    'log file switch (checkpoint incomplete)',
    'log file switch (archiving needed)',
    'log file switch completion',
    'log file parallel write',
    'log file sync',
    'log buffer space'
)
ORDER BY time_waited_micro DESC;
~~~

Values in V$SYSTEM_EVENT are cumulative since instance startup. To evaluate a time window, take two snapshots and compute the delta. In RAC, use GV$SYSTEM_EVENT and preserve INST_ID.

### 15.8 Viewing Session Waits

~~~sql
SELECT sid,
       event,
       total_waits,
       time_waited_micro,
       average_wait
FROM v$session_event
WHERE event LIKE 'log file%'
   OR event = 'log buffer space'
ORDER BY time_waited_micro DESC;
~~~

V$SESSION_EVENT is also cumulative per session. For long-lived sessions, total waits may be large without indicating a current problem. Combine with V$SESSION.EVENT/STATE and snapshot deltas.

## 16. RAC: Redo Threads and Log Groups

In Oracle RAC, each instance typically has its own redo thread. Each thread has its own online redo log groups, all belonging to the same database.

### 16.1 Threads and Instances

V$THREAD displays:

- THREAD#: redo thread identifier.
- STATUS/ENABLED: thread status.
- INSTANCE: associated instance.
- GROUPS: number of groups in the thread.
- CURRENT_GROUP#: current active group.

In RAC, do not look only at the total group count across the database. Ensure each thread has enough groups, the right size, and sufficient members.

### 16.2 Viewing Groups by Thread

~~~sql
SELECT thread#,
       group#,
       sequence#,
       bytes,
       members,
       archived,
       status
FROM gv$log
ORDER BY thread#, group#;
~~~

### 16.3 Adding a Group to a Thread

~~~sql
ALTER DATABASE ADD LOGFILE THREAD 2 GROUP 12
(
    '+DATA/ORCL/ONLINELOG/redo_t2_g12a.log',
    '+FRA/ORCL/ONLINELOG/redo_t2_g12b.log'
)
SIZE 1G;
~~~

ASM names are illustrative only. In RAC, coordinate with DBA/storage teams to ensure members reside in proper failure groups and the group is assigned to the correct thread.

### 16.4 Log Switches in RAC

ALTER SYSTEM SWITCH LOGFILE affects the redo thread of the instance executing the command. If you need to switch another instance's thread, connect to that instance or use an approved cluster procedure. Do not assume running the command on one instance switches all threads.

### 16.5 GV$ and INST_ID

When querying cluster-wide, use GV$LOG, GV$LOGFILE, GV$THREAD, GV$SYSTEM_EVENT, and retain INST_ID. While group numbers are unique across the database, thread/instance states should still be evaluated together.

## 17. Data Guard and Standby Redo Logs

Standby redo logs (SRLs) are typically used on physical standby databases to receive redo from the primary and support real-time apply. They are distinct from the primary's online redo log groups.

In V$LOGFILE, TYPE can be ONLINE or STANDBY. Do not confuse SRLs with the online redo logs of a thread serving user workloads.

Key notes:

- Standby requires an SRL count and size matching the primary's online redo logs and number of redo threads.
- SRLs are used by the redo receiving mechanism, not where the primary's LGWR writes normal online redo.
- Data Guard transport/apply lag can affect archive/log reuse and recovery operations; monitor destination status and broker/standby metrics.
- Changes to redo configuration in Data Guard must be coordinated across primary and standby following role-specific procedures.

## 18. Backup and Recovery When Modifying Redo Logs

Redo logs are an essential component of recovery. Before dropping, clearing, renaming, or changing configuration, know which redo is still needed for instance recovery, media recovery, backups, and standby.

### 18.1 After Adding or Dropping Groups

Verify:

- The database has enough groups per thread.
- Members are accessible.
- Group sizes and member counts are consistent.
- Archive destinations are working.
- Data Guard (if present) continues receiving/applying redo.
- The alert log has no LGWR/ARCn errors.

### 18.2 After CLEAR UNARCHIVED LOGFILE

If you cleared an unarchived log, reassess recoverability from existing backups. Take a new database backup according to recovery policy and document the event and affected sequences.

### 18.3 Do Not Delete Redo Files via OS While Control File Still References Them

Deleting physical files before dropping/renaming metadata can prevent the database from opening or cause LGWR errors when needing the group. Always update database metadata via SQL using proper procedures before cleaning up files.

### 18.4 Preserve Alert Logs

The alert log records log switches, archive errors, member I/O errors, group clearing, and many recovery events. During an incident, inspect the alert log alongside timestamps from V$LOG/V$LOGFILE/V$ARCHIVED_LOG to reconstruct the timeline.

## 19. Common Errors

| Error/Scenario | Common Cause | Resolution Path |
|---|---|---|
| ORA-00313 / ORA-00312 | Unable to open/read/write redo log member | Check path, permissions, storage, and alert log |
| ORA-00308 | Unable to open archived log | Check archive destination, file existence, and permissions |
| ORA-00257 | Archiver error, typically full archive destination/FRA or archive failure | Fix destination/ARCn; do not just keep switching logs |
| ORA-01624 | Log needed for crash recovery, cannot drop/clear yet | Wait for/complete recovery/checkpoint per procedure |
| ORA-01623 | Cannot drop log group that is CURRENT | Switch to another group first |
| ORA-01624 or group still ACTIVE | Redo still needed for instance recovery | Wait for checkpoint or investigate I/O/checkpointing |
| Frequent log switches | Groups too small or redo rate increased | Measure redo rate and increase size/group count appropriately |
| log file switch (checkpoint incomplete) | Checkpoint has not freed the next group | Check DBWR/datafile I/O, group count, and size |
| log file switch (archiving needed) | Archiving has not completed | Check ARCn, FRA/destination, and Data Guard |
| Member INVALID/STALE | Missing file, I/O error, or out of sync | Restore/add member, verify status, then drop failed member |
| Group has only one member | Insufficient multiplexing redundancy | Add member on an independent failure domain |
| Inconsistent group sizes | Configuration migration incomplete | Add new groups of uniform size, switch, and drop old groups |

Exact error codes and conditions depend on database state and release. Read the full error stack and alert log; do not act on a single truncated error code alone.

## 20. Redo Log Operations Checklist

Before changing redo logs:

1. Have you confirmed ARCHIVELOG/NOARCHIVELOG mode?
2. Have you reviewed all groups, threads, sequences, sizes, and statuses in V$LOG?
3. Have you reviewed all members and statuses in V$LOGFILE?
4. Are members placed on independent failure domains?
5. Does each thread have enough groups for log switching, checkpointing, and archiving?
6. Are group sizes uniform within each thread?
7. Have you checked archive destinations, FRA, and ARCn?
8. Have you confirmed any group to be dropped is not CURRENT, not ACTIVE, and archived if required?
9. Have you checked Data Guard/SRLs if the database has a standby?
10. Have you assessed the backup/recovery impact of CLEAR or CLEAR UNARCHIVED?
11. Have you kept physical files intact until the control file no longer references them?
12. Have you reviewed the alert log after the operation?

When investigating log switches:

1. Have you calculated switch intervals per thread?
2. Have you measured redo generation rate via redo size deltas?
3. Are there checkpoint incomplete or archiving needed waits?
4. Is LGWR waiting on log file parallel write?
5. Are foreground sessions waiting on log file sync?
6. Does any archive destination show ERROR or lack free space?
7. Is the next group INACTIVE and properly ARCHIVED?
8. Are group count and size aligned with peak workload?

## 21. Summary

Online redo logs are the foundation for instance recovery and media recovery. Oracle organizes them into groups; each group has one or more members containing identical redo. LGWR writes to the CURRENT group, while older groups transition through ACTIVE/INACTIVE depending on checkpoint and archive conditions.

- Multiplex members across independent storage failure domains to protect against single-file/device failures.
- Monitor groups with V$LOG, members with V$LOGFILE, and threads with V$THREAD.
- In ARCHIVELOG mode, a group must be archived before reuse; checkpoints must also release redo from instance recovery needs.
- Log switches occur automatically when a group fills; ALTER SYSTEM SWITCH LOGFILE requests a manual switch for the current thread, while ARCHIVE LOG CURRENT requests archiving the current log.
- Groups/members can be added via SQL DDL; drop a group only when it is neither CURRENT nor ACTIVE and satisfies archive/recovery requirements.
- Do not resize groups in place; use add–switch–drop to transition to a new size.
- CLEAR LOGFILE, and especially CLEAR UNARCHIVED LOGFILE, are high-risk recovery operations, not routine switch troubleshooting tools.
- In RAC, each instance has its own redo thread; track thread/INST_ID when inspecting and acting.
- Distinguish online redo logs from standby redo logs in Data Guard.
- Measure redo rate and switch intervals against actual workloads; diagnose checkpoint waits, archive waits, LGWR I/O, and commit waits separately.

Effective redo log management means maintaining adequate groups and members, placing them on appropriate storage, keeping archiving and checkpoints progressing smoothly, and verifying recovery before any destructive change.

## 22. Oracle Reference Documentation

- Oracle Database 19c Administrator's Guide, “Managing the Redo Log”: https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-the-redo-log.html
- Oracle Database 19c Administrator's Guide, “Multiplexing the Redo Log”: https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-the-redo-log.html#GUID-7F4D4A6B-2A0A-4D3E-8C1E-6E8C8B6A9C3A
- Oracle Database 19c Database Reference, “V$LOG”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOG.html
- Oracle Database 19c Database Reference, “V$LOGFILE”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOGFILE.html
- Oracle Database 19c Database Reference, “V$LOG_HISTORY”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOG_HISTORY.html
- Oracle Database 19c Database Reference, “V$THREAD”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-THREAD.html
- Oracle Database 19c Database Reference, “V$ARCHIVED_LOG”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-ARCHIVED_LOG.html
- Oracle Database 19c Database Reference, “V$ARCHIVE_DEST_STATUS”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-ARCHIVE_DEST_STATUS.html
- Oracle Database 19c Database Reference, “V$SYSTEM_EVENT”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SYSTEM_EVENT.html
- Oracle Database 19c Data Guard Concepts and Administration, “Managing Standby Redo Logs”: https://docs.oracle.com/en/database/oracle/oracle-database/19/sbydb/managing-oracle-data-guard-physical-standby-databases.html
