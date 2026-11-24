# Tests That Only Check Exit Code in Spring Batch

## 1. Why Is This a Common Testing Mistake?

A Spring Batch test often starts by launching a Job and checking a single outcome:

~~~java
JobExecution execution = jobLauncherTestUtils.launchJob(parameters);
assertEquals("COMPLETED", execution.getExitStatus().getExitCode());
~~~

This assertion confirms that Spring Batch reported the expected exit code. **It does not prove that the Job processed data properly, wrote complete output, committed cleanly, avoided duplicates, or processed the right business period.**

Suppose a Job must import orders for 2026-11-16. The reader has a bug in its SQL filtering for 2026-11-15 instead. If zero matching records exist and no exception is thrown, the Step still finishes normally. `ExitStatus` is `COMPLETED`, yet **not a single order for the target date was written**. A test checking only the exit code passes falsely.

This lesson belongs to the **Common Pitfalls** group in *Spring Batch Core Processing*. After this lesson, you will know how to:

- Distinguish **OS process exit code**, **BatchStatus**, and **ExitStatus**.
- Recognize when `COMPLETED` does not guarantee accurate business results.
- Verify `JobExecution`, `StepExecution`, and `JobParameters` metadata.
- Verify results in target tables, files, APIs, or message brokers.
- Design fixtures capable of catching wrong periods, wrong tenants, missing records, and duplicates.
- Test filtering, skipping, retrying, transaction rollbacks, and restarts.
- Write integration tests using `@SpringBatchTest` and a JDBC `JobRepository`.
- Avoid premature assertions on asynchronously executed Jobs.

## 2. Three Distinct Signals

| Signal | Where is it read from? | Meaning |
| --- | --- | --- |
| **Process exit code** | Shell, OS, container runtime | Integer returned by the Java process on exit, per application/launcher logic. |
| **BatchStatus** | `JobExecution.getStatus()` | Lifecycle status managed by Spring Batch: `STARTING`, `STARTED`, `COMPLETED`, `FAILED`, `STOPPED`… |
| **ExitStatus** | `JobExecution.getExitStatus()` | Exit code and description used for flow routing or callers; customizable. |

Spring Batch 5.2 example:

~~~java
JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

BatchStatus batchStatus = execution.getStatus();
String exitCode = execution.getExitStatus().getExitCode();
String description =
        execution.getExitStatus().getExitDescription();
~~~

**`ExitStatus` is not the process exit code.** Spring Batch uses strings like `COMPLETED`, `FAILED`, or custom codes; the operating system observes the process's integer return code. An `ExitCodeMapper` or application code may map the string to a number.

~~~text
JobExecution.ExitStatus = "COMPLETED"
           |
           v
Java application / launcher / optional ExitCodeMapper
           |
           v
OS process exit code (e.g., 0)
~~~

A Spring Boot application may stay running after a Job finishes; multiple Jobs can also coexist in one JVM. Therefore, checking `echo $?` equals 0 does not prove a specific Job wrote complete data.

**`BatchStatus` and `ExitStatus` are also not two names for the same property.** `BatchStatus` describes execution lifecycle, whereas `ExitStatus` can be customized to signal flow branching or report special outcomes like `COMPLETED WITH SKIPS`. Both must be interpreted against the Job configuration.

## 3. Green Status, Wrong Result

| Situation | Possible Job status | Missed bug |
| --- | --- | --- |
| Reader filters wrong date | COMPLETED | Target period's data not imported. |
| Query lacks tenant condition | COMPLETED | Imported another tenant's data. |
| Processor returns `null` against rules | COMPLETED | Records unexpectedly filtered out. |
| Step skip policy too broad | COMPLETED | Critical data silently dropped. |
| Writer maps amount incorrectly | COMPLETED | Row count right, monetary values wrong. |
| Target table holds leftover data from prior test | COMPLETED | Test thinks the new Job wrote the rows. |
| Restart with a new identifying `run.id` | COMPLETED | Creates a new `JobInstance`, risking duplicate processing. |
| Exported file missing header or rows | COMPLETED | Artifact unusable downstream. |
| Mock API always returns success | COMPLETED | Payload/idempotency key may be wrong. |
| Required Step skipped due to broken flow | COMPLETED | Job took the wrong branch. |

`COMPLETED` **is usually a necessary condition**, yet **never a sufficient condition** to conclude business processing succeeded.

## 4. Assertion Layers to Include

