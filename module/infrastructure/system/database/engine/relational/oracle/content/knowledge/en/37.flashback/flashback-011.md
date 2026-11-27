# Choosing How to Recover from Accidental Deletes, Mistaken Updates, or Failed Deployments Using Oracle Flashback

When data is accidentally deleted, updated incorrectly, or a deployment corrupts database state, the first question is not "which Flashback command should I run?"—it is **what scope must be rolled back, to which point in time, and whether valid changes made afterward can be discarded**.

Oracle offers multiple recovery mechanisms with very different scopes:

- **ROLLBACK** cancels changes made by an uncommitted transaction.
- **Flashback Query and Flashback Versions Query** read data at an earlier point in time or inspect row versions across changes.
- **Flashback Table** returns one or more tables to a prior state.
- **Flashback Drop** restores a recently DROPped table if the object remains in the recycle bin.
- **Flashback Database** returns the entire database or a supported scope to an SCN, timestamp, or restore point.
- **RMAN point-in-time recovery (PITR)** recovers a database, tablespace, PDB, or table to a point in time based on backups and archived redo.

Each approach has different prerequisites, limitations, and blast radii. Flashback Query is typically suited for reading and reconstructing data; Flashback Table modifies an entire table; Flashback Database can discard all transactions after the recovery milestone; RMAN PITR requires backup/recovery infrastructure and can take significant time.

Using Oracle Database 19c as the reference baseline, this lesson focuses on selecting the right method for accidental DELETE/UPDATE, DROP/TRUNCATE, failed DDL/DML deployments, and incidents requiring broader recovery; then verifying data, managing subsequent transactions, and recording recovery evidence.

## 1. Start by classifying the incident

### 1.1. Five questions that determine the approach

Before running any recovery command, determine:

1. **Has the change been COMMITted?** If not, ROLLBACK or ROLLBACK TO SAVEPOINT can resolve it directly.
2. **What type of change occurred?** DELETE, UPDATE, erroneous INSERT, DROP, TRUNCATE, DDL, configuration change, or physical corruption.
3. **What scope must be recovered?** A few rows, a table, a tablespace/PDB, or the entire database.
4. **What data milestone must you return to?** Which SCN, timestamp, transaction, or restore point?
5. **Must valid changes made after that milestone be preserved?** This factor often decides between Flashback Table/compensating DML and Flashback Database/PITR.

If the exact time of the error is unknown, determine it from application logs, deployment logs, audit trails, transaction IDs, and SCNs before executing recovery.

### 1.2. Quick option selection matrix

| Situation | Option typically evaluated first | Scope of impact | Key prerequisites/limitations |
| --- | --- | --- | --- |
| Uncommitted DELETE/UPDATE | ROLLBACK or ROLLBACK TO SAVEPOINT | Current transaction | Session/transaction still active |
| COMMITted DELETE/UPDATE, only need to view old data | Flashback Query | Read row history | Undo still retains required version |
| Only a few rows modified erroneously, valid changes must stay | Flashback Query/Versions Query then compensating DML | Selected rows | Must pinpoint exact rows and change ordering |
| Entire table must return to pre-error state | Flashback Table | Entire specified table | Row movement, undo/history, and DDL limits |
| Table recently DROPped | Flashback Drop | Object in recycle bin | Not PURGEd; matching version in recycle bin |
| Table recently TRUNCATEd | RMAN RECOVER TABLE or broader recovery | Table recovered via auxiliary database | Flashback Table does not undo TRUNCATE |
| Failed DDL/deployment, need database-wide rewind | Flashback Database to restore point/SCN | Entire database | Flashback logs and willingness to drop post-milestone changes |
| Need recovery from backups or insufficient flashback logs | RMAN PITR | Database/tablespace/PDB/table depending on method | Backups, archived redo, and recovery workflow |
| Datafile/storage corruption | RMAN restore/recover | File/tablespace/database | Flashback alone does not replace media recovery |

This matrix is a starting point. Before running anything, confirm the exact incident type, time, and scope. Do not choose Flashback Database merely because the command looks shorter when only a single table is affected.

### 1.3. Identifying the blast radius

Blast radius is the scope of data and workload impacted by the recovery operation:

- ROLLBACK: changes within the current transaction.
- Compensating DML: the specific rows/attributes actively modified by the repair script.
- Flashback Table: the specified tables; valid changes after the milestone on those tables may be lost.
- Flashback Drop: the object restored from the recycle bin; dependencies must be verified.
- Flashback Database: the entire database rewound to an earlier point; post-milestone transactions are removed from current state.
- RMAN PITR: scope depends on the chosen database, tablespace, PDB, or table.

The wider the recovery scope, the greater the demands for application coordination, backups, validation, and downtime.

## 2. Identifying the incident time and SCN

### 2.1. Timestamp and SCN

An SCN (System Change Number) is the logical sequence number Oracle uses to mark a consistent point in the database. Many Flashback and RMAN operations accept an SCN as the target anchor.

Timestamps are easier to correlate with application logs, while SCNs are generally better for pinpointing the exact recovery point. Record both whenever possible.

### 2.2. Converting between SCN and timestamp

Oracle provides conversion functions:

~~~sql
SELECT SCN_TO_TIMESTAMP(123456789) AS approximate_time
FROM   dual;
~~~

~~~sql
SELECT TIMESTAMP_TO_SCN(
           TO_TIMESTAMP('2026-11-14 01:30:00',
                        'YYYY-MM-DD HH24:MI:SS')
       ) AS target_scn
FROM   dual;
~~~

SCN_TO_TIMESTAMP only maps within the range of mapping metadata still retained; it is not an indefinite SCN history service. Timestamp-to-SCN also requires the milestone to lie within the range supported by the database. For critical recoveries, never derive an SCN through manual time arithmetic.

### 2.3. Finding the SCN from transactions or audits

