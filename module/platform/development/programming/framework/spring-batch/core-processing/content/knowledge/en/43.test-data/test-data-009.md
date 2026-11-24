# Cleaning Up Metadata After Tests in Spring Batch

In **Spring Batch Core Processing**, a Job run does not only read and write business data; it also creates many **metadata** records in `JobRepository`. Metadata records which Job ran, which parameters were used, execution status, how many records each Step processed, and the information needed to restart on failure.

When writing tests, cleaning up metadata after tests prevents independent test runs from accidentally reusing each other's history. However, cleaning up at the wrong moment can break restart tests or wipe results currently in use by another test. This article explains how to clean up metadata using official `spring-batch-test` utilities, how to structure the test lifecycle, and how to distinguish metadata from business data.

## 1. Why does stale metadata affect tests?

Suppose there is a Job `importOrdersJob` with a fixed parameter set:

```text
jobName = importOrdersJob
inputFile = orders-2026-11.csv
batchDate = 2026-11-16
```

On the first run, Spring Batch creates:

```text
Job
└── JobInstance (jobName + identifying JobParameters)
    └── JobExecution #101  [COMPLETED]
        ├── JobExecutionContext
        ├── StepExecution: readOrdersStep    [COMPLETED]
        │   └── StepExecutionContext
        └── StepExecution: persistOrdersStep [COMPLETED]
            └── StepExecutionContext
```

If another test launches the **same Job with the same identifying parameters** against the same repository, Spring Batch recognizes it as a completed `JobInstance`. The usual result is a `JobInstanceAlreadyCompleteException`, because a `COMPLETED` JobInstance cannot be executed again as a new instance.

Other issues caused by leaving stale metadata around include:

- Tests counting Job/Step executions may see earlier runs.
- Restart tests may mistakenly reference an execution no longer belonging to the context under test.
- Data in `ExecutionContext` from an old run can produce unexpected state when intentionally reusing an instance.
- A test suite running repeatedly against the same database becomes execution-order dependent.

**The goal of cleanup is to give each independent test a clean starting state** and release test history that is no longer needed. Metadata is part of the identification and restart mechanism, so understand it before deleting it.

## 2. What does metadata consist of?

In a Spring Batch configuration backed by a relational `JobRepository`, the default schema typically includes the following tables (names/prefixes may vary by version and configuration):

| Table | Main content |
| --- | --- |
| `BATCH_JOB_INSTANCE` | Identity of a JobInstance: Job name and key derived from identifying parameters. |
| `BATCH_JOB_EXECUTION` | Each actual run of the JobInstance, status, and timestamps. |
| `BATCH_JOB_EXECUTION_PARAMS` | JobParameters attached to each JobExecution. |
| `BATCH_JOB_EXECUTION_CONTEXT` | State stored at the JobExecution scope for sharing and restarts. |
| `BATCH_STEP_EXECUTION` | Status and counters of each StepExecution. |
| `BATCH_STEP_EXECUTION_CONTEXT` | State stored at the StepExecution scope. |
| ID-generation tables/sequences | Provide identifier keys for metadata, depending on the database. |

These tables have foreign-key relationships from child records to parent records. Therefore, **do not delete `BATCH_JOB_EXECUTION` alone with a simple `DELETE` statement** while child rows still reference it in context, parameters, or step tables. Manual cleanup must respect dependency order and match the exact schema of the running version.

### Metadata differs from business data

Suppose an order-import Job writes to an `orders` table:

```text
Test database
├── BATCH_JOB_INSTANCE                ← Spring Batch metadata
├── BATCH_JOB_EXECUTION               ← Spring Batch metadata
├── BATCH_STEP_EXECUTION              ← Spring Batch metadata
├── BATCH_*_EXECUTION_CONTEXT         ← Spring Batch metadata
└── orders                            ← business data written by Job
```

Cleaning up metadata **does not mean** deleting rows from `orders`. A test may have wiped Job history completely while still leaving 50 orders from a prior test. Conversely, clearing business tables does not remove `COMPLETED` `JobExecution`s from the repository.

Thus, the test lifecycle must manage **two separate data groups**:

1. Spring Batch metadata: use `spring-batch-test` utilities or controlled repository cleanup.
2. Business data, output files, messages, caches: use fixtures, SQL, test repositories, or temporary resources suited to the application.

## 3. Primary tool: `JobRepositoryTestUtils`

