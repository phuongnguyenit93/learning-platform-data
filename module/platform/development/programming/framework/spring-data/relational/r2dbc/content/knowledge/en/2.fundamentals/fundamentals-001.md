# Essential SQL, Primary Keys, Foreign Keys, and Data Constraints

## 1. Why Understanding These Concepts Matters When Using Spring Data Relational R2DBC

Spring Data Relational R2DBC enables Java applications to read and write data in a relational database using the reactive model. R2DBC changes how the application communicates asynchronously with the database; it does not replace SQL, nor does it automatically guarantee that persisted data is always valid.

Data correctness is primarily determined by table structure, data types, keys, and constraints enforced by the database. Annotations in Spring Data Relational describe how Java objects map to tables and columns; they do not automatically replace constraints in the SQL schema.

For example, a Java object with a `customerId` field of type `Long` is not enough to guarantee that the customer exists. For the database to reject an order referencing a nonexistent customer, the orders table needs a foreign key pointing to the customers table. Similarly, checking email uniqueness in the UI does not prevent another process from inserting a duplicate email directly into the database; a `UNIQUE` constraint protects that rule at the data layer.

After this lesson, you should be able to read table creation statements, explain the roles of primary keys and foreign keys, choose appropriate constraints, and understand how those rules work together with Spring Data Relational R2DBC code.

## 2. Tables, Rows, Columns, and Data Types in SQL

Relational databases organize data into tables. A table typically represents one type of entity or a collection of records with the same structure.

- **Table:** a collection of records, such as `customers` or `orders`.
- **Row:** a specific record, such as the customer with ID `101`.
- **Column:** an attribute of a record, such as `email` or `created_at`.
- **Data type:** restricts the kind of values a column can store, such as `BIGINT`, `VARCHAR`, `DATE`, `TIMESTAMP`, `BOOLEAN`, or `DECIMAL`.

Data types are the first line of defense. Choose types based on the meaning and value domain of the data:

| Requirement | Commonly Used Type | Notes |
|---|---|---|
| Large integer identifier | BIGINT | Suitable for numeric IDs that can grow over time |
| Bounded-length string | VARCHAR(n) | Choose a reasonable limit based on business rules |
| Long text content | TEXT | Exact syntax and limits depend on the database system |
| Money or decimals requiring precision | DECIMAL(p, s) / NUMERIC(p, s) | Avoid floating-point numbers for monetary calculations |
| Date | DATE | Does not include time of day |
| Point in time | TIMESTAMP or equivalent type | Standardize on a system-wide time zone convention |
| True/false | BOOLEAN | Some database systems represent this in their own way |

`DECIMAL(12, 2)` can represent numbers with up to 12 total digits, including 2 digits after the decimal point. For example, a price of `125000.50` fits this type. Do not choose `FLOAT` or `DOUBLE` for monetary amounts when business logic requires exact decimal results, because they are binary floating-point types and can introduce representation errors.

SQL has the concept of `NULL`, representing an unknown or unprovided value. `NULL` is not the same as an empty string (`''`), the number `0`, or `false`. Comparisons with `NULL` generally do not return ordinary true/false values, instead producing an unknown state; therefore, use `IS NULL` or `IS NOT NULL`, not `= NULL`.

Example:

~~~sql
SELECT id, email
FROM customers
WHERE deleted_at IS NULL;
~~~

If an attribute is required, declare it `NOT NULL`. Validating only in Java is not enough to protect data against other write paths.

## 3. Primary Keys (PRIMARY KEY)

### 3.1. Concept and Purpose

A primary key is a column or group of columns used to uniquely identify each row in a table. A primary key must satisfy two properties:

1. **Uniqueness:** no two rows have the same primary key value.
2. **Non-nullability:** columns belonging to the primary key cannot accept `NULL`.

Each table has at most one primary key constraint. That constraint can consist of multiple columns, called a composite primary key.

Example:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL
);
~~~

Here, `id` identifies a customer. Two customers cannot share the same `id`, and a customer row cannot lack an `id`.

