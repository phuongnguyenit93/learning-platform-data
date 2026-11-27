# Views as Query Interfaces and Data Abstraction Layers in PostgreSQL

An e-commerce application stores order information in the `orders` table and customer information in the `customers` table. Every time it displays a list of orders, the application has to JOIN the two tables, rename columns, exclude internal fields, filter data by status, and format values to return to the UI.

If multiple services and reports each write this JOIN query on their own, renaming a column or moving customer information to a new table can force dozens of queries to be updated at once. Some services might also forget the tenant filter, accidentally select sensitive fields, or calculate metrics inconsistently.

A **view** in PostgreSQL solves part of that problem by turning a named `SELECT` query into a **query interface that can be used like a relation**:

```sql
CREATE VIEW reporting.v_order_summary AS
SELECT
    o.order_id,
    o.ordered_at,
    c.display_name AS customer_name,
    o.status,
    o.amount
FROM application.orders AS o
JOIN application.customers AS c
  ON c.customer_id = o.customer_id;
```

The application then queries:

```sql
SELECT order_id, customer_name, status, amount
FROM reporting.v_order_summary
WHERE status = 'PAID'
ORDER BY ordered_at DESC
LIMIT 20;
```

A view acts as a **read data contract** between storage and consumption. Consumers do not need to repeat every JOIN detail, physical table name, or computed column formula.

However, it is important to understand accurately:

- A regular view **does not pre-store the full SELECT result** and **is not a cache**.
- A view does not automatically make queries faster or turn an incorrect query into a correct one.
- A view does not automatically provide complete access control if permissions on the base tables, ownership, or Row-Level Security are configured improperly.
- Not every view is updatable via `INSERT`, `UPDATE`, or `DELETE`.
- A view interface can remain stable across certain schema changes, yet still has **dependencies on data types, column names, permissions, and semantics**.

This lesson belongs to the **View** chapter of the **Database Engine Relational PostgreSQL** module, focusing on **views as query interfaces and data abstraction layers**: building a SELECT contract, separating the storage model from the read model, managing changes and access permissions, understanding updatability/performance, and organizing views for long-term application use.

---

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain what a view is, how PostgreSQL processes a regular view, and distinguish it from a physical table.
2. Use `CREATE VIEW`, `CREATE OR REPLACE VIEW`, `ALTER VIEW`, and `DROP VIEW` within the proper scope.
3. Design a **read model** across multiple tables, standardize column names, and hide internal schema details.
4. Create derived columns, filter conditions, and aggregations with business meaning inside a view.
5. Distinguish between a **structurally stable interface** and a **semantically stable interface**.
6. Understand a view's dependencies on underlying tables/columns/functions, especially during schema changes.
7. Recognize the limitations of `CREATE OR REPLACE VIEW` regarding existing column names, order, and types.
8. Explain the difference between **automatically updatable** views and read-only views based on query structure.
9. Use `WITH LOCAL CHECK OPTION` and `WITH CASCADED CHECK OPTION` in appropriate scenarios.
10. Understand default view permission mechanics, `security_invoker`, `security_barrier`, and Row-Level Security considerations.
11. Use views as a least-privilege read access layer without confusing them with a complete security mechanism.
12. Use `EXPLAIN (ANALYZE, BUFFERS)` to observe how the planner executes queries through a view.
13. Distinguish between regular views, materialized views, CTEs, SQL functions, and physical summary tables.
14. Design naming, versioning, testing, and safe migration strategies for views serving multiple applications.
15. Know when a view reduces coupling and when too many view layers make a system harder to understand.

**Scope:** Modern PostgreSQL. Some features such as `security_invoker` have version constraints (supported starting in PostgreSQL 15). All examples involving role creation, granting permissions, or DDL operations must be run in an authorized environment. Lab examples can be recreated from scratch in a dedicated schema; never run schema-drop commands on production.

---

## 2. What Is a View?

A view is a **schema object defined by a query**. Users can reference the view name in many places just as they would reference a table:

```sql
SELECT * FROM some_schema.some_view;
```

However, behind the view name there is not necessarily a heap storing result rows. With a **regular view**, PostgreSQL stores the **query definition and metadata**, and processes the query against the underlying data when the statement is executed.

Diagram:

```text
Application / JDBC / reports
           |
           | SELECT ... FROM api.v_order_read_model
           v
+-------------------------------------------+
| View: api.v_order_read_model               |
| - public name and column list              |
| - SELECT definition                        |
| - permissions and view options             |
+-------------------------------------------+
           |
           | Planner/rewrite processes query
           v
+-----------------+      +------------------+
| internal.orders | JOIN | internal.customers|
+-----------------+      +------------------+
           |
           v
     Result rows according to SELECT snapshot
```

### 2.1. A View as a Name for a Query

If three reports each have to write on their own:

```sql
SELECT
    o.order_id,
    c.display_name,
    o.status,
    o.amount
FROM internal.orders AS o
JOIN internal.customers AS c
  ON c.tenant_id = o.tenant_id
 AND c.customer_id = o.customer_id;
```

then a view can centralize that JOIN definition in one place.

### 2.2. A View as an Abstraction Layer

Abstraction here means the application depends on:

- A stable view name.
- The column names, order, types, and meaning exposed by the view.
- Access permissions on the view.
- Contracts regarding units, timezones, statuses, and data completeness.

The application **does not necessarily** need to know physical table names, multi-table relational structures, or the fields used to compute derived columns.

### 2.3. A View Is Not an Immutable Snapshot

When base tables change and transactions commit, querying the view under an appropriate snapshot reflects the new data. A regular view is not a storage location holding old data from when the view was created.

### 2.4. A View Name Does Not Guarantee Correctness

If a view defines a JOIN with the wrong tenant key, uses an incorrect filter, or computes a SUM inflated by a one-to-many JOIN, every consumer of the view will receive the same wrong results. **Centralizing logic brings consistency, but centralized logic still has to be correct.**

---

## 3. Comparing Tables, Regular Views, and Materialized Views

| Characteristic | Physical Table | Regular View | Materialized View |
| --- | --- | --- | --- |
| Stores result rows as a physical relation | Yes | No | Yes |
| Defined by a SELECT over other tables | Not required | Yes | Yes |
| New base table data automatically visible on next SELECT | Not applicable | Yes, per snapshot/transaction | No; requires refresh |
| Can create indexes directly on the object itself | Yes | Not directly | Yes |
| Supports standard DML | Yes, subject to permissions/constraints | Some views are automatically updatable; others require triggers/rules | Not like a standard DML table |
| Cost per SELECT | On table/indexes | Depends on expanded underlying query | On materialized results/indexes |
| Primary use case | Storing data | Abstraction and query interface | Report snapshots / expensive computations needing refresh |

**A regular view does not materialize results just because `CREATE VIEW` was used.**

### 3.1. A View with a JOIN Can Still Query Fast

PostgreSQL's optimizer can push down many predicates and choose indexes on the underlying tables. Therefore, a view with a JOIN does not necessarily scan entire tables first and filter afterward.

### 3.2. A View with GROUP BY Still Aggregates When Needed

If you query an aggregated view over millions of orders, PostgreSQL typically has to compute the aggregation from the underlying data according to the query plan. A view does not automatically cache COUNT/SUM results.

### 3.3. Materialized Views Have a Different Freshness Contract

A materialized view holds physical data from the time it was populated/refreshed. Choosing it to speed up reports also means designing **refresh schedules, access permissions, staleness tolerances, and index maintenance**.

---

## 4. Lab Dataset: Multi-Tenant Customers and Orders

To treat a view as a data contract, we need base tables containing both public and internal fields.

> **Warning:** The following `DROP SCHEMA ... CASCADE` statements delete **all** objects in the lab schema of that name. Only run them in a dedicated lab database that is safe to reset. Never run them on a database with data you need to keep.

### 4.1. Create the Practice Schema

```sql
DROP SCHEMA IF EXISTS view_contract_lab CASCADE;

CREATE SCHEMA view_contract_lab;
```

We use a single schema for brevity. In production, you can separate `internal` and `api`/`reporting` into distinct schemas to manage permissions and lifecycles.

### 4.2. Customers Table

```sql
CREATE TABLE view_contract_lab.customers (
    tenant_id INTEGER NOT NULL,
    customer_id BIGINT NOT NULL,
    display_name TEXT NOT NULL,
    email TEXT NOT NULL,
    region TEXT NOT NULL,
    PRIMARY KEY (tenant_id, customer_id)
);
```

### 4.3. Orders Table

```sql
CREATE TABLE view_contract_lab.orders (
    tenant_id INTEGER NOT NULL,
    order_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('PENDING', 'PAID', 'CANCELED', 'REFUNDED')),
    amount NUMERIC(14,2) NOT NULL CHECK (amount >= 0),
    ordered_at TIMESTAMPTZ NOT NULL,
    internal_note TEXT,
    PRIMARY KEY (tenant_id, order_id),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES view_contract_lab.customers(tenant_id, customer_id)
);
```

Key points:

- `tenant_id` is part of both the primary key and the foreign key.
- `orders.internal_note` is intended solely for internal operations.
- `customers.email` may be personal data whose readership needs to be restricted.
- `amount` is the example order value; do not assume it equates to captured cash or net revenue after refunds.

### 4.4. Insert Customers

```sql
INSERT INTO view_contract_lab.customers (
    tenant_id, customer_id, display_name, email, region
)
VALUES
    (10, 101, 'An',    'an@example.test',    'NORTH'),
    (10, 102, 'Binh',  'binh@example.test',  'SOUTH'),
    (20, 101, 'Chi',   'chi@example.test',   'CENTRAL'),
    (20, 103, 'Dung',  'dung@example.test',  'NORTH');
```

Two tenants can share the same `customer_id=101`. Therefore, joining solely on customer_id is **incorrect** without also matching tenant_id.

### 4.5. Insert Orders

