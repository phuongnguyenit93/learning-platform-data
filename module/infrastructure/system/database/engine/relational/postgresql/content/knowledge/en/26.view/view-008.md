# Schema Dependencies and Data Contract Changes

In PostgreSQL, a **view** is not merely a `SELECT` statement saved under a name. A view is also **a data interface layer** between physical table structures and data consumers: Java applications, BI reports, integration tools, ETL pipelines, internal APIs, or other views. When table structures, data types, column names, or business semantics change, these dependencies determine which changes PostgreSQL blocks, which changes succeed yet silently break clients, and in what order deployments must run.

Suppose an application queries:

~~~sql
SELECT customer_id, display_name, email
FROM api.customer_public_v1
WHERE customer_id = 101;
~~~

The view may source data from `core.customers`, where the physical column is `full_name`. If the physical column is renamed to `legal_name` while the view keeps exposing `display_name`, the application may not need to change its SQL at all. Conversely, dropping a column referenced by the view triggers PostgreSQL dependency protection under DDL rules. And if you silently change the meaning of `display_name` from display name to an identifier code while its data type stays `text`, the database **cannot detect that the business contract broke**.

This lesson belongs to the **View** chapter of the *Database Engine Relational PostgreSQL* module. It covers schema dependencies, how PostgreSQL stores and protects views, `CREATE OR REPLACE VIEW` constraints, backward-compatible contract evolution strategies, access privileges, catalog impact-analysis queries, migration labs, and exercises.

## 1. What Is a Data Contract?

A **data contract** is the set of expectations between data producers and data consumers. For an SQL view, the contract encompasses both **structure** and **semantics**.

| Component | Example | Why It Matters |
|---|---|---|
| Object name | `api.customer_public_v1` | Clients address SQL to this name |
| Column names | `display_name` | ORMs, JDBC mappers, and JSON serializers bind by name |
| Column order | `customer_id`, `display_name`, `email` | `SELECT *` and positional mapping depend on order |
| Data types | `bigint`, `text`, `timestamptz` | JDBC types, comparisons, and serialization |
| Effective nullability | Can `email` be NULL? | Java code may omit null checks |
| Business semantics | Active customers only | Wrong filters skew reports |
| Cardinality | One row per customer | JOINs assume uniqueness |
| Data freshness | Real-time vs. snapshot | UI behavior and consistency guarantees |
| Privileges and scope | Permitted tenants only | Data security |
| Write behavior | Does the view allow UPDATE/INSERT? | DML clients need stable semantics |
| Output ordering | Explicit `ORDER BY` in outer query | Never rely on implicit order |
| Version | `v1`, `v2` | Lets clients migrate independently |

PostgreSQL's **catalog dependencies** protect part of the structural contract. They do not automatically verify business expectations such as "one row per customer," "revenue net of refunds," or "timestamps always in UTC."

## 2. Views Are Logical Relations, Not Table Copies

Create a view:

~~~sql
CREATE VIEW api.customer_public_v1 AS
SELECT
    customer_id,
    full_name AS display_name,
    email
FROM core.customers
WHERE status = 'active';
~~~

This defines a logical relation. For a **regular view**, PostgreSQL stores the query definition and uses rewrite/planner mechanisms whenever users SELECT from it. PostgreSQL does not create a heap table storing the view's results upon `CREATE VIEW`.

### 2.1. Views Hide Physical Details

Applications only see `display_name` on the view. The physical table may store `full_name` or later rename it to `legal_name`; the view can keep exposing `display_name` as long as the definition stays compatible.

### 2.2. Views Do Not Freeze Data Automatically

Every query against a regular view reads underlying data per its snapshot/isolation level. Regular views are not permanent caches. **Materialized views**, by contrast, store physical results and require refreshes, covered separately later.

### 2.3. Views Can Assist Access Control

You can grant SELECT on a view without granting direct access to certain base tables, depending on ownership, `security_invoker`, RLS, and PostgreSQL rules. However, a view does not become a complete security mechanism merely by having a WHERE clause.

### 2.4. View Names Are Part of the API

If a dashboard runs SQL directly against `api.customer_public_v1`, dropping or renaming the view is just like removing or renaming an API endpoint. Migrations must account for external database consumers.

## 3. Where Does PostgreSQL Store View Definitions?

Views are represented in system catalogs, notably:

- `pg_class`: relation metadata, typically `relkind='v'` for regular views and `relkind='m'` for materialized views.
- `pg_attribute`: current output columns and data types of the relation.
- `pg_rewrite`: the `_RETURN` rewrite rule holding the view's defining query.
- `pg_depend`: catalog dependencies across objects, columns, functions, types, etc.
- `pg_namespace`: owning schema.
- `pg_get_viewdef(...)`: reconstructs the view's defining SQL in readable form.

### 3.1. Why Doesn't PostgreSQL Just Store Raw SQL Text?

When creating a view, PostgreSQL parses and binds object and column references by catalog identity. Renaming an underlying object or column is tracked via object/attribute identity rather than breaking the view simply because old SQL text used the prior name.

### 3.2. Dependencies Span Multiple Levels

~~~text
core.customers
      |
      v
api.customer_public_v1
      |
      +---- api.customer_report_v1
      |
      +---- dashboard reports / JDBC client
                    |
                    +---- API JSON consumer
~~~

PostgreSQL tracks relationships **inside the database** (e.g., view → table, view → view). However, JDBC clients, SQL files in repositories, external reports, and BI tools are rarely registered in `pg_depend`. Thus catalog dependency lists **never show the complete blast radius**.

## 4. Object Dependencies and Column Dependencies

A view can depend on:

1. Referenced tables, partitioned tables, or foreign tables.
2. One or more **columns** of base tables.
3. Other views.
4. Functions or operators used in expressions.
5. Data types, collations, domains, or related objects.
6. Additional objects per SQL and catalog semantics.

### 4.1. Column Dependency Example

~~~sql
CREATE VIEW api.customer_id_and_name AS
SELECT customer_id, full_name
FROM core.customers;
~~~

The view reads `customer_id` and `full_name`. Dropping `full_name` will be rejected while the view depends on it. Adding a new `phone` column to the base table, however, does not directly break this view.

### 4.2. The Dependency Graph Is Directed

Notation:

~~~text
Base table/column  --->  Dependent view  --->  Further dependent view
~~~

When altering a base table or column, trace **all downstream objects along the dependency chain**, not only views referencing it directly.

### 4.3. Functional Dependencies Differ from Raw SQL Text Dependencies

With dynamic SQL constructed and executed at runtime, dependencies may not be recorded statically at function creation time. This especially affects applications and PL/pgSQL functions using dynamic SQL. Never treat `pg_depend` as a complete search over all code references.

## 5. Schema Change Compatibility Matrix

The table below summarizes **typical** behavior for regular views in modern PostgreSQL; always verify against your exact schema and version.

| Change | Typical Behavior | Contract Risk |
|---|---|---|
| Add column to base table | Existing view keeps its previously defined columns | Clients expecting the new column won't see it automatically |
| Rename base table column | Bound view continues working via metadata | View's exposed column name does not change automatically |
| Drop column used by view | PostgreSQL blocks due to dependency unless CASCADE | Blocks migration or wipes views if forced with CASCADE |
| Drop column unused by view | Succeeds if no other dependencies exist | External logic outside DB might still use the column |
| Change type of column used by view | Blocked due to view/rule dependency | Needs dedicated migration, not plain ALTER TYPE |
| `CREATE OR REPLACE VIEW` changing expression with identical output shape | Allowed | Can silently break semantics even though DDL succeeds |
| Rename exposed view column | Requires explicit rename command | Clients querying old column name break |
| Append column at end via OR REPLACE | Permitted within compatibility rules | Clients using `SELECT *` or positional mapping may break |
| Reorder or retype existing view column via OR REPLACE | Strictly disallowed | Requires versioning or controlled migration |
| DROP table or view with dependents | Default RESTRICT blocks; CASCADE deletes dependents | Breaks the entire downstream chain |

The hardest trap: **succeeding DDL does not mean the data contract remained intact**.

## 6. SELECT * in Views Is a Compatibility Trap

Suppose:

~~~sql
CREATE VIEW api.customer_export AS
SELECT *
FROM core.customers;
~~~

Many assume this means "the view always returns every current column of customers." Yet PostgreSQL expands `*` at **view creation time**; the view's column list is fixed right then.

### 6.1. Adding a Base Column Does Not Expand the View

~~~sql
ALTER TABLE core.customers
ADD COLUMN phone TEXT;
~~~

The existing `api.customer_export` view **does not automatically gain `phone`** just because the table added a column.

### 6.2. Pros and Cons of This Behavior

Pro: the column contract does not accidentally mutate when internal tables add new fields.

Con: authors expecting `SELECT *` to mirror future schema changes are surprised when new columns never show up.

### 6.3. Always Declare an Explicit Column List for API Views

