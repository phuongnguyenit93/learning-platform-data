# Testing Synchronous, Asynchronous, and Error-Handling Event Listeners

## 1. Why Must Event Listeners Be Tested Under Two Execution Models?

Spring provides **application events** so components within the same `ApplicationContext` can exchange signals without calling one another directly. A service can publish `OrderPlaced`; other listeners write audits, update projections, or trigger notifications. This reduces coupling, yet makes it easy for tests to draw wrong conclusions about **execution timing, execution threads, transaction scope, exceptions, and retries**.

For example:

```java
publisher.publishEvent(new OrderPlaced("ORD-101"));
```

With a **default synchronous** `@EventListener`, the listener executes on the caller's thread; if the listener throws a runtime exception, `publishEvent(...)` can propagate that exception to the caller and stop subsequent listeners from running.

With `@Async @EventListener`, execution is handed off to an executor: the caller can return before the listener completes. Exceptions from an asynchronous `void` method **do not propagate back to the caller through the normal `publishEvent` call**. Detecting failures requires inspecting a completion signal, error handler, log/metric, or business state. Exceptions during **task submission**—such as executor rejection—can still happen at publish time; do not confuse that with exceptions raised *inside* the worker.

This lesson belongs to **Events and Observability**, topic **“Testing synchronous, asynchronous, and error-handling event listeners”**. The scope is Spring **application events within the same JVM**, not Kafka/RabbitMQ broker listeners. Examples use **Java 17+**, **Spring Boot 3.3.5**, **Spring Framework 6.1**, JUnit Jupiter, and `spring-boot-starter-test`.

### Learning Goals

- Distinguish `ApplicationEventPublisher.publishEvent(...)`, `@EventListener`, `@Async`, and `ApplicationEventMulticaster`.
- Test synchronous listeners: exact order, exact thread, error propagation to publisher, and halted fan-out on failure.
- Test asynchronous listeners: executor thread, bounded completion signals with timeout, and errors not propagating directly to the publisher.
- Configure `@EnableAsync`, a named `ThreadPoolTaskExecutor`, and `AsyncUncaughtExceptionHandler`.
- Distinguish the `@Async` error handler from `SimpleApplicationEventMulticaster.setErrorHandler(...)`.
- Test both multicaster policies: default propagate and custom suppress/record.
- Use `@RecordApplicationEvents`/`ApplicationEvents` to confirm **the event was published**, without confusing that with listener completion.
- Avoid `Thread.sleep`, brittle elapsed-time checks, and assertions tied to scheduling order.
- Recognize `@TransactionalEventListener`, `@Order`, retries/idempotency, observability, and propagation of MDC/tracing context.
- Know when integration tests with DB/outbox, brokers, or real metrics systems are required.

## 2. Mental Model Before Writing Tests

```text
                         ApplicationEventPublisher
                               publishEvent(E)
                                     |
                             ApplicationEventMulticaster
                                     |
                      +--------------+-----------------+
                      |                                |
             @EventListener sync               @Async @EventListener
                      |                                |
                 caller thread                   eventExecutor pool
                      |                                |
                logic + side effect              logic + side effect
                      |                                |
          RuntimeException can return        void listener exception
          directly to publisher              -> AsyncUncaughtExceptionHandler
                      |                                |
            test assertThrows(...)              test awaits result/failure
            + assert state/order                with timeout
```

**By default**, `SimpleApplicationEventMulticaster` dispatches listeners on the **publisher's thread**. This is a synchronous mechanism despite “publish” in the API name. Spring can be configured with a shared task executor on the multicaster, but **the sample project does not do so**: we keep the default synchronous dispatch and apply `@Async("eventExecutor")` **only to one specific listener**. That lets tests distinguish the two paths cleanly.

| Signal | What It Proves | What It Does Not Automatically Prove |
| --- | --- | --- |
| `publishEvent` was called | Publisher handed the event to the dispatch mechanism | Listener finished / committed |
| `publishEvent` returns under default sync | Synchronous listeners finished dispatching if none failed | External non-transactional side effects are durable |
| `publishEvent` returns with `@Async` | Task was submitted to the configured executor | Listener completed |
| Listener success callback/probe | Processing branch reached the success marker | Database/external broker commit if callback fires too early |
| `AsyncUncaughtExceptionHandler` receives error | Async void method threw an unhandled exception | Caller received error or job will auto-retry |
| `ApplicationEvents` records event | Event was published during the test | A listener ran on a different thread |
| Business table/metric updated | Side effect was observed | Exactly-once across all failures/retries |

### In-JVM Events Are Not a Durable Queue

Spring `ApplicationEventPublisher` does not persist messages to disk by default, has no consumer offsets, and has no dead-letter queue. If the JVM crashes right after publishing or before the executor finishes, an application event is not automatically replayed. If the domain requires durable delivery after a DB commit, consider a **transactional outbox**, a broker, or dedicated retry/idempotency mechanisms. Application event tests do not replace end-to-end tests for those systems.

## 3. Synchronous Event Listener: Exceptions Can Fail the Publisher

Example with two listeners receiving a `SyncSignal` record:

- The first listener has `@Order(10)`, records a trace mark, and can throw `IllegalStateException` when the signal requests a simulated failure.
- The second listener has `@Order(20)` and records the next trace mark.
- On success, both listeners run on the publisher thread in order.
- When the first listener fails, under the **default multicaster with no custom ErrorHandler**, the error propagates back to the publisher, and the subsequent listener might not be called.

```text
publish SyncSignal("A", false)
     -> first @Order(10)   [record "first"]
     -> second @Order(20)  [record "second"]
     -> return normally

publish SyncSignal("B", true)
     -> first @Order(10)   [record "first"; throw]
     -> publisher receives IllegalStateException
     -> second not called under default fail-fast dispatch
```

**Do not generalize this to all event infrastructures.** If the application customizes `ApplicationEventMulticaster` with an executor or `ErrorHandler`, propagation and continued dispatch change. Tests must reflect the real configuration.

### @Order Is Not Global Ordering in Async Systems

`@Order` helps control invocation order for listeners, yet with multi-threaded task executors, **completion order** can differ. Two `@Async` listeners scheduled in order does not mean their side effects commit in order. To guarantee business ordering, serialize work by key/partition or design an explicit workflow.

## 4. Asynchronous Listener: Test Results, Not Sleep

`@Async` works via Spring asynchronous method interception. `@EnableAsync` and a Spring-managed bean are required; calling an async method via `this.someAsyncMethod()` (self-invocation) can bypass proxy-based interception.

In the demo, an `@EventListener` is annotated with `@Async("eventExecutor")` and receives `AsyncSignal`. It:

- Succeeds → signals completion with an `AsyncCompletion` containing the event ID and worker thread name.
- Fails → throws `IllegalStateException`.
- The configured `AsyncUncaughtExceptionHandler` captures `void` method exceptions and records an `AsyncFailure` keyed by event ID.
- Tests await `CompletableFuture.get(5, TimeUnit.SECONDS)` with a deadline.
- Tests generate a unique correlation ID before publishing, independent of worker speed.

Do not write:

```java
publisher.publishEvent(event);
Thread.sleep(1000);
assertEquals(1, output.size());
```

This is an **anti-pattern**: one second may be too long on a laptop yet too short on a loaded CI runner. Never increase arbitrary timeouts when lacking a completion signal; design a proper observable condition and use a bounded wait.

### CompletableFuture in the Example Is a Test Probe, Not an EventListener Return Value

`@Async @EventListener` does not support emitting new events via return values like synchronous listeners; the example uses **a thread-safe `EventProbe`** storing futures by ID for tests to await. We **do not** return `CompletableFuture` from the event listener and do not treat `publisher.publishEvent` as a future representing processing.

