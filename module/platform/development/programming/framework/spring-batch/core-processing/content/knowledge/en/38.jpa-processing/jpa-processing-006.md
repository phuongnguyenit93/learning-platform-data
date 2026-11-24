# JpaItemWriter

`JpaItemWriter<T>` is Spring Batch's writer that uses the Java Persistence API (JPA) to write a chunk of entities to the database through an `EntityManager`. It receives entities from the processor or reader, performs persist/merge operations within the step's transaction, and flushes changes to the persistence provider.

`JpaItemWriter` is suitable when the application already uses JPA/Hibernate and you want the batch step to write entities using the same mapping model as the rest of the application. To use it safely, understand whether entities are transient, managed, or detached; choose between `persist` and `merge`; configure the right `EntityManagerFactory` and transaction manager; and design cascades, flushing, rollback, and restart around chunk boundaries.

## 1. Where does JpaItemWriter sit in chunk processing?

In a chunk-oriented step, the reader retrieves inputs, the processor converts inputs into entities, and the writer writes the group of entities. `JpaItemWriter` receives a `Chunk` and executes JPA operations for each item.

```text
Input source
    |
    v
ItemReader<OrderInput>
    |
    v
ItemProcessor<OrderInput, OrderEntity>
    |
    v
Chunk<OrderEntity>
    |
    v
JpaItemWriter<OrderEntity>
    |
    +--> EntityManager.persist(...) or merge(...)
    |
    +--> flush persistence context
    |
    v
JPA provider / JDBC
    |
    v
Database
    |
    v
Chunk transaction commit
```

The writer does not define the entire step transaction boundary by itself. Spring Batch opens a transaction for the chunk; `JpaItemWriter` performs JPA operations inside that transaction. When the chunk commits, the database commits the changes; if the transaction rolls back, uncommitted changes in that chunk are undone.

## 2. Configuring JpaItemWriter in Spring Batch 5

`JpaItemWriterBuilder<T>` configures the writer with an `EntityManagerFactory` and persist/merge options.

```java
@Bean
JpaItemWriter<OrderEntity> orderJpaWriter(
        EntityManagerFactory entityManagerFactory) {

    return new JpaItemWriterBuilder<OrderEntity>()
        .entityManagerFactory(entityManagerFactory)
        .build();
}
```

This example uses the writer's default behavior, which merges entities. `EntityManagerFactory` must match the persistence unit and database the step targets.

When using Spring Boot with Spring Data JPA, `EntityManagerFactory` is typically auto-configured. Do not manually create an `EntityManager` per item or inject a mutable `EntityManager` into the writer; let the writer use the factory and current transaction.

## 3. Configuring JpaTransactionManager for the step

JPA requires a transaction manager matching the `EntityManagerFactory`. In a plain Spring application, you can declare `JpaTransactionManager` as follows:

```java
@Bean
PlatformTransactionManager jpaTransactionManager(
        EntityManagerFactory entityManagerFactory) {
    return new JpaTransactionManager(entityManagerFactory);
}
```

