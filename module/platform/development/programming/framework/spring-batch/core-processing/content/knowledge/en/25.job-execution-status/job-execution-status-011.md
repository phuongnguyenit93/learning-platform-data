# Testing Final Status

In Spring Batch, testing final status verifies that a Job or Step terminates as designed after processing data, encountering errors, taking a flow branch, or stopping intentionally. A Batch test should not merely assert that the launch method throws no exception; it must inspect the metadata Spring Batch writes to `JobExecution` and `StepExecution`.

Two pieces of information to verify together are `BatchStatus` and `ExitStatus`:

- `BatchStatus` describes the lifecycle state of a JobExecution or StepExecution, such as `COMPLETED`, `FAILED`, or `STOPPED`.
- `ExitStatus` describes the outcome code and supplemental details, such as `COMPLETED`, `FAILED`, `STOPPED`, or a custom business code like `NO_DATA`.

A Step can have `BatchStatus.COMPLETED` while its `ExitStatus` is `NO_DATA`; the Job uses that code to choose a flow branch. Consequently, checking only one of these two fields can miss flow routing bugs or incorrect business outcomes.

## 1. How Do BatchStatus and ExitStatus Differ?

`BatchStatus` is an enum representing the execution lifecycle. Common statuses:

| BatchStatus | Meaning |
|---|---|
| `STARTING` | Execution is initializing. |
| `STARTED` | Execution is running. |
| `STOPPING` | Stop request received and waiting to stop. |
| `STOPPED` | Execution stopped and can be restarted if eligible. |
| `FAILED` | Execution ended due to an error. |
| `COMPLETED` | Execution completed successfully along the flow. |
| `ABANDONED` | Execution marked abandoned, not continued via normal restart. |
| `UNKNOWN` | Reliable execution status cannot be determined. |

`ExitStatus` is a value object containing an exit code and exit description. The exit code is commonly used to control Job flow transitions. Standard values corresponding to common states:

```java
ExitStatus.COMPLETED
ExitStatus.FAILED
ExitStatus.STOPPED
```

Applications can also create their own exit codes:

```java
new ExitStatus("NO_DATA")
new ExitStatus("VALIDATION_WARNING")
new ExitStatus("ALREADY_PROCESSED")
```

For example, a validation Step succeeds yet finds no data. The Step can have `BatchStatus.COMPLETED` and `ExitStatus.NO_DATA`. The Job flow can use `on("NO_DATA")` to end successfully or route to a Step generating an empty report.

## 2. Should Status Be Checked at the Job or Step Level?

A Job can contain multiple Steps. Each Step has its own `StepExecution`, while the entire Job run has a `JobExecution`.

Tests should verify both levels when Step outcomes affect the Job result:

- Did the Job finish `COMPLETED`, `FAILED`, or `STOPPED` as expected?
- Does the critical Step have the right `BatchStatus`?
- Is the Step's exit code right for selecting the flow branch?
- Which Steps ran and which Steps were bypassed?
- Were any failure exceptions recorded?
- Do skip, read, write, commit, and rollback counts reflect expected results?

For example, a Job may end `COMPLETED` even though one Step returned exit code `NO_DATA` and an optional Step was bypassed. Checking only Job status fails to verify that the right flow branch was taken.

## 3. Using @SpringBatchTest and JobLauncherTestUtils

Spring Batch provides testing utilities in the `spring-batch-test` module. The `@SpringBatchTest` annotation registers utilities and listeners supporting Job/Step testing, including:

- `JobLauncherTestUtils`: launches a Job or a single Step for testing.
- `JobRepositoryTestUtils`: helps clean up execution metadata in test environments.
- `StepScopeTestExecutionListener` and `JobScopeTestExecutionListener`: support testing Batch-scoped beans.

Example using Spring Boot and JUnit 5:

```java
@SpringBootTest
@SpringBatchTest
class ImportJobStatusTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    @Qualifier("importJob")
    private Job importJob;

    @BeforeEach
    void configureJob() {
        jobLauncherTestUtils.setJob(importJob);
    }

    @Test
    void jobCompletesSuccessfully() throws Exception {
        JobExecution execution = jobLauncherTestUtils.launchJob(
                testJobParameters());

        assertThat(execution.getStatus())
                .isEqualTo(BatchStatus.COMPLETED);
        assertThat(execution.getExitStatus().getExitCode())
                .isEqualTo(ExitStatus.COMPLETED.getExitCode());
    }

    private JobParameters testJobParameters() {
        return new JobParametersBuilder()
                .addString("businessDate", "2026-11-15")
                .addString("testRunId", UUID.randomUUID().toString())
                .toJobParameters();
    }
}
```

