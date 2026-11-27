# Owners, Superusers, and the Principle of Least Privilege in PostgreSQL

A PostgreSQL system can have a well-designed table structure, parameterized SQL queries, and strict data constraints, yet still suffer severe incidents if **the application connects as a superuser**, **all services share the schema-owning account**, or **privileges are granted more broadly than actually needed**.

Consider an online store with an inventory-reading API and a restocking job. If both connect using an account that can `DROP TABLE`, `ALTER ROLE`, or bypass Row-Level Security (RLS), a programming bug, SQL injection, or leaked credential can cause far more damage than the actual task the program needs to perform.

PostgreSQL allows clearly separating:

- **Owner**: the role that controls the lifecycle and definition of an object such as a table, schema, view, or function.
- **Object privileges**: which roles can perform `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `USAGE`, `EXECUTE`, `CREATE`, and other actions.
- **Role attributes**: whether a role can log in, create databases, administer roles, has `BYPASSRLS`, or holds superuser privileges.
- **Role membership**: a role can receive or use privileges from another role according to inheritance rules, `SET ROLE`, and administrative options.
- **Row-level policies (RLS policies)**: narrowing the set of rows that can be read/modified after table-level privileges are checked.
- **Principle of least privilege**: each application, user, and process holds only enough privileges to perform its authorized tasks, for the duration needed.

For example, an API role that only reads SKU codes and stock counts does not need full privileges on the entire products table:

```sql
GRANT USAGE ON SCHEMA inventory_api TO app_reader;

GRANT SELECT (sku, stock)
ON TABLE inventory_api.products
TO app_reader;
```

Conceptually, this role can read the two granted columns, while not automatically gaining permission to read unit cost, modify stock, create new tables, or alter the schema. To achieve a true security boundary, you must also evaluate inherited privileges, other grants, schema privileges, and privileges on related objects.

This lesson belongs to the **Database Engine Relational PostgreSQL** module, **Security** chapter, focusing on managing **ownership**, understanding the scope of **superuser** privileges, designing **least privilege**, and verifying privileges across a multi-role system.

---

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **owner**, **privilege**, **membership**, **role attribute**, and **RLS policy**.
2. Explain why an owner has object-modification capabilities that cannot be represented simply by a `GRANT ALL` statement.
3. Distinguish `LOGIN`, `NOLOGIN`, `INHERIT`, `NOINHERIT`, and `SET ROLE`.
4. Design **non-login object-owning roles** and runtime roles that only receive the necessary DML privileges.
5. Understand the risks of `SUPERUSER`, `CREATEROLE`, `CREATEDB`, `REPLICATION`, and `BYPASSRLS`.
6. Distinguish a true superuser role from restricted "admin" accounts in managed PostgreSQL services.
7. Use `GRANT`, `REVOKE`, column-level privileges, schema usage, and membership for their intended purposes.
8. Understand that `PUBLIC` represents the set of all roles, not a single separate user name.
9. Read default privileges when creating schemas, tables, functions, sequences, and databases.
10. Use `ALTER DEFAULT PRIVILEGES` without mistakenly assuming it modifies already-existing objects.
11. Distinguish table privileges from privileges to use sequences, functions, views, and materialized views.
12. Explain why a table owner normally bypasses RLS unless `FORCE ROW LEVEL SECURITY` is set, whereas superusers and `BYPASSRLS` roles have separate special privileges.
13. Understand how default views and `security_invoker` views differ regarding privileges on underlying objects.
14. Write `SECURITY DEFINER` functions following least privilege and a safe `search_path`.
15. Inspect role attributes, ownership, table/column/schema privileges, and grants using PostgreSQL catalogs and functions.
16. Manage ownership of schemas, tables, and functions when deploying migrations.
17. Use `REASSIGN OWNED` and `DROP OWNED` in a controlled manner when decommissioning a role.
18. Design a privilege model for read APIs, write services, reporting jobs, migrations, backups, and operations.
19. Distinguish true read-only access from "merely lacking direct `UPDATE`" while still having write paths via functions or inherited privileges.
20. Build a permission test suite covering **both allowed paths and paths that must be denied**.

**Scope:** Modern PostgreSQL. Certain details regarding membership options changed in PostgreSQL 16, and `security_invoker` for views is supported starting in PostgreSQL 15. Verify against your running version before deploying. Role-creation and privilege-granting examples are strictly for authorized lab databases; never run examples that alter administrative privileges in production without an impact assessment.

---

## 2. Permission Model: From Connection to a Data Row

A query passes through multiple control layers:

```text
Application or user
        |
        | Authentication (pg_hba.conf, TLS, password/cert/...)
        v
Login role / session
        |
        | Role attributes and role memberships
        v
Does it have CONNECT on the database?
        |
        v
Does it have USAGE on the schema?
        |
        v
Does it have SELECT/INSERT/UPDATE/... on the object?
        |
        v
If the table has RLS, which policies apply?
        |
        v
Column, function, view, sequence, and constraint checks
        |
        v
Result or permission denied
```

This diagram illustrates the layers to consider; PostgreSQL's internal evaluation order does not necessarily execute strictly step by step like a linear pipeline.

### 2.1. Authentication Does Not Mean Authorization

A role being able to log in does not mean it can read every table. Conversely, a `NOLOGIN` role can own tables and be used via membership/`SET ROLE` without being able to authenticate directly.

### 2.2. Schema Privileges Do Not Mean Table Privileges

`USAGE ON SCHEMA` primarily allows referencing object names inside the schema as permitted. It **does not automatically grant `SELECT`** on every table.

### 2.3. Table Privileges Do Not Replace Database/Schema Privileges

A role with `GRANT SELECT ON TABLE app.orders` that lacks the associated privileges needed to access the object name may still fail to execute the query as intended.

### 2.4. RLS Does Not Replace the SELECT Privilege

RLS filters rows where applicable. A role lacking the required `SELECT` privilege cannot rely solely on a policy to read a table.

### 2.5. Ownership Is a Different Tier of Power

The owner controls object definitions and privilege distribution. A read-only consumer should never become the owner just because it needs to run a `SELECT`.

---

## 3. What Is a PostgreSQL Role?

PostgreSQL unifies the concepts of user and group into a **role**.

A role can:

- Be allowed to log in if it has the `LOGIN` attribute.
- Be disallowed from logging in directly if it has `NOLOGIN`.
- Be a member of other roles.
- Own databases/schemas/tables/functions.
- Be granted privileges on objects.
- Hold administrative attributes such as `CREATEDB`, `CREATEROLE`, or `SUPERUSER`.
- Have or lack the ability to immediately use inherited privileges depending on membership configuration.

### 3.1. Creating a Non-Login Role

```sql
CREATE ROLE reporting_reader NOLOGIN;
```

This role is suited as a **privilege group** in which multiple login roles can be granted membership.

### 3.2. Creating a Login Role

```sql
CREATE ROLE reporting_service LOGIN;
```

This example **does not yet configure a secure authentication method**. In production, you must configure a password/certificate/identity and appropriate login controls. Never create a passwordless login role and rely on a broad `trust` configuration for security.

### 3.3. Granting a Role to a Role

```sql
GRANT reporting_reader TO reporting_service;
```

Depending on membership/inheritance configuration, `reporting_service` can use the privileges of `reporting_reader`.

### 3.4. Roles Are Cluster-Level Objects

Roles are managed at the PostgreSQL cluster scope, not just within a single schema. One role can hold privileges across multiple databases in the same cluster.

Therefore, dropping a role or changing its attributes can affect multiple applications and databases. Never treat `DROP ROLE` as a change limited to the current database.

### 3.5. NOLOGIN Does Not Mean Unprivileged

A `NOLOGIN` role can serve as an owner, be granted very broad privileges, or be assumed via `SET ROLE` from a permitted session. `NOLOGIN` only blocks direct login; it does not strip object privileges.

---

## 4. Owners Differ from SELECT/UPDATE Privileges

Suppose a table:

```sql
CREATE TABLE app.orders (...);
```

is owned by `app_owner`.

Another role is granted:

```sql
GRANT SELECT ON app.orders TO app_reader;
```

The two roles have fundamentally different capabilities.

| Capability | Owner | Granted only SELECT |
| --- | --- | --- |
| Read table data | Normally yes | Yes, within grant/RLS bounds |
| INSERT/UPDATE/DELETE | Owner has base object rights, still subject to RLS/constraints | Not from SELECT alone |
| ALTER TABLE | Controls definition under ownership rules | No |
| DROP TABLE | Controls object lifecycle per DDL rules | No |
| GRANT object privileges to others | Owner can grant | No, unless holding GRANT OPTION or equivalent mechanism |
| Change owner | Possible under permitted conditions | No |
| Bypass RLS | Table owner normally bypasses, unless FORCE RLS | Not by default |
| Administer entire cluster | Not merely from owning a table | No |

### 4.1. GRANT ALL Does Not Turn a Role into the Owner

```sql
GRANT ALL PRIVILEGES ON TABLE app.orders TO app_writer;
```

grants all applicable **grantable table privileges**. It does not transfer ownership, does not automatically allow `ALTER`/`DROP` on the object, and does not make the role a superuser.

### 4.2. Owner Rights Are Not Just Granted ACLs

PostgreSQL treats the ability to alter or drop an object as inherent to ownership. You cannot simply "REVOKE the owner's `DROP TABLE` privilege" with an ordinary `GRANT`/`REVOKE` while leaving that role as the owner.

### 4.3. Owner DML Still Interacts with RLS

Do not assume "the owner has privileges on the table" means it bypasses every database feature. With `FORCE ROW LEVEL SECURITY`, a table owner can be subject to RLS policies; superusers and `BYPASSRLS` roles remain separate special cases.

### 4.4. The Owner Need Not Be the Role That Runs Daily Apps

One role can create a table and transfer ownership to another role if permitted. Distinguish between the *creator*, the *current owner*, and the *migration runner*.

---

## 5. Why Should Application Accounts Not Own Tables?

If an API service connects as `app_owner`, an exploited query can leverage owner rights to:

- `ALTER` or `DROP` owned objects.
- Change permissions granted on objects.
- Disable or alter controls managed by the owner.
- Touch data not meant to be exposed if the owner has broad access.
- Accidentally mutate schemas during a buggy deployment.

### 5.1. A Better Model

```text
migration/admin deployment
         |
         | SET ROLE app_owner when DDL is needed
         v
app_owner (NOLOGIN)
         |
         +-- owns schemas/tables/functions
         |
         +-- GRANT SELECT       --> app_read (NOLOGIN)
         +-- GRANT narrow DML   --> app_write (NOLOGIN)
                                |
                                +--> service logins granted membership
