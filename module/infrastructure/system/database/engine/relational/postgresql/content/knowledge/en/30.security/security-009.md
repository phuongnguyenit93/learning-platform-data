# FORCE ROW LEVEL SECURITY and Policy Bypass Cases in PostgreSQL

**Row-Level Security (RLS)** enables PostgreSQL to restrict **which rows a role is allowed to read, insert, update, or delete**. This feature is especially useful when a single table stores data belonging to multiple tenants, departments, customers, or groups with different permissions.

However, a very dangerous assumption is: "I enabled RLS, so everyone accessing the table is restricted by the policies." In PostgreSQL, several subjects **can bypass RLS policies**:

- **Superusers**.
- **Roles with the `BYPASSRLS` attribute**.
- **The table owner** by default, **unless** the table has `FORCE ROW LEVEL SECURITY` set.

Therefore, these two commands serve different purposes:

~~~sql
ALTER TABLE secure.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE secure.orders FORCE ROW LEVEL SECURITY;
~~~

The first command enables row-level policy enforcement; the second forces a **normal table owner** to also be subject to policies when RLS is enabled. **FORCE does not prevent superusers or BYPASSRLS roles from bypassing RLS.**

This article **"FORCE ROW LEVEL SECURITY and Policy Bypass Cases"**, part of the **Security** chapter in the **Database Engine Relational PostgreSQL** module, clarifies these exceptions, table owner behavior, the relationship with `GRANT`, `USING`/`WITH CHECK` policies, `row_security=off`, backups, views, `SECURITY DEFINER`, special operation paths, and how to verify behavior using real roles.

> **Practice scope:** only execute commands that create roles, change ownership, FORCE/DISABLE RLS, and run DML experiments in a dedicated lab database. In production, modifying RLS can expose data or break application functionality. Do not use superuser/BYPASSRLS accounts as regular application accounts.

---

## 1. Visualizing RLS Through a Multi-Tenant Problem

Suppose the `orders` table contains:

| order_id | tenant_id | amount | status |
|---:|---:|---:|---|
| 1 | 10 | 100.00 | paid |
| 2 | 10 | 80.00 | draft |
| 3 | 20 | 300.00 | paid |
| 4 | 20 | 40.00 | draft |

The application needs to guarantee:

- Users of tenant 10 can only read orders 1 and 2.
- Users of tenant 20 can only read orders 3 and 4.
- Users cannot insert or modify an order to belong to another tenant.
- Administrative tasks with broader privileges must be controlled.

If you rely solely on application SQL queries:

~~~sql
SELECT *
FROM orders
WHERE tenant_id = 10;
~~~

an endpoint that forgets the tenant predicate can return another tenant's data. RLS lets you enforce these conditions at the table level.

~~~sql
CREATE POLICY tenant_read ON secure.orders
FOR SELECT
USING (/* expression determining a valid tenant */);
~~~

This is an illustrative shape, not a runnable policy as-is. In the lab below, we will write a concrete expression.

## 2. Where Does RLS Sit in the Authorization Model?

A query that wants to read data must pass through multiple layers:

~~~text
Authentication and connection role
                 |
                 v
USAGE on schema, SELECT on table
                 |
                 v
Is there an RLS bypass exception?
                 |
                 v
RLS ENABLED and matching policy?
                 |
                 v
Rows SQL is allowed to return
~~~

RLS **does not grant SELECT privileges**. It only restricts rows when the role already has access privileges and RLS applies to that role.

Conversely, `GRANT SELECT` **does not isolate tenants by itself**. If table RLS is disabled or the role bypasses it, the role can read more rows than intended.

## 3. Four DDL Commands to Distinguish

~~~sql
ALTER TABLE secure.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE secure.orders FORCE ROW LEVEL SECURITY;
ALTER TABLE secure.orders NO FORCE ROW LEVEL SECURITY;
ALTER TABLE secure.orders DISABLE ROW LEVEL SECURITY;
~~~

| Command | Effect |
|---|---|
| `ENABLE` | Turns on policy enforcement for roles subject to RLS |
| `FORCE` | Forces a normal table owner to be subject to policies |
| `NO FORCE` | Restores the default table owner exemption |
| `DISABLE` | Turns off row policy enforcement on the table |

FORCE only performs actual filtering when the table has RLS **ENABLED**. The two states ("RLS enabled" and "owner forced to obey RLS") are stored separately.

### 3.1. FORCE Does Not Automatically Create Policies

If there is no SELECT policy for the owner, enabling FORCE can cause the owner to see **0 rows**. PostgreSQL does not automatically create an "owner-only policy".

### 3.2. NO FORCE Is Not DISABLE

NO FORCE does not exempt normal application roles from policies; it only restores the table ownership exemption.

### 3.3. DISABLE Can Expose Data

When DISABLED, any role with GRANT SELECT is no longer filtered by RLS. Therefore, never use DISABLE as a temporary workaround for a policy issue on a table holding multi-tenant data.

## 4. Behavior Matrix Before and After FORCE

Assume the table has RLS ENABLED, a policy allows viewing only a subset of rows, and the role holds the necessary table privileges.

| Subject | Without FORCE | With FORCE |
|---|---|---|
| Normal application role | Policy applied | Policy applied |
| Normal table owner | **Bypass** | **Policy applied** |
| Superuser | **Bypass** | **Bypass** |
| Role with `BYPASSRLS` | **Bypass** | **Bypass** |
| Role lacking SELECT | Permission denied | Permission denied |

This is the most important matrix in this article.

**FORCE is not a switch that forces every role to obey RLS. It only removes the default exemption of a table owner that has no other bypass privileges.**

## 5. Why Does the Table Owner Bypass Row Policies by Default?

The table owner is responsible for administering an object: altering its structure, setting grants and policies, and performing maintenance operations. By default, PostgreSQL treats the owner as exempt from RLS on its own table.

Consequence: if the application connects using the role that **owns the table**, RLS may not filter any rows even if you wrote the policy correctly.

~~~text
Application connection = table owner
                  |
                  v
RLS ENABLED, NO FORCE
                  |
                  v
Owner bypass: policy does not block rows
~~~

To avoid this:

1. Separate the **migration/table owner** role from the runtime role.
2. Do not grant DDL/ownership privileges to the app when unnecessary.
3. Consider FORCE for tables where even owner access needs control.
4. Test using the real application role, not only superuser.

## 6. What Does FORCE Do to the Owner?

~~~sql
ALTER TABLE secure.orders FORCE ROW LEVEL SECURITY;
~~~

When the table has RLS ENABLED:

- A normal owner no longer receives automatic RLS exemption.
- Applicable SELECT/INSERT/UPDATE/DELETE policies can apply to the owner.
- The owner views or writes data according to the applicable policies.
- If no matching policy exists, the operation may be filtered or rejected.

FORCE **does not** change the owner, add GRANTs, create policies, or populate the table with new data.

### 6.1. The Owner Still Retains DDL Authority

FORCE does not strip structural administrative authority from the owner. An owner with the appropriate privileges can alter policies or the table's RLS configuration. Therefore, FORCE **does not protect against a compromised table owner that is able to execute DDL**.

## 7. Superusers Still Bypass When FORCE Is Set

Superusers bypass row security policies by virtue of PostgreSQL privilege rules, even on tables with FORCE.

If you check:

~~~sql
SELECT COUNT(*) FROM secure.orders;
~~~

using the `postgres` superuser account and see all rows, that **does not prove FORCE is broken**. You are using a role with a higher exemption.

In production, superuser accounts should be reserved for controlled system administration, not as credentials for HTTP APIs or routine business jobs.

## 8. BYPASSRLS Is a Role Attribute

A role with `BYPASSRLS` bypasses RLS at the database level according to the privileges granted to it. It does not merely bypass a single table's policy.

