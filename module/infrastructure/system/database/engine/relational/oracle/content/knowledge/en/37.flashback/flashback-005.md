# FLASHBACK TABLE, Row Movement, and Dependency Limitations in Oracle Database

FLASHBACK TABLE allows you to return one or more tables to their data state at a past timestamp or SCN without restoring the entire database. It is useful when users accidentally delete or update data, a batch job writes erroneous rows, or an application produces unexpected modifications.

To perform this operation, Oracle requires the older data versions to still be available in undo. The table must also allow row movement. During flashback, Oracle may change the physical locations of rows, so ROWIDs can change. Tables with foreign key relationships, triggers, indexes, and dependent materialized views must be evaluated before recovery.

FLASHBACK TABLE is a table-level data recovery operation. It does not recover the entire database, does not reverse all DDL changes, and does not replace backups. In particular, flashbacking a single table on its own can introduce inconsistencies with parent/child tables or external systems if dependencies are not handled at the same point in time.

Using Oracle Database 19c as the reference baseline, this lesson explains the mechanism, prerequisites, row movement, using TO SCN/TO TIMESTAMP, multi-table recovery, effects on triggers/indexes/constraints, limitations, common errors, and a controlled recovery workflow.

## 1. What is FLASHBACK TABLE used for?

### 1.1. Restoring table data to a prior point in time

Suppose an application accidentally executes:

~~~sql
UPDATE hr.employees
SET    salary = salary * 10;
~~~

If no other transaction has modified the data in a way that prevents reversal, the administrator can use Flashback Table to return the table to its state prior to the erroneous statement, provided the required undo still exists.

Another example is a user mistakenly deleting a group of rows:

~~~sql
DELETE FROM orders
WHERE  order_date < DATE '2024-01-01';
COMMIT;
~~~

After COMMIT, ROLLBACK cannot undo that transaction. FLASHBACK TABLE can restore the table state prior to the DELETE if prerequisites and limitations are satisfied.

### 1.2. Flashback Table is not backup/restore

| Mechanism | Scope | Goal |
| --- | --- | --- |
| ROLLBACK | Current uncommitted transaction | Cancel changes of the transaction |
| Flashback Query | Query data in the past | Inspect row versions |
| Flashback Versions Query | View row version history over a range | Investigate changes |
| Flashback Transaction Query | View transaction details that changed data | Find SQL/transactions behind changes |
| FLASHBACK TABLE | Return data of one or more tables to an earlier time | Recover tables |
| Flashback Drop | Recover a DROPped table still in the recycle bin | Reclaim dropped objects |
| Flashback Database | Return the database to an earlier SCN/timestamp | Database-wide recovery |
| RMAN restore/recover | Restore/recover datafiles/database from backups and redo | Recover when backups are needed |

FLASHBACK TABLE is suitable when the incident scope is limited to one or a group of tables and sufficient undo remains. If the database has broad corruption, or if you must recover DDL, datafiles, or changes beyond the undo window, evaluate Flashback Database or RMAN.

### 1.3. Data is restored, not historical table structure

FLASHBACK TABLE primarily restores row contents. It is not a mechanism to revert a table definition to an older DDL version.

Examples:
- Mistaken UPDATE/DELETE/INSERT: potentially suitable.
- Column structure changes, truncate, or DDLs altering the object: may make flashbacking prior to that operation unfeasible.
- DROP TABLE: use Flashback Drop if the object remains in the recycle bin, or an appropriate backup/recovery method.

Always determine the exact time and type of erroneous operation before selecting a recovery mechanism.

## 2. Mechanism and recovery data source

### 2.1. Undo provides older data versions

Oracle stores undo records to support rollback and read consistency. FLASHBACK TABLE uses undo information to reconstruct row states at the target SCN or timestamp.

This means:
- Required undo must still be available.
- Queries or flashback operations targeting too far back may fail with snapshot errors or snapshot-not-found errors.
- Undo retention and undo capacity affect recoverability.
- Heavy DML workloads can overwrite older undo faster than expected if space is insufficient.

Do not treat UNDO_RETENTION as an absolute guarantee in every configuration. Check tablespace state, retention policy, and actual workload.

### 2.2. Flashback Table generates new changes

When returning a table to the past, Oracle performs the changes required to restore row states. This recovery work is itself database work, generating redo/undo and consuming CPU/I/O.

After flashback:
- Changes made after the target time are removed from the restored table state.
- Data returns to its state at the target point.
- Flashback changes constitute a new operation in the database's history.
- Other transactions or systems outside the database are not automatically reversed.

Check the impact on redo generation, standby/replication, audit trails, and applications.

### 2.3. SCN and timestamp

An SCN (System Change Number) is the logical anchor Oracle uses to order database changes. A timestamp is human-readable, though it may need to be mapped to an SCN.

