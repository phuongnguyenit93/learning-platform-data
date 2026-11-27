# Datafiles, Control Files, Online Redo Logs, and Archived Redo Logs in Oracle Database

Oracle Database does not store all information in a single file. Table and index data is organized in **datafiles**; database identification and physical structure information resides in **control files**; changes needed for recovery are written to **online redo logs**; and when redo archiving is enabled, completed redo logs are preserved as **archived redo logs**. These four components work together so Oracle can both process transactions quickly and recover a consistent state after failures.

In this lesson under **Oracle Database Architecture**, we trace the path of a transaction, understand each file type both during normal operation and when failures occur, and use read-only queries to inspect files on a real Oracle system.

After studying this lesson, you will be able to:

- Distinguish where persistent data, structural metadata, and recovery information are stored.
- Explain the relationships between **tablespace and datafile**, **redo log group and member**, and **online redo and archived redo**.
- Describe the roles of **DBWR, LGWR, CKPT, and ARCn** in data writing, commits, checkpoints, log switches, and archiving.
- Distinguish **instance/crash recovery** from **media recovery**, understanding why backups and required redo are essential.
- Read `V$DATAFILE`, `V$CONTROLFILE`, `V$LOG`, `V$LOGFILE`, `V$DATABASE`, and `V$ARCHIVED_LOG`.
- Recognize risky configurations, such as missing control file copies, having only a single redo member, or a full archived log destination.

> The illustrated commands are primarily **read-only queries**. Operations such as switching `ARCHIVELOG` mode, switching log groups, or modifying file configurations have real operational impact and should only be performed on a **private lab database with administrative privileges** after understanding the consequences. Examples use general terminology for modern Oracle; paths, tablespace names, and log group counts may vary by version/installation.

## 1. Architectural Picture: Where Are Data and Recoverability Stored?

Imagine a user executes:

`UPDATE accounts SET balance = balance - 100 WHERE account_id = 10;`

and then `COMMIT`. Oracle must ensure a committed transaction can be recovered after a process or host failure, even if the changes to the data blocks have not yet been written by DBWR down to a datafile.

~~~text
                           ORACLE INSTANCE
                    +----------------------------+
SQL UPDATE/COMMIT ->| Database Buffer Cache      |
                    |   (data blocks)            |
                    |                            |
                    | Redo Log Buffer            |
                    |   (redo change records)    |
                    +---------------+------------+
                                    |
                    +---------------+-------------------+
                    |                                   |
                    v                                   v
                 DBWR                                LGWR
                    |                                   |
                    v                                   v
             +-------------+                  +--------------------+
             | DATAFILES   |                  | ONLINE REDO LOGS   |
             | data        |                  | group 1, 2, 3...   |
             +-------------+                  +----------+---------+
                                                         |
                                                log switch / ARCn
                                                         |
                                                         v
                                              +--------------------+
                                              | ARCHIVED REDO LOGS |
                                              | retained redo      |
                                              | history (ARCHIVELOG)|
                                              +--------------------+

   CONTROL FILE: database identity, list of datafiles/redo,
   checkpoints, and metadata needed to mount, manage, and recover.
~~~

**Key takeaway:** `COMMIT` does not require Oracle to immediately write every modified block down to a datafile. **Write-ahead logging** lets Oracle write recovery redo first; DBWR can write modified blocks to datafiles afterward. Therefore **redo is not a copy of a datafile** and **a datafile is not a transaction log**.

### 1.1. Comparison Table of the Four File Types

| Component | Primary Contents | When Written/Updated? | Role During Failure |
| --- | --- | --- | --- |
| **Datafile** | Tablespace data blocks, including tables, indexes, undo segments, and relevant storage metadata | DBWR writes dirty buffers and various file admin operations | Where data blocks are recovered; lost/corrupted files usually require restoring from backup |
| **Control file** | Database identity, names/locations of datafiles and redo logs, checkpoint info, log sequences, and admin/recovery metadata | Database updates when structure, checkpoints, or redo state change | Required to mount the database and orchestrate recovery |
| **Online redo log** | Redo records describing changes so they can be reapplied during recovery | LGWR writes continuously, cycling across groups | Used for **instance recovery**; may hold newest unarchived redo |
| **Archived redo log** | Saved copy of a **completed online redo log group**, tracked by log sequence | ARCn archives after a log switch in `ARCHIVELOG` mode | Supplies redo history for **media recovery**, point-in-time recovery, and standby replicas |

