# Building Order, OrderItem, and Customer Schemas with Migrations

A sales application typically needs to store customers, orders, and order line items. When using Spring Data JDBC, you need to design both the **relational schema** and the **aggregate boundaries** before writing repositories.

In this example:

- `Customer` is an independent aggregate root.
- `PurchaseOrder` is another aggregate root and stores the customer ID as a reference.
- `OrderItem` is a child entity belonging to an order's lifecycle.

The schema will have three tables: `customer`, `purchase_order`, and `order_item`. The initial Flyway migration creates the tables, primary keys, foreign keys, unique constraints, check constraints, and indexes. Then, the Java entities use `AggregateReference` to reference the customer and `@MappedCollection` to map the list of line items.

This lesson walks from business requirements to the relational diagram, DDL, Java mapping, repositories/services, and migration management workflow.

## 1. Identifying data and aggregate boundaries

Before writing DDL, answer two questions:

1. Which records have their own identity and lifecycle?
2. Which data exists only inside an aggregate?

### Customer

A customer can exist independently of individual orders. A customer can place multiple orders, and saving an order should not recreate or delete the customer.

Therefore, `Customer` is a separate aggregate root.

### PurchaseOrder

An order has its own identity and status. It references a customer but does not own the customer's lifecycle.

`PurchaseOrder` is an aggregate root. It stores the customer ID as a reference.

### OrderItem

An order item only has meaning within the scope of an order. It is added, modified, or removed together with the order and is not directly referenced by other aggregates.

`OrderItem` is a child entity of `PurchaseOrder`.

Relational diagram:

~~~mermaid
erDiagram
    CUSTOMER ||--o{ PURCHASE_ORDER : places
    PURCHASE_ORDER ||--|{ ORDER_ITEM : contains

    CUSTOMER {
        bigint id PK
        varchar email UK
        varchar full_name
        timestamptz created_at
    }

    PURCHASE_ORDER {
        bigint id PK
        varchar order_number UK
        bigint customer_id FK
        varchar status
        timestamptz created_at
        bigint version
    }

    ORDER_ITEM {
        bigint order_id PK,FK
        integer line_no PK
        varchar sku
        integer quantity
        numeric unit_price
    }
~~~

One Customer can have many PurchaseOrders. One PurchaseOrder has one or more OrderItems according to the example's business rules.

### Why not embed Customer inside PurchaseOrder?

If you declare a `Customer` object directly inside `PurchaseOrder` as a referenced entity, Spring Data JDBC may treat `Customer` as part of the order's aggregate. That is inappropriate when multiple orders reference the same customer.

Use `AggregateReference<Customer, Long>` to represent the ID of another aggregate. When saving `PurchaseOrder`, Spring Data JDBC stores the customer ID value in the `customer_id` column; it does not save or delete the `Customer` aggregate along with the order's lifecycle.

## 2. Data rules to protect

The sample schema enforces the following rules:

| Rule | Protection mechanism |
| --- | --- |
| Every customer has a unique ID | Primary key on `customer.id` |
| Customer emails cannot be duplicated | Unique constraint on `customer.email` |
| Every order has a unique number | Unique constraint on `purchase_order.order_number` |
| Every order must belong to an existing customer | Foreign key `purchase_order.customer_id` |
| Every order item belongs to an existing order | Foreign key `order_item.order_id` |
| A SKU can appear only once per order | Unique constraint `(order_id, sku)` |
| Quantity must be greater than 0 | Check constraint `quantity > 0` |
| Unit price must be non-negative | Check constraint `unit_price >= 0` |
| Order status belongs to the allowed set of values | Check constraint on `status` |

Unique `(order_id, sku)` is a business decision for this example. If the system allows the same SKU to appear multiple times in a single order, omit that constraint or choose another appropriate unique key.

### Deletion behavior

Deleting a Customer should not be allowed while orders still reference that customer. The foreign key will block that operation. The application can use soft delete or an archive/hide workflow for customers instead of physical deletion.

`OrderItem` belongs to the `PurchaseOrder` aggregate. Spring Data JDBC manages the line items automatically when saving/deleting the root. The DDL can use a standard foreign key; there is no need to rely on cascade delete to simulate the aggregate lifecycle.

## 3. Writing the V1 migration for PostgreSQL

This example uses PostgreSQL to illustrate identity and timestamp syntax. If your project uses MySQL, Oracle, or SQL Server, write the DDL in that database's dialect; do not assume one SQL file runs across all vendors.

With Flyway, place the migration file at:

~~~text
src/main/resources/db/migration/V1__create_customer_order_schema.sql
~~~

Contents:

~~~sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY,
    email VARCHAR(320) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_customer PRIMARY KEY (id),
    CONSTRAINT uq_customer_email UNIQUE (email)
);

CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY,
    order_number VARCHAR(40) NOT NULL,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT pk_purchase_order PRIMARY KEY (id),
    CONSTRAINT uq_purchase_order_number UNIQUE (order_number),
    CONSTRAINT fk_purchase_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer(id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_purchase_order_status
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
);

CREATE TABLE order_item (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL,

    CONSTRAINT pk_order_item
        PRIMARY KEY (order_id, line_no),
    CONSTRAINT fk_order_item_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_order(id)
        ON DELETE RESTRICT,
    CONSTRAINT uq_order_item_sku
        UNIQUE (order_id, sku),
    CONSTRAINT ck_order_item_quantity
        CHECK (quantity > 0),
    CONSTRAINT ck_order_item_unit_price
        CHECK (unit_price >= 0)
);

CREATE INDEX idx_purchase_order_customer_created
    ON purchase_order(customer_id, created_at DESC);

CREATE INDEX idx_order_item_sku
    ON order_item(sku);
~~~

### Explaining the schema choices

**Customer**

- `id` is an identity primary key.
- `email` has a unique constraint so no two customers share the same email.
- `created_at` has a default timestamp so the database fills in the creation time if the INSERT statement does not provide a value.

**PurchaseOrder**

- `order_number` is a business code with its own unique constraint separate from the primary key.
- `customer_id` is a required foreign key. `ON DELETE RESTRICT` prevents deleting a Customer that still has orders.
- `status` has a check constraint to accept only defined statuses.
- `version` is for optimistic locking using `@Version` in the entity.
- The index on `(customer_id, created_at)` supports querying a customer's orders chronologically.

**OrderItem**

- Does not need a single-column ID in this example. The pair `(order_id, line_no)` identifies the line item within an order.
- `line_no` is the key column corresponding to the element's position in the List.
- Unique `(order_id, sku)` expresses the rule that a SKU appears only once per order.
- Check constraints ensure positive quantity and non-negative unit price.
- The index on `sku` is useful if the system searches orders by SKU across the entire table.

Do not add indexes out of habit. Base them on actual queries and execution plans; every index increases write cost and storage usage.

## 4. Configuring Flyway and migration rules

Spring Boot can automatically run Flyway migrations at application startup if Flyway is on the classpath and a DataSource is configured.

Example configuration:

~~~properties
spring.flyway.enabled=true
spring.flyway.locations=classpath:db/migration
~~~

The application still needs database connection settings such as URL, username, and password provided via environment variables or appropriate secure configuration.

With Gradle, main dependencies may include Spring Data JDBC, Flyway, and the database JDBC driver:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jdbc")
    implementation("org.flywaydb:flyway-core")
    runtimeOnly("org.postgresql:postgresql")
    runtimeOnly("org.flywaydb:flyway-database-postgresql")
}
~~~

Flyway's database module depends on the Flyway version in use. Check the corresponding dependency managed by the Spring Boot BOM.

### Migration versioning rules

- Migrations that have already run on a shared environment must be treated as immutable.
- When schema changes are needed, create a new migration such as `V2__add_order_note.sql` instead of editing an already-applied V1 file.
- Each migration should perform an explainable schema change and deploy in order.
- Test migrations from an empty schema and from the latest schema version running in production.
- Do not simultaneously run Flyway and another automatic schema generation mechanism against the same database in production.

Example V2 migration adding a note to orders:

~~~sql
ALTER TABLE purchase_order
ADD COLUMN note VARCHAR(500);
~~~

Flyway stores executed migration history in its metadata table. When the application starts, Flyway compares the history with migration files and applies only pending migrations.

If your project uses Liquibase instead of Flyway, describe the same schema using changelogs and changesets. Pick one schema management tool as the source of truth for deployment environments.

## 5. Mapping Customer as an aggregate root

The `Customer` entity maps to the `customer` table. Use a record to represent immutable values:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public record Customer(
    @Id Long id,
    String email,
    @Column("full_name") String fullName,
    @Column("created_at") Instant createdAt
) {
}
~~~

Repository:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
~~~

`Customer` has its own repository because it is an independent aggregate root. Orders store the Customer's ID rather than nesting the `Customer` object inside.

## 6. Mapping PurchaseOrder and OrderItem

Status enum:

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
~~~

Child entity `OrderItem`:

~~~java
import java.math.BigDecimal;

import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("order_item")
public record OrderItem(
    String sku,
    int quantity,
    @Column("unit_price") BigDecimal unitPrice
) {
}
~~~

Aggregate root `PurchaseOrder`:

~~~java
import java.time.Instant;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.jdbc.core.mapping.AggregateReference;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public record PurchaseOrder(

    @Id
    Long id,

    @Column("order_number")
    String orderNumber,

    @Column("customer_id")
    AggregateReference<Customer, Long> customer,

    OrderStatus status,

    @Column("created_at")
    Instant createdAt,

    @Version
    Long version,

    @MappedCollection(
        idColumn = "order_id",
        keyColumn = "line_no"
    )
    List<OrderItem> items
) {
}
~~~

Key mapping points:

- `@Id Long id` maps to the primary key of the order table.
- `AggregateReference<Customer, Long> customer` stores the ID of the Customer aggregate in the `customer_id` column.
- `@Version Long version` enables optimistic locking; a null value marks a new aggregate.
- `@MappedCollection` maps the list of OrderItems to the `order_item` table.
- `idColumn = "order_id"` is the back-reference to the root.
- `keyColumn = "line_no"` stores the index of each element in the List.

`OrderItem` has no separate repository in this example. To add, edit, or remove line items, operate through `PurchaseOrder` to preserve aggregate boundaries.

### Meaning of keyColumn with List

When using a `List`, the key column stores the element's position. If elements are deleted or reordered, positions may shift and Spring Data JDBC may rewrite the child rows according to the new state.

If the business requires stable user-supplied line numbers, you can use a `Map` keyed by line number or design an appropriate child identifier instead of treating the `List` index as a business code.

### Why use AggregateReference?

`AggregateReference<Customer, Long>` expresses that `Customer` is a separate aggregate. When saving `PurchaseOrder`, Spring Data JDBC writes only the customer ID. It does not re-insert `Customer` and does not delete `Customer` when the order is deleted.

This suits a relationship where many orders reference one customer.

## 7. Repositories for the two aggregate roots

Customer repository:

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
~~~

PurchaseOrder repository:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

There is no need to create an `OrderItemRepository` for `PurchaseOrder`'s child entity in this model. One repository per aggregate root is the right organization for Spring Data JDBC.

## 8. Creating Customer and PurchaseOrder in a service

The service checks that the Customer exists, creates a reference, and saves the order aggregate:

~~~java
import java.time.Instant;
import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.data.jdbc.core.mapping.AggregateReference;

@Service
public class OrderApplicationService {

    private final CustomerRepository customers;
    private final PurchaseOrderRepository orders;

    public OrderApplicationService(
            CustomerRepository customers,
            PurchaseOrderRepository orders) {
        this.customers = customers;
        this.orders = orders;
    }

    @Transactional
    public PurchaseOrder placeOrder(
            Long customerId,
            String orderNumber,
            List<OrderItem> items) {

        Customer customer = customers.findById(customerId)
            .orElseThrow(() ->
                new CustomerNotFoundException(customerId)
            );

        PurchaseOrder order = new PurchaseOrder(
            null,
            orderNumber,
            AggregateReference.to(customer.id()),
            OrderStatus.NEW,
            Instant.now(),
            null,
            List.copyOf(items)
        );

        return orders.save(order);
    }
}
~~~