```sql
INSERT INTO view_contract_lab.orders (
    tenant_id, order_id, customer_id, status,
    amount, ordered_at, internal_note
)
VALUES
    (10, 1001, 101, 'PAID',     120.00,
     TIMESTAMPTZ '2026-01-10 09:00:00+00', 'Call before shipping'),
    (10, 1002, 101, 'PENDING',   80.00,
     TIMESTAMPTZ '2026-01-11 10:00:00+00', 'Manual review'),
    (10, 1003, 102, 'PAID',      50.00,
     TIMESTAMPTZ '2026-01-12 11:00:00+00', NULL),
    (10, 1004, 102, 'CANCELED',  30.00,
     TIMESTAMPTZ '2026-01-13 12:00:00+00', 'Customer canceled'),
    (20, 1001, 101, 'PAID',     300.00,
     TIMESTAMPTZ '2026-01-11 09:00:00+00', 'Special pricing'),
    (20, 1002, 103, 'PAID',      75.00,
     TIMESTAMPTZ '2026-01-14 09:00:00+00', NULL),
    (20, 1003, 103, 'REFUNDED',  40.00,
     TIMESTAMPTZ '2026-01-15 09:00:00+00', 'Refund requested');

ANALYZE view_contract_lab.customers;
ANALYZE view_contract_lab.orders;
```

Verify:

```sql
SELECT tenant_id, order_id, customer_id, status, amount
FROM view_contract_lab.orders
ORDER BY tenant_id, order_id;
```

There are **seven orders**: four belonging to tenant 10 and three belonging to tenant 20.

---

## 5. The First View: Order Read Interface

Goal: give applications a clean read model with customer name, region, and order value without having to write JOINs themselves.

```sql
CREATE VIEW view_contract_lab.v_order_read_model AS
SELECT
    o.tenant_id,
    o.order_id,
    o.customer_id,
    c.display_name AS customer_name,
    c.region AS customer_region,
    o.status,
    o.amount AS gross_amount,
    o.ordered_at,
    (o.status = 'PAID') AS is_paid
FROM view_contract_lab.orders AS o
JOIN view_contract_lab.customers AS c
  ON c.tenant_id = o.tenant_id
 AND c.customer_id = o.customer_id;
```

### 5.1. Querying Through the View

```sql
SELECT
    order_id,
    customer_name,
    status,
    gross_amount
FROM view_contract_lab.v_order_read_model
WHERE tenant_id = 10
ORDER BY ordered_at DESC, order_id DESC;
```

No need to repeat the customer JOIN. The view decides the exposed columns and how keys are matched.

### 5.2. Inspecting the Results

For tenant 10:

| order_id | customer_name | status | gross_amount |
| ---: | --- | --- | ---: |
| 1004 | Binh | CANCELED | 30.00 |
| 1003 | Binh | PAID | 50.00 |
| 1002 | An | PENDING | 80.00 |
| 1001 | An | PAID | 120.00 |

The `internal_note` and `email` columns **are absent from the view interface**. This is one step toward reducing data exposure through the SELECT contract; however, to ensure readers cannot access underlying data, proper permissions must still be configured.

### 5.3. The Role of Aliases

```sql
o.amount AS gross_amount
c.display_name AS customer_name
```

Aliases are part of the **interface contract**. The name `gross_amount` can remain stable even if the underlying column name changes later or the data is sourced from a different structure.

### 5.4. Column Names Are a Contract with Clients

When an application maps:

```text
order_id        -> orderId
customer_name   -> customerName
gross_amount    -> grossAmount
```

renaming an alias in the view can break mappers/JDBC/ORMs/BI tools. Therefore, manage view changes just like API changes.

---

## 6. Abstraction Is More Than Shorter SQL

A well-designed view can centralize multiple conventions:

- Joining on the right keys and cardinality.
- Standardizing field names.
- Interpreting business statuses.
- Rules for excluding internal fields.
- Unit conversions or representations of derived fields.
- Separating the read model from the transactional model.
- Ensuring tenant/permission conditions are upheld architecturally.

### 6.1. Expose Only What Is Necessary

A view reduces the risk of users accidentally running `SELECT *` and leaking sensitive fields to a client:

```sql
SELECT *
FROM view_contract_lab.v_order_read_model
WHERE tenant_id = 10;
```

The result does not contain `customers.email` or `orders.internal_note`, because the view definition does not expose them.

**Limitation:** if a role still holds direct SELECT permissions on the base tables, that role can still query those fields. Creating a view alone does not revoke base table permissions.

### 6.2. Centralizing Multi-Tenant JOINs

Incorrect:

```sql
JOIN view_contract_lab.customers AS c
  ON c.customer_id = o.customer_id
```

because both tenant 10 and tenant 20 have customer `101`.

Correct:

```sql
JOIN view_contract_lab.customers AS c
  ON c.tenant_id = o.tenant_id
 AND c.customer_id = o.customer_id
```

Placing the correct JOIN inside the view lets all consumers reuse it. However, **this is not a substitute for tenant authorization**: queries against the view must still filter the appropriate tenant or rely on trustworthy RLS.

### 6.3. A View Cannot Replace the Authentication Contract

Never trust an arbitrary client-supplied `tenant_id` as proof of access rights. Authorization must rely on authenticated identity/session context, server-side policies, RLS, or equivalent mechanisms. A view is only one piece of the architecture.

---

## 7. Derived Columns in Views

A view can generate business fields without storing additional columns in the base table.

Example:

```sql
CREATE VIEW view_contract_lab.v_order_flags AS
SELECT
    tenant_id,
    order_id,
    status,
    amount,
    (status = 'PAID') AS is_paid,
    (status = 'CANCELED') AS is_canceled,
    CASE
        WHEN status = 'PAID' THEN 'COMPLETED'
        WHEN status = 'PENDING' THEN 'IN_PROGRESS'
        ELSE 'CLOSED'
    END AS lifecycle_group
FROM view_contract_lab.orders;
```

Usage:

```sql
SELECT
    order_id,
    is_paid,
    lifecycle_group
FROM view_contract_lab.v_order_flags
WHERE tenant_id = 10
ORDER BY order_id;
```

### 7.1. A Derived Field Is Not Stored by Default

`is_paid` and `lifecycle_group` are computed by the view's SELECT expressions. When an order's status changes, querying the view after the change commits returns the updated value per the snapshot.

### 7.2. Be Careful with Volatile Expressions

A view can call functions that depend on time, session configuration, or application-defined functions. In such cases, results may vary across SELECT calls even when the source tables have not changed.

Example:

```sql
CREATE VIEW view_contract_lab.v_order_age AS
SELECT
    tenant_id,
    order_id,
    ordered_at,
    CURRENT_TIMESTAMP - ordered_at AS order_age
FROM view_contract_lab.orders;
```

The `order_age` field changes over time. Do not treat it as a physical column captured statically at view creation time.

### 7.3. Do Not Lose Unit Semantics

If a view converts `amount` to another unit, name it clearly—for example `amount_in_minor_units` or `amount_vnd`—and document the rounding policy. A view contract is not just the `NUMERIC` type, but also **units and semantics**.

---

## 8. Aggregated Views for Reporting

A view can encapsulate `GROUP BY` so reports use a single consistent definition.

Example: count of PAID orders and total value of currently PAID orders per UTC day and tenant.

```sql
CREATE VIEW view_contract_lab.v_daily_paid_orders AS
SELECT
    tenant_id,
    (ordered_at AT TIME ZONE 'UTC')::DATE AS order_day_utc,
    COUNT(*) AS paid_order_count,
    SUM(amount) AS paid_order_value
FROM view_contract_lab.orders
WHERE status = 'PAID'
GROUP BY
    tenant_id,
    (ordered_at AT TIME ZONE 'UTC')::DATE;
```

Usage:

```sql
SELECT *
FROM view_contract_lab.v_daily_paid_orders
WHERE tenant_id = 10
ORDER BY order_day_utc;
```

### 8.1. Why Do Reporting Views Need Clear Metric Definitions?

`paid_order_value` here means **the sum of amount for orders whose status is PAID**, grouped by **order placement date in UTC**. It is not:

- Daily payment cash flow.
- Net revenue after refunds.
- Order value grouped by the date status transitioned to PAID.
- Revenue in a local timezone.

If a view is named `v_revenue` without documenting its semantics, multiple teams may misuse it.

### 8.2. Aggregated Views Are Typically Not Automatically Updatable

Views with `GROUP BY` and aggregates are not simple enough for PostgreSQL to automatically map an UPDATE on the output back to a single base table row.

Therefore, this view should be treated as a **reporting read interface**, not a DML-writable table like orders.

### 8.3. Aggregated Views Do Not Speed Things Up Automatically

Every query against `v_daily_paid_orders` typically still executes the aggregation logic over the underlying data according to an appropriate plan. If aggregation costs become too high and dashboards call it frequently, consider a materialized view or summary table, accompanied by a data freshness contract.

---

## 9. Views as a Stable Contract Across Schema Changes

This is a primary reason to use views.

Suppose an application originally stored customer names in `customers.display_name`. After a migration, the backend stores the data in a different structure, such as two columns `given_name` and `family_name`.

Without a view, every client would have to change:

```text
customers.display_name
    |
    v
concat_ws(' ', given_name, family_name)
```

With a view, the backend can continue exposing:

```sql
... AS customer_name
```

to consumers while migrating the internal data structure.

### 9.1. Views as a Data Anti-Corruption Layer

A read model helps separate:

```text
Physical schema:
    table names, columns, normalized structure, FK

View contract:
    field names, data types, granularity, filters, semantics

Consumer:
    JDBC mapper, reports, dashboard, export, API
```

When the physical schema changes, keeping the view returning data with the same meaning and compatible types prevents consumers from breaking on every migration step.

### 9.2. However, Views Do Not Survive Every Change Automatically

If a base column that a view still depends on is dropped, PostgreSQL will block the DDL or require CASCADE, which deletes dependent objects. You cannot expect a view to automatically reconstruct JOINs or convert `TEXT` to `INTEGER`.

Schema change steps still require dependency management and careful migrations.

### 9.3. Structural Stability Differs from Semantic Stability

A view that still returns an `amount NUMERIC` column while changing its meaning from "pre-tax order value" to "value net of refunds" is a **semantic breaking change**, even if the application reports no data type errors.

View contracts should have documentation describing units, timezones, statuses, NULL handling, calculation rules, and access permissions.

---

## 10. CREATE OR REPLACE VIEW: Updating Definitions

PostgreSQL supports modifying a view's query via:

```sql
CREATE OR REPLACE VIEW view_contract_lab.v_order_flags AS
SELECT
    tenant_id,
    order_id,
    status,
    amount,
    (status = 'PAID') AS is_paid,
    (status = 'CANCELED') AS is_canceled,
    CASE
        WHEN status = 'PAID' THEN 'COMPLETED'
        WHEN status = 'PENDING' THEN 'IN_PROGRESS'
        ELSE 'CLOSED'
    END AS lifecycle_group
FROM view_contract_lab.orders;
```

