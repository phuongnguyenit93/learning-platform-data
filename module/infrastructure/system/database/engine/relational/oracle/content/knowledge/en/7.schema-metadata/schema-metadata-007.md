# Querying PL/SQL Source, Compilation Errors, and INVALID Status in Oracle Database

When working with Oracle Database, you do not just create tables and execute SQL statements. The database also stores numerous **PL/SQL** objects such as procedures, functions, packages, triggers, and type bodies. These objects have **source code**, **compilation status**, **error messages**, and **dependency relationships** with other objects. All of these can be queried through Oracle's **data dictionary**.

A familiar scenario: an application calls a procedure and encounters an error, even though the local source file looks right. The procedure in the database might still contain an older version, might have failed during compilation, or might have become `INVALID` because a dependent table or package changed. To find the root cause, answer in order: *Which database and schema am I connected to? What PL/SQL code is actually stored? Which object is INVALID? Which line does the compiler report an error on? What does the object depend on?*

Objectives after this lesson:

- Identify the schema, container/PDB, and PL/SQL object type to inspect.
- Read source code via `USER_SOURCE`, `ALL_SOURCE`, and when privileged, `DBA_SOURCE`.
- Query compilation errors via `USER_ERRORS`, `ALL_ERRORS`, `DBA_ERRORS`, and the `SHOW ERRORS` command.
- Distinguish `VALID`/`INVALID` status in `USER_OBJECTS` or `ALL_OBJECTS` from **runtime** execution errors.
- Understand the difference between a package specification and a package body during compilation.
- Investigate invalidation caused by dependencies, access privileges, or DDL changes, and perform controlled recompilation.
- Practice creating an invalid procedure, reading errors, fixing code, verifying status, and invoking it successfully.

> These examples use self-created objects in a **practice schema**. Never run `CREATE OR REPLACE` or `ALTER ... COMPILE` on production objects without authorization to change them; modifying a package specification, trigger, or shared object can impact many sessions and applications. The content focuses on modern Oracle Database; some dictionary view columns and privileges vary by version and security policy.

## 1. Placing PL/SQL objects in the schema and metadata picture

A **schema** is the collection of objects belonging to a database user. When you create a regular procedure under account `LAB_USER`, the object is stored in schema `LAB_USER`, unless the statement has privileges and specifies a different owner. PL/SQL objects can be stored and compiled in the database; they differ from anonymous PL/SQL blocks submitted by a client for immediate execution.

| Type | Example | Stored as a named object? | Is source code queryable? |
| --- | --- | --- | --- |
| **Procedure** | `LAB_SEND_EMAIL` | Yes | Typically via `USER_SOURCE` with `TYPE='PROCEDURE'` |
| **Function** | `LAB_TOTAL_PRICE` | Yes | `TYPE='FUNCTION'` |
| **Package specification** | `LAB_ORDER_PKG` API declaration | Yes | `TYPE='PACKAGE'` |
| **Package body** | `LAB_ORDER_PKG` implementation | Yes, as a distinct object type | `TYPE='PACKAGE BODY'` |
| **Trigger** | `LAB_AUDIT_TRG` | Yes | `TYPE='TRIGGER'` |
| **Object type/type body** | `LAB_ADDRESS_TYPE` | Yes | `TYPE='TYPE'` and `TYPE='TYPE BODY'` |
| **Anonymous block** | `DECLARE ... BEGIN ... END;` | Not as a standalone stored schema object | Does not appear as a procedure in `USER_SOURCE` |

Information about a stored object is spread across multiple dictionary views. Do not treat a single view as the sole source for an entire diagnosis.

```text
            Current Oracle Database / PDB
                         │
                        Schema
                         │
              Stored PL/SQL object
                         │
          ┌──────────────┼──────────────┬────────────────┐
          │              │              │                │
          ▼              ▼              ▼                ▼
      *_SOURCE       *_OBJECTS       *_ERRORS       *_DEPENDENCIES
      Line-by-line   VALID/INVALID   Compilation    Dependencies
      source code    status          errors/warnings between objects
```

### 1.1. Three scopes: USER, ALL, and DBA

Many data dictionary view families use three prefixes:

| Prefix | General meaning | When to use |
| --- | --- | --- |
| `USER_*` | Objects belonging to the **connected user's schema** | Start here when you own the procedure/package to fix; no `OWNER` column needed |
| `ALL_*` | Objects the current user can access/see per dictionary privileges | Look up objects in other schemas within permitted scope; usually includes `OWNER` |
| `DBA_*` | Database-wide information within administrative privilege scope | Analyze across multiple schemas; requires appropriate privileges |

For example, `USER_SOURCE` and `USER_ERRORS` suit the account that owns the procedure; to inspect `HR.PAYROLL_PKG` from another user, you may need `ALL_SOURCE`/`ALL_ERRORS` if privileges permit, or ask a DBA. **Never assume having `EXECUTE` on a package automatically lets you view all private/body source code**; visibility depends on privileges, version, and security policies.

