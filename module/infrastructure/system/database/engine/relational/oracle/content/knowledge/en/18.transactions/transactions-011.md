# SCN and the Relationship Between COMMIT and Recovery Requirements in Oracle

In Oracle Database, the **SCN (System Change Number)** is a logical sequence number used to pinpoint the position of changes in the database. SCNs help Oracle maintain read consistency, record when transactions commit, apply redo during recovery, and query past versions of data.

When a transaction executes **COMMIT**, Oracle records the transaction's completion in redo and associates it with a commit SCN. Committing does not mean all data blocks have already been written immediately to datafiles. Redo, undo, and recovery mechanisms cooperate to guarantee committed changes can be recovered after a crash, while uncommitted changes never become confirmed data.

This lesson explains what an SCN is, the relationship between SCN and COMMIT, how Oracle uses SCNs for read consistency, Flashback, and recovery, how to inspect SCNs with SQL, and how to choose recovery targets according to business requirements.

## 1. What Is an SCN?

An SCN is a **System Change Number**, a numeric value managed by Oracle to order events/changes in the database. Think of the SCN as a logical database clock:

- SCNs identify a consistent point in database history.
- Committed transactions are tagged with SCN information.
- Redo records and recovery metadata are organized so Oracle can apply changes in the proper order.
- A query can request reading data as of a past SCN if the required version information is still available.

An SCN **is not wall-clock time** and is not a count of modified rows. You cannot deduce "one SCN equals one second" or "each UPDATE increments the SCN by exactly one." An SCN is a logical ordering milestone; the relationship between an SCN and real time can only be mapped approximately within the window for which Oracle retains mapping data.

### 1.1. SCNs Identify a Consistent Point

Suppose an accounts table initially has:

| ACCOUNT_ID | BALANCE |
|---:|---:|
| 1 | 1000 |
| 2 | 500 |

A transaction transfers 200 from account 1 to account 2:

~~~sql
UPDATE account
SET balance = balance - 200
WHERE account_id = 1;

UPDATE account
SET balance = balance + 200
WHERE account_id = 2;

COMMIT;
~~~

After COMMIT, the new state is 800 and 700. Oracle records the committed transaction at a logical position in database history. The commit SCN distinguishes versions before and after the transaction.

If a query needs to read the state prior to the transfer, Oracle can use undo information to reconstruct the data version at the earlier SCN, provided required undo data is still available and Flashback prerequisites are met.

### 1.2. An SCN Is a Logical Clock, Not a Timestamp

| Property | SCN | Timestamp |
|---|---|---|
| Nature | Logical sequence number managed by Oracle | Calendar time |
| Used for | Change ordering, consistency, recovery | Expressing wall-clock time |
| Increments per second? | No | Has time units |
| Exact 1:1 mapping? | No | Not applicable |
| Can be used as a Flashback target? | Yes | Timestamp can be converted to an approximate SCN |

When an exact recovery point is needed, an SCN is usually more useful than an operator-supplied timestamp. However, you must capture the SCN from the exact event and the right database/incarnation; an SCN number by itself does not contain the backups or redo needed to recover.

## 2. What Does COMMIT Produce?

A transaction usually consists of one or more DML statements:

~~~sql
UPDATE lab_scn_account
SET balance = balance - 100
WHERE account_id = 1;

UPDATE lab_scn_account
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
~~~

Conceptually, COMMIT makes Oracle confirm the transaction has completed. The database writes commit information to redo; the transaction is assigned a commit SCN, and other sessions can see the changes according to Oracle's read consistency rules.

Key point: COMMIT **does not require DBWR to write all modified blocks to datafiles immediately**. Writing data blocks can happen later. The redo log is the critical component enabling Oracle to recover committed changes if the instance crashes before dirty blocks reach datafiles.

### 2.1. Redo and Undo Serve Different Roles

| Component | Primary Role |
|---|---|
| Redo | Records information needed to reapply changes during recovery |
| Undo | Holds prior-version info for rollback and supplying consistent reads |
| Online redo log | Stores redo across the database's log groups |
| Archived redo log | Saved copies of filled redo logs, required for many media recovery/PITR scenarios |
| Datafile | Stores the database's data blocks |

Simplified model:

~~~text
SQL DML
  |
  +----> Modify block in buffer cache
  |
  +----> Generate redo in redo log buffer
  |
  +----> Generate undo for rollback / reading old versions
                 |
                 v
              COMMIT
                 |
                 v
       Write commit record and SCN to redo
                 |
                 v
        LGWR writes redo per commit mechanism
                 |
                 v
        COMMIT is confirmed to client
                 |
                 v
       DBWR writes dirty blocks to datafiles
       (may happen after COMMIT)
~~~

