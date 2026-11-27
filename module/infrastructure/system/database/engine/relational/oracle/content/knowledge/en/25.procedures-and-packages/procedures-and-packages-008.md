# AUTHID DEFINER, AUTHID CURRENT_USER, and execution privilege checks

A stored procedure or package can access data using the privileges of the schema that owns the code or using the privileges of the user currently invoking it. Oracle controls this behavior with the AUTHID property:

- **AUTHID DEFINER**: code runs with the privileges of the owner (the definer). This is the default if AUTHID is not specified.
- **AUTHID CURRENT_USER**: code runs with the privileges of the invoker (the caller in the current context).

This choice directly affects security, how Oracle checks privileges, how object names are resolved, the role of roles, and the reusability of PL/SQL across multiple schemas. A properly designed definer-rights API can let an application use data through a narrow interface without granting direct table privileges. An invoker-rights utility can use the caller's privileges and schema to operate on data the caller is permitted to access.

This lesson focuses on choosing AUTHID, understanding the difference between SESSION_USER and CURRENT_USER, granting direct grants, handling INHERIT PRIVILEGES, checking execution privileges, securing dynamic SQL, and verifying through a multi-schema lab.

## 1. What does AUTHID control?

AUTHID is a security attribute of a named PL/SQL unit such as a standalone procedure/function, package, or type method. It determines the privilege context used when the unit executes.

~~~text
APP_USER
   |
   | EXECUTE
   v
API_OWNER.GET_REPORT
   |
   +-- AUTHID DEFINER
   |      |
   |      +-- SQL runs with API_OWNER's privileges
   |      +-- APP_USER's regular roles are not used
   |
   +-- AUTHID CURRENT_USER
          |
          +-- SQL runs with the current invoker's privileges
          +-- enabled roles of the invoker can be used
~~~

AUTHID does not grant privileges to anyone on its own. Callers still need EXECUTE privilege on the procedure/package. AUTHID only determines the privilege context and name resolution when code is executed.

### 1.1. AUTHID DEFINER is the default

If AUTHID is omitted, a named PL/SQL unit defaults to definer's rights. The following two declarations have the same AUTHID meaning:

~~~sql
CREATE OR REPLACE PROCEDURE p_report (
    p_id IN NUMBER
) AS
BEGIN
    NULL;
END;
/
~~~

~~~sql
CREATE OR REPLACE PROCEDURE p_report (
    p_id IN NUMBER
)
AUTHID DEFINER
AS
BEGIN
    NULL;
END;
/
~~~

Explicitly writing AUTHID DEFINER can help readers recognize the security intent of the API, even though it is not required.

### 1.2. AUTHID CURRENT_USER

To execute with the invoker's privileges:

~~~sql
CREATE OR REPLACE PROCEDURE p_report (
    p_id IN NUMBER
)
AUTHID CURRENT_USER
AS
BEGIN
    NULL;
END;
/
~~~

The caller must have EXECUTE on the procedure. When the procedure performs data operations, Oracle checks privileges against the current invoker, along with the roles enabled in that context.

### 1.3. A package uses one AUTHID for its subprograms

A package's AUTHID is declared in the package specification and applies to the subprograms in the package:

~~~sql
CREATE OR REPLACE PACKAGE report_api
AUTHID CURRENT_USER
AS
    PROCEDURE open_report (
        p_result OUT SYS_REFCURSOR
    );
END report_api;
/
~~~

You cannot declare a separate AUTHID for individual procedures within the same package. If two APIs require different privilege models, separate them into distinct packages or standalone units with clear security boundaries.

## 2. Distinguishing SESSION_USER, CURRENT_USER, and CURRENT_SCHEMA

These three concepts are often confused but have distinct meanings.

| Value | Meaning |
| --- | --- |
| SESSION_USER | The database user authenticated for the login session |
| CURRENT_USER | The user Oracle is currently using as the active privilege context |
| CURRENT_SCHEMA | The default schema used to resolve unqualified object names |

In a definer-rights unit, CURRENT_USER and CURRENT_SCHEMA are switched to the unit's owner while the unit runs. SESSION_USER still reflects the user who originally logged in.

In an invoker-rights unit, CURRENT_USER and CURRENT_SCHEMA reflect the current invoker's context. CURRENT_SCHEMA can differ from SESSION_USER if the session explicitly changed schemas with ALTER SESSION SET CURRENT_SCHEMA.

### 2.1. Checking the execution context

You can inspect it with SYS_CONTEXT:

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_USER')   AS current_user,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

Place this query inside a procedure or function to observe the context while the code runs.

### 2.2. Example procedure printing context

