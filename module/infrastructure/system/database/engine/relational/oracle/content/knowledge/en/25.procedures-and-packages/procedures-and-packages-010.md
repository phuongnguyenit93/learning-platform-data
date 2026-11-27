# EXECUTE privileges, direct grants, and roles during PL/SQL compilation

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Procedures and packages  
> **Objective:** Understand the privilege model of procedures, functions, and packages in Oracle; distinguish program unit creation privileges, privileges on referenced objects, and EXECUTE privileges for callers; explain why privileges granted through roles are usually insufficient to compile stored PL/SQL; distinguish AUTHID DEFINER from AUTHID CURRENT_USER; recognize the effects of static SQL, dynamic SQL, roles, nested call chains, and INHERIT PRIVILEGES; know how to diagnose compile/runtime errors and deploy following the least-privilege principle.

## 1. What privileges does a procedure need to run?

A stored procedure can be created by one schema, access tables belonging to another schema, and be called by an application using a separate account. These three actions correspond to three distinct privilege layers:

1. **Program unit creation privilege:** allows a schema to create procedures, functions, or packages.
2. **Program unit privileges on referenced objects:** allows PL/SQL code to read/write tables, call packages, or use sequences.
3. **Caller EXECUTE privilege:** allows a user or role to invoke the procedure/function/package.

For example, APP_CODE owns the CUSTOMER_API package, the package reads the DATA_OWNER.CUSTOMERS table, and the application connects using APP_RUNTIME:

~~~text
APP_RUNTIME (application account)
       |
       | EXECUTE
       v
APP_CODE.CUSTOMER_API (package)
       |
       | SELECT according to the package's security model
       v
DATA_OWNER.CUSTOMERS (source table)
~~~

The right privileges must be granted along each path. Having SELECT on the table for APP_RUNTIME does not automatically make APP_CODE's package compile. Conversely, APP_CODE having SELECT on the table does not mean APP_RUNTIME is allowed to call the package.

A common design mistake is granting a role with many privileges to the code-owning schema and expecting stored procedures to automatically use all of those privileges. Stored PL/SQL has specific role rules, especially for definer-rights units.

## 2. Privileges to create procedures, functions, and packages

To create program units in its own schema, an account typically needs the appropriate system privileges:

- CREATE PROCEDURE: create procedures, functions, and packages in one's own schema.
- CREATE ANY PROCEDURE: create or alter program units in other schemas; this is a broad privilege and must be restricted.
- CREATE SESSION: allows connecting to the database; does not replace CREATE PROCEDURE.
- Additional privileges may be required depending on specific objects and operations.

Example of a DBA granting code-creation privileges to an application schema:

~~~sql
GRANT CREATE SESSION TO app_code;
GRANT CREATE PROCEDURE TO app_code;
~~~

APP_CODE can then create a procedure in its own schema:

~~~sql
CREATE OR REPLACE PROCEDURE app_code.hello_api IS
BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello from APP_CODE');
END;
/
~~~

If connected as APP_CODE, the schema prefix can be omitted:

~~~sql
CREATE OR REPLACE PROCEDURE hello_api IS
BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello');
END;
/
~~~

Do not grant CREATE ANY PROCEDURE to an application account merely to resolve a compile error in its own schema. Identify the proper owner and grant only the minimum required privileges.

### 2.1. Creating code differs from calling code

A user with CREATE PROCEDURE does not automatically have EXECUTE privilege on every procedure in the database. Similarly, a user with EXECUTE on a package cannot automatically create new packages.

These are two independent actions:

~~~sql
GRANT CREATE PROCEDURE TO app_code;

GRANT EXECUTE ON app_code.customer_api TO app_runtime;
~~~

The first statement grants program unit creation privilege to APP_CODE. The second allows APP_RUNTIME to call the CUSTOMER_API package.

## 3. Privileges to access referenced objects in PL/SQL

Suppose DATA_OWNER owns the CUSTOMERS table:

~~~sql
CREATE TABLE data_owner.customers (
    customer_id NUMBER PRIMARY KEY,
    customer_name VARCHAR2(100) NOT NULL,
    status VARCHAR2(20) NOT NULL
);
~~~

APP_CODE needs to create a procedure reading that table:

~~~sql
CREATE OR REPLACE PROCEDURE app_code.list_customers IS
BEGIN
    FOR r IN (
        SELECT customer_id, customer_name
        FROM data_owner.customers
        ORDER BY customer_id
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(
            r.customer_id || ': ' || r.customer_name
        );
    END LOOP;
END;
/
~~~

For a procedure using the default AUTHID DEFINER, APP_CODE needs appropriate direct access privileges on DATA_OWNER.CUSTOMERS for static SQL to compile and for the procedure to execute with owner's privileges.

The DBA or DATA_OWNER grants directly:

~~~sql
GRANT SELECT ON data_owner.customers TO app_code;
~~~

Then APP_CODE compiles the procedure.

If the procedure needs INSERT:

~~~sql
GRANT INSERT ON data_owner.customers TO app_code;
~~~

If it needs to UPDATE specific columns:

~~~sql
GRANT UPDATE (status) ON data_owner.customers TO app_code;
~~~

If it needs DELETE:

~~~sql
GRANT DELETE ON data_owner.customers TO app_code;
~~~

Grant the exact object privilege matching actual operations. Do not grant full SELECT/INSERT/UPDATE/DELETE just to avoid compile errors.

### 3.1. Direct privileges vs. privileges through roles

Consider this scenario:

~~~sql
CREATE ROLE r_customer_reader;

GRANT SELECT ON data_owner.customers TO r_customer_reader;
GRANT r_customer_reader TO app_code;
~~~

APP_CODE may see the granted role in metadata/session depending on configuration, yet this role does not substitute for the direct object grant needed to compile static SQL in stored definer-rights PL/SQL.

For definer-rights units, roles granted to the user are disabled while the unit runs. Thus, the procedure cannot rely on SELECT privileges coming only from APP_CODE's role.

The proper fix for a procedure needing SELECT on the source table:

~~~sql
GRANT SELECT ON data_owner.customers TO app_code;
~~~

This is a direct grant to the owner schema.

### 3.2. Why does SQL run directly yet fail to compile inside a procedure?

A user can run a SELECT statement in a worksheet successfully thanks to a role:

~~~sql
SELECT customer_id, customer_name
FROM data_owner.customers;
~~~

However, when placing that same SQL into a stored procedure, the compiler checks privileges in the stored unit compilation context. Roles are not used as direct grants to satisfy compilation requirements.

Consequently, you may encounter this situation:

- Direct SELECT succeeds.
- CREATE PROCEDURE or ALTER PROCEDURE fails.
- USER_ERRORS records a compile error, such as ORA-00942 or PLS-00201 depending on how it is referenced and the context.

Do not conclude the table does not exist solely from ORA-00942. Verify the owner, object name, synonyms, and direct privileges of the compiling schema.

## 4. Static SQL vs. dynamic SQL: when privileges are checked

Object access privileges also depend on whether SQL is written directly in PL/SQL or built as a string and executed at runtime.

### 4.1. Static SQL

Static SQL is written directly in source code:

~~~sql
SELECT customer_name
INTO l_customer_name
FROM data_owner.customers
WHERE customer_id = p_customer_id;
~~~

Oracle parses, resolves names, and checks privileges during compilation. Static SQL is also checked for privileges at runtime under the active security domain.

For definer-rights units, the owner must have appropriate object privileges. Roles do not supply privileges for compiling static SQL.

For invoker-rights units, pay attention to the template object rule: static SQL must resolve to a corresponding object in the owner schema at compile time and in the invoker schema at runtime for external references resolved as the invoker. Both objects must have compatible structures. The AUTHID CURRENT_USER section explains this in more detail.

### 4.2. Dynamic SQL

Dynamic SQL is constructed and executed at runtime, for example:

~~~sql
EXECUTE IMMEDIATE
    'SELECT COUNT(*) FROM data_owner.customers'
INTO l_customer_count;
~~~

Oracle performs name resolution and privilege checking when executing the dynamic statement. Therefore, runtime privileges and the program unit's security domain determine whether the SQL succeeds.

In a definer-rights unit, dynamic SQL runs with the owner's privileges; the owner's roles are disabled per definer's rights rules, except for roles granted directly to the program unit where supported by Oracle.

In an invoker-rights unit, dynamic SQL uses the invoker's privileges and enabled roles within valid contexts.

Do not use dynamic SQL merely to work around missing direct grants in static SQL. Dynamic SQL increases complexity, SQL injection risk, and makes dependency tracking harder. Use it only when table names, column names, or statement structure truly must change at runtime.

## 5. EXECUTE: caller privileges on procedures/packages

After APP_CODE creates the CUSTOMER_API package, APP_RUNTIME needs EXECUTE privilege to call the package.

~~~sql
GRANT EXECUTE ON app_code.customer_api TO app_runtime;
~~~

It can be granted to an application role:

~~~sql
CREATE ROLE app_runtime_role;
GRANT EXECUTE ON app_code.customer_api TO app_runtime_role;
GRANT app_runtime_role TO app_runtime;
~~~

When the role is enabled in the session, APP_RUNTIME can call the package:

~~~sql
BEGIN
    app_code.customer_api.list_customers;
END;
/
~~~

The caller does not need CREATE PROCEDURE to call the package. The caller also does not necessarily need direct SELECT on DATA_OWNER.CUSTOMERS if the package is definer-rights and only exposes designed operations.

### 5.1. EXECUTE on a package vs. privileges on underlying objects

Granting EXECUTE on a package does not automatically grant SELECT on every table the package uses.

Example:

- APP_RUNTIME has EXECUTE on APP_CODE.CUSTOMER_API.
- APP_CODE has direct SELECT on DATA_OWNER.CUSTOMERS.
- CUSTOMER_API runs with AUTHID DEFINER.

APP_RUNTIME can call the API; the package uses APP_CODE's privileges to access the table according to its implemented logic.

This is how to build a controlled database API: users only invoke published operations rather than accessing every table directly.

However, if a procedure returns all sensitive data without filtering by user, granting only EXECUTE can still expose too much data. Business authorization must be designed inside the API.

### 5.2. EXECUTE for procedures called from other stored procedures

Suppose APP_CODE.PROC_A calls APP_SERVICE.PROC_B. If PROC_A is definer-rights, the schema owning PROC_A needs appropriate EXECUTE privilege on PROC_B according to the call chain's security model.

Do not rely on an end user's roles to allow a definer-rights stored procedure to call another subprogram. Privilege checks along a PL/SQL chain must be evaluated based on each unit's owner and AUTHID.

### 5.3. Restrict GRANT EXECUTE TO PUBLIC

Privileges can be granted to PUBLIC:

~~~sql
GRANT EXECUTE ON app_code.customer_api TO PUBLIC;
~~~

However, PUBLIC represents every database user. This greatly widens code invocation scope and is inappropriate for sensitive business APIs without clear justification.

Prefer granting to dedicated application roles or specific users, then managing role membership.

## 6. AUTHID DEFINER: running with owner's privileges

If AUTHID is omitted, stored procedures/functions/packages default to definer's rights in standard cases.

It can be stated explicitly:

~~~sql
CREATE OR REPLACE PROCEDURE app_code.list_customers
AUTHID DEFINER
IS
BEGIN
    FOR r IN (
        SELECT customer_id, customer_name
        FROM data_owner.customers
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(r.customer_name);
    END LOOP;
END;
/
~~~

When APP_RUNTIME calls the procedure:

- CURRENT_USER in the definer-rights context is the unit's owner.
- SQL access privileges are evaluated under the owner's security domain.
- Owner's roles are disabled inside the unit.
- The caller needs EXECUTE on the unit, without needing direct privileges on every table the unit accesses.
- Data modifications still participate in the calling session's transaction; definer's rights do not auto-commit.

### 6.1. Definer's rights as a security boundary

A definer-rights API can allow users to perform a specific operation without granting direct privileges on source tables.

For example, callers may only call a procedure to create a support request:

~~~sql
CREATE OR REPLACE PROCEDURE app_code.create_support_request (
    p_customer_id IN NUMBER,
    p_message     IN VARCHAR2
)
AUTHID DEFINER
IS
BEGIN
    INSERT INTO data_owner.support_requests (
        customer_id,
        request_message,
        created_at
    )
    VALUES (
        p_customer_id,
        p_message,
        SYSTIMESTAMP
    );
END;
/
~~~

APP_CODE needs direct INSERT on SUPPORT_REQUESTS. APP_RUNTIME only needs EXECUTE on the procedure.

The procedure must validate the customer, message length, account status, and business rules before writing. Otherwise, a broadly granted EXECUTE API can become an uncontrolled data-writing path.

### 6.2. Roles are disabled inside definer-rights units

In a definer-rights unit, the caller's enabled roles do not become execution privileges for the code. This prevents a procedure from accidentally inheriting all of the caller's role privileges.

It also means SET ROLE cannot be used to enable roles inside a definer-rights unit. Grant appropriate direct privileges to the owner or design a different AUTHID when caller privileges are genuinely required.

## 7. AUTHID CURRENT_USER: running with invoker's privileges

An invoker-rights unit is declared with AUTHID CURRENT_USER.

Example:

~~~sql
CREATE OR REPLACE PROCEDURE app_code.count_my_customers
AUTHID CURRENT_USER
IS
    l_count NUMBER;
BEGIN
    SELECT COUNT(*)
    INTO l_count
    FROM customers;

    DBMS_OUTPUT.PUT_LINE('Rows = ' || l_count);
END;
/
~~~

When called, the unit uses the invoker's security context for external references resolved in the invoker's schema. The invoker's enabled roles can participate in privilege checking, unless the unit was called directly or indirectly from a definer-rights unit that causes roles to be disabled along the call chain.

### 7.1. Template objects for static SQL

For an invoker-rights unit containing static SQL, Oracle must resolve objects at compile time. Referenced objects must exist in the owner's schema at compile time and in the invoker's schema at runtime if names are resolved relative to the invoker.

Example:

- APP_CODE creates COUNT_MY_CUSTOMERS.
- APP_CODE has a CUSTOMERS table as a template so the compiler can analyze the SELECT.
- APP_RUNTIME has its own CUSTOMERS table with a compatible structure.
- When APP_RUNTIME calls the procedure, static SQL resolves against the invoker's schema and runs on APP_RUNTIME's CUSTOMERS.

Corresponding objects must have compatible names/columns. APP_CODE's template table does not need data; it serves compilation and metadata resolution.

This is a useful pattern when writing utilities that run across identically named objects in multiple schemas. If that generality is not needed, definer's rights with explicitly qualified objects is usually easier to manage.

### 7.2. Invoker privileges

For DML and dynamic SQL referencing objects resolved in the invoker's schema, the invoker must have the necessary runtime privileges. Privileges can come from direct grants or enabled roles in allowed contexts.

For example, if APP_RUNTIME accesses DATA_OWNER.CUSTOMERS via dynamic SQL or references resolved in that schema, APP_RUNTIME needs appropriate privileges on the source table, directly or via roles per invoker-rights semantics.

Granting privileges to the owner APP_CODE does not substitute for runtime privileges needed by the invoker on the invoker-rights path.

### 7.3. Not all external references are checked the same way

Oracle distinguishes external references in DML/dynamic SQL from other PL/SQL references. For certain PL/SQL references resolved at compile time, the owner's privileges are checked during compilation and are not re-checked as runtime object accesses by the invoker.

Therefore, AUTHID CURRENT_USER should not be oversimplified as "every statement uses the caller's privileges." Determine the reference type, when name resolution occurs, and whether the unit is called directly or indirectly from definer-rights code.

### 7.4. INHERIT PRIVILEGES in supported versions

Starting in Oracle Database 12c, invoker-rights units are also subject to checking permission to inherit the invoker's security context. If the owner lacks INHERIT PRIVILEGES on the invoker and lacks INHERIT ANY PRIVILEGES, runtime can raise:

~~~text
ORA-06598: insufficient INHERIT PRIVILEGES privilege
~~~

A DBA can grant the required privilege per policy:

~~~sql
GRANT INHERIT PRIVILEGES ON USER app_runtime TO app_code;
~~~

Or in special cases, grant INHERIT ANY PRIVILEGES to the owner. This ANY privilege is very broad, so prefer granting INHERIT PRIVILEGES on the specific required user.

Do not grant INHERIT PRIVILEGES en masse without understanding which units genuinely need to run under invoker privileges.

## 8. Comparing AUTHID DEFINER and AUTHID CURRENT_USER

| Criterion | AUTHID DEFINER | AUTHID CURRENT_USER |
|---|---|---|
| Runtime security context | Owner of the program unit | Current invoker |
| User roles | Disabled inside definer-rights unit | Can be enabled, depending on call stack |
| Privileges on source tables | Owner needs appropriate privileges | Invoker needs runtime privileges for external references resolved in invoker schema |
| Common goal | Business API with controlled privileges | Generic utility running under caller privileges |
| Primary risk | Code can exercise powerful owner privileges on caller's behalf | Results/access scope vary by invoker and roles |
| Declaration | Default or explicit AUTHID DEFINER | AUTHID CURRENT_USER |
| INHERIT PRIVILEGES | No IR-style switch to invoker checked | May be required on Oracle 12c+ |

Choose AUTHID based on the security contract:

- Use DEFINER when exposing a controlled set of operations using the schema owner's privileges.
- Use CURRENT_USER when logic must respect the caller's privileges and schema.
- Do not switch to CURRENT_USER merely to fix a missing direct grant error.
- Do not use DEFINER just to spare callers from needing table privileges without designing authorization inside the procedure.

## 9. Roles in stored PL/SQL

Roles bundle multiple privileges into one unit to grant to users. Roles are very useful for application sessions and privilege management, yet their effect in PL/SQL depends on AUTHID and the call stack.

### 9.1. Roles in a SQL session

Example:

~~~sql
CREATE ROLE r_reporting;

GRANT SELECT ON data_owner.customers TO r_reporting;
GRANT r_reporting TO app_runtime;
~~~

After logging in, if the role is enabled:

~~~sql
SELECT role
FROM session_roles
WHERE role = 'R_REPORTING';
~~~

APP_RUNTIME can run direct SELECTs thanks to the role.

### 9.2. Roles in a definer-rights unit

When a definer-rights procedure runs, roles of the caller and owner are disabled in the unit's security domain. Therefore, do not rely on R_REPORTING to supply SELECT to APP_CODE when compiling and running static SQL in a definer-rights procedure.

Instead, grant direct object privileges to APP_CODE:

~~~sql
GRANT SELECT ON data_owner.customers TO app_code;
~~~

### 9.3. Roles in an invoker-rights unit

An invoker-rights unit can use the invoker's enabled roles for runtime privilege checking on external references resolved in the invoker's schema, except when a call stack originating from a definer-rights unit disables roles.

This is useful for a utility called by multiple schemas with varying privileges. The same procedure can access whichever objects each invoker is permitted to access.

### 9.4. Nested call chains

Consider:

~~~text
APP_RUNTIME
    |
    v
APP_CODE.PROC_A  (AUTHID DEFINER)
    |
    v
UTIL.PKG_B       (AUTHID CURRENT_USER)
    |
    v
DML / dynamic SQL
~~~

When an invoker-rights unit is called directly or indirectly by a definer-rights unit, the invoker's roles are not automatically re-enabled as they would be when called directly from a session. Analyze the entire call stack, not just the AUTHID of the final procedure.

## 10. Complete example: direct grants, roles, and EXECUTE

This section illustrates a common three-schema pattern:

- DATA_OWNER owns the data.
- APP_CODE owns the API package.
- APP_RUNTIME is the application account.

### 10.1. DATA_OWNER creates the table

Connect as DATA_OWNER:

~~~sql
CREATE TABLE customers (
    customer_id NUMBER PRIMARY KEY,
    customer_name VARCHAR2(100) NOT NULL
);

INSERT INTO customers VALUES (1, 'An');
INSERT INTO customers VALUES (2, 'Binh');
COMMIT;
~~~

### 10.2. Grant direct privilege to APP_CODE

Connect as DATA_OWNER or DBA:

~~~sql
GRANT SELECT ON customers TO app_code;
~~~

This is a direct object grant. Do not grant SELECT only via a role.

### 10.3. APP_CODE creates a definer-rights package

Connect as APP_CODE:

~~~sql
CREATE OR REPLACE PACKAGE customer_api
AUTHID DEFINER
AS
    PROCEDURE print_customer_names;
END customer_api;
/
~~~

Package body:

~~~sql
CREATE OR REPLACE PACKAGE BODY customer_api AS
    PROCEDURE print_customer_names IS
    BEGIN
        FOR r IN (
            SELECT customer_name
            FROM data_owner.customers
            ORDER BY customer_id
        ) LOOP
            DBMS_OUTPUT.PUT_LINE(r.customer_name);
        END LOOP;
    END print_customer_names;
END customer_api;
/
~~~

If the package body compiles successfully, verify object status:

~~~sql
SELECT object_name,
       object_type,
       status
FROM user_objects
WHERE object_name = 'CUSTOMER_API';
~~~

### 10.4. Grant EXECUTE to an application role

Connect as APP_CODE or DBA:

~~~sql
CREATE ROLE app_runtime_role;

GRANT EXECUTE ON customer_api TO app_runtime_role;
GRANT app_runtime_role TO app_runtime;
~~~

APP_RUNTIME can invoke the package:

~~~sql
BEGIN
    app_code.customer_api.print_customer_names;
END;
/
~~~

APP_RUNTIME does not need direct SELECT on DATA_OWNER.CUSTOMERS for the operation performed by the definer-rights package. However, APP_RUNTIME still needs EXECUTE on the package through the chosen grant path.

### 10.5. Revoking the direct grant to observe compile/runtime impact

In a lab environment, DATA_OWNER can revoke direct SELECT:

~~~sql
REVOKE SELECT ON customers FROM app_code;
~~~

The stored unit may turn INVALID or fail with a privilege error on the next compilation/execution, depending on dependencies and state. Inspect USER_OBJECTS/USER_ERRORS in APP_CODE and never perform this test in production.

Re-grant:

~~~sql
GRANT SELECT ON customers TO app_code;
~~~

Then recompile if needed:

~~~sql
ALTER PACKAGE customer_api COMPILE BODY;
~~~

This experiment shows that the owner's privileges on source objects are part of the package's operational contract.

## 11. Diagnosing compile and runtime errors

Do not look at a single error code and immediately grant broader privileges. Determine at which stage the error occurred.

### 11.1. Check object status

~~~sql
SELECT object_name,
       object_type,
       status,
       last_ddl_time
FROM user_objects
WHERE object_type IN ('PROCEDURE', 'FUNCTION', 'PACKAGE', 'PACKAGE BODY')
ORDER BY object_name, object_type;
~~~

INVALID indicates the program unit needs attention/recompilation or has a dependency problem.

### 11.2. Check compile errors

~~~sql
SELECT name,
       type,
       line,
       position,
       text
FROM user_errors
ORDER BY name, sequence;
~~~

USER_ERRORS shows errors for objects in the current schema. For other schemas, a DBA can use DBA_ERRORS if authorized.

### 11.3. Check direct object grants

~~~sql
SELECT owner,
       table_name,
       grantee,
       privilege,
       grantable
FROM all_tab_privs
WHERE grantee IN ('APP_CODE', 'APP_RUNTIME')
ORDER BY owner, table_name, grantee, privilege;
~~~

A DBA can use DBA_TAB_PRIVS for database-wide visibility. USER_TAB_PRIVS/ALL_TAB_PRIVS/DBA_TAB_PRIVS have different visibility scopes; choose the view matching the privileges of the account investigating.

### 11.4. Check roles and system privileges

Roles enabled in the session:

~~~sql
SELECT role
FROM session_roles
ORDER BY role;
~~~

System privileges in the session:

~~~sql
SELECT privilege
FROM session_privs
ORDER BY privilege;
~~~

Roles granted to the user:

~~~sql
SELECT granted_role,
       default_role
FROM user_role_privs
ORDER BY granted_role;
~~~

These views help distinguish direct privileges in the session from enabled roles. However, an enabled role in a session does not prove that role is usable inside a definer-rights unit.

### 11.5. Check EXECUTE privilege

~~~sql
SELECT owner,
       table_name,
       grantee,
       privilege
FROM all_tab_privs
WHERE privilege = 'EXECUTE'
  AND table_name = 'CUSTOMER_API'
ORDER BY owner, grantee;
~~~

If the package resides in another schema, verify the exact owner and grantee. Also verify whether the role holding EXECUTE is granted to the user and enabled under the actual connection method.

### 11.6. Common errors

| Error/scenario | Possible cause | What to check |
|---|---|---|
| ORA-00942 during compile | Object does not exist, wrong owner/name, or missing direct privilege | Check object, synonym, direct grant, and USER_ERRORS |
| PLS-00201 | Identifier cannot be resolved or missing visibility privilege | Check schema qualification, grants, and compile errors |
| ORA-01031 | Insufficient privileges for DDL/DML or runtime operation | Identify executing user and security domain |
| ORA-06598 | Missing INHERIT PRIVILEGES for invoker-rights unit | Check INHERIT grant on invoker |
| Procedure runs directly but fails when called from another package | Privileges in call stack/definer-rights differ from session roles | Check AUTHID of each unit and direct grants |
| Package becomes INVALID after REVOKE | Dependencies or compile/runtime privileges changed | USER_OBJECTS, USER_ERRORS, and grants |
| Caller cannot call package | Missing EXECUTE or role not enabled | Check ALL_TAB_PRIVS and SESSION_ROLES |

Error codes can have multiple causes. Read the entire error stack, compile line, and referenced objects before modifying privileges.

## 12. Least-privilege granting workflow

A deployment workflow should separate the owner, data schema, and runtime user:

~~~text
DATA_OWNER
   |
   | GRANT exact SELECT/INSERT/UPDATE/DELETE
   | directly to APP_CODE if unit needs it
   v
APP_CODE
   |
   | CREATE PROCEDURE / package
   | compile and check USER_ERRORS
   |
   | GRANT EXECUTE on API
   v
APP_RUNTIME_ROLE
   |
   | GRANT role to APP_RUNTIME
   v
APP_RUNTIME
   |
   | call published API
   v
APP_CODE.CUSTOMER_API
~~~

Execution steps:

1. Identify source objects and minimum required operations.
2. Grant direct object privileges to the code owner where needed for definer-rights/static SQL.
3. Compile procedures/packages and check USER_ERRORS.
4. Choose AUTHID matching the security contract.
5. Grant EXECUTE on exact procedures/packages to the application role.
6. Grant the role to the application user per policy.
7. Test using the actual runtime account, not just the owner.
8. Verify that out-of-scope accesses are denied.
9. Audit dynamic SQL and SQL injection protections if present.
10. Record grant/revoke statements in migration scripts under version control.

### 12.1. Do not grant overly broad privileges to fix errors

Avoid uncontrolled fixes:

~~~sql
GRANT DBA TO app_code;
GRANT SELECT ANY TABLE TO app_code;
GRANT EXECUTE ANY PROCEDURE TO app_runtime;
GRANT EXECUTE ON app_code.customer_api TO PUBLIC;
~~~

These privileges exceed the needs of a specific API. Grant direct object privileges or EXECUTE only on required objects.

### 12.2. Revoke privileges when the API no longer needs them

If a package no longer uses a table, revoke the corresponding grant after confirming dependencies:

~~~sql
REVOKE SELECT ON data_owner.old_customers FROM app_code;
~~~

If the application is no longer allowed to call a package:

~~~sql
REVOKE EXECUTE ON app_code.customer_api FROM app_runtime_role;
~~~

After REVOKE, check object status, compile dependencies, and caller behavior. Do not revoke grants in production before confirming no other units also rely on that privilege.

## 13. Dynamic SQL and security safety

Dynamic SQL causes privileges to be checked at runtime and allows object names to vary per caller. This is a useful feature, yet it easily creates vulnerabilities if strings are concatenated directly from input.

Unsafe:

~~~sql
l_sql := 'SELECT * FROM ' || p_table_name;
EXECUTE IMMEDIATE l_sql;
~~~

If P_TABLE_NAME contains untrusted input, a user can alter the statement structure. Bind variables only substitute values, not table/column names.

For dynamic identifiers:

- Whitelist allowed schema/table names.
- Use DBMS_ASSERT for appropriate identifiers.
- Never concatenate input values into literals; use bind variables.
- Schema-qualify when needed to prevent unintended name resolution.
- Verify runtime privileges under AUTHID and the call stack.
- Grant EXECUTE only on objects that genuinely require it.

Example binding values:

~~~sql
l_sql :=
    'SELECT COUNT(*) FROM data_owner.customers ' ||
    'WHERE status = :1';

EXECUTE IMMEDIATE l_sql
INTO l_count
USING p_status;
~~~

P_STATUS is bound as data. The table name remains fixed in code; if the table name must be dynamic, validate it with a whitelist/DBMS_ASSERT.

## 14. Packages and Package-Level Privileges

Packages group procedures/functions into a shared API. Callers are typically granted EXECUTE on the package rather than separately on each public subprogram.

Example:

~~~sql
GRANT EXECUTE ON app_code.customer_api TO app_runtime_role;
~~~

Package EXECUTE privilege allows callers to invoke public subprograms in the package specification. Private subprograms can only be called from within the package and cannot be called directly from another schema.

### 14.1. Package AUTHID

AUTHID is declared in the package specification and applies to the package unit:

~~~sql
CREATE OR REPLACE PACKAGE app_code.report_api
AUTHID CURRENT_USER
AS
    PROCEDURE run_report;
END report_api;
/
~~~

The package body implements subprograms under the package's security property. You cannot declare a separate AUTHID for individual procedures within the same package to override that shared property.

If a package needs entry points with different security behaviors, design separate packages or split standalone units along clear boundaries.

### 14.2. Private Subprograms and Controlled Entry Points

A package can expose one public procedure as an entry point while keeping helper procedures private in the body. Callers can only invoke entry points for which they have EXECUTE permission; helpers are invoked internally along the call chain.

This reduces the API surface area and centralizes validation. Do not publish every helper in the package specification if the application does not need to call it directly.

## 15. Lab: Proving Roles Do Not Substitute for Direct Grants in Definer-Rights Code

Perform only in a lab schema with user/role creation privileges or have a DBA prepare it. Never revoke grants on production objects.

### 15.1. Preparation

Create a role and grant SELECT through the role:

~~~sql
CREATE ROLE r_lab_reader;
GRANT SELECT ON data_owner.customers TO r_lab_reader;
GRANT r_lab_reader TO app_code;
~~~

Log in as APP_CODE and try a direct SELECT:

~~~sql
SELECT COUNT(*)
FROM data_owner.customers;
~~~

If the role is enabled, the direct SQL query succeeds.

### 15.2. Create a Definer-Rights Procedure

~~~sql
CREATE OR REPLACE PROCEDURE test_role_privilege IS
    l_count NUMBER;
BEGIN
    SELECT COUNT(*)
    INTO l_count
    FROM data_owner.customers;

    DBMS_OUTPUT.PUT_LINE(l_count);
END;
/
~~~

With only a role grant, static SQL compilation will fail. Inspect:

~~~sql
SELECT line, position, text
FROM user_errors
WHERE name = 'TEST_ROLE_PRIVILEGE'
ORDER BY sequence;
~~~

### 15.3. Grant Direct Privilege and Recompile

DATA_OWNER or DBA:

~~~sql
GRANT SELECT ON data_owner.customers TO app_code;
~~~

APP_CODE:

~~~sql
ALTER PROCEDURE test_role_privilege COMPILE;
~~~

Check:

~~~sql
SELECT object_name, status
FROM user_objects
WHERE object_name = 'TEST_ROLE_PRIVILEGE';
~~~

### 15.4. Grant EXECUTE to the Caller

~~~sql
GRANT EXECUTE ON app_code.test_role_privilege TO app_runtime;
~~~

Log in as APP_RUNTIME and invoke:

~~~sql
BEGIN
    app_code.test_role_privilege;
END;
/
~~~

The caller is allowed to run the procedure via EXECUTE. The procedure's SELECT privilege comes from APP_CODE under definer's rights; APP_RUNTIME does not need SELECT on the table just to run this example.

## 16. Pre-Deployment PL/SQL Verification Checklist

- [ ] Identify the owner of each procedure/function/package.
- [ ] Identify the owning schema of every referenced table, view, sequence, and package.
- [ ] Verify CREATE PROCEDURE or appropriate creation privileges.
- [ ] Distinguish direct grants from privileges held only through roles.
- [ ] For definer-rights static SQL, grant direct object privileges to the owner.
- [ ] For invoker-rights static SQL, prepare template objects and matching objects in invoker schemas.
- [ ] Identify which SQL is static and which SQL is dynamic.
- [ ] Choose AUTHID DEFINER or CURRENT_USER per the security contract.
- [ ] Check roles and call stacks, especially IR units called from DR units.
- [ ] Verify INHERIT PRIVILEGES on applicable Oracle releases.
- [ ] Grant EXECUTE on exact packages/procedures to the required roles or users.
- [ ] Avoid GRANT EXECUTE TO PUBLIC unless clearly justified.
- [ ] Check USER_OBJECTS and USER_ERRORS after compilation.
- [ ] Test with the actual runtime account.
- [ ] Test both authorized operations and operations that must be denied.
- [ ] Audit dynamic SQL, bind variables, and identifier validation.
- [ ] Record GRANT/REVOKE statements in migrations and access-governance processes.

## 17. Key Takeaways

- CREATE PROCEDURE allows creating program units in one's own schema; CREATE ANY PROCEDURE is a broad privilege to create in other schemas.
- Code-creation privileges, code privileges on objects, and caller EXECUTE privileges are three independent layers.
- Static SQL is checked at compile time and runtime; AUTHID does not alter compile-time checks.
- Privileges granted only through roles do not substitute for direct grants required to compile static SQL in stored PL/SQL.
- Definer-rights units are the default: runtime uses owner privileges and user roles are disabled inside the unit.
- Invoker-rights units use the invoker's security context for external references resolved in the invoker's schema; roles can participate in runtime checking depending on the call stack.
- Invoker-rights static SQL requires template objects in the owner schema at compile time and matching objects in the invoker schema at runtime.
- Dynamic SQL is resolved and checked for privileges at runtime; never use dynamic SQL just to bypass privilege errors.
- EXECUTE on a package does not automatically grant SELECT/INSERT/UPDATE/DELETE on every table used by the package.
- A definer-rights procedure calling another unit must be evaluated by the owner's privileges and AUTHID of each link, not by the end user's roles.
- Oracle 12c+ may require INHERIT PRIVILEGES when running invoker-rights units; missing it can trigger ORA-06598.
- Least privilege, clear package entry points, accurate direct grants, and testing with runtime accounts make PL/SQL more secure.
- When errors occur, inspect compile errors, object status, direct grants, roles, AUTHID, and call stacks before granting broader privileges.

### Oracle Documentation to Reference

- [Oracle Database PL/SQL Language Reference — Invoker's Rights and Definer's Rights](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/invokers-rights-and-definers-rights-authid-property.html) — AUTHID, static/dynamic SQL, template objects, roles, and INHERIT PRIVILEGES.
- [Oracle Database Security Guide — Managing Security for Definer's Rights and Invoker's Rights](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/managing-security-for-definers-rights-and-invokers-rights.html) — runtime privileges, call chains, and invoker privileges.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — GRANT, REVOKE, CREATE PROCEDURE, and EXECUTE privileges.
- [Oracle Database PL/SQL Packages and Types Reference](https://docs.oracle.com/en/database/) — package specification/body and program units.
- [Oracle Database Reference](https://docs.oracle.com/en/database/) — USER_OBJECTS, USER_ERRORS, ALL_TAB_PRIVS, SESSION_ROLES, and dictionary views.

AUTHID rules, template objects, roles in call stacks, and INHERIT PRIVILEGES should be verified against your target Oracle release. Test compilation and execution in isolated lab schemas, verify both direct grants and role grants, and only then apply privilege migrations to production.