### 3.2. Surrogate Keys and Natural Keys

A key can be:

- **Natural key:** an attribute that inherently carries business meaning and can serve as an identifier, such as a country code or a company-managed product code.
- **Surrogate key:** a value generated specifically to identify a record, such as a `BIGINT` or `UUID` `id`.

In many applications, surrogate keys keep relationships between tables more stable. Email addresses, phone numbers, or names can change, so they are usually unsuitable as primary keys even though they may need a `UNIQUE` constraint to prevent duplicates under business rules.

Do not assume that a value that appears unique today will always make a good identifier. Consider mutability, sensitivity, normalization rules, and uniqueness scope before choosing a key.

### 3.3. Composite Primary Keys

A composite primary key uses multiple columns to identify a row. For example, a product appears only once in each order:

~~~sql
CREATE TABLE order_items (
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    PRIMARY KEY (order_id, product_id)
);
~~~

The pair `(order_id, product_id)` must be unique. `order_id` alone can repeat because one order has multiple products; `product_id` alone can also repeat because one product appears in multiple orders.

A composite key is appropriate when the column combination itself is the natural identifier of the row. If other tables need to reference this row, weigh the complexity of carrying multiple key columns. A simple surrogate key can make referencing easier, while still keeping `UNIQUE(order_id, product_id)` to enforce the business rule.

### 3.4. Key Generation

IDs can be generated by the application, sequences, database identity/auto-increment columns, or UUID generators. The exact declaration syntax depends on the database system.

Example in PostgreSQL syntax:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL
);
~~~

In Spring Data Relational, `@Id` marks the identifier property in the Java mapping. This annotation does not create a primary key in the database, nor does it replace the schema's ID generation mechanism.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {
    @Id
    private Long id;

    private String fullName;
}
~~~

Ensure the Java type is compatible with the column type and chosen ID generation mechanism. For UUIDs, use the Java type and column type supported by the corresponding driver and database system.

## 4. Foreign Keys (FOREIGN KEY)

### 4.1. Concept and Purpose

A foreign key is a constraint requiring that the value in a column or group of columns in a table reference a valid key in another table, typically a primary key or a set of columns with a unique constraint.

Foreign keys protect **referential integrity**. They prevent data from creating links to a nonexistent row, and they define how to handle cases where a referenced row is deleted or updated.

For example, every order belongs to a customer:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL
);

CREATE TABLE orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(id)
);
~~~

`orders.customer_id` must match an existing `customers.id`. Because `customer_id` is also declared `NOT NULL`, every order must have a customer. If `NOT NULL` were omitted, the database could allow an unattached order by storing `NULL`; a foreign key does not forbid that case.

### 4.2. Rules When Deleting or Updating a Referenced Row

When declaring a foreign key, you can specify the behavior when a parent record is deleted or a referenced key is updated:

| Behavior | Meaning | When to Consider |
|---|---|---|
| RESTRICT / NO ACTION | Rejects operations that break references; exact timing of the check depends on the database system and constraint configuration | Child data must be retained or handled explicitly |
| CASCADE | Deletes/updates corresponding child rows following operations on the parent row | Child rows have no independent meaning outside the parent row |
| SET NULL | Sets the foreign key column to NULL | The relationship is optional and the column allows NULL |
| SET DEFAULT | Sets the column to its default value | Use only when the default value still satisfies constraints and the business model |

Example:

~~~sql
CONSTRAINT fk_orders_customer
    FOREIGN KEY (customer_id)
    REFERENCES customers(id)
    ON DELETE RESTRICT
    ON UPDATE CASCADE
~~~

`ON DELETE CASCADE` can be convenient when deleting a parent record must remove all dependent child rows. However, setting cascade without careful thought can delete a large amount of data unexpectedly. For orders, invoices, or transaction history, it is usually necessary to preserve history and use a dedicated business workflow instead of cascading deletes.