Key imports come from `org.springframework.batch.test`, `org.springframework.batch.core`, `org.springframework.batch.core.launch`, `org.springframework.batch.core.repository`, along with JUnit and AssertJ. Tests require `spring-batch-test` in test dependencies and a Batch configuration providing `JobRepository`, `JobLauncher`, and the Job under test.

If the application context defines multiple Job beans, specify the target Job with `setJob(job)` or configure an appropriate test context. Do not let the utility pick an ambiguous Job implicitly.

### Why does each test need distinct JobParameters?

Spring Batch identifies a `JobInstance` by Job name and identifying JobParameters. If one test runs a Job successfully and another test launches the same Job with the same identifying parameters, the second launch can be rejected because the JobInstance is already `COMPLETED`.

A simple approach is adding a test-specific identifying parameter, such as `testRunId` using a UUID. Conversely, if the test verifies restarting the same JobInstance, you must keep the exact same identifying parameters between the initial run and the restart run.

Avoid blindly adding a random parameter to every test without understanding the goal. Independent status tests need a fresh JobInstance; restart tests need the same JobInstance.

## 4. Testing a Successfully Completed Job

For a successful Job, verify `BatchStatus.COMPLETED` and the expected exit code. Without a custom ExitStatus, the outcome code is normally `COMPLETED`.

```java
@Test
void importJobHasCompletedStatus() throws Exception {
    jobLauncherTestUtils.setJob(importJob);

    JobExecution execution = jobLauncherTestUtils.launchJob(
            testJobParameters());

    assertThat(execution.getStatus())
            .isEqualTo(BatchStatus.COMPLETED);
    assertThat(execution.getExitStatus().getExitCode())
            .isEqualTo("COMPLETED");
    assertThat(execution.getEndTime()).isNotNull();
}
```

`endTime` helps confirm the execution has terminated. With a synchronous JobLauncher, `launchJob` typically returns after the Job finishes. If the application configures an asynchronous JobLauncher, never assume the execution is terminal when launch returns; wait for completion and reload the execution from `JobExplorer`.

## 5. Testing StepExecution

`JobExecution` exposes the `StepExecution` instances created during that run. You can find a Step by name and assert its status:

```java
private StepExecution findStepExecution(
        JobExecution execution,
        String stepName) {

    return execution.getStepExecutions().stream()
            .filter(step -> step.getStepName().equals(stepName))
            .findFirst()
            .orElseThrow(() -> new AssertionError(
                    "StepExecution not found: " + stepName));
}

@Test
void loadStepCompletes() throws Exception {
    jobLauncherTestUtils.setJob(importJob);

    JobExecution execution = jobLauncherTestUtils.launchJob(
            testJobParameters());

    StepExecution loadStep = findStepExecution(execution, "loadStep");

    assertThat(loadStep.getStatus())
            .isEqualTo(BatchStatus.COMPLETED);
    assertThat(loadStep.getExitStatus().getExitCode())
            .isEqualTo("COMPLETED");
    assertThat(loadStep.getEndTime()).isNotNull();
}
```

Checking individual Steps helps localize issues. A Job may end via a custom transition while an earlier Step produced a specific exit code; inspecting only Job status does not show which Steps ran and how they ended.

## 6. Testing a Failed Job

To test `FAILED`, create a deterministic failure condition in the test, such as a test Tasklet throwing an exception or a processor receiving bad test data. Avoid relying on real external services failing randomly.

Example of an intentionally failing Step in a test:

```java
@Bean
Step failingStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {

    return new StepBuilder("failingStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                throw new IllegalStateException("Expected test failure");
            }, transactionManager)
            .build();
}

@Bean
Job failingJob(JobRepository jobRepository, Step failingStep) {
    return new JobBuilder("failingJob", jobRepository)
            .start(failingStep)
            .build();
}
```

Verifying the outcome:

```java
@Test
void jobFailsWhenStepThrowsException() throws Exception {
    jobLauncherTestUtils.setJob(failingJob);

    JobExecution execution = jobLauncherTestUtils.launchJob(
            testJobParameters());

    assertThat(execution.getStatus())
            .isEqualTo(BatchStatus.FAILED);
    assertThat(execution.getExitStatus().getExitCode())
            .isEqualTo(ExitStatus.FAILED.getExitCode());
    assertThat(execution.getAllFailureExceptions()).isNotEmpty();

    StepExecution step = findStepExecution(execution, "failingStep");
    assertThat(step.getStatus()).isEqualTo(BatchStatus.FAILED);
    assertThat(step.getFailureExceptions()).isNotEmpty();
}
```

