# Object dependencies, signature changes, and recompilation in Oracle

A procedure can call another package, a package can query a view, and a view depends on a table. When an object changes, objects that use it may need to be recompiled. If that change makes a procedure or package signature incompatible, callers may fail to compile or fail at runtime. Therefore, modifying an object in Oracle is not just running a DDL statement; you must understand the dependency graph, impact scope, and deployment order.

Oracle stores dependency information among schema objects in the data dictionary. Dependencies help the database know which objects need to be checked or marked INVALID when an underlying object changes. PL/SQL stored units can be automatically recompiled when invoked after becoming invalid, or a DBA/developer can proactively compile them in the proper order. However, successful compilation only confirms that the current code compiles against current dependencies; it does not prove that business logic remains compatible with every caller.

This lesson belongs to the **Procedures and packages** group of Database Engine Relational Oracle. It focuses on dependencies among procedures, functions, package specifications/bodies, views, tables, types, and synonyms; the impact of signature changes; VALID/INVALID states; recompilation; error diagnosis; and safe change deployment workflows.

After this lesson, you will be able to:

- Explain direct and transitive dependencies between schema objects.
- Distinguish package specification from package body in terms of role and impact scope.
- Identify procedure/function signature changes that can break callers.
- Understand why changes to tables, views, types, or privileges can make stored objects INVALID.
- Inspect dependencies using USER_DEPENDENCIES/ALL_DEPENDENCIES.
- Check object status and compile errors using USER_OBJECTS/USER_ERRORS.
- Proactively compile procedures, functions, packages, package bodies, and views.
- Recompile a schema appropriately with administrative privileges.
- Recognize dependency-tracking limitations with dynamic SQL.
- Sequence migrations and handle package state when changing code.
- Design stable PL/SQL APIs to reduce impact when deploying new versions.

> **Example scope:** Syntax follows Oracle Database 19c. Objects with the `_LAB` suffix are intended for practice schemas. DDL in Oracle performs an implicit commit per database rules; plan migrations carefully and do not run examples on live business schemas.

## 1. What is an object dependency?

One object depends on another when its definition or body references that object. Example:

~~~text
TABLE EMPLOYEE
    |
    v
VIEW V_EMPLOYEE_DIRECTORY
    |
    v
PACKAGE EMPLOYEE_API
    |
    v
PROCEDURE HR_SERVICE
~~~

In the diagram, the view reads the EMPLOYEE table; the package uses the view; the procedure calls the package. If the table changes in a way that affects the view, the impact can propagate upward through dependent objects.

### 1.1. Direct dependency

Procedure querying a table:

~~~sql
CREATE OR REPLACE PROCEDURE show_employee_lab (
    p_employee_id IN NUMBER
) AS
    l_name employee_data_lab.full_name%TYPE;
BEGIN
    SELECT full_name
    INTO l_name
    FROM employee_data_lab
    WHERE employee_id = p_employee_id;

    DBMS_OUTPUT.PUT_LINE(l_name);
END;
/
~~~

SHOW_EMPLOYEE_LAB has a direct dependency on EMPLOYEE_DATA_LAB because its body references the table and its columns.

### 1.2. Transitive dependency

A procedure calls a package, the package reads a view, and the view reads a table:

~~~text
HR_SERVICE
   |
   v
EMPLOYEE_API
   |
   v
V_EMPLOYEE_DIRECTORY
   |
   v
EMPLOYEE_DATA
~~~

HR_SERVICE has a direct dependency on EMPLOYEE_API. It depends indirectly on the view and table through the object chain. When an underlying dependency changes, Oracle may mark certain dependent objects for recompilation depending on dependency rules and the degree of change.

### 1.3. Dependencies are relationships between objects, not a single runtime call

A stored procedure can depend on:

- Tables, views, materialized views.
- Sequences.
- Synonyms resolved to target objects.
- Package specifications, packages, procedures, or functions.
- SQL object types, collection types.
- Other objects referenced in its definition.

Dependencies are recorded when the compiler analyzes static references. An object name appearing only inside a dynamic SQL string is not checked in the same way at compile time.

## 2. Dependency graph and impact scope

### 2.1. One change can affect many objects

Suppose a package spec is used by multiple other packages:

~~~text
                PACKAGE CUSTOMER_API SPEC
                    /       |       \
                   v        v        v
              ORDER_API   BILLING_API  REPORT_API
                  |          |           |
                  v          v           v
              ORDER_SVC   BILLING_SVC  REPORT_JOB
~~~

Changing CUSTOMER_API's public declarations can turn directly dependent packages INVALID. Further downstream dependent objects may also need recompilation. Therefore, before modifying a shared API, map out the dependency graph and consumer scope.

### 2.2. Changes do not always invalidate the entire schema

Oracle tracks dependencies at the object level and, for many PL/SQL/SQL reference types, has fine-grained dependency tracking. A change unrelated to the elements a dependent object uses may not invalidate all dependents. Exact outcomes depend on object type, change type, release, and dependency metadata.

Avoid both extreme assumptions:

- Every ALTER TABLE invalidates every procedure in the schema.
- Table changes never affect procedures.

Always inspect actual object status after a migration.

### 2.3. Dependency graphs can span multiple layers and multiple schemas

USER_DEPENDENCIES only shows dependencies owned by the current user. When an application spans multiple schemas, use ALL_DEPENDENCIES or DBA_DEPENDENCIES with appropriate privileges for a wider view. Account for underlying object owners, synonyms, packages, and views.

### 2.4. An INVALID object does not mean corrupted data

INVALID is a status indicating the object needs recompilation or revalidation. It does not mean table data is lost or altered. However, if the application invokes an INVALID object whose automatic recompilation fails, functionality depending on that object cannot run.

## 3. Package specification and package body

A package has two parts with distinct roles:

- **Specification (spec):** the public contract, declaring types, constants, variables, cursors, exceptions, procedures, and functions that callers are allowed to use.
- **Body:** implementations of subprograms, cursor bodies, private declarations, and internal logic.

### 3.1. Package specification