Oracle Database Multitenant also has the **CDB/PDB** level. A user with the same name in two PDBs can own completely different objects. Therefore, confirm the session/connection before reading `USER_SOURCE`.

## 2. Confirm the right login session before diagnosing

Run a simple SQL query:

```sql
SELECT USER AS login_user,
       SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
       SYS_CONTEXT('USERENV', 'DB_NAME') AS database_name,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;
```

Meaning:

- `LOGIN_USER`: the logged-in database user.
- `CURRENT_SCHEMA`: the schema used to resolve object names written without an owner; may have been changed via `ALTER SESSION SET CURRENT_SCHEMA`.
- `CONTAINER_NAME`: the current CDB root or PDB.
- `DATABASE_NAME` and `SERVICE_NAME`: help confirm the target database/service.

**Important note:** `CURRENT_SCHEMA` can differ from `USER`. `USER_*` views describe objects belonging to the **current user's** schema and do not automatically switch to another schema just because you set a different `CURRENT_SCHEMA`. To inspect an object owned by another user, specify the explicit schema name and use `ALL_*` views filtered by `OWNER` when permitted.

A practical connection checklist:

```text
Database/service:   ORACLE_LAB / FREEPDB1       (example)
Current PDB:        FREEPDB1
Login user:         LAB_USER
Current schema:     LAB_USER
Object owner:       LAB_USER
Object name:        LAB_COMPILE_DEMO
Object type:        PROCEDURE
```

Never use the example names to guess the names of a real database.

## 3. Querying PL/SQL source code in USER_SOURCE

`USER_SOURCE` stores source code for PL/SQL objects in the current schema, typically **line by line**. Core columns:

| Column | Meaning |
| --- | --- |
| `NAME` | Stored object name |
| `TYPE` | Source type: `PROCEDURE`, `FUNCTION`, `PACKAGE`, `PACKAGE BODY`, `TRIGGER`, `TYPE`, `TYPE BODY`, etc. |
| `LINE` | Line number within the object's source code |
| `TEXT` | Text of the stored source line |

Example reading a procedure:

```sql
SELECT line, text
FROM user_source
WHERE name = 'LAB_COMPILE_DEMO'
  AND type = 'PROCEDURE'
ORDER BY line;
```

**You must include `ORDER BY LINE`** to reconstruct exact order; SQL query results without `ORDER BY` are not guaranteed to follow storage order. Object names created without double quotes are stored/queried by Oracle in uppercase, hence `'LAB_COMPILE_DEMO'`. Objects created with double quotes for case-sensitive names must match exact casing.

### 3.1. Reading package specifications and package bodies

A package has two source parts with distinct roles:

- **Specification (`TYPE='PACKAGE'`):** declares public procedures, functions, types, constants, cursors, and the caller API.
- **Body (`TYPE='PACKAGE BODY'`):** defines the implementation and may contain private elements.

Read both parts separately:

```sql
SELECT type, line, text
FROM user_source
WHERE name = 'LAB_ORDER_PKG'
  AND type IN ('PACKAGE', 'PACKAGE BODY')
ORDER BY CASE type WHEN 'PACKAGE' THEN 1 ELSE 2 END, line;
```

Do not filter only by `NAME` and interleave lines regardless of `TYPE`: line 1 of the specification and line 1 of the body are **two separate line counters**. Also do not treat the package specification's status as representing the body's compilation state.

### 3.2. Reading source in another schema when permitted

`ALL_SOURCE` adds `OWNER`:

```sql
SELECT owner, name, type, line, text
FROM all_source
WHERE owner = 'APP_OWNER'
  AND name = 'PAYMENT_PKG'
  AND type = 'PACKAGE'
ORDER BY line;
```

With appropriate administrative privileges, `DBA_SOURCE` supports database-wide analysis within the relevant container scope:

```sql
SELECT owner, name, type, line, text
FROM dba_source
WHERE owner = 'APP_OWNER'
  AND name = 'PAYMENT_PKG'
  AND type = 'PACKAGE BODY'
ORDER BY line;
```

Both examples are illustrative queries. Do not assume privilege to view another schema's package body if the database returns a privilege error or zero rows.

### 3.3. Why can queried source code differ from the file in Git?

Common reasons:

1. Connected to the wrong PDB or a different environment's database.
2. Object owner differs from the schema you are querying.
3. The file in Git was edited but **not yet deployed** to the database, or the database received a different deployment.
4. A `CREATE OR REPLACE` script ran from a client with unexpected `/` delimiter handling.
5. The object was **wrapped** (obfuscated using PL/SQL wrapping); the dictionary stores the wrapped representation, not the original plaintext source.
6. The object is an anonymous block, dynamic SQL, or runtime-generated code, so it does not exist as a named procedure in `USER_SOURCE`.