This command redefines the SELECT body without needing to drop the view.

### 10.1. Restrictions on Existing Columns

For an existing view, `CREATE OR REPLACE VIEW` requires that existing columns retain the **same names, same order, and same data types**; new columns may be appended at the end as supported by PostgreSQL.

Do not expect it to arbitrarily:

- Remove an old column.
- Rename an old column directly in the replacement definition.
- Change the return type of an old column.
- Reorder existing columns.

Such changes will be rejected or require a different migration strategy.

### 10.2. Appending Columns at the End

Example adding `currency_code` to the flags view:

```sql
CREATE OR REPLACE VIEW view_contract_lab.v_order_flags AS
SELECT
    tenant_id,
    order_id,
    status,
    amount,
    (status = 'PAID') AS is_paid,
    (status = 'CANCELED') AS is_canceled,
    CASE
        WHEN status = 'PAID' THEN 'COMPLETED'
        WHEN status = 'PENDING' THEN 'IN_PROGRESS'
        ELSE 'CLOSED'
    END AS lifecycle_group,
    'VND'::TEXT AS currency_code
FROM view_contract_lab.orders;
```

Here the existing columns remain unchanged, and the new column is appended at the end. The currency code only illustrates structure; a real system must read currency from actual data rather than hardcoding VND for all transactions if multiple currencies exist.

### 10.3. When You Need to Rename a Column

PostgreSQL provides:

```sql
ALTER VIEW view_contract_lab.v_order_flags
RENAME COLUMN currency_code TO settlement_currency_code;
```

However, renaming a column can break consumers relying on the old name. Permitted DDL syntax does not mean the change is safe at the API contract level.

### 10.4. When You Need to Change a Type or Remove a Column

Usually you must create a new view version or orchestrate a controlled migration; never drop/cascade a view used by dozens of consumers without knowing its dependencies.

---

## 11. Versioning Views Like Versioning APIs

A system can publish:

```text
api.v_orders_v1
api.v_orders_v2
```

Example:

```sql
CREATE VIEW view_contract_lab.v_orders_v1 AS
SELECT
    tenant_id,
    order_id,
    status,
    amount
FROM view_contract_lab.orders;

CREATE VIEW view_contract_lab.v_orders_v2 AS
SELECT
    tenant_id,
    order_id,
    status,
    amount AS gross_amount,
    ordered_at,
    (status = 'PAID') AS is_paid
FROM view_contract_lab.orders;
```

### 11.1. Why Create v2?

V2 can rename fields and introduce new semantics without forcing all consumers to switch simultaneously.

Process:

1. Create v2 and verify the output contract.
2. Grant permissions to consumers that need it.
3. Migrate clients one by one to v2.
4. Monitor usage and errors.
5. Remove v1 only after all remaining consumers have been handled.

### 11.2. Version Names Do Not Replace Testing

A view suffixed with `_v2` can still have a wrong JOIN or expose sensitive columns. Versioning manages change; it does not certify quality.

### 11.3. Avoid Depending on SELECT *

Clients might write:

```sql
SELECT *
FROM view_contract_lab.v_orders_v1;
```

If the view later appends columns, positional mappers or fixed-format exports might unexpectedly receive extra fields. For long-lived interfaces, specify the exact columns clients need and test every column's name and type.

---

## 12. View Dependencies on Underlying Objects

Views typically depend on tables, columns, functions, operators, and any objects required by their query definition.

### 12.1. When Changing Table Structure

Suppose a view uses `orders.status`. Attempting to drop this column from the base table will be rejected by PostgreSQL because dependent views exist.

```sql
-- Do not run on the lab if you want to keep the existing views.
ALTER TABLE view_contract_lab.orders
DROP COLUMN status;
```

Normally PostgreSQL reports dependent objects unless the DDL specifies a mechanism like CASCADE. However, `CASCADE` can drop dependent views and other objects—do not use it casually in production.

### 12.2. Renaming a Base Column vs. Renaming a View Interface Column

PostgreSQL tracks view references to objects via metadata/dependencies. An `ALTER TABLE ... RENAME COLUMN` on the base table can be handled by the system without necessarily changing the alias exposed by the view.

Still, never rely on intuition to claim a migration is compatible: check `pg_get_viewdef`, the view's output names, and consumer queries.

### 12.3. Inspecting View Definitions with pg_get_viewdef

```sql
SELECT pg_get_viewdef(
    'view_contract_lab.v_order_read_model'::REGCLASS,
    TRUE
) AS view_definition;
```

This retrieves the SELECT definition stored by PostgreSQL, usually deparsed/normalized; it will not necessarily match the exact DDL string you originally typed character for character.

### 12.4. Listing Views in a Schema

```sql
SELECT
    schemaname,
    viewname,
    viewowner,
    definition
FROM pg_views
WHERE schemaname = 'view_contract_lab'
ORDER BY viewname;
```

### 12.5. Metadata for Exposed Columns

```sql
SELECT
    table_name,
    ordinal_position,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'view_contract_lab'
  AND table_name = 'v_order_read_model'
ORDER BY ordinal_position;
```

This metadata can support contract tests. `information_schema` visibility depends on the role's privileges.

### 12.6. Viewing in psql

If using the `psql` client:

```text
\dv
\dv+ view_contract_lab.*
\d+ view_contract_lab.v_order_read_model
```

These are **psql meta-commands**, not SQL statements that work in every JDBC client.

---

## 13. Regular Views Do Not Store Results: Performance Perspective

Suppose an application runs:

```sql
SELECT order_id, customer_name
FROM view_contract_lab.v_order_read_model
WHERE tenant_id = 10
  AND ordered_at >= TIMESTAMPTZ '2026-01-10 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-02-01 00:00:00+00';
```

PostgreSQL can optimize based on underlying expressions, JOINs, indexes, statistics, and selectivity.

### 13.1. Views Do Not Force Two Separate SELECT Passes

Do not imagine PostgreSQL always:

1. Runs the view's SELECT and stores the entire result.
2. Filters the outer WHERE afterward.

With regular views, query rewrite/planning gives the optimizer the opportunity to optimize conditions across the view boundary.

### 13.2. Indexes on Base Tables Can Be Used

Example:

```sql
CREATE INDEX idx_orders_tenant_date
ON view_contract_lab.orders (tenant_id, ordered_at);

CREATE INDEX idx_orders_customer
ON view_contract_lab.orders (tenant_id, customer_id);

ANALYZE view_contract_lab.orders;
```

These indexes live on the **base tables**, not on the regular view itself.

Queries against the view filtering by tenant/time can be planned to use appropriate indexes on `orders`, depending on scale and data distribution. On a seven-row lab table, `Seq Scan` may be cheaper.

### 13.3. VIEWs Do Not Support CREATE INDEX Directly

You cannot create a B-tree or GIN index directly on a regular view's output the way you index a physical table. If a view query is slow, examine:

- Indexes on base tables.
- How JOINs and WHERE clauses are written.
- GROUP BY/DISTINCT/LIMIT inside the view.
- Row estimates and statistics.
- Whether a materialized view or summary table is actually needed.

### 13.4. Views Do Not Cure JOIN Fan-Out

If you JOIN an orders table with two child tables that each have multiple rows, SUM of `orders.amount` can be multiplied. Putting that JOIN into a view merely makes the bug more widely reusable.

When metrics are needed at the order grain, pre-aggregate child tables before joining or design at the proper grain.

---

## 14. Using EXPLAIN Through a View

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    order_id,
    customer_name,
    gross_amount
FROM view_contract_lab.v_order_read_model
WHERE tenant_id = 10
  AND status = 'PAID';
```

In the plan, you can see scans of underlying tables like `orders` and `customers`, JOIN nodes, or index scans. You will not necessarily see a separate node named "Scan on View" like a physical heap relation.

### 14.1. Reading Key Plan Information

| EXPLAIN Field | Meaning |
| --- | --- |
| `Seq Scan` | Sequential scan of base table |
| `Index Scan` | Locates rows via index and accesses heap |
| `Index Only Scan` | Can reduce heap visits when visibility conditions allow |
| `Hash Join` | JOIN using a hash table |
| `Nested Loop` | JOIN iterating over outer input |
| `Merge Join` | JOIN leveraging/sorting order by keys |
| `HashAggregate`/`GroupAggregate` | Aggregation when view/query uses GROUP BY |
| `Filter`/`Index Cond` | Where predicates are applied |
| `actual rows` | Actual row count per node |
| `Buffers` | Buffer hits/reads/temp blocks involved |
| `Planning Time` | Time spent planning |
| `Execution Time` | Time spent executing |

### 14.2. Do Not Judge Speed by Object Type Alone

A view can be fast with a selective WHERE clause yet slow when a consumer runs:

```sql
SELECT *
FROM view_contract_lab.v_order_read_model;
```

across billions of historical rows. The issue is the query's scope and shape, not merely the use of a view.

### 14.3. Predicate Pushdown Has Limits

Constructs such as:

- GROUP BY.
- DISTINCT.
- LIMIT/OFFSET.
- Certain window functions.
- Certain subqueries/set operations.
- Security barriers and security conditions.
- Volatile expressions or ones unsafe to relocate.

can limit the planner's ability to push filters down. Do not assume a view is always "inlined" like a flat SELECT.

### 14.4. On Small Data, Seq Scan Is Normal

Seven orders and four customers are too small to show index benefits. PostgreSQL will choose Seq Scan due to lower cost. Never force index usage in production just to make a plan look "pretty."

---

## 15. Outer WHERE Clauses on Views: Can They Push Down?

Suppose:

```sql
SELECT *
FROM view_contract_lab.v_order_read_model
WHERE tenant_id = 10
  AND status = 'PAID';
```

For simple JOIN views, PostgreSQL can typically combine `tenant_id` and `status` predicates with base table operations during optimization.

### 15.1. Views Let Callers Supply Their Own Filters

Instead of creating one view per tenant, you can have a shared read model view, while services scope the tenant when querying based on a trusted identity.

However, **application-written tenant filters do not replace server-side security mechanisms**. If any consumer with view access forgets the tenant WHERE clause, they can see multiple tenants unless views/permissions restrict it.

### 15.2. A View with Built-In Filters Is a Different Contract

```sql
CREATE VIEW view_contract_lab.v_paid_orders AS
SELECT
    tenant_id, order_id, customer_id,
    status, amount, ordered_at
