# Composite Keys: Checking Version Support and Choosing Alternative Models

A composite primary key is a key made up of two or more columns. For example, a line item in a purchase order can be identified by the pair `(order_id, line_no)`: the line sequence number is meaningful only within a single order, so `line_no` is not unique across the whole table.

Relational database management systems support composite primary keys at the SQL level. However, the ability to create a table with a composite key does not mean every mapping framework can map that key directly as an entity ID. With Spring Data Relational and Spring Data R2DBC, you must check the exact version in use, how that version represents IDs, and which Repository operations are supported.

When direct mapping does not meet your needs, you can keep the composite key in the database while using a surrogate key as the entity ID, combined with `UNIQUE` to enforce business uniqueness. Another option is keeping the composite-key schema and operating via SQL with `DatabaseClient`. Each approach suits different requirements.

## 1. What Is a Composite Key?

A primary key uniquely identifies a row in a table. With a single-column key, one column suffices to identify the row. With a composite key, multiple columns must be combined to identify a row.

For example, an `order_line` table stores the lines of an order:

```sql
CREATE TABLE order_line (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(19, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no),
    FOREIGN KEY (order_id) REFERENCES purchase_order(id),
    FOREIGN KEY (product_id) REFERENCES product(id)
);
```

In this table:

- `order_id` indicates which order the line belongs to.
- `line_no` is the sequence number of the line within that order.
- One order can have lines `1`, `2`, `3`, and another order can have the same line numbers.
- The pair `(order_id, line_no)` must be unique, while each individual column does not need to be unique.

Example data:

| order_id | line_no | product_id | quantity |
|---:|---:|---:|---:|
| 1001 | 1 | 501 | 2 |
| 1001 | 2 | 502 | 1 |
| 1002 | 1 | 501 | 3 |

Two rows with `line_no = 1` are valid because `order_id` differs. However, there cannot be two rows with the same `(order_id = 1001, line_no = 1)`.

Composite keys commonly appear in many-to-many join tables, parent-dependent detail tables, multi-tenant data tables, or business domains with multi-part natural keys.

## 2. Distinguishing Database Support from Spring Data Support

Separate two questions:

1. **Does the database allow defining and enforcing a composite primary key?** Popular relational databases support declaring multiple columns in `PRIMARY KEY`, creating the corresponding unique index, and referencing those columns in foreign keys.
2. **Does the Spring Data Relational version in use map composite keys directly as an entity ID and support the operations you need?** The answer depends on the framework version and how mapping is implemented.

Spring Data R2DBC is not JPA/Hibernate. Never assume that a JPA ID declaration style, such as `@EmbeddedId` or `@IdClass`, will automatically work in Spring Data R2DBC. Each framework's annotations and mapping rules can differ.

Because Spring Data Relational has evolved across multiple release trains, read the documentation and release notes for the exact version resolved in your application. Do not only check the Spring Boot version in `build.gradle` or `pom.xml`: Boot manages multiple Spring Data modules and transitive dependencies, so the actual resolved version may differ from what you guess from a single declaration.

## 3. Checking Support by Version

Before designing an entity that uses a composite key directly, determine the actual version and thoroughly verify the required behavior.

### Step 1 — Identify the Resolved Spring Data Version

If the project uses Gradle, you can inspect the runtime dependency tree:

```bash
./gradlew dependencyInsight \
  --dependency spring-data-relational \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-data-r2dbc \
  --configuration runtimeClasspath
```

If the project uses Maven:

```bash
./mvnw dependency:tree \
  -Dincludes=org.springframework.data:spring-data-relational,org.springframework.data:spring-data-r2dbc
```

Note the versions of `spring-data-relational`, `spring-data-r2dbc`, and the Spring Boot BOM managing them. If multiple versions are pulled in, identify the final version on the runtime classpath and why that version was chosen.

### Step 2 — Read Documentation for the Exact Release Train