`USER_SOURCE` reflects the stored object code Oracle holds in the current schema/PDB, while Git reflects the repository's source. When comparing, check deployment version, owner, object name, and source type. `USER_SOURCE` is not a tool for recovering plaintext from wrapped PL/SQL.

## 4. Checking VALID and INVALID status

`USER_OBJECTS` (or `ALL_OBJECTS` with an `OWNER` column) provides schema object metadata: name, type, status, and DDL timestamps.

List PL/SQL objects of interest:

```sql
SELECT object_name,
       object_type,
       status,
       created,
       last_ddl_time
FROM user_objects
WHERE object_type IN (
    'PROCEDURE', 'FUNCTION',
    'PACKAGE', 'PACKAGE BODY',
    'TRIGGER', 'TYPE', 'TYPE BODY'
)
ORDER BY object_type, object_name;
```

Filter only `INVALID` objects:

```sql
SELECT object_name,
       object_type,
       status,
       last_ddl_time
FROM user_objects
WHERE status = 'INVALID'
ORDER BY object_type, object_name;
```

Inspect a specific object:

```sql
SELECT object_name, object_type, status, last_ddl_time
FROM user_objects
WHERE object_name = 'LAB_COMPILE_DEMO';
```

### 4.1. What does VALID actually mean?

For stored PL/SQL, **`VALID`** typically means Oracle considers the object valid in terms of compilation and dependency status at the time of inspection. It **does not prove** the procedure will execute successfully for every parameter or runtime condition.

For example, a `VALID` procedure can still hit:

- `NO_DATA_FOUND` or `TOO_MANY_ROWS` from `SELECT ... INTO`.
- Constraint errors, deadlocks, connection drops, or tablespace-full errors during execution.
- Runtime privilege, data, or object errors in applicable scenarios, especially with dynamic SQL.
- Business logic exceptions or errors raised by another procedure.

**`VALID` is an object-state indicator**, not a guarantee that all business logic is bug-free.

### 4.2. What does INVALID actually mean?

**`INVALID`** indicates Oracle must recompile/revalidate the object before normal use, or that a previous compilation failed. Common causes:

- Syntax or declaration errors in PL/SQL.
- References to tables, columns, packages, or functions that do not exist, were renamed, or are inaccessible.
- DDL changes on a dependent object that invalidated the current object.
- Changes to a package specification causing dependent objects to require revalidation/recompilation.
- Privileges required for compilation were revoked or granted in an incompatible form.

An object marked `INVALID` due to **dependency invalidation** may **have no new compilation error rows in `USER_ERRORS` yet**. Oracle attempts automatic recompilation when the object is used; if the cause is gone and compilation succeeds, the object returns to `VALID`. If errors remain, the call fails.

Do not treat `INVALID` as an instruction to immediately run `ALTER ... COMPILE` in every environment: first identify the root cause and impact on the application.

### 4.3. What is LAST_DDL_TIME?

`LAST_DDL_TIME` is the timestamp of DDL operations related to the object, which can update on compiles, create/alter statements, and certain other DDL activities. It is **not the last time the procedure was executed**, nor a hash of source content. To track business changes to source code, compare deployments/versions or use controlled source diffs.

## 5. Querying compilation errors in USER_ERRORS

When `CREATE OR REPLACE PROCEDURE`, `FUNCTION`, `PACKAGE BODY`, or another PL/SQL object fails compilation, Oracle may create/save the object without compiling it successfully. SQL*Plus typically prints a message like *Procedure created with compilation errors*. To see the exact errors, inspect the diagnostics.

`USER_ERRORS` holds **ERROR/WARNING** messages stored by Oracle for objects in the current schema.

| Column | Role |
| --- | --- |
| `NAME` | Object name |
| `TYPE` | Object type, e.g., `PROCEDURE` or `PACKAGE BODY` |
| `SEQUENCE` | Sequence order of diagnostic messages |
| `LINE` | Line in the source unit where the error is reported |
| `POSITION` | Column position within the line where the error is reported |
| `TEXT` | Diagnostic message text |
| `ATTRIBUTE` | Diagnostic type, typically `ERROR` or `WARNING` |

Example:

```sql
SELECT name,
       type,
       sequence,
       line,
       position,
       attribute,
       text
FROM user_errors
WHERE name = 'LAB_COMPILE_DEMO'
ORDER BY type, sequence;
```

To show only errors:

```sql
SELECT line, position, text
FROM user_errors
WHERE name = 'LAB_COMPILE_DEMO'
  AND type = 'PROCEDURE'
  AND attribute = 'ERROR'
ORDER BY sequence;
```

**Note:** `WARNING` rows can appear when PL/SQL compiler warnings are enabled even while the object remains `VALID`. Not every row in `USER_ERRORS` means the object cannot run. Conversely, an object marked `INVALID` due to a changed dependency may have no diagnostic rows until Oracle attempts recompilation.