Spring Data JDBC inserts the root first, retrieves the database-generated ID, and then inserts the line items with the corresponding back-reference. A null `version` property indicates a new aggregate; after insert, `version` is initialized.

The service places `@Transactional` so the entire operation belongs to the same transaction. If inserting a line item fails due to a check or unique constraint, the transaction rolls back and does not leave a partially persisted order behind.

### Creating a customer

A customer can be created via its own service method:

~~~java
@Transactional
public Customer registerCustomer(String email, String fullName) {
    Customer customer = new Customer(
        null,
        email,
        fullName,
        Instant.now()
    );

    return customers.save(customer);
}
~~~

If the email already exists, the unique constraint `uq_customer_email` protects the database. The service can validate email format and translate constraint violations into an appropriate business error.

## 9. Testing the schema and mappings

An integration test should verify that the migration created the schema and Spring Data JDBC can save and load the full aggregate.

Example using the full Spring Boot context so Flyway runs migrations on startup:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.data.jdbc.core.mapping.AggregateReference;

@SpringBootTest
@Transactional
class OrderSchemaIntegrationTest {

    @Autowired
    CustomerRepository customers;

    @Autowired
    PurchaseOrderRepository orders;

    @Test
    void persistsCustomerOrderAndItems() {
        Customer customer = customers.save(
            new Customer(
                null,
                "alice@example.com",
                "Alice",
                Instant.now()
            )
        );

        PurchaseOrder saved = orders.save(
            new PurchaseOrder(
                null,
                "ORD-2026-0001",
                AggregateReference.to(customer.id()),
                OrderStatus.NEW,
                Instant.now(),
                null,
                List.of(
                    new OrderItem(
                        "BOOK-01",
                        2,
                        new BigDecimal("12.50")
                    ),
                    new OrderItem(
                        "PEN-02",
                        3,
                        new BigDecimal("1.75")
                    )
                )
            )
        );

        PurchaseOrder loaded = orders.findById(saved.id())
            .orElseThrow();

        assertThat(loaded.items()).hasSize(2);
        assertThat(loaded.customer().getId()).isEqualTo(customer.id());
    }
}
~~~

This example assumes the test datasource is connected to a database capable of running the V1 migration. The test transaction rolls back after each test, so test data does not persist after the test finishes.

### Verifying constraints

Additional tests can be added to confirm:

- Saving two Customers with the same email is rejected.
- Saving two PurchaseOrders with the same order number is rejected.
- Saving an OrderItem with quantity 0 is rejected by the check constraint.
- Inserting a PurchaseOrder with a non-existent customer ID is rejected by the foreign key when going directly to repository/JDBC.
- Deleting a Customer still referenced by a PurchaseOrder is blocked by the database.

When testing unique/FK constraints directly, you can use `JdbcTemplate` to bypass service-layer validation and verify the database constraints themselves.

### Using a production-like database

If production uses PostgreSQL, run critical integration tests against PostgreSQL using Testcontainers or a dedicated test database. H2 may not accurately reflect PostgreSQL data types, DDL syntax, locking, and constraints.

When tests use a container, make sure Spring Data connects to the container and Flyway runs on that database. If a test slice replaces the DataSource with an embedded database by default, configure `@AutoConfigureTestDatabase(replace = Replace.NONE)` to keep the provided test datasource.