~~~sql
CREATE VIEW api.customer_public_v1 AS
SELECT
    customer_id,
    full_name AS display_name,
    email,
    created_at
FROM core.customers
WHERE status = 'active';
~~~

This makes every column's name, order, type, and origin clear. Reviewers reading migrations immediately see which contract fields are affected.

### 6.4. Avoid SELECT * in Clients Too

A Java client running:

~~~sql
SELECT * FROM api.customer_public_v1;
~~~

relies on column order and metadata. When a column is appended to the view, positional mappers or ORMs can behave unexpectedly. Always request only the columns the client actually consumes.

## 7. Renaming Base Table Columns: View Columns Stay Unchanged

Suppose the view is:

~~~sql
CREATE VIEW api.customer_public_v1 AS
SELECT
    customer_id,
    full_name AS display_name
FROM core.customers;
~~~

After:

~~~sql
ALTER TABLE core.customers
RENAME COLUMN full_name TO legal_name;
~~~

PostgreSQL continues executing the view because its dependency points to the **table attribute**, not just the old SQL text string.

### 7.1. Inspecting the Updated Definition

~~~sql
SELECT pg_get_viewdef(
    'api.customer_public_v1'::regclass,
    true
);
~~~

The displayed definition references `legal_name` as the source column, while **the view's output column remains `display_name`**.

### 7.2. Why Is This Useful for Migrations?

You can refactor internal column names to match a new data model while preserving external API names. This is a prime strength of views as a *compatibility layer*.

### 7.3. Do Not Apply This Assumption to Direct Client SQL

If an application queries directly:

~~~sql
SELECT full_name FROM core.customers;
~~~

renaming the column breaks that SQL. PostgreSQL preserves internal view dependencies inside the database; **it never rewrites SQL queries living in application repositories**.

## 8. Dropping a Column Used by a View

Suppose a view reads `email`:

~~~sql
CREATE VIEW api.customer_contact AS
SELECT customer_id, email
FROM core.customers;
~~~

Attempt to drop the column:

~~~sql
ALTER TABLE core.customers
DROP COLUMN email;
~~~

Because the view depends on `email`, PostgreSQL rejects the statement and reports dependent objects. This protects schema integrity.

### 8.1. RESTRICT Prevents Silent Breakage

Where supported on DROP commands, default RESTRICT behavior prevents deleting objects that still have dependents. This is not an annoyance—it forces you to plan changes across the whole dependency chain.

### 8.2. CASCADE Can Be Very Dangerous

~~~sql
-- RISK ILLUSTRATION: DO NOT RUN ON REAL SYSTEMS
ALTER TABLE core.customers
DROP COLUMN email CASCADE;
~~~

CASCADE deletes the view and all downstream dependent objects. If those objects serve active APIs, the system breaks in production even though the migration DDL succeeded.

### 8.3. A Safer Alternative

- Add the replacement column.
- Migrate/backfill data.
- Create a new versioned view using the replacement column.
- Cut clients over gradually.
- Confirm zero users remain on the old column/view.
- Finally drop the old column in a controlled migration.

**CASCADE is a dependency tool**, not a "fix migration error" button.

## 9. Changing the Data Type of a Referenced Column

Suppose `email` is `text` and you want to change its type or representation.

~~~sql
ALTER TABLE core.customers
ALTER COLUMN email TYPE VARCHAR(200);
~~~

In many cases, PostgreSQL **forbids altering the type of a column referenced by a view or rule**, even when a cast looks trivial. The database must protect the bound view definition and its output types.

### 9.1. Do Not Assume USING Casts Resolve Dependencies Automatically

Adding `USING email::varchar(200)` does not make PostgreSQL rewrite all referencing views. View/rule dependencies still block the type change.

### 9.2. Use Add-Copy-Switch Instead of In-Place Alteration

Workflow:

1. `ADD COLUMN email_new ...`.
2. Backfill/sync values from `email`.
3. Create view `v2` with the new type/semantics.
4. Migrate consumers to `v2`.
5. Resolve `v1` dependencies.
6. Drop the old column once unused.

### 9.3. Casting Inside Views Has Limits Too

To preserve a `text` output contract over a newly typed internal column:

~~~sql
SELECT email_new::text AS email
FROM core.customers;
~~~

This works to hide the new internal type under v1, **only when internal column steps follow a dependency-safe order**. You cannot alter the type of a column already bound by an active view directly and hope v1 casts automatically.

### 9.4. Identical Types Do Not Guarantee Identical Semantics

Changing `email` from plaintext addresses to hashed values still produces `text`, so PostgreSQL will not block valid DDL. Yet that is a **breaking semantic change**.

## 10. CREATE OR REPLACE VIEW: What Can Be Modified?

PostgreSQL supports:

~~~sql
CREATE OR REPLACE VIEW api.customer_public_v1 AS
SELECT
    customer_id,
    full_name AS display_name,
    lower(email) AS email
FROM core.customers
WHERE status = 'active';
~~~

However, **CREATE OR REPLACE VIEW does not let you freely change every aspect of the output schema**.

### 10.1. Core Rules

For existing view columns, the replacement query must keep the **same column names, same order, and same data types** per PostgreSQL rules; **new columns may be appended at the end** of the list.

### 10.2. Appending a Column at the End Is Valid

Initial view:

~~~sql
CREATE VIEW api.customer_public_v1 AS
SELECT customer_id, full_name AS display_name
FROM core.customers;
~~~

Replaced with:

~~~sql
CREATE OR REPLACE VIEW api.customer_public_v1 AS
SELECT
    customer_id,
    full_name AS display_name,
    email
FROM core.customers;
~~~

Appending `email` after the two original columns is valid.

### 10.3. Reordering Columns Is Incompatible

If a view currently exposes:

~~~text
customer_id BIGINT
display_name TEXT
email TEXT
~~~

a new definition returning `email` before `display_name` is rejected even though both are `text`. PostgreSQL enforces output column names, order, and types.

### 10.4. Do Not Use OR REPLACE to Rename Columns Arbitrarily

To rename an output column, PostgreSQL requires an explicit view column rename, e.g.:

~~~sql
ALTER VIEW api.customer_public_v1
RENAME COLUMN display_name TO public_name;
~~~

Yet that is a **breaking change for every client** querying `display_name`. When parallel support is needed, create `v2` instead of renaming v1.

### 10.5. Appending at the End Can Still Break Clients

PostgreSQL allows appending columns at the end, yet clients using `SELECT *`, `INSERT INTO ... SELECT *`, or positional deserializers can still break. **Database-level replace compatibility is not application-level backward compatibility**.

### 10.6. OR REPLACE Can Silently Change Semantics

Two SELECTs with identical column names, order, and types can still change WHERE filters or formulas:

~~~sql
CREATE OR REPLACE VIEW api.active_customer_count AS
SELECT COUNT(*)::bigint AS count
FROM core.customers
WHERE status = 'active';
~~~

Changing `status='active'` to another criterion passes DDL cleanly while shifting report numbers. Migrations need semantic tests.

## 11. DROP VIEW, RESTRICT, and CASCADE

Suppose:

~~~text
core.customers
      |
      v
api.customer_public_v1
      |
      v
api.customer_summary_v1
~~~

When running:

~~~sql
DROP VIEW api.customer_public_v1;
~~~

PostgreSQL rejects the drop because `customer_summary_v1` depends on it, unless dependencies are handled explicitly.

### 11.1. CASCADE Deletes the Dependent Chain

~~~sql
-- RISK ILLUSTRATION ONLY
DROP VIEW api.customer_public_v1 CASCADE;
~~~

This deletes downstream dependent views as well.

### 11.2. Grants and Metadata

When you DROP and CREATE anew, object identity changes. Ownership, grants, comments, and related metadata must be re-applied. `CREATE OR REPLACE VIEW` preserves the existing view object and its privileges, unlike DROP/CREATE.

### 11.3. Never Use CASCADE to "Simplify Deployment"

In databases with hundreds of views and BI clients, cascading drops shatter contracts widely. Map dependencies, build v2, migrate consumers, and drop v1 only once confirmed unused.

## 12. Renaming Tables or Moving Schemas

Beyond columns, PostgreSQL tracks relation identity via metadata such as object OIDs.

### 12.1. Renaming a Base Table

~~~sql
ALTER TABLE core.customers
RENAME TO customer_accounts;
~~~

Views already bound to the table continue operating under the new table name, whereas direct client SQL querying `core.customers` breaks because the old name no longer exists.

### 12.2. Moving a Table to Another Schema

~~~sql
ALTER TABLE core.customer_accounts
SET SCHEMA internal;
~~~

Requires the target `internal` schema and appropriate privileges. Dependent views keep working via object identity, while **application SQL** hardcoding the old schema path breaks.

### 12.3. search_path and Unqualified Names

