# Publisher Waits for Listeners to Finish in Synchronous Event Processing

In Spring Framework Application Events, the statement `publisher.publishEvent(event)` often looks like a simple "send notification" operation. Under the default synchronous dispatch configuration, however, it is a **blocking call**: Spring invokes matching listeners directly on the publishing thread, and `publishEvent(...)` returns normally only after those synchronous listeners have finished executing. If a listener runs slowly, the publisher waits too; if a listener throws an exception and no custom exception handler is configured, the publish call can throw that exception.

This is an important characteristic concerning **timing, performance, errors, and transactions**. Understanding it accurately prevents assuming that "published" is equivalent to "offloaded to the background."

## 1. How Does the Default Behavior Work?

In a typical `ApplicationContext`, when you do not replace or reconfigure the event multicaster, Spring uses `SimpleApplicationEventMulticaster` to deliver events to listeners. By default, the multicaster executes listeners synchronously on the **caller's thread**; in practical terms, this behaves equivalently to using `SyncTaskExecutor`.

```text
Business execution thread
        |
        | 1. service calls publisher.publishEvent(event)
        v
ApplicationEventPublisher
        |
        v
ApplicationEventMulticaster (default: synchronous)
        |
        | 2. invokes listener A ----------------+
        |                                      | A finishes executing
        | <------------------------------------+
        | 3. invokes listener B ----------------+
        |                                      | B finishes executing
        | <------------------------------------+
        | 4. returns control to publisher
        v
Statement after publishEvent(...)
```

The diagram assumes listeners are called and **return normally**. Listener ordering can be influenced by `@Order`, but the main focus here is that **the publish call waits on the same thread**. You should not interpret the diagram as a guarantee that every system, every bean, or every listener configuration runs sequentially.

The contract can be stated precisely:

> When using the default synchronous multicaster and synchronously executed listeners, if `publishEvent(...)` returns normally, then the bodies of the synchronous listeners invoked by the multicaster for that event have finished.

The contract does **not** automatically guarantee that a database transaction has committed, that background tasks spawned by a listener itself have completed, that a message has reached an external system, or that `@TransactionalEventListener(AFTER_COMMIT)` listeners have executed.

### Three Things to Distinguish

| Observation | What does it mean in the default synchronous setup? | What cannot be inferred |
| --- | --- | --- |
| Listener is invoked | Spring is executing the event-handling method on the publishing thread | That the listener succeeded if it is still running or throws an error |
| `publishEvent` returns **normally** | Synchronous listeners were invoked and finished without letting an exception escape | That the transaction committed; that internal async work finished |
| `publishEvent` throws an exception | At least one step along the dispatch path had an unhandled error | That all listeners ran; that effects prior to the error were rolled back |

## 2. Java 17+ Example: Seeing Order Before and After `publishEvent`

Create a minimal Gradle project with the two source files below. The example uses Spring Framework 6.2.x; the `ApplicationEventPublisher`, `@EventListener`, and `AnnotationConfigApplicationContext` APIs are also familiar in Spring Boot projects.

**`settings.gradle`**

```groovy
rootProject.name = 'sync-application-events'
```

**`build.gradle`**

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'

    testImplementation 'org.springframework:spring-test:6.2.9'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