When multiple tables must be returned to the same consistent point, SCN is generally a clearer anchor. Record the SCN before starting a batch job or during investigation whenever possible.

### 2.4. Why can't you flashback indefinitely into the past?

Undo is reused according to retention policies and space pressure. Once required row versions no longer exist, Oracle cannot reconstruct that state using FLASHBACK TABLE alone.

If recovery requirements exceed the undo window:
- Use backups/redo or Flashback Database if configured.
- Use data copies, exports, or audit trails to reconstruct the required portion.
- Consider point-in-time recovery at the appropriate scope.
- Do not repeatedly retry older timestamps once there is evidence that undo is gone.

## 3. Prerequisites and required privileges

### 3.1. Enabling row movement on the table

Before flashbacking, row movement must be enabled on the table:

~~~sql
ALTER TABLE hr.employees ENABLE ROW MOVEMENT;
~~~

If not enabled, the FLASHBACK TABLE statement typically fails with ORA-08189.

You can check the status:

~~~sql
SELECT table_name,
       row_movement
FROM   user_tables
WHERE  table_name = 'EMPLOYEES';
~~~

For another schema, use DBA_TABLES or ALL_TABLES depending on privileges:

~~~sql
SELECT owner,
       table_name,
       row_movement
FROM   dba_tables
WHERE  owner = 'HR'
AND    table_name = 'EMPLOYEES';
~~~

ROW_MOVEMENT typically displays ENABLED or DISABLED.

### 3.2. FLASHBACK privileges

The executor needs appropriate privileges:
- FLASHBACK object privilege on the table, or
- FLASHBACK ANY TABLE system privilege to flashback tables within allowed scope.

Beyond the FLASHBACK privilege, Oracle requires the object privileges needed to access and modify the table, such as SELECT, INSERT, DELETE, and ALTER per Flashback Table privilege rules. The table owner generally holds the required privileges on their own objects.

Example DBA granting object privileges to a recovery operator:

~~~sql
GRANT FLASHBACK ON hr.employees TO recovery_operator;
GRANT SELECT, INSERT, DELETE, ALTER
ON hr.employees TO recovery_operator;
~~~

Grant minimal privileges on the specific objects. Do not grant FLASHBACK ANY TABLE or DBA merely for a one-off run when object privileges suffice.

### 3.3. Sufficient undo must remain

Before executing, verify:
- Target time/SCN.
- Undo tablespace and datafile status.
- Current UNDO_RETENTION.
- Undo generation rate during peak hours.
- Active long-running transactions/queries.
- Whether retention guarantee is enabled.
- Whether sufficient free space exists for recovery and ongoing workload.

View configuration:

~~~sql
SHOW PARAMETER undo;
~~~

Or:

~~~sql
SELECT name,
       value
FROM   v$parameter
WHERE  name IN ('undo_management', 'undo_tablespace', 'undo_retention');
~~~

### 3.4. No incompatible DDL within the recovery interval

FLASHBACK TABLE cannot reconstruct a table structure that changed after the target time. Operations such as TRUNCATE or table definition changes can prevent flashbacking prior to that operation.

If DDL is suspected:
- Check audit trails or application deployment logs.
- Identify the time of the DDL.
- Inspect object metadata and test errors on a clone/test environment.
- Choose Flashback Drop, Flashback Database, or RMAN if appropriate.

Do not test-run flashback in production without verifying DDL boundaries first.

### 3.5. The table must be of a supported type

Oracle imposes restrictions by object type, structure, and dependencies. For example, special tables such as clustered tables or unsupported structures may not support standard flashback.

Before running on complex tables, review the Restrictions section of the SQL Language Reference for your exact release. Do not assume every object listed in DBA_TABLES can be flashbacked.

## 4. ROW MOVEMENT — meaning and impact

### 4.1. What is row movement?

In Oracle, a row has a ROWID identifying its physical location. Certain operations require a row to move to a different physical location. Row movement allows Oracle to change a row's ROWID when necessary.

Flashback Table needs the ability to relocate rows to reconstruct prior states, so it requires ENABLE ROW MOVEMENT.

### 4.2. Enabling row movement does not immediately move all rows

~~~sql
ALTER TABLE hr.employees ENABLE ROW MOVEMENT;
~~~

This statement enables row movement capability for the table. It does not automatically scan and relocate all existing rows.

Row movement can be used by operations such as Flashback Table, segment shrink, or certain partition key updates. Exact behavior depends on the table type and operation.

### 4.3. ROWIDs can change

When flashback or another operation moves rows, a row's ROWID may differ from before. Therefore:
- Do not store ROWIDs long-term as business keys.
- Do not use ROWIDs as foreign keys across tables.
- Do not assume a row's ROWID stays constant after flashback.
- If an application caches ROWIDs, refresh the cache after recovery.

ROWID is useful for physically locating a row at query time, not as a stable business identifier.

### 4.4. Checking and changing row movement status

Check status:

~~~sql
SELECT owner,
       table_name,
       row_movement
FROM   dba_tables
WHERE  owner = 'HR'
AND    table_name = 'EMPLOYEES';
~~~

Enable:

~~~sql
ALTER TABLE hr.employees ENABLE ROW MOVEMENT;
~~~

Disable afterward if required by design policy:

~~~sql
ALTER TABLE hr.employees DISABLE ROW MOVEMENT;
~~~

You do not always have to disable it immediately after flashback. If the application or another process requires row movement, leave it ENABLED. If you want to restrict row relocation, confirm no dependent operation relies on it before disabling.

### 4.5. Row movement and partitioned tables

For partitioned tables, row movement may be required when updating a partition key moves a row between partitions. Row movement status therefore affects both partition operations and flashback.

Before changing it, review partition keys, partitioning strategy, local/global indexes, and application behavior. Do not habitually disable row movement if the table requires cross-partition row migration.

## 5. Flashback Table by TIMESTAMP

### 5.1. Basic syntax

~~~sql
FLASHBACK TABLE hr.employees
TO TIMESTAMP (SYSTIMESTAMP - INTERVAL '10' MINUTE);
~~~

This statement returns HR.EMPLOYEES to its data state 10 minutes prior to the current time. The table must satisfy privilege, row movement, undo, and object limitation requirements.

### 5.2. Using a fixed timestamp

~~~sql
FLASHBACK TABLE hr.employees
TO TIMESTAMP (
    TO_TIMESTAMP_TZ(
        '2026-11-14 19:30:00 +07:00',
        'YYYY-MM-DD HH24:MI:SS TZH:TZM'
    )
);
~~~

This example uses a timestamp with an explicit time zone. Replace the timestamp with the point verified from incident logs and confirm application/database time zones before executing.

Do not use a rough estimate like "about 10 minutes ago" for production recovery if an exact SCN from traces or investigation procedures is available.

### 5.3. Using a relative timestamp

Some test scenarios may use:

~~~sql
FLASHBACK TABLE hr.orders
TO TIMESTAMP (SYSTIMESTAMP - INTERVAL '30' MINUTE);
~~~

A relative timestamp depends on when the statement is executed. When preparing multiple steps or flashbacking multiple tables, determine and record a single shared anchor beforehand.

### 5.4. Pre-execution checks

Before running, verify:
- Timestamp uses the right time zone.
- Target time lies within the available undo window.
- The table has not undergone incompatible DDL.
- Row movement is ENABLED.
- Related tables have been identified.
- No concurrent transactions/applications are modifying the same data.
- A backup/restore plan exists if flashback cannot meet requirements.

## 6. Flashback Table by SCN

### 6.1. Syntax

~~~sql
FLASHBACK TABLE hr.employees
TO SCN 123456789;
~~~

SCN is a specific logical anchor. The number above is illustrative only; use a real SCN from the database or incident record.

### 6.2. Getting the current SCN

~~~sql
SELECT current_scn
FROM   v$database;
~~~

Or using PL/SQL:

~~~sql
DECLARE
    l_scn NUMBER;
BEGIN
    l_scn := DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER;
    DBMS_OUTPUT.PUT_LINE('Current SCN = ' || l_scn);
END;
/
~~~

Record the SCN before an incident if the system has a snapshot/incident marker workflow. A current SCN captured after an incident does not represent the recovery point.

### 6.3. Converting timestamp to SCN

Oracle provides a function to map timestamp to SCN:

~~~sql
SELECT TIMESTAMP_TO_SCN(
           SYSTIMESTAMP - INTERVAL '10' MINUTE
       ) AS target_scn
FROM dual;
~~~

SCN_TO_TIMESTAMP performs the reverse within the retained mapping range. Timestamp/SCN mapping has finite resolution and retention; do not treat it as an exact conversion for arbitrary old timestamps.

~~~sql
SELECT SCN_TO_TIMESTAMP(123456789)
FROM dual;
~~~

### 6.4. When should you choose SCN?

SCN is appropriate when:
- Multiple tables must be flashbacked to the exact same point.
- Correlating against transaction/redo/incident records.
- Recording an unambiguous recovery anchor.
- Avoiding time zone confusion or timestamp precision issues.

Timestamps are convenient to read, while SCNs are generally better for cross-object consistency.

## 7. Flashbacking multiple tables and dependency relationships

### 7.1. Why shouldn't you flashback tables individually at random?

Suppose there are two tables:
- DEPARTMENTS is the parent table.
- EMPLOYEES contains DEPARTMENT_ID referencing DEPARTMENTS.

An incident deleting departments and employees can impact both tables. If you flashback only EMPLOYEES or only DEPARTMENTS, the current state of the other table may conflict with the restored state.

For example:
- EMPLOYEES is reverted to a time when DEPARTMENT_ID = 50 existed.
- DEPARTMENTS currently no longer has department_id = 50.
- Foreign keys may be violated or business state becomes inconsistent.

