# Designing Foreign Keys, Unique Constraints, and Data Invariants

In Spring Data Relational R2DBC, repositories and `R2dbcEntityTemplate` help applications read, insert, update, and delete entities reactively. However, data correctness cannot rely solely on checks in service code. When multiple requests run concurrently, multiple instances write data simultaneously, or another program accesses the same database, application-layer checks alone are not enough. The database needs constraints to protect relationships and critical invariants right where data is stored.

Foreign keys ensure a value references a valid record. Unique constraints prevent duplicate values or combinations of values. Constraints such as `NOT NULL`, `CHECK`, and primary keys enforce additional rules. Combining them with transactions and business-layer validation keeps data consistent even when multiple operations occur simultaneously.

## 1. What Is a Data Invariant?

A data invariant is a condition that must always hold true for persisted state. For example:

- Every order must reference an existing customer.
- Every account has a unique identifier within a tenant scope.
- A customer's registration email must be unique according to the product's normalization rules.
- Inventory stock quantity must never be negative.
- Totals or record statuses must obey defined domain rules.

Some invariants can be expressed directly with relational structures: `PRIMARY KEY`, `FOREIGN KEY`, `UNIQUE`, `NOT NULL`, and `CHECK`. More complex rules must be verified in the domain/service layer or within transactions, such as limit sums across multiple lines, workflow state transitions, or conditions spanning multiple aggregates.

Place rules at the layer capable of protecting them against all write paths. If a condition can be expressed as a database constraint, the constraint is usually the most reliable final line of defense. Application-layer validation is still necessary to return user-friendly errors and catch bad input early, but it does not replace constraints.

## 2. Commonly Used Constraint Types

| Constraint | Protected Rule | Example |
| --- | --- | --- |
| `PRIMARY KEY` | Each row has a unique, non-null identifier | `customer.id` |
| `FOREIGN KEY` | Referenced value must exist in the referenced table | `orders.customer_id` references `customer.id` |
| `UNIQUE` | A column or column combination cannot duplicate per database rules | `(tenant_id, email_normalized)` |
| `NOT NULL` | Column must have a value | `orders.created_at` |
| `CHECK` | Value must satisfy a conditional expression | `quantity >= 0` |

Constraints can be combined. For example, an account table with primary key `id`, required email, email unique within a tenant, and `tenant_id` referencing a valid tenant:

```sql
CREATE TABLE tenant (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL
);

CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    email_normalized VARCHAR(320) NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    CONSTRAINT fk_customer_tenant
        FOREIGN KEY (tenant_id) REFERENCES tenant(id),
    CONSTRAINT uq_customer_tenant_email
        UNIQUE (tenant_id, email_normalized)
);
```

This SQL uses common PostgreSQL syntax. Data types, constraint naming, and certain details may vary across database engines. Constraints are created in the database schema; entity annotations alone do not replace this complete schema definition.

## 3. Foreign Keys Protect Relationships Between Tables

A foreign key specifies that a column or group of columns in a child table must match a primary key or a referenced unique key in a parent table. For example, an order must belong to an existing customer:

```sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customer(id)
);
```

`orders.customer_id` is a foreign key. The database rejects inserting or updating an order if `customer_id` does not point to a valid customer. `NOT NULL` ensures an order must have a customer. If a column is nullable and lacks `NOT NULL`, `NULL` values are typically accepted because there is no reference value to check; details vary by database engine.

Foreign keys protect referential integrity. They do not create object graphs in Java, do not automatically load customers when reading orders, and do not equate to ORM entity operation cascades. Spring Data Relational R2DBC maps columns via metadata; database relationships are still enforced by the database.

### Foreign Keys in Spring Data R2DBC Entities

A straightforward representation is storing the ID of the referenced object:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("orders")
public class Order {

    @Id
    private Long id;

    @Column("customer_id")
    private Long customerId;

    @Column("created_at")
    private LocalDateTime createdAt;

