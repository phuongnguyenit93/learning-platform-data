# AS OF SCN, AS OF TIMESTAMP, and Querying Historical Data

Oracle Flashback Query allows you to query the data of a table or supported object as it existed at a point in the past. Two common ways to specify that point are **AS OF SCN** and **AS OF TIMESTAMP**.

- SCN (System Change Number) is the database's logical change sequence number. It identifies a consistent point in the database's history.
- TIMESTAMP is a wall-clock point in time. Oracle maps the timestamp to an appropriate SCN to execute the query.
- AS OF SCN queries the state of data at the specified SCN.
- AS OF TIMESTAMP queries the state of data at the specified point in time.

For example, if an employee's salary was updated by mistake at 10:15, the DBA can query the EMPLOYEES table at an SCN prior to that operation to inspect the old value. A historical query only reads old data; it does not roll back transactions automatically and does not automatically write old data back into the current table.

Flashback Query relies on undo information still retained in the database. Consequently, the ability to query the past depends on undo volume, query duration, concurrent write workload, retention configuration, and object structural changes. You cannot assume that every point in the past remains queryable.

## 1. What problem does Flashback Query solve?

In an active system, data continuously changes via INSERT, UPDATE, and DELETE. When you need to inspect a past state, a standard query returns only current data.

Flashback Query lets you attach a historical point to a SELECT statement to read the data version as of that time.

Use cases:

- Inspecting values before a transaction modified data by mistake.
- Reconciling data before and after a batch run.
- Determining the state of a row at the time an incident occurred.
- Comparing data at two SCNs.
- Investigating an unintended DELETE or UPDATE operation.
- Creating an inspection copy from historical data before deciding on recovery.
- Supporting audits and incident analysis while undo data remains available.

### 1.1. Example of changing data

Suppose the EMPLOYEES table has a row:

~~~sql
EMPLOYEE_ID  NAME   SALARY
-----------  -----  -------
100          AN     3000
~~~

Then a mistaken update occurs:

~~~sql
UPDATE employees
SET salary = 300
WHERE employee_id = 100;

COMMIT;
~~~

A normal query will show SALARY = 300. If the required undo still remains, you can query the state prior to the operation:

~~~sql
SELECT employee_id,
       name,
       salary
FROM employees AS OF SCN 123456789
WHERE employee_id = 100;
~~~

The historical query can return SALARY = 3000. The SCN in the example is illustrative only; you must use an actual SCN prior to the transaction under investigation.

### 1.2. Flashback Query is not a rollback

A SELECT AS OF statement only reads historical data. It does not:
- Cancel a COMMITted transaction.
- Modify current rows.
- Restore the entire database.
- Create a new backup.
- Guarantee that historical data persists indefinitely.

If you need to recover certain rows, query the historical data, confirm the values with the data owner, and execute separate DML under a controlled plan. If you need to return the entire database to a point in time, that is a Flashback Database or RMAN point-in-time recovery task.

## 2. SCN and TIMESTAMP

### 2.1. What is an SCN?

An SCN is a logical sequence number that Oracle uses to order changes and establish consistency. An SCN is neither a row sequence number nor seconds elapsed since an epoch.

A transaction produces changes identified by an SCN upon commit. The SCN enables Oracle to determine which data versions are visible at a consistent point.

Key characteristics to remember:
- SCN advances as changes occur in the database.
- SCN is a logical identifier, not a wall-clock time.
- A single SCN can serve as a common anchor across multiple tables in one query.
- Do not calculate an SCN manually by adding seconds or transaction counts.
- Do not compare SCNs across different databases as if they shared the same timeline.

### 2.2. What is a TIMESTAMP?

A TIMESTAMP is a wall-clock point in time. It is human-readable and often convenient when users know an incident occurred at 10:15 or before a specific business milestone.

Example:

~~~sql
TO_TIMESTAMP(
    '2026-11-14 10:15:00',
    'YYYY-MM-DD HH24:MI:SS'
)
~~~

When using timestamps:
- The format model must match the string.
- Identify the time zone of the timestamp.
- Do not rely on the default NLS_DATE_FORMAT.
- Watch out for clock skew among application hosts, database hosts, and log systems.
- Avoid ambiguous timestamps during daylight saving time transitions.

### 2.3. When to choose SCN vs. TIMESTAMP?

| Need | Preferred option |
| --- | --- |
| Have an SCN recorded immediately before the transaction | AS OF SCN |
| Have a timestamp from application logs or incident timeline | AS OF TIMESTAMP |
| Need the exact same anchor across multiple tables | AS OF SCN |
| Operators only know the wall-clock time of the incident | AS OF TIMESTAMP, optionally converted to SCN afterward |
| Need to reproduce a consistent point saved in an audit | AS OF SCN |
| Need to query near a wall-clock time | AS OF TIMESTAMP |

If the application can record the SCN at business boundaries, SCN is usually better for precise investigation. If only a timestamp is available, understand that Oracle maps the time to an SCN according to its available mapping resolution and history.

## 3. Prerequisites for using Flashback Query

Flashback Query requires enough historical data for Oracle to reconstruct the requested version.

Key conditions:

1. The database and object must have existed at the queried point.
2. The required undo must still exist and be readable.
3. The user must have appropriate SELECT and Flashback privileges.
4. The object must not have undergone structural changes that prevent querying across that point.
5. The SCN/TIMESTAMP must be valid within the historical range supported by Oracle.
6. The query must use only objects and constructs supported by Flashback Query.

### 3.1. Undo is the foundation of Flashback Query

When a row is UPDATEd or DELETEd, Oracle stores undo information to support rollback and read consistency. Flashback Query uses these undo versions to reconstruct data at an earlier SCN.

If the undo has already been reused, Oracle may no longer have enough information to return historical data.

### 3.2. UNDO_RETENTION is not an absolute guarantee in default configuration

The UNDO_RETENTION parameter sets the target retention duration for undo in seconds under automatic undo management. However, when the undo tablespace faces space pressure, Oracle may reuse unexpired undo in the default configuration.

To guarantee retention of unexpired undo, a DBA may consider RETENTION GUARANTEE on the undo tablespace. Understand the risk: if no space remains to allocate new undo, DML transactions may fail rather than overwriting protected undo.

Do not enable RETENTION GUARANTEE solely to keep Flashback Query working longer without evaluating capacity and write workload.

### 3.3. Required privileges

A user needs object read privileges and appropriate Flashback privileges. Object owners have privileges on their own objects; a DBA can grant specific object privileges:

~~~sql
GRANT SELECT, FLASHBACK
ON hr.employees
TO report_user;
~~~

Or grant a broader system privilege when administratively justified:

~~~sql
GRANT FLASHBACK ANY TABLE TO report_user;
~~~

FLASHBACK ANY TABLE has broad scope. Prefer object-level privileges when only specific tables need to be queried. Granting SELECT/FLASHBACK should follow the principle of least privilege.

Permission to query V$DATABASE or dynamic performance views to retrieve the current SCN is a separate privilege concern; application users do not necessarily need access to those views.

## 4. Querying with AS OF SCN

AS OF SCN places the historical anchor immediately after the table name in the FROM clause.

### 4.1. Basic syntax

~~~sql
SELECT column_list
FROM table_name AS OF SCN scn_expression
WHERE condition;
~~~

The SCN expression can be a literal or an appropriate bind variable.

Example:

~~~sql
SELECT employee_id,
       first_name,
       salary
FROM hr.employees AS OF SCN 123456789
WHERE employee_id = 100;
~~~

Oracle returns the row version visible at the specified SCN if the required undo data still exists.

### 4.2. Using bind variables

In applications or SQL*Plus, pass the SCN via a bind variable rather than concatenating dynamic SQL strings:

~~~sql
VARIABLE p_scn NUMBER
EXEC :p_scn := 123456789;

SELECT employee_id,
       first_name,
       salary
FROM hr.employees AS OF SCN :p_scn
WHERE employee_id = 100;
~~~

Bind variables promote SQL reuse and prevent errors when constructing statements from input. The bind type must match SCN requirements.

### 4.3. Retrieving the current SCN

You can read CURRENT_SCN from V$DATABASE:

~~~sql
SELECT current_scn
FROM v$database;
~~~

If you need to mark a point before executing a business change, save the SCN along with a request ID or audit event:

~~~sql
INSERT INTO operation_marker (
    request_id,
    captured_scn,
    captured_at
)
SELECT
    :request_id,
    current_scn,
    SYSTIMESTAMP
FROM v$database;
~~~

The example above illustrates saving a marker before an operation. The operation_marker table must be designed and protected according to business needs. If an exact anchor is needed for a transaction, clearly define when the SCN is captured relative to DML/COMMIT; do not capture an SCN after an incident occurs and label it as a pre-incident baseline.

### 4.4. Comparing current data with data at an SCN

~~~sql
SELECT 'CURRENT' AS source,
       employee_id,
       salary
FROM hr.employees
WHERE employee_id = 100
UNION ALL
SELECT 'HISTORICAL' AS source,
       employee_id,
       salary
FROM hr.employees AS OF SCN :p_scn
WHERE employee_id = 100;
~~~

The result highlights differences between the current state and the historical point. If the row does not exist on one side, that branch returns no rows. To show full missing/current/historical status, you can use an outer join or two separate check queries.

### 4.5. Using the same SCN across multiple tables

When querying related tables, apply the same SCN to each table reference:

~~~sql
SELECT o.order_id,
       o.status,
       c.customer_name
FROM sales.orders AS OF SCN :p_scn o
JOIN sales.customers AS OF SCN :p_scn c
  ON c.customer_id = o.customer_id
WHERE o.order_id = :p_order_id;
~~~

This ensures the tables are read at the same consistent point. If you place AS OF SCN only on ORDERS while reading CUSTOMERS from current data, the result may mix two points in time and produce relationships that do not reflect a consistent historical state.

Apply the same anchor to child tables in subqueries and views when a shared snapshot is needed. For complex views, verify supportability and how Oracle applies the flashback clause.

## 5. Querying with AS OF TIMESTAMP

AS OF TIMESTAMP is convenient when the point in time is known by hour, minute, and second.

### 5.1. Basic syntax

~~~sql
SELECT column_list
FROM table_name AS OF TIMESTAMP timestamp_expression
WHERE condition;
~~~

Example:

~~~sql
SELECT employee_id,
       first_name,
       salary