FROM view_contract_lab.orders
WHERE status = 'PAID';
```

This view always enforces status PAID in its definition. Yet that condition **does not restrict tenants**; permissions/tenant isolation still need separate handling.

### 15.3. Multiple View Layers Can Obscure Tracing

```text
v_dashboard
   -> v_order_export
       -> v_paid_orders
           -> orders
```

A chain of views can organize contracts, but if each layer alters semantics and adds CTEs/JOINs/aggregations, reading query plans and debugging becomes harder.

Only stack views when each layer has a clear purpose and is thoroughly tested.

---

## 16. Does a View with ORDER BY Guarantee Output Order?

A common question:

```sql
CREATE VIEW view_contract_lab.v_latest_orders AS
SELECT
    tenant_id, order_id, status, ordered_at
FROM view_contract_lab.orders
ORDER BY ordered_at DESC;
```

In API design, **never rely on an ORDER BY inside a view to guarantee output ordering for every outer SELECT**.

Callers should specify explicitly:

```sql
SELECT *
FROM view_contract_lab.v_latest_orders
WHERE tenant_id = 10
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

### 16.1. Why Add order_id?

If multiple orders share the same ordered_at, `ORDER BY ordered_at DESC` does not establish a total order. Adding a stable unique key makes results consistent, especially for pagination.

### 16.2. ORDER BY Inside a View Can Be Costly

If a view forces an unnecessary sort step for most consumers, it adds extra work or constrains the optimizer in some cases. Avoid putting ORDER BY into every view by default just for "readability."

### 16.3. LIMIT Inside a View Changes Data Semantics

```sql
CREATE VIEW view_contract_lab.v_recent_ten AS
SELECT *
FROM view_contract_lab.orders
ORDER BY ordered_at DESC, tenant_id, order_id
LIMIT 10;
```

This view exposes **only ten rows system-wide** by the stated criteria; a user filtering by tenant afterward will not necessarily receive the ten most recent orders for that tenant. If you need "10 most recent orders per tenant," design the query with the tenant filter before LIMIT or use an appropriate pattern.

This is a semantic change, not just a performance optimization.

---

## 17. What Is an Automatically Updatable View?

PostgreSQL can automatically map DML on **certain simple views** down to the base table.

Example:

```sql
CREATE VIEW view_contract_lab.v_order_edit AS
SELECT
    tenant_id,
    order_id,
    customer_id,
    status,
    amount,
    ordered_at
FROM view_contract_lab.orders;
```

This view selects columns directly from **a single base table** with no JOIN/GROUP BY/DISTINCT. It qualifies as **automatically updatable** under PostgreSQL's supported conditions.

### 17.1. UPDATE Through a Simple View

Test only inside a lab transaction:

```sql
BEGIN;

UPDATE view_contract_lab.v_order_edit
SET amount = 130.00
WHERE tenant_id = 10 AND order_id = 1001
RETURNING tenant_id, order_id, amount;

ROLLBACK;
```

The operation updates the corresponding row in the `orders` table. `ROLLBACK` ensures original data remains unchanged after the example.

### 17.2. INSERT Through a Simple View

```sql
BEGIN;

INSERT INTO view_contract_lab.v_order_edit (
    tenant_id, order_id, customer_id,
    status, amount, ordered_at
)
VALUES (
    10, 1099, 101,
    'PENDING', 99.00,
    TIMESTAMPTZ '2026-01-16 10:00:00+00'
)
RETURNING tenant_id, order_id, status;

ROLLBACK;
```

Data must still satisfy PRIMARY KEY, FOREIGN KEY, CHECK, NOT NULL, and other constraints on the base table.

### 17.3. Not Every View Column Is Writable

A view with an expression:

```sql
SELECT amount * 2 AS double_amount
```

has no unique inverse mapping from `double_amount` back to the `amount` column in all cases.

Views with JOIN, GROUP BY, DISTINCT, UNION, aggregates, or other constructs generally do not qualify as fully **automatically updatable**. You can inspect per-column updatability via catalogs/information schema and your version's documentation.

### 17.4. Updatability Is Not a Reason to Write Through Views by Default

A read model is often intentionally granted **SELECT only**, even if PostgreSQL could automatically UPDATE it. DML capability is an SQL property, whereas write access is an architectural decision.

---

## 18. WITH CHECK OPTION: Preserving Predicates When Writing Through Views

Suppose there is a view showing only PAID orders for tenant 10:

```sql
CREATE VIEW view_contract_lab.v_tenant10_paid_edit AS
SELECT
    tenant_id, order_id, customer_id,
    status, amount, ordered_at
FROM view_contract_lab.orders
WHERE tenant_id = 10
  AND status = 'PAID'
WITH CASCADED CHECK OPTION;
```

This view is simple, backed by a single table, and automatically updatable under the right conditions.

**CHECK OPTION** ensures that INSERT/UPDATE operations through the view cannot produce a row outside the view's accepted conditions, according to LOCAL/CASCADED scope.

### 18.1. Valid UPDATE Example

```sql
BEGIN;

UPDATE view_contract_lab.v_tenant10_paid_edit
SET amount = 125.00
WHERE tenant_id = 10 AND order_id = 1001
RETURNING order_id, status, amount;

ROLLBACK;
```

The order remains in tenant 10 with status PAID.

### 18.2. Example of a Change That Makes a Row Disappear from the View

If you run:

```sql
-- Test separately in the lab environment; this statement is expected to be rejected
-- because it produces a row that does not satisfy the view predicate.
UPDATE view_contract_lab.v_tenant10_paid_edit
SET status = 'PENDING'
WHERE tenant_id = 10 AND order_id = 1001;
```

with CHECK OPTION, PostgreSQL rejects writes through the view that create rows failing the corresponding condition.

### 18.3. What Without CHECK OPTION?

An updatable view with `WHERE status='PAID'` but without CHECK OPTION may allow an UPDATE that moves the row outside the view's SELECT scope, depending on structure and permissions. After updating, the row "disappears" from the view's results.

This is not always a bug: some workflows intentionally transition state through a filtered view. Choose deliberately.

### 18.4. CHECK OPTION Is Not a System-Wide Constraint

CHECK OPTION applies to **DML through the qualifying view**, does not replace base table CHECK constraints, and does not govern UPDATEs executed directly on the base table.

If a rule like "amount must never be negative" must always hold, enforce it with a base table constraint, not just a view.

---

## 19. LOCAL and CASCADED CHECK OPTION

When multiple layers of updatable views exist:

```sql
CREATE VIEW view_contract_lab.v_tenant10_orders AS
SELECT
    tenant_id, order_id, customer_id,
    status, amount, ordered_at
FROM view_contract_lab.orders
WHERE tenant_id = 10;

CREATE VIEW view_contract_lab.v_tenant10_paid_local AS
SELECT *
FROM view_contract_lab.v_tenant10_orders
WHERE status = 'PAID'
WITH LOCAL CHECK OPTION;
```

### 19.1. LOCAL

`LOCAL CHECK OPTION` checks the conditions of the **current view** in supported cases, without requiring checks on underlying views unless those underlying views define their own CHECK OPTION.

In this example, the local view has `status='PAID'`. The `tenant_id=10` condition belongs to the underlying view and is not enforced by LOCAL if the underlying view has no CHECK OPTION of its own.

### 19.2. CASCADED

`CASCADED CHECK OPTION` extends checking across the conditions of underlying automatically updatable views according to PostgreSQL's rules.

```sql
CREATE VIEW view_contract_lab.v_tenant10_paid_cascaded AS
SELECT *
FROM view_contract_lab.v_tenant10_orders
WHERE status = 'PAID'
WITH CASCADED CHECK OPTION;
```

Here both the status predicate and the tenant predicate from the chain of automatically updatable views are checked.

### 19.3. Limitations with Triggers/Rules

For views using `INSTEAD OF` triggers or complex rewrite rules, CHECK OPTION has specific limitations and interactions; do not assume every condition across every layer is enforced identically to simple views.

### 19.4. CASCADED Does Not Replace Authorization

Anyone with direct permissions on the `orders` table can still bypass the view via the base table. CHECK OPTION only restricts behavior **through that view**. If the goal is tenant isolation, protect it with permissions and properly authenticated RLS/tenant guards.

---

## 20. INSTEAD OF Triggers for Complex Views

A JOIN view has no unambiguous write mapping. For example:

```sql
SELECT
    o.order_id,
    c.display_name,
    o.amount
FROM orders o
JOIN customers c ON ...;
```

If a user runs:

```sql
UPDATE view_name
SET display_name = 'New name',
    amount = 200
WHERE order_id = 1001;
```

PostgreSQL would need to know whether to update customers, orders, or both, and how to handle a customer with multiple orders. No single strategy can be inferred for all JOIN views.

### 20.1. INSTEAD OF Trigger

PostgreSQL lets you define `INSTEAD OF INSERT/UPDATE/DELETE` triggers on views in supported cases. The trigger function translates view-level operations into base table DML according to rules you design.

Model:

```text
UPDATE on view
      |
      v
INSTEAD OF trigger
      |
      +--> check permissions/business rules
      +--> UPDATE orders
      +--> UPDATE customers (if appropriate)
      +--> RETURN NEW / NULL per trigger contract
      |
      v
Database transaction
```

### 20.2. Do Not Turn Every Read Model View into Writable

Triggers must handle:

- Tenant keys/authorization.
- Concurrency and stale updates.
- Transaction atomicity.
- FK/unique/check constraints.
- Affected row counts.
- INSERTs with missing fields.
- Multi-table update handling.
- Errors and rollbacks.
- RETURNING/trigger return values.

The complexity can exceed exposing a dedicated, explicitly controlled mutation API.

### 20.3. Rules and INSTEAD OF Triggers Differ

PostgreSQL also has rewrite rules, but for complex business DML, triggers generally make per-row behavior easier to reason about. Avoid using rules as arbitrary "view update handlers" unless you thoroughly understand query rewriting and side effects.

---

## 21. SELECT Permissions on Views vs. Base Table Permissions

One advantage of views is granting read access to a restricted interface **without granting direct permissions on all underlying tables/columns** under default view mechanics.

Model:

```text
Role: report_reader
      |
      | SELECT on api.v_order_read_model
      v
View (owner has read permission on base tables)
      |
      +--> internal.orders
      +--> internal.customers

report_reader does not necessarily have direct SELECT
on internal.orders or internal.customers
```

### 21.1. Testing Roles in an Authorized Environment

