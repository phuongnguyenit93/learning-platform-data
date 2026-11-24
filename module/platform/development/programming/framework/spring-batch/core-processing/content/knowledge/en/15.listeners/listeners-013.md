# Testing Listeners with Execution Status

In Spring Batch, `JobExecutionListener` provides two callbacks—`beforeJob()` and `afterJob()`—to perform work tied to the lifecycle of a Job run. When testing a listener, you need to verify that callbacks are invoked at the right time, receive the right `JobExecution`, and handle statuses such as `COMPLETED`, `FAILED`, or `STOPPED` accurately.

The key point is that listeners operate on a **JobExecution**, meaning a specific run. A `JobInstance` can have multiple `JobExecution` instances if the Job is restarted. Therefore, tests must verify the status of each run and avoid relying on state stored in listener fields to infer outcomes.

## 1. Identifying Behaviors to Test

`JobExecutionListener` has two methods:

```java
public interface JobExecutionListener {
    void beforeJob(JobExecution jobExecution);
    void afterJob(JobExecution jobExecution);
}
```

- `beforeJob()` is invoked before the Job starts executing its Steps. It can record Job startup, `JobParameters`, or create an audit record.
- `afterJob()` is invoked after the Job finishes. It can persist the final status, aggregate metrics, or signal the outcome.

A listener often needs to react differently depending on `BatchStatus`:

| BatchStatus | Meaning | Testable Behavior |
|---|---|---|
| `COMPLETED` | Job ended normally according to configured flow | Record success, persist `ExitStatus` and completion timestamp. |
| `FAILED` | Job failed | Record failure, save failure exceptions, and raise alerts. |
| `STOPPED` | Job was stopped cleanly | Record stopped status and recovery info. |
| `ABANDONED` | Execution marked not to continue via normal restart | Record separate administrative status. |
| `UNKNOWN` | Status cannot be determined reliably | Route to investigation instead of treating as success. |

`BatchStatus` and `ExitStatus` must be verified separately. For example, a Job may have `BatchStatus.COMPLETED` while `ExitStatus` carries business code `NO_DATA`. Tests should confirm the listener preserves both values.

## 2. Separating Listener Logic for Unit Testing

A listener may call a service to save audit records. Pass values needed from `JobExecution` into the service so unit tests do not depend on a database or Spring context.

```java
import java.util.List;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class JobOutcomeListener implements JobExecutionListener {

    private final JobAuditService auditService;

    public JobOutcomeListener(JobAuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void beforeJob(JobExecution jobExecution) {
        String jobName = jobExecution.getJobInstance().getJobName();
        auditService.recordStarted(
                jobExecution.getId(),
                jobName,
                jobExecution.getJobParameters());
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        String jobName = jobExecution.getJobInstance().getJobName();
        List<String> failureMessages = jobExecution.getAllFailureExceptions()
                .stream()
                .map(Throwable::getMessage)
                .toList();

        auditService.recordOutcome(
                jobExecution.getId(),
                jobName,
                jobExecution.getStatus(),
                jobExecution.getExitStatus().getExitCode(),
                failureMessages);
    }
}
```

`JobAuditService` is an application service that can persist audits to a database or forward data to a monitoring system:

```java
import java.util.List;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobParameters;
import org.springframework.stereotype.Service;

@Service
public class JobAuditService {

    public void recordStarted(
            Long executionId,
            String jobName,
            JobParameters parameters) {
        // Save start timestamp and run information.
    }

    public void recordOutcome(
            Long executionId,
            String jobName,
            BatchStatus status,
            String exitCode,
            List<String> failureMessages) {
        // Save final status and error details.
    }
}
```

Audit persistence lives in the service so the listener focuses on extracting data from `JobExecution`. In unit tests, you can mock the service and assert the listener passes the right data.

## 3. Creating JobExecution in Unit Tests

To test callbacks directly, create a `JobExecution` with a `JobInstance` and `JobParameters`, then set the status to test.

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.JobParameters;

private JobExecution newJobExecution() {
    JobInstance instance = new JobInstance(1L, "importOrdersJob");
    return new JobExecution(instance, 10L, new JobParameters());
}
```

In tests, change `BatchStatus` and `ExitStatus` to simulate execution outcomes:

```java
JobExecution execution = newJobExecution();
execution.setStatus(BatchStatus.COMPLETED);
execution.setExitStatus(ExitStatus.COMPLETED);
```

This is a metadata object used to test the listener. It does not execute a real Job and does not persist metadata to `JobRepository`. Therefore, this kind of unit test runs fast and is well suited for verifying callback logic.

## 4. Testing beforeJob() with Mockito

Tests for `beforeJob()` should verify that the listener records the right execution ID, Job name, and `JobParameters`.

```java
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.JobParameters;