FROM hr.employees AS OF TIMESTAMP
     TO_TIMESTAMP(
         '2026-11-14 10:15:00',
         'YYYY-MM-DD HH24:MI:SS'
     )
WHERE employee_id = 100;
~~~

The timestamp is mapped by Oracle to an appropriate SCN to execute the Flashback Query. The returned anchor should not be interpreted as a transaction clock accurate to every microsecond.

### 5.2. Using TIMESTAMP bind variables

~~~sql
VARIABLE p_time VARCHAR2(19)
EXEC :p_time := '2026-11-14 10:15:00';

SELECT employee_id,
       salary
FROM hr.employees AS OF TIMESTAMP
     TO_TIMESTAMP(:p_time, 'YYYY-MM-DD HH24:MI:SS')
WHERE employee_id = 100;
~~~

In applications, it is better to bind a TIMESTAMP datatype directly if the driver supports it, avoiding string conversions and NLS dependencies.

### 5.3. Relative queries compared to the current time

Example querying the state approximately 10 minutes ago:

~~~sql
SELECT employee_id,
       salary
FROM hr.employees AS OF TIMESTAMP
     (CAST(SYSTIMESTAMP AS TIMESTAMP) - INTERVAL '10' MINUTE)
WHERE employee_id = 100;
~~~

The time expression must have a suitable datatype and a clearly understood time zone. When incident reproducibility is needed, record the actual timestamp used and the resulting mapped SCN if available.

### 5.4. Time zones and NLS

Do not use ambiguous date strings like 11/14/26 without a format model. Do not depend on the session's NLS_TIMESTAMP_FORMAT or NLS_DATE_FORMAT.

If the timestamp originates from another system:
- Identify the source time zone.
- Convert to a consistent time zone.
- Record the UTC offset explicitly.
- Verify clock synchronization.
- Use SCN if an anchor can be recorded directly from the database.

## 6. Converting between SCN and TIMESTAMP

Oracle provides functions to map between SCN and timestamp.

### 6.1. TIMESTAMP_TO_SCN

~~~sql
SELECT TIMESTAMP_TO_SCN(
           TO_TIMESTAMP(
               '2026-11-14 10:15:00',
               'YYYY-MM-DD HH24:MI:SS'
           )
       ) AS target_scn
FROM dual;
~~~

The function returns the SCN corresponding to the timestamp based on mapping information Oracle still retains. It is useful when recording an SCN after operators identify the incident time.

### 6.2. SCN_TO_TIMESTAMP

~~~sql
SELECT SCN_TO_TIMESTAMP(123456789) AS approximate_time
FROM dual;
~~~

The function returns a timestamp approximately corresponding to the SCN. The result is Oracle's time mapping, not proof that every change occurred at that exact instant.

### 6.3. Mapping has limits

Oracle does not maintain SCN-to-timestamp mappings indefinitely. If an SCN or timestamp falls outside the available mapping range, the function can raise errors such as ORA-08181 or ORA-08180 in relevant contexts.

The actual range depends on the database and mapping history. Do not hard-code an assumption that timestamps are always convertible for a fixed number of days.

### 6.4. SCN and timestamp are not fully interchangeable

- SCN represents logical order and is generally suited for consistency boundaries.
- TIMESTAMP is convenient for humans and logs.
- Timestamps map to SCNs with finite resolution.
- SCN_TO_TIMESTAMP returns an approximate time.
- Do not compare timestamps from two unsynchronized hosts and assume they align precisely with an SCN.

If an incident requires determining transactions before/after a specific boundary, prefer an SCN captured at the time the event occurred.

## 7. Querying multiple tables at the same point in time

A business operation often spans multiple tables. If only one table is flashbacked, the result may be business-inconsistent.

### 7.1. Example with orders and order items

~~~sql
SELECT o.order_id,
       o.order_status,
       i.line_id,
       i.product_id,
       i.quantity
FROM sales.orders AS OF SCN :p_scn o
JOIN sales.order_items AS OF SCN :p_scn i
  ON i.order_id = o.order_id
WHERE o.order_id = :p_order_id;
~~~

Both ORDERS and ORDER_ITEMS are queried at the same SCN.

### 7.2. Do not mix current with historical unintentionally

Avoid writing:

~~~sql
SELECT o.order_id,
       o.status,
       c.customer_name
FROM sales.orders AS OF SCN :p_scn o
JOIN sales.customers c
  ON c.customer_id = o.customer_id;
~~~

Here ORDERS is historical while CUSTOMERS is current. If a customer was renamed after the SCN, the result pairs the old order with the current name. That may be fine if the question calls for current customer info, but it is inappropriate if the goal is to reconstruct the full state at a point in time.

### 7.3. Using the same anchor in subqueries

~~~sql
SELECT o.order_id,
       o.status
FROM sales.orders AS OF SCN :p_scn o
WHERE EXISTS (
    SELECT 1
    FROM sales.order_items AS OF SCN :p_scn i
    WHERE i.order_id = o.order_id
      AND i.quantity > 0
);
~~~

All table references need the same SCN if the goal is a consistent snapshot.

## 8. Querying rows that were UPDATEd or DELETEd

Flashback Query can read pre-change row versions while undo remains available.

### 8.1. UPDATEd rows

~~~sql
SELECT employee_id,
       salary,
       department_id