This is a conceptual model; internal details depend on Oracle architecture and configuration. Remember two things:

1. Redo protects recoverability of committed changes.
2. Undo supports rollbacks and reading consistent versions; undo does not replace backups or archived redo logs.

### 2.2. Why Does COMMIT Not Wait for DBWR to Write Datafiles?

If COMMIT had to wait for every data block to be physically written to datafiles, transactions would depend on scattered writes across many data locations. Oracle uses redo to decouple transaction confirmation from when DBWR flushes data blocks.

In standard synchronous commit configuration, LGWR must write the required redo (including the commit record) to the online redo log before COMMIT returns success to the client. DBWR can write data blocks later. If power fails after COMMIT returns yet before DBWR flushes blocks, instance recovery can read redo to reapply committed changes.

Do not misinterpret this as "COMMIT writes nothing to disk." Standard COMMIT waits for the redo write mechanism per commit settings; what is waited on is redo, not every datafile.

## 3. Commit SCN and When a Transaction Is Confirmed

When a transaction commits, Oracle writes a commit record in redo and assigns a commit SCN. The commit SCN identifies the post-transaction data version.

Several points to distinguish:

- Current database SCN is the logical milestone currently managed at the moment of observation.
- A transaction's commit SCN is the milestone tied to that transaction's completion.
- A SELECT's SCN is the consistency milestone the query uses to read data.
- Checkpoint SCN relates to checkpoint and recovery progress, and is not synonymous with a specific transaction's commit SCN.

Never grab an arbitrary `CURRENT_SCN` value and claim it is the exact commit SCN of a transaction that just ran. When investigating a specific transaction, use appropriate sources such as redo/log mining, auditing, Flashback Version Query, or relevant administrative views.

### 3.1. Ordering of Transactions

Suppose Session A commits transaction T1, and then Session B commits transaction T2. Oracle manages the logical order of events so consistent-read and recovery mechanisms understand database state at each milestone. The commit SCN is part of that metadata.

Do not assume every SQL statement inside a transaction has a separate SCN like a commit SCN. A transaction can have many DML operations yet finishes only at its commit boundary.

## 4. COMMIT and Data Visibility in Other Sessions

Oracle defaults to the READ COMMITTED isolation level in many applications. Each SELECT statement sees a consistent snapshot as of the time the query begins (statement-level read consistency).

We can observe this with two sessions.

### 4.1. Prepare the Test Table

Run in a lab schema of a practice PDB. If the table already exists, use a different name or a fresh lab schema.

~~~sql
CREATE TABLE lab_scn_account (
    account_id NUMBER(6) PRIMARY KEY,
    holder_name VARCHAR2(50 CHAR) NOT NULL,
    balance NUMBER(14,2) NOT NULL
);

INSERT INTO lab_scn_account VALUES (1, 'An', 1000);
INSERT INTO lab_scn_account VALUES (2, 'Binh', 500);
COMMIT;
~~~

### 4.2. Session A Updates Without Committing

~~~sql
UPDATE lab_scn_account
SET balance = 800
WHERE account_id = 1;
~~~

Session A sees balance 800 within its own transaction.

### 4.3. Session B Reads Before A Commits

In Session B:

~~~sql
SELECT account_id, balance
FROM lab_scn_account
WHERE account_id = 1;
~~~

Session B reads the previously committed version, balance 1000. It does not see Session A's uncommitted change. Normally, SELECT is not blocked just because A holds a row lock on the updated row; Oracle uses undo to supply a consistent version.

### 4.4. Session A COMMITs, Session B Reads Again

Session A:

~~~sql
COMMIT;
~~~

Then Session B runs a new SELECT:

~~~sql
SELECT account_id, balance
FROM lab_scn_account
WHERE account_id = 1;
~~~

Session B can see balance 800 because the new SELECT started after transaction A committed.

### 4.5. A Running SELECT Does Not Switch Snapshots Mid-Flight

A long query may start at SCN S. If another transaction commits while the SELECT is running, that query continues reading data consistent with its chosen snapshot, rather than taking some rows from before commit and some from after commit.

Oracle can use undo to reconstruct versions matching the query's SCN. If required undo was overwritten before the query completes, `ORA-01555: snapshot too old` can occur.

## 5. Reading Data at an SCN with Flashback Query

Flashback Query lets you query a data version at a past SCN:

~~~sql
SELECT account_id, holder_name, balance
FROM lab_scn_account AS OF SCN 123456
ORDER BY account_id;
~~~

`123456` is only an illustrative value; replace it with an actual SCN captured from the database. Oracle uses undo information to reconstruct the row version at that point in time.

### 5.1. Capturing the Current SCN

You can read the current SCN via a package:

~~~sql
SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS current_scn
FROM dual;
~~~

Or via a dynamic performance view if the account is privileged:

~~~sql
SELECT current_scn
FROM v$database;
~~~

`DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER` returns the current SCN reported by the database. `V$DATABASE.CURRENT_SCN` also provides current SCN information. Both values observe database milestones; they do not automatically represent the commit SCN of a specific transaction.

### 5.2. Before-and-After COMMIT Experiment

On table `LAB_SCN_ACCOUNT`, capture the SCN before making changes:

~~~sql
SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS scn_before
FROM dual;
~~~

Record the returned value, denoted `S_BEFORE`. Then:

~~~sql
UPDATE lab_scn_account
SET balance = balance - 100
WHERE account_id = 1;

UPDATE lab_scn_account
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
~~~

Capture the current SCN after COMMIT:

~~~sql
SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS scn_after
FROM dual;
~~~

Record this value, denoted `S_AFTER`. You can compare versions:

~~~sql
-- Replace the value below with the captured S_BEFORE.
SELECT account_id, balance
FROM lab_scn_account AS OF SCN 123456
ORDER BY account_id;

-- Replace the value below with the captured S_AFTER.
SELECT account_id, balance
FROM lab_scn_account AS OF SCN 123789
ORDER BY account_id;
~~~

The result at the earlier SCN reflects balances before the transfer; the result at the later SCN reflects balances after the transfer, provided enough undo remains to read the older version.

Never use example SCN numbers from code as real targets. Always substitute values captured from your own session/database.

### 5.3. Prerequisites and Limits of Flashback Query

Flashback Query depends on being able to access older versions:

- Required undo is still present in the undo tablespace.
- The account has appropriate privileges to use Flashback Query.
- Objects and data types meet Flashback restrictions.
- No DDL or structural changes occurred that render the target version unreadable under feature limits.

`UNDO_RETENTION` is a retention target duration, not an absolute promise that every old version is always kept. If the undo tablespace experiences pressure without an appropriate retention guarantee setting, Oracle may reuse undo before the target duration elapses. Older queries can then encounter ORA-01555.

## 6. Flashback Version Query: Viewing Row Version History

Beyond reading data at a single SCN, Oracle can display row versions over an SCN range using Flashback Version Query:

~~~sql
SELECT
    versions_startscn,
    versions_endscn,
    versions_operation,
    versions_xid,
    account_id,
    balance
FROM lab_scn_account
VERSIONS BETWEEN SCN 123456 AND 123789
WHERE account_id = 1
ORDER BY versions_startscn;
~~~

Replace the two illustrative SCNs with a real SCN range.

Notable pseudo-columns:

| Column | Meaning |
|---|---|
| VERSIONS_STARTSCN | SCN where the returned version began |
| VERSIONS_ENDSCN | SCN where the version ended; may be NULL for the current version in range |
| VERSIONS_OPERATION | Type of operation creating the version, typically `I`, `U`, or `D` |
| VERSIONS_XID | Transaction ID associated with the version |

Flashback Version Query is useful for investigating how a row changed within the historical range for which Oracle still holds sufficient version info.

Do not treat this as a permanent audit log. Undo has finite duration and retention targets; when long-term business history is required, design audit/history tables, Unified Auditing, CDC, or appropriate archival storage.

## 7. SCN_TO_TIMESTAMP and TIMESTAMP_TO_SCN

Oracle provides functions to map between SCNs and timestamps:

~~~sql
SELECT SCN_TO_TIMESTAMP(123456) AS approximate_time
FROM dual;
~~~

~~~sql
SELECT TIMESTAMP_TO_SCN(
    TIMESTAMP '2026-11-14 10:00:00'
) AS approximate_scn
FROM dual;
~~~

The values here are only illustrative. Substitute an SCN and timestamp suitable for your actual database.

### 7.1. Mapping Is Approximate

`SCN_TO_TIMESTAMP` returns the approximate timestamp corresponding to an SCN; `TIMESTAMP_TO_SCN` returns the approximate SCN corresponding to a timestamp. The mapping is stored over a limited historical window, not as a permanent full lookup table.

If the requested SCN falls outside the stored mapping window, Oracle can raise an error such as `ORA-08181: specified number is not a valid system change number`.

Therefore:

- Use a directly captured SCN when an exact milestone is needed.
- Use timestamp-to-SCN to find an approximate milestone near a business time when appropriate.
- Verify data after running Flashback queries; never assume timestamp mapping yields the exact millisecond of a commit.

### 7.2. An SCN Is Not the Exact Commit Time of Each Row

Two transactions can commit close together in wall-clock time. You cannot deduce a row's exact commit time merely by taking an SCN and converting it to a timestamp. Combine transaction IDs, auditing, application logs, and redo info when an investigation requires high precision.

