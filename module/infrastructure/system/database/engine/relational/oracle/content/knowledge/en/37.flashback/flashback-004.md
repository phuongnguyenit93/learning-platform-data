# Flashback Transaction Query and Prerequisites for Accessing Transaction Information in Oracle Database

When a mistaken data change has been COMMITted, DBAs and development teams often need to answer several questions: which transaction modified the row, when did the change occur, which database user executed it, which tables did the transaction affect, and what SQL statements can reverse each operation?

Oracle provides **Flashback Transaction Query** to look up transaction metadata and SQL representing the inverse operations. This feature reads from the data dictionary view FLASHBACK_TRANSACTION_QUERY. The view provides the transaction ID (XID), start/commit timestamps, logon user, operation, table, ROWID, and UNDO_SQL.

In practice, Flashback Transaction Query is commonly used alongside **Flashback Version Query**. Version Query finds row versions within an SCN or timestamp range and supplies the VERSIONS_XID pseudocolumn. Using that XID, the DBA queries FLASHBACK_TRANSACTION_QUERY to inspect all changes recorded in the transaction.

To use this feature, the database must have **minimal supplemental logging** enabled and COMPATIBLE set to an appropriate level. The querying user needs the SELECT ANY TRANSACTION system privilege—a powerful privilege because it permits viewing transaction information across the entire database. To execute the UNDO_SQL statements, the user also needs appropriate DML privileges on the specific tables.

This document focuses on Flashback Transaction Query and the prerequisites for accessing transaction information. Distinguish it from Flashback Transaction Backout: Query is used to investigate and view inverse SQL; Backout is a separate recovery feature that executes compensating transactions and has additional configuration requirements.

## 1. Flashback Transaction Query within the Flashback family

Oracle Flashback Technology includes multiple features with distinct purposes. They can be combined in an investigation workflow, though they do not replace one another.

| Feature | Purpose | How it is used |
|---|---|---|
| Flashback Query | View data at a past SCN/timestamp | SELECT ... AS OF SCN/TIMESTAMP |
| Flashback Version Query | View row versions across a time range | VERSIONS BETWEEN SCN/TIMESTAMP |
| Flashback Transaction Query | View metadata and inverse SQL for a transaction | Query FLASHBACK_TRANSACTION_QUERY |
| Flashback Transaction Backout | Back out a transaction and dependent transactions while the database is online | DBMS_FLASHBACK.TRANSACTION_BACKOUT |
| Flashback Table | Return one or more tables to a prior state | FLASHBACK TABLE ... TO SCN/TIMESTAMP |
| Flashback Database | Return the entire database to a prior SCN/timestamp | Flashback Database with flashback logs |

### 1.1 Role of Flashback Transaction Query

Suppose a user reports that an order was deleted by mistake. The DBA can:

1. Use Flashback Query or Version Query to determine the row state before and after the change.
2. Retrieve VERSIONS_XID of the transaction that performed the erroneous operation.
3. Query FLASHBACK_TRANSACTION_QUERY by XID.
4. Inspect the user, timestamp, operation, table, and UNDO_SQL.
5. Assess the impact on other tables within the same transaction.
6. Choose an appropriate recovery method and test before execution.

Flashback Transaction Query is an investigative tool. Seeing UNDO_SQL does not mean Oracle has automatically reversed the transaction.

### 1.2 Distinguishing Query and Backout

The two feature names are similar, but their purposes differ:

- **Flashback Transaction Query:** Reads transaction information and displays SQL representing the logical inverse of each DML operation.
- **Flashback Transaction Backout:** Uses DBMS_FLASHBACK.TRANSACTION_BACKOUT to generate and execute compensating transactions, capable of handling dependencies between transactions.

Backout requires additional archiving and supplemental logging prerequisites. Do not take Backout's prerequisite checklist and mistakenly apply it to Query operations.

## 2. The FLASHBACK_TRANSACTION_QUERY view

FLASHBACK_TRANSACTION_QUERY is a static data dictionary view providing information about transactions accessible via Flashback Transaction Query.

### 2.1 Key columns

| Column | Data type | Meaning |
|---|---|---|
| XID | RAW(8) | Transaction identifier |
| START_SCN | NUMBER | SCN when the transaction started |
| START_TIMESTAMP | DATE | Timestamp when the transaction started |
| COMMIT_SCN | NUMBER | SCN when the transaction committed; NULL for active transactions |
| COMMIT_TIMESTAMP | DATE | Commit timestamp; NULL for active transactions |
| LOGON_USER | VARCHAR2(128) | Database logon user that executed the transaction |
| UNDO_CHANGE# | NUMBER | Sequence/identifier of the undo change within the transaction |
| OPERATION | VARCHAR2(32) | Original DML operation |
| TABLE_NAME | VARCHAR2(256) | Affected table |
| TABLE_OWNER | VARCHAR2(386) | Schema owning the table |
| ROW_ID | VARCHAR2(19) | ROWID of the affected row |
| UNDO_SQL | VARCHAR2(4000) | SQL representing the logical inverse of the original DML |

