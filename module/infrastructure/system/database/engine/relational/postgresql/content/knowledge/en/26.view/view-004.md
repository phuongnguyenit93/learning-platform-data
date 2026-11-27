# View Execution Privileges, security_invoker, and security_barrier in PostgreSQL

## 1. Whose Permissions Does a View Use to Return Data?

Suppose a system has a `finance.payments` table containing amounts, customers, processors, and internal notes. A reporting application needs to view **a subset of rows and columns**, rather than receiving direct read access to the entire table.

The development team creates a view:

~~~sql
CREATE VIEW reporting.v_paid_payments AS
SELECT payment_id, customer_id, amount
FROM finance.payments
WHERE status = 'paid';

GRANT SELECT ON reporting.v_paid_payments TO report_reader;
~~~

The critical security question is not just "Was `GRANT SELECT` issued on the view?", but also:

- Does the caller need `SELECT` on the `finance.payments` table?
- When the base table has **Row-Level Security (RLS)**, are the **caller's** policies or the **view owner's** policies applied?
- If the caller adds an expression that can leak data in an outer `WHERE` clause on the view, can PostgreSQL execute that expression before the view's filter?
- Is a view with `security_invoker=true` the same as a view with `security_barrier=true`?
- Does a view automatically protect data if a user can access the base table through another path?
- How do functions, nested views, schema privileges, and role memberships alter the answer?

This lesson answers those questions through one guiding principle: **you must separate access privileges, the identity used for RLS, and expression optimization boundaries (`security_barrier`)**. These three mechanisms are related, yet none replaces the others.

### 1.1. Learning Objectives

After this lesson, you will be able to:

1. Explain the difference between **SELECT privilege on a view**, **SELECT privilege on base tables**, and **USAGE privilege on a schema**.
2. Understand the default view mechanism that checks base table privileges using the **view owner's permissions**.
3. Create and alter views `WITH (security_invoker=true)` in PostgreSQL 15+ and state the impact on privileges and RLS.
4. Use `WITH (security_barrier=true)` when protecting filter conditions from premature pushdown of untrusted outer expressions.
5. Distinguish `security_barrier` from `security_invoker` and from `SECURITY DEFINER` on functions.
6. Test access with independent roles, `SET ROLE`, `GRANT`/`REVOKE`, `EXPLAIN`, and catalog queries.
7. Understand the risks of **RLS owner bypass**, `BYPASSRLS`, missing policies, nested views, and function execution privileges.
8. Recognize the limits of views as a security boundary: side channels, leaky functions, alternate access paths, and write operations.
9. Design migration, authorization, testing, and review workflows for sensitive views.
10. Practice SQL exercises and troubleshoot data access scenarios.

> **Operational warning:** `CREATE ROLE`, `GRANT`, `REVOKE`, `ALTER VIEW`, and `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` affect data access if run in the wrong environment. Practice in a dedicated database/schema using an authorized admin role. Do not execute an entire script containing "expected error" sections through a migration tool configured to stop on error.

---

## 2. What Is a View, and Where Does the Security Boundary Lie?

A **regular view** stores a SELECT query definition under a logical relation name. When queried, PostgreSQL uses rewrite/planning mechanisms to expand the query appropriately and execute it against the underlying relations.

~~~text
Application / User: report_reader
            |
            | SELECT payment_id, amount
            | FROM reporting.v_paid_payments;
            v
   reporting.v_paid_payments
   SELECT payment_id, amount
   FROM finance.payments
   WHERE status='paid'
            |
            v
      finance.payments
            |
            v
      Returned data rows
~~~

The caller sees a view interface by name, while base table read permissions are evaluated according to PostgreSQL's view rules.

### 2.1. Views Do Not Necessarily Create a Data Copy

A regular view does not store its own rows like a table. `SELECT` on a view executes the underlying query logic; when the base table changes, view results change accordingly.

A **materialized view** is a different object: it stores physical results and must be REFRESHed. Do not transfer caching/refresh assumptions from materialized views directly to regular view security.

### 2.2. A Security View Does Not Make Every Layer Safe Automatically

A view can:

- Expose only selected columns.
- Expose only rows matching a predicate.
- Check base table privileges as the owner or invoker.
- Apply a security barrier to constrain evaluation order of non-leakproof expressions.

However, a view **does not automatically**:

- Revoke direct base table read privileges that the caller already holds.
- Prevent data leaks across all side channels such as timing, locks, statistics, or error messages from permitted paths.
- Replace accurate RBAC/RLS design.
- Stop dangerous functions from being called externally if the role still holds `EXECUTE` on those functions.
- Guarantee row filtering if a view's definition is modified or another role holds privileges to alter the view.

You must design **least privilege** across every data access path.

---

## 3. Privilege Layers to Check When Querying a View

| Layer | Example Privilege / Object | Purpose |
|---|---|---|
| Database | `CONNECT ON DATABASE` | Allows connecting to the database |
| View schema | `USAGE ON SCHEMA reporting` | Resolves and uses objects in the schema |
| View | `SELECT ON reporting.v_paid_payments` | Allows reading the view's columns |
| Base table | `SELECT ON finance.payments` | Whether the caller needs this depends on the view's security mode |
| Base table schema | `USAGE ON SCHEMA finance` | Required for direct table access; via a default view, callers normally do not need this to query the view |
| Functions | `EXECUTE ON FUNCTION ...` | Functions invoked in the query have independent execution privileges |
| Row-level security | `POLICY ... USING (...)` | Filters/controls rows once the effective RLS identity is determined |
| Role attributes | `BYPASSRLS`, owner status, membership | Can alter RLS enforcement or effective privileges |

### 3.1. Grants on Views vs. Grants on Base Tables Are Separate Commands

~~~sql
GRANT SELECT ON reporting.v_paid_payments TO report_reader;
~~~

This grants `SELECT` on the **view**; it does not grant `SELECT` on `finance.payments`. Conversely:

~~~sql
GRANT SELECT ON finance.payments TO report_reader;
~~~

gives the user a separate path to read the base table, subject to schema privileges and RLS; it does not grant `SELECT` on the reporting view.

### 3.2. Schema USAGE for the Referenced Object

A role holding `SELECT` on a view without `USAGE` on the view's schema will still be blocked when accessing the view by name.

~~~sql
GRANT USAGE ON SCHEMA reporting TO report_reader;
GRANT SELECT ON reporting.v_paid_payments TO report_reader;
~~~

These are two distinct grants.

### 3.3. Is USAGE Needed on the Base Table's Schema?

For a **regular view checking base privileges as the view owner**, users only need appropriate privileges to use the view; they do not necessarily need `USAGE` on the base table's schema or `SELECT` on the base table.

For a **`security_invoker` view**, privileges on **base relations** are checked as the invoker, though accessing an underlying relation **through the view** does not mean the caller needs `USAGE` on every base schema the way direct table name resolution requires. For the caller to reference the base table directly by name, schema `USAGE` is still required. Distinguish **relation privilege checks** from **name lookup/access via view** when reviewing grants.

### 3.4. Column-Level Privileges

PostgreSQL supports granting privileges on individual columns:

~~~sql
GRANT SELECT (payment_id, customer_id, amount, status)
ON finance.payments TO report_reader;
~~~

When the caller holds the required column-level SELECT grants, a security-invoker view can run without granting `SELECT` on other sensitive columns, provided every reference in the view definition is covered.

Still, if an application can read `status` and filter columns via direct base table access, it can run arbitrary queries against them. **Column privileges do not replace row-level isolation**.

### 3.5. Privileges Do Not Replace Row Visibility Controls

`GRANT SELECT` answers "can the role execute SELECT?"; RLS answers "which rows are visible or modifiable under policy?"; `security_barrier` answers "can optimization push certain expressions ahead of protective filters?". All three questions must be answered independently.

---

## 4. Default Views: Base Table Privileges Checked as the View Owner

### 4.1. Default Behavior

In PostgreSQL, a regular view without `security_invoker` enabled accesses base tables using the **view owner's privileges**. This mechanism is sometimes informally called a *security-definer-like view*, though **never confuse it with `SECURITY DEFINER` on functions**.

Example:

~~~sql
-- Run as a role with privileges on the base table:
CREATE VIEW reporting.v_paid_payments AS
SELECT payment_id, customer_id, amount
FROM finance.payments
WHERE status='paid';
~~~

If:

- `report_owner` owns the view and holds SELECT on the base table.
- `report_reader` has `USAGE` on the view's schema + `SELECT` on the view.
- `report_reader` lacks SELECT on the base table.

then `report_reader` **can still SELECT from the view**, because base table access is checked against the view owner.

### 4.2. Privilege Check Flow

~~~text
SELECT FROM view sent by report_reader
       |
       +--> Does report_reader have SELECT on view? ---- No --> ERROR
       |
       +--> Does report_reader have USAGE on view schema? --- No --> ERROR
       |
       v
Default view (security_invoker = false)
       |
       +--> Base table permissions checked as VIEW OWNER
       |
       v
Read base table per query/view definition
       |
       v
Return rows/columns matching definition
~~~

### 4.3. Security Consequences

Default view behavior is useful for exposing **a restricted read interface** to users who must not access raw underlying tables directly.

However, if a view owner has permission to read **all rows**, view results may expose data beyond the caller's own RLS policies. This depends on RLS identity and owner rights on the base table, analyzed in the next sections.

### 4.4. View Owner Differs from Caller

A view may be created by `report_owner`, while the querying user is `report_reader`.

When querying the view:

- **Invoker** is the role executing the query.
- **View owner** is the role owning the view relation.
- **Table owner** may be yet another role.

These three roles are **not automatically the same**.

### 4.5. Never Over-Privilege the View Owner Unnecessarily

If the view owner is a superuser or holds `BYPASSRLS`, it has special bypass behavior under RLS. For sensitive reporting views, use a dedicated owner role with the **minimum privileges required**, rather than creating views as superuser out of convenience.

Also assess who can **alter the view definition**. A compromised view owner can expand exposed columns/rows within the limits of its privileges.

---

## 5. security_invoker: Checking Base Table Privileges as the Caller

### 5.1. Available Since PostgreSQL 15

The `security_invoker` option for **regular views** was introduced in PostgreSQL 15. Before using it:

~~~sql
SHOW server_version;

SELECT current_setting('server_version_num')::integer >= 150000
       AS supports_security_invoker_views;
~~~

If your database is older than PostgreSQL 15, do not rely on this syntax; upgrade or choose another verified privilege/RLS design.

### 5.2. Creating a View with security_invoker

~~~sql
CREATE VIEW reporting.v_paid_payments_invoker
WITH (security_invoker = true)
AS
SELECT payment_id, customer_id, amount
FROM finance.payments
WHERE status = 'paid';
~~~

When a caller SELECTs from the view:

1. The caller needs `SELECT` on the view and `USAGE` on the view's schema.
2. **Privileges on underlying base relations** are checked against the caller as if referenced directly, rather than against the view owner.
3. If base tables have RLS, **policies applicable to the caller** are enforced, subject to standard RLS/bypass rules.
4. The caller can be denied even if the view owner holds full SELECT on the base tables.

### 5.3. Altering an Existing View

~~~sql
ALTER VIEW reporting.v_paid_payments
SET (security_invoker = true);
~~~

And you can revert to default behavior:

~~~sql
ALTER VIEW reporting.v_paid_payments
SET (security_invoker = false);
~~~

Changing this option can cause **running applications to lose read access** or change which rows they see. Never toggle this flag in production without auditing grants, RLS, and all caller roles.

### 5.4. security_invoker Does Not Grant Base Table Privileges Automatically

A common misconception:

> "Just enable security_invoker and callers can SELECT the view and still see data without base table privileges."

The opposite is true: with `security_invoker` enabled, the caller **must hold required privileges on base relations** per invoker checks. Otherwise the query fails with `permission denied for table ...`.

### 5.5. security_invoker Does Not Automatically Add WHERE tenant_id

It only changes **whose identity is checked for privileges and RLS**. If the base table lacks RLS and the caller already has full-table SELECT, a security-invoker view **does not restrict the caller from reading the base table** by a tenant-specific predicate.

To enforce true row isolation, design proper RLS, role grants, and policies.

### 5.6. The Option Applies Per View, Not Per Session

There is no session setting like `SET security_invoker=on` to turn all views into invoker views. It is a per-view property stored in catalogs and managed via `CREATE VIEW WITH (...)` and `ALTER VIEW ... SET (...)`.

---

## 6. security_barrier: Protecting Security Filter Evaluation Order

### 6.1. The Problem with Caller-Supplied Expressions

Suppose a view restricts users to rows belonging to tenant 10:

~~~sql
CREATE VIEW reporting.v_tenant10 AS
SELECT record_id, tenant_id, public_code
FROM finance.records
WHERE tenant_id = 10;
~~~

A caller might add an extra predicate:

~~~sql
SELECT *
FROM reporting.v_tenant10
WHERE suspicious_function(public_code);
~~~

The SQL optimizer normally tries to push filter conditions down early to reduce work. However, a user-controlled function could:

- Raise an error message containing part of the input value.
- Write logs or raise exceptions based on values.
- Trigger observable side effects.
- Exhibit input-dependent execution timing.

If an expression **unsafe to evaluate before filtering** executes on rows the view predicate intended to hide, the user can infer values from filtered-out rows even though they never appear in the final output.

### 6.2. What Is security_barrier Used For?

When a view is declared as:

~~~sql
CREATE VIEW reporting.v_tenant10_safe
WITH (security_barrier = true)
AS
SELECT record_id, tenant_id, public_code
FROM finance.records
WHERE tenant_id = 10;
~~~

PostgreSQL processes the security-barrier view under rules that prevent **non-leakproof** operators/functions from the outer query from being pushed ahead of the view's security qualifications in ways that could leak filtered-out data.

