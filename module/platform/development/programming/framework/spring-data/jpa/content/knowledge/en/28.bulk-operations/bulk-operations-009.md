# Impact of IDENTITY and SEQUENCE on Batching Capability

## 1. What is batching in JPA/Hibernate?

When saving many entities, an application can generate hundreds or thousands of INSERT statements. Sending each statement individually can add communication overhead between the application and the database for every transmission. **JDBC batching** allows grouping multiple executions of the same prepared statement into a single batch and sending them to the database together.

For example, instead of sending 100 INSERT statements one by one for 100 orders, Hibernate can prepare one INSERT template, bind parameter sets for each order, and invoke JDBC's batching mechanism. The database still processes records as individual INSERT operations; batching primarily reduces round-trips and JDBC call overhead rather than turning them into a single SQL statement.

In Spring Data JPA, Hibernate is typically the JPA provider. Hibernate manages entity operations in the persistence context and emits SQL on flush. The ability to group INSERTs into a JDBC batch depends on:

- Hibernate's batch size configuration.
- The identifier generator type used to produce primary keys.
- Whether the SQL statements share the same shape to be grouped into one batch.
- Flush timing, transaction boundaries, and JDBC driver behavior.
- Database configuration, dialect, and Hibernate version.

The JPA specification does not require every provider to implement JDBC batching in the exact same way. The behavior explanations below focus on Hibernate, which is the common provider in Spring Data JPA.

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

Database systems can implement this with identity or auto-increment columns, such as MySQL AUTO_INCREMENT or SQL Server IDENTITY.

### 2.1. Why does IDENTITY prevent insert batching in Hibernate?

After an INSERT, Hibernate needs to know the database-generated ID to identify the entity in the persistence context, manage relationships, and handle subsequent operations. With IDENTITY, this value is only available after the database executes the INSERT and returns the generated key.

Because it needs the ID immediately from the database, Hibernate typically has to execute the INSERT eagerly for entities using IDENTITY. Hibernate therefore **disables JDBC insert batching for entities using the identity identifier generator**. Even with a batch size greater than 0, INSERTs for this entity group are usually sent individually.

Practical consequences:

- Calling save() repeatedly or saveAll() does not automatically turn IDENTITY INSERTs into a JDBC batch.
- Increasing hibernate.jdbc.batch_size does not overcome Hibernate's IDENTITY insert batching limitation.
- UPDATE and DELETE operations can still be batched if other batching conditions are met.
- Other entities using SEQUENCE can still batch inserts in the same application.

This is a limitation of Hibernate's IDENTITY execution path, not a rule that every SQL operation in the transaction loses batching.

### 2.2. When is IDENTITY still reasonable?

IDENTITY is simple, easy to configure, and suitable when the database has standardized on auto-increment columns for ID generation, insert volume is modest, or insert performance is not a bottleneck. It also fits when compatibility with an existing schema matters more than insert batching.

Do not change strategies solely on the assumption that sequence is always faster. Measure the actual workload, evaluate the deployed database, and consider whether batching brings meaningful gains.

## 3. How does SEQUENCE work?

With the SEQUENCE strategy, Hibernate fetches values from a database sequence before inserting the entity. Because the ID is already known prior to sending the INSERT, Hibernate can queue multiple entities in the persistence context and group the corresponding INSERTs into a JDBC batch on flush.

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

In the example, purchase_order_seq_gen is the generator name referenced in the JPA mapping; purchase_order_seq is the database sequence name. allocationSize is the number of identifiers the provider can allocate under its allocation/optimizer mechanism. The default allocationSize in JPA is 50 if omitted.

### 3.1. Why does SEQUENCE allow batching?

General workflow:

1. Hibernate pre-fetches one or more IDs from the sequence.
2. Entities are assigned IDs and managed in the persistence context.
3. On flush, Hibernate emits INSERTs sharing the same SQL shape.
4. Eligible INSERTs are grouped into batches according to JDBC configuration.
5. The JDBC driver sends the batch to the database.

Hibernate does not need to wait for an INSERT to finish to know the entity's ID. That is the key difference making SEQUENCE favorable for insert batching.

If allocationSize equals 1, the provider may need to fetch sequence values more frequently. Even so, knowing the ID before the INSERT still permits grouping INSERTs; allocationSize and JDBC batch size are two independent settings.

### 3.2. allocationSize is not batch size

Two parameters that are often confused:

| Parameter | Purpose |
|---|---|
| allocationSize | Number of IDs allocated per the JPA provider's sequence allocation mechanism. |
| hibernate.jdbc.batch_size | Number of similar JDBC statements Hibernate attempts to group into one batch. |

For instance, allocationSize = 50 and batch_size = 50 does not mean the two features are the same. One parameter controls ID allocation; the other controls the number of JDBC statements in a batch.

