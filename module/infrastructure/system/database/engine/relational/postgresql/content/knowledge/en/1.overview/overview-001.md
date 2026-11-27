# What Is PostgreSQL and the Role of a Relational Database Management System

When building a sales application, student management system, or payment processing service, developers need more than just a place to store records. The system must also answer harder questions: **How do we prevent an order from referencing a nonexistent customer? How can two users update data concurrently without corrupting the result? What happens if the server loses power mid-transaction? And how do we quickly find a few hundred rows among millions?**

**PostgreSQL** is an open-source relational database management system, commonly referred to as **Postgres**. It provides structured storage, the SQL query language, integrity constraints, transactions, concurrency control, indexing, access control, and operational tools to help applications handle data reliably.

This lesson introduces PostgreSQL from the perspective of learning **Database Engine Relational PostgreSQL**: what a relational database management system does, how PostgreSQL operates, how it differs from a data file or a SQL library, and when to choose it for a production system.

## 1. Three Commonly Confused Concepts: Data, Database, and DBMS

Before exploring PostgreSQL, let us distinguish these terms:

| Concept | Meaning | Example |
|---|---|---|
| **Data** | Values representing events or entities | Customer named An, order number 101 |
| **Database** | An organized collection of data for access and management | Customer, product, and order data of an application |
| **Database Management System (DBMS)** | Software that manages storing, reading, modifying, protecting, and ensuring the integrity of data | PostgreSQL |
| **RDBMS** | A DBMS built on the relational model | PostgreSQL, MySQL, SQL Server |
| **SQL** | A declarative language for defining, querying, and modifying relational data | `SELECT`, `INSERT`, `CREATE TABLE` |

**PostgreSQL is not a SQL statement or merely a `.sql` file.** It is a software system running on a server that receives application requests, plans execution, accesses data, and maintains many guarantees that a plain text file does not inherently provide.

Picture an application:

~~~text
                       USER
                        |
                        v
               Web/Mobile Application
                        |
                  SQL via driver
                        |
                        v
                PostgreSQL Server
                /       |       \
          Queries  Transactions  Permissions
             |          |          |
             +----------+----------+
                        |
                        v
                Tables and Indexes
                        |
                        v
                Durable Storage
~~~

Users do not need to know which disk page holds a row. The application describes the data to retrieve using SQL; PostgreSQL is responsible for locating, reading, validating, and returning results according to granted privileges.

## 2. What Is PostgreSQL?

PostgreSQL is an open-source **object-relational database management system (ORDBMS)**. At its core, it follows the relational model and uses SQL. Beyond traditional relational data types and features, PostgreSQL also supports extensible data types, functions, operators, extensions, and a wide range of customizations.

Key characteristics:

- **Open source:** can be used, studied, and developed under the PostgreSQL project's license.
- **Client–server architecture:** multiple applications and connections access the same PostgreSQL server.
- **SQL-based:** create tables, define constraints, query across multiple tables, aggregate, update, and delete data.
- **Transactional:** group changes into a unit that can be committed with `COMMIT` or rolled back with `ROLLBACK`.
- **Concurrency and recovery mechanisms:** MVCC, locks, WAL, and consistency checks.
- **Indexes and query optimizer:** help choose an appropriate data access path.
- **Access control:** roles and privileges on databases, schemas, tables, and other objects.
- **Extensibility:** rich built-in data types, extensions, user-defined functions, and ecosystem tools.

PostgreSQL is commonly used for online transaction processing (OLTP) applications, enterprise business systems, web APIs, analytical services, geospatial storage, and systems requiring strict control over relational data.

"PostgreSQL supports many features" should not be misunderstood as "PostgreSQL automatically fits every workload." Data structure, query patterns, latency requirements, write load, operations, and team capabilities still determine the right technology choice.

### 2.1. PostgreSQL and the Name Postgres

The two names **PostgreSQL** and **Postgres** are commonly used to refer to the same database management system. PostgreSQL is the official project and product name; Postgres is the common shorthand.

When reading documentation or configurations, you may encounter names such as:

~~~text
PostgreSQL server
postgres                 (common server binary name)
psql                     (command-line client program)
postgresql.conf          (server configuration file)
pg_hba.conf              (client authentication configuration)
PGDATA                   (data directory of an instance/cluster)
~~~

These names refer to different components, not synonyms for a single SQL statement.

## 3. What Problem Does the Relational Model Solve?

In the relational model, data is represented as **relations**; in SQL implementations, these are typically organized into **tables** consisting of **rows** and **columns**.

Suppose an application manages orders:

~~~text
customers
+-------------+-----------------+
| customer_id | customer_name   |
+-------------+-----------------+
|           1 | An              |
|           2 | Bình            |
+-------------+-----------------+

orders
+----------+-------------+---------+
| order_id | customer_id | status  |
+----------+-------------+---------+
|      101 |           1 | paid    |
|      102 |           1 | pending |
|      103 |           2 | paid    |
+----------+-------------+---------+
~~~

Here:

- Each row in `customers` represents one customer.
- Each row in `orders` represents one order.
- `customer_id` in `orders` identifies the customer who owns the order.
- One customer can have **many orders**, while each order belongs to one customer in this model.

That relationship can be enforced with a **foreign key** to prevent inserting an order that points to a nonexistent customer.

~~~text
customers.customer_id
        |
        | 1 ---- N
        v
orders.customer_id
~~~

The relational model helps **separate data into meaningful entities**, avoids excessive duplication, and enables combining them using joins (`JOIN`).

### 3.1. Not Every "Table" Is a CSV File

A CSV file also has rows and columns, but it does not natively provide mechanisms such as:

- Primary key and foreign key constraints enforced by the engine.
- Multi-statement transactions that can roll back consistently.
- Concurrency control across multiple users.
- Specialized indexes to accelerate lookups.
- Per-user or per-object access privileges.
- Write-ahead logging and crash recovery procedures.

CSV can be used for export/import or data exchange, but a system with concurrent writes and complex relationships usually needs far more than reading and writing a flat file.

## 4. Core Building Blocks of Relational Data

### 4.1. Tables, Rows, Columns, and Data Types

A table defines its columns and accepted data types:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Meaning:

| Element | Purpose |
|---|---|
| `BIGINT` | Large-range integer |
| `TEXT` | Text string |
| `TIMESTAMPTZ` | Point in time with time zone semantics, displayed according to the session time zone |
| `NOT NULL` | Disallows `NULL` values |
| `PRIMARY KEY` | Primary key that uniquely identifies each row |
| `UNIQUE` | Disallows duplicate non-null values under standard unique rules |
| `GENERATED ALWAYS AS IDENTITY` | PostgreSQL generates identifier values via the identity mechanism |
| `DEFAULT CURRENT_TIMESTAMP` | Default value is the current timestamp in the transaction context |

PostgreSQL supports many other types such as `BOOLEAN`, `NUMERIC`, `DATE`, `UUID`, `JSONB`, arrays, ranges, geometric types, and user-defined types.