The following statements illustrate permission management; they require appropriate CREATE ROLE/GRANT privileges and should not be run casually in production.

```sql
CREATE ROLE view_lab_reader NOLOGIN;

GRANT USAGE ON SCHEMA view_contract_lab
TO view_lab_reader;

GRANT SELECT ON view_contract_lab.v_order_read_model
TO view_lab_reader;
```

A role can then be granted access to the view without necessarily holding SELECT on the base tables. However, actual behavior depends on the view owner, underlying objects, RLS, and view options.

### 21.2. Do Not Over-Grant Permissions for "Simplicity"

```sql
GRANT SELECT ON ALL TABLES IN SCHEMA view_contract_lab
TO view_lab_reader;
```

is completely different from granting on **one view**. The statement above opens read access to all base tables and other views in the schema, defeating data surface restriction.

### 21.3. Column-Level Permissions on Views

PostgreSQL supports column-level GRANTs, for example:

```sql
GRANT SELECT (
    tenant_id, order_id, status, gross_amount
)
ON view_contract_lab.v_order_read_model
TO view_lab_reader;
```

If the role **already holds SELECT on the entire view**, an additional column-restricted GRANT **does not narrow** prior access. To allow only specific columns, redesign grants/revokes properly and verify effective privileges.

In practice, it is often clearer to create a separate view containing only the permitted columns and grant access solely to that view.

---

## 22. Whose Permissions Does a View Use by Default?

In PostgreSQL, regular views check permissions on underlying objects as the **view owner** by default. This allows a role with view read access to query it without direct read privileges on base tables.

However:

- Callers still need access privileges on the view and USAGE on the relevant schema.
- The owner must hold appropriate privileges on the objects referenced by the view.
- Functions called inside the view have their own execution permission checks and depend on their security definer/invoker attributes.
- Row-Level Security can apply differently depending on owner, security_invoker, FORCE RLS, BYPASSRLS, and configuration.
- Changes to the owner's or view's permissions can affect consumers.

### 22.1. A View Is Not a SECURITY DEFINER Function by Default

Do not equate a view with a `SECURITY DEFINER` SQL function. They are distinct PostgreSQL mechanisms, even though both interact with privileges and underlying objects.

### 22.2. Ownership Is Part of the Architecture

If a view is owned by a superuser or an overly privileged role, certain base table protections may be bypassed under owner/BYPASSRLS rules. For views exposing sensitive data, use a dedicated owner role and enforce least privilege.

### 22.3. Granting SELECT on a View Does Not Mean Ignoring RLS

A view filtering tenants with WHERE and a base table with RLS are two different layers. Clearly design which policy determines which rows a reader sees; never assume a VIEW automatically inherits "user identity" the way API authors imagine.

---

## 23. security_invoker: Checking Base Table Permissions as the Caller

Starting in PostgreSQL 15, views support the `security_invoker` option.

Example syntax:

```sql
CREATE VIEW view_contract_lab.v_orders_invoker
WITH (security_invoker = true)
AS
SELECT
    tenant_id, order_id, status, amount
FROM view_contract_lab.orders;
```

Idea: when querying a security-invoker view, permissions on underlying relations and RLS policies are evaluated against the **caller** under this feature's semantics, rather than the view owner as by default.

### 23.1. Crucial Differences

| Scenario | Default View | security_invoker View |
| --- | --- | --- |
| Caller has SELECT on view but lacks base table permissions | Can read via view owner's permissions | Typically denied due to missing base table permissions |
| RLS on base tables | Depends on owner/settings applied | Typically evaluated as the caller |
| Using a view to expose selected columns without granting base table access | May be suitable | Requires care since caller still needs base privileges |
| Using a view to reuse SQL while preserving caller privileges | Not the default behavior | Typically more suitable |

Cases involving permissions, functions, and nested views still require testing against your actual version and configuration.

### 23.2. Do Not Blindly Convert Every View to Invoker

If a dashboard is granted SELECT only on a view and not on base tables, enabling `security_invoker=true` can cause permission denied errors for the dashboard.

Conversely, if the architecture requires each caller's RLS policy to run on base tables, a default view may lack the expected semantics.

**This is a security choice**, not merely an optimization option.

### 23.3. Testing Real Permissions

When testing on staging, include at least:

- A role with SELECT on the view only.
- A role with SELECT on the view and sufficient base table privileges.
- A role restricted by a tenant RLS policy.
- A view owner distinct from the caller.
- Cases where table owner / BYPASSRLS could interfere.
- Verifying how many rows each role actually reads.

Never conclude permissions work just because a superuser session ran SELECT successfully.

---

## 24. security_barrier: Mitigating One Class of Predicate Pushdown Risks

A view used to hide sensitive rows may need to care about **predicate evaluation order** and unsafe functions pushed down by the optimizer.

PostgreSQL supports:

```sql
CREATE VIEW view_contract_lab.v_tenant10_barrier
WITH (security_barrier = true)
AS
SELECT
    tenant_id, order_id, status, amount
FROM view_contract_lab.orders
WHERE tenant_id = 10;
```

`security_barrier` is designed to prevent **non-leakproof** caller-supplied expressions from being pushed past the view's filter boundary in ways that could leak information from filtered-out rows.

### 24.1. Not the Same as RLS

`security_barrier` does not determine tenant identity from a login token, does not grant or revoke base table permissions, and does not replace RLS.

### 24.2. Why Can It Impact Performance?

A security barrier can restrict predicate pushdown. Some conditions and index paths may not be applied as they would on a simple view, especially with non-leakproof expressions. Balance safety against cost, and run `EXPLAIN` with realistic roles and queries.

### 24.3. Does Not Guarantee Blocking Every Information Channel

Security barrier is a safeguard within the SQL executor/optimizer model, **not an absolute guarantee against all side channels** (such as timing, statistics, or out-of-scope behaviors). Real-world security still requires permissions, RLS, data policies, and testing.

### 24.4. security_invoker and security_barrier Serve Different Purposes

- `security_invoker`: governs **caller permission semantics on underlying tables**.
- `security_barrier`: controls **certain optimizations that could cross security filter boundaries**.

You may need one, both, or neither depending on your goals. Do not treat the two options as synonyms.

---

## 25. Views and Row-Level Security

Row-Level Security (RLS) can restrict which rows a role can read or modify at the **base table** level.

Illustrative configuration:

```sql
ALTER TABLE view_contract_lab.orders
ENABLE ROW LEVEL SECURITY;
```

RLS requires policies designed around a trustworthy identity. Conceptual example:

```sql
-- Illustrative concept only: do not implement a real policy
-- based on a tenant value arbitrarily SET by the client.
--
-- CREATE POLICY ... ON orders
-- USING (tenant_id = trusted_tenant_context);
```

### 25.1. Questions You Must Answer

- Which PostgreSQL role represents the caller?
- Where does tenant context come from, and can users tamper with it?
- Which role owns the view?
- Is the view `security_invoker` or default?
- Does the owner/table role bypass RLS?
- Do policies apply differently to SELECT, UPDATE, INSERT, and DELETE?
- Whose permissions do functions inside the view execute under?

### 25.2. Caution with current_setting in Multi-Tenant Systems

A common pattern:

```sql
WHERE tenant_id = current_setting('app.tenant_id')::INTEGER
```

is safe only when the architecture proves this session variable is set by a trusted layer, callers cannot spoof it, connection pooling never leaks context across requests, and all access paths are protected.

If an arbitrary SQL client can run `SET app.tenant_id` to another tenant, using that value as an authorization boundary is insufficient.

### 25.3. Base Table RLS Must Still Be Sound Even If Views Filter

Do not create a tenant-filtering view while granting SELECT on the entire base table; direct queries can bypass the view.

A safer pattern generally involves:

- Protecting base tables with proper permissions/RLS.
- Views exposing the right columns and semantics.
- API roles holding only the privileges genuinely needed.
- Testing from multiple roles and tenants.
- Avoiding inappropriate owners that bypass RLS policies.

---

## 26. A View Is Not Automatically a Secure API

A view can act as a **database-facing API**, but it does not replace:

- Authentication.
- Authorization.
- Input validation.
- Rate limiting.
- Audit logging.
- Application/business transactions.
- Personal data classification.
- Governance over data exposure via reports/exports.
- Privilege and credential management.

### 26.1. Avoid Misleading Names

A view named `v_public_orders` that contains `customer_email` does not become safe simply because it has the word "public" in its name.

### 26.2. Avoid Uncontrolled SELECT *

Contract views should declare an explicit column list:

```sql
SELECT
    tenant_id,
    order_id,
    customer_id,
    status,
    amount
FROM view_contract_lab.orders;
```

rather than:

```sql
SELECT * FROM view_contract_lab.orders;
```

in a long-term contract layer.

PostgreSQL stores the view definition at creation time; `SELECT *` in CREATE VIEW should not be mistaken for a promise to automatically append future base table columns. Column names can accidentally become contract dependencies when schemas evolve. Listing columns explicitly aids code review and exposure control.

### 26.3. Restrict Function Execution Privileges

Views can invoke SQL functions. If a function has side effects or unusual privilege attributes, view callers might trigger unintended behavior. Evaluate function volatility, SECURITY DEFINER/INVOKER, EXECUTE privileges, and search_path on custom functions.

---

## 27. Views Do Not Accept Parameters Like Functions

There is no regular view syntax such as:

```sql
SELECT *
FROM v_orders(tenant_id => 10);
```

if `v_orders` was created with `CREATE VIEW`, not as a function.

Consumers typically pass predicates via:

```sql
SELECT *
FROM view_contract_lab.v_order_read_model
WHERE tenant_id = $1
  AND ordered_at >= $2
  AND ordered_at < $3;
```

### 27.1. When Do You Need an SQL Function?

If you want a **parameterized interface** with its own contract, you can use a function:

```sql
CREATE FUNCTION view_contract_lab.get_orders_in_range(
    p_tenant_id INTEGER,
    p_start TIMESTAMPTZ,
    p_end TIMESTAMPTZ
)
RETURNS TABLE (
    tenant_id INTEGER,
    order_id BIGINT,
    status TEXT,
    gross_amount NUMERIC,
    ordered_at TIMESTAMPTZ
)
LANGUAGE SQL
STABLE
AS $$
    SELECT
        v.tenant_id,
        v.order_id,
        v.status,
        v.gross_amount,
        v.ordered_at
    FROM view_contract_lab.v_order_read_model AS v
    WHERE v.tenant_id = p_tenant_id
      AND v.ordered_at >= p_start
      AND v.ordered_at < p_end;
$$;
```

