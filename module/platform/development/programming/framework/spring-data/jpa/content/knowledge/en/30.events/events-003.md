# Impact of IDENTITY and SEQUENCE on Batching Capability

## 1. JDBC batching in Spring Data JPA

When saving many entities, an application can generate hundreds or thousands of INSERT statements. Sending each statement individually can add JDBC call overhead and round-trip communication between the application and the database. **JDBC batching** groups multiple executions of the same prepared statement into a batch and sends them to the database together.

For example, instead of sending 100 individual INSERTs for 100 orders sequentially, Hibernate can prepare a single INSERT template, bind parameter sets for each order, and invoke JDBC batching. The database still processes records per INSERT statement; batching primarily reduces round trips and JDBC call overhead rather than turning them into a single SQL statement.

In Spring Data JPA, Hibernate is typically the JPA provider. Hibernate manages entities in the persistence context and emits SQL on flush. The ability to group INSERTs into a JDBC batch depends on:

- Hibernate's batch size configuration.
- The entity's identifier (primary key) generation strategy.
- Whether SQL statements share the same shape to be grouped into the same batch.
- Flush timing, transaction boundaries, and JDBC driver behavior.
- Database configuration, dialect, and Hibernate version.

The JPA specification does not require every provider to implement JDBC batching in the same way. The explanation below focuses on Hibernate, which is the common provider in Spring Data JPA applications.

## 2. How does IDENTITY work?

With the IDENTITY strategy, the database generates the primary key when executing the INSERT. The application does not know the ID value before the INSERT statement runs.

Example entity using an auto-increment column:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String customerName;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String customerName) {
        this.customerName = customerName;
    }
}
~~~

Database engines can implement this via identity or auto-increment columns, such as MySQL AUTO_INCREMENT or SQL Server IDENTITY.

### 2.1. Why does IDENTITY hinder insert batching in Hibernate?

After an INSERT, Hibernate needs to know the database-generated ID to identify the entity in the persistence context, manage associations, and handle subsequent operations. With IDENTITY, this value is available only after the database executes the INSERT and returns the generated key.

Because it must obtain the ID from the database, Hibernate generally must execute INSERTs individually for entities using IDENTITY. Hibernate therefore **disables JDBC insert batching for entities using the identity identifier generator**. Even when a batch size greater than 0 is configured, INSERTs for this group of entities are not combined into a JDBC insert batch.

Practical consequences:

- Calling save() multiple times or saveAll() does not automatically turn IDENTITY INSERTs into a JDBC batch.
- Increasing hibernate.jdbc.batch_size does not overcome Hibernate's IDENTITY insert batching limitation.
- UPDATE and DELETE operations can still be batched if other batching conditions are met.
- Other entities using SEQUENCE can still be batch-inserted within the same application.

This is a limitation of Hibernate's IDENTITY execution path, not a rule that every SQL operation in the transaction loses batching. Other JPA providers may have different implementations, so check the documentation for the provider you use.

### 2.2. When is IDENTITY still reasonable?

IDENTITY is simple, easy to configure, and suitable when the database standardizes ID generation with auto-increment columns, insert volume is modest, or insert performance is not a bottleneck. It also fits when compatibility with an existing schema matters more than insert batching.

Do not switch strategies solely on the assumption that sequences are always faster. Measure actual workloads, evaluate the target database, and consider whether batching brings meaningful benefits.

## 3. How does SEQUENCE work?

With the SEQUENCE strategy, Hibernate obtains values from a database sequence before inserting the entity. Because the ID is already known before sending the INSERT, Hibernate can queue multiple entities in the persistence context and group their corresponding INSERTs into a JDBC batch on flush.

Example declaring a sequence generator:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;

@Entity
public class PurchaseOrder {
    @Id
    @SequenceGenerator(
        name = "purchase_order_seq_gen",
        sequenceName = "purchase_order_seq",
        allocationSize = 50
    )
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "purchase_order_seq_gen"
    )
    private Long id;

    private String customerName;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String customerName) {
        this.customerName = customerName;
    }
}
~~~

In the example, purchase_order_seq_gen is the generator name referenced in the JPA mapping; purchase_order_seq is the sequence name in the database. allocationSize is the number of identifiers the provider can allocate under its allocation/optimizer mechanism. The default value of allocationSize in JPA is 50 if unspecified.

