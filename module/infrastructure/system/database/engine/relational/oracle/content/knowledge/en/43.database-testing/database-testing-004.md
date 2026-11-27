# Creating/Resetting Schemas, Seeding Data, and Foreign Key Dependency Ordering

Testing applications using Oracle Database requires a data environment that is reproducible, starts from a well-defined initial state, and yields consistent results across runs. If leftover data from a previous test remains in the schema, foreign keys are not created in the proper order, or sequences keep generating unpredictable values, tests can flap between passing and failing even when the code has not changed.

The three foundational tasks for a test database are:

1. **Creating the schema:** preparing users, privileges, tablespaces, and objects required by the application.
2. **Resetting the schema:** returning the environment to a clean state or a known baseline.
3. **Seeding data:** loading test data in dependency order, especially primary key/foreign key relationships.

With Oracle, pay attention to a crucial difference: many DDL statements such as `CREATE`, `ALTER`, `DROP`, and `TRUNCATE` cause an implicit commit. Consequently, you cannot rely on `ROLLBACK` to undo a schema reset that involves DDL. You must design isolated test environments and controlled reset procedures.

## 1. Oracle schemas and object-owning users

In Oracle, a schema is the collection of database objects owned by a database user. The schema name normally matches the name of the user that owns the objects. For example, user `APP_TEST` owns the application's `CUSTOMERS` and `ORDERS` tables, packages, sequences, triggers, and views.

A test environment may use:

| User/schema | Purpose |
|---|---|
| `APP_OWNER` | Schema owning application objects in the standard environment or deployed via migrations |
| `APP_TEST` | Dedicated schema for integration tests |
| `APP_RUNTIME` | User simulating the application's connection account, granted only necessary privileges |
| `TEST_ADMIN` | Test environment admin account, granted scoped privileges to create/reset schemas |

Do not run tests as `SYS`, `SYSTEM`, or a DBA account. Broad administrative privileges can mask missing application privilege bugs and allow tests to accidentally mutate objects outside their scope.

### 1.1. Creating a test user/schema

A DBA or an account with appropriate privileges can create a dedicated test user. Example:

```sql
CREATE USER app_test
IDENTIFIED BY "Use-A-Secret-From-The-Test-Environment"
DEFAULT TABLESPACE users
TEMPORARY TABLESPACE temp
QUOTA 500M ON users;
```

In real environments, passwords must come from a secret store or CI credential injection mechanism, never committed to source control. Tablespace names and quotas must suit the environment. Quota limits the segment space a schema can allocate; granting `CREATE TABLE` without an appropriate quota can cause errors when creating objects.

Grant the minimal system privileges for the schema to run migrations/tests:

```sql
GRANT CREATE SESSION,
      CREATE TABLE,
      CREATE VIEW,
      CREATE SEQUENCE,
      CREATE PROCEDURE,
      CREATE TRIGGER,
      CREATE TYPE,
      CREATE SYNONYM
TO app_test;
```

The list above is only an example for a schema containing packages, triggers, types, and synonyms. If the application does not use a certain object type, omit the corresponding privilege. Some migrations may require specific additional privileges; determine them from the actual DDL rather than granting `DBA` or `ANY` privileges as a shortcut.

If tests need to create objects in another schema, design explicit privileges and verify exact requirements. Do not grant `CREATE ANY TABLE` or `DROP ANY TABLE` to a runtime user merely to simplify fixtures.

### 1.2. Separating owner and runtime privileges

A test suite can execute two verification groups:

- Migration/schema tests connecting as `APP_TEST` to create and alter objects.
- Application integration tests connecting as `APP_RUNTIME` to verify the exact privileges the production application will hold.

Example:

```sql
GRANT SELECT, INSERT, UPDATE, DELETE
ON app_test.orders
TO app_runtime;

GRANT SELECT
ON app_test.customers
TO app_runtime;
```

In Oracle, object privileges must be granted per object or through an appropriate role. If stored PL/SQL runs with `AUTHID DEFINER`, the program unit owner may require direct grants on objects in other schemas; privileges received solely through roles are insufficient in many cases for compiling/executing definer-rights code. Testing with the runtime user helps surface discrepancies between DBA privileges and application privileges.

## 2. Choosing a schema creation and reset strategy

No single reset approach fits every test. Choose based on runtime duration, isolation level, object count, and environment safety.

| Strategy | Approach | Best suited when |
|---|---|---|
| Fresh schema per test run | Create a dedicated user/schema, run migrations, seed, and drop upon completion | Parallel CI, strong isolation required |
| Dedicated test PDB/database | Create or clone a test database environment and run tests against it | Near-production environment and full reset needed |
| Drop/recreate schema | Drop the test user along with its objects and recreate | Dedicated test schema with administrative privileges |
| Drop/recreate objects | Drop objects in dependency order and re-run migrations | Keeping the user and schema configuration intact |
| Delete/truncate data | Keep structures, delete only data and re-seed | Repeated tests on a stable schema |
| Rollback transaction | Execute DML within a transaction and roll back | Single isolated tests not needing commits or post-commit checks |

### 2.1. Test environments must be isolated from production

Schema reset is a destructive operation. Use a dedicated test database/PDB/schema, dedicated accounts, dedicated service names, and dedicated secrets. CI should verify the database identity or a configuration marker before running a reset.

Never let default test environment variables point to production. Fail fast if the URL, `DB_UNIQUE_NAME`, PDB, or schema is not in the test allowlist. Checking only the username is insufficient: a production database could also contain a user named `APP_TEST`.

### 2.2. Dropping and recreating the user

In a dedicated test database, a DBA can drop the schema:

```sql
DROP USER app_test CASCADE;
```

`CASCADE` drops the user along with all objects in its schema. This operation cannot be undone with `ROLLBACK`. Execute only after verifying the right database and the right test user.