### 5.1. Joining errors with source lines

Often you want to immediately see the source line containing each error:

```sql
SELECT e.type,
       e.sequence,
       e.line,
       e.position,
       e.attribute,
       e.text AS error_text,
       s.text AS source_line
FROM user_errors e
LEFT JOIN user_source s
       ON s.name = e.name
      AND s.type = e.type
      AND s.line = e.line
WHERE e.name = 'LAB_COMPILE_DEMO'
  AND e.type = 'PROCEDURE'
ORDER BY e.sequence;
```

`USER_ERRORS.LINE` and `USER_SOURCE.LINE` match within the **same unit and `TYPE`**. Line numbers in a local `.sql` file can differ from source unit line numbers stored in Oracle, because client scripts also include `SET` commands, comments before `CREATE`, other SQL statements, and the trailing slash. The `/` is a SQL*Plus/SQLcl script execution command, **not a line of PL/SQL source**.

An initial declaration error can cascade into several secondary errors. Read from the lowest `SEQUENCE` first, resolve the root error, recompile, and check fresh diagnostics.

### 5.2. Querying errors in another schema

With appropriate privileges:

```sql
SELECT owner, name, type, line, position, attribute, text
FROM all_errors
WHERE owner = 'APP_OWNER'
  AND name = 'PAYMENT_PKG'
ORDER BY type, sequence;
```

`DBA_ERRORS` can be used by administrators with read privileges. Cross-schema lookups must specify the **exact owner**; never filter solely by `NAME` when multiple schemas have objects with identical names.

## 6. SHOW ERRORS in SQL*Plus, SQLcl, and SQL Developer

In SQL*Plus/SQLcl, right after running `CREATE OR REPLACE`, you can inspect errors for the most recent object with:

```sql
SHOW ERRORS
```

Or specify the type and name explicitly:

```sql
SHOW ERRORS PROCEDURE LAB_COMPILE_DEMO
SHOW ERRORS FUNCTION LAB_TOTAL_PRICE
SHOW ERRORS PACKAGE LAB_ORDER_PKG
SHOW ERRORS PACKAGE BODY LAB_ORDER_PKG
SHOW ERRORS TRIGGER LAB_AUDIT_TRG
```

In SQL Developer, **Run Script (F5)** generally supports script commands like `SHOW ERRORS`; **Run Statement (Ctrl+Enter)** handles things differently. You can also open the object and view its diagnostics/errors tab depending on version. Querying `USER_ERRORS` with `SELECT` is the standard SQL client-independent method when a tool does not support `SHOW ERRORS`.

Some tools offer a **Compile/Recompile** button in the UI. Identify the right object type: specifically, an error in a **package body** does not require recompiling or altering the package specification.

## 7. Full hands-on lab: create an INVALID procedure and fix it

Practice in a dedicated schema such as `LAB_USER` in the right PDB. You need `CREATE PROCEDURE` in the schema and privilege to execute `DBMS_OUTPUT` to see output (practice environments usually include these). If `LAB_COMPILE_DEMO` already exists and must be preserved, choose a new object name so `CREATE OR REPLACE` does not overwrite another exercise's code.

### Step 1 — Intentionally create a compilation error

In SQL*Plus/SQLcl or SQL Developer in Run Script mode, run:

```sql
CREATE OR REPLACE PROCEDURE lab_compile_demo AS
    v_result NUMBER;
BEGIN
    v_result := missing_value + 1;
    DBMS_OUTPUT.PUT_LINE('Result = ' || v_result);
END;
/
```

The variable `missing_value` is **undeclared** inside the procedure; therefore the compiler will raise an error like `PLS-00201: identifier ... must be declared` or related diagnostics. The `/` on its own line tells SQL*Plus-style clients to send the entire `CREATE OR REPLACE` command for execution; it is not part of the procedure's PL/SQL code.

Note that Oracle may return a message stating **the procedure was created with compilation errors**. That means the object name exists in the dictionary, not that it can be invoked successfully.

### Step 2 — Confirm the object is INVALID

```sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name = 'LAB_COMPILE_DEMO';
```

Expected result during the error step:

```text
OBJECT_NAME          OBJECT_TYPE    STATUS
-------------------  -------------  -------
LAB_COMPILE_DEMO     PROCEDURE      INVALID
```

### Step 3 — Read the error and actual database source

```sql
SHOW ERRORS PROCEDURE LAB_COMPILE_DEMO
```

And:

```sql
SELECT sequence, line, position, attribute, text
FROM user_errors
WHERE name = 'LAB_COMPILE_DEMO'
  AND type = 'PROCEDURE'
ORDER BY sequence;

SELECT line, text
FROM user_source
WHERE name = 'LAB_COMPILE_DEMO'
  AND type = 'PROCEDURE'
ORDER BY line;
```

