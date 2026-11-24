# Testing JobInstance in Spring Batch

## 1. Objectives

When testing a batch job, asserting that the job returns `COMPLETED` only shows that **a single execution** succeeded. To verify rerun and restart mechanisms properly, you must also test **JobInstance**: how Spring Batch determines whether two run requests belong to the same instance, how many executions it creates, and under what conditions it permits a rerun.

After this lesson, you will be able to:

- Distinguish `Job`, `JobInstance`, and `JobExecution` in tests.
- Intentionally construct `JobParameters` to control the identity of a `JobInstance`.
- Test first-run, rerun-after-completion, different-parameter, and restart-after-failure scenarios.
- Use `JobExplorer`, `JobRepository`, and `spring-batch-test` to inspect metadata instead of relying solely on logs.
- Recognize cases where tests produce misleading results due to random parameters, leftover metadata, or auto-launching jobs.

## 2. What Is a JobInstance and Why Test It?

A `Job` is a job definition consisting of steps and execution flow. On each job launch request, Spring Batch determines the `JobInstance` from the **job name** and **the JobParameters marked as identifying**.

Conceptually:

```text
JobInstance = Job name + identifying JobParameters

Job: importOrdersJob
    |
    +-- JobInstance A: businessDate=2026-11-16
    |      +-- JobExecution 101: FAILED
    |      +-- JobExecution 102: COMPLETED (restart)
    |
    +-- JobInstance B: businessDate=2026-11-17
           +-- JobExecution 103: COMPLETED
```

| Component | Meaning | What to Assert in Tests |
| --- | --- | --- |
| `Job` | Definition of the processing workflow | The right job is invoked |
| `JobParameters` | Inputs for a run; each parameter has an identifying flag | Identifying parameters are configured intentionally |
| `JobInstance` | Logical identity of a data processing run for a given identifying parameter set | Same identifying parameters resolve to the same instance; different ones create a different instance |
| `JobExecution` | A single execution attempt of an instance | Each valid restart creates a new execution |
| `StepExecution` | Execution of a single step within a JobExecution | Which steps were rerun or skipped during restart |
| `JobRepository` | Storage and manager of batch metadata | Metadata exists and no unintended duplicate instances are created |
| `JobExplorer` | API for reading persisted metadata | Instance count, execution count, and statuses match expectations |

**Note:** `BatchStatus` (such as `COMPLETED`, `FAILED`, `STOPPED`) represents the processing status; `ExitStatus` is the exit outcome that can be customized for flow control or reporting. Do not conflate these two concepts.

### Identifying and Non-Identifying Parameters

By default, standard parameter-adding methods in `JobParametersBuilder` create identifying parameters. You can also specify this explicitly:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16", true) // Identifies the instance
    .addString("requestId", "req-001", false)      // For tracing only
    .toJobParameters();
```

Changing `businessDate` changes the instance identity. Changing only `requestId` does **not** create a new instance.

This also explains a common design pitfall: adding a random `run.id` or timestamp as an **identifying** parameter on every run causes Spring Batch to create a new instance each time, so the test no longer verifies rerun behavior on the same instance.

## 3. Scenarios to Test

Suppose the job is named `importOrdersJob` and its identifying parameter is `businessDate`:

| Scenario | Condition | Expected Result |
| --- | --- | --- |
| First run | No instance exists for `businessDate=D1` | Creates one `JobInstance` and one `JobExecution` |
| Rerun after success | Instance for `D1` is already `COMPLETED` | Rejects the new run, typically with `JobInstanceAlreadyCompleteException` |
| Run with a different date | Instance `D1` exists; invoked with `D2` | Creates a new instance with a different ID |
| Change non-identifying parameter | Keep `D1`, change `requestId` | Still the same instance; rejected if already completed |
| Restart after failure | Previous execution for `D1` is `FAILED`, job allows restart | Instance ID stays the same; a new JobExecution is added |
| Duplicate run while job is active | An execution of the same instance is currently running | Rejects concurrent launch, typically with `JobExecutionAlreadyRunningException` |
| Restart non-restartable job | Instance already exists and job sets `restartable=false` | Rejects restart, typically with `JobRestartException` |

Exceptions must be tested under **conditions that genuinely trigger them**. For example, do not use a job that finishes too quickly to test concurrent execution, because the job might finish before the second request arrives.

## 4. Testing Strategy

A JobInstance test is typically an **integration test**: it requires a real `JobLauncher`, `JobRepository`, and metadata store (such as a test H2 database). Mocking the entire repository and hardcoding instance IDs only tests mock behavior, not Spring Batch's instance-identification algorithm and restart rules.

With Spring Boot 3.x and Spring Batch 5.x, common dependencies (Gradle) are:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-batch'
testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'org.springframework.batch:spring-batch-test'
testRuntimeOnly 'com.h2database:h2'
```

