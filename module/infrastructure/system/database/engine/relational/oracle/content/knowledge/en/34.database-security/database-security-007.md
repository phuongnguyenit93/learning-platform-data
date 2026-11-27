# Privilege boundaries across synonyms, views, packages, and database links

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Security  
> **Objective:** Understand how Oracle distinguishes name resolution from privilege checking; design access boundaries using synonyms, views, and PL/SQL packages; choose between AUTHID DEFINER and AUTHID CURRENT_USER; understand direct privileges, roles, and INHERIT PRIVILEGES; control local/remote identity, usage rights, and data privileges across database links; diagnose privilege errors and build a least-privilege model.

## 1. Four objects, four distinct roles

Synonyms, views, packages, and database links often appear together in a multi-schema architecture. However, they solve different problems:

| Component | Primary role | Does it automatically grant data access? |
|---|---|---|
| Synonym | Alias for resolving an object name | No |
| View | Exposes a set of columns/rows or expressions from a data source | Users need privileges on the view; underlying table privileges are checked per view rules |
| PL/SQL package | Encapsulates operations and provides a controlled API | Callers need EXECUTE; privileges inside the code depend on AUTHID and owner/invoker rights |
| Database link | Connects from a local database to a remote database under an identity | Does not automatically grant privileges on remote objects; the remote identity must hold appropriate privileges |

The key point is that a SQL statement may pass through multiple naming layers and multiple schemas, yet Oracle must still determine:

1. Which object does the name resolve to?
2. Who is the executing user?
3. Is the code running with definer rights or invoker rights?
4. Which object privilege or system privilege is required?
5. If a database link is involved, under which identity does the remote session log in?
6. Does the remote identity have privileges on the target object?

A synonym can shorten an access name, but it does not give the user extra privileges. A view can restrict exposed columns and rows, but becomes meaningless if the user is also granted direct privileges on the base table. A package can provide an API instead of direct DML grants, but requires controlling definer rights and dynamic SQL. A database link introduces an additional authentication and authorization boundary at the remote database.

## 2. Schema model separating data and API

A common organizational pattern separates the data-owning schema, the API-exposing schema, and the application user schema.

~~~text
                 Local database
+------------------------------------------------+
|                                                |
|  DATA_OWNER                                    |
|  +----------------------+                      |
|  | ORDERS               |  base data tables    |
|  | CUSTOMERS            |                      |
|  +----------------------+                      |
|       ^                  ^                     |
|       | direct grants    |                     |
|       |                  |                     |
|  API_OWNER                                     |
|  +----------------------+                      |
|  | ORDER_API package    |  AUTHID DEFINER      |
|  | V_OPEN_ORDERS view   |  or view owner       |
|  +----------------------+                      |
|       ^                  ^                     |
|       | EXECUTE          | SELECT on view      |
|       |                  |                     |
|  APP_USER                                      |
|  +----------------------+                      |
|  | private synonyms     |  convenient names    |
|  +----------------------+                      |
|                                                |
+------------------------------------------------+
                 |
                 | database link
                 v
          Remote database
+------------------------------------------------+
| REMOTE_REPORT_READER                            |
|   minimal SELECT privileges on needed data     |
+------------------------------------------------+
~~~

A deployment structure might use:

- DATA_OWNER owns the tables and data.
- API_OWNER owns packages performing permitted operations.
- APP_USER is the application connection schema.
- APP_READ and APP_WRITE are roles grouping application privileges.
- A dedicated remote account reads only the necessary data in the remote database.

Not every system needs all of these schemas/roles. The goal is to clearly define who owns the data, who manages the API, who invokes the API, and which identity is used at the remote database.

### 2.1. Principle of least privilege

Each principal should only have the privileges required for its job:

- Reporting applications only need SELECT on views or read packages.
- Order-creation applications only need EXECUTE on the order-creation package.
- API_OWNER only has the required SELECT/INSERT/UPDATE on relevant tables.
- The remote account only has SELECT on the tables/views it needs to query.
- Do not grant DBA, ANY TABLE, or schema-wide privileges when only a few objects are needed.

Separate read and write privileges when business needs differ. Do not grant SELECT ANY TABLE to an application just to fix a missing privilege error on a single table.

## 3. Synonym: name resolution, not a security layer

A synonym is an alternative name for a schema object. It lets clients avoid writing the full owner.object or remote object name.

### 3.1. Private synonym

For example, APP_USER creates a synonym pointing to a view:

~~~sql
CREATE SYNONYM open_orders
FOR api_owner.v_open_orders;
~~~

Then it can query:

~~~sql
SELECT order_id, created_at, total_amount
FROM open_orders;
~~~

The synonym only shortens the name. APP_USER still needs SELECT privilege on API_OWNER.V_OPEN_ORDERS.

Grant the privilege:

~~~sql
GRANT SELECT ON api_owner.v_open_orders TO app_user;
~~~

Without privileges on the view, querying through the synonym is still denied. The existence of a synonym does not prove the user can access the target.

### 3.2. Public synonym

A public synonym is created in the shared namespace:

~~~sql
CREATE PUBLIC SYNONYM open_orders
FOR api_owner.v_open_orders;
~~~

The name OPEN_ORDERS can be resolved by other schemas without creating separate private synonyms. However, a public synonym does not grant SELECT, INSERT, UPDATE, DELETE, or EXECUTE on the target object.

A user without privileges on API_OWNER.V_OPEN_ORDERS still cannot read the view merely because a public synonym exists.

Public synonyms can also introduce name resolution risks if the shared name collides with objects/private synonyms in other schemas. Use clear naming, govern ownership, and avoid creating public synonyms casually.

### 3.3. A synonym does not own its target

Dropping a synonym only removes the alias:

~~~sql
DROP SYNONYM open_orders;
~~~

This statement does not drop the target view or table. Likewise, modifying a synonym does not alter privileges on the target.

Do not confuse DROP SYNONYM with DROP TABLE or DROP VIEW.

### 3.4. Synonym pointing to a package

A synonym can be created for a package:

~~~sql
CREATE SYNONYM order_api
FOR api_owner.order_api;
~~~

Calling the procedure:

~~~sql
BEGIN
    order_api.set_order_status(
        p_order_id => 1001,
        p_status   => 'SHIPPED'
    );
END;
/
~~~

APP_USER still needs EXECUTE on API_OWNER.ORDER_API. A synonym does not replace GRANT EXECUTE.

### 3.5. Synonym pointing across a database link

A synonym can point to a remote object:

~~~sql
CREATE SYNONYM remote_orders
FOR sales.orders@reporting_link;
~~~

Then:

~~~sql
SELECT order_id, created_at
FROM remote_orders;
~~~

For the query to succeed, independent conditions must be met:

- The synonym resolves to the target.
- The session can use the database link according to link type and owner.
- The remote connection authenticates successfully.
- The remote identity has SELECT privilege on SALES.ORDERS.
- The network/service name and remote database are available.

A synonym does not translate local privileges into remote privileges.

## 4. View: controlled exposure of columns and rows

A view is a named query. A view can expose only selected columns, filter rows, compute expressions, or combine multiple tables.

Example base table:

~~~sql
CREATE TABLE data_owner.orders (
    order_id      NUMBER PRIMARY KEY,
    customer_id   NUMBER NOT NULL,
    status        VARCHAR2(20) NOT NULL,
    created_at    TIMESTAMP(6) NOT NULL,
    total_amount  NUMBER(12,2) NOT NULL,
    internal_note VARCHAR2(1000)
);
~~~

Create a view exposing only the columns the application is allowed to read:

~~~sql
CREATE OR REPLACE VIEW data_owner.v_open_orders AS
SELECT order_id,
       customer_id,
       created_at,
       total_amount
FROM data_owner.orders
WHERE status = 'OPEN'
WITH READ ONLY;
~~~

Grant SELECT on the view:

~~~sql
GRANT SELECT ON data_owner.v_open_orders TO app_read;
GRANT app_read TO app_user;
~~~

Users with the APP_READ role can query the view when the role is enabled in the session:

~~~sql
SELECT order_id, customer_id, total_amount
FROM data_owner.v_open_orders;
~~~

They do not need SELECT granted on DATA_OWNER.ORDERS if no other direct access path exists.

### 4.1. Column restriction

The view omits INTERNAL_NOTE from its projection, so view readers cannot retrieve this column through the view itself.

This separates internal data from the application interface. However, if APP_USER has direct SELECT on the base table, they can bypass the view. Therefore, for a view to serve as a column boundary, do not grant base table privileges to consumers.

### 4.2. Row restriction

The WHERE clause in the view restricts the rows returned by the view:

~~~sql
CREATE OR REPLACE VIEW data_owner.v_open_orders AS
SELECT order_id,
       customer_id,
       created_at,
       total_amount
FROM data_owner.orders
WHERE status = 'OPEN'
WITH READ ONLY;
~~~

This view shows only OPEN orders. However, this is a fixed policy for everyone with privileges on the view. If each tenant/user should see different rows, an appropriate row-level security mechanism is needed, such as Virtual Private Database (VPD) or a policy controlled via a secured application context.

Do not treat a static predicate in a view as automatically providing per-user authorization policies.

### 4.3. WITH CHECK OPTION

If a view allows DML, WITH CHECK OPTION forces rows inserted/updated through the view to continue satisfying the view's predicate.

Example:

~~~sql
CREATE OR REPLACE VIEW data_owner.v_open_orders_edit AS
SELECT order_id,
       customer_id,
       status,
       created_at,
       total_amount
FROM data_owner.orders
WHERE status = 'OPEN'
WITH CHECK OPTION CONSTRAINT v_open_orders_ck;
~~~

If a user updates STATUS to CLOSED through this view, the operation can be rejected because the row no longer satisfies the view condition.

WITH CHECK OPTION does not replace business constraints or row-level security. It ensures DML through the view preserves the view's predicate.

### 4.4. WITH READ ONLY

If consumers only need read access, WITH READ ONLY prevents DML through the view:

~~~sql
CREATE OR REPLACE VIEW data_owner.v_order_summary AS
SELECT customer_id,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
FROM data_owner.orders
GROUP BY customer_id
WITH READ ONLY;
~~~

The view can serve as a reporting interface. Users can SELECT but cannot update data through the view.

### 4.5. A view is not automatically a complete security barrier

A view only restricts the access path it provides. Check other paths:

- Does the user have direct privileges on the base table?
- Are there other synonyms pointing to the base table?
- Are there other packages returning sensitive data?
- Are there database links or other schemas permitting access?
- Are there ANY TABLE privileges or overly broad system privileges?
- Are there other views joining back the hidden columns?

A secure view must accompany an overall privilege matrix. Simply creating a view and granting SELECT without revoking excess privileges does not establish the desired boundary.

### 4.6. View owner privileges and reader privileges

To create a view, the owner needs appropriate direct privileges on the underlying objects; privileges held only through a role are typically insufficient for dependency/compilation of stored objects.

A user granted SELECT on a view can read through the view without direct SELECT on the base table.

If the view owner does not own the underlying object and wants to grant privileges on the view to others, check the grant option requirement on the underlying objects. Missing grant options can lead to ORA-01720. A straightforward management approach is having the table-owning schema create the published view, or designing an intentional grant chain instead of broadly granting WITH GRANT OPTION.

