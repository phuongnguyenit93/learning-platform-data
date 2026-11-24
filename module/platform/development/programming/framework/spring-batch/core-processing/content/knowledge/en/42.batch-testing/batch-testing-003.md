# Running Job Tests with `JobParameters` in Spring Batch

In Spring Batch, the same `Job` can process different datasets depending on the parameters passed at launch time. Therefore, batch testing does not stop at verifying that a job finishes successfully: tests must pass the right `JobParameters`, verify which parameters the job received, observe the processing results, and understand what happens when re-running with the same parameter set.

This lesson uses **Spring Batch 5.x, Spring Boot 3.x, and JUnit 5**. The focus is on integration testing with `@SpringBatchTest`, `JobLauncherTestUtils`, and `JobParametersBuilder`.

## 1. What Role Does `JobParameters` Play in a Test?

`JobParameters` is a collection of name–value pairs passed to a single job run. For example, a reporting job might receive:

| Parameter Name | Example | Meaning |
| --- | --- | --- |
| `businessDate` | `2026-11-16` | Business date to process |
| `region` | `VN` | Region for report generation |
| `run.id` | `test-001` | Distinguishes independent runs when needed |

A typical test executes the following sequence:

```text
JUnit test
  └── Create JobParameters
        └── JobLauncherTestUtils.launchJob(parameters)
              └── JobLauncher → JobRepository → Job
                    └── Step → Reader / Processor / Writer or Tasklet
              └── JobExecution
                    ├── BatchStatus / ExitStatus
                    ├── Actual JobParameters
                    ├── StepExecutions
                    └── Observable results
```

Three concepts must be distinguished:

- **`Job`**: defines the workflow, for example `reportJob`.
- **`JobInstance`**: a logical job instance identified by **job name and parameters with `identifying=true`**.
- **`JobExecution`**: a single execution attempt of a `JobInstance`. One instance can have multiple executions in a failure-and-restart scenario, whereas a completed instance normally cannot be re-run.

Consequently, changing `JobParameters` may create a new `JobInstance` or still point to the old instance, depending on **which parameters are identifying**. This is the most common source of bugs when writing tests.

## 2. Preparing the Test Environment

For a Spring Boot project already using `spring-boot-starter-batch`, add the testing dependencies (for example in Gradle):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

Spring Boot manages compatible dependency versions when using the corresponding BOM/plugin. H2 here serves as a test database for storing Spring Batch metadata; applications using another database can substitute a dedicated test database or Testcontainers.

In tests, note two configuration properties:

```properties
spring.batch.job.enabled=false
spring.batch.jdbc.initialize-schema=always
```

- `spring.batch.job.enabled=false`: prevents Spring Boot from automatically running the job as soon as the test context initializes; the test will explicitly call `launchJob(...)`.
- `spring.batch.jdbc.initialize-schema=always`: creates the `BATCH_*` metadata tables in the test database. Use only when appropriate for your test environment's schema management; if the schema is already prepared by migrations or Testcontainers, you do not need to enable it.

`@SpringBatchTest` provides utilities such as `JobLauncherTestUtils` and `JobRepositoryTestUtils`, while registering test support for beans using job/step scope. `@SpringBootTest` loads the application context to run realistic integration tests.

## 3. A Sample Job Accepting Runtime Parameters

Suppose we have `reportJob` accepting `businessDate` and `region`. To focus on parameter passing, the sample step validates the inputs and writes the processed values into the job's `ExecutionContext`. In a real application, the step might read files, query data, invoke a processor, or write to a database.

