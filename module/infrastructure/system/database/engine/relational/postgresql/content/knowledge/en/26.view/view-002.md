# Creating, Replacing, Renaming, and Dropping Views in PostgreSQL

In PostgreSQL, a **view** is a database object representing a named SQL query. Instead of rewriting `SELECT` statements repeatedly, developers can create a view once and query it like a relation:

~~~sql
SELECT *
FROM sales.v_order_summary;
~~~

Suppose an application needs an order report containing customer name, status, total amount, and order timestamp. The underlying query may have to `JOIN` the `orders` table with `customers`. A view centralizes this representation, allowing reports or APIs to share a unified data interface.

However, views also have a **lifecycle** just like other schema objects. When business requirements evolve, you need to know how to:

- **Create** a view with `CREATE VIEW`.
- **Replace the definition** with `CREATE OR REPLACE VIEW` without accidentally breaking the column interface.
- **Rename a view or column** with `ALTER VIEW ... RENAME`.
- **Move a view to another schema** with `ALTER VIEW ... SET SCHEMA` when needed.
- **Drop** a view with `DROP VIEW`, understanding `RESTRICT`, `CASCADE`, and dependency impacts accurately.

This lesson, **"Creating, Replacing, Renaming, and Dropping Views,"** belongs to the **View** chapter of the **Database Engine Relational PostgreSQL** module. The content progresses from syntax and hands-on SQL examples to dependency management, access permissions, updatable views, compatible changes, production migrations, metadata inspection, and practice exercises.

> **Practice principle:** the DDL commands below are intended for a **dedicated test database**. For views in production, inspect active consuming applications, dependent objects, permissions, migrations, and rollback plans before replacing, renaming, or dropping them.

---

## 1. What Is a View?

A **regular view** is a query stored under a name in a schema:

~~~text
Application
   |
   v
SELECT ... FROM v_order_summary
   |
   v
View defines SELECT/JOIN/WHERE
   |
   v
orders + customers tables
   |
   v
Results sent to application
~~~

Example:

~~~sql
CREATE VIEW sales.v_paid_orders AS
SELECT
    order_id,
    customer_id,
    total_amount
FROM sales.orders
WHERE status = 'paid';
~~~

Then:

~~~sql
SELECT *
FROM sales.v_paid_orders;
~~~

PostgreSQL plans and executes the view's logic against the source tables/relations. **A regular view does not store a separate copy of result data** like a materialized view.

### 1.1. How Do Views Differ from Tables?

| Property | Table | Regular View |
|---|---|---|
| Stores row data for the object itself | Yes | Does not store separate SELECT results |
| Supports direct SQL SELECT | Yes | Yes |
| Defined using | `CREATE TABLE` | `CREATE VIEW ... AS SELECT` |
| Impact when underlying table data changes | Table data itself changes | View results reflect changes on subsequent queries |
| Can create indexes directly | Yes | Not directly on a regular view |
| Supports INSERT/UPDATE/DELETE | Subject to constraints/permissions | Some views are automatically updatable; others need additional mechanisms |
| Dropped using | `DROP TABLE` | `DROP VIEW` |

Do not use `DROP TABLE` to drop a regular view, and do not use `DROP VIEW` for a table.

### 1.2. Views vs. Materialized Views

A **materialized view** stores query results in materialized form and must be refreshed to update its data. It uses commands such as `CREATE MATERIALIZED VIEW`, `REFRESH MATERIALIZED VIEW`, and `DROP MATERIALIZED VIEW`.

This lesson focuses on **regular views**. Do not assume `CREATE OR REPLACE VIEW` can be used to replace a materialized view's definition.

## 2. Basic Syntax of CREATE VIEW

Common form:

~~~sql
CREATE VIEW schema_name.view_name AS
SELECT ...
FROM ...
WHERE ...;
~~~

PostgreSQL syntax also supports optional clauses such as:

~~~sql
CREATE [ OR REPLACE ] [ TEMP | TEMPORARY ] VIEW view_name
    [ (column_name [, ...]) ]
    [ WITH (view_option_name [= view_option_value] [, ...]) ]
AS
    query
    [ WITH [ CASCADED | LOCAL ] CHECK OPTION ];
~~~

This is a syntax reference diagram to read, not an SQL statement to run verbatim; square brackets denote optional clauses.

PostgreSQL also supports **recursive views** in supported versions, which are covered briefly later.

### 2.1. Key Components

- `CREATE VIEW` creates a new object.
- `schema_name.view_name` identifies the view; schema-qualify names in migrations.
- `(column_name,...)` optionally specifies output column names.
- `AS query` defines the source query.
- `WITH (...)` sets options such as `security_barrier` and `security_invoker` on supported versions.
- `WITH CHECK OPTION` governs validation when writing through automatically updatable views.
- `OR REPLACE` updates the definition of an **existing view**, subject to specific column constraints.

### 2.2. Permissions and Object Names

To create a view in a schema, a role needs appropriate privileges on the schema and referenced objects. A view name shares the relation namespace with tables, indexes, sequences, and other relation objects in the same schema; you cannot create a duplicate name that is already taken.

Do not treat `CREATE VIEW` as a way to bypass schema or object permissions.

## 3. Setting Up a Self-Contained Lab Dataset

To make examples sequential, use a dedicated schema `view_lab`.

In an **empty practice database**, run:

~~~sql
CREATE SCHEMA view_lab;

CREATE TABLE view_lab.customers (
    customer_id BIGINT PRIMARY KEY,
    customer_name TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE view_lab.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES view_lab.customers(customer_id),
    status TEXT NOT NULL
        CHECK (status IN ('new', 'paid', 'cancelled')),
    total_amount NUMERIC(12,2) NOT NULL
        CHECK (total_amount >= 0),
    placed_at TIMESTAMPTZ NOT NULL
);

INSERT INTO view_lab.customers (
    customer_id, customer_name, active
)
VALUES
    (101, 'Lan', TRUE),
    (102, 'Minh', TRUE),
    (103, 'Hà', FALSE);

INSERT INTO view_lab.orders (
    order_id, customer_id, status,
    total_amount, placed_at
)
VALUES
    (1001, 101, 'paid', 125000.00,
     TIMESTAMPTZ '2026-11-01 09:00:00+00'),
    (1002, 102, 'new',  89000.00,
     TIMESTAMPTZ '2026-11-02 10:00:00+00'),
    (1003, 101, 'cancelled', 50000.00,
     TIMESTAMPTZ '2026-11-03 11:00:00+00'),
    (1004, 103, 'paid', 220000.00,
     TIMESTAMPTZ '2026-11-04 12:00:00+00');

ANALYZE view_lab.customers;
ANALYZE view_lab.orders;
~~~

The dataset has 3 customers and 4 orders. Timestamps are inserted with explicit timezone offsets; display formatting depends on the session's `TimeZone`.

### 3.1. Why Use Schema-Qualified Names?

The examples always use `view_lab.orders` rather than `orders` to:

- Avoid colliding with identically named tables in other schemas.
- Clearly distinguish objects belonging to the practice lab.
- Reduce reliance on `search_path`.
- Keep migrations explicit.

If `CREATE SCHEMA view_lab` or the tables already exist, creation statements may fail. Never blindly run `DROP SCHEMA ... CASCADE` on an unknown schema just to rerun a lab.

## 4. Creating the First View from a Single Table

Create a view of paid orders:

~~~sql
CREATE VIEW view_lab.v_paid_orders AS
SELECT
    order_id,
    customer_id,
    total_amount,
    placed_at
FROM view_lab.orders
WHERE status = 'paid';
~~~

Query it:

~~~sql
SELECT
    order_id,
    customer_id,
    total_amount
FROM view_lab.v_paid_orders
ORDER BY order_id;
~~~

Logical result:

| order_id | customer_id | total_amount |
|---:|---:|---:|
| 1001 | 101 | 125000.00 |
| 1004 | 103 | 220000.00 |

The view does not copy data. If an order is UPDATEd to `paid`, subsequent queries against the view reflect that change according to transaction snapshot rules.

### 4.1. Column Names Normally Come from the SELECT

The columns `order_id`, `customer_id`, `total_amount`, and `placed_at` become the output columns of the view.

If you use an unaliased expression:

~~~sql
SELECT total_amount * 1.1
FROM view_lab.orders;
~~~

the generated column name may be unsuitable for APIs or reports. When creating a view, always assign **clear aliases**.

## 5. Creating Views with Expressions and Aliases

Example creating a view for amounts with a hypothetical 5% fee:

~~~sql
CREATE VIEW view_lab.v_order_amounts AS
SELECT
    o.order_id,
    o.total_amount AS base_amount,
    (o.total_amount * 1.05)::NUMERIC(14,2)
        AS amount_with_demo_fee
FROM view_lab.orders AS o;
~~~

The name `amount_with_demo_fee` is much clearer than an expression's default generated name.

In this example, the 5% rate is strictly for SQL illustration; it is not a financial or tax rule.

### 5.1. Using a Column Name List After the View Name

You can specify output names in the header:

~~~sql
CREATE VIEW view_lab.v_status_counts(
    order_status,
    order_count
) AS
SELECT
    status,
    COUNT(*)
FROM view_lab.orders
GROUP BY status;
~~~

This list supplies names to corresponding columns in **SELECT order**. Avoid letting the name list get out of sync with the expression order, as mismatched names cause confusion.

### 5.2. Choosing Output Data Types Deliberately

A view is a schema interface. If an expression changes type due to casting or literal changes, applications can break. Use explicit casts when you need to stabilize the view's output types.

## 6. Creating Views with JOINs

In the lab, an order report needs customer names:

~~~sql
CREATE VIEW view_lab.v_order_summary AS
SELECT
    o.order_id,
    c.customer_name,
    o.status,
    o.total_amount,
    o.placed_at
