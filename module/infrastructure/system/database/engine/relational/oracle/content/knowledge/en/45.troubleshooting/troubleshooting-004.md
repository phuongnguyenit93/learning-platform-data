# ORA-00942, ORA-01031, and Object Resolution or Insufficient Privilege Errors

When a SQL statement or PL/SQL program fails to access a table, view, sequence, package, or other object, Oracle typically returns one of two errors:

- **ORA-00942: table or view does not exist** — Oracle cannot resolve the table/view name in the execution context, or the object is not accessible to the current user. A synonym may exist but point to a nonexistent or inaccessible object.
- **ORA-01031: insufficient privileges** — Oracle recognized the operation or object, but the executing user lacks the required privilege for that operation.

These two errors can occur at different stages and sometimes stem from the same misconfiguration: connecting to the wrong schema/PDB, a synonym pointing to the wrong owner, a missing grant, privileges granted only through a role when definer-rights PL/SQL requires direct grants, or the application running as a different user than the one the DBA is testing with.

Never resolve these by granting `DBA`, `SELECT ANY TABLE`, or broad `ANY` privileges to an application. The right investigation approach is to identify the **actual session**, the **object name Oracle resolves**, the **object owner**, the **operation type**, and the **grant path**. Then grant the exact least privilege on the right object or fix the name/schema/synonym/service.

## 1. Understanding the Two Errors and When They Occur

### 1.1 ORA-00942

ORA-00942 typically displays:

~~~text
ORA-00942: table or view does not exist
~~~

Common causes:

- The table or view has not been created yet.
- The object resides in another schema, but the SQL uses an unqualified name.
- The application connects using a different database user.
- The current schema differs from what was assumed.
- A synonym does not exist, points to a dropped/renamed object, or points to the wrong owner.
- The account lacks access privileges on the referenced object.
- The object name was created with a quoted identifier and casing does not match.
- Connected to the wrong database, service, or PDB.
- A database link or remote object has an issue.
- A view, procedure, or dynamic SQL references an object that does not exist in the current environment.

ORA-00942 is not absolute proof that the object was dropped. Oracle may conceal the existence of an object from a user who lacks privileges to access it. Therefore, test using the actual application user and cross-check metadata as a DBA when needed.

### 1.2 ORA-01031

Common message:

~~~text
ORA-01031: insufficient privileges
~~~

This error occurs when the user lacks the system privilege or object privilege required for the operation. Examples:

- `SELECT`, `INSERT`, `UPDATE`, or `DELETE` on an object in another schema.
- `EXECUTE` on a procedure, function, or package.
- `CREATE TABLE`, `CREATE VIEW`, `CREATE PROCEDURE`, or `CREATE SEQUENCE` in the user's own schema.
- `CREATE ANY TABLE` or `ALTER ANY TABLE` when operating on another schema.
- Privileges required to create a view referencing another owner's object.
- Re-granting privileges to another user without `GRANT OPTION` or `ADMIN OPTION`.
- Privileges needed inside a PL/SQL stored unit not granted directly to the definer.

Some errors involving quota, tablespace, object state, or syntax have different error codes. For instance, ORA-01950 typically relates to tablespace quota; do not treat every `CREATE TABLE` failure as ORA-01031.

### 1.3 Quick Comparison

| Criterion | ORA-00942 | ORA-01031 |
|---|---|---|
| Common meaning | Cannot resolve table/view or cannot access that name | Missing privilege for the operation |
| Primary issue | Name, owner, synonym, service/PDB, or object visibility | System privilege, object privilege, or grant path |
| First check | User, current schema, owner, synonym, where the object exists | Statement being run and specific privilege required |
| Common fix | Fix schema qualification, synonym, connection, or grant object privilege | Grant exact minimal object/system privilege |
| Risk of wrong fix | Creating wrong synonyms or pointing to wrong data | Granting overly broad privileges, widening access scope |

Do not change privileges based solely on the error code. Identify the exact SQL statement and execution context first.

## 2. Identifying the Session Causing the Error

Investigating with a DBA account without verifying the application session's identity is a frequent cause of misdiagnosis. The DBA can see the object and read its data while the application cannot.

Start with a query from the failing connection itself:

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_USER') AS current_user,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema,
    SYS_CONTEXT('USERENV', 'CURRENT_EDITION_NAME') AS current_edition,
    SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
    SYS_CONTEXT('USERENV', 'DB_NAME') AS database_name
FROM dual;
~~~

These values answer distinct questions:

- `SESSION_USER` is the database user authenticated for the session.
- `CURRENT_USER` is the active user in the current execution context; it can change upon entering definer-rights PL/SQL.
- `CURRENT_SCHEMA` is the schema Oracle uses to resolve unqualified object names.
- `CURRENT_EDITION_NAME` indicates the current edition if the database uses edition-based redefinition.
- `CON_NAME` and `SERVICE_NAME` identify the connected container/PDB and service.
- `DB_NAME` verifies the target database.

### 2.1 SESSION_USER Is Not CURRENT_SCHEMA

For example, a session logs in as `APP_RUNTIME` but switches the resolution schema:

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = SALES;
~~~

After this statement:

- `SESSION_USER` remains `APP_RUNTIME`.
- `CURRENT_SCHEMA` becomes `SALES`.
- Unqualified table names are searched in the `SALES` schema.
- Actual privileges are still evaluated against the user and privilege context; changing `CURRENT_SCHEMA` grants no extra privileges.

`CURRENT_SCHEMA` controls name resolution; it is not a way to log in as another user and does not replace `GRANT`.

### 2.2 Checking from a DBA Session

A DBA can locate the application sessions:

~~~sql
SELECT
    sid,
    serial#,
    username,
    schema#,
    service_name,
    machine,
    program,
    module,
    action,
    status,
    sql_id
FROM v$session
WHERE username = 'APP_RUNTIME'
ORDER BY logon_time;
~~~

Replace `APP_RUNTIME` with the actual user. In Oracle RAC, use `GV$SESSION` and include `INST_ID` in filters/joins to distinguish sessions with matching SIDs across instances.

If the connection pool uses multiple users or proxy authentication, check client identifier, service, module/action, and proxy details as well. Do not assume every request runs under one schema just because the datasource configuration is named that way.

### 2.3 Comparing the Application Connection with a SQL Client

Run the same session context `SELECT` across:

1. The failing application connection.
2. SQL Developer or SQL*Plus logged in with the exact application username.
3. A DBA connection to inspect metadata when needed.

If results differ, record user, service, PDB, current schema, edition, and session settings. A SQL Developer connection logged in with a personal account does not represent the application's privileges.

## 3. How Oracle Resolves Object Names

A name like `ORDERS` can exist in multiple schemas. When SQL uses an unqualified name, Oracle must determine which object is referenced.

### 3.1 Unqualified vs. Owner-Qualified Names

Example:

~~~sql
SELECT *
FROM orders;
~~~

The name `ORDERS` omits the owner. Oracle resolves it within the current schema context and applicable synonyms.

If the object lives in schema `SALES`, specify it explicitly:

~~~sql
SELECT *
FROM sales.orders;
~~~