## 8. ORA_ROWSCN Is Not an Exact Commit SCN for Every Row

Oracle provides the `ORA_ROWSCN` pseudo-column to observe an SCN related to row modifications:

~~~sql
SELECT
    account_id,
    balance,
    ORA_ROWSCN
FROM lab_scn_account
ORDER BY account_id;
~~~

However, understand its limitations:

- By default Oracle tracks this at the block level, so `ORA_ROWSCN` for rows in the same block can be identical even if they were not updated in the same transaction.
- When a table is created with `ROWDEPENDENCIES`, Oracle tracks row dependencies at a finer row level, yet `ORA_ROWSCN` should still not be treated as a complete audit trail or absolute proof of commit time.
- `ORA_ROWSCN` does not replace Flashback Version Query, redo mining, or business history tables.

When you must track precisely who changed which row, when, and from what value to what value, design proper auditing instead of relying solely on `ORA_ROWSCN`.

## 9. SCN and Checkpoints

Checkpoints help Oracle record progress in syncing changes from the buffer cache to datafiles and establish the starting boundary for instance recovery.

Several related SCNs:

- `CURRENT_SCN`: current SCN milestone reported by the database.
- `CHECKPOINT_CHANGE#`: checkpoint SCN associated with the database/control file.
- `START_SCN` or other SCNs in transaction/recovery views: metadata serving specific administrative purposes.

Do not confuse checkpoint SCN with commit SCN. A checkpoint is not a COMMIT operation for every transaction; it is a mechanism managing data writes and recovery.

You can inspect database info:

~~~sql
SELECT
    name,
    open_mode,
    log_mode,
    current_scn,
    checkpoint_change#
FROM v$database;
~~~

Accessing `V$DATABASE` usually requires dynamic performance view privileges or equivalent grants. In environments without admin privileges, use `DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER` if the package is permitted.

## 10. Instance Recovery: Recovering After an Instance Crash

Suppose a server loses power or an instance crashes. Some dirty blocks may not yet have been written to datafiles by DBWR, even though their transactions COMMITted successfully.

When reopening the database, Oracle performs instance recovery using redo and undo:

1. Determine the recovery scope from checkpoint metadata and redo.
2. Roll forward by applying redo to bring blocks forward to the necessary state.
3. Process uncommitted transactions using undo to remove unconfirmed changes.
4. Open the database once recovery completes per operational requirements.

Model:

~~~text
Instance crash
      |
      v
Read checkpoint / redo metadata
      |
      v
ROLL FORWARD using REDO
      |
      v
Necessary changes applied
      |
      v
ROLL BACK uncommitted transactions using UNDO
      |
      v
Database consistent to open
~~~

Key points:

- Redo can contain changes from both committed and uncommitted transactions.
- During recovery, Oracle can apply redo first and then use undo to roll back uncommitted transactions.
- Committed transactions are preserved even if their data blocks were not flushed to datafiles before the crash.

That is why commit records, SCNs, redo, and undo are tightly interconnected.

## 11. Media Recovery and the Role of Archived Redo Logs

Instance recovery handles instance failures when all required files remain intact. If a datafile is lost/corrupted, media recovery is needed: restore a backup and apply redo to bring the file/database to an appropriate state.

Conceptual workflow:

~~~text
Datafile backup
      |
      v
Restore backup to storage
      |
      v
Apply archived redo logs
      |
      v
Apply online redo if available and needed
      |
      v
Reach target SCN / point in time
      |
      v
Open database in the appropriate recovery mode
~~~

The SCN defines how far the database must be recovered. Backups supply the base data image; redo supplies subsequent changes. An SCN itself contains neither backups nor redo.

### 11.1. ARCHIVELOG and NOARCHIVELOG

- A database in `ARCHIVELOG` mode can archive filled online redo logs as archived redo logs, enabling full media recovery and point-in-time recovery scenarios.
- A database in `NOARCHIVELOG` mode has far more limited crash recovery options; it usually relies on consistent backups and can lose changes made after the backup.

Check:

~~~sql
SELECT log_mode
FROM v$database;
~~~

Switching to `ARCHIVELOG` mode is a database administration task typically requiring mount state and DBA privileges. Never perform it casually on a live environment; follow the system's backup/recovery procedures.

## 12. Point-in-Time Recovery (PITR) by SCN

Point-in-time recovery restores a database or an eligible portion of a database to a past point in time. The target can be specified by SCN or timestamp depending on the method.

Business examples:

- A batch job accidentally deleted and COMMITted data.
- A bad deployment wrote corrupt data across multiple tables.
- The database must be recovered to right before a data-corrupting transaction.

