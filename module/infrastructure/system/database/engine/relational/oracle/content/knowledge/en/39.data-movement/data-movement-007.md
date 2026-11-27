# Consistent Export Using FLASHBACK_SCN/FLASHBACK_TIME

When exporting a database with Oracle Data Pump, source data may continue changing while the job is running. Without defining a common snapshot point, tables can be read at different points in time. When related data is updated concurrently, the dump file can contain states that do not align to the same business point in time.

Data Pump Export provides two parameters to request reading data as of a historical point:

- **FLASHBACK_SCN:** exports data as of a specific System Change Number.
- **FLASHBACK_TIME:** exports data as of a timestamp; Data Pump determines the corresponding SCN to use as the flashback point.

These two parameters help create a consistent export of table data at the same snapshot, even while applications continue running INSERT, UPDATE, or DELETE during the export.

An important principle: FLASHBACK_SCN and FLASHBACK_TIME do not replace backups. They create a consistent logical snapshot for Data Pump Export. Physical database recovery after media failure still requires RMAN backups, archived redo logs, and an appropriate recovery procedure.

## 1. Why Is a Consistent Export Needed?

Suppose an order management application has two tables:

- ORDERS: order header information.
- ORDER_ITEMS: order line items.

A transaction creating an order might INSERT into both tables and then COMMIT:

~~~sql
INSERT INTO orders (order_id, customer_id, status)
VALUES (9001, 100, 'NEW');

INSERT INTO order_items (order_id, item_id, quantity)
VALUES (9001, 1, 2);

COMMIT;
~~~

While Data Pump exports, the application remains active. If ORDERS is exported before the transaction commits, yet ORDER_ITEMS is exported after the commit, the dump may not reflect the same logical point in time. The result could be ORDER_ITEMS having child rows while ORDERS lacks the parent row, or vice versa, depending on when each table was read and transaction states.

### 1.1 Statement-level read consistency vs. job-wide consistency

Oracle provides read consistency per SQL statement: a statement sees data as of a consistent snapshot at the time the statement began.

However, a Data Pump job can read many tables, partitions, and objects using multiple workers. Without fixing a snapshot for the job, the read timestamp of different parts of the data can vary.

Consistent export instructs Data Pump to use the exact same SCN to read table data:

~~~text
                   SCN = 123456789
                         |
          +--------------+--------------+
          |              |              |
          v              v              v
       ORDERS         ORDER_ITEMS    CUSTOMERS
          |              |              |
          +--------------+--------------+
                         |
                         v
                Consistent dump set
~~~

Changes committed before or at the snapshot point are visible according to SCN rules; changes committed after that point do not appear in the snapshot.

### 1.2 Example of transactions occurring during export

Suppose the snapshot is chosen at SCN 1000:

| Point in time | Event | Included in SCN 1000 export? |
|---|---|---|
| SCN 950 | INSERT customer and COMMIT | Yes |
| SCN 980 | UPDATE order status and COMMIT | Yes |
| SCN 1010 | INSERT order and COMMIT | No |
| SCN 1020 | DELETE customer and COMMIT | No |
| SCN 1030 | UPDATE address and COMMIT | No |

Data Pump reads as of SCN 1000, so the dump reflects the data state at that point even though later transactions commit while the job runs.

### 1.3 Consistent export does not lock the entire application

Flashback-based export uses Oracle's historical version reading capability. The goal is preserving a consistent snapshot without stopping all DML activity for the duration of the job.

However:

- Concurrent DDL can still affect the export.
- Sufficient UNDO must remain available to reconstruct data at the chosen SCN.
- Some object types or data sources do not support the same snapshot mechanism.
- External changes outside the database, such as external table files, are not automatically frozen at the SCN.

## 2. What Is FLASHBACK_SCN?

FLASHBACK_SCN is a Data Pump Export parameter that specifies the SCN as of which data should be exported.

Example:

~~~text
expdp app_user@PDB1 DIRECTORY=DP_DIR DUMPFILE=app_%U.dmp LOGFILE=app_export.log SCHEMAS=APP FLASHBACK_SCN=123456789
~~~

### 2.1 SCN is a logical database marker

An SCN (System Change Number) is a logical sequence number Oracle uses to order changes and define snapshots. It is suitable when you need to:

- Capture an exact snapshot before an export batch.
- Use the same marker across multiple export jobs.
- Record the data point in a runbook.
- Correlate with logs, transactions, or recovery.

### 2.2 Getting the current SCN

You can retrieve the SCN using DBMS_FLASHBACK:

~~~sql
SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS export_scn
FROM dual;
~~~

Or view the current SCN in V$DATABASE:

~~~sql
SELECT current_scn
FROM v$database;
~~~

DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER is a direct way to obtain a current SCN. Record the returned value right before starting the Data Pump job.

### 2.3 Recording the SCN alongside export details

Record:

- Database name and DB_UNIQUE_NAME.
- Source PDB/service.
- Chosen SCN.
- Timestamp when the SCN was captured and timezone.
- Exported schemas/tables.
- Data Pump job name.
- Dump files and log file.
- Oracle version.
- Operator and change/incident ID.