~~~text
Launch Job with explicit JobParameters
                    |
                    v
             Job/Exit status
                    |
                    v
       JobInstance and execution ID
                    |
                    v
         StepExecution metadata
                    |
                    v
     Output data and business rules
                    |
                    v
       No duplicates, no scope leaks
                    |
                    v
       Transactions/restart if needed
                    |
                    v
             Test verdict
~~~

| Verification layer | Suggested assertions |
| --- | --- |
| Technical outcome | `BatchStatus.COMPLETED`, matching `ExitStatus`, no unexpected failure exceptions. |
| Identity | Right Job name, identifying `JobParameters`, and `JobInstance` ID. |
| Step metadata | Expected Steps ran, Step status, and matching counters. |
| Data | Row counts, business keys, values, relationships, totals, checksums. |
| Negative assertions | No out-of-date or cross-tenant records emitted; out-of-scope data untouched. |
| Transactions | Failing chunk rolls back; committed chunks remain intact. |
| Restart | Same `JobInstance`, new `JobExecution`, zero duplicates. |
| External systems | Accurate HTTP requests/messages, idempotency keys, file publishing. |

You do not need to cram all of these into one method. Split the suite into processor unit tests, Step integration tests, Job integration tests, and recovery tests.

## 5. Test Data Must Be Able to Catch Bugs

Using an empty dataset allows both right code and broken filters to return 0 rows. A fixture should include at least two valid items and one **out-of-scope** item.

Example Job running for `businessDate=2026-11-16`:

| id | business_date | amount | Expectation |
| ---: | --- | ---: | --- |
| 1001 | 2026-11-16 | 120 | Present in output. |
| 1002 | 2026-11-16 | 230 | Present in output. |
| 1003 | 2026-11-15 | 900 | Must NOT be written to output. |

Expectations include **exact IDs 1001 and 1002**, with total amount **350**. If you assert only row count equals 2, the Job could still write two wrong IDs or wrong amounts. Therefore, assert **keys and values**, not just `COUNT(*)`.

In multi-tenant systems, also seed records for tenant B on the same date to test that tenant A's Job does not touch them.

## 6. Integration Example with Spring Batch 5.2 and Spring Boot 3

To focus on the exit-code trap, this example uses a **Tasklet** running a SQL `INSERT ... SELECT`. It clearly shows how SQL returning 0 rows without throwing still lets a Job finish `COMPLETED`.

### 6.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 6.2. Test Schema

File `src/test/resources/batch-test-schema.sql`:

~~~sql
CREATE TABLE source_orders (
    id BIGINT PRIMARY KEY,
    business_date VARCHAR(10) NOT NULL,
    amount BIGINT NOT NULL
);

CREATE TABLE processed_orders (
    id BIGINT PRIMARY KEY,
    business_date VARCHAR(10) NOT NULL,
    amount BIGINT NOT NULL
);
~~~

