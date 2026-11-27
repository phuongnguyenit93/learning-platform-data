# Default Privileges and Permissions on Future Objects in PostgreSQL

When deploying a PostgreSQL system, granting permissions via `GRANT` on existing tables is not enough. Tomorrow, the development team runs a migration creating table `orders_2027`, view `order_summary`, or sequence `invoice_no_seq`. **Who has permission to read, write, or invoke those new objects?** Without an explicit policy, applications can suddenly fail with `permission denied`—or worse, a newly created function ends up with broader `EXECUTE` permissions than intended.

PostgreSQL addresses **default privileges for objects created in the future** using:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE app_owner
    IN SCHEMA app
GRANT SELECT ON TABLES TO app_reader;
```

Read this statement literally:

> Whenever **role `app_owner`** creates **a table or object belonging to the `TABLES` group** in schema `app` **from this point forward**, automatically grant `SELECT` on that object to role `app_reader`.

This **does not** mean:

- Existing tables in schema `app` immediately receive the privilege.
- Other roles in the same group as `app_owner` inherit `app_owner`'s default privileges when they create tables themselves.
- Role `app_reader` can access the schema without `USAGE ON SCHEMA`.
- `SELECT` bypasses Row-Level Security (RLS), access policies, or other constraints.
- Configuring default privileges replaces auditing actual permissions after a migration.

This lesson dives deep into **`ALTER DEFAULT PRIVILEGES`, `FOR ROLE`, `IN SCHEMA`, global vs. per-schema defaults, `PUBLIC`, privileges on tables/sequences/functions/types/schemas, the effect of `SET ROLE`, inspection with `\\ddp` and `pg_default_acl`, safe migrations, application privileges, RLS, and hands-on PostgreSQL exercises**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish `GRANT` on an existing object, `GRANT ... ON ALL ... IN SCHEMA`, and `ALTER DEFAULT PRIVILEGES`.
2. Explain why default privileges apply only at **object creation time**, never retroactively.
3. Identify the **object creator/current role** that determines which default privileges set is applied.
4. Use `FOR ROLE`, `IN SCHEMA`, and `GRANT`/`REVOKE` syntax for future objects.
5. Distinguish **global** and **per-schema** default privilege configurations; understand why a per-schema `REVOKE` cannot remove a global default `GRANT`.
6. Understand the role of `PUBLIC` and PostgreSQL defaults for `EXECUTE` on functions and `USAGE` on types.
7. Design future privileges individually for **TABLES, SEQUENCES, FUNCTIONS/ROUTINES, TYPES, and SCHEMAS**.
8. Grant future privileges following *least privilege*, avoiding unnecessary `GRANT ALL`.
9. Understand why granting `INSERT` on a table is not necessarily enough for code calling `nextval()` or `UPDATE ... WHERE`.
10. Inspect active policies using `psql \\ddp`, catalog `pg_default_acl`, and effective rights via `has_*_privilege` functions.
11. Design deployment workflows with migration roles, owner roles, `SET ROLE`, and schema privileges.
12. Distinguish privileges across base tables, views, partitions, sequences, routines, types, and schemas.
13. Understand that default privileges do not replace `GRANT USAGE ON SCHEMA`, RLS, or `SECURITY DEFINER` privilege checks.
14. Write regression tests to catch privilege drift after deployments.
15. Follow a runbook to diagnose `42501 insufficient_privilege` errors when new objects appear.

## 2. Three-Layer Privilege Model in PostgreSQL

When an application accesses a table, distinguish three questions:

1. **Can it connect to the database?** E.g., `CONNECT ON DATABASE`.
2. **Can it access the namespace/schema?** E.g., `USAGE ON SCHEMA`.
3. **Does it hold the right privileges on the object?** E.g., `SELECT ON TABLE`, `USAGE ON SEQUENCE`, or `EXECUTE ON FUNCTION`.

An access flow:

```text
Client / role app_reader
        |
        v
Database (CONNECT)
        |
        v
Schema app (USAGE)
        |
        v
Table app.orders (SELECT)
        |
        v
Row-Level Security / view semantics (if applicable)
        |
        v
Actual rows permitted to be returned
```

`ALTER DEFAULT PRIVILEGES` primarily controls **initial privileges on new objects in the third layer**, plus setting default privileges for schemas created in the future. It does not automatically grant privileges at the remaining layers.

### 2.1. Schema Privileges and Table Privileges Are Independent

For example:

```sql
GRANT USAGE ON SCHEMA app TO app_reader;
```

allows the role to look up/reference object names in the schema when other privileges are met. It **does not automatically allow `SELECT` on all tables** in the schema.

Conversely:

```sql
GRANT SELECT ON app.orders TO app_reader;
```

does not automatically grant `USAGE ON SCHEMA app` if the role lacks it.

### 2.2. A Role Granted Privileges Might Still Not See Every Row

A table with RLS enabled may expose only certain rows. A default `GRANT SELECT` does not bypass RLS. Likewise, views have owner/invoker semantics and privileges that must be evaluated separately.

### 2.3. The Object-Owning Role Holds a Special Position

The object owner holds object-administration capabilities tied to ownership. The purpose of default privileges is typically to **grant required privileges to other roles** when the owner creates new objects, not to alter ownership semantics.

## 3. Three Commonly Confused Commands: GRANT, ALL, and DEFAULT

Suppose schema `app` currently has tables `customers` and `orders`, and will soon have table `invoices`.

| Statement | Affected objects | Timing |
| --- | --- | --- |
| `GRANT SELECT ON app.orders TO app_reader` | The specified `orders` table | Immediately on execution |
| `GRANT SELECT ON ALL TABLES IN SCHEMA app TO app_reader` | **Currently existing** `TABLES`-category objects in the schema | Immediately on execution |
| `ALTER DEFAULT PRIVILEGES ... GRANT SELECT ON TABLES TO app_reader` | Objects of that kind **created later by the designated role** | At future `CREATE` time |

### 3.1. Two Commands Usually Used Together

When initializing permissions for an application that already has data:

```sql
-- For existing tables:
GRANT SELECT ON ALL TABLES IN SCHEMA app TO app_reader;

-- For tables created later by app_owner:
ALTER DEFAULT PRIVILEGES
    FOR ROLE app_owner
    IN SCHEMA app
GRANT SELECT ON TABLES TO app_reader;
```

In this example, the roles/schemas must already exist and the executor must have appropriate rights. This is a **design pattern**; do not run it before preparing the environment.

### 3.2. GRANT ON ALL Alone Is Not Enough for the Future

A week after migration:

```sql
CREATE TABLE app.new_feature (...);
```

The new table **does not automatically inherit** last week's `GRANT ON ALL TABLES`. If default privileges are not configured for the **actual creator role**, `app_reader` may be denied `SELECT`.

### 3.3. ALTER DEFAULT PRIVILEGES Alone Is Not Enough for the Past

Existing tables keep their own ACLs. PostgreSQL does not rescan and rewrite privileges on old objects whenever you edit default privilege settings.

## 4. ALTER DEFAULT PRIVILEGES Syntax

Structure:

```sql
ALTER DEFAULT PRIVILEGES
    [FOR ROLE creator_role [, ...]]
    [IN SCHEMA schema_name [, ...]]
GRANT privileges ON object_type TO grantee_role [, ...];
```

Or:

```sql
ALTER DEFAULT PRIVILEGES
    [FOR ROLE creator_role [, ...]]
    [IN SCHEMA schema_name [, ...]]
REVOKE privileges ON object_type FROM grantee_role [, ...];
```

The `[...]` brackets in these two blocks are **syntax notation indicating optional clauses**, not literal SQL characters to type.

### 4.1. FOR ROLE

Specifies the role **that will create objects**. If `FOR ROLE` is omitted, PostgreSQL uses the current role executing the statement.

```sql
ALTER DEFAULT PRIVILEGES FOR ROLE app_owner
GRANT SELECT ON TABLES TO app_reader;
```

Do not misread `app_owner` as the role **receiving** `SELECT`; the recipient role after `TO` is `app_reader`.

### 4.2. IN SCHEMA

Restricts where objects **will be created**. This configures defaults specifically for the named schema:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE app_owner
    IN SCHEMA app
GRANT SELECT ON TABLES TO app_reader;
```

If `IN SCHEMA` is omitted, the default configuration has **global scope for objects created by that creator role**, regardless of schema, subject to object-type differences.

### 4.3. GRANT and REVOKE

- `GRANT` adds privileges for future objects.
- `REVOKE` adjusts default configuration within the corresponding scope; important rules apply when both global and per-schema defaults exist.

These are **not** DML statements or operations that update ACLs on already-existing objects.

### 4.4. Commonly Used Object Types

```sql
ON TABLES
ON SEQUENCES
ON FUNCTIONS
ON ROUTINES
ON TYPES
ON SCHEMAS
```

Supported scope and behavior for each group should be checked against your environment's PostgreSQL version. Here we focus on the types commonly used in application deployments.

## 5. Summary Table of Privileges by Object Type

| Object | Common privileges | Example purpose |
| --- | --- | --- |
| `TABLES` | `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `REFERENCES`, `TRIGGER` | Read/write/declare constraints or triggers as applicable |
| `SEQUENCES` | `USAGE`, `SELECT`, `UPDATE` | Call `nextval`, `currval`, `setval` per matching privilege |
| `FUNCTIONS` / `ROUTINES` | `EXECUTE` | Call permitted functions or procedures |
| `TYPES` | `USAGE` | Reference/use corresponding data types, domains, types |
| `SCHEMAS` | `USAGE`, `CREATE` | Resolve object names or create objects in the schema |

Newer PostgreSQL releases also introduce additional table privileges such as maintenance rights; never copy a `GRANT ALL` without knowing which privileges it includes in your running version.

### 5.1. Why Should You Not Habitually Use GRANT ALL?

`GRANT ALL PRIVILEGES ON TABLES` can grant capabilities unneeded by simple read/write applications, such as `TRUNCATE`, `REFERENCES`, or `TRIGGER`, depending on object type and version.

Start with **dedicated `SELECT` for readers**, and only the write privileges genuinely needed for writers.

### 5.2. INSERT Does Not Imply Read Permission

`GRANT INSERT ON TABLE` does not automatically grant `SELECT`. In PostgreSQL, an `UPDATE ... WHERE some_column=...` or `INSERT ... RETURNING column` statement can require additional `SELECT` on the read or returned columns.

Always inspect the **application's actual SQL queries**, not just CRUD labels.

## 6. When Defaults Apply: At Object Creation Time

Timeline:

```text
T0: app_owner creates app.old_table
      -> Privileges determined at T0

T1: ALTER DEFAULT PRIVILEGES FOR ROLE app_owner
    IN SCHEMA app GRANT SELECT ON TABLES TO app_reader
      -> Changes policy for future CREATEs

T2: app_owner creates app.new_table
      -> PostgreSQL initializes ACL per policy at T2

T3: REVOKE default SELECT in policy
      -> Only changes policy for CREATEs after T3

T4: app_owner creates app.third_table
      -> No longer receives grant from the removed rule
```

**Key point:** The ACL assigned to `new_table` at T2 **is not automatically removed** when the default policy is revoked at T3.

### 6.1. Object-Level GRANT Remains Independent State

After creating a table, the owner or a holder of grant option can run:

```sql
GRANT SELECT ON app.new_table TO another_reader;
REVOKE SELECT ON app.new_table FROM app_reader;
```

These commands adjust privileges on the **specific object** without modifying the default policy.

### 6.2. ALTER OWNER Does Not Reapply Default ACLs

If a table is created by `app_deployer` and later transferred to `app_owner`, PostgreSQL **does not treat that as a new `CREATE` by `app_owner`** to apply `app_owner`'s default ACLs. Plan explicit `GRANT`s or proper creation/migration steps rather than expecting `ALTER TABLE ... OWNER TO` to rewrite creation history.

## 7. Multi-Role Lab: Goals and Prerequisites

We create:

- `acl_owner`: role owning schemas and creating objects.
- `acl_reader`: role with read-only access to tables/documents.
- `acl_writer`: role with read/write access as granted.
- `acl_deployer`: role simulating a migration runner able to create objects.
- `acl_lab`: primary schema.
- `acl_else`: second schema to test global vs. per-schema defaults.

**Prerequisites:** the role/schema setup commands are for a test database and a user with role/schema administrative rights, such as a lab superuser. If you lack `CREATEROLE` or permission to `SET ROLE` to these test roles, skip running setup and review the example statements with your DBA.

### 7.1. Creating Roles, Schemas, and Namespace Privileges

```sql
-- Run once in a clean test database.
CREATE ROLE acl_owner NOLOGIN;
CREATE ROLE acl_reader NOLOGIN;
CREATE ROLE acl_writer NOLOGIN;
CREATE ROLE acl_deployer NOLOGIN;