### 4.2. Primary Key

A **primary key** is a column or set of columns used to uniquely identify each row. In PostgreSQL, a primary key constraint enforces both `NOT NULL` and uniqueness.

Example:

~~~sql
PRIMARY KEY (customer_id)
~~~

You cannot insert a customer with an already existing `customer_id` into the same table unless an appropriate conflict-handling clause is used.

Primary keys are also frequently used in queries that look up an exact record:

~~~sql
SELECT customer_name
FROM customers
WHERE customer_id = 1;
~~~

### 4.3. Foreign Key

A foreign key enforces the relationship between a child table and a parent table:

~~~sql
CREATE TABLE orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES customers(customer_id),
    order_status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

An order cannot reference a nonexistent customer, according to the declared constraint rules and checking timing.

This matters because multiple applications may access the same database. If each application only validates in application code without a table constraint, another write path can bypass the check or produce invalid data under concurrent access.

### 4.4. Other Constraints

Example of a products table:

~~~sql
CREATE TABLE products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL
        CHECK (unit_price >= 0),
    stock_qty INTEGER NOT NULL DEFAULT 0
        CHECK (stock_qty >= 0)
);
~~~

The `CHECK` constraints express rules for non-negative prices and non-negative stock quantities. `NUMERIC(12,2)` is suitable for decimal monetary examples requiring exact precision; modeling real-world currency also requires considering currency units, rounding rules, and additional domain attributes.

Not every business rule can or should be expressed solely with `CHECK`. Rules spanning multiple rows, multiple tables, or business workflows require choosing an appropriate design involving transactions, foreign keys, unique constraints, exclusion constraints, triggers, or application-level handling.

## 5. SQL: The Language for Working with PostgreSQL

**SQL (Structured Query Language)** is a declarative language: the author describes the desired data or operation rather than specifying individual disk page reads.

Core statement categories:

| Category | Examples | Purpose |
|---|---|---|
| Data Definition Language (DDL) | `CREATE`, `ALTER`, `DROP` | Define or modify structure |
| Data Manipulation Language (DML) | `INSERT`, `UPDATE`, `DELETE` | Insert, update, delete rows |
| Queries | `SELECT` | Read, filter, join, aggregate data |
| Transaction Control | `BEGIN`, `COMMIT`, `ROLLBACK` | Manage units of change |
| Access Control | `GRANT`, `REVOKE` | Grant or revoke privileges |

Example:

~~~sql
-- Insert a customer.
INSERT INTO customers (customer_name, email)
VALUES ('An', 'an@example.test');

-- Read the list.
SELECT customer_id, customer_name
FROM customers
ORDER BY customer_id;

-- Update email.
UPDATE customers
SET email = 'an.new@example.test'
WHERE customer_id = 1;

-- Delete a row (succeeds only if constraints allow).
DELETE FROM customers
WHERE customer_id = 1;
~~~

`WHERE` is critical for `UPDATE` and `DELETE`. Omitting `WHERE` can affect every row in the table, if the statement and privileges permit it.

### 5.1. PostgreSQL's SQL Implementation and Dialect Extensions

SQL follows a shared standard, but RDBMS engines have differing extensions, syntax, and behaviors. PostgreSQL provides features such as:

- `RETURNING` to retrieve values from inserted, updated, or deleted rows.
- `INSERT ... ON CONFLICT` to handle violations of an appropriate unique or exclusion arbiter.
- Type casting syntax `expression::type`.
- Operators and functions for `JSONB`, arrays, and ranges.
- `CREATE EXTENSION` to install extensions available on the server when permitted.

Do not assume a query written for MySQL, SQL Server, or SQLite will run unchanged on PostgreSQL. Differences can involve data types, identity columns, string concatenation, upsert syntax, `NULL` handling, or DDL behavior.

## 6. Client–Server Architecture: How Applications Talk to PostgreSQL

An application typically connects to PostgreSQL through a **driver** or client program.

~~~text
                 +------------------------+
                 |        Client          |
                 | Java / Python / Node   |
                 | psql / BI tool         |
                 +-----------+------------+
                             |
                     PostgreSQL protocol
                             |
                             v
                 +------------------------+
                 |   PostgreSQL server    |
                 |  authenticate conn     |
                 |  parse / plan / execute|
                 |  transaction / locks   |
                 +-----------+------------+
                             |
                 +-----------+------------+
                 |                        |
                 v                        v
           Buffer Cache             WAL + data files
          (shared buffers)            on storage
~~~

The client sends SQL and parameters; the server checks privileges, parses the statement, plans and executes it, and returns results or an error status.

PostgreSQL uses a traditional **one backend process per connection** architecture. Consequently, opening thousands of independent connections is not free. High-traffic applications typically use a **connection pool** to reuse connections and limit the number of active sessions.

### 6.1. Server, Database, Schema, Table: Four Distinct Layers

A PostgreSQL instance/cluster can serve multiple databases. Each database contains multiple schemas; each schema can contain tables, views, functions, and other objects.

~~~text
PostgreSQL instance/cluster
|
+-- database: app_db
|      |
|      +-- schema: public
|      |      +-- table: customers
|      |
|      +-- schema: sales
|             +-- table: orders
|             +-- view: order_summary
|
+-- database: analytics_db
       |
       +-- schema: public
              +-- table: metrics
~~~

A **database** is an important namespace and administrative boundary. A **schema** is a namespace within a database. `public` is a schema that commonly exists by default, while additional schemas help group objects and manage privileges.

In PostgreSQL, a normal SQL query within a connection accesses data in the database to which that connection is open. You cannot directly join `app_db.sales.orders` with `analytics_db.public.metrics` the way you join two schemas in the same database. If cross-database integration is truly needed, dedicated mechanisms such as FDW (Foreign Data Wrappers) or data synchronization are used.

A fully qualified table name within a database typically takes the form:

~~~sql
SELECT *
FROM sales.orders;
~~~

`sales` is the schema and `orders` is the table.

### 6.2. How `search_path` Affects Table Name Resolution

When you write:

~~~sql
SELECT * FROM orders;
~~~

PostgreSQL looks up the name `orders` across schemas according to the current **`search_path`**.

Inspect it:

~~~sql
SHOW search_path;
SELECT current_schema();
~~~

To avoid ambiguity in applications with multiple schemas or when writing privileged SQL, you can use qualified names `schema.table` or manage `search_path` with clear rules. This also relates to security for objects and functions resolved through namespaces.

## 7. Role 1: Storing Structured Data

An RDBMS helps an application store data according to a consistent model. Each table has column types, keys, and constraints, so writing data is more than appending text to the end of a file.

For example, PostgreSQL can reject:

~~~sql
INSERT INTO products
    (sku, product_name, unit_price, stock_qty)
VALUES
    ('BAD-001', 'Invalid product', -50000.00, 10);