Schema qualification makes SQL less dependent on `CURRENT_SCHEMA` and reduces ambiguity when multiple schemas share object names. However, writing `SALES.ORDERS` does not automatically grant access; the user must still hold the appropriate privilege on the object.

### 3.2 Local Objects and Synonyms

A synonym is an alias for an object. There are two common types:

- Private synonym: belongs to a specific schema and is scoped to that schema's visibility/privileges.
- Public synonym: created in the public namespace and referenceable by multiple schemas.

Example:

~~~sql
CREATE SYNONYM app_runtime.orders
FOR sales.orders;
~~~

Or public synonym:

~~~sql
CREATE PUBLIC SYNONYM orders
FOR sales.orders;
~~~

Public synonyms should generally only be created for clear administrative reasons because they affect name resolution across many schemas.

**Synonyms do not grant privileges.** If `APP_RUNTIME` has a synonym `APP_RUNTIME.ORDERS` pointing to `SALES.ORDERS` without `SELECT` on `SALES.ORDERS`, the `SELECT` statement still fails.

### 3.3 Same-Named Local Objects Can Shadow Synonyms

If a schema contains both an actual object and a synonym with the same name, the local object resolves ahead of the synonym. For example, if `APP_RUNTIME` has an old `ORDERS` table while a private synonym `ORDERS` points to `SALES.ORDERS`, unqualified SQL may reference the local table.

When suspecting a shadowed synonym, use owner-qualified names and inspect `ALL_OBJECTS`/`ALL_SYNONYMS`. Do not drop a local object solely to make a synonym take effect; verify dependencies and design intent first.

### 3.4 Synonyms Can Point to the Wrong Target or Become Stale

A synonym can continue to exist even after its target is dropped or renamed. Creating a synonym does not guarantee that the target remains present and accessible on every execution.

Check:

~~~sql
SELECT
    owner,
    synonym_name,
    table_owner,
    table_name,
    db_link
FROM all_synonyms
WHERE synonym_name = 'ORDERS'
ORDER BY owner;
~~~

With DBA privileges, you can inspect `DBA_SYNONYMS`. For the current user's own synonyms, query `USER_SYNONYMS`.

If `DB_LINK` is non-null, the synonym points to a remote object. Investigate the database link and remote identity separately rather than searching only for a local table.

### 3.5 Database Links

Example:

~~~sql
SELECT *
FROM sales.orders@reporting_link;
~~~

The object reference includes schema, object, and database link. Check:

- Does the database link exist and fall within the user's scope?
- Does the link use a fixed user, connected user, or current user per its definition?
- Is the remote database/service operational?
- Does the remote user hold privileges on the object?
- Are the remote schema and object names accurate?

View link metadata visible to the user:

~~~sql
SELECT owner, db_link, username, host
FROM all_db_links;
~~~

Password details are not exposed in the view. Verify the remote identity using:

~~~sql
SELECT user
FROM dual@reporting_link;
~~~

If a remote query fails, the error code may be ORA-02019, ORA-12154, ORA-01017, or another network error instead of ORA-00942. Read the entire error stack to determine whether the error originates on the local or remote database.

## 4. Are Object Names Case-Sensitive?

Oracle converts unquoted identifiers to uppercase when storing and resolving them.

Example:

~~~sql
CREATE TABLE customer_order (
    id NUMBER
);
~~~

The name is stored as `CUSTOMER_ORDER`. Unquoted references like `customer_order`, `Customer_Order`, or `CUSTOMER_ORDER` all normalize to the same identifier.

If created using a quoted identifier:

~~~sql
CREATE TABLE "CustomerOrder" (
    "OrderId" NUMBER
);
~~~

then it must be referenced with exact casing and quotes:

~~~sql
SELECT "OrderId"
FROM "CustomerOrder";
~~~

The following statements do not reference the same names:

~~~sql
SELECT orderid FROM CustomerOrder;
SELECT "ORDERID" FROM "CUSTOMERORDER";
~~~

Quoted identifiers easily cause errors when ORMs or code generators emit unquoted names. For new schemas, unquoted identifiers following a consistent naming convention are generally recommended. If you must integrate existing quoted objects, check exact metadata before writing SQL.

### 4.1 Checking the Actual Name in the Data Dictionary

~~~sql
SELECT owner, object_name, object_type
FROM all_objects
WHERE UPPER(object_name) = UPPER(:name)
ORDER BY owner, object_type, object_name;
~~~

This query is helpful for fuzzy searches, though it may return multiple objects differing only by case. When an object was created with a quoted identifier, match `OBJECT_NAME` exactly:

~~~sql
SELECT owner, object_name, object_type
FROM all_objects
WHERE object_name = :exact_name;
~~~

Bind `:exact_name` with the exact string returned by metadata.

## 5. Verifying Object Existence and Visibility

The data dictionary provides several views with different scopes.

| View | Scope |
|---|---|
| USER_OBJECTS | Objects owned by the current schema |
| ALL_OBJECTS | Objects accessible/visible to the current user |
| DBA_OBJECTS | Objects across the database; requires DBA/catalog privileges |
| USER_TABLES | Tables owned by the current schema |
| ALL_TABLES | Tables accessible to the user |
| DBA_TABLES | Tables across the database |
| USER_VIEWS / ALL_VIEWS / DBA_VIEWS | View metadata by scope |
| USER_SYNONYMS / ALL_SYNONYMS / DBA_SYNONYMS | Synonyms by scope |
| ALL_TAB_PRIVS | Object grants visible to the user |
| USER_TAB_PRIVS_RECD | Object grants received by the user |
| USER_SYS_PRIVS | System privileges granted directly to the user |
| SESSION_PRIVS | System privileges currently active in the session |
| SESSION_ROLES | Roles currently enabled in the session |

### 5.1 Finding an Object by Owner and Name

~~~sql
SELECT
    owner,
    object_name,
    object_type,
    status,
    editionable
FROM all_objects
WHERE owner = 'SALES'
  AND object_name = 'ORDERS'
ORDER BY object_type;
~~~

If your release does not expose the `editionable` column or attribute in this manner, omit that column and use metadata appropriate for your version. For unquoted names, owner and object are stored in uppercase.

`ALL_OBJECTS` is not a database-wide catalog. Zero rows in `ALL_OBJECTS` does not prove the object does not exist; the user may simply lack privileges to see it. A DBA can check `DBA_OBJECTS` or `CDB_OBJECTS` in the right container if needed.

### 5.2 Checking Tables and Views Separately

~~~sql
SELECT owner, table_name
FROM all_tables
WHERE owner = 'SALES'
  AND table_name = 'ORDERS';

SELECT owner, view_name
FROM all_views
WHERE owner = 'SALES'
  AND view_name = 'ORDER_SUMMARY';
~~~

A query might reference a synonym or view rather than a table directly. Verify the exact object type and dependencies.

### 5.3 Checking View/Package Dependencies

~~~sql
SELECT
    owner,
    name,
    type,
    referenced_owner,
    referenced_name,
    referenced_type
FROM all_dependencies
WHERE owner = 'APP_OWNER'
  AND name = 'ORDER_API'
ORDER BY referenced_owner, referenced_name;
~~~