Match line/position to locate the line referencing `missing_value`. If multiple error rows appear, address the undeclared-identifier message first. Exact line numbers and diagnostic order can vary with source formatting and Oracle version.

### Step 4 — Fix the code to compile cleanly

Replace the procedure with a version declaring and initializing the variable properly:

```sql
CREATE OR REPLACE PROCEDURE lab_compile_demo AS
    v_value  NUMBER := 41;
    v_result NUMBER;
BEGIN
    v_result := v_value + 1;
    DBMS_OUTPUT.PUT_LINE('Result = ' || v_result);
END;
/
```

Verify again:

```sql
SHOW ERRORS PROCEDURE LAB_COMPILE_DEMO

SELECT object_name, object_type, status
FROM user_objects
WHERE object_name = 'LAB_COMPILE_DEMO';

SELECT line, position, attribute, text
FROM user_errors
WHERE name = 'LAB_COMPILE_DEMO'
ORDER BY sequence;
```

The object should transition to `VALID` with no `ERROR` diagnostics left from the earlier failed compile. Having zero rows in `USER_ERRORS` after a clean compile is normal when warnings are disabled or none were emitted.

### Step 5 — Invoke the procedure after compilation

In SQL*Plus/SQLcl:

```sql
SET SERVEROUTPUT ON

BEGIN
    lab_compile_demo;
END;
/
```

Sample output:

```text
Result = 42
```

In GUI tools supporting `DBMS_OUTPUT`, you may need to open or enable the corresponding output panel. `SET SERVEROUTPUT ON` is a client command for displaying `DBMS_OUTPUT`, not procedure syntax.

### Step 6 — Recompile without changing source

To ask Oracle to recompile an **existing procedure**:

```sql
ALTER PROCEDURE lab_compile_demo COMPILE;

SELECT object_name, object_type, status
FROM user_objects
WHERE object_name = 'LAB_COMPILE_DEMO';

SELECT line, position, text
FROM user_errors
WHERE name = 'LAB_COMPILE_DEMO'
ORDER BY sequence;
```

`ALTER ... COMPILE` does not fix source code by itself: it asks Oracle to recompile the stored object as-is. If the underlying error remains, the object stays `INVALID`. For an undeclared identifier like `missing_value`, you must fix the code with `CREATE OR REPLACE`; running `ALTER ... COMPILE` repeatedly will never make an undeclared name valid.

> When re-running the lab, `CREATE OR REPLACE` overwrites any procedure with the same name in the current schema. Only run it in your lab schema after confirming the object is not needed by another exercise.

## 8. PACKAGE and PACKAGE BODY: two independent compilation states

A package is split into a **specification** and a **body**. A package can have a `VALID` specification while its body is `INVALID`; in that case the API remains declared, yet calling routines implemented in the body will fail.

Simple package example:

```sql
CREATE OR REPLACE PACKAGE lab_math_pkg AS
    FUNCTION double_value(p_value NUMBER) RETURN NUMBER;
END lab_math_pkg;
/

CREATE OR REPLACE PACKAGE BODY lab_math_pkg AS
    FUNCTION double_value(p_value NUMBER) RETURN NUMBER IS
    BEGIN
        RETURN p_value * 2;
    END double_value;
END lab_math_pkg;
/
```

Query both objects:

```sql
SELECT object_name, object_type, status, last_ddl_time
FROM user_objects
WHERE object_name = 'LAB_MATH_PKG'
ORDER BY object_type;
```

Output may show two rows:

```text
LAB_MATH_PKG   PACKAGE        VALID
LAB_MATH_PKG   PACKAGE BODY   VALID
```

If the body misspells a variable or calls a nonexistent routine, errors appear under `TYPE='PACKAGE BODY'`:

```sql
SELECT type, line, position, attribute, text
FROM user_errors
WHERE name = 'LAB_MATH_PKG'
ORDER BY type, sequence;
```

Corresponding compile commands:

```sql
ALTER PACKAGE lab_math_pkg COMPILE PACKAGE;
ALTER PACKAGE lab_math_pkg COMPILE BODY;
```

**Distinguish impact:** Compiling the specification can trigger invalidation/revalidation across dependent objects under Oracle rules; if only the body has errors, focus on fixing the body and use `COMPILE BODY` to avoid unnecessary disruption to the public specification. Changing public APIs in the specification affects callers far more widely than changing private implementation inside the body.

When inspecting source, always specify the right `TYPE`:

```sql
SELECT line, text
FROM user_source
WHERE name = 'LAB_MATH_PKG'
  AND type = 'PACKAGE BODY'
ORDER BY line;
```

**Common mistake:** running only `SHOW ERRORS PACKAGE LAB_MATH_PKG` when the bug is in `PACKAGE BODY`, and concluding "there are no errors." Always check the exact object type.

