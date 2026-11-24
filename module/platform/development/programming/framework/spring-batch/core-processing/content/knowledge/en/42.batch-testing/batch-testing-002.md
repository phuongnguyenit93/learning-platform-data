# JobRepositoryTestUtils in Spring Batch Testing

## 1. What Problem Does JobRepositoryTestUtils Solve?

When testing a Spring Batch application, we often need control over **job run metadata**: which `JobInstance` records exist, how many `JobExecution` records there are, which steps were recorded, and whether data from a previous run affects the next run. `JobRepositoryTestUtils` is a utility in the `spring-batch-test` module designed to **quickly create and clean up batch execution records in `JobRepository`**.

This class resides in the package:

```java
org.springframework.batch.test.JobRepositoryTestUtils
```

Its two main tasks are:

1. **Preparing test data:** creating sample `JobExecution` and `StepExecution` records, persisted through `JobRepository`, to test components that read or process metadata.
2. **Cleaning state between tests:** deleting old batch records so subsequent runs with the same job name and parameter set are not affected by prior history.

This is a utility for manipulating **metadata**, not a tool for directly executing `ItemReader`, `ItemProcessor`, `ItemWriter` logic, or a full `Job`. Calling `createJobExecutions(...)` creates records simulating execution history; it **does not actually run the steps**. To verify end-to-end data processing results, run the job using the appropriate launch utility and inspect the output.

### Relationships Between Batch Objects

```text
Job (job definition)
  |
  +-- JobInstance (jobName + identifying JobParameters)
        |
        +-- JobExecution #1 (one execution attempt)
        |     +-- StepExecution: readStep
        |     +-- StepExecution: writeStep
        |
        +-- JobExecution #2 (a retry/restart attempt)
              +-- StepExecution: readStep
              +-- StepExecution: writeStep
```

- `JobInstance` represents a logical job run identified by the job name and **identifying job parameters**.
- `JobExecution` represents a single execution attempt of that instance; one instance can have multiple executions when restarted.
- `StepExecution` stores the status, counters, and details of a single step execution.
- `JobRepository` manages persisting and retrieving metadata; `JobExplorer` provides APIs for reading and querying metadata.

With a typical JDBC repository, metadata resides in tables such as `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_JOB_EXECUTION_PARAMS`, `BATCH_JOB_EXECUTION_CONTEXT`, `BATCH_STEP_EXECUTION`, and `BATCH_STEP_EXECUTION_CONTEXT`. Foreign key relationships across these tables are why metadata cleanup should use a utility that understands Spring Batch's schema rather than arbitrarily deleting a single table.

## 2. Key APIs

| Method | Function | Use Case |
| --- | --- | --- |
| `createJobExecutions(int count)` | Creates `count` sample executions; each execution has one step execution | Quickly needing a few metadata records without caring about specific job/step names |
| `createJobExecutions(String jobName, String[] stepNames, int count)` | Creates `count` sample executions with the specified job name and list of step names | Testing execution history queries for a specific job or step |
| `removeJobExecution(JobExecution execution)` | Deletes a specified execution along with its associated step executions | Cleaning up a single run; consider remaining `JobInstance` records |
| `removeJobExecutions(Collection<JobExecution> executions)` | Deletes the specified collection of executions along with related metadata | Accurately cleaning up only the data created by a single test |
| `removeJobExecutions()` | Deletes **all** job/step execution metadata managed by the utility in the current repository | Resetting a repository dedicated to a test environment |
| `setJobParametersIncrementer(JobParametersIncrementer incrementer)` | Sets the parameter increment mechanism when creating multiple sample executions | Controlling how identifying parameter sets are generated |
| `setJobRepository(JobRepository repository)` | Assigns the repository used by the utility | Manual configuration when not using a bean provided by the test context |

**Deletion scope should be read carefully:** `removeJobExecutions()` is a broad operation with no job-name filter in its method signature. On a shared repository, it can delete metadata belonging to other tests or jobs. According to API documentation, `removeJobExecution(...)` focuses on deleting a single `JobExecution` and its associated `StepExecution` records; do not assume this single method always deletes the `JobInstance` as well. When you want to clean up all objects created for a test, `removeJobExecutions(Collection)` is usually more suitable.