FROM hr.employees AS OF SCN :before_update_scn
WHERE employee_id = 100;
~~~

If the row still exists today, the historical query returns its old version at that SCN.

### 8.2. DELETEd rows

~~~sql
SELECT employee_id,
       first_name,
       last_name
FROM hr.employees AS OF SCN :before_delete_scn
WHERE employee_id = 100;
~~~

If the row existed at the SCN and was DELETEd afterward, the historical query can still return the old row.

### 8.3. Rows INSERTed after the historical anchor

If a row did not exist at the SCN, an AS OF SCN query will not return that row. This is the expected behavior of a point-in-time query.

### 8.4. Controlled row recovery

Do not directly UPDATE current data just because a historical query returned an old value. Safe procedure:
1. Query the row at the required SCN.
2. Save the result to a staging table or export it to a controlled file.
3. Confirm the exact primary key and columns to recover.
4. Check for valid changes that occurred after the SCN.
5. Write DML targeting only the rows/columns needing repair.
6. Execute inside a transaction with row count verification.
7. Reconcile data after commit.

Example inserting a copy into a staging table:

~~~sql
INSERT INTO employees_recovery_stage (
    employee_id,
    first_name,
    last_name,
    salary,
    source_scn
)
SELECT employee_id,
       first_name,
       last_name,
       salary,
       :before_update_scn
FROM hr.employees AS OF SCN :before_update_scn
WHERE employee_id = 100;
~~~

The staging table must be created with an appropriate schema and data protection. Do not INSERT directly into production business tables without checking duplicate keys, foreign keys, triggers, auditing, and newer updates.

## 9. Flashback Versions Query: viewing history over a range

AS OF SCN/TIMESTAMP returns state at a single point. When you need to view row versions across an interval, use Flashback Versions Query with VERSIONS BETWEEN.

### 9.1. Syntax

~~~sql
SELECT versions_startscn,
       versions_endscn,
       versions_operation,
       versions_xid,
       employee_id,
       salary
FROM hr.employees
     VERSIONS BETWEEN SCN :start_scn AND :end_scn
WHERE employee_id = 100
ORDER BY versions_startscn;
~~~

Common pseudocolumns:
- VERSIONS_STARTSCN: Starting SCN of the version.
- VERSIONS_ENDSCN: Ending SCN of the version.
- VERSIONS_OPERATION: Operation that created the version, typically I, U, or D.
- VERSIONS_XID: Associated transaction ID.

### 9.2. Using a TIMESTAMP range

~~~sql
SELECT versions_starttime,
       versions_endtime,
       versions_operation,
       employee_id,
       salary
FROM hr.employees
     VERSIONS BETWEEN TIMESTAMP
         TO_TIMESTAMP('2026-11-14 09:00:00', 'YYYY-MM-DD HH24:MI:SS')
     AND TO_TIMESTAMP('2026-11-14 11:00:00', 'YYYY-MM-DD HH24:MI:SS')
WHERE employee_id = 100
ORDER BY versions_starttime;
~~~

Use timestamp when the boundaries are defined by clock time. Keep in mind that version data still depends on undo retention and mapping availability.

### 9.3. When to use AS OF vs. VERSIONS?

| Need | Syntax |
| --- | --- |
| View a row at a single exact SCN | AS OF SCN |
| View state at a wall-clock time | AS OF TIMESTAMP |
| View row versions across a range | VERSIONS BETWEEN SCN/TIMESTAMP |
| View a past state for comparison | AS OF |
| Investigate a row's sequence of INSERT/UPDATE/DELETE | VERSIONS BETWEEN |

VERSIONS BETWEEN is not an indefinite audit log. It also relies on still-available version history.

## 10. Flashback Query and other Flashback features

The names are similar, but the features solve different problems.

| Feature | Goal | Mechanism/impact scope |
| --- | --- | --- |
| Flashback Query | Read table data at a past SCN/TIMESTAMP | SELECT and undo |
| Flashback Versions Query | View row versions across a range | SELECT, versions, and undo |
| Flashback Transaction Query | Inspect transaction metadata related to changes | Transaction metadata and undo |
| Flashback Table | Return one or more tables to a past state | Internal DML; requires specific conditions like row movement |
| Flashback Database | Return the entire database to an earlier SCN/time | Flashback logs and database recovery |
| RMAN point-in-time recovery | Restore/recover database to a timestamp/SCN | Backups and archived redo |

Flashback Query does not require Flashback Database to be enabled. It uses undo, whereas Flashback Database requires configured flashback logging and a flashback area.

Do not use Flashback Table or Flashback Database merely to read an old row. Conversely, when full database recovery is needed after a major error, a SELECT AS OF query cannot replace a recovery procedure.

## 11. Undo retention and the risk of ORA-01555

### 11.1. Why can Flashback Query fail?

When a query requests a past version, Oracle must locate undo to reconstruct the data. If undo has been overwritten or is insufficient, the query may fail.

Causes:
- UNDO_RETENTION is too low relative to the age of the data being queried.
- The undo tablespace lacks sufficient capacity.
- Sudden spikes in DML workload.
- Long-running historical queries.
- Large transactions generating undo rapidly.
- RETENTION GUARANTEE is not enabled and Oracle reuses unexpired undo when needed.

### 11.2. ORA-01555: snapshot too old

