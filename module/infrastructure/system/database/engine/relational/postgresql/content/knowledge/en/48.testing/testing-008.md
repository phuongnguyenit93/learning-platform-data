# Testing Role Privileges, RLS, and Access Denial Behavior

In PostgreSQL, data access is governed across multiple layers. A role may connect to the database yet lack schema `USAGE`; it may hold table `SELECT` yet see only a subset of rows; or it may be allowed to update a row yet forbidden from moving that row to another tenant. Security testing must therefore verify role privileges, object privileges, and Row-Level Security (RLS) policies, while confirming exactly how PostgreSQL responds when access is denied.

This lesson explains how to set up test roles, verify effective privileges, create RLS policies, assert outcomes for each SQL command, and distinguish errors from queries that succeed while returning zero rows.

## 1. Layers to Test

An access attempt typically passes through these layers:

1. **Connection authentication:** whether the user can log in with the current credentials and connection method.
2. **Roles and memberships:** which role the session runs under, which roles it inherits privileges from, and which roles it can switch into.
3. **Object privileges:** whether the role has schema usage, table reads, column writes, function execution, or sequence privileges as required.
4. **RLS:** when RLS is enabled on a table, which rows are allowed for reading, updating, deleting, or inserting under policies applying to the current role.
5. **Special execution paths:** whether views, `SECURITY DEFINER` functions, partitions, or connection pool sessions alter the privilege context.

These layers can produce similar surface symptoms with different root causes. For instance, a `SELECT` returning 0 rows may mean the table genuinely has no matching data or that RLS filtered every row. Conversely, a "permission denied" error usually indicates the role lacks an object-level privilege before the query can even read rows.

When writing a test, specify four elements: executing role, SQL statement, input data, and expected outcome. Never merely check that a command "failed"; determine whether it was blocked by `GRANT`/`REVOKE` or by an RLS policy.

## 2. Understanding Roles and Execution Context

In PostgreSQL, a role is the unit of identity and privilege management. A role can have the `LOGIN` attribute for authentication or `NOLOGIN` to act as a privilege group. A login account is often granted membership in one or more group roles.

Two important information functions are:

- **session_user:** the initial identity of the connection session.
- **current_user:** the role currently checked for privileges when a statement runs.

`SET ROLE` changes `current_user` to the target role if the current session is permitted to assume it. `session_user` remains unchanged. `SET LOCAL ROLE` applies only within the current transaction, which is very handy in tests because `ROLLBACK` or transaction completion restores the prior context.

Example:

~~~sql
BEGIN;
SET LOCAL ROLE app_reader;

SELECT
    session_user,
    current_user;

ROLLBACK;
~~~

If the session initially connected as `app_login` and that account is permitted to switch to `app_reader`, the result is normally `session_user = app_login` and `current_user = app_reader`. Check both values to catch tests running under the wrong role.

Membership does not automatically mean every privilege is inherited identically. The `INHERIT` attribute and membership options determine whether privileges take effect automatically or require `SET ROLE`. Membership behavior gained finer-grained options in newer PostgreSQL releases, so tests must run on the system's real version. The reliable approach is to verify effective privileges via privilege-checking functions and execute statements under the target role.

Do not grant `SUPERUSER`, `BYPASSRLS`, `CREATEROLE`, or `CREATEDB` to ordinary application roles. In particular, `BYPASSRLS` skips RLS policies and can render all row-level access tests meaningless.

## 3. Checking Schema and Object Privileges

`GRANT` and `REVOKE` control privileges at multiple levels. Having `SELECT` on a table is insufficient if the role lacks `USAGE` on the schema containing that table. Similarly, `INSERT` may require sequence privileges if a column uses a standard sequence like `SERIAL`. Always verify all objects touched by the actual statement.

Common privileges:

| Scope | Privileges to consider | Meaning |
|---|---|---|
| Database | CONNECT, CREATE, TEMPORARY | Connect, create schemas, or create temporary tables |
| Schema | USAGE, CREATE | Look up objects in the schema or create objects |
| Table | SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER | Read, write, delete, truncate tables, and related operations |
| Column | SELECT, INSERT, UPDATE | Restrict access to specific columns |
| Sequence | USAGE, SELECT, UPDATE | Fetch values from or adjust a sequence |
| Function | EXECUTE | Invoke a function or procedure |

Example granting least privileges to a reader role and an editor role:

~~~sql
GRANT USAGE ON SCHEMA public TO app_reader, app_editor;