This is not valid syntax:

~~~sql
-- There is no GRANT BYPASSRLS ON TABLE ...
~~~

BYPASSRLS is a **role attribute**, not a table-level grant.

Administrative example (do not run in production just to test):

~~~sql
CREATE ROLE dedicated_audit_admin
NOLOGIN BYPASSRLS;
~~~

Creating or altering roles with BYPASSRLS is an operation restricted to superusers under PostgreSQL's privilege rules.

### 8.1. BYPASSRLS Differs from the SELECT Privilege

A role with BYPASSRLS **still needs regular table/schema privileges**, unless it holds broader privileges like superuser. BYPASSRLS is not equivalent to an automatic GRANT SELECT across the entire database.

### 8.2. Do Not Grant It to app_service

If the role used for all requests has BYPASSRLS, a query that misses a tenant filter can read across tenants. Setting FORCE on the table will not fix that issue.

## 9. Role Membership and SET ROLE

You should not assume BYPASSRLS is inherited like a normal `GRANT SELECT` merely because one role is a member of another role. Special role attributes follow their own rules.

However, the ability to switch execution context via `SET ROLE` also matters: a session permitted to switch to a privileged role can change its active privileges during execution.

Check with:

~~~sql
SELECT session_user, current_user, current_role;
~~~

- `session_user`: the authenticated login identity.
- `current_user`: the current execution role in the active context.
- `current_role`: generally reflects the current active role.

When `SET ROLE` or `SECURITY DEFINER` is involved, the execution context can differ from the initial login role.

## 10. Inspecting rolbypassrls and rolsuper

~~~sql
SELECT
    rolname,
    rolsuper,
    rolbypassrls,
    rolcanlogin,
    rolinherit
FROM pg_roles
ORDER BY rolname;
~~~

Columns:

- `rolsuper`: whether the role has superuser privileges.
- `rolbypassrls`: whether the role has the BYPASSRLS attribute.
- `rolcanlogin`: whether the role can log in.
- `rolinherit`: information related to privilege inheritance via membership.

This is a metadata query; restrict its output to appropriate consumers and avoid exposing unnecessary internal details publicly.

## 11. Lab: Roles Used to Test RLS

This hands-on lab uses an **isolated lab database** where you have permission to create roles and change ownership. The following commands must be run by an administrator with sufficient privileges, such as a superuser in the test database.

Create three **NOLOGIN** roles:

~~~sql
CREATE ROLE rls_demo_owner NOLOGIN;
CREATE ROLE rls_demo_alice NOLOGIN;
CREATE ROLE rls_demo_bob NOLOGIN;
~~~

Purpose:

| Role | Purpose |
|---|---|
| `rls_demo_owner` | Table owner to test exemption/FORCE |
| `rls_demo_alice` | Runtime role for tenant 10 |
| `rls_demo_bob` | Runtime role for tenant 20 |

Because they are NOLOGIN, no password is needed. An authorized admin can use `SET ROLE` to simulate each role. Do not create these roles in an environment where roles with the same names already exist or where you are not authorized to make changes.

## 12. Lab: Creating the Schema, Table, and Sample Data

~~~sql
CREATE SCHEMA rls_lab;

CREATE TABLE rls_lab.orders (
    order_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    status TEXT NOT NULL
        CHECK (status IN ('draft','paid','cancelled'))
);

INSERT INTO rls_lab.orders (
    order_id, tenant_id, amount, status
)
VALUES
    (1, 10, 100.00, 'paid'),
    (2, 10,  80.00, 'draft'),
    (3, 20, 300.00, 'paid'),
    (4, 20,  40.00, 'draft');

ALTER TABLE rls_lab.orders
OWNER TO rls_demo_owner;
~~~

The table holds the exact four rows shown at the start of the article.

### 12.1. Granting Privileges to Runtime Roles

~~~sql
GRANT USAGE ON SCHEMA rls_lab
TO rls_demo_alice, rls_demo_bob;

GRANT SELECT ON rls_lab.orders
TO rls_demo_alice, rls_demo_bob;
~~~

Alice and Bob can read the table via GRANT, but cannot INSERT/UPDATE/DELETE yet because they were only granted SELECT.

## 13. Lab: ENABLE RLS and Read Policy

~~~sql
ALTER TABLE rls_lab.orders
ENABLE ROW LEVEL SECURITY;

CREATE POLICY orders_tenant_read
ON rls_lab.orders
FOR SELECT
TO PUBLIC
USING (
    (current_user = 'rls_demo_alice' AND tenant_id = 10)
    OR
    (current_user = 'rls_demo_bob' AND tenant_id = 20)
    OR
    (current_user = 'rls_demo_owner' AND tenant_id = 10)
);
~~~

The policy applies to all roles (`TO PUBLIC`), but the `USING` expression only permits:

- Alice: tenant 10.
- Bob: tenant 20.
- Owner: tenant 10 **if the owner is subject to policies**.

Using `current_user` clearly demonstrates changes in the execution role during the lab. In a multi-tenant application sharing a single DB role, a different safe tenant-identification model is required; we will discuss that later.

## 14. Lab: Testing Alice

In an admin session permitted to run `SET ROLE`:

~~~sql
SET ROLE rls_demo_alice;

SELECT
    current_user,
    order_id,
    tenant_id,
    amount
FROM rls_lab.orders
ORDER BY order_id;

RESET ROLE;
~~~

Expected result:

| order_id | tenant_id | amount |
|---:|---:|---:|
| 1 | 10 | 100.00 |
| 2 | 10 | 80.00 |

Because Alice is neither the owner nor a BYPASSRLS role, the policy filters out tenant 20 rows.

## 15. Lab: Testing Bob

~~~sql
SET ROLE rls_demo_bob;

SELECT
    current_user,
    order_id,
    tenant_id,
    amount
FROM rls_lab.orders
ORDER BY order_id;

RESET ROLE;
~~~

Expected result:

| order_id | tenant_id | amount |
|---:|---:|---:|
| 3 | 20 | 300.00 |
| 4 | 20 | 40.00 |

Both roles hold SELECT on the table, yet the policy produces two distinct datasets.

### 15.1. Do Not Substitute Superuser Results for Testing

A superuser admin sees all four rows, so testing solely as a superuser skips the exact mechanism taught in this article.

## 16. Lab: Owner Before FORCE

~~~sql
SET ROLE rls_demo_owner;

SELECT
    current_user,
    order_id,
    tenant_id
FROM rls_lab.orders
ORDER BY order_id;

RESET ROLE;
~~~

When RLS is ENABLED **but not FORCED**, a normal owner bypasses policies. Expected result: **all four orders 1, 2, 3, and 4**.

Notice: the policy expression only grants tenant 10 to the owner, yet PostgreSQL does not enforce it for an owner currently exempt from RLS.

## 17. Lab: FORCE and Re-Running the Same Query

Switch back to table-administration privileges:

~~~sql
ALTER TABLE rls_lab.orders
FORCE ROW LEVEL SECURITY;
~~~

Test again:

~~~sql
SET ROLE rls_demo_owner;

SELECT
    current_user,
    order_id,
    tenant_id
FROM rls_lab.orders
ORDER BY order_id;

RESET ROLE;
~~~

Expected result: **only orders 1 and 2**.

The FORCE operation did not delete the two tenant 20 rows. It changed whether policies are applied to the owner.

### 17.1. Do Alice and Bob Change?

Not under the current policy logic: both were already subject to RLS before FORCE. FORCE targets the normal owner's exemption.

### 17.2. The Owner Remains the Owner

Toggling FORCE is not equivalent to `ALTER TABLE ... OWNER TO ...`. The role owning the table is still `rls_demo_owner`.

## 18. Lab: Testing NO FORCE

~~~sql
ALTER TABLE rls_lab.orders
NO FORCE ROW LEVEL SECURITY;
~~~

