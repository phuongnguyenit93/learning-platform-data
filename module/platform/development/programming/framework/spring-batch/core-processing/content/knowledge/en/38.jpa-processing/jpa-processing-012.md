# Testing JPA Batch

Spring Batch can use JPA to read entities page by page, process data, and write entities back to the database. When a job runs over large datasets, testing a single repository or standalone query is not enough. You must test how the reader paginates, how the processor transforms entities, how the writer flushes data, how transactions commit per chunk, and how restart state is persisted in `JobRepository`.

**Testing JPA batch** means verifying the behavior of JPA components across a Spring Batch pipeline, from reader to writer and the actual database. A solid test suite typically has three layers:

- Unit tests for processors and mapping logic, without a database.
- Integration tests for JPA readers/writers and repositories against a test database.
- Job/step integration tests verifying chunks, transactions, skips, restarts, and final persisted outcomes.

The most error-prone area is transaction and persistence context boundaries. Tests might read an entity from the first-level cache even though data was never committed; or a test method might open its own transaction so setup fixtures remain invisible to the job's transaction. Therefore, deliberately control when fixtures are seeded, flushed, cleared, and committed before launching the job.

## 1. Goals of JPA batch testing

A JPA job typically follows this structure:

```mermaid
flowchart LR
    A[Database input] --> B[JpaPagingItemReader]
    B --> C[ItemProcessor]
    C --> D[JpaItemWriter]
    D --> E[Database output]
    E --> F[Verify persisted state]
```

Questions tests should answer:

- Does the reader fetch all records without missing any across page boundaries?
- Are JPQL, parameter bindings, and sort ordering correct?
- Does the processor transform fields or filter items as required?
- Does the writer insert/update the right entities and flush constraints properly?
- Do chunks commit/roll back cleanly when an item fails?
- Are generated IDs, relationships, and foreign keys persisted properly?
- Can the job restart from a checkpoint without duplicating or dropping records?
- Is the result accurate when re-read from the database using a fresh persistence context?

Tests must not assert only that `JobExecution` has `BatchStatus.COMPLETED`. A job can finish yet write wrong counts, wrong values, or missing relationships.

## 2. Three recommended test layers

| Test layer | Components | Goal |
|---|---|---|
| Unit tests | Processors, mappers, business rules | Verify pure logic and edge cases |
| Component integration tests | `JpaPagingItemReader`, `JpaItemWriter`, repositories | Verify JPA queries, mappings, and persistence |
| Batch integration tests | Job/Step with database | Verify chunks, transactions, listeners, skips, and restarts |

Unit tests run fast without a Spring context. Component integration tests use a test database to verify real mappings. Batch integration tests load the real job configuration and execute via `JobLauncherTestUtils` or `JobLauncher`.

Do not boot an entire job merely to test a calculation inside a processor. Conversely, you cannot prove restart or commit behavior with a unit test invoking a processor directly.

## 3. Dependencies for Spring Batch testing

With Gradle, add the Spring Batch test module in test scope:

```groovy
dependencies {
    testImplementation("org.springframework.batch:spring-batch-test")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

If the project manages versions via Spring Boot dependency management or the Spring Batch BOM, do not pin a version that diverges from runtime. Test libraries must match the Spring Batch version in use.

Commonly used utilities:

- `SpringBatchTest`: registers test support for Spring Batch.
- `JobLauncherTestUtils`: launches jobs or individual steps in tests.
- `JobRepositoryTestUtils`: cleans execution metadata in tests.
- `StepScopeTestExecutionListener` and `JobScopeTestExecutionListener`: support scoped beans in tests.
- `StepScopeTestUtils`: executes code inside a simulated `StepExecutionContext`.

In non-Spring-Boot projects, configure `ApplicationContext` and Batch infrastructure using your application's setup. Test utilities do not automatically create a datasource, `JobRepository`, or transaction manager for an unconfigured context.

## 4. Testing processors without a database

Processors should be tested independently when logic does not depend on JPA. Example order-status processor:

```java
public class OrderProcessor
        implements ItemProcessor<OrderEntity, OrderEntity> {

    @Override
    public OrderEntity process(OrderEntity item) {
        if (item.getAmount().signum() <= 0) {
            throw new InvalidOrderException("amount must be positive");
        }

        item.setStatus(OrderStatus.PROCESSED);
        return item;
    }
}
```

Unit test:

```java
class OrderProcessorTest {

    private final OrderProcessor processor = new OrderProcessor();

    @Test
    void marksValidOrderAsProcessed() throws Exception {
        OrderEntity input = new OrderEntity();
        input.setAmount(new BigDecimal("125.50"));
        input.setStatus(OrderStatus.NEW);

        OrderEntity result = processor.process(input);

        assertSame(input, result);
        assertEquals(OrderStatus.PROCESSED, result.getStatus());
    }

