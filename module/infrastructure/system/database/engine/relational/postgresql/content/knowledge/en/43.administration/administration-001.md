# Lifecycle Management of Roles, Databases, Schemas, and Ownership in PostgreSQL

## 1. Why Lifecycle-Based Privilege Management Matters

PostgreSQL uses roles to manage identities, login privileges, administrative privileges, and data access privileges. A role can represent a user, an application, a privilege group, or the owner of a group of objects. Databases and schemas organize objects; ownership identifies the role that has administrative authority over an object; ACL grants determine which operations other roles are permitted to perform.

If privileges are granted only on an ad-hoc basis upon request, systems typically accumulate fragmented grants: a user is granted SELECT directly on many tables, a service shares an admin account, a schema has CREATE granted to PUBLIC, or newly created objects do not receive default privileges as expected. Over time, it becomes unclear who owns the data, which privileges come from membership, which privileges were granted directly, and where privileges must be revoked when personnel or services leave the system.

Lifecycle management means having a consistent process from role creation, membership assignment, database/schema creation, owner establishment, privilege granting for current and future objects, privilege modification, periodic auditing, ownership transfer, and login deactivation through safe role deletion.

Foundational principles:

- Use NOLOGIN roles to represent privilege groups and ownership.
- Use a dedicated login role for each person or service requiring authentication.
- Grant privileges through group roles instead of scattered direct grants.
- Separate object ownership from application runtime privileges.
- Grant database, schema, and object privileges at the appropriate level.
- Use default privileges so new objects receive the proper ACLs immediately upon creation.
- Verify effective privileges, membership, and ownership before closing a change.
- Revoke privileges and transfer ownership before dropping a role.
- Maintain an audit trail for all impactful privilege changes.

```text
                 ROLE LIFECYCLE
                       |
                       v
                 Provision role
                       |
                       v
             Assign group membership
                       |
                       v
             Create database/schema
                       |
                       v
             Set stable object owner
                       |
                       v
          Grant current/default privileges
                       |
                       v
             Validate effective access
                       |
                       v
          Review / rotate / change access
                       |
                       v
             Disable login and sessions
                       |
                       v
             Transfer ownership / revoke
                       |
                       v
                    Drop role
```

## 2. Learning Objectives

After this lesson, you will be able to:

1. Distinguish between roles, login roles, group roles, databases, schemas, and object owners.
2. Explain how ownership differs from ACL privileges.
3. Design an owner/runtime/migration role model.
4. Create and alter roles using CREATE ROLE, ALTER ROLE, and DROP ROLE.
5. Manage LOGIN, NOLOGIN, INHERIT, CREATEDB, CREATEROLE, and privileged attributes.
6. Grant and revoke role memberships using GRANT/REVOKE.
7. Understand INHERIT, SET ROLE, and ADMIN OPTION.
8. Grant database, schema, table, sequence, function, and type privileges with the proper scope.
9. Distinguish PUBLIC from a regular group role.
10. Use default privileges for objects created in the future.
11. Transfer ownership of databases, schemas, and objects.
12. Use REASSIGN OWNED and DROP OWNED in a controlled manner.
13. Inspect effective privileges using `has_*_privilege` and catalog views.
14. Inspect role memberships, object owners, and ACLs.
15. Manage user/service onboarding, role rotation, and offboarding.
16. Revoke login, terminate sessions, and clean up dependencies.
17. Avoid granting unnecessary SUPERUSER, BYPASSRLS, or CREATEROLE privileges.
18. Handle privileges on the `public` schema and predefined roles.
19. Design audits, reviews, and change records.
20. Build a runbook for lifecycle administration of roles/databases/schemas.

## 3. Roles, Users, and Group Roles

### 3.1. Role as the Central Concept

In PostgreSQL, a role is a cluster-wide object representing an identity or a set of privileges. A role can log in if it has the LOGIN attribute, or be used solely to group privileges if it is NOLOGIN.

The CREATE USER command is a convenience alias equivalent to CREATE ROLE ... LOGIN. Calling it a user does not create a different security object type. Use role to keep the model consistent.

### 3.2. Login Role

A login role is an identity used to authenticate connections:

```sql
CREATE ROLE app_runtime
    LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION
    NOBYPASSRLS;
```

In practice, credentials should be provisioned through a secret manager or secure workflow. Do not write real passwords into migration files, source control, shell history, or baseline documentation. With psql, you can use `\password role_name` to enter a password interactively.

### 3.3. Group Role

A group role is usually created with NOLOGIN and then granted to login roles:

```sql
CREATE ROLE app_read NOLOGIN;
CREATE ROLE app_write NOLOGIN;
CREATE ROLE app_support NOLOGIN;

GRANT app_read TO app_runtime;
GRANT app_write TO app_runtime;
```

When read access needs to be revoked, you can change the login role's membership without having to find and revoke individual table grants.

### 3.4. Owner Role

An owner role represents ownership of databases/schemas/objects. Typically, this role does not log in directly:

```sql
CREATE ROLE app_owner NOLOGIN;
```

The migration identity can be allowed to `SET ROLE` to `app_owner` to create objects under the proper owner. The runtime role receives only the privileges needed to run the application.

### 3.5. Separating Identities and Privileges

A common model:

| Role | LOGIN | Purpose |
| --- | --- | --- |
| app_owner | NOLOGIN | Owns schema and objects |
| app_read | NOLOGIN | Read privilege group |
| app_write | NOLOGIN | Write privilege group |
| app_migrator | YES | Identity running migrations, can SET ROLE app_owner |
| app_runtime | YES | Application runtime identity |
| app_readonly_job | YES | Read-only/reporting service |

This separation enables credential rotation without changing the ACL ownership of thousands of objects.

## 4. Role Attributes and Privileges

### 4.1. Common Attributes

| Attribute | Meaning |
| --- | --- |
| LOGIN / NOLOGIN | Allowed / not allowed to log in |
| SUPERUSER / NOSUPERUSER | Has / does not have full superuser privileges |
| CREATEDB / NOCREATEDB | Allowed / not allowed to create databases |
| CREATEROLE / NOCREATEROLE | Allowed / not allowed to create and manage certain roles |
| REPLICATION / NOREPLICATION | Allowed / not allowed to use special replication privileges |
| BYPASSRLS / NOBYPASSRLS | Allowed / not allowed to bypass row-level security |
| INHERIT / NOINHERIT | Inherit privileges from memberships by default per version semantics |
| CONNECTION LIMIT | Limits concurrent connections for the role, with system exceptions |
| VALID UNTIL | Expiration timestamp for password authentication |

### 4.2. Do Not Grant SUPERUSER to Applications

SUPERUSER bypasses most privilege checks and can modify configuration, data, or sensitive objects. Application runtime, reporting jobs, and migration roles typically do not need SUPERUSER.

If an administrative operation requires superuser, perform it using a break-glass identity with auditing and a time limit, rather than attaching that privilege to continuously running credentials.

### 4.3. CREATEROLE Is a Sensitive Privilege

CREATEROLE allows creating/managing roles within the scope permitted by the PostgreSQL version. The ability to manage role memberships and attributes has changed across major versions. Do not treat CREATEROLE as equivalent to a regular data-reading privilege; grant it only to controlled identity-administration roles.

### 4.4. CREATEDB and REPLICATION

CREATEDB allows creating databases. REPLICATION allows connecting using the replication protocol as required. Grant these only when a specific task requires them; an application does not need either privilege merely to access tables.

### 4.5. BYPASSRLS

BYPASSRLS allows bypassing row-level security. This is a powerful attribute that can break tenant data boundaries. Use it only for specific controlled administrative/backup roles. Superusers also bypass RLS; table owners normally bypass RLS unless FORCE ROW LEVEL SECURITY is enabled.