### 6.3. A Security-Barrier View Still Has Its Own Owner/Invoker Mode

`security_barrier=true` **does not** switch base table privilege checks to invoker mode. The view above **remains in default owner mode** unless `security_invoker=true` is also specified.

This is the single most important distinction between the two options.

### 6.4. What Does LEAKPROOF Mean?

PostgreSQL has a `LEAKPROOF` function/operator attribute indicating to the optimizer that the function **reveals no information about arguments other than its return value**. Only a highly privileged role (practically superuser) can mark a function as LEAKPROOF.

The optimizer can push expressions known to be **leakproof** past a security barrier where valid. Thus `security_barrier` does not mean "every caller WHERE always runs after every view WHERE in literal written order."

**Never** mark a function `LEAKPROOF` if it can error on data, log values, cause side effects, or leak data just to help the planner use an index faster.

### 6.5. Do Not Rely on WHERE Clause Order as a Security Boundary

~~~sql
WHERE tenant_id = 10
  AND suspicious_function(public_code)
~~~

SQL makes no general guarantee that the left condition always evaluates before the right condition. PostgreSQL can reorder predicates for optimization within safety constraints.

When access control depends on evaluation order, design proper **`security_barrier`/RLS/permissions** instead of just reordering WHERE clauses.

### 6.6. A Barrier Is Not Absolute Isolation

`security_barrier` mitigates one specific leak vector via **predicate pushdown/evaluation order**. It does not stop all side channels involving timing, result sizes, selectivity estimates, logging, locking, statistics, or other privileges the user already possesses.

If the view exposes `public_code` on permitted rows, users can read `public_code` on those rows. A barrier does not turn exposed view columns into secrets.

---

## 7. Comparison Table of the Two Options

| Aspect | Default View | `security_invoker=true` | `security_barrier=true` |
|---|---|---|---|
| View access privilege | Caller needs view privilege | Caller needs view privilege | Caller needs view privilege |
| Base table privileges | Checked as **view owner** on default view relations | Checked as **caller** on invoker view base relations | **Does not change** owner/invoker mode |
| RLS on base tables | Policies evaluated as view owner | Evaluated as caller | **Does not change** RLS identity |
| Blocks early evaluation of caller's non-leakproof quals past view filter | No special barrier | Not solely via invoker | **Yes**, per security barrier rules |
| Changes the view's SQL WHERE? | No | No | No |
| Grants base table privileges to caller? | No | No | No |
| Can both options be combined? | Not applicable | **Yes** | **Yes** |
| Typical use case | Exposing restricted read interface on tables caller cannot read directly | Views that must respect caller's base privileges and RLS | Views with sensitive predicates guarding against external leaky quals |
| Primary risk | Overprivileged owner; RLS applied as owner | Caller lacks base privileges; visible rows may change after migration | Can restrict pushdown and reduce performance |

### 7.1. Combining Both

~~~sql
CREATE VIEW reporting.v_secure
WITH (
    security_invoker = true,
    security_barrier = true
)
AS
SELECT record_id, tenant_id, public_code
FROM finance.records
WHERE is_active = true;
~~~

When combined:

- **Invoker mode:** applies the caller's privileges and RLS identity to underlying base relations.
- **Barrier mode:** protects evaluation order against external non-leakproof qualifiers.

There are valid reasons to use both, and cases where only one is needed. Never assume turning on every security flag is always best: **review both the security model and the cost plan**.

---

## 8. How Does Base Table RLS Interact with Views?

### 8.1. RLS Is a Table Mechanism, Not a Security Column on Views

Row-Level Security is enabled on the **base table**:

~~~sql
ALTER TABLE finance.records ENABLE ROW LEVEL SECURITY;
~~~

Then policies are defined:

~~~sql
CREATE POLICY visible_records_for_readers
ON finance.records
FOR SELECT
TO report_reader
USING (tenant_id = 10);
~~~

This syntax is illustrative. The lab section below provides a self-contained schema and roles.

### 8.2. RLS Policies Depend on the Effective Role

When base table RLS is enabled:

- Regular users cannot see rows unless permitted by a policy.
- If no matching policy applies, the default behavior is **deny** for roles subject to RLS.
- The **table owner** bypasses RLS by default unless `FORCE ROW LEVEL SECURITY` is enabled on the table.
- Superusers and roles with `BYPASSRLS` bypass RLS by privilege.
- `FORCE ROW LEVEL SECURITY` subjects the table owner to RLS, but does not subject superusers or `BYPASSRLS` roles to normal policies.

Therefore, you must identify the **RLS identity** and role attributes whenever analyzing a view.

### 8.3. Default-Owner Views Can Bypass Caller Policies

If the view owner is also the **table owner**, it normally bypasses RLS. A reader whose policy limits direct table queries to tenant 10 may still see **additional tenants through a default-owner view** unless the view itself filters by tenant.

This is not a bug in PostgreSQL. It is a direct consequence of the **owner-based view privilege model**. Never use a default-owner view in place of per-user RLS without understanding this effect.

### 8.4. security_invoker Views Enforce the Caller's RLS

With `security_invoker=true`, base relations are accessed under the caller's privileges and RLS identity; the caller's row-level policies can further narrow the view's output beyond the view's own predicate.

If the caller is a superuser or holds `BYPASSRLS`, invoker mode does not force normal RLS restrictions onto that role. Security invoker never downgrades a caller's own privileges.

### 8.5. Policies Do Not Grant SELECT Privileges

RLS decides which rows a role may see, but the role must still hold the required **relation privileges**. Creating a SELECT policy does not grant SELECT on the table; a separate `GRANT` is needed if a security-invoker view or direct access requires it.

### 8.6. Never Build Tenant Isolation on Client-Writable GUCs

A commonly written policy pattern:

~~~sql
USING (tenant_id = current_setting('app.tenant_id')::integer)
~~~

If the querying role can freely run `SET app.tenant_id`, it can switch to any tenant and bypass the security goal. Only use a session setting for tenant identity when **the application/infrastructure binds it to a verified identity**, clients cannot tamper with it, and the threat model is clearly validated.

In the lab below, we use role-specific policies with fixed tenant IDs for clear testing rather than untrusted custom GUCs.

---

## 9. Reproducible Security Lab: Owner, Caller, and RLS

### 9.1. Environment Prerequisites

This lab assumes:

- PostgreSQL **15 or newer** to support `security_invoker`.
- A test admin account with privileges to create roles and schemas, create tables/views/policies, and run `SET ROLE` into the lab roles.
- A fresh database or one where schema `view_lab` does not yet exist.
- Role names `view_lab_owner` and `view_lab_reader` are not already in use elsewhere.

`CREATE ROLE` affects the **entire PostgreSQL cluster**, not just one schema. Run only on an authorized test instance. We omit LOGIN/password on lab roles since we test via `SET ROLE` from an admin session.

### 9.2. Creating Roles

Run as an **authorized** admin account:

~~~sql
CREATE ROLE view_lab_owner NOLOGIN;
CREATE ROLE view_lab_reader NOLOGIN;

CREATE SCHEMA view_lab AUTHORIZATION view_lab_owner;
~~~

`NOLOGIN` roles cannot connect directly, but can own objects, receive grants, and simulate permissions via `SET ROLE` from a privileged session.

### 9.3. Creating the Table as the Owner Role

~~~sql
SET ROLE view_lab_owner;

CREATE TABLE view_lab.accounts (
    account_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    region TEXT NOT NULL,
    balance NUMERIC(12,2) NOT NULL,
    internal_code TEXT NOT NULL
);

INSERT INTO view_lab.accounts
    (account_id, tenant_id, region, balance, internal_code)
VALUES
    (1, 10, 'north', 100.00, 'N10-A'),
    (2, 20, 'north', 200.00, 'N20-B'),
    (3, 10, 'south', 300.00, 'S10-C'),
    (4, 20, 'south', 400.00, 'S20-D'),
    (5, 10, 'north', 500.00, 'N10-E');
~~~

The table has five rows:

| account_id | tenant_id | region | balance | internal_code |
|---:|---:|---|---:|---|
| 1 | 10 | north | 100 | N10-A |
| 2 | 20 | north | 200 | N20-B |
| 3 | 10 | south | 300 | S10-C |
| 4 | 20 | south | 400 | S20-D |
| 5 | 10 | north | 500 | N10-E |

### 9.4. Creating a Default Owner-Mode View

While still in `SET ROLE view_lab_owner`:

~~~sql
CREATE VIEW view_lab.v_north_default AS
SELECT account_id, tenant_id, region, balance
FROM view_lab.accounts
WHERE region = 'north';

RESET ROLE;
~~~

The view exposes four columns, **omits `internal_code`**, and filters `region='north'`.

### 9.5. Granting Privileges Only on the View

Run as the appropriate owner/admin; use `SET ROLE view_lab_owner` if the session has permission to switch roles:

~~~sql
GRANT USAGE ON SCHEMA view_lab TO view_lab_reader;
GRANT SELECT ON view_lab.v_north_default TO view_lab_reader;
~~~

Do **not** grant `SELECT ON view_lab.accounts` to the reader yet.

### 9.6. Reading the View as the Reader

~~~sql
SET ROLE view_lab_reader;

SELECT current_user, session_user;

SELECT account_id, tenant_id, region, balance
FROM view_lab.v_north_default
ORDER BY account_id;

RESET ROLE;
~~~

Expected `account_id` set: **1, 2, 5**.

The reader can query the view despite **lacking SELECT on the base table**, because the view defaults to checking base privileges as `view_lab_owner`.

### 9.7. Attempting to Read the Base Table: Expected Error

~~~sql
-- Run SEPARATELY to observe the permission error:
SET ROLE view_lab_reader;

SELECT account_id, tenant_id
FROM view_lab.accounts;

RESET ROLE;
~~~

The direct base table SELECT is expected to fail with `permission denied for table accounts`. If your SQL client aborts on error, run `RESET ROLE` separately or in a clean statement.

Verification point: **GRANT SELECT on a view does not grant SELECT on the base table**.

### 9.8. Avoiding Confusion with SET ROLE

`SET ROLE view_lab_reader` changes `current_user` to simulate privileges while `session_user` remains your original login role. If run from an account lacking permission to assume `view_lab_reader`, `SET ROLE` itself will error—that is a lab setup prerequisite, not a `security_invoker` error.

---

## 10. Enabling Base Table RLS While Default Views Still Use Owner Identity

### 10.1. Creating a Policy Limiting the Reader to Tenant 10

Run as the owner:

~~~sql
SET ROLE view_lab_owner;

ALTER TABLE view_lab.accounts ENABLE ROW LEVEL SECURITY;

CREATE POLICY accounts_reader_tenant10
ON view_lab.accounts
FOR SELECT
TO view_lab_reader
USING (tenant_id = 10);

RESET ROLE;
~~~

This policy lets the reader see rows with `tenant_id=10` **when the reader is subject to RLS and holds SELECT on the table**. It does not grant relation privileges by itself.

### 10.2. Which Rows Does the Default View Return Now?

~~~sql
SET ROLE view_lab_reader;

SELECT account_id,tenant_id,region
FROM view_lab.v_north_default
ORDER BY account_id;

RESET ROLE;
~~~

Expected result is still **1, 2, 5**.

Why is row **2** (`tenant_id=20`) still visible even though the reader's policy allows only tenant 10?

- This view is in **owner mode**.
- `view_lab_owner` also owns `view_lab.accounts`.
- **Table owners bypass RLS by default** unless FORCE RLS is enabled.
- Thus the RLS policy targeting `view_lab_reader` is not applied when reading the base table through this owner-mode view.
- The view still filters `region='north'`, returning 1, 2, 5.

**Security lesson:** enabling RLS on a base table is insufficient if users also have an access path through a view owned by a role that bypasses RLS.

### 10.3. What Does FORCED RLS Change?

When the owner runs:

~~~sql
ALTER TABLE view_lab.accounts FORCE ROW LEVEL SECURITY;
~~~

a normal table owner becomes subject to RLS. Because the lab only defined a SELECT policy for `view_lab_reader`, the owner lacks a permissive policy and the default view returns **zero rows** unless the owner has `BYPASSRLS`.

This is a **major behavioral change**; never toggle it on production tables just to experiment. Remember that `FORCE ROW LEVEL SECURITY` still does not force superusers or `BYPASSRLS` roles under normal policies.

If testing in the lab, plan policy updates carefully and remember FORCE RLS affects all other applications connecting as the table owner.

---

## 11. Creating a Security-Invoker View and Testing Base Privileges

### 11.1. Creating an Invoker View on the Same Table

Run as the owner:

~~~sql
SET ROLE view_lab_owner;

CREATE VIEW view_lab.v_north_invoker
WITH (security_invoker = true)
AS
SELECT account_id, tenant_id, region, balance
FROM view_lab.accounts
WHERE region = 'north';

RESET ROLE;
~~~

### 11.2. Grant the View Without Granting the Base Table

~~~sql
GRANT SELECT ON view_lab.v_north_invoker TO view_lab_reader;
~~~

Test:

~~~sql
-- Test SEPARATELY: expected outcome is permission denied.
SET ROLE view_lab_reader;

SELECT account_id,tenant_id,region
FROM view_lab.v_north_invoker
ORDER BY account_id;

RESET ROLE;
~~~

The reader holds SELECT on the view yet **lacks SELECT on the base table**, so the security-invoker view fails the base relation privilege check. This is the sharp contrast with `v_north_default`.

### 11.3. Granting SELECT on Required Base Table Columns

~~~sql
GRANT SELECT (account_id, tenant_id, region, balance)
ON view_lab.accounts TO view_lab_reader;
~~~

Do not grant `internal_code`.