## 5. PL/SQL package: data manipulation API

A package can encapsulate read/write logic and expose only permitted business operations. Consumers are granted EXECUTE on the package instead of direct DML on tables.

Example:

~~~sql
CREATE OR REPLACE PACKAGE api_owner.order_api
AUTHID DEFINER
AS
    PROCEDURE set_order_status(
        p_order_id IN data_owner.orders.order_id%TYPE,
        p_status   IN data_owner.orders.status%TYPE
    );

    PROCEDURE create_order(
        p_order_id     IN data_owner.orders.order_id%TYPE,
        p_customer_id  IN data_owner.orders.customer_id%TYPE,
        p_total_amount IN data_owner.orders.total_amount%TYPE
    );
END order_api;
/
~~~

Package body:

~~~sql
CREATE OR REPLACE PACKAGE BODY api_owner.order_api
AS
    PROCEDURE set_order_status(
        p_order_id IN data_owner.orders.order_id%TYPE,
        p_status   IN data_owner.orders.status%TYPE
    )
    IS
    BEGIN
        IF p_status NOT IN ('OPEN', 'PAID', 'SHIPPED', 'CANCELLED') THEN
            RAISE_APPLICATION_ERROR(-20001, 'Invalid order status');
        END IF;

        UPDATE data_owner.orders
        SET status = p_status
        WHERE order_id = p_order_id;

        IF SQL%ROWCOUNT = 0 THEN
            RAISE_APPLICATION_ERROR(-20002, 'Order not found');
        END IF;
    END set_order_status;
END order_api;
/
~~~

The illustrative example requires the corresponding columns and privileges to exist. Production APIs need additional validation, transaction contracts, auditing, and business-appropriate error handling.

Grant privileges:

~~~sql
GRANT UPDATE ON data_owner.orders TO api_owner;
GRANT EXECUTE ON api_owner.order_api TO app_writer;
GRANT app_writer TO app_user;
~~~

APP_USER invokes the API without having direct UPDATE granted on DATA_OWNER.ORDERS.

### 5.1. Package specification and body

- The specification exposes the permitted procedures, functions, types, constants, and cursors.
- The body contains the implementation and internal details.
- Consumers only need to know the contract in the specification.
- Changing the implementation in the body may not require consumer changes if the public contract remains intact.

Do not expose internal procedures in the package specification if applications do not need to call them. Every public member expands the API surface and must be managed for compatibility.

### 5.2. Packages do not automatically make code secure

A definer-rights package can execute operations with broader privileges than the caller. If the API accepts arbitrary input and constructs dynamic SQL unsafely, an attacker can exploit the package owner's privileges.

Principles:

- Expose only necessary business operations.
- Validate state, keys, and tenant scope on the server.
- Bind values instead of concatenating SQL strings.
- Whitelist table/column names/sort directions if dynamic SQL is unavoidable.
- Use DBMS_ASSERT to validate identifiers when appropriate; it does not replace authorization.
- Do not return internal errors, SQL text, or sensitive data to clients.
- Do not grant package privileges to PUBLIC without justification.
- Keep only the object privileges the package owner actually needs.

## 6. AUTHID DEFINER: executing with the owner's privileges

PL/SQL stored procedures, functions, and packages default to definer rights if no other AUTHID is specified.

~~~sql
CREATE OR REPLACE PACKAGE api_owner.order_api
AUTHID DEFINER
AS
    PROCEDURE close_order(p_order_id NUMBER);
END;
/
~~~

When APP_USER invokes the package, the code runs with API_OWNER's privileges for operations performed inside the definer-rights unit.

This allows API_OWNER to hold UPDATE privileges on the table while APP_USER holds only EXECUTE on the package.

### 6.1. Roles do not replace direct grants in definer-rights code

In definer-rights PL/SQL, the caller session's roles are not used to authorize SQL executed inside the unit; required privileges must be granted directly to the owner per stored-object rules.

Example:

~~~sql
-- Insufficient to compile static SQL in a definer-rights package:
GRANT update_role TO api_owner;

-- Grant the object privilege directly to the package owner:
GRANT UPDATE ON data_owner.orders TO api_owner;
~~~

If API_OWNER only has UPDATE via UPDATE_ROLE, static SQL inside the package may fail to compile or fail to execute as expected. Grant the appropriate object privilege directly.

This is a key difference between SQL executed directly in a session and SQL inside a stored definer-rights program unit.

### 6.2. Why definer rights are useful

- Consumers do not need to know the physical tables.
- Operations can be controlled through procedures.
- Validation and auditing are centralized.
- Internal schemas can evolve without changing the application contract.
- Direct DML privileges on tables are minimized.

### 6.3. Risks of definer rights

- The package owner may hold broader privileges than the caller.
- An authorization bug in the package can become a privilege escalation vector.
- Dynamic SQL can expand the SQL injection surface.
- Packages granted EXECUTE to too many users can become unintended data access gateways.
- Owner direct grants may accidentally be overly broad.

Use a dedicated owner schema, do not use SYS/SYSTEM as an application owner, and do not grant ANY TABLE just to make code run.

## 7. AUTHID CURRENT_USER: executing with invoker's privileges

Declaring AUTHID CURRENT_USER creates an invoker-rights unit:

~~~sql
CREATE OR REPLACE PACKAGE util_owner.report_tools
AUTHID CURRENT_USER
AS
    PROCEDURE read_report;
END;
/
~~~

When called, the unit uses the invoker's privileges per invoker-rights rules. This is useful for shared utilities that need to operate on objects the caller has access to.

General differences:

| Characteristic | AUTHID DEFINER | AUTHID CURRENT_USER |
|---|---|---|
| Primary runtime privileges | Unit owner | Invoker |
| Goal | Controlled business API | Shared utility running under caller privileges |
| Caller roles | Do not authorize definer-rights SQL | Invoker privileges and enabled roles apply |
| Primary risk | Code may exercise overly broad owner privileges | Behavior depends on caller privileges and schema context |
| Best suited for | Encapsulated read/write APIs | Shared frameworks/utilities operating per caller |

Do not choose invoker rights merely to avoid direct grants to the owner. It changes authorization semantics and can cause the same procedure to succeed for one user and fail for another.

### 7.1. INHERIT PRIVILEGES

Starting in Oracle 12c, the INHERIT PRIVILEGES mechanism controls whether an invoker-rights program unit is allowed to inherit the invoker's privileges.

Illustrative example:

~~~sql
GRANT INHERIT PRIVILEGES ON USER app_user TO util_owner;
~~~

This statement allows UTIL_OWNER to inherit APP_USER's privileges in an invoker-rights context per Oracle rules.

If appropriate privileges are missing, calling an invoker-rights unit can raise ORA-06598. A system privilege INHERIT ANY PRIVILEGES exists, but it is very broad; do not grant it to application owners when inheriting privileges from only specific users is needed.

Verify INHERIT PRIVILEGES grants and system privileges against DBA policy. Do not resolve ORA-06598 by granting INHERIT ANY PRIVILEGES to every schema.

### 7.2. CURRENT_USER and CURRENT_SCHEMA are not the same

- CURRENT_USER is the security identity used for the execution context.
- CURRENT_SCHEMA affects the default schema when resolving unqualified object names.
- Changing CURRENT_SCHEMA does not grant additional privileges and does not turn the session into another user.

Example:

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = reporting;
~~~

This statement can change how Oracle resolves unqualified names, but privileges remain those of the logged-in user/current security context. Do not use CURRENT_SCHEMA as an authorization mechanism.

### 7.3. Choosing AUTHID based on the contract

Before creating a package, answer:

- Who is responsible for granting privileges on tables?
- Should the procedure be allowed to operate beyond the caller's privileges?
- Does the caller need to access their own objects or objects managed by the owner?
- Is there dynamic SQL or schema-qualified objects?
- Should caller roles affect the intended outcome?
- Is INHERIT PRIVILEGES needed?
- Can the API be constrained using definer rights and smaller object grants?

Explicitly specify AUTHID in DDL rather than relying on the default so reviewers can see the intent.

## 8. Direct privileges, roles, and stored object privileges

Oracle has multiple privilege layers:

- System privilege: allows performing system-level operations, such as CREATE SESSION or CREATE VIEW.
- Object privilege: privilege on a specific object, such as SELECT on a table or EXECUTE on a package.
- Role: a group of privileges granted to a user or another role.
- Program-unit privilege behavior: privileges required for stored code depend on AUTHID and compile/runtime rules.

### 8.1. Granting privileges via roles for application users

~~~sql
CREATE ROLE app_read;

GRANT SELECT ON data_owner.v_order_summary TO app_read;
GRANT app_read TO app_user;
~~~

When the APP_READ role is enabled, APP_USER can SELECT from the view.

Check currently enabled roles:

~~~sql
SELECT role
FROM session_roles
ORDER BY role;
~~~

A role granted to a user is not necessarily enabled in every session; secure application roles or SET ROLE can change its state.

### 8.2. Direct grants to the package owner

~~~sql
GRANT SELECT, UPDATE
ON data_owner.orders
TO api_owner;
~~~

This is a direct privilege on the object. API_OWNER's AUTHID DEFINER package can use this privilege according to the package contract.

Avoid granting unnecessary privileges. If the package only updates STATUS, consider designing object/column privileges and the API so the owner does not need read/write access to all columns.

### 8.3. PUBLIC privileges

PUBLIC is a special role through which every database user can receive privileges granted to PUBLIC. Granting object privileges or package EXECUTE to PUBLIC can expand the access surface across the entire database.

Avoid:

~~~sql
GRANT EXECUTE ON api_owner.admin_api TO PUBLIC;
~~~

unless the API is genuinely designed to be public for all database users and risks have been assessed.

### 8.4. GRANT OPTION and ADMIN OPTION

- WITH GRANT OPTION on an object privilege allows the grantee to further grant that object privilege within defined limits.
- WITH ADMIN OPTION on a role/system privilege allows the grantee to manage or further grant the corresponding privilege per Oracle rules.

Do not grant GRANT OPTION or ADMIN OPTION out of habit. They expand the grantee's administrative authority, not merely object usage rights.

## 9. Database link: authentication boundary to another database

A database link is an object in a local database containing information to connect to a remote database. SQL can access remote objects using the syntax:

~~~sql
SELECT order_id, total_amount
FROM sales.orders@reporting_link;
~~~

A database link is not a synonym and not a proxy that automatically carries local privileges unchanged to the remote database. The remote database authenticates an identity and checks that identity's privileges on the remote object.

### 9.1. Private database link

A private link belongs to the creating schema:

~~~sql
CREATE DATABASE LINK reporting_link
CONNECT TO report_reader IDENTIFIED BY "replace_with_managed_secret"
USING 'REPORTING_DB';
~~~

Example using a fixed user: the remote connection logs in as REPORT_READER. In production, do not put real passwords in source control, logs, or deployment documents. Use organization-approved credential management processes and rotate per policy.

A private link is used by the schema owner per database link rules. Other users cannot implicitly use a private link merely by knowing its name.

### 9.2. Public database link

A public link can be used by database users:

~~~sql
CREATE PUBLIC DATABASE LINK reporting_public
CONNECT TO report_reader IDENTIFIED BY "managed_secret"
USING 'REPORTING_DB';
~~~