~~~

If the table has `CHECK (unit_price >= 0)`, PostgreSQL will not allow a row violating this rule to be saved.

Similarly:

~~~sql
INSERT INTO customers (customer_name, email)
VALUES ('Bình', 'an@example.test');
~~~

can be rejected if `email = 'an@example.test'` already exists in a column with a `UNIQUE` constraint.

The engine's value is that **rules are enforced at a shared write point**, even when data comes from multiple applications, an admin script, or an import job.

### 7.1. PostgreSQL Does Not Replace Data Modeling

Having an RDBMS does not automatically make a data model good. If customer info, orders, items, and various statuses are stuffed into an arbitrary JSON column, the system will still struggle with constraints, querying, and maintenance.

Developers must determine:

- What key uniquely identifies an entity?
- How are one-to-many and many-to-many relationships represented?
- Which attributes are required versus nullable (`NULL`)?
- Which data should be normalized into separate tables?
- Which rules must PostgreSQL enforce?
- Which indexes do critical queries require?

The DBMS provides the tools; an **appropriate data model** remains a design responsibility.

## 8. Role 2: Querying and Combining Data

A major advantage of relational databases is **querying and combining multiple tables** without pulling all data into the application to assemble it manually.

Suppose you have `customers` and `orders` tables. To find which customer has which orders:

~~~sql
SELECT
    c.customer_name,
    o.order_id,
    o.order_status
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_name, o.order_id;
~~~

`JOIN` combines rows based on the relational condition. PostgreSQL chooses an appropriate execution strategy, such as nested loop, hash join, or merge join depending on the data and query.

### 8.1. Filtering, Sorting, and Limiting

~~~sql
SELECT
    order_id,
    customer_id,
    created_at
FROM orders
WHERE order_status = 'paid'
ORDER BY created_at DESC
LIMIT 20;
~~~

This statement describes the request: find paid orders, sort by most recent date, and return at most 20 rows. Without `ORDER BY`, the return order of SQL results is **not guaranteed**.

### 8.2. Aggregating Metrics

~~~sql
SELECT
    customer_id,
    COUNT(*) AS order_count
FROM orders
GROUP BY customer_id
HAVING COUNT(*) >= 2
ORDER BY order_count DESC;
~~~

`GROUP BY` groups rows by customer; `COUNT(*)` counts orders; `HAVING` filters groups with at least two orders.

These operations can be expressed concisely in SQL and executed by the server close to where the data is stored.

### 8.3. PostgreSQL Supports Highly Complex Queries

Beyond basic SQL statements, PostgreSQL also supports:

- Common Table Expressions (CTEs) with `WITH`.
- Window functions such as `ROW_NUMBER()`, `RANK()`, and `SUM() OVER (... )`.
- Recursive CTEs with `WITH RECURSIVE`.
- Subqueries, set operations, and various aggregations.
- Views to create named query interfaces.
- Materialized views to pre-store query results and refresh them via an appropriate mechanism.

However, a query that works is not necessarily optimal. The engine's role is planning and execution; developers still need an appropriate data model, indexes, and resource-aware usage.

## 9. Role 3: Managing Transactions with ACID

A **transaction** is a group of SQL operations managed by PostgreSQL as a consistent unit. A transaction can be confirmed with `COMMIT` or canceled with `ROLLBACK`.

Example transferring 100 balance units between two accounts:

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
~~~

This is an illustrative example: in a real financial system, you must check affected row counts, balances, transaction permissions, and appropriate concurrency conditions. Otherwise, two syntactically valid SQL statements can still record incorrect business data.

Transactions have four groups of properties commonly called **ACID**:

| Letter | Name | Practical Meaning |
|---|---|---|
| **A** | Atomicity | Transaction changes are committed as a single unit; on rollback, none of the transaction's changes are retained |
| **C** | Consistency | Declared constraints are preserved according to DBMS rules; business correctness also depends on application logic |
| **I** | Isolation | Concurrent transactions see and affect data according to the chosen isolation level |
| **D** | Durability | Committed transactions have storage and recovery mechanisms to survive crashes within the system's guarantees and configuration |

### 9.1. Why Is Rollback Needed?

Consider a two-step order placement:

1. Create the order.
2. Deduct product stock.

If step 2 fails, the system should not leave behind a confirmed order without deducting stock per business rules.

~~~sql
BEGIN;

-- Example assumes tables and keys already exist.
INSERT INTO orders (customer_id, order_status)
VALUES (1, 'pending');

UPDATE products
SET stock_qty = stock_qty - 1
WHERE product_id = 1
  AND stock_qty >= 1;

-- The application must inspect the UPDATE result before deciding.
-- If business conditions are met:
COMMIT;

-- If a critical step fails to meet requirements, use ROLLBACK.
~~~

**Key point to remember:** the condition `stock_qty >= 1` ensures the stock deduction only happens when the row meets the condition; however, if `UPDATE` affects **0 rows**, PostgreSQL does not automatically infer that "the order must be rolled back." The application must inspect the result and control the transaction.

### 9.2. PostgreSQL Supports DDL Inside Transactions

PostgreSQL allows many common DDL operations such as `CREATE TABLE` or `ALTER TABLE` inside a transaction and rolls them back if the transaction rolls back, with certain exceptions.

Example:

~~~sql
BEGIN;

CREATE TABLE temporary_design_demo (
    id BIGINT PRIMARY KEY
);

ROLLBACK;
~~~

After the rollback, the newly created table no longer exists as a committed change in the database.

Not every administrative command is allowed inside a transaction block. For example, `CREATE DATABASE` and certain special operations have their own restrictions. Do not assume that **every** PostgreSQL DDL or maintenance command can run inside `BEGIN ... COMMIT`.

## 10. Role 4: Handling Concurrency with MVCC and Locks

Imagine two staff members opening a customer profile at the same time while a third staff member updates the phone number. The system needs rules to prevent readers from seeing half-written data while preventing conflicting updates.

PostgreSQL uses **MVCC — Multi-Version Concurrency Control**, managing concurrent access through multiple versions of data.

Intuitive picture:

~~~text
Transaction A reads row H
        |
        +--> sees a version matching A's snapshot

Transaction B updates H
        |
        +--> creates a new state/version per MVCC rules

Transaction A continues reading
        |
        +--> what is visible depends on isolation level/snapshot
~~~

MVCC lets many read operations avoid blocking normal write operations, but that **does not mean PostgreSQL never uses locks**. Write operations still acquire row-level locks; DDL may require relation-level locks; certain SQL statements request explicit locking.

### 10.1. Transaction Isolation Levels

In PostgreSQL, the supported isolation levels include:

- **READ COMMITTED:** the default in typical configurations; each statement sees a snapshot as of the start of that statement.
- **REPEATABLE READ:** queries within a transaction use a consistent snapshot according to this level's rules; serialization errors can occur under certain contention.
- **SERIALIZABLE:** PostgreSQL detects conflicts that could violate serializability and may abort a transaction with an error requiring retry.

