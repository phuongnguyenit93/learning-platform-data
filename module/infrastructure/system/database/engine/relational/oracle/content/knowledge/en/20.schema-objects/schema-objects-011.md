# INVALID Objects, Recompilation, and Dependency Tracking

In Oracle Database, a schema object such as a view, procedure, function, package, trigger, or type can exist in the data dictionary yet remain in an **INVALID** state. This usually means Oracle does not yet have a usable compiled version of the object after its latest creation/modification, or a dependency the object relies on has changed.

When an application invokes an INVALID object, Oracle may attempt to recompile it automatically. If compilation succeeds, the object returns to VALID and execution proceeds. If errors remain, the application can receive errors such as ORA-04063, ORA-06508, or ORA-04045 along with specific PL/SQL compilation errors. Consequently, investigation cannot stop at running COMPILE: you must find the root error, changed dependencies, access privileges, and dependent objects that may be affected.

This lesson explains how to inspect object status, read compilation errors, compile the right object types, trace dependencies bidirectionally, handle direct privileges in stored PL/SQL, and plan recompilation after schema changes.

## 1. What Do VALID and INVALID Mean?

Oracle stores schema object metadata in the data dictionary. For compilable object types, the STATUS column in USER_OBJECTS, ALL_OBJECTS, or DBA_OBJECTS typically indicates:

| STATUS | Meaning |
| --- | --- |
| VALID | The object currently has a valid state per Oracle metadata/compilation |
| INVALID | The object must be compiled or revalidated before normal use |

An INVALID object still exists in USER_OBJECTS. INVALID does not mean the object was dropped, nor does it state the root cause on its own. An object might have been created before a dependency existed, contain source code errors, lack direct privileges, suffer from a package signature change, or depend on a modified referenced object.

### 1.1. Common Object Types

- **VIEW:** the SELECT defining the view no longer compiles, e.g., a referenced table/column changed or privileges were revoked.
- **PROCEDURE/FUNCTION:** PL/SQL source or embedded static SQL fails to compile.
- **PACKAGE:** specification or body has errors; a package body can be INVALID even while its specification remains VALID.
- **TRIGGER:** trigger source or objects referenced by the trigger are no longer valid.
- **TYPE/TYPE BODY:** type definition or body needs recompilation.
- **MATERIALIZED VIEW:** may require refresh/compile depending on cause and object type; do not apply PL/SQL compile syntax indiscriminately to every object type.

Not all object types in *_OBJECTS share the same compilation semantics. When writing operational scripts, filter appropriate OBJECT_TYPE values rather than assuming every INVALID object can be fixed with a single ALTER ... COMPILE statement.

### 1.2. INVALID Can Appear After DDL

Example:

1. View V_ORDER_SUMMARY references table ORDERS.
2. Procedure P_CLOSE_ORDER calls package PKG_ORDER.
3. Package PKG_ORDER uses view V_ORDER_SUMMARY.
4. A DDL change on a referenced object causes dependent objects to require revalidation.

Oracle tracks dependencies to recognize relationships among objects. When an object changes, Oracle may mark certain dependent objects as INVALID. When an object is next referenced, Oracle can attempt automatic recompilation. Fine-grained dependency tracking avoids unnecessary invalidation for some SQL changes that do not affect referenced elements; however, changing a package specification or public interface can still impact many callers.

## 2. Listing INVALID Objects in a Schema

### 2.1. Current Schema: USER_OBJECTS

~~~sql
SELECT
    object_type,
    object_name,
    status,
    last_ddl_time
FROM user_objects
WHERE status = 'INVALID'
ORDER BY object_type, object_name;
~~~

USER_OBJECTS lists objects owned by the logged-in schema. This is usually the starting point when developers investigate their own objects.

### 2.2. Accessible Objects: ALL_OBJECTS

~~~sql
SELECT
    owner,
    object_type,
    object_name,
    status,
    last_ddl_time
FROM all_objects
WHERE status = 'INVALID'
ORDER BY owner, object_type, object_name;
~~~

ALL_OBJECTS shows objects accessible to the current session per metadata/privileges. It is not necessarily a list of every object in the database.

### 2.3. Entire Database: DBA_OBJECTS

DBAs or appropriately privileged accounts can use:

~~~sql
SELECT
    owner,
    object_type,
    object_name,
    status,
    last_ddl_time
FROM dba_objects
WHERE status = 'INVALID'
ORDER BY owner, object_type, object_name;
~~~