GRANT SELECT
ON TABLE public.documents
TO app_reader;

GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE public.documents
TO app_editor;
~~~

Unneeded privileges can be revoked with `REVOKE`:

~~~sql
REVOKE DELETE
ON TABLE public.documents
FROM app_editor;
~~~

Never use `GRANT ALL` just to make a test pass. Overly broad grants can mask design flaws and give application roles capabilities beyond requirements.

The following functions check effective privileges, accounting for direct grants and effective privileges via applicable role memberships:

~~~sql
SELECT
    has_schema_privilege(
        'app_reader',
        'public',
        'USAGE'
    ) AS can_use_schema,
    has_table_privilege(
        'app_reader',
        'public.documents',
        'SELECT'
    ) AS can_select,
    has_table_privilege(
        'app_reader',
        'public.documents',
        'INSERT'
    ) AS can_insert,
    has_column_privilege(
        'app_reader',
        'public.documents',
        'title',
        'UPDATE'
    ) AS can_update_title;
~~~

Check login role membership:

~~~sql
SELECT
    pg_has_role(
        'app_login',
        'app_reader',
        'MEMBER'
    ) AS is_reader_member;
~~~

Privilege helper results are useful evidence, yet you should still run the actual statements under the target role. A single query may depend simultaneously on schema, table, column, and function privileges as well as RLS policies.

## 4. Row-Level Security Mechanics

RLS restricts which rows a role may act upon. RLS works alongside standard SQL privileges: the role must first hold the necessary object privileges; RLS policies then determine which rows are accessible.

Enable RLS on a table:

~~~sql
ALTER TABLE public.documents
ENABLE ROW LEVEL SECURITY;
~~~

Disable RLS:

~~~sql
ALTER TABLE public.documents
DISABLE ROW LEVEL SECURITY;
~~~

When RLS is enabled, if no policy matches the role and command type being executed, PostgreSQL enforces default deny. For `SELECT`, this usually manifests as seeing zero rows. For `INSERT` or `UPDATE`, a new row failing the policy condition is rejected.

### 4.1. USING and WITH CHECK

The two main expressions in a policy serve distinct roles:

- **USING** determines which existing rows a statement can see or affect. It applies to `SELECT`, `UPDATE`, and `DELETE`.
- **WITH CHECK** validates the row's state after `INSERT` or `UPDATE`. The resulting row must satisfy this expression.

Example policy allowing reads only for documents belonging to the current tenant:

~~~sql
CREATE POLICY documents_read_tenant
ON public.documents
FOR SELECT
TO app_reader, app_editor
USING (
    tenant_id =
    current_setting('app.tenant_id', true)::uuid
);
~~~

Policy allowing the editor role to update documents of the current tenant:

~~~sql
CREATE POLICY documents_update_tenant
ON public.documents
FOR UPDATE
TO app_editor
USING (
    tenant_id =
    current_setting('app.tenant_id', true)::uuid
)
WITH CHECK (
    tenant_id =
    current_setting('app.tenant_id', true)::uuid
);
~~~

`USING` prevents the role from selecting or updating rows belonging to another tenant. `WITH CHECK` prevents the role from changing a valid row into one belonging to another tenant. Testing only `USING` can miss a bug allowing row ownership transfer.

For `INSERT`, policies normally use `WITH CHECK`. For `DELETE`, policies use `USING`. For `UPDATE`, both the old row and the new row must be checked. When a `FOR ALL` or `FOR UPDATE` policy omits `WITH CHECK`, PostgreSQL uses the `USING` expression to validate the new row per policy rules; declaring both expressions explicitly when controlling tenant transfers makes intent clear to readers and maintainers.

### 4.2. Multiple Policies Applying Together

Policies can be permissive or restrictive:

- Permissive policies combine with `OR`. One permissive policy allowing a row through can suffice to grant access.
- Restrictive policies combine with `AND`. Every applicable restrictive policy must be satisfied.
- Overall access requires at least one permissive policy to pass while also passing all applicable restrictive policies.

Therefore, adding a new policy can widen or narrow access depending on policy type and target role. Tests must evaluate all applicable policies together, not only the newly created policy.

If `TO` is omitted, a policy applies to `PUBLIC`. A policy's effective role scope is also influenced by role memberships and the current role. Always test with the role actually executing commands rather than merely reading the role name listed in the policy.

### 4.3. Table Owners and Roles Bypassing RLS

By default, a table owner is normally exempt from RLS on tables they own. `SUPERUSER` and roles with `BYPASSRLS` can always bypass RLS.