An SCN has no standalone meaning unless you know which database/incarnation it belongs to.

## 3. What Is FLASHBACK_TIME?

FLASHBACK_TIME lets you specify a point in time as a timestamp instead of entering an SCN directly. Data Pump converts the timestamp to a corresponding SCN and uses that SCN for the export.

Example:

~~~text
FLASHBACK_TIME="TO_TIMESTAMP('2026-11-14 10:00:00','YYYY-MM-DD HH24:MI:SS')"
~~~

When running in a parfile, the timestamp expression is wrapped in outer double quotes and the format string in single quotes.

### 3.1 Parfile example

Create `consistent_export.par`:

~~~text
DIRECTORY=DP_DIR
DUMPFILE=app_consistent_%U.dmp
LOGFILE=app_consistent.log
SCHEMAS=APP
FLASHBACK_TIME="TO_TIMESTAMP('2026-11-14 10:00:00','YYYY-MM-DD HH24:MI:SS')"
PARALLEL=4
FILESIZE=10G
~~~

Run:

~~~text
expdp app_user@PDB1 PARFILE=consistent_export.par
~~~

Do not store plaintext database passwords in parfiles or command history. Use a secure authentication mechanism conforming to environment standards, such as interactive password prompting, Oracle Wallet/secure external password store, or a DBA-approved mechanism.

### 3.2 Timestamps and timezones

The timestamp literal in the example has no timezone. Understand the database/session timezone and the timezone the operator used to specify the target time.

If the application logs in UTC while the DBA enters local time, the wrong snapshot can be chosen. Best practices:

- Standardize timestamps in UTC or an agreed convention.
- Explicitly note the timezone in tickets/runbooks.
- Record both the timestamp and the resolved SCN.
- Prefer FLASHBACK_SCN when an exact logical point is needed and the SCN can be captured beforehand.

### 3.3 FLASHBACK_TIME is not when the file starts writing

FLASHBACK_TIME selects the data snapshot; it does not mean Data Pump must start writing the dump at that exact wall-clock time. The export can start afterward and still read data as of the resolved SCN.

## 4. Comparing FLASHBACK_SCN and FLASHBACK_TIME

| Criterion | FLASHBACK_SCN | FLASHBACK_TIME |
|---|---|---|
| Input | Numeric SCN | Timestamp expression |
| Snapshot selection | Directly by SCN | Timestamp mapped to an SCN |
| Operational precision | Suits a recorded logical marker | Depends on timestamp-to-SCN mapping |
| Ease of use | Requires capturing/recording SCN | Easy to read as wall-clock time |
| Multi-job usage | Very convenient, pass the same SCN | Can use the same timestamp, but record the resolved SCN |
| Best suited for | Migrations/logical backups needing reproducibility | Exports aligned to a business timestamp |

These two parameters are mutually exclusive in the same Data Pump Export job. Choose only one:

~~~text
FLASHBACK_SCN=123456789
~~~

or:

~~~text
FLASHBACK_TIME="TO_TIMESTAMP('2026-11-14 10:00:00','YYYY-MM-DD HH24:MI:SS')"
~~~

Do not specify both in the same job.

## 5. Capturing the SCN Before Export

To give multiple schemas or multiple jobs the same snapshot, capture the SCN once and reuse it.

Example:

~~~sql
SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS export_scn
FROM dual;
~~~

Suppose the result is 123456789. Record the SCN in the change record and use the same value in every job:

~~~text
expdp app_user@PDB1 parfile=app.par
expdp ref_user@PDB1 parfile=reference.par
~~~

In each parfile:

~~~text
FLASHBACK_SCN=123456789
~~~

### 5.1 Why must the same SCN be used?

If APP is exported at SCN 1000 and REFERENCE is exported at SCN 2000, the two dumps do not represent the same database state. When importing both, data relationships may fail to match if transactions modified data between the two points.

Using the same SCN lets tables exported in separate jobs see the same snapshot, provided:

- Same source database and correct database incarnation.
- The SCN is still queryable via UNDO.
- All required objects support flashback export.
- No other restriction prevents reading part of the data at that SCN.

### 5.2 Multiple long-running jobs require keeping UNDO longer

If the first job finishes while the second job starts later and still uses the old SCN, Oracle must reconstruct data at that old SCN until the second job finishes reading. Necessary undo must remain available throughout that entire duration.

When sharing an SCN across multiple jobs, calculate the total time from capturing the SCN until the last job completes.

## 6. Schema-Level Data Pump Export Example

### 6.1 Capture the SCN

~~~sql
SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS export_scn
FROM dual;
~~~

Suppose the SCN is 987654321.

### 6.2 Create the parfile

~~~text
DIRECTORY=DP_DIR
DUMPFILE=app_full_%U.dmp
LOGFILE=app_full_consistent.log
SCHEMAS=APP
FLASHBACK_SCN=987654321
PARALLEL=4
FILESIZE=8G
METRICS=YES
LOGTIME=ALL
~~~

### 6.3 Run the export

~~~text
expdp app_user@PDB1 PARFILE=app_export.par
~~~

### 6.4 Read the log

