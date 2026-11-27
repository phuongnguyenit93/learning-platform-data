# VERSIONS BETWEEN and Viewing Row Change History

Oracle Flashback Versions Query lets you view the versions of a data row across a time interval or SCN range. Instead of returning only the row's current state, the query can return multiple versions that existed during the selected interval, along with metadata indicating when each version started/ended, which transaction created it, and which DML operation was involved.

This is a useful tool when investigating:

- What values has a row gone through across its changes?
- What were the values before and after an UPDATE?
- In what time window was a row DELETEd?
- Which transaction created the version being inspected?
- How did the data change before an incident or mistaken operation?

Flashback Versions Query relies on row version information and UNDO still retained by Oracle. It is not a permanent audit log, does not replace backups, and does not guarantee indefinite historical visibility. If you need long-term history with end-user identity, business justification, or compliance proof, design auditing/CDC or dedicated history tables.

## 1. What is Flashback Versions Query?

Flashback Versions Query is the ability to query row versions across an SCN or timestamp range using the VERSIONS BETWEEN clause.

Basic example:

~~~sql
SELECT employee_id,
       salary
FROM employees
VERSIONS BETWEEN SCN 100000 AND 200000
WHERE employee_id = 100;
~~~

If the row for employee 100 went through multiple versions within that SCN range, the result may contain multiple rows with the same EMPLOYEE_ID but different SALARY values. Each returned row represents one row version.

### 1.1 Difference from a standard SELECT

A standard SELECT reads the current state:

~~~sql
SELECT employee_id, salary
FROM employees
WHERE employee_id = 100;
~~~

Flashback Versions Query reads row versions within a range:

~~~sql
SELECT employee_id,
       salary,
       versions_startscn,
       versions_endscn,
       versions_operation
FROM employees
VERSIONS BETWEEN SCN 100000 AND 200000
WHERE employee_id = 100
ORDER BY versions_startscn;
~~~

### 1.2 Each result row is one row version

Suppose an employee's salary changed:

~~~text
SCN 100: INSERT salary = 5000
SCN 150: UPDATE salary = 6000
SCN 190: UPDATE salary = 7000
SCN 230: DELETE employee
~~~

Within a range covering those changes, Versions Query can return the corresponding versions:

| Version | SALARY value | Operation creating version | Illustrative lifespan |
|---|---:|---|---|
| V1 | 5000 | I | SCN 100 to before 150 |
| V2 | 6000 | U | SCN 150 to before 190 |
| V3 | 7000 | U | SCN 190 to before 230 |
| V4 | Row value prior to deletion | D | Version associated with the DELETE operation |

This table illustrates the row version concept. NULL values in boundary pseudocolumns and how versions appear depend on the query range and the history remaining in UNDO.

## 2. VERSIONS BETWEEN syntax

There are two ways to specify the range:

- SCN: using System Change Numbers.
- TIMESTAMP: using clock time.

### 2.1 Querying by SCN

~~~sql
SELECT employee_id,
       salary
FROM employees
VERSIONS BETWEEN SCN 100000 AND 200000
WHERE employee_id = 100;
~~~

SCN is a logical database anchor, well suited when determining recovery boundaries or correlating with logs/transactions.

### 2.2 Querying by timestamp

~~~sql
SELECT employee_id,
       salary
FROM employees
VERSIONS BETWEEN TIMESTAMP
    TO_TIMESTAMP('2026-11-14 09:00:00',
                 'YYYY-MM-DD HH24:MI:SS')
AND TO_TIMESTAMP('2026-11-14 10:00:00',
                 'YYYY-MM-DD HH24:MI:SS')
WHERE employee_id = 100;
~~~

Timestamps are easier for operators to read, but mapping timestamps to SCNs has accuracy and range limits depending on metadata Oracle still retains. When exact boundaries are needed, record the SCN at critical business moments.

### 2.3 Using TIMESTAMP literals

You can use timestamp literals:

~~~sql
SELECT employee_id,
       salary
FROM employees
VERSIONS BETWEEN TIMESTAMP
    TIMESTAMP '2026-11-14 09:00:00'
AND TIMESTAMP '2026-11-14 10:00:00'
WHERE employee_id = 100;
~~~

Ensure the timestamp type and time zone align with business requirements. If the application, database, and operations teams use different time zones, document the time convention explicitly.

### 2.4 Getting the current SCN

You can retrieve the current SCN with:

~~~sql
SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS current_scn
FROM dual;
~~~

To bracket an operation, capture the SCN before and after the operation in the same database:

~~~sql
SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS scn_before
FROM dual;

-- Perform the operation to be tracked and COMMIT.

SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS scn_after
FROM dual;
~~~

SCNs read before/after serve as reference points. A transaction may commit at a different SCN from when a statement started; use commit/transaction metadata when precise investigation is required.

## 3. Pseudocolumns of Versions Query

Oracle provides pseudocolumns to describe each row version:

| Pseudocolumn | Meaning |
|---|---|
| VERSIONS_STARTSCN | SCN at which the row version started |
| VERSIONS_STARTTIME | Timestamp corresponding to when the version started |
| VERSIONS_ENDSCN | SCN at which the row version ended/was superseded |
| VERSIONS_ENDTIME | Timestamp corresponding to when the version ended |
| VERSIONS_XID | Transaction ID that created the row version |
| VERSIONS_OPERATION | Type of operation that created the version: I, U, or D |

These pseudocolumns are meaningful only in a query block using VERSIONS BETWEEN. They are not physical columns stored in the table.

### 3.1 VERSIONS_STARTSCN

VERSIONS_STARTSCN indicates the starting SCN of the row version.

If the version already started before the lower bound of the query range, its value may be NULL because the creation time lies outside the requested range.

### 3.2 VERSIONS_ENDSCN

VERSIONS_ENDSCN indicates the SCN at which the version ended or was superseded by the next version.

If the version is still active at the upper bound of the query range, its value may be NULL.

### 3.3 STARTTIME and ENDTIME

VERSIONS_STARTTIME and VERSIONS_ENDTIME are the timestamp equivalents of the row version boundaries. They are useful for reading results visually, though SCN is generally better when correlating with recovery or transaction metadata.

### 3.4 VERSIONS_XID

VERSIONS_XID is the transaction identifier of the transaction that created the row version. One transaction can modify multiple rows; versions created by the same transaction share the same XID.

XID does not directly reveal the end-user name, application module, or business actor. For further detail, correlate with other sources if that information still exists and the querying user has privileges.

### 3.5 VERSIONS_OPERATION

VERSIONS_OPERATION describes the operation associated with the version:

- I: INSERT.
- U: UPDATE.
- D: DELETE.

With UPDATE, a new version is created and the previous version expires. With DELETE, Versions Query can return the row version associated with the delete operation within the queried range.

Do not treat this pseudocolumn as a complete audit record. It does not by itself provide change justification, the original SQL text, the application user, or request payload.

## 4. Querying the full history of a row

Suppose we have the EMPLOYEES table:

~~~sql
CREATE TABLE employees (
    employee_id   NUMBER PRIMARY KEY,
    employee_name VARCHAR2(100),
    department_id NUMBER,
    salary        NUMBER(12,2)
);
~~~

Query the history of one employee:

~~~sql
SELECT employee_id,
       employee_name,
       department_id,
       salary,
       versions_startscn,
       versions_endscn,
       versions_starttime,
       versions_endtime,
       versions_xid,
       versions_operation
FROM employees
VERSIONS BETWEEN SCN :scn_from AND :scn_to
WHERE employee_id = :employee_id
ORDER BY versions_startscn NULLS FIRST,
         versions_starttime NULLS FIRST;
~~~

This is a common query pattern when investigating a primary key. Replace the binds with the actual SCNs and EMPLOYEE_ID.

### 4.1 Always filter by business key

If the table has a primary key, use it to select the target row. Avoid relying solely on ROWID as a long-term identifier:

- ROWID can change after move, shrink, export/import, or segment reorganization.
- A primary key represents the logical identity of the row.
- Versions Query can return multiple versions with the same primary key; that is precisely what you want to observe.

### 4.2 Ordering results

Sort by VERSIONS_STARTSCN and primary key to observe the progression of changes. If a version has a NULL STARTSCN, place NULLS FIRST so the version that already existed before the lower bound appears first.

Do not rely on default return order; SQL does not guarantee ordering without ORDER BY.

## 5. INSERT, UPDATE, and DELETE example

Execute in a lab schema:

~~~sql
CREATE TABLE employee_history_demo (
    employee_id NUMBER PRIMARY KEY,
    employee_name VARCHAR2(100),
    salary NUMBER(12,2)
);
~~~

Insert a row:

~~~sql
INSERT INTO employee_history_demo
    (employee_id, employee_name, salary)
VALUES
    (101, 'An', 5000);

COMMIT;
~~~

First update:

~~~sql
UPDATE employee_history_demo
SET salary = 6000
WHERE employee_id = 101;

COMMIT;
~~~