You can force the table owner to be subject to policies too:

~~~sql
ALTER TABLE public.documents
FORCE ROW LEVEL SECURITY;
~~~

`FORCE ROW LEVEL SECURITY` does not block `SUPERUSER` or `BYPASSRLS` roles. During testing, never use an administrative account to stand in for an application role. Use a role configured with production-accurate privileges.

Setting `row_security = off` does not disable protection so a user can read all rows either. If a query would be filtered by RLS, PostgreSQL raises an error instead of silently returning filtered results. This setting is useful in workflows needing to detect when rows are being filtered, not as a way to bypass policies.

## 5. Building an RLS Test Scenario

The following example models two tenants. Readers can only view documents; editors can read, insert, update, and delete documents within the current tenant.

Run the role and table setup using an administrative account in a dedicated test database:

~~~sql
CREATE ROLE app_reader NOLOGIN;
CREATE ROLE app_editor NOLOGIN;

CREATE ROLE app_login LOGIN NOINHERIT;
GRANT app_reader, app_editor TO app_login;

CREATE TABLE public.documents (
    id bigint PRIMARY KEY,
    tenant_id uuid NOT NULL,
    title text NOT NULL
);

INSERT INTO public.documents (id, tenant_id, title)
VALUES
    (
        1,
        '11111111-1111-4111-8111-111111111111',
        'Tenant A document'
    ),
    (
        2,
        '22222222-2222-4222-8222-222222222222',
        'Tenant B document'
    );

GRANT USAGE ON SCHEMA public
TO app_reader, app_editor;

GRANT SELECT
ON public.documents
TO app_reader;

GRANT SELECT, INSERT, UPDATE, DELETE
ON public.documents
TO app_editor;

ALTER TABLE public.documents
ENABLE ROW LEVEL SECURITY;

CREATE POLICY documents_read_tenant
ON public.documents
FOR SELECT
TO app_reader, app_editor
USING (
    tenant_id =
    current_setting('app.tenant_id', true)::uuid
);

CREATE POLICY documents_insert_tenant
ON public.documents
FOR INSERT
TO app_editor
WITH CHECK (
    tenant_id =
    current_setting('app.tenant_id', true)::uuid
);

CREATE POLICY documents_update_tenant
ON public.documents
FOR UPDATE
TO app_editor
USING (
    tenant_id =
    current_setting('app.tenant_id', true)::uuid
)
WITH CHECK (
    tenant_id =
    current_setting('app.tenant_id', true)::uuid
);

CREATE POLICY documents_delete_tenant
ON public.documents
FOR DELETE
TO app_editor
USING (
    tenant_id =
    current_setting('app.tenant_id', true)::uuid
);
~~~

In this example, `app_login` is a login role permitted to switch to `app_reader` or `app_editor`. The `NOINHERIT` attribute forces the scenario to make role switching explicit. Log in as `app_login` during integration tests; in simple test environments, an admin account may also use `SET ROLE` to test each role, provided `current_user` is verified after switching.

The policy expressions use a custom configuration parameter `app.tenant_id` to illustrate passing tenant context. In tests, this can be set transaction-locally via `set_config` with `true` as the third argument:

~~~sql
SELECT set_config(
    'app.tenant_id',
    '11111111-1111-4111-8111-111111111111',
    true
);
~~~

Passing `true` scopes the setting to the current transaction only. In a real application, tenant context must be set by a trusted backend after authentication. Never trust a `tenant_id` supplied directly by end users or allow them to execute arbitrary SQL to set this variable themselves; if they can pick their own tenant context, the policy cannot enforce tenant boundaries.

### 5.1. Testing the reader role

~~~sql
BEGIN;

SET LOCAL ROLE app_reader;

SELECT
    session_user,
    current_user;

SELECT set_config(
    'app.tenant_id',
    '11111111-1111-4111-8111-111111111111',
    true
);

SELECT id, tenant_id, title
FROM public.documents
ORDER BY id;

ROLLBACK;
~~~

Expected result: the query returns only tenant A's document. Tenant B's document still exists but does not appear in the reader role's result.

Verify the reader role cannot `INSERT`:

~~~sql
BEGIN;

SET LOCAL ROLE app_reader;

SELECT set_config(
    'app.tenant_id',
    '11111111-1111-4111-8111-111111111111',
    true
);

INSERT INTO public.documents (id, tenant_id, title)
VALUES (
    3,
    '11111111-1111-4111-8111-111111111111',
    'Insert not allowed'
);