The `spring-batch-test` library provides `JobRepositoryTestUtils` to clean up JobExecutions stored in a test repository. The most commonly used API is:

```java
jobRepositoryTestUtils.removeJobExecutions();
```

This method deletes metadata for Job executions accessible via the repository/explorer, including related details for those executions. For tests running against a **completely dedicated database**, it is the simplest way to start the next test run free from old JobInstances.

Required test-scope dependencies:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
```

When using Spring Boot, dependency versions should be managed consistently by the project's BOM. Without Boot, configure JUnit 5, Spring Test, and Spring Batch accordingly.

The `@SpringBatchTest` annotation registers test support components, including `JobRepositoryTestUtils`. Combine it with `@SpringBootTest` when launching an actual Job inside an application context:

```java
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class BatchMetadataTest {

    @Autowired
    private JobRepositoryTestUtils jobRepositoryTestUtils;

    // Test methods and lifecycle methods in the following sections.
}
```

`spring.batch.job.enabled=false` prevents Spring Boot from auto-launching Jobs when building the test context. The test decides **when** to launch the Job, with which parameters, and **when** to clean up metadata.

> Important scope note: `removeJobExecutions()` does not mean "delete only data from the current JUnit test class". It can remove executions across **multiple Jobs** in the same repository. Use full cleanup only when the test owns a dedicated schema/database or when guaranteed no other test runs against that repository.

## 4. Put cleanup in `@BeforeEach` or `@AfterEach`?

Both lifecycle hooks are useful, serving different purposes.

| Hook | Timing | Value in tests |
| --- | --- | --- |
| `@BeforeEach` | Before each test method | Clears leftover history from previous runs, establishing predictable preconditions. |
| `@AfterEach` | After each test method | Deletes metadata created by the just-finished test, even when an assertion fails and JUnit runs teardown normally. |
| `@BeforeAll` / `@AfterAll` | Before/after the entire class | Fits cases where methods intentionally share history or each class owns its own database; requires explicitly managing inter-method dependencies. |

Minimal example:

```java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class BatchCleanupLifecycleTest {

    @Autowired
    private JobRepositoryTestUtils jobRepositoryTestUtils;

    @BeforeEach
    void clearStaleBatchMetadata() {
        jobRepositoryTestUtils.removeJobExecutions();
    }

    @AfterEach
    void clearCreatedBatchMetadata() {
        jobRepositoryTestUtils.removeJobExecutions();
    }
}
```

This is an illustrative lifecycle structure; a real class will add `@Test` methods to launch the Job and assert results. You do not always need both hooks:

- Use `@BeforeEach` when a test must start from a clean repository, even after an aborted test run where the prior `@AfterEach` never executed.
- Use `@AfterEach` to ensure each test's data is released immediately after verification finishes.
- Use both in an **isolated** test database if you want two layers of defense. Cleanup cost is typically small in focused test suites, though it can become noticeable if test metadata grows huge.

Never place cleanup between steps of **the same restart test**: the later step must read back the JobInstance, ExecutionContext, and history from the earlier step.

## 5. Complete example: run a Job then clean up metadata

The example below uses **Spring Batch 5.x**, JUnit Jupiter, AssertJ, and Spring Boot 3.x. It assumes the application defines a `Job` bean named `importOrdersJob` along with valid fixture data so the Job completes with `COMPLETED`.

```java
import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class ImportOrdersJobIT {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JobRepositoryTestUtils jobRepositoryTestUtils;

    @Autowired
    @Qualifier("importOrdersJob")
    private Job importOrdersJob;

    @BeforeEach
    void prepare() {
        // Safe only because this is a dedicated test JobRepository.
        jobRepositoryTestUtils.removeJobExecutions();

        // Specify the target Job if the application context has multiple Jobs.
        jobLauncherTestUtils.setJob(importOrdersJob);

        // Prepare input and business data here.
    }

    @Test
    void shouldCompleteWithCleanMetadata() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("testRunId", UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertThat(execution.getStatus())
                .isEqualTo(BatchStatus.COMPLETED);
    }

    @AfterEach
    void cleanup() {
        // Runs after assertions: JobExecution can still be inspected in the test.
        jobRepositoryTestUtils.removeJobExecutions();

        // Clean up business data / fixture files via a separate mechanism.
    }
}
```

The flow proceeds as follows:

```text
@BeforeEach
  ├─ Remove leftover metadata in the test repository
  ├─ Select the target Job
  └─ Prepare input data