When choosing database PITR, the DBA must identify the target SCN, a valid backup prior to that milestone, and all archived redo logs needed to apply up to the target.

### 12.1. Illustrative RMAN Command Example

In a dedicated recovery environment, RMAN syntax might look like:

~~~text
RMAN> RUN {
  SET UNTIL SCN 123456;
  RESTORE DATABASE;
  RECOVER DATABASE;
}

SQL> ALTER DATABASE OPEN RESETLOGS;
~~~

`123456` is an illustrative SCN, not a real value to use. Verify the exact target SCN semantics in the RMAN syntax for your version; RMAN's `UNTIL SCN` clause has specific boundary rules (typically exclusive of the specified SCN itself). Consult the RMAN documentation for your deployed release before running.

This is a DBA operation that alters the state of the entire database. Opening with `RESETLOGS` creates a new database incarnation after incomplete recovery; plan a fresh backup and verify ongoing recovery strategies. Never run example commands on production as an experiment.

### 12.2. Why Is RESETLOGS Needed?

After incomplete recovery or certain recovery workflows, the database is opened with `RESETLOGS` to begin a new redo branch. Redo from the old branch beyond the recovery point cannot simply continue being applied as if history never branched.

RMAN tracks database incarnations to distinguish branches. After `RESETLOGS`, take an appropriate backup so a new recovery baseline exists on the current incarnation.

## 13. Differences Between Flashback Query, Flashback Table, and Flashback Database

Oracle offers several Flashback features. They use SCNs or timestamps, yet their scope and requirements differ.

| Feature | Scope | Primary Mechanism | Purpose |
|---|---|---|---|
| Flashback Query (AS OF SCN) | Queries past versions of data | Undo | Read data at a past SCN |
| Flashback Version Query | History of row versions across an SCN range | Undo and version metadata | Investigate changes |
| Flashback Table | Restores one or a few tables to an earlier milestone | Undo | Fix table-level DML mistakes |
| Flashback Database | Rewinds the entire database to an earlier milestone | Flashback logs and database mechanisms | Recover database to an earlier point |
| RMAN PITR | Database/tablespace/datafile depending on scenario | Backups and redo | Physical recovery to a target SCN/time |

### 13.1. Flashback Table

Flashback Table can return a table to its state at a prior SCN or timestamp, within undo and feature limits:

~~~sql
FLASHBACK TABLE lab_scn_account
TO SCN 123456;
~~~

The example above requires substituting a real SCN. Flashback Table normally requires enabling row movement:

~~~sql
ALTER TABLE lab_scn_account ENABLE ROW MOVEMENT;
~~~

Row movement permits a row's `ROWID` to change when Oracle restores the table version. Verify privileges, constraints, triggers, dependencies, and Flashback Table limits before using it. When parent-child relationships exist, plan across all related tables so referential integrity is not violated.

Flashback Table is a table-data recovery operation; it does not rewind the entire database's SCN backward in time. It generates new changes in the database and the SCN keeps moving forward.

### 13.2. Flashback Database

Flashback Database rewinds the entire database back to a past SCN using flashback logs, if the feature was enabled and sufficient logs remain. This is a database-wide operation, distinct from merely SELECTing old data.

Administrative prerequisites include:

- `ARCHIVELOG` configured as required by the feature.
- Fast Recovery Area (FRA) configured with adequate capacity.
- Flashback Database enabled prior to the incident.
- Flashback logs covering the target SCN.
- Impact assessment on applications and database incarnations.

Flashback Database does not replace backups. Flashback logs have finite retention windows and storage limits; backups remain necessary for lost/corrupted files or recoveries beyond the flashback window.

## 14. When to Use Flashback vs. RMAN PITR?

Choose the method based on error scope and what is available:

| Scenario | Approach Typically Considered |
|---|---|
| Need to inspect data before a committed UPDATE/DELETE | Flashback Query `AS OF SCN` |
| Need to investigate versions of a row | Flashback Version Query |
| Need to revert one table before an accidental DML | Flashback Table if prerequisites are met |
| Need to rewind the whole database before an incident | Flashback Database if enabled and flashback logs exist |
| Datafile is lost/corrupted | RMAN restore and media recovery |
| Need recovery to an SCN from backups and archived redo | RMAN PITR |

Flashback Query **reads** old data; it does not restore current data by itself. Flashback Table/Database perform recovery. RMAN PITR relies on backups and redo and may require `OPEN RESETLOGS` depending on scope and method.

## 15. COMMIT WRITE: WAIT, NOWAIT, IMMEDIATE, and BATCH

Oracle provides options controlling how COMMIT waits for LGWR to write redo:

~~~sql
COMMIT WRITE WAIT IMMEDIATE;
~~~

