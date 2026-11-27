# Data Dictionary, Static Dictionary Views, and Dynamic Performance Views in Oracle

When working with **Oracle Database**, developers often need to know "which columns does this table have?", "which table does this foreign key reference?", or "which objects can the current user access?". DBAs and operators often ask "which sessions are running?", "which SQL statement consumes the most resources?", "when did the instance start?", or "is the database waiting on I/O or locks?". Oracle provides two major groups of views to answer those questions:

- **Static data dictionary views**: present **metadata stored and managed by Oracle**, such as schemas, objects, columns, constraints, indexes, users, roles, privileges, tablespaces, and recorded statistics. These views typically use prefixes **`USER_`**, **`ALL_`**, **`DBA_`**, or **`CDB_`**.
- **Dynamic performance views**: present **operational state and runtime statistics while Oracle is running**, such as instances, sessions, SQL cursors, wait events, resources, and effective parameters. These views are typically named **`V$...`** or **`GV$...`**.

Both groups can be queried using SQL `SELECT`, but they **do not share the same data source, temporal semantics, access privileges, or container/instance scope**. A common misconception is that *static* means immutable: after a `CREATE TABLE` statement, dictionary metadata changes as well. "Static" is used to distinguish structural/persistent metadata from the volatile runtime metrics exposed by dynamic views.

## 1. The big picture: what does Oracle store and expose?

```text
                       ORACLE DATABASE
                              |
            +-----------------+------------------+
            |                                    |
      DATA DICTIONARY                    RUNTIME / INSTANCE
      database metadata                  operational state
      - user, role, grant                - session, cursor
      - table, column, index             - wait, lock, memory
      - constraint, view                 - process, resource
      - tablespace, object               - SQL statistics
            |                                    |
            v                                    v
      Static dictionary views            Dynamic performance views
      USER_* / ALL_*                      V$SESSION / V$SQL
      DBA_* / CDB_*                       V$INSTANCE / V$PARAMETER
      DICTIONARY / DICT                   GV$SESSION / GV$SQL
            |                                    |
            +-----------------+------------------+
                              |
                        SQL SELECT
                              |
              Developer / DBA / Operations
```

The **data dictionary** is the metadata set Oracle uses to describe the database itself and the objects inside it. It includes object definitions and administrative metadata; it is **not a business schema for applications to edit directly**. In Oracle, many underlying base tables belong to the system schema `SYS`; Oracle exposes controlled views so users can query information appropriate to their privileges.

Dynamic performance views generally expose information from internal operational structures and statistics maintained by Oracle while the instance runs. Many `V$...` names that users query are **public synonyms** pointing to views owned by `SYS` named `V_$...`; similarly, `GV$...` usually points to `GV_$...`. Synonyms make names convenient to type, but **do not automatically grant `SELECT` privilege** on the view's data.

| Aspect | Static dictionary view | Dynamic performance view |
|---|---|---|
| Primary question | "How is the database defined, authorized, and organized?" | "How is Oracle currently operating and consuming resources?" |
| Data represented | Metadata for tables, columns, constraints, users, roles, objects, storage | Sessions, SQL cursors, processing times, waits, processes, resources, instance state |
| Examples | `USER_TABLES`, `ALL_TAB_COLUMNS`, `DBA_OBJECTS`, `CDB_USERS` | `V$SESSION`, `V$SQL`, `V$INSTANCE`, `GV$SESSION` |
| Currency | Updates when Oracle updates metadata or related storage information | Can change continuously during reads; many metrics are cumulative counters |
| Scope | By owner, object visibility privileges, container, and view group | By view, instance, container, and diagnostic privileges |
| Typical tasks | Schema discovery, migration checks, privilege auditing, structure comparison | Load monitoring, SQL/session lookup, wait investigation, resource limits |
| Misconception to avoid | "Static means unchanged after DDL" | "A single V$ query gives complete history and a point-in-time consistent snapshot" |

## 2. Data dictionary: metadata managed by Oracle

Example statement:

```sql
CREATE TABLE orders (
    order_id   NUMBER PRIMARY KEY,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);
```

After creating the table successfully, Oracle records the information required to know which user/schema owns `ORDERS`, what columns and data types it has, which constraints are declared, the object's status, and how its storage is managed. Applications and IDE tools **do not need to read `SYS` base tables directly**; metadata can be queried through Oracle-supported views.

For instance, the owning account can inspect:

```sql
SELECT table_name
FROM user_tables
WHERE table_name = 'ORDERS';

SELECT column_name, data_type, nullable
FROM user_tab_columns
WHERE table_name = 'ORDERS'
ORDER BY column_id;
```

Object names created **without double quotes** are normally normalized to uppercase in the dictionary; hence `WHERE table_name = 'ORDERS'` matches the `orders` table created in the example. Objects created with quoted identifiers can preserve special casing; in those cases, the exact actual name must be used.

### 2.1. The dictionary holds more than just a list of tables