With Hibernate, a sequence optimizer can allocate a block of IDs to reduce sequence calls. Ensure the physical database sequence configuration is compatible with allocationSize and the optimizer used by your Hibernate version. Do not arbitrarily alter the sequence INCREMENT BY without checking how the provider allocates IDs; mismatched configuration can cause schema validation errors or incorrect ID allocation.

Sequence allocation can leave gaps in the ID sequence due to rollbacks, unused allocated blocks, database caching, or application shutdown mid-run. Auto-generated IDs are not contiguous business sequence numbers and should not be used to guarantee gapless numbering.

## 4. Comparing IDENTITY and SEQUENCE for batching

| Criterion | IDENTITY | SEQUENCE |
|---|---|---|
| When ID is available | After the database executes the INSERT | Before INSERT, after fetching sequence value |
| How ID is generated | Database generates from identity/auto-increment column | Database provides from sequence |
| Insert batching in Hibernate | Usually disabled for entities using IDENTITY | Can group INSERTs into a JDBC batch |
| Pre-allocating multiple IDs | Not supported via sequence allocation | Can use allocationSize/optimizer |
| Database dependency | Requires an identity column or equivalent | Database and provider must support sequences |
| Suitable scenarios | Simple schema, moderate insert volume, auto-increment preferred | Large imports, insert throughput matters, database supports sequences |

For example, a service importing 10,000 entities using IDENTITY may still have to send each INSERT individually through Hibernate. If the entity uses SEQUENCE and batching is configured properly, Hibernate can send groups of INSERTs via JDBC batching. Actual results also depend on driver, network, indexes, constraints, transactions, and database load; you cannot extrapolate a fixed speedup ratio solely from the ID strategy.

**Technical conclusion:** in Hibernate, SEQUENCE is generally the more favorable choice for high-volume insert workloads because IDs are known before INSERT. IDENTITY can still be appropriate when schema requirements or workloads do not need insert batching.

## 5. Enabling JDBC batching in Spring Boot

When using Spring Boot with Hibernate, configure in application.properties:

~~~properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
~~~

Meaning:

- hibernate.jdbc.batch_size: maximum number of JDBC statements Hibernate groups into a batch. A value of 50 is merely a starting point for benchmarking, not optimal for every system.
- hibernate.order_inserts: instructs Hibernate to sort INSERT operations so statements of the same type have a better chance of sitting adjacent and forming better batches.
- hibernate.order_updates: sorts UPDATE operations to improve batching opportunities and can help reduce certain lock conflicts via consistent ordering.

Sorting operations carries its own overhead, so benchmark before and after enabling it. Statements differing in table, columns, or SQL shape cannot necessarily be batched together.

Configuring batch_size does not by itself guarantee batching occurs. If the entity uses IDENTITY, the insert batching restriction still applies in Hibernate. If the transaction flushes too early, statements do not group together, or the driver has special behavior, actual batches may be smaller than expected.

## 6. Example saving multiple entities in groups

Suppose new entities use SEQUENCE and the repository extends JpaRepository:

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

The example assumes objects in the list are all new entities, the repository is declared, and the identifier mapping uses SEQUENCE. The import method runs in one service transaction; saveAll calls join that transaction via default propagation.

- saveAll() saves entities into the persistence context. On its own, saveAll() mainly iterates through entities and calls the save mechanism; the method name does not guarantee the database receives a single bulk INSERT statement.
- flush() instructs EntityManager to synchronize pending changes to the database. Hibernate can send eligible INSERTs via JDBC batch.
- clear() removes all managed entities from the persistence context, helping bound memory during large imports. Entities become detached afterward.

You must flush before clearing so pending changes are not lost. After clearing, do not continue assuming old entities remain managed or that subsequent modifications to them will be saved automatically.

CHUNK_SIZE in the example is the application-level processing group size; hibernate.jdbc.batch_size is the JDBC batch size. Both values can be equal for clarity, but they do not have to be identical.

### 6.1. Flush and commit are different

flush() pushes SQL to the database within the current transaction, yet does not commit the transaction. Changes can still roll back until the transaction commits.

If the entire import runs in a single transaction, flushing and clearing in groups reduces the number of entities kept in the persistence context, but does not shorten the transaction. Database locks, transaction logs, and rollback scope can still span until the end of the import.

If you need to commit each group to limit transaction duration, design separate transaction boundaries per group. This changes atomicity: earlier groups may have committed even if a later group fails. Do not add REQUIRES_NEW or internal transaction calls casually; explicitly design error handling, retries, and partially committed data handling.

## 7. saveAll(), saveAllAndFlush(), and JDBC batch

Repository methods are often misunderstood:

- **saveAll(entities):** saves each entity via Spring Data JPA's save mechanism. It does not automatically turn the list into a multi-row SQL INSERT and does not guarantee a JDBC batch.
- **saveAllAndFlush(entities):** saves the list and then flushes the persistence context. Flushing can cause Hibernate to execute a JDBC batch if configuration and identifier strategy permit.
- **EntityManager.persist(entity):** marks a new entity for the persistence provider to manage. This is the direct JPA API; calling persist in a loop does not guarantee batching if the provider or ID strategy does not support it.