```

### 5.2. Separating Deploy Accounts from Runtime Accounts

- **Deployment/migration role** is granted the ability to change schemas through a controlled process.
- **Runtime role** holds only the `SELECT`/`INSERT`/`UPDATE`/`DELETE` privileges it needs.
- **Reporting role** reads only published reporting objects.
- **Operator role** holds deliberately granted observability or maintenance capabilities.
- **Superuser/break-glass** is used very sparingly and never placed in the application connection pool.

### 5.3. Every Role Still Needs Credential Management

A `NOLOGIN` owner has no direct login credentials. Application login roles still require secret management, rotation, TLS, and connection-level access controls. Separating roles alone does not automatically make the whole system secure.

---

## 6. Superuser: Cluster-Level Privilege

PostgreSQL has the `SUPERUSER` attribute, which grants vast power, including bypassing routine permission checks on database objects.

In many self-managed clusters, the initial administrative account is named `postgres`, though **this is not mandatory**. On cloud-managed PostgreSQL, an account named "admin" or "postgres" may **not actually have `SUPERUSER`**, because the provider restricts system-level privileges.

### 6.1. What Can a Superuser Do?

A true superuser can perform many actions beyond ordinary owner or table privileges:

- Access or modify almost any object in the cluster.
- Manage role attributes and very high privileges.
- Perform many maintenance, configuration, and extension operations.
- Bypass RLS per PostgreSQL rules.
- Access other sensitive administrative capabilities restricted from non-superusers.

Exact capabilities also depend on the cluster, version, extensions, and external controls such as the OS or managed service.

### 6.2. Why Is Using a Superuser for an Application a Major Risk?

If credentials leak or the code has a SQL injection vulnerability, the attacker is no longer constrained by read/write grants on a single schema.

### 6.3. Superuser Is Not the Fix for "Eliminating Permission Denied Errors"

A rejected `SELECT` is a signal to find out which privilege is missing, not a reason to add `SUPERUSER`.

### 6.4. Most CRUD Needs No Superuser

Everyday operations such as:

```sql
SELECT ...
INSERT ...
UPDATE ...
DELETE ...
```

can be granted precisely at the database/schema/table/column level without `SUPERUSER`.

### 6.5. Operational Principles

Reserve high administrative privileges for dedicated accounts with auditing, protected credentials, approval-gated access when needed, and avoid using them as the default login for services.

---

## 7. High-Privilege Role Attributes

Notable role attributes:

| Attribute | Meaning | Risk if granted broadly |
| --- | --- | --- |
| `SUPERUSER` | Very high cluster-wide privileges | Virtually removes object ACL/RLS boundaries |
| `CREATEROLE` | Administer roles/memberships within version limits | Can expand privileges via role management |
| `CREATEDB` | Create databases | Creates new resources with database ownership |
| `REPLICATION` | Connect/perform replication operations | Access to replication/WAL data and system state |
| `BYPASSRLS` | Bypass Row-Level Security | Access rows outside policies |
| `LOGIN` | Direct login | Credentials must be protected |
| `INHERIT` | Default configuration for inheriting member privileges | May receive broader privileges than anticipated |
| `CONNECTION LIMIT` | Limit connection count per role rules | Not a data-access policy |

### 7.1. CREATEROLE Is Not Simply SUPERUSER

`CREATEROLE` allows role-management actions within permitted boundaries. Those boundaries vary by version; in particular, PostgreSQL 16 changed membership administration rules.

Do not equate `CREATEROLE` with the ability to create or self-grant every superuser privilege.

### 7.2. BYPASSRLS Is Very Sensitive

A `BYPASSRLS` role can bypass row-protection policies. If a multi-tenant application relies on RLS, giving `BYPASSRLS` to runtime can neutralize a critical defense layer.

### 7.3. CREATEDB Does Not Automatically Allow Reading Every Table

Owning a database or being able to create databases does not make a role the default owner of tables created by others in other databases.

### 7.4. REPLICATION Does Not Belong in a Runtime API

Replication and backup are specialized roles capable of accessing large volumes of data. Never attach `REPLICATION` to a role that only performs CRUD.

### 7.5. Role Attributes Differ from Table GRANTs

A role without `SUPERUSER` can still read a table when granted `SELECT`. Conversely, a role with `CREATEDB` cannot necessarily read an application's private tables.

---

## 8. LOGIN, NOLOGIN, INHERIT, and NOINHERIT

### 8.1. LOGIN/NOLOGIN

```sql
CREATE ROLE security_owner NOLOGIN;
CREATE ROLE security_runtime LOGIN;
```

The owner role is typically designed as `NOLOGIN`, while the runtime login uses an appropriate authentication method.

### 8.2. INHERIT

With proper inheritance, a member role can use privileges of a granted role without running `SET ROLE` first.

```sql
GRANT reporting_reader TO security_runtime;
```

### 8.3. NOINHERIT

A role declared `NOINHERIT` does not automatically use all privileges from its memberships the way an `INHERIT` role can. However, whether it can run `SET ROLE` depends on membership rights and the PostgreSQL version.

### 8.4. From PostgreSQL 16: More Granular Membership Options

Membership relationships carry options for **INHERIT**, **SET**, and **ADMIN**. Thus you cannot inspect only `rolinherit` and deduce every inheritance or role-switching path accurately.

An example that appeared safe in PostgreSQL 15 may require reviewing how roles are `GRANT`ed after upgrading or modifying memberships on PostgreSQL 16+.

### 8.5. INHERIT Does Not Mean a Role Can Replace the Owner

Inheriting `SELECT` on a table does not imply permission to perform every action the owner can perform. Owner/DDL operations and `SET ROLE` follow separate rules.

### 8.6. Never Assume "Role Was Granted" Without Testing

In a real environment, test from the runtime login:

```sql
SELECT session_user, current_user;
SELECT has_table_privilege(
    current_user,
    'app.orders',
    'SELECT'
);
```

and test both allowed and expected-denied operations against the actual role memberships.

---

## 9. SET ROLE, session_user, and current_user

A connection can authenticate as role A yet operate in the context of role B if permitted.

```sql
SELECT
    session_user,
    current_user;
```

- `session_user` is typically the initial authenticated session role.
- `current_user` is the role used for most permission checks in the current context; it can change after `SET ROLE` or inside privilege contexts such as `SECURITY DEFINER`.

### 9.1. Switching Roles Within a Session

```sql
SET ROLE security_owner;

-- Execute authorized DDL.

RESET ROLE;
```

This succeeds only when the session has permission to switch to that role or holds administrative privileges allowing it.

### 9.2. SET ROLE Does Not Create a New Session

The session remains the same session; it changes the privilege context according to PostgreSQL rules. GUCs, transactions, and pooling still need to be managed.

### 9.3. Do Not Forget RESET ROLE in Migrations/Tests

If a connection is reused after `SET ROLE`, failing to restore the role can cause the next step to run with unintended privileges. In production, it is better to use dedicated migration connections with explicit lifecycle management.

### 9.4. SECURITY DEFINER and current_user

Inside a `SECURITY DEFINER` function, PostgreSQL executes the body with the privileges of the function's owner; `current_user` can reflect the effective role inside the function. That means authorization logic must not blindly assume `current_user` is always the authenticated caller identity.

### 9.5. Role Membership Is an Escalation Path If Misconfigured

If a runtime role is permitted to `SET ROLE` to an owner role, runtime can access owner privileges at that point. Never inspect only direct grants and overlook membership in an owner role.

---

## 10. PUBLIC Is Not an Ordinary Login Role

In the context of `GRANT`/`REVOKE`, `PUBLIC` represents **all current and future roles**.

For example:

```sql
GRANT SELECT ON TABLE app.public_catalog TO PUBLIC;
```

means every role that has the other required access privileges on the object can use that `SELECT`.

### 10.1. No Need to GRANT Membership to PUBLIC

Every role implicitly belongs to `PUBLIC` in PostgreSQL's privilege model.

### 10.2. REVOKE FROM PUBLIC

```sql
REVOKE EXECUTE ON FUNCTION
    app.sensitive_operation(INTEGER)
FROM PUBLIC;
```

is an example of revoking a default privilege or an overly broad prior grant.

### 10.3. Revoking PUBLIC Does Not Remove Other Grants

If a role holds a direct `GRANT` or a grant via a group role, `REVOKE ... FROM PUBLIC` alone does **not** remove those other privilege paths.

### 10.4. Do Not Confuse the public Schema with the PUBLIC Pseudo-Role

- `public` (schema): a schema object commonly named `public`.
- `PUBLIC` in `GRANT`/`REVOKE`: the set of all roles.

They are two distinct concepts despite looking similar.

### 10.5. Check Default Privileges by Version

A newly created PostgreSQL database may grant `CONNECT`/`TEMP` on the database and `USAGE` on schema `public` by default, while `CREATE` on the `public` schema changed in recent versions. Do not rely on one memorized rule for every upgraded or restored cluster.

---

## 11. Permission Lab: Role Model and Inventory Table

Let's build a model:

- `sec379_owner`: non-login owner.
- `sec379_read`: read privilege group.
- `sec379_write`: inventory-update privilege group.
- `sec379_app_reader`: role simulating a read consumer.
- `sec379_app_writer`: role simulating a write worker.
- `sec379_lab`: demo schema.

The app roles in the lab are also `NOLOGIN` so we do not create login accounts with credentials. When testing, an administrator permitted to use `SET ROLE` simulates each context.

**Operational warning:** The following statements require appropriate role/schema admin privileges and **must only be run on a practice cluster/database** where these role and schema names are reserved for the lab. Never run them on a production environment, and never add `SUPERUSER` to these roles.

### 11.1. Creating the Roles

```sql
CREATE ROLE sec379_owner NOLOGIN;
CREATE ROLE sec379_read NOLOGIN;
CREATE ROLE sec379_write NOLOGIN;
CREATE ROLE sec379_app_reader NOLOGIN INHERIT;
CREATE ROLE sec379_app_writer NOLOGIN INHERIT;

GRANT sec379_read TO sec379_app_reader;
GRANT sec379_write TO sec379_app_writer;
```

In a real environment, inheritance behavior depends on membership options; the lab assumes grants are configured so members receive the corresponding privileges.

### 11.2. Creating a Schema Owned by the Owner Role

```sql
CREATE SCHEMA sec379_lab AUTHORIZATION sec379_owner;
```

Only create the schema in a database where you have `CREATE` privileges and no name conflict exists.

### 11.3. Creating a Table with a Non-Login Owner

From an administrative session permitted to switch roles:

```sql
SET ROLE sec379_owner;

CREATE TABLE sec379_lab.inventory (
    sku TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    stock INTEGER NOT NULL
        CONSTRAINT inventory_stock_nonnegative CHECK (stock >= 0),
    unit_cost NUMERIC(12,2) NOT NULL
        CONSTRAINT inventory_cost_nonnegative CHECK (unit_cost >= 0),
    internal_note TEXT
);

INSERT INTO sec379_lab.inventory (
    sku, display_name, stock, unit_cost, internal_note
)
VALUES
    ('SKU-100', 'Keyboard', 8, 280000.00, 'Cost is confidential'),
    ('SKU-200', 'Mouse', 25, 90000.00, 'Supplier terms private'),
    ('SKU-300', 'Monitor', 4, 1750000.00, NULL);