ROLLBACK;
~~~

Expected result: missing `INSERT` privilege error on the table. This tests object privileges rather than RLS `WITH CHECK`, because `app_reader` was never granted `INSERT`.

### 5.2. Testing the editor role

The editor role can insert documents in its own tenant:

~~~sql
BEGIN;

SET LOCAL ROLE app_editor;

SELECT set_config(
    'app.tenant_id',
    '11111111-1111-4111-8111-111111111111',
    true
);

INSERT INTO public.documents (id, tenant_id, title)
VALUES (
    3,
    '11111111-1111-4111-8111-111111111111',
    'New Tenant A document'
);

SELECT id, tenant_id, title
FROM public.documents
ORDER BY id;

ROLLBACK;
~~~

Expected result: `INSERT` succeeds in tenant A. `ROLLBACK` cleans up the test data.

Next, try inserting a row belonging to tenant B while context remains tenant A:

~~~sql
BEGIN;

SET LOCAL ROLE app_editor;

SELECT set_config(
    'app.tenant_id',
    '11111111-1111-4111-8111-111111111111',
    true
);

INSERT INTO public.documents (id, tenant_id, title)
VALUES (
    4,
    '22222222-2222-4222-8222-222222222222',
    'Wrong-tenant document'
);

ROLLBACK;
~~~

Expected result: PostgreSQL rejects the `INSERT` because the new row fails `WITH CHECK`. This error proves the role holds table-level `INSERT` privilege yet the policy forbids writing rows into another tenant.

Verify `UPDATE` cannot move a row to another tenant:

~~~sql
BEGIN;

SET LOCAL ROLE app_editor;

SELECT set_config(
    'app.tenant_id',
    '11111111-1111-4111-8111-111111111111',
    true
);

UPDATE public.documents
SET tenant_id = '22222222-2222-4222-8222-222222222222'
WHERE id = 1;

ROLLBACK;
~~~

Expected result: PostgreSQL rejects the update because the modified row fails `WITH CHECK`. This is a critical case: the role is allowed to edit the original row but forbidden from moving it outside the tenant boundary.

Verify `DELETE` targeting a row belonging to another tenant:

~~~sql
BEGIN;

SET LOCAL ROLE app_editor;

SELECT set_config(
    'app.tenant_id',
    '11111111-1111-4111-8111-111111111111',
    true
);

DELETE FROM public.documents
WHERE id = 2;

ROLLBACK;
~~~

Expected result: the command executes but deletes 0 rows because the `USING` policy prevents the role from seeing or affecting tenant B's row. This is not a SQL error.

## 6. Distinguishing Types of Access Denial

Not every blocked access raises an exception. This must be tested explicitly.

| Situation | Typical behavior | How to verify |
|---|---|---|
| Missing schema or table privilege | Permission denied error | Check `SQLSTATE` and privileges with `has_schema_privilege` / `has_table_privilege` |
| `SELECT` filtered out by RLS | Query succeeds, 0 rows | Check dataset and policies under the real role |
| `UPDATE` or `DELETE` targets RLS-hidden row | Query succeeds, 0 rows affected | Check affected row count |
| `INSERT` violates `WITH CHECK` | Access denied error | Verify `SQLSTATE` and `INSERT` policy |
| `UPDATE` produces row violating `WITH CHECK` | Access denied error | Verify post-update row state is rejected |
| No matching policy when RLS is enabled | Default deny on rows | Check policies by role and command |

Privilege errors and RLS policy errors often share SQLSTATE `42501`, condition name `insufficient_privilege`. Checking the error code alone is therefore insufficient to identify which layer blocked the command. Combine error code, error message, current role, and configured privileges/policies.

For `SELECT`, RLS filters rows silently without raising an error. For `UPDATE` and `DELETE`, the affected row count can be 0. A test asserting only "no exception" misses the fact that the application cannot see data; conversely, a test expecting an exception when `SELECT` is filtered has the wrong expectation.

If using a testing library that supports `SQLSTATE` checks, verify both the error code and business outcome. For example, with `pgTAP`, use `throws_ok` to confirm an out-of-tenant `INSERT` fails with `42501`; filtered `SELECT`/`UPDATE`/`DELETE` queries need assertions on result sets or affected row counts.

## 7. Inspecting RLS Configuration to Diagnose Causes

The `pg_policies` system view shows existing policies, command types, target roles, and condition expressions:

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
WHERE schemaname = 'public'
  AND tablename = 'documents'