~~~sql
CREATE OR REPLACE PACKAGE employee_api_lab AS
    PROCEDURE get_employee_name (
        p_employee_id IN NUMBER,
        p_full_name OUT VARCHAR2
    );

    FUNCTION employee_count
        RETURN NUMBER;
END employee_api_lab;
/
~~~

Callers compile against the public declarations in the spec. This is the contract the package provides to other stored objects and calling code.

### 3.2. Package body

~~~sql
CREATE OR REPLACE PACKAGE BODY employee_api_lab AS
    PROCEDURE get_employee_name (
        p_employee_id IN NUMBER,
        p_full_name OUT VARCHAR2
    ) IS
    BEGIN
        SELECT full_name
        INTO p_full_name
        FROM employee_data_lab
        WHERE employee_id = p_employee_id;
    END get_employee_name;

    FUNCTION employee_count
        RETURN NUMBER
    IS
        l_count NUMBER;
    BEGIN
        SELECT COUNT(*)
        INTO l_count
        FROM employee_data_lab;

        RETURN l_count;
    END employee_count;
END employee_api_lab;
/
~~~

The body holds the implementation. If only internal calculation logic changes while the public spec stays unchanged, callers usually do not need to recompile just because the implementation changed. However, the body must compile cleanly and sessions holding package state can still be affected when the package is replaced.

### 3.3. Modifying the spec has a wider impact than modifying the body

| Change | Typical impact |
| --- | --- |
| Modifying only SQL or logic in the body | Package body needs compilation; public contract unchanged |
| Adding a private helper in the body | Body changes; callers do not know about the helper |
| Changing a public procedure's parameters in the spec | Callers depending on the signature may become INVALID or fail to compile |
| Changing a public type in the spec | Objects using the type may need recompilation |
| Removing a procedure/function from the spec | Callers referencing the removed API fail to compile |
| Changing constants/public declarations | Consumers depending on declarations may be affected |

This is a key design principle: keep the spec stable and evolve implementation inside the body whenever possible. When a public API must change, plan a migration for all callers.

### 3.4. The package body still depends on the spec

The body must conform to declarations in the spec. If the body lacks an implementation for a public subprogram or has a mismatched signature, the body fails to compile. When the spec is modified, the body can become INVALID and need corresponding updates.

## 4. Procedure and function signatures

A signature describes how callers interact with a subprogram. For PL/SQL procedures/functions, key elements include:

- Subprogram name.
- Number and order of parameters.
- Parameter names when callers use named notation.
- Parameter data types and subtypes.
- Parameter modes: IN, OUT, IN OUT.
- Parameter default values.
- Function return type.
- Overload resolution rules.

### 4.1. Initial signature

~~~sql
CREATE OR REPLACE PROCEDURE create_order_lab (
    p_customer_id IN NUMBER,
    p_amount IN NUMBER
) AS
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'Customer=' || p_customer_id ||
        ', amount=' || p_amount
    );
END;
/
~~~

Caller using positional notation:

~~~sql
BEGIN
    create_order_lab(501, 250);
END;
/
~~~

Caller using named notation:

~~~sql
BEGIN
    create_order_lab(
        p_customer_id => 501,
        p_amount => 250
    );
END;
/
~~~

### 4.2. Adding a required parameter

Suppose the new API adds p_currency without a default:

~~~sql
CREATE OR REPLACE PROCEDURE create_order_lab (
    p_customer_id IN NUMBER,
    p_amount IN NUMBER,
    p_currency IN VARCHAR2
) AS
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        p_customer_id || ' ' || p_amount || ' ' || p_currency
    );
END;
/
~~~

Existing callers passing only two arguments no longer match the signature. Stored callers can become INVALID and fail recompilation with parameter count/type errors. Callers outside the database must also be updated.

### 4.3. Adding a parameter with a default at the end

One way to reduce impact is adding an optional parameter at the end with a default:

~~~sql
CREATE OR REPLACE PROCEDURE create_order_lab (
    p_customer_id IN NUMBER,
    p_amount IN NUMBER,
    p_currency IN VARCHAR2 DEFAULT 'VND'
) AS
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        p_customer_id || ' ' || p_amount || ' ' || p_currency
    );
END;
/
~~~

Existing callers passing two arguments can still call the procedure and use the default for p_currency. However:

- Check all callers using positional/named notation.
- The default must fit business semantics.
- Changing the public spec can still require dependent objects to revalidate/recompile.
- External database clients, generated bindings, and integration contracts still need verification.

Default parameters are a conditional compatibility tool, not a guarantee that zero API consumers need changes.

### 4.4. Inserting a parameter in the middle endangers positional calls

If a parameter is inserted in the middle of the list, positional callers may bind old values to the wrong parameters or fail to compile. Even with a default, changing parameter order can break calls.

For widely used APIs, prefer:

- Adding optional parameters at the end when semantics fit.
- Using named notation in PL/SQL callers.
- Creating a new overload or API version for incompatible changes.
- Keeping an old wrapper procedure during transition periods.

### 4.5. Changing parameter mode

IN, OUT, and IN OUT cannot be treated as cosmetic changes:

- IN: caller provides a value for the subprogram to read.
- OUT: subprogram returns a value to the caller.
- IN OUT: subprogram receives a value and may modify and return it.

Changing IN to OUT/IN OUT can render existing callers invalid, especially when callers pass literals, expressions, or variables incompatible with OUT semantics. Check every call site and client binding.

### 4.6. Changing data type

Changing NUMBER to VARCHAR2 or altering subtype/precision can cause:

- Callers to no longer match data types.
- Overload resolution to select a different subprogram.
- Implicit conversions or runtime errors.
- Client bindings to require updates.

Do not treat implicit conversion as an API contract. Use explicit data types and tested migrations.

### 4.7. Changing function return type

Function returning NUMBER:

~~~sql
CREATE OR REPLACE FUNCTION get_credit_limit_lab (
    p_customer_id IN NUMBER
) RETURN NUMBER
AS
BEGIN
    RETURN 1000;
END;
/
~~~

Changing the return type to VARCHAR2 or a SQL object type can affect callers using the function in SQL, PL/SQL expressions, or client bindings. Return type is part of the contract.

