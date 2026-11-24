# Data for Restart Testing in Spring Batch

## 1. How should restart be tested with data?

In Spring Batch, **restart** means resuming an interrupted `JobInstance`, typically after a run ends with status `FAILED` or `STOPPED`. A restart creates a new `JobExecution` for the **same `JobInstance`**, and Steps that need to run again can restore state from the `ExecutionContext` persisted at an earlier checkpoint.

Restart testing does not merely ask: "Did the rerun end `COMPLETED`?". More important questions are:

- Is data **committed before the failure** preserved intact?
- Is data from the **failed uncommitted chunk** reprocessed?
- Is data **not yet reached** processed after the restart?
- Does the final output contain **all records, accurate values, and zero missing or duplicate entries**?
- Did Spring Batch actually create a new execution for the same `JobInstance` and restore the checkpoint?

To answer these, the test dataset must have **deterministic ordering, easily cross-referenced identifiers, clear chunk boundaries, and a controlled fault position**. This article builds a complete example along those lines in the Spring Batch Core Processing context.

## 2. Distinguishing a restart from running a new Job

Spring Batch identifies a `JobInstance` by **Job name and identifying JobParameters**. For example:

```text
Job: importCustomersJob
Identifying parameters:
  businessDate = 2026-11-15
  inputFile    = /tmp/customers.csv
```

Suppose the first run fails:

```text
JobInstance J1
  ├─ JobExecution E1: FAILED
  └─ JobExecution E2: COMPLETED   <-- successful restart
```

If you change `businessDate` or add a new identifying parameter with a different value before launching the second time, Spring Batch treats it as a **new JobInstance** rather than restarting J1:

```text
JobInstance J1 (businessDate=2026-11-15)
  └─ JobExecution E1: FAILED

JobInstance J2 (businessDate=2026-11-16)
  └─ JobExecution E2: COMPLETED   <-- new Job, not a restart of J1
```

Therefore, when testing restart, **keep identifying JobParameters identical across both launches**. If the test needs a random parameter to avoid colliding with prior runs, generate it **once at the start of the test** and reuse the exact same `JobParameters` object for both launches.

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputFile", inputFile.toAbsolutePath().toString(), true)
        .addString("testCaseId", UUID.randomUUID().toString(), true)
        .toJobParameters();

JobExecution firstRun = jobLauncherTestUtils.launchJob(parameters);
JobExecution restartRun = jobLauncherTestUtils.launchJob(parameters);
```

The two `launchJob` calls above only demonstrate restart when **the first run finished in a restartable state**, the Job configuration permits restart, and `JobRepository` still holds the first run's metadata. If the first run ended `COMPLETED`, launching again with the same identifying parameters is normally rejected with `JobInstanceAlreadyCompleteException`.

Do not use `RunIdIncrementer`, current timestamps, or a **fresh `UUID.randomUUID()` on the second launch** in a restart test: altering identifying parameters silently turns the test into launching a brand-new Job.

## 3. Fixture design: 7 records, chunk size = 3, failure at record 5

Suppose a Step reads a CSV file, transforms items via `ItemProcessor`, and writes to table `imported_customer`. We choose the source dataset as follows:

**File `customers.csv`:**

```csv
id,name
101,An
102,Binh
103,Chi
104,Dung
105,Ha
106,Minh
107,Thao
```

**Target table** with a primary key on `id`:

```sql
CREATE TABLE imported_customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);
```

The Step is configured with `chunk(3)`, and the processor intentionally throws an exception **exactly once** when encountering `id = 105`. This exception is not in the scenario's skip/retry policy, so the first run leaves the Step `FAILED`.

| Stage | Relevant data | Expected transaction outcome |
| --- | --- | --- |
| Chunk 1 | 101, 102, 103 | Writer writes 3 items, transaction **commits**. |
| Chunk 2 | 104, 105, 106 | Processor fails at 105; current chunk **does not commit**. |
| After run 1 | 101, 102, 103 | Only the first three records exist in the target table. |
| After restart | 104, 105, 106, 107 | Reader resumes from checkpoint; writes the remaining four records. |
| Final result | 101 through 107 | All seven records exist, each `id` appearing exactly once. |

Because the processor stops right when processing 105, chunk 2's writer is never called in this scenario. Items 104 and 105 were touched by the reader/processor yet belong to the **uncommitted** chunk; they must be reprocessed on restart. Items 106 and 107 will be read during the next run.

```text
RUN 1