    @Test
    void rejectsNonPositiveAmount() {
        OrderEntity input = new OrderEntity();
        input.setAmount(BigDecimal.ZERO);

        assertThrows(
                InvalidOrderException.class,
                () -> processor.process(input));
    }
}
```

This test validates business rules without needing an `EntityManager`. If the processor calls repositories, clocks, or external services, inject them via constructor and mock/fake them in unit tests.

## 5. Entity model used in examples

Example entity with an identity key and business fields:

```java
@Entity
@Table(name = "orders")
public class OrderEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "source_ref", nullable = false, unique = true)
    private String sourceRef;

    @Column(nullable = false, precision = 18, scale = 2)
    private BigDecimal amount;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    // Constructors, getters and setters
}
```

With real entities, tests must use the application's actual mappings, column constraints, enum strategies, and relationships. Creating Java objects without persisting them never tests schema alignment or JPA provider behavior.

Use production-like schema migrations whenever possible. Hibernate auto-generated schemas are convenient for quick tests, but miss discrepancies between entity mappings and actual migrations.

## 6. Testing JpaPagingItemReader

`JpaPagingItemReader` reads entities via JPQL and slices results into pages. Reader tests should verify:

- JPQL returns the expected subset of records.
- Parameter binding works accurately.
- Page size is honored.
- Page boundaries neither drop nor duplicate items.
- Sort order is deterministic.
- The reader opens, reads, updates state, and closes according to lifecycle.

Example configuration:

```java
@Bean
JpaPagingItemReader<OrderEntity> orderReader(
        EntityManagerFactory entityManagerFactory) {

    return new JpaPagingItemReaderBuilder<OrderEntity>()
            .name("orderReader")
            .entityManagerFactory(entityManagerFactory)
            .queryString("""
                    select o
                    from OrderEntity o
                    where o.status = :status
                    order by o.id
                    """)
            .parameterValues(Map.of(
                    "status",
                    OrderStatus.NEW))
            .pageSize(2)
            .saveState(true)
            .build();
}
```

A page size of 2 forces even a small test with three or more records to cross multiple pages. Sorting on a unique key keeps ordering stable across pages.

For paging queries, never omit `ORDER BY` when tests or jobs depend on ordering. When sorting by a non-unique column, add the primary key as a tie-breaker.

## 7. Testing the reader directly

You can test a reader without launching a full job by opening the stream, reading to exhaustion, and closing it:

```java
@Test
void readsAllMatchingOrdersAcrossPages() throws Exception {
    seedCommittedOrders();

    JpaPagingItemReader<OrderEntity> reader = createOrderReader();
    reader.afterPropertiesSet();

    ExecutionContext context = new ExecutionContext();
    reader.open(context);

    List<Long> ids = new ArrayList<>();
    try {
        OrderEntity item;
        while ((item = reader.read()) != null) {
            ids.add(item.getId());
        }
    } finally {
        reader.close();
    }

    assertEquals(List.of(1L, 2L, 3L), ids);
}
```

This is an illustrative skeleton; actual IDs in tests should be captured from persisted fixtures rather than assuming sequences always start at 1.

Because the reader is an `ItemStreamReader`, call `open` before reading and `close` afterward. To test restarts directly, retain the `ExecutionContext` after several reads, close the reader, instantiate a new reader, and open it with the saved context per lifecycle rules.

## 8. Seeded data must commit before the job reads

A common mistake is inserting fixtures inside a test transaction and launching the job right away. The job may run in a separate transaction that cannot see the test's uncommitted data.

Example:

```java
transactionTemplate.executeWithoutResult(status -> {
    entityManager.persist(newOrder("SRC-1001"));
    entityManager.persist(newOrder("SRC-1002"));
    entityManager.flush();
});

JobExecution execution = jobLauncherTestUtils.launchJob(parameters);
```

`TransactionTemplate` commits when the callback finishes without error. The job can then read those rows from its own transaction.

When using `TestEntityManager` under `@DataJpaTest`, remember test slices normally run in a transaction that rolls back after the test. A reader using a different `EntityManager` may not see uncommitted fixtures. Seed via a separate committed transaction or design the test setup to fit the goal.

Do not assume that sharing the same JVM or `DataSource` makes uncommitted data visible across every `EntityManager`. Isolation levels and transaction boundaries govern visibility.

## 9. Testing JpaItemWriter

`JpaItemWriter` writes items via a JPA `EntityManager`. The builder takes an `EntityManagerFactory` and can be configured to use `persist` instead of `merge` depending on item types and entity lifecycles.

Example:

```java
@Bean
JpaItemWriter<OrderEntity> orderWriter(
        EntityManagerFactory entityManagerFactory) {

    return new JpaItemWriterBuilder<OrderEntity>()
            .entityManagerFactory(entityManagerFactory)
            .build();
}
```

Writer tests should verify:

- Entities are inserted or updated according to desired semantics.
- Generated IDs are assigned on flush/commit when using identity generation.
- Relationships and cascades operate per mappings.
- Constraint violations surface at the expected flush/commit boundary.
- No duplicates are written from misusing `persist`/`merge`.

`JpaItemWriter` must execute within a step transaction or an explicit test transaction. Invoking the writer outside a transaction does not reflect real step execution.

## 10. Persist and merge must be tested accurately

JPA distinguishes two operations:

- `persist` is for new, unmanaged entities.
- `merge` copies entity state into a managed instance and returns that managed instance.

`JpaItemWriterBuilder` provides `usePersist` to pick the desired behavior. Clarify whether items are brand-new entities or existing keyed entities needing updates.

Example:

```java
new JpaItemWriterBuilder<OrderEntity>()
        .entityManagerFactory(entityManagerFactory)
        .usePersist(true)
        .build();