Second update:

~~~sql
UPDATE employee_history_demo
SET salary = 7000
WHERE employee_id = 101;

COMMIT;
~~~

Delete the row:

~~~sql
DELETE FROM employee_history_demo
WHERE employee_id = 101;

COMMIT;
~~~

Query the versions:

~~~sql
SELECT employee_id,
       employee_name,
       salary,
       versions_startscn,
       versions_endscn,
       versions_xid,
       versions_operation
FROM employee_history_demo
VERSIONS BETWEEN TIMESTAMP
    SYSTIMESTAMP - INTERVAL '1' HOUR
AND SYSTIMESTAMP
WHERE employee_id = 101
ORDER BY versions_startscn;
~~~

If enough UNDO remains and Flashback Query limits are satisfied, the result can show the salary values across versions and the associated operations. If the data has exceeded the UNDO retention window, the query may not return full history.

### 5.1 Why is COMMIT required?

Flashback Versions Query serves to view committed historical versions. Uncommitted changes from another session are not stable historical versions to be queried like completed commits.

If a transaction updates and then rolls back, the rolled-back change does not become a committed historical row version.

## 6. Reading results by row version lifecycle

Suppose a row has three committed versions:

~~~text
Version A: salary 5000
  STARTSCN = 100
  ENDSCN   = 150
  OPERATION = I

Version B: salary 6000
  STARTSCN = 150
  ENDSCN   = 190
  OPERATION = U

Version C: salary 7000
  STARTSCN = 190
  ENDSCN   = NULL
  OPERATION = U
~~~

Interpretation:

- Version A was created by INSERT and existed until the UPDATE created Version B.
- Version B was created by the first UPDATE and existed until the next UPDATE.
- Version C is the current version at the upper bound of the query, so ENDSCN can be NULL.

This is an explanatory model. Actual SCNs are assigned by the database; exact boundaries must be read from the query output.

### 6.1 Row created before the query range

If a row already existed prior to the starting SCN, the first row version may have a NULL VERSIONS_STARTSCN because its creation time preceded the lower bound.

This does not mean the row has no history or had no creating transaction; it only means the creation boundary lies outside the requested range.

### 6.2 Row still exists at the end of the range

If a row version is still valid at the upper bound, VERSIONS_ENDSCN can be NULL. This is not a data error.

### 6.3 Deleted row

If a DELETE occurred within the range, Versions Query can return the version associated with the delete with VERSIONS_OPERATION = D. The displayed data is the row version tied to that operation, useful for inspecting values before the row disappeared.

After DELETE, a normal SELECT no longer returns that row, yet Versions Query can still show its historical versions within the UNDO window.

## 7. Filtering history by operation type

View only versions produced by UPDATE:

~~~sql
SELECT employee_id,
       salary,
       versions_startscn,
       versions_xid
FROM employees
VERSIONS BETWEEN SCN :scn_from AND :scn_to
WHERE versions_operation = 'U'
ORDER BY versions_startscn;
~~~

View only INSERT:

~~~sql
SELECT employee_id,
       employee_name,
       versions_startscn,
       versions_xid
FROM employees
VERSIONS BETWEEN SCN :scn_from AND :scn_to
WHERE versions_operation = 'I';
~~~

View only DELETE:

~~~sql
SELECT employee_id,
       employee_name,
       salary,
       versions_startscn,
       versions_xid
FROM employees
VERSIONS BETWEEN SCN :scn_from AND :scn_to
WHERE versions_operation = 'D';
~~~

The queries above are filtering examples. Versions may have NULL pseudocolumns at range boundaries, so do not use a single operation filter as sole proof of every operation that ever occurred.

## 8. Comparing SCN and TIMESTAMP

| Criterion | SCN | TIMESTAMP |
|---|---|---|
| Nature | Database logical anchor | Wall-clock time |
| Precision | Suitable as an internal/recovery anchor | Depends on timestamp-to-SCN mapping |
| Readability | Hard for operators to read | Easy to understand |
| Redo/recovery correlation | More direct | May require conversion |
| Risk | Capturing wrong SCN or wrong incarnation/context | Time zone, clock drift, and mapping |
| Use when | Investigating precisely by SCN | Investigating by business wall-clock time |

### 8.1 TIMESTAMP_TO_SCN

You can convert a timestamp to an SCN:

~~~sql
SELECT TIMESTAMP_TO_SCN(
           TO_TIMESTAMP('2026-11-14 09:30:00',
                        'YYYY-MM-DD HH24:MI:SS')
       ) AS target_scn
FROM dual;
~~~