## 5. Overloading and API changes

A package can overload procedures/functions using distinct signatures:

~~~sql
CREATE OR REPLACE PACKAGE payment_api_lab AS
    PROCEDURE pay (
        p_account_id IN NUMBER,
        p_amount IN NUMBER
    );

    PROCEDURE pay (
        p_account_id IN NUMBER,
        p_amount IN NUMBER,
        p_currency IN VARCHAR2
    );
END payment_api_lab;
/
~~~

Overloading is useful when variants have clear semantics. However, overloading can introduce ambiguity when parameter types are close or literals can convert to multiple types.

### 5.1. Overload resolution

~~~sql
BEGIN
    payment_api_lab.pay(10, 250);
    payment_api_lab.pay(10, 250, 'VND');
END;
/
~~~

When adding an overload, check whether existing calls can become ambiguous or resolve to a different overload. Calls passing NULL literals, untyped numbers, or strings may need explicit types.

### 5.2. Using named notation

~~~sql
BEGIN
    payment_api_lab.pay(
        p_account_id => 10,
        p_amount => 250,
        p_currency => 'VND'
    );
END;
/
~~~

Named notation clarifies parameter meaning and reduces argument-order mistakes. It does not eliminate issues when renaming public parameters, because parameter names are part of the named-call contract.

### 5.3. Do not overload just to avoid versioning

If two variants have significantly different semantics, separate API names can be clearer:

- CREATE_ORDER_V1 and CREATE_ORDER_V2 during a transition period.
- CREATE_ORDER with a versioned request record.
- Separate API packages by domain or version.

Overloading should be used when variants genuinely represent the same operation with different parameter sets.

## 6. How table, view, and type changes affect PL/SQL

### 6.1. Procedures depending on table columns

~~~sql
CREATE OR REPLACE PROCEDURE read_salary_lab (
    p_employee_id IN NUMBER,
    p_salary OUT NUMBER
) AS
BEGIN
    SELECT monthly_salary
    INTO p_salary
    FROM employee_data_lab
    WHERE employee_id = p_employee_id;
END;
/
~~~

The procedure depends on the table and the MONTHLY_SALARY column. If the column is dropped or renamed, the procedure cannot compile with the old SQL statement.

### 6.2. %TYPE creates a dependency on the source data type

~~~sql
CREATE OR REPLACE PROCEDURE update_employee_email_lab (
    p_employee_id IN employee_data_lab.employee_id%TYPE,
    p_email IN employee_data_lab.work_email%TYPE
) AS
BEGIN
    UPDATE employee_data_lab
    SET work_email = p_email
    WHERE employee_id = p_employee_id;
END;
/
~~~

%TYPE keeps PL/SQL data types aligned with columns. If the source data type changes, the stored unit may need revalidation/recompilation and callers must check compatibility.

### 6.3. %ROWTYPE depends on row structure

~~~sql
DECLARE
    l_employee employee_data_lab%ROWTYPE;
BEGIN
    SELECT *
    INTO l_employee
    FROM employee_data_lab
    WHERE employee_id = 101;
END;
/
~~~

%ROWTYPE binds to the row shape of a table/view. Adding, dropping, or altering columns can affect units using rowtype and corresponding SELECT statements. Use %ROWTYPE when the full row is needed; use an explicit record when the contract should include only a fixed subset of fields.

### 6.4. View changes

A procedure querying a view depends on the columns exposed by the view. If CREATE OR REPLACE VIEW renames a column, drops a column, or changes a data type, procedures using the view can become INVALID or fail to compile. If only the predicate changes while the schema stays identical, code may still compile yet data semantics change; business testing is required.

### 6.5. SQL object type changes

Packages/procedures can use SQL object types or collection types in parameters. Altering a type specification can affect dependent objects. For object types with attributes/methods, type changes must be managed as contract changes, especially when the type is used in tables or cross-schema interfaces.

### 6.6. Adding a column does not always invalidate every dependent

Oracle uses fine-grained dependency tracking to avoid unnecessary invalidations during certain changes. For instance, a procedure referencing only two specific columns does not necessarily become invalid just because an unrelated column is added to the table. However, objects using %ROWTYPE or SELECT * have a broader dependency on row shape.

Do not guess the invalidation scope. Inspect USER_OBJECTS after DDL and compile/test related objects.

## 7. Static SQL and dynamic SQL in dependency tracking

### 7.1. Static SQL

~~~sql
CREATE OR REPLACE PROCEDURE get_employee_static_lab (
    p_id IN NUMBER
) AS
    l_name VARCHAR2(80);
BEGIN
    SELECT full_name
    INTO l_name
    FROM employee_data_lab
    WHERE employee_id = p_id;
END;
/
~~~

The compiler analyzes table/column names in static SQL and records appropriate dependencies. If an underlying object changes in a way that breaks the SQL, the stored unit can become invalid or fail recompilation.

### 7.2. Dynamic SQL

~~~sql
CREATE OR REPLACE PROCEDURE get_employee_dynamic_lab (
    p_table_name IN VARCHAR2,
    p_id IN NUMBER,
    p_name OUT VARCHAR2
) AS
BEGIN
    EXECUTE IMMEDIATE
        'SELECT full_name FROM ' || p_table_name ||
        ' WHERE employee_id = :x'
        INTO p_name
        USING p_id;
END;
/
~~~

The table name lives inside a string at runtime. The compiler cannot fully verify object names inside strings as it does for static SQL. Consequently, the dependency dictionary may not reflect every object dynamic SQL accesses.

This means:

- A procedure compiling cleanly does not prove every dynamic SQL path is valid.
- Renaming/dropping a table referenced in a string may only surface errors when that runtime branch is called.
- Tests must cover actual object names and dynamic SQL branches.
- Inputs used as identifiers must be strictly controlled; bind variables bind values only, not table/column names.

### 7.3. Do not concatenate arbitrary input into dynamic SQL

Never use user input directly as an object name or SQL fragment:

~~~sql
-- Unsafe if p_table_name comes from untrusted input.
EXECUTE IMMEDIATE
    'SELECT COUNT(*) FROM ' || p_table_name;