Pass the transaction manager into the chunk builder:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager jpaTransactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, OrderEntity> orderProcessor,
        JpaItemWriter<OrderEntity> orderJpaWriter) {

    return new StepBuilder("importOrders", jobRepository)
        .<OrderInput, OrderEntity>chunk(100, jpaTransactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderJpaWriter)
        .build();
}
```

In Spring Boot, a `JpaTransactionManager` may already be auto-configured. If there are multiple persistence units or transaction managers, inject the right bean using `@Qualifier`.

Do not arbitrarily pick `DataSourceTransactionManager` for a JPA-writing step. `JpaTransactionManager` manages transactions bound to `EntityManagerFactory` and synchronizes the persistence context with the transaction. If one step uses both JPA and JDBC, configure them on the same datasource using Spring-supported mechanisms so JDBC access joins the same transaction properly.

## 4. Entities require valid JPA mappings

`JpaItemWriter` writes entities managed by a JPA provider. Entities need valid mappings, typically including `@Entity`, `@Id`, and field/relationship mappings.

```java
@Entity
@Table(name = "ORDERS")
public class OrderEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "SOURCE_ORDER_ID", nullable = false, unique = true)
    private String sourceOrderId;

    @Column(name = "CUSTOMER_ID", nullable = false)
    private String customerId;

    @Column(name = "TOTAL_AMOUNT", nullable = false, precision = 19, scale = 2)
    private BigDecimal totalAmount;

    protected OrderEntity() {
    }

    public OrderEntity(
            String sourceOrderId,
            String customerId,
            BigDecimal totalAmount) {
        this.sourceOrderId = sourceOrderId;
        this.customerId = customerId;
        this.totalAmount = totalAmount;
    }

    public Long getId() { return id; }
    public String getSourceOrderId() { return sourceOrderId; }
    public String getCustomerId() { return customerId; }
    public BigDecimal getTotalAmount() { return totalAmount; }
}
```

This example uses `sourceOrderId` as a unique business key to prevent importing the same source order twice. The JPA primary key and business key serve different roles: the database ID identifies the entity, while the source ID identifies the same input record across retries, restarts, or repeated imports.

## 5. Processor converts DTOs into entities

The reader can read DTOs from CSV, XML, JSON, or JDBC. The processor converts DTOs into entities before the writer persists them:

```java
@Bean
ItemProcessor<OrderInput, OrderEntity> orderProcessor() {
    return input -> {
        if (input.orderId() == null || input.orderId().isBlank()) {
            throw new InvalidOrderException("orderId is required");
        }

        if (input.totalAmount() == null || input.totalAmount().signum() < 0) {
            throw new InvalidOrderException("totalAmount must be non-negative");
        }

        return new OrderEntity(
            input.orderId(),
            input.customerId(),
            input.totalAmount()
        );
    };
}
```

Item validation typically belongs in the processor or a dedicated validator. The writer focuses on persistence. If the processor looks up existing entities or builds JPA relationships, consider query counts, entity state, and the transaction in which the processor runs.

## 6. How do persist and merge differ?

`JpaItemWriter` defaults to `EntityManager.merge(item)`. You can configure `usePersist(true)` to call `EntityManager.persist(item)`.

| Operation | Purpose | Input object |
|---|---|---|
| `persist` | Places a new/transient entity into the persistence context for insertion | Brand-new entity not yet persisted |
| `merge` | Copies state from an input entity into a managed instance | Typically detached entities or entities needing state synchronization |

`persist` is not an upsert operation. If an entity with an already-existing identity or conflicting constraint is persisted, it can fail at persist or flush time.

`merge` is also not simply "update if exists, insert if not" in the sense of a SQL upsert statement. The JPA provider determines how to find or create the managed instance based on identity and mappings. If no matching entity exists, `merge` can create a new copy to insert.

## 7. Using persist for new entities

When every item is a brand-new entity and IDs are generated appropriately, configure the writer to use `persist`:

```java
@Bean
JpaItemWriter<OrderEntity> newOrderWriter(
        EntityManagerFactory entityManagerFactory) {

    return new JpaItemWriterBuilder<OrderEntity>()
        .entityManagerFactory(entityManagerFactory)
        .usePersist(true)
        .build();
}
```

`persist` generally fits import pipelines creating new entities. Ensure each entity does not already exist by identity or business key. If the same item is replayed due to a retry, restart, or job re-launch, unique constraints can cause subsequent writes to fail.

To make imports safely re-runnable, apply an explicit strategy such as existence checks by source ID, controlled upserts, staging tables, or business duplicate handling. Do not enable `persist` expecting the writer to automatically deduplicate records.

## 8. Using merge for detached entities or state synchronization

`merge` is useful when items are detached entities or constructed outside the current persistence context. You can use the default behavior:

```java
@Bean
JpaItemWriter<CustomerEntity> customerWriter(
        EntityManagerFactory entityManagerFactory) {

    return new JpaItemWriterBuilder<CustomerEntity>()
        .entityManagerFactory(entityManagerFactory)
        .usePersist(false)
        .build();
}
```

`merge` returns a managed instance. The passed-in object does not itself become managed; it may remain detached. `JpaItemWriter` calls `merge` without replacing items in the chunk with the returned managed objects, so do not rely on fields being updated on the input objects after the writer runs.

Merging can trigger queries to look up existing entities, so for millions of items measure query counts and throughput. If the goal is merely updating a few columns, consider bulk updates via JDBC/JPA queries or a specialized writer rather than merging entire entity graphs.

## 9. When to choose persist vs. merge?

The decision depends on entity state and business requirements:

| Scenario | Common choice |
|---|---|
| Creating new entities guaranteed not to exist yet | `persist` |
| Receiving detached entities whose state needs synchronization | `merge` |
| Updating entities already managed in the same persistence context | Usually no need to call persist/merge again; dirty checking will flush changes |
| Import that may encounter existing IDs | Define explicit update/skip/reject rules; do not guess via defaults |
| Needing upsert by business key | Use explicit upsert logic or a database-specific strategy |

Do not choose `merge` merely because it seems "more flexible." `merge` can increase `SELECT` queries and copy all field values, including nulls if the input object is incomplete. Do not choose `persist` for detached entities just to skip `SELECT`s; `persist` does not have update semantics for existing entities.

## 10. JpaItemWriter flushes the persistence context

JPA does not necessarily send SQL to the database immediately when `persist` or `merge` is called. Changes are tracked in the persistence context and can be flushed before commit.

`JpaItemWriter` flushes the persistence context after writing a chunk so constraint or persistence errors surface within the writer call/transaction scope. Flushing sends SQL to the database, though the transaction is not yet committed.

```text
Chunk transaction starts
    |
    v