Execution creation methods may throw `JobExecutionAlreadyRunningException`, `JobRestartException`, or `JobInstanceAlreadyCompleteException` if the repository determines that creating the execution is invalid given the existing state and parameters. This is also a sign to check how test data is isolated.

## 3. Adding Dependencies and Initializing the Utility

### Dependencies

For a Spring Boot project using Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2' // Only needed when using H2 for tests
}
```

In Maven, the key direct dependency is:

```xml
<dependency>
    <groupId>org.springframework.batch</groupId>
    <artifactId>spring-batch-test</artifactId>
    <scope>test</scope>
</dependency>
```

If the project uses the Spring Boot BOM or a corresponding Spring Batch BOM, let the BOM manage versions to avoid assigning incompatible Spring Batch artifact versions.

### Registering JobRepositoryTestUtils in the Spring TestContext

The most common approach is to annotate the test class with `@SpringBatchTest` and load a configuration containing the Spring Batch beans:

```java
@SpringBatchTest
@SpringJUnitConfig(BatchTestConfiguration.class)
class BatchMetadataTest {

    @Autowired
    private JobRepositoryTestUtils jobRepositoryTestUtils;

    // Place @Test methods here
}
```

`BatchTestConfiguration` in the example is the project's configuration class; it needs to provide the batch infrastructure, particularly `JobRepository` and required infrastructure beans. For JDBC-based tests, the test DataSource must be connected to a database initialized with Spring Batch metadata tables. `@SpringBootTest` can be used instead of `@SpringJUnitConfig` when loading the entire application is needed.

`@SpringBatchTest` registers a `jobRepositoryTestUtils` bean in the test context, so `@Autowired` is normally all you need. If you want to use it without the annotation, you can instantiate the utility using the constructor taking a `JobRepository`:

```java
JobRepositoryTestUtils utils = new JobRepositoryTestUtils(jobRepository);
```

The constructor taking `JobRepository` is compatible with both Spring Batch 5.2 and 6.x. Do not assume the no-argument constructor is available when writing code intended to run on Spring Batch 6.x.

### Distinguishing the Two Version Lines

| Aspect | Spring Batch 5.x | Spring Batch 6.x |
| --- | --- | --- |
| Metadata manipulation utility | `JobRepositoryTestUtils` | `JobRepositoryTestUtils` |
| Utility commonly used to run jobs in tests | `JobLauncherTestUtils` | `JobOperatorTestUtils` |
| `JobExecution` import | `org.springframework.batch.core.JobExecution` | `org.springframework.batch.core.job.JobExecution` |
| Test platform | JUnit Jupiter supported | JUnit Jupiter preferred; JUnit 4 is no longer supported per 6.0 documentation |

Therefore, when copying examples from older projects, check the **version and package imports** before concluding that `JobRepositoryTestUtils` has an error.

## 4. Example: Creating Metadata and Verifying with JobExplorer

Suppose you want to test a screen or service that displays invoice processing history. Without running the actual job yet, we only need two executions of the `invoiceImportJob` job, each recording two steps: `readInvoices` and `writeInvoices`.

The JUnit 5 example below uses `var` so the test body can apply across Spring Batch versions with different `JobExecution` packages:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.batch.core.repository.explore.JobExplorer;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringBatchTest
@SpringJUnitConfig(BatchTestConfiguration.class)
class JobRepositoryMetadataTest {

    @Autowired
    private JobRepositoryTestUtils repositoryTestUtils;

    @Autowired
    private JobExplorer jobExplorer;

    @Test
    void taoLichSuThucThiDeKiemThuTruyVan() throws Exception {
        var created = repositoryTestUtils.createJobExecutions(
                "invoiceImportJob",
                new String[] {"readInvoices", "writeInvoices"},
                2
        );

        try {
            assertEquals(2, created.size());

            for (var execution : created) {
                assertNotNull(execution.getId());
                assertEquals(
                        "invoiceImportJob",
                        execution.getJobInstance().getJobName()
                );

                var persisted = jobExplorer.getJobExecution(execution.getId());
                assertNotNull(persisted);
                assertEquals(2, persisted.getStepExecutions().size());
            }
        } finally {
            repositoryTestUtils.removeJobExecutions(created);
        }
    }
}
```