FROM view_lab.orders AS o
JOIN view_lab.customers AS c
    ON c.customer_id = o.customer_id;
~~~

Query it:

~~~sql
SELECT *
FROM view_lab.v_order_summary
WHERE status = 'paid'
ORDER BY placed_at DESC;
~~~

The logical result consists of the two paid orders, including `customer_name`.

A view hides JOIN logic from consumers, but does not reduce the number of tables PostgreSQL must access. When executing the view, the planner still inspects the query logic and source tables.

### 6.1. Views Do Not Store JOIN Results by Default

If `view_lab.customers.customer_name` changes, view results reflect the change on the next query; there is no need to `REFRESH` a regular view.

### 6.2. Do Not Use Views to Mask JOIN Costs

If a view JOINs multiple huge tables, queries using the view can still be expensive. A view is a **logical abstraction**, not a data cache.

## 7. Creating Views with GROUP BY and Aggregations

~~~sql
CREATE VIEW view_lab.v_customer_revenue AS
SELECT
    o.customer_id,
    COUNT(*) FILTER (
        WHERE o.status = 'paid'
    ) AS paid_order_count,
    COALESCE(
        SUM(o.total_amount) FILTER (
            WHERE o.status = 'paid'
        ),
        0::NUMERIC
    ) AS paid_total
FROM view_lab.orders AS o
GROUP BY o.customer_id;
~~~

Query:

~~~sql
SELECT *
FROM view_lab.v_customer_revenue
ORDER BY customer_id;
~~~

Explanation:

- Aggregated views provide reusable reporting metrics.
- `FILTER` counts only `paid` orders.
- `COALESCE` replaces SQL NULL from SUM with no matching inputs with 0.
- Views with `GROUP BY`/aggregates are generally **not automatically updatable** via direct INSERT/UPDATE.

## 8. Do Not Rely on Row Ordering Inside a View

SQL relations have no guaranteed default order. Even when a view definition contains `ORDER BY` in certain cases, consumers should still specify ordering in the **outermost SELECT**:

~~~sql
SELECT *
FROM view_lab.v_order_summary
ORDER BY placed_at DESC, order_id DESC;
~~~

This is especially important for:

- Pagination.
- `LIMIT/OFFSET`.
- Deterministic API responses.
- Report exports.
- Snapshot comparisons.

Never treat physical table layout or a view's internal ordering as an API contract.

## 9. SELECT * When Defining a View

Example:

~~~sql
CREATE VIEW view_lab.v_orders_all AS
SELECT *
FROM view_lab.orders;
~~~

When creating a view, PostgreSQL parses the query and resolves the list of output columns. If a new column is later added to `view_lab.orders`, **the existing view does not automatically gain the new column** just because its original definition used `*`.

This is an important distinction from the misconception that "a view always selects all current columns."

### 9.1. Why Avoid SELECT * in Public Views?

- It easily creates an overly wide column interface.
- It obscures the API contract.
- When schemas change, you may need separate migrations to update the view.
- It risks exposing internal fields if views are altered carelessly.
- It makes column dependencies harder to predict.

Always list explicitly the columns consumers actually need.

## 10. Inspecting Newly Created View Definitions

PostgreSQL provides `pg_views`:

~~~sql
SELECT
    schemaname,
    viewname,
    viewowner,
    definition
FROM pg_views
WHERE schemaname = 'view_lab'
ORDER BY viewname;
~~~

To view a specific view's defining query:

~~~sql
SELECT pg_get_viewdef(
    'view_lab.v_order_summary'::regclass,
    TRUE
) AS view_definition;
~~~

`pg_get_viewdef` returns the query reconstructed by PostgreSQL from system catalog definitions, which does not necessarily preserve your original whitespace, alias layout, or character-for-character SQL text.

### 10.1. In psql

Common meta-commands:

~~~text
\dv view_lab.*
\d+ view_lab.v_order_summary
~~~

- `\dv` lists views.
- `\d+` describes view details, columns, and definitions where applicable.

These are **psql** commands, not standard SQL to send via JDBC.

## 11. CREATE OR REPLACE VIEW to Update Definitions

Syntax:

~~~sql
CREATE OR REPLACE VIEW view_lab.v_paid_orders AS
SELECT
    order_id,
    customer_id,
    total_amount,
    placed_at
FROM view_lab.orders
WHERE status IN ('paid', 'new');
~~~

This command replaces the existing view's query while keeping the **existing column interface** identical: same names, same order, same types.

The new result includes orders with status `paid` or `new`.

### 11.1. If the View Does Not Exist Yet

`CREATE OR REPLACE VIEW` creates a new view if no view with that name exists. It does not require a prior `CREATE VIEW` statement.

### 11.2. If the Name Belongs to a Table or Materialized View

`OR REPLACE` does not mean PostgreSQL will convert an existing table or materialized view of the same name into a regular view. A different object type with the same name causes the command to fail.

### 11.3. Why Choose OR REPLACE?

It updates the view definition without dropping and recreating the object, minimizing impact on:

- Existing grants on the view.
- View identity and ownership.
- Dependent views, provided the column interface remains compatible.
- Comments and metadata attached to the view.

However, **changing the query logic** can still affect results and permissions on source tables. Column compatibility **does not mean** application semantics are unchanged.

## 12. Crucial Limitations of CREATE OR REPLACE VIEW

For an existing view, the new definition must preserve existing output columns in:

1. **Column names**.
2. **Column order**.
3. **Column data types**.

PostgreSQL allows **appending new output columns at the end** of the existing list, but you cannot use `CREATE OR REPLACE VIEW` to arbitrarily rename, retype, or drop existing columns.

Example original view:

~~~text
v_paid_orders:
  order_id       BIGINT
  customer_id    BIGINT
  total_amount   NUMERIC(12,2)
  placed_at      TIMESTAMPTZ
~~~

A new definition keeping the first four columns identical and adding one column at the end is valid.

### 12.1. Why Does PostgreSQL Impose This Limit?

Other views or applications may depend on the old column list. Silently altering columns arbitrarily would cause running SQL to misinterpret data or fail due to missing columns.

This constraint makes compatible migrations more predictable, though it cannot guarantee every application query remains semantically correct.

## 13. Appending New Columns with OR REPLACE

Suppose you want to add status at the **end of the view**:

~~~sql
CREATE OR REPLACE VIEW view_lab.v_paid_orders AS
SELECT
    order_id,
    customer_id,
    total_amount,
    placed_at,
    status
FROM view_lab.orders
WHERE status IN ('paid', 'new');
~~~

The original four columns keep their order and types; `status` is added at the end.

Query:

~~~sql
SELECT
    order_id,
    total_amount,
    status
FROM view_lab.v_paid_orders
ORDER BY order_id;
~~~

### 13.1. Do Not Insert New Columns in the Middle

A definition such as:

~~~sql
-- Pattern NOT compatible with existing columns:
CREATE OR REPLACE VIEW view_lab.v_paid_orders AS
SELECT
    order_id,
    status,
    customer_id,
    total_amount,
    placed_at
FROM view_lab.orders;
~~~

will be rejected because the order/types/names of the leading output columns changed. If the view does not yet have `status`, append it **at the end** to comply with OR REPLACE rules.

### 13.2. Why Does Appending a Column Still Require Consumer Checks?

Applications using `SELECT *` or positional ORM mappings can break when a view gains an extra column. Thus, a change that is compatible at the PostgreSQL catalog level is not automatically compatible with every consumer.

## 14. Do Not Use OR REPLACE to Rename Columns

Suppose you want to rename `customer_id` to `buyer_id`.

The following statement is **not the right way** to rename a column on an existing view:

~~~sql
-- Illustrates a statement that PostgreSQL will reject:
CREATE OR REPLACE VIEW view_lab.v_paid_orders AS
SELECT
    order_id,
    customer_id AS buyer_id,
    total_amount,
    placed_at,
    status
FROM view_lab.orders;
~~~

Because the second column of the current view is still named `customer_id`, changing its name at that position violates the `CREATE OR REPLACE VIEW` contract.

The correct way is:

~~~sql
ALTER VIEW view_lab.v_paid_orders
RENAME COLUMN customer_id TO buyer_id;
~~~

After renaming, subsequent `CREATE OR REPLACE VIEW` calls must use an alias matching the new name:

~~~sql
CREATE OR REPLACE VIEW view_lab.v_paid_orders AS
SELECT
    order_id,
    customer_id AS buyer_id,
    total_amount,
    placed_at,
    status
FROM view_lab.orders
WHERE status IN ('paid','new');
~~~

This illustrates the difference between **updating the query definition** and **modifying column name metadata**.

## 15. Do Not Use OR REPLACE to Change Column Types

Suppose `total_amount` is `NUMERIC(12,2)`.

If a new definition returns `total_amount::TEXT` at that same position:

~~~sql
-- Will be rejected for changing an existing column's type:
CREATE OR REPLACE VIEW view_lab.v_paid_orders AS
SELECT
    order_id,
    buyer_id,
    total_amount::TEXT AS total_amount,
    placed_at,
    status
FROM view_lab.v_paid_orders;
~~~

Note that this illustrative snippet also references the very view being replaced, so **do not run it** as a migration: it creates an invalid self-referencing definition in this case. The key takeaway is that **changing an existing output column's type via OR REPLACE is not arbitrarily supported**.

The safe approach is usually to **create a new versioned view** with the desired type, migrate consumers, and retire the old version on schedule.

### 15.1. Cast Explicitly to Preserve Types

If an expression is rewritten while business semantics remain unchanged, use an explicit cast to keep the output column's type intact:

~~~sql
CREATE OR REPLACE VIEW view_lab.v_order_amounts AS
SELECT
    o.order_id,
    o.total_amount AS base_amount,
    ROUND(o.total_amount * 1.05, 2)::NUMERIC(14,2)
        AS amount_with_demo_fee