This grants SELECT on the columns used by the view, including `region` in the predicate; column-level SELECT does not let the reader query all columns of `accounts`.

### 11.4. Retrying the Invoker View

~~~sql
SET ROLE view_lab_reader;

SELECT account_id,tenant_id,region,balance
FROM view_lab.v_north_invoker
ORDER BY account_id;

RESET ROLE;
~~~

Expected result: **1, 5**.

Because:

- The view WHERE retains only `region = 'north'`.
- The RLS policy for `view_lab_reader` retains only `tenant_id = 10`.
- Both conditions combine: **region north AND tenant 10**.
- Row 2 (tenant 20, north) is filtered out by RLS.

### 11.5. Querying the Base Table Directly After Granting Columns

~~~sql
SET ROLE view_lab_reader;

SELECT account_id,tenant_id,region,balance
FROM view_lab.accounts
ORDER BY account_id;

RESET ROLE;
~~~

Expected per RLS: **1, 3, 5** (all regions for tenant 10).

Direct table access lacks the view's `region = 'north'` filter. A security-invoker view creates no new row isolation if the caller already has table access; **RLS on the table** is the tenant isolation boundary.

### 11.6. Attempting to Read an Ungranted Column

~~~sql
-- Test SEPARATELY: rejected by column privileges.
SET ROLE view_lab_reader;

SELECT internal_code
FROM view_lab.accounts;

RESET ROLE;
~~~

The reader was not granted SELECT on `internal_code`, so direct reads fail.

### 11.7. Comparison of Outcomes

| Access Path as `view_lab_reader` | Expected Result | Reason |
|---|---|---|
| `SELECT v_north_default` | 1, 2, 5 | Owner-mode view; owner bypasses RLS |
| `SELECT v_north_invoker` before base grant | Base table permission error | Invoker requires base privileges |
| `SELECT v_north_invoker` after column grant | 1, 5 | View WHERE + reader RLS |
| `SELECT accounts` after column grant | 1, 3, 5 | Reader RLS, without view WHERE |
| `SELECT internal_code FROM accounts` | Column permission error | Lacks SELECT grant on `internal_code` |

Expected outcomes assume a clean lab schema with no extra role memberships, policies, or grants.

---

## 12. Enabling Both security_invoker and security_barrier on One View

### 12.1. Creating a View with Both Options

~~~sql
SET ROLE view_lab_owner;

CREATE VIEW view_lab.v_north_secure
WITH (
    security_invoker = true,
    security_barrier = true
)
AS
SELECT account_id,tenant_id,region,balance
FROM view_lab.accounts
WHERE region='north';

RESET ROLE;

GRANT SELECT ON view_lab.v_north_secure TO view_lab_reader;
~~~

### 12.2. What Does the Caller See?

~~~sql
SET ROLE view_lab_reader;

SELECT account_id,tenant_id
FROM view_lab.v_north_secure
ORDER BY account_id;

RESET ROLE;
~~~

Expected: **1,5**.

Each option handles its own responsibility:

- `security_invoker=true`: enforces reader's base privileges and RLS.
- `security_barrier=true`: prevents external non-leakproof qualifiers from being pushed past internal view filters.

### 12.3. Altering Options on an Existing View

~~~sql
SET ROLE view_lab_owner;

ALTER VIEW view_lab.v_north_default
SET (security_barrier = true);

RESET ROLE;
~~~

This **does not** turn `v_north_default` into an invoker view. It still returns 1, 2, 5 in the lab due to owner identity, changing only how the optimizer handles external predicates.

To change both privilege mode and barrier:

~~~sql
ALTER VIEW view_lab.v_north_default
SET (security_invoker = true, security_barrier = true);
~~~

Run that final command **only after reviewing privilege/RLS impact**. To keep the lab's comparison outputs clear, keep `v_north_default` in owner mode and use `v_north_secure` as the dual-flag view rather than running every ALTER simultaneously.

---

## 13. Using security_barrier Against a Caller's Leaky Function

### 13.1. Experiment Goal

Suppose the view owner wants to expose `internal_code` only for **region north** accounts. A caller-supplied function in WHERE could throw an exception whenever it encounters a code starting with `S` (the region south rows in the lab).

We want to prevent users from exploiting optimizer **pushdown of a non-leakproof function ahead of the region filter** to probe values in hidden rows.

### 13.2. Creating an Intentionally "Leaky" Function in the Lab

Run as owner on the lab schema:

~~~sql
SET ROLE view_lab_owner;

CREATE FUNCTION view_lab.raise_if_south_code(p_code text)
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
AS $fn$
BEGIN
    IF left(p_code, 1) = 'S' THEN
        RAISE EXCEPTION 'A protected code reached the predicate';
    END IF;
    RETURN true;
END;
$fn$;

REVOKE ALL
ON FUNCTION view_lab.raise_if_south_code(text)
FROM PUBLIC;

GRANT EXECUTE
ON FUNCTION view_lab.raise_if_south_code(text)
TO view_lab_reader;

RESET ROLE;
~~~

This function **intentionally raises errors based on data** to demonstrate the threat model; do not ship functions like this in production. Production functions should return booleans cleanly without leaking data or sit behind proper security boundaries.

The function is not marked `LEAKPROOF`, and throwing data-dependent exceptions makes it **ineligible** to be considered leakproof.

### 13.3. Creating a View Protecting the Region Predicate

~~~sql
SET ROLE view_lab_owner;

CREATE VIEW view_lab.v_north_codes_barrier
WITH (security_barrier = true)
AS
SELECT account_id,region,internal_code
FROM view_lab.accounts
WHERE region='north';

RESET ROLE;

GRANT SELECT ON view_lab.v_north_codes_barrier
TO view_lab_reader;
~~~

This is an owner-mode + barrier view. The reader lacks direct SELECT on `internal_code` from the base table, yet is allowed to view it **through the view for north rows**. Use this pattern only when exposing north codes is explicitly permitted.

### 13.4. Caller Adds the Leaky Predicate

~~~sql
SET ROLE view_lab_reader;

SELECT account_id,internal_code
FROM view_lab.v_north_codes_barrier
WHERE view_lab.raise_if_south_code(internal_code)
ORDER BY account_id;

RESET ROLE;
~~~

Because the view has a security barrier and the caller's function is **non-leakproof**, PostgreSQL must not evaluate that function on rows filtered out by `region='north'` in a way that leaks south row codes.

On the sample dataset, the function will not raise an exception over south codes; expected output is account IDs **1,2,5** given the reader's grants.

### 13.5. Why Not Test by Removing the Barrier on Sensitive Data?

A view without a barrier gives the optimizer more freedom to reorder/push down qualifiers. There is **no guarantee** that simply removing the barrier on a small query will reproduce an error or leak across every PostgreSQL version and plan. Use `EXPLAIN` to inspect plans and follow safety rules rather than staging live leaks in production.

If the underlying data is genuinely sensitive, plan differences are sufficient to establish the need for a barrier without deploying secret-logging probe functions.

### 13.6. Barriers Do Not Protect Against Functions Inside the View Definition

A view owner can place function calls inside the view's own SELECT/WHERE; `security_barrier` does not "fix" a view whose own definition invokes buggy or leaky functions. Review the **view definition, function semantics, and owner privileges** together.

---

## 14. Query Plans and the Cost of security_barrier

### 14.1. Why Can a Barrier Slow Down Queries?

Normally, the planner can push caller predicates into a base table scan to use indexes and filter early. A security barrier restricts pushing non-leakproof expressions across the security boundary.

Example:

~~~sql
SELECT account_id,balance
FROM view_lab.v_north_codes_barrier
WHERE view_lab.raise_if_south_code(internal_code);
~~~

If a leaky function is expensive, it must execute only after the protective filter; this can change execution order and plan shape compared to an unbarriered view.

### 14.2. Comparing EXPLAIN on Safe SELECTs

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT account_id
FROM view_lab.v_north_default
WHERE account_id=1;
~~~

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT account_id
FROM view_lab.v_north_secure
WHERE account_id=1;
~~~

These two views have **different security properties**, so do not attribute timing differences solely to the barrier: RLS identity, row counts, and privileges also differ. To isolate barrier overhead, keep **the same privilege mode and SELECT definition** and vary only the barrier flag between two compared views.

### 14.3. Plans You May Encounter

A plan might show:

~~~text
Subquery Scan on v_secure
  Filter: (some_nonleakproof_condition(...))
  -> Seq Scan on accounts
       Filter: (region = 'north' ...)
~~~

or another structure depending on PostgreSQL version, statistics, indexes, and qualifiers. Never treat the presence or absence of "Subquery Scan" as a complete security test; view rewrite and optimizer plans have many variations.

### 14.4. Leakproof Predicates Can Still Push Down

Built-in operators marked leakproof can be pushed inside the barrier by the planner where valid. This allows certain **index conditions** to remain effective. Do not misinterpret `security_barrier` as "PostgreSQL always materializes the entire view before applying any outer WHERE."

### 14.5. Benchmark at Scale, Never Drop Barriers Just for Speed

When a view serves as a necessary security boundary, never disable the barrier simply because a single benchmark runs faster. Safer optimizations include:

- Creating indexes supporting the **view's internal predicates**.
- Narrowing columns and data crossing the boundary.
- Simplifying protective filter predicates while preserving semantics.
- Using built-in leakproof operators/functions instead of custom functions where business logic permits.
- Adjusting privilege/RLS models to reduce the need for view barriers where security design allows.
- Measuring key queries with `EXPLAIN (ANALYZE, BUFFERS)` on representative workloads.

**Never mark functions LEAKPROOF recklessly** to "win back performance," as mislabeling defeats the barrier.

### 14.6. Do Not Confuse Cost with Wall-Clock Time

`EXPLAIN` shows estimated `cost` in arbitrary units; `EXPLAIN ANALYZE` measures actual time in milliseconds. Never read `cost=500` as "the barrier costs 500 ms." Record Planning Time, Execution Time, buffers, rows, and loops in before/after benchmarks.

---

## 15. Function Privileges Are Separate from View Privileges

### 15.1. Functions Inside a View Do Not Grant EXECUTE Automatically

Suppose a view defines:

~~~sql
CREATE VIEW view_lab.v_masked_accounts AS
SELECT
    account_id,
    view_lab.mask_code(internal_code) AS masked_code
FROM view_lab.accounts
WHERE region='north';
~~~

This is an example view definition only; **`mask_code` has not been created**.

When a function appears inside a view, callers may still require `EXECUTE` on that function under function privilege rules. `SELECT` on a view is not a blanket grant to invoke every function referenced.

### 15.2. SECURITY INVOKER Functions and security_invoker Views Are Independent

By default, functions execute with the **caller's** privileges (`SECURITY INVOKER` on the function), not "automatically as the view owner" just because the view is in default-owner mode.

- Default-owner views determine relation checks for base relations referenced in the view.
- `SECURITY INVOKER` functions run with the caller's privileges.
- `SECURITY DEFINER` functions run with the function owner's privileges.
- `security_barrier` views restrict pushdown of external leaky quals.

Do not lump these into a single "runs as owner" mental model.

### 15.3. SECURITY DEFINER Functions Are Potential Privilege Escalation Paths

A `SECURITY DEFINER` function accesses data as its owner and can inadvertently return data the caller cannot read directly.

If unavoidable, you must:

1. Own it with a least-privilege role, not superuser unless required.
2. Pin a safe `search_path` and schema-qualify all object names.
3. Never build dynamic SQL from unvalidated input.
4. Revoke broad `EXECUTE` grants (functions often default to granting EXECUTE to PUBLIC).
5. Grant EXECUTE only to needed roles.
6. Audit RLS/BYPASSRLS and all tables/functions called inside.
7. Test for SQL injection, `search_path` object shadowing, and schema permissions.
8. Verify behavior when view owner, table owner, and caller are three distinct roles.

### 15.4. Watch Default EXECUTE Grants on Functions

Never assume a newly created function is "callable only by its owner." PostgreSQL has default EXECUTE privileges for functions. Review pattern:

~~~sql
REVOKE ALL
ON FUNCTION view_lab.raise_if_south_code(text)
FROM PUBLIC;

GRANT EXECUTE
ON FUNCTION view_lab.raise_if_south_code(text)
TO view_lab_reader;
~~~

If your environment uses `ALTER DEFAULT PRIVILEGES`, verify **the exact creating role and schema**; changing default privileges is not retroactive for existing functions.

### 15.5. RLS Policies Calling Functions Carry Their Own Privileges and Risks

A policy may invoke a function reading session identity or claims. The function runs under its own privilege context; querying users may need EXECUTE and underlying table permissions if the function is `SECURITY INVOKER`. Avoid policies calling unsafe functions or querying the protected table recursively.

### 15.6. Do Not Rely on Function Error Messages to Hide Data

Even on a barrier view, functions allowed to run on **exposed rows** can still raise exceptions revealing that row's contents. While that does not breach the barrier if those rows are already permitted, minimize sensitive info in logs and function side effects.

---

## 16. Nested Views: An Outer View Does Not Override Every Inner Layer

### 16.1. Views Can Reference Other Views

~~~text
Reader's SELECT
    |
    v
v_outer (security_invoker=true)
    |
    v
v_inner (security_invoker=false)
    |
    v
base_table (RLS enabled)
~~~

If `v_inner` remains in default owner mode, privileges/RLS identity when reading the base relation **through `v_inner`** still follow `v_inner`'s owner, even though `v_outer` is an invoker view.

Conversely, an inner security-invoker view causes its underlying base relations to be checked as the caller even when the outer view is not invoker. What matters is **each view layer and the path to each base relation**, not just a flag on the outermost view.

### 16.2. Extending the Lab: Outer Invoker → Inner Default