Identify the full set of dependent tables and return them to the same SCN when needed.

### 7.2. Flashbacking multiple tables to the same SCN

Oracle supports flashbacking multiple tables in a single statement when corresponding conditions and restrictions are met:

~~~sql
FLASHBACK TABLE hr.departments,
                hr.employees
TO SCN 123456789;
~~~

This example returns both tables to the same SCN. Substitute the table list and SCN for your actual system. Verify all tables have row movement enabled and sufficient privileges.

### 7.3. Foreign keys and referential integrity

Before flashbacking tables with foreign key relationships:
1. List parent and child tables.
2. Check whether foreign keys are enabled/validated.
3. Identify changes made after the target SCN.
4. Select the set of tables to flashback simultaneously.
5. Use the same SCN across related tables.
6. Verify constraints after the operation.

Do not disable constraints just to let the statement pass and then forget to revalidate them. If temporary disabling is required under an approved plan, include a plan to verify data and re-enable/revalidate them.

### 7.4. Inspecting foreign key dependencies

~~~sql
SELECT c.owner,
       c.table_name,
       c.constraint_name,
       c.r_owner,
       p.table_name AS parent_table,
       c.status,
       c.validated
FROM   dba_constraints c
JOIN   dba_constraints p
       ON p.owner = c.r_owner
      AND p.constraint_name = c.r_constraint_name
WHERE  c.constraint_type = 'R'
AND    (c.owner = 'HR' OR c.r_owner = 'HR')
ORDER  BY c.owner, c.table_name, c.constraint_name;
~~~

This query locates foreign keys on HR tables and tables referencing HR. For multi-schema systems, expand the filter according to actual object dependencies.

### 7.5. Checking constraints on a table

~~~sql
SELECT owner,
       table_name,
       constraint_name,
       constraint_type,
       status,
       validated,
       r_owner,
       r_constraint_name
FROM   dba_constraints
WHERE  owner = 'HR'
AND    table_name IN ('DEPARTMENTS', 'EMPLOYEES')
ORDER  BY table_name, constraint_type, constraint_name;
~~~

Before and after flashback, save constraint metadata for comparison. Constraints are not row data and do not revert to older definitions via Flashback Table.

### 7.6. Self-referencing foreign keys

A table can reference itself, such as EMPLOYEES.MANAGER_ID referencing EMPLOYEE_ID. When restoring rows, internal parent-child relationships within the same table must be consistent at the target SCN.

With self-references, flashbacking the entire table to the same SCN is generally the right scope compared to trying to restore a subset of rows individually. Check constraints after completion.

### 7.7. External relationships outside the database

Flashback Table does not reverse:
- Messages already sent to queues or other systems.
- Emails/notifications already dispatched.
- API calls made to external services.
- Files already written to a filesystem.
- Caches or search indexes in other systems.
- Data copies already exported to a data warehouse.

After flashback, reconciliation or application-level replay/compensation is required. Database state may rewind, yet external side effects persist.

## 8. Triggers, indexes, and dependent objects

### 8.1. Triggers during flashback

Triggers can produce additional changes whenever DML occurs. If triggers fire during flashback, they may cause unintended side effects or alter other data.

Flashback Table syntax includes the ENABLE TRIGGERS option. By default, triggers are not fired during Flashback Table; use ENABLE TRIGGERS only when you have confirmed which triggers must run and fully understand their side effects.

Example:

~~~sql
FLASHBACK TABLE hr.employees
TO SCN 123456789
ENABLE TRIGGERS;
~~~

Without a specific business requirement, do not enable triggers during recovery. After flashback, verify trigger status and application behavior.

### 8.2. Inspecting triggers

~~~sql
SELECT owner,
       trigger_name,
       table_owner,
       table_name,
       status,
       triggering_event,
       trigger_type
FROM   dba_triggers
WHERE  table_owner = 'HR'
AND    table_name = 'EMPLOYEES'
ORDER  BY trigger_name;
~~~

Check whether triggers write business audits, update other tables, enqueue messages, or invoke external packages. Review trigger code and dependencies before choosing ENABLE TRIGGERS.

### 8.3. Indexes are maintained

Oracle maintains associated indexes during Flashback Table so indexes reflect the post-recovery row state. Typically, rebuilding all indexes solely because of flashback is unnecessary.

Nevertheless, verify:
- Whether indexes are in VALID status.
- Whether index partitions have valid status.
- Whether any index was already unusable before the incident.
- Whether function-based/domain indexes or special structures require separate inspection.

### 8.4. Inspecting indexes

~~~sql
SELECT owner,
       index_name,
       table_owner,
       table_name,
       status,
       visibility,
       uniqueness
FROM   dba_indexes
WHERE  table_owner = 'HR'
AND    table_name = 'EMPLOYEES'
ORDER  BY index_name;
~~~