If the application logs transaction IDs/request IDs, cross-check:
- Application logs and deployment logs.
- Unified audit trail.
- Flashback Versions Query.
- FLASHBACK_TRANSACTION_QUERY when required data exists.
- Restore points and the alert log.
- Backup/archivelog metadata.

An audit record's timestamp is not necessarily the exact SCN of every change in a transaction. Use multiple sources to narrow down the boundary.

### 2.4. Checking database mode and Flashback capability

~~~sql
SELECT name,
       open_mode,
       log_mode,
       flashback_on,
       database_role
FROM   v$database;
~~~

Key fields:
- LOG_MODE: whether the database runs in ARCHIVELOG mode.
- FLASHBACK_ON: Flashback Database status.
- DATABASE_ROLE: primary, physical standby, or another role.
- OPEN_MODE: current open state.

Flashback Query/Table rely on undo and have different prerequisites from Flashback Database. FLASHBACK_ON = NO does not mean every Flashback feature is unavailable.

### 2.5. Checking the flashback log window

~~~sql
SELECT oldest_flashback_scn,
       oldest_flashback_time,
       retention_target,
       flashback_size,
       estimated_flashback_size
FROM   v$flashback_database_log;
~~~

This view is useful when Flashback Database is configured and flashback log metadata exists. It indicates the estimated flashback range still available. Never rely on a single column to promise guaranteed recovery; verify the FRA, logs, restore points, and database state.

## 3. Uncommitted transaction: ROLLBACK first

### 3.1. Uncommitted DELETE

~~~sql
DELETE FROM orders
WHERE  order_id = 9001;

-- Mistaken deletion detected before COMMIT:
ROLLBACK;
~~~

ROLLBACK cancels uncommitted changes in the current transaction. If the transaction contains a mix of valid and erroneous operations, ROLLBACK TO SAVEPOINT may be needed instead of rolling back everything.

### 3.2. Using SAVEPOINT

~~~sql
SAVEPOINT before_risky_update;

UPDATE accounts
SET    balance = balance - 500
WHERE  account_id = 1001;

-- Error detected:
ROLLBACK TO SAVEPOINT before_risky_update;
~~~

SAVEPOINT lets you roll a transaction back to a marked checkpoint without undoing operations before the savepoint.

### 3.3. COMMITted transactions

After COMMIT, a standard ROLLBACK cannot undo that transaction. At that point, determine whether old data still exists in undo, whether a dropped table/object remains in the recycle bin, or whether recovery from backup/Flashback Database is required.

Never run ROLLBACK in another session expecting it to cancel a prior session's committed transaction.

### 3.4. DDL and implicit commits

Oracle performs implicit commits around many DDL statements. Consequently, you cannot rely on ROLLBACK to undo a deployment that executed CREATE, ALTER, DROP, or TRUNCATE and then failed on a subsequent step.

A deployment script may:
- Commit prior DML before executing DDL.
- Execute DDL and implicitly commit.
- Fail mid-migration.
- Leave the schema in a half-old, half-new state.

Select the recovery method based on each change that actually occurred; never assume an entire script is one atomic transaction.

## 4. Flashback Query — reading data at a prior point

### 4.1. Reading a table AS OF SCN

Flashback Query lets you query data at an earlier SCN:

~~~sql
SELECT order_id,
       status,
       total_amount
FROM   orders AS OF SCN 123456789
WHERE  order_id = 9001;
~~~

The result reflects the consistent data version at the specified SCN, provided Oracle still holds enough undo to reconstruct that version.

### 4.2. Reading a table AS OF TIMESTAMP

~~~sql
SELECT order_id,
       status,
       total_amount
FROM   orders AS OF TIMESTAMP
       TO_TIMESTAMP('2026-11-14 01:30:00',
                    'YYYY-MM-DD HH24:MI:SS')
WHERE  order_id = 9001;
~~~

Timestamps are helpful when the error time is known from deployment or application logs. When high precision is needed, identify the SCN and verify results at that point.

### 4.3. Comparing current vs. historical data

~~~sql
SELECT current_row.order_id,
       current_row.status AS current_status,
       old_row.status AS old_status,
       current_row.total_amount AS current_amount,
       old_row.total_amount AS old_amount
FROM   orders current_row
JOIN   orders AS OF SCN 123456789 old_row
       ON old_row.order_id = current_row.order_id
WHERE  current_row.order_id = 9001;
~~~

This query shows how current values differ from values at the SCN milestone. If the current row was already deleted, use a direct historical query or an outer join from a known key set.

### 4.4. Reconstructing deleted rows

If the keys of deleted rows are known, you can query the prior version and use the result as the source for recovery INSERTs:

~~~sql
SELECT order_id,
       customer_id,
       status,
       total_amount,
       created_at
FROM   orders AS OF SCN 123456789
WHERE  order_id IN (9001, 9002, 9003);
~~~

After checking the data, you can populate a staging table or run selective INSERTs. Never insert directly into the production table without checking:
- Whether primary/unique keys already exist.
- Whether foreign keys remain valid.
- Whether triggers cause side effects.
- What rules govern identity/default/generated columns.
- Whether the row was validly recreated by the business after that time.

### 4.5. Undo retention and ORA-01555

Flashback Query relies on older version information. If required undo has already been reused, the query can fail, typically with ORA-01555: snapshot too old.

Historical queryability depends on:
- UNDO_RETENTION.
- Undo tablespace size and undo generation rate.
- Concurrent DML.
- Elapsed time between the change and the query.
- Retention guarantee configuration and workload.

UNDO_RETENTION is a target, not an absolute guarantee in every configuration. If historical data must be retained long-term, design Flashback Data Archive or proper backups/archiving rather than relying on regular undo.

### 4.6. Flashback query privileges

Users need appropriate object privileges and permission to use Flashback Query. Depending on the case, SELECT, FLASHBACK object privilege, or broader administrative privileges may be required. Grant minimal necessary privileges; never grant SELECT ANY TABLE solely to recover a single table.