~~~sql
CREATE OR REPLACE PROCEDURE show_execution_context
AUTHID DEFINER
AS
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'SESSION_USER=' || SYS_CONTEXT('USERENV', 'SESSION_USER')
    );
    DBMS_OUTPUT.PUT_LINE(
        'CURRENT_USER=' || SYS_CONTEXT('USERENV', 'CURRENT_USER')
    );
    DBMS_OUTPUT.PUT_LINE(
        'CURRENT_SCHEMA=' || SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')
    );
END;
/
~~~

If APP_USER invokes a procedure owned by API_OWNER, the typical result is that SESSION_USER remains APP_USER while CURRENT_USER and CURRENT_SCHEMA inside the definer-rights code are API_OWNER.

If the procedure is changed to AUTHID CURRENT_USER, CURRENT_USER switches to the current invoker. This is a direct way to verify the difference between the two models.

### 2.3. CURRENT_SCHEMA is not an access privilege

ALTER SESSION SET CURRENT_SCHEMA = OTHER_SCHEMA only changes the default schema used when resolving unqualified object names. It does not grant SELECT, INSERT, UPDATE, DELETE, or EXECUTE on objects in that schema.

For example, setting CURRENT_SCHEMA to DATA_OWNER does not mean the user is allowed to read DATA_OWNER.PAYROLL. Appropriate object privileges are still required directly or via an enabled role depending on the execution context.

## 3. AUTHID DEFINER: running with owner's privileges

Definer's rights are commonly used to build data APIs. The owner of the procedure is granted privileges on the required tables, while the application is only granted EXECUTE on the API.

### 3.1. Three-schema model

For example, consider three users:

- DATA_OWNER owns the business tables.
- API_OWNER owns the procedures providing the API.
- APP_USER is the application account.

~~~text
DATA_OWNER
  |
  +-- PAYROLL
        ^
        | SELECT granted directly
        |
API_OWNER
  |
  +-- GET_EMPLOYEE_SALARY  (AUTHID DEFINER)
        ^
        | EXECUTE
        |
APP_USER
~~~

APP_USER does not need SELECT on PAYROLL if it only needs to retrieve data through the procedure and the procedure is safely designed.

### 3.2. Granting privileges to the API owner

The DBA or DATA_OWNER creates the table and grants privileges directly to API_OWNER:

~~~sql
CREATE TABLE payroll (
    employee_id NUMBER PRIMARY KEY,
    salary      NUMBER(12, 2)
);

GRANT SELECT ON payroll TO api_owner;
~~~

If API_OWNER only receives SELECT through a role, that privilege is insufficient for compiling static SQL in stored PL/SQL. Grant the required object privileges directly to the owner.

### 3.3. Creating a definer-rights procedure

Log in as API_OWNER:

~~~sql
CREATE OR REPLACE PROCEDURE get_employee_salary (
    p_employee_id IN NUMBER,
    p_salary      OUT NUMBER
)
AUTHID DEFINER
AS
BEGIN
    SELECT salary
    INTO p_salary
    FROM data_owner.payroll
    WHERE employee_id = p_employee_id;
END;
/
~~~

The procedure runs the SELECT using API_OWNER's privileges. Because API_OWNER has direct SELECT on DATA_OWNER.PAYROLL, the unit can compile and execute that query.

### 3.4. Granting only EXECUTE to the application

The DBA or API_OWNER grants:

~~~sql
GRANT EXECUTE ON get_employee_salary TO app_user;
~~~

APP_USER invokes the procedure:

~~~sql
VARIABLE v_salary NUMBER
EXEC api_owner.get_employee_salary(101, :v_salary)
PRINT v_salary
~~~

This is SQL*Plus/SQLcl syntax. A JDBC or .NET application will bind the OUT parameter using the driver's API.

APP_USER can call the procedure without having SELECT on PAYROLL. The procedure is the access boundary; therefore, restrict the parameters, rows, and columns the API allows reading.

### 3.5. Benefits and risks

Benefits:

- Avoids granting direct table privileges to every application.
- Centralizes tenant validation, business state checks, and auditing in the API.
- Allows internal tables to evolve without forcing clients to query directly.
- Provides controlled operations such as creating orders, approving transactions, or reading reports.

Risks:

- A procedure can become a privilege escalation path if it accepts overly permissive parameters.
- String-concatenated dynamic SQL can allow SQL injection running with owner's privileges.
- A flaw in tenant or authorization checks at the API layer can expose multiple users' data.
- Excessive privileges on the owner magnify the impact of any code bug.

Definer's rights is a mechanism for building privileged APIs, not a reason to grant DBA or ANY privileges to application schemas.

## 4. Role privileges in a definer-rights unit

When a definer-rights unit runs, regular roles granted to the owner user are disabled within the unit's context. Privileges required for static SQL must be granted directly to the owner.

Example:

~~~sql
CREATE ROLE payroll_reader;
GRANT SELECT ON data_owner.payroll TO payroll_reader;
GRANT payroll_reader TO api_owner;
~~~

If API_OWNER only has SELECT through PAYROLL_READER, a procedure referencing PAYROLL may fail to compile. The fix is a direct grant:

~~~sql
GRANT SELECT ON data_owner.payroll TO api_owner;
~~~

Do not confuse:

- USER_ROLE_PRIVS shows roles granted to the user.
- SESSION_ROLES shows roles currently enabled in the session.
- A role granted to a user does not mean that role is used inside a definer-rights unit.

### 4.1. Roles granted directly to PL/SQL units (CBAC)

Oracle supports Code Based Access Control (CBAC) on releases with this feature. A DBA can grant a role to a procedure, function, or package so that the role's privileges are active while the unit runs, rather than granting the role to the entire owner user.

Illustrative example:

~~~sql
CREATE ROLE report_runtime_role;
GRANT SELECT ON data_owner.payroll TO report_runtime_role;

GRANT report_runtime_role
TO PROCEDURE api_owner.get_employee_salary;
~~~

Attaching a role to a unit creates a narrower privilege boundary than attaching it to the entire schema. However, privileges required to compile static SQL must still be granted directly to the owner per compile-time rules. CBAC does not replace carefully reviewing compile-time and runtime privileges.

Inspect roles granted to code using appropriate dictionary views such as DBA_CODE_ROLE_PRIVS or USER_CODE_ROLE_PRIVS if supported by the version.

## 5. AUTHID CURRENT_USER: running with invoker's privileges

Invoker's rights fit when a shared unit needs to perform work within the scope of the caller's privileges. It does not automatically give the caller extra privileges; the caller must have the necessary privileges for the statements executed.

### 5.1. Context inspection example

~~~sql
CREATE OR REPLACE PROCEDURE show_invoker_context
AUTHID CURRENT_USER
AS
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'SESSION_USER=' || SYS_CONTEXT('USERENV', 'SESSION_USER')
    );
    DBMS_OUTPUT.PUT_LINE(
        'CURRENT_USER=' || SYS_CONTEXT('USERENV', 'CURRENT_USER')
    );
    DBMS_OUTPUT.PUT_LINE(
        'CURRENT_SCHEMA=' || SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')
    );
END;
/
~~~

When APP_USER calls the procedure, CURRENT_USER reflects the current invoker. In a typical direct call, that is APP_USER. If the call passes through multiple units, the current invoker may be the owner of the nearest definer-rights unit in the call chain; see section 8.

### 5.2. Runtime privileges belong to the invoker

Suppose an invoker-rights procedure runs a SELECT on DATA_OWNER.PAYROLL:

- APP_USER must have SELECT directly or through an enabled role at the time of the call.
- API_OWNER also needs the privileges required to compile static SQL in the unit.
- APP_USER still needs EXECUTE on the procedure.

If APP_USER lacks access to PAYROLL, API_OWNER having SELECT does not allow APP_USER to read it via AUTHID CURRENT_USER.

### 5.3. When to use invoker's rights?

- Shared utility packages used across multiple schemas that must respect the caller's privileges.
- Frameworks running statements against objects in the caller's current schema.
- APIs that must use the end user's privileges instead of the owner's broad privileges.
- PL/SQL libraries using dynamic SQL to operate on caller-supplied objects within the caller's privilege scope.

Do not choose CURRENT_USER merely to make code “flexible.” If the goal is to provide controlled data operations via an API, definer's rights may be more appropriate.

## 6. INHERIT PRIVILEGES and ORA-06598

Starting in Oracle Database 12c, the INHERIT PRIVILEGES mechanism controls whether the owner of an invoker-rights unit is allowed to inherit the invoker's privileges.

When an invoker-rights unit runs, Oracle must verify that the unit's owner is permitted to execute code under the invoker's privilege context. If this privilege is missing, the call can fail with:

~~~text
ORA-06598: insufficient INHERIT PRIVILEGES privilege
~~~

### 6.1. Granting privilege to the owner of an invoker-rights unit

For example, when APP_USER calls a unit owned by API_OWNER:

~~~sql
GRANT INHERIT PRIVILEGES ON USER app_user TO api_owner;
~~~

This command grants API_OWNER the right to inherit APP_USER's privileges in an invoker-rights context. It does not grant APP_USER SELECT on tables, nor does it grant EXECUTE on procedures.

### 6.2. Restricting PUBLIC grants

In Oracle environments that default to granting INHERIT PRIVILEGES to PUBLIC on users, a DBA can narrow the scope and grant it specifically to the required code owners:

~~~sql
REVOKE INHERIT PRIVILEGES ON USER app_user FROM PUBLIC;
GRANT INHERIT PRIVILEGES ON USER app_user TO api_owner;
~~~

Verify the database's actual grants and security policy before changing them. If multiple invokers call the same unit, each user must be evaluated under the corresponding policy.

### 6.3. INHERIT ANY PRIVILEGES

INHERIT ANY PRIVILEGES allows a user to inherit the privileges of many other users and has a broad scope. Do not grant this privilege as a quick fix for ORA-06598. Prefer granting INHERIT PRIVILEGES on the specific user to the specific owner.

### 6.4. Checking INHERIT privileges

A DBA can inspect related object grants:

~~~sql
SELECT
    grantee,
    owner,
    table_name,
    privilege,
    grantor
FROM dba_tab_privs
WHERE privilege = 'INHERIT PRIVILEGES'
  AND table_name = UPPER('APP_USER')
ORDER BY grantee;
~~~

Displayed names and metadata may vary by release/grant type; consult DBA_TAB_PRIVS and the exact version's Reference documentation if the query does not return expected results.

## 7. Compile-time and runtime privilege checks

This is a critical point when debugging privilege errors: Oracle checks privileges at different stages.

### 7.1. When compiling static SQL

Stored PL/SQL must resolve object names and verify privileges to compile static SQL statements. Object privileges required for compilation must be granted directly to the unit's owner; privileges coming solely from the owner's roles are insufficient.

For example, API_OWNER compiles a procedure containing:

~~~sql
SELECT salary
INTO p_salary
FROM data_owner.payroll
WHERE employee_id = p_employee_id;
~~~

API_OWNER needs direct SELECT on DATA_OWNER.PAYROLL to compile the unit. Having the PAYROLL_READER role does not substitute for this direct grant.

### 7.2. When running AUTHID DEFINER

Oracle checks runtime privileges against the unit's owner. Regular roles of the owner user are disabled in a definer-rights context; the owner's direct privileges are used. Roles granted directly to the PL/SQL unit via CBAC are a separate mechanism if configured.

Callers need EXECUTE on the unit, but do not necessarily need privileges on every table accessed by the definer unit.

### 7.3. When running AUTHID CURRENT_USER

Oracle checks runtime privileges against the current invoker. Roles enabled in the invoker's context can participate in privilege checks. The invoker needs privileges on the accessed objects and permission to call the unit.

The unit's owner must still satisfy compile-time requirements for static SQL. Thus, “runtime runs as invoker” does not mean the owner can compile a static query referencing nonexistent objects or lacking required privileges.

### 7.4. Dynamic SQL is checked at runtime

Dynamic SQL is parsed and executed at runtime. Therefore, access privileges for dynamic SQL are checked under the active AUTHID context:

- Definer's rights: owner's privileges, with the owner's regular roles disabled.
- Invoker's rights: invoker's privileges, including roles enabled in that context.

This is a major difference when a unit uses EXECUTE IMMEDIATE or OPEN FOR with a SQL string.

### 7.5. Summary table

| Stage | AUTHID DEFINER | AUTHID CURRENT_USER |
| --- | --- | --- |
| Caller needs EXECUTE on unit | Yes | Yes |
| Compile static SQL | Owner needs appropriate direct privileges | Owner needs appropriate direct privileges |
| Runtime privilege check | Unit's owner | Current invoker |
| Owner's regular roles | Disabled inside unit | Not the source of invoker's runtime privileges |
| Invoker's enabled roles | Not used for SQL inside unit | Can be used |
| Dynamic SQL | Checked under owner context | Checked under invoker context |
| INHERIT PRIVILEGES | Not a separate requirement of definer unit | Requires appropriate inherit privilege on invoker |

## 8. Privileges in a PL/SQL call chain

When one unit calls another, AUTHID context is applied step by step. The CURRENT_USER of an invoker-rights unit is the current invoker at the moment that unit is called, not necessarily always the original SESSION_USER.

~~~text
APP_USER (SESSION_USER)
   |
   v
APP_OWNER.CLIENT_ENTRY
   AUTHID DEFINER
   CURRENT_USER = APP_OWNER
   |
   v
SHARED_OWNER.UTILITY
   AUTHID CURRENT_USER
   CURRENT_USER = APP_OWNER
   |
   v
DATA_OWNER.DATA_API
   AUTHID DEFINER
   CURRENT_USER = DATA_OWNER
~~~

The diagram illustrates the context-switching rule: when definer-rights code runs, privileges switch to the owner; when an invoker-rights unit is called from within that context, the new unit's invoker is the current user active at the call point. When the unit finishes, Oracle restores the caller's context.

### 8.1. Why does the call chain matter?