The owner sees all four rows again because the ownership exemption is restored while the table has RLS ENABLED.

Return the table to the FORCE state:

~~~sql
ALTER TABLE rls_lab.orders
FORCE ROW LEVEL SECURITY;
~~~

This demonstrates a **metadata** change, not a change to the underlying data.

## 19. What Does DISABLE RLS Change?

Example (do not run in a real system just to test):

~~~sql
ALTER TABLE rls_lab.orders
DISABLE ROW LEVEL SECURITY;
~~~

Because Alice and Bob already hold SELECT privileges, their queries are **no longer filtered by RLS** and can return all four rows.

To restore the lab:

~~~sql
ALTER TABLE rls_lab.orders
ENABLE ROW LEVEL SECURITY;

ALTER TABLE rls_lab.orders
FORCE ROW LEVEL SECURITY;
~~~

### 19.1. FORCE=true While ENABLE=false?

The FORCE flag can still remain stored; if RLS is disabled, policies are not enforced. Do not merely look at FORCE in the catalog and conclude that tenant isolation is active.

## 20. Default Deny When Policies Are Missing

PostgreSQL applies **default deny** to roles subject to RLS when no policy permits the corresponding operation.

For example, if all SELECT policies are dropped while RLS remains ENABLED:

- Alice SELECT: normally 0 rows.
- Bob SELECT: normally 0 rows.
- Owner with FORCE: normally 0 rows.
- Owner with NO FORCE: bypass.
- Superuser/BYPASSRLS: bypass.

Do not confuse "SELECT returns 0 rows" with "the table's data was deleted".

For safe maintenance, investigate the policies and roles instead of reflexively running DISABLE RLS.

## 21. Inspecting Both RLS Flags in pg_class

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    pg_get_userbyid(c.relowner) AS owner_name,
    c.relrowsecurity AS rls_enabled,
    c.relforcerowsecurity AS rls_forced
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'rls_lab'
  AND c.relname = 'orders';
~~~

| relrowsecurity | relforcerowsecurity | Meaning |
|---|---|---|
| false | false | Row policies not applied |
| true | false | RLS applied, owner bypasses by default |
| true | true | RLS applied, normal owner subject to policies |
| false | true | FORCE flag set, but RLS is disabled |

These two columns are independent metadata. **Do not draw conclusions from `relforcerowsecurity` alone.**

## 22. Inspecting Policies in pg_policies

~~~sql
SELECT
    schemaname,
    tablename,
    policyname,
    permissive,
    roles,
    cmd,
    qual,
    with_check
FROM pg_policies
WHERE schemaname = 'rls_lab'
  AND tablename = 'orders'
ORDER BY policyname;
~~~

Key fields:

- `cmd`: `SELECT`, `INSERT`, `UPDATE`, `DELETE`, or `ALL`.
- `qual`: the `USING` expression.
- `with_check`: the `WITH CHECK` expression.
- `roles`: role scope.
- `permissive`: policy combination behavior.

**The existence of a policy does not prove it is in effect for a specific role.** You must also check ENABLE/FORCE, role bypass attributes, and the command being executed.

## 23. Inspecting in psql

The command:

~~~text
\d+ rls_lab.orders
~~~

is a **psql** meta-command that can display the table, its policies, and related attributes depending on the PostgreSQL version.

It is not standard SQL to run over JDBC.

## 24. row_security=off Is Not for Bypassing

PostgreSQL provides the parameter:

~~~sql
SHOW row_security;
SET row_security = off;
~~~

It is easy to misunderstand `row_security=off` as "do not apply policies, return all rows". **That understanding is wrong.**

This parameter is designed to prevent queries from being **silently** filtered by policies: if a query would be affected by row security in the relevant context, PostgreSQL can **raise an error**.

It **does not grant BYPASSRLS**, remove row policies, or change table ownership.

### 24.1. Lab Experiment

~~~sql
SET ROLE rls_demo_alice;

SET row_security = off;

SELECT *
FROM rls_lab.orders;

RESET row_security;
RESET ROLE;
~~~

This test is expected to trigger an RLS error; the goal is **not** to retrieve tenant 20 rows.

When a statement throws an error inside an explicit transaction, the transaction enters an aborted state until ROLLBACK. Test this in a separate lab session.

## 25. The row_security GUC vs. DISABLE

| Action | What Changes | Meaning |
|---|---|---|
| `ALTER TABLE ... DISABLE ROW LEVEL SECURITY` | Table state | Turns off RLS enforcement on the table |
| `SET row_security=off` | Session/context configuration parameter | Raises an error when row security filtering would apply according to rules |
| `ALTER TABLE ... FORCE ROW LEVEL SECURITY` | Table owner enforcement state | Forces a normal owner to obey policies |

Never treat one as another name for the other.

## 26. Why Does pg_dump Relate to RLS?

When taking backups, you normally need **all data**, not just the rows visible to a runtime tenant role.

`pg_dump` uses behavior tied to `row_security=off` to avoid silently exporting an incomplete subset due to policies. If the backup role is subject to RLS and lacks sufficient privilege to back up everything, the dump may fail with an error.

Some versions provide the option:

~~~text
pg_dump --enable-row-security ...
~~~

This allows dumping data according to the role's RLS policies, meaning **it may export only a subset**. It does not automatically produce a **full backup** capable of restoring the entire system.

### 26.1. FORCE Can Affect Owner-Based Backups

With FORCE enabled, a normal table owner is also subject to policies. A backup job that previously produced a full dump because it ran as the owner may now miss data or fail.

Proper handling:

1. Determine whether the goal is a full backup or a tenant-scoped export.
2. Select a backup role/privileges through approved governance controls.
3. Verify row counts, restore behavior, and completeness.
4. Do not grant BYPASSRLS to a runtime app role just to fix a backup failure.
5. Do not DISABLE RLS in production just to run a one-off `pg_dump`.

## 27. Which Operations Does RLS Control?

RLS governs the following operations:

- `SELECT`: which rows can be read.
- `INSERT`: which new rows are valid.
- `UPDATE`: which existing rows can be modified and which resulting rows are valid.
- `DELETE`: which existing rows can be deleted.

Policies can differ per command.

Core mechanism:

- `USING (predicate)` generally controls **existing** rows that the role can see/target.
- `WITH CHECK (predicate)` controls **new** row data resulting from INSERT/UPDATE.

Never define only a SELECT policy and assume all write operations are automatically protected by the same condition.

## 28. INSERT Policy for Alice

In the lab, you can allow Alice to insert orders for tenant 10:

~~~sql
GRANT INSERT ON rls_lab.orders TO rls_demo_alice;

CREATE POLICY orders_alice_insert
ON rls_lab.orders
FOR INSERT
TO rls_demo_alice
WITH CHECK (tenant_id = 10);
~~~

Valid:

~~~sql
SET ROLE rls_demo_alice;

BEGIN;

INSERT INTO rls_lab.orders (
    order_id, tenant_id, amount, status
)
VALUES (100, 10, 25.00, 'draft');

ROLLBACK;

RESET ROLE;
~~~

The new row has tenant 10 so `WITH CHECK` accepts it; ROLLBACK keeps the lab untouched.

### 28.1. Attempting to Create a Tenant 20 Order

~~~sql
-- Run as role Alice in the lab; expected to be rejected:
INSERT INTO rls_lab.orders (
    order_id, tenant_id, amount, status
)
VALUES (101, 20, 25.00, 'draft');
~~~

The `WITH CHECK (tenant_id=10)` policy forbids inserting a tenant 20 row. In a failed transaction, you must ROLLBACK before running further queries.

## 29. UPDATE Policies Must Check Before and After

~~~sql
GRANT UPDATE ON rls_lab.orders TO rls_demo_alice;