FROM view_lab.orders AS o;
~~~

The aliases, columns, and types remain compatible with the previously created `v_order_amounts` definition.

## 16. CREATE OR REPLACE Is Not Equivalent to DROP Then CREATE

Compare:

**Approach A — replace definition:**

~~~sql
CREATE OR REPLACE VIEW view_lab.v_order_summary AS
SELECT
    o.order_id,
    c.customer_name,
    o.status,
    o.total_amount,
    o.placed_at
FROM view_lab.orders AS o
JOIN view_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.status <> 'cancelled';
~~~

**Approach B — drop then recreate:**

~~~sql
-- Should not be treated as equivalent:
DROP VIEW view_lab.v_order_summary;

CREATE VIEW view_lab.v_order_summary AS
SELECT ...;
~~~

Differences:

| Factor | OR REPLACE | DROP + CREATE |
|---|---|---|
| Object identity | Preserves existing view | Creates a new object |
| Grants/ownership | Retained on existing view | Must be re-established on new object |
| Dependent objects | Preserved if compatible | DROP may be blocked or require dependency handling |
| Comments | Attached to old view are preserved | Must be reapplied to new object |
| Renaming/retyping/dropping columns | Restricted | Possible on new object, but breaking |
| Migration safety | Usually suited for compatible changes | Risks breaking dependencies |

Do not habitually use DROP + CREATE just to tweak a `WHERE` clause.

## 17. Modifying Views Inside a Transaction

PostgreSQL supports transactional execution for many DDL operations.

Lab example:

~~~sql
BEGIN;

CREATE OR REPLACE VIEW view_lab.v_order_summary AS
SELECT
    o.order_id,
    c.customer_name,
    o.status,
    o.total_amount,
    o.placed_at
FROM view_lab.orders AS o
JOIN view_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.status <> 'cancelled';

SELECT COUNT(*) AS visible_orders
FROM view_lab.v_order_summary;

ROLLBACK;
~~~

With transaction rollback, this definition change is not committed. This is useful for testing syntax and behavior in a **lab environment**.

### 17.1. Transactions Do Not Make Migrations Harmless

DDL still requires locks. Long transactions hold locks until COMMIT/ROLLBACK and can block other queries. In production, avoid opening a DDL transaction and leaving it idle while operators check things manually.

### 17.2. Do Not Use ROLLBACK as a Substitute for Staging

Even though rollback undoes schema changes, dependency checks, lock analysis, load testing, and application verification must still happen in staging before deployment.

## 18. Renaming a View with ALTER VIEW

Syntax:

~~~sql
ALTER VIEW schema_name.old_view_name
RENAME TO new_view_name;
~~~

Example creating a temporary view to rename:

~~~sql
CREATE VIEW view_lab.v_orders_for_rename AS
SELECT
    order_id,
    status
FROM view_lab.orders;
~~~

Rename it:

~~~sql
ALTER VIEW view_lab.v_orders_for_rename
RENAME TO v_order_status;
~~~

Query under the new name:

~~~sql
SELECT *
FROM view_lab.v_order_status
ORDER BY order_id;
~~~

### 18.1. RENAME TO Takes Only the New Name, Not a Schema-Qualified Name

To rename within the same schema, write:

~~~sql
ALTER VIEW view_lab.v_order_status
RENAME TO v_order_state;
~~~

Do not write a schema-qualified target like `view_lab.v_order_state` after `TO`.

### 18.2. Renaming Does Not Leave an Alias for the Old Name

After renaming, SQL still referencing `view_lab.v_order_status` will fail because that name no longer exists. If both old and new names must coexist during a transition period, create **a separate wrapper view** under proper governance rather than assuming RENAME preserves an alias automatically.

## 19. Renaming a View Column with ALTER VIEW

Syntax:

~~~sql
ALTER VIEW schema_name.view_name
RENAME COLUMN old_column TO new_column;
~~~

For example, since `v_paid_orders` already has `buyer_id` from the earlier section, do not repeat that rename. To demonstrate independently on `v_order_state`:

~~~sql
ALTER VIEW view_lab.v_order_state
RENAME COLUMN status TO order_status;
~~~

Then:

~~~sql
SELECT order_id, order_status
FROM view_lab.v_order_state
ORDER BY order_id;
~~~

### 19.1. Renaming a Column Does Not Automatically Fix SQL Clients

An application running:

~~~sql
SELECT status FROM view_lab.v_order_state;
~~~

must be updated to `order_status`.

Dependent views tracked internally by PostgreSQL via column identity may continue working, but **external SQL text**, Java/ORM code, dashboards, and BI tools are not updated automatically. Locate all consumers and plan a migration.

### 19.2. Difference Between RENAME COLUMN and Changing Aliases in CREATE OR REPLACE

- `ALTER VIEW ... RENAME COLUMN` modifies column name metadata.
- `CREATE OR REPLACE VIEW` updates the query while preserving existing column names, types, and order.

This is a key boundary when maintaining views.

## 20. How Renaming a View Affects Dependencies

PostgreSQL tracks internal dependencies by **object identity**, not merely by the string name of the view.

For example, create a child view:

~~~sql
CREATE VIEW view_lab.v_order_state_paid AS
SELECT order_id
FROM view_lab.v_order_state
WHERE order_status = 'paid';
~~~

If you then rename the parent view:

~~~sql
ALTER VIEW view_lab.v_order_state
RENAME TO v_order_state_current;
~~~

the child view remains valid because its dependency points to the parent object, and PostgreSQL reconstructs its definition using the new name.

However:

- Application SQL calling the old name will fail.
- Migration scripts hardcoding the old name must be updated.
- Functions using dynamic SQL strings may have dependencies PostgreSQL did not resolve statically.
- External reports outside the DB will not update automatically.

**Preserved internal object dependencies do not mean every name-based consumer is safe.**

## 21. Moving a View to Another Schema

Syntax:

~~~sql
ALTER VIEW old_schema.view_name
SET SCHEMA new_schema;
~~~

Lab example:

~~~sql
CREATE SCHEMA view_reporting;

ALTER VIEW view_lab.v_order_amounts
SET SCHEMA view_reporting;
~~~

The fully qualified name after moving is:

~~~sql
SELECT *
FROM view_reporting.v_order_amounts
ORDER BY order_id;
~~~

### 21.1. SET SCHEMA Differs from RENAME

- `RENAME TO` changes the **object name** within its schema.
- `SET SCHEMA` changes the **schema containing the object**.
- Both can be performed via two separate commands.

### 21.2. Permissions and Consumers

The executing role must hold appropriate privileges on the view and source/target schemas. Applications referencing `view_lab.v_order_amounts` explicitly must update to the new name or use a compatibility wrapper. `search_path` can also affect unqualified SQL references.

**Do not use SET SCHEMA just to reorganize code folders** without verifying permissions and consumer SQL.

## 22. Changing a View's Owner

Example syntax:

~~~sql
ALTER VIEW view_lab.v_order_summary
OWNER TO reporting_owner;
~~~

`reporting_owner` is a **hypothetical** role; the statement succeeds only if that role exists and the caller has privileges to transfer ownership under PostgreSQL rules.

A view's owner determines administrative privileges over the object and, in many cases, privileges used to access underlying source tables under default mode.

### 22.1. Owner Differs from View Users

Applications typically only need `GRANT SELECT` on a view. They do not need to be the owner and should not have `ALTER VIEW` or `DROP VIEW` permissions.

Separate:

- **Migration/owner role:** manages view definitions.
- **Application role:** holds only appropriate read/write grants.
- **Base-table roles:** governed by respective permissions and row-level security.

Never grant ownership to an application role just to work around a temporary permission error.

## 23. WITH Options When Creating or Altering Views

Important view options include:

- `security_barrier`.
- `security_invoker` (supported starting in PostgreSQL 15).
- `check_option` for updatable views.

Example:

~~~sql
CREATE VIEW view_lab.v_order_public
WITH (security_barrier = true) AS
SELECT
    order_id,
    customer_id,
    status,
    total_amount
FROM view_lab.orders
WHERE status <> 'cancelled';
~~~

Or adjust options on an existing view:

~~~sql
ALTER VIEW view_lab.v_order_public
SET (security_barrier = true);
~~~

### 23.1. Do Not Use Options to Arbitrarily Alter Columns

`ALTER VIEW ... SET (...)` modifies options, **not** the `SELECT` query or column list. To modify the query definition, use `CREATE OR REPLACE VIEW` within compatibility rules.

## 24. security_invoker and Base Table Permissions

On supported PostgreSQL versions, create a view with:

~~~sql
CREATE VIEW view_lab.v_orders_invoker
WITH (security_invoker = true) AS
SELECT
    order_id,
    customer_id,
    status
FROM view_lab.orders;
~~~

Meaning: under security invoker mode, permission checks on the underlying relations referenced by the view use the **caller's** privileges instead of applying the default view owner's privileges for underlying relations.

### 24.1. Default Views vs. security_invoker

By default, callers need privileges on the **view**, while privilege checks on underlying referenced relations are evaluated as the **view owner**. Thus, granting SELECT on a view lets you expose a restricted column/row interface without granting direct SELECT on the entire source table.

When `security_invoker=true`, the caller must hold appropriate privileges on the underlying objects checked by invoker mode; `GRANT SELECT` on the view alone is insufficient.

### 24.2. This Is a Security Decision, Not Just Syntax

Using security invoker alters privilege checks and interacts with Row-Level Security (RLS). Verify the PostgreSQL version, owner/role, grants, and actual RLS behavior before changing this option on views containing sensitive data.

Never use a view as your sole authorization layer without auditing other access paths to the source tables.

## 25. security_barrier and Optimization Limits