```

Enable `persist` only when inputs are genuinely new entities without key conflicts. When items represent detached entities needing updates, `merge` is usually the right choice.

Do not merely assert that the object passed into the writer now has an ID after `write`. With `merge`, JPA may return a separate managed copy; the input object is not necessarily updated identically to the managed instance. Re-query the database to verify final state.

## 11. Flush and clear when verifying results

JPA uses a persistence context (first-level cache). An entity that was already loaded or persisted may stay in memory, causing tests to read cached state instead of actual database state.

When verifying in tests:

1. Flush to push pending changes to the database.
2. Clear the `EntityManager` or open a new `EntityManager`.
3. Re-query the data.

Example:

```java
entityManager.flush();
entityManager.clear();

OrderEntity saved = entityManager.find(OrderEntity.class, orderId);
assertEquals(OrderStatus.PROCESSED, saved.getStatus());
```

In Spring Boot tests, `TestEntityManager.flush()` and `clear()` work well inside JPA slice tests. For job integration tests, query via repositories or `JdbcTemplate` after the job commits.

Flushing is not committing. Constraints may be checked at flush, yet the transaction can still roll back later. When tests must confirm committed persistence, read in a new transaction after the job completes.

## 12. The first-level cache can mask bugs

Test example:

```java
OrderEntity order = entityManager.find(OrderEntity.class, id);
order.setStatus(OrderStatus.PROCESSED);

OrderEntity again = entityManager.find(OrderEntity.class, id);
assertEquals(OrderStatus.PROCESSED, again.getStatus());
```

This assertion does not prove the writer wrote to the database. The second `find` simply returns the exact same managed instance from the persistence context.

To verify real persistence:

```java
entityManager.flush();
entityManager.clear();

OrderEntity reloaded = entityManager.find(OrderEntity.class, id);
assertEquals(OrderStatus.PROCESSED, reloaded.getStatus());
```

Or open a new transaction and query using a repository or `JdbcTemplate` after the chunk transaction commits.

## 13. Transaction manager for JPA batch

JPA readers and writers require a matching `EntityManagerFactory` and compatible transaction semantics. The Step must use the transaction manager governing the persistence resource used by the writer.

In JPA setups, this is normally `JpaTransactionManager` for that `EntityManagerFactory`. When Batch metadata and business data use separate `DataSource`s, determine which transaction manager governs chunks and which governs `JobRepository`.

Checklist:

- `JpaItemWriter` uses the right `EntityManagerFactory`.
- The step's transaction manager manages the same persistence unit.
- Repositories and writers do not accidentally target a different `DataSource`.
- If atomicity between batch metadata and business data is needed, verify the real transaction configuration.
- When writing to multiple databases, never assume a single local transaction spans all of them.

Do not choose a transaction manager by bean name alone. Verify the actual injected bean type, `EntityManagerFactory`, and `DataSource`.

## 14. Why you should not casually put @Transactional on job tests

A test method annotated with `@Transactional` normally opens a test-framework transaction that rolls back at test end. Meanwhile, a chunk step manages its own transaction boundaries.

If a job launches inside a test-managed transaction:

- Uncommitted fixtures may be invisible to the job's transaction.
- The writer may join the outer transaction unexpectedly if on the same thread/manager.
- Assertions may execute before data actually commits.
- End-of-test rollback makes test behavior diverge from an independent production job.

For full job integration tests, it is usually much clearer to leave the test method non-transactional. Seed fixtures in an explicit committed transaction, launch the job, query results in a fresh transaction, and clean up deliberately.

For repository slice tests, `@Transactional` is convenient and appropriate because those tests target single repository calls inside one transaction.

## 15. How @DataJpaTest and @SpringBootTest differ

| Annotation | Scope | Best suited for |
|---|---|---|
| `@DataJpaTest` | JPA slice, entity/repository and database tests | Mappings, JPQL, repositories |
| `@SpringBootTest` | ApplicationContext close to real app | Jobs/steps, Batch infrastructure, JPA integration |
| `@SpringBatchTest` | Batch test utilities and scoped test support | Launching jobs/steps and test scopes |

JPA slice example:

```java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    private OrderRepository orderRepository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void findsOrdersByStatus() {
        entityManager.persistAndFlush(newOrder("SRC-1001"));

        List<OrderEntity> result =
                orderRepository.findByStatus(OrderStatus.NEW);

        assertEquals(1, result.size());
    }
}
```

This test does not prove the Spring Batch job works. Because `@DataJpaTest` is a slice, it may omit `Job`, `Step`, or Batch infrastructure beans.

For job integration tests, pair `@SpringBootTest` with `@SpringBatchTest` or equivalent Spring Test configuration. If combining a slice with Batch, explicitly import required configurations and know which beans the slice filters exclude.

## 16. Launching jobs with JobLauncherTestUtils

The Spring Batch test module provides `JobLauncherTestUtils` to run jobs from tests.

Example:

```java
@SpringBootTest
@SpringBatchTest
class JpaImportJobTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private Job importOrdersJob;

    @BeforeEach
    void configureJob() {
        jobLauncherTestUtils.setJob(importOrdersJob);
    }

    @Test
    void importsOrdersSuccessfully() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("run.id", UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution execution =
                jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertEquals(
                ExitStatus.COMPLETED.getExitCode(),
                execution.getExitStatus().getExitCode());
    }
}
```

When the application context defines multiple `Job` beans, `setJob` tells the utility which job to launch. `JobParameters` need a new identifying value whenever each test requires an independent `JobInstance`.

If the job requires mandatory parameters such as input file, batch ID, or business date, supply all of them. Do not add random parameters if those parameters alter queries or output paths in non-deterministic ways.

## 17. Launching a single step

When testing only one JPA step, use `launchStep`:

```java
JobExecution execution =
        jobLauncherTestUtils.launchStep(
                "importOrdersStep",
                new JobParametersBuilder()
                        .addString(
                                "run.id",
                                UUID.randomUUID().toString())
                        .toJobParameters());