Choose the behavior based on the data lifecycle. Do not use `CASCADE` just because it makes delete statements easier to write. If a customer cannot be deleted while orders still exist, `RESTRICT` or the default behavior is more appropriate. If a customer can be deleted while orders must remain, you may need a design that preserves historical information or an anonymized state rather than mechanically setting `customer_id` to `NULL`.

### 4.3. Composite Foreign Keys

A foreign key can also consist of multiple columns. The number, order, and data types of the referencing columns must be compatible with the referenced key.

~~~sql
CREATE TABLE order_items (
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_item_order
        FOREIGN KEY (order_id) REFERENCES orders(id),
    CONSTRAINT fk_item_product
        FOREIGN KEY (product_id) REFERENCES products(id)
);
~~~

In this example, each line item must belong to an existing order and an existing product. If the target table uses a composite key, the `REFERENCES` clause must list all corresponding key columns.

### 4.4. A Foreign Key Does Not Automatically Imply a Bidirectional Object Relationship

In the relational model, a foreign key is a database rule. In Java code, whether you have a `customerId` field, a `Customer` object, or a collection of `Order`s is an application modeling and mapping decision.

Spring Data Relational R2DBC does not work like JPA with automatic lazy/eager relationship loading through proxies. Spring Data Relational's model centers on aggregates: it typically loads and saves an aggregate root along with the members belonging to that aggregate. A foreign key in SQL does not automatically cause Spring Data R2DBC to construct an entire object graph.

For example, the `customer_id` column can be mapped as a simple ID field:

~~~java
@Table("orders")
public class Order {
    @Id
    private Long id;

    @Column("customer_id")
    private Long customerId;
}
~~~

The `customerId` field only holds the foreign key value. When customer details are needed, the application can query `Customer` separately or use an appropriate join query. The database still enforces the foreign key on writes.

## 5. Other Important Data Constraints

Primary keys and foreign keys handle identification and links. A real-world schema usually needs the following additional constraints.

### 5.1. NOT NULL

`NOT NULL` requires a column to have a value. Use it for required attributes such as a product name, creation timestamp, or the foreign key of a mandatory relationship.

~~~sql
full_name VARCHAR(150) NOT NULL
~~~

If a column has both `NOT NULL` and `DEFAULT`, when an insert statement omits the column, the database can populate the default value. If a writer explicitly passes `NULL`, the operation is still rejected by `NOT NULL`.

### 5.2. UNIQUE

`UNIQUE` requires a value or combination of values not to be duplicated. For example, a login email may need to be unique:

~~~sql
ALTER TABLE customers
ADD CONSTRAINT uq_customers_email UNIQUE (email);
~~~

A unique constraint can be created across multiple columns:

~~~sql
ALTER TABLE products
ADD CONSTRAINT uq_products_sku_per_store
UNIQUE (store_id, sku);
~~~

In this case, the same `sku` can appear in different stores, but cannot be repeated within the same store.

Note: how databases handle multiple `NULL` values in a unique constraint varies across database systems and can sometimes be configured. For example, PostgreSQL allows multiple rows with `NULL` in a unique column by default. If an email is both required and unique, `NOT NULL` and `UNIQUE` are typically combined.

### 5.3. CHECK

`CHECK` restricts values according to a logical expression evaluated on the row being inserted or updated.

~~~sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(12, 2) NOT NULL,
    stock_quantity INTEGER NOT NULL,
    CONSTRAINT ck_products_price_nonnegative CHECK (price >= 0),
    CONSTRAINT ck_products_stock_nonnegative CHECK (stock_quantity >= 0)
);
~~~

Another example:

~~~sql
ALTER TABLE employees
ADD CONSTRAINT ck_employees_valid_dates
CHECK (end_date IS NULL OR end_date >= start_date);
~~~

`CHECK` is well suited for rules that can be evaluated from data within the same row. Do not rely on a regular `CHECK` constraint to validate total quantities across multiple rows or state in another table; cross-row or cross-table rules require another design, such as transactions, triggers, or specialized database mechanisms.

