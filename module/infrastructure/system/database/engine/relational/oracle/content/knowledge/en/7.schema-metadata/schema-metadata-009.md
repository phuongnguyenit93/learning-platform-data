# Extracting DDL with `DBMS_METADATA` in Oracle Database

## 1. Purpose: retrieving object definitions from the data dictionary

When a table, view, index, sequence, or PL/SQL package already exists in Oracle Database, an administrator may need to retrieve its creation statement for code review, storing in Git, comparing two environments, preparing migrations, or analyzing schema structure. Oracle provides the **`DBMS_METADATA`** package to read metadata from the data dictionary and transform it into **DDL (Data Definition Language)**, such as `CREATE TABLE`, `CREATE VIEW`, `CREATE INDEX`, or `CREATE OR REPLACE PACKAGE`.

For example, suppose a database has an `APP.ORDERS` table, yet the development team no longer has the original SQL creation script. The query:

```sql
SELECT DBMS_METADATA.GET_DDL('TABLE', 'ORDERS', 'APP')
FROM   DUAL;
```

returns DDL equivalent to the table's current definition, including columns, data types, constraints, and other attributes depending on transform configuration. This is **metadata at query time**, not a recording of every DDL statement ever executed.

**Three limitations to understand right away:**

1. **DDL is not table data**: `CREATE TABLE` does not contain millions of existing rows. Exporting data requires another mechanism such as Data Pump, backups, or a data pipeline.
2. **One object's DDL is not the entire schema**: `GET_DDL('TABLE', ...)` alone may omit independent indexes, triggers, comments, object grants, packages, jobs, and dependencies needed to reconstruct an application.
3. **Reading DDL is not executing DDL**: `GET_DDL` only returns text; running the extracted script on a target environment is a separate action that modifies the database and requires review.

> This content focuses on Oracle Database 19c and the `DBMS_METADATA` mechanism maintained in newer releases. Schema and object names in examples are hypothetical. Before running on real systems, verify the right PDB, access privileges, and Oracle documentation matching your running release.

## 2. How `DBMS_METADATA` works

The package can return metadata as XML, SXML, or DDL. When a user requests DDL, Oracle reads accessible metadata and applies **transforms** to produce the corresponding SQL statements.

```text
                      Oracle data dictionary
                        (schema metadata)
                                │
                                ▼
                    DBMS_METADATA retrieval
                    ┌──────────────────────┐
                    │ Object type          │
                    │ Owner / object name  │
                    │ Privilege filtering  │
                    └──────────┬───────────┘
                               │
                               ▼
                     XML metadata model
                               │
                     ┌─────────┴──────────┐
                     │ Transform 'DDL'    │
                     │ PRETTY / STORAGE   │
                     │ TABLESPACE / ...   │
                     └─────────┬──────────┘
                               │
                               ▼
                        CLOB containing DDL
                               │
              ┌────────────────┴────────────────┐
              ▼                                 ▼
       SQL*Plus / SQLcl                    PL/SQL / application
       display / SPOOL                     receives full CLOB
              │                                 │
              └────────────────┬────────────────┘
                               ▼
                    Review → store source → check
                    dependencies → decide deployment
```

In this model, **`GET_DDL` is the short entry point** for a single named object. When iterating over many objects, the API opens a retrieval context with `OPEN`, filters with `SET_FILTER`, attaches transforms with `ADD_TRANSFORM`, calls `FETCH_CLOB` repeatedly, and calls `CLOSE`.

### 2.1. Three metadata categories to distinguish

| Category | Examples | Common function |
| --- | --- | --- |
| **Named object** | Table `APP.ORDERS`, view `APP.V_ORDERS`, package `APP.ORDER_API` | `GET_DDL` |
| **Dependent object** | Indexes, object grants, or comments dependent on a base table | `GET_DEPENDENT_DDL` |
| **Granted object** | System privileges or role grants issued to a user/role | `GET_GRANTED_DDL` |

Oracle also provides **heterogeneous collection** types such as `SCHEMA_EXPORT`, `TABLE_EXPORT`, and `DATABASE_EXPORT`. These represent collections of multiple object types and use the `OPEN`/`FETCH_*` interface or Data Pump tools; do not pass `SCHEMA_EXPORT` to `GET_DDL` expecting an entire schema in one call.

## 3. Preparing connection, privileges, and schema scope

### 3.1. Which PDB are you in?

In a multitenant architecture, the same name `APP.ORDERS` can exist across multiple PDBs. `DBMS_METADATA` operates within the **session's container context** and available privileges. Before exporting, confirm database, service, and container:

```sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME')     AS con_name,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
       SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema,
       SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user
FROM   dual;
```

Sample output:

```text
CON_NAME    SERVICE_NAME             CURRENT_SCHEMA  SESSION_USER
----------  -----------------------  --------------  ------------
SALES_PDB   sales_app.example.com    APP             APP
```

If the client connects to `CDB$ROOT` by mistake, DDL extracted at root does not automatically represent an identically named object inside `SALES_PDB`. Do not alter schemas or arbitrarily run `ALTER SESSION SET CONTAINER` to force cross-tenant metadata extraction; connect to the proper PDB service with an appropriately privileged account.

### 3.2. Metadata read privileges

Under `DBMS_METADATA`'s security model in Oracle 19c:

- **Regular users** can retrieve metadata for objects they own. They can also retrieve certain items such as public synonyms or grants related to them per package rules.
- **Privileged users** as defined by Oracle—typically connected as `SYS` or holding `SELECT_CATALOG_ROLE`—can retrieve metadata belonging to other schemas within their privilege scope.
- Having only `SELECT` on another schema's table **does not mean** you can extract the owner's full `CREATE TABLE` via `GET_DDL`.
- When requesting an object you are not permitted to see, the API may report **no matching object found**, resembling a nonexistent object; errors like `ORA-31603` must be evaluated alongside privileges and container context.

**Important PL/SQL boundary:** Inside **definer's-rights** (`AUTHID DEFINER`, the default) procedures, functions, or packages, roles are generally disabled. An account that runs `GET_DDL` interactively thanks to `SELECT_CATALOG_ROLE` can still fail when moving that same logic into a default stored procedure. If caller privileges are needed, design with **invoker's rights (`AUTHID CURRENT_USER`)** and appropriate privileges; never work around this by blindly granting `DBA` or running all extractions as `SYS`.

### 3.3. Verify the object before extracting DDL