assertEquals(BatchStatus.COMPLETED, execution.getStatus());
```

Launching a step isolates that step's reader, processor, writer, and transactions without executing the entire job flow.

However, if the step depends on `JobExecutionContext` data populated by an earlier step, seed that context in the test or run the full job. Never skip that dependency and conclude the step works standalone.

## 18. Checking StepExecution metrics

After running the job, inspect `StepExecution`:

```java
StepExecution stepExecution = execution.getStepExecutions()
        .stream()
        .filter(step -> step.getStepName().equals("importOrdersStep"))
        .findFirst()
        .orElseThrow();

assertEquals(3, stepExecution.getReadCount());
assertEquals(3, stepExecution.getWriteCount());
assertEquals(0, stepExecution.getReadSkipCount());
assertEquals(0, stepExecution.getProcessSkipCount());
assertEquals(0, stepExecution.getWriteSkipCount());
```

Useful counters:

- `readCount`: items returned by the reader.
- `writeCount`: items written per execution counters.
- `filterCount`: items filtered out by the processor returning `null`.
- `readSkipCount`: errors skipped while reading.
- `processSkipCount`: errors skipped while processing.
- `writeSkipCount`: errors skipped while writing.
- `commitCount` and `rollbackCount`: transaction commits and rollbacks for the step.

Expected metrics must match your fixture. When processors filter or steps skip/retry, assert each individual counter rather than checking totals alone.

## 19. Verifying data after the job using a fresh persistence context

Example after job completion:

```java
@Autowired
private JdbcTemplate jdbcTemplate;

@Test
void persistsProcessedOrders() throws Exception {
    seedCommittedOrders();

    JobExecution execution = launchImportJob();
    assertEquals(BatchStatus.COMPLETED, execution.getStatus());

    Integer count = jdbcTemplate.queryForObject(
            "select count(*) from orders where status = ?",
            Integer.class,
            "PROCESSED");

    assertEquals(3, count);
}
```

Querying with `JdbcTemplate` after the job reads committed database state instead of entities lingering in a test persistence context. You can also use a repository in a new transaction to assert domain objects and relationships.

If the test uses a JPA `EntityManager` directly, clear it or create a new `EntityManager` before re-querying. Never assert only against original object references passed through the processor.

## 20. Testing page boundaries

Paging readers must be tested with more records than `pageSize` so execution genuinely crosses multiple pages.

Example:

- Seed 5 entities with status `NEW`.
- Configure `pageSize = 2`.
- Exhaust the reader.
- Expect 5 items with zero duplicates and zero omissions.

Check:

| Page | Expected IDs |
|---|---|
| 1 | 1, 2 |
| 2 | 3, 4 |
| 3 | 5 |

IDs here are illustrative. Tests should capture real IDs from seeded fixtures or sort by a deterministically ordered source reference.

If page size is greater than or equal to total rows, the test never exercises page transitions. Pick a page size smaller than the record count and ensure at least one partial trailing page.

## 21. Testing JPQL and parameter binding

A reader might return the right count while using the wrong filter or parameter. Seed records in multiple states and verify only matching records are read.

JPQL example:

```java
select o
from OrderEntity o
where o.status = :status
  and o.createdAt < :cutoff