PostgreSQL also accepts the name `READ UNCOMMITTED`, but executes it identically to `READ COMMITTED` in PostgreSQL; it does not allow dirty reads of uncommitted data as many people expect.

Regardless of isolation level, an application with concurrent transactions still needs **retry** handling, appropriate locking, and business-condition checks. MVCC should not be interpreted as automatically making every concurrent read–write combination business-correct.

### 10.2. Inventory and Concurrent Updates

A safer inventory update pattern compared to "read quantity, compute in application, overwrite":

~~~sql
UPDATE products
SET stock_qty = stock_qty - 2
WHERE product_id = 1
  AND stock_qty >= 2
RETURNING product_id, stock_qty;
~~~

If no row is returned, no update matched the condition. The application must handle this result as out of stock or nonexistent product depending on its logic.

`RETURNING` is a convenient PostgreSQL feature: an `UPDATE` can return values from the modified row, eliminating a separate query round-trip in many scenarios.

## 11. Role 5: Durable Writes and Recovery with WAL

Writing data to disk is not as simple as calling a `save` command and assuming it is always safe. If the server crashes abruptly mid-transaction, the system must know which changes were committed and how to recover to a consistent state.

PostgreSQL uses **WAL — Write-Ahead Logging**. Under the write-ahead principle, the necessary log records are durably written appropriately before data page changes are considered durable by the engine's mechanism.

~~~text
Application writes data
       |
       v
Changes in memory / buffers
       |
       +--> WAL records
       |
       v
COMMIT per durability policy
       |
       v
Data pages flushed to storage over time
       |
       v
On restart after a crash:
   PostgreSQL uses WAL to recover a consistent state
~~~

WAL serves:

- **Crash recovery** after unexpected shutdowns.
- Ensuring transaction durability.
- The foundation for certain replication mechanisms and point-in-time recovery.
- Supporting PostgreSQL checkpointing and data writing processes.

However, **WAL is not a standalone backup**. If valid but erroneous business deletes occur, or the entire storage volume is lost, existing WAL alone may not suffice to recover to the desired target. Operations require a backup plan, retention policy, and restore testing.

### 11.1. Durability Depends on Configuration and Infrastructure

Durability must not be understood as "data can never be lost under any failure." Settings such as `synchronous_commit`, storage configuration, hardware quality, operations, and failure scope all affect actual guarantees.

Alongside transaction design, operators must ensure:

- Independent backups and tested restore procedures.
- Sufficient disk capacity for WAL and data.
- Monitoring of server health and storage subsystems.
- Clear understanding of acceptable downtime and maximum tolerable data loss.

## 12. Role 6: Optimizing Queries with the Planner and Indexes

When a table has millions of rows, sequentially scanning every row for each query may be unsuitable. PostgreSQL uses a **query planner/optimizer** to estimate costs and select an execution plan.

Example:

~~~sql
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at DESC);
~~~

This B-tree index can be useful for the query:

~~~sql
SELECT order_id, created_at, order_status
FROM orders
WHERE customer_id = 1
ORDER BY created_at DESC
LIMIT 20;
~~~

However, PostgreSQL is **not required** to use an index just because it exists. On very small tables, low-selectivity predicates, or specific statistics, the planner may choose a sequential scan.

### 12.1. Common Index Types

| Type | Typical Use Cases |
|---|---|
| **B-tree** | Equality, range queries, sorting on matching keys |
| **Hash** | Certain equality comparisons in appropriate cases |
| **GIN** | Searching multiple keys/elements inside structures like arrays or `JSONB`; also used by some extensions |
| **GiST** | Specialized structures/searches such as geometry, ranges, and matching extensions |
| **BRIN** | Page-range summaries for very large tables with physical correlation to key values |
| **SP-GiST** | Certain specialized space/dataset partitioning schemes |

These are guidelines rather than absolute rules. Whether an index type can be used also depends on operators, data types, operator classes, and query characteristics.

### 12.2. What Does EXPLAIN Show?

~~~sql
EXPLAIN
SELECT order_id, created_at
FROM orders
WHERE customer_id = 1;
~~~

`EXPLAIN` shows the execution plan PostgreSQL intends to use, such as sequential scan, index scan, or bitmap heap scan, along with estimated row counts and costs.

When you want to measure actual execution:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM orders
WHERE customer_id = 1;
~~~

**`ANALYZE` in `EXPLAIN (ANALYZE)` actually executes the SQL statement.** For read queries on small tables this is usually simple, but on production systems resource usage must be watched; for DML statements, the command can **actually modify data** if not safely structured. Never treat `EXPLAIN ANALYZE UPDATE/DELETE` as a read-only operation.

### 12.3. What Roles Do VACUUM and ANALYZE Play?

Because MVCC retains row versions per the engine's mechanism, PostgreSQL requires **VACUUM/autovacuum** to reclaim space for reuse from dead tuples and maintain long-term storage health. **ANALYZE** updates statistics so the planner can estimate and choose plans.

This is an important operational task, not something an application should run after every `INSERT`. PostgreSQL has automatic maintenance processes and configurations; under heavy write loads or specific issues, operators should check settings and metrics.

## 13. Role 7: Managing Users, Privileges, and Access Policies

Not every application should be allowed to read every table or alter every object. PostgreSQL uses **roles** for identity management and authorization.

Example administrative syntax in a test environment:

~~~sql
-- Only an administrator with appropriate privileges can run this.
CREATE ROLE app_reader LOGIN PASSWORD 'use-a-strong-secret';

GRANT CONNECT ON DATABASE app_db TO app_reader;
GRANT USAGE ON SCHEMA sales TO app_reader;
GRANT SELECT ON sales.orders TO app_reader;
~~~

This defines an application account with permission to connect to the database, use the schema, and read a specific table. In production systems, passwords must be protected by a secret management mechanism rather than using example strings in a repository.

Common privileges:

| Privilege | Typical Effect |
|---|---|
| `CONNECT` | Allows connecting to a database |
| `USAGE` on schema | Allows resolving names/accessing objects subject to further privileges |
| `SELECT` | Read table/view data |
| `INSERT`, `UPDATE`, `DELETE` | Modify rows |
| `CREATE` on schema | Create objects within the schema |
| `EXECUTE` | Invoke matching functions/procedures |

`GRANT` statements must be evaluated alongside object ownership, default privileges, role membership, and per-database/schema policies. Do not grant `SUPERUSER` to regular applications.

### 13.1. Row-Level Security (RLS)

PostgreSQL provides **Row-Level Security**, allowing policies that control which rows can be seen or modified in a table when enabled and properly configured.

This can be a useful tool for multi-tenant applications. However, RLS does not automatically know who the web user is: the application architecture must still pass trusted identity/context, assign privileges properly, and control policy bypasses.