Verify:

- Export job started and ended cleanly.
- Job used the right schema/mode.
- Table data exported successfully.
- No tables were skipped or errored.
- All dump file pieces were created.
- The log recorded the intended flashback parameter.

The log file is critical operational evidence. Do not rely solely on the exit code or a job-completed message.

## 7. Table-Level Export Example

If only a few tables are needed:

~~~text
DIRECTORY=DP_DIR
DUMPFILE=orders_%U.dmp
LOGFILE=orders_consistent.log
TABLES=APP.ORDERS,APP.ORDER_ITEMS
FLASHBACK_SCN=987654321
PARALLEL=2
~~~

The tables are exported at the same SCN. This is useful when moving a set of related tables.

### 7.1 INCLUDE/EXCLUDE

You can use INCLUDE/EXCLUDE to select object metadata/data per Data Pump rules:

~~~text
SCHEMAS=APP
INCLUDE=TABLE:"IN ('ORDERS','ORDER_ITEMS','CUSTOMERS')"
FLASHBACK_SCN=987654321
~~~

INCLUDE/EXCLUDE expressions have specific shell and parfile quoting requirements. For complex filters, use a parfile to avoid escaping errors.

## 8. Full-Database Export Example

Data Pump can export the full database with FULL=Y if the user has corresponding privileges:

~~~text
DIRECTORY=DP_DIR
DUMPFILE=full_%U.dmp
LOGFILE=full_consistent.log
FULL=Y
FLASHBACK_SCN=987654321
PARALLEL=8
FILESIZE=16G
~~~

Run:

~~~text
expdp system@PDB1 PARFILE=full_export.par
~~~

In multitenant environments, clarify whether you are exporting the CDB or a PDB and connect to the right service/container. FULL=Y inside a PDB does not export the entire CDB.

## 9. FLASHBACK_SCN/FLASHBACK_TIME and Data Pump Import

FLASHBACK_SCN and FLASHBACK_TIME are Data Pump Export parameters. They determine the source data snapshot when the dump is created.

During import:

~~~text
impdp app_user@TARGET PARFILE=app_import.par
~~~

Import reads the contents already recorded in the dump file. There is no need to re-specify the source database's SCN to recreate the export snapshot.

### 9.1 Import does not bring data to the current source state

If a dump was exported at SCN 1000, importing it several hours later still loads the SCN 1000 snapshot. Transactions committed after that SCN are not in the dump.

### 9.2 Importing into another schema

You can use REMAP_SCHEMA or REMAP_TABLESPACE as needed:

~~~text
REMAP_SCHEMA=APP:APP_TEST
REMAP_TABLESPACE=APP_DATA:APP_TEST_DATA
~~~

Remap parameters do not alter the snapshot SCN used during export.

## 10. Required Privileges

To run Data Pump Export, the user needs privileges matching the export mode and selected objects. Additionally, using FLASHBACK_SCN/FLASHBACK_TIME requires Flashback privileges on the exported tables.

Commonly reviewed privileges:

- Privileges to use the DIRECTORY object with READ and WRITE.
- SELECT privilege on tables/objects exported in the selected mode.
- Appropriate Data Pump privileges, such as the DATAPUMP_EXP_FULL_DATABASE role when exporting beyond the user's own schema.
- FLASHBACK privilege on relevant tables, or FLASHBACK ANY TABLE if needed across a broad scope.

Example granting directory privileges:

~~~sql
GRANT READ, WRITE ON DIRECTORY dp_dir TO app_user;
~~~

Example granting FLASHBACK on a table:

~~~sql
GRANT FLASHBACK ON app.orders TO export_user;
GRANT FLASHBACK ON app.order_items TO export_user;
~~~

Example broad system privilege:

~~~sql
GRANT FLASHBACK ANY TABLE TO export_user;
~~~

FLASHBACK ANY TABLE is a broad privilege. Grant it only when required by the export scope and in line with least-privilege policy. Prefer object privileges if exporting only a defined set of tables.

### 10.1 DIRECTORY is a database server-side path

DIRECTORY=DP_DIR references an Oracle DIRECTORY object:

~~~sql
CREATE OR REPLACE DIRECTORY dp_dir
AS '/u05/oracle/dpump';
~~~

The path is a filesystem on the database server, not the current directory on the machine running SQL Developer or the terminal client.

### 10.2 OS permissions

The Oracle Database software owner needs read/write permissions on the physical folder. Granting READ/WRITE on a DIRECTORY does not automatically grant filesystem permissions at the operating system level.

### 10.3 Do not use SYSDBA for routine Data Pump operations

Run Data Pump using an administrative user with appropriate privileges following organizational procedures. Avoid using SYSDBA as a way to bypass privilege design. If a privileged account must be used in a specific scenario, understand the connection requirements and ensure audit logging.

## 11. UNDO and Snapshot Retention Capability

Data Pump must read data at an older SCN while the database continues changing. Oracle may need UNDO to reconstruct row versions at that SCN.

If the export runs long, the duration UNDO must be retained also increases. When required undo is overwritten before workers finish reading, the export can fail with a snapshot-too-old error, typically ORA-01555.

