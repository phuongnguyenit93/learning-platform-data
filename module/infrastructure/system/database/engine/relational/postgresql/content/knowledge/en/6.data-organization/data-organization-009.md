# COMMENT and documenting objects directly inside PostgreSQL

When a database contains hundreds of tables and thousands of columns, object names do not always explain business meaning. Which states can a `status` column hold? Is `amount` before or after tax? Does `customer_id` reference the purchasing customer or the billed customer? Which API was an index created to serve? If that knowledge exists only in a developer's head or in a document outside the repository, future maintainers can easily misunderstand it when writing queries or migrations.

PostgreSQL supports **`COMMENT ON`** to store descriptions directly in **the database object metadata**. Those descriptions can be inspected with `psql`, read via system catalogs such as `pg_description`, queried through functions like `obj_description()` and `col_description()`, or included in schema exports to live alongside migration history.

Documenting right inside the database gives data consumers context right where they work. However, comments **do not replace** constraints, data modeling, authorization, comprehensive business documentation, or version control workflows. This lesson belongs to the **Data Organization** chapter of PostgreSQL, focusing on syntax, writing useful descriptions, practical examples, retrieval methods, and safely managing comments in projects.

## 1. What is COMMENT ON?

`COMMENT ON` is a PostgreSQL DDL statement used to **attach a text description to a database object**. Example:

~~~sql
COMMENT ON TABLE public.orders IS
    'Customer orders. Each row represents one unique order.';

COMMENT ON COLUMN public.orders.created_at IS
    'Order creation timestamp; stored as timestamptz.';
~~~

These two statements add no rows and change no column types. They add **metadata explaining the objects**.

A comment can help answer:

- What business purpose does this object serve?
- What is the exact meaning of the column?
- What are the units, time zone, or precision of the value?
- Which values or states are expected?
- Which system produces the data and under what update rules?
- Why is an index or constraint kept?
- What caveats apply when using a view, function, or foreign key?

### 1.1. Difference among name, data type, constraint, and comment

Suppose a column is:

~~~sql
amount NUMERIC(14, 2) NOT NULL
~~~

What is already known:

- The name is `amount`.
- The data type is `NUMERIC(14,2)`.
- `NULL` cannot be stored.

What is **not yet known**:

- Is this the order total or the refunded total?
- Is the currency VND, USD, or determined by another column?
- Does the value include taxes and shipping fees?
- Can it be negative for refund orders?
- Is the value captured at creation time or recalculated?

A comment can clarify:

~~~sql
COMMENT ON COLUMN public.orders.amount IS
    'Order total after discounts, excluding shipping fees; '
    'currency is VND per this system''s configuration.';
~~~

Yet if the real database supports multiple currencies, writing "currency is VND" becomes inaccurate documentation. **Write comments only once business rules are verified**; never guess meaning from a column name alone.

### 1.2. Comments are not constraints

~~~sql
COMMENT ON COLUMN public.products.price IS
    'Price must not be negative.';
~~~

This is merely descriptive text. It **does not block** writing `-100` into the column. To have PostgreSQL enforce the rule, add an appropriate constraint:

~~~sql
ALTER TABLE public.products
ADD CONSTRAINT chk_products_price
CHECK (price >= 0);
~~~

Then, a comment can explain the **reason** behind the constraint:

~~~sql
COMMENT ON CONSTRAINT chk_products_price
ON public.products IS
    'Disallows negative selling prices when creating or updating products.';
~~~

Put simply:

> **Constraints let the database engine enforce rules; comments help humans understand them.**

## 2. Which PostgreSQL objects can have comments?

PostgreSQL supports comments on many object kinds. Common categories include:

| Object | Syntax pattern | What to document |
|---|---|---|
| Schema | `COMMENT ON SCHEMA ... IS ...` | Business scope and conventions |
| Table | `COMMENT ON TABLE ... IS ...` | Grain of a single row, data lifecycle |
| Column | `COMMENT ON COLUMN table.column IS ...` | Meaning, units, NULL semantics, timing |
| View | `COMMENT ON VIEW ... IS ...` | Query purpose and usage limits |
| Materialized view | `COMMENT ON MATERIALIZED VIEW ... IS ...` | Aggregated data, refresh schedule |
| Index | `COMMENT ON INDEX ... IS ...` | Supported query pattern, reason for existing |
| Constraint | `COMMENT ON CONSTRAINT ... ON table IS ...` | Business rule enforced |
| Sequence | `COMMENT ON SEQUENCE ... IS ...` | Value generation purpose |
| Function | `COMMENT ON FUNCTION name(types) IS ...` | Inputs, outputs, properties, and limits |
| Procedure | `COMMENT ON PROCEDURE name(types) IS ...` | Action performed and side effects |
| Type / domain | `COMMENT ON TYPE/DOMAIN ... IS ...` | Type semantics, allowed value range |
| Trigger | `COMMENT ON TRIGGER name ON table IS ...` | When it fires and its effects |
| Policy | `COMMENT ON POLICY name ON table IS ...` | Goal of the RLS policy |
| Database | `COMMENT ON DATABASE ... IS ...` | Database's role in the system |
| Role | `COMMENT ON ROLE ... IS ...` | Purpose of the account/privilege group |

PostgreSQL can also support comments on additional objects such as tablespaces, extensions, text-search objects, operators, publications, or subscriptions depending on version. You do not need to memorize the entire list immediately: in `psql`, inspect the syntax for your active version with:

~~~text
\h COMMENT
~~~

**The syntax across categories is not completely uniform.** In particular, commenting on a column, constraint, trigger, or routine has specific object-identification syntax; you cannot simply copy `COMMENT ON TABLE` and swap one keyword arbitrarily.

## 3. General syntax and writing description strings

General form:

~~~sql
COMMENT ON object_type object_identity IS 'description';
~~~

Where:

- `object_type` is the kind of object, e.g., `TABLE`, `COLUMN`, `VIEW`.
- `object_identity` uniquely identifies the object to describe.
- After `IS` comes a **text string value** or `NULL` to remove the comment.

Example:

~~~sql
COMMENT ON SCHEMA sales IS
    'Sales business data for the application.';

COMMENT ON TABLE sales.orders IS
    'Each row is an order placed by a customer.';

COMMENT ON COLUMN sales.orders.status IS
    'Business status of the order along the processing workflow.';
~~~

### 3.1. Each object holds one current comment

When running `COMMENT ON` again on the same object, PostgreSQL **replaces the previous description** with the new one:

~~~sql
COMMENT ON TABLE sales.orders IS
    'Orders created from the application.';

COMMENT ON TABLE sales.orders IS
    'Each row is one order; data is managed by the sales service.';
~~~

After the second statement, the active description is the second string. This is not an append-only log or version-history mechanism for comments.

If you need to track how descriptions evolved over time, rely on **migration history, version control systems, or audit logs**, not merely reading the current comment.

### 3.2. Using IS NULL to remove a comment

~~~sql
COMMENT ON TABLE sales.orders IS NULL;
~~~

The `sales.orders` object still exists; only its comment is removed.

Distinguish between:

~~~sql
-- Remove the description:
COMMENT ON TABLE sales.orders IS NULL;

-- Set the description to an empty string:
COMMENT ON TABLE sales.orders IS '';
~~~

One uses SQL `NULL`, while the other uses an **empty string**. In documentation coverage reports, both can be treated as "missing a useful description", yet never assume they share identical metadata representations.

