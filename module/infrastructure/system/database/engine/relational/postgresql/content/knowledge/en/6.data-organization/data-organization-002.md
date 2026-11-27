# Schemas as namespaces and object organization boundaries in PostgreSQL

When a PostgreSQL database contains many tables, views, functions, and data types, placing everything into a single namespace easily causes naming collisions and makes access permissions difficult to manage. PostgreSQL uses **schemas** to group and name objects inside **a single database**. Each schema is a **namespace**: two schemas can both have a table named `customers` while still being distinguished through fully qualified names such as `sales.customers` and `reporting.customers`.

A schema also acts as an **organizational and authorization boundary**: you can specify which group may create objects, which group may use existing objects, and which application should operate through which schema. However, a schema is **not a separate database**, nor does it automatically create physical isolation, resource isolation, or absolute security.

This lesson demonstrates how to create and use multiple schemas, understand `search_path`, assign permissions at the right layer, organize migrations, and avoid common pitfalls when an application or multiple teams work together in PostgreSQL.

## 1. Where do schemas sit in the PostgreSQL architecture?

You can visualize the hierarchy:

~~~mermaid
flowchart TD
    C["PostgreSQL cluster / instance"] --> D1["Database: commerce"]
    C --> D2["Database: analytics"]
    D1 --> S1["Schema: sales"]
    D1 --> S2["Schema: reporting"]
    D1 --> S3["Schema: audit"]
    S1 --> T1["Table: customers"]
    S1 --> T2["Table: orders"]
    S2 --> T3["View: paid_revenue"]
    S3 --> T4["Table: change_events"]
~~~

A **database** is the collection of data objects that each PostgreSQL connection selects upon login. Inside that database live multiple **schemas**. Each schema contains objects such as:

- Tables (`TABLE`), partitioned tables, and foreign tables.
- Views and materialized views.
- Sequences.
- Functions, procedures, operators, and aggregates.
- Types, domains, and other objects.

A schema is not a copy of a database. Creating a new schema does **not** create an additional database, does not spin up a separate PostgreSQL server, and does not allow connecting to another database via schema names.

### Comparing databases and schemas

| Criterion | Database | Schema |
| --- | --- | --- |
| Scope | Belongs to a PostgreSQL cluster | Belongs to exactly one database |
| Example | `commerce`, `analytics` | `sales`, `reporting` |
| How clients select | When opening a connection, e.g., `-d commerce` | Via qualified names or `search_path` within the connection |
| Objects | Contains schemas and database-level objects | Contains tables, views, functions, data types, etc. |
| Namespace | Databases have distinct names within the cluster | Distinct schema names within the database |
| Querying in one SQL statement | Cannot directly access another database's tables with standard syntax | Can `JOIN` tables across multiple schemas in the same database |
| Permissions | Has `CONNECT`, `CREATE`, `TEMPORARY` privileges at the database level | Has `USAGE`, `CREATE` privileges at the schema level |
| Data isolation | Has separate database boundaries and connections | Logical boundary; does not provide complete isolation |

For example, PostgreSQL does not support three-part table names like `database.schema.table` to arbitrarily access another database in standard SQL queries. When cross-database data is needed, an explicit mechanism such as `postgres_fdw`, `dblink`, or a data sync pipeline is required; this is outside the scope of using schemas.

## 2. Fully qualified object names: schema.table

Suppose there are two tables:

~~~sql
CREATE SCHEMA sales;
CREATE SCHEMA reporting;

CREATE TABLE sales.customers (
    customer_id bigint PRIMARY KEY,
    customer_name text NOT NULL
);

CREATE TABLE reporting.customers (
    customer_id bigint PRIMARY KEY,
    display_label text NOT NULL
);
~~~

Both `CREATE TABLE` statements use the name `customers` without colliding, because they belong to different schemas.

When querying with a **qualified name** (schema-prefixed name):

~~~sql
SELECT customer_id, customer_name
FROM sales.customers;

SELECT customer_id, display_label
FROM reporting.customers;
~~~

PostgreSQL knows precisely which table is requested. In applications, writing qualified names like `sales.customers` is useful for critical SQL statements, migrations, multi-schema reports, or administrative tools.

### Other objects also live in schemas

For example:

~~~sql
CREATE SEQUENCE sales.invoice_number_seq START WITH 1000;

CREATE VIEW reporting.customer_names AS
SELECT customer_id, customer_name
FROM sales.customers;
~~~

The names `sales.invoice_number_seq` and `reporting.customer_names` also use namespaces. For overloaded functions, PostgreSQL additionally considers **function name plus parameter types**, so you should not look solely at the text name and assume no conflict exists.

### Cannot create two tables with the same name in the same schema

~~~sql
-- Table sales.customers already exists so this statement will fail.
CREATE TABLE sales.customers (
    id integer PRIMARY KEY
);
~~~

The exact error message depends on the version and existing object, but fundamentally **a namespace does not allow two conflicting relations with the same name in the same schema**. If you genuinely need two tables with different roles, choose a different name or a different schema depending on business boundaries.

## 3. Role of the public schema

When creating a standard PostgreSQL database, a schema named `public` is present. If a user runs:

~~~sql
CREATE TABLE tasks (
    task_id bigint PRIMARY KEY,
    task_name text NOT NULL
);
~~~

without specifying a schema, the table may be created in `public.tasks` depending on the session's `search_path` and the role's privileges. However, **never assume every schema-less CREATE statement always goes into `public`**: that depends on `search_path` and `CREATE` privileges.

Several distinctions to keep clear:

- `public` (lowercase) is a commonly pre-existing **schema name**.
- `PUBLIC` (uppercase in `GRANT ... TO PUBLIC`) is a **pseudo-role representing all roles**.
- The `public` schema does not mean "everyone can always create and read every object".

In PostgreSQL 15 and later, new databases have different default permissions on the `public` schema compared to many older versions: by default, all roles are typically not allowed to arbitrarily create objects there. Databases upgraded from older versions or custom-configured may still retain broader permissions. **Always verify actual permissions**, rather than guessing solely from version.

You may choose to use `public` for small experiments, but when building multi-module or multi-team applications, creating meaningfully named schemas such as `sales`, `billing`, and `audit` makes object management much clearer.

## 4. search_path: how PostgreSQL resolves unqualified names

When writing:

~~~sql
SELECT *
FROM customers;
~~~

PostgreSQL must determine which schema `customers` belongs to. This mechanism relies on **`search_path`**, the list of namespaces the query session inspects when looking up an unqualified name.

Check the configuration:

~~~sql
SHOW search_path;

SELECT
    current_schema() AS creation_schema,
    current_schemas(true) AS effective_search_schemas;
~~~

The default value typically looks like:

~~~text
"$user", public
~~~

`"$user"` is a placeholder for a schema sharing the same name as the current role if that schema exists and the user has appropriate privileges. If no such schema exists, PostgreSQL skips it when looking up objects. `public` is the next schema in the common default list.

### How search_path handles two tables with the same name

Suppose both `sales.customers` and `reporting.customers` exist:

~~~sql
SET search_path TO reporting, sales;

SELECT *
FROM customers;
~~~

The name `customers` in this example resolves to `reporting.customers` because `reporting` precedes `sales` and contains a matching table.

Swap the order:

~~~sql
SET search_path TO sales, reporting;

SELECT *
FROM customers;
~~~

The exact same `SELECT * FROM customers` statement now targets `sales.customers`. This is a way of **changing the meaning of SQL without modifying the query text**.

When you want certainty, use the qualified name:

~~~sql
SELECT *
FROM sales.customers;
~~~

This statement does not depend on the order of `sales` and `reporting` in `search_path`, provided the role has appropriate privileges on the schema and table.

### How schemas are chosen when creating objects

In a schema-less `CREATE TABLE customers (...)` statement, PostgreSQL normally uses **the first valid schema in the search path** as the creation target. You can observe this with `current_schema()`.

If the first selected schema does not grant the role `CREATE` privilege, the statement can fail with a permission error; PostgreSQL does not automatically fall back to another schema where you do have permission just because you might expect it. For migrations, use qualified names or configure `search_path` deliberately instead of relying on defaults.

### Restoring search_path after experiments

~~~sql
RESET search_path;
~~~

`RESET` returns the value to the session's inherited setting, **which is not necessarily the default string of every PostgreSQL installation**, because the role or database may have configured its own value.

## 5. Distinguishing SET, SET LOCAL, and persistent configuration

There are several ways to change `search_path`:

~~~sql
-- Applies within the current session.
SET search_path TO sales, reporting;

-- Inspect the current value.
SHOW search_path;

-- Return to the session's inherited setting.
RESET search_path;
~~~

When it only needs to apply within a single transaction:

~~~sql
BEGIN;

SET LOCAL search_path TO sales, pg_catalog;

-- SQL statements in this transaction use the search_path above.
SELECT * FROM customers;

COMMIT;
~~~

`SET LOCAL` takes effect only for the current transaction; after the transaction ends, the previous session setting returns. This is an option when isolating configuration for a unit of work, though **it must not be relied upon to persist schema context for a subsequent transaction in a connection pool**.

Administrators can also set defaults for a role or database:

~~~sql
-- Syntax illustration; requires appropriate administrative privileges.
ALTER ROLE app_reader SET search_path = sales, public;
ALTER DATABASE commerce SET search_path = sales, public;
~~~

These statements are illustrative only; `app_reader` and `commerce` must actually exist. Default settings typically apply to **new connections**, without automatically changing already-open sessions.

### What else does search_path affect?

Beyond tables, PostgreSQL uses schema resolution for many object types such as views, sequences, functions, types, and operators. Relying on `search_path` makes SQL shorter, but also increases the risk of name collisions or routing to unintended objects.

Notably, `pg_catalog` contains many system objects and is typically searched automatically even if omitted from `search_path`. The session's temporary schema also has special precedence rules for relation and type names. Thus, resolution outcomes are not simply "search only the exact two user-listed schemas" in every situation.

## 6. Hands-on lab with three schemas: sales, reporting, audit

Create an **isolated lab database** (for example `schema_lab`), then connect to it. The following statements are run once when no schemas with these names exist in the lab:

~~~sql
CREATE SCHEMA lab_sales;
CREATE SCHEMA lab_reporting;
CREATE SCHEMA lab_audit;
~~~