In Oracle, all four are **physical components** of the database environment, yet their purposes are completely different. Tablespace, schema, and segment are **logical** concepts; SGA and background processes belong to the **instance**, not to data files.

## 2. Datafile: Where Data Blocks Are Persistently Stored

### 2.1. Relationship Between Tablespace and Datafile

Oracle organizes storage across multiple layers:

~~~text
Database (or PDB)
  |
  +-- Tablespace USERS
  |     +-- Datafile users01.dbf
  |     +-- Datafile users02.dbf
  |          +-- Segment: table ACCOUNTS
  |          +-- Segment: index ACCOUNTS_PK
  |
  +-- Tablespace SYSTEM
  |     +-- Datafile system01.dbf
  |
  +-- Tablespace UNDOTBS1
        +-- Datafile undotbs01.dbf
~~~

A **tablespace** is a logical storage unit. A permanent or undo tablespace has **one or more datafiles**; a single datafile belongs to **one tablespace** at a time. Inside a tablespace, objects use segments; segments consist of extents; extents consist of data blocks.

For example:

- `SYSTEM` and `SYSAUX` contain much of Oracle's internal metadata.
- `USERS` is commonly used for application or practice objects, depending on configuration.
- Undo tablespaces hold **undo segments** used for rollback and read consistency; undo blocks still reside in **datafiles**, and redo also records changes needed for undo.
- **Temporary** tablespaces use **tempfiles** to store temporary data for large sort/hash/work areas. Tempfiles differ from regular datafiles and have different recovery handling; do not assume every file ending in `.dbf` is a datafile.

**File extensions are only a convention.** Oracle can manage files via Oracle Managed Files (OMF), ASM, or filesystem paths. Files do not have to end in `.dbf`, and you should not guess a file's role solely from its path.

### 2.2. What Happens When a Statement Modifies Data?

When a session updates a row, Oracle typically:

1. Finds or loads the target block into the SGA's **database buffer cache**.
2. Modifies the in-memory copy of the block and generates appropriate undo information.
3. Generates **redo records** describing the changes needed to reconstruct them.
4. LGWR writes redo according to flush conditions, where **COMMIT** requires the transaction's redo to be durable under standard commit semantics.
5. **DBWR** writes modified blocks (*dirty buffers*) down to datafiles based on cache demand, checkpoints, and other conditions—potentially **after COMMIT time**.

This explains why a datafile may not yet contain the latest image of every block while committed transactions are still protected by redo. On startup after an instance crash, Oracle can read the required redo to recover.

### 2.3. Datafile Headers and Checkpoints

Datafiles contain metadata in their headers, including identification and status used for consistency and recovery. Oracle also stores related checkpoint information in the control file.

A **checkpoint** marks progress so the database can determine the scope of redo needed during instance recovery. The **CKPT** process coordinates or signals checkpoints and updates checkpoint metadata where required; **DBWR** is the process that primarily writes dirty buffers down to datafiles. Do not mistakenly think CKPT writes all table data itself or that every commit must wait for a checkpoint.

### 2.4. Inspecting Datafiles on a System

With an account granted read access to dynamic performance views (in an administrative practice lab, `SYSDBA` may be used), run:

~~~sql
SELECT file#, name, status,
       ROUND(bytes / 1024 / 1024) AS size_mb
FROM v$datafile
ORDER BY file#;

SELECT file#, name, status,
       ROUND(bytes / 1024 / 1024) AS size_mb
FROM v$tempfile
ORDER BY file#;
~~~

The two queries intentionally separate **datafiles** from **tempfiles**. In a CDB, information in some `V$` views may span multiple containers; when scoping to a PDB, also check session context or the `CON_ID` column where supported. Paths may be filesystem paths, ASM paths (e.g., `+DATA/...`), or OMF-managed names.

## 3. Control File: Structural Map and State of the Database

### 3.1. What Does a Control File Contain?

A **control file** is a critical binary file Oracle needs to identify and **mount** the database. Typical contents include:

- **DB_NAME, DBID**, and database identification details.
- List, names, and locations of **datafiles**.
- List of **online redo log groups/members** and related redo info.
- **Checkpoint** info, redo log sequences, log history, and archived redo log info.
- Backup/recovery metadata stored by the control file in reusable record sections per retention policy.
- Information supporting structural changes and recovery, such as relevant `RESETLOGS`/incarnation history.

Do not confuse the control file with:

| File/Component | How It Differs from the Control File |
| --- | --- |
| `spfile` / `pfile` | Stores **instance initialization parameters**, such as memory settings or `CONTROL_FILES`; does not replace the control file |
| Data dictionary | Logical metadata about tables, columns, users, privileges, etc., stored inside system datafiles, not the entire control file |
| RMAN recovery catalog | Optional external backup metadata repository outside the target database; not a simple copy of the control file |
| Datafile | Stores block data; the control file only holds the map and state needed to manage those files |

### 3.2. Role Across Startup Stages

~~~text
STARTUP
   |
   +--> NOMOUNT
   |      Read SPFILE/PFILE, create SGA and background processes.
   |
   +--> MOUNT
   |      Read control file, identify database,
   |      datafiles, and online redo log files.
   |
   +--> OPEN
          Open and verify required files;
          perform instance recovery if needed;
          allow appropriate database access.
~~~

In the CDB/PDB model, **OPENing the CDB** does not automatically guarantee every PDB is in `READ WRITE` mode. When practicing queries inside a PDB, verify you are in the right container.

If Oracle cannot access **any valid control file copy**, the database cannot mount normally. By contrast, if a single datafile of an application tablespace is lost, depending on damage scope and operating mode, file/tablespace recovery procedures can be performed rather than recovering the entire database.

### 3.3. Multiplexing the Control File

An operational best practice is to maintain **multiple synchronized control file copies managed by Oracle** across storage locations with separate failure domains:

~~~text
CONTROL_FILES
    |
    +-- /disk_a/oradata/DB/control01.ctl
    +-- /disk_b/oradata/DB/control02.ctl
~~~

Oracle writes management metadata to all configured control file copies. This is **multiplexing**, not creating separate independent control files per PDB. Placing both files on the same physical disk does not provide the same disk failure tolerance as two separate devices.

The `CONTROL_FILES` parameter specifies the list of files used:

~~~sql
SHOW PARAMETER control_files;

SELECT name, status
FROM v$controlfile;
~~~

`SHOW PARAMETER` is an SQL*Plus command; querying `V$CONTROLFILE` uses SQL. Changing the control file list requires an operational procedure suited to the live environment and typically an instance restart; do not modify `CONTROL_FILES` casually in an active lab session serving transactions.

**Multiplexing does not replace backups.** Logical errors, losing an entire storage subsystem, misconfiguration, or corruption affecting both copies can still lose metadata needed for recovery. RMAN control file autobackup or an appropriate backup policy protects recoverability; if all control files are lost, restore/recreate and incarnation handling require DBA control.

## 4. Online Redo Log: Circular Recovery Journal

### 4.1. What Do Redo Records Store?

**Redo** is sufficient information for Oracle to reapply required changes during recovery. It describes changes to database structures in an internal redo format—**not a full copy of data rows in SQL form** or a list of the user's original `INSERT/UPDATE` statements.

An uncommitted transaction can also generate redo, and that redo may already be written to disk. During recovery, Oracle can use redo to roll forward changes and then resolve uncommitted transactions using undo to ensure consistency. Thus:

- **Redo** answers: "Which changes need to be reapplied after a failure?"
- **Undo** enables rolling back incomplete transactions and provides historical data needed for read consistency.
- **Commit** does not mean datafiles were written immediately; the transaction's redo has been durably written under standard commit semantics.

### 4.2. Groups, Members, and Circular Writing

Online redo logs are organized into **groups**. Each group has **one or more members**; members within the same group hold the exact same redo stream. `LGWR` writes sequentially to the **current group** (*CURRENT*), then advances to the next group upon a log switch.

~~~text
                        LGWR
                          |
           +--------------+--------------+
           |                             |
           v                             v
    REDO GROUP 1                   REDO GROUP 2
    member 1a                      member 2a
    member 1b                      member 2b
         ^                              |
         |                              v
         +----------- REDO GROUP 3 -----+
                     member 3a
                     member 3b
~~~

The diagram only illustrates group rotation, not three groups being written simultaneously. Within one group, **members are concurrent mirrors**. When a group fills or a log switch is issued, Oracle moves to the next group if that group is eligible for reuse.

**Two easily confused concepts:**

1. **Multiple groups** give LGWR room to rotate and allow archiving/checkpoints to keep up.
2. **Multiple members in one group** create redundant copies for that specific group, reducing risk if one redo member or storage device fails.

Having more members **does not increase the historical time span of redo retained in a group**: all members of a group hold the same redo, rather than extending sequentially.

A normally operating database requires at least two online redo log groups; group size and count are chosen based on redo volume, archive speed, recovery objectives, and infrastructure. In RAC systems, there is also the **redo thread** concept bound to each instance; do not assume every database has only a single redo thread.