Keep `v_north_default` in owner mode (or with only `security_barrier`, not invoker).

~~~sql
SET ROLE view_lab_owner;

CREATE VIEW view_lab.v_outer_invoker
WITH (security_invoker = true)
AS
SELECT account_id,tenant_id
FROM view_lab.v_north_default;

RESET ROLE;

GRANT SELECT ON view_lab.v_outer_invoker TO view_lab_reader;
~~~

Test:

~~~sql
SET ROLE view_lab_reader;

SELECT account_id,tenant_id
FROM view_lab.v_outer_invoker
ORDER BY account_id;

RESET ROLE;
~~~

In the lab, because the reader holds `SELECT` on both `v_outer_invoker` and `v_north_default`, the path through the inner default view returns **1,2,5**—it does not narrow to 1,5 just because the outer view is invoker.

**If you ran `ALTER v_north_default SET (security_invoker=true)`** in another experiment, the outcome changes. Always inspect actual catalog options before interpreting results.

### 16.3. Outer Default → Inner Invoker

Reverse structure:

~~~sql
SET ROLE view_lab_owner;

CREATE VIEW view_lab.v_outer_default AS
SELECT account_id,tenant_id
FROM view_lab.v_north_invoker;

RESET ROLE;

GRANT SELECT ON view_lab.v_outer_default TO view_lab_reader;
~~~

`v_north_invoker` remains a security-invoker view, so base relations accessed through it use the caller's privileges and RLS identity per invoker rules, even though the outer view is owner mode. With column grants on the reader, expected output is **1,5**.

Never guess behavior for complex nested trees from just two examples; when a view references multiple views, tables, and functions with mixed modes, **diagram the dependency graph and audit every edge**.

### 16.4. SELECT Privileges on Intermediate Views

When querying a view through another view, privilege checks on intermediate views follow their respective owner/invoker rules. In the outer-invoker example, the reader needed SELECT on the inner default view. Removing that grant blocks the query; SELECT on the outer view does not bypass intermediate invoker checks.

Good rule: **never use nested views to mask missing privileges**, and always test as the real role through the exact view tree.

### 16.5. Nested View Analysis Table

| Path to Base Relation | Privilege/RLS Identity Reading Base Table |
|---|---|
| Direct table access | Caller, per caller's grants and RLS |
| Default-owner view → table | Owner of the default-owner view |
| Security-invoker view → table | Caller |
| Outer invoker → inner owner-mode → table | Owner of the inner owner-mode view |
| Outer owner-mode → inner invoker → table | Caller per inner invoker rule |

This table models **base relation identity**; it does not imply privileges on intermediate views and functions are granted automatically.

---

## 17. Inspecting Security Properties from Catalogs

### 17.1. pg_class.reloptions

View options like `security_invoker=true` and `security_barrier=true` are stored in relation options.

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS view_name,
    pg_get_userbyid(c.relowner) AS view_owner,
    c.reloptions
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid=c.relnamespace
WHERE n.nspname='view_lab'
  AND c.relkind='v'
ORDER BY c.relname;
~~~

A view might show:

~~~text
{security_invoker=true,security_barrier=true}
~~~

If `reloptions` is NULL, do not assume security flags are enabled: defaults are `security_invoker=false` and `security_barrier=false`.

### 17.2. Expanding reloptions into Key/Value Rows

~~~sql
SELECT
    n.nspname,
    c.relname,
    opt.option_name,
    opt.option_value
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid=c.relnamespace
CROSS JOIN LATERAL pg_options_to_table(c.reloptions) AS opt
WHERE n.nspname='view_lab'
  AND c.relkind='v'
ORDER BY c.relname,opt.option_name;
~~~

This query lists only **explicitly set** options; absent flags simply indicate default values, not external policy overrides.

### 17.3. Inspecting View SQL

~~~sql
SELECT pg_get_viewdef(
    'view_lab.v_north_secure'::regclass,
    true
) AS definition;
~~~

Inspect WHERE, JOINs, function calls, computed columns, LIMIT/aggregates, and base relations. Never check only flags while ignoring what data the view actually selects.

### 17.4. information_schema.views / pg_views

~~~sql
SELECT schemaname,viewname,viewowner,definition
FROM pg_views
WHERE schemaname='view_lab'
ORDER BY viewname;
~~~

Catalog views return definitions; to verify `security_invoker`/`security_barrier`, query `pg_class.reloptions` as shown above. Do not assume the SQL view definition text includes ownership, grants, or RLS.

### 17.5. Checking Grants with has_*_privilege

~~~sql
SELECT
    has_schema_privilege(
        'view_lab_reader','view_lab','USAGE'
    ) AS reader_has_schema_usage,
    has_table_privilege(
        'view_lab_reader','view_lab.v_north_default','SELECT'
    ) AS reader_can_select_default_view,
    has_table_privilege(
        'view_lab_reader','view_lab.v_north_invoker','SELECT'
    ) AS reader_can_select_invoker_view,
    has_column_privilege(
        'view_lab_reader','view_lab.accounts','balance','SELECT'
    ) AS reader_can_select_balance,
    has_column_privilege(
        'view_lab_reader','view_lab.accounts','internal_code','SELECT'
    ) AS reader_can_select_internal_code;
~~~

These functions inspect **privileges**, not **RLS result sets** or security barriers.

### 17.6. Inspecting RLS Policies

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
WHERE schemaname='view_lab'
ORDER BY tablename,policyname;
~~~

Review every policy expression alongside role memberships, ownership, BYPASSRLS, and target SQL commands.

### 17.7. Table RLS Flags

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    pg_get_userbyid(c.relowner) AS table_owner,
    c.relrowsecurity AS rls_enabled,
    c.relforcerowsecurity AS force_rls
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid=c.relnamespace
WHERE n.nspname='view_lab'
  AND c.relname='accounts';
~~~

RLS enabled alone does not prove every caller is filtered: check owner bypass and `rolbypassrls`.

### 17.8. Checking BYPASSRLS

~~~sql
SELECT rolname,rolsuper,rolbypassrls,rolcanlogin
FROM pg_roles
WHERE rolname IN ('view_lab_owner','view_lab_reader')
ORDER BY rolname;
~~~

Only privileged administrators should configure special role attributes. Never toggle `BYPASSRLS` casually to test a policy without proper authorization and an isolated environment.

---

## 18. Diagnosing "permission denied" Step by Step

An application reports:

~~~text
ERROR: permission denied for table accounts
~~~

while the DBA says "I already ran GRANT SELECT on the view." Check in order:

1. Does the view have `security_invoker=true`?
2. Which role is actually running the query (`current_user`, pool role, `SET ROLE`, memberships)?
3. Does the role have `USAGE` on the view schema and `SELECT` on the view?
4. If invoker, does the role hold SELECT on the required base table columns?
5. Does the view reference **nested invoker views** or functions needing EXECUTE?
6. Does the table have RLS? Permission denied errors differ from queries returning **0 rows** due to RLS deny.
7. Is `FORCE ROW LEVEL SECURITY` enabled while the owner lacks a policy?
8. Are default privileges, role memberships, `PUBLIC` grants, or REVOKEs involved?
9. Is the app hitting the right database, schema, and `search_path`, or an identically named view with a different owner?
10. Did a migration ALTER VIEW or change ownership, altering effective identity?

### 18.1. Schema Privileges vs. Table Privileges

An error:

~~~text
ERROR: permission denied for schema view_lab
~~~

usually indicates missing `USAGE` on the view's schema. Do not fix a missing schema grant by granting base table SELECT or disabling `security_invoker`.

### 18.2. Returning 0 Rows Is Not Permission Denied

If the reader holds relation privileges yet policy predicates reject rows, SELECT succeeds with an empty result set. Distinguish:

- **Access denied:** PostgreSQL raises a privilege error.
- **RLS deny:** query succeeds, rows filtered out (depending on command/policy).
- **View WHERE:** rows filtered out by the view's own predicate.
- **Empty table:** no data exists.
- **Join/filter logic:** query naturally matches zero rows.

### 18.3. Missing Column Privileges

A security-invoker view might SELECT or filter on a column the caller was not granted. Errors occur even if the caller's outer query selects only a subset of view columns; effective privilege checks cover all base columns and expressions referenced by the view.

Never grant `SELECT ON ALL TABLES IN SCHEMA ...` to work around a missing column grant when only four columns of one table are needed: grant the minimum required.

---

## 19. Read Privilege Does Not Automatically Allow View UPDATE

### 19.1. Some Views Are Automatically Updatable

A **simple view** over a single table can accept `INSERT`, `UPDATE`, and `DELETE` when PostgreSQL qualifies it as automatically updatable. Views with joins, DISTINCT, GROUP BY, aggregates, or complex clauses generally do not auto-update; they may require triggers/rules.

### 19.2. Write Privileges Are Separate

`GRANT SELECT ON view` does not grant `UPDATE` or `INSERT`.

On a security-invoker view, write privileges on base relations must be granted to the caller for rewritten DML; RLS policies `FOR UPDATE`, `FOR INSERT`, and `FOR DELETE` govern target rows and new values.

### 19.3. WITH CHECK OPTION Differs from security_barrier

If a view permits UPDATEs and must ensure rows **still match the view's WHERE after INSERT/UPDATE**, use `WITH CHECK OPTION` where supported.

~~~sql
CREATE VIEW some_schema.v_tenant10
WITH (security_invoker = true)
AS
SELECT id,tenant_id,description
FROM some_schema.tasks
WHERE tenant_id=10
WITH LOCAL CHECK OPTION;
~~~

This syntax example assumes `some_schema.tasks` exists. `WITH CHECK OPTION` validates whether **newly written rows** stay visible in the view per its predicate; it is **not** `security_barrier` and does not replace grants or RLS.

### 19.4. Small Lab with DML and RLS

Create a separate tasks table as owner:

~~~sql
SET ROLE view_lab_owner;

CREATE TABLE view_lab.tasks (
    task_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'open'
);

INSERT INTO view_lab.tasks(task_id,tenant_id,title,state)
VALUES
    (1,10,'Prepare report','open'),
    (2,20,'Inspect operations','open');

ALTER TABLE view_lab.tasks ENABLE ROW LEVEL SECURITY;

CREATE POLICY tasks_reader_select
ON view_lab.tasks
FOR SELECT
TO view_lab_reader
USING (tenant_id=10);

CREATE POLICY tasks_reader_update
ON view_lab.tasks
FOR UPDATE
TO view_lab_reader
USING (tenant_id=10)
WITH CHECK (tenant_id=10);

CREATE VIEW view_lab.v_tenant10_tasks
WITH (security_invoker=true)
AS
SELECT task_id,tenant_id,title,state
FROM view_lab.tasks
WHERE tenant_id=10
WITH LOCAL CHECK OPTION;

RESET ROLE;
~~~

Grant **least-privilege** permissions to reader:

~~~sql
GRANT SELECT(task_id,tenant_id,title,state)
ON view_lab.tasks TO view_lab_reader;

GRANT UPDATE(state)
ON view_lab.tasks TO view_lab_reader;

GRANT SELECT
ON view_lab.v_tenant10_tasks TO view_lab_reader;

GRANT UPDATE(state)
ON view_lab.v_tenant10_tasks TO view_lab_reader;
~~~

Test UPDATE in a lab transaction:

~~~sql
SET ROLE view_lab_reader;

BEGIN;

UPDATE view_lab.v_tenant10_tasks
SET state='closed'
WHERE task_id=1
RETURNING task_id,tenant_id,title,state;

ROLLBACK;

RESET ROLE;
~~~

In the lab, this UPDATE affects only tenant 10's task, and ROLLBACK restores initial data. To check whether `tenant_id` can be modified, inspect **column UPDATE grants**, `WITH CHECK OPTION`, and **RLS WITH CHECK**; a single view flag never tells the whole story.

### 19.5. RLS USING and WITH CHECK

- `USING` governs which existing rows are visible/targetable before the operation, per policy type.
- `WITH CHECK` validates new row values during INSERT/UPDATE.

An UPDATE through a security-invoker view must satisfy both base privileges and RLS policies. `WITH CHECK OPTION` on the view validates the view's predicate on the new row; all layers interact.

### 19.6. Triggers and Rules Change the Picture

If a view uses `INSTEAD OF` triggers or rules, DML runs differently from automatically updatable views. Audit trigger function privileges (`SECURITY INVOKER/DEFINER`), target base tables, and custom code. Never assume `security_invoker` alone governs custom trigger DML.

---

## 20. Role Membership, Inherited Privileges, and PUBLIC

### 20.1. Privileges Can Come from Role Membership

A user might hold no direct grants yet inherit privileges through a parent role membership, per PostgreSQL inheritance/`SET ROLE` rules.

Thus if:

~~~sql
SELECT has_table_privilege(
  'view_lab_reader',
  'view_lab.v_north_default',
  'SELECT'
);
~~~

returns true, you cannot conclude a direct `GRANT SELECT` was issued to `view_lab_reader`; the privilege could come from membership or `PUBLIC`. Inspect ACLs and role memberships.

### 20.2. Grants to PUBLIC Have Broad Scope

~~~sql
GRANT SELECT ON view_lab.v_north_default TO PUBLIC;
~~~

Never run this in the lab if only `view_lab_reader` should read the view. `PUBLIC` includes all current and future roles, so accidental PUBLIC grants expose data broadly.

### 20.3. ALTER DEFAULT PRIVILEGES

Default privileges affect newly created views, tables, and functions. Do not confuse:

- `GRANT SELECT ON view_lab.v_north_default TO reader`: applies to one existing view.
- `ALTER DEFAULT PRIVILEGES ... GRANT SELECT ON TABLES TO reader`: applies to objects created **in the future** by the specified creator role.