-- With sufficient privileges, create schemas owned by the designated owner.
CREATE SCHEMA acl_lab AUTHORIZATION acl_owner;
CREATE SCHEMA acl_else AUTHORIZATION acl_owner;

-- Allow reader/writer to resolve objects in the schemas.
GRANT USAGE ON SCHEMA acl_lab TO acl_reader, acl_writer;
GRANT USAGE ON SCHEMA acl_else TO acl_reader, acl_writer;

-- Give deployer permission to create objects (simulating a migration runner).
GRANT CREATE ON SCHEMA acl_lab TO acl_deployer;

-- Deployer is a member of the owner role to simulate
-- being able to SET ROLE acl_owner in a deployment pipeline.
GRANT acl_owner TO acl_deployer;
```

**Note:** This lab assumes an administrative account has permission to `SET ROLE` to those roles. In production systems, role names, membership options, and role-creation rights must follow organizational policy; never grant broad owner roles to runtime applications.

### 7.2. Why Are NOLOGIN Roles Still Essential?

A `NOLOGIN` role cannot log in directly, yet it can still:

- Own database objects.
- Receive `GRANT`s.
- Be the target of `SET ROLE` if the session is authorized.
- Be granted as a role/group to other login roles.

This pattern cleanly separates **ownership** from **login identities**.

### 7.3. Do Not Grant Table Privileges Directly Before the Experiment

So far we have only granted `USAGE ON SCHEMA`. `SELECT`/`INSERT` privileges on tables will be tested separately to observe the effect of default privileges.

## 8. Creating a Table Before Configuring Default Privileges

Run under the role that will own the object:

```sql
SET ROLE acl_owner;

CREATE TABLE acl_lab.before_default (
    id bigint PRIMARY KEY,
    note text NOT NULL
);

INSERT INTO acl_lab.before_default(id, note)
VALUES (1, 'created before policy');

RESET ROLE;
```

Verify:

```sql
SELECT
    has_schema_privilege('acl_reader', 'acl_lab', 'USAGE')
        AS reader_can_use_schema,
    has_table_privilege(
        'acl_reader', 'acl_lab.before_default', 'SELECT'
    ) AS reader_can_select_old_table;
```

Expected in a clean lab with no other global defaults or `GRANT`s:

- `reader_can_use_schema = true`.
- `reader_can_select_old_table = false`.

### 8.1. Why Use has_table_privilege?

It checks effective privileges for a role and object at the current moment. That makes it much easier to automate in tests than manually parsing ACL text.

### 8.2. What If It Unexpectedly Returns True?

The role may already hold privileges via `PUBLIC`, membership, or another `GRANT`; the lab may not be clean; or the object may already exist. Find the **actual privilege source** rather than assuming PostgreSQL applied an unexpected default.

## 9. Configuring Default Privileges for Future Tables

Run as role `acl_owner`:

```sql
SET ROLE acl_owner;

ALTER DEFAULT PRIVILEGES
    IN SCHEMA acl_lab
GRANT SELECT ON TABLES TO acl_reader;

ALTER DEFAULT PRIVILEGES
    IN SCHEMA acl_lab
GRANT SELECT, INSERT, UPDATE ON TABLES TO acl_writer;

RESET ROLE;
```

These two statements mean:

- When `acl_owner` creates an object in the `TABLES` category inside `acl_lab`, `acl_reader` receives `SELECT`.
- `acl_writer` receives `SELECT`, `INSERT`, and `UPDATE`.
- `DELETE`, `TRUNCATE`, and higher administrative rights are not automatically granted.

### 9.1. Explicit FOR ROLE

If an administrator has permission to alter default privileges for `acl_owner`, the equivalent form is:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
    IN SCHEMA acl_lab
GRANT SELECT ON TABLES TO acl_reader;
```

Write `FOR ROLE` explicitly in migrations and audit scripts to avoid creator confusion when sessions run under a different role.

### 9.2. Default Grants Do Not Fix Missing Schema USAGE

The default `GRANT`s in section 9 do not modify schema ACLs. The lab explicitly granted `USAGE ON SCHEMA acl_lab` in section 7.

### 9.3. Non-Retroactive

`acl_lab.before_default` still does not automatically gain `SELECT` for reader unless granted explicitly or via another privilege.

## 10. Creating a Table, a View, and Checking New Privileges

```sql
SET ROLE acl_owner;

CREATE TABLE acl_lab.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_name text NOT NULL,
    net_amount numeric(12, 2) NOT NULL
        CHECK (net_amount >= 0)
);

CREATE VIEW acl_lab.order_overview AS
SELECT order_id, customer_name, net_amount
FROM acl_lab.orders;

RESET ROLE;
```

Verify:

```sql
SELECT
    has_table_privilege(
        'acl_reader', 'acl_lab.orders', 'SELECT'
    ) AS reader_selects_orders,
    has_table_privilege(
        'acl_writer', 'acl_lab.orders', 'INSERT'
    ) AS writer_inserts_orders,
    has_table_privilege(
        'acl_writer', 'acl_lab.orders', 'UPDATE'
    ) AS writer_updates_orders,
    has_table_privilege(
        'acl_reader', 'acl_lab.order_overview', 'SELECT'
    ) AS reader_selects_view,
    has_table_privilege(
        'acl_reader', 'acl_lab.before_default', 'SELECT'
    ) AS reader_selects_old_table;
```

In a clean lab:

| Check | Expected |
| --- | --- |
| Reader `SELECT` on new `orders` table | `TRUE` |
| Writer `INSERT` on new `orders` table | `TRUE` |
| Writer `UPDATE` on new `orders` table | `TRUE` |
| Reader `SELECT` on new `order_overview` view | `TRUE` |
| Reader `SELECT` on old `before_default` table | `FALSE` |

### 10.1. Why Do Views Also Follow the ON TABLES Policy?

In PostgreSQL's privilege system, the `TABLES` keyword in `GRANT`/default ACLs encompasses relation types handled under table-like privileges, including regular views. Do not look for a separate `ON VIEWS` clause for standard view defaults.

### 10.2. Updatable Views Carry Risk If INSERT/UPDATE Is Granted

If a view is automatically updatable and writer holds `INSERT`/`UPDATE` on views, writer may modify the underlying table through the view subject to permissions, owner/invoker semantics, check options, and constraints.

If a schema contains both **reporting-only views** and **transactional write tables**, defaulting `INSERT, UPDATE ON TABLES` may be broader than intended. Consider separating schemas and inspecting privileges on new views.

## 11. Testing Under the Grantee Roles

A `NOLOGIN` role can still be tested with `SET ROLE` from an authorized administrative session.

### 11.1. Testing Reader

```sql
SET ROLE acl_reader;

SELECT order_id, customer_name, net_amount
FROM acl_lab.orders
ORDER BY order_id;

SELECT *
FROM acl_lab.order_overview;

RESET ROLE;
```

### 11.2. Testing Writer

```sql
SET ROLE acl_writer;

INSERT INTO acl_lab.orders(customer_name, net_amount)
VALUES ('Customer A', 100.00);

SELECT order_id, customer_name, net_amount
FROM acl_lab.orders
ORDER BY order_id;

RESET ROLE;
```

### 11.3. INSERT RETURNING Requires Checking SELECT Privileges

Because the lab granted `SELECT` to writer, `INSERT ... RETURNING order_id` works under current permissions. If a writer has only `INSERT` without `SELECT`, columns in `RETURNING` or `WHERE`/expressions in `UPDATE` may require additional read privileges.

### 11.4. Never Use an Administrative Role to Verify Application Permissions

A `SELECT` succeeding under `acl_owner` does not prove `acl_reader` has access. Always test under the runtime identity or via `has_*_privilege` for the real role.

## 12. Fixing Privileges on Older Tables

At this point `before_default` still lacks `SELECT` for reader.

You can grant it specifically:

```sql
SET ROLE acl_owner;

GRANT SELECT ON acl_lab.before_default TO acl_reader;

RESET ROLE;
```

Or if policy calls for granting across **all existing tables in the schema**:

```sql
-- Execute only as the role owning the objects,
-- holding grant option, or holding required admin privileges.
GRANT SELECT ON ALL TABLES IN SCHEMA acl_lab TO acl_reader;
```

### 12.1. Ownership Note for GRANT ON ALL

If a schema contains tables owned by **multiple different roles**, a role that merely owns the schema may not have permission to `GRANT` on all those tables. `GRANT ... ON ALL TABLES` requires sufficient authority on each object; warnings or permission errors can occur for objects the grantor cannot modify.

### 12.2. Standard Migration Pattern for Existing Systems

Typically deploy in two steps:

1. Grant appropriate privileges on **existing** objects.
2. Configure default privileges for **future** objects.

And afterward, **verify** using the actual roles.

## 13. Default Privileges on SEQUENCES

A sequence is a separate object, not a table. An application calling `nextval('schema.seq')` may need `USAGE` or another matching privilege on the sequence.

```sql
SET ROLE acl_owner;

ALTER DEFAULT PRIVILEGES
    IN SCHEMA acl_lab
GRANT USAGE, SELECT ON SEQUENCES TO acl_writer;

CREATE SEQUENCE acl_lab.invoice_no_seq
    START WITH 1000
    INCREMENT BY 1;

RESET ROLE;
```

Verify:

```sql
SELECT
    has_sequence_privilege(
        'acl_writer',
        'acl_lab.invoice_no_seq',
        'USAGE'
    ) AS writer_uses_sequence,
    has_sequence_privilege(
        'acl_reader',
        'acl_lab.invoice_no_seq',
        'USAGE'
    ) AS reader_uses_sequence;
```

In the lab:

- Writer has `USAGE`.
- Reader has not been granted `USAGE` on the sequence.

### 13.1. GRANT SELECT ON TABLES Does Not Grant Sequence Privileges

This is a common error:

```text
The application has INSERT on the table.
The ID column uses DEFAULT nextval('invoice_no_seq').
The application still gets permission denied for sequence.
```

The cause may be that the application lacks `USAGE` on the referenced sequence.

### 13.2. SERIAL and IDENTITY Are Not Identical

With a traditional `SERIAL` column, the default calls `nextval()`; the inserting role may need sequence privileges.

With PostgreSQL `GENERATED ... AS IDENTITY`, identity value generation during `INSERT` follows identity semantics and does not necessarily require the role to hold separate `USAGE` on the internal sequence the way an explicit `nextval()` call does. However, if the application **calls the sequence directly**, sequence privileges still apply.

Never fix every error by granting `ALL ON ALL SEQUENCES` without inspecting the column type and actual SQL.

### 13.3. SELECT, USAGE, and UPDATE on Sequences

`nextval`, `currval`, and `setval` have different privilege requirements. In many cases, `USAGE` suffices for `nextval`, while `UPDATE` gives broader control over sequence state. Grant only what the application needs.

### 13.4. Direct Test

```sql
SET ROLE acl_writer;

SELECT nextval('acl_lab.invoice_no_seq');

RESET ROLE;
```

This statement **has a side effect**: the sequence advances, and allocated values do not roll back like normal table rows. Run this only in the lab.

## 14. Default Privileges on FUNCTIONS and ROUTINES

For functions and procedures, the primary privilege to manage is `EXECUTE`.

Example:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
    IN SCHEMA acl_lab