This query suits database-wide reporting. Never grant DBA_OBJECTS or broad catalog read privileges merely so an application can list objects in its own schema.

### 2.4. Counting Objects by Owner and Type

~~~sql
SELECT
    owner,
    object_type,
    COUNT(*) AS invalid_count
FROM dba_objects
WHERE status = 'INVALID'
GROUP BY owner, object_type
ORDER BY owner, invalid_count DESC, object_type;
~~~

This query helps spot whether a schema has a single broken package body or hundreds of INVALID objects after a deployment. A high count alone does not identify the root cause; drill down by object and dependency.

### 2.5. Recording Timestamps and Editions

When investigating environments using Edition-Based Redefinition, note that objects can be distinguished by edition. If your release's metadata views include EDITION_NAME, include that column in reports so objects across editions are not confused. Also record snapshot timestamps and database/service/instance details in incident logs.

## 3. Reading Compilation Errors

INVALID status only tells you an object needs attention; details reside in *_ERRORS.

### 3.1. USER_ERRORS

For objects in the current schema:

~~~sql
SELECT
    name,
    type,
    sequence,
    line,
    position,
    text,
    attribute
FROM user_errors
WHERE name = UPPER(:object_name)
ORDER BY sequence;
~~~

Key columns:

| Column | Meaning |
| --- | --- |
| NAME | Object name |
| TYPE | Object type, e.g., PROCEDURE, FUNCTION, PACKAGE BODY, TRIGGER |
| SEQUENCE | Error message ordering |
| LINE | Source line number |
| POSITION | Column position within the line |
| TEXT | Error message text |
| ATTRIBUTE | Message category, typically ERROR or WARNING |

Names in USER_ERRORS follow object identifier rules. For standard unquoted identifiers, UPPER(:object_name) is the usual filter. If an object uses case-sensitive quoted identifiers, pass the exact name.

### 3.2. ALL_ERRORS and DBA_ERRORS

To view errors in another schema:

~~~sql
SELECT
    owner,
    name,
    type,
    sequence,
    line,
    position,
    text,
    attribute
FROM dba_errors
WHERE owner = UPPER(:owner)
  AND name = UPPER(:object_name)
ORDER BY sequence;
~~~

Use ALL_ERRORS when you only need errors on objects accessible to the session; DBA_ERRORS is for accounts privileged to inspect everything.

### 3.3. SHOW ERRORS in SQL*Plus/SQLcl

In SQL*Plus or SQLcl:

~~~sql
SHOW ERRORS PROCEDURE p_rebuild_summary;
SHOW ERRORS PACKAGE BODY pkg_order;
SHOW ERRORS VIEW v_order_summary;
~~~

SHOW ERRORS is a client command, not a SQL statement sent directly to the database. In JDBC applications or tools lacking that command, query USER_ERRORS/ALL_ERRORS/DBA_ERRORS.

### 3.4. Fetching Source for Cross-Reference

For PL/SQL source:

~~~sql
SELECT
    line,
    text
FROM user_source
WHERE name = UPPER(:object_name)
  AND type = UPPER(:object_type)
ORDER BY line;
~~~

For other schemas, query ALL_SOURCE or DBA_SOURCE per privileges. Source lets you match error line numbers to exact statements. For views, fetch DDL via DBMS_METADATA.GET_DDL or inspect definitions in appropriate metadata views.

Never edit source merely to silence an error message without confirming business requirements and object dependencies.

## 4. Common Causes of INVALID Objects

### 4.1. Syntax or Data Type Errors in Source

~~~sql
CREATE OR REPLACE PROCEDURE p_test_invalid AS
BEGIN
    SELECT missing_column
    INTO   l_value
    FROM   employees
    WHERE  employee_id = 100;
END;
/
~~~

This example lacks a declaration for variable l_value, and missing_column may not exist. Oracle stores the object definition, but compilation fails; USER_ERRORS reveals the exact errors. Fix the source against the actual schema and recompile.

### 4.2. Dropped, Renamed, or Interface-Changed Dependencies

A procedure may reference a view or package. If a dependency is dropped or a package signature changes, dependents can become INVALID or report missing/incompatible objects on compilation.

For instance, a procedure calls:

~~~sql
pkg_customer.get_status(p_customer_id, p_status);
~~~

If the package specification renames the procedure or alters parameter types, callers must be updated to match the new interface and recompiled.

### 4.3. Missing Direct Privileges in Stored PL/SQL