### 4.3. LGWR and the Write-Ahead Logging Principle

Abbreviated process:

~~~text
UPDATE on block in buffer cache
        |
        +--> Generate redo into redo log buffer
        |
       COMMIT
        |
        v
LGWR flushes required redo to online redo log
        |
        v
Commit confirmed under default durability mechanism
        |
        v
DBWR can write dirty data block to datafile afterward
~~~

LGWR can write redo for other reasons besides commit, such as buffer/log pressure, periodic triggers, or log switches; Oracle also uses **group commit** to optimize multiple transactions. Certain commit options can alter confirmation timing and durability semantics; this lesson describes the standard commit mechanism.

If an Oracle instance stops abruptly **after a commit was durably recorded yet before DBWR updated the datafile**, redo allows instance recovery to bring the datafile to a consistent state.

### 4.4. Log Group States and Log Switches

Common statuses in `V$LOG`:

| Status | Primary Meaning |
| --- | --- |
| `CURRENT` | Group currently being written by LGWR for the corresponding redo thread |
| `ACTIVE` | Group is no longer current yet may still be needed for instance recovery; not yet eligible for reuse |
| `INACTIVE` | Group is no longer needed for instance recovery; may be reused if other conditions, such as archiving, are met |
| `UNUSED` | Group has never been written to since creation or in its current state context |
| `CLEARING` / `CLEARING_CURRENT` | Special state while the database is clearing a log; not part of the normal cycle for every group |

In `ARCHIVELOG` mode, a group must be **archived before being overwritten**; an `ACTIVE` group also cannot be reused yet. Hence a database may pause even with multiple groups if checkpoints or the archiver fall behind.

Illustrative timeline example:

~~~text
T1:  group 1 = CURRENT
T2:  group 1 full, log switch -> group 2 = CURRENT
T3:  ARCn archives group 1 (if ARCHIVELOG)
T4:  group 1 no longer needed for instance recovery -> INACTIVE
T5:  after other groups, LGWR can reuse group 1
~~~

Actual checkpoint and archiving order can interleave; do not assume that immediately after a log switch, the old group instantly becomes `INACTIVE` or finishes archiving.

### 4.5. Observing Online Redo Logs

~~~sql
SELECT group#, thread#, sequence#,
       ROUND(bytes / 1024 / 1024) AS size_mb,
       members, archived, status
FROM v$log
ORDER BY thread#, group#;

SELECT group#, member, status
FROM v$logfile
WHERE type = 'ONLINE'
ORDER BY group#, member;
~~~

Column meanings:

- `GROUP#`: online redo log group number.
- `THREAD#`: redo thread, important in RAC.
- `SEQUENCE#`: sequence number of the redo log within its thread/incarnation.
- `MEMBERS`: number of members in the group.
- `ARCHIVED`: indicates whether the group's redo has been archived in the context of the view.
- `STATUS` in `V$LOG`: **group** status; `STATUS` in `V$LOGFILE`: **member** status—two different pieces of information.

If the same `GROUP#` appears on two rows in `V$LOGFILE` with two member paths, that is **multiplexing of one group**. Never delete member files directly at the OS level to "free up space"; structural redo log changes must go through supported database procedures.

## 5. Archived Redo Log: Retaining Change History After Log Switches

### 5.1. Why Are Online Redo Logs Not Enough?

Online redo logs have a **finite number of groups** and are **overwritten in rotation**. If a datafile is damaged and must be restored from an older backup, the needed redo may have been overwritten long ago. To recover from backup time up to a recent point in time, completed redo history must be saved outside the online log cycle.

That is the role of **archived redo logs**. When the database is in `ARCHIVELOG` mode, the **ARCn** (archiver) background process writes a copy of completed online redo log groups to configured destinations before the group is reused.

~~~text
REDO GROUP 1 (sequence 100)  -- log switch --> REDO GROUP 2 (seq 101)
              |
              +-- ARCn archives sequence 100
                         |
                         v
                   archived redo log
                   thread 1 / sequence 100

REDO GROUP 2 (sequence 101)  -- log switch --> REDO GROUP 3 (seq 102)
              |
              +-- ARCn archives sequence 101
                         |
                         v
                   archived redo log
                   thread 1 / sequence 101
~~~

An archived redo log is a **saved copy of already-generated redo**, not a copy of all tables or the database, and not a standalone backup of datafiles. Each archive carries metadata such as thread, sequence, and `RESETLOGS`/incarnation info so Oracle can determine the exact application order during recovery.