### 2.2 OPERATION values

Values described in the Database Reference:

| OPERATION | Meaning |
|---|---|
| D | DELETE |
| I | INSERT |
| U | UPDATE |
| B | Transaction BEGIN marker |
| UNKNOWN | Operation not classified under the displayed groups |

A transaction typically has multiple rows in this view because each undo change can generate a metadata row. There may be a B row representing the start of the transaction rather than a table DML.

### 2.3 XID is the primary lookup key

XID has type RAW(8). When you know the XID as a hexadecimal string, convert it to RAW using HEXTORAW:

~~~sql
SELECT xid,
       operation,
       table_owner,
       table_name,
       row_id,
       undo_sql
FROM flashback_transaction_query
WHERE xid = HEXTORAW('000200030000002D');
~~~

The XID string in the example is illustrative data only. In practice, obtain the XID from VERSIONS_XID or a verified investigative source—never guess an XID.

### 2.4 Avoid querying the entire view unnecessarily

Oracle notes that querying FLASHBACK_TRANSACTION_QUERY without specifying XID in the WHERE clause can scan many unrelated transaction rows and degrade performance.

Prefer filtering by XID:

~~~sql
WHERE xid = :p_xid
~~~

If investigating by time range, use Version Query to find relevant XIDs first, then query transaction metadata per XID. Do not use an unconstrained query as a routine polling mechanism.

## 3. Database configuration prerequisites

Oracle Database 19c specifies two direct configuration prerequisites for Flashback Transaction Query:

1. The database must run with COMPATIBLE at 10.0 or higher.
2. At least minimal supplemental logging must be enabled.

These are the prerequisites for Flashback Transaction Query. Requirements such as ARCHIVELOG, primary key supplemental logging, and foreign key supplemental logging belong to Flashback Transaction Backout or other specific LogMiner/recovery objectives.

### 3.1 Checking COMPATIBLE

~~~sql
SHOW PARAMETER compatible;
~~~

Or:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'compatible';
~~~

Oracle documentation requires compatibility 10.0.0 or higher to configure Flashback Transaction Query. On modern database releases, the default value usually meets this requirement, though you should still check if a system retains a lower COMPATIBLE setting after an upgrade.

### 3.2 Enabling minimal supplemental logging

Command executed by a DBA:

~~~sql
ALTER DATABASE ADD SUPPLEMENTAL LOG DATA;
~~~

Minimal supplemental logging adds necessary information to redo to support change extraction operations. It can introduce additional redo overhead and must be evaluated within the database's operational and logging policy.

Do not enable supplemental logging after an incident occurs and expect historical redo data to be retroactively enriched. Logging only records supplemental details for changes generated after it is enabled.

### 3.3 Checking supplemental logging

~~~sql
SELECT supplemental_log_data_min,
       supplemental_log_data_pk,
       supplemental_log_data_ui,
       supplemental_log_data_fk
FROM v$database;
~~~

SUPPLEMENTAL_LOG_DATA_MIN reflects the status of minimal supplemental logging. The PK/UI/FK columns show specific supplemental logging groups. Column names may vary by release; verify against the Database Reference for your running version.

### 3.4 Enabling logging at database or table scope?

Configuration prerequisites in the Flashback Transaction Query documentation require database-level minimal supplemental logging. Additional supplemental logging for primary key, unique index, or foreign key columns may be needed for other LogMiner/transaction dependency goals.

Do not enable every logging group blindly just because you use Flashback Transaction Query. Identify the goal:

- Querying metadata/UNDO_SQL only: start with minimal supplemental logging as required by the documentation.
- Transaction backout with dependencies: requires primary key logging and potentially foreign key logging.
- CDC/LogMiner or replication: follow the specific requirements of that technology.

## 4. Access requirements and required privileges

### 4.1 SELECT ANY TRANSACTION

Oracle requires the system privilege:

~~~sql
GRANT SELECT ANY TRANSACTION TO flash_txn_auditor;
~~~

This privilege allows querying the contents of FLASHBACK_TRANSACTION_QUERY. It is a powerful privilege because the grantee can inspect transaction details across the entire database, including historical data. Grant it only to DBAs or authorized investigative accounts—never broadly to ordinary application users.

It can be granted through a dedicated role:

~~~sql
CREATE ROLE flash_txn_query_role;

GRANT SELECT ANY TRANSACTION TO flash_txn_query_role;

GRANT flash_txn_query_role TO flash_txn_auditor;
~~~

The role must be enabled in the session according to how the application or DBA connects. With definer-rights PL/SQL, privileges via roles do not substitute for direct grants in all contexts; verify the unit's privilege model if querying the view inside stored code.

### 4.2 Privileges to execute UNDO_SQL

To read UNDO_SQL, the user needs SELECT ANY TRANSACTION. To execute the generated SQL, Oracle requires SELECT, UPDATE, DELETE, and INSERT privileges on the specific tables involved.

Example for one table:

~~~sql
GRANT SELECT, INSERT, UPDATE, DELETE
ON app.orders
TO flash_txn_operator;
~~~