application {
    mainClass = 'example.events.SyncEventDemo'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

**`src/main/java/example/events/SyncEventDemo.java`**

```java
package example.events;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class SyncEventDemo {

    record InvoiceIssued(String invoiceId) { }

    static class InvoiceListener {
        @EventListener
        public void onInvoiceIssued(InvoiceIssued event) {
            System.out.println("2. Listener started: " + event.invoiceId());
            System.out.println("3. Listener finished: " + event.invoiceId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {
        @Bean
        InvoiceListener invoiceListener() {
            return new InvoiceListener();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            System.out.println("1. Before publish");
            context.publishEvent(new InvoiceIssued("HD-01"));
            System.out.println("4. After publish");
        }
    }
}
```

Run with JDK 17+ and the project's Gradle wrapper:

```bash
./gradlew run
```

On Windows PowerShell, use `./gradlew.bat run`. The four lines produced by `System.out.println` in the example appear in order:

```text
1. Before publish
2. Listener started: HD-01
3. Listener finished: HD-01
4. After publish
```

Line 4 can only run after `onInvoiceIssued` finishes in this configuration. No `Thread.sleep`, no manual thread creation, and no need for the listener to extend `ApplicationEvent`: Spring supports publishing plain Java objects, such as the `InvoiceIssued` record.

**Step-by-step explanation:**

1. `AnnotationConfigApplicationContext` initializes the context and registers the `InvoiceListener` bean.
2. `@EventListener` makes `onInvoiceIssued` subscribe to events of type `InvoiceIssued`.
3. `context.publishEvent(...)` goes through the context's multicaster; since no asynchronous executor is configured, the listener runs on the same thread.
4. The listener method prints two lines and returns `void`; only then does `publishEvent(...)` return and the line after publish execute.
5. The context is closed at the end of the `try` block to release resources.

This example demonstrates **control flow order**, not blocking duration. A listener making an HTTP call, querying a database, or waiting on a lock can substantially increase the elapsed time from line 1 to line 4.

## 3. Actually Testing That the Publisher Waits

A test that only compares log line order is useful, but you can make it stronger: actively **hold the listener mid-execution** and confirm `publishEvent` has not returned yet. `CountDownLatch` provides explicit synchronization points without relying on "sleeping" for some number of milliseconds.

Create **`src/test/java/example/events/PublisherWaitsTest.java`**:

```java
package example.events;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(PublisherWaitsTest.Config.class)
class PublisherWaitsTest {

    @Autowired
    ApplicationEventPublisher publisher;

    @Autowired
    Gate gate;

    record WorkRequested(String id) { }

    static class Gate {
        final CountDownLatch listenerEntered = new CountDownLatch(1);
        final CountDownLatch allowListenerToFinish = new CountDownLatch(1);
        final AtomicBoolean finished = new AtomicBoolean(false);
        final AtomicReference<Thread> listenerThread = new AtomicReference<>();
    }

    static class BlockingListener {
        private final Gate gate;

        BlockingListener(Gate gate) {
            this.gate = gate;
        }

        @EventListener
        public void on(WorkRequested event) {
            gate.listenerThread.set(Thread.currentThread());
            gate.listenerEntered.countDown();

            try {
                if (!gate.allowListenerToFinish.await(30, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Listener timed out");
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Listener interrupted", ex);
            }

            gate.finished.set(true);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {
        @Bean
        Gate gate() {
            return new Gate();
        }

        @Bean
        BlockingListener blockingListener(Gate gate) {
            return new BlockingListener(gate);
        }
    }

    @Test
    void publishWaitsForSynchronousListener() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        AtomicReference<Thread> publishingThread = new AtomicReference<>();

        try {
            Future<?> publication = executor.submit(() -> {
                publishingThread.set(Thread.currentThread());
                publisher.publishEvent(new WorkRequested("JOB-7"));
            });

            // Wait until the listener has been invoked and is waiting to be released.
            assertTrue(gate.listenerEntered.await(5, TimeUnit.SECONDS));

            // The listener has not finished yet, so publishEvent has not returned either.
            assertFalse(gate.finished.get());
            assertFalse(publication.isDone());

            // Allow the listener to return; only now can the publisher complete.
            gate.allowListenerToFinish.countDown();
            publication.get(5, TimeUnit.SECONDS);

            assertTrue(gate.finished.get());
            assertSame(publishingThread.get(), gate.listenerThread.get());
        } finally {
            // Release the listener even if an assertion fails.
            gate.allowListenerToFinish.countDown();
            executor.shutdownNow();
        }
    }
}
```

Run just this test:

```bash
./gradlew test --tests "example.events.PublisherWaitsTest"
```

**Expected result:** the test passes. This is a JUnit test, so there is no required business stdout string; Gradle reports that the test task succeeded. The test proves two points:

- While the listener is waiting on `allowListenerToFinish`, `publication.isDone()` remains `false`. That means `publish` is still blocked in the synchronous dispatch path.
- After `countDown()`, `publication.get(...)` completes, and `assertSame` proves the listener ran on the exact thread executing the publish call, not on the external JUnit observer thread.

**Why create an executor in the test at all?** The executor here only moves **the entire publish call** onto a separate thread so the JUnit thread can observe it while blocked. This executor **does not configure** `ApplicationEventMulticaster` to be async. Those are two different concepts. The test has timeouts so that if the listener fails, CI fails fast instead of hanging indefinitely. The latches and atomic flags enable cross-thread observation with clear memory visibility boundaries.

This test targets the **default synchronous dispatch configuration**; if a project intentionally switches to async, the behavior to test will differ.

## 4. A Slow Listener Slows Down the Publisher

Suppose an HTTP request handler runs:

```java
orderRepository.save(order);
publisher.publishEvent(new OrderCreated(order.getId()));
return ResponseEntity.accepted().build();
```

This is only a **snippet** inside a controller/service, not a standalone program. If there are two synchronous listeners, one taking about 150 ms and another taking about 250 ms, those handlers alone add roughly 400 ms total to the publish duration (excluding other overhead). These numbers are **hypothetical calculation examples**, not real performance guarantees.

Common consequences:

- API responses slow down because they wait for secondary tasks like sending email, writing audit logs, or calling external services.
- Request-handling threads stay tied up; high traffic can exhaust server worker threads.
- A listener experiencing hung I/O or long timeouts inflicts the same latency on the publisher.
- Later listeners can be affected if an earlier listener throws an error.

However, **intentional** synchronous processing is also useful. For example, a listener may need to update a mandatory internal state before the service proceeds, and the system wants to receive an error directly if that step fails. In that case, evaluate whether the logic belongs directly in the orchestrating service or truly fits a synchronous event.

## 5. Exceptions: How a Listener Failure Affects the Publisher

By default in `SimpleApplicationEventMulticaster`, if a synchronous listener throws an unchecked exception and it goes unhandled, the exception propagates back to the caller of `publishEvent`. Therefore, statements after publish may **not be executed**.

Illustrative listener snippet:

```java
@EventListener
public void on(InvoiceIssued event) {
    throw new IllegalStateException("Cannot update invoice index");
}
```

With the default synchronous multicaster, the caller can catch the error:

```java
try {
    publisher.publishEvent(new InvoiceIssued("HD-01"));
    // Not reached when the listener error is unhandled.
} catch (IllegalStateException ex) {
    // Application decides how to handle the business error.
}
```

Both snippets are **illustrative code** that belong inside beans with proper declarations and imports. You must not generalize that *every listener* finished when `publish` throws an exception: the multicaster can stop dispatching to remaining listeners. The exact behavior depends on `ErrorHandler` configuration, listener ordering, and the dispatch mechanism. A custom `ErrorHandler` may log and swallow exceptions; in that case, `publishEvent` returning normally **does not prove every listener succeeded**.

In particular, if an earlier listener already updated a database or called an external service before the next listener failed, that work is **not automatically undone**. Undoing work depends on transactions and the nature of the side effects; an email or outbound HTTP request cannot be rolled back merely by `publishEvent`.

## 6. Common Trap: "Synchronous" Does Not Mean "Committed"

If `publishEvent` is called **inside** a `@Transactional` method, an ordinary `@EventListener` can run immediately on the same thread and inside the same transaction context before the transaction commits. The event is processed synchronously, yet the database can still roll back afterward.

Consider this illustrative structure:

```java
@Transactional
public void createOrder(Order order) {
    orderRepository.save(order);
    publisher.publishEvent(new OrderCreated(order.getId()));
    // The transaction has usually not committed at this point.
}
```

If a listener sends an email immediately upon receiving the event, the user might receive a notification about an order that is later rolled back. When the requirement is **to act only after a successful commit**, use a more suitable mechanism:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendReceipt(OrderCreated event) {
    notificationGateway.send(event.orderId());
}
```

These snippets are illustrative only; real `Order`, `OrderCreated`, repository, gateway, and transaction manager components are required. When an active transaction exists, the `AFTER_COMMIT` listener body is bound to the **post-commit** phase, so calling `publishEvent` inside the transactional method **does not wait for this callback body to finish at publish time**. Without an active transaction, this kind of listener does not run by default unless `fallbackExecution = true` is set.

Distinguish clearly:

| Listener | Typical execution timing | Does `publishEvent` wait for the listener body? |
| --- | --- | --- |
| `@EventListener`, default synchronous | Immediately when the event is published | Yes, if the listener returns normally |
| `@TransactionalEventListener(AFTER_COMMIT)` inside an active transaction | Upon post-commit callback | Does not wait for the **callback body** at publish time |
| `@Async @EventListener` with async enabled | Scheduled as a background task | No guarantee of waiting for the background task to complete |
| Listener on a multicaster with an asynchronous executor | On the executor, depending on whether the listener supports async | No guarantee of waiting for work submitted to the executor |

In modern Spring Framework, transaction-synchronized listeners may require immediate dispatch on the original thread to **register** the transaction callback; that does not turn an `AFTER_COMMIT` callback body into work completed immediately inside `publishEvent`.

## 7. Configurations That Change the Blocking Behavior

### A. Using `@Async` on a Listener

```java
@Async
@EventListener
public void sendNotification(OrderCreated event) {
    notificationGateway.send(event.orderId());
}
```

This example requires Spring async support to be enabled, such as `@EnableAsync`, along with an appropriate executor. `publish` can then complete right after handing the call off to the async mechanism while the `sendNotification` body continues running. Exceptions from async listeners do not automatically propagate back to the publisher; they must be handled or monitored separately (for instance via `AsyncUncaughtExceptionHandler`, appropriate `Future` handling, or a retry mechanism).

### B. Configuring an Executor on the Multicaster

Spring lets you define a bean named `applicationEventMulticaster` using a `SimpleApplicationEventMulticaster` configured with a `TaskExecutor`. This can dispatch async-capable listeners onto another thread instead of invoking them directly; **a scheduled task does not mean a completed task**. Some listeners, especially transaction-bound ones, may require running on the original thread to preserve context; do not assume all listeners move to the executor.

### C. Listener Spawns Background Work Itself

Even with a synchronous multicaster, if a listener simply calls `executor.submit(...)` and returns, the publisher only waits for **the listener to return**, not for the submitted task. The synchronous rule applies at the *listener invocation boundary*, not to external work launched outside that boundary by the listener.

### D. Distributed Systems

`ApplicationEventPublisher` is an in-process event mechanism inside a Spring `ApplicationContext`. It is not a distributed message broker and does not guarantee that an external system has received or persisted data. Reliable delivery across processes or networks requires dedicated mechanisms such as a transactional outbox, a broker, acknowledgments, idempotency, and retries.

## 8. Design Options When the Publisher Should Not Wait

The choice should come from business semantics:

| Need | Commonly suitable option | Trade-off |
| --- | --- | --- |
| Mandatory step needed to return an accurate immediate result | Explicit service call or synchronous event listener with a clear contract | Increases publisher latency; errors propagate directly |
| Secondary task that need not finish before the HTTP response | `@Async` or an appropriate queue | Requires retries, error observability, and completion timing awareness |
| Task that must happen only after commit | `@TransactionalEventListener(AFTER_COMMIT)` | Tied to commit; does not guarantee delivery across crashes by itself |
| Event that must survive service restarts/crashes | Outbox + broker/worker, delivery, and idempotency | Adds infrastructure and processing state |
| Sequence of mandatory ordered steps | Service orchestration or explicit chained events | Increases clarity, reduces hidden coupling between listeners |

Do not add async just to reduce latency while ignoring error visibility or failures. Conversely, do not keep slow tasks on a request thread if the user does not need to wait for them to finish.

## 9. Testing Different Requirements

**Requirement: publisher must wait for synchronous listener completion.** Use the latch test in section 3. Assert that the publish `Future` is not done while the listener is held, and completes after releasing the gate.

**Requirement: exceptions must propagate back to the publisher.** Create a listener throwing `IllegalStateException`; call `assertThrows(IllegalStateException.class, () -> publisher.publishEvent(event))` in the default context. Do not use an `@Async` listener for this kind of test.

**Requirement: background secondary listener does not block the HTTP response.** Use a latch to confirm the task started and a timeout mechanism to observe completion. When testing an async flow, prove the response does not depend on completion rather than asserting a fixed thread order.

**Requirement: send notifications only after commit.** Use an integration test with a real transaction manager; verify nothing is sent before commit, it is sent after commit, and nothing is sent on rollback. Note that `@Transactional` tests usually roll back by default; use `TransactionTemplate` or `TestTransaction` to control commits.

**Requirement: all listeners succeed.** Test the effects of each listener and failure branch. Simply observing `publishEvent` return normally is insufficient when using a custom `ErrorHandler`, async, or listeners that schedule other tasks.

## 10. Common Mistakes

1. **Thinking publish puts work on a queue.** Under the default synchronous configuration, Spring runs listeners directly on the calling thread; the publisher pays the entire execution time.
2. **Measuring with `Thread.sleep` in tests.** Sleep depends on OS scheduling and CI load. `CountDownLatch` or synchronization primitives with timeouts reflect verifiable happens-before relationships.
3. **Believing publish returning means the database committed.** The transaction may still be open; ordinary listeners and `AFTER_COMMIT` listeners execute in different phases.
4. **Believing waiting for the listener means waiting for all background I/O.** A listener can submit a task and return; the publisher does not track that spawned work.
5. **Ignoring exceptions or blocking time.** Unreliable listeners can slow requests or abort the listener chain; you need timeouts, metrics, an error strategy, and clear transaction design.
6. **Confusing the thread creating the publisher with the test method thread.** In the latch test, the publish call runs on the executor thread; the synchronous listener runs on that same executor thread, while the JUnit thread only observes.
7. **Mistaking `@Order` for a solution to waiting.** `@Order` prioritizes listener invocation order; it does not make async work synchronous or guarantee a transaction has committed.

## 11. Self-Check

- If a synchronous listener takes 2 seconds, can you expect `publishEvent` to return in a few milliseconds? **No** under the default configuration; the publisher must wait for the listener.
- If publishing occurs inside a `@Transactional` method and an ordinary listener finishes, is the transaction definitely committed? **Not necessarily**; commit may happen after the publish call.
- If a listener is annotated with `@Async` but Spring async support is not enabled, can you claim the listener runs in the background? **No**; you must verify the actual configuration.
- If a listener throws `IllegalStateException` in default synchronous mode with no `ErrorHandler`, what happens to the publish call? It **throws the exception** to the caller; remaining listeners may not be invoked.
- If a synchronous listener only calls an API returning a `CompletableFuture` and exits, did publish wait for that `Future` to complete? **No**, unless the listener itself waits/joins on the `Future` before returning.

**Core takeaway:** With default synchronous Spring Application Events, `publishEvent` is a wait point for **directly invoked synchronous listeners**. The observable contract is "the listeners have returned when publish returns normally," along with exceptions for errors, async, and transaction phases; do not overextend it into a guarantee that all business work is complete.

## Official References

- [Spring Framework Reference – Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework Javadoc – SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework Reference – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