@ExtendWith(MockitoExtension.class)
class JobOutcomeListenerBeforeTest {

    @Mock
    private JobAuditService auditService;

    @InjectMocks
    private JobOutcomeListener listener;

    @Test
    void recordsJobStart() {
        JobInstance instance = new JobInstance(1L, "importOrdersJob");
        JobParameters parameters = new JobParameters();
        JobExecution execution = new JobExecution(instance, 10L, parameters);

        listener.beforeJob(execution);

        verify(auditService).recordStarted(10L, "importOrdersJob", parameters);
    }
}
```

The test invokes the callback directly and uses Mockito's `verify` to assert the service was called once with matching arguments. If the listener puts a value into the Job `ExecutionContext`, verify that value after calling `beforeJob()`.

## 5. Testing afterJob() with COMPLETED Status

For a successful Job, the listener should record `BatchStatus.COMPLETED`, the `ExitStatus` code, and an empty error list.

```java
import static org.mockito.Mockito.verify;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.JobParameters;

@ExtendWith(MockitoExtension.class)
class JobOutcomeListenerCompletedTest {

    @Mock
    private JobAuditService auditService;

    @InjectMocks
    private JobOutcomeListener listener;

    @Test
    void recordsCompletedExecution() {
        JobExecution execution = new JobExecution(
                new JobInstance(1L, "importOrdersJob"),
                10L,
                new JobParameters());
        execution.setStatus(BatchStatus.COMPLETED);
        execution.setExitStatus(ExitStatus.COMPLETED);

        listener.afterJob(execution);

        verify(auditService).recordOutcome(
                10L,
                "importOrdersJob",
                BatchStatus.COMPLETED,
                "COMPLETED",
                List.of());
    }
}
```

This test confirms the listener not only checks status but also forwards the exact `ExitStatus` code and exception list. If the listener sends a success notification, mock the notification service and verify it is invoked only for appropriate statuses.

## 6. Testing FAILED and Failure Exceptions

When a Job fails, `JobExecution` can contain one or more failure exceptions. Listeners commonly need to record the status and error messages to aid investigation.

```java
import static org.mockito.Mockito.verify;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.JobParameters;

@ExtendWith(MockitoExtension.class)
class JobOutcomeListenerFailedTest {

    @Mock
    private JobAuditService auditService;

    @InjectMocks
    private JobOutcomeListener listener;

    @Test
    void recordsFailedExecutionAndException() {
        JobExecution execution = new JobExecution(
                new JobInstance(2L, "importOrdersJob"),
                20L,
                new JobParameters());
        execution.setStatus(BatchStatus.FAILED);
        execution.setExitStatus(ExitStatus.FAILED);
        execution.addFailureException(
                new IllegalStateException("Input file is invalid"));

        listener.afterJob(execution);

        verify(auditService).recordOutcome(
                20L,
                "importOrdersJob",
                BatchStatus.FAILED,
                "FAILED",
                List.of("Input file is invalid"));
    }
}
```

This test does not need to deliberately fail a database or file. Simply construct a `JobExecution` with the desired status and exception to test the listener's handling logic.

Do not merely assert that the listener called `recordOutcome()`. Verify the exact status, exit code, and errors passed in, since a single wrong value can cause dashboards or alerts to misreport Job health.

## 7. Using Parameterized Tests for Multiple Execution Statuses

When a listener handles multiple statuses under one rule, use JUnit 5 `@ParameterizedTest` to verify each status.

```java
import static org.mockito.Mockito.verify;

import java.util.List;
import java.util.stream.Stream;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.JobParameters;

@ExtendWith(MockitoExtension.class)
class JobOutcomeListenerStatusTest {

    @Mock
    private JobAuditService auditService;

    @InjectMocks
    private JobOutcomeListener listener;

    static Stream<BatchStatus> terminalStatuses() {
        return Stream.of(
                BatchStatus.COMPLETED,
                BatchStatus.FAILED,
                BatchStatus.STOPPED,
                BatchStatus.ABANDONED);
    }