For stored PL/SQL running under definer's rights (default when AUTHID CURRENT_USER is omitted), privileges required by static SQL inside the unit must be granted directly to the unit's owner. Privileges granted only through roles are normally insufficient for compiling/executing under definer's-rights semantics.

Example:

~~~sql
GRANT SELECT ON data_owner.orders TO app_owner;
~~~

If APP_OWNER.P_ORDER_REPORT queries DATA_OWNER.ORDERS, APP_OWNER needs appropriate direct privileges. Creating a synonym does not substitute for object privileges. A synonym is only an alias for name resolution.

With invoker's-rights units (AUTHID CURRENT_USER), runtime access is checked against the invoker; however, dependencies, object creation privileges, and compilation context must still be designed properly. When compilation reports insufficient privileges, check owner, AUTHID setting, and actual privileges before granting more access.

### 4.4. Misdirected Synonyms or Cross-Schema Dependencies

A procedure may reference a synonym instead of using explicit owner.object notation. If the synonym is repointed or its target no longer exists, dependent objects may fail to compile. Query ALL_SYNONYMS/DBA_SYNONYMS to check where the synonym points.

### 4.5. Package Specification Changes

A package specification is the public interface. Changing public names, parameter types, constants, types, or declarations can force dependent callers to recompile. Changes confined to the package body usually affect callers less since the interface stays unchanged, though the package body itself must still compile cleanly.

### 4.6. Remote Dependencies Over Database Links

Objects referencing remote objects over database links introduce remote dependency rules. Oracle manages remote dependencies using timestamp or signature modes; connectivity, privileges, or DDL in the remote database can cause compilation or execution failures. When investigating, check REFERENCED_LINK_NAME in dependency views and verify database link and remote object status via authorized processes.

## 5. Recompiling a Specific Object

Fix the root cause first, then recompile the right object type. Compiling does not fix broken source or grant missing privileges by itself.

### 5.1. Views

~~~sql
ALTER VIEW v_order_summary COMPILE;
~~~

Then inspect errors:

~~~sql
SELECT line, position, text
FROM user_errors
WHERE name = 'V_ORDER_SUMMARY'
  AND type = 'VIEW'
ORDER BY sequence;
~~~

### 5.2. Procedures and Functions

~~~sql
ALTER PROCEDURE p_close_order COMPILE;
ALTER FUNCTION f_order_total COMPILE;
~~~

If compilation still fails, query USER_ERRORS filtering by exact name and type.

### 5.3. Package Specifications and Bodies

~~~sql
ALTER PACKAGE pkg_order COMPILE SPECIFICATION;
ALTER PACKAGE pkg_order COMPILE BODY;
~~~

Specification and body are distinct parts. If the spec is INVALID, fix the spec before the body. If the spec is VALID while the body is INVALID, compile the body and check errors for type PACKAGE BODY.

### 5.4. Triggers

~~~sql
ALTER TRIGGER trg_orders_audit COMPILE;
~~~

A trigger can be INVALID due to its own source or referenced objects. Do not enable/disable triggers as a substitute for fixing compilation errors; enabled/disabled state and validity state are separate concerns.

### 5.5. Types and Other Objects

Types have their own compile syntax depending on kind and specification/body state. Objects such as materialized views have their own handling procedures. Consult the SQL Language Reference for your release and specific object type rather than running one generic ALTER ... COMPILE across every OBJECT_TYPE.

### 5.6. REUSE SETTINGS

For PL/SQL objects, compile syntax supports REUSE SETTINGS to preserve previously stored compiler settings:

~~~sql
ALTER PROCEDURE p_close_order COMPILE REUSE SETTINGS;
ALTER PACKAGE pkg_order COMPILE BODY REUSE SETTINGS;
~~~

This helps when recompiling without accidentally altering an object's compiler flags. If the goal is to change PL/SQL optimization or debug settings, explicitly configure them and test the impact first.

## 6. Confirming Objects Are VALID After Compilation

Do not treat an ALTER ... COMPILE command returning success as sole proof. Check status explicitly:

~~~sql
SELECT
    object_name,
    object_type,
    status,
    last_ddl_time
FROM user_objects
WHERE object_name IN (
    'V_ORDER_SUMMARY',
    'P_CLOSE_ORDER',
    'F_ORDER_TOTAL',
    'PKG_ORDER',
    'TRG_ORDERS_AUDIT'
)
ORDER BY object_type, object_name;
~~~