@Test
  ├─ Build JobParameters
  ├─ launchJob(parameters)
  ├─ Spring Batch persists metadata
  └─ Assert JobExecution.status == COMPLETED
@AfterEach
  ├─ Remove created Job/Step metadata
  └─ Release business data / temporary files
```

Here, a fresh `testRunId` on each run keeps **JobInstance**s independent even if the repository has not been wiped. Meanwhile, cleanup ensures the test leaves no history for subsequent runs. Both mechanisms complement each other while serving distinct roles.

If the Job requires `inputFile`, `businessDate`, or other business parameters, supply them along with the corresponding fixtures; `testRunId` alone does not make an arbitrary Job succeed.

### Depending on Spring Batch version

In **Spring Batch 6.x**, the test launcher utility is `JobOperatorTestUtils` with `startJob(parameters)`. Cleanup continues to center on `JobRepositoryTestUtils`:

```java
@Autowired
private JobOperatorTestUtils jobOperatorTestUtils;

@Autowired
private JobRepositoryTestUtils jobRepositoryTestUtils;

@Test
void shouldRun() throws Exception {
    jobOperatorTestUtils.setJob(importOrdersJob);
    JobExecution execution =
            jobOperatorTestUtils.startJob(parameters);

    assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
}

@AfterEach
void cleanup() {
    jobRepositoryTestUtils.removeJobExecutions();
}
```

This excerpt assumes a test configured with `@SpringBatchTest`, `@SpringBootTest`, an `importOrdersJob` bean, `parameters`, and AssertJ. When writing full code for Spring Batch 6, update `Job`/`JobExecution` imports to `org.springframework.batch.core.job` packages and `JobParameters` to `org.springframework.batch.core.job.parameters`. Differences in the launcher utility do not change the principle: **wait for the Job to finish, assert, and only then clean up metadata**.

## 6. Scoping cleanup properly: full repository or a set of executions?

### 6.1. Dedicated test repository

If each test suite has its own database, `removeJobExecutions()` is usually the most practical choice:

```java
@AfterEach
void clean() {
    jobRepositoryTestUtils.removeJobExecutions();
}
```

This approach is easy to use, avoids writing custom SQL following foreign-key graphs, and keeps test code focused on Job behavior.

### 6.2. Repository shared by multiple Jobs/tests

When multiple tests share one schema, deleting all metadata risks interfering with other Jobs. Some Spring Batch versions also offer overloads accepting a collection of `JobExecution`s to scope deletion to specific executions:

```java
// Illustrative example of scoping cleanup when supported by the version's API.
// jobRepositoryTestUtils.removeJobExecutions(executionsCreatedByThisTest);
```

Even when scoping by execution, consider restarts belonging to the same `JobInstance`. Cleaning out of order or missing an execution can leave metadata inconsistent. The most reliable approach for concurrent tests remains **giving each test suite its own database/schema**.

In real projects, a "dedicated repository" can be:

- An in-memory database living only for the lifetime of the test context.
- A dedicated database/container for a group of integration tests.
- A dedicated schema per parallel test worker, with `JobRepository` pointing to that schema.

**Never run `removeJobExecutions()` against a JobRepository shared with production, staging, or live batch runs.** Job history is vital operational data needed for retries, restarts, reconciliation, and incident investigation.

## 7. Restart tests: when metadata must be kept within the same test

Restarts are the classic example of **not cleaning up metadata prematurely**. Suppose a Job fails midway on its first run, then input is fixed and it resumes from the checkpoint.

```text
JobInstance (same identifying parameters)
├── JobExecution #201 -> FAILED
│   └── StepExecution holding ExecutionContext/checkpoint
└── JobExecution #202 -> COMPLETED (restart same JobInstance)
```

Proper sequence in a test:

1. Prepare input to trigger a controlled failure.
2. Run the Job with fixed **identifying JobParameters** and assert the first run `FAILED`.
3. Resolve the failure condition; **preserve metadata** from the first run.
4. Re-launch/restart via the configured mechanism; assert the second run `COMPLETED` and business output matches.
5. After all assertions finish, remove metadata in `@AfterEach`.

Logical structure example:

```java
@Test
void restartAfterTransientFailure() throws Exception {
    JobParameters sameParameters = /* fixed identifying parameters */;

    // Test data causing the Step to fail in a controlled way.
    prepareFailingInput();

    JobExecution first = jobLauncherTestUtils.launchJob(sameParameters);
    assertThat(first.getStatus()).isEqualTo(BatchStatus.FAILED);

    // Do not call removeJobExecutions() here!
    repairInput();

    // The Job must be configured as restartable and the failure condition resolved.
    JobExecution restarted =
            jobLauncherTestUtils.launchJob(sameParameters);
    assertThat(restarted.getStatus())
            .isEqualTo(BatchStatus.COMPLETED);
}