The function works only within the timestamp-SCN mapping range Oracle still retains. Timestamp-to-SCN is an approximate metadata mapping, not an exact conversion for every historical instant.

### 8.2 SCN_TO_TIMESTAMP

~~~sql
SELECT SCN_TO_TIMESTAMP(:target_scn)
FROM dual;
~~~

The function returns an approximate timestamp corresponding to the SCN if mapping is still available. Do not treat the result as a commit timestamp accurate to the millisecond.

### 8.3 Time zones and clocks

When investigating an incident:

- Determine the database session time zone.
- Determine the application/log time zone.
- Verify whether hosts are NTP-synchronized.
- Record the SCN whenever possible at the time of the event.
- Do not compare timestamp strings while ignoring time zones.

## 9. How VERSIONS BETWEEN differs from AS OF

Flashback Query AS OF returns the table state at a single point:

~~~sql
SELECT employee_id,
       salary
FROM employees AS OF SCN :target_scn
WHERE employee_id = :employee_id;
~~~

Flashback Versions Query returns multiple row versions across a range:

~~~sql
SELECT employee_id,
       salary,
       versions_startscn,
       versions_endscn,
       versions_operation
FROM employees
VERSIONS BETWEEN SCN :scn_from AND :scn_to
WHERE employee_id = :employee_id;
~~~

| Question | Mechanism |
|---|---|
| What value did the row have at SCN X? | AS OF SCN |
| What value did the row have at time T? | AS OF TIMESTAMP |
| What versions did the row have between X and Y? | VERSIONS BETWEEN SCN |
| What versions existed between time T1 and T2? | VERSIONS BETWEEN TIMESTAMP |

AS OF is suited for viewing one snapshot. VERSIONS BETWEEN is suited for examining a progression of multiple versions.

## 10. Correlating VERSIONS_XID with transactions

VERSIONS_XID identifies the transaction that created the row version. You can use XID to locate transaction details in an appropriate metadata source.

One source Oracle provides is FLASHBACK_TRANSACTION_QUERY, depending on privileges and configuration:

~~~sql
SELECT xid,
       start_scn,
       commit_scn,
       start_timestamp,
       commit_timestamp,
       logon_user,
       operation,
       table_name,
       undo_sql
FROM flashback_transaction_query
WHERE xid = :xid;
~~~

This view can provide transaction information and UNDO_SQL under supported conditions. Queryability depends on privileges, supplemental logging, and retained metadata; not every transaction will have complete information.

### 10.1 Privileges to access transaction metadata

To view transaction metadata, a user may need SELECT ANY TRANSACTION along with read privileges on relevant views. This is a broad and sensitive privilege; only DBAs or approved roles should receive it.

To run Versions Query on a table, a user needs SELECT and appropriate FLASHBACK privileges on the object, or the corresponding system privilege per policy:

~~~sql
GRANT SELECT ON employees TO analyst;
GRANT FLASHBACK ON employees TO analyst;
~~~

Do not grant FLASHBACK ANY TABLE or SELECT ANY TRANSACTION to an application solely to support one historical report.

### 10.2 XID is not complete user identity

XID identifies a transaction at the database layer. It does not necessarily tell you which end user clicked which button or which HTTP request arrived. When correlation is needed, the application should attach MODULE, ACTION, CLIENT_IDENTIFIER, and an auditing system following security conventions.

### 10.3 UNDO_SQL is not a safe replay script

UNDO_SQL can be helpful for understanding the inverse operation at the SQL layer. Do not execute batches of UNDO_SQL directly in production without checking:

- Transaction ordering.
- Foreign keys and triggers.
- Side effects outside the database.
- Sequences or package state.
- Subsequent changes to the data.
- Current business rules.

UNDO_SQL is investigative data, not a substitute for a controlled recovery process.

## 11. UNDO and history retention time

Flashback Versions Query relies on UNDO information to reconstruct prior versions. Oracle stores UNDO in the undo tablespace and reuses it according to undo management mechanisms.

Factors affecting historical visibility:

- UNDO_RETENTION.
- Undo tablespace capacity.
- Transaction/DML rate.
- Query duration.
- Retention guarantee if configured.
- Operations that alter table structure.

### 11.1 UNDO_RETENTION

Check:

~~~sql
SHOW PARAMETER undo_retention;
~~~

UNDO_RETENTION is the target undo retention time in automatic undo management. It is not an absolute guarantee that every version will survive for that many seconds if space is scarce.

### 11.2 RETENTION GUARANTEE

