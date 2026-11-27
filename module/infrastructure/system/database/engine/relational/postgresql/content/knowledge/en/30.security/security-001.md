# Roles, LOGIN, Role Membership, and Inherited Privileges in PostgreSQL

When designing PostgreSQL security, the question is not just **"can the user log in?"**, but also **"after logging in, what are they allowed to do, where do the privileges come from, and which roles can they switch to?"**.

Suppose a system has three user groups:

- Reporting staff may only read documents.
- Editorial staff may read and, when genuinely needed, edit documents.
- Deployment staff may create tables and run migrations, while the day-to-day application should not own the schema.

A poorly segregated design might create a shared `app_user` account granted `SUPERUSER` or `ALL PRIVILEGES` just to "avoid permission errors." That design works at first, but creates major risk: SQL injection, a compromised application, a faulty migration, or a programming bug can all cause widespread damage.

PostgreSQL provides a **role-based access control (RBAC)** system:

- **Role**: an identity used to own objects, receive privileges, and be a member of other roles.
- **`LOGIN`**: an attribute allowing a role to be used as a login account, while authentication and connection privileges are separate steps.
- **`NOLOGIN`**: a role not used for direct login, typically intended for privilege groups or object ownership.
- **Membership**: the relationship where one role is a member of another role via `GRANT role TO member`.
- **Privilege inheritance**: object privileges of a parent role can be used automatically through membership paths that allow inheritance.
- **`SET ROLE`**: explicitly switching the *effective current role* to a role that the session is allowed to assume.
- **Admin option**: the privilege to administer membership of the granted role, which does not imply all table privileges or all role attributes.

This lesson belongs to the **Security** chapter of the **Database Engine Relational PostgreSQL** module. We will build a lab with a reader role, a writer role, two login roles, and inheritance/role-switching scenarios, then expand into schema privileges, ownership, RLS, function security, and checking effective privileges.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish between a PostgreSQL **role**, an account with `LOGIN`, a `NOLOGIN` privilege group, and a database user in common parlance.
2. Understand the **cluster-wide** scope of roles, as opposed to privileges on individual databases, schemas, and objects.
3. Create and modify roles with `CREATE ROLE` and `ALTER ROLE` following the principle of least privilege.
4. Grant and revoke privileges on tables, schemas, and sequences using `GRANT`/`REVOKE`.
5. Grant role membership and understand direct as well as multi-level membership.
6. Distinguish the `INHERIT`, `SET`, and `ADMIN` membership options in PostgreSQL 16+.
7. Know the key differences between PostgreSQL 15 and earlier versus PostgreSQL 16+ when configuring inheritance.
8. Distinguish **object privileges** from **role attributes** such as `SUPERUSER`, `CREATEDB`, `CREATEROLE`, `REPLICATION`, and `BYPASSRLS`.
9. Understand `session_user`, `current_user`, and `SET ROLE`/`RESET ROLE` behavior.
10. Design reader/writer/owner/deployer role groups following the principle of least privilege.
11. Recognize the roles of `PUBLIC`, schema `USAGE`, database `CONNECT`, and default privileges.
12. Inspect effective privileges using `pg_roles`, `pg_auth_members`, `pg_has_role`, `has_table_privilege`, and psql commands.
13. Analyze scenarios where a revoke is insufficient, privileges arrive through another path, and role memberships are nested.
14. Understand the relationship between roles, object ownership, RLS, `SECURITY DEFINER`, and application permissions.
15. Avoid dangerous configurations such as letting an app role own all tables, using a superuser for a connection pool, or storing passwords in SQL logs.

## 2. What Layers Exist in the PostgreSQL Privilege System?

~~~mermaid
flowchart TD
    LOGIN["Login role: app_editor"] -->|"membership"| R["NOLOGIN role: app_reader"]
    LOGIN -->|"membership (may require SET ROLE)"| W["NOLOGIN role: app_writer"]
    R -->|"USAGE"| SCHEMA["Schema: app"]
    R -->|"SELECT"| TBL["Table: app.documents"]
    W -->|"INSERT/UPDATE"| TBL
    DB["Database: shopdb"] -->|"CONNECT privilege"| LOGIN
    ACL["RLS / table privileges / object owner"] --> TBL
~~~

For a normal connection session to read `app.documents`, multiple conditions must be evaluated:

1. Did the client authenticate successfully into **a role with LOGIN**?
2. Does the role have `CONNECT` on the database?
3. Does the role have `USAGE` on schema `app`?
4. Does the role have `SELECT` on the table or the relevant columns?
5. If **row-level security** is enabled, does the policy allow reading those rows?
6. Are there other privileges from role membership, `PUBLIC`, ownership, or `SECURITY DEFINER` affecting the outcome?

**No single `GRANT SELECT` statement guarantees that all remaining conditions have already been met.**

## 3. What Are Roles and Users?

In modern PostgreSQL, **users and groups are unified under the concept of a role**.

A role can:

- Be used for login authentication if it has `LOGIN`.
- Receive privileges on tables, schemas, sequences, functions, databases, and other objects.
- Own objects.
- Be a member of other roles.
- Be managed by a role with appropriate privileges.

Two familiar statements:

~~~sql
CREATE ROLE app_reader NOLOGIN;

CREATE ROLE app_user LOGIN;
~~~

`app_reader` can serve as a privilege group. `app_user` can serve as a login identity, but it does not automatically gain read access to every table.

### CREATE USER and CREATE GROUP

PostgreSQL still keeps historical aliases:

~~~sql
CREATE USER demo_user;

CREATE GROUP demo_group;
~~~

In essence, these are convenient shorthands for `CREATE ROLE` with different defaults:

- `CREATE USER` corresponds to a role that defaults to `LOGIN`.
- `CREATE GROUP` corresponds to a role that defaults to `NOLOGIN`.

**A NOLOGIN role is not less "powerful" in terms of object privileges.** It simply cannot log in directly; a session permitted to `SET ROLE` to that role can still use it according to membership rules.

## 4. PostgreSQL Roles Have Cluster-Wide Scope

This is easy to overlook if you are used to other database management systems.

**A PostgreSQL role is a database cluster-level object**, not confined to a single database.

For example:

~~~sql
CREATE ROLE report_reader NOLOGIN;
~~~

This role exists across the entire cluster, even when there are multiple databases. However:

- A `SELECT` privilege on a table in database A **does not automatically carry over** to a table in database B.
- Schemas and tables are per-database objects.
- `CONNECT` on each database can differ.
- PostgreSQL does not let a regular query directly join objects across two independent databases merely because a role exists cluster-wide.

### Implications for Multi-Tenant Environments

If each tenant is a separate database within the same cluster, you should:

- Avoid role name collisions or follow a clear naming convention.
- Check the memberships of roles used across databases.
- Grant object privileges separately per database.
- Avoid creating one account with cluster-wide access when it only needs access to a single tenant.

**A cluster-wide role does not mean cluster-wide access.**

## 5. What Does LOGIN Mean?

A `LOGIN` role can be used as the identity for a connection, provided the authentication and connection steps succeed.

~~~sql
CREATE ROLE lab378_reporter LOGIN;
~~~

However, **`LOGIN` does not by itself guarantee a successful connection**:

- The `pg_hba.conf` policy must allow the corresponding connection/authentication type.
- A password or external authentication mechanism (SCRAM, certificate, peer, IAM integration, etc.) must be configured.
- The database must grant `CONNECT` to the role.
- The role must also satisfy relevant constraints such as expiration or connection limits if configured.
- Network, TLS, and database availability must also permit the connection.

### Do Not Hard-Code Passwords

Avoid:

~~~sql
-- Example NOT TO USE in source code/CI logs:
CREATE ROLE unsafe_app LOGIN PASSWORD 'plain-text-secret';
~~~

The snippet above is an **anti-pattern**, not a recommended command to run.

In `psql`, an administrator can use the interactive command:

~~~text
\password lab378_reporter
~~~

This command avoids typing the password as a literal SQL statement in shell history. In production, use a secret manager/credential rotation, modern authentication policies, and protected connections.

### When Is NOLOGIN Used?

~~~sql
CREATE ROLE lab378_reader NOLOGIN;
CREATE ROLE lab378_writer NOLOGIN;
~~~

These two roles do not need passwords. They represent **privilege bundles** and can be granted as memberships to accounts that have `LOGIN`.

## 6. Role Attributes Are Distinct from Object Privileges

Role attributes are declared via `CREATE ROLE`/`ALTER ROLE`:

| Role attribute | Purpose |
| --- | --- |
| `LOGIN`/`NOLOGIN` | Allow/disallow direct login |
| `SUPERUSER` | Very broad special privileges, bypassing many standard checks |
| `CREATEDB` | Allow creating databases |
| `CREATEROLE` | Allow managing roles subject to version rules/scope |
| `REPLICATION` | Privileges for replication-related operations |
| `BYPASSRLS` | Bypass row-level security |
| `INHERIT`/`NOINHERIT` | Attribute related to default membership inheritance; semantics depend on version |
| `CONNECTION LIMIT` | Appropriate connection limit |
| `PASSWORD`/`VALID UNTIL` | Credentials/expiration configuration |

A role having `CREATEDB` does not mean it can `SELECT` on every table.

A role having `SELECT` on a table does not mean it can create databases.

### Role Attributes Are Not Automatically "Inherited" Like Table Privileges

Suppose:

~~~sql
CREATE ROLE powerful_owner NOLOGIN CREATEDB;

GRANT powerful_owner TO ordinary_user;
~~~

**Do not infer** that `ordinary_user` automatically receives `CREATEDB` just because the membership has `INHERIT`. Special role attributes are not inherited the way `SELECT` on an object is.

If a session is allowed to run `SET ROLE powerful_owner`, the effective role and privilege context can change according to `SET ROLE` semantics. That is different from having the attribute "permanently added" to the login role.

