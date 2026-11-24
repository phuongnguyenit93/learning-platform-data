# Running Spring Batch Tests Safely in Parallel

## 1. Why Do Parallel Tests Easily Fail?

Running multiple tests concurrently cuts suite execution time, especially when each integration test initializes a Spring context, opens transactions, and hits a database. However, Spring Batch tests often share stateful infrastructure: **`JobRepository`**, **`BATCH_*` metadata tables**, source and target databases, beans inside the Spring context, input/output files, or test utilities. If two tests do not isolate their data properly, they interfere with each other even when batch processing logic is completely sound.

For example, suppose two tests launch **importCustomersJob** with identical identifying **JobParameters**:

~~~text
Test A: importCustomersJob + businessDate=2026-11-16
Test B: importCustomersJob + businessDate=2026-11-16
                      |
                      v
             SAME JobInstance
                      |
          +-----------+-----------+
          |                       |
   One test is running     The other launches again
                                  |
                    JobExecutionAlreadyRunningException
                     or unexpected status
~~~

This is not a race condition in the import logic; the two tests accidentally drove **the exact same `JobInstance`**. Another common failure is Test A wiping the entire target table during setup right as Test B is writing rows. Test B may fail intermittently—or worse, pass while asserting against tampered data.

This lesson focuses on **Spring Batch test infrastructure**: how to structure data, `JobParameters`, application contexts, and resources so multiple tests run side by side reliably. This differs from configuring a multi-threaded Step or partitioning inside a single Job; batch processing itself can be sequential while **tests launch distinct `JobInstance`s in parallel**.

## 2. Components That Can Be Shared

| Component | What Can Be Shared | Risk Under Concurrent Tests |
| --- | --- | --- |
| **JobRepository** | Metadata tables for `JobInstance`, `JobExecution`, `StepExecution`, and `ExecutionContext` | Identical identifying `JobParameters` cause contention over one `JobInstance`; deleting metadata breaks other tests. |
| **Business database** | Input, output, staging, and audit tables | Test data deleted, overwritten, misread, or hitting unique key violations. |
| **Spring ApplicationContext** | Singleton beans, `Job`, `Step`, processors, services, mocks | One test mutates shared bean state, giving another test stale config or state. |
| **JobLauncher / test utilities** | Launcher and job-configuration utilities | One test swaps the Job or utility settings while another test is running. |
| **Readers / writers / processors** | Cursors, counters, buffers, caches, file paths | One test consumes items or mutates state belonging to another test. |
| **Filesystem** | CSV/XML files, output files, temp directories | Writing to the same filename or deleting a file another test is reading. |
| **Connections and transactions** | JDBC pools, database locks, transaction managers | Pool exhaustion, deadlocks, timeouts, or assertions seeing uncommitted data. |
| **Test framework config** | Spring context cache, global mock resets, before/after hooks | Tests sharing a context call global resets, truncates, or resource shutdowns. |

Running parallel tests safely does not require every test to have its own Spring context. Typically, **beans without per-test mutable state can be shared**, while writable data, parameters, and mutable resources must be separated.

## 3. First Rule: Every Test Needs Its Own `JobInstance`

Spring Batch identifies a **`JobInstance`** by the Job name and the **`JobParameters` flagged as identifying**. Two launches with the same Job name and identifying parameters resolve to the same `JobInstance`. That is ideal for restart tests, yet wrong when two independent tests run concurrently.

### 3.1. Generate a Unique Identifier per Test

In Spring Batch 5.x:

~~~java
String caseId = UUID.randomUUID().toString();

JobParameters parameters = new JobParametersBuilder()
        .addString("caseId", caseId, true)
        .toJobParameters();

JobExecution execution = jobLauncher.run(importCustomersJob, parameters);
~~~

Here **`caseId`** is an identifying parameter. Each test generates a fresh value, allowing Spring Batch to create separate `JobInstance`s even though all tests share the same `Job` bean.

Avoid hardcoding one fixed parameter set across tests:

~~~java
// Unsuitable for two independent tests launching the same Job.
JobParameters parameters = new JobParametersBuilder()
        .addString("caseId", "shared-test", true)
        .toJobParameters();
~~~