| Information category | Common views | Meaning |
|---|---|---|
| Object/schema | `USER_OBJECTS`, `ALL_OBJECTS`, `DBA_OBJECTS` | Tables, views, packages, indexes, sequences, DDL timestamps, object status |
| Table/column | `USER_TABLES`, `ALL_TABLES`, `USER_TAB_COLUMNS`, `ALL_TAB_COLUMNS` | Table/column definitions and attributes within visible scope |
| Constraint | `USER_CONSTRAINTS`, `USER_CONS_COLUMNS`, `ALL_CONSTRAINTS` | Primary key, unique, foreign key, check constraints, and participating columns |
| Index | `USER_INDEXES`, `USER_IND_COLUMNS`, `DBA_INDEXES` | Index name, uniqueness, columns/column positions, and index properties |
| Views and PL/SQL source | `USER_VIEWS`, `USER_SOURCE`, `ALL_SOURCE`, `USER_ERRORS` | Definitions or compilation error details for visible objects |
| User/role/grant | `DBA_USERS`, `DBA_ROLES`, `DBA_SYS_PRIVS`, `DBA_ROLE_PRIVS`, `DBA_TAB_PRIVS` | Identities, roles, system/object privileges, and role membership |
| Storage | `DBA_TABLESPACES`, `DBA_DATA_FILES`, `DBA_SEGMENTS`, `DBA_EXTENTS`, `DBA_FREE_SPACE` | Tablespaces, datafiles, segment/extent sizes, and unallocated space |
| Multi-PDB metadata | `CDB_OBJECTS`, `CDB_USERS`, `CDB_TABLES` | Adds container information to observe multiple PDBs from root per privileges |

Not every view has every prefix variant. Use Oracle documentation or the actual view catalog to find exact view and column names for your running version, rather than blindly combining `USER_` with any suffix.

### 2.2. Never update base dictionary tables directly

Valid operations for modifying metadata are **DDL** and Oracle-supported administrative APIs, such as `CREATE TABLE`, `ALTER TABLE`, `CREATE USER`, `GRANT`, or appropriate administrative packages. Never run `INSERT`, `UPDATE`, or `DELETE` directly on `SYS`-owned base tables to "fix the dictionary." Such tampering can break database integrity and supportability.

Many standard Oracle DDL commands perform an **implicit commit**. Therefore, migrations that alter dictionary metadata must be tested and deployed under control; do not assume you can undo everything with `ROLLBACK` like a DML transaction.

## 3. Static dictionary view groups: `USER_`, `ALL_`, `DBA_`, `CDB_`

### 3.1. `USER_*`: objects belonging to the current schema

This is the convenient starting point for developers exploring **objects they own**. Many `USER_*` views omit the `OWNER` column because the owner is already determined by the corresponding user/schema context.

```sql
SELECT object_name, object_type, status, last_ddl_time
FROM user_objects
WHERE object_type IN ('TABLE', 'VIEW', 'PACKAGE', 'INDEX')
ORDER BY object_type, object_name;
```

`STATUS` is meaningful per object type, such as `VALID`/`INVALID` for views or packages when Oracle tracks compilation/dependency status. `LAST_DDL_TIME` is not the "last time a data row was modified": DML such as `UPDATE` on a table does not necessarily change the object's DDL timestamp.

```sql
SELECT table_name, tablespace_name, partitioned
FROM user_tables
ORDER BY table_name;
```

`USER_TABLES` answers which tables exist in the schema within the view's scope. If a table is created without a segment yet due to deferred segment creation, the table can still appear in `USER_TABLES` while having no corresponding row in `USER_SEGMENTS`.

### 3.2. `ALL_*`: objects the user is permitted to see/access

The `ALL_*` group answers: **"In this container, which objects are within the active account's access scope?"** It can include objects owned by other schemas that the user has privileges on or is allowed by Oracle to see, which does not mean the user owns all those objects.

```sql
SELECT owner, table_name
FROM all_tables
WHERE owner = 'APP_OWNER'
ORDER BY table_name;
```

```sql
SELECT owner, table_name, column_name, data_type, nullable
FROM all_tab_columns
WHERE owner = 'APP_OWNER'
  AND table_name = 'ORDERS'
ORDER BY column_id;
```

Filtering by `OWNER` is very helpful when multiple schemas have tables with identical names. Note: an object appearing in `ALL_*` **does not guarantee all operations on that object are permitted**. A user might only have `SELECT`, only `EXECUTE` on a package, or access via a specific privilege mechanism. To know allowed operations, inspect grants and execution context.

### 3.3. `DBA_*`: broad metadata in the connected container

The `DBA_*` group provides broader visibility, typically intended for DBAs or accounts granted appropriate catalog privileges:

```sql
-- Intended for users with corresponding dictionary read privileges.
SELECT owner, object_name, object_type, status
FROM dba_objects
WHERE owner = 'APP_OWNER'
ORDER BY object_type, object_name;
```

The `DBA_` prefix does not mean only accounts with the `DBA` role can query it; access is governed by specific privileges/grants and Oracle policies. Conversely, a regular application account **should not be granted `DBA`** just to list a table.

In the **CDB/PDB** architecture, when executed inside PDB A, `DBA_*` primarily describes metadata within **container A**. Querying `DBA_OBJECTS` in PDB A does not by default list every object in PDB B. To observe multiple containers from root, Oracle provides the `CDB_*` group.

### 3.4. `CDB_*`: container-aware dictionary views

From `CDB$ROOT`, a DBA can use `CDB_*` views to inspect metadata across multiple containers according to access privileges and Oracle visibility rules. These views usually add **`CON_ID`** to identify which container holds each metadata row.

```sql
-- Run from CDB$ROOT using an account with appropriate privileges.
SELECT con_id, owner, object_name, object_type, status
FROM cdb_objects
WHERE owner = 'APP_OWNER'
  AND object_type = 'TABLE'
ORDER BY con_id, object_name;
```

If `APP_OWNER.ORDERS` exists in two PDBs, two rows can share the same `OWNER` and `OBJECT_NAME` while having **different `CON_ID` values**. Do not merge or compare multi-PDB metadata solely by object name.

Common meanings of `CON_ID`:

| `CON_ID` | Interpretation |
|---|---|
| `0` | Row applies CDB-wide or is not tied to a single container, depending on the view |
| `1` | `CDB$ROOT` |
| `2` | `PDB$SEED` in standard CDB architectures |
| `3` and above | PDBs or other containers per the current catalog |

Do not hard-code that `CON_ID = 3` is always a particular application PDB. During administrative work, verify `CON_ID` against the container catalog provided by the DBA; whether a PDB appears in results also depends on privileges, container state, and Oracle version.

### 3.5. Comparison of access scopes

| Prefix | Scope to visualize | Typical use case |
|---|---|---|
| `USER_` | Objects/schema of the active user in the current container | Developer inspecting their own schema's tables, columns, and indexes |
| `ALL_` | Objects the current user can see/access per privileges | Developer checking tables or views in another schema |
| `DBA_` | Broad metadata in the current container, requiring catalog privileges | DBA auditing users, objects, tablespaces, and grants |
| `CDB_` | Multi-container metadata from root with `CON_ID`, subject to privileges | DBA comparing PDBs or inspecting common/local users |

**Note:** *schema* scope, *container* scope, and *metadata visibility privileges* are three distinct factors. Users may share the same name across multiple PDBs yet be **independent local users**; querying from one PDB does not automatically grant visibility into another PDB.

## 4. Discovering static dictionary views and their columns

You do not need to memorize hundreds of views. Oracle provides mechanisms to explore metadata about the dictionary itself.

### 4.1. Finding views via `DICTIONARY` or `DICT`

```sql
SELECT table_name, comments
FROM dictionary
WHERE table_name IN (
    'USER_OBJECTS', 'ALL_TABLES', 'DBA_OBJECTS', 'V$SESSION'
)
ORDER BY table_name;
```

`DICTIONARY` (commonly accessible via synonym `DICT`) lists dictionary views/tables along with descriptions visible to the account within Oracle's scope. A name appearing in the catalog does not guarantee the user has privileges to read all data from that view; test permitted queries or consult the DBA.

```sql
SELECT table_name, column_name, comments
FROM dict_columns
WHERE table_name = 'USER_OBJECTS'
ORDER BY column_name;
```

`DICT_COLUMNS` helps look up column names and descriptions. You can also use the **Describe** feature in SQLcl/SQL*Plus/SQL Developer or JDBC metadata APIs. When learning a specific Oracle release, check actual view and column names because releases can add columns or change visibility.

### 4.2. Viewing object definitions via supported APIs

To retrieve DDL for an object you own, you can use `DBMS_METADATA.GET_DDL` if granted appropriate privileges:

```sql
SELECT DBMS_METADATA.GET_DDL('TABLE', 'ORDERS', USER)
FROM dual;
```

The output is a `CLOB` containing the DDL and may include storage attributes; formatting depends on package/tool options. This is a metadata-reading API, not a direct read of dictionary base tables. When used for another schema, privileges and metadata protection policies must be respected.

## 5. Reading a schema's metadata from tables to constraints and indexes

Suppose the application has table `APP_OWNER.ORDERS`. A developer needs to understand data boundaries before changing migrations. The following queries are read-only and use `ALL_*` so they can inspect an object owned by another schema within granted privileges.

### 5.1. Finding columns and data types

```sql
SELECT column_id, column_name, data_type,
       data_length, data_precision, data_scale, nullable
FROM all_tab_columns
WHERE owner = 'APP_OWNER'
  AND table_name = 'ORDERS'
ORDER BY column_id;
```

Look beyond `DATA_TYPE`: for `NUMBER`, pay attention to `DATA_PRECISION`/`DATA_SCALE`; for `VARCHAR2`, check length semantics and size. Do not naively assume `DATA_LENGTH` is always the number of characters a user can enter, as it may reflect **bytes** even when the column uses `CHAR` length semantics.

### 5.2. Reading constraints

```sql
SELECT c.constraint_name,
       c.constraint_type,
       c.status,
       c.validated,
       cc.column_name,
       cc.position,
       c.r_constraint_name
FROM all_constraints c
LEFT JOIN all_cons_columns cc
  ON cc.owner = c.owner
 AND cc.constraint_name = c.constraint_name
 AND cc.table_name = c.table_name
WHERE c.owner = 'APP_OWNER'
  AND c.table_name = 'ORDERS'
ORDER BY c.constraint_name, cc.position;
```

Common `CONSTRAINT_TYPE` codes: `P` (primary key), `R` (referential/foreign key), `U` (unique), `C` (check, including check constraints associated with `NOT NULL`), etc. For foreign keys, `R_CONSTRAINT_NAME` points to the referenced constraint; you must combine **owner** and related metadata to locate the exact target object, especially when multiple schemas share constraint names.

`STATUS` and `VALIDATED` indicate different properties: whether the constraint is currently enabled and whether existing data was validated against the constraint. Do not assume that a named constraint is always enforced the way you expect.

### 5.3. Reading indexes and column order

```sql
SELECT i.owner, i.index_name, i.uniqueness,
       ic.column_name, ic.column_position
FROM all_indexes i
JOIN all_ind_columns ic
  ON ic.index_owner = i.owner
 AND ic.index_name = i.index_name
WHERE i.table_owner = 'APP_OWNER'
  AND i.table_name = 'ORDERS'
ORDER BY i.index_name, ic.column_position;
```

Column order can determine whether a composite index serves a query. For example, `(CUSTOMER_ID, CREATED_AT)` is not equivalent to `(CREATED_AT, CUSTOMER_ID)`. Metadata tells you **how the index is defined**; whether a specific SQL query actually uses the index depends on the optimizer, statistics, data distribution, and execution plan.

### 5.4. Understanding limitations of statistics in the dictionary