`security_barrier = true` is designed for views that must constrain predicate evaluation order to reduce the risk of data leaks via untrusted functions in security-sensitive contexts.

However:

- It does **not** automatically turn every view into an absolute security boundary.
- `LEAKPROOF` functions and planner rules still play a role.
- It can restrict predicate pushdown and impact performance.
- It does not replace proper authorization or RLS.

For security-sensitive views, evaluate **both authorization correctness and execution plans**, rather than adding the option simply because "security" sounds safer.

## 26. Automatically Updatable Views

Not every view is read-only.

A simple single-table view can be automatically updatable if it satisfies PostgreSQL's conditions:

~~~sql
CREATE VIEW view_lab.v_non_cancelled_orders AS
SELECT
    order_id,
    customer_id,
    status,
    total_amount,
    placed_at
FROM view_lab.orders
WHERE status <> 'cancelled';
~~~

Where auto-updatable conditions are met, PostgreSQL allows:

~~~sql
UPDATE view_lab.v_non_cancelled_orders
SET total_amount = 130000.00
WHERE order_id = 1001;
~~~

This command actually **modifies the source table**. Do not run it casually if you need to preserve the lab data for other observations.

### 26.1. When Is a View Not Automatically Updatable?

Cases that are generally not auto-updatable include:

- `GROUP BY` or aggregation.
- `DISTINCT`.
- `UNION`/set operations.
- Many JOINs and complex queries.
- Other constructs lacking a direct one-to-one mapping from a view row to a base relation row.

You can use `INSTEAD OF` triggers or rules in appropriate designs to define write behavior, but that is an **explicit custom design**, not automatic behavior.

### 26.2. INSERT/UPDATE/DELETE Permissions

Even when a view is auto-updatable, the role still needs appropriate privileges. A view never bypasses grants, constraints, or transaction semantics.

## 27. WITH CHECK OPTION When Writing Through Views

By default, if a view has:

~~~sql
WHERE status <> 'cancelled'
~~~

an UPDATE through the view might modify a row so that it **no longer satisfies the view's WHERE clause**, causing the row to disappear from the view afterward.

To enforce visibility conditions on writes through an automatically updatable view, use `WITH CHECK OPTION`:

~~~sql
CREATE VIEW view_lab.v_visible_orders AS
SELECT
    order_id,
    customer_id,
    status,
    total_amount,
    placed_at
FROM view_lab.orders
WHERE status <> 'cancelled'
WITH CHECK OPTION;
~~~

Afterward, an UPDATE through the view attempting to set `status='cancelled'` will be rejected by CHECK OPTION, subject to updatability and view structure.

### 27.1. CHECK OPTION vs. CHECK Constraint

- `CHECK OPTION` applies to writes **through the qualifying view**.
- `CHECK (...)` constraints attach to tables and are enforced on all writes to the table.

If the source table is updated directly, the view's CHECK OPTION does not apply like a table constraint. Invariants that must hold across every write path belong in database constraints, RLS, or appropriate backend logic.

## 28. LOCAL and CASCADED CHECK OPTION

When one view builds on another, there are two check scopes:

- `WITH LOCAL CHECK OPTION` validates only the conditions of the **current view** per applicable rules.
- `WITH CASCADED CHECK OPTION` also validates conditions of underlying qualifying automatically updatable views in the chain.
- `WITH CHECK OPTION` defaults to cascaded mode in supported contexts.

Example:

~~~sql
CREATE VIEW view_lab.v_non_cancelled_base AS
SELECT
    order_id,
    customer_id,
    status,
    total_amount,
    placed_at
FROM view_lab.orders
WHERE status <> 'cancelled';

CREATE VIEW view_lab.v_large_visible_orders AS
SELECT
    order_id,
    customer_id,
    status,
    total_amount,
    placed_at
FROM view_lab.v_non_cancelled_base
WHERE total_amount >= 100000
WITH CASCADED CHECK OPTION;
~~~

Writes through `v_large_visible_orders` must satisfy both the total amount condition and the status condition across the automatically updatable view chain per CHECK OPTION rules.

### 28.1. Exceptions to Know

CHECK OPTION has limitations on views using `INSTEAD OF` triggers/rules and non-automatically-updatable views. Do not rely on CHECK OPTION as a complete policy engine for complex views.

If an invariant is critical, test write paths in staging and enforce data constraints at the appropriate layer.

## 29. Creating Temporary Views

A temporary view exists for the lifetime of a session per PostgreSQL rules:

~~~sql
CREATE TEMP VIEW temp_order_ids AS
SELECT order_id
FROM view_lab.orders
WHERE status = 'paid';
~~~

Query:

~~~sql
SELECT *
FROM temp_order_ids;
~~~

### 29.1. When Is It Appropriate?

- In-session experimentation.
- Ad-hoc data analysis.
- Workflows requiring short-lived objects.

Do not use temporary views as shared API contracts across connections.

### 29.2. Other Sessions Cannot See It

Temporary views live in a session's temporary schema. Connection pools maintain many backend sessions; a temp view created on connection A will not exist as the same object for connection B.

### 29.3. Names and Schemas

Temporary objects follow separate namespace rules; avoid naming them identically to important permanent objects and relying on `search_path` to guess which object PostgreSQL resolves.

## 30. Recursive Views Conceptually

PostgreSQL supports recursive view syntax in appropriate contexts, such as traversing hierarchies.

A clear way to learn recursive queries is to start by writing:

~~~sql
WITH RECURSIVE nums(n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1
    FROM nums
    WHERE n < 5
)
SELECT n
FROM nums;
~~~

You can then wrap such a query definition inside a view:

~~~sql
CREATE VIEW view_lab.v_numbers_1_to_5 AS
WITH RECURSIVE nums(n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1
    FROM nums
    WHERE n < 5
)
SELECT n
FROM nums;
~~~

This remains a regular view; results are computed at query time. Always ensure a termination condition to prevent runaway recursion.

The main focus of this lesson remains **creating, replacing, renaming, and dropping**, not optimizing every recursive query pattern.

## 31. DROP VIEW: Deleting Views

Syntax:

~~~sql
DROP VIEW view_lab.view_name;
~~~

Example with a standalone view created earlier:

~~~sql
DROP VIEW view_lab.v_orders_all;
~~~

This deletes the **view definition**, not the data in `view_lab.orders` referenced by the view.

### 31.1. Dropping Multiple Views in One Command

~~~sql
DROP VIEW
    view_lab.v_status_counts,
    view_lab.v_customer_revenue;
~~~

Only do this after confirming both views are no longer needed and have no dependent objects to preserve.

### 31.2. DROP VIEW Does Not Delete Source Tables

After:

~~~sql
DROP VIEW view_lab.v_order_public;
~~~

the `view_lab.orders` table still exists. Any DML previously executed through the view **does not roll back** when the view definition is dropped.

## 32. DROP VIEW IF EXISTS

Syntax:

~~~sql
DROP VIEW IF EXISTS view_lab.v_optional_report;
~~~

If the view does not exist, PostgreSQL does not treat it as a missing-object error and emits a NOTICE instead.

Useful in certain idempotent scripts, but must be used carefully.

### 32.1. IF EXISTS Does Not Permit Dropping the Wrong Object Type

If the name belongs to a **table** or another object type, `DROP VIEW IF EXISTS` will not drop that object as if it were a view.

### 32.2. IF EXISTS Can Mask Broken Migrations

In a production migration expected to drop a view that definitely exists, `IF EXISTS` can silently swallow a schema management error when the view is missing.

Use `IF EXISTS` when absence is an **expected valid state by design**, not to suppress all errors.

## 33. DROP VIEW RESTRICT: Default Dependency Protection

PostgreSQL defaults to **RESTRICT** behavior unless CASCADE is specified.

~~~sql
DROP VIEW view_lab.some_view RESTRICT;
~~~

If another view depends on it, PostgreSQL refuses the drop until dependent objects are addressed.

Lab example:

~~~sql
CREATE VIEW view_lab.v_order_summary_paid AS
SELECT
    order_id,
    customer_name,
    total_amount
FROM view_lab.v_order_summary
WHERE status = 'paid';
~~~

`v_order_summary_paid` depends on `v_order_summary`. Then:

~~~sql
-- Illustrates a statement blocked while dependencies exist:
DROP VIEW view_lab.v_order_summary;
~~~

PostgreSQL errors out because the dependent view still exists.

### 33.1. What Does RESTRICT Protect Against?

It prevents dropping a parent view from **silently** wiping out dependent objects.

In production, treat dependency errors as a **signal to investigate**, not a cue to immediately reach for CASCADE.

## 34. DROP VIEW CASCADE: Cascading Impact

Syntax:

~~~sql
DROP VIEW view_lab.v_order_summary CASCADE;
~~~

If dependent views or other database objects tracked by PostgreSQL exist, CASCADE drops them along the dependency graph.

Example:

~~~text
v_order_summary
        |
        +--> v_order_summary_paid
                  |
                  +--> v_paid_report_nested
~~~

Dropping `v_order_summary CASCADE` drops all dependent views in the chain.

### 34.1. Major Risks of CASCADE

- Deleting objects not in your intended target list.
- Breaking dashboards or applications relying on dependent views.
- Removing an active API contract layer.
- Breaking other migrations that depend on those objects.
- Losing metadata, grants, and comments attached to dropped views.

**Never treat CASCADE as a "fix dependency error" switch.** Before using it, inspect the **entire closure of dependent objects** and have a recovery plan.

### 34.2. CASCADE Does Not Drop Source Tables

Dropping a view with CASCADE does not make its source tables dependent on the view. Base tables normally **remain intact**. CASCADE targets objects **that depend on the view being dropped**, not objects the view reads from.

## 35. Dropping Dependent Views Manually in Order

When you want exact control over which objects are removed:

~~~sql
DROP VIEW view_lab.v_order_summary_paid;

DROP VIEW view_lab.v_order_summary;
~~~

Here the child view is dropped first, followed by the parent view.

### 35.1. Why Can Manual Ordering Be Better Than CASCADE?

- Explicit list of objects in the migration.
- Code reviewers see each view name being dropped.
- Fewer surprises if an unexpected new dependency appeared.
- Allows consumer migration steps between changes.

Still, manual migrations require full dependency verification and transactional execution where appropriate.

## 36. Dependencies Can Be View → View, Not Just View → Table

Example:

~~~text
orders (table)
  |
  v
v_paid_orders (view)
  |
  v
v_paid_orders_api (view)
  |
  v
Dashboard/SQL client
~~~

PostgreSQL tracks database-level object dependencies in system catalogs. External consumers such as Java source code, dashboard URLs, or queries in another service are not visible to PostgreSQL.

Therefore, you need **two dependency maps**:

1. **Database dependency graph**: views/rules/functions/objects tracked by catalogs.
2. **Application dependency graph**: code, ORMs, reports, jobs, BI tools, migrations.

A view with no catalog dependents **is not guaranteed** to have no active users.

## 37. Consequences of DROP + CREATE for Grants

Suppose role `app_reader` was granted permissions:

~~~sql
GRANT SELECT ON view_lab.v_paid_orders TO app_reader;
~~~

`app_reader` is a hypothetical role; the command runs only if the role exists and the caller has privileges.

If you replace the definition compatibly with `CREATE OR REPLACE VIEW`, grants on the existing view are preserved.

If you run:

~~~sql
DROP VIEW view_lab.v_paid_orders;
CREATE VIEW view_lab.v_paid_orders AS ...;
~~~

it creates a **new object**, and the old view's privileges are not automatically copied to the new object across DROP/CREATE. You must inspect and re-apply grants, ownership, comments, and options.

### 37.1. A Good Migration Checks More Than Just the SELECT

After modifying a view, verify:

- Which roles have SELECT?
- Do any roles have INSERT/UPDATE/DELETE?
- Is the owner right?
- Are `security_invoker`/`security_barrier` options intact?
- Are there RLS/privilege implications?
- Were object comments preserved?
- Are dependent views still valid?

## 38. Viewing Grants and Permissions on Views

You can query `information_schema.table_privileges` where visibility allows:

~~~sql
SELECT
    table_schema,
    table_name,
    grantee,
    privilege_type
FROM information_schema.table_privileges
WHERE table_schema = 'view_lab'
ORDER BY table_name, grantee, privilege_type;
~~~

Or inspect in psql:

~~~text
\dp view_lab.*
\d+ view_lab.v_paid_orders
~~~

Note that `information_schema` visibility depends on the caller's privileges and context.

### 38.1. Verify Privileges with the Application Role

A query succeeding as the migration owner does not prove the application has access. Test using a role and connection context matching the real application.

Never over-privilege an application role just to make a view query pass.

## 39. Row-Level Security and Views

If `view_lab.orders` has Row-Level Security enabled, policies interact with how views evaluate privileges:

- Default views follow owner-related privilege/policy rules.
- `security_invoker=true` views on supported versions use the caller's context for relevant checks.

Consequently, two views with the **exact same SELECT** can return different rows depending on roles and RLS configuration.

### 39.1. Do Not Use a View as the Sole Tenant Boundary Without Verification

For example:

~~~sql
CREATE VIEW view_lab.v_customer_101_orders AS
SELECT
    order_id,
    customer_id,
    status
FROM view_lab.orders
WHERE customer_id = 101;
~~~

This is a display filter, not a complete authorization/tenant-scoping system. Audit grants, RLS, and whether users can access base tables or other objects directly.

## 40. Attaching COMMENTs to Views and Columns

PostgreSQL lets you store descriptions:

~~~sql
COMMENT ON VIEW view_lab.v_paid_orders IS
'Order interface for paid or new status for learning example';
~~~

You can comment on columns as well:

~~~sql
COMMENT ON COLUMN view_lab.v_paid_orders.total_amount IS
'Order amount in the system currency unit';
~~~

Comments help administrators understand purpose and contracts.

### 40.1. Comments Are Not Constraints

Column descriptions are documentation, not value validation. Business rules require CHECK/NOT NULL/FK constraints, application logic, or policies.

### 40.2. DROP + CREATE Loses Previous Metadata

If you drop and recreate an object, comments must be reapplied. Therefore, for compatible definition updates, `CREATE OR REPLACE VIEW` is simpler and less disruptive.

## 41. Views in System Catalogs

PostgreSQL manages views in its metadata catalogs.

Key catalogs:

- `pg_class`: relation objects, including views with `relkind='v'`.
- `pg_namespace`: schemas containing views.
- `pg_attribute`: output columns and types.
- `pg_rewrite`: rules storing view query definitions.
- `pg_depend`: object dependency relationships.
- `pg_description`: comments.

Inspect views in `view_lab`:

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS view_name,
    c.oid AS view_oid,
    c.relkind
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'view_lab'
  AND c.relkind = 'v'
ORDER BY c.relname;
~~~

`relkind='v'` denotes a regular view. Materialized views use a different relkind code.

### 41.1. Never Edit pg_catalog Directly

Do not directly UPDATE `pg_class`, `pg_rewrite`, or `pg_depend` to rename, drop, or replace views. Always use official DDL commands so PostgreSQL keeps metadata and dependencies consistent.

## 42. Inspecting View Columns via information_schema

~~~sql
SELECT
    table_schema,
    table_name,
    column_name,
    ordinal_position,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'view_lab'
  AND table_name = 'v_paid_orders'
ORDER BY ordinal_position;
~~~

This query verifies:

- Column names.
- Column positions.
- Data types.
- Standard metadata attributes.

When you need exact PostgreSQL types (such as `NUMERIC(12,2)` or custom types), you can query `pg_catalog` or use `format_type`.

### 42.1. Querying Exact Column Types

~~~sql
SELECT
    a.attnum AS column_position,
    a.attname AS column_name,
    format_type(a.atttypid, a.atttypmod) AS sql_type
FROM pg_attribute AS a
WHERE a.attrelid = 'view_lab.v_paid_orders'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

This is a reliable way to inspect the current column interface before writing `CREATE OR REPLACE VIEW`.

## 43. Inspecting View Definitions with pg_get_viewdef

~~~sql
SELECT pg_get_viewdef(
    'view_lab.v_paid_orders'::regclass,
    TRUE
);
~~~

Useful when you need to:

- Inspect actual `WHERE`/`JOIN` logic.
- Verify a migration updated the query.
- Compare view definitions before and after.
- Identify base tables in readable syntax.

### 43.1. Do Not Expect Output to Match Original CREATE VIEW Verbatim

PostgreSQL reconstructs and normalizes query formatting. `pg_get_viewdef` does not necessarily return the exact migration SQL text, options, grants, or comments.

To reproduce a view faithfully in migrations, maintain the **source SQL definition** along with options, grants, comments, and dependencies in version control, rather than just copying text from `pg_get_viewdef`.

## 44. Dependencies in pg_depend

In PostgreSQL catalogs, a regular view's query definition is stored as a rewrite rule; dependencies on source tables and columns are attached to that rule.

Therefore, when querying dependencies, looking only for `pg_depend.objid = view_oid` will not reveal all underlying table references.

### 44.1. Example Query for View Rule Relation Dependencies

~~~sql
SELECT
    vn.nspname AS view_schema,
    vc.relname AS view_name,
    r.rulename,
    rn.nspname AS referenced_schema,
    rc.relname AS referenced_relation,
    d.refobjsubid AS referenced_column_number
FROM pg_rewrite AS r
JOIN pg_class AS vc
    ON vc.oid = r.ev_class
JOIN pg_namespace AS vn
    ON vn.oid = vc.relnamespace
JOIN pg_depend AS d
    ON d.classid = 'pg_rewrite'::regclass
   AND d.objid = r.oid
JOIN pg_class AS rc
    ON d.refclassid = 'pg_class'::regclass
   AND d.refobjid = rc.oid
JOIN pg_namespace AS rn
    ON rn.oid = rc.relnamespace
WHERE vn.nspname = 'view_lab'
  AND vc.relkind = 'v'
  AND r.rulename = '_RETURN'
  AND rc.oid <> vc.oid
ORDER BY vc.relname, rc.relname, d.refobjsubid;
~~~

This query is meant to **observe relation dependencies** of view rewrite rules. It is not an exhaustive dependency-graphing tool for every object type, and may return multiple rows per referenced table when multiple columns are referenced.

Never assume this query alone makes `DROP ... CASCADE` safe in production. You must examine the full dependency closure, including consumers outside the database.

## 45. information_schema.views and pg_views

You can inspect views via the relatively standard interface:

~~~sql
SELECT
    table_schema,
    table_name,
    view_definition,
    check_option,
    is_updatable
FROM information_schema.views
WHERE table_schema = 'view_lab'
ORDER BY table_name;
~~~

`information_schema` enforces privilege-based visibility rules, so results seen by restricted roles may differ from PostgreSQL-specific metadata in system catalogs.

`pg_views` is convenient for PostgreSQL view metadata; `pg_get_viewdef` inspects definitions by specific object.

### 45.1. Distinguish Nonexistent Views from Missing Permissions

If an application role cannot see a view in a metadata query, do not immediately assume the object was dropped. Check the schema, `search_path`, role/privileges, and metadata visibility rules.

## 46. Performance When Modifying Views

Because regular views store query definitions rather than cached results, changing a view's `SELECT` can alter the execution plans of every consumer.

For example, adding a filter:

~~~sql
CREATE OR REPLACE VIEW view_lab.v_order_summary AS
SELECT
    o.order_id,
    c.customer_name,
    o.status,
    o.total_amount,
    o.placed_at