Consult the Spring Data Relational reference documentation for the exact resolved version, especially sections describing entity identifiers, mapping metadata, persistence, and Repositories. Read release notes or migration guides when features are added or changed across versions.

Do not use the `current` branch documentation to draw conclusions for a project running an older version. An example in the latest documentation might rely on APIs that do not exist in your project's release train.

### Step 3 — Verify the Entire Entity Lifecycle

Even if the documentation states composite IDs are supported, still test the operations your application actually uses:

- Mapping each ID component to the right table columns.
- Reading an entity by composite ID and passing the right ID type to `findById`.
- Inserting a new entity with a pre-assigned ID.
- Distinguishing a new entity from an existing entity when calling `save`.
- Updating and deleting using all components of the key.
- Mapping foreign keys that reference a composite key, if the schema includes such cases.
- Behavior of optimistic locking, auditing, and custom conversions if used by the application.
- Handling of null values, varied data types, and column naming rules.

A feature might support reading by composite key while still having limitations around generated IDs, entity state detection, or a specific Repository operation. Therefore, verifying that the code compiles is not enough.

### Step 4 — Write Integration Tests Against the Real Driver

Create a test table with a composite key in the exact database engine and driver used by your project. Test insert, read, update, delete, duplicate keys, and transactions. If you only test on H2 while production runs PostgreSQL or SQL Server, add tests on the corresponding production database because data types, SQL, and drivers can differ.

## 4. Considerations When Choosing Composite Keys

Composite keys are suitable when all key components together form a natural, stable, meaningful identifier in the data domain.

Suitable examples:

- `order_id + line_no`: line numbers are unique only within a single order.
- `tenant_id + external_code`: codes issued by an external system that are unique only per tenant.
- `student_id + course_id`: a student has only one enrollment record per course in a term, if business rules define it that way.
- `country_code + local_number`: phone numbers identified by country code and local number, if that is the chosen identification rule.

Composite keys offer several benefits:

- Express uniqueness rules directly in the database.
- Avoid adding an artificial ID column when natural components are sufficiently stable.
- Clarify identification scope, such as a code unique only within a tenant or parent aggregate.
- Convenient for join tables where the foreign-key pair itself identifies the row.

However, there are also costs:

- Every identifying query must carry all key components.
- Foreign keys from other tables must include all columns of the composite key.
- Indexes and joins can be larger when keys span multiple columns or wide columns.
- If any key component changes, updates become complex and can ripple to referencing tables.
- Some frameworks, caching libraries, APIs, or mapping tools handle composite IDs less smoothly than single IDs.

Do not use mutable fields such as display name, email, or status as primary key components merely because they currently appear unique. A primary key should remain stable over the row's lifetime.

## 5. Common Alternative Model: Surrogate Key and Unique Constraint

When Spring Data R2DBC or an integration library needs a simple ID, a common alternative is adding a surrogate key, typically a `BIGINT` identity or UUID. Business uniqueness rules are preserved via `UNIQUE(order_id, line_no)`.

Schema:

```sql
CREATE TABLE order_line (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_order(id),
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL REFERENCES product(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(19, 2) NOT NULL CHECK (unit_price >= 0),
    CONSTRAINT uq_order_line_order_line_no UNIQUE (order_id, line_no)
);
```

Here there are two identifiers with different purposes:

- `id` is a single technical key used to identify the entity in the application and serve as the ID for the Spring Data Repository.
- `(order_id, line_no)` is the business unique key, ensuring an order cannot have two lines with the same sequence number.

The unique constraint is enforced by the database, so it still protects data under concurrent requests. Checking beforehand in Java with `existsByOrderIdAndLineNo(...)` is not sufficient to guarantee uniqueness: two transactions can both observe absence and then both insert. Database constraints remain the final safeguard; the application should handle unique constraint violations appropriately.

### Entity with a Single ID