Views such as `USER_TABLES`/`DBA_TABLES` include columns like `NUM_ROWS` and `LAST_ANALYZED`. `NUM_ROWS` is typically **optimizer statistics from the last collection**, not a live row counter updated immediately after every `INSERT`/`DELETE`.

```sql
SELECT table_name, num_rows, last_analyzed
FROM user_tables
WHERE table_name = 'ORDERS';
```

If 10,000 rows were just inserted and `NUM_ROWS` has not changed, do not conclude the insert failed. To check the exact row count under current transaction read consistency, you can run `SELECT COUNT(*)` on the table if permitted, keeping in mind that scanning large tables carries significant resource cost. Dictionary statistics and live runtime counts serve different purposes.

## 6. Dynamic performance views: observing Oracle while running

Dynamic performance views usually start with **`V$`**. Examples:

- `V$INSTANCE`: instance identity, status, and startup time.
- `V$DATABASE`: database information and key operational states.
- `V$SESSION`: sessions, users, status, wait events, and associated SQL.
- `V$SQL`: SQL cursors in the shared SQL area, execution counts, and related statistics.
- `V$SQL_PLAN`: execution plan information for cached cursors by SQL ID/child.
- `V$PARAMETER`: instance/session parameter values currently in effect within the view's context.
- `V$RESOURCE_LIMIT`: current/peak usage and configured limits for certain resources.
- `V$SESSION_EVENT`, `V$SYSTEM_EVENT`: cumulative wait event statistics at their respective scopes.
- `V$LOCK`: lock and lock-request information useful when investigating blocking.

Not all dynamic views hold "instantaneous values" in the same way: some reflect current state, while others hold cumulative statistics since the session, cursor, or instance started. Values can change between two `SELECT` runs; **multiple columns do not form a strictly synchronized system-wide snapshot**.

### 6.1. Inspecting the running instance

```sql
-- Requires privilege to read the corresponding dynamic performance view.
SELECT instance_name, host_name, status, startup_time
FROM v$instance;
```

This helps determine whether the instance recently restarted or which environment the application is hitting. `STARTUP_TIME` is not the database creation date and does not directly tell you when a specific PDB was opened. In Oracle RAC, one CDB/database can have **multiple instances** across multiple nodes.

### 6.2. Observing application sessions

```sql
SELECT sid, serial#, username, status,
       sql_id, wait_class, event, con_id
FROM v$session
WHERE username = 'APP_RUNTIME'
ORDER BY sid;
```

An actual session is identified by attributes such as **instance**, `SID`, and `SERIAL#`, not by `SID` alone. A session can switch SQL or terminate immediately after your query. `STATUS = 'ACTIVE'` does not necessarily mean the session is continuously burning CPU: it may be executing a database call while waiting on I/O, locks, or network. When a session is not currently waiting, the `EVENT` column may reflect a recent wait event; inspect wait state and context carefully before drawing conclusions.

`V$SESSION` helps answer "which sessions currently exist, under which account, and associated with which SQL?". It **does not by itself explain the root cause** of every slow API request; combine it with application logs/traces and connection pool metrics.

### 6.3. Observing SQL cursors and relative consumption

```sql
-- Example query; use only when granted diagnostic privileges.
SELECT sql_id,
       child_number,
       executions,
       buffer_gets,
       disk_reads,
       ROUND(elapsed_time / 1000000, 2) AS elapsed_seconds
FROM v$sql
WHERE parsing_schema_name = 'APP_RUNTIME'
ORDER BY elapsed_time DESC
FETCH FIRST 10 ROWS ONLY;
```

`ELAPSED_TIME` here is reported in **microseconds** in many Oracle versions, so the example divides by `1,000,000` to display seconds. This is **cumulative time associated with the cursor**, not the duration of the most recent execution. `EXECUTIONS` shows recorded execution counts for that cursor; numbers can change when cursors are reloaded, aged out of the shared pool, or when the instance restarts. A single SQL ID can have multiple **child cursors** with different plans and statistics; do not sum or divide metrics blindly without accounting for child cursor boundaries.

SQL information in these views can expose **SQL text and literals containing sensitive data**. Extract only needed fields, and avoid pasting raw user SQL into uncontrolled tickets or chats. Moreover, `V$SQL` statistics are not an infinite history: older SQL statements may no longer be in the shared pool.

### 6.4. Checking active parameters and resource limits

```sql
SELECT name, value, isdefault, issys_modifiable
FROM v$parameter
WHERE name IN ('open_cursors', 'sessions', 'processes')
ORDER BY name;
```

```sql
SELECT resource_name,
       current_utilization,
       max_utilization,
       limit_value
FROM v$resource_limit
WHERE resource_name IN ('sessions', 'processes')
ORDER BY resource_name;
```

An application experiencing connection creation failures may need to compare connection pool size multiplied by replica count against database limits. However, `CURRENT_UTILIZATION` or a single high-usage moment does not prove the cause of dropped connections; ORA error codes, logs, and workload still must be checked. Modifying instance parameters must be performed by a DBA through change management, not automatically by developers.

### 6.5. When to use `V$SQL_PLAN`

If you already have the `SQL_ID` of a cached SQL statement, you can inspect the cursor's execution plan or use `DBMS_XPLAN.DISPLAY_CURSOR` when granted appropriate privileges. An execution plan shows what access paths Oracle expected or used according to the tool's observed cursor data, yet **one cursor's plan does not explain every execution** nor replace checking actual data, bind values, statistics, SQL versions, and wait events. Advanced diagnostic procedures/options may carry separate privilege and licensing requirements.