RESET ROLE;
```

### 11.4. Ownership Result

The table and schema are owned by `sec379_owner` in this example; this role needs no runtime login password.

### 11.5. Why Include Sensitive Columns?

`unit_cost` and `internal_note` represent fields that an API displaying only stock levels **should not read**. This makes testing column-level privileges clear.

### 11.6. Separating DDL from Runtime

The day-to-day application does not need ownership just to `SELECT` `sku` and `stock`. The next sections grant narrow privileges to the consumer roles.

---

## 12. GRANT USAGE on Schema

A role wanting to query a named object inside a schema generally needs `USAGE` on the schema in addition to privileges on the object itself.

In the lab:

```sql
GRANT USAGE ON SCHEMA sec379_lab
TO sec379_read, sec379_write;
```

### 12.1. USAGE Does Not Allow Creating Tables

```sql
GRANT USAGE ON SCHEMA sec379_lab TO sec379_read;
```

does not grant `CREATE` in the schema.

### 12.2. CREATE on a Schema Is a Sensitive Privilege

```sql
GRANT CREATE ON SCHEMA sec379_lab TO some_role;
```

allows the role to create supported objects in the schema; if that schema appears on the `search_path` of a `SECURITY DEFINER` function, letting untrusted roles create objects opens the door to name shadowing/hijacking.

### 12.3. A Role Granted Table SELECT Without Schema USAGE

Even with a table-level grant, a role may be unable to access the table by name when lacking schema `USAGE`. When debugging permission denied, check all layers—do not add `SUPERUSER`.

### 12.4. Be Careful with the public Schema

Creating internal tables in dedicated schemas makes managing owners and grants by domain much clearer than dumping every object into `public` shared across applications.

### 12.5. Schema Ownership Does Not Let the Owner Read Tables Owned by Others

Owning a schema grants control over the schema per PostgreSQL rules, but does not automatically make the schema owner the owner of—or grant `SELECT` on—every table owned by other roles inside it.

---

## 13. Column-Level GRANT for the Inventory-Reading API

Instead of:

```sql
GRANT SELECT ON sec379_lab.inventory TO sec379_read;
```

we grant only the exact two columns needed:

```sql
GRANT SELECT (sku, stock)
ON TABLE sec379_lab.inventory
TO sec379_read;
```

### 13.1. Allowed Query

Assuming `sec379_app_reader` properly inherits `sec379_read`:

```sql
SET ROLE sec379_app_reader;

SELECT sku, stock
FROM sec379_lab.inventory
ORDER BY sku;

RESET ROLE;
```

### 13.2. Query That Must Be Denied

Run each failing test separately (do not bundle it into a transaction with work you want to keep):

```sql
SET ROLE sec379_app_reader;

-- Expected to be denied because SELECT on unit_cost was not granted.
SELECT sku, unit_cost FROM sec379_lab.inventory;

RESET ROLE;
```

If the failing statement puts an open transaction into an aborted state, run `ROLLBACK` before subsequent statements. In automated scripts, use separate test sessions or transactions/savepoints per PostgreSQL rules.

### 13.3. SELECT * Can Fail

```sql
SELECT * FROM sec379_lab.inventory;
```

requires privileges on all queried columns. Granting only `SELECT(sku,stock)` is insufficient to read `unit_cost` and `internal_note`.

### 13.4. Why Is This Least Privilege?

The API only needs to display SKU and quantity. If its account is compromised, the accessible data surface is smaller than with table-wide `SELECT`.

### 13.5. Watch Out for Broad Privileges Granted via Other Paths

If `sec379_app_reader` also inherits a role holding `SELECT ON TABLE inventory`, the column-level restriction above does not "negate" that broader grant. PostgreSQL privileges are generally additive across valid grant paths; there is no simple blanket `DENY` for a column already granted via another path.

---

## 14. GRANT UPDATE for a Worker Updating Only Stock

The inventory worker needs to read `sku`/`stock` for filtering and updating stock, without modifying `unit_cost` or reading `internal_note`.

```sql
GRANT SELECT (sku, stock),
      UPDATE (stock)
ON TABLE sec379_lab.inventory
TO sec379_write;
```

### 14.1. Allowed UPDATE

```sql
BEGIN;

SET LOCAL ROLE sec379_app_writer;

UPDATE sec379_lab.inventory
SET stock = stock - 1
WHERE sku = 'SKU-100'
  AND stock >= 1
RETURNING sku, stock;

ROLLBACK;
```

The example above is a simple **atomic conditional UPDATE** pattern. The worker needs appropriate `SELECT` privileges to read `stock` in expressions/`WHERE`/`RETURNING` and `UPDATE` on the `stock` column.

**Note:** `SET LOCAL ROLE` is not general PostgreSQL syntax for transaction-scoped role switching. In the actual lab, use `SET ROLE sec379_app_writer` followed by `RESET ROLE` in an appropriate session, or use `SET ROLE` inside a controlled transaction. Valid executable example:

```sql
BEGIN;
SET ROLE sec379_app_writer;

UPDATE sec379_lab.inventory
SET stock = stock - 1
WHERE sku = 'SKU-100'
  AND stock >= 1
RETURNING sku, stock;

ROLLBACK;
-- After rollback, verify that the effective role returned to the pre-test context.
```

### 14.2. Disallowed UPDATE

```sql
SET ROLE sec379_app_writer;

-- Expected permission denied because UPDATE on unit_cost is not granted.
UPDATE sec379_lab.inventory
SET unit_cost = 1
WHERE sku = 'SKU-100';

RESET ROLE;
```

### 14.3. DELETE/TRUNCATE/ALTER Remain Ungranted

`UPDATE(stock)` does not allow the worker to delete rows, truncate the table, or alter structure.

### 14.4. Do Not Grant ALL Just to Update One Column

```sql
GRANT ALL ON TABLE sec379_lab.inventory TO sec379_write;
```

opens far more privileges than required and makes least privilege hard to prove.

### 14.5. Constraints Are Still Necessary

Even when a role can only modify `stock`, the table should retain `CHECK (stock >= 0)` to protect all write paths, including the owner, migrations, and other code.

---

## 15. Table-Level and Column-Level Privileges Differ

In PostgreSQL, `SELECT`/`INSERT`/`UPDATE` can be granted at the column level depending on command form and object type.

| GRANT statement | Effect |
| --- | --- |
| `GRANT SELECT ON table` | Read table columns per current privileges |
| `GRANT SELECT(col1,col2) ON table` | Read only the specified columns |
| `GRANT INSERT(col1) ON table` | `INSERT` values into specific columns, still subject to defaults/constraints |
| `GRANT UPDATE(col1) ON table` | `UPDATE` specific columns |
| `GRANT DELETE ON table` | `DELETE` rows, not granted per column |
| `GRANT TRUNCATE ON table` | `TRUNCATE` the table |
| `GRANT REFERENCES ON table` | Reference appropriate table/columns in a foreign key |
| `GRANT TRIGGER ON table` | Create triggers per relevant privileges and rules |

### 15.1. DELETE Is a High-Impact Privilege

Even if an application only needs to delete "one order," granting `DELETE` on the entire table confers the capability to delete many rows. Enforce bounds via business logic, RLS, triggers, or API boundaries.

### 15.2. TRUNCATE Is Not the Same as DELETE

`TRUNCATE` follows separate mechanics and is not evaluated row-by-row under RLS like `DELETE`. Never grant `TRUNCATE` to runtime just because it needs to delete a row.

### 15.3. REFERENCES Is Not SELECT

To create a foreign key referencing another table, appropriate `REFERENCES` privileges are required. Do not grant it to ordinary APIs unnecessarily.

### 15.4. Column Privileges Must Be Tested Against Real Queries

A statement like `UPDATE ... SET stock = stock - 1 WHERE sku = ...` requires `UPDATE` on `stock` plus `SELECT` on all read columns, not `UPDATE` alone.

### 15.5. Privileges Can Arrive from Multiple Paths

Check direct grants, memberships, `PUBLIC`, ownership, and helper functions rather than reading just one `GRANT` line in a migration.

---

## 16. GRANT/REVOKE Is Not a DENY System

PostgreSQL uses an **additive grant model**: a role holds a privilege if it is granted via any valid path or holds corresponding special attributes.

### 16.1. Revoking a Direct Grant

```sql
REVOKE SELECT ON sec379_lab.inventory
FROM sec379_read;
```

revokes that table-level grant if present.

### 16.2. That Does Not Mean the Role Loses All Read Paths

If the role receives `SELECT` through another role or `PUBLIC`, it can still read.

### 16.3. REVOKE Cannot Disable a Superuser

A true superuser bypasses routine ACL checks. To enforce least privilege, you must **never make runtime a superuser** in the first place.

### 16.4. Revoking Owner Privileges Has Limits

An owner does not lose object control rights such as `ALTER`/`DROP` merely because DML grants are revoked. To separate administrative control, transfer ownership or split roles.

### 16.5. REVOKE ... CASCADE Can Affect Downstream Grantees

When a role has granted privileges onward using `GRANT OPTION`, revoking that grant option can cascade and revoke dependent grants. Never use `CASCADE` before understanding the full delegation chain.

---

## 17. GRANT OPTION and Privilege Delegation

A role can be granted a privilege **along with the ability to grant it onward** to others.

```sql
GRANT SELECT ON TABLE app.some_report
TO reporting_lead
WITH GRANT OPTION;
```

### 17.1. Risk

If a role only needs to view reports, giving it `GRANT OPTION` allows that role to distribute read access to unintended recipients.

### 17.2. Owners Have Inherent Grant Capabilities

An owner normally has the right to grant privileges on owned objects. There is no need to turn the owner into a runtime user just to simplify granting.

### 17.3. GRANT OPTION Differs from Membership ADMIN OPTION

- `WITH GRANT OPTION` on an object privilege: allows granting that object privilege onward.
- `ADMIN OPTION` on role membership: governs membership administration rights per version rules.

They are not the same attribute.

### 17.4. Control Who Can Grant

Use deployment scripts, reviews, and catalog audits to detect unintentionally broad grants. Least privilege includes **the power to create more privileges**.

---

## 18. Database-Level Privileges: CONNECT, CREATE, TEMPORARY

Database privileges differ from table privileges.

| Database privilege | Meaning |
| --- | --- |
| `CONNECT` | Connect to the database under grant rules |
| `CREATE` | Create schemas and certain database-level objects per PostgreSQL rules |
| `TEMPORARY`/`TEMP` | Create temporary tables when permitted |

### 18.1. CONNECT Does Not Grant Read Access to Every Table

```sql
GRANT CONNECT ON DATABASE appdb TO app_login;
```

is not equivalent to `GRANT SELECT ON ALL TABLES`.

### 18.2. Database CREATE Privilege Is Not the CREATEDB Role Attribute

- `GRANT CREATE ON DATABASE appdb`: ability to create schemas/database-scoped objects inside `appdb`.
- `CREATEDB` role attribute: ability to create **new databases** in the cluster.

### 18.3. TEMP Must Be Evaluated Against the Threat Model

Temporary tables are useful for ETL, but carry storage overhead and name-resolution implications—especially with `SECURITY DEFINER` functions. Do not assume `TEMP` is harmless in an untrusted multi-tenant system.

### 18.4. PUBLIC May Already Hold CONNECT/TEMP

In many PostgreSQL databases, `CONNECT` and `TEMP` are granted to `PUBLIC` by default. To enforce an allowlist, inspect and revoke the appropriate grants. Changing `CONNECT` on an active database can prevent existing clients or monitoring from reconnecting.

### 18.5. Do Not Modify System Databases While Learning

Do not run `REVOKE CONNECT ON DATABASE postgres FROM PUBLIC` or alter shared databases purely for illustration. Create a dedicated lab database and analyze impact beforehand.

---

## 19. The public Schema and Default Changes from PostgreSQL 15

Historically, many clusters allowed every role to create objects in the `public` schema, while that schema typically appeared in `search_path`.

### 19.1. PostgreSQL 15 Changed Defaults for New Databases

In PostgreSQL 15 and later, the `public` schema in new databases has safer defaults: `CREATE` for `PUBLIC` is no longer granted broadly as in older versions, and ownership aligns with the `pg_database_owner` model.

### 19.2. Upgraded Databases May Retain Old Grants

A database created on an older PostgreSQL version and later upgraded/restored may still retain the old `public` schema ACL. Never assume "we are on PG16, so `PUBLIC` definitely lacks `CREATE`."

### 19.3. Check Actual Privileges

```sql
SELECT
    has_schema_privilege(
        'public',
        'USAGE'
    ) AS can_use_public,
    has_schema_privilege(
        'public',
        'CREATE'
    ) AS can_create_in_public;
