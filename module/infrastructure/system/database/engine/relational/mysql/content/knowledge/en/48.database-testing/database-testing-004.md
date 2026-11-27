# Schema Creation/Reset, Data Seeding, and Foreign Key Ordering

A reliable MySQL test must start from a reproducible schema, predictable input data, and a database state that is cleanly reset after running. If tests share a long-lived schema, leftover data can make tests flaky; if seeding violates foreign key order, inserts fail; if resets bypass foreign key checks, the database can accumulate orphan rows undetected by tests.

This lesson covers creating test schemas, applying migrations, seeding deterministic data, ordering operations by foreign key dependencies, and resetting the database safely. Examples use MySQL/InnoDB. Destructive schema statements should only run against an isolated, clearly named test database.

## Learning Objectives

After this lesson, you will be able to:

- Create a test schema with charset, collation, and configuration matching the target test environment.
- Use migrations to build a schema from an empty state.
- Choose the appropriate reset strategy: recreating the schema, transaction rollback, or deleting data in dependency order.
- Seed deterministic, reproducible data.
- Order inserts parent-before-child and cleanup child-before-parent.
- Handle self-referencing relationships, foreign key cycles, and bulk-imported data.
- Understand the limitations of `FOREIGN_KEY_CHECKS`, `TRUNCATE`, and transactions in MySQL.
- Isolate data across tests running in parallel.

## 1. Test Schemas Must Be Isolated

Never run destructive tests on a schema containing shared developer data or data from another environment. Create a dedicated schema whose name clearly states its purpose and environment:

```sql
CREATE DATABASE mysql_app_test
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
```

`utf8mb4_0900_ai_ci` is a common collation on MySQL 8.0. If production uses a different collation, use that exact collation so tests reflect real comparison, sorting, and unique-index rules. Do not pick a collation merely because it is the default on a developer machine.

After creating the schema, configure the test connection to point to that exact database:

```text
jdbc:mysql://localhost:3306/mysql_app_test
```

The test account should only have privileges on the test schema. A migration account may need DDL privileges; an account running business tests only needs appropriate DML privileges. Separating those roles prevents tests from accidentally relying on broad administrative privileges.

### 1.1. One Schema Per Suite or One Schema Per Test?

Several isolation strategies exist:

| Strategy | How it is used | Appropriate when |
|---|---|---|
| Fresh schema per test suite | Drop/create schema before the suite, run migrations, seed fixtures | You want tests starting from a clean state and need to test migrations |
| Separate schema per test class/worker | Each test group has its own database | Tests run in parallel or mutate data destructively |
| Transaction rollback per test | Open transaction, seed and run test, roll back at end of test | Tests only modify transactional data and use the same connection/transaction |
| Delete/truncate data after test | Delete fixtures or all tables in dependency order | You need to reuse the schema and reset quickly |

For migration tests, a fresh schema from scratch is usually the clearest choice: run all migrations on an empty database and verify the schema. For repository/service tests, transaction rollback works if all operations stay inside the same transaction and have no external side effects.

Never let multiple test workers simultaneously drop, truncate, or seed a shared schema. If parallel execution is needed, create separate schemas per worker or separate database containers.

## 2. Building the Schema via Migrations

The test schema should be created using the exact migrations the application deploys with, such as Flyway or Liquibase. Do not maintain a separate set of `CREATE TABLE` scripts solely for testing, as the two schemas can drift over time.

Example migration creating three tables with foreign key relationships:

```sql
CREATE TABLE customers (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  email VARCHAR(255) NOT NULL,
  display_name VARCHAR(120) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_customers_email (email)
) ENGINE = InnoDB;

CREATE TABLE orders (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  customer_id BIGINT UNSIGNED NOT NULL,
  order_number VARCHAR(40) NOT NULL,
  created_at DATETIME NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_orders_order_number (order_number),
  KEY idx_orders_customer_id (customer_id),
  CONSTRAINT fk_orders_customer
    FOREIGN KEY (customer_id) REFERENCES customers (id)
) ENGINE = InnoDB;

CREATE TABLE order_items (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  order_id BIGINT UNSIGNED NOT NULL,
  sku VARCHAR(60) NOT NULL,
  quantity INT UNSIGNED NOT NULL,
  unit_price DECIMAL(12, 2) NOT NULL,
  PRIMARY KEY (id),
  KEY idx_order_items_order_id (order_id),
  CONSTRAINT fk_order_items_order
    FOREIGN KEY (order_id) REFERENCES orders (id)
) ENGINE = InnoDB;
```

