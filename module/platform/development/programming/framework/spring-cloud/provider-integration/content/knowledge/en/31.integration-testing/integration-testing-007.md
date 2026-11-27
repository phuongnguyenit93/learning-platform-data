# Waiting on Asynchronous Conditions and Deterministic Timeout Testing

## 1. Context and Objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, we practice integrating Spring Boot with managed services across **AWS, Azure, and Google Cloud** via Spring Cloud libraries and their corresponding client libraries. Flows such as sending messages to SQS/Pub/Sub, processing files on workers, updating databases, receiving storage events, or running tasks with `@Async` often complete after the initial method has already returned.

In integration tests, a successful message publish API call does not mean the consumer has finished processing. An HTTP request returning `202 Accepted` does not prove a job has completed either. Tests must wait on an **observable condition** with a clear deadline, while failing fast if the workflow enters an unrecoverable error state.

`Thread.sleep()` is frequently used to wait, yet fixed wait times do not prove a condition occurred. Waiting too briefly makes tests flaky; waiting too long slows the entire suite. **Awaitility** provides time-bounded polling; JUnit provides test timeouts; `CompletableFuture`, Reactor, and controllable clocks/schedulers help test asynchronous logic deterministically.

After this lesson, you will be able to:

- Distinguish test timeouts, service call timeouts, business deadlines, and ack/visibility timeouts.
- Use Awaitility to wait on database state, message consumers, and asynchronous jobs.
- Choose `atMost`, `pollInterval`, `pollDelay`, `untilAsserted`, `during`, and fail-fast conditions appropriately.
- Test `@Async`, `CompletableFuture`, SQS listeners, and Pub/Sub subscribers.
- Design retries/backoff within an overall deadline.
- Use clocks and virtual schedulers to avoid wall-clock dependencies in unit tests.
- Prevent race conditions, duplicate delivery issues, uncommitted test transactions, and resource leaks.
- Write stable tests under parallel execution or variable CI load.

## 2. Why Does `Thread.sleep()` Make Tests Unstable?

Suppose a test sends a message and waits for a worker to update status:

~~~java
publisher.publish(event);
Thread.sleep(2_000);
assertEquals(JobStatus.COMPLETED, repository.findStatus(event.jobId()).orElse(null));
~~~

This snippet has three problems:

1. If the worker finishes in 100 ms, the test wastes nearly 1.9 seconds.
2. If CI is under heavy load and the worker takes 2.1 seconds, the test fails even though the application works properly.
3. If the worker fails before updating the database, the test still waits the full two seconds before noticing.

A well-written test expresses the expected condition—for example, "the job reaches status COMPLETED within at most 5 seconds." The framework checks the condition repeatedly until it succeeds or the deadline expires.

Not every wait can be replaced with polling. When testing pure time-based logic such as token expiration, retry schedules, or contract expiration dates, control the clock/scheduler instead of waiting on the real wall clock.

## 3. Distinguishing Timeout Types

From test timeouts to message broker timeouts, each limit serves a distinct purpose:

| Type | Meaning | Example |
|---|---|---|
| Test timeout | Total time limit allowed for one test to run | JUnit `@Timeout`, `assertTimeout` |
| Condition timeout | Maximum time to wait for a state to appear | Awaitility `atMost(5s)` |
| Poll interval | Delay between consecutive condition checks | 100 ms |
| Client/request timeout | Maximum time for a single HTTP, gRPC, or SDK call | AWS SDK API call timeout |
| Future wait timeout | Time a test waits for a `Future` result | `future.get(3, SECONDS)` |
| Business deadline | Latest point by which the business operation must finish | Preview ready within 2 minutes |
| SQS visibility timeout | Duration a message in flight is hidden from redelivery | 30 seconds |
| Pub/Sub ack deadline | Time the broker waits for acknowledgment before redelivery | 10 seconds, extendable by the client |
| Retry budget | Total time allocated for attempts and backoff | 3 attempts within 5 seconds |

Do not reuse one timeout value across every layer. The condition timeout must be large enough to cover publishing, queue delivery, processing, and persistence. The outer test timeout must exceed the condition timeout plus setup/cleanup.

You can add `@Timeout` at the JUnit test level as a final safety net. That timeout does not replace per-request deadlines or Awaitility conditions; it only bounds total test runtime.