### 3.1. Why does SEQUENCE allow batching?

Overview process:

1. Hibernate pre-fetches one or more IDs from the sequence.
2. Entities are assigned IDs and managed in the persistence context.
3. On flush, Hibernate generates INSERTs with the same SQL shape.
4. Eligible INSERTs are grouped into batches according to JDBC configuration.
5. The JDBC driver sends the batch to the database.

Hibernate does not need to wait for the INSERT to complete to learn the entity's ID. This is the key difference that makes SEQUENCE favorable for insert batching.

If allocationSize is 1, the provider may need to fetch sequence values more frequently. Even so, knowing the ID before the INSERT still allows grouping INSERTs; allocationSize and JDBC batch size are two independent settings.

### 3.2. allocationSize is not batch size

Two parameters are often confused:

| Parameter | Function |
|---|---|
| allocationSize | Number of IDs allocated per the JPA provider's sequence allocation mechanism. |
| hibernate.jdbc.batch_size | Maximum number of JDBC statements Hibernate attempts to group into one batch. |

For instance, setting allocationSize to 50 and batch_size to 50 does not mean the two features are the same. One parameter controls ID allocation; the other controls the number of JDBC statements in a batch.

Hibernate can use a sequence optimizer to allocate a block of IDs, reducing sequence calls. Make sure the physical database sequence configuration matches the allocationSize and optimizer used by your Hibernate version. If creating sequences manually via DDL, verify the INCREMENT BY value and mapping configuration against provider guidelines; do not alter the increment arbitrarily without checking.

Sequence allocation can leave gaps in ID values due to rollbacks, pre-allocated unused blocks, database caches, or mid-run application shutdowns. Auto-generated IDs are not contiguous business sequence numbers and should not be relied upon to guarantee gapless numbering.

## 4. Comparing IDENTITY and SEQUENCE for batching

| Criterion | IDENTITY | SEQUENCE |
|---|---|---|
| When ID is available | After the database executes INSERT | Before INSERT, after fetching sequence value |
| How ID is generated | Database generates from identity/auto-increment column | Database supplies from sequence |
| Insert batching in Hibernate | Disabled for entities using IDENTITY | Can group INSERTs into a JDBC batch |
| Pre-allocating multiple IDs | Not via sequence allocation mechanism | Can use allocationSize/optimizer |
| Database dependency | Requires identity column type or equivalent | Database and provider must support sequences |
| Suitable scenarios | Simple schema, moderate insert volume, auto-increment preferred | Bulk imports, insert throughput matters, database supports sequences |

For example, a service importing 10,000 entities using IDENTITY may have to send each INSERT individually through Hibernate. If the entity uses SEQUENCE and batching is configured properly, Hibernate can send groups of INSERTs using JDBC batches. Actual results still depend on driver, network, indexes, constraints, transactions, and database load; a fixed speedup ratio cannot be inferred from ID strategy alone.

**Technical takeaway:** in Hibernate, SEQUENCE is usually the more favorable choice for high-volume insert workloads because IDs are known before INSERT. IDENTITY can still be appropriate when schema requirements or workloads do not need insert batching.

## 5. Enabling JDBC batching in Spring Boot

When using Spring Boot with Hibernate, you can configure properties in application.properties:

~~~properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
~~~

Meaning:

- hibernate.jdbc.batch_size: maximum number of JDBC statements Hibernate groups into a single batch. A value of 50 is merely a starting point for measurement, not the optimal number for every system.
- hibernate.order_inserts: instructs Hibernate to sort INSERT operations so statements of the same type sit adjacent to one another and form better batches.
- hibernate.order_updates: sorts UPDATE operations to improve batching and may help reduce certain lock contentions via a consistent ordering.

Ordering operations has its own overhead, so benchmark before and after enabling it. Statements differing in table, columns, or SQL shape cannot necessarily be combined into one batch.

Setting batch_size alone does not guarantee batching occurs. If entities use IDENTITY, Hibernate's insert batching limitation still applies. If the transaction flushes too early, statements do not belong to the same group, or the driver behaves differently, actual batches may be smaller than expected.

### 5.1. Driver configuration

Some JDBC drivers have their own batch optimization options. For example, PostgreSQL JDBC has reWriteBatchedInserts; MySQL Connector/J has rewriteBatchedStatements. These options can help the driver transform or optimize how batches are sent, though syntax, defaults, and effectiveness depend on driver version.