Spring Data JPA determines whether an entity is new or existing to choose persist or merge. If an entity is detected as already existing, merge may issue a SELECT or behave differently from the persist path for new entities. When optimizing imports, check entity state and how Spring Data determines isNew.

If many rows need updating under the same condition, JPQL bulk UPDATE or DELETE may be more suitable than batching entities. However, bulk DML has different semantics: it executes directly on the database, does not update entities in the persistence context, and can bypass lifecycle callbacks and version mechanisms compared to normal entity operations. Sync/clear the persistence context appropriately after bulk DML.

## 8. Other factors affecting batching

Besides IDENTITY and SEQUENCE, check the following factors:

1. **Transaction boundary:** Operations must run in an appropriate transaction. Calling individual repository methods in many tiny transactions can eliminate opportunities to batch statements together.
2. **Flush mode and flush timing:** Hibernate may flush before certain queries or at transaction commit. Flushing too frequently shrinks batches.
3. **Identical SQL shape:** Hibernate only batches statements compatible in SQL text. Different entity types or INSERTs with different column sets may belong to separate batches.
4. **Operation ordering:** order_inserts and order_updates can improve statement grouping. Foreign key relationships and data dependency ordering must still be validly handled by the provider.
5. **Optimistic locking:** Entities with @Version can produce UPDATEs with version conditions. Batching versioned UPDATEs depends on driver ability to return accurate update counts and corresponding Hibernate settings. Check provider and driver versions before changing batch options for versioned data.
6. **Driver and database:** Packet size limits, parameter limits, batch rewrite support, and how the driver implements executeBatch can affect performance.
7. **Indexes and constraints:** The database still has to maintain indexes and check foreign keys and constraints for every record. Batching reduces communication overhead, not this cost.
8. **Persistence context size:** Holding tens of thousands of managed entities at once can consume considerable memory. Use chunked flush/clear when needed while understanding the impact of clear on managed entities.

Do not pick an overly large batch size right from the start. Oversized batches can increase application/driver memory, request sizes, and per-batch processing time. Measure with production-like data and load, try reasonable levels like 20, 50, or 100, and choose based on results.

## 9. Verifying batching actually works

To verify, do not merely count save() or saveAll() calls. Observe Hibernate actually sending batches over JDBC.

Recommended verification process:

1. Use the same database engine and JDBC driver as the deployment environment. Testcontainers helps integration tests run on a real database rather than relying solely on H2.
2. Create a sufficiently large number of entities, e.g., several hundred records, and execute within one transaction.
3. Test IDENTITY and SEQUENCE mappings separately while keeping other conditions comparable.
4. Enable hibernate.jdbc.batch_size and inspect Hibernate, JDBC driver, or datasource-proxy logs/metrics to observe executeBatch calls.
5. Compare batch count, round-trip count, duration, memory usage, and data results.
6. Also test rollbacks, constraint errors, and foreign key relationships to be sure the optimization does not alter correctness.

You can enable Hibernate statistics in test environments:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Statistics and logs help observe ORM activity; to confirm exact JDBC batching, use a datasource proxy or JDBC instrumentation tool that displays executeBatch. Plain SQL logging can print each INSERT separately even if the driver received them via a batch, so inspect the right measurement layer.

A benchmark should compare at least three cases: IDENTITY with batching enabled, SEQUENCE with batch_size equal to 1, and SEQUENCE with batch_size greater than 1. This comparison isolates the effect of identifier generation from the benefit of JDBC batching.

## 10. Choosing a strategy for the application

- **Choose IDENTITY** if the current schema uses auto-increment, insert volume is not large, or simplicity outweighs insert throughput. Accept that Hibernate usually does not batch INSERTs for IDENTITY entities.
- **Choose SEQUENCE** if the database supports sequences and the application frequently inserts many entities. Combine an appropriate allocationSize with an optimizer to reduce ID fetches, and enable JDBC batching to group INSERTs.
- **Do not rely on AUTO when predictable performance behavior is needed:** the provider may pick different strategies depending on database and dialect. For sensitive workloads, declare the strategy explicitly and verify the schema.
- **Measure on the target database:** do not draw conclusions from unit tests or H2 alone, because ID generation, locking, sequences, and batching depend on engine/driver.
- **Preserve transaction correctness:** batch optimization must never compromise rollback control, foreign keys, optimistic locking, or persistence context state.

When importing large datasets with Spring Data JPA and Hibernate, choosing SEQUENCE generally creates better conditions for JDBC insert batching because IDs are available before INSERT. However, actual gains only materialize when the identifier generator, batch size, transactions, flush/clear, and JDBC driver are configured cohesively and measured in a near-production environment.
