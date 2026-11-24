# Testing Database Readers and Writers

In Spring Batch, database readers and writers are typically where the application interfaces directly with business data, so they must be tested at both the component level and the Job/Step level. Reader tests verify SQL queries, mapping, ordering, and checkpoints; writer tests verify parameter binding, batch updates, transactions, and constraints; integration tests verify components collaborate properly under the real transaction manager and `JobRepository`.

Tests that only mock `ItemReader` or `ItemWriter` do not prove JDBC queries and write statements actually work. Conversely, running only end-to-end Job tests can make mapping or boundary bugs hard to pinpoint. A sound strategy combines unit tests for mapping logic, database integration tests for readers/writers, and Spring Batch tests for chunk, restart, skip, and transaction behavior.

## 1. Goals When Testing Database Readers and Writers

A database reader can return the expected row count yet still return wrong data due to column mapping, filter predicates, or unstable ordering. A writer can report success yet write the wrong columns, miss parameters, fail to roll back with the chunk, or mishandle constraints under policy.

Common verification goals:

- Reader executes the expected SQL and binds the right parameters.
- `RowMapper` converts `ResultSet` rows into accurate objects.
- Results are returned in deterministic order.
- Reader handles empty datasets, nulls, and boundary data.
- Reader persists and restores checkpoints on restart.
- Writer binds the right properties into SQL statements.
- Batch inserts/updates affect the expected number of rows.
- Unique, foreign key, and check constraints are handled properly.
- Writer participates in the Step's transaction.
- Rollback leaves behind no data from a failed chunk.
- Job restart neither misses nor duplicates records.
- Skip/retry listeners and `ExecutionContext` reflect accurate outcomes.

Define data contracts clearly before writing tests: which keys are unique, which records may be absent, which ordering matters, and where a restart must resume.

## 2. Testing Layers

Not every test needs to launch an entire Job. Tests can be organized into three layers:

| Layer | Components | Goal |
|---|---|---|
| Unit test | `RowMapper`, parameter mapper, processor, routing rules | Verify small, deterministic Java logic |
| Database integration test | `JdbcCursorItemReader`, `JdbcPagingItemReader`, `JdbcBatchItemWriter` | Verify SQL, mapping, and JDBC driver behavior |
| Spring Batch integration test | `Job`, `Step`, `JobRepository`, transaction manager | Verify chunks, checkpoints, restart, skip, and lifecycle |

Unit tests fit logic that needs no database. For example, a mapper turning `ResultSet` into `Order` can be tested with a mocked `ResultSet`, though testing against a real database remains valuable for catching wrong column names or data types.

Database integration tests run SQL against a test database and inspect real persisted data. Spring Batch integration tests wire readers/writers into a Step to verify how the framework manages transactions and `ExecutionContext`.

## 3. Spring Batch Testing Dependencies

In Spring Batch 5, the standard test dependency is:

~~~xml
<dependency>
    <groupId>org.springframework.batch</groupId>
    <artifactId>spring-batch-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Spring Boot projects typically manage versions through dependency management/BOM. Without Boot, align `spring-batch-test` version with `spring-batch-core`.

Spring Batch Test provides utilities such as:
- `@SpringBatchTest` to register Batch test support components.
- `JobLauncherTestUtils` to launch Jobs or Steps.
- `JobRepositoryTestUtils` to clean up `JobExecution` metadata in tests.
- `StepScopeTestExecutionListener` and `JobScopeTestExecutionListener` for scoped beans in tests.
- `MetaDataInstanceFactory` to construct test metadata when needed.

Exact APIs can vary across Spring Batch versions. Verify your actual dependencies rather than mixing Spring Batch 4 snippets with Spring Batch 5.

## 4. Choosing a Test Database

You can use an embedded database like H2 or a database container close to production.

| Option | Advantages | Limitations |
|---|---|---|
| H2 | Fast startup, easy reset, good for simple SQL tests | Syntax, type, isolation, and driver differences vs. production |
| HSQLDB/Derby | Lightweight, embedded | Still differs from production databases |
| Testcontainers | Runs production-like engine and driver | Slower startup and requires Docker/compatible runtime |
| Shared test database | Can mirror internal environment | Requires schema/data isolation so parallel tests do not collide |