### 4.6. Inspecting Attributes

```sql
SELECT
    rolname,
    rolsuper,
    rolinherit,
    rolcreaterole,
    rolcreatedb,
    rolcanlogin,
    rolreplication,
    rolbypassrls,
    rolconnlimit,
    rolvaliduntil
FROM pg_catalog.pg_roles
ORDER BY rolname;
```

`pg_roles` is the appropriate view for inspecting role attributes. Password hashes are not exposed through this view.

### 4.7. Altering Roles

```sql
ALTER ROLE app_runtime CONNECTION LIMIT 40;
ALTER ROLE app_runtime VALID UNTIL '2027-01-01 00:00:00+00';
ALTER ROLE app_runtime NOLOGIN;
ALTER ROLE app_runtime LOGIN;
```

VALID UNTIL applies to password authentication; other authentication methods have their own semantics. NOLOGIN is the way to disable opening new login sessions regardless of the authentication method.

## 5. Role Membership, INHERIT, and SET ROLE

### 5.1. GRANT role TO role

Membership syntax is directional:

```sql
GRANT app_read TO app_runtime;
```

`app_runtime` is a member of `app_read` and can receive the granted role's privileges according to membership options and INHERIT behavior.

### 5.2. Revoking Membership

```sql
REVOKE app_read FROM app_runtime;
```

This operation revokes the membership; it does not drop the `app_read` role and does not remove ACL grants made directly to `app_runtime`.

### 5.3. INHERIT

INHERIT determines whether a role automatically uses the privileges of its memberships according to configuration/version. In PostgreSQL versions prior to 16, the INHERIT/NOINHERIT attribute on the member role controlled overall inheritance behavior. Starting with PostgreSQL 16, membership grants can specify INHERIT and SET options individually.

Example for newer versions:

```sql
GRANT app_read TO app_runtime
    WITH INHERIT TRUE, SET TRUE;
```

Verify exact syntax against the major version in use.

### 5.4. SET ROLE

SET ROLE switches the session's effective role to a role that the session has permission to set:

```sql
SET ROLE app_owner;

SELECT
    session_user,
    current_user;

RESET ROLE;
```

`session_user` reflects the initial connection identity; `current_user` is the current effective identity used for permission checks. After SET ROLE, newly created objects normally belong to the role that is `current_user`.

### 5.5. Why Migrations Need SET ROLE

If the migration login is `app_migrator` and it creates a table directly, the table may end up owned by `app_migrator`. Default privileges configured for `app_owner` will not apply to objects created by `app_migrator`.

Use `SET ROLE app_owner` before creating objects so that ownership and default privileges remain consistent. End with `RESET ROLE` or close the session.

### 5.6. ADMIN OPTION

ADMIN OPTION allows a member to manage memberships of the granted role within the scope permitted by the PostgreSQL version:

```sql
GRANT app_read TO access_admin WITH ADMIN OPTION;
```

This is a membership-administration privilege, distinct from the object privilege WITH GRANT OPTION. Do not grant ADMIN OPTION to application runtime roles.

### 5.7. PostgreSQL 16 and Later: Membership Options

Starting in PostgreSQL 16, memberships have distinct options:

- ADMIN: whether the member can grant/revoke membership in the granted role.
- INHERIT: whether the member automatically inherits privileges of the granted role.
- SET: whether the member is allowed to SET ROLE to the granted role.

A membership can be configured not to inherit privileges automatically while still allowing SET ROLE. This is the basis for letting a migration identity temporarily switch to an owner role.

### 5.8. Inspecting Membership

On PostgreSQL 16 and later:

```sql
SELECT
    member_role.rolname AS member_role,
    granted_role.rolname AS granted_role,
    m.admin_option,
    m.inherit_option,
    m.set_option
FROM pg_catalog.pg_auth_members AS m
JOIN pg_catalog.pg_roles AS member_role
  ON member_role.oid = m.member
JOIN pg_catalog.pg_roles AS granted_role
  ON granted_role.oid = m.roleid
ORDER BY member_role.rolname, granted_role.rolname;
```

On older versions, `pg_auth_members` does not have the `inherit_option` and `set_option` columns; use the catalog view schema appropriate for the version.

### 5.9. Memberships Can Be Nested

Role A can be a member of role B, and role B a member of C. Effective privileges depend on the membership path and INHERIT/SET options. During audits, inspect both direct and nested memberships rather than only the most recent GRANT line.

## 6. Databases, Schemas, and Objects Are Different Privilege Layers

### 6.1. Database

A database is the unit of connection and contains schemas. Database privileges include:

- CONNECT: allows connecting to the database.
- CREATE: allows creating schemas and certain database-level objects according to semantics.
- TEMPORARY/TEMP: allows creating temporary tables.

Having CONNECT does not mean being able to SELECT from a table.

### 6.2. Schema

A schema is a namespace containing tables, views, sequences, functions, types, and other objects.

- USAGE: allows accessing/resolving objects inside the schema if the role has privileges on the object.
- CREATE: allows creating new objects inside the schema.

Having USAGE on a schema does not automatically grant SELECT on tables. Having SELECT on a table without USAGE on the schema is also insufficient to access it by schema name.

### 6.3. Object Privileges

Specific privileges on an object depend on the object type. For example, tables have SELECT/INSERT/UPDATE/DELETE; sequences have USAGE/SELECT/UPDATE; functions have EXECUTE.

### 6.4. Ownership

An owner has administrative authority over an object, including the ability to ALTER/DROP it and manage privileges. Ownership is not the same as a regular GRANT ALL: you cannot replace all owner rights merely by granting ACLs.

### 6.5. PUBLIC Privileges

PUBLIC is a pseudo-role representing all roles in the cluster. Grants to PUBLIC apply broadly; revoking from a specific user does not disable privileges that the user still receives via PUBLIC or another membership.

### 6.6. A Request Requires Multiple Layers

For `app_runtime` to read `app.orders`, it typically needs:

1. CONNECT on the database.
2. USAGE on the `app` schema.
3. SELECT on the `app.orders` table.
4. Appropriate memberships/role attributes.
5. Passing RLS policies if row-level security is enabled on the table.

## 7. Database Lifecycle and Ownership

### 7.1. Creating a Database with a Clear Owner

CREATE DATABASE cannot run inside a transaction block:

```sql
CREATE DATABASE appdb OWNER app_owner;
```

Choose encoding, locale provider, collation, and template according to application requirements. Locale choices can affect sort order and index behavior; do not treat database creation as merely picking a name.

### 7.2. Granting Connection Privileges

```sql
GRANT CONNECT ON DATABASE appdb TO app_runtime;
GRANT CONNECT ON DATABASE appdb TO app_migrator;
```

Grant TEMP only if the workload needs temporary tables:

```sql
GRANT TEMPORARY ON DATABASE appdb TO app_runtime;
```

### 7.3. Inspecting Default Database ACLs

In many databases, CONNECT and TEMPORARY are granted to PUBLIC by default. Inspect the actual ACL, especially on older or upgraded databases:

```sql
SELECT
    datname,
    pg_catalog.pg_get_userbyid(datdba) AS owner,
    datacl
FROM pg_catalog.pg_database
WHERE datname = 'appdb';
```

If you want to restrict CONNECT, you can revoke it from PUBLIC and then grant it back to the required roles:

```sql
REVOKE CONNECT ON DATABASE appdb FROM PUBLIC;
GRANT CONNECT ON DATABASE appdb TO app_runtime, app_migrator;
```

Perform this only after identifying all services, monitoring, backup jobs, and operators that still need to connect. Missing a role can cause applications or maintenance jobs to lose connectivity.