One common pitfall: in SQL logic, a `CHECK` expression evaluating to `UNKNOWN` due to `NULL` generally does not cause the row to be rejected. Therefore, `CHECK (price >= 0)` does not replace `NOT NULL` if a price is required.

### 5.4. DEFAULT

`DEFAULT` provides a value when an insert statement does not specify that column:

~~~sql
CREATE TABLE orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

`DEFAULT` does not force every written value to equal the default value. If the application passes a different value, that value is used as long as it does not violate the remaining constraints. `DEFAULT` is also not the same as `NOT NULL`: to require a column to have a value, declare both when needed.

### 5.5. Summary of Constraints

| Constraint | What Does It Protect? | Question to Ask |
|---|---|---|
| PRIMARY KEY | Unique identification and non-nullability | By which key is a row identified? |
| FOREIGN KEY | Link to a valid row | Does the related record actually exist? |
| NOT NULL | Required value presence | Is this attribute allowed to be missing? |
| UNIQUE | No duplicates allowed | Which value or combination must be unique? |
| CHECK | Value domain restricted by an expression | What condition must hold on every row? |
| DEFAULT | Value used when insert omits the column | What is a sensible initial value? |

Constraints can be combined. For example, `email VARCHAR(255) NOT NULL UNIQUE` both requires an email and prevents duplicate emails.

## 6. Indexes and Their Relationship with Keys

An index is a structure that helps the database search or join data more efficiently. Primary keys and unique constraints are typically backed by a unique index or equivalent structure in the database system. A foreign key exists for data integrity; it does not mean every database automatically creates an index on the referencing column.

For example, a query frequently looks up orders by customer:

~~~sql
SELECT id, created_at
FROM orders
WHERE customer_id = 101;
~~~

An index on `orders.customer_id` can make this query faster when the table grows large:

~~~sql
CREATE INDEX ix_orders_customer_id ON orders(customer_id);
~~~

An index on a foreign key column can also help the database process joins and make checking or deleting parent rows more efficient. However, indexes increase storage usage and write/update overhead, so decisions should be based on actual queries and execution plans.

Distinguish between:

- **Constraint:** defines what data is allowed to exist.
- **Index:** supports how the database finds and sorts data.
- **Unique index:** both accelerates lookups and enforces uniqueness according to database rules.

Do not create redundant indexes duplicating those already created by a primary key or unique constraint. Nor should you create indexes on every column out of habit.

## 7. Complete Schema Example for Customers, Orders, and Products

The following example uses PostgreSQL syntax for illustration. Identity type names and certain syntax details may differ in MySQL, SQL Server, Oracle, or H2; adjust them according to the database system used by your project.

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_customers PRIMARY KEY (id),
    CONSTRAINT uq_customers_email UNIQUE (email)
);

CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY,
    sku VARCHAR(60) NOT NULL,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(12, 2) NOT NULL,
    stock_quantity INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT pk_products PRIMARY KEY (id),
    CONSTRAINT uq_products_sku UNIQUE (sku),
    CONSTRAINT ck_products_price CHECK (price >= 0),
    CONSTRAINT ck_products_stock CHECK (stock_quantity >= 0)
);

CREATE TABLE orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_orders PRIMARY KEY (id),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
        ON DELETE RESTRICT
);

CREATE TABLE order_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    CONSTRAINT pk_order_items PRIMARY KEY (id),
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id) REFERENCES orders(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_order_items_product
        FOREIGN KEY (product_id) REFERENCES products(id)
        ON DELETE RESTRICT,
    CONSTRAINT uq_order_items_order_product UNIQUE (order_id, product_id),
    CONSTRAINT ck_order_items_quantity CHECK (quantity > 0),
    CONSTRAINT ck_order_items_unit_price CHECK (unit_price >= 0)
);

CREATE INDEX ix_orders_customer_id ON orders(customer_id);
CREATE INDEX ix_order_items_product_id ON order_items(product_id);
~~~

Rules expressed in the schema:

- `customers.id`, `products.id`, `orders.id`, and `order_items.id` are primary keys.
- Each customer email and product SKU is unique.
- An order must reference an existing customer.
- A line item must reference an existing order and an existing product.
- A product can appear at most once in a single order; if more quantity is needed, update the `quantity` of that line item.
- Quantity must be greater than 0; price and unit price cannot be negative.
- Deleting an order deletes its line items; deleting a referenced product is rejected.

In the example, `unit_price` is stored on the line item to record the price at the time of purchase. If you only joined to the current price in `products`, order history would change whenever the product price was updated. This is a business-driven data modeling decision, not merely a column-type decision.

## 8. Using an SQL Schema with Spring Data Relational R2DBC

### 8.1. Mapping Annotations Do Not Replace Constraints

A simple entity can be mapped as follows:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {
    @Id
    private Long id;

    @Column("full_name")
    private String fullName;

    private String email;
}
~~~

Key annotations:

- `@Table("customers")` specifies the mapped table.
- `@Id` marks the entity's ID property.
- `@Column("full_name")` specifies the column name when the Java property name differs from the column name.

These annotations do not mean the database already has `PRIMARY KEY`, `NOT NULL`, or `UNIQUE`. The schema must be created and managed separately. If email must be unique, define a unique constraint in the database, even if the application already checks before saving.

### 8.2. Reactive Repositories Do Not Bypass Database Rules

A repository can be declared as follows:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
~~~

Save operations through the repository still send commands to the database. If an insert or update violates a primary key, foreign key, unique, not-null, or check constraint, the database rejects the operation. In a reactive stream, the error appears as a publisher error signal; it can be handled using operators like `onErrorMap` or `onErrorResume` at the appropriate application boundary.

Example illustrating error handling at the service layer:

~~~java
public Mono<Customer> createCustomer(Customer customer) {
    return customerRepository.save(customer)
            .onErrorMap(this::translatePersistenceError);
}
~~~

`translatePersistenceError` is application-defined logic to convert persistence errors into appropriate business or API errors. Never return raw SQL messages or internal database details directly to clients. Nor should catching errors be treated as a substitute for constraints; constraints are what protect data against every write path.

### 8.3. Aggregate Model and Child Collections

Spring Data Relational organizes data persistence around an aggregate root. An aggregate root can contain child objects mapped with `@MappedCollection`. Conceptual example:

~~~java
@Table("orders")
public class Order {
    @Id
    private Long id;

    @Column("customer_id")
    private Long customerId;

    @MappedCollection(idColumn = "order_id")
    private Set<OrderItem> items = new HashSet<>();
}
~~~

In the example, `order_items.order_id` is the column linking child rows to the `orders` aggregate root. A foreign key in the schema still needs to be declared to ensure every `order_id` references an existing order. `@MappedCollection` describes how Spring Data Relational maps the collection; it does not replace a SQL foreign key.

Do not treat `@MappedCollection` like JPA's `@OneToMany`/`@ManyToOne`. Spring Data Relational does not provide a full object-relational mechanism with lazy-loading proxies. Design aggregate boundaries based on business consistency, then decide how to query related data using repositories, `R2dbcEntityTemplate`, or `DatabaseClient`.

### 8.4. Creating and Evolving Schemas with Migrations

Schemas must be version-controlled. Typically, projects store migration scripts in source control, for example:

~~~text
src/main/resources/db/migration/
    V1__create_customers.sql
    V2__create_orders.sql
    V3__add_customer_email_unique.sql
~~~

Each migration records an intentional change: creating a table, adding a column, adding a constraint, or creating an index. During deployment, the migration tool applies changes in order and records the executed versions. Choose a tool and configuration suited to the project's database system, environment, and driver; some traditional migration tools use JDBC even when the main application accesses data via R2DBC.

Do not rely on the application guessing or auto-generating the schema in production. Migrations make structural changes reviewable, repeatable, and consistently deployable across environments.

## 9. Validation in Java vs. Constraints in the Database