Call it:

```sql
SELECT *
FROM view_contract_lab.get_orders_in_range(
    10,
    TIMESTAMPTZ '2026-01-01 00:00:00+00',
    TIMESTAMPTZ '2026-02-01 00:00:00+00'
);
```

### 27.2. Functions Carry Additional Responsibilities

A function can have:

- Parameters and default arguments.
- EXECUTE permissions.
- Volatility and parallel safety metadata.
- SECURITY INVOKER/DEFINER.
- Search path and dependencies.
- Inlining capability under specific conditions.

Thus a function can suit parameterized APIs, but does not replace views in all cases.

### 27.3. Do Not Use a Tenant Parameter Function Without Authorization

`p_tenant_id=10` is just a parameter. If a caller can pass 20, the function still needs appropriate privileges and policies. Adding a parameter does not automatically turn a query into an authorized operation.

---

## 28. Views and CTEs: Two Different Levels of Reuse

CTE (*Common Table Expression*):

```sql
WITH paid_orders AS (
    SELECT *
    FROM view_contract_lab.orders
    WHERE status = 'PAID'
)
SELECT tenant_id, COUNT(*)
FROM paid_orders
GROUP BY tenant_id;
```

A CTE exists only within the scope of **a single statement**. It does not create a named schema object with independent permissions and lifecycle like a view.

### 28.1. When to Use a CTE

- Splitting a complex query into readable steps.
- Computing an intermediate set.
- Structuring a one-off report query.
- Writing recursive queries when needed.

### 28.2. When to Use a View

- Multiple consumers share the same contract.
- You want object-level schema permissions.
- You want to hide underlying JOINs/schemas.
- You want named, managed dependencies.
- You want to version a read model.

### 28.3. CTEs Are Also Not a Cache by Default

In modern PostgreSQL, CTEs may be inlined or materialized depending on conditions and the `MATERIALIZED/NOT MATERIALIZED` keywords. Never judge a view as fast/slow based on slogans about CTEs being "better" or "worse."

---

## 29. Views and Materialized Views: Practical Example

From the regular reporting view:

```sql
SELECT *
FROM view_contract_lab.v_daily_paid_orders;
```

you can create a materialized view that stores the aggregated definition's results:

```sql
CREATE MATERIALIZED VIEW view_contract_lab.mv_daily_paid_orders
AS
SELECT *
FROM view_contract_lab.v_daily_paid_orders
WITH DATA;
```

Query:

```sql
SELECT *
FROM view_contract_lab.mv_daily_paid_orders
WHERE tenant_id = 10
ORDER BY order_day_utc;
```

### 29.1. Base Table Changes Do Not Auto-Update Materialized Views

For example, after an order changes from PENDING to PAID, querying the regular view sees the new metric under the appropriate snapshot; the materialized view retains old results until refreshed.

```sql
REFRESH MATERIALIZED VIEW
    view_contract_lab.mv_daily_paid_orders;
```

### 29.2. Indexes on Materialized Views

Unlike regular views, materialized views store physical data and can be indexed:

```sql
CREATE UNIQUE INDEX idx_mv_daily_paid_tenant_day
ON view_contract_lab.mv_daily_paid_orders (
    tenant_id, order_day_utc
);
```

Only use UNIQUE when there is truly one row per key pair; with our lab's GROUP BY definition, that pair is the output grain.

### 29.3. Refresh Concurrently

Under conditions supported by PostgreSQL—such as a populated materialized view with a valid unique index using only column names covering all rows—you can run:

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY
    view_contract_lab.mv_daily_paid_orders;
```

This does not mean refresh is free or incremental. It reduces certain reader blocking during refresh, with its own costs and constraints.

### 29.4. Choosing Based on Need

| Requirement | Option to Consider |
| --- | --- |
| Always read fresh data per DB snapshot | Regular view |
| Stable column contract, simple JOINs | Regular view |
| Expensive aggregate queries, dashboard tolerates lag | Materialized view |
| Incremental event updates near real time | Summary table/pipeline with idempotency |
| One-off query | SELECT/CTE |
| Query interface needing parameters | SQL function or query with bind parameters |

---

## 30. Reading Data Through Views and MVCC

PostgreSQL uses **Multi-Version Concurrency Control (MVCC)**. A view does not create an independent consistency boundary outside transactions.

### 30.1. One SELECT Is One Query

When an application executes:

```sql
SELECT *
FROM view_contract_lab.v_order_read_model
WHERE tenant_id = 10;
```

it sees data according to the transaction/statement's snapshot and isolation level.

### 30.2. Two SELECTs Can Differ

Under `READ COMMITTED`, each SELECT in the same transaction can take a new snapshot per isolation rules. If another transaction COMMITs an UPDATE between two statements, view results can change.

### 30.3. Consistent Multi-Query Reads in One Transaction

If multiple reports require the exact same snapshot, consider `REPEATABLE READ` inside a short read transaction, aligned with business needs and system characteristics.

Never keep a transaction open for hours just to "freeze a view": it is not a snapshot cache mechanism, and long-running transactions hinder VACUUM/MVCC cleanup.

### 30.4. Views on a Standby Can Lag

If an application queries a view on an **asynchronous replica**, data can trail the primary due to replication lag. Views do not eliminate this lag.

### 30.5. Multiple Views in One Statement

When a single SELECT JOINs multiple views, underlying tables are processed under the snapshot active for that statement. Do not build dashboards from several independent HTTP requests and assume they all read the exact same point in time.

---

## 31. Java/JDBC Applications Reading Views

In Java, a view can serve as a data source mapped to a DTO just like a table query.

Example:

```java
import java.math.BigDecimal;
import java.time.OffsetDateTime;

public record OrderReadDto(
    int tenantId,
    long orderId,
    String customerName,
    String status,
    BigDecimal grossAmount,
    OffsetDateTime orderedAt
) {}
```

Repository:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

public final class OrderReadRepository {

    public List<OrderReadDto> listPaidOrders(
            Connection connection,
            int authenticatedTenantId) throws SQLException {

        String sql = """
            SELECT
                tenant_id,
                order_id,
                customer_name,
                status,
                gross_amount,
                ordered_at
            FROM view_contract_lab.v_order_read_model
            WHERE tenant_id = ?
              AND status = 'PAID'
            ORDER BY ordered_at DESC, order_id DESC
            """;

        try (PreparedStatement ps =
                     connection.prepareStatement(sql)) {
            ps.setInt(1, authenticatedTenantId);

            List<OrderReadDto> results = new ArrayList<>();

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    results.add(new OrderReadDto(
                        rs.getInt("tenant_id"),
                        rs.getLong("order_id"),
                        rs.getString("customer_name"),
                        rs.getString("status"),
                        rs.getBigDecimal("gross_amount"),
                        rs.getObject(
                            "ordered_at",
                            OffsetDateTime.class
                        )
                    ));
                }
            }

            return results;
        }
    }
}
```

### 31.1. Views Do Not Replace Bind Parameters

You must still use `PreparedStatement`. Never concatenate user input into WHERE/ORDER BY unsafely.

### 31.2. Tenant Parameters Must Be Trusted

`authenticatedTenantId` must come from a server-authenticated context, not an unverified request string assumed to represent valid permission. And if SQL clients can omit the WHERE clause, database-level permission policies must still be strong enough.

### 31.3. Mapping by Stable Column Names

Changing `gross_amount` to `amount` in the view will break `rs.getBigDecimal("gross_amount")`. That is why metadata and contract tests must protect column names and types.

### 31.4. In ORMs

You can map a view as a read-only entity or DTO/projection depending on the library. Never assume a view with JOINs and computed columns becomes an ORM object safe for UPDATE/DELETE.

Define a stable key, read-only intent, and clear transaction/flush behavior.

---

## 32. NULL, Timezone, and Data Type Contracts

A view can alter how data is presented, but must make the contract explicit.

### 32.1. NULLs from LEFT JOIN

If you want to preserve orders even without a matching related record, a view may use LEFT JOIN. Right-hand columns can then be NULL.

Consumers must know:

```text
Can customer_name be NULL?
Does NULL mean missing data or not permitted to view?
```

Do not blindly `COALESCE(customer_name,'Unknown')` if it masks the business distinction between a customer lacking data and restricted data.

### 32.2. TIMESTAMPTZ and Reporting Days

View:

```sql
SELECT (ordered_at AT TIME ZONE 'UTC')::DATE AS day_utc
```

exposes a **UTC date**, which differs from a date in `Asia/Ho_Chi_Minh`. If reporting by local date, document the timezone and day boundaries clearly.

### 32.3. NUMERIC and Currencies

`NUMERIC(14,2)` suits exact decimal arithmetic under defined rounding rules; a view should not blindly mix different currencies into a single SUM without defining exchange rates.

### 32.4. ENUM/TEXT and Evolution

If `status` is TEXT with a CHECK constraint, adding a new value can break consumers with unhandled `switch`/`CASE` branches. The view still returns TEXT, yet the business contract expanded. Test the full set of valid status values, not just column types.

---

## 33. View Migrations via Expand–Migrate–Contract

A safe strategy when changing schemas:

### Phase A — Expand

Add new tables/columns and compatibility write mechanisms if needed, without breaking views currently used by consumers.

Example adding a new column to the base table:

```sql
ALTER TABLE view_contract_lab.orders
ADD COLUMN currency_code TEXT;
```

At this point, the old view continues exposing the same column set as before.

### Phase B — Backfill and Verify

Existing data must be populated with accurate values. Do not assign a default currency like VND if the system supports multiple currencies and the value cannot be derived from data.

Run data migrations and verify constraints, JOINs/row counts, and correctness before switching views.

### Phase C — Create New View Interface or Append Columns at End

Example v2 exposing currency:

```sql
CREATE VIEW view_contract_lab.v_order_amount_v2 AS
SELECT
    tenant_id,
    order_id,
    status,
    amount AS gross_amount,
    currency_code
FROM view_contract_lab.orders;
```

### Phase D — Migrate Consumers

Update DTOs/BI reports/ETLs, grant SELECT on the new view, verify query plans, metrics, and permissions per role.

### Phase E — Contract

Only once you are certain no consumers depend on the old interface should you consider dropping/renaming, revoking grants, or removing old base columns.

### 33.1. Why Not DROP CASCADE First?

`DROP VIEW ... CASCADE` can delete dependent views. If multiple teams share a schema, the blast radius extends beyond a single application. Map all dependencies before migrating.