For packages, two separate object types appear: PACKAGE and PACKAGE BODY. Check both:

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name = 'PKG_ORDER'
ORDER BY object_type;
~~~

Check any remaining errors:

~~~sql
SELECT name, type, line, position, text
FROM user_errors
WHERE name = 'PKG_ORDER'
ORDER BY type, sequence;
~~~

If an object is VALID yet still fails at runtime, inspect runtime privileges, data, dynamic SQL, database links, and errors not caught at compile time. VALID does not guarantee every runtime execution path will succeed.

## 7. What Is a Dependency?

A dependency describes that object A relies on object B to compile or execute. In Oracle dependency views:

- OWNER, NAME, TYPE: the **dependent** object.
- REFERENCED_OWNER, REFERENCED_NAME, REFERENCED_TYPE: the **referenced** object.
- REFERENCED_LINK_NAME: database link if the dependency is remote.
- DEPENDENCY_TYPE: dependency kind, such as HARD or REF as applicable.

Example:

~~~text
APP_OWNER.P_ORDER_REPORT
        |
        | depends on
        v
DATA_OWNER.V_ORDER_SUMMARY
        |
        | depends on
        v
DATA_OWNER.ORDERS
~~~

If ORDERS changes, you must identify objects directly and indirectly depending on it. When a package spec changes, identify callers and other objects relying on that interface.

## 8. Inspecting Direct Dependencies

### 8.1. Objects in the Current Schema

~~~sql
SELECT
    name AS dependent_name,
    type AS dependent_type,
    referenced_owner,
    referenced_name,
    referenced_type,
    referenced_link_name,
    dependency_type
FROM user_dependencies
WHERE name = UPPER(:dependent_object)
ORDER BY referenced_owner, referenced_type, referenced_name;
~~~

This query answers: "Which objects does this object depend on?"

### 8.2. Finding Which Objects Depend on the Current Object

~~~sql
SELECT
    name AS dependent_name,
    type AS dependent_type,
    referenced_owner,
    referenced_name,
    referenced_type,
    dependency_type
FROM user_dependencies
WHERE referenced_owner = USER
  AND referenced_name = UPPER(:referenced_object)
ORDER BY type, name;
~~~

This checks only dependent objects in the current schema referencing the specified object. If the referenced object resides in another schema, filter REFERENCED_OWNER by that owner.

### 8.3. Database-Wide via DBA_DEPENDENCIES

~~~sql
SELECT
    owner,
    name AS dependent_name,
    type AS dependent_type,
    referenced_owner,
    referenced_name,
    referenced_type,
    referenced_link_name,
    dependency_type
FROM dba_dependencies
WHERE referenced_owner = UPPER(:referenced_owner)
  AND referenced_name = UPPER(:referenced_name)
ORDER BY owner, type, name;
~~~

This query is vital before altering shared tables or packages. Objects in other schemas can depend on your object, so checking only USER_DEPENDENCIES would miss cross-schema callers.

## 9. Tracing Multi-Level Dependencies

### 9.1. Finding Multi-Level Dependents from an Object

Each row in DBA_DEPENDENCIES represents a dependent object referencing a referenced object. You can use CONNECT BY NOCYCLE to walk from a root object to direct and indirect dependents:

~~~sql
SELECT
    LEVEL AS dependency_level,
    owner,
    name AS dependent_name,
    type AS dependent_type,
    referenced_owner,
    referenced_name,
    referenced_type,
    SYS_CONNECT_BY_PATH(
        owner || '.' || name || ' [' || type || ']',
        ' <- '
    ) AS dependent_path
FROM dba_dependencies
START WITH referenced_owner = UPPER(:root_owner)
   AND referenced_name = UPPER(:root_name)
   AND referenced_type = UPPER(:root_type)
CONNECT BY NOCYCLE
       PRIOR owner = referenced_owner
   AND PRIOR name = referenced_name
   AND PRIOR type = referenced_type
ORDER SIBLINGS BY owner, type, name;
~~~

Read the tree direction carefully:

- START WITH selects objects directly referencing the root object.
- Each result row is a dependent object.
- CONNECT BY uses the prior level's dependent object as the next level's referenced object.
- NOCYCLE prevents infinite loops if metadata contains circular references.

This query shows the dependency metadata scope; it does not imply every listed object is INVALID. Cross-check DBA_OBJECTS to inspect statuses and see which objects need attention.

### 9.2. Retrieving Status of Dependent Objects