~~~sql
COMMIT WRITE WAIT BATCH;
~~~

~~~sql
COMMIT WRITE NOWAIT BATCH;
~~~

General meaning:

- `WAIT`: the session waits until required redo is written per commit mechanics before COMMIT returns.
- `NOWAIT`: the session may receive confirmation before redo is durably written; if the instance crashes in that window, a transaction already reported successful may not be guaranteed under normal durability levels.
- `IMMEDIATE`: instructs LGWR to write redo immediately under this mode.
- `BATCH`: allows batching commit write requests to improve group write efficiency.

Not every application needs to specify these options manually. Default behavior also depends on database/session settings and related commit parameters; do not make assumptions from a syntax example alone.

### 15.1. Why Is NOWAIT Risky?

With `NOWAIT`, the client can receive a COMMIT success result before the commit redo is durably persisted. If the instance crashes right in that window, the transaction can be lost even though the application received a success response.

Therefore, for operations requiring strict durability—such as money transfers, payments, order placement, or balance updates—do not arbitrarily enable `NOWAIT` to shave latency. Only consider it if the application tolerates losing some transactions near a crash and RPO requirements have been thoroughly evaluated.

### 15.2. COMMIT and Data Guard

In Data Guard configurations, durability requirements can also involve shipping and applying redo on standby databases. Protection modes such as Maximum Performance, Maximum Availability, or Maximum Protection have different wait/guarantee behaviors.

A successful COMMIT on the primary does not automatically mean every standby has applied the redo. Distinguish:

- Redo generated on primary.
- Redo written locally to online redo log.
- Redo transported to standby.
- Redo written/applied on standby.

Transport and apply lag, protection mode, and synchronous/asynchronous configuration determine protection levels when the primary fails. This belongs to Data Guard administration—inspect the actual configuration rather than inferring from a single SCN.

## 16. SCN and Transaction Modes

### 16.1. READ COMMITTED

Under READ COMMITTED, each SELECT has its own snapshot as of statement start. Two consecutive SELECTs in the same transaction can see different data if another session commits in between.

### 16.2. SERIALIZABLE

Under SERIALIZABLE, a transaction reads from a consistent snapshot as of transaction start, and Oracle enforces write-conflict detection per this isolation level's rules. A transaction can hit a serialization error if concurrent modifications conflict.

### 16.3. SET TRANSACTION READ ONLY

A READ ONLY transaction allows multiple queries to read the same consistent snapshot throughout the transaction:

~~~sql
SET TRANSACTION READ ONLY;

SELECT COUNT(*) FROM lab_scn_account;
SELECT SUM(balance) FROM lab_scn_account;

COMMIT;
~~~

Both SELECTs in the transaction read the exact same snapshot, even if another session commits changes meanwhile, via read consistency. Enough undo must remain to supply the needed versions.

Never use a READ ONLY transaction to run DML; it is a read-only mode.

## 17. Recording SCNs for Recovery and Investigation

If a system has requirements to recover to a business milestone, record key information:

- SCN right before deploying or running a major batch job.
- Start/end times per application clock.
- Transaction ID or business batch code.
- User/process performing the change.
- Backups and archived redo logs covering that milestone.
- Database incarnation and Data Guard state if applicable.

Example capturing an SCN before a batch job:

~~~sql
SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS batch_start_scn
FROM dual;
~~~

Applications/DBAs can store the returned value in a deployment log or dedicated management table. If stored in a database table, that log record must also be committed and appropriately protected; do not let the log itself get wiped out together with the batch under investigation.

A single SCN milestone alone does not guarantee recoverability. You must have backups, redo/undo, or flashback logs matching the chosen method.

## 18. SCN in Data Dictionary and Dynamic Performance Views

Several administrative views help observe SCNs:

~~~sql
SELECT
    current_scn,
    checkpoint_change#,
    resetlogs_change#,
    resetlogs_time,
    log_mode
FROM v$database;
~~~

Columns:

- `CURRENT_SCN`: current SCN reported by the database.
- `CHECKPOINT_CHANGE#`: SCN related to checkpoints.
- `RESETLOGS_CHANGE#`: SCN associated with the current incarnation's RESETLOGS.
- `RESETLOGS_TIME`: recorded timestamp of RESETLOGS.
- `LOG_MODE`: `ARCHIVELOG`/`NOARCHIVELOG` mode.

To inspect archived logs and SCN ranges, DBAs can run:

~~~sql
SELECT
    thread#,
    sequence#,
    first_change#,
    next_change#,
    archived,
    applied
FROM v$archived_log
ORDER BY thread#, sequence#;
~~~

In RAC there can be multiple redo threads; never assume only one thread exists. `FIRST_CHANGE#` and `NEXT_CHANGE#` show an archived log's SCN range per metadata. These views require appropriate read privileges.