    // Constructors, getters, and required domain methods.
}
```

`customerId` maps to the `customer_id` column. The `fk_orders_customer` constraint is declared in the schema and checked by the database on write. Having a Java field named `customerId` does not automatically create a foreign key; the schema must be created via migrations or a schema management tool.

When customer information is needed, the service can combine two reactive queries, use a suitable join query, or design a projection. Do not assume R2DBC provides JPA/Hibernate-style lazy loading and navigation proxies.

## 4. Choosing Behavior When a Referenced Record Is Deleted

When a parent row is referenced by child rows, the database needs to know how to behave if the application deletes or changes the parent row's key. Common behaviors include:

| Behavior | Meaning | Use Case |
| --- | --- | --- |
| `RESTRICT` | Rejects deleting/modifying the parent row while referencing child rows exist; exact check timing depends on the database engine | Child data must be handled explicitly before deleting the parent |
| `NO ACTION` | Performs no automatic action; database checks the constraint according to engine rules and timing | You want the database to reject operations that violate the relationship |
| `CASCADE` | Deletes or updates the corresponding key in child rows when the parent row is deleted or its key is updated | Child rows truly belong to the parent's lifecycle and may be deleted together |
| `SET NULL` | Sets the foreign key column in child rows to `NULL` when the parent row is deleted or its key is updated | The relationship is optional and child rows retain independent meaning |
| `SET DEFAULT` | Sets the foreign key column to its default value | Suitable only when the default value is valid and meaningful in the domain |

Example forbidding customer deletion while orders still exist:

```sql
CONSTRAINT fk_orders_customer
    FOREIGN KEY (customer_id)
    REFERENCES customer(id)
    ON DELETE RESTRICT
```

Example allowing deletion of address rows that depend entirely on the customer:

```sql
CONSTRAINT fk_customer_address
    FOREIGN KEY (customer_id)
    REFERENCES customer(id)
    ON DELETE CASCADE
```

Only use `CASCADE` when deleting child rows aligns with the business lifecycle. Deleting a customer does not necessarily mean deleting invoices, transaction history, or placed orders. For data requiring an audit trail, archiving, anonymization, or soft delete workflows are usually needed instead of physical cascade deletion.

`SET NULL` requires the foreign key column to be nullable. If the column is `NOT NULL`, the operation cannot succeed under that behavior. Also review multi-table cascade chains, triggers, and retention policies before choosing a behavior.

## 5. Composite Foreign Keys and Tenant Isolation

In a multi-tenant system, simply checking that `customer_id` exists may be insufficient. An order belonging to tenant A must not reference a customer belonging to tenant B. You can protect this relationship using a composite foreign key containing both `tenant_id` and `customer_id`.

```sql
CREATE TABLE customer (
    id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL,
    name VARCHAR(200) NOT NULL,
    CONSTRAINT pk_customer PRIMARY KEY (id),
    CONSTRAINT uq_customer_tenant_id UNIQUE (tenant_id, id)
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    CONSTRAINT fk_orders_customer_tenant
        FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customer(tenant_id, id)
);
```

The unique key `(tenant_id, id)` on the customer table creates a valid target key for the composite foreign key. When inserting an order, the database verifies both values belong to the same customer. Thus, a `customer_id` may exist yet still cannot be referenced from the wrong tenant.

At the application layer, you must still verify the user is authorized to operate on that tenant. Constraints guard data against bugs or non-compliant write paths, but they do not replace access control and authorization.

## 6. Single-Column Unique Constraints

`UNIQUE` ensures no two rows share the same value in a specified column or column combination according to the database engine's semantics. For example, an account code must be unique:

```sql
CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    account_code VARCHAR(50) NOT NULL,
    CONSTRAINT uq_account_code UNIQUE (account_code)
);
```

When a request creates an account with an `account_code` already in use, the database rejects the insert. This protects data even when two concurrent requests try to register the same code simultaneously.

Unique constraints can be created via DDL in migrations. Some databases also support unique indexes directly. As a design practice, give constraints meaningful names so they are easy to identify during error handling and schema inspection.

## 7. Composite Multi-Column Unique Constraints

Many rules require uniqueness within a scope rather than across the entire table. For example, an email only needs to be unique within each tenant:

```sql
ALTER TABLE customer
    ADD CONSTRAINT uq_customer_tenant_email
    UNIQUE (tenant_id, email_normalized);