In production, outcome signals should be reflected through meaningful business state, DB, outbox, metrics, or error infrastructure; the probe in this lab simply demonstrates deterministic testing.

## 5. Distinguishing Three Kinds of Errors

| Error | When It Happens | Who Can Observe It | What Tests Should Do |
| --- | --- | --- | --- |
| Sync listener throws `RuntimeException` | During dispatch on publisher thread | Caller of `publishEvent` | `assertThrows` + check whether later listener ran |
| `@Async void` listener throws | On worker thread, after submit | `AsyncUncaughtExceptionHandler`/logs/metrics | Await failure signal with timeout; assert cause/method/ID |
| Executor rejects task | At dispatch/submit time or shutdown/full queue | Publisher may receive `TaskRejectedException` | Test saturation/rejection separately; don't confuse with worker exception |
| Global multicaster `ErrorHandler` suppresses | Listener fails in dispatch, handler swallows error | ErrorHandler | Assert publisher does not throw and handler recorded it |
| Global multicaster propagates | No ErrorHandler or handler rethrows | Publisher or executor (depending on execution model) | Assert expected exception at the right boundary |
| Transactional listener AFTER_COMMIT fails | After transaction commit | Transaction callback/log/caller behavior per config | Test exact transaction/commit; do not claim rollback occurred |
| Domain side effect fails but is caught | Listener catches and logs/suppresses | Metrics/error store/test probe | Test fail-closed/retry policy, not just HTTP response |

An application may require **failure isolation** (listener A failing does not block listener B) or **fail-fast** (bad audit rolls back the command). No single policy fits every system. Choose intentionally and write tests guarding that choice.

## 6. Illustrative Project Structure

This project is a Spring Boot application without a web server, featuring two event types and two error-handling policies. The main suite runs upon Spring TestContext startup; no Kafka, RabbitMQ, database, or Redis is needed.

```text
spring-event-listener-tests/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/events/
│   ├── EventLessonApplication.java
│   ├── SyncSignal.java
│   ├── AsyncSignal.java
│   ├── EventProbe.java
│   ├── EventCommandService.java
│   ├── FirstSyncListener.java
│   ├── SecondSyncListener.java
│   ├── AsyncSignalListener.java
│   └── EventAsyncConfiguration.java
└── src/test/java/com/example/events/
    ├── EventListenersTest.java
    └── MulticasterPolicyTest.java
```

The test suite has two independent classes:

1. `EventListenersTest` uses a **real Spring context**, publisher, annotated listeners, `@EnableAsync`, named executor, and error handler. It tests real wiring.
2. `MulticasterPolicyTest` uses **`SimpleApplicationEventMulticaster` directly**, without a Spring Boot context, to isolate the two ErrorHandler policies. It does **not** claim the production app configures its global multicaster in either way.

### Specifications

- Java: 17+.
- Spring Boot: **3.3.5**.
- Spring Framework: 6.1.x managed by Boot BOM.
- Gradle dependency management plugin: 1.1.6.
- JUnit Jupiter and Mockito/AssertJ from `spring-boot-starter-test`.
- No test assertions based on elapsed milliseconds, scheduling order luck, or real HTTP.

## 7. Gradle Configuration

### settings.gradle

```groovy
rootProject.name = 'spring-event-listener-tests'
```

### build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

`spring-boot-starter` brings in Spring Context, scheduling/async infrastructure, and logging. `spring-boot-starter-test` provides JUnit Jupiter, Spring TestContext, AssertJ, and `@RecordApplicationEvents`. No web starter is needed since the lesson uses internal application events.

**If no Gradle Wrapper exists yet** (the project lists only the two Gradle scripts), run a compatible installed Gradle with `gradle test`, or generate the Wrapper per project conventions; do not run `./gradlew` on a directory lacking that script and think the test code is broken.

## 8. Spring Boot Application Root

`src/main/java/com/example/events/EventLessonApplication.java`:

```java
package com.example.events;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EventLessonApplication {

    public static void main(String[] args) {
        SpringApplication.run(EventLessonApplication.class, args);
    }
}
```

The root class sits in the parent package `com.example.events` so Spring scans the listeners, publisher service, probe, and async configuration. There is no controller. Tests use `@SpringBootTest(webEnvironment = NONE)` to ensure no embedded HTTP port opens.

### Why Not Write a Custom Static Event Bus?

Spring `ApplicationEventPublisher` integrates with ApplicationContext, `@EventListener`, and lifecycle facilities. A custom static event bus can lack bean lifecycles, conditionals, proxies, and test support. To learn/test Spring EventListener, use the framework's real dispatcher and fake only **outputs/supporting infrastructure** rather than mocking the entire `ApplicationEventPublisher` in the main integration suite.

## 9. Two Event Records with Distinct Identifiers

`src/main/java/com/example/events/SyncSignal.java`:

```java
package com.example.events;

public record SyncSignal(String id, boolean fail) {
    public SyncSignal {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id is required");
        }
    }
}
```

`src/main/java/com/example/events/AsyncSignal.java`:

```java
package com.example.events;

public record AsyncSignal(String id, boolean fail) {
    public AsyncSignal {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id is required");
        }
    }
}
```

Java records are immutable message payloads. `id` lets tests distinguish executions, while `fail` is merely a **synthetic fault-injection** toggle for the lesson, not a production event schema design. In production, use business event IDs, correlation IDs, payload versions, and timestamps per contract.

`ApplicationEventPublisher.publishEvent(Object)` supports POJOs/records that do not extend `ApplicationEvent`. Spring wraps the object when needed for dispatch, while the listener method receives the exact declared record type.

### Event ID Differs from Trace ID

A correlation event ID ties an outcome to an input. A Trace ID from Micrometer/OpenTelemetry links spans in observability. They can be related, yet are **not identical**: one event can be processed/retried multiple times across different traces, and one trace can contain multiple events. Do not substitute a thread name or trace ID for a unique business event ID.

## 10. EventProbe: Bounded, Thread-Safe Observation

`src/main/java/com/example/events/EventProbe.java`:

```java
package com.example.events;

import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.stereotype.Component;

@Component
public class EventProbe {

    public record SyncCall(
            String stage,
            String threadName
    ) {
    }

    public record AsyncCompletion(
            String id,
            String threadName
    ) {
    }

    public record AsyncFailure(
            String id,
            String methodName,
            String exceptionType,
            String message,
            String threadName
    ) {
    }

    private final ConcurrentMap<String, List<SyncCall>>
            syncCalls = new ConcurrentHashMap<>();

    private final ConcurrentMap<String, CompletableFuture<AsyncCompletion>>
            successes = new ConcurrentHashMap<>();

    private final ConcurrentMap<String, CompletableFuture<AsyncFailure>>
            failures = new ConcurrentHashMap<>();

    public void markSync(String id, String stage) {
        syncCalls.computeIfAbsent(
                id,
                ignored -> new CopyOnWriteArrayList<>()
        ).add(new SyncCall(
                stage, Thread.currentThread().getName()));
    }

    public List<SyncCall> syncCalls(String id) {
        List<SyncCall> calls = syncCalls.get(id);
        return calls == null ? List.of() : List.copyOf(calls);
    }

    public CompletableFuture<AsyncCompletion> success(String id) {
        return successes.computeIfAbsent(
                id,
                ignored -> new CompletableFuture<>());
    }

    public CompletableFuture<AsyncFailure> failure(String id) {
        return failures.computeIfAbsent(
                id,
                ignored -> new CompletableFuture<>());
    }

    public void markAsyncSuccess(String id) {
        success(id).complete(
                new AsyncCompletion(
                        id, Thread.currentThread().getName()));
    }

    public void markAsyncFailure(
            String id, String method, Throwable exception) {

        failure(id).complete(
                new AsyncFailure(
                        id,
                        method,
                        exception.getClass().getSimpleName(),
                        exception.getMessage(),
                        Thread.currentThread().getName()));
    }
}
```