## 4. Designing the Total Deadline

A workflow may involve multiple service calls, retries, and backoffs. Estimate the total duration before picking timeouts:

\[
T_{workflow} \leq \sum_{i=1}^{n} T_{attempt_i} + \sum_{j=1}^{n-1} T_{backoff_j}
\]

Example:

- Each dependency call has an 800 ms timeout.
- Maximum of 3 attempts.
- Backoff between attempts is 200 ms, then 400 ms.

\[
T_{workflow} \leq 3 \times 0.8 + 0.2 + 0.4 = 3.0\text{ seconds}
\]

If a test waits only 2 seconds, the test timeout may be shorter than the application's retry budget. If a test waits 30 seconds for a flow that should finish within 3 seconds, the test hides regressions and slows CI.

A practical rule of thumb:

- Each request timeout must fit within the remaining workflow budget.
- Total retry/backoff must fit within the business deadline.
- Awaitility timeout must cover the workflow while remaining short enough to catch regressions.
- The test timeout must add headroom for Spring context startup, containers, and cleanup.
- Ack deadlines/visibility timeouts must accommodate message processing duration; for long tasks, use lease extension or redesign.

These numbers are illustrative only. Choose deadlines based on real latencies, retry policies, and product requirements.

## 5. Choosing the Right Waiting Tool by Scenario

| Scenario | Suitable Tool | Reason |
|---|---|---|
| Waiting for a database update by a worker | Awaitility | Condition can be polled safely multiple times |
| Waiting for a `CompletableFuture` to finish | `get(timeout)` or Awaitility | Direct Future handle is available to wait on |
| Verifying a method completes within a limit | JUnit `assertTimeout` | Bounds execution time of a block of code |
| Testing a stream under virtual time | Reactor `StepVerifier.withVirtualTime` | Avoids waiting on real wall-clock time |
| Testing date/time-dependent business rules | Inject `Clock` | Sets deterministic test timestamps |
| Testing a task scheduler | Test-controllable scheduler | Triggers tasks deterministically from tests |
| Verifying a consumer received a message | Awaitility + durable state | Waits for the business side effect |
| Verifying a message was acknowledged | Ack callback/metric or appropriate broker observation | Database state alone does not prove acknowledgment |

Do not use Awaitility for precise latency measurement or throughput benchmarking. Polling adds overhead and only observes that a condition became true at a polling check.

## 6. Adding Awaitility to Your Project

Awaitility is a library dedicated to asynchronous testing. Maven example with Awaitility 4.3.1:

~~~xml
<dependency>
    <groupId>org.awaitility</groupId>
    <artifactId>awaitility</artifactId>
    <version>4.3.1</version>
    <scope>test</scope>
</dependency>
~~~

If your project manages versions through dependency management or a version catalog, declare the version in the shared location. Awaitility 4.x supports Java `Duration`, lambdas, and `untilAsserted`.

Common static imports:

~~~java
import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
~~~

By default, Awaitility waits up to 10 seconds and polls every 100 ms. In critical tests, declare timeouts and poll intervals explicitly rather than relying on global defaults.

## 7. Waiting on Database State with Awaitility

Example: a service accepts a preview creation request, and a worker updates job status in the database. The test does not need to guess how long the worker takes; it simply waits for the terminal state.

~~~java
import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class PreviewWorkflowIT {

    @Test
    void completesPreviewWithinDeadline() {
        UUID jobId = UUID.randomUUID();

        previewPublisher.publish(new PreviewRequested(jobId));

        await()
                .alias("preview job " + jobId + " completed")
                .pollDelay(Duration.ZERO)
                .pollInterval(Duration.ofMillis(100))
                .atMost(Duration.ofSeconds(5))
                .untilAsserted(() ->
                        assertEquals(
                                JobStatus.COMPLETED,
                                jobRepository.findStatus(jobId).orElse(null)));
    }
}
~~~

`untilAsserted` re-runs the assertion while it fails and exits immediately once it passes. `alias` makes failure messages clearer when a test has multiple wait points.

In this example, the repository is queried repeatedly, so the read method must be safe and side-effect free. Never call `publish`, `send`, `delete`, or mutate state inside the polling lambda because the lambda can execute multiple times.