## 7. `V$` vs. `GV$`: single instance vs. multi-instance

In Oracle Real Application Clusters (**RAC**), one database can be served simultaneously by multiple instances. **`V$...`** focuses on dynamic view data within the connected instance's context; **`GV$...`** (*global dynamic performance view*) generally aggregates corresponding data across instances and adds the **`INST_ID`** column.

```text
            ORACLE RAC DATABASE
          +---------------------+
          |                     |
   Instance 1              Instance 2
      SID 25                  SID 25
      SID 46                  SID 81
          |                     |
      V$SESSION             V$SESSION
          \                     /
           \                   /
             GV$SESSION
        INST_ID + SID + SERIAL#
```

`SID = 25` can appear on **two different instances**; when investigating a RAC session, inspect `INST_ID` alongside `SID`/`SERIAL#` and container if applicable.

```sql
SELECT inst_id, sid, serial#, username,
       status, sql_id, event, con_id
FROM gv$session
WHERE username = 'APP_RUNTIME'
ORDER BY inst_id, sid;
```

Not every database runs RAC. On single-instance systems, `GV$` still works, though reading `INST_ID` does not represent a multi-node topology. Some dynamic views do not have identical counterparts or columns across all versions; consult the catalog for your running version.

### 7.1. `CON_ID` differs from `INST_ID`

| Column | Question answered | Example |
|---|---|---|
| `CON_ID` | Which **container/PDB** does this metadata/runtime row belong to? | PDB `SALES_APP` has `CON_ID = 4` in the current CDB |
| `INST_ID` | From which **instance** was this runtime row collected? | RAC instance `1` or `2` |
| `SID` + `SERIAL#` | Which specific session in the instance at the time of observation? | Combined with `INST_ID` in RAC |
| `OWNER`, `USERNAME` | Which object owner/schema or user account? | `APP_OWNER`, `APP_RUNTIME` |

**CDB/PDB and RAC are two orthogonal axes.** A single PDB can be served across multiple RAC instances; a single instance can also serve multiple PDBs. Investigations should therefore capture **PDB, instance, session, SQL ID, and timestamp** rather than a single ID.

## 8. Metadata and dynamic metrics in a CDB/PDB environment

In multitenant architectures, developers typically connect directly to the **application PDB service**. Meanwhile, DBAs may work at `CDB$ROOT` to observe multiple PDBs. The same view can return different scopes and row counts depending on container, privileges, and how Oracle implements that view.

```sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS login_user
FROM dual;
```

Run this session-verification query **before interpreting output** from `DBA_*` or `V$...`. If you are inside PDB A, a `DBA_OBJECTS` query missing tables from PDB B may be completely expected behavior.

A DBA at root with appropriate privileges can list containers:

```sql
-- Example from CDB$ROOT, subject to privileges and version.
SELECT con_id, name, open_mode
FROM v$pdbs
ORDER BY con_id;
```

When placing metadata queries from `CDB_OBJECTS` next to session queries from `GV$SESSION`, **join or group by the exact matching keys**, never joining everything solely by `USERNAME` or `OBJECT_NAME`. A table `ORDERS` in PDB A and a table `ORDERS` in PDB B are two distinct objects despite having the same name.

To prevent context confusion, technical incident reports should record:

```text
Environment: TEST
Database service: order_test_service
Container/PDB: ORDER_TEST_PDB
Instance: instance_1
Schema owner: ORDER_OWNER
Session user: ORDER_RUNTIME
Observed at: 2026-11-14 10:20 +07
```

These values are illustrative only. Never include credentials, passwords, wallets, or SQL containing sensitive data in reports.

## 9. Access privileges for dictionary and dynamic views

Being able to query metadata **does not mean accessing the entire catalog**. Oracle restricts privileges to prevent exposing database structure, usernames, SQL text, or session states of other applications.

| Account | Typical need | Appropriate access path |
|---|---|---|
| Developer/schema owner | Inspect their own tables, columns, indexes, and constraints | `USER_*`, `ALL_*` within granted scope |
| Runtime application | Execute business SQL | Typically does not need `DBA_*`, `V$SQL`, or system-wide `V$SESSION` |
| CI/migration identity | Verify schema version and validity after migration | `USER_*` or specific metadata under controlled privileges |
| Monitoring account | Collect defined instance/session/resource metrics | Grant `SELECT` only on necessary dynamic views per policy |
| Authorized DBA/on-call | Investigate broad metadata, sessions, waits, resources | Corresponding catalog/diagnostic privileges, auditing, and appropriate access window |

### 9.1. A public view name does not imply public access

`V$SESSION` is commonly exposed via a public synonym, yet a user without appropriate grants can hit `ORA-00942` or a privilege error when querying it. That is not proof the database lacks the view. A DBA can grant read access on the underlying view (such as **`SYS.V_$SESSION`**) or an appropriate catalog role/mechanism to an approved monitoring identity; exact granting details depend on version and policy.

Broad privileges such as **`SELECT ANY DICTIONARY`**, roles like **`SELECT_CATALOG_ROLE`**, or the `DBA` role open substantial scope. Do not grant them to a web application account merely to unblock one diagnostic query. In **definer's-rights** PL/SQL, role-based privileges generally do not substitute for direct grants during compilation and execution; verify the actual privilege context.

### 9.2. Metadata can also be sensitive information

Some views can expose:

- Account names, hostnames, connecting programs, services, and privilege layouts.
- SQL text or binds/literals revealing identifiers, personal data, or statements containing secrets.
- Topology, session counts, resource limits, system state, and workload patterns.
- Object/schema details that system owners do not want shared across DEV/TEST boundaries.