Recreate the user and grant privileges using a bootstrap script. Store user DDL, quotas, and grants in the repository or migration infrastructure so the environment can be rebuilt consistently.

### 2.3. Resetting by deleting data

If you prefer not to drop the schema every time, you can delete data from the tables. With foreign key relationships, delete child tables before parent tables unless the foreign key specifies `ON DELETE CASCADE`.

Example ordering:

```sql
DELETE FROM order_items;
DELETE FROM orders;
DELETE FROM customers;
DELETE FROM products;
```

This example assumes `ORDER_ITEMS` references `ORDERS` and `PRODUCTS`, while `ORDERS` references `CUSTOMERS`. If other child tables exist, place them in the proper dependency order.

`DELETE` is DML, so it can be rolled back before commit. However, in large transactions, undo/redo volume can be substantial. Delete triggers may fire and mutate additional data. Clearly decide whether a reset should fire triggers or not.

### 2.4. TRUNCATE vs. DELETE

`TRUNCATE TABLE` is usually faster than a full-table `DELETE` and reclaims/deallocates segment space according to Oracle semantics, but it is DDL and triggers an implicit commit. Truncates cannot be rolled back.

Example:

```sql
TRUNCATE TABLE app_test.order_items;
TRUNCATE TABLE app_test.orders;
TRUNCATE TABLE app_test.customers;
TRUNCATE TABLE app_test.products;
```

Ordering must still respect foreign keys. Oracle normally disallows truncating a parent table referenced by an enabled foreign key. Use truncate only in a dedicated test schema and after verifying constraints/dependencies. Never mass-disable constraints, truncate, and omit re-enabling and validating them.

### 2.5. Do not use ROLLBACK to reset DDL

Oracle implicitly commits before and after many DDL statements. Example:

```sql
DELETE FROM app_test.orders;
CREATE TABLE app_test.tmp_test (id NUMBER);
ROLLBACK;
```

The `DELETE` before the DDL may already be implicitly committed before `CREATE TABLE` executes. The trailing `ROLLBACK` will not restore the deleted rows. This is why schema resets must be treated as a distinct workflow, not a single transaction.

## 3. Building schemas via migrations

In Spring Boot applications, schemas should be built from versioned migrations rather than relying on a manual schema on a developer machine.

Common tools include Flyway and Liquibase. They store migration history and apply scripts in a defined order. Integration tests should use the exact same migrations as the deployment environment to catch DDL errors, missing indexes, constraints, or sequences.

### 3.1. Migration ordering

Example:

```text
V001__create_customers.sql
V002__create_products.sql
V003__create_orders.sql
V004__create_order_items.sql
V005__create_order_indexes.sql
V006__create_order_api.sql
```

This order creates parent tables before child tables, then indexes and program units depending on those tables. Actual ordering depends on dependencies across objects, not solely across tables.

### 3.2. Oracle DDL and migration transactions

Many Oracle DDL statements trigger implicit commits. Thus, migration tools cannot assume every DDL statement can be rolled back like DML. If a migration fails mid-way, the schema may end up in a partially applied state. Migration tools typically record history and provide mechanisms to detect failed migrations, but recovery must follow the tool's and script's guidelines.

Write small, clearly ordered migrations whose state is easy to determine upon failure. Do not bundle hundreds of unrelated DDL operations into one hard-to-recover script.

### 3.3. Create the schema before seeding

A standard workflow is typically:

1. Provision the test database/PDB/schema.
2. Grant quotas and privileges.
3. Run migrations to create objects.
4. Verify migrations completed.
5. Seed reference/master data.
6. Seed business data in dependency order.
7. Run tests.
8. Delete/reset data or tear down the test schema.

Never seed data into a schema that has not run all migrations. When the schema version changes, seed scripts must also remain compatible with that version.

## 4. Example model with foreign key relationships

Suppose a sales system has four tables:

- `CUSTOMERS`: customers.
- `PRODUCTS`: products.
- `ORDERS`: orders, referencing customers.
- `ORDER_ITEMS`: order line items, referencing orders and products.

Relationships:

```text
CUSTOMERS                 PRODUCTS
    |                         |
    | 1                       | 1
    v                         v
  ORDERS  ----------------> ORDER_ITEMS
       1                         *
```

Insert dependency graph:

```text
CUSTOMERS ─────┐
               v
             ORDERS ──────┐
                          v
PRODUCTS ─────────────> ORDER_ITEMS
```

`ORDERS` requires `CUSTOMERS` first. `ORDER_ITEMS` requires both `ORDERS` and `PRODUCTS` first. Therefore, a valid seed order is:

1. `CUSTOMERS`
2. `PRODUCTS`
3. `ORDERS`
4. `ORDER_ITEMS`

Data deletion order follows reverse dependencies:

1. `ORDER_ITEMS`
2. `ORDERS`
3. `CUSTOMERS`
4. `PRODUCTS`

`CUSTOMERS` and `PRODUCTS` do not depend on each other, so either can be seeded first. What matters is that every parent exists before inserting any child.

## 5. Creating tables and foreign keys

DDL example:

```sql
CREATE TABLE customers (
    customer_id   NUMBER(12) CONSTRAINT pk_customers PRIMARY KEY,
    customer_name VARCHAR2(200) NOT NULL,
    email         VARCHAR2(320),
    created_at    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT uq_customers_email UNIQUE (email)
);

CREATE TABLE products (
    product_id   NUMBER(12) CONSTRAINT pk_products PRIMARY KEY,
    product_name VARCHAR2(200) NOT NULL,
    unit_price   NUMBER(12,2) NOT NULL,
    CONSTRAINT ck_products_price CHECK (unit_price >= 0)
);

CREATE TABLE orders (
    order_id     NUMBER(12) CONSTRAINT pk_orders PRIMARY KEY,
    customer_id  NUMBER(12) NOT NULL,
    order_date   DATE NOT NULL,
    order_status VARCHAR2(20) NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
);

CREATE TABLE order_items (
    order_item_id NUMBER(12) CONSTRAINT pk_order_items PRIMARY KEY,
    order_id      NUMBER(12) NOT NULL,
    product_id    NUMBER(12) NOT NULL,
    quantity      NUMBER(10) NOT NULL,
    unit_price    NUMBER(12,2) NOT NULL,
    CONSTRAINT fk_items_order
        FOREIGN KEY (order_id)
        REFERENCES orders(order_id),
    CONSTRAINT fk_items_product
        FOREIGN KEY (product_id)
        REFERENCES products(product_id),
    CONSTRAINT ck_items_quantity CHECK (quantity > 0)
);
```

Constraints are named explicitly to make testing and troubleshooting easier to read. Constraint names also help pinpoint the exact error when inserting invalid data. In large schemas, follow naming conventions like `PK_`, `FK_`, `UK_`, and `CK_`, ensuring names are unique within Oracle's required scope.

### 5.1. Primary keys and unique keys

A primary key uniquely identifies each row and disallows `NULL`. A unique constraint enforces that values or combinations of values do not duplicate per Oracle semantics. For unique keys containing `NULL`, understand that Oracle allows multiple rows with `NULL` in certain cases; do not use a unique constraint as a way to require every row to have a value. If a column must be both unique and non-null, combine `NOT NULL` with `UNIQUE`.

### 5.2. Foreign keys

A foreign key ensures that values in the child table reference a valid key in the parent table. When inserting a child, the parent key must exist. When deleting a parent, Oracle rejects the deletion if referencing child rows exist, unless the constraint declares `ON DELETE CASCADE` or another behavior.

Example:

```sql
INSERT INTO orders(order_id, customer_id, order_date, order_status)
VALUES (1001, 501, DATE '2026-11-01', 'NEW');
```

This statement fails with a foreign key error if `CUSTOMERS.CUSTOMER_ID = 501` does not exist yet.

### 5.3. Indexes on foreign keys

Oracle does not automatically create an index on a foreign key just because a constraint is declared. An index on FK columns is often useful for joins and can reduce locking/contention during certain parent update/delete operations. Example:

```sql
CREATE INDEX ix_orders_customer_id
    ON orders(customer_id);

CREATE INDEX ix_items_order_id
    ON order_items(order_id);

CREATE INDEX ix_items_product_id
    ON order_items(product_id);
```

Not every foreign key needs an index immediately; evaluate workload and table size. However, for large child tables or parents whose keys are frequently updated/deleted, evaluate indexing the FK.

## 6. Seeding data in parent-child order

Seed data is initial data loaded so tests can execute against a known state. Seed data should:

- Have deterministic keys that tests can reference.
- Contain values sufficient to cover business cases.
- Be repeatable or resettable.
- Not depend on leftover data from prior runs.
- Avoid real personal data unless necessary.

Example seeding parents first:

```sql
INSERT INTO customers(customer_id, customer_name, email)
VALUES (501, 'Test Customer A', 'customer-a@example.test');

INSERT INTO customers(customer_id, customer_name, email)
VALUES (502, 'Test Customer B', 'customer-b@example.test');

INSERT INTO products(product_id, product_name, unit_price)
VALUES (9001, 'Test Product A', 125.50);

INSERT INTO products(product_id, product_name, unit_price)
VALUES (9002, 'Test Product B', 80.00);
```

Then insert orders:

```sql
INSERT INTO orders(order_id, customer_id, order_date, order_status)
VALUES (1001, 501, DATE '2026-11-01', 'NEW');

INSERT INTO orders(order_id, customer_id, order_date, order_status)
VALUES (1002, 502, DATE '2026-11-02', 'PAID');
```

Finally insert order items:

```sql
INSERT INTO order_items(
    order_item_id, order_id, product_id, quantity, unit_price
)
VALUES (1, 1001, 9001, 2, 125.50);

INSERT INTO order_items(
    order_item_id, order_id, product_id, quantity, unit_price
)
VALUES (2, 1001, 9002, 1, 80.00);

INSERT INTO order_items(
    order_item_id, order_id, product_id, quantity, unit_price
)
VALUES (3, 1002, 9001, 1, 125.50);

COMMIT;
```

The `COMMIT` at the end persists the seed data once the script completes. If seeding runs inside a framework-managed test transaction, a manual commit may not be needed; choose one consistent approach.

### 6.1. Why not seed children first?

If `ORDER_ITEMS` is inserted before `ORDERS`, foreign key `FK_ITEMS_ORDER` cannot find the parent and Oracle raises `ORA-02291: integrity constraint violated - parent key not found`.

Similarly, `ORDERS` cannot reference a non-existent customer. This error is not a random Oracle failure; it is the intended outcome of referential integrity.

### 6.2. Seed data should be meaningful

Do not merely populate rows with values `1`, `2`, `3` unrelated to test scenarios. Choose data that expresses business semantics:

| Customer | Order | Status | Items | Test objective |
|---|---|---|---|---|
| 501 | 1001 | NEW | 2 rows | New order with multiple products |
| 502 | 1002 | PAID | 1 row | Paid order |
| 501 | 1003 | CANCELLED | None | Cancelled order and itemless edge case |

Meaningful data makes assertions easier to read and helps uncover mapping or join bugs.

## 7. Computing table dependency order

In schemas with many tables, do not guess the seed order manually. Foreign keys can be modeled as a directed graph:

- Each table is a node.
- An edge `PARENT -> CHILD` exists if the child has a foreign key referencing the parent.
- Topological sort yields a valid insert order if the graph is acyclic.
- Delete order is the reverse order.