```

The composite constraint ensures no two rows share the same `tenant_id` and `email_normalized`. Two different tenants can have the same email if business rules permit it.

Other examples of composite uniqueness:

- `(tenant_id, external_reference)` so external reference codes are unique per tenant.
- `(warehouse_id, product_id)` so each product has only one stock row per warehouse.
- `(room_id, booking_date, time_slot)` to allow at most one reservation per room, date, and time slot.
- `(country_code, tax_identifier)` if tax identifiers only need to be unique per country.

Identify the exact business scope before creating a constraint. If you create a global unique constraint on `email` when the actual requirement is per-tenant uniqueness, the application will reject valid cases. Conversely, omitting `tenant_id` from a tenant-scoped uniqueness rule allows duplicates within the same scope.

## 8. NULL and Unique Constraints

The meaning of `NULL` in unique constraints often causes confusion. Many database engines, including PostgreSQL by default, allow multiple rows to contain `NULL` in a unique column because `NULL` is not considered equal to another `NULL` under standard comparisons. Some databases have options or different rules; check the specific database documentation.

If the business rule requires every row to have a value and for that value to be unique, combine `NOT NULL` with `UNIQUE`:

```sql
CREATE TABLE user_account (
    id BIGINT PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    CONSTRAINT uq_user_account_username UNIQUE (username)
);
```

With composite uniqueness, if any of the columns can be null, behavior may differ from expectations. Do not use null to represent "unknown" and assume a unique constraint limits the number of unknown rows. If a domain rule allows at most one absent value, choose a design and constraint supported by the database engine.

## 9. Normalizing Values Before Applying Uniqueness

Unique constraints compare values according to database collation and rules. For example, `User@example.com` and `user@example.com` might be treated as distinct under one configuration, yet equivalent under another. Leading/trailing whitespace or Unicode normalization forms can also affect comparisons.

If business rules require case-insensitive or canonical comparisons, define a clear canonicalization rule and apply it consistently. One option is storing a separate normalized column:

```sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    email VARCHAR(320) NOT NULL,
    email_normalized VARCHAR(320) NOT NULL,
    CONSTRAINT uq_customer_email_normalized UNIQUE (email_normalized)
);
```

The application computes `email_normalized` using the agreed rule before saving. If the database supports generated columns or suitable functional indexes, normalizing directly in the database can be considered. Syntax and semantics depend on the engine.

Do not blindly lowercase every part of every identifier if business rules forbid it. Clearly specify how to handle Unicode, whitespace, accents, locales, and edge cases. A database constraint only protects stored values; it does not automatically know the product's desired normalization rules.

## 10. Soft Deletes and Uniqueness

Soft deletion typically keeps the row in the database and sets a `deleted_at` or `is_deleted` flag. If a unique constraint still applies across all rows, a soft-deleted account continues to occupy the username/email, preventing creation of a new record reusing that value.

If business rules allow reusing values after soft deletion, uniqueness must be designed around active status. PostgreSQL supports partial unique indexes:

```sql
CREATE UNIQUE INDEX uq_active_customer_email
    ON customer (tenant_id, email_normalized)
    WHERE deleted_at IS NULL;
```

This is PostgreSQL-specific syntax, not portable across all databases. On other engines, you may need generated columns, status columns, or a different data model. Ensure application-level checks match the index predicate exactly.

Soft deletes also affect foreign keys. A row marked deleted still physically exists, so foreign keys still treat it as a valid referenced record. If business rules forbid creating new orders for a soft-deleted customer, check status in the service/domain and protect the operation appropriately with transactions or the data model. Standard foreign keys do not check the parent row's `deleted_at` column.

## 11. CHECK Constraints for Single-Row Rules

`CHECK` ensures an expression holds true for every inserted or updated row. For instance, positive quantities and non-negative prices:

```sql
CREATE TABLE order_line (
    id BIGINT PRIMARY KEY,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL,
    CONSTRAINT ck_order_line_quantity CHECK (quantity > 0),
    CONSTRAINT ck_order_line_unit_price CHECK (unit_price >= 0)
);
```

`NOT NULL` is still required. In SQL, a `CHECK` expression typically passes if it evaluates to `TRUE` or `UNKNOWN` (due to `NULL`); therefore `CHECK (quantity > 0)` alone does not prevent `quantity = NULL` in engines following these semantics. Combine it with `NOT NULL` to protect required fields.

Other invariants expressible with `CHECK`:

```sql
ALTER TABLE account
    ADD CONSTRAINT ck_account_balance_nonnegative
    CHECK (balance >= 0);