In the test environment:

- Disable automatic job execution when the application context starts via `spring.batch.job.enabled=false`.
- Initialize the metadata schema for the test database, e.g., `spring.batch.jdbc.initialize-schema=always` when using a dedicated test H2 database.
- Isolate metadata between tests, such as using `JobRepositoryTestUtils.removeJobExecutions()` or a separate database.
- Use a **fixed** `JobParameters` set when testing reruns, and a different set when testing new instance creation.
- Verify both the result returned by the launcher and the metadata read back via `JobExplorer`.

`@SpringBatchTest` provides utilities like `JobLauncherTestUtils` and `JobRepositoryTestUtils`. However, `JobLauncherTestUtils.launchJob()` **without arguments** typically generates unique parameters to support isolated tests. To test JobInstance identity, pass explicit parameters to `launchJob(parameters)` or call `jobLauncher.run(job, parameters)` directly.

## 5. Integration Example with JUnit 5

The following example creates a simple job with one tasklet. The `failNextExecution` flag lets the test deliberately fail the next execution to test restart. The test app uses H2 and Spring Batch metadata, requiring no access to external systems.

> The example targets Spring Boot 3.x / Spring Batch 5.x. When your application uses a different version, adjust the batch infrastructure declarations and dependencies accordingly.

```java
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

import static org.junit.jupiter.api.Assertions.*;

@SpringBatchTest
@SpringBootTest(
    classes = JobInstanceIntegrationTest.TestApplication.class,
    properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always",
        "spring.datasource.url=jdbc:h2:mem:job_instance_test;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.datasource.username=sa",
        "spring.datasource.password="
    }
)
class JobInstanceIntegrationTest {

    @Autowired
    private JobLauncher jobLauncher;

    @Autowired
    private JobExplorer jobExplorer;

    @Autowired
    private JobRepositoryTestUtils repositoryTestUtils;

    @Autowired
    @Qualifier("instanceDemoJob")
    private Job job;

    @Autowired
    private AtomicBoolean failNextExecution;

    @BeforeEach
    void cleanBeforeEachTest() {
        repositoryTestUtils.removeJobExecutions();
        failNextExecution.set(false);
    }

    private JobParameters businessDate(String date) {
        return new JobParametersBuilder()
            .addString("businessDate", date, true)
            .toJobParameters();
    }

    @Test
    void completedInstanceCannotBeExecutedAgain() throws Exception {
        JobParameters parameters = businessDate("2026-11-16");

        JobExecution first = jobLauncher.run(job, parameters);

        assertEquals(BatchStatus.COMPLETED, first.getStatus());
        assertThrows(
            JobInstanceAlreadyCompleteException.class,
            () -> jobLauncher.run(job, parameters)
        );

        List<JobInstance> instances =
            jobExplorer.getJobInstances(job.getName(), 0, 10);

        assertEquals(1, instances.size());
        assertEquals(1, jobExplorer.getJobExecutions(instances.get(0)).size());
    }

    @Test
    void differentIdentifyingParametersCreateDifferentInstances()
            throws Exception {
        JobExecution first =
            jobLauncher.run(job, businessDate("2026-11-16"));
        JobExecution second =
            jobLauncher.run(job, businessDate("2026-11-17"));

        assertEquals(BatchStatus.COMPLETED, first.getStatus());
        assertEquals(BatchStatus.COMPLETED, second.getStatus());
        assertNotEquals(
            first.getJobInstance().getInstanceId(),
            second.getJobInstance().getInstanceId()
        );
        assertEquals(
            2,
            jobExplorer.getJobInstances(job.getName(), 0, 10).size()
        );
    }

    @Test
    void nonIdentifyingParameterDoesNotCreateAnotherInstance()
            throws Exception {
        JobParameters firstParameters = new JobParametersBuilder()
            .addString("businessDate", "2026-11-16", true)
            .addString("requestId", "req-001", false)
            .toJobParameters();

        JobParameters secondParameters = new JobParametersBuilder()
            .addString("businessDate", "2026-11-16", true)
            .addString("requestId", "req-002", false)
            .toJobParameters();

        JobExecution first = jobLauncher.run(job, firstParameters);

        assertEquals(BatchStatus.COMPLETED, first.getStatus());
        assertThrows(
            JobInstanceAlreadyCompleteException.class,
            () -> jobLauncher.run(job, secondParameters)
        );
        assertEquals(
            1,
            jobExplorer.getJobInstances(job.getName(), 0, 10).size()
        );
    }

    @Test
    void failedExecutionCanRestartWithinSameInstance() throws Exception {
        JobParameters parameters = businessDate("2026-11-16");
        failNextExecution.set(true);

        JobExecution failed = jobLauncher.run(job, parameters);
        JobExecution restarted = jobLauncher.run(job, parameters);

        assertEquals(BatchStatus.FAILED, failed.getStatus());
        assertEquals(BatchStatus.COMPLETED, restarted.getStatus());

        assertEquals(
            failed.getJobInstance().getInstanceId(),
            restarted.getJobInstance().getInstanceId()
        );
        assertNotEquals(failed.getId(), restarted.getId());

        JobInstance instance =
            jobExplorer.getJobInstances(job.getName(), 0, 1).get(0);
        assertEquals(2, jobExplorer.getJobExecutions(instance).size());
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {

        @Bean
        AtomicBoolean failNextExecution() {
            return new AtomicBoolean(false);
        }

        @Bean
        Job instanceDemoJob(
                JobRepository jobRepository,
                PlatformTransactionManager transactionManager,
                AtomicBoolean failNextExecution) {

            Step step = new StepBuilder("instanceDemoStep", jobRepository)
                .tasklet((contribution, chunkContext) -> {
                    if (failNextExecution.getAndSet(false)) {
                        throw new IllegalStateException(
                            "Simulated failure for restart test"
                        );
                    }
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();

            return new JobBuilder("instanceDemoJob", jobRepository)
                .start(step)
                .build();
        }
    }
}
```