Grant privileges only on tables that genuinely need recovery. Do not grant INSERT ANY TABLE, UPDATE ANY TABLE, or DELETE ANY TABLE merely for convenience when running undo SQL.

### 4.3 Access privilege does not imply recovery privilege

Roles can be separated:

| Role | Appropriate privileges |
|---|---|
| Investigative auditor | SELECT ANY TRANSACTION, necessary read privileges |
| Analytical DBA | Dictionary/monitoring privileges per DBA policy |
| Recovery operator | DML privileges on approved tables; additional privileges if using Backout |
| Business application | Should not hold SELECT ANY TRANSACTION just for normal functionality |

An account can view UNDO_SQL without being permitted to execute it. This separates investigative access from data modification privileges.

### 4.4 Unified Auditing starting in 19c RU 19.32

Starting in Oracle Database 19c Release Update 19.32, unified auditing records the use of the SELECT ANY TRANSACTION system privilege when accessing FLASHBACK_TRANSACTION_QUERY. This feature gives administrators better audit visibility into accesses to historical transaction data via this powerful privilege.

If the system runs on an earlier RU, do not assume this auditing behavior exists. Check the release update and active unified auditing policies.

## 5. Finding XID with Flashback Version Query

In many situations, the DBA knows the modified table and row but does not yet know the transaction ID. Flashback Version Query can locate row versions and return VERSIONS_XID, VERSIONS_OPERATION, VERSIONS_STARTSCN, and VERSIONS_ENDSCN.

### 5.1 VERSIONS BETWEEN syntax

~~~sql
SELECT versions_startscn,
       versions_endscn,
       versions_xid,
       versions_operation,
       employee_id,
       salary
FROM employees
VERSIONS BETWEEN SCN MINVALUE AND MAXVALUE
WHERE employee_id = :p_employee_id;
~~~

VERSIONS BETWEEN SCN MINVALUE AND MAXVALUE requests all row versions still accessible within the current undo range. In real environments, constrain the query with specific SCNs or timestamps to avoid scanning too broad a range.

### 5.2 Finding changes within a time interval

~~~sql
SELECT versions_starttime,
       versions_endtime,
       versions_xid,
       versions_operation,
       order_id,
       status,
       total_amount
FROM orders
VERSIONS BETWEEN TIMESTAMP
    TO_TIMESTAMP('2026-11-14 08:00:00', 'YYYY-MM-DD HH24:MI:SS')
AND TO_TIMESTAMP('2026-11-14 10:00:00', 'YYYY-MM-DD HH24:MI:SS')
WHERE order_id = :p_order_id
ORDER BY versions_starttime;
~~~

The timestamps in the example are illustrative. Use timestamps aligned with the database's time zone and clock. If exact database-change boundaries are needed, use SCN.

### 5.3 Meaning of VERSIONS_OPERATION

| Value | Meaning |
|---|---|
| I | Row version created by INSERT |
| U | Row version created by UPDATE |
| D | Row version associated with DELETE |

The VERSIONS_OPERATION pseudocolumn describes the operation that produced the returned row version. For DELETE, the displayed version is the row data before deletion. Certain index key updates may appear as a DELETE plus an INSERT in Version Query.

### 5.4 VERSIONS_XID and transaction metadata

VERSIONS_XID is a RAW transaction identifier. It can be joined directly with FLASHBACK_TRANSACTION_QUERY:

~~~sql
SELECT DISTINCT
       ftq.xid,
       ftq.start_scn,
       ftq.commit_scn,
       ftq.logon_user,
       ftq.operation,
       ftq.table_owner,
       ftq.table_name,
       ftq.undo_sql
FROM flashback_transaction_query ftq
WHERE ftq.xid IN (
    SELECT versions_xid
    FROM orders VERSIONS BETWEEN SCN MINVALUE AND MAXVALUE
    WHERE order_id = :p_order_id
      AND versions_xid IS NOT NULL
);
~~~

This is the standard Oracle workflow: Version Query finds the XID of the row versions under investigation; Transaction Query provides the metadata for that transaction.

### 5.5 One transaction can modify multiple tables

Version Query on a single row only reveals the transaction that created that row's version. Once the XID is obtained, querying FLASHBACK_TRANSACTION_QUERY by XID can reveal other DML statements from the same transaction on other tables.

For example, one transaction might:

- Update ORDERS.
- Update INVENTORY.
- Insert into ORDER_AUDIT.
- Delete a staging row.
- Commit all changes in one transaction.

Investigating by XID identifies the transaction's full scope more completely than inspecting a single row.

## 6. Querying FLASHBACK_TRANSACTION_QUERY by XID

### 6.1 Querying details of a single transaction

~~~sql
SELECT xid,
       start_scn,
       start_timestamp,
       commit_scn,
       commit_timestamp,
       logon_user,
       undo_change#,
       operation,
       table_owner,
       table_name,
       row_id,
       undo_sql
FROM flashback_transaction_query
WHERE xid = HEXTORAW(:p_xid_hex)
ORDER BY undo_change#;
~~~