### 5.2. `ARCHIVELOG` vs. `NOARCHIVELOG` Mode

| Criterion | `ARCHIVELOG` | `NOARCHIVELOG` |
| --- | --- | --- |
| Online redo groups | Still exist and are used by LGWR | Still exist and are used by LGWR |
| Retains redo after group completes | Archived per configuration | Does not archive redo history in the standard way |
| Instance recovery after crash when files remain intact | Can use required online redo | Can use required online redo |
| Media recovery from an older backup to a later point | Possible if backup and **all required redo** remain intact | Severely limited because overwritten redo is not retained |
| Online/hot backups under standard RMAN strategy | Supported when backup requirements are met | Cannot rely on the same online backup strategy to guarantee consistency |
| Archive space management need | Must monitor and back up/purge per retention | Does not generate archived redo in the same manner |

**Enabling `ARCHIVELOG` does not automatically create good backups.** For full recoverability, you still need reliable datafile/control file backups, contiguous archived redo logs covering the recovery window, current online redo if available, and tested restore/recover procedures.

### 5.3. Archive Storage Locations and Fast Recovery Area

Archived redo logs can be written to declared archive destinations, commonly the **Fast Recovery Area (FRA)**. The FRA is an Oracle-managed storage area for recovery artifacts such as archived redo logs, RMAN backup pieces, control file autobackups, and other recovery components depending on configuration.

Useful parameters to inspect:

- `DB_RECOVERY_FILE_DEST`: FRA location.
- `DB_RECOVERY_FILE_DEST_SIZE`: FRA capacity limit.
- `LOG_ARCHIVE_DEST_n`: configured archive destinations and attributes.

~~~sql
SHOW PARAMETER db_recovery_file_dest;
SHOW PARAMETER db_recovery_file_dest_size;
SHOW PARAMETER log_archive_dest;
~~~

If the FRA or an archive destination fills up, **ARCn may be unable to archive completed logs**. When online groups cannot be reused because they remain unarchived, transactions can stall and archiver errors such as `ORA-00257` appear. This is an archive space/pipeline error, not proof that datafiles are full.

Do not delete archives arbitrarily using a file manager. Oracle/RMAN tracks which copies have been backed up, are still needed for recovery or Data Guard standbys, and retention/deletion policies. Deletion must be governed by backup/restore status, recoverability, and organizational policy; **nor does the FRA replace a safe backup on independent storage**.

### 5.4. Observing Mode and Archived Redo Log History

~~~sql
SELECT name, log_mode, open_mode
FROM v$database;

SELECT thread#, sequence#, name,
       first_time, next_time, completion_time
FROM v$archived_log
WHERE name IS NOT NULL
ORDER BY completion_time DESC
FETCH FIRST 20 ROWS ONLY;
~~~

`LOG_MODE` indicates `ARCHIVELOG` or `NOARCHIVELOG`. `V$ARCHIVED_LOG` is metadata about archive/log copies recorded in the control file; **a single sequence can appear on multiple rows** due to multiple destinations/copies or operational history. Do not use row counts in this view to infer redo group counts or datafile copy counts.

If the database is in `NOARCHIVELOG`, the second query may contain no ordinary archived logs. If archives were backed up and deleted from disk, metadata rows may still persist for some time; a populated `NAME` field or metadata row **does not prove the file is still readable on disk**. Verifying backup/archive usability belongs to RMAN procedures.

## 6. Background Processes Coordinating with the Four File Types

| Component | Primary Job | Misconception to Avoid |
| --- | --- | --- |
| **DBWR** | Writes dirty data blocks in buffer cache down to **datafiles** | Not the process writing online redo |
| **LGWR** | Writes redo from redo log buffer down to **online redo logs** | Does not write table copies directly to datafiles on every commit |
| **CKPT** | Coordinates/signals checkpoints and updates checkpoint metadata | Does not write all data blocks itself instead of DBWR |
| **ARCn** | Archives completed redo groups when the database is in `ARCHIVELOG` | Cannot recreate lost data if backups/redo are missing |
| **LREG** | Registers instance/service info with the listener (network role) | Not part of the datafile/redo write chain in this diagram |

In particular, **checkpoint** and **log switch** are two distinct concepts:

- **Checkpoint:** write/synchronization progress to bound redo needed for instance recovery; involves DBWR/CKPT, file headers, and the control file.
- **Log switch:** LGWR switching to another online redo group; the old group may be archived in `ARCHIVELOG` mode.

A log switch can trigger checkpoint activity, yet **it does not mean every dirty buffer was flushed before the switch**, nor does it mean archived redo completes instantaneously.