~~~

If a table must be selected by business logic, use an allowlist of valid names, schema qualification, and DBMS_ASSERT for appropriate identifiers. Bind values instead of concatenating values into strings:

~~~sql
EXECUTE IMMEDIATE
    'SELECT COUNT(*) FROM employee_data_lab WHERE department_id = :d'
INTO l_count
USING p_department_id;
~~~

DBMS_ASSERT helps validate certain identifier/literal forms; it does not replace authorization or business allowlists.

### 7.4. Synonyms and unqualified names

If code references a name without a schema prefix, Oracle may resolve it to an object in the current schema or a synonym. When a synonym's target changes, query meaning can change. For predictable migrations, consider schema-qualifying critical dependencies and controlling synonym grants/targets.

## 8. VALID and INVALID status

Oracle stores object status in the data dictionary. For stored PL/SQL units, views, and several schema objects, status is typically VALID or INVALID.

### 8.1. Viewing objects in the current schema

~~~sql
SELECT
    object_name,
    object_type,
    status,
    last_ddl_time
FROM user_objects
WHERE object_type IN (
    'PROCEDURE',
    'FUNCTION',
    'PACKAGE',
    'PACKAGE BODY',
    'VIEW',
    'TRIGGER'
)
ORDER BY object_type, object_name;
~~~

VALID means the object compiled/validated successfully against current state. INVALID means the object needs recompilation or has a dependency/definition error.

### 8.2. Viewing invalid objects in the schema

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE status = 'INVALID'
ORDER BY object_type, object_name;
~~~

Across multiple schemas, a DBA can use DBA_OBJECTS or ALL_OBJECTS depending on privileges.

### 8.3. Viewing compile errors

~~~sql
SELECT
    name,
    type,
    sequence,
    line,
    position,
    text
FROM user_errors
ORDER BY name, type, sequence;
~~~

USER_ERRORS contains compilation errors for objects in the current schema. ALL_ERRORS/DBA_ERRORS provide broader scope with appropriate privileges. Compile errors usually indicate line/position; inspect the exact source line to fix the root cause.

### 8.4. SHOW ERRORS

In SQL*Plus or tools supporting equivalent commands:

~~~sql
SHOW ERRORS PROCEDURE show_employee_lab
SHOW ERRORS PACKAGE employee_api_lab
SHOW ERRORS PACKAGE BODY employee_api_lab
~~~

SHOW ERRORS is convenient interactively. USER_ERRORS is better when querying errors with SQL or integrating into deployment reports.

## 9. Viewing dependencies via the data dictionary

### 9.1. USER_DEPENDENCIES

View which objects the current schema's objects depend on:

~~~sql
SELECT
    name,
    type,
    referenced_owner,
    referenced_name,
    referenced_type,
    dependency_type
FROM user_dependencies
ORDER BY name, referenced_owner, referenced_name;
~~~

Key columns:

- NAME/TYPE: the dependent object.
- REFERENCED_OWNER: schema of the referenced object.
- REFERENCED_NAME/TYPE: name and type of the referenced object.
- DEPENDENCY_TYPE: dependency type per dictionary.

### 9.2. Finding objects that depend on a package

~~~sql
SELECT
    name,
    type,
    referenced_owner,
    referenced_name,
    referenced_type
FROM all_dependencies
WHERE referenced_name = 'EMPLOYEE_API_LAB'
  AND referenced_type IN ('PACKAGE', 'PACKAGE BODY')
ORDER BY owner, name, type;
~~~

ALL_DEPENDENCIES includes OWNER; when querying within the current schema, USER_DEPENDENCIES can be simpler. Use uppercase package names per dictionary convention unless the object was created with quoted identifiers.

### 9.3. Finding dependencies by underlying object

~~~sql
SELECT
    name,
    type,
    referenced_owner,
    referenced_name,
    referenced_type
FROM user_dependencies
WHERE referenced_name = 'EMPLOYEE_DATA_LAB'
ORDER BY type, name;
~~~

Results help identify stored objects/views directly depending on a table.

### 9.4. Dependencies are not a complete runtime call graph

Dictionary dependencies are not a profiler. They do not show:

- Which objects are called most frequently.
- Which dynamic SQL branches actually execute.
- Which external database callers invoke a procedure.
- Which client code uses positional parameter binding.
- Which objects are only invoked via reflection/frameworks.

To build a complete map, combine dependency metadata, source searches, application repositories, SQL monitoring, and runtime logs.

### 9.5. Viewing stored object source

~~~sql
SELECT line, text
FROM user_source
WHERE name = 'EMPLOYEE_API_LAB'
  AND type IN ('PACKAGE', 'PACKAGE BODY')
ORDER BY type, line;
~~~

USER_SOURCE shows currently stored PL/SQL source. For package specs/bodies, filter by the appropriate TYPE. ALL_SOURCE/DBA_SOURCE cover wider scopes per privileges.

## 10. Recompiling objects

When an object is INVALID, it can be compiled manually once dependencies are valid.

### 10.1. Compile procedure

~~~sql
ALTER PROCEDURE show_employee_lab COMPILE;
~~~

### 10.2. Compile function

~~~sql
ALTER FUNCTION get_credit_limit_lab COMPILE;
~~~

### 10.3. Compile package specification

~~~sql
ALTER PACKAGE employee_api_lab COMPILE SPECIFICATION;
~~~

You can use ALTER PACKAGE ... COMPILE to compile the package per supported syntax. When targeting only the body:

~~~sql
ALTER PACKAGE employee_api_lab COMPILE BODY;
~~~

### 10.4. Compile view

~~~sql
ALTER VIEW v_employee_directory_lab COMPILE;
~~~

If a view remains INVALID because a column/table is missing or privileges are invalid, recompiling will not repair the definition. Fix the dependency or view query first.

### 10.5. Compile trigger

~~~sql
ALTER TRIGGER trg_employee_audit_lab COMPILE;
~~~

Triggers can depend on table columns, packages, sequences, and other objects. Check USER_ERRORS after compiling.