Be sure to understand exceptions for table owners, superusers, and roles with bypass-RLS privileges; do not treat enabling RLS as an absolute guarantee if high-privilege access paths remain.

## 14. PostgreSQL Can Serve Many Data Types

Although its core is relational, PostgreSQL is not limited to plain numbers and text columns.

### 14.1. JSONB: Semi-Structured Data

Example:

~~~sql
CREATE TABLE event_logs (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Inserting data:

~~~sql
INSERT INTO event_logs (event_type, payload)
VALUES
(
    'order_created',
    '{"order_id": 101, "channel": "web", "items": 2}'::jsonb
);
~~~

Querying attributes:

~~~sql
SELECT
    event_id,
    payload ->> 'channel' AS channel
FROM event_logs
WHERE payload ->> 'channel' = 'web';
~~~

`JSONB` allows storing and querying JSON documents in a binary representation processed by PostgreSQL. It is convenient for variable attributes, event payloads, or integration data.

However, if all core relationships are pushed into JSON, it becomes harder to maintain foreign keys, strict typing, and conventional JOINs. **Using JSONB appropriately** usually means combining relational columns for core information with JSONB for flexible parts, rather than abandoning the relational model.

### 14.2. UUID, Arrays, and Ranges

PostgreSQL supports:

- `UUID` for identifiers.
- Array types such as `INTEGER[]`.
- Range types such as `daterange` or `tstzrange`.
- Specialized types and operators for search and data processing.

These types can express domain problems more clearly, but should be chosen based on actual query patterns and constraint maintainability.

### 14.3. Extensions

PostgreSQL supports an **extension** mechanism, for example:

- **PostGIS:** adds geospatial capabilities when installed and granted.
- **pg_trgm:** supports trigram-based text matching operations, which can be paired with indexes.
- Other extensions depending on distribution, provider, and operational policy.

Not every extension is available or permitted on every PostgreSQL service. Availability depends on version, deployed packages, privileges, and infrastructure policies.

## 15. Hands-On Start: From Schema to Relational Queries

This section builds a step-by-step runnable example in a PostgreSQL 12+ **test database** where your account is allowed to create schemas and tables. Do not run it on a production schema.

To avoid depending on database creation privileges or existing tables in `public`, the example uses a dedicated schema `pg_intro` in the **database you are currently connected to**.

### 15.1. Check the Current Version and Database

In `psql` or a SQL client:

~~~sql
SELECT version();
SELECT current_database();
SELECT current_user;
SELECT current_schema();
~~~

If using `psql`, the command:

~~~text
\conninfo
~~~

displays current connection details. This is a **psql meta-command**, not SQL; do not send `\conninfo` over JDBC as a server query.

### 15.2. Create the Schema

~~~sql
CREATE SCHEMA IF NOT EXISTS pg_intro;
~~~

To keep the SQL statements below unambiguous, we use fully qualified table names `pg_intro.table_name`. That way, there is no need to change the session's `search_path`.

### 15.3. Create the Tables

~~~sql
CREATE TABLE pg_intro.customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE
);

CREATE TABLE pg_intro.products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL
        CHECK (unit_price >= 0),
    stock_qty INTEGER NOT NULL DEFAULT 0
        CHECK (stock_qty >= 0)
);

CREATE TABLE pg_intro.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES pg_intro.customers(customer_id),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'paid', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE pg_intro.order_items (
    order_item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES pg_intro.orders(order_id),
    product_id BIGINT NOT NULL
        REFERENCES pg_intro.products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL
        CHECK (unit_price >= 0)
);
~~~

The model consists of:

~~~text
customers (1) ----- (N) orders
                          |
                          | (1)
                          |
                          v
                  order_items (N)
                          |
                          | (N)
                          |
                  products (1)
~~~

The `order_items` table links orders with products; each row represents one product and its quantity in an order. The price is stored on the order line item to preserve **the price at transaction time**, rather than always depending on the current price in `products`.

### 15.4. Insert Sample Data

~~~sql
INSERT INTO pg_intro.customers (full_name, email)
VALUES
    ('An', 'an@example.test'),
    ('Bình', 'binh@example.test')
RETURNING customer_id, full_name;

INSERT INTO pg_intro.products
    (sku, product_name, unit_price, stock_qty)
VALUES
    ('BK-01', 'Notebook', 50000.00, 20),
    ('PN-02', 'Pen',      12000.00, 40)
RETURNING product_id, sku;

INSERT INTO pg_intro.orders (customer_id, status)
VALUES
    (1, 'paid'),
    (1, 'pending'),
    (2, 'paid')
RETURNING order_id, customer_id, status;

INSERT INTO pg_intro.order_items
    (order_id, product_id, quantity, unit_price)
VALUES
    (1, 1, 2, 50000.00),
    (1, 2, 3, 12000.00),
    (2, 2, 1, 12000.00),
    (3, 1, 1, 50000.00);
~~~

The references `1`, `2`, `3` in `order_items` assume freshly created tables with no prior inserts or deletes. When re-running the exercise on tables that already have data, **do not assume identity values always restart at 1**. Use the actual IDs returned by `RETURNING` or look them up by business keys.

### 15.5. Query Combined Data

~~~sql
SELECT
    o.order_id,
    c.full_name AS customer_name,
    o.status,
    o.created_at
FROM pg_intro.orders AS o
JOIN pg_intro.customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.order_id;
~~~

This query combines data from two tables along the foreign key relationship.

### 15.6. Calculate Order Totals

~~~sql
SELECT
    o.order_id,
    c.full_name,
    o.status,
    SUM(oi.quantity * oi.unit_price) AS total_amount
FROM pg_intro.orders AS o
JOIN pg_intro.customers AS c
    ON c.customer_id = o.customer_id
JOIN pg_intro.order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY
    o.order_id,
    c.customer_id
ORDER BY o.order_id;
~~~

Expected output from the sample data:

| order_id | full_name | status | total_amount |
|---:|---|---|---:|
| 1 | An | paid | 136000.00 |
| 2 | An | pending | 12000.00 |
| 3 | Bình | paid | 50000.00 |

This query uses `JOIN`, `GROUP BY`, and `SUM` to generate a report from detail rows. With appropriate primary keys, PostgreSQL recognizes certain functional dependencies during grouping checks, though when writing SQL meant to be portable across RDBMSs or easier to read, it is good practice to group by the columns needed for the result semantics.

### 15.7. View Customers Without Orders

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS order_count
FROM pg_intro.customers AS c
LEFT JOIN pg_intro.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

`LEFT JOIN` preserves the customer row even when no matching order exists. Using `COUNT(o.order_id)` instead of `COUNT(*)` counts actual orders because `LEFT JOIN` still produces a row with `NULL` values for `orders` columns.

This example shows that **the correctness of aggregations depends on understanding the relational model**, not just whether a SQL statement runs.

## 16. Experiencing Transactions and Rollback

With sample data in place, let us try a reversible change.

~~~sql
BEGIN;