GRANT EXECUTE ON FUNCTIONS TO acl_reader;
```

In supported versions, `ROUTINES` can also be used to cover both functions and procedures syntactically.

### 14.1. Critical Security Distinction: PUBLIC EXECUTE

By default in PostgreSQL, a newly created function typically receives `EXECUTE` for `PUBLIC` (all roles) unless altered by a default privilege policy.

Thus a per-schema `GRANT EXECUTE ... TO acl_reader` **does not necessarily restrict the function to reader alone**. While `PUBLIC` retains `EXECUTE`, many other roles can still call it.

### 14.2. Global-Scope Hardening

To remove default `PUBLIC` `EXECUTE` for future functions created by `acl_owner`:

```sql
SET ROLE acl_owner;

ALTER DEFAULT PRIVILEGES
REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

ALTER DEFAULT PRIVILEGES
    IN SCHEMA acl_lab
GRANT EXECUTE ON FUNCTIONS TO acl_reader;

RESET ROLE;
```

Then:

- Future functions created by `acl_owner` do not automatically grant `EXECUTE` to `PUBLIC` via the built-in default.
- Future functions in `acl_lab` receive `EXECUTE` for reader via the per-schema rule.

**Note:** the global `REVOKE` applies to future functions created by `acl_owner` across every schema, not only `acl_lab`. Evaluate impact on other application groups before enabling it in a shared environment.

### 14.3. Why Is REVOKE PUBLIC at Per-Schema Scope Not Enough?

If the built-in default or a global default still grants `PUBLIC`, a statement like:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
    IN SCHEMA acl_lab
REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
```

**is not** a way to strip an `EXECUTE` privilege granted at the global level. Per-schema default privileges **add onto** global defaults; to remove global `PUBLIC` `EXECUTE`, you must modify the global default.

This is one of the easiest mistakes to make with `ALTER DEFAULT PRIVILEGES`.

## 15. Creating a Function After Configuring Privileges

```sql
SET ROLE acl_owner;

CREATE FUNCTION acl_lab.calculate_tax(p_net numeric)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT p_net * 0.10
$$;

RESET ROLE;
```

Verify:

```sql
SELECT
    has_function_privilege(
        'acl_reader',
        'acl_lab.calculate_tax(numeric)',
        'EXECUTE'
    ) AS reader_executes_function,
    has_function_privilege(
        'acl_writer',
        'acl_lab.calculate_tax(numeric)',
        'EXECUTE'
    ) AS writer_executes_function;
```

In a clean lab, after revoking global `PUBLIC` `EXECUTE`:

- `acl_reader` holds `EXECUTE` from the per-schema default `GRANT`.
- `acl_writer` does not automatically hold `EXECUTE` unless granted via another path.

### 15.1. Test from the Reader Role

```sql
SET ROLE acl_reader;

SELECT acl_lab.calculate_tax(100.00);

RESET ROLE;
```

### 15.2. Objects Created Before Default REVOKE Retain Old Privileges

Suppose an older function already had `PUBLIC` `EXECUTE`. Today's global default `REVOKE` does not retroactively remove that right. You must run a direct `REVOKE` on existing functions if you want to tighten access.

```sql
-- Example for an existing function:
REVOKE EXECUTE ON FUNCTION acl_lab.calculate_tax(numeric)
FROM PUBLIC;
```

When running commands like this in a real system, make sure you do not inadvertently break legitimate callers invoking the function.

## 16. Why Are PUBLIC Privileges Especially Sensitive?

`PUBLIC` is a group name encompassing **every role**, including roles created in the future. It is not a regular separate role you create with `CREATE ROLE PUBLIC`.

Example:

```sql
GRANT EXECUTE ON FUNCTION app.some_function(integer)
TO PUBLIC;
```

if granted, any role with schema access and passing other security checks has an opportunity to invoke the function.

### 16.1. Not Every Function Is Dangerous

A pure mathematical helper with no special rights may be intended for many roles to call. However, for functions that:

- Use `SECURITY DEFINER`.
- Modify data.
- Read sensitive information.
- Trigger payment workflows or grant permissions.
- Invoke extensions or system resources.

default `PUBLIC` `EXECUTE` can create significant risk surface.

### 16.2. CREATE and REVOKE in a Single Transaction

If default privilege hardening has not been configured, creating a function and revoking in two separate transactions creates a **window of overly broad privileges** between commits.

In a controlled migration, you can do:

```sql
BEGIN;

CREATE FUNCTION app.new_sensitive_function()
RETURNS integer
LANGUAGE sql
AS $$
    SELECT 1
$$;

REVOKE EXECUTE ON FUNCTION app.new_sensitive_function()
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app.new_sensitive_function()
TO app_service;

COMMIT;
```

This pattern assumes schemas/roles already exist, the runner owns the function, and function creation can sit inside a transaction. **Configuring global default `PUBLIC` revocation upfront** lowers the risk of forgetting `REVOKE` on each new function.

### 16.3. PUBLIC Differs from the ALL Keyword

- `PUBLIC`: the set of recipient roles receiving a privilege.
- `ALL PRIVILEGES`: the set of privilege types on an object.

These two keywords govern different axes and must never be confused.

## 17. Default Privileges on TYPES

Types and domains created in a schema also have a `USAGE` privilege. PostgreSQL may grant `USAGE` on types to `PUBLIC` by default, similar to `PUBLIC` `EXECUTE` on functions though for a different privilege type.

Example creating a domain:

```sql
SET ROLE acl_owner;

CREATE DOMAIN acl_lab.positive_money
AS numeric(12,2)
CHECK (VALUE >= 0);

RESET ROLE;
```

### 17.1. Granting Default USAGE for Future Types

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
    IN SCHEMA acl_lab
GRANT USAGE ON TYPES TO acl_reader;
```

This command **only applies to types created after it runs**; it does not alter privileges on the `positive_money` domain just created.

### 17.2. Per-Schema GRANT Does Not Remove Default PUBLIC

If global defaults still grant `PUBLIC` `USAGE` on types, adding a per-schema grant to reader does not revoke access from other roles.

To configure restrictive defaults, you may need to evaluate:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
REVOKE USAGE ON TYPES FROM PUBLIC;
```

This is a **broad change** for the owner's future types and can impact other applications or services. Check dependencies first.

### 17.3. Type USAGE Does Not Grant Table Read Access

A role can use the `positive_money` domain yet lack `SELECT` on any table using that domain. Type privileges and table privileges are independent.

### 17.4. Checking Privileges

```sql
SELECT
    has_type_privilege(
        'acl_reader',
        'acl_lab.positive_money',
        'USAGE'
    ) AS reader_uses_type;
```

For types created before changing defaults, the result depends on actual ACLs, including `PUBLIC` or direct `GRANT`s.

## 18. Default Privileges on Future SCHEMAS

When a role **creates new schemas**, you can also configure default privileges for schemas created in the future.

Example:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
GRANT USAGE ON SCHEMAS TO acl_reader;
```

When `acl_owner` creates a new schema later:

```sql
SET ROLE acl_owner;

CREATE SCHEMA acl_future;

RESET ROLE;
```

Role `acl_reader` receives `USAGE` on schema `acl_future` per that global rule, while still not automatically receiving `SELECT` on tables inside the new schema.

### 18.1. Do Not Use IN SCHEMA for Future Schema Defaults

Schemas do not nest in PostgreSQL. Therefore default privileges on **SCHEMAS** are configured at global scope for the creator role, never via `IN SCHEMA parent_schema` as with tables, sequences, functions, or types.

### 18.2. USAGE Differs from CREATE

Granting `USAGE ON SCHEMAS` lets the role resolve and access objects where it holds object privileges. Granting `CREATE ON SCHEMAS` is far broader: the role can create objects inside future schemas.

For readers and runtime applications, never grant `CREATE` just to work around a `SELECT` error.

### 18.3. Existing Schemas Do Not Change

Because `acl_lab` was created **before** the default `GRANT USAGE ON SCHEMAS` command, `acl_lab`'s ACL remains unchanged. The lab granted `USAGE` to reader/writer directly via `GRANT USAGE ON SCHEMA`.

## 19. Global Defaults and Per-Schema Defaults Are Additive

Two kinds of default privileges:

```text
Global (no IN SCHEMA):
    Applies whenever the creator role CREATEs an object,
    regardless of schema (where applicable).

Per-schema (with IN SCHEMA):
    Adds privileges for objects by the same creator
    when CREATEd in the specified schema.
```

Example:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
GRANT SELECT ON TABLES TO acl_reader;

ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
    IN SCHEMA acl_lab
GRANT INSERT ON TABLES TO acl_writer;
```

While both policies are active:

| Schema where table is created | `acl_reader` | `acl_writer` |
| --- | --- | --- |
| `acl_lab` | `SELECT` (global) | `INSERT` (per-schema) |
| `acl_else` | `SELECT` (global) | Does not automatically get `INSERT` from `acl_lab` rule |

### 19.1. Why Separate the Two Layers?

- Global defaults suit policies shared across every schema a role owns.
- Per-schema defaults suit schemas with distinct access requirements.

### 19.2. Overly Broad Globals Are a Design Risk

If `acl_owner` also creates tables in a schema holding sensitive data, a global `GRANT SELECT TO acl_reader` can expose tables to reader where you never intended.

When access requirements differ across domains, prefer **per-schema grants** and/or separate owner roles.

## 20. Crucial Pitfall: Per-Schema REVOKE Does Not Subtract Global GRANTs

Suppose a global policy already granted `SELECT`:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
GRANT SELECT ON TABLES TO acl_reader;
```

You want schema `acl_else` **not** to grant that `SELECT`, so you try:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
    IN SCHEMA acl_else
REVOKE SELECT ON TABLES FROM acl_reader;
```

**This fails to achieve the goal:** a per-schema `REVOKE` can only reverse matching per-schema grants; it **does not remove** privileges arising from global defaults.

### 20.1. The Right Design

If reader should read only schema `acl_lab`:

1. Do not grant global `SELECT` for that owner, or revoke the configured global policy.
2. Grant `SELECT` per-schema only for `acl_lab`.
3. Verify permissions on both existing and future objects.

Example:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
REVOKE SELECT ON TABLES FROM acl_reader;

ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
    IN SCHEMA acl_lab
GRANT SELECT ON TABLES TO acl_reader;
```

### 20.2. Global REVOKE Is Insufficient If a Per-Schema GRANT Exists

If a per-schema policy still grants `SELECT`, a global `REVOKE` **does not delete** that per-schema grant. To remove a default privilege completely, inspect **both layers**.

### 20.3. Test Inside a Transaction to Avoid Permanently Changing the Lab

```sql
BEGIN;

ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
GRANT SELECT ON TABLES TO acl_reader;

ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
    IN SCHEMA acl_else
REVOKE SELECT ON TABLES FROM acl_reader;

SET ROLE acl_owner;
CREATE TABLE acl_else.global_grant_example(id integer);
RESET ROLE;

SELECT has_table_privilege(
    'acl_reader',
    'acl_else.global_grant_example',
    'SELECT'
) AS reader_still_has_global_select;

ROLLBACK;
```

Expected to return `TRUE` in the lab context, demonstrating that per-schema `REVOKE` does not cancel a global grant. Because the entire block is rolled back, the global default ACL was altered only temporarily inside this transaction.

## 21. Object Creator: The Most Decisive Factor

A very common mistake:

```text
Role app_owner has properly configured default privileges.
Role deployer is a member of app_owner.
Deployer connects and runs CREATE TABLE directly.
The reader app gets permission denied on the new table.
```

Because **default privileges use the policy set of the role actually creating the object**, never automatically inheriting policies from roles of which the creator is a member.

### 21.1. current_user, current_role, session_user

Check:

```sql
SELECT
    current_user,
    current_role,
    session_user;
```

When running `SET ROLE acl_owner`:

```sql
SET ROLE acl_owner;

SELECT current_user, current_role, session_user;