The relationships are:

```text
customers
    |
    | customers.id <- orders.customer_id
    v
  orders
    |
    | orders.id <- order_items.order_id
    v
order_items
```

`orders` is a child table of `customers`; `order_items` is a child table of `orders`. When inserting data, a customer must exist before an order, and an order before an order item. When deleting data, follow the reverse order.

### 2.1. Why InnoDB?

InnoDB supports transactions and foreign keys. Business tests must verify the behavior of the production engine; testing with another engine or H2 can differ in locking rules, constraints, collations, and SQL behavior.

Inspect engines and constraints after migration:

```sql
SHOW TABLE STATUS FROM mysql_app_test;
SHOW CREATE TABLE mysql_app_test.orders\G
```

Integration tests should run on MySQL with the same major version and production-like configuration, such as via a MySQL container. Testing only on H2 is insufficient to prove migrations or foreign keys behave like MySQL.

## 3. Determining Foreign Key Order

### 3.1. Insert Parent-Before-Child

A child row can only reference an existing parent row when foreign keys are checked. In the example above, the correct seeding order is:

1. `customers`
2. `orders`
3. `order_items`

Seeding data with fixed IDs and values makes tests predictable:

```sql
INSERT INTO customers (id, email, display_name)
VALUES
  (1001, 'an@example.test', 'An Nguyen'),
  (1002, 'binh@example.test', 'Binh Tran');

INSERT INTO orders (id, customer_id, order_number, created_at)
VALUES
  (2001, 1001, 'TEST-ORDER-001', '2025-01-10 09:00:00'),
  (2002, 1002, 'TEST-ORDER-002', '2025-01-10 10:00:00');

INSERT INTO order_items (id, order_id, sku, quantity, unit_price)
VALUES
  (3001, 2001, 'SKU-RED-01', 2, 19.90),
  (3002, 2001, 'SKU-BLUE-02', 1, 29.50),
  (3003, 2002, 'SKU-GREEN-03', 3, 12.00);
```

Fixed IDs make fixture references explicit in tests, such as asserting that order `2001` belongs to customer `1001`. Only use fixed IDs in an isolated test schema; do not seed collision-prone IDs into shared data.

### 3.2. Deriving Order from the Dependency Graph

With many tables, do not sort by table name or file order. Model foreign key relationships as a directed graph:

- Each table is a node.
- There is an edge from parent table to child table if the child references the parent.
- A topological sort of the graph gives a valid insert order.
- Cleanup runs in reverse order.

For example, a system with `departments`, `employees`, `projects`, and `employee_projects`:

```text
departments -----> employees
      |                |
      v                v
   projects ------> employee_projects
```

If `employees.department_id` references `departments.id`, `projects.department_id` references `departments.id`, and `employee_projects` references both employee and project, seed `departments` first, then `employees`/`projects`, and finally `employee_projects`.

You can query foreign key metadata to build the dependency list:

```sql
SELECT
  TABLE_NAME AS child_table,
  COLUMN_NAME AS child_column,
  REFERENCED_TABLE_NAME AS parent_table,
  REFERENCED_COLUMN_NAME AS parent_column,
  CONSTRAINT_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE CONSTRAINT_SCHEMA = 'mysql_app_test'
  AND REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY REFERENCED_TABLE_NAME, TABLE_NAME, CONSTRAINT_NAME;
```

The output shows each child table, referencing column, and parent table. Use this list to construct seed/cleanup ordering or spot relationships that fixtures must satisfy.

### 3.3. Cleanup Child-Before-Parent

For the example tables, the proper deletion order is `order_items`, `orders`, `customers`:

```sql
DELETE FROM order_items;
DELETE FROM orders;
DELETE FROM customers;
```

Deleting a customer before deleting referencing orders will be rejected by MySQL under default foreign key rules. You can use `ON DELETE CASCADE` if that reflects an actual business rule, but never add cascades merely to shorten test cleanup.

When relationships branch across multiple tables, clean up in reverse topological order. Deepest child tables are deleted first, and root parent tables last.

## 4. Self-Referencing Relationships and Foreign Key Cycles

### 4.1. Self-Referencing Tables

A table can reference itself, such as a category tree:

```sql
CREATE TABLE categories (
  id BIGINT UNSIGNED NOT NULL,
  parent_id BIGINT UNSIGNED NULL,
  category_name VARCHAR(120) NOT NULL,
  PRIMARY KEY (id),
  KEY idx_categories_parent (parent_id),
  CONSTRAINT fk_categories_parent
    FOREIGN KEY (parent_id) REFERENCES categories (id)
) ENGINE = InnoDB;
```

