# Waiting for Completion Conditions Instead of Fixed Sleep Durations

## 1. Why does Thread.sleep make asynchronous tests flaky?

In the **Spring Boot - testing** module, **Async and Scheduling** group, an asynchronous call might finish in a few milliseconds on a developer machine yet run slower when CI is CPU-starved, starting up the JVM, or waiting on a database, broker, or thread pool. Tests must wait for the **completed business state**, not simply a guessed time duration.

Counter-example:

~~~java
// Anti-pattern illustrative code, DO NOT put in runnable tests.
jobService.submit("job-7", "hello");
Thread.sleep(1_000);
assertThat(jobStore.find("job-7").orElseThrow().status())
        .isEqualTo(JobStatus.SUCCEEDED);
~~~

With the code above:

- If the job completes in 5 ms, the test still **waits the full 1,000 ms**, needlessly slowing the suite.
- If the job takes 1,300 ms due to an overloaded CI runner, the assertion runs too early → **flaky failure**.
- If the worker throws an exception and fails to update status, the test only knows the status is wrong, making root-cause analysis hard.
- If a submitted task never ran because the executor was shut down or rejected it, increasing sleep will not fix it.
- If the business effect happens **after** a callback or database commit, a created `Future` does not prove the effect is visible yet.

The right way:

~~~java
await()
    .atMost(Duration.ofSeconds(5))
    .pollInterval(Duration.ofMillis(50))
    .untilAsserted(() ->
        assertThat(jobStore.find("job-7").orElseThrow().status())
            .isEqualTo(JobStatus.SUCCEEDED)
    );
~~~

`untilAsserted` re-checks the assertion repeatedly until it passes or reaches the **maximum deadline**. When the condition becomes true, the test continues immediately; it does **not** sleep for the full 5 seconds. `atMost` is a safety bound, not an expected delay.

This lesson covers Awaitility, `CompletableFuture.get(timeout)`, `CountDownLatch`/`Future`, testing `@Async` and `@Scheduled`, thread visibility, async errors, cross-thread transactions, cleanup, and parallel execution. Runnable examples are based on **Java 17, Spring Boot 3.5.16, JUnit Jupiter, AssertJ, and Awaitility 4.x**.

## 2. Distinguishing three questions: submitted, started, completed

An event/command passes through multiple states:

~~~text
Test thread
    |
    +-- submit(request)  ---> accepted / QUEUED
                                    |
                              executor thread
                                    |
                                RUNNING
                                    |
                       +------------+-----------+
                       |                        |
                    SUCCEEDED                 FAILED
                       |                        |
                 business state             error/cause
                 visible to test            visible to test
~~~

| Observation | What it proves | What it does NOT prove yet |
| --- | --- | --- |
| `submit` method returned | The sender-side call completed | Worker has started/finished |
| Kafka `send().get()` returned | Producer acknowledged per broker/acks config | Consumer processed the business effect |
| `Future.isDone()` | Computation attached to the Future ended (succeeded, failed, or cancelled) | DB/outbox/external effects committed, if outside the Future |
| `CompletableFuture.get(timeout)` succeeded | Future completed without throwing | Eventual projection in another service updated |
| Database marker `status=SUCCEEDED` | Business state is observable per query transaction/isolation | All external side effects outside DB finished |
| `CountDownLatch` reached 0 | Parties called `countDown()` per protocol | Any step occurring **after** the signal finished |
| `@Scheduled` tick count increased | Callback ran at least once | Task ran at exact millisecond schedule or all child jobs finished |

For reliable tests, pick the **signal matching the test case's contract**. For example, testing a payment consumer requires verifying the committed balance/ledger or idempotency marker; knowing a message was published is not enough.

A common invariant pattern:

~~~text
submit command
    -> await until authoritative business predicate is true
    -> assert final values / cardinality / side effects
    -> release/cleanup resources
~~~

## 3. When to use Awaitility, Future, latch, and virtual time?

| Tool | Best suited for | Characteristics |
| --- | --- | --- |
| Awaitility `await().untilAsserted(...)` | Polling an eventually consistent state: DB row, status API, in-memory concurrent store | Provides timeout/poll interval and assertion failure messages |
| Awaitility `until(...)` | Simple boolean/predicate safe to evaluate repeatedly | Condition must be **side-effect free** |
| `Future.get(timeout, unit)` | Waiting on **one task with a Future handle** for result/error | Preserves exception and deadline, no state polling needed |
| `CompletableFuture.allOf(...)` | Waiting on a set of futures known to the test | Completes when all futures finish; inspect individual results/errors |
| `CountDownLatch.await(timeout, unit)` | Synchronizing ordering between threads at exact points | Signal-driven, independent of CI speed |
| `CyclicBarrier` / `Phaser` | Forcing multiple workers to a contention point or multiple phases | Well suited for race/concurrency tests |
| Reactor `StepVerifier.withVirtualTime` | Publishers driven by Reactor schedulers | Controls **virtual scheduler**, not OS/DB clocks |
| Injected `Clock.fixed` / `Clock.offset` | Testing time-based business logic: TTL, deadlines | Does not make thread pools/schedulers run automatically |
| `MockRestServiceServer` / embedded broker probe | Testing respective client/network pipelines | Must observe **post-processing**, not just request dispatch |

Do not use one tool for every problem. If a `CompletableFuture` is returned from the exact boundary the test cares about, `get(timeout)` is the clearest solution. If completion lands in a database across multiple services, Awaitility observing the DB or API fits better. If you need to control the ordering of two threads to reproduce a race, a latch/barrier is more accurate than hoping a scheduler hits the desired timing.

## 4. Awaitility: explicit conditions and bounds

Awaitility is a Java DSL for asynchronous tests. Spring Boot 3.5's `spring-boot-starter-test` already includes Awaitility in test dependencies; you can also declare `testImplementation 'org.awaitility:awaitility'` directly with the version managed by Boot's BOM.

Core patterns:

~~~java
import static org.awaitility.Awaitility.await;
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

// Boolean predicate: returns true when value reaches 3.
await().atMost(Duration.ofSeconds(5))
       .until(() -> counter.get() >= 3);

// AssertJ re-evaluated until it passes.
await().atMost(Duration.ofSeconds(5))
       .pollInterval(Duration.ofMillis(50))
       .untilAsserted(() ->
           assertThat(repository.count()).isEqualTo(3)
       );
~~~

This is an **illustrative code snippet**; `counter`/`repository` must be created by the test. In the runnable example suite below, `JobStore` and `TickCounter` are the real dependencies.

### Meaning of each parameter

- `atMost(Duration.ofSeconds(5))`: maximum deadline for the condition, not a guarantee that the task always takes 5 seconds.
- `pollInterval(Duration.ofMillis(50))`: interval between observations; choose based on responsiveness and system load rather than blindly setting 1 ms.
- `pollDelay(Duration.ZERO)`: check immediately on the first poll if desired; by default Awaitility has a configurable initial poll delay.
- `untilAsserted(...)`: re-runs assertions; on timeout, reports which condition was not met.
- `until(predicate)`: the predicate should be **read-only and fast**, not consuming messages, deleting rows, or triggering business effects on every poll.