101 -> 102 -> 103 -> [COMMIT / CHECKPOINT]
104 -> 105 -> [ERROR] -> [ROLLBACK CHUNK 2] -> FAILED

TARGET TABLE AFTER RUN 1
101, 102, 103

RUN 2: RESTART SAME JOBINSTANCE

[restore checkpoint after 103]
104 -> 105 -> 106 -> [COMMIT]
107 -> [COMMIT] -> COMPLETED

FINAL TARGET TABLE
101, 102, 103, 104, 105, 106, 107
```

**Why fail at record 5?** Failing at the very first record fails to test preserving an already-committed chunk. Failing only after all data is written fails to test resuming unfinished work. Position 105 forces the test to verify **committed data**, **reprocessed data**, and **unread data** simultaneously.

## 4. Conditions for a fixture to genuinely test restart

### 4.1. Fixed input across runs

The `customers.csv` file must keep identical contents and ordering between the failed run and the restart. Deleting, adding, or reordering lines after a checkpoint is saved can cause a position-restoring reader to miss or re-read the wrong record. For production batch jobs, immutable files, pinned data versions, or staging mechanisms protect the source data.

With database readers, ensure deterministic read ordering (such as `ORDER BY id`/unique sort key when paging) and control dataset mutations during restart. Never rely on a query with non-deterministic ordering and expect checkpoints to point to the same record.

### 4.2. Stateful reader

Restartable readers like `FlatFileItemReader` use `ExecutionContext` to save read position. In this example, ensure:

- A stable `name` on the reader (state keys derive from the name).
- `saveState(true)` enabled; supporting readers default to true, yet setting it explicitly documents test intent.
- Do not delete `BATCH_*` metadata from `JobRepository` between the two runs.
- Ensure the reader opens cleanly within a new `StepExecution` on restart.

If using a custom reader, it must properly implement the `ItemStream` contract (`open`, `update`, `close`) to persist and restore checkpoint positions. Implementing `ItemReader#read()` alone does not make a reader remember its position across restarts.

### 4.3. Consistent writer and transaction boundaries

This example uses a JDBC writer and target table within the Step's transaction. When chunk 2 fails before commit, chunk 2 data never appears in the target table; since chunk 1 committed, the first three records remain intact.

If a writer calls an HTTP API, publishes messages, writes to a non-transactional file, or causes non-rollbackable side effects, that property **is no longer automatically guaranteed**. The fixture must then test idempotency, deduplication keys, outbox state, or target-system recovery mechanisms.

### 4.4. Scripted, repeatable fault

Avoid relying on real network outages, random timeouts, or uncontrolled process kills for baseline restart tests. An intentionally injected fault, such as throwing `IllegalStateException` only the first time `id = 105` is seen, makes outcomes predictable. On restart, disable this fault so the Step can complete.

## 5. Illustrative Spring Batch configuration

The examples below use **Java 17, Spring Boot 3.x, Spring Batch 5.x, JDBC, and JUnit 5**. The snippets serve as illustrative test fixtures to integrate into an app that already provides `JobRepository`, `DataSource`, transaction manager, and Batch configuration. You can place test beans in a `@TestConfiguration` class and `@Import` it into the test; the `imported_customer` table must exist before tests run.

### 5.1. CSV row model

```java
public record Customer(long id, String name) {
}
```

### 5.2. Checkpoint-enabled reader

```java
@Bean
@StepScope
FlatFileItemReader<Customer> customerReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<Customer>()
            .name("customerCsvReader")
            .resource(new FileSystemResource(inputFile))
            .linesToSkip(1)        // Skip header line: id,name
            .saveState(true)       // Save read position to ExecutionContext
            .delimited()
            .names("id", "name")
            .fieldSetMapper(fields -> new Customer(
                    fields.readLong("id"),
                    fields.readString("name")))
            .build();
}
```

`@StepScope` ensures the reader bean is created per Step execution and can receive JobParameters. An actual input file must stay unchanged across launches; this example reads the file path from the identifying parameter `inputFile`.

### 5.3. Single-failure processor

In this test fixture, an `AtomicBoolean` living across **two launches in the same application context** controls the fault. This is a test harness mechanism, not a production processor pattern:

```java
@Bean
AtomicBoolean failOnceAt105() {
    return new AtomicBoolean(true);
}

@Bean
ItemProcessor<Customer, Customer> customerProcessor(
        AtomicBoolean failOnceAt105) {

    return item -> {
        if (item.id() == 105L && failOnceAt105.compareAndSet(true, false)) {
            throw new IllegalStateException("Simulated failure at id=105");
        }
        return item;
    };
}
```