Some exceptions can be handled by retry or skip, so merely throwing an exception inside a processor/writer does not guarantee the Job becomes `FAILED`. Tests must configure an exception outside retry/skip policies or exceed limits to test the failure branch.

## 7. Testing STOPPED

A Job can stop via a `.stop()` or `.stopAndRestart(...)` flow transition. This is a deterministic way to produce `STOPPED` in integration tests without depending on the timing of a running thread.

Example flow with an approval-wait branch:

```java
@Bean
Job approvalJob(
        JobRepository jobRepository,
        Step approvalCheckStep,
        Step paymentStep) {

    return new JobBuilder("approvalJob", jobRepository)
            .start(approvalCheckStep)
                .on("WAITING_FOR_APPROVAL").stop()
            .from(approvalCheckStep)
                .on("APPROVED").to(paymentStep)
            .end()
            .build();
}
```

When the test fixture causes `approvalCheckStep` to return exit code `WAITING_FOR_APPROVAL`, assert:

```java
assertThat(execution.getStatus()).isEqualTo(BatchStatus.STOPPED);
assertThat(execution.getExitStatus().getExitCode())
        .isEqualTo(ExitStatus.STOPPED.getExitCode());
```

Also verify that `paymentStep` has no `StepExecution`, since the flow stopped before invoking that Step.

### Testing JobOperator.stop

`JobOperator.stop(executionId)` sends a stop request to a running Job. Testing this path usually requires an asynchronous JobLauncher or a Step with a controlled wait/synchronization point. The test should:

1. Launch the Job and capture the JobExecution ID.
2. Wait until the execution has genuinely started.
3. Call `jobOperator.stop(executionId)`.
4. Wait for the Job to reach a terminal status.
5. Reload the execution and assert `STOPPED`.

Avoid using arbitrary `Thread.sleep` durations assuming the Job has reached the desired state. Use latches/barriers in test fixtures or a wait utility with timeouts to synchronize on deterministic events. Also distinguish between the stop request being accepted and the Job actually reaching `STOPPED`.

## 8. Testing Custom ExitStatus and Flow Routing

A Step can finish technically successfully yet return a business exit code:

```java
@Bean
Step checkInputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {

    return new StepBuilder("checkInputStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                contribution.setExitStatus(new ExitStatus("NO_DATA"));
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

The flow can use that exit code to terminate successfully or route to another Step:

```java
@Bean
Job optionalImportJob(
        JobRepository jobRepository,
        Step checkInputStep,
        Step importStep,
        Step emptyReportStep) {

    return new JobBuilder("optionalImportJob", jobRepository)
            .start(checkInputStep)
                .on("NO_DATA").to(emptyReportStep)
            .from(checkInputStep)
                .on("COMPLETED").to(importStep)
            .from(emptyReportStep)
                .on("COMPLETED").end()
            .from(importStep)
                .on("COMPLETED").end()
            .end()
            .build();
}
```

Tests must verify both the Step's exit code and which subsequent Step was invoked:

```java
StepExecution check = findStepExecution(execution, "checkInputStep");

assertThat(check.getStatus()).isEqualTo(BatchStatus.COMPLETED);
assertThat(check.getExitStatus().getExitCode()).isEqualTo("NO_DATA");

assertThat(execution.getStepExecutions())
        .extracting(StepExecution::getStepName)
        .contains("emptyReportStep")
        .doesNotContain("importStep");
```

The Job can still end `COMPLETED` after running `emptyReportStep`. A test asserting only Job status without checking Steps will miss cases where the flow took the wrong branch.

## 9. Testing Bypassed Steps

When a conditional transition skips over a Step, that Step is not executed and has no `StepExecution` in the current JobExecution.

You can verify this by asserting that the StepExecution list does not contain the bypassed Step's name:

```java
assertThat(execution.getStepExecutions())
        .extracting(StepExecution::getStepName)
        .doesNotContain("optionalEnrichmentStep");