JpaItemWriter.write(chunk)
    |
    +--> persist/merge each entity
    |
    +--> EntityManager.flush()
    |
    v
Database executes SQL within transaction
    |
    +--> writer/step succeeds -> COMMIT at chunk end
    |
    +--> exception -> ROLLBACK per policy
```

If flushing raises `ConstraintViolationException`, `PersistenceException`, or a Spring-translated exception, the exception propagates to the step and the transaction can roll back. Do not catch and swallow flush exceptions if data has not been written properly.

## 11. Persistence context and clearing after write

The persistence context tracks managed entities. Holding too many entities in a long-lived context raises memory consumption and makes dirty checking expensive.

`JpaItemWriter` provides a `clearPersistenceContext` option in supporting Spring Batch versions. When enabled, the writer flushes and then clears the persistence context to release managed entities after writing each chunk. The builder can configure this option with `clearPersistenceContext(...)`.

Once the context is cleared, previously managed entities become detached. Do not keep references expecting later field changes to be automatically persisted via dirty checking. If further updates are needed, load or merge the entity in an appropriate transaction.

Clearing prevents the persistence context from accumulating across multiple chunks. However, if processors or listeners rely on entities remaining managed after the writer runs, verify callback ordering and configuration; never assume objects remain managed after the writer completes.

## 12. Transaction boundaries of JpaItemWriter

`JpaItemWriter` requires an active transaction to write data consistently. In Spring Batch, the chunk step's transaction is usually the appropriate boundary.

```java
return new StepBuilder("importOrders", jobRepository)
    .<OrderInput, OrderEntity>chunk(100, jpaTransactionManager)
    .reader(orderReader)
    .processor(orderProcessor)
    .writer(orderJpaWriter)
    .build();
```

All JPA operations performed by the writer in a chunk join the transaction managed by the transaction manager corresponding to `EntityManagerFactory`. If a chunk has 100 items and the writer fails on the last item, uncommitted changes in that chunk roll back.

Previously committed chunks remain intact. A job failure does not automatically roll back all data from the start of the job. This is why restarts rely on reader checkpoints and writers must handle uncommitted items being re-read safely.

## 13. Using the same EntityManagerFactory and transaction manager

The writer and transaction manager must belong to the same persistence unit. If the transaction manager manages a different `EntityManagerFactory` than the one the writer uses, the writer may not participate in the expected transaction.

With multiple persistence units, wire them explicitly:

```java
@Bean("ordersJpaTransactionManager")
PlatformTransactionManager ordersJpaTransactionManager(
        @Qualifier("ordersEntityManagerFactory") EntityManagerFactory emf) {
    return new JpaTransactionManager(emf);
}