When the processor first sees 105, the flag flips from `true` to `false` and throws an exception. When the Step restarts and reads 105 again, the processor returns the item normally. If tests run multiple times in the same context, reset the flag before each scenario so expected failures are not accidentally skipped.

### 5.4. JDBC writer and Step

```java
@Bean
JdbcBatchItemWriter<Customer> customerWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Customer>()
            .dataSource(dataSource)
            .sql("INSERT INTO imported_customer (id, name) VALUES (:id, :name)")
            .itemSqlParameterSourceProvider(customer ->
                    new MapSqlParameterSource()
                            .addValue("id", customer.id())
                            .addValue("name", customer.name()))
            .build();
}

@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FlatFileItemReader<Customer> customerReader,
        ItemProcessor<Customer, Customer> customerProcessor,
        JdbcBatchItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<Customer, Customer>chunk(3, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .build();
}

@Bean
Job importCustomersJob(JobRepository jobRepository, Step importCustomersStep) {
    return new JobBuilder("importCustomersJob", jobRepository)
            .start(importCustomersStep)
            .build();
}
```

To test **failure then restart**, the Step above omits `.faultTolerant().skip(...)` for `IllegalStateException`. Skipping that exception could allow the Step to end `COMPLETED`, turning the test away from a failure-restart scenario.

The target table should participate in the same transaction management matching the `transactionManager` passed to `chunk(...)`. A unique primary key on `id` both helps verify data completeness and surfaces duplicate writes as clear errors.

## 6. Integration test: prepare data, fail, restart, reconcile results