Therefore, when collecting logs or tickets, export only **error codes, metrics, SQL IDs, timestamps, environment, and strictly necessary figures**. Never dump full `V$SQL.SQL_FULLTEXT`, passwords, secrets, or sensitive configuration files into shared reports.

### 9.3. Diagnostic features and licensing considerations

Basic dynamic performance views and advanced/historical diagnostic features **are not equivalent in terms of usage rights and licensing**. For instance, AWR, ASH, or tuning capabilities may require Oracle Diagnostics Pack/Tuning Pack and depend on edition/license terms. Do not run advanced reports or features just because the view or package names are visible. Confirm privileges and licensing with your DBA or Oracle license management team before using them.

## 10. Combining static and dynamic views to investigate issues

An Oracle incident often requires both **"what is the object?"** and **"what is the session doing?"**. The two view groups complement each other, though they do not replace application logs, connection pool metrics, network data, or traces.

### Scenario A — `ORA-00942` when executing business SQL

The application logs in successfully, yet `SELECT * FROM APP_OWNER.ORDERS` fails with `ORA-00942: table or view does not exist`.

1. Developer checks whether the schema/table name was declared accurately and whether the migration created the object.
2. Check `ALL_TABLES`/`ALL_OBJECTS` from the **exact runtime account and PDB** to see if the object appears in the user's scope.
3. DBA/schema owner checks `DBA_OBJECTS`/object grants if the regular user cannot see the object; check synonyms if the SQL omits the owner.
4. Verify appropriate `SELECT` privilege; never use `SYS` to prove the runtime account has privileges.

This is primarily a **metadata and authorization problem**, not a CPU or wait-event issue. `V$SESSION` can only help confirm the session; it cannot fix a missing object or missing grant.

### Scenario B — Package becomes `INVALID` after migration

After altering a table or column, the application fails to invoke a PL/SQL package and encounters compilation/dependency errors.

```sql
SELECT object_name, object_type, status, last_ddl_time
FROM user_objects
WHERE object_name = 'ORDER_SERVICE_PKG';

SELECT name, type, line, position, text
FROM user_errors
WHERE name = 'ORDER_SERVICE_PKG'
ORDER BY sequence;
```

`USER_OBJECTS`/`USER_ERRORS` inspect object status and compilation error details in the owning schema. The developer reviews DDL changes, dependencies, and direct grants needed for definer's-rights PL/SQL. Dynamic session views can help assess runtime impact, but **the root cause of an invalid object lies in its definition, dependencies, and privileges**.

### Scenario C — Slow API and sessions showing wait events

The application reports increased latency after a release. Investigation path:

```text
Application logs/metrics
  -> request ID, SQL ID if available, connection pool, release
             |
             v
V$SESSION / GV$SESSION
  -> which session, which SQL_ID, wait/event/instance/PDB
             |
             v
V$SQL / execution plan
  -> cursor, execution count, buffer_gets, elapsed_time, plan
             |
             v
USER_/ALL_/DBA_ metadata
  -> whether indexes exist, constraints, schema, statistics/DDL
             |
             v
Formulate hypothesis and verify with measurements
```

For example, if `V$SESSION` shows many application sessions tied to the same SQL ID waiting on I/O, the developer can inspect predicates, query frequency, and indexes. The DBA uses static dictionary views to verify that the index actually exists, its status, and statistics, and dynamic views to examine waits and resources. **Seeing I/O waits does not automatically prove an index is missing**, and having an index does not mean the optimizer is forced to use it.

### Scenario D — New connections fail due to session limits

Developers see pool timeouts or Oracle returns errors related to session creation. The DBA can inspect `V$RESOURCE_LIMIT` for `sessions`/`processes` utilization, and `V$SESSION`/`GV$SESSION` to check session counts per account/instance. Meanwhile, operations checks replicas, autoscaling, and retries; developers check connection leaks and pool sizes. `DBA_USERS`/dictionary views can identify accounts, profiles, or privileges, but **do not directly represent active session counts**.

### Scenario E — A PDB has a table with the same name but different structure

In a CDB, the same name `APP_OWNER.ORDERS` appears in both DEV and TEST PDBs. A migration was missed in TEST, leaving a column missing.

The DBA queries `CDB_OBJECTS` or column metadata by container to compare **`CON_ID` + `OWNER` + `OBJECT_NAME`**; the developer verifies schema version via the migration tool and runs tests against the right PDB service. Never use a single `DBA_TAB_COLUMNS` result from root to conclude every PDB has the same table structure.

## 11. Hands-on lab: query the dictionary, then observe sessions

This lab has two parts. **Part A** runs under a user permitted to create tables in a **DEV/lab PDB**; **Part B** queries dynamic views and requires appropriate diagnostic privileges granted by a DBA. Do not execute DDL on production, and do not grant `DBA`/`SYSDBA` to a lab account.

### Part A — Create small objects and inspect the static dictionary

**Step 1.** Verify container and user:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS login_user
FROM dual;
```

**Step 2.** In a lab schema granted quota and `CREATE TABLE`, create two related tables:

```sql
CREATE TABLE lab_customers_meta (
    customer_id NUMBER GENERATED BY DEFAULT AS IDENTITY,
    full_name   VARCHAR2(100 CHAR) NOT NULL,
    CONSTRAINT pk_lab_customers_meta PRIMARY KEY (customer_id)
);

CREATE TABLE lab_orders_meta (
    order_id    NUMBER GENERATED BY DEFAULT AS IDENTITY,
    customer_id NUMBER NOT NULL,
    status      VARCHAR2(12 CHAR) DEFAULT 'NEW' NOT NULL,
    created_at  TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_lab_orders_meta PRIMARY KEY (order_id),
    CONSTRAINT fk_lab_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES lab_customers_meta (customer_id),
    CONSTRAINT ck_lab_orders_status
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
);