**Do not grant `SUPERUSER`/`CREATEROLE`/`BYPASSRLS` to an application connection just to work around permission errors.**

## 7. Principle of Least Privilege

**Least privilege** means each role has only the permissions it genuinely needs.

Example role layout in a system:

| Role | LOGIN | Responsibility | Intended privileges |
| --- | --- | --- | --- |
| `app_reader` | No | Read group | Schema `USAGE`, `SELECT` on specific tables |
| `app_writer` | No | Data modification group | Selective `SELECT`/`INSERT`/`UPDATE` |
| `app_owner` | No | Owns schemas/tables | Ownership rights, scoped DDL |
| `app_web` | Yes | Production API | Limited membership in required data groups |
| `app_deployer` | Yes | Runs migrations | `SET ROLE app_owner` when permitted |
| `app_analyst` | Yes | Reporting queries | Read-only membership only |

Why separate the owner?

- Production login roles have minimal ability to alter or drop tables.
- DDL follows a separate deployment/audit path.
- Compromising application credentials does not automatically mean losing control over every object in the schema.
- It is easier to review permissions through reader/writer groups instead of ad-hoc grants to individual services.

Do not assume that having 6 roles is always safer than having 2 roles. You need roles aligned with real functions, avoiding deeply nested roles that are hard to reason about.

## 8. Two Completely Different Kinds of GRANT

### 8.1. Granting Object Privileges

~~~sql
GRANT SELECT
ON TABLE some_schema.some_table
TO app_reader;
~~~

This is an **object privilege grant**: it allows `app_reader` to read the specified table.

### 8.2. Granting Role Membership

~~~sql
GRANT app_reader TO app_analyst;
~~~

This is a **role membership grant**: `app_analyst` becomes a member of `app_reader` according to the applicable options.

Both statements use `GRANT`, but their targets differ:

| Statement | What is granted |
| --- | --- |
| `GRANT SELECT ON table TO role` | Object read privilege |
| `GRANT USAGE ON SCHEMA TO role` | Privilege to use the schema namespace |
| `GRANT role_a TO role_b` | Membership of `role_a` granted to `role_b` |
| `GRANT role_a TO role_b WITH ADMIN ...` | Membership along with a membership-administration option |

**You cannot replace `GRANT SELECT ON table` with `GRANT table TO user`.** A table is not a role.

## 9. Membership Can Form a Privilege Graph

~~~mermaid
flowchart LR
    U["lab378_editor (LOGIN)"] -->|"INHERIT TRUE"| R["lab378_reader (NOLOGIN)"]
    U -->|"INHERIT FALSE / SET TRUE"| W["lab378_writer (NOLOGIN)"]
    R -->|"SELECT"| T["lab378.documents"]
    W -->|"SELECT/INSERT/UPDATE"| T
~~~

In this PostgreSQL 16+ design:

- The editor logs in with the `lab378_editor` identity.
- The reader's `SELECT` privilege is inherited automatically.
- The writer's write privileges **are not automatically inherited** because the membership edge has `INHERIT FALSE`.
- When writes are needed, the editor can run `SET ROLE lab378_writer` if the edge/path has `SET TRUE`.
- After `RESET ROLE`, the current role returns to the original role and does not keep writer privileges as a permanent effective state.

**Membership is a role relationship; inheritance is privilege-usage behavior.** The two are not identical.

## 10. PostgreSQL 16+ Has Three Important Membership Options

Starting in PostgreSQL 16, each membership grant can carry independent properties:

| Membership option | Meaning |
| --- | --- |
| `INHERIT TRUE/FALSE` | Whether object privileges of the granted role are used automatically through this membership path |
| `SET TRUE/FALSE` | Whether `SET ROLE` to the granted role is permitted through this membership path |
| `ADMIN TRUE/FALSE` | Whether the member can administer/re-grant membership of that role under current rules |

**PostgreSQL 16+** example:

~~~sql
GRANT lab378_reader TO lab378_reporter
WITH INHERIT TRUE, SET TRUE, ADMIN FALSE;

GRANT lab378_reader TO lab378_editor
WITH INHERIT TRUE, SET TRUE, ADMIN FALSE;

GRANT lab378_writer TO lab378_editor
WITH INHERIT FALSE, SET TRUE, ADMIN FALSE;
~~~

### Three Typical Configurations

| INHERIT | SET | Expected behavior |
| --- | --- | --- |
| TRUE | TRUE | Uses object privileges automatically and can `SET ROLE` to the granted role |
| FALSE | TRUE | Does not use privileges automatically, but can explicitly switch roles when needed |
| TRUE | FALSE | Automatically uses inheritable privileges, but cannot directly switch to that role via this SET path |
| FALSE | FALSE | Membership may serve administrative/structural purposes, but does not auto-grant object privileges and does not allow SET via that edge |

`ADMIN` is a separate axis. You can have `ADMIN TRUE` with `INHERIT FALSE`; **membership administration privilege does not turn into `SELECT`/`UPDATE` on tables**.

### Distinguishing "Is a Member" from "Can Use"

A role may appear as a member in the catalog yet lack an `INHERIT` path to use privileges automatically, and also lack a `SET` path to switch roles. Therefore, merely asking "is the user a member of the role?" is **not enough** to conclude what operations the user can execute.

## 11. How PostgreSQL 15 and Earlier Differ

Before PostgreSQL 16, memberships did not have the per-edge `INHERIT`/`SET` option set found in PostgreSQL 16+. Inheritance behavior was tied much more directly to the `INHERIT`/`NOINHERIT` attribute of the member role.

Historical example:

~~~sql
CREATE ROLE old_style_user LOGIN NOINHERIT;

GRANT old_style_group TO old_style_user;
~~~

In older versions, `NOINHERIT` indicated that the role did not automatically use membership privileges via default inheritance, while `SET ROLE` still followed that version's membership semantics.

### Important Rule Starting in PostgreSQL 16

In PostgreSQL 16+:

- The `INHERIT`/`NOINHERIT` attribute on a role governs **the default `INHERIT` value for new membership grants** to that role.
- Each existing membership has its own `inherit_option`.
- **`ALTER ROLE some_role NOINHERIT` must not be treated as a bulk/retroactive fix for every membership edge already granted.**
- To control existing inheritance rights, you must inspect and configure options on the memberships according to the running version's mechanism.

Consequently, a guide that simply says "`ALTER ROLE user NOINHERIT` and all privileges are cut off" can be **wrong on PostgreSQL 16+** if an earlier grant still carries `INHERIT TRUE`.

**The following lab uses PostgreSQL 16+ syntax** to show both `INHERIT` and `SET` explicitly. For PostgreSQL 15 and earlier, adjust the membership statements to match your version; do not blindly copy `WITH INHERIT FALSE, SET TRUE` syntax onto an older server.

## 12. Lab Setup: Cluster-Level Roles

**To practice:** you need an admin account with permission to create roles and grant appropriate memberships, along with a dedicated practice database for the schema and table. Roles have **cluster-wide** scope, so do not run this on a cluster that already uses `lab378_*` names for another purpose.

Run the following statements **only once**. If a role already exists, `CREATE ROLE` will fail; do not blindly run `DROP ROLE ... CASCADE` on a production cluster to "reset" things.

~~~sql
-- Run as an administrative role with appropriate privileges.
-- Lab designed for PostgreSQL 16+.
CREATE ROLE lab378_reader NOLOGIN;
CREATE ROLE lab378_writer NOLOGIN;

CREATE ROLE lab378_reporter LOGIN;
CREATE ROLE lab378_editor LOGIN;

GRANT lab378_reader TO lab378_reporter
WITH INHERIT TRUE, SET TRUE, ADMIN FALSE;

GRANT lab378_reader TO lab378_editor
WITH INHERIT TRUE, SET TRUE, ADMIN FALSE;

GRANT lab378_writer TO lab378_editor
WITH INHERIT FALSE, SET TRUE, ADMIN FALSE;
~~~

### Authentication Note

The two login roles do not yet have a password or real authentication mechanism configured. You can test using `SET ROLE` from an administrative session permitted to do so, or configure secure login separately and connect directly.

Do not assume `CREATE ROLE ... LOGIN` alone is sufficient for clients connecting from the internet.

### Role of Each Membership

| Login | Membership path | Automatically usable privileges | Role available via SET if permitted along that path |
| --- | --- | --- | --- |
| reporter | reader, INHERIT TRUE | Reader | Reader |
| editor | reader, INHERIT TRUE | Reader | Reader |
| editor | writer, INHERIT FALSE | Writer not auto-used | Writer |

This is a demonstrative model for observing `SET ROLE`, not a recommendation that every web application should switch roles on every request.

## 13. Creating the Schema, Table, and Demo Data

Run this inside the **chosen lab database**, using an administrative role with permission to create schemas and tables.

~~~sql
-- Run only in the practice database.
CREATE SCHEMA lab378;

CREATE TABLE lab378.documents (
    doc_id bigint PRIMARY KEY,
    title text NOT NULL,
    body text NOT NULL,
    visibility text NOT NULL DEFAULT 'internal'
        CHECK (visibility IN ('internal', 'public')),
    created_at timestamptz NOT NULL
        DEFAULT transaction_timestamp()
);

INSERT INTO lab378.documents (
    doc_id, title, body, visibility
)
VALUES
    (1, 'Role basics', 'Roles control privileges.', 'public'),
    (2, 'Internal note', 'For authorized readers.', 'internal'),
    (3, 'Membership', 'Members can inherit or set roles.', 'public');
~~~

In this lab, the admin created the table, so the admin is the initial owner. The two group roles only receive the privileges we are about to grant; they **do not automatically own the table**.

### Why Not Use Real System Tables?

We need to verify privileges without affecting production data. A lab table makes it easy to observe operation successes/failures and clean up in a controlled way.

## 14. Granting Schema and Table Privileges

~~~sql
GRANT USAGE ON SCHEMA lab378
TO lab378_reader, lab378_writer;

