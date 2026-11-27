# Object Dependencies and the Invalidation Mechanism

In Oracle Database, schema objects rarely operate in isolation. A **view** reads a table; a **procedure** queries a view; a **package** calls a function in another package; a **trigger** is attached to a table. When the structure or definition of a referenced object changes, Oracle must decide whether dependent objects remain usable or require **invalidation** (marking them no longer valid) and **recompilation**.

This is a critical mechanism when developing Oracle systems: a single DDL statement affecting a table can impact the entire data API layer above it, even if developers did not directly touch the views or procedures. Conversely, Oracle uses fine-grained dependency tracking to avoid unnecessary invalidation when a change does not affect the referenced components.

This lesson focuses on four questions:

1. How does Oracle record **who depends on whom**?
2. Which changes can cause an object to become **INVALID**?
3. What happens when a session invokes an invalidated object?
4. How do you use the **data dictionary** to inspect and manage the impact of schema changes?

## 1. Schema objects form a dependency graph

Suppose there is a customer table, a view selecting active customers, and a procedure counting customers:

~~~text
P_DEM_KH_ACTIVE (PROCEDURE)
        |
        | queries
        v
V_KH_ACTIVE (VIEW)
        |
        | reads data
        v
KHACH_HANG_DEP (TABLE)
~~~

This is a dependency graph directed from **dependent object → referenced object**:

- **Dependent object**: an object that relies on the definition or attributes of another object to function, such as the procedure relying on the view.
- **Referenced object**: the object being depended upon, such as the view queried by the procedure.
- **Direct dependency**: the procedure directly references the view.
- **Indirect/transitive dependency**: the procedure indirectly depends on the table through the view.

In this example, renaming a column used by the view can invalidate the view; the procedure above it may also be affected when Oracle re-evaluates executability. When assessing the impact of a change, inspect **the entire downstream branch**, not only the object being edited.

### 1.1. Common dependency relationships

| Dependent object | Referenced object | Why does the dependency arise? |
| --- | --- | --- |
| View | Table/other view | Needs columns, data types, and object names in its `SELECT` |
| Procedure/function | Table, view, package, function, etc. | Static SQL or object calls inside PL/SQL code |
| Package body | Package specification, tables/views, other program units | The body implements the interface and uses other objects |
| Cross-schema procedure | Granted public interface of a package | Depends on called signatures/components and appropriate privileges |
| Trigger | Owning table and objects referenced by trigger code | Fires on events, using columns/objects |
| Materialized view | Source tables/views and related metadata | Materialized view data definition depends on sources |
| Shared SQL cursor | Tables/views and metadata used to parse/execute SQL | Must re-check when definitions or optimization info change |

Not every dependency shares the same invalidation mechanism or metadata status. Specifically, **SQL cursors in the library cache** and **stored objects such as views/procedures/packages** are two separate scopes: a change can force a cursor to reparse without making a stored procedure `INVALID`.

### 1.2. Static vs. dynamic dependencies

Oracle records dependencies from **static SQL statements** and object references analyzed when creating or compiling views or PL/SQL:

~~~sql
CREATE OR REPLACE PROCEDURE p_dem_kh_active AS
    v_dem NUMBER;
BEGIN
    SELECT COUNT(*)
    INTO v_dem
    FROM v_kh_active;

    DBMS_OUTPUT.PUT_LINE('Customer count: ' || v_dem);
END;
/
~~~

Here, the procedure code has a static reference to **V_KH_ACTIVE**, so Oracle stores the relationship in the data dictionary.

With **dynamic SQL**:

~~~sql
EXECUTE IMMEDIATE
    'DELETE FROM bang_tam_thuc_hanh WHERE ngay_tao < :1'
    USING DATE '2024-01-01';
~~~

The table name sits inside a string parsed **at runtime**, so never assume Oracle lists every dynamically accessed object in compile-time dependency metadata. Tables selected from configuration, dynamically concatenated object names, remote objects over database links, or logic in Java services all require dedicated impact analysis methods.

**USER_DEPENDENCIES is not an exhaustive inventory of every possible data access path in a system.**

## 2. Where does the data dictionary store dependency information?

Oracle provides metadata views scoped by access privileges:

| View | Information scope | Purpose |
| --- | --- | --- |
| **USER_DEPENDENCIES** | Dependencies of objects owned by the current user | Find objects in your schema referencing other objects |
| **ALL_DEPENDENCIES** | Dependency info for objects the user is permitted to see | Inspect within granted access scope |
| **DBA_DEPENDENCIES** | Database-wide dependencies, requiring appropriate privileges | Global analysis, especially when multiple schemas depend on one another |
| **USER_OBJECTS** | Objects in the current schema, including OBJECT_TYPE and STATUS | Check VALID/INVALID status |
| **USER_ERRORS** | Compilation errors for views/PL/SQL and matching objects in the schema | Find errors after failed compilation |
| **ALL_OBJECTS**, **DBA_OBJECTS** | Object metadata within access scope | Inspect status of objects outside the current schema |

### 2.1. Viewing direct relationships

~~~sql
SELECT name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type,
       dependency_type
FROM user_dependencies
WHERE name IN ('P_DEM_KH_ACTIVE', 'V_KH_ACTIVE')
ORDER BY name, referenced_owner, referenced_name;
~~~

Meaning of key columns:

- **NAME / TYPE**: name and type of the **dependent** object.
- **REFERENCED_OWNER / REFERENCED_NAME / REFERENCED_TYPE**: schema, name, and type of the **referenced** object.
- **DEPENDENCY_TYPE**: dependency type info recorded by Oracle; do not use a single value alone to deduce the impact of every DDL operation.

A procedure calling `DBMS_OUTPUT` or system packages may show additional relationships beyond business objects. To focus on the lab chain, filter on `REFERENCED_NAME` accordingly.

### 2.2. Finding objects that depend on a table

~~~sql
SELECT name,
       type,
       referenced_name,
       referenced_type
FROM user_dependencies
WHERE referenced_name = 'KHACH_HANG_DEP'
ORDER BY name, type;
~~~

This query primarily finds **direct dependencies**. If a procedure depends on a view and the view depends on a table, filtering on the table name may show only the view and omit the procedure.

You can query a multi-level dependency graph using Oracle hierarchical query syntax:

~~~sql
SELECT LEVEL AS muc_do,
       LPAD(' ', 2 * (LEVEL - 1)) || name AS doi_tuong_phu_thuoc,
       type,
       referenced_name AS phu_thuoc_vao,
       referenced_type
FROM user_dependencies
START WITH referenced_name = 'KHACH_HANG_DEP'
           AND referenced_type = 'TABLE'
CONNECT BY NOCYCLE
       PRIOR name = referenced_name
   AND PRIOR type = referenced_type
ORDER SIBLINGS BY name;
~~~

In the example graph, level 1 is the view referencing the table, and the next level is the procedure referencing the view. Large systems can have multiple paths to the same object or long dependency chains; interpret results as **paths in a graph**, not necessarily a tree without duplicates. When other schemas are involved, use `OWNER`/`REFERENCED_OWNER` and matching view scopes to join accurately instead of matching by name alone.

### 2.3. Checking object status

~~~sql
SELECT object_name,
       object_type,
       status,
       last_ddl_time
FROM user_objects
WHERE object_name IN (
    'KHACH_HANG_DEP',
    'V_KH_ACTIVE',
    'P_DEM_KH_ACTIVE'
)
ORDER BY object_type, object_name;
~~~

**STATUS = VALID** generally means Oracle validated the definition as of the metadata snapshot. **STATUS = INVALID** signals that the object needs recompilation/revalidation or cannot be used under the current definition. This status **is not a complete test that all business SQL or runtime data are valid**.

**LAST_DDL_TIME** shows when DDL affecting the object was recorded; it does not mean the last time table row data changed. Never use this column as an `INSERT`/`UPDATE`/`DELETE` timestamp.

## 3. What is invalidation?

**Invalidation** is Oracle's mechanism for marking a dependent object or execution structure as no longer trustworthy as-is. Its purpose is to prevent the system from continuing to use stale definitions, signatures, privileges, or execution plans after a related change.

~~~text
Referenced object changes
                |
                v
Oracle evaluates dependencies and change impact
                |
       +--------+---------+
       |                  |
       v                  v
No impact             Affected or needs revalidation
       |                  |
       v                  v
Continue using       Dependent object/cursor invalidated
                          |
                          v
               On recompile/re-execution
                  +-------+--------+
                  |                |
                  v                v
            Compiles OK       Compile fails
                  |                |
                  v                v
            VALID, runs      INVALID or error
~~~

Not every DDL invalidates every object in the graph. Oracle supports **fine-grained dependency tracking** in supported cases/versions: the system tracks specific referenced elements, such as individual columns or public package components, to avoid invalidation when unrelated elements change.