~~~sql
SELECT
    d.owner,
    d.name,
    d.type,
    o.status,
    o.last_ddl_time,
    d.referenced_owner,
    d.referenced_name,
    d.referenced_type
FROM dba_dependencies d
JOIN dba_objects o
  ON o.owner = d.owner
 AND o.object_name = d.name
 AND o.object_type = d.type
WHERE d.referenced_owner = UPPER(:referenced_owner)
  AND d.referenced_name = UPPER(:referenced_name)
ORDER BY d.owner, d.type, d.name;
~~~

This lists direct dependents and their current status. An object may appear in multiple rows if it references multiple objects; thus row count does not necessarily equal unique object count. When counting objects, deduplicate by owner/name/type first.

### 9.3. Dependencies Are Metadata, Not All Business Relationships

Dependency views track references Oracle can resolve at object creation time. Relationships built through dynamic SQL, string-concatenated table names, scheduler jobs invoking procedures by name, application code issuing raw SQL, or external configs may not appear in *_DEPENDENCIES.

Example:

~~~sql
EXECUTE IMMEDIATE
    'SELECT COUNT(*) FROM ' || p_table_name
    INTO l_count;
~~~

Oracle cannot always statically know which object P_TABLE_NAME will select at runtime. Therefore, complement dependency metadata with searches across source code, application repositories, job metadata, and deployment logs.

## 10. Direct vs. Reverse Dependencies

When an object is INVALID, ask two distinct questions:

1. **What does this object need?** Find the referenced objects it depends on.
2. **Who needs this object?** Find the dependent objects referencing it.

For example, if PKG_ORDER is INVALID because view V_ORDER_SUMMARY fails to compile:

- Follow PKG_ORDER's dependencies forward to find the views/packages/tables it requires.
- Trace reverse dependencies from PKG_ORDER to find procedures, triggers, or views calling the package.

Do not immediately recompile the entire schema when one object fails. Find the root dependency first, fix the prerequisite, and then compile dependents in proper order.

## 11. Impact of Dependency Changes and Invalidation

### 11.1. DDL on Referenced Objects

When a table, view, package specification, or other object changes, Oracle checks dependencies and may invalidate dependent objects. Later, when a dependent is invoked, Oracle can recompile it automatically. If the interface remains compatible and privileges are intact, the object can return to VALID without manual DBA compilation.

### 11.2. Fine-Grained Dependency Tracking

Oracle tracks dependencies at finer granularity in many SQL scenarios, reducing invalidation when changes do not affect referenced columns or attributes. Still, never assume every DDL leaves dependents VALID. Verify actual object statuses after deployment and consult dependency management docs for your release.

### 11.3. Package Specification vs. Body

- Changing a **package specification** can affect callers because the public interface changed.
- Changing only a **package body** without altering the interface usually does not require callers to recompile; however, the body itself must still compile cleanly.
- Changing types or signatures exposed in a package interface can trigger multi-level invalidation.

This is why keeping interfaces stable and isolating implementation changes from public APIs whenever possible is good practice.

### 11.4. Synonyms Are Not Security Dependencies

A synonym resolves an object name but grants no access privileges. If a synonym exists yet the user lacks privileges on the target, compilation or execution still fails. During investigation, check both the synonym target and actual object privileges.

## 12. Privileges Required to Compile and Run

### 12.1. Direct Grants for Definer-Rights PL/SQL

By default, stored PL/SQL executes under definer's rights. Object privileges needed by static SQL inside the unit must be granted directly to the schema owner. Privileges acquired via roles are not used as direct object privileges during compilation/execution of definer-rights units under applicable rules.

Example:

~~~sql
-- Executed by DATA_OWNER or a DBA with grant privileges.
GRANT SELECT ON data_owner.orders TO app_owner;
GRANT EXECUTE ON common_owner.pkg_currency TO app_owner;
~~~

Then the owner recompiles the object:

~~~sql
ALTER PROCEDURE p_order_report COMPILE;
~~~

Never grant SELECT ANY TABLE or EXECUTE ANY PROCEDURE merely to make an object compile. Grant exact privileges on exact objects following least privilege.

### 12.2. AUTHID CURRENT_USER

Units declared with AUTHID CURRENT_USER run under the invoker's privileges for runtime operations governed by invoker's rights. This is a different security model from default definer's rights. Inspect package/procedure declarations and PL/SQL Security docs before changing AUTHID; switching AUTHID alters security behavior and is not a generic compile-fix trick.