P_XID_HEX is a hexadecimal string obtained from a trusted source. If the application already holds the XID as RAW, bind it directly:

~~~sql
WHERE xid = :p_xid
~~~

Do not convert XID to VARCHAR2 for comparison when you can bind RAW with the proper type.

### 6.2 Viewing a transaction summary

~~~sql
SELECT xid,
       MIN(start_scn) AS start_scn,
       MAX(commit_scn) AS commit_scn,
       MIN(start_timestamp) AS start_timestamp,
       MAX(commit_timestamp) AS commit_timestamp,
       MAX(logon_user) AS logon_user,
       COUNT(CASE WHEN operation IN ('I', 'U', 'D') THEN 1 END)
           AS dml_change_count,
       COUNT(DISTINCT table_owner || '.' || table_name)
           AS affected_table_count
FROM flashback_transaction_query
WHERE xid = HEXTORAW(:p_xid_hex)
GROUP BY xid;
~~~

This summary helps orient the investigation. The BEGIN row is excluded from dml_change_count. If the transaction touches multiple schemas, preserve owner/table names separately to avoid confusing objects.

### 6.3 Filtering by schema and table

~~~sql
SELECT xid,
       start_timestamp,
       commit_timestamp,
       operation,
       table_owner,
       table_name,
       row_id,
       undo_sql
FROM flashback_transaction_query
WHERE xid = HEXTORAW(:p_xid_hex)
  AND table_owner = UPPER(:p_owner)
  AND table_name = UPPER(:p_table)
ORDER BY undo_change#;
~~~

Owner/table filters are helpful once you know the target scope, yet XID remains the most important filter to bound the transaction.

### 6.4 Active transactions

COMMIT_SCN and COMMIT_TIMESTAMP can be NULL for uncommitted transactions. Flashback Transaction Query is typically used to investigate completed transactions, though the metadata also describes active transactions when accessible. Do not treat a NULL commit timestamp as a data error if the transaction is still open.

### 6.5 LOGON_USER is not always the end user

LOGON_USER is the database user that logged in and executed the transaction. If an application uses a shared schema or connection pool, LOGON_USER may simply be APP_USER rather than the end user on a website.

To trace the business actor, the application must implement additional audit trails, unified auditing, CLIENT_IDENTIFIER, MODULE/ACTION, or appropriate request attributes. Flashback Transaction Query cannot automatically know the application-tier user if the database sees only a shared account.

## 7. UNDO_RETENTION and history limits

Flashback Version Query needs row versions that can still be reconstructed from undo. Therefore, when an investigation starts from a row and needs VERSIONS_XID, undo retention directly affects the ability to find the transaction ID.

### 7.1 Automatic Undo Management

Flashback features rely on Automatic Undo Management (AUM) and the undo tablespace to retain historical data. The DBA must ensure the undo tablespace is large enough for the rate of data modification and the required historical query window.

Check configuration:

~~~sql
SHOW PARAMETER undo;
~~~

Or:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name IN (
    'undo_management',
    'undo_tablespace',
    'undo_retention'
);
~~~

### 7.2 UNDO_RETENTION is a target, not an absolute guarantee

Setting UNDO_RETENTION specifies how long Oracle tries to retain undo. In a fixed-size undo tablespace, Oracle automatically tunes retention based on available space. With an autoextend undo tablespace, Oracle can retain undo longer to meet the retention threshold and long-running queries.

However, if the system runs short on space, Oracle may overwrite unexpired undo to serve new workload, unless the tablespace is configured with RETENTION GUARANTEE. Consequently, you cannot look solely at UNDO_RETENTION and assert with certainty that every version within that window remains queryable.

### 7.3 Checking tuned undo retention

~~~sql
SELECT begin_time,
       end_time,
       tuned_undoretention,
       undoblks,
       txncount,
       maxquerylen,
       ssolderrcnt,
       nospaceerrcnt
FROM v$undostat
ORDER BY begin_time DESC
FETCH FIRST 24 ROWS ONLY;
~~~

TUNED_UNDORETENTION helps the DBA estimate how long undo was actually retained across statistical intervals. UNDO_RETENTION and TUNED_UNDORETENTION are two distinct concepts.

### 7.4 RETENTION GUARANTEE

An undo tablespace can be configured with RETENTION GUARANTEE so Oracle will not overwrite unexpired undo. This protects the promised flashback window, at a trade-off: if the undo tablespace fills up, new DML statements may fail because undo cannot be written.

Example tablespace configuration:

~~~sql
ALTER TABLESPACE undotbs1 RETENTION GUARANTEE;
~~~

Only a DBA should alter this setting after evaluating capacity, workload, and the risk of impacting DML. Do not enable guarantee in production just to satisfy a flashback query without sizing capacity first.

### 7.5 Which part of the workflow does UNDO_RETENTION affect?

Distinguish two steps:

- **Finding XID via Flashback Version Query:** Depends on whether the required row versions can still be reconstructed from undo.
- **Looking up metadata by XID in FLASHBACK_TRANSACTION_QUERY:** Requires supplemental logging and still-available transaction metadata; querying by a known XID is not the same operation as reading a row version.

If undo history has expired, Version Query may fail to find the needed version or hit snapshot too old. In that case, check for the XID in audit/logs/other sources if available; raising UNDO_RETENTION now will not recreate undo that was already overwritten.

## 8. Reading and using UNDO_SQL

UNDO_SQL is SQL code representing the logical inverse of the DML in the transaction. Examples:

| Original DML | UNDO_SQL may represent |
|---|---|
| INSERT a row | DELETE that row |
| DELETE a row | Re-INSERT the old data |
| UPDATE a row | UPDATE reverting columns to prior values |

This is suggested SQL for the inverse operation, not a complete backup of the transaction.

### 8.1 UNDO_SQL is not always an exact physical inverse

Oracle warns that UNDO_SQL may not be the exact inverse operation in every case. For instance, when UNDO_SQL re-creates a DELETEd row, the new row might not receive the same ROWID as the original row.

Factors to consider:

- Triggers may fire again when executing the inverse SQL.
- Constraints or foreign keys may no longer be in the same state as when the original transaction ran.
- Related data may have been modified by subsequent transactions.
- Sequences, identity columns, external side effects, and application logic do not rewind automatically.
- One transaction may have altered multiple tables and created dependencies across changes.
- UNDO_SQL may reference ROWID; an old ROWID may no longer be valid after subsequent operations.

### 8.2 Never execute UNDO_SQL in bulk without review

Safe procedure:

1. Confirm the exact XID and transaction scope.
2. Read all rows of the transaction, including related tables.
3. Reconcile against current data state and subsequent transactions.
4. Check constraints, triggers, cascade rules, and side effects.
5. Take a backup or create an appropriate restore point beforehand.
6. Test on a clone/test database if possible.
7. Choose the recovery method: manual DML, Flashback Table, Flashback Transaction Backout, or another recovery method.
8. Execute in a controlled transaction, verify affected row counts, and commit under change management.

Do not copy all UNDO_SQL from the view into a SQL worksheet and run it directly in production.

### 8.3 Privileges to execute undo SQL

If a transaction touched APP.ORDERS, APP.INVENTORY, and APP.ORDER_AUDIT, the operator needs appropriate privileges on each table. Example:

~~~sql
GRANT SELECT, INSERT, UPDATE, DELETE
ON app.orders
TO flash_txn_operator;

GRANT SELECT, INSERT, UPDATE, DELETE
ON app.inventory
TO flash_txn_operator;

GRANT SELECT, INSERT, UPDATE, DELETE
ON app.order_audit
TO flash_txn_operator;
~~~

Grant privileges only on approved objects. If using Flashback Transaction Backout, EXECUTE privilege on the package and that feature's specific prerequisites are also required.

## 9. Workflow for investigating a faulty transaction

A typical workflow combining Flashback Version Query and Flashback Transaction Query:

~~~text
Erroneous data detected
        |
        v
Identify table, row key, and time range
        |
        v
Flashback Version Query
VERSIONS BETWEEN SCN/TIMESTAMP
        |
        v
Obtain VERSIONS_XID
        |
        v
FLASHBACK_TRANSACTION_QUERY
WHERE XID = ...
        |
        v
Read LOGON_USER, operation, table, ROWID, UNDO_SQL
        |
        v
Evaluate entire transaction and subsequent transactions
        |
        v
Select appropriate recovery method
        |
        v
Test, review, back up, and execute under control
~~~

### 9.1 Step 1: identify the row and time interval

Gather the primary key, table, schema, discovery time, and the last known good time. If only an approximate time is known, use a Version Query window narrow enough to limit the number of row versions.

### 9.2 Step 2: obtain the relevant XIDs

~~~sql
SELECT versions_startscn,
       versions_endscn,
       versions_xid,
       versions_operation,
       order_id,
       status,
       total_amount
FROM app.orders
VERSIONS BETWEEN TIMESTAMP
    TO_TIMESTAMP('2026-11-14 08:00:00', 'YYYY-MM-DD HH24:MI:SS')
AND TO_TIMESTAMP('2026-11-14 10:00:00', 'YYYY-MM-DD HH24:MI:SS')
WHERE order_id = :p_order_id
ORDER BY versions_startscn;
~~~

Record the XID of the faulty version. A row may have multiple versions and multiple XIDs if modified multiple times.

### 9.3 Step 3: inspect the entire transaction

~~~sql
SELECT xid,
       start_timestamp,
       commit_timestamp,
       logon_user,
       operation,
       table_owner,
       table_name,
       row_id,
       undo_sql
FROM flashback_transaction_query
WHERE xid = :p_xid
ORDER BY undo_change#;
~~~

This step reveals whether the transaction modified other tables. Do not recover only the first table discovered if the original transaction updated multiple objects.

### 9.4 Step 4: reconcile with current state