```java
package com.example.batch;

import java.time.LocalDate;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class ReportJobConfig {

    @Bean
    public Job reportJob(JobRepository jobRepository, Step reportStep) {
        return new JobBuilder("reportJob", jobRepository)
                .start(reportStep)
                .build();
    }

    @Bean
    public Step reportStep(JobRepository jobRepository,
                           PlatformTransactionManager transactionManager,
                           Tasklet reportTasklet) {
        return new StepBuilder("reportStep", jobRepository)
                .tasklet(reportTasklet, transactionManager)
                .build();
    }

    @Bean
    @StepScope
    public Tasklet reportTasklet(
            @Value("#{jobParameters['businessDate']}") String businessDate,
            @Value("#{jobParameters['region']}") String region) {

        return (contribution, chunkContext) -> {
            if (businessDate == null || businessDate.isBlank()) {
                throw new IllegalArgumentException("businessDate is required");
            }
            if (region == null || region.isBlank()) {
                throw new IllegalArgumentException("region is required");
            }

            // Validate yyyy-MM-dd format; an invalid date causes the step to become FAILED.
            String normalizedDate = LocalDate.parse(businessDate).toString();

            JobExecution execution = contribution.getStepExecution()
                    .getJobExecution();
            execution.getExecutionContext()
                    .putString("processedDate", normalizedDate);
            execution.getExecutionContext()
                    .putString("processedRegion", region);

            return RepeatStatus.FINISHED;
        };
    }
}
```

The key point is `@StepScope`. The `reportTasklet` bean must be created per **step execution** so that the `#{jobParameters['...']}` expression retrieves the values of the currently running job. If you omit the scope and try to read job parameters when the application context initializes, late binding may fail or yield incorrect values. The names in the expressions must exactly match the parameter names passed by the test.

In the example above, writing to `ExecutionContext` gives the lesson an easily observable outcome. `ExecutionContext` is primarily meant for batch processing state and restart tracking; for production jobs, tests should prioritize verifying **real business outputs** such as database records, exported files, or written item counts.

## 4. Writing Integration Tests with Specific Parameters

Assume the application has a `@SpringBootApplication` class that scans `ReportJobConfig` and has a test datasource. The test below explicitly selects the job, builds the parameter set, runs the job, and checks both status and the values passed into the step.

```java
package com.example.batch;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;

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

@SpringBatchTest
@SpringBootTest(properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always"
})
class ReportJobIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JobRepositoryTestUtils jobRepositoryTestUtils;

    @Autowired
    @Qualifier("reportJob")
    private Job reportJob;

    @BeforeEach
    void setUp() {
        // Explicitly specify the job to test, especially when the context has multiple Jobs.
        jobLauncherTestUtils.setJob(reportJob);

        // Only delete metadata on a dedicated test database.
        jobRepositoryTestUtils.removeJobExecutions();
    }

    @Test
    void runsJobWithBusinessParameters() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", "2026-11-16")
                .addString("region", "VN")
                .addString("run.id", UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(execution.getExitStatus().getExitCode())
                .isEqualTo("COMPLETED");
        assertThat(execution.getJobParameters().getString("businessDate"))
                .isEqualTo("2026-11-16");
        assertThat(execution.getJobParameters().getString("region"))
                .isEqualTo("VN");

        // Verify that the step actually read and processed the parameters.
        assertThat(execution.getExecutionContext().getString("processedDate"))
                .isEqualTo("2026-11-16");
        assertThat(execution.getExecutionContext().getString("processedRegion"))
                .isEqualTo("VN");
    }

    @Test
    void failsWhenRegionIsMissing() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", "2026-11-16")
                .addString("run.id", UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertThat(execution.getStatus()).isEqualTo(BatchStatus.FAILED);
        assertThat(execution.getAllFailureExceptions())
                .anySatisfy(error -> assertThat(error)
                        .isInstanceOf(IllegalArgumentException.class));
    }
}
```

### Why Do the Lines in the Test Matter?

1. `new JobParametersBuilder()` creates a new input dataset; `.addString(...)` appends a `String` parameter and `.toJobParameters()` builds the `JobParameters` object.
2. `jobLauncherTestUtils.setJob(reportJob)` prevents selecting the wrong job when the context contains multiple `Job` beans.
3. `launchJob(parameters)` executes the entire job with the exact parameters passed in and returns a `JobExecution` for inspection.
4. Checking `BatchStatus.COMPLETED` confirms the job finished successfully; checking `ExecutionContext` shows that the parameters affected the processing step, going beyond merely verifying the input object.
5. The missing-`region` test illustrates **an error occurring inside the step**, so a `JobExecution` exists with status `FAILED`. If a `JobParametersValidator` is used at job entry, invalid parameters can cause `launchJob(...)` to throw `JobParametersInvalidException` before the step runs; the test should catch the appropriate exception rather than always expecting `FAILED`.