A public link can be convenient across multiple schemas, but if it logs in with a broadly privileged remote account, many local users can share that remote identity.

Avoid public links to remote accounts with write privileges or sensitive data access unless clearly required with appropriate compensating controls. Prefer private links with restricted remote accounts.

### 9.3. Fixed-user database link

A fixed-user link specifies a remote username/password in the link definition:

~~~sql
CREATE DATABASE LINK reporting_link
CONNECT TO report_reader IDENTIFIED BY "managed_secret"
USING 'REPORTING_DB';
~~~

Every SQL statement over the link uses the REPORT_READER remote identity. Remote privileges do not automatically change based on the local APP_USER.

Therefore, if multiple local users can use the same link, they can perform whatever operations REPORT_READER is permitted to do. Minimize remote account privileges and control who can use the link.

### 9.4. Connected-user and current-user links

Oracle supports link types that use the user's identity instead of a fixed remote account, depending on authentication mechanisms and configuration:

- Connected-user links use the corresponding identity/credentials of the locally connected user per link configuration.
- Current-user links use a global user identity in supported enterprise authentication environments.

Example current-user link syntax:

~~~sql
CREATE DATABASE LINK enterprise_reporting
CONNECT TO CURRENT_USER
USING 'ENTERPRISE_REPORTING';
~~~

A current-user link requires proper global user authentication conditions. It cannot be treated as a fixed-user link without a password. Verify Oracle Net, enterprise users, directory/authentication setup, and specific release behavior before deploying.

### 9.5. Local privileges and remote privileges are two separate layers

To query SALES.ORDERS@REPORTING_LINK, check:

1. Can the local user/schema use the link based on link type and ownership?
2. Can the link connect to the remote service?
3. Does remote authentication succeed?
4. Does the remote identity have SELECT on SALES.ORDERS?
5. Does the remote object exist and resolve properly?
6. Are the network, listener, and service name available?

Granting SELECT on a local table does not grant SELECT on a remote table. Conversely, a remote account having SELECT does not automatically allow a local user to use another schema's private link.

## 10. Remote identity and privileges on remote objects

Example where the remote DBA creates a read-only account:

~~~sql
CREATE USER report_reader IDENTIFIED BY "managed_secret";
GRANT CREATE SESSION TO report_reader;
GRANT SELECT ON sales.orders TO report_reader;
~~~

In the local database, a schema has a fixed-user link to REPORT_READER. When running:

~~~sql
SELECT order_id, total_amount
FROM sales.orders@reporting_link;
~~~

the remote database checks REPORT_READER's privileges on SALES.ORDERS.

Do not grant SELECT ANY TABLE to REPORT_READER when only one table is needed. If multiple tables are needed, grant per object or create a remote view exposing only appropriate columns/rows and grant SELECT on the view.

### 10.1. Using a remote view to restrict data

On the remote database:

~~~sql
CREATE OR REPLACE VIEW sales.v_order_export AS
SELECT order_id,
       customer_id,
       created_at,
       total_amount
FROM sales.orders
WHERE status IN ('PAID', 'SHIPPED')
WITH READ ONLY;

GRANT SELECT ON sales.v_order_export TO report_reader;
~~~

The remote account is only granted SELECT on the view if privileges and ownership chains align. Then the local query via link runs:

~~~sql
SELECT order_id, customer_id, total_amount
FROM sales.v_order_export@reporting_link;
~~~

A remote view provides a stable interface and avoids granting read access on the base table to the remote account. If the view owner does not own the base table, check grant option requirements when granting privileges on the view.

### 10.2. Remote synonyms do not replace remote privileges

~~~sql
CREATE SYNONYM remote_order_export
FOR sales.v_order_export@reporting_link;
~~~

The synonym shortens the name. The remote identity still needs SELECT on SALES.V_ORDER_EXPORT, and the local session still needs to be able to use REPORTING_LINK.

### 10.3. Packages in a remote database

A remote package can be called if the remote identity has appropriate EXECUTE privileges and the database link supports access:

~~~sql
BEGIN
    sales.reporting_api.refresh_summary@reporting_link;
END;
/
~~~

When remote code runs, the privileges and AUTHID of the remote stored unit apply at the remote database. Both the local link identity and the remote package privilege chain must be verified.

## 11. Database links and stored code

When a database link is used inside a view or PL/SQL package, identify which schema owns the link and which AUTHID the code runs under.

Questions to verify:

- Is the link private or public?
- Which schema owns the link?
- Is the package AUTHID DEFINER or CURRENT_USER?
- Can the runtime user access the link in that context?
- Is the remote login user a fixed user or current user?
- Are remote object privileges sufficient?
- Does dynamic SQL use the proper schema/link and bind values?

Do not assume a definer-rights package can automatically use every private link of the caller. Test using the real application user, real package owner, and real link in a test environment.

### 11.1. Remote links inside a package API

A package API can read remote data and return controlled results. The package owner needs appropriate privileges and a private link; callers only get EXECUTE on the package in a definer-rights design.

This avoids granting database link usage directly to every user. However, it also makes the package a concentration point for remote privileges, so you must:

- Limit exposed procedures.
- Validate inputs and tenant scope.
- Restrict the remote account.
- Audit operations and errors.
- Apply bounded timeouts/retries.
- Control returned data.
- Never allow callers to pass arbitrary SQL fragments.

### 11.2. Distributed transactions

DML across a database link can participate in a distributed transaction. When a transaction updates both local and remote databases, Oracle may use two-phase commit to coordinate the commit.

This introduces additional operational risks:

- Network failure during commit.
- In-doubt transactions.
- Prolonged locks and latency.
- Remote database unavailability.
- Difficulty retrying without idempotency.