order by o.id
```

Tests should cover:

- Records matching both predicates.
- Records with a non-matching status.
- Records with `createdAt` past the cutoff.
- Records right on comparison boundaries.
- Records with nullable fields if the query handles nulls.

For JPQL with joins, fetch joins, or entity graphs, verify there are no duplicate root entities and no unintended N+1 queries. Collection fetch joins paired with pagination can have provider-specific semantics and performance pitfalls; test with fixtures having multiple child records.

## 22. Testing writer inserts and updates

`JpaItemWriter` can insert new entities or update detached entities depending on persist/merge configuration.

Write two separate test cases:

### Inserting new entities

- Initial ID is null when using generated identity.
- Writer inserts entities.
- Flush/commit creates rows.
- Re-query to verify IDs and fields.

### Updating existing entities

- Seed entities and commit.
- Obtain detached items or read entities appropriately.
- Mutate fields.
- Writer merges items.
- Re-query with a fresh `EntityManager` to confirm updates.

Do not mix both goals into one test when verifying explicit persist vs. merge semantics. An entity carrying an ID that does not exist in the database can behave differently from a brand-new entity and should be verified against your JPA provider.

## 23. Testing relationships and cascades

JPA batches often write entities with `ManyToOne`, `OneToMany`, or `ManyToMany` associations. Tests should verify:

- Foreign keys are written properly.
- Cascade types match entity lifecycles.
- Child entities are persisted as intended.
- Merging graphs does not create duplicate parents.
- `orphanRemoval` does not unintentionally delete children.
- Fetch strategies do not cause severe N+1 queries.

Example:

```java
@Entity
class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id")
    private OrderEntity order;
}
```

After the job runs, query the `order_line` table joined with `orders` to confirm every line references the right parent. Do not merely assert the collection on the original Java object, which may sit inside an old persistence context.

## 24. Testing constraints and flush errors

Certain JPA errors surface only at flush or commit:

- `NOT NULL` violations.
- Unique constraint violations.
- Foreign key violations.
- Column length/precision overflows.
- Optimistic locking conflicts.
- Invalid entity states.

Tests should intentionally feed a constraint-violating input to observe which phase throws the exception and whether the skip policy handles it properly.

For instance, if the writer flushes at chunk end, constraint failures may surface inside `write` or at transaction commit depending on the provider. Do not assume all database errors are thrown immediately on `persist`.

When a step uses a skip policy, verify the exact exception type seen by Spring Batch after exception translation/wrapping. Never broadly skip all `PersistenceException` errors if doing so could mask schema or infrastructure defects.

## 25. Testing skips and filters in a JPA step

Distinguish clearly:

- Processor returns `null`: filters the item and increments `filterCount`.
- Processor throws a skippable exception: process skip.
- Writer throws a skippable exception: write skip if the framework can isolate the offending item per configuration.
- Non-skippable constraint or infrastructure failure: step fails.

For writer errors, a batch write may hold multiple items. Depending on the writer and fault-tolerance mode, Spring Batch may roll back and scan to isolate the bad item. Tests should run against a real database or compatible dialect and verify exactly which records were committed and which were rejected.

If using a skip listener to persist rejected records, test the listener's transaction behavior and idempotency across chunk rollbacks and retries.

## 26. Testing chunk rollback

To verify transaction boundaries, build a test with a chunk containing valid items alongside one failing non-skippable item:

1. Reader returns items in the chunk.
2. Processor or writer throws an error.
3. Step rolls back the chunk.
4. Query the database in a new transaction.
5. Verify none of the failed chunk's changes exist.
6. Verify previously committed chunks remain intact.

Example:

```text
Chunk 1: items 1-2 -> commit
Chunk 2: items 3-4 -> rollback due to item 4 error
Chunk 3: not yet executed
```

Expected outcome: chunk 1's data persists in the database, chunk 2's data rolls back within its transaction, and chunk 3 was never processed.

Never verify rollback using entity objects retained in memory. Use a new transaction or JDBC query after the failing transaction finishes.

## 27. Testing restarts and ExecutionContext

`JpaPagingItemReader` supports saving state when `saveState` is enabled and the reader has a stable name. Restart tests must confirm the reader resumes from its checkpoint after a failure.

Scenario:

1. Seed more records than a single page.
2. Configure a small page size and chunk size.
3. Have a test writer or processor fail intentionally after several chunks commit.
4. Verify `StepExecution` persisted `ExecutionContext`.
5. Restart the same `JobInstance` using identical identifying `JobParameters`.
6. Verify the reader resumes at the right position.
7. Verify total output has zero missing or duplicate records.

Keep these stable across restarts:

- Reader name.
- Query and parameters.
- Sort order.
- Page size and pagination mechanism.
- Identifying `JobParameters`.
- Writer configuration and business keys.

If you alter the query, sort key, or source dataset between the initial run and restart, the saved checkpoint may no longer point to the right position.

## 28. Source data mutating during paging

Paging readers rely on queries and ordering to fetch consecutive pages. If source rows are inserted, deleted, or have sort keys modified while the job runs, page query results can shift.

Tests should simulate or enforce policies such as:

- Inputs locked by batch ID or business date.
- Unique, immutable sort keys.
- Isolation levels matching requirements.
- Source data remaining immutable during the processing window, or mutations handled by contract.

Do not assume `saveState` snapshots the data. `saveState` stores position/checkpoint state; dataset consistency depends on database transactions/isolation and query design.

## 29. Testing @StepScope and JobParameters

Readers and writers often use `@StepScope` to bind `JobParameters`:

```java
@Bean
@StepScope
JpaPagingItemReader<OrderEntity> orderReader(
        EntityManagerFactory entityManagerFactory,
        @Value("#{jobParameters['batchId']}") String batchId) {

    return new JpaPagingItemReaderBuilder<OrderEntity>()
            .name("orderReader")
            .entityManagerFactory(entityManagerFactory)
            .queryString("""
                    select o
                    from OrderEntity o
                    where o.batchId = :batchId
                    order by o.id
                    """)
            .parameterValues(Map.of("batchId", batchId))
            .pageSize(100)
            .saveState(true)
            .build();
}
```

When testing a scoped bean directly, an active `StepExecution` context is required for SpEL to resolve `jobParameters`. `@SpringBatchTest` registers `StepScopeTestExecutionListener`; you can also use `StepScopeTestUtils` to run code inside a test-created `StepExecution`.

Without a scope context, failures happen during bean lookup rather than when calling `read`. That is a test setup issue, not a JPQL error.

## 30. Testing a step-scoped reader with StepScopeTestUtils

Illustrative example:

```java
StepExecution stepExecution =
        MetaDataInstanceFactory.createStepExecution(
                new JobParametersBuilder()
                        .addString("batchId", "BATCH-100")
                        .toJobParameters());