Root nodes have `parent_id = NULL`; child nodes reference an existing parent node. Seed parent before child:

```sql
INSERT INTO categories (id, parent_id, category_name)
VALUES (1, NULL, 'Electronics');

INSERT INTO categories (id, parent_id, category_name)
VALUES (2, 1, 'Computers');

INSERT INTO categories (id, parent_id, category_name)
VALUES (3, 2, 'Laptops');
```

When deleting, delete child nodes before parent nodes if `ON DELETE CASCADE` is not present. For tree structures, you can delete in proper bottom-up order or use cascade if deleting an entire subtree matches business policy.

### 4.2. Mutually Referencing Tables

A cycle arises when table A references B and B also references A. MySQL InnoDB checks foreign keys immediately per statement; it does not support `DEFERRABLE` constraints to postpone checks until the end of a transaction like some other RDBMSs.

If both foreign keys are mandatory, you cannot insert the first row normally when the referenced row does not yet exist. Common design approaches:

- Make one side nullable, insert the parent record first, and update the remaining foreign key afterward.
- Extract the circular relationship into a join table if appropriate for the domain model.
- Construct data via a multi-step workflow with clearly designed constraints.

For example, an employee-manager relationship can use a nullable `manager_id`: insert the employees first, then update the manager once both rows exist. Do not disable foreign key checks as a default workaround for a cyclic data model.

## 5. Deterministic and Reproducible Seed Data

Seed data provides sample data for testing. Good seed data is stable, adequately represents business scenarios, and does not depend on when tests run.

### 5.1. Using Fixed Data

Predefine:

- IDs or business keys for each fixture.
- Emails, order numbers, SKUs, and unique values.
- Explicit timestamps instead of `NOW()` if tests expect deterministic temporal results.
- Numeric values using `DECIMAL` and literals of realistic scale.
- Business states covering both happy paths and edge cases.

For example, if a test requires one paid order and one pending order, seed those two states explicitly. Do not use random data when tests expect fixed outcomes, unless the seeder logs the seed value for reproducibility.

### 5.2. Idempotent Seeding

An idempotent seed script can be re-run without creating duplicate data or causing unintended side effects. The simplest approach in a fresh test schema is resetting cleanly and running deterministic `INSERT`s.

If you need to re-run against a schema that already has data, you can:

- Delete only the fixtures matching a `test_run_id` or dedicated identifier key, then re-insert.
- Use upserts on a unique key if update semantics are clearly defined.
- Track batch IDs and seed status so the job knows what has already completed.

Do not use `INSERT IGNORE` to mask duplicates or data errors. `INSERT IGNORE` can silently skip invalid records and let tests proceed with missing fixtures. Be careful with `ON DUPLICATE KEY UPDATE` as well if a table has multiple unique keys, since a conflict can trigger on a key other than the one you intended.

### 5.3. Separating Fixtures by Purpose

Do not load one massive seed dataset for every test. Split fixtures by purpose:

- Minimal fixtures for repository and CRUD tests.
- Multi-table relational fixtures for join, cascade, and constraint tests.
- Boundary fixtures for `NULL`, empty strings, large numbers, leap days, and Unicode data.
- Conflict fixtures for duplicate keys, missing parents, and `CHECK`/FK violations.
- Larger performance fixtures loaded in dedicated benchmarks.

Each test should seed only the data it needs to minimize hidden coupling between tests.

## 6. Resetting Schema and Data

There are several ways to reset, each with different scope and limitations.

### 6.1. Dropping and Recreating the Schema

For integration tests verifying migrations from scratch, recreating the database is usually the clearest option:

```sql
DROP DATABASE IF EXISTS mysql_app_test;

CREATE DATABASE mysql_app_test
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
```

Then run all migrations and seeds. Only run this on an explicitly designated test database. `DROP DATABASE` deletes every table and row in the schema; never pass schema names from untrusted inputs into destructive scripts.

DDL such as `CREATE DATABASE`, `DROP DATABASE`, `CREATE TABLE`, `ALTER TABLE`, and `TRUNCATE TABLE` can trigger implicit commits. Do not wrap DDL reset statements in a transaction expecting `ROLLBACK` to restore the old schema.

### 6.2. Deleting Data with DELETE

When you want to keep the schema and reset only data, use `DELETE` in child-before-parent order:

```sql
START TRANSACTION;

DELETE FROM order_items;
DELETE FROM orders;
DELETE FROM customers;

COMMIT;
```

With InnoDB, delete statements inside a transaction can be rolled back if an error occurs before commit. `DELETE` does not automatically reset `AUTO_INCREMENT`; if tests use fixed IDs, this usually does not matter.

If you need to reset counters after tables are empty, you can reset `AUTO_INCREMENT`:

```sql
ALTER TABLE order_items AUTO_INCREMENT = 1;
ALTER TABLE orders AUTO_INCREMENT = 1;
ALTER TABLE customers AUTO_INCREMENT = 1;
```

`ALTER TABLE` is DDL and can trigger an implicit commit. Only do this when tables are empty and tests genuinely depend on the next generated value. A more resilient approach is seeding fixed IDs or writing tests without assuming auto-increment IDs are contiguous.

### 6.3. Using TRUNCATE with Its Limitations

`TRUNCATE TABLE` removes all rows quickly and usually resets `AUTO_INCREMENT`, but it is DDL with an implicit commit. InnoDB forbids truncating a table referenced by another table's foreign key, even if the child table currently contains no referencing rows. Therefore, you cannot arbitrarily replace ordered `DELETE` statements with a list of `TRUNCATE` statements.

You can use `TRUNCATE` on tables not referenced by any other table, or after handling schemas/constraints through a dedicated procedure. For tightly coupled tables, dependency-ordered `DELETE` or recreating the schema is usually safer and more predictable.

## 7. `FOREIGN_KEY_CHECKS` and What Not to Assume

MySQL has the `foreign_key_checks` variable to enable or disable foreign key checks at the session or global scope. Some bulk-loading tools temporarily disable checks to load data out of order, but this is not a standard test reset method.

Session-scope example:

```sql
SET SESSION foreign_key_checks = 0;

-- Controlled bulk load operations here.

SET SESSION foreign_key_checks = 1;
```

One crucial point: when re-enabling `foreign_key_checks=1`, MySQL does not scan rows loaded while checks were disabled to verify they satisfy constraints. Thus, re-enabling the variable does not prove the data contains no orphan rows.

If a bulk load must disable checks, include a separate validation step before the data is used. For example, finding orders without a customer:

```sql
SELECT o.id, o.customer_id
FROM orders AS o
LEFT JOIN customers AS c ON c.id = o.customer_id
WHERE c.id IS NULL;
```

Finding order items without an order:

```sql
SELECT i.id, i.order_id
FROM order_items AS i
LEFT JOIN orders AS o ON o.id = i.order_id
WHERE o.id IS NULL;
```

If these queries return rows, the data violates the expected relationships. Fix or remove the bad data before proceeding with tests.

Never disable `foreign_key_checks` globally for a test. A session variable affects only the current connection; when using a connection pool, make sure the session state is restored before returning the connection to the pool. A connection left with `foreign_key_checks=0` can cause subsequent tests to run with unintended behavior.

## 8. Transaction Rollback in Tests

A test can start a transaction, seed fixtures, invoke the logic under test, and then roll back to clean up data:

```sql
START TRANSACTION;

INSERT INTO customers (id, email, display_name)
VALUES (9001, 'rollback@example.test', 'Rollback Test');

SELECT * FROM customers WHERE id = 9001;

ROLLBACK;
```

This is fast and effective when:

- Tables use InnoDB or another transactional engine.
- The test and seed share the same transaction and connection.
- The code does not commit on its own or switch to another connection.
- No DDL or external side effects occur outside the transaction.

If the application opens a separate connection, calls `REQUIRES_NEW`, uses async workers, or processes tasks through a queue, the test transaction does not cover those operations. The test may roll back its main transaction while data committed on another connection remains.

In Spring tests with `@Transactional`, the test transaction is normally rolled back after the test. However, if the test invokes a service using different transaction propagation, spawns another thread, or runs DDL, verify the actual transaction boundaries. Never assume every operation inside a test rolls back solely because the test method is annotated.

## 9. Resetting in Parallel Tests

Two tests sharing one schema can trigger race conditions:

- Test A seeds customer `1001`.
- Test B resets the `customers` table.
- Test A reads the order, but the customer has been deleted.
- Test C uses the same order number and hits a duplicate key error.

To prevent conflicts:

- Use a separate database/schema per test worker or test class that performs destructive operations.
- If sharing a schema, scope fixtures with a namespace or `test_run_id` and never truncate/drop shared data.
- Never run a full-schema reset concurrently with other tests.
- Set timeouts and run cleanup in `finally`/lifecycle hooks, while still reporting cleanup failures.
- Use separate database containers when strong isolation and reproducible environments are needed.

