# Configuring @SequenceGenerator and Key Value Allocation in Spring Data JPA

## 1. What Is a Sequence-Generated Primary Key?

In a relational database, a primary key uniquely identifies a row. Java applications typically map that primary key to an entity property, such as `Long id`.

Several database management systems support **sequences**: an independent database object capable of issuing numeric values in ascending order. A sequence can be queried for its next value without first inserting a row into a table. Multiple tables can even share a single sequence if the design calls for it.

JPA supports sequences via `GenerationType.SEQUENCE` and the `@SequenceGenerator` annotation. In Spring Data JPA, this configuration lives on the entity; repositories continue to work normally. When saving a new entity, Spring Data JPA delegates the operation to the JPA `EntityManager`, and the JPA provider (for example Hibernate) obtains key values according to the mapping configuration.

It is important to distinguish:

- **The generator name in Java**: the logical name referenced by `@GeneratedValue`.
- **The sequence name in the database**: the actual database sequence object called by the provider.
- **The allocated key value**: the number returned by the sequence or allocated by the provider from a pre-fetched range.

These three concepts are related, though they do not necessarily share the same name or operate identically.

## 2. Role of @SequenceGenerator and @GeneratedValue

`@SequenceGenerator` declares the configuration for a sequence generator. `@GeneratedValue` states that the primary key property will be auto-generated and specifies which generator to use.

Minimal example:

~~~java
@Entity
@SequenceGenerator(
    name = "customer_seq_gen",
    sequenceName = "customer_seq",
    allocationSize = 1
)
public class Customer {
    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "customer_seq_gen"
    )
    private Long id;
}
~~~

In this example:

- `name = "customer_seq_gen"` is the logical generator name in JPA metadata.
- `sequenceName = "customer_seq"` is the physical sequence name in the database.
- `strategy = GenerationType.SEQUENCE` instructs JPA to use a sequence.
- `generator = "customer_seq_gen"` links `@GeneratedValue` to the declared generator.
- `allocationSize = 1` requests allocation one value at a time.

If `generator` is omitted from `@GeneratedValue`, the provider may select a default generator instead of the one just declared. Therefore, when using a specific sequence, both annotations must reference the exact same name.

### Important Attributes of @SequenceGenerator

| Attribute | Meaning | Default Value |
|---|---|---|
| `name` | Logical generator name referenced by `@GeneratedValue`; required attribute | None |
| `sequenceName` | Sequence name in the database | Provider-chosen default name |
| `allocationSize` | Number of values the provider expects to allocate per sequence fetch | `50` |
| `initialValue` | Starting value when the sequence is created by schema generation | `1` |
| `schema` | Schema containing the sequence | Default schema |
| `catalog` | Catalog containing the sequence | Default catalog |

The generator `name` must be unique within the persistence unit. Avoid declaring multiple different generators with the same name because the provider may not know which configuration to apply.

`@SequenceGenerator` can be placed on the entity class or on the key property. Placing it at the class level often helps readers see the ID configuration right near the entity declaration. Wherever the generator is declared, use that exact logical name in `@GeneratedValue`.

## 3. Complete Entity and Repository Example

Suppose an application manages purchase orders. The `PurchaseOrder` entity has a primary key `id` generated from the `purchase_order_seq` sequence.

~~~java
package com.example.shop.order.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_order")
@SequenceGenerator(
    name = "purchase_order_seq_gen",
    sequenceName = "purchase_order_seq",
    initialValue = 1,
    allocationSize = 50
)
public class PurchaseOrder {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "purchase_order_seq_gen"
    )
    private Long id;

    private String description;

    protected PurchaseOrder() {
        // No-arg constructor required by JPA.
    }

    public PurchaseOrder(String description) {
        this.description = description;
    }

    public Long getId() {
        return id;
    }

    public String getDescription() {
        return description;
    }
}
~~~

The repository does not need custom key generation logic:

~~~java
package com.example.shop.order.persistence;

import com.example.shop.order.domain.PurchaseOrder;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}
~~~