Example:

```text
COUNTRIES ──> CUSTOMERS ──> ORDERS ──> ORDER_ITEMS
                           ^             ^
                           |             |
PRODUCTS ──────────────────┴─────────────┘
```

In this example, `ORDERS` references `CUSTOMERS`, and `ORDER_ITEMS` references `ORDERS` and `PRODUCTS`. `COUNTRIES` can be a parent of `CUSTOMERS`.

### 7.1. Inspecting foreign keys in the data dictionary

`USER_CONSTRAINTS` lists constraints in the current schema. For foreign keys, `CONSTRAINT_TYPE = 'R'`; `R_CONSTRAINT_NAME` points to the referenced constraint on the parent table.

```sql
SELECT child.table_name       AS child_table,
       child.constraint_name  AS fk_name,
       parent.table_name      AS parent_table,
       child.status,
       child.deferrable,
       child.deferred
FROM user_constraints child
JOIN user_constraints parent
  ON parent.constraint_name = child.r_constraint_name
 AND parent.owner = child.r_owner
WHERE child.constraint_type = 'R'
ORDER BY parent.table_name, child.table_name;
```

In the current schema, `USER_CONSTRAINTS` suffices; for cross-schema inspection, use `ALL_CONSTRAINTS` or `DBA_CONSTRAINTS` with the corresponding owner columns. Check both `STATUS` and `VALIDATED` to see if the constraint is enabled/disabled and whether existing data has been validated.

### 7.2. Inspecting foreign key columns

```sql
SELECT c.table_name,
       c.constraint_name,
       cc.column_name,
       cc.position
FROM user_constraints c
JOIN user_cons_columns cc
  ON cc.constraint_name = c.constraint_name
 AND cc.table_name = c.table_name
WHERE c.constraint_type = 'R'
ORDER BY c.table_name, c.constraint_name, cc.position;
```

For composite foreign keys, column order is critical. Map each child column to its parent column by `POSITION`; do not rely solely on the constraint name.

### 7.3. Topological sort

For an acyclic graph, Kahn's algorithm can be used:

1. Compute the in-degree of each table as the number of unresolved parent dependencies.
2. Enqueue tables with an in-degree of 0.
3. Dequeue a table and append it to the insert order.
4. For each child of that table, decrement the child's in-degree.
5. When a child's in-degree reaches 0, enqueue the child.
6. If nodes remain unprocessed at the end, the graph contains a cycle.

The result is a parent-before-child seed order. To reset via delete, reverse this order.

Not every schema requires implementing this algorithm manually. For a handful of tables, an ordered list in migrations/fixtures is enough. For large schemas or test frameworks that auto-discover dependencies, metadata-driven topological sort prevents overlooking relationships.

## 8. Composite foreign keys and multiple parents

A child table can reference multiple parents or use composite keys. Example:

```sql
CREATE TABLE order_allocations (
    order_id    NUMBER(12) NOT NULL,
    warehouse_id NUMBER(12) NOT NULL,
    allocation_no NUMBER(4) NOT NULL,
    CONSTRAINT pk_order_allocations
        PRIMARY KEY (order_id, warehouse_id, allocation_no),
    CONSTRAINT fk_alloc_order
        FOREIGN KEY (order_id)
        REFERENCES orders(order_id),
    CONSTRAINT fk_alloc_warehouse
        FOREIGN KEY (warehouse_id)
        REFERENCES warehouses(warehouse_id)
);
```

Before seeding `ORDER_ALLOCATIONS`, both the order and the warehouse must exist. With a composite foreign key, a parent key matching the exact column combination must exist. Having individual column values exist separately in the parent is insufficient if the combined tuple does not match.

Example:

```sql
FOREIGN KEY (country_code, region_code)
REFERENCES regions(country_code, region_code)
```

The child row must reference an existing `(country_code, region_code)` pair. Seed the parent with that exact pair first.

## 9. Cyclic relationships and deferrable foreign keys

Topological sort only produces a linear order if the dependency graph is acyclic. Some schemas have cyclic relationships, for example:

```text
EMPLOYEES.manager_id -> EMPLOYEES.employee_id
DEPARTMENTS.manager_id -> EMPLOYEES.employee_id
EMPLOYEES.department_id -> DEPARTMENTS.department_id
```

Here an employee belongs to a department, the department has an employee as manager, and an employee can reference another manager. If columns are all `NOT NULL` and foreign keys are immediate, seeding may have no valid linear insert order.

### 9.1. Insert NULL first then UPDATE

If business rules allow the referencing column to start as `NULL`, you can create the parent first and update the relationship afterward:

```sql
INSERT INTO employees(employee_id, department_id, manager_id, employee_name)
VALUES (10, 100, NULL, 'Manager A');

INSERT INTO departments(department_id, department_name, manager_id)
VALUES (100, 'Engineering', 10);

INSERT INTO employees(employee_id, department_id, manager_id, employee_name)
VALUES (11, 100, 10, 'Developer B');
```

This is typically straightforward if `MANAGER_ID` is allowed to be `NULL` during creation. Update later once both sides exist.

### 9.2. DEFERRABLE constraints

Oracle supports `DEFERRABLE` constraints, allowing constraint validation to be deferred until the end of the transaction when set to deferred state.

Example:

```sql
CREATE TABLE departments (
    department_id NUMBER(12) PRIMARY KEY,
    manager_id    NUMBER(12),
    department_name VARCHAR2(100) NOT NULL,
    CONSTRAINT fk_department_manager
        FOREIGN KEY (manager_id)
        REFERENCES employees(employee_id)
        DEFERRABLE INITIALLY DEFERRED
);
```

And the reverse-referencing constraint:

```sql
CREATE TABLE employees (
    employee_id   NUMBER(12) PRIMARY KEY,
    department_id NUMBER(12) NOT NULL,
    manager_id    NUMBER(12),
    employee_name VARCHAR2(100) NOT NULL,
    CONSTRAINT fk_employee_department
        FOREIGN KEY (department_id)
        REFERENCES departments(department_id)
        DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT fk_employee_manager
        FOREIGN KEY (manager_id)
        REFERENCES employees(employee_id)
        DEFERRABLE INITIALLY DEFERRED
);
```

This DDL example only illustrates deferrability; in an actual schema, create objects in an order that references existing objects, or add constraints via `ALTER TABLE` after creating both tables.

Inside a transaction:

```sql
SET CONSTRAINTS ALL DEFERRED;

INSERT INTO departments(department_id, manager_id, department_name)
VALUES (100, 10, 'Engineering');

INSERT INTO employees(employee_id, department_id, manager_id, employee_name)
VALUES (10, 100, NULL, 'Manager A');

COMMIT;
```

Foreign keys are checked on commit. If still unsatisfied at transaction end, the commit fails. `SET CONSTRAINTS` applies only to constraints declared `DEFERRABLE`; `NOT DEFERRABLE` constraints cannot be switched to deferred.

### 9.3. INITIALLY IMMEDIATE and INITIALLY DEFERRED

- `DEFERRABLE INITIALLY IMMEDIATE`: checked immediately by default, though a transaction can switch it to deferred.
- `DEFERRABLE INITIALLY DEFERRED`: checked at commit by default.
- `NOT DEFERRABLE`: always checked immediately and cannot be deferred.

Deferrable constraints can help when importing/testing cyclic data, but should not be used merely to mask an unthought-out seed order. They shift when errors are detected: an `INSERT` statement succeeds, only for the commit to fail later.

### 9.4. Temporarily disabling constraints

Oracle allows disabling constraints:

```sql
ALTER TABLE order_items
DISABLE CONSTRAINT fk_items_order;
```

After loading data, re-enable and validate:

```sql
ALTER TABLE order_items
ENABLE VALIDATE CONSTRAINT fk_items_order;
```

`ENABLE VALIDATE` verifies that all existing data satisfies the constraint. If data is invalid, enabling with validate fails. `ENABLE NOVALIDATE` exists for certain migration scenarios, though legacy data remains unchecked. Standard tests should favor enabled/validated constraints to catch referential errors early.

Do not disable foreign keys on every seed run. Doing so removes a critical verification layer and can allow tests to pass with data that production would reject.

## 10. Sequences and identity columns when seeding data

Many Oracle tables use sequences or identity columns to generate keys. Tests must decide whether to use fixed IDs or database-generated IDs.

### 10.1. Seeding fixed IDs

For readable fixtures, deterministic IDs can be inserted if the column is a regular numeric column:

```sql
INSERT INTO customers(customer_id, customer_name)
VALUES (501, 'Test Customer A');
```

Fixed IDs make referencing data in tests straightforward. However, if the production schema uses a sequence, avoid collisions between seeded IDs and upcoming sequence values.

Sequence example:

```sql
CREATE SEQUENCE customer_seq START WITH 1000 INCREMENT BY 1 CACHE 20;
```

If manually seeding `CUSTOMER_ID = 501`, a sequence starting at 1000 will not collide with that ID. When seeding IDs higher than the sequence's next value, synchronize the sequence or choose another seeding strategy.

### 10.2. Obtaining IDs from sequences

```sql
INSERT INTO customers(customer_id, customer_name)
VALUES (customer_seq.NEXTVAL, 'Generated Customer');
```

In Java applications, you can fetch `NEXTVAL` via `JdbcTemplate` or use the sequence inside `INSERT`. Do not rely on contiguous or gap-free sequence values. Transaction rollbacks do not return issued sequence values.

### 10.3. Identity columns

Modern Oracle versions support identity columns:

```sql
CREATE TABLE test_events (
    event_id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    event_name VARCHAR2(100) NOT NULL
);
```

`GENERATED ALWAYS AS IDENTITY` instructs the database to always generate the value and normally disallows explicit inserts. `GENERATED BY DEFAULT` permits providing an explicit value on insert; `BY DEFAULT ON NULL` has specific semantics when `NULL` is supplied.

If tests require fixed IDs, choose the appropriate identity mode or use dedicated fixture tables/sequences. Syntax for restarting identity counters varies by Oracle version; do not assume a single `ALTER TABLE ... RESTART` works across all releases. In a dedicated test schema, dropping/recreating objects or sequences via a clean procedure is usually easier to control.

### 10.4. Sequences do not reset on DELETE

Deleting all rows from a table does not reset a sequence to its initial value. A sequence is an independent object with its own cache and metadata. If a test requires a sequence to start at a specific value, reset it using a version-supported method or drop/recreate it in an isolated test environment.

Never reset a sequence while the application or other tests are actively sharing the same schema. Doing so can cause duplicate keys or interfere with parallel tests.

## 11. Designing repeatable seed scripts

Seed scripts often run across multiple contexts: provisioning a new environment, refreshing a local database, integration tests, or CI. Clearly distinguish which scripts run once and which can run repeatedly.

### 11.1. Plain inserts for clean schemas

If every test run creates a fresh schema, plain `INSERT` statements with fixed keys are simple and catch unexpected duplicates immediately:

```sql
INSERT INTO products(product_id, product_name, unit_price)
VALUES (9001, 'Test Product A', 125.50);
```

If executed twice on the same schema, the second run violates the primary key. This can be desirable behavior as it detects an incomplete reset.

### 11.2. MERGE for idempotent reference data

For reference data that must be guaranteed to exist after every bootstrap, `MERGE` makes seeding repeatable:

```sql
MERGE INTO app_test.order_statuses t
USING (
    SELECT 'NEW' AS status_code, 'New order' AS status_name FROM dual
    UNION ALL
    SELECT 'PAID', 'Paid order' FROM dual
    UNION ALL
    SELECT 'CANCELLED', 'Cancelled order' FROM dual
) s
ON (t.status_code = s.status_code)
WHEN MATCHED THEN
    UPDATE SET t.status_name = s.status_name
WHEN NOT MATCHED THEN
    INSERT (status_code, status_name)
    VALUES (s.status_code, s.status_name);
```

`MERGE` stabilizes reference data seeding, though you must decide whether existing values should be updated. For test fixture data, overwriting rows can mask stale state; a clean schema reset is usually clearer.

### 11.3. Using SQL*Plus/SQLcl scripts

A bootstrap script can invoke files in order:

```sql
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK

PROMPT Seeding customers and products
@seed/01_customers.sql
@seed/02_products.sql
PROMPT Seeding orders
@seed/03_orders.sql
PROMPT Seeding order items
@seed/04_order_items.sql

COMMIT;
PROMPT Seed completed
EXIT SUCCESS
```

`WHENEVER SQLERROR` halts the script upon SQL errors. However, it does not undo DDL that previously committed implicitly. Separate DDL migrations from DML seeding and define clear transaction boundaries.

## 12. Seeding data with Java/Spring Boot

Beyond SQL scripts, tests can load fixtures using `JdbcTemplate` or `NamedParameterJdbcTemplate`. This is useful when data is constructed from test objects or needs immediate inspection in Java.

### 12.1. Seeding in explicit order

```java
@Component
public class OrderTestDataSeeder {

    private final JdbcTemplate jdbc;

    public OrderTestDataSeeder(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void seed() {
        jdbc.update("""
            INSERT INTO customers(customer_id, customer_name, email)
            VALUES (?, ?, ?)
            """, 501L, "Test Customer A", "customer-a@example.test");

        jdbc.update("""
            INSERT INTO products(product_id, product_name, unit_price)
            VALUES (?, ?, ?)
            """, 9001L, "Test Product A", new BigDecimal("125.50"));

        jdbc.update("""
            INSERT INTO orders(order_id, customer_id, order_date, order_status)
            VALUES (?, ?, ?, ?)
            """, 1001L, 501L,
                Timestamp.valueOf(LocalDateTime.of(2026, 11, 1, 10, 0)), "NEW");

        jdbc.update("""
            INSERT INTO order_items(
                order_item_id, order_id, product_id, quantity, unit_price
            ) VALUES (?, ?, ?, ?, ?)
            """, 1L, 1001L, 9001L, 2,
                new BigDecimal("125.50"));
    }
}
```

Statement order reflects dependencies. Monetary values use `BigDecimal` to preserve precision. Oracle `DATE` stores time down to seconds; when passing Java timestamps, verify JDBC mapping matches the column type.

### 12.2. Separating fixtures from production startup

Never automatically load test fixtures when the production application starts. Use dedicated profiles such as `test`, `@TestConfiguration`, test SQL resources, or test framework annotations. Prevent seeder components from being accidentally enabled in production.

### 12.3. @Sql in Spring Test

Spring Test supports `@Sql` to run scripts before/after tests:

```java
@SpringBootTest
@Sql(
    scripts = {
        "/db/test/cleanup.sql",
        "/db/test/seed.sql"
    },
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
class OrderRepositoryIT {
    // tests
}
```

`cleanup.sql` must delete children before parents. If the test method runs inside a Spring Test-managed transaction, scripts and tests may participate in that transaction depending on configuration. Check transaction mode and execution phase to avoid assuming DML has committed when it will actually roll back after the test.

### 12.4. Testing transactions and real commits

Spring Test typically rolls back a test transaction after a method finishes if the test runs transactionally. This is a fast way to isolate DML. However, some scenarios require testing real commit behavior, such as:

- Transaction boundaries across multiple service calls.
- Triggers or jobs that only run post-commit.
- Data visibility from another connection.
- Locking and isolation behavior.
- Outbox entries or events emitted after commit.

In such tests, configure transactions explicitly, using `@Commit` or `@Rollback(false)` where appropriate, and clean up manually afterward. Do not enable commits globally across the entire test suite arbitrarily.

## 13. Resetting data in dependency order

When tests share a schema, cleanup must reverse the insert order. For the sales example:

```sql
DELETE FROM order_items;
DELETE FROM orders;
DELETE FROM customers;
DELETE FROM products;
COMMIT;
```

Since `ORDER_ITEMS` references both `ORDERS` and `PRODUCTS`, `ORDER_ITEMS` must be deleted before both parents. Then delete `ORDERS` before `CUSTOMERS`.

### 13.1. Multi-table cleanup

For large schemas, store dependency ordering in scripts or fixture tooling. Never delete parents, catch FK errors, and continue. Cleanup failures should fail test setup so tests do not execute against an unknown data state.

### 13.2. ON DELETE CASCADE

If a foreign key declares `ON DELETE CASCADE`, deleting a parent can automatically delete related children:

```sql
CONSTRAINT fk_items_order
    FOREIGN KEY (order_id)
    REFERENCES orders(order_id)
    ON DELETE CASCADE
```

This can simplify cleanup, but it is a business/schema design decision—do not add it just to make tests easier. Cascading can delete far more rows than expected if fixtures are widely referenced. Check affected row counts and use it only when semantics fit.

### 13.3. TRUNCATE and foreign keys

Truncate does not follow standard delete cascade semantics. A referenced parent table may fail to truncate. In practice, truncate children first, then parents; or drop/recreate the schema in an isolated test environment.

Do not use `TRUNCATE` if delete triggers must fire or rollback is needed. `TRUNCATE` does not fire row-by-row delete triggers like `DELETE`.