**If the assertion evaluates to true early, the test finishes early.** Do not call `Thread.sleep(...)` after `await()` since you already have the completion signal.

### Note on multi-state conditions

Do not just await `status != QUEUED` because `FAILED` also satisfies it. If the business rule requires success, await **`SUCCEEDED`** and check payload/amount/record count. If the terminal state is `FAILED`, you can configure fail-fast diagnostics instead of waiting out the deadline.

### Do not poll with side effects

Wrong:

~~~java
await().until(() -> queue.poll() != null);
~~~

`queue.poll()` **retrieves and removes the element** on every call, making the test itself consume data. Instead, inspect a thread-safe invariant count/marker, or receive the element once with `poll(timeout, unit)` and assert afterward. With Kafka/RabbitMQ, do not poll with a test helper that steals records meant for the app consumer.

## 5. Timeout is not a magic number

Every async test needs a **finite bound** so it does not hang CI, without needing to sleep for that full duration.

A reference configuration:

~~~java
await()
    .atMost(Duration.ofSeconds(8))
    .pollInterval(Duration.ofMillis(50))
    .untilAsserted(() ->
        assertThat(statusService.lookup(jobId)).isEqualTo("DONE")
    );
~~~

This is an illustrative snippet. 8 seconds is a **maximum threshold per test environment SLA**, not a promise that the job needs 8 seconds. The test can complete in a few milliseconds.

Choose timeouts based on:

1. Startup/coordination time of executors, brokers, and DB migrations.
2. Internal pipeline latency, retry/backoff, and async batching.
3. CI load and legitimate contention.
4. Total suite time budget.
5. Enough polling iterations for diagnostics.
6. Internal client bounds (HTTP, DB) and outer layer timeouts (JUnit/Gradle/CI).

**Do not cure a deadlock by increasing timeouts indefinitely.** If a condition consistently times out, inspect the root cause in workers/logs/stack traces, verify whether the task was actually submitted, whether the thread pool still has workers, and whether the DB/broker is available.

One pitfall: setting `pollInterval` larger than `atMost` can prevent even a single useful observation. Avoid aggressive polling against a shared database; choose a reasonable interval.

## 6. Runnable example suite: @Async + @Scheduled with explicit signals

The example application implements two flows:

- **Asynchronous:** `JobSubmissionService.submit` creates `QUEUED` in `JobStore`, then calls `AsyncJobWorker.process` annotated with `@Async("jobExecutor")` through a **different Spring bean**. The worker transitions the state to `SUCCEEDED` or `FAILED` and returns a `CompletableFuture` to the caller.
- **Scheduled:** `TickCounter.tick` is invoked by `@Scheduled(fixedDelayString=..., initialDelayString=...)`. In a dedicated integration test, delays are reduced via properties and awaited until the counter increments; no sleeping for a fixed clock interval.

File structure:

~~~text
settings.gradle
build.gradle
src/main/java/com/example/conditionwait/
    ConditionWaitApplication.java
    JobAsyncConfig.java
    JobStatus.java
    JobSnapshot.java
    JobStore.java
    JobHandle.java
    AsyncJobWorker.java
    JobSubmissionService.java
    TickCounter.java
src/main/resources/
    application.properties
src/test/java/com/example/conditionwait/
    AsyncJobIntegrationTest.java
    ScheduledTickIntegrationTest.java
    GateWithoutSleepTest.java
~~~

All Java files use package `com.example.conditionwait`. The example needs no web server, database, or Docker; there are no HTTP side effects blurring the meaning of completion.

## 7. Gradle and Spring Boot 3.5

**`settings.gradle`:**

~~~groovy
rootProject.name = 'condition-wait-tests'
~~~