**Execution sequence:**

1. `createJobExecutions(...)` asks the repository to create two executions with the specified job name and corresponding step executions.
2. The returned objects have IDs assigned by the repository, allowing verification that this metadata was created in the repository infrastructure.
3. `JobExplorer.getJobExecution(id)` reads the record back from the repository; this is a useful check for history-querying components.
4. The `finally` block cleans up the executions created by the test itself, even if an assertion throws an error.

The example assumes `BatchTestConfiguration` configures a real `JobRepository` capable of persisting and reading data, along with a `JobExplorer` pointing to **the exact same metadata source**. If using a non-persistent repository or two different DataSources, the read-back check will not behave as expected.

Note that the names `readInvoices` and `writeInvoices` here are only recorded as **sample StepExecution names**. Neither step runs; no invoice records are read, transformed, or written to any output simply by calling `createJobExecutions(...)`.

## 5. Example: Cleaning Metadata Before an Integration Test That Runs a Real Job

Suppose `invoiceImportJob` ran successfully with identifying parameters `businessDate=2026-01-15`. If another test re-runs the **same job and same parameter set**, Spring Batch may treat it as an already completed `JobInstance` and refuse to launch it as a new instance. This behavior protects framework consistency, but it makes tests dependent on leftover history.

In a database **dedicated solely to one test class or a controlled sequential test suite**, you can clean metadata before each run:

```java
@SpringBatchTest
@SpringJUnitConfig(BatchTestConfiguration.class)
class InvoiceJobIntegrationTest {

    @Autowired
    private JobRepositoryTestUtils repositoryTestUtils;

    @BeforeEach
    void clearBatchHistory() {
        repositoryTestUtils.removeJobExecutions();
    }

    // @Test runs the actual job and verifies BatchStatus/ExitStatus/output
}
```

If using Spring Boot and you want to prevent jobs from running automatically as soon as the test context starts, configure the test environment specifically:

```properties
spring.batch.job.enabled=false
spring.batch.jdbc.initialize-schema=always
```

Schema initialization properties should only be enabled when appropriate for how the project manages test databases. The snippet above is usually suitable for H2 or ephemeral test databases; if the schema is created by Flyway/Liquibase, use the existing migration process to avoid double creation.

For **Spring Batch 6.x**, real job tests typically use `JobOperatorTestUtils.startJob(...)`. In **Spring Batch 5.x**, documentation and older projects typically use `JobLauncherTestUtils.launchJob(...)`. Whichever launch mechanism is used, `JobRepositoryTestUtils` retains its role in managing test input/output metadata.

**Important:** deleting batch metadata does not delete business data written by the job, such as an `INVOICE` table, CSV files, queues, or storage objects. A complete integration test must prepare and clean up those resources itself. Deleting `BATCH_JOB_EXECUTION` alone cannot make tests independent if old output remains.

## 6. Choosing the Right Cleanup Granularity

### Deleting Only Executions Created by the Test

When a test only creates metadata using `createJobExecutions(...)`, save the returned list and pass it back to `removeJobExecutions(Collection)`:

```java
var executions = repositoryTestUtils.createJobExecutions(
        "testOnlyJob",
        new String[] {"testStep"},
        3
);

try {
    // Perform queries/assertions on the three executions.
} finally {
    repositoryTestUtils.removeJobExecutions(executions);
}
```

This clearly expresses **test data ownership**. It is suitable when multiple jobs share metadata in the repository and you only need to clean up data for the scenario under test. However, for `JobInstance` records with multiple interrelated executions, understand the state of remaining records before deleting part of the history.