RESET ROLE;
```

`current_user`/`current_role` reflect the effective role for privilege checks and object creation in ordinary contexts; `session_user` remains the role that initiated the session.

### 21.2. Membership Does Not Change the Creator Role

Even when:

```sql
GRANT acl_owner TO acl_deployer;
```

and deployer holds table-creation ability through grants/membership, running:

```sql
SET ROLE acl_deployer;
CREATE TABLE acl_lab.created_by_deployer(id integer);
RESET ROLE;
```

still creates the object **under role `acl_deployer`** if that is the current role at `CREATE` time.

### 21.3. Owner Defaults Do Not Apply Automatically to Deployer

If you only configured:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
    IN SCHEMA acl_lab
GRANT SELECT ON TABLES TO acl_reader;
```

then `acl_lab.created_by_deployer` receives no `SELECT` `GRANT` from that policy.

### 21.4. Verify

```sql
SELECT
    has_table_privilege(
        'acl_reader',
        'acl_lab.created_by_deployer',
        'SELECT'
    ) AS reader_can_read_deployer_table;
```

In a lab with no default `SELECT` configured for creator `acl_deployer`, the expected result is `FALSE` unless another grant exists.

## 22. How to Handle Migration Runners Creating Objects

There are two clear approaches.

### 22.1. Approach A — SET ROLE Owner Before CREATE

If `acl_deployer` is permitted to `SET ROLE acl_owner`:

```sql
SET ROLE acl_owner;

CREATE TABLE acl_lab.created_as_owner (
    id integer PRIMARY KEY,
    note text
);

RESET ROLE;
```

The new table is created by `acl_owner`, so the `FOR ROLE acl_owner` policy applies.

### 22.2. Approach B — Configure Defaults for the Deployer Itself

If runtime migrations always create objects as `acl_deployer`:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_deployer
    IN SCHEMA acl_lab
GRANT SELECT ON TABLES TO acl_reader;
```

Afterward:

```sql
SET ROLE acl_deployer;

CREATE TABLE acl_lab.created_after_deployer_policy (
    id integer PRIMARY KEY,
    description text
);

RESET ROLE;
```

Reader can receive `SELECT` on new tables created by deployer.

### 22.3. Do Not Mix Both Strategies Without Controls

If some migrations run under owner and others under deployer, privileges and ownership on future tables become inconsistent. Your pipeline should explicitly specify:

- Login/session role.
- Current role at `CREATE`.
- Resulting owner after `CREATE`.
- Target schema.
- Which default ACL applies.
- How to verify post-migration.

## 23. FOR ROLE Is Not the Privilege Recipient

Read the statement:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
    IN SCHEMA acl_lab
GRANT SELECT ON TABLES TO acl_reader;
```

across three positions:

| Clause | Role |
| --- | --- |
| `FOR ROLE acl_owner` | **Creator role** watched by the policy |
| `IN SCHEMA acl_lab` | **Location where objects are created** |
| `TO acl_reader` | **Grantee role** receiving privileges on new objects |

### 23.1. One Role Can Appear in Multiple Positions

You can configure defaults for the creating role itself or other group roles per policy, provided you understand ownership and effective privileges. Never use `GRANT ... TO owner` as a substitute for ownership mechanics.

### 23.2. Who Can Alter Default Privileges for Another Role?

Not just any user can modify another creator role's policy. PostgreSQL restricts altering default privileges to objects created by the current user, roles with appropriate membership/permission relationships, or sufficiently privileged administrators.

A runtime application should never be granted rights to edit the owner's default ACLs merely to `SELECT` new tables.

### 23.3. Multiple Target Roles in FOR ROLE

The syntax accepts multiple creator roles where permitted:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE team_owner_a, team_owner_b
    IN SCHEMA app
GRANT SELECT ON TABLES TO app_reader;
```

This is a conceptual example with hypothetical roles/schemas. The executor must hold sufficient permissions for every target role.

## 24. Creating Tables in Another Schema Does Not Trigger Per-Schema Grants

In the lab, `acl_reader` received per-schema default `SELECT` only in `acl_lab` from the owner's default policy.

Test:

```sql
SET ROLE acl_owner;

CREATE TABLE acl_else.other_orders (
    other_order_id integer PRIMARY KEY,
    note text
);

RESET ROLE;
```

Verify:

```sql
SELECT
    has_table_privilege(
        'acl_reader', 'acl_else.other_orders', 'SELECT'
    ) AS reader_selects_other_schema_table;
```

Without a global default `SELECT` for owner or another `GRANT`, the expected result is `FALSE`.

### 24.1. USAGE ON acl_else Does Not Turn SELECT into TRUE

The lab granted `USAGE ON SCHEMA acl_else` to reader, yet the role still does not automatically gain `SELECT` on `other_orders`.

### 24.2. Default Privileges Are Not Based on Table Names

Default policies key off **creator + schema + object type**, not whether a table is named `orders`, `other_orders`, or `secret_table`.

If tables in the same schema require different permissions, a blanket default grant is insufficient; consider splitting schemas, using distinct creator roles, or issuing object-specific `GRANT`/`REVOKE` in migrations.

## 25. Inspecting Default ACLs in psql with \\ddp

`psql` provides the meta-command:

```text
\ddp
```

It displays currently configured default privilege entries, typically showing:

- Owner/creator role.
- Schema (when per-schema).
- Object type.
- Corresponding `GRANT`/`REVOKE` items.

### 25.1. \\ddp vs. \\dp

| psql command | What it displays |
| --- | --- |
| `\\ddp` | **Default privileges** for future objects |
| `\\dp acl_lab.*` | ACLs/privileges on **existing** objects |
| `\\dn+ acl_lab` | Schema details and access privileges |
| `\\du+` | Roles and related attributes/memberships |
| `\\df+ acl_lab.*` | Existing functions/routines and extra metadata |

Commands beginning with a backslash are **`psql` meta-commands**, not standard SQL. Run them in `psql`, not over JDBC as SQL statements.

### 25.2. Why Look at Both \\ddp and \\dp?

A default policy may be completely accurate while existing tables—created **before** the policy or by a **different role**—still have the wrong ACLs.

### 25.3. Never Draw Conclusions from \\ddp Alone

You must evaluate:

- Both global and per-schema entries.
- The creator role.
- The object type.
- `PUBLIC` and role memberships.
- Each individual object's actual ACL.

## 26. Querying the pg_default_acl Catalog

PostgreSQL stores default privilege entries in the `pg_default_acl` catalog.

```sql
SELECT
    pg_get_userbyid(d.defaclrole) AS creator_role,
    CASE
        WHEN d.defaclnamespace = 0::oid THEN '<global>'
        ELSE d.defaclnamespace::regnamespace::text
    END AS scope,
    d.defaclobjtype AS object_type_code,
    d.defaclacl AS acl_items
FROM pg_default_acl AS d
ORDER BY creator_role, scope, object_type_code;
```

### 26.1. Column Meanings

- `defaclrole`: creator role the policy belongs to.
- `defaclnamespace`: schema OID, or `0` for global entries.
- `defaclobjtype`: object-type code, such as relation, sequence, function, type, or schema.
- `defaclacl`: the ACL items.

### 26.2. Do Not Assume the Catalog Has Rows for Built-In Defaults

If a role has never had custom default ACLs configured, there is no entry for it in `pg_default_acl`. PostgreSQL also applies **built-in initial privileges** by object type.

Therefore:

```text
No pg_default_acl row
    DOES NOT mean
nobody has privileges on new objects.
```

In particular, remember default `PUBLIC` `EXECUTE` on functions and `PUBLIC` `USAGE` on types in standard configurations.

### 26.3. Catalog Queries Are Read-Only Observation

Never `UPDATE pg_default_acl` manually with SQL. Always use PostgreSQL's supported `ALTER DEFAULT PRIVILEGES` DDL.

## 27. Decoding ACLs with aclexplode

ACL items such as `role=r/owner` can be hard to read. PostgreSQL provides `aclexplode` to unpack each privilege:

```sql
SELECT
    pg_get_userbyid(d.defaclrole) AS creator_role,
    CASE
        WHEN d.defaclnamespace = 0::oid THEN '<global>'
        ELSE d.defaclnamespace::regnamespace::text
    END AS scope,
    d.defaclobjtype,
    CASE
        WHEN a.grantee = 0::oid THEN 'PUBLIC'
        ELSE pg_get_userbyid(a.grantee)
    END AS grantee,
    a.privilege_type,
    a.is_grantable
FROM pg_default_acl AS d
CROSS JOIN LATERAL aclexplode(d.defaclacl) AS a
ORDER BY creator_role, scope, grantee, a.privilege_type;
```

### 27.1. Why Does Grantee 0 Represent PUBLIC?

In PostgreSQL's ACL representation, OID `0` denotes `PUBLIC` in privilege contexts.

### 27.2. What Is is_grantable?

Distinguishes the right to execute an operation from the right to **re-grant** it to others. Grants with `WITH GRANT OPTION` can be delegated onward under PostgreSQL privilege rules.

### 27.3. Do Not Check Only One Entry

A role can receive privileges from:

- Direct `GRANT`s.
- One or more group roles.
- `PUBLIC`.
- Ownership.

When assessing effective object permissions, `has_*_privilege` and testing as the actual role are usually clearer than reading a single ACL item.

## 28. Checking Current Privileges with has_*_privilege

Useful SQL functions:

```sql
SELECT
    has_schema_privilege(
        'acl_reader', 'acl_lab', 'USAGE'
    ) AS can_use_schema,
    has_table_privilege(
        'acl_reader', 'acl_lab.orders', 'SELECT'
    ) AS can_select_table,
    has_sequence_privilege(
        'acl_writer', 'acl_lab.invoice_no_seq', 'USAGE'
    ) AS can_use_sequence,
    has_function_privilege(
        'acl_reader', 'acl_lab.calculate_tax(numeric)', 'EXECUTE'
    ) AS can_execute_function,
    has_type_privilege(
        'acl_reader', 'acl_lab.positive_money', 'USAGE'
    ) AS can_use_type;
```

### 28.1. TRUE Does Not Guarantee Every Query Succeeds

For instance, `has_table_privilege(..., 'SELECT') = TRUE`:

- Does not check schema `USAGE`.
- Says nothing about RLS row visibility.
- Says nothing about locks, constraints, function permissions inside expressions, or other policies.

### 28.2. Role Memberships Can Grant Privileges Indirectly

Privilege functions account for effective rights via memberships and `PUBLIC` under active rules. Thus, not finding a direct `GRANT` does not mean a role lacks access.

### 28.3. When Objects Do Not Exist

If an object name is wrong, name-based calls can raise an error rather than returning `FALSE`. Verify that the schema/object actually exists in the target database before checking privileges.

## 29. Viewing Object ACLs in pg_class and Other Catalogs

For tables, views, and sequences:

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    c.relkind,
    pg_get_userbyid(c.relowner) AS owner_role,
    c.relacl
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname IN ('acl_lab', 'acl_else')
ORDER BY n.nspname, c.relname;
```

### 29.1. NULL relacl Does Not Mean Nobody Has Privileges

When no custom ACL has been set, `relacl` can be `NULL` and PostgreSQL applies built-in defaults based on object kind and ownership. Understand these semantics before writing audits.

### 29.2. Distinguishing Relation Types

Common `relkind` codes:

- `r`: ordinary table.
- `p`: partitioned table.
- `v`: view.
- `m`: materialized view.
- `S`: sequence.
- `f`: foreign table.

This helps identify which objects in a schema belong in a given `GRANT` policy.

### 29.3. Function ACLs Live in pg_proc

`pg_class.relacl` does not store function ACLs. Functions live in `pg_proc`, with `proacl` alongside signature and owner info.

```sql
SELECT
    p.oid::regprocedure AS function_signature,
    pg_get_userbyid(p.proowner) AS owner_role,
    p.proacl
FROM pg_proc AS p
JOIN pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE n.nspname = 'acl_lab'
ORDER BY function_signature::text;
```

## 30. Privileges on New Tables from CREATE TABLE AS

A migration may create a table using:

```sql
SET ROLE acl_owner;

CREATE TABLE acl_lab.order_snapshot AS
SELECT order_id, customer_name, net_amount
FROM acl_lab.orders;

RESET ROLE;
```

This is still a **new table created by `acl_owner` in `acl_lab`**, so default table privileges apply at `CREATE` time.

### 30.1. Source Data Privileges Differ from Target Table Privileges