ALTER TABLE booking
    ADD CONSTRAINT ck_booking_time_range
    CHECK (ends_at > starts_at);
```

`CHECK` expressions are generally evaluated on a single row. Do not use them as a general mechanism to validate aggregates across multiple rows or query other tables; support and behavior vary across engines. Cross-row invariants need specialized constraints, transactions, locking, or suitable data modeling.

## 12. Distinguishing Constraints from Application-Layer Validation

Validation and constraints address complementary goals:

| Layer | Goal | Example |
| --- | --- | --- |
| API/request validation | Reject malformed input early and return clear errors | Malformed email, invalid quantity |
| Domain/service | Check business rules and authorization to perform actions | Forbid placing an order if the customer does not belong to the current tenant |
| Database constraint | Protect persisted state across all write paths and concurrent races | Unique email, customer FK, positive quantity check |
| Transaction | Ensure a group of related operations succeed or roll back together per policy | Create order and order lines in one transaction |

For example, a service may check whether an email already exists before creating an account to respond quickly. Yet a unique constraint is still necessary because two requests might both observe the email missing and then both insert. Only the database can atomically arbitrate between those two competing writes.

Do not remove validation just because the database has constraints. Waiting until insert to discover an invalid email can expose confusing technical errors to users. Conversely, do not rely solely on validation and omit constraints for invariants that must be guarded at the data layer.

## 13. Race Conditions When Checking Before Writing

A common bug is executing a "check then insert" sequence as if those two steps were atomic:

```java
public Mono<Customer> register(String email) {
    return customerRepository.existsByEmail(email)
            .flatMap(exists -> {
                if (exists) {
                    return Mono.error(new EmailAlreadyRegisteredException());
                }

                return customerRepository.save(Customer.newCustomer(email));
            });
}
```

This snippet returns an early error when the email already exists, but it is not enough to guarantee uniqueness. Two requests can execute as follows:

```text
Request A                 Database                 Request B
    |                         |                         |
    |---- check email ------->|<------ check email -----|
    |<--- not found ----------|---------- not found ----|
    |                         |                         |
    |---- insert email ------>|<------ insert email ----|
    |                         |                         |
    |<--- insert succeeds ----|---- unique violation -->|
```

The unique constraint ensures at most one insert succeeds. The other request receives a constraint violation error. Without the constraint, both could succeed and produce duplicate data.

Therefore, you can keep the pre-check for better user experience, but the insert result and unique constraint remain the final authority. Always handle duplicate errors on the write path.

## 14. Handling Constraint Errors in Spring Data R2DBC

When the database rejects an operation due to a unique, foreign key, check, or not-null violation, the driver emits an error that propagates through the publisher. Spring may translate certain driver errors into exceptions in the `DataAccessException` hierarchy, such as `DuplicateKeyException` or `DataIntegrityViolationException`, depending on the driver and execution context.

Identified duplicate key errors can be handled in the service:

```java
public Mono<Customer> register(String email) {
    Customer customer = Customer.newCustomer(email);

    return customerRepository.save(customer)
            .onErrorMap(DuplicateKeyException.class,
                    error -> new EmailAlreadyRegisteredException());
}
```

This example assumes data-access exception translation maps unique errors to `DuplicateKeyException`. Verify the actual driver and version in use. Some constraint errors may only map to `DataIntegrityViolationException` or a driver-specific exception. Do not convert every integrity error into "email already exists" because the root cause could be an FK, CHECK, or NOT NULL violation.

If multiple constraints need to be distinguished, rely on the error type, constraint name, or database error code provided by the driver. Centralize translating infrastructure errors into domain errors at a clear boundary, then let controllers/APIs map them to appropriate status codes. For example, duplicates often become HTTP 409 Conflict; malformed input can be 400 Bad Request. Specific choices depend on the API contract.

Never log passwords, URLs containing credentials, or full sensitive payloads inside exceptions. Log error codes and constraint names when safe, along with a correlation ID for request tracing.

## 15. Foreign Keys and Operation Ordering in Transactions

When creating parent and child records, ensure the parent record exists before child records reference it, unless the database and constraints are configured for deferred checking in an appropriate way. The simplest and most common approach is saving the parent, receiving its ID, and then saving children within the same transaction:

```java
public Mono<Order> createOrder(Order order, List<OrderLine> lines) {
    return transactionalOperator.transactional(
            orderRepository.save(order)
                    .flatMap(savedOrder ->
                            Flux.fromIterable(lines)
                                    .map(line -> line.withOrderId(savedOrder.getId()))
                                    .concatMap(orderLineRepository::save)
                                    .then(Mono.just(savedOrder))
                    )
    );
}
```

This snippet illustrates chaining operations inside one transactional publisher. `withOrderId` represents a method creating a copy of the line attached to the order ID per the application's entity model. If saving a child line fails, the error propagates through the pipeline so the transaction manager can roll back operations participating in the transaction.

With `Flux`, choose concurrency intentionally. If child writes are independent and the database permits it, parallel execution inside the transaction may be considered. If ordering is required or you want to reduce pool pressure, `concatMap` executes sequentially. Do not call `subscribe()` separately per line, as that can detach them from the transaction and error stream of the order creation operation.

## 16. Multi-Row Invariants and Concurrent Updates

Not every invariant is a simple unique or check constraint. For example, total reservations must not exceed an event's capacity. If a service only reads the current total, checks availability, and then inserts, two concurrent requests could both see one remaining spot and both claim the last spot.

Several design patterns can protect this kind of invariant:

- Perform an atomic conditional update, such as incrementing `reserved_count` only when `reserved_count + requested <= capacity`, then check the affected row count.
- Use transactions with an appropriate isolation level or locking mechanism to serialize competing operations.
- Model reservable resources as individual rows and use unique constraints so each resource can only be booked once in the same time scope.
- Use optimistic locking/versioning if supported by the model and Spring Data version, then handle update conflicts by re-reading or returning an appropriate error.

Example conditional update in PostgreSQL SQL:

```sql
UPDATE event_capacity
SET reserved_count = reserved_count + :requested
WHERE event_id = :eventId
  AND reserved_count + :requested <= capacity;