UNDO_SQL describes the inverse of the selected transaction's changes. Before using it, verify whether current data was modified by subsequent transactions. If a row received valid updates after the faulty transaction, applying old undo can erase those valid newer changes.

### 9.5 Step 5: choose the recovery tool

| Situation | Recovery option to consider |
|---|---|
| A few rows modified/deleted, no dependent changes | Use Flashback Query to fetch old values and run controlled DML |
| Many rows in one table, want to revert the entire table | Evaluate Flashback Table |
| A faulty transaction and dependent transactions must be handled | Evaluate Flashback Transaction Backout |
| Widespread data corruption or need to rewind the whole database | Evaluate point-in-time recovery / Flashback Database |
| Only need to identify actor and scope of changes | Flashback Transaction Query and audit logs |

Do not pick a method solely because UNDO_SQL is available. Evaluate dependencies, timing, subsequent data, and recovery objectives.

## 10. Flashback Transaction Backout: a different feature from Query

Flashback Transaction Backout is a recovery mechanism in the DBMS_FLASHBACK package. It can back out a transaction and dependent transactions while the database remains online by generating and executing compensating transactions.

Flashback Transaction Query only displays metadata and UNDO_SQL. It does not invoke Backout and does not execute SQL automatically.

### 10.1 Specific configuration prerequisites for Backout

According to Oracle Database 19c documentation, to use Flashback Transaction Backout, the DBA needs:

1. Enable ARCHIVELOG mode.
2. Archive at least one log.
3. Enable minimal supplemental logging.
4. Enable primary key supplemental logging.
5. If foreign key dependencies must be tracked, enable foreign key supplemental logging.

Illustrative commands:

~~~sql
ALTER DATABASE ADD SUPPLEMENTAL LOG DATA;
ALTER DATABASE ADD SUPPLEMENTAL LOG DATA (PRIMARY KEY) COLUMNS;
ALTER DATABASE ADD SUPPLEMENTAL LOG DATA (FOREIGN KEY) COLUMNS;
~~~

Foreign key supplemental logging can introduce overhead, especially in databases with many foreign key constraints. Enable it only when Backout's dependency analysis requires it.

Switching from NOARCHIVELOG to ARCHIVELOG requires the database to be in MOUNT state per administrative procedure:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
ALTER DATABASE ARCHIVELOG;
ALTER DATABASE OPEN;
ALTER SYSTEM ARCHIVE LOG CURRENT;
~~~

This is an operational maintenance task, not a mandatory step merely to read FLASHBACK_TRANSACTION_QUERY under 19c configuration.

### 10.2 Privileges to execute Backout

To use functions in DBMS_FLASHBACK, Oracle requires EXECUTE privilege on the package:

~~~sql
GRANT EXECUTE ON SYS.DBMS_FLASHBACK TO flash_txn_operator;
~~~

In addition, the operator needs relevant privileges to read metadata and perform operations on objects per approved workflow. Do not grant Backout privileges more broadly than necessary.

### 10.3 Dependencies between transactions

If transaction B depends on data created by transaction A, backing out A may require backing out B or resolving conflicts. DBMS_FLASHBACK.TRANSACTION_BACKOUT supports dependency options such as CASCADE, NONCONFLICT_ONLY, and NOCASCADE_FORCE depending on the scenario.

Do not pick NOCASCADE_FORCE simply to force backout to succeed. If a later transaction relied on data from the earlier transaction, forcing can create an inconsistent business state.

### 10.4 Limitations of Backout

The limitations below apply to Flashback Transaction Backout and should not be misapplied to conclude that FLASHBACK_TRANSACTION_QUERY cannot inspect transactions:

- Transactions containing DDL that alters a table's logical structure cannot be backed out by this mechanism.
- Transactions using LOB types such as BFILE, BLOB, CLOB, and NCLOB have documented limitations.
- Features unsupported by LogMiner cannot be fully processed.
- PDML and certain XA/RAC transaction branches may not be supported.
- AQ transactions may not be backed out because effects outside the database cannot be fully observed.

Before using Backout, verify limitations for your exact release, COMPATIBLE setting, and transaction types in the workload.

## 11. Lab: finding XID and viewing UNDO_SQL

The following lab demonstrates creating data, running a multi-DML transaction, finding the XID with Version Query, and querying metadata.

### 11.1 Prerequisites before running

- Run in a lab schema, not on production tables.
- The database has minimal supplemental logging enabled.
- COMPATIBLE satisfies Flashback Transaction Query requirements.
- The investigative account holds SELECT ANY TRANSACTION.
- The account has privileges to read the lab table and use Version Query as appropriate.

### 11.2 Create the table

~~~sql
CREATE TABLE flash_txn_lab (
    id          NUMBER PRIMARY KEY,
    description VARCHAR2(100),
    amount      NUMBER
);
~~~

After CREATE TABLE, Oracle recommends waiting at least 15 seconds before committing a transaction that needs to be reflected by Flashback Version Query. Wait that interval during the lab.

### 11.3 Insert initial data