In environments without DBA privileges, only use packages/views granted to the account. Do not grant broad privileges just to run an SCN-observation query in a lab schema.

## 19. ORA_ROWSCN, Flashback, and Auditing: Choosing the Right Tool

Different change-tracking methods answer different questions:

| Tool | Question Answered | Primary Limitation |
|---|---|---|
| ORA_ROWSCN | Which SCN is associated with a row/block? | Not a full history; may be block-level |
| Flashback Query | What did data look like at an old SCN? | Depends on undo and retention window |
| Flashback Version Query | Which row versions remain queryable across an SCN range? | Not a permanent audit log |
| Unified Auditing / audit | Who performed which action under a policy? | Depends on policy, config, and retention |
| Application-designed history table | Old/new values and business context | Must be designed, written, and protected |
| LogMiner | Analyzes redo contents within supported bounds | Requires privileges, archived/online redo, and proper setup |

If the requirement is "who changed the balance, from what value to what value, and why," an SCN alone cannot answer completely. Combine transaction IDs, auditing, application logs, and historical tables.

## 20. SCN, Flashback, and Undo Limits

Flashback Query/Version Query relies on version metadata Oracle still retains. Influencing factors:

- `UNDO_RETENTION`.
- Undo tablespace size.
- DML generation rate and undo contention.
- `RETENTION GUARANTEE` setting if enabled.
- Query duration and volume of undo to read.

Check settings:

~~~sql
SHOW PARAMETER undo_retention;
~~~

Or:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name IN ('undo_retention', 'undo_tablespace');
~~~

`UNDO_RETENTION` is a target time in seconds. Without retention guarantee, Oracle may overwrite expired undo—or reuse undo when low on space. Retention guarantee can protect unexpired undo, yet can cause DML to fail if no free undo space remains; manage capacity carefully.

Do not mechanically increase `undo_retention` without calculating space, DML rate, and expected Flashback query duration.

## 21. Distinguishing Rollback, Flashback, and Recovery

All of these mechanisms can revert data to an earlier state, yet they operate at different scopes and times:

| Mechanism | When Used | Scope | Requires Open Transaction? |
|---|---|---|:---:|
| ROLLBACK | Discard uncommitted changes | Current transaction | Yes |
| ROLLBACK TO SAVEPOINT | Discard partial uncommitted changes | Work after savepoint | Yes |
| Flashback Query | Read older versions | SELECT | No |
| Flashback Table | Restore table(s) to an earlier milestone | One/a few tables | No |
| Flashback Database | Rewind database to an earlier milestone | Database | No |
| RMAN PITR | Recover from backups and redo to a milestone | Database/tablespace/datafile by method | No |

After COMMIT, standard ROLLBACK cannot undo that transaction. To recover mistakenly committed data, evaluate Flashback, RMAN PITR, or a business compensation process. Never confuse ROLLBACK with Flashback: ROLLBACK handles uncommitted transactions; Flashback/recovery handles states already recorded at earlier milestones.

## 22. Common Errors

| Symptom | Cause | Resolution |
|---|---|---|
| ORA-01555: snapshot too old | Undo needed for consistent read/Flashback is gone | Tune undo capacity/retention, shorten query duration, consider retention guarantee |
| ORA-08181: specified number is not a valid system change number | Invalid SCN or outside timestamp/SCN mapping window | Check SCN source, database/incarnation, and mapping range |
| Flashback Query fails to return expected version | Undo gone, DDL occurred, or object limits | Check SCN, retention, and object type |
| ORA-01466 during Flashback | Table definition changed within the flashback window | Inspect DDL history and Flashback Query limits |
| COMMIT returned yet datafile is not updated | DBWR writes blocks after COMMIT; redo protects changes | Normal behavior; verify redo/recovery, do not demand DBWR flush every block |
| Lost a just-confirmed transaction in a special setup | `COMMIT NOWAIT` or altered durability config may be in use | Check `COMMIT_WRITE`/commit mode and durability requirements |
| PITR cannot reach target SCN | Missing backups or redo covering the required span | Inspect backups, archived logs, incarnation, and recovery catalog/control file |
| Wrong recovery target chosen | Used approximate timestamp or SCN from wrong incarnation | Record event SCNs, check RESETLOGS and target semantics |
| Standby data lags behind primary | Redo transport/apply lag | Inspect Data Guard transport/apply and protection mode |

## 23. Practice Exercises

### Exercise 1 — Capture the Current SCN

Write a query using `DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER` and a query using `V$DATABASE.CURRENT_SCN`.

**Question:** What do these two values tell you? Can you claim they are the commit SCN of a transaction that just ran?