ORA-01555 typically indicates Oracle could not retain or locate the undo version required for a read-consistent query. Flashback Query can encounter this error when sufficient history is no longer available.

Do not assume increasing UNDO_RETENTION alone will solve the problem. Evaluate undo capacity, undo generation rate, query duration, and retention policy.

### 11.3. Checking UNDO_RETENTION

~~~sql
SHOW PARAMETER undo_retention;
SHOW PARAMETER undo_tablespace;
~~~

UNDO_RETENTION is measured in seconds. The configured value is a retention target; the effective retention may be dynamically tuned by Oracle based on workload and space.

### 11.4. Monitoring V$UNDOSTAT

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

Useful columns:
- UNDOBLKS: Number of undo blocks consumed during the interval.
- TXNCOUNT: Number of transactions during the interval.
- MAXQUERYLEN: Length of the longest recorded query, in seconds.
- TUNED_UNDORETENTION: Retention tuned for actual workload, in seconds.
- SSOLDERRCNT: Number of snapshot too old errors in the interval.
- NOSPACEERRCNT: Number of undo space errors in the interval.

Review trends across multiple intervals and compare against the Flashback Query window you need to support.

### 11.5. RETENTION GUARANTEE

A DBA can configure retention guarantee on an undo tablespace:

~~~sql
ALTER TABLESPACE undotbs1 RETENTION GUARANTEE;
~~~

Disable guarantee:

~~~sql
ALTER TABLESPACE undotbs1 RETENTION NOGUARANTEE;
~~~

RETENTION GUARANTEE prevents Oracle from overwriting unexpired undo per policy. In return, if no space remains to allocate new undo, DML transactions may fail. Evaluate carefully before enabling, especially under heavy write workloads.

## 12. DDL and object structural changes

Flashback Query focuses on data versions. If an object's structure changes, Oracle may be unable to query across the DDL boundary.

Examples:
- DROP or recreate table.
- TRUNCATE.
- Column structure changes.
- Certain partition or move operations that alter metadata/segments.

A possible error is ORA-01466, reporting that data cannot be read because the table definition has changed.

### 12.1. DDL is not like DML

DML modifies row data and generates transactional undo. DDL alters metadata and typically performs an implicit commit. Do not expect Flashback Query to reconstruct every pre-DDL table structure using row undo alone.

### 12.2. If a table is DROPped

Flashback Query is not a tool for recovering dropped objects. If the table is in the recycle bin, Flashback Drop may be considered under appropriate conditions. If the object cannot be flashbacked from the recycle bin, restore/recovery from backup or another approach is required.

### 12.3. TRUNCATE

TRUNCATE is DDL and cannot be treated like a batch of DELETEs that remains indefinitely queryable in history. If pre-TRUNCATE data must be recovered, evaluate the recycle bin, backups, RMAN, or an auxiliary environment. Do not assume AS OF SCN can always query across a TRUNCATE.

## 13. Limitations and cases to verify

Flashback Query has limitations regarding datatypes, objects, DDL, privileges, and Oracle releases. Before building a dependent process, test on the exact object type and release.

Points to note:
- Not every table/object type supports every form of Flashback Query.
- Temporary tables and external tables have distinct semantics and should not be assumed to behave like standard heap tables.
- The object must exist with a compatible definition at the queried point.
- Required undo must still be available.
- Certain DDL operations prevent querying past an older boundary.
- A timestamp may fail to map if historical mapping is no longer retained.
- Large queries can run long and consume significant resources reconstructing old versions.
- Flashback Query does not replace backups, archive logs, or disaster recovery.

When designing an audit or recovery workflow, confirm limitations in the documentation for your exact Oracle release and test with a representative schema.

## 14. Capturing SCN anchors for applications and incident investigation

A good practice is to capture the SCN near critical business moments rather than attempting to deduce it hours later from timestamp logs.

### 14.1. Saving the SCN before sensitive operations

Example:

~~~sql
SELECT current_scn
INTO :p_before_scn
FROM v$database;
~~~

Applications or stored procedures can save the SCN alongside a request ID, batch ID, and timestamp. Ensure the user has privilege to read the view or uses a DBA-approved service for recording.

### 14.2. Recording both SCN and timestamp

An audit marker should store:
- Request/batch ID.
- SCN.
- Timestamp with time zone.
- Database identity.
- Instance/service if relevant.
- User/module/action.
- Description of the operation.

The SCN enables reproducing the logical snapshot; the timestamp helps correlate with logs and human timelines.

### 14.3. Determining an SCN near an incident timestamp

If only a timestamp is available, use TIMESTAMP_TO_SCN:

~~~sql
SELECT TIMESTAMP_TO_SCN(
           TO_TIMESTAMP(
               :incident_time,
               'YYYY-MM-DD HH24:MI:SS'
           )
       ) AS incident_scn
FROM dual;
~~~

If conversion fails, check the mapping range, format, time zone, and input timestamp. Do not substitute the current SCN automatically.

### 14.4. Verifying the anchor before recovery

Run a test query by primary key or on a small set of rows. Compare current and historical values, verify the data aligns with business logs, and only then prepare the staging/recovery script.

## 15. Example: investigating a mistaken UPDATE

Suppose an operator updated employee 100's salary by mistake. The reported incident timestamp is 10:15.

### 15.1. Converting timestamp to SCN