## 14. Verifying foreign keys and seed data

After seeding, verify that referential data is valid and constraints are enabled/validated.

### 14.1. Checking constraint status

```sql
SELECT table_name,
       constraint_name,
       constraint_type,
       status,
       validated,
       deferrable,
       deferred
FROM user_constraints
WHERE constraint_type IN ('P', 'U', 'R')
ORDER BY table_name, constraint_type, constraint_name;
```

`STATUS = ENABLED` indicates the constraint is active. `VALIDATED = VALIDATED` indicates existing data has been checked against the constraint. For a clean test schema, required constraints should normally be `ENABLED` and `VALIDATED`.

### 14.2. Finding orphaned child rows

Example checking for orders without a matching customer:

```sql
SELECT o.order_id,
       o.customer_id
FROM orders o
WHERE NOT EXISTS (
    SELECT 1
    FROM customers c
    WHERE c.customer_id = o.customer_id
);
```

If the foreign key is enabled/validated, this query must return zero rows. If rows are returned, investigate whether the constraint was disabled/novalidated or data was loaded through another path.

### 14.3. Reconciling seed row counts

```sql
SELECT 'CUSTOMERS' AS table_name, COUNT(*) AS row_count FROM customers
UNION ALL
SELECT 'PRODUCTS', COUNT(*) FROM products
UNION ALL
SELECT 'ORDERS', COUNT(*) FROM orders
UNION ALL
SELECT 'ORDER_ITEMS', COUNT(*) FROM order_items;
```

Tests should verify expected fixture counts and critical keys. Do not merely verify that a script threw no errors; a script might succeed while missing a file or skipping part of a fixture.

## 15. Deterministic seed data and parallel tests

Deterministic seeding means the same setup produces identical logical data and reference keys. This makes tests reproducible.

### 15.1. Avoid current-time-dependent data

If fixtures use `SYSDATE` or `SYSTIMESTAMP`, results may vary across runs. While occasionally needed to test "current" logic, inject clocks or use fixed dates in fixtures for standard tests.

Example:

```sql
INSERT INTO orders(order_id, customer_id, order_date, order_status)
VALUES (1001, 501, DATE '2026-11-01', 'NEW');
```

ANSI literal `DATE 'YYYY-MM-DD'` is independent of `NLS_DATE_FORMAT`. For timestamps with fractional seconds, use `TIMESTAMP 'YYYY-MM-DD HH24:MI:SS.FF'` with the appropriate literal syntax.

### 15.2. Do not rely on contiguous sequence values

Sequences can cache and exhibit gaps. Tests must never assume the first call always returns 1 or the second always returns 2. When needed, capture the returned value and use it in subsequent operations.

### 15.3. Parallel tests require isolated schemas/databases

Two test suites deleting and seeding the same schema simultaneously will corrupt each other's data. For instance, test A reads `ORDERS` while test B runs `DELETE FROM ORDERS` cleanup. Outcomes become timing-dependent and hard to reproduce.

Options:

- Give each CI worker its own schema.
- Give each test suite its own PDB/container database.
- Use isolated tenant/test keys and scope all queries/cleanups to that key.
- Serialize tests that reset a shared schema if isolation is not possible.

Simply adding `@DirtiesContext` does not create database isolation; it refreshes the Spring `ApplicationContext`, without resetting the Oracle schema separately.

## 16. Testing with containers or dedicated test databases

Oracle can run in supported container environments or use a dedicated test database provisioned by the organization. For Oracle, use authorized images/editions under appropriate usage terms; do not assume any arbitrary database image is licensed for all environments.

Testcontainers can spin up a test-scoped database and tear it down after the suite finishes. However, startup time, image size, license/terms, and Oracle version configuration must be weighed.

A common strategy:

1. Provision the Oracle test database/PDB.
2. Run Flyway/Liquibase migrations.
3. Run seed scripts.
4. Execute integration tests.
5. Destroy the database/container upon completion.

The advantage is an independent baseline per run. The trade-off is higher resource and time cost than sharing a schema.

## 17. Rebuilding schemas in CI/CD

CI should implement a reproducible pipeline:

```text
Provision test database/schema
          |
          v
Create user and grants
          |
          v
Run versioned migrations
          |
          v
Load deterministic seed
          |
          v
Run integration tests
          |
          v
Collect logs and test results
          |
          v
Drop schema / destroy test database
```

### 17.1. Fail-fast before reset

Before running reset commands, scripts should check:

- JDBC URL/service/PDB matches the test environment.
- Database unique name or test marker is in the allowlist.
- Target user schema is on the reset allowlist.
- CI run ID or worker ID is attached to the schema when running in parallel.
- Credentials are test credentials.

If any check fails, abort the pipeline before executing destructive DDL.

### 17.2. Logging and reconciliation

Save logs from migrations, seeding, cleanup, and tests. On failure, you need to know which script ran, which migration succeeded, whether seeding committed, and what state the schema is left in.

Do not save just a single line reading "database setup failed". Preserve SQL error codes, script names, migration versions, and test run IDs, while avoiding logging credentials or sensitive data.

## 18. Common errors when building schemas and seeding