`ALL_DEPENDENCIES` helps locate objects referenced by stored objects. If a view or package depends on a dropped or renamed object, errors occur at compile or execution time. Also check `ALL_ERRORS`/`USER_ERRORS` to inspect exact compilation errors.

### 5.4 Inspecting Actual DDL

With appropriate privileges, a DBA or owner can extract DDL:

~~~sql
SELECT DBMS_METADATA.GET_DDL(
    'TABLE',
    'ORDERS',
    'SALES'
)
FROM dual;
~~~

For views, synonyms, packages, or sequences, substitute the corresponding object type. DDL confirms exact names, constraints, columns, and actual structure. Do not use metadata extraction to expose DDL or sensitive definitions to unauthorized users.

## 6. Checking Synonyms and Targets

If SQL uses the name `ORDERS` while the real table is in `SALES`, the application may rely on a private or public synonym.

Inspect all synonyms visible to the user:

~~~sql
SELECT
    owner,
    synonym_name,
    table_owner,
    table_name,
    db_link
FROM all_synonyms
WHERE synonym_name = 'ORDERS'
ORDER BY owner;
~~~

Interpret the output:

- `OWNER`: schema containing the synonym, or `PUBLIC` for a public synonym.
- `TABLE_OWNER`: target owner.
- `TABLE_NAME`: target object.
- Non-null `DB_LINK`: indicates the target is accessed over a database link.

Then check the target:

~~~sql
SELECT owner, object_name, object_type, status
FROM all_objects
WHERE owner = 'SALES'
  AND object_name = 'ORDERS';
~~~

And check privileges on the target:

~~~sql
SELECT
    grantee,
    owner,
    table_name,
    privilege,
    grantable
FROM all_tab_privs
WHERE owner = 'SALES'
  AND table_name = 'ORDERS'
ORDER BY grantee, privilege;
~~~

If `APP_RUNTIME` does not appear in the output, the privilege might be granted through a role. Check roles and their enabled status. For definer-rights PL/SQL, role grants do not substitute for direct grants, as explained later.

### 6.1 Creating a Private Synonym After Confirming the Target

For example, a DBA or owner creates a synonym for the user:

~~~sql
CREATE SYNONYM app_runtime.orders
FOR sales.orders;
~~~

If the user creates a synonym in their own schema, they need `CREATE SYNONYM`. Creating a public synonym requires `CREATE PUBLIC SYNONYM`, which is normally reserved for administrators.

After creating the synonym, the user still needs the object privilege on `SALES.ORDERS`:

~~~sql
GRANT SELECT ON sales.orders TO app_runtime;
~~~

Do not create synonyms merely to hide owners before resolving access privileges.

## 7. Distinguishing Object Privileges and System Privileges

Oracle has two main privilege categories relevant to these errors.

### 7.1 Object Privileges

Object privileges authorize actions on a specific object.

| Privilege | Example Operations |
|---|---|
| SELECT | Read a table/view or certain selectable objects |
| INSERT | Insert rows |
| UPDATE | Update columns/rows |
| DELETE | Delete rows |
| REFERENCES | Create a foreign key referencing the object's key |
| ALTER | Alter object structure where supported |
| INDEX | Create indexes on the object as permitted |
| EXECUTE | Invoke an executable procedure, function, package, or type |

Certain objects have specialized privileges. Consult the Oracle SQL Language Reference for the exact object type and release.

Example granting `SELECT` on a table:

~~~sql
GRANT SELECT ON sales.orders TO app_runtime;
~~~

Grant only the DML needed:

~~~sql
GRANT SELECT, INSERT, UPDATE ON sales.orders TO app_runtime;
~~~

Do not grant `DELETE` if the service never deletes data.

### 7.2 System Privileges

System privileges authorize categories of operations at the schema or database scope.

| Privilege | Example |
|---|---|
| CREATE SESSION | Log in to the database |
| CREATE TABLE | Create tables in the user's own schema |
| CREATE VIEW | Create views in the user's own schema |
| CREATE SEQUENCE | Create sequences in the user's own schema |
| CREATE PROCEDURE | Create procedures/functions/packages in the user's own schema |
| CREATE SYNONYM | Create private synonyms in the user's own schema |
| CREATE ANY TABLE | Create tables in another schema |
| ALTER ANY TABLE | Alter tables owned by another schema |
| DROP ANY TABLE | Drop tables owned by another schema |
| CREATE ANY VIEW | Create views in another schema |
| EXECUTE ANY PROCEDURE | Execute procedures owned by another schema |

`ANY` privileges have broad scope and can affect objects across many schemas. Never grant them to a runtime account just to make a query work.

### 7.3 Object Creation Privileges and Tablespace Quota

To create a table in their own schema, a user typically needs `CREATE TABLE` and sufficient quota on a tablespace (or `UNLIMITED TABLESPACE` per policy).

Example:

~~~sql
GRANT CREATE SESSION, CREATE TABLE TO app_developer;
ALTER USER app_developer QUOTA 100M ON app_data;
~~~

Quota is granted on a specific tablespace. Insufficient quota normally raises ORA-01950 rather than ORA-01031.

Do not grant `UNLIMITED TABLESPACE` by default to every user. Assign quotas sized to capacity and environment.

## 8. Granting Privileges on the Right Object

Suppose `SALES` owns `ORDERS` and the application `APP_RUNTIME` needs to read orders.

### 8.1 Granting SELECT Directly

The owner or DBA runs:

~~~sql
GRANT SELECT ON sales.orders TO app_runtime;
~~~

The application queries:

~~~sql
SELECT order_id, status
FROM sales.orders
WHERE order_id = :order_id;
~~~

If a synonym is desired:

~~~sql
CREATE SYNONYM app_runtime.orders
FOR sales.orders;
~~~

Then:

~~~sql
SELECT order_id, status
FROM orders
WHERE order_id = :order_id;
~~~

The synonym only shortens the name; the `SELECT` grant is still required.

### 8.2 Granting Multiple Object Privileges

For example, if a service needs to read and update status:

~~~sql
GRANT SELECT, UPDATE ON sales.orders TO app_runtime;
~~~

You can restrict columns for certain object privileges such as `UPDATE`:

~~~sql
GRANT UPDATE (status, updated_at)
ON sales.orders
TO app_runtime;
~~~

Column-level privileges limit modification scope when a service only updates specific columns. Verify that the actual `UPDATE` statement does not modify other columns.

### 8.3 EXECUTE Privilege on a Package

If the application calls a package:

~~~sql
GRANT EXECUTE ON sales.order_api TO app_runtime;
~~~

Java invoking a procedure via JDBC:

~~~java
try (Connection connection = dataSource.getConnection();
     CallableStatement statement =
         connection.prepareCall("{ call sales.order_api.get_order(?, ?) }")) {

    statement.setLong(1, orderId);
    statement.registerOutParameter(2, java.sql.Types.VARCHAR);
    statement.execute();

    String status = statement.getString(2);
}
~~~

`EXECUTE` on a package allows calling public members exposed in the package spec. It does not automatically grant `APP_RUNTIME` direct `SELECT` on all tables the package accesses. A definer-rights package runs with the owner's privileges during execution; internal privileges must be designed separately.