In `CREATE VIEW`, unqualified table or function names resolve according to `search_path` when the definition is parsed. Deploying identical DDL text across two environments with different `search_path` settings can bind to entirely different objects.

### 12.4. Always Use Schema-Qualified Names in Migrations

~~~sql
CREATE VIEW api.customer_public_v1 AS
SELECT customer_id, full_name AS display_name
FROM core.customers;
~~~

Schema-qualified names prevent accidental binding when multiple schemas hold identically named tables.

### 12.5. Do Not Use RENAME as API Versioning

Renaming a physical table can be an internal refactoring step, whereas renaming a client-facing view changes the public contract. Separate internal names from SQL endpoint names.

## 13. View Dependencies on Functions, Operators, and Expressions

Views can invoke functions:

~~~sql
CREATE VIEW api.customer_normalized AS
SELECT
    customer_id,
    lower(email) AS normalized_email
FROM core.customers;
~~~

Here the view depends on the `lower` function/operator and the `email` column.

### 13.1. User-Defined Functions

~~~sql
CREATE FUNCTION core.format_customer_name(p_name TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT btrim(p_name);
$$;
~~~

Then:

~~~sql
CREATE VIEW api.customer_formatted AS
SELECT
    customer_id,
    core.format_customer_name(full_name) AS display_name
FROM core.customers;
~~~

### 13.2. Replacing a Function Body Can Alter Semantics Without Changing View Schema

If `CREATE OR REPLACE FUNCTION` preserves signature while changing formatting logic, the view keeps running while output values shift. That is another form of **semantic contract change**.

### 13.3. Function Overloads and Types

When new overloads are added or schemas change, the parser picks functions based on argument types and `search_path` during view creation/replacement. Inspect argument types and schema qualification, not just function names.

### 13.4. Dynamic SQL Is Not Fully Captured by Catalogs

If a PL/pgSQL function uses `EXECUTE` with dynamic SQL built from table names passed as strings, catalog dependency graphs miss runtime table references. During schema changes, search code, tests, and logs too.

## 14. Contract Breaks Go Beyond DDL

An SQL view with an unchanged structure can still break clients:

### 14.1. Changing Filter Semantics

Originally the view exposed only `status='active'` customers. Someone alters WHERE to include all customers, inflating downstream report counts without touching column names or types.

### 14.2. Changing Cardinality

A view originally returned one row per customer, then later JOINs an `addresses` table holding multiple rows per customer:

~~~sql
SELECT c.customer_id, c.full_name, a.address_line
FROM core.customers AS c
JOIN core.addresses AS a
  ON a.customer_id = c.customer_id;
~~~

If a customer has three addresses, the query returns three rows for that customer. Consumers assuming `customer_id` is unique compute wrong totals.

### 14.3. Changing NULL Semantics

Originally `email` was always populated; after a migration it returns NULL for unverified customers. The type stays `text`, yet Java code hits NullPointerExceptions or invalidates JSON schemas.

### 14.4. Changing Timezones

Switching from local timestamps to UTC instants while keeping `timestamp without time zone` silently shifts displayed times with zero schema change. Prefer `timestamptz` for instants and state timezone contracts clearly.

### 14.5. Changing Measurement Units

Changing an `amount` column from VND to thousands of VND leaves its type numeric while corrupting financial reports. Introduce a new column such as `amount_minor_units` and a new API version.

### 14.6. Result Order Is Never Implicitly Guaranteed

A view defined without an explicit ordering contract makes no row order promise. Clients must add `ORDER BY` to outer queries whenever deterministic order matters. Even if a view has an internal `ORDER BY`, never rely on it as an ordering guarantee for outer queries.

## 15. Views as Compatibility Layers

A strong pattern is **keeping the public interface stable while evolving physical schemas**:

~~~text
JDBC / BI / API
       |
       v
api.customer_public_v1
       |
       v
core.customers
       |
       v
physical columns / indexes / partitions
~~~

### 15.1. Aliases Protect Names

`full_name AS display_name` decouples the API name from internal storage naming.

### 15.2. Casts Protect Types

If v1 commits to `text` for email, you can cast new internal expressions inside the view provided dependency ordering is respected during migration.

### 15.3. Filters Protect Scope

Views can limit exposed rows to active customers or published rules; however, using views for security enforcement requires careful evaluation of security semantics.

### 15.4. Compatibility Has Limits

A view alone cannot solve:

- Global uniqueness.
- Data quality.
- Versioning of every semantic rule.
- Clients querying base tables directly.
- Performance regressions from complex JOINs.
- Missing owner/invoker privileges.
- Migrations across separate database servers.

## 16. Versioning Views: v1 and v2

For major contract changes, **create a new view** rather than mutating v1 immediately.

~~~sql
CREATE VIEW api.customer_public_v1 AS
SELECT
    customer_id,
    full_name AS display_name,
    email
FROM core.customers;

CREATE VIEW api.customer_public_v2 AS
SELECT
    customer_id,
    full_name AS display_name,
    email,
    phone AS contact_phone
FROM core.customers;
~~~

### 16.1. Two Contracts Coexist

- Existing clients keep querying v1.
- New clients switch to v2 and adopt `contact_phone`.
- Consumers migrate individually without requiring simultaneous lockstep deploys.

### 16.2. When Is v2 Unnecessary?

For bug fixes that preserve committed structure and semantics after compatibility review, `CREATE OR REPLACE VIEW` is simpler. Still test and measure behavioral changes.

### 16.3. Marking Deprecation

Attach COMMENT metadata and operational docs:

~~~sql
COMMENT ON VIEW api.customer_public_v1 IS
'Compatibility contract v1; deprecate after consumers migrate to v2.';
~~~

COMMENTs are passive metadata—**they do not notify clients automatically**; assign owners and deprecation timelines.

### 16.4. Never Delete v1 Just Because v2 Exists

Confirm all callers, reporting jobs, stored queries, permissions, and dependent views have migrated. Catalogs cannot see external applications.

## 17. The Expand–Migrate–Contract Strategy

Use this pattern when applications and databases cannot upgrade atomically at the exact same instant.

~~~text
EXPAND
  Add new structures while keeping old ones
          |
          v
MIGRATE
  Backfill, dual-read/dual-write, switch clients
          |
          v
VERIFY
  Verify contracts and data
          |
          v
CONTRACT
  Remove old structures once no dependencies remain
~~~

### 17.1. Expand: Additive Changes

~~~sql
ALTER TABLE core.customers
ADD COLUMN preferred_name TEXT;
~~~

The table gains a new column while v1 remains untouched.

### 17.2. Sync and Backfill

~~~sql
UPDATE core.customers
SET preferred_name = full_name
WHERE preferred_name IS NULL;
~~~

Illustrative only; large tables require batched backfills, lock/transaction sizing, and handling concurrent writes.

### 17.3. Create v2

~~~sql
CREATE VIEW api.customer_public_v2 AS
SELECT
    customer_id,
    preferred_name AS display_name,
    email
FROM core.customers
WHERE status = 'active';
~~~

### 17.4. Migrate Consumers

Deploy applications reading v2, update SQL, DAOs/ORMs, BI reports, and contract tests; monitor real errors.

### 17.5. Final Contract Phase

Only after confirming zero dependencies remain on v1 or old columns should you drop obsolete objects with a verified rollback plan.

### 17.6. Why Avoid Big-Bang Cutovers?

In production, app instances undergo rolling deploys and batch jobs run on schedules. Keeping two versions side by side eliminates the need to deploy every caller simultaneously.

## 18. Comprehensive Lab: Safe Environment Setup

The following sections use a dedicated schema **for practice only**. Run in a test database; if `view_contract_lab` already exists, pick another name to avoid conflicts. Never delete objects holding real data.

### 18.1. Create Schema

~~~sql
CREATE SCHEMA view_contract_lab;
~~~

### 18.2. Create Base Table

~~~sql
CREATE TABLE view_contract_lab.customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'inactive')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

### 18.3. Insert Sample Data

~~~sql
INSERT INTO view_contract_lab.customers(
    full_name, email, status
)
VALUES
    ('Nguyen An', 'an@example.test', 'active'),
    ('Tran Binh', 'binh@example.test', 'active'),
    ('Le Chi', 'chi@example.test', 'inactive');
~~~

Sample data uses `example.test`, not real customer addresses.

### 18.4. Create v1 with Explicit Output Aliases

~~~sql
CREATE VIEW view_contract_lab.customer_public_v1 AS
SELECT
    customer_id,
    full_name AS display_name,
    email,
    created_at
FROM view_contract_lab.customers
WHERE status = 'active';
~~~

### 18.5. Create a View Depending on v1

~~~sql
CREATE VIEW view_contract_lab.customer_labels_v1 AS
SELECT
    customer_id,
    display_name
FROM view_contract_lab.customer_public_v1;
~~~

Dependency chain:

~~~text
view_contract_lab.customers
          |
          v
