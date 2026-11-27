# Defining Foreign Keys, Indexes, Unique, and Check Constraints

In **Spring Data Relational JDBC**, entity mapping describes how aggregates translate into rows and columns, while the database schema decides what data is allowed to exist. A Java model can validate data in a service, yet batch jobs, other applications, or direct SQL queries can still write to the same database. Therefore, critical integrity rules need to be enforced at the database layer.

Four commonly used components are:

- **Foreign key:** ensures the referenced value points to an existing row in the referenced table.
- **Index:** helps the database locate and sort data more efficiently for suitable queries.
- **Unique constraint:** ensures a column or combination of columns contains no duplicate values according to database rules.
- **Check constraint:** ensures a row's values satisfy a boolean condition expression.

In Spring Data JDBC applications, these components are typically created and evolved using schema migrations such as Flyway or Liquibase. Mapping annotations inform Spring Data of table/column names and aggregate relationships; they do not replace designing, implementing, and enforcing constraints in the actual schema.

## 1. Why Are Database Constraints Needed?

Suppose an application has an orders table and an order items table:

```sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL
);

CREATE TABLE order_items (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_code VARCHAR(40) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(19, 2) NOT NULL
);
```

Java code can check that an order has an order number, an item belongs to an order, quantity is greater than 0, and order numbers do not duplicate. However, checks in Java only execute when data flows through that exact code path. A manual SQL statement or another application can bypass validation.

Database constraints protect data at the storage layer, regardless of whether the write comes from a repository, **JdbcAggregateTemplate**, **JdbcTemplate**, or another tool.

### 1.1. Distinguishing Validation from Constraints

| Mechanism | Responsibility |
|---|---|
| Bean Validation such as **@NotNull**, **@Size** | Checks data at the application layer when validation is invoked |
| Domain validation | Protects business rules within aggregate behavior |
| Database constraint | Prevents data violating integrity rules from being persisted |
| Index | Organizes access paths for queries; not every index is a constraint |

These layers complement one another. The domain model can return user-friendly errors when quantity is negative, while a CHECK constraint serves as the final line of defense if a write path bypasses the domain model.

Do not push every business rule into constraints. Constraints are suited for data integrity conditions that can be reliably expressed and enforced in the database.

## 2. Foreign Keys: Protecting Relationships Between Tables

A foreign key (FK) binds one or more columns of a referencing table to the primary key or a unique key of a referenced table.

For example, every order item must belong to an existing purchase order:

```sql
ALTER TABLE order_items
ADD CONSTRAINT fk_order_items_purchase_order
FOREIGN KEY (order_id)
REFERENCES purchase_orders(id);
```

Once the FK is created:

- You cannot insert an `order_items.order_id` pointing to a nonexistent order.
- You cannot delete a referenced order if the delete violates the FK policy.
- The database verifies this relationship on relevant write operations.

### 2.1. Declaring an FK at Table Creation

```sql
CREATE TABLE order_items (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_code VARCHAR(40) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_order_items_purchase_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_orders(id)
);
```

Constraint names are chosen explicitly to make errors easy to read, inspect the schema, and write subsequent migrations.

### 2.2. The Referenced Key Must Be an Appropriate Key

The referenced column is usually a primary key or a candidate key backed by a unique constraint/index accepted by the database.

Example referencing an order number:

```sql
ALTER TABLE purchase_orders
ADD CONSTRAINT uq_purchase_orders_order_number
UNIQUE (order_number);

ALTER TABLE order_items
ADD CONSTRAINT fk_order_items_order_number
FOREIGN KEY (order_number)
REFERENCES purchase_orders(order_number);
```

In typical designs, referencing by a stable ID is easier to manage than referencing by a mutable business code. If a business key is used, define a policy for when that code is updated.

### 2.3. NOT NULL and Foreign Key Are Two Separate Rules

An FK does not by default require the referencing column to have a value.

```sql
CREATE TABLE order_items (
    id BIGINT PRIMARY KEY,
    order_id BIGINT,
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_orders(id)
);
```

In this example, `order_id` can be NULL. When NULL, there is no concrete value to check for referential integrity, so the FK usually allows that row.

If every item must belong to an order, declare both:

```sql
order_id BIGINT NOT NULL,
CONSTRAINT fk_order_items_order
    FOREIGN KEY (order_id)
    REFERENCES purchase_orders(id)
```

`NOT NULL` governs the presence of a value; the FK governs that the value must reference a valid row.

## 3. Policies When a Referenced Row Is Deleted or Updated

When a referenced parent row is deleted or the referenced key changes, the database applies a configured action.