**Why separate `success(id)` and `failure(id)`?** Tests can await the exact outcome for a specific event. A successful listener completes the success future; when the listener throws, the async error handler completes the failure future. Both include the correlation ID and thread name to verify the execution path.

`ConcurrentHashMap` and `CopyOnWriteArrayList` protect access across the test thread and event workers. `CompletableFuture.complete(...)` ensures proper memory visibility when the test thread calls `get(...)`. Neither `volatile boolean processed` nor `Thread.sleep` is needed.

**Limitation:** this is an in-memory probe strictly for the lesson, not a persistent, retryable, memory-bounded job status store. The maps grow with event IDs; a production application must manage lifecycle/eviction, telemetry, and business state. If business code has a DB transaction, calling `markAsyncSuccess` **before commit** does not prove commit; place the signal where the contract requires or assert DB state separately.

### Why Not Clear the Whole Probe in @BeforeEach?

Tests generate fresh IDs from `UUID.randomUUID()` so they never share outcomes. Clearing a shared map could collide with an unfinished worker from a prior test under parallel runs. In this project, each async test awaits its completion or failure before ending. If enabling JUnit parallel execution or high volume, isolate probes per test/class or clean up strictly by owned ID.

## 11. Real Publishing Service

`src/main/java/com/example/events/EventCommandService.java`:

```java
package com.example.events;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class EventCommandService {

    private final ApplicationEventPublisher publisher;

    public EventCommandService(
            ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void publishSync(String id, boolean fail) {
        publisher.publishEvent(new SyncSignal(id, fail));
    }

    public void publishAsync(String id, boolean fail) {
        publisher.publishEvent(new AsyncSignal(id, fail));
    }
}
```

The service is solely responsible for publishing, without directly invoking listeners or knowing about thread pools. In a real app, you might publish after domain state changes; if emitting an event before a transaction commits and the listener runs synchronously, the listener can observe uncommitted state on the same thread/transaction. When execution must wait for commit, use `@TransactionalEventListener` with dedicated tests (Section 24).

### Why Not Mock the Service in Tests?

The primary integration test needs to verify the wiring `ApplicationEventPublisher → multicaster → @EventListener / @Async`. If `EventCommandService` were a Mockito mock, no real `publishEvent` would occur and the test would not protect the configuration. Keep the service and listeners real; fake only the observation probe with no external side effects.

## 12. First Synchronous Listener: @Order(10), With Error Branch

`src/main/java/com/example/events/FirstSyncListener.java`:

```java
package com.example.events;

import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
public class FirstSyncListener {

    private final EventProbe probe;

    public FirstSyncListener(EventProbe probe) {
        this.probe = probe;
    }

    @EventListener
    @Order(10)
    public void onSync(SyncSignal signal) {
        probe.markSync(signal.id(), "first");

        if (signal.fail()) {
            throw new IllegalStateException(
                    "sync rejected: " + signal.id());
        }
    }
}
```

This listener records a trace mark before throwing so tests can verify **it was invoked yet failed during processing**. With `fail=false`, it finishes normally.

### Exceptions Thrown from Synchronous Listeners

A runtime exception like `IllegalStateException` is normally passed back by Spring's `@EventListener` adapter to the event multicaster. By default, `SimpleApplicationEventMulticaster` has no custom error handler and dispatches synchronously, so the exception returns to the publisher. If a listener throws a **checked exception**, the adapter can wrap it in `UndeclaredThrowableException`; the example uses an unchecked exception to avoid an off-topic wrapper layer.

**Do not depend on framework exception messages** when tests may run across versions. We assert the message explicitly constructed by `FirstSyncListener`, keeping the expected value unambiguous.

## 13. Second Synchronous Listener: @Order(20)

`src/main/java/com/example/events/SecondSyncListener.java`:

```java
package com.example.events;

import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
public class SecondSyncListener {

    private final EventProbe probe;

    public SecondSyncListener(EventProbe probe) {
        this.probe = probe;
    }

    @EventListener
    @Order(20)
    public void onSync(SyncSignal signal) {
        probe.markSync(signal.id(), "second");
    }
}
```

Because `@Order(10)` has higher precedence than `@Order(20)`, under default sync dispatch we expect order `first` → `second`. When the first listener throws, Spring halts processing the listener list for that dispatch (under no-suppress defaults). Tests verify **second does not run** in the failure scenario.

If `SimpleApplicationEventMulticaster.setErrorHandler(...)` is configured to suppress errors, the result changes. This matters because error policy choices affect side effects: should one failing listener prevent other notifications or projections?

## 14. @Async Listener: Worker Thread and Exceptions

`src/main/java/com/example/events/AsyncSignalListener.java`:

```java
package com.example.events;

import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

@Component
public class AsyncSignalListener {

    private final EventProbe probe;

    public AsyncSignalListener(EventProbe probe) {
        this.probe = probe;
    }

    @Async("eventExecutor")
    @EventListener
    public void onAsync(AsyncSignal signal) {
        if (signal.fail()) {
            throw new IllegalStateException(
                    "async rejected: " + signal.id());
        }

        probe.markAsyncSuccess(signal.id());
    }
}
```

Points to note:

- `@Async("eventExecutor")` specifies **the exact executor bean**. Without a qualifier, Spring picks an executor based on async infrastructure and bean names/config, making it harder for tests to prove execution on a specific pool.
- `@EventListener` on the same method registers the listener for event type `AsyncSignal`.
- The method returns `void`, so errors cannot be returned to the publisher as a `CompletableFuture` via `publishEvent`.
- The success branch calls `probe.markAsyncSuccess` right at the demo's **logical completion point**.
- The failure branch throws an exception; the custom `AsyncUncaughtExceptionHandler` records the error.
- Do not wrap the listener body in a `try/catch` that swallows exceptions and falsely reports success.

### What Can Prevent @Async from Running Asynchronously?

- Forgetting `@EnableAsync`.
- Instantiating the listener manually with `new AsyncSignalListener(...)` outside Spring, bypassing the proxy.
- Calling the method directly from within the same bean via `this.onAsync(...)`, bypassing proxy-based advice.
- Configuring the executor to run inline via `SyncTaskExecutor`.
- Async interceptor not applied due to bean registration/proxy setting changes.
- Tests invoking the listener method directly instead of going through `ApplicationEventPublisher`.

The test verifies that the worker thread name starts with the dedicated prefix `event-worker-` and differs from the publisher test thread. Tests do not assert that publishing completes in fewer than a few milliseconds, because CPU/CI scheduling is non-deterministic.

## 15. Configuring @EnableAsync and AsyncUncaughtExceptionHandler

`src/main/java/com/example/events/EventAsyncConfiguration.java`:

```java
package com.example.events;

import java.lang.reflect.Method;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class EventAsyncConfiguration implements AsyncConfigurer {

    private static final Logger log =
            LoggerFactory.getLogger(EventAsyncConfiguration.class);

    private final EventProbe probe;

    public EventAsyncConfiguration(EventProbe probe) {
        this.probe = probe;
    }

    @Bean("eventExecutor")
    ThreadPoolTaskExecutor eventExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("event-worker-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(5);

        return executor;
    }

    @Override
    public AsyncUncaughtExceptionHandler
            getAsyncUncaughtExceptionHandler() {

        return (exception, method, args) -> {
            if (args.length == 1
                    && args[0] instanceof AsyncSignal signal) {

                probe.markAsyncFailure(
                        signal.id(),
                        method.getName(),
                        exception);

                log.warn(
                        "Async event listener {} failed for {}",
                        method.getName(),
                        signal.id(),
                        exception);
            } else {
                log.error(
                        "Unexpected async method failure: {}",
                        method.getName(),
                        exception);
            }
        };
    }
}
```