**`build.gradle` (Groovy DSL):**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    // Can be declared explicitly even though starter-test already includes it.
    testImplementation 'org.awaitility:awaitility'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-test` provides JUnit Jupiter, AssertJ, and Awaitility; declaring `org.awaitility:awaitility` directly makes the dependency explicit and uses the compatible version managed by the Spring Boot 3.5 BOM. With Boot 3.5.16, the BOM manages Awaitility 4.2.2. Avoid copying APIs available only in Awaitility 4.3.x into the demo without updating the version.

Java 17 supports `record`, `CompletableFuture.failedFuture`, `Duration`, and `java.util.concurrent`. A pre-generated Gradle Wrapper (or an installed Gradle) is required; the script only declares dependencies and does not generate `gradlew`.

**`src/main/resources/application.properties`:**

~~~properties
# Normally do not run scheduler ticks continuously in the demo.
demo.tick.initial-delay-ms=600000
demo.tick.delay-ms=600000
~~~

These two properties may be overridden **in the dedicated scheduler test** so it does not depend on the default 10-minute wait. Do not alter production configuration globally for all tests.

## 8. Bootstrapping the application and configuring the thread pool

**`src/main/java/com/example/conditionwait/ConditionWaitApplication.java`:**

~~~java
package com.example.conditionwait;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableAsync
@EnableScheduling
public class ConditionWaitApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConditionWaitApplication.class, args);
    }
}
~~~

`@EnableAsync` activates `@Async` interception, while `@EnableScheduling` registers `@Scheduled` methods with the Spring scheduler. Declaring the annotations does not guarantee every Java method called via `this` gets proxy interception; see the self-invocation section.

**`src/main/java/com/example/conditionwait/JobAsyncConfig.java`:**

~~~java
package com.example.conditionwait;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class JobAsyncConfig {

    @Bean(name = "jobExecutor")
    ThreadPoolTaskExecutor jobExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("job-worker-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(5);
        executor.initialize();
        return executor;
    }
}
~~~

`@Async("jobExecutor")` selects **the exact executor named `jobExecutor`**, independent of Boot's default executor. The thread name prefix helps integration tests prove execution ran on a worker rather than the test thread; it is **not** a synchronization mechanism.

For production, sizing and rejection policy must reflect workload/concurrency/latency. A full queue can throw `TaskRejectedException` **at submission**, before the job even runs. A real system must record rejected jobs/metrics rather than merely awaiting until timeout.

## 9. State model: enum and immutable snapshot

**`src/main/java/com/example/conditionwait/JobStatus.java`:**

~~~java
package com.example.conditionwait;

public enum JobStatus {
    QUEUED,
    SUCCEEDED,
    FAILED
}
~~~

**`src/main/java/com/example/conditionwait/JobSnapshot.java`:**

~~~java
package com.example.conditionwait;

public record JobSnapshot(
        String id,
        JobStatus status,
        String result,
        String workerThread,
        String error
) {
}
~~~

Using an immutable `record` ensures every read sees **a consistent snapshot** of status/result/error. With multiple separate `volatile` fields, a test could observe `status=SUCCEEDED` while `result` is still stale due to unsynchronized updates across fields; replacing an immutable object atomically in a map is cleaner.

`FAILED` is a distinct terminal state. Do not treat "no longer `QUEUED`" as "succeeded".

## 10. Thread-safe JobStore for integration tests

**`src/main/java/com/example/conditionwait/JobStore.java`:**

~~~java
package com.example.conditionwait;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Component;

@Component
public class JobStore {

    private final Map<String, JobSnapshot> jobs =
            new ConcurrentHashMap<>();

    public void queued(String id) {
        JobSnapshot initial = new JobSnapshot(
                id, JobStatus.QUEUED, null, null, null
        );

        if (jobs.putIfAbsent(id, initial) != null) {
            throw new IllegalArgumentException(
                    "Duplicate job id: " + id
            );
        }
    }

    public void succeeded(
            String id,
            String result,
            String workerThread
    ) {
        replace(
                id,
                new JobSnapshot(
                        id, JobStatus.SUCCEEDED,
                        result, workerThread, null
                )
        );
    }

    public void failed(
            String id,
            String error,
            String workerThread
    ) {
        replace(
                id,
                new JobSnapshot(
                        id, JobStatus.FAILED,
                        null, workerThread, error
                )
        );
    }

    private void replace(String id, JobSnapshot snapshot) {
        jobs.compute(id, (key, old) -> {
            if (old == null) {
                throw new IllegalStateException(
                        "Unknown job: " + id
                );
            }
            return snapshot;
        });
    }

    public Optional<JobSnapshot> find(String id) {
        return Optional.ofNullable(jobs.get(id));
    }

    public void remove(String id) {
        jobs.remove(id);
    }
}
~~~

`ConcurrentHashMap` supports concurrent access from test and worker threads. `putIfAbsent` prevents duplicate IDs within a single JVM; `compute` replaces the snapshot atomically. That allows polling to observe transitions without coarse locking or sleep.

**Limitation:** This is a test/demo in-memory store, offering no durability or consistency across multiple JVMs/pods. In production, use a database/queue and verify actual commits/acks; do not assume a `ConcurrentHashMap` handles distributed idempotency.

### Why not use a regular HashMap?

`HashMap` is not thread-safe under concurrent reads/writes; under CI it can expose stale state or hard-to-reproduce concurrency errors. Likewise, a boolean field read across threads needs `volatile`, `AtomicBoolean`, or proper synchronization. Do not "fix" visibility bugs by sleeping longer.

## 11. CompletableFuture handle for a job

**`src/main/java/com/example/conditionwait/JobHandle.java`:**

~~~java
package com.example.conditionwait;

import java.util.concurrent.CompletableFuture;

public record JobHandle(
        String id,
        CompletableFuture<Void> completion
) {
}
~~~

The handle bundles the job ID and completion future. This is an **in-JVM-only** illustrative model; do not serialize `CompletableFuture` into JSON. For a REST API receiving asynchronous commands, the response usually contains a job ID/status URL; clients poll state through a separate API instead of passing a `Future` over the network.

`Future` only indicates completion of the work attached to it. If the worker fires and forgets another task, the initial worker's `Future` may complete before the child task's side effects; link futures or await the proper business state.

## 12. Real @Async worker reporting both success and error

**`src/main/java/com/example/conditionwait/AsyncJobWorker.java`:**

~~~java
package com.example.conditionwait;

import java.util.Locale;
import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncJobWorker {

    private final JobStore store;

    public AsyncJobWorker(JobStore store) {
        this.store = store;
    }

    @Async("jobExecutor")
    public CompletableFuture<Void> process(
            String id,
            String input
    ) {
        String thread = Thread.currentThread().getName();

        try {
            // Intentionally allow a controlled failing test case.
            if ("FAIL".equals(input)) {
                throw new IllegalStateException(
                        "simulated worker failure"
                );
            }

            store.succeeded(
                    id,
                    input.toUpperCase(Locale.ROOT),
                    thread
            );
            return CompletableFuture.completedFuture(null);
        } catch (RuntimeException failure) {
            store.failed(
                    id,
                    failure.getMessage(),
                    thread
            );
            return CompletableFuture.failedFuture(failure);
        }
    }
}
~~~

With Spring proxy-based async, calls to the `AsyncJobWorker` bean through the Spring proxy are submitted to the executor. The body of `process` runs on the configured `job-worker-...` thread. The method returns `CompletableFuture.completedFuture(null)` on the worker so Spring completes the caller's future; on the error branch it uses `failedFuture` so the error **does not vanish**.

Key distinctions:

- `store.succeeded(...)` marks the business state complete (in this demo).
- `completion` indicates the worker method finished.
- Any downstream callback running afterward must be awaited separately if part of the contract.
- With `@Async void`, exceptions do not appear in a caller `Future`; appropriate `AsyncUncaughtExceptionHandler`/observability is needed. Thus when testing results/errors, prefer `Future`/`CompletableFuture`.

In production with a DB, `store.succeeded` must be replaced by a transaction commit or meaningful business DB status. Do not mark `SUCCEEDED` **before** critical side effects actually finish.

## 13. Submission service calling another bean

**`src/main/java/com/example/conditionwait/JobSubmissionService.java`:**

~~~java
package com.example.conditionwait;

import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class JobSubmissionService {

    private final JobStore store;
    private final AsyncJobWorker worker;

    public JobSubmissionService(
            JobStore store,
            AsyncJobWorker worker
    ) {
        this.store = store;
        this.worker = worker;
    }

    public JobHandle submit(String id, String input) {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(input, "input");

        store.queued(id);
        return new JobHandle(
                id,
                worker.process(id, input)
        );
    }
}
~~~

`JobSubmissionService` and `AsyncJobWorker` are **two separate Spring beans**. When `submit` calls `worker.process`, the call crosses `AsyncJobWorker`'s proxy, activating `@Async`.

Self-invocation counter-example:

~~~java
@Service
class IncorrectWorker {
    public void submit() {
        doWorkAsync(); // this.doWorkAsync(): bypasses proxy!
    }

    @Async
    public void doWorkAsync() {
        // May execute synchronously on the calling thread.
    }
}
~~~

This is an **error-illustrating skeleton**. In Spring's default proxy mode, `@Async` on an internal call within the same instance is not applied. A test checking only "the final result is correct" might still PASS because the task ran synchronously! Therefore, the main test asserts the **worker thread name** and distinguishes it from the caller thread.

**A limitation of the demo code:** if the executor rejects immediately during `submit`, the newly created `QUEUED` marker could remain. When building production code, catch `TaskRejectedException` around scheduling, update the status to `FAILED`/`REJECTED` or use transactional enqueueing, and return an appropriate error. Do not leave jobs silently stuck in `QUEUED` forever.

## 14. @Scheduled task with an observable counter

**`src/main/java/com/example/conditionwait/TickCounter.java`:**

~~~java
package com.example.conditionwait;

import java.util.concurrent.atomic.AtomicLong;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class TickCounter {

    private final AtomicLong ticks = new AtomicLong();

    @Scheduled(
            fixedDelayString = "${demo.tick.delay-ms:600000}",
            initialDelayString = "${demo.tick.initial-delay-ms:600000}"
    )
    public void tick() {
        ticks.incrementAndGet();
    }

    public long count() {
        return ticks.get();
    }
}
~~~

According to Spring Framework, `fixedDelay` measures from **when the previous execution completes** to the next start; `fixedRate` measures from the planned start times on a cadence, while `cron` evaluates calendar schedules with a timezone. Both operate in **real scheduler time**, not accelerated by `Clock.offset`.

Under default configuration, the first tick is scheduled only after 600,000 ms (10 minutes). The dedicated scheduler test overrides these values:

~~~properties
demo.tick.initial-delay-ms=0
demo.tick.delay-ms=120
~~~

The first tick may have already executed **before the JUnit test method starts** because the Spring context starts up first. The test does not assert `count()==1` after 120 ms; instead it captures the **current counter baseline** and awaits `count() > baseline`. There is no exact millisecond guarantee per tick when thread pools and CPU scheduling vary.

**This lesson does not use clock virtualization for `@Scheduled`**, because Java `Clock` injection does not automatically replace the Spring `TaskScheduler`'s clock. If you need to test logic running at a specific point in time, separate the logic from the trigger and test with a fake `Clock`; use a small scheduler integration test to prove real binding.

## 15. @Async integration test with Awaitility

**`src/test/java/com/example/conditionwait/AsyncJobIntegrationTest.java`:**

~~~java
package com.example.conditionwait;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.awaitility.Awaitility.await;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class AsyncJobIntegrationTest {

    @Autowired
    JobSubmissionService submissions;

    @Autowired
    JobStore store;

    private final List<JobHandle> created = new ArrayList<>();

    private JobHandle newJob(String payload) {
        String id = "test-" + UUID.randomUUID();
        JobHandle handle = submissions.submit(id, payload);
        created.add(handle);
        return handle;
    }

    private JobSnapshot awaitStatus(
            String id,
            JobStatus expected
    ) {
        await()
                .atMost(Duration.ofSeconds(5))
                .pollInterval(Duration.ofMillis(50))
                .untilAsserted(() -> {
                    JobSnapshot snapshot =
                            store.find(id).orElseThrow();
                    assertThat(snapshot.status()).isEqualTo(expected);
                });
        return store.find(id).orElseThrow();
    }

    @AfterEach
    void finishJobsThenCleanOwnIds() throws Exception {
        try {
            for (JobHandle handle : created) {
                try {
                    // Wait for the worker to finish before removing the store entry.
                    handle.completion().get(5, TimeUnit.SECONDS);
                } catch (ExecutionException completedWithFailure) {
                    // One test case intentionally simulates a worker failure.
                    // That test case must assert the error separately.
                }
            }
        } finally {
            created.forEach(h -> store.remove(h.id()));
        }
    }

    @Test
    void eventuallySucceedsWithoutSleeping() throws Exception {
        String callerThread = Thread.currentThread().getName();
        JobHandle handle = newJob("hello");

        JobSnapshot result = awaitStatus(
                handle.id(), JobStatus.SUCCEEDED
        );

        assertThat(result.result()).isEqualTo("HELLO");
        assertThat(result.workerThread())
                .startsWith("job-worker-")
                .isNotEqualTo(callerThread);

        handle.completion().get(5, TimeUnit.SECONDS);
    }

    @Test
    void eventuallyFailsAndFutureExposesCause() {
        JobHandle handle = newJob("FAIL");

        JobSnapshot result = awaitStatus(
                handle.id(), JobStatus.FAILED
        );

        assertThat(result.error())
                .isEqualTo("simulated worker failure");
        assertThat(result.result()).isNull();

        assertThatThrownBy(
                () -> handle.completion().get(
                        5, TimeUnit.SECONDS
                )
        ).isInstanceOf(ExecutionException.class)
         .hasCauseInstanceOf(IllegalStateException.class);
    }

    @Test
    void twoIndependentJobsBothReachBusinessCompletion()
            throws Exception {
        JobHandle first = newJob("alpha");
        JobHandle second = newJob("beta");

        await().atMost(Duration.ofSeconds(5))
                .pollInterval(Duration.ofMillis(50))
                .untilAsserted(() -> {
                    assertThat(
                            store.find(first.id()).orElseThrow()
                                    .result()
                    ).isEqualTo("ALPHA");
                    assertThat(
                            store.find(second.id()).orElseThrow()
                                    .result()
                    ).isEqualTo("BETA");
                });

        CompletableFuture.allOf(
                first.completion(),
                second.completion()
        ).get(5, TimeUnit.SECONDS);

        assertThat(
                store.find(first.id()).orElseThrow().status()
        ).isEqualTo(JobStatus.SUCCEEDED);

        assertThat(
                store.find(second.id()).orElseThrow().status()
        ).isEqualTo(JobStatus.SUCCEEDED);
    }

    @Test
    void duplicateJobIdIsRejectedInsteadOfOverwritingState()
            throws Exception {
        JobHandle existing = newJob("first");

        assertThatThrownBy(
                () -> submissions.submit(existing.id(), "second")
        ).isInstanceOf(IllegalArgumentException.class)
         .hasMessageContaining("Duplicate job id");

        existing.completion().get(5, TimeUnit.SECONDS);
        assertThat(
                awaitStatus(existing.id(), JobStatus.SUCCEEDED)
                        .result()
        ).isEqualTo("FIRST");
    }
}
~~~

**Four integration tests** prove:

1. The job actually runs via the Spring async proxy, updates business state, and the thread name starts with `job-worker-`.
2. The error path is not swallowed; both the `FAILED` snapshot and the exception via `Future.get(timeout)` are present.
3. Two jobs with distinct IDs both reach completion; `allOf` proves both futures finished.
4. Submitting a duplicate ID is rejected without overwriting the original job's state.

No `Thread.sleep(...)`. Tasks may complete even before the first poll — the test still PASSES. The timeout is a **bound**, not a forced wait duration.

`@AfterEach` awaits the futures of the current method, then cleans up the keys created by that method, preventing a worker from updating the map **after the test cleared state**. For the intentional worker failure, `ExecutionException` is accepted during cleanup, while `eventuallyFailsAndFutureExposesCause` itself verifies the cause. For production background tasks that may not return a `Future`, provide an equivalent cancellation/join or lifecycle ownership mechanism.

### What must NOT be inferred from the demo

`ConcurrentHashMap` is an in-JVM source of truth, not a database or distributed state. `@Async` across executor threads does not by default carry transactions, `SecurityContext`, or every caller `ThreadLocal`; production requires appropriate context propagation and tests. This test only proves timing/lifecycle within the configured Spring context.

## 16. @Scheduled integration test: waiting for new ticks instead of sleeping

**`src/test/java/com/example/conditionwait/ScheduledTickIntegrationTest.java`:**

~~~java
package com.example.conditionwait;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = {
                "demo.tick.initial-delay-ms=0",
                "demo.tick.delay-ms=120"
        }
)
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS
)
class ScheduledTickIntegrationTest {

    @Autowired
    TickCounter ticks;

    @Test
    void schedulerEventuallyRunsAtLeastOnceAfterObservation() {
        long before = ticks.count();

        await()
                .atMost(Duration.ofSeconds(5))
                .pollInterval(Duration.ofMillis(40))
                .untilAsserted(() ->
                        assertThat(ticks.count()).isGreaterThan(before)
                );
    }

    @Test
    void schedulerCanProduceTwoAdditionalTicks() {
        long before = ticks.count();

        await()
                .atMost(Duration.ofSeconds(5))
                .pollInterval(Duration.ofMillis(40))
                .untilAsserted(() ->
                        assertThat(ticks.count())
                                .isGreaterThanOrEqualTo(before + 2)
                );
    }
}
~~~

The **two tests** above do not call `ticks.tick()` directly (calling directly would not prove Spring's scheduler scheduled it). They observe the real `AtomicLong` counter and only wait for it to **increase relative to a baseline**.

Using `@DirtiesContext(AFTER_CLASS)` closes the context with the short scheduler interval after the class completes, preventing a test-specific context from continuing to emit ticks while other tests share an environment. This lifecycle measure incurs context startup cost; in a real suite, organize scheduler test groups thoughtfully rather than overusing it on every test.

### Why not assert "after 120 ms count must equal 1"?

- The first callback may run before the test method begins.
- CPU scheduling and GC do not guarantee exact execution instants.
- `fixedDelay` measures the wait after **the previous execution finishes**.
- If context startup took longer, the counter could exceed 1.
- Parallel test suite execution can start the test method at a different point in time.

For testing cron rules like "exact date/time", isolate the calculation/trigger policy with `Clock.fixed` and `ZoneId`, then keep a small integration test verifying the scheduler registered the callback. Awaitility does not make calendar time advance faster.

## 17. CountDownLatch: exact event synchronization without sleep

When testing a race or an execution path that must pause at a specific point, `CountDownLatch` is better than Awaitility polling. We have the worker **explicitly signal it has started**, then wait for the test thread to open the gate.

**`src/test/java/com/example/conditionwait/GateWithoutSleepTest.java`:**

~~~java
package com.example.conditionwait;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class GateWithoutSleepTest {

    @Test
    void testControlsWorkerInterleavingWithoutSleep()
            throws Exception {
        ExecutorService executor =
                Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean completed = new AtomicBoolean(false);

        try {
            Future<?> task = executor.submit(() -> {
                started.countDown();

                try {
                    if (!release.await(3, TimeUnit.SECONDS)) {
                        throw new AssertionError(
                                "Worker gate not released"
                        );
                    }
                    completed.set(true);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(ex);
                }
            });

            // Wait for the signal that the worker reached the gate.
            assertThat(
                    started.await(3, TimeUnit.SECONDS)
            ).isTrue();

            // At this point the test has NOT opened the gate yet.
            assertThat(completed.get()).isFalse();

            release.countDown();
            task.get(3, TimeUnit.SECONDS);

            assertThat(completed.get()).isTrue();
        } finally {
            // Do not let a failing test leave the worker stuck.
            release.countDown();
            executor.shutdownNow();
            assertThat(
                    executor.awaitTermination(3, TimeUnit.SECONDS)
            ).isTrue();
        }
    }

    @Test
    void futureCanCompleteFromAnExplicitTestSignal()
            throws Exception {
        CompletableFuture<String> input =
                new CompletableFuture<>();

        CompletableFuture<String> transformed =
                input.thenApply(String::toUpperCase);

        assertThat(transformed.isDone()).isFalse();

        // This is a signal, not waiting a number of milliseconds.
        input.complete("ready");

        assertThat(
                transformed.get(2, TimeUnit.SECONDS)
        ).isEqualTo("READY");
    }
}
~~~

There are **two unit tests** that do not start Spring. The first makes the protocol clear:

~~~text
Worker: countDown(started) ---- await(release) ---- completed=true
Test:    await(started) ------- assert false --- countDown(release)
                                              \--- Future.get(timeout)
~~~

No `Thread.sleep` or guessing OS execution order. If the worker fails to reach the gate or finish within the deadline, the test FAILS with a clear timeout.

### Two important caveats

- `CountDownLatch` is **one-shot**: the count cannot be reset above 0 once it reaches 0. For multiple phases or reusable barriers, consider `CyclicBarrier` or `Phaser`.
- Place `countDown()` at the **exact point of business completion**. If placed before a database commit, the latch only proves the worker passed that signal line, not the commit. A misplaced signal creates a false positive just like a bad sleep.

## 18. How does a completion signal differ from Future completion?

A `CompletableFuture` is often very helpful:

~~~java
CompletableFuture<Void> first = sendAsyncCommandA();
CompletableFuture<Void> second = sendAsyncCommandB();

CompletableFuture.allOf(first, second)
        .get(5, TimeUnit.SECONDS);
~~~

This is an illustrative snippet with two hypothetical functions, not a standalone Java file. It proves **the two futures finished**, not that a downstream consumer in another process has finished processing or that the database committed.

With Spring services:

- If `@Async CompletableFuture<T>` directly processes and commits the business change inside the method, Future completion is a strong signal.
- If `@Async` only enqueues a message and returns, the Future completes **before** the consumer runs.
- If HTTP `202 Accepted` is returned after queuing a job, you must await the job status resource.
- If the code fires and forgets another `void` task, the earlier step's Future does not include that task.
- If Kafka `KafkaTemplate.send` completes, wait for the **consumer-side observable effect** when testing the consumer, rather than stopping at the producer ack.

**Choose the boundary according to your goal.** An "HTTP accepted" test only needs `202`/Location; an "order paid" test must check ledger/payment state, not just acceptance.

### Future timeout and cancel

`future.get(5, TimeUnit.SECONDS)` throws `TimeoutException` if waiting too long; the Future is not automatically cancelled just because of a timeout. When a test owns a private executor, it can call `cancel(true)` or shut down in `finally`. For a Spring-managed executor, do not shut down the shared bean inside a test method; let the Spring context manage lifecycle while the test cleans up its own tasks.

If a task relies on networking, set timeouts **on the HTTP client** as well as the test deadline; a test timeout alone does not abort an indefinitely blocked socket call.

## 19. @Async self-invocation: tests can pass yet actually run synchronously

Spring Framework handles `@Async` via proxies by default. If a synchronous method in the same object calls an `@Async` method:

~~~java
@Service
class WrongService {
    public void submit() {
        doAsync(); // Calls this directly, bypassing the proxy.
    }

    @Async
    public void doAsync() {
        // Usually does not run on the async executor as intended.
    }
}
~~~

This is a **counter-example** requiring imports, not a class from the runnable sample. A test that only checks the final outcome can still PASS because `doAsync()` executes immediately on the calling thread. Split out a separate service bean or call through the valid proxy. In the demo, `JobSubmissionService` injects a separate `AsyncJobWorker`, and the test asserts the `job-worker-` thread name.

**Do not use `Thread.sleep` to "prove async".** A synchronous program can sleep too. Tests need to check execution context, completion sequencing, latency contracts, or states/signals per real requirements.

### @EnableAsync and executor

Simply annotating `@Async` without enabling async support or going through a proxy can prevent the method from running as expected. In Boot, the default executor depends on beans/properties, versions, and configuration; using `@Async("jobExecutor")` in the example establishes a clear owner and naming. If the environment uses Java 21 virtual threads, scheduler/executor behavior can differ; this lesson chooses Java 17 and an explicit `ThreadPoolTaskExecutor`.

## 20. Observing state across threads: volatile, Atomic*, and transactions

Awaitility **does not fix** data races. It only re-runs the assertion. Conditions must read state that is genuinely published across threads.

Counter-example:

~~~java
// Counter-example: no memory visibility contract.
class UnsafeFlag {
    boolean done;
}
~~~

One thread writes `done=true` while another reads repeatedly without a valid happens-before relationship: the program has a **data race**. You cannot fix it by polling faster or sleeping longer.

Appropriate options:

- `AtomicBoolean`/`AtomicInteger`/`AtomicLong` for simple state/counters.
- `volatile` for status flags requiring visibility; does not make compound operations like `counter++` atomic.
- `ConcurrentHashMap` and immutable value snapshots when multiple fields are related.
- `CountDownLatch`/`Future.get` for happens-before and completion signals.
- DB commit followed by query on a proper transaction/connection when state lives in a database.
- `BlockingQueue`/`CompletionService` when a consumer receives results from workers.

**Do not call `Thread.sleep` to compensate for missing synchronization.** It is never a proper solution for a data race.

### Multiple fields at once

If a worker does:

~~~java
result = "READY";
done = true;
~~~

and both are plain fields, a test may see wrong/stale flags depending on memory ordering. Use an immutable snapshot inside `AtomicReference`/`ConcurrentHashMap`, or group fields into one object and publish via a thread-safe mechanism. The `JobStore` demo replaces the entire `JobSnapshot` atomically with `compute` to keep status and payload in sync.

## 21. Worker failure: FAILED, Future exception, and fail-fast

An async test must not keep waiting for `SUCCEEDED` once the job has reached the terminal `FAILED` state.

Simple approach in the runnable example:

~~~java
await().atMost(Duration.ofSeconds(5))
    .untilAsserted(() ->
        assertThat(store.find(jobId).orElseThrow().status())
            .isEqualTo(JobStatus.FAILED)
    );
~~~

And afterward:

~~~java
assertThatThrownBy(() -> handle.completion()
        .get(5, TimeUnit.SECONDS))
    .isInstanceOf(ExecutionException.class)
    .hasCauseInstanceOf(IllegalStateException.class);
~~~

These are snippets taken from the integration test, relying on existing `store`/`handle` variables. For a test **expecting `SUCCEEDED`**, fail early if `FAILED` is observed, for example using Awaitility 4.x `failFast(...)` or writing a predicate that observes any terminal state and then asserts the final status upon waking:

~~~java
await().atMost(Duration.ofSeconds(5))
    .until(() -> {
        JobStatus state = store.find(jobId).orElseThrow()
                .status();
        return state == JobStatus.SUCCEEDED
                || state == JobStatus.FAILED;
    });

assertThat(store.find(jobId).orElseThrow().status())
        .isEqualTo(JobStatus.SUCCEEDED);
~~~

This avoids waiting the full 5 seconds when failure is already decisive. Do not configure `ignoreExceptions()` globally without care: it can swallow real database or serialization errors that should fail. If a condition has a **valid transient exception**, use `ignoreException(SomeTransientException.class)` with a very narrow scope and a deadline.

An `@Async void` method with an uncaught error may only log through a handler, invisible to the test. When errors must be asserted, prefer `CompletableFuture<T>` or an observable error channel/record. A test must never PASS simply because no exception occurred on the **test thread**.

## 22. @Scheduled: fixedDelay, fixedRate, cron, and environment

In Spring:

- `@Scheduled(fixedDelay=...)`: after the previous execution **completes**, wait the delay before the next one.
- `@Scheduled(fixedRate=...)`: schedules triggers at a fixed start cadence; actual overlap behavior depends on scheduler capacity and configuration.
- `@Scheduled(cron=..., zone=...)`: executes per cron schedule and zone; does not guarantee absolute precision under load.
- `initialDelay`/`initialDelayString`: delays the first run; useful when tests need to override configuration.
- `@EnableScheduling`: required to activate scheduling infrastructure.
- `@Scheduled` methods typically take no arguments, and return values are not treated as a test `Future`.

If you need to test "scan orders every 5 minutes":

1. Extract the **scanning logic** into a service that can be called directly and tested with fixture data/fake `Clock`.
2. Use a `@Scheduled` adapter to trigger that service.
3. Have an integration test solely prove the adapter is actually invoked by Spring when test config uses a small delay.
4. Do not assert the **exact absolute run count** after `Thread.sleep(5_000)`; assert an invariant like "ticked at least once more".
5. To simulate cron calendars and DST, test next-fire-time calculation with an explicit `ZoneId` and clock/time API instead of waiting in real life.

A scheduled method that calls an `@Async` worker can finish its `@Scheduled` callback **immediately upon enqueuing**, not when the job finishes processing. Thus the scheduler adapter's `fixedDelay` does not automatically wait for the async worker. Business tests must await **job completion** separately.

## 23. Timeouts across multiple layers and false-positive tests

Multiple timeout types are easily confused:

| Timeout | Purpose | Layer |
| --- | --- | --- |
| Awaitility `atMost` | Prevent test from waiting indefinitely for a condition | Assertion/test |
| `Future.get(timeout)` | Prevent waiting indefinitely for a Future | Java concurrency |
| JUnit `@Timeout` | Limit runtime of the entire test method | Test runner |
| HTTP client connect/read timeout | Bound network I/O | Client |
| DB query/transaction timeout | Bound SQL/transactions | Database |
| Broker consumer poll/ack timeout | Bound delivery/liveness | Messaging |
| CI job timeout | Bound overall pipeline | Infrastructure |

A test with `await().atMost(5s)` while the worker's HTTP call has a 60s timeout can still leave a background task running after the assertion times out. Design requires **cancellation, bounded I/O**, and cleanup, not merely increasing timeouts.

### Do not use preemptive timeouts arbitrarily with Spring @Transactional

Some JUnit timeout mechanisms can run the test body on **a different thread** (e.g., `assertTimeoutPreemptively`). Spring TestContext's test-managed transaction is bound to the test thread, so DB operations on the new thread may **not** join the test's rollback transaction. This is especially important for async tests: consumers, `@Async`, HTTP servers, and scheduled tasks already run on different threads/transactions. Do not expect `@Transactional` on a test to roll back all DB writes from background threads.

### Tests do not always have to wait 5 seconds

An `atMost(5s)` does not make every test take 5 seconds. If the state is already `SUCCEEDED` before the first poll, Awaitility can finish on the very first check. That is why condition-based waiting is both **faster** and **less flaky** than fixed sleeps.

## 24. When testing databases, HTTP, and message brokers: wait for the business effect

In distributed applications, the awaited signal must match the pipeline:

### Database worker

~~~java
await().atMost(Duration.ofSeconds(10))
    .untilAsserted(() ->
        assertThat(repository.findByCorrelationId(correlationId))
            .hasValueSatisfying(row ->
                assertThat(row.getStatus()).isEqualTo("COMPLETED")
            )
    );
~~~

This is an illustrative snippet without repository/entity definitions. Do not poll a stale `EntityManager` cache and conclude the DB has not committed; use a fresh transaction/connection or refresh if the persistence context holds stale state.

### HTTP 202 Accepted

~~~text
POST /jobs -> 202 Accepted + Location: /jobs/<id>
GET /jobs/<id> -> QUEUED
GET /jobs/<id> -> RUNNING
GET /jobs/<id> -> SUCCEEDED
~~~

Tests should poll `GET /jobs/{id}` with an appropriate client until terminal status, bounding the deadline and checking response body/side effects. Do not call `Thread.sleep(1_000)` after POST and assume the job is done.

### Kafka / RabbitMQ

~~~text
Producer sends E -> broker ack
Consumer receives E -> DB transaction/ledger commit
Test awaits ledger/status/callback observer
~~~

`KafkaTemplate.send(...).get()` only confirms producer-side delivery per configuration; **it does not prove the consumer finished**. For tests with two duplicate deliveries, await **enough consumer processing cycles** or check meaningful markers/business state; a single initial update does not prove a second delivery produces no side effect.

### MockMvc async dispatch

For Spring MVC controllers returning `Callable`, `DeferredResult`, or a supported async return type, tests can use:

~~~java
MvcResult pending = mockMvc.perform(get("/async/report"))
        .andExpect(request().asyncStarted())
        .andReturn();

mockMvc.perform(asyncDispatch(pending))
        .andExpect(status().isOk());
~~~

This is an illustrative snippet **only for MVC async controllers** with matching mappings and imports; it is not part of this lesson's runnable console application. `asyncDispatch` is how Spring MVC tests simulate async dispatch completion without requiring `Thread.sleep`. Do not use `asyncStarted()` on synchronous controllers, as it will properly FAIL.

## 25. Unit testing with virtual time: when NOT to poll a real clock

Some logic genuinely depends on **elapsed time**, such as Reactor `Flux.interval`, debounce, retry/backoff, or timeouts. Waiting a real 30 minutes with Awaitility is the wrong tool. **Virtualize the time source** when the framework supports it.

Reactor's `StepVerifier.withVirtualTime` is one option (requiring `io.projectreactor:reactor-test` in test scope and Reactor in the app):

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofMinutes(30)).take(2)
)
.expectSubscription()
.thenAwait(Duration.ofMinutes(30))
.expectNext(0L)
.thenAwait(Duration.ofMinutes(30))
.expectNext(1L)
.verifyComplete();
~~~

This is an **optional snippet, not part of the runnable Gradle sample**; it requires Reactor `Flux`, `StepVerifier` imports, and corresponding test dependencies. `withVirtualTime` must receive a **supplier creating the publisher after the virtual scheduler is installed**, rather than creating a `Flux` on a real scheduler beforehand and expecting time to be virtualized.

**`Clock.fixed` ≠ Reactor `VirtualTimeScheduler` ≠ Spring `TaskScheduler`.** Each mechanism controls its own subsystem's clock/scheduler. If code calls `System.currentTimeMillis` directly, Reactor's virtual time will not control it. If code reads timestamps from a DB server, JVM `Clock` injection will not control the DB clock either.

## 26. Running tests in parallel: shared resources and test data

Async tests are particularly sensitive to context caching and singleton state:

- A `@SpringBootTest` context can be **cached across multiple test classes**; a singleton `JobStore` bean retains state if not cleaned up.
- Two tests using the same job ID will contend over the same map/DB row, even if each test has its own Awaitility deadline.
- Test A calling `@AfterEach` cleanup while A's task finishes afterward can re-insert/update a row and pollute Test B.
- One test altering executor properties or using `@DirtiesContext` can affect context lifecycle; do not shut down a shared executor bean between methods.
- `@Scheduled` can keep ticking even after JUnit moves to the next method; scheduler tests must have proper data isolation or context/bean lifecycle.
- Shared `CountDownLatch`/`AtomicBoolean` in static fields across tests can introduce test-order dependencies.
- Across CI shards/multiple JVMs, JUnit's `@ResourceLock` only coordinates within its JVM/engine, not across shared DBs/brokers across processes.
- Background tasks run on other threads, so MDC, locale, security context, and transactions do not propagate automatically the way test authors might expect.

Solution in the demo: **unique UUID per job**, immutable snapshots, thread-safe map, `Future.get(timeout)` in cleanup, and closing the scheduler-specific context after the class. Do not put `@DirtiesContext` on all async tests due to context startup cost; use it only where lifecycle isolation is needed.

### Separating the waiter from the state mutator

If an Awaitility condition calls a side-effect-producing method on every poll:

~~~java
await().until(() -> paymentClient.charge(orderId).isSuccess());
~~~

this is **dangerous**: every poll could **charge again**. The right pattern is to trigger the effect **once**, then poll a **read-only** endpoint/ledger or await the corresponding callback/future. In messaging/retries, use a stable idempotency key and cap attempts per business rules.

## 27. Common mistakes and fixes

| Mistake | Symptom | Fix |
| --- | --- | --- |
| `Thread.sleep(1000)` then assert | CI fluctuates PASS/FAIL; slow suite | `await().untilAsserted` + deadline |
| Increasing sleep to 10s "just to be safe" | Slow suite yet still flaky when tasks stall | Wait for exact state or `Future` |
| Only asserting `Future` was created | Test PASSES before task runs | Await Future completion / business effect |
| Awaiting `status != QUEUED` | `FAILED` also satisfies the condition | Await `SUCCEEDED`, handle `FAILED` explicitly |
| Polling a queue with `poll()` inside predicate | Test consumes messages | Poll read-only or receive message once |
| Polling plain `HashMap`/boolean from another thread | Stale state / data race | `ConcurrentHashMap`, `Atomic*`, latch |
| `@Async` self-invocation | Task runs synchronously despite annotation | Extract bean, call through Spring proxy |
| Forgot `@EnableAsync` | `@Async` is not applied | Enable async configuration |
| Worker fails on `@Async void` without assertion | Test only times out meaninglessly | `CompletableFuture`/error channel |
| `Future.get()` without timeout | CI hangs forever | `get(timeout, unit)` |
| `@Scheduled` test asserts exact tick after 120ms | Drift from CPU/GC/context startup | Baseline count + await increase |
| Using `Clock.offset` to trigger Spring scheduler | Scheduler does not run on fake clock | Dedicated scheduler test or proper virtual scheduler |
| `@Transactional` test body with async DB write | Row does not roll back with test thread | Explicit DB cleanup / tx scope |
| Awaitility ignores all exceptions | Swallows real schema/connection errors | Ignore only specific named transient exceptions |
| Invoking task on every Awaitility poll | Causes duplicate business effects | Submit once, observe read-only in poll |
| `@DirtiesContext` on every test | Context churn, slow test suite | Proper resource isolation |
| Test only asserts producer ack | Consumer has not processed yet | Await consumer-side DB/status |
| Timeout too short on shared CI | Flaky under heavy load | Size deadlines to environment, reasonable poll |
| Timeout too huge masking deadlocks | Long wait with no feedback | Fail-fast / worker errors / metrics, bounded I/O |
| `@AfterEach` deletes fixtures while worker still runs | Worker recreates data after cleanup | Join/cancel tasks before cleanup |
| Reactive `StepVerifier` uses publisher created before virtual scheduler | Real time still elapses | Create publisher inside supplier |
| `Mockito.verify(timeout(...))` treated as proof of DB commit | Only verifies invocation | Assert committed DB state |
| Multiple tasks update a shared non-atomic counter | Lost updates | `AtomicLong` / DB atomic update |
| Waiting for callback while outbox relay is unfinished | Downstream side effect incomplete | Await the true authoritative boundary |

## 28. QA checklist before signing off on an async/scheduler test

- [ ] Does the test identify a **business completion condition** rather than a guessed delay?
- [ ] Is the task triggered **once**, and is the polling predicate read-only?
- [ ] Is there a finite timeout such as `atMost` or `get(timeout)`?
- [ ] Is the poll interval reasonable for CI without hammering databases/services?
- [ ] Is state published thread-safely (`Atomic*`, `ConcurrentHashMap`, DB commit)?
- [ ] Does the assertion check **SUCCEEDED + payload** rather than merely status not `QUEUED`?
- [ ] Are `FAILED`/worker exceptions checked or failed fast?
- [ ] Does it distinguish producer ack / request accepted from consumer business effect?
- [ ] For `@Async`, is the method invoked through a Spring bean proxy with `@EnableAsync`?
- [ ] Is the executor properly configured/named without silent rejections?
- [ ] Is there a `Future` handle/observer when debugging uncaught errors?
- [ ] For `@Scheduled`, does the test avoid assuming callbacks fire after an exact number of milliseconds?
- [ ] Are `Clock`/virtual time only used for subsystems that actually support them?
- [ ] When reproducing concurrency races, are latches/barriers used instead of sleep?
- [ ] Does test cleanup await/cancel background jobs before deleting fixtures?
- [ ] Is there no singleton test state sharing IDs or mutable latches?
- [ ] If DB writes happen on worker threads, does the test avoid relying on test transaction rollback?
- [ ] For HTTP/messaging, does it await final persisted state instead of just call invocation?
- [ ] Does it avoid swallowing exceptions via ignore-all or catch-and-return-success?
- [ ] Does it avoid turning timeouts into absolute performance assertions?
- [ ] Are expected results documented and does the report distinguish code review from actual test execution?

## 29. Run commands, expected results, and example limitations

From the directory containing the Gradle Wrapper and JDK 17+:

~~~bash
./gradlew test --tests "com.example.conditionwait.AsyncJobIntegrationTest"
./gradlew test --tests "com.example.conditionwait.ScheduledTickIntegrationTest"
./gradlew test --tests "com.example.conditionwait.GateWithoutSleepTest"
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "com.example.conditionwait.AsyncJobIntegrationTest"
.\gradlew.bat test --tests "com.example.conditionwait.ScheduledTickIntegrationTest"
.\gradlew.bat test --tests "com.example.conditionwait.GateWithoutSleepTest"
~~~

There are **8 JUnit test methods**: 4 in `AsyncJobIntegrationTest`, 2 in `ScheduledTickIntegrationTest`, and 2 in `GateWithoutSleepTest`.

Key expectations:

~~~text
Async input "hello" -> status=SUCCEEDED, result="HELLO"
Async input "FAIL"  -> status=FAILED, Future has IllegalStateException
Two jobs alpha/beta -> results "ALPHA" and "BETA"
Duplicate job ID    -> IllegalArgumentException, original job unchanged
Scheduler tick      -> counter increases over baseline within deadline
CountDownLatch      -> completes after release, no sleep
CompletableFuture   -> "ready" transformed to "READY"
~~~

These are **expected outcomes based on source code logic**, not observed Gradle/JUnit output. The code contains no `System.out.println`; test logs vary by runtime. **Gradle was not compiled/run during authoring**, so a full JDK 17, Gradle Wrapper, and dependency setup is needed to confirm in practice.

**Conclusion:** Do not use `Thread.sleep` as synchronization. **Trigger the task once**, pick a meaningful business state/signal, **wait for the condition with a finite timeout**, then assert both outcomes/errors and clean up. Awaitility fits eventual state; `Future.get(timeout)` fits task handles; `CountDownLatch` fits thread ordering; virtual time fits reactive timers. Done right, tests run fast when workers finish early and do not fail randomly due to CI speed.

### Official documentation and API guides

- [Spring Framework — Task Execution and Scheduling, @Async and @Scheduled](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Boot 3.5 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html)
- [Spring Boot 3.5 — Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/)
- [Spring Boot — Test Scope Dependencies/Awaitility](https://docs.spring.io/spring-boot/3.5/reference/testing/test-scope-dependencies.html)
- [Awaitility — Usage Guide 4.x](https://github.com/awaitility/awaitility/wiki/Usage)
- [Awaitility — GitHub README](https://github.com/awaitility/awaitility)
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [JUnit Jupiter — User Guide (parallel execution, timeouts)](https://docs.junit.org/current/user-guide/)
- [Reactor — Testing with StepVerifier and Virtual Time](https://projectreactor.io/docs/core/release/reference/testing.html)