CREATE POLICY orders_alice_update
ON rls_lab.orders
FOR UPDATE
TO rls_demo_alice
USING (tenant_id = 10)
WITH CHECK (tenant_id = 10);
~~~

Meaning:

1. Alice can only target existing rows belonging to tenant 10.
2. Alice cannot update a valid row so that it becomes tenant 20.

Example rejected by `WITH CHECK`:

~~~sql
UPDATE rls_lab.orders
SET tenant_id = 20
WHERE order_id = 1;
~~~

When an UPDATE query has a `WHERE` clause, `RETURNING`, or expressions needing to read columns, related SELECT privileges/policies may also apply; test the exact SQL issued by JDBC/ORM.

## 30. DELETE Policy and TRUNCATE

~~~sql
GRANT DELETE ON rls_lab.orders TO rls_demo_alice;

CREATE POLICY orders_alice_delete
ON rls_lab.orders
FOR DELETE
TO rls_demo_alice
USING (tenant_id = 10);
~~~

The DELETE policy prevents Alice from targeting tenant 20 rows under RLS rules.

**However, TRUNCATE is a different operation**, and is not filtered row-by-row by DELETE policies. Never grant TRUNCATE to a tenant application role.

## 31. Owner Write Permissions After FORCE

An easily overlooked detail: FORCE applies to the owner not only for SELECT, but also for other RLS-governed commands.

In our lab, there is a SELECT policy for the owner, but no INSERT/UPDATE/DELETE policy for the owner. Once FORCED, owner write operations can be restricted or rejected even though the owner owns the table.

If an owner job must UPDATE tenant 10:

~~~sql
CREATE POLICY orders_owner_update
ON rls_lab.orders
FOR UPDATE
TO rls_demo_owner
USING (tenant_id = 10)
WITH CHECK (tenant_id = 10);
~~~

This is a **policy-granted permission**, not a bypass.

Do not blindly add `USING(true)` for the owner just to get legacy code working again without reviewing all requirements and risks.

## 32. Does a TO PUBLIC Policy Apply to a FORCED Owner?

Yes, when the policy matches. In the lab we created:

~~~sql
CREATE POLICY orders_tenant_read
ON rls_lab.orders
FOR SELECT TO PUBLIC
USING (...);
~~~

When the owner is FORCED, it is evaluated against applicable `TO PUBLIC` policies. If the policy includes a branch for the owner, rows satisfying the predicate are allowed.

If a `USING(true)` policy applies to the owner, a FORCED owner still sees all rows **because the policy allows it**, not because of automatic bypass.

This distinction is critical when investigating "FORCE is set, yet all rows are still visible".

## 33. PERMISSIVE and RESTRICTIVE

PostgreSQL combines applicable policies using the following rules:

- **PERMISSIVE policies** combine using **OR** logic.
- **RESTRICTIVE policies** add **AND** conditions.

Illustrative example:

~~~sql
CREATE POLICY tenant_visible
ON secure.orders
AS PERMISSIVE FOR SELECT
USING (tenant_id = 10);

CREATE POLICY not_cancelled
ON secure.orders
AS RESTRICTIVE FOR SELECT
USING (status <> 'cancelled');
~~~

A role subject to RLS only sees rows permitted by at least one permissive policy **and** passing all restrictive policies.

An appropriate permissive policy must exist; creating only a restrictive policy does not grant row visibility from scratch.

### 33.1. An Overly Broad Permissive USING(true) Policy

If a broad policy is added for the same role, OR combination can render a narrow tenant condition ineffective unless restrictive policies still constrain it.

FORCE does not change policy combination rules.

## 34. SECURITY DEFINER Functions and RLS Exceptions

A function:

~~~sql
CREATE FUNCTION secure.some_command(...)
RETURNS ...
LANGUAGE plpgsql
SECURITY DEFINER
AS $$ ... $$;
~~~

can execute with the privileges of the **function owner** under PostgreSQL's security model.

When the function accesses an RLS-protected table:

- A normal function owner that owns a **non-FORCED** table can bypass RLS via ownership.
- If the same normal owner owns a **FORCED** table, policies can be enforced.
- If the function owner is a superuser or BYPASSRLS role, FORCE **does not** disable that exception.
- If the function owner lacks necessary privileges, the function does not automatically acquire all privileges merely because it is SECURITY DEFINER.

### 34.1. SECURITY DEFINER Is Not Another Name for BYPASSRLS

What matters is the **actual privileges of the routine owner**, the underlying tables, and the policy context. Do not label every SECURITY DEFINER function as an automatic bypass.

## 35. Data Leakage Through Functions Owned by Over-Privileged Roles

In the lab, suppose a superuser creates:

~~~sql
CREATE FUNCTION rls_lab.count_all_orders_admin()
RETURNS BIGINT
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
    SELECT COUNT(*) FROM rls_lab.orders;
$$;
~~~

If the function owner is a superuser, the SELECT inside can bypass RLS on the underlying table.

If granted:

~~~sql
GRANT EXECUTE
ON FUNCTION rls_lab.count_all_orders_admin()
TO rls_demo_alice;
~~~

Alice can learn the system-wide order count through the function, even though direct table SELECT only shows tenant 10.

**Never expose such a function to a runtime tenant role in production**. This example illustrates why testing direct SELECTs alone is insufficient.

### 35.1. Safe Design Practices

- Do not use superuser as the function owner except for genuine administrative needs.
- Restrict EXECUTE privileges.
- Use a least-privilege owner.
- Enforce policy/tenant checks inside routines where needed.
- Audit routines capable of returning cross-tenant data.
- Review all dynamic SQL and nested function calls.

## 36. search_path in SECURITY DEFINER

A SECURITY DEFINER function can inadvertently invoke an object created by an untrusted user if it uses unqualified names with an unsafe `search_path`.

Structural pattern:

~~~sql
-- Illustrative pattern; replace ellipses with actual code:
CREATE FUNCTION secure.example(...)
RETURNS ...
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = secure, pg_temp
AS $$
BEGIN
    -- Reference secure.orders using its schema-qualified name.
    ...
END;
$$;
~~~

The `...` are placeholders, **not runnable as-is**.

Principles:

1. Include only trusted schemas.
2. Place `pg_temp` appropriately.
3. Schema-qualify table and function references.
4. Do not allow untrusted roles CREATE privileges in trusted schemas.
5. Use parameter binding; never concatenate raw SQL.
6. Restrict EXECUTE privileges and track changes via migrations.

FORCE does not fix a SECURITY DEFINER function with a `search_path` vulnerability.

## 37. Default Views Can Change Security Context

A **standard view** checks privileges and policies on underlying tables relative to the **view owner** under default behavior.

If a view is owned by a highly privileged role, callers querying the view may receive different data than when querying the base table directly.

~~~text
Alice SELECT base_table
          |
          v
RLS per Alice's privileges/policies
          |
          v
2 rows

Alice SELECT default_view
          |
          v
Underlying security context tied to view owner
          |
          v
May differ from 2 rows
~~~

Checkpoints: view owner, table owner, FORCE, BYPASSRLS, grants, active policies, and functions invoked inside the view.

## 38. Security-Invoker Views Since PostgreSQL 15

In PostgreSQL 15+, you can declare:

~~~sql
CREATE VIEW rls_lab.v_orders_invoker
WITH (security_invoker = true) AS
SELECT
    order_id,
    tenant_id,
    amount,
    status
FROM rls_lab.orders;
~~~

With `security_invoker`, permissions and row policies on underlying tables are checked against the **caller** accordingly.

~~~sql
GRANT SELECT ON rls_lab.v_orders_invoker
TO rls_demo_alice, rls_demo_bob;
~~~

In the lab, Alice and Bob already have read access to the base table, so they can test the view under their respective roles.

### 38.1. Difference in GRANTs