    @ParameterizedTest
    @MethodSource("terminalStatuses")
    void recordsEveryTerminalStatus(BatchStatus status) {
        JobExecution execution = new JobExecution(
                new JobInstance(3L, "importOrdersJob"),
                30L,
                new JobParameters());
        execution.setStatus(status);
        execution.setExitStatus(new ExitStatus(status.name()));

        listener.afterJob(execution);

        verify(auditService).recordOutcome(
                30L,
                "importOrdersJob",
                status,
                status.name(),
                List.of());
    }
}
```

`UNKNOWN` and running statuses such as `STARTING`, `STARTED`, or `STOPPING` are not normal completion outcomes to test in the same terminal-status group. If the application handles those statuses explicitly, write corresponding tests to ensure the listener does not treat them as success.

## 8. Testing Custom ExitStatus

`BatchStatus` indicates the execution lifecycle state; `ExitStatus` can carry business codes. The listener should preserve both values.

Example where the Job completes normally with no data:

```java
JobExecution execution = newJobExecution();
execution.setStatus(BatchStatus.COMPLETED);
execution.setExitStatus(new ExitStatus("NO_DATA"));

listener.afterJob(execution);

verify(auditService).recordOutcome(
        10L,
        "importOrdersJob",
        BatchStatus.COMPLETED,
        "NO_DATA",
        List.of());
```

This test catches a common bug: reading only `BatchStatus` and writing that same value as the exit code. When routing Step branches, test the Job flow separately based on Step `ExitStatus`; listeners should simply observe the final outcome.

## 9. Integration Testing with Spring Batch Test

Unit tests verify callbacks directly, yet do not prove Spring Batch actually invokes the listener during the Job lifecycle. For integration testing, use the `spring-batch-test` module and `JobLauncherTestUtils`.

Add the test dependency matching the Spring Batch version used by your application. Maven example:

```xml
<dependency>
    <groupId>org.springframework.batch</groupId>
    <artifactId>spring-batch-test</artifactId>
    <scope>test</scope>
</dependency>
```

With Spring Boot, Boot's dependency management usually manages the compatible version. Do not pick a different version from the application's core Spring Batch version.

Example integration test for a successful Job:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
@SpringBatchTest
class ImportJobListenerIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JobAuditRepository auditRepository;

    @Test
    void listenerPersistsSuccessfulExecution() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("testRun", UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertTrue(auditRepository.existsByExecutionId(execution.getId()));
    }
}
```

This example assumes the test context has a Job configured for `JobLauncherTestUtils`, the listener is registered on the Job, and `JobAuditRepository` provides a lookup by execution ID. If the context has multiple Jobs, specify which Job `JobLauncherTestUtils` uses. The unique `testRun` parameter ensures test runs create distinct `JobInstance` records, avoiding rejection because a prior instance already `COMPLETED`.

To test failure, configure a test Job containing a Step that throws an exception:

```java
@Bean
public Step failingStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {
    return new StepBuilder("failingStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                throw new IllegalStateException("Simulated failure");
            }, transactionManager)
            .build();
}
```

When launching the test Job containing this Step, verify `JobExecution.getStatus()` is `FAILED` and the audit record captures the right execution ID and failure message. If `JobLauncherTestUtils.launchJob()` throws an exception in a specific test setup, query `JobExecution` from `JobRepository`/`JobExplorer` by ID or parameters to confirm final metadata.

## 10. Verifying Listeners Are Invoked in the Right Order

In an integration test, you can use a test listener that records events into a thread-safe collection or audit table. For a sequential Job, the expected order is:

```text
beforeJob
    |
    v
beforeStep
    |
    v
Step executes
    |
    v
afterStep
    |
    v
afterJob
```

If a Job has multiple Steps, Step callbacks appear according to the Job flow; `beforeJob` still runs before the Steps and `afterJob` after the Job finishes. When a Job has branches or parallel Steps, the order across Step callbacks can vary; do not write tests relying on unguaranteed thread ordering.

One way to verify is creating a test-only `RecordingJobExecutionListener`:

```java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;

public class RecordingJobExecutionListener implements JobExecutionListener {

    private final List<String> events = new CopyOnWriteArrayList<>();

    @Override
    public void beforeJob(JobExecution jobExecution) {
        events.add("before:" + jobExecution.getId());
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        events.add("after:" + jobExecution.getId());
    }

    public List<String> events() {
        return List.copyOf(events);
    }
}
```

After launching the test Job synchronously, assert that the first event is `before:<executionId>` and the last event is `after:<executionId>`. `CopyOnWriteArrayList` fits a small test event recorder that may be accessed across threads; in production listeners, do not retain execution history in a singleton bean's collection.

## 11. Testing Listeners When a Job Restarts

Listeners run per `JobExecution`. If the first `JobInstance` fails and is restarted, the listener should receive two distinct executions:

```text
JobInstance: importOrders / businessDate=2026-11-15
  |
  +--> JobExecution #1: FAILED
  |       beforeJob(#1)
  |       afterJob(#1)
  |
  +--> JobExecution #2: COMPLETED
          beforeJob(#2)
          afterJob(#2)
```

