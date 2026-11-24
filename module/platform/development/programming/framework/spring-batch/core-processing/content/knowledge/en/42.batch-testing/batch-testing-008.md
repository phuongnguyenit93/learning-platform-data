# Asserting `JobExecution` Status in Spring Batch Testing

In Spring Batch, running a `Job` is not enough to conclude that the process succeeded. A test must obtain the `JobExecution` of **that specific run**, compare its actual status against the expected result, and, when needed, inspect individual `Step` statuses and output data. This is the core of **asserting `JobExecution` status** under the *Testing batch* topic.

After this lesson, you will be able to test a successful job, an intentionally failing job, distinguish `BatchStatus` from `ExitStatus`, and avoid assertions that give misleading results across multiple test runs.

## 1. What Does `JobExecution` Reflect?

A `Job` is the job definition, such as `importCustomersJob`. A `JobInstance` is a logical processing run identified by the job name and **identifying job parameters**. A `JobExecution` is **a single execution attempt** of that `JobInstance`; if a job fails and is restarted, one `JobInstance` can have multiple `JobExecution` records.

`JobExecution` carries useful information for assertions:

| Property | API | Meaning When Testing |
| --- | --- | --- |
| Execution status | `getStatus()` | Returns the `BatchStatus` enum, such as `COMPLETED` or `FAILED`. |
| Exit code | `getExitStatus().getExitCode()` | Returns a string, by default typically `COMPLETED`/`FAILED`; can be customized. |
| Exit description | `getExitStatus().getExitDescription()` | Additional details for diagnosing the outcome. |
| Start/end timestamps | `getStartTime()`, `getEndTime()` | Helps verify that a run has finished. |
| Job and step errors | `getAllFailureExceptions()` | Collection of exceptions causing failure, including exceptions from steps. |
| Step executions | `getStepExecutions()` | Inspects which steps ran, their outcomes, and processed record counts. |

Example of a successful run:

```text
Job: importCustomersJob
  JobInstance: importCustomersJob + {inputFile=customers.csv}
    JobExecution #42
      status: COMPLETED
      exitCode: COMPLETED
      StepExecution(validateFileStep): COMPLETED
      StepExecution(importRowsStep): COMPLETED
```

**You must inspect the status of the exact `JobExecution` that just ran.** A job that succeeded in the past does not prove the current run succeeded.

## 2. How Do `BatchStatus` and `ExitStatus` Differ?

`BatchStatus` is the operational status managed by Spring Batch. Common values:

| `BatchStatus` | Interpretation | Usage in Assertions |
| --- | --- | --- |
| `STARTING`, `STARTED` | Job is starting or executing. | Cannot yet conclude the job has finished. |
| `STOPPING` | Processing a stop request. | Not yet the final stopped state. |
| `COMPLETED` | Job completed successfully according to workflow conditions. | `isEqualTo(BatchStatus.COMPLETED)` |
| `FAILED` | Job ended due to failure. | `isEqualTo(BatchStatus.FAILED)` |
| `STOPPED` | Job has stopped. | `isEqualTo(BatchStatus.STOPPED)` |
| `ABANDONED` | Execution abandoned, usually cannot be restarted through normal mechanisms. | Expect only in explicitly designed scenarios. |
| `UNKNOWN` | Status cannot be determined reliably. | Usually requires investigating metadata and infrastructure. |

`ExitStatus` is the exit outcome containing an **exit code** (`String`) and description. It supports flow branching and communicating results externally. For example:

```java
assertThat(execution.getStatus())
        .isEqualTo(BatchStatus.COMPLETED);

assertThat(execution.getExitStatus().getExitCode())
        .isEqualTo(ExitStatus.COMPLETED.getExitCode());
```

These two assertions check two different things:

- `getStatus()` verifies the job's execution status.
- `getExitStatus().getExitCode()` verifies the **exit code** published by the job.

A job can have `BatchStatus.COMPLETED` with a custom exit code like `COMPLETED_WITH_WARNINGS` set by a listener or flow configuration. In that case, asserting `COMPLETED` for `BatchStatus` still holds, while asserting the exit code must follow the actual contract. When comparing error codes, `getExitCode()` is usually sufficient: comparing entire `ExitStatus` objects can be sensitive to differing `exitDescription` text.

## 3. Preparing the Test Environment

Use **JUnit Jupiter**, **AssertJ**, and the `spring-batch-test` library. In a Spring Boot application, the project typically needs the corresponding test dependencies:

```groovy
// Example in build.gradle; versions are managed by Spring Boot/BOM.
testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'org.springframework.batch:spring-batch-test'
```

Integration tests require an `ApplicationContext` containing the job, `JobRepository`, and Spring Batch infrastructure. Use a dedicated test database (such as H2 or a specialized test database) with the batch schema matching your version. `@SpringBatchTest` provides utilities for launching and inspecting batch jobs. `@SpringBootTest` loads the application context; if not using Spring Boot, use `@SpringJUnitConfig` with an appropriate Spring configuration.

The primary examples below use **Spring Batch 6.x**; Section 7 presents the variant for **Spring Batch 5.x**, as Java packages and test utilities differ between the two version lines.

## 4. Asserting a Successful Job Run with Spring Batch 6.x

Suppose the application has a `Job` bean named `importCustomersJob`. The test below launches the job with a unique identifying parameter per run and checks the outcome:

```java
import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.job.Job;
import org.springframework.batch.core.job.JobExecution;
import org.springframework.batch.core.job.parameters.JobParameters;
import org.springframework.batch.core.job.parameters.JobParametersBuilder;
import org.springframework.batch.test.JobOperatorTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class ImportCustomersJobStatusTest {

    @Autowired
    private JobOperatorTestUtils jobOperatorTestUtils;

    @Autowired
    @Qualifier("importCustomersJob")
    private Job importCustomersJob;

    @BeforeEach
    void selectJob() {
        // Explicitly select the job if the application context has multiple Job beans.
        jobOperatorTestUtils.setJob(importCustomersJob);
    }

    @Test
    void shouldCompleteSuccessfully() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("testRunId", UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution execution = jobOperatorTestUtils.startJob(parameters);

        assertThat(execution.getStatus())
                .as("Execution status of importCustomersJob")
                .isEqualTo(BatchStatus.COMPLETED);

        assertThat(execution.getExitStatus().getExitCode())
                .as("Exit code of importCustomersJob")
                .isEqualTo(ExitStatus.COMPLETED.getExitCode());

        assertThat(execution.getEndTime())
                .as("Job completion timestamp")
                .isNotNull();
    }
}
```

Explanation of the sequence:

1. `setJob(importCustomersJob)` ensures the utility runs the exact `Job` bean under test.
2. `testRunId` is an **identifying** parameter by default. A new value creates a separate `JobInstance`, avoiding collisions with prior `COMPLETED` runs in `JobRepository`.
3. `startJob(parameters)` returns a `JobExecution` for the test to inspect.
4. `getStatus()` is the primary assertion of the lesson; `getExitCode()` and `getEndTime()` are supplementary conditions depending on business requirements.

The property `spring.batch.job.enabled=false` prevents automatic job launching when Spring Boot initializes the test context. When running the test suite, ensure fixtures (input data, files, database) are set up properly so `importCustomersJob` can genuinely succeed; `testRunId` only distinguishes runs and does not replace business parameters required by the job.

> **Note:** If `startJob(...)` returns before the job finishes because the launcher/operator is configured asynchronously, `getStatus()` may still be `STARTING` or `STARTED`. For typical integration tests, prefer synchronous execution configuration. If asynchronous execution is required, wait for the terminal state via bounded polling, re-reading `JobExecution` from the repository/explorer; never use a fixed `Thread.sleep(...)` and guess the job has finished.

## 5. Asserting an Intentionally Failing Job

A failure-path test needs to create **reproducible failing inputs or a failing step**, then verify that `JobExecution` ends in `FAILED`. For example, consider a bean `failingProbeJob` with a step throwing `IllegalStateException` with message `invalid-record`. The test below verifies status, exit code, and cause:

```java
@Test
void shouldFailForInvalidRecord() throws Exception {
    jobOperatorTestUtils.setJob(failingProbeJob);

    JobParameters parameters = new JobParametersBuilder()
            .addString("testRunId", UUID.randomUUID().toString())
            .toJobParameters();

    JobExecution execution = jobOperatorTestUtils.startJob(parameters);

    assertThat(execution.getStatus())
            .isEqualTo(BatchStatus.FAILED);

    assertThat(execution.getExitStatus().getExitCode())
            .isEqualTo(ExitStatus.FAILED.getExitCode());

    assertThat(execution.getAllFailureExceptions())
            .anySatisfy(error -> assertThat(error)
                    .isInstanceOf(IllegalStateException.class)
                    .hasMessageContaining("invalid-record"));
}
```