This example uses `@SpringBatchTest` for `JobLauncherTestUtils`, `@SpringBootTest` to boot the context, and `JdbcTemplate` to read written rows. It assumes the test imports the bean configuration from section 5 and runs the Job synchronously. If the context contains multiple Jobs, set the target `Job` explicitly.

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBatchTest
@SpringBootTest(properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always"
})
class ImportCustomersRestartTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    @Qualifier("importCustomersJob")
    private Job importCustomersJob;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private AtomicBoolean failOnceAt105;

    @BeforeEach
    void setup() {
        jobLauncherTestUtils.setJob(importCustomersJob);
        failOnceAt105.set(true);
        jdbcTemplate.update("DELETE FROM imported_customer");
    }

    @Test
    void shouldRestartFromLastCommittedChunk(@TempDir Path tempDir) throws Exception {
        // Step 1: Prepare an immutable input fixture for the test.
        Path inputFile = tempDir.resolve("customers.csv");
        Files.writeString(inputFile, """
                id,name
                101,An
                102,Binh
                103,Chi
                104,Dung
                105,Ha
                106,Minh
                107,Thao
                """, StandardCharsets.UTF_8);

        // Step 2: Build identifying parameters exactly once.
        JobParameters params = new JobParametersBuilder()
                .addString("inputFile", inputFile.toAbsolutePath().toString(), true)
                .addString("testCaseId", UUID.randomUUID().toString(), true)
                .toJobParameters();

        // Step 3: First run fails at id=105.
        JobExecution firstRun = jobLauncherTestUtils.launchJob(params);
        assertThat(firstRun.getStatus()).isEqualTo(BatchStatus.FAILED);

        // Only the first chunk (101..103) committed.
        assertThat(storedIds()).containsExactly(101L, 102L, 103L);

        StepExecution firstStep = findStep(firstRun, "importCustomersStep");
        assertThat(firstStep.getStatus()).isEqualTo(BatchStatus.FAILED);
        assertThat(firstStep.getWriteCount()).isEqualTo(3);

        // Step 4: Restart with the EXACT same params.
        JobExecution secondRun = jobLauncherTestUtils.launchJob(params);
        assertThat(secondRun.getStatus()).isEqualTo(BatchStatus.COMPLETED);

        // Restart creates a new JobExecution for the same JobInstance.
        assertThat(secondRun.getId()).isNotEqualTo(firstRun.getId());
        assertThat(secondRun.getJobInstance().getInstanceId())
                .isEqualTo(firstRun.getJobInstance().getInstanceId());

        StepExecution secondStep = findStep(secondRun, "importCustomersStep");
        assertThat(secondStep.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(secondStep.getWriteCount()).isEqualTo(4);

        // Step 5: Verify final data; no missing rows, no duplicates.
        assertThat(storedIds()).containsExactly(
                101L, 102L, 103L, 104L, 105L, 106L, 107L);
        assertThat(jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM imported_customer", Long.class))
                .isEqualTo(7L);
    }

    private List<Long> storedIds() {
        return jdbcTemplate.queryForList(
                "SELECT id FROM imported_customer ORDER BY id", Long.class);
    }

    private StepExecution findStep(JobExecution execution, String stepName) {
        return execution.getStepExecutions().stream()
                .filter(step -> stepName.equals(step.getStepName()))
                .findFirst()
                .orElseThrow(() -> new AssertionError(
                        "Missing StepExecution: " + stepName));
    }
}
```

The test requires `spring-batch-test`, the Spring Boot test starter, a JDBC driver, and a test database (such as H2). The `imported_customer` table can be created via `schema.sql` or the project's migration tool; `spring.batch.jdbc.initialize-schema=always` applies only to initializing Batch metadata tables for Spring Boot-supported databases. **Do not** expect that property to create business tables automatically.

In this example, `@BeforeEach` clears the target table **before the first run** so the scenario stays independent. Never wipe the target table or Batch metadata **between `firstRun` and `secondRun`**: doing so destroys the checkpoint or erases traces of committed data, leaving a test that no longer simulates restart.

For stable results, `ItemProcessor` uses a mock flag reset in `setup()`, and `testCaseId` is uniquely generated per test. If the job runs asynchronously, wait for job completion before checking status; this example assumes a synchronous `JobLauncher`.

## 7. What the assertions prove

| Assertion | Meaning |
| --- | --- |
| `firstRun.getStatus() == FAILED` | The injected fault genuinely stopped the first run as a failure. |
| Target table contains only `101, 102, 103` | Chunk 1's transaction committed; the failing chunk left no partial changes in the target table. |
| `firstStep.getWriteCount() == 3` | The first execution recorded three items written successfully. |
| `secondRun.getId() != firstRun.getId()` | Both runs created two distinct `JobExecution`s. |
| Both executions share the same `JobInstance` id | The second run is a restart of the same JobInstance, not a new Job. |
| `secondStep.getWriteCount() == 4` | The restarted Step wrote the remaining four items in this fixture. |
| Target table holds 7 unique IDs | Zero missed items and zero duplicates across the failure and restart boundary. |

In a general job, `readCount` and `writeCount` belong to **each `StepExecution`**, not automatically representing totals across all runs of a JobInstance. In this fixed scenario, the first `writeCount` is 3 and the restart `writeCount` is 4; the 7 rows in the database represent the final overall outcome.

`readCount` on a failed run can be tricky to deduce precisely when failures, transaction rollbacks, or retries happen. Therefore, restart tests focus on **checkpoints, status, committed data, and final output**. Assert exact intermediate counts only when those counts are the specific behavior the test was designed to verify.

## 8. Which restart scenarios should test data cover?

One illustrative fixture is a solid start. To catch real bugs, build multiple datasets targeting **different interruption points**:

| Scenario | Example data and fault position | What to verify after restart |
| --- | --- | --- |
| Failure before first commit | 7 items, chunk 3, fails at item 2 | Target table initially empty; restart reads and writes all 7 items. |
| Failure after at least one commit | 7 items, chunk 3, fails at item 5 | 3 committed items remain intact; remaining 4 items are written. |
| Failure at start of next chunk | 7 items, chunk 3, fails at item 4 | Checkpoint does not skip over item 4. |
| Failure in partial final chunk | 7 items, chunk 3, fails at item 7 | After two chunks commit, restart writes item 7. |
| Filter present in processor | 7 items, one item returns `null` | Filtered item is not mistaken for a lost item; output equals expected set. |
| Skippable exception present | One bad item allowed to skip | If Job still ends `COMPLETED`, that is a skip flow rather than a failed restart. |
| Writer prone to duplicate writes | Re-attempts writing an already-committed item | Unique key or idempotency mechanism blocks duplicate data. |
| Multiple Steps | Step A completes, Step B fails | Completed Step A is typically skipped on restart; Step B reruns. |
| Mutated source data | Rows reordered or added/deleted after failure | Catches violated input-immutability rules; tests system policy instead of assuming safety. |

These cases do not need to be crammed into a single test. Each test should document the fault position, pre-failure dataset, and post-restart expected dataset. When faults happen too early, tests miss bugs that only surface after a checkpoint; when faults happen too late, tests miss bugs in recovering an uncommitted chunk.

## 9. Testing restart with multiple Steps

Suppose a Job has two Steps:

```text
importCustomersJob
  Step A: validateInput     --> COMPLETED
  Step B: importCustomers   --> FAILED (run 1)
```

If Step A already completed under default configuration, restarting in Spring Batch normally **skips Step A** and reruns Step B. That differs from launching a new `JobInstance`, where Step A runs from scratch.

Test data should leave clear evidence of Step A, such as a test audit record with `validationId`. After restart, you can assert the audit row was not written a second time, while the remaining Step B rows are all written.

Note that `.allowStartIfComplete(true)` allows a `COMPLETED` Step to execute again in subsequent runs of the same JobInstance; if enabled, expectations for Step A must adjust. `startLimit(...)` and `.preventRestart()` at the Job level also affect restartability. Test fixtures must align with the **defined restart policy**, never assuming every Step always reruns or always gets skipped.

## 10. Restart test data with `JdbcPagingItemReader` or database sources

When reading from a database, test data selection must account for **ordering and result-set drift**. Example:

```sql
CREATE TABLE source_customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL
);