| Action | Meaning |
|---|---|
| **NO ACTION** | Disallows the operation if invalid references remain at check time |
| **RESTRICT** | Rejects the operation when referencing rows exist; check timing depends on the database |
| **CASCADE** | Deletes or updates affected child rows |
| **SET NULL** | Sets the FK column on referencing rows to NULL |
| **SET DEFAULT** | Sets the FK column to its default value if supported by the database and that value satisfies the FK |

Example:

```sql
CONSTRAINT fk_order_items_order
    FOREIGN KEY (order_id)
    REFERENCES purchase_orders(id)
    ON DELETE CASCADE
```

If an order is deleted, the database automatically deletes the order items referencing that order.

### 3.1. ON DELETE CASCADE

CASCADE is suitable when child rows have no independent meaning without the parent row, such as line items belonging to an order.

However, consider carefully:

- Deleting one root can delete a large number of child rows.
- Audit records or history that need to be retained may be deleted unexpectedly.
- The application may already delete children explicitly via its own persistence workflow.
- Cascading across multiple relationships can create hard-to-trace deletion chains.

With Spring Data JDBC, the framework understands aggregate mappings and has its own strategy for writing/deleting aggregate members. Make sure you know whether database cascades and Spring Data's deletion behavior are compatible; do not enable cascade simply because a one-to-many relationship exists.

### 3.2. ON DELETE RESTRICT or NO ACTION

If child data must be handled explicitly before deleting the parent, use RESTRICT or NO ACTION:

```sql
CONSTRAINT fk_order_items_order
    FOREIGN KEY (order_id)
    REFERENCES purchase_orders(id)
    ON DELETE RESTRICT
```

The database rejects deleting the order while referencing items still exist. The service can require cancelling, archiving, or processing the items before allowing deletion.

NO ACTION and RESTRICT differ in check timing in some databases, especially with deferred constraints. Verify the exact semantics for your dialect.

### 3.3. ON DELETE SET NULL

Use only when the relationship is truly optional:

```sql
FOREIGN KEY (sales_rep_id)
REFERENCES employees(id)
ON DELETE SET NULL
```

The FK column must allow NULL. If the column is declared NOT NULL, the SET NULL action cannot succeed.

A valid example might be a customer that continues to exist after its assigned employee is deleted, and the system accepts customers without an assigned representative.

### 3.4. ON UPDATE

You can specify behavior when a referenced key changes:

```sql
FOREIGN KEY (country_code)
REFERENCES countries(code)
ON UPDATE CASCADE
```

With immutable primary key IDs, changing keys is not a normal business operation. If mutable business keys are used, decide explicitly whether updates should cascade or be forbidden.

Do not rely on ON UPDATE CASCADE as a substitute for stable key design.

## 4. Foreign Keys and Aggregate Boundaries in Spring Data JDBC

Spring Data JDBC organizes data around aggregates. The aggregate root is the entry point for accessing and saving the aggregate; entities within the aggregate are managed alongside the root according to the mapping.

Example:

```java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @MappedCollection(idColumn = "order_id")
    private Set<OrderItem> items = new LinkedHashSet<>();
}
```

```java
@Table("order_items")
public class OrderItem {

    @Id
    private Long id;

    private String productCode;
    private int quantity;
}
```

`idColumn = "order_id"` describes the column in the member table used to reference the root's ID. The database schema must contain that column and can protect the relationship with an FK:

```sql
ALTER TABLE order_items
ADD CONSTRAINT fk_order_items_order
FOREIGN KEY (order_id)
REFERENCES purchase_orders(id);
```

Mapping annotations help Spring Data JDBC generate and execute SQL matching the declared structure. Migrations create the FK in the database. Both parts must stay consistent in table names, column names, data types, and nullability.

### 4.1. Referencing Another Aggregate

Example of an order referencing a customer:

```java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("customer_id")
    private AggregateReference<Customer, Long> customer;
}
```

`AggregateReference` represents a reference to another aggregate by ID. It lets the model express aggregate boundaries without embedding the entire customer into the order.

In the schema, you can create an FK:

```sql
ALTER TABLE purchase_orders
ADD CONSTRAINT fk_purchase_orders_customer
FOREIGN KEY (customer_id)
REFERENCES customers(id);
```

An FK is a database-layer decision. `AggregateReference` does not automatically guarantee that every schema migration created the constraint. If the application must ensure the customer exists, create the FK in a migration and handle reference errors on write.

### 4.2. Do Not Turn Every Object Relationship into One Aggregate

FKs can connect tables belonging to different aggregates. That does not mean Spring Data JDBC will automatically load the entire object graph or allow modifying them as a single aggregate.

Aggregate boundary design should be driven by business consistency rules and data lifecycles. FKs protect referential integrity in the database; they do not replace domain design.

## 5. Indexes: Accelerating Suitable Queries

An index is an auxiliary structure that helps the database locate rows without scanning the entire table in many cases.

For example, a query that frequently fetches orders by customer sorted by newest first:

```sql
SELECT id, order_number, created_at
FROM purchase_orders
WHERE customer_id = :customerId
ORDER BY created_at DESC, id DESC;
```

You can consider an index:

```sql
CREATE INDEX idx_purchase_orders_customer_created_id
ON purchase_orders(customer_id, created_at DESC, id DESC);
```

The index orders columns according to the query's filter conditions and sort order. The query planner still decides whether to use the index based on statistics, cardinality, cost, and execution plan.

### 5.1. Indexes Do Not Automatically Speed Up Every Query

Indexes carry costs:

- Consume storage space.
- Make INSERT/UPDATE/DELETE do extra work to update indexes.
- Can increase maintenance overhead depending on the database.
- Many overlapping indexes make the schema harder to manage.

Create indexes based on actual queries rather than mechanically indexing every column.

### 5.2. Indexes for Foreign Keys

An FK ensures integrity, but that does not mean the FK column is automatically indexed in every database.

```sql
CREATE INDEX idx_order_items_order_id
ON order_items(order_id);
```

This index can help load items for an order, JOIN orders with items, check referencing rows when deleting/updating a root, and run queries filtering by `order_id`.

Some databases such as PostgreSQL do not automatically create an index on referencing columns in child tables when declaring an FK. MySQL InnoDB typically requires and may automatically create a suitable index if none exists. Therefore, check dialect behavior and existing indexes before adding new ones.

### 5.3. Single-Column and Composite Indexes

Single-column index:

```sql
CREATE INDEX idx_orders_status
ON purchase_orders(status);
```

Can support queries filtering solely by `status`.

Composite index:

```sql
CREATE INDEX idx_orders_customer_status_created
ON purchase_orders(customer_id, status, created_at DESC);
```

Can support queries filtering by customer and status, then sorting by timestamp.

Column order in a composite index matters greatly. With B-tree indexes, databases typically leverage conditions on leading columns well (leftmost prefix). An index `(customer_id, status, created_at)` can be useful for queries by customer, or customer + status; it usually does not replace a status-only index well when a query has no customer predicate.

Design indexes around queries that actually occur in the application.

### 5.4. Indexes Supporting ORDER BY

An index can support sorting if its column order and direction match the query:

```sql
CREATE INDEX idx_orders_created_id
ON purchase_orders(created_at DESC, id DESC);
```

Query:

```sql
SELECT id, order_number
FROM purchase_orders
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

The database can read the index in the required order instead of sorting the entire result set. Effectiveness depends on the database, filters, sort direction, and query plan.

### 5.5. Covering Indexes and Included Columns

Some databases support adding non-key columns so queries can retrieve data directly from the index.

PostgreSQL example:

```sql
CREATE INDEX idx_orders_customer_created
ON purchase_orders(customer_id, created_at DESC)
INCLUDE (id, order_number, status);
```

Columns in `INCLUDE` do not participate in key ordering but can enable index-only scans under suitable conditions. This is a dialect-specific optimization; do not treat this syntax as portable SQL.

## 6. Unique Constraints: Preventing Duplicate Data

A unique constraint requires the value of a column or combination of columns to be unique.

For example, order numbers must not duplicate:

```sql
ALTER TABLE purchase_orders
ADD CONSTRAINT uq_purchase_orders_order_number
UNIQUE (order_number);
```

Or declared when creating the table:

```sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL,
    CONSTRAINT uq_purchase_orders_order_number
        UNIQUE (order_number)
);
```

### 6.1. Multi-Column Unique Constraints

A customer can have multiple addresses, but must not have duplicate address labels for the same customer:

```sql
ALTER TABLE customer_addresses
ADD CONSTRAINT uq_customer_addresses_customer_label
UNIQUE (customer_id, label);
```

This allows two different customers to both have the label `HOME`, while one customer cannot have two addresses with the same label.

A composite unique constraint checks the combination of values, not each column individually.

### 6.2. UNIQUE and NULL

How NULL is handled in unique constraints varies across databases.

Many DBMSs allow multiple rows to have NULL in a unique column by default because NULL is not considered equal under standard unique semantics. Some databases provide alternative syntax or options, such as PostgreSQL's `NULLS NOT DISTINCT` in supported versions.

If the business requires every row to have a unique and mandatory value, use both:

```sql
email_address VARCHAR(320) NOT NULL,
CONSTRAINT uq_customers_email UNIQUE (email_address)
```

If NULL means "no email yet", decide explicitly whether multiple customers without an email are allowed and use the appropriate syntax for your database.

### 6.3. Unique Constraints vs. Unique Indexes

Many databases implement unique constraints using unique indexes. In terms of design intent:

- `UNIQUE` expresses a data integrity rule.
- A unique index is an index structure that enforces the rule and can also serve queries.

When expressing a standard uniqueness rule, use a `UNIQUE` constraint so the schema clearly states its intent. Use a unique index directly when you need specialized features such as partial unique indexes or expression indexes.

### 6.4. Partial Unique Indexes

There are cases where uniqueness is only desired over a subset of rows.

For example, each customer has only one active default address:

```sql
CREATE UNIQUE INDEX uq_customer_one_active_default_address
ON customer_addresses(customer_id)
WHERE is_default = TRUE AND archived_at IS NULL;
```

This is a partial unique index in PostgreSQL. It applies only to rows matching the `WHERE` condition. Not all databases support similar syntax; use a solution appropriate to your dialect.

### 6.5. Unique Constraints Do Not Replace Conflict Handling in the Application

Do not rely solely on checking beforehand:

```java
if (!repository.existsByOrderNumber(orderNumber)) {
    repository.save(order);
}
```

Two concurrent requests can both observe that the code does not exist yet and both insert. This is a race condition.

A database unique constraint is the final line of defense. The application should catch and translate duplicate errors into a suitable business response, such as reporting that the order number is already in use.

In Spring, the error may be translated into `DuplicateKeyException` or `DataIntegrityViolationException` depending on the driver, SQL statement, and Spring's exception translation. Do not depend on a single exception subclass if multiple databases/drivers are supported.

## 7. Check Constraints: Validating Values Within Each Row

A check constraint requires that a conditional expression not evaluate to `FALSE` when inserting or updating a row.

For example, quantity must be greater than 0:

```sql
ALTER TABLE order_items
ADD CONSTRAINT chk_order_items_quantity_positive
CHECK (quantity > 0);
```

Unit price must not be negative:

```sql
ALTER TABLE order_items
ADD CONSTRAINT chk_order_items_unit_price_nonnegative
CHECK (unit_price >= 0);
```

Status may only belong to a set of values:

```sql
ALTER TABLE purchase_orders
ADD CONSTRAINT chk_purchase_orders_status
CHECK (status IN ('NEW', 'PAID', 'CANCELLED', 'SHIPPED'));
```

### 7.1. CHECK Does Not Replace NOT NULL

An important detail: SQL `CHECK` typically accepts expressions that evaluate to `UNKNOWN` (such as when a value is NULL), as long as the result is not `FALSE`.

Therefore:

```sql
quantity INTEGER CHECK (quantity > 0)
```

does not necessarily prevent `quantity = NULL`.

If quantity is required and must be greater than 0:

```sql
quantity INTEGER NOT NULL,
CONSTRAINT chk_order_items_quantity_positive
    CHECK (quantity > 0)
```

`NOT NULL` and `CHECK` enforce two distinct conditions.

### 7.2. Check for Value Ranges

For example, discount percentage must be between 0 and 100:

```sql
discount_percent DECIMAL(5, 2) NOT NULL,
CONSTRAINT chk_discount_percent_range
    CHECK (discount_percent >= 0 AND discount_percent <= 100)
```

You can use `BETWEEN`:

```sql
CHECK (discount_percent BETWEEN 0 AND 100)
```

Both expressions have the same meaning for non-NULL numeric values.

### 7.3. Check for Relationships Between Columns

For example, the end date must be on or after the start date:

```sql
CREATE TABLE promotions (
    id BIGINT PRIMARY KEY,
    starts_at TIMESTAMP NOT NULL,
    ends_at TIMESTAMP NOT NULL,
    CONSTRAINT chk_promotion_date_range
        CHECK (ends_at >= starts_at)
);
```

This condition involves columns in the same row and fits a CHECK constraint well.

### 7.4. Do Not Use CHECK for Rules That Span Multiple Rows

CHECK is designed to evaluate expressions on the current row. Avoid using it to check totals across related rows or the state of rows in another table.

For example, "a customer may have at most 5 open orders" is a multi-row rule. It may require transaction locking, triggers, a synchronously maintained counter table, or a different domain design. A simple CHECK cannot enforce this rule portably.

If the rule is uniqueness, use a unique constraint/index. If the rule references another table, use an FK. If the rule is complex across multiple rows, choose an appropriate database and transaction mechanism instead of forcing it into CHECK.

### 7.5. CHECK and Database Versions

CHECK support varies by DBMS and version. For example, MySQL only enforces CHECK constraints in newer releases (MySQL 8.0.16 and later); older versions may parse but ignore the constraint. Verify that your production version actually enforces the condition.

## 8. Combining Constraints in a Schema

For example, an order schema might define these rules:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    email_address VARCHAR(320) NOT NULL,
    CONSTRAINT uq_customers_email UNIQUE (email_address)
);

CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    order_number VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL,

    CONSTRAINT uq_purchase_orders_order_number
        UNIQUE (order_number),

    CONSTRAINT fk_purchase_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(id),

    CONSTRAINT chk_purchase_orders_status
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED', 'SHIPPED'))
);

CREATE TABLE order_items (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_code VARCHAR(40) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(19, 2) NOT NULL,

    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_orders(id)
        ON DELETE CASCADE,

    CONSTRAINT chk_order_items_quantity_positive
        CHECK (quantity > 0),

    CONSTRAINT chk_order_items_unit_price_nonnegative
        CHECK (unit_price >= 0)
);

CREATE INDEX idx_purchase_orders_customer_created
    ON purchase_orders(customer_id, created_at DESC, id DESC);

CREATE INDEX idx_order_items_order_id
    ON order_items(order_id);
```