### Explaining the Assertions

**Test 1 — Rerunning a completed instance.** The first `jobLauncher.run(job, parameters)` must succeed; the second call with the exact same identifying parameters is rejected. The two metadata assertions confirm there is only one instance and one execution, so no extraneous execution was created after the exception.

**Test 2 — Different identifying parameters.** Two `businessDate` values create two instances with different IDs. Checking that both executions are `COMPLETED` serves as an additional condition: both instances actually ran.

**Test 3 — Non-identifying parameter.** `requestId` changes while `businessDate` stays the same. If a test merely compares the entire `JobParameters` objects, you might wrongly conclude these are two different instances. Inspecting metadata confirms Spring Batch's identification rule.

**Test 4 — Restart after failure.** The tasklet is configured to fail exactly once; the next run completes. The two `JobExecution` objects have different IDs, yet both point to the same `JobInstance`. This is the core difference between **restart** and **creating a new instance**.

The test intentionally uses a synchronous job and an error-control flag so the restart scenario yields deterministic outcomes. When applying to a real project, replace `instanceDemoJob` with the job under test while keeping the pattern of controlling inputs and querying metadata. If the test suite runs in parallel or shares a database, isolate contexts and data so no test deletes another test's metadata.

## 6. Inspecting Metadata Directly

In an environment using `JdbcJobRepository`, you can cross-check details in the metadata tables:

- `BATCH_JOB_INSTANCE`: records instances, job names, and identifying keys.
- `BATCH_JOB_EXECUTION`: records each execution attempt and its status, linked to an instance.
- `BATCH_JOB_EXECUTION_PARAMS`: records execution parameters, including the identifying parameter flag.
- `BATCH_STEP_EXECUTION`: supports analyzing which steps ran, failed, or were reprocessed.

Sample query for observation only—do not put this SQL into primary assertions:

```sql
SELECT
    ji.JOB_INSTANCE_ID,
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.EXIT_CODE
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
    ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'instanceDemoJob'
ORDER BY ji.JOB_INSTANCE_ID, je.JOB_EXECUTION_ID;
```

When restarting after a failure, you expect two rows with the same `JOB_INSTANCE_ID` but different `JOB_EXECUTION_ID` values. If reruns generate a different `JOB_INSTANCE_ID`, inspect identifying parameters and any auto-incrementing `run.id` mechanisms.