The three namespaces have distinct responsibilities:

| Schema | Purpose |
| --- | --- |
| `lab_sales` | Core transactional data: customers, orders |
| `lab_reporting` | Views or materialized views for reporting |
| `lab_audit` | Event/audit logging tables for the lab |

### Creating transactional tables

~~~sql
CREATE TABLE lab_sales.customers (
    customer_id integer PRIMARY KEY,
    customer_name text NOT NULL,
    city text NOT NULL
);

CREATE TABLE lab_sales.orders (
    order_id integer PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES lab_sales.customers(customer_id),
    status text NOT NULL
        CHECK (status IN ('paid', 'pending', 'cancelled')),
    total numeric(12, 2) NOT NULL
        CHECK (total >= 0)
);

INSERT INTO lab_sales.customers
    (customer_id, customer_name, city)
VALUES
    (1, 'An', 'HCM'),
    (2, 'Binh', 'HAN'),
    (3, 'Chi', 'HCM');

INSERT INTO lab_sales.orders
    (order_id, customer_id, status, total)
VALUES
    (101, 1, 'paid', 100.00),
    (102, 1, 'paid', 250.00),
    (103, 2, 'pending', 300.00),
    (104, 3, 'paid', 120.00);
~~~

These tables belong to `lab_sales`, even though they have foreign key relationships and participate together in JOIN queries.

### Placing a reporting view in another schema

~~~sql
CREATE VIEW lab_reporting.paid_revenue AS
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_order_count,
    COALESCE(SUM(o.total), 0)::numeric(12, 2) AS revenue
FROM lab_sales.customers AS c
LEFT JOIN lab_sales.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'paid'
GROUP BY c.customer_id, c.customer_name;
~~~

Query:

~~~sql
SELECT *
FROM lab_reporting.paid_revenue
ORDER BY customer_id;
~~~

Expected result:

| customer_id | customer_name | paid_order_count | revenue |
| ---: | --- | ---: | ---: |
| 1 | An | 2 | 350.00 |
| 2 | Binh | 0 | 0.00 |
| 3 | Chi | 1 | 120.00 |

The view resides in `lab_reporting`, while the base tables live in `lab_sales`. PostgreSQL allows **cross-schema querying and linking within the same database**, provided permission constraints and execution conditions are met.

In the example, the status condition is placed in `ON` to preserve customers who have no `paid` orders. `COUNT(o.order_id)` does not count `NULL` rows produced by the `LEFT JOIN`.

### Using the audit schema for objects with separate responsibility

~~~sql
CREATE TABLE lab_audit.events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_name text NOT NULL,
    entity_id integer NOT NULL,
    event_type text NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now()
);
~~~

The audit table is organized in another schema, though **a schema does not automatically write audit events**. The application, triggers, or a dedicated process must generate records per the audit policy. Placing the table in `lab_audit` helps clarify its purpose and simplifies permission management.

## 7. Two schemas can share a table name without conflict

Create a same-named table in `lab_reporting` to demonstrate namespaces:

~~~sql
CREATE TABLE lab_reporting.customers (
    customer_id integer PRIMARY KEY,
    display_label text NOT NULL
);

INSERT INTO lab_reporting.customers
    (customer_id, display_label)
VALUES
    (1, 'Customer Group A'),
    (2, 'Customer Group B');
~~~

Query with explicit schemas:

~~~sql
SELECT customer_id, customer_name
FROM lab_sales.customers
ORDER BY customer_id;

SELECT customer_id, display_label
FROM lab_reporting.customers
ORDER BY customer_id;
~~~

Same name `customers`, yet the two tables differ in structure and data. To inspect `search_path`:

~~~sql
SET search_path TO lab_reporting, lab_sales;

SELECT customer_id, display_label
FROM customers;

SET search_path TO lab_sales, lab_reporting;

SELECT customer_id, customer_name
FROM customers;

RESET search_path;
~~~

This is why **you should not rely on short names** in queries or migrations requiring high precision. If a new schema is later placed earlier in `search_path`, old SQL statements might resolve to a different object.

## 8. Schemas group objects logically, not physically

In the three-schema example, PostgreSQL still uses:

- The same instance and transaction management system.
- The same database and shared operational resources.
- The same WAL/backup mechanisms per the database/cluster architecture.
- The same catalog system for managing object metadata.
- The same query planner, capable of performing `JOIN` operations across schemas.

Therefore, schemas are suitable for **logical organization and privilege management**, but do not inherently guarantee:

- Independent CPU/memory/I/O partitioning per schema.
- Completely independent backup/restore of every schema object.
- Risk isolation for DDLs or transactions consuming shared resources.
- Preventing all cross-schema queries if a role holds the necessary privileges.
- Secure tenant boundaries without access controls.

If stronger isolation is needed for administration, operations, or data lifecycles, you must consider separate databases, separate clusters, or different infrastructure depending on requirements.

## 9. Two-tier permissions: schema and object

PostgreSQL manages privileges at both the **schema** level and the **objects inside the schema**. This is the single most important point to remember when using schemas as organizational boundaries.

Key schema privileges:

| Privilege | Meaning |
| --- | --- |
| `USAGE` | Allows referencing/looking up objects inside the schema per privilege rules |
| `CREATE` | Allows creating new objects inside the schema |

Table privileges are a separate layer, such as `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `REFERENCES`, and `TRIGGER`.

**Having `USAGE` on a schema does not automatically allow `SELECT` on every table in that schema.** Similarly, having `SELECT` on a table without `USAGE` on its schema normally prevents referencing that table in the usual way.

### Read-only role example

In the lab environment and using an account with administrative privileges:

~~~sql
CREATE ROLE lab_sales_reader NOLOGIN;

REVOKE ALL ON SCHEMA lab_sales FROM PUBLIC;

GRANT USAGE ON SCHEMA lab_sales
TO lab_sales_reader;

GRANT SELECT ON ALL TABLES IN SCHEMA lab_sales
TO lab_sales_reader;
~~~

Meaning:

1. `lab_sales_reader` is a non-login group role (`NOLOGIN`).
2. `REVOKE ALL ... FROM PUBLIC` removes schema privileges broadly granted to the `PUBLIC` pseudo-role, if any.
3. `GRANT USAGE` allows the group to reference objects inside `lab_sales`.
4. `GRANT SELECT ON ALL TABLES` grants read access on eligible tables/views **currently existing** in the schema at the time of execution.

For an actual user to use the group's privileges, an administrator must grant membership to an appropriate login role, for example via `GRANT lab_sales_reader TO some_login_role` once that role has been created and verified. Privileges may be inherited or require `SET ROLE` depending on membership/role configuration.

### Write role example

~~~sql
CREATE ROLE lab_sales_writer NOLOGIN;

GRANT USAGE ON SCHEMA lab_sales
TO lab_sales_writer;

GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA lab_sales
TO lab_sales_writer;
~~~

A role with table write privileges does not necessarily have permission to alter the schema. Without `CREATE` on the schema or table ownership, that role does not automatically have the right to create tables or run all `ALTER TABLE` commands.

In real systems, you can separate:

- **Migrator/owner:** responsible for creating and modifying schemas/DDL.
- **Application writer:** uses only the required DML privileges.
- **Report reader:** reads only permitted tables or views.
- **Audit reader:** granted audit read access under a separate policy.

This separation limits the blast radius if an application or credentials are compromised.

### CREATE at the database level differs from CREATE at the schema level

To **create a new schema** in a database, a role needs the appropriate database-level privilege (typically `CREATE ON DATABASE`). To **create a table inside an existing schema**, a role needs `CREATE ON SCHEMA` or must be the owner/hold equivalent privileges.

Illustrative syntax example:

~~~sql
-- Grant permission to create new schemas in the database to an
-- existing role, when policy permits.
GRANT CREATE ON DATABASE commerce TO app_migrator;

-- Grant permission to create objects in the sales schema.
GRANT CREATE ON SCHEMA sales TO app_migrator;
~~~

`commerce`, `sales`, and `app_migrator` here are illustrative names. Do not grant broad `CREATE` privileges to every account simply to resolve an error during a single migration run.

## 10. Default privileges: permissions for future tables

`GRANT SELECT ON ALL TABLES IN SCHEMA ...` applies only to tables/views that exist at the moment the command runs. When a migration creates a new table, that table **does not automatically inherit all previously granted privileges**.

PostgreSQL provides `ALTER DEFAULT PRIVILEGES` to set default privileges for objects created in the future. For example, if role `lab_migrator` is the role that will actually create tables:

~~~sql
-- Illustration: lab_migrator must exist and the executor
-- must have permission to configure default privileges for this role.
ALTER DEFAULT PRIVILEGES
    FOR ROLE lab_migrator
    IN SCHEMA lab_sales
    GRANT SELECT ON TABLES TO lab_sales_reader;
~~~

Meaning:

- Affects only objects **created after the configuration**, not retroactively granting permissions on existing tables.
- Tied to the **object-creating role** (`FOR ROLE lab_migrator`), not solely to the schema name.
- Does not mean another group role's privileges automatically determine default privileges when a member creates a table.
- Separate configurations may be needed for `SEQUENCES`, `FUNCTIONS`, or other object types, as they do not share the same privilege set as `TABLES`.

When using Flyway, Liquibase, or other migration tools, identify the exact role running migrations to configure default privileges appropriately.

## 11. Schema owner differs from table owner

A schema and each object inside it have their **own owners**. The creator of a schema typically owns the schema; however, being permitted to create a table in a schema does not mean every table will belong to the schema's owner.

For example:

~~~sql
SELECT
    n.nspname AS schema_name,
    pg_get_userbyid(n.nspowner) AS schema_owner
FROM pg_namespace AS n
WHERE n.nspname = 'lab_sales';
~~~

And inspect table owners:

~~~sql
SELECT
    schemaname,
    tablename,
    tableowner
FROM pg_tables
WHERE schemaname = 'lab_sales'
ORDER BY tablename;
~~~

When managing migrations, standardize a consistent owner role to avoid situations where account A creates one table and account B creates another, causing subsequent DDL changes to fail due to missing permissions.

`GRANT ALL PRIVILEGES` on a table does not make the grantee the **owner** of the table; certain DDL operations and ownership management still have distinct requirements.

## 12. search_path is a security concern, not just SQL typing convenience

If an application uses **unqualified** function, table, or type names and places a schema where untrusted users have `CREATE` privileges ahead in `search_path`, those users could create same-named objects to alter how PostgreSQL resolves names.

Therefore, placing a schema in `search_path` implies **trusting objects that may be created inside it**. For security-sensitive applications:

- Do not grant `CREATE` in schemas searched early by the application to untrusted roles.
- Prefer qualified object names in critical SQL statements.
- Control `search_path` settings in connection pools, migrations, and routines.
- Never allow user input to arbitrarily dictate schema names concatenated into SQL.
- Verify actual privileges on `public`, especially in upgraded databases or databases created from older templates.

### Special care with SECURITY DEFINER

A function declared `SECURITY DEFINER` executes with the privileges of the **function owner** rather than the caller. If this function relies on an unsafe `search_path`, wrongly resolved objects can create severe vulnerabilities.

A safer structure uses qualified table names and pins the function's path:

~~~sql
CREATE OR REPLACE FUNCTION lab_reporting.customer_count()
RETURNS bigint
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, lab_sales, pg_temp
AS $$
    SELECT COUNT(*) FROM lab_sales.customers
$$;
~~~

This is a syntax example, **not a recommendation to make every counting function SECURITY DEFINER**. In real use, you must evaluate the owner, `EXECUTE` privileges, table access permissions, temporary object handling, and the function's entire execution path. When privilege elevation is unnecessary, prefer `SECURITY INVOKER` (standard behavior).

`pg_catalog` has special system lookup rules, while `pg_temp` must be ordered carefully so temporary objects do not shadow critical objects. Pinning `search_path` prevents callers from indirectly controlling the function's name-resolution environment.

## 13. Is a schema an absolute security boundary?

**No.** Schemas have separate access privileges but still live inside the same database. Several limitations must be understood:

- A role with sufficient privileges can still `JOIN` tables from `sales` with tables from `audit`.
- Object-owning roles have administrative privileges that differ from a role granted only `SELECT`.
- Superusers and powerful administrative roles can bypass many standard permission checks.
- Schemas do not automatically apply **row-level security (RLS)** to all tables.
- Sharing a schema does not force tables to share the same owner or permissions.
- Functions and views have their own permission execution rules that must be reviewed so they do not serve as unintended data backdoors.

If you need to separate data among multiple customers/tenants, you must design permissions, tenant routing, migrations, RLS if appropriate, monitoring, and cross-access testing. **Simply placing tenants in separate schemas does not guarantee data leak prevention** if the application role has read privileges across multiple schemas.

## 14. Organizing by business domain or by technical layer?

There are two common ways to divide schemas.

### By business domain

~~~text
sales.orders
sales.customers

billing.invoices
billing.payments

identity.users
identity.sessions
~~~

Advantages: business-related objects sit close together, ownership/migrations can be assigned per module, and permissions align with responsibilities.

### By object category or usage purpose

~~~text
core.customers
core.orders

reporting.daily_revenue
reporting.customer_spend

audit.entity_events
audit.access_events
~~~

Advantages: clearly separates base tables, reporting layers, and logs. However, an overly large `core` schema can cause teams to become tightly coupled.

**There is no single optimal schema layout for every project.** The division should reflect access patterns, object counts, migration lifecycles, ownership boundaries, and operational overhead.

### Questions to ask when creating a schema

1. Do this group of objects share an owner and lifecycle?
2. Do we need different permissions between this group and other groups?
3. Do the tables require frequent foreign keys and JOINs across them?
4. Will one group's migrations be deployed independently?
5. Do backup, restore, BI, ORM, and CI tools support this organization?
6. Is there a risk of object names being shadowed via `search_path`?
7. Does a new schema solve a real problem or just add another namespace to manage?

Do not create a dedicated schema for every single table if it does not provide proportional organizational or permission benefits.

## 15. Foreign keys and JOIN queries across schemas

Because schemas live in the same database, you can declare cross-schema foreign keys:

~~~sql
CREATE SCHEMA lab_billing;

CREATE TABLE lab_billing.invoices (
    invoice_id integer PRIMARY KEY,
    order_id integer NOT NULL UNIQUE
        REFERENCES lab_sales.orders(order_id),
    amount numeric(12, 2) NOT NULL CHECK (amount >= 0)
);
~~~

An aggregate query:

~~~sql
SELECT
    i.invoice_id,
    o.order_id,
    c.customer_name,
    i.amount
FROM lab_billing.invoices AS i
JOIN lab_sales.orders AS o
    ON o.order_id = i.order_id
JOIN lab_sales.customers AS c
    ON c.customer_id = o.customer_id
ORDER BY i.invoice_id;
~~~

If no invoice rows have been inserted yet, the result is an empty set; the query remains valid. You can insert a test row in the lab database:

~~~sql
INSERT INTO lab_billing.invoices
    (invoice_id, order_id, amount)
VALUES (9001, 101, 100.00);
~~~

Rerunning the query returns invoice 9001 for order 101, customer An.

### Do cross-schema foreign keys affect organization?

Yes. Schemas provide namespaces, but **do not decouple dependencies**. If `lab_sales.orders` is dropped or altered, `lab_billing.invoices` may be affected by the referential constraint. A schema cannot arbitrarily be "deployed independently" if another schema has foreign keys, views, or functions depending on it.

When designing modules that must truly deploy independently, you need to plan dependency management, migration ordering, or architectural adjustments rather than assuming schemas already solve the problem.

## 16. Migrations: specify the target schema instead of guessing

In projects using Flyway, Liquibase, Alembic, or plain SQL migrations, a common mistake is running:

~~~sql
CREATE TABLE invoices (
    invoice_id bigint PRIMARY KEY
);
~~~

under a `search_path` different from the expected environment. The table may be created in the wrong schema or fail due to insufficient privileges.

A clearer approach:

~~~sql
CREATE TABLE billing.invoices (
    invoice_id bigint PRIMARY KEY
);
~~~

When working in a multi-schema environment, design consistently:

- **Target schema:** explicitly declare where tables and objects are created.
- **Migrator role:** holds required ownership/DDL privileges, separate from the application role.
- **Migration history:** the tool may require a dedicated schema for its migration tracking table.
- **Dependency order:** schemas are created before tables; tables are created before dependent views/foreign keys.
- **Default privileges:** configured for the role that actually creates new objects.
- **Rollback/forward-fix:** account for the limits of each DDL type and data transformations.

A script using `CREATE SCHEMA IF NOT EXISTS` can be rerun if the schema already exists, though that **does not prove** the existing schema has the right owner, permissions, or structure. Similarly, `CREATE TABLE IF NOT EXISTS` does not verify that the entire table definition matches the design. For production, migrations need versioning and validation procedures.

### search_path in application tooling

Some clients/frameworks provide a default schema configuration option. Understand whether it sets `search_path` on the session or prepends the schema name when generating SQL. These two approaches have different impacts on prepared statements, connection pools, functions, and migrations.

In a connection pool, if a request alters `search_path` and returns the connection to the pool without properly resetting it, the next request may inherit leftover schemas. When per-transaction configuration is needed, consider `SET LOCAL` inside a clearly scoped transaction and ensure connections are never reused out of context.

## 17. Schemas in multi-tenant architectures

One multi-tenancy design option is **schema per tenant**:

~~~text
tenant_a.customers
tenant_a.orders

tenant_b.customers
tenant_b.orders

shared.countries
shared.product_catalog
~~~

Potential advantages include:

- Identical table names, with data separated by namespace.
- Ability to control permissions and migrations per tenant if properly structured.
- Clear visibility of data boundaries in the catalog.

However, evaluate the costs:

- Schema and object counts grow rapidly as tenants scale.
- Every tenant requires ordered migrations and error handling.
- Connection pools must select the right tenant in every transaction.
- Backup/restore and dependency checks can become more complex.
- A misconfigured `search_path` or a role with access to multiple schemas can cause cross-tenant reads/writes.
- Catalogs and tooling experience overhead from managing many objects.

Thus, schema-per-tenant is **an architectural option**, not automatically the safest or fastest default. Some systems use shared tables with `tenant_id` combined with RLS, while others use database-per-tenant; the decision depends on isolation requirements, scale, operations, and compliance.

### Never concatenate arbitrary tenant names into SQL

If a tenant ID originates from a request, never use unchecked string concatenation to build `SET search_path TO tenant_...` or dynamic table names. Schema names must come from a trusted mapping, be properly quoted as identifiers when needed, and be tightly bound to the authenticated tenant. **Prepared statement placeholders `?` are only suitable for values**, not for directly substituting schema or table names in SQL.

## 18. Common system schemas

When listing schemas, you will notice several namespaces serving internal purposes.

| Schema | Role |
| --- | --- |
| `pg_catalog` | Contains PostgreSQL's system catalogs and built-in functions and types |
| `information_schema` | SQL-standard views for inspecting metadata, subject to access privileges |
| `public` | Standard schema pre-created in many databases |
| `pg_toast` | Objects related to PostgreSQL's large-value storage mechanism |
| `pg_temp_N` | Session/backend temporary schema; exact naming managed by PostgreSQL |

Do not create business tables directly inside `pg_catalog`, `pg_toast`, or other system schemas. Temporary schemas have their own lifecycles and lookup rules and are not a long-term solution for module separation.

### Temporary tables and search_path

For example:

~~~sql
CREATE TEMP TABLE scratch (
    id integer PRIMARY KEY
);

INSERT INTO scratch (id) VALUES (1);

SELECT * FROM scratch;
~~~

Temporary tables are placed in the session's temporary schema, not `sales.scratch` or `public.scratch`. PostgreSQL has lookup rules checking the temporary schema for unqualified relation/type names, meaning a temporary table can **shadow** a regular table of the same name in certain situations.

When you need to query a real table unambiguously, use a qualified name such as `lab_sales.orders`. A temp table is normally dropped when the session ends, or according to the declared `ON COMMIT` option.

## 19. Inspecting schemas and objects in psql

Inside `psql`, several meta-commands are helpful:

~~~text
\dn
\dn+
\dt lab_sales.*
\dv lab_reporting.*
\df lab_reporting.*
\d lab_sales.orders
~~~

Meaning:

- `\dn`: list schemas.
- `\dn+`: additional details such as owner and access privileges.
- `\dt lab_sales.*`: list tables in the specified schema.
- `\dv lab_reporting.*`: list views.
- `\df lab_reporting.*`: functions in the schema.
- `\d lab_sales.orders`: column, index, and constraint details for the table.

Commands starting with a backslash are **psql meta-commands**, not standard SQL sent over JDBC.

### Querying via SQL

To read the list of schemas:

~~~sql
SELECT schema_name
FROM information_schema.schemata
ORDER BY schema_name;
~~~

`information_schema` is typically filtered by the role's privileges. To inspect the PostgreSQL catalog directly:

~~~sql
SELECT
    n.nspname AS schema_name,
    pg_get_userbyid(n.nspowner) AS owner
FROM pg_namespace AS n
WHERE n.nspname NOT LIKE 'pg_%'
  AND n.nspname <> 'information_schema'
ORDER BY n.nspname;
~~~

To view tables/views by schema:

~~~sql
SELECT
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema IN (
    'lab_sales',
    'lab_reporting',
    'lab_audit'
)
ORDER BY table_schema, table_name;
~~~

Listings from `information_schema` can be incomplete if the role lacks permissions to see the corresponding objects. Never conclude a schema is "empty" solely from a query run by a restricted role.

## 20. Checking permissions with SQL

PostgreSQL provides privilege-checking functions, for example:

~~~sql
SELECT
    has_schema_privilege(
        current_user,
        'lab_sales',
        'USAGE'
    ) AS can_use_schema,
    has_schema_privilege(
        current_user,
        'lab_sales',
        'CREATE'
    ) AS can_create_in_schema,
    has_table_privilege(
        current_user,
        'lab_sales.customers',
        'SELECT'
    ) AS can_read_customers;
~~~

These functions inspect permissions for the currently connected user. They are useful when an application reports `permission denied for schema ...` or `permission denied for table ...`.

If `can_use_schema = true` while `can_read_customers = false`, the role can reference the schema but cannot read the table. Conversely, having a table grant is not sufficient without schema `USAGE`. In practice, also check privileges related to functions, sequences, and other objects depending on the operation.

### Applying least-privilege GRANTs

An application that only needs to read reporting views can be granted `USAGE` on `lab_reporting` and `SELECT` on the appropriate view, rather than granting `SELECT` on all transactional tables. However, views have their own **permission execution rules** (by default usually using the view owner's permissions on base tables; options such as `security_invoker` have version requirements). You must design and verify ownership, permissions, and RLS in practice before treating views as a complete security layer.

## 21. Backup, restore, and schema lifecycle

The `pg_dump` tool supports filtering by schema:

~~~bash
pg_dump \
  -Fc \
  -n lab_sales \
  -d schema_lab \
  -f lab_sales.dump
~~~

The `-n` option selects objects matching the specified schema; `-Fc` produces a custom-format archive for use with `pg_restore` following an appropriate workflow.

**Important warning:** backing up one schema does not guarantee inclusion of all dependencies located outside that schema. For instance, `lab_reporting.paid_revenue` references tables in `lab_sales`; dumping only `lab_reporting` may be insufficient to restore independently into an empty database. Privileges, extensions, roles, and related objects also require separate planning.

A schema is an **object selection boundary for administrative tasks**, not necessarily a completely self-contained backup unit. For production, always test actual restores, verify dependencies, and record version/system metadata.

### DROP SCHEMA, RESTRICT, and CASCADE

~~~sql
-- Rejects dropping the schema if dependent objects remain
-- according to PostgreSQL dependency rules.
DROP SCHEMA lab_audit RESTRICT;
~~~

While the schema still contains the `events` table, this command fails because objects exist. The `CASCADE` version:

~~~sql
-- DANGEROUS: practice only when certain it is the right lab schema.
DROP SCHEMA lab_audit CASCADE;
~~~

`CASCADE` can pull in **dependent objects in other schemas**, not merely tables inside the dropped schema. Therefore, it cannot be treated like "just deleting a folder". In real environments, examine dependencies, backups, privileges, and recovery plans before altering or dropping a schema.

### Renaming a schema

PostgreSQL supports:

~~~sql
ALTER SCHEMA lab_reporting RENAME TO lab_reports;
~~~

This is a syntax example and requires ownership or equivalent privileges. Although the database can update internal dependencies, SQL statements or applications with hardcoded schema names may break after renaming; migrations must be coordinated with code and tooling.

## 22. Common errors and misconceptions

### 22.1. Confusing schemas with databases

`sales` and `reporting` in the same database can be joined directly. Two different databases cannot be queried across databases with the same simple qualified naming.

### 22.2. Assuming an unqualified table is always public.table

`CREATE TABLE orders (...)` depends on `search_path`. If another schema sits first, the object may be created elsewhere. Use qualified names in migrations.

### 22.3. Granting SELECT while forgetting USAGE

Without `USAGE` privilege on the schema, a role may be unable to reference a table even if it has `SELECT`. Check both schema and object permissions.

### 22.4. Granting USAGE and assuming all tables are readable

`USAGE` does not replace `SELECT`. Reading requires appropriate table/view grants or a controlled access path.

### 22.5. Using GRANT ALL TABLES and expecting future tables to inherit permissions

That command applies to existing tables. To grant permissions for future objects, configure `ALTER DEFAULT PRIVILEGES` for the exact role creating those objects.

### 22.6. Giving untrusted users CREATE in a schema early in search_path

New objects can shadow names referenced by the application, creating SQL resolution risks. Keep `search_path` trusted and avoid broad `CREATE` grants.

### 22.7. Dynamically changing search_path in a connection pool and forgetting to reset

Subsequent requests may read the wrong tenant or module. Properly manage session/transaction lifecycles or use fully qualified names.

### 22.8. Treating schema-per-tenant as absolute security isolation

Data still resides in the same database and permissions may allow cross-access. You must implement tenant authorization, role separation, and cross-access tests.

### 22.9. Running DROP SCHEMA CASCADE without inspecting dependencies

It can delete tables, views, or constraints elsewhere via dependencies. Never use it in production as a casual cleanup step.

### 22.10. Thinking schemas determine query performance

Schemas are namespaces; they do not inherently make queries faster. Performance depends on queries, indexes, statistics, data, and execution plans. Splitting tables across multiple schemas does not replace SQL optimization.

## 23. Hands-on exercises

Use the `lab_sales`, `lab_reporting`, and `lab_audit` data from the previous sections.

### Exercise 1: Two tables with the same name

Run:

~~~sql
SELECT COUNT(*) AS sales_customers
FROM lab_sales.customers;

SELECT COUNT(*) AS report_customers
FROM lab_reporting.customers;
~~~

**Expected result:** `sales_customers = 3`; `report_customers = 2`. Same name `customers`, yet not the same object.

### Exercise 2: Changing search_path and observing

~~~sql
SET search_path TO lab_reporting, lab_sales;

SELECT customer_id, display_label
FROM customers
ORDER BY customer_id;

SET search_path TO lab_sales, lab_reporting;

SELECT customer_id, customer_name
FROM customers
ORDER BY customer_id;

RESET search_path;
~~~

Explain why both queries use `FROM customers` yet read different tables. Hint: schema position in `search_path`.

### Exercise 3: Cross-schema query

~~~sql
SELECT
    c.customer_name,
    o.order_id,
    o.status,
    o.total
FROM lab_sales.customers AS c
JOIN lab_sales.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'paid'
ORDER BY o.order_id;
~~~

**Result:** orders 101 and 102 for An, and order 104 for Chi. Try querying `lab_reporting.paid_revenue` and compare revenue 350 for An, 0 for Binh, and 120 for Chi.

### Exercise 4: Analyzing privileges

Suppose a role has `USAGE ON SCHEMA lab_sales` and `SELECT ON lab_sales.customers`, but does not have `INSERT`. Can the role run `SELECT`? Can it run `INSERT`?

**Answer:** Given standard appropriate permissions, ownership, and policies, the role can read the table but cannot insert rows from these two grants alone.

### Exercise 5: Default privileges

You ran `GRANT SELECT ON ALL TABLES IN SCHEMA lab_sales TO lab_sales_reader`. Tomorrow the migrator creates `lab_sales.returns`. Why might the reader role not yet be able to read the new table?

**Answer:** `GRANT ... ALL TABLES` applies to existing tables. Default privileges must be configured for the exact **table-creating role** and schema, or new privileges must be granted after the migration.

### Exercise 6: Checking the current schema

~~~sql
SHOW search_path;

SELECT
    current_schema(),
    current_schemas(true);
~~~

Compare the list above with the output of `\dn` in `psql`. Explain why some schemas may appear in the catalog but not in the effective search path.

### Exercise 7: Designing new boundaries

An application has groups for **orders**, **payments**, **reporting**, and **audit**. Propose schema names, owner/migrator roles, and read/write privileges for each group. Answer: why should the payment-processing application not be granted `CREATE` on all schemas? Should every application writer be granted read access to the entire audit schema?

There is no single right answer for schema names, but the design must clearly demonstrate responsibilities, least privilege, and cross-schema dependencies.

## 24. Key takeaways for organizing PostgreSQL data

- **A schema is a namespace inside a database**, enabling two objects with the same name to exist in different organizational areas.
- **Qualified names `schema.object`** make SQL unambiguous and avoid dependence on `search_path`.
- **`search_path` is both a name-resolution mechanism and a trust decision** that must be controlled across applications, migrations, and privileged functions.
- **Schema privileges (`USAGE`, `CREATE`) and table/view/function privileges are separate tiers**; granting one does not substitute for the other.
- **Default privileges** affect only future objects created by the matching role; configure them alongside grants on existing tables.
- **Schemas are neither physical nor absolute security boundaries**; tables still share a database and can have cross-schema dependencies.
- **Good organization** is grounded in business domains, ownership, migrations, access control, and operability, rather than sheer namespace count.

When schemas are used to clearly express responsibilities and limit access, PostgreSQL becomes much easier to govern. Yet the most effective usage always combines namespaces with explicit object names, least-privilege roles, ordered migrations, and actual permission verification.