A restart integration test can follow these steps:

1. Launch the Job the first time with fixed identifying `JobParameters` and test setup causing a Step to fail.
2. Verify the first `JobExecution` has status `FAILED` and the listener recorded an audit for that execution ID.
3. Change the test condition so the Step can complete, such as clearing the failure flag or fixing input data.
4. Relaunch the same Job with the exact same identifying `JobParameters`.
5. Verify the second `JobExecution` belongs to the same `JobInstance` with a different ID, has status `COMPLETED`, and the listener wrote a separate audit.

Do not add a new identifying UUID between the two launches when testing restart. Changing identifying parameters causes Spring Batch to create a new `JobInstance`, so the test no longer verifies restarting the same instance.

If a Step already completed on the first run, that Step is normally skipped on restart unless `allowStartIfComplete(true)` is configured. Tests should reflect the Job's and reader/writer's actual restart policy rather than assuming every Step runs from the beginning again.

## 12. Testing Errors Originating Inside a Listener

A listener is part of the Job lifecycle, so errors in `beforeJob()` or `afterJob()` can affect execution or outcome recording. Decide the desired behavior and test it.

For example, if saving the start audit fails in `beforeJob()`, the application might want to stop the Job because running without an audit is prohibited. Conversely, if sending a notification fails in `afterJob()` and notifications are not a Job business precondition, you might log the error and enqueue the notification for separate retry.

Tests should cover:

- `recordStarted()` throws an exception: confirm whether the Job is prevented from running per policy.
- `recordOutcome()` throws an exception: confirm how the application records the callback failure and Job status.
- Notification service timeout: confirm notification errors do not cause duplicate sends or lost audits.
- Callback retry: confirm audit/notification operations have proper idempotency keys.

Do not catch and ignore every exception in a listener. If an audit error is mandatory, let the system surface the failure clearly. If the failure only affects a secondary notification channel, decouple it from business processing status and retry independently.

## 13. Listeners and Asynchronous JobLauncher

With a synchronous launcher, `launchJob()` typically returns after the Job completes, so tests can assert final status immediately after the call.

With an asynchronous launcher, the launch method may return while the Job is still `STARTING` or `STARTED`. In that case, do not assert `afterJob()` has run merely because `run()` returned. Integration tests must wait with a bounded synchronization mechanism or poll `JobExecution` via `JobExplorer`/repository until a terminal status is reached.

Listeners are commonly singleton beans and can be invoked concurrently for multiple `JobExecution` instances. Do not use mutable fields such as `currentStatus`, `currentJobName`, or `startedAt` to store per-run state. Every piece of tested data must be tied to the execution ID or reside inside the corresponding `JobExecution`.

## 14. Common Testing Mistakes

| Mistake | Cause | How to Fix |
|---|---|---|
| Testing only `COMPLETED` status | Misses bugs in how the listener handles `FAILED` or `STOPPED`. | Use dedicated tests or parameterized tests across terminal statuses. |
| Asserting only `BatchStatus` | Ignores business outcome codes in `ExitStatus`. | Assert both `getStatus()` and `getExitStatus().getExitCode()`. |
| Not checking failure exceptions | Audits may store `FAILED` while dropping root-cause info. | Add exceptions to `JobExecution` and verify messages are forwarded. |
| Using mock `JobExecution` alone to conclude Spring invokes the callback | Unit tests verify listener logic, not registration or lifecycle wiring. | Add integration tests with `JobLauncherTestUtils`. |
| Changing identifying parameters in a restart test | Creates a new `JobInstance` instead of restarting the old instance. | Keep identifying `JobParameters` identical across both launches. |
| Using a listener field to hold state between callbacks | Concurrent executions can overwrite data. | Use `JobExecution` ID and corresponding metadata. |
| Testing async launch and asserting immediately | The Job may not have finished and `afterJob` has not run yet. | Wait for execution to reach a terminal status with a timeout. |
| Sending real emails in unit tests | Makes tests network-dependent with external side effects. | Mock the notification service or test an outbox. |

## Conclusion

Testing listeners with execution status should cover both `beforeJob()` and `afterJob()`, statuses `COMPLETED`, `FAILED`, and `STOPPED`, as well as corresponding `ExitStatus` codes. Unit tests can construct mock `JobExecution` instances and use Mockito to confirm audit or notification services receive the right data. Integration tests with `spring-batch-test` and `JobLauncherTestUtils` verify Spring Batch actually invokes the listener within the Job lifecycle, while also testing restarts and callback order. Tie every assertion to an execution ID, handle listener errors explicitly, and never assume a Job has finished just because an asynchronous launcher returned.