## 5. Flashback Versions Query — viewing row versions

### 5.1. Purpose

Flashback Versions Query reveals row versions across an SCN or timestamp range. It is helpful when:
- You need to know how many times a row changed.
- You need to distinguish INSERT/UPDATE/DELETE operations.
- You need to find the associated transaction ID.
- You need to choose the exact version before running compensating DML.

### 5.2. Querying versions by SCN

~~~sql
SELECT versions_startscn,
       versions_endscn,
       versions_operation,
       versions_xid,
       order_id,
       status,
       total_amount
FROM   orders
       VERSIONS BETWEEN SCN 123456000 AND 123456900
WHERE  order_id = 9001
ORDER  BY versions_startscn;
~~~

Pseudo-columns:
- VERSIONS_STARTSCN: SCN when the version began.
- VERSIONS_ENDSCN: SCN when the version ended; may be NULL for the current version.
- VERSIONS_OPERATION: operation creating the version, typically I, U, or D.
- VERSIONS_XID: associated transaction ID.

Some values may be NULL depending on version type and retrieval boundaries. Interpret alongside application data and transaction context.

### 5.3. Querying versions by time

~~~sql
SELECT versions_starttime,
       versions_endtime,
       versions_operation,
       versions_xid,
       order_id,
       status
FROM   orders
       VERSIONS BETWEEN TIMESTAMP
           TO_TIMESTAMP('2026-11-14 01:00:00',
                        'YYYY-MM-DD HH24:MI:SS')
       AND TO_TIMESTAMP('2026-11-14 02:00:00',
                        'YYYY-MM-DD HH24:MI:SS')
WHERE  order_id = 9001
ORDER  BY versions_starttime;
~~~

The STARTTIME/ENDTIME pseudo-columns provide version timing info. When an exact recovery point is needed, convert to and use SCN after verification.

### 5.4. Limitations

Versions Query is not a long-term audit log:
- Depends on remaining undo.
- Does not necessarily show complete history for every object.
- Certain DDL operations or object types are not supported like DML row history.
- Versions already purged/reused cannot be reconstructed via query.
- Does not replace backups or audit trails.

## 6. Querying transaction info and UNDO_SQL

### 6.1. FLASHBACK_TRANSACTION_QUERY

The FLASHBACK_TRANSACTION_QUERY view can provide transaction details and SQL representing the inverse of certain changes:

~~~sql
SELECT xid,
       start_scn,
       commit_scn,
       logon_user,
       operation,
       table_name,
       undo_sql
FROM   flashback_transaction_query
WHERE  table_name = 'ORDERS'
ORDER  BY commit_scn DESC;
~~~

To pinpoint the right transaction, filter by the XID obtained from VERSIONS_XID and by the SCN/time range.

### 6.2. Supplemental logging

The ability to query transactions and reconstruct required details can depend on supplemental logging and remaining redo/undo data. For deep investigations, the DBA must verify which logging configuration was active at the time of the event; enabling supplemental logging after an incident does not regenerate lost details.

### 6.3. UNDO_SQL is a suggestion, not a safe recovery script

UNDO_SQL can be useful for understanding how to invert a DML statement. However, never copy all contents and run them directly in production:
- Data may have changed further after the original transaction.
- Constraints and transaction ordering can create dependencies.
- Triggers can fire side effects.
- SQL may require exact key values or context.
- Multiple transactions may depend on one another.

Inspect every statement, stage target values, and execute inside a controllable transaction.

### 6.4. DBMS_FLASHBACK.TRANSACTION_BACKOUT

Oracle includes Transaction Backout to reverse one or more transactions with dependency analysis. This is a specialized mechanism, not the default choice for every mistaken UPDATE/DELETE. Understand dependencies, cascade options, privileges, and limits, and test before using it.

For a few bad rows, Flashback Query/Versions Query followed by compensating DML is usually easier to control. For complex transactions, consult the package reference and experienced DBAs.

## 7. Flashback Table — returning an entire table to a prior state

### 7.1. When is it appropriate?

Flashback Table is appropriate when:
- A table suffered widespread erroneous updates or deletes.
- The entire table must return to before the event.
- Sufficient undo remains to reconstruct the state.
- It is acceptable that valid changes on that table after the milestone are also rolled back.

If only a few rows are wrong while most of the table received valid updates after the milestone, Flashback Table can discard newer valid data. Consider Flashback Query and compensating DML instead.

### 7.2. Enabling row movement

Flashback Table requires row movement to be enabled:

~~~sql
ALTER TABLE orders ENABLE ROW MOVEMENT;
~~~

Check:

~~~sql
SELECT table_name,
       row_movement
FROM   user_tables
WHERE  table_name = 'ORDERS';
~~~

Row movement allows a row's ROWID to change during certain operations. Applications should never treat ROWID as a stable business key.

### 7.3. Flashback Table to SCN

~~~sql
FLASHBACK TABLE orders
TO SCN 123456789;
~~~

This command returns the table to its state at the specified SCN. It affects the entire named table, not just one row. Related tables, locks, and constraints may need to be addressed beforehand.

### 7.4. Flashback Table to timestamp

~~~sql
FLASHBACK TABLE orders
TO TIMESTAMP TO_TIMESTAMP(
    '2026-11-14 01:30:00',
    'YYYY-MM-DD HH24:MI:SS'
);
~~~

The timestamp must lie within usable undo/history range. Whenever possible, convert to and record an SCN as a clear recovery anchor.

### 7.5. Flashbacking multiple tables

~~~sql
FLASHBACK TABLE orders, order_items
TO SCN 123456789;
~~~

Related tables may need to revert to the same anchor to preserve business consistency. Check foreign keys, triggers, materialized views, indexes, and related data before recovering.

### 7.6. Pre-checks before Flashback Table