An undo tablespace can be configured with retention guarantee when undo must be retained longer:

~~~sql
ALTER TABLESPACE undotbs1 RETENTION GUARANTEE;
~~~

When guarantee is enabled, Oracle prioritizes preserving unexpired undo; if the undo tablespace runs out of space, DML operations may fail rather than overwriting retained undo.

Do not enable retention guarantee without calculating capacity, peak DML, and the risk of preventing the application from writing data.

You can check:

~~~sql
SELECT tablespace_name,
       retention
FROM dba_tablespaces
WHERE contents = 'UNDO';
~~~

### 11.3 ORA-01555 snapshot too old

If the undo required to reconstruct a version has been overwritten, the query may hit ORA-01555: snapshot too old.

Investigation checklist:

- Is the VERSIONS BETWEEN range too long?
- Is the query running too long?
- Is the DML volume high?
- Does the undo tablespace have enough space?
- Is UNDO_RETENTION appropriate?
- Is retention guarantee enabled?

Do not merely increase UNDO_RETENTION without inspecting capacity and undo generation rates.

### 11.4 History no longer in UNDO

Once UNDO has been reused, Flashback Versions Query cannot reconstruct complete row versions from the current table alone. When long-term history is required, use auditing, CDC, temporal/history tables, or a backup/recovery strategy.

## 12. Limitations and unsupported cases

Flashback Versions Query is not an unlimited historical archive. Important limitations:

- Row versions are queryable only while the required UNDO information remains available.
- DDL altering the table definition within the range can cause flashback queries to fail or be constrained.
- TRUNCATE and DDL operations are not represented like standard row-level INSERT/UPDATE/DELETE sequences.
- Certain object types or special tables have support restrictions.
- External tables, temporary tables, and structures without standard UNDO history are unsuitable for this query.
- Partition maintenance, move, exchange, or truncate partition operations can eliminate expected version queryability.
- If the table was created after the lower bound, or the object definition is incompatible with the queried time, errors may occur.

Check the Flashback Query documentation for your exact Oracle release before relying on the feature for a specific object type or DDL operation.

### 12.1 DDL and ORA-01466

If an object's definition changed within the flashback interval, Oracle may be unable to read data using a consistent definition for that point and return an error such as ORA-01466.

Do not treat Versions Query as a tool for recovering all DDL changes. DDL requires separate audit/deployment logs and a backup/recovery strategy.

### 12.2 TRUNCATE vs. DELETE

DELETE is DML and can produce row versions reflected in Flashback Versions Query while UNDO persists.

TRUNCATE is DDL and does not generate per-row history the way DELETE does. If a table is truncated, do not expect VERSIONS BETWEEN to list every pre-truncate row as a series of DELETE operations.

### 12.3 Uncommitted transactions

Versions Query is meant for committed version history. Open or rolled-back transactions should not be interpreted as complete committed history.

## 13. Analyzing multiple rows in the same transaction

A single transaction can update multiple rows:

~~~sql
UPDATE employees
SET department_id = 20
WHERE department_id = 10;

COMMIT;
~~~

Row versions created by the same transaction share the same VERSIONS_XID. You can group by XID to identify a set of changes belonging to the same transaction:

~~~sql
SELECT versions_xid,
       versions_operation,
       COUNT(*) AS row_count,
       MIN(versions_startscn) AS first_start_scn,
       MAX(versions_startscn) AS last_start_scn
FROM employees
VERSIONS BETWEEN SCN :scn_from AND :scn_to
GROUP BY versions_xid, versions_operation
ORDER BY first_start_scn;
~~~

This is an illustrative grouping technique. A single transaction may affect multiple tables; reconstructing the entire transaction requires querying related tables and transaction metadata, if still available.

## 14. Tracking changes across multiple columns

For example, when you need to inspect changes to SALARY and DEPARTMENT_ID:

~~~sql
SELECT employee_id,
       salary,
       department_id,
       versions_startscn,
       versions_endscn,
       versions_operation,
       versions_xid
FROM employees
VERSIONS BETWEEN TIMESTAMP
    SYSTIMESTAMP - INTERVAL '2' DAY
AND SYSTIMESTAMP
WHERE employee_id = :employee_id
ORDER BY versions_startscn;
~~~

Each version returns the row's values in that version. Compare consecutive versions to determine which columns changed.

### 14.1 Finding specific value changes

If you care only about SALARY, you can project:

~~~sql
SELECT employee_id,
       salary,
       versions_startscn,
       versions_operation,
       versions_xid