```

This tests flow routing. Do not look for `BatchStatus.SKIPPED` on a bypassed Step; skipping items inside a chunk and bypassing a Step are two separate mechanisms.

## 10. Testing Skips and Retries When the Job Remains COMPLETED

A Job can end `COMPLETED` even when items were skipped or successfully retried. Therefore, final-status tests should also verify counters whenever fault tolerance is part of the requirements.

Example Step allowing skips for a data exception:

```java
@Test
void jobCompletesWithinSkipLimit() throws Exception {
    jobLauncherTestUtils.setJob(importJob);

    JobExecution execution = jobLauncherTestUtils.launchJob(
            testJobParameters());

    assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);

    StepExecution step = findStepExecution(execution, "importStep");
    assertThat(step.getStatus()).isEqualTo(BatchStatus.COMPLETED);
    assertThat(step.getSkipCount()).isEqualTo(2);
    assertThat(step.getProcessSkipCount()).isEqualTo(2);
}
```

Values in the example are expected outcomes of the test fixture, not default values. If retries eventually succeed, the Step can still be `COMPLETED`; inspect retry metrics/listeners or mock invocation counts to confirm retries actually occurred.

If skip count exceeds `skipLimit`, the Step normally fails. Write separate tests for right at the threshold and above the threshold to verify the policy works as designed.

## 11. Testing Restart and JobInstance Identity

Restarts are an important part of final status testing. After an eligible `FAILED` or `STOPPED` execution, the next run must create a new JobExecution for the same JobInstance.

Example test using the same identifying parameters:

```java
@Test
void restartUsesSameJobInstance() throws Exception {
    jobLauncherTestUtils.setJob(restartableJob);

    JobParameters parameters = new JobParametersBuilder()
            .addString("businessDate", "2026-11-15")
            .addString("testRunId", UUID.randomUUID().toString())
            .toJobParameters();

    JobExecution firstExecution =
            jobLauncherTestUtils.launchJob(parameters);

    assertThat(firstExecution.getStatus()).isEqualTo(BatchStatus.FAILED);

    // Test fixture is configured so the subsequent run succeeds.
    JobExecution restartedExecution =
            jobLauncherTestUtils.launchJob(parameters);

    assertThat(restartedExecution.getStatus())
            .isEqualTo(BatchStatus.COMPLETED);
    assertThat(restartedExecution.getJobInstance().getInstanceId())
            .isEqualTo(firstExecution.getJobInstance().getInstanceId());
    assertThat(restartedExecution.getId())
            .isNotEqualTo(firstExecution.getId());
}
```

The test fixture must make the first run fail and the second run succeed, for example using a stateful test service. Crucially, both launches use the exact same identifying parameters. If you generate a new `testRunId` on the second launch, the test creates a new JobInstance and does not test restart.

To test the restart API directly, use `JobOperator.restart(previousExecutionId)` once the old execution is in a restartable state. You can then retrieve the new JobExecution via `JobExplorer` using the returned ID.

## 12. Inspecting Failure Exceptions and Exit Descriptions

When a Job fails, asserting only `BatchStatus.FAILED` may be insufficient. Inspect failure exceptions at the Job or Step level:

```java
assertThat(execution.getAllFailureExceptions())
        .anySatisfy(exception ->
                assertThat(exception)
                        .isInstanceOf(IllegalStateException.class));

StepExecution failedStep = findStepExecution(execution, "failingStep");

assertThat(failedStep.getFailureExceptions())
        .anySatisfy(exception ->
                assertThat(exception.getMessage())
                        .contains("Expected test failure"));
```

`ExitStatus.getExitDescription()` can also hold diagnostic info. Avoid asserting entire stack traces or environment-dependent messages if the test goal is verifying status. Assert exception types, business error codes, or a stable message fragment.

Avoid putting sensitive data into failure descriptions or logs. Messages from databases, HTTP clients, or input files may contain data that should not appear on operational dashboards.

## 13. Testing Status in Multi-Branch Job Flows

For Jobs with multiple transitions, verify every critical path:

| Condition | Input Step/ExitStatus | Expected Result |
|---|---|---|
| Valid data | `COMPLETED` | Runs import Step then report; Job `COMPLETED`. |
| No data | `NO_DATA` | Bypasses import, runs empty report; Job `COMPLETED`. |
| Critically invalid data | `INVALID_DATA` | Takes fail branch or error Step; Job `FAILED`. |
| Awaiting approval | `WAITING_FOR_APPROVAL` | Flow stops; Job `STOPPED`. |
| Processing Step throws non-skipped/non-retried exception | `FAILED` | Job `FAILED`, failure exception recorded. |

You do not need to test every imaginable combination. Focus on each declared flow branch and business-significant boundary conditions. Each test should have deterministic input data so outcomes are repeatable.

## 14. Testing with JobLauncherTestUtils.launchStep

If you only want to test a single Step without running the entire Job, `JobLauncherTestUtils` provides `launchStep`:

```java
@Test
void validateStepCompletesInIsolation() throws Exception {
    jobLauncherTestUtils.setJob(importJob);

    JobExecution execution = jobLauncherTestUtils.launchStep(
            "validateStep",
            testJobParameters());

    assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);

    StepExecution step = findStepExecution(execution, "validateStep");
    assertThat(step.getStatus()).isEqualTo(BatchStatus.COMPLETED);
}
```

`launchStep` is useful for testing readers, processors, writers, listeners, or StepScope beans within a Step's scope. However, it does not replace integration tests for the full Job flow. When verifying transitions, bypassed Steps, final Job status, or restarts, launch the actual Job.

## 15. Testing StepScope and JobScope

Readers/processors/writers can use `@StepScope` or `@JobScope` to access JobParameters and ExecutionContext. In tests, `@SpringBatchTest` registers listeners supporting these scopes.

For isolated component tests, you can use `StepScopeTestUtils` to execute a callback inside StepScope with a specific `ExecutionContext`:

```java
ExecutionContext context = new ExecutionContext();
context.putString("inputFile", "classpath:orders.csv");