### 8.4 Privileges on Views

If `APP_RUNTIME` only needs to read a restricted dataset, grant `SELECT` on a view:

~~~sql
GRANT SELECT ON sales.order_summary_v TO app_runtime;
~~~

The view owner needs the appropriate privileges on underlying objects to create/maintain the view. Consumers typically only need privileges on the view, subject to view and underlying object privilege rules. Do not grant broad access to all base tables when the application only needs the view.

## 9. Direct Grants vs. Role Grants

This is a frequent reason why a SQL statement runs in SQL Developer while a stored procedure fails with ORA-00942 or ORA-01031.

### 9.1 What Is a Role?

A role is a named group of privileges granted to users or other roles. Roles simplify group privilege management.

Example:

~~~sql
CREATE ROLE order_reader_role;

GRANT SELECT ON sales.orders TO order_reader_role;

GRANT order_reader_role TO app_runtime;
~~~

When the role is enabled in the session, `APP_RUNTIME` can use the `SELECT` privilege granted via the role in normal interactive SQL.

Check active roles:

~~~sql
SELECT role
FROM session_roles
ORDER BY role;
~~~

A role granted to a user is not necessarily enabled in a session; it may be restricted by default roles, `SET ROLE`, secure application roles, or authentication mechanisms.

### 9.2 Definer-Rights PL/SQL

By default, stored procedures, functions, and packages run with the owner's privileges (definer rights), unless declared with `AUTHID CURRENT_USER`.

Inside a definer-rights unit:

- The definer's privileges govern execution-time checks.
- Ordinary roles of the definer are disabled while the unit executes.
- Privileges required by static SQL inside the stored unit must be granted directly to the owner per compile-time privilege checking rules.
- Granting privileges only via a role to the owner can allow interactive SQL to succeed while the stored unit fails to compile or execute.

For example, `APP_OWNER` creates a package reading `SALES.ORDERS`. Granting a role to `APP_OWNER` is not enough. Grant directly:

~~~sql
GRANT SELECT ON sales.orders TO app_owner;
~~~

Then compile the package as `APP_OWNER`.

Do not grant underlying table privileges to `APP_RUNTIME` if the definer-rights package is owned by `APP_OWNER` and runtime only needs `EXECUTE` on the package. Privileges must be granted to the exact principal executing each operation within its privilege context.

### 9.3 Example Error Caused by Role-Based Privileges

Suppose:

~~~sql
CREATE ROLE sales_read_role;
GRANT SELECT ON sales.orders TO sales_read_role;
GRANT sales_read_role TO app_owner;
~~~

`APP_OWNER` can run directly:

~~~sql
SELECT * FROM sales.orders;
~~~

if the role is enabled. However, when compiling a definer-rights procedure with static SQL:

~~~sql
CREATE OR REPLACE PROCEDURE app_owner.read_orders
AS
    l_count NUMBER;
BEGIN
    SELECT COUNT(*)
      INTO l_count
      FROM sales.orders;
END;
/
~~~

Oracle fails compilation because the owner lacks a direct grant on `SALES.ORDERS`. Grant directly:

~~~sql
GRANT SELECT ON sales.orders TO app_owner;
~~~

Then recompile:

~~~sql
ALTER PROCEDURE app_owner.read_orders COMPILE;
~~~

Check compilation errors:

~~~sql
SELECT line, position, text
FROM all_errors
WHERE owner = 'APP_OWNER'
  AND name = 'READ_ORDERS'
  AND type = 'PROCEDURE'
ORDER BY sequence;
~~~

### 9.4 AUTHID CURRENT_USER and Invoker Rights

A unit declared with:

~~~sql
CREATE OR REPLACE PROCEDURE app_owner.read_orders
AUTHID CURRENT_USER
AS
    l_count NUMBER;
BEGIN
    SELECT COUNT(*)
      INTO l_count
      FROM sales.orders;
END;
/
~~~

`AUTHID CURRENT_USER` runs the unit with the invoker's privileges at runtime. Enabled roles of the invoker can participate in privilege checks under invoker-rights rules. This is useful when a single unit should respect each caller's privileges, though it makes authorization dependent on the calling user.

Distinguish privileges needed to compile the unit from privileges needed at runtime. Static SQL is resolved at compile time; the owner still needs appropriate privileges to reference the objects. At runtime under invoker rights, privileges are checked against the invoker. Check both the compiling owner and the caller rather than switching `AUTHID` blindly to bypass an error.

### 9.5 Dynamic SQL

Dynamic SQL constructs statements at runtime:

~~~sql
EXECUTE IMMEDIATE
    'SELECT COUNT(*) FROM sales.orders'
INTO l_count;
~~~

Dynamic SQL does not remove privilege requirements. In a definer-rights unit, the definer's roles remain disabled; privileges are evaluated in the definer's privilege context. In an invoker-rights unit, runtime privileges follow the invoker under invoker-rights rules.

Dynamic SQL also introduces SQL injection risk if user input is concatenated into identifiers or literals. Use bind variables for data values; identifiers must be whitelisted and validated under strict rules because bind variables cannot replace table or column names.

## 10. Privileges Needed to Create Views and Stored Objects

Creating an object differs from querying an existing object. A user may be able to `SELECT` from a table while lacking `CREATE VIEW`; or hold `CREATE VIEW` while lacking a direct `SELECT` grant on the underlying table.

### 10.1 Creating a View in Your Own Schema

For example, `APP_REPORT` needs to create a view on `SALES.ORDERS`:

~~~sql
GRANT CREATE VIEW TO app_report;
GRANT SELECT ON sales.orders TO app_report;
~~~

Then as `APP_REPORT`:

~~~sql
CREATE OR REPLACE VIEW order_summary_v AS
SELECT order_id, status
FROM sales.orders;
~~~

For underlying objects in other schemas, the privileges needed to create the view must be granted directly to the view owner per Oracle requirements. Role grants are insufficient for privilege checks when defining a view.

If the view accesses base objects across multiple schemas, grant each required privilege directly to the view owner. Grant exact `SELECT` or required object privileges rather than `SELECT ANY TABLE`.

### 10.2 Creating a View in Another Schema

`CREATE ANY VIEW` allows creating views in other schemas and is a broad system privilege. Only DBAs or controlled deployment accounts should hold this privilege when genuinely required.

Do not grant `CREATE ANY VIEW` to runtime accounts. It is better to deploy using the owning schema or a release process with controlled temporary privileges.

### 10.3 Creating Procedures/Packages

To create a procedure in their own schema, a user needs `CREATE PROCEDURE`. Creating one in another schema requires `CREATE ANY PROCEDURE`, a much broader privilege.

Example:

~~~sql
GRANT CREATE PROCEDURE TO app_owner;
~~~

If the procedure references objects in other schemas, appropriate direct privileges on those objects are required at compile and runtime depending on `AUTHID`.

### 10.4 Creating Sequences and Synonyms

Create a sequence in your own schema:

~~~sql
GRANT CREATE SEQUENCE TO app_owner;
~~~

Create a private synonym:

~~~sql
GRANT CREATE SYNONYM TO app_runtime;
~~~

Creating a public synonym requires the administrative `CREATE PUBLIC SYNONYM` privilege. Do not grant this privilege to normal applications.

## 11. Checking Existing Privileges

### 11.1 Object Grants

~~~sql
SELECT
    grantee,
    owner,
    table_name,
    privilege,
    grantable
FROM all_tab_privs
WHERE owner = 'SALES'
  AND table_name = 'ORDERS'
ORDER BY grantee, privilege;
~~~

Check privileges received by the current user:

~~~sql
SELECT
    owner,
    table_name,
    privilege,
    grantor,
    grantable
FROM user_tab_privs_recd
ORDER BY owner, table_name, privilege;
~~~

`ALL_TAB_PRIVS` and related views show results scoped to current privileges. DBAs can use `DBA_TAB_PRIVS` for full visibility.

### 11.2 Role-Based Privileges

~~~sql
SELECT granted_role, default_role
FROM user_role_privs
ORDER BY granted_role;

SELECT role
FROM session_roles
ORDER BY role;

SELECT role, owner, table_name, privilege
FROM role_tab_privs
WHERE owner = 'SALES'
  AND table_name = 'ORDERS'
ORDER BY role, privilege;
~~~

`USER_ROLE_PRIVS` lists granted roles and default roles per metadata; `SESSION_ROLES` lists roles currently enabled in the session. `ROLE_TAB_PRIVS` shows object privileges granted to roles.

If a user receives a role via another role, trace the role hierarchy. DBAs can inspect `DBA_ROLE_PRIVS`/`ROLE_ROLE_PRIVS` and `DBA_TAB_PRIVS`.

### 11.3 System Privileges

~~~sql
SELECT privilege
FROM session_privs
ORDER BY privilege;
~~~

`SESSION_PRIVS` lists system privileges currently active in the session. `USER_SYS_PRIVS` lists system privileges granted directly to the user:

~~~sql
SELECT privilege, admin_option
FROM user_sys_privs
ORDER BY privilege;
~~~

Privileges via roles can be inspected through `ROLE_SYS_PRIVS` and `SESSION_ROLES`. Distinguish granted privileges, default privileges, and currently enabled privileges.

### 11.4 Finding Users Granted Access to an Object

A DBA can query:

~~~sql
SELECT
    grantee,
    privilege,
    grantable
FROM dba_tab_privs
WHERE owner = 'SALES'
  AND table_name = 'ORDERS'
ORDER BY grantee, privilege;
~~~

`DBA_TAB_PRIVS` requires appropriate catalog privileges. Never grant database-wide catalog access to an application just for self-diagnostics.

## 12. Common Scenarios Causing ORA-00942

### 12.1 Connecting as the Wrong User

SQL works as `SALES`, but the application connects as `APP_RUNTIME`. `SALES` sees `SALES.ORDERS` as the owner; `APP_RUNTIME` has neither the privilege nor an appropriate synonym.

Resolution:

- Read `SESSION_USER` from the application connection.
- Identify the object owner.
- Grant the exact object privilege or invoke the exposed API/package.
- Use owner qualification where appropriate.

### 12.2 Object Resides in Another Schema

The application runs:

~~~sql
SELECT * FROM orders;
~~~

while the object is `SALES.ORDERS` and `CURRENT_SCHEMA` is `APP_RUNTIME`.

You can fix the SQL:

~~~sql
SELECT * FROM sales.orders;
~~~

or create a private synonym for `APP_RUNTIME`. Both approaches still require the object privilege.

### 12.3 Synonym Target Dropped or Renamed

Inspect `ALL_SYNONYMS`, then inspect the target in `ALL_OBJECTS`/`DBA_OBJECTS`. If the target was renamed, update the synonym per an approved migration and check other consumers.

### 12.4 Wrong PDB or Service

A single database can host multiple PDBs. `SALES.ORDERS` exists in `PDB_DEV` but not in `PDB_TEST`. The application may be using the wrong JDBC URL or service name.

Check:

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'DB_NAME') AS db_name,
    SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;
~~~

Cross-check with the JDBC URL, service registration, datasource environment variables, and deployment secrets/config. Do not alter grants in a PDB different from the one the application actually connects to.

### 12.5 Object Not Deployed Yet

If a migration did not run or failed, the object may not exist yet. Check release version, migration history, and schema owner. Do not create objects manually in production if schema migrations are the source of truth; fix the migration/deployment through the proper pipeline.

### 12.6 View or Synonym with a Quoted Name

If an object was created with a quoted name, unquoted queries look for a different uppercase name. Check `ALL_OBJECTS`/`ALL_SYNONYMS` for the exact name and fix the SQL/ORM mapping.

### 12.7 View Depends on an Unavailable Object

A view may exist, yet querying it fails due to dependencies, `INVALID` status, or missing privileges on base objects. Check:

~~~sql
SELECT owner, object_name, status
FROM all_objects
WHERE owner = 'SALES'
  AND object_name = 'ORDER_SUMMARY_V';
~~~

Then inspect `ALL_ERRORS` and `ALL_DEPENDENCIES`. Invalid views may raise ORA-04063 or other errors; inspect the complete error stack.

## 13. Common Scenarios Causing ORA-01031

### 13.1 Missing DML Privilege

`APP_RUNTIME` can read a table but fails to `INSERT`:

~~~sql
INSERT INTO sales.orders (order_id, status)
VALUES (:id, 'NEW');
~~~

If only `SELECT` was granted, `INSERT` returns a privilege error. Grant the needed privilege:

~~~sql
GRANT INSERT ON sales.orders TO app_runtime;
~~~

If the service needs `UPDATE` but not `DELETE`, grant only `INSERT`/`UPDATE`/`SELECT`.

### 13.2 Missing CREATE Privilege in Own Schema

`APP_OWNER` runs `CREATE TABLE` without `CREATE TABLE` privilege:

~~~sql
CREATE TABLE staging_orders (
    order_id NUMBER PRIMARY KEY
);
~~~

A DBA can grant:

~~~sql
GRANT CREATE TABLE TO app_owner;
ALTER USER app_owner QUOTA 100M ON app_data;
~~~

Check default tablespace, quota, and policy. If the error is ORA-01950, fix quota instead of granting `CREATE ANY TABLE`.

### 13.3 Using ANY Privileges to Solve the Wrong Problem

If `APP_RUNTIME` needs to `SELECT` `SALES.ORDERS`, do not grant:

~~~sql
GRANT SELECT ANY TABLE TO app_runtime;
~~~

This privilege allows reading tables far outside the business scope. Instead:

~~~sql
GRANT SELECT ON sales.orders TO app_runtime;
~~~

Similarly, never grant `INSERT ANY TABLE`, `UPDATE ANY TABLE`, `DELETE ANY TABLE`, `ALTER ANY TABLE`, or `DROP ANY TABLE` just to fix an error on a single object.

### 13.4 Missing EXECUTE Privilege

If the application calls package `SALES.ORDER_API` without `EXECUTE`:

~~~sql
GRANT EXECUTE ON sales.order_api TO app_runtime;
~~~