Default privileges do not retroactively alter grants on existing views.

### 20.4. REVOKE Is Not Always Enough If Other Paths Exist

If a role still has SELECT via `PUBLIC` or another role membership, `REVOKE SELECT ON ... FROM reader` will not remove effective access. Verify effective ACLs, memberships, and test directly as the role.

### 20.5. Owner Privileges Are Special

Object owners retain authority to alter or drop their objects under ownership rules; plain GRANT/REVOKE does not strip an owner's administrative powers. Use dedicated owner roles and restrict who can `SET ROLE` into them.

---

## 21. Changing View or Table Ownership Can Alter Visible Data

### 21.1. Changing a Default View's Owner

~~~sql
-- Syntax form; do not run directly in production:
ALTER VIEW view_lab.v_north_default OWNER TO another_role;
~~~

When `security_invoker=false`, the new owner brings different base privileges and RLS identity. Ownership changes can cause a view to:

- Lose base table read access due to missing grants.
- Return fewer rows due to RLS.
- Return more rows if the new owner has `BYPASSRLS`.
- Invoke functions with different owner/privilege side effects.

Never treat an ownership change as harmless metadata housekeeping.

### 21.2. Changing the Base Table's Owner

If the base table owner changes, the role eligible for owner-level RLS exemption changes too. A view owner that previously matched the table owner may stop bypassing RLS.

### 21.3. FORCE ROW LEVEL SECURITY

Enabling FORCE RLS makes owner-mode views stricter, yet can also cause apps to see **0 rows** if policies for the owner were never written. Never treat FORCE as a "turn on to make all accounts safe" switch if superusers, `BYPASSRLS`, or weak policies remain.

### 21.4. search_path Changes and Object Resolution

View definitions store bound references to relation objects in PostgreSQL metadata, whereas SQL functions, dynamic SQL, `SECURITY DEFINER` functions, and view creation/replacement scripts face `search_path` risks when using unqualified names.

Always schema-qualify references in sensitive definitions and pin a safe `search_path` on `SECURITY DEFINER` functions.

---

## 22. True Row Isolation: View Filters or RLS Policies?

### 22.1. When Is a View WHERE Sufficient?

If applications only access a reporting view and have zero alternate paths to the base table, an owner-mode view with a fixed filter plus `security_barrier` can provide a useful restricted interface.

Still verify:

- Callers hold no base table SELECT through any other role.
- The view owner holds only necessary privileges, not excessive ones.
- The filter predicate cannot be bypassed via other views or functions.
- Exposed columns in the SELECT list match the contract.
- A barrier is enabled if the threat model includes external leaky function qualifiers.

### 22.2. When Is RLS a Better Fit?

When many tables, views, and queries share a per-user/per-tenant isolation rule, **base table RLS** is a stronger centralized control. Security-invoker views ensure views respect caller RLS identity instead of overriding it with owner privileges.

Audit RLS carefully for:

- Policies per role and operation.
- `USING` vs. `WITH CHECK`.
- SELECT/INSERT/UPDATE/DELETE grants.
- Owner/BYPASSRLS and FORCE flags.
- Connection pool role identity.
- How tenant/user identity is propagated and protected against spoofing.

### 22.3. When to Combine Views and RLS?

For example:

- RLS ensures callers see only permitted tenants.
- Views expose only needed reporting columns/fields.
- `security_invoker=true` prevents owner privilege escalation over caller RLS.
- `security_barrier=true` protects sensitive view-level row restrictions when the threat model demands it.

This provides **defense in depth**, though it never eliminates the need to verify every layer.

### 22.4. Do Not Use Static View Filters When Callers Need Per-User Policies

A view with `WHERE tenant_id=10` works only for tenant 10, not for a 10,000-tenant SaaS where each caller needs distinct isolation. Use RLS tied to authenticated identity paired with invoker views or role isolation.

### 22.5. Application Connection Pool Privilege Model

If every HTTP request executes under **one shared database role** with broad SELECT and a single `TO app_role` policy, PostgreSQL cannot tell two application end-users apart. Design secure identity propagation (role switching, trusted session context, or equivalent) and reset session state whenever pooled connections are reused.

**`security_invoker` sees only the executing database role**—it has no automatic awareness of JWTs or application user IDs without proper authentication and context mapping.

---

## 23. Testing Privileges and Data: Minimum Test Matrix

Never test security views solely as the owner or superuser. Include representative caller roles.

| Test | View / Action | Expected Outcome |
|---|---|---|
| 1 | Reader SELECT owner-mode view without base SELECT | Succeeds if granted view/schema access |
| 2 | Reader SELECT base table without GRANT | Permission denied |
| 3 | Reader SELECT invoker view without base SELECT | Permission denied |
| 4 | Reader SELECT invoker after base column GRANT | Succeeds; RLS applied as reader |
| 5 | Reader SELECT default view with owner bypassing RLS | Can see tenant 20 rows if view WHERE allows |
| 6 | Reader SELECT invoker with tenant 10 RLS | Only tenant 10 |
| 7 | Reader SELECT `internal_code` directly without column grant | Permission denied |
| 8 | Reader SELECT barrier view + leaky function | Function never receives filtered-out rows per barrier rules |
| 9 | Reader SELECT outer invoker → inner owner-mode | Must check inner identity, not just outer |
| 10 | Reader UPDATE view without UPDATE grant | Permission denied |
| 11 | Reader UPDATE invoker view with grant but blocked by RLS | Denied rows untouched; CHECK error if new row violates policy |
| 12 | View grant REVOKEd while PUBLIC/membership grant exists | Check effective privilege, don't infer from one REVOKE |
| 13 | View owner changed to lower-privilege role | May lose base access or change visible row set |
| 14 | FORCE RLS on base table | Owner loses default owner exemption |
| 15 | View lacks `security_barrier`, caller passes non-leakproof function | Evaluation-order leak risk; one safe plan proves nothing |
| 16 | Queries via shared connection pool role | Policies enforce database role, not separate app users |

### 23.1. Verify the Effective Identity

Inside a test session:

~~~sql
SELECT current_user,session_user;
~~~

When using `SET ROLE`, inspect both values. In applications, verify the actual PostgreSQL role running SQL queries. A username in HTTP logs does not necessarily match the database role.

### 23.2. Include Negative Cases

Strong security tests prove not only "User A can read row A," but also:

- User A **cannot** read tenant B's data.
- User A **cannot** read base tables directly beyond intent.
- Outer queries cannot probe hidden rows via function evaluation when a barrier is required.
- User A cannot UPDATE/INSERT past check options or RLS policies.
- Role B or roles with inherited memberships do not accidentally gain unintended access paths.

### 23.3. Distinguish Privilege Tests from Data Tests

A query returning 0 rows may simply reflect an empty table or a filter predicate, not blocked privileges. Seed test data with **at least two tenants and multiple regions** to produce unambiguous positive and negative evidence, as in the accounts lab.

---

## 24. Migrating from Default Views to security_invoker

### 24.1. Why Can Flipping the Flag Cause Outages?

Suppose an API queries a default view with SELECT on the view and no base SELECT, and a DBA runs:

~~~sql
ALTER VIEW reporting.v_paid_payments
SET (security_invoker=true);
~~~

The API immediately fails with `permission denied for table payments`. If the DBA reacts by running `GRANT SELECT` on the entire base table as a "quick fix," sensitive columns and rows become directly queryable outside the view.

### 24.2. Controlled Migration Process

1. Inventory all caller roles and services depending on the view.
2. Confirm PostgreSQL major version supports invoker views (15+).
3. Audit view definition, nested views, functions, owner, and base table RLS.
4. Identify exact base columns/relations callers will require.
5. Evaluate whether callers could query the base table directly once granted, and whether RLS restricts scope appropriately.
6. Create a **staging candidate view** or parallel view with the flag enabled.
7. Run positive, negative, and edge-case access tests under each representative role.
8. Compare **exact row sets** before and after, not just row counts and timings.
9. Review `EXPLAIN` plans if `security_barrier` or RLS predicates change.
10. Roll out grants, policies, and the flag with an explicit rollback plan.
11. Monitor for permission denied errors and unexpected 0-row queries.
12. Retire old views/grants only after all consumers migrate and auditing finishes.

### 24.3. Never Treat Full-Table GRANT SELECT as the Default Fix

If the original goal was to **hide unauthorized rows**, switching to a security-invoker view requiring base table grants creates a conflict unless RLS enforces row scope. In many reporting cases, a tightly controlled default-owner view + `security_barrier` + zero base grants for readers is the better architecture.

Never enable `security_invoker` solely because "security" is in its name.

### 24.4. Review CREATE OR REPLACE VIEW Too

A migration modifying SELECT lists, WHERE clauses, JOINs, function calls, or view options can expand data exposure without changing the view name. Review diffs of view definitions and dependent privileges rather than merely confirming DDL succeeded.

### 24.5. Measure Performance When Changing Security Settings

RLS policies inject predicates that change row estimates, join orders, and index choices. Security barriers constrain pushdown. A successful migration requires both:

- **Correct privileges and row isolation.**
- **Acceptable workload performance**, or a documented mitigation plan.

---

## 25. Auditing Access and Configuration Changes

### 25.1. Metadata for Periodic Audits

A periodic security report should list:

- View owners.
- `security_invoker` / `security_barrier` flags.
- Base relation and nested view dependencies.
- `GRANT`s on views.
- RLS status on underlying tables.
- RLS policies and target roles.
- Any `SECURITY DEFINER` functions along sensitive paths.

### 25.2. Auditing Privilege Changes

Operations worth flagging in change review:

~~~text
GRANT / REVOKE on views and base tables
ALTER VIEW ... SET (security_invoker / security_barrier)
ALTER VIEW ... OWNER TO
CREATE OR REPLACE VIEW
ALTER TABLE ... ENABLE/DISABLE/FORCE ROW LEVEL SECURITY
CREATE/ALTER/DROP POLICY
ALTER ROLE ... BYPASSRLS
CREATE/ALTER FUNCTION ... SECURITY DEFINER / LEAKPROOF
ALTER DEFAULT PRIVILEGES
~~~

A small change at one layer can shift effective access across nested views.

### 25.3. PostgreSQL Logs and Connection Monitoring

Use approved logging/audit extensions and operational tooling to track privilege and DDL changes. When logging SQL, view definitions, or errors, redact sensitive literals and parameters. Do not grant broad read access to system catalogs or query logs to unprivileged roles.

### 25.4. Views Do Not Replace Data Backups or Auditing

When a view exposes customer data, `security_barrier` and `security_invoker` do not solve data retention, backups, encryption, external masking, or DBA access governance. Coordinate controls across all layers.

---

## 26. Design Scenario 1: Cross-Department Reporting View

### 26.1. Context

`finance.payments` belongs to the finance team. The analytics team needs to read settled payments (`payment_id`, `customer_id`, `amount`), but must never see bank account numbers or unsettled/failed statuses.

Goal: consumers must **not hold direct SELECT privileges** on the finance table.

### 26.2. Suitable Design Pattern

~~~sql
-- Executed by an owner role with SELECT on the needed columns:
CREATE VIEW reporting.v_paid_payments
WITH (security_barrier = true)
AS
SELECT payment_id, customer_id, amount
FROM finance.payments
WHERE status='paid';

GRANT USAGE ON SCHEMA reporting TO analysis_reader;
GRANT SELECT ON reporting.v_paid_payments TO analysis_reader;
~~~

Here **default owner mode** lets callers read the view without base table SELECT grants. `security_barrier` is warranted if `status='paid'` is a security boundary users must not probe past using leaky quals.

### 26.3. Mandatory Review Questions

- Does the view owner have finance read access while **not being a superuser**?
- Does `analysis_reader` hold SELECT on `finance.payments` via any other role?
- Does another view expose unpaid records?
- Can functions inside the view leak data or cause side effects?
- Is `status='paid'` accurate for business rules (refunds/cancellations/taxes)?
- Is altering/replacing the view restricted strictly to authorized maintainers?

### 26.4. Why Might security_invoker Be Unsuitable Here?

With invoker enabled, `analysis_reader` needs base relation privileges. Without RLS protecting finance rows, granting base table SELECT lets them query non-`paid` rows directly. When the goal is **no base table access**, a tightly governed default-owner view is often a better fit.

### 26.5. Barriers Do Not Hide Selected Columns

If a view accidentally selects `bank_account_number`, a barrier will not hide that column from callers holding SELECT on the view. **An accurate SELECT list and least privilege** always come first.

---

## 27. Design Scenario 2: Multi-Tenant SaaS with RLS

### 27.1. Context

An application serves many tenants. PostgreSQL RLS on base tables enforces row isolation per database identity (or trusted authenticated tenant context).

The team wants views to simplify SELECTs and reporting without letting a view owner bypass caller RLS.

### 27.2. Illustrative Design

~~~sql
CREATE VIEW api.v_active_orders
WITH (security_invoker=true)
AS
SELECT order_id, tenant_id, total_amount
FROM app.orders
WHERE status='active';
~~~

In a real system, `app.orders` requires proper RLS policies, table grants, and identity propagation; the snippet above covers only the view definition.

### 27.3. When to Add security_barrier?

If the view includes an internal protective condition vulnerable to probing via external leaky qualifications during optimizer reordering, consider:

~~~sql
ALTER VIEW api.v_active_orders
SET (security_barrier=true);
~~~

Still, underlying RLS remains the primary tenant isolation boundary. A barrier does not authenticate tenants.

### 27.4. Connection Pool Risks

If every request runs under one shared `app_runtime` database role and RLS reads a client-writable GUC, `security_invoker` cannot distinguish user A from user B. You need secure authentication, application authorization, and validated session state cleanup.

### 27.5. Testing