### 3.1. Changes likely to have an impact

| Change | Potentially affected objects | Key point to understand |
| --- | --- | --- |
| Rename or drop a column used by a view/procedure | Views, PL/SQL program units, and downstream dependents | Code referencing the old column name can no longer compile |
| DROP/RECREATE a table or view | Referencing objects | Source object disappears or its new definition differs |
| CREATE OR REPLACE VIEW | Objects using the view's columns | Oracle evaluates changes to the view's interface definition |
| Modify a package specification | Program units calling affected public elements | Signature/interface changes may require recompilation |
| Modify a package body | The body itself and sessions currently using the package | Generally differs from spec changes; stateful packages need care |
| REVOKE a direct privilege needed to compile/execute | Objects in the grantee schema | After privilege changes, objects may fail to compile or run |
| Change a synonym's target object | Code or queries using the synonym | Name resolution and target object may change |
| DDL changing indexes or optimizer statistics | SQL cursors and execution plans | Cursors may invalidate/reparse; stored procedures do not necessarily become INVALID |

**Regular data `UPDATE`/`INSERT`/`DELETE` operations are not DDL changing object definitions**, so they do not automatically make views or procedures `INVALID`. They can affect query outputs and data characteristics, which should be kept distinct from metadata dependencies.

### 3.2. Fine-grained dependencies: which changes actually matter?

Suppose a procedure only reads column **MA_KHACH_HANG** from a table. When an unused new column is added to the table, Oracle can avoid invalidating the procedure because the interface it uses was not affected. Conversely, renaming or dropping `MA_KHACH_HANG` directly impacts it.

These cases are not an absolute rule based solely on the `ALTER TABLE` type. Impact also depends on how references are written (e.g., `SELECT *` vs. explicit column lists), object type, Oracle version, and exact change details. During maintenance, verify via metadata and actual testing rather than assuming every `ADD COLUMN` is safe for all dependent objects.

### 3.3. Cursor invalidation differs from object INVALID status

A parsed `SELECT` can have a shared cursor in the library cache. Table structure changes or optimizer statistics updates under certain invalidation policies can require that cursor to **hard parse or re-optimize**.

This happens at the SQL execution structure level. A stored procedure can remain **VALID**, yet internal SQL needs a new cursor on its next run. Conversely, a procedure with `STATUS = INVALID` may fail to compile due to a missing column or privilege while an unrelated standalone `SELECT` runs normally.

Do not equate hard parse counts with the number of `INVALID` stored objects, and do not use `USER_OBJECTS.STATUS` to infer that every shared SQL cursor is still valid.

## 4. The VALID → INVALID → VALID lifecycle

Stored objects in Oracle such as views or PL/SQL units can go through this lifecycle:

1. **Created or compiled successfully:** Oracle validates the definition, records dependencies, and marks the appropriate status as `VALID`.
2. **Source object changes:** Oracle determines which dependents are no longer safe to use as-is and may invalidate them.
3. **Invoked next time:** For many PL/SQL units, Oracle attempts **automatic recompilation** prior to execution.
4. **Recompilation succeeds:** If the definition remains compatible, the object returns to `VALID` and executes.
5. **Recompilation fails:** The object stays `INVALID` or the caller receives an error; the definition, privileges, or source object must be fixed.

**`INVALID` does not always mean source code was deleted or table data is corrupted.** It can be a temporary state requiring recompilation after DDL. Yet do not treat every `INVALID` as harmless: if a referenced column was dropped, automatic recompilation cannot repair broken syntax.

### 4.1. Common errors

| Message/error code | Diagnostic hint |
| --- | --- |
| **ORA-04063: view ... has errors** | The view has compilation errors or an invalid definition |
| **ORA-06508: PL/SQL: could not find program unit being called** | The called program unit is unavailable, possibly due to invalidation/failed recompile |
| **ORA-04068: existing state of packages has been discarded** | Stateful package state in the session was discarded after a change/invalidation |
| **ORA-04061 / ORA-04065** | Errors related to the state or modification of a program unit/package |
| **ORA-00904: invalid identifier** | Invalid column or expression reference, possibly after renaming/dropping a column |
| **ORA-00942: table or view does not exist** | Missing object or missing visibility privileges on the target object |
| **PLS-00302 / PLS-00306** | Mismatched package component or PL/SQL call signature |