Do not open long distributed transactions if the flow can be separated into messaging/outbox or checkpointed batch sync. If atomic commits across databases are required, thoroughly understand distributed transactions, recovery, and DBA procedures.

## 12. Secure design for dynamic SQL

Dynamic SQL is a high-risk area when a package runs with definer rights.

Unsafe example:

~~~sql
l_sql := 'SELECT * FROM data_owner.orders WHERE status = '''
         || p_status || '''';
EXECUTE IMMEDIATE l_sql;
~~~

If input contains quotes or malicious SQL fragments, the statement can be altered.

Use bind variables:

~~~sql
l_sql := 'SELECT order_id FROM data_owner.orders WHERE status = :b1';

EXECUTE IMMEDIATE l_sql
BULK COLLECT INTO l_order_ids
USING p_status;
~~~

For table/column names, bind variables do not apply to identifiers. Use a whitelist:

~~~sql
CASE p_sort_key
    WHEN 'CREATED_AT' THEN
        l_order_by := 'created_at';
    WHEN 'TOTAL_AMOUNT' THEN
        l_order_by := 'total_amount';
    ELSE
        RAISE_APPLICATION_ERROR(-20010, 'Unsupported sort key');
END CASE;
~~~

DBMS_ASSERT can help validate identifiers/literals for specific targets:

~~~sql
l_safe_name := DBMS_ASSERT.SIMPLE_SQL_NAME(p_column_name);
~~~

However, DBMS_ASSERT does not prove the caller is authorized to access that object. Authorization still requires whitelists and privilege checks.

In definer-rights code, SQL injection can exploit the owner's privileges. Minimize dynamic SQL and never concatenate untrusted input into statements.

## 13. Summary table of privileges across layers

| Access path | Caller privilege required | Executing principal privilege required |
|---|---|---|
| Direct table SELECT | SELECT on table or enabled role | The session user itself |
| SELECT via private synonym | SELECT on target object | The session user itself |
| SELECT via public synonym | SELECT on target object | The session user itself |
| SELECT via view | SELECT on view | View owner needs appropriate underlying privileges |
| Call definer-rights package | EXECUTE on package | Package owner needs direct grants for internal SQL |
| Call invoker-rights package | EXECUTE on package | Invoker needs context privileges and appropriate INHERIT PRIVILEGES |
| SELECT via fixed-user DB link | Link usage per owner/link type | Fixed remote account needs remote object privileges |
| SELECT via current-user DB link | Appropriate link/authentication setup | Current global user needs remote object privileges |
| Call remote package via link | Link usage and remote EXECUTE privilege | Remote package applies AUTHID and privileges at remote DB |

This table is a general model. Specific compile-time, runtime, role, remote authentication, and object resolution details depend on object type and Oracle release. When deploying, test with the actual principals.

## 14. Data dictionary views to inspect privileges and names

### 14.1. Object privileges

View object privileges in the current schema:

~~~sql
SELECT owner,
       table_name,
       grantee,
       privilege,
       grantable
FROM user_tab_privs
ORDER BY table_name, grantee, privilege;
~~~

View privileges visible to the current user:

~~~sql
SELECT owner,
       table_name,
       grantee,
       privilege,
       grantable
FROM all_tab_privs
WHERE grantee IN ('APP_USER', 'APP_READ', 'APP_WRITE')
ORDER BY owner, table_name, grantee, privilege;
~~~

DBAs can use DBA_TAB_PRIVS to inspect the entire database when authorized.

### 14.2. System privileges and roles

~~~sql
SELECT privilege
FROM session_privs
ORDER BY privilege;
~~~

~~~sql
SELECT role
FROM session_roles
ORDER BY role;
~~~

To check roles granted to a user, query USER_ROLE_PRIVS or DBA_ROLE_PRIVS within privilege scope.

Session_roles shows roles currently enabled in the current session; user_role_privs does not imply all granted roles are currently enabled.

### 14.3. Synonym metadata

~~~sql
SELECT owner,
       synonym_name,
       table_owner,
       table_name,
       db_link
FROM all_synonyms
WHERE synonym_name IN ('OPEN_ORDERS', 'ORDER_API')
ORDER BY owner, synonym_name;
~~~

A non-NULL DB_LINK indicates the synonym points to an object across a database link. This metadata only shows target mapping; it does not prove the user has privileges to access the target.

### 14.4. View and package dependencies

~~~sql
SELECT owner,
       name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type
FROM all_dependencies
WHERE owner IN ('DATA_OWNER', 'API_OWNER')
ORDER BY owner, name, referenced_owner, referenced_name;
~~~

Dependencies help identify objects referenced by views/packages. Dynamic SQL may not be fully recorded in dependency metadata because object names only appear at runtime.

### 14.5. Database link metadata

~~~sql
SELECT owner,
       db_link,
       username,
       host,
       created
FROM all_db_links
ORDER BY owner, db_link;
~~~

USER_DB_LINKS/ALL_DB_LINKS/DBA_DB_LINKS provide metadata within privilege scope. Do not treat link metadata as a place to extract plaintext passwords; never put credentials in logs or reports.

### 14.6. Checking package AUTHID

Inspect package source or metadata to determine AUTHID:

~~~sql
SELECT owner,
       name,
       type,
       line,
       text
FROM all_source
WHERE owner = 'API_OWNER'
  AND name = 'ORDER_API'
  AND type IN ('PACKAGE', 'PACKAGE BODY')
ORDER BY type, line;
~~~

During review, check whether the package spec specifies AUTHID DEFINER or CURRENT_USER. If omitted, understand that it defaults to definer rights.

## 15. Common privilege errors

| Error | Common cause | Investigation direction |
|---|---|---|
| ORA-00942 | Object does not exist or user lacks privilege; wrong synonym target | Check owner/object, synonym, and grants |
| ORA-01031 | Missing system/object privilege | Identify operation and executing principal |
| ORA-01720 | Missing grant option on underlying object when granting privilege via view | Check view owner and grant chain |
| ORA-06598 | Invoker-rights unit lacks appropriate INHERIT PRIVILEGES | Check AUTHID and inherit grants |
| ORA-04063 | View/package has errors or invalid dependency | Check USER_ERRORS/ALL_ERRORS and compile |
| ORA-04068 | Package state discarded after change/recompile in some cases | Check package state and retry contract |
| ORA-02019 | Connection description/database link not found | Check link name and Oracle Net |
| ORA-02085 | Database link global name mismatch per configuration | Check GLOBAL_NAMES and remote global name |
| ORA-02019/ORA-12154 | Link/service name cannot be resolved | Check USING connect identifier, tnsnames/LDAP |
| ORA-01017 | Invalid remote username/password | Verify remote identity and credential rotation |
| ORA-02063 | Error returned from remote database | Read the remote error message preceding ORA-02063 |
| ORA-02049 | Distributed transaction timeout waiting on lock | Check remote blocking and transaction duration |

One error code can have multiple causes. Always read the full error stack and determine whether the error originated on the local or remote database.

## 16. Testing privilege boundaries with real users

Do not test only as SYS or the schema owner. Use accounts representing the application.

Example matrix:

| Principal | SELECT base table | SELECT view | EXECUTE package | Use DB link |
|---|---:|---:|---:|---:|
| DATA_OWNER | Yes | Yes | Per grant | Per configuration |
| API_OWNER | Only required direct grants | Per design | Owner | Private link if needed |
| APP_READ | No | Yes | No | No |
| APP_WRITE | No | Possibly no | Yes | Not directly |
| APP_USER | Per granted role | Per role | Per role | Only if designed |

Important test cases:

1. APP_READ SELECT on view succeeds.
2. APP_READ SELECT on base table is denied.
3. APP_WRITE calling package succeeds.
4. APP_WRITE direct UPDATE on base table is denied.
5. User without EXECUTE cannot invoke package.
6. Synonym exists, but missing target privilege still causes query denial.
7. Non-owner user cannot use another schema's private database link.
8. Read-only remote account cannot UPDATE remote table.
9. When remote password expires/changes, the link is updated per runbook.
10. Invoker-rights package is tested with users both with and without INHERIT PRIVILEGES.
11. Dynamic SQL cannot alter objects or predicates outside the whitelist.
12. Views do not leak sensitive columns or other tenants' rows through secondary access paths.

### 16.1. Negative test cases

Security tests must prove both allowed operations and denied operations. A test confirming SELECT succeeds does not prove the base table is protected.

Use a fresh session or reset roles/session context appropriately. Record the login user, current_user, current_schema, enabled roles, and database link identity.

## 17. Auditing and operations

A privilege boundary must be verifiable after deployment.

Per database policy, you can audit:

- EXECUTE on sensitive packages.
- SELECT/UPDATE/DELETE on critical objects.
- Changes to roles and object grants.
- Creation/deletion of public synonyms.
- Creation/modification of database links.
- Remote account logins and activity at the remote database.

Unified Auditing and audit policies can assist monitoring depending on version/configuration. Do not enable overly broad auditing without capacity, retention, and analysis plans.

For package APIs, log application module/action, user context, and business transaction IDs. Do not log passwords, tokens, or sensitive personal data in audit payloads.

For database links:

- Monitor remote availability and latency.
- Use dedicated accounts for each critical integration.
- Rotate credentials.
- Review remote privileges periodically.
- Restrict public links.
- Use Oracle Net encryption/TCPS per security requirements.
- Control distributed transactions and retries.
- Do not give remote accounts DBA or schema-wide privileges unnecessarily.

## 18. Access path design workflow

When designing a new access flow:

1. Identify source data and owner.
2. List columns/rows consumers are permitted to see.
3. Decide between a view for a read interface or a package for business operations.
4. Choose AUTHID DEFINER or CURRENT_USER based on desired runtime privileges.
5. Grant minimal direct privileges to the view/package owner.
6. Grant SELECT/EXECUTE to consumer roles or users.
7. Create private synonyms if convenient access names are needed.
8. If accessing remote data, choose the database link type and remote identity.
9. Grant minimal remote object privileges.
10. Verify data dictionary and dependencies.
11. Run positive and negative security tests using application users.
12. Establish auditing, credential rotation, and revoke/rollback runbooks.

### 18.1. Revoking and removing privileges

Example revoking view read privilege:

~~~sql
REVOKE SELECT ON data_owner.v_open_orders FROM app_read;
~~~

Revoking package EXECUTE:

~~~sql
REVOKE EXECUTE ON api_owner.order_api FROM app_writer;
~~~

Revoking table privilege from the package owner:

~~~sql
REVOKE UPDATE ON data_owner.orders FROM api_owner;
~~~

If privileges come from a role, revoke the role grant or the privilege granted to the role according to scope. Before revoking, check dependent applications to avoid unexpected outages.

Dropping a private link:

~~~sql
DROP DATABASE LINK reporting_link;
~~~

The command must be executed in the schema owning the private link. Public links require corresponding administrative privileges and public scope. Before dropping, check dependent views/packages/synonyms/jobs.

## 19. Common design mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Assuming a synonym grants privileges | User still hits ORA-00942/ORA-01031 | Grant privileges on the target object |
| Using public synonyms as public data access | Mistakenly thinking every user can SELECT | Distinguish namespace from object privileges |
| Granting base table SELECT alongside view grant | Users bypass view filter/projection | Revoke unnecessary base table privileges |
| Granting package EXECUTE to PUBLIC | Exposes API to entire database | Grant to specific roles/users |
| Definer package owner has DBA role | Package bugs can cause privilege escalation | Dedicated owner and least privilege |
| Granting privileges only via roles to definer package | Stored code lacks direct grants | Grant object privileges directly to owner |
| Choosing AUTHID CURRENT_USER by guesswork | Behavior depends on caller privileges and may hit ORA-06598 | Define contract and verify INHERIT PRIVILEGES |
| Using CURRENT_SCHEMA as user authorization | Name resolution changes, privileges do not | Use proper grants/roles |
| Concatenating input into dynamic SQL in definer package | SQL injection exploits owner privileges | Bind values, whitelist identifiers |
| Sharing broad fixed-user link across multiple schemas | Multiple local users share strong remote identity | Dedicated remote account, minimal privileges, private link |
| Public DB link to remote admin account | Expands remote privileges to many local users | Avoid public links or restrict remote identity |
| Assuming remote SELECT grant is local link privilege | Missing a privilege layer | Check link owner/type and remote object privileges |
| Treating remote synonym as a security control | Does not change remote identity | Check remote grants and link identity |
| Not testing with the app user | Misses role/direct-grant/definer-rights behavior | Test with the actual principal |
| Lacking audits/credential rotation | Hard to investigate and revoke | Runbooks and audit policies |

## 20. Pre-production security checklist

### Synonyms and views

- [ ] Clearly identify the target owner/object of every synonym.
- [ ] Do not treat private/public synonyms as privileges.
- [ ] Grant privileges on target objects/views/packages.
- [ ] Views expose only necessary columns and rows.
- [ ] Do not grant base tables directly to consumers if the view is a boundary.
- [ ] Verify WITH CHECK OPTION/READ ONLY as needed.
- [ ] Check grant option when granting privileges on views built on another owner's objects.
- [ ] Check secondary access paths via other synonyms/views/packages.

### Packages and AUTHID

- [ ] AUTHID is explicitly declared and matches the contract.
- [ ] Definer-rights owner is a dedicated schema.
- [ ] Owner holds only necessary direct grants.
- [ ] Consumers hold only EXECUTE on required packages.
- [ ] Do not grant EXECUTE to PUBLIC unnecessarily.
- [ ] Dynamic SQL uses bind values and identifier whitelisting.
- [ ] Verify INHERIT PRIVILEGES for invoker-rights code.
- [ ] Validation and authorization are enforced inside the API.
- [ ] Positive/negative tests run using the application user.

### Database links

- [ ] Intentionally choose private/public and fixed/connected/current-user links.
- [ ] Remote identity is defined and documented in the design.
- [ ] Remote account holds only required object privileges.
- [ ] Avoid remote accounts with DBA/ANY privileges.
- [ ] Never place passwords in source code, logs, or documentation.
- [ ] Credential rotation procedure is in place.
- [ ] Remote network encryption and service resolution are controlled.
- [ ] Check synonyms/packages/views dependent on the link.
- [ ] Evaluate distributed transaction and retry behavior.
- [ ] Monitor remote access with auditing and monitoring.

## 21. Core takeaways

- A synonym is only a name-resolution alias; privileges are checked on the target object.
- Public synonyms make names resolvable more broadly, but do not make objects publicly accessible.
- Views can restrict columns/rows; consumers need privileges on the view and should not hold base table privileges if the view is a security boundary.
- WITH CHECK OPTION keeps DML rows via the view satisfying the predicate; WITH READ ONLY forbids DML through the view.
- View owners need appropriate underlying privileges; granting on a view may require grant options on underlying objects if the owner does not own them.
- Packages provide business APIs; EXECUTE on a package does not grant consumers direct DML on tables.
- AUTHID DEFINER runs with the owner's privileges; caller roles do not authorize definer-rights SQL, so the owner needs appropriate direct grants.
- AUTHID CURRENT_USER runs with the invoker's privileges; check roles, schema context, and INHERIT PRIVILEGES.
- CURRENT_SCHEMA changes name resolution, not security identity, and grants no extra privileges.
- Definer-rights packages can serve as strong privilege boundaries, but unsafe dynamic SQL can turn them into privilege escalation paths.
- Database links create remote sessions using fixed, connected, or current-user identities per configuration; the remote database checks the remote identity's privileges.
- Private links belong to the schema owner; public links widen link usage and require caution.
- Remote SELECT grants and local database link usage rights are two distinct conditions.
- A synonym pointing across a database link still does not grant remote privileges.
- Least privilege applies across local owners, application users, package owners, and remote accounts.
- Test both permitted operations and operations that must be denied using the actual application user.
- Use the data dictionary, auditing, and runbooks to maintain privileges, links, credentials, and dependencies after deployment.

### Oracle documentation references

- [Oracle Database Security Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/) — Users, roles, object privileges, definer/invoker rights, database links and security policies.
- [Oracle Database PL/SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/) — AUTHID, invoker rights, definer rights, stored program units and dynamic SQL.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/) — CREATE VIEW, CREATE SYNONYM, GRANT and REVOKE.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/) — Database links, users, privileges and distributed database administration.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — USER/ALL/DBA_TAB_PRIVS, SESSION_ROLES, ALL_SYNONYMS, ALL_DB_LINKS and dependency views.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_ASSERT](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_ASSERT.html) — Validation of SQL identifiers and literals in dynamic SQL.

Privilege checks, database-link authentication, invoker-rights behavior and dictionary metadata can vary by Oracle release and deployment configuration. Verify the exact release documentation, test with real application principals, and review both local and remote grants before exposing an access path in production.