### 33.2. Testing on Staging

A solid migration should run:

- Actual DDL in exact order.
- Before/after contract queries.
- Permission checks.
- EXPLAIN on key queries.
- Rollback/recovery checks.
- Connectivity tests from both old and new application versions.

---

## 34. When Should You Create a View and When Not?

| Scenario | Is a View Appropriate? | Reason |
| --- | --- | --- |
| Multiple services need the same JOIN and column names | Yes | Unified read interface |
| Restricting columns exposed to a reporting role | Yes, with proper permissions | Narrows data exposure surface |
| Hiding internal normalization structure | Yes | Reduces coupling |
| Reporting metrics sharing one definition | Yes, if formula is correct | Centralizes semantics |
| Caching COUNT(*) over billions of rows | Regular view is insufficient | Needs materialization/summary |
| INSERT/UPDATE into a complex JOIN | Needs different design or trigger | Not automatically writable |
| Query interface needing parameters | Use view+WHERE or SQL function | Views have no built-in parameters |
| Simple one-off query | Not necessary | Direct SELECT/CTE is enough |
| Enforcing tenant isolation for untrusted users | View is only part of it | Must have auth/RLS/permissions |
| Streaming data to another system | Insufficient | Needs dedicated API/export/replication |
| Full-text search, JSONB GIN | Can expose via view | But indexes live on base tables |
| Many redundant abstraction view layers | Reconsider | Can complicate debugging |
| Rapidly changing data, dashboard tolerates lag | Consider materialized view | Trades freshness for compute cost |

### 34.1. A View Is Not a "Better Table"

Views organize query logic and access; base tables store data and enforce constraints. Use each for its proper role.

### 34.2. Do Not Create a View for Every Small SELECT

If every API endpoint adds three view layers without real reuse or clear contracts, object counts grow, dependencies tangle, and schema changes become harder.

### 34.3. Do Not Put All Business Logic Into Views

Workflows involving state machines, multi-step writes, external API calls, queues, idempotency, write contention, and auditing generally belong in appropriate services/transactions/procedures. A SELECT view cannot handle the full business lifecycle.

---

## 35. Naming Conventions and View Lifecycle Management

A helpful convention:

```text
internal.orders
internal.customers

api.v_order_read_model
api.v_customer_overview_v1

reporting.v_daily_paid_order_value
reporting.mv_daily_paid_order_value
```

### 35.1. Descriptive Names

Names should convey:

- Primary entity: order, customer, invoice.
- Grain: one row per order, per customer, or per day.
- Scope: active, paid, historical.
- Key unit/timing: order value, captured payments, UTC day.
- Contract version when external-team consumers exist.

Avoid overly generic names like `v_data`, `v_final`, `v_temp2`.

### 35.2. Document with COMMENT ON VIEW

```sql
COMMENT ON VIEW view_contract_lab.v_daily_paid_orders
IS 'One row per tenant and UTC order day. Paid order count and sum of amount for orders whose current status is PAID; not a cash-flow metric.';
```

This metadata helps users understand semantics, especially for financial reports.

### 35.3. Ownership and DDL Governance

Establish clear processes for:

- Who can CREATE/REPLACE/DROP?
- Who owns the view?
- Who can GRANT SELECT?
- Who reviews security_invoker/security_barrier?
- Who validates column name/type changes?
- Which versions can be deprecated?
- Who manages migrations in CI/CD?

### 35.4. Avoid Creating Views as Superuser Unnecessarily

Use a dedicated owner role, least-privilege principles, and a consistent migration pipeline. Overprivileged owners can alter security semantics.

---

## 36. Testing View Contracts

A view can survive a migration and still return wrong data. Multiple test layers are needed.

### 36.1. Testing Columns, Order, and Types

Query metadata:

```sql
SELECT
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'view_contract_lab'
  AND table_name = 'v_order_read_model'
ORDER BY ordinal_position;
```

Compare against the expected DTO schema or API contract.

### 36.2. Testing Row Counts and JOINs

In the lab, each order has exactly one customer in the same tenant. The read model view row count should equal the orders table count:

```sql
SELECT
    (SELECT COUNT(*)
     FROM view_contract_lab.orders) AS base_orders,
    (SELECT COUNT(*)
     FROM view_contract_lab.v_order_read_model) AS view_orders;
```

If the view returns more rows, a JOIN may be duplicating rows. If fewer, a JOIN may be dropping orders with missing related rows or a filter is intentionally excluding them.

### 36.3. Testing Tenant Isolation Semantically

```sql
SELECT
    tenant_id,
    COUNT(*) AS orders
FROM view_contract_lab.v_order_read_model
GROUP BY tenant_id
ORDER BY tenant_id;
```

The lab expects 4 orders for tenant 10 and 3 for tenant 20. This checks the JOIN model, **not security enforcement** for tenant isolation.

Security tests must run under restricted roles and verify that cross-tenant access is blocked under actual policies.

### 36.4. Testing That Sensitive Columns Are Absent

Query `information_schema.columns` to confirm the exposed view omits `email` or `internal_note` when required by the contract.

### 36.5. Testing Metric Semantics

Compare `v_daily_paid_orders` numbers against direct base table queries over a known dataset. Check REFUNDED, CANCELED, and PENDING statuses.

### 36.6. Testing EXPLAIN at Representative Scale

Use data close to production workload to see whether the planner filters tenant/time on base tables, whether indexes fit, and whether aggregations spill. On a seven-row lab, execution timings do not represent production.

---

## 37. Common Mistakes

| Misconception or Mistake | Reality |
| --- | --- |
| "CREATE VIEW pre-stores all rows." | Regular views store definitions, not materialized results |
| "Views are always faster than the underlying SELECT." | Planner still executes underlying logic; no automatic caching |
| "With a VIEW, indexes aren't needed." | Indexes still live on the base tables |
| "CREATE INDEX directly on a normal view." | Normal views have no physical result heap to index |
| "If a view has ORDER BY, all clients get sorted results automatically." | Consumers should specify ORDER BY per contract |
| "LIMIT in a view only optimizes the query." | LIMIT can alter the dataset the view exposes |
| "SELECT * in CREATE VIEW auto-adds future table columns." | View definitions do not expand dynamically like that |
| "Changing an alias doesn't affect clients." | Column names are part of the contract |
| "Changing column types freely in CREATE OR REPLACE VIEW." | Constrained by existing column types/names/order |
| "Removing a column from a view is non-breaking." | Can break DTOs, BI reports, and dependent views |
| "DROP ... CASCADE only deletes the target view." | Can delete multiple dependent objects |
| "Views with JOINs are automatically updatable." | Many JOIN views are not automatically updatable |
| "GROUP BY views can UPDATE summaries like tables." | Typically read-only interfaces |
| "CHECK OPTION blocks all invalid DML on the table." | Only guards DML through qualifying views |
| "LOCAL checks all underlying view layers." | LOCAL and CASCADED behave differently |
| "A view with WHERE tenant is enough for security." | Requires auth, permissions, RLS, owner semantics |
| "GRANT SELECT on a view always requires GRANT SELECT on base tables." | Default uses view owner privileges; invoker differs |
| "security_invoker and security_barrier are the same." | One governs permissions, the other predicate pushdown |
| "security_invoker always lets view-only roles work." | May require base table privileges and fail with permission denied |
| "View owner doesn't affect RLS." | Owner/BYPASSRLS/FORCE RLS can affect enforcement |
| "Setting current_setting for tenant is safe for any client." | Context must come from a trusted layer and resist spoofing |
| "Since the view hides email, the role can't read email." | If the role still has base table permissions, it can read directly |
| "A view reads an immutable snapshot for the app's entire lifetime." | Each query follows isolation/snapshot rules |
| "Views on a read replica always return the latest data." | Replicas can experience lag |
| "Views accept parameters like SQL functions." | Views normally take filters from the caller's WHERE clause |
| "CTEs and views share the same lifecycle." | CTEs are statement-scoped; views are schema-scoped |
| "Materialized views auto-refresh after each UPDATE." | Require explicit REFRESH per designed schedule |
| "REFRESH CONCURRENTLY needs no unique index." | Requires a qualifying unique index and populated view |
| "A view with a revenue metric is self-explanatory." | Must document status, timing, units, and refunds |
| "Multi-table views never multiply rows." | JOIN fan-out still corrupts metrics |
| "All views should be designed as writable." | Read-only contracts are usually safer and clearer |
| "Stacking dozens of view layers is always good abstraction." | Can worsen dependencies, debugging, and performance |
| "A view SELECT succeeding as superuser proves permissions are right." | Must test from actual restricted roles |
| "If a view still SELECTs after a schema change, the contract hasn't changed." | Semantics/NULLs/timezones may have shifted |

---

## 38. Practice Exercises

### Exercise 1 — Explaining Views

Describe what data is stored in the `orders` table and what metadata is stored for `v_order_read_model`. Why is a regular view not a cache?

### Exercise 2 — Creating a Simple View

Create a view exposing `tenant_id`, `order_id`, `status`, and `amount` from orders. Run a SELECT filtering for tenant 10.

### Exercise 3 — Joining Tenants Correctly

Write a view joining orders and customers on `(tenant_id,customer_id)`. If you joined only on customer_id, which lab rows risk matching a customer from the wrong tenant?

### Exercise 4 — Column Contracts

Create a view with aliases `customer_name` and `gross_amount`. Why can renaming the aliases to `name` and `amount` break consumers?

### Exercise 5 — Hiding Internal Columns

Create an order read view that omits `email` and `internal_note`. Explain why base table permission management is still needed.

### Exercise 6 — Derived Columns

Create a view with `is_paid` and `lifecycle_group` using CASE. If an order's status changes from PENDING to PAID, when does the data returned by the view reflect the change?

### Exercise 7 — Aggregated Views

Create a view counting PAID orders per tenant and UTC day. State the output grain and why `SUM(amount)` in this view must not be called "net captured revenue" without a payments table.

### Exercise 8 — Outer WHERE Clauses

Query `v_order_read_model` by tenant and date range. Predict at which step the optimizer can apply the predicates, then use EXPLAIN to observe it.

### Exercise 9 — ORDER BY and Pagination

Write a query fetching the 20 latest orders for tenant 10. Why must ORDER BY be in the consumer query and include `order_id` as a tie-breaker?

### Exercise 10 — LIMIT Inside a View

