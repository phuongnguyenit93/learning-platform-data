# Metadata Visibility Privileges and Account-Based Restrictions

Metadata describes the structure and state of a database: schemas, tables, columns, indexes, constraints, views, routines, and certain operational details. In MySQL, metadata is not exposed in full to every account by default. Visibility depends on the privileges of the connected account, the object type, and the command or metadata table being queried.

This mechanism allows administrators to limit what structural information each application or user group is permitted to discover. An account with read access on only one table can view partial metadata for that table, without necessarily seeing the entire schema, view definitions, stored routines, or other sessions' activity.

In the **DATABASE_MYSQL** module, understanding metadata visibility helps design privilege models, build schema inspection tools, support migrations, conduct audits, and troubleshoot incidents. Clearly distinguish three questions: whether an account can see an object's name, whether it can view its detailed definition, and whether it can read or modify data.

## 1. What Is Metadata and Where Is It Accessed?

Metadata is data describing the database rather than business rows inside tables. Examples:

- **Schema:** database name and related attributes.
- **Table and view:** object name, engine, row format, creation or update timestamps.
- **Column:** column name, data type, nullability, default, collation, and ordinal position.
- **Index:** index name, participating columns, column order, and uniqueness.
- **Constraint:** primary key, foreign key, unique, and check constraints.
- **Routine and trigger:** name, object type, definer, status, and definition subject to privileges.
- **Operational metadata:** details on sessions, statements, locks, transactions, and instruments when provided via Performance Schema.

MySQL offers multiple interfaces to inspect metadata:

| Interface | Purpose |
|---|---|
| `SHOW DATABASES`, `SHOW TABLES`, `SHOW COLUMNS`, `SHOW INDEX` | Quick commands to inspect schemas, tables, columns, and indexes |
| `SHOW CREATE TABLE`, `SHOW CREATE VIEW` | View the definition statement of an object |
| `INFORMATION_SCHEMA` | Query structured metadata using SQL |
| `SHOW STATUS`, `SHOW VARIABLES` | Inspect server/session status and configuration |
| `performance_schema` | Observe activity, statements, sessions, waits, and locks |
| `sys` | Convenient views aggregating diagnostic data from Performance Schema and Information Schema |

These interfaces do not share the exact same purpose or visibility rules. In particular, `INFORMATION_SCHEMA` is not an unrestricted public copy of the data dictionary. Metadata rows are filtered by account privileges, and certain definition columns carry additional privilege requirements.

## 2. Privilege-Based Metadata Filtering Principle

MySQL applies the principle of **displaying only objects that the account holds appropriate privileges to know about or act upon**. As a result, two accounts querying the exact same metadata table can receive different results.

For example, an account with privileges on `appdb.orders` can see that table in listing commands and corresponding metadata queries. An account without privileges on a schema or table may not see that object in normal listings.

Distinguish clearly:

1. **Schema visibility:** determines whether the account can list a database.
2. **Object visibility:** affects the ability to list tables, views, columns, and indexes.
3. **Definition viewing privilege:** certain objects such as views or routines may require extra privileges to view definition bodies.
4. **Data usage privileges:** `SELECT`, `INSERT`, `UPDATE`, `DELETE`, and other privileges govern whether data operations are permitted.
5. **Server activity observation privileges:** session and statement information may require privileges such as `PROCESS` or privileges to read Performance Schema.

Seeing a table's name does not mean being permitted to read every row in that table. Conversely, a view granted `SELECT` can allow reading a restricted dataset even when the user lacks direct privileges on the underlying tables.

## 3. Database and Table Visibility

### 3.1. SHOW DATABASES

By default, `SHOW DATABASES` lists only schemas on which the account holds an appropriate privilege. An account with the global `SHOW DATABASES` privilege can list all schemas on the instance.

Example:

```sql
SHOW DATABASES;
```

An account granted privileges on a specific database can see that database without needing permission to list all schemas. Administrators can grant the global privilege if an audit or administrative role genuinely requires it:

```sql
GRANT SHOW DATABASES ON *.*
TO 'metadata_auditor'@'10.20.0.25';
```

`SHOW DATABASES` expands the scope of information an account can discover. Do not grant this privilege to every application just because it needs to connect to an already-known schema.

### 3.2. SHOW TABLES and INFORMATION_SCHEMA.TABLES

`SHOW TABLES` lists tables and views for which the account holds appropriate privileges in the specified or current schema.

```sql
SHOW TABLES FROM appdb;
```

You can query it structurally through `INFORMATION_SCHEMA.TABLES`:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    TABLE_TYPE,
    ENGINE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'appdb'