### 7.4. Transferring Database Owner

```sql
ALTER DATABASE appdb OWNER TO app_owner;
```

The executor must meet PostgreSQL's ownership/membership and privilege requirements. Verify the database owner after the change.

### 7.5. The Database Owner Does Not Automatically Own All Objects

Database ownership does not mean all tables in the database automatically belong to the database owner. Schema/table/function ownership is a separate attribute. Inventory and transfer each object type if needed.

### 7.6. Dropping a Database

```sql
DROP DATABASE appdb;
```

This is a destructive operation on the entire database. Before executing lifecycle decommissioning, verify backups/retention, dependencies, active connections, subscriptions, and owner approval. Do not use this example as an automated cleanup step.

## 8. Schema Lifecycle and Schema Privileges

### 8.1. Creating a Schema with an Owner

```sql
CREATE SCHEMA app AUTHORIZATION app_owner;
```

The schema owner controls altering/dropping the schema and managing schema privileges.

### 8.2. Granting USAGE and CREATE Separately

```sql
GRANT USAGE ON SCHEMA app TO app_read, app_write;
GRANT CREATE ON SCHEMA app TO app_owner;
```

Runtime roles usually need only USAGE. Reserve CREATE for owner/migration identities.

### 8.3. Do Not Arbitrarily Grant CREATE to PUBLIC

The `public` schema has different default behavior across PostgreSQL versions and database histories. Newly created databases on PostgreSQL 15 and later typically have CREATE on the `public` schema revoked from PUBLIC by default, but upgraded or older databases may differ. Check the actual ACL:

```sql
SELECT
    nspname,
    pg_catalog.pg_get_userbyid(nspowner) AS owner,
    nspacl
FROM pg_catalog.pg_namespace
WHERE nspname IN ('public', 'app')
ORDER BY nspname;
```

If policy requires it, revoke CREATE from PUBLIC and re-grant it to owner/migration roles:

```sql
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO app_runtime;
```

Do not run this blindly on an existing database; check extension installations, deployment scripts, and users depending on the `public` schema first.

### 8.4. Transferring Schema Owner

```sql
ALTER SCHEMA app OWNER TO app_owner;
```

Changing the schema owner does not automatically transfer ownership of all objects inside the schema. Tables, sequences, functions, and types may still belong to other roles.

### 8.5. Schema Naming and Boundaries

Use schemas to separate application domains or trust boundaries. Avoid letting unrelated services both have CREATE in the same schema. `search_path` must be controlled to prevent object name shadowing.

### 8.6. Search Path

Inspect:

```sql
SHOW search_path;

SELECT
    rolname,
    rolconfig
FROM pg_catalog.pg_roles
WHERE rolname IN ('app_runtime', 'app_migrator');
```

`search_path` can be configured per role/database. For SECURITY DEFINER functions, set a safe `search_path` and use schema-qualified object references to prevent object substitution attacks.

## 9. Object Privileges by Object Type

### 9.1. Tables and Views

| Privilege | Meaning |
| --- | --- |
| SELECT | Read rows/columns within ACL and RLS scope |
| INSERT | Insert rows |
| UPDATE | Update granted rows/columns |
| DELETE | Delete rows |
| TRUNCATE | Remove all rows using TRUNCATE |
| REFERENCES | Create a foreign key referencing the table |
| TRIGGER | Create a trigger on the table |

Example:

```sql
GRANT SELECT ON TABLE app.orders TO app_read;
GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE app.orders TO app_write;
```

Do not grant TRUNCATE or REFERENCES if the workload does not require them.

### 9.2. Granting Privileges on All Existing Tables

```sql
GRANT SELECT ON ALL TABLES IN SCHEMA app TO app_read;

GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA app TO app_write;
```

ALL TABLES here applies to qualifying tables/views/foreign tables in the schema at the time the command is run. It does not automatically apply to objects created in the future.

### 9.3. Sequences

Sequences have dedicated privileges:

- USAGE: allows `nextval` and `currval`.
- SELECT: allows `currval`.
- UPDATE: allows `nextval` and `setval`.

For example, runtime inserts using a sequence:

```sql
GRANT USAGE ON ALL SEQUENCES IN SCHEMA app TO app_write;
```

Do not grant UPDATE if the application does not need `setval`.

### 9.4. Functions and Procedures

```sql
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA app TO app_runtime;
```

Functions and procedures can have important security semantics. Review SECURITY DEFINER, owner, `search_path`, and execution permissions before granting broadly.

### 9.5. Types

A role may need USAGE on user-defined types to use them in appropriate declarations/statements:

```sql
GRANT USAGE ON TYPE app.order_status TO app_runtime;
```

### 9.6. Large Objects

Large objects have their own ACLs and are not necessarily controlled by table grants. If the application uses large objects, audit privileges on those objects separately.

### 9.7. Column-Level Privileges

PostgreSQL supports column-level grants for certain table privileges:

```sql
GRANT SELECT (order_id, created_at, status)
ON app.orders TO support_read;
```

Column grants can help restrict reading sensitive columns, but you must check table-level grants, PUBLIC, role memberships, and RLS. Table-level SELECT still allows reading all columns.

## 10. Default Privileges for Future Objects

### 10.1. Why Default Privileges Are Needed

`GRANT ... ON ALL TABLES IN SCHEMA` only grants privileges on existing objects. When a migration creates a new table, runtime roles may get permission denied if default privileges are not configured.

### 10.2. Default Privileges Are Tied to the Creator Role

Default privileges apply to objects created by the specified role. They do not automatically apply to objects created by another role merely because that role is a member of the owner role.

Therefore, ensure migrations execute `SET ROLE app_owner` before creating objects.

### 10.3. Configuring Default Table Privileges

```sql
ALTER DEFAULT PRIVILEGES
FOR ROLE app_owner
IN SCHEMA app
GRANT SELECT ON TABLES TO app_read;

ALTER DEFAULT PRIVILEGES
FOR ROLE app_owner
IN SCHEMA app
GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLES TO app_write;
```

### 10.4. Default Sequence Privileges

```sql
ALTER DEFAULT PRIVILEGES
FOR ROLE app_owner
IN SCHEMA app
GRANT USAGE ON SEQUENCES TO app_write;
```

Grant SELECT as well if reporting needs `currval` without granting `nextval`? Choose based on sequence semantics and workload; USAGE allows `nextval`/`currval`, while SELECT allows only `currval`.

### 10.5. Default Function Privileges

EXECUTE on functions is typically granted to PUBLIC by PostgreSQL defaults. If policy requires revoking the default, execute a global default revoke for the creator role:

```sql
ALTER DEFAULT PRIVILEGES
FOR ROLE app_owner
REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

ALTER DEFAULT PRIVILEGES
FOR ROLE app_owner
IN SCHEMA app
GRANT EXECUTE ON FUNCTIONS TO app_runtime;
```

A per-schema default privilege REVOKE cannot remove an existing global grant; global defaults and per-schema defaults are combined according to PostgreSQL rules. Understand this when designing least privilege.

### 10.6. Default Privileges Do Not Modify Existing Objects

After configuring defaults, you still need to grant privileges on older objects:

```sql
GRANT SELECT ON ALL TABLES IN SCHEMA app TO app_read;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA app TO app_write;
```

### 10.7. Inspecting Default ACLs

```sql
SELECT
    defaclrole::regrole AS creator_role,
    defaclnamespace::regnamespace AS schema_name,
    defaclobjtype,
    defaclacl
FROM pg_catalog.pg_default_acl
ORDER BY creator_role, schema_name, defaclobjtype;
```