@Bean
JpaItemWriter<OrderEntity> ordersWriter(
        @Qualifier("ordersEntityManagerFactory") EntityManagerFactory emf) {
    return new JpaItemWriterBuilder<OrderEntity>()
        .entityManagerFactory(emf)
        .build();
}
```

When building the step, inject `ordersJpaTransactionManager`. Use `@Qualifier` to prevent Spring from selecting the wrong transaction manager or `EntityManagerFactory` when multiple datasources exist.

## 14. Relationship between JPA transactions and JDBC access

An application might use JPA for entities and JDBC for certain bulk operations. When both target the same datasource and use Spring transaction-aware APIs, `JpaTransactionManager` can coordinate JDBC access on that datasource under proper configuration.

Example JDBC repository using `JdbcTemplate`:

```java
@Repository
public class ImportAuditRepository {

    private final JdbcTemplate jdbcTemplate;

    public ImportAuditRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public void recordChunk(long count) {
        jdbcTemplate.update(
            "INSERT INTO IMPORT_AUDIT (RECORD_COUNT) VALUES (?)",
            count
        );
    }
}
```

For JDBC operations to join the JPA transaction, use the exact datasource managed by `JpaTransactionManager` alongside `JdbcTemplate`/`DataSourceUtils`. A connection pulled directly from a pool or a different datasource may execute outside the chunk transaction.

Do not assume JPA and JDBC across two independent datasources will commit atomically. When multiple resources require atomic commits, use an appropriate distributed coordination mechanism; otherwise, design outbox, staging, idempotency, or compensation strategies.

## 15. Cascades with entity relationships

When an entity has relationships to other entities, `persist` and `merge` can propagate according to cascade configuration.

Example of an order with order lines:

```java
@Entity
@Table(name = "ORDERS")
public class OrderEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToMany(mappedBy = "order", cascade = CascadeType.PERSIST)
    private List<OrderLineEntity> lines = new ArrayList<>();

    public void addLine(OrderLineEntity line) {
        lines.add(line);
        line.setOrder(this);
    }
}
```

When using `persist`, `CascadeType.PERSIST` allows new lines to be persisted along with the relationship. If merging a detached graph, consider `CascadeType.MERGE` or `CascadeType.ALL` according to requirements.

Do not add broad cascades mechanically. For instance, `CascadeType.REMOVE` can delete related entities unexpectedly; `CascadeType.ALL` includes remove, detach, refresh, persist, and merge under JPA semantics. Design ownership and cascades according to actual data lifecycles.

## 16. Entity references and write-time N+1

A processor may need to link a new entity to an existing customer. Avoid loading the same customer repeatedly in a way that triggers N+1 queries if it can be optimized.

You can use `EntityManager.getReference` inside a transactional service to obtain an ID-backed reference proxy when appropriate, or use chunk-level caching/lookups. However, never inject an `EntityManager` and share it across threads; `EntityManager` is not thread-safe.

With `JpaItemWriter`, each item is typically persisted/merged within the transaction's persistence context. If every item holds a large graph, cascades can generate numerous SQL statements. Inspect actual SQL, fetch strategies, and cascade paths to avoid redundant writes or unnecessary loads.

## 17. Optimistic locking and @Version

When multiple transactions can update the same entity, optimistic locking detects updates built on stale state.

```java
@Entity
public class InventoryEntity {

    @Id
    private Long id;

    @Version
    private long version;