StepExecution stepExecution = MetaDataInstanceFactory
        .createStepExecution(jobParameters, context);

StepScopeTestUtils.doInStepScope(stepExecution, () -> {
    ItemReader<OrderInput> reader = applicationContext.getBean(
            "orderReader", ItemReader.class);
    // Perform read calls and assert results.
    return null;
});
```

The snippet illustrates scope setup; generic types and bean lookup must match the application's bean definition. For JobScope, use the corresponding test utility or run the Job through `JobLauncherTestUtils` so the framework establishes scope naturally.

## 16. JobRepositoryTestUtils and Test Data

Job metadata is persisted in JobRepository. If multiple tests share the same metadata database and identical identifying parameters, test outcomes can interfere with each other.

Two common approaches:

- Generate distinct identifying JobParameters per test.
- Use `JobRepositoryTestUtils` to clean metadata after tests in a dedicated test repository.

Example:

```java
@Autowired
private JobRepositoryTestUtils jobRepositoryTestUtils;

@AfterEach
void cleanBatchMetadata() {
    jobRepositoryTestUtils.removeJobExecutions();
}
```

Only use this cleanup against an isolated test database/repository. `removeJobExecutions()` can delete execution metadata in the configured repository; never invoke it on a repository shared with operational data or other tests. In parallel test environments, each test suite should have its own database/schema or an explicit isolation strategy.

Do not rely on `@Transactional` on a test method to automatically roll back an entire Job. JobLauncher can run in separate transactions or threads; metadata and business data can commit independently of the test's transaction.

## 17. Testing an Asynchronous JobLauncher

If JobLauncher uses an asynchronous TaskExecutor, `launchJob()` can return while the Job is still `STARTED`. In that case, the following test can fail spuriously:

```java
JobExecution execution = jobLauncherTestUtils.launchJob(parameters);
assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
```

The test must wait for the execution to reach a terminal state, then reload from `JobExplorer` or the repository to inspect the latest metadata.

One approach:

1. Launch the Job and retrieve the execution ID.
2. Use `JobExplorer.getJobExecution(id)` to read the latest status.
3. Wait with a bounded timeout until status is `COMPLETED`, `FAILED`, `STOPPED`, or the expected terminal status.
4. If the timeout expires while still `STARTED`/`STOPPING`, fail the test with current status and StepExecution details.

Use `CountDownLatch`, test listeners, or a wait utility like Awaitility to synchronize on events. Avoid arbitrary long `Thread.sleep` calls because they slow tests down and cause flakiness.

## 18. Testing Process Kill Differs from Testing a Failed Job

A test where a Tasklet throws an exception verifies the normal `FAILED` termination path. It does not simulate a killed process, because Spring Batch still gets a chance to catch the exception and update metadata.

To test crash recovery, you must run the Job in an independently terminable process, kill the process at a controlled point, and then restart the application against the same JobRepository and JobParameters. Then verify:

- Whether the old execution metadata has a stale `STARTED` status.
- Whether the recovery procedure brings the execution to a restartable state.
- Whether the last committed checkpoint is restored properly.
- Whether already committed chunks are not unintentionally re-written.
- Whether external side effects are not duplicated or can be reconciled.
- Whether the new JobExecution belongs to the same JobInstance.

This is a higher-cost integration/system test than regular status tests. It cannot be proven by a unit test that simply calls `launchJob` and asserts `FAILED`.

## 19. Common Pitfalls When Testing Final Status

### Asserting only Job BatchStatus

A Job may be `COMPLETED` yet the flow took the wrong branch or an optional Step never ran. Also inspect StepExecution, ExitStatus, and the list of executed Steps.

### Asserting only ExitStatus

A custom exit code does not tell the full lifecycle story. Check BatchStatus too so `COMPLETED`, `FAILED`, and `STOPPED` are clearly distinguished.

### Using the same JobParameters across independent tests

An earlier JobInstance may already be complete and block subsequent launches. Use distinct identifying parameters for independent tests; reuse identical parameters for restart tests.

### Assuming launchJob is always synchronous

With an asynchronous JobLauncher, execution may still be `STARTED`. Wait for terminal state and reload metadata.

### Not checking the failure exception

The Job may have `FAILED` due to a different error than the test expected. Assert the exception type or a stable error code.

### Using a Step test to conclude the Job flow is right

`launchStep` does not test full Job transitions. Use `launchJob` to test flows, bypasses, stops, and final Job status.

### Clearing metadata on a shared repository

Cleanup can disrupt other tests or operational data. Use an isolated test repository/database.

### Treating a thrown exception as proof the Job failed

The exception might be retried or skipped. Assert final status and counters, rather than only verifying a mock threw an exception.

### Using standard tests to claim process kill coverage

An exception test is not equivalent to SIGKILL. Crash recovery requires process boundaries and a persistent JobRepository.

## 20. Final Status Test Matrix

A foundational status test suite can cover:

| Scenario | Job BatchStatus | Job ExitStatus | Additional Checks |
|---|---|---|---|
| All Steps complete | `COMPLETED` | `COMPLETED` or flow-defined code | Expected Steps all have a StepExecution. |
| Unhandled exception | `FAILED` | `FAILED` | Failure exception and failed Step. |
| Approval-wait branch | `STOPPED` | `STOPPED` | Steps after stop point did not run; restartable if eligible. |
| Step returns `NO_DATA` then succeeds | `COMPLETED` | Per final flow | Step has `ExitStatus.NO_DATA`; import Step bypassed. |
| Skipped items within limit | Usually `COMPLETED` | Per flow | Skip count and SkipListener accurate. |
| Skip limit exceeded | `FAILED` | `FAILED` | Skip count exceeds threshold and matching failure exception. |
| Retry succeeds | Usually `COMPLETED` | Per flow | Retry count/callback accurate; no duplicate output. |
| Restart after failed execution | `COMPLETED` after new run if recovery succeeds | Per flow | Same JobInstance, new JobExecution ID. |

This matrix is a guideline. Jobs can set custom ExitStatus at the Step or Job level, so tests should assert the exact outcome code expected by the real flow rather than always assuming ExitStatus equals the BatchStatus name.

## 21. Workflow for Writing Final Status Tests

When adding tests for a Job, follow this sequence:

1. Identify the valid terminal statuses of the Job: `COMPLETED`, `FAILED`, `STOPPED`, or special operational cases.
2. List custom ExitStatus codes used by the flow for branching.
3. Prepare deterministic test fixtures for success, failure, skip, retry, and stop.
4. Use `@SpringBatchTest` and `JobLauncherTestUtils` to launch the Job.
5. Generate unique JobParameters for independent tests; reuse identical parameters when testing restarts.
6. Assert both `JobExecution.getStatus()` and `getExitStatus().getExitCode()`.
7. Locate critical StepExecutions and assert status, exit code, counters, and failure exceptions.
8. Verify Steps were executed or bypassed according to the flow.
9. If the launcher is asynchronous, await terminal state and reload via JobExplorer.
10. Clean metadata only on an isolated test repository.
11. For crash recovery, run a separate test process and simulate an actual kill.

## Conclusion

Testing final status in Spring Batch requires verifying both `BatchStatus` and `ExitStatus` for Jobs and Steps, while also checking executed Steps, flow branches, failure exceptions, and relevant counters. `@SpringBatchTest` and `JobLauncherTestUtils` fit launching Jobs/Steps in integration tests; `JobRepositoryTestUtils` helps clean metadata in an isolated test repository. Use distinct JobParameters for independent tests, preserve identifying parameters when testing restarts, and wait for terminal state if JobLauncher runs asynchronously. A test that throws an exception does not replace process kill testing; crash recovery requires simulating process boundaries, a persistent JobRepository, checkpoints, and real side effects.