The schema above illustrates several types of rules:

| Rule | Constraint/index |
|---|---|
| Customer emails must not duplicate | `uq_customers_email` |
| Order numbers must not duplicate | `uq_purchase_orders_order_number` |
| Order must belong to an existing customer | `fk_purchase_orders_customer` |
| Order status belongs to allowed set | `chk_purchase_orders_status` |
| Item must belong to an existing order | `fk_order_items_order` |
| Quantity must be positive | `chk_order_items_quantity_positive` |
| Unit price must be non-negative | `chk_order_items_unit_price_nonnegative` |
| Load orders by customer and timestamp | `idx_purchase_orders_customer_created` |
| Load items by order | `idx_order_items_order_id` |

`ON DELETE CASCADE` in the example is an illustrative choice. Use it only if the data lifecycle permits deleting items along with the order. If history must be preserved, use soft deletes or a different policy.

## 9. Managing Constraints and Indexes via Schema Migrations

Spring Data JDBC focuses on aggregate mapping and persistence. In most projects, the schema is managed with a migration tool so development, test, and production environments share the same structure.

A versioned migration can create initial tables and constraints. Example Flyway filenames:

```text
src/main/resources/db/migration/
  V001__create_customer_tables.sql
  V002__add_order_indexes.sql
  V003__add_order_status_constraint.sql
```

Example migration content:

```sql
-- V001__create_customer_tables.sql

CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    email_address VARCHAR(320) NOT NULL,
    CONSTRAINT uq_customers_email UNIQUE (email_address)
);

CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    order_number VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_purchase_orders_order_number
        UNIQUE (order_number),
    CONSTRAINT fk_purchase_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);
```

The next migration adds an index:

```sql
-- V002__add_order_indexes.sql

CREATE INDEX idx_purchase_orders_customer_created
ON purchase_orders(customer_id, created_at DESC, id DESC);
```

A later migration adds a CHECK constraint:

```sql
-- V003__add_order_status_constraint.sql

ALTER TABLE purchase_orders
ADD CONSTRAINT chk_purchase_orders_status
CHECK (status IN ('NEW', 'PAID', 'CANCELLED', 'SHIPPED'));
```

Migrations are applied in version order. Once a migration has run in a shared environment, do not edit its historical content to alter the schema; create a new migration describing the next change.

### 9.1. Constraint Names Should Be Clear and Stable

A common convention:

| Type | Suggested prefix | Example |
|---|---|---|
| Primary key | `pk_` | `pk_purchase_orders` |
| Foreign key | `fk_` | `fk_order_items_order` |
| Unique | `uq_` | `uq_customers_email` |
| Check | `chk_` | `chk_order_items_quantity_positive` |
| Index | `idx_` | `idx_orders_customer_created` |

Clear names make database error messages readable and simplify writing drop/alter migrations. Some databases impose identifier length limits; keep names concise yet meaningful and consistent with the project's naming convention.

### 9.2. Migrations Must Be Safe for Existing Data

Adding a constraint to a table that already contains data can fail if existing data violates the new rule.

Before adding an FK:

```sql
SELECT oi.order_id
FROM order_items oi
LEFT JOIN purchase_orders o ON o.id = oi.order_id
WHERE oi.order_id IS NOT NULL
  AND o.id IS NULL;
```

Before adding a unique constraint:

```sql
SELECT order_number, COUNT(*)
FROM purchase_orders
GROUP BY order_number
HAVING COUNT(*) > 1;
```

Before adding a CHECK constraint:

```sql
SELECT id, quantity
FROM order_items
WHERE quantity <= 0;
```

These queries help locate data that needs remediation before applying the migration. For nullable columns, check for NULLs separately if the new rule requires NOT NULL.

Do not automatically delete or modify production data without defining transformation rules. The migration may require a controlled backfill or cleanup step before enabling the constraint.

### 9.3. Expand-Contract for Major Changes

When changing a schema while old and new application versions may run concurrently during deployment, use the expand-contract strategy:

1. **Expand:** add columns/indexes/constraints compatible with the old application version.
2. Deploy new code that can read/write the new structure.
3. Backfill old data.
4. Switch the application to the new structure.
5. **Contract:** drop old columns or structures in a later migration once no code uses them.