**Guided Answer:** these report the database's current SCN; they do not automatically identify a specific transaction's commit SCN.

### Exercise 2 — Observe READ COMMITTED

Open two sessions. Session A UPDATEs an account without COMMITting; Session B SELECTs the same row; then A COMMITs and B SELECTs again.

**Question:** Why does Session B read the old value before COMMIT and the new value in the SELECT after COMMIT?

**Guided Answer:** statement-level read consistency and undo provide the committed snapshot as of when each SELECT starts.

### Exercise 3 — Flashback Query

Record the SCN before updating a balance, UPDATE and COMMIT, then use `AS OF SCN` to read back.

**Question:** If required undo was already overwritten, what can happen?

**Answer:** Flashback Query can fail, typically raising `ORA-01555` depending on the case.

### Exercise 4 — Compare Flashback Version Query

Use `VERSIONS BETWEEN SCN ... AND ...` to view versions of an account after two UPDATEs and COMMITs.

**Requirement:** display `VERSIONS_STARTSCN`, `VERSIONS_ENDSCN`, `VERSIONS_OPERATION`, and balance.

### Exercise 5 — Timestamp and SCN

Run `SCN_TO_TIMESTAMP` and `TIMESTAMP_TO_SCN` with values within the database's active mapping range.

**Question:** Why should mapping results not be treated as an exact absolute commit timestamp?

**Guided Answer:** mapping is approximate and covers a limited historical retention window.

### Exercise 6 — COMMIT and DBWR

Explain why a COMMITted transaction can still have dirty blocks not yet written to datafiles by DBWR.

**Guided Answer:** standard COMMIT waits for required redo to be written; DBWR writes data blocks later via checkpoint/background mechanisms.

### Exercise 7 — Choose a Recovery Method

For each scenario, choose Flashback Query, Flashback Table, Flashback Database, or RMAN PITR:

1. Only need to view the balance before an UPDATE.
2. Need to restore one table after an accidental DELETE.
3. Need to rewind the whole database before a bad batch job.
4. A datafile is corrupted and needs restoration from backup.

**Guidance:** respectively Flashback Query; Flashback Table if prerequisites are met; Flashback Database or RMAN PITR per configuration; RMAN restore/recovery.

### Exercise 8 — Commit Durability

Explain the difference between `COMMIT WRITE WAIT` and `NOWAIT`, and why financial transactions must evaluate carefully before using `NOWAIT`.

### Exercise 9 — SCN and Auditing

An investigator needs to know who changed a balance, from which value to which value, and why. Explain why `ORA_ROWSCN` alone is insufficient.

**Guidance:** `ORA_ROWSCN` is not an audit log; auditing/history, transaction ID, and application context are required.

## 24. Process for Selecting an SCN and Recovery Method

When a data incident occurs, define the goal before picking a command:

1. **Has the mistake been COMMITted?** If the transaction is still open, ROLLBACK or ROLLBACK TO may suffice.
2. **Do you only need to read old data or restore current data?** For reading, use Flashback Query; restoring tables/databases requires corresponding features.
3. **What is the scope of impact?** One row, one table, multiple tables, or the entire database?
4. **Where does the target SCN come from?** Deployment logs, batch logs, auditing, transaction investigation, or a DBA-recorded milestone?
5. **Are undo/flashback logs still present?** Check retention and space.
6. **Do suitable backups and archived redo logs exist?** Essential for media recovery/PITR.
7. **Are Data Guard or multiple incarnations involved?** Check redo transport/apply, RESETLOGS, and database branches.
8. **Can results be verified in an isolated environment?** Validate before returning the database to service.

Decision diagram:

~~~text
Erroneous change detected
          |
          v
Was transaction COMMITted?
       /          \
     No            Yes
      |              |
      v              v
ROLLBACK /       Choose scope to handle
ROLLBACK TO           |
      |          +----+------------------+
      |          |           |          |
      |          v           v          v
      |      Read only   One/few tbls  Whole database
      |          |           |          |
      |          v           v          v
      |    Flashback     Flashback    Flashback DB
      |      Query        Table       or RMAN PITR
      |          |           |          |
      +----------+-----------+----------+
                         |
                         v
              Verify required SCN, undo,
              backups, and redo
                         |
                         v
                  Verify outcome
~~~

SCNs provide the logical milestones Oracle uses to pinpoint data versions and recovery positions. COMMIT records transaction completion and establishes a boundary usable by sessions, redo, and recovery. Redo protects the ability to reapply committed changes; undo supports rollback and consistent reads; Flashback and RMAN use SCN milestones alongside appropriate stored data to read or recover past states. By clearly distinguishing these roles, you will select the right method for every incident and avoid mistaking an SCN number for the recovery data itself.