```

Results are evaluated for the current role.

### 19.4. Revoke Only with a Plan

```sql
-- Illustrative only; evaluate dependencies before running:
-- REVOKE CREATE ON SCHEMA public FROM PUBLIC;
```

Revoking `CREATE` can break legacy migration tools or extensions that previously relied on that broad grant. Migrate them to dedicated roles/schemas and test in staging.

### 19.5. The public Schema Is Not a Public Data Dump

The name `public` does not mean every table inside is automatically readable via `SELECT` by every role. Schema and table privileges are separate layers.

---

## 20. Sequence Privileges and Identity Columns

When designing `INSERT`, examine **where primary keys come from**.

Example table using a manual sequence:

```sql
CREATE SEQUENCE app.order_number_seq;

CREATE TABLE app.orders (
    id BIGINT PRIMARY KEY
        DEFAULT nextval('app.order_number_seq'::REGCLASS),
    ...
);
```

An inserting role should not receive broader sequence privileges than required.

### 20.1. Privileges on a Sequence

PostgreSQL supports sequence privileges such as `USAGE`, `SELECT`, and `UPDATE` for their respective operations.

For patterns calling `nextval`, `USAGE` (or the privilege required under PostgreSQL rules) is typically what needs attention.

```sql
GRANT USAGE ON SEQUENCE app.order_number_seq
TO app_writer;
```

### 20.2. Do Not Assume Table INSERT Automatically Grants All Sequence Privileges

If a column has a `DEFAULT` invoking `nextval` on a separate sequence, sequence privileges may need to be granted alongside table `INSERT`.

### 20.3. IDENTITY Differs from SERIAL/Manual Defaults

`GENERATED ... AS IDENTITY` columns are managed differently by PostgreSQL than columns with a manual `DEFAULT nextval(...)`. Do not mechanically apply identical sequence-grant assumptions to every identity case; check your version and test actual permissions.

### 20.4. GRANT ON ALL SEQUENCES Has Broad Scope

```sql
GRANT USAGE ON ALL SEQUENCES IN SCHEMA app TO app_writer;
```

may fit a general ingestion job writing across all tables, but is not a good default for a service writing to a single sequence.

### 20.5. Sequences Do Not Roll Back Like Table Data

Values drawn from a sequence can leave gaps when transactions roll back. Never treat incrementing numbers as proof that all transactions succeeded or to count total transactions.

---

## 21. EXECUTE Privileges on Functions

A function can serve as an indirect data-read or data-write path.

### 21.1. Default EXECUTE on Functions

In a typical PostgreSQL configuration, newly created functions grant `EXECUTE` to `PUBLIC` by default unless configured otherwise. Creating a sensitive `SECURITY DEFINER` function and forgetting to `REVOKE` can expose an unintended attack surface.

### 21.2. Example of a Restricted Function

```sql
-- Run only in a database where the matching schema and table exist.
CREATE FUNCTION app.get_order_status(p_order_id BIGINT)
RETURNS TEXT
LANGUAGE SQL
STABLE
AS $fn$
    SELECT status
    FROM app.orders
    WHERE order_id = p_order_id;
$fn$;

REVOKE ALL ON FUNCTION app.get_order_status(BIGINT)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app.get_order_status(BIGINT)
TO app_reader;
```

### 21.3. In SECURITY INVOKER Functions

This is the default for ordinary functions: the caller needs appropriate underlying object privileges while the function executes.

### 21.4. In SECURITY DEFINER Functions

The function can run with the owner's privileges; the caller needs `EXECUTE` on the function but does not necessarily need direct `SELECT`/`UPDATE` on the underlying tables the function touches.

### 21.5. A Read-Only Role Can Write Indirectly

If a role lacks `UPDATE` on tables yet has `EXECUTE` on a `SECURITY DEFINER` function that performs `UPDATE`, the role can mutate the database through that function. Thus "no table `UPDATE`" is **insufficient** to prove a role is functionally read-only.

### 21.6. GRANT EXECUTE Must Specify the Signature

With overloaded functions, syntax such as:

```sql
GRANT EXECUTE ON FUNCTION app.get_order_status(BIGINT)
TO app_reader;
```

identifies the exact function by parameter types; never omit signatures when referencing overloaded names.

---

## 22. SECURITY DEFINER and the Principle of Least Privilege

A `SECURITY DEFINER` function is a powerful tool for exposing a narrow operation without granting underlying table privileges to the caller.

Because it runs with elevated privileges, however, it is also an attack target if `search_path`, dynamic SQL, or input validation is neglected.

### 22.1. Example Limiting Returned Data

In the `sec379_lab` lab, we can create a function returning only the stock of a SKU, without exposing `unit_cost` or `internal_note`:

```sql
SET ROLE sec379_owner;

CREATE FUNCTION sec379_lab.lookup_stock(p_sku TEXT)
RETURNS INTEGER
LANGUAGE SQL
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
    SELECT i.stock
    FROM sec379_lab.inventory AS i
    WHERE i.sku = p_sku;
$fn$;

REVOKE ALL ON FUNCTION sec379_lab.lookup_stock(TEXT)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION sec379_lab.lookup_stock(TEXT)
TO sec379_read;

RESET ROLE;
```

**Note:** The function is owned by `sec379_owner`. It runs with the owner's privileges under `SECURITY DEFINER` semantics. Key objects are schema-qualified; `search_path` includes only trusted schemas.

### 22.2. Why Does SET search_path Matter?

If a function executes with owner privileges yet resolves an unqualified table/function name through a schema where the caller can create objects, the caller may inject a spoofed object into name resolution.

Setting a safe `search_path` and schema-qualifying critical names mitigates this risk.

### 22.3. Consider the Placement of pg_temp

The temporary schema has special name-lookup rules. When writing `SECURITY DEFINER` code, it is standard practice to place `pg_temp` at the end of a controlled `search_path` so temporary objects cannot shadow trusted objects.

### 22.4. Do Not Leave Default PUBLIC EXECUTE on Sensitive Functions

When deploying, create the function, revoke `PUBLIC`, and grant only the intended role within **the same safe transaction** when appropriate, avoiding a window where the new function has overly broad permissions.

### 22.5. Do Not Leak Secrets via MESSAGE/DETAIL

A function returning only `stock` that throws `RAISE EXCEPTION 'Unit cost is ...'` on error still leaks sensitive information. Inspect error messages, `HINT`s, return values, and timing against your threat model.

### 22.6. SECURITY DEFINER Does Not Replace Tenant Verification

A function accepting a client-supplied `p_tenant_id` and reading all tenants with owner privileges can become a cross-tenant read vulnerability. Derive tenant identity from a trusted source, never from unvalidated input alone.

### 22.7. Do Not Create Privileged Functions When Plain GRANTs Suffice

If a role simply needs `SELECT` on two columns of a table, a column-level `GRANT` or a properly owned/permissioned read-only view can be simpler than a `SECURITY DEFINER` function.

---

## 23. View Ownership and security_invoker

A view is not a physical copy of data, yet it has an owner and `SELECT` privileges like any schema object.

### 23.1. Default Views

For an ordinary view, permission checks on underlying tables and RLS can be evaluated against the **view owner** per PostgreSQL semantics. This allows granting `SELECT` on a view without granting the caller direct `SELECT` on the entire underlying table.

### 23.2. Risk

If the view owner has broad privileges or is the table owner bypassing RLS, an unchecked published view may return rows the caller should not see.

### 23.3. security_invoker (PostgreSQL 15+)

```sql
CREATE VIEW app.v_orders_invoker
WITH (security_invoker = true)
AS
SELECT order_id, tenant_id, status
FROM app.orders;
```

With this option, underlying table permissions and RLS are evaluated using the caller's privileges per feature rules, instead of defaulting to the view owner.

### 23.4. A Change That Can Break Consumers with Permission Denied

If callers hold `SELECT` on the view without underlying table privileges, enabling `security_invoker=true` can cut off their read access. This is a security/contract change, not merely a SQL optimization.

### 23.5. security_barrier Differs from security_invoker

- `security_invoker` determines whose privileges are checked on underlying tables.
- `security_barrier` restricts certain predicate pushdowns to reduce information-leak risks when a view performs security row filtering.

Do not confuse these two options or treat them as automatic replacements for RLS.

---

## 24. Row-Level Security and Owner Bypass

RLS restricts which rows are visible or modifiable by applicable roles.

For example:

```sql
ALTER TABLE app.tenant_orders
ENABLE ROW LEVEL SECURITY;
```

Once RLS is enabled, appropriate policies determine which rows can be viewed or written by roles subject to RLS.

### 24.1. Table Owners Normally Bypass RLS

By default, a table owner is not subject to RLS like an ordinary role. This is why you **never use the table-owner role as the login for a tenant API**.

### 24.2. FORCE ROW LEVEL SECURITY

```sql
ALTER TABLE app.tenant_orders
FORCE ROW LEVEL SECURITY;
```

subjects the table owner to RLS policies under PostgreSQL rules as well, except for special privileges that still bypass RLS.

### 24.3. Superuser and BYPASSRLS

Superusers and roles with `BYPASSRLS` still bypass RLS; `FORCE ROW LEVEL SECURITY` does not constrain them like ordinary users.

### 24.4. RLS Is Not a Schema/Table Privilege

The caller still needs the corresponding `SELECT`/`UPDATE` privilege on the table. RLS filters the row set; it does not grant DML privileges that were never granted.

### 24.5. RLS Policies Can Combine

PostgreSQL supports permissive and restrictive policies and separate clauses for `SELECT`/`INSERT`/`UPDATE`/`DELETE`. Never infer from "there is one tenant filter policy" that all write operations are automatically safe.

### 24.6. Avoid Designs Relying on Arbitrary SET app.tenant_id

A condition like:

```sql
USING (
    tenant_id =
    current_setting('app.tenant_id')::INTEGER
)
```

simply reads a session setting. If untrusted SQL callers can arbitrarily set `app.tenant_id` to another tenant, that setting is **not** a trustworthy authentication source.

Using session context to enforce tenant isolation requires a strict authentication and connection/pooling architecture preventing client spoofing, plus testing across every access path.

---

## 25. Extended Lab: Testing RLS by Role

We can test a minimal RLS model where a role can see only tenant 10. This is an example for learning policy structure; production typically requires a more flexible role/identity model.

### 25.1. Creating the Table and Data

```sql
SET ROLE sec379_owner;