Java validation and SQL constraints serve two related but distinct purposes.

**Application-layer validation** provides early, user-friendly feedback. For example, Bean Validation can check required fields, email formats, or positive quantities before calling the repository:

~~~java
public record CreateProductRequest(
        @NotBlank String name,
        @PositiveOrZero BigDecimal price,
        @PositiveOrZero Integer stockQuantity
) {}
~~~

**Database constraints** are the final line of defense protecting data. They apply to every write: from APIs, background jobs, admin scripts, other applications, or direct SQL queries.

If you only check before writing, two concurrent requests can still both pass the check and then both attempt to save the same email. A unique constraint resolves that race condition: only one operation can succeed. Therefore, for uniqueness rules, the application should check beforehand to provide a clear message, while still catching and handling database duplicate rejections.

Practical guidelines:

- Use Java validation to check input data and generate friendly messages.
- Use `NOT NULL`, `UNIQUE`, `FOREIGN KEY`, and `CHECK` for data invariants that the database can enforce.
- Use transactions when multiple operations must succeed or fail together.
- Handle constraint errors at the appropriate boundary; distinguish user data errors from system errors.
- Do not rely on a preliminary `SELECT` check to guarantee uniqueness or existence under concurrent writes.

## 10. Transactions and Concurrent Operations

Constraints are typically checked when the database executes a write statement or at the configured checking time. When a statement violates a constraint, the database rejects it. If the operation is inside a transaction, the application must handle the transaction state according to the driver and database rules; typically the transaction must be rolled back when an error prevents it from continuing.

For example, creating an order may involve writing an `orders` row, writing `order_items` rows, and then updating stock. If only part succeeds, data can become inconsistent. Place steps requiring atomicity within the same reactive transaction properly configured for R2DBC.

R2DBC is a reactive API for relational access, so do not casually use imperative JDBC-style transactions. In Spring, use `TransactionalOperator` or an appropriate R2DBC transaction manager configuration to wrap the publisher. Ensure all operations in the transaction flow use the same connection/transaction context managed by the framework.

Constraints also do not solve every concurrency rule on their own. For example, two transactions simultaneously reading a stock quantity of 1 and both ordering 1 item can cause issues if they simply read and then write without synchronization. You may need conditional update statements, appropriate locking, or optimistic locking. Let the database perform the check and update atomically whenever possible, for example:

~~~sql
UPDATE products
SET stock_quantity = stock_quantity - 1
WHERE id = 10
  AND stock_quantity >= 1;
~~~

The application checks the affected row count: if it is `0`, either the product does not exist or there is insufficient stock. Specific rules should be designed explicitly to distinguish the two cases if required by business logic.

## 11. Common Design Mistakes

### Declaring `@Id` Without a Database Primary Key

`@Id` helps Spring Data recognize the identifier field. If the schema lacks an appropriate primary key or unique constraint, the database is not protected in the way the code assumes. Verify the actual DDL.

### Checking Duplicates Only with `SELECT` Before `INSERT`

Two concurrent requests can both observe that an email does not exist yet. Use `UNIQUE` so the database safely enforces uniqueness; the application can check beforehand to improve error messages.

### Storing Reference IDs Without a Foreign Key

A `BIGINT` `customer_id` column is just a number without a foreign key. Data can end up pointing to a deleted or nonexistent customer. Declare a foreign key if the relationship needs to be protected in the database.

### Using `ON DELETE CASCADE` for Every Relationship

Cascading can wipe out history or data that must be retained. Review data lifecycles and audit requirements before choosing deletion behavior.

### Allowing Unintended `NULL` Values

`NULL` has special semantics in SQL and can cause conditions, unique constraints, or check constraints to behave differently than expected. Declare `NOT NULL` on required attributes and check `NULL` cases in your design.

### Assuming Java Annotations Automatically Generate All Constraints

Mapping annotations are not automatically DDL. Use migrations to create primary keys, foreign keys, unique constraints, check constraints, and indexes; verify the real schema in each environment.