    private int availableQuantity;
}
```

The JPA provider uses `version` to detect conflicts. If one transaction updates an entity after another transaction already incremented its version, flush or commit can raise `OptimisticLockException` or a Spring-translated exception.

Do not blindly retry an optimistic lock failure by merging the exact same stale detached snapshot. Retrying with the old version will keep conflicting. Reload fresh state and reapply business logic if the operation can be recomputed safely.

## 18. Constraint violations and write errors

Common errors encountered when the writer flushes include:

- Unique constraint violations from duplicate source IDs or business keys.
- Foreign key violations because a referenced entity does not yet exist.
- Not-null or check constraint violations from invalid data.
- Optimistic lock conflicts due to changed versions.
- Mapping or SQL errors when schema and entity definitions diverge.

Not every database error can be retried. Permanent data errors usually require rejection or failure; deadlocks or transient faults can be retried with limits; optimistic locking requires a reload-and-recompute strategy.

In a fault-tolerant step, you can configure skip for specific item-level errors if business rules allow. However, a chunk-level writer failure may trigger framework recovery to isolate the offending item; the writer must be safe when re-invoked.

## 19. Retry and skip with JpaItemWriter

Example step configuration allowing skips for a well-defined data exception:

```java
return new StepBuilder("importOrders", jobRepository)
    .<OrderInput, OrderEntity>chunk(100, jpaTransactionManager)
    .reader(orderReader)
    .processor(orderProcessor)
    .writer(orderJpaWriter)
    .faultTolerant()
    .skip(InvalidOrderException.class)
    .skipLimit(50)
    .build();
```

This example skips exceptions thrown by the processor. If an error occurs during JPA flush, identify the concrete exception and whether it can be isolated to a single item. Never skip every `PersistenceException`, because connection failures, schema mismatches, or database-wide issues affect the entire chunk and cannot be resolved by dropping one item.

Retry applies only to classified transient faults. For instance, deadlocks may be retried after rollback; permanent unique constraint violations generally will not resolve on retry. When using `merge`, operations should have idempotent semantics so retries do not create duplicate business side effects.

## 20. Restart and JobRepository

`JpaItemWriter` does not replace reader checkpoints. When a chunk commits, JPA data is committed; readers and other `ItemStream` components persist their state via `ExecutionContext`. When restarting the same `JobInstance`, Spring Batch uses `JobRepository` to determine which step to re-run and the reader resumes from its checkpoint.

Example:

```text
Execution #1
  chunk 1 -> 100 entities -> COMMIT
  chunk 2 -> 100 entities -> COMMIT
  chunk 3 -> error before commit -> ROLLBACK

Execution #2 (restart same JobInstance)
  reader restores checkpoint after item 200
  re-read items belonging to uncommitted chunk
  writer writes next chunk