The role running `CREATE TABLE AS SELECT` needs read access on the source and `CREATE` in the destination schema. Once created, the target object gets its own ACL.

### 30.2. Copied Data Does Not Carry Over the Source Table's ACL

Copying rows into a new table does not "clone the source table's privileges." The new ACL is initialized from ownership, built-in defaults, and the creator's default policy.

### 30.3. Snapshots Containing Sensitive Data

If a schema has a per-schema default `SELECT` for all new tables, a temporary snapshot containing sensitive data immediately receives a reader grant. Consider a **dedicated schema for sensitive staging/temp tables** or a separate creator role instead of treating default `SELECT` as harmless.

## 31. New Views and Verifying Runtime Privileges

A view is typically created with:

```sql
SET ROLE acl_owner;

CREATE VIEW acl_lab.order_names AS
SELECT order_id, customer_name
FROM acl_lab.orders;

RESET ROLE;
```

A default `GRANT SELECT ON TABLES TO acl_reader` on new views is not a guarantee that all `SELECT` queries against the view share identical security behavior.

### 31.1. Privileges on a View's Underlying Tables

In PostgreSQL, permissions on relations referenced by a view depend on how the view is defined and checked. Default views typically use owner-based semantics for underlying relations; the `security_invoker` option in supported versions checks permissions/RLS as the invoker.

### 31.2. RLS and Views

A default `GRANT SELECT` on a view can open another access path to base-table data under view semantics. Before letting reader `SELECT` every new view, review:

- Does the view expose sensitive columns?
- Who owns the view?
- Is `security_invoker` set?
- Under which role will base-table RLS apply?
- Do any functions inside the view use `SECURITY DEFINER`?

### 31.3. Never Use Default GRANT as Automatic Security Approval

Creating a new view does not mean it has passed security review. Many organizations require **explicit per-view grants** for sensitive data marts instead of schema-wide default `SELECT`.

## 32. Materialized Views, Foreign Tables, and Similar Objects

PostgreSQL has multiple relation-category objects that `ON TABLES` syntax can affect depending on DDL and object type:

- Ordinary tables.
- Views.
- Materialized views.
- Foreign tables.
- Partitioned tables and partitions.

### 32.1. Do Not Equate Object Privileges with Data-Source Access

A foreign table may depend on a foreign server, user mapping, and additional rights. A materialized view stores physical results and has its own `REFRESH` mechanics.

A default `GRANT SELECT` on those objects **does not automatically solve underlying FDW rights, refresh permissions, ownership, or security**.

### 32.2. Why Test Every Object Kind?

If migrations create tables, views, materialized views, and foreign tables, verify actual ACLs after `CREATE` for the **exact object types used** on your PostgreSQL version—never rely on assuming "everything behaves like a table."

## 33. Partitioned Tables and Partitions

Suppose an application creates a partitioned table:

```sql
CREATE TABLE app.events (
    event_id bigint,
    occurred_at timestamptz NOT NULL,
    payload jsonb
) PARTITION BY RANGE (occurred_at);
```

Then creates partitions:

```sql
CREATE TABLE app.events_2027_01
PARTITION OF app.events
FOR VALUES FROM ('2027-01-01 00:00:00+00')
TO ('2027-02-01 00:00:00+00');
```

### 33.1. Default Privileges Follow the Creator at CREATE Time

A partition is a created relation, so default privileges for its creator role and target schema apply.

### 33.2. Access Through Parent vs. Directly on Partition

Privilege checks when querying/writing through the partitioned parent differ semantically from a user querying a child partition directly by name. Never assume `GRANT SELECT ON parent` always equals `GRANT SELECT ON every partition` across all access paths.

### 33.3. Retention Jobs May Need Different DDL Rights

Jobs creating, attaching, dropping, or detaching partitions need appropriate owner/schema/DDL rights. Default `SELECT, INSERT, UPDATE` does not permit `ALTER TABLE ... ATTACH PARTITION` or dropping partitions.

### 33.4. Audit After Partition Creation

In systems creating daily/monthly partitions automatically:

- Verify the job's creator role.
- Verify partition schema and owner.
- Verify table ACLs if applications query partitions directly.
- Verify RLS, ownership, and queries through the parent.

## 34. Column Privileges: Never Expect ALTER DEFAULT PRIVILEGES to Replace Them

PostgreSQL supports column-level `GRANT`s on existing tables:

```sql
GRANT SELECT (order_id, customer_name)
ON acl_lab.orders
TO acl_reader;
```

However, default `GRANT SELECT ON TABLES` grants privileges at the **table object** level; it cannot express a policy like "only columns A and B of every future table."

### 34.1. When Sensitive Columns Exist

Consider:

- Splitting tables/schemas by domain.
- Creating views exposing only permitted columns.
- Granting specific column-level privileges after `CREATE`.
- Enforcing sensitive-data policies at both application and database layers.

### 34.2. Why Can Default Table SELECT Be Too Broad?

Today `orders` has only `customer_name`; tomorrow a migration adds `personal_id`. If reader holds table-level `SELECT`, read access on the new column may exceed original intent.

Default table grants must be reviewed alongside schema-change reviews, not solely at initial table creation.

## 35. WITH GRANT OPTION and Onward Delegation

A default privilege `GRANT` can include `WITH GRANT OPTION` when supported by the privilege syntax:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE app_owner
    IN SCHEMA app
GRANT SELECT ON TABLES TO app_reader
WITH GRANT OPTION;
```

Meaning: the recipient role is permitted to grant `SELECT` onward to other roles under PostgreSQL privilege rules.

### 35.1. Principle of Least Privilege

Runtime applications rarely **need the ability to re-grant privileges**. Avoid `WITH GRANT OPTION` in default policies unless there is a clear delegation use case.

### 35.2. Grant Option Differs from Membership Admin Option

Grant options on object privileges are not the same as role/membership administration rights. Do not confuse them with `ADMIN OPTION` or `CREATEROLE`.

### 35.3. PUBLIC and Grant Options

Do not design onward delegation for `PUBLIC` the way you would for a dedicated role. Check PostgreSQL's rules and prefer granting to managed named roles.

## 36. Default Privileges Do Not Automatically Grant CREATE on Existing Schemas

Many people expect:

```sql
ALTER DEFAULT PRIVILEGES FOR ROLE app_owner
IN SCHEMA app GRANT SELECT ON TABLES TO app_reader;
```

to let `app_reader` create tables itself. That is completely wrong.

### 36.1. Who Can CREATE TABLE?

Depends on schema ownership, memberships, and `CREATE ON SCHEMA`. For example:

```sql
GRANT CREATE ON SCHEMA app TO migration_role;
```

grants the migration role permission to **create objects in the existing schema**—not a default grant on future tables.

### 36.2. Broad CREATE Privileges Fragment Creator Roles

Granting `CREATE` to multiple roles in the same schema causes new tables to have different owners and receive different default ACLs.

This is another reason to use a unified migration owner role and avoid granting `CREATE` broadly to runtime roles.

### 36.3. CREATEROLE and Schema CREATE Are Different

System-wide role-creation power (`CREATEROLE`) is not permission to create tables in a schema. Operations teams must govern these two privileges independently.

## 37. A Sound Role Design for a PostgreSQL Application

Example:

```text
deployment_login
   |
   +-- SET ROLE app_ddl_owner during migrations
           |
           +-- CREATE TABLE / VIEW / FUNCTION in app schema

app_reader (runtime)
   |
   +-- USAGE ON SCHEMA app
   +-- SELECT ON approved tables/views

app_writer (runtime)
   |
   +-- USAGE ON SCHEMA app
   +-- SELECT, INSERT, UPDATE (and DELETE if needed)
   +-- USAGE on sequences when nextval is needed

app_function_caller
   |
   +-- EXECUTE only on approved routines
```

### 37.1. Advantages

- Migrations have a consistent object-creating identity.
- Runtime needs no `CREATE`/`DROP TABLE`.
- Default policies have clear scopes.
- Privilege auditing is much simpler.
- Risk of creating objects with unintended owners drops.

### 37.2. Never Over-Privilege app_writer

A runtime user that only creates new orders does not need:

```sql
DELETE
TRUNCATE
REFERENCES
TRIGGER
CREATE ON SCHEMA
```

Use separate roles and workflows for administrative operations.

### 37.3. Never Use a NOLOGIN Owner as a Shared Password

`NOLOGIN` roles exist to own objects, while login credentials belong to service accounts with separate policies. Never embed secrets in migration SQL or documentation files.

## 38. SET ROLE and Migration Scripts

A pipeline can execute:

```sql
-- Session logged in as deployment_login
SET ROLE app_ddl_owner;

-- ALTER DEFAULT PRIVILEGES + CREATE TABLE + CREATE FUNCTION...

RESET ROLE;
```

### 38.1. Choose a Consistent Current Role

When DDL runs under `app_ddl_owner`, `FOR ROLE app_ddl_owner` policies apply. If a pipeline forgets `SET ROLE` in one script, objects end up owned by `deployment_login` and miss the right ACLs.

### 38.2. Pre-Migration Check

```sql
SELECT current_user, current_role, session_user;
```

Add an assertion in your migration tool or entrypoint to abort if `current_role` is not the expected owner.

### 38.3. SET ROLE Is Not Inherently Harmless

`SET ROLE` capability depends on role memberships and privileges. Allowing `deployment_login` to `SET ROLE` to a superuser or an owner holding excessive unrelated data can create unnecessary privilege escalation.

### 38.4. The Active Role Matters More Than the Migration Filename

A file named `2027_create_table_as_owner.sql` does not determine the owner; PostgreSQL uses the actual session role and privileges at `CREATE` time.

## 39. Safely Revoking Default Privileges

If the business decides to **stop auto-granting `UPDATE` to writer on future tables**:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
    IN SCHEMA acl_lab
REVOKE UPDATE ON TABLES FROM acl_writer;
```

### 39.1. What Changes?

Tables created afterward by `acl_owner` in `acl_lab` no longer receive automatic `UPDATE` **because the per-schema rule was removed**, unless a global default or another grant exists.

### 39.2. What Does Not Change?

Tables created before the `REVOKE` keep their existing ACLs. You still need:

```sql
REVOKE UPDATE ON acl_lab.orders FROM acl_writer;
```

if you want to remove the privilege on existing tables.

### 39.3. Do Not Confuse Per-Schema REVOKE with Global

If a global default still grants `UPDATE` to writer, a per-schema `REVOKE` will not block that privilege on new objects.

### 39.4. Why Can a Default REVOKE Break Applications?

If a service needs to update a newly added table yet default `UPDATE` was revoked, code deployment may succeed while runtime requests fail with `42501`. Sequence privilege changes and code deployments properly.

## 40. Granting Privileges to Only Selected New Functions

Default `GRANT`s have granularity by **object kind + creator + schema**, not per individual function signature.

Suppose schema `app` contains both:

- `app.public_format_name(text)`: safe helper for readers.
- `app.approve_refund(bigint)`: function with side effects requiring a specific business role.

If a default sets:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE app_owner
    IN SCHEMA app
GRANT EXECUTE ON FUNCTIONS TO app_reader;
```

then **every new function created by `app_owner` in `app`** automatically grants `EXECUTE` to reader, including sensitive new functions if an author forgets to verify post-migration.

### 40.1. Better Design

- Separate schemas `api_read` and `api_write_privileged` with dedicated owners and default ACLs.
- Global `REVOKE` of `PUBLIC` `EXECUTE` for the appropriate creator.
- Explicit `GRANT EXECUTE` only on approved functions.
- Use `SECURITY DEFINER` sparingly; restrict `EXECUTE` to authorized roles.

### 40.2. Default Privileges Are Not a Function-Name Allowlist

When you need an exact allowlist of callable functions, explicit per-function `GRANT`s combined with catalog checks are far clearer than a broad default grant.

## 41. SECURITY DEFINER and Future EXECUTE Privileges

A `SECURITY DEFINER` function normally executes with the function owner's privileges per PostgreSQL rules, not merely the caller's.

Sensitive function example:

```sql
CREATE FUNCTION app.approve_refund(p_refund_id bigint)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    -- Skeleton only: requires business authorization checks, transaction handling,
    -- search_path pinning, RLS, idempotency, auditing, and real constraints.
    NULL;