GRANT SELECT
ON TABLE lab378.documents
TO lab378_reader;

GRANT SELECT, INSERT, UPDATE
ON TABLE lab378.documents
TO lab378_writer;
~~~

Here:

- `lab378_reader` can read.
- `lab378_writer` can read, `INSERT`, and `UPDATE`.
- Neither role is granted `DELETE` through these grants.
- Neither role is granted `CREATE` on schema `lab378` through the statements above.

### Why Does the Writer Also Have SELECT?

Real-world SQL `UPDATE` statements often read columns in `WHERE`, `RETURNING`, or `SET` expressions, and PostgreSQL requires appropriate `SELECT` privileges on the columns being read. Granting `SELECT` to the writer allows conditional `UPDATE` examples to work.

In stricter systems, you can use column-level grants or reviewed `SECURITY DEFINER` functions to restrict how data is modified instead of giving the writer broad read access.

## 15. Reading a Table Usually Requires Privileges at Multiple Layers

Having only:

~~~sql
GRANT SELECT
ON TABLE lab378.documents
TO lab378_reader;
~~~

is not enough if the role lacks `USAGE` on schema `lab378`.

Typically, to access a table by name:

1. The role must be allowed to connect to the database.
2. It must have `USAGE` on the schema containing the table.
3. It must have `SELECT` on the table/appropriate columns.
4. RLS policies, if enabled, must also allow seeing the rows to be read.

### USAGE and CREATE on a Schema Are Different

~~~sql
GRANT USAGE ON SCHEMA lab378 TO lab378_reader;
~~~

allows looking up/resolving objects inside the schema according to rules, **not creating new objects**.

~~~sql
GRANT CREATE ON SCHEMA lab378 TO some_role;
~~~

is what grants the ability to create objects in the schema where permitted. **`CREATE` on a schema does not imply automatic `SELECT` on existing tables.**

### Database Connection Is Yet Another Privilege

`GRANT CONNECT ON DATABASE ...` must be run against a specific database name. Conceptual example:

~~~sql
-- ILLUSTRATIVE: only use if database shop_training actually exists.
GRANT CONNECT ON DATABASE shop_training
TO lab378_reporter, lab378_editor;
~~~

Do not run this statement if database `shop_training` does not exist. Many initial PostgreSQL installations grant `PUBLIC` `CONNECT` on some databases by default, but that policy may have been revoked; **you must check the actual configuration**.

## 16. Inspecting Roles and Memberships from the Catalog

### Listing Role Attributes

~~~sql
SELECT
    rolname,
    rolcanlogin,
    rolinherit,
    rolcreatedb,
    rolcreaterole,
    rolsuper,
    rolreplication,
    rolbypassrls
FROM pg_roles
WHERE rolname LIKE 'lab378_%'
ORDER BY rolname;
~~~

Columns such as `rolcanlogin`, `rolinherit`, and `rolsuper` are **role attributes**, not a complete list of object privileges.

### Listing Membership Edges (PostgreSQL 16+)

~~~sql
SELECT
    member_role.rolname AS member_name,
    granted_role.rolname AS granted_role,
    m.inherit_option,
    m.set_option,
    m.admin_option
FROM pg_auth_members AS m
JOIN pg_roles AS member_role
    ON member_role.oid = m.member
JOIN pg_roles AS granted_role
    ON granted_role.oid = m.roleid
WHERE member_role.rolname LIKE 'lab378_%'
   OR granted_role.rolname LIKE 'lab378_%'
ORDER BY member_name, granted_role;
~~~

In PostgreSQL 16+, `pg_auth_members` includes `inherit_option`, `set_option`, and `admin_option` columns to inspect each grant edge.

### Why Not Look Only at rolinherit?

In PostgreSQL 16+, `rolinherit` is not enough to determine whether **existing memberships** currently grant inheritance. You must check each edge in `pg_auth_members` as well as multi-level membership paths.

## 17. Checking Automatically Inherited Privileges

PostgreSQL provides `pg_has_role`:

~~~sql
SELECT
    pg_has_role(
        'lab378_editor',
        'lab378_reader',
        'MEMBER'
    ) AS is_reader_member,
    pg_has_role(
        'lab378_editor',
        'lab378_reader',
        'USAGE'
    ) AS can_use_reader_automatically,
    pg_has_role(
        'lab378_editor',
        'lab378_reader',
        'SET'
    ) AS can_set_reader;
~~~

In PostgreSQL 16+, `MEMBER`, `USAGE`, and `SET` have distinct meanings:

- **MEMBER**: has a membership relationship under the checked semantics.
- **USAGE**: can automatically use privileges of the granted role through an appropriate inheritance path.
- **SET**: can switch to that role via `SET ROLE` through permitted paths.

### Comparing with Writer

~~~sql
SELECT
    pg_has_role(
        'lab378_editor',
        'lab378_writer',
        'MEMBER'
    ) AS is_writer_member,
    pg_has_role(
        'lab378_editor',
        'lab378_writer',
        'USAGE'
    ) AS auto_writer_privileges,
    pg_has_role(
        'lab378_editor',
        'lab378_writer',
        'SET'
    ) AS can_set_writer;
~~~

With the lab grants, the intended results are:

| Check | Reader | Writer |
| --- | --- | --- |
| MEMBER | true | true |
| USAGE | true | false |
| SET | true | true |

**`SET` in `pg_has_role` is a check option in versions that support it**; on servers prior to PostgreSQL 16, consult the corresponding syntax/docs. Do not blindly copy PG16+ option lists to older servers.

## 18. Checking Effective Object Privileges

~~~sql
SELECT
    has_schema_privilege(
        'lab378_editor',
        'lab378',
        'USAGE'
    ) AS can_use_schema,
    has_table_privilege(
        'lab378_editor',
        'lab378.documents',
        'SELECT'
    ) AS can_read_table,
    has_table_privilege(
        'lab378_editor',
        'lab378.documents',
        'INSERT'
    ) AS can_insert_table,
    has_table_privilege(
        'lab378_editor',
        'lab378.documents',
        'UPDATE'
    ) AS can_update_table;
~~~

With the lab design:

- The editor automatically receives reader privileges (`SELECT`).
- The editor **does not automatically receive writer privileges** (`INSERT`/`UPDATE`) through the writer membership because it has `INHERIT FALSE`.
- When writer is activated via `SET ROLE`, effective privileges change.

### Interpretation Limits of has_table_privilege

`has_table_privilege` checks object ACL/privileges in the context of the selected role, but an actual query also depends on schema access, RLS, column-level grants, the active role, and other constraints.

Do not build a security UI relying solely on a single `has_table_privilege` boolean while skipping real query tests and policies.

## 19. session_user, current_user, and current_role

When a client logs in as `lab378_editor`, you can observe:

~~~sql
SELECT
    session_user,
    current_user,
    current_role;
~~~

- `session_user`: the initial/current session authorization identity under SQL rules.
- `current_user`: the identity used for most permission checks at execution time.
- `current_role`: essentially synonymous with `current_user` in PostgreSQL.

Normally right after login:

~~~text
session_user = lab378_editor
current_user = lab378_editor
current_role = lab378_editor
~~~

After `SET ROLE`, `current_user` changes while `session_user` usually remains the original login role.

### Why Does This Matter?

An audit table recording `current_user` may log the group role name `lab378_writer` after `SET ROLE`, no longer directly indicating which employee/login role performed the action.

If you want to log the session identity, you must understand `session_user` as well as the authentication/application identity layer. Never assume the two values are always the same.

## 20. SET ROLE Switches the Effective Role

Suppose you are connected as `lab378_editor` and have the `SET` option to writer:

~~~sql
SELECT session_user, current_user;

SET ROLE lab378_writer;

SELECT session_user, current_user;

RESET ROLE;

SELECT session_user, current_user;
~~~

Expected output:

| Moment | session_user | current_user |
| --- | --- | --- |
| Before SET ROLE | lab378_editor | lab378_editor |
| After SET ROLE writer | lab378_editor | lab378_writer |
| After RESET ROLE | lab378_editor | lab378_editor |

**`SET ROLE` does not ask you to enter the target role's password.** Permission is governed by membership/SET path and applicable administrative rules.

### Can You SET ROLE to a NOLOGIN Role?

Yes, when the session is authorized: `NOLOGIN` only prevents a role from acting as a direct login identity. It does not prevent an authorized session from explicitly assuming the role via `SET ROLE`.

### SET ROLE Is Not a Permanent Grant

`RESET ROLE` restores the corresponding role context. Object privileges are not copied to the login role by a single `SET ROLE`.

## 21. When You SET ROLE writer, You Do Not Automatically Keep All Editor Privileges

A common misconception:

> "I am editor, and I already inherit reader. I run `SET ROLE writer`, so I definitely have both reader and writer combined."

Do not reason that way.

`SET ROLE lab378_writer` switches `current_user` to writer; effective privileges depend on writer and **writer's** memberships. Privileges belonging to the `editor` login role are not implicitly "accumulated" onto writer merely because `session_user` is still editor.

That is why in the lab we granted writer both `SELECT` and `INSERT`/`UPDATE` so writer can run `UPDATE` statements with `WHERE`/`RETURNING`.

### Want Writer to Use Reader Privileges Through the Group Graph?

You can design it as:

~~~sql
-- Example modifying the role graph; only use if intended by policy.
GRANT lab378_reader TO lab378_writer
WITH INHERIT TRUE, SET TRUE;
~~~

Writer then has a path to reader; inherited privileges depend on the options across the entire path.

**Creating nested role graphs must be documented explicitly.** Do not add memberships ad hoc to "fix a permission error" and then forget to review the new authorization paths.

## 22. Practicing Read-Only Access as Reporter

Two ways to test:

1. **Best:** actually log in as `lab378_reporter` after configuring authentication.
2. **In the lab:** use an admin/superuser session permitted to run `SET ROLE lab378_reporter` to simulate effective privileges.