FROM view_lab.orders AS o
JOIN view_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.status IN ('paid','new');
~~~

Then:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM view_lab.v_order_summary
WHERE total_amount >= 100000;
~~~

You may see the planner choose `Seq Scan`, `Index Scan`, `Hash Join`, `Nested Loop`, or another strategy. Views do not guarantee a fixed execution plan.

### 46.1. Indexes Live on Source Tables

For regular views, read optimizations typically come from indexes on base tables or query rewrites, not creating indexes directly on regular views:

~~~sql
CREATE INDEX idx_orders_status_amount
ON view_lab.orders(status, total_amount);
~~~

Never assume an index will automatically be used. Measure `EXPLAIN`/`BUFFERS` and DML overhead before deploying indexes to production.

### 46.2. security_barrier Can Affect the Planner

If a barrier is enabled, predicate pushdown behavior may change. For views serving access control, validate both security correctness and query latency.

## 47. Creating a New View for Incompatible Interface Changes

When you must:

- Remove a column currently in use.
- Rename a public column.
- Change a column type from BIGINT to TEXT or vice versa.
- Change a column's meaning.
- Reorder columns that consumers rely on.

`CREATE OR REPLACE VIEW` generally **cannot** handle this safely.

A cleaner strategy:

~~~sql
CREATE VIEW view_lab.v_order_summary_v2 AS
SELECT
    o.order_id,
    o.customer_id AS buyer_id,
    c.customer_name,
    o.total_amount::NUMERIC(14,2) AS amount_v2
FROM view_lab.orders AS o
JOIN view_lab.customers AS c
    ON c.customer_id = o.customer_id;
~~~

Keep the old `v_order_summary` while migrating applications to `v_order_summary_v2`. Once you are sure no old consumers remain, drop the old view and its dependencies according to plan.

### 47.1. Advantages of Versioned Views

- Consumers get a transition window.
- Columns are not renamed or retyped underneath running applications.
- Old and new views can run side-by-side for result comparison.
- Consumers can easily roll back to the old name.
- Grants on v2 can be configured before cutover.

In return, you must manage the lifecycle of both versions and verify semantic consistency as required.

## 48. Expand–Migrate–Contract for Views

A safe schema change strategy typically breaks into phases:

**Expand:**

~~~text
Create view v2 or append compatible columns to the old view.
Keep existing consumers working.
~~~

**Migrate:**

~~~text
Update applications/dashboards/jobs to use the new column or view.
Measure correctness, permissions, and performance.
~~~

**Contract:**

~~~text
Once no old consumers remain,
remove the old compatibility view/column via a controlled migration.
~~~

### 48.1. Avoid Uncoordinated Renames During Deployments

If a new deployment queries `v_order_summary_v2` before the database migration creates it, the app fails. Conversely, if the old view is renamed too early, older application instances fail.

Sequence migrations and deployments so multiple application versions can coexist cleanly.

## 49. ALTER VIEW RENAME and Rolling Deployments

Suppose production has two active application versions running side-by-side:

- App A queries `v_order_summary`.
- App B queries `v_order_summary_v2`.

If you simply run:

~~~sql
ALTER VIEW view_lab.v_order_summary
RENAME TO v_order_summary_v2;
~~~

App A immediately loses the old name and fails. Renaming **replaces the object name**; it does not create two endpoints.

A smoother migration path:

1. Create v2 under the new name.
2. Grant permissions on v2.
3. Deploy App B using v2.
4. Confirm no App A instances remain.
5. Drop v1 after checking dependencies.

Do not assume `ALTER VIEW RENAME` is safe for zero-downtime rollouts just because it executes quickly.

## 50. Locks and Concurrent Queries During DDL

`CREATE OR REPLACE VIEW`, `ALTER VIEW`, and `DROP VIEW` acquire appropriate locks so PostgreSQL updates metadata consistently.

Operational impacts can include:

- DDL waiting on active queries/transactions.
- Concurrent queries queuing behind DDL.
- Migrations holding locks until transaction end.
- Connection pools needing to reparse/replan prepared statements.
- Slowdowns or errors if consumers access the object during schema transitions.

### 50.1. Set Explicit Timeouts

A migration test example:

~~~sql
BEGIN;

SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '30s';

ALTER VIEW view_lab.v_order_state_current
RENAME TO v_order_state_final;

COMMIT;
~~~

This snippet **only runs if `v_order_state_current` currently exists** per the example sequence. In production, set timeouts and rollback policies aligned with your SLOs.

### 50.2. Never Leave a DDL Transaction Idle

A transaction after DDL holds locks until commit or rollback. Prepare reviewable scripts, run them at the right maintenance window, and finish transactions promptly.

## 51. Backup and Rollback Before View Changes

In production migrations, record:

- Current running CREATE VIEW definition.
- Owner and grants.
- Comments.
- View options.
- List of dependent objects.
- Consuming applications and queries.
- Plan to restore the old name/definition.
- Rollback strategy compatible with new data/schemas.

### 51.1. DDL Rollback Differs from Application Rollback

If a migration has COMMITted and the app deploy fails, you cannot simply ROLLBACK the prior transaction. You need a **recovery migration** or versioned-view strategy so the app can revert.

If a source column was already dropped or data changed incompatibly, restoring the old view may no longer be straightforward. Always evaluate dependencies in both directions.

## 52. Uppercase Names, Spaces, and Quoting Identifiers

PostgreSQL folds unquoted identifiers to lowercase per standard rules.

~~~sql
CREATE VIEW view_lab.V_My_Report AS
SELECT order_id
FROM view_lab.orders;
~~~

The actual stored name is folded according to unquoted identifier rules, resulting in `v_my_report`.

If created with double quotes:

~~~sql
CREATE VIEW view_lab."V_My_Report" AS
SELECT order_id
FROM view_lab.orders;
~~~

you must reference it with exact case and quotes:

~~~sql
SELECT *
FROM view_lab."V_My_Report";
~~~

### 52.1. Naming Recommendation

Prefer unquoted lowercase `snake_case`, such as:

- `v_order_summary`.
- `v_paid_orders`.
- `v_customer_revenue`.

This reduces friction in SQL migrations, ORM mappings, and scripts.

### 52.2. Never Concatenate Untrusted Input into Identifiers

Bind parameters like `$1`/`?` are for **values**, not view, schema, or column names. If an application must pick among several views, use an allowlist of valid names or fixed SQL templates; never concatenate user input directly into DDL.

## 53. Common Errors with CREATE VIEW

### 53.1. Schema Does Not Exist

~~~sql
CREATE VIEW not_existing_schema.v_report AS
SELECT 1 AS id;
~~~

fails if the schema has not been created or is inaccessible. Ensure a valid `CREATE SCHEMA` runs first.

### 53.2. View Name Already Exists

~~~sql
CREATE VIEW view_lab.v_paid_orders AS
SELECT ...;
~~~

fails with a duplicate relation error if the view already exists. For compatible definition updates, use `CREATE OR REPLACE VIEW`.

### 53.3. Duplicate Column Names

If two expressions produce indistinguishable column names in the view definition, PostgreSQL errors or causes ambiguity. Assign unique, descriptive aliases.

### 53.4. Missing Privileges or Invalid Object References

The role needs privileges to create the view and reference its source objects. Never fix this by granting superuser to an application role.

### 53.5. SELECT * After Source Table Changes

The old view will not automatically include new columns. Run a migration updating its definition when you want to expose those fields.

## 54. Common Errors with CREATE OR REPLACE VIEW

### 54.1. Renaming an Existing Column

An error like "cannot change name of view column" indicates you need `ALTER VIEW ... RENAME COLUMN`, or a new view version if it is a public breaking change.

### 54.2. Changing a Column Type

If the old view returned NUMERIC and the new definition returns TEXT, OR REPLACE will be rejected. Preserve the type with an explicit cast or create v2.

### 54.3. Changing Column Order

Keep all existing columns in the exact same order; only append new columns at the end.

### 54.4. Accidentally Changing Semantics

A new SELECT with matching column names and types can still alter WHERE/JOIN filters, double row counts, or expose sensitive data.

### 54.5. Failing to Test Permissions After Replacement

View ownership, security options, and source table permissions affect what application roles see; do not test solely as the owner.

## 55. Common Errors with ALTER VIEW

### 55.1. Renaming via CREATE OR REPLACE

Use `ALTER VIEW ... RENAME TO` or `RENAME COLUMN` instead of changing aliases directly in OR REPLACE for existing columns.

### 55.2. Renaming Breaks Clients

PostgreSQL creates no compatibility alias for the old name. Migrate consumers or maintain a versioned view.

### 55.3. SET SCHEMA While Leaving Schema-Qualified SQL Behind

Applications still calling `old_schema.view_name` will fail. Update them or provide an appropriate wrapper.

### 55.4. Role Lacks ALTER Privileges

Ownership and privileges on the target schema must be sufficient. Do not confuse SELECT privilege with structural alteration rights.

### 55.5. Changing security_invoker Without Testing RLS

This can cause SELECT queries to return fewer rows or fail with permission errors when the application role lacks source table privileges.

## 56. Common Errors with DROP VIEW

### 56.1. DROP VIEW Rejected Due to Dependencies

This is RESTRICT behavior protecting dependent objects. Inspect dependencies and drop or update child objects intentionally.

### 56.2. Turning On CASCADE Immediately After an Error

This can wipe out multiple other views. Before using CASCADE, inspect every object that will be affected.

### 56.3. Running DROP VIEW on a Table or Materialized View

Use the matching command for each object type. `IF EXISTS` does not allow dropping the wrong object kind.

### 56.4. DROP + CREATE Without Reapplying Grants