### 11.1 UNDO_RETENTION

Check:

~~~sql
SHOW PARAMETER undo_retention;
~~~

UNDO_RETENTION is the target undo retention duration in automatic undo management. It is not an absolute guarantee that all undo will remain available if the undo tablespace runs out of space.

### 11.2 Inspecting undo statistics

~~~sql
SELECT begin_time,
       end_time,
       undoblks,
       txncount,
       maxquerylen,
       tuned_undoretention,
       ssolderrcnt,
       nospaceerrcnt
FROM v$undostat
ORDER BY begin_time DESC;
~~~

Columns may vary by version. V$UNDOSTAT aggregates by time intervals, which helps inspect longest query duration, undo block usage, and snapshot-too-old counts.

### 11.3 Estimating retention

Undo retention time should cover:

~~~text
Snapshot age at job completion
  = time from choosing SCN
    to the last worker finishing its table data
~~~

In practice, also add:

- Job preparation and scheduling lead time.
- Runtime of parallel/sequential export jobs.
- Retry time if a job fails.
- Safety margin for peak workloads.

If sharing one SCN across multiple jobs, retention must suffice until the final job finishes reading.

### 11.4 Undo capacity

Check undo tablespace:

~~~sql
SELECT tablespace_name,
       status,
       contents,
       retention
FROM dba_tablespaces
WHERE contents = 'UNDO';
~~~

Check datafiles:

~~~sql
SELECT tablespace_name,
       file_name,
       bytes,
       autoextensible,
       maxbytes
FROM dba_data_files
WHERE tablespace_name IN (
    SELECT tablespace_name
    FROM dba_tablespaces
    WHERE contents = 'UNDO'
);
~~~

Required capacity depends on peak-hour undo generation rate and how long the snapshot must be retained.

### 11.5 RETENTION GUARANTEE

An undo tablespace can use RETENTION GUARANTEE to prioritize keeping undo for the retention period. However, if the tablespace runs out of space, DML can fail rather than overwrite needed undo.

Do not enable RETENTION GUARANTEE just to make an export job succeed without evaluating the risk to write-heavy applications.

## 12. ORA-01555 in Data Pump Export

ORA-01555 occurs when Oracle no longer has enough undo to reconstruct the required query snapshot. With Data Pump, the error can happen on a large table or a long-running worker.

Common causes:

- Long export duration.
- High DML volume during the export window.
- Small undo tablespace.
- UNDO_RETENTION too low compared to snapshot duration.
- Insufficient or capped autoextend.
- Multiple export jobs holding old snapshots simultaneously.

### 12.1 Resolution approach

1. Identify the failing table/worker in the Data Pump log.
2. Measure job runtime and long query durations.
3. Inspect V$UNDOSTAT, undo tablespace, and alert log.
4. Increase undo capacity where justified.
5. Tune UNDO_RETENTION appropriately.
6. Run during a lower-DML window.
7. Reduce concurrent jobs if undo contention/capacity is the bottleneck.
8. Re-run with a new SCN after preparation.

### 12.2 Do not mix SCNs across parts of the same logical export

If a job fails and must be rerun, you can pick a new SCN for the entire new logical export. However, do not export some tables at an old SCN and the rest at a new SCN and combine the dumps as a single snapshot unless you have an explicit reconciliation design.

## 13. DDL During Export

FLASHBACK_SCN/FLASHBACK_TIME focus on creating a consistent data snapshot. They do not turn every database structural change into a freely queryable schema history.

During export, DDL operations such as:

- ALTER TABLE.
- DROP/RENAME TABLE.
- TRUNCATE.
- MOVE/SHRINK.
- Partition changes.
- Data type/constraint changes.

can cause Data Pump metadata errors or prevent reading the object at the desired snapshot.

### 13.1 Recommendations

- Freeze DDL on the schema during the export window.
- Record deployment windows.
- Avoid running migrations concurrently with exports unless necessary.
- If DDL is unavoidable, split into phases and test.
- Read logs to identify failing objects instead of blindly retrying the entire job.

### 13.2 ORA-01466

ORA-01466 can occur when an object's definition changes within the flashback window being read. If an export fails due to DDL, increasing UNDO does not fix the root cause.

## 14. Parallelism and Consistent Snapshots

Data Pump can use multiple workers via PARALLEL. When FLASHBACK_SCN is provided, workers read data as of the specified snapshot.

Example:

~~~text
DIRECTORY=DP_DIR
DUMPFILE=app_%U.dmp
LOGFILE=app.log
SCHEMAS=APP
FLASHBACK_SCN=987654321
PARALLEL=4
~~~

PARALLEL=4 can speed up export if storage/CPU have headroom. However:

- More workers can increase I/O and CPU consumption.
- Workers still need undo to reconstruct the same snapshot.
- A single long-running worker can extend how long undo must be retained.
- Parallelism does not fix DDL errors or insufficient undo.

### 14.1 %U in DUMPFILE

When PARALLEL is greater than 1 or dumps are split across multiple files, use a substitution variable like %U:

~~~text
DUMPFILE=app_%U.dmp
~~~