For example, to make `email_address` unique when existing data still has duplicates: first clean up the duplicates and deploy code that prevents creating duplicates; only then add the unique constraint.

### 9.4. Migration Rollback

Not every schema change can be rolled back safely once new data has been written.

- Dropping an index usually does not lose data, though it can hurt performance.
- Dropping an FK removes a layer of referential protection.
- Dropping a CHECK constraint removes domain value protection.
- Dropping a unique constraint allows new duplicates to appear.
- Changing column types can lose data if the conversion is lossy.

Evaluate data consequences and compatibility before writing rollback scripts. With Flyway, versioned migrations are normally forward-only history; rollbacks are typically implemented via new migrations or controlled undo workflows depending on how the project is organized.

## 10. Creating Indexes on Large Tables

Creating an index on a large table can consume significant time, CPU, and I/O, and affect write availability.

PostgreSQL supports:

```sql
CREATE INDEX CONCURRENTLY idx_orders_created_id
ON purchase_orders(created_at DESC, id DESC);
```

`CONCURRENTLY` reduces write blocking compared to regular index creation, but has limitations: it cannot run inside a regular transaction block and can leave an invalid index if the operation fails. Configure the migration tool so this migration is not wrapped in a transaction when using that syntax.

SQL Server and other databases have their own online index options depending on edition/version. Do not assume `CONCURRENTLY` is portable syntax.

Before creating an index in production:

- Identify the query to optimize.
- Inspect the execution plan.
- Assess table size and write workload.
- Choose the least-disruptive index creation method for the database.
- Monitor duration, locks, and index state.
- Verify the migration tool handles transactions as required by the statement.

## 11. Deferrable Constraints and Deferred Checking

Some databases, such as PostgreSQL, support constraints whose checking can be deferred until the end of a transaction:

```sql
ALTER TABLE order_items
ADD CONSTRAINT fk_order_items_order
FOREIGN KEY (order_id)
REFERENCES purchase_orders(id)
DEFERRABLE INITIALLY DEFERRED;
```

With a deferred constraint, a transaction can temporarily create an invalid referential state between statements, provided the final state at check time is valid.

This is useful in certain key-swapping operations or multi-row writes with circular dependencies. However, not all constraint types or databases support deferrable constraints in the same way.

Do not use deferred constraints to mask unclear write ordering. Enable them only when a use case genuinely requires them and integration tests confirm the semantics on the target database.

## 12. Constraints and Exceptions in Spring Data JDBC

When a statement violates an FK, unique, or CHECK constraint, the database returns an error. Spring JDBC typically translates JDBC errors into the exception hierarchy in package `org.springframework.dao`.

| Violation | Common Spring Exception |
|---|---|
| Unique/duplicate key | `DuplicateKeyException` or `DataIntegrityViolationException` |
| FK | `DataIntegrityViolationException` |
| CHECK | `DataIntegrityViolationException` |
| NOT NULL | `DataIntegrityViolationException` |

The exact exception subclass may depend on the database, driver, and error translation. If the application supports multiple dialects, handle by business failure type and avoid relying solely on a vendor error code.

Example:

```java
@Transactional
public Customer register(Customer customer) {
    try {
        return customerRepository.save(customer);
    } catch (DuplicateKeyException exception) {
        throw new EmailAlreadyRegisteredException(
            customer.emailAddress(),
            exception
        );
    }
}
```

The example assumes a unique constraint on email is defined in the database. The service translates the persistence error into a meaningful domain exception for the use case.

Avoid simply catching `DataIntegrityViolationException` and returning a generic "invalid data" message for every case. FK, CHECK, NOT NULL, and unique violations have different meanings; translate them into appropriate domain/API errors when enough context is available.

### 12.1. Do Not Replace Constraints with `exists` Checks

The following code can be helpful for providing early feedback:

```java
if (!repository.existsByOrderNumber(orderNumber)) {
    repository.save(order);
}
```

However, you still must keep the unique constraint in the database to handle concurrency. Pre-checks improve user experience; constraints provide the final guarantee.

### 12.2. After a Constraint Error, the Transaction May Be Rollback-Only

Some databases mark a transaction as aborted after a SQL statement violates a constraint. If you catch the exception and continue running queries in the same transaction, subsequent operations may fail or the transaction still cannot commit.

The safer approach is usually to let the exception exit the transaction boundary and translate it at a higher layer. If you need to continue after an operation that might violate a constraint, design separate transactions/savepoints and verify database/transaction manager support.

## 13. Spring Data JDBC Mapping and Schema Must Stay Consistent

Spring Data JDBC uses mapping metadata to know:

- Table names from **@Table**.
- Column names from **@Column** or the naming strategy.
- IDs from **@Id**.
- Collection relationships via **@MappedCollection**.
- Aggregate references via **AggregateReference**.
- Data types via converters.