The new object does not inherit grants, comments, or ownership from the dropped view. Application users will encounter permission denied errors.

### 56.5. Overlooking External Consumers

A view with zero catalog dependents can still be queried by Java apps, cron jobs, or BI dashboards. Monitor live usage and search SQL across repositories and configs.

## 57. Testing the Full View Lifecycle in a Dedicated Lab

A small, isolated lab independent of the main example names:

~~~sql
-- Create view:
CREATE VIEW view_lab.v_lifecycle AS
SELECT
    order_id,
    status
FROM view_lab.orders;

-- Change logic, keeping names/types/order of the 2 columns:
CREATE OR REPLACE VIEW view_lab.v_lifecycle AS
SELECT
    order_id,
    status
FROM view_lab.orders
WHERE status <> 'cancelled';

-- Append a column at the end:
CREATE OR REPLACE VIEW view_lab.v_lifecycle AS
SELECT
    order_id,
    status,
    total_amount
FROM view_lab.orders
WHERE status <> 'cancelled';

-- Rename a column:
ALTER VIEW view_lab.v_lifecycle
RENAME COLUMN status TO order_status;

-- Rename view:
ALTER VIEW view_lab.v_lifecycle
RENAME TO v_lifecycle_v2;

-- Inspect definition:
SELECT pg_get_viewdef(
    'view_lab.v_lifecycle_v2'::regclass,
    TRUE
);

-- Query data:
SELECT *
FROM view_lab.v_lifecycle_v2
ORDER BY order_id;

-- Drop view:
DROP VIEW view_lab.v_lifecycle_v2;
~~~

### 57.1. Why Is This a Good Lab?

It demonstrates a complete lifecycle:

~~~text
CREATE
  |
  v
CREATE OR REPLACE (modify WHERE)
  |
  v
CREATE OR REPLACE (append column at end)
  |
  v
ALTER VIEW RENAME COLUMN
  |
  v
ALTER VIEW RENAME TO
  |
  v
pg_get_viewdef / SELECT
  |
  v
DROP VIEW
~~~

It avoids CASCADE, leaves base table data untouched, and uses dedicated lab view names.

### 57.2. Do Not Re-Run Without Resetting

If interrupted mid-way, the existing view name may differ. Check current state via `pg_views`/`\dv` before continuing. Never use DROP CASCADE to "clean up quickly" without knowing what objects exist.

## 58. Testing Dependencies Before Dropping

A separate lab:

~~~sql
CREATE VIEW view_lab.v_parent_demo AS
SELECT order_id, status
FROM view_lab.orders;

CREATE VIEW view_lab.v_child_demo AS
SELECT order_id
FROM view_lab.v_parent_demo
WHERE status = 'paid';
~~~

Command:

~~~sql
-- Expected to be rejected because child still exists:
DROP VIEW view_lab.v_parent_demo RESTRICT;
~~~

Instead of CASCADE, drop in controlled order:

~~~sql
DROP VIEW view_lab.v_child_demo;

DROP VIEW view_lab.v_parent_demo;
~~~

### 58.1. Takeaways

- `RESTRICT` protects dependencies.
- `CASCADE` has broad reach; understand its consequences.
- Dropping child before parent is a reviewable strategy.
- Base table `view_lab.orders` is not deleted.

## 59. Where Should Migration Scripts Be Idempotent?

Not every command needs `IF EXISTS` or `OR REPLACE`.

- Migrations creating **new** objects should normally fail if the object unexpectedly exists, catching state drift.
- Migrations intentionally updating a view compatibly use `CREATE OR REPLACE VIEW`.
- Optional cleanup scripts can use `DROP VIEW IF EXISTS` when absence is an expected state.
- Breaking migrations should explicitly create v2, deploy/migrate consumers, and drop v1.
- Renames must use `ALTER VIEW RENAME` with a clearly planned consumer cutover.

**Idempotency** does not mean "ignore all errors." It is an intentional property of specific steps in a deployment pipeline.

## 60. Managing Views with Migration Tools

Java applications often use migration tools like Flyway or Liquibase. Regardless of tool, the core SQL DDL remains:

~~~sql
CREATE VIEW ... AS SELECT ...;

CREATE OR REPLACE VIEW ... AS SELECT ...;

ALTER VIEW ... RENAME TO ...;

ALTER VIEW ... RENAME COLUMN ... TO ...;

DROP VIEW ...;
~~~

A migration should:

1. Execute in deterministic order.
2. Be code-reviewed.
3. Be tested against production-like schemas and data.
4. Check dependent views and consumers.
5. Include grants, ownership, options, and comments.
6. Have a pre-evaluated rollback/fallback plan.
7. Never use CASCADE automatically without explicit approval.

### 60.1. SQL View Definitions Are Code

Store full definitions in version control rather than treating views as ad-hoc objects edited in an admin UI. This explains why logic changed and reproduces schemas cleanly across new environments.

## 61. Evaluating Compatibility of a View Change

A quick decision table:

| Change | Typical Command | Risks to Check |
|---|---|---|
| Modify WHERE, keep columns | `CREATE OR REPLACE VIEW` | Results, performance, permissions |
| Modify JOIN, keep columns | `CREATE OR REPLACE VIEW` | Cardinality, duplicate rows |
| Append column at end | `CREATE OR REPLACE VIEW` | SELECT */ORM consumers |
| Rename view | `ALTER VIEW ... RENAME TO` | SQL clients using old name |
| Rename column | `ALTER VIEW ... RENAME COLUMN` | APIs/ORMs using old name |
| Change view schema | `ALTER VIEW ... SET SCHEMA` | search_path, grants, qualified names |
| Change owner | `ALTER VIEW ... OWNER TO` | Privilege/security behavior |
| Modify security options | `ALTER VIEW ... SET (...)` | Permissions, RLS, planner |
| Change type / drop old column | Create view v2, migrate consumers | Breaking change, dependencies |
| Drop unused view | `DROP VIEW ... RESTRICT` | Internal/external DB dependencies |
| Drop verified view tree | `DROP VIEW ... CASCADE` in controlled scenarios | Unintended deletion of dependent objects |

These are guiding options, not blind rules to apply without checking actual state.

## 62. Checklist Before CREATE/REPLACE/RENAME/DROP

**Before CREATE:**

- Does the target schema exist?
- Is the view name already used by another object?
- Are output columns clearly named and typed?
- Does the query return the right semantics and row count?
- Does the creating role have sufficient privileges?
- Are security options or check options needed?
- Are GRANTs and COMMENTs needed after creation?

**Before REPLACE:**

- Do existing columns keep their names, order, and types?
- Are new columns only appended at the end?
- Do child views remain functional?
- Do query results before and after match expectations?
- Did the plan or performance change significantly?
- Do application roles still have access?
- Is there a transaction and rollback plan?

**Before RENAME:**

- Does the new name collide with an existing object?
- Which apps, ORMs, or reports use the old name?
- Are two parallel versions needed?
- Were column names changed in mappings?
- Are `search_path` and schema-qualified SQL updated?
- Do docs, migrations, or monitoring need updates?

**Before DROP:**

- Is the view unused both inside and outside the DB?
- What are its catalog dependents?
- Is `RESTRICT` safe?
- If using CASCADE, have all dependent objects been verified?
- Are definitions, grants, and comments backed up for recovery?
- Will it run in a safe window with lock timeouts?
- Is application error monitoring active after deployment?

## 63. Practice Exercises

### Exercise 1 — Simple View

Create a view `v_new_orders` showing only orders with status `new`.

**Hint:** `CREATE VIEW ... AS SELECT ... WHERE status='new'`.

### Exercise 2 — JOIN View

Create a view returning `order_id`, `customer_name`, and `total_amount`.

**Hint:** JOIN orders with customers on `customer_id`.

### Exercise 3 — GROUP BY View

Create a view totaling paid amounts per `customer_id`.

**Hint:** `SUM(...) FILTER (WHERE status='paid')`.

### Exercise 4 — Aliases

An expression `total_amount*1.05` needs the name `amount_with_fee`. Write the CREATE VIEW statement with the proper alias.

**Hint:** `AS amount_with_fee`.

### Exercise 5 — Column Name List

Use `CREATE VIEW name(col1,col2) AS SELECT ...` to name two output columns.

**Hint:** names in the list follow SELECT order.

### Exercise 6 — Why Avoid SELECT *

Why does adding a new column to a base table not automatically add that column to a view created with `SELECT *`?

**Hint:** the view definition stores the output column list resolved at creation time.

### Exercise 7 — OR REPLACE

Modify the WHERE clause of an existing view while keeping column names, types, and order unchanged.

**Hint:** `CREATE OR REPLACE VIEW`.

### Exercise 8 — Adding a Column

You want to add `status` to an existing four-column view. Where should you place it?

**Hint:** at the end of the column list.

### Exercise 9 — Renaming a Column

Rename `customer_id` to `buyer_id` on a view.

**Hint:** `ALTER VIEW ... RENAME COLUMN customer_id TO buyer_id`.

### Exercise 10 — Changing Types

Can you change `total_amount NUMERIC` to TEXT at the same position using OR REPLACE?

**Hint:** not arbitrarily; create v2 for breaking changes.

### Exercise 11 — Renaming a View

Rename `v_report_old` to `v_report_new`.

**Hint:** `ALTER VIEW ... RENAME TO v_report_new`.

### Exercise 12 — Old Names After Rename

After RENAME, do clients using the old name continue working automatically?

**Hint:** no automatic alias is created.

### Exercise 13 — SET SCHEMA

Move a view from `view_lab` to `view_reporting`.

**Hint:** `ALTER VIEW view_lab.view_name SET SCHEMA view_reporting`.

### Exercise 14 — Ownership

Why does GRANT SELECT not let a role run ALTER VIEW?