For partitioned indexes, also inspect DBA_IND_PARTITIONS and DBA_IND_SUBPARTITIONS. Do not run rebuilds without evidence of invalid indexes or a necessary maintenance plan.

### 8.5. Grants, synonyms, and views

Flashback Table restores rows; it is not a mechanism for restoring all object metadata. Grants, synonyms, views, and trigger/index definitions are not reverted to older versions solely by flashbacking data.

If DDL altered an object definition after the target time, Flashback Table may fail. If only data changed, existing object metadata is usually preserved; still verify object dependencies before reopening the application.

### 8.6. Materialized views

Materialized views depending on source tables can become stale after Flashback Table modifies data. Check refresh status and refresh according to an appropriate strategy before consumers use them again.

~~~sql
SELECT owner,
       mview_name,
       staleness,
       last_refresh_type,
       last_refresh_date
FROM   dba_mviews
WHERE  owner = 'REPORTING'
ORDER  BY mview_name;
~~~

Columns and query privileges vary by release. Do not assume materialized views automatically synchronize to the same state simply because the base table was flashbacked.

### 8.7. Constraints and triggers are not the only side effects

A table may be tied to:
- Foreign keys and check constraints.
- Triggers.
- Materialized views/logs.
- CDC/replication/GoldenGate.
- Change data capture or downstream ETL.
- Application caches and search indexes.
- Audit policies and application logs.

Build a dependency inventory before flashbacking, then confirm each system is synchronized afterward.

## 9. Limitations of FLASHBACK TABLE

### 9.1. DDL and structural changes

Flashback Table is not DDL time travel. If table structure changed since the target time, Oracle may be unable to interpret old undo against the current definition.

Examples of operations requiring special attention:
- TRUNCATE TABLE.
- DROP TABLE.
- Column definition changes.
- Certain MOVE/REDEFINITION or segment-restructuring operations.
- Partition/object changes affecting required metadata.

ORA-01466 typically indicates the table definition changed within the interval to be read. Check DDL history/audit/deployment logs and pick the right recovery method.

### 9.2. Truncate is not like DELETE

DELETE generates undo for deleted rows, so flashback is possible if sufficient undo remains.

TRUNCATE is DDL and does not generate row-by-row undo like DELETE. FLASHBACK TABLE cannot be used to undo TRUNCATE. Use Flashback Drop if an object was dropped, or Flashback Database or backup/recovery depending on the situation.

### 9.3. DROPped tables

FLASHBACK TABLE ... TO TIMESTAMP/SCN is not the syntax for recovering a dropped object. If the table remains in the recycle bin, see Flashback Drop:

~~~sql
FLASHBACK TABLE hr.orders
TO BEFORE DROP;
~~~

Flashback Drop has its own prerequisites depending on the recycle bin, object name, and available space. If the object was purged or not stored in the recycle bin, use backup/recovery.

### 9.4. Undo no longer available

If the target time exceeds available undo, errors such as ORA-01555 or ORA-08180 may occur. Increasing UNDO_RETENTION after an incident has happened cannot recreate undo records that were already reused.

For longer recovery requirements, design backups, Flashback Database, guaranteed restore points, or archiving/replication aligned with RPO requirements.

### 9.5. Clustered tables or special object types

Certain table/object types have Flashback Table restrictions. Check the Restrictions section in the Oracle Database 19c SQL Language Reference for the exact object type being handled, especially clustered tables, special nested/object structures, remote objects, or tables with complex relationships.

Do not generalize capabilities from a simple heap table to every table type in the database.

### 9.6. Locks and active transactions

Flashback Table must lock the restored tables to guarantee a consistent operation. Sessions holding DML locks or workloads continuously updating data can cause the operation to wait or fail.

Before running:
- Quiesce or pause application writers if possible.
- Identify open transactions.
- Notify consumers and batch jobs.
- Choose a maintenance window.
- Monitor locks/waits.
- Do not kill sessions indiscriminately.

### 9.7. Consistency boundary

Flashback Table restores tables within the database. It does not automatically revert:
- Sequences to older values.
- Audit trails to the past.
- Scheduler jobs or external jobs to older states.
- Files and object storage to an earlier point.
- Other caches/queues/services to the same SCN.

These components must be handled through separate reconciliation procedures.

## 10. Complete hands-on example

### 10.1. Create the demo table

~~~sql
CREATE TABLE flash_demo_accounts (
    account_id NUMBER PRIMARY KEY,
    owner_name VARCHAR2(100) NOT NULL,
    balance    NUMBER(12,2) NOT NULL
);
~~~

### 10.2. Load initial data

~~~sql
INSERT INTO flash_demo_accounts VALUES (1, 'An', 1000);
INSERT INTO flash_demo_accounts VALUES (2, 'Binh', 2000);
INSERT INTO flash_demo_accounts VALUES (3, 'Chi', 3000);
COMMIT;
~~~