`JpaRepository<PurchaseOrder, Long>` indicates that the managed entity is `PurchaseOrder` and the primary key type is `Long`. When calling `save`, Spring Data JPA uses the JPA mapping on the entity to store the record. You do not need to query the sequence manually in the service or write a custom repository implementation just to obtain IDs.

Example usage in a service:

~~~java
@Service
public class PurchaseOrderService {
    private final PurchaseOrderRepository repository;

    public PurchaseOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Long create(String description) {
        PurchaseOrder order = new PurchaseOrder(description);
        PurchaseOrder saved = repository.save(order);
        return saved.getId();
    }
}
~~~

These snippets belong to a Spring Boot application with the Spring Data JPA dependency and an appropriate datasource configuration, not a standalone Java program compilable solely with `javac`. The example uses the `jakarta.persistence` namespace of Spring Boot 3+. Older Spring Boot 2 projects typically use `javax.persistence`; do not mix the two namespaces within the same application.

## 4. Configuring the Sequence in the Database

Annotations describe mapping metadata for JPA, but the actual sequence remains a database object. When using migrations or managing schemas manually, you must create a sequence matching the entity configuration.

For the `allocationSize = 50` example, an illustrative PostgreSQL DDL when using Hibernate with a pooled optimizer might look like:

~~~sql
CREATE SEQUENCE purchase_order_seq
    START WITH 1
    INCREMENT BY 50;

CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY,
    description VARCHAR(255)
);
~~~

In common Hibernate pooled configurations, `allocationSize` and the physical increment of the sequence must be compatible. With `allocationSize = 50`, Hibernate typically expects the sequence to increment by 50 so each fetched value represents an allocated range of IDs. If the database sequence increments by 1 while the mapping and optimizer expect 50, Hibernate may report an increment mismatch error at startup or during schema validation.

If you choose `allocationSize = 1`, the corresponding DDL usually uses an increment of 1:

~~~java
@SequenceGenerator(
    name = "purchase_order_seq_gen",
    sequenceName = "purchase_order_seq",
    initialValue = 1,
    allocationSize = 1
)
~~~

~~~sql
CREATE SEQUENCE purchase_order_seq
    START WITH 1
    INCREMENT BY 1;
~~~

**Note:** how Hibernate uses a sequence also depends on the optimizer and provider configuration. JPA defines the meaning of `allocationSize`, whereas how the provider pre-fetches and consumes ID ranges is an implementation detail. Always consult the documentation for your exact Hibernate/provider version and corresponding schema configuration; do not apply one optimizer's DDL blindly to every provider.

In production environments, manage sequences using migrations such as Flyway or Liquibase. Never assume that changing an annotation will automatically modify an existing sequence in the database.

## 5. How Does allocationSize Work?

`allocationSize` is an important parameter controlling how often the application must call the database to obtain sequence values.

### allocationSize = 1

With `allocationSize = 1`, the provider fetches one sequence value for each new ID needed. This approach is easy to understand and generally suitable when simple configuration is desired or when the sequence increments by 1.

Advantages:

- Mapping and DDL are easy to reconcile.
- Every ID allocation takes a value directly from the sequence.
- Less need to reason about pre-allocated ID ranges.

Limitations:

- Higher frequency of database calls to fetch sequence values when inserting many records.
- Can increase round trips and hurt throughput if writes occur frequently.

### allocationSize Greater Than 1

With `allocationSize = 50`, the provider can pre-fetch a group of values from the sequence and then assign IDs from that group to new entities without calling the database for every entity.

Conceptually, the flow can be visualized as:

~~~text
Application needs an ID
      |
      v
Provider asks database for a sequence value
      |
      v
Provider receives ID range information
      |
      v
Subsequent entities use IDs from the allocated range
      |
      v
When the range is exhausted, provider fetches the next range
~~~

The main benefit is reducing the number of sequence calls to the database. This can help when the application writes many entities and round-trip latency is significant.

In exchange:

- Gaps can appear in the ID series when the application restarts before exhausting an allocated range.
- A transaction rollback does not return already-fetched sequence values.
- Multiple application instances may hold different ID ranges, so observed IDs do not necessarily increase strictly in insert order.
- Configuration must stay consistent across instances and between the mapping and the physical sequence.