**Hint:** ownership/DDL administration differs from SELECT privilege.

### Exercise 15 — security_invoker

Whose context does `security_invoker=true` apply when checking source object permissions?

**Hint:** the caller; check PostgreSQL version and RLS.

### Exercise 16 — security_barrier

Why shouldn't you enable security_barrier on every view without measuring?

**Hint:** affects security/predicate pushdown/performance.

### Exercise 17 — Auto-Updatable

Can a simple single-table view be UPDATEd?

**Hint:** yes, if it meets PostgreSQL's conditions.

### Exercise 18 — GROUP BY Views

Can an aggregated GROUP BY view automatically UPDATE rows in the underlying table normally?

**Hint:** generally not automatically updatable.

### Exercise 19 — WITH CHECK OPTION

What does a view's CHECK OPTION protect when writing through the view?

**Hint:** enforces the view's visibility predicate.

### Exercise 20 — CHECK OPTION vs. CHECK Constraint

Why does CHECK OPTION not replace table CHECK constraints?

**Hint:** writes through a view differ in scope from direct table writes.

### Exercise 21 — Temp Views

Does a temp view created on connection A automatically exist on connection B?

**Hint:** no, it is session-scoped.

### Exercise 22 — DROP VIEW

Does DROP VIEW delete rows from the base table?

**Hint:** no, it removes the view definition.

### Exercise 23 — IF EXISTS

What are the benefits and risks of `DROP VIEW IF EXISTS`?

**Hint:** avoids errors when an optional view is absent, but can mask broken migration states.

### Exercise 24 — RESTRICT

A parent view has a dependent child view. What happens by default when dropping the parent view?

**Hint:** rejected due to dependency.

### Exercise 25 — CASCADE

Why is `DROP VIEW ... CASCADE` dangerous?

**Hint:** it can delete dependent database objects.

### Exercise 26 — Manual Order

If a child view depends on a parent view and you want to drop both, which do you drop first?

**Hint:** child before parent.

### Exercise 27 — External Consumers

Does finding zero catalog dependencies prove a view is no longer used by applications?

**Hint:** no; inspect code, BI tools, and jobs.

### Exercise 28 — GRANTs After DROP/CREATE

Why might an app hit permission denied after dropping and recreating a view with the same name?

**Hint:** the new object does not automatically retain grants from the dropped object.

### Exercise 29 — pg_views

Write a query retrieving definitions of views in schema `view_lab`.

**Hint:** `SELECT ... FROM pg_views WHERE schemaname='view_lab'`.

### Exercise 30 — pg_get_viewdef

How do you inspect a view's definition using its qualified name?

**Hint:** `pg_get_viewdef('schema.view'::regclass, true)`.

### Exercise 31 — View relkind

In `pg_class`, what is `relkind` for a regular view?

**Hint:** `'v'`.

### Exercise 32 — Rewrite Dependencies

Why can searching dependencies solely by view OID miss query references?

**Hint:** view definitions are stored via `pg_rewrite`/rules.

### Exercise 33 — EXPLAIN

Does creating a view automatically cache results and speed up JOINs?

**Hint:** regular views are stored queries, not materialized results.

### Exercise 34 — Compatible Migrations

Why can appending an output column at the end be valid SQL yet still break ORMs using SELECT *?

**Hint:** consumers depend on shape and column count.

### Exercise 35 — Versioned Views

When you need to change a column type or remove a column, why is creating v2 safer than dropping v1 immediately?

**Hint:** allows gradual consumer cutover and easier rollback.

### Exercise 36 — Rolling Deploys

What is the risk of renaming a view while two application versions are running concurrently?

**Hint:** the older app version still queries the old name.

### Exercise 37 — Lock Timeout

What is the benefit of setting `SET LOCAL lock_timeout` before ALTER VIEW inside a transaction?

**Hint:** caps unintended lock wait durations.

### Exercise 38 — Quoting

What is the difference between unquoted `V_Report` and double-quoted `"V_Report"`?

**Hint:** case folding vs. case-sensitive identifier.

### Exercise 39 — Comments

Write a COMMENT ON VIEW describing a view's purpose.

**Hint:** `COMMENT ON VIEW schema.view IS '...';`.

### Exercise 40 — Migration Review

List at least seven checks to perform before dropping a production view.

**Hint:** dependents, consumers, grants, schema, backup, locks, rollback, monitoring.

## 64. Frequently Asked Questions

### Do VIEWs store SELECT results automatically?

Regular views store query definitions, not separate result copies. Materialized views are distinct objects with their own REFRESH lifecycle.

### If base table data changes, do I need to recreate the view?

No. Regular views read current data at query time per transaction snapshot. You only update a view when changing its **SELECT logic/interface**, options, or metadata.

### Can CREATE OR REPLACE VIEW change everything?

No. Existing columns must keep their names, order, and types, except new columns may be appended at the end. Renaming uses ALTER VIEW; type changes or column removals generally need another migration strategy.

### Does OR REPLACE wipe GRANT privileges?

It replaces the definition on the existing view, so object grants and ownership are preserved. DROP + CREATE creates a new object requiring metadata to be re-established.

### Can you rename a view that has dependent views?

PostgreSQL manages internal dependencies by object identity, so renaming keeps dependent views valid. However, external application SQL referencing the old name is not updated automatically.

### Does ALTER VIEW RENAME TO change schemas?

No. Use `SET SCHEMA` to move a view across schemas.

### Does DROP VIEW default to CASCADE?

No. The default is `RESTRICT`: dropping is rejected while dependent objects exist.

### Does DROP VIEW CASCADE delete source tables?

Not by default. It drops objects that depend on the view according to catalog dependencies; source tables do not depend on the view.

### When should I use DROP VIEW IF EXISTS?

When an optional view may legitimately be absent, such as multi-state cleanup scripts. Do not use it to silently ignore migration drift.

### Can views update tables directly?

Some simple views are automatically updatable; complex aggregated/JOIN views typically are not. `INSTEAD OF` triggers/rules can be used in appropriate designs. Permissions and constraints still apply.

### Does security_invoker=true work on all PostgreSQL versions?

No. It was introduced in PostgreSQL 15. Check your running version and permission/RLS semantics before adopting it.

### Can ALTER VIEW cause lock waits?

DDL requires locks; with long transactions or concurrent queries, it can wait or block traffic. Plan migrations, timeouts, and execution windows accordingly.

### Do VIEWs use indexes?

Regular views have no indexes of their own. The planner can leverage base table indexes when executing view queries; verify with EXPLAIN.

### Should every view migration use DROP + CREATE?

Not by default. For compatible changes, `CREATE OR REPLACE VIEW` avoids breaking dependencies and grants. For breaking changes, consider v2 and migrate consumers gradually.

## 65. Summary

Core commands:

~~~sql
-- Create:
CREATE VIEW schema_name.view_name AS
SELECT ...;

-- Replace definition compatibly:
CREATE OR REPLACE VIEW schema_name.view_name AS
SELECT ...;

-- Rename view:
ALTER VIEW schema_name.old_name
RENAME TO new_name;

-- Rename column:
ALTER VIEW schema_name.view_name
RENAME COLUMN old_column TO new_column;

-- Move schema:
ALTER VIEW old_schema.view_name
SET SCHEMA new_schema;

-- Drop (defaults to RESTRICT):
DROP VIEW schema_name.view_name;

-- Skip if nonexistent:
DROP VIEW IF EXISTS schema_name.view_name;

-- Drop including dependent objects (only when verified):
DROP VIEW schema_name.view_name CASCADE;
~~~

Key principles to remember:

1. **Regular views are named queries**, not materialized data copies.
2. **`CREATE VIEW`** builds reusable read/computed interfaces over one or more tables.
3. **`CREATE OR REPLACE VIEW`** works when modifying SQL logic while preserving existing column names, order, and types; new columns can be appended at the **end**.
4. **Renaming views or columns** uses `ALTER VIEW ... RENAME`, never OR REPLACE for renaming old columns.
5. **Changing types or removing old columns** is a breaking change; evaluate view v2 and expand–migrate–contract.
6. **`DROP VIEW` defaults to RESTRICT**; treat dependency errors as signals to investigate, not triggers to blindly use CASCADE.
7. **`DROP VIEW ... CASCADE`** drops dependent views/objects, but **does not drop source tables**.
8. **DROP + CREATE is not equivalent to OR REPLACE**: grants, ownership, comments, dependencies, and object identity change.
9. **Regular views have no dedicated indexes**; inspect EXPLAIN and base table indexes when tuning.
10. **View permissions, `security_invoker`, `security_barrier`, and RLS** shape what data application roles can see.
11. **DDL carries locking and transaction semantics**, requiring controlled migrations and rollback plans in production.
12. **Catalog dependencies miss external consumers**; audit applications, jobs, reports, and BI tools too.
13. **Versioned views** enable planned interface transitions during rolling deployments instead of abrupt renames or drops.
14. **Metadata** via `pg_views`, `pg_get_viewdef`, `information_schema`, and `pg_catalog` lets you verify view state before and after changes.

A safe lifecycle:

~~~text
Define requirements and output columns
              |
              v
      CREATE VIEW
              |
              v
  Apply SELECT / GRANT / COMMENT
              |
              v
      Need to change?
        /             \
       /               \
Compatible change   Breaking change
       |               |
 CREATE OR REPLACE   Create view v2
       |               |
       |          Migrate consumers
       \               /
        \             /
         Verify permissions, results,
         performance, and dependencies
                  |
                  v
        When old view is no longer used:
        DROP VIEW ... RESTRICT
                  |
                  v
           Monitor after deploy
~~~

By clearly distinguishing between **replacing a definition**, **modifying name metadata**, and **dropping an object**, you can manage PostgreSQL views as stable schema interfaces while rolling out changes deliberately without breaking dependent queries.