- Does enough undo remain to recover to the milestone?
- Does the table have row movement enabled?
- Was there any incompatible DDL after the milestone?
- Are any transactions holding blocking locks?
- Do dependent tables need to be flashbacked to the same time?
- Is losing valid post-milestone changes on the table acceptable?
- Is there staging/backup preserving current data if reconciliation is needed?

Flashback Table has restrictions for certain object types and DDL operations. Read the SQL Language Reference for your exact release before running on special tables, partitioned tables, objects with dependencies, or complex structures.

### 7.7. Verification after Flashback Table

After the command finishes:
1. Count rows and verify key business identifiers.
2. Compare sample data against the desired state.
3. Check constraints and indexes.
4. Check triggers and row movement status.
5. Run critical business queries.
6. Confirm application services function properly.
7. Account for valid post-milestone changes that were reverted and apply compensation if needed.

Do not rely solely on the FLASHBACK TABLE statement returning success.

## 8. Flashback Drop — recovering a DROPped table

### 8.1. Recycle bin

When the recycle bin is enabled and an object is eligible, DROP TABLE can move the object into the recycle bin instead of immediately freeing its segments.

Check the recycle bin:

~~~sql
SHOW PARAMETER recyclebin;
~~~

Inspect objects:

~~~sql
SELECT object_name,
       original_name,
       type,
       droptime,
       dropscn,
       can_undrop,
       can_purge
FROM   user_recyclebin
ORDER  BY droptime DESC;
~~~

The recycle bin is not a backup. Objects can be purged by users/DBAs or due to space pressure.

### 8.2. Restoring a table under its original name

~~~sql
FLASHBACK TABLE orders
TO BEFORE DROP;
~~~

If multiple objects share the same original name in the recycle bin, you may need to specify the exact recycle bin name instead of the original name.

### 8.3. Restoring with a new name

~~~sql
FLASHBACK TABLE orders
TO BEFORE DROP
RENAME TO orders_recovered;
~~~

Use a new name when the original table has already been recreated or when you need to inspect data before replacing the live object.

### 8.4. Restoring by recycle bin object name

~~~sql
SELECT object_name,
       original_name,
       type,
       droptime
FROM   user_recyclebin
WHERE  original_name = 'ORDERS'
ORDER  BY droptime DESC;
~~~

You can pass the BIN$... object_name into FLASHBACK TABLE TO BEFORE DROP when selecting the exact dropped object version.

### 8.5. Limitations of Flashback Drop

Flashback Drop cannot restore objects that were PURGEd or are no longer in the recycle bin. The following cases require another method:
- DROP TABLE PURGE.
- Recycle bin disabled.
- Object purged due to space pressure.
- Unsupported object type.
- Dependent object conflicts or reused object names.

Flashback Drop is not a way to undo TRUNCATE. If a table was only truncated, evaluate RMAN RECOVER TABLE or broader recovery methods.

### 8.6. After recovery

Verify:
- Table and data.
- Indexes, constraints, triggers.
- Grants and synonyms.
- Dependent objects.
- Object names and any newly recreated objects with the same name.
- Application references.

Some dependent objects may require checking/recompiling or separate restoration to their pre-DROP state.

## 9. Flashback Database — rewinding the entire database to a prior milestone

### 9.1. When should it be used?

Flashback Database is appropriate when an error has wide impact:
- A deployment modifies multiple schemas/objects.
- Widespread erroneous DML/DDL.
- The database must return to before a release or administrative operation.
- A clear restore point or SCN exists.
- Flashback logs cover the target rewind milestone.

This approach has a large blast radius. The database returns to its state at that milestone; post-milestone transactions no longer exist in current state. If post-milestone transactions were valid and must be retained, extract/reconcile and reapply them per plan.

### 9.2. Primary prerequisites

Flashback Database requires proper configuration and resources, including:
- Database in ARCHIVELOG mode for standard Flashback Database workflows.
- Flashback Database enabled or a guaranteed restore point satisfying usage conditions.
- Flash Recovery Area (FRA) with sufficient capacity for flashback logs and related files.
- Flashback logs still covering the target milestone.
- Database and required files still accessible.

Check:

~~~sql
SELECT log_mode,
       flashback_on
FROM   v$database;
~~~

~~~sql
SHOW PARAMETER db_recovery_file_dest;
SHOW PARAMETER db_recovery_file_dest_size;
SHOW PARAMETER db_flashback_retention_target;
~~~

The flashback retention target is a goal, not a guarantee every milestone remains available. Check oldest flashback SCN/time and FRA usage before deciding.

### 9.3. Normal restore points

Create a restore point:

~~~sql
CREATE RESTORE POINT before_release_2026_11_14;
~~~

A normal restore point saves a name and SCN for convenient reference. It does not itself guarantee flashback logs are retained up to the restore point without a corresponding guarantee mechanism.

### 9.4. Guaranteed restore points

~~~sql
CREATE RESTORE POINT before_release_2026_11_14
GUARANTEE FLASHBACK DATABASE;
~~~

A guaranteed restore point directs Oracle to retain the flashback logs required to flashback to that milestone, but those logs consume FRA space. If the FRA runs out of space, the database can face severe disruption because logs protected by the restore point cannot be deleted.

Create a guaranteed restore point only when:
- A clear retention schedule exists.
- FRA capacity and data change rate have been calculated.
- FRA alerting/monitoring is active.
- Someone is explicitly responsible for dropping the restore point once the release is accepted.

### 9.5. Inspecting restore points

~~~sql
SELECT name,
       scn,
       time,
       guarantee_flashback_database,
       storage_size,
       preserved
FROM   v$restore_point
ORDER  BY time DESC;
~~~

Column names may depend on state/release; use DESC V$RESTORE_POINT if needed. Check SCN, timestamp, guarantee flag, and retained storage size.

### 9.6. Flashback Database to a restore point