### Leaving Constraints Unnamed

Without explicit names, the database may auto-generate hard-to-read constraint names. Clear names like `fk_orders_customer` or `uq_customers_email` make reading migrations, logs, and diagnosing errors much easier. Naming conventions should be consistent across the project.

## 12. Process for Designing Constraints for a New Table

When adding a table, you can follow this sequence:

1. Identify what entity or event a single row represents.
2. Choose data types and length/precision limits for each column.
3. Choose the primary key; consider natural keys, surrogate keys, or composite keys.
4. Mark all required attributes as `NOT NULL`.
5. Identify values that must be unique and add `UNIQUE`.
6. Identify relationships to other tables and add `FOREIGN KEY`.
7. Identify value domains and add `CHECK` when expressions can be evaluated at the row level.
8. Choose `DEFAULT` when the database has a sensible default value.
9. Review `ON DELETE`/`ON UPDATE` behavior according to the data lifecycle.
10. Review common queries to decide on indexes; avoid creating duplicate indexes.
11. Write a migration, apply it in a development environment, and test both valid and invalid cases.
12. Map entities and repositories in Spring Data Relational R2DBC so Java types and column names match the schema.

## 13. Self-Check Exercises

### Exercise 1: Identifying Keys

A `students` table has columns `id`, `student_code`, `full_name`, and `email`. `student_code` does not change over a student's lifecycle; `email` may change. Propose a primary key and unique constraints.

Hint: You can choose `id` as a surrogate key and add `UNIQUE(student_code)`. If email must be unique in the system, add `UNIQUE(email)`, plus `NOT NULL` if email is required.

### Exercise 2: Protecting Relationships

A `payments` table has `order_id`. Write constraints so every payment belongs to a real order. Determine what happens when an order is deleted.

Hint: Use `order_id NOT NULL` and a foreign key referencing `orders(id)`. Choose `RESTRICT` if an order with payments cannot be deleted; if payment data must be preserved as history, an appropriate retention policy is usually needed instead of cascade.

### Exercise 3: Restricting Value Domains

A `discounts` table has `percentage` between 0 and 100. Write an appropriate data type and constraint.

Hint:

~~~sql
percentage DECIMAL(5, 2) NOT NULL,
CONSTRAINT ck_discounts_percentage
    CHECK (percentage >= 0 AND percentage <= 100)
~~~

### Exercise 4: Distinguishing Validation and Constraints

An API checks emails using Bean Validation before calling `save`. Why does the table still need a unique constraint?

Hint: Validation improves user experience and provides early feedback, but it does not eliminate concurrent writes or other write paths. A unique constraint protects uniqueness where the data is stored.

### Exercise 5: Interpreting Database Errors

An application saves an `Order` with a nonexistent `customerId`. If `orders.customer_id` has a foreign key, what happens?

Hint: The database rejects the write operation due to a referential integrity violation. In a reactive pipeline, the error travels as an error signal; the application layer needs to translate the persistence error into an appropriate response.

## 14. Key Takeaways for Working with Spring Data Relational R2DBC

- SQL and schemas are the foundation of relational data; R2DBC only changes how the application communicates with the database.
- Primary keys identify rows; foreign keys protect links between tables.
- `NOT NULL`, `UNIQUE`, `CHECK`, and `DEFAULT` express distinct data rules that can be combined.
- Constraints must be created in the database via DDL/migrations. `@Id`, `@Table`, `@Column`, and `@MappedCollection` handle object mapping and do not replace constraints.
- Java validation provides friendly error messages; database constraints protect data against all write paths and concurrency scenarios.
- Choose foreign key delete/update actions according to the data lifecycle; consider indexes based on actual queries.
- With R2DBC, handle errors and transactions within the reactive pipeline while keeping critical integrity rules in the database.

When reading or designing an entity in Spring Data Relational R2DBC, always cross-check three parts: the actual SQL structure, the business rules for the data, and how the entity/repository maps to that structure. These three parts must stay aligned for the application to store data reliably.