Suppose APP_USER calls a definer-rights procedure owned by APP_OWNER, which in turn calls an invoker-rights utility owned by SHARED_OWNER. The utility does not necessarily run as the initial APP_USER; it runs as APP_OWNER because APP_OWNER is the current user at the time of the call.

When investigating privileges, trace the call chain and determine:

1. Which unit is executing?
2. What is that unit's AUTHID?
3. Who is CURRENT_USER immediately before calling the unit?
4. Does the unit's owner have INHERIT PRIVILEGES on that invoker?
5. Which object privileges are needed at compile-time and runtime?

Do not just look at SESSION_USER and assume it is the user checked for every SQL statement in the call chain.

## 9. Name resolution and dynamic SQL

AUTHID also affects the schema context used to resolve unqualified object names. In a definer-rights unit, CURRENT_SCHEMA inside the unit is the owner's schema. In an invoker-rights unit, CURRENT_SCHEMA follows the invoker's context.

### 9.1. Static SQL and dynamic SQL

Static SQL is analyzed when compiling the unit and creates dependency metadata. Dynamic SQL is parsed at runtime, so it can use object names resolved under the runtime context.

Example of an invoker-rights utility accessing a table of the same name in the caller's schema:

~~~sql
CREATE OR REPLACE PROCEDURE open_my_items (
    p_status IN VARCHAR2,
    p_result OUT SYS_REFCURSOR
)
AUTHID CURRENT_USER
AS
BEGIN
    OPEN p_result FOR
        'SELECT item_id, item_name ' ||
        'FROM caller_items ' ||
        'WHERE status = :status ' ||
        'ORDER BY item_id'
    USING p_status;
END;
/
~~~

If APP_USER calls the procedure and CURRENT_SCHEMA in that context is APP_USER, the unqualified name CALLER_ITEMS is resolved in the invoker's current schema. APP_USER must have the required privileges on that table. Because the query is dynamic SQL, the object is not hard-coded as a static dependency of the procedure.

This is an advanced pattern. Test with actual schemas, synonyms, and CURRENT_SCHEMA before using it. If the caller changed CURRENT_SCHEMA via ALTER SESSION, unqualified names may resolve in that schema.

### 9.2. Bind variables for data

Always bind values instead of concatenating strings:

~~~sql
OPEN p_result FOR
    'SELECT item_id, item_name FROM caller_items WHERE status = :s'
USING p_status;
~~~

Bind variables prevent SQL injection for data values and allow Oracle to reuse cursors more efficiently.

### 9.3. Identifiers cannot be bound

Bind variables cannot replace table names, column names, or SQL keywords. If an API needs to choose a sort column, use a whitelist:

~~~sql
IF p_sort = 'NAME' THEN
    l_order_by := 'item_name';
ELSIF p_sort = 'DATE' THEN
    l_order_by := 'created_at';
ELSE
    RAISE_APPLICATION_ERROR(-20001, 'Unsupported sort column');
END IF;

l_sql := 'SELECT item_id, item_name FROM caller_items ORDER BY '
         || l_order_by;

OPEN p_result FOR l_sql;
~~~

Only concatenate identifiers taken from a fixed list controlled by code. DBMS_ASSERT can help validate identifier syntax in some cases, but it does not replace whitelists, privilege checks, and business validation.

### 9.4. SQL injection risks in definer-rights

If a definer-rights procedure accepts arbitrary SQL strings and executes them with owner's privileges, a caller can make the code operate on objects the caller is not allowed to access directly.

Do not build APIs like:

~~~sql
EXECUTE IMMEDIATE p_sql_text;
~~~

unless it is a specially controlled administrative tool with strict caller authentication and authorization. In application APIs, keep SQL structure fixed, bind values, and whitelist every identifier choice.

## 10. Checking AUTHID in the data dictionary

Do not infer AUTHID merely from a procedure name or schema owner. Inspect stored subprogram metadata instead.

### 10.1. ALL_PROCEDURES

~~~sql
SELECT
    owner,
    object_name,
    procedure_name,
    authid
FROM all_procedures
WHERE owner = UPPER(:owner)
  AND object_name = UPPER(:object_name)
ORDER BY procedure_name;
~~~

AUTHID values typically display DEFINER or CURRENT_USER. For packages, inspect the subprograms belonging to the package and cross-check the package specification. Visibility into metadata depends on the session's access privileges.

### 10.2. USER_SOURCE

If you need to verify the source:

~~~sql
SELECT line, text
FROM user_source
WHERE name = UPPER(:object_name)
  AND type IN ('PROCEDURE', 'FUNCTION', 'PACKAGE')
ORDER BY type, line;
~~~

For packages, AUTHID is declared in the specification. Do not look for a separate AUTHID in the package body and conclude the body has different rights from the specification.

## 11. Checking effective privileges

