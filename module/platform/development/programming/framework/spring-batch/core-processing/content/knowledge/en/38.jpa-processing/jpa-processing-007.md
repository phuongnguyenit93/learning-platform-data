# Transaction Manager for JPA

When a Spring Batch Step uses JPA to write data, the chunk's transaction manager needs to manage the exact `EntityManagerFactory` used by the Writer. The standard component is `JpaTransactionManager`. It opens and manages JPA transactions for an `EntityManagerFactory`, binds the `EntityManager` to the thread running the Step, and coordinates commits and rollbacks when a chunk finishes.

In Spring Batch 5, the transaction manager is passed explicitly to `StepBuilder`'s `chunk(...)`. Therefore, distinguish between the transaction manager used for business chunks and the transaction manager used by `JobRepository` to persist metadata. If the two use different datasources or persistence units, they do not automatically form a single atomic transaction.

## 1. What role does the transaction manager play in a JPA Step?

A chunk-oriented Step reads, processes, and writes a group of items within a transaction. With JPA, the transaction determines when changes in the persistence context are synchronized to the database and when they are committed.

Example of an order import Step:

```text
JobRepository
    |
    v
Step: importOrdersStep
    |
    v
JpaTransactionManager.begin()
    |
    +--> ItemReader
    +--> ItemProcessor
    +--> JpaItemWriter
    |       EntityManager.persist / merge
    |       EntityManager.flush
    |
    v
Transaction commit
    |
    v
Checkpoint / Step execution metadata
```

When a chunk succeeds, the transaction manager commits the JPA changes. If an exception triggers chunk rollback, uncommitted changes in that transaction are undone.

The transaction manager must be tied to the matching persistence unit. If the Writer uses `EntityManagerFactory` A while the Step runs with the transaction manager for persistence unit B, JPA operations may not join the chunk transaction as expected.

## 2. What is JpaTransactionManager?

`JpaTransactionManager` is the `PlatformTransactionManager` implementation for JPA. It manages transactions for a single `EntityManagerFactory`.

Inside a transaction, Spring binds the appropriate `EntityManager` to the current thread. Spring components such as `JpaItemWriter` or JPA repositories can obtain the transaction-participating `EntityManager` rather than starting an independent transaction.

Basic bean declaration:

```java
import jakarta.persistence.EntityManagerFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.orm.jpa.JpaTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class JpaTransactionConfig {

    @Bean("jpaTransactionManager")
    public PlatformTransactionManager jpaTransactionManager(
            EntityManagerFactory entityManagerFactory) {
        return new JpaTransactionManager(entityManagerFactory);
    }
}
```

This example uses Jakarta Persistence as in Spring Boot 3 / Spring Batch 5 applications. For older applications on Spring Batch 4 and Java EE namespaces, imports may use `javax.persistence.EntityManagerFactory`; match the namespace to your project's dependency version.

`JpaTransactionManager` is commonly used alongside `JpaItemWriter`, Spring Data JPA repositories, and `@Transactional` services sharing the same persistence unit.

## 3. Wiring the right transaction manager into chunk()