Oracle creates dump files with sequential numbering. Ensure sufficient filesystem space and concurrent multi-file write capability.

### 14.2 Do not increase PARALLEL indefinitely

If storage is already at maximum throughput, adding workers can slow down the export and degrade production workloads. Benchmark with 1, 2, 4, and 8 workers under realistic load.

## 15. Multiple Export Jobs Sharing One SCN

A migration may require exporting multiple schemas separately:

~~~text
SCN = 987654321

Job 1: APP
Job 2: CRM
Job 3: BILLING
Job 4: REFERENCE
~~~

Every parfile uses the same FLASHBACK_SCN=987654321.

### 15.1 Benefits

- Schemas can be imported together in a logically consistent state.
- Easy to document the data point.
- Jobs can be run independently according to storage capacity.
- The entire export can be retried at a new snapshot if the old snapshot loses undo.

### 15.2 Risks

- The last job may start late, making the SCN very old.
- Undo must last for the entire span.
- Some objects may not support flashback export.
- External operations outside the database are not synchronized automatically.
- DDL must be controlled across all jobs.

### 15.3 One SCN across all PDBs?

An SCN belongs to a specific database/container context. In multitenant environments, clarify whether exporting at the CDB or PDB level and use the right service/container. Do not capture an SCN from one database and apply it to another database or another PDB without understanding scope and support.

## 16. Consistent Export and Data Pump Modes

Data Pump Export supports multiple modes:

- FULL.
- SCHEMAS.
- TABLES.
- TABLESPACES.

Appropriate modes can be combined with FLASHBACK_SCN/FLASHBACK_TIME subject to release and object-type limitations.

### 16.1 Schema mode

~~~text
SCHEMAS=APP
FLASHBACK_SCN=987654321
~~~

Suitable for exporting an application schema.

### 16.2 Table mode

~~~text
TABLES=APP.ORDERS,APP.ORDER_ITEMS
FLASHBACK_SCN=987654321
~~~

Suitable for exporting a group of tables.

### 16.3 Full mode

~~~text
FULL=Y
FLASHBACK_SCN=987654321
~~~

Requires Data Pump full export privileges and appropriate container scope.

### 16.4 Transportable tablespaces

Transportable tablespace export has its own consistency procedures and requirements. Do not assume FLASHBACK_SCN/FLASHBACK_TIME can be used identically to schema/table mode for every transportable workflow. Consult Data Pump documentation for your exact release, especially regarding self-contained tablespace sets, read-only transitions, and metadata export.

## 17. Objects Not Frozen by FLASHBACK_SCN Alone

Flashback SCN applies to table data that Data Pump can read via flashback. It does not automatically synchronize every resource outside the database:

- External files referenced by external tables.
- BFILEs or content stored on the filesystem.
- Data in external systems accessed over DB links.
- External message queues or event streams.
- Application files generated concurrently.
- Sequence state or non-transactional side effects unlike row DML.

For these objects, use a separate snapshot procedure or freeze the source during the export window.

### 17.1 Sequences

Sequences do not behave like transactional columns in a table. Calling NEXTVAL can advance a sequence even if the transaction rolls back. Do not assume all sequence values are exported with the same snapshot semantics as table data.

If sequences must be guaranteed after migration:

- Capture sequence metadata/current values per procedure.
- Check sequence cache and concurrent NEXTVAL usage.
- Stop or coordinate sequence-issuing applications during the cutover window if needed.
- Reconcile sequence values on the target before opening writes.

### 17.2 External tables

External tables read data from files outside the database. FLASHBACK_SCN does not snapshot file contents. If a file changes during export, take a separate file snapshot/copy or freeze the source.

### 17.3 Metadata and DDL

Flashback SCN is not a DDL versioning system. Keep schemas and metadata stable during the export window.

## 18. FLASHBACK_TIME and Converting Timestamps to SCN

You can use TIMESTAMP_TO_SCN to find the approximate corresponding SCN:

~~~sql
SELECT TIMESTAMP_TO_SCN(
           TO_TIMESTAMP('2026-11-14 10:00:00',
                        'YYYY-MM-DD HH24:MI:SS')
       ) AS flashback_scn
FROM dual;
~~~

You can then pass that SCN into the parfile:

~~~text
FLASHBACK_SCN=987654321
~~~

Timestamp-to-SCN mapping exists only within the metadata range Oracle retains and is approximate. If the timestamp is too old, the mapping may no longer exist.

### 18.1 Using the SCN after choosing FLASHBACK_TIME

When an export must be reproducible, record the actual SCN used. The initial timestamp is business context; the SCN is a better technical marker for reuse.

### 18.2 Do not confuse an SCN captured after export

If you query the SCN after the export finishes, that is not the dump's snapshot SCN. Capture the SCN before running the job and pass it explicitly to Data Pump.

## 19. Verifying Data After Export

Inspect the Data Pump log carefully:

- Job completed successfully.
- No table data was skipped.
- No notable ORA-/UDE- errors.
- Exported row counts are reasonable.
- All dump pieces are present and readable.
- The log reflects the configured SCN or timestamp.

### 19.1 Row counts