For instance, an application pre-allocates a range of 50 IDs, uses only part of it, and then shuts down. The remaining values may never be used again. This is normal behavior of a pre-allocation strategy, not a data loss bug.

### What allocationSize Should You Choose?

There is no single optimal number for every system. You can start with:

- `1` if you want direct, predictable configuration and write traffic is low.
- A value such as `50` if the provider uses a matching pooling strategy and the application performs many inserts.
- A larger value only when benchmarks show that reducing round trips yields measurable gains and the operations team understands the consequences of pre-allocation.

Do not pick a large number merely assuming IDs will be generated faster. Benchmark performance with real write workloads, check the provider's optimizer, and keep sequence DDL synchronized.

## 6. What Does initialValue Do?

`initialValue` declares the starting value of the sequence when the schema is created by a tool/provider supporting DDL generation. The default value is `1`.

Example:

~~~java
@SequenceGenerator(
    name = "invoice_seq_gen",
    sequenceName = "invoice_seq",
    initialValue = 1000,
    allocationSize = 1
)
~~~

When the provider creates a new sequence from this metadata, the sequence is configured to start at 1000 as supported by the provider and database.

Crucially, `initialValue` should not be treated as an instruction to reset an existing sequence automatically. If the database already has the sequence, updating the annotation does not guarantee the existing sequence will be reset. When managing schemas with migrations, update the DDL or migration explicitly.

When adding a sequence to a table that already contains data, ensure the next sequence value does not collide with existing primary keys. Synchronizing the sequence with `MAX(id)` must be done via a migration statement appropriate for your database, optimizer, and `allocationSize`.

Simple PostgreSQL example for the `allocationSize = 1` case:

~~~sql
SELECT setval(
    'purchase_order_seq',
    COALESCE((SELECT MAX(id) FROM purchase_order), 0) + 1,
    false
);
~~~

With the `false` parameter, the next `nextval` call returns the exact value set. This statement is specific to PostgreSQL and sequences incrementing by 1; do not copy it verbatim to other databases or to pooled configurations with larger increments.

## 7. Relationship Between @SequenceGenerator, Database Sequence, and Hibernate

There are three layers to understand:

1. **JPA mapping:** `@GeneratedValue` and `@SequenceGenerator` describe the strategy and generator metadata for the entity.
2. **JPA provider:** Hibernate or another provider reads the mapping, decides when to call the sequence, and allocates IDs according to its optimizer.
3. **Database:** the physical sequence stores state and issues values according to the DBMS syntax and rules.

Consequently, an error occurring in one layer cannot always be fixed simply by changing an annotation in another layer.

With Hibernate, common optimizers may use sequences in pooled or pooled-lo modes. Range calculation, interpretation of database-returned values, and increment requirements can differ. Avoid assuming `allocationSize` always means the database returns a simple ID and the application adds 1 per entity; details depend on the optimizer.

If multiple services or multiple instances write to the same table, all writers using the sequence must agree on the sequence name, increment, and allocation strategy. If one application configures `allocationSize = 50` and another configures `allocationSize = 1` against the same sequence, conflicts or validation errors can occur depending on the provider and optimizer.

## 8. Comparing SEQUENCE with IDENTITY and AUTO

| Strategy | How ID Is Issued | Characteristics |
|---|---|---|
| `SEQUENCE` | Fetches value from an independent database sequence | Can fetch IDs before insert and allocate in batches; requires database sequence support |
| `IDENTITY` | Database generates ID when inserting the row | Usually requires executing the insert to know the ID; can restrict some insert batching approaches |
| `AUTO` | Provider selects a strategy suited to the ID type and database | Less detail to specify, but actual strategy depends on provider/database |

`SEQUENCE` is often useful when the database supports sequences and the application wants to leverage pre-allocation. `IDENTITY` fits database auto-increment columns. `AUTO` is convenient when letting the provider decide, though if operations require an explicit strategy, declare it directly.

Do not pick `SEQUENCE` just because it seems more modern. Base your decision on database capabilities, performance needs, how migrations manage schemas, and the characteristics of your provider.

## 9. Common Errors