Real error stacks can combine several codes in sequence depending on detection point, Oracle version, and client tool. Compilation errors after DDL must be cross-checked against **USER_ERRORS**, object metadata, and recent schema changes.

## 5. Hands-on lab: building an observable dependency graph

The example below uses an **empty sandbox schema** where the account holds **CREATE TABLE, CREATE VIEW, and CREATE PROCEDURE**. Run sequentially on Oracle Database via SQLcl, SQL*Plus, or a SQL tool supporting PL/SQL blocks. Never reuse names of objects containing real business data.

### 5.1. Create the table, view, and procedure

~~~sql
-- Base table.
CREATE TABLE khach_hang_dep (
    ma_khach_hang NUMBER(6) CONSTRAINT pk_khach_hang_dep PRIMARY KEY,
    ho_ten        VARCHAR2(100 CHAR) NOT NULL,
    trang_thai    VARCHAR2(10 CHAR) NOT NULL,
    CONSTRAINT ck_khach_hang_dep_tt
        CHECK (trang_thai IN ('ACTIVE', 'INACTIVE'))
);

INSERT INTO khach_hang_dep
    (ma_khach_hang, ho_ten, trang_thai)
VALUES (1, 'Nguyen An', 'ACTIVE');

INSERT INTO khach_hang_dep
    (ma_khach_hang, ho_ten, trang_thai)
VALUES (2, 'Tran Binh', 'INACTIVE');

INSERT INTO khach_hang_dep
    (ma_khach_hang, ho_ten, trang_thai)
VALUES (3, 'Le Chi', 'ACTIVE');

COMMIT;

-- View directly dependent on the table and column TRANG_THAI.
CREATE OR REPLACE VIEW v_kh_active AS
SELECT ma_khach_hang, ho_ten
FROM khach_hang_dep
WHERE trang_thai = 'ACTIVE';

-- Procedure directly dependent on the view.
CREATE OR REPLACE PROCEDURE p_dem_kh_active AS
    v_dem NUMBER;
BEGIN
    SELECT COUNT(*)
    INTO v_dem
    FROM v_kh_active;

    DBMS_OUTPUT.PUT_LINE('Active customers: ' || v_dem);
END;
/
~~~

In SQLcl/SQL*Plus, enable `DBMS_OUTPUT` display:

~~~sql
SET SERVEROUTPUT ON

EXEC p_dem_kh_active;
~~~