With a security-invoker view, the caller may need privileges on the **underlying tables**. Having GRANT SELECT solely on the view is not necessarily sufficient.

### 38.2. Does Not Stop a BYPASSRLS Caller

If the caller is a superuser or BYPASSRLS role, a security-invoker view runs under that privileged context. Do not treat `security_invoker` as a mechanism to strip exemptions from a privileged role.

### 38.3. security_barrier Is Not security_invoker

`security_barrier` pertains to planner optimization and predicate evaluation order for security. It does not mean caller-based permissions and does not FORCE the owner.

## 39. Superuser-Owned Views: A Risky Case

A view owned by a superuser:

~~~sql
-- Illustrative only, in an isolated lab database:
CREATE VIEW rls_lab.v_orders_admin_owned AS
SELECT
    order_id,
    tenant_id,
    amount,
    status
FROM rls_lab.orders;
~~~

If SELECT on this view is granted to Alice, data risks being accessed using the view owner's broader privileges rather than the caller's, even when the base table is FORCED.

Never expose multi-tenant data via a default superuser-owned view without rigorous verification. Designs requiring caller policies can use `security_invoker` views with appropriate grants.

## 40. There Is More Than One Execution Context Layer

A real query may pass through:

~~~text
Application (login role)
       |
       v
SET ROLE or connection context
       |
       v
View (default owner-based or security-invoker)
       |
       +--> Base table RLS
       |
       +--> SECURITY DEFINER function
       |
       +--> Other SQL / other tables
~~~

Each segment may be evaluated under different privilege rules. FORCE only affects the **table owner exemption on the FORCED table**, not every execution context in the system.

## 41. TRUNCATE Is Not Restricted by DELETE Policies

PostgreSQL does not apply row security policies to `TRUNCATE`.

~~~sql
-- DO NOT run on data you need to keep:
TRUNCATE TABLE rls_lab.orders;
~~~

A role holding the TRUNCATE privilege can execute the operation without row-by-row filtering by DELETE `USING` policies.

**Lesson:** never grant TRUNCATE to a runtime tenant role. Protect DDL privileges, TRUNCATE privileges, and administrative routines via privilege governance and change control.

FORCE does not turn TRUNCATE into a row-by-row DELETE.

## 42. REFERENCES and Integrity Checks

RLS also does not apply to `REFERENCES` privileges/operations the way it applies row-by-row to SELECT/INSERT/UPDATE/DELETE.

PostgreSQL must still enforce integrity constraints such as:

- `PRIMARY KEY`.
- `UNIQUE`.
- `FOREIGN KEY`.

Internal constraint checks can **bypass row security** to guarantee the table remains consistent with constraints.

### 42.1. Why Must Hidden Rows Still Be Seen?

If a row exists but is hidden by a policy, PostgreSQL still needs to detect it when checking for duplicate keys or foreign key validity; otherwise, data integrity would break.

### 42.2. Side Channels via Constraint Errors

An INSERT can raise a duplicate key error even if the role cannot SELECT the conflicting row. This can reveal **the existence** of a hidden value.

Mitigate this risk by:

- Designing keys and uniqueness scopes aligned with tenants.
- Never exposing raw sensitive constraint errors in API responses.
- Using unpredictable IDs where appropriate.
- Enforcing rate limits and abuse controls.
- Auditing probing behaviors.
- Evaluating the full threat model, not just SELECT outputs.

FORCE does not block necessary internal integrity checks.

## 43. RLS Does Not Hide All Metadata

RLS on a table does not automatically filter table names, column names, role metadata, or policy definitions under the same row policy.

System catalogs and `information_schema` follow their own privilege and visibility rules. Do not assume that "cannot SELECT rows" means a user cannot see any metadata about the object.

If schema metadata itself is sensitive, review privileges and exposure surfaces separately.

## 44. The Owner Still Manages Structure and Policies

Even with FORCE:

- The table owner remains the owner.
- The owner retains appropriate DDL privileges.
- Depending on privileges, the owner can modify policies or FORCE/ENABLE state.
- FORCE does not revoke ownership or automatically reassign privileges.

Consequently, FORCE does not defend against compromise of an application role that **is both the owner and able to alter RLS**.

A cleaner architecture is typically:

~~~text
Migration owner (NOLOGIN if appropriate)
    - Owns tables, manages schema/policies

Application role
    - Does not own tables
    - Holds minimal DML privileges
    - Subject to RLS

Backup/maintenance role
    - Used in separate administrative workflows
    - Holds necessary full privileges and is audited

Security admin
    - Manages privileged roles and controls migrations
~~~

## 45. Multi-Tenancy with a Single Shared DB Role

In a Java backend, a connection pool often uses a single login such as `app_service` for all end users. In that setup, `current_user` is always the same role.

A policy like:

~~~sql
USING (current_user = 'tenant_10_role')
~~~

cannot distinguish tenants when every HTTP request shares one database role.

Another policy pattern relies on session/transaction context:

~~~sql
-- Illustrative pattern; NOT safe by itself:
USING (
    tenant_id = NULLIF(
        current_setting('app.tenant_id', true),
        ''
    )::INTEGER
)
~~~

### 45.1. GUCs Are Not Tamper-Proof Identity Sources by Themselves

If the session role can execute `SET app.tenant_id` freely and there is a SQL injection flaw or untrusted SQL execution path, an attacker may attempt to tamper with the context.

You must ensure the application authenticates the real tenant, sets context in a controlled manner, prevents arbitrary client SQL execution, and tests policies against the relevant threat model.

### 45.2. Connection Pooling and Context Leakage

If tenant context is set on a long-lived connection and a subsequent request reuses that connection without resetting state, cross-tenant data leakage can occur.

Prefer **transaction-scoped** context (`SET LOCAL`), verify pool configuration, ensure proper commit/rollback cleanup, and test connection reuse. FORCE does not prevent context leakage.

## 46. INSERT ... ON CONFLICT DO UPDATE

UPSERT combines inserting a new row and updating an existing row:

~~~sql
INSERT INTO rls_lab.orders (
    order_id, tenant_id, amount, status
)
VALUES (1, 10, 120.00, 'paid')
ON CONFLICT (order_id)
DO UPDATE SET amount = EXCLUDED.amount;
~~~

When the role is subject to RLS, evaluate INSERT policies, UPDATE policies, `WITH CHECK`, and any SELECT privileges/policies involved in read expressions.

Do not assume UPSERT is permitted just because the role has an INSERT policy. Conflicting with a row the role is not permitted to see can fail with an error or behave differently from "no matching row".

### 46.1. Preventing Cross-Tenant Probing via UPSERT

If a unique key spans the whole table globally, conflicts or constraint errors can reveal whether a key already exists. Handle API error responses carefully and design tenant-aware identifiers.

## 47. MERGE and Version-Dependent Behaviors

Different PostgreSQL versions may introduce behavioral details around MERGE, RLS, and execution paths. Do not copy assumptions from Oracle or SQL Server.

For a given server version, verify:

- Is MERGE supported with RLS in that scenario?
- Which policies apply to the INSERT/UPDATE/DELETE branches?
- How are hidden rows handled?
- Are SELECT privileges involved?
- Are there special trigger or constraint interactions?

This article focuses on FORCE and bypasses; the overarching rule is **never assume FORCE gives complex DML the exact same semantics as a simple SELECT**.

## 48. Partitioned Tables and Direct Partition Access

For partitioned tables, accessing via the parent table and accessing individual child partitions directly can pass through the privileges and policies of the respective relation.

Verify:

1. Querying the parent table.
2. Querying a child partition directly.
3. Owners of the parent and child tables.
4. Policies and FORCE flags on all related objects.
5. Direct SELECT/INSERT/UPDATE privileges on child partitions.
6. Row movement across partitions.
7. Views or functions accessing partitions.