FROM employees
VERSIONS BETWEEN SCN :scn_from AND :scn_to
WHERE employee_id = :employee_id
ORDER BY versions_startscn;
~~~

SQL does not automatically generate an old_value/new_value pair per column. To compare old/new values, use analytic functions over the queried row versions or process results in the application.

## 15. Comparing versions with analytic functions

Example using LAG to compare salary with the previous version:

~~~sql
WITH history AS (
    SELECT employee_id,
           salary,
           versions_startscn,
           versions_operation,
           versions_xid
    FROM employees
    VERSIONS BETWEEN SCN :scn_from AND :scn_to
    WHERE employee_id = :employee_id
)
SELECT employee_id,
       versions_startscn,
       versions_operation,
       salary,
       LAG(salary) OVER (
           PARTITION BY employee_id
           ORDER BY versions_startscn
       ) AS previous_salary
FROM history
ORDER BY versions_startscn;
~~~

LAG shows the value in the preceding version ordered by SCN. For versions with NULL STARTSCN, define how NULL ordering should be handled. If multiple row versions share the same SCN, add a suitable tie-breaker sort key and do not assume a single SCN always defines a unique business order in all cases.

### 15.1 Computing deltas

You can add:

~~~sql
salary - LAG(salary) OVER (
    PARTITION BY employee_id
    ORDER BY versions_startscn
) AS salary_delta
~~~

This delta is the difference between two adjacent row versions in the result set. It does not by itself explain the business reason.

## 16. Viewing delete history and investigating mistaken deletes

Suppose row CUSTOMER_ID = 500 was deleted by mistake. If enough UNDO remains:

~~~sql
SELECT customer_id,
       customer_name,
       email,
       versions_startscn,
       versions_endscn,
       versions_operation,
       versions_xid
FROM customers
VERSIONS BETWEEN TIMESTAMP
    SYSTIMESTAMP - INTERVAL '1' DAY
AND SYSTIMESTAMP
WHERE customer_id = 500
ORDER BY versions_startscn;
~~~

The result can show the last version before deletion and operation D.

### 16.1 Recovering a single row using historical data

Once the correct pre-DELETE values are confirmed, you can consider re-INSERTing the row with those observed values, provided you:

- Verify all required columns.
- Check foreign keys.
- Check triggers.
- Check sequences/identity columns.
- Check related data in child tables.
- Confirm no valid transaction modified the state afterward.
- Obtain business approval.

Do not mechanically copy historical query results into an INSERT.

### 16.2 Recovering with Flashback Table

If an entire table needs to be returned to a point in time, Flashback Table is a separate mechanism with its own scope and prerequisites. Flashback Versions Query only displays row version history; it does not write data back into the table.

## 17. Versions Query and Flashback Transaction Query

The two features serve different purposes:

| Feature | Role |
|---|---|
| Flashback Versions Query | Displays row versions within a range |
| Flashback Transaction Query | Displays transaction metadata and undo SQL information under supported conditions |

VERSIONS_XID acts as the bridge to locate the corresponding transaction. However, not every transaction has complete metadata in FLASHBACK_TRANSACTION_QUERY.

Some undo SQL details may require appropriate supplemental logging. Verify release conditions and configuration before relying on it in an audit process.

## 18. Versions Query is not an audit trail

Flashback Versions Query is useful for short-term investigation, but it is not a complete audit log.

| Requirement | Versions Query | Audit/CDC/history table |
|---|---|---|
| View previous row version values | Yes, if UNDO remains | Yes, if designed to capture them |
| View I/U/D operations | Has operation metadata | Can record detailed events |
| View transaction XID | Yes | Can store transaction context |
| Know the end user | Not fully provided automatically | Can attach identity/request |
| Know the business reason | No | Can record reason/business event |
| Retain for years | Not guaranteed | Can be designed for long retention |
| Tamper-resistant history | Not its purpose | Can be designed as immutable/off-host |
| Track DDL | Incomplete | Audit/deployment logs are better suited |

If compliance or forensic evidence is required, use Oracle auditing, CDC, application event logs, or history tables per policy. You can pair them with Versions Query for rapid investigation within the UNDO window.

## 19. Performance and how to write queries

Versions Query can be resource-intensive because Oracle must reconstruct versions from UNDO. Constrain:

- The SCN/time range.
- Primary key or partition key.
- The list of columns to view.
- The number of participating tables.

Avoid querying the entire history of a large table across a wide range when only one row is needed.

### 19.1 Filtering by key

~~~sql
SELECT employee_id,
       salary,
       versions_startscn,
       versions_operation