### 12.3. Synonyms and Privileges

If APP_OWNER uses synonym ORDERS pointing to DATA_OWNER.ORDERS, appropriate privileges on DATA_OWNER.ORDERS are still required. Creating a synonym does not replace GRANT.

## 13. Compiling Multiple Objects in a Schema

After a major deployment, INVALID objects in a schema may need recompiling. Run bulk recompilation only after fixing root causes; compiling en masse while dependencies remain broken leaves objects INVALID and clutters logs.

### 13.1. DBMS_UTILITY.COMPILE_SCHEMA

~~~sql
BEGIN
    DBMS_UTILITY.COMPILE_SCHEMA(
        schema         => 'APP_OWNER',
        compile_all    => FALSE,
        reuse_settings => TRUE
    );
END;
/
~~~

COMPILE_ALL => FALSE processes only INVALID objects; TRUE compiles all eligible objects in the schema. REUSE_SETTINGS => TRUE preserves stored compiler settings. The caller needs appropriate privileges; when operating on another schema, DBAs must follow environment permissions and procedures.

### 13.2. UTL_RECOMP

Oracle provides UTL_RECOMP for batch recompilation, especially useful after database upgrades or operations leaving many invalid objects. Example running serially for a schema:

~~~sql
BEGIN
    UTL_RECOMP.RECOMP_SERIAL('APP_OWNER');
END;
/
~~~

UTL_RECOMP is typically executed by DBAs during maintenance windows and has specific privilege/prerequisite requirements. Parallel execution can reduce runtime while increasing CPU/I/O load and contention; verify package signatures for your release and choose appropriate parallelism. Never run multiple recompilation tools concurrently on the same schema without coordination.

### 13.3. Never Use Bulk Recompilation to Mask Root Causes

If an object is INVALID because a table/column was dropped, a package spec became incompatible, or direct privileges were revoked, repeatedly running COMPILE_SCHEMA will never fix the root cause. Fix dependencies, interfaces, privileges, and source first; compile afterward.

## 14. Monitoring Status Before and After Deployment

Every schema deployment should include a baseline and post-check.

### 14.1. Save a Snapshot of Invalid Objects

~~~sql
SELECT
    owner,
    object_type,
    object_name,
    status,
    last_ddl_time
FROM dba_objects
WHERE owner IN ('APP_OWNER', 'DATA_OWNER')
  AND status = 'INVALID'
ORDER BY owner, object_type, object_name;
~~~

Record pre-deployment results to distinguish pre-existing INVALID objects from objects impacted by the new release.

### 14.2. Check INVALID Objects After Deployment

~~~sql
SELECT
    owner,
    object_type,
    object_name,
    status,
    last_ddl_time
FROM dba_objects
WHERE owner IN ('APP_OWNER', 'DATA_OWNER')
  AND status = 'INVALID'
ORDER BY owner, object_type, object_name;
~~~

Compare against the baseline, then query DBA_ERRORS and dependencies for every newly INVALID object. Do not compare only total counts, as one existing invalid object might get fixed while a new object breaks.

### 14.3. Check Dependencies of Modified Objects

Before deploying a shared package specification or table, run the dependent-object query in Section 8.3 and save the list. Identify which application schemas hold dependent callers, plan compilation/testing, and assign owners.

### 14.4. Record Status and Errors in Operations Logs

For automated deployment pipelines, record:

- Release/build ID.
- Object owner/name/type.
- Pre- and post-deployment status.
- Error line/position/message.
- Root dependency.
- Compilation timestamp.
- Executing operator/job.

You do not need a custom table if your deployment tool or repository already captures complete history. The goal is traceability from any INVALID object back to the change that broke it.

## 15. Lab Example: Trigger Errors, Read Errors, Fix, and Recompile

Practice in a dedicated lab schema.

### 15.1. Create Valid Table and View

~~~sql
CREATE TABLE lab_departments (
    department_id NUMBER PRIMARY KEY,
    department_name VARCHAR2(80) NOT NULL
);

INSERT INTO lab_departments VALUES (10, 'Engineering');
COMMIT;

CREATE OR REPLACE VIEW lab_department_v AS
SELECT department_id, department_name
FROM lab_departments;
~~~

Verify:

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name = 'LAB_DEPARTMENT_V';
~~~

### 15.2. Create a Procedure Depending on the View

~~~sql
CREATE OR REPLACE PROCEDURE lab_show_department (
    p_department_id IN NUMBER
) AS
    l_name lab_department_v.department_name%TYPE;