ORDER BY TABLE_NAME;
```

Results are filtered by the account's privileges. An account with privileges on `appdb.orders` can see that table's metadata, while other tables without privileges may not appear.

Do not use `SHOW TABLES` or `INFORMATION_SCHEMA.TABLES` results from a restricted account to conclude that a database has no other tables. To inventory an entire schema, use an audit account granted an intentional scope of privileges.

### 3.3. Column and index metadata

An account with appropriate privileges on a table can view column information with `SHOW COLUMNS`:

```sql
SHOW FULL COLUMNS FROM appdb.orders;
```

Or query `INFORMATION_SCHEMA.COLUMNS`:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    COLUMN_NAME,
    ORDINAL_POSITION,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    EXTRA
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'appdb'
  AND TABLE_NAME = 'orders'
ORDER BY ORDINAL_POSITION;
```

Index information can be viewed via:

```sql
SHOW INDEX FROM appdb.orders;
```

Or:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    INDEX_TYPE
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = 'appdb'
  AND TABLE_NAME = 'orders'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
```

Column and index metadata are useful for migration tools, schema diffs, and performance reviews. However, results still reflect the current account's privilege perspective. When automated tools perform schema discovery, run them using an account with sufficient privileges to read the required metadata.

## 4. Viewing View and Routine Definitions Requires Separate Privileges

View or routine names may appear in some metadata results while their definition bodies are not necessarily visible to every account.

### 4.1. Views and the SHOW VIEW privilege

The `SHOW VIEW` privilege allows viewing a view's definition. Example:

```sql
GRANT SHOW VIEW ON appdb.*
TO 'metadata_auditor'@'10.20.0.25';

SHOW CREATE VIEW appdb.order_summary;
```

View metadata can be queried via `INFORMATION_SCHEMA.VIEWS`:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    DEFINER,
    SECURITY_TYPE,
    IS_UPDATABLE,
    VIEW_DEFINITION
FROM INFORMATION_SCHEMA.VIEWS
WHERE TABLE_SCHEMA = 'appdb';
```

If the account lacks appropriate `SHOW VIEW` privilege, the `VIEW_DEFINITION` field may return `NULL`. This is an important boundary: seeing a view's name does not mean being permitted to see the SQL query defining the view.

The `SHOW VIEW` privilege does not automatically grant permission to read the data the view returns. Querying a view and viewing its definition are two separate privileges.

### 4.2. Stored procedures and functions

Routine metadata is provided via `INFORMATION_SCHEMA.ROUTINES`, along with commands such as `SHOW PROCEDURE STATUS`, `SHOW FUNCTION STATUS`, and `SHOW CREATE PROCEDURE`.

Starting in MySQL 8.0.20, the dynamic privilege `SHOW_ROUTINE` controls viewing stored routine definitions. An account may also hold routine-specific privileges such as `EXECUTE`, `ALTER ROUTINE`, or `CREATE ROUTINE`; definition visibility depends on the privilege combination and version. When configuring an audit account, check the exact version's documentation and grant routine-viewing privileges only when truly needed.

Example viewing general metadata:

```sql
SELECT
    ROUTINE_SCHEMA,
    ROUTINE_NAME,
    ROUTINE_TYPE,
    DEFINER,
    SECURITY_TYPE,
    SQL_DATA_ACCESS
FROM INFORMATION_SCHEMA.ROUTINES
WHERE ROUTINE_SCHEMA = 'appdb';
```

Do not grant privileges to view all routine definitions to a runtime account if the application only needs to call a single procedure on which it already holds `EXECUTE`.

## 5. Session and Server Activity Metadata

Database structural information differs from operational activity information. Tables in `performance_schema` and views in `sys` can contain SQL statements, usernames, hosts, thread states, locks, and wait events.

### 5.1. PROCESS and connection lists

Without the `PROCESS` privilege, a normal account sees only its own threads or connections in process list interfaces. An account with the global `PROCESS` privilege can inspect thread details for other users.

Example:

```sql
SHOW FULL PROCESSLIST;
```

Or:

```sql
SELECT
    THREAD_ID,
    PROCESSLIST_ID,
    PROCESSLIST_USER,
    PROCESSLIST_HOST,
    PROCESSLIST_DB,
    PROCESSLIST_COMMAND,
    PROCESSLIST_TIME,
    PROCESSLIST_STATE,
    PROCESSLIST_INFO
FROM performance_schema.threads
WHERE TYPE = 'FOREGROUND';
```

To read Performance Schema tables, an account needs appropriate `SELECT` privileges on those tables. The `PROCESS` privilege expands visibility into other accounts' threads in the process list. This is a sensitive privilege because displayed details can include SQL statements and operational data.

### 5.2. Reading locks and waits

Performance Schema provides tables such as `data_locks`, `data_lock_waits`, and `metadata_locks` for lock diagnostics. Example:

```sql
SELECT
    OBJECT_SCHEMA,
    OBJECT_NAME,
    INDEX_NAME,
    LOCK_TYPE,
    LOCK_MODE,
    LOCK_STATUS
FROM performance_schema.data_locks;
```

A diagnostic query returns only the information the account has privilege to read and that the system is currently instrumenting. Without `SELECT` privilege on the Performance Schema table, the query is denied; if there is no matching data or the instrument is not recording events, the result may be empty.

For production operations, grant read privileges separately to DBA or observability teams rather than granting `PROCESS` and broad read privileges to every application.

### 5.3. Views in the sys schema

`sys` provides more readable views aggregating data from Performance Schema and Information Schema, such as views for statements, schemas, indexes, or process lists. This is a convenience layer for administrators, not a mechanism to bypass privileges.

Whether a `sys` view can be queried depends on the view's `SQL SECURITY` definition and the privileges the account holds on the view or underlying data sources. If you encounter `Access denied`, verify the required privileges rather than assuming all `sys` views are public.

## 6. Role-Based Privilege Examples

A system usually has at least three account categories with differing metadata needs:

| Role | Need | Privilege scope to consider |
|---|---|---|
| Runtime application | Connect and manipulate business data | DML privileges on needed schemas/tables; no instance-wide audit privileges needed |
| Migration tool | Read schemas and alter structure during deployments | Metadata read privileges and required DDL privileges during migration windows |
| DBA/auditor | Inventory schemas, view definitions, diagnose sessions and locks | Metadata privileges, `SHOW VIEW`, routine privileges, or `PROCESS` per specific duty |

Example creating an account to read data from one table and its associated metadata:

```sql
CREATE USER 'report_reader'@'10.20.0.25'
    IDENTIFIED BY 'REPLACE_WITH_A_STRONG_SECRET';

GRANT SELECT
    ON appdb.orders
    TO 'report_reader'@'10.20.0.25';
```

This account has privilege to read data from the `orders` table and can see the corresponding metadata per MySQL rules. It does not automatically gain privileges to see all databases, private view definitions, routines, or other users' sessions.

If a team needs to view view definitions in a schema:

```sql
GRANT SHOW VIEW
    ON appdb.*
    TO 'metadata_auditor'@'10.20.0.25';
```

If an auditor needs to list all schemas, global `SHOW DATABASES` can be granted after evaluating scope:

```sql
GRANT SHOW DATABASES
    ON *.*
    TO 'metadata_auditor'@'10.20.0.25';
```

Grant `PROCESS` only when the role requires observing other accounts' connections:

```sql
GRANT PROCESS
    ON *.*
    TO 'dba_observer'@'10.20.0.25';
```

These examples use placeholder IP addresses and passwords; substitute actual accounts and connection sources. Never use example passwords in production.

## 7. Checking Privileges and Explaining Results

### 7.1. Determining the account actually in use

Run on the exact connection being investigated:

```sql
SELECT
    USER() AS client_identity,
    CURRENT_USER() AS matched_account,
    CURRENT_ROLE() AS active_roles,
    DATABASE() AS current_database;
```

`USER()` reports the identity the client presented when connecting. `CURRENT_USER()` reports the MySQL account selected for privilege checking. `CURRENT_ROLE()` displays active roles in the session. Two accounts with the same username and different hosts can have completely different privilege sets.

If privileges are granted through roles, check whether the roles have been activated in the session. Roles can be set as default for a user or activated via `SET ROLE` depending on configuration.

### 7.2. Viewing granted privileges

Use `SHOW GRANTS` to inspect an account's privileges:

```sql
SHOW GRANTS FOR 'report_reader'@'10.20.0.25';
```

To view privileges for the current account:

```sql
SHOW GRANTS;
```

If an account receives privileges via roles, inspect both granted roles and active roles. Do not look at a single `GRANT SELECT` statement and conclude it represents all privileges: privileges can come from global, schema, table, column, routine, or role grants.

### 7.3. Comparing metadata between two accounts