### What This Configuration Guarantees

- `@EnableAsync` enables async method interception.
- `eventExecutor` is a Spring-lifecycle-managed named `ThreadPoolTaskExecutor`; when the bean initializes, it creates worker threads as needed.
- `setThreadNamePrefix("event-worker-")` lets tests verify worker execution without depending on JUnit thread names.
- `setCorePoolSize(2)`, `setMaxPoolSize(2)`, `setQueueCapacity(16)` fit the small event volume in the lab; they are not production throughput settings.
- Shutdown properties support cleaner context closure without guaranteeing transactional durability for external side effects.
- `getAsyncUncaughtExceptionHandler()` captures **uncaught exceptions from asynchronous `void` methods**. It extracts the original method/args to associate the failure with the event ID.

### Two Caveats

**Caveat 1 — AsyncConfigurer initializes early.** Spring docs note that an `AsyncConfigurer` configuration class can be initialized early in the ApplicationContext. Here it injects only a lightweight `EventProbe` with no proxies or external connections. In production, avoid injecting a complex bean graph into `AsyncConfigurer` before post-processing completes; extract a simple error sink or use appropriate lazy initialization.

**Caveat 2 — Logging does not replace a failure policy.** The custom handler currently records to the probe and logs. It does not retry, send to a DLQ, or roll back the earlier publish command. If async errors require business recovery, the application needs a durable failure-handling mechanism, not just a warning log.

### Should You Declare getAsyncExecutor()?

Because the listener declares `@Async("eventExecutor")`, it looks up the specific `eventExecutor` bean; the demo does not need to override `AsyncConfigurer.getAsyncExecutor()` for a default. If other `@Async` methods exist without qualifiers, a real application should configure a default executor explicitly instead of relying on fallback behavior. Testing the default executor is separate from testing this named event listener.

## 16. Integration Test Suite: EventListenersTest.java

`src/test/java/com/example/events/EventListenersTest.java`:

```java
package com.example.events;

import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@RecordApplicationEvents
class EventListenersTest {

    @Autowired
    EventCommandService commands;

    @Autowired
    EventProbe probe;

    private String id(String prefix) {
        return prefix + "-" + UUID.randomUUID();
    }

    @Test
    void syncListenersRunInOrderOnPublisherThread() {
        String eventId = id("sync");
        String publisherThread =
                Thread.currentThread().getName();

        commands.publishSync(eventId, false);

        List<EventProbe.SyncCall> calls =
                probe.syncCalls(eventId);

        assertEquals(
                List.of("first", "second"),
                calls.stream()
                        .map(EventProbe.SyncCall::stage)
                        .toList());

        assertTrue(calls.stream().allMatch(call ->
                publisherThread.equals(call.threadName())));
    }

    @Test
    void syncExceptionPropagatesAndStopsLaterListener() {
        String eventId = id("sync-error");

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> commands.publishSync(eventId, true));

        assertEquals(
                "sync rejected: " + eventId,
                error.getMessage());

        assertEquals(
                List.of("first"),
                probe.syncCalls(eventId).stream()
                        .map(EventProbe.SyncCall::stage)
                        .toList());
    }

    @Test
    void twoSyncEventsKeepIndependentHistories() {
        String firstId = id("one");
        String secondId = id("two");

        commands.publishSync(firstId, false);
        commands.publishSync(secondId, false);

        assertEquals(2, probe.syncCalls(firstId).size());
        assertEquals(2, probe.syncCalls(secondId).size());
        assertTrue(probe.syncCalls("not-published").isEmpty());
    }

    @Test
    void asyncSuccessRunsOnNamedWorkerThread()
            throws Exception {

        String eventId = id("async-success");
        String publisherThread =
                Thread.currentThread().getName();

        CompletableFuture<EventProbe.AsyncCompletion>
                completion = probe.success(eventId);

        commands.publishAsync(eventId, false);

        EventProbe.AsyncCompletion observed =
                completion.get(5, TimeUnit.SECONDS);

        assertEquals(eventId, observed.id());
        assertTrue(observed.threadName()
                .startsWith("event-worker-"));
        assertNotEquals(publisherThread,
                observed.threadName());
    }

    @Test
    void asyncFailureDoesNotEscapePublishEvent()
            throws Exception {

        String eventId = id("async-error");
        CompletableFuture<EventProbe.AsyncFailure>
                failure = probe.failure(eventId);

        assertDoesNotThrow(() ->
                commands.publishAsync(eventId, true));

        EventProbe.AsyncFailure observed =
                failure.get(5, TimeUnit.SECONDS);

        assertEquals(eventId, observed.id());
        assertEquals(
                "IllegalStateException",
                observed.exceptionType());
    }

    @Test
    void asyncErrorHandlerRecordsMethodAndCause()
            throws Exception {

        String eventId = id("async-handler");
        CompletableFuture<EventProbe.AsyncFailure>
                failure = probe.failure(eventId);

        commands.publishAsync(eventId, true);

        EventProbe.AsyncFailure observed =
                failure.get(5, TimeUnit.SECONDS);

        assertEquals("onAsync", observed.methodName());
        assertEquals(
                "async rejected: " + eventId,
                observed.message());
        assertTrue(observed.threadName()
                .startsWith("event-worker-"));

        assertFalse(probe.success(eventId).isDone());
    }

    @Test
    void twoAsyncSignalsAreCorrelatedById()
            throws Exception {

        String firstId = id("async-A");
        String secondId = id("async-B");

        CompletableFuture<EventProbe.AsyncCompletion>
                first = probe.success(firstId);
        CompletableFuture<EventProbe.AsyncCompletion>
                second = probe.success(secondId);

        commands.publishAsync(firstId, false);
        commands.publishAsync(secondId, false);

        assertEquals(
                firstId,
                first.get(5, TimeUnit.SECONDS).id());
        assertEquals(
                secondId,
                second.get(5, TimeUnit.SECONDS).id());

        // Do not assert completion order of the two tasks.
    }

    @Test
    void successfulAsyncEventHasNoFailureRecord()
            throws Exception {

        String eventId = id("async-no-failure");
        CompletableFuture<EventProbe.AsyncCompletion>
                success = probe.success(eventId);

        commands.publishAsync(eventId, false);

        assertEquals(
                eventId,
                success.get(5, TimeUnit.SECONDS).id());
        assertFalse(probe.failure(eventId).isDone());
    }

    @Test
    void publishedEventIsVisibleToApplicationEvents(
            ApplicationEvents events) {

        String eventId = id("recorded");

        commands.publishSync(eventId, false);

        long count = events.stream(SyncSignal.class)
                .filter(signal ->
                        eventId.equals(signal.id()))
                .count();

        assertEquals(1L, count);
        assertEquals(2, probe.syncCalls(eventId).size());
    }
}
```

**There are 9 `@Test` methods** in `EventListenersTest`. Random event IDs strictly isolate test probe entries and do not alter expected behavior. None of the tests assert exact milliseconds or use thread sleeps.

### Key Assertions Explained

**Sync success:** checks both `List.of("first","second")` and that both callback thread names match the publisher thread. This guards default sync dispatch and `@Order`. If someone switches the global multicaster to an async executor, this test detects the changed assumption.

**Sync failure:** uses `assertThrows` at the **publisher boundary** and asserts only `first` ran; this verifies the demo's fail-fast behavior. If a suppressing custom ErrorHandler is introduced to the app, update the test to reflect the new policy rather than dropping assertions haphazardly.