INSERT INTO source_customer (id, name, status) VALUES
    (101, 'An', 'NEW'),
    (102, 'Binh', 'NEW'),
    (103, 'Chi', 'NEW'),
    (104, 'Dung', 'NEW'),
    (105, 'Ha', 'NEW'),
    (106, 'Minh', 'NEW'),
    (107, 'Thao', 'NEW');
```

If a reader queries `WHERE status = 'NEW'` while the writer/processor immediately flips `status` on processed source rows, the result set on restart **no longer matches the first run**. Depending on paging and checkpoints, the reader can skip records. That is a data-design and read-strategy bug, not something to paper over by hardcoding a `readCount` assertion.

For paging readers, use a stable, unique sort key (commonly `id`) to support deterministic position recovery. If business requirements demand updating the source data while reading, consider snapshots, staging tables, version markers, or a suitable reader strategy, and incorporate those mutations into test data.

A strong dataset also includes out-of-scope records, such as `status = 'DONE'`, proving the reader does not accidentally scan the whole table. Keep out-of-scope rows in a **separate expectation**; never add them to the Step's `readCount`.

## 11. Safe restarts and idempotency testing

In JDBC scenarios, transactions and checkpoints curb duplicate processing within chunks. In integration systems, however, a writer might call an external API, push to a queue, or generate a file while Batch transactions only govern the local database. If the API accepts a request and the Step fails before persisting the checkpoint, restarting can call the API again.

For instance, using the business key `customerId + businessDate` as an **idempotency key** when calling an external system:

```text
Run 1: send customer=104, businessDate=2026-11-15
        -> external system accepts
        -> Batch fails before checkpoint

Restart: resend same customer=104, businessDate=2026-11-15
         -> external system recognizes existing idempotency key
         -> does not create another duplicate record
```

A test dataset for such a writer must simulate **side effects having occurred without a committed checkpoint**. Expectations cover not just `BatchStatus.COMPLETED` but **exactly one business outcome** per key. Database primary keys, upserts, outbox tables, or idempotency keys can provide this guarantee depending on architecture.

## 12. Checklist for preparing restart test data

Before adding a restart scenario to a test suite, explicitly define:

1. **Input dataset:** records, ordering, IDs, and source data version.
2. **Chunk size:** items per chunk and which items sit immediately before/after commit boundaries.
3. **Failure point:** failure in reader, processor, writer, or after a side effect; exact occurrence index.
4. **Failure type:** exception that fails the Step versus one handled by skip/retry configuration.
5. **Checkpoint:** which reader/writer is stateful; where `ExecutionContext` is stored and whether it survives failure.
6. **State after run 1:** which records committed and which remain uncommitted.
7. **Job parameters:** keep identifying parameters identical to restart the right `JobInstance`.
8. **State after restart:** reconcile IDs, values, and total counts; verify zero duplicates and zero gaps.
9. **Isolation:** tests use source data, repositories, and target tables independent of other runs.
10. **Transactionality:** determine whether the target system rolls back with the chunk or needs separate idempotency.

What matters most when designing **data for restart testing** is choosing records and a fault position that clearly expose **pre-failure state and post-restart state**. When a fixture spans a committed chunk, an interrupted chunk, and remaining unprocessed records, the test validates the core promise of Spring Batch restart: **resuming from the proper checkpoint and producing the exact final result**.