| Error | Common cause | Mitigation |
|---|---|---|
| `ORA-01031: insufficient privileges` | User lacks system/object privileges to create objects or run migrations | Identify which privileges the DDL needs; grant minimally to schema owner |
| `ORA-01950: no privileges on tablespace` | Schema lacks quota on tablespace | Grant appropriate quota or select the right tablespace |
| `ORA-00955: name is already used by an existing object` | Reset failed to drop old objects or migration re-ran | Check objects and migration history; never drop arbitrarily |
| `ORA-02291: parent key not found` | Child seeded before parent or wrong parent key | Fix dependency order and reference keys |
| `ORA-02292: child record found` | Deleting parent while child rows still exist | Clean up child-before-parent or use appropriate cascade semantics |
| `ORA-00001: unique constraint violated` | Duplicate key seeded or script re-executed | Reset properly, use intentional `MERGE`, or isolate fixture IDs |
| `ORA-02266`/truncate error due to FK | Parent referenced by foreign key | Truncate children first or use another reset strategy |
| Committed but test still cannot see data | Test uses a different DataSource/schema/PDB or transaction visibility | Check connection URL, schema, transaction, and service |
| Individual test passes but suite fails | Data leaks between tests or execution order dependency | Isolate schemas, clean up, and remove order dependencies |
| Sequence generates conflicting fixture IDs | Sequence next value is lower than seeded IDs | Sync sequence or separate fixture IDs from sequence range |
| Parallel tests fail intermittently | Multiple workers resetting the same schema | Give each worker a separate schema/PDB or serialize |
| Rollback fails to restore schema | DDL/Truncate triggered implicit commit | Rebuild schema from migrations; never rely on rolling back DDL |

## 19. Sample script structure for a test schema

A database test directory can be organized as:

```text
src/test/resources/db/oracle/
  migration/
    V001__create_customers.sql
    V002__create_products.sql
    V003__create_orders.sql
    V004__create_order_items.sql
  seed/
    01_customers.sql
    02_products.sql
    03_orders.sql
    04_order_items.sql
  cleanup/
    01_order_items.sql
    02_orders.sql
    03_customers.sql
    04_products.sql
```

Migrations run parent before child. Seeding also runs parent before child. Cleanup runs child before parent.

### 19.1. Seed script with explicit transaction boundaries

Example `seed/01_customers.sql`:

```sql
INSERT INTO customers(customer_id, customer_name, email)
VALUES (501, 'Test Customer A', 'customer-a@example.test');

INSERT INTO customers(customer_id, customer_name, email)
VALUES (502, 'Test Customer B', 'customer-b@example.test');
```

Subsequent seed scripts insert products, orders, and order items. An orchestrating script can commit once all seeding finishes. If a seed file fails before commit, prior DML can roll back provided no DDL or implicit commit occurred in between.

### 19.2. Cleanup script

```sql
DELETE FROM order_items;
DELETE FROM orders;
DELETE FROM customers;
DELETE FROM products;
COMMIT;
```

If using `TRUNCATE`, the operation is DDL and cannot be rolled back. Use it only in a dedicated test schema after confirming order and constraints.

### 19.3. Fixture verification

```sql
DECLARE
    l_customers NUMBER;
    l_products  NUMBER;
    l_orders    NUMBER;
    l_items     NUMBER;
BEGIN
    SELECT COUNT(*) INTO l_customers FROM customers;
    SELECT COUNT(*) INTO l_products FROM products;
    SELECT COUNT(*) INTO l_orders FROM orders;
    SELECT COUNT(*) INTO l_items FROM order_items;

    IF l_customers <> 2 OR l_products <> 2
       OR l_orders <> 2 OR l_items <> 3 THEN
        RAISE_APPLICATION_ERROR(-20001, 'Unexpected seed row counts');
    END IF;
END;
/
```

This is a setup-level assertion. Business tests still need to assert query results and application behavior, not merely row counts.

## 20. Principles for reliable resets and seeding

A sound test environment should adhere to these principles:

1. **Isolation:** tests never touch production schemas or databases.
2. **Reproducibility:** migrations and seeds can run from a clean state.
3. **Ordering:** objects are created in dependency order; parent data is seeded before children.
4. **Reverse cleanup:** children are deleted before parents.
5. **Determinism:** keys, dates, and fixture data are controlled.
6. **Constraints always active:** never disable FKs merely for easier seeding without a specific reason.
7. **Clear transactions:** understand DML can roll back while DDL/Truncate trigger implicit commits.
8. **Dedicated sequences:** never assume gap-free sequences or automatic resets upon table deletion.
9. **Parallel isolation:** each worker has its own schema/database or key/data partitioning.
10. **Realistic user testing:** test privileges with runtime accounts, not solely DBA accounts.
11. **Reconciliation:** verify row counts, keys, and constraints after seeding.
12. **Traceability:** clearly log migrations, seed batches, database identity, and Oracle errors.

## 21. Checklist before running integration tests

| Item | Question |
|---|---|
| Database identity | Do the JDBC URL, service, PDB, and DB unique name match the test environment? |
| Schema | Does the test user exist with appropriate quota and default tablespace? |
| Privileges | Does the schema owner have exact object creation privileges; does the runtime user have exact object privileges? |
| Migrations | Is the schema version at the expected state? |
| Dependencies | Are parent tables created before child tables and dependent objects created after base objects? |
| Seeding | Do parent rows precede child rows; are reference keys valid? |
| Constraints | Are PK/FK/UK/CHECK enabled and validated? |
| Sequences | Can sequences/identities collide with fixture IDs? |
| Reset | Is cleanup child-first; are there any implicit DDL commits to account for? |
| Transactions | Does the test roll back or commit; do seed scripts participate in the transaction? |
| Parallelism | Are test workers sharing a schema and deleting each other's data? |
| Security | Are passwords/secrets kept out of source control; is reset scoped strictly to the right schema? |
| Evidence | Are migration, seed, row count, and SQL error logs captured on failure? |

Properly creating and resetting schemas ensures Oracle tests start from a known state. Seeding data in dependency order ensures foreign keys always reference existing parents, while reverse-order cleanup removes data without violating referential integrity. Combining versioned migrations, deterministic fixtures, isolated schemas, and awareness of implicit DDL commits makes integration tests reproducible, order-independent, and much closer to how the application behaves on real Oracle.