Example entity using the surrogate-key model:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("order_line")
public record OrderLine(
    @Id Long id,
    Long orderId,
    Integer lineNo,
    Long productId,
    Integer quantity,
    BigDecimal unitPrice
) {}
```

The repository can use the single ID for CRUD operations while still querying by business key:

```java
public interface OrderLineRepository
        extends ReactiveCrudRepository<OrderLine, Long> {

    Mono<OrderLine> findByOrderIdAndLineNo(Long orderId, Integer lineNo);

    Flux<OrderLine> findByOrderIdOrderByLineNo(Long orderId);
}
```

Derived query method names use entity properties, not necessarily SQL column names. The mapping context translates `orderId` and `lineNo` to their corresponding columns by convention or mapping annotations.

This model usually integrates smoothly with `ReactiveCrudRepository`, `R2dbcEntityTemplate`, APIs taking a single ID, and third-party libraries. In exchange, the database gains an extra key column and a unique index for the business rule.

## 6. Using Composite Keys in SQL Queries via DatabaseClient

If an existing schema must retain a composite primary key, the application can still operate with explicit SQL. `DatabaseClient` supports binding each component of the key and mapping results into DTOs or domain objects.

Example finding one line item:

```java
public Mono<OrderLineView> findLine(Long orderId, Integer lineNo) {
    return databaseClient.sql("""
            SELECT order_id, line_no, product_id, quantity, unit_price
            FROM order_line
            WHERE order_id = :orderId
              AND line_no = :lineNo
            """)
        .bind("orderId", orderId)
        .bind("lineNo", lineNo)
        .map((row, metadata) -> new OrderLineView(
            row.get("order_id", Long.class),
            row.get("line_no", Integer.class),
            row.get("product_id", Long.class),
            row.get("quantity", Integer.class),
            row.get("unit_price", BigDecimal.class)
        ))
        .one();
}
```

Updates and deletes must also include all key components:

```java
public Mono<Long> updateQuantity(
        Long orderId,
        Integer lineNo,
        Integer quantity) {

    return databaseClient.sql("""
            UPDATE order_line
            SET quantity = :quantity
            WHERE order_id = :orderId
              AND line_no = :lineNo
            """)
        .bind("quantity", quantity)
        .bind("orderId", orderId)
        .bind("lineNo", lineNo)
        .fetch()
        .rowsUpdated();
}

