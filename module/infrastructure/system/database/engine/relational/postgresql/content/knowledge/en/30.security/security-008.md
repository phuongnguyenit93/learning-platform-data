# Row-Level Security, Policies, USING, and WITH CHECK in PostgreSQL

Suppose a SaaS application stores documents from multiple organizations in a shared `documents` table. Each document has a `tenant_id` or an owner identifier. If the application layer accidentally omits the `WHERE tenant_id = ...` predicate, an ordinary query can expose another organization's data. **Row-Level Security (RLS)** in PostgreSQL lets you enforce access rules **at the row level directly inside the database**.

For example, instead of relying solely on every developer remembering to write:

```sql
SELECT *
FROM documents
WHERE tenant_id = 42;
```

an administrator can create a **policy** so PostgreSQL lets a database role view or modify only rows belonging to that role's scope. That rule applies when querying the table directly, even if the `SELECT` query has no explicit tenant predicate.

The two core expressions in a policy are:

- **`USING`:** determines which **existing rows** are visible or eligible as targets of `UPDATE`/`DELETE`.
- **`WITH CHECK`:** determines whether **new rows or the post-change version of rows** are allowed to be written via `INSERT`/`UPDATE`.

This distinction is critical: a user may be allowed to edit rows they currently own, yet **must not be allowed to transfer a row to another tenant**. `USING` checks the old row; `WITH CHECK` checks the proposed new row.

However, RLS **does not replace** `GRANT`, authentication, column-level privileges, input validation, or application security. Table owners, superusers, roles with `BYPASSRLS`, and objects/functions running under a different security context can alter enforcement. This lesson builds a complete safe lab, explains exactly when RLS filters rows versus rejects writes, shows how multiple policies combine, and covers pitfalls with connection pools, views, and `SECURITY DEFINER`.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain how RLS differs from table/column privileges (`GRANT`/`REVOKE`).
2. Enable/disable RLS on a table via `ALTER TABLE ... ENABLE/DISABLE ROW LEVEL SECURITY`.
3. Read `CREATE POLICY`, `ALTER POLICY`, and `DROP POLICY` syntax.
4. Distinguish `USING` from `WITH CHECK` semantics across `SELECT`, `INSERT`, `UPDATE`, and `DELETE`.
5. Understand the **deny-by-default when no policy matches** rule for roles subject to RLS.
6. Explain `AS PERMISSIVE` and `AS RESTRICTIVE`, how policies combine via OR/AND, and the requirement for at least one matching permissive policy.
7. Recognize exceptions: table owner, `FORCE ROW LEVEL SECURITY`, superuser, and `BYPASSRLS` roles.
8. Build a multi-tenant example using database roles and test with `SET ROLE` in a lab database.
9. Separate row read permissions, row update permissions, and permission to change a row's tenant value.
10. Inspect `pg_policies`, catalog metadata, and troubleshoot "SELECT returns 0 rows", "UPDATE 0 rows", and "new row violates row-level security policy".
11. Evaluate RLS limits with `SECURITY DEFINER`, views, connection pooling, session context, constraints, and operations outside row policies such as `TRUNCATE`.
12. Design tests preventing cross-tenant data leaks and enforce least privilege for production.

## 2. Distinguishing GRANT from Row-Level Security

PostgreSQL has multiple protection layers. Two common layers are:

1. **Object privileges:** whether a role can run `SELECT`, `INSERT`, `UPDATE`, or `DELETE` on the table at all—managed via `GRANT`/`REVOKE`.
2. **Row-level policies:** once the role is permitted to run the command, **which rows** may participate and **which new values** may be stored?

Example:

```sql
GRANT SELECT, UPDATE
ON TABLE app.documents
TO app_reader_writer;
```

This `GRANT` does not restrict rows by tenant. If RLS is disabled, the role can `SELECT`/`UPDATE` rows subject to existing object rights and other constraints. If RLS is enabled and policies apply, access is further restricted by those policies.

### 2.1. Two Inspection Gates

```text
Database role submits SQL
          |
          v
Check object/schema/column privileges
          |
          +---- Insufficient -> ERROR: permission denied
          |
          v
Check whether RLS applies to role/table
          |
          +---- Bypass/disabled -> No RLS row filtering applied
          |
          v
Apply policies for matching command and role
          |
          +---- USING: selects existing rows eligible to read/update/delete
          |
          +---- WITH CHECK: validates new rows for INSERT/UPDATE
          |
          v
Execute command under SQL/MVCC/constraint rules
```

This diagram is conceptual: in practice, checks and expressions are integrated into the planner/executor per internal rules rather than always running as a literal physical step-by-step pipeline.

### 2.2. RLS Does Not Grant SELECT

A `USING (true)` policy for a role lacking table privileges **does not grant** `SELECT`. The role still requires matching table privileges and schema `USAGE`.

### 2.3. GRANT SELECT Does Not Remove Policies

A role with `GRANT SELECT ON documents` and a policy allowing only tenant A still sees only tenant A's rows on `SELECT`, unless the role bypasses RLS.

### 2.4. RLS Does Not Replace Column Permissions

For example, a role may read all rows of tenant A yet must not read column `secret_token`. Use `GRANT SELECT(col1, col2)`, views/APIs, or separate column models. RLS controls **rows**, without hiding sensitive column values inside visible rows.

## 3. When Does RLS Take Effect?

RLS is a **per-table** property. Policies may already exist, yet until `ENABLE ROW LEVEL SECURITY` is set on the table, those policies do not restrict row access as intended.

```sql
ALTER TABLE app.documents
ENABLE ROW LEVEL SECURITY;
```

From this point on, roles subject to RLS have policies applied when operating on the table.

### 3.1. Enabling RLS with No Policies: Default Deny

Once RLS is enabled, if no policy applies to a given role/command, the default behavior for a role **subject to RLS** is:

- `SELECT` sees no permitted rows -> returns **0 rows**.
- `UPDATE`/`DELETE` finds no eligible target rows -> affects **0 rows**.
- `INSERT` attempts a new row that passes no policy check -> **rejected** with an RLS error.

Note that this is **not** what an owner or superuser bypassing RLS observes by default. Always test using a real role subject to RLS.

### 3.2. Disabling RLS

```sql
ALTER TABLE app.documents
DISABLE ROW LEVEL SECURITY;
```

Disabling RLS **does not drop policies**, though they stop filtering ordinary table commands until re-enabled. This is sensitive DDL reserved strictly for authorized administrators.

### 3.3. Enabling RLS Does Not Automatically Make a Multi-Tenant App Safe

RLS is only as strong as:

- Trustworthy role/tenant identity establishment.
- Policies written accurately for every command type.
- Audited schema privileges, bypass roles, views, functions, and background jobs.
- Application controls preventing users from arbitrarily spoofing another tenant's context.
- Tests covering both read paths and write paths.

## 4. CREATE POLICY Syntax

Core syntax:

```sql
CREATE POLICY policy_name ON schema.table_name
    [ AS PERMISSIVE | RESTRICTIVE ]
    [ FOR ALL | SELECT | INSERT | UPDATE | DELETE ]
    [ TO role_name [, ...] ]
    [ USING ( using_expression ) ]
    [ WITH CHECK ( check_expression ) ];
```

Clauses:

| Clause | Meaning |
| --- | --- |
| `policy_name` | Policy name, unique within the table. |
| `ON schema.table` | Protected table. |
| `AS PERMISSIVE` | Permissive policy (default); multiple permissive policies combine with OR. |
| `AS RESTRICTIVE` | Additional restrictive filter; multiple restrictive policies combine with AND. |
| `FOR ALL` | Applies across command types per respective semantics. |
| `FOR SELECT` | Row visibility filter using `USING`. |
| `FOR INSERT` | New row validation using `WITH CHECK`. |
| `FOR UPDATE` | `USING` filters existing rows; `WITH CHECK` validates new rows. |
| `FOR DELETE` | `USING` filters deletable rows. |
| `TO roles` | Roles the policy applies to; defaults to `PUBLIC`. |
| `USING` | Boolean expression evaluated against existing rows. |
| `WITH CHECK` | Boolean expression validating proposed rows after `INSERT`/`UPDATE`. |

### 4.1. Invalid or Unsuitable Combinations

- `FOR SELECT` uses only `USING`; do not specify `WITH CHECK`.
- `FOR DELETE` uses only `USING` because `DELETE` creates no new row.
- `FOR INSERT` uses only `WITH CHECK`; do not use `USING` on an `INSERT`-only policy.
- `FOR UPDATE` can specify both.
- `FOR ALL` can specify both `USING` and `WITH CHECK`.

### 4.2. Policy Expressions Are SQL Booleans

`USING (tenant_id = current_setting('app.tenant_id')::integer)` or `WITH CHECK (owner_name = current_user)` are SQL boolean expressions. To allow a row, the expression must evaluate to **TRUE**. `FALSE` or SQL `NULL`/`UNKNOWN` does not pass.

### 4.3. Do Not Cram All Logic into One Hard-to-Read Policy

Splitting by command type makes policies easier to review:

```sql
CREATE POLICY docs_read ... FOR SELECT ... USING (...);
CREATE POLICY docs_create ... FOR INSERT ... WITH CHECK (...);
CREATE POLICY docs_edit ... FOR UPDATE ... USING (...) WITH CHECK (...);
CREATE POLICY docs_remove ... FOR DELETE ... USING (...);
```

This syntax is illustrative; complete runnable examples follow in the lab section.

## 5. Semantics Table for USING and WITH CHECK

| Command | Which row does `USING` evaluate? | Which row does `WITH CHECK` evaluate? | Behavior when condition fails |
| --- | --- | --- | --- |
| `SELECT` | Existing row being read. | Not applicable. | Row is omitted from results. |
| `INSERT` | Not applicable. | Proposed new row for `INSERT`. | `INSERT` fails with RLS error. |
| `UPDATE` | Existing row eligible as `UPDATE` target. | New row version after `SET`/triggers. | Old row is filtered out; invalid new row raises error. |
| `DELETE` | Existing row eligible for deletion. | Not applicable. | Row is excluded from deletion targets. |

Owner-based policy example:

```sql
CREATE POLICY owner_can_update ON app.documents
FOR UPDATE
USING (owner_name = current_user)
WITH CHECK (owner_name = current_user);
```

If `current_user` is `team_a`:

- `UPDATE` a `team_a` row: `USING` passes.
- `UPDATE` a `team_b` row: row is not selected as an eligible target by the policy.
- `UPDATE` a `team_a` row and `SET owner_name = 'team_b'`: the new row violates `WITH CHECK`, so `UPDATE` is rejected.

**Distinction:** `USING` is not merely an optional app-supplied `WHERE` clause; it is a database-enforced row-level access predicate.

## 6. Lab Setup: Simulating Two Tenants with Database Roles

To keep the lab independent of app-set session variables, we use **two distinct database roles**. Each row stores `tenant_role` matching the authorized role name.

**Lab prerequisites:** run in a dedicated database using an admin account permitted to create roles, schemas, tables, policies, and `SET ROLE` to both test roles (e.g., a superuser in a lab environment). Never use superuser for production apps; use it here solely to initialize and simulate.

### 6.1. Creating Two Simulated Tenant Roles

```sql
CREATE ROLE rls_demo_alpha NOLOGIN;
CREATE ROLE rls_demo_beta NOLOGIN;
```

`NOLOGIN` prevents direct logins with these roles. The admin session uses `SET ROLE` to test privileges; if your test environment prohibits `SET ROLE`, a DBA must configure appropriate memberships. Never embed hard-coded passwords in lessons just to test.

### 6.2. Creating the Schema and Table

```sql
CREATE SCHEMA rls_demo;

CREATE TABLE rls_demo.documents (
    document_id integer PRIMARY KEY,
    tenant_role text NOT NULL,
    title text NOT NULL,
    state text NOT NULL
        CHECK (state IN ('draft','published','archived')),
    amount numeric(12,2) NOT NULL
        CHECK (amount >= 0)
);
```

This is a minimal table focused on policies. In real applications, use stable tenant keys, appropriate FKs/constraints, and verified account/role mappings.

### 6.3. Inserting Initial Data as Owner/Admin

```sql
INSERT INTO rls_demo.documents
    (document_id, tenant_role, title, state, amount)
VALUES
    (1, 'rls_demo_alpha', 'Alpha draft',     'draft',     100),
    (2, 'rls_demo_alpha', 'Alpha released',  'published', 250),
    (3, 'rls_demo_beta',  'Beta draft',      'draft',      90),
    (4, 'rls_demo_beta',  'Beta released',   'published', 410),
    (5, 'rls_demo_alpha', 'Alpha archive',   'archived',   30),
    (6, 'rls_demo_beta',  'Beta archive',    'archived',   20);
```

Initial data:

| document_id | tenant_role | state | amount |
| ---: | --- | --- | ---: |
| 1 | rls_demo_alpha | draft | 100 |
| 2 | rls_demo_alpha | published | 250 |
| 3 | rls_demo_beta | draft | 90 |
| 4 | rls_demo_beta | published | 410 |
| 5 | rls_demo_alpha | archived | 30 |
| 6 | rls_demo_beta | archived | 20 |

### 6.4. Granting Object Privileges to Roles

```sql
GRANT USAGE ON SCHEMA rls_demo
TO rls_demo_alpha, rls_demo_beta;

GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE rls_demo.documents
TO rls_demo_alpha, rls_demo_beta;
```

These `GRANT`s are prerequisites for the lab; **they do not yet isolate each tenant to its own rows**.

### 6.5. Enabling RLS

```sql
ALTER TABLE rls_demo.documents
ENABLE ROW LEVEL SECURITY;
```

At this instant **no policies exist yet**, so roles subject to RLS cannot read or write any rows despite holding table `GRANT`s.

### 6.6. Testing Default-Deny with SET ROLE

```sql
SET ROLE rls_demo_alpha;

SELECT current_user AS active_role;

SELECT document_id, title
FROM rls_demo.documents
ORDER BY document_id;

RESET ROLE;
```

With an admin session permitted to `SET ROLE`, `current_user` becomes `rls_demo_alpha` and `SELECT` returns **0 rows** because no policy exists yet. If you get `permission denied to set role`, that is a role-switching permission issue on the test session; have an admin grant membership rather than disabling RLS.

### 6.7. Why Can the Table Creator Still See Six Rows?

By default, **the table owner bypasses RLS**; superusers and `BYPASSRLS` roles also bypass. The admin account that created the table can `SELECT` all six rows even with RLS enabled. Therefore **never test RLS solely as the table creator**; always test under a real role subject to the policy.

## 7. SELECT Policy: Filtering Rows with USING

Create a policy allowing each role to read documents tagged with its own role name:

```sql
CREATE POLICY documents_select_own
ON rls_demo.documents
FOR SELECT
TO rls_demo_alpha, rls_demo_beta
USING (tenant_role = current_user::text);
```

This policy grants no new table privileges; both roles already received `GRANT SELECT` above.

### 7.1. SELECT as Alpha

```sql
SET ROLE rls_demo_alpha;

SELECT document_id, tenant_role, title, state
FROM rls_demo.documents
ORDER BY document_id;

RESET ROLE;
```

Output:

| document_id | tenant_role | title | state |
| ---: | --- | --- | --- |
| 1 | rls_demo_alpha | Alpha draft | draft |
| 2 | rls_demo_alpha | Alpha released | published |
| 5 | rls_demo_alpha | Alpha archive | archived |

The user SQL did not need `WHERE tenant_role = 'rls_demo_alpha'` to achieve this row restriction: PostgreSQL applied the policy.

### 7.2. SELECT as Beta

```sql
SET ROLE rls_demo_beta;

SELECT document_id, tenant_role, title, state
FROM rls_demo.documents
ORDER BY document_id;

RESET ROLE;
```

Results contain only IDs **3, 4, and 6**.

### 7.3. Requesting Another Tenant's Row Explicitly

```sql
SET ROLE rls_demo_alpha;

SELECT *
FROM rls_demo.documents
WHERE document_id = 4;

RESET ROLE;
```

For alpha, ID 4 fails the `USING` predicate, so the query **returns 0 rows**—not an error saying "you requested another tenant's document."

That is often desirable to avoid leaking existence, though your API should define clear HTTP 404/403 conventions without unnecessarily revealing out-of-scope row existence.

### 7.4. SELECT COUNT(*) Also Obeys RLS

```sql
SET ROLE rls_demo_alpha;

SELECT COUNT(*) AS visible_documents,
       SUM(amount) AS visible_amount
FROM rls_demo.documents;

RESET ROLE;
```

Alpha gets **3 rows** and sum `amount` **380**. Beta also gets 3 rows with sum `amount` **520**. A role under RLS never aggregates invisible rows.

### 7.5. JOINs and Aggregations Still Require Correct Semantics

Policies on `documents` apply whenever that table appears in a `JOIN` or subquery per RLS rules. However, RLS **does not prevent join multiplication**, replace privileges on other tables, or fix incorrect aggregates. Evaluate every table holding tenant data independently.

## 8. INSERT Policy: Validating New Rows with WITH CHECK

Create a policy allowing inserts only when `tenant_role` matches the current role:

```sql
CREATE POLICY documents_insert_own
ON rls_demo.documents
FOR INSERT
TO rls_demo_alpha, rls_demo_beta
WITH CHECK (tenant_role = current_user::text);
```

### 8.1. Valid-Tenant INSERT

```sql
BEGIN;

SET LOCAL ROLE rls_demo_alpha;

INSERT INTO rls_demo.documents
    (document_id, tenant_role, title, state, amount)
VALUES
    (11, 'rls_demo_alpha', 'Alpha new', 'draft', 60)
RETURNING document_id, tenant_role, title;

ROLLBACK;
```

The new row satisfies `WITH CHECK`, so the `INSERT` succeeds. `ROLLBACK` reverts it so the lab dataset stays clean. `SET LOCAL ROLE` scopes to this transaction and requires permission to switch roles.

### 8.2. Wrong-Tenant INSERT

```sql
-- Run separately in the lab if you want to observe the error:
-- SET ROLE rls_demo_alpha;
-- INSERT INTO rls_demo.documents
--     (document_id, tenant_role, title, state, amount)
-- VALUES
--     (12, 'rls_demo_beta', 'Injected beta document', 'draft', 10);
-- RESET ROLE;
```

The policy checks **the proposed new row**, sees `tenant_role != current_user::text`, and **rejects** the `INSERT` (typically with `new row violates row-level security policy for table ...`).

Note: when deliberately running a failing statement inside a transaction, PostgreSQL marks the transaction as aborted until `ROLLBACK` or savepoint recovery. Failing statements are commented out so they don't interrupt the main walkthrough.

### 8.3. INSERT Has No USING

A standard `INSERT` has no "existing row" in the target table to filter. That is why `FOR INSERT` policies use `WITH CHECK` rather than `USING`.

### 8.4. Default Values Still Pass Through WITH CHECK

If the table defines a `DEFAULT` for `tenant_role` or a `BEFORE INSERT` trigger populates the tenant, **the final proposed row** must still satisfy the matching policy. Never treat `DEFAULT`s or triggers as exemptions from RLS.

### 8.5. INSERT ... SELECT and COPY FROM

RLS is not bypassed merely because rows are inserted in bulk. `INSERT ... SELECT` must still obey the `INSERT` policy on the target table. For `COPY FROM` on tables with RLS, PostgreSQL imposes specific restrictions and often requires using `INSERT` instead when row security enforcement is needed; never assume bulk loads enforce RLS identically to `INSERT` and silently succeed.

## 9. UPDATE Policy: USING Checks the Old Row, WITH CHECK Checks the New Row

This is the easiest place to make mistakes in multi-tenant designs.

```sql
CREATE POLICY documents_update_own
ON rls_demo.documents
FOR UPDATE
TO rls_demo_alpha, rls_demo_beta
USING (tenant_role = current_user::text)
WITH CHECK (tenant_role = current_user::text);
```

### 9.1. Updating a Row Belonging to the Same Tenant

```sql
BEGIN;

SET LOCAL ROLE rls_demo_alpha;

UPDATE rls_demo.documents
SET title = 'Alpha draft revised'
WHERE document_id = 1
RETURNING document_id, tenant_role, title;

ROLLBACK;
```

ID 1 belongs to alpha, so `USING` is `TRUE`. After changing `title`, `tenant_role` remains alpha, so `WITH CHECK` is `TRUE`. The update succeeds and returns the updated row.

### 9.2. Attempting to UPDATE a Beta Tenant Row

```sql
BEGIN;

SET LOCAL ROLE rls_demo_alpha;

UPDATE rls_demo.documents
SET title = 'Unauthorized edit'
WHERE document_id = 4;

ROLLBACK;
```

ID 4 belongs to beta. The policy rejects it as an updatable existing row, so the result is **UPDATE 0 rows**. Physically existing while hidden by RLS does not make it an eligible target.

### 9.3. Attempting to Reassign an Alpha Row to Beta

```sql
-- Expected to be rejected if executed under role alpha:
-- SET ROLE rls_demo_alpha;
-- UPDATE rls_demo.documents
-- SET tenant_role = 'rls_demo_beta'
-- WHERE document_id = 1;
-- RESET ROLE;
```

Here:

1. Existing row `document_id = 1` has `tenant_role = 'rls_demo_alpha'` -> **USING TRUE**.
2. Post-update row would have `tenant_role = 'rls_demo_beta'` -> **WITH CHECK FALSE**.
3. PostgreSQL rejects the operation because the new row version violates the policy.

**If a policy checks only the old row, developers easily overlook the rule "cannot write rows out into another tenant."**

### 9.4. USING and WITH CHECK Need Not Be Identical

Business rules might allow users to edit **their own drafts** while only permitting valid state transitions. `USING` then checks "can edit this existing row?" and `WITH CHECK` checks "is the resulting row state valid?".

Hypothetical policy example:

```sql
CREATE POLICY editors_update_drafts ON app.documents
FOR UPDATE
TO app_editor
USING (
    tenant_id = app.current_tenant_id()
    AND state = 'draft'
)
WITH CHECK (
    tenant_id = app.current_tenant_id()
    AND state IN ('draft', 'review')
);
```

This is a **design template** assuming the table, role, and a trusted `app.current_tenant_id()` function exist. Users can edit a `draft` and transition it to `review`, yet once it becomes `review`, it no longer passes `USING (state = 'draft')` for further edits under this policy.

### 9.5. What Does Omitting WITH CHECK in UPDATE Mean?

For a `FOR UPDATE` or `FOR ALL` policy specifying `USING` **without an explicit `WITH CHECK`**, PostgreSQL falls back to using the `USING` expression to validate new rows as well. Thus:

```sql
CREATE POLICY example_update ON app.documents
FOR UPDATE
USING (tenant_id = app.current_tenant_id());
```

still blocks transferring a row to another tenant if the new `tenant_id` fails `USING`. In security reviews, however, writing **both** explicitly is clearer and prevents confusion when read/target rules diverge from write rules.

Never assume "omitting `WITH CHECK` means any value can be written" while ignoring PostgreSQL's fallback rule.

### 9.6. SELECT Policies Affect UPDATE

`UPDATE` and `DELETE` often need to identify rows, and when `UPDATE` reads columns in `WHERE`, `SET`, or `RETURNING`, `SELECT` privileges and `SELECT` policies come into play. In our lab, we granted `SELECT` and created a `FOR SELECT` policy, so `UPDATE ... RETURNING` behaves predictably.

Never design an `UPDATE` policy in isolation and assume `UPDATE ... RETURNING *` will work if the role cannot `SELECT` any columns or rows. Test actual statements alongside column grants and `SELECT` policies.

## 10. DELETE Policy: Selecting Deletable Rows with USING

```sql
CREATE POLICY documents_delete_own
ON rls_demo.documents
FOR DELETE
TO rls_demo_alpha, rls_demo_beta
USING (tenant_role = current_user::text);
```

### 10.1. Deleting an Own-Tenant Row

```sql
BEGIN;

SET LOCAL ROLE rls_demo_alpha;

DELETE FROM rls_demo.documents
WHERE document_id = 5
RETURNING document_id, title;

ROLLBACK;
```

Alpha row `document_id = 5` is eligible for deletion per `USING`, and `ROLLBACK` preserves lab data.

### 10.2. Cannot Delete Another Tenant's Row

```sql
BEGIN;

SET LOCAL ROLE rls_demo_alpha;

DELETE FROM rls_demo.documents
WHERE document_id = 6;

ROLLBACK;
```

Beta row ID 6 fails `USING`, so the statement normally affects **0 rows**.

### 10.3. DELETE Has No WITH CHECK

`DELETE` produces no new row to validate, so `FOR DELETE` policies have only `USING`. Audit, retention, and foreign-key constraints remain separate concerns.

### 10.4. Do Not Equate 0 Rows with "Row Does Not Exist"

An app calling `DELETE` by ID and receiving row count 0 could mean:

- The row does not exist physically.
- The row exists but belongs to another tenant.
- The row failed an additional restrictive policy.
- Another `WHERE` predicate did not match.

APIs should handle responses and logging without leaking out-of-scope existence while keeping sufficient admin visibility for incident investigation.

## 11. Complete Set of Four Policies on the Lab Table

Once created, the table has:

```text
rls_demo.documents
     |
     +-- SELECT documents_select_own
     |       USING (tenant_role = current_user)
     |
     +-- INSERT documents_insert_own
     |       WITH CHECK (tenant_role = current_user)
     |
     +-- UPDATE documents_update_own
     |       USING (tenant_role = current_user)
     |       WITH CHECK (tenant_role = current_user)
     |
     +-- DELETE documents_delete_own
             USING (tenant_role = current_user)
```