### 9.1. Sequence Not Found

The database may report that the sequence does not exist, for example PostgreSQL reporting that the sequence relation does not exist.

Common causes:

- `sequenceName` does not match the real sequence name.
- The sequence resides in a different schema, but the mapping does not declare `schema`.
- The migration created the table but forgot to create the sequence.
- The connection user lacks permission to use the sequence.

Resolution: check the name, schema, migrations, and database privileges. Do not change the `generator` name to fix a physical sequence name error; those two names belong to different layers.

### 9.2. Increment Size Mismatch

Hibernate may report that the sequence increment in the database does not match the increment size in the mapping. For example, the mapping sets `allocationSize = 50`, while the physical sequence increments by 1 and the active optimizer expects an increment of 50.

Resolution:

1. Check `allocationSize` on the entity.
2. Inspect the sequence DDL or metadata in the database.
3. Check the active Hibernate optimizer and configuration.
4. Pick a compatible configuration and update the migration/schema.
5. Restart the application and verify schema validation.

Do not disable schema validation merely to hide a mismatch error without understanding the risk of ID allocation collisions.

### 9.3. Duplicate Primary Key After Adding a Sequence to an Existing Table

If a sequence starts at a value less than or equal to an ID already present in the table, new inserts may violate the unique or primary key constraint.

The fix is to synchronize the sequence state with existing data using an appropriate migration. Account for `allocationSize`, the optimizer, sequence increment, and whether multiple instances are running. Adjusting the sequence must be scheduled safely so concurrent allocations do not occur during the change.

### 9.4. Mismatched generator Name

For example, declaring:

~~~java
@SequenceGenerator(
    name = "order_seq_gen",
    sequenceName = "order_seq"
)
~~~

yet referencing:

~~~java
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "orders_seq_gen"
)
~~~

The two strings `order_seq_gen` and `orders_seq_gen` differ. Ensure `generator` in `@GeneratedValue` matches `name` in `@SequenceGenerator` exactly.

### 9.5. Database Does Not Support Sequences

Not every database management system supports sequences in the same way. If the database does not support them or the dialect/provider does not implement this strategy, consider `IDENTITY`, `AUTO`, or a strategy suitable for your DBMS.

## 10. Practical Configuration and Verification Workflow

When adding a sequence to an entity, follow this order:

1. Choose a clear sequence name, e.g., `purchase_order_seq`.
2. Declare `@SequenceGenerator` with a unique logical name within the persistence unit.
3. Declare `@GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "...")` and verify the referenced name matches exactly.
4. Choose `allocationSize` based on provider, optimizer, and write load.
5. Create or update the sequence in migrations with a compatible increment.
6. If the table already holds data, synchronize the sequence value to avoid duplicate IDs.
7. Start the application with appropriate schema validation to catch mapping mismatches.
8. Save a test entity via the repository and verify the assigned ID.
9. Test multiple saves, rollbacks, and restarts to confirm that ID gaps are normal allocation behavior.
10. With multiple instances, verify they share the generator and sequence configuration consistently.

You do not need to write code calling `nextval` in services for normal CRUD flows. Let the JPA provider manage the generator via mapping unless the application has a special requirement to access the sequence directly.

## 11. Key Takeaways

- `@SequenceGenerator.name` is the logical generator name in JPA.
- `sequenceName` is the actual sequence name in the database.
- `@GeneratedValue(generator = "...")` must reference `name` accurately.
- `allocationSize` defaults to `50`; it affects how the provider allocates IDs and how often it queries the sequence.
- `initialValue` defaults to `1`, primarily meaningful when creating a new sequence from metadata.
- The physical sequence and the provider's optimizer configuration must be compatible.
- IDs do not have to be continuous; gaps from rollbacks, pre-allocation, or restarts are normal.
- With Spring Data JPA, declaring the mapping on the entity is sufficient for the repository to use the key generation strategy; there is no need to write ID allocation logic in the repository.

Understanding the relationship among JPA mapping, Hibernate optimizers, and database sequences helps you configure `@SequenceGenerator` accurately, avoid increment mismatch errors, and ensure application instances allocate keys safely.