Using a unique ID per test prevents accidentally reading state from another test or a previous run.

## 8. Polling, `atMost`, `pollDelay`, and `pollInterval`

A typical Awaitility configuration has four parts:

~~~java
await()
        .alias("document uploaded")
        .pollDelay(Duration.ZERO)
        .pollInterval(Duration.ofMillis(150))
        .atMost(Duration.ofSeconds(8))
        .until(() -> storageRepository.exists(objectKey));
~~~

- `atMost`: overall deadline for the condition.
- `pollDelay`: wait duration before the first check.
- `pollInterval`: interval between subsequent checks.
- `alias`: descriptive label for the wait condition.

Polling too aggressively puts unnecessary load on the database, broker, or API. If waiting on a queued event, 100–250 ms is usually a reasonable starting point; if state updates in batches every few seconds, poll less frequently.

The polling interval is not an SLA. A condition may finish right after a check, yet the test will only observe it on the next poll.

## 9. Waiting for Stable Conditions and Failing Fast

Sometimes a condition being true once is not enough. For example, a status might briefly become COMPLETED before another step overwrites it. Awaitility supports `during` to confirm a condition stays true for a period of time:

~~~java
await()
        .during(Duration.ofMillis(500))
        .atMost(Duration.ofSeconds(5))
        .until(() ->
                jobRepository.findStatus(jobId)
                        .filter(JobStatus.COMPLETED::equals)
                        .isPresent());
~~~

`during` is meant to verify that a state remains stable, not to enforce a minimum processing duration. Avoid using `atLeast` to force a workflow to be slow; that ties tests to machine speed and slows down the suite.

When unrecoverable states exist, fail fast instead of waiting out the full timeout:

~~~java
await()
        .atMost(Duration.ofSeconds(5))
        .failFast(
                "Preview job entered terminal failure",
                () -> jobRepository.findStatus(jobId)
                        .filter(JobStatus.FAILED::equals)
                        .isPresent())
        .until(() ->
                jobRepository.findStatus(jobId)
                        .filter(JobStatus.COMPLETED::equals)
                        .isPresent());
~~~

This example fails immediately if the job transitions to FAILED rather than waiting the full 5 seconds. Fail-fast conditions are valuable for terminal states like FAILED, CANCELLED, or REJECTED.

## 10. Handling Exceptions While Waiting

A condition may be temporarily unreadable:

- The record does not exist yet.
- A read replica has not caught up yet.
- An emulator resource is not ready yet.
- An endpoint returns a transient error during startup.

Prefer representing absent data via `Optional`, booleans, or explicit states. If you genuinely need to ignore an intermediate exception, ignore only the specific exception type:

~~~java
await()
        .ignoreException(TransientDataAccessResourceException.class)
        .atMost(Duration.ofSeconds(5))
        .until(() -> repository.isVisible(jobId));
~~~

Never call `ignoreExceptions()` broadly for all exceptions. If configured too broadly, invalid SQL, credential errors, or programming bugs can be masked as hard-to-diagnose timeouts.

By default, Awaitility can capture uncaught exceptions from other threads and propagate them to the waiting thread. This is helpful when a worker throws an exception outside the test thread. Do not disable this mechanism just to turn a failing test green; find and fix the underlying exception.

Awaitility does not automatically guarantee thread safety or memory visibility. Conditions should read from repositories, thread-safe collections, or properly synchronized variables. Never use an ordinary mutable field written by a worker and read by a test without a happens-before relationship or synchronization.

## 11. Testing Spring `@Async`

`@Async` dispatches method calls onto a `TaskExecutor`; the method returns immediately to the caller. Methods returning a value must use `Future` or `CompletableFuture`. `void` methods do not propagate exceptions back to the caller; an `AsyncUncaughtExceptionHandler` is required to handle those errors.

Enable annotation-driven async execution with `@EnableAsync` in Spring configuration. Executors can be named and selected via the `@Async` attribute.

Service example:

~~~java
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class PreviewDispatcher {
    private final PreviewWorker worker;

    public PreviewDispatcher(PreviewWorker worker) {
        this.worker = worker;
    }

    @Async("previewExecutor")
    public CompletableFuture<Void> dispatch(UUID jobId) {
        worker.generate(jobId);
        return CompletableFuture.completedFuture(null);
    }
}
~~~