END;
$$;
```

### 41.1. Why Can Default PUBLIC EXECUTE Be Dangerous?

An ordinary role can invoke a function running with the owner's stronger privileges whenever it holds `EXECUTE` and schema access. If the function lacks validation/authorization, callers can trigger unintended actions.

### 41.2. Hardening

In a secure design:

- Never allow `PUBLIC` `EXECUTE` on sensitive functions.
- Grant `EXECUTE` only to named roles that need it.
- Pin a trusted `search_path` inside `SECURITY DEFINER`.
- Use schema-qualified references.
- Audit permissions and test as a role lacking base-table rights.

### 41.3. Global PUBLIC REVOKE Helps, But Is Not Enough

Even without `PUBLIC` `EXECUTE`, an overly broadly granted named role can still call the function. Controlling who receives `GRANT`s and authorization checks inside the function remains critical.

## 42. RLS: SELECT Privilege Does Not Equal Seeing Every Row

Suppose table `app.orders` has RLS enabled, allowing reads only for the current tenant's orders.

A default:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE app_owner
    IN SCHEMA app
GRANT SELECT ON TABLES TO app_reader;
```

does not disable policies on the table.

### 42.1. Coordinating Layers

| Layer | Responsibility |
| --- | --- |
| Schema `USAGE` | Permits namespace access |
| Table `SELECT` | Permits running read queries |
| RLS `USING` | Restricts which rows are visible |
| View semantics | Can change which role is checked for underlying relation privileges/RLS |
| Application authorization | Enforces user identity, scope, and returned data |

### 42.2. Owner/BYPASSRLS

A role that is the table owner or holds `BYPASSRLS` may not be constrained by RLS like an ordinary role under PostgreSQL semantics. Always test using **the actual app role**, not just the owner or superuser.

### 42.3. Never Treat Default Privileges as Tenant Isolation

Granting `SELECT` on tables does not create a `tenant_id = current_tenant` policy. Design RLS, predicates, and privileges separately.

## 43. PostgreSQL Role Inheritance and Default Creators

A role can receive `SELECT` via membership depending on membership options and role attributes.

However, **effective privileges from membership** differ from **which default ACL is chosen at object creation**.

### 43.1. Example

```text
acl_deployer is a member of acl_owner

acl_deployer may inherit CREATE via membership.
acl_deployer runs CREATE TABLE directly.

Owner of new table: acl_deployer.
Default ACLs checked for creator acl_deployer.
Does NOT automatically use acl_owner's default ACLs.
```

### 43.2. SET ROLE Changes the Creator Identity

If deployer runs `SET ROLE acl_owner` before `CREATE`, then the creator role for the new object is `acl_owner` in that context, and the owner's default policy applies.

### 43.3. Do Not Confuse GRANT owner TO deployer with Default GRANT TO reader

Two completely different `GRANT`s:

```sql
GRANT acl_owner TO acl_deployer;
```

manages role membership, whereas:

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
GRANT SELECT ON TABLES TO acl_reader;
```

manages initial ACLs on future tables.

## 44. Object Ownership Drift

A system may drift into:

```text
app.orders         owner app_owner
app.invoices       owner deploy_login
app.events         owner app_owner
app.audit_log      owner emergency_admin
```

Even though all objects sit in the same schema, they may have received **different** default privileges at creation time.

### 44.1. Ownership Audit Query

```sql
SELECT
    n.nspname AS schema_name,
    c.relname,
    c.relkind,
    pg_get_userbyid(c.relowner) AS owner_name
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'acl_lab'
  AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
ORDER BY c.relkind, c.relname;
```

### 44.2. Why Is ALTER OWNER Not Enough?

Changing the owner after `CREATE` does not reapply the new owner's default policy. Inspect actual ACLs and run direct grants/revokes as needed.

### 44.3. Guarding the Pipeline

Assert `current_role` before DDL, inspect new object owners after DDL, and fail the step on unexpected drift.

## 45. Default Privileges Across Multiple Schemas in One Deployment

Suppose you have:

```text
schema api_read
schema operations
schema internal_audit
```

One owner creates objects in all three schemas, yet permissions must differ:

- `api_read`: reader gets `SELECT`.
- `operations`: writer gets `SELECT`/`INSERT`/`UPDATE`.
- `internal_audit`: only an audit role gets `SELECT`.

### 45.1. Per-Schema Configuration

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE app_owner
    IN SCHEMA api_read
GRANT SELECT ON TABLES TO app_reader;

ALTER DEFAULT PRIVILEGES
    FOR ROLE app_owner
    IN SCHEMA operations
GRANT SELECT, INSERT, UPDATE ON TABLES TO app_writer;

ALTER DEFAULT PRIVILEGES
    FOR ROLE app_owner
    IN SCHEMA internal_audit
GRANT SELECT ON TABLES TO audit_reader;
```

These use hypothetical schema/role names. Do not run verbatim without matching objects, roles, and privileges.

### 45.2. Avoid Global SELECT When an Audit Schema Exists

A global default `SELECT` for `app_reader` could expose newly created audit tables. When strict separation is required, avoid broad globals or use separate creator roles.

### 45.3. Domain-Scoped Owner Roles

In large systems, instead of one owner across every schema, domain-specific owner roles limit blast radius if a migration role is misused.

## 46. Future-Object Privileges Are Not an Auto-Sync Service

No background job periodically "rescans all tables" just because you used `ALTER DEFAULT PRIVILEGES`. Default privileges are **applied at `CREATE` time**.

### 46.1. Post-CREATE Changes

If a table is:

- Renamed.
- Moved to another schema.
- Transferred to a new owner.
- Directly modified via `GRANT`/`REVOKE`.

the table's own ACL remains managed state. Default policies do not automatically reapply whenever a name, schema, or owner changes.

### 46.2. Monitoring Privilege Drift

Periodically or after each deployment, compare:

- Expected creator/owner.
- Expected schema.
- Actual object ACLs.
- Effective privileges for reader/writer.
- New functions added in migrations.

### 46.3. Event Triggers Do Not Replace Default ACL Knowledge

You can build DDL controls with event triggers or pipeline policy gates in specialized cases, but those are separate mechanisms with their own operational and privilege risks. Design clear role and default ACL structures first.

## 47. Modifying Default Privileges Inside a Transaction

PostgreSQL supports transactions for many DDL and privilege-management commands.

Example:

```sql
BEGIN;

ALTER DEFAULT PRIVILEGES
    FOR ROLE acl_owner
    IN SCHEMA acl_lab
GRANT SELECT ON TABLES TO acl_reader;

SET ROLE acl_owner;

CREATE TABLE acl_lab.created_in_migration (
    id integer PRIMARY KEY,
    payload text
);

RESET ROLE;

COMMIT;
```

### 47.1. Why Is This Beneficial?

If the migration fails before `COMMIT`, DDL/ACL changes in the same transaction roll back together under PostgreSQL semantics, preventing half-deployed permission states.

### 47.2. Exceptions Can Exist

Not every PostgreSQL administrative command can run inside a transaction block, and external/sequence side effects behave differently. For specific DDL, verify against your version and migration tool.

### 47.3. SET ROLE Inside Migrations

If your migration tool manages transactions, role switching, and connection pooling itself, verify how it preserves or resets roles instead of nesting transactions arbitrarily.

## 48. Revoking on Existing Functions and Default PUBLIC

Suppose today you discover a sensitive function was created with `PUBLIC` `EXECUTE`.

Two independent actions:

```sql
-- 1. For future functions created by owner:
ALTER DEFAULT PRIVILEGES
    FOR ROLE app_owner
REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

-- 2. For an already-existing function:
REVOKE EXECUTE
ON FUNCTION app.approve_refund(bigint)
FROM PUBLIC;
```

### 48.1. Revoking Across an Entire Schema

If needed and authorized:

```sql
REVOKE EXECUTE
ON ALL FUNCTIONS IN SCHEMA app
FROM PUBLIC;
```

This is a **major change** that can break multiple applications. Never run it before inventorying callers, reviewing `SECURITY DEFINER` routines, and planning a rollout.

### 48.2. Safe Ordering

1. Identify functions and callers.
2. Grant explicit `EXECUTE` to valid roles.
3. Revoke `PUBLIC` `EXECUTE` on existing functions.
4. Configure global default `REVOKE` for the creator of future functions.
5. Verify under app roles and monitor for `42501` errors.

### 48.3. Never Infer Permissions from Role Names

A role named `readonly_user` could still hold `PUBLIC` `EXECUTE` on a data-modifying function if ACLs allow it. A role name is not a security policy.

## 49. Default Privileges with Extensions and Migration Tools

Not all DDL is executed the same way:

- A migration tool may connect via a deploy login distinct from the owner.
- Extension installation can create many objects.
- A maintenance job creates partitions.
- A batch task creates temporary/staging tables.
- A manual hotfix script patches production.

### 49.1. Verify the Actual Creator

For objects created by tools or migrations, verify the effective role at `CREATE` time and ownership afterward. Never assume every object in a schema receives the schema owner's default ACLs.

### 49.2. Test After Extensions or Migrations

If an extension or script creates new functions, they may have different permissions than functions created manually by your standard role. Inspect actual ACLs, `PUBLIC` grants, and who can call sensitive entrypoints.

### 49.3. Staging Schemas Are Not Automatically Safe

A staging table holding personal data can receive default `SELECT` if its creator and schema match a broad policy. Consider a separate schema and tighter roles.

## 50. Backing Up and Restoring Privileges

When backing up and restoring PostgreSQL, you need more than table data:

- Object owners.
- Current `GRANT`/`REVOKE` ACLs.
- Default ACL policies.
- Roles and memberships.
- Schema permissions.
- RLS policies and function privileges.

### 50.1. pg_dump Is Not a Cluster-Wide Role Backup

A single database dump records DDL and object ACLs, whereas roles are cluster-level objects that must be prepared/migrated appropriately. Restoring without the matching creator or owner roles can error or alter ownership depending on restore options.

### 50.2. Never Restore and Test Only SELECT as a Superuser

Verify:

1. `\\ddp` on the target.
2. Creator/owner roles of tables.
3. Reader/writer permissions on existing objects.
4. Creating a test table/function in the target schema and confirming default ACLs.
5. RLS and `SECURITY DEFINER` behavior.

### 50.3. Backup Tool Flags Can Change Outcomes

Dump/restore flags that omit ownership or privileges can leave a restored environment configured differently from production. Check exact tool flags and operational runbooks.

## 51. Changing Default Policy When a Schema Already Has Thousands of Objects

An anti-pattern is running:

```sql
ALTER DEFAULT PRIVILEGES ...
```

and thinking "all permissions are now fixed."

### 51.1. Inventory First

List:

- Existing tables, views, and sequences.
- Functions and signatures.
- Types and domains.
- Owners.
- ACLs and `PUBLIC` grants.
- Role memberships.

### 51.2. Two-Phase Migration

First define the **target permission state**. Then:

1. Update default policies for future objects.
2. Grant/revoke privileges on existing objects.
3. Verify each object type and role.
4. Run smoke tests.

### 51.3. Read-Only Permissions Are Not Just SELECT

An application may require schema `USAGE`, function `EXECUTE`, type `USAGE`, and sequence `SELECT` for `currval()`/metadata reads. Inspect the real **SQL call graph**.

## 52. Diagnosing 42501 insufficient_privilege

When an application receives:

```text
SQLSTATE 42501
permission denied for table new_orders
```

walk through the checklist in order.

### 52.1. Which Object Actually Raised the Error?

It is not always the top-level table. It could be:

- `permission denied for schema app`.
- `permission denied for sequence ...`.
- `permission denied for function ...`.
- `permission denied for relation ...`.

### 52.2. Who Is Executing?

```sql
SELECT current_user, current_role, session_user;
```

In connection pools, verify exact login identity and any `SET ROLE` applied.

### 52.3. Who Currently Owns the Object?

Check `pg_class.relowner`/`pg_proc.proowner` and the schema.