### Deleting a Single JobExecution

```java
repositoryTestUtils.removeJobExecution(oneExecution);
```

This method is useful when needing to clean up one specific execution. The API describes deleting the `JobExecution` and its associated `StepExecution` records. Do not rely on it as a full `JobInstance` reset; if the test requires a completely clean repository state, use a cleanup strategy aligned with the entire metadata lifecycle.

### Resetting the Entire Repository

```java
repositoryTestUtils.removeJobExecutions();
```

Choose this only when certain the repository belongs exclusively to tests and is not shared with other work. When running tests in parallel against the same database, test A may delete metadata that test B just created. To prevent this, prefer **an independent database/schema per test suite**, or separate integration tests that perform reset operations.

## 7. JobParameters, Uniqueness, and Simulating Restarts

Spring Batch does not distinguish two `JobInstance` records merely by the API invocation timestamp. Identity is determined by **job name plus identifying parameters**. For example:

| Invocation | Job name | Identifying parameters | Meaning |
| --- | --- | --- | --- |
| A | `invoiceImportJob` | `businessDate=2026-01-15` | First JobInstance |
| B | `invoiceImportJob` | `businessDate=2026-01-16` | Different JobInstance |
| C | `invoiceImportJob` | `businessDate=2026-01-15` | Same JobInstance as A; a rerun/restart if status permits |

When creating multiple sample metadata records, `JobRepositoryTestUtils` can use a `JobParametersIncrementer` to generate successive parameter sets. You can replace this mechanism via `setJobParametersIncrementer(...)` when test scenarios require a specific rule. If your custom incrementer always returns the same identifying parameters, sample executions may collide on the same instance or fail due to prior running/completed state.

**Distinguish two testing goals:**

- **Testing metadata queries:** creating sample executions with `createJobExecutions(...)` is fast and sufficient when you only need historical records.
- **Testing real restarts:** you need to run the job, cause it to stop or fail in a controlled state, save the required `ExecutionContext`, and restart it according to Spring Batch's contract. Simply creating a few sample executions does not prove checkpoint logic, commit/rollback behavior, or reader/writer restartability.

Deleting metadata of a failed run can also cause the next run to be treated as a **new job** instead of a restart; at that point, the `ExecutionContext` state used to resume progress is gone. Therefore, do not use `removeJobExecutions()` to "fix" a failing restart test: determine upfront whether you want to test a **fresh run** or a **resume from checkpoint**.

## 8. Transaction Lifecycle and Isolation Level

`JobRepositoryTestUtils` performs operations that actually modify metadata; results are affected by the transaction manager, DataSource, and test transaction scope.

Some practical rules:

1. **Same DataSource/schema:** `JobRepository`, `JobExplorer`, and test utilities must operate on the same metadata store when creating and reading back data.
2. **Do not assume rollback always cleans up:** in tests annotated with `@Transactional`, creations/deletions may participate in the current transaction or use separate propagation from repository configuration. Choose appropriate setup/cleanup timing and verify the application's transaction boundaries.
3. **Do not reset while another job is running:** deleting metadata of a still-active job can leave the repository no longer reflecting actual executions and affect orchestration logic.
4. **Do not use a shared production/staging database:** this utility is intended for tests and contains very broad deletion methods.
5. **Do not confuse metadata status with output:** a `COMPLETED` status on an execution does not automatically verify business records, row counts written, or output data quality.

When using a newly created test database per run, the simplest pattern is usually: create schema → load fixtures → run tests → destroy database. When a database is reused, establish a clear cleanup policy and prevent parallel tests from accidentally deleting each other's data.

## 9. Comparison with Other Testing Utilities