// @AfterEach cleans up metadata for both runs afterward.
```

This illustration uses Spring Batch 5.x APIs and two project fixture helpers (`prepareFailingInput`, `repairInput`). Depending on Job configuration, restart may go through `JobOperator`; the prerequisite is that the first run fails in a **restartable** way and the identifying parameters determining the JobInstance remain identical.

Wiping metadata between the failure and the restart turns the next run into a fresh execution or wipes the checkpoint. The test then stops testing real restartability.

## 8. Cleanup does not replace business data management

Consider a test for a Job that reads CSV and writes to `orders`. If you only have:

```java
@AfterEach
void cleanup() {
    jobRepositoryTestUtils.removeJobExecutions();
}
```

then orders inserted by the Job can remain in the database. Subsequent tests reading and writing the same table will be affected.

One option in Spring Boot projects is `@Sql` with SQL targeting business tables:

```java
import org.springframework.test.context.jdbc.Sql;

@Sql(
    scripts = "/sql/clean-orders-test-data.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
class ImportOrdersJobIT {
    // ...
}
```

The `clean-orders-test-data.sql` script is authored by the project to delete **fixture data** in `orders` and dependent tables; the SQL must match the business schema and foreign-key rules.

Other options:

| Data type | Appropriate cleanup |
| --- | --- |
| Job/Step metadata | `JobRepositoryTestUtils` on a dedicated test repository. |
| Orders/products tables written by Job | Test SQL, truncate in test schema, repository fixtures, or reset test database. |
| Input/output files | Temporary path per test; delete temp files/dirs at the end. |
| Message queues/caches | Isolated destination or namespace; clean using the corresponding test tool. |
| ID sequences | Usually no need to reset for state assertions; avoid depending on exact ID numbers. |

`@DirtiesContext` only tells Spring Test to rebuild the application context. If `JobRepository` uses an external persistent database, that annotation **does not automatically delete metadata records**.

Similarly, placing `@Transactional` on a test method does not mean all Job transactions roll back when the test finishes. Spring Batch manages transactions at Step/chunk boundaries. To verify and clean up post-Job results, use explicit fixture lifecycle controls for each resource type.

## 9. Parallel tests and asynchronous tests

### Parallel tests sharing a repository

Suppose Test A is running a Job while Test B calls `removeJobExecutions()` on the same schema:

```text
Test A:  startJob ─── write StepExecution ───── finish
Test B:             removeJobExecutions()
                              ↑
                    May delete metadata Test A currently needs
```

This causes flaky failures or wrong results because Test B wipes Test A's history. Ways to reduce contention include isolating databases/schemas per worker or disabling parallel execution for test groups sharing a repository. Using an ordering annotation inside one class will not stop another class running concurrently.

### Asynchronous Job execution

If a Job launches via an asynchronous `TaskExecutor`, the launch call may return while `JobExecution` is still `STARTING`/`STARTED`. **Do not clean up metadata immediately** while the Job is still running. Wait for a terminal status using bounded polling/await and re-read status from `JobExplorer`/repository. For typical integration tests, synchronous execution keeps lifecycle and cleanup much simpler.

Deleting metadata mid-run can break execution context updates, Step status, or JobExecution writes. Cleanup in `@AfterEach` is safe only once the test has confirmed the Job truly finished before teardown runs.

## 10. Common errors and how to tell them apart

### `JobInstanceAlreadyCompleteException` when running tests multiple times

**Common cause:** the same Job + same identifying parameters already completed in the repository. For independent tests, use fresh identifying parameters and clean the test repository at the right scope. For restart tests, do not arbitrarily change identifying parameters; design the test to intentionally resume a failed instance.

### Metadata is clean yet tests still see old data

**Cause:** business data lives outside metadata tables. Clean domain tables/repositories and file fixtures separately; do not expect `JobRepositoryTestUtils` to manage business tables.

### Metadata cleanup breaks restart tests

**Cause:** calling cleanup before restarting wipes the `JobInstance` and checkpoint. Move cleanup to the end of the test, after inspecting every related `JobExecution`.

### Foreign-key error when running `DELETE FROM BATCH_JOB_EXECUTION`

**Cause:** child context, parameters, or StepExecution rows still reference it. Use `JobRepositoryTestUtils` with a matching test schema, or write custom SQL respecting the exact schema dependency order. Never disable foreign keys arbitrarily just to "force a delete".

### Test passes alone but fails in the full suite

**Likely cause:** classes share a repository, fixture, file, or JobParameters; one test's cleanup deletes another's data. Isolate resources or serialize tests that cannot be isolated.

### JobExecution IDs keep increasing after cleanup

**Explanation:** deleting metadata rows does not necessarily reset ID sequences/tables. What matters is that no unexpected executions remain in the test scope, **not** that new IDs always restart from 1.

### Stale records exist despite `@AfterEach`

**Possibilities:** a previous run was forcefully killed so teardown never ran; the test uses a different database than the one being inspected; cleanup ran before an async Job completed; or another process wrote metadata concurrently. Check datasource/job repository configuration and test ownership boundaries.

## 11. A maintainable test organization pattern

For Spring Batch integration suites with multiple Jobs, structure base classes/fixtures around these principles:

```text
BatchIntegrationTest
├── Dedicated datasource/schema for tests
├── @SpringBatchTest + Spring test context
├── @BeforeEach
│   ├── Clean stale metadata
│   └── Reset business data and input fixtures
├── @Test
│   ├── Launch Job
│   ├── Assert JobExecution / StepExecution
│   └── Assert business output
└── @AfterEach
    ├── Wait for Job completion (if asynchronous)
    ├── Clean metadata
    └── Clean temporary test resources
```

If a test involves multiple related executions (such as retry/restart), keep those runs **within the same test method** or manage dedicated fixtures so no cleanup runs in between.

For scenarios needing failure diagnostics, capture diagnostic details **before** deleting metadata. For example, include status, exit description, failure exceptions, and step counters in test assertion messages/logs. Once cleanup runs, do not rely on querying that `JobExecution` back from the database.

## 12. Practice exercises

Suppose `importPaymentsJob` reads 8 payment records from a test file and persists 8 valid rows into the database.

**Scenario A – Independent test:**

1. Create a test database/schema and an 8-transaction fixture.
2. Add `@BeforeEach` to clean metadata and `payments` data before launching.
3. Run `importPaymentsJob` with a distinct identifying parameter.
4. Assert `JobExecution.getStatus()` equals `BatchStatus.COMPLETED`; verify 8 output rows.
5. In `@AfterEach`, call `JobRepositoryTestUtils.removeJobExecutions()` and clean fixture files.
6. Run the same test twice to verify the second run is unaffected by the first run's metadata.

**Scenario B – Restart test:**

1. Create input causing the Job to fail at record 5.
2. Run the Job the first time and assert `FAILED`.
3. Fix the failure condition and restart with the same identifying parameters.
4. Assert the second execution is `COMPLETED` and verify output data has zero duplicates.
5. Clean up metadata only after all scenario assertions complete.

Both scenarios illustrate the core rule: **independent tests need clean history; restart tests intentionally retain history until verification finishes**.

## Key takeaways

- `JobRepository` stores metadata required to identify JobInstances, track JobExecution/StepExecution, and support restarts.
- `JobRepositoryTestUtils.removeJobExecutions()` is the primary tool for cleaning metadata in a **dedicated test repository**.
- `@BeforeEach` establishes consistent initial state; `@AfterEach` frees history once assertions complete.
- Metadata cleanup does not replace clearing business data or non-database resources.
- Never clean up between runs of a restart test, and never clean up while a Job is still running.
- For parallel tests, **isolating repositories/schemas** is the safest foundation for full cleanup.

## Further reading

- [Spring Batch Reference – Unit Testing](https://docs.spring.io/spring-batch/reference/testing.html) – `@SpringBatchTest` and test utilities.
- [Spring Batch Reference – Meta-Data Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html) – roles and relationships of metadata tables.
- [Spring Batch Reference – Configuring a JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html) – repository configuration.
- [Spring Batch API – `JobRepositoryTestUtils`](https://docs.spring.io/spring-batch/docs/5.2.4/api/org/springframework/batch/test/JobRepositoryTestUtils.html) – utility for cleaning executions in tests.