### 52.4. What Are the Effective Privileges?

```sql
SELECT
    has_schema_privilege('app_reader','app','USAGE'),
    has_table_privilege('app_reader','app.new_orders','SELECT');
```

### 52.5. Does the Default Policy Match the Creator?

Inspect `\\ddp` and `pg_default_acl`:

- Is there an entry `FOR ROLE deployer` or only `FOR ROLE app_owner`?
- Is `IN SCHEMA app` present?
- Are there unintended global grants?
- Was the object created before the policy?

### 52.6. Fix the Right Layer

- Missing schema `USAGE` -> appropriate `GRANT USAGE ON SCHEMA`.
- Missing permission on existing object -> direct `GRANT`.
- Wrong future policy -> `ALTER DEFAULT PRIVILEGES` for the exact creator/schema.
- Runtime missing sequence/function privilege -> adjust on that exact object kind.
- Unexpected object owner -> fix the pipeline and remediate existing ACLs/ownership separately.

## 53. JDBC: Detecting Permission Errors After Migrations

A Java service may catch a `SQLException` when querying a new table.

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT order_id, customer_name " +
        "FROM app.new_orders WHERE order_id = ?")) {
    ps.setLong(1, 101L);
    try (ResultSet rs = ps.executeQuery()) {
        // Process results.
    }
} catch (SQLException e) {
    if ("42501".equals(e.getSQLState())) {
        // Missing privilege: safely log object/role/request context,
        // return an appropriate error, never auto-grant from the app.
    }
    throw e;
}
```

### 53.1. Do Not Leak Full Database Details to Clients

Error messages can reveal schema names, table names, or internal structures. Map errors according to your API contract and logging policy.

### 53.2. Never Auto-GRANT from the Runtime Application

An application should never hold broad ACL-admin rights so that upon seeing `42501` it grants itself more permissions. That is a privilege-escalation anti-pattern.

### 53.3. Test Using the Exact Role

Integration tests should connect under the real application role or an equivalent-privilege role, not just owner or superuser.

## 54. Post-Migration Smoke Test for Newly Created Objects

A pipeline can assert invariants:

```sql
SELECT
    has_schema_privilege('acl_reader','acl_lab','USAGE')
        AS reader_schema_usage,
    has_table_privilege('acl_reader','acl_lab.orders','SELECT')
        AS reader_orders_select,
    has_table_privilege('acl_writer','acl_lab.orders','INSERT')
        AS writer_orders_insert,
    has_sequence_privilege(
        'acl_writer','acl_lab.invoice_no_seq','USAGE'
    ) AS writer_sequence_usage,
    has_function_privilege(
        'acl_reader','acl_lab.calculate_tax(numeric)','EXECUTE'
    ) AS reader_function_execute;
```

### 54.1. When Must the Test Fail?

In CI/deployment gates, if any required privilege evaluates to `FALSE`, fail the pipeline rather than merely logging a warning.

### 54.2. Also Assert What Must NOT Be Permitted

Example:

```sql
SELECT
    NOT has_table_privilege(
        'acl_reader','acl_lab.orders','DELETE'
    ) AS reader_not_allowed_delete,
    NOT has_function_privilege(
        'acl_writer','acl_lab.calculate_tax(numeric)','EXECUTE'
    ) AS writer_not_allowed_execute;
```

A strong security smoke test verifies both required grants **and forbidden privileges**.

### 54.3. Test RLS via Real SELECT Queries

`has_table_privilege = TRUE` does not prove RLS filters rows properly. Run real data tests under appropriate tenants and roles.

## 55. Building an Automated Check for Default Policies

Example querying `pg_default_acl` to verify a creator has expected policy entries:

```sql
SELECT
    pg_get_userbyid(d.defaclrole) AS creator,
    CASE
        WHEN d.defaclnamespace = 0::oid THEN '<global>'
        ELSE d.defaclnamespace::regnamespace::text
    END AS schema_scope,
    a.privilege_type,
    pg_get_userbyid(a.grantee) AS grantee
FROM pg_default_acl AS d
CROSS JOIN LATERAL aclexplode(d.defaclacl) AS a
WHERE pg_get_userbyid(d.defaclrole) = 'acl_owner'
  AND d.defaclobjtype = 'r'
  AND a.grantee <> 0::oid
ORDER BY schema_scope, grantee, a.privilege_type;
```

### 55.1. Why Checking Entries Alone Is Not Enough

A default entry can exist while:

- Migrations created tables under a different role.
- Tables were created before the entry existed.
- Specific objects were revoked after `CREATE`.
- The schema lacks `USAGE`.

Test both the **policy** and **effective privileges on new objects**.

### 55.2. Test with a Real Future Object

In a test database, create a table under the exact creator, assert `SELECT`/`INSERT`, then roll back or drop per policy. This catches semantic mismatches that catalog inspection alone might miss.

## 56. Questions to Answer Before Using DEFAULT PRIVILEGES

1. **Which object type will be created?** Table, sequence, function, type, or schema?
2. **Who actually runs `CREATE`?** Owner role, deployer login, job runner, or administrator?
3. **What is the target schema?** One fixed schema or multiple schemas?
4. **Which privileges are needed?** `SELECT`, `INSERT`, `UPDATE`, `EXECUTE`, `USAGE`?
5. **Which role receives the privileges?** Named role or `PUBLIC`?
6. **Is any global setting overly broad?**
7. **Is there default `PUBLIC` `EXECUTE`/`USAGE` that should be globally revoked?**
8. **Do existing objects need separate `GRANT`/`REVOKE`?**
9. **Are `USAGE ON SCHEMA` and dependent privileges granted?**
10. **Does the app writer need sequence privileges?**
11. **Could new views/functions expose data or escalate privileges?**
12. **Do RLS/`security_invoker`/`SECURITY DEFINER` alter access paths?**
13. **Is the creator role verified during migrations?**
14. **Are privileges tested under the app role after deployment?**
15. **Are disallowed privileges covered by negative tests?**
16. **Is there a rollback plan if a policy change breaks the application?**

## 57. Anti-Patterns and Fixes Table

| Anti-pattern | Consequence | Right approach |
| --- | --- | --- |
| Running `GRANT ON ALL TABLES` only once | New tables lack access | Add default policy for creator |
| Using `ALTER DEFAULT PRIVILEGES` alone | Old tables still lack access | Run `GRANT` on existing objects too |
| Setting defaults for schema owner while deployer `CREATE`s | Policy does not apply | `SET ROLE` owner or set policy for deployer |
| Assuming role membership inherits default ACLs | New objects get wrong ACLs | Determine `current_role` at `CREATE` |
| Per-schema `REVOKE` trying to block global `GRANT` | Privilege is still granted | Fix global policy and apply needed per-schema `GRANT`s |
| Per-schema `REVOKE PUBLIC EXECUTE` to block built-in default | Functions stay broadly callable | Global `REVOKE PUBLIC EXECUTE` |
| `GRANT SELECT ON TABLES` while forgetting schema `USAGE` | Reader still cannot access | `GRANT USAGE ON SCHEMA` |
| `GRANT INSERT ON TABLES` while forgetting sequences | `nextval` may raise permission denied | Grant sequence `USAGE` when needed |
| `GRANT ALL` for runtime | Grants `DELETE`/`TRUNCATE`/DDL beyond need | Least privilege |
| `GRANT WITH GRANT OPTION` for runtime | Can delegate privileges onward | Grant only when genuinely required |
| Default `SELECT` on all new views | Sensitive views may be exposed | Review view security; separate schemas |
| Assuming a role named `readonly` is read-only | `PUBLIC`/other grants still permit actions | Audit effective privileges |
| Using default ACLs in place of RLS | No tenant isolation | Implement RLS/authorization separately |
| Assuming `ALTER OWNER` reapplies default ACLs | Existing ACLs are not recomputed | Inspect and grant/revoke per object |
| Updating PG catalogs directly to edit ACLs | Catalog corruption/unsupported | Use `ALTER DEFAULT PRIVILEGES` |
| Testing as superuser | Masks real permission bugs | Test using the app role |
| Checking only `\\ddp` | Ignores current object ACLs | Check `\\dp` + `has_*_privilege` |
| Checking only `\\dp` | Ignores future object behavior | Check `\\ddp` + test creating an object |
| Manually granting on every new table name each time | Error-prone/migration failures | Configure proper future defaults |
| Splitting permission logic from migrations without tests | Environment drift | Versioned grants + smoke tests |
| Assuming `CREATE OR REPLACE FUNCTION` reapplies defaults | Existing object ACL does not reset | Manage ACLs of existing objects explicitly |
| Leaving `PUBLIC` `EXECUTE` on unreviewed `SECURITY DEFINER` | Privilege escalation risk | Revoke `PUBLIC`, restrict grants, pin `search_path` |
| Adding a sensitive column to a table where reader has `SELECT` | Reader can read the new column | Column/view/schema security review |
| Writing scripts meant for owner while CI runs as login role | Inconsistent ownership | Assert `current_role`/`SET ROLE` |
| Omitting role grants from restore checklists | Restores produce wrong permissions | Verify roles/owners/default ACLs |
| App auto-`GRANT`ing when hitting `42501` | Privilege escalation | Let deployment/DBA update policies |

## 58. Consolidation Exercise: Building a Future-Privilege Policy

In this section, combine three parts: **existing privileges**, **future policies**, and **dependent privileges**.

### 58.1. Requirements

The application has:

- `app_ddl_owner`: owns objects and runs migrations via `SET ROLE`.
- `app_reader`: `SELECT` only on approved public tables/views.
- `app_writer`: `INSERT`/`UPDATE` on business tables and calls to specific sequences.
- `app_api_caller`: `EXECUTE` only on approved API functions.

Schemas:

```text
app_public
app_write
app_internal
```

### 58.2. Namespace Privileges

```sql
GRANT USAGE ON SCHEMA app_public TO app_reader;
GRANT USAGE ON SCHEMA app_write TO app_writer;
GRANT USAGE ON SCHEMA app_public TO app_api_caller;
```

### 58.3. Future Privileges

```sql
ALTER DEFAULT PRIVILEGES
    FOR ROLE app_ddl_owner
    IN SCHEMA app_public
GRANT SELECT ON TABLES TO app_reader;

ALTER DEFAULT PRIVILEGES
    FOR ROLE app_ddl_owner
    IN SCHEMA app_write
GRANT SELECT, INSERT, UPDATE ON TABLES TO app_writer;

ALTER DEFAULT PRIVILEGES
    FOR ROLE app_ddl_owner
    IN SCHEMA app_write
GRANT USAGE ON SEQUENCES TO app_writer;

ALTER DEFAULT PRIVILEGES
    FOR ROLE app_ddl_owner
REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
```

For `app_internal`, do not configure default `SELECT` for any runtime role unless required.

### 58.4. Function APIs

If you do not want every function in `app_public` executable by `app_api_caller`, **avoid** a broad default `GRANT EXECUTE` in that schema; use explicit `GRANT`s for reviewed functions:

```sql
GRANT EXECUTE ON FUNCTION app_public.get_order(bigint)
TO app_api_caller;
```

### 58.5. Past Privileges

For existing objects:

```sql
GRANT SELECT
ON ALL TABLES IN SCHEMA app_public
TO app_reader;

GRANT SELECT, INSERT, UPDATE
ON ALL TABLES IN SCHEMA app_write
TO app_writer;