### 3.3. Single quotes inside comments

SQL strings use single quotes. If a comment needs a single quote, double the quote:

~~~sql
COMMENT ON COLUMN sales.orders.customer_note IS
    'Customer-entered text; do not treat the word ''confirmed'' as a system status.';
~~~

PostgreSQL supports Unicode text when client/server encodings are compatible; comments can be written in Vietnamese or any Unicode language:

~~~sql
COMMENT ON TABLE sales.orders IS
    'Order information; used for sales processing and reconciliation.';
~~~

When using migration tools, ensure SQL files are saved in a compatible encoding, typically UTF-8.

### 3.4. Multi-line long descriptions

You can write longer strings, for instance using **dollar-quoted strings** to include quotes and line breaks cleanly:

~~~sql
COMMENT ON TABLE sales.orders IS $doc$
Orders created by the sales system.

Scope:
- Each row represents a single order.
- Not an aggregated accounting ledger.
- Deleting or hiding orders must follow data retention policies.
$doc$;
~~~

Dollar quoting is handy when descriptions contain single quotes or multiple paragraphs. However, overly long comments become hard to read in `\d+` and difficult to maintain; keep database comments **concise, accurate, and practical**, and place lengthy process docs in version-controlled documentation.

## 4. Hands-on: creating a schema to document

This section targets **PostgreSQL 12+** in a test database. Object-creation statements should only run in a lab environment with `CREATE` privileges. If you already have a `comment_lab` schema from an earlier attempt, rename it or use another database to avoid conflicts; never wipe real data just to rerun examples.

### 4.1. Create the schema

~~~sql
CREATE SCHEMA comment_lab;
~~~

### 4.2. Create the customers table

~~~sql
CREATE TABLE comment_lab.customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY,
    customer_code TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    email TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_customers PRIMARY KEY (customer_id),
    CONSTRAINT uq_customers_code UNIQUE (customer_code)
);
~~~

### 4.3. Create the orders table

~~~sql
CREATE TABLE comment_lab.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY,
    customer_id BIGINT NOT NULL,
    order_status TEXT NOT NULL DEFAULT 'pending',
    total_amount NUMERIC(14, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_orders PRIMARY KEY (order_id),
    CONSTRAINT fk_orders_customers
        FOREIGN KEY (customer_id)
        REFERENCES comment_lab.customers(customer_id),
    CONSTRAINT chk_orders_amount
        CHECK (total_amount >= 0),
    CONSTRAINT chk_orders_status
        CHECK (order_status IN ('pending', 'paid', 'cancelled'))
);
~~~

### 4.4. Create an index and view

~~~sql
CREATE INDEX idx_orders_created_at
ON comment_lab.orders (created_at DESC);

CREATE VIEW comment_lab.v_paid_orders AS
SELECT
    o.order_id,
    c.customer_code,
    o.total_amount,
    o.created_at
FROM comment_lab.orders AS o
JOIN comment_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.order_status = 'paid';
~~~

### 4.5. Create a function