**Async success:** awaits `CompletableFuture.get(5, SECONDS)`, asserts the worker prefix, and confirms it differs from the publisher thread. This catches bugs like missing `@EnableAsync` or accidental synchronous execution.

**Async failure:** obtains the future before publishing so no result is missed; `assertDoesNotThrow(publishAsync(...))` verifies listener exceptions do not propagate directly to the caller under non-saturated setup. Then it awaits the failure future and asserts class/method/message/thread. For submission-time executor rejection, a separate test must target that specifically; do not expect `assertDoesNotThrow` under arbitrary load.

**Multiple events:** completion order is unfixed, so assert by correlation ID rather than `first completed before second`. A two-worker pool can finish out of publish order.

**ApplicationEvents:** `@RecordApplicationEvents` captures events published during the test; `ApplicationEvents.stream(SyncSignal.class)` proves **the event was published**, while the probe proves listeners handled it. For async, the event recorder alone is insufficient to tell whether the worker finished.

## 17. Testing SimpleApplicationEventMulticaster and Two Error Policies

Spring offers `SimpleApplicationEventMulticaster.setErrorHandler(...)` to handle exceptions from multicast listeners. This is a **different mechanism** from `AsyncUncaughtExceptionHandler`, which handles uncaught errors from `@Async` void methods.

Create `src/test/java/com/example/events/MulticasterPolicyTest.java`:

```java
package com.example.events;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class MulticasterPolicyTest {

    static final class ProbeEvent extends ApplicationEvent {
        ProbeEvent(Object source) {
            super(source);
        }
    }

    private SimpleApplicationEventMulticaster multicasterWithFailure() {
        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();

        multicaster.addApplicationListener(
                new ApplicationListener<ProbeEvent>() {
                    @Override
                    public void onApplicationEvent(ProbeEvent event) {
                        throw new IllegalStateException(
                                "multicaster listener failed");
                    }
                });

        return multicaster;
    }

    @Test
    void defaultMulticasterPropagatesListenerError() {
        SimpleApplicationEventMulticaster multicaster =
                multicasterWithFailure();

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> multicaster.multicastEvent(
                        new ProbeEvent(this)));

        assertEquals(
                "multicaster listener failed",
                error.getMessage());
    }

    @Test
    void customErrorHandlerCanRecordAndSuppressError() {
        SimpleApplicationEventMulticaster multicaster =
                multicasterWithFailure();
        AtomicReference<Throwable> observed =
                new AtomicReference<>();

        multicaster.setErrorHandler(observed::set);

        assertDoesNotThrow(() ->
                multicaster.multicastEvent(
                        new ProbeEvent(this)));

        Throwable error = observed.get();
        assertNotNull(error);
        assertInstanceOf(
                IllegalStateException.class, error);
        assertEquals(
                "multicaster listener failed",
                error.getMessage());
    }
}
```

**There are 2 `@Test` methods**. The whole project contains **11 test methods**: 9 integration event tests and 2 multicaster policy unit tests.

### Significance of Direct Multicaster Tests

- No custom ErrorHandler → synchronous listener exception propagates out of `multicastEvent`.
- With `setErrorHandler(observed::set)` → the handler **records and suppresses** the exception; the call does not throw.
- The test does not alter the production `ApplicationContext`; it simply proves **how `SimpleApplicationEventMulticaster` behaves**.

If you truly want the app to use a suppress policy, configure a **multicaster bean** with the name recognized by Spring ApplicationContext and write an integration test guarding that behavior in context. Changing the global multicaster is an architectural decision requiring review, not a shortcut to turn one fail-fast test green.

## 18. Notes for Configuring a Global ErrorHandler

In a Spring ApplicationContext, the bean named `applicationEventMulticaster` has special significance. An *illustrative* configuration, **not part of the main runnable project**:

```java
@Configuration(proxyBeanMethods = false)
class MulticasterPolicyConfiguration {

    @Bean(name = "applicationEventMulticaster")
    ApplicationEventMulticaster applicationEventMulticaster() {
        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();

        multicaster.setErrorHandler(
                TaskUtils.LOG_AND_SUPPRESS_ERROR_HANDLER);

        return multicaster;
    }
}
```

Requires imports `Configuration`, `Bean`, `ApplicationEventMulticaster`, `SimpleApplicationEventMulticaster`, and `org.springframework.scheduling.support.TaskUtils`. Adding this to the app changes the **sync failure policy from the project's**: errors may be logged/suppressed and subsequent listeners may proceed, depending on dispatch/handler. Update tests to reflect the intended policy rather than having two conflicting configs coexist.

**Do not replace `EventAsyncConfiguration` with the snippet above** and claim `AsyncUncaughtExceptionHandler` was tested. The two error hooks operate at different layers:

- The global multicaster ErrorHandler wraps listener invocation/dispatch (on the respective thread).
- `AsyncUncaughtExceptionHandler` receives errors from **asynchronous void methods** when the executor runs that listener.

When a listener has `@Async`, exceptions are caught by the async interceptor after dispatch hands off the task; the global multicaster ErrorHandler might never see exceptions inside the worker. Conversely, submission/rejection errors can appear directly on the dispatch path.

## 19. Why Can't @Async Exceptions Be Caught Directly by assertThrows?

A broken test:

```java
assertThrows(IllegalStateException.class, () -> {
    publisher.publishEvent(new AsyncSignal("A", true));
});
```

In the demo, the listener uses `@Async("eventExecutor")` and returns `void`. `publishEvent` usually schedules the task and returns immediately, so the listener error occurs on the worker thread and is never thrown back into the `assertThrows` lambda. That test will fail even though the listener actually threw and the error handler recorded it.

Proper test:

```java
String id = "case-123";
CompletableFuture<EventProbe.AsyncFailure>
        observed = probe.failure(id);

publisher.publishEvent(new AsyncSignal(id, true));

EventProbe.AsyncFailure failure =
        observed.get(5, TimeUnit.SECONDS);

assertEquals("IllegalStateException",
        failure.exceptionType());
```

This is a **snippet** requiring `publisher`/`probe` injected into the class, plus imports for `CompletableFuture`, `TimeUnit`, and JUnit assertions. It is not a standalone file outside the project. The timeout distinguishes a non-running handler from an infinitely hanging test.

**Watch out for submission errors:** if the executor has shut down or its queue is full, `publishEvent` can throw `TaskRejectedException` before a worker runs. That is a separate failure branch; the main suite does not deliberately induce saturation because tests must stay deterministic.

## 20. Thread Pool Exhaustion, Backpressure, and Rejection

`ThreadPoolTaskExecutor` has several settings to understand:

| Setting | Effect |
| --- | --- |
| `corePoolSize` | Core thread count |
| `maxPoolSize` | Upper thread bound when queue policy triggers |
| `queueCapacity` | Holds tasks waiting for workers |
| `threadNamePrefix` | Aids diagnostics/logging |
| `RejectedExecutionHandler` | Policy when new tasks cannot be accepted |
| Shutdown/await settings | Context stop and task completion |

With the demo's small configuration (`core=2, max=2, queue=16`), sending hundreds of events while workers are blocked can cause task submissions to be rejected. **Do not treat `@Async` as a durable queue**: a bounded executor does not automatically persist or retry tasks.

A separate integration test for rejection can use a deliberately tiny executor, block a worker with a `CountDownLatch`, confirm the worker/queue are full via synchronization, then submit another task and assert `TaskRejectedException`. Afterward release the latch and close the executor. Never use `Thread.sleep` to “guess” the pool is full. In production, choose a rejection policy—fail caller, drop, caller-runs, or backpressure—based on SLAs.

### Common Pitfall with CallerRunsPolicy