The test invokes the Spring-injected bean so the call passes through the proxy:

~~~java
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class PreviewDispatcherIT {
    @Autowired
    PreviewDispatcher dispatcher;

    @Test
    void asyncMethodCompletesWithinDeadline() throws Exception {
        CompletableFuture<Void> result =
                dispatcher.dispatch(UUID.randomUUID());

        result.get(3, TimeUnit.SECONDS);
    }
}
~~~

If you need to verify that side effects were committed, wait on database state with Awaitility after the Future completes, or use the Future as a completion signal if the method's contract guarantees it completes only after side effects are persisted.

Common pitfalls:

- Calling an `@Async` method from another method on the same object (self-invocation), bypassing the proxy.
- Constructing the object with `new` in the test instead of injecting the Spring bean.
- Executor queue full or thread pool shut down.
- A `void` method throws an exception while the test waits on a flag that is never updated.

## 12. Waiting on `CompletableFuture` and Distinguishing Timeout from Cancellation

When you hold a Future directly, `get(timeout)` is a straightforward way to wait:

~~~java
CompletableFuture<UploadResult> future =
        storageService.uploadAsync(document);

UploadResult result = future.get(5, TimeUnit.SECONDS);
assertEquals(UploadStatus.STORED, result.status());
~~~

`get(timeout)` throws `TimeoutException` if the Future has not finished within the allotted time. It does not automatically stop the running task. If the test intends to cancel the work, call `cancel(true)` or the client's cancellation mechanism, and verify whether the underlying work actually stopped.

`CompletableFuture.orTimeout(...)` completes the Future exceptionally on timeout, but does not guarantee that external I/O or submitted tasks are cancelled. Do not confuse "Future timed out" with "the server stopped processing the request."

If the Future merely indicates that a publisher sent a message, wait separately for consumer state. Completion of a publish future usually proves only that the broker accepted the publish, not that subscribers have processed the message.

## 13. Testing SQS Flows with Spring Cloud AWS

An integration test can send a message via `SqsTemplate`, then wait for an `@SqsListener` to update business state:

~~~java
import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import io.awspring.cloud.sqs.operations.SqsTemplate;

@SpringBootTest
class PreviewQueueIT {
    @Autowired
    SqsTemplate sqsTemplate;

    @Autowired
    JobRepository jobRepository;

    @Test
    void waitsUntilListenerCompletesJob() {
        UUID jobId = UUID.randomUUID();
        jobRepository.createPending(jobId);

        sqsTemplate.send("preview-requests", new PreviewRequested(jobId));

        await()
                .alias("SQS preview job " + jobId)
                .pollInterval(Duration.ofMillis(150))
                .atMost(Duration.ofSeconds(10))
                .untilAsserted(() ->
                        assertEquals(
                                JobStatus.COMPLETED,
                                jobRepository.findStatus(jobId).orElse(null)));
    }
}
~~~

The listener should complete synchronous processing before the framework acknowledges the message under the configured acknowledgement mode:

~~~java
import io.awspring.cloud.sqs.annotation.SqsListener;
import org.springframework.stereotype.Component;

@Component
class PreviewRequestListener {
    private final PreviewProcessor processor;

    PreviewRequestListener(PreviewProcessor processor) {
        this.processor = processor;
    }

    @SqsListener("preview-requests")
    public void handle(PreviewRequested event) {
        processor.generateAndPersist(event.jobId());
    }
}
~~~

This example uses a queue name already created in the test environment. When running with LocalStack/Testcontainers, configure endpoints and resources before the Spring listener container starts.

Do not invoke an `@Async void` method and return immediately from the listener if acknowledgement depends on processing completion. Once the listener returns normally, the container may treat the message as processed and acknowledge it while background work is still running. If asynchronous processing is needed, use the listener/acknowledgement mechanisms supported by Spring Cloud AWS and acknowledge only after side effects are durable.

## 14. Testing Pub/Sub and Acknowledgment

With Spring Framework on Google Cloud, `PubSubTemplate.publish()` returns a future. You can wait for publish completion with a timeout:

~~~java
String messageId = pubSubTemplate
        .publish("preview-requests", new PreviewRequested(jobId))
        .get(5, TimeUnit.SECONDS);
~~~

Next, use Awaitility to wait for the consumer to update the database:

~~~java
await()
        .alias("Pub/Sub job " + jobId + " completed")
        .pollInterval(Duration.ofMillis(150))
        .atMost(Duration.ofSeconds(10))
        .untilAsserted(() ->
                assertEquals(
                        JobStatus.COMPLETED,
                        jobRepository.findStatus(jobId).orElse(null)));
~~~

These two steps verify two distinct facts:

- Publish future completed: the publisher received confirmation of message submission.
- Database shows status COMPLETED: the consumer performed the side effect the test cares about.

For subscribers, acknowledgment must occur after successful processing per contract. `PubSubTemplate` supports ack/nack; `PubSubInboundChannelAdapter` offers `AUTO`, `AUTO_ACK`, and `MANUAL` modes. Choose the mode matching your error handler. If an error handler swallows exceptions and completes normally, the adapter may treat the flow as successful and acknowledge the message.

## 15. Ack Deadline, Visibility Timeout, and Redelivery

Test timeouts do not replace broker timeouts:

| Broker | Mechanism | When Processing Exceeds Limit |
|---|---|---|
| Amazon SQS | Visibility timeout | Message may reappear and be received by another consumer |
| Google Cloud Pub/Sub | Ack deadline | Unacknowledged message may be redelivered; client may extend ack deadline |

With SQS, Spring Cloud AWS allows configuring visibility timeout or extending visibility while the listener processes. With Pub/Sub, subscriber clients can automatically extend ack deadlines; Spring Framework on Google Cloud provides `max-ack-extension-period` to cap extension duration.

Tests should verify:

- Messages are not acknowledged before the business transaction commits.
- Messages are redelivered when consumers fail according to policy.
- Consumers are idempotent when the same event is redelivered.
- Retry and DLQ behavior match the tested configuration.
- Jobs are not marked COMPLETED before results are persisted durably.

Do not pin tests to an exact redelivery timestamp if the broker uses polling, backoff, or internal scheduling. Wait on meaningful conditions such as `attemptCount >= 2`, status RETRYING, or the message appearing in the DLQ within a reasonable deadline.

## 16. Retries, Backoff, and Verifying Attempt Counts

Retries often use increasing delays and may add jitter. Therefore, tests should not assume the second attempt always happens exactly 200 ms after the first.

You can check via state or metrics:

~~~java
await()
        .alias("dependency retry observed")
        .pollInterval(Duration.ofMillis(100))
        .atMost(Duration.ofSeconds(5))
        .until(() -> retryRepository.countAttempts(jobId) >= 2);
~~~

For unit tests, inject a backoff/sleeper or scheduler abstraction so tests can trigger retries without waiting on real time. For integration tests, keep the real retry policy while setting an ample deadline and verifying the final outcome.

Never configure infinite retries in tests. Permanent errors must transition to FAILED/DLQ and be caught by a fail-fast condition in the test. With unbounded retries, tests can hang until the outer test timeout without showing where the workflow stalled.

## 17. Virtual Time, `Clock`, and Controllable Schedulers

### 17.1. Reactor Virtual Time

With Reactor, `StepVerifier.withVirtualTime` lets you test publishers with delays/intervals without waiting on the real clock:

~~~java
import java.time.Duration;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void emitsThreeTicksWithoutWaitingInRealTime() {
    StepVerifier.withVirtualTime(
                    () -> Flux.interval(Duration.ofSeconds(1)).take(3))
            .thenAwait(Duration.ofSeconds(3))
            .expectNext(0L, 1L, 2L)
            .verifyComplete();
}
~~~

Construct the publisher inside the supplier so Reactor installs the virtual scheduler before the publisher is created. Virtual time applies only to schedulers supported by Reactor; external HTTP clients or thread pools still use real time.

### 17.2. Injecting `Clock` for Time-Based Logic

Do not call `Instant.now()` directly in business logic if tests must verify expirations. Inject `Clock`:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.temporal.ChronoUnit;

public class DownloadTokenService {
    private final Clock clock;

    public DownloadTokenService(Clock clock) {
        this.clock = clock;
    }

    public Instant expiresAt() {
        return Instant.now(clock).plus(15, ChronoUnit.MINUTES);
    }
}
~~~

In unit tests, use `Clock.fixed` to fix a deterministic instant:

~~~java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-24T10:00:00Z"),
        ZoneOffset.UTC);
~~~

When time needs to advance, use an adjustable test `Clock` or a project-defined `TimeProvider` abstraction. `Clock.fixed` does not tick forward automatically; it always returns the same instant.

### 17.3. Controllable Schedulers

For `@Scheduled`, delayed retries, or periodic tasks, separate time calculation from execution mechanism. Inject `TaskScheduler` or an application-owned scheduler interface, then swap in a test implementation that triggers tasks manually. With Reactor, use `VirtualTimeScheduler`/`StepVerifier`.

Never try to use Awaitility to wait 24 hours for a scheduled job. Control the scheduler or clock to test scheduling logic, and use only a short smoke test to verify real wiring.

## 18. Race Conditions, Transactions, and Cleanup

An asynchronous test can fail even when application code is correct if test data has not committed or resources are cleaned up too early.

### 18.1. Uncommitted Transactions

Spring test transactions are typically bound to the test thread. Workers running on other threads cannot see uncommitted data. If a test publishes a message inside an uncommitted transaction, the consumer may read nonexistent data or the test may roll back before the worker finishes.

For asynchronous integration tests:

- Create required prerequisite data in a committed transaction before publishing.
- Do not assume the test's transaction covers consumer threads.
- Clean up data after the consumer finishes.
- If testing an outbox, verify outbox commit before waiting on the publisher relay.

### 18.2. Preemptive Timeouts and ThreadLocals

JUnit `assertTimeout` executes code on the same thread and fails if it exceeds the limit; it does not forcibly interrupt running code. `assertTimeoutPreemptively` executes code on a different thread and aborts on timeout. This can strip `ThreadLocal` context—especially Spring's transaction context. Database work on the spawned thread may commit independently even if the test thread's transaction rolls back.

Do not use `assertTimeoutPreemptively` around code relying on Spring transactions, security contexts, or other ThreadLocals unless you understand the consequences. Configure test-level timeouts with an appropriate thread mode and apply dedicated deadlines to async operations.

### 18.3. Cleanup

Clean up only after the workflow has completed or been cancelled cleanly:

- Stop listener containers before deleting queues/subscriptions.
- Wait for in-flight messages to complete or confirm they were redelivered.
- Delete test buckets/objects, topics/subscriptions, queues, and database records.
- Use UUIDs in resource names so parallel tests do not collide.
- Use `try/finally` or lifecycle callbacks so cleanup runs when assertions fail.
- Never leave `@Async` tasks running after the Spring context closes.

## 19. Diagnosing Timeouts and Stabilizing CI

When Awaitility times out, do not merely bump the timeout. Capture intermediate state to see where the workflow stalled.

Collect:

- Job ID/correlation ID and last observed status.
- Retry count and most recent error class.
- Message ID, queue/subscription, and publish timestamp.
- Consumer lag, queue age, and visibility/ack deadlines if available.
- Listener, worker, and dependency logs.
- Elapsed time and poll count.

Awaitility supports a condition evaluation listener to log intermediate values. Example:

~~~java
await()
        .conditionEvaluationListener(
                condition -> log.debug(
                        "Waiting for job {}: elapsed={}ms, remaining={}ms",
                        jobId,
                        condition.getElapsedTimeInMS(),
                        condition.getRemainingTimeInMS()))
        .atMost(Duration.ofSeconds(5))
        .until(() -> jobRepository.isCompleted(jobId));
~~~

Practices that keep CI stable:

1. Set explicit timeouts and poll intervals rather than relying on global defaults.
2. Poll a lightweight read query without producing extra messages or side effects.
3. Use unique resource IDs per test.
4. Avoid assuming completion order across concurrent consumers.
5. Bound concurrency if sharing an emulator/broker.
6. Use virtual time for pure timer and retry logic.
7. Wait on business state rather than fixed durations.
8. Archive logs and container output before cleanup when tests fail.

If a test times out intermittently, inspect poll history, CI load, consumer concurrency, database connection pools, and broker backlog before increasing deadlines.

## 20. Summary and Practice Exercises

Asynchronous tests must wait on **observable conditions** with finite deadlines. Awaitility fits waiting on database, job, or consumer state; `Future.get(timeout)` fits direct Future handles; JUnit timeouts bound overall test duration; Reactor virtual time and injected `Clock`/schedulers test time logic without waiting on real clocks.