Do not compare dump row counts against current source row counts if the source continued changing after the SCN. Compare against the snapshot at the same SCN:

~~~sql
SELECT COUNT(*)
FROM app.orders AS OF SCN 987654321;
~~~

Compare against row counts in the Data Pump log or after importing into a test environment. For large tables, counting can take time.

### 19.2 Inspecting the dump set

You can use Data Pump Import in SQLFILE mode to view DDL without executing it:

~~~text
impdp app_user@TARGET DIRECTORY=DP_DIR DUMPFILE=app_consistent_%U.dmp SQLFILE=app_ddl_review.sql
~~~

SQLFILE verifies DDL metadata; it does not fully validate table data.

### 19.3 Test import into an isolated schema

Import the dump into a test environment or isolated target schema:

~~~text
impdp app_user@TEST PARFILE=app_test_import.par
~~~

Verify:

- Tables and constraints.
- Row counts.
- Foreign key relationships.
- Indexes and triggers.
- Sequence states.
- Stored procedures/packages.
- Business-level data integrity.

## 20. Data Pump Logs and Job Monitoring

Data Pump creates a master table and worker processes to coordinate the job. Monitor running jobs using views:

- DBA_DATAPUMP_JOBS.
- DBA_DATAPUMP_SESSIONS.
- V$SESSION_LONGOPS.

Example:

~~~sql
SELECT owner_name,
       job_name,
       operation,
       job_mode,
       state,
       degree,
       attached_sessions
FROM dba_datapump_jobs
ORDER BY owner_name, job_name;
~~~

Monitor long operations:

~~~sql
SELECT sid,
       serial#,
       opname,
       sofar,
       totalwork,
       units,
       elapsed_seconds,
       time_remaining
FROM v$session_longops
WHERE totalwork > 0
  AND sofar < totalwork
ORDER BY start_time;
~~~

These views and columns require appropriate catalog/performance privileges. Do not grant broad privileges to application users merely to monitor one job.

## 21. Common Errors

### ORA-01555: snapshot too old

Necessary undo to read data at the chosen SCN is no longer available.

Resolution approach:

- Check the Data Pump log to identify the failing object/worker.
- Inspect V$UNDOSTAT and the undo tablespace.
- Increase undo capacity or retention where justified.
- Run during lower DML activity.
- Reduce total elapsed time from SCN capture to job completion.
- Choose a new SCN for a fresh export.

### ORA-01466: unable to read data - table definition has changed

DDL altered the object definition within the flashback window.

Resolution approach:

- Check deployment/DDL logs.
- Pause DDL during the export window.
- Retry with a stable schema and appropriate SCN.
- Do not just increase UNDO, since the root cause is metadata/DDL.

### UDE-/ORA- privilege errors

Possible causes:

- Missing FLASHBACK privilege on tables.
- Missing SELECT or Data Pump privileges.
- DIRECTORY object lacks READ/WRITE grant.
- OS user cannot write to the directory.

Verify privileges for the export scope; do not grant DBA or SELECT ANY DICTIONARY as a default fix.

### Insufficient dump files or out of space

Check:

- Filesystem/ASM free space.
- FILESIZE and DUMPFILE substitution.
- OS permissions.
- Number of dump pieces.
- End of job log.

### Timestamp rejected

Check:

- TO_TIMESTAMP syntax.
- Quoting in parfile/shell.
- Format mask.
- Timezone.
- Whether timestamp-to-SCN mapping is still available.

## 22. Migration Workflow Using Consistent Export

A schema migration can be structured as follows:

### Phase 1: Preparation

1. Identify source database/PDB and target.
2. Inventory schemas, tables, dependencies, and external objects.
3. Verify Data Pump version compatibility.
4. Check directories, filesystems, quotas, and dump capacity.
5. Confirm FLASHBACK/Data Pump privileges.
6. Evaluate UNDO retention and capacity.
7. Define a DDL freeze window.
8. Test export/import with representative data.

### Phase 2: Snapshot selection

1. Choose the business point in time.
2. Capture the SCN via DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER or determine the timestamp.
3. Record the SCN, timestamp, timezone, and database identity.
4. Pass the same SCN to all export jobs sharing one snapshot.

### Phase 3: Export

1. Run expdp using a parfile.
2. Monitor workers, elapsed time, and undo.
3. Do not deploy DDL on the schema during the export window.
4. Inspect logs, dump pieces, and errors.
5. If a job fails, determine whether it can be restarted/resumed or if the snapshot must be retried.

### Phase 4: Import and reconciliation

1. Run impdp into target/test schema.
2. Check metadata and object status.
3. Compare row counts against source AS OF the same SCN.
4. Verify parent-child relationships and constraints.
5. Verify sequences and external files separately.
6. Run business smoke tests.

### Phase 5: Cutover

1. Finalize changes occurring after the snapshot per migration strategy.
2. Stop/coordinate data writes if needed.
3. Sync post-snapshot deltas using a dedicated mechanism if required.
4. Perform final reconciliation.
5. Open application writes on the target.

Consistent export only guarantees the snapshot at the SCN. If the source continues accepting transactions after the SCN, those transactions are not in the dump. A zero-data-loss cutover requires delta replication/CDC or a dedicated write-freeze window.