### 10.6. Always verify after compiling

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN (
    'SHOW_EMPLOYEE_LAB',
    'EMPLOYEE_API_LAB',
    'V_EMPLOYEE_DIRECTORY_LAB'
)
ORDER BY object_type, object_name;

SELECT name, type, line, position, text
FROM user_errors
ORDER BY name, type, sequence;
~~~

Do not treat ALTER ... COMPILE returning without immediate error as sole proof. Always check object status and compile errors.

## 11. Automatic recompilation and first invocation

When an INVALID stored object is referenced, Oracle can automatically attempt to recompile it. If all required dependencies are valid and privileges are intact, the object can return to VALID and the call proceeds.

### 11.1. Automatic revalidation does not guarantee success

If:

- A column was dropped/renamed.
- A called procedure changed signature.
- A type is no longer compatible.
- A view cannot compile.
- Direct privileges on an underlying object were revoked.
- Package spec and body do not match.

then automatic compilation can fail and the caller receives an error.

### 11.2. Can introduce latency on the first call

If the system waits until the application calls an INVALID object to recompile it, the first request after deployment may incur extra compilation time or fail. For critical systems, proactively compiling and verifying all objects during the deployment window helps catch errors before live traffic arrives.

### 11.3. No need to blindly recompile the entire schema after every change

Recompiling every object after every small DDL can add unnecessary load and obscure root errors. Instead:

1. Identify affected dependencies.
2. Fix underlying objects first.
3. Compile in dependency order.
4. Inspect any remaining invalid objects.
5. Run smoke tests on affected APIs.

For large schemas or multi-object migrations, DBAs can use planned schema recompilation tools.

## 12. Recompiling a schema and multiple objects

### 12.1. DBMS_UTILITY.COMPILE_SCHEMA

DBMS_UTILITY provides COMPILE_SCHEMA to compile stored objects in a schema:

~~~sql
BEGIN
    DBMS_UTILITY.COMPILE_SCHEMA(
        schema => 'APP_OWNER',
        compile_all => FALSE
    );
END;
/
~~~

COMPILE_ALL = FALSE generally compiles only INVALID objects; TRUE requests compiling all eligible objects. Package execution privileges and schema scope depend on the user. Run during maintenance/deployment windows when a schema has many objects.

### 12.2. UTL_RECOMP

UTL_RECOMP supports recompiling invalid objects serially or in parallel for administrative use:

~~~sql
BEGIN
    UTL_RECOMP.RECOMP_SERIAL('APP_OWNER');
END;
/
~~~

Or a DBA may consider RECOMP_PARALLEL per the release's package documentation and system resources. UTL_RECOMP typically requires appropriate administrative privileges and should not be called casually from application runtime.

### 12.3. Parallel compilation is not always better

Parallel recompilation can shorten duration on large schemas, yet consumes CPU, memory, and I/O. If dependencies are still missing or source errors remain unfixed, parallel compilation merely makes many objects fail together. Fix the root cause first.

### 12.4. Checking before and after

Before:

~~~sql
SELECT owner, object_type, COUNT(*) AS invalid_count
FROM dba_objects
WHERE status = 'INVALID'
GROUP BY owner, object_type
ORDER BY owner, object_type;
~~~

After:

~~~sql
SELECT owner, object_name, object_type, status
FROM dba_objects
WHERE owner = 'APP_OWNER'
  AND status = 'INVALID'
ORDER BY object_type, object_name;
~~~

DBA_OBJECTS requires appropriate dictionary privileges. Without DBA privileges, use USER_OBJECTS or ALL_OBJECTS within permitted scope.

## 13. Direct privileges and dependencies during compilation

Stored PL/SQL runs with privileges determined by AUTHID and corresponding privilege rules. Specifically for definer-rights stored units (the default), role grants do not substitute for direct object grants when compiling/resolving static SQL inside stored code.

### 13.1. Cross-schema example

DATA_OWNER owns the table:

~~~sql
CREATE TABLE employee_data_lab (
    employee_id NUMBER PRIMARY KEY,
    full_name VARCHAR2(80)
);
~~~

APP_OWNER needs access to the table:

~~~sql
GRANT SELECT ON employee_data_lab TO app_owner;
~~~

Then APP_OWNER creates the procedure:

~~~sql
CREATE OR REPLACE PROCEDURE app_read_employee_lab (
    p_id IN NUMBER,
    p_name OUT VARCHAR2
) AS
BEGIN
    SELECT full_name
    INTO p_name
    FROM data_owner.employee_data_lab
    WHERE employee_id = p_id;
END;
/
~~~

If SELECT is granted to APP_OWNER only through a role, compiling the definer-rights stored procedure may fail. Grant direct privileges on underlying objects to the stored unit's owner following least privilege.

### 13.2. Revoking privileges can prevent objects from compiling

If DATA_OWNER revokes SELECT:

~~~sql
REVOKE SELECT ON employee_data_lab FROM app_owner;
~~~

Procedures depending on the table can become invalid or fail to revalidate/compile. When troubleshooting errors, check both object dependencies and grants—do not only inspect source code.

### 13.3. AUTHID CURRENT_USER

Procedures/packages with AUTHID CURRENT_USER use the invoker-rights model. Access privileges are checked against the invoker per Oracle rules, differing from the default definer's rights. Invoker-rights design is useful for APIs that must use caller privileges, but it is not an automatic fix for missing direct grants. Clearly define the security model and test with actual users.

## 14. Synonyms and dependency resolution

A synonym is an alias for another object. Stored code can reference an object via a synonym:

~~~sql
CREATE SYNONYM employee_source_lab
FOR data_owner.employee_data_lab;
~~~

Procedure:

~~~sql
CREATE OR REPLACE PROCEDURE read_employee_syn_lab (
    p_id IN NUMBER,
    p_name OUT VARCHAR2
) AS
BEGIN
    SELECT full_name
    INTO p_name
    FROM employee_source_lab
    WHERE employee_id = p_id;
END;
/
~~~

### 14.1. Synonyms do not grant privileges

A synonym only provides an alternate name. The caller/owner still needs privileges on the target object per the security model. Creating a synonym does not automatically grant SELECT/EXECUTE.