~~~sql
SELECT TIMESTAMP_TO_SCN(
           TO_TIMESTAMP(
               '2026-11-14 10:15:00',
               'YYYY-MM-DD HH24:MI:SS'
           )
       ) AS incident_scn
FROM dual;
~~~

Suppose the result is 987654321. The actual target point must be verified against the timeline; if the UPDATE occurred before 10:15, choose a point prior to that transaction.

### 15.2. Reading historical data

~~~sql
SELECT employee_id,
       first_name,
       salary
FROM hr.employees AS OF SCN 987654321
WHERE employee_id = 100;
~~~

### 15.3. Reading current data

~~~sql
SELECT employee_id,
       first_name,
       salary
FROM hr.employees
WHERE employee_id = 100;
~~~

Compare both results and the audit trail to confirm the exact row and values to restore.

### 15.4. Saving the historical copy to staging

~~~sql
INSERT INTO employee_salary_recovery (
    employee_id,
    salary_before,
    source_scn,
    captured_at
)
SELECT employee_id,
       salary,
       987654321,
       SYSTIMESTAMP
FROM hr.employees AS OF SCN 987654321
WHERE employee_id = 100;
~~~

Staging lets operators review and verify data before updating the production business table.

## 16. Example: controlled recovery of specific columns

After verifying historical values, you can perform a conditional update. Example:

~~~sql
UPDATE hr.employees current_row
SET current_row.salary = (
    SELECT historical_row.salary
    FROM hr.employees AS OF SCN :p_scn historical_row
    WHERE historical_row.employee_id = current_row.employee_id
)
WHERE current_row.employee_id = :employee_id;
~~~

Before COMMITting:
- Check SQL%ROWCOUNT.
- Verify old and new values.
- Confirm you are not overwriting valid changes made after the SCN.
- Check triggers and auditing.
- Check whether the transaction affects related tables.

A row may have received multiple valid updates after the incident. Restoring the entire row to an older SCN can erase those valid changes. Only fix the exact columns/rows required by the business decision.

Example verification inside a transaction:

~~~sql
SAVEPOINT before_repair;

UPDATE hr.employees current_row
SET current_row.salary = (
    SELECT historical_row.salary
    FROM hr.employees AS OF SCN :p_scn historical_row
    WHERE historical_row.employee_id = current_row.employee_id
)
WHERE current_row.employee_id = :employee_id;

SELECT employee_id, salary
FROM hr.employees
WHERE employee_id = :employee_id;

-- COMMIT only after verification.
-- If the result is incorrect:
ROLLBACK TO before_repair;
~~~

Do not embed an automatic COMMIT in recovery scripts when an operator review step is required. Record the source SCN and incident ID in the change record.

## 17. Querying across schemas, synonyms, and views

The flashback clause is placed on the table reference in the FROM clause. For other schemas, specify the owner explicitly to avoid synonyms pointing to unintended objects.

Example:

~~~sql
SELECT *
FROM app_owner.customer_orders AS OF SCN :p_scn o;
~~~

When using views:
- Verify the view and its base tables support flashback in that context.
- Ensure privileges on both the object and underlying base objects are adequate.
- For complex queries, you can flashback individual base tables in FROM to enforce the same SCN.
- Do not assume synonyms automatically resolve the historical anchor for every dependency.

If a view uses a database link or external objects, check specific limitations. Do not treat a SELECT AS OF on a local table as proof that distributed data sources share the same snapshot.

## 18. CDB/PDB and RAC environments

### 18.1. PDB context

In multitenant architecture, queries must execute in the container holding the target objects and with appropriate privileges. Record:
- DBID/CDB identity.
- PDB name and CON_ID.
- SCN captured within the corresponding database context.
- Timestamp and time zone.
- User and privileges.

Do not mix SCNs/timestamps or historical results across different PDBs as though they shared the same object namespace. Verify SCN scope and the views used for your Oracle release.

### 18.2. RAC

SCN provides database-wide logical ordering in a RAC database, though dynamic performance views may display per-instance rows. When collecting diagnostic info, record INST_ID and do not confuse instance identity with database identity.

Flashback Query reads database data at an SCN, not a per-instance counter. However, when gathering timestamps, logs, and SCNs from multiple nodes, clock synchronization and database identity remain important.

## 19. Monitoring undo and verifying historical query capability

Before rolling out a historical query process, the DBA should check:
- Current UNDO_RETENTION.
- Undo tablespace size.
- Undo generation rate.
- MAXQUERYLEN.
- TUNED_UNDORETENTION.
- SSOLDERRCNT.
- NOSPACEERRCNT.
- Peak workload and transaction duration.

Example checking configuration:

~~~sql
SELECT tablespace_name,
       retention
FROM dba_tablespaces
WHERE contents = 'UNDO';
~~~

Checking undo files:

~~~sql
SELECT tablespace_name,
       file_name,
       bytes / 1024 / 1024 AS size_mb,
       autoextensible,
       maxbytes / 1024 / 1024 AS max_mb
FROM dba_data_files
WHERE tablespace_name = (
    SELECT value
    FROM v$parameter
    WHERE name = 'undo_tablespace'
);
~~~