UPDATE pg_intro.products
SET stock_qty = stock_qty - 2
WHERE sku = 'BK-01'
  AND stock_qty >= 2
RETURNING sku, stock_qty;

-- Inspect within the same transaction.
SELECT sku, stock_qty
FROM pg_intro.products
WHERE sku = 'BK-01';

ROLLBACK;
~~~

If there were 20 notebooks previously, the `UPDATE` temporarily shows 18. After `ROLLBACK`, checking again outside the transaction shows the quantity is still 20:

~~~sql
SELECT sku, stock_qty
FROM pg_intro.products
WHERE sku = 'BK-01';
~~~

That is a small demonstration of **atomicity**. In production applications, a transaction can involve multiple operations and must handle errors, timeouts, and retries.

### 16.1. When to Use COMMIT?

If the business rules pass and you want to persist the change:

~~~sql
BEGIN;

UPDATE pg_intro.products
SET stock_qty = stock_qty - 1
WHERE sku = 'PN-02'
  AND stock_qty >= 1
RETURNING sku, stock_qty;

-- Only COMMIT once business conditions have been verified.
COMMIT;
~~~

This example saves the change if a row is updated and the transaction commits successfully. If the `UPDATE` returns no rows, the application must handle the absence of a matching row rather than blindly assuming success.

**In Java/JDBC applications:** `Connection#setAutoCommit(false)` is typically used, followed by `commit()` or `rollback()` based on step outcomes. Exception handling must ensure connections are not left in an aborted transaction state or held open unnecessarily long.

## 17. Creating an Index and Inspecting the Plan

The orders table is frequently queried by customer and timestamp. We can add an index:

~~~sql
CREATE INDEX idx_pg_intro_orders_customer_created
ON pg_intro.orders (customer_id, created_at DESC);
~~~

Then:

~~~sql
EXPLAIN
SELECT order_id, created_at, status
FROM pg_intro.orders
WHERE customer_id = 1
ORDER BY created_at DESC;
~~~

Because the lab table has only a few rows, PostgreSQL may choose a `Seq Scan` instead of an `Index Scan`. That does not prove the index is broken or the planner is buggy: on small tables, scanning the table can be cheaper than reading the index.

To evaluate whether an index is effective, you need to:

1. Understand the primary filter and sort predicates.
2. Examine data volume and value distribution.
3. Read `EXPLAIN` or `EXPLAIN (ANALYZE, BUFFERS)` in a safe environment.
4. Account for write overhead, storage size, and index maintenance.

**Adding an index is not a free operation**: during `INSERT/UPDATE/DELETE`, PostgreSQL must also maintain the associated index structures.

## 18. Observing PostgreSQL via Catalogs and Statistics Views

Beyond business data, PostgreSQL provides **system catalogs** and **statistics views** to inspect structure, activity, and performance.

Several useful read queries:

~~~sql
-- Current database.
SELECT current_database();

-- Server version.
SHOW server_version;

-- Size of the current database.
SELECT pg_size_pretty(pg_database_size(current_database()))
       AS database_size;

-- Total size of a table and its indexes.
SELECT pg_size_pretty(
    pg_total_relation_size('pg_intro.orders')
) AS orders_total_size;
~~~

When the table exists, `pg_total_relation_size` reports the total size of the relation together with its indexes and associated components as calculated by PostgreSQL. This number is **not** the raw byte count of business data alone.

Inspect activity on user tables:

~~~sql
SELECT
    schemaname,
    relname,
    seq_scan,
    idx_scan,
    n_live_tup,
    n_dead_tup
FROM pg_stat_user_tables
WHERE schemaname = 'pg_intro'
ORDER BY relname;
~~~

The fields `n_live_tup` and `n_dead_tup` are **statistical estimates**, not replacements for exact row counts. Statistics also have update and reset cycles; they should not be treated as the server's entire history.

Inspect active sessions:

~~~sql
SELECT
    pid,
    datname,
    usename,
    state,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database();
~~~

Visible details depend on the account's privileges. Not every account is permitted to view the full query text of other sessions.

## 19. Tools for Working with PostgreSQL

### 19.1. psql

**`psql`** is PostgreSQL's popular command-line client. A connection command typically looks like:

~~~bash
psql -h localhost -p 5432 -U app_user -d app_db
~~~

Where:

| Option | Meaning |
|---|---|
| `-h` | Server host or address |
| `-p` | Connection port, commonly 5432 by default |
| `-U` | Login role name |
| `-d` | Database name |