## 9. How compilation errors differ from runtime errors

These two classes of failures follow different investigation paths.

| Scenario | Examples | Where to inspect |
| --- | --- | --- |
| **Stored PL/SQL parse/compile error** | `PLS-00201`: undeclared variable or identifier | `USER_ERRORS`, `USER_SOURCE`, `SHOW ERRORS` |
| **Static SQL error inside stored PL/SQL** | `ORA-00904`: wrong column name; `PL/SQL: SQL Statement ignored` | `USER_ERRORS` and dependent tables/columns/privileges |
| **Object/privilege resolution error during compile** | `PLS-00201`, `ORA-00942` when object is inaccessible | `USER_ERRORS`, dependencies, direct grants |
| **Error when running a VALID object** | `NO_DATA_FOUND`, `TOO_MANY_ROWS`, `ZERO_DIVIDE` | Call stack, data conditions, exception handlers |
| **Error when calling an invalid object** | `ORA-04063`, `ORA-06508`, `ORA-04098` depending on object and call path | `USER_OBJECTS`, `USER_ERRORS`, dependencies, alert/application logs |
| **Anonymous block error** | `ORA-06550` and `PLS-...` messages when running `BEGIN ... END;` | Client output and the anonymous block itself; do not expect a new stored object in `USER_ERRORS` |

### 9.1. Example of a VALID object that still fails at runtime

```sql
CREATE OR REPLACE PROCEDURE lab_runtime_demo AS
    v_num NUMBER;
BEGIN
    SELECT 1 / 0 INTO v_num
    FROM dual;
END;
/
```

This procedure is syntactically valid in principle, yet running it raises a mathematical error such as `ORA-01476: divisor is equal to zero`. Therefore `VALID` status does not guarantee runtime business success. Do not look in `USER_ERRORS` for exceptions that only occur during execution.

### 9.2. Example of a wrong column in static SQL

Suppose a table has columns `ORDER_ID` and `AMOUNT`, while a procedure contains:

```sql
SELECT amount_missing
INTO v_amount
FROM lab_orders
WHERE order_id = p_order_id;
```

If `LAB_ORDERS` exists and the compiler has access, `AMOUNT_MISSING` can trigger `ORA-00904: invalid identifier` during procedure compilation. Editing only the procedure is not enough if the root issue is that the table schema changed or the SQL targets a different schema version.

## 10. Investigating INVALID status caused by dependencies

A procedure can be `VALID` yesterday and `INVALID` today even though nobody edited its source directly. The usual reason is that a **referenced dependency** changed.

Example:

```text
TABLE LAB_ORDERS
       │ column referenced by procedure
       ▼
PACKAGE BODY LAB_ORDER_PKG
       │ function called by another function
       ▼
FUNCTION LAB_REPORT_TOTAL
```

DDL changes on a table or package specification can require dependent objects to be revalidated or recompiled. Modern Oracle versions implement **fine-grained dependency management**: not every DDL change invalidates every dependent object. Always **verify actual status** after changes.

### 10.1. Querying dependency relationships

`USER_DEPENDENCIES` includes columns such as `NAME`, `TYPE`, `REFERENCED_OWNER`, `REFERENCED_NAME`, and `REFERENCED_TYPE`:

```sql
SELECT name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type
FROM user_dependencies
WHERE name = 'LAB_ORDER_PKG'
ORDER BY type, referenced_owner, referenced_name;
```

To find objects **depending on** a specific table or package within visible scope:

```sql
SELECT owner,
       name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type
FROM all_dependencies
WHERE referenced_owner = 'LAB_USER'
  AND referenced_name = 'LAB_ORDERS'
ORDER BY owner, name, type;
```

These views reflect dependencies tracked by Oracle; **dynamic SQL** assembling object names at runtime does not necessarily record static dependencies the way direct SQL references do. Real systems must also consider application code, synonyms, and dynamic calls.

To check the status of objects returned by dependency views, query `ALL_OBJECTS` with the appropriate owner/type:

```sql
SELECT owner, object_name, object_type, status
FROM all_objects
WHERE owner = 'LAB_USER'
  AND object_name IN ('LAB_ORDERS', 'LAB_ORDER_PKG');
```

### 10.2. Automatic vs. manual recompilation

Oracle can **attempt to recompile an INVALID object automatically when it is referenced or invoked**, provided required conditions are restored. That does not guarantee every call succeeds: if a referenced column was dropped or privileges remain missing, compilation still fails.

When explicit compilation is needed:

```sql
ALTER PROCEDURE lab_compile_demo COMPILE;
ALTER FUNCTION lab_total_price COMPILE;
ALTER PACKAGE lab_math_pkg COMPILE BODY;
ALTER TRIGGER lab_audit_trg COMPILE;
```

These commands are **syntax templates by object type**; run them only when the specific object exists and you hold privileges, never as a blind script to "fix all errors."