BEGIN
    SELECT department_name
    INTO l_name
    FROM lab_department_v
    WHERE department_id = p_department_id;

    DBMS_OUTPUT.PUT_LINE(l_name);
END;
/
~~~

Check dependencies:

~~~sql
SELECT
    name,
    type,
    referenced_owner,
    referenced_name,
    referenced_type
FROM user_dependencies
WHERE name = 'LAB_SHOW_DEPARTMENT'
ORDER BY referenced_owner, referenced_type, referenced_name;
~~~

The procedure references the view; the view references the table. Dependency graphs reveal multi-level relationships.

### 15.3. Invalidate the View via a Dependency Change

Rename the column referenced by the view:

~~~sql
ALTER TABLE lab_departments
RENAME COLUMN department_name TO department_label;
~~~

Check:

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN (
    'LAB_DEPARTMENT_V',
    'LAB_SHOW_DEPARTMENT'
)
ORDER BY object_type, object_name;
~~~

Exact dependent object statuses can update per your release's dependency/revalidation behavior. Rely on observed results rather than assuming all objects immediately flip to INVALID at the exact same instant.

### 15.4. Read Errors

~~~sql
SELECT name, type, sequence, line, position, text
FROM user_errors
WHERE name IN ('LAB_DEPARTMENT_V', 'LAB_SHOW_DEPARTMENT')
ORDER BY name, type, sequence;
~~~

Errors will show the view can no longer find DEPARTMENT_NAME; the procedure depending on the view may also need revalidation.

### 15.5. Fix the View and Compile Dependents

~~~sql
CREATE OR REPLACE VIEW lab_department_v AS
SELECT department_id, department_label AS department_name
FROM lab_departments;

ALTER PROCEDURE lab_show_department COMPILE;
~~~

Verify again:

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN (
    'LAB_DEPARTMENT_V',
    'LAB_SHOW_DEPARTMENT'
)
ORDER BY object_type, object_name;

SELECT name, type, line, position, text
FROM user_errors
WHERE name IN ('LAB_DEPARTMENT_V', 'LAB_SHOW_DEPARTMENT')
ORDER BY name, type, sequence;
~~~

Once both the view and procedure are VALID, test execution:

~~~sql
SET SERVEROUTPUT ON;
EXEC lab_show_department(10);
~~~

SET SERVEROUTPUT ON is a client command in SQL*Plus/SQLcl. If your tool does not support it, invoke the procedure via your tool's supported mechanism and verify output.

## 16. Controlled Schema Changes

When a shared table is about to alter columns or a package spec is about to change signatures, deploy in sequence:

1. List direct and indirect dependent objects.
2. Identify cross-schema callers via DBA_DEPENDENCIES, application source, and job metadata.
3. Assess whether the change is backward compatible.
4. Prepare updated DDL and source for dependent objects.
5. Deploy prerequisites/interfaces in proper order.
6. Compile and inspect errors.
7. Run smoke/integration tests for critical callers.
8. Compare pre- and post-deployment INVALID lists.
9. Close the release only when critical objects are VALID and business tests pass.

Oracle DDL performs implicit commits before/after DDL statements. Never treat a sequence of ALTER/CREATE OR REPLACE statements as an all-or-nothing rollbackable DML transaction. Maintain backups/source control and compensating rollback DDL plans.

## 17. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Object INVALID without knowing why | Checked OBJECTS only, skipped ERRORS | Query USER_ERRORS/ALL_ERRORS/DBA_ERRORS |
| Package shows two statuses | PACKAGE and PACKAGE BODY are separate object types | Check both spec and body |
| Recompiled yet still INVALID | Source/dependency/privilege remains unfixed | Read latest errors, fix root cause first |
| Stored procedure cannot see table via role | Definer-rights unit needs direct object grants to owner | Grant directly on object, recompile |
| Synonym exists yet compilation fails | Synonyms do not grant privileges and may point to wrong target | Check ALL_SYNONYMS and target privileges |
| Querying only USER_DEPENDENCIES misses callers | Callers reside in other schemas | Query DBA_DEPENDENCIES if privileged |
| Table change invalidates many objects | Dependencies impacted by DDL | Build dependency impact list, compile prerequisites first |
| Repeated schema compile fails to fix errors | Root cause still persists | Fix interface, source, privileges, or referenced objects |
| Dynamic SQL absent from dependency views | Object name resolved at runtime | Search source, job metadata, and application code |
| VALID yet fails at runtime | Compilation does not validate all data/runtime paths | Check runtime privileges, dynamic SQL, DB links, and data |
| Wrong compile syntax for object type | Each object type has specific DDL | Consult SQL Language Reference for your release |
| Parallel recompilation overloads system | Concurrent compiles consume CPU/I/O | Run in maintenance window and cap parallelism |