List<OrderEntity> items =
        StepScopeTestUtils.doInStepScope(stepExecution, () -> {
            JpaPagingItemReader<OrderEntity> reader =
                    applicationContext.getBean("orderReader",
                            JpaPagingItemReader.class);

            reader.open(new ExecutionContext());
            try {
                List<OrderEntity> result = new ArrayList<>();
                OrderEntity item;
                while ((item = reader.read()) != null) {
                    result.add(item);
                }
                return result;
            } finally {
                reader.close();
            }
        });
```

This is an illustrative skeleton; bean names, generic types, and `StepExecution` construction must match your project. Seed records with the matching `batchId` and commit before the reader executes.

## 31. JobRepositoryTestUtils and cleanup

`JobRepositoryTestUtils` removes job/step execution metadata after tests:

```java
@Autowired
private JobRepositoryTestUtils jobRepositoryTestUtils;

@AfterEach
void cleanBatchMetadata() {
    jobRepositoryTestUtils.removeJobExecutions();
}
```

This utility cleans Spring Batch metadata; it does not delete business entities in `orders` or `order_lines`. Clean business tables separately in an order that respects foreign keys.

Example:

```java
@AfterEach
void cleanBusinessData() {
    jdbcTemplate.update("delete from order_lines");
    jdbcTemplate.update("delete from orders");
}
```

In projects running tests in parallel, never wipe entire shared tables while other tests may be running. Scope fixtures with unique batch/test IDs and delete only rows belonging to that test.

## 32. Choosing a test database: H2 or Testcontainers?

H2 works well for fast tests when queries, mappings, and DDL use compatible features. Yet in-memory databases differ from production engines in SQL dialect, type mapping, identity generation, locking, and constraints.

Testcontainers runs a real database engine in a container:

| Option | Advantages | Limitations |
|---|---|---|
| H2 | Fast, simple setup | Does not fully represent production SQL dialects |
| Testcontainers | Tests real database engine and JDBC driver | Slower, requires Docker/container runtime |
| Shared test database | Closer to integration environments | Requires strict data isolation and cleanup |

Whenever a job relies on native queries, sequences, identity columns, JSON columns, locking, or generated keys, run integration tests against the exact production database type and JDBC driver.

Never conclude from H2 passing that a JPQL or native query will behave identically on PostgreSQL, Oracle, SQL Server, or MySQL.

## 33. Using real migrations in integration tests

If production uses Flyway or Liquibase, execute those migrations in tests so schemas match production.

Verify:

- Column types and numeric precision.
- Primary keys, sequences, and identity columns.
- Unique and foreign key constraints.
- Indexes supporting paging queries.
- Default values and triggers.
- Enum and string representations.
- Schema versions.

Hibernate `ddl-auto=create-drop` is handy for simple entity tests, but it masks migration bugs and drift between entity mappings and production schemas.

## 34. Testing performance and N+1 queries

A functional test may pass while the reader runs slowly because of:

- Page sizes that are too small or too large.
- Queries missing indexes.
- Processors querying repositories per item.
- Lazy relationships triggering N+1 queries.
- Writers flushing too often or inappropriate chunk sizes.

Inspect SQL logs, Hibernate statistics, or datasource metrics in dedicated performance/integration tests. Avoid asserting brittle exact query counts if provider upgrades alter internal queries, unless query count is an explicitly governed contract.

N+1 example:

```java
for (OrderEntity order : orders) {
    String customerName = order.getCustomer().getName();
}
```

If `customer` is `LAZY` and was not fetched with the query, each access can issue an extra query. Use projections, entity graphs, or appropriate fetch strategies and measure across many items.

Do not blindly add collection fetch joins to paged queries. Joining collections multiplies root rows or forces in-memory pagination depending on the provider. Test SQL and outputs against fixtures with many child rows.

## 35. Testing optimistic locking and concurrent updates

When entities use `@Version`, tests must verify optimistic locking conflicts are handled per policy:

```java
@Version
private long version;
```

One transaction reads an old version; another transaction updates the entity and commits; the first transaction attempts to write and receives an optimistic locking exception.

In batch jobs:

- Classify whether conflicts are retryable, skippable, or step-failing.
- Inspect the concrete exception translated by the JPA provider/Spring.
- Confirm retries do not overwrite newer changes.
- Avoid endless retries when conflicts stem from continuous concurrent updates.

Concurrency tests need truly separate transactions and threads; a sequential unit test cannot simulate a real optimistic locking race.

## 36. Testing lazy loading and detached entities

`JpaPagingItemReader` manages its own `EntityManager` lifecycle and may return entities no longer managed by the reader's persistence context once a page is read. Code must not assume lazy relationships remain accessible inside the processor.

Tests should check:

- Does the processor touch lazy associations?
- Does the reader query fetch all required data?
- Should a DTO projection replace entities?
- Does `LazyInitializationException` occur during item processing?
- Does the writer's merge/persist strategy fit detached entities?

If the processor needs rich related data, use JPQL projections/DTOs or controlled fetch strategies. Avoid widening transactions or persistence contexts solely to hide inefficient query design.

## 37. Testing writer errors and constraint translation

JPA providers may wrap `SQLException` inside `PersistenceException`, `ConstraintViolationException`, or Spring-translated exceptions. Tests must verify the exact exception type received by the skip policy.

Example step skip configuration:

```java
.faultTolerant()
.skip(DataIntegrityViolationException.class)
.skipLimit(10)
```

Configure constraint-exception skipping only when business rules allow dropping offending records. If errors stem from schema mismatches, missing tables, or database outages, skipping hides systemic failures and finishes the job with missing data.

Test all of these:

- A single record violating a unique constraint.
- Multiple records in a chunk containing one bad record.
- Errors surfacing at flush/commit.
- Skip listener recording rejected items properly.
- Chunk rollback and reprocessing of valid items per policy.

## 38. Testing JobParameters and repeatability

Batch jobs use identifying `JobParameters` to identify a `JobInstance`. Running a test with the exact same identifying parameters a second time can raise `JobInstanceAlreadyCompleteException` if the job already completed.

Generate a fresh run ID or batch ID for each independent test case:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("batchId", "TEST-" + UUID.randomUUID())
        .toJobParameters();
```