Granted privileges, enabled roles, and privileges required for an operation are three distinct concepts.

### 11.1. Granted roles and enabled roles

~~~sql
SELECT role
FROM user_role_privs
ORDER BY role;

SELECT role
FROM session_roles
ORDER BY role;
~~~

USER_ROLE_PRIVS shows roles granted to the user. SESSION_ROLES shows roles currently enabled in the session. When checking privileges for an invoker-rights unit, examine the roles enabled at the time the unit runs.

### 11.2. Effective system privileges

~~~sql
SELECT privilege
FROM session_privs
ORDER BY privilege;
~~~

SESSION_PRIVS shows system privileges active in the session. Do not use it to draw conclusions about all object privileges on a specific table.

### 11.3. Object privileges

For privileges on tables/views:

~~~sql
SELECT
    owner,
    table_name,
    privilege,
    grantor,
    grantee
FROM all_tab_privs
WHERE table_name = UPPER(:table_name)
ORDER BY owner, grantee, privilege;
~~~

A DBA can use DBA_TAB_PRIVS for a broader view. Distinguish whether the grantee is a user or a role; if granted to a role, check next whether that role is enabled in the session.

### 11.4. EXECUTE privilege on APIs

Check who has been granted privileges on a procedure/package:

~~~sql
SELECT
    owner,
    table_name,
    grantee,
    privilege,
    grantable
FROM all_tab_privs
WHERE owner = UPPER(:api_owner)
  AND table_name = UPPER(:api_name)
  AND privilege = 'EXECUTE'
ORDER BY grantee;
~~~

A user having privileges on a table does not imply the user has permission to call a procedure; conversely, having EXECUTE on a procedure does not automatically grant direct privileges on every table the procedure uses.

## 12. Comparing AUTHID choices in design

| Scenario | Typical suitable choice | Reason |
| --- | --- | --- |
| API reading data via a controlled interface | DEFINER | Caller only needs EXECUTE; API uses owner's privileges |
| Business update API with centralized validation and auditing | DEFINER | Owner performs DML within controlled code boundaries |
| Utility accessing objects in the caller's schema | CURRENT_USER | Respects the invoker's privileges and schema |
| Framework executing operations using each user's privileges | CURRENT_USER | Avoids using broad owner privileges on behalf of callers |
| Shared utility package needing unit-specific privileges | Evaluate CURRENT_USER or CBAC | Depends on who should own runtime privileges |
| Tool running arbitrary SQL | Do not expose a broad API; redesign | Very high risk of SQL injection and privilege escalation |

No single AUTHID fits every package. The decision rests on trust boundaries: who is allowed to call, which data may be accessed, and who is responsible for runtime privileges.

## 13. Lab: verifying definer and invoker rights

The lab requires three schemas: DATA_OWNER, API_OWNER, and APP_USER. The DBA creates the users, tablespace/quota, and appropriate CREATE SESSION/CREATE TABLE/CREATE PROCEDURE privileges. Use passwords compliant with lab policy; do not use sample passwords in production.

### 13.1. Create data

Log in as DATA_OWNER:

~~~sql
CREATE TABLE lab_payroll (
    employee_id NUMBER PRIMARY KEY,
    employee_name VARCHAR2(80),
    salary NUMBER(12, 2)
);

INSERT INTO lab_payroll VALUES (101, 'An', 2500);
INSERT INTO lab_payroll VALUES (102, 'Binh', 3200);
COMMIT;

GRANT SELECT ON lab_payroll TO api_owner;
~~~

### 13.2. Create a definer-rights API

Log in as API_OWNER:

~~~sql
CREATE OR REPLACE PROCEDURE lab_get_salary (
    p_employee_id IN NUMBER,
    p_salary OUT NUMBER
)
AUTHID DEFINER
AS
BEGIN
    SELECT salary
    INTO p_salary
    FROM data_owner.lab_payroll
    WHERE employee_id = p_employee_id;
END;
/

GRANT EXECUTE ON lab_get_salary TO app_user;
~~~

Log in as APP_USER and call:

~~~sql
VARIABLE v_salary NUMBER
EXEC api_owner.lab_get_salary(101, :v_salary)
PRINT v_salary
~~~

APP_USER receives the salary even without SELECT on DATA_OWNER.LAB_PAYROLL. Try selecting directly from the table to observe the difference in privileges.

### 13.3. Create an invoker-rights API

Log in as API_OWNER:

~~~sql
CREATE OR REPLACE PROCEDURE lab_check_payroll_access (
    p_result OUT SYS_REFCURSOR
)
AUTHID CURRENT_USER
AS
BEGIN
    OPEN p_result FOR
        SELECT employee_id, employee_name, salary
        FROM data_owner.lab_payroll
        ORDER BY employee_id;
END;
/