`JobLauncherTestUtils` normally runs synchronously with the default `JobLauncher` configuration. If the system configures an asynchronous launcher, receiving a `JobExecution` does not necessarily mean the job has finished; in that case, a bounded wait-for-completion mechanism is required before asserting results.

## 5. Distinguishing Identifying and Non-Identifying Parameters

In `JobParametersBuilder`, the final overload lets you specify whether a parameter participates in identifying a `JobInstance`:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16", true)
        .addString("region", "VN", true)
        .addString("traceId", "trace-A", false)
        .toJobParameters();
```

Here, `businessDate` and `region` have `identifying=true`. `traceId` has `identifying=false`, so changing `traceId` does **not** create a new `JobInstance`. When the `identifying` argument is omitted, methods like `addString`, `addLong`, etc. default to `true`.

Suppose the job name is always `reportJob`:

| Run | `businessDate` | `region` | `traceId` (`identifying=false`) | Consequence |
| --- | --- | --- | --- | --- |
| A | `2026-11-16` | `VN` | `trace-A` | First instance |
| B | `2026-11-16` | `VN` | `trace-B` | **Still A's instance** |
| C | `2026-11-17` | `VN` | `trace-C` | New instance |
| D | `2026-11-16` | `SG` | `trace-D` | New instance |

If A is already `COMPLETED`, attempting B typically leads to `JobInstanceAlreadyCompleteException`, because that instance has already completed. Changing a non-identifying parameter does not let you re-run an already completed job.

In tests that need to run a job independently multiple times, an identifying `run.id` with a unique value can be used:

```java
private JobParameters paramsFor(String date, String region) {
    return new JobParametersBuilder()
            .addString("businessDate", date)
            .addString("region", region)
            .addString("run.id", UUID.randomUUID().toString())
            .toJobParameters();
}
```

However, **do not change `run.id` when testing a restart of the same instance**: changing an identifying parameter creates a new instance and causes the test to stop checking restart behavior. When testing restart, keep the identifying parameters identical and trigger the next run on the `FAILED` or `STOPPED` instance according to the job's restart policy.

## 6. Essential Test Scenarios

Depending on business logic, cover the following categories of cases:

| Scenario | How Parameters Are Passed | What to Verify |
| --- | --- | --- |
| Valid data | Both `businessDate` and `region` provided | Job `COMPLETED` and produces expected output |
| Missing required value | Omit `region` | Validator rejects or step becomes `FAILED` as designed |
| Invalid format | `businessDate=not-a-date` | Parse/validation error handled properly |
| Different input data | Run with different `region` values | Output changes accordingly without stale values leaking between runs |
| Re-run with old parameters | Keep all identifying parameters identical | Restart/instance constraint works according to prior state |
| Non-identifying parameter | Change only `traceId` | Does not create a new instance |
| Multiple jobs in context | Call `setJob(...)` explicitly | Test runs the intended job |

### Testing the Same Parameter Set After Job Completion

In a **separate test**, omit metadata deletion between two launches and reuse the exact same `JobParameters` object:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;

JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16")
        .addString("region", "VN")
        .addString("run.id", UUID.randomUUID().toString())
        .toJobParameters();

JobExecution first = jobLauncherTestUtils.launchJob(parameters);
assertThat(first.getStatus()).isEqualTo(BatchStatus.COMPLETED);

assertThrows(JobInstanceAlreadyCompleteException.class,
        () -> jobLauncherTestUtils.launchJob(parameters));
```

The snippet above assumes the job completes successfully and the repository still holds metadata from the first run. This test verifies the instance identification rule rather than a second data-processing behavior.

### Verifying Business Outputs Rather Than Just Status

For a job writing to a database or exporting a file, the most important assertions usually target results outside `JobExecution`. For example, if the job writes report records to a repository:

```java
JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
assertThat(reportRepository.findByBusinessDateAndRegion(
        LocalDate.parse("2026-11-16"), "VN"))
        .hasSize(3);
```

This is an **illustrative assertion pattern**: `reportRepository` and the query method are business components needed in a real project, not built-in Spring Batch APIs. Similarly, when testing a chunk-oriented step, you can inspect `StepExecution` metrics (`getReadCount()`, `getWriteCount()`, `getSkipCount()`) where appropriate.

## 7. Using `launchStep(...)` When Only Testing a Single Step