Schema names can be generated from a run ID, provided you only interpolate identifiers generated and controlled by the test harness; SQL identifiers cannot be bound via JDBC placeholders like data values. Never concatenate database names from external inputs directly into `DROP DATABASE`.

## 10. Verifying Schema and Seed Data

After migrations and seeding, do not check only total row counts. Verify the schema, foreign keys, and required relationships.

Check tables and engines:

```sql
SELECT TABLE_NAME, ENGINE, TABLE_COLLATION
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'mysql_app_test'
ORDER BY TABLE_NAME;
```

Check foreign keys:

```sql
SELECT
  TABLE_NAME,
  CONSTRAINT_NAME,
  COLUMN_NAME,
  REFERENCED_TABLE_NAME,
  REFERENCED_COLUMN_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE CONSTRAINT_SCHEMA = 'mysql_app_test'
  AND REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY TABLE_NAME, CONSTRAINT_NAME;
```

Check fixture counts:

```sql
SELECT COUNT(*) AS customer_count FROM customers;
SELECT COUNT(*) AS order_count FROM orders;
SELECT COUNT(*) AS item_count FROM order_items;
```

Check relationships:

```sql
SELECT o.id, o.order_number, c.email
FROM orders AS o
JOIN customers AS c ON c.id = o.customer_id
ORDER BY o.id;

SELECT i.id, i.sku, o.order_number
FROM order_items AS i
JOIN orders AS o ON o.id = i.order_id
ORDER BY i.id;
```

For tests that must prove constraints work, write negative tests: try inserting an order with a nonexistent `customer_id` and verify MySQL returns a foreign key error. After a negative test, roll back or clean up state so subsequent fixtures are not polluted.

## 11. Practical Workflow for a Test Suite

An automatable workflow:

1. Start an isolated MySQL test instance or schema.
2. Create the database with compatible charset and collation.
3. Run Flyway/Liquibase from the first migration to the current version.
4. Verify tables, indexes, and foreign keys were created.
5. Seed parent tables before child tables following the dependency graph.
6. Verify fixture counts and relationships.
7. Run tests; prefer transaction rollback for self-contained DML tests.
8. For tests that must commit or migration tests, clean up child-before-parent or drop the dedicated schema.
9. Capture error logs and cleanup status; do not ignore cleanup failures.
10. Destroy the test container/schema once the suite finishes.

Separate migration tests from repository/service tests. Migration tests must start from an empty schema or a clearly prepared prior version; repository tests typically need small fixtures and fast execution.

## 12. Practice Exercise

An e-commerce application has tables `customers`, `orders`, `order_items`, and `payments`. `orders.customer_id` references `customers.id`; `order_items.order_id` and `payments.order_id` both reference `orders.id`. The team wants to run integration tests on MySQL 8.0 with multiple parallel workers.

Design the workflow and answer:

1. Write the statement to create the test schema with `utf8mb4` and a collation matching the application environment.
2. Why should shared migrations run instead of maintaining separate test-only DDL?
3. Determine the seeding order for the four tables and the reverse cleanup order.
4. Write a seed dataset with fixed IDs, emails, order numbers, and timestamps.
5. If a test only performs DML changes and uses InnoDB, when is transaction rollback appropriate?
6. Why can `TRUNCATE customers` be rejected even when `orders` is empty?
7. Why does re-enabling `foreign_key_checks=1` fail to verify rows loaded while checks were disabled?
8. Write queries to find orders without a customer and payments without an order.
9. How can you reset `AUTO_INCREMENT` without assuming IDs are always contiguous?
10. Propose a schema isolation strategy so two workers do not delete each other's data.
11. Design a negative test proving that the foreign key rejects a child record without a parent record.

A strong solution must specify where DDL runs, test account privileges, dependency ordering, transaction boundaries, and how data is cleaned up if a test fails mid-run.

## Conclusion

Reliable MySQL tests require an isolated schema, migrations shared with the application, deterministic fixtures, and operation ordering following the foreign key graph. Insert parent-before-child and clean up child-before-parent. Use transaction rollback for DML tests when all operations truly execute inside the same transaction; use separate schemas or migration resets for DDL tests. `TRUNCATE` triggers an implicit commit and is restricted by foreign keys; disabling `foreign_key_checks` does not make MySQL re-validate data when re-enabled. Verify schema, counts, relationships, and parallel safety before trusting a test suite.