view_contract_lab.customer_public_v1
          |
          v
view_contract_lab.customer_labels_v1
~~~

This lab lets you observe the **dependency chain** and effects of DROP/ALTER.

## 19. Lab: SELECTing from Views and Inspecting Definitions

### 19.1. Reading v1 Data

~~~sql
SELECT
    customer_id,
    display_name,
    email,
    created_at
FROM view_contract_lab.customer_public_v1
ORDER BY customer_id;
~~~

Returns active customers matching the WHERE clause.

### 19.2. Reading the Dependent View

~~~sql
SELECT *
FROM view_contract_lab.customer_labels_v1
ORDER BY customer_id;
~~~

Exposes only `customer_id` and `display_name`.

### 19.3. Inspecting Definition via pg_get_viewdef

~~~sql
SELECT pg_get_viewdef(
    'view_contract_lab.customer_public_v1'::regclass,
    true
) AS definition;
~~~

Returns the reconstructed SELECT SQL. Whitespace and alias formatting may differ from the original text, while semantics remain stored in the rewrite representation.

### 19.4. Inspecting Columns via information_schema

~~~sql
SELECT
    ordinal_position,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'view_contract_lab'
  AND table_name = 'customer_public_v1'
ORDER BY ordinal_position;
~~~

Note: view nullability metadata does not reflect every inferred constraint from base tables. Never treat a view's `is_nullable` as absolute proof of business invariants.

## 20. Lab: Adding a Table Column While Keeping the Old View Contract

### 20.1. Add phone

~~~sql
ALTER TABLE view_contract_lab.customers
ADD COLUMN phone TEXT;
~~~

### 20.2. Populate Sample Phone Numbers

~~~sql
UPDATE view_contract_lab.customers
SET phone = CASE
    WHEN customer_id = 1 THEN '0900000001'
    WHEN customer_id = 2 THEN '0900000002'
    ELSE NULL
END;
~~~

### 20.3. Check View v1

~~~sql
SELECT *
FROM view_contract_lab.customer_public_v1
ORDER BY customer_id;
~~~

The `phone` column **does not appear automatically** in v1.

### 20.4. Check the Base Table

~~~sql
SELECT customer_id, full_name, email, phone
FROM view_contract_lab.customers
ORDER BY customer_id;
~~~

The column exists in the base table. This highlights the boundary between physical database schema and view contract.

### 20.5. Create v2 Instead of Changing v1

~~~sql
CREATE VIEW view_contract_lab.customer_public_v2 AS
SELECT
    customer_id,
    full_name AS display_name,
    email,
    phone AS contact_phone,
    created_at
FROM view_contract_lab.customers
WHERE status = 'active';
~~~

### 20.6. Verify Both Versions

~~~sql
SELECT customer_id, display_name, email
FROM view_contract_lab.customer_public_v1;

SELECT customer_id, display_name, email, contact_phone
FROM view_contract_lab.customer_public_v2;
~~~

V1 continues serving older clients; v2 adds `contact_phone` under an API-controlled name.

## 21. Lab: Renaming a Physical Column While Preserving View Contracts

In the **lab database**, run:

~~~sql
ALTER TABLE view_contract_lab.customers
RENAME COLUMN full_name TO legal_name;
~~~

### 21.1. View v1 Still Exposes display_name

~~~sql
SELECT customer_id, display_name
FROM view_contract_lab.customer_public_v1
ORDER BY customer_id;
~~~

### 21.2. View v2 Works Too

~~~sql
SELECT customer_id, display_name, contact_phone
FROM view_contract_lab.customer_public_v2
ORDER BY customer_id;
~~~

### 21.3. Inspect Definition After Rename

~~~sql
SELECT pg_get_viewdef(
    'view_contract_lab.customer_public_v1'::regclass,
    true
);
~~~

The source column reflects the new physical column `legal_name`, while the output alias remains `display_name`.

### 21.4. Direct Base Table Clients Behave Differently

SQL:

~~~sql
SELECT full_name
FROM view_contract_lab.customers;
~~~

now fails after the rename and must switch to `legal_name`. Keeping clients on the view layer reduces coupling—only if clients genuinely query through the view.

## 22. Lab: DDLs Blocked by Dependencies

The statements below **intentionally demonstrate dependency errors** and are not required setup steps. Run them individually in a test database only when observing error messages.

### 22.1. Attempting to Drop a Column Used by Views

~~~sql
-- ILLUSTRATION: EXPECTED TO BE REJECTED BY PostgreSQL
ALTER TABLE view_contract_lab.customers
DROP COLUMN email;
~~~

Both v1 and v2 reference `email`. PostgreSQL rejects the drop because dependent objects exist.

### 22.2. Attempting to Alter Column Type

~~~sql
-- ILLUSTRATION: EXPECTED TO BE BLOCKED WHILE VIEW/RULE USES COLUMN
ALTER TABLE view_contract_lab.customers
ALTER COLUMN email TYPE VARCHAR(200);
~~~

Do not treat this as a valid migration step. After an error inside an active transaction, run ROLLBACK or rollback to a savepoint before running further statements.

### 22.3. Attempting to Drop v1 While Labels View Depends on It

~~~sql
-- ILLUSTRATION: EXPECTED TO BE BLOCKED DUE TO DEPENDENT VIEW
DROP VIEW view_contract_lab.customer_public_v1;
~~~

### 22.4. Do Not Use CASCADE Just to Bypass Exercises

~~~sql
-- DO NOT RUN ON DATA YOU NEED TO KEEP
DROP VIEW view_contract_lab.customer_public_v1 CASCADE;
~~~

This deletes `customer_labels_v1` and any downstream dependents. The point is understanding why PostgreSQL blocks unsafe drops, not destroying the dependency graph to force DDL through.

## 23. Lab: Compatible CREATE OR REPLACE VIEW

If you want to **append a column at the end** of v1 (in a verified compatible change), the definition must keep existing column names, order, and types:

~~~sql
CREATE OR REPLACE VIEW view_contract_lab.customer_public_v1 AS
SELECT
    customer_id,
    legal_name AS display_name,
    email,
    created_at,
    phone AS contact_phone
FROM view_contract_lab.customers
WHERE status = 'active';
~~~

### 23.1. Why Does This Succeed?

The first four columns keep v1's exact names, order, and types; `contact_phone` is appended at the end.

### 23.2. Prior Dependent Views

~~~sql
SELECT customer_id, display_name
FROM view_contract_lab.customer_labels_v1;
~~~

Existing dependent views keep reading the first two columns cleanly. External consumers running `SELECT * FROM v1`, however, now receive an extra column and must be checked for compatibility.

### 23.3. Renaming a Column via OR REPLACE Is Rejected

Replacing `display_name` with `legal_name` at the same position is not allowed by CREATE OR REPLACE. Use `ALTER VIEW ... RENAME COLUMN` to rename; if older clients still rely on the old name, leave v1 intact and create v2.

### 23.4. Advice for Versioned Contracts

This lab shows what PostgreSQL **permits at the DDL level**. In production, when v1 is a strict published contract, evaluate even trailing column additions carefully—often it is safer to freeze v1 and evolve v2 freely.

## 24. Inspecting View Dependencies via pg_rewrite and pg_depend

PostgreSQL records view query dependencies against the `_RETURN` rewrite rule.

~~~sql
SELECT DISTINCT
    v.oid::regclass AS view_name,
    d.refobjid::regclass AS referenced_relation,
    a.attname AS referenced_column,
    d.deptype AS dependency_type
FROM pg_class AS v
JOIN pg_rewrite AS r
  ON r.ev_class = v.oid
JOIN pg_depend AS d
  ON d.classid = 'pg_rewrite'::regclass
 AND d.objid = r.oid
 AND d.refclassid = 'pg_class'::regclass
LEFT JOIN pg_attribute AS a
  ON a.attrelid = d.refobjid
 AND a.attnum = d.refobjsubid
WHERE v.oid =
    'view_contract_lab.customer_public_v1'::regclass
  AND d.refobjid <> v.oid
ORDER BY
    referenced_relation,
    referenced_column;
~~~

### 24.1. Meaning of refobjid and refobjsubid

- `refobjid`: OID of the referenced object.
- `refobjsubid`: for column-level dependencies, the attribute number; 0 indicates a whole-relation dependency.
- `pg_attribute.attnum`: corresponding column attribute number.
- `pg_attribute.attname`: column name.

### 24.2. Why Join pg_rewrite?

A view's query lives in the rewrite rule linked to the view relation. Query dependencies attach to the **rewrite rule**, not solely to the view relation's OID.

### 24.3. Why Exclude Self-References?

The rewrite rule holds internal dependencies pointing to the view itself, not only source tables. Filtering `d.refobjid <> v.oid` isolates external relations.

### 24.4. Do Not Treat Catalog Output as a Complete Application Map