Example:

```java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_number")
    private String orderNumber;

    @Column("customer_id")
    private AggregateReference<Customer, Long> customer;

    @MappedCollection(idColumn = "order_id")
    private Set<OrderItem> items = new LinkedHashSet<>();
}
```

The schema needs to match:

```sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL,
    customer_id BIGINT NOT NULL,
    CONSTRAINT uq_purchase_orders_order_number UNIQUE (order_number),
    CONSTRAINT fk_purchase_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE order_items (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_code VARCHAR(40) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id),
    CONSTRAINT chk_order_items_quantity
        CHECK (quantity > 0)
);

CREATE INDEX idx_order_items_order_id
ON order_items(order_id);
```

If the mapping uses `customer_id` but the schema only has `customer`, generated SQL statements can fail. If `MappedCollection` uses `order_id` while the child table uses `purchase_order_id`, either the mapping or migration must be updated so they agree.

### 13.1. Mapping Annotations Do Not Automatically Create All Constraints

`@Table`, `@Column`, `@Id`, and `@MappedCollection` describe object-relational mapping. Do not expect them to automatically create complete FKs, indexes, unique, and CHECK constraints in production.

Some schema initialization tools can generate DDL for development environments, but versioned migrations remain the explicit way to manage schemas cleanly under control.

### 13.2. Uniqueness in Java vs. Uniqueness in the Database

If a model has an `emailAddress` field, checking email uniqueness in the service does not automatically create a unique constraint. Create the constraint via a migration:

```sql
ALTER TABLE customers
ADD CONSTRAINT uq_customers_email_address
UNIQUE (email_address);
```

Then write an integration test verifying that the database rejects duplicates.

## 14. Testing Constraints and Indexes

Constraints are database behavior, so pure Java unit tests are insufficient to prove they are properly deployed.

### 14.1. Testing Foreign Keys

Insert an order item referencing a nonexistent ID and verify the database rejects it:

```java
@Test
void rejectsItemWithUnknownOrder() {
    assertThatThrownBy(() ->
        jdbcTemplate.update(
            """
            INSERT INTO order_items(
                id, order_id, product_code, quantity, unit_price
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            1L,
            999999L,
            "KB-01",
            1,
            new BigDecimal("10.00")
        )
    ).isInstanceOf(DataIntegrityViolationException.class);
}
```

### 14.2. Testing Unique Constraints

```java
@Test
void rejectsDuplicateOrderNumber() {
    insertOrder(1L, "ORD-1001");

    assertThatThrownBy(() ->
        insertOrder(2L, "ORD-1001")
    ).isInstanceOf(DataIntegrityViolationException.class);
}
```

The test should confirm that the database rejects duplicates, not merely that service validation does.

### 14.3. Testing CHECK Constraints

```java
@Test
void rejectsNonPositiveItemQuantity() {
    assertThatThrownBy(() ->
        insertOrderItem(1L, 10L, "KB-01", 0)
    ).isInstanceOf(DataIntegrityViolationException.class);
}
```

### 14.4. Testing Migrations Against the Exact Database

H2 can differ from PostgreSQL, MySQL, SQL Server, or Oracle in syntax and constraint/index semantics. If production uses a specific database, integration tests should run against the same DBMS and a compatible version, typically via Testcontainers.

Verify:

- Migrations run on an empty schema.
- Migrations run on representative existing data.
- FKs reject nonexistent references.
- Unique constraints reject duplicates.
- CHECK constraints reject invalid values.
- Indexes are created with the right columns and ordering.
- Real queries produce suitable execution plans once indexes exist.

### 14.5. Indexes Cannot Be Tested Simply by Checking Query Results

Indexes generally do not change a query's logical result. To confirm effectiveness, inspect execution plans and measure against sufficiently representative data. Do not claim a query uses an index merely because the index was created.

## 15. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Cannot insert item with valid order | FK points to wrong column or mapping/schema mismatch | Check mapping and DDL |
| Item points to nonexistent order | Missing FK | Add foreign key constraint |
| FK still allows NULL | Only FK present, missing NOT NULL | Add NOT NULL if relationship is required |
| Deleting order is rejected | Referencing child rows remain with RESTRICT/NO ACTION | Handle child rows or choose intentional cascade |
| Deleting order loses historical data | Improper use of ON DELETE CASCADE | Use RESTRICT/soft delete or retention policy |
| Query filtering by FK is slow | FK column lacks suitable index | Check indexes and execution plan |
| Unique constraint allows multiple NULLs | Database NULL semantics | Combine with NOT NULL or design appropriate unique constraint |
| Two requests create duplicates | Only Java exists-check used | Use unique constraint and handle duplicate exception |
| CHECK allows NULL | CHECK returns UNKNOWN when expression contains NULL | Add NOT NULL if required |
| CHECK not enforced | Database version does not support/enforce | Verify production version |
| Adding constraint fails on deploy | Old data violates new condition | Audit, backfill, and clean up before migration |
| Indexes slow down writes | Too many indexes or low-value indexes | Measure workload, drop redundant/unused indexes |
| Migration fails creating large index | Lock or dialect transaction limitations | Use appropriate online/concurrent strategy |
| H2 tests pass but production fails | Dialect differences | Integration test with production-compatible database |