## 23. Consistent Export Is Not Continuous Synchronization

A dump at an SCN is a static snapshot. It does not automatically receive changes occurring after the snapshot was chosen.

Example:

~~~text
SCN 1000: snapshot chosen
SCN 1010: export starts
SCN 1050: export finishes
SCN 1060: source continues receiving new transactions
~~~

The dump reflects the state at SCN 1000, not the state at SCN 1050 or 1060.

If the target must catch up to the source:

- Use replication/CDC.
- Use Data Guard for physical database replication.
- Use GoldenGate or an appropriate logical replication solution.
- Or stop source writes, export a final snapshot, and cut over.

Choose the solution based on RPO, RTO, downtime, and data types.

## 24. Consistent Export and Application Quiesce

Even though flashback export does not require stopping DML, there are cases where quiescing the application is advisable:

- Need a snapshot consistent with external files outside the database.
- Need sequence states synchronized with data.
- Need to guarantee no DDL occurs.
- Need to cut over and accept no new transactions after the cutoff.
- Application has side effects outside the database.

You can stop only writes (application-level read-only mode) rather than shutting down the whole database. The key is defining a clear snapshot boundary and which transactions are permitted afterward.

## 25. Consistent Export and Network Links

Data Pump can export data from a remote source via NETWORK_LINK in certain workflows. When using a network link:

- Identify which database is the actual source.
- Flashback privileges must be valid where Data Pump executes source queries.
- The SCN must belong to the source database.
- Verify version compatibility and network stability.
- Check limitations of network exports and flashback parameters in your release.

Never pass an SCN captured from the target into the source or vice versa. An SCN is not a global timestamp shared across independent databases.

## 26. Useful Accompanying Data Pump Parameters

Example parfile:

~~~text
DIRECTORY=DP_DIR
DUMPFILE=app_%U.dmp
LOGFILE=app_consistent.log
SCHEMAS=APP
FLASHBACK_SCN=987654321
PARALLEL=4
FILESIZE=8G
METRICS=YES
LOGTIME=ALL
STATUS=60
~~~

Meaning:

- DIRECTORY: Oracle DIRECTORY object.
- DUMPFILE: dump filename; %U for multiple pieces.
- LOGFILE: export log.
- SCHEMAS: schema to export.
- FLASHBACK_SCN: snapshot SCN.
- PARALLEL: target worker count.
- FILESIZE: size limit per dump piece.
- METRICS: writes object metrics to the log.
- LOGTIME: writes timestamps to the log.
- STATUS: interval for displaying job status in supported environments.

Check the Data Pump parameter reference for your version. Some parameters or values may change across releases.

## 27. Best Practices

- Prefer FLASHBACK_SCN when a recordable and reusable snapshot marker is needed.
- Use FLASHBACK_TIME when the business cutoff is defined by wall-clock time.
- Record the actual SCN, timestamp, and timezone.
- Use the same SCN for all jobs belonging to one logical export.
- Ensure sufficient UNDO for the longest span from SCN capture to final job completion.
- Monitor V$UNDOSTAT, alert log, and Data Pump logs.
- Avoid schema DDL during the export window.
- Use parfiles to reduce quoting errors and protect passwords.
- Never put database passwords into command history or shared files.
- Use server-side DIRECTORY objects with minimal filesystem permissions.
- Check every skipped or errored table/object.
- Run a test import in an isolated environment before cutover.
- Reconcile against source AS OF the same SCN.
- Handle sequences, external files, and side effects separately.
- Do not confuse snapshot exports with continuous delta synchronization.

## 28. Common Mistakes

| Mistake | Consequence | Correct practice |
|---|---|---|
| Omitting flashback parameters for multiple related tables | Tables may be read at different points in time | Use a single FLASHBACK_SCN/TIME |
| Specifying both FLASHBACK_SCN and FLASHBACK_TIME | Parameters are mutually exclusive | Choose one |
| Capturing the SCN after export completes | SCN does not represent the dump's snapshot | Capture before running the job |
| Using different SCNs for different schemas | Dumps do not share the same state | Use the same SCN |
| Increasing only UNDO_RETENTION | Undo space may still be insufficient | Measure undo rate, increase capacity, and control workload |
| Assuming UNDO_RETENTION is a guarantee | ORA-01555 can still occur | Understand retention target vs. retention guarantee |
| Running DDL during export | Object metadata can change and export can fail | Enforce a DDL freeze window |
| Increasing PARALLEL without limit | I/O/CPU contention | Benchmark |
| Thinking the dump reflects end-of-job state | Data committed after SCN is omitted | Document the snapshot SCN |
| Using a snapshot dump like CDC | Transactions after snapshot are lost | Maintain a delta replication/cutover plan |
| Comparing dump row counts to current source | Source changed after the SCN | Compare against AS OF the same SCN |
| Ignoring sequences/external files | Target lacks state outside row data | Synchronize separately |
| Forgetting FLASHBACK privilege | Job fails when reading historical data | Grant least-privilege object/system privileges |
| Thinking DIRECTORY is a local client folder | Dump files land in the wrong place or fail to write | Verify the server-side path |
| Not reading logs | Skipped tables or warnings go unnoticed | Review logs, dump pieces, and run test imports |