## 7. Four Failure Scenarios Showing Why Each File Type Is Needed

### 7.1. Scenario A — Instance Stops Abruptly, Datafiles and Redo Remain Intact

Suppose a money transfer transaction executed `COMMIT` and LGWR flushed its redo, yet DBWR had not written all modified blocks to datafiles when the host lost power.

~~~text
Before crash:
  Datafile A: block in older state
  Online redo: redo of UPDATE + COMMIT saved

After restart:
  Oracle reads control file / datafile headers
  -> identifies required redo
  -> rolls forward changes
  -> resolves uncommitted transactions (undo)
  -> database is consistent
~~~

This is **instance recovery (crash recovery)**. When physical files remain intact and redo is sufficient, Oracle generally handles it automatically while opening the database. There is no need to restore every datafile from backup just because an instance process crashed.

### 7.2. Scenario B — A Datafile Is Lost or Corrupted

Suppose `users01.dbf` is lost due to a storage failure. Online redo and control files may still exist, yet Oracle **cannot reconstruct every block solely from recent redo** without a suitable data baseline.

~~~text
Datafile backup at time T0
          |
          | archived redo sequence N, N+1, N+2, ...
          |
Required online redo (if any)
          v
Restore datafile from backup
       + apply continuous redo
          v
Recover to permitted time / SCN
~~~

This is **media recovery**: typically you must **restore** the datafile backup first and then **recover** using appropriate redo. If a mandatory archived redo log is missing, recovering to the desired point in time may no longer be possible. Having `ARCHIVELOG` enabled without keeping complete archives, backups, or critical files still does not guarantee successful recovery.

### 7.3. Scenario C — Loss of Control File

If one control file copy in a multiplexed setup fails, the system may encounter read/write errors and require DBA intervention. If **all control file copies are lost**, Oracle lacks the structural metadata needed to mount normally. Restoring the control file from backup and performing recovery (potentially involving `RESETLOGS` depending on scenario) is a different procedure from restoring a single datafile.

**Never create an empty file named `control01.ctl`**: control files have a binary format and consistent metadata and cannot be replaced with a text file or an empty file.

### 7.4. Scenario D — Loss of One Online Redo Group Member

If a group has two redo members on two disks, losing one member may leave the other member usable depending on circumstances. If a group has only one member and that member fails, impact depends on whether it was current/active, archived or unarchived, and what backups/redo exist. Losing the **current online redo** can be especially severe because it holds the newest unarchived redo.

Therefore **multiplexing redo members** improves fault tolerance for the active log group; **archiving** preserves completed redo history; the two mechanisms mitigate different risks.

## 8. Distinguishing Backups, Redo, Undo, and Flashback Logs

| Concept | Function | Can It Replace a Datafile Backup? |
| --- | --- | --- |
| Datafile | Current physical data foundation | Not a backup if sitting on the same failing system |
| RMAN backup | Saved copies of datafiles/control files/archived logs per backup policy | Serves as the **restore** source when originals are lost or damaged |
| Online redo | Near-current redo in a circularly reused log | No |
| Archived redo | Historical redo applied during recovery | No; requires an underlying datafile baseline/backup |
| Undo data | Data needed for rollback/read consistency | No |
| Flashback log | Supports Flashback Database features when configured | Does not replace a complete backup/archived redo strategy |

Concrete example: **today's archived redo is not a copy of today's database**. To recover a host that lost all datafiles, you must have valid backups/snapshots plus the required redo. Similarly, having only an RMAN backup from three days ago without continuous redo generally prevents bringing the database up to just before the failure using that backup alone.

## 9. Hands-On Practice: Inspecting the Four File Types

The steps below do not alter database configuration. You need an available Oracle instance and an account with privileges on dynamic performance views. `V$` views are usually not granted by default to application schemas; if you only have a regular practice user, ask a DBA for the output or appropriate read grants. **Do not grant `SYSDBA` to an application just to run these queries.**

### Step 1 — Identify the Database and Log Mode

~~~sql
SELECT name, dbid, open_mode, log_mode
FROM v$database;

SELECT instance_name, status
FROM v$instance;
~~~

Record the database name and `LOG_MODE`. In systems with PDBs, these two queries inspect database/instance level; do not equate `V$INSTANCE.INSTANCE_NAME` with the name of the PDB you are practicing in.

### Step 2 — List Datafiles and Tempfiles

~~~sql
SELECT file#, name, status
FROM v$datafile
ORDER BY file#;