ORDER BY policyname;
~~~

Check whether RLS and `FORCE RLS` are enabled on the table:

~~~sql
SELECT
    c.relname,
    c.relrowsecurity,
    c.relforcerowsecurity
FROM pg_class AS c
WHERE c.oid = 'public.documents'::regclass;
~~~

Check whether roles can bypass RLS:

~~~sql
SELECT
    rolname,
    rolsuper,
    rolbypassrls
FROM pg_roles
WHERE rolname IN (
    'app_login',
    'app_reader',
    'app_editor'
)
ORDER BY rolname;
~~~

You can call `row_security_active` to determine whether RLS is active on a relation under the current role context:

~~~sql
BEGIN;

SET LOCAL ROLE app_reader;

SELECT row_security_active('public.documents'::regclass);

ROLLBACK;
~~~

When results differ from expectations, inspect in order: `current_user`, schema `USAGE` privilege, table/column privileges, memberships, RLS enabled state, policies by command and role, and finally the `USING`/`WITH CHECK` expressions. Walking layer by layer locates root causes faster than immediately rewriting policies upon seeing 0 rows.

## 8. Additional Execution Paths to Test

### 8.1. Table owner, SUPERUSER, and BYPASSRLS

Always include at least one test verifying the application does not accidentally connect as the table owner or a `BYPASSRLS` role. Without `FORCE ROW LEVEL SECURITY`, the table owner sees all rows. `SUPERUSER` and `BYPASSRLS` bypass policies even when `FORCE` is enabled.

In test environments, compare results under an admin role with results under the application role to understand the difference. Never treat results from an admin role as proof that application policies work.

### 8.2. Views and functions

Views may access underlying tables using the view owner's privileges. On PostgreSQL versions supporting the `security_invoker` option, views can be configured to use the caller's privileges. Therefore, if the application reads through views, test the view directly as the application role and verify underlying table behavior.

Functions marked `SECURITY DEFINER` execute with the privileges of the function owner. If the function owner is the table owner or a `BYPASSRLS` role, the function can open access beyond policy expectations. Use `SECURITY DEFINER` only when truly needed; restrict `EXECUTE`, set a safe `search_path`, and audit the function owner's privileges. Tests must invoke the function under the application role, not only run equivalent SQL directly.

### 8.3. TRUNCATE and privileges not protected by RLS

RLS governs row-level access, but it does not replace all table privileges. `TRUNCATE` and `REFERENCES` are not guarded by row policies the way `SELECT`/`INSERT`/`UPDATE`/`DELETE` are. If a role holds `TRUNCATE`, it can empty the entire table even if RLS permits visibility into only one tenant.

Consequently, audit `TRUNCATE` separately and never grant it to ordinary application roles. Likewise, test `REFERENCES`, `TRIGGER`, and `EXECUTE` when the system relies on those capabilities.

### 8.4. Connection pools and session state

If the application uses a connection pool, a single physical connection can serve multiple requests sequentially. Session-level `SET ROLE` or `SET app.tenant_id` can linger when a connection is reused unless the application resets state properly.

Prefer explicitly scoped transactions:

~~~sql
BEGIN;
SET LOCAL ROLE app_reader;

SELECT set_config(
    'app.tenant_id',
    '11111111-1111-4111-8111-111111111111',
    true
);

SELECT id, title
FROM public.documents;

COMMIT;
~~~

`SET LOCAL ROLE` and `set_config` with `is_local = true` confine state to the transaction. Test two consecutive requests on the same connection: the first for tenant A, the second for tenant B; confirm the second request sees no tenant A data from leftover context. Also test error and rollback paths, since failed transactions must likewise be handled and reset to a safe state by the pool.

### 8.5. Tenant context variables

The example above uses `app.tenant_id` for illustration, yet custom configuration parameters do not authenticate users by themselves. If a role can submit arbitrary SQL, it can set the variable to another tenant. This is an identity design issue that cannot be solved merely by adding another UUID-comparing policy.

In multi-tenant applications, the backend must authenticate the user and then set trusted context within the transaction. If users have direct SQL access, bind tenants to database identities or a controlled context-issuing mechanism that callers cannot spoof. Security tests must include attempts to tamper with tenant context and verify users cannot cross their granted boundaries.

## 9. Recommended Test Matrix

A baseline test suite should cover the following cases. Adapt roles and table names to your actual design.