- Queries from Tenant A return only A.
- Queries from Tenant B return only B.
- Users lacking base column SELECT fail with permission denied.
- Overprivileged roles are never used for routine traffic.
- Pooled connection reuse never leaks tenant context across requests.
- Nested owner-mode views are audited to prevent accidental RLS bypass.

---

## 28. Design Scenario 3: Sensitive View with User-Supplied Filter Functions

### 28.1. Context

A public view exposes only `is_public=true` events. Callers can attach custom WHERE predicates, including functions with side effects or data-dependent errors.

### 28.2. Design Requiring security_barrier

~~~sql
CREATE VIEW public_api.v_public_events
WITH (security_barrier=true)
AS
SELECT event_id, code, created_at
FROM app.events
WHERE is_public=true;
~~~

Purpose of the barrier: prevent **external non-leakproof qualifiers** from being optimized to run before the view's protective condition and leaking non-public rows.

### 28.3. Additional Requirements

- Callers have no direct SELECT on `app.events` unless authorized.
- The `code` column is intentionally public **for public rows**.
- The view owner holds minimal necessary privileges.
- Functions inside the view are security-reviewed.
- Roles allowed to CREATE FUNCTION cannot mark functions `LEAKPROOF`.
- Error logs and timing side channels are monitored per the threat model.

### 28.4. Performance Impact

An outer predicate calling a non-leakproof function may execute after the protective filter, blocking some index pushdowns. Benchmark and add indexes supporting internal view predicates rather than disabling the barrier to "force an index" when it guards real sensitive data.

---

## 29. Flowchart for Choosing View Security Mode

~~~mermaid
flowchart TD
    A["Design view for application"] --> B{"Should caller have base table privileges?"}
    B -- "No" --> C["Default owner-mode view"]
    B -- "Yes, per grants/RLS" --> D["security_invoker=true; PostgreSQL 15+"]
    C --> E{"Is view WHERE a boundary for sensitive rows?"}
    D --> F{"Need to block external leaky quals bypassing filter?"}
    E -- "Yes" --> G["security_barrier=true"]
    E -- "No" --> H["Review predicate, columns, owner grants"]
    F -- "Yes" --> G
    F -- "No" --> H
    G --> I["Review function EXECUTE and LEAKPROOF"]
    H --> I
    I --> J{"Is base RLS/owner/BYPASSRLS identity right?"}
    J -- "Not yet" --> K["Fix role/policy/grants; do not deploy"]
    J -- "Yes" --> L["Test with real roles and negative cases"]
    K --> L
    L --> M["EXPLAIN, benchmark, migration + monitoring"]
~~~

### 29.1. Four Common Combinations

| `security_invoker` | `security_barrier` | Primary Meaning |
|---|---|---|
| false | false | Standard view: base privileges/RLS evaluated as owner, full optimizer flexibility |
| false | true | Owner-mode privileges on base tables, with a barrier against external leaky quals |
| true | false | Caller's privileges/RLS enforced, without an extra barrier for external quals |
| true | true | Caller's privileges/RLS enforced **and** security barrier enabled |

No combination solves every problem on its own: **role grants, RLS policies, SELECT lists, function privileges, and ownership controls** remain mandatory.

---

## 30. Common Misconceptions and Misconfigurations to Avoid

| Misconception / Error | Why It Is Wrong | How to Handle |
|---|---|---|
| "Views default to using the caller's privileges on base tables" | Default uses the view owner's privileges | Check `security_invoker` |
| "GRANT SELECT on a view also grants SELECT on base tables" | Two distinct ACLs | Verify grants on each relation |
| "Callers need USAGE on all base schemas for a default view" | Default views access indirectly via owner | Distinguish view schema vs. base relation checks |
| "SELECT on the view is enough even with invoker=true" | Invoker requires base privileges | Grant least privilege or switch mode |
| "security_invoker grants table privileges to callers" | Changes check identity, does not grant rights | Audit RLS and base privileges |
| "security_invoker filters tenant_id automatically" | Adds no WHERE or policy | Implement RLS/tenant policies |
| "RLS always enforces caller policies through any view" | Default owner-mode uses owner identity | Check owner bypass and invoker |
| "Table owners are always subject to RLS" | Owners bypass unless FORCE RLS | Inspect `relforcerowsecurity` |
| "FORCE RLS blocks superusers/BYPASSRLS" | Privilege-based bypasses still apply | Restrict roles and test realistically |
| "A SELECT policy grants SELECT privilege" | Policies and GRANTs are separate layers | Configure both properly |
| "security_barrier changes owner privilege checks" | Barrier does not alter owner/invoker mode | Set the right flags per requirement |
| "security_barrier blocks all predicate pushdown" | Leakproof quals are an exception | Understand LEAKPROOF and inspect EXPLAIN |
| "Writing WHERE A AND B ensures A runs first" | SQL planner can reorder predicates | Use proper security boundaries |
| "Removing a barrier always leaks in every test" | Depends on optimizer and data | Test the threat model, not one plan |
| "A barrier blocks all side channels" | Addresses only evaluation-order leakage | Apply defense in depth |
| "Callers blocked from tables can't abuse functions" | Function EXECUTE has its own ACL | Audit function grants |
| "Functions inside a view run as the view owner" | Function SECURITY INVOKER/DEFINER is independent | Inspect function definitions |
| "SECURITY DEFINER is safe by default" | Risks `search_path`/dynamic SQL/bypass | Least privilege, REVOKE PUBLIC |
| "LEAKPROOF is just a performance hint" | Mislabeling breaks security barriers | Reserve strictly for truly leakproof functions |
| "An outer invoker view makes inner views invoker" | Inner owner-mode views keep their own semantics | Trace the full dependency graph |
| "GRANT SELECT on the whole table is the best invoker fix" | Opens direct reads outside the view | Use column grants + RLS or owner mode |
| "SELECT returning 0 rows means permission denied" | Can be RLS or view WHERE | Distinguish errors from empty results |
| "View SELECT grant allows UPDATE on the view" | DML requires separate privileges | Grant UPDATE/INSERT explicitly |
| "security_barrier is the same as WITH CHECK OPTION" | One governs evaluation order, the other DML row checks | Apply each for its own purpose |
| "Updating an invoker view needs no base grants/policies" | Invoker checks base privileges and policies | Review UPDATE/USING/WITH CHECK |
| "One direct REVOKE guarantees zero access" | PUBLIC/role memberships may remain | Verify effective ACLs |
| "Changing owner only changes metadata" | Base access and RLS identity can shift | Security review + regression tests |
| "Views are always as fast as direct SELECTs" | Barriers/RLS/rewrites can alter plans | Run EXPLAIN and benchmarks |
| "A view is a security boundary even when callers have base SELECT" | Direct table path bypasses the view | Revoke direct grants / enforce RLS |
| "One shared database role distinguishes HTTP users" | PostgreSQL only sees DB identity/trusted context | Propagate identity securely |
| "CREATE OR REPLACE does not affect security" | Definitions, functions, rows, and columns can change | Review diffs and re-test |
| "Testing as superuser is sufficient" | Superuser bypasses checks and RLS | Test as actual caller roles |

---

## 31. Checklist Before Granting Access to a Sensitive View

### 31.1. Definition and Ownership

- [ ] View SELECT list exposes only permitted columns.
- [ ] WHERE/JOIN accurately reflects row-level business rules.
- [ ] View owner is a least-privilege role, not superuser unnecessarily.
- [ ] Only authorized maintainers can ALTER VIEW/OWNER/REPLACE.
- [ ] PostgreSQL major version has been verified.
- [ ] `security_invoker` and `security_barrier` verified in catalogs.

### 31.2. Access Privileges

- [ ] Caller has `USAGE` on the view's schema.
- [ ] Caller has only needed `SELECT/INSERT/UPDATE/DELETE` on the view.
- [ ] If invoker, caller holds needed base-table/column privileges.
- [ ] No accidental direct SELECT on sensitive tables via memberships or PUBLIC.
- [ ] Function `EXECUTE` grants audited.
- [ ] `SECURITY DEFINER` functions and `search_path` audited.

### 31.3. RLS

- [ ] Base tables have `ENABLE ROW LEVEL SECURITY` where required.
- [ ] Policies match intended roles and operations.
- [ ] RLS owner bypass behavior accounted for.
- [ ] Evaluated whether `FORCE ROW LEVEL SECURITY` is needed.
- [ ] Verified whether owner or caller has `BYPASSRLS` or superuser.
- [ ] Tenant identity is authenticated and cannot be spoofed via SET.
- [ ] Connection pool reset / role switching handled safely.

### 31.4. Barriers and Performance

- [ ] Determined whether view WHERE is a security boundary or ordinary filter.
- [ ] Checked threat model for external user-defined/leaky expressions.
- [ ] Enabled `security_barrier=true` where needed.
- [ ] `LEAKPROOF` never applied recklessly.
- [ ] Plans compared on representative data and caller roles.
- [ ] Planning Time, Execution Time, and BUFFERS measured.
- [ ] Barriers never removed solely for speed without equivalent protection.

### 31.5. Deployment and Testing

- [ ] Tests verify **permitted rows** are readable and **forbidden rows** are hidden.
- [ ] Tests verify privilege errors when grants are missing.
- [ ] Nested views and function calls tested.
- [ ] UPDATE/INSERT/CHECK OPTION tested if writable.
- [ ] Rollback plan prepared for ALTER VIEW/GRANT/RLS changes.
- [ ] Logging/auditing enabled without exposing sensitive row data.

---

## 32. Practice Exercises

Exercises use the `view_lab` lab unless noted otherwise. Run error-inducing statements **separately**; PostgreSQL clients may abort subsequent statements after an error. Execute privilege commands in a test instance, never casually on production.

### Exercise 1 — Direct Access vs. View Access

A reader has `USAGE` on the view schema and `SELECT` on the view, but no SELECT on the base table. Can the reader query a default-owner view? Can they query the base table directly?

### Exercise 2 — Who Owns the View?

Write SQL to inspect the owner of `view_lab.v_north_default` from `pg_class` and `pg_namespace`.

### Exercise 3 — Creating a Default View

Write SQL creating `view_lab.v_north_2` returning only `account_id` and `balance` for `region='north'` rows, owned by `view_lab_owner`. What grants does the reader need to query it?

### Exercise 4 — Granting Only the View

Write commands granting `USAGE` on `view_lab` and `SELECT` on `v_north_default`, without granting the base table. If the role already holds these grants, what happens when repeating GRANT?

### Exercise 5 — Testing Owner Mode

On the lab dataset, which account IDs does `v_north_default` return to the reader **before enabling RLS**?

### Exercise 6 — Enabling RLS

Write SQL enabling RLS on `view_lab.accounts` and adding a SELECT policy for `view_lab_reader` limited to `tenant_id=10`. Does this policy grant SELECT on the table automatically?

### Exercise 7 — Owner Bypassing RLS

Why can the default-owner view still return account 2 (tenant 20) after Exercise 6, even though the reader's policy allows only tenant 10?

### Exercise 8 — CREATE VIEW security_invoker

Write SQL creating `view_lab.v_tenant10_invoker` with `security_invoker=true`, filtering `tenant_id=10`, and exposing `account_id,tenant_id,balance`.

### Exercise 9 — Caller Lacking Base Table Privileges

If the reader has SELECT only on the invoker view and not on the base table, does querying the view succeed? If it errors, is that an RLS issue or a base privilege issue?

### Exercise 10 — Column Privileges

Write a GRANT on `account_id,tenant_id,balance` of `accounts` for the reader to use `v_tenant10_invoker`, omitting `internal_code`.

### Exercise 11 — Reader RLS Results

With `v_north_invoker` after granting required columns, which account IDs does the reader see? Why is row 3 (tenant 10) omitted?

### Exercise 12 — Direct Table Results

After column grants and the tenant 10 policy, which IDs does the reader see when querying `account_id,tenant_id,region,balance` directly from `accounts`? Why does this differ from the north invoker view?

### Exercise 13 — Forbidden Columns

What happens if the reader SELECTs `internal_code` directly? Does that change if the reader can read `internal_code` for a subset of rows via a separately granted owner-mode view?

### Exercise 14 — Version Flag

Write a query checking whether the PostgreSQL server supports `security_invoker` on views (PG15+).

### Exercise 15 — Changing a View's Flag

Write the command enabling `security_invoker` on `v_north_default`. State two changes an application could experience.

### Exercise 16 — Creating a Barrier View

Write SQL creating `view_lab.v_north_balance_barrier` with `security_barrier=true`, filtering region north. Does this flag switch base table privilege checks to the caller?

### Exercise 17 — Combining Both Flags

Write a `CREATE VIEW` with both `security_invoker=true` and `security_barrier=true`.

### Exercise 18 — Leaky Functions

Explain why a function that throws input-dependent errors is non-leakproof. How does `security_barrier` interact with this function when placed in an outer WHERE clause?

### Exercise 19 — LEAKPROOF

Who can declare a function as LEAKPROOF? Why shouldn't you label a custom function containing logging or `RAISE EXCEPTION` as LEAKPROOF just to gain index speed?

### Exercise 20 — No WHERE Order Guarantee

Why does `WHERE tenant_id=10 AND f(code)` not guarantee `f` runs after the tenant filter? What mechanism should protect sensitive rows instead?

### Exercise 21 — Catalog reloptions

Write SQL showing `security_invoker` and `security_barrier` stored in `reloptions` for views in `view_lab`.

### Exercise 22 — Viewing RLS Policies

Write SQL listing policies on `view_lab.accounts` alongside `relrowsecurity` and `relforcerowsecurity`.

### Exercise 23 — Per-User Privileges

Write a query using `has_table_privilege` and `has_column_privilege` to check the reader's SELECT on the view and SELECT on `balance` and `internal_code`.