This query lists only relation dependencies recorded in the catalog matching its filters. It misses Java SQL strings, external dashboards, runtime functions, and dependencies in other `refclassid` classes.

## 25. Finding All Views Depending on a Table

To see which objects may be affected when changing `view_contract_lab.customers`:

~~~sql
SELECT DISTINCT
    dependent.oid::regclass AS dependent_relation,
    a.attname AS referenced_column
FROM pg_depend AS d
JOIN pg_rewrite AS r
  ON r.oid = d.objid
JOIN pg_class AS dependent
  ON dependent.oid = r.ev_class
 AND dependent.relkind IN ('v', 'm')
LEFT JOIN pg_attribute AS a
  ON a.attrelid = d.refobjid
 AND a.attnum = d.refobjsubid
WHERE d.classid = 'pg_rewrite'::regclass
  AND d.refclassid = 'pg_class'::regclass
  AND d.refobjid =
      'view_contract_lab.customers'::regclass
  AND dependent.oid <> d.refobjid
ORDER BY dependent_relation, referenced_column;
~~~

### 25.1. This Query Finds Direct References

`customer_labels_v1` depends on v1 rather than directly on `customers`. Trace **multi-hop transitive dependencies** whenever modifying or dropping base objects.

### 25.2. Multi-Layer Dependencies in Migrations

A graph might look like:

~~~text
customers -> customer_public_v1 -> customer_labels_v1 -> report_job
~~~

Modifying `customers.email` directly affects v1/v2, while downstream reports on v1 can still suffer semantic shifts. Recursive catalog queries trace multi-hop views, while external jobs require searching source repositories and ownership inventories.

### 25.3. Never Filter Only by Unqualified Text Names

An `email` column can exist across multiple schemas. Use `regclass`/OIDs to pinpoint the exact relation instead of error-prone string matching.

## 26. Inspecting All Columns of a View via Catalogs

~~~sql
SELECT
    a.attnum AS ordinal_position,
    a.attname AS column_name,
    format_type(a.atttypid, a.atttypmod) AS column_type,
    a.attnotnull AS declared_not_null
FROM pg_attribute AS a
WHERE a.attrelid =
      'view_contract_lab.customer_public_v1'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

### 26.1. Using This as a Contract Snapshot

Shows exact column order, names, and types of the current view. Save these snapshots as migration manifests to compare **via external checks in STEP 4**.

### 26.2. Interpret View Nullability Carefully

An expression like `coalesce(email,'')` does not automatically mark the view column `attnotnull` in catalogs as developers might assume. Nullability contracts require explicit tests and application validation.

### 26.3. format_type Reports Exact Types

`format_type` shows `character varying(200)` or numeric precision/scale needed by clients, unlike bare type names stripped of typmod.

## 27. How Does information_schema Help?

When standard SQL metadata suffices instead of PostgreSQL-specific catalogs, `information_schema` provides views such as:

~~~sql
SELECT
    table_schema,
    table_name,
    view_definition
FROM information_schema.views
WHERE table_schema = 'view_contract_lab';
~~~

and:

~~~sql
SELECT
    table_schema,
    table_name,
    column_name,
    ordinal_position,
    data_type
FROM information_schema.columns
WHERE table_schema = 'view_contract_lab'
ORDER BY table_name, ordinal_position;
~~~

### 27.1. Advantages

Readable for common checks and closer to standard SQL across engines.

### 27.2. Limitations

Visibility depends on user privileges, and it omits full dependency graphs and PostgreSQL-specific attributes. For precise object reference analysis, query `pg_catalog` with appropriate privileges.

### 27.3. Never Mix Up Schemas

A view named `customer_public_v1` can exist in several schemas. Always filter by `table_schema` in metadata queries and deployments.

## 28. ALTER VIEW and Other Alterations

Beyond `CREATE OR REPLACE VIEW`, PostgreSQL provides commands like:

~~~sql
ALTER VIEW view_contract_lab.customer_public_v1
RENAME TO customer_public_legacy;
~~~

or:

~~~sql
ALTER VIEW view_contract_lab.customer_public_v1
RENAME COLUMN display_name TO customer_name;
~~~

These examples are **contract-breaking DDL**. Do not run them mid-lab if later queries reference the original names.

### 28.1. Renaming a View

Internal catalog dependencies continue referencing the object by OID, while external SQL clients querying the old name fail.

### 28.2. Renaming a View Column

Dependent views bound to the column update via metadata, yet direct SQL clients reading the old column name fail. DDL succeeding never means all consumers are ready.

### 28.3. Changing Ownership

`ALTER VIEW ... OWNER TO ...` can change effective privileges on underlying tables depending on view mode, even when the output schema stays unchanged.

### 28.4. Changing View Schema

`ALTER VIEW ... SET SCHEMA ...` changes the qualified path referenced by apps, requiring updates to SQL names and schema `USAGE` grants.

## 29. Access Privileges Are Part of the Contract

Suppose a client holds only:

~~~sql
GRANT SELECT
ON view_contract_lab.customer_public_v1
TO app_reader;
~~~

This illustrates granting to an **existing role**. In the lab, skip running this unless `app_reader` exists and you hold GRANT privileges.

### 29.1. GRANT Does Not Replace Schema Privileges

Callers also need namespace/schema access under PostgreSQL rules, such as `USAGE ON SCHEMA`.

### 29.2. Default Views Use Owner Privileges on Base Tables

In PostgreSQL, regular views by default check privileges on underlying base relations as the view owner; callers still need appropriate privileges on the view itself.

### 29.3. SECURITY INVOKER

Starting in PostgreSQL 15, views can set `security_invoker=true` so base relation privileges are checked as the caller:

~~~sql
CREATE VIEW view_contract_lab.customer_public_invoker
WITH (security_invoker = true)
AS
SELECT customer_id, legal_name
FROM view_contract_lab.customers;
~~~

If a caller has SELECT on the view yet **lacks privileges on the base table**, the query fails. Never add `security_invoker` merely because it sounds "safer" without understanding the privilege model.

### 29.4. Permission Changes Also Break Clients

A `REVOKE`/`GRANT` migration changes neither view names nor column types, yet can break every query from an application role. Privileges are part of the data contract.

## 30. RLS, security_barrier, and Security Boundaries

### 30.1. RLS

Row-Level Security on base tables governs which rows clients see. View owner/invoker mode and role bypass attributes interact with RLS; never assume a superuser test query matches what an application role sees.

### 30.2. security_barrier Views

For sensitive filtering, views can set:

~~~sql
CREATE VIEW view_contract_lab.active_customers_barrier
WITH (security_barrier = true)
AS
SELECT customer_id, legal_name, email
FROM view_contract_lab.customers
WHERE status = 'active';
~~~

This restricts optimizer reordering of caller predicates across the view boundary per security/leakproof function rules, preventing evaluation-order information leaks.

### 30.3. Performance Trade-Offs

`security_barrier` can inhibit predicate pushdown and alter query plans compared to regular views. Never treat it as a "speed flag." It is a security mechanism with potential runtime cost.

### 30.4. security_barrier Does Not Replace RLS/GRANT

A view with a WHERE clause is not a complete authorization system. Audit who can SELECT base tables directly, who owns the view, who has `BYPASSRLS`, and whether functions can leak data.

### 30.5. Versioning Privilege Policies

If v2 exposes additional sensitive columns, never blindly copy v1's grants onto v2. Review permitted fields, authorized roles, audit logging, and data classification.

## 31. Do Views Allow INSERT, UPDATE, DELETE?

Simple single-table views can be **automatically updatable** under PostgreSQL rules. Views with GROUP BY, aggregates, DISTINCT, multiple JOINs, or complex constructs generally are not automatically updatable.

### 31.1. Simple View Example

~~~sql
CREATE VIEW view_contract_lab.active_customers_editable AS
SELECT customer_id, legal_name, email, status
FROM view_contract_lab.customers
WHERE status = 'active';
~~~

Depending on structure and conditions, this qualifies as automatically updatable.

### 31.2. WITH CHECK OPTION

~~~sql
CREATE VIEW view_contract_lab.active_customers_checked AS
SELECT customer_id, legal_name, email, status
FROM view_contract_lab.customers
WHERE status = 'active'
WITH LOCAL CHECK OPTION;
~~~

`WITH CHECK OPTION` ensures rows written through the view continue satisfying the view predicate per PostgreSQL semantics. It does not replace full business validation or RLS.

### 31.3. Changing a View Can Break Write Contracts

Changing a view from a simple single-table SELECT to a JOIN or aggregate may keep output columns identical while silently removing automatic INSERT/UPDATE support. DML clients will break after migration.

### 31.4. INSTEAD OF Triggers

Some views rely on `INSTEAD OF` triggers to handle custom write logic. When evolving base table schemas, inspect trigger functions too; catalogs do not always catch dynamic SQL inside functions.

### 31.5. Never Test Only SELECT