CREATE TABLE sec379_lab.tenant_orders (
    tenant_id INTEGER NOT NULL,
    order_id BIGINT NOT NULL,
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    PRIMARY KEY (tenant_id, order_id)
);

INSERT INTO sec379_lab.tenant_orders (
    tenant_id, order_id, amount
)
VALUES
    (10, 1001, 100.00),
    (10, 1002, 200.00),
    (20, 1001, 300.00);

ALTER TABLE sec379_lab.tenant_orders
ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant10_reader
ON sec379_lab.tenant_orders
FOR SELECT
TO sec379_app_reader
USING (tenant_id = 10);

GRANT SELECT ON TABLE sec379_lab.tenant_orders
TO sec379_app_reader;

RESET ROLE;
```

### 25.2. Querying as the Consumer Role

```sql
SET ROLE sec379_app_reader;

SELECT tenant_id, order_id, amount
FROM sec379_lab.tenant_orders
ORDER BY tenant_id, order_id;

RESET ROLE;
```

In this example, the consumer role matches the tenant 10 policy and sees only tenant 10 rows.

### 25.3. Querying as the Owner

If the owner queries the table in the lab environment, the owner bypasses RLS by default and can see both tenant 10 and tenant 20.

### 25.4. Testing FORCE RLS

```sql
SET ROLE sec379_owner;

ALTER TABLE sec379_lab.tenant_orders
FORCE ROW LEVEL SECURITY;

RESET ROLE;
```

Afterward, the owner is subject to policies; if no policy covers the owner, the query may return 0 rows. Superusers and `BYPASSRLS` roles still bypass RLS per system rules.

### 25.5. Never Use a Superuser Test to Prove RLS

An administrator with superuser privileges can see all rows even when consumer roles are properly restricted by RLS. Always test using **the actual effective application role**, not just an admin account.

### 25.6. Per-Role Policies Are Illustrative Only

Do not create tens of thousands of static policies if a system has many tenants. Choose a protected, operable identity/role/session model and understand its performance cost and security surface.

---

## 26. Default Privileges: Permissions for Future Objects

A `GRANT` on existing tables **does not automatically apply to tables created tomorrow**.

PostgreSQL provides:

```sql
ALTER DEFAULT PRIVILEGES
FOR ROLE owner_role
IN SCHEMA some_schema
GRANT SELECT ON TABLES TO reader_role;
```

Meaning: when **`owner_role`** creates objects of the matching type in that schema in the future, PostgreSQL applies those default grants.

### 26.1. Affects Future Objects Only

`ALTER DEFAULT PRIVILEGES` does not retroactively modify the ACLs of existing tables.

### 26.2. Tied to the Role Creating the Object

Default privileges do not naively apply across every role membership. You must identify the **actual object-creating role** in migrations, especially when using `SET ROLE`.

If a migration connects as `deploy_admin` without running `SET ROLE app_owner`, new objects may be created with `deploy_admin` as owner and `deploy_admin`'s default privileges—not `app_owner`'s as intended.

### 26.3. Example in a Separate Reporting Schema

Create a schema containing only non-sensitive read models:

```sql
CREATE SCHEMA sec379_reports
AUTHORIZATION sec379_owner;

GRANT USAGE ON SCHEMA sec379_reports TO sec379_read;

ALTER DEFAULT PRIVILEGES
FOR ROLE sec379_owner
IN SCHEMA sec379_reports
GRANT SELECT ON TABLES TO sec379_read;
```

Thereafter, whenever `sec379_owner` creates tables or views in the reporting schema, default privileges grant `SELECT` to reader per configuration.

### 26.4. Why Not Apply SELECT ALL to Every Internal Table?

If a schema holds unit costs, tokens, PII, secrets, or access-control columns, a `GRANT SELECT ON TABLES` default rule for reader can automatically expose new sensitive objects or columns.

Least privilege requires **proper schema separation and default-privilege reviews**, not broad defaults configured just to avoid writing explicit `GRANT`s.

### 26.5. Global and Schema-Scoped Default Privileges Combine

A global default grant can apply broadly. A schema-scoped `REVOKE` does not necessarily negate privileges granted via global defaults. Inspect how rules compose and design a consistent strategy.

### 26.6. Do Not Confuse with Role Attributes

`ALTER DEFAULT PRIVILEGES` alters permissions on **future created objects**, not `LOGIN`/`CREATEROLE`/`SUPERUSER` attributes or memberships on a role.

---

## 27. GRANT ON ALL TABLES Differs from ALTER DEFAULT PRIVILEGES

The two commands operate on different timeframes:

```sql
GRANT SELECT ON ALL TABLES IN SCHEMA reporting
TO reporting_reader;
```

versus:

```sql
ALTER DEFAULT PRIVILEGES
FOR ROLE reporting_owner
IN SCHEMA reporting
GRANT SELECT ON TABLES TO reporting_reader;
```

### 27.1. ALL TABLES IN SCHEMA

Applies to supported tables/views **currently existing** at the moment the command executes.

### 27.2. ALTER DEFAULT PRIVILEGES

Applies to **objects created in the future**, without backfilling older objects.

### 27.3. When Deploying a New Reporting Schema

If policy genuinely allows reader to view all current and future reporting objects, both mechanisms may be needed.

### 27.4. When Permissions Must Be Per-Object

If the reporting schema contains datasets of varying sensitivity, avoid broad `ALL TABLES`/default grants. Grant explicitly per published view/table.

### 27.5. Multiple Creator Roles

Within a single schema, if service A creates tables and service B creates tables under a different role, default privileges defined for `owner_role` A do not govern objects created by B. Controlling **who runs DDL** is part of least privilege.

---

## 28. Predefined Roles Requiring Caution

PostgreSQL provides several built-in roles for administration and observability. Exact names and capabilities vary across versions.

Examples:

| Predefined role | General purpose |
| --- | --- |
| `pg_monitor` | Broader observability/monitoring capabilities than ordinary roles |
| `pg_read_all_settings` | Read many configuration settings |
| `pg_read_all_stats` | Read extensive statistics |
| `pg_signal_backend` | Send signals to backends within limits |
| `pg_read_all_data` | Broad read access across data per role semantics |
| `pg_write_all_data` | Broad write access per role semantics |
| `pg_read_server_files` | Read files on the server within limits and high-risk characteristics |
| `pg_write_server_files` | Write files on the server within limits and high-risk characteristics |
| `pg_execute_server_program` | Execute server-side programs in supported contexts |

### 28.1. Do Not Treat Predefined Roles as "Harmless Utility Groups"

A role that reads all data or accesses server files has massive reach. Evaluate it with the same rigor as administrative privileges.

### 28.2. pg_read_all_data Does Not Automatically Bypass All RLS

This role provides broad read coverage over objects per its definition, yet **does not implicitly grant `BYPASSRLS`**. That distinguishes it from superusers or roles explicitly granted `BYPASSRLS`.

### 28.3. pg_monitor Does Not Replace Business Reporting Roles

A dashboard monitoring CPU and connections has different requirements from a system reading revenue or PII. Never grant `pg_monitor` just because a role needs to read a reporting table.

### 28.4. File/Server-Program Roles Carry High Risk

Reading/writing files on the PostgreSQL server or executing server programs opens an impact surface beyond database objects. Grant only to trusted operators under strict controls.

### 28.5. Check Your Version

Do not assume every predefined role listed above exists in all PostgreSQL versions; check `pg_roles` and the documentation for your deployed version.

---

## 29. CREATEROLE, Membership, and Privilege Escalation Paths

A role with `CREATEROLE` can manage roles within the limits allowed by the system. However, this feature has critical nuances around membership and grant options.

### 29.1. Understand That Role Management Differs from Data Privileges

If you grant `CREATEROLE` to a runtime API, the API can not only read/write data, but also potentially alter the permission model of other roles within certain bounds.

### 29.2. PostgreSQL 16 Changed Membership Administration Semantics

`ADMIN`, `INHERIT`, and `SET` membership options are governed much more explicitly. Never copy role-grant scripts from PostgreSQL 14 to PostgreSQL 16 without verifying the new semantics.

### 29.3. Avoid Granting Unnecessary Privileged Memberships

For instance, an account granted membership in an owner role may be able to run `SET ROLE` and execute DDL depending on membership options. This is an indirect privilege path easily missed by direct ACL checks.

### 29.4. Audit Role-to-Role Grants Too

Do not audit only:

```sql
GRANT SELECT ON table ...
```

but also:

```sql
GRANT powerful_role TO runtime_role;
```

and whether the runtime role can actually exercise those privileges.

### 29.5. Principle

Only authorized provisioning/migration accounts need role administration. Never include this privilege in an application pool or reporting job.

---

## 30. Inspecting Role Attributes via pg_roles

The `pg_roles` catalog exposes basic role attributes without accessing sensitive password hashes.

```sql
SELECT
    rolname,
    rolcanlogin,
    rolsuper,
    rolcreaterole,
    rolcreatedb,
    rolreplication,
    rolbypassrls,
    rolinherit,
    rolconnlimit
FROM pg_catalog.pg_roles
WHERE rolname LIKE 'sec379_%'
ORDER BY rolname;
```

### 30.1. What to Confirm

In the lab, `sec379_*` roles are created with `NOLOGIN`, no `SUPERUSER`, no `CREATEDB`, no `CREATEROLE`, and no `BYPASSRLS`.

### 30.2. Role Attributes Do Not Describe Full Privileges

A role with `rolsuper=false` can still read sensitive data if granted `SELECT` via another role or a privileged membership.

### 30.3. Do Not Read pg_authid in Applications

Sensitive authentication data lives in protected catalogs. Never grant access to password catalogs just to check basic role attributes; use `pg_roles` and appropriate administrative tools.

### 30.4. Query to Find Superusers

In an authorized environment:

```sql
SELECT rolname
FROM pg_catalog.pg_roles
WHERE rolsuper
ORDER BY rolname;
```

Keep the number of superusers small and intentional. Never drop or modify administrative roles without a cluster access recovery plan.

### 30.5. Query to Find BYPASSRLS

```sql
SELECT rolname
FROM pg_catalog.pg_roles
WHERE rolbypassrls
ORDER BY rolname;
```

Especially critical for systems relying on RLS for tenant isolation.

---

## 31. Checking Owners of Schemas, Tables, and Functions

### 31.1. Schema Owner

```sql
SELECT
    n.nspname AS schema_name,
    pg_catalog.pg_get_userbyid(n.nspowner)
        AS schema_owner
FROM pg_catalog.pg_namespace AS n
WHERE n.nspname IN ('sec379_lab', 'sec379_reports')
ORDER BY n.nspname;
```

### 31.2. Table/View/Sequence Owner

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind,
    pg_catalog.pg_get_userbyid(c.relowner)
        AS object_owner
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'sec379_lab'
ORDER BY c.relkind, c.relname;
```

Common `relkind` values:

- `r`: ordinary table.
- `p`: partitioned table.
- `v`: view.
- `m`: materialized view.
- `S`: sequence.
- `i`: index.

### 31.3. Function Owner

```sql
SELECT
    n.nspname AS schema_name,
    p.proname AS function_name,
    pg_catalog.pg_get_userbyid(p.proowner)
        AS function_owner,
    pg_catalog.pg_get_function_identity_arguments(p.oid)
        AS arguments,
    p.prosecdef AS security_definer
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE n.nspname = 'sec379_lab'
ORDER BY p.proname;
```

### 31.4. Why Check Owners After Migrations?

If a migration ran as `deploy_admin` instead of `SET ROLE sec379_owner`, new tables can end up with an unexpected owner. That affects subsequent DDL, default privileges, and potentially RLS/view behavior.

---

## 32. Checking Effective Privileges with has_*_privilege

PostgreSQL provides functions to check effective privileges for a specific role and object.

### 32.1. Schema Usage

```sql
SELECT pg_catalog.has_schema_privilege(
    'sec379_app_reader',
    'sec379_lab',
    'USAGE'
) AS can_use_schema;
```

### 32.2. Table-Level SELECT

```sql
SELECT pg_catalog.has_table_privilege(
    'sec379_app_reader',
    'sec379_lab.inventory',
    'SELECT'
) AS table_select_granted;
```

In the lab, the role only received **column-level** `SELECT`. Thus you must not infer table-level `SELECT` is `TRUE` merely because it can read `sku` and `stock`.

### 32.3. Column-Level SELECT

```sql
SELECT
    pg_catalog.has_column_privilege(
        'sec379_app_reader',
        'sec379_lab.inventory',
        'sku',
        'SELECT'
    ) AS can_read_sku,
    pg_catalog.has_column_privilege(
        'sec379_app_reader',
        'sec379_lab.inventory',
        'stock',
        'SELECT'
    ) AS can_read_stock,
    pg_catalog.has_column_privilege(
        'sec379_app_reader',
        'sec379_lab.inventory',
        'unit_cost',
        'SELECT'
    ) AS can_read_cost;
```

`can_read_sku` and `can_read_stock` are expected to be `TRUE`, while `can_read_cost` is expected to be `FALSE` unless other grants widen access.

### 32.4. Function EXECUTE

```sql
SELECT pg_catalog.has_function_privilege(
    'sec379_app_reader',
    'sec379_lab.lookup_stock(text)',
    'EXECUTE'
) AS can_call_lookup;
```

### 32.5. Effective Privilege Checks Do Not Replace Query Testing

A function privilege check may confirm the role has `EXECUTE`, yet the function body can still fail due to underlying object privileges, `search_path`, RLS, constraints, or business logic.

Test using both helper functions and real queries from the caller's context.

### 32.6. Reading Raw ACLs Is Not Enough

ACL columns such as `relacl` can be `NULL` when using default ACLs, and role membership/`PUBLIC` causes effective privileges to differ from a single entry. Use helper functions and test role contexts when answering "what can this role actually do?".

---

## 33. psql Meta-Commands for Inspecting Privileges

When using `psql`:

```text
\du
\du+
\dn+
\dp sec379_lab.*
\z sec379_lab.*
\df+ sec379_lab.*
```

General meanings:

- `\du`: roles and role attributes.
- `\dn+`: schemas and related privileges.
- `\dp`/`\z`: access privileges on relations.
- `\df+`: function information.

These commands are **`psql` meta-commands**, not raw SQL to send through JDBC.

### 33.1. Why Check Multiple Sources?

A role can receive privileges through:

- Direct grants.
- Role memberships.
- `PUBLIC`.
- Ownership.
- Predefined role attributes.
- Security-definer views/functions.
- Special privileges such as superuser/`BYPASSRLS`.

A single `\dp` output does not expose every indirect path for every action.

### 33.2. In CI/CD

You can write automated permission tests using `has_*_privilege` functions and controlled test queries instead of relying on an operator visually inspecting `\du` output.

---

## 34. Transferring Ownership: ALTER ... OWNER TO

When restructuring permissions, you may need to transfer object ownership.

For example:

```sql
ALTER TABLE app.orders OWNER TO new_owner;
```

### 34.1. Requirements Go Beyond GRANT UPDATE

Typically, changing ownership requires the executing role to hold ownership/ability to act on behalf of the owner per PostgreSQL rules, permission to transition to the new owner, and the new owner having the required schema privileges. Superusers can perform actions beyond non-superuser limits.

### 34.2. Why Not Transfer Ownership to a Runtime Login?

If the goal is merely letting a service update the `stock` column, `GRANT UPDATE(stock)` is far more appropriate than `ALTER TABLE ... OWNER TO runtime_login`.

### 34.3. Changing Owner Affects RLS

The new owner may have different RLS behavior than the previous role (especially since owners bypass RLS by default). Review policies and view/function ownership at the same time.

### 34.4. Changing Owner Affects Maintenance/Migration Permissions

Subsequent migrations must run under a role authorized to modify the re-owned objects. Never change ownership locally without updating the full deployment pipeline.

### 34.5. Check Dependencies

Ownership of a table, its associated sequences, views, functions, or dependent objects does not automatically change together just because one table's owner changed. Audit each object type and its PostgreSQL rules.

---

## 35. REASSIGN OWNED and DROP OWNED

When an employee leaves or an old role must be removed, do not immediately run `DROP ROLE` if the role still owns objects.

### 35.1. REASSIGN OWNED

```sql
REASSIGN OWNED BY old_owner TO new_owner;
```

transfers ownership of objects belonging to the old role within PostgreSQL's applicable scope, preserving the objects rather than deleting them.

### 35.2. DROP OWNED

```sql
DROP OWNED BY old_owner;
```

drops objects owned by the role in the current database and revokes privileges granted to the role under PostgreSQL semantics; **it is not a safe command for cleaning up a few minor grants**.

### 35.3. REASSIGN OWNED Does Not Revoke All Remaining Grants

After transferring ownership, you may need `DROP OWNED BY old_owner` to clear remaining privileges before running `DROP ROLE`, but you must understand exactly which objects are affected and run it in a controlled manner.

### 35.4. Multiple Databases in the Same Cluster

A role can own objects across multiple databases. Reassignment/cleanup steps must be executed per database as well as for shared objects; do not run them in a single database and assume the role has zero remaining dependencies.

### 35.5. Execution Privileges

`REASSIGN OWNED`/`DROP OWNED` require corresponding role membership/privileges. Never grant those to runtime services merely for operational convenience.

### 35.6. Do Not Use CASCADE Without Knowing the Impact

`DROP OWNED ... CASCADE` can cascade into dependent objects outside the diagram you thought belonged only to the old role. Before running in production, perform an inventory, prepare a backup/restore plan, and review dependencies.

---

## 36. Privileges of a Migration Role

Migrations require different capabilities from runtime. A sound model:

```text
Deployment pipeline
  |
  +-- authenticates with controlled deploy_login
  |
  +-- SET ROLE app_owner (when permitted)
        |
        +-- CREATE/ALTER TABLE
        +-- CREATE INDEX
        +-- CREATE/REPLACE VIEW
        +-- CREATE FUNCTION
        +-- ALTER DEFAULT PRIVILEGES per policy
  |
  +-- RESET ROLE
  |
  +-- deploys runtime GRANTs via reviewed scripts
```

### 36.1. Consistent Ownership

If all application objects are owned by `app_owner` (`NOLOGIN`), subsequent migrations are predictable regarding which role runs DDL and which default grants apply.

### 36.2. Do Not Use Superuser for Every Migration

Certain special administrative tasks may require high privileges, but most `CREATE`/`ALTER` operations on application objects can run through a scoped owner/migration role.

### 36.3. Separate Migration and App Pool Credentials

If the same secret deploys schemas and serves HTTP APIs, a runtime compromise can open the door to DDL. Separate credentials by responsibility.

### 36.4. Verify Privileges After Every Migration

A migration might accidentally create a function with `EXECUTE` to `PUBLIC` or a view with a different owner; CI/CD should catch this immediately.

### 36.5. Migration Rollback Is Not Just DROP

A migration that alters grants or ownership can strip application access or over-expose permissions. Rollbacks must revisit ACLs, default privileges, and dependencies—not merely drop a newly added table.

---

## 37. Designing Roles for a Multi-Component Application

A system may include a read API, write API, ETL job, BI, and operators.

| Component | Recommended privileges by need | Avoid granting |
| --- | --- | --- |
| Catalog read API | Schema `USAGE` + `SELECT` on needed columns/views | `SUPERUSER`, `ALTER`/`DROP`, `SELECT` PII |
| Inventory update API | `SELECT`/`UPDATE` on relevant columns or narrow function `EXECUTE` | `ALL TABLES`, `BYPASSRLS` |
| ETL job | `INSERT`/`UPDATE` on specific staging/target tables, sequence `USAGE` when needed | `CREATE ROLE`, `SUPERUSER` |
| BI dashboard | `SELECT` on appropriately scoped reporting views | Direct `SELECT` across all internal tables |
| Migration pipeline | DDL privileges via controlled owner role | Credentials shared with runtime |
| Monitoring | Selected observability predefined role and minimal metrics privileges | `pg_read_all_data` if only stats are needed |
| Backup | Approved backup privileges/tool with clear scope | Sharing API login |
| Break-glass admin | Very high privileges with auditing and approval | Regular use inside applications |

### 37.1. No Single "app" Role for the Entire System

A catalog-reading API and a settlement-processing worker carry different risk profiles. Separate roles along **task boundaries**, not combined merely because they live in the same repository.

### 37.2. Do Not Over-Fragment to the Point of Unmanageability

Least privilege does not require one role per `SELECT` statement. You can group privileges by equivalent responsibility and data sensitivity, provided the scope remains necessary and reviewable.

### 37.3. Time-Bounded Privileges

An operator account needing elevated privileges to resolve an incident can use temporary grants that expire or are revoked afterward. Never leave powerful memberships enabled indefinitely "just in case."

### 37.4. Never Share Service Accounts Across Environments

Dev, staging, and production require architecturally separate credentials and roles. Never bring a production superuser password into a local developer setup.

---

## 38. Read-Only Is Not Simply Lacking Table UPDATE

A role may lack direct `UPDATE` on tables yet still cause modifications via:

- `EXECUTE` on a `SECURITY DEFINER` function containing DML.
- Privileges from another group role.
- `SET ROLE` to an owner or privileged role.
- `CREATE` on a schema leading to malicious object resolution when referenced by a trusted function.
- Privileges on foreign tables or extensions with unexpected side effects.
- Unaudited predefined roles or server-level privileges.

### 38.1. Real Testing

Do not merely ask:

```sql
SELECT has_table_privilege(..., 'UPDATE');
```

Instead, test **every access path exposed to runtime** against your threat model.

### 38.2. Read-Only Roles Can Still Exhaust Resources

Heavy `SELECT` queries can consume CPU, I/O, memory, and locks, impacting availability. Least privilege on data access does not replace statement timeouts, quotas, pool limits, and query governance.

### 38.3. Read-Only Roles Can Still Read Sensitive Data