### 14.2. Changing a synonym target

If a synonym is changed to point to another table/view, the semantics of stored code can change. Dependent objects may require revalidation; even if compilation succeeds, the new schema may have different data or constraints.

### 14.3. Use schema qualification for critical dependencies

In application stored code, explicitly referencing OWNER.OBJECT helps:

- Reduce ambiguity when private/public synonyms share names.
- Simplify dependency reviews.
- Reduce risks of target switching via search path/synonyms.
- Make cross-schema migrations clearer.

However, schema qualification does not replace privileges and does not eliminate dependencies.

## 15. Package state and errors after replacing packages

A package can hold session-scoped state if it contains public/private package variables, initialized constants, cursors, or other state. When a package is recompiled/replaced while a session already initialized package state, that session can receive a package-state error on its next call.

### 15.1. Possible errors

- ORA-04061: existing state of package has been invalidated.
- ORA-04065: not executed, altered or dropped stored procedure/package.
- ORA-04068: existing state of packages has been discarded.
- ORA-04063: package/body or object has errors.

Exact messages depend on the scenario and release.

### 15.2. Why can changing only the package body still affect sessions?

Even when the spec is unchanged and callers do not need recompilation, replacing a package body can render already-initialized package state in old sessions invalid. Oracle may discard package state so the session uses the new implementation. Applications must handle the error and may need to reinitialize package state.

### 15.3. Package state is not for persistent state

Do not use package variables as a durable data source across sessions. Package state:

- Belongs to a session.
- Can be reset when the package is invalidated/recompiled.
- Is not shared across sessions like a table.
- Can cause unpredictable behavior in connection pools if state is unmanaged.

If business state must survive across sessions or restarts, store it in tables or appropriate storage.

### 15.4. Connection pools and package state

Connection pools reuse database sessions. A session can retain package state from a prior request. If an API relies on package variables, deliberately reset/initialize state and never assume every request gets a clean session. After package deployment, test existing sessions held in the pool.

## 16. Deployment order when changing dependencies

When an API or underlying object changes, deploy in dependency order to minimize cascading invalidations.

### 16.1. General order

~~~text
1. TABLES / SEQUENCES / SQL TYPES
          |
          v
2. GRANTS / SYNONYMS
          |
          v
3. VIEWS
          |
          v
4. PACKAGE SPECIFICATIONS
          |
          v
5. PACKAGE BODIES
          |
          v
6. PROCEDURES / FUNCTIONS / TRIGGERS
          |
          v
7. RECOMPILE DEPENDENTS
          |
          v
8. SMOKE TESTS / APPLICATION CHECK
~~~

This is a general order. Real schemas may have package specs referencing other types/packages, views depending on views, or circular dependencies handled via forward declarations. Use the actual dependency graph to determine order.

### 16.2. Additive changes

Additive changes add functionality while keeping the old contract intact, such as adding a trailing parameter with a default or adding a new procedure to a package spec. These are usually less disruptive, yet still require checking:

- Did dependent objects become INVALID?
- Did overload resolution change?
- Do existing callers continue to compile/run?
- Was public package state reset?
- Do external database clients need updated bindings?

### 16.3. Breaking changes

Breaking changes include:

- Removing a procedure/function.
- Renaming a public subprogram.
- Changing data types or parameter modes.
- Changing positional parameter order.
- Changing return type.
- Changing public record/object types.
- Changing semantics of parameters or results.

For breaking changes, consider creating a new API version, compatibility wrappers, or a multi-step rollout.

### 16.4. Compatibility wrapper

Keep the old API while delegating implementation to the new API:

~~~sql
CREATE OR REPLACE PACKAGE employee_api_v2_lab AS
    PROCEDURE get_employee (
        p_employee_id IN NUMBER,
        p_include_status IN BOOLEAN,
        p_full_name OUT VARCHAR2,
        p_status OUT VARCHAR2
    );
END employee_api_v2_lab;
/
~~~

The old package keeps the old signature and calls the new API with an appropriate default:

~~~sql
CREATE OR REPLACE PACKAGE BODY employee_api_lab AS
    PROCEDURE get_employee_name (
        p_employee_id IN NUMBER,
        p_full_name OUT VARCHAR2
    ) IS
        l_status VARCHAR2(12);
    BEGIN
        employee_api_v2_lab.get_employee(
            p_employee_id => p_employee_id,
            p_include_status => FALSE,
            p_full_name => p_full_name,
            p_status => l_status
        );
    END get_employee_name;
END employee_api_lab;
/
~~~

Wrappers allow old consumers to keep working during the transition period. Once all callers have migrated, the old API can be deprecated and removed in a separate release.

## 17. Practical deployment workflow

### 17.1. Before deployment

1. List dependent objects.
2. Find callers in source repositories and application configurations.
3. Classify the change as additive or breaking.
4. Verify direct grants and synonym targets.
5. Sequence DDL and compilation steps.
6. Prepare rollback/forward-fix scripts.
7. Assess package state and connection pools.
8. Run the migration in an environment with matching release and schema shape.

### 17.2. During deployment

- Pause or coordinate traffic if changes are incompatible.
- Deploy underlying objects first.
- Update grants and synonyms.
- Create views and package specs/bodies in dependency order.
- Compile dependent stored objects.
- Check USER_OBJECTS/USER_ERRORS.
- Run smoke tests as both schema owner and application user.
- Check existing sessions if package state is significant.

### 17.3. After deployment

- Confirm no unexpected INVALID objects remain.
- Run representative queries and transactions.
- Check application logs for ORA-/PLS- errors.
- Verify old callers and new client bindings.
- Inspect new dependencies and grants.
- Record API version and migration results.

### 17.4. DDL and rollback

DDL in Oracle triggers an implicit commit. If a script contains 10 CREATE/ALTER statements and statement 8 fails, the earlier DDL statements have already committed. You cannot wrap an entire DDL migration in one transaction and ROLLBACK like DML.

Prepare:

- Forward-fix scripts or corresponding reverse DDL.
- Backups/version control of DDL prior to changes.
- Application compatibility plans during rollout.
- Verification steps after each stage.