Then verify the package spec, synonym, and procedure name. If the package invokes other objects, internal access depends on `AUTHID` and owner/invoker privileges; `EXECUTE` on a package is not a blanket grant across the entire schema.

### 13.5 Missing GRANT OPTION

A user with `SELECT` on `SALES.ORDERS` does not automatically have permission to grant `SELECT` to another user.

To re-grant an object privilege, the grantor needs the appropriate authority—typically being the object owner or holding the privilege `WITH GRANT OPTION`.

Example owner grant:

~~~sql
GRANT SELECT ON sales.orders
TO app_runtime
WITH GRANT OPTION;
~~~

Use `WITH GRANT OPTION` only if `APP_RUNTIME` truly needs to propagate that privilege. Do not grant it broadly out of habit.

For system privileges and roles, `ADMIN OPTION` is the corresponding mechanism; it differs from `GRANT OPTION` on object privileges.

## 14. Direct Grants, Roles, and Code Paths

Not every operation evaluates privileges the same way. Identify whether the code runs directly, in a definer-rights stored procedure, an invoker-rights unit, a trigger, a view, or a job.

### 14.1 Direct SQL from JDBC

Interactive SQL in a session can use directly granted system/object privileges and enabled roles. If a role is not enabled, privileges granted only through that role do not apply.

Check `SESSION_ROLES` and `SESSION_PRIVS` from the exact connection.

### 14.2 Definer-Rights Stored Procedures

This is the common default for named PL/SQL units. The owner's privileges govern execution; roles are typically disabled inside the unit. Static SQL in the unit requires the appropriate privileges granted directly to the owner.

If a procedure reads `SALES.ORDERS`, grant `SELECT` directly to the procedure owner. The caller normally needs only `EXECUTE` on the procedure when the API is designed this way.

### 14.3 Invoker Rights

`AUTHID CURRENT_USER` bases runtime privileges on the invoker. This is an intentional choice when a unit must honor the caller's permissions.

Check:

- Can the owner compile the unit and resolve objects?
- Does the invoker hold the runtime privileges?
- Are required roles enabled?
- Does dynamic SQL reference objects derived from input?
- Could the unit unintentionally escalate privileges?

### 14.4 Triggers

Triggers execute under the database and trigger security model. Do not assume the calling session's roles supply privileges for SQL inside a trigger. If a trigger references objects outside its owner's schema, verify direct grants for the trigger owner and dependencies.

A trigger with a privilege error can cause DML on the base table to fail even though the user holds `INSERT`/`UPDATE` on that base table. Inspect `ALL_ERRORS`, `ALL_DEPENDENCIES`, and trigger source.

### 14.5 Jobs and Schedulers

Jobs may run under different credentials/schemas than interactive sessions. Check the job owner, credential, `job_action`, enabled state, and privilege context. Do not use SQL Developer results to assume a job holds the same privileges.

## 15. Views, Packages, and Underlying Object Privileges

A common design pattern keeps tables in an owner schema while application users access data through views or packages.

Example:

~~~text
SALES schema
  ORDERS
  CUSTOMERS
  ORDER_SUMMARY_V
  ORDER_API package

APP_RUNTIME
  SELECT on ORDER_SUMMARY_V
  EXECUTE on ORDER_API
~~~

The view/package owner holds access to underlying data. Runtime receives only the exposed interface.

### 15.1 View Owner Privileges

When creating a view on objects in another schema, the view owner needs the appropriate privileges on the base objects granted directly. Role grants do not satisfy privilege verification for view definitions.

Example:

~~~sql
GRANT SELECT ON sales.orders TO app_report;

-- Run as APP_REPORT:
CREATE OR REPLACE VIEW order_summary_v AS
SELECT order_id, status
FROM sales.orders;
~~~

Then:

~~~sql
GRANT SELECT ON app_report.order_summary_v TO app_runtime;
~~~

`APP_RUNTIME` can read the view without needing direct `SELECT` on `SALES.ORDERS` if the view is properly created and configured. If the view uses invoker rights or specialized security features, review the corresponding rules.

### 15.2 Definer-Rights Package Privileges

The package owner holds direct grants on the tables the package needs. Callers need only `EXECUTE` on the package. This reduces the privilege surface of runtime users.

However, the package must validate inputs, constrain data access, and avoid unsafe dynamic SQL. A definer-rights package is a security boundary; buggy code could execute operations with higher privileges than the caller.

### 15.3 WITH GRANT OPTION and Views

Granting privileges on views or objects has specific rules. Never grant `WITH GRANT OPTION` simply to work around an application's ORA-01031. If one schema must grant privileges to another, map the owner and grant chain explicitly; having the DBA/owner grant directly is usually simpler.

## 16. Checking Invalid Objects and PL/SQL Compile Errors

An object may exist yet remain in `INVALID` status. That usually raises a different error than ORA-00942, though invalid dependencies can lead to compile or execution errors.

Check status:

~~~sql
SELECT owner, object_name, object_type, status
FROM all_objects
WHERE owner = 'APP_OWNER'
  AND status <> 'VALID'
ORDER BY object_type, object_name;
~~~

Inspect compile errors:

~~~sql
SELECT
    owner,
    name,
    type,
    line,
    position,
    text
FROM all_errors
WHERE owner = 'APP_OWNER'
ORDER BY name, type, sequence;
~~~

If checking your own schema, `USER_ERRORS` can be used.

Recompile objects once dependencies or grants are fixed:

~~~sql
ALTER PACKAGE app_owner.order_api COMPILE;
ALTER PACKAGE app_owner.order_api COMPILE BODY;
~~~

Or compile the corresponding procedure/view. Then re-check `ALL_OBJECTS` and `ALL_ERRORS`.

Do not run mass recompilations in production without understanding dependencies and impact. Modifying objects can invalidate dependents and create compilation load.

## 17. Dynamic SQL and Object Names from Input

Dynamic SQL can trigger ORA-00942 if an object name built from input specifies an invalid schema or identifier.

Dangerous example:

~~~sql
l_sql := 'SELECT COUNT(*) FROM ' || p_table_name;
EXECUTE IMMEDIATE l_sql INTO l_count;
~~~

`p_table_name` could be empty, misspelled, point to an unintended schema, or be abused for SQL injection.

### 17.1 Whitelisting Identifiers

Table names cannot be bound like data values. When selecting a table dynamically, use a whitelist:

~~~sql
CASE p_source
    WHEN 'ORDERS' THEN
        l_table_name := 'SALES.ORDERS';
    WHEN 'CUSTOMERS' THEN
        l_table_name := 'SALES.CUSTOMERS';
    ELSE
        RAISE_APPLICATION_ERROR(-20001, 'Unsupported source');
END CASE;

l_sql := 'SELECT COUNT(*) FROM ' || l_table_name;
EXECUTE IMMEDIATE l_sql INTO l_count;
~~~

The whitelist must be a controlled internal mapping, never raw identifiers taken directly from requests.

### 17.2 Binding Values

~~~sql
l_sql := 'SELECT COUNT(*) FROM sales.orders WHERE status = :1';
EXECUTE IMMEDIATE l_sql INTO l_count USING p_status;
~~~