This snippet belongs in the test class configured with `@SpringBatchTest`/`@SpringBootTest` from Section 4, with an added field `@Autowired @Qualifier("failingProbeJob") Job failingProbeJob`. A test fixture can define the explicitly failing step:

```java
@Bean("failingProbeStep")
Step failingProbeStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {
    return new StepBuilder("failingProbeStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                throw new IllegalStateException("invalid-record");
            }, transactionManager)
            .build();
}

@Bean("failingProbeJob")
Job failingProbeJob(
        JobRepository jobRepository,
        @Qualifier("failingProbeStep") Step failingProbeStep) {
    return new JobBuilder("failingProbeJob", jobRepository)
            .start(failingProbeStep)
            .build();
}
```

These `@Bean` definitions reside in a `@TestConfiguration` class loaded into the test context, not necessarily in production configuration. With Spring Batch 6, `Job` and `Step` are imported from `org.springframework.batch.core.job.Job` and `org.springframework.batch.core.step.Step`; `JobBuilder` and `StepBuilder` reside in `...core.job.builder` and `...core.step.builder` respectively. `JobRepository` resides in `...core.repository`.

**Do not use `assertThatThrownBy(() -> startJob(...))` as a substitute for asserting `FAILED`.** When an error occurs inside a step and is handled by the framework, the launch method can still return a `JobExecution` carrying `FAILED` status. Exceptions thrown right at launch time (such as invalid parameters, an already completed job instance, or a missing job) form a separate category of test scenarios.

If the application deliberately catches and *skips* bad records, the job may still end as `COMPLETED`. In that case, assert `COMPLETED` and the skip count rather than assuming every exception during processing must turn the job `FAILED`.

## 6. Also Asserting Each `StepExecution` and Business Outcome

A `COMPLETED` job confirms the flow's termination condition, but does not tell you whether the job processed the right data. For a data-import job, inspect the specific step and item counts:

```java
JobExecution execution = jobOperatorTestUtils.startJob(parameters);

assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);

var importStep = execution.getStepExecutions().stream()
        .filter(step -> "importRowsStep".equals(step.getStepName()))
        .findFirst()
        .orElseThrow(() -> new AssertionError(
                "StepExecution for importRowsStep not found"));

assertThat(importStep.getStatus()).isEqualTo(BatchStatus.COMPLETED);
assertThat(importStep.getReadCount()).isEqualTo(10);
assertThat(importStep.getWriteCount()).isEqualTo(10);
assertThat(importStep.getSkipCount()).isZero();
```

The number `10` is merely an example corresponding to a fixture with 10 valid records. In a job with **conditional branching**, a step may be intentionally bypassed; do not require every defined step to appear. In chunk processing with **filtering**, `readCount` and `writeCount` do not necessarily match either.

Even better, assert the data written to the database or output file:

```java
assertThat(customerRepository.count()).isEqualTo(10);
```

This assertion confirms the job's actual effect. Prepare data and isolate the data store before each test so counts are not skewed by other runs.

## 7. If Your Project Uses Spring Batch 5.x

In **Spring Batch 5.x**, the standard utility is `JobLauncherTestUtils.launchJob(...)`, whereas Spring Batch 6 introduces `JobOperatorTestUtils.startJob(...)`; `JobLauncherTestUtils` is marked deprecated in the 6.x API.

Key imports also changed:

| Component | Spring Batch 5.x | Spring Batch 6.x |
| --- | --- | --- |
| `Job`, `JobExecution` | `org.springframework.batch.core.Job` / `JobExecution` | `org.springframework.batch.core.job.Job` / `JobExecution` |
| `JobParameters`, `JobParametersBuilder` | `org.springframework.batch.core` | `org.springframework.batch.core.job.parameters` |
| `Step`, `StepExecution` | `org.springframework.batch.core` | `org.springframework.batch.core.step` |
| Test runner utility | `JobLauncherTestUtils` | `JobOperatorTestUtils` |
| Launching a job | `launchJob(parameters)` | `startJob(parameters)` |

Core example for **5.x** (inside a test class with `@SpringBatchTest` and a configured Spring test context):

```java
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;

// @Autowired JobLauncherTestUtils jobLauncherTestUtils;
// jobLauncherTestUtils.setJob(importCustomersJob);

JobParameters parameters = new JobParametersBuilder()
        .addString("testRunId", UUID.randomUUID().toString())
        .toJobParameters();

JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
assertThat(execution.getExitStatus().getExitCode())
        .isEqualTo(ExitStatus.COMPLETED.getExitCode());
```