Avoid casual DROP/CREATE when CREATE OR REPLACE or ALTER is suitable; DROP can lose grants, break synonym references, or create a window where the object does not exist.

## 18. Lab example: changing a signature and recompiling dependent objects

This lab demonstrates dependencies between a package and a procedure calling it. Run in an isolated schema.

### 18.1. Create the initial package version

~~~sql
CREATE OR REPLACE PACKAGE employee_api_sig_lab AS
    PROCEDURE get_name (
        p_employee_id IN NUMBER,
        p_name OUT VARCHAR2
    );
END employee_api_sig_lab;
/

CREATE OR REPLACE PACKAGE BODY employee_api_sig_lab AS
    PROCEDURE get_name (
        p_employee_id IN NUMBER,
        p_name OUT VARCHAR2
    ) IS
    BEGIN
        SELECT full_name
        INTO p_name
        FROM employee_data_lab
        WHERE employee_id = p_employee_id;
    END get_name;
END employee_api_sig_lab;
/
~~~

### 18.2. Create the dependent caller

~~~sql
CREATE OR REPLACE PROCEDURE caller_sig_lab (
    p_employee_id IN NUMBER
) AS
    l_name VARCHAR2(80);
BEGIN
    employee_api_sig_lab.get_name(
        p_employee_id => p_employee_id,
        p_name => l_name
    );

    DBMS_OUTPUT.PUT_LINE(l_name);
END;
/
~~~

The caller depends on the public signature of EMPLOYEE_API_SIG_LAB.

### 18.3. Inspect dependencies

~~~sql
SELECT
    name,
    type,
    referenced_name,
    referenced_type
FROM user_dependencies
WHERE referenced_name = 'EMPLOYEE_API_SIG_LAB'
ORDER BY name, type;
~~~

### 18.4. Make a breaking signature change

Add a required parameter:

~~~sql
CREATE OR REPLACE PACKAGE employee_api_sig_lab AS
    PROCEDURE get_name (
        p_employee_id IN NUMBER,
        p_language IN VARCHAR2,
        p_name OUT VARCHAR2
    );
END employee_api_sig_lab;
/
~~~

The body must be updated to match the spec. The old caller still passes two arguments and can no longer compile.

~~~sql
CREATE OR REPLACE PACKAGE BODY employee_api_sig_lab AS
    PROCEDURE get_name (
        p_employee_id IN NUMBER,
        p_language IN VARCHAR2,
        p_name OUT VARCHAR2
    ) IS
    BEGIN
        SELECT full_name
        INTO p_name
        FROM employee_data_lab
        WHERE employee_id = p_employee_id;
    END get_name;
END employee_api_sig_lab;
/
~~~

### 18.5. Check caller status and errors

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN (
    'EMPLOYEE_API_SIG_LAB',
    'CALLER_SIG_LAB'
)
ORDER BY object_type;

SELECT name, type, line, position, text
FROM user_errors
WHERE name = 'CALLER_SIG_LAB'
ORDER BY sequence;
~~~

### 18.6. Fix the caller

~~~sql
CREATE OR REPLACE PROCEDURE caller_sig_lab (
    p_employee_id IN NUMBER
) AS
    l_name VARCHAR2(80);
BEGIN
    employee_api_sig_lab.get_name(
        p_employee_id => p_employee_id,
        p_language => 'VI',
        p_name => l_name
    );

    DBMS_OUTPUT.PUT_LINE(l_name);
END;
/
~~~

After fixing the caller, re-check status and errors, then invoke the procedure with a valid employee_id.

### 18.7. Compare with a default parameter

In another design, adding p_language at the end with DEFAULT 'VI' can preserve two-argument callers. This is a less disruptive API change, though you still must compile/test dependencies and verify default semantics.

### 18.8. Clean up lab (optional)

Run only if you are sure these are lab objects you created:

~~~sql
DROP PROCEDURE caller_sig_lab;
DROP PACKAGE employee_api_sig_lab;
~~~

DROP is DDL and performs an implicit commit. Never run on live business objects.

## 19. Common errors

| Error/symptom | Common cause | Resolution |
| --- | --- | --- |
| PLS-00306 wrong number or types of arguments | Caller does not match the new signature | Update call site, add overload, or add compatibility wrapper |
| PLS-00302 component must be declared | Public member was removed/renamed or is missing from spec | Update caller or restore API |
| PLS-00905 object is invalid | Referenced object is INVALID | Check USER_ERRORS and compile dependency first |
| ORA-04063 has errors | Package/view/procedure has compile errors | Query USER_ERRORS/ALL_ERRORS and fix source |
| ORA-04061 package state invalidated | Package changed while session held state | Handle session/package state, reinitialize per design |
| ORA-04068 package state discarded | Oracle discarded initialized package state | Application handles error, reinitializes request/session state |
| ORA-00942 table or view does not exist | Object does not exist, wrong synonym, or missing privilege | Check owner, object name, and direct grants |
| PLS-00201 identifier must be declared | Object/type/procedure name cannot be resolved or missing privilege | Check spec, schema qualification, synonyms, and grants |
| Object remains INVALID after COMPILE | Underlying dependency is still wrong or compile error persists | Fix root cause first, then recompile |
| Dynamic SQL fails even though procedure is VALID | Object name in string was not fully checked at compile time | Test runtime paths and validate identifiers |
| External DB caller fails after deployment | Client binding/contract was not updated | Check JDBC/OCI/ORM/generated APIs and versioning |

## 20. Common misconceptions

| Misconception | Reality |
| --- | --- |
| Package body and spec are one object with the same impact | Spec is the public contract; body is the implementation |
| Editing the body always invalidates every caller | Body-only changes usually leave caller contracts intact, yet session package state may be discarded |
| Adding a parameter always breaks all callers | A trailing parameter with a default can preserve some call sites, but still requires verification |
| Successful compilation proves API compatibility | It only proves the object compiles; external clients and semantics still need testing |
| INVALID means table data is corrupted | INVALID is a schema object status, not a data status |
| Oracle always succeeds at automatic recompilation | Auto revalidation can fail due to dependencies, signatures, or privileges |
| USER_DEPENDENCIES shows every runtime call | Dynamic SQL and external callers may not appear completely |
| Synonyms grant access privileges | Synonyms are only aliases; privileges are still needed on the target object |
| Role grants always suffice for stored definer-rights code | Compiling static SQL requires appropriate direct object grants |
| ALTER ... COMPILE fixes all errors | Compile only retries compilation; broken source or dependencies must still be fixed |
| An entire DDL migration can be rolled back | DDL triggers implicit commits; forward-fix/reverse DDL is required |
| Package variables persist forever | Package state is session-scoped and can be reset or invalidated |