### 10.3. Record the SCN before changes

~~~sql
SELECT current_scn
FROM   v$database;
~~~

Write down the SCN in your incident/test notes. Suppose the captured SCN is 123456789; this is an illustrative value only.

### 10.4. Enable row movement

~~~sql
ALTER TABLE flash_demo_accounts ENABLE ROW MOVEMENT;
~~~

### 10.5. Perform an erroneous change

~~~sql
UPDATE flash_demo_accounts
SET    balance = balance + 50000;

COMMIT;
~~~

Check:

~~~sql
SELECT *
FROM   flash_demo_accounts
ORDER  BY account_id;
~~~

### 10.6. Flashback to the recorded SCN

~~~sql
FLASHBACK TABLE flash_demo_accounts
TO SCN 123456789;
~~~

Replace the illustrative SCN with the real value captured before the change. The table must satisfy privilege, undo, and DDL-compatibility requirements.

### 10.7. Verify the data

~~~sql
SELECT *
FROM   flash_demo_accounts
ORDER  BY account_id;
~~~

Compare balances against the snapshot/test baseline. Verify row counts, constraints, and application checks before reopening traffic.

### 10.8. Clean up the demo table

~~~sql
DROP TABLE flash_demo_accounts PURGE;
~~~

Run this only in a test schema once the data is no longer needed. PURGE removes the object from the recycle bin, so never run it carelessly on real tables.

## 11. Workflow for recovering a table in production

### Step 1 — Isolate the incident

Identify:
- Affected table and schema.
- Time when erroneous changes began.
- SQL/transaction causing the change.
- Related tables.
- Whether any DDL, TRUNCATE, or DROP occurred in this interval.
- Which applications are writing data.

Do not choose the target time solely from when users reported the error. Identify the last known good state.

### Step 2 — Preserve evidence and current data

Before recovery:
- Record SQL_ID, transaction, audit records, and timestamps.
- Export/snapshot current data if reconciliation will be needed.
- Record the current SCN.
- Save constraint/index/trigger metadata.
- Confirm available backups/recovery points.
- Record row counts and key business identifiers.

A pre-flashback snapshot helps compare and reconstruct valid changes made after the target time if needed.

### Step 3 — Determine the target SCN/time

Use audit trails, application logs, transaction logs, or snapshots to pinpoint the anchor. When possible, use a specific SCN. Verify time zones if using a timestamp.

### Step 4 — Check undo and flashback feasibility

Inspect UNDO_RETENTION, V$UNDOSTAT, undo tablespace, and workload. If the target exceeds undo availability, stop pursuing Flashback Table and evaluate backups/Flashback Database.

### Step 5 — Verify row movement and privileges

Confirm ROW_MOVEMENT = ENABLED, FLASHBACK privilege, and object privileges. Record initial states to restore them if required.

### Step 6 — Check dependencies

Compile a list of:
- Parent/child FKs.
- Self-referencing FKs.
- Triggers.
- Indexes.
- Materialized views.
- Replication/CDC.
- Application caches/queues.
- Downstream systems.

Include all tables that must be flashbacked to the same SCN to preserve referential integrity.

### Step 7 — Stop or control writers

Quiesce writers, batch jobs, and services that could modify the table during recovery. Confirm active transactions have completed or been handled per runbook.

### Step 8 — Execute flashback

Run a single statement for the approved set of tables using the same SCN. Monitor duration, locks, redo, undo, and the alert log.

### Step 9 — Validation

Verify:
- Row counts and critical aggregates.
- Primary keys and foreign keys.
- Check constraints.
- Index status.
- Trigger status and side effects.
- Materialized view staleness.
- Audit trails.
- Replication/CDC.
- Application smoke tests.

### Step 10 — Reconcile valid changes

Valid changes made after the target time are also removed from the restored table state. Use snapshots/audits/application logs to identify what must be replayed or re-entered. Never copy data back blindly, as doing so can reintroduce the original error.

### Step 11 — Reopen the application

Reopen writers only after:
- Validation passes.
- Referential integrity is valid.
- Consumers/downstream systems are synchronized.
- Application owners accept the result.
- Monitoring and alerting are active.

### Step 12 — Document the incident

Record the target SCN, timestamp, executed commands, approver, validation results, reconciled data, and configuration changes such as row movement.

## 12. Common errors and troubleshooting