`defaclnamespace` can be `0` for global defaults. Inspect both global and schema-specific records.

### 10.8. Testing New Objects

Create a test table under the owner role in a test/lab schema, then verify its ACL using `\dp` or a catalog query. Do not assume default ACLs are correct simply because `ALTER DEFAULT PRIVILEGES` returned success.

## 11. Ownership Differs from GRANT

### 11.1. Owners Have Special Administrative Authority

An owner controls the object, including ALTER/DROP and the ability to manage privileges. Another role may be granted SELECT/UPDATE without automatically having the right to change the owner or drop the object.

### 11.2. GRANT ALL Does Not Transfer Ownership

`GRANT ALL PRIVILEGES ON TABLE ...` grants the ACL privileges applicable to the object type. It does not turn the recipient into the owner.

### 11.3. Membership in an Owner Role

Membership may allow a role to exercise owner rights according to membership semantics. However, to create objects with consistent ownership and apply the creator's default privileges, you should `SET ROLE` to the owner role before running DDL.

### 11.4. Owner Roles Should Be NOLOGIN

If the owner role does not have LOGIN, application credentials cannot log in directly as that identity. A migration role with `SET ROLE` privileges can execute controlled DDL.

### 11.5. The Object Creator Determines the Default Owner

An object normally belongs to the role that is `current_user` when the object is created. Check `current_user` in the migration session:

```sql
SELECT session_user, current_user;
```

## 12. Reference Privilege Model for an Application

This example illustrates a database `appdb`, schema `app`, owner role, and runtime roles.

### 12.1. Create Roles

```sql
CREATE ROLE app_owner NOLOGIN;
CREATE ROLE app_read NOLOGIN;
CREATE ROLE app_write NOLOGIN;

CREATE ROLE app_migrator
    LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION
    NOBYPASSRLS;

CREATE ROLE app_runtime
    LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION
    NOBYPASSRLS;

GRANT app_read, app_write TO app_runtime;
```

Provision credentials via a secret manager or secure provisioning flow. Login roles can be created before credentials are set.

### 12.2. Grant SET ROLE Capability to the Migrator

On PostgreSQL 16 and later:

```sql
GRANT app_owner TO app_migrator
    WITH INHERIT FALSE, SET TRUE;
```

On older versions, configure membership/NOINHERIT according to the corresponding semantics and test `SET ROLE` in a lab.

### 12.3. Create Database and Schema

Run CREATE DATABASE in an autocommit session:

```sql
CREATE DATABASE appdb OWNER app_owner;
```

Connect to `appdb` and create the schema:

```sql
CREATE SCHEMA app AUTHORIZATION app_owner;

GRANT CONNECT ON DATABASE appdb TO app_runtime, app_migrator;
GRANT USAGE ON SCHEMA app TO app_read, app_write;
```

### 12.4. Configure Default Privileges

```sql
ALTER DEFAULT PRIVILEGES
FOR ROLE app_owner
IN SCHEMA app
GRANT SELECT ON TABLES TO app_read;

ALTER DEFAULT PRIVILEGES
FOR ROLE app_owner
IN SCHEMA app
GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLES TO app_write;

ALTER DEFAULT PRIVILEGES
FOR ROLE app_owner
IN SCHEMA app
GRANT USAGE ON SEQUENCES TO app_write;
```

### 12.5. Create Objects Under the Owner Role

Connect as the migrator:

```sql
SET ROLE app_owner;

CREATE TABLE app.orders (
    order_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

RESET ROLE;
```

Then inspect the owner and ACL. When using identity columns, PostgreSQL manages sequence dependencies according to identity semantics; with `serial` or manually created sequences, check sequence grants separately.

### 12.6. Verify Runtime Access

```sql
SET ROLE app_runtime;

SELECT count(*) FROM app.orders;

RESET ROLE;
```

Test INSERT/UPDATE inside a test transaction with rollback if appropriate. Do not validate solely with a SELECT; read and write privileges are separate layers.

## 13. Checking Effective Privileges

### 13.1. Database Privileges

```sql
SELECT
    has_database_privilege('app_runtime', 'appdb', 'CONNECT') AS can_connect,
    has_database_privilege('app_runtime', 'appdb', 'CREATE') AS can_create_schema,
    has_database_privilege('app_runtime', 'appdb', 'TEMP') AS can_create_temp;
```

### 13.2. Schema Privileges

```sql
SELECT
    has_schema_privilege('app_runtime', 'app', 'USAGE') AS can_use_schema,
    has_schema_privilege('app_runtime', 'app', 'CREATE') AS can_create_objects;
```

### 13.3. Table Privileges

```sql
SELECT
    has_table_privilege('app_runtime', 'app.orders', 'SELECT') AS can_select,
    has_table_privilege('app_runtime', 'app.orders', 'INSERT') AS can_insert,
    has_table_privilege('app_runtime', 'app.orders', 'UPDATE') AS can_update,
    has_table_privilege('app_runtime', 'app.orders', 'DELETE') AS can_delete,
    has_table_privilege('app_runtime', 'app.orders', 'TRUNCATE') AS can_truncate;
```

### 13.4. Sequence Privileges

```sql
SELECT
    has_sequence_privilege('app_runtime', 'app.orders_order_id_seq', 'USAGE') AS can_nextval,
    has_sequence_privilege('app_runtime', 'app.orders_order_id_seq', 'SELECT') AS can_currval,
    has_sequence_privilege('app_runtime', 'app.orders_order_id_seq', 'UPDATE') AS can_setval;
```

Replace the example sequence name with the actual name. Identity sequences have distinct dependencies/visibility; query the catalog or `pg_get_serial_sequence` when you need to identify the sequence.

### 13.5. Function Privileges

```sql
SELECT
    has_function_privilege(
        'app_runtime',
        'app.calculate_total(bigint)',
        'EXECUTE'
    ) AS can_execute;
```

The function identity must include argument types to distinguish overloads.

### 13.6. ACLs Are Not the Entire Policy

`has_*_privilege` helps check ACLs and effective privileges by role. With RLS, you must also check policies, `row_security`, owner/BYPASSRLS, and session context. A role with SELECT may still see only a subset of rows.

## 14. Catalogs and psql Commands for Auditing

### 14.1. List of Roles

```sql
SELECT
    rolname,
    rolcanlogin,
    rolsuper,
    rolcreatedb,
    rolcreaterole,
    rolreplication,
    rolbypassrls,
    rolinherit,
    rolvaliduntil
FROM pg_catalog.pg_roles
ORDER BY rolname;
```

### 14.2. Database Owners

```sql
SELECT
    datname,
    pg_catalog.pg_get_userbyid(datdba) AS owner,
    datallowconn,
    datconnlimit
FROM pg_catalog.pg_database
ORDER BY datname;
```

### 14.3. Schema Owners

```sql
SELECT
    nspname,
    pg_catalog.pg_get_userbyid(nspowner) AS owner,
    nspacl
FROM pg_catalog.pg_namespace
WHERE nspname NOT LIKE 'pg_%'
  AND nspname <> 'information_schema'
ORDER BY nspname;
```

### 14.4. Table Owners

```sql
SELECT
    schemaname,
    tablename,
    tableowner
FROM pg_catalog.pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, tablename;
```

### 14.5. psql Shortcuts

In psql:

- `\du+`: roles and attributes.
- `\l+`: databases, owners, and ACLs.
- `\dn+`: schemas, owners, and ACLs.
- `\dp`: table/view/sequence privileges.
- `\ddp`: default privileges.
- `\df+`: functions and details.
- `\dp app.*`: ACLs of objects in the `app` schema.

psql commands are meta-commands, not SQL statements; do not send raw `\du` over JDBC as an SQL query.