In Spring Batch 5, `StepBuilder` accepts `JobRepository`, and the chunk transaction manager is passed to `chunk(commitInterval, transactionManager)`:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager jpaTransactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(200, jpaTransactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

If the application has multiple `PlatformTransactionManager` beans, inject with `@Qualifier` instead of relying implicitly on parameter names or `@Primary`:

```java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        @Qualifier("jpaTransactionManager")
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(200, transactionManager)
            .reader(reader)
            .writer(writer)
            .build();
}
```

`chunk(200, transactionManager)` means each chunk of up to 200 items is processed within a transaction managed by that manager. The commit interval is not a commit count per individual Writer call; all JPA changes participating in that transaction commit together at chunk boundaries.

## 4. Combining JpaItemWriter with JpaTransactionManager

`JpaItemWriter<T>` writes items to the database through an `EntityManager`. It requires the `EntityManagerFactory` matching the Step's `JpaTransactionManager`.

Builder example:

```java
import jakarta.persistence.EntityManagerFactory;

import org.springframework.batch.item.database.JpaItemWriter;
import org.springframework.batch.item.database.builder.JpaItemWriterBuilder;
import org.springframework.context.annotation.Bean;

@Bean
public JpaItemWriter<Order> orderJpaWriter(
        EntityManagerFactory entityManagerFactory) {

    return new JpaItemWriterBuilder<Order>()
            .entityManagerFactory(entityManagerFactory)
            .usePersist(false)
            .build();
}
```

Under this configuration, the Writer uses `merge` by default (`usePersist(false)`). `merge` fits when items may be detached entities needing synchronization into the persistence context. If all items are brand-new entities without an existing identity in the persistence context, you can set `usePersist(true)` to call `persist`.

Do not choose `persist` purely for faster writes. If an entity already exists or already has an identity in the database, `persist` can cause entity-already-exists or key violation errors. Clarify whether items are new entities or updates.

`JpaItemWriter` flushes the persistence context as configured before returning from write. Flushing dispatches SQL statements over the database connection, yet the transaction still does not commit until the transaction manager commits the chunk. If an exception occurs after flush but before commit, the database can still roll back changes in the transaction.

## 5. How do persist and merge differ?

These two operations have different semantics:

| Operation | Used for | Behavior |
|---|---|---|
| `EntityManager.persist(entity)` | New, transient entities | Places that exact instance into the persistence context for insertion at flush/commit. |
| `EntityManager.merge(entity)` | Detached entities or state needing synchronization | Copies state into a managed instance; the return value is the managed instance. |

A common pitfall is assuming `merge()` turns the passed-in object into a managed object. It returns a separate managed object or corresponding managed instance. If code keeps mutating the original object after `merge`, those changes are not guaranteed to be synchronized as expected.

For data imports, if every record represents a new entity, `persist` can be used. If records may update existing entities, use `merge` or, better yet, look up the entity by business key and update permitted fields.

`merge` does not automatically guarantee business idempotency. If each retry creates a new entity with a new ID, the database can still accumulate duplicates. Enforce unique constraints on business keys and define explicit insert/update rules.

## 6. Configuring JpaPagingItemReader and the JPA transaction manager

Spring Batch provides `JpaPagingItemReader` to read JPA data page by page. Example:

```java
import jakarta.persistence.EntityManagerFactory;

import org.springframework.batch.item.database.JpaPagingItemReader;
import org.springframework.batch.item.database.builder.JpaPagingItemReaderBuilder;
import org.springframework.context.annotation.Bean;

@Bean
public JpaPagingItemReader<SourceOrder> sourceOrderReader(
        EntityManagerFactory entityManagerFactory) {

    return new JpaPagingItemReaderBuilder<SourceOrder>()
            .name("sourceOrderReader")
            .entityManagerFactory(entityManagerFactory)
            .queryString("select o from SourceOrder o order by o.id")
            .pageSize(200)
            .saveState(true)
            .build();
}
```

The query needs a deterministic, unique ordering—typically `ORDER BY` on the primary key. Without deterministic ordering, data can shift between pages; restarts or paging can skip or duplicate items.

`JpaPagingItemReader` manages page-based reading and the Reader's persistence context. Consult the documentation for your version regarding the `transacted` option and detached entity state after reading. If the Processor needs to modify entities or access lazy associations, clarify whether entities remain managed or are detached; never rely on Open Session in View in batch jobs.

Reader and Writer can share the same `EntityManagerFactory` when reading and writing in the same persistence unit. If reading from a source persistence unit and writing to a separate target persistence unit, see the multiple persistence units section below.

## 7. EntityManagerFactory and transaction manager must match the same persistence unit

This relationship must be consistent:

```text
EntityManagerFactory (ordersEntityManagerFactory)
             |
             v
JpaTransactionManager (ordersTransactionManager)
             |
             v
Step.chunk(..., ordersTransactionManager)
             |
             v
JpaItemWriter uses ordersEntityManagerFactory
```

When multiple `EntityManagerFactory` beans exist, never inject default beans ambiguously. Name and qualify them explicitly:

```java
@Bean("ordersTransactionManager")
PlatformTransactionManager ordersTransactionManager(
        @Qualifier("ordersEntityManagerFactory")
        EntityManagerFactory entityManagerFactory) {
    return new JpaTransactionManager(entityManagerFactory);
}
```

The Writer must also use the matching factory:

```java
@Bean
JpaItemWriter<Order> orderWriter(
        @Qualifier("ordersEntityManagerFactory")
        EntityManagerFactory entityManagerFactory) {
    return new JpaItemWriterBuilder<Order>()
            .entityManagerFactory(entityManagerFactory)
            .build();
}
```

When a Writer uses a different factory than the Step's transaction manager, JPA operations can open a separate persistence context/transaction or miss the chunk transaction entirely. This leaves unprotected changes out of rollbacks when the application expects protection.

## 8. Multiple transaction managers: distinguishing JobRepository and chunk

Spring Batch has two transaction groups to distinguish:

- `JobRepository` transactions for saving `JobExecution`, `StepExecution`, and `ExecutionContext`.
- Chunk transactions for governing business read/process/write operations.

If metadata uses a dedicated JDBC datasource while business data uses JPA, there may be two transaction managers:

```text
Batch metadata database
  batchDataSource
       |
       v
  batchTransactionManager
       |
       v
  JobRepository

Business JPA database
  businessEntityManagerFactory
       |
       v
  jpaTransactionManager
       |
       v
  Step.chunk(..., jpaTransactionManager)
```

Example Batch infrastructure configuration in Spring Batch 5:

```java
@Configuration
@EnableBatchProcessing(
        dataSourceRef = "batchDataSource",
        transactionManagerRef = "batchTransactionManager")
public class BatchInfrastructureConfig {
}
```

Meanwhile, the business Step receives `jpaTransactionManager` in `chunk(...)`. `transactionManagerRef` on `@EnableBatchProcessing` specifies the transaction manager for Batch infrastructure/`JobRepository`; it does not automatically replace the transaction manager passed to each chunk Step.

If metadata and business data live in two separate databases, their local transactions do not automatically commit or roll back atomically together. Business data may commit while checkpoint metadata fails to save, or vice versa. Writers need idempotency and the system needs a reconciliation strategy; if cross-database atomicity is mandatory, use a distributed transaction mechanism such as JTA/XA.

## 9. Using Spring Data JPA repositories in a Processor or service

A Processor or service invoked within a chunk may use a Spring Data JPA repository. If the repository and Step share `JpaTransactionManager` on the same persistence unit, repository calls with default `REQUIRED` propagation join the active transaction.

Example:

```java
@Service
public class OrderImportService {

    private final ImportedOrderRepository repository;

    public OrderImportService(ImportedOrderRepository repository) {
        this.repository = repository;
    }

    public void save(Order order) {
        repository.save(order);
    }
}
```

If a service is called from a Writer or Processor inside a chunk, ensure the repository uses the same `EntityManagerFactory` and transaction manager. Do not open an independent transaction per item if operations must commit with the chunk.

If the service declares `@Transactional`, specify the manager explicitly when multiple managers exist:

```java
@Transactional(transactionManager = "jpaTransactionManager")
public void updateOrder(Order order) {
    repository.save(order);
}
```

`REQUIRED` propagation typically joins the active chunk transaction. `REQUIRES_NEW` starts an independent transaction; if used unintentionally, data can commit even when the outer chunk rolls back. That breaks chunk-level atomicity expectations.

## 10. Flush does not mean commit

JPA uses the persistence context to track changes. When `flush()` is called, Hibernate/JPA synchronizes changes as SQL statements to the database. Yet the transaction still has not committed.

```text
EntityManager.persist(order)
        |
        v
Entity in persistence context
        |
        v
EntityManager.flush()
        |
        v
SQL INSERT sent to database
        |
        v
Transaction commit
        |
        v
Changes committed
```

If a constraint violation occurs during flush, the exception surfaces before commit. If flush succeeds but a subsequent item fails, the transaction can still roll back.

Do not call `EntityManager.getTransaction().commit()` inside a Writer when Spring manages transactions. Doing so conflicts with the transaction manager and can cause `TransactionRequiredException`, inconsistent transaction state, or commits outside the chunk boundary.

## 11. Persistence context and chunk size

The persistence context tracks loaded or modified entities. With large chunks, managed entity counts can climb and consume significant memory. `JpaItemWriter` has an option to clear the persistence context after writing; consider this when batches process large item volumes.

Example:

```java
@Bean
JpaItemWriter<Order> orderWriter(EntityManagerFactory entityManagerFactory) {
    return new JpaItemWriterBuilder<Order>()
            .entityManagerFactory(entityManagerFactory)
            .usePersist(false)
            .build();
}
```

If you need tighter persistence context control, configure the writer per your Spring Batch version's API or use a custom Writer managing `flush()`/`clear()` inside the transaction. Do not clear the persistence context while entities still need to be accessed as managed objects within the same chunk.

Chunk size must balance throughput, memory, lock hold time, and rollback scope. Overly large chunks create bloated persistence contexts and long transactions. Overly small chunks increase commit frequency and metadata overhead.

## 12. Combining JPA and JdbcTemplate on the same database

A Step may use JPA for one part and JDBC for another. When both access the same database, they can coordinate in a single transaction if `JpaTransactionManager` is configured with the appropriate datasource and JDBC code obtains connections via Spring mechanisms like `JdbcTemplate`/`DataSourceUtils`.

Example:

```java
@Bean
JdbcTemplate businessJdbcTemplate(
        @Qualifier("businessDataSource") DataSource dataSource) {
    return new JdbcTemplate(dataSource);
}

@Bean
PlatformTransactionManager jpaTransactionManager(
        EntityManagerFactory entityManagerFactory) {
    return new JpaTransactionManager(entityManagerFactory);
}
```

`EntityManagerFactory` must bind to the same `businessDataSource`. `JpaTransactionManager` can expose a JDBC connection synchronized with the JPA transaction when the datasource is recognized/configured and `JpaDialect` supports it. If the datasource is not auto-detected, configure the datasource explicitly on the transaction manager using the appropriate API.

Never call `DriverManager.getConnection()` or open standalone connections inside a Writer if JDBC statements must join the current JPA transaction. Manually opened connections are not managed by `JpaTransactionManager` and can commit independently.

If JPA and JDBC use two different datasources, they do not share a transaction merely by running inside the same Step. Split them into separate Steps or use a distributed transaction/consistency pattern.

## 13. Multiple EntityManagerFactories or multiple databases

`JpaTransactionManager` manages one `EntityManagerFactory`. If an application has a source persistence unit and a target persistence unit, it normally declares two factories and two transaction managers:

```text
sourceEntityManagerFactory
       |
       v
sourceJpaTransactionManager

targetEntityManagerFactory
       |
       v
targetJpaTransactionManager
```

A Step reading from source and writing to target can assign the target's transaction manager to the chunk while the Reader reads using the source factory. However, the target transaction does not automatically govern the source's read transaction. If a consistent snapshot across both databases is required, use a snapshot/watermark mechanism or an appropriate distributed transaction.

You cannot pass two independent `JpaTransactionManager` instances into one `chunk(...)` to automatically commit both. If both databases must commit/roll back atomically together, use JTA/XA with XA-capable resources and a properly configured transaction coordinator. If eventual consistency is acceptable, use an outbox, idempotency keys, retries, and reconciliation.

## 14. Rollback and retry when using a JPA Writer

When a JPA Writer throws an exception in a chunk, the transaction manager rolls back the chunk transaction. Uncommitted JPA changes are undone. If the Step is configured with retry, items/chunks can be reprocessed according to policy.

Example retry configuration for transient database errors:

```java
return new StepBuilder("saveOrdersStep", jobRepository)
        .<Order, Order>chunk(100, jpaTransactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderJpaWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
```

Retry only exceptions likely to be transient. Constraint violations from invalid data generally will not clear on retry. If you want to skip business errors, classify specific exceptions and set a skip limit.

When a chunk retries or a Job restarts, the same business item can reach the Writer again. Use unique constraints, upserts, or lookups by business key to prevent duplicates. Never rely on a freshly generated entity ID per attempt to identify the same business record.

## 15. Restart and JobRepository with JPA

Restart requires durable metadata from `JobRepository` and checkpoints saved at Step commit boundaries. With JPA Readers/Writers, ensure:

1. `JobRepository` uses a durable database.
2. The Reader implements `ItemStream` and enables `saveState(true)` when checkpointing is needed.
3. Reader/Writer names stay stable across runs.
4. Identifying `JobParameters` remain identical when restarting the same `JobInstance`.
5. The data source has stable ordering or a fixed snapshot.
6. The Writer is idempotent to handle re-processing of uncommitted chunks or metadata/business transaction divergence.

If the metadata database and business database differ, their commits may not be atomic. This is why idempotency remains necessary even when the Reader saves checkpoints properly.

Never manually edit `BATCH_*` tables to reset checkpoints or transaction statuses. Use Spring Batch APIs like `JobOperator`, `JobExplorer`, and controlled operational procedures.

## 16. Testing the transaction manager for a JPA Step

Write integration tests against a real database or suitable Testcontainers instance to confirm the transaction manager actually governs JPA changes.

Useful test scenarios:

1. **Chunk commit:** Writer saves entities; once the chunk succeeds, verify data exists in the database.
2. **Chunk rollback:** Make the Writer throw an exception after persisting several entities; verify none of the failing chunk's changes are committed.
3. **Retry:** Simulate a transient error on the first attempt and success on retry; verify no duplicates in the final result.
4. **Restart:** Fail the Job after several committed chunks, restart the same `JobInstance`, and verify the Reader resumes from the exact checkpoint.
5. **Qualifier:** With multiple transaction managers, verify the Step uses the manager for the right `EntityManagerFactory`.
6. **JPA and JDBC in the same transaction:** Verify JDBC updates roll back alongside JPA updates when sharing the same datasource and properly configured manager.
7. **REQUIRES_NEW:** If a service uses this propagation, verify explicitly which data stays committed when the outer chunk rolls back.
8. **Multiple databases:** Test single-resource failure and verify XA or reconciliation matches the design.

Conceptual rollback test:

```java
assertEquals(BatchStatus.FAILED, jobExecution.getStatus());
assertEquals(0, orderRepository.countByBatchId(failedBatchId));
```

Tests must ensure the failure occurs within the same chunk and verification queries execute after the transaction completes. If earlier chunks already committed, verify only that the failing chunk's data rolled back; do not expect the entire Job to erase data from earlier successful chunks.

## 17. Common pitfalls

| Mistake | Consequence | Resolution |
|---|---|---|
| Using `DataSourceTransactionManager` for a JPA Writer without JPA coordination | `EntityManager` may not join the chunk transaction as expected. | Use `JpaTransactionManager` for the matching `EntityManagerFactory`. |
| Step uses the transaction manager of a different persistence unit | JPA Writer may commit outside the Step transaction. | Use `@Qualifier` and pair matching factory and manager. |
| Confusing Batch infrastructure `transactionManagerRef` with chunk TM | Step may run with the wrong transaction manager. | Pass the business manager explicitly to `chunk(...)`. |
| Calling `EntityManager.getTransaction().commit()` manually | Conflicts with Spring-managed transactions. | Let the Step transaction manager handle commit and rollback. |
| Unintended `REQUIRES_NEW` propagation | Partial data commits even when the outer chunk rolls back. | Use `REQUIRED` propagation when the chunk transaction must wrap it. |
| Confusing flush with commit | SQL has been sent, yet the transaction can still roll back. | Understand flush and commit are two distinct steps. |
| Using `persist` for existing entities | Can cause entity/duplicate key errors. | Choose `persist` for new entities and `merge`/update for detached/existing ones. |
| Persistence context growing too large | Consumes memory and lengthens transactions. | Tune chunk size and flush/clear strategy. |
| Two `EntityManagerFactory` beans with one `JpaTransactionManager` | Manager coordinates only one persistence unit. | Declare separate managers or use JTA/XA if atomicity is required. |
| Missing business key deduplication | Retries/restarts can insert duplicate records. | Enforce unique constraints, upserts, and idempotency. |

## Conclusion

`JpaTransactionManager` manages JPA transactions for an `EntityManagerFactory`. In Spring Batch 5, pass the right manager to `StepBuilder.chunk(...)` and ensure `JpaItemWriter` uses the matching factory. `flush()` only synchronizes SQL, while commit and rollback remain controlled by the transaction manager at chunk boundaries. When multiple transaction managers exist, clearly separate the `JobRepository` manager from business data managers; local transactions across multiple databases are not automatically atomic. Combine checkpoints, business keys, unique constraints, and idempotent Writers for safe restarts, and test commit, rollback, retry, and restart against the actual database engine your application uses.