| Error/situation | Possible cause | Investigation step |
| --- | --- | --- |
| ORA-08189 | Row movement not enabled | Check DBA_TABLES.ROW_MOVEMENT and run ENABLE ROW MOVEMENT |
| ORA-08180 | No matching snapshot/SCN found | Check target time/SCN and undo availability |
| ORA-01555 | Required undo no longer exists | Review V$UNDOSTAT, query duration, DML rate, and retention |
| ORA-01466 | Table definition changed within the interval | Check DDL history, truncate/move/alter, and choose another recovery method |
| ORA-02292 or constraint error | Restored state violates data relationships | Flashback related tables to the same SCN and verify FKs |
| ORA-00054 or lock waits | Object is locked by another session | Check V$LOCK/V$SESSION and quiesce writers per runbook |
| Insufficient privileges | Missing FLASHBACK/object privilege or table operation rights | Grant minimal required privileges |
| Flashback lacks expected records | Wrong target time or undo expired | Verify timestamp/time zone/SCN and other log sources |
| Materialized view stale | Source table changed after flashback | Check DBA_MVIEWS and refresh appropriately |

Specific error codes and messages depend on the operation, object, and release. When encountering an error, capture the full stack and SQL, and consult Oracle Database Error Messages rather than acting solely on the error name.

### 12.1. ORA-08189 — row movement not enabled

Check:

~~~sql
SELECT owner,
       table_name,
       row_movement
FROM   dba_tables
WHERE  owner = 'HR'
AND    table_name = 'EMPLOYEES';
~~~

If approved, enable:

~~~sql
ALTER TABLE hr.employees ENABLE ROW MOVEMENT;
~~~

Then confirm privileges, target time, and undo before retrying.

### 12.2. ORA-01555/ORA-08180 — required version no longer available

Do not repeat the same statement with an older timestamp. Assess remaining undo availability and consider backups/Flashback Database. Increasing UNDO_RETENTION after undo has been overwritten cannot recover lost versions.

### 12.3. Constraint violation

If the table has FKs:
- Identify parent/child direction.
- Check constraint status.
- Verify data at the target SCN.
- Flashback the necessary set of tables to the same SCN.
- Validate constraints before reopening the application.

Do not drop constraints and forget to re-enable them. If temporary disabling is unavoidable, record the owner, initial state, and restoration commands.

## 13. Post-Flashback Table checks

### 13.1. Check row counts

~~~sql
SELECT COUNT(*) AS row_count
FROM   hr.employees;
~~~

Compare against the baseline—do not rely solely on row count, as counts may match while contents differ.

### 13.2. Check keys and constraints

~~~sql
SELECT constraint_name,
       constraint_type,
       status,
       validated
FROM   dba_constraints
WHERE  owner = 'HR'
AND    table_name = 'EMPLOYEES'
ORDER  BY constraint_type, constraint_name;
~~~

If related tables exist, verify the entire FK chain.

### 13.3. Check indexes

~~~sql
SELECT index_name,
       status,
       visibility,
       uniqueness
FROM   dba_indexes
WHERE  table_owner = 'HR'
AND    table_name = 'EMPLOYEES'
ORDER  BY index_name;
~~~

For partitioned indexes, check each partition/subpartition status.

### 13.4. Check triggers

~~~sql
SELECT trigger_name,
       status,
       triggering_event
FROM   dba_triggers
WHERE  table_owner = 'HR'
AND    table_name = 'EMPLOYEES'
ORDER  BY trigger_name;
~~~

Ensure triggers are in the expected state and side effects are controlled.

### 13.5. Check row movement

~~~sql
SELECT row_movement
FROM   dba_tables
WHERE  owner = 'HR'
AND    table_name = 'EMPLOYEES';
~~~

Decide whether to keep it ENABLED or DISABLED according to table design and future operations. Do not change it merely to "revert to the old state" if that state no longer fits the workload.

### 13.6. Check materialized views and downstream systems

Check staleness/refresh, replication lag, CDC checkpoints, cache invalidation, and exported data. Conduct reconciliation before declaring the whole system consistent.

## 14. Comparing Flashback Table with other Flashback mechanisms

| Mechanism | Data/object | When to use | Key limitations |
| --- | --- | --- | --- |
| Flashback Query | Query row versions | Inspect past data | Depends on undo |
| Flashback Versions Query | Row version history | Investigate who/what changed across available versions | Depends on undo and query limits |
| Flashback Transaction Query | Transactions and changing SQL | Find the faulty transaction | Needs transaction/undo data and appropriate privileges |
| FLASHBACK TABLE | One or more tables | Restore table data | Row movement, undo, DDL/dependency restrictions |
| Flashback Drop | DROPped table | Reclaim object from recycle bin | Object must still be in recycle bin |
| Flashback Database | Entire database | Rewind database to SCN/time | Requires flashback logging and storage configuration |
| RMAN | Datafiles/database | Recovery from backups and redo | Requires backups, archive logs, and restore procedure |

### 14.1. Flashback Query to preview

Before recovering, you can preview historical data using AS OF TIMESTAMP:

~~~sql
SELECT employee_id,
       first_name,
       salary
FROM   hr.employees
AS OF TIMESTAMP (SYSTIMESTAMP - INTERVAL '10' MINUTE)
WHERE  employee_id = 100;
~~~