| Group | Role / condition | Operation | Expected outcome |
|---|---|---|---|
| Connection | Valid account | Connect to database | Connection succeeds |
| Connection | Invalid account or lacks `CONNECT` | Connect to database | Rejected |
| Schema | Role lacks `USAGE` | Access table via schema | Rejected |
| Table ACL | Reader | `SELECT` granted table | Succeeds |
| Table ACL | Reader | Ungranted `INSERT` / `UPDATE` / `DELETE` | Permission denied |
| RLS `SELECT` | Reader, tenant A | `SELECT` data | Sees only tenant A |
| RLS `INSERT` | Editor, tenant A | `INSERT` tenant A | Succeeds |
| RLS `INSERT` | Editor, tenant A | `INSERT` tenant B | Rejected by `WITH CHECK` |
| RLS `UPDATE` | Editor, tenant A | `UPDATE` tenant A row | Succeeds if new row is valid |
| RLS `UPDATE` | Editor, tenant A | Move row to tenant B | Rejected by `WITH CHECK` |
| RLS `DELETE` | Editor, tenant A | `DELETE` tenant B row | 0 rows deleted |
| Default deny | Role with no matching policy | `SELECT` or write rows | No row access |
| Bypass | Table owner / `BYPASSRLS` | `SELECT` data | Confirms expected bypass behavior |
| Pool | Two different-tenant requests on same connection | Sequential reads | No context leak across requests |
| View/function | Application role | Access via view or `SECURITY DEFINER` | Privileges remain per design |

Add tests for every new policy or `GRANT`/`REVOKE` change. When multiple permissive/restrictive policies exist, seed data satisfying and failing each expression individually so newly added policies do not inadvertently widen access.

## 10. Organizing Automated Tests and Test Data

A repeatable testing workflow can be broken into steps:

1. Create an isolated test database or schema; create roles and memberships matching the configuration under test.
2. Create tables, seed multi-tenant data, and configure `GRANT`/`REVOKE`.
3. Enable RLS, create policies, and verify policies in `pg_policies`.
4. Run each test group in its own transaction under the application role.
5. Assert query results, affected row counts, `SQLSTATE`, and `current_user`.
6. `ROLLBACK` or clean up fixtures after the test; never let test data or privileges pollute shared environments.

Every test needs sufficiently distinct data: at least one row for the current tenant, one row for another tenant, and a boundary-value row if policies depend on status conditions. If you seed only one tenant, tests can stay green even when a policy exposes every tenant.

For automated tests, separate three assertion groups clearly:

- **Privilege assertions:** `has_table_privilege`, `has_column_privilege`, `has_schema_privilege`, and command execution outcomes.
- **RLS assertions:** visible rows, writable rows, and filtered rows.
- **Denial assertions:** `SQLSTATE`, appropriate messages, and affected row counts.

Run tests under a role as close to production as possible. Testing as `SUPERUSER` yields misleading results because it bypasses RLS. If an admin role must set up fixtures, switch to the application role before running assertions and verify `current_user` at the start of each test.

## 11. Common Testing Mistakes

- **Checking only GRANT:** a role may hold `SELECT` while RLS still filters all rows. Policies must also be tested.
- **Testing as the table owner:** the owner can bypass RLS, reading all tenants and making it look like the policy is inactive.
- **Forgetting schema privileges:** `GRANT SELECT` on a table fails if the role lacks `USAGE` on the schema.
- **Testing only USING:** a role can edit a valid row and reassign its tenant if `WITH CHECK` is missing or wrong.
- **Assuming no error means access succeeded:** `SELECT` can return 0 rows; `UPDATE`/`DELETE` can affect 0 rows.
- **Assuming every denial comes from RLS:** permission denied can originate from schema, table, column, or function privileges.
- **Granting BYPASSRLS to application roles:** policies stop acting as a boundary for those roles.
- **Failing to reset connection state:** `SET ROLE` or tenant context lingers when a pool reuses connections.
- **Trusting client-supplied tenant context:** users can pick another tenant if permitted to set custom configuration variables.
- **Ignoring views and SECURITY DEFINER:** indirect access paths may execute with the object owner's privileges.

When a test fails, first record the role, `current_user`, `session_user`, `SQLSTATE`, and affected row count. Then cross-check object privileges and applicable policies. Do not immediately edit policies before pinpointing which layer caused the unexpected result, because changing the wrong policy can widen data access.

A thorough test suite proves that each role executes only granted operations, sees only rows within its scope, cannot write or move data into another scope, and never leaks session state across pooled requests.