~~~sql
INSERT INTO flash_txn_lab VALUES (1, 'Order A', 100);
INSERT INTO flash_txn_lab VALUES (2, 'Order B', 200);
INSERT INTO flash_txn_lab VALUES (3, 'Order C', 300);
COMMIT;
~~~

### 11.4 Execute a transaction with multiple changes

~~~sql
UPDATE flash_txn_lab
SET amount = 150,
    description = 'Order A updated'
WHERE id = 1;

DELETE FROM flash_txn_lab
WHERE id = 2;

INSERT INTO flash_txn_lab
    (id, description, amount)
VALUES
    (4, 'Order D', 400);

COMMIT;
~~~

All three DML statements run in the same session and transaction before COMMIT. The goal is to observe how one XID can encompass multiple changes.

### 11.5 Find the XID via Version Query

~~~sql
SELECT versions_startscn,
       versions_endscn,
       versions_xid,
       versions_operation,
       id,
       description,
       amount
FROM flash_txn_lab
VERSIONS BETWEEN SCN MINVALUE AND MAXVALUE
WHERE id IN (1, 2, 4)
ORDER BY versions_startscn;
~~~

Record the XID corresponding to the transaction just executed. Some rows may have multiple row versions; compare SCNs and operations to select the right XID.

### 11.6 Query transaction metadata

~~~sql
SELECT xid,
       start_scn,
       commit_scn,
       start_timestamp,
       commit_timestamp,
       logon_user,
       undo_change#,
       operation,
       table_owner,
       table_name,
       row_id,
       undo_sql
FROM flashback_transaction_query
WHERE xid = HEXTORAW(:p_xid_hex)
ORDER BY undo_change#;
~~~

The result can show UPDATE, DELETE, INSERT, and a BEGIN row. UNDO_SQL will contain statements that are the logical inverse of the executed DMLs.

### 11.7 Compare with current state

~~~sql
SELECT *
FROM flash_txn_lab
ORDER BY id;
~~~

Compare the current state with the historical versions. Do not execute UNDO_SQL in the lab without carefully reviewing ordering and effects; the goal of the lab is to observe metadata and understand the XID relationship.

### 11.8 Clean up lab data

~~~sql
DROP TABLE flash_txn_lab PURGE;
~~~

Run DROP TABLE only if this is the lab table just created and it contains no data worth keeping.

## 12. Common errors and troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| ORA-01031 insufficient privileges | Missing SELECT ANY TRANSACTION or object flashback privilege when running Version Query | Grant minimal required privileges for the feature being used |
| FLASHBACK_TRANSACTION_QUERY does not return expected transaction | Supplemental logging was not enabled when the transaction occurred, wrong XID, or metadata no longer available | Check supplemental logging, XID, and transaction timing |
| Version Query cannot find old row version | Undo was overwritten or time window is outside effective retention | Check V$UNDOSTAT, undo tablespace, and retention |
| ORA-01555 snapshot too old | Undo needed for consistent read/flashback was overwritten | Increase capacity/retention appropriately and narrow query window |
| Querying the view is too slow | Not filtering by XID | Obtain XID from Version Query first, then filter directly |
| UNDO_SQL is not as expected | UNDO_SQL is a logical opposite; does not always restore ROWID or side effects | Review constraints, triggers, current data, and dependent transactions |
| Cannot run UNDO_SQL | Missing DML privileges on the table or SQL no longer fits current state | Grant minimal object privileges after approval; re-evaluate SQL |
| LOGON_USER is not the end user | Application uses shared schema/connection pool | Use audit trail, CLIENT_IDENTIFIER, and MODULE/ACTION |
| Transaction before enabling supplemental logging not visible | Supplemental logging does not retroactively enrich old redo | Cannot fix historical data by enabling logging after the incident |
| Confusing Query with Backout | The two features have different configuration requirements and impacts | Use Query to investigate; Backout to execute compensating transactions |
| Backout reports conflict/dependency | Later transactions depend on the transaction being backed out | Analyze dependencies; choose CASCADE/NONCONFLICT_ONLY per procedure |

## 13. Security and operations

### 13.1 Protecting SELECT ANY TRANSACTION

SELECT ANY TRANSACTION is a powerful system privilege. You should:

- Grant it to a dedicated role, limited to approved DBA/auditor members.
- Never grant it to PUBLIC or ordinary application schemas.
- Periodically review users and roles holding the privilege.
- Audit privilege usage according to release and unified auditing policies.
- Never write UNDO_SQL output or sensitive historical data to unprotected logs.

### 13.2 Separating investigation from execution

A well-controlled process separates two accounts or roles:

- An investigative account that only reads transaction metadata and necessary data.
- A recovery operations account holding DML privileges only on approved objects, used only after change approval.

Role separation prevents a situation where someone authorized to view all history can simultaneously modify all data.

### 13.3 Supplemental logging and redo overhead

Supplemental logging increases redo volume because Oracle writes additional required information. Minimal logging is a configuration prerequisite for Flashback Transaction Query; primary key/foreign key groups can introduce significant overhead depending on workload.