```

If the updated row count is 1, the operation successfully reserved capacity under the condition. If 0, either the event does not exist or insufficient capacity remains; the service can distinguish the two cases via an additional query or business rule. The statement is a single atomic database operation on the updated row, eliminating the gap between separate read and write steps.

## 17. Designing Aggregates and Relationships in Spring Data Relational

Spring Data Relational is not JPA. Do not design entities expecting lazy-loading proxies, cascading persistence, or automatic Hibernate-style object graphs. The aggregate model defines the boundaries of data persisted together and the update responsibilities of each part.

For an order with multiple order lines, `Order` can be treated as the aggregate root and `OrderLine` as data belonging to the order's lifecycle. Spring Data Relational provides annotations like `@MappedCollection` to map collections managed by an aggregate root in suitable models. DDL still requires the corresponding primary and foreign keys; mapping annotations do not replace constraints.

For relationships between two independent aggregates, such as `Order` and `Customer`, typically store a reference ID (`customerId`) and query the required aggregate explicitly. This avoids accidentally loading or updating a large object network simply because of a relationship property.

Choose aggregate boundaries based on domain consistency rules. If two pieces of data must change atomically, design explicit transactions and ownership relationships. If they have independent lifecycles, holding ID references usually makes write responsibilities clearer.

## 18. Indexes and Performance of Foreign Keys and Unique Constraints

Unique constraints are typically implemented by the database using a unique index or equivalent structure. This index both enforces uniqueness and accelerates queries on the unique columns. There is no need to create a completely redundant index if the database already created one for that constraint.

For columns on the child side of a foreign key, not every database engine creates an index automatically. PostgreSQL, for instance, does not automatically create an index on referencing columns in child tables. An index on `orders.customer_id` can speed up querying orders by customer and help certain parent-table delete/update checks scan referencing rows faster.

Example:

```sql
CREATE INDEX ix_orders_customer_id ON orders(customer_id);
```

For a composite foreign key `(tenant_id, customer_id)`, inspect actual queries and consider a composite index with an appropriate column order:

```sql
CREATE INDEX ix_orders_tenant_customer
    ON orders(tenant_id, customer_id);
```

Indexes also carry write and storage costs. Do not add indexes by guesswork; use query plans, query frequencies, row counts, and update costs to decide. Unique constraints and foreign keys serve integrity; additional indexes primarily serve performance and do not replace data rules.

## 19. Managing Constraints with Database Migrations

Schemas and constraints should be managed with versioned migrations rather than relying solely on entity annotations or manual changes in production databases. Migrations give development, testing, and production environments the same reproducible data structure.

Example SQL migration:

```sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    email_normalized VARCHAR(320) NOT NULL,
    CONSTRAINT uq_customer_tenant_email
        UNIQUE (tenant_id, email_normalized)
);