| Tool | Primary Responsibility | When to Use |
| --- | --- | --- |
| `JobRepositoryTestUtils` | Create/delete `JobExecution` and `StepExecution` metadata | Preparing mock history, cleaning the repository |
| `JobExplorer` | Read repository state and history | Asserting persisted results, querying executions |
| `JobOperatorTestUtils` (6.x) | Launch jobs/steps in tests | Real job execution testing in Spring Batch 6 |
| `JobLauncherTestUtils` (5.x) | Launch jobs/steps in tests | Real job execution testing in Spring Batch 5 projects |
| `StepScopeTestUtils`, `@SpringBatchTest` | Support `StepScope`/`JobScope` context in tests | Testing beans whose values depend on `JobParameters` or `ExecutionContext` |
| Mockito or stub reader/processor/writer | Isolate processing units | Unit testing business logic of a single component |

For example, if the requirement is "when an invoice input is invalid, the processor returns an error," use a unit test for the processor. If the requirement is "the job processes 100 invoices, writes 98, and skips 2," run the job/step and verify counters along with output data. If the requirement is "the admin page reads three runs of `invoiceImportJob`," `JobRepositoryTestUtils` combined with `JobExplorer` is a natural fit.

## 10. Common Errors and Root Causes

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` for `JobRepositoryTestUtils` | Missing `spring-batch-test` or `@SpringBatchTest`/utility bean not registered | Add the test dependency; load the proper Spring test context |
| Cannot create `JobRepositoryTestUtils` | Test context lacks `JobRepository` or incomplete infrastructure configuration | Check DataSource, transaction manager, repository, and test configuration |
| Missing `BATCH_JOB_INSTANCE`/`BATCH_JOB_EXECUTION` error | Metadata schema not initialized or pointing to wrong database | Initialize schema for the Spring Batch version and verify connection |
| `JobInstanceAlreadyCompleteException` on re-run | Same job name and identifying parameters already completed | Use new parameters for a new run; only reset metadata in an isolated test environment |
| `JobExecutionAlreadyRunningException` | Repository records an execution of the same instance still running | Check old executions and transactions; do not arbitrarily delete while a real job is running |
| `JobExplorer` cannot find newly created execution | Explorer uses a different data source, transaction not yet visible, or non-persistent repository | Cross-check DataSource and commit timing |
| Test passes in isolation but fails across the full suite | Leftover metadata/output or parallel tests sharing the repository | Isolate database, use unique parameters, clean up according to ownership |
| Output remains after calling `removeJobExecutions()` | Utility only cleans batch metadata | Clean business tables/files/queues with separate fixtures |
| `JobExecution` import errors after version upgrade | Spring Batch 6 changed package structure | Update imports to match version and align dependencies |

## 11. Practice Exercise

Suppose you are building an API `GET /batch/history?jobName=invoiceImportJob` that returns the number of runs and recorded step names:

1. Configure a test database with the Spring Batch schema and a `JobExplorer` pointing to that same repository.
2. Use `createJobExecutions("invoiceImportJob", new String[]{"readInvoices", "writeInvoices"}, 3)` to create the fixture.
3. Call the application's history-querying service/API; verify that the job has three executions and each execution has two recorded steps.
4. In `finally` or an appropriate cleanup hook, call `removeJobExecutions(created)`.
5. Add a test that runs an actual job using the launch utility for your version and verifies output to clearly see the difference between **metadata fixtures** and **real job execution**.

## 12. Key Takeaways

`JobRepositoryTestUtils` is a tool for managing **execution history data for tests**. Keeping three boundaries clear ensures proper usage: `createJobExecutions` creates metadata rather than running steps; `removeJobExecutions` deletes metadata rather than business data; and cleanup operations are only safe when you understand which repository/schema is being targeted. Combining this utility with `@SpringBatchTest`, `JobExplorer`, an isolated test database, and version-appropriate job launch utilities helps you write repeatable, explainable integration tests that do not depend on execution order.

### Official References

- [Spring Batch 6 — JobRepositoryTestUtils API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/test/JobRepositoryTestUtils.html)
- [Spring Batch 6 — @SpringBatchTest API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/test/context/SpringBatchTest.html)
- [Spring Batch — Unit Testing](https://docs.spring.io/spring-batch/reference/testing.html)
- [Spring Batch 5.2 — JobRepositoryTestUtils API](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/test/JobRepositoryTestUtils.html)