public Mono<Long> deleteLine(Long orderId, Integer lineNo) {
    return databaseClient.sql("""
            DELETE FROM order_line
            WHERE order_id = :orderId
              AND line_no = :lineNo
            """)
        .bind("orderId", orderId)
        .bind("lineNo", lineNo)
        .fetch()
        .rowsUpdated();
}
```

With this approach, you can map results into projections without requiring a Repository to model a composite ID. However, the data access layer must manage SQL, parameter binding, mapping, and required operations itself. Always bind parameters for input values; never concatenate user input into SQL strings.

## 7. Keeping Composite Keys in the Database While Modeling Business Keys as Value Objects

Even when the entity uses a surrogate ID, the business key pair can still be modeled as a dedicated Java type to avoid passing separate scattered parameters and to express domain semantics.

```java
public record OrderLineKey(Long orderId, Integer lineNo) {}
```

The service can accept an `OrderLineKey`:

```java
public Mono<OrderLine> findLine(OrderLineKey key) {
    return repository.findByOrderIdAndLineNo(key.orderId(), key.lineNo());
}
```

This value object does not have to be a primary key mapped by Spring Data. It simply groups the business key components in code. The entity still uses the single `id` as `@Id`, while the database enforces a unique constraint on the key pair.

If your Spring Data Relational version supports mapping a value object or embedded object across multiple columns, you can consider using that feature for composite data fields. However, mapping multiple columns into a property does not by itself prove that property is supported as a primary key. Both capabilities must be verified separately against your version's documentation.

## 8. When to Choose Each Model

| Scenario | Suitable Option | Reason |
|---|---|---|
| Spring Data version confirmed to support composite IDs and full lifecycle tested | Direct composite ID | Keeps the entity model aligned with the database primary key |
| Need simple Repository CRUD or compatibility with other libraries | Surrogate key + unique constraint | Single ID is easy to pass, cache, and integrate |
| Legacy schema mandates keeping composite PK, specialized queries | `DatabaseClient` with all key components | Preserves schema and provides direct SQL control |
| Need to group multiple key components in business APIs | Business-key value object | Reduces parameter-order mistakes and expresses semantics |
| Simple join table used only in a few queries | Composite PK in database and specialized queries | Avoids forcing every table into a Repository aggregate |

No single choice is optimal for every system. Weigh the number of referencing tables, mutability of key components, required API shape, compatibility needs, and operational complexity.

## 9. Risks When Using Composite Keys

### Key Components Changing

Primary keys should remain stable. If `line_no` is part of the key, renumbering lines can equate to deleting an old identity and creating a new one. If other tables reference `(order_id, line_no)`, this also impacts foreign keys. If sequence numbers are only for display and may change, consider using a single ID as the primary key and applying unique constraints per business rules.

### Foreign Keys Must Carry All Components

If another table references `order_line`, its foreign key must include every column of the composite primary key. This makes schemas and joins more complex when keys have many parts. When multiple tables reference the same row, a surrogate key can simplify relationships.

### Column Order in Indexes

Composite indexes are column-ordered. An index on `(order_id, line_no)` generally suits filters on `order_id` or both columns, but is not necessarily optimal for queries filtering only on `line_no`. If other access patterns exist, add secondary indexes based on actual workloads.

### ID Generation and New-Entity Detection

Composite keys are usually assigned by the application from business data rather than generated as a single value by the database. Therefore, verify how Spring Data determines whether an entity is new or existing when the ID already has a value before `save` is called. Depending on how the framework detects state from IDs or another strategy, new entities with pre-assigned IDs may need an appropriate newness mechanism for your version. Never assume `save` always executes `INSERT` just because the object was newly instantiated in Java.

With a surrogate-key model using identity, the ID can be left `null` before inserting; this is the common flow cleanly supported by Spring Data. Business rules remain protected by the unique constraint.

### Duplicate Key Errors Under Concurrent Requests

Pre-checking existence before insert cannot replace a unique constraint. Two concurrent requests can both pass the check. Let the database enforce uniqueness and map constraint-violation errors into appropriate business responses, such as reporting that the line item already exists.

## 10. Migrating from a Composite Primary Key to a Surrogate Key

In a running system, do not swap keys simply by adding an ID column and immediately dropping the old primary key. Plan the migration around referencing tables and deployment flows.

A general sequence might look like:

1. Add the surrogate ID column with an appropriate value-generation strategy.
2. Backfill IDs for all existing rows and ensure there are no duplicates or nulls.
3. Create a unique constraint on the old business key columns, e.g., `(order_id, line_no)`.
4. Create new indexes and referencing columns on child tables that reference the composite key.
5. Update the application to read/write using the new ID while retaining business-key queries as needed.
6. Migrate referencing data and verify row counts, orphans, duplicates, and consistency.
7. Switch foreign keys to the new ID once all applications use the new column.
8. Drop the old primary key only when no consumers depend on it and a rollback plan is in place.

The exact sequence depends on the database, table size, zero-downtime requirements, and release process. For large tables, consider online/concurrent index creation if supported and batch the backfill to avoid long table locks.

## 11. Testing Composite Keys and Alternative Models

An integration test suite should verify the following cases on the target database:

- Two rows sharing the first key component but differing on the second are allowed to be saved.
- Two rows duplicating the entire key are rejected by the database.
- Querying with all key components returns exactly one row.
- Querying without one component does not accidentally return multiple rows when the code expects one.
- Update and delete affect only the target row.
- Foreign keys referencing the composite key accept valid pairs and reject invalid ones.
- `save` distinguishes insert and update accurately under the ID strategy of your Spring Data version.
- Transactions roll back when a write operation within the aggregate fails.
- All ID data types bind and map accurately via the production driver.

With the surrogate-key model, also verify that the unique constraint still prevents duplicate business-key pairs even when two requests run concurrently. Test Repository CRUD by single ID and derived queries by business-key components.

## 12. Complete Example: Choosing a Surrogate Key for Order Lines

Suppose the application requires these operations:

- Load all line items by `order_id`, ordered by `line_no`.
- Find a single line by `(order_id, line_no)`.
- Update the quantity of one line.
- Other modules occasionally need to reference a line item by ID.

A surrogate-key model satisfies those requirements:

```sql
CREATE TABLE order_line (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_order(id),
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL REFERENCES product(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(19, 2) NOT NULL CHECK (unit_price >= 0),
    CONSTRAINT uq_order_line_order_line_no UNIQUE (order_id, line_no)
);

CREATE INDEX idx_order_line_order_line_no
    ON order_line (order_id, line_no);
```

Entity and repository:

```java
@Table("order_line")
public record OrderLine(
    @Id Long id,
    Long orderId,
    Integer lineNo,
    Long productId,
    Integer quantity,
    BigDecimal unitPrice
) {}

public interface OrderLineRepository
        extends ReactiveCrudRepository<OrderLine, Long> {

    Flux<OrderLine> findByOrderIdOrderByLineNo(Long orderId);

    Mono<OrderLine> findByOrderIdAndLineNo(Long orderId, Integer lineNo);
}
```

The business layer can use a meaningful identifier type:

```java
public record OrderLineKey(Long orderId, Integer lineNo) {}

public Mono<OrderLine> getLine(OrderLineKey key) {
    return orderLineRepository.findByOrderIdAndLineNo(
        key.orderId(),
        key.lineNo()
    );
}
```

In this example, `id` lets the Repository use standard CRUD; `OrderLineKey` lets business code express the natural identifier; the unique constraint preserves the database rule. If a line number changes later, the application must clarify whether that is a business-attribute update or an identity change. With a surrogate ID, changing `line_no` does not change the row's technical ID.

## 13. Decision Workflow

When encountering a table with a composite primary key, you can follow this sequence:

**Step 1 — Identify why the composite key exists.** Are the columns a stable natural identifier, or merely a business uniqueness rule?

**Step 2 — Determine the actual framework version.** Use dependency insight or dependency tree to find the resolved versions of Spring Data Relational and Spring Data R2DBC.

**Step 3 — Read version-specific documentation.** Verify composite ID mapping, ID types, Repository APIs, and related limitations.

**Step 4 — Identify required APIs.** Does the application need `findById`, `save`, `deleteById`, or only SQL queries by column tuple?

**Step 5 — Compare options.** Weigh direct composite ID, surrogate ID plus unique constraint, or custom SQL via `DatabaseClient`.

**Step 6 — Write integration tests.** Verify insert/read/update/delete, duplicate keys, entity newness, transactions, and the real driver.

**Step 7 — Document the decision.** State the rationale for the chosen model, verified versions, constraints to preserve, and limitations to monitor during framework upgrades.

## 14. Conclusion

Composite keys are a relational feature at the database level, whereas mapping them to entity IDs in Spring Data Relational is a version- and API-dependent concern. Check actual dependencies, documentation for the exact release train, and the full Repository lifecycle before choosing direct composite IDs.

If you need a simple ID and predictable CRUD integration, a surrogate key combined with a unique constraint is often the pragmatic choice: the database still protects the business key, while Spring Data uses a single ID to manage the entity. When a schema must preserve a composite key or queries are specialized, `DatabaseClient` lets you bind all key components and map results as needed. Base the decision on access patterns, key stability, compatibility requirements, and integration tests against the right driver and database.