General workflow in a single-instance environment:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;

FLASHBACK DATABASE TO RESTORE POINT before_release_2026_11_14;

ALTER DATABASE OPEN RESETLOGS;
~~~

This is a database-wide recovery operation requiring DBA coordination and application shutdown. In RAC, Data Guard, or CDB/PDB, the procedure has additional architecture-specific requirements; never apply this skeleton blindly without verifying architecture.

### 9.7. Flashback Database to SCN or timestamp

~~~sql
FLASHBACK DATABASE TO SCN 123456789;
~~~

Or:

~~~sql
FLASHBACK DATABASE TO TIMESTAMP
TO_TIMESTAMP('2026-11-14 01:30:00',
             'YYYY-MM-DD HH24:MI:SS');
~~~

After Flashback Database, OPEN RESETLOGS is normally required to open the database into a new incarnation per procedure. Verify recovery instructions and database state before opening.

### 9.8. Flashback Database is not a single-table rollback

Flashback Database rewinds the database to a consistent milestone. It does not select one table to rewind while keeping every other object in the present.

If only one table is affected, evaluate:
- Flashback Query/Versions Query to reconstruct rows.
- Flashback Table if the whole table can revert.
- Flashback Drop if the object was DROPped.
- RMAN RECOVER TABLE if recovering just that table from backups is needed.

### 9.9. After OPEN RESETLOGS

Once the database opens:
- Confirm database open mode and incarnation.
- Check PDBs/services.
- Verify data and schemas.
- Run application smoke tests.
- Evaluate post-milestone transactions that were discarded.
- Review backup strategy and take a new backup per policy after opening a new incarnation.
- Verify Data Guard, replication, and downstream consumers per runbook.

Never allow applications to write new data until the DBA confirms recovery integrity.

### 9.10. Dropping the restore point once the release is stable

~~~sql
DROP RESTORE POINT before_release_2026_11_14;
~~~

Drop only after the rollback window ends and the owner approves. For guaranteed restore points, dropping allows Oracle to reuse flashback logs held specifically for that milestone.

## 10. RMAN Point-in-Time Recovery

### 10.1. When is RMAN PITR needed?

RMAN PITR is the choice when:
- Flashback logs do not cover the required recovery point.
- Flashback Database was not enabled or does not meet prerequisites.
- Recovery from backups is required.
- Recovery at database/tablespace/PDB/table scope is needed using RMAN-supported techniques.
- Physical corruption occurred or datafiles need restore/recover.

RMAN PITR requires suitable backups and continuous archived redo up to the target milestone. If required backups or logs are missing, recovery may be unable to reach the desired SCN.

### 10.2. Database point-in-time recovery

General pattern:

~~~text
RMAN> SHUTDOWN IMMEDIATE;
RMAN> STARTUP MOUNT;
RMAN> RUN {
  SET UNTIL SCN 123456789;
  RESTORE DATABASE;
  RECOVER DATABASE;
}
RMAN> SQL 'ALTER DATABASE OPEN RESETLOGS';
~~~

Actual syntax and preparation steps depend on control files, catalog, backup location, incarnation, encryption, and architecture. Verify backups/archivelogs first, ensure the target SCN lies within the recoverable range, and plan for Data Guard/standbys.

### 10.3. Tablespace point-in-time recovery

If only a single tablespace needs to rewind, RMAN TSPITR can recover that tablespace to a point in time without rewinding the entire database. Oracle uses an auxiliary instance to recover and plug the tablespace back in.

TSPITR has dependency limitations:
- Objects with cross-tablespace references.
- Indexes/LOBs/partitions and dependent objects.
- Undo/system tablespaces and tablespaces that cannot be recovered via standard TSPITR.
- Referential integrity and consistency between the recovered tablespace and the rest of the database.

Never pick TSPITR merely because its scope is smaller than database PITR; identify dependencies and verify consistency.

### 10.4. RMAN RECOVER TABLE

Oracle 19c supports RMAN table recovery to restore a table or partition to a point in time, using an auxiliary database/instance during processing and then importing the recovered object into the target database.

Illustrative example:

~~~text
RMAN> RECOVER TABLE HR.EMPLOYEES
      UNTIL SCN 123456789
      AUXILIARY DESTINATION '/u01/rman_aux'
      REMAP TABLE 'HR'.'EMPLOYEES':'EMPLOYEES_RECOVERED';
~~~

The auxiliary path must exist with adequate space and permissions. Exact syntax may require adding OF PLUGGABLE DATABASE if the table resides in a PDB. Verify syntax in the RMAN Reference for your running release.

Recovering to a new name is generally safer for inspecting data before replacing the live table. Afterward, address grants, synonyms, constraints, indexes, triggers, and application dependencies.

### 10.5. RMAN PITR vs. Flashback Database

| Criterion | Flashback Database | RMAN database PITR |
| --- | --- | --- |
| Primary recovery source | Flashback logs and required redo | Backups and archived redo |
| Pre-incident preparation | Flashback Database/restore point | Backup and archive log policy |
| Recovery duration | Usually faster while flashback logs remain | Depends on restore size and redo apply |
| Scope | Database-wide (or supported scopes such as PDB) | Database/tablespace/PDB/table depending on technique |
| Post-recovery impact | Opened via RESETLOGS procedure as needed | PITR typically requires OPEN RESETLOGS |
| Limitations | Missing logs, FRA pressure, wide blast radius | Missing backups/archivelogs, auxiliary storage, recovery time |
| Best suited for | Fast rewind to recent milestone with flashback logs | Recovering from backups or finer-grained scopes |

RMAN can serve as a method to recover a specific table without rewinding the entire database. Flashback Database is typically convenient when a restore point exists and rewinding the whole database is acceptable.

## 11. Truncate, Drop, DDL, and key limitations

### 11.1. DELETE vs. TRUNCATE