~~~sql
CREATE FUNCTION comment_lab.line_amount(
    p_quantity INTEGER,
    p_unit_price NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
STRICT
AS $$
    SELECT p_quantity * p_unit_price;
$$;
~~~

This function uses multiplication to illustrate a two-parameter signature. It does **not** implement complex pricing logic, taxes, or currencies. All subsequent metadata exercises work even when tables contain zero rows.

## 5. COMMENT ON SCHEMA: describing business scope

~~~sql
COMMENT ON SCHEMA comment_lab IS
    'Practice schema for PostgreSQL documentation; holds sample customer and order data.';
~~~

A good schema-level comment typically explains:

- Which domain the schema belongs to.
- Which system manages objects in the schema.
- Whether it holds source data, reporting data, or staging data.
- Important organizational conventions.

Never store passwords, tokens, connection strings, or secrets in schema comments.

Example for a production system:

~~~sql
COMMENT ON SCHEMA reporting IS
    'Data for reporting queries; do not use as a transactional source of truth.';
~~~

This is a **written convention**—it does not automatically block anyone from writing into the schema. To restrict operations, enforce proper `GRANT`/`REVOKE` privileges and ownership management.

## 6. COMMENT ON TABLE: what does one row mean?

Table-level comments should start with **the unit (grain) of a single row**:

~~~sql
COMMENT ON TABLE comment_lab.customers IS
    'Each row represents one customer in the sample retail system; customer_code is the unique business key.';

COMMENT ON TABLE comment_lab.orders IS
    'Each row represents one order; each record references exactly one customer via customer_id.';
~~~

Clarifying "what one row represents" prevents common mistakes:

- Treating an event log table as a current-state table.
- Treating a snapshot table as mutable source data.
- Confusing an order header table with an order line-items table.
- Confusing a historical archive table with an active operational table.

### 6.1. A useful table comment template

When more than one sentence is needed, you can write:

~~~sql
COMMENT ON TABLE comment_lab.orders IS $doc$
Purpose: stores orders in the sales workflow.
Granularity: one row = one order.
Write source: order-processing service.
Primary relation: customer_id references customers.
Note: do not use this table as an accounting balance ledger.
$doc$;
~~~

Fields such as *write source* or *retention period* should only be documented if someone owns the policy and keeps them synchronized when business logic changes.

### 6.2. Table comments differ from COMMENT ON COLUMN

Table descriptions explain **the overall object**. Do not cram every column's meaning into the table comment; on large tables, consumers inspect individual column descriptions via metadata tools.

A clean division is:

- Table comment: purpose, granularity, business ownership.
- Column comment: meaning, units, and specific conventions.
- Constraint comment: rule protected by the constraint.
- Index comment: query pattern or uniqueness rationale.
- View/function comment: exposed data contract or behavioral specification.

## 7. COMMENT ON COLUMN: the most important case

Columns often have concise names because they appear repeatedly in SQL. Comments preserve ergonomic names while removing ambiguity.

~~~sql
COMMENT ON COLUMN comment_lab.customers.customer_id IS
    'Technical primary key generated by PostgreSQL identity.';

COMMENT ON COLUMN comment_lab.customers.customer_code IS
    'Business customer code; do not convert to numeric because leading zeros may exist.';

COMMENT ON COLUMN comment_lab.customers.customer_name IS
    'Display name of the customer.';

COMMENT ON COLUMN comment_lab.customers.email IS
    'Optional contact email; NULL means no email has been recorded.';

COMMENT ON COLUMN comment_lab.customers.created_at IS
    'Timestamp when the customer record was created; stored as timestamptz.';
~~~

For the orders table:

~~~sql
COMMENT ON COLUMN comment_lab.orders.order_id IS
    'Technical identifier key of the order.';

COMMENT ON COLUMN comment_lab.orders.customer_id IS
    'Customer owning the order; references comment_lab.customers(customer_id).';

COMMENT ON COLUMN comment_lab.orders.order_status IS
    'Order status: pending, paid, or cancelled; allowed values enforced by chk_orders_status.';

COMMENT ON COLUMN comment_lab.orders.total_amount IS
    'Order total in the sample system''s currency; NUMERIC(14,2), non-negative.';

COMMENT ON COLUMN comment_lab.orders.created_at IS
    'Order creation timestamp as timestamptz; not the payment timestamp.';
~~~

### 7.1. Monetary columns: don't just write "amount"

Comments on monetary values should clarify:

- Pre-tax or post-tax?
- Before or after discounts?
- Includes shipping fees or not?
- Where does the currency come from?
- What rounding rule applies?
- Can it be negative?

If the model has only one `total_amount` column without confirmed rules, never write a comment asserting unverified assumptions. Misleading metadata erodes trust faster than missing metadata.

### 7.2. Timestamp columns: know the event moment and time zone

Example:

~~~sql
COMMENT ON COLUMN comment_lab.orders.created_at IS
    'Timestamp when the order record was created; TIMESTAMPTZ. Do not use as delivery time.';
~~~

`TIMESTAMPTZ` in PostgreSQL stores an absolute point in time and displays it in the session's time zone. It **does not store the client's original time zone name** as a separate field.

If business logic needs "transaction date in Vietnam time", document the date-conversion rule; you may need a dedicated business date column or explicitly specified calculation rather than relying solely on the name `created_at`.

### 7.3. Status columns: describe the lifecycle

A `status` column usually needs more than a bare list of values:

~~~text
pending   -> awaiting processing
paid      -> payment confirmed
cancelled -> order cancelled
~~~

Comments can reference the business workflow, yet **do not enforce valid state transitions**. `CHECK` validates only the set of permitted values; preventing invalid transitions like `cancelled` back to `paid` requires application logic or additional database mechanisms.

### 7.4. Nullable columns: explain what "missing" means

These two cases are not equivalent:

- `email IS NULL`: no email collected yet.
- `email = ''`: an empty string was stored.

A comment can help report authors distinguish those two states, provided the application uses them consistently.

If upstream data uses `NULL` with multiple mixed meanings, fix the model or ingestion pipeline rather than papering over it with a polished comment.

## 8. COMMENT ON CONSTRAINT: explaining integrity rules

Constraint names often read like technical shorthand:

~~~text
fk_orders_customers
chk_orders_amount
chk_orders_status
uq_customers_code
~~~

Comments explain **why** they are necessary.

~~~sql
COMMENT ON CONSTRAINT fk_orders_customers
ON comment_lab.orders IS
    'Every order must belong to an existing customer.';

COMMENT ON CONSTRAINT chk_orders_amount
ON comment_lab.orders IS
    'Regular order totals cannot be negative; refunds require a separate model.';

COMMENT ON CONSTRAINT chk_orders_status
ON comment_lab.orders IS
    'Restricts order status to values supported by the processing workflow.';

COMMENT ON CONSTRAINT uq_customers_code
ON comment_lab.customers IS
    'Customer code must be unique to support reconciliation with external systems.';
~~~

Note the syntax:

~~~sql
COMMENT ON CONSTRAINT ten_constraint
ON schema.ten_bang IS '...';
~~~

**The table name is required**, because PostgreSQL must know which table owns the constraint.

### 8.1. New constraints affect data; comments do not

Two distinct operations:

~~~sql
-- Changes the data validation rule.
ALTER TABLE comment_lab.orders
ADD CONSTRAINT chk_orders_example
CHECK (total_amount <= 999999999999.99);

-- Changes only the description of an existing rule.
COMMENT ON CONSTRAINT chk_orders_amount
ON comment_lab.orders IS
    'Total amount must not be less than 0.';
~~~

The `ALTER TABLE` example only illustrates the difference; there is no need to run it in the lab. Adding constraints on live tables can require table scans or affect locks, so handle them via proper migrations.

### 8.2. Is commenting on a primary key useful?

Primary keys may be self-evident in simple tables. When a table uses a composite primary key or a special business key, however, a comment explaining row identification is very helpful.

~~~sql
COMMENT ON CONSTRAINT pk_orders
ON comment_lab.orders IS
    'Technical primary key; do not expose as the customer-facing order number.';
~~~

Avoid repeating obvious definitions in every comment. Prioritize explaining **design decisions and common pitfalls**.

## 9. COMMENT ON INDEX: why does an index exist?

Indexes are typically created to speed up queries or enforce constraints. Over time, operators often see several similar indexes without knowing which ones are still needed.

~~~sql
COMMENT ON INDEX comment_lab.idx_orders_created_at IS
    'Supports listing orders by newest creation time; used by the order history lookup screen.';
~~~

A useful index comment can note:

- The main filter/sort pattern the index serves.
- Critical APIs or reports relying on it.
- Why the column order of a composite index was chosen.
- Whether uniqueness or a constraint depends on it.
- When the index should be re-evaluated.

Hypothetical composite index example:

~~~sql
-- Run only if the workload needs it, in a test environment.
CREATE INDEX idx_orders_customer_created
ON comment_lab.orders (customer_id, created_at DESC);

COMMENT ON INDEX comment_lab.idx_orders_customer_created IS
    'Supports finding a customer''s newest orders: customer_id = ? ORDER BY created_at DESC.';
~~~

### 9.1. Comments do not guarantee the optimizer uses the index

An index documented as "for history queries" does not force PostgreSQL to choose it. The planner may pick a sequential scan if the table is small or estimated cost is lower.

To determine whether an index remains worthwhile, combine `EXPLAIN`, usage statistics, write overhead, and real workloads. **Comments state design intent, not performance certification.**

### 9.2. Commenting on primary key indexes

PostgreSQL automatically creates indexes for primary keys and unique constraints. To document **the integrity rule**, comment on the constraint itself. Comment on the index only when explaining specific index characteristics.

Dropping an index that enforces a constraint is restricted by dependency links. A clear description helps maintainers avoid confusing standalone indexes with constraint-backing indexes.

## 10. COMMENT ON VIEW and MATERIALIZED VIEW

### 10.1. Views as query interfaces

~~~sql
COMMENT ON VIEW comment_lab.v_paid_orders IS
    'List of orders with status paid; exposes only customer code, total amount, and creation timestamp.';
~~~

Views are commonly used to provide a data interface for reporting or application layers. Comments should clarify:

- Row selection criteria.
- Result semantics and granularity.
- Implicit filtering conditions inside the view.
- Underlying source tables.
- Intended business usage scope.

Never write "safe view for all accounts" merely because it selects a subset of columns. **Authorization** still depends on view/table privileges, ownership, and related security settings.

### 10.2. Materialized views hold stored data

Example creating a materialized view:

~~~sql
CREATE MATERIALIZED VIEW comment_lab.mv_daily_order_total AS
SELECT
    created_at::date AS order_date,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_amount
FROM comment_lab.orders
GROUP BY created_at::date;
~~~

Attach a description:

~~~sql
COMMENT ON MATERIALIZED VIEW comment_lab.mv_daily_order_total IS
    'Daily order aggregation based on created_at; results reflect the most recent refresh.';
~~~

Unlike regular views, materialized views persist data and must be refreshed via an appropriate mechanism:

~~~sql
REFRESH MATERIALIZED VIEW comment_lab.mv_daily_order_total;
~~~

In real systems, comments should also state **which job refreshes it, how often, and acceptable data staleness** if those details are actively managed.

### 10.3. Never describe a materialized view as real-time data

If a materialized view refreshes only once per night, its comment must avoid claiming data is "always up to date". BI users can make bad decisions if unaware of data latency.

## 11. COMMENT ON FUNCTION and PROCEDURE

Functions and procedures have not only names, but also **parameter signatures**. PostgreSQL supports multiple functions sharing a name with different argument types (*function overloading*).

Previously created:

~~~sql
CREATE FUNCTION comment_lab.line_amount(
    p_quantity INTEGER,
    p_unit_price NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
STRICT
AS $$
    SELECT p_quantity * p_unit_price;
$$;
~~~

Attach a comment:

~~~sql
COMMENT ON FUNCTION comment_lab.line_amount(INTEGER, NUMERIC) IS
    'Multiplies quantity by unit price; inputs exclude taxes and discounts; NULL returns NULL due to STRICT.';
~~~

Key points:

- Qualify the function name with its schema whenever possible.
- The parentheses contain the **parameter types identifying the function**.
- Never omit the signature arbitrarily when overloads exist.
- Comments should state **input/output contracts** and limits, rather than merely repeating "calculates line amount".

### 11.1. When multiple overloads exist

Suppose there are:

~~~text
comment_lab.calculate_fee(integer)
comment_lab.calculate_fee(numeric)
~~~

These are two distinct functions. Use the exact signature to attach comments accurately:

~~~sql
COMMENT ON FUNCTION comment_lab.calculate_fee(INTEGER)
IS 'Calculates fee from an integer value.';

COMMENT ON FUNCTION comment_lab.calculate_fee(NUMERIC)
IS 'Calculates fee from a decimal numeric value.';
~~~

These two statements are **syntax examples**; run them only if those functions actually exist. If no matching overload exists, PostgreSQL reports object not found.

### 11.2. Comments on stored procedures

Syntax example for an existing procedure:

~~~sql
COMMENT ON PROCEDURE comment_lab.close_order(BIGINT) IS
    'Confirms order completion by ID; must be invoked in a flow with business authorization checks.';
~~~

This example assumes procedure `close_order(BIGINT)` already exists. It is not runnable standalone in the current lab.

For procedures with write side effects, comments should describe:

- Parameters and preconditions.
- Affected tables or data categories.
- Possible business errors.
- Idempotency expectations if applicable.
- Allowed caller privileges or where authorization is enforced.

This guidance helps callers, yet **does not replace SQL authorization and business validation**.

## 12. Other comment types: triggers, policies, types, domains

### 12.1. Triggers

For a trigger named `trg_orders_audit` attached to `comment_lab.orders`, syntax is:

~~~sql
COMMENT ON TRIGGER trg_orders_audit
ON comment_lab.orders IS
    'Records order changes into the audit table after update operations.';
~~~

This applies only if the trigger already exists. Triggers can cause major side effects, so good comments state **timing, event, and purpose**.

### 12.2. Row-level security policies

If a table has a policy `orders_tenant_policy`, it can be documented:

~~~sql
COMMENT ON POLICY orders_tenant_policy
ON comment_lab.orders IS
    'Restricts row visibility per the application''s tenant-isolation policy.';
~~~

No such policy exists in the initial lab schema; this illustrates syntax. **Comments do not activate policies.** Enabling RLS requires creating/enabling policies and configuring appropriate privileges.

Specifically, a comment stating "readable only by current tenant" does not prove the system actually prevents cross-tenant leaks. Test with accounts and contexts carrying different privileges.

### 12.3. Domains

Domains can bundle a data type with reusable constraints:

~~~sql
CREATE DOMAIN comment_lab.nonnegative_amount
AS NUMERIC(14, 2)
CHECK (VALUE >= 0);

COMMENT ON DOMAIN comment_lab.nonnegative_amount IS
    'Non-negative decimal number used for monetary values in the practice schema.';
~~~

When multiple tables share this domain, the comment clarifies its uniform meaning. Still, a domain alone does not specify currency or tax rules.

### 12.4. Enum types

~~~sql
CREATE TYPE comment_lab.order_priority AS ENUM (
    'low',
    'normal',
    'high'
);

COMMENT ON TYPE comment_lab.order_priority IS
    'Order processing priority level: low, normal, or high.';
~~~

If the enum's value set changes, update its comment in the same migration workflow.

## 13. Who is allowed to create or modify comments?

`COMMENT` modifies object metadata, so users holding only `SELECT` privilege on data cannot automatically alter comments.

Under PostgreSQL rules, **the object owner** is typically permitted to modify comments, alongside authorized/special-privilege cases where applicable. Certain system or shared objects carry version-specific privilege conditions.

Example:

~~~sql
SELECT
    current_user,
    session_user,
    current_database();
~~~

In psql, check privileges and ownership:

~~~text
\dn+
\dt+ comment_lab.*
\du
~~~

If an account only has:

~~~sql
GRANT SELECT ON comment_lab.orders TO report_reader;
~~~

that `SELECT` grant does not grant permission to alter the table's comments.

### 13.1. Migration accounts typically own schemas

In many projects, the migration role creates and owns tables, indexes, views, and functions. Placing `COMMENT` statements inside the same migration keeps metadata synchronized with DDL.

If multiple developers create objects with different accounts, comment modification permissions can become inconsistent. This is another reason to govern ownership and DDL roles clearly.

### 13.2. COMMENT does not grant or restrict data read access

~~~sql
COMMENT ON TABLE comment_lab.orders IS
    'Order data for internal use.';
~~~

This statement **does not block** users who already hold `SELECT` from reading data. To restrict access, use privilege controls:

~~~sql
REVOKE SELECT ON comment_lab.orders FROM report_reader;
~~~

This illustrates the distinction; never run it casually in shared labs or production. Comments can describe data classification, while **actual access controls** must be configured, tested, and monitored separately.

## 14. Viewing comments in psql: \d+, \dd, and \df+

The fastest way to explore descriptions in the terminal is using **`psql`**.

### 14.1. \d+ for tables and columns

~~~text
\d+ comment_lab.orders
~~~

This describes the table with columns, data types, defaults, constraints/indexes, and additional details. Depending on `psql` version, column comments appear in the **Description** column and table comments appear in extended metadata.

Try:

~~~text
\d+ comment_lab.customers
\d+ comment_lab.v_paid_orders
\d+ comment_lab.mv_daily_order_total
~~~

Distinguish between:

- `\d`: basic object description.
- `\d+`: extended description, typically including comments where applicable.
- `\dd`: lists descriptions of matching objects.

These meta-commands are **handled client-side by `psql`**, not sent verbatim as SQL to the server. Never pass `\d+` over JDBC expecting PostgreSQL to understand it.

### 14.2. \dd lists objects with descriptions

~~~text
\dd comment_lab.*
~~~

This helps inventory comments `psql` can display by pattern and object type. Exact output and scope depend on `psql` version and privileges.

Some column-level or specific object descriptions may require `\d+` or querying `pg_catalog` to see completely. Never treat an empty `\dd` output as proof that no columns have comments.

### 14.3. \df+ for functions

~~~text
\df+ comment_lab.line_amount
~~~

`psql` displays descriptions, signatures, volatility/strictness properties, and other function details depending on version. For overloaded functions, inspect the exact parameter types.

### 14.4. \l+ and \dn+ for databases/schemas

~~~text
\l+
\dn+
~~~

These display extended database/schema details, including descriptions where applicable—handy for reviewing high-level annotations before drilling into individual tables.

## 15. Where are comments stored in PostgreSQL?

At the catalog level, PostgreSQL uses **`pg_catalog.pg_description`** to store descriptions for database-scoped objects and **`pg_catalog.pg_shdescription`** for certain cluster-wide shared objects.

Never manipulate these catalog tables directly to create comments. **Always use `COMMENT ON`**, rather than trying to `INSERT`/`UPDATE` `pg_description`.

### 15.1. What columns does pg_description contain?

Key columns:

| Column | Meaning |
|---|---|
| `objoid` | OID of the described object |
| `classoid` | OID of the system catalog managing that object kind |
| `objsubid` | Sub-object ID; typically 0 for the whole object, or attribute number for columns |
| `description` | Comment text |

Why are both `objoid` and `classoid` needed? Because the same numeric OID can exist across different catalog namespaces; uniquely identifying an object requires knowing its catalog.

### 15.2. Table comments and column comments differ by objsubid

At the relation level:

- Table comments use the relation's OID with `objsubid = 0`.
- Column comments link to the relation's OID and the column's **attribute number**.

Therefore, never grab an arbitrary row in `pg_description` and assume it describes the whole table without checking `objsubid`.

### 15.3. Never edit system catalogs manually

Right way:

~~~sql
COMMENT ON TABLE comment_lab.orders IS
    'Each row represents one order.';
~~~

Wrong way:

~~~sql
-- Do not do this:
-- UPDATE pg_catalog.pg_description
-- SET description = '...'
-- WHERE ...;
~~~

Catalogs are internal structures managed by PostgreSQL. Unauthorized direct edits can corrupt metadata or be rejected by the system. Official DDL exists so PostgreSQL updates metadata consistently.

## 16. Reading table comments with obj_description()

The `obj_description()` function retrieves an object's comment via its OID and catalog name.

Table example:

~~~sql
SELECT obj_description(
    'comment_lab.orders'::regclass,
    'pg_class'
) AS orders_description;
~~~

`'comment_lab.orders'::regclass` resolves the relation name to an OID using PostgreSQL syntax. `pg_class` is the catalog managing relations like tables, indexes, views, and sequences.

If the table exists and has a comment, the function returns the stored text. If no comment exists, it normally returns `NULL`.

### 16.1. Listing relation comments in a schema

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    c.relkind AS object_kind,
    obj_description(c.oid, 'pg_class') AS description
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'comment_lab'
  AND c.relkind IN ('r', 'p', 'v', 'm', 'i', 'I', 'S')
ORDER BY c.relkind, c.relname;
~~~

Common `relkind` codes:

| relkind | Relation kind |
|---|---|
| `r` | Ordinary table |
| `p` | Partitioned table |
| `v` | View |
| `m` | Materialized view |
| `i` | Index |
| `I` | Partitioned index |
| `S` | Sequence |

This list covers key types relevant to this lesson; PostgreSQL has additional relation kinds. Filtering by the target schema keeps reports concise and avoids scanning unrelated metadata.

### 16.2. Reading schema comments

Schemas live in `pg_namespace`, not `pg_class`:

~~~sql
SELECT
    n.nspname,
    obj_description(n.oid, 'pg_namespace') AS schema_description
FROM pg_catalog.pg_namespace AS n
WHERE n.nspname = 'comment_lab';
~~~

**The catalog argument must match the object kind.** Do not pass `pg_class` for everything; roles, functions, constraints, and schemas belong to separate catalogs.

## 17. Reading column comments with col_description()

For relation columns, use `col_description(relation_oid, attribute_number)`.

Example reading `orders` columns:

~~~sql
SELECT
    a.attnum AS ordinal_position,
    a.attname AS column_name,
    pg_catalog.format_type(a.atttypid, a.atttypmod) AS column_type,
    pg_catalog.col_description(c.oid, a.attnum) AS description
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
JOIN pg_catalog.pg_attribute AS a
    ON a.attrelid = c.oid
WHERE n.nspname = 'comment_lab'
  AND c.relname = 'orders'
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

Explanation of parts:

- `pg_class` identifies the relation.
- `pg_namespace` restricts to the right schema.
- `pg_attribute` describes attributes/columns.
- `a.attnum > 0` excludes system attributes in this query.
- `NOT a.attisdropped` excludes columns marked dropped at the catalog level.
- `col_description(c.oid, a.attnum)` returns the corresponding description.

### 17.1. Why use attnum instead of display order?

`attnum` is the attribute number managed by PostgreSQL. After adding and dropping columns, numbers may no longer be contiguous. Never count from 1 to the number of visible columns to guess `attnum`.

Always retrieve `a.attnum` from the catalog instead of guessing.

### 17.2. Summarizing all column comments in a schema

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    a.attname AS column_name,
    pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
    pg_catalog.col_description(c.oid, a.attnum) AS description
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
JOIN pg_catalog.pg_attribute AS a
    ON a.attrelid = c.oid
WHERE n.nspname = 'comment_lab'
  AND c.relkind IN ('r', 'p')
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY c.relname, a.attnum;
~~~

This SQL is handy for exporting documentation to internal reports or auditing metadata quality. On large databases, filter schemas and limit scope as needed.

## 18. Reading constraint comments via pg_constraint

Constraints are described in `pg_catalog.pg_constraint`.

~~~sql
SELECT
    n.nspname AS schema_name,
    t.relname AS table_name,
    con.conname AS constraint_name,
    con.contype AS constraint_kind,
    pg_catalog.pg_get_constraintdef(con.oid) AS constraint_definition,
    obj_description(con.oid, 'pg_constraint') AS description
FROM pg_catalog.pg_constraint AS con
JOIN pg_catalog.pg_class AS t
    ON t.oid = con.conrelid
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = t.relnamespace
WHERE n.nspname = 'comment_lab'
ORDER BY t.relname, con.conname;
~~~

In `pg_constraint.contype`, common codes include:

| contype | Meaning |
|---|---|
| `p` | Primary key |
| `u` | Unique |
| `f` | Foreign key |
| `c` | Check |
| `x` | Exclusion constraint |

Other constraints such as domain constraints are not represented by joining `conrelid` to tables as above. This query focuses on **table-attached constraints**.

### 18.1. Why do constraint comments matter during migrations?

Suppose a migration changes `CHECK (amount >= 0)` into a more complex rule. Updating the constraint while leaving the old comment intact leaves inaccurate documentation behind.

In a well-crafted migration, logic changes and comment updates are handled **together**. Explaining "why this rule exists" stops future maintainers from accidentally relaxing an invariant the application depends on.

## 19. Reading function comments from pg_proc

Functions and procedures are stored in `pg_proc`. Because functions can be overloaded, reports should identify full signatures.

~~~sql
SELECT
    n.nspname AS schema_name,
    p.proname AS routine_name,
    pg_catalog.pg_get_function_identity_arguments(p.oid) AS identity_args,
    obj_description(p.oid, 'pg_proc') AS description
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE n.nspname = 'comment_lab'
ORDER BY p.proname, identity_args;
~~~

`pg_get_function_identity_arguments()` formats the arguments needed to uniquely identify the routine—much better than printing only `proname` and conflating different overloads.

### 19.1. Reading a specific function via regprocedure

~~~sql
SELECT obj_description(
    'comment_lab.line_amount(integer, numeric)'::regprocedure,
    'pg_proc'
) AS function_description;
~~~

`regprocedure` resolves by **signature**. If no matching object exists, PostgreSQL raises an error instead of picking a close match.

### 19.2. Function comments are not engine-verified API contracts

If a comment says "returns amount rounded to 2 decimal places" while the function body omits `ROUND(...,2)`, PostgreSQL executes the function body as defined. Comments do not stay in sync with code automatically.

To preserve accuracy, pair behavioral tests, migrations, and metadata reviews whenever modifying functionality.

## 20. Comments on shared objects: pg_shdescription

Not every PostgreSQL object belongs to a single database. Objects such as **databases**, **roles**, and **tablespaces** are cluster-wide.

Descriptions of shared objects live in **`pg_shdescription`** rather than `pg_description`.

Example when the account has appropriate privileges and database `training_db` exists:

~~~sql
COMMENT ON DATABASE training_db IS
    'PostgreSQL training database; contains no real customer data.';
~~~

Read via function:

~~~sql
SELECT
    d.datname,
    pg_catalog.shobj_description(d.oid, 'pg_database') AS description
FROM pg_catalog.pg_database AS d
WHERE d.datname = 'training_db';
~~~

**Run the COMMENT statement only if that database actually exists and you have appropriate privileges.** If your environment uses another database name, adjust accordingly.

### 20.1. Why not use obj_description for every object?

`obj_description()` and `pg_description` serve objects in database-scoped catalogs. For shared cluster objects, `shobj_description()` and `pg_shdescription` are the corresponding mechanism.

That is why a documentation report covering "all objects on the server" must distinguish **database-level objects** from **cluster-level shared objects**, rather than querying only a single catalog table.

## 21. Detecting undocumented tables and columns

One benefit of storing comments in metadata is generating documentation-coverage reports.

### 21.1. Finding tables without comments

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'comment_lab'
  AND c.relkind IN ('r', 'p')
  AND obj_description(c.oid, 'pg_class') IS NULL
ORDER BY c.relname;
~~~

This SQL detects only **NULL** comments. If your team also treats empty or whitespace-only strings as missing, add:

~~~sql
AND NULLIF(
    btrim(obj_description(c.oid, 'pg_class')),
    ''
) IS NULL
~~~

Keep reporting criteria realistic: technical, staging, or temporary tables do not all need the same level of documentation.

### 21.2. Finding columns without comments

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    a.attname AS column_name,
    pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
JOIN pg_catalog.pg_attribute AS a
    ON a.attrelid = c.oid
WHERE n.nspname = 'comment_lab'
  AND c.relkind IN ('r', 'p')
  AND a.attnum > 0
  AND NOT a.attisdropped
  AND NULLIF(
      btrim(pg_catalog.col_description(c.oid, a.attnum)),
      ''
  ) IS NULL
ORDER BY c.relname, a.attnum;
~~~

This is an **audit report**, not an automated comment generator. Auto-filling descriptions like "The customer_id column" on every column solely to hit 100% coverage yields complete-looking metadata with almost zero practical value.

### 21.3. Coverage and quality are two different things

Example:

~~~sql
COMMENT ON COLUMN comment_lab.orders.total_amount IS
    'Amount.';
~~~

A comment exists, yet answers none of the real questions: taxes, fees, currency, timing, and rounding rules.

A metric like "95% of columns have comments" helps track **coverage**, yet does not prove documentation is accurate or useful. Maintain content quality just as carefully as the rest of the data model.

## 22. Documenting via migrations and version control

A comment typed manually on production is easily lost when schemas are rebuilt, or drifts out of sync across development, staging, and production.

The durable approach is placing `COMMENT ON` statements inside **version-controlled migrations** alongside related DDL.

Example migration:

~~~sql
BEGIN;

ALTER TABLE comment_lab.orders
ADD COLUMN payment_reference TEXT;

COMMENT ON COLUMN comment_lab.orders.payment_reference IS
    'Payment reference code supplied by the payment gateway; may be NULL prior to payment.';

COMMENT ON TABLE comment_lab.orders IS
    'Each row represents one order; can link to payment transactions via payment_reference.';

COMMIT;
~~~

In PostgreSQL, many DDL operations and `COMMENT` statements can participate in transactions, letting schema and metadata changes commit or roll back together per PostgreSQL rules.

Keep in mind:

- Not **every** DDL statement can run inside a transaction block.
- Adding columns or altering constraints can acquire locks and affect runtime traffic.
- Running migrations requires appropriate privileges and rollback plans.
- If a new column has transitional semantics while legacy data is backfilled, comments should reflect the transition phase as well.

### 22.1. Renaming columns and comments

When renaming a column via `ALTER TABLE ... RENAME COLUMN`, object metadata generally stays attached via PostgreSQL's internal identifiers. However, **the comment text itself** may still refer to the old name or old meaning.

For example, a comment might mention "references customer code via customer_code" even after the design switched to a new key. Metadata surviving a rename does not mean its semantics were updated.

Therefore, every significant migration should review **structure**, **dependent queries**, and **related comments** together.

### 22.2. Dropped objects

When an object is genuinely dropped, its attached comment ceases to exist as active metadata for that object. If a migration drops and recreates an object, ensure `COMMENT ON` statements are reapplied to the new definition.

### 22.3. Rerunning migrations

`COMMENT ON` on an existing object normally **replaces the description**, so applying identical content yields the same description. Still, it requires the object to exist and the executor to hold privileges.

A migration should never be assumed completely idempotent merely because `COMMENT` statements are repeatable; accompanying `CREATE TABLE`, `ALTER TABLE`, and data updates still need separate management.

## 23. Exporting schemas with pg_dump

During logical backups or schema deployments, **`pg_dump`** can export both object definitions and comments.

Shell example, given connection privileges:

~~~bash
pg_dump --schema-only --dbname=appdb --schema=comment_lab
~~~

This is a **shell command** invoking `pg_dump`, not SQL sent directly over JDBC. `appdb` is an example name; substitute your environment's actual database.

Inside the dump output, comments appear as statements like:

~~~sql
COMMENT ON TABLE comment_lab.orders IS
    'Each row represents one order.';
~~~

### 23.1. Not every export method preserves comments

If an export tool runs with comment-skipping options like `--no-comments`, or a pipeline reconstructs tables solely from `information_schema.columns`, comments will be omitted.

Therefore:

- Inspect export and restore flags.
- Check whether comments are captured in migration/schema artifacts.
- Test restoring in an appropriate environment.
- Never assume "since comments are in the database, every dump definitely keeps them".

### 23.2. Dumps do not validate description accuracy

`pg_dump` preserves whatever comments currently exist, including outdated ones. Backup/restore handles **metadata copying**, not business accuracy verification.

## 24. Differences between INFORMATION_SCHEMA and PostgreSQL catalogs

PostgreSQL provides both **`information_schema`** and **`pg_catalog`**.

`information_schema.columns` exposes fields such as:

~~~sql
SELECT
    table_schema,
    table_name,
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'comment_lab'
ORDER BY table_name, ordinal_position;
~~~

However, `COMMENT` descriptions **are not a standard column in PostgreSQL's `information_schema.columns`**. To retrieve comments, use `col_description()` or query system catalogs as shown above.

### 24.1. When to use which source?

| Goal | Appropriate source |
|---|---|
| Quickly inspect a table's descriptions in terminal | `psql \d+ schema.table` |
| View function descriptions | `psql \df+` or catalog/functions |
| Retrieve a table comment | `obj_description(..., 'pg_class')` |
| Retrieve a column comment | `col_description(..., attnum)` |
| Retrieve a constraint comment | `obj_description(..., 'pg_constraint')` |
| Retrieve routine comments | `pg_proc` and `obj_description` |
| Retrieve shared object comments | `shobj_description` |
| Inventory columns via standard SQL interface | `information_schema.columns` |
| Export DDL and descriptions | `pg_dump` with appropriate options |
| Track comment change history | Migrations/audit/version control |

JDBC drivers also provide metadata APIs, yet whether descriptions populate fields like `REMARKS` depends on driver, version, and configuration. Never assume every JDBC tool automatically displays comments.

## 25. Security: comments are not a place for secrets

Comments are generally **metadata readable by authorized database users**. Never treat comments as private storage accessible only to the object owner.

Strictly avoid recording:

- Database passwords, tokens, or API keys.
- Connection strings containing secrets.
- Internal authentication credentials.
- Sensitive personal values of specific customers.
- Dynamic SQL containing unnecessary real data.
- Detailed descriptions of security flaws or privilege-bypass paths.

What not to do:

~~~sql
-- Do not do this:
-- COMMENT ON TABLE comment_lab.customers IS
-- 'Admin password = ...';
~~~

Instead, comments can note **classification and handling requirements**:

~~~sql
COMMENT ON COLUMN comment_lab.customers.email IS
    'Personal contact info; use strictly per the system''s data protection policy.';
~~~

This description guides data users, while email access must still be **enforced and verified** using PostgreSQL roles/privileges, RLS where appropriate, and application policies.

### 25.1. Comments are not an authorization layer

A column commented "accounting department only" does not make PostgreSQL restrict `SELECT`.

Proper controls include:

- Restricting table/column/view privileges.
- Applying RLS policies where architecture requires and supports them.
- Using functional roles.
- Logging/auditing access as needed.
- Protecting data when exporting to BI or inventory tools.

**Documenting a policy** and **enforcing a policy** are two separate responsibilities.

## 26. Conventions for writing high-quality comments

A useful comment answers **what the name and data type do not already convey**.

### 26.1. Weak vs. better examples

| Object | Weak comment | More useful comment |
|---|---|---|
| `customers` | "Customers table" | "One row = one customer; customer_code is the business identifier" |
| `orders.total_amount` | "Amount" | "Order total at confirmation time; currency and calculation follow business contract" |
| `orders.created_at` | "Created date" | "Record creation timestamp stored as TIMESTAMPTZ; not payment time" |
| `orders.order_status` | "Status" | "pending/paid/cancelled; CHECK enforces allowed values, transitions handled in service" |
| `idx_orders_created_at` | "Index" | "Supports listing newest orders ordered by created_at" |
| `v_paid_orders` | "Paid orders" | "View filtering status=paid; excludes pending/cancelled" |
| `line_amount` | "Calculate amount" | "Product of quantity and unit price; excludes tax and discounts" |

Adapt examples to **actual system behavior**. A description saying "at confirmation time" is accurate only if the column is truly frozen at that point.

### 26.2. A concise template

For tables:

~~~text
Purpose:
Row grain:
Write source / business owner:
Related objects:
Usage notes:
~~~

For columns:

~~~text
Meaning:
Unit / time semantics:
NULL / special values:
Source or formula:
Privilege / data quality notes:
~~~

For views/reports:

~~~text
Purpose:
Filter criteria:
Output granularity:
Sources:
Data latency (if any):
~~~

You do not need every line when a single clear sentence suffices. Comments are **quick-reference metadata**, not a place to duplicate entire process manuals.

### 26.3. Language and terminology

In multinational projects, agree on a consistent comment language. PostgreSQL stores Unicode text matching the database encoding, so Vietnamese or any language works—what matters is that system users understand it consistently.

Standardize terms such as:

- "Order" vs. "payment transaction".
- "Creation timestamp" vs. "business date".
- "Revenue" vs. "cash collected".
- "Current price" vs. "price at order placement".

Consistent terminology reduces misinterpretation in reports and migrations.

## 27. Identifier safety when generating COMMENT statements dynamically

When automating comments across many objects, an application may need to generate `COMMENT ON` statements from a list of schemas, tables, and columns.

Never concatenate unvalidated object names or user-supplied description strings directly into SQL:

~~~text
"COMMENT ON TABLE " + tableName + " IS '" + description + "'"
~~~

This breaks on uppercase/spaced identifiers or quotes in text, and worse, introduces **SQL injection** if inputs are untrusted.

### 27.1. Identifiers and string literals are different constructs

- Schema, table, and column names are **SQL identifiers**.
- The description after `IS` is a **SQL string literal** or `NULL`.

Inside a PL/pgSQL function with controlled privileges and inputs, you can use `format()` such as:

~~~sql
-- Illustrative template for generating statements from validated values.
SELECT format(
    'COMMENT ON TABLE %I.%I IS %L',
    'comment_lab',
    'orders',
    'Orders following the sales workflow.'
);
~~~

Here:

- `%I` quotes identifiers.
- `%L` quotes values as SQL literals.

The statement above **only returns a text string**; it does not execute `COMMENT`. If executing dynamic SQL in an app or procedure, still apply allowlists, privilege checks, and limits on modifiable objects.

### 27.2. Avoid unqualified names

When two `orders` tables exist in two schemas, running:

~~~sql
COMMENT ON TABLE orders IS '...';
~~~

depends on the session's `search_path`. In migrations, write explicitly:

~~~sql
COMMENT ON TABLE comment_lab.orders IS '...';
~~~

This prevents updating the wrong object when `search_path` differs across environments.

## 28. Operational impact and transactions

`COMMENT ON` is a metadata DDL operation. It does not scan entire tables to "attach comments to every row", yet it still participates in PostgreSQL's locking, catalog updates, and transactions.

Never assume "it's only metadata so it can never block queries" across all object types, workloads, and versions. Schedule concurrent DDL changes under appropriate rollout policies.

### 28.1. COMMENT can roll back

In a test database:

~~~sql
BEGIN;

COMMENT ON TABLE comment_lab.orders IS
    'Test description inside a transaction.';

SELECT obj_description(
    'comment_lab.orders'::regclass,
    'pg_class'
);

ROLLBACK;
~~~

After `ROLLBACK`, the pre-transaction comment is preserved provided no other committed change altered it.

This shows comments can live inside transactional migration workflows. It does not mean every PostgreSQL DDL command is identically transaction-safe; certain administrative commands have their own restrictions.

### 28.2. Updating comments does not alter business queries

Given:

~~~sql
SELECT order_id, total_amount
FROM comment_lab.orders;
~~~

Changing the comment on `total_amount` does not alter column values, data types, query filters, or privileges. **The impact is primarily on metadata read by humans and tooling.**

However, tools that auto-generate docs or code from metadata may reflect updated comments, so treat comment edits as version-controlled changes.

## 29. Documentation at scale: ownership and maintenance responsibility

When multiple teams share PostgreSQL, comments grow stale quickly without clear ownership.

An effective workflow:

1. **Define which objects require comments:** core business tables, ambiguous columns, reporting views, public functions.
2. **Assign business owners:** teams responsible for data semantics.
3. **Place comments in migrations:** avoid untracked manual edits.
4. **Run coverage reports:** identify tables and columns missing comments.
5. **Verify accuracy during logic changes:** type updates, enums, currencies, time zones, state transitions.
6. **Verify export/restore behavior:** ensure comments survive across environments.
7. **Keep secrets out of metadata:** users with catalog read access must never discover secrets.
8. **Maintain external long-form docs:** API designs, state machines, and ownership often belong outside the database.

### 29.1. Comments and data catalogs

Organizations may run a data catalog, BI metadata layer, or lineage platform. PostgreSQL comments serve as **the closest-to-object descriptions**, feeding or syncing into broader catalogs.

Still, comments alone do not prove:

- Data quality is good.
- Tables refresh on schedule.
- End-to-end lineage across all services is complete.
- Users are authorized to view the data.
- Reports implement approved KPI logic.

Those assurances require separate tooling and governance.

### 29.2. Comment schema drift

Development may hold one description while production retains an older one. Diffing only column types and indexes misses **documentation metadata drift**.

You can export comment lists from catalogs in two environments, normalize by stable keys such as:

~~~text
(schema, relation, object_kind)
(schema, table, column)
(schema, table, constraint_name)
(schema, routine_name, argument_types)
~~~

and compare them. **Never use OIDs as stable cross-database keys**, as OIDs differ when objects are recreated.

## 30. Practice exercises

### Exercise 1 — Describing the right row grain

An `order_items` table stores multiple lines per order. Write a comment stating that **each row is one product line inside an order**, not an entire order.

**Hint:**

~~~sql
COMMENT ON TABLE comment_lab.order_items IS
    'Each row is one product and quantity line within an order.';
~~~

Run this only if `comment_lab.order_items` has already been created.

### Exercise 2 — Describing a status column

Write a comment on `comment_lab.orders.order_status` showing its three valid values. Why can't that comment replace `CHECK`?

**Hint:**

~~~sql
COMMENT ON COLUMN comment_lab.orders.order_status IS
    'Order status: pending, paid, cancelled.';
~~~

Because comments do not enforce rules; constraints validate data on writes per PostgreSQL semantics.

### Exercise 3 — Updating description without changing structure

Update the description of `comment_lab.customers` to explain that `customer_code` is the business key, without altering the schema.

**Hint:** Use `COMMENT ON TABLE`; no `ALTER TABLE` is needed.

### Exercise 4 — Removing a comment

Write a statement to remove the description of the `email` column without dropping the column.

**Suggested answer:**

~~~sql
COMMENT ON COLUMN comment_lab.customers.email IS NULL;
~~~

### Exercise 5 — Commenting on a foreign key constraint

Write a comment for `fk_orders_customers` explaining that an order must point to an existing customer.

**Suggested answer:**

~~~sql
COMMENT ON CONSTRAINT fk_orders_customers
ON comment_lab.orders IS
    'Prevents orders from referencing non-existent customers.';
~~~

### Exercise 6 — Overloaded functions

Two functions exist: `compute_fee(integer)` and `compute_fee(numeric)`. Why must comments include the exact parameter signature?

**Hint:** PostgreSQL allows same-named functions with different parameter types, so a bare name would be ambiguous or fail to identify the routine.

### Exercise 7 — Reading a table comment

Write SQL returning the comment on `comment_lab.orders` using `obj_description()`.

**Suggested answer:**

~~~sql
SELECT obj_description(
    'comment_lab.orders'::regclass,
    'pg_class'
);
~~~

### Exercise 8 — Reading column comments

You need the column names and comments of `comment_lab.customers`. Why shouldn't you number columns 1..N manually when calling `col_description()`?

**Hint:** PostgreSQL `attnum` values can have gaps after dropping columns; read from `pg_attribute` with `attnum > 0 AND NOT attisdropped`.

### Exercise 9 — Finding undocumented objects

Write a query listing ordinary tables in `comment_lab` that lack a table comment.

**Hint:** Join `pg_class` and `pg_namespace`, filter `relkind IN ('r','p')`, and check `obj_description(..., 'pg_class') IS NULL`.

### Exercise 10 — Comments and security

A developer wants to put a service password in a comment for easy lookup in `psql`. Should they do this?

**Hint:** No. Comments are metadata readable by users with catalog access; secrets belong in a proper secrets management system.

### Exercise 11 — Materialized views

A materialized view refreshes nightly. Which comment is more critical: "aggregated view" or "data updates only once nightly"?

**Hint:** Include both purpose and **data latency**, since readers might otherwise mistake reports for real-time data.

### Exercise 12 — Migrations changing data semantics

A `total_amount` column changes meaning from "pre-tax price" to "post-tax price". Besides DDL and code, what must happen to comments?

**Hint:** Update the comment in the same migration, check related reports and docs, and avoid leaving stale descriptions behind.

### Exercise 13 — Comments and psql

In the `psql` terminal, which commands display detailed descriptions of tables and functions?

**Hint:**

~~~text
\d+ comment_lab.orders
\df+ comment_lab.line_amount
~~~

### Exercise 14 — Shared objects

Why can a database's description live in `pg_shdescription` instead of `pg_description`?

**Hint:** Databases are cluster-level objects; PostgreSQL manages shared metadata via a separate catalog.

### Exercise 15 — Automation

A script reads schema, table, and comment text from a config file. Why shouldn't it concatenate strings directly to build SQL?

**Hint:** Identifiers may need quoting, descriptions may contain quotes, and untrusted input opens SQL injection risks. Use allowlists and proper identifier/literal quoting.

## 31. Quick reference table

| Task | Syntax / source |
|---|---|
| Document a schema | `COMMENT ON SCHEMA s IS '...';` |
| Document a table | `COMMENT ON TABLE s.t IS '...';` |
| Document a column | `COMMENT ON COLUMN s.t.c IS '...';` |
| Document a view | `COMMENT ON VIEW s.v IS '...';` |
| Document a materialized view | `COMMENT ON MATERIALIZED VIEW s.mv IS '...';` |
| Document an index | `COMMENT ON INDEX s.idx IS '...';` |
| Document a constraint | `COMMENT ON CONSTRAINT c ON s.t IS '...';` |
| Document a function | `COMMENT ON FUNCTION s.f(types) IS '...';` |
| Document a procedure | `COMMENT ON PROCEDURE s.p(types) IS '...';` |
| Document a trigger | `COMMENT ON TRIGGER tr ON s.t IS '...';` |
| Document a domain | `COMMENT ON DOMAIN s.domain IS '...';` |
| Document a type | `COMMENT ON TYPE s.type IS '...';` |
| Replace a comment | Run a new `COMMENT ON` on the same object |
| Remove a comment | `COMMENT ON ... IS NULL;` |
| Check version-specific COMMENT syntax | `psql: \h COMMENT` |
| View table and column comments | `psql: \d+ schema.table` |
| View function comments | `psql: \df+ schema.function` |
| List descriptions | `psql: \dd schema.*` |
| Read table comment via SQL | `obj_description(oid,'pg_class')` |
| Read column comment via SQL | `col_description(table_oid,attnum)` |
| Read constraint comment | `obj_description(oid,'pg_constraint')` |
| Read function comment | `obj_description(oid,'pg_proc')` |
| Read database comment | `shobj_description(oid,'pg_database')` |
| Export schema and comments | `pg_dump --schema-only` with appropriate options |
| Track comment history | Migrations/version control |
| Enforce privileges or business rules | GRANT/REVOKE, constraints, RLS, and proper logic — **not comments** |

---

## Conclusion

**`COMMENT ON` is PostgreSQL's built-in tool for documenting objects inside the database.** It captures the purpose of schemas and tables, column meanings, constraint and index rationales, view/function contracts, and caveats on aggregated data. These descriptions can be browsed quickly in `psql`, queried via `pg_catalog` functions, or exported alongside schemas for migration management.

To make documentation reliable, prioritize **real business semantics**, attach descriptions to the right objects, track comment edits alongside DDL, and keep secrets out of metadata. Comments do not validate data, replace authorization, or auto-update when application logic changes. When maintained as a first-class part of the schema, they help developers, analysts, and operators understand PostgreSQL faster and make fewer mistakes when querying or evolving data structures.