Setting FORCE on the parent **is not enough to assume every direct path to partitions produces the same outcome**. Design and test against your actual PostgreSQL version.

## 49. SELECT FOR UPDATE and Read/Lock Privileges

Example:

~~~sql
SELECT *
FROM rls_lab.orders
WHERE tenant_id = 10
FOR UPDATE;
~~~

This query has specific privilege and row-locking semantics. Do not assume FOR UPDATE bypasses RLS to lock rows the caller is not allowed to access.

Nor does RLS fully isolate system resources: tenants A and B can still contend on the same table, indexes, and locks. RLS is primarily a **row access policy**, not resource isolation.

## 50. EXPLAIN Can Be Misleading When Testing RLS

~~~sql
EXPLAIN
SELECT *
FROM rls_lab.orders;
~~~

The planner may fold policy expressions into the query plan according to optimization and security rules.

However:

- A superuser's plan can differ from Alice's plan.
- Not every policy appears as an obvious standalone filter node.
- A query returning 0 rows might be due to RLS, a WHERE clause, or genuinely empty data.
- `EXPLAIN ANALYZE` executes the query; for DML, it produces real side effects.

Always test **actual query results and permissions under the exact role**, alongside inspecting metadata. Do not treat a plan viewed as an admin as final proof.

## 51. Auditing RLS Configuration Across Multiple Tables

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    pg_get_userbyid(c.relowner) AS owner_name,
    c.relrowsecurity AS enabled,
    c.relforcerowsecurity AS forced
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'rls_lab'
  AND c.relkind IN ('r', 'p')
ORDER BY n.nspname, c.relname;
~~~

`relkind='r'` denotes regular tables; `'p'` denotes partitioned tables.

A complete security posture report should combine:

- Tables with RLS disabled.
- Tables with FORCE set.
- Table owners.
- Roles with BYPASSRLS or superuser.
- Policy roles, commands, and predicates.
- Grants and runtime connection identities.
- Views and SECURITY DEFINER functions.
- Partitions and direct access paths.
- Backup/export roles.

## 52. Staging Functional Test Matrix

| Scenario | Outcome to Verify |
|---|---|
| Alice direct SELECT | Tenant 10 only |
| Bob direct SELECT | Tenant 20 only |
| Owner ENABLE + NO FORCE | Bypass via ownership |
| Owner ENABLE + FORCE | Subject to owner policy |
| Role without SELECT | Permission denied |
| Alice INSERT tenant 10 | Allowed when INSERT policy/GRANT valid |
| Alice INSERT tenant 20 | Rejected |
| Alice UPDATE tenant 20 row | Cannot target row |
| Alice changes tenant_id 10 → 20 | Rejected by WITH CHECK |
| Alice DELETE tenant 20 | Cannot delete |
| Privileged-owner default view | Does not accidentally return cross-tenant rows |
| Security-invoker view | Evaluates privileges per caller as designed |
| SECURITY DEFINER function | No unintended data leakage path |
| row_security=off | Does not turn into a bypass |
| Superuser/BYPASSRLS | FORCE exemptions clearly understood |
| Backup role | Full dump or partial export matches intent |
| TRUNCATE | Not granted to tenant app role |
| Direct partition access | Does not bypass designed boundaries |

Test both **positive cases** (permitted) and **negative cases** (denied). Do not stop after confirming Alice sees two rows while overlooking a privileged view Alice can call to see everything.

## 53. Checklist Before Enabling FORCE in Production

1. Identify the table and its actual table owner.
2. Check `relrowsecurity` and `relforcerowsecurity`.
3. List all SELECT/INSERT/UPDATE/DELETE/ALL policies.
4. Determine how permissive and restrictive policies combine.
5. Check which roles are superuser or BYPASSRLS.
6. Review table/schema privileges of runtime roles.
7. List queries currently running under the owner role.
8. Audit views and SECURITY DEFINER functions.
9. Check whether backup, ETL, or maintenance jobs run as the owner.
10. Test owner policies before and after FORCE.
11. Verify partition and direct child-table access paths.
12. Check TRUNCATE/REFERENCES and constraint error side channels.
13. Plan DDL locks, timeouts, migration execution, and rollback.
14. Run staging tests using real application roles.
15. Have monitoring in place to detect permission/RLS errors after deployment.

**Never toggle FORCE by guesswork**: it can break application reads or writes even though no table data changed.

## 54. Transactional FORCE Migration

~~~sql
BEGIN;

SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '30s';

ALTER TABLE rls_lab.orders
ENABLE ROW LEVEL SECURITY;

ALTER TABLE rls_lab.orders
FORCE ROW LEVEL SECURITY;

COMMIT;
~~~

This example is **for lab use only**. PostgreSQL supports transactional DDL for appropriate operations, though DDL still requires locks.

### 54.1. Do Not Leave DDL Transactions Idle

An open transaction holding locks after DDL can block other queries. Prepare changes beforehand, review them, and complete the transaction promptly under approved procedures.

### 54.2. After COMMIT, a Compensating Migration Is Required

You cannot ROLLBACK a transaction that has already COMMITted. If adjustments are needed, apply a new migration after assessing data-exposure risk; never assume `NO FORCE` is a safe security rollback.

## 55. Troubleshooting: Owner Reads Everything Despite FORCE

Possible causes:

- RLS is DISABLED.
- The executing role is superuser or BYPASSRLS.
- There is a permissive `USING(true)` policy or another policy allowing all rows.
- The query goes through a view or routine with a privileged security context.
- You checked the wrong schema or table.
- The runtime session is not actually running as the owner role you assumed.

Diagnostic steps:

~~~sql
SELECT current_user, session_user;

SELECT
    relrowsecurity,
    relforcerowsecurity
FROM pg_class
WHERE oid = 'rls_lab.orders'::regclass;

SELECT policyname, cmd, qual, with_check
FROM pg_policies
WHERE schemaname='rls_lab'
  AND tablename='orders';
~~~

**FORCE means the owner is no longer exempt from policies**, not that fewer rows are guaranteed if a policy allows everything.

## 56. Troubleshooting: Owner Sees 0 Rows After FORCE

Possible causes:

- No SELECT policy exists for the owner.
- Existing policies target other roles (`TO ...`).
- Tenant context is missing.
- A restrictive policy filters out all rows.
- The predicate expression is flawed.
- The active execution role differs from what was expected.

Never "fix" this in production by running DISABLE RLS; determine the exact scope the owner job genuinely requires and provide an appropriate policy or governed administrative path.

## 57. Troubleshooting: Export/Backup Fails After FORCE

Suppose a backup job uses the table owner to dump data. Before FORCE, the owner bypassed RLS; after FORCE, the owner is subject to policies.

To avoid silently exporting an incomplete dataset, the backup tool may raise an error instead of dumping a subset. You should:

1. Determine whether a full backup or single-tenant export is needed.
2. Check the role/privileges and FORCE flags.
3. Use a separately governed backup path.
4. Verify restore behavior and row counts.
5. Never grant BYPASSRLS to an app role or DISABLE RLS as an emergency patch.

## 58. Troubleshooting: UPDATE Affects 0 Rows Even Though the ID Exists

~~~sql
UPDATE rls_lab.orders
SET amount = 250.00
WHERE order_id = 3;
~~~

If executed as Alice with an UPDATE policy for tenant 10, order 3 (belonging to tenant 20) cannot be targeted; affected row count = 0.

This differs from a `WITH CHECK` error, which occurs when an existing row is permitted to be updated, but its **post-UPDATE** values are invalid.

An HTTP API should return a standardized "not found / not permitted" response aligned with its information-disclosure policy rather than leaking raw database errors that let attackers probe other tenants' IDs.

## 59. Common Pitfalls

### 59.1. Enabling RLS Only and Assuming the Owner Is Restricted