## 16. Exercises

Assume tables `customers`, `purchase_orders`, and `order_items`.

**Exercise 1.** Every item must belong to an existing order. Which constraint is needed?

*Answer:* A foreign key from `order_items.order_id` to `purchase_orders.id`. If an item must have an order, column `order_id` also needs `NOT NULL`.

**Exercise 2.** Order numbers must be unique. What should be used?

*Answer:* A unique constraint on `purchase_orders.order_number`.

**Exercise 3.** Quantity must be greater than 0. What should be used?

*Answer:* `CHECK (quantity > 0)` and `NOT NULL` if quantity must have a value.

**Exercise 4.** A query frequently loads items by `order_id` but runs slowly. What might be needed?

*Answer:* An index on `order_items(order_id)`, then confirm with an execution plan. Some databases create indexes for FKs automatically; others do not.

**Exercise 5.** Should `existsByOrderNumber` alone be used to prevent duplicate order numbers?

*Answer:* No. Two concurrent transactions can both pass the check. The database still needs a unique constraint.

**Exercise 6.** Is `ON DELETE CASCADE` always appropriate for order items?

*Answer:* No. Use it only when items have a lifecycle dependent on the root and deleting the root is allowed to delete all items. If auditing or history is needed, choose another policy.

**Exercise 7.** Why is `CHECK (quantity > 0)` not enough to forbid NULL?

*Answer:* In SQL, an expression with NULL can evaluate to `UNKNOWN`; CHECK typically only rejects `FALSE`. Add `NOT NULL` if the value is required.

**Exercise 8.** Can a unique constraint be added to a production table that currently has duplicates?

*Answer:* It cannot be added successfully while data violates it. Find and resolve duplicates first, then deploy the migration adding the constraint.

**Exercise 9.** Does Spring Data JDBC automatically create all indexes and FKs from aggregate mappings?

*Answer:* Do not assume so. Mappings describe object relationships and column names; schema constraints/indexes should be managed via migrations or controlled DDL mechanisms.

## 17. Key Takeaways

- **Foreign keys** protect references between tables; use **NOT NULL** separately if the relationship is mandatory.
- Choose **CASCADE**, **RESTRICT**, **NO ACTION**, or **SET NULL** based on data lifecycle and retention requirements.
- Spring Data JDBC aggregate mappings and database FKs play complementary roles; mappings do not automatically guarantee constraints exist in the schema.
- **Indexes** help suitable queries find/sort data more efficiently, at the expense of storage and write overhead.
- Design indexes from actual queries; pay attention to column ordering in composite indexes and indexes on FK columns.
- **Unique constraints** are the final safeguard for uniqueness, even under concurrent requests.
- **CHECK constraints** validate per-row expressions; combine with **NOT NULL** if missing values are disallowed.
- Do not use simple CHECK constraints to enforce complex rules spanning multiple rows or tables.
- Name constraints/indexes clearly and manage them with versioned migrations.
- Before adding a constraint to a populated table, find and resolve violating rows.
- Test migrations and constraints against the production database/dialect.
- Handle data integrity exceptions in the service layer to translate them into appropriate business/API errors.

### Official References

- [Spring Data Relational — JDBC Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): aggregate mapping, tables, columns, and member relationships.
- [Spring Data Relational — JDBC Reference](https://docs.spring.io/spring-data/relational/reference/jdbc.html): repositories and persistence in Spring Data JDBC.
- [PostgreSQL — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): primary keys, foreign keys, unique, check, and constraint behavior.
- [PostgreSQL — Indexes](https://www.postgresql.org/docs/current/indexes.html): index types and how the database uses indexes.
- [MySQL — InnoDB Foreign Key Constraints](https://dev.mysql.com/doc/refman/8.4/en/innodb-foreign-key-constraints.html): FK rules and referential actions.
- [MySQL — CHECK Constraints](https://dev.mysql.com/doc/refman/8.4/en/create-table-check-constraints.html): syntax and CHECK enforcement conditions.
- [Flyway — Versioned Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/versioned-migrations): organizing migrations by version.

When implementing, verify syntax, NULL semantics, cascade behavior, and index creation capabilities for your actual database/version. The goal is for Spring Data JDBC mappings, schema migrations, and database integrity rules to describe the exact same data structure.