Suppose `report_reader` has privileges only on `appdb.orders`, whereas `metadata_auditor` has metadata read privileges on more tables. When running the exact same `INFORMATION_SCHEMA.TABLES` query, results can differ.

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    TABLE_TYPE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA IN ('appdb', 'billing')
ORDER BY TABLE_SCHEMA, TABLE_NAME;
```

To explain the discrepancy, compare the effective privileges of both sessions, including user/host, active roles, and directly granted privileges. An empty result is not enough to conclude a schema or table does not exist.

## 8. Limitations and Security Considerations

### 8.1. Metadata can still leak sensitive information

Database names, table names, column names, indexes, routines, and view definitions can reveal business architecture. Column names such as `salary`, `customer_token`, or `payment_reference` expose what kind of data the system stores even when the viewer cannot read row values.

Therefore, metadata privileges must also follow the principle of least privilege. Grant full-schema inventorying or routine-definition viewing only to groups whose duties require them.

### 8.2. Hiding metadata is no substitute for data authorization

You cannot rely on an object not appearing in `SHOW TABLES` as a data-protection mechanism. Data protection must rely on `SELECT`, `INSERT`, `UPDATE`, `DELETE`, routine execution privileges, view security context, and proper access controls.

If an account has permission to read a view defined with `SQL SECURITY DEFINER`, it can query data that the definer is permitted to access, even if the calling account lacks direct privileges on the underlying tables. This is an intentional delegation mechanism; review view definitions and definer privileges carefully.

### 8.3. Do not access files or system tables directly to bypass privileges

Starting in MySQL 8.0, the data dictionary is managed transactionally. Applications should use `INFORMATION_SCHEMA`, `SHOW`, and published interfaces rather than depending on legacy metadata files or editing system tables directly.

Do not grant broad read access on the `mysql` schema just so a tool can retrieve metadata. Identify the appropriate metadata interface and grant the right privileges on that interface.

### 8.4. Metadata can change between two checks

Metadata is a snapshot at query time. A migration can create or drop tables between two reads; privileges can also change as roles are granted, revoked, or activated. Audit and migration tools should log the check timestamp, account, active roles, and server version so results remain explainable.

Do not rely on a single metadata check to guarantee the schema will not change before the next operation runs. DDL operations must be coordinated and re-verified during deployment.

## 9. Safe Metadata Inventory Workflow

When building an audit or schema discovery tool, follow this sequence:

1. **Define the purpose.** Does the tool need to list schemas, compare tables/columns/indexes, inspect view definitions, or observe sessions?
2. **Use a dedicated account.** Do not use `root` or an application runtime account for audit tools.
3. **Grant least privilege.** Grant privileges on the schemas/tables to be inspected; add `SHOW VIEW`, `SHOW_ROUTINE`, `SHOW DATABASES`, or `PROCESS` only when the task requires them.
4. **Record session identity.** Log `USER()`, `CURRENT_USER()`, active roles, and server version.
5. **Query official metadata.** Use `INFORMATION_SCHEMA` and appropriate `SHOW` statements.
6. **Interpret results in light of privileges.** Do not treat hidden rows as proof that an object does not exist.
7. **Verify effective privileges.** Use `SHOW GRANTS`, verifying roles and privilege scopes.
8. **Protect audit outputs.** Metadata, view definitions, and SQL in process lists can contain sensitive details; restrict access to audit reports.
9. **Repeat after migrations.** Compare pre- and post-deployment metadata using an account with the same privilege scope to avoid discrepancies caused by differing accounts.

## 10. Common Misconceptions

| Misconception | Accurate understanding |
|---|---|
| `SHOW DATABASES` always lists every schema | By default, output is limited by privileges; global `SHOW DATABASES` expands listing scope |
| Not seeing a table means the table does not exist | The account may lack privileges to see the object |
| Seeing a view's name means you can view its definition | `SHOW VIEW` may be required to inspect the definition |
| Holding `SELECT` on a view means holding privileges on underlying tables | A view can use `SQL SECURITY DEFINER`; view privileges and base-table privileges differ |
| `INFORMATION_SCHEMA` always contains all metadata | Rows and some metadata columns are filtered by privileges |
| Without `PROCESS` you can still see every user's sessions | Normally you see only your own threads; `PROCESS` expands observation scope |
| Metadata visibility means data-reading permission | Metadata visibility and data manipulation privileges are two distinct layers |
| Running an audit tool with the runtime account is enough | Runtime accounts usually lack schema inventory or definition-viewing privileges |

## 11. Key Takeaways

- Metadata describes schemas, tables, columns, indexes, constraints, views, routines, and server activity.
- `SHOW` and `INFORMATION_SCHEMA` filter objects by account privileges; an empty result does not prove an object does not exist.
- Global `SHOW DATABASES` allows listing all schemas; grant it only when administrative or audit duties require it.
- `SHOW VIEW` controls viewing view definitions; routine definitions may require `SHOW_ROUTINE` or related privileges depending on version.
- `PROCESS` expands visibility into other users' connections; restrict it because process lists can expose SQL and operational data.
- Performance Schema and `sys` are diagnostic interfaces that are also subject to privilege controls.
- Separate runtime, migration, and DBA/auditor accounts; grant minimum metadata privileges per role.
- Never use hidden metadata as a data-security mechanism; always enforce proper privileges on data, views, and routines.

When you clearly understand metadata visibility privileges, you can build reliable schema discovery and audit tools, interpret metadata query results accurately, and avoid granting broader privileges than each MySQL account actually needs.