### 14.6. Information Schema Views

Views such as `information_schema.table_privileges`, `role_table_grants`, and `schema_privileges` are useful for standardized checks, though visibility may be restricted by the executor's privileges. For deep audits, combine catalogs with a controlled superuser/audit role.

## 15. Role Provisioning: Onboarding Users and Services

### 15.1. Identify the Identity Type

Before creating a role, determine:

- Human user or service account?
- Does it need LOGIN or only a group role?
- Does it need read, write, migration, or operational privileges?
- Which databases/schemas are in scope?
- Does it need an expiry or connection limit?
- Who are the owner and approver?
- How will credentials be stored and rotated?

### 15.2. Create a Minimal Login Role

```sql
CREATE ROLE analyst_alex
    LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION
    NOBYPASSRLS
    CONNECTION LIMIT 5;
```

The role name is only an example. Establish a naming convention aligned with the identity source and service catalog.

### 15.3. Grant a Group Role

```sql
GRANT app_read TO analyst_alex;
```

If limited read access is needed, create a dedicated group role per data domain instead of granting SELECT across the entire database.

### 15.4. Provision Credentials Outside Source Control

Use SCRAM-SHA-256 per policy, a secret manager, and a rotation workflow. Do not copy passwords into tickets/chats/logs. For human identities, integrate environment-appropriate authentication such as certificates, LDAP/PAM, or an identity provider if deployed.

### 15.5. Set Expiry When Needed

```sql
ALTER ROLE analyst_alex VALID UNTIL '2026-12-31 23:59:59+00';
```

Set an expiry for temporary access. Remember that VALID UNTIL affects password authentication; use NOLOGIN to block all new logins when offboarding.

### 15.6. Verify Connectivity and Privileges

Use the new identity itself to connect over the real `pg_hba.conf`/network path. Test permitted operations as well as operations that must be denied. Verify role memberships, database CONNECT, schema USAGE, and object ACLs.

## 16. Managing Service Accounts

### 16.1. Each Service Has Its Own Identity

Do not share a single login across an API, reporting job, ETL, and migration pipeline. Separate identities enable query auditing, credential rotation, and scoped privilege revocation.

### 16.2. Separate Runtime and Migration

The runtime role should not have CREATE/ALTER/DROP on production schemas. The migration role can `SET ROLE` to the owner during deployment windows and is managed through CI/CD secrets.

### 16.3. Connection Limits and Pools

CONNECTION LIMIT can be set to constrain a role, but this does not replace pool sizing, global connection capacity, or proxies. Superusers and certain internal connections may not be subject to limits in the same way as regular client roles.

### 16.4. Password Rotation

Safe rotation typically includes:

1. Creating/setting the new credential in the secret manager.
2. Updating clients gradually or supporting overlap via two identities.
3. Verifying that updated clients connect and function properly.
4. Revoking the old credential / disabling the old role.
5. Checking remaining sessions.
6. Recording the rotation timestamp and owner.

If a single role has only one password, plan the rollout to avoid downtime when instances update credentials asynchronously.

### 16.5. Do Not Use SUPERUSER for Health Checks

Health checks only need to connect and run a simple query. Use a dedicated role with only CONNECT and read access to an appropriate object/status.

## 17. Modifying and Revoking Privileges

### 17.1. Direct Revoke

```sql
REVOKE UPDATE, DELETE
ON TABLE app.orders
FROM app_support;
```

If the role still holds privileges via group membership, PUBLIC, or another grant, a direct revoke may not cause operations to be denied.

### 17.2. Revoking Membership

```sql
REVOKE app_write FROM app_runtime;
```

This is typically the cleanest way to manage privilege groups when a runtime identity no longer needs write privileges.

### 17.3. REVOKE ... CASCADE

When a grantor has further granted privileges to other roles using GRANT OPTION, revoking may require CASCADE to revoke dependent grants. CASCADE can have broad impact; inspect dependencies and grant chains before running it.

### 17.4. Checking Privileges via PUBLIC

PUBLIC is not a normal role in `pg_roles`. Grants to PUBLIC can allow every user to continue accessing an object after revoking from a specific role. Inspect ACLs and `has_*_privilege`.

### 17.5. Revoking Database and Schema Privileges

```sql
REVOKE CONNECT ON DATABASE appdb FROM app_runtime;
REVOKE CREATE ON SCHEMA app FROM app_migrator;
REVOKE USAGE ON SCHEMA app FROM app_read;
```

Revoke only after confirming the role has no remaining dependencies. If the application is still active, this can cause requests to fail immediately.

### 17.6. Default Privileges Must Be Revoked Separately

Revoking on existing objects does not automatically remove default privileges for future objects. Inspect `pg_default_acl` and use `ALTER DEFAULT PRIVILEGES ... REVOKE` as appropriate.

## 18. Offboarding and Safely Dropping Roles

### 18.1. Identify All Dependencies First

A role may:

- Own databases/schemas/tables/functions/sequences.
- Have direct privileges on objects.
- Be a member of other roles.
- Have other roles granted membership in it.
- Own tablespaces or shared objects.
- Be referenced in policies, security-definer functions, jobs, or external configurations.
- Have active sessions.

### 18.2. Disable Login First

```sql
ALTER ROLE analyst_alex NOLOGIN;
```

This prevents new logins. It does not automatically terminate already open sessions.

### 18.3. Terminate Sessions in a Controlled Manner

```sql
SELECT
    pid,
    datname,
    application_name,
    state,
    query_start
FROM pg_catalog.pg_stat_activity
WHERE usename = 'analyst_alex';
```

Once the target sessions are confirmed, they can be terminated:

```sql
SELECT pg_catalog.pg_terminate_backend(pid)
FROM pg_catalog.pg_stat_activity
WHERE usename = 'analyst_alex'
  AND pid <> pg_backend_pid();
```

This interrupts the role's transactions. Check the owner, database, application, and impact before executing. Appropriate privileges are required to terminate backends.

### 18.4. Transfer Ownership Before Dropping

To transfer objects owned by the old role to an owner role:

```sql
REASSIGN OWNED BY analyst_alex TO app_owner;
```

This command affects objects in the current database and certain shared objects. Connect to each relevant database and repeat according to your inventory; do not assume running it once in a single database handles the entire cluster.

### 18.5. DROP OWNED

After ownership has been transferred and remaining grants have been identified, DROP OWNED can revoke the role's privileges on objects in the current database and shared objects. If the role still owns un-transferred objects, the command can drop them.

```sql
DROP OWNED BY analyst_alex;
```

This command can destroy data if the role still owns objects. Run it only after reviewing ownership and backup/recovery requirements. Execute in each database requiring cleanup.

### 18.6. Drop the Role

```sql
DROP ROLE analyst_alex;
```

DROP ROLE succeeds only when no dependencies remain. If PostgreSQL reports a dependency, read the error and handle the dependency intentionally; do not blindly use CASCADE as a cleanup shortcut.

### 18.7. Reference Offboarding Order

1. Confirm the owner and offboarding approval.
2. Block new logins via NOLOGIN/credential revocation.
3. Stop services/jobs using the identity.
4. Terminate sessions according to plan.
5. Revoke memberships.
6. Inventory ownership and grants.
7. Reassign ownership to a stable owner role.
8. Run DROP OWNED to revoke remaining grants when safe.
9. Verify the role is gone and applications/maintenance still work.
10. Store evidence and close the ticket.

## 19. Lifecycle Ownership Transfers

### 19.1. When a Team or Service Changes Owner

Ownership should not be tied to an individual who has left or to a short-lived deployment identity. Transfer it to a stable NOLOGIN owner role so ownership does not depend on credential lifecycles.