DELETE is DML and generates undo for deleted rows. If sufficient undo remains, Flashback Query/Table can read or restore the data.

TRUNCATE is DDL:
- Performs an implicit commit.
- Does not generate row-level undo to restore truncated contents via Flashback Table.
- Cannot be rolled back with ROLLBACK.
- Cannot use Flashback Table to revert to pre-TRUNCATE state.

If a table was truncated by mistake:
1. Halt further modifications to the table.
2. Identify the timestamp and SCN.
3. Check backups/archivelogs.
4. Use RMAN RECOVER TABLE if appropriate.
5. If single-table recovery is unfeasible, evaluate Flashback Database or PITR with a clearly understood blast radius.

### 11.2. DROP TABLE vs. DROP TABLE PURGE

DROP TABLE can place an object into the recycle bin if eligible. DROP TABLE PURGE bypasses the recycle bin or immediately purges the object from it.

- Standard DROP: try Flashback Drop.
- DROP PURGE: requires RMAN table recovery, PITR, or backup/export.
- Recycle bin already purged: Flashback Drop no longer has data to restore.

### 11.3. Structural DDL

Flashback Table has limitations when table structure changes after the target milestone. Operations such as TRUNCATE, MOVE, DROP COLUMN, or certain partition changes can render Flashback Table unusable as expected.

When a deployment includes multiple DDLs:
- Save pre-release schema state.
- Create a restore point or appropriate backup.
- Log every DDL step that succeeded.
- Identify which DDLs committed.
- Choose reverse migration, Flashback Database, or RMAN table recovery depending on scope.

Never assume Flashback Table can reverse arbitrary DDL.

### 11.4. Interleaved DML and DDL in a deployment

Migration example:
1. UPDATE normalizing data.
2. ALTER TABLE adding a column.
3. INSERT mapping data.
4. CREATE INDEX.
5. Script fails at the next step.

Rolling back a transaction cannot return the database before the entire migration because DDL implicitly committed. Determine:
- Which DML already committed.
- Which DDL completed.
- Which objects were created/altered.
- Which application version is currently running.
- Whether new data arrived after the migration.

You may need reverse migration for schema, compensating DML for data, or Flashback Database if reverting the entire database before deployment.

## 12. Sample scenario: accidental DELETE of committed orders

### 12.1. Stop the impact and identify the milestone

Suppose an application mistakenly deleted order_id 9001 and 9002, and the transaction COMMITted around 01:30. Pause any related job that might keep updating those rows. Obtain the SCN near the error time and confirm via logs.

### 12.2. Inspect data before DELETE

~~~sql
SELECT order_id,
       customer_id,
       status,
       total_amount
FROM   orders AS OF TIMESTAMP
       TO_TIMESTAMP('2026-11-14 01:29:00',
                    'YYYY-MM-DD HH24:MI:SS')
WHERE  order_id IN (9001, 9002);
~~~

Check the output and related keys. If sufficient undo no longer remains, the query may fail; switch to RMAN recovery.

### 12.3. Inspect current data

~~~sql
SELECT order_id,
       customer_id,
       status,
       total_amount
FROM   orders
WHERE  order_id IN (9001, 9002);
~~~

If no rows remain, that matches expectations after DELETE. If a row was recreated or has newer data, investigate before INSERTing.

### 12.4. Controlled recovery

You can INSERT the verified rows from Flashback Query:

~~~sql
INSERT INTO orders (
    order_id,
    customer_id,
    status,
    total_amount
)
SELECT old_row.order_id,
       old_row.customer_id,
       old_row.status,
       old_row.total_amount
FROM   orders AS OF SCN 123456789 old_row
WHERE  old_row.order_id IN (9001, 9002)
AND    NOT EXISTS (
           SELECT 1
           FROM orders current_row
           WHERE current_row.order_id = old_row.order_id
       );
~~~

This is an illustrative example only. Real tables may have additional NOT NULL columns, identity columns, audit columns, triggers, or child tables. Verify all dependencies and restore child rows in foreign key order.

### 12.5. Verification

- Check the number of INSERTed rows.
- Compare business columns with the historical version.
- Verify foreign keys and child tables.
- Confirm no duplicates or side effects were introduced.
- Run business queries and smoke tests.
- Record the recovery transaction and approver.

## 13. Sample scenario: mistaken UPDATE of one column across an entire table

### 13.1. Determine scope

Suppose a script ran:

~~~sql
UPDATE customers
SET    credit_limit = 0;
COMMIT;
~~~

instead of updating only a subset of customers. If the table has millions of customers and valid updates occurred afterward, Flashback Table would rewind the entire table and erase those newer changes.

### 13.2. Find prior versions

~~~sql
SELECT versions_startscn,
       versions_endscn,
       versions_operation,
       versions_xid,
       customer_id,
       credit_limit
FROM   customers
       VERSIONS BETWEEN SCN 123456000 AND 123456900
WHERE  credit_limit = 0
ORDER  BY customer_id, versions_startscn;
~~~

Actual queries must use a predicate that isolates erroneously updated rows. Do not rely solely on credit_limit = 0 if 0 is also a valid value.

### 13.3. Build a staging set before repairing

~~~sql
CREATE TABLE customers_repair_stage AS
SELECT customer_id,
       credit_limit AS old_credit_limit
FROM   customers AS OF SCN 123456789
WHERE  customer_id IN (
    SELECT customer_id
    FROM customers
    WHERE credit_limit = 0
);
~~~

This example must be refined to identify the exact erroneous row set. Never build staging with a broad predicate that sweeps in valid rows.

### 13.4. Compensating UPDATE

After verifying staging and confirming each key:

~~~sql
UPDATE customers c
SET    credit_limit = (
           SELECT s.old_credit_limit
           FROM customers_repair_stage s
           WHERE s.customer_id = c.customer_id
       )