`JobLauncherTestUtils` can also run a specific step of a job:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16")
        .addString("region", "VN")
        .addString("run.id", UUID.randomUUID().toString())
        .toJobParameters();

JobExecution execution =
        jobLauncherTestUtils.launchStep("reportStep", parameters);

assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
```

`launchStep` is suitable for isolating a step, but it runs the step through a synthetic test job created by the framework. Consequently, its result does not fully represent step ordering, transition conditions, job-level listeners, or the restart flow of the entire `reportJob`. If the test needs to evaluate those relationships, use `launchJob(parameters)`.

## 8. Managing Test Data and Metadata to Avoid Cross-Test Interference

Spring Batch stores job history in `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_JOB_EXECUTION_PARAMS`, `BATCH_STEP_EXECUTION`, and related tables. This makes tests stateful even when business logic only performs simple reads/writes.

There are two common strategies:

1. **Isolate the test repository:** each suite/test has its own database, setting up independent schema and test data; you can call `jobRepositoryTestUtils.removeJobExecutions()` in `@BeforeEach` when certain the database is dedicated solely to tests. This method deletes batch execution history, so never invoke it against a repository shared with production or other parallel tests.
2. **Generate unique identifying parameters:** add `run.id` when wanting to create new instances. This avoids identity collisions but does **not automatically clean up** batch history, business data, or exported files; an appropriate cleanup strategy is still needed.

If tests run in parallel against the same database, one test deleting another test's metadata will cause hard-to-reproduce failures. In that case, use separate databases/schemas or control parallelism instead of indiscriminately wiping the entire repository.

`@Transactional` on a JUnit method also does not automatically roll back all batch work because jobs/steps may use independent transactions. Explicitly determine where data cleanup is required and use an isolated test database.

## 9. Common Errors When Testing with `JobParameters`

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `JobInstanceAlreadyCompleteException` | Running an already completed job with the same identifying parameters | Use a new instance for independent tests; keep parameters unchanged if intentionally testing re-run restrictions |
| `JobExecutionAlreadyRunningException` | An execution of the instance is still running | Check asynchronous launcher, repository state, and completion wait mechanism |
| `JobParametersInvalidException` | Job's validator rejects parameters | Check names, types, required conditions; assert exception at launch boundary |
| Step cannot read parameter | Wrong key name, missing `@StepScope`, incompatible scope config | Match `addString("name", ...)` with `#{jobParameters['name']}` |
| Job runs automatically on context startup | Spring Boot auto-triggers jobs | Set `spring.batch.job.enabled=false` in tests |
| `JobRepository` reports missing `BATCH_*` tables | Metadata schema not created | Create dedicated test schema or enable initialize-schema on the test datasource |
| Asserts `COMPLETED` but data is wrong | Test only checks technical status | Assert actual records/files/item counts and real business values |
| Test only passes when run alone | Leftover metadata or data from another test | Isolate datasource, clean data within proper scope, and control parallel execution |

**Version note:** The examples above use Spring Batch 5 APIs (`JobBuilder` taking `JobRepository`, `StepBuilder` taking `JobRepository`, tasklet step taking `PlatformTransactionManager`). If the project still uses Spring Batch 4, builder configuration and some parameter details may differ; use the API matching your project's version.

## 10. Hands-On Practice Exercise

Use `reportJob` above to perform the following steps in order:

1. Run with `businessDate=2026-11-16`, `region=VN`, and a new `run.id`; verify the job completes and `processedRegion=VN`.
2. Keep the date but change `region=SG` and use a new `run.id`; verify the corresponding step result is `SG`.
3. Omit `businessDate`, then pass `businessDate=16/11/2026`; for each case, verify the error occurs at the designed point.
4. Run a completing job twice with **the same** identifying parameters in the same test without clearing the repository between runs; observe the exception on the second run.
5. Add a `traceId` parameter with `identifying=false`; try changing only `traceId` and explain why doing so does not create a new instance.

When implementing a real job, the principle to follow is: **tests pass purposeful parameters, confirm `JobInstance` is identified accurately, verify execution status, and check the actual business outcome produced by those parameters**. This testing approach catches defects that a test merely calling `launchJob()` and asserting `COMPLETED` often misses.