FROM employees
VERSIONS BETWEEN SCN :scn_from AND :scn_to
WHERE employee_id = :employee_id;
~~~

### 19.2 Selecting only needed columns

Avoid SELECT * when a table contains LOBs or many wide columns. Project only the columns under investigation to reduce returned data and improve readability.

### 19.3 Short query intervals

Start with a narrow window around the incident time, then widen if needed. Wide windows increase history reconstruction work and the risk of running out of UNDO.

### 19.4 Checking the plan

You can inspect execution plans using EXPLAIN PLAN or DBMS_XPLAN.DISPLAY_CURSOR as permitted. When measuring runtime, record SQL_ID, elapsed time, buffers, and time range. Do not assume Versions Query always uses the same index as a current SELECT.

## 20. Common errors

### ORA-01555: snapshot too old

Required UNDO is no longer sufficient to reconstruct the snapshot/row version.

Resolution steps:

- Narrow the VERSIONS BETWEEN range.
- Run the query sooner after the incident.
- Check UNDO_RETENTION and undo space.
- Check whether DML workload spiked.
- If long-term history is needed, design auditing/history tables instead of stretching UNDO indefinitely.

### ORA-01466: unable to read data - table definition has changed

The table definition changed within the flashback range or object metadata is incompatible.

Resolution steps:

- Check DDL/deployment logs.
- Determine the object definition at each point in time.
- Narrow the time range if possible.
- Use backup/recovery or another audit source when DDL falls inside the range.

### No rows returned

Possible reasons:

- No changes or versions existed within the range.
- Incorrect SCN/time range.
- Wrong primary key or filter.
- Undo has expired/been overwritten.
- The table/object does not support that query case.
- Insufficient SELECT/FLASHBACK privileges.

Do not conclude a row never existed just because the query returns 0 rows.

### VERSIONS_XID is NULL

Some boundaries/versions lie outside the range or lack corresponding transaction metadata in the output. Read STARTSCN/ENDSCN and query conditions before drawing conclusions.

## 21. Workflow for investigating a modified row

A practical workflow to follow:

1. Identify the row's primary key.
2. Determine the suspected time and time zone.
3. Obtain the SCN if logs/application markers captured one.
4. Choose a narrow SCN/time range.
5. Run VERSIONS BETWEEN and retrieve pseudocolumns.
6. Sort by STARTSCN.
7. Compare values across row versions.
8. Record VERSIONS_XID and VERSIONS_OPERATION.
9. If authorized, correlate XID with transaction metadata.
10. Cross-check audit/application logs to identify the actor and reason.
11. If recovery is needed, choose Flashback Table, controlled row re-insertion, or RMAN recovery depending on scope.
12. Preserve evidence and avoid modifying data before completing the investigation.

## 22. Practical example: finding who changed a salary?

Versions Query can reveal the transaction XID, timestamp, and salary values, though it does not by itself identify the end user. You can start with:

~~~sql
SELECT employee_id,
       salary,
       versions_startscn,
       versions_starttime,
       versions_xid,
       versions_operation
FROM employees
VERSIONS BETWEEN TIMESTAMP
    TO_TIMESTAMP('2026-11-14 08:00:00',
                 'YYYY-MM-DD HH24:MI:SS')
AND TO_TIMESTAMP('2026-11-14 12:00:00',
                 'YYYY-MM-DD HH24:MI:SS')
WHERE employee_id = 100
ORDER BY versions_startscn;
~~~

Then:

- Record the XID of the UPDATE version.
- Check transaction metadata if privileges and data remain.
- Search for MODULE/ACTION/CLIENT_IDENTIFIER in audit or application logs.
- Correlate with deployment/job/request timestamps.

If the application does not record identity/request context, it may be impossible to identify the end user from row versions alone.

## 23. Best practices

- Save primary keys and SCN/time markers for critical business operations when investigation may be needed.
- Run Versions Query promptly after an incident is detected, while UNDO remains available.
- Do not set UNDO_RETENTION excessively high without budgeting storage capacity.
- Do not enable RETENTION GUARANTEE without evaluating DML impact.
- Use auditing/CDC/history tables for long-term historical retention requirements.
- Maintain consistent application module/action/client identifier conventions.
- Protect FLASHBACK and SELECT ANY TRANSACTION privileges.
- Do not execute UNDO_SQL as an automated rollback script.
- Do not use Versions Query as a substitute for backup/restore.
- Record time zone and SCN in the incident record.

## 24. Self-check hands-on exercises

Run exercises in a lab schema using test data.

### Exercise 1 — Create history for one row