When views support writes, contract tests must verify INSERT/UPDATE/DELETE, constraint errors, RETURNING, transactions, and privileges under application roles.

## 32. Materialized Views and Data Contracts

**Materialized views** differ from regular views by persisting physical query results.

~~~sql
CREATE MATERIALIZED VIEW view_contract_lab.customer_counts_mv AS
SELECT status, COUNT(*)::bigint AS customer_count
FROM view_contract_lab.customers
GROUP BY status;
~~~

### 32.1. Snapshots Do Not Auto-Reflect Writes Immediately

After `customers` changes, the materialized view retains the prior snapshot until refreshed:

~~~sql
REFRESH MATERIALIZED VIEW
view_contract_lab.customer_counts_mv;
~~~

### 32.2. Refresh Is Part of the Freshness Contract

Clients must know how often reports refresh and tolerate stale data. This is a major contract distinction from regular views.

### 32.3. Indexes on Materialized Views

Materialized views have their own physical storage and indexes, unlike regular views which have no result heap to index directly.

### 32.4. REFRESH CONCURRENTLY Has Prerequisites

PostgreSQL supports `REFRESH MATERIALIZED VIEW CONCURRENTLY` only under specific conditions, including a qualifying unique index on a populated view. Never assume every materialized view can refresh concurrently.

### 32.5. Base Schema Changes Still Have Dependencies

Materialized views also track dependencies on tables, columns, and objects. Migrations altering referenced columns must account for dependency resolution, recreation/refresh steps, and snapshot timing.

## 33. Multi-Table JOIN Views: Contracts and Cardinality

A view aggregating customers and orders:

~~~sql
CREATE VIEW view_contract_lab.customer_order_totals AS
SELECT
    c.customer_id,
    c.legal_name AS display_name,
    COUNT(o.order_id)::bigint AS order_count
FROM view_contract_lab.customers AS c
LEFT JOIN view_contract_lab.orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.legal_name;
~~~

This example **requires an `orders` table** and illustrates logic only; do not run it in the lab unless `orders` exists.

### 33.1. JOINs Can Alter Cardinality

One customer has many orders. Without aggregation, a view returns multiple rows per customer; with aggregation, the GROUP BY key and JOIN shape dictate cardinality.

### 33.2. Changing Dependent Tables Can Slow Down Queries

Adding a JOIN, filter, or expression without altering output columns can still cause latency spikes. Application contracts include latency/SLO expectations, not just column names.

### 33.3. Regular Views Are Expanded by the Planner

Regular views do not materialize a costly intermediate I/O layer by default. The planner rewrites queries across views within semantic and security limits. Still, stacking many views/JOINs increases complexity and requires `EXPLAIN` verification.

### 33.4. Never Alter Semantics for Speed Without Notice

Dropping a JOIN to cut latency while omitting business rows breaks the contract even though SELECT runs faster.

## 34. Schema Changes in Live Environments

Production migrations run alongside concurrent queries and rolling deployments.

### 34.1. Database DDLs Acquire Locks

`ALTER TABLE`, `DROP`, `CREATE OR REPLACE VIEW`, and similar commands acquire locks. On busy systems, migrations may queue behind long transactions or block concurrent SQL briefly or at length.

### 34.2. Transactional DDL

Many PostgreSQL DDL commands execute transactionally and roll back cleanly on failure. However, never assume commands with `CONCURRENTLY` or specialized maintenance options can share the same transaction block.

### 34.3. Avoid Unnecessary DROP + CREATE

For compatible definition updates, `CREATE OR REPLACE VIEW` preserves object identity and grants, unlike DROP/CREATE. For breaking changes, create v2 rather than relying on CASCADE.

### 34.4. Set Lock Timeouts

~~~sql
BEGIN;
SET LOCAL lock_timeout = '3s';

-- Run small DDL pre-verified in staging.

COMMIT;
~~~

This is an operational wrapper, not a schema change itself. `lock_timeout` prevents indefinite wait queues, though timed-out migrations require clean rollback and scheduled retries.

### 34.5. Backfilling Large Tables

Never run a full-table UPDATE across hundreds of millions of rows in a single transaction. Plan batch sizing, WAL headroom, autovacuum, index overhead, concurrency, and dual-write synchronization.

### 34.6. Sequence Code Deploys Carefully

If a new app needs v2 columns, create the columns/view first before deploying the new app. While old app instances stay live during rolling deploys, keep v1 intact until zero callers remain.

## 35. Rolling Deploy Compatibility Matrix

Suppose the database evolves across two schema versions while applications span two versions.

| App | DB with v1 Only | DB with v1 and v2 | DB with v2 Only |
|---|---|---|---|
| Old app using v1 | Works if v1 contract holds | Works | Fails if v1 dropped |
| New app using v2 | Fails if v2 missing | Works | Works if v2 contract holds |
| Legacy scheduled job | Works | Works | Fails if unmigrated |
| External BI dashboard | Depends on refs | Depends on refs | Fails if referencing v1 |

### 35.1. Safe Rollout Sequence

1. Expand base tables.
2. Create v2 while **keeping v1**.
3. Verify application role privileges.
4. Deploy new app.
5. Migrate jobs and dashboards.
6. Monitor remaining v1 traffic.
7. Confirm deprecation deadline passed.
8. Only then drop v1 and obsolete columns.

### 35.2. Catalogs Cannot Confirm All Clients Migrated

A view with zero catalog dependents can still be queried by a quarterly batch job. Use application inventories, query logs, telemetry, and owner sign-off.

## 36. Contract Tests for Views

A solid view contract must be verified at two layers: **schema** and **semantics**.

### 36.1. Schema Shape

~~~sql
SELECT
    a.attnum,
    a.attname,
    format_type(a.atttypid, a.atttypmod)
FROM pg_attribute AS a
WHERE a.attrelid =
    'view_contract_lab.customer_public_v1'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

Asserts exact column names, ordinal positions, and types.

### 36.2. Data Filtering Contract

~~~sql
SELECT COUNT(*)
FROM view_contract_lab.customer_public_v1
WHERE customer_id IN (
    SELECT customer_id
    FROM view_contract_lab.customers
    WHERE status <> 'active'
);
~~~

In the lab, expected count is 0 because the view exposes only active customers. On large datasets, integration tests should use deterministic fixtures rather than relying on arbitrary data.

### 36.3. Cardinality

~~~sql
SELECT customer_id, COUNT(*)
FROM view_contract_lab.customer_public_v1
GROUP BY customer_id
HAVING COUNT(*) > 1;
~~~

If the contract promises one row per customer, this query must return zero rows.

### 36.4. Querying as the Application Role

Schemas can pass as the owner yet fail on `GRANT`/RLS under the application role. Run permission tests in the real role context.

### 36.5. JDBC Mapping

Java tests should verify `ResultSetMetaData` returns expected column names/types and maps cleanly into DTOs, including NULLs, timestamps, and numeric precision.

### 36.6. Semantic Fixtures

Seed test fixtures with active/inactive customers, empty/Unicode strings, modified emails, and multi-order cases for summary views, then assert exact values. Schema checks never substitute for semantic tests.

## 37. Java/JDBC: Views as Stable Interfaces

Java example using `PreparedStatement` to query v1:

~~~java
String sql = """
    SELECT customer_id, display_name, email
    FROM view_contract_lab.customer_public_v1
    WHERE customer_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 1L);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            long id = rs.getLong("customer_id");
            String name = rs.getString("display_name");
            String email = rs.getString("email");
            // Map to DTO per v1 contract.
        }
    }
}
~~~

Uses Java text blocks (Java 15+). On older Java versions, use standard string literals.

### 37.1. Separate v1 and v2 DTOs

If v2 changes email/phone/nullability/semantics, avoid forcing one shared DTO across versions if it blurs validation or null-safety contracts.

### 37.2. Parameters Instead of String Concatenation

Use `?` bind parameters for SQL values to prevent injection and enforce typing. Schema/view names are identifiers and cannot be bound with `?`; when selecting among versions, enforce an allowlist of valid identifiers.

### 37.3. Prepared Statements After DDL

Cached prepared plans require invalidation/replanning across schema changes, and changing result column types can break wire protocols or callers. Keeping v1 stable prevents prepared SQL statements from shifting result shapes unexpectedly.

### 37.4. Keep Clients Off Base Tables

When applications only have read grants on `api.*` and none on `core.*`, the view layer lets internal physical changes happen with minimal client coupling, provided privileges and security semantics are designed properly.

## 38. Measuring Performance Impact with EXPLAIN

Changing a view from a simple query to multi-table JOINs or heavy computations alters runtime and row counts even when the view name stays identical.

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    customer_id,
    display_name
FROM view_contract_lab.customer_public_v1
WHERE customer_id = 1;
~~~

### 38.1. Inspecting Base Table Plans

Regular views are rewritten and optimized as part of the outer query. `EXPLAIN` shows scans on `view_contract_lab.customers`, not necessarily a separate "View Scan" node.

### 38.2. Predicate Pushdown

When a view is a simple filter/alias, caller predicates like `customer_id=1` are pushed down into base table scans subject to semantic and barrier constraints.

### 38.3. Security Barriers

With `security_barrier=true`, certain predicate pushdowns are restricted to protect security semantics; plans and latency may differ from ordinary views.

### 38.4. Materialized Views

SELECTs on materialized views read stored materialized rows and use materialized view indexes, though data remains stale until the next REFRESH.

### 38.5. Never Run EXPLAIN ANALYZE Carelessly on DML

`EXPLAIN ANALYZE` **executes the SQL statement**. For INSERT/UPDATE/DELETE, wrap in a rolled-back test transaction or dedicated test database—never run on production thinking it is purely dry-run analysis.

## 39. Impact of Base Table Indexes and Schemas

Regular views cannot carry direct physical table indexes. When a view query slows down, inspect indexes on **base tables**.

### 39.1. Indexes Supporting Predicates

When many clients query v1 by `customer_id`, primary keys or indexes on the base table accelerate lookups.

### 39.2. Changing Views Can Change Index Eligibility

If v1 uses `WHERE status='active'` and v2 replaces it with an expression on `status` or joins another table, index paths can shift. Measure plans and statistics.

### 39.3. Do Not Separate View Maintenance from Index Tuning

Any long-lived API view requires ownership of both schema contracts and query performance. Every expression or filter tweak can invalidate existing index paths.

### 39.4. Cached Plans

Prepared/generic plans and parameter distributions affect index selection. Benchmark with representative parameter values, not a single sample row.

## 40. Ordering Migrations Using the Dependency Graph

General ordering rule:

- **Create:** create tables/columns/functions first, then dependent views.
- **Compatible update:** modify internals while keeping external shape, verify owner/grants and semantics.
- **Breaking update:** create new version, migrate consumers, drop old version last.
- **Delete:** remove dependent consumers from the outside in.

### 40.1. Example Graph

~~~text
customers
    |
    v
customer_public_v1
    |
    +------ customer_labels_v1
    |              |
    |              +------ report_A
    |
    +------ dashboard_B
~~~

Dropping `customers` impacts every downstream node. Dropping `customer_labels_v1` requires migrating `report_A` first.

### 40.2. Never Infer Dependencies from Version Numbers in Names

`v2` might be defined on top of `v1`, which would still block dropping `v1`. To decouple lifecycles, define `v2` directly against base tables or a stable internal layer depending on your maintenance model.

### 40.3. Migrations Must Be Semantically Idempotent, Not Just Syntactically

`CREATE OR REPLACE VIEW` does not make every change compatible. Re-running migrations must preserve published schemas/semantics without losing grants, comments, or data transformations.

## 41. Documenting Contract Ownership

Every API-facing view should document:

| Field | Example |
|---|---|
| View | `api.customer_public_v1` |
| Owner | Customer Data Team |
| Consumers | Customer service, BI, ETL |
| Version | v1 |
| Status | Active / Deprecated |
| Key | `customer_id` |
| Cardinality | One row per active customer |
| Time semantics | `created_at` is `timestamptz` |
| Nullability | `email` is non-NULL per business rules |
| Data freshness | Per SELECT snapshot |
| Security | SELECT granted to permitted roles; RLS per model |
| SLA/SLO | p95 latency and availability targets if applicable |
| Deprecation deadline | Once all consumers migrate to v2 |

### 41.1. COMMENTs in the Database

~~~sql
COMMENT ON VIEW view_contract_lab.customer_public_v1 IS
'Public customer contract v1. Consumers should migrate before deprecation.';
~~~

### 41.2. COMMENTs Are Insufficient Alone

Database metadata neither tracks external SQL jobs, reminds owners of deadlines, nor replaces governance processes.

### 41.3. Version-Control DDL in Repositories

Storing view definitions and migrations in version control enables contract diff reviews, staging reproducibility, and clean rollbacks.

## 42. Common Mistakes

### 42.1. "Views store query strings, so renaming a base column always breaks the view"

False in general. PostgreSQL binds dependencies by catalog identity; base column renames preserve view execution.

### 42.2. "Adding a table column auto-adds it to SELECT * views"

False. A view's column list is fixed at creation/replacement time.

### 42.3. "DDL succeeding means no breaking change occurred"

False. Semantics, cardinality, NULLs, privileges, or latency can shift even when types and names stay identical.

### 42.4. "CREATE OR REPLACE VIEW lets you change any name, type, or order"

False. PostgreSQL restricts altering existing columns, typically permitting only appending new columns at the end.

### 42.5. "Appending a trailing column is always compatible with all clients"

Not guaranteed. Clients using `SELECT *` or positional mapping can fail.

### 42.6. "You can drop any column used by a view freely"

False. PostgreSQL tracks dependencies and blocks unsafe drops unless dependents are handled.

### 42.7. "CASCADE is a safe shortcut for fast deploys"

False. It silently deletes dependent views and critical objects.

### 42.8. "ALTER TYPE with USING automatically updates referencing views"

False. View/rule dependencies still block direct column type changes.

### 42.9. "Renaming a base column renames the view's output column"

False. View aliases/output contracts stay unchanged.

### 42.10. "Renaming a view does not impact clients"

False. Clients querying the old name fail immediately.

### 42.11. "Catalogs list every application using a view"

False. External SQL strings, BI dashboards, and ETL scripts are absent from `pg_depend`.

### 42.12. "A table with zero dependent views is safe to drop"

False. Application code, dynamic SQL, batch jobs, or external integrations may still depend on it.

### 42.13. "Regular views have no storage, so they have no dependencies"

False. Regular views still have rewrite rules, column types, and catalog dependencies.

### 42.14. "Materialized views always return the freshest data"

False. They hold snapshots requiring explicit refreshes.

### 42.15. "Materialized views behave identically to regular views in DDL/indexes"

False. Materialized views have distinct storage, indexing, and refresh semantics.

### 42.16. "Views are always safe security boundaries"

False in general. Audit ownership, grants, RLS, `security_invoker`, `security_barrier`, and leakproof behavior.

### 42.17. "security_invoker and security_barrier mean the same thing"

False. One governs invoker-mode base table privileges; the other limits optimizer pushdown to protect security semantics.

### 42.18. "GRANT SELECT ON VIEW always includes USAGE ON SCHEMA"

False. Schema and object privileges are distinct.

### 42.19. "Changing view owner cannot affect who sees what data"

False. Ownership alters base table privilege/RLS evaluation in owner-mode views.

### 42.20. "Any view you can SELECT from also supports INSERT/UPDATE"

False. Updatability depends on query structure; JOIN/aggregate views need custom handling.

### 42.21. "VIEW WITH CHECK OPTION replaces all constraints"

False. It validates view visibility predicates on view writes, not FKs, uniqueness, or table-wide invariants.

### 42.22. "Querying through views is always slower than querying tables"

False. Regular views are rewritten and optimized; cost depends on the actual query, indexes, and security barriers.

### 42.23. "If a view has an internal ORDER BY, all clients get sorted output"

Never rely on this. Put `ORDER BY` in consumer queries whenever stable order is needed.

### 42.24. "DROP + CREATE preserves grants and comments"

Not automatically. Object identity changes and metadata/privileges must be reapplied.

### 42.25. "Unit testing DDL alone is enough"

False. You need contract tests covering schema, semantics, privileges, DML if applicable, and client integration.

## 43. Practice Exercises

### Exercise 1 — Contracts

List five components of a data contract for a public view.

**Hint:** Object name, column names, order, types, semantics, privileges, freshness.

### Exercise 2 — Dependency Graph

View A reads table B; view C reads A. When dropping B, which nodes are at risk?

**Hint:** A, C, and external clients.

### Exercise 3 — SELECT *

Create a view `SELECT * FROM table`, then `ADD COLUMN` to the table. Does the new column appear automatically in the old view?

**Answer:** Not by default; the view already fixed its column list.

### Exercise 4 — Renaming Physical Columns

If `full_name` is exposed by a view under alias `display_name`, does renaming the base column to `legal_name` force clients to change the alias?

**Hint:** Not necessarily; view dependencies and aliases preserve it.

### Exercise 5 — Direct SQL

Why do clients querying `full_name` directly on the base table fail after the rename?

**Hint:** PostgreSQL does not rewrite external client SQL.

### Exercise 6 — Dropping Columns

`email` is referenced by a view. Why does PostgreSQL reject `DROP COLUMN`?

**Hint:** Object dependency.

### Exercise 7 — CASCADE

Why is `DROP ... CASCADE` risky on public views?

**Hint:** It deletes dependent objects.

### Exercise 8 — ALTER TYPE

A view reads a `text` column. Can you always `ALTER` the base column to `varchar`?

**Answer:** No; view/rule dependencies block it.

### Exercise 9 — OR REPLACE

Can you use `CREATE OR REPLACE VIEW` to arbitrarily change an existing output column's data type?

**Answer:** No.

### Exercise 10 — Appending at the End

A view has columns `(id bigint, name text)`. Can appending `email text` at the end via `CREATE OR REPLACE` succeed?

**Hint:** Yes, provided existing names, order, and types stay unchanged.

### Exercise 11 — Reordering

Is swapping the order of `name` and `email` in a view purely cosmetic?

**Answer:** No; column order is part of the result shape.

### Exercise 12 — Renaming View Columns

Which command renames an output column of a view?

**Answer:** `ALTER VIEW ... RENAME COLUMN ...`.

### Exercise 13 — Semantic Breaks

A view still returns `amount` as text, yet its measurement unit changed; does the database catch this error?

**Hint:** Databases do not automatically enforce business semantics.

### Exercise 14 — Cardinality

A JOIN introduces multiple address rows per customer. Does the "one row per customer" expectation still hold?

**Answer:** Not necessarily.

### Exercise 15 — Nullability

If `email` can become NULL after a migration, what issues can Java mappers hit?

**Hint:** Null handling, validation, JSON contracts.

### Exercise 16 — Materialized Views

How do regular views and materialized views differ in freshness?

**Hint:** Regular views query base tables; materialized views store snapshots requiring refreshes.

### Exercise 17 — Dependencies

Which two catalogs are central for inspecting view query dependencies?

**Answer:** `pg_rewrite` and `pg_depend`.

### Exercise 18 — pg_attribute

Which catalog stores a view's column names and ordinal positions?

**Answer:** `pg_attribute`.

### Exercise 19 — pg_get_viewdef

Which function reconstructs a view's defining SELECT?

**Answer:** `pg_get_viewdef`.

### Exercise 20 — Direct vs. Transitive

A view depends on v1 without directly referencing `customers`. Will a query looking up direct dependencies of `customers` automatically show it?

**Hint:** No; you must trace multi-hop dependencies.

### Exercise 21 — External Consumers

Does `pg_depend` know about every query inside Java repositories?

**Answer:** No.

### Exercise 22 — search_path

Why should you schema-qualify tables and functions in `CREATE VIEW` for API views?

**Hint:** Prevents wrong object binding via `search_path`.

### Exercise 23 — View Versioning

When changing the type and semantics of a column already exposed in v1, why is creating v2 safer?

**Hint:** Lets clients migrate gradually while keeping v1 online.

### Exercise 24 — Expand–Contract

Order these steps: drop old column, add new column, backfill, switch clients, verify.

**Suggested answer:** Add → backfill/sync → switch → verify → drop.

### Exercise 25 — Rolling Deploys

Old app instances still query v1. Should you drop v1 as soon as the new app is rolled out to 10% of instances?

**Answer:** No.

### Exercise 26 — GRANT

Why must you test view SQL under the application role, not solely as superuser?

**Hint:** Privileges, RLS, and `security_invoker` differ.

### Exercise 27 — security_invoker

Whose privileges on base tables does this option check?

**Answer:** The invoker's, under matching semantics.

### Exercise 28 — security_barrier

What does this option primarily restrict?

**Hint:** Certain optimizer pushdowns/expression evaluations across views to protect security semantics.

### Exercise 29 — Updatable Views

Can a `GROUP BY COUNT(*)` view accept automatic UPDATEs like a simple single-table view?

**Hint:** Not under standard automatically updatable rules.

### Exercise 30 — WITH CHECK OPTION

What does this option validate when writing through a qualifying view?

**Hint:** That new rows still satisfy the view predicate per supported semantics.

### Exercise 31 — DDL Locks

Why must an `ALTER TABLE` migration on a large table account for concurrent workloads?

**Hint:** Locks and wait queues can block queries.

### Exercise 32 — CREATE OR REPLACE vs. DROP/CREATE

Why is `OR REPLACE` less disruptive to object identity?

**Hint:** Updates the existing view rather than creating a new object.

### Exercise 33 — Contract Metadata

Write a query listing columns, types, and positions of v1 using `pg_attribute`.

**Hint:** Base it on the query in Section 26.

### Exercise 34 — Semantic Tests

How do you verify `customer_public_v1` returns only active customers?

**Hint:** Seed an inactive fixture and assert it does not appear.

### Exercise 35 — Cardinality Tests

Write a `GROUP BY HAVING` query checking for duplicate `customer_id` rows in the view.

**Hint:** `GROUP BY customer_id HAVING COUNT(*) > 1`.

### Exercise 36 — JDBC

Why is `ResultSet.getString("display_name")` more resilient than positional mapping when a view expands?

**Hint:** Less coupled to column ordinal positions.

### Exercise 37 — Prepared SQL

Can you bind a view name with `?` like an ordinary value?

**Answer:** No. Identifiers must be selected/quoted via separate logic; use an allowlist across versions.

### Exercise 38 — Performance

Must a regular view always materialize its entire result set before applying a caller's `customer_id` filter?

**Answer:** No; the planner typically optimizes across the view within limits.

### Exercise 39 — Inventory

Catalogs show zero dependent views; is dropping v1 guaranteed safe?

**Answer:** No; external consumers may exist.

### Exercise 40 — End-to-End Plan

The `customers` table currently has `full_name text`. You want the internal name to become `legal_name`, add `preferred_name`, and let the new API prefer `preferred_name` when present. Design a plan without breaking the old app.

**Hint:** Keep v1 `display_name`; add `preferred_name`, backfill/sync, create v2 `display_name` with the new logic, migrate clients, verify, and finally deprecate v1. Renaming the base column can happen cleanly in a controlled step while view dependencies remain intact.

## 44. Lesson Summary Cheat Sheet

| Concept | Key Point |
|---|---|
| Regular view | Logical SELECT rewritten by PostgreSQL at query time |
| Materialized view | Persisted snapshot requiring REFRESH |
| Data contract | Both schema and semantics of a data interface |
| Object dependency | View depends on tables/views/functions/types/etc. |
| Column dependency | View references specific columns |
| `pg_rewrite` | Rewrite rule storing view definition |
| `pg_depend` | Dependency metadata |
| `pg_attribute` | Columns and types of a relation |
| `pg_get_viewdef` | Reconstructs view defining SQL |
| `information_schema.views` | Standard view metadata |
| `information_schema.columns` | Column list visible per caller privileges |
| `SELECT *` in CREATE VIEW | Expands at creation time; does not auto-add future columns |
| Renaming base column | View keeps working via dependency |
| Dropping column used by view | Blocked until dependents are handled |
| ALTER TYPE on column used by view | Blocked by view/rule dependency |
| RESTRICT | Protects objects with remaining dependencies |
| CASCADE | Deletes dependent chains transitively |
| `CREATE OR REPLACE VIEW` | Preserves existing column schema; can append at end |
| `ALTER VIEW RENAME COLUMN` | Renames output column; can break clients |
| Schema-qualified names | Prevents `search_path` misbinding |
| Contracts v1/v2 | Enables phased client migration |
| Expand–migrate–contract | Add new → switch → remove old |
| Semantic change | Can break business logic without changing types or names |
| Cardinality | Row multiplicity per business key to preserve |
| RLS/GRANT | Access privileges and row scope are part of the contract |
| `security_invoker` | Base table privileges checked as invoker where supported |
| `security_barrier` | Constrains optimization to uphold security semantics |
| Updatable views | Write support depends on query structure |
| `WITH CHECK OPTION` | Validates visibility of rows written through views |
| External consumers | Often absent from `pg_depend` |
| Contract tests | Schema, semantics, privileges, DML, and JDBC |
| EXPLAIN | Measures plan and performance impact |
| Migration rollback | Prepare before dropping or contracting |

---

## Conclusion

A PostgreSQL view is both **an object with database-tracked schema dependencies** and **a data contract with consumers outside the database**. Those two protections are not identical.

PostgreSQL tracks dependencies between views and underlying tables, columns, and functions, blocking destructive actions like dropping used columns or altering their types directly. Catalog binding also lets many base-table renames succeed without breaking views. Yet adding a table column never expands `SELECT *` views automatically, `CREATE OR REPLACE VIEW` restricts modifying existing column names/order/types, and `DROP ... CASCADE` can wipe out entire dependent chains.

More importantly, **the database cannot validate every semantic contract automatically**: whether results stay one row per customer, preserve currency units, respect timezones, enforce privileges, meet freshness expectations, or uphold NULL guarantees still depends on owners and tests. External clients do not show up in `pg_depend` either.

For potentially breaking changes, prefer **v1/v2 view versioning** and **expand–migrate–contract**: add new structures, backfill/sync, migrate consumers gradually, verify schema + semantics + privileges + performance, and drop old structures last. Done right, views become a stable interface layer allowing PostgreSQL schemas to evolve without forcing every application to change at once.