SELECT file#, name, status
FROM v$tempfile
ORDER BY file#;
~~~

Note that data files and temp files are managed separately. Never edit or move the listed files directly at the OS level while the database is using them.

### Step 3 — Inspect Control File Copies

~~~sql
SHOW PARAMETER control_files;

SELECT name, status
FROM v$controlfile;
~~~

Compare file names/paths against the `CONTROL_FILES` parameter. If multiple files reside on the same storage or failure domain, having more than one file may still fail to achieve fault tolerance.

### Step 4 — Inspect Redo Log Groups and Members

~~~sql
SELECT group#, thread#, sequence#, status, archived,
       ROUND(bytes/1024/1024) AS size_mb, members
FROM v$log
ORDER BY thread#, group#;

SELECT group#, member, status
FROM v$logfile
WHERE type = 'ONLINE'
ORDER BY group#, member;
~~~

Locate the group with `STATUS = 'CURRENT'` in `V$LOG`. Count members in `V$LOGFILE` to understand multiplexing. If `MEMBERS = 2`, do not mistake that for having two different redo sequences in the group; those are two files for the exact same group.

### Step 5 — Inspect Archive Destinations and Archived Logs

~~~sql
SELECT name, log_mode
FROM v$database;

SHOW PARAMETER db_recovery_file_dest;
SHOW PARAMETER log_archive_dest;

SELECT thread#, sequence#, name, completion_time
FROM v$archived_log
WHERE name IS NOT NULL
ORDER BY completion_time DESC
FETCH FIRST 10 ROWS ONLY;
~~~

If `LOG_MODE = 'ARCHIVELOG'` and archiving activity has occurred, you may see many historical records. Do not claim an archive still exists on disk solely from `NAME`; backup/delete/copy operations can add records or change storage state.

### Step 6 — Observe a Log Switch on a Private Lab Database (Optional)

**Run only if you hold DBA privileges on an isolated lab instance** with sufficient archive space and tolerance for extra I/O and redo. Do not execute on production or shared environments.

First note `SEQUENCE#` and `STATUS` from `V$LOG` in Step 4. Then in an administrative session:

~~~sql
ALTER SYSTEM SWITCH LOGFILE;
~~~

Re-query `V$LOG` to observe that the `CURRENT` group and sequence changed. In `ARCHIVELOG` mode, the archiver may proceed to archive the completed group; depending on timing, `V$ARCHIVED_LOG` might not show the new record instantaneously. In `NOARCHIVELOG` mode, switching groups does not generate an archived log.

`ALTER SYSTEM SWITCH LOGFILE` **causes a real state change**, not a read-only query. It does not directly test restore/recover, nor does it guarantee every dirty block in the database has finished flushing. Afterward, monitor archive/FRA space if archiving is enabled.

## 10. Operational Rules When Designing Storage and Backups

### 10.1. Protecting Control Files and Online Redo

- Place control file copies and multiplexed redo members on separate devices or failure domains; two paths on the same failing disk do not provide desired protection.
- Never binary-edit or manually move datafiles/control files/redo members while Oracle is managing them.
- Monitor I/O error alerts and individual member status; one failed copy does not mean it can safely be ignored long-term.
- With ASM, OMF, RAC, or storage replication, mirror placement and file management must follow platform tooling; do not blindly mimic filesystem commands.

### 10.2. Protecting Archived Redo and Backups

- Choose a backup policy covering **datafiles, control files, and archived redo logs** that meets agreed RPO/RTO, retention, and recovery requirements.
- Ensure contiguous archived redo covers all intended recovery points; retaining too few logs can break recoverability even while the database runs smoothly.
- Monitor FRA/archive destination capacity, redo generation rate, archive rate, and backup duration. Required capacity depends on actual change volume, not just database size.
- Delete archived redo only via validated admin/RMAN procedures that account for standby/Data Guard requirements if any.
- Periodically test **restore and recover** in an authorized environment; a backup file existing does not prove it is usable.

### 10.3. Enabling `ARCHIVELOG` Is an Operational Change

A database can be switched between `NOARCHIVELOG` and `ARCHIVELOG` via administrative commands in the appropriate state—typically requiring the database to be **mounted but not open**, which affects availability. Administrators must preconfigure archive destinations and capacity, schedule downtime, take a post-change backup, and verify archiving actually works.

Syntax illustration on a single-instance lab database managed by a DBA, solely to recognize the sequence:

~~~sql
-- Illustrates an admin operation requiring downtime; DO NOT run on production.
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
ALTER DATABASE ARCHIVELOG;
ALTER DATABASE OPEN;