File `src/test/resources/application-batchtest.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:exitcode_test;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.batch.jdbc.initialize-schema=always
spring.batch.job.enabled=false

spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:batch-test-schema.sql
~~~

Here Spring Boot Batch auto-configuration creates the JDBC `JobRepository` and `BATCH_*` metadata tables. If an application configures its own repository or uses multiple DataSources, explicitly select the repository, transaction manager, and schema scripts. The example omits `@EnableBatchProcessing` because it relies on Boot 3 auto-configuration.

### 6.3. Illustrative Job

File `CopyOrdersJobConfiguration.java`:

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
public class CopyOrdersJobConfiguration {

    @Bean
    Step copyOrdersStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            JdbcTemplate jdbc) {

        return new StepBuilder("copyOrdersStep", repository)
                .tasklet((contribution, chunkContext) -> {

                    String businessDate = contribution
                            .getStepExecution()
                            .getJobParameters()
                            .getString("businessDate");

                    jdbc.update(
                        "INSERT INTO processed_orders " +
                        "(id, business_date, amount) " +
                        "SELECT id, business_date, amount " +
                        "FROM source_orders " +
                        "WHERE business_date = ?",
                        businessDate);

                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
    }

    @Bean
    Job copyOrdersJob(JobRepository repository, Step copyOrdersStep) {
        return new JobBuilder("copyOrdersJob", repository)
                .start(copyOrdersStep)
                .build();
    }
}
~~~

If code queries the wrong date in SQL, it can insert 0 rows yet still return `RepeatStatus.FINISHED`. This is precisely the bug that checking exit code misses.

### 6.4. Weak Test

~~~java
@Test
void weakTest() throws Exception {
    JobParameters params = new JobParametersBuilder()
            .addString("businessDate", "2026-11-16")
            .toJobParameters();

    JobExecution execution = launcherTestUtils.launchJob(params);

    assertEquals("COMPLETED",
            execution.getExitStatus().getExitCode());
}
~~~

The test has no idea what is in `processed_orders`, so it cannot claim the work succeeded per the business contract.

### 6.5. Test Verifying Results

File `CopyOrdersIT.java`:

~~~java
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.*;

@SpringBatchTest
@ActiveProfiles("batchtest")
@SpringBootTest(classes = CopyOrdersIT.TestApplication.class)
class CopyOrdersIT {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(CopyOrdersJobConfiguration.class)
    static class TestApplication {
    }

    @Autowired JobLauncherTestUtils launcherTestUtils;
    @Autowired JobRepositoryTestUtils repositoryTestUtils;
    @Autowired JobRepository jobRepository;
    @Autowired JdbcTemplate jdbc;

    @Autowired
    @Qualifier("copyOrdersJob")
    Job job;

    @BeforeEach
    void prepare() {
        launcherTestUtils.setJob(job);

        // Clean metadata only in an isolated test database.
        repositoryTestUtils.removeJobExecutions();
        jdbc.update("DELETE FROM processed_orders");
        jdbc.update("DELETE FROM source_orders");

        jdbc.update("INSERT INTO source_orders VALUES (?, ?, ?)",
                1001L, "2026-11-16", 120L);
        jdbc.update("INSERT INTO source_orders VALUES (?, ?, ?)",
                1002L, "2026-11-16", 230L);
        jdbc.update("INSERT INTO source_orders VALUES (?, ?, ?)",
                1003L, "2026-11-15", 900L);
    }

    @Test
    void checksStatusAndBusinessOutcome() throws Exception {
        JobParameters params = new JobParametersBuilder()
                .addString("businessDate", "2026-11-16", true)
                .toJobParameters();

        JobExecution execution = launcherTestUtils.launchJob(params);

        // 1. Technical status.
        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertEquals(ExitStatus.COMPLETED.getExitCode(),
                execution.getExitStatus().getExitCode());
        assertTrue(execution.getAllFailureExceptions().isEmpty());

        // 2. Persisted metadata.
        assertEquals("copyOrdersJob",
                execution.getJobInstance().getJobName());

        JobExecution persisted = jobRepository.getLastJobExecution(
                "copyOrdersJob", params);

        assertNotNull(persisted);
        assertEquals(execution.getId(), persisted.getId());
        assertEquals(BatchStatus.COMPLETED, persisted.getStatus());

        // 3. Exact business ID set.
        List<Long> ids = jdbc.queryForList(
                "SELECT id FROM processed_orders ORDER BY id",
                Long.class);
        assertEquals(List.of(1001L, 1002L), ids);

        // 4. Exact total value.
        Long sum = jdbc.queryForObject(
                "SELECT SUM(amount) FROM processed_orders",
                Long.class);
        assertEquals(350L, sum);

        // 5. Source not unintentionally mutated.
        Integer sourceRows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM source_orders",
                Integer.class);
        assertEquals(3, sourceRows);
    }
}
~~~

If the SQL is changed to read Nov 15, the Job still becomes `COMPLETED`, yet the test fails on the ID list and total amount assertions.

**Note:** `removeJobExecutions()` wipes batch history in the database targeted by the utility. Use it only on isolated test databases. Never call it between two executions of the same restart test. For parallel test execution, isolate databases/schemas so tests do not wipe one another's data.

## 7. When a Step Uses Chunks: Check the Appropriate Metadata

The example above used a SQL Tasklet. With a Tasklet, `getReadCount()` and `getWriteCount()` can remain 0 even when SQL inserted 2 rows. Thus you must inspect target data.

With a **chunk-oriented Step**, `StepExecution` provides useful counts:

~~~java
StepExecution step = execution.getStepExecutions().stream()
        .filter(s -> "importOrdersStep".equals(s.getStepName()))
        .findFirst()
        .orElseThrow();

assertEquals(BatchStatus.COMPLETED, step.getStatus());

assertEquals(100, step.getReadCount());
assertEquals(98, step.getWriteCount());
assertEquals(2, step.getFilterCount());

assertEquals(0, step.getReadSkipCount());
assertEquals(0, step.getProcessSkipCount());
assertEquals(0, step.getWriteSkipCount());
~~~

These assertions **illustrate** a Step reading 100 items, filtering 2 items per policy, and writing 98 items; do not apply these numbers to the SQL Tasklet above.

| StepExecution field | Interpretation |
| --- | --- |
| `READ_COUNT` | Items read per Step semantics. |
| `WRITE_COUNT` | Items written per Step semantics. |
| `FILTER_COUNT` | Items filtered by processor returning null. |
| `READ_SKIP_COUNT` | Items skipped by reader per policy. |
| `PROCESS_SKIP_COUNT` | Items skipped in processor. |
| `WRITE_SKIP_COUNT` | Items skipped in writer. |
| `COMMIT_COUNT` | Transaction commits recorded by Step. |
| `ROLLBACK_COUNT` | Rollbacks recorded by Step. |

`writeCount=98` does not guarantee all 98 records have the right amounts. Metadata locates which stage diverged; **business assertions** prove the outcome.

## 8. Filter, Skip, and Retry: COMPLETED Does Not Mean Complete

Suppose out of 100 items:

- 95 items are valid.
- 3 items are filtered by business rule.
- 2 bad items are permitted to skip and routed to quarantine.

A Job can report `COMPLETED` even after skipping 2 items under skip configuration. If the business **forbids skipping**, assert:

~~~java
assertEquals(0, step.getReadSkipCount());
assertEquals(0, step.getProcessSkipCount());
assertEquals(0, step.getWriteSkipCount());
~~~

If skips are permitted, verify the **exact IDs**, reasons, and quarantine entries; never check total skip count alone, as an important item could have been skipped by mistake.

A listener can attach a custom `ExitStatus` such as `COMPLETED WITH SKIPS`. Tests should check that code if it is part of the flow contract, yet still verify `StepExecution` and actual data results.

**Retry count differs from rollback count.** One rollback can reprocess multiple items; an HTTP client may retry several times without a matching Step rollback. Never mislabel `rollbackCount` as retry count.

## 9. Verifying Transactions Using Committed Data

Suppose chunk size is 2; the processor hits a non-retryable exception on item 3:

~~~text
Execution #101
  items 1, 2 -> COMMIT
  item 3     -> error, ROLLBACK chunk
  Job        -> FAILED

Correct output after failure: [1, 2]
~~~

A test checking only `ExitStatus.FAILED` does not prove rollback. Read the data:

~~~java
assertEquals(BatchStatus.FAILED, first.getStatus());

List<Long> ids = jdbc.queryForList(
        "SELECT id FROM target_orders ORDER BY id",
        Long.class);
assertEquals(List.of(1L, 2L), ids);
~~~

This assumes the JDBC writer shares the right transaction resource, the reader has deterministic ordering, and the error is neither skipped nor retried. If the writer calls an HTTP API outside the transaction, a database rollback will not undo already sent side effects.

Avoid annotating an entire integration test with `@Transactional` without considering Batch transactions; the test framework's rollback can obscure real commits under test.

## 10. Restart: Verify JobInstance Instead of Only the Second Run's Exit Code

~~~text
JobInstance #42
 businessDate=2026-11-16
       |
       +-- JobExecution #101: FAILED
       |
       +-- JobExecution #102: COMPLETED
~~~

To prove restart worked properly:

~~~java
assertEquals(BatchStatus.FAILED, first.getStatus());
assertEquals(BatchStatus.COMPLETED, restarted.getStatus());

assertNotEquals(first.getId(), restarted.getId());

assertEquals(
        first.getJobInstance().getInstanceId(),
        restarted.getJobInstance().getInstanceId());
~~~

Pair this with checks that final data is complete, free of duplicates, and that previously completed Steps were skipped per configuration.

If the second run adds a new identifying `run.id`, Spring Batch may create a **new JobInstance**. Seeing `COMPLETED` on the second run does not prove the failed instance's checkpoint was restored.

Once a `JobInstance` is `COMPLETED`, re-running with the same identifying `JobParameters` is normally rejected:

~~~java
// Example in an isolated test with an already COMPLETED Job.
assertThrows(JobInstanceAlreadyCompleteException.class,
        () -> launcherTestUtils.launchJob(sameParameters));
~~~

Also verify the target table was not written again during the rejected call. Never delete `BATCH_*` metadata between failure and restart just to make a test "pass".

## 11. When Output Is a File, API, or Message

**CSV files:** verify file existence, header, encoding, line count, exact IDs/values, CSV escaping, and checksums if needed. Staging `.part` files must not be readable downstream before successful publication.

~~~java
Path output = Path.of(tempDir.toString(), "orders.csv");
List<String> lines = Files.readAllLines(
        output, StandardCharsets.UTF_8);

assertEquals(3, lines.size());  // Header and 2 rows.
assertEquals("id,amount", lines.get(0));
assertTrue(lines.contains("1001,120"));
assertTrue(lines.contains("1002,230"));
~~~

For CSVs with commas, quotes, or newlines inside fields, use a real CSV parser instead of naive string splitting. Isolate test output directories using `@TempDir`.

**HTTP APIs:** verify endpoint, method, body, request count, idempotency key, and fake server state. A mock that blindly returns HTTP 200 without checking payloads can let mapping bugs slip through.

**Message brokers:** verify topic, message key, schema, correlation ID, consumer side effects, or protocol ACKs. Never check only that the producer Job `COMPLETED`.

**Payments:** if the server processed the command yet the client timed out and retried, use a stable idempotency key per business operation and test that the business effect happens only once.

## 12. Async Jobs: Must Wait for Terminal Status

With an asynchronous `TaskExecutor`, the start/launch call can return while the Job is still `STARTED`:

~~~text
Test thread:
  launch -> gets execution ID -> asserts too early

Worker thread:
  read -> process -> write -> COMMIT -> COMPLETED
~~~

Approach:

1. Capture the execution ID.
2. Wait for a terminal status using synchronization or bounded polling.
3. Re-read the persisted `JobExecution` from `JobRepository`/`JobExplorer`.
4. Assert final status and committed output.

Illustrative pseudocode using Awaitility if the project includes the dependency:

~~~java
await().atMost(Duration.ofSeconds(30)).untilAsserted(() -> {
    JobExecution latest = jobExplorer.getJobExecution(executionId);
    assertNotNull(latest);

    BatchStatus s = latest.getStatus();
    assertTrue(s == BatchStatus.COMPLETED
            || s == BatchStatus.FAILED
            || s == BatchStatus.STOPPED);
});

// Continue asserting specific expected status and data.
~~~

Avoid fixed `Thread.sleep` calls as completion conditions. Never infer "launch threw no exception" means the Job processed data successfully.

## 13. Empty Input: COMPLETED May Be Valid

A Job with zero input records is not necessarily an error. Tests must derive from the **business contract**:

| Contract | Expectation when input is empty |
| --- | --- |
| Having no orders that day is normal | `COMPLETED`, empty output, no-data audit if needed. |
| Daily input file is mandatory | `FAILED` or warning code per design. |
| Empty report must still include header | File has exact header and schema. |
| Reconciliation needs data from two sources | Missing one source must be detected. |

Include both an empty-input test **and** a concrete-data test. Testing only the empty case fails to prove reader/processor/writer handle real records properly.

## 14. Mutation Testing Exposes Missing Proof in Tests

On an experimental branch, intentionally inject a small bug:

- Change the date condition in SQL.
- Remove the tenant filter.
- Have the processor filter a valid item.
- Change amount multiplication from ×100 to ×10.
- Write the wrong column or drop a field in an API payload.
- Make the writer create duplicates after restart.

Tests checking only `COMPLETED` may stay green; tests checking **business IDs, values, scope, and idempotency** must turn red. Revert the injected bug afterward.

This is a practical way to evaluate assertion quality: are your tests truly sensitive to the bugs the system must prevent?

## 15. Testing Across Different Layers

| Test level | Primary focus |
| --- | --- |
| `ItemProcessor` unit test | Inputs, outputs, validation, filtering, exceptions. |
| Writer mapping unit test | SQL parameter binding, file lines, API payloads. |
| Step integration | Read/write/filter/skip/rollback and data. |
| Job integration | Flow, `JobParameters`, `JobRepository`, and outcomes. |
| Recovery integration | `FAILED` -> restart, checkpoints, zero duplicates. |
| End-to-end | Downstream receives accurate data; publishing/auditing complete. |

A single small test need not cover everything. However, if **every test** asserts only the exit code, no layer proves business correctness.

## 16. Spring Batch 5.2 and 6.x

| Topic | Spring Batch 5.2.x | Spring Batch 6.x |
| --- | --- | --- |
| Test launcher | `JobLauncherTestUtils.launchJob(params)` | `JobOperatorTestUtils.startJob(params)` |
| Domain packages | Many types under `org.springframework.batch.core` | Split into packages by `job`, `step`, `job.parameters` |
| Tasklet builder | `new StepBuilder(name, repo).tasklet(tasklet, tx)` | Matching 6.x builder API |
| `JobRepository` | Boot 3 can use JDBC auto-configuration | Confirm appropriate JDBC infrastructure; defaults include resourceless config |
| Assertions | Status + metadata + data | **Same principles apply** |

On Spring Batch 6.x, when proving persisted metadata and restart, use a version-appropriate JDBC `JobRepository` and matching schema. A resourceless repository cannot substitute for testing `BATCH_*` table history.

## 17. Test Matrix

| Scenario | Expected status | What to verify beyond status |
| --- | --- | --- |
| 2 valid items | `COMPLETED` | Exact 2 IDs and total amount. |
| Valid empty input | `COMPLETED` | Empty output matching contract. |
| SQL filters wrong period | May be `COMPLETED` | Test must turn red due to missing data. |
| Processor mis-filters | May be `COMPLETED` | Missing output IDs and wrong `filterCount`. |
| Step skips permitted record | May be `COMPLETED` | Quarantine, skip counts, and remaining data. |
| Item fails mid-chunk | `FAILED` | Uncommitted chunk rolled back. |
| Restart after `FAILED` | `COMPLETED` on new execution | Same `JobInstance`; zero duplicates. |
| Re-run `COMPLETED` batch | Rejected | No new side effects. |
| File with bad header | May be `COMPLETED` | File content/schema assertions turn red. |
| API request with wrong body | May be `COMPLETED` | Contract assertions turn red. |
| Async Job | Terminal once awaited | Metadata and output persisted. |

## 18. Common Mistakes

**Asserting only `ExitStatus.COMPLETED`.** Fails to prove data correctness.

**Asserting only process exit code 0.** Process and `JobExecution` do not always map 1:1.

**Asserting only `BatchStatus.COMPLETED`.** The framework does not know your business invariants.

**Empty test fixtures.** Broken queries can still return 0 rows.

**Asserting only `COUNT(*)`.** Right count with wrong IDs/values is still a bug.

**Trusting `read`/`writeCount` on a SQL Tasklet.** Those counters do not automatically measure a Tasklet's SQL effects.

**Ignoring filter and skip counts.** Job finishes after dropping valid records by mistake.

**Using a new identifying `run.id` in restart tests.** Creates a different `JobInstance`.

**Not waiting for async Jobs to finish.** Tests read stale state.

**Not cleaning data between independent tests.** Leftover rows yield false green results.

**Deleting metadata between failure and restart.** Destroys history, checkpoints, and test validity.

**Mocking the writer without real writes while calling it a data integration test.** Tests only wiring and flow.

## 19. Practice Exercises

**Exercise 1 — False Green Test.** Write a Job importing Nov 16 orders and check only exit code. Switch SQL to Nov 15 and demonstrate the test still passes. Add ID/total amount assertions to catch the bug.

**Exercise 2 — Scope Checks.** Seed extra data for another tenant and another date. Ensure output contains zero out-of-scope records, even if total row count happens to match.

**Exercise 3 — Filter/Skip.** Build a Step reading 100 items, filtering 2 and skipping 1 per policy. Verify metadata, output, and quarantine; intentionally break the filter so the test turns red.

**Exercise 4 — Transactions.** With chunk size 2, inject failure on item 3. Verify Job `FAILED` and only items 1 and 2 committed.

**Exercise 5 — Restart.** Disable the failure, restart with the exact same identifying params. Assert same `JobInstance` ID, new execution ID, and complete, duplicate-free final data.

**Exercise 6 — CSV.** Verify header, encoding, schema, IDs, amounts, and that staging files are unpublished until completion.

**Exercise 7 — API.** Simulate server succeeding while client times out. Retry/restart with the same idempotency key and verify the business effect occurs once.

**Exercise 8 — Async.** Use an async executor, wait for terminal status, then inspect data. Compare against a test asserting immediately after start.

## 20. References

- [Spring Batch — Domain Language](https://docs.spring.io/spring-batch/reference/domain.html)
- [Spring Batch 5.2 — Unit Testing](https://docs.spring.io/spring-batch/reference/5.2/testing.html)
- [Spring Batch 6.x — Unit Testing](https://docs.spring.io/spring-batch/reference/testing.html)
- [Spring Batch — Chunk-Oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html)
- [Spring Batch — Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html)
- [Spring Batch — Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html)
- [Spring Batch — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html)
- [Spring Batch — Configuring a JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html)
- [Spring Batch — Meta-Data Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html)
- [Spring Batch 5.2 — JobExecution API](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/JobExecution.html)
- [Spring Batch 5.2 — StepExecution API](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/StepExecution.html)