### 11.1. Action Matrix Tests

| Test under role alpha | Expected outcome |
| --- | --- |
| `SELECT` all | Sees only IDs 1, 2, 5. |
| `SELECT` beta's ID 4 | 0 rows. |
| `INSERT` `tenant_role` alpha | Allowed. |
| `INSERT` `tenant_role` beta | `WITH CHECK` error. |
| `UPDATE` title on ID 1 | Allowed. |
| `UPDATE` title on ID 4 | 0 rows. |
| `UPDATE` ID 1 to `tenant_role` beta | `WITH CHECK` error. |
| `DELETE` ID 5 | Allowed. |
| `DELETE` ID 6 | 0 rows. |

### 11.2. Value of Testing with Real Roles

Testing as owner or superuser bypasses policies and produces completely different behavior. Write separate tests for alpha and beta, especially whenever modifying policies or role mappings.

### 11.3. Lab Policies Are Not Permanent Data Constraints

An administrator bypassing RLS can still `INSERT` a row with any `tenant_role` (subject to constraints). If an invariant like "every document always belongs to a valid tenant" must hold across **all write paths**, enforce it with FKs, `CHECK` constraints, and ownership architecture—not solely app-role RLS.

## 12. FORCE ROW LEVEL SECURITY for Table Owners

By default, **table owners bypass RLS**. If an application connects using the table-owning account, enabling RLS may provide none of the isolation you expected.

To force the table owner to obey RLS too:

```sql
ALTER TABLE rls_demo.documents
FORCE ROW LEVEL SECURITY;
```

Thereafter, an ordinary table owner is subject to policies when querying the table instead of bypassing by default ownership.

### 12.1. FORCE Does Not Constrain Superusers or BYPASSRLS

`FORCE ROW LEVEL SECURITY` does not turn a superuser or a `BYPASSRLS` role into an ordinary role. Both still bypass RLS by PostgreSQL design.

### 12.2. Do Not Apply FORCE Mid-Lab While the Owner Still Inserts Multi-Tenant Seed Data

In the lab, initial seed inserts ran as owner/admin before policies existed. If you enable `FORCE` on a **non-superuser** owner and policies allow only `tenant_role = current_user`, the owner may no longer see alpha/beta rows when inspecting. That is working as configured, not missing data.

If testing `FORCE`:

```sql
-- Run as owner or authorized admin:
ALTER TABLE rls_demo.documents FORCE ROW LEVEL SECURITY;

-- After observing, restore depending on lab goal:
ALTER TABLE rls_demo.documents NO FORCE ROW LEVEL SECURITY;
```

As a superuser, running those two commands does not show the non-superuser owner difference; to test `FORCE` realistically, use a dedicated owner role **without `BYPASSRLS` or `SUPERUSER`** in an appropriate lab.

### 12.3. Be Cautious with Applications Using Owner Roles

Best practice separates:

- **DDL owner/migration role:** owns tables and runs schema migrations.
- **Application data role:** non-owner, no `BYPASSRLS`, minimal DML privileges.
- **Maintenance role:** granted specific maintenance privileges under operational policy.

This eliminates accidental default bypass while clarifying accountability compared to connecting apps as owner or superuser.

## 13. Superuser, BYPASSRLS, and row_security = off

Never confuse these three mechanisms.

### 13.1. Superuser

PostgreSQL superusers bypass RLS. Never use a superuser as the daily data-access account for a SaaS API; a single query bug gains cluster-wide impact.

### 13.2. Roles with BYPASSRLS

A role with the `BYPASSRLS` attribute bypasses Row-Level Security. This is a powerful privilege reserved for tightly controlled administrative tasks.

Authorized catalog query:

```sql
SELECT rolname, rolsuper, rolbypassrls
FROM pg_roles
WHERE rolname IN (
    'rls_demo_alpha',
    'rls_demo_beta'
)
ORDER BY rolname;
```

In our lab, both roles were created without `SUPERUSER`/`BYPASSRLS`, so `rolsuper` and `rolbypassrls` are `FALSE`.

Only suitably privileged role administrators can grant or alter this attribute. Never hand `BYPASSRLS` to an app role just to avoid writing a tricky policy.

### 13.3. row_security = off Is Not a Bypass Switch

PostgreSQL has the parameter:

```sql
SHOW row_security;
```

Setting `off` **does not grant an ordinary role permission to bypass RLS**. Instead, it causes commands to error whenever RLS would filter rows, helping detect incomplete exports or backups.

Lab-only illustration:

```sql
-- Expect error/ROLLBACK handling whenever a policy would filter rows:
-- SET ROLE rls_demo_alpha;
-- SET row_security = off;
-- SELECT * FROM rls_demo.documents;
-- RESET row_security;
-- RESET ROLE;
```

Never use `SET row_security = off` trying to fix an app seeing zero rows; check policies, roles, object grants, and query intent instead.

### 13.4. Backups and Exports

A full-table export run under a role subject to RLS may silently export only a subset—creating incomplete backups. Design dedicated backup roles and processes, verify restores, and audit who holds bypass privileges. `row_security = off` helps catch unintended row filtering during exports, not grant bypass rights.

## 14. PERMISSIVE and RESTRICTIVE: OR and AND

When multiple policies apply to the same command and role, PostgreSQL combines them by policy type:

- Matching **PERMISSIVE** policies combine with **OR**.
- Matching **RESTRICTIVE** policies combine with **AND**.
- Access requires passing at least one permissive policy **and** all applicable restrictive policies.

Conceptually:

```text
Allowed =
    (P1 OR P2 OR ... Pn)
    AND
    (R1 AND R2 AND ... Rm)
```

where `P` are permissive and `R` are restrictive. If **no permissive policy applies**, a lone restrictive policy **grants zero access**.

### 14.1. Example: Hiding Archived Documents with a Restrictive Policy

The current `SELECT` policies let alpha see IDs 1, 2, and 5. To ensure **neither tenant sees `archived` rows in `SELECT`**, add a restrictive policy.

Wrapped in a transaction to test without altering base lab policies:

```sql
BEGIN;

CREATE POLICY documents_hide_archived
ON rls_demo.documents
AS RESTRICTIVE
FOR SELECT
TO rls_demo_alpha, rls_demo_beta
USING (state <> 'archived');

SET LOCAL ROLE rls_demo_alpha;

SELECT document_id, title, state
FROM rls_demo.documents
ORDER BY document_id;

ROLLBACK;
```

Inside this transaction, alpha sees only IDs **1 and 2**. The permissive policy selects alpha's rows, and the restrictive policy narrows them further to non-archived rows. `ROLLBACK` removes the test policy, returning the lab to its prior state.

### 14.2. Two Permissive Policies Can Widen Access

Suppose a system has:

```sql
CREATE POLICY p_own ON app.documents
FOR SELECT TO app_user
USING (tenant_id = app.current_tenant_id());

CREATE POLICY p_published ON app.documents
FOR SELECT TO app_user
USING (state = 'published');
```

Two permissive policies combine via OR:

```text
(tenant_id = current tenant)
OR
(state = 'published')
```

This lets users read **every published row across all tenants** when both policies apply. If the intent was "only current tenant's rows AND only published," combine both conditions with `AND` in one policy or pair a permissive tenant policy with a restrictive state policy.

**This is a common multi-tenant leak bug: adding a `PERMISSIVE` policy thinking it tightens access, when it actually widens access via OR.**

### 14.3. A Lone Restrictive Policy Is Not Enough

If you have only:

```sql
CREATE POLICY only_restrictive ON app.documents
AS RESTRICTIVE
FOR SELECT
TO app_user
USING (state = 'published');
```

with no permissive policy permitting row reads, the result remains default deny. Restrictive policies **narrow** a set already allowed by permissive policies; they do not replace the base permissive grant.

### 14.4. Restrictive for WITH CHECK

A restrictive policy covering `INSERT`/`UPDATE` adds `AND` conditions on new rows. However, never write a `FOR SELECT` policy expecting it to enforce `INSERT` new-row checks. Specify the exact command and check expression.

### 14.5. Be Careful with FOR ALL Policies

A `FOR ALL` policy applies across `SELECT`/`INSERT`/`UPDATE`/`DELETE`. If it is permissive with `USING (true)`, it can silently widen `SELECT`/`UPDATE`/`DELETE` even when strict per-command policies already exist.

Never add:

```sql
-- Very dangerous if applied to all commands for everyone:
-- CREATE POLICY allow_everything
-- ON rls_demo.documents
-- FOR ALL TO PUBLIC
-- USING (true) WITH CHECK (true);
```

without understanding how it ORs with existing policies.

## 15. FOR ALL Policies and WITH CHECK Fallback

When commands share identical rules, one combined policy can be written as:

```sql
CREATE POLICY documents_tenant_all ON app.documents
FOR ALL
TO app_user
USING (tenant_id = app.current_tenant_id())
WITH CHECK (tenant_id = app.current_tenant_id());
```

This pattern assumes a trusted `app.current_tenant_id()` and existing objects, applying one consistent tenant rule across supported commands.

### 15.1. Advantage

Fewer policies and a clear core invariant: "never cross tenant boundaries."

### 15.2. Limitations

Real-world rules often diverge by command:

- Anyone in the tenant can read published documents.
- Only the author can edit drafts.
- Only moderators can delete violating documents.
- Reviewers can view pending rows without changing tenant ownership.

One broad `FOR ALL` policy struggles to express distinct per-command boundaries.

### 15.3. USING Serves as CHECK When Omitted

For `FOR ALL` or `FOR UPDATE` policies, PostgreSQL reuses the `USING` expression to check new rows whenever `WITH CHECK` is omitted.

Example:

```sql
CREATE POLICY documents_tenant_all ON app.documents
FOR ALL
USING (tenant_id = app.current_tenant_id());
```

The tenant rule still checks new rows on `INSERT`/`UPDATE` via PostgreSQL's fallback rule. Even so, writing both `USING` and `WITH CHECK` explicitly helps reviewers verify old-row vs. new-row logic, especially as policies evolve.

### 15.4. Never Treat FOR ALL as Table Privileges

Even with `FOR ALL USING(true) WITH CHECK(true)`, a role lacking `INSERT`/`UPDATE`/`DELETE` table grants still cannot execute those commands. `GRANT` and policies remain two separate layers.

## 16. TO Role and PUBLIC: Who Does a Policy Apply To?

In the lab:

```sql
TO rls_demo_alpha, rls_demo_beta
```

scopes the policy to those two database roles. Omitting `TO` defaults the policy to `PUBLIC` (the pseudo-role covering all roles, not a literal username).

### 16.1. Policy TO PUBLIC Differs from GRANT TO PUBLIC

A policy `TO PUBLIC` means **this RLS rule is evaluated for all roles**. It does not `GRANT SELECT ON TABLE ... TO PUBLIC`. Without table privileges, `SELECT` still fails with permission denied.

### 16.2. Membership Affects Policy Scope

A policy targeting a database role can also apply via role membership under PostgreSQL semantics. Therefore permission audits cannot stop at reading `TO role`—inspect memberships, inheritance, and `SET ROLE`/execution under other roles.

Never assume a user "not named in the policy" is exempt from or unaffected by a policy if that user is a member of a role listed in `TO`.

### 16.3. SET ROLE Changes current_user

`SET ROLE rls_demo_alpha` changes the active role used for permission checks and `current_user` in the session, while `session_user` remains the original login identity.

```sql
SET ROLE rls_demo_alpha;

SELECT
    current_user AS effective_role,
    session_user AS login_identity;

RESET ROLE;
```

In our demo, policies compare against `current_user`. If your system uses `SECURITY DEFINER` wrappers, `current_user` inside the wrapper differs from the app role—test explicitly rather than generalizing.

### 16.4. Do Not Create Roles per Request Unnecessarily

A database role per end user/tenant establishes crisp trust boundaries, yet incurs management cost across roles, memberships, connection pools, and provisioning. At high tenant counts, applications often use one shared app role paired with trusted session context—see the section below on session-variable spoofing risks.

## 17. ALTER POLICY, DROP POLICY, and Lifecycle Management

To update a rule:

```sql
ALTER POLICY documents_select_own
ON rls_demo.documents
USING (tenant_role = current_user::text);
```