CREATE TABLE orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    CONSTRAINT fk_orders_customer_tenant
        FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customer(tenant_id, id)
        ON DELETE RESTRICT
);

CREATE INDEX ix_orders_tenant_customer
    ON orders(tenant_id, customer_id);
```

This is a PostgreSQL example; `GENERATED BY DEFAULT AS IDENTITY` and index syntax may need adjustment for other databases. With Spring Boot, Flyway or Liquibase is commonly used to manage migrations. Migration tools typically run via JDBC or their own mechanisms; having the runtime application use R2DBC does not mean every migration tool automatically runs over R2DBC. Configure migrations separately and ensure they finish before the application relies on the new schema.

When adding a constraint to a table that already contains data, the migration can fail if existing data violates the rule. A safe workflow typically includes:

1. Auditing and locating duplicate, null, or orphaned reference data.
2. Determining how to fix, merge, or remove violating data based on business decisions.
3. Deploying application changes in a compatible sequence if needed, such as writing data in the new format before enforcing the constraint.
4. Adding constraints/indexes via migrations while controlling lock duration and workload impact.
5. Verifying schema and data post-migration in the corresponding environment.

Never drop a constraint just to get a migration to pass without understanding the impact on invariants. For large tables, evaluate online or concurrent index/constraint creation strategies supported by your database.

## 20. Testing Data Integrity

Service unit tests can verify validation and error handling, but they do not prove the database actually enforces foreign keys or unique constraints. Include integration tests with a compatible database engine to confirm real behavior.

Scenarios that should be tested include:

- Inserting an order with an existing `customer_id` succeeds.
- Inserting an order with a non-existent `customer_id` is rejected.
- Deleting a customer with referencing orders is rejected when using `RESTRICT`.
- Two concurrent requests creating the same unique value: at most one succeeds.
- Composite uniqueness allows the same email across different tenants but rejects duplicates within the same tenant.
- Null or negative values are blocked properly by `NOT NULL` and `CHECK`.
- An error in a child operation causes the transaction to roll back related changes.
- Soft deletes exhibit proper uniqueness behavior according to value-reuse rules.

For reactive tests, Reactor Test's `StepVerifier` can verify that publishers complete successfully or emit errors. For contention scenarios, run multiple concurrent subscriptions in integration tests and verify the final database state, not just the exception type on one request.

## 21. Practical Guidelines

- Define data invariants clearly before designing tables and relationships.
- Use primary keys for identity, foreign keys for referential integrity, and unique constraints for values/combinations that must be unique.
- Combine `NOT NULL` with `UNIQUE` when a field is required to have a value.
- Use `CHECK` for single-row conditions and separately address cross-row rules needing transactions or concurrency mechanisms.
- Choose `ON DELETE` according to business lifecycles; never use cascade merely to make deleting data easier.
- For multi-tenant systems, consider composite unique constraints and composite foreign keys to prevent cross-tenant references.
- Define normalization rules before creating unique constraints on emails, usernames, or identifiers.
- Keep validation at the application layer for clear error messages, but let database constraints arbitrate competing writes.
- Catch and classify constraint errors in the reactive pipeline; do not map every integrity error to the same business error.
- Manage schemas with migrations and test constraints against a compatible database.
- Design aggregates suited to Spring Data Relational; do not assume JPA-style relationship and cascade mechanics.
- Create additional indexes based on queries and query plans without duplicating indexes already generated by unique constraints.

## 22. Conclusion

Foreign keys protect relationships between tables, unique constraints protect the uniqueness of a value or combination of values, and `NOT NULL` and `CHECK` protect basic single-row conditions. These constraints form the foundation that keeps data accurate when multiple requests, multiple instances, and multiple write paths access the database concurrently.

In Spring Data Relational R2DBC, entity mapping and reactive repositories help organize data operations, while database constraints guard integrity at the storage layer. Combining validation, reactive transactions, constraint error handling, and controlled migrations enables the application to uphold business invariants without relying on a single isolated check in a service.