WHERE  EXISTS (
           SELECT 1
           FROM customers_repair_stage s
           WHERE s.customer_id = c.customer_id
       );
~~~

Before COMMITting, verify affected row count and new values. If incorrect, ROLLBACK. Note that if the table received valid updates after the milestone, define a merge policy rather than overwriting whole rows.

## 14. Sample scenario: failed deployment after DDL

### 14.1. Before deployment

For high-risk releases:
- Verify the latest backup and restore capability.
- Create a restore point (guaranteed if FRA is sized and fast rewind is required).
- Record SCN and timestamp.
- Save schema metadata, grants, and dependencies.
- Prepare migration/reverse migration scripts.
- Define rollback criteria and decision cutoff times.

Example:

~~~sql
CREATE RESTORE POINT before_app_release
GUARANTEE FLASHBACK DATABASE;
~~~

Ensure the FRA has enough free space and monitoring is active before creating a guaranteed restore point.

### 14.2. Deployment fails midway

Do not immediately rerun the entire script. Record:
- Which steps succeeded.
- Which steps failed.
- Which DDLs committed.
- Which DMLs committed.
- Whether the application has started writing data under the new schema.
- Whether new requests/transactions arrived after the release milestone.

### 14.3. Choosing a rollback strategy

- If only one table had bad DML and schema is unchanged: Flashback Query/compensating DML or Flashback Table.
- If a table was DROPped and remains in the recycle bin: Flashback Drop.
- If TRUNCATE or DDL cannot be reversed locally: RMAN RECOVER TABLE or broader recovery.
- If the entire database must return before the release and losing post-milestone transactions is acceptable: Flashback Database to restore point.
- If sufficient flashback logs do not exist: RMAN PITR from backups/archivelogs.

### 14.4. Avoiding loss of valid post-release transactions

If the application continued accepting requests after a faulty deployment, Flashback Database will discard database changes made after the restore point. Before rewinding:
- Stop or drain the application.
- Identify transactions generated after the milestone.
- Export/stage data that must be kept if possible.
- Define how to replay/compensate once the database is flashbacked.
- Announce downtime and check downstream systems.

Never flashback the entire database without evaluating the impact on newer transactions.

### 14.5. Post-recovery

- Verify schema version.
- Check object validity and invalid objects.
- Verify business data.
- Check grants, synonyms, jobs, and triggers.
- Verify application compatibility.
- Run smoke tests and reconciliation.
- Take backups per policy after incarnation changes if RESETLOGS was used.
- Reopen traffic only after owner approval.

## 15. Restore points as part of the release process

### 15.1. Normal vs. guaranteed restore points

| Characteristic | Normal restore point | Guaranteed restore point |
| --- | --- | --- |
| Stores name and SCN | Yes | Yes |
| Guarantees retaining flashback logs to milestone | No | Yes, while restore point exists |
| FRA consumption | Does not hold logs separately like guaranteed point | Can grow substantially |
| Best suited for | Convenient milestone marker | Short rollback window with strict guarantee |
| Post-release management | Can drop when unneeded | Must drop on schedule to release retained logs |

### 15.2. Release workflow with restore points

1. Confirm the database is in a supported mode.
2. Check FRA usage and free space.
3. Define the retention period.
4. Create a restore point named after the release.
5. Record SCN/time in the change record.
6. Execute the deployment.
7. Run smoke tests, validation, and monitoring.
8. If the release fails, decide on Flashback Database accounting for post-milestone transactions.
9. If the release succeeds, keep the restore point until the rollback window closes, then drop it.
10. Check the FRA after dropping.

### 15.3. Never keep guaranteed restore points indefinitely

Guaranteed restore points can cause flashback logs to keep filling the FRA. If the FRA fills up, archiving/backups/flashback operations can be disrupted. Attach an owner, expiry time, and alerts to every restore point.

## 16. Data Guard, RAC, and multitenant

### 16.1. Data Guard

In Data Guard environments, Flashback Database and PITR can affect standbys or require resynchronization. After OPEN RESETLOGS, the database incarnation changes and standbys must be handled according to the appropriate Data Guard procedure.

Never apply standalone single-instance procedures on primary without evaluating:
- Standby role and apply lag.
- Flashback Database on primary/standby.
- Broker configuration.
- Reinstate/failover strategy.
- Redo transport and incarnation.

### 16.2. RAC

With RAC, database-wide recovery is a database-level operation, not a single-instance action. Coordinate shutdown/mount and reopening according to cluster/database procedures. Verify every instance and service after recovery.

### 16.3. CDB/PDB

Oracle 19c supports several PDB-scoped Flashback/PITR options depending on prerequisites and configuration. Determine:
- CDB root vs. PDB.
- Scope of the restore point.
- Whether the PDB uses local undo or shared undo per configuration.
- RMAN syntax and auxiliary destination.
- Impact on other PDBs and common objects.

Never run a CDB-wide command when the target is a single PDB if a suitable PDB recovery option exists. Consult the exact Oracle Multitenant/Backup and Recovery Guide.

## 17. Cases where Flashback does not replace backups

Flashback is great for recent logical errors, yet does not replace backups:
- Datafile lost or storage failed.
- Flashback logs/undo no longer remain.
- Table dropped with DROP PURGE and no longer in recycle bin.
- TRUNCATE or DDL unrecoverable via Flashback Table.
- Need to recover to a point farther back than retained Flashback data.
- Database lost control files or physical structures.
- Need an independent copy to inspect historical data.
- Need disaster recovery at another site.

RMAN backups, archived redo, control file autobackups, recovery catalog, and restore testing remain the foundation of recoverability.

## 18. Pre-recovery checklist

### Evidence and timeline

- [ ] Incident/change ID and accountable owner assigned.
- [ ] Type of erroneous operation identified.
- [ ] Target timestamp or SCN determined.
- [ ] Application/audit/deployment logs cross-checked.
- [ ] Valid post-milestone transactions identified.