### 19.2. Transferring Database Owner

```sql
ALTER DATABASE appdb OWNER TO app_owner;
```

### 19.3. Transferring Schema Owner

```sql
ALTER SCHEMA app OWNER TO app_owner;
```

### 19.4. Transferring Table Owner

```sql
ALTER TABLE app.orders OWNER TO app_owner;
```

### 19.5. Transferring Sequence/Function Owner

```sql
ALTER SEQUENCE app.orders_order_id_seq OWNER TO app_owner;
ALTER FUNCTION app.calculate_total(bigint) OWNER TO app_owner;
```

Functions require the full signature to distinguish overloads. For procedures, types, views, and other object classes, use the corresponding `ALTER ... OWNER` command for your version.

### 19.6. REASSIGN OWNED When Transferring Many Objects

```sql
REASSIGN OWNED BY old_migrator TO app_owner;
```

This is useful when the old role owns many objects in the database. Inventory before and after; inspect shared objects and other databases separately.

### 19.7. Ownership and Default Privileges

After transferring ownership, review default privileges for the new owner. `ALTER DEFAULT PRIVILEGES FOR ROLE old_owner` does not automatically become defaults for the new owner. Configure default ACLs for the new owner and verify migrations run under the right role.

## 20. RLS and Ownership

### 20.1. ACL and RLS Are Two Layers

`GRANT SELECT` allows a role to access a table per ACL. Row-level security (RLS) further filters the rows the role is allowed to see or modify.

### 20.2. Table Owners Normally Bypass RLS

A table owner normally is not subject to RLS unless the table has FORCE ROW LEVEL SECURITY enabled. Superusers and roles with BYPASSRLS always bypass RLS.

### 20.3. Runtime Should Not Be the Owner

If the runtime role owns the table, it can bypass RLS by default and has ALTER/DROP rights. Use a NOLOGIN owner and grant the runtime role only the required ACL + RLS policies.

### 20.4. Inspecting RLS Flags

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    pg_catalog.pg_get_userbyid(c.relowner) AS owner,
    c.relrowsecurity,
    c.relforcerowsecurity
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p')
  AND n.nspname = 'app'
ORDER BY c.relname;
```

### 20.5. Test with the Runtime Identity

Do not test only under the owner or superuser. Use the actual runtime role, tenant context, and application path to verify policies.

## 21. Predefined Roles and Administrative Privileges

PostgreSQL provides several predefined roles for monitoring and maintenance, such as `pg_monitor`, `pg_read_all_settings`, `pg_read_all_stats`, `pg_read_all_data`, `pg_write_all_data`, and others depending on the version.

These roles are convenient but have broad scope. For example, `pg_read_all_data` allows reading extensive data across the database without granting SELECT on every table; it does not automatically grant BYPASSRLS. Read the documentation for your exact version before granting them.

### 21.1. Monitoring Role

A monitoring service may need permissions to read statistics and settings. Grant the appropriate predefined role instead of SUPERUSER.

### 21.2. Backup Role

Backup tools may require specific privileges depending on the physical/logical backup method. Do not use a role with BYPASSRLS or SUPERUSER if the tool does not require it.

### 21.3. Maintenance Role

Predefined maintenance roles can allow broad operations across many objects. Verify exact capabilities for your version and restrict role membership.

### 21.4. Auditing Predefined Role Memberships

```sql
SELECT
    member.rolname AS member_role,
    granted.rolname AS predefined_role
FROM pg_catalog.pg_auth_members AS m
JOIN pg_catalog.pg_roles AS member
  ON member.oid = m.member
JOIN pg_catalog.pg_roles AS granted
  ON granted.oid = m.roleid