### Exercise 24 — Nested Views A

An outer invoker view references an inner default-owner view, which references `accounts`. Whose privilege/RLS identity applies to `accounts`? Is holding SELECT solely on the outer view sufficient for the reader?

### Exercise 25 — Nested Views B

An outer default-owner view references an inner security-invoker view. Whose identity checks the base relation when the reader queries the outer view?

### Exercise 26 — Function Privileges

A view calls `view_lab.mask_code(internal_code)`. Why does `GRANT SELECT ON view` not automatically let callers invoke the function without `EXECUTE`? What role does `SECURITY DEFINER` play?

### Exercise 27 — SECURITY DEFINER

List at least five safeguards required when a `SECURITY DEFINER` function reads a sensitive table and is exposed through a view.

### Exercise 28 — Permission Denied vs. Empty Result

One reader gets permission denied on a view SELECT, while another reader runs SELECT cleanly and gets 0 rows. Do both necessarily share the same root cause?

### Exercise 29 — FORCED RLS

How does enabling `FORCE ROW LEVEL SECURITY` affect the table owner? Does it force superusers or `BYPASSRLS` roles under normal policies?

### Exercise 30 — Updatable Views

Explain the differences between `GRANT UPDATE`, `WITH CHECK OPTION`, and `security_barrier` when a user UPDATEs a simple view.

### Exercise 31 — RLS UPDATE

In `view_lab.tasks` with SELECT and UPDATE policies for tenant 10, what happens if the reader tries to UPDATE a tenant 20 row? If changing a tenant 10 row's `tenant_id` to 20, which two checks apply?

### Exercise 32 — PUBLIC Warning

Write a grant you should avoid when only one role should read data (`GRANT SELECT ... TO PUBLIC`) and explain the scope of `PUBLIC`.

### Exercise 33 — Changing View Ownership

Why can `ALTER VIEW ... OWNER TO` change SELECT/RLS results even when the SQL definition stays identical?

### Exercise 34 — Connection Pools

All API calls share one database role, and an RLS policy uses `current_setting('app.tenant_id')` which clients can SET freely. Is this safe? Does `security_invoker` fix it?

### Exercise 35 — Barrier Performance

A query runs slower after enabling `security_barrier` because a non-leakproof predicate no longer pushes down. Should you turn off the barrier? Propose at least four safer ways to optimize.

### Exercise 36 — Planning a Migration

A default-owner reporting view is used by 12 services whose roles only hold SELECT on the view. Propose a plan to migrate to `security_invoker` without blindly granting full-table SELECT or causing downtime.

### Exercise 37 — Selecting a Design

Choose owner mode, invoker mode, barrier, or a combination for three scenarios:

1. A sales report showing only paid orders, with zero base table access granted.
2. A multi-tenant SaaS where RLS already enforces database roles and views simply clean up SQL.
3. A public view restricting `is_public=true` where untrusted users can pass custom function predicates.

### Exercise 38 — Self-Evaluating a Security View

Write a minimum review checklist for `reporting.v_customer_stats`: SQL definition, owner, grants, RLS, function permissions, nested views, barrier, runtime tests, and rollout/rollback. Distinguish **correctness of privileges** from **performance**.

---

## 33. Suggested Solutions

### Exercise 1 — Access via View

If the caller has `USAGE` on the view's schema and `SELECT` on a **default-owner view**, PostgreSQL checks base table privileges as the **view owner**, so the caller can read the view without base table SELECT. Direct base table queries still require table privileges and schema access, and fail without them.

### Exercise 2 — View Owner

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS view_name,
    pg_get_userbyid(c.relowner) AS owner_name
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid=c.relnamespace
WHERE n.nspname='view_lab'
  AND c.relname='v_north_default'
  AND c.relkind='v';
~~~

Expect `view_lab_owner` if created under `SET ROLE view_lab_owner` as in the lab.

### Exercise 3 — Default View

~~~sql
SET ROLE view_lab_owner;

CREATE VIEW view_lab.v_north_2 AS
SELECT account_id,balance
FROM view_lab.accounts
WHERE region='north';

RESET ROLE;

GRANT USAGE ON SCHEMA view_lab TO view_lab_reader;
GRANT SELECT ON view_lab.v_north_2 TO view_lab_reader;
~~~

No base table SELECT grant is required for the reader in **default owner mode**. If RLS is enabled, owner bypass/policies must still be evaluated.

### Exercise 4 — Grant Only on View

~~~sql
GRANT USAGE ON SCHEMA view_lab TO view_lab_reader;
GRANT SELECT ON view_lab.v_north_default TO view_lab_reader;
~~~

Repeating an identical GRANT does not create "duplicate privileges" and does not grant base table privileges. Still verify the grantor, role memberships, and other ACLs.

### Exercise 5 — Default-Owner Before RLS

~~~sql
SELECT account_id
FROM view_lab.v_north_default
ORDER BY account_id;
~~~

With the initial lab data and view privileges, the result is **1,2,5** because those rows match `region='north'`.

### Exercise 6 — Enabling RLS

~~~sql
SET ROLE view_lab_owner;

ALTER TABLE view_lab.accounts ENABLE ROW LEVEL SECURITY;

CREATE POLICY accounts_reader_tenant10_answer
ON view_lab.accounts
FOR SELECT
TO view_lab_reader
USING (tenant_id=10);

RESET ROLE;
~~~

If an equivalent policy already exists, skip recreating it in the lab. Policies do not grant SELECT; for a reader to access the table via a security-invoker view, separate relation/column GRANTs are needed.

### Exercise 7 — Table Owner Bypass

A default-owner view uses **`view_lab_owner`'s privileges and RLS identity** on the base table. That role also owns the table, bypassing RLS unless FORCE RLS is enabled. Because the view only filters region north, tenant 20 row 2 remains visible. The reader's tenant 10 policy is not applied as it would be in an invoker view.

### Exercise 8 — Creating an Invoker View

~~~sql
SET ROLE view_lab_owner;

CREATE VIEW view_lab.v_tenant10_invoker
WITH (security_invoker=true)
AS
SELECT account_id,tenant_id,balance
FROM view_lab.accounts
WHERE tenant_id=10;

RESET ROLE;

GRANT SELECT ON view_lab.v_tenant10_invoker TO view_lab_reader;
~~~

The view uses the caller's base relation privileges and RLS, without granting SELECT on `accounts`.

### Exercise 9 — Missing Base Grant

No. If the reader holds SELECT only on the invoker view and lacks SELECT on the needed base columns, the query fails with **permission denied for table accounts**. This is first and foremost a **base relation privilege** failure, not proof that RLS filtered all rows. RLS yields 0 rows only once relation privileges pass.

### Exercise 10 — Column Privileges

~~~sql
GRANT SELECT (account_id,tenant_id,balance)
ON view_lab.accounts TO view_lab_reader;
~~~

This covers columns for Exercise 8's `v_tenant10_invoker`, excluding `internal_code`. For `v_north_invoker` in the lab, the reader also needs `region` since the view selects and filters on `region`; grant all actually referenced columns.

### Exercise 11 — North Invoker and RLS

The reader sees **1,5**:

- RLS `tenant_id=10` allows rows 1, 3, 5.
- View `region='north'` allows rows 1, 2, 5.
- Their intersection is 1, 5.

Row 3 is tenant 10 yet **south**, so the view predicate excludes it.

### Exercise 12 — Direct Table Read After Grants

~~~sql
SET ROLE view_lab_reader;

SELECT account_id,tenant_id,region,balance
FROM view_lab.accounts
ORDER BY account_id;

RESET ROLE;
~~~

Expected **1,3,5** (all rows of tenant 10); the north view returns only 1,5 due to its extra `region='north'` filter. This shows that view filters and RLS policies are independent conditions.

### Exercise 13 — Ungranted Column Directly

~~~sql
SELECT internal_code FROM view_lab.accounts;
~~~

as reader raises a column privilege error if ungranted. However, if a separately granted owner-mode view **intentionally exposes `internal_code` for a subset of rows**, the reader can read those **exposed values through the view** without direct base column access. That is a controlled interface design requiring strict review.

### Exercise 14 — Version Check

~~~sql
SELECT
    current_setting('server_version') AS version_text,
    current_setting('server_version_num')::integer >= 150000
        AS has_security_invoker_view_option;
~~~

PostgreSQL 15+ supports `security_invoker` on regular views. On older versions, do not attempt the syntax.

### Exercise 15 — Enabling Invoker on an Existing View

~~~sql
ALTER VIEW view_lab.v_north_default
SET (security_invoker=true);
~~~

Two possible impacts:

1. **Permission denied** if callers lack SELECT on base relations/columns.
2. **Changed row sets** when RLS evaluates as the caller instead of the owner.

In the lab with column grants and tenant 10 RLS, results shift from 1,2,5 to 1,5. This is a major change requiring tested migrations.

### Exercise 16 — Barrier View

~~~sql
SET ROLE view_lab_owner;

CREATE VIEW view_lab.v_north_balance_barrier
WITH (security_barrier=true)
AS
SELECT account_id,region,balance
FROM view_lab.accounts
WHERE region='north';

RESET ROLE;

GRANT SELECT ON view_lab.v_north_balance_barrier
TO view_lab_reader;
~~~

A barrier does not switch base privilege checks to the caller: without `security_invoker`, the view stays in default owner mode. It adds evaluation-order protection against external non-leakproof qualifiers.

### Exercise 17 — Both Flags

~~~sql
SET ROLE view_lab_owner;

CREATE VIEW view_lab.v_north_both_flags
WITH (
    security_invoker=true,
    security_barrier=true
)
AS
SELECT account_id,tenant_id,region,balance
FROM view_lab.accounts
WHERE region='north';

RESET ROLE;
~~~

Callers need SELECT on the view and the corresponding base columns. In the lab with tenant 10 RLS, expected output after grants is 1,5.

### Exercise 18 — Leaky Function

A function that can `RAISE EXCEPTION`, log data, cause side effects, or take input-dependent time is **non-leakproof**. When a caller uses it in an outer WHERE over a sensitive view, the planner must not push it past a **security barrier** onto hidden rows in a way that leaks data. Barriers do not forbid calling the function on **rows the view exposes**.

### Exercise 19 — LEAKPROOF

Only a **superuser** can mark a function as LEAKPROOF. Truly leakproof functions reveal nothing about arguments beyond their return value, not even via errors or side effects. Falsely marking a function LEAKPROOF for index speed can expose hidden rows and break the security model.

### Exercise 20 — WHERE Order

SQL does not guarantee left-to-right AND evaluation; the optimizer can reorder predicates. When condition A protects sensitive data, rely on RLS/permissions and `security_barrier` if external leaky quals are in scope, rather than placing A before B.

### Exercise 21 — Inspecting reloptions

~~~sql
SELECT
    c.relname AS view_name,
    c.reloptions,
    pg_get_userbyid(c.relowner) AS owner_name
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid=c.relnamespace
WHERE n.nspname='view_lab'
  AND c.relkind='v'
ORDER BY c.relname;
~~~

`reloptions` lists explicitly set flags. A view with no custom options typically has `reloptions IS NULL`, reflecting defaults.

### Exercise 22 — RLS Metadata

~~~sql
SELECT
    schemaname,tablename,policyname,
    permissive,roles,cmd,qual,with_check
FROM pg_policies
WHERE schemaname='view_lab'
  AND tablename='accounts';
~~~

~~~sql
SELECT
    c.relname,c.relrowsecurity,c.relforcerowsecurity
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid=c.relnamespace
WHERE n.nspname='view_lab'
  AND c.relname='accounts';
~~~

Also check table ownership and `BYPASSRLS` attributes; seeing RLS enabled alone does not confirm whether the owner is restricted.

### Exercise 23 — Privilege Check

~~~sql
SELECT
    has_table_privilege(
        'view_lab_reader',
        'view_lab.v_north_default',
        'SELECT'
    ) AS can_read_view,
    has_column_privilege(
        'view_lab_reader',
        'view_lab.accounts',
        'balance',
        'SELECT'
    ) AS can_read_balance,
    has_column_privilege(
        'view_lab_reader',
        'view_lab.accounts',
        'internal_code',
        'SELECT'
    ) AS can_read_internal_code;
~~~

`has_column_privilege` checks column SELECT grants, **not** full RLS policy behavior. Runtime tests under the actual role remain essential.

### Exercise 24 — Outer Invoker → Inner Owner-Mode

Base table access **through the inner default-owner view** uses the **inner view owner's** privileges and RLS identity, not the reader's merely because the outer view is invoker. The caller may need SELECT on the inner view because the outer invoker view accesses it as the caller, depending on privilege structure.

Never assume `GRANT SELECT` on the outer view covers all nested invoker hops.

### Exercise 25 — Outer Default → Inner Invoker

Base table access through the **inner security-invoker view** uses the **querying caller's** identity per invoker rules, even when the outer view is owner mode. With base grants and tenant 10 RLS on the reader, results obey the reader's policy.

### Exercise 26 — Functions in Views

`GRANT SELECT` on a view governs view access. Functions invoked inside a view carry separate `EXECUTE` privileges, and view access does not automatically grant EXECUTE.

`SECURITY INVOKER` functions (default) run with caller privileges. `SECURITY DEFINER` functions run with the function owner's privileges, creating an elevation path requiring audit. This is a **function** attribute, distinct from `security_invoker` on views.

### Exercise 27 — SECURITY DEFINER Hardening

At minimum:

1. Own with a minimal-privilege role.
2. Pin a safe `search_path` and schema-qualify relation names.
3. Never assemble dynamic SQL from unquoted/unvalidated inputs.
4. `REVOKE EXECUTE ... FROM PUBLIC` on sensitive functions.
5. Grant EXECUTE only to required roles.
6. Audit RLS owner/BYPASSRLS and all tables the function reads.
7. Test for SQL injection, shadowing, and concurrent privileges.
8. Audit function definitions after every deployment.
9. Design outputs to avoid exposing secrets outside the contract.

### Exercise 28 — Privilege Errors vs. Empty Sets

They do not necessarily share the same cause. Permission denied occurs when a role lacks required grants. A successful query returning 0 rows can stem from view WHERE filters, RLS default-deny, bind parameters, joins, or empty tables. Check **access**, **policy identity**, and **data** separately.

### Exercise 29 — FORCE RLS

`ALTER TABLE ... FORCE ROW LEVEL SECURITY` subjects a normal **table owner** to RLS instead of letting ownership bypass it. However, superusers and `BYPASSRLS` roles retain their privileges. Never rely on FORCE to constrain an application running as superuser.

### Exercise 30 — UPDATE, CHECK OPTION, and Barrier

- `GRANT UPDATE`: lets the role run UPDATE on the view/columns when the view is updatable and base privileges allow.
- `WITH CHECK OPTION`: verifies newly INSERTed/UPDATEd rows still match the view's predicate per supported rules.
- `security_barrier`: constrains optimizer evaluation of non-leakproof outer predicates to prevent evaluation-order leaks; **does not replace grants or validate post-UPDATE rows**.

Base table RLS also enforces `USING` and `WITH CHECK` on DML.

### Exercise 31 — RLS UPDATE on tasks

With tenant 10 policies, the reader cannot UPDATE tenant 20 rows because `USING` hides them from UPDATE targeting. Changing a tenant 10 row's `tenant_id` to 20 involves:

1. **Column UPDATE privileges** (the lab granted UPDATE only on `state`).
2. **View `WITH CHECK OPTION`** if the new row leaves the tenant 10 view.
3. **RLS `WITH CHECK`** blocking `tenant_id=20` under the tenant 10 policy.

Thus even if UPDATE on `tenant_id` were granted, view CHECK OPTION and RLS policy checks would still reject it.

### Exercise 32 — PUBLIC

~~~sql
-- Example NOT recommended for sensitive views:
GRANT SELECT ON view_lab.v_north_default TO PUBLIC;
~~~

`PUBLIC` means every role. When only a small group should read data, grant directly to a dedicated role and audit memberships.

### Exercise 33 — Changing Owner

In an owner-mode view, the owner determines base relation grants and RLS identity. Changing the owner can break base grants or change which RLS policies apply; if the new owner holds `BYPASSRLS` or table ownership exemption, visible rows can expand. Treat `ALTER VIEW ... OWNER TO` as a **security change**, not just metadata housekeeping.

### Exercise 34 — Client-Set GUC

Not safe if clients can set `app.tenant_id` to arbitrary tenants. An RLS policy reading that GUC trusts unverified input, letting users spoof tenants. `security_invoker` only switches base checks to the database role; it **does not** validate GUC values. Set tenant context in a trusted layer, lock down permissions, and reset pooled connections.

### Exercise 35 — Barrier Slowdowns

Do not disable a barrier protecting a real security boundary purely for speed.

Improvements:

1. Add indexes matching the view's **internal** predicates.
2. Minimize rows, columns, and joins inside the view.
3. Replace user-defined predicates with built-in leakproof operators of equivalent semantics where valid.
4. Evaluate whether RLS/role grants can replace a barrier view after a formal security review.
5. Inspect `EXPLAIN` with realistic data and privileges.
6. Check statistics, selectivity, skew, and planning overhead.
7. Redesign the API/query contract so callers do not need dangerous functions over views.

Never mark unsafe functions `LEAKPROOF`.

### Exercise 36 — Migrating 12 Services

Process:

1. Inventory all 12 services, database roles, current view grants, and nested dependencies.
2. Verify PostgreSQL 15+.
3. Audit view owner, base grants, RLS policies, and `BYPASSRLS`.
4. Identify minimal base columns needed; avoid full-table SELECT grants without matching RLS.
5. Create a parallel `..._invoker_candidate` view in staging.
6. Apply minimal grants and base RLS policies if callers get direct table access.
7. Run positive/negative tests per service role and parameter profile.
8. Compare **exact row/column sets** before/after and audit unauthorized reads.
9. Benchmark plans and API latencies.
10. Roll out via canary/gradual cutover while monitoring permission errors and row mismatches.
11. Keep a time-bounded rollback path; avoid flipping flags or revoking grants across all services at once without full testing.
12. Clean up old views/grants after confirming zero consumers remain.

### Exercise 37 — Choosing Mode

**Scenario 1 — restricted reporting without base table access:** owner-mode view + view grants; consider `security_barrier=true` if the paid filter is a security boundary against external leaky quals. Least-privilege owner, zero base bypass paths for callers.

**Scenario 2 — SaaS with database-role RLS already in place:** `security_invoker=true` so views respect caller privileges/RLS. Add a barrier if the threat model includes non-leakproof predicates probing past view filters.

**Scenario 3 — public view facing untrusted caller functions:** `security_barrier=true` is essential for the `is_public=true` predicate. Choose owner vs. invoker separately based on whether callers should hold base privileges and which RLS identity is needed; never expect a barrier to grant or revoke privileges.

### Exercise 38 — Comprehensive Checklist

For `reporting.v_customer_stats`, minimum review covers:

- **Definition:** SELECT list, WHERE, JOIN, functions—any customer info exposed beyond contract?
- **Owner:** view and base table owners; superuser or `BYPASSRLS`?
- **Privileges:** view schema USAGE, view SELECT, base grants if invoker, memberships/PUBLIC.
- **RLS:** enabled/forced, policies, tenant identity, and owner bypass.
- **Options:** `security_invoker`/`security_barrier` via `pg_class.reloptions`.
- **Functions:** EXECUTE grants, `SECURITY DEFINER/INVOKER`, `LEAKPROOF`, `search_path`.
- **Nested views:** owner/invoker per layer, direct base relation paths.
- **Runtime tests:** authorized role sees exact rows; unauthorized roles blocked, column denials enforced, DML/check tested if writable.
- **Performance:** `EXPLAIN/ANALYZE` on safe SELECTs, buffers, index pushdown, RLS/barrier overhead.
- **Rollout:** staged grants/policies, canary, monitoring, rollback, change audit.

**Correctness of privileges** must never be sacrificed for faster queries. **Performance** must be tuned within the boundaries of a design that preserves correct privileges and data isolation.

---

## 34. Concise Admin Queries for Reuse

### 34.1. Checking Version and View Flags

~~~sql
SELECT current_setting('server_version') AS postgres_version;

SELECT
    n.nspname,
    c.relname,
    pg_get_userbyid(c.relowner) AS owner_name,
    c.reloptions
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid=c.relnamespace
WHERE n.nspname='view_lab'
  AND c.relkind='v'
ORDER BY c.relname;
~~~

### 34.2. Checking View Definition

~~~sql
SELECT
    'view_lab.v_north_secure' AS view_name,
    pg_get_viewdef('view_lab.v_north_secure'::regclass,true)
        AS sql_definition;
~~~

### 34.3. Reader's Base and View Privileges

~~~sql
SELECT
    has_schema_privilege('view_lab_reader','view_lab','USAGE')
        AS schema_usage,
    has_table_privilege(
        'view_lab_reader','view_lab.v_north_secure','SELECT'
    ) AS view_select,
    has_column_privilege(
        'view_lab_reader','view_lab.accounts','account_id','SELECT'
    ) AS account_id_select,
    has_column_privilege(
        'view_lab_reader','view_lab.accounts','internal_code','SELECT'
    ) AS internal_code_select;
~~~

### 34.4. RLS Metadata

~~~sql
SELECT
    n.nspname,
    c.relname,
    c.relrowsecurity,
    c.relforcerowsecurity,
    pg_get_userbyid(c.relowner) AS owner_name
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid=c.relnamespace
WHERE n.nspname='view_lab'
  AND c.relname='accounts';
~~~

~~~sql
SELECT policyname,roles,cmd,qual,with_check
FROM pg_policies
WHERE schemaname='view_lab'
  AND tablename='accounts';
~~~

### 34.5. Comparing Lab View Results

~~~sql
SET ROLE view_lab_reader;

SELECT
    'default' AS path,
    array_agg(account_id ORDER BY account_id) AS ids
FROM view_lab.v_north_default
UNION ALL
SELECT
    'invoker',
    array_agg(account_id ORDER BY account_id)
FROM view_lab.v_north_invoker
UNION ALL
SELECT
    'both_flags',
    array_agg(account_id ORDER BY account_id)
FROM view_lab.v_north_secure;

RESET ROLE;
~~~

With the lab keeping default owner mode, expected output is:

~~~text
default     {1,2,5}
invoker     {1,5}
both_flags  {1,5}
~~~

If you modified owners, options, FORCE RLS, or data, results will differ. This query **tests actually exposed rows**, without replacing a full privilege audit.

### 34.6. Cleaning Up After the Lab

Dropping schemas and roles **destroys lab data** and modifies cluster-wide roles. Run only after confirming these objects belong strictly to this lab and are unused elsewhere:

~~~sql
-- Only run on a lab instance with confirmed ownership:
-- DROP SCHEMA view_lab CASCADE;
-- DROP ROLE view_lab_reader;
-- DROP ROLE view_lab_owner;
~~~

Before cleanup, ensure your session ran `RESET ROLE`, no grants or objects outside the lab schema depend on those roles, and no clients are connected with them.

---

## 35. Official Documentation and Version Scope

When verifying syntax and privilege details for your PostgreSQL major version, consult:

- [PostgreSQL — CREATE VIEW](https://www.postgresql.org/docs/current/sql-createview.html): `security_invoker`, `security_barrier`, automatically updatable views, and `CHECK OPTION`.
- [PostgreSQL — ALTER VIEW](https://www.postgresql.org/docs/current/sql-alterview.html): modifying view options and ownership.
- [PostgreSQL — Privileges](https://www.postgresql.org/docs/current/ddl-priv.html): object privileges, ownership, schema access.
- [PostgreSQL — GRANT](https://www.postgresql.org/docs/current/sql-grant.html): table/column/function/schema grants and role memberships.
- [PostgreSQL — Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html): RLS, owner bypass, FORCE, policies.
- [PostgreSQL — CREATE POLICY](https://www.postgresql.org/docs/current/sql-createpolicy.html): `USING` and `WITH CHECK`.
- [PostgreSQL — CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html): `SECURITY DEFINER`, `SECURITY INVOKER`, and `LEAKPROOF`.
- [PostgreSQL — Function Security](https://www.postgresql.org/docs/current/perm-functions.html): privileges and risks when granting function execution.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): inspecting plans and actual execution.
- [PostgreSQL — System Catalog pg_class](https://www.postgresql.org/docs/current/catalog-pg-class.html): `reloptions`, owner, `relrowsecurity`/`relforcerowsecurity`.
- [PostgreSQL — pg_policies](https://www.postgresql.org/docs/current/view-pg-policies.html): system view listing policy definitions.

`/current/` URLs may point to a newer major version than you run. For `security_invoker`, remember the **PostgreSQL 15+** requirement; auxiliary behaviors and catalog/view DDL features vary across versions, so check your exact major version docs before deploying.

---

## 36. Summary

**Views in PostgreSQL are query interfaces governed by distinct privilege rules.** When handling sensitive data, `security_invoker` and `security_barrier` solve **two different problems**:

1. **Default views** check base table access as the **view owner**. This lets you grant SELECT on a restricted view without granting SELECT on base tables. However, RLS identity defaults to the owner, and table owners bypass RLS by default.
2. **`security_invoker=true`** (PostgreSQL 15+) applies the **caller's privileges and RLS identity** to qualifying base relations. Callers need privileges on base tables/columns; `GRANT SELECT` on the view alone is insufficient. This option does not add tenant WHERE filters or policies automatically.
3. **`security_barrier=true`** protects **sensitive view filter conditions** from the optimizer pushing external non-leakproof functions/operators ahead of them in ways that leak filtered-out rows. It **does not** alter base table privilege checks or convert a view into invoker mode.
4. **RLS** and **GRANT** are separate layers: roles need object privileges and rows must pass matching policies. `BYPASSRLS`, table ownership, and `FORCE ROW LEVEL SECURITY` can alter outcomes.
5. **Functions** carry independent `EXECUTE` privileges and `SECURITY INVOKER/DEFINER` modes; never infer function privileges from view flags. In particular, never mislabel functions `LEAKPROOF` just to force pushdown.
6. **Nested views** must be audited layer by layer: an outer invoker view does not turn an inner owner-mode view into invoker; an inner invoker view enforces caller privileges even under an outer owner-mode view.
7. **Security views do not replace every security layer.** Restrict direct table grants, control owner/role memberships, audit function privileges, enforce RLS, and authenticate application identity.
8. **UPDATE/INSERT through views** also depends on DML privileges, RLS `USING`/`WITH CHECK`, `WITH CHECK OPTION`, and view updatability. A barrier does not replace DML constraints.
9. **Flipping a flag on an active view can break applications or alter visible data scope.** Test as real roles, compare row sets, review grants/policies, and prepare a rollback.
10. **Performance still matters:** barriers and RLS can alter predicate pushdown and query plans. Measure `EXPLAIN` on representative data, but never trade away a security boundary just to shave off a few milliseconds.

Workflow to remember: **identify callers and allowed data scope → check view owner, schema/view/base grants → understand RLS identity and policies → choose `security_invoker` based on base privilege needs → choose `security_barrier` based on leaky-predicate threat model → audit functions and nested views → test positive and negative cases under real roles → measure execution plans → roll out safely with monitoring and rollback**.