Assertions on `BatchStatus` and `ExitStatus` retain the same meaning across both versions. When migrating code from 5.x to 6.x, update both imports and the test runner utility to match the dependency version.

## 8. Choosing Appropriate Assertions by Scenario

| Scenario | Primary Assertion | Useful Additional Assertions |
| --- | --- | --- |
| Job processes all valid data | `BatchStatus.COMPLETED` | Exit code `COMPLETED`; read/write counts; output data. |
| Step throws unhandled error | `BatchStatus.FAILED` | Exit code `FAILED`; `getAllFailureExceptions()`; failing step. |
| Job stopped on request | `BatchStatus.STOPPED` | Last step; persisted state enabling restart if designed to allow it. |
| Processing with valid skips | Usually `BatchStatus.COMPLETED` | Accurate `skipCount`; valid data still written; exit code per contract. |
| Completed with business warnings | `BatchStatus.COMPLETED` | Custom exit code, e.g., `COMPLETED_WITH_WARNINGS`. |
| Restart after a failure | First run `FAILED`, restart run `COMPLETED` | Both `JobExecution` records belong to the same `JobInstance`; completed steps rerun or skipped per config. |

To test **restart**, do not add a new `testRunId` when you need to reuse the same `JobInstance`. Use the same identifying parameters between the failed run and the restart run, then fetch each `JobExecution` separately to assert. A new `JobInstance` and a new `JobExecution` are two different concepts.

## 9. Common Errors When Asserting Status

**1. Test reports `JobInstanceAlreadyCompleteException` on the second run.** You are reusing the job name and identifying parameters of an already completed instance. For independent test runs, provide unique identifying parameters or intentionally manage/clean test metadata. For restart tests, intentionally reuse the same parameters.

**2. Test expects `FAILED` but receives `COMPLETED`.** Check whether the job configures skip, retry, custom listeners, or transitions that deliberately turn a step failure into a completed flow result. Compare the step's status against the job's final status.

**3. Test compares `getStatus()` against the string `"COMPLETED"`.** `getStatus()` returns `BatchStatus` (an enum), so compare against `BatchStatus.COMPLETED`. The string `"COMPLETED"` is for `getExitStatus().getExitCode()`.

**4. Tests are flaky when running in parallel.** Multiple tests sharing database tables, files, or identical job parameters can collide. Each test should have isolated fixtures; if launched asynchronously, synchronize on results persisted to the repository.

**5. Checking status while ignoring data.** A job can complete even if it read zero records or skipped all data per configuration. Combine status with `readCount`, `writeCount`, `skipCount`, and target data to verify actual requirements.

**6. Catching an exception on the job launch call and concluding the job failed.** An exception during *launch* differs from a `FAILED` outcome after *execution*. If the goal is testing `JobExecution` status, obtain `JobExecution` and assert status on that object.

## 10. Practice Exercise

Suppose `importOrdersJob` reads 12 orders: 10 valid, 2 invalid. Business requirements allow skipping up to 2 invalid orders and still completing.

1. Create a fixture with exactly 12 inputs and an empty destination store.
2. Launch `importOrdersJob` with a new parameter set.
3. Assert `JobExecution.getStatus() == BatchStatus.COMPLETED`.
4. Find the `StepExecution` of the order-import step; assert `readCount == 12`, `writeCount == 10`, and `skipCount == 2` (matching your fixture's reader/processor/writer configuration).
5. Verify the destination store has exactly 10 valid orders.
6. Also test a case where errors exceed the skip limit and confirm `FAILED` status along with the relevant cause.

Upon completion, you will distinguish **"job finishes according to flow"** from **"job produces accurate data results"**—two testing conditions that usually belong together.

## References

- [Spring Batch – Unit Testing](https://docs.spring.io/spring-batch/reference/testing.html): `@SpringBatchTest` and Spring Batch 6 testing utilities.
- [Spring Batch – Controlling Step Flow](https://docs.spring.io/spring-batch/reference/step/controlling-flow.html): distinguishing `BatchStatus` and `ExitStatus`.
- [Spring Batch 6 – `JobExecution` API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/job/JobExecution.html).
- [Spring Batch 6 – `JobOperatorTestUtils` API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/test/JobOperatorTestUtils.html).
- [Spring Batch 5.2 – `JobLauncherTestUtils` API](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/test/JobLauncherTestUtils.html).