This is an additional optimization step. First verify that Hibernate actually issues JDBC batches; only then test driver options and measure again. Do not copy one driver's option to another database.

## 6. Example of saving many entities in chunks

Suppose the new entity uses SEQUENCE and the repository extends JpaRepository:

~~~java
import java.util.List;

import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderImportService {
    private static final int CHUNK_SIZE = 50;

    private final PurchaseOrderRepository repository;
    private final EntityManager entityManager;

    public OrderImportService(
            PurchaseOrderRepository repository,
            EntityManager entityManager) {
        this.repository = repository;
        this.entityManager = entityManager;
    }

    @Transactional
    public void importOrders(List<PurchaseOrder> orders) {
        for (int start = 0; start < orders.size(); start += CHUNK_SIZE) {
            int end = Math.min(start + CHUNK_SIZE, orders.size());
            List<PurchaseOrder> chunk = orders.subList(start, end);

            repository.saveAll(chunk);

            entityManager.flush();
            entityManager.clear();
        }
    }
}
~~~

The example assumes all objects in the list are new entities, the repository is declared, and the identifier mapping uses SEQUENCE. The import method runs in a service transaction; saveAll calls join that transaction under default propagation.

- saveAll() stores entities in the persistence context. On its own, saveAll() mainly iterates over entities and calls the save mechanism; the method name does not guarantee the database receives a single bulk INSERT statement.
- flush() asks EntityManager to synchronize pending changes to the database. Hibernate can send eligible INSERTs via JDBC batching.
- clear() removes all managed entities from the persistence context, helping bound memory during large imports. Those entities then become detached.

You must flush before clear so pending changes are not lost. After clear, do not assume old entities are still managed or that subsequent modifications to them will be saved automatically.

CHUNK_SIZE in the example is the application-level processing chunk size; hibernate.jdbc.batch_size is the JDBC batch size. The two values may be equal for ease of tracking, though they do not have to match.

### 6.1. Flush and commit are different

flush() pushes SQL to the database within the current transaction, but it does not commit the transaction. Changes can still roll back until the transaction commits.

If the entire import runs in a single transaction, flushing and clearing in chunks reduces how many entities are held in the persistence context, but it does not shorten the transaction. Database locks, transaction logs, and rollback scope can still extend until the end of the import.

If you need to commit per chunk to limit transaction duration, you must design separate transaction boundaries per chunk. That changes atomicity: earlier chunks may already be committed even if a later chunk fails. Do not add REQUIRES_NEW or internal transaction calls casually; design error handling, retries, and committed data explicitly.

## 7. saveAll(), saveAllAndFlush(), and JDBC batching

Repository methods are frequently misunderstood:

- **saveAll(entities):** saves each entity via Spring Data JPA's save mechanism. It does not automatically turn the list into a multi-row SQL INSERT and does not guarantee JDBC batching.
- **saveAllAndFlush(entities):** saves the list and then flushes the persistence context. Flushing can cause Hibernate to execute JDBC batches if configuration and identifier strategy allow.
- **EntityManager.persist(entity):** marks a new entity to be managed by the persistence provider. This is the direct JPA API; calling persist in a loop does not guarantee batching if the provider or ID strategy does not support it.

Spring Data JPA determines whether an entity is new or existing to choose between persist and merge. If an entity is detected as existing, merge may issue a SELECT or follow a different path than persist for new entities. When optimizing imports, check entity state and how Spring Data evaluates isNew.

If many rows need updating under the same condition, a JPQL bulk UPDATE or DELETE may be more suitable than batching entities. However, bulk DML has different semantics: it executes directly in the database, does not update entities currently held in the persistence context, and may bypass lifecycle callbacks or versioning compared to regular entity operations. Synchronize or clear the persistence context appropriately after bulk DML.

## 8. Other factors affecting batching

Beyond IDENTITY and SEQUENCE, inspect the following factors:

1. **Transaction boundary:** Operations must sit inside an appropriate transaction. Calling individual repository methods across many tiny transactions can eliminate opportunities to batch statements together.
2. **Flush mode and flush timing:** Hibernate may flush before certain queries or at transaction commit. Flushing too frequently shrinks batches.
3. **Matching SQL shape:** Hibernate can only group statements with compatible SQL. Different entity types or INSERTs with different column sets may fall into separate batches.
4. **Operation ordering:** order_inserts and order_updates can improve statement grouping. Foreign-key relationships and data dependency ordering must still be handled validly by the provider.
5. **Optimistic locking:** Entities using @Version can generate UPDATEs with version conditions. Batching versioned UPDATEs depends on driver support for returning accurate update counts and corresponding Hibernate settings. Check provider and driver versions before changing batch options for versioned data.
6. **Driver and database:** Packet size limits, parameter limits, batch rewrite capability, and how the driver implements executeBatch can affect performance.
7. **Indexes and constraints:** The database must still maintain indexes and check foreign keys and constraints for every record. Batching reduces communication overhead but does not eliminate this work.
8. **Persistence context size:** Holding tens of thousands of managed entities at once can consume significant memory. Use chunked flush/clear when needed while understanding how clear affects managed entities.

Do not pick an overly large batch size right away. Overly large batches can increase application/driver memory usage, request sizes, and per-call processing time. Measure with production-like data and load, try reasonable levels such as 20, 50, or 100, and choose based on results.

## 9. Verifying that batching actually works

To verify, do not look only at the number of save() or saveAll() calls. Observe Hibernate actually sending batches through JDBC.

Suggested verification process:

1. Use the same database engine and JDBC driver as your deployment environment. Testcontainers helps integration tests run against a real database instead of relying solely on H2.
2. Create a sufficiently large number of entities, such as a few hundred records, and execute within a single transaction.
3. Test IDENTITY and SEQUENCE mappings separately while keeping other conditions comparable.
4. Enable hibernate.jdbc.batch_size and inspect logs/metrics from Hibernate, the JDBC driver, or a datasource proxy to see executeBatch calls.
5. Compare batch counts, round trips, duration, memory usage, and resulting data.
6. Also test rollbacks, constraint errors, and foreign-key relationships to ensure optimizations do not alter correctness.

You can enable Hibernate statistics in test environments:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Statistics and logs help observe ORM activity; to verify exact JDBC batching, use a datasource proxy or JDBC observability tool that displays executeBatch. Plain SQL logging can print each INSERT individually even when the driver receives them via a batch, so inspect the right measurement layer.

A measurement should compare at least three cases: IDENTITY with batching enabled, SEQUENCE with batch_size = 1, and SEQUENCE with batch_size > 1. This comparison separates the effect of identifier generation from the benefit of JDBC batching.

## 10. Database support and choosing a strategy

Using SEQUENCE depends on the database management system:

| Database | Sequence and identity | Notes |
|---|---|---|
| PostgreSQL | Supports sequences and identity columns | SEQUENCE is a natural choice for Hibernate insert batching; configure sequence/optimizer appropriately. |
| Oracle Database | Supports sequences | Sequences are commonly used to supply IDs before INSERT; combines well with JDBC batching. |
| Microsoft SQL Server | Supports sequences and IDENTITY | Sequence objects can be chosen if schema and application allow. |
| MySQL | Uses AUTO_INCREMENT; no native sequence objects | IDENTITY/AUTO_INCREMENT is common; do not assume GenerationType.SEQUENCE has the same capability as in PostgreSQL or Oracle. |

How to choose:

- **Choose IDENTITY** if the existing schema uses auto-increment, insert volume is low, or simplicity matters more than insert throughput. Accept that Hibernate normally does not batch INSERTs for IDENTITY entities.
- **Choose SEQUENCE** if the database supports sequences and the application frequently inserts many entities. Pair an appropriate allocationSize with an optimizer to reduce ID round trips and enable JDBC batching to group INSERTs.
- **Do not rely on AUTO when predictable performance behavior is needed:** providers can select different strategies depending on database and dialect. For sensitive workloads, declare the strategy explicitly and verify the schema.
- **Measure on the target database:** do not draw conclusions solely from unit tests or H2, because ID generation, locking, sequences, and batching depend on the engine and driver.
- **Preserve transaction correctness:** batch optimizations must never compromise rollback control, foreign keys, optimistic locking, or persistence context state.

When importing large volumes of data with Spring Data JPA and Hibernate, choosing SEQUENCE generally creates better conditions for JDBC insert batching because IDs are available before INSERT. Still, the final outcome only materializes when the identifier generator, batch size, transactions, flush/clear, and JDBC driver are configured coherently and measured in a production-like environment.