GRANT USAGE
ON ALL SEQUENCES IN SCHEMA app_write
TO app_writer;
```

These example commands require matching roles/schemas/objects and privileges, and every object should be reviewed before bulk granting.

### 58.6. Verification

Create a new table using `SET ROLE app_ddl_owner` in each schema and verify:

- Reader holds `SELECT` only on intended objects.
- Writer holds appropriate write privileges.
- Nobody automatically receives `SELECT` on `app_internal` from an accidental global policy.
- New functions lack `PUBLIC` `EXECUTE` once the owner is hardened.
- Schema `USAGE`, RLS, and function security are accurate.

## 59. Hands-On PostgreSQL Exercises

Exercises use `acl_lab`, `acl_else`, and the lab roles where appropriate. Run role-creation/privilege commands only with administrative permissions in a test database.

1. **Concept:** explain what default privileges are and why they are non-retroactive.
2. **Classification:** how does `GRANT SELECT ON app.orders` differ from `GRANT ON ALL TABLES IN SCHEMA app`?
3. **Timeline:** sketch T0 `CREATE` old table, T1 `ALTER DEFAULT`, T2 `CREATE` new table, T3 `REVOKE` default, and identify which tables are affected.
4. **Schema:** why is `GRANT SELECT ON TABLES` insufficient without `USAGE ON SCHEMA`?
5. **Database:** does database `CONNECT` belong to `ALTER DEFAULT PRIVILEGES ON TABLES`?
6. **Lab roles:** create four `NOLOGIN` roles for owner/reader/writer/deployer.
7. **Lab schemas:** create `acl_lab` and `acl_else` owned by `acl_owner`.
8. **Namespace:** `GRANT USAGE ON SCHEMA acl_lab` to reader/writer.
9. **Old table:** create `acl_lab.before_default` before setting default policies and check reader `SELECT`.
10. **FOR ROLE:** distinguish the creator role position from the grantee role position in `ALTER DEFAULT PRIVILEGES`.
11. **Table defaults:** grant default `SELECT` to reader with `IN SCHEMA acl_lab`.
12. **Writer defaults:** grant default `SELECT`/`INSERT`/`UPDATE` to writer in `acl_lab`.
13. **New table:** create `acl_lab.orders` under `SET ROLE acl_owner`.
14. **Effective privileges:** use `has_table_privilege` to verify reader `SELECT` and writer `INSERT`.
15. **Non-retroactive:** prove `before_default` did not receive `SELECT` just because the default policy was added.
16. **GRANT existing:** grant `SELECT` directly on `before_default`.
17. **ALL TABLES:** explain `GRANT SELECT ON ALL TABLES IN SCHEMA` and its ownership limitations.
18. **View:** create `order_overview` under `acl_owner` and verify reader's ACL.
19. **VIEW security:** explain the risk of default `SELECT` on a newly created sensitive view.
20. **INSERT:** run `INSERT` as `acl_writer`, without using owner.
21. **RETURNING:** why can `INSERT ... RETURNING` require additional `SELECT` privilege?
22. **Sequence:** configure default `USAGE, SELECT ON SEQUENCES` for writer.
23. **New sequence:** create `invoice_no_seq` and test `has_sequence_privilege`.
24. **nextval:** run `nextval` as writer and explain why sequence increments do not roll back.
25. **SERIAL vs. IDENTITY:** contrast sequence privilege needs when inserting with explicit `nextval`.
26. **PUBLIC EXECUTE:** explain default `PUBLIC` `EXECUTE` on functions and its risks.
27. **Global REVOKE:** configure default `REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC` for `acl_owner`.
28. **Per-schema function:** `GRANT EXECUTE ON FUNCTIONS TO acl_reader` in `acl_lab`.
29. **New function:** create `calculate_tax(numeric)` and confirm reader has `EXECUTE` while writer does not.
30. **Per-schema REVOKE:** explain why `REVOKE EXECUTE FROM PUBLIC` scoped only to `acl_lab` fails to remove global `PUBLIC` `EXECUTE`.
31. **Existing function:** show how to `REVOKE EXECUTE` on an already-existing function.
32. **Signature:** use `has_function_privilege` with exact function signatures when overloads exist.
33. **TYPES:** create domain `positive_money` and inspect its existing `USAGE`.
34. **Default types:** set `GRANT USAGE ON TYPES` for a named role; do objects created before the policy change?
35. **PUBLIC TYPES:** explain global `REVOKE USAGE ON TYPES FROM PUBLIC` and compatibility risks.
36. **SCHEMAS:** set default `USAGE ON SCHEMAS` for reader, then create `acl_future`.
37. **No nested schemas:** why is `IN SCHEMA` invalid with default privileges `ON SCHEMAS`?
38. **Global vs. per-schema:** set global `SELECT` for reader and per-schema `INSERT` for writer; compare `acl_lab` and `acl_else`.
39. **Global revoke trap:** `REVOKE SELECT` on `acl_else` and explain why global `SELECT` still applies.
40. **Fix:** design per-schema `SELECT` for `acl_lab` only without exposing `acl_else`.
41. **Role boundary:** create a table under `acl_deployer` instead of `acl_owner`; inspect reader's privileges.
42. **Membership:** why does `GRANT acl_owner TO acl_deployer` not apply `acl_owner`'s default ACLs during `CREATE`?
43. **SET ROLE:** create `created_as_owner` under `acl_owner` and compare against `created_by_deployer`.
44. **FOR ROLE deployer:** set a dedicated default policy for `acl_deployer` and create a new table to verify.
45. **current_user:** compare `current_user`, `current_role`, and `session_user` before/after `SET ROLE`.
46. **ALTER OWNER:** change a table's owner after `CREATE`; is the new owner's policy reapplied?
47. **Other schema:** create `acl_else.other_orders` as `acl_owner` and explain why reader's permissions differ from `acl_lab`.
48. **psql:** use `\\ddp` to inspect default ACLs.
49. **Existing ACL:** use `\\dp acl_lab.*` and compare with `\\ddp`.
50. **Catalog:** query `pg_default_acl` and explain `defaclrole`/`defaclnamespace`/`defaclobjtype`.
51. **Global scope:** why does `defaclnamespace = 0` denote global scope?
52. **aclexplode:** decode each `privilege_type`, `grantee`, and `is_grantable`.
53. **PUBLIC code:** why does grantee OID `0` mean `PUBLIC`?
54. **relacl:** inspect `pg_class.relacl`, owner, and `relkind` for tables, views, and sequences.
55. **proacl:** inspect `pg_proc.proacl` for functions in `acl_lab`.
56. **NULL ACL:** why does `relacl = NULL` not mean an object grants no privileges?
57. **has_*_privilege:** write a query checking effective schema/table/sequence/function/type privileges.
58. **Member grants:** explain how a role inherits `SELECT` via membership despite having no direct `GRANT`.
59. **CREATE TABLE AS:** create `order_snapshot` and verify permissions by creator/schema.
60. **Partition:** create a lab partition and inspect owner and direct partition privileges.
61. **Materialized view:** list specific permission and `REFRESH` behaviors to test.
62. **Column security:** why can default table `SELECT` expose sensitive columns added later?
63. **Grant option:** explain the risk of `WITH GRANT OPTION` on default `SELECT` for runtime.
64. **Least privilege:** design a role allowed only to create orders, with no `DELETE`/`TRUNCATE`.
65. **Schema CREATE:** distinguish `GRANT CREATE ON SCHEMA` from `ALTER DEFAULT PRIVILEGES ON TABLES`.
66. **Schema segmentation:** define separate default policies for `app_public`, `operations`, and `internal_audit`.
67. **Function allowlist:** explain why sensitive API functions should use explicit `GRANT`s rather than default `EXECUTE` on all functions.
68. **SECURITY DEFINER:** explain why `PUBLIC` `EXECUTE` on a high-privilege function is especially dangerous.
69. **RLS:** why does `has_table_privilege(..., 'SELECT') = TRUE` not prove tenant isolation?
70. **View invoker:** explain how `security_invoker` changes which privileges are checked on base tables.
71. **Migration:** create a table inside a transaction together with a default policy and observe the result.
72. **REVOKE future:** remove default `UPDATE` for writer; which privileges do existing tables keep?
73. **REVOKE existing:** revoke `UPDATE` directly on `acl_lab.orders`.
74. **Restore:** list roles, owners, grants, and default ACLs to verify after restoration.
75. **42501:** write a runbook for when a service fails with permission denied reading a new table.
76. **Java:** in `SQLException.getSQLState`, distinguish `42501` from other SQL errors.
77. **CI positive test:** assert reader can `SELECT` the new table and writer can `INSERT`.
78. **CI negative test:** assert reader cannot `DELETE` and writer cannot `EXECUTE` sensitive functions.
79. **Permission drift:** design an audit query checking ownership + ACLs after every deployment.
80. **Comprehensive design:** architect permissions for a multi-schema system with a migration owner, reader/writer/function caller, RLS, default ACLs, existing `GRANT`s, `PUBLIC` hardening, and smoke tests.

## 60. Safe Implementation Checklist

Before merging or running a migration containing `ALTER DEFAULT PRIVILEGES`:

1. Identify the exact **creator role** for each object kind.
2. Ensure the migration runs under the intended `current_role`.
3. List every schema to which the policy should apply.
4. Distinguish global vs. per-schema defaults; avoid overly broad unintended global grants.
5. Choose the smallest privilege set matching real SQL queries.
6. Grant `USAGE ON SCHEMA` to roles needing access.
7. Grant sequence privileges separately when `nextval`/`currval` is needed.
8. Review `PUBLIC` `EXECUTE` on functions and `PUBLIC` `USAGE` on types.
9. Audit `SECURITY DEFINER` functions and `EXECUTE` rights.
10. Inspect views, RLS, and `security_invoker`, not just direct tables.
11. Do not default-grant `SELECT` on all new objects if the schema holds sensitive data.
12. Manage permissions for **existing objects** and **future objects** separately.
13. Never treat `ALTER OWNER` as a way to reapply default ACLs.
14. Use `\\ddp` and `pg_default_acl` to inspect policies.
15. Use `\\dp`, catalogs, and `has_*_privilege` to inspect actual/effective rights.
16. Test under runtime roles, not just owner or superuser.
17. Test both required privileges and strictly forbidden operations.
18. Test creating a real new object in a test environment.
19. Record an audit trail of changes, reviewers, rollout, and rollback plans.
20. After deployment, monitor for `42501` errors and owner drift.

## 61. Summary

Keep this mental model in mind:

```text
ROLE ACTUALLY RUNNING CREATE OBJECT
            |
            v
DEFAULT PRIVILEGES OF CREATOR ROLE
            |
            +---- GLOBAL defaults
            |
            +---- PER-SCHEMA defaults (additive)
            |
            v
NEW OBJECT RECEIVES INITIAL ACL AT CREATE TIME
            |
            v
GRANTEE ROLE CAN ACCESS OBJECT
WHEN SCHEMA PRIVILEGES / RLS / OTHER CHECKS ALSO PASS
```

Key takeaways:

- **`ALTER DEFAULT PRIVILEGES` applies only to future objects.** It never grants or revokes privileges on existing tables, functions, or sequences.
- **`FOR ROLE` is the creator role, `TO` is the grantee role, `IN SCHEMA` is where objects are created.** Mixing up any of these three clauses produces wrong permissions.
- **Role membership does not inherit a parent role's default ACLs.** If migrations create objects as deployer instead of owner, use `SET ROLE` or configure defaults specifically for deployer.
- **Global and per-schema defaults combine additively.** A per-schema `REVOKE` cannot cancel a global `GRANT`.
- **Review `PUBLIC` `EXECUTE` on future functions and `PUBLIC` `USAGE` on future types.** For sensitive functions, global default `REVOKE PUBLIC` plus explicit `GRANT`s is safer than broad default `EXECUTE`.
- **`TABLES`, `SEQUENCES`, `FUNCTIONS`, `TYPES`, and `SCHEMAS` have distinct privileges.** Granting table `SELECT` does not grant schema/sequence `USAGE` or function `EXECUTE`.
- **Least privilege is an ongoing process**, not a one-off `GRANT ALL`. Review schemas, sensitive columns, views, RLS, `SECURITY DEFINER`, and ownership.
- **Always check both policies and actual privileges:** `\\ddp`/`pg_default_acl` for the future; `\\dp`, catalogs, and `has_*_privilege` for existing objects.
- **Test under application roles** and verify forbidden actions as well, especially after migrations or restores.

Well-designed default privileges ensure new objects start with the right permissions from the moment they are created—reducing `permission denied` surprises as the system grows while preventing accidental privilege sprawl. Their greatest value is not merely automating `GRANT`, but **preserving consistent ownership, least privilege, and verifiable security as new tables, sequences, views, functions, and schemas are continuously added to PostgreSQL**.