If an application needs 24-hour historical queries but undo only lasts a fraction of that time under heavy load, the current design does not meet requirements. Adjust capacity/retention or choose a long-term history mechanism such as audit/history tables, CDC, Flashback Data Archive, or backup-based recovery depending on requirements.

## 20. Flashback Data Archive and long-term history

Undo-based Flashback Query is typically suited for querying past data within the available undo window. If business requirements demand retaining history for months or years, consider Flashback Data Archive (Total Recall) or a dedicated temporal/audit model.

Flashback Data Archive stores change history for configured tables according to retention policies. It differs from simply increasing UNDO_RETENTION.

Before using it, you must:
- Confirm Oracle edition and licensing/feature entitlement.
- Identify supported tables.
- Design retention and storage.
- Review DML and administrative impact.
- Define who has privilege to query historical data.
- Verify compliance and purge requirements.

Do not assume Flashback Data Archive is enabled by default for all tables. It requires separate configuration and operations.

## 21. Performance and cost of querying past data

Flashback Query may need to read undo and reconstruct older versions. Cost depends on:
- Age of the SCN.
- Number of rows to read.
- Volume of changes between the historical anchor and the present.
- Undo blocks that must be accessed.
- Joins, sorts, aggregations, and parallelism.
- Storage latency and buffer cache.
- Concurrent workload.

### 21.1. Limiting scope

Filter with WHERE by primary key or partition key whenever possible. Avoid full historical table scans when only a few rows are needed.

~~~sql
SELECT employee_id,
       salary
FROM hr.employees AS OF SCN :p_scn
WHERE employee_id BETWEEN :low_id AND :high_id;
~~~

### 21.2. Avoid running large historical queries during an incident

If the database is already short on undo or storage, a heavy Flashback Query can increase load. Identify the minimal row set first and choose an appropriate time to run the query.

### 21.3. Checking execution plans

You can use EXPLAIN PLAN or DBMS_XPLAN according to privileges and environment procedures. The flashback clause does not automatically make any query cheaper. Join order, indexes, predicates, and row counts still matter.

### 21.4. Selecting only needed columns

Do not SELECT * when only two columns are needed for recovery. This reduces data read, transferred, and stored in staging.

## 22. Security and auditing

Historical queries can reveal deleted or modified data, including personal information and sensitive records.

Controls:
- Grant FLASHBACK privileges at minimal scope.
- Grant SELECT only on necessary objects.
- Audit queries against sensitive data per policy.
- Restrict access to staging/recovery tables.
- Encrypt and protect exports.
- Do not output sensitive data to DBMS_OUTPUT or unprotected logs.
- Record the SCN, request ID, operator, and recovery justification.

Do not grant broad FLASHBACK ANY TABLE to an application account solely to support one report when object-level grants suffice.

## 23. Common errors

| Error/situation | Possible cause | Resolution |
| --- | --- | --- |
| ORA-01555 | Required undo no longer available | Check undo retention, size, generation rate, and query duration |
| ORA-08180 | No matching snapshot found for timestamp | Check timestamp, mapping, and available history |
| ORA-08181 | Invalid SCN or no valid mapping in function context | Verify SCN/database and mapping range |
| ORA-01466 | Table definition changed across the historical anchor | Identify DDL/segment changes; use backup or another method |
| ORA-01031 | Insufficient privileges | Check SELECT/FLASHBACK privileges |
| ORA-00942 | Object does not exist or not visible | Verify owner, object name, and grants |
| Historical row not found | Row did not exist at SCN or was deleted before SCN | Verify anchor and check Versions Query |
| Timestamp returns unexpected values | Wrong format, time zone, or NLS | Use TO_TIMESTAMP with an explicit format model |
| One table right, joined table wrong time | Only one table reference has AS OF | Apply the same SCN to all tables needing a shared snapshot |
| Historical query runs slowly | Broad scope, undo I/O, heavy joins/sorts | Narrow predicates and inspect execution plan |
| AS OF cannot read object | Unsupported object type/DDL | Check version and object limitations |
| Recovered row overwrites valid changes | Recovery DML updates entire row unchecked | Stage, reconcile, and update conditionally |

Error codes may depend on release and context. Read the full error stack, alert log, and traces when needed; do not rely solely on the top-level error code.

## 24. Runbook for investigating mistakenly modified data

1. Identify the affected table, primary key, and columns.
2. Record the incident time from application logs, audit trails, or incident timeline.
3. Identify the database/PDB/service and time zone.
4. Obtain the SCN near the point of interest or convert the timestamp to an SCN.
5. Verify SELECT/FLASHBACK privileges.
6. Run AS OF SCN on a single test row.
7. Compare current and historical values.
8. If you need the sequence of changes, use VERSIONS BETWEEN.
9. Check undo availability and any DDL within the interval.
10. Save historical data into a secure staging table.
11. Confirm with the data owner and assess valid changes made after the SCN.
12. Write conditional DML and check row counts.
13. Execute inside a transaction with a savepoint.
14. Review results before COMMITting.
15. Document the SCN, operator, script, and outcome.
16. Verify the application after recovery.

If undo is no longer available, stop repeatedly probing older timestamps. Switch to backup/restore on an auxiliary database, Flashback Data Archive, or an appropriate audit source.

## 25. Consolidated example: querying an order at an SCN

Suppose you have the ORDERS and ORDER_ITEMS tables. Before a status-updating batch job, the DBA records the SCN:

~~~sql
SELECT current_scn
FROM v$database;
~~~

After the batch, you want to know the state of order 5001 before the batch:

~~~sql
SELECT order_id,
       status,
       customer_id,
       total_amount
FROM sales.orders AS OF SCN :batch_start_scn
WHERE order_id = 5001;
~~~

Inspect details at the same anchor:

~~~sql
SELECT i.order_id,
       i.line_no,
       i.product_id,
       i.quantity,
       i.unit_price
FROM sales.order_items AS OF SCN :batch_start_scn i
WHERE i.order_id = 5001
ORDER BY i.line_no;
~~~

If a single joined result is needed:

~~~sql
SELECT o.order_id,
       o.status,
       o.total_amount,
       i.line_no,
       i.product_id,
       i.quantity
FROM sales.orders AS OF SCN :batch_start_scn o
JOIN sales.order_items AS OF SCN :batch_start_scn i
  ON i.order_id = o.order_id
WHERE o.order_id = 5001
ORDER BY i.line_no;
~~~

Using the same SCN ensures both header and detail are read at the same logical snapshot, provided undo and object metadata still support that point.

## 26. Common misconceptions

**AS OF SCN is a way to roll back a transaction.** False. It only reads an older version of the data.

**AS OF TIMESTAMP is accurate to the microsecond.** False. Oracle maps timestamps to SCNs via a mapping with finite resolution.

**SCN is a numeric timestamp.** False. SCN is a logical change sequence number, not an epoch timestamp.

**UNDO_RETENTION guarantees every historical query will succeed.** False in the default configuration when undo is under space pressure and may be reused. Capacity and retention guarantee must be evaluated.

**Flashback Query requires Flashback Database to be enabled.** False. Flashback Query uses undo; Flashback Database uses flashback logs.

**AS OF SCN automatically recovers data.** False. Separate DML is required if you want to update current data.

**Adding AS OF to only the main table is enough.** False if a consistent snapshot across multiple tables is needed. Apply the same SCN to every relevant table reference.

**Flashback Query replaces backups.** False. Undo has a limited lifespan and does not replace backups/archived redo.

**VERSIONS BETWEEN is an infinite audit log.** False. Versions depend on available undo data and object limitations.

**You can query across any DDL.** False. Structural DDL can cause Flashback Query to fail, such as with ORA-01466.

**DELETEd rows cannot be read again.** Pre-DELETE versions can be read if undo remains available and the object supports it.

**You can restore an entire old row without affecting newer updates.** False. Valid changes after the SCN must be reconciled, and only the necessary columns/rows should be updated.

**TIMESTAMP_TO_SCN always converts every timestamp.** False. Mapping has a finite range; timestamps that are too old or invalid can fail.

**SCNs between two databases can be compared directly.** You should not. SCNs only carry meaning within the history of their respective database.

## 27. Self-study exercises

1. Explain what Flashback Query is used for.
2. Distinguish between SCN and TIMESTAMP.
3. Write a SELECT AS OF SCN query for a row by primary key.
4. Write a SELECT AS OF TIMESTAMP query using TO_TIMESTAMP and a format model.
5. Why should you not rely on NLS_TIMESTAMP_FORMAT?
6. Retrieve CURRENT_SCN from V$DATABASE.
7. Explain when an SCN should be saved prior to a business operation.
8. Use TIMESTAMP_TO_SCN to convert an incident time into an SCN.
9. Use SCN_TO_TIMESTAMP to check the approximate corresponding time.
10. Explain why SCN_TO_TIMESTAMP is not an exact wall clock.
11. State the undo prerequisites required for Flashback Query.
12. Distinguish UNDO_RETENTION from RETENTION GUARANTEE.
13. State the risks of enabling RETENTION GUARANTEE.
14. Write a GRANT SELECT and FLASHBACK statement for a table.
15. Why should FLASHBACK ANY TABLE not be granted to every user?
16. Write a query joining ORDERS and ORDER_ITEMS at the same SCN.
17. Explain the risk when one table uses AS OF while another reads current data.
18. Query a row that was mistakenly UPDATEd at an SCN prior to the change.
19. Query a row that was DELETEd at an SCN prior to the DELETE.
20. Explain why AS OF does not automatically roll back a transaction.
21. Write a VERSIONS BETWEEN SCN query to view a row's history.
22. Explain VERSIONS_OPERATION and VERSIONS_XID.
23. Distinguish Flashback Query, Flashback Table, and Flashback Database.
24. How can ORA-01555 affect Flashback Query?
25. What kind of change is ORA-01466 typically associated with?
26. Why can Flashback Query fail after TRUNCATE or DDL?
27. Design a staging workflow before recovering a row.
28. Which feature is suitable when months of data history are needed?
29. Design an audit marker recording request ID, SCN, timestamp, and module.
30. Build a runbook for investigating mistaken UPDATE/DELETE operations, from capturing the SCN anchor to controlled recovery DML.

**AS OF SCN and AS OF TIMESTAMP let you read data states at a point in the past; SCN identifies the logical anchor while timestamp locates it by wall-clock time.** Flashback Query relies on available undo, requires appropriate privileges, and has limitations when object structures change. Use the same SCN for all tables in a snapshot, validate historical data before recovering, and always perform corrective DML through a controlled process.