The table owner bypasses RLS by default unless FORCE is set.

### 59.2. Thinking FORCE Blocks Superusers or BYPASSRLS Roles

No. Those exemptions go beyond the table-owner exemption.

### 59.3. Testing as postgres and Concluding Policies Do Not Work

Superusers bypass RLS. Always test under the runtime role.

### 59.4. Using DISABLE to Work Around Missing Policies

This can expose all rows to any role holding SELECT.

### 59.5. Assuming NO FORCE and DISABLE Are Identical

NO FORCE only restores the table owner exemption.

### 59.6. Granting SELECT Without Creating a Policy

With RLS enabled, a normal role will typically see 0 rows.

### 59.7. Creating a Policy Without Granting SELECT

The query will fail with permission denied.

### 59.8. Granting BYPASSRLS to the Application Service Account

You lose the safety net against queries missing tenant filters.

### 59.9. Setting row_security=off Expecting to Bypass RLS

This GUC grants no bypass privileges; it raises errors when policies would filter rows.

### 59.10. Thinking FORCE Automatically Grants a Policy to the Owner

If no policy covers the owner, the owner may see 0 rows.

### 59.11. Unintentionally Adding a Permissive USING(true) Policy

Through OR combination, this can negate narrow tenant policies.

### 59.12. Having Only Restrictive Policies

Without an enabling permissive policy, no rows are allowed.

### 59.13. Omitting WITH CHECK on tenant_id Updates

This can allow improperly modifying the new tenant value.

### 59.14. Failing to Test Views Owned by Privileged Roles

Queries through views may run with broader context than direct table SELECTs.

### 59.15. Exposing Superuser SECURITY DEFINER Functions to APIs

This can leak data even when the underlying table has FORCE set.

### 59.16. Failing to Protect search_path

Risks resolving objects created by untrusted roles.

### 59.17. Thinking TRUNCATE Obeys DELETE Policies

TRUNCATE is not filtered row-by-row by RLS.

### 59.18. Thinking UNIQUE/FK Checks Only See Rows Visible to SELECT RLS

Integrity checks can bypass RLS and create existence side channels.

### 59.19. Using a User-Settable Tenant GUC Without Controls

SQL injection or context leakage may allow a client to pick another tenant.

### 59.20. Not Resetting Context When Reusing Pooled Connections

This can leak tenant data across requests.

### 59.21. Checking Only relforcerowsecurity=true

RLS might still be DISABLED (`relrowsecurity=false`).

### 59.22. Failing to Check Partitions and Direct Child Access

Direct child queries may behave differently from parent policies.

### 59.23. Backing Up as a FORCED Owner and Assuming It Is a Full Backup

The owner may be subject to policies and export only a subset.

### 59.24. Relying on FORCE to Block Table Owner DDL

The owner can still alter table configuration using its administrative privileges.

## 60. The Principle of Least Privilege

A practical separation model:

| Role Type | Appropriate Privileges |
|---|---|
| Runtime app | USAGE and minimal required DML only; does not own tables |
| Table/migration owner | Manages schema; not used as a request login |
| Reporting | SELECT restricted to contract |
| Backup | Governed, audited path with full required access |
| Security admin | Manages policies and role privileges; not used for app requests |

Never build an "all-purpose" account that simultaneously owns tables, holds superuser/BYPASSRLS, serves application requests, and runs backup jobs.

### 60.1. FORCE Is Defense-in-Depth, Not the Sole Security Boundary

Even with FORCE, ensure runtime roles cannot DISABLE RLS themselves, cannot query overly privileged views outside contract, and cannot gain row-bypassing access via SECURITY DEFINER routines.

## 61. Workflow for Investigating RLS Bypasses

~~~text
Query returns more rows than expected
                 |
                 v
Identify current_user/session_user
                 |
                 v
Check role rolsuper/rolbypassrls
                 |
                 v
Check table owner and FORCE/ENABLE flags
                 |
                 v
Inspect pg_policies + GRANTs
                 |
                 v
Does query hit base table or view/function?
                 |
                 v
Check view owner/security_invoker/
SECURITY DEFINER/search_path
                 |
                 v
Inspect runtime tenant context and pool
                 |
                 v
Re-test under application role in staging
~~~

Do not merely patch the failing endpoint with `WHERE tenant_id`; determine why the database defense layer failed to behave as expected.

## 62. Practice Exercises

### Exercise 1 — ENABLE vs FORCE

Explain the difference between `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`.

**Hint:** ENABLE turns on policy enforcement; FORCE brings a normal table owner under policy enforcement.

### Exercise 2 — Owner Bypass

When RLS is enabled without FORCE, what does the owner see in the lab?

**Hint:** all four orders.

### Exercise 3 — FORCE

After FORCE, which `order_id` values does the owner see in the lab?

**Hint:** 1 and 2, per the owner policy.

### Exercise 4 — Superuser

Does FORCE compel a superuser to obey policies?

**Hint:** no.

### Exercise 5 — BYPASSRLS

Is BYPASSRLS a table grant or a role attribute?

**Hint:** a role attribute.

### Exercise 6 — BYPASSRLS and SELECT

Can a role with BYPASSRLS select from a table without table privileges?

**Hint:** no; it does not automatically grant all privileges.

### Exercise 7 — NO FORCE

Does NO FORCE disable RLS for Alice?

**Hint:** no; it only restores the owner exemption.

### Exercise 8 — DISABLE

Alice already has GRANT SELECT. How does DISABLE RLS change her results?

**Hint:** rows are no longer filtered by row policies.

### Exercise 9 — Both Flags

What does `relrowsecurity=true` and `relforcerowsecurity=true` mean?

**Hint:** RLS is enabled and FORCED on the owner.

### Exercise 10 — Force Flag While Disabled

If `relforcerowsecurity=true` while `relrowsecurity=false`, does RLS filter rows?

**Hint:** no.

### Exercise 11 — Default Deny

How many rows will a role subject to RLS see if there is no SELECT policy?

**Hint:** normally 0.

### Exercise 12 — GRANT

What happens if a SELECT policy exists but GRANT SELECT is missing?

**Hint:** permission denied.

### Exercise 13 — Inspecting Role Attributes

Write a query to inspect `rolsuper` and `rolbypassrls`.

**Hint:** query `pg_roles`.

### Exercise 14 — Inspecting Policies

Write a query to view `qual` and `with_check` for a table.

**Hint:** query `pg_policies`.

### Exercise 15 — Current User

Why can `session_user` and `current_user` differ?

**Hint:** `SET ROLE` / `SECURITY DEFINER`.

### Exercise 16 — row_security=off

Is this a command to bypass RLS?

**Hint:** no.

### Exercise 17 — pg_dump

Why might a normal owner on a FORCED table fail to dump all data?

**Hint:** the owner is subject to policies.

### Exercise 18 — Partial Export

Is `pg_dump --enable-row-security` guaranteed to create a full backup?

**Hint:** no.

### Exercise 19 — INSERT WITH CHECK

What does WITH CHECK inspect during an INSERT?

**Hint:** the new row.

### Exercise 20 — UPDATE

Why should an UPDATE policy have both USING and WITH CHECK?

**Hint:** to check both the old target row and the new values.

### Exercise 21 — DELETE

Does a DELETE policy prevent a role from running TRUNCATE if it has GRANT TRUNCATE?

**Hint:** no.

### Exercise 22 — PUBLIC

Does `TO PUBLIC` automatically grant access to see all rows?

**Hint:** no; the predicate and table privileges still apply.

### Exercise 23 — Permissive

Do two permissive policies combine with OR or AND?

**Hint:** OR.

### Exercise 24 — Restrictive

Can a restrictive policy grant row visibility on its own without a permissive policy?

**Hint:** no.

### Exercise 25 — Security Definer