This is a read-only query useful for confirming target data before running flashback DDL.

### 14.2. Flashback Versions Query to inspect row history

~~~sql
SELECT versions_startscn,
       versions_endscn,
       versions_operation,
       versions_xid,
       employee_id,
       salary
FROM   hr.employees
VERSIONS BETWEEN SCN 123456000 AND 123456789
WHERE  employee_id = 100;
~~~

The VERSIONS_* pseudocolumns show row versions within the still-available SCN range. They can be used to pinpoint the transaction under investigation.

### 14.3. Flashback Drop for dropped objects

~~~sql
FLASHBACK TABLE hr.employees
TO BEFORE DROP;
~~~

This syntax differs from TO SCN/TIMESTAMP. It restores a dropped table remaining in the recycle bin rather than reverting an existing table's data to an earlier time.

## 15. Hands-on exercises

Run hands-on exercises in a test schema with backups/snapshots and non-sensitive data. Never run recovery commands in production for experimentation.

### Exercise 1 — Enable row movement

Create a demo table, inspect USER_TABLES.ROW_MOVEMENT, run ENABLE ROW MOVEMENT, and verify again.

### Exercise 2 — Compare ROWIDs

Capture ROWIDs of rows before and after a flashback operation in a test environment. Observe why ROWID should not be used as a business key.

### Exercise 3 — Flashback by TIMESTAMP

Record the table state, execute an UPDATE and COMMIT, then flashback to the timestamp before the UPDATE. Compare the data.

### Exercise 4 — Flashback by SCN

Obtain the SCN from V$DATABASE or DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER before making changes. Perform DML, COMMIT, and flashback to the recorded SCN.

### Exercise 5 — Flashback Query before recovery

Use AS OF TIMESTAMP/SCN to preview target data. Verify the rows and values to restore.

### Exercise 6 — Test undo limits

Run a sufficiently large DML and keep a long-running query in test. Observe V$UNDOSTAT, attempt to read older versions, and note the impact of retention.

### Exercise 7 — ORA-08189

Create a table with row movement disabled, attempt flashback in test, and record the error. Enable row movement and retry.

### Exercise 8 — Parent/child relationships

Create two tables with a foreign key. Modify/delete data in both, then flashback both to the same SCN. Verify referential integrity.

### Exercise 9 — Self-referencing FK

Create an employees table where MANAGER_ID references EMPLOYEE_ID. Flashback the table to the same SCN and verify the hierarchy.

### Exercise 10 — Triggers

Create a business audit trigger on a demo table. Perform a default flashback and test ENABLE TRIGGERS in a test environment. Observe side effects and trigger status.

### Exercise 11 — Indexes and constraints

Create a primary key, unique index, and check constraint. Flashback the table, then verify index status and constraint validation.

### Exercise 12 — DDL and TRUNCATE

In a test schema, try DML followed by flashback; then try TRUNCATE and evaluate why Flashback Table cannot serve as undo for DDL.

### Exercise 13 — Materialized views

Create a materialized view depending on a demo table, flashback the source table, and check staleness/refresh status.

### Exercise 14 — Recovery runbook

Draft a flashback plan for a mistaken UPDATE incident: target SCN, dependent tables, undo, row movement, privileges, triggers, validation, reconciliation, and rollback/fallback.

## 16. Oracle reference documentation

- [Oracle Database 19c SQL Language Reference — FLASHBACK TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/FLASHBACK-TABLE.html): syntax, prerequisites, and restrictions of Flashback Table.
- [Oracle Database 19c SQL Language Reference — ALTER TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TABLE.html): ENABLE/DISABLE ROW MOVEMENT.
- [Oracle Database 19c Backup and Recovery User's Guide — Using Flashback Table and Flashback Drop](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/using-flasback-database-and-other-flashback-features.html): overview of Flashback features.
- [Oracle Database 19c Administrator's Guide — Managing Undo](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-undo.html): undo tablespace and retention.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_FLASHBACK](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_FLASHBACK.html): SCN and supported flashback operations.
- [Oracle Database Reference — DBA_TABLES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_TABLES.html): ROW_MOVEMENT and table metadata.
- [Oracle Database Reference — DBA_CONSTRAINTS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_CONSTRAINTS.html): constraint metadata and status.
- [Oracle Database Reference — DBA_TRIGGERS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_TRIGGERS.html): trigger status and events.
- [Oracle Database Reference — DBA_MVIEWS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_MVIEWS.html): materialized view status.

FLASHBACK TABLE can restore table data to an SCN or timestamp while required undo remains available and the object meets prerequisites. Row movement must be enabled, ROWIDs can change, parent/child tables must be processed at the same anchor to preserve data relationships, and triggers and dependent objects must be checked before and after the operation. **Identify the exact target SCN, inventory dependencies, control writers, flashback within the approved scope, and validate all related data before reopening the application.**