Prefer `JobExplorer` in Java tests to avoid direct coupling to table names, column types, and schema variations across versions. SQL is better suited for debugging failures or inspecting operational data.

## 7. Testing Edge Cases

### 7.1. Two Concurrent Requests for the Same Instance

This is a concurrency-control test, distinct from two sequential calls. A controllable approach:

1. Have the first step wait on a `CountDownLatch`, so the first execution is genuinely running.
2. Use the launcher or an appropriate execution mechanism to run the first request on a separate thread.
3. Only after confirming the first execution is `STARTED`, submit the second request with **the same identifying parameters**.
4. Assert that the second request is rejected with `JobExecutionAlreadyRunningException` and that there are not two active executions for the same instance.
5. Release the latch, wait for the first thread to finish, and clean up resources in `finally`.

Do not use `Thread.sleep` to *guess* when the step starts; timing dependence easily causes flaky tests. Do not test with an instantaneously finishing step, because the second request may hit an already-completed instance instead of a running one.

### 7.2. Non-Restartable Jobs

You can define a non-restartable job:

```java
Job nonRestartableJob = new JobBuilder("nonRestartableJob", jobRepository)
    .start(step)
    .preventRestart()
    .build();
```

Let the first execution fail in a controlled way, then call again with the same parameters. Assert `JobRestartException` and verify no new execution is created. You must use an **already-executed instance**, because a `preventRestart()` job is still allowed to run for the first time with a new parameter set.

### 7.3. Completed Steps on Restart

The same JobInstance does not mean every step runs again. In a multi-step job, steps that are already `COMPLETED` are typically skipped on restart unless configured to allow re-execution (e.g., `allowStartIfComplete(true)`). Tests should read `StepExecution` records or verify actual invocation counts to confirm the failed step reruns and completed steps are not unintentionally re-executed.

### 7.4. Matching Metadata but Wrong Business Data

A unique `JobInstance` alone does not guarantee no duplicate orders are written or no notifications are sent twice. A job may persist partial data before failing; upon restart, write steps must have appropriate transactions, checkpoints, or idempotency mechanisms. Therefore, for real problems, combine metadata tests with assertions on business tables or outputs after each run.

## 8. Common Errors When Writing Tests

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Two invocations always create new instances | Adding a timestamp, UUID, or identifying `run.id` each time | Pass the exact identifying parameters from the first run |
| Rerun test does not throw an exception | `JobLauncherTestUtils.launchJob()` auto-generates unique parameters | Use `launchJob(parameters)` or `jobLauncher.run(job, parameters)` |
| Test passes in isolation but fails in the full suite | Leftover metadata from prior tests or multiple tests sharing a DB | Clean metadata in a controlled manner; use isolated databases/contexts |
| Job runs before the test calls the launcher | Spring Boot auto-launches jobs at startup | Set `spring.batch.job.enabled=false` |
| `requestId` parameter increases instance count | Marked as identifying | Use `addString("requestId", value, false)` |
| Restart creates a new instance | Identifying parameters changed | Keep identifying parameters unchanged; do not auto-increment run ID |
| Metadata tables not found | Batch schema not initialized | Configure schema for the test DB and check dependencies |
| Parallel tests fail intermittently | Sharing the same DB, job name, or failure-control flag | Isolate state and avoid wiping data from other threads |

## 9. Practice Exercise

Extend `instanceDemoJob` into a job with two steps: `validateInputStep` and `persistDataStep`. On the first run, let the first step complete and the second step fail; on the second run, let the job restart successfully with the same `businessDate`.

Verify all three outcomes: there is only **one JobInstance**, there are **two JobExecutions**, and `validateInputStep` does not re-execute if it already completed and is not configured with `allowStartIfComplete(true)`. Next, try marking `sourceSystem` as identifying as well and observe how the instance count increases when this parameter value changes.

## 10. Conclusion

The key to JobInstance testing is **identity and lifecycle**: the same job name plus the same set of identifying parameters identifies the same instance; an instance can have multiple executions during valid restarts; a completed instance cannot be re-run with the same identity. Combining `JobLauncher` to trigger behavior with `JobExplorer` to inspect metadata helps uncover parameter configuration, duplicate-run, and restart bugs earlier than merely observing `COMPLETED` status.