Timeouts must be designed across every layer: request, retry, workflow, condition, test, and broker acknowledgment. For SQS/Pub/Sub, publish completion does not mean consumer completion; ack/visibility deadlines and redelivery must be tested explicitly. Crucially, acknowledge messages only after business side effects are durable.

### Exercise A — Waiting for Job Completion

Build an endpoint accepting preview requests and returning a job ID. Have an async worker update status in a database. Write an integration test that sends a request and uses Awaitility to wait for COMPLETED within 5 seconds. Fail fast if FAILED appears.

### Exercise B — Testing SQS

Send `PreviewRequested` via `SqsTemplate`, receive via `@SqsListener`, and wait on job status. Make the handler throw an exception to observe retry/redelivery. Verify the message is not acknowledged before the transaction commits.

### Exercise C — Testing Pub/Sub

Publish an event via `PubSubTemplate`, wait for the publish future to complete, and then wait for the subscriber to persist results. Experiment with `AUTO`, `AUTO_ACK`, and `MANUAL` ack modes; observe differences when handlers throw exceptions or error handlers swallow them.

### Exercise D — Bounded Retries

Create a mock dependency that fails twice and succeeds on the third attempt. Set per-attempt timeouts and backoff. Verify total duration stays within the deadline, attempt counts match, and no infinite retries occur.

### Exercise E — Virtual Time

Write a Reactor pipeline with `delayElements` or `retryWhen`. Use `StepVerifier.withVirtualTime` to verify event ordering and backoff without waiting on real time.

### Exercise F — Transactions and Race Conditions

Write a transactional test that publishes a message before commit and observe that the consumer cannot read uncommitted data. Fix the test to commit before publishing and clean up after the consumer completes.

### Self-Check Questions

1. **Why does `Thread.sleep()` make tests flaky?** Because it waits a fixed duration without checking the condition and depends on machine load.
2. **What does `atMost` express in Awaitility?** The maximum deadline for the condition to become true.
3. **Is `pollInterval` an SLA?** No; it only specifies how often the condition is checked.
4. **Why avoid side effects inside an Awaitility lambda?** The lambda can execute multiple times.
5. **When should you use `untilAsserted`?** When you want to re-run assertions until they pass or the deadline expires.
6. **What is `during` used for?** Verifying that a condition remains true continuously over a time window.
7. **Does `Future.get(timeout)` cancel the underlying task?** No; timing out the wait does not guarantee background work or I/O stopped.
8. **Does publish future completion prove the consumer processed the message?** No; check consumer side effects or signals separately.
9. **How do SQS visibility timeout and Pub/Sub ack deadline affect tests?** If a message is not acknowledged before the deadline, the broker may redeliver it.
10. **Why can `assertTimeoutPreemptively` be dangerous with Spring transactions?** Because code runs on a different thread and does not inherit the test thread's transaction ThreadLocal.
11. **When should virtual time be used?** When testing timers, delays, intervals, or retry logic managed by supported schedulers.
12. **How do you prevent race conditions between tests and consumers?** Use unique IDs, commit prerequisite data before publishing, wait on durable state, and clean up after processing finishes.

### Official References

- [Awaitility — Usage](https://github.com/awaitility/awaitility/wiki/Usage)
- [Awaitility — Changelog](https://github.com/awaitility/awaitility/blob/master/changelog.txt)
- [JUnit 5 — Assertions and timeouts](https://docs.junit.org/5.14.4/api/org.junit.jupiter.api/org/junit/jupiter/api/Assertions.html)
- [JUnit 5 — User Guide, timeout thread modes](https://docs.junit.org/5.14.0/user-guide/index.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Spring Cloud AWS — SQS sending, listeners and acknowledgements](https://docs.awspring.io/spring-cloud-aws/docs/4.1.1/reference/html/index.html)
- [Spring Framework on Google Cloud — Pub/Sub](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/pubsub.html)
- [Google Cloud — Pub/Sub subscriber acknowledgement deadlines](https://cloud.google.com/pubsub/docs/subscriber)
- [Project Reactor — Testing with StepVerifier and virtual time](https://projectreactor.io/docs/core/release/reference/testing.html)