This illustrates updating the expression (preserving the lab's logic here).

### 17.1. What Can ALTER POLICY Change?

`ALTER POLICY` can modify `TO ...` roles, `USING`, and `WITH CHECK` expressions. However, not every property can be altered in place: changing command scope (`FOR SELECT` -> `FOR UPDATE`) or permissive/restrictive generally requires **`DROP` + `CREATE`**.

### 17.2. DROP POLICY

```sql
-- Example only; do not run while following the lab:
-- DROP POLICY documents_select_own
-- ON rls_demo.documents;
```

Dropping the only matching `SELECT` policy puts alpha/beta back into default-deny (0 rows) even though `GRANT SELECT` remains.

### 17.3. Policy Migrations Must Account for Transactions and Locks

Changing policies is sensitive DDL; deploying at peak traffic can affect query plans, locks, and visible row sets. Prepare migration scripts, test role matrices, measure impact, prepare rollbacks, and avoid intermediate windows that unintentionally widen access.

### 17.4. Use Meaningful Policy Names

Names like `documents_select_own`, `documents_insert_own`, and `documents_reviewers_select` are far easier to audit than `policy1` or `p2`. Names are metadata; real enforcement lives in the expressions and `TO` roles.

## 18. Inspecting Policies via pg_policies

PostgreSQL exposes the `pg_policies` catalog view:

```sql
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
WHERE schemaname = 'rls_demo'
  AND tablename = 'documents'
ORDER BY policyname;
```

In our lab, this returns four policies covering `SELECT`/`INSERT`/`UPDATE`/`DELETE` with `tenant_role = current_user::text` in the matching expression columns.

### 18.1. qual and with_check

- `qual` shows the `USING` expression as formatted by PostgreSQL.
- `with_check` shows the declared `WITH CHECK` expression.

If `with_check` is empty on a policy with `USING`, never assume `INSERT`/`UPDATE` can write arbitrary values; remember the fallback rule.

### 18.2. Checking Whether RLS Is Enabled on a Table

```sql
SELECT
    c.oid::regclass AS table_name,
    c.relrowsecurity AS rls_enabled,
    c.relforcerowsecurity AS force_owner_rls
FROM pg_class AS c
WHERE c.oid = 'rls_demo.documents'::regclass;
```

`rls_enabled` is expected to be `true`. `force_owner_rls` depends on whether the `FORCE` test was reverted.

### 18.3. Object Privileges Must Still Be Checked Separately

```sql
SELECT
    has_table_privilege(
        'rls_demo_alpha',
        'rls_demo.documents',
        'SELECT'
    ) AS alpha_can_select,
    has_table_privilege(
        'rls_demo_alpha',
        'rls_demo.documents',
        'UPDATE'
    ) AS alpha_can_update;
```

Both returning `TRUE` indicates only object privileges—**not that alpha can see every row**, because row policies still filter.

### 18.4. psql \d and Version Differences

In `psql`, `\d` or `\d+ schema.table` displays RLS/policy details depending on version. Those are **`psql` meta-commands**, not SQL to run via JDBC; `pg_policies` and `pg_class` are much better suited for monitoring scripts.

## 19. Do INSERT, UPDATE, and DELETE Need a SELECT Policy?

In practice, **write operations** and **reading referenced data** interact. An `UPDATE` often needs `SELECT` permissions and policies for columns/rows referenced in `WHERE`, `SET`, or `RETURNING`.

Example:

```sql
UPDATE rls_demo.documents
SET amount = amount + 5
WHERE document_id = 1
RETURNING document_id, amount;
```

To compute `amount + 5`, evaluate `WHERE`, and return `RETURNING`, the role needs the corresponding read rights. Our lab granted `SELECT` and added a `FOR SELECT` policy so `UPDATE ... RETURNING` behaves predictably.

### 19.1. Why Can a Valid UPDATE Policy Still Fall Short?

If an operator creates only `FOR UPDATE` without a matching read policy, `UPDATE` variants needing `SELECT` can fail to behave as expected—resulting in skipped rows or privilege/RLS errors depending on the query and permissions.

### 19.2. FOR UPDATE Row Locks

`SELECT ... FOR UPDATE` is not plain read-only `SELECT` because it acquires row locks and involves write-targeting rules; applicable policies can differ from plain `SELECT`. Never assume every `SELECT ... FOR UPDATE` succeeds just because `SELECT` works if `UPDATE` policies/grants are missing.

### 19.3. RETURNING Changes Read Requirements

DML with `RETURNING` must read and return those columns, triggering `SELECT` privilege and row-security checks. Include `INSERT/UPDATE/DELETE ... RETURNING` in your test matrix rather than testing non-`RETURNING` forms alone.

### 19.4. Do Not Omit SELECT to "Hide" Data While Allowing Arbitrary WHERE

If an API allows updating by ID without reading row contents, design explicit updatable columns, fixed SQL statements, and narrow grants/policies—never rely on broad `GRANT UPDATE` paired with arbitrary user SQL.

## 20. Multi-Tenant Pattern Using Session Configuration Variables

In a SaaS with thousands of tenants, creating a separate database login per tenant may be impractical. A common application architecture:

- The app uses a single database role `app_runtime` that owns no tables and has no `BYPASSRLS`.
- A trusted backend authenticates the user/tenant.
- The backend sets a tenant context for the transaction.
- RLS policies read that tenant context.

**Design example** (not directly runnable because these objects are hypothetical):

```sql
CREATE POLICY orders_by_tenant ON app.orders
FOR ALL
TO app_runtime
USING (
    tenant_id = nullif(
        current_setting('app.tenant_id', true),
        ''
    )::bigint
)
WITH CHECK (
    tenant_id = nullif(
        current_setting('app.tenant_id', true),
        ''
    )::bigint
);
```

### 20.1. current_setting and missing_ok

`current_setting('app.tenant_id', true)` reads a session/transaction setting and returns SQL `NULL` if unset (`missing_ok = true`). Because some resets leave an empty string, `nullif(..., '')` converts `''` to SQL `NULL` before casting to `bigint`.

When the tenant context evaluates to SQL `NULL`, `tenant_id = NULL` evaluates to `UNKNOWN`, not `TRUE`, so the policy denies all rows.

If the setting holds a non-numeric string, however, `::bigint` raises an error. Always validate and set context within a trusted code path.

### 20.2. Setting Context per Transaction

```sql
BEGIN;

SET LOCAL app.tenant_id = '42';

-- SQL statements here run as app_runtime,
-- filtered by app.orders policy for tenant_id = 42.

COMMIT;
```

`SET LOCAL` applies strictly within the current transaction, avoiding context bleed across requests in connection pools. In JDBC/frameworks, ensure an explicit transaction wraps both `SET LOCAL` and all protected queries.

### 20.3. Critical Warning: Custom GUCs Do Not Authenticate Tenants on Their Own

**A custom session variable is not a security boundary independent of the SQL role.** If an attacker can run arbitrary SQL under the same `app_runtime` role, they can run `SET app.tenant_id` to impersonate another tenant.

Therefore, `current_setting`-based designs require:

- A trusted application server authenticating the tenant and setting the value.
- No direct database access letting untrusted clients arbitrarily `SET` custom GUCs and run freeform SQL.
- Parameterized queries preventing SQL injection, never trusting client-supplied tenant context directly.
- Minimal DB privileges and auditing of `SECURITY DEFINER` paths.
- Honest threat modeling: if you need DB-level isolation between untrusted SQL users, custom GUCs alone are insufficient.

Never label this pattern "the database is completely isolated even if an attacker controls the app role."

### 20.4. How Connection Pooling Leaks Context Bugs

```text
Request A (tenant 42) -----> Connection #7
    SET app.tenant_id = 42
    SELECT ...
    return connection to pool

Request B (tenant 99) -----> Connection #7
    if context is not reset:
    SELECT ... may still use tenant 42
```

Prefer transaction-scoped `SET LOCAL` when the app controls transaction boundaries, ensuring no query runs outside a transaction using stale state. With session-level `SET`, enforce reliable pool resets.

### 20.5. Transaction Pooling

With PgBouncer transaction pooling or similar modes, session-level settings cannot be assumed to persist across transactions for one request. Set context within every transaction matching the pooler contract, and test against the real pooler configuration.

### 20.6. current_user and Tenant Context Are Two Different Models

Our main lab relies on `tenant_role = current_user::text`, which is clear when each tenant has a distinct DB role. The GUC model relies on a backend-supplied tenant ID inside one shared role. Each has trade-offs in trust, scale, role management, and pooling; never mix the two without clarifying who is trusted to set tenant identity.

## 21. SECURITY DEFINER: An Easy-to-Miss Bypass Path

PostgreSQL functions marked `SECURITY DEFINER` execute with **the privileges of the function's owner**, not merely the caller's. If the function owner is also the table owner bypassing RLS, the function can return more rows than the caller can `SELECT` directly.

### 21.1. Example Demonstrating the Difference

Run in the lab only if you want to observe the risk; wrapped in a transaction to roll back the temporary function:

```sql
BEGIN;

CREATE FUNCTION rls_demo.count_all_documents()
RETURNS bigint
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, rls_demo, pg_temp
AS $$
    SELECT COUNT(*) FROM rls_demo.documents;
$$;

REVOKE ALL
ON FUNCTION rls_demo.count_all_documents()
FROM PUBLIC;

GRANT EXECUTE
ON FUNCTION rls_demo.count_all_documents()
TO rls_demo_alpha;

SET LOCAL ROLE rls_demo_alpha;

SELECT COUNT(*) AS own_visible_count
FROM rls_demo.documents;

SELECT rls_demo.count_all_documents()
    AS definer_function_count;

ROLLBACK;
```

If the function is owned by a **superuser/owner with bypass** and the lab has all six rows intact:

- `own_visible_count` = **3**.
- `definer_function_count` can be **6** because the function executes under a definer context that bypasses policies.

This intentionally demonstrates the risk—**not a pattern to deploy in production**.

### 21.2. FORCE and Definer

`FORCE ROW LEVEL SECURITY` subjects **ordinary table owners** to RLS, yet superusers and `BYPASSRLS` remain exempt. Never enable `FORCE` and assume every `SECURITY DEFINER` function is automatically safe.

### 21.3. Locking search_path

`SECURITY DEFINER` functions must be hardened against object-name resolution / `search_path` attacks. Best practices include schema-qualifying objects and pinning an explicit `search_path` with `pg_temp` placed safely. Never allow name resolution to fall back to schemas where untrusted users can create objects.

### 21.4. Function EXECUTE Privileges

PostgreSQL's defaults may grant `EXECUTE` on new functions to `PUBLIC` unless default privileges are hardened. For sensitive functions, `REVOKE ALL FROM PUBLIC` and grant only specific roles—ideally in the same transaction that creates the function to avoid a window of broad exposure.

### 21.5. When SECURITY DEFINER Makes Sense

Controlled administrative functions may intentionally perform cross-tenant work (aggregate reports, migrations, maintenance). Always audit:

- Which callers hold `EXECUTE`.
- What data the function returns and whether it filters scope internally.
- What bypass rights the function owner holds.
- Safety of `search_path` and input validation.
- Logging/auditing and negative test cases.

Never use `SECURITY DEFINER` merely to "fix" an RLS error without evaluating trust boundaries.

## 22. Views Can Evaluate RLS Under Different Privileges

In PostgreSQL, traditional views check underlying relation permissions using the **view owner's** context (certain details vary by config and major version). If the view owner bypasses RLS, callers running `SELECT` on the view can receive rows they could not `SELECT` directly from the table.

### 22.1. Risk of Views Created by Owners/Bypass Roles

```sql
-- Illustrative pattern requiring privilege review:
-- CREATE VIEW rls_demo.all_documents_v AS
-- SELECT * FROM rls_demo.documents;
-- GRANT SELECT ON rls_demo.all_documents_v TO rls_demo_alpha;
```

If the view runs under the owner's context and the owner bypasses policies, querying the view exposes cross-tenant rows. Never treat "the underlying table has RLS" as proof that every view over it is automatically safe.

### 22.2. security_invoker Views (PostgreSQL 15+)

Starting in PostgreSQL 15, views support `security_invoker = true` so permissions and RLS on underlying relations are checked as the caller under documented semantics.

Lab example:

```sql
CREATE VIEW rls_demo.documents_invoker_v
WITH (security_invoker = true)
AS
SELECT
    document_id, tenant_role, title, state, amount
FROM rls_demo.documents;

GRANT SELECT
ON rls_demo.documents_invoker_v
TO rls_demo_alpha, rls_demo_beta;
```

Test:

```sql
SET ROLE rls_demo_alpha;

SELECT document_id, tenant_role, title
FROM rls_demo.documents_invoker_v
ORDER BY document_id;

RESET ROLE;
```

On PostgreSQL 15+ with lab privileges, alpha sees only IDs **1, 2, and 5** because the view uses the caller's context. Callers still need required privileges on underlying tables under security-invoker rules; the lab already granted them.

### 22.3. security_barrier Is Not security_invoker

`security_barrier` controls optimization/evaluation order of filter expressions to prevent leaks via unsafe user functions. It **does not mean** "the view runs with the caller's privileges" and does not replace `security_invoker = true`.

### 22.4. Watch PostgreSQL Major Versions

View `security_invoker` syntax is unsupported in older PostgreSQL versions. Check:

```sql
SHOW server_version;
```

On unsupported servers, choose alternative view/function/role designs and verify RLS enforcement rather than copying SQL blindly.

## 23. Commands and Mechanisms Not Protected Like Ordinary SELECT

RLS filters rows for `SELECT`, `INSERT`, `UPDATE`, and `DELETE` within supported bounds. It is **not enforced across every table operation**.

### 23.1. TRUNCATE Does Not Filter by Policy

`TRUNCATE` does not delete "only rows visible via RLS." It is a relation-level operation; PostgreSQL does not apply row security like `DELETE`.

Grant `TRUNCATE` strictly to authorized administrative roles—never use `TRUNCATE` as a shortcut to delete one tenant's records.

### 23.2. REFERENCES and Foreign Keys

Referential integrity (FK), uniqueness, and certain constraint checks are **not filtered by RLS** the way user `SELECT`s are, in order to preserve data integrity. That creates potential indirect information leaks via error messages or behavior differences.

### 23.3. COPY TO and COPY FROM

`COPY TO` can export `SELECT` results respecting privileges and row security. `COPY FROM` on RLS-enabled tables has specific restrictions and should not be assumed equivalent to policy-checked bulk `INSERT` in all cases.

When loading data as an app role subject to RLS, prefer tested `INSERT` paths; for batch/`COPY`, verify exact major-version documentation and permissions.

### 23.4. DDL and Ownership Rights

Roles permitted to alter tables or policies can modify RLS rules. Cross-tenant boundaries typically require that applications **do not own** tables and hold no dangerous DDL rights.

### 23.5. Unintended Special GRANTs

Never casually grant `TRUNCATE`, `REFERENCES`, `BYPASSRLS`, or broad role memberships just because `SELECT`/`UPDATE` policies look solid.

## 24. Information Leaks via UNIQUE and FOREIGN KEY Constraints

Suppose a table is defined as:

```sql
CREATE TABLE app.users (
    user_id bigint PRIMARY KEY,
    tenant_id bigint NOT NULL,
    email text NOT NULL UNIQUE
);
```

RLS shows tenant 42 only tenant 42's rows. Yet if tenant 99 already registered `a@example.com`, an `INSERT` by tenant 42 with that email raises `duplicate key` because the `UNIQUE` constraint checks across the underlying dataset, not just rows visible to tenant 42.

### 24.1. This Is a Side Channel

The error message reveals "that email exists in another tenant," even though RLS blocks `SELECT` on that row. Constraints must still enforce uniqueness per their definition.

### 24.2. Per-Tenant Unique Keys When Business Allows

If email only needs to be unique **within a tenant**:

```sql
CREATE TABLE app.users (
    user_id bigint PRIMARY KEY,
    tenant_id bigint NOT NULL,
    email text NOT NULL,
    UNIQUE (tenant_id, email)
);
```

Two tenants can then use the same email without conflict. If business requires globally unique emails, never weaken it to per-tenant uniqueness just to dodge errors; instead standardize error messages, registration flows, and leakage risk.

### 24.3. Foreign Keys Can Also Be a Side Channel

An `INSERT` referencing `parent_id` can succeed or fail depending on whether that parent row exists, even when RLS hides the parent from the caller. Design unpredictable IDs, authorization checks, and careful error handling.

### 24.4. RLS Cannot Stop Every Observation Channel

Execution timing, lock contention, constraint errors, trigger/exception details, and object privileges can still leak signals outside `SELECT` row results. RLS is valuable, yet never replaces full-system threat modeling.

## 25. Policies Referencing Other Tables and Supporting Privileges

A policy can check membership relationships:

```sql
CREATE POLICY projects_read ON app.projects
FOR SELECT
USING (
    EXISTS (
        SELECT 1
        FROM app.project_members AS m
        WHERE m.project_id = projects.project_id
          AND m.user_id = app.current_user_id()
    )
);
```

This SQL is a conceptual template; `app.projects`, `app.project_members`, and `app.current_user_id()` are not created in the lab.

### 25.1. Privileges on Referenced Tables

Policies execute within the query's privilege context. If the policy expression reads `app.project_members` and the role lacks `SELECT` on it, queries can **fail with permission denied** even though `app.projects` granted `SELECT`.

Solve this with least-privilege access on the helper table or a carefully reviewed security helper function—not by granting `SELECT` on sensitive membership tables to everyone.

### 25.2. Policy Dependency Cycles Can Occur

If table A's policy reads B and B's policy reads A, or a policy queries the same protected table recursively, PostgreSQL can raise policy-recursion or excessive-complexity errors. Structure identity/membership schemas so permission checks evaluate finitely and safely.

### 25.3. Subquery Policies and Race Conditions

When a policy reads a permission-state table modified concurrently with target rows, consider snapshot visibility and consistency. Membership state read at a snapshot might lag concurrent modifications. Depending on security requirements, use appropriate locking, synchronous updates, or consistent authorization table designs.

### 25.4. JOIN Cost Inside Policies

An `EXISTS(...)` inside a policy can become expensive across millions of rows. Create matching indexes on `(project_id, user_id)`, inspect `EXPLAIN`, and avoid heavy UDFs inside policies. Never trade away security by dropping the policy for speed.

## 26. Expression Evaluation Order, Triggers, and SQL NULL

Policies are not simple application `IF` statements; PostgreSQL integrates them into query execution semantics.

### 26.1. USING During Row Reads

`USING` is a SQL predicate evaluated on candidate rows. PostgreSQL enforces security rules around evaluation order between policies and user expressions, where operators/functions marked **`LEAKPROOF`** have special plan-pushdown eligibility.

Never build a security model assuming Java-style short-circuiting like `if (a) { b }`. A policy is safe only if its own predicate admits the exact valid row set—never because you assume an application `WHERE` runs before or after it.

### 26.2. SQL NULL Is Not TRUE

Suppose:

```sql
USING (tenant_role = current_user::text)
```

and `tenant_role` is SQL `NULL`; the comparison yields `UNKNOWN`. A policy admits a row only when the condition evaluates to `TRUE`. In our lab, `tenant_role` is `NOT NULL` to avoid ambiguity.

### 26.3. BEFORE ROW Triggers and WITH CHECK

For `INSERT`/`UPDATE`, PostgreSQL evaluates `WITH CHECK` against the proposed row after applicable `BEFORE ROW` triggers have run. Thus triggers can alter values checked by policies.

For example, a `BEFORE INSERT` trigger might populate `tenant_role` when omitted, after which the resulting row must still pass `WITH CHECK`. Conversely, a buggy trigger could overwrite `tenant_role` and fail the policy.

**Never assume triggers can bypass policies**, and never populate tenant identity from untrusted input when it can come from a verified role/context.

### 26.4. AFTER Triggers and Side Effects

An `AFTER` trigger invoking a high-privilege function can run additional SQL. Audit trigger functions, owners, and target tables separately; RLS on the initial table does not automatically guard every downstream trigger side effect.

### 26.5. RLS Does Not Validate Business Rules on Its Own

`WITH CHECK (tenant_role = current_user)` does not check:

- Whether `amount` is within business limits.
- Whether `state` followed a valid `draft -> published` workflow.
- Whether `title` contains unsafe content.
- Whether the user is allowed to edit the `amount` column.

Use `CHECK` constraints, FKs, column grants, business validation, triggers, or application policies as needed.

## 27. Restricting State Transitions in UPDATE with USING and WITH CHECK

Suppose users may edit only `draft` documents and may only leave them as `draft` or move them to `review`.

### 27.1. Specialized Policy

```sql
CREATE POLICY drafts_editor_update
ON app.documents
FOR UPDATE
TO app_editor
USING (
    tenant_id = app.current_tenant_id()
    AND state = 'draft'
)
WITH CHECK (
    tenant_id = app.current_tenant_id()
    AND state IN ('draft','review')
);
```

Hypothetical example—do not run in the lab because `app.documents` and `app_editor` do not exist.

### 27.2. Allowed State Transition

Old row is `draft` in the right tenant -> `USING` is `TRUE`. New row is `review` in the right tenant -> `WITH CHECK` is `TRUE`. `UPDATE` succeeds under this policy if other grants and policies allow it.

### 27.3. Editing a Review Row Again Is Denied

Once a row is `review`, `USING` is `FALSE`, so this policy refuses it as an `UPDATE` target. That restricts state flow using **old row vs. new row**.

### 27.4. When Another Permissive Policy Exists

If someone adds a permissive `FOR UPDATE ... USING(true) WITH CHECK(true)` policy covering the same role, ORing them widens both old and new conditions. To enforce an invariant across every update path for a role, use a restrictive policy or tightly separated policies.

### 27.5. RLS Does Not Replace Complex State Machines

Rules like "only a signed-off reviewer may move `review -> approved`" or "never edit locked invoices" require explicit permission models, states, and transactions. Use RLS as one defense layer rather than stuffing an entire workflow into an untestable expression.

## 28. ON CONFLICT and MERGE on RLS Tables

Multi-branch DML commands must be audited across **every branch that can execute**.

### 28.1. INSERT ... ON CONFLICT DO UPDATE

```sql
INSERT INTO app.documents AS d (
    document_id, tenant_id, title
)
VALUES (123, app.current_tenant_id(), 'New title')
ON CONFLICT (document_id)
DO UPDATE SET title = EXCLUDED.title;
```

This statement can take either the `INSERT` or `UPDATE` path depending on existing rows. Audit the `INSERT` `WITH CHECK` policy and the `UPDATE` `USING`/`WITH CHECK` policies (plus read permissions)—not `INSERT` alone.

### 28.2. Conflict with Another Tenant's Row

If the primary key is global and `document_id = 123` belongs to another tenant, a `UNIQUE` conflict still occurs even though that row is hidden from the current tenant's `SELECT`. Never let `ON CONFLICT` probe foreign IDs or update another tenant's rows.

### 28.3. DO NOTHING Does Not Eliminate Side Channels

If a user tries inserting a key colliding with a hidden row, `ON CONFLICT DO NOTHING` produces a different affected-row count than a non-colliding key; constraint behavior can leak existence. Align keys, error handling, and APIs with your threat model.

### 28.4. MERGE

Supported since PostgreSQL 15, `MERGE` combines matched and not-matched branches. When running it on RLS-enabled tables, verify policies and permissions for every action branch per your major version's documentation. Never assume a `SELECT` policy covers all `UPDATE`/`INSERT`/`DELETE` branches, or that `MERGE` shares identical concurrency semantics with `ON CONFLICT`.

### 28.5. Never Write Overly Broad SQL in Place of Authorization

An UPSERT can overwrite fields the client should not touch if the app blindly assigns `EXCLUDED.column`. Row-level security restricts rows, whereas column privileges and validation must still guard fields.

## 29. Indexing for Tenant-Scoped Policies

RLS effectively adds a tenant predicate to queries. On large tables, matching indexes cut filtering cost:

```sql
CREATE INDEX idx_rls_demo_tenant_state
ON rls_demo.documents (tenant_role, state);
```

### 29.1. When Does an Index Help?

With millions of rows across thousands of tenants, a query:

```sql
SELECT document_id, title
FROM rls_demo.documents
WHERE state = 'published';
```

executed under an RLS-constrained role includes the tenant policy predicate, so an index prefixed with `(tenant_role, state)` can help depending on statistics and selectivity.

### 29.2. Small Labs Often Pick Seq Scan

With six rows, the planner naturally picks a Sequential Scan. That does not mean RLS is broken or the index won't be used at scale.

### 29.3. Running EXPLAIN Under the Real Role

```sql
SET ROLE rls_demo_alpha;

EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title
FROM rls_demo.documents
WHERE state = 'published';

RESET ROLE;
```

The plan reflects tenant filtering, though the planner may restructure predicates and access paths rather than printing the literal policy SQL verbatim.

Remember `EXPLAIN (ANALYZE)` executes the `SELECT`; if production data is sensitive, avoid publishing plans or query texts containing expressions, object names, or parameter literals.

### 29.4. Functions Inside Policies Can Be Expensive

If a policy runs a complex function per row or queries an unindexed membership table, latency can spike. Never falsely mark a function reading session state or permission tables as `IMMUTABLE` just to cache results—that causes stale security decisions.

### 29.5. Optimization Must Never Weaken Isolation

Optimize via indexes, query design, accurate `STABLE`/`VOLATILE` markers, and clean authorization tables. Never change `tenant_id = current_tenant` to `true` just to make queries faster.

## 30. RLS and Partitioning

On tables partitioned by tenant or date, evaluate policies according to whether users **query the parent or child partitions**.

### 30.1. Querying Through the Partitioned Parent

When querying the parent partitioned table, the parent's row-security policies apply per parent-access semantics. The planner can prune partitions when conditions allow.

### 30.2. Direct Access to Child Partitions

If a role holds direct privileges on **a child partition** as a standalone table, inspect policies on that access path too; never assume parent policies automatically govern direct `SELECT`s on child partitions across every version and configuration.

### 30.3. Operational Recommendation

Applications should normally access through the designed parent/API, withhold direct grants on child partitions unless needed, and run negative tests against both the parent and any accessible child partitions.

### 30.4. Partitioning Does Not Replace RLS

Partition pruning is a query optimization and routing mechanism; it does not authenticate tenants. Partitioning by tenant while letting an app role `SELECT` all partitions directly still leaks data without proper grants and RLS.

## 31. RLS, Administrative Roles, and Background Jobs

Real systems run multiple workload types:

| Role | Typical scope |
| --- | --- |
| Application tenant role | DML strictly on permitted tenant rows. |
| Report reader | Read-only access to required reporting columns/rows. |
| Migration owner | Runs DDL; isolated from APIs. |
| Maintenance job | Vacuum/refresh/cleanup with appropriate admin privileges. |
| Cross-tenant analytics | Intentional system-wide access with dedicated logging and controls. |

### 31.1. Cross-Tenant Reporting Is a Separate Requirement

Never grant `BYPASSRLS` to user-facing apps just because analytics needs system-wide totals. Use a controlled reporting role/job exporting approved aggregates, or a tightly scoped dedicated interface.

### 31.2. Multi-Tenant State-Changing Jobs

A job that "closes all overdue orders" running under a tenant-limited role touches only rows visible to that role. When cross-tenant scope is genuinely intended, run it via an authorized operational path—never silently switch to superuser without auditing.

### 31.3. Object Ownership and Migrations

When creating new tables/views, migrations must verify:

- Is RLS enabled on the new table?
- Do default grants expose overly broad access?
- Are policies created before the app serves traffic?
- Who owns the views and functions?
- Does the owner bypass by default or require `FORCE`?

A single new tenant table missing `ENABLE ROW LEVEL SECURITY` opens a gap even when older tables are locked down.

## 32. Guide to Role-Based RLS Testing

Security testing requires both **positive tests** (allowed) and **negative tests** (denied / 0 rows).

### 32.1. Testing SELECT

- Alpha `SELECT` without `WHERE` -> only IDs 1, 2, 5.
- Beta `SELECT` without `WHERE` -> only IDs 3, 4, 6.
- Alpha `SELECT` ID 4 -> 0 rows.
- Beta `SELECT` ID 1 -> 0 rows.
- `COUNT`/`SUM` under each role sees only its own set.

### 32.2. Testing INSERT

- Alpha `INSERT` alpha row -> succeeds.
- Alpha `INSERT` beta row -> `WITH CHECK` error.
- Alpha `INSERT` `tenant_role` SQL `NULL` -> rejected by `NOT NULL`.
- `INSERT` invalid `state`/`amount` -> rejected by `CHECK` constraints.
- `INSERT ... RETURNING` and `INSERT ... ON CONFLICT` -> test both read and write paths.

### 32.3. Testing UPDATE

- Alpha updates title on ID 1 -> succeeds.
- Alpha updates ID 4 -> `UPDATE 0 rows`.
- Alpha changes `tenant_role` on ID 1 to beta -> `WITH CHECK` error.
- Alpha sets a valid `state` per constraint yet disallowed by a state policy -> blocked by policy.
- `UPDATE ... RETURNING` -> verify matching `SELECT` permissions/policies.

### 32.4. Testing DELETE

- Alpha deletes ID 5 -> succeeds.
- Alpha deletes ID 6 -> `DELETE 0 rows`.
- Retention/soft-delete rules (if any) verified independently.

### 32.5. Testing Bypass and Indirect Paths

- Test ordinary owner before/after `FORCE`.
- Test `BYPASSRLS` role only in a controlled admin lab.
- Test `SELECT` through default views vs. `security_invoker` views.
- Test whether `SECURITY DEFINER` functions leak cross-tenant data.
- Test direct child partition access if granted.
- Test custom tenant GUCs across pooled requests.

### 32.6. Test Using Production-Like Privileges

A test suite running solely as superuser or an unforced table owner risks **false green passes** because policies are bypassed. Run tests as the actual app role (or an identically privileged test role), including membership checks.

## 33. Troubleshooting Common RLS Issues

### 33.1. SELECT Always Returns 0 Rows

Possible causes:

- `ENABLE ROW LEVEL SECURITY` is active with no permissive policy for the role/command.
- Policy `TO role` excludes the current role.
- `USING` evaluates to `FALSE`/`UNKNOWN`, e.g., tenant context unset.
- `current_user` differs from expected due to `SET ROLE` or `SECURITY DEFINER`.
- A `RESTRICTIVE` policy filters out every row.
- The query's own `WHERE` excludes rows.

Fix: check `current_user`/`session_user`, `pg_policies`, tenant config, and test as the exact role—never disable RLS just to make rows appear.

### 33.2. Permission Denied

The role may lack:

- Schema `USAGE`.
- Table/column `SELECT`/`INSERT`/`UPDATE`/`DELETE`.
- `SELECT` on helper tables referenced by the policy.
- `EXECUTE` on functions invoked by the policy.

Policies do not replace `GRANT`s—verify object permissions first.

### 33.3. new row violates row-level security policy

Typically occurs when `INSERT`/`UPDATE` produces a row failing `WITH CHECK`. Inspect:

- Does the new row's tenant match the verified role/context?
- Did a `BEFORE` trigger alter `tenant`/`state`?
- Did an extra restrictive policy add a condition?
- Did an unexpected `FOR ALL`/`INSERT`/`UPDATE` policy apply?

Never drop `WITH CHECK` to let bad data through if that check enforces a security invariant.

### 33.4. UPDATE 0 Rows Even Though the ID Exists

Likely `USING` disqualified the existing row as a target. Verify via an authorized admin role and safe audit logs; avoid exposing cross-tenant row existence to callers.

### 33.5. Policy Protects the Table, Yet a View Leaks Rows

Inspect the view's owner and security context. On PostgreSQL 15+, evaluate `security_invoker = true`; on older versions, adjust view/role design. Test every view granted to app roles.

### 33.6. Queries Error After Adding an EXISTS Policy

The policy may query a membership table or function the caller lacks privileges on, or trigger policy recursion. Audit dependency rights, add indexes, and eliminate reference cycles.

### 33.7. Backups Miss Rows

The backup role may be subject to RLS, exporting a filtered subset. Define dedicated backup roles and clear governance, catch filtering via config/processes, and test restores—never treat `row_security = off` as a bypass privilege.

### 33.8. Intermittent Bugs Under Connection Pools

Custom tenant GUCs leaked between requests, `SET LOCAL` ran outside an explicit transaction, or queries split across connections. Enforce transaction-bound context and run integration tests against a real pool.

### 33.9. CREATE POLICY Added, Yet All Rows Still Leak

RLS may not be enabled on the table, the role may be table owner/superuser/`BYPASSRLS`, or another permissive policy with `USING(true)` widened access via OR.

### 33.10. RLS Slow After Deployment

Policies may add unindexed predicates, expensive functions, or membership subqueries lacking stats. Run `EXPLAIN (ANALYZE)` under the real role and tune without disabling isolation.

## 34. Policy Design Decision Table

| Security question | Tool to consider | Common pitfall |
| --- | --- | --- |
| Can the role `SELECT` the table? | `GRANT SELECT`. | RLS never grants permissions. |
| Which rows can the role `SELECT`? | `FOR SELECT ... USING`. | `SELECT` policy does not restrict `INSERT` by default. |
| Which rows can the role `INSERT`? | `FOR INSERT ... WITH CHECK`. | Failed `INSERT` errors loudly rather than skipping silently. |
| Which old rows can the role `UPDATE`? | `FOR UPDATE ... USING`. | Other tenants' rows normally yield `UPDATE 0 rows`. |
| What values can post-`UPDATE` rows hold? | `FOR UPDATE ... WITH CHECK`. | Checking only old rows fails to constrain writes. |
| Which rows can the role `DELETE`? | `FOR DELETE ... USING`. | `DELETE` has no `WITH CHECK`. |
| Need extra constraints across all matching policies? | `AS RESTRICTIVE`. | Restrictive grants nothing without a permissive policy. |
| Two independent read-access paths? | Multiple `PERMISSIVE` policies. | OR can leak across tenants. |
| Must the owner obey RLS? | `FORCE ROW LEVEL SECURITY`. | Does not constrain superusers/`BYPASSRLS`. |
| View reads using caller privileges? | `security_invoker=true` (PG15+). | Default views may run in owner context. |
| Function exceeds caller privileges? | `SECURITY DEFINER`/owner/`EXECUTE`. | Definer may bypass RLS. |
| App uses one DB role for many tenants? | Trusted tenant context + policy. | Custom GUCs can be spoofed if users run arbitrary SQL. |
| Policy queries helper table for membership? | Controlled `EXISTS`/function. | Privileges, recursion, races, and performance. |
| Partitioned tables? | Policies across parent/child paths. | Direct child grants open separate paths. |
| Prevent `TRUNCATE`? | Do not grant `TRUNCATE`. | RLS does not filter `TRUNCATE` row-by-row. |
| Prevent duplicate-key leaks? | Constraint/schema/API error design. | `UNIQUE`/FK checks act as side channels. |
| Confirm policies are active? | `pg_policies` + `pg_class` + role tests. | Policies on an RLS-disabled table do nothing. |

### 34.1. Implement "Deny by Default" as a Rule

For every table storing tenant data:

1. Narrow object privileges first.
2. Enable RLS.
3. Author policies per genuinely required command.
4. Test with the least-privileged role.
5. Cover views, functions, background jobs, and constraints.

Never grant full read access and rely solely on application `WHERE` clauses. RLS is most valuable as an independent defense-in-depth layer.

## 35. Hands-On Exercises

Exercises use `rls_demo.documents` created with six rows, four policies, and two roles. Statements expected to error should run separately with `ROLLBACK` after errors in transactions. Exercises requiring role switches use an account permitted to `SET ROLE` in the practice database. Never run privilege-escalation commands or `DISABLE RLS` in production.

### Exercise 1. Two Privilege Layers

Explain why `GRANT SELECT ON rls_demo.documents TO rls_demo_alpha` does not guarantee alpha reads only its own data, and why `CREATE POLICY` alone is insufficient if `GRANT` is forgotten.

### Exercise 2. Default Deny

After `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` with no policies yet, how many rows does alpha (non-bypass) with `GRANT SELECT` see? How many can the ordinary owner see?

### Exercise 3. SELECT Policy

Write a policy allowing both alpha and beta to `SELECT` only rows where `tenant_role = current_user::text`.

### Exercise 4. Alpha's SELECT Output

Across the original six rows, which `document_id`s does alpha see? What is the sum of `amount`?

### Exercise 5. SELECT an Out-of-Tenant ID

Alpha runs `SELECT ... WHERE document_id = 4`. Expect permission denied or 0 rows? Explain.

### Exercise 6. INSERT Policy

Write a policy letting alpha/beta `INSERT` only rows whose `tenant_role` matches `current_user`.

### Exercise 7. Wrong-Tenant INSERT

Alpha tries to `INSERT` `(12, 'rls_demo_beta', 'x', 'draft', 10)`. Which row does the policy check, and does it allow it?

### Exercise 8. UPDATE USING

Write an `UPDATE` policy letting each tenant edit existing rows whose `tenant_role` matches the role.

### Exercise 9. UPDATE WITH CHECK

Alpha updates ID 1 setting `tenant_role = 'rls_demo_beta'`. With `USING` and `WITH CHECK` sharing the tenant check, explain each phase and the outcome.

### Exercise 10. Out-of-Tenant Row in UPDATE

Alpha runs `UPDATE ... SET title = 'bad' WHERE document_id = 4`. How many rows are normally affected?

### Exercise 11. DELETE Policy

Write a `FOR DELETE` policy letting alpha and beta delete only their own tenant's rows.

### Exercise 12. No WITH CHECK for DELETE

Why does `FOR DELETE` have no `WITH CHECK`? When is a row excluded from `DELETE`?

### Exercise 13. FOR ALL

Write a `FOR ALL` policy for `app_user` on hypothetical table `app.documents` using `tenant_id = app.current_tenant_id()` for both existing-row checks and new-row checks.

### Exercise 14. WITH CHECK Fallback

If a `FOR UPDATE` policy specifies `USING` without `WITH CHECK`, is it true the role can freely change `tenant_id` to any value?

### Exercise 15. PERMISSIVE and OR

Two permissive `SELECT` policies for the same role:

```sql
USING (tenant_id = 42)
USING (state = 'published')
```

What is the effective expression? Could it leak other tenants' rows?

### Exercise 16. RESTRICTIVE and AND

With permissive `USING (tenant_role = current_user::text)` and restrictive `USING (state <> 'archived')`, which IDs does alpha see in the lab?

### Exercise 17. Only a Restrictive Policy

A role has `SELECT` grant and RLS is enabled, yet only one restrictive policy `USING (true)` exists with no permissive policy. Can the role see all rows?

### Exercise 18. FORCE OWNER

What does `FORCE ROW LEVEL SECURITY` change for an ordinary owner? Does it constrain superusers or `BYPASSRLS` roles?

### Exercise 19. row_security off

An app role without `BYPASSRLS` runs `SET row_security = off` and `SELECT`. Does it see all rows?

### Exercise 20. pg_policies

Write a query listing policy name, command, permissive, roles, `USING`, and `WITH CHECK` for `rls_demo.documents`.

### Exercise 21. Is RLS Truly Enabled?

Write a query checking `relrowsecurity` and `relforcerowsecurity` for the lab table.

### Exercise 22. Object Privileges

Write a query checking whether alpha has `SELECT` and `UPDATE` privileges on the lab table. Does that tell you alpha sees every row?

### Exercise 23. current_user vs. session_user

In an admin session after `SET ROLE rls_demo_alpha`, are `current_user` and `session_user` necessarily equal? Which one does the lab policy use?

### Exercise 24. Custom Tenant GUC

State the conditions for a policy using `current_setting('app.tenant_id', true)` to be safe under a trusted backend. Why is it not a security boundary if clients can execute arbitrary SQL under that app role?

### Exercise 25. SET LOCAL and Pools

In a shared-role + pool design, why is `SET LOCAL app.tenant_id` inside each transaction often safer than session-level `SET`?

### Exercise 26. SECURITY DEFINER

A `SECURITY DEFINER` function owned by an RLS-bypassing owner returns `SELECT COUNT(*) FROM documents`. Could alpha receive `6` even though direct `SELECT` sees only `3`? What must be controlled?

### Exercise 27. security_invoker Views

Starting in which PostgreSQL major version is `security_invoker = true` supported on views? How does it differ from default views and `security_barrier`?

### Exercise 28. TRUNCATE

If an app role holds `TRUNCATE` on an RLS-enabled table, does `TRUNCATE` delete only the role's rows per `USING`? What should you do?

### Exercise 29. UNIQUE Side Channel

Why can a table-wide `UNIQUE(email)` reveal that an email exists in another tenant even when RLS blocks `SELECT`? If business requires uniqueness only per tenant, which constraint fits?

### Exercise 30. FK Side Channel

An `INSERT` references a parent row ID hidden by RLS. Why can the FK check outcome still reveal whether that parent exists?

### Exercise 31. Policy Subqueries

What privilege, performance, and concurrency issues can arise with `USING (EXISTS (SELECT 1 FROM app.membership ...))`?

### Exercise 32. Connection Pool Bug

A request for tenant 42 uses connection #7 and returns it to the pool without resetting session GUCs. What can happen to tenant 99's request receiving connection #7? Give two mitigations.

### Exercise 33. SELECT and UPDATE RETURNING

A role holds `UPDATE` grant/policy without matching `SELECT` permission/policy. Why might `UPDATE ... RETURNING title` fail to work as expected?

### Exercise 34. State-Transition Policy

Write `USING` and `WITH CHECK` conditions so editors can modify only current-tenant documents whose old state is `draft`, and whose new state is only `draft` or `review`.

### Exercise 35. Index Optimization

On a 20M-row `documents` table with policy `tenant_role = current_user::text`, the app often runs `SELECT ... WHERE state = 'published'`. Suggest an index and performance verification steps.

### Exercise 36. RLS and View Owners

Why can an RLS-protected table still leak data through a view if the view executes under an owner who bypasses RLS? List design steps to reduce risk.

### Exercise 37. Negative Tests

Propose at least eight negative tests for tenant alpha to catch `SELECT`/`INSERT`/`UPDATE`/`DELETE` bugs, view/function bypasses, and pool context leaks.

### Exercise 38. Migrating Policies

A team adds a `PERMISSIVE` `USING (true)` policy for all roles thinking it will "help legacy policies run more smoothly." What is the risk?

### Exercise 39. Cross-Tenant Maintenance

A job needs to purge archived documents across all tenants, while the app role can `DELETE` only the current tenant's documents. Should we reuse the app role and disable RLS? Propose a safer model.

### Exercise 40. Comprehensive Design

You are designing a multi-tenant SaaS: table `invoices(tenant_id, invoice_id, amount, state)`, a backend serving hundreds of tenants with a connection pool. Propose a permission model, RLS policies for `SELECT`/`INSERT`/`UPDATE`/`DELETE`, a trustworthy tenant identity source, test strategy, and audit checks.

## 36. Exercise Solutions Guide

### Answer 1. GRANT and RLS

`GRANT SELECT` governs whether a role can read the relation, without filtering rows. `USING` policies define the permitted row subset without granting `SELECT`; missing either breaks access or isolation. Combine schema `USAGE`, table/column `GRANT`s, and RLS.

### Answer 2. Default Deny

Non-bypass role alpha sees **0 rows** when RLS is enabled and no matching policy exists. An ordinary table owner **bypasses by default** and sees all six rows unless `FORCE` is set; superusers bypass as well.

### Answer 3. SELECT Policy

```sql
CREATE POLICY documents_select_own
ON rls_demo.documents
FOR SELECT
TO rls_demo_alpha, rls_demo_beta
USING (tenant_role = current_user::text);
```

This policy already exists in the lab; this is the reference solution—do not recreate with the same name.

### Answer 4. Alpha SELECT

Alpha sees IDs **1, 2, 5**. Sum of `amount` is `100 + 250 + 30 = 380`. Beta sees IDs **3, 4, 6**, summing to `520`.

### Answer 5. Other-Tenant Row

`SELECT ... WHERE document_id = 4` as alpha returns **0 rows** because `USING` filters out ID 4. It does not raise permission denied merely because another tenant's row exists.

### Answer 6. INSERT Policy

```sql
CREATE POLICY documents_insert_own
ON rls_demo.documents
FOR INSERT
TO rls_demo_alpha, rls_demo_beta
WITH CHECK (tenant_role = current_user::text);
```

`FOR INSERT` uses `WITH CHECK` because it validates new rows. This policy already exists in the lab.

### Answer 7. Wrong-Tenant INSERT

Alpha attempts to write a row with `tenant_role = rls_demo_beta`. `WITH CHECK` evaluates to `FALSE`, so `INSERT` is rejected with a row-level security error rather than silently inserting 0 rows.

### Answer 8. UPDATE Policy

```sql
CREATE POLICY documents_update_own
ON rls_demo.documents
FOR UPDATE
TO rls_demo_alpha, rls_demo_beta
USING (tenant_role = current_user::text)
WITH CHECK (tenant_role = current_user::text);
```

`USING` filters old rows; `WITH CHECK` constrains new rows. Assumes the policy does not already exist; do not re-run in the prepared lab.

### Answer 9. Changing Tenant via UPDATE

ID 1 belongs to alpha so `USING` is `TRUE`; after changing `tenant_role = beta`, `WITH CHECK` is `FALSE`. PostgreSQL rejects the `UPDATE`. This shows why checking only the old row is insufficient when business rules forbid transferring ownership.

### Answer 10. Updating Another Tenant

Normal result is **UPDATE 0 rows** because existing row ID 4 fails `USING`. This does not prove ID 4 is absent physically.

### Answer 11. DELETE Policy

```sql
CREATE POLICY documents_delete_own
ON rls_demo.documents
FOR DELETE
TO rls_demo_alpha, rls_demo_beta
USING (tenant_role = current_user::text);
```

`DELETE` only needs to define which existing rows may be targeted.

### Answer 12. DELETE and WITH CHECK

`DELETE` creates no new row version to validate, so `WITH CHECK` does not apply to `FOR DELETE`. Rows failing `USING` are excluded from deletion, often yielding fewer deleted rows than expected or 0.

### Answer 13. FOR ALL

Pattern on pre-existing objects:

```sql
CREATE POLICY app_docs_tenant_scope
ON app.documents
FOR ALL
TO app_user
USING (
    tenant_id = app.current_tenant_id()
)
WITH CHECK (
    tenant_id = app.current_tenant_id()
);
```

The app role must hold required object privileges, and `app.current_tenant_id()` must derive tenant identity from a trusted source. A `FOR ALL` policy does not grant table privileges.

### Answer 14. Fallback

False. When an `UPDATE`/`ALL` policy omits `WITH CHECK` while specifying `USING`, PostgreSQL falls back to using `USING` to check new rows. Authors should still declare both explicitly whenever target and write rules differ.

### Answer 15. Permissive OR

Effective predicate:

```sql
(tenant_id = 42) OR (state = 'published')
```

Any published row from another tenant satisfies the second branch, creating a **cross-tenant leak risk**. If both must hold, combine with `AND` in one policy or add a matching restrictive policy.

### Answer 16. Restrictive AND

Alpha initially sees 1, 2, 5. The restrictive policy removes `archived`, leaving **1, 2**. When run inside a transaction and rolled back, the test policy is undone.

### Answer 17. Restrictive Only

No. Restrictive policies only narrow sets allowed by permissive policies. Without a permissive policy, default deny still applies for RLS-constrained roles.

### Answer 18. FORCE

`FORCE ROW LEVEL SECURITY` forces an ordinary table owner to obey policies when querying the table. It **does not force superusers or `BYPASSRLS` roles** to obey RLS.

### Answer 19. row_security off

No. `row_security = off` does not grant bypass rights; for a role filtered by policies, the query raises an error rather than silently returning a subset. Full access requires authorized admin/bypass privileges and controlled operational flows.

### Answer 20. pg_policies

```sql
SELECT
    policyname,
    cmd,
    permissive,
    roles,
    qual,
    with_check
FROM pg_policies
WHERE schemaname = 'rls_demo'
  AND tablename = 'documents'
ORDER BY policyname;
```

`qual` shows `USING`; `with_check` shows declared check expressions. Do not assume an empty `with_check` means no check exists—remember the fallback rule.

### Answer 21. pg_class

```sql
SELECT
    c.relrowsecurity,
    c.relforcerowsecurity
FROM pg_class AS c
WHERE c.oid = 'rls_demo.documents'::regclass;
```

`relrowsecurity` checks `ENABLE`; `relforcerowsecurity` checks owner `FORCE`.

### Answer 22. has_table_privilege

```sql
SELECT
    has_table_privilege(
        'rls_demo_alpha',
        'rls_demo.documents',
        'SELECT'
    ) AS can_select,
    has_table_privilege(
        'rls_demo_alpha',
        'rls_demo.documents',
        'UPDATE'
    ) AS can_update;
```

Both returning `TRUE` indicates object privileges only—**not** that the role reads/updates all rows; RLS still filters separately.

### Answer 23. current_user and session_user

`SET ROLE` changes `current_user` to the effective role, while `session_user` remains the original login role. They do not have to match. The lab compares `tenant_role = current_user::text`, so alpha sees only alpha rows.

### Answer 24. GUC and Trust Boundaries

The backend must authenticate the tenant, set the context in-transaction via a trusted path, parameterize all SQL, minimize DB privileges, and block untrusted direct SQL under the shared app role. If an attacker can run arbitrary SQL as the app role, they can overwrite `app.tenant_id` to probe other tenants; a GUC alone is not an unforgeable identity.

### Answer 25. SET LOCAL

`SET LOCAL` is transaction-scoped, preventing tenant A's context from lingering when a connection returns to the pool for tenant B—provided every query runs inside a properly wrapped transaction and context is always set explicitly. With session-level `SET`, enforce reliable pool resets; under transaction pooling, never assume session context persists across transactions.

### Answer 26. SECURITY DEFINER

Yes. The function runs under the definer's rights, and if the definer bypasses RLS, it can count all six rows and return `6` even though alpha directly sees `3`. Audit owner/function privileges, `EXECUTE` grants, input validation, `search_path`, and returned data—never use `SECURITY DEFINER` as a casual bypass.

### Answer 27. security_invoker Views

PostgreSQL supports `security_invoker = true` on views starting in **major version 15**. Such views check permissions and RLS on underlying relations as the caller, whereas ordinary views may run under the view owner's context. `security_barrier` guards against optimizer/expression leaks rather than changing privilege context like `security_invoker`.

### Answer 28. TRUNCATE

No. `TRUNCATE` is not filtered row-by-row via `USING`. Never grant `TRUNCATE` to app tenant roles; when deleting per tenant, use `DELETE` with proper predicates and RLS/constraints, or an authorized admin workflow.

### Answer 29. UNIQUE Side Channel

Uniqueness checks span the whole dataset, raising duplicate errors for values owned by other tenants invisible to caller `SELECT`s. If business requires per-tenant uniqueness only, use:

```sql
UNIQUE (tenant_id, email)
```

Never weaken global uniqueness to per-tenant uniqueness if business rules strictly mandate global uniqueness.

### Answer 30. FK Side Channel

Referential integrity checks do not filter targets under caller RLS; an `INSERT` referencing a parent ID succeeds or fails depending on whether that parent exists, leaking existence. Use unpredictable IDs, proper authorization, and minimal-detail error responses.

### Answer 31. Policy Subqueries

Issues include:

- The role needs read rights on the referenced membership table/function, or queries fail.
- Subqueries referencing the RLS-protected table itself can trigger policy recursion.
- Concurrent membership edits introduce snapshot/race risks.
- Unindexed subqueries slow down per-row checks.

Design schema/privileges carefully, ensure proper isolation/locking and indexes, and verify `EXPLAIN` as the real role.

### Answer 32. Pool Context

Tenant 99's request B could execute with tenant 42's leftover context if not reset, reading wrong data or failing. Two mitigations:

1. Use `SET LOCAL` inside a transaction wrapping all queries of the request.
2. With session `SET`, reliably set and reset connection context on pool checkout/checkin, and run integration tests through the real pool.

In both approaches, tenant identity is verified server-side, never taken directly from untrusted input.

### Answer 33. UPDATE RETURNING

`RETURNING title` reads column values; `WHERE`/`SET` may read columns too. The role requires `SELECT` privileges and matching policies per `UPDATE` semantics. Having only an `UPDATE` grant/policy is not enough for `UPDATE ... RETURNING`.

### Answer 34. Draft Editor

```sql
USING (
    tenant_id = app.current_tenant_id()
    AND state = 'draft'
)
WITH CHECK (
    tenant_id = app.current_tenant_id()
    AND state IN ('draft', 'review')
)
```

`USING` checks the existing row; `WITH CHECK` validates the resulting row. Assumes a trusted current-tenant function; if other permissive policies exist, check whether ORing them widens access.

### Answer 35. Indexing and Measurement

Example:

```sql
CREATE INDEX idx_rls_demo_tenant_state
ON rls_demo.documents (tenant_role, state);
```

This matches both the tenant and state predicates (skip creating if it already exists in the lab). On 20M rows, compare `EXPLAIN (ANALYZE, BUFFERS)` under the app role, checking actual rows, buffers, planning/execution times, index size, and write overhead. Never assume an index scan always beats a sequential scan.

### Answer 36. View Owner Bypass

Ordinary views can read base tables using the view owner's security context. If the view owner bypasses RLS, callers holding `SELECT` on the view see out-of-scope rows. From PG15 onward, use `security_invoker = true` where appropriate, separate owner/bypass roles, restrict view `GRANT`s, and test as real tenant roles.

### Answer 37. Eight Negative Tests

Minimal set:

1. Alpha `SELECT` beta row ID 4 -> returns 0 rows.
2. Alpha `UPDATE` beta row ID 4 -> updates 0 rows.
3. Alpha `DELETE` beta row ID 6 -> deletes 0 rows.
4. Alpha `INSERT` row with `tenant_role` beta -> RLS error.
5. Alpha `UPDATE` alpha row changing `tenant_role` to beta -> RLS error.
6. Alpha queries a granted view -> leaks zero beta rows (per contract).
7. Alpha calls an exposed `SECURITY DEFINER` function -> leaks zero out-of-scope counts/details.
8. Two different-tenant requests reuse the same connection pool -> zero tenant context bleed.

Also test missing tenant context, accidental `FOR ALL USING(true)` widening, role memberships, and `INSERT ... ON CONFLICT`.

### Answer 38. PERMISSIVE USING(true)

Permissive policies for the same command/role are ORed with existing permissive policies. Adding `USING(true)` makes the combined permissive predicate `TRUE` for every row, effectively nullifying prior tenant filters on those read/update/delete paths. That is a severe vulnerability; to tighten rules, use restrictive policies or `AND` inside controlled policies.

### Answer 39. Cross-Tenant Maintenance

Never disable RLS for the app role or grant `BYPASSRLS` casually. Create a dedicated maintenance job/role with scoped permissions, managed secrets, bounded schedules/data scopes, auditing, and dry-run/count checks. The backend tenant role keeps RLS intact; the cross-tenant job runs through an isolated, audited admin path.

### Answer 40. Invoices System Design

A complete plan:

1. **Migration owner** owns tables and policies; **`app_runtime`** is non-owner and lacks `BYPASSRLS`.
2. Enable `ENABLE ROW LEVEL SECURITY` on `invoices`.
3. Choose a trusted tenant identity source: separate DB roles or a trusted backend setting transaction-scoped context; never rely on custom GUCs if clients can run arbitrary SQL.
4. Create `SELECT` policy `USING (tenant_id = current_tenant)`.
5. Create `INSERT` policy `WITH CHECK (tenant_id = current_tenant)`.
6. Create `UPDATE` policy `USING (tenant_id = current_tenant)` and `WITH CHECK (tenant_id = current_tenant)`, plus state restrictions if needed.
7. Create `DELETE` policy with `USING` only if business truly needs hard deletes; otherwise omit both `GRANT DELETE` and `DELETE` policies.
8. Restrict `GRANT`s by command/column, omitting `TRUNCATE`/DDL/bypass rights.
9. Enforce constraints on invoice identity, numeric ranges, and state transitions; consider per-tenant unique keys if business allows.
10. Run negative tests across multiple tenants, `WHERE`-less `SELECT`s, wrong-tenant `INSERT`/`UPDATE`, `UPDATE RETURNING`, UPSERTs, views/functions, connection pooling, and backup/maintenance roles.
11. Audit `pg_policies`/`pg_class`/role memberships, inspect `EXPLAIN` plans and access logs without logging secrets or sensitive contents.

General policy template **once objects and a verified `current_tenant` function exist**:

```sql
CREATE POLICY invoices_read ON app.invoices
FOR SELECT TO app_runtime
USING (tenant_id = app.current_tenant_id());

CREATE POLICY invoices_insert ON app.invoices
FOR INSERT TO app_runtime
WITH CHECK (tenant_id = app.current_tenant_id());

CREATE POLICY invoices_update ON app.invoices
FOR UPDATE TO app_runtime
USING (tenant_id = app.current_tenant_id())
WITH CHECK (tenant_id = app.current_tenant_id());
```

If the application never deletes invoices, **omit** both `DELETE` policies and `GRANT DELETE`. If deletion is required, add a tenant-scoped `DELETE` policy matching business rules. These statements do not run directly in the lab because `app.invoices` and `app.current_tenant_id()` are hypothetical objects.

## 37. Row-Level Security Checklist

### 37.1. Schema and Privileges

1. Is `ENABLE ROW LEVEL SECURITY` enabled on tables storing tenant data?
2. Are all tenant tables protected, including new tables added in migrations?
3. Is the app role free of table ownership, `SUPERUSER`, and `BYPASSRLS`?
4. Is `FORCE ROW LEVEL SECURITY` needed for ordinary owners?
5. Do schema `USAGE` and table/column `GRANT`s follow least privilege?
6. Are `TRUNCATE`, `REFERENCES`, and unnecessary DDL withheld from the app role?
7. Are views, materialized views, functions, and jobs free of unintended policy bypasses?

### 37.2. Policy Design

8. Does the `SELECT` `USING` policy rely on a trustworthy tenant identity?
9. Does the `INSERT` `WITH CHECK` policy block creating rows for other tenants?
10. Does the `UPDATE` policy validate **both existing rows and new rows**?
11. Is `DELETE` enabled only if genuinely required by business rules?
12. Could any `PERMISSIVE` policy unexpectedly widen access via OR?
13. Do restrictive policies have at least one matching permissive policy so access works?
14. Does any `FOR ALL` policy alter unintended commands?
15. Do policy expressions handle SQL `NULL`/`UNKNOWN` safely as deny-by-default?
16. Do helper tables/functions referenced by policies have proper privileges and acceptable cost?

### 37.3. Tenant Identity and Application

17. Are `current_user`, `session_user`, and tenant context clearly distinguished?
18. If using custom GUCs, are untrusted users blocked from arbitrarily setting them via SQL?
19. With connection pools, is context transaction-bound and reliably reset?
20. Is all SQL parameterized against injection?
21. Are `SECURITY DEFINER` `search_path` and `EXECUTE` leak risks mitigated?
22. On PG15+, which views require `security_invoker = true`?
23. Is the app prevented from directly accessing partitions or helper tables unchecked?

### 37.4. Testing and Operations

24. Are `WHERE`-less `SELECT`s tested under each tenant?
25. Are wrong-tenant `INSERT`/`UPDATE` attempts tested and confirmed to fail?
26. Are out-of-tenant `UPDATE`/`DELETE` attempts tested and confirmed to affect 0 rows?
27. Are `RETURNING`, UPSERTs, and view/function paths tested?
28. Is pool context isolation tested across sequential and concurrent requests?
29. Are `UNIQUE`/FK errors evaluated as potential side channels?
30. Are dedicated backup and maintenance roles configured?
31. Are `pg_policies`, `pg_class`, and role grants/memberships monitored?
32. Are `EXPLAIN` plans and indexes verified so RLS does not degrade workloads?
33. Are migrations checked so policies aren't dropped/changed or new tables left with RLS disabled?
34. Are access and errors logged/audited without exposing sensitive contents?

## 38. Summary

**Row-Level Security** lets PostgreSQL enforce access limits **at the row level** directly under database roles and policies, adding a vital defense layer alongside application `WHERE` clauses.

Rules to remember:

- **`GRANT` and RLS are two distinct layers:** a role needs object privileges before row policies are evaluated.
- **`ENABLE ROW LEVEL SECURITY` creates no policies automatically:** for roles subject to RLS, having no matching permissive policy means default deny.
- **`USING` evaluates existing rows** for `SELECT`, `UPDATE`, and `DELETE`.
- **`WITH CHECK` evaluates new rows** for `INSERT` and post-change `UPDATE` rows; failing checks raise an error rather than silently skipping.
- **`UPDATE` requires thinking about two states:** can the old row be touched, and does the resulting row remain within allowed bounds?
- **Permissive policies OR; restrictive policies AND:** adding another permissive policy can widen access unintentionally.
- **Owners bypass RLS by default; `FORCE` constrains ordinary owners only; superusers/`BYPASSRLS` still bypass.**
- **`row_security = off` does not grant bypass rights**; it raises errors to prevent unknowingly processing filtered data.
- **Session GUCs are not unforgeable identities:** if an app role lets users run arbitrary SQL, they can spoof custom context; enforce a strict trust boundary.
- **Views and `SECURITY DEFINER` functions need dedicated review:** owner rights can let indirect access bypass caller policies.
- **RLS does not filter every operation:** `TRUNCATE`, `UNIQUE`/FK checks, and side channels require privilege controls and careful schema/API design.
- **Test with low-privilege app roles**, never solely superusers; monitor `pg_policies`, grants, and execution plans.

Safety rule:

> **Use `USING` to constrain which rows users may touch; use `WITH CHECK` to constrain which rows users may create. Keep tenant identity trustworthy and test every access path—not just one sample `SELECT`.**

RLS is powerful for multi-tenant systems, owner-scoped data, and row-isolation requirements, yet is trustworthy only when paired with **least privilege, accurate policy semantics, constraints, isolation, negative testing, and disciplined operations**.

## 39. References

Official PostgreSQL documentation; cross-check against your running server's major version:

- [Row Security Policies — PostgreSQL Documentation](https://www.postgresql.org/docs/current/ddl-rowsecurity.html): RLS, default deny, `USING`/`WITH CHECK`, permissive/restrictive, bypass, and limitations.
- [CREATE POLICY](https://www.postgresql.org/docs/current/sql-createpolicy.html): syntax, command applicability, and policy expressions.
- [ALTER POLICY](https://www.postgresql.org/docs/current/sql-alterpolicy.html): changing roles and expressions.
- [DROP POLICY](https://www.postgresql.org/docs/current/sql-droppolicy.html): removing policies.
- [ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html): `ENABLE`/`DISABLE`/`FORCE`/`NO FORCE ROW LEVEL SECURITY`.
- [GRANT](https://www.postgresql.org/docs/current/sql-grant.html): schema/table/column/function privileges.
- [Role Attributes](https://www.postgresql.org/docs/current/role-attributes.html): superuser, `BYPASSRLS`, and role attributes.
- [SET ROLE](https://www.postgresql.org/docs/current/sql-set-role.html): active role, `CURRENT_USER`, and role context.
- [pg_policies](https://www.postgresql.org/docs/current/view-pg-policies.html): inspecting policy definitions.
- [CREATE VIEW](https://www.postgresql.org/docs/current/sql-createview.html): `security_invoker` and `security_barrier` options.
- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html): `SECURITY DEFINER`, `search_path`, and `EXECUTE` grants.
- [CREATE TRIGGER](https://www.postgresql.org/docs/current/sql-createtrigger.html): trigger effects in write operations.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): measuring query plans with RLS under the real role context.