CREATE INDEX ix_lab_orders_customer
    ON lab_orders_meta (customer_id);
```

This script is intended for a schema that does not already have lab objects with the same names. If run previously, do not drop tables to start over without confirming the data belongs to your lab exercise. A primary key can create a supporting index for the constraint; therefore, when inspecting `USER_INDEXES`, the number of indexes does not necessarily equal the number of `CREATE INDEX` statements you wrote.

**Step 3.** Inspect tables, columns, and constraints:

```sql
SELECT table_name
FROM user_tables
WHERE table_name IN ('LAB_CUSTOMERS_META', 'LAB_ORDERS_META')
ORDER BY table_name;

SELECT table_name, column_id, column_name,
       data_type, nullable
FROM user_tab_columns
WHERE table_name = 'LAB_ORDERS_META'
ORDER BY column_id;

SELECT constraint_name, constraint_type, status, validated
FROM user_constraints
WHERE table_name = 'LAB_ORDERS_META'
ORDER BY constraint_name;
```

**Step 4.** Identify indexes and foreign key relationships:

```sql
SELECT i.index_name, i.uniqueness,
       ic.column_name, ic.column_position
FROM user_indexes i
JOIN user_ind_columns ic
  ON ic.index_name = i.index_name
WHERE i.table_name = 'LAB_ORDERS_META'
ORDER BY i.index_name, ic.column_position;

SELECT c.constraint_name, c.r_constraint_name,
       cc.column_name, cc.position
FROM user_constraints c
JOIN user_cons_columns cc
  ON cc.constraint_name = c.constraint_name
WHERE c.table_name = 'LAB_ORDERS_META'
  AND c.constraint_type = 'R'
ORDER BY cc.position;
```

Note the PK, FK, CHECK names, index names, and column positions. These outputs are **definition metadata**, not session or performance information. Reading the dictionary itself does not require inserting real data into the tables.

### Part B — Observe dynamic performance views if granted access

**Step 5.** Generate a simple read activity:

```sql
SELECT COUNT(*) AS order_count
FROM lab_orders_meta;
```

Then, from a session with privileges granted by a DBA, inspect instance/session information:

```sql
SELECT instance_name, startup_time
FROM v$instance;

SELECT sid, serial#, username, status,
       sql_id, event, con_id
