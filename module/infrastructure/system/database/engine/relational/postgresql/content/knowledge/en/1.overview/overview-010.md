# Roadmap from Your First Database to Safe PostgreSQL Operations

A single `CREATE DATABASE` command can create a PostgreSQL database in seconds, yet building a system that stays **reliable with real users** is a longer journey. Data needs constraints, transactions must remain correct under concurrent access, applications must connect and handle errors safely, access must be restricted, and backups must actually **restore** when an incident hits.

This lesson presents a **learning and implementation roadmap for PostgreSQL from zero to controlled production operations**. Instead of listing isolated features, each stage defines objectives, hands-on examples, completion evidence, and readiness criteria for the next step. The sample dataset is a simple store; the same principles apply to learning platforms, order management systems, web apps, or Java services backed by PostgreSQL.

Commands follow modern PostgreSQL using `psql`, `IDENTITY`, `TIMESTAMPTZ`, and `NUMERIC`, and InnoDB is **irrelevant here**: PostgreSQL has its own storage engine and MVCC implementation. Run exercises on a **test** instance and database. Hostnames, accounts, and passwords in examples are placeholders, never real credentials.

## 1. Journey Map: From "It Runs" to "It Operates Safely"

A PostgreSQL system should mature through these stages:

~~~mermaid
flowchart TD
    A["1. Connect and understand cluster / database / schema"] --> B["2. Design tables and constraints"]
    B --> C["3. Load data and write accurate queries"]
    C --> D["4. Transactions and concurrency"]
    D --> E["5. App connectivity, migrations, and privileges"]
    E --> F["6. Explain plans and observe load"]
    F --> G["7. Backups, restore drills, monitoring, incident response"]
    G --> H["8. Runbook-driven production operations"]
~~~

Each step depends on the previous one:

- If the **schema does not enforce integrity**, building APIs quickly cannot fix corrupt data.
- If **transactions are not atomic**, individually succeeding statements can still leave orders missing items or miscalculate stock.
- If **privileges are not separated**, a single SQL injection bug or leaked credential can cause massive blast radius.
- If **restores are never tested**, a backup file sitting on disk does not prove the service can recover.
- If **observability and alerting are missing**, connection exhaustion, lock pileups, disk saturation, or lagging autovacuum go unnoticed until the application stops.

The ultimate goal is establishing a **verifiable path** from writing data to operating, protecting, and recovering that data.

## 2. PostgreSQL Concepts to Know Before Creating Tables

PostgreSQL uses specific terms with precise meanings:

| Concept | Meaning | Example |
| --- | --- | --- |
| **Server/instance** | PostgreSQL process serving client connections to data | A PostgreSQL service on a VM or managed service |
| **Database cluster** | Set of databases managed by one PostgreSQL instance; not synonymous with an HA cluster | Instance holding `postgres` and `shop_learning` |
| **Database** | Named database unit; each connection operates within one database | `shop_learning` |
| **Schema** | Object namespace inside a database | `sales` |
| **Table** | Collection of rows, columns, and constraints | `sales.orders` |
| **Role** | Identity managing login, ownership, and privileges | `shop_reader` |
| **Transaction** | Atomic unit of work that can `COMMIT` or `ROLLBACK` | Create order and deduct stock |
| **WAL** | Write-ahead log supporting durability and recovery | Foundation of crash recovery and PITR |

**A PostgreSQL cluster can hold multiple databases; a database can hold multiple schemas.** You cannot use `schema.table` in standard PostgreSQL to directly reference a table in another database as if it were a schema in the same database. Cross-database access requires dedicated mechanisms such as `postgres_fdw` or separate integration designs.

`public` is a schema commonly created by default, yet our example creates a dedicated `sales` schema to separate application objects from defaults and simplify privilege management.

## 3. Stage 1 — Install, Connect, and Verify the Right Environment

Depending on OS, PostgreSQL may be installed via system packages, official installers, containers, or a managed service. Installation method does not change core SQL rules, yet affects data file paths, service management, TLS, and backup policies.

Before starting, make sure you have:

1. Server host and port; `5432` is common by default, though configurable.
2. An existing database name to connect to initially, such as `postgres`.
3. A role with privileges to create a practice database.
4. A secure authentication method: password entered interactively, via a secret manager, or organization-approved auth.
5. Confirmation that this is a **development/lab** instance, never production.

Connect with `psql`:

~~~bash
psql -h 127.0.0.1 -p 5432 -U postgres -d postgres
~~~

The command may prompt for a password. Never embed passwords directly in shell history, URLs, or source files. Inside `psql`, inspect:

~~~sql
SELECT
    current_database() AS database_name,
    current_user AS connected_role,
    current_setting('server_version') AS server_version,
    current_setting('TimeZone') AS session_timezone;
~~~

`psql` meta-commands:

~~~text
\conninfo
\l
\du
~~~