## 10. Common errors when building schemas and migrations

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Table not found when repository runs | Migration did not run or file placed in wrong directory | Check Flyway locations and migration history |
| Cannot insert PurchaseOrder | Customer ID does not exist or wrong FK column name | Check Customer before creating reference and verify `customer_id` |
| Cannot insert OrderItem | `order_id` or `line_no` does not match mapping | Align `@MappedCollection` with DDL |
| Duplicate email or order number | Unique constraint violated | Validate business values and translate errors appropriately |
| Cannot delete Customer | Orders still reference the customer | Use soft delete or handle orders per policy |
| Saving Order loses OrderItems | Passed-in object is missing the item list | Load full aggregate and modify via root |
| Line items rewritten when only status changed | Spring Data JDBC resynchronizes the entire child collection | Keep aggregates reasonably sized; consider SQL update for single-column updates |
| Status enum fails to persist | Enum value does not match check constraint | Synchronize Java enum and allowed values in migration |
| Timestamp is null | Entity does not assign a value and INSERT sends null instead of relying on default | Set `Instant` in the application or use an appropriate callback/default |
| Migration checksum mismatch | Edited a migration file that already ran | Create a new migration instead of editing old migrations |
| Tests pass on H2 but fail on PostgreSQL | Dialect or data type differences | Run tests against the target database |

## 11. Order of deploying a new schema change

When adding a field or constraint to Order, OrderItem, or Customer:

1. Identify the new business rule and affected tables/columns.
2. Write a new migration, e.g., `V2__add_order_note.sql`.
3. If the new column is required, consider adding it as nullable/with a default first and then backfilling existing data.
4. Update the Java entity and repository mapping.
5. Update services to supply the new value.
6. Write integration tests against the target database.
7. Run the migration from the old schema and verify existing data remains valid.
8. Deploy in a compatible order if multiple application versions run concurrently.

Example V2 migration adding a note to orders:

~~~sql
ALTER TABLE purchase_order
ADD COLUMN note VARCHAR(500);
~~~

Once the application writes notes for all orders, if the business requires it to be mandatory, a subsequent migration can backfill data and add `NOT NULL`.

Do not immediately add a `NOT NULL` column without a default to a table containing data if the migration does not provide values for existing rows.

## 12. Hands-on exercises

### Exercise 1 — Create the V1 migration

Write `V1__create_customer_order_schema.sql` creating the `Customer`, `PurchaseOrder`, and `OrderItem` tables along with primary keys, foreign keys, unique constraints, and check constraints.

### Exercise 2 — Map Customer

Create the `Customer` entity and `CustomerRepository`. Save a customer and verify email uniqueness with an integration test.

### Exercise 3 — Map PurchaseOrder

Create the `PurchaseOrder` entity with `AggregateReference<Customer, Long>`. Save an order referencing an existing customer.

### Exercise 4 — Map OrderItem

Use `@MappedCollection(idColumn = "order_id", keyColumn = "line_no")` to persist a List of `OrderItem`s. Verify that line item order is preserved by the key column.

### Exercise 5 — Verify foreign keys

Attempt to create a `PurchaseOrder` with a non-existent customer ID directly via JDBC. Confirm the database rejects the insert.

### Exercise 6 — Verify unique constraints

Create two customers with the same email or two orders with the same order number. Confirm the unique constraints prevent duplicate data.

### Exercise 7 — Modify the aggregate

Save an order with two line items, reload it, change the status, and save. Confirm the line items remain intact. Then remove one item from the collection and verify the final state of the child table.

### Exercise 8 — V2 Migration

Add a `note` column to `purchase_order` via a V2 migration. Run the application starting from the V1 schema and confirm Flyway applies V2 in the proper order.

## 13. Official references

- [Spring Data Relational — Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): how to map entities, `@MappedCollection`, `AggregateReference`, and back-references.
- [Spring Data Relational — Domain Driven Design and Relational Databases](https://docs.spring.io/spring-data/relational/reference/jdbc/domain-driven-design.html): aggregate boundaries and how to represent references between aggregates.
- [Spring Data Relational — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): how Spring Data JDBC persists aggregate roots and child entities.
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): how to configure Flyway/Liquibase and schema initialization order.
- [Flyway — Versioned Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/versioned-migrations): how to name, version, and manage applied migrations.

The sample schema separates `Customer` and `PurchaseOrder` into two aggregate roots, while `OrderItem` lives inside the `PurchaseOrder` aggregate. The migration creates primary keys, foreign keys, unique constraints, and check constraints so the database protects invariants. When implementing, keep Java mappings aligned with column names in migrations, reference `Customer` by ID, and manage `OrderItem` through `PurchaseOrder` so Spring Data JDBC properly maintains child data lifecycles.