For restart tests, conversely, reuse the exact identifying parameters from the failed run. Do not generate a new batch ID when the goal is resuming the same `JobInstance`.

When outputs or queries filter by `batchId`, seed fixtures with that exact value and verify the job does not read another batch's rows.

## 39. Structure of a full job integration test

Overall skeleton example:

```java
@SpringBootTest
@SpringBatchTest
class JpaOrderJobIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JobRepositoryTestUtils jobRepositoryTestUtils;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private Job importOrdersJob;

    @BeforeEach
    void setUp() {
        jobLauncherTestUtils.setJob(importOrdersJob);
        cleanBusinessRows();
        seedCommittedRows();
    }

    @Test
    void processesNewOrders() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("batchId", "TEST-ORDERS-01")
                .addString("run.id", UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution execution =
                jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());

        StepExecution step = execution.getStepExecutions()
                .stream()
                .filter(item ->
                        item.getStepName().equals("processOrdersStep"))
                .findFirst()
                .orElseThrow();

        assertEquals(3, step.getReadCount());
        assertEquals(3, step.getWriteCount());

        Integer processed = jdbcTemplate.queryForObject(
                """
                select count(*)
                from orders
                where batch_id = ?
                  and status = ?
                """,
                Integer.class,
                "TEST-ORDERS-01",
                "PROCESSED");

        assertEquals(3, processed);
    }

    @AfterEach
    void tearDown() {
        cleanBusinessRows();
        jobRepositoryTestUtils.removeJobExecutions();
    }

    private void cleanBusinessRows() {
        jdbcTemplate.update(
                "delete from orders where batch_id like 'TEST-%'");
    }

    private void seedCommittedRows() {
        // Seed in a separate committed transaction before launch.
    }
}
```

This is an illustrative skeleton. In real tests, cleanup must delete child tables before parent tables; fixtures must commit before launch; batch IDs must be unique per test; and query assertions must match your application schema.

## 40. Testing asynchronous job execution

`JobLauncherTestUtils` normally uses a synchronous launcher in simple test configurations, yet applications may configure an asynchronous task executor. In that case, `launchJob` can return a `JobExecution` before the job finishes.