If `SELECT` is granted too broadly, lacking `UPDATE` does not protect PII or secrets. Least privilege must account for **the sensitivity of readable data**.

### 38.4. Protect SECURITY DEFINER Helpers

Even a function named `list_orders` could have side effects or leak data via errors. Review its body, owner, and permissions.

---

## 39. Passwords, Authentication, and TLS Do Not Replace ACLs

PostgreSQL uses various authentication mechanisms, configured primarily via `pg_hba.conf`, drivers, TLS, and infrastructure.

### 39.1. Valid Credentials Only Prove "Who Is Connecting"

SQL authorization must still be configured across roles, databases, schemas, and objects.

### 39.2. Use Proper Password Storage Mechanisms

`SCRAM-SHA-256` is a modern password authentication mechanism supported by PostgreSQL. Cluster and client configurations must match; avoid deprecated methods or broad `trust` configurations in production.

### 39.3. Never Hardcode Passwords in Migrations

```sql
-- Anti-pattern: never store a real password in a public migration file.
-- CREATE ROLE app_login LOGIN PASSWORD 'my-real-secret';
```

Provision credentials through approved secrets/infrastructure systems. SQL statements containing secrets can leak into shell history, logs, or CI systems.

### 39.4. TLS and Remote Connections

Good privileges still fail to protect credentials if traffic is exposed on the network or client/server identity is unverified. Use TLS, certificate validation, and appropriate network policies.

### 39.5. Rotate, Revoke, and Disable Logins

If a secret leaks, rotate/revoke it or lock the account per incident procedures. Never simply revoke one grant on one table if the account retains privileges via other paths.

---

## 40. Backup/Restore and Ownership

A backup contains not only data, but also ownership and grant metadata.

### 40.1. Restores Can Encounter Missing Roles

If a dump references ownership by `app_owner` while the target cluster lacks that role, restore steps may error or require mapping.

### 40.2. Superuser Restores Require Control

A superuser can restore objects more easily, yet resulting ownership/permissions may diverge from intent if tool options change. Audit privileges after restoring.

### 40.3. Options That Skip Restoring Owners/Grants

Tools such as `pg_dump`/`pg_restore` provide options affecting ownership and privileges (e.g., `--no-owner`, `--no-acl`). Using them changes the target database's privilege contract; plan to reapply grants, default privileges, and owners.

### 40.4. Backup Roles Do Not Always Need Superuser

Depending on logical dumps, physical backups, RLS, and data scope, backup roles require different privileges. Design a dedicated account with only the privileges needed for the chosen backup tool; never reuse an application superuser.

### 40.5. Test Restores for Permissions, Not Just Rows

After restoring, verify:

- Object owners.
- Schema `USAGE`/`CREATE`.
- `TABLE`/`SEQUENCE`/`FUNCTION` privileges.
- RLS enabled/disabled state and `FORCE RLS`.
- `SECURITY DEFINER` function ownership and `search_path`.
- Whether application logins hold the exact expected privileges.

---

## 41. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "A newly created LOGIN role automatically reads every table." | `LOGIN` only grants authentication ability; ACLs still apply |
| "NOLOGIN means the role has no privileges." | `NOLOGIN` can own objects or act as a privilege group |
| "An owner role differs from a reader only by having more GRANTs." | Ownership carries inherent `ALTER`/`DROP`/`GRANT` rights |
| "GRANT ALL on a table makes a role the owner." | No |
| "Revoking SELECT from the owner stops the owner from modifying the table." | Ownership is not stripped like an ordinary grant |
| "A schema owner automatically reads every table in the schema." | Not by default |
| "GRANT USAGE ON SCHEMA equals SELECT on every table." | No |
| "GRANT SELECT on a table doesn't need schema usage." | Both layers must be evaluated |
| "A column GRANT negates table-wide SELECT from another role." | Privileges accumulate across valid paths |
| "REVOKE FROM PUBLIC blocks grants through membership too." | No |
| "PUBLIC is a specific individual user." | It is a pseudo-role representing all roles |
| "The public schema means all data inside is public." | Schema name does not determine `SELECT` access |
| "Database CONNECT automatically grants table privileges." | No |
| "GRANT CREATE ON DATABASE is the CREATEDB role attribute." | Two distinct privileges |
| "Table INSERT automatically grants USAGE on every sequence." | Sequence/identity semantics must be checked |
| "A new function is executable only by the owner by default." | `PUBLIC` often receives `EXECUTE` by default |
| "An app without table UPDATE is definitely read-only." | `SECURITY DEFINER` or role memberships may write |
| "SET ROLE never requires permission." | Depends on membership/privileges |
| "INHERIT guarantees all owner/DDL rights propagate automatically." | Separate rules apply, plus PG16+ membership options |
| "CREATEROLE equals SUPERUSER." | No |
| "CREATEDB allows reading every database." | No |
| "pg_read_all_data automatically bypasses RLS." | Not by default |
| "BYPASSRLS can be safely granted to an API." | Breaks RLS boundaries |
| "Table owners are always constrained by RLS." | Owners bypass by default unless `FORCE` |
| "FORCE RLS constrains superusers too." | Superusers/`BYPASSRLS` remain special |
| "SECURITY DEFINER is just convenient for skipping GRANT SELECT." | Carries privilege escalation risks |
| "security_invoker and security_barrier are the same." | Different purposes |
| "A view hiding PII means the role cannot read the underlying table." | If table grants remain, it still can |
| "CREATE on schema public is always open to everyone." | Default changed in PG15; upgraded DBs may vary |
| "ALTER DEFAULT PRIVILEGES modifies existing tables." | Future objects only |
| "Default ACLs for owner A apply to objects created by role B." | Tied to the creator role |
| "GRANT ON ALL TABLES applies automatically to new tables." | No |
| "Schema-scoped REVOKE negates global default grants." | Not that simple |
| "Object owners after restore always match the source." | Restore options and roles affect the outcome |
| "DROP OWNED only removes a role's privileges." | It can drop owned objects as well as grants |
| "REASSIGN OWNED suffices to DROP ROLE across all databases." | Other databases may still hold grants/ownership |
| "DROP CASCADE has a small blast radius." | Can cascade across unexpected dependencies |
| "It doesn't matter who runs each migration." | Ownership and default grants change |
| "pg_roles tells the whole permission story." | ACLs, memberships, and RLS are also needed |
| "has_table_privilege SELECT false means no columns are readable." | Column-level grants may allow reading specific columns |
| "An account named admin is always a superuser." | Managed services may restrict it |
| "TLS authentication means GRANT/REVOKE is unnecessary." | Authentication differs from authorization |
| "RLS relying on an arbitrary session tenant setting is secure." | Callers may spoof the setting |
| "A low-privilege SELECT role is always safe from DoS." | Heavy queries still consume resources |
| "Permission denied should be fixed with SUPERUSER." | Find the minimal missing privilege instead |
| "Testing only allowed actions is enough." | Negative permission tests are also essential |

---

## 42. Practice Exercises

### Exercise 1 — Owner and SELECT

Create a table as an owner role and `GRANT SELECT` to a reader. List three actions the owner can perform that the reader cannot.

### Exercise 2 — NOLOGIN Group

Create a `warehouse_read NOLOGIN` role and an appropriate login role, grant membership, and verify effective `SELECT` privileges.

### Exercise 3 — Distinguishing session_user and current_user

Query both variables before and after a permitted `SET ROLE`. When do they differ?

### Exercise 4 — SUPERUSER

List at least five risks if an HTTP API connects as a superuser. Why should you never fix permission denied errors by adding `SUPERUSER`?

### Exercise 5 — CREATEDB vs. CREATE DATABASE Privilege

Compare the `CREATEDB` role attribute with `GRANT CREATE ON DATABASE`.

### Exercise 6 — BYPASSRLS

A system protects tenant data using RLS. Explain what happens if the runtime role is granted `BYPASSRLS`.

### Exercise 7 — pg_roles

Write a query listing roles with `rolsuper=true`, `rolbypassrls=true`, or `rolcreaterole=true`. Why must you also review roles that cannot `LOGIN`?

### Exercise 8 — CREATEROLE

Explain why role administration privileges should be separated from CRUD privileges. Note the membership option changes in PostgreSQL 16+ to watch for.

### Exercise 9 — PUBLIC

Why does `GRANT SELECT TO PUBLIC` not merely grant access to a single role named `PUBLIC`? Does `REVOKE` from `PUBLIC` remove another direct `GRANT`?

### Exercise 10 — Schema USAGE

Create a dedicated schema and grant `USAGE` to a reader without granting table `SELECT`. Can the reader `SELECT` from the table?

### Exercise 11 — Schema CREATE

Grant `CREATE` on a schema to a role. Why must this privilege be carefully reviewed if that schema appears on the `search_path` of a `SECURITY DEFINER` function?

### Exercise 12 — Column-Level SELECT

Create a table with `sku`, `stock`, and `unit_cost`, and grant `SELECT` only on `sku`/`stock`. Test `SELECT sku, stock` and `SELECT unit_cost` from the consumer role.

### Exercise 13 — SELECT *

A reader only has privileges on two columns; what happens with `SELECT *`? Why should API mappers select columns explicitly?

### Exercise 14 — Updating a Single Column

Grant `UPDATE(stock)` and `SELECT(sku, stock)`, and test a conditional `UPDATE`. Why can the role not `UPDATE` `unit_cost`?

### Exercise 15 — DELETE/TRUNCATE

Compare `DELETE` and `TRUNCATE` privileges. Does a role that only updates stock need either of these privileges?

### Exercise 16 — GRANT ALL

Explain in precise terms why `GRANT ALL ON TABLE` does not permit `ALTER TABLE ... DROP COLUMN` the way ownership does.

### Exercise 17 — Inherited Privileges

A login role receives `SELECT` from two different group roles, one of which has table-wide `SELECT`. Why is a column-level `REVOKE` on the other group insufficient to restrict column access?

### Exercise 18 — GRANT OPTION

Propose a scenario where a role genuinely needs `WITH GRANT OPTION`. Why should you never grant it to a reporting-only user?

### Exercise 19 — pg_namespace Ownership

Write a query listing schema owners. If a schema is owned by role A while a table inside it is owned by role B, who controls `ALTER TABLE` under ownership rules?

### Exercise 20 — pg_class Ownership

List `relname`, `relkind`, and owner of tables/views/sequences in a schema. Why should this check run after migrations?

### Exercise 21 — Function Owner

List functions with `prosecdef=true` along with function owner and signature. Why is this list an essential input for a security audit?

### Exercise 22 — PUBLIC EXECUTE

Create a function in the lab schema and inspect its `EXECUTE` privileges. Revoke `EXECUTE` from `PUBLIC` and grant to a specific role in the appropriate transaction.

### Exercise 23 — SECURITY INVOKER

A function reads a table using the caller's privileges. The caller holds `EXECUTE` on the function but lacks `SELECT` on the table: what error can occur?

### Exercise 24 — SECURITY DEFINER

Create a function returning a SKU's stock using owner privileges. Why must you verify that the caller cannot request `unit_cost` through an unintended path?

### Exercise 25 — search_path

Explain a name-shadowing scenario in `SECURITY DEFINER`. Why are schema-qualified table names and placing `pg_temp` appropriately so important?