## 29. Self-Check Practice Labs

Perform in a lab database or an environment approved by the DBA.

### Lab 1 — Capture SCN

Use DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER. Record SCN, timestamp, database name, and PDB.

### Lab 2 — Export a schema

Create a parfile with SCHEMAS and FLASHBACK_SCN. Run expdp and inspect the log.

### Lab 3 — Data changing during export

Run a long export in the lab while concurrently updating data. Import the dump and compare against source AS OF the chosen SCN.

### Lab 4 — FLASHBACK_TIME

Run an export with a timestamp expression. Compare with the SCN mapped by TIMESTAMP_TO_SCN.

### Lab 5 — Same SCN across multiple jobs

Export two schemas using two separate jobs with the same SCN. Import together and check data relationships.

### Lab 6 — Insufficient undo

In the lab, run a long export with limited undo capacity. Observe potential ORA-01555 occurrence and inspect V$UNDOSTAT.

### Lab 7 — DDL during export

Attempt DDL on a table being exported in the lab. Record the error/impact and establish a DDL freeze window.

### Lab 8 — Parallelism

Compare PARALLEL=1, 2, and 4 under the same workload. Measure elapsed time, I/O, and CPU.

### Lab 9 — Test import

Import the dump into another schema using REMAP_SCHEMA. Verify row counts and constraints.

### Lab 10 — External tables

Export a schema containing an external table. Modify the external file outside the database and explain why FLASHBACK_SCN does not freeze file contents.

### Lab 11 — Sequences

Call NEXTVAL during export. Inspect the sequence on the target and design a separate synchronization step.

### Lab 12 — Cutover

Design a workflow with snapshot SCN, export, delta capture, write freeze, final sync, and cutover. Document RPO/downtime.

## 30. Checklist Before Running a Production Export

**Snapshot**

- Chosen SCN or timestamp?
- If using timestamp, is timezone clear?
- Recorded the actual SCN?
- Do multiple jobs use the same SCN?
- Does the SCN belong to the right source database/PDB?

**UNDO**

- Is undo retention sufficient for the longest job?
- Does the undo tablespace have enough capacity?
- Checked V$UNDOSTAT?
- Any peak DML or batch jobs during the export window?
- Plan in place for handling ORA-01555?

**Objects and DDL**

- Inventoried tables/objects?
- Any external tables or data outside the database?
- Do sequence states require separate synchronization?
- DDL freeze window agreed upon?
- Any objects that do not support flashback export?

**Data Pump**

- DIRECTORY object correct?
- READ/WRITE privileges and filesystem permissions correct?
- FLASHBACK privilege sufficient?
- DUMPFILE %U, FILESIZE, and PARALLEL appropriate?
- Parfile free of plaintext passwords?
- Logfile monitored?

**Import/cutover**

- All dump pieces complete?
- Log free of skipped/errored tables?
- Test import succeeded?
- Row counts reconciled at the same SCN?
- Constraints and relational data valid?
- Plan in place to synchronize post-snapshot changes?

## 31. Key Takeaways

| Concept | What to remember |
|---|---|
| Consistent export | Exports table data as of a single shared snapshot |
| FLASHBACK_SCN | Selects snapshot by SCN |
| FLASHBACK_TIME | Selects snapshot by timestamp mapped to an SCN |
| SCN | Logical marker of a database |
| DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER | Retrieves the current SCN |
| TIMESTAMP_TO_SCN | Maps a timestamp to an SCN while mapping remains available |
| Data Pump Export | Tool for creating logical dumps |
| Data Pump Import | Loads the snapshot already stored in the dump |
| DIRECTORY | Oracle object pointing to a database server-side filesystem |
| FLASHBACK privilege | Privilege required to read historical data |
| UNDO_RETENTION | Undo retention target, not an absolute guarantee |
| ORA-01555 | Insufficient undo remaining to reconstruct the snapshot |
| ORA-01466 | Object definition changed within the flashback window |
| DDL freeze | Avoid structural changes during the export window |
| PARALLEL | Target number of Data Pump workers |
| %U | Substitution variable generating multiple dump pieces |
| External table | External file outside the database not frozen by SCN |
| Sequence | State lacks transactional snapshot semantics like table DML |
| CDC/delta sync | Synchronizes changes occurring after the snapshot |

FLASHBACK_SCN and FLASHBACK_TIME enable Data Pump Export to read table data at a shared snapshot while applications remain active. SCN is ideal when a recordable, reusable technical marker is required; timestamps are convenient for business cutoffs, provided timezones and mapping are carefully managed. For a successful export, retain sufficient UNDO until the last worker finishes reading, avoid DDL during the export window, grant proper FLASHBACK privileges, and inspect all logs and dumps. Snapshots exclude changes committed after the SCN, do not freeze external files, and do not replace delta synchronization at cutover. Always run a test import, reconcile against source AS OF the same SCN, and rehearse the workflow before production migration.