## 21. Safe procedure/package change checklist

Before modifying:

1. Identify underlying objects and dependent objects.
2. Review current package spec/body and signatures.
3. Search for callers in PL/SQL source and application repositories.
4. Classify changes as additive or breaking.
5. Check positional/named notation, overloads, and parameter modes.
6. Check direct grants, roles, AUTHID, and synonym resolution.
7. Check whether dynamic SQL references the modified object.
8. Plan the migration in dependency order.

After modifying:

1. Compile the package spec before the body when the spec changes.
2. Compile dependent procedures/functions/triggers/views in dependency order.
3. Inspect USER_OBJECTS/ALL_OBJECTS.
4. Inspect USER_ERRORS/ALL_ERRORS.
5. Confirm no unexpected invalid objects remain.
6. Run smoke tests from actual callers.
7. Verify session/connection pool package state.
8. Verify client bindings and API compatibility.
9. Record version and deployment results.

## 22. Self-check questions

1. What is an object dependency?
2. How does a direct dependency differ from a transitive dependency?
3. Why can changing a package spec affect many callers?
4. How does a package body's role differ from a package spec's?
5. What impact does a body-only change usually have on dependent callers?
6. Why can replacing a package body still affect sessions holding package state?
7. What are the key components of a procedure/function signature?
8. How does adding a required parameter affect existing callers?
9. How does adding a trailing parameter with a default help?
10. Why can changing positional parameter order be dangerous?
11. How do IN, OUT, and IN OUT affect the call contract?
12. What errors or ambiguities can overloading introduce?
13. How do %TYPE and %ROWTYPE create schema dependencies?
14. Why does adding a column to a table not necessarily invalidate every procedure?
15. What limitations does dynamic SQL have in dependency tracking?
16. What is USER_DEPENDENCIES used to inspect?
17. How do USER_OBJECTS and USER_ERRORS differ?
18. When do you use ALTER PACKAGE COMPILE BODY?
19. When does automatic recompilation run and what are its limitations?
20. What is DBMS_UTILITY.COMPILE_SCHEMA used for?
21. Why does definer-rights stored code need direct grants?
22. Does a synonym replace object privileges?
23. What is ORA-04068 related to?
24. Why can a DDL migration not be rolled back like a DML transaction?
25. When should you create a new API version or a wrapper?

**Answer hints:**

1. A relationship between a schema object and an object it references.
2. Direct is an immediate reference; transitive goes through one or more intermediate objects.
3. Callers compile against the spec's public declarations.
4. The spec declares the public contract; the body contains the implementation.
5. Usually only the body needs compilation; caller contracts stay unchanged if the spec is unchanged.
6. Initialized package state may be invalidated/discarded.
7. Name, parameters, order, data types, modes, defaults, return type, and overload behavior.
8. Old calls missing the argument may fail to compile.
9. It can preserve some existing callers when default semantics are appropriate.
10. Values may be bound to the wrong parameters or calls may become invalid.
11. They define data flow in/out and which actual arguments are permitted.
12. Ambiguous resolution or selecting a different overload than intended.
13. They bind data type/row shape to a column or table/view.
14. Oracle uses fine-grained dependency tracking; objects referencing only unchanged columns may not need invalidation.
15. Object names inside strings are usually resolved only at runtime and not fully checked by the compiler.
16. Dependent objects and referenced objects.
17. USER_OBJECTS shows status; USER_ERRORS shows compile errors.
18. When you need to compile the implementation body of a package.
19. Oracle attempts compilation when an INVALID object is referenced; it fails if dependencies, privileges, or source still have errors.
20. Compiling stored objects in a schema, typically to process INVALID objects.
21. Role grants do not substitute for direct object grants when compiling static SQL in definer-rights stored units.
22. No; a synonym is only an alias.
23. The session's package state was discarded due to package invalidation.
24. DDL triggers implicit commits.
25. When a breaking change must be rolled out gradually while keeping old consumers working during transition.

## Oracle reference documentation

- [Oracle Database Concepts — Schema Objects and Dependencies](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/schema-objects.html): schema objects and dependency relationships.
- [Oracle Database PL/SQL Language Reference — PL/SQL Units and Compilation](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plsql-units-and-compilation.html): stored PL/SQL units and compilation.
- [Oracle Database PL/SQL Language Reference — Packages](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plsql-packages.html): package specification, body, and package state.
- [Oracle Database SQL Language Reference — ALTER PROCEDURE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-PROCEDURE.html): recompiling procedures.
- [Oracle Database SQL Language Reference — ALTER PACKAGE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-PACKAGE.html): compiling package specification/body.
- [Oracle Database Reference — USER_DEPENDENCIES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_DEPENDENCIES.html): dependency metadata within a schema.
- [Oracle Database Reference — USER_OBJECTS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_OBJECTS.html): object status and metadata.
- [Oracle Database Reference — USER_ERRORS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_ERRORS.html): compilation errors for stored objects.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_UTILITY](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_UTILITY.html): COMPILE_SCHEMA and administrative utilities.
- [Oracle Database PL/SQL Packages and Types Reference — UTL_RECOMP](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/UTL_RECOMP.html): recompiling invalid objects.

**Key principle:** The package specification is the public contract; the package body is the implementation. Changing a public signature can make callers incompatible, while changing only the body usually preserves the contract yet can still discard package state in active sessions. Inspect the dependency graph, grants, and callers before migration; deploy underlying objects before dependent objects; compile and verify status/errors afterward; and finally run smoke tests with actual callers and connection pools.