### Exercise 26 — SECURITY DEFINER and Tenants

A `SECURITY DEFINER` function accepts an unverified `p_tenant_id` and `SELECT`s all orders for that tenant. Why does this create a cross-tenant read risk?

### Exercise 27 — View Owner

Create a view exposing a subset of columns. If the view owner bypasses RLS, how can a caller observe unexpected data?

### Exercise 28 — security_invoker

Create a view `WITH (security_invoker=true)` on PostgreSQL 15+. Why can a caller with only `SELECT` on the view hit permission denied on the underlying table?

### Exercise 29 — RLS Owner Bypass

Create a table with an RLS `SELECT` policy for tenant 10 only. Compare query results across a consumer role, the table owner, and a superuser (only in an authorized lab).

### Exercise 30 — FORCE RLS

Enable `FORCE ROW LEVEL SECURITY` and re-test as the owner. Does it subject superusers or `BYPASSRLS` roles to the policy?

### Exercise 31 — current_setting Tenant Context

A policy uses `current_setting('app.tenant_id')`, which the client can `SET` arbitrarily. Is this trustworthy tenant authorization? Propose a safer way to manage identity/context.

### Exercise 32 — The public Schema

On a test database, inspect who holds `USAGE`/`CREATE` on the `public` schema. Why might a database created prior to PG15 and upgraded differ from a newly created database?

### Exercise 33 — Database CONNECT

Inspect `CONNECT` grants on a separate database and distinguish them from table `SELECT`. Does revoking `CONNECT` affect new connections?

### Exercise 34 — Sequence USAGE

On a column with `DEFAULT nextval`, grant table `INSERT` without granting sequence privileges. Observe and explain the error that can occur.

### Exercise 35 — IDENTITY vs. Sequence

Compare privilege requirements on an identity column versus a manual `DEFAULT nextval`. Why should you not assume both mechanisms require identical privileges?

### Exercise 36 — ALTER DEFAULT PRIVILEGES

Configure default `SELECT` for reporting tables created by a specific owner role. Does a previously created table automatically receive the new privilege?

### Exercise 37 — ALL TABLES vs. Defaults

Write two statements to apply read access to existing tables and future tables. If the reporting schema contains sensitive data, what must you consider first?

### Exercise 38 — Creator Role Drift

A deployment forgets `SET ROLE app_owner`, so a new table is owned by `deploy_admin`. List three consequences regarding DDL, default ACLs, and security.

### Exercise 39 — has_column_privilege

Use `has_column_privilege` to verify that `app_reader` has `SELECT` on `sku` and `stock` but not `unit_cost`. Why can `has_table_privilege(..., 'SELECT')` alone be misleading?

### Exercise 40 — Negative Permission Tests

Design a test suite with 5 operations that must succeed and 5 operations that must return permission denied, executed under the real runtime role rather than a superuser.

### Exercise 41 — Predefined Roles

Compare the purposes of `pg_monitor`, `pg_read_all_data`, and `pg_write_all_data`. Does a job reading only connection statistics need `pg_read_all_data`?

### Exercise 42 — DROP OWNED

A role owns 30 tables and holds `SELECT` across 10 schemas. Why is `DROP OWNED BY role` a dangerous command if you only intended to revoke one grant?

### Exercise 43 — REASSIGN OWNED

Design an offboarding/decommissioning plan for an old role using `REASSIGN OWNED`, grant cleanup, multi-database checks, and only then `DROP ROLE`.

### Exercise 44 — Restoring Ownership

A dump is restored with `--no-owner`/`--no-acl`. Which privileges and owners must be re-established before allowing the API to serve traffic?

### Exercise 45 — Runtime vs. Migration

A system runs Flyway or Liquibase alongside an HTTP API. Design two login credentials, a `NOLOGIN` owner, and separate DDL vs. DML privileges.

### Exercise 46 — Role Credential Incident

If the runtime app password leaks, list the steps to rotate/disable it, revoke sessions per procedure, inspect unintended privileges, and audit queries.

### Exercise 47 — Is Read-Only Truly Read-Only?

A role has no `UPDATE` on any table, yet has `EXECUTE` on a `SECURITY DEFINER` function that runs `INSERT`. Can that role modify data? How do you detect it?

### Exercise 48 — Production Multi-Tenant

Design a permission model for 1,000 tenants, three microservices, revenue reporting, a migration pipeline, and several monitoring operators. Include ACLs, RLS, ownership, `security_invoker`/`definer`, role memberships, and negative permission tests.

---

## 43. Least Privilege Implementation Checklist

| Question | What to verify |
| --- | --- |
| Are sensitive assets identified? | PII, financial data, tokens, internal metadata |
| Are owner and runtime separated? | `NOLOGIN` owner; runtime owns no schemas/tables |
| Is ownership consistent? | Schemas/tables/views/functions/sequences |
| How many superusers exist? | Minimal, approved, and audited |
| Does runtime have `SUPERUSER`? | No |
| Does runtime have `CREATEROLE`/`CREATEDB`? | Only with a genuine, exceptional requirement |
| Does runtime have `REPLICATION`/`BYPASSRLS`? | Never in ordinary applications |
| Are overly broad predefined roles used? | `pg_read_all_data`/`pg_write_all_data`/file/program |
| Do login roles have separate credentials? | Never shared across production/dev |
| Are TLS and secure auth enabled? | `pg_hba`, SCRAM/cert, secrets |
| Are `NOLOGIN` privilege-group roles used? | Separating functions from accounts |
| Are unnecessary memberships present? | Review role-to-role grants |
| Can runtime `SET ROLE` to owner? | Never grant to runtime |
| Are PG16+ membership options verified? | `INHERIT`/`SET`/`ADMIN` |
| Are database `CONNECT` privileges scoped? | Granted per requirement |
| Are excess database `TEMP`/`CREATE` privileges present? | Inspect |
| Is schema `USAGE` scoped? | Only schemas requiring access |
| Is `CREATE` granted on sensitive schemas? | Never to untrusted roles |
| Does schema `public` grant `CREATE` to `PUBLIC`? | Check version and actual ACLs |
| Is table `SELECT` overly broad? | Use column-level or narrow views where appropriate |
| Are `INSERT`/`UPDATE` restricted? | Granted only on required tables/columns |
| Are unneeded `DELETE`/`TRUNCATE` granted? | Revoke |
| Are excess `REFERENCES`/`TRIGGER` granted? | Review |
| Are sequence privileges scoped? | Only sequences actually needed |
| Are identity and serial distinguished? | Test privileges against real schema |
| Do sensitive functions have `PUBLIC` `EXECUTE`? | `REVOKE` + `GRANT` to specific roles |
| Are `SECURITY DEFINER` functions audited? | Owner, body, `search_path`, inputs |
| Are object names schema-qualified? | Prevent name shadowing |
| Is dynamic SQL used in privileged functions? | Bind/quote properly, validate input |
| Do view owners hold overly broad rights? | Review RLS and base table privileges |
| Is `security_invoker` set properly? | Caller privileges and RLS align |
| Is `security_barrier` used when needed? | Do not confuse with invoker/RLS |
| Is RLS enabled on tenant tables? | Correct `SELECT`/`INSERT`/`UPDATE`/`DELETE` policies |
| Does table owner bypass RLS? | Check `FORCE RLS` and owner role |
| Does any role hold `BYPASSRLS`? | Never let runtime bypass policies |
| Is tenant context trustworthy? | Not spoofable by SQL callers |
| Are default privileges configured properly? | Creator role/schema/object type |
| Are broad `PUBLIC` grants present? | Audit |
| Are broad grants via other memberships present? | Audit effective privileges |
| Are excess `GRANT OPTION`/`ADMIN OPTION` present? | Revoke |
| Is the reporting schema separated? | Avoid exposing PII/secrets |
| Do migrations run under the right owner? | `SET ROLE` or standard owner identity |
| Is ownership checked after deployment? | `pg_namespace`/`pg_class`/`pg_proc` |
| Are permission helpers tested? | `has_schema`/`table`/`column`/`function_privilege` |
| Are negative tests included? | Sensitive `SELECT`, `UPDATE`, `ALTER` must fail |
| Are tests run with real login/roles? | Not just superuser |
| Are query resources controlled? | Timeouts, pools, monitoring |
| Is a credential revocation plan ready? | Rotation and incident response |
| Is a role retirement plan ready? | `REASSIGN OWNED`/`DROP OWNED`/`DROP ROLE` per scope |
| Are multiple databases present? | Audit ownership/privileges cluster-wide |
| Are role/grant restores tested? | Account for `--no-owner`/`--no-acl` |
| Is a role matrix documented? | Role names, scopes, owners, rationale |
| Are permissions reviewed periodically? | Drift detection |
| Are sensitive events audited? | Logging/auditing per policy |
| Is superuser restricted in CI? | Never share high privileges with normal pipelines |
| Are ACL changes managed as code? | Migrations/review/rollback |

## Conclusion

**Ownership, superusers, and the principle of least privilege** form the foundation of secure PostgreSQL operations. Three concepts must be kept distinct:

1. **The owner controls object definition and lifecycle.** An owner's `ALTER`/`DROP`/`GRANT` rights are not equivalent to a granted list of `SELECT`/`UPDATE` privileges. Never let a runtime login own tables merely because the application needs to read and write.
2. **Superuser carries cluster-wide authority.** Never treat superuser as a convenient fix for permission denied; managed PostgreSQL services may also provide restricted admin accounts.
3. **Least privilege means privileges matched to the task, not merely lacking `SUPERUSER`.** Evaluate databases, schemas, tables, columns, sequences, functions, views, role memberships, default privileges, and RLS.
4. **`NOLOGIN` owner + privilege group roles + runtime login** is a practical pattern for separating deployments from daily operations.
5. **`PUBLIC`, memberships, and `GRANT OPTION` create indirect privilege paths.** A single `REVOKE` does not automatically override other grants.
6. **Column-level `GRANT`s and narrow views reduce the readable data surface.** However, you must check for broader privileges from other sources and owner-executed functions.
7. **RLS has critical exceptions.** Table owners normally bypass RLS by default; `FORCE RLS` has limits, and `SUPERUSER`/`BYPASSRLS` retain special privileges.
8. **`SECURITY DEFINER` requires defensive design.** Signatures, `search_path`, `PUBLIC` `EXECUTE`, ownership, and tenant logic can all create privilege escalation paths.
9. **Default privileges must be bound to the exact creator role and creation time.** Do not confuse them with `GRANT`s on already-existing tables.
10. **Ownership and ACLs must be verified after migrations and restores.** Use catalogs, `has_*_privilege` functions, and negative tests executed under real roles.
11. **Role cleanup paths carry risk too.** `REASSIGN OWNED`, `DROP OWNED`, and `DROP ROLE` require plans accounting for multiple databases and dependencies.
12. **Least privilege is an ongoing process.** Maintain reviews, logging, credential governance, role-drift monitoring, and testing as the system evolves.

A strong PostgreSQL architecture does not merely ensure **who can log in**—it proves **who owns objects, who can change definitions, who can read each dataset, who can write through indirect paths, and what remains denied if an account is compromised**.