A view selects the 10 latest orders **system-wide** and then the application filters for tenant 10. Why does the result differ from "the 10 latest orders for tenant 10"?

### Exercise 11 — CREATE OR REPLACE VIEW

Modify a view definition keeping existing columns intact and appending a new column at the end. What changes are disallowed under standard replace rules?

### Exercise 12 — Renaming a View Column

Use `ALTER VIEW ... RENAME COLUMN` on a test view. Which consumers could be impacted?

### Exercise 13 — Versioning

Design `v_orders_v1` and `v_orders_v2` with new column names. Describe the steps to migrate consumers without forcing everyone to deploy simultaneously.

### Exercise 14 — Dependencies

Suppose a view references `orders.status`. What happens if you run `ALTER TABLE orders DROP COLUMN status`? Why must `CASCADE` be treated with extreme caution?

### Exercise 15 — pg_get_viewdef

Use `pg_get_viewdef` to inspect a view's SELECT and compare it with your original `CREATE VIEW`. Why doesn't the output necessarily preserve your exact formatting?

### Exercise 16 — information_schema

List column positions, names, and types of `v_order_read_model` from `information_schema.columns`. Use the output as part of a contract test.

### Exercise 17 — pg_views

List views in the lab schema and their owners. How would you detect a view owned by an inappropriate role?

### Exercise 18 — EXPLAIN on a JOIN View

Run `EXPLAIN (ANALYZE, BUFFERS)` on a query filtering tenant/status. Which base tables and JOIN nodes appear? Why might a seven-row lab table use Seq Scan?

### Exercise 19 — Base Table Indexes

Create an index on `orders(tenant_id,ordered_at)` and run EXPLAIN on a view query. Why can't you create an index directly on a normal view?

### Exercise 20 — Updatable Simple Views

Create a view selecting columns directly from orders, run an UPDATE inside a transaction, and ROLLBACK. Where does the data change?

### Exercise 21 — Can a JOIN View Be Updated?

Run `UPDATE` on an orders/customers JOIN view without an INSTEAD OF trigger. Explain why mapping the operation to base tables is ambiguous.

### Exercise 22 — CHECK OPTION

Create a view of only PAID orders for tenant 10 with CASCADED CHECK OPTION. Attempt to change status to PENDING through the view. Why is the UPDATE rejected?

### Exercise 23 — LOCAL and CASCADED

Create a lower-layer view filtering tenant and an upper-layer view filtering status. Explain the difference between LOCAL and CASCADED CHECK OPTION. Why do they not replace tenant authorization?

### Exercise 24 — INSTEAD OF Trigger

Diagram the handling of an UPDATE on a JOIN view that modifies data across two base tables. Which transaction/permission/concurrency checks must reside in the trigger or service?

### Exercise 25 — GRANT SELECT on a View

In a lab environment with role creation privileges, grant SELECT only on one view and USAGE on the schema. Why can the role read a default view without necessarily having SELECT on the base tables?

### Exercise 26 — SECURITY INVOKER

Create a view `WITH (security_invoker=true)` in a supported PostgreSQL version. What error will a role with view SELECT but no base table SELECT encounter?

### Exercise 27 — SECURITY BARRIER

Explain why a view filtering sensitive rows might use `security_barrier` and why this option can affect predicate pushdown. Does it replace RLS?

### Exercise 28 — RLS and Ownership

Describe a case where the view owner has different privileges than the caller. Why does testing as superuser fail to prove real callers only see their own tenant?

### Exercise 29 — Session Tenant Context

If RLS relies on `current_setting('app.tenant_id')` but clients can SET the value themselves, what is the risk? Explain how to ensure trustworthy tenant context in the architecture.

### Exercise 30 — Views vs. CTEs

A one-off query needs to be split into two logical steps. Why is a CTE sufficient? When should reusable logic be promoted to a named view?

### Exercise 31 — Views vs. SQL Functions

Design a function accepting `tenant_id` and a date range, returning a list of orders. Why does function EXECUTE permission still not replace authorization checks?

### Exercise 32 — Views vs. Materialized Views

Create a materialized view from `v_daily_paid_orders`, add a unique index, and refresh it. When an order changes status, how do results of the regular view and materialized view differ before refresh?

### Exercise 33 — REFRESH CONCURRENTLY

State the unique index requirements for concurrent refresh in modern PostgreSQL. Why does concurrent refresh not mean data is always up to date?

### Exercise 34 — MVCC

Under READ COMMITTED, can two SELECTs on the same view at different times see different order counts? When is REPEATABLE READ useful for multiple reports needing one snapshot?

### Exercise 35 — JDBC Mapping

Write a PreparedStatement SELECTing from a view and mapping columns by name to a DTO. Why can renaming the `gross_amount` alias break the mapper?

### Exercise 36 — NULLs and LEFT JOIN

Design a view using LEFT JOIN to preserve orders without matching related records. Test whether `customer_name` can be NULL and whether `COUNT(*)` could be misinterpreted.

### Exercise 37 — Semantic Contracts

A view changes from "total value of PAID orders" to "captured cash minus refunds," while still returning NUMERIC. Why is this a breaking change even when column types and names stay identical?

### Exercise 38 — Expand–Migrate–Contract

Plan a migration from the old customer name column to the new customer name schema while keeping consumers on view v1; include backfill, view v2, permissions, testing, and retiring v1.

### Exercise 39 — JOIN Fan-Out Bugs

A reporting view JOINs orders with multiple `order_items` and computes `SUM(o.amount)`. Why can the result be multiplied? Propose pre-aggregating at the proper grain.

### Exercise 40 — Production View Design

A multi-tenant system has hundreds of millions of orders, multiple applications needing read models, daily dashboards, and roles permitted to view only non-sensitive data. Design the schema/view/materialized view layout, permissions/RLS, indexes, API versioning, and test suite. Explain the responsibility boundaries of each component.

---

## 39. Design Checklist for Views as Data Interfaces

| Question | How to Evaluate |
| --- | --- |
| Who does the view serve? | API, Java DTO, BI, export, internal |
| What grain do consumers need? | One row per order, customer, or day |
| Is the logic reused? | JOINs/metrics appearing in multiple places |
| Is the exposed column list explicit? | No casual SELECT * |
| Are column names/types/order a contract? | Metadata and contract tests |
| Which columns are sensitive? | Expose only what is necessary |
| Do JOINs include full tenant keys? | Prevent cross-tenant customer mismatches |
| Could JOINs multiply rows? | Verify cardinality/fan-out |
| Are metrics clearly defined? | Status, date basis, amount, refunds |
| Are there NULLs/LEFT JOINs? | Consumers understand what NULL means |
| Are timezones/units specified? | UTC/local day, currency, scale |
| Should the view allow writes? | Distinguish read-only vs. updatable |
| Is CHECK OPTION needed? | LOCAL/CASCADED when writing via views |
| Does a JOIN view need an INSTEAD OF trigger? | Only with an explicit write contract |
| Which role owns the view? | Least privilege, not casual superuser |
| Do callers have base table permissions? | Verify GRANT/REVOKE |
| Is RLS in place? | Owner/invoker privileges, FORCE/BYPASSRLS |
| Is security_invoker needed? | PostgreSQL version and base permissions |
| Is security_barrier needed? | Leakproof/pushdown risk |
| Is tenant context trustworthy? | Server-side identity / DB policy |
| Tested with real roles? | Not solely run as superuser |
| Does CREATE OR REPLACE alter old columns? | Respect name/type/order constraints |
| Is there a breaking semantic change? | New version / migration |
| Are there dependent views? | Check before DROP/ALTER |
| Do callers need ORDER BY? | Deterministic ordering |
| Is there a LIMIT inside the view? | Assess semantic impact |
| Are indexes present on base tables? | EXPLAIN and selectivity |
| Does the view have a large GROUP BY? | Aggregation cost |
| Is a materialized view needed? | Read frequency, refresh latency |
| Is there a freshness contract? | MVCC, replica lag, REFRESH |
| Are parameters needed? | View+WHERE or SQL function |
| Is there JDBC/ORM mapping? | DTO projection and read-only intent |
| Are migrations managed in CI/CD? | Versioning and rollback |
| Is COMMENT ON VIEW present? | Document grain/metrics |
| Are there contract tests? | Columns/types, row counts, permissions |
| Are benchmarks run? | Planning/Execution Time, Buffers |
| Are there too many view layers? | Complexity and plan readability |
| Are permissions reviewed periodically? | Least privilege and data exposure |

## Conclusion

**Views as query interfaces and data abstraction layers** enable PostgreSQL to provide a stable data layer for applications, reporting, and cross-system integration. Instead of forcing every consumer to understand all underlying tables, a view centralizes JOINs, column renaming, computed expressions, and part of the data-exposure rules.

Core principles:

1. **Regular views store SELECT definitions, not precomputed results.** Querying a view reads underlying data according to PostgreSQL's snapshot and planner.
2. **A view is a data contract.** Column names, types, order, grain, timezones, NULLs, and business semantics all matter.
3. **Abstraction reduces coupling but does not enforce logic correctness by itself.** Wrong tenant JOINs or SUMs after JOIN fan-out remain wrong even inside a view.
4. **CREATE OR REPLACE VIEW has constraints.** Do not arbitrarily rename, retype, or reorder existing columns; use migrations/versioning for breaking changes.
5. **Not every view is writable.** Simple views can be automatically updatable; JOIN/aggregate views typically require a different design. CHECK OPTION only governs DML through qualifying views.
6. **Security must be designed explicitly.** View permissions, ownership, `security_invoker`, `security_barrier`, and RLS play distinct roles; creating a view does not constitute authorization by itself.
7. **Views are neither indexes nor caches.** When queries are slow, use EXPLAIN and base table indexes; for repeated expensive reports, consider materialized views or summary tables with freshness contracts.
8. **Distinguish views, CTEs, and functions.** Views are reusable schema objects, CTEs are statement-scoped, and functions support parameters and distinct execution privileges.
9. **Test both structure and semantics.** Use metadata, row counts, EXPLAIN, role/tenant tests, and metric reconciliation to catch breaking changes.
10. **Manage lifecycles like APIs.** Name clearly, document with COMMENT, enforce least privilege, version when needed, and use expand–migrate–contract for safe schema evolution.

A good view does more than shorten SQL. It gives applications a **well-defined, testable, permissioned, and safely evolvable data surface**, while PostgreSQL continues to enforce correctness, query optimization, and transactional consistency on the underlying tables.