GRANT EXECUTE ON lab_check_payroll_access TO app_user;
~~~

If APP_USER does not yet have SELECT on DATA_OWNER.LAB_PAYROLL, calling the procedure fails at runtime due to missing invoker privileges. The DBA or DATA_OWNER can grant:

~~~sql
GRANT SELECT ON lab_payroll TO app_user;
~~~

Then call the procedure again using a client that supports SYS_REFCURSOR. APP_USER can read the data because the invoker itself has SELECT privilege.

### 13.4. Test INHERIT PRIVILEGES

If the environment revoked the grant from PUBLIC or policy requires explicit grants, grant:

~~~sql
GRANT INHERIT PRIVILEGES ON USER app_user TO api_owner;
~~~

Try revoking the appropriate grant in the lab environment to observe ORA-06598, then re-grant it. Do not modify privileges on production users.

### 13.5. Observe CURRENT_USER

Create procedures that display context with both AUTHID DEFINER and AUTHID CURRENT_USER. Call them from APP_USER and compare SESSION_USER, CURRENT_USER, and CURRENT_SCHEMA.

### 13.6. Verify roles do not replace direct grants at compile time

Create a role with SELECT on LAB_PAYROLL, grant the role to API_OWNER, and try compiling a static SQL procedure when API_OWNER lacks direct SELECT. Observe the compile error. Grant direct SELECT to API_OWNER and recompile.

This lab demonstrates that compile-time privilege checks and runtime privilege checks are two separate steps.

## 14. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Procedure omits AUTHID but runs with owner privileges | DEFINER is the default | Explicitly specify AUTHID to show intent |
| APP_USER cannot SELECT table, yet procedure still reads it | Procedure is definer-rights and owner has privilege | Verify whether the API properly restricts data |
| Procedure fails to compile even though a role has SELECT | Owner's roles do not replace direct grants for compiling static SQL | GRANT object privilege directly to owner |
| Invoker-rights procedure reports insufficient privileges | Invoker lacks runtime privilege on the object | Grant least privilege to invoker or redesign API |
| ORA-06598 | Owner of invoker-rights unit is not permitted to inherit invoker's privileges | Grant INHERIT PRIVILEGES on the right user to the right owner |
| EXECUTE granted, yet SELECT still fails | EXECUTE on unit does not imply runtime object access privilege | Identify AUTHID and check privileges in the active context |
| CURRENT_SCHEMA changed, yet access is still denied | CURRENT_SCHEMA only affects name resolution | Grant appropriate object privileges |
| Session role has privilege, yet definer unit cannot use it | Regular roles are disabled in definer-rights context | Use direct grants or evaluate CBAC |
| Procedure in call chain uses unexpected privileges | CURRENT_USER changes per executing unit | Trace call chain and check each unit's AUTHID |
| Dynamic SQL can access unintended tables | Uncontrolled concatenation of identifiers or SQL text | Bind values, whitelist identifiers, and restrict privileges |
| Caller sees results from another tenant | Definer API lacks tenant filtering/authorization | Authenticate/validate tenant/user inside API and audit |
| Package AUTHID behaves unexpectedly | AUTHID belongs to package specification and applies to subprograms | Check package spec and metadata |
| Granting INHERIT ANY PRIVILEGES as a quick fix | Grants overly broad inherit privilege | Use INHERIT PRIVILEGES on the specific user |

## 15. Privilege checklist when a procedure fails

When a procedure/package encounters ORA-01031, ORA-00942, ORA-06598, or privilege-related compilation errors, proceed in order:

1. Identify the actual owner, object type, and AUTHID.
2. Identify SESSION_USER, CURRENT_USER, and CURRENT_SCHEMA at the point of failure.
3. Confirm the caller has EXECUTE on the procedure/package.
4. Determine whether the failing SQL statement is static SQL or dynamic SQL.
5. If static SQL compilation failed, check direct grants to the owner.
6. If definer-rights runtime failed, check owner privileges and roles attached directly to code if CBAC is used.
7. If invoker-rights runtime failed, check the invoker's direct/object privileges and enabled roles.
8. Check INHERIT PRIVILEGES on the invoker.
9. Check synonyms, CURRENT_SCHEMA, and the actual owner of the object.
10. Trace the call chain if the procedure is called indirectly.
11. Check for SQL injection or identifier parameters if dynamic SQL is used.
12. Grant least privilege and retest using the exact application user/role.

Do not fix errors by granting SELECT ANY TABLE, EXECUTE ANY PROCEDURE, or INHERIT ANY PRIVILEGES without analyzing required privileges. These broad privileges can dramatically expand the code's access scope.

## 16. Hands-on exercises

Use the three-schema lab from section 13.

### Exercise 1 — Comparing contexts