```sql
-- In the connected schema: objects owned by the current user.
SELECT object_name, object_type, status
FROM   user_objects
WHERE  object_name = 'ORDERS'
ORDER BY object_type;

-- If permitted to view another schema in the right PDB:
SELECT owner, object_name, object_type, status
FROM   all_objects
WHERE  owner = 'APP'
AND    object_name = 'ORDERS'
ORDER BY object_type;
```

`ALL_OBJECTS` shows metadata per view/object visibility; **having a row in `ALL_OBJECTS` does not guarantee permission to extract DDL via `DBMS_METADATA`**. Standard object names and owners are stored in uppercase by Oracle when created **without quoted identifiers**. Objects created like `"OrderItems"` preserve exact casing; the `name`/`schema` arguments must match the exact stored name.

## 4. `GET_DDL`: the first query to know

### 4.1. Function signature

```text
DBMS_METADATA.GET_DDL(
    object_type IN VARCHAR2,
    name        IN VARCHAR2,
    schema      IN VARCHAR2 DEFAULT NULL,
    version     IN VARCHAR2 DEFAULT 'COMPATIBLE',
    model       IN VARCHAR2 DEFAULT 'ORACLE',
    transform   IN VARCHAR2 DEFAULT 'DDL'
) RETURN CLOB;
```

| Parameter | Meaning | Example values |
| --- | --- | --- |
| `object_type` | Object type in the metadata API, **not always identical verbatim to `USER_OBJECTS.OBJECT_TYPE`** | `TABLE`, `VIEW`, `INDEX`, `PACKAGE_SPEC`, `PACKAGE_BODY` |
| `name` | Object name matching the exact form stored in the dictionary | `ORDERS`, `OrderItems` |
| `schema` | Owner, defaulting to the current user per API rules | `APP` |
| `version` | Metadata version representation, defaulting to database compatibility | `COMPATIBLE`, `LATEST` |
| `model` | Metadata model; Oracle supports `ORACLE` | `ORACLE` |
| `transform` | Converts XML metadata to DDL | `DDL` |

The return value is a **CLOB**; the client tool must display or write the full CLOB. Never use `DBMS_LOB.SUBSTR(..., 4000, 1)` as a final export method because it only captures **a slice**.

### 4.2. Extracting common object types

```sql
-- A table with explicit owner.
SELECT DBMS_METADATA.GET_DDL('TABLE', 'ORDERS', 'APP') AS ddl
FROM   dual;

-- Standalone index.
SELECT DBMS_METADATA.GET_DDL('INDEX', 'IDX_ORDERS_CREATED_AT', 'APP') AS ddl
FROM   dual;

-- View.
SELECT DBMS_METADATA.GET_DDL('VIEW', 'V_ORDER_TOTAL', 'APP') AS ddl
FROM   dual;

-- Sequence.
SELECT DBMS_METADATA.GET_DDL('SEQUENCE', 'SEQ_ORDER_ID', 'APP') AS ddl
FROM   dual;

-- Trigger.
SELECT DBMS_METADATA.GET_DDL('TRIGGER', 'TRG_ORDER_AUDIT', 'APP') AS ddl
FROM   dual;

-- Stored procedure or function.
SELECT DBMS_METADATA.GET_DDL('PROCEDURE', 'RECALCULATE_ORDER', 'APP') AS ddl
FROM   dual;

SELECT DBMS_METADATA.GET_DDL('FUNCTION', 'CALC_TAX', 'APP') AS ddl
FROM   dual;

-- Separate package specification and package body.
SELECT DBMS_METADATA.GET_DDL('PACKAGE_SPEC', 'ORDER_API', 'APP') AS ddl
FROM   dual;

SELECT DBMS_METADATA.GET_DDL('PACKAGE_BODY', 'ORDER_API', 'APP') AS ddl
FROM   dual;
```

All names above are examples: run only queries for objects that actually exist and that you are authorized to access. `PACKAGE` is also an API-supported object type; per Oracle 19c documentation, it retrieves both specification and body under default configuration. When storing source and automating builds, using `PACKAGE_SPEC`/`PACKAGE_BODY` gives clearer control over file separation and ordering.

### 4.3. Quoted identifiers and case sensitivity

Suppose a table was created as follows in an authorized schema:

```sql
CREATE TABLE "OrderItems" (
    "ItemId" NUMBER PRIMARY KEY,
    "Qty"    NUMBER NOT NULL
);
```

The name stored by Oracle is **`OrderItems`**, not `ORDERITEMS`. When calling `GET_DDL`, pass the exact string:

```sql
SELECT DBMS_METADATA.GET_DDL('TABLE', 'OrderItems')
FROM   dual;
```

`name` is a string value filtering the object name, not SQL text containing SQL identifier double quotes. Therefore, do not include `"` characters inside the `name` argument unless double quotes are literally characters in the target name. For standard unquoted objects, pass uppercase.

### 4.4. `GET_DDL('USER', ...)` and system objects

`DBMS_METADATA` also supports database-level object types such as `USER`, `ROLE`, and `TABLESPACE`, subject to privileges. However, user DDL can include **authentication attributes, account settings, or sensitive administrative details**; tablespace DDL can expose datafile paths and environment-specific storage traits. Never commit such files to public repositories or run them verbatim on another database without reviewing, sanitizing sensitive details, and verifying privileges.

## 5. Displaying CLOBs properly in SQL*Plus and SQLcl

A frequent mistake occurs when `GET_DDL` generates the full content, yet the client **displays only a few thousand characters**, making learners think metadata was truncated.

### 5.1. Display settings

```sql
-- SQL*Plus / SQLcl, before calling GET_DDL.
SET LONG 2000000
SET LONGCHUNKSIZE 32767
SET PAGESIZE 0
SET LINESIZE 32767
SET HEADING OFF
SET FEEDBACK OFF
SET TRIMSPOOL ON

SELECT DBMS_METADATA.GET_DDL('TABLE', 'ORDERS', 'APP')
FROM   dual;
```

Explanation:

- `SET LONG` sets the maximum length of LONG/CLOB values displayed by SQL*Plus; increase it enough for complex objects.
- `SET LONGCHUNKSIZE` adjusts the chunk size the client fetches per read; it does not alter metadata content.
- `PAGESIZE 0`, `HEADING OFF`, and `FEEDBACK OFF` keep column headers, page breaks, and row-count feedback out of the SQL script.
- `LINESIZE` and `TRIMSPOOL` help output clean text formatting; they do not by themselves prove every CLOB character was written.