```

Entities from committed chunks remain persisted. Changes from the uncommitted chunk are rolled back if the JPA transaction and database function properly. Thus, the writer does not need to store a separate item index in `ExecutionContext` to replace the reader's checkpoint.

## 21. Idempotency on restart or job re-run

Restarting the same `JobInstance` differs from launching a new `JobInstance` for the same input. On restart, Spring Batch relies on checkpoints to avoid re-running committed chunks when transactions and metadata are properly coordinated.

Still, the system must guard against jobs launched with new identifying parameters, replayed inputs, or setups where metadata transactions and business data live on separate resources.

Common protections:

- Unique constraints on source/business keys.
- Upserts with explicit update rules.
- Staging tables keyed by batch ID, then merged/published after validation.
- Tracking import status by source ID.
- Idempotency keys for side effects outside the database.

Do not rely on `merge` alone to guarantee idempotency. `merge` synchronizes entity state by JPA identity; it does not replace business keys or duplicate-handling rules.

## 22. Performance with large chunks

`JpaItemWriter` throughput depends on items per chunk, SQL statement count, cascade graphs, persistence context behavior, ID generation strategy, and the provider/database's batch insert capabilities.

Key considerations:

- Large chunks reduce transaction commits but increase memory usage and rollback work.
- Merging detached entities can issue `SELECT` queries before updates/inserts.
- Large cascade graphs can emit more SQL than expected.
- Flushing per chunk surfaces errors before commit but can emit a large burst of SQL.
- Clearing the persistence context bounds accumulated managed entities.
- JDBC batching depends on provider, dialect, driver, and Hibernate/JPA settings.

With Hibernate, settings like `hibernate.jdbc.batch_size` and `hibernate.order_inserts`/`hibernate.order_updates` can improve batching where applicable. Measure SQL and benchmark against a real database; no single batch size is optimal for every workload.

## 23. IDENTITY generation and JDBC batching

ID generation strategies affect insert batching. Some providers/databases struggle to batch inserts when using `GenerationType.IDENTITY` because each `INSERT` must execute immediately to retrieve the generated key.

Sequence or table generator strategies can let the provider pre-allocate IDs and batch inserts more effectively, depending on database and configuration.

Do not change ID strategies purely for throughput without evaluating schema, uniqueness, and portability requirements. Measure against your actual provider and database while verifying insert ordering and cascades.

## 24. Bulk operations vs. JpaItemWriter

`JpaItemWriter` processes entities through the persistence context via persist/merge operations. Bulk JPQL updates/deletes or JDBC batches can be far more efficient when updating large volumes by predicate without hydrating individual entities.

Bulk JPQL updates/deletes bypass part of entity lifecycle semantics such as dirty checking and per-entity callbacks; an open persistence context can become stale after a bulk operation.

Choose the write mechanism based on requirements:

| Need | Suitable approach to consider |
|---|---|
| Writing entity graphs with cascades/lifecycle callbacks | `JpaItemWriter` |
| Writing new entities chunk by chunk | `JpaItemWriter` with `persist` when items are truly new |
| Synchronizing detached entities | `JpaItemWriter` with `merge` |
| Updating a column across millions of rows by condition | Bulk JPQL or JDBC batch |
| Custom SQL or database-specific upserts | Custom JDBC writer/query |

Do not choose bulk queries if per-entity callbacks, cascades, or entity-level validation are required. Conversely, do not merge millions of large graphs when a single bulk SQL statement expresses the business rule cleanly.

## 25. EntityManager is not thread-safe

A JPA `EntityManager` and its persistence context are not designed to be shared concurrently across multiple threads. `JpaItemWriter` uses the transaction/persistence context bound to the write execution; never create a singleton `EntityManager` and share it across workers.

With partitioning, each worker step has its own transaction and persistence context bound to its thread/execution. Ensure each worker uses the right transaction manager and has sufficient connection pool capacity.

Never store an `EntityManager` in a static field, pass it to an executor, or invoke the same persistence context from multiple threads. If a custom processor or writer needs JPA, inject transaction-aware services/repositories and let Spring manage the context.

## 26. Writer in a composite pipeline

`JpaItemWriter` can serve as a delegate inside a composite writer when one chunk must write to multiple targets. However, all delegates must have compatible transaction semantics.

Conceptual configuration example:

```java
CompositeItemWriter<OrderEntity> compositeWriter =
    new CompositeItemWriterBuilder<OrderEntity>()
        .delegates(orderJpaWriter, auditWriter)
        .build();