SELECT log_mode
FROM v$database;
~~~

This snippet **is not an instruction to run automatically**. Before running, verify archive destination configuration, SYSDBA privilege, CDB/PDB scope, service status, storage, backups, and environment procedures. RAC, Oracle Restart, and Data Guard have distinct prerequisites and sequences; never apply those four commands mechanically.

## 11. Common Misconceptions

**"COMMIT means the datafile has finished being written."** False. Under normal commit mechanisms, required redo is flushed to guarantee durability; DBWR may write datafiles later. That is why redo is crucial for instance recovery.

**"The control file only contains datafile names."** Incomplete. It also contains database identity, logs, checkpoints, recovery info, and much other metadata. Losing all control files is a severe administrative incident.

**"Online redo log is the same thing as archived redo log."** False. Online redo is written circularly by LGWR and reused; archived redo is a saved copy of a completed group, keeping history beyond that cycle when archiving is enabled.

**"A group with multiple members means multiple copies of redo over time."** False. Members of one group are identical copies for fault tolerance. Time progression corresponds to groups/sequences cycling and archived logs being saved.

**"ARCHIVELOG automatically guarantees recovery to any point in time."** False. Recoverability depends on backups, redo continuity, control file state, archive destinations, and the target time/SCN.

**"CKPT writes all dirty blocks itself."** False. DBWR writes data blocks. CKPT manages checkpoint coordination and metadata per Oracle's mechanism.

**"Archived redo logs can be deleted right after a log switch finishes."** Very dangerous. Archives may still be needed for RMAN recovery, backups, and Data Guard. Follow retention/deletion policies and verified restore capabilities.

**"Undo is just another kind of redo."** False. Undo supports rollback and read consistency; redo describes changes for recovery, including changes to undo data. They serve different purposes.

## 12. Review Questions and Reasoning Scenarios

1. When `COMMIT` finishes, datafiles have not yet been fully updated by DBWR. What enables Oracle to recover the transaction if the instance crashes?
2. Can one tablespace have multiple datafiles? Can one datafile belong to two tablespaces simultaneously?
3. Why do two control files on the same disk not provide the same protection as two control files on two independent storage domains?
4. Group 2 has two redo members and is `CURRENT`. Does this mean Oracle has two different redo sequences inside the group?
5. What is the difference between `ACTIVE` and `INACTIVE` in `V$LOG`?
6. When a database is in `NOARCHIVELOG`, does an instance crash necessarily render all redo unusable? Why?
7. A datafile is lost; you have the last two days of archived redo but no datafile backup. Can archived redo be treated as a full datafile copy to restore from?
8. Why can a full FRA block applications even when datafiles still have plenty of free space?
9. When needing to recover to an SCN after backup time, why must continuous redo be preserved across log sequences?
10. Distinguish checkpoint from log switch; what are the respective roles of DBWR, CKPT, LGWR, and ARCn?

**Answer hints:**

1. Redo durably written by LGWR into online redo logs lets instance recovery reapply committed changes.
2. One tablespace can have multiple datafiles; one datafile belongs to one tablespace at a time.
3. Both share the same device failure risk or failure domain.
4. No. Both members hold identical redo content for the group; sequence belongs to the group/thread's redo stream.
5. `ACTIVE` may still be needed for instance recovery; `INACTIVE` is no longer needed for instance recovery, though reuse still depends on archiving and other conditions.
6. No. Online redo still supports instance recovery as long as required files remain intact; lacking archived redo mainly limits history for media recovery.
7. No. You need an appropriate data baseline from a backup plus required redo; archived redo is not a datafile copy.
8. ARCn cannot archive logs needing archiving, preventing online redo groups from becoming eligible for reuse.
9. Missing a redo segment can prevent recovery from applying the continuous chain of changes from the backup up to the target SCN.
10. Checkpoint relates to datafile write progress and metadata; log switch is switching to another redo log group. DBWR writes dirty blocks, CKPT coordinates checkpoints/metadata, LGWR writes online redo, and ARCn saves completed redo.

## Oracle Reference Documentation

- [Oracle Database Concepts](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/): physical architecture, datafiles, control files, redo logs, and background processes.
- [Oracle Database Backup and Recovery User's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/): backup, restore, recovery, archived redo, and RMAN principles.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/): exact definitions of `V$DATAFILE`, `V$CONTROLFILE`, `V$LOG`, `V$LOGFILE`, and `V$ARCHIVED_LOG` by version.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/): managing physical files, checkpoints, archive mode, and operational configurations.