These are **client commands**, not database SQL. Other tools like SQL Developer, DBeaver, JDBC, or IDEs have their own CLOB display/download settings. If a grid view truncates output, use full-CLOB export or a streaming reader API.

### 5.2. Writing to a file with `SPOOL`

Example script run in SQL*Plus/SQLcl, where `APP.ORDERS` actually exists:

```sql
SET ECHO OFF
SET VERIFY OFF
SET HEADING OFF
SET FEEDBACK OFF
SET PAGESIZE 0
SET LONG 2000000
SET LONGCHUNKSIZE 32767
SET LINESIZE 32767
SET TRIMSPOOL ON

EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'DEFAULT');
EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'SQLTERMINATOR', TRUE);

SPOOL orders_table.sql
SELECT DBMS_METADATA.GET_DDL('TABLE', 'ORDERS', 'APP') FROM dual;
SPOOL OFF

EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'DEFAULT');
```

`SPOOL` writes text output to a file on **the machine running SQL*Plus/SQLcl**, not automatically to the server's datafile directory. File paths and write permissions depend on the client environment. After exporting, inspect the actual file to confirm there are no prompts or headers, content was not truncated, statements have proper terminators, and encoding is correct before committing to Git.

**Watch out for length:** If an object has a multi-megabyte package body, set `SET LONG` high enough or use a streaming CLOB exporter. `SET LINESIZE` does not solve truncation caused by too small a `SET LONG`.

## 6. Controlling DDL output with `SESSION_TRANSFORM`

Oracle-generated DDL can be very verbose due to `PCTFREE`, `INITRANS`, `STORAGE`, `TABLESPACE`, `LOGGING`, and numerous physical attributes. When saving schemas for review or moving across environments with different tablespace names, decide whether to **preserve physical details** or **omit them**.

Oracle provides `DBMS_METADATA.SET_TRANSFORM_PARAM` with the **`DBMS_METADATA.SESSION_TRANSFORM`** handle to adjust how `GET_DDL`, `GET_DEPENDENT_DDL`, and `GET_GRANTED_DDL` format DDL in the **current session**.

### 6.1. Omitting physical attributes for cleaner scripts

```sql
BEGIN
  DBMS_METADATA.SET_TRANSFORM_PARAM(
    DBMS_METADATA.SESSION_TRANSFORM, 'SEGMENT_ATTRIBUTES', FALSE);

  DBMS_METADATA.SET_TRANSFORM_PARAM(
    DBMS_METADATA.SESSION_TRANSFORM, 'SQLTERMINATOR', TRUE);

  DBMS_METADATA.SET_TRANSFORM_PARAM(
    DBMS_METADATA.SESSION_TRANSFORM, 'PRETTY', TRUE);
END;
/

SELECT DBMS_METADATA.GET_DDL('TABLE', 'ORDERS', 'APP')
FROM   dual;

-- Restore the session to default transform settings after use.
EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'DEFAULT');
```

`SEGMENT_ATTRIBUTES=FALSE` omits segment-level physical attributes, including items such as storage, tablespace, and logging per transform behavior. If you **want to omit only `STORAGE` while keeping `TABLESPACE`**, set `STORAGE=FALSE` and leave `SEGMENT_ATTRIBUTES` enabled. When `SEGMENT_ATTRIBUTES=FALSE`, both `STORAGE` and `TABLESPACE` are ignored because the parent group is disabled.

### 6.2. Key transform parameters

| Parameter | Scope | When `TRUE`/`FALSE` | Notes |
| --- | --- | --- | --- |
| `PRETTY` | Multiple object types | Indented formatting on/off | Defaults to `TRUE` |
| `SQLTERMINATOR` | Multiple object types | Appends `;` or `/` on/off | Defaults to `FALSE`; useful for runnable SQL files |
| `SEGMENT_ATTRIBUTES` | Tables, indexes, and some other objects | Includes physical, storage, tablespace, logging | Stripping details can change storage semantics |
| `STORAGE` | Tables/indexes and supported groups | Emits storage clause on/off | Ignored if `SEGMENT_ATTRIBUTES=FALSE` |
| `TABLESPACE` | Tables/indexes and supported groups | Emits tablespace clause on/off | Ignored if `SEGMENT_ATTRIBUTES=FALSE` |
| `CONSTRAINTS` | Tables | Emits non-referential constraints on/off | Disabling omits `PRIMARY KEY`, `UNIQUE`, `CHECK` from table DDL |
| `REF_CONSTRAINTS` | Tables | Emits foreign keys on/off | Do not disable when reconstructing all constraints |
| `CONSTRAINTS_AS_ALTER` | Tables | Emits constraints as `ALTER TABLE` when supported | Requires `CONSTRAINTS=TRUE` |
| `PARTITIONING` | Tables, indexes | Emits partitioning clauses on/off | Disabling alters logical/physical structure and may break migrations |
| `SPECIFICATION`, `BODY` | Packages/types | Controls whether spec/body are emitted | Can alternatively use dedicated spec/body object types |
| `DEFAULT` | All supported transforms | With `TRUE`, resets transforms to defaults | Always reset after an export session |

Example hiding only `STORAGE` while keeping the tablespace name:

```sql
EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'DEFAULT');
EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'STORAGE', FALSE);

SELECT DBMS_METADATA.GET_DDL('TABLE', 'ORDERS', 'APP')
FROM   dual;

EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'DEFAULT');
```

### 6.3. Session transforms persist until reset

`SESSION_TRANSFORM` belongs to the **database session**. If a script sets `CONSTRAINTS=FALSE` and forgets to reset it, subsequent `GET_DDL` calls in the same session continue omitting constraints. With a connection pool, reusing the same physical session makes this bug even harder to spot.

Therefore, a repeatable extraction workflow should **explicitly set transforms before reading**, **reset to `DEFAULT` afterward**, and avoid semantics-altering transforms when the goal is full DDL backup.

## 7. What is still missing from a single table's `GET_DDL`?

A schema comprises relationships across many objects. `CREATE TABLE` for `APP.ORDERS` may include columns, data types, and enabled constraints, yet fully reconstructing an application also requires inspecting:

```text
APP.ORDERS
  ├── CREATE TABLE + column definitions
  ├── constraints (PK, UNIQUE, CHECK, FK)
  ├── indexes (especially separately created indexes)
  ├── triggers
  ├── column/table comments
  ├── object grants / synonyms
  ├── sequences, procedures, packages, and views referencing the table
  └── related metadata such as policies, jobs, materialized views, types...
```

**Do not assume everything fits into one `GET_DDL('TABLE')` call.** Certain constraints may print inside table DDL by default; remaining dependent objects usually must be exported separately via `GET_DDL`, `GET_DEPENDENT_DDL`, `GET_GRANTED_DDL`, or a dependency-aware schema export workflow.

### 7.1. `GET_DEPENDENT_DDL`: metadata dependent on a base object

Abbreviated signature:

```text
DBMS_METADATA.GET_DEPENDENT_DDL(
    object_type, base_object_name, base_object_schema,
    version, model, transform, object_count
) RETURN CLOB;
```

Example retrieving DDL for object grants issued **on table** `APP.ORDERS`:

```sql
SELECT DBMS_METADATA.GET_DEPENDENT_DDL(
           'OBJECT_GRANT', 'ORDERS', 'APP') AS ddl
FROM   dual;
```

Example retrieving indexes whose metadata depends on the table:

```sql
SELECT DBMS_METADATA.GET_DEPENDENT_DDL(
           'INDEX', 'ORDERS', 'APP') AS ddl
FROM   dual;
```

These calls can return **multiple DDL statements inside a single CLOB**. If no objects of that dependent type exist or the account cannot view them, an object-not-found error may occur. Check dictionary views such as `ALL_INDEXES`, `ALL_TAB_PRIVS`, and `ALL_TRIGGERS` within privileges before concluding.

**Watch out for duplicates:** When `GET_DDL('TABLE')` already includes a primary key or unique constraint definition along with an Oracle-created supporting index, do not blindly replay every `CREATE INDEX` statement without checking its origin, as that can cause duplicates or conflicts. Decide on a consistent strategy for recreating constraints and indexes.

### 7.2. `GET_GRANTED_DDL`: privileges granted to a user/role

`GET_GRANTED_DDL` takes a **grantee** (the user or role receiving privileges), not the name of a granted table:

```sql
-- System privileges granted to user APP.
SELECT DBMS_METADATA.GET_GRANTED_DDL('SYSTEM_GRANT', 'APP')
FROM   dual;

-- Roles granted to APP.
SELECT DBMS_METADATA.GET_GRANTED_DDL('ROLE_GRANT', 'APP')
FROM   dual;

-- Object privileges where APP is the grantee.
SELECT DBMS_METADATA.GET_GRANTED_DDL('OBJECT_GRANT', 'APP')
FROM   dual;
```

Distinguish these two questions:

| Question | Appropriate API |
| --- | --- |
| Who holds privileges on **table `APP.ORDERS`**? | `GET_DEPENDENT_DDL('OBJECT_GRANT','ORDERS','APP')` |
| Which object grants were issued **to user `REPORT_USER`**? | `GET_GRANTED_DDL('OBJECT_GRANT','REPORT_USER')` |
| Which system privileges are granted to `REPORT_USER`? | `GET_GRANTED_DDL('SYSTEM_GRANT','REPORT_USER')` |
| Which roles are granted to `REPORT_USER`? | `GET_GRANTED_DDL('ROLE_GRANT','REPORT_USER')` |

When exporting a user or reconstructing privileges, also review **default roles**, profiles, quotas, system grants, object grants, common/local grants in CDB/PDB, and other security policies. A standalone `CREATE USER` does not capture all granted privileges.

## 8. Extracting multiple tables in a schema using SQL

If the goal is simply to quickly extract DDL for all application tables in the current schema, you can query the dictionary and invoke `GET_DDL` per table.

```sql
-- Inside schema APP, no cross-schema metadata privileges required.
SET LONG 2000000
SET PAGESIZE 0

EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'DEFAULT');
EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'SQLTERMINATOR', TRUE);

SELECT DBMS_METADATA.GET_DDL('TABLE', t.table_name)
FROM   user_all_tables t
WHERE  t.nested = 'NO'
AND    (t.iot_type IS NULL OR t.iot_type = 'IOT')
ORDER  BY t.table_name;

EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'DEFAULT');
```

Oracle uses **`NESTED='NO'`** and **`IOT_TYPE IS NULL OR IOT_TYPE='IOT'`** in its official example to avoid calling `GET_DDL` on internal sub-objects or overflow segments of tables. If a schema includes external tables, temporary tables, partitions, nested collections, XMLType, or specialized objects, explicitly verify the inventory to export rather than assuming this filter covers every case.

Example extracting DDL for views owned by the user:

```sql
SELECT DBMS_METADATA.GET_DDL('VIEW', view_name)
FROM   user_views
ORDER  BY view_name;
```

Do not blindly feed `USER_OBJECTS.OBJECT_TYPE` into `GET_DDL` across all object types: `DBMS_METADATA` object type names differ from dictionary values in several cases (`PACKAGE BODY` vs. `PACKAGE_BODY`), and some dictionary rows are internal objects unsuitable for standalone recreation.

### 8.1. Automated DDL exports must respect dependencies

Suppose view `V_ORDER_REPORT` depends on table `ORDERS`, a trigger calls package `ORDER_API`, and the package uses type `ORDER_ROW_TYPE`. If scripts are exported alphabetically and executed in order, many statements will fail or leave objects temporarily **`INVALID`**.

Typical deployment order to evaluate:

1. Users/roles, tablespaces, and schema-level prerequisites where authorized.
2. Types, sequences, tables, and foundational objects.
3. Indexes/constraints and dependent objects per design.
4. Views, packages/procedures/functions/triggers/materialized views in dependency order.
5. Grants, synonyms, jobs/policies, and operational objects.
6. Recompile and verify `USER_OBJECTS.STATUS`, constraints, indexes, privileges, and invalid objects.

This is a **guideline**, not a universal rule for every schema: types, views, foreign keys, and PL/SQL can form mutual or complex dependency chains. For large schemas, consider **Data Pump** or the `OPEN('SCHEMA_EXPORT')` interface rather than writing custom scripts sorted only alphabetically.

## 9. Multi-object API: `OPEN` → `SET_FILTER` → `ADD_TRANSFORM` → `FETCH_CLOB` → `CLOSE`

When programmatic DDL retrieval is required, `DBMS_METADATA` offers a handle-based API. `OPEN` creates a **retrieval context**, which can be filtered by schema/name, attached to transforms, and iterated via `FETCH_CLOB`.