WHERE granted.rolname LIKE 'pg_%'
ORDER BY member.rolname, granted.rolname;
```

Review each membership based on owner and business need. Do not drop PostgreSQL's predefined roles.

## 22. Auditing and Controlling Privilege Changes

### 22.1. Recording Change Records

Every privilege change should record:

- Request/ticket ID.
- Requester and approver.
- Modified role.
- Database/schema/object scope.
- Before/after privileges or memberships.
- Timestamp and operator.
- Reason and expiry if temporary access.
- Validation results.
- Rollback procedure.

### 22.2. Auditing Role Memberships

Periodically collect role attributes and memberships. Detect:

- Login roles with unnecessary SUPERUSER/CREATEROLE/CREATEDB.
- Memberships in owner/admin roles.
- Unexpected ADMIN OPTION.
- Old roles with no remaining owner.
- Roles with LOGIN that lack an owner.
- Expired temporary access.

### 22.3. Auditing Ownership

Inspect database, schema, table, sequence, function, and type owners. Find objects owned by individuals or decommissioned migration roles.

### 22.4. Auditing Grants

Review direct grants, PUBLIC grants, default ACLs, and membership inheritance. `\dp`, `\ddp`, and catalog queries assist with inspection.

### 22.5. Logging

You can use PostgreSQL logs, an audit extension, or a change management system to record DDL/security changes. `log_statement` and `pgaudit` have trade-offs regarding volume, sensitive SQL text, and overhead; choose according to policy.

### 22.6. Periodic Access Review

Periodically require owners to confirm:
- Is the identity still active?
- Does the role still need the privileges?
- Are the privileges appropriate for its duties?
- Have temporary grants expired?
- Does the service account have an owner and rotation date?
- Can the scope be reduced?

## 23. Common Security Pitfalls

### 23.1. Granting Privileges Directly to Individual Users

Direct grants make auditing and offboarding difficult. Use group roles organized by capability/data domain.

### 23.2. Granting CREATE to Runtime

CREATE on a schema allows creating objects and can cause name shadowing or objects with unintended owners/default ACLs. Reserve CREATE for the migration owner.

### 23.3. Sharing Service Accounts

Shared credentials eliminate attribution, increase blast radius on password leaks, and complicate rotation. Use separate identities.

### 23.4. Using GRANT ALL Without Understanding Scope

GRANT ALL on a database applies only to database privileges; on a schema, only to schema privileges; on tables, to existing object ACLs. It does not transfer ownership and does not automatically create default privileges.

### 23.5. Forgetting PUBLIC

Revoking from a user while privileges still come through PUBLIC. Always inspect ACLs and `has_*_privilege`.

### 23.6. Configuring Default Privileges for the Wrong Creator

Defaults for `app_owner` do not apply if migrations create objects under `app_migrator`. Check `current_user`.

### 23.7. Transferring Schema Owner but Forgetting Objects

Schema ownership does not automatically transfer table/function/sequence ownership. Inventory object owners separately.

### 23.8. Dropping a Role Before Handling Dependencies

A role may own objects or hold grants across multiple databases. Use REASSIGN OWNED/DROP OWNED per database in a controlled manner.

### 23.9. Forgetting Active Sessions

NOLOGIN does not terminate open sessions. Check `pg_stat_activity` and manage session lifecycle.

### 23.10. Unsafe SECURITY DEFINER

A SECURITY DEFINER function runs with the owner's privileges. If `search_path` allows an attacker to create shadowing objects, the function can execute unintended objects. Set a safe `search_path`, schema-qualify references, and restrict EXECUTE.

## 24. Runbook: Onboarding a New Application

1. Identify the service owner, database, and schema scope.
2. Create owner/group/login roles following the naming convention.
3. Provision credentials through a secret manager.
4. Create the database with a NOLOGIN owner.
5. Create the schema with the owner role.
6. Grant CONNECT and USAGE to the appropriate roles.
7. Configure default privileges for tables, sequences, and functions.
8. Grant memberships to runtime/migrator.
9. Verify migrator can `SET ROLE` to the owner.
10. Create a test object under the owner role.
11. Verify the owner, ACL, and default ACL.
12. Connect with the runtime identity and test permitted reads/writes.
13. Test several operations that must be denied.
14. Verify RLS if multi-tenant data is used.
15. Record the inventory and service account owner.

## 25. Runbook: Offboarding a Role

1. Verify the role name, owner, and database scope.
2. Stop applications/jobs using the role.
3. Run `ALTER ROLE ... NOLOGIN` and revoke credentials.
4. Check `pg_stat_activity`; terminate sessions per plan.
5. Check bidirectional memberships.
6. Inventory owned objects and ACL grants.
7. Reassign owned objects to a stable owner role.
8. Run DROP OWNED in each relevant database after review.
9. Verify default ACLs, policies, and external configs no longer reference the role.
10. DROP ROLE.
11. Verify old logins are rejected and other services continue running.
12. Save evidence and close the ticket.

## 26. Runbook: Auditing Ownership and Privileges

### Step 1. Inventory Roles

Retrieve attributes, login state, validity, privileged flags, and connection limits.

### Step 2. Inventory Memberships

Check which roles are members of owner/admin roles; inspect ADMIN/INHERIT/SET options per version.

### Step 3. Inventory Database/Schema Owners

Cross-check against current service/team owners.

### Step 4. Inventory Object Owners

Find objects owned by login identities, former employees, or inactive deployment roles.

### Step 5. Inventory ACLs/Default ACLs

Check grants to PUBLIC, direct grants, group grants, and default privileges.

### Step 6. Test Effective Access

Use `has_*_privilege` and test connections with real identities. With RLS, test per user/tenant context.

### Step 7. Remediate via Change Process

Transfer ownership, revoke grants, or update memberships via tickets with an owner. Do not automatically delete roles based solely on age or NOLOGIN status.

### Step 8. Save a New Baseline

Save a snapshot of roles, memberships, owners, and ACLs after the audit so future reviews can compare against it.

## 27. Practice Exercises with Answers

These exercises assume you have a dedicated PostgreSQL lab. Never revoke privileges, drop roles, or transfer production ownership solely for practice.

### Exercise 1. What is a role in PostgreSQL?

**Answer:** A cluster-wide object representing an identity or a set of privileges, which can be LOGIN or NOLOGIN.

### Exercise 2. How does CREATE USER differ from CREATE ROLE?

**Answer:** CREATE USER is a form of CREATE ROLE with LOGIN; it does not create a different security object type.

### Exercise 3. Does a group role normally have LOGIN?

**Answer:** Normally it is NOLOGIN and used to bundle privileges/memberships.

### Exercise 4. Why do we need a NOLOGIN owner role?

**Answer:** To separate ownership from runtime connection credentials, reducing the risk of exposing the owner identity.

### Exercise 5. How does ownership differ from GRANT?

**Answer:** An owner has object administration rights such as ALTER/DROP and managing privileges; GRANT only assigns specific ACL privileges.

### Exercise 6. Does GRANT ALL transfer ownership?

**Answer:** No.

### Exercise 7. What is LOGIN used for?

**Answer:** It allows a role to log into PostgreSQL if authentication/network policy permits.

### Exercise 8. Does NOLOGIN terminate existing sessions?

**Answer:** No. It blocks new logins; existing sessions must be handled separately.

### Exercise 9. Should SUPERUSER be granted to application runtime?

**Answer:** No. Runtime should have only the minimum privileges needed for the workload.

### Exercise 10. Is CREATEROLE sensitive?

**Answer:** Yes. It allows managing roles/memberships within the scope permitted by the version.

### Exercise 11. What does CREATEDB allow?

**Answer:** Creating databases.

### Exercise 12. What is the impact of BYPASSRLS?

**Answer:** It bypasses row-level security, potentially crossing tenant data boundaries.

### Exercise 13. What does GRANT app_read TO app_runtime mean?

**Answer:** `app_runtime` is a member of `app_read` and can receive privileges according to membership options.

### Exercise 14. Does revoking membership delete the group role?

**Answer:** No. It only removes the member role's membership.

### Exercise 15. What does INHERIT control?

**Answer:** Automatic inheritance of privileges from memberships according to semantics/version.

### Exercise 16. What does SET ROLE do?

**Answer:** Switches the effective `current_user` to a role permitted to be set within the session.

### Exercise 17. How does session_user differ from current_user?

**Answer:** `session_user` is the initial connection identity; `current_user` is the current effective role for permission checks.

### Exercise 18. How does ADMIN OPTION differ from GRANT OPTION?

**Answer:** ADMIN OPTION manages role membership; GRANT OPTION allows further granting object privileges.

### Exercise 19. Which membership options did PostgreSQL 16 add?

**Answer:** Separate ADMIN, INHERIT, and SET options for membership grants.

### Exercise 20. Does database CONNECT grant table SELECT?

**Answer:** No. Schema USAGE and object SELECT are also required.

### Exercise 21. What does schema USAGE allow?

**Answer:** Resolving/accessing objects inside the schema if the role has privileges on the object.

### Exercise 22. What does schema CREATE allow?

**Answer:** Creating new objects inside the schema.

### Exercise 23. Is table SELECT sufficient without schema USAGE?

**Answer:** No. The role also needs access privileges on the schema.

### Exercise 24. What is PUBLIC?

**Answer:** A pseudo-role representing all roles in the cluster.

### Exercise 25. Why must PUBLIC grants be checked?

**Answer:** A user may still retain privileges through PUBLIC even after direct grants are revoked.

### Exercise 26. Does the database owner automatically own every table?

**Answer:** No. Object ownership is managed separately.

### Exercise 27. Does GRANT ALL ON DATABASE grant all privileges on tables?

**Answer:** No. It applies only to database-level privileges.

### Exercise 28. What does sequence USAGE allow?

**Answer:** `nextval` and `currval`.

### Exercise 29. What does sequence SELECT allow?

**Answer:** `currval`.

### Exercise 30. What does sequence UPDATE allow?

**Answer:** `nextval` and `setval`.

### Exercise 31. When do default privileges apply?

**Answer:** When new objects are created by the configured creator role.

### Exercise 32. Does ALTER DEFAULT PRIVILEGES modify existing objects?

**Answer:** No. Separate GRANTs are needed for existing objects.

### Exercise 33. Do default privileges for app_owner apply when app_migrator creates a table?

**Answer:** No, unless the effective creator role is switched to `app_owner`.

### Exercise 34. Why do migrations use SET ROLE app_owner?

**Answer:** So created objects belong to the owner role and receive that role's default privileges.

### Exercise 35. To whom is default function EXECUTE usually granted?

**Answer:** PUBLIC by PostgreSQL default, unless changed by default privileges configuration.

### Exercise 36. Can a per-schema REVOKE remove a global default grant?

**Answer:** No. Per-schema defaults are additive; revoking a global grant must be handled at the global level.

### Exercise 37. What is pg_default_acl used to inspect?

**Answer:** Default privileges by creator role and object type, both global and schema-specific.

### Exercise 38. What is has_schema_privilege used for?

**Answer:** Checking whether a role has USAGE/CREATE or the queried schema privilege.

### Exercise 39. Which view lists role attributes?

**Answer:** `pg_roles`.

### Exercise 40. What does pg_auth_members store?

**Answer:** Membership relationships between member roles and granted roles along with related options.

### Exercise 41. What does REASSIGN OWNED do?

**Answer:** Transfers ownership of objects belonging to the old role to a new role within the current database and related shared objects.

### Exercise 42. Must REASSIGN OWNED be run in every relevant database?

**Answer:** Yes. Run it in each database where ownership of objects in that database needs to be handled.

### Exercise 43. What does DROP OWNED do?

**Answer:** Drops objects still owned by the role in the current scope and revokes privileges granted to the role on objects; it can destroy data.

### Exercise 44. Does DROP OWNED delete the role?

**Answer:** No. Run DROP ROLE only after dependencies are resolved.

### Exercise 45. Why should DROP ROLE CASCADE not be used carelessly?

**Answer:** It can drop/revoke broad dependencies and cause unintended loss of objects or privileges.

### Exercise 46. Does NOLOGIN replace password rotation?

**Answer:** No. NOLOGIN blocks logins; rotation changes credentials per a separate lifecycle.

### Exercise 47. What does VALID UNTIL apply to?

**Answer:** Password authentication expiration; it is not a replacement for NOLOGIN across all auth methods.

### Exercise 48. Why should each service have its own login?

**Answer:** Clear attribution, rotation, and offboarding scope; avoids shared credentials.

### Exercise 49. Why should runtime and migration roles be separated?

**Answer:** Runtime only needs DML; migration needs DDL/`SET ROLE` owner during deployment workflows.

### Exercise 50. Does changing the schema owner transfer table owners?

**Answer:** No. Objects inside have their own ownership.

### Exercise 51. Does a table owner normally bypass RLS?

**Answer:** Yes, unless FORCE ROW LEVEL SECURITY is enabled; superuser/BYPASSRLS always bypass.

### Exercise 52. Does GRANT SELECT bypass RLS?

**Answer:** No. ACLs and row policies are two separate layers.

### Exercise 53. What does pg_database indicate about the owner?

**Answer:** The `datdba` column is the owner's OID; use `pg_get_userbyid` to display the name.

### Exercise 54. Which psql command displays roles?

**Answer:** `\du` or `\du+`.

### Exercise 55. Which psql command displays default privileges?

**Answer:** `\ddp`.

### Exercise 56. Why is terminating sessions necessary when offboarding?

**Answer:** NOLOGIN does not end previously authenticated sessions.

### Exercise 57. Should the predefined role pg_read_all_data be granted broadly?

**Answer:** No. It has broad read scope; grant based on need and audit it.

### Exercise 58. What risk does a SECURITY DEFINER function carry?

**Answer:** It runs with the owner's privileges; an unsafe `search_path`/object shadowing can create privilege escalation.

### Exercise 59. When should a new role/ACL baseline be created?

**Answer:** After onboarding/offboarding or an approved access review, save a snapshot of roles, memberships, owners, and ACLs.

### Exercise 60. Create a role offboarding checklist

**Suggested answer:**

1. Identify the identity, owner, databases, and service dependencies.
2. Stop jobs/services and revoke credentials.
3. Run `ALTER ROLE NOLOGIN`.
4. Inspect/terminate active sessions per the change plan.
5. Inspect bidirectional memberships and revoke them.
6. Inventory owned objects, database/schema owners, and grants.
7. Run `REASSIGN OWNED` to a stable owner role in each relevant database.
8. Review and run `DROP OWNED` to revoke remaining grants when safe.
9. Check default ACLs, policies, functions, and external configs.
10. Run `DROP ROLE`, verify no dependencies remain, and save audit evidence.

## 28. Production Checklist

| Check | Requirement |
| --- | --- |
| Role naming | Naming conventions exist for human, service, group, and owner roles |
| Login identities | Each service/person has a dedicated identity |
| Group roles | Privileges are grouped by capability/domain |
| Owner roles | NOLOGIN and assigned to an owner team |
| Runtime privileges | Only required privileges |
| SUPERUSER | Not granted to runtime |
| CREATEROLE/CREATEDB | Has justification and an owner |
| REPLICATION | Granted only to replication identities |
| BYPASSRLS | Strictly controlled |
| Password/auth | Secret manager and rotation policy |
| VALID UNTIL | Temporary access has an expiry |
| Membership | INHERIT/SET/ADMIN options are reviewed |
| Database owner | Correct stable owner role |
| CONNECT | Only identities that need to connect |
| Schema owner | Correct owner role |
| Schema USAGE | Runtime roles granted proper scope |
| Schema CREATE | Only owner/migration roles |
| PUBLIC | Database/schema/function ACLs are checked |
| Object grants | Minimal table/sequence/function/type privileges |
| Default privileges | Configured per creator role |
| Migration session | SET ROLE owner before DDL |
| Existing objects | Explicit GRANTs, not relying on defaults |
| Ownership inventory | Tables, sequences, functions, and types |
| RLS | Owner/runtime/BYPASSRLS behavior is tested |
| SECURITY DEFINER | Owner, search_path, and EXECUTE are reviewed |
| Audit | Change ticket, approver, before/after |
| Onboarding | Provisioning and validation runbook exists |
| Offboarding | NOLOGIN, sessions, REASSIGN/DROP OWNED |
| Active sessions | Checked before dropping |
| Cross-database cleanup | Handled in each relevant database |
| Predefined roles | Membership has justification |
| Access review | Scheduled with owner confirmation |
| Baseline | Roles, memberships, owners, and ACLs are saved |
| Version compatibility | Membership options/catalog columns match major version |

## 29. Summary

Lifecycle management of roles, databases, schemas, and ownership helps PostgreSQL maintain clear access controls as systems, personnel, and services evolve. A sustainable model separates login identities, group roles, and owner roles; grants privileges layer by layer; uses default privileges for future objects; and follows safe transfer/offboarding procedures.

Key principles:

1. **Roles are identities and privilege-grouping units.** LOGIN roles are for connections; NOLOGIN roles represent groups or owners.
2. **Separate runtime from ownership.** Runtime does not need to own objects or hold DDL privileges.
3. **Ownership differs from GRANT.** GRANT ALL does not transfer object ownership.
4. **Databases, schemas, and objects are three separate privilege layers.** CONNECT, USAGE, and SELECT govern different steps.
5. **Memberships must be audited.** INHERIT, SET, and ADMIN OPTION affect effective privileges.
6. **Default privileges are tied to the creator role.** Migrations must create objects under the proper owner role.
7. **Default privileges do not apply retroactively.** Grant privileges separately for existing objects.
8. **PUBLIC is cluster-wide.** Check grants through PUBLIC during audits.
9. **RLS adds a row-control layer.** Table ACLs do not replace row policies.
10. **Schema ownership does not automatically transfer object owners.** Inventory tables, sequences, functions, and types separately.
11. **Offboarding must handle sessions and dependencies.** NOLOGIN does not terminate sessions.
12. **REASSIGN OWNED and DROP OWNED are database-scoped.** Execute them in each database with an inventory.
13. **Do not drop a role before transferring ownership/revoking grants.** Keep a stable owner role for objects.
14. **Predefined roles can be very broad.** Grant according to least privilege.
15. **Audits and baselines must preserve history.** Record who changed what, why, and the effective privileges after the change.

Reference privilege model:

```text
              app_migrator (LOGIN)
                      |
                  SET ROLE
                      |
                      v
               app_owner (NOLOGIN)
                      |
               owns schema/objects
                      |
             +--------+---------+
             |                  |
             v                  v
         app_read            app_write
          (NOLOGIN)           (NOLOGIN)
             ^                  ^
             |                  |
             +--------+---------+
                      |
                      v
              app_runtime (LOGIN)
                 DML only
```

**Final review question:** "When a new service is created, who owns the database/schema and objects? Which exact privileges does the runtime identity receive? Do migrations create objects under the owner role so default privileges apply? When a service is decommissioned, can we disable logins, transfer ownership, and revoke grants without losing another team's data?" A solid role lifecycle process must answer those questions through a clear role model, catalog inventory, and audit trail.