~~~sql
SET ROLE lab378_reporter;

SELECT
    session_user,
    current_user;

SELECT
    doc_id,
    title,
    visibility
FROM lab378.documents
ORDER BY doc_id;

RESET ROLE;
~~~

In the lab, the `SELECT` query succeeds because:

- Reporter has reader membership with `INHERIT TRUE`.
- Reader has schema `USAGE`.
- Reader has table `SELECT`.

### Negative Test: Reporter Cannot INSERT

Run as reporter in a separate statement:

~~~sql
-- INTENTIONALLY TRIGGERS permission denied.
SET ROLE lab378_reporter;

INSERT INTO lab378.documents (
    doc_id, title, body
)
VALUES (
    99, 'Not allowed', 'Should be rejected'
);

RESET ROLE;
~~~

If the `INSERT` errors in a normal implicit transaction, the client can proceed to `RESET`. If you are inside an **explicit `BEGIN; ...`**, the transaction enters an aborted state and must be rolled back before resetting/continuing. Do not blindly run an entire negative-test script sequentially without managing transaction state.

## 23. Practicing Automatic Read for Editor While Writes Require SET ROLE

Test `SELECT` in the editor context:

~~~sql
SET ROLE lab378_editor;

SELECT doc_id, title
FROM lab378.documents
ORDER BY doc_id;

RESET ROLE;
~~~

The `SELECT` succeeds thanks to the inherited reader membership.

### Negative Test: Direct Write as Editor

~~~sql
-- INTENTIONALLY TRIGGERS permission denied:
SET ROLE lab378_editor;

UPDATE lab378.documents
SET body = 'Edited outside writer role'
WHERE doc_id = 1;

RESET ROLE;
~~~

In the PostgreSQL 16+ lab design, editor has `INHERIT FALSE` on writer, so `UPDATE` is not automatically granted via the writer membership. If another privilege path (a direct grant, `PUBLIC`, or another group) grants `UPDATE`, the negative test may not fail—which is precisely why you must **verify all effective privilege paths**, not just the role grant you just created.

### Positive Test: SET ROLE writer

~~~sql
BEGIN;

-- Run from an actual editor session, or an admin session
-- permitted to simulate the corresponding SET ROLE steps.
SET ROLE lab378_writer;

UPDATE lab378.documents
SET body = 'Edited using explicit writer role'
WHERE doc_id = 1
RETURNING doc_id, title, body;

RESET ROLE;

ROLLBACK;
~~~

`ROLLBACK` restores the lab data, without invalidating the conclusion that writer had `UPDATE` permission while active.

### Connection Pool Note

If a connection is reused and `RESET ROLE` is forgotten, the next request can execute with the previous request's effective role. This is a severe security bug in connection pooling.

**There must be a session-state reset protocol**, ideally managed by the pool/framework and thoroughly tested. Do not rely on developer discipline to remember `RESET` on every exception path.

## 24. INHERIT TRUE Uses Object Privileges Automatically, Not LOGIN

Suppose `NOLOGIN` role reader has `SELECT` and editor inherits reader. Editor can read the table because **object privileges** are inherited.

That **does not** turn reader into a login account; nor does it automatically give editor `CREATEDB`/`SUPERUSER` from another role. Role attributes follow separate rules.

### Illustrative Distinction

~~~sql
-- For illustration only, DO NOT run in the least-privilege lab:
CREATE ROLE privileged_role NOLOGIN CREATEDB;
GRANT privileged_role TO lab378_reporter;
~~~

Do not conclude that reporter automatically gains database-creation rights merely from membership; nor should you grant membership in a role with powerful attributes in a real system without reviewing `SET ROLE`/`ADMIN OPTION` capabilities.

**Role membership is a powerful delegation capability**, especially when the target holds DDL rights or special attributes.

## 25. Multi-Level and Multi-Path Membership

Example graph:

~~~text
analyst
  | INHERIT TRUE
  v
team_reader
  | INHERIT TRUE
  v
app_reader
  | SELECT
  v
app.documents
~~~

If **every edge along the inheritance path** allows inheritance, `analyst` can use the reader privileges according to the applicable semantics.

However, if one edge has `INHERIT FALSE`, you cannot look only at the first edge and conclude that the entire path inherits automatically.

### Multiple Distinct Paths

~~~text
analyst -> group_A -> app_reader
analyst -> group_B -> app_reader
~~~

If one path is blocked while the other path still allows inheritance, the effective privilege may still exist. PostgreSQL evaluates permissions across **effective grant paths**, not just a single row in the catalog.

Therefore, running `REVOKE` on one grant or changing one edge to `INHERIT FALSE` does not necessarily remove the privilege if the role still has another path.

## 26. The ADMIN Option Grants Membership Management Rights

PG16+ example:

~~~sql
GRANT lab378_reader TO lab378_editor
WITH ADMIN TRUE;
~~~

A member holding a valid admin option may grant/manage membership of that role within the bounds of current PostgreSQL rules.

### ADMIN Does Not Mean SELECT

Having the `ADMIN` option for `lab378_reader` does not directly mean editor can read `lab378.documents` if there is no suitable inheritance or `SET` path.

### Why Is ADMIN Sensitive?

Someone who can grant membership onward can expand the set of recipients holding privileges. If the target role holds sensitive privileges, the admin option can become an authorization escalation path.

Principles:

- App runtime does not need the `ADMIN` option.
- Only appropriate admins/deployers should manage membership.
- Review who holds `CREATEROLE` and `ADMIN` options.
- When upgrading major versions, check membership management semantics because PostgreSQL 16 significantly changed role administration rules.

Do not create lots of roles with `ADMIN TRUE` just for deployment convenience.

## 27. ALTER ROLE INHERIT/NOINHERIT Does Not Modify All Old Grants (PG16+)

Suppose editor already has:

~~~sql
GRANT lab378_reader TO lab378_editor
WITH INHERIT TRUE, SET TRUE;
~~~

Then you run:

~~~sql
ALTER ROLE lab378_editor NOINHERIT;
~~~

In PostgreSQL 16+, this **must not be assumed to retroactively modify the existing reader -> editor edge**. The attribute on the role affects the default value when creating new membership grants, while existing edges keep their granted options until explicitly altered.

### How to Verify?

~~~sql
SELECT
    m.inherit_option,
    m.set_option,
    m.admin_option
FROM pg_auth_members AS m
JOIN pg_roles AS granted
    ON granted.oid = m.roleid
JOIN pg_roles AS member
    ON member.oid = m.member
WHERE granted.rolname = 'lab378_reader'
  AND member.rolname = 'lab378_editor';
~~~

Do not rely solely on `pg_roles.rolinherit` to assert a role's current inherited privileges.

**This is an important version difference**; older PostgreSQL tutorials may describe `INHERIT` in ways that do not fully reflect PG16+ behavior.

## 28. Revoking Membership Differs from Revoking an Object Privilege

### Revoking Role Membership

~~~sql
REVOKE lab378_writer
FROM lab378_editor;
~~~

Editor no longer has the writer membership path just revoked, unless other grant paths exist through the role graph.

### Revoking a Table Permission

~~~sql
REVOKE UPDATE
ON TABLE lab378.documents
FROM lab378_writer;
~~~

Writer no longer has `UPDATE` **via that grant**, but may still receive `UPDATE` from another role, `PUBLIC`, ownership, or another grant.

### Comparison

| Statement | What changes |
| --- | --- |
| `REVOKE lab378_writer FROM lab378_editor` | Editor's membership in writer |
| `REVOKE UPDATE ON ... FROM lab378_writer` | Writer's `UPDATE` privilege on the object |
| `REVOKE SELECT ON ... FROM PUBLIC` | A privilege granted to the `PUBLIC` pseudo-role |
| `ALTER ROLE ... NOLOGIN` | The role's ability to log in |

In the SQL privilege model, **`REVOKE` is not an absolute-priority "DENY"**. It removes the specified grant; access may still arrive via another path.

## 29. PUBLIC Is a Pseudo-Role Applying to Every Role

`PUBLIC` is not an ordinary role that you create, drop, or manage membership for like `app_reader`. It represents **all roles** in the context of object privileges.

For example:

~~~sql
GRANT SELECT
ON TABLE lab378.documents
TO PUBLIC;
~~~

If executed, any role satisfying schema/connect and other policy checks can obtain `SELECT` through `PUBLIC`.

**This is an example to avoid for sensitive data**, not a default recommendation.

### REVOKE FROM PUBLIC

~~~sql
REVOKE SELECT
ON TABLE lab378.documents
FROM PUBLIC;
~~~

Revokes that direct `PUBLIC` grant, though it does not necessarily remove other direct grants or membership privileges.

### PUBLIC Defaults Vary by Object and Version

For example:

- Some database privileges are typically granted to `PUBLIC` by default when a database is created.
- The `EXECUTE` privilege on functions has defaults that should be reviewed.
- Privileges on schema `public` vary by PostgreSQL major version and how the database was created or upgraded.

Do not apply a blanket rule like "every PostgreSQL gives `PUBLIC` `CREATE` on the `public` schema" to all versions. PostgreSQL 15 changed the relevant defaults; always inspect the actual privileges.

## 30. The public Schema and search_path Are a Security Boundary

Many sessions default to a `search_path` like:

~~~text
"$user", public
~~~

Actual configurations may differ.

If a schema on `search_path` grants `CREATE` to untrusted roles, they can create functions, operators, or objects with names that interfere with unqualified name resolution in poorly secured SQL statements.

### Principles

- Do not give application roles arbitrary `CREATE` privileges on shared schemas.
- Schema-qualify critical objects in migrations and security-sensitive SQL.
- When using `SECURITY DEFINER`, set a safe `search_path` per PostgreSQL documentation.
- Check the schema owner and `CREATE` privileges held by `PUBLIC` or other roles.
- Do not confuse `USAGE` with `CREATE`.

Commands to inspect `search_path`:

~~~sql
SHOW search_path;

SELECT current_schemas(true);
~~~

Do not alter `search_path` haphazardly just to "silence `relation does not exist` errors"; check privileges and object names properly.

## 31. Granting SELECT Does Not Mean All Tables in a Schema Are Readable

~~~sql
GRANT USAGE ON SCHEMA lab378 TO lab378_reader;
~~~

does not grant `SELECT` on any individual table.

~~~sql
GRANT SELECT
ON ALL TABLES IN SCHEMA lab378
TO lab378_reader;
~~~

grants `SELECT` on **applicable existing relations** in the schema at the time the command runs.

**It does not automatically apply to tables created in the future.** For that, you need `ALTER DEFAULT PRIVILEGES` targeting the role creating the objects, covered later.

### Be Careful with ALL TABLES

This command may include relations that should not be readable, such as audit tables, tokens, or confidential content. In production, many organizations grant privileges on specific tables/views, or grant `SELECT` only on views designed for reporting.

Least privilege does not mean "`GRANT SELECT ON ALL TABLES`" is safe in every schema.

## 32. Sequence Privileges Are Separate from Table Privileges

When a table uses a sequence—such as `serial` or `nextval(...)`—an `INSERT` may need privileges on the sequence if the statement actually invokes `nextval` in a way that requires them.

For example:

~~~sql
GRANT USAGE
ON SEQUENCE lab378.some_sequence
TO lab378_writer;
~~~

This snippet is **illustrative**; only run it if `lab378.some_sequence` exists.

Distinguish between:

- `GRANT INSERT ON table`: permission to insert rows.
- `GRANT USAGE ON sequence`: permission to use certain sequence operations.
- `GRANT SELECT ON sequence`: access to appropriate sequence read functions.
- Identity columns have distinct semantics compared to manually calling a sequence, depending on version and operation type.

**Do not grant `ALL ON ALL SEQUENCES` just because an `INSERT` failed** before identifying which sequence is actually needed and which operation the caller is invoking.

## 33. Column-Level Privileges and RETURNING

Instead of the whole table, you can grant:

~~~sql
GRANT SELECT (doc_id, title)
ON TABLE lab378.documents
TO lab378_reader;
~~~

This is an example of column-level `SELECT`.

### When a Query Requests an Ungranted Column

~~~sql
SELECT doc_id, title, body
FROM lab378.documents;
~~~

If reader is only permitted to read `doc_id` and `title`, the `body` column requires the corresponding privilege; the query may fail with permission denied.

### Column-Level UPDATE

~~~sql
GRANT UPDATE (title, body)
ON TABLE lab378.documents
TO lab378_writer;
~~~

`UPDATE` privileges on columns do not automatically guarantee `SELECT` privileges on columns referenced in `WHERE`, expressions, or `RETURNING`. Design ACLs to match the actual SQL statements.

### Limitations of Column Grants

- They do not replace RLS when per-tenant row filtering is required.
- They do not automatically hide fields exposed differently via views or functions.
- They require maintenance whenever sensitive columns are added to the schema.

## 34. Ownership Carries Special Rights

A table owner generally has privileges to manage the object's structure and ACL—such as `ALTER TABLE`/`DROP TABLE` under PostgreSQL rules—not merely simple `SELECT`/`UPDATE`.

**Object ownership differs from a `GRANT SELECT`.**

For example, if a production service only needs to `UPDATE` a status, making the service account the owner of the table means a severe SQL bug could allow DDL changes, ACL alterations, or data modifications far beyond what is needed.

### Special Owner Rights Are Not Simply Inherited Like SELECT

A member of an owner role may need to run `SET ROLE` to the owner to perform certain owner-only operations, depending on the operation and membership.

Hence a common pattern:

- `app_owner NOLOGIN` owns schemas/tables.
- `app_runtime LOGIN` only has DML grants via privilege groups.
- `app_deployer LOGIN` has `SET ROLE app_owner` within a controlled scope for migrations.

Do not use `GRANT ALL PRIVILEGES ON TABLE ...` trying to grant `DROP TABLE` to an app; `ALL PRIVILEGES` on a table is not equivalent to ownership/DDL authority.

## 35. Extended Lab: Owner Role and Deployer

These examples are for a PG16+ practice environment with appropriate admin privileges.

~~~sql
CREATE ROLE lab378_owner NOLOGIN;
CREATE ROLE lab378_deployer LOGIN;

GRANT CREATE ON SCHEMA lab378 TO lab378_owner;

GRANT lab378_owner TO lab378_deployer
WITH INHERIT FALSE, SET TRUE, ADMIN FALSE;
~~~

After logging in as `lab378_deployer` or using a session permitted to simulate it:

~~~sql
SET ROLE lab378_owner;

CREATE TABLE lab378.owner_example (
    example_id bigint PRIMARY KEY,
    description text NOT NULL
);

RESET ROLE;
~~~

The table `lab378.owner_example` is created in the context of the effective role `lab378_owner`, so the object's owner is `lab378_owner`.

### Key Takeaway

`lab378_owner` being `NOLOGIN` does not prevent it from owning tables. The deployer can `SET ROLE` to owner because of the membership `SET` option, **not because the deployer is a superuser**.

In production, tightly control `SET`/`ADMIN` paths to the owner; do not allow app runtime to switch to owner if it only needs DML.

## 36. ALTER DEFAULT PRIVILEGES for Future Objects

A statement like:

~~~sql
GRANT SELECT ON ALL TABLES IN SCHEMA lab378 TO lab378_reader;
~~~

only affects **applicable existing tables**. For new tables created by the owner, you can define default privileges:

~~~sql
-- Run as lab378_owner or a role permitted to manage
-- default privileges for lab378_owner in your version.
ALTER DEFAULT PRIVILEGES
FOR ROLE lab378_owner
IN SCHEMA lab378
GRANT SELECT ON TABLES TO lab378_reader;
~~~

Afterward, when `lab378_owner` creates a new table in schema `lab378`, the corresponding default grant is applied.

### Important Pitfall

**Default privileges are selected based on the role creating the object.** If a migration runs with `current_user = lab378_deployer` without running `SET ROLE lab378_owner`, default privileges set `FOR ROLE lab378_owner` **do not automatically apply merely because deployer is a member of owner**.

Explicit workflow example:

~~~sql
SET ROLE lab378_owner;

CREATE TABLE lab378.future_reports (
    report_id bigint PRIMARY KEY,
    report_title text NOT NULL
);

RESET ROLE;
~~~

With default privileges configured, reader can receive the new `SELECT` privilege according to the rule.

### Do Not Confuse Scope

Default privileges can have global or per-schema scope depending on the command, and revoking in one scope does not necessarily undo a grant in another scope. When using `ALTER DEFAULT PRIVILEGES`, inspect the catalog/`psql` and verify actual privileges on newly created tables.

**Do not use default privileges to accidentally expose all confidential tables to a reader.**

## 37. Function Permissions Differ from Table Permissions

A function can execute database logic in a security context different from direct table access.

PostgreSQL often has privilege defaults around `EXECUTE` on functions; depending on creation and default privileges, `PUBLIC` may hold `EXECUTE` unless revoked.

Conceptual example:

~~~sql
REVOKE EXECUTE
ON FUNCTION lab378.some_function(integer)
FROM PUBLIC;

GRANT EXECUTE
ON FUNCTION lab378.some_function(integer)
TO lab378_reader;
~~~

Only execute this if a function with that exact signature exists.

### Why Does This Matter?

A user might lack `UPDATE` privileges on a table, yet have `EXECUTE` on a `SECURITY DEFINER` function designed to modify that table. That can be an **intentional** database API—or a vulnerability if the function fails to validate authorization and inputs.

Never inspect only table ACLs and declare that a user has no way to modify data.

## 38. SECURITY INVOKER and SECURITY DEFINER

**SECURITY INVOKER** (the default for many functions) uses the caller's privileges according to function semantics.

**SECURITY DEFINER** executes with the privileges of the function's owner in the applicable execution context.

Conceptual example:

~~~sql
CREATE FUNCTION some_schema.safe_operation(p_id bigint)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, some_schema
AS $fn$
BEGIN
    -- Only carefully reviewed operations, with schema-qualified objects.
    -- Validate parameters, caller identity, and appropriate business permissions.
    NULL;
END;
$fn$;
~~~

This snippet is **illustrative**; do not run it directly without setting up the full schema, function ownership, and security policy.

### Two Risks

1. **Elevated privileges:** the caller can affect data using the function owner's privileges.
2. **`search_path` injection:** if the function resolves object names from untrusted schemas, a caller can exploit created objects to hijack logic.

Only grant `EXECUTE` on reviewed functions, set a safe `search_path`, and avoid improperly quoted dynamic SQL. Never treat `SECURITY DEFINER` as a shortcut to "bypass permission denied" without threat modeling.

### SET ROLE Inside SECURITY DEFINER

`SET ROLE` has restrictions inside a security-definer context; do not design `SECURITY DEFINER` functions as a place for callers to arbitrarily execute `SET ROLE` to bypass controls. Use an explicit permission model rather than relying on complex session-state interactions.

## 39. Row-Level Security (RLS) Is Not Replaced by Role Membership

Object privileges answer the question:

> Is this role allowed to perform `SELECT`/`UPDATE` on the table in general?

RLS answers an additional question:

> Within that table, **which rows** is the role allowed to read or modify?

For instance, a multi-tenant table containing `tenant_id`. A role granted `SELECT` may still see only a subset of rows under an RLS policy.

### Conditions to Watch

- RLS is enabled on the table.
- `USING`/`WITH CHECK` policies match `SELECT`/`UPDATE`/`INSERT`.
- The table owner may bypass RLS by default unless `FORCE ROW LEVEL SECURITY` is used appropriately.
- Superusers and roles with `BYPASSRLS` bypass RLS according to system semantics.
- Running `SET ROLE` to another role changes `current_user` and affects policy matching and effective privileges.
- Membership does not turn a regular role into `BYPASSRLS` merely because it was granted a powerful role.