Expected output is **Active customers: 2**. The trailing **/** after procedure creation is a tool command submitting the PL/SQL block for execution, not part of PL/SQL grammar. When using JDBC/Spring JDBC, procedure invocation and output handling differ.

### 5.2. Inspect the generated dependency graph

~~~sql
SELECT name, type, referenced_name, referenced_type
FROM user_dependencies
WHERE name IN ('V_KH_ACTIVE', 'P_DEM_KH_ACTIVE')
  AND referenced_name IN ('KHACH_HANG_DEP', 'V_KH_ACTIVE')
ORDER BY name;
~~~

Expected relationships:

| NAME | TYPE | REFERENCED_NAME | REFERENCED_TYPE |
| --- | --- | --- | --- |
| P_DEM_KH_ACTIVE | PROCEDURE | V_KH_ACTIVE | VIEW |
| V_KH_ACTIVE | VIEW | KHACH_HANG_DEP | TABLE |

The procedure may also have a dependency on system package **DBMS_OUTPUT**; the query filters down to the two business relationships for clarity.

Check statuses:

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN (
    'KHACH_HANG_DEP', 'V_KH_ACTIVE', 'P_DEM_KH_ACTIVE'
)
ORDER BY object_type, object_name;
~~~

Initially, successfully created objects normally show STATUS **VALID**.

### 5.3. Make a change that breaks a dependency

To see invalidation clearly, rename the column used in the view's `WHERE` clause:

~~~sql
ALTER TABLE khach_hang_dep
    RENAME COLUMN trang_thai TO tinh_trang;
~~~

Column data is not deleted, yet the view still contains **WHERE TRANG_THAI = 'ACTIVE'**, while that column name no longer exists. Oracle must re-evaluate the view definition, and dependent objects can become invalidated. Observe:

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN ('V_KH_ACTIVE', 'P_DEM_KH_ACTIVE')
ORDER BY object_name;
~~~

With a direct change removing the referenced column name, the view can no longer compile cleanly until its definition is fixed or the column name is restored. Upstream dependents' statuses can depend on when Oracle propagates invalidation and attempts recompilation.

Try querying the view or calling the procedure:

~~~sql
SELECT COUNT(*) FROM v_kh_active;

EXEC p_dem_kh_active;
~~~

These commands **are expected to raise errors** and are not part of standard data setup. Depending on the failure point, Oracle may report an invalid view error, invalid identifier, or program unit error. Do not rely on a single specific error code as your sole diagnostic criterion.

To inspect detailed compilation errors after attempting to compile the view or procedure:

~~~sql
ALTER VIEW v_kh_active COMPILE;

SELECT name, type, line, position, text
FROM user_errors
WHERE name IN ('V_KH_ACTIVE', 'P_DEM_KH_ACTIVE')
ORDER BY name, sequence;
~~~

`ALTER VIEW COMPILE` will report warnings/errors because the referenced column is gone. `USER_ERRORS` reveals the actual problem; do not rely solely on SQL client summary messages.

### 5.4. Restore the source and recompile

In this sandbox schema, restore the column name:

~~~sql
ALTER TABLE khach_hang_dep
    RENAME COLUMN tinh_trang TO trang_thai;

ALTER VIEW v_kh_active COMPILE;
ALTER PROCEDURE p_dem_kh_active COMPILE;
~~~

Afterward:

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN ('V_KH_ACTIVE', 'P_DEM_KH_ACTIVE')
ORDER BY object_name;

SELECT name, type, line, position, text
FROM user_errors
WHERE name IN ('V_KH_ACTIVE', 'P_DEM_KH_ACTIVE')
ORDER BY name, sequence;

SELECT COUNT(*) AS so_khach_active
FROM v_kh_active;
~~~

Once definitions and privileges are valid again, **the view and procedure return to `VALID`**, and querying the view again returns **2**. Some objects may already be automatically recompiled by Oracle upon first reference after the source is restored; explicit `COMPILE` statements here make the maintenance step clear.

**`ALTER TABLE` is DDL with implicit commit behavior.** Never run column changes as part of an incomplete application transaction expecting `ROLLBACK` to undo the DDL.

### 5.5. Clean up practice data

After finishing and confirming only your exercise's sandbox objects remain:

~~~sql
DROP PROCEDURE p_dem_kh_active;
DROP VIEW v_kh_active;
DROP TABLE khach_hang_dep PURGE;
~~~

Dropping from dependent objects down to referenced objects makes dependency order clear. **PURGE** bypasses the normal recycle bin retention; only use it when test data can be permanently removed.

## 6. Package specification and package body: interface dependencies

For PL/SQL packages, distinguish:

- **Package specification (spec)**: the public interface declaring procedures/functions, types, constants, or variables accessible to callers.
- **Package body**: the implementation of specification items plus private elements.

Example:

~~~sql
CREATE OR REPLACE PACKAGE pkg_quy_tac_dep AS
    FUNCTION nhan_doi(p_gia_tri IN NUMBER) RETURN NUMBER;
END pkg_quy_tac_dep;
/

CREATE OR REPLACE PACKAGE BODY pkg_quy_tac_dep AS
    FUNCTION nhan_doi(p_gia_tri IN NUMBER)
        RETURN NUMBER
    AS
    BEGIN
        RETURN p_gia_tri * 2;
    END nhan_doi;
END pkg_quy_tac_dep;
/

CREATE OR REPLACE PROCEDURE p_dung_quy_tac_dep AS
    v_ket_qua NUMBER;
BEGIN
    v_ket_qua := pkg_quy_tac_dep.nhan_doi(10);
    DBMS_OUTPUT.PUT_LINE('Result: ' || v_ket_qua);
END p_dung_quy_tac_dep;
/
~~~

Procedure **P_DUNG_QUY_TAC_DEP** calls the package's public function. If only the calculation inside the **body** changes, the function signature remains intact and callers generally do not need source edits. However, the new package body must still compile validly, and replacing the body can affect **package state** in active sessions.

If you change the **spec** by renaming, removing a function, or altering a required signature used by callers, callers can become invalidated and fail recompilation until updated. Fine-grained dependency tracking can avoid propagating invalidation from unrelated public interface changes; therefore never assume "every spec edit invalidates every caller."

Inspect metadata specifically:

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN (
    'PKG_QUY_TAC_DEP',
    'P_DUNG_QUY_TAC_DEP'
)
ORDER BY object_type;
~~~

You will see two rows—**PACKAGE** and **PACKAGE BODY**—for the same package name. When errors occur in the body, filter for the right error/object type:

~~~sql
SELECT name, type, line, position, text
FROM user_errors
WHERE name = 'PKG_QUY_TAC_DEP'
ORDER BY type, sequence;
~~~

Compile manually within the required scope:

~~~sql
ALTER PACKAGE pkg_quy_tac_dep COMPILE SPECIFICATION;
ALTER PACKAGE pkg_quy_tac_dep COMPILE BODY;
ALTER PROCEDURE p_dung_quy_tac_dep COMPILE;
~~~

These commands apply only when the objects already exist; never use bulk recompiling to mask unresolved interface bugs. After the lab, drop the procedure and then the package when no longer needed.

### 6.1. Stateful packages and ORA-04068

A package with variables or state persisting across multiple calls in a session is a **stateful package**. If a package currently in use by a session is replaced or invalidated, Oracle may discard the old state; on the next call, the application can receive related errors, prominently **ORA-04068**.

This is particularly critical with **Java connection pools**, because physical JDBC connections keep Oracle sessions alive across many HTTP requests. A session holding pre-deployment package state can fail on its next call even though brand-new sessions succeed.

The solution is not "catch and ignore all errors." Determine whether package state is actually relied upon, design proper re-initialization, coordinate deployment/connection-pool refresh timing, and decide retries based on operation safety. Write transactions with uncertain outcomes must be checked before retrying.

## 7. Access privileges and cross-schema objects

Cross-schema dependencies also involve **privilege dependencies**. Suppose schema `APP_OWNER` owns a table, while schema `REPORT_APP` creates a view or procedure reading that table.

A DBA or object owner can grant privileges directly:

~~~sql
-- Illustrative example; run only when schemas/accounts exist
-- and the executor holds granting authority.
GRANT SELECT ON app_owner.don_hang TO report_app;
~~~

When `REPORT_APP` creates a stored PL/SQL unit referencing another schema's object, **privileges required for static SQL in definer's-rights PL/SQL must be granted directly as required**, rather than relying on roles enabled in an interactive session. Invoker's-rights units (`AUTHID CURRENT_USER`) have additional compile/runtime privilege rules; check both owner and invoker privileges per design.

If a required direct privilege is **REVOKE**d, compiled objects can become invalidated or fail to run/recompile. When diagnosing, distinguish:

1. Source object still exists, yet caller **lacks privileges**.
2. Source object was renamed or dropped.
3. Synonym still exists, yet target object or target privileges are no longer valid.
4. Dynamic SQL fails at runtime even though dependency metadata shows no direct reference path.

A synonym is an **object alias**; it does not create an independent copy of a table/procedure and grants no access privileges. Altering or dropping a synonym can affect code using that name depending on reference type and Oracle name resolution.

### 7.1. Querying cross-schema dependencies

Within appropriate privilege scope, you can query:

~~~sql
SELECT owner,
       name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type
FROM all_dependencies
WHERE referenced_owner = 'APP_OWNER'
  AND referenced_name = 'DON_HANG'
ORDER BY owner, name;
~~~

**ALL_DEPENDENCIES** shows only objects the caller is permitted to see; it is not guaranteed to cover the entire database. To assess full impact across all schemas, a DBA can use `DBA_DEPENDENCIES`, privilege metadata, and relevant application source repositories.

## 8. Dependency tracking does not cover every impact

An application can depend on Oracle in ways beyond what the stored-object data dictionary records.

| Dependency kind | Directly recorded by dictionary? | Supplementary method |
| --- | --- | --- |
| View directly selecting from a table | Usually yes | USER_DEPENDENCIES / ALL_DEPENDENCIES |
| Procedure calling a static package | Usually yes | Dependency views, package spec, and errors |
| Procedure using `EXECUTE IMMEDIATE` with dynamic table names | Cannot be assumed complete in compile-time dependencies | Code analysis, configuration review, and executed SQL logs |
| Java JDBC sending `SELECT` to a table | Not a stored schema object dependency | Search source code, repositories, query logs/observability |
| External report querying a view | Not always an Oracle stored dependent object | Reporting tool catalogs, API contracts, integration tests |
| Materialized view | Tracks source dependencies alongside its own refresh/staleness state | Check mview metadata and refresh mechanism |
| Database link to a remote object | Uses separate resolution/dependency mechanisms | Check privileges and metadata on both databases |

A **materialized view** can have **STALE** data state because it has not refreshed yet, which is distinct from `STATUS = INVALID` on an ordinary view. Likewise, a `VALID` stored procedure does not prove every dynamic SQL string inside it succeeds for all inputs.

When changing a schema, combine **dependency metadata**, **static/dynamic SQL analysis**, and **external caller testing**, especially for Java/Spring Boot applications.

## 9. Manual and automatic recompilation

Oracle can automatically attempt to recompile an invalid stored object when needed. However, automatic recompilation can add latency to the first request after deployment, and if the definition is no longer valid, the request still fails.

For specific objects:

~~~sql
ALTER VIEW v_kh_active COMPILE;
ALTER PROCEDURE p_dem_kh_active COMPILE;
ALTER PACKAGE pkg_quy_tac_dep COMPILE BODY;
~~~

Then check `STATUS` and `USER_ERRORS`. Never treat "Statement processed" or a single completed `COMPILE` command as proof that the entire dependency graph is valid.

In systems with many `INVALID` objects, Oracle provides schema/database recompilation utilities that DBAs can use when appropriate. Bulk recompilation consumes CPU and can cause contention; analyze root causes first. If an object is `INVALID` because a referenced column was dropped, recompiling repeatedly never replaces updating the code.

### 9.1. Processing order along the graph

For a chain:

~~~text
TABLE -> VIEW -> PROCEDURE -> APPLICATION
~~~

When fixing a dependency error, the logical order is:

1. Fix or restore the **root object** (table/column/privilege).
2. Recompile or verify **views**.
3. Recompile or verify **procedures/packages**.
4. Test **application callers** and verify business results.

This is a troubleshooting order for fixing root causes, not a requirement to manually invoke `COMPILE` on every object after every DDL statement. Oracle can automatically revalidate eligible objects on use.

## 10. Pre-deployment schema change assessment workflow

A small `ALTER TABLE` change in a migration can impact multiple services. To avoid discovering issues after traffic shifts to a new release, treat schema changes as **contract** changes between objects.

**Step 1 — Identify the object and interface changing.** Which table/view/package name changes? Does it touch an existing column, data type, constraint, or public function, or only add a new element?

**Step 2 — Retrieve direct and indirect dependents.** Use `USER_DEPENDENCIES`, `ALL_DEPENDENCIES`, or `DBA_DEPENDENCIES` per privileges. Record both owning schema and referenced owner.

**Step 3 — Check dependencies outside the database.** Search SQL in Java repositories, ORM mappings, batch jobs, reports, migrations, and dynamic SQL. These dependencies may not appear in `USER_DEPENDENCIES`.

**Step 4 — Classify impact.** Renaming or dropping directly used columns is high risk. Adding an unused column is generally lower risk, yet still inspect `SELECT *`, views, triggers, and special dependencies.

**Step 5 — Plan backward-compatible transitions.** Consider an *expand–migrate–contract* pattern: add the new structure, deploy compatible read/write code, migrate data, and remove the old name/column only after all callers have switched. Where appropriate, evaluate Oracle editioning mechanisms only after assessing object and operational limits for your version.

**Step 6 — Execute migration and compile.** Run controlled DDL, resolve definition errors directly, and check `USER_OBJECTS` and `USER_ERRORS`. For stateful packages, account for existing sessions and connection pools.

**Step 7 — Test the contract.** Exercise view/procedure SQL, Java APIs, batch jobs, and critical transactions. A `VALID` object only proves compilation within a limited scope; it does not guarantee business logic remains intact.

**Step 8 — Monitor post-deployment.** Watch `INVALID` object counts, `ORA-04063`/`06508`/`04068` errors, parse rates, and first-request latency. Prepare rollback/roll-forward plans aligned with DDL and migration capabilities, not relying on regular SQL transaction `ROLLBACK`.

## 11. Diagnosing an invalidation incident

Suppose after deployment, a Java API receives errors when calling procedure `P_DEM_KH_ACTIVE`. Proceed step by step:

### 11.1. Identify INVALID objects

~~~sql
SELECT object_name,
       object_type,
       status,
       last_ddl_time
FROM user_objects
WHERE status = 'INVALID'
ORDER BY object_type, object_name;
~~~

Not every `INVALID` object necessarily relates to the API. Filter by the right schema and dependency chain before making edits.

### 11.2. Retrieve compilation errors

~~~sql
SELECT name,
       type,
       line,
       position,
       text
FROM user_errors
ORDER BY name, sequence;
~~~

If a procedure reports an error calling a view, inspect the view itself and its source objects. A downstream error can be a symptom rather than the root cause.

### 11.3. Trace back to source objects

~~~sql
SELECT name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type
FROM user_dependencies
WHERE name = 'P_DEM_KH_ACTIVE'
ORDER BY referenced_owner, referenced_name;
~~~

Continue inspecting the referenced view and table. If the error involves missing privileges, check direct grants and recent `GRANT`/`REVOKE` changes. If the error involves a missing column, compare the current table/view definition against the previous migration version.

### 11.4. Fix and verify up to the application layer

Restore the object name, data type, or privilege—or update dependent code—recompile as needed, and invoke the exact call used by the Java application. When using a connection pool with stateful packages, handle pre-deployment sessions cleanly. If a write transaction failed mid-flow, verify commit state before retrying automatically.

## 12. Common misconceptions

**"Any DDL change on a table makes every procedure using that table INVALID."** False. Fine-grained dependency tracking can avoid invalidation when changes do not affect referenced elements.

**"An INVALID object means table data inside is corrupted."** False. `INVALID` is a metadata/compilation or usability state for an object, not a judgment on data integrity.

**"Clean compilation means all business logic is correct."** False. Compilation checks definitions and statically visible dependencies; dynamic SQL, runtime data, and Java callers still require testing.

**"USER_DEPENDENCIES lists every query from a Java application."** False. Java JDBC submits SQL from outside the database; it does not become a stored schema object dependency merely by running `SELECT`.

**"Replacing a package body always forces every caller to recompile."** Not necessarily. Depending on spec/interface differs from body implementation; however, replacing a package body can affect package state in active sessions.

**"Renaming a column affects only one table."** False. Views, procedures, dynamic SQL, ORM mappings, and upstream integrations may rely on the old name.

**"If a procedure is VALID, shared SQL cursors definitely will not reparse."** False. SQL cursors have their own lifecycle and invalidation rules, separate from a stored procedure's `STATUS`.

**"Every ORA-04068 error can be retried immediately."** Unsafe when a data-modifying call might already have made changes or transaction state is unclear. Understand package state and idempotency first.

**"Granting privileges via a role is enough for definer's-rights PL/SQL to compile."** False for static SQL requiring direct grants inside stored definer's-rights units. Grant privileges appropriately to the owner and program unit type.

## 13. Self-practice exercises

1. Draw the graph consisting of `TABLE KHACH_HANG`, `VIEW V_KH_ACTIVE`, and `PROCEDURE P_DEM_KH_ACTIVE`. Identify the procedure's direct and indirect dependencies.
2. Complete Section 5 and record `USER_DEPENDENCIES` output before renaming the column, after renaming, and after restoring the name. Which views show compilation status and errors?
3. A view only reads column `MA_KHACH_HANG`. Column `MO_TA` is added to the table. Can you conclude with certainty that the view will become `INVALID`? Why should fine-grained dependencies be considered?
4. A procedure uses `EXECUTE IMMEDIATE` with a table name from a variable. Why might checking `USER_DEPENDENCIES` miss the impact of renaming that table?
5. A package exposes public function `tinh_thue(p NUMBER)`. How does changing the formula inside the body differ from renaming the function in the spec?
6. Replacing a package body in production causes some JDBC connections to hit `ORA-04068`. Why might pre-existing stateful sessions be affected differently from brand-new sessions?
7. An object becomes `INVALID` after losing `SELECT` privilege on a table in another schema. Will running `COMPILE` repeatedly fix it? Which prerequisite must be restored?
8. Why does a SQL cursor needing to hard parse after a structural change not mean the stored procedure containing that SQL became `INVALID`?
9. When renaming a column referenced by a Java application, why is `USER_DEPENDENCIES` alone insufficient to allow dropping the old column immediately?
10. Draft a safe deployment plan for renaming column `TRANG_THAI` to `TINH_TRANG` when views, packages, and multiple versions of a Java service are running concurrently.

Dependency relationships help Oracle preserve consistency between **referenced object definitions** and **the objects consuming them**. Invalidation is a signal to revalidate or recompile after relevant changes; automatic recompilation succeeds only when source and privileges remain compatible. Combining the data dictionary with application analysis and post-migration testing allows schema evolution without accidentally breaking the system's dependency chain.