```text
h = OPEN('TABLE')
  │
  ├── SET_FILTER(h, 'SCHEMA', 'APP')
  ├── SET_FILTER(h, 'NAME', 'ORDERS') [optional]
  ├── t = ADD_TRANSFORM(h, 'DDL')
  └── SET_TRANSFORM_PARAM(t, 'SEGMENT_ATTRIBUTES', FALSE)
         │
         ▼
       FETCH_CLOB(h) ── CLOB object #1
         │
         ▼
       FETCH_CLOB(h) ── CLOB object #2 ...
         │
         ▼
       FETCH_CLOB(h) ── NULL = no more objects
         │
         ▼
          CLOSE(h)
```

### 9.1. Runnable PL/SQL example: iterating metadata and counting CLOB lengths

The following snippet **only reads metadata and prints character lengths** of each DDL to demonstrate iterating through objects cleanly. It does not write files yet, avoiding accidental DDL corruption from `DBMS_OUTPUT` line truncation:

```sql
SET SERVEROUTPUT ON SIZE UNLIMITED

DECLARE
  l_handle       NUMBER;
  l_transform    NUMBER;
  l_ddl          CLOB;
  l_count        PLS_INTEGER := 0;
BEGIN
  l_handle := DBMS_METADATA.OPEN('TABLE');
  DBMS_METADATA.SET_FILTER(l_handle, 'SCHEMA', 'APP');

  l_transform := DBMS_METADATA.ADD_TRANSFORM(l_handle, 'DDL');
  DBMS_METADATA.SET_TRANSFORM_PARAM(
    l_transform, 'SQLTERMINATOR', TRUE);
  DBMS_METADATA.SET_TRANSFORM_PARAM(
    l_transform, 'SEGMENT_ATTRIBUTES', FALSE);

  LOOP
    l_ddl := DBMS_METADATA.FETCH_CLOB(l_handle);
    EXIT WHEN l_ddl IS NULL;

    l_count := l_count + 1;
    DBMS_OUTPUT.PUT_LINE(
      'Object #' || l_count || ': ' || DBMS_LOB.GETLENGTH(l_ddl) || ' characters');

    -- In a real application, persist the entire l_ddl via CLOB streaming.
    -- Do not store only DBMS_LOB.SUBSTR(l_ddl, 4000, 1).
  END LOOP;

  DBMS_METADATA.CLOSE(l_handle);
  l_handle := NULL;
  DBMS_OUTPUT.PUT_LINE('Total objects: ' || l_count);
EXCEPTION
  WHEN OTHERS THEN
    IF l_handle IS NOT NULL THEN
      DBMS_METADATA.CLOSE(l_handle);
    END IF;
    RAISE;
END;
/
```

Replace `APP` with a schema your account has permission to inspect before running. `OPEN('TABLE')` selects table objects; `SET_FILTER` narrows scope; `ADD_TRANSFORM` converts XML metadata into DDL; `FETCH_CLOB` retrieves each object; and `CLOSE` releases the handle.

**Two distinct handle types:** `l_handle` from `OPEN` is passed to `SET_FILTER`, `FETCH_CLOB`, and `CLOSE`. `l_transform` from `ADD_TRANSFORM` is passed to `SET_TRANSFORM_PARAM`; mistakenly passing `l_handle` as a transform handle raises errors. `SESSION_TRANSFORM` applies to `GET_*` calls, while a transform added to an `OPEN` context is configured directly via `l_transform` (unless parameter inheritance via `INHERIT` is enabled).

### 9.2. When to use `SCHEMA_EXPORT`?

For a complete schema, `OPEN('SCHEMA_EXPORT')` opens a **multi-object-type** context capable of emitting DDL in the object-group order Oracle designed for schema exports. Oracle Database Utilities shows fetching CLOBs and storing them in a staging table for inspection.

```sql
-- Core calls inside a PL/SQL program;
-- illustrates the retrieval pipeline only, not a standalone script.
l_handle := DBMS_METADATA.OPEN('SCHEMA_EXPORT');
DBMS_METADATA.SET_FILTER(l_handle, 'SCHEMA', 'APP');
l_transform := DBMS_METADATA.ADD_TRANSFORM(l_handle, 'DDL');

-- Loop DBMS_METADATA.FETCH_CLOB(l_handle) until NULL, then CLOSE.
```

For complex collections, locate valid object paths using `SCHEMA_EXPORT_OBJECTS`, `TABLE_EXPORT_OBJECTS`, `DATABASE_EXPORT_OBJECTS`, and filter parameters like `INCLUDE_PATH_EXPR`/`EXCLUDE_PATH_EXPR`. Never equate `SCHEMA_EXPORT` output with `GET_DDL('TABLE')`: objects, grants, statistics, and dependent metadata span many DDL statements. Rebuilding a schema still requires handling privileges, ordering, and environment-specific objects.

## 10. Customizing schema/tablespace names with `MODIFY` and `REMAP`

A common need is copying a table definition from `APP` to `APP_TEST`, or from tablespace `DATA_PROD` to `DATA_TEST`. In the multi-object API, Oracle allows chaining a **`MODIFY` transform** followed by a **`DDL` transform**, applying `SET_REMAP_PARAM` to the `MODIFY` handle.

Example reading a table's DDL and remapping the owner without executing DDL:

```sql
SET SERVEROUTPUT ON SIZE UNLIMITED

DECLARE
  l_handle    NUMBER;
  l_modify    NUMBER;
  l_ddl_tr    NUMBER;
  l_ddl       CLOB;
BEGIN
  l_handle := DBMS_METADATA.OPEN('TABLE');
  DBMS_METADATA.SET_FILTER(l_handle, 'SCHEMA', 'APP');
  DBMS_METADATA.SET_FILTER(l_handle, 'NAME', 'ORDERS');

  l_modify := DBMS_METADATA.ADD_TRANSFORM(l_handle, 'MODIFY');
  DBMS_METADATA.SET_REMAP_PARAM(
    l_modify, 'REMAP_SCHEMA', 'APP', 'APP_TEST');

  l_ddl_tr := DBMS_METADATA.ADD_TRANSFORM(l_handle, 'DDL');
  DBMS_METADATA.SET_TRANSFORM_PARAM(
    l_ddl_tr, 'SQLTERMINATOR', TRUE);

  l_ddl := DBMS_METADATA.FETCH_CLOB(l_handle);
  DBMS_OUTPUT.PUT_LINE('DDL chars: ' || NVL(DBMS_LOB.GETLENGTH(l_ddl), 0));

  DBMS_METADATA.CLOSE(l_handle);
  l_handle := NULL;
EXCEPTION
  WHEN OTHERS THEN
    IF l_handle IS NOT NULL THEN
      DBMS_METADATA.CLOSE(l_handle);
    END IF;
    RAISE;
END;
/
```