If an executor uses `CallerRunsPolicy` to execute tasks directly on the publisher thread under overload, `@Async` processing logic can end up **executing on the caller thread**. Then the assumption “`@Async` always runs on another thread” no longer holds unconditionally. The demo uses the executor's default rejection policy without `CallerRunsPolicy` and submits only a few tasks.

## 21. @Order and Multiple Listeners for the Same Event

`@Order` is meaningful for dispatch order in many situations, yet is not a transaction coordinator:

- Two synchronous listeners with the default multicaster → invoked in `@Order` sequence.
- First listener throws an unchecked exception with no custom ErrorHandler → typically stops subsequent dispatch.
- Custom ErrorHandler suppresses → subsequent listeners can continue.
- Two `@Async` listeners → invocation/submission is ordered, **completion** is not guaranteed.
- Mixed synchronous/async listeners → an async listener may still be incomplete when a later sync listener runs.
- With a custom multicast TaskExecutor → all thread/order assumptions must be re-verified.
- `@TransactionalEventListener` has its own transaction synchronization semantics; see Section 24.

If there is a business dependency “must generate report before sending email”, do not build two independent async listeners hoping `@Order` guarantees it. Use explicit orchestration, a transactional outbox, or an acknowledged workflow.

## 22. When to Use @RecordApplicationEvents?

Spring TestContext provides:

```java
@RecordApplicationEvents
@SpringBootTest
class PublishingTest {

    @Test
    void publishesOrderEvent(ApplicationEvents events) {
        // Call service to publish...
        long count = events.stream(SyncSignal.class)
                .filter(e -> "ORDER-1".equals(e.id()))
                .count();
        assertEquals(1L, count);
    }
}
```

This is a **structural snippet**; it needs a service/publisher and matching event to actually emit "ORDER-1". The project already includes a complete method using `ApplicationEvents`. The annotation is `org.springframework.test.context.event.RecordApplicationEvents`, and the parameter is `org.springframework.test.context.event.ApplicationEvents`.

### What Does It Measure?

`ApplicationEvents` records events published within the scope of a test, useful for verifying whether a service publishes the right event type/payload. It does not by itself prove:

- The listener finished.
- An async handler consumed the message on a worker.
- The business DB transaction committed.
- A downstream Kafka message was ACKed.
- The event was persisted for replay.

In async event tests, the recorder and listener can belong to different thread-locals/contexts. Thus a bounded probe or business outcome is a much safer way to assert **processing**. Do not use `ApplicationEvents.stream(...).count()==1` as proof that an async callback succeeded.

### When Should You Mock the Publisher?

If a service unit test only needs to prove `publisher.publishEvent(new MyEvent(...))` was called with the right payload, mocking `ApplicationEventPublisher` with Mockito can be fast. However, do not mock the publisher in tests checking Spring `@EventListener` wiring, because real dispatch would never happen.

## 23. Exception Contracts and Business Error-Handling Branches

A solid event producer/consumer design must answer:

1. If a synchronous listener fails, must the **business command** fail?
2. With multiple independent listeners, should listener A failing block listener B?
3. If an async listener fails, who handles retries/alerts?
4. Are timeouts, deduplication, or exactly-once side effects required?
5. Is the event published before or after database commit?
6. Can events be lost during JVM shutdown/crash?
7. How must event ID/tenant/trace ID be tracked?
8. Which error types should fail fast and which are retryable?

### Typical Policies

| Use Case | Potentially Suitable Policy | Mandatory Tests |
| --- | --- | --- |
| Synchronous domain validation before commit | Fail fast | Error propagates; business data not committed |
| Non-critical best-effort metrics/audit | Suppress after recording/alerting | Publisher still succeeds; error signal recorded |
| Async email notification | Retry/outbox when reliability needed | Failure recorded + retry/idempotency |
| Mandatory compliance audit | Transactional/outbox, no silent drop | Business cannot “succeed” if audit isn't guaranteed |
| Cache invalidation | Async and eventual consistency | Bounded wait for state update, recovery on fail |
| Projection/event sourcing | Durable event store | Ordering/version/concurrency + replay tests |

**Do not turn every exception into log-only.** A compliance or data integrity error must not be treated like a best-effort performance metric. Base the policy on product requirements, then protect that result with tests.

## 24. @TransactionalEventListener: Branching by Commit or Rollback

`@TransactionalEventListener` differs from a normal `@EventListener`. It registers a callback bound to a transaction phase:

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderPlaced event) {
    // Side effect only after a successful transaction commit.
}
```

This is a **snippet**, not part of the runnable project since the project lacks a DataSource/transaction manager. Four common phases exist:

| Phase | When It Runs |
| --- | --- |
| `BEFORE_COMMIT` | Before transaction commit |
| `AFTER_COMMIT` | After successful commit (default) |
| `AFTER_ROLLBACK` | After rollback |
| `AFTER_COMPLETION` | After transaction finishes, whether commit or rollback |

By default, when no active transaction exists, a transactional listener **is not invoked** because `fallbackExecution=false`. With `fallbackExecution=true`, it can be invoked even outside a transaction; tests must define the expected policy rather than using fallback to hide a broken transaction boundary.

### Standard Test Pattern for AFTER_COMMIT

- Use a real test DB/transaction manager.
- Publish the event **inside a transaction**.
- Before commit: the AFTER_COMMIT listener has not run yet.
- Commit the transaction: the listener runs.
- In the rollback scenario: the AFTER_COMMIT listener does not run; an AFTER_ROLLBACK listener can run.
- Use `TransactionTemplate` or explicit programmatic commit/rollback control; do not assume `@Transactional` on a test method (which normally rolls back at the end) triggers after-commit callbacks.
- Assert business side effects at the appropriate transaction boundary.

Snippet with `TransactionTemplate`:

```java
transactionTemplate.executeWithoutResult(status -> {
    publisher.publishEvent(
            new OrderPlaced("ORDER-100"));
});