```

If `auditWriter` writes to the same datasource and joins the same transaction, both can commit or roll back together. If the audit writer calls an external API or writes a file, that side effect does not automatically roll back if the JPA transaction fails.

Delegate order also matters: if the first delegate produces a non-transactional side effect and a later delegate fails, the first side effect may remain. Use an outbox, staging, or compensation when cross-target consistency is required.

## 27. Testing JpaItemWriter

Unit tests on processors can verify entities are constructed properly. However, transactions, cascades, flushing, and constraints require integration tests against a suitable JPA provider and database.

Scenarios worth testing:

1. New entities are persisted and rows appear after commit.
2. Detached entities are merged and state synchronizes per mappings.
3. `usePersist(true)` handles duplicate identity/constraint violations per policy.
4. Cascaded persist/merge relationships work properly.
5. Constraint violations at flush roll back the chunk.
6. Previously committed chunks survive when a subsequent chunk fails.
7. Optimistic locking conflicts are handled per policy.
8. Clearing the persistence context does not break downstream code assuming managed state.
9. Restarting the same `JobInstance` does not write committed chunks twice.
10. Parallel partitions do not share an `EntityManager` across threads.
11. JDBC and JPA operations on the same datasource participate in the transaction when configured to do so.
12. External side effects are protected by idempotency, outbox, or compensation.

Conceptual transactional service test verifying rollback:

```java
@Test
void rollsBackJpaWritesWhenChunkTransactionFails() {
    assertThatThrownBy(() -> transactionTemplate.execute(status -> {
        entityManager.persist(new OrderEntity(
            "SRC-1001", "C001", new BigDecimal("125.50")));
        entityManager.flush();
        throw new IllegalStateException("forced failure");
    })).isInstanceOf(IllegalStateException.class);

    assertThat(orderRepository.findBySourceOrderId("SRC-1001"))
        .isEmpty();
}
```

This example assumes `TransactionTemplate`, `EntityManager`, and the repository share the same `JpaTransactionManager`/persistence unit. In full Spring Batch tests, launch the job and verify both `JobRepository` metadata and database rows.

## 28. Common pitfalls

| Pitfall | Consequence | Resolution |
|---|---|---|
| Using the wrong `EntityManagerFactory` | Writer does not join the expected persistence unit/transaction | Inject the right factory with `@Qualifier` |
| Using an incompatible transaction manager | JPA writes may not join the chunk transaction | Use the matching `JpaTransactionManager` |
| Choosing `persist` for existing entities | Can cause duplicate/EntityExists/constraint errors | Distinguish new vs. detached entities before choosing |
| Treating `merge` as SQL upsert | Can trigger unexpected `SELECT`/`INSERT`/`UPDATE` statements | Define explicit identity and business upsert rules |
| Ignoring the managed instance returned by `merge` | Continuing to mutate the detached input object expecting dirty checking | Reload/re-merge or use the managed instance inside the transaction |
| Wrong cascade configuration | Missing child inserts or unintended cascading deletes/updates | Configure cascades according to entity lifecycles |
| Missing unique business keys | Re-running jobs creates duplicates or fails | Enforce unique constraints and idempotent imports |
| Persistence context growing too large | Increased memory and dirty-checking overhead | Enable appropriate clearing and use reasonable chunk sizes |
| Retrying every `PersistenceException` | Permanent schema/constraint errors repeat needlessly | Separate transient errors from data errors |
| Sharing `EntityManager` across threads | Race conditions and persistence context corruption | Use thread-bound, transaction-scoped `EntityManager` instances |
| Confusing flush with commit | Data can still roll back after flush | Distinguish flush from transaction commit |
| Assuming JPA and file/API writes are atomic together | External side effects persist after rollback | Use an outbox, staging, or compensation |

## 29. Workflow for choosing and configuring JpaItemWriter

When designing a JPA writing step, clarify:

1. Are writer inputs JPA entities or DTOs converted by a processor?
2. Are entities new/transient or detached needing state synchronization?
3. Should `persist` or `merge` be used based on data semantics?
4. Do `EntityManagerFactory` and `JpaTransactionManager` belong to the same persistence unit?
5. Has the step builder received the right transaction manager?
6. Which persist/merge cascades do entity relationships require?
7. Are there unique business keys, optimistic locking, or constraints to handle?
8. Does the persistence context need clearing after each chunk to bound memory?
9. Have chunk size, JDBC batching, and ID strategies been benchmarked against a real database?
10. Are restarts, duplicate inputs, and external side effects idempotent?
11. Do integration tests verify flush, commit, rollback, cascades, and restarts?

## Conclusion

`JpaItemWriter<T>` writes entities chunk by chunk via a JPA `EntityManager`. By default, it uses `merge`; you can select `persist` when all items are brand-new entities. `persist` and `merge` have distinct semantics: `merge` copies state into a managed instance and returns that instance, whereas `persist` adds a new entity to the persistence context. `merge` is not a substitute for business-key upsert guarantees.

Configure the writer with the right `EntityManagerFactory` and use the matching `JpaTransactionManager` on the chunk step. Understand that flushing differs from committing, as well as entity cascades, persistence context clearing, optimistic locking, and thread-safety limits. Protect restarts and repeated imports with unique business keys and idempotency, and run integration tests against a real database to verify commits, rollbacks, performance, and final persisted state.