This snippet prints only the length to avoid losing the remainder of the CLOB. In real usage, export the full `l_ddl` and review the file before running. **`REMAP_TABLESPACE`** is also available where supported by the object/metadata type. See the `DBMS_METADATA` Reference for exact parameters and supported object types.

**Important limitation:** Oracle explicitly notes that remapping **is not guaranteed to rewrite all schema reference strings** embedded inside PL/SQL bodies, views, triggers, types, or dynamic code. For example, package source containing `EXECUTE IMMEDIATE 'SELECT ... FROM APP.ORDERS'` may require manual editing. Additionally, remapping an owner does not guarantee the target schema has the user, quota, tablespace, privileges, or dependencies required.

## 11. DDL is a metadata snapshot, not a full backup

### 11.1. What `DBMS_METADATA` can and cannot provide

| Requirement | How `DBMS_METADATA` handles it | If more is needed |
| --- | --- | --- |
| Retrieve `CREATE TABLE` | Very well suited via `GET_DDL('TABLE')` | Inspect dependent objects and data separately |
| Retrieve view, sequence, package definitions | Well suited via `GET_DDL` for the exact object type | Check dependencies and version compatibility |
| Retrieve indexes/grants/comments on a table | Via `GET_DEPENDENT_DDL` or collection API | Check duplicate constraints/indexes and privileges |
| Retrieve grants issued to a user | Via `GET_GRANTED_DDL` | Inventory profiles, quotas, common/local grants |
| Export an entire multi-object schema | `OPEN('SCHEMA_EXPORT')`, filters, transforms, fetch | At large scale, use Data Pump metadata export |
| Export existing data rows | **Not** via `GET_DDL` | Data Pump, backups, ETL, or appropriate tooling |
| Point-in-time recovery backups | **Not supported** | RMAN, archived redo, backup/DR strategy |
| Recover full history of every `ALTER TABLE` | **Not supported** | DDL auditing or prior version control |
| Produce a universally safe migration script | Provides a starting point only | Review diffs, dependencies, privileges, test deploy/rollback |

### 11.2. Current DDL does not equal change history

Suppose a table was created with two columns, then `ALTER TABLE` added three columns, changed one column's type, and added constraints. `GET_DDL('TABLE', ...)` describes the **current structural state**; it does not reconstruct the chronological sequence of events.

Thus, a Git-managed schema still needs ordered, versioned migration files (Liquibase, Flyway, or an equivalent internal mechanism). `DBMS_METADATA` helps **detect drift** or rebuild a baseline; it does not replace controlled migration history.

### 11.3. Data Pump `METADATA_ONLY` differs from fetching a single CLOB

When exporting multiple object types, privileges, and dependencies in an importable format, Oracle Data Pump supports **`CONTENT=METADATA_ONLY`**. Optionally, `impdp SQLFILE=...` lets you inspect DDL from a dump file without executing object creation statements. That is a Data Pump dump/SQLFILE workflow with its own privileges and file behavior, not an argument to `DBMS_METADATA.GET_DDL`.

These tools share adjacent goals yet differ in output and management: `GET_DDL` is very handy for reviewing individual objects, while Data Pump suits exporting/importing large schemas under administrative workflows.

## 12. Privileges, security, and common information leaks

Metadata contains more than column names: some objects contain **business logic**, host/service names, file paths, authentication configurations, network endpoints, or sensitive comments inside PL/SQL source. Control exports with the same care as any other configuration artifact.

1. **Use least privilege**: prefer extracting from the owning schema; use cross-schema privileges only when authorized for the task.
2. **Pick the right PDB**: never accidentally export from root or another PDB and mix scripts across tenants.
3. **Protect secrets**: review DDL for users, database links, credential-related objects, directories/paths, scheduler jobs, and package bodies before committing to Git, attaching to tickets, or sharing externally.
4. **Clarify script purpose**: DDL for code review may omit storage clauses, whereas exact recovery DDL must preserve critical attributes. Never use one transform profile for every purpose.
5. **Do not blindly replay DDL**: `CREATE`, `ALTER`, `DROP`, and `GRANT` mutate the database. Extracting metadata is read-only; applying scripts is a separate change request.
6. **Watch consistency**: if multiple users run DDL concurrently, hundreds of `GET_DDL` calls at different instants may yield an inconsistent schema snapshot. For environment promotions, use a freeze/change window or a consistency-aware export tool.

### 12.1. Definer's rights and disabled roles

This scenario frequently causes confusion during automation:

```text
DBA_USER runs directly:
  SELECT DBMS_METADATA.GET_DDL('TABLE','ORDERS','APP') FROM DUAL;
  → Succeeds thanks to SELECT_CATALOG_ROLE.

DBA_USER moves logic into an AUTHID DEFINER procedure:
  → Role-based privileges are generally disabled inside the procedure.
  → GET_DDL for schema APP may return object-not-found.

What to consider:
  Invoker's rights AUTHID CURRENT_USER when the security model allows,
  or properly scoped direct grants; never grant the DBA role carelessly.
```

Always review the authentication/authorization model of any package you build. `AUTHID CURRENT_USER` does not automatically authorize reading every user's metadata.