// After template commits, verify AFTER_COMMIT outcome.
```

This snippet needs an `OrderPlaced` class and injected `transactionTemplate/publisher`; it is not standalone runnable. When the DB transaction rolls back, `AFTER_COMMIT` does not run by default. **Do not create a fake transaction and assert only the listener callback** if the real question is commit behavior.

### Combining @Async + @TransactionalEventListener

You can annotate a transactional listener with `@Async` to run **after commit** on a worker, but the publisher's thread-bound transaction context does not move to the worker. Handlers should not rely on lazy-loaded JPA entities outside a session or assume they remain inside the old transaction. For transaction-bound listeners combined with a custom global multicaster executor, Spring 6.1 has specific synchronization protections—test against your exact version. When high reliability is needed, an outbox is usually clearer than a non-durable after-commit callback.

## 25. Observability: Logs, Metrics, Tracing, and Correlation

Since the group includes **observability**, beyond “did the listener run?” design production observability carefully:

- **Structured logs**: event type, correlation/business ID, outcome, retry count, elapsed time, categorized error. Never log PII/credential payloads.
- **Metrics**: events published, listeners succeeded/failed, executor active/queued/rejected, processing duration, retry/dead-letter counts.
- **Distributed tracing**: spans or observations for tracked business operations, linking producer/handler/HTTP/DB where applicable.
- **Audit state**: when business requires it, record a durable outcome rather than relying solely on a metric that could be lost.
- **Alerts**: rising failure rate, saturated queues, processing latency breaching SLO, slow worker shutdown.

### Spring Does Not Automatically Create an Observation per @EventListener

Spring Framework observability docs note that **application event publication/listening does not act as a separate observation by default**. Synchronous listeners default to the same thread, so ThreadLocals/MDC can see the publisher's context. When dispatch crosses onto an executor/another thread, MDC/tracing context is **not automatically guaranteed**.

If the project uses Micrometer Context Propagation, consider `ContextPropagatingTaskDecorator` (Spring Framework 6.1) on the corresponding TaskExecutor along with required dependencies; test trace IDs/log context across the async boundary. TaskDecorators add overhead; do not enable them just for prettier logs without evaluating performance and propagation policy.

**The lab project** only asserts thread ID and event ID, without pretending a Micrometer ObservationRegistry is configured. To test real spans/metrics, add Actuator/Micrometer test setup and assert against a test registry or explicitly configured observation handlers.

### Metrics Are Not Proof of Business Commit

Incrementing a `listener.success` counter before a DB write commits can mislead. Place metrics at points matching their exact semantics, distinguishing `received`/`started`/`completed`/`committed`/`failed`. Measure metrics alongside asserting critical business state if correctness depends on it.

## 26. Logging Context Across @Async and Security Context

ThreadLocals, MDC (Mapped Diagnostic Context), and SecurityContext have thread-bound lifecycles:

- Default synchronous listeners run on the caller thread, so they see current MDC and thread-local transactions.
- `@Async` listeners execute on a worker pool and **do not inherit all thread-local contexts by default**.
- If SecurityContext propagation is required, use `DelegatingSecurityContextAsyncTaskExecutor` or Spring Security's equivalent under an explicit policy.
- If trace/MDC propagation is required, use a Micrometer context-propagation TaskDecorator or a version-supported logging/tracing solution.
- Never copy mutable thread-local objects into workers without cleanup; thread pool reuse can leak context across requests/users.
- In reactive apps, context normally resides in the Reactor Context rather than ThreadLocal; event listener tests require a different strategy.

Do not write a unit test claiming “context propagated successfully” just by asserting a thread name or placing a trace ID inside the record; those are two separate concerns. Event IDs in payloads provide **business correlation**, whereas trace/MDC context propagation is an infrastructure concern.

## 27. Event Publication, Asynchronous Transactions, and Idempotency

An event can be published multiple times due to:

- Caller retrying a command after a timeout.
- Transaction rolling back and the service republishing.
- Duplicate event callback registration.
- A listener publishing another event.
- Tests/ApplicationContext registering duplicate listener beans.
- Restarts/replays from an external broker/outbox.

Because application events themselves have no deduplication, idempotency must be built **at the side-effect boundary** whenever redelivery is possible. For financial transactions, emails/notifications can use dedup keys; DB writes need unique constraints or a processed-event ledger per business policy.

### Testing Duplicate Events

A domain-level test can publish the same event ID twice and assert only one side effect **if the implementation includes an idempotency guard**. The lab project has **no** idempotency guard, so do not attach “exactly once” expectations to the current tests. To extend it, add a repository/store, handle concurrent races on the same ID across workers, and test uniqueness.

### Retries Do Not Happen Automatically via @Async

`@Async` schedules a method; it does not retry when the method throws. `AsyncUncaughtExceptionHandler` is not a retry orchestrator. If retries are needed, use Spring Retry/Resilience4j or a retry-capable queue/outbox, and test attempt counts/backoff/idempotency. Never publish twice in a test and call it framework retry.

## 28. Failure Scenarios to Test Beyond the Lab Project

| Scenario | What to Prove | Tools |
| --- | --- | --- |
| Sync listener throws runtime exception | Publisher gets error; later listener runs/skips per policy | `assertThrows` + trace stages |
| Async void listener throws | Handler receives right ID/cause | CompletableFuture/latch with timeout |
| Executor rejects | Caller receives expected error without silent drop | Controlled saturation via latch |
| Context shuts down with pending tasks | Resource cleanup / await policy | Lifecycle test + bounded shutdown |
| Handler catches and suppresses error | Metrics/error sink still records it | Fake error sink + assertions |
| Async listener loses tracing MDC | Propagation config works properly | Test TaskDecorator/context |
| Transaction rolls back | AFTER_COMMIT does not run | Real transaction manager + TransactionTemplate |
| Transaction commits | AFTER_COMMIT runs after commit | Real DB transaction + observable result |
| DB write fails after “success” event | Outcome measured at commit point | Repository state + transaction semantics |
| Duplicate event ID | Idempotency policy enforced | Real DB constraint/dedup store |
| Wrong listener `@Order` | Sync order changes | Recording probe stages |
| Two `@Async` listeners | Do not assume completion order | Correlation-aware outcomes |
| Custom global ErrorHandler | Suppresses/propagates per policy | Multicaster policy test + context test |
| Event published in controller tx | Proper exception status mapping/rollback | MVC + transactional integration |
| Global multicaster executor + transactional listener | Transaction semantics preserved | Version-appropriate test + DB |

The lab suite covers the core axes with 11 tests, without pretending to cover every topology, network, or infrastructure combination.

## 29. Common Mistakes and How to Fix Them

| Symptom | Common Cause | Check / Fix |
| --- | --- | --- |
| Listener not invoked | Bean not scanned, wrong event type, wrong context | Check package, `@Component`, `@EventListener` |
| Sync test misses exception | Custom global `ErrorHandler` suppresses | Inspect multicaster configuration/policy |
| Async listener runs on test thread | Forgot `@EnableAsync`, proxy bypass, inline executor | Named pool + thread prefix assertion |
| `assertThrows` test fails for async | Exception thrown on worker, doesn't return to caller | Error signal/handler with timeout |
| Test occasionally times out | Using sleep, saturated pool, deadlock | Bounded future + diagnostics |
| Test PASSES yet handler never ran | Only asserted `publishEvent` returned | Await outcome/side effect |
| `@RecordApplicationEvents` sees event yet business unchanged | Recorder only observes publish | Assert listener/business output |
| `@Order` set yet async completion reversed | Scheduler/threads have no global order | Assert by correlation ID |
| Throwable logged without retry | `AsyncUncaughtExceptionHandler` is not a retry system | Design retry/outbox |
| Worker fails yet application returns 200 | Caller responded before async processing | Match semantics or make synchronous? |
| Executor shutdown triggers rejections | Out-of-sync context/test lifecycle | Use managed executor, bounded shutdown |
| EventProbe retains old records | Shared IDs/probe across tests | UUID/fixture isolation; cleanup by ID |
| Transactional listener outside tx doesn't run | `fallbackExecution=false` | Test inside real transaction |
| AFTER_COMMIT listener skips in `@Transactional` rollback test | No commit occurred | Commit with TransactionTemplate |
| Log MDC lost in worker | ThreadLocal doesn't propagate automatically | TaskDecorator/context propagation |
| Failed metric increments with no error logs | Async handler swallow/log policy | Assert error sink and logging config |
| Payload event serialization error | In-process POJO events need no default JSON serialization | Don't confuse with broker transport |
| Spring listener “runs twice” | Duplicate bean/listener registration | Inspect context/components and events |
| `@Async` listener return value event isn't published | Async `@EventListener` doesn't support return-value publication | Inject publisher and publish explicitly |
| Checked exception gets wrapped | Adapter cannot propagate checked directly | Assert expected wrapper per API |
| `@Async` listens to event without executor | Default executor selection differs from intent | Use `@Async("eventExecutor")` |
| Test overly constrained on elapsed ms | CI scheduling is non-deterministic | Assert thread/outcome, bounded timeout |

### 8-Step Debugging Process

1. Confirm the event record/class, publisher, and listener live in the same Spring ApplicationContext.
2. Check that the `@EventListener` method signature accepts the exact event type.
3. Check whether the app defines a custom `applicationEventMulticaster`, TaskExecutor, or ErrorHandler.
4. For async, confirm `@EnableAsync`, Spring-managed bean/proxy, and `@Async("eventExecutor")`.
5. Verify the listener was invoked via event ID/logs/tracing, not merely response status.
6. Separate failures occurring on the publisher thread, at task submission, or inside the worker.
7. For async, await completion/error signals with a timeout and inspect the exact root cause.
8. For transactions/outbox/brokers, assert commit/retry/durable state via integration tests rather than inferring from an in-memory probe.

## 30. Running Tests and Reading Results Properly

When the project has a generated Gradle Wrapper:

```bash
./gradlew test --tests 'com.example.events.EventListenersTest'
./gradlew test --tests 'com.example.events.MulticasterPolicyTest'
./gradlew test
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
```

When a compatible Gradle is installed without a Wrapper:

```bash
gradle test
```

JUnit/Gradle reports typically appear at:

```text
build/reports/tests/test/index.html
build/test-results/test/
```

The sample source contains **11 `@Test` methods**, comprising 9 integration tests and 2 standalone multicaster tests. That is the **method count in source**, not an observed PASS count. Gradle was not executed while writing this lesson; do not claim the suite actually passed.

### No Fixed Stdout

The tests never call `System.out.println`. Spring Boot/Gradle logs and worker thread IDs vary by environment. Reliable evidence is the test report showing successful/failed/skipped counts from a real run with zero failing assertions. On timeouts, stack traces in the report should identify the event ID and awaited future; never bump sleeps to mask issues.

## 31. Practical Exercises

1. Run `syncListenersRunInOrderOnPublisherThread` and verify both handlers run on the caller thread.
2. Remove `@Order` from listeners in a sandbox and examine why an ordering assertion can become unstable.
3. Set `fail=true` and observe `assertThrows` at the publisher with a synchronous listener.
4. Configure the global multicaster `setErrorHandler(TaskUtils.LOG_AND_SUPPRESS_ERROR_HANDLER)` in a **separate** test context and compare policies with the default.
5. Remove `@EnableAsync` in a sandbox and use the thread-prefix test to catch the regression.
6. Remove the `"eventExecutor"` qualifier on `@Async` and inspect which actual executor gets chosen.
7. Invoke the `@Async` listener method directly from within the same bean and analyze self-invocation and proxies.
8. Send a successful async event, await the future, and assert correlation ID/thread.
9. Send a failing async event and verify `AsyncUncaughtExceptionHandler` records the method/cause.
10. Try putting `assertThrows` directly around `publishAsync` and explain why it does not catch the worker exception.
11. Configure a tiny pool, block tasks with a latch, induce controlled rejection, and assert `TaskRejectedException`.
12. Add a second async listener and verify you cannot rely on `@Order` for fixed completion order.
13. Add a `@TransactionalEventListener(AFTER_COMMIT)` with H2 and `TransactionTemplate`, verifying it runs only after commit.
14. Try `fallbackExecution=true` and publish outside a transaction to inspect the new policy.
15. Test an after-rollback event with a real transaction and observe the right listener running.
16. Add business DB state and avoid treating `EventProbe.markAsyncSuccess` as transaction commit.
17. Add `@RecordApplicationEvents` to a publisher test, distinguishing recorded publication from listener completion.
18. Use `ApplicationEvents.stream(...)` to assert the event payload has the right ID, without using it as an async completion gate.
19. Add a TaskDecorator/context propagation and test MDC/trace ID on the `event-worker` thread.
20. Add an idempotency layer with unique event IDs and run two duplicate-ID events concurrently.
21. Shut down the context/executor while tasks are still pending to find failure behavior that needs monitoring.
22. Run each test and the full suite, reading real JUnit reports rather than predicting PASS.

## 32. Pre-Merge QA Checklist

- [ ] Distinguished synchronous `@EventListener`, `@Async @EventListener`, and custom multicaster executors?
- [ ] Real event publisher and listeners are managed by Spring?
- [ ] `@EnableAsync` is enabled for methods intended to be async?
- [ ] Named executor is selected explicitly when needed?
- [ ] Sync tests check callbacks, ordering, and caller thread?
- [ ] Sync failure tests assert exceptions at the publisher boundary?
- [ ] Tests cover whether later listeners stop or continue per ErrorHandler policy?
- [ ] Async tests await completion/errors with a finite timeout?
- [ ] No `Thread.sleep`/timing thresholds used as readiness gates?
- [ ] Async failure tests **do not** expect exceptions thrown directly from `publishEvent`?
- [ ] `AsyncUncaughtExceptionHandler` records cause/method/event ID accurately?
- [ ] Distinguished task rejection from worker exceptions?
- [ ] Tests do not assume global completion order across `@Async` listeners?
- [ ] Tests cover both success and error branches of each critical event type?
- [ ] `@RecordApplicationEvents` is used solely to assert publication, not processing?
- [ ] Correlation IDs do not collide across tests?
- [ ] Test probes do not alter business semantics or mask DB rollbacks?
- [ ] If using `TransactionalEventListener`, tested commit/rollback/no-transaction?
- [ ] Avoided `@Transactional` test rollback while expecting AFTER_COMMIT to run?
- [ ] If the app uses retries, tested attempt counts/idempotency/recovery policy separately?
- [ ] No static mutable state or global System properties causing test pollution?
- [ ] With a global multicaster ErrorHandler, tested suppress/propagate separately?
- [ ] Micrometer observations/metrics are genuinely instrumented when tested, not assumed built-in?
- [ ] Trace/MDC/SecurityContext propagation across threads verified if part of SLAs?
- [ ] Logs/metrics/error probes never leak secrets/PII?
- [ ] Verified against Spring Framework 6.1/Boot 3.3 APIs?
- [ ] Executed Gradle/CI for real before claiming tests PASS?

## 33. Official References

- [Spring Framework 6.1 — Application Events and Listeners](https://docs.spring.io/spring-framework/reference/6.1/core/beans/context-introduction.html): event publishing, `@EventListener`, synchronous listeners, `@Async`, and ordering.
- [Spring Framework 6.1 — EventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/EventListener.html): exceptions, async limitations, listener return values.
- [Spring Framework 6.1 — SimpleApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html): default thread, `setTaskExecutor`, and `setErrorHandler`.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@EnableAsync`, `@Async`, `AsyncConfigurer`, and executor options.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener`, transaction phases, and fallbackExecution.
- [Spring Framework — Application Events Testing](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html): `@RecordApplicationEvents` and `ApplicationEvents`.
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): Spring application events and observation semantics, context propagation.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): SpringBootTest, test lifecycle, and dependency management.
- [Spring Framework — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): pool settings and lifecycle.
- [JUnit Jupiter User Guide](https://junit.org/junit5/docs/current/user-guide/): `@Test`, assertions, and independent test methods.

## 34. Conclusion

**Testing event listeners requires pinpointing exactly where the event is processed and where errors surface.** With a default synchronous `@EventListener`, publisher and listener share the same thread; `assertThrows` at the publisher checks exceptions, while `@Order`/probes verify ordering and early termination. With `@Async @EventListener`, execution moves to an executor; test using completion/error signals keyed by event ID with **finite timeouts**, using `AsyncUncaughtExceptionHandler` for errors from asynchronous void methods rather than expecting exceptions from ordinary publisher calls.

Do not confuse **AsyncUncaughtExceptionHandler** with a global **ApplicationEventMulticaster ErrorHandler**, or confuse `@RecordApplicationEvents` (published) with completed business processing. When events tie into transactions, test `@TransactionalEventListener` against real commits and rollbacks. When production needs tracing, MDC, and durable error/retry handling, add appropriate context propagation, metrics, and outbox/broker integration tests. The Java 17+ / Spring Boot 3.3.5 codebase provides 11 illustrative test methods as a foundation, while actual PASS counts must be verified from a real Gradle/CI report rather than inferred from the lesson text.