If production uses PostgreSQL, MySQL, Oracle, or SQL Server, critical tests for paging, cursors, batch updates, exception translation, and locking should run on that engine/driver or an equivalent environment.

H2 is great for fast feedback, but it does not prove PostgreSQL- or Oracle-specific SQL behaves identically. Never use H2 as proof of holdability, vendor error codes, or isolation semantics of another database.

## 5. Creating Repeatable Schemas and Test Data

Tests must control schema and input data. Each test must know the exact starting state of the database and expected end state.

You can create schemas using `schema.sql`:

~~~sql
DROP TABLE IF EXISTS orders;

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL
);
~~~

Test data:

~~~sql
INSERT INTO orders (id, customer_id, status, amount)
VALUES
    (101, 501, 'NEW', 125.50),
    (102, 502, 'NEW', 89.00),
    (103, 503, 'DONE', 210.00);
~~~

You can use `@Sql` to run scripts before tests:

~~~java
@SpringBootTest
@Sql(
    scripts = "/sql/orders-test-data.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
class OrderReaderIntegrationTest {
}
~~~

If scripts recreate schemas, clean up data or isolate schemas so tests do not depend on execution order. With shared databases, use separate schema/database names per test suite or controlled transaction isolation.

Never let tests depend on leftover data from previous runs. Running a test standalone or inside the full suite must yield identical results.

## 6. Using JdbcTemplate to Seed and Assert Data

`JdbcTemplate` is convenient for inserting fixtures and verifying results after readers/writers run:

~~~java
@Autowired
JdbcTemplate jdbcTemplate;

@BeforeEach
void setUp() {
    jdbcTemplate.update("delete from orders");
    jdbcTemplate.update("""
            insert into orders(id, customer_id, status, amount)
            values (?, ?, ?, ?)
            """,
            101L, 501L, "NEW", new BigDecimal("125.50"));
}
~~~

Asserting data:

~~~java
Integer count = jdbcTemplate.queryForObject(
        "select count(*) from orders where status = ?",
        Integer.class,
        "NEW");

assertEquals(1, count);
~~~

`JdbcTemplate` keeps tests focused on real data instead of mocking every JDBC call. When testing transactions, check whether `JdbcTemplate` uses the same `DataSource` as the Step's transaction manager.

Avoid sharing a single test transaction that accidentally hides Job commits/rollbacks. If a Job runs in its own transaction or thread, uncommitted test fixtures may be invisible to it. A clean pattern is seeding fixtures and committing before launching the Job.

## 7. Testing JdbcCursorItemReader Directly

`JdbcCursorItemReader` opens a cursor and reads sequentially through a `ResultSet`. You can test the reader standalone by calling `open`, reading repeatedly, checking items, and calling `close`.

Example:

~~~java
@Test
void readsOrdersInStableOrder() throws Exception {
    JdbcCursorItemReader<Order> reader =
            new JdbcCursorItemReaderBuilder<Order>()
                    .name("ordersReader")
                    .dataSource(dataSource)
                    .sql("""
                            select id, customer_id, status, amount
                            from orders
                            where status = ?
                            order by id
                            """)
                    .preparedStatementSetter(ps ->
                            ps.setString(1, "NEW"))
                    .rowMapper((rs, rowNum) -> new Order(
                            rs.getLong("id"),
                            rs.getLong("customer_id"),
                            rs.getString("status"),
                            rs.getBigDecimal("amount")))
                    .saveState(true)
                    .build();

    ExecutionContext context = new ExecutionContext();
    reader.open(context);

    try {
        Order first = reader.read();
        Order second = reader.read();
        Order end = reader.read();

        assertEquals(101L, first.getId());
        assertEquals(102L, second.getId());
        assertNull(end);
    } finally {
        reader.close();
    }
}
~~~

This is a direct component test; it does not exercise Step transaction/chunk orchestration. It is ideal for catching SQL errors, parameter binding bugs, `RowMapper` issues, and end-of-input handling.

If the reader is a `@StepScope` bean, initialize it within a Step scope test or use `StepScopeTestUtils`. Do not invoke a scoped bean proxy outside an active scope.

## 8. Verifying RowMapper

`RowMapper` determines how each `ResultSet` row becomes an object. Tests should verify all important fields, especially types prone to conversion bugs.

Examples:
- `BIGINT` to `long`/`Long`.
- `DECIMAL` to `BigDecimal`.
- `TIMESTAMP` to `LocalDateTime` or `Instant`.
- Nullable columns to wrapper types.
- Enums or status codes to domain enums.

Assert directly against test data:

~~~java
Order order = reader.read();

assertAll(
        () -> assertEquals(101L, order.getId()),
        () -> assertEquals(501L, order.getCustomerId()),
        () -> assertEquals("NEW", order.getStatus()),
        () -> assertEquals(
                new BigDecimal("125.50"),
                order.getAmount()));
~~~

For nullable columns, test SQL `NULL` cases as well. Avoid primitives when the database allows null and null carries business meaning; `ResultSet.getLong()` returns `0` for SQL `NULL`, so call `wasNull()` or use an appropriate mapping approach.

Tests should also check column aliases when SQL uses `AS`. Renaming an alias without updating `RowMapper` causes runtime errors even though the query itself executes cleanly.

## 9. Testing JdbcPagingItemReader

`JdbcPagingItemReader` reads page by page and requires a stable sort key so pagination neither skips nor duplicates records.

Tests should include:
- More records than `pageSize`.
- Records sitting on page boundaries.
- Duplicate sort key values if allowed by design.
- Query filters and parameters.
- A partial final page smaller than `pageSize`.
- An empty result set.

Conceptual configuration example:

~~~java
JdbcPagingItemReader<Order> reader =
        new JdbcPagingItemReaderBuilder<Order>()
                .name("ordersPagingReader")
                .dataSource(dataSource)
                .queryProvider(queryProvider)
                .parameterValues(Map.of("status", "NEW"))
                .pageSize(2)
                .rowMapper(orderRowMapper)
                .saveState(true)
                .build();
~~~

The query provider needs sort keys. Sorting only by `created_at` when multiple records share timestamps leaves ordering non-deterministic. Add a unique key as a tie-breaker, such as `(created_at, id)`.

Test across multiple pages to catch paging, query provider, and sort mapping bugs. Do not test only a single small page because many paging bugs surface only at page boundaries.

## 10. Verifying Sort Order and Stable Datasets

SQL guarantees no ordering without `ORDER BY`. Reader tests should assert explicit ordering and check results accordingly.

Example:
~~~sql
SELECT id, customer_id, status, amount
FROM orders
WHERE status = :status
ORDER BY id ASC
~~~

If the sort key is not unique, add secondary keys to create a total order. With paging readers, this is crucial because each page runs as a separate query.

If source data mutates while the Job runs, paging can encounter new records, deleted records, or changed sort keys. When a fixed input set is required, consider batch IDs, watermarks, snapshots, or staging tables.

Tests should simulate at least some source mutations if the application lets writers update the same table the reader reads. Exact behavior depends on database, isolation level, and reader query strategy.

## 11. Testing Reader Checkpoints

Readers implementing `ItemStream` can store position in `ExecutionContext`. Direct checkpoint tests verify the reader restores from saved state.

Test pattern:

~~~text
Reader run 1:
  open(empty context)
  read item 1
  read item 2
  update(context)
  close()

Reader run 2:
  open(same saved context)
  read item 3
  read item 4
  close()
~~~

Conceptual example:

~~~java
ExecutionContext context = new ExecutionContext();

reader.open(context);
assertEquals(101L, reader.read().getId());
assertEquals(102L, reader.read().getId());
reader.update(context);
reader.close();

reader.open(context);
assertEquals(103L, reader.read().getId());
reader.close();
~~~

Depending on reader and version, state may be a row count, key, or other internal data. Tests should not couple to internal key names unless the framework exposes them as a public contract. Verify that reopening resumes at the right next item.

For cursor readers, restart may reopen the query and skip/position to the checkpoint. For paging readers, checkpoints usually track page/current item state. Verify with real data and stable sort orders.

## 12. Testing JdbcBatchItemWriter

`JdbcBatchItemWriter` runs batch inserts/updates based on SQL and item mappings. Direct writer tests can open the writer with an `ExecutionContext`, write a chunk, close the writer, and query the database to verify.

Configuration example:

~~~java
@Bean
JdbcBatchItemWriter<Order> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    insert into orders(id, customer_id, status, amount)
                    values (:id, :customerId, :status, :amount)
                    """)
            .beanMapped()
            .assertUpdates(true)
            .build();
}
~~~

Test:

~~~java
@Test
void writesAllItems() throws Exception {
    JdbcBatchItemWriter<Order> writer = orderWriter(dataSource);
    ExecutionContext context = new ExecutionContext();

    writer.open(context);
    try {
        writer.write(new Chunk<>(List.of(
                new Order(201L, 601L, "NEW",
                        new BigDecimal("10.00")),
                new Order(202L, 602L, "NEW",
                        new BigDecimal("20.00")))));
    } finally {
        writer.close();
    }

    Integer count = jdbcTemplate.queryForObject(
            "select count(*) from orders where id in (201, 202)",
            Integer.class);

    assertEquals(2, count);
}
~~~

This direct test checks the SQL and binding. Transaction commit/rollback must be tested inside a Step with a transaction manager, since opening/closing the writer does not create chunk transactions.

In Spring Batch 5, `write` accepts `Chunk`; earlier versions accepted `List`. Adapt tests to your version.

## 13. Verifying Parameter Binding

A common bug is SQL parameter names mismatching item properties or map fields.

Example SQL:
~~~sql
INSERT INTO orders(id, customer_id, amount)
VALUES (:id, :customerId, :amount)
~~~

Items must expose `id`, `customerId`, and `amount` properties when using bean mapping. When using a custom `ItemSqlParameterSourceProvider`, tests must verify the provider builds the exact names and types.

Include tests for:
- `BigDecimal` with scale.
- Timestamps/timezones.
- SQL `NULL`.
- Strings with Unicode characters.
- Values at column length boundaries.
- Booleans/enums if the database uses specific column types.

Do not check only inserted row counts. Query back individual columns to ensure mappings were neither swapped nor rounded improperly.

## 14. Verifying Updates and assertUpdates

`JdbcBatchItemWriter` can execute `UPDATE` instead of `INSERT`. Example:

~~~sql
UPDATE orders
SET status = :status,
    amount = :amount
WHERE id = :id
~~~

Tests should verify:
- When the ID exists, exactly one row is updated.
- When the ID does not exist, behavior matches `assertUpdates`.
- No overly broad `WHERE` condition updates multiple rows.
- Unmodified columns remain intact.
- A chunk with multiple items updates the right records.

`assertUpdates(true)` instructs the writer to inspect updated row counts per its contract. When an item update affects zero rows, the writer can throw an exception. This differs from duplicate key errors and should be tested separately.

## 15. Verifying Unique Constraints and DuplicateKeyException

To test duplicates, seed an existing row and write an item with the same key. Verify the actual exception thrown by the writer/driver.

~~~java
@Test
void duplicatePrimaryKeyIsReported() {
    jdbcTemplate.update("""
            insert into orders(id, customer_id, status, amount)
            values (?, ?, ?, ?)
            """,
            301L, 701L, "NEW", new BigDecimal("15.00"));

    assertThrows(DataIntegrityViolationException.class, () ->
            writer.write(new Chunk<>(List.of(
                    new Order(301L, 702L, "NEW",
                            new BigDecimal("25.00"))))));
}
~~~

Exact exception classes depend on writer and database. If the Step skips `DuplicateKeyException`, tests on a production-like database must confirm that exact class is thrown. Never assert only a broad superclass and assume skip classification will work.

Besides primary keys, test other unique constraints. A duplicate external reference may carry different meaning than a duplicate primary key.

## 16. Testing Jobs with SpringBatchTest and JobLauncherTestUtils

To test a Job end-to-end, use `@SpringBatchTest` together with `JobLauncherTestUtils`.

Example:

~~~java
@SpringBatchTest
@SpringBootTest
@Sql(
    scripts = "/sql/orders-test-data.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
class ImportOrdersJobTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void importsOrdersSuccessfully() throws Exception {
        JobParameters parameters =
                new JobParametersBuilder()
                        .addString("inputBatch", "test-001")
                        .toJobParameters();

        JobExecution execution =
                jobLauncherTestUtils.launchJob(parameters);

        assertEquals(
                BatchStatus.COMPLETED,
                execution.getStatus());

        Integer count = jdbcTemplate.queryForObject(
                "select count(*) from orders",
                Integer.class);

        assertEquals(3, count);
    }
}
~~~

Test configuration must specify which Job to launch if the `ApplicationContext` defines multiple Jobs. You can configure `JobLauncherTestUtils` with a specific `Job` bean or use dedicated test configurations depending on version.

Identifying `JobParameters` must differ across test runs if each test needs a fresh `JobInstance`. Reusing identifying parameters from an already `COMPLETED` `JobInstance` causes Spring Batch to reject re-launching it.

## 17. Testing Individual Steps

When isolating behavior in one Step, you do not have to launch the entire Job. `JobLauncherTestUtils` can launch a specific Step via its step-launching utility.

Conceptual example:

~~~java
JobExecution execution =
        jobLauncherTestUtils.launchStep(
                "importOrdersStep",
                new JobParametersBuilder()
                        .addString("inputBatch", "step-test-01")
                        .toJobParameters());
~~~

Step tests isolate readers/writers and run faster. However, if a Step depends on Job `ExecutionContext` populated by an earlier Step, prepare an appropriate context or test the full Job.

Assert:
- `BatchStatus`.
- `ExitStatus`.
- Read/write/filter/skip counts.
- `StepExecutionContext` if part of a public contract.
- Persisted database state after commit.
- Required side effects.

Do not assert `COMPLETED` alone; a Step can complete while writing fewer records due to processor filtering or unexpected skips.

## 18. Verifying Chunk Transaction Rollback

A critical test confirms that when the writer fails, all database updates in the same chunk transaction roll back.

You can use a test writer that writes and then intentionally throws:

~~~java
public class FailingDatabaseWriter
        implements ItemWriter<Order> {

    private final JdbcTemplate jdbcTemplate;

    public FailingDatabaseWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        for (Order order : chunk) {
            jdbcTemplate.update("""
                    insert into orders(id, customer_id, status, amount)
                    values (?, ?, ?, ?)
                    """,
                    order.getId(),
                    order.getCustomerId(),
                    order.getStatus(),
                    order.getAmount());
        }

        throw new IllegalStateException("Simulated writer failure");
    }
}
~~~

When the writer uses the same `DataSource` managed by the Step's transaction manager, the exception rolls back the chunk transaction. After the Job fails, query the database to confirm rows from that chunk do not exist.

Tests must ensure:
- The transaction manager and `JdbcTemplate` share the same `DataSource`.
- The writer does not open an independent transaction with `REQUIRES_NEW` propagation.
- No outer test transaction distorts what is observed.
- The Job has finished before querying results.

If the writer writes files or makes HTTP calls, those side effects do not roll back alongside JDBC. Testing database rollback does not prove external resources rolled back too.

## 19. Do Not Let a Test Transaction Mask Job Outcomes

A common mistake is putting `@Transactional` on a test method and launching a Job inside it. The test transaction may not be the transaction the Job uses, especially when the Job runs on another thread or uses a separate transaction manager.

This can cause:
- The Job not seeing uncommitted test fixtures.
- The test not seeing data committed by the Job.
- Test rollback cleanup failing to remove rows committed by another transaction.
- Divergent behavior between synchronous and asynchronous launchers.

Safe approach:
1. Seed fixtures in a dedicated transaction and commit.
2. Launch the Job.
3. Wait for the Job to finish.
4. Query results using a fresh connection or `JdbcTemplate`.
5. Clean up test data afterward via script or separate transaction.

If intentionally testing transaction propagation, write a dedicated test and document transaction boundaries explicitly rather than relying on test framework defaults.

## 20. Testing Restart of Readers and Writers

Restart tests must prove the Job resumes the same `JobInstance` and restores checkpoints. A common scenario:
1. Launch the Job with fixed identifying parameters.
2. Allow some chunks to commit.
3. Intentionally fail a subsequent chunk.
4. Confirm `JobExecution` is `FAILED` and data from committed chunks persists.
5. Re-launch the same `JobInstance` with identical identifying parameters.
6. Confirm the new `JobExecution` belongs to the original `JobInstance`.
7. Confirm the reader resumes past the checkpoint and the writer writes no duplicates.

Example ID assertions:

~~~java
assertEquals(
        firstExecution.getJobInstance().getInstanceId(),
        restartExecution.getJobInstance().getInstanceId());

assertNotEquals(
        firstExecution.getId(),
        restartExecution.getId());
~~~

Restarting does not mean launching with new identifying parameters. Changing identifying parameters creates a new `JobInstance` and ignores the old instance's checkpoint.

Verify both database rows and `JobRepository` metadata. A Job can report `COMPLETED` while producing wrong data if input queries lack stable ordering or writers trigger out-of-transaction side effects.

## 21. Testing Skip and Retry on Database Writers

If a Step configures skipping duplicate keys, prepare tests with:
- A new item.
- An item whose key already exists.
- Another new item after the duplicate item.

After launching, verify:
- Both new items are written.
- The duplicate item does not halt the Step when within skip policy.
- Write skip count increments accurately.
- `SkipListener` receives the right item.
- The item after the duplicate still processes.
- Other integrity violations are not accidentally skipped.

For retry, simulate a recoverable transient error. Do not use `DuplicateKeyException` to test retry because deterministic duplicates do not vanish when retrying the same `INSERT`.

If the writer uses JDBC batching, the driver can report failures at the batch level. Test how Spring Batch isolates the failing item and applies skips in practice.

## 22. Testing Scoped Readers/Writers and JobParameters

Readers/writers annotated with `@StepScope` or `@JobScope` often inject parameters via SpEL. Tests must execute inside the corresponding scope.

Example:

~~~java
@Bean
@StepScope
JdbcCursorItemReader<Order> orderReader(
        DataSource dataSource,
        @Value("#{jobParameters['businessDate']}")
        String businessDate) {
    // Configure reader by businessDate.
}
~~~

You can test via `JobLauncherTestUtils` by passing `JobParameters`. This is usually closest to production because the framework activates scope during the Step.

For unit tests of scoped components, use `StepScopeTestExecutionListener` or `StepScopeTestUtils` to create a test `StepExecution`. Do not fetch target beans before scope is active.

Test cases:
- Parameter present with valid value.
- Missing parameter.
- Malformed parameter.
- Parameter selecting an empty dataset.
- Restart using identical identifying parameters.
- Non-identifying parameter changing without creating a new `JobInstance`.

## 23. Testing Readers/Writers with Multiple DataSources

A Job may read from a source database and write to a target database. Tests must configure the right `DataSource`, transaction manager, and schema for each side.

Verify:
- Reader uses the source `DataSource`.
- Writer uses the target `DataSource`.
- Transaction manager governs the intended rollback resource.
- `JobRepository` can use its own `DataSource`.
- Source transactions are not confused with target transactions.
- Failure between reading and writing leaves no unexpected inconsistent state.

A simple JDBC transaction manager does not create an atomic transaction across multiple `DataSource`s. When source and target differ, tests must reflect real semantics: target commits, metadata checkpoints, and source reads may belong to separate transactions.

If distributed transactions are required, configure and test the corresponding transaction manager. Otherwise, design retries, idempotency, and reconciliation for crashes occurring between two resources.

## 24. Testing Database-Specific Behavior with Testcontainers

When production runs a specific database engine, Testcontainers can spin up a real database instance inside integration tests.

PostgreSQL container example with Spring Boot:

~~~java
@Testcontainers
@SpringBootTest
class PostgreSqlOrderWriterTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void databaseProperties(
            DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username",
                postgres::getUsername);
        registry.add("spring.datasource.password",
                postgres::getPassword);
    }
}
~~~

Pin container image versions to match your project environment; avoid `latest` in CI when reproducible results are required.

Testcontainers is valuable for testing:
- SQL dialects.
- `SQLState` and exception translation.
- Batch inserts/updates.
- Decimal/date/time mapping.
- Paging query providers.
- Isolation and locking.
- Constraint behavior.
- Driver cursor/fetch behavior.

Container tests still do not replace production validation. Database versions, extensions, collations, timezones, and connection settings can differ in production.

## 25. Performance Testing Readers and Writers

Performance tests should measure against production-like data:
- Item counts.
- Row width.
- Column counts and joins.
- Indexes.
- Chunk size.
- Fetch size/page size.
- Batch update size.
- Connection pool sizing.
- Network latency.
- Execution plans.

Do not benchmark a tiny H2 test and extrapolate production throughput. Likewise, do not raise chunk size arbitrarily because longer transactions increase lock duration, rollback cost, and memory usage.

Metrics to measure:
- Items read/written per second.
- Query and fetch durations.
- Batch write durations.
- Round-trip counts.
- Heap usage.
- Connection wait times.
- Lock waits/deadlocks.
- Commit duration.

Separate performance tests from functional unit/integration tests so CI does not become flaky under machine load.

## 26. Testing Resource Lifecycles and Connection Leaks

Cursor readers can hold connections for the duration of a Step. Tests should verify resources are closed whether the Step succeeds or fails.

You can inspect connection pool metrics before/after the Job, or use a datasource proxy/test double to count acquire/release calls. For JDBC readers, verify cursors and statements close via lifecycle callbacks.

Scenarios:
- Job completes normally.
- Reader throws an exception mid-read.
- Writer fails.
- Step is stopped.
- Restart after failure.
- Opening a second resource fails after the first resource already opened.

Do not test only the happy path. Connection leaks frequently surface after repeated runs or along error branches.

## 27. Assertions Should Verify Data, Not Just Job Status

A good integration test verifies both metadata and business data.

Example assertions:
- `BatchStatus.COMPLETED`.
- Expected `ExitStatus`.
- `readCount`, `writeCount`, `filterCount`, `skipCount`.
- Row count in target tables.
- Values of critical columns.
- Zero unexpected duplicate business keys.
- Zero missing records.
- Checkpoint/`JobInstance` identity on restart.
- Audit records for skips/rejects.

When a processor filters items, having `writeCount` smaller than `readCount` is normal. Tests must assert expected counts per business rules rather than always expecting `readCount` to equal `writeCount`.

For large datasets, verify counts, min/max keys, checksums, or business key sets instead of loading the entire table into test memory.

## 28. Test Isolation and Parallel Execution

Tests sharing a database/schema can collide if executed in parallel:
- One test truncates a table while another is reading.
- Two Jobs use identical identifying parameters.
- Sequences/identities get reset mid-run.
- Leftover `JobRepository` metadata from an earlier test interferes.
- Output file names collide.

Mitigations:
- Dedicated schemas per test suite or worker.
- Unique `JobParameters` for each fresh test launch.
- Cleaning `JobExecution` metadata with `JobRepositoryTestUtils` where appropriate.
- Explicit transaction/cleanup boundaries.
- Avoiding shared output directories across parallel tests.
- Never resetting sequences while other tests are running.

If a test specifically verifies restarting the same `JobInstance`, keep identifying parameters unchanged within that test. Generate unique parameters only between independent test cases.

## 29. Testing JobRepository and Transaction Manager Configuration

A Job test might run readers/writers properly while `JobRepository` uses a different database or transaction manager than production configuration. That makes tests misrepresent real checkpoint/commit behavior.

Verify:
- `JobRepository` is configured with the intended `DataSource`.
- The Step uses the right transaction manager.
- The JDBC writer uses a `DataSource` participating in the Step's transaction.
- Cursor reader connection semantics are well understood.
- Batch metadata schema is initialized.
- Isolation level and transaction propagation are appropriate.

When using `@SpringBootTest`, check test profiles and property overrides. Never accidentally run against an embedded database while believing tests run against Testcontainers.

## 30. Sample Test Suite for Database Readers/Writers

A practical test suite can be structured as:

| Category | Minimum tests |
|---|---|
| Reader SQL | Filters, parameter binding, mapping, empty results |
| Reader ordering | Stable `ORDER BY`, page boundaries |
| Reader state | Open/update/close, checkpoint/reopen |
| Writer SQL | Insert, update, parameter mapping |
| Writer constraints | Duplicates, foreign keys, not-null |
| Transactions | Chunk commit and rollback |
| Batch behavior | Multiple items, partial batch failures |
| Job integration | Launch Job/Step and assert persisted data |
| Restart | Same `JobInstance`, restored `ExecutionContext` |
| Fault tolerance | Skip, retry, listeners, and limits |
| Resources | Connections/cursors closed on success/failure |
| Database dialect | Tests on production-like engine/driver |

This suite provides coverage from small SQL contracts up to end-to-end behavior without mocking away every real component.

## 31. Common Pitfalls When Testing Database Readers/Writers

**Mocking only JdbcTemplate or ItemWriter.** Tests fail to verify real SQL, constraints, and driver behavior.

**Using H2 for everything.** Can miss dialect, isolation, paging, and exception translation differences.

**Omitting ORDER BY in queries.** Tests may pass by chance and fail later when data or execution plans change.

**Testing paging with a single page.** Misses bugs at page boundaries.

**Skipping field-level mapping checks.** Row counts can match while individual column values are wrong.

**Wrapping the Job inside a test transaction.** Uncommitted fixtures or committed Job writes may be observed inaccurately.

**Reusing identical identifying JobParameters across tests.** An already `COMPLETED` `JobInstance` cannot be launched again.

**Asserting only BatchStatus.** A `COMPLETED` Job does not guarantee business data is right.

**Not testing rollback.** Writers may leave behind partial rows from failing chunks.

**Not testing restart.** Checkpoints and unstable input ordering can drop or duplicate records.

**Ignoring actual driver exception classes.** Skipping `DuplicateKeyException` fails if the writer throws a different `SQLException`.

**Failing to clean JobRepository metadata.** Later tests may be affected by stale `JobExecution`s.

**Not testing resource cleanup.** Cursors/connections can leak on error branches.

**Running tests in parallel on the same schema/files.** Data or outputs can overwrite each other.

## 32. Process for Testing Database Readers and Writers

When testing a Step using database readers/writers, follow this sequence:

1. Select an appropriate test database; use a production-like engine/driver for vendor-specific behavior.
2. Create repeatable schemas and fixtures isolated across tests.
3. Test the reader directly for SQL, parameters, `RowMapper`, sort order, and empty results.
4. Test paging/cursors across multiple pages/chunks and data boundaries.
5. Test reader checkpoints via `ExecutionContext` and reopening.
6. Test the writer directly for SQL, parameter binding, inserts/updates, and constraints.
7. Test Step transactions to verify commit and rollback.
8. Use `SpringBatchTest` and `JobLauncherTestUtils` to launch Jobs/Steps.
9. Assert `BatchStatus`, `ExitStatus`, counts, and actual database rows.
10. Test skip/retry, `DuplicateKeyException`, listeners, and skip limits.
11. Test restarting the same `JobInstance` with stable identifying parameters.
12. Test multiple `DataSource`s, connection lifecycles, and resource cleanup if applicable.
13. Use Testcontainers for critical SQL dialect, driver, and concurrency behaviors.
14. Isolate `JobRepository` metadata, schemas, output paths, and fixtures so tests run independently.
15. Separate performance tests from functional tests and measure on production-like data.

Testing database readers and writers must prove both the SQL statements and how they behave inside Spring Batch transactions and lifecycles. Unit tests validate small logic; database integration tests validate JDBC and schemas; Spring Batch integration tests validate chunks, checkpoints, skips, and restarts. When tests run against an appropriate database with isolated fixtures and data-level assertions, bugs are caught well before batches touch production data.