With an asynchronous launcher:

- Do not assert `COMPLETED` immediately when `launchJob` returns.
- Wait for a terminal status with a bounded timeout.
- Avoid long fixed sleeps when polling conditions with timeouts can be used.
- On timeout, print `JobExecution`/`StepExecution` statuses and failure exceptions for diagnostics.

Ideally, configure a synchronous test launcher when testing final job outputs without needing async behavior. When async execution itself is a requirement, dedicate tests to that lifecycle.

## 41. Verifying JobRepository metadata and business data separately

`JobRepository` stores metadata such as `JobInstance`, `JobExecution`, `StepExecution`, and `ExecutionContext`. Business JPA entities live in application tables.

Both data groups need separate assertions and cleanup:

| Data | Storage location | How to verify |
|---|---|---|
| `JobExecution`/`StepExecution` | Batch metadata tables | `JobRepositoryTestUtils` or repositories |
| Business entities | JPA tables | Repositories, fresh `EntityManager`, or `JdbcTemplate` |
| Checkpoints | `ExecutionContext` | `StepExecution` execution context |
| Rejected/error records | Reject tables or error resources | Query by batch ID or source key |

`JobRepositoryTestUtils` does not clean up business tables. Similarly, deleting rows from `orders` does not remove `JobExecution` metadata.

## 42. Common pitfalls

**Asserting only JobExecution COMPLETED.** A job can complete while writing wrong data or wrong row counts. Assert `StepExecution` counters and database state too.

**Seeding fixtures in an uncommitted test transaction.** The job's transaction may not see the rows. Commit fixtures prior to launch.

**Re-querying within the same persistence context.** The first-level cache can hide unflushed or uncommitted data. Flush, clear, or query in a new transaction.

**Using @DataJpaTest to prove an entire job works.** JPA slices do not load Batch infrastructure automatically. Use `@SpringBootTest` and `@SpringBatchTest` for job integration.

**Failing to test multiple pages.** A page size larger than the entire fixture never crosses page boundaries. Seed more items than `pageSize`.

**Missing deterministic ORDER BY.** Paging produces nondeterministic order and undermines test/restart reliability. Sort by a unique key.

**Using a transaction manager that does not manage the writer's EntityManagerFactory.** Flushes/commits may miss the expected transaction. Check persistence unit and step wiring.

**Confusing flush with commit.** Flush sends SQL, yet the transaction can still roll back. Verify results from a fresh transaction.

**Failing to test persist and merge separately.** New and detached entities require different semantics. Pick `usePersist` per input lifecycle and test both inserts and updates.

**Using H2 for database-specific features.** Tests pass while production fails due to dialect/driver differences. Use Testcontainers for target databases.

**Ignoring lazy loading and N+1.** Jobs may produce correct results slowly or fail with `LazyInitializationException`. Test query strategies and needed associations.

**Restarting with new JobParameters.** That launches a new `JobInstance` instead of testing resume. Reuse the failed run's exact identifying parameters.

**Truncating whole tables during parallel tests.** One test can wipe another test's rows. Isolate fixtures by batch/test ID.

**Skipping every PersistenceException.** This can mask schema or infrastructure failures. Skip only classified record-level exceptions.

## 43. Workflow for building a JPA batch test suite

When adding a JPA-backed job, build tests in this order:

1. Unit tests for processors and pure mapping logic.
2. JPA repository tests for JPQL queries and constraints.
3. Reader tests with small page sizes and committed fixtures.
4. Writer tests for inserts, updates, relationships, and generated keys.
5. Step integration tests for chunks, transactions, filtering, and skipping.
6. Full job integration tests for parameters, flows, and final outputs.
7. Restart tests for `ExecutionContext` and checkpoints.
8. Database-specific tests using the target engine/driver when relying on engine-specific queries or features.
9. Performance tests for page size, chunk size, N+1 queries, and query plans when data scale demands it.

Not every small job requires every test layer at equal depth. However, jobs with restarts, rich relationships, or critical data always require explicit transaction and persisted-output testing.

## 44. Practical summary

Testing JPA batch jobs must validate both JPA behavior and Spring Batch lifecycles. Unit tests cover processors and business rules; repository/reader/writer tests validate JPQL, mappings, and persistence; job integration tests validate chunks, transactions, skips, restarts, and final outputs.

Pay close attention to persistence context and transaction boundaries: seed data in committed transactions before launch, flush/clear or query with a fresh `EntityManager` when verifying results, and avoid wrapping full job tests in `@Transactional` arbitrarily. Use small page sizes to exercise multiple pages, enforce deterministic sort keys, verify `StepExecution` counters, and assert business data in the database post-commit.

For features dependent on SQL dialects, sequences, identity columns, locking, or native queries, run tests against the production database engine and JDBC driver using Testcontainers or an equivalent integration environment. Once tests span the reader, processor, writer, transactions, and restarts, you gain confidence that the job not only finishes, but writes accurate data and recovers safely.