A sensible workflow:

1. Identify the `INVALID` object and which dependency changed.
2. Read `USER_ERRORS`, `USER_SOURCE`/`ALL_SOURCE`, and check schema/privilege metadata.
3. Fix the root cause: PL/SQL source, column/table names, package API, access privileges, or deployment error.
4. Recompile the affected object using its exact object type.
5. Re-check `STATUS` and `*_ERRORS`; test invocation in an appropriate test environment.
6. Check dependent objects and applications using this API.

**Do not use bulk recompilation as a default fix.** Schema-wide compile utilities or parallel recompilers consume CPU, affect dependencies, and require high privileges. In production, weigh maintenance windows, blast radius, and rollback plans.

### 10.3. Role-based privileges vs. direct privileges

A subtle issue arises when a user can `SELECT` a table in a SQL session, yet a **definer's-rights** stored PL/SQL unit fails to compile because the privilege comes only from a **role**.

For example, a user holds a role allowing reads on `OTHER_SCHEMA.ORDERS`. Ad hoc queries work, but when a definer's-rights procedure references that table in static SQL, the required privilege typically must be **granted directly to the procedure owner**. By default, roles are not used to authorize named definer's-rights PL/SQL privileges the same way they are in interactive SQL sessions.

With `AUTHID CURRENT_USER` (invoker's-rights), privilege evaluation and authentication context follow additional rules; avoid over-generalizing a single rule across every routine type and Oracle version.

When hitting `PLS-00201` or `ORA-00942` in a stored procedure, check:

- Does the object exist in the right PDB/schema?
- Is the name exact, including any quoted identifiers?
- Does the procedure use definer's-rights or invoker's-rights?
- Does the owner have the direct grants needed to compile?
- Do synonyms point to the right object, and are grants still active?

**Never grant `DBA` or broad privileges just to clear INVALID objects.** Grant the exact object privilege and verify against system security policies.

## 11. Common issues when inspecting metadata

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| `USER_SOURCE` returns no rows | Wrong schema/PDB, wrong name or type, object not created, or not stored PL/SQL | Check `USER`, `CURRENT_SCHEMA`, `CON_NAME`, `USER_OBJECTS` |
| `ALL_SOURCE` cannot see body | Missing visibility privileges, wrong owner/type, or protected object | Verify privileges, owner, policy, and object status |
| `USER_ERRORS` is empty yet status is `INVALID` | Object invalidated by dependency and not yet recompiled, or error is in another object | Check dependencies, root object state; compile under control |
| `USER_ERRORS` has rows yet status is `VALID` | Only warnings exist, not errors | Check `ATTRIBUTE`, `TYPE`, and current status |
| `SHOW ERRORS` reports no errors yet package still fails | Checking `PACKAGE` instead of `PACKAGE BODY`, or a runtime error | Check `USER_OBJECTS`/`USER_ERRORS` with the exact type |
| Source file edited yet old error persists | Not deployed to right database/PDB, script did not run, or wrong object owner | Read `USER_SOURCE` in the database, verify connection |
| Compiles cleanly yet fails when called | Runtime/data/privilege/dynamic SQL error; dependent call failed | Inspect runtime stack trace and dependency statuses |
| Recompile leaves object `INVALID` | Root cause still present | Read latest `USER_ERRORS`, fix source/dependencies/grants |
| Status changed after DDL despite no PL/SQL edits | Oracle invalidated a dependency | Check `USER_DEPENDENCIES` and changes to referenced objects |
| Error line does not match `.sql` file line | File contains client commands, comments, `/` before/after unit | Compare with `USER_SOURCE.LINE` in the exact `TYPE` |
| Cannot find the object just called | Invoked via synonym, different owner, or different edition/PDB | Trace synonym/owner/edition and metadata privileges |

### 11.1. Key error codes to recognize

| Error | Common meaning |
| --- | --- |
| `PLS-00103` | Compiler encountered an unexpected token or syntax |
| `PLS-00201` | Identifier is undeclared or cannot be resolved/accessed |
| `PLS-00302` | Component of package/object is not declared or unavailable |
| `PLS-00306` | Wrong number or types of arguments in call to procedure/function |
| `ORA-00904` | Invalid SQL identifier or column name |
| `ORA-00942` | Table/view does not exist or is inaccessible in the required context |
| `ORA-04063` | Stored object (e.g., package body or view) has errors |
| `ORA-06508` | Could not find or execute the called program unit |
| `ORA-04098` | Trigger is invalid and failed re-validation |
| `ORA-06550` | PL/SQL compilation/parse error reported at a position inside a block |

Real error messages often include multiple error codes in one stack. Read **the full text, object type, line/position, and preceding cause** before concluding.

## 12. Checking object status in large environments

In multi-schema systems, counting INVALID objects is only a starting point, not a diagnosis:

```sql
SELECT owner, object_type, COUNT(*) AS invalid_count
FROM all_objects
WHERE status = 'INVALID'
GROUP BY owner, object_type
ORDER BY invalid_count DESC, owner, object_type;
```

`ALL_OBJECTS` reflects current privilege scope. A DBA needing an aggregate across the database/container can use `DBA_OBJECTS`, and in a CDB must consider container scope/`CDB_*` when managing multiple PDBs. Never merge PDBs solely by `OWNER` and `OBJECT_NAME`, since the same names can appear in multiple PDBs.

An incident record should capture:

| Field | Why it matters |
| --- | --- |
| Database/PDB/edition and timestamp | Pinpoints exactly where the error occurred |
| Owner, object name, object type | Distinguishes package spec/body or homonymous objects |
| `STATUS` before/after | Shows whether recompiling restored the object |
| Source version/deployment ID | Cross-references with Git and deployment pipelines |
| Diagnostic line/position/text | Pinpoints the compiler error |
| Recently changed referenced object | Identifies the cause of invalidation |
| Affected users/programs | Assesses priority and deployment window |

### 12.1. When should you avoid fixing immediately on your own?

- Production object shared by multiple services.
- Package specification requiring a public API signature change.
- Trigger participating in business DML or auditing.
- `INVALID` status appearing mid-migration or after a security privilege change.
- System/Oracle-maintained schema objects handled by DBAs through dedicated procedures.

In these cases, prioritize **reading metadata and reporting the cause with evidence**. Production source edits or recompiles should follow deployment governance, dependency impact review, and rollback procedures.

## 13. Applied exercises

### Exercise 1 — Find the actual source of a function

Suppose the current schema contains function `CALC_DISCOUNT`. Write a `SELECT` retrieving `NAME`, `TYPE`, `LINE`, `TEXT` from `USER_SOURCE`, filtering `TYPE='FUNCTION'` and sorting ascending by `LINE`. Then identify which variables are declared in the header section and what operations occur inside `BEGIN ... END`.

### Exercise 2 — Why does a VALID function fail in the application?

A function looks up a price via `SELECT price INTO v_price FROM products WHERE id = p_id`. `USER_OBJECTS` reports `VALID`, yet calling it with a nonexistent product ID raises `NO_DATA_FOUND`. Explain why `USER_ERRORS` does not necessarily have any rows and why investigation should focus on data and exception handling.

### Exercise 3 — Package spec VALID, body INVALID

Suppose `USER_OBJECTS` returns:

```text
OBJECT_NAME      OBJECT_TYPE     STATUS
---------------  --------------  -------
PAYMENT_PKG      PACKAGE         VALID
PAYMENT_PKG      PACKAGE BODY    INVALID
```

Write a `USER_ERRORS` query filtering `NAME='PAYMENT_PKG'` and `TYPE='PACKAGE BODY'`; then choose the right command `SHOW ERRORS PACKAGE BODY PAYMENT_PKG`. Explain why compiling the specification first does not necessarily fix errors in the body.

### Exercise 4 — INVALID after a table change

A package body uses the `ORDER_TOTAL` column of `ORDERS`. After a migration, that column is renamed. What checks should you perform before running a recompile? List at least four points: status, source, errors, dependencies, and deployed schema version. Explain why `ALTER PACKAGE ... COMPILE BODY` does not automatically update old column names in source code.

### Exercise 5 — Distinguish warnings from errors

An object has a row with `USER_ERRORS.ATTRIBUTE='WARNING'` yet `USER_OBJECTS.STATUS='VALID'`. Is this a contradiction? Explain what PL/SQL compiler warnings mean and why you must filter on `ATTRIBUTE` when counting objects that genuinely failed compilation.

## 14. Concise lookup workflow to apply

```text
1. Confirm database / PDB / USER / CURRENT_SCHEMA
                         │
                         ▼
2. Identify owner + object name + object type
                         │
                         ▼
3. USER_OBJECTS / ALL_OBJECTS → VALID or INVALID?
                         │
                         ▼
4. USER_SOURCE / ALL_SOURCE → what source is stored?
                         │
                         ▼
5. USER_ERRORS / ALL_ERRORS → error or warning? which line?
                         │
                         ▼
6. *_DEPENDENCIES + grants → what changed or lacks privileges?
                         │
                         ▼
7. Fix root cause / compile exact object type
                         │
                         ▼
8. Re-check STATUS + ERRORS, test call in suitable environment
```

In Oracle, **`USER_SOURCE` answers "what code is stored in the database", `USER_ERRORS` answers "what is the compiler reporting", `USER_OBJECTS` answers "is the object marked VALID or INVALID", and `USER_DEPENDENCIES` indicates "which objects may impact it"**. Combining these four perspectives with schema/PDB context and privileges lets you systematically separate deployment errors, compilation errors, invalidation, and runtime errors.