Bind variables protect data values and enable SQL reuse. They do not replace object-name validation.

### 17.3 DBMS_ASSERT

Oracle provides `DBMS_ASSERT` to validate certain identifier and SQL name formats. It is a validation helper, not a replacement for whitelisting and authorization. A syntactically valid name can still reference an object the caller is not authorized to access.

## 18. Errors When Calling Objects Through Synonyms, Views, and Packages

When a statement does not reference a table directly, trace each layer.

Example:

~~~text
APP_RUNTIME query
    |
    v
APP_RUNTIME.ORDERS synonym
    |
    v
SALES.ORDER_SUMMARY_V view
    |
    v
SALES.ORDERS table
    |
    v
SALES.CUSTOMERS table
~~~

Investigate in order:

1. Does `APP_RUNTIME` have a synonym `ORDERS`?
2. Which owner/object does the synonym point to?
3. Does the target view exist and is it `VALID`?
4. Do the view's dependencies still exist?
5. Does the view owner hold direct privileges on the underlying objects?
6. Does `APP_RUNTIME` have `SELECT` on the view?
7. If the view calls a function/package, are owner and `EXECUTE` privileges aligned?
8. If a database link is involved, are the remote identity and remote grants right?

An error at the lowest layer can surface on the top-level SQL statement. Do not grant `APP_RUNTIME` direct privileges on all base objects before verifying the security design.

## 19. Container Databases, PDBs, and Editions

In multitenant environments, identical schema/object names can exist across multiple PDBs. A local user in one PDB does not automatically hold privileges in another PDB.

### 19.1 Identifying the Container

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;
~~~

Verify the service in the JDBC URL matches the intended PDB. Do not issue grants in CDB root when the application connects to a PDB, or vice versa, without understanding common vs. local users.

### 19.2 Common and Local Users

Common users are scoped to containers based on how grants and container clauses are applied; local users belong to a specific PDB. Privileges can be granted locally or commonly depending on object, user, and requirements.

Do not use `CONTAINER=ALL` as a quick fix. It modifies privilege scope across multiple containers and requires administrative review.

### 19.3 Edition-Based Redefinition

If the database uses edition-based redefinition, objects can have editioned versions. The same name can resolve differently depending on the session's current edition.

Inspect `CURRENT_EDITION_NAME` and editionable object metadata. An application connected to a different edition may see a different package/view version than SQL Developer. This is a deployment/name resolution issue, not necessarily a missing grant.

## 20. Diagnostic Procedure for ORA-00942

Follow this sequence so you do not alter privileges before knowing the root cause.

### Step 1: Collect the SQL Statement and Full Error Stack

Record the exact SQL, schema qualification, bind types, timestamp, application service, database user, and connection pool. Do not save only the top ORA-00942 line if the stack includes remote or PL/SQL errors.

### Step 2: Identify Session Context

Query `SESSION_USER`, `CURRENT_USER`, `CURRENT_SCHEMA`, `CON_NAME`, `SERVICE_NAME`, and `CURRENT_EDITION_NAME` from the failing connection.

### Step 3: Check the Object Name

Determine whether SQL references an unqualified name, `schema.object`, a synonym, or a remote object. Check quoted identifiers and casing.

### Step 4: Locate the Object and Synonyms

Use `USER_OBJECTS`, `ALL_OBJECTS`, `ALL_SYNONYMS`, and related views. If the object is not visible, have a DBA/owner confirm using `DBA_OBJECTS` in the right PDB.

### Step 5: Check Target and Dependencies

For synonyms, inspect the target. For views/packages, inspect status, dependencies, and compile errors. For database links, inspect the remote database and remote user.

### Step 6: Check Privileges

Inspect `ALL_TAB_PRIVS`, `SESSION_ROLES`, and `SESSION_PRIVS`. For definer-rights PL/SQL, verify direct grants to the owner rather than only caller roles.

### Step 7: Fix the Right Layer

- Wrong schema/name: fix the SQL or mapping.
- Wrong synonym: fix the synonym after confirming the target.
- Wrong PDB/service: fix connection configuration.
- Missing object privilege: owner/DBA grants the right object privilege.
- Missing direct grant for stored unit: grant to the definer and recompile.
- Object not deployed: run migration in the proper environment.

### Step 8: Re-Test with the Same User

Verify from the application connection, not only from a DBA account.

## 21. Diagnostic Procedure for ORA-01031

### Step 1: Identify the Failing Operation

Did the error occur on `SELECT`, DML, `CREATE`, `ALTER`, `DROP`, `GRANT`, `EXECUTE`, or inside PL/SQL? Required privileges vary by operation and object.

### Step 2: Identify the Principal

Determine `SESSION_USER`, `CURRENT_USER`, the stored unit owner, and the invoker if applicable. For jobs, determine the job owner/credential.

### Step 3: Identify the Required Privilege

Examples:

- `SELECT` on another schema's object: `SELECT` object privilege.
- Calling a package: `EXECUTE` on the package.
- Creating a table in own schema: `CREATE TABLE` and quota.
- Creating a view: `CREATE VIEW` and direct grants on base objects.
- Creating an object in another schema: the matching `ANY` privilege, typically restricted to controlled deployment accounts.

### Step 4: Check the Grant Path

Inspect direct grants, role grants, enabled roles, and grant options. For definer-rights PL/SQL, check direct grants to the owner.

### Step 5: Grant Least Privilege

Owner/DBA grants the exact privilege on the exact object or the system privilege required for deployment. Avoid `DBA`, `ANY`, or `UNLIMITED` privileges unless explicitly required.

### Step 6: Compile and Verify

Recompile stored units if needed. Run the statement as the exact user/service. Test both allowed operations and denied operations to confirm the security boundary holds.

## 22. End-to-End Example: Application Reading Table SALES.ORDERS

Suppose:

- `SALES` owns table `ORDERS`.
- `APP_RUNTIME` is the user connecting from the application.
- The application only needs to read `order_id`, `status`, and `created_at`.
- Direct DML is not required.

### 22.1 Check Connection

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema,
    SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;
~~~

Confirm `SESSION_USER` is `APP_RUNTIME` and the service/PDB matches the target environment.

### 22.2 Check Object

DBA or owner:

~~~sql
SELECT owner, object_name, object_type, status
FROM dba_objects
WHERE owner = 'SALES'
  AND object_name = 'ORDERS';
~~~

If the object exists, verify its exact object type and status.

### 22.3 Grant Least Privilege

Owner `SALES`:

~~~sql
GRANT SELECT ON sales.orders TO app_runtime;
~~~

### 22.4 Qualified Query

~~~sql
SELECT order_id, status, created_at
FROM sales.orders
WHERE order_id = :order_id;
~~~

### 22.5 Verify from the Application

Use the actual `APP_RUNTIME` datasource. Record the session context, run the query, and verify results. If a synonym is needed, create a private synonym after granting and test name resolution.

Never grant `SELECT ANY TABLE` because a single query could not access `SALES.ORDERS`.

## 23. End-to-End Example: Definer-Rights Package

Suppose `SALES` owns `ORDERS`, `APP_OWNER` owns the API package, and `APP_RUNTIME` should only invoke the package.