Create two identical procedures, one with AUTHID DEFINER and one with AUTHID CURRENT_USER. Call them from APP_USER, recording SESSION_USER, CURRENT_USER, and CURRENT_SCHEMA. Explain the results.

### Exercise 2 — Direct grants and roles

Grant SELECT on LAB_PAYROLL to a role and grant that role to API_OWNER. Try compiling static SQL. Then grant SELECT directly to API_OWNER and recompile. Explain why the two cases differ.

### Exercise 3 — Runtime invoker privileges

Create an AUTHID CURRENT_USER procedure accessing DATA_OWNER.LAB_PAYROLL. Call it when APP_USER does not have SELECT, then grant SELECT to APP_USER and call it again. Distinguish compile-time errors from runtime errors.

### Exercise 4 — INHERIT PRIVILEGES

In the lab environment, inspect INHERIT PRIVILEGES grants. Revoke the grant from PUBLIC if lab policy permits, grant it specifically to API_OWNER, and observe the result. Document the scenario that triggers ORA-06598.

### Exercise 5 — Call chains

Create a definer-rights procedure that calls an invoker-rights utility. Call it from APP_USER and observe CURRENT_USER inside the utility. Reverse the AUTHID order and compare.

### Exercise 6 — Dynamic SQL

Write an invoker-rights procedure that opens a cursor on CALLER_ITEMS in the caller's schema. Use a bind variable for status. Verify that object names resolve according to CURRENT_SCHEMA.

### Exercise 7 — SQL injection

Test an input containing a single quote in a search value. Compare a query using bind variables with a string-concatenated query. Do not run destructive payloads; the goal is to understand why binding keeps input as data.

### Exercise 8 — Inspecting metadata

Use ALL_PROCEDURES, SESSION_ROLES, SESSION_PRIVS, and ALL_TAB_PRIVS to build a privilege matrix for API_OWNER and APP_USER. Distinguish granted privileges, enabled privileges, compile-time privileges, and runtime privileges.

## 17. Cleaning up lab data

Run only in the lab schema you created, after completing the exercises and confirming no dependencies remain:

~~~sql
DROP PROCEDURE lab_check_payroll_access;
DROP PROCEDURE lab_get_salary;
DROP TABLE lab_payroll PURGE;
~~~

Revoke the grants, roles, and INHERIT PRIVILEGES granted during the lab for the corresponding users/owners before dropping the lab schema. Do not run cleanup commands on business objects.

## Summary

AUTHID DEFINER runs with the owner's privileges and is the default for named PL/SQL units. It is well suited for building privileged APIs, but requires direct grants for compile-time static SQL, strict control over EXECUTE, and protection of all dynamic SQL. AUTHID CURRENT_USER runs with the current invoker's privileges, can use the invoker's enabled roles, and requires appropriate INHERIT PRIVILEGES on the invoker.

SESSION_USER is the logged-in user; CURRENT_USER is the user checked for privileges while code runs; CURRENT_SCHEMA governs name resolution for unqualified names. These three values can differ across a call chain. When debugging, separate compile-time from runtime, static SQL from dynamic SQL, and EXECUTE privilege from data object privileges. Secure design begins with least privilege, clear API contracts, bind variables, identifier whitelisting, and testing with the exact user/role the application uses.

## Oracle reference documentation

- [Oracle Database PL/SQL Language Reference — Invoker's Rights and Definer's Rights (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/invokers-rights-and-definers-rights-authid-property.html) — AUTHID, runtime identity, and privilege model.
- [Oracle Database Security Guide — Using Invoker's Rights and Definer's Rights (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/managing-security-for-definers-rights-and-invokers-rights.html) — stored PL/SQL security.
- [Oracle Database Security Guide — Inherit Privileges (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/managing-security-for-definers-rights-and-invokers-rights.html) — INHERIT PRIVILEGES and invoker-rights control.
- [Oracle Database Security Guide — Code Based Access Control (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/configuring-privilege-and-role-authorization.html) — roles granted to PL/SQL program units.
- [Oracle Database Reference — ALL_PROCEDURES (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/ALL_PROCEDURES.html) — procedure metadata and AUTHID.
- [Oracle Database Reference — SESSION_ROLES (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/SESSION_ROLES.html) — roles enabled in the session.
- [Oracle Database Reference — SESSION_PRIVS (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/SESSION_PRIVS.html) — active system privileges.
- [Oracle Database SQL Language Reference — GRANT (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/GRANT.html) — granting object privileges, roles, and INHERIT PRIVILEGES.

When deploying on an Oracle release other than 19c, consult the PL/SQL Language Reference, Security Guide, and Reference for that exact version, especially rules for INHERIT PRIVILEGES, CBAC, roles in definer-rights units, and AUTHID metadata.