## 18. Practice Exercises

Use the lab schema from Section 15.

### Exercise 1 — List INVALID Objects

Create a procedure containing a compile error. Use USER_OBJECTS to locate the INVALID object and explain why the object still exists in the data dictionary.

### Exercise 2 — Read Compile Errors

Use USER_ERRORS to retrieve line, position, text, and sequence. Compare with SHOW ERRORS in SQL*Plus/SQLcl.

### Exercise 3 — Fix Dependencies

Create a view referencing a table, then a procedure referencing the view. Rename a column in the table and observe which objects require revalidation. Fix the view and compile the procedure.

### Exercise 4 — Bidirectional Dependencies

Use USER_DEPENDENCIES to answer: Which objects does the procedure depend on? Then find which objects depend on the view. Sketch the graph in dependent → referenced direction.

### Exercise 5 — Cross-Schema Dependencies

Simulate separate data owner and application owner schemas. Grant direct privileges to the app owner, create a definer-rights procedure referencing the data table, then revoke the grant and observe compile/execute errors. Re-grant the right privilege and compile.

### Exercise 6 — Package Specification and Body

Create a package with one public procedure and one caller. Change the signature in the specification and observe dependent callers. Next, edit only the body while keeping the interface intact, and compare the impact.

### Exercise 7 — Compile Schema

Create several INVALID objects in the lab schema, run DBMS_UTILITY.COMPILE_SCHEMA with COMPILE_ALL => FALSE, then inspect status and errors. Never run bulk recompilation on production schemas for experimentation.

### Exercise 8 — Conduct Impact Analysis

Pick a shared table or package. Query direct dependents, trace multi-level dependencies, and list cross-schema objects. Propose a deployment, compilation, and testing order.

## 19. Clean Up Lab Data

Run only in the lab schema you created, after completing exercises:

~~~sql
DROP PROCEDURE lab_show_department;
DROP VIEW lab_department_v;
DROP TABLE lab_departments PURGE;
~~~

Drop dependent objects before prerequisites to avoid leaving objects pointing at dropped targets. PURGE bypasses the recycle bin; never use it on business objects or data that might need recovery.

## Summary

INVALID is a status requiring investigation, not a root cause. Start with USER_OBJECTS/ALL_OBJECTS/DBA_OBJECTS, then read USER_ERRORS/ALL_ERRORS/DBA_ERRORS for error lines and message types. Fix source code, referenced objects, or direct privileges before recompiling the appropriate object type; for packages, verify both specification and body.

Dependency views show which objects depend on which: NAME/TYPE is the dependent, REFERENCED_OWNER/NAME/TYPE is the prerequisite. Use bidirectional and multi-level dependency checks to assess impact prior to deployment, while supplementing with searches for dynamic SQL, jobs, and application code because metadata does not capture every runtime relationship. After compiling, verify status, errors, and business execution paths. Bulk recompilation should run only after root dependencies are fixed and within an appropriate operational window.

## Oracle Reference Documentation

- [Oracle Database Reference — USER_OBJECTS (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_OBJECTS.html) — object status in the current schema.
- [Oracle Database Reference — DBA_OBJECTS (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_OBJECTS.html) — database-wide object metadata.
- [Oracle Database Reference — USER_ERRORS (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_ERRORS.html) — compile diagnostics.
- [Oracle Database Reference — DBA_DEPENDENCIES (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_DEPENDENCIES.html) — dependencies among schema objects.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_UTILITY (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_UTILITY.html) — COMPILE_SCHEMA.
- [Oracle Database PL/SQL Packages and Types Reference — UTL_RECOMP (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/UTL_RECOMP.html) — recompilation utilities.
- [Oracle Database PL/SQL Language Reference — Invoker's Rights and Definer's Rights (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/invokers-rights-and-definers-rights-authid-property.html) — PL/SQL execution rights.

When operating on Oracle releases other than 19c, consult the SQL Language Reference, PL/SQL Language Reference, and Database Reference for your exact version—particularly compile syntax per object type, dependency invalidation, and recompilation utility privileges.