Commands starting with `\` in `psql` are **client meta-commands**:

~~~text
\l            List databases
\dn           List schemas
\dt           List tables in search path
\d pg_intro.orders
              Describe table structure
\conninfo     Display current connection info
\q            Quit psql
~~~

These are not standard SQL statements that can be sent verbatim through every driver.

### 19.2. pgAdmin and Graphical Tools

**pgAdmin** is a graphical tool in the PostgreSQL ecosystem for browsing objects, running SQL, and performing administrative tasks. Other popular tools can connect via a PostgreSQL driver.

Even when using a GUI, learners should still understand SQL, transactions, and privileges. A "Save" click in an admin screen can emit `ALTER TABLE`, `UPDATE`, or other high-impact statements.

### 19.3. Application Drivers

Java applications typically use the **PostgreSQL JDBC Driver**; Python can use compatible drivers, and other languages have their own client libraries.

Simple Java example:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public class ReadCustomers {
    public static void main(String[] args) throws Exception {
        // In real applications, load config and secrets from a secure environment.
        String url = "jdbc:postgresql://localhost:5432/app_db";
        String user = "app_reader";
        String password = "replace-with-secret";

        String sql = """
            SELECT customer_id, full_name
            FROM pg_intro.customers
            WHERE customer_id = ?
            """;

        try (Connection conn = DriverManager.getConnection(
                    url, user, password);
             PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setLong(1, 1L);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    System.out.println(
                        rs.getLong("customer_id") + ": "
                        + rs.getString("full_name")
                    );
                }
            }
        }
    }
}
~~~

This sample code requires the JDBC driver on the classpath and the corresponding database, role, and table to exist. Never hard-code real passwords in production source code; use a secret manager and environment configuration.

**PreparedStatement** passes values as parameters separate from SQL syntax. It does not by itself guarantee authorization or prevent all logic bugs, but it is a critical tool for reducing SQL injection risk when used properly.

## 20. How Does PostgreSQL Support Operations and System Evolution?

A production RDBMS does more than just run `SELECT` queries. Many operational concerns emerge over time.

### 20.1. Backup and Recovery

PostgreSQL provides both logical and physical backup methods, for example:

- `pg_dump` to export data and schema at the logical level.
- Physical backup methods and appropriate WAL management.
- **Point-In-Time Recovery (PITR)** when an appropriate backup and WAL archive chain is deployed.

Running a single dump command should not be treated as sufficient for all recovery goals. You should define **RPO** (maximum acceptable data loss) and **RTO** (target recovery time), and then test restore capability.

### 20.2. Replication and Availability

PostgreSQL supports multiple replication mechanisms, including **streaming/physical replication** and **logical replication** in appropriate configurations.

Replication enables replicas for purposes such as standby failover, read scaling, or data integration, but it does not replace backups. A valid erroneous data deletion can be replicated to replicas.

Achieving **high availability** also requires tooling and procedures for failure detection, role promotion, connection routing, split-brain prevention, and failover testing. Do not claim that simply enabling replication creates a complete HA cluster.

### 20.3. Upgrades and Schema Changes

Over a long lifecycle, applications add columns, create indexes, change constraints, or upgrade PostgreSQL versions. These changes can carry locking costs, I/O load, and compatibility risks.

General principles:

- Use version-controlled migrations.
- Validate existing data before adding constraints.
- Estimate space and time before creating indexes or altering column types.
- Consider strategies that minimize write blocking where supported.
- Verify applications and client tooling after upgrades.
- Have a backup/rollback plan appropriate to the change type.

### 20.4. System Monitoring

Practical metrics that typically require monitoring:

| Category | Examples |
|---|---|
| Connections | Number of backend connections, pool utilization |
| Transactions | Commit/rollback rates, long-running transactions |
| Queries | Latency, slow queries, execution plans |
| Locks | Waiting sessions, deadlocks |
| Storage | Table/index sizes, WAL size, free disk space |
| Maintenance | VACUUM/autovacuum, dead tuples, statistics |
| Replication | Replica lag, WAL retention status |
| Backups | Backup outcomes, restore duration, recoverability |

No DBMS eliminates the need for monitoring and maintenance. PostgreSQL provides helpful automation, but large applications still need operators who understand warning signs.

## 21. When Is PostgreSQL the Right Choice?

PostgreSQL is often a strong candidate when a system has the following needs:

### 21.1. Clear Relational Data

For example, customers–orders–order items–products. Primary keys, foreign keys, unique constraints, and transactions help enforce those relationships.

### 21.2. Critical Integrity Rules

Payment, inventory, scheduling, or HR systems often need to prevent bad data from concurrent update sources. PostgreSQL's constraints and transaction mechanisms are well suited for this requirement.

### 21.3. Diverse Query Patterns

Systems that serve both key-based transactions and aggregated reporting, multi-criteria filtering, and multi-table JOINs can leverage PostgreSQL's SQL capabilities.

### 21.4. Specialized Extensions Needed

Applications handling geospatial data can use PostGIS; applications storing flexible JSON payloads can use JSONB; systems analyzing time-based data can leverage range types, aggregates, and matching extensions.

### 21.5. Desire for Deployment and Access Control

Organizations can operate PostgreSQL on their own infrastructure or use a managed PostgreSQL service, depending on cost, compliance, backup, version, and team staffing requirements.

**Do not choose it just because "PostgreSQL is famously powerful."** Identify the required functionality, reliability, scale, team skills, and operational model.

## 22. When to Consider Other Solutions or Combine Technologies?

PostgreSQL does not have to be the sole component in every architecture:

- For large binary files like videos or images, **object storage** is usually suited for file contents while PostgreSQL stores metadata and references.
- For ultra-low-latency ephemeral caching, a dedicated cache layer can be added while PostgreSQL remains the source of truth.
- For extremely high-volume logs/events primarily used for analytical aggregation, a dedicated data warehouse or analytics engine may be considered depending on requirements.
- For specialized full-text or vector search at particular scales, PostgreSQL has suitable capabilities/extensions for many problems, though it should be benchmarked against specialized search engines if requirements diverge.
- For very small embedded systems without a separate server process, an embedded database like SQLite may fit the deployment model better.
- For multi-region distributed applications requiring concurrent writes with special guarantees, the architecture must be analyzed carefully rather than assuming a single PostgreSQL server meets every need.

Modern architectures often use **PostgreSQL as the core transactional source of truth** and pair it with caches, search, analytics, or object storage when genuinely needed.

### 22.1. PostgreSQL vs. NoSQL: Not an Absolute Opposition

"Relational SQL" and "NoSQL" are not simply "rigid" versus "flexible."

| Question | Relational PostgreSQL | Some NoSQL Systems |
|---|---|---|
| Data model | Tables, keys, relations, optionally combined with JSONB | Document, key-value, wide-column, graph, etc., depending on engine |
| Querying | SQL, JOINs, aggregates, and rich operators | Engine-specific API/query language |
| Constraints | PK, FK, CHECK, UNIQUE, and extensible mechanisms | Varies by system |
| Transactions | Strong transaction support per PostgreSQL mechanisms | Varies by product; not all NoSQL systems lack transactions |
| Distribution | Supports replication and appropriate scaling approaches | Some systems are designed for horizontal distribution from the ground up |
| Key considerations | Schema design, queries, locks, VACUUM, operations | Consistency model, query patterns, data partitioning, engine-specific limits |

The choice must be based on **actual workload and consistency requirements**, not technology labels.

## 23. Common Misconceptions About PostgreSQL

### 23.1. "PostgreSQL Is Just a Place to Store Tables"

Incomplete. PostgreSQL is also responsible for transactions, constraint enforcement, concurrency, indexes, query planning, privileges, backup/replication, and many other server operations.

### 23.2. "Knowing SQL Means Knowing How to Operate PostgreSQL"

SQL is an essential foundation, but operations also cover connection configuration, locking, MVCC/VACUUM, WAL, backups, access control, and performance observability.

### 23.3. "An RDBMS Cannot Store JSON"

False. PostgreSQL provides `JSON` and `JSONB`, along with corresponding functions and operators. Supporting JSON does not eliminate the role of the relational model.

### 23.4. "Having PRIMARY KEY and FOREIGN KEY Guarantees All Business Logic Is Correct"

No. Constraints protect declarable rules. Business workflows still require transactions, authorization checks, concurrency handling, and logical validation.

### 23.5. "Every Indexed Query Is Fast"

False. The planner weighs cost, statistics, selectivity, and the number of rows to read. An index may not be chosen or may help very little if predicates do not fit it.

### 23.6. "Using Transactions Means Never Needing Retries"

False. Concurrent access can encounter deadlocks, serialization failures, timeouts, or other errors. Applications must classify errors and perform safe retries when appropriate.

### 23.7. "MVCC Means There Are No Locks"

False. MVCC manages row versions and consistent reads, but writes, DDL, and explicit locking statements still use locks.

### 23.8. "WAL Is Equivalent to a Backup"

False. WAL supports crash recovery and certain replication/PITR mechanisms, but independent backups and restore testing remain essential.

### 23.9. "PostgreSQL Automatically Creates an Index for Every Foreign Key"

PostgreSQL creates indexes to enforce primary keys and unique constraints appropriately, but **does not automatically create an index on the referencing columns of every foreign key**. When child tables are large or parent tables experience updates/deletes, evaluate creating a dedicated index on the FK column based on workload.

### 23.10. "MySQL Syntax Can Be Used in PostgreSQL Without Changes"

Not always true. Identity syntax, upserts, booleans, date/time types, administrative commands, and many other details differ. When migrating systems, review SQL and migrations thoroughly.

### 23.11. "PostgreSQL Needs No Administration When Running on a Cloud Service"

A managed service may handle part of the infrastructure, but users still need to design schemas, tune queries, configure privileges, set appropriate backup/retention policies, and monitor the application.

## 24. Designing PostgreSQL for a New Application

Suppose you are designing an ordering system. Before creating tables, answer these questions:

1. **What is the core data?** Customers, products, orders, order items, payments.
2. **What entity or event does one row represent?** One row per order, one row per product line item in an order.
3. **What are the primary and foreign keys?** Unique identifiers and relationships between tables.
4. **Which attributes are required?** Disallow `NULL` on mandatory business fields.
5. **Which rules should the DBMS enforce?** Unique SKUs, non-negative prices, valid FKs.
6. **Which operations form a single transaction?** Creating an order, deducting stock, recording payment per the workflow.
7. **What are the main query paths?** Finding orders by customer, status, or timestamp.
8. **How many concurrent clients will there be?** Pooling, timeouts, locking, and retry requirements.
9. **Who can read/modify data?** Application roles and least-privilege permissions.
10. **How is data backed up and restored?** Backups, WAL, and RPO/RTO targets.
11. **As data grows, what will you monitor?** Indexes, latency, VACUUM, sizes, and storage.
12. **When changing the schema, how will you avoid outages?** Tested migrations and rollout plans.

These questions connect RDBMS capabilities to real requirements instead of starting with an ad-hoc `CREATE TABLE` command.

## 25. Practice Exercises

### Exercise 1 — Distinguish Database and DBMS

A team stores a customer list in CSV, then migrates to PostgreSQL. Name at least four new capabilities PostgreSQL provides beyond simply storing data rows.

**Hint:** PK/FK constraints, transactions, indexes, concurrent access control, authorization, crash recovery, SQL query planner.

### Exercise 2 — Identify Relationships

A store has the entities `customers`, `orders`, `order_items`, and `products`. Identify the one-to-many relationships and their corresponding FK columns.

**Hint:** Each customer has many orders; each order has many order items; each product can appear in many order items.

### Exercise 3 — Choose Constraints

You need to prevent products with `unit_price < 0`, prevent two products from sharing the same SKU, and block orders from referencing nonexistent customers. Choose the appropriate constraint for each requirement.

**Hint:** `CHECK`, `UNIQUE`, `FOREIGN KEY`.

### Exercise 4 — Write a JOIN Query

Write a SQL query to retrieve customer names and order IDs from `pg_intro.customers` and `pg_intro.orders`.

**Suggested answer:**

~~~sql
SELECT c.full_name, o.order_id
FROM pg_intro.customers AS c
JOIN pg_intro.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY o.order_id;
~~~

### Exercise 5 — Predict the Outcome of ROLLBACK

Notebook stock is 20. A transaction subtracts 5, then executes `ROLLBACK`. What is the final result and why?

**Hint:** Assuming no other changes in the transaction and no concurrent conflicting updates, committed stock remains 20 because the transaction was not committed.

### Exercise 6 — Understand Concurrency

Two transactions update the same inventory row simultaneously. Why can this not be solved merely by "reading the value in the application and overwriting it"?

**Hint:** There is a risk of lost updates or checking stock against stale values. Use atomic conditional updates, transactions/locking, and concurrency handling.

### Exercise 7 — Is an Index Always Used?

You create an index on `customer_id` for a table with only 10 rows. `EXPLAIN` still reports a sequential scan. Is the index broken?

**Hint:** Not necessarily. The planner may choose a sequential scan because it is cheaper; examine the workload, data distribution, and actual measurements.

### Exercise 8 — WAL and Backups

A server has WAL and a streaming replica. Can you skip all backups?

**Hint:** No. Valid erroneous data changes replicate to the replica; backups and restore testing aligned with RPO/RTO targets are still required.

### Exercise 9 — Choosing PostgreSQL for an Application

An inventory management system needs transactions, FK constraints, SQL reporting, and multiple concurrent users. Explain why PostgreSQL is a reasonable candidate, and list two additional requirements to ask about before deciding.

**Hint:** Load scale/latency, HA/backup requirements, operations team capacity, integrations, cost.

### Exercise 10 — Schema and Database

Within the same database, two schemas `sales` and `hr` both have an `employees` table. How do you query a specific one?

**Hint:**

~~~sql
SELECT * FROM hr.employees;
SELECT * FROM sales.employees;
~~~

Use schema-qualified names when needed to avoid relying on `search_path`.

## 26. Quick Reference

| Question | Answer |
|---|---|
| What is PostgreSQL? | An open-source object-relational database management system |
| What model does an RDBMS use for data? | Relations/tables, rows, columns, keys, and constraints |
| What role does SQL play? | Defining, querying, and manipulating data |
| What is a primary key used for? | Uniquely identifying each row |
| What is a foreign key used for? | Enforcing declared referential relationships |
| What does a transaction provide? | Grouping operations into a unit that can be committed or rolled back |
| What is ACID? | Atomicity, Consistency, Isolation, Durability |
| What is MVCC? | Multi-version concurrency control for snapshots and concurrent access |
| What is WAL? | Write-Ahead Logging, the foundation for crash recovery and durability |
| What do indexes help with? | Providing efficient access paths for many search patterns |
| What does EXPLAIN show? | The query plan chosen by the planner |
| What does VACUUM need to do? | Clean up dead tuples and maintain reusable space to support MVCC operations |
| How does a schema differ from a database? | A schema is a namespace inside a database |
| What is psql? | PostgreSQL's command-line client |
| Can PostgreSQL store JSON? | Yes, including `JSON` and `JSONB` |
| Should applications use superuser? | No; prefer least privilege |
| Do replicas replace backups? | No |
| Does PostgreSQL solve all business logic? | No; proper data design, transactions, and authorization are still required |

---

## Conclusion

**PostgreSQL is a software platform for storing and processing relational data under strict controls**, not merely a container for tables with rows and columns. It provides SQL for querying and combining data, constraints to protect integrity, ACID transactions to manage changes, MVCC and locks to handle concurrent access, WAL to support recovery, indexes and a planner to optimize reads, plus access control and operational tooling for long-lived systems.

For anyone learning PostgreSQL, the most important first step is understanding **which problem each component solves**. Tables and relations model the business domain; constraints protect core rules; transactions handle multi-step changes; indexes accelerate queries; and backup, statistics, and security tools support operations as data grows. With that big picture in mind, you can study PostgreSQL in greater depth without mistaking a working SQL query for a well-designed, safely operated data system.