### Warning on Tenant Session Variables

Some systems use `current_setting('app.tenant_id')` in RLS policies. If direct database users can arbitrarily run `SET app.tenant_id`, you must prove that this mechanism does not allow tenant spoofing under your threat model; a session variable is not a trusted identity source on its own.

**Role ACLs and RLS should be two distinct layers serving different purposes**, not replacements for one another.

## 40. Default Roles and System Roles

PostgreSQL includes several predefined roles for monitoring, reading statistics, and administering specific features, named `pg_*`. Their exact privileges and semantics can vary across versions.

Do not grant an application role membership in a predefined role just because its name sounds "read-only." Some predefined roles can expose data or behaviors beyond what the service needs.

Example catalog check for roles:

~~~sql
SELECT
    rolname,
    rolcanlogin,
    rolsuper
FROM pg_roles
WHERE rolname LIKE 'pg\_%' ESCAPE '\'
ORDER BY rolname;
~~~

If you need to use a predefined role, read the official documentation **for your exact major version**, identify its actual privileges, and evaluate the impact on RLS, data confidentiality, or server-wide monitoring.

### SUPERUSER Is the Major Exception

A superuser is trusted to administer the cluster and can bypass many normal permission checks. Use it only for genuinely required administrative tasks and isolate its credentials.

## 41. CREATEROLE Is Not a "Completely Safe Admin"

`CREATEROLE` allows managing roles within PostgreSQL's rule boundaries; specific capabilities changed significantly across versions, especially in PostgreSQL 16.

A role with `CREATEROLE` can affect memberships, role attributes, and delegation paths within current limits. This is a sensitive privilege that should not be granted to application runtime.

### Principles

- Manage roles via reviewed IaC/migrations.
- Separate admin roles from application login roles.
- Monitor membership grants that include the `ADMIN` option.
- Do not rely on outdated documentation to determine exactly what `CREATEROLE` can or cannot do in a newer version.
- Require security reviewer sign-off before creating highly privileged roles.

## 42. Database Privileges: CONNECT, CREATE, and TEMPORARY

A database has specific privilege types:

- `CONNECT`: allows connecting to the database.
- `CREATE`: allows creating schemas or certain database-level objects according to semantics.
- `TEMPORARY`/`TEMP`: allows creating temporary tables.

Illustrative example with a lab database named `shop_training`:

~~~sql
-- Only use if database shop_training actually exists.
REVOKE CONNECT ON DATABASE shop_training FROM PUBLIC;

GRANT CONNECT ON DATABASE shop_training
TO lab378_reporter, lab378_editor;

GRANT TEMPORARY ON DATABASE shop_training
TO lab378_editor;
~~~

Verify production policy before revoking `CONNECT` from `PUBLIC`, as doing so can disrupt many clients.

### Do Not Confuse CONNECT and LOGIN

- `LOGIN` is a role attribute.
- `CONNECT` is a database object privilege.
- Authentication via `pg_hba`/password/TLS is a separate step.

A `LOGIN` role without `CONNECT` on the target database can be rejected. A `NOLOGIN` role with `CONNECT` cannot log in directly.

## 43. Default Schema Privileges and Versions

Starting in PostgreSQL 15, new databases changed default ownership/`CREATE` privileges on the `public` schema compared to many historical installations.

Do not teach:

> "Every PostgreSQL user always has `CREATE` on the `public` schema."

That is false across many modern versions, installations, and hardened systems.

### Check Instead of Guessing

~~~sql
SELECT
    nspname,
    nspowner::regrole AS schema_owner,
    nspacl
FROM pg_namespace
WHERE nspname = 'public';
~~~

And for a specific role:

~~~sql
SELECT
    has_schema_privilege(
        'lab378_editor',
        'public',
        'USAGE'
    ) AS may_use_public,
    has_schema_privilege(
        'lab378_editor',
        'public',
        'CREATE'
    ) AS may_create_in_public;
~~~

Rely only on results from the actual cluster/database and a reviewed security policy.

## 44. \du and \dp in psql

When using `psql`, several meta-commands are very handy:

~~~text
\du
\du+ lab378_editor
\dn+ lab378
\dp lab378.documents
\ddp
~~~

Meanings:

| psql command | Purpose |
| --- | --- |
| `\du` | List roles and some attributes/memberships |
| `\du+` | More detailed role information |
| `\dn+` | Schemas and associated privileges |
| `\dp` / `\z` | Object privileges |
| `\ddp` | Default privileges |