Measure redo generation and archive throughput before and after changing logging. Coordinate with existing Data Guard, LogMiner, CDC, and recovery policies.

### 13.4 CDB/PDB

In multitenant environments, connect to the exact container holding the table under investigation and check privileges granted in the appropriate scope. For common/local privileges and transaction data in a PDB, follow the CDB's privilege-granting policy; do not assume a grant in root automatically equals a local grant in every context.

Check the current container:

~~~sql
SHOW CON_NAME;
~~~

Or:

~~~sql
SELECT sys_context('USERENV', 'CON_NAME') AS con_name
FROM dual;
~~~

When investigating across multiple PDBs, explicitly record the PDB/service and schema to avoid confusing identically named objects.

### 13.5 RAC

In RAC, transactions can originate from different instances. DBAs should record database/service/instance details in incident records and correlate transaction XIDs with other audit/monitoring sources. Never infer the executing instance solely from LOGON_USER.

XA transactions or PDML/RAC branches may face specific restrictions when using Flashback Transaction Backout; this does not mean all metadata queries via Flashback Transaction Query are excluded.

## 14. Checklist before querying or recovering a transaction

### Access prerequisites

1. Is the database running with COMPATIBLE 10.0 or higher?
2. Was minimal supplemental logging enabled before the transaction under investigation occurred?
3. Does the account hold SELECT ANY TRANSACTION?
4. If using Version Query, does the account have FLASHBACK and READ/SELECT on the object or the corresponding system privilege?
5. Are you connected to the right PDB/service?
6. If executing UNDO_SQL, have SELECT/INSERT/UPDATE/DELETE been granted on the exact tables?

### Historical data conditions

1. Have the table, row key, and SCN/timestamp range been identified?
2. Is the undo needed for Version Query still within effective retention?
3. Has V$UNDOSTAT.TUNED_UNDORETENTION been checked?
4. Is there a risk of snapshot too old or undo tablespace space shortage?
5. Is FLASHBACK_TRANSACTION_QUERY filtered by XID?
6. Have all tables and DML operations belonging to the transaction been inspected?
7. Does LOGON_USER represent the end user or merely an application schema?

### Before executing inverse SQL

1. Has every UNDO_SQL statement been reviewed?
2. Have transactions occurring after the faulty transaction been checked?
3. Have triggers, constraints, foreign keys, and side effects been evaluated?
4. Have ROWID and the current row state been verified?
5. Is there a suitable backup/restore point or rollback plan?
6. Has it been tested in a test/clone environment?
7. Is change approval obtained and the operator designated?
8. If using Backout, are ARCHIVELOG and the corresponding supplemental logging prerequisites met?

## 15. Summary

Flashback Transaction Query helps trace transaction metadata and SQL representing the inverse of executed DML operations:

- The central view is FLASHBACK_TRANSACTION_QUERY.
- XID is a RAW(8) transaction identifier, typically obtained via VERSIONS_XID from Flashback Version Query.
- Key metadata includes START_SCN, COMMIT_SCN, LOGON_USER, OPERATION, TABLE_OWNER, TABLE_NAME, ROW_ID, and UNDO_SQL.
- The database requires COMPATIBLE 10.0 or higher and minimal supplemental logging.
- The querying user needs SELECT ANY TRANSACTION; this is a powerful privilege and must be granted sparingly.
- To execute UNDO_SQL, SELECT/INSERT/UPDATE/DELETE privileges on the specific tables are required.
- Flashback Version Query depends on available undo; UNDO_RETENTION is not an absolute guarantee if the undo tablespace runs short on space.
- UNDO_SQL is only a logical opposite, not a perfect recovery script, and should never be executed in bulk without review.
- Flashback Transaction Backout is a different feature; it requires ARCHIVELOG, primary key supplemental logging, and potentially foreign key supplemental logging to resolve dependencies.

Good practice is to find the XID using Version Query, query transaction metadata by XID, determine the full scope of changes, and then choose the appropriate recovery tool after evaluating dependencies and privileges. Flashback Transaction Query provides the evidence for decision-making; data modification must still be controlled like a recovery operation.

## 16. Oracle reference documentation

- Oracle Database 19c Development Guide, “Using Oracle Flashback Transaction Query”: https://docs.oracle.com/en/database/oracle/oracle-database/19/adfns/flashback.html
- Oracle Database 19c Database Reference, “FLASHBACK_TRANSACTION_QUERY”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/FLASHBACK_TRANSACTION_QUERY.html
- Oracle Database 19c SQL Language Reference, “SELECT” and Flashback Version Query: https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html
- Oracle Database 19c SQL Language Reference, “GRANT”: https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/GRANT.html
- Oracle Database 19c PL/SQL Packages and Types Reference, “DBMS_FLASHBACK”: https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_FLASHBACK.html
- Oracle Database 19c Database Reference, “V$UNDOSTAT”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-UNDOSTAT.html
- Oracle Database 19c Error Messages, “ORA-54500 to ORA-56978”: https://docs.oracle.com/en/database/oracle/oracle-database/19/errmg/ORA-54500.html