### 23.1 Grant Privilege to Package Owner

~~~sql
GRANT SELECT ON sales.orders TO app_owner;
~~~

The privilege is granted directly to `APP_OWNER`.

### 23.2 Create the Package

~~~sql
CREATE OR REPLACE PACKAGE app_owner.order_api AS
    PROCEDURE get_order_count(p_count OUT NUMBER);
END order_api;
/

CREATE OR REPLACE PACKAGE BODY app_owner.order_api AS
    PROCEDURE get_order_count(p_count OUT NUMBER) IS
    BEGIN
        SELECT COUNT(*)
          INTO p_count
          FROM sales.orders;
    END get_order_count;
END order_api;
/
~~~

### 23.3 Grant EXECUTE to Runtime

~~~sql
GRANT EXECUTE ON app_owner.order_api TO app_runtime;
~~~

`APP_RUNTIME` only needs to call the package:

~~~sql
BEGIN
    app_owner.order_api.get_order_count(:count_value);
END;
/
~~~

If the package is invalid, check `ALL_ERRORS` for `APP_OWNER`. If the caller cannot invoke it, check `EXECUTE` and name resolution. If the package owner lacks privileges on `SALES.ORDERS`, grant directly to `APP_OWNER` and recompile.

## 24. Security and the Principle of Least Privilege

Privileges are part of security design. Overly broad grants can turn an access error on one table into read/write access to data far outside the application's scope.

Principles:

- Separate owner schemas and runtime schemas where appropriate.
- Runtime accounts should hold only privileges needed for active functionality.
- Prefer object grants on specific tables, views, or packages.
- Restrict `ANY` privileges to controlled deployment accounts.
- Never grant `DBA` to applications.
- Never grant `CREATE PUBLIC SYNONYM` to runtime accounts.
- Never grant `GRANT OPTION` or `ADMIN OPTION` unless privilege delegation is required.
- Use packages/views as interfaces when controlling data access.
- Verify privileges in both direct SQL and PL/SQL privilege contexts.
- Audit grant/revoke actions and synonym changes.
- Never log database link passwords or secrets.
- Avoid exposing internal object details to end clients unnecessarily.

### 24.1 Separating Deployment and Runtime Accounts

A common model:

| User | Responsibility | Typical Privileges |
|---|---|---|
| SALES_OWNER | Owns business tables | Create/alter objects in schema `SALES` |
| APP_OWNER | Owns view/package interfaces | Direct grants needed on base objects; `CREATE VIEW`/`PROCEDURE` |
| APP_RUNTIME | Application connection | `SELECT` on views and `EXECUTE` on packages, or narrow object grants |
| MIGRATION_USER | Runs schema migrations | Controlled DDL privileges, used only during releases |

Do not make `APP_RUNTIME` the owner of all objects if the application only needs DML/execute. Separating owner and runtime limits blast radius if application credentials are compromised.

### 24.2 Auditing Privileges

DBAs can query direct and role-based grants, recording who granted them, when, and why. Release pipelines should maintain an intended grant list and check for drift across DEV/TEST/PROD.

Do not revoke a privilege simply because a grant looks unfamiliar. Inspect dependencies, audit trails, jobs, and packages before revoking.

## 25. Common Anti-Patterns to Avoid

| Practice | Risk | Better Practice |
|---|---|---|
| Granting `DBA` to `APP_RUNTIME` | Nearly full database privileges | Grant minimal object privileges |
| Granting `SELECT ANY TABLE` to read one table | Opens read access across schemas | `GRANT SELECT ON owner.table` |
| Creating public synonyms for every object | Affects name resolution database-wide | Private synonyms or schema qualification |
| Creating a synonym and assuming access is granted | Synonyms do not grant privileges | Grant on the target object |
| Using `ALTER SESSION CURRENT_SCHEMA` to bypass grants | Does not add any privileges | Grant exact object privileges |
| Testing with a DBA account and assuming the app has access | DBAs have different privileges than app users | Test using the exact datasource/user |
| Granting only via role for definer-rights packages | Roles are disabled inside the unit | Grant directly to the package owner |
| Granting `CREATE ANY TABLE` to runtime | Allows creating objects in other schemas | Use a controlled deployment user |
| Running `SELECT` before `INSERT` to prevent duplicates | Race condition | `UNIQUE` constraint |
| Fixing synonyms in the wrong PDB | App still fails or points to wrong data | Verify service/container first |
| Recompiling all objects in production | Can trigger invalidations and compile load | Compile only relevant objects deliberately |
| Renaming quoted objects arbitrarily | Breaks dependent consumers | Verify dependencies and migrations |

## 26. Investigation Checklist

### Identity and Environment

- [ ] Collected the full error stack and exact SQL statement.
- [ ] Identified `SESSION_USER`.
- [ ] Identified `CURRENT_USER` and `CURRENT_SCHEMA`.
- [ ] Identified service, database, and PDB/container.
- [ ] Checked edition if the environment uses edition-based redefinition.
- [ ] Reproduced using the exact application user and connection.

### Object Resolution

- [ ] Identified full object name and object type.
- [ ] Checked owner/schema.
- [ ] Checked casing and quoted identifiers.
- [ ] Checked private/public synonyms.
- [ ] Verified the synonym target still exists.
- [ ] Checked database links if present.
- [ ] Checked view/package dependencies and status.
- [ ] Confirmed the object is deployed in the right PDB.

### Privileges

- [ ] Identified which privilege the operation requires.
- [ ] Checked object grants.
- [ ] Checked system privileges.
- [ ] Checked granted roles and currently enabled roles.
- [ ] Distinguished direct grants from role grants.
- [ ] Determined definer-rights vs. invoker-rights.
- [ ] Checked direct grants to the owner of stored units/views where needed.
- [ ] Checked `GRANT OPTION`/`ADMIN OPTION` if privilege-granting operations are involved.
- [ ] Checked tablespace quota if the error involves segment/table creation.

### Remediation and Verification

- [ ] Fixed only the specific SQL, schema, synonym, service, or grant causing the error.
- [ ] Avoided granting `DBA`/broad `ANY` privileges to runtime.
- [ ] Recompiled invalid objects if needed.
- [ ] Re-tested using the exact application user.
- [ ] Verified both permitted operations and operations that must remain denied.
- [ ] Documented grant/synonym/migration changes for reproducibility.

## 27. Conclusion

ORA-00942 usually relates to Oracle failing to resolve a table/view name in the current context or the user lacking access to that object. ORA-01031 indicates the operation lacks a required privilege. Both must be investigated from the exact session, schema, service/PDB, and privilege context.

Trace the object name from SQL through schema, synonym, view, or database link; verify the object exists in the right container; then inspect object privileges, system privileges, and roles. In particular, privileges granted through roles in interactive SQL do not replace the direct grants required by static SQL in definer-rights PL/SQL or view definitions.

The sustainable fix is to use schema qualification where appropriate, manage synonyms intentionally, grant least-privilege object grants, separate schema owners from runtime users, and verify with the actual application connection. Never use `DBA` or broad `ANY` privileges to mask a name-resolution error or a missing grant.