`\conninfo` shows current connection details; `\l` lists databases; `\du` lists roles within visible privilege scope. Lines starting with `\` are **psql meta-commands**, not SQL statements you can send verbatim via JDBC.

### 3.1. Create a Practice Database

While connected to `postgres` as a role with `CREATEDB` privilege:

~~~sql
CREATE DATABASE shop_learning
    WITH ENCODING 'UTF8';
~~~

`CREATE DATABASE` cannot execute inside an explicit transaction block. Afterward, switch to the new database using the `psql` command:

~~~text
\connect shop_learning
~~~

Then verify:

~~~sql
SELECT current_database();
-- shop_learning
~~~

If the database name already exists, creation raises an error. Never run `DROP DATABASE` to "start fresh" without confirming that the database is strictly a disposable lab environment containing no data worth keeping.

### 3.2. Distinguish Database from Schema

Inside `shop_learning`:

~~~sql
CREATE SCHEMA sales;

SELECT schema_name
FROM information_schema.schemata
WHERE schema_name = 'sales';
~~~

All tables in this lesson carry the `sales.` prefix, e.g., `sales.customers`. Qualifying schema names avoids surprises from differing `search_path` settings across sessions or roles.

**Stage 1 completion check:** connected via `psql`, verified exact database/role/version, and created a practice database and schema without touching production data.

## 4. Stage 2 — Design Tables, Data Types, and Constraints

Suppose the store manages customers, products, orders, and order line items. Relationships:

~~~mermaid
erDiagram
    CUSTOMERS ||--o{ ORDERS : places
    ORDERS ||--o{ ORDER_ITEMS : contains
    PRODUCTS ||--o{ ORDER_ITEMS : appears_in

    CUSTOMERS {
        bigint customer_id PK
        text email UK
        text full_name
    }
    PRODUCTS {
        bigint product_id PK
        text sku UK
        text product_name
        numeric list_price
        integer stock_qty
    }
    ORDERS {
        bigint order_id PK
        text order_no UK
        bigint customer_id FK
        timestamptz created_at
        text status
    }
    ORDER_ITEMS {
        bigint order_id PK,FK
        bigint product_id PK,FK
        integer quantity
        numeric unit_price
    }
~~~

A customer can have many orders; each order has many line items; a product can appear across many orders. The composite primary key `(order_id, product_id)` on `order_items` encodes the rule that **a product appears at most once per order**.

### 4.1. Create Customers and Products

~~~sql
CREATE TABLE sales.customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT customers_full_name_nonblank
        CHECK (length(btrim(full_name)) > 0)
);

CREATE TABLE sales.products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    list_price NUMERIC(12, 2) NOT NULL,
    stock_qty INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT products_name_nonblank
        CHECK (length(btrim(product_name)) > 0),
    CONSTRAINT products_price_positive
        CHECK (list_price > 0),
    CONSTRAINT products_stock_nonnegative
        CHECK (stock_qty >= 0)
);
~~~

Notable design choices:

- `GENERATED ALWAYS AS IDENTITY` generates identifier values via a PostgreSQL-managed sequence; normal applications do not supply IDs manually.
- `email` and `sku` are unique business keys; PostgreSQL enforces `UNIQUE` per the relevant comparison operator/collation.
- `NUMERIC(12,2)` fits two-decimal currency better than `real`/`double precision` when exact decimal arithmetic is needed.
- `BOOLEAN` supports `TRUE`, `FALSE`, and `NULL` unless constrained by `NOT NULL`; this example explicitly forbids `NULL`.
- `CHECK` restricts prices and quantities. `NOT NULL` must be declared separately: in PostgreSQL, a `CHECK` expression evaluating to `UNKNOWN` due to `NULL` does not trigger a violation.

### 4.2. Create Orders and Line Items

~~~sql
CREATE TABLE sales.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_no TEXT NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL
        REFERENCES sales.customers(customer_id)
        ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status TEXT NOT NULL DEFAULT 'NEW',
    CONSTRAINT orders_status_valid
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
);

CREATE TABLE sales.order_items (
    order_id BIGINT NOT NULL
        REFERENCES sales.orders(order_id)
        ON DELETE RESTRICT,
    product_id BIGINT NOT NULL
        REFERENCES sales.products(product_id)
        ON DELETE RESTRICT,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL,
    PRIMARY KEY (order_id, product_id),
    CONSTRAINT items_quantity_positive
        CHECK (quantity > 0),
    CONSTRAINT items_price_positive
        CHECK (unit_price > 0)
);
~~~

`FOREIGN KEY` prevents orders tied to nonexistent customers and prevents line items from referencing nonexistent products. `ON DELETE RESTRICT` guards against accidentally wiping order history when deleting a customer or product; applications can mark records inactive instead of physical deletion when preserving history.

**The locked-in price at order time** lives in `order_items.unit_price`. If the store later updates `products.list_price`, historical orders keep their recorded unit prices.

### 4.3. Distinguish Business Keys from Referential Keys

| Type | Example | Purpose |
| --- | --- | --- |
| Primary key | `customer_id` | Stable internal row identification and referencing |
| Unique business key | `email`, `sku`, `order_no` | Prevent duplicate business codes |
| Foreign key | `orders.customer_id` | Protect parent–child referential integrity |
| Composite key | `order_items(order_id, product_id)` | Prevent repeating the same product in one order |
| Check constraint | `stock_qty >= 0` | Block invalid per-row states |

In PostgreSQL, **a foreign key does not automatically create an index on the referencing child column**. Indexes supporting `JOIN`s and parent delete/update checks should be created deliberately as data volume grows.

### 4.4. Inspect the Created Structure

In `psql`:

~~~text
\dt sales.*
\d sales.customers
\d sales.order_items
~~~

Or via metadata query:

~~~sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'sales'
ORDER BY table_name;
~~~

**Stage 2 completion check:** can explain why four tables are used instead of one wide table, identify primary/foreign keys, and explain how `CHECK`, `UNIQUE`, and `NOT NULL` reject invalid data.

## 5. Stage 3 — Load Sample Data and Run Reconcilable Queries

Load data in order: **parent tables first, child tables after**. Sample statements resolve internal keys via email, SKU, and order number rather than hardcoding sequence ID values.

### 5.1. Load Customers and Products

~~~sql
INSERT INTO sales.customers (email, full_name)
VALUES
    ('an@example.test', 'Nguyễn An'),
    ('binh@example.test', 'Trần Bình');

INSERT INTO sales.products
    (sku, product_name, list_price, stock_qty)
VALUES
    ('BOOK-SQL', 'PostgreSQL Book', 150000.00, 40),
    ('PEN-BLUE', 'Blue Pen',        20000.00, 100),
    ('MOUSE-01', 'Wireless Mouse', 280000.00, 15);
~~~

The `example.test` domain is reserved for illustrative data. Never use real customer emails in shared examples.

### 5.2. Load Two Orders

~~~sql
INSERT INTO sales.orders (order_no, customer_id, status)
SELECT v.order_no, c.customer_id, v.status
FROM (
    VALUES
        ('SO-001', 'an@example.test',   'PAID'),
        ('SO-002', 'binh@example.test', 'NEW')
) AS v(order_no, email, status)
JOIN sales.customers AS c
    ON c.email = v.email;
~~~

In this sample, both emails exist. In real bulk-import pipelines, reconcile input row counts against inserted row counts; using `INNER JOIN` to look up keys silently drops unmatched input rows from the `SELECT` output rather than raising a foreign key error.

### 5.3. Load Three Order Line Items

~~~sql
INSERT INTO sales.order_items
    (order_id, product_id, quantity, unit_price)
SELECT
    o.order_id,
    p.product_id,
    v.quantity,
    v.unit_price
FROM (
    VALUES
        ('SO-001', 'BOOK-SQL', 2, 150000.00::numeric),
        ('SO-001', 'PEN-BLUE', 3,  20000.00::numeric),
        ('SO-002', 'MOUSE-01', 1, 280000.00::numeric)
) AS v(order_no, sku, quantity, unit_price)
JOIN sales.orders AS o ON o.order_no = v.order_no
JOIN sales.products AS p ON p.sku = v.sku;
~~~

Line totals:

| Order | Product | Formula | Total |
| --- | --- | --- | ---: |
| `SO-001` | PostgreSQL Book | 2 × 150,000 | 300,000 |
| `SO-001` | Blue Pen | 3 × 20,000 | 60,000 |
| `SO-002` | Wireless Mouse | 1 × 280,000 | 280,000 |

### 5.4. Verify Data with SELECT and JOIN

~~~sql
SELECT
    o.order_no,
    c.full_name,
    o.status,
    SUM(oi.quantity * oi.unit_price) AS order_total
FROM sales.orders AS o
JOIN sales.customers AS c
    ON c.customer_id = o.customer_id
JOIN sales.order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY o.order_id, o.order_no, c.full_name, o.status
ORDER BY o.order_no;
~~~

Expected result:

| `order_no` | `full_name` | `status` | `order_total` |
| --- | --- | --- | ---: |
| `SO-001` | Nguyễn An | `PAID` | 360,000 |
| `SO-002` | Trần Bình | `NEW` | 280,000 |

Verify row counts:

~~~sql
SELECT
    (SELECT count(*) FROM sales.customers) AS customers,
    (SELECT count(*) FROM sales.products) AS products,
    (SELECT count(*) FROM sales.orders) AS orders,
    (SELECT count(*) FROM sales.order_items) AS items;
-- Expected: 2, 3, 2, 3 if only this exact seed dataset was loaded.
~~~

An important learning lesson: **a query returning results does not mean all business data is completely valid**. Constraints enforce specific structural rules; business rules like "every `PAID` order must have a payment matching its total" require a payments model and additional logic.

### 5.5. Test a Constraint Violation Inside a Transaction

~~~sql
BEGIN;

INSERT INTO sales.products
    (sku, product_name, list_price, stock_qty)
VALUES
    ('BOOK-SQL', 'Duplicate SKU Record', 50000.00, 1);
-- ERROR 23505: unique_violation (SKU already exists).

ROLLBACK;
~~~

Because PostgreSQL places a transaction into an **aborted** state after most SQL errors, subsequent statements in the transaction are rejected until `ROLLBACK`. To catch and recover from an error inside a sub-part of a transaction, use `SAVEPOINT` and `ROLLBACK TO SAVEPOINT` before continuing.

**Stage 3 completion check:** loaded sample data, verified expected row counts, calculated order totals accurately, and explained error `23505` without leaving a broken session or committing bad data.

## 6. Stage 4 — Transactions, MVCC, and Concurrent Updates

PostgreSQL supports **ACID** transactions and uses **MVCC** (*multi-version concurrency control*) so concurrent reads and writes proceed according to isolation level. What a user observes depends on transaction timing, statement timing, and isolation level.

A classic scenario is two buyers purchasing the last remaining unit simultaneously. If the application merely:

1. Reads `stock_qty`.
2. Computes the new quantity in memory.
3. Overwrites the column with the new value.

then two threads can read the same stale stock, causing a **lost update** or overselling without proper concurrency control.

### 6.1. Conditional Atomic UPDATE

Instead of read-then-overwrite:

~~~sql
BEGIN;

UPDATE sales.products
SET stock_qty = stock_qty - 2
WHERE sku = 'MOUSE-01'
  AND is_active = TRUE
  AND stock_qty >= 2
RETURNING product_id, stock_qty;

-- Continue creating the order and line items in the same transaction
-- only when exactly one row is returned.

ROLLBACK;
~~~

With the initial seed data, this `UPDATE` returns one row with `stock_qty = 13`. `ROLLBACK` restores stock to 15 so the sample dataset stays intact. In real application code, if `RETURNING` yields zero rows, abort and roll back rather than creating the order.

`UPDATE ... WHERE stock_qty >= 2` executes within PostgreSQL's row-locking and condition-rechecking rules, preventing two concurrent requests from blindly subtracting from the same stale client-read quantity.

### 6.2. Every Multi-Step Business Flow Must Use One Transaction

Creating a new order involves:

~~~text
BEGIN
  validate request and business authorization
  conditionally deduct stock
  insert orders record
  insert order_items rows
  record payment/status if applicable
COMMIT once all steps succeed

If any critical step fails:
  ROLLBACK
~~~

Never run stock deduction and line-item insertion as separate autocommit transactions and expect atomicity. In JDBC, applications typically call `setAutoCommit(false)` on **one connection**, execute the SQL statements, and call `commit()` or `rollback()`.

### 6.3. Isolation Levels to Know

PostgreSQL accepts all four SQL-standard isolation names, though `READ UNCOMMITTED` behaves identically to `READ COMMITTED`. `READ COMMITTED` is the common default: each statement sees a snapshot as of statement start. `REPEATABLE READ` preserves a transaction-wide snapshot; `SERIALIZABLE` may ask the application to retry when it detects a pattern that cannot be serialized safely.

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

-- Business reads and writes here.

ROLLBACK;
~~~

This command only demonstrates syntax. Never turn on `SERIALIZABLE` globally while ignoring `SQLSTATE 40001` (*serialization_failure*). When a retryable error occurs, **retry the entire transaction** with bounded attempts, backoff, and idempotency if the flow performs writes.

### 6.4. Separating Deadlocks, Data Errors, and Connection Drops

| SQLSTATE | Common Meaning | Handling Direction |
| --- | --- | --- |
| `23505` | Unique key violation | Handle conflict or check request ID; never retry blindly |
| `23503` | Foreign key violation | Fix referenced data or operation order |
| `23514` | CHECK constraint violation | Fix invalid value |
| `40001` | Serialization failure | Roll back and retry entire transaction if safe |
| `40P01` | Deadlock detected | Roll back and perform bounded full-transaction retry |
| `55P03` | Lock not available | Check lock/timeout policy, roll back as needed |
| `57014` | Query canceled, e.g. statement timeout | Identify root cause and transaction state |
| `08xxx` class | Connection / communication error | Discard broken connection, verify transaction outcome |

If a connection drops **right at COMMIT**, the application may not know whether the server committed. Never automatically resend a brand-new write with a new key: use an **idempotency key** and query durable state before deciding success or failure.

**Stage 4 completion check:** can explain why an entire workflow must roll back when one step fails, and when to use conditional updates, locks, and retries instead of relying solely on Java input validation.

## 7. Stage 5 — Application Connectivity and Versioned Schema Migrations

A Java program or web service should never use a privileged admin role merely to execute `SELECT` and `INSERT`. At minimum, separate:

- An **admin/migration** role allowed to alter schemas.
- An **application** role with only required DML privileges.
- A **reporting** role restricted to `SELECT` on approved tables or views.

### 7.1. Java Connectivity via JDBC and Connection Pooling

Example PostgreSQL JDBC URL:

~~~text
jdbc:postgresql://db.example.internal:5432/shop_learning
~~~

In applications, use a `DataSource` backed by a properly configured connection pool (such as HikariCP). Never open a fresh TCP connection per SQL statement under load. Key configuration parameters include:

- Pool size relative to `max_connections`, app instance count, and database resources.
- Connection acquisition timeout, connect timeout, statement timeout, and API deadlines.
- TLS, secret rotation, hostname verification, and network rules.
- Returning connections to the pool after every request, even on exceptions.
- Transaction hygiene: roll back before returning a connection to the pool if business logic fails.

Minimal JDBC pattern:

~~~java
try (Connection con = dataSource.getConnection()) {
    con.setAutoCommit(false);

    try (PreparedStatement ps = con.prepareStatement(
            "UPDATE sales.products " +
            "SET stock_qty = stock_qty - ? " +
            "WHERE sku = ? AND stock_qty >= ? " +
            "RETURNING product_id")) {

        ps.setInt(1, 2);
        ps.setString(2, "MOUSE-01");
        ps.setInt(3, 2);

        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                throw new IllegalStateException("Insufficient stock");
            }
        }
    }

    // Transaction illustration: do not persist changes.
    con.rollback();

} // Closes connection / returns to pool per DataSource.
~~~

`PreparedStatement` separates parameters from SQL syntax, reducing SQL injection risk compared to concatenating raw input into SQL strings. It does not replace user authentication, authorization, and business validation.

For multi-step transactions, catch exceptions to roll back explicitly. This condensed example intentionally rolls back for demonstration; in production logic, manage all error paths and log rollback failures rather than swallowing them.

### 7.2. Migrations: Versioned Schema Evolution

During early prototyping, manual SQL table edits are common. Once multiple environments exist, move DDL into **versioned migrations** managed by tools like Flyway, Liquibase, or an equivalent workflow.

Syntactically safe change example:

~~~sql
ALTER TABLE sales.products
ADD COLUMN description TEXT;
~~~

In PostgreSQL, many DDL operations can run inside a transaction and roll back on failure. Still, do not assume every DDL command runs in a transaction: certain commands, such as `CREATE INDEX CONCURRENTLY`, **cannot run inside an explicit transaction block**.

Example when the orders table is large and you want to speed up queries while minimizing write blocking:

~~~sql
CREATE INDEX CONCURRENTLY idx_orders_customer_created
ON sales.orders (customer_id, created_at DESC);
~~~

`CONCURRENTLY` carries its own costs and preconditions, can take longer, and needs monitoring. If it fails, PostgreSQL may leave behind an invalid index requiring deliberate cleanup. Never treat `CONCURRENTLY` as a magic keyword guaranteeing "zero locks and zero risk."

Reliable migration workflow:

1. Store each schema change under a unique version in source control.
2. Dry-run against representative data, checking indexes, constraints, and old/new code compatibility.
3. Structure breaking changes as multi-step **expand → migrate data → switch code → contract** rollouts.
4. Set appropriate `lock_timeout` and `statement_timeout` for evaluated migrations so DDL never blocks production traffic indefinitely waiting for a lock.
5. Verify backups/recoverability, have a mitigation plan, and monitor after deployment.

Never patch DDL directly in production and forget to update migration scripts; environments will drift into inconsistent schemas.

**Stage 5 completion check:** app does not use superuser; uses a `DataSource`, explicit transaction boundaries, prepared statements, and a versioned migration pipeline tested on staging.

## 8. Stage 6 — Securing Access: Roles, GRANT, `pg_hba.conf`, and TLS

PostgreSQL enforces authorization via **roles** and **GRANT/REVOKE**. Being able to log in does not mean a role can read or alter any table.

### 8.1. Read-Only Reporting Role

Run the following SQL using a role owning the database/schema or holding appropriate admin privileges in the lab environment:

~~~sql
CREATE ROLE shop_reader LOGIN;

GRANT CONNECT ON DATABASE shop_learning TO shop_reader;
GRANT USAGE ON SCHEMA sales TO shop_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA sales TO shop_reader;
~~~

In `psql`, set the password interactively rather than writing plaintext passwords in SQL files:

~~~text
\password shop_reader
~~~

`\password` is a `psql` meta-command. In environments using other auth methods like IAM or secret managers, manual password setting may be unnecessary—just ensure the role authenticates via an approved method.

Granting privileges on **existing tables** does not automatically apply to future tables. To allow the reporting role to read future tables created by **the same role that owns the current tables**, configure default privileges while connected as that table-creating/owning role:

~~~sql
ALTER DEFAULT PRIVILEGES IN SCHEMA sales
GRANT SELECT ON TABLES TO shop_reader;
~~~

**Default privileges depend on the role creating the object.** If migrations run under a different role than the one that ran `ALTER DEFAULT PRIVILEGES`, newly created tables will not inherit those grants. In production, declare privileges explicitly tied to the object-owning role and manage them via deployment scripts.

### 8.2. Least-Privilege Guidelines

| Account Type | Recommended Privileges | Should Not Have by Default |
| --- | --- | --- |
| Read-only app | `CONNECT`, schema `USAGE`, matching `SELECT` | Schema modify/drop privileges, superuser |
| Read-write app | `SELECT`/`INSERT`/`UPDATE`/`DELETE` on required tables | Arbitrary `CREATE`/`DROP`, role management |
| Migration/owner | Alter objects it owns, grant required access | Long-lived use in live app request paths |
| System admin role | Controlled and audited operational access | Direct use by everyday HTTP requests |

A write-enabled app should hold only the privileges its workflows require; across multiple services, avoid sharing a single database credential.

### 8.3. `pg_hba.conf`, Networking, and Encryption

`pg_hba.conf` controls **which client addresses can connect to which databases, as which roles, and with which authentication methods**. Strong methods like SCRAM-SHA-256 are standard; never expose `trust` authentication on public networks or broadly across all users.

For secure remote connectivity:

- Restrict `listen_addresses` and firewalls/security groups to only required interfaces and subnets.
- Enforce TLS over untrusted networks; verify server certificates per your security model.
- Store and rotate credentials in a secret manager or secure store—never commit passwords to Git.
- Apply least privilege, audit schema ownership, and lock down `search_path`.
- Log logins, privilege changes, and critical operations per security policy.

Editing a config file alone does not guarantee security: verify the config was reloaded properly, unauthorized connections are rejected, and allowed connections enforce valid TLS and authentication.

**Stage 6 completion check:** reporting role reads required data yet cannot `UPDATE`; unauthorized connections are denied; application accounts have neither schema-creation nor superuser privileges.

## 9. Stage 7 — Fast Queries and Measuring with EXPLAIN

PostgreSQL uses its **planner** to pick data access paths. As tables grow, a correct query can turn slow due to large scans, missing indexes, suboptimal joins, or stale statistics.

Example filtering one customer's orders chronologically:

~~~sql
EXPLAIN
SELECT order_no, created_at, status
FROM sales.orders
WHERE customer_id = (
    SELECT customer_id
    FROM sales.customers
    WHERE email = 'an@example.test'
)
ORDER BY created_at DESC;
~~~

On a table with only a few rows, the planner picks a sequential scan because it is cheapest. That is **not a bug**. As data grows, consider an index:

~~~sql
CREATE INDEX idx_orders_customer_created
ON sales.orders (customer_id, created_at DESC);
~~~

If you already created an index with this name in the migration section earlier, **do not run this statement again**; both illustrate the same index structure, with the migration example using `CONCURRENTLY`. Choose one based on your current schema state.

To inspect actual runtime and row counts on a safe `SELECT` query:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_no, created_at, status
FROM sales.orders
ORDER BY created_at DESC;
~~~

Key distinctions:

- `EXPLAIN` shows only the estimated plan without executing the query to collect runtime stats.
- `EXPLAIN (ANALYZE, BUFFERS)` **actually executes the query** and records runtime metrics. On write statements, it actually modifies data—never run it recklessly in production.
- Estimated vs. actual row counts at each node can diverge; large gaps suggest checking statistics, data skew, or predicates.
- Sequential scans are not always bad, especially when reading most of a table.

On large tables, `ANALYZE` updates planner statistics:

~~~sql
ANALYZE sales.orders;
~~~

Autovacuum includes autoanalyze automatically. You do not need to run `ANALYZE` manually after every `INSERT`; run it for operational reasons such as right after a large bulk load or when row estimates drift badly.

### 9.1. Indexes Are Tools, Not "More Is Always Better"

Every index consumes space and adds maintenance overhead on `INSERT`, `UPDATE`, and `DELETE`. The right workflow is:

1. Identify slow or high-impact queries from logs or metrics.
2. Measure execution plans on representative data.
3. Design indexes targeting filters, joins, and sort orders.
4. Re-measure row counts, buffers, and latency.
5. Monitor impact on write throughput, storage size, and maintenance overhead.

Concluding "adding an index always makes queries faster" from a three-order toy table has zero validity in production.

**Stage 7 completion check:** can read `Seq Scan`, `Index Scan`/`Index Only Scan`, recognize join order and estimated rows, and re-measure after SQL or index changes.

## 10. Stage 8 — Understand VACUUM, Statistics, and Maintenance

PostgreSQL uses MVCC: when rows are updated or deleted, older versions must be retained temporarily for active transactions that still need to see them. Obsolete versions must eventually be cleaned up, otherwise tables bloat and query efficiency degrades.

**VACUUM** reclaims space inside tables for reuse and maintains tuple visibility metadata. **ANALYZE** updates planner statistics. PostgreSQL runs **autovacuum** to automate these tasks per policy; never disable it merely because you see disk I/O.

Diagnostic commands:

~~~sql
SHOW autovacuum;

SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'sales'
ORDER BY relname;
~~~

`n_live_tup` and `n_dead_tup` are **statistical estimates**, not exact per-row counts. `last_autovacuum` and `last_autoanalyze` show when automatic runs completed, though they must be interpreted alongside transaction age, workload, and table size.

### 10.1. Why Do Long-Open Transactions Pose Risks?

A long-running read or write transaction delays removing old row versions that older snapshots might still need. Consequences include **bloat**, higher I/O, storage growth, and vacuum pressure. Keep transactions brief—never hold one open waiting on user input or slow HTTP calls.

Inspect open transactions:

~~~sql
SELECT
    pid,
    usename,
    state,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Visibility of other sessions' details may be restricted by role; never grant overly broad monitoring privileges just to run an exercise.

### 10.2. `VACUUM` vs. `VACUUM FULL`

| Operation | Characteristics | Notes |
| --- | --- | --- |
| Autovacuum | Automated background cleanup of dead versions, stats updates, and maintenance | Monitor and tune per workload; never disable lightly |
| `VACUUM table` | Reclaims dead versions and frees reusable space inside the relation | Does not guarantee shrinking OS file size proportionally |
| `ANALYZE table` | Collects planner statistics | Does not clean up dead tuples |
| `VACUUM (ANALYZE) table` | Combines dead-tuple cleanup and statistics refresh | Incurs I/O cost |
| `VACUUM FULL table` | Rewrites the entire table to reclaim physical disk space when justified | Takes heavy exclusive locks, requires extra free disk space and maintenance planning |

Never schedule `VACUUM FULL` as a routine daily job on hot tables: its exclusive lock and rewrite cost can severely disrupt service. PostgreSQL also enforces **transaction ID wraparound** prevention, tying vacuum directly to database safety—monitor transaction age warnings and maintenance thresholds for your environment.

**Stage 8 completion check:** understands why tables grow after heavy `UPDATE`/`DELETE`, can monitor autovacuum and long-running transactions, and knows `VACUUM` does not delete live user data.

## 11. Stage 9 — Backups Must Always Be Paired with Restore Drills

A backup is not true protection until you know **what point you can restore to, how long it takes, and have tested restoring it**. Two critical operational targets:

- **RPO (Recovery Point Objective):** maximum acceptable data loss if a disaster strikes.
- **RTO (Recovery Time Objective):** maximum acceptable time to restore service.

For example, a 15-minute RPO and 1-hour RTO are business requirements—you cannot meet them with a daily `pg_dump` cron job alone.

### 11.1. Logical Backups with `pg_dump`

`pg_dump` creates a consistent logical backup of one database, for example in custom archive format:

~~~bash
pg_dump \
  -h 127.0.0.1 -p 5432 -U postgres \
  -d shop_learning \
  -F c \
  -f shop_learning.dump
~~~

With `-F c`, output uses custom format, suitable for selective or full restores with `pg_restore`. `pg_dump` backs up **only the specified database**; it does not replace cluster configuration, global roles, tablespaces, or continuous WAL archiving.

Inspect the archive table of contents:

~~~bash
pg_restore -l shop_learning.dump
~~~

**Never overwrite a production database to "test a backup."** Create a separate database in a test environment:

~~~bash
createdb -h 127.0.0.1 -p 5432 -U postgres shop_restore_test

pg_restore \
  -h 127.0.0.1 -p 5432 -U postgres \
  -d shop_restore_test \
  --no-owner --no-privileges \
  --exit-on-error \
  shop_learning.dump
~~~

Then connect to `shop_restore_test` to verify table counts, foreign keys, row counts, and application queries. `--no-owner`/`--no-privileges` help when restoring into a test environment lacking original roles; real environments need proper ownership and privilege policies rather than always stripping permissions.

### 11.2. Post-Restore Verification

~~~sql
SELECT
    (SELECT count(*) FROM sales.customers) AS customers,
    (SELECT count(*) FROM sales.products) AS products,
    (SELECT count(*) FROM sales.orders) AS orders,
    (SELECT count(*) FROM sales.order_items) AS items;
~~~

With the lesson seed dataset, expect `2, 3, 2, 3`. If the source processed more transactions after the dump ran, compare against **state as of dump time**, not days-later live production counts.

Also verify the application can connect and run critical queries, constraints exist, indexes are built, and core workflows run cleanly. Listing contents from a backup file does not prove every object and extension restores cleanly enough to run the app.

### 11.3. PITR: Base Backups and WAL Chains

`pg_dump` is a point-in-time logical snapshot. To recover **to an arbitrary timestamp** (Point-In-Time Recovery, PITR), PostgreSQL needs a valid **base backup** plus an **unbroken chain of archived WAL segments** to replay up to the target point.

~~~mermaid
flowchart LR
    A["Base backup at T0"] --> B["WAL archive T0 → T1"]
    B --> C["WAL archive T1 → T2"]
    C --> D["Restore base backup + replay WAL"]
    D --> E["Data state at target time T"]
~~~

`pg_basebackup`, `archive_mode`, `archive_command`, WAL retention, archive storage location, and recovery parameters must match your PostgreSQL version and infrastructure. If even one required WAL segment is missing, lost transactions cannot be reconstructed from the base backup alone. Monitor archiving, drill PITR, and maintain runbooks before claiming RPO compliance.

**Backups must be protected:** encrypt at rest and in transit where appropriate, restrict read access, store isolated from the primary host, enforce retention, and verify readability. A backup sitting on the same failing disk as the primary fails against hardware failure or ransomware.

**Stage 9 completion check:** scheduled backups plus verified restore evidence in an isolated environment, knowing exactly what data and points in time the procedure can recover.

## 12. Stage 10 — Monitoring, Alerting, and Incident Response

A reliable service surfaces issues **before users hit mass errors**. Observability combines PostgreSQL system views, server logs, host metrics, connection pool stats, and infrastructure monitoring.

### 12.1. Metric Categories to Track

| Category | Useful Metrics | Warning Signs to Investigate |
| --- | --- | --- |
| Availability | Successful connections, latency, connection errors | Connection failures, rising `08xxx`, pool exhaustion |
| Resources | CPU, RAM, disk usage, I/O latency | Disk nearing full, sustained I/O stalls, swapping |
| Transactions | Commits/rollbacks, transaction duration, long-open count | Spike in rollbacks, long-held snapshots/locks |
| Queries | Slow queries, rows scanned, runtime and call rate | Sudden endpoint latency spike |
| Locks | Lock waits, deadlocks, wait durations | Deadlocks or growing lock queues |
| Data health | `n_dead_tup`, autovacuum activity, table/index sizes | Bloat, lagging vacuum, rising transaction ID age |
| Backups | Latest backup status, restore drill recency, WAL archive | Failed backups or broken WAL archive chain |
| Replicas (if any) | Replay lag, receiver/apply state, replication slots | Lagging replica or excessive WAL retention |

### 12.2. Simple Diagnostic Queries

Current database metrics:

~~~sql
SELECT
    datname,
    numbackends,
    xact_commit,
    xact_rollback,
    blks_read,
    blks_hit,
    deadlocks
FROM pg_stat_database
WHERE datname = current_database();
~~~

These counters are **cumulative totals since statistics reset**, not per-second rates. Monitoring tools must sample deltas over time and handle counter resets.

Inspecting active and waiting sessions:

~~~sql
SELECT
    pid,
    usename,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start NULLS LAST;
~~~

Interpret `wait_event_type` and `wait_event` alongside session `state`; an `idle` session is not executing SQL. Never blindly terminate backends or kill sessions serving critical transactions without assessing impact.

### 12.3. Set Intentional Alert Thresholds

Examples:

- Data or WAL disk usage exceeds a safe threshold.
- No successful backup within the policy window.
- Most recent restore verification is too old.
- Connection pool frequently waits or PostgreSQL nears `max_connections`.
- Rising deadlocks, long transactions, or sustained replica lag.
- Repeated `archive_command` failures preventing WAL archiving.

Never apply a single blanket threshold to every environment; write-heavy transactional systems and read-heavy reporting systems have very different load signatures.

### 12.4. Incident Response Runbook

A minimal runbook should document:

1. **Symptoms and scope:** all endpoints or one query, primary or replica, when did it start?
2. **Current state:** connections, logs, disk, active transactions, locks, WAL, and backups.
3. **Safe initial actions:** shed or pause abusive load if needed, curb retries, preserve logs, confirm backup status.
4. **Intervention decisions:** roll back migration, scale resources, carefully terminate blocking sessions, fail over, or restore per prepared plan.
5. **Recovery verification:** business queries, latency, metrics, and write health restored.
6. **Post-incident review:** root cause, impact, monitoring gaps, and corrective actions.

**Stage 10 completion check:** dashboards exist, alerts are tested, and another teammate can follow the runbook to diagnose common incidents.

## 13. Stage 11 — Replication and High Availability Do Not Replace Backups

When one PostgreSQL instance can no longer satisfy availability targets, build a **primary–standby** setup using physical streaming replication. The primary ships WAL; standbys receive and replay changes to maintain a near-real-time copy.

~~~mermaid
flowchart LR
    A["App writes"] --> P["Primary PostgreSQL"]
    P -->|"WAL streaming"| S["Standby PostgreSQL"]
    B["App reads"] --> S
    C["Backups + WAL archive"] -. "independent recovery" .-> P
~~~

Key principles to remember:

- Default replication is often **asynchronous**; transactions committed on the primary may not have reached the standby before a sudden primary failure.
- Standbys reduce downtime and offload reads when architected properly, yet replica reads can return slightly stale data.
- **Failover requires orchestration and fencing** to prevent two primaries from accepting writes simultaneously (*split-brain*).
- Replication **does not replace backups**: accidental deletes or bad updates on the primary replicate rapidly to standbys.
- Replication slots retain WAL if a consumer stalls or stops; monitor disk usage and manage slot lifecycles.
- When enabling synchronous replication for stronger guarantees, understand the trade-offs in commit latency, availability if standbys disconnect, and commit settings.

Inspecting on the primary:

~~~sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
~~~

On a standby, inspect WAL receive status via `pg_stat_wal_receiver` and recovery mode via `pg_is_in_recovery()`. Never look at a single lag metric and assume every transaction is safe; explicitly define read-after-write needs, RPO, and failover procedures.

**Stage 11 completion check:** can distinguish backup, replication, and failover; has a role-promotion plan and tested application reconnection when the primary fails.

## 14. Milestone-Based Practice Roadmap

The table below is a **suggested learning plan**, not a rigid timeline for everyone. Pace varies with prior experience and system complexity.

| Stage | Core Practice | Evidence of Mastery |
| --- | --- | --- |
| **Foundations** | `psql`, cluster/database/schema, roles, table creation | Connected and created `shop_learning.sales`; accurately describes each tier |
| **Correct Data** | `PRIMARY KEY`, `UNIQUE`, FK, `CHECK`, seed, `JOIN`/`GROUP BY` | Four constrained tables; computes both sample order totals accurately |
| **Concurrency** | `BEGIN`/`COMMIT`/`ROLLBACK`, conditional updates, isolation | Tests stock update with rollback; distinguishes retryable errors |
| **Integration** | JDBC, pooling, prepared statements, migrations | App uses dedicated non-admin role; schema is version-controlled |
| **Performance** | `EXPLAIN`, indexes, `ANALYZE`, statistics | Captures before/after plan measurements on target queries |
| **Security** | `GRANT`/`REVOKE`, `pg_hba.conf`, TLS | Read-only reporting role enforced; no credentials in source code |
| **Recovery** | `pg_dump`/`pg_restore`, backup policies, PITR | Restores into an isolated database and reconciles counts/queries |
| **Operations** | Monitoring, vacuum, locks, WAL, runbooks | Basic alerts firing; teammates can follow the runbook |
| **High Availability** | Primary–standby, replication, failover | Completed failover drill with measured RPO/RTO |

### 14.1. Four Gateways Before Promoting Environments

**Before leaving local development:**

- Can someone else initialize the database from migrations and seeds without undocumented manual steps?
- Do database constraints block invalid inputs?
- Does the app roll back the whole business flow if one SQL statement in the chain fails?
- Are app credentials separated from administrative accounts?

**Before staging handles production-like data:**

- Are migrations backward-compatible with the currently running application version?
- Have heavy queries been measured against representative data volumes?
- Are backups, restore drills, and least-privilege access controls in place?
- Do dashboards track connection errors, locks, and disk usage?

**Before going live:**

- Have RPO and RTO been agreed upon with stakeholders?
- Has a restore test from a **real backup** succeeded in an isolated environment?
- Is there a rollback plan and clear owner for app/migration deployments?
- Are alerts configured for disk space, replication (if used), backups, long transactions, and connection exhaustion?

**After going live:**

- Who is on-call for incidents and who is authorized to intervene in the database?
- How often are backups, restores, and version upgrades tested?
- Is there active monitoring of autovacuum, bloat, WAL archiving, and transaction ID age?
- Are roles, schema migrations, and slow queries reviewed periodically?

## 15. Common Pitfalls on the PostgreSQL Learning Path

| Misconception | What to Remember |
| --- | --- |
| "Creating a database means the system is ready" | Initialization is step one; you still need integrity, backups, security, and observability |
| "A PostgreSQL schema is another database" | A schema is a namespace **inside** a database |
| "Having a `FOREIGN KEY` means all business logic is valid" | FKs protect links, not totals, inventory rules, or state workflows |
| "`UNIQUE` and checking via SELECT are equivalent" | Pre-insert SELECTs still suffer race conditions; UNIQUE enforces atomically in the DB |
| "After an SQL error, the transaction recovers automatically" | Most errors abort the transaction until `ROLLBACK` or savepoint recovery |
| "Adding an index always speeds up queries" | Indexes consume disk and add write overhead; verify with execution plans |
| "`EXPLAIN ANALYZE` only inspects metadata" | It runs the query; on write statements it modifies data |
| "Long transactions hurt nobody" | They hold locks, pin snapshots, and block vacuum |
| "`VACUUM` always shrinks files on disk" | Standard VACUUM frees internal reusable space; `VACUUM FULL` trades heavy locks and I/O |
| "Having a dump file means no restore test is needed" | Only an actual restore verifies recoverability in the target environment |
| "Having replicas means no backups are needed" | Logic bugs and accidental deletes replicate straight to replicas |
| "Using superuser for the app is convenient" | Any bug or leaked credential gains unnecessarily destructive blast radius |
| "Setting a password is enough connection security" | Also restrict networks, auth methods, TLS, privileges, and secret management |
| "SQL passing locally guarantees production safety" | Data scale, concurrency, statistics, and resources can differ dramatically |

## 16. Comprehensive Self-Assessment Exercises

### Exercise 1 — Add a Linked Table

Add `sales.payments` with an identity primary key `payment_id`, `order_id` referencing orders, positive `paid_amount NUMERIC(12,2)`, and `paid_at TIMESTAMPTZ` defaulting to `now()`. Decide whether business rules allow **one or multiple** payments per order; if one, declare `UNIQUE (order_id)`. Explain how this choice affects installment payments and refunds.

### Exercise 2 — Catch Invalid Inputs

Attempt inserting a product with `stock_qty = -5`, an order referencing a nonexistent `customer_id`, and a line item with `order_items.quantity = 0`. Record each returned SQLSTATE. Run in a test environment and use `ROLLBACK` after errors.

### Exercise 3 — Explain Transaction Abort

Inside a transaction with two DML statements, the first succeeds and the second violates `UNIQUE`. How does PostgreSQL respond if you issue a third statement right after the error? When should you use `ROLLBACK` versus `SAVEPOINT`? What happens if the app ignores the error and calls `COMMIT`?

### Exercise 4 — Configure Two User Roles

Create a read-only role for `sales` and an application role with write access to specific tables. Explain how database `CONNECT`, schema `USAGE`, and table `SELECT`/`INSERT` privileges differ. Verify the read-only role cannot update `sales.products`.

### Exercise 5 — Measure Before and After an Index

Generate larger test volume in a **lab environment** and run `EXPLAIN (ANALYZE, BUFFERS)` for a query looking up orders by `customer_id`. Add an appropriate index, re-measure row counts, runtime, and buffers, and note any impact on inserts.

### Exercise 6 — Simulate Data Loss

Create a `pg_dump` backup, restore into a new database, and verify row counts and order-total queries. Write a brief runbook covering: where backups live, who can read them, exact restore commands, success criteria, and fallback steps if a backup file is corrupt.

### Exercise 7 — Minimal Operations Plan

For a Java service backed by PostgreSQL, outline:

- Connection pool sizing and timeout limits.
- Signals indicating slow queries, deadlocks, and low disk space.
- Backup policy, retention, and restore drill schedule.
- Migration rollout workflow controlling lock impact.
- Criteria deciding when standby replicas and failover are needed.

The goal is not picking arbitrary "universal numbers," but explaining **why chosen values match the workload, resources, and business requirements**.

## 17. Conclusion: What Safe PostgreSQL Looks Like

The starting point is creating a database, a schema, and a few tables. Yet PostgreSQL only becomes a truly dependable operational platform when built in layers: **data constraints**, **proper transactions**, **least-privilege access**, **controlled migrations**, **measured query performance**, **vacuum and monitoring**, **restore-verified backups**, and **incident runbooks**.

A strong learning roadmap does not stop at memorizing `CREATE TABLE` or `SELECT` syntax. It equips you to answer: "What happens if two write requests arrive simultaneously?", "How do we recover if a migration goes wrong?", "What data could be lost if the primary dies?", and "Who is allowed to read or modify this data?"

Once you can prove those answers through constraints, queries, transactions, privileges, and an actual tested restore, your database has moved far beyond **"works on my laptop"**: it has the foundation to **run PostgreSQL safely, observably, and recoverably**.