FROM v$session
WHERE username = SYS_CONTEXT('USERENV', 'SESSION_USER')
ORDER BY sid;
```

Depending on how your DBA grants privileges, the lab account may not be able to read these views; that is an **expected security boundary**. If you lack access, stop here and ask the DBA to provide sanitized output for discussion. Do not grant `SELECT ANY DICTIONARY` just to finish the lab.

`SQL_ID` in `V$SESSION` may be empty or already changed when you read it because the session is idle or running another query. Even though `COUNT(*)` ran, there is no guarantee you will always catch it in a row of `V$SQL` at an arbitrary moment due to cursor caching and operational conditions.

**Step 6.** Record answers to three questions:

1. Does `USER_TAB_COLUMNS` tell you **how data is defined**, or **how fast/slow it is being processed**?
2. In `V$SESSION`, which columns represent **session identity**, and which represent **volatile runtime state**?
3. If multiple PDBs contain a table named `LAB_ORDERS_META`, why must you verify the **container** before comparing metadata?

**Step 7.** When permitted to clean up inside the **DEV** schema, you can drop the lab objects in dependency order:

```sql
-- Run only after confirming this is lab data safe to delete.
DROP TABLE lab_orders_meta PURGE;
DROP TABLE lab_customers_meta PURGE;
```

`DROP` is DDL that directly affects data and typically performs an implicit commit. Never run this command on production or when objects hold data outside the lab scope.

## 12. Common query patterns for developers and DBAs

### 12.1. Which view should you pick first?

| Need | Initial recommended source | What to watch out for |
|---|---|---|
| List tables in your own schema | `USER_TABLES` | Does not require broad catalog privileges |
| Find columns of a granted table in another schema | `ALL_TAB_COLUMNS` | Filter by `OWNER` and `TABLE_NAME` |
| Check invalid objects | `USER_OBJECTS`, `USER_ERRORS`; or `DBA_OBJECTS` if permitted | Check metadata status and compile errors together with dependencies |
| Find foreign keys / primary keys | `USER_CONSTRAINTS`, `USER_CONS_COLUMNS` | For FKs, trace the referenced constraint |
| View indexes on a table | `USER_INDEXES`, `USER_IND_COLUMNS` | Having an index does not prove the optimizer will use it |
| Compare objects across multiple PDBs | `CDB_OBJECTS`/matching CDB views | Needs `CON_ID` and appropriate root privileges |
| View Oracle sessions | `V$SESSION` | Sessions change rapidly; check username/PDB/SQL ID |
| View sessions across RAC instances | `GV$SESSION` | Also read `INST_ID` |
| View SQL currently in cursor cache | `V$SQL` | Not a complete history; avoid exposing raw SQL text |
| View instance parameters | `V$PARAMETER` | Never tune parameters from a single point-in-time observation |
| View session/process resources | `V$RESOURCE_LIMIT` | Distinguish current/max usage from configured limits |

### 12.2. Correlating data by timestamp

Output from views should always accompany **collection timestamp, service/PDB, instance, application release, and measurement purpose**. For example, one `V$SQL` sample shows cursors currently in the shared pool, while comparing it against index metadata captured after a migration completes may reflect **two different points in time**. When diagnosing changes over time, collect multiple samples and correlate with logs rather than inferring trends from a single snapshot.

### 12.3. Should you use `SELECT *`?

In a small lab, `SELECT *` helps explore a view, but on larger systems you should **select only required columns, filter by schema/PDB/user scope, and limit row counts**. Views like `V$SQL` can have many rows and wide columns containing sensitive information. Overly broad dictionary queries or monitoring dashboards polling too frequently also consume resources. Fetch only what you need and protect the output.

## 13. Common misconceptions

| Misconception | Accurate understanding |
|---|---|
| "Static dictionary views never change." | Metadata changes after DDL and administrative operations; *static* merely contrasts with volatile runtime state. |
| "`USER_TABLES` shows every table the user can query." | It focuses on tables in the user's own schema; use `ALL_TABLES` to find visible/accessible tables in other schemas. |
| "`ALL_TABLES` contains all tables across the CDB." | It depends on account privileges and the current container scope. |
| "`DBA_OBJECTS` in PDB A always sees objects in PDB B." | Viewing multiple containers generally requires querying `CDB_*` from root with appropriate privileges. |
| "Having `V$SESSION` lets you see full history of all past sessions." | Dynamic views reflect runtime lifecycle state/metrics; ended sessions may no longer appear. |
| "`V$SQL.ELAPSED_TIME` is the duration of the last query." | It is normally cumulative statistics for the cursor/child, not a single request's duration. |
| "`V$SQL` always holds every SQL statement ever run." | Cursors can age out or clear on restart; use appropriate historical/observability tools if licensed and permitted. |
| "`V$SESSION.STATUS = ACTIVE` means CPU is at 100%." | The session may be waiting on I/O, locks, or another event while a database call is active. |
| "`GV$SESSION` and `V$SESSION` are just two aliases for the same data." | `GV$` adds the instance dimension (`INST_ID`), especially useful in RAC. |
| "`CON_ID` and `INST_ID` are the same ID." | `CON_ID` is container/PDB; `INST_ID` is instance. |
| "`USER_TABLES.NUM_ROWS` always equals `COUNT(*)`." | `NUM_ROWS` is typically previously gathered optimizer statistics and may be stale. |
| "Because public synonym `V$SQL` exists, every user can read it." | Synonyms do not grant privileges; appropriate privileges on the view are required. |
| "Granting `DBA` is the easiest way for a dashboard to collect metrics." | Broad grants increase risk; restrict to only needed views and data. |
| "AWR/ASH are just like basic V$ views and free to use by default." | Certain diagnostic features carry licensing and privilege conditions; confirm before using. |

## 14. Review questions

**Question 1.** You need to know which columns the `CUSTOMER` table in your own schema has. Should you start with `USER_TAB_COLUMNS` or `V$SESSION`?

**Answer:** `USER_TAB_COLUMNS`, because it holds column structural metadata; `V$SESSION` describes active sessions.

**Question 2.** An application user has `SELECT` privilege on the `REPORTS` table in schema `REPORT_OWNER`, but does not own the table. Should they check `USER_TABLES` or `ALL_TABLES`?

**Answer:** `ALL_TABLES` filtered by `OWNER = 'REPORT_OWNER'`; visibility depends on privileges. With `USER_TABLES`, you primarily see tables in your own schema.

**Question 3.** A DBA at `CDB$ROOT` wants to distinguish the `ORDERS` table across two PDBs. Which field is needed besides `OWNER` and `OBJECT_NAME`?

**Answer:** `CON_ID`/container, combined with `CDB_*` views and appropriate privileges.

**Question 4.** A session has `SID = 125` on RAC instance 1 and RAC instance 2. Is this the same session?

**Answer:** You cannot conclude that. You need `INST_ID`, `SID`, `SERIAL#`, and the corresponding timestamp/container.

**Question 5.** After running `INSERT` for 500 rows, `USER_TABLES.NUM_ROWS` still holds the old value. Did Oracle fail to save the data?

**Answer:** No. `NUM_ROWS` may be unrefreshed statistics; verify the transaction and actual data with appropriate SQL if permitted.

**Question 6.** `V$SQL` reports a cursor with `EXECUTIONS = 100` and `ELAPSED_TIME = 2,000,000` microseconds. Can you assume every request took exactly 20 ms?

**Answer:** No. These are cumulative statistics in the cursor context; a simple average does not reflect latency distribution, per-request duration, child cursors, parallel execution effects, or cache lifetime limits.

**Question 7.** A developer querying `V$SESSION` encounters `ORA-00942`, even though the view name is in the documentation. What should be checked?

**Answer:** Read privileges on the dynamic view/synonym and container context. Ask the DBA for minimal privileges or the needed metrics; never grant `DBA` to a runtime account.

## Conclusion

In Oracle, the **data dictionary** describes the database's managed structure and metadata; **static dictionary views** such as `USER_*`, `ALL_*`, `DBA_*`, and `CDB_*` provide different privilege- and container-scoped lenses onto that metadata. **Dynamic performance views** such as `V$SESSION`, `V$SQL`, and `V$INSTANCE` expose live activity and operational statistics, while `GV$...` adds a multi-instance view in RAC environments.

To interpret results accurately, always identify **user/schema, PDB/container, instance, collection timestamp, and access privileges**. Use the dictionary to learn *how objects are defined*, dynamic views to see *how the database is operating*, and combine both with logs, metrics, and empirical checks when troubleshooting. Never interpret metadata as live row counts, treat V$ metrics as complete history, or grant broad catalog privileges merely for the convenience of one query.