### Technical prerequisites

- [ ] ARCHIVELOG, FLASHBACK_ON, and FRA checked.
- [ ] Undo retention checked if using Flashback Query/Table.
- [ ] Recycle bin checked if using Flashback Drop.
- [ ] Backups and archived redo checked if using RMAN.
- [ ] CDB/PDB, RAC, and Data Guard context identified.
- [ ] Privileges and exact release syntax verified.

### Scope and plan

- [ ] Blast radius determined.
- [ ] Narrowest option meeting the objective selected.
- [ ] Current data preserved if reconciliation/replay is needed.
- [ ] Application stopped or drained when necessary.
- [ ] Validation and rollback/forward-fix prepared.
- [ ] Stakeholders and downtime communicated.

### Post-recovery

- [ ] Data and schema verified.
- [ ] Constraints/indexes/triggers/grants/dependencies checked.
- [ ] Application smoke tests passed.
- [ ] Downstream systems/standbys verified.
- [ ] New backup taken when required by procedure.
- [ ] Incident record logs SCN, commands, timing, and results.

## 19. Hands-on exercises

Use a dedicated test schema, non-sensitive data, and recoverable backups. Never test DROP/TRUNCATE or Flashback Database in production.

### Exercise 1 — Roll back a transaction

DELETE a row, inspect before COMMIT, then ROLLBACK. Confirm the row still exists.

### Exercise 2 — Flashback Query

UPDATE a row and COMMIT. Query AS OF SCN/TIMESTAMP to read the pre-change value.

### Exercise 3 — Versions Query

Update the same row multiple times. Use VERSIONS BETWEEN SCN to list operations, SCNs, and XIDs.

### Exercise 4 — Transaction Query

Retrieve the XID from versions query and query FLASHBACK_TRANSACTION_QUERY. Inspect UNDO_SQL without executing it automatically.

### Exercise 5 — Compensating DML

Use Flashback Query to obtain a row's old value. Stage, verify, and run a compensating UPDATE inside a rollback-capable transaction.

### Exercise 6 — Flashback Table

Enable row movement, update multiple rows, record the SCN, then run FLASHBACK TABLE. Compare before/after data and note which valid changes were reverted.

### Exercise 7 — Flashback Drop

Create a test table, DROP without PURGE, inspect USER_RECYCLEBIN, then run FLASHBACK TABLE TO BEFORE DROP.

### Exercise 8 — Drop and purge

Create a second test table, run DROP TABLE PURGE. Confirm Flashback Drop is no longer available and plan RMAN recovery.

### Exercise 9 — Truncate

TRUNCATE a test table that has a suitable backup. Try Flashback Table to observe its limitation, then recover using RMAN RECOVER TABLE in the test environment.

### Exercise 10 — Normal restore point

Create a normal restore point, query V$RESTORE_POINT, then drop the restore point after finishing.

### Exercise 11 — Guaranteed restore point

In a test database with a sufficiently large FRA, create a guaranteed restore point. Monitor V$FLASHBACK_DATABASE_LOG and FRA usage; drop the restore point after the exercise.

### Exercise 12 — Flashback Database

Create a restore point before test changes, introduce identifiable changes, flashback the database per runbook, and verify state after OPEN RESETLOGS.

### Exercise 13 — RMAN table recovery

Use test schema backups/archived redo to RECOVER TABLE to an SCN before a delete or truncate. Recover to a new name and inspect dependencies.

### Exercise 14 — Selecting an option

Simulate three incidents: accidental DELETE of a few rows, accidental TRUNCATE of a table, and a failed DDL deployment. For each incident, state the milestone, scope, method, prerequisites, blast radius, and verification steps.

## 20. Oracle reference documentation

- [Oracle Database 19c SQL Language Reference — SELECT / Flashback Query](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): AS OF SCN/TIMESTAMP and Versions Query.
- [Oracle Database 19c SQL Language Reference — FLASHBACK TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/FLASHBACK-TABLE.html): restoring tables to an SCN, timestamp, or before DROP.
- [Oracle Database 19c SQL Language Reference — FLASHBACK DATABASE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/FLASHBACK-DATABASE.html): Flashback Database syntax.
- [Oracle Database Backup and Recovery User's Guide 19c — Flashback Database](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/using-flasback-database.html): configuring and operating Flashback Database.
- [Oracle Database Backup and Recovery User's Guide 19c — Performing Flashback and Database Point-in-Time Recovery](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/performing-flashback-dbpitr.html): choosing and executing Flashback/PITR.
- [Oracle Database Backup and Recovery User's Guide 19c — Recovering Tables and Table Partitions](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/rman-recovering-tables-partitions.html): RMAN table recovery.
- [Oracle Database Administrator's Guide 19c — Managing Tables](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-tables.html): recycle bin and table management.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_FLASHBACK](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_FLASHBACK.html): Flashback APIs and transaction-related operations.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_FLASHBACK_ARCHIVE](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_FLASHBACK_ARCHIVE.html): managing Flashback Data Archive.
- [Oracle Database Reference — V$RESTORE_POINT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-RESTORE_POINT.html): restore point metadata.
- [Oracle Database Reference — V$FLASHBACK_DATABASE_LOG](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-FLASHBACK_DATABASE_LOG.html): flashback log range and sizing.

How you recover from accidental deletes, mistaken updates, or failed deployments depends on COMMIT status, operation type, timestamp, and the scope of data to revert. Use ROLLBACK for uncommitted transactions; use Flashback Query/Versions to read and reconstruct older data; use Flashback Table when reverting the entire table is acceptable; use Flashback Drop for objects still in the recycle bin; use Flashback Database when rewinding the entire database is acceptable; and use RMAN PITR when recovering from backups or at table/tablespace/database scope. **Choose the option with the smallest blast radius that meets the goal, preserve valid changes, and verify data before reopening the application.**