Not every parameter participates in `JobInstance` identity. For example:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("caseId", caseId, true)        // identifying
        .addString("requestedBy", "junit", false) // non-identifying
        .toJobParameters();
~~~

Varying only **`requestedBy`** does not create a new `JobInstance`. Therefore, when distinguishing test runs, make sure the differentiating parameter is marked identifying.

### 3.2. Intentional Exception: Restart Tests

A restart test must launch the second run with **the exact identifying `JobParameters` used on the first run** to verify continuation of the same `JobInstance`:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("caseId", UUID.randomUUID().toString(), true)
        .toJobParameters();

JobExecution failedRun = jobLauncher.run(job, parameters);
// Assume the first run FAILED due to a controlled fault.

JobExecution restartedRun = jobLauncher.run(job, parameters);
// Same JobInstance, new JobExecution.
~~~

What must be isolated is **between different restart tests**, where each test uses its own `caseId`. Within **one** restart test, both the initial run and the restart reuse the same `caseId`. Never delete `JobRepository` metadata or committed data between the two runs, because that is the exact state restart needs to recover.

## 4. Second Rule: Partition Business Data by Test

Creating distinct `JobInstance`s alone **is not enough**. If two Jobs read from the same input table or write to the same target table with overlapping keys, they will still collide.

A straightforward technique is adding **`case_id`** to fixtures, filtering queries by `caseId`, and using a composite key **`(case_id, id)`** so each test has its own data namespace.

~~~sql
CREATE TABLE source_customer (
    case_id       VARCHAR(64) NOT NULL,
    id            BIGINT NOT NULL,
    customer_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (case_id, id)
);

CREATE TABLE imported_customer (
    case_id       VARCHAR(64) NOT NULL,
    id            BIGINT NOT NULL,
    customer_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (case_id, id)
);
~~~

For instance, two tests can both use business IDs **101** and **102**:

~~~text
source_customer

case_id   id    customer_name
--------  ----  -------------
case-A    101   An
case-A    102   Binh
case-B    101   Chi
case-B    102   Dung
~~~

Neither test contends on primary keys because the **`(case_id, id)`** pairs differ. However, this design only works if **every read, write, count, and cleanup query respects `case_id`**:

~~~sql
-- Reader sees only the current test's input.
SELECT id, customer_name, case_id
FROM source_customer
WHERE case_id = ?
ORDER BY id;

-- Assertion sees only the current test's output.
SELECT id
FROM imported_customer
WHERE case_id = ?
ORDER BY id;

-- Clean up only this test's data, if needed.
DELETE FROM imported_customer WHERE case_id = ?;
DELETE FROM source_customer WHERE case_id = ?;
~~~

If the business schema cannot be altered, isolate via **separate schemas/databases**, **tenant IDs**, **run codes**, separate files, or another application-appropriate namespace. The core principle is that every test can identify the exact rows it owns and is allowed to delete.

### Setup and Cleanup Operations to Avoid

The following statements are dangerous when multiple tests share a database:

~~~sql
TRUNCATE TABLE source_customer;
DELETE FROM imported_customer;
DELETE FROM BATCH_JOB_EXECUTION;
DELETE FROM BATCH_STEP_EXECUTION;
~~~

One test can fire a delete right when another test just created metadata or committed a chunk. Placing these in **`@BeforeEach`**, **`@AfterEach`**, or **`@Sql`** does not make them safe under parallel execution: hooks from two tests interleave.

If a full database reset is truly needed, run it before starting the parallel test group, or give each test an independent database/schema. With partitioned test data, always delete scoped to that test's `caseId`.

## 5. Third Rule: Keep Processing State Scoped to the Step

Spring creates beans with **`singleton`** scope by default. A processor holding mutable state will be shared across multiple `JobExecution`s unless you explicitly isolate it.

An example unsuitable for concurrent tests:

~~~java
@Component
public class CountingProcessor implements ItemProcessor<Customer, Customer> {

    private int processedCount = 0;

    @Override
    public Customer process(Customer item) {
        processedCount++;
        return item;
    }

    public int getProcessedCount() {
        return processedCount;
    }
}
~~~

**`processedCount`** is singleton state. The counter can mix items across tests, and the increment itself is not thread-safe.

Safer alternatives include:

- Keep processors **stateless**: outputs depend solely on inputs and thread-safe services.
- Keep state genuinely belonging to one Step run inside a **`@StepScope`** bean or an object created per execution.
- For state that must survive restarts, use **`ExecutionContext`** and **`ItemStream`** mechanisms rather than static fields.
- If mutable in-memory sharing is unavoidable, design and test explicit synchronization policies; synchronization only fixes memory races and does not replace business data partitioning.

### Readers Should Be Step-Scoped

A reader with a cursor or read position must be instantiated per `StepExecution`. Example with **`JdbcCursorItemReader`**:

~~~java
@Bean
@StepScope
JdbcCursorItemReader<Customer> customerReader(
        DataSource dataSource,
        @Value("#{jobParameters['caseId']}") String caseId) {

    return new JdbcCursorItemReaderBuilder<Customer>()
            .name("customerReader")
            .dataSource(dataSource)
            .sql("""
                SELECT id, customer_name, case_id
                FROM source_customer
                WHERE case_id = ?
                ORDER BY id
                """)
            .preparedStatementSetter(ps -> ps.setString(1, caseId))
            .rowMapper((rs, rowNum) -> new Customer(
                    rs.getLong("id"),
                    rs.getString("customer_name"),
                    rs.getString("case_id")))
            .saveState(true)
            .build();
}
~~~

In this example, **`Customer`** is a record:

~~~java
public record Customer(long id, String customerName, String caseId) {}
~~~

**`@StepScope`** creates a fresh reader per Step execution and enables binding `JobParameters`. **`saveState(true)`** persists reader state at checkpoints. A singleton reader carrying an exhausted cursor from Test A into Test B can cause Test B to read zero items even with a different `caseId`.

For stateful writers such as file writers, output paths must also be partitioned—for example **`outputDir/caseId/results.csv`**. Never let two `StepExecution`s write to the same file without an explicit coordination design.

## 6. Job Configuration Pattern Safe for Parallel Tests

The following example uses **Java 17, Spring Batch 5.x, Spring Boot 3.x, Spring JDBC, JUnit 5, and AssertJ**. It assumes the application configures **`JobRepository`**, **`PlatformTransactionManager`**, and **`DataSource`**, and that the two fixture tables from Section 4 are created by migrations or test SQL initialization.

The reader in Section 5 filters input by the identifying **`caseId`**. The writer below persists the same `caseId` to the target table:

~~~java
@Bean
JdbcBatchItemWriter<Customer> customerWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Customer>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO imported_customer (case_id, id, customer_name)
                VALUES (:caseId, :id, :customerName)
                """)
            .itemSqlParameterSourceProvider(customer ->
                    new MapSqlParameterSource()
                            .addValue("caseId", customer.caseId())
                            .addValue("id", customer.id())
                            .addValue("customerName", customer.customerName()))
            .build();
}
~~~

The chunk-oriented Step can be declared as:

~~~java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcCursorItemReader<Customer> customerReader,
        JdbcBatchItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<Customer, Customer>chunk(2, transactionManager)
            .reader(customerReader)
            .writer(customerWriter)
            .build();
}

@Bean
Job importCustomersJob(
        JobRepository jobRepository,
        Step importCustomersStep) {

    return new JobBuilder("importCustomersJob", jobRepository)
            .start(importCustomersStep)
            .build();
}
~~~

In this configuration, tests share the **`Job`** and **`Step`** definitions, while each launch gets its own **`StepExecution`**, step-scoped reader, and **`caseId`** parameter. The JDBC writer holds no per-test mutable buffers here; each write call uses only items from the current chunk.

If the application has processors or listeners, audit those beans for shared state too. **`@StepScope`** does not make a separate singleton service thread-safe if that service still stores test data in shared fields.

## 7. Enabling JUnit 5 Parallel Execution Under Control

JUnit Jupiter does not run tests in parallel automatically just because a machine has multiple CPUs. Enable it in **`src/test/resources/junit-platform.properties`**:

~~~properties
junit.jupiter.execution.parallel.enabled=true

# Run sequentially by default; only annotated tests/classes run in parallel.
junit.jupiter.execution.parallel.mode.default=same_thread
junit.jupiter.execution.parallel.mode.classes.default=same_thread

junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=4
~~~

Then opt in only test classes designed to be safe:

~~~java
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

@Execution(ExecutionMode.CONCURRENT)
class ParallelCustomerImportTest {
    // @Test methods in this class may be run concurrently by JUnit.
}
~~~

This configuration requires enough JUnit worker threads so tests actually have a chance to overlap. **`@Execution(CONCURRENT)`** permits concurrent execution; it does not guarantee overlap on every run. When the goal is reproducing a bug that occurs only when two transactions intersect, coordinate the intersection with **`CountDownLatch`**, **`CyclicBarrier`**, or bounded synchronization rather than relying on random **`Thread.sleep`** calls.

To enable parallelism suite-wide, you can switch **`mode.default=concurrent`** and **`mode.classes.default=concurrent`**, but only after verifying no involved test shares unsafe state. Opting in prepared classes selectively keeps scope under control.

## 8. Parallel Integration Tests Against a Shared Database

When tests share a Spring `ApplicationContext`, inject **`JobLauncher`** and **`Job`** directly and launch with separate `JobParameters`. This avoids mutating state inside shared test utilities.

The example assumes the beans from Section 6 are in the application context, `JobLauncher` is **synchronous**, and the business schema is already initialized:

~~~java
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always"
})
@Execution(ExecutionMode.CONCURRENT)
class ParallelCustomerImportTest {

    @Autowired
    private JobLauncher jobLauncher;

    @Autowired
    @Qualifier("importCustomersJob")
    private Job importCustomersJob;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void importsThreeRows() throws Exception {
        runIsolatedScenario(List.of(101L, 102L, 103L));
    }

    @Test
    void importsFourRowsWithOverlappingBusinessIds() throws Exception {
        // Overlapping IDs with the test above are intentional.
        // The (case_id, id) composite key prevents the two tests from colliding.
        runIsolatedScenario(List.of(101L, 102L, 103L, 104L));
    }

    private void runIsolatedScenario(List<Long> expectedIds) throws Exception {
        String caseId = UUID.randomUUID().toString();

        try {
            // Fixtures belong strictly to this test.
            for (Long id : expectedIds) {
                jdbcTemplate.update(
                        """
                        INSERT INTO source_customer (case_id, id, customer_name)
                        VALUES (?, ?, ?)
                        """,
                        caseId, id, "customer-" + id);
            }

            JobParameters parameters = new JobParametersBuilder()
                    .addString("caseId", caseId, true)
                    .toJobParameters();

            JobExecution execution = jobLauncher.run(
                    importCustomersJob, parameters);

            assertThat(execution.getStatus())
                    .isEqualTo(BatchStatus.COMPLETED);

            StepExecution step = execution.getStepExecutions().stream()
                    .filter(s -> "importCustomersStep".equals(s.getStepName()))
                    .findFirst()
                    .orElseThrow();

            assertThat(step.getReadCount()).isEqualTo(expectedIds.size());
            assertThat(step.getWriteCount()).isEqualTo(expectedIds.size());
            assertThat(step.getSkipCount()).isZero();

            // Read only output tagged with this test's caseId.
            List<Long> actualIds = jdbcTemplate.queryForList(
                    """
                    SELECT id FROM imported_customer
                    WHERE case_id = ?
                    ORDER BY id
                    """,
                    Long.class,
                    caseId);

            assertThat(actualIds).containsExactlyElementsOf(expectedIds);

        } finally {
            // Cleanup scoped strictly to this test's caseId.
            jdbcTemplate.update(
                    "DELETE FROM imported_customer WHERE case_id = ?", caseId);
            jdbcTemplate.update(
                    "DELETE FROM source_customer WHERE case_id = ?", caseId);
        }
    }
}
~~~

### Key Aspects of This Test

1. **`caseId` is generated inside each scenario execution.** Two tests can reuse the same business IDs while keeping distinct `JobInstance`s and data slices.
2. **`JobLauncher` and `Job` are never mutated between tests.** Each launch passes only that test's `JobParameters`.
3. **The reader filters by `caseId` in SQL.** Passing `caseId` in `JobParameters` without filtering in the reader would still cause cross-test reads.
4. **Assertions query by `caseId`.** Never run **`SELECT COUNT(*) FROM imported_customer`** to check one test's row count in a shared database.
5. **Cleanup runs by `caseId`.** Test A never deletes Test B's fixtures; Batch metadata tables are left untouched while tests are active.
6. **`JobLauncher` is assumed synchronous by this example.** If the Job launches asynchronously via a `TaskExecutor`, **`run(...)`** returns while the Job is still running. In that case, wait for terminal status via **`JobExplorer`** or a bounded completion mechanism before asserting and cleaning up.
7. **Source and target tables must exist before concurrent tests begin.** Schema creation/deletion should never run inside per-test **`@BeforeEach`** hooks on a shared database.

The snippet uses **`spring.batch.jdbc.initialize-schema=always`** to set up Batch metadata in a suitable test environment. This property does not create **`source_customer`** or **`imported_customer`**. When a database is shared across multiple Spring contexts, avoid having multiple contexts re-initialize metadata schemas while Jobs are running; manage migrations/schema init centrally in the test infrastructure lifecycle.

## 9. Be Careful with `spring-batch-test` Utilities

**`spring-batch-test`** supplies **`@SpringBatchTest`**, **`JobLauncherTestUtils`**, **`JobRepositoryTestUtils`**, and Step-scope listeners. They are helpful, yet how you use them determines whether tests are safe in parallel.

### 9.1. `JobLauncherTestUtils` Holds Mutable Job Configuration State

Many tests are written like this:

~~~java
@Autowired
private JobLauncherTestUtils testUtils;

@BeforeEach
void setUp() {
    testUtils.setJob(importCustomersJob);
}

@Test
void launch() throws Exception {
    testUtils.launchJob(parameters);
}
~~~

**`JobLauncherTestUtils`** holds a reference to the configured Job. If two tests sharing a context call **`setJob(...)`** with different Jobs, Test A can accidentally launch the Job Test B just assigned.

For integration tests running concurrently, injecting **`JobLauncher`** directly and calling **`jobLauncher.run(targetJob, parameters)`** as in Section 8 keeps boundaries clean. If you still use **`JobLauncherTestUtils`**, ensure the Job reference is never reassigned across tests and each test passes unique `JobParameters`.

### 9.2. Never Use Global Metadata Cleanup in Concurrent Tests

**`JobRepositoryTestUtils.removeJobExecutions()`** can wipe metadata across multiple runs. Calling it in **`@BeforeEach`** or **`@AfterEach`** when tests share a `JobRepository` can delete state that another active test relies on.

Use unique `JobParameters` to distinguish runs; clean metadata only once the suite finishes or inside isolated metadata stores. When testing restart, preserve the failed run's metadata until restart and assertions complete.

### 9.3. Thread-Bound Scope and `StepExecution`

**`@StepScope`** and **`@JobScope`** bind beans to the context of the corresponding execution. When Spring Batch runs a Step, the framework establishes the proper context for the Step lifecycle, preventing reader state from leaking across `JobExecution`s.

If a unit test invokes a step-scoped bean directly without launching a Step, you may need **`StepScopeTestUtils`** or a `spring-batch-test` listener to create a simulated `StepExecution` context. Spawning threads manually and calling a step-scoped bean outside Batch's lifecycle does not carry `StepContext` over automatically; define context boundaries explicitly.

## 10. Test Transactions vs. Job Transactions

A common mistake is annotating an entire integration test with **`@Transactional`** expecting fixtures to roll back automatically afterward:

~~~java
@Transactional
@Test
void importsCustomers() {
    // Insert fixture data.
    // Launch a Job that has its own Step transactions.
}
~~~

Rolling back a test-framework transaction does not mean every transaction inside the Job rolls back with it. When a Step opens its own transaction—or runs on another thread—the Job may not see uncommitted fixture rows; conversely, rows committed by the Job survive after the test rolls back.

For integration tests verifying commits, retries, skips, or restarts, the clean approach is:

- Seed fixture rows before launching and ensure inputs are committed/visible under the database isolation level.
- Let the Job use the exact transaction manager configuration under test.
- Wait for the Job to finish before inspecting output.
- Clean up strictly this test's data after the Job completes.

If you do wrap an entire test in a transaction, understand propagation, thread boundaries, transaction managers, and data visibility. Never assume **`@Transactional`** isolates batch tests automatically.

## 11. Connection Pools, Database Locks, and Resource Stability

Even with partitioned data, tests share physical resources. Suppose JUnit runs four tests concurrently, and each Job needs connections for `JobRepository`, reader, and writer. If the pool is too small, one Job can hold a connection while waiting for another, causing the group to deadlock or time out.

Example pool configuration in a test environment:

~~~properties
spring.datasource.hikari.maximum-pool-size=12
spring.datasource.hikari.connection-timeout=30000
~~~

These numbers are strictly **illustrative**. The right size depends on concurrency level, reader type, transaction behavior, and connections held per Job. Raising pool size endlessly will not overcome database server limits; measure connection usage, lock waits, and wait times, then tune alongside JUnit parallelism.

Additional notes:

- **`JdbcCursorItemReader`** can hold a cursor connection open for the entire Step; account for held connections when multiple Jobs run concurrently.
- **`JobRepository`** uses transactions to create `JobExecution`s and update metadata. Avoid accidental contention on the same `JobInstance`.
- **Global DDL or `TRUNCATE`** can acquire heavy locks, blocking other Jobs even when they process distinct `caseId`s.
- With Testcontainers, a single database container initialized per class/suite can be shared using data partitioning; if tests alter schemas or database settings incompatibly, give each its own schema or container.
- In-memory H2 works well for fast tests, yet locking, isolation, SQL, and transaction behavior differ from PostgreSQL/MySQL. For transaction race scenarios, run critical tests on the production-equivalent database engine.

### Never Close Shared Resources While Still in Use

If multiple tests share a static Testcontainers instance or a cached Spring context, Test A must never stop the container, close the `DataSource`, or drop schemas while Test B is still running. Shared resources require a **class- or suite-level lifecycle**, tearing down only after all consumer tests finish.

## 12. Mocks, Static State, and Spring Context Caching

**`@SpringBootTest`** normally uses the Spring TestContext cache, allowing multiple test classes to reuse one `ApplicationContext`. This saves time, yet singletons and mocks survive across tests.

Common conflict sources include:

- One test mutates a configuration field on a singleton and another test reads it.
- Two tests reconfigure the same Spring-registered mock; Test B resets the mock while Test A is calling it.
- A **static `AtomicBoolean`** simulating failures is shared across restart tests, causing one test to "consume" the failure meant for another.
- One test uses **`@DirtiesContext`** to shut down and rebuild the context while another test is using it.
- A global cache, file path, system property, or environment variable is modified inside a single test.

Prefer fixtures and beans **free of cross-test mutable state**. If fault injection is needed per `JobExecution`, key failure plans by **`caseId`**, use appropriately scoped beans, or isolate the fault switch per test dependency. A single suite-wide static flag is unreliable for parallel fail/restart tests.

If legacy tests must touch global state, run them sequentially for now, or use JUnit's **`@ResourceLock`** to serialize tests sharing a named resource:

~~~java
import org.junit.jupiter.api.parallel.ResourceLock;

@ResourceLock("shared-batch-fixture")
class LegacyBatchTest {
    // Tests using fixtures that cannot be isolated yet.
}
~~~

**`@ResourceLock`** only works if every test touching that resource honors the same lock name. It is a pragmatic bridge for hard-to-isolate cases; long term, independent data and state scale parallelism much better.

## 13. Intentionally Testing Concurrent Launches of One `JobInstance`

Some tests verify **policies preventing two concurrent runs of the same `JobInstance`**. Here, sharing identifying parameters is **the explicit goal of the scenario**, unlike two independent tests.

When a `JobExecution` is already running, a second launch request for the same `JobInstance` can be rejected, for example with **`JobExecutionAlreadyRunningException`**. To test this reliably:

1. Generate unique identifying parameters for the test scenario, then pass **that exact same parameter set** to both launch calls inside the scenario.
2. Place a barrier holding the first `JobExecution` at a point guaranteed to be in-flight.
3. Trigger the second launch once the first run is confirmed active.
4. Assert the exception or status matching the contract of your Spring Batch version.
5. Release the barrier and wait for the first Job to finish; always enforce timeouts so tests never hang.

If both Jobs start and finish too fast, time-based assertions miss the race window. Coordinate with **`CountDownLatch`** inside **`try/finally`** so latches always release even if an assertion fails.

Keep these concurrency-contention tests separate from normal parallel data-import tests so intentional `JobParameters` collisions are not confused with test-isolation bugs.

## 14. A Tiered Implementation Strategy

### Level 1: Parallel Unit Tests

Stateless processors, validators, mappers, and utilities can run in parallel via JUnit without initializing Batch infrastructure. Keep databases and static mutable fixtures out of unit tests whenever possible.

### Level 2: Integration Tests Sharing a Database with Partitioned Data

Often the best balance: tests share a Spring context, `JobRepository`, and database, while each test uses an **identifying `caseId`**, partitioned input/output keys, and `caseId`-scoped cleanup. Size connection pools appropriately and avoid global resets.

### Level 3: Schema- or Database-Isolated Integration Tests

Tests that alter schemas, test migrations, run full resets, or take intrusive database locks should use dedicated schemas or databases. Setup costs more, yet resource boundaries are airtight.

### Level 4: Adversarial Contention Tests

For scenarios such as duplicate `JobInstance` launches, deadlocks, lock timeouts, multiple workers updating one record, or duplicate event delivery, coordinate concurrency deterministically and assert the exact contention condition being modeled.

There is no need to force every test to the heaviest isolation level. Match the mechanism to the state each test actually mutates.

## 15. Signs a Parallel Test Is Not Safe Yet

| Symptom | Cause to Investigate | Resolution |
| --- | --- | --- |
| Intermittent **`JobInstanceAlreadyCompleteException`** | Tests share identifying parameters; one `JobInstance` already completed | Generate a unique identifying `caseId` per test. |
| **`JobExecutionAlreadyRunningException`** | Two launches for the same `JobInstance` overlapped | Separate `JobInstance`s for independent tests; coordinate intentionally if testing contention. |
| **`readCount`/`writeCount`** vary across runs | Inputs altered by another test; singleton reader; unpartitioned fixtures | Filter by `caseId`, make readers step-scoped, keep inputs isolated. |
| Primary key violations | Two tests insert the same business ID into a shared table | Use a composite key with `caseId` or separate schemas. |
| Passes alone, fails in suite | Global table deletes, shared mocks/static state, context closed mid-run | Scope cleanup, remove shared mutable state, isolate legacy tests. |
| Timeouts as test count grows | Connection pool too small, lock waits, database overload | Measure connections/locks, tune parallelism and pool size. |
| Restart test fails to recover | Metadata wiped, `JobParameters` changed, reader did not save state | Preserve identifying parameters and `JobRepository`; check `ItemStream`/checkpoints. |
| Assertions see mixed results | Test queries the entire table instead of its own slice | Query and assert strictly by this test's `caseId`. |
| Pass/fail order depends on scheduling | Unprotected shared mutable data or stateful beans | Identify shared resources, partition data, or apply test locks. |

## 16. Checklist Before Enabling Parallel Tests

- [ ] Every independent test generates unique **identifying `JobParameters`**.
- [ ] Restart tests reuse **the exact same parameters across runs within the test**, yet differ from other restart tests.
- [ ] Readers, processors, and writers do not share mutable state across `StepExecution`s unintentionally.
- [ ] Inputs, outputs, and assertions are partitioned by `caseId`, schema, database, or separate file paths.
- [ ] Cleanup affects only data created by that test; Batch metadata is not wiped while other Jobs are running.
- [ ] No test mutates a shared `Job` reference inside a singleton or test utility.
- [ ] Fixtures are committed before the Job reads; assertions run after the Job finishes.
- [ ] Shared Spring contexts, mocks, and containers are never reset or closed by one concurrent test.
- [ ] Connection pools and parallelism match database capacity.
- [ ] Tests intentionally inducing race conditions use barriers and timeouts to verify exact conditions.

When properly designed, **parallel tests** can still share most Spring Batch infrastructure. Each test clearly owns its `JobInstance`, data slice, and cleanup scope, while shared components remain stateless per test or explicitly synchronized. That way, test failures expose real batch defects rather than depending on which test happened to run first.