Create a demo table, INSERT, UPDATE twice, and DELETE; commit each operation.

### Exercise 2 — Query by SCN

Capture the SCN before/after the operations, query VERSIONS BETWEEN SCN, and record the versions.

### Exercise 3 — Query by timestamp

Query the same interval using VERSIONS BETWEEN TIMESTAMP. Compare with the SCN results and pay attention to time zones.

### Exercise 4 — Read pseudocolumns

Explain STARTSCN, ENDSCN, STARTTIME, ENDTIME, XID, and OPERATION for each version.

### Exercise 5 — Filter by operation

Filter for I, U, and D. Explain why DELETE can appear in Versions Query even though a current SELECT no longer sees the row.

### Exercise 6 — Multiple rows in one transaction

UPDATE multiple rows and COMMIT. Group results by VERSIONS_XID and compare row counts.

### Exercise 7 — Compare using LAG

Use analytic LAG to display the previous salary and calculate the delta between two row versions.

### Exercise 8 — Flashback AS OF

Compare a single AS OF SCN snapshot with multiple versions from VERSIONS BETWEEN.

### Exercise 9 — Transaction metadata

In an environment with granted privileges, try correlating VERSIONS_XID with FLASHBACK_TRANSACTION_QUERY. Note which fields may be NULL or unavailable.

### Exercise 10 — Undo retention

Monitor UNDO_RETENTION and query over a historical range. Observe conditions that can trigger ORA-01555 in the lab environment.

### Exercise 11 — DDL boundary

In a dedicated lab database, test making a DDL change between two anchors and observe flashback limitations. Do not perform on important data.

### Exercise 12 — Distinguish Versions Query from auditing

Create a table comparing information provided by Versions Query against information requiring application auditing/CDC to identify the actor, reason, and long-term history.

## 25. Checklist before using VERSIONS BETWEEN

**Query range**

- Use SCN or timestamp?
- Is the time zone unambiguous?
- Does the range fall within the window where UNDO is still available?
- Are there SCN markers before/after the event?

**Row identity**

- Is there a primary key?
- Is the right row filtered?
- Are there multiple versions for the same key?
- Are results sorted by STARTSCN?

**Metadata**

- Have STARTSCN/ENDSCN been read?
- Are boundary NULLs understood?
- Has OPERATION been checked?
- Has XID been recorded?
- Is transaction metadata correlation needed?

**Limitations**

- Was there DDL/TRUNCATE/partition maintenance within the range?
- Might undo have been overwritten?
- Is the object type supported?
- Are SELECT/FLASHBACK privileges sufficient?

**Investigation and recovery**

- Are there application/audit logs to identify the actor?
- Does history need to be retained long-term?
- Are backups available if broader recovery is needed?
- Is approval obtained before modifying/recovering data?

## 26. Remember

| Concept | Key point to remember |
|---|---|
| Flashback Versions Query | View multiple row versions within a range |
| VERSIONS BETWEEN SCN | Select range by SCN |
| VERSIONS BETWEEN TIMESTAMP | Select range by time |
| VERSIONS_STARTSCN | SCN when row version started |
| VERSIONS_ENDSCN | SCN when row version ended |
| VERSIONS_STARTTIME | Timestamp when version started |
| VERSIONS_ENDTIME | Timestamp when version ended |
| VERSIONS_XID | Transaction ID that created row version |
| VERSIONS_OPERATION | I, U, or D |
| AS OF SCN | State at a single SCN |
| TIMESTAMP_TO_SCN | Maps timestamp to SCN within supported range |
| UNDO_RETENTION | Target to retain UNDO, not an absolute guarantee under space shortage |
| RETENTION GUARANTEE | Preserves undo per retention; can cause DML errors when out of space |
| ORA-01555 | Required snapshot/row version is no longer in UNDO |
| ORA-01466 | Object definition changed within flashback range |
| FLASHBACK_TRANSACTION_QUERY | Transaction metadata/undo SQL under supported conditions |
| Audit/CDC | Solution for long-term history retention and actor/business context |

VERSIONS BETWEEN lets you trace the evolution of a row through row versions and SCN, timestamp, XID, and operation metadata. Use SCN when exact logical boundaries are required; use timestamp when investigating by clock time while accounting for time zone and mapping limits. Queryability depends on retained UNDO, FLASHBACK privileges, and object/DDL restrictions. This tool is highly valuable for short-term investigation, yet it is neither a long-term audit trail nor an automatic identifier of the end user. Combine Versions Query with transaction metadata, application context, auditing, and appropriate backup/recovery.