Commands starting with `\` **are not SQL statements**; they are interpreted by the `psql` client. Do not run them directly through a JDBC `PreparedStatement`.

### When Are Catalog Queries Better?

When you need to:

- Filter many roles by prefix.
- Compare PG16+ membership options.
- Export privilege data for review.
- Query effective privileges of a specific role.

In those cases, querying `pg_roles`, `pg_auth_members`, and privilege functions is appropriate.

## 45. Inspecting the Privilege Graph Is Not Just Looking at ACLs

Suppose a table ACL has `GRANT SELECT TO lab378_reader`. An editor account can read via membership, yet has no direct `GRANT SELECT ... TO lab378_editor` entry.

Therefore:

- `pg_class.relacl`/`\dp` shows object grant ACLs.
- `pg_auth_members` shows membership edges.
- `pg_has_role` shows role membership/usage relationships.
- `has_table_privilege` shows effective privileges under the corresponding check.
- An actual `SELECT` query under the application role confirms behavior including schema and RLS effects.

**Auditing permissions requires combining information across multiple layers, not just grepping for a single `GRANT` line.**

## 46. Revocation Does Not Always Block Access Immediately as Expected

Scenarios worth testing:

1. A role has direct `SELECT` and inherited `SELECT` -> revoking one path leaves the other intact.
2. `PUBLIC` has `SELECT` -> revoking from reader does not make the table private.
3. A role holds membership through two groups -> blocking one edge leaves the other edge active.
4. A session has run `SET ROLE` to another role -> effective privileges must be checked under `current_user`.
5. A `SECURITY DEFINER` function can execute an operation the caller cannot run directly.
6. An object owner has special rights beyond normal object ACLs.
7. RLS may still filter rows even when table `SELECT` is granted.

### Privilege-Reduction Workflow

- Identify all direct and indirect paths.
- Design the target privilege state.
- Apply `REVOKE`/`GRANT`/membership option changes appropriate to your version.
- Check `pg_has_role` and `has_*_privilege`.
- Log in or simulate as the application role and run real queries.
- Check connection pools/active sessions and any privilege refresh mechanism if needed.
- Monitor permission errors after rollout.

Never promise that a single `REVOKE` statement always blocks every operation immediately in every session or context.

## 47. Roles and Auditing: session_user Is Not the Web End-User Identity

In a web application, hundreds of thousands of users may share the same database login `app_api`. PostgreSQL sees `session_user = app_api` and does not automatically know which web user sent a given request.

For accurate auditing, a system may need:

- An app-layer authenticated user ID.
- A signed/validated request identity from a trusted service.
- Transaction context metadata passed through a tamper-resistant mechanism.
- Audit events recording the business actor ID, DB role, and transaction/request IDs separately.
- Restricted permissions on audit tables.

### When Using SET ROLE

`current_user` can be a `NOLOGIN` group role after `SET ROLE`; `session_user` remains the DB login. Distinguish these two fields when writing audit logs.

Do not use `current_user` alone as forensic proof that a specific human performed an action.

## 48. SET ROLE and Connection Pooling

Connection pools hold long-lived sessions. If a request runs:

~~~sql
SET ROLE lab378_writer;
~~~

then hits an exception and forgets:

~~~sql
RESET ROLE;
~~~

the next request borrowing that connection may execute with writer privileges.

### Mitigations

1. Use a pool with a proven and tested session-state reset mechanism.
2. Use explicit `try/finally`/transaction boundaries when switching effective roles.
3. Never let user input arbitrarily determine the role name in `SET ROLE`.
4. If using `SET LOCAL ROLE` (when appropriate for the version/context), understand transaction scope thoroughly and test both rollback and commit.
5. Never use a production superuser connection as the runtime pool.
6. Assert `session_user/current_user` in verification tests.

**SQL role switching is a security-critical session state**, not merely a convenience variable.

## 49. Dangerous Mistakes When Creating Roles

### 49.1. Giving the App User SUPERUSER

Just to "eliminate permission denied," while breaking the principle of least privilege.

### 49.2. Letting the App User Own Every Table

The application gets unnecessary DDL/ownership rights; separate owner from runtime.

### 49.3. Using One LOGIN Role as a Privilege Group for All Services

Expands blast radius and complicates credential rotation. `NOLOGIN` group roles separate privilege bundles from credentials.

### 49.4. Assuming a NOLOGIN Role Cannot Be Misused

A member with a valid `SET` option can assume a `NOLOGIN` role.

### 49.5. Assuming Role Members Automatically Get All Attributes

`LOGIN`/`SUPERUSER`/`CREATEDB`/`BYPASSRLS` are not inherited like `SELECT`.

### 49.6. Assuming Membership Always Grants Privileges Automatically

PG16+ has `INHERIT FALSE` and `SET FALSE`; membership does not equal automatic privilege usage.

### 49.7. Assuming ALTER ROLE NOINHERIT Retroactively Fixes All Old Grants

Not true in PG16+ with per-membership `inherit_option`.

### 49.8. Confusing ADMIN with SET or INHERIT

They are three independent options with distinct purposes.

### 49.9. Using GRANT ALL PRIVILEGES as a Substitute for Ownership

Table privileges do not grant owner-level `DROP`/`ALTER`.

### 49.10. Granting SELECT Without Schema USAGE

Queries can be rejected during namespace resolution.

### 49.11. Forgetting Database CONNECT

`LOGIN` does not guarantee connection to a database where `PUBLIC` `CONNECT` has been revoked.

### 49.12. Forgetting Sequence Privileges

Some `INSERT` statements using sequences can fail with permission denied.

### 49.13. Granting ALL TABLES IN SCHEMA When Secret Tables Exist

Overly broad read access—especially for audit logs, tokens, and PII.

### 49.14. Assuming ALL TABLES Grants Apply to Future Tables

You must configure default privileges for the role creating objects.

### 49.15. Setting Default Privileges FOR ROLE on the Wrong Owner

Migrations creating objects under a different role will not pick up those default grants.

### 49.16. Treating REVOKE as an Absolute DENY

Privileges may still remain via `PUBLIC`, direct grants, another membership path, or ownership.

### 49.17. Ignoring pg_auth_members When Debugging Permissions

An effective privilege may come from multiple nested role layers.

### 49.18. Using SET ROLE Without Resetting the Connection

Leaks privileges to subsequent requests in a connection pool.

### 49.19. Using SECURITY DEFINER Without Locking search_path

Increases the risk of object-name hijacking and privilege escalation.

### 49.20. Assuming RLS Automatically Applies to Everyone Including Superuser/Owner

Bypass rules and `FORCE RLS` semantics must be checked.

### 49.21. Storing Plaintext Passwords in Migrations and Logs

Exposes credentials in git, CI, shell history, and error logs.

### 49.22. Failing to Distinguish session_user from current_user

Records the wrong identity in audits due to effective-role switching.

### 49.23. Using Old PostgreSQL Docs for PG16+ Options

Leads to misunderstanding inheritance/`SET`/`ADMIN` behavior.

### 49.24. Forgetting to Test with the Actual Role

A superuser can read everything even when app role config is broken; always test with the corresponding non-superuser role.

## 50. Production Privilege Design Guidelines

A typical approach includes these steps:

1. Create a `NOLOGIN` owner role for schemas and tables.
2. Create `NOLOGIN` groups aligned with actual operations: reader, writer, reporting.
3. Create separate login roles per service or client type.
4. Grant schema `USAGE` and exact object privileges.
5. Grant memberships with explicit `INHERIT`/`SET`/`ADMIN` options appropriate to your version.
6. Allow only the deployer to `SET ROLE` to owner inside migration pipelines.
7. Do not grant app runtime `CREATE`/`ALTER`/`DROP` unless genuinely needed.
8. Configure `CONNECT`/`TEMP`/database privileges according to policy.
9. Audit `PUBLIC` and default privileges.
10. Enable RLS when row-level isolation is needed and test bypass conditions.
11. Restrict `SECURITY DEFINER` and `EXECUTE` privileges.
12. Manage passwords, secrets, TLS, and `pg_hba` outside SQL grants.
13. Test negative cases using actual login roles.
14. Inspect catalogs and store changes as migrations/IaC.
15. Revoke legacy privileges and verify no alternative paths remain.
16. Verify that connection pools do not retain old effective roles.

### Distinguishing "Technical Privileges" from "Business Authorization"

A SQL role having `UPDATE` on a table does not by itself know whether a user is authorized to edit **that specific order**. You still need application authorization—and potentially RLS or secured functions—to enforce business policy.

## 51. Reader/Writer Group Permission Scenarios

| Scenario | Login role | Membership | Behavior |
| --- | --- | --- | --- |
| Reporting reads documents | reporter | reader INHERIT TRUE | `SELECT` allowed |
| Reporting INSERTS documents | reporter | reader | `INSERT` blocked unless another grant exists |
| Editor reads normally | editor | reader INHERIT TRUE | `SELECT` allowed |
| Editor UPDATES before SET ROLE | editor | writer INHERIT FALSE | `UPDATE` blocked unless another grant exists |
| Editor SET ROLE writer then UPDATES | editor | writer SET TRUE | `UPDATE` allowed under writer privileges |
| Editor RESET ROLE | editor | original role | Returns to editor's effective privileges |
| Deployer SET ROLE owner | deployer | owner SET TRUE | DDL under owner privileges |
| Runtime SELECTS another table | runtime | not yet granted | Only allowed if another path/owner/`PUBLIC` permits |

This table assumes the exact lab grants, **with no unexpected privileges from `PUBLIC` or other roles**. Actual cluster results may differ if grant paths exist outside the lab.

## 52. Practice Exercises with Answers

These exercises use `lab378` and `lab378_*` created earlier. Statements intended to fail should be run separately, restoring transaction state before continuing. Any example that modifies data should use `BEGIN ... ROLLBACK` when merely testing.

### Exercise 1. What is a role?

**Answer:** A PostgreSQL identity used to receive privileges, own objects, and be a member of other roles. A role may or may not have `LOGIN`.

### Exercise 2. How does LOGIN differ from CONNECT?

**Answer:** `LOGIN` is a role attribute allowing the role to act as a connection identity; `CONNECT` is a privilege on a database. An appropriate authentication policy is also required.

### Exercise 3. Can a NOLOGIN role own a table?

**Answer:** Yes. A `NOLOGIN` role can own objects; it simply cannot log in directly.

### Exercise 4. Create a read-only group

~~~sql
CREATE ROLE example_reader NOLOGIN;
~~~

**Answer:** This is initially an empty role; to read tables, you must grant appropriate schema/table privileges or memberships.

### Exercise 5. Grant SELECT on the lab table

~~~sql
GRANT SELECT
ON TABLE lab378.documents
TO lab378_reader;
~~~

**Answer:** Reader receives table `SELECT`; schema `USAGE` and any other conditions/privileges are still needed to run queries.

### Exercise 6. Grant schema USAGE

~~~sql
GRANT USAGE
ON SCHEMA lab378
TO lab378_reader;
~~~

**Answer:** Allows using the schema namespace; does not grant `CREATE` and does not automatically grant `SELECT` on all tables.

### Exercise 7. What is granting membership?

~~~sql
GRANT lab378_reader TO lab378_reporter;
~~~

**Answer:** Reporter becomes a member of reader under your version's grant options/defaults; this is not a direct table grant.

### Exercise 8. PG16+: Writer not auto-inherited, but SET allowed

~~~sql
GRANT lab378_writer TO lab378_editor
WITH INHERIT FALSE, SET TRUE;
~~~

**Answer:** Editor does not automatically use writer object privileges through that edge, but can run `SET ROLE` to writer if an appropriate permission path exists.

### Exercise 9. Are INHERIT and SET the same?

**Answer:** No. `INHERIT` controls automatic usage of object privileges; `SET` controls the ability to switch `current_role` along that membership path.

### Exercise 10. What is the ADMIN option?

**Answer:** The right to administer/re-grant membership of the granted role under PostgreSQL rules; it does not automatically grant `SELECT`/`UPDATE` on tables.

### Exercise 11. Which role attributes are not inherited like SELECT?

**Answer:** Special attributes such as `SUPERUSER`, `CREATEDB`, `CREATEROLE`, `LOGIN`, `REPLICATION`, and `BYPASSRLS` are not automatically added to member roles via inheritance like table privileges.

### Exercise 12. Where do PostgreSQL roles exist?

**Answer:** At the cluster level. Object grants on tables and schemas are tied to objects in their respective databases.

### Exercise 13. What is current_user after SET ROLE?

~~~sql
SET ROLE lab378_writer;

SELECT session_user, current_user;

RESET ROLE;
~~~

**Answer:** `current_user` switches to writer; `session_user` typically remains the original login role.

### Exercise 14. Can you SET ROLE to a NOLOGIN writer?

**Answer:** Yes, if the session has `SET` permission to that role. `NOLOGIN` only prevents direct login.

### Exercise 15. Does editor automatically use writer privileges if INHERIT FALSE?

**Answer:** Not through that edge. However, another grant path could exist, so you must check overall effective privileges.

### Exercise 16. Reading membership options

~~~sql
SELECT
    r.rolname AS granted_role,
    m.inherit_option,
    m.set_option,
    m.admin_option
FROM pg_auth_members AS m
JOIN pg_roles AS r
    ON r.oid = m.roleid
JOIN pg_roles AS u
    ON u.oid = m.member
WHERE u.rolname = 'lab378_editor';
~~~

**Answer:** Used on PostgreSQL 16+ to inspect each membership edge of editor.

### Exercise 17. How does pg_has_role MEMBER differ from USAGE?

**Answer:** `MEMBER` checks the membership relationship, while `USAGE` checks the ability to automatically use role privileges through valid inheritance paths.

### Exercise 18. What does pg_has_role SET check?

**Answer:** On PostgreSQL versions that support it, it checks the ability to `SET ROLE` along valid membership paths.

### Exercise 19. Check whether editor has SELECT

~~~sql
SELECT has_table_privilege(
    'lab378_editor',
    'lab378.documents',
    'SELECT'
);
~~~

**Answer:** In the lab this is typically `true` via reader `INHERIT TRUE`, unless other grants/paths were modified.

### Exercise 20. Check whether editor automatically has UPDATE

~~~sql
SELECT has_table_privilege(
    'lab378_editor',
    'lab378.documents',
    'UPDATE'
);
~~~

**Answer:** In the lab this is typically `false` because writer has `INHERIT FALSE` and there is no other `UPDATE` path.

### Exercise 21. Why might revoking one grant not remove the privilege?

**Answer:** The user may still hold a direct grant, a `PUBLIC` privilege, membership via another role, or owner special rights.

### Exercise 22. Is PUBLIC a regular role?

**Answer:** No. It is a pseudo-role representing all roles when granting object privileges, not a regular group role you create and manage.

### Exercise 23. A role has SELECT, but no schema USAGE?

**Answer:** Accessing the relation via the schema can be rejected; schema `USAGE` or an appropriate permitted context is required.

### Exercise 24. Does ALL TABLES apply to future tables?

**Answer:** Not automatically. You must use `ALTER DEFAULT PRIVILEGES` for the role creating the objects and the corresponding schema.

### Exercise 25. Do default privileges FOR ROLE owner apply if deployer creates a table without SET ROLE?

**Answer:** Not automatically just because deployer is a member; default privileges attach to the role actually creating the object.

### Exercise 26. Can a user DROP a table because of GRANT ALL?

**Answer:** `GRANT ALL` object privileges do not transfer ownership/DDL rights. `DROP`/`ALTER` depend on ownership/membership and related rights.

### Exercise 27. Is RLS the same as GRANT SELECT?

**Answer:** No. `SELECT` privilege permits operations on the table; RLS can restrict individual rows. Table owners, superusers, and `BYPASSRLS` have bypass rules that must be checked.

### Exercise 28. Should an app role be SUPERUSER to avoid permission denied?

**Answer:** No. Use least privilege, configure schema/table/sequence grants properly, and enforce app authorization.

### Exercise 29. What must you watch out for with SET ROLE in a connection pool?

**Answer:** Session state must be reliably reset/controlled; otherwise, subsequent requests may inherit the previous request's effective role privileges.

### Exercise 30. What should you watch out for with secure functions?

**Answer:** For `SECURITY DEFINER`, control the owner, `EXECUTE`, `search_path`, dynamic SQL, input validation, and caller authorization to prevent privilege escalation.

### Exercise 31. When should you use a NOLOGIN owner?

**Answer:** When you want a role owning schemas/tables to have no direct login credentials, while the deployer can `SET ROLE` to owner under appropriate management permissions.

### Exercise 32. When should you grant ADMIN TRUE?

**Answer:** Only to roles that need to administer membership. Normal app runtime does not need `ADMIN`.

### Exercise 33. Why can't you infer privileges solely from rolinherit in PG16+?

**Answer:** Because inheritance is a per-membership option on each edge; `ALTER ROLE NOINHERIT` does not automatically change existing grants.

### Exercise 34. Why is inspecting only table ACLs insufficient?

**Answer:** Privileges can come from the role graph, `PUBLIC`, ownership, `SECURITY DEFINER` functions, schema access, or RLS. You must combine multiple layers and test with the real role.

### Exercise 35. Should you put literal passwords in CREATE ROLE migrations?

**Answer:** No—do not store plaintext secrets in repos or CI logs. Use a secret manager or secure credential setup mechanism.

### Exercise 36. What is the workflow for removing a privilege?

**Answer:** Find all grant paths, run `REVOKE` or adjust memberships as needed, inspect catalogs/functions, test with the application role, check connection pools, and monitor permission failures.

## 53. Implementation Checklist

- [ ] Identify the PostgreSQL major version, especially membership semantics from PostgreSQL 16 onward.
- [ ] Distinguish cluster-wide roles from per-database/per-schema object grants.
- [ ] Create `NOLOGIN` roles for privilege groups and owners, and `LOGIN` roles for connection identities.
- [ ] Do not grant `SUPERUSER`/`CREATEROLE`/`CREATEDB`/`BYPASSRLS` to runtime unless truly necessary.
- [ ] Ensure `LOGIN` roles also satisfy authentication, `pg_hba`/TLS, and database `CONNECT`.
- [ ] Separate reader, writer, deployer, and owner by responsibility.
- [ ] Grant schema `USAGE` and sufficient—but not overly broad—object privileges.
- [ ] Grant schema `CREATE` only to roles that need to create objects.
- [ ] Grant memberships with explicit `INHERIT`/`SET`/`ADMIN` options on PG16+.
- [ ] Do not assume role attributes are inherited like table `SELECT`.
- [ ] Check multiple membership paths, not just a single edge.
- [ ] Use `pg_has_role` to distinguish `MEMBER`/`USAGE`/`SET` where supported by your version.
- [ ] Use `has_table_privilege`/`has_schema_privilege` and real queries with a non-superuser role.
- [ ] Do not treat `REVOKE` as an absolute `DENY`; check `PUBLIC`, direct, and indirect grants.
- [ ] Review `PUBLIC` privileges and the `public` schema per version rather than relying on historical assumptions.
- [ ] Verify sequence grants when `INSERT` uses sequences.
- [ ] Control column-level `SELECT`/`UPDATE` when sensitive data is present.
- [ ] Distinguish object ownership from ordinary table privileges.
- [ ] Use `SET ROLE` to owner in a controlled way during migrations; never let app runtime assume owner.
- [ ] Manage `ALTER DEFAULT PRIVILEGES` for the exact role actually creating objects.
- [ ] Restrict `PUBLIC` `EXECUTE` and review `SECURITY DEFINER` functions.
- [ ] Set a safe `search_path` for security-sensitive SQL.
- [ ] Apply RLS when row-level isolation is needed; check owner/`BYPASSRLS` behavior.
- [ ] Do not rely on DB `current_user` as the sole web end-user identifier.
- [ ] Do not hard-code passwords; use secret rotation and TLS.
- [ ] Reset roles/session state in connection pools.
- [ ] Test both positive and permission-denied cases with unprivileged roles.
- [ ] Maintain migrations/audit trails for `CREATE ROLE`/`GRANT`/`REVOKE`.
- [ ] Do not drop a cluster-wide role without checking dependencies and scope.

## 54. Official PostgreSQL Documentation

Read the documentation **for your server's major version**, as membership semantics and role administration privileges have changed across releases:

- [Database Roles](https://www.postgresql.org/docs/current/user-manag.html) — introduction to roles.
- [Role Attributes](https://www.postgresql.org/docs/current/role-attributes.html) — `LOGIN`, `SUPERUSER`, `CREATEDB`, `CREATEROLE`, `INHERIT`, `BYPASSRLS`.
- [Role Membership](https://www.postgresql.org/docs/current/role-membership.html) — `GRANT`/`REVOKE` role, `INHERIT`/`SET`/`ADMIN` options, membership paths.
- [Privileges](https://www.postgresql.org/docs/current/ddl-priv.html) — object privileges, `PUBLIC`, ownership, and ACLs.
- [CREATE ROLE](https://www.postgresql.org/docs/current/sql-createrole.html) — creating roles.
- [ALTER ROLE](https://www.postgresql.org/docs/current/sql-alterrole.html) — modifying role attributes.
- [GRANT](https://www.postgresql.org/docs/current/sql-grant.html) — object privilege grants and role membership.
- [REVOKE](https://www.postgresql.org/docs/current/sql-revoke.html) — revoking grants.
- [SET ROLE](https://www.postgresql.org/docs/current/sql-set-role.html) — changing the effective current role.
- [ALTER DEFAULT PRIVILEGES](https://www.postgresql.org/docs/current/sql-alterdefaultprivileges.html) — grants for objects to be created later.
- [Information Functions](https://www.postgresql.org/docs/current/functions-info.html) — `current_user`, `pg_has_role`, `has_table_privilege`, and other functions.
- [System Catalog pg_auth_members](https://www.postgresql.org/docs/current/catalog-pg-auth-members.html) — role members and options.
- [System View pg_roles](https://www.postgresql.org/docs/current/view-pg-roles.html) — role metadata.
- [Schemas](https://www.postgresql.org/docs/current/ddl-schemas.html) — schema `USAGE`/`CREATE`, `search_path`.
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) — RLS and bypass conditions.
- [Function Security](https://www.postgresql.org/docs/current/perm-functions.html) — controlling function privileges, `SECURITY DEFINER`.
- [Client Authentication](https://www.postgresql.org/docs/current/client-authentication.html) — `pg_hba`, authentication.
- [Password Authentication](https://www.postgresql.org/docs/current/auth-password.html) — SCRAM and credential protection.

`/current/` points to the current PostgreSQL documentation; when deploying on PostgreSQL 15 or older, **do not blindly use PostgreSQL 16+ membership options**.

## 55. Summary

**A role is a privilege identity in PostgreSQL, `LOGIN` is the ability to log in, membership is a relationship between roles, and inherited privileges depend on how those relationships are configured.**

Key takeaways:

1. **Roles have cluster-wide scope**; schema, table, and database privileges remain separate object privileges.
2. **`LOGIN` does not automatically grant `CONNECT` or `SELECT`**. Authentication and other privilege conditions are still required.
3. **`NOLOGIN` is well suited for permission groups and owner roles**, though an authorized session can still `SET ROLE` to them.
4. **`GRANT SELECT ON table TO role` differs from `GRANT role TO member`**: one grants an object privilege, while the other grants membership.
5. **PostgreSQL 16+ separates `INHERIT`, `SET`, and `ADMIN` per membership grant**. Holding membership does not mean automatically using privileges, being able to `SET ROLE`, or administering membership.
6. **Special role attributes are not inherited like object privileges**. Do not confuse `SUPERUSER`/`CREATEDB`/`CREATEROLE`/`LOGIN` with `SELECT`.
7. **`SET ROLE` changes `current_user`**, usually without changing `session_user`; `RESET ROLE` returns the effective role to the initial context.
8. **`ALTER ROLE NOINHERIT` in PG16+ does not retroactively change existing membership options**.
9. **`REVOKE` is not an absolute `DENY`**: privileges may persist via `PUBLIC`, direct grants, the role graph, ownership, or privilege-elevating routines.
10. **Schema `USAGE`, database `CONNECT`, table privileges, RLS, and function `EXECUTE` are distinct layers**; they must be evaluated together.
11. **`NOLOGIN` owner + `deployer SET ROLE owner` + low-privilege runtime** is a solid pattern for separating DDL from DML.
12. **Verify privileges using catalogs, privilege functions, and queries run under the real login role**, rather than concluding from a single `GRANT` statement.
13. **Combine privilege design with controls over session pools, secrets, `SECURITY DEFINER`, and RLS** to prevent privileges from leaking through unintended paths.

When you explicitly model **who logs in, which privilege groups they belong to, what they inherit automatically, which roles they can switch to, and which objects they can access**, a PostgreSQL system becomes easier to audit, more secure, and easier to scale without granting excessive privileges to the application.