Can a function owned by a superuser bypass FORCE when reading a table?

**Hint:** yes.

### Exercise 26 — Normal Function Owner

Can FORCE change the outcome of a SECURITY DEFINER function owned by a normal table owner?

**Hint:** yes, because the owner is now subject to policies.

### Exercise 27 — View

Why can a SELECT from a default view differ from a direct SELECT on the base table?

**Hint:** underlying table privileges/policies are checked in a context tied to the view owner.

### Exercise 28 — security_invoker

Whose privileges and policies does it use on underlying tables?

**Hint:** the caller's.

### Exercise 29 — security_barrier

Is it synonymous with `security_invoker`?

**Hint:** no.

### Exercise 30 — TRUNCATE

Why should TRUNCATE never be granted to a tenant app role?

**Hint:** it is not filtered row-by-row by DELETE policies.

### Exercise 31 — Constraints

Do UNIQUE/FK checks only inspect rows visible through SELECT RLS?

**Hint:** no; data integrity must still be preserved.

### Exercise 32 — Constraint Error Side Channel

What can a duplicate key error reveal?

**Hint:** the existence of a hidden key.

### Exercise 33 — Single Shared DB Role

Why can't `current_user` distinguish end users when the app pool shares a single login?

**Hint:** the execution role is identical.

### Exercise 34 — Tenant GUC

Is a tenant context variable safe if an untrusted caller can SET it directly?

**Hint:** no.

### Exercise 35 — Connection Pool

Why must tenant context be reset at transaction boundaries?

**Hint:** to prevent cross-request leakage.

### Exercise 36 — Partitions

Does FORCE on the parent prove every direct child partition access path is safe?

**Hint:** no; test every path.

### Exercise 37 — UPSERT

Why might UPSERT require both INSERT and UPDATE policies?

**Hint:** because of the `ON CONFLICT` branch.

### Exercise 38 — Owner DDL

Does FORCE prevent the owner from altering table configuration?

**Hint:** no.

### Exercise 39 — Test Matrix

List at least three negative tests beyond SELECT.

**Hint:** INSERT for another tenant, UPDATE `tenant_id`, DELETE another tenant's row.

### Exercise 40 — Migration

Write a checklist of at least eight items before setting FORCE on a production table.

**Hint:** roles, bypass, policies, owner, privileges, views, jobs, backup, staging, and rollback.

## 63. Frequently Asked Questions

### Does FORCE ROW LEVEL SECURITY force every role to obey policies?

**No.** It forces a normal table owner to obey policies. Superusers and `BYPASSRLS` roles remain exempt.

### Does FORCE automatically enable RLS?

No. You still need `ENABLE ROW LEVEL SECURITY`.

### Does FORCE automatically create a policy for the owner?

No. Without an appropriate policy, the owner may see 0 rows or have DML rejected.

### Should a normal owner be used as the application role?

Generally no. Separate migration owners from runtime roles. FORCE provides defense-in-depth, though it does not strip DDL authority from the owner.

### Is NO FORCE the same as DISABLE?

No. NO FORCE restores the owner exemption; DISABLE turns off row policy enforcement on the table.

### Does row_security=off let me view all tenants?

No. It is not a bypass; it raises an error when a query would be filtered by RLS.

### Does a BYPASSRLS role automatically have GRANT SELECT?

No. It is a role attribute that bypasses the RLS layer, not a blanket grant of all table privileges.

### Does SECURITY DEFINER automatically bypass RLS?

It depends on the **function owner** and privileges on the underlying table. If the owner is a superuser or BYPASSRLS role, it can bypass RLS even when FORCE is set.

### Can a default view return rows the caller cannot see in a direct SELECT?

Yes, depending on the view owner and security context. Check `security_invoker`, grants, and policies.

### Since which PostgreSQL version has security_invoker been supported?

The `security_invoker` view option has been supported since PostgreSQL 15.

### Is TRUNCATE restricted by DELETE policies?

No. Protect it using TRUNCATE/DDL privileges and operational controls.

### Do FK/UNIQUE checks miss data because of RLS?

No. The database must enforce integrity, which is why side channels can exist via constraint errors.

### Are ENABLE + FORCE alone enough for multi-tenant security?

Not yet. You must also verify runtime roles, owner privileges, policy predicates, views, functions, tenant context, backups, partitions, connection pooling, and other bypass paths.

## 64. Summary

Commands to remember:

~~~sql
-- Enable policy enforcement.
ALTER TABLE rls_lab.orders
ENABLE ROW LEVEL SECURITY;

-- Force the normal table owner to obey policies.
ALTER TABLE rls_lab.orders
FORCE ROW LEVEL SECURITY;

-- Restore the owner exemption.
ALTER TABLE rls_lab.orders
NO FORCE ROW LEVEL SECURITY;

-- Disable RLS across the table (risky if roles hold broad GRANTs).
ALTER TABLE rls_lab.orders
DISABLE ROW LEVEL SECURITY;

-- Inspect active execution role.
SELECT session_user, current_user;

-- Inspect table RLS flags.
SELECT
    relrowsecurity,
    relforcerowsecurity
FROM pg_class
WHERE oid = 'rls_lab.orders'::regclass;

-- Inspect policies.
SELECT *
FROM pg_policies
WHERE schemaname = 'rls_lab'
  AND tablename = 'orders';

-- Inspect privileged roles.
SELECT rolname, rolsuper, rolbypassrls
FROM pg_roles;
~~~

**Key principles:**

1. Having RLS enabled **does not mean every role is filtered**.
2. A normal table owner **bypasses RLS by default**.
3. FORCE compels a normal owner to **obey policies** when RLS is enabled.
4. Superusers and `BYPASSRLS` roles **still bypass**, regardless of FORCE.
5. FORCE does not create policies or open read/write privileges automatically.
6. NO FORCE differs from DISABLE: one changes only the owner exemption, the other turns off row filtering.
7. `row_security=off` is **not** a bypass switch; it helps catch exports or queries unexpectedly filtered by policies.
8. GRANT and RLS are two independent yet complementary authorization layers.
9. USING controls existing rows; WITH CHECK controls rows resulting from INSERT/UPDATE.
10. View owners and SECURITY DEFINER can cause queries to run under a privileged context different from the caller.
11. `security_invoker` views on PostgreSQL 15+ evaluate underlying rights and policies against the caller.
12. TRUNCATE is not governed by row policies like DELETE; integrity checks can bypass RLS.
13. The table owner retains DDL capabilities; separate ownership from the runtime application role.
14. Backups, partitions, UPSERT, and connection pooling are access paths that must be reviewed individually.
15. Always verify both permitted and denied behaviors **under the exact execution role**.

Decision flowchart:

~~~text
Role executes query
         |
         v
Has required SQL privileges?
    /                \
   No                Yes
    |                  |
Permission denied      v
               Is RLS ENABLED?
                 /       \
                No       Yes
                 |         |
           RLS not applied v
                       Superuser/BYPASSRLS?
                         /        \
                       Yes         No
                         |          |
                      Bypass        v
                              Table owner?
                                /       \
                               No       Yes
                                |        |
                            Apply RLS  FORCE?
                                        /   \
                                      Yes    No
                                       |      |
                                   Apply RLS Bypass
                                       |
                                       v
                               Matching policies
                                       |
                                       v
                              Allow/filter/deny
~~~

**Conclusion:** `FORCE ROW LEVEL SECURITY` closes one specific, critical exception: **the normal table owner being exempt from RLS by default**. It does not strip privileges from superusers/BYPASSRLS roles and does not replace overall security architecture. For reliable row-level data protection, combine accurate policies, least-privilege GRANTs, separation of owner and runtime roles, testing of views and SECURITY DEFINER routines, proper tenant context management, and verification across backups, TRUNCATE, and integrity checks.