## 13. Common errors and troubleshooting scenarios

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| `ORA-31603: object ... not found in schema ...` | Wrong name/owner/type, wrong PDB, or insufficient metadata privileges | Check `SYS_CONTEXT`, `USER_OBJECTS`/`ALL_OBJECTS`, case-sensitive identifiers, and security model |
| `ORA-31600`/`INVALID_ARGVAL` | Invalid object type, filter, or transform parameter | Verify object types/filter names in `DBMS_METADATA` docs for your release |
| `ORA-31608` or object-not-found on dependent/granted DDL | No matching dependent object/grant exists, or not permitted to see | Check `ALL_TAB_PRIVS`, `ALL_INDEXES`, `ROLE_ROLE_PRIVS`, or matching dictionary views |
| DDL truncated around 4,000 characters | Client LONG/CLOB limit, or `DBMS_LOB.SUBSTR` call | Increase `SET LONG`, fetch full CLOB via client, compare length with `DBMS_LOB.GETLENGTH` |
| Only the table prints without indexes or triggers | Only `GET_DDL('TABLE')` was called | Extract dependent objects or use a structured schema export |
| DDL includes too much `STORAGE`, `TABLESPACE` | Default transform emits physical attributes | Set `STORAGE` or `SEGMENT_ATTRIBUTES` as needed, then reset |
| DDL is missing constraints | Session left `CONSTRAINTS=FALSE` or partial export | Reset transforms; check `CONSTRAINTS`, `REF_CONSTRAINTS`; verify against dictionary |
| Schema remapped, yet package still references old owner | Strings in PL/SQL source/dynamic SQL are not universally rewritten | Review source, dependencies, and hard-coded qualifiers |
| User has direct query access, yet `GET_DDL` for another schema fails | Difference between table `SELECT` privilege and metadata privilege | Check `DBMS_METADATA` security model, `SELECT_CATALOG_ROLE`, current container |
| Works directly, fails inside a procedure | Definer's rights disables roles | Check `AUTHID CURRENT_USER`, direct grants, and privilege rules |
| Export succeeds, yet deployment fails | Missing user/tablespace/grant/dependency, version mismatch, or existing object conflict | Read actual errors, compare target capabilities, execution order, and transforms |

### 13.1. Checking whether DDL is actually longer than displayed

```sql
-- Measure exact CLOB length returned by the function without truncating.
SELECT DBMS_LOB.GETLENGTH(
         DBMS_METADATA.GET_DDL('TABLE', 'ORDERS', 'APP')) AS ddl_chars
FROM   dual;
```

If `DDL_CHARS = 25000` while the saved file holds only a few thousand characters, the **client/export pipeline** truncated the output—not `DBMS_METADATA` omitting metadata. For large package bodies, choose a lossless CLOB persistence method rather than a single `DBMS_OUTPUT.PUT_LINE` (which enforces line length limits).

### 13.2. Be careful with `DBMS_OUTPUT`

`DBMS_OUTPUT.PUT_LINE(DBMS_LOB.SUBSTR(l_ddl, 32767, 1))` looks convenient but is unreliable as a full CLOB exporter:

- A single `SUBSTR` captures only the prefix; longer objects **lose everything after**.
- `PUT_LINE` has a **bytes-per-line** limit sensitive to multi-byte characters and tool versions.
- Arbitrarily inserting newlines across CLOB chunks can corrupt string literals, quoted identifiers, or PL/SQL syntax in scripts.

When exporting programmatically, use a client API that streams the **intact CLOB**, or a file-writing mechanism preserving exact character strings with controlled encoding. Use `DBMS_OUTPUT` only for debugging or printing lengths, not as a lossless SQL generator.

## 14. Controlled hands-on practice in a lab schema

> Table creation steps modify the database and are only for an **authorized lab schema**. Never create, truncate, or drop production objects. If your environment is read-only, skip creation and use objects designated by your DBA.

### 14.1. Create simple schema objects

```sql
-- Connect to the right PDB/lab schema.
CREATE TABLE metadata_lab_orders (
    order_id      NUMBER GENERATED BY DEFAULT AS IDENTITY,
    customer_code VARCHAR2(30 CHAR) NOT NULL,
    amount        NUMBER(12, 2) DEFAULT 0 NOT NULL,
    created_at    TIMESTAMP DEFAULT SYSTIMESTAMP,
    CONSTRAINT pk_metadata_lab_orders PRIMARY KEY (order_id)
);

CREATE INDEX idx_md_orders_customer
  ON metadata_lab_orders(customer_code);

COMMENT ON TABLE metadata_lab_orders IS 'Lab table for DBMS_METADATA';
```

`CREATE` DDL modifies the schema and issues an implicit commit. Run only when authorized; avoid these names if objects with the same names already exist in the schema.

### 14.2. Export table and index DDL

```sql
SET LONG 2000000
SET PAGESIZE 0

EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'DEFAULT');
EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'SQLTERMINATOR', TRUE);

SELECT DBMS_METADATA.GET_DDL('TABLE', 'METADATA_LAB_ORDERS')
FROM   dual;

SELECT DBMS_METADATA.GET_DDL('INDEX', 'IDX_MD_ORDERS_CUSTOMER')
FROM   dual;

EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'DEFAULT');
```

Observe that the table DDL normally includes the PK constraint, while the secondary index is requested separately. Do not assume table DDL always emits every independent index in the schema.

### 14.3. Retrieve comments via dependent metadata

```sql
SELECT DBMS_METADATA.GET_DEPENDENT_DDL(
           'COMMENT', 'METADATA_LAB_ORDERS')
FROM   dual;
```

If no output returns, verify that the object/table comment exists, check privileges, default owner name, and the right PDB. `GET_DEPENDENT_DDL` retrieves only dependent objects of the specified type, not all metadata for the table.

### 14.4. Compare two DDL output styles

```sql
-- Version A: keep physical attributes at defaults.
EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'DEFAULT');
SELECT DBMS_METADATA.GET_DDL('TABLE','METADATA_LAB_ORDERS') FROM dual;

-- Version B: change display only, without running ALTER TABLE in the database.
EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'SEGMENT_ATTRIBUTES', FALSE);
SELECT DBMS_METADATA.GET_DDL('TABLE','METADATA_LAB_ORDERS') FROM dual;

EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'DEFAULT');
```

**Question:** Can two DDL outputs differ even though the underlying table did not change? **Yes.** Transforms only control how metadata is formatted as SQL; they do not execute `ALTER TABLE` on the source object.

### 14.5. Clean up the lab (optional, only when certain of the objects)

```sql
-- Run in the lab schema only after saving any needed results.
DROP TABLE metadata_lab_orders PURGE;
```

`DROP TABLE ... PURGE` deletes the table and related dependent objects with no normal DML rollback path. In exercises, prefer keeping lab objects or letting the schema owner manage cleanup. Never run this drop command if the object was not created by you for the lab.

## 15. Designing a reviewable, reusable export workflow

When using `DBMS_METADATA` in real work, every export should have a **clear manifest**:

| Field | Example |
| --- | --- |
| Source database | `SALES_PDB`, service, and DB version/compatible setting |
| Schema | `APP` |
| Scope | `TABLE`, `INDEX`, `VIEW`, `PACKAGE_SPEC/BODY`, grants, comments, etc. |
| Exporting identity | Account authorized to read metadata |
| Transform profile | `PRETTY=TRUE`, `SQLTERMINATOR=TRUE`, `STORAGE=FALSE` or full-fidelity mode |
| Capture timestamp | UTC timestamp and change window |
| Object inventory | Object list + type + owner + object status |
| File count / checksums | `orders.sql`, `order_api.pks`, `order_api.pkb`, etc. |
| PDB scope | Current container/DBID or matching identifier |
| Review | Complete dependencies, no leaked secrets, no CLOB truncation |
| Intended use | Audit, schema diff, review, or controlled deployment |

A workflow can be organized as:

```text
1. Verify connection and privileges
2. Freeze scope and capture timestamp
3. Gather object inventory from dictionary
4. Choose GET_DDL / GET_DEPENDENT_DDL / GET_GRANTED_DDL
   or OPEN('SCHEMA_EXPORT')
5. Configure appropriate transforms
6. Export full CLOBs and save as UTF-8
7. Verify files/manifest; classify sensitive metadata
8. Review dependencies, normalize intentional differences
9. Compare against Git or target schema
10. Once approved, deploy via a dedicated pipeline
```

Two often-competing goals should be stated explicitly in the manifest:

- **Full-fidelity capture**: prioritizes preserving full definitions, physical clauses, and dependent objects; serves auditing and exact reconstruction.
- **Portable DDL for review/migration**: may strip `STORAGE` or remap tablespaces/owners to ease cross-environment moves; requires accepting intentional diffs and reviewing before applying.

Never diff text files from those two modes and conclude schema drift when transform profiles differ. Conversely, identical column DDL text does not prove **data, grants, indexes, policies, and runtime settings** match.

## 16. Self-check questions

**Question 1.** What data type does `DBMS_METADATA.GET_DDL('TABLE','ORDERS','APP')` return? Does it include all rows in the table?

**Question 2.** A DBA needs a list of `GRANT SELECT ON APP.ORDERS ...`. Should they use `GET_DEPENDENT_DDL` or `GET_GRANTED_DDL`?

**Question 3.** To retrieve all roles granted to user `REPORT_USER`, which function and object type should you choose?

**Question 4.** A 35,000-character package body exported as only 4,000 characters. Which settings or code patterns could cause that?

**Question 5.** What impact does `SEGMENT_ATTRIBUTES=FALSE` have on the table definition in the running database?

**Question 6.** Why is `GET_DDL` for a single table insufficient to guarantee full application recovery?

**Question 7.** A common user holds `SELECT_CATALOG_ROLE`; direct queries for another schema's DDL succeed, yet calling the same logic inside a definer's-rights procedure fails. Explain why.

**Question 8.** A CDB has `APP.ORDERS` in two PDBs. Is knowing only schema and object name enough to export the right one?

**Question 9.** After creating a transform handle with `ADD_TRANSFORM`, is calling `SET_TRANSFORM_PARAM` using the `OPEN` handle valid?

**Question 10.** Does `REMAP_SCHEMA` automatically fix every hard-coded schema name inside PL/SQL dynamic SQL?

<details>
<summary>Answer hints</summary>

1. Returns a **CLOB containing DDL**, not data rows. Data requires a separate export/backup process.
2. `GET_DEPENDENT_DDL('OBJECT_GRANT','ORDERS','APP')` because the question asks for grants **on the table**.
3. `GET_GRANTED_DDL('ROLE_GRANT','REPORT_USER')`.
4. `SET LONG` too small, a client tool previewing only part of the CLOB, or a script calling `DBMS_LOB.SUBSTR` once.
5. Affects only **the exported DDL text**, not the source table. However, a script rebuilt from that text will omit the corresponding physical attributes.
6. Standalone indexes, triggers, comments, grants, views, packages, sequences, data, dependencies, and many other objects are still missing.
7. Roles are normally disabled in definer's-rights PL/SQL; design permissions properly with invoker's rights or direct grants.
8. Not enough: you must verify **the current PDB/service, container, and privileges**.
9. No. Pass the transform handle from `ADD_TRANSFORM`, not the retrieval handle from `OPEN`.
10. Not guaranteed. Review source code, view definitions, and dependencies after remapping.

</details>

## 17. Official Oracle documentation

1. [Oracle Database 19c — `DBMS_METADATA` Package Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_METADATA.html): exact signatures for `GET_DDL`, `GET_DEPENDENT_DDL`, `GET_GRANTED_DDL`, `OPEN`, `SET_FILTER`, `SET_TRANSFORM_PARAM`, `FETCH_CLOB`, security model, object types, and transform parameters.
2. [Oracle Database 19c Utilities — Using the Metadata APIs](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/using-oracle-dbms_metadata-api.html): `OPEN`/`FETCH_CLOB` workflow, object filtering, `MODIFY`/`REMAP_SCHEMA`, and collection exports.
3. [Oracle Database 19c Administrator's Guide — Managing Schema Objects](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-schema-objects.html): official example extracting DDL from `USER_ALL_TABLES`, avoiding nested tables/overflow segments, and resetting session transforms.
4. [Oracle Database 19c Utilities — Oracle Data Pump Export](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-export-utility.html): metadata-only export, schema scope, export modes, and prerequisites for full exports.
5. [Oracle Database 19c Utilities — Oracle Data Pump Import](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-import-utility.html): `SQLFILE`, reviewing DDL from a Data Pump dump without executing object creation statements.
6. [Oracle Database 19c Reference — Data Dictionary](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/about-static-data-dictionary-views.html): `USER_*`, `ALL_*`, `DBA_*`, and `CDB_*` views as sources for object and grant inventories.
7. [Oracle Database 19c Multitenant Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/multi/): current container, PDB services, privileges, and metadata scope when extracting in a CDB.
8. [Oracle AI Database 26ai — `DBMS_METADATA` Package Reference](https://docs.oracle.com/en/database/oracle/oracle-database/26/arpls/DBMS_METADATA.html): reference for object type and transform parameter changes in newer releases; always cross-check against your running environment.

**Practical rule of thumb:** Confirm **container → owner → object type/name → privileges → transforms → full CLOB → dependencies**. `DBMS_METADATA` is a highly useful tool for reading **current definitions**, yet generated scripts must be clearly distinguished from data, migration history, backups, and deployment decisions on target systems.
