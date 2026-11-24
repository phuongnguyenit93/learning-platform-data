# Do Not Use Return Values to Publish Follow-up Events in Asynchronous Listeners

## 1. The Problem to Understand

In Spring Framework Application Events, a listener can produce a new event after handling an input event. For **synchronous** `@EventListener` methods, Spring offers special support: if the method returns an object, Spring treats that return value as a new event and publishes it automatically. However, **automatic event publishing via return values is not supported for asynchronous event listeners**.

Order workflow example:

```text
OrderSubmitted
    |
    v
Validate / accept order
    |
    v
OrderAccepted
    |
    v
Prepare notification asynchronously
    |
    v
NotificationRequested
    |
    v
Notification-sending listener
```

Suppose the "prepare notification" step uses `@Async` to run on a thread pool. You cannot write it like a synchronous listener returning `NotificationRequested` and implicitly expect Spring to publish it onward. **The right way** is to inject `ApplicationEventPublisher` and call `publisher.publishEvent(new NotificationRequested(...))` at the point where you want the next event emitted.

This is a specific limitation of **`@EventListener` return-value handling**, not a ban on publishing events inside an asynchronous listener. An `@Async` listener can still publish new events **explicitly**.

## 2. Comparing the Two Event-Publishing Mechanisms

| Characteristic | Synchronous Listener | Asynchronous Listener |
| --- | --- | --- |
| Typical declaration | `@EventListener` | `@Async @EventListener` |
| Execution thread | Usually the thread calling `publishEvent` in default configuration | An executor thread selected by Spring |
| Returning an event for Spring to auto-publish | **Supported** | **Not supported** |
| Returning a Collection/array of events to auto-publish each item | **Supported** for synchronous listeners | **Not applicable** to asynchronous listeners |
| Publishing a new event via `ApplicationEventPublisher` | Supported | **Supported and the approach to use** |
| Errors from the method body | Under default synchronous dispatch, uncaught errors can propagate to the publisher | Errors in `@Async void` do not automatically propagate to the publisher |
| Guarantee that handling finished when initial `publishEvent` returns | Typically yes for the default synchronous path | No, for work offloaded to the executor |

Key point: the "`return new SomeEvent(...)`" mechanism is **a convenience implemented by the `@EventListener` adapter**, not a general feature of every Java method or every `ApplicationListener` object. An `ApplicationListener<E>` by interface has `void onApplicationEvent(E event)`.

### 2.1. Valid Pattern with Synchronous Listeners

```java
@EventListener
public OrderAccepted accept(OrderSubmitted event) {
    // Validate/accept the order during synchronous processing.
    return new OrderAccepted(event.orderId());
}
```

When Spring invokes this `@EventListener` method and receives `OrderAccepted`, the adapter can publish the result as a new event. Other listeners registered for `OrderAccepted` will be evaluated for execution.

If a synchronous method returns a `Collection` or array of events, Spring publishes **each element** as a separate event. Do not use this mechanism to express complex multi-step workflows with strict constraints: it only expresses publishing resulting events.

### 2.2. Invalid Pattern with Asynchronous Listeners

```java
// ANTI-PATTERN: do not use this design.
@Async("eventWorker")
@EventListener
public NotificationRequested wrong(OrderAccepted event) {
    return new NotificationRequested(event.orderId());
}
```

The snippet above is **not a valid runnable example**. In standard proxy mode, `@Async` requires a `void` return type or a supported `Future` type; a domain return type like `NotificationRequested` does not conform to the async method contract. More importantly, Spring **does not support auto-publishing events from the return value of an asynchronous listener**.

Changing it to `CompletableFuture<NotificationRequested>` does not turn it into an auto-publishing mechanism for `NotificationRequested`. A Future represents the result of async work; to emit a follow-up event, there must be an explicit publish call.

### 2.3. Valid Pattern with Asynchronous Listeners

```java
// Inside a Spring bean with @EnableAsync enabled.
private final ApplicationEventPublisher publisher;

@Async("eventWorker")
@EventListener
public void prepareNotification(OrderAccepted event) {
    // Perform asynchronous work.
    publisher.publishEvent(
            new NotificationRequested(event.orderId()));
}
```

This is a design excerpt: `publisher` must be injected, event types must be defined, and the `eventWorker` executor must exist. A complete example is in section 4.

The method returns `void`. The new event is emitted **at the line calling `publisher.publishEvent(...)`**. If processing fails before that line and no compensation/retry mechanism exists, the new event will not be published. Writing it explicitly makes clear exactly "when" the follow-up event is published and makes attaching error policies straightforward.

## 3. How Does the Execution Flow Actually Work?

Two distinct operations are often conflated:

1. **Publishing the initial event:** a component calls `ApplicationEventPublisher.publishEvent(orderSubmitted)`.
2. **Publishing the follow-up event:** a listener finishes a piece of work and decides to call `publisher.publishEvent(notificationRequested)`.

For synchronous listeners, Spring can perform the second operation for you if the `@EventListener` method returns an event. For asynchronous listeners, **the listener code itself** must perform the follow-up publication.

```text
Publisher thread                    Executor thread
-----------------                   --------------------------
publishEvent(OrderSubmitted)
       |
       v
Synchronous @EventListener
return OrderAccepted
       |
       v
Spring publishes OrderAccepted
       |
       +------> @Async @EventListener -> prepare data
                    (scheduled)            |
       |                                   v
Initial publishEvent                publisher.publishEvent(
may have already returned             NotificationRequested)
                                           |
                                           v
                                    NotificationRequested Listener
```

**A detail about threads:** with the default synchronous `SimpleApplicationEventMulticaster`, when an `@Async` listener calls `publishEvent` on a **worker thread**, synchronous listeners for the new event also typically run on **that same worker thread**. Do not assume the "next event" automatically switches back to the original thread. If the multicaster or target listener has its own async configuration, thread behavior will differ.

**A detail about timing:** `publishEvent` called inside an `@Async` listener can occur after the initial publishing method has already returned. Therefore, callers should not infer that the event chain has finished simply because `publishEvent(OrderSubmitted)` returned.

## 4. Runnable Java 17 and Spring 6.2 Example

This example builds a small chain to clearly prove both mechanisms:

- `accept` is a synchronous `@EventListener` that **returns** `OrderAccepted`. Spring publishes that event automatically.
- `prepareNotification` is an `@Async @EventListener` returning `void` that **explicitly calls `ApplicationEventPublisher`** to publish `NotificationRequested`.
- `observeNotification` receives the new event. The program uses `CountDownLatch` to wait and inspect threads rather than guessing execution order.

**Directory structure:**

```text
async-event-followup/
├── pom.xml
└── src/main/java/example/AsyncEventFollowupDemo.java
```

**`pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>async-event-followup</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>example.AsyncEventFollowupDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/example/AsyncEventFollowupDemo.java`:**

```java
package example;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class AsyncEventFollowupDemo {

    public record OrderSubmitted(String orderId) {}
    public record OrderAccepted(String orderId) {}
    public record NotificationRequested(String orderId) {}

    public static final class Evidence {
        private final AtomicReference<String> acceptedId =
                new AtomicReference<>();
        private final AtomicReference<String> notificationId =
                new AtomicReference<>();
        private final AtomicReference<String> workerThread =
                new AtomicReference<>();
        private final AtomicReference<String> notificationThread =
                new AtomicReference<>();
        private final CountDownLatch finished = new CountDownLatch(1);

        public void awaitNotification() throws InterruptedException {
            if (!finished.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Timeout waiting for NotificationRequested");
            }
        }
    }

    // Not final: this bean needs to be proxied by Spring for @Async.
    public static class OrderListeners {
        private final ApplicationEventPublisher publisher;
        private final Evidence evidence;

        public OrderListeners(ApplicationEventPublisher publisher,
                              Evidence evidence) {
            this.publisher = publisher;
            this.evidence = evidence;
        }

        // Synchronous listener: Spring auto-publishes the return value.
        @EventListener
        public OrderAccepted accept(OrderSubmitted event) {
            return new OrderAccepted(event.orderId());
        }

        @EventListener
        public void observeAccepted(OrderAccepted event) {
            evidence.acceptedId.set(event.orderId());
        }

        // Asynchronous listener: must publish a new event explicitly.
        @Async("eventWorker")
        @EventListener
        public void prepareNotification(OrderAccepted event) {
            evidence.workerThread.set(Thread.currentThread().getName());
            publisher.publishEvent(
                    new NotificationRequested(event.orderId()));
        }

        // With default synchronous multicaster, this listener runs
        // on the thread that called publishEvent(NotificationRequested).
        @EventListener
        public void observeNotification(NotificationRequested event) {
            evidence.notificationId.set(event.orderId());
            evidence.notificationThread.set(
                    Thread.currentThread().getName());
            evidence.finished.countDown();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {
        @Bean
        public Evidence evidence() {
            return new Evidence();
        }

        @Bean
        public OrderListeners orderListeners(
                ApplicationEventPublisher publisher,
                Evidence evidence) {
            return new OrderListeners(publisher, evidence);
        }

        @Bean("eventWorker")
        public ThreadPoolTaskExecutor eventWorker() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("event-worker-");
            return executor;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        String originalThread = Thread.currentThread().getName();

        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            context.publishEvent(new OrderSubmitted("O-42"));

            Evidence evidence = context.getBean(Evidence.class);
            evidence.awaitNotification();

            String acceptedId = evidence.acceptedId.get();
            String notificationId = evidence.notificationId.get();
            String workerThread = evidence.workerThread.get();
            String downstreamThread = evidence.notificationThread.get();

            System.out.println("Sync return created event: "
                    + "O-42".equals(acceptedId));
            System.out.println("Explicit async publish created event: "
                    + "O-42".equals(notificationId));
            System.out.println("Follow-up event ran on worker: "
                    + (downstreamThread != null
                            && downstreamThread.startsWith("event-worker-")
                            && downstreamThread.equals(workerThread)
                            && !downstreamThread.equals(originalThread)));
        }
    }
}
```

**Run** from the directory containing `pom.xml` with JDK 17+ and Maven:

```bash
mvn -q compile exec:java
```

**Output printed by the program** assuming the executor accepts and completes the task:

```text
Sync return created event: true
Explicit async publish created event: true
Follow-up event ran on worker: true
```

Explanation:

1. Spring receives `OrderSubmitted("O-42")`. The synchronous method `accept` returns `OrderAccepted("O-42")`; the `@EventListener` adapter publishes that event.
2. `observeAccepted` records `O-42`. `prepareNotification` also receives `OrderAccepted`, but is dispatched to the `eventWorker` executor because of `@Async("eventWorker")`.
3. On the `event-worker-*` thread, `prepareNotification` calls `publisher.publishEvent(new NotificationRequested("O-42"))`.
4. Under the default multicaster configuration, `observeNotification` is a synchronous listener and receives this event directly on the thread that called `publishEvent`. It records the result and releases the latch.
5. `main` only prints results after the latch completes. Checking the prefix and comparing thread names proves that the follow-up event listener ran on the worker, without relying on random log ordering.

If the async listener does not finish within 10 seconds, `awaitNotification()` throws a timeout exception; the program **does not print three fake success lines**. This demo needs no web server, database, or broker. Any auxiliary Maven/Spring logs if enabled are separate from the three result lines above.

## 5. Why Doesn't `CompletableFuture` Solve Follow-up Event Publishing?

One might think an async listener can return `CompletableFuture<NotificationRequested>` and Spring will automatically take the value inside the Future as an event. **Do not rely on this assumption.** The `@Async` contract permits certain asynchronous result types, but Spring's automatic publishing of **`@EventListener` return values** is documented as unsupported for asynchronous listeners.

Separate two concepts:

- **Completion value of a Future:** represents a computation result or completion state.
- **Application event:** delivered to other listeners when a component calls `ApplicationEventPublisher.publishEvent(...)` or when a **synchronous listener** uses Spring's supported return-event mechanism.

When working with Futures, you can still publish an event explicitly at an appropriate completion point. Illustrative integration example:

```java
// Assuming prepareAsync(...) returns CompletableFuture<Payload>,
// and publisher is an injected ApplicationEventPublisher.
prepareAsync(order).whenComplete((payload, error) -> {
    if (error != null) {
        // Record failure and apply error/retry policy.
        return;
    }
    publisher.publishEvent(new NotificationRequested(order.orderId()));
});
```

This snippet requires defining `prepareAsync`, `order`, and dependencies to run in an application; **it is not part of the standalone example in section 4**. It clarifies that `publish` is invoked in the callback once work completes successfully. If the callback might run after context shutdown, design lifecycle handling and task persistence accordingly.

Do not call `join()` or `get()` inside a listener to turn the whole async flow synchronous, especially if the subtask also needs the same single-threaded pool: that can cause stalls or deadlocks.

## 6. When Should the Follow-up Event Be Published?

Explicit publishing forces you to pinpoint the exact business milestone.

| Processing Milestone | Appropriate Event | Notes |
| --- | --- | --- |
| Order was validated and accepted | `OrderAccepted` | Reflects acceptance result, not that email was sent |
| Content preparation succeeded | `NotificationPrepared` | Can be published after building the payload to send |
| Notification system was asked to send | `NotificationRequested` | Represents only a **request**, does not prove successful delivery |
| Provider confirmed successful delivery | `NotificationSent` | Publish only after obtaining a reliable result from the sending task |
| Sending failed | `NotificationFailed` | Decide on retries, error recording, and preventing infinite loops |

Naming events after **facts that have occurred** helps downstream listeners interpret them accurately. An `@Async` listener that receives `OrderAccepted` and publishes `NotificationSent` before calling the email service is semantically wrong even though it is valid Java syntax.

If a business step has multiple success and failure branches, you can emit different events, each carrying enough data to trace: `eventId`, `orderId`, timestamp, outcome type, and correlation info when needed. Do not pass mutable entities currently being updated across threads and treat them as immutable snapshots.

## 7. Transactions and Thread Boundaries

Suppose code publishes `OrderSubmitted` while a transaction has not yet committed:

```java
@Transactional
public void submitOrder(String orderId) {
    // Save business changes via repository.
    publisher.publishEvent(new OrderSubmitted(orderId));
}
```

This is an integration snippet requiring a real service, repository, and transaction manager. If an `@Async` listener receives the event immediately, processing on the worker **can run before commit**, and newly saved data may not yet be visible to queries from another transaction. If the original transaction rolls back, follow-up events may still have been emitted.

When work may only run **after a successful commit**, consider:

```java
// Illustrative inside a Spring bean with @EnableAsync and real transactions.
@Async("eventWorker")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderAccepted event) {
    publisher.publishEvent(
            new NotificationRequested(event.orderId()));
}
```

This snippet requires importing `@TransactionalEventListener` and `TransactionPhase` along with related dependencies. Things to remember:

- `@TransactionalEventListener` defaults to the `AFTER_COMMIT` phase; with `fallbackExecution = false`, events published outside a transaction **do not trigger** transaction-bound listeners.
- Transaction callback registration must associate with the transaction active when the event is published. Once the commit phase is satisfied, `@Async` can offload execution to the worker.
- When a follow-up event is published **on the worker**, that thread normally **does not carry the original transaction**. A `@TransactionalEventListener` on the follow-up event may likewise not run if the worker has no active transaction.
- `AFTER_COMMIT` addresses **timing**, not durable task executor persistence. If the process dies between commit and publishing, the follow-up event may never exist.
- If you need both data commit and eventual delivery guarantees, consider a **transactional outbox**: persist state and an outbox record in the same transaction, then have a worker read the outbox to publish/deliver with retries and idempotency.

Do not assume `ThreadLocal`, MDC, security context, transactions, or persistence contexts automatically transfer from the publisher to `@Async`. Include business identifiers and correlation IDs in the event, and use intentional context propagation mechanisms if needed.

## 8. Errors, Retries, and Reliability

Separate three potential failure points:

1. **Initial listener fails before `publishEvent`:** the follow-up event has not been published. With `@Async void`, exceptions in the method body do not propagate back to the caller; configure `AsyncUncaughtExceptionHandler` or handle errors explicitly.
2. **Executor rejects the task:** the async listener may not even start. For instance, an overloaded `ThreadPoolTaskExecutor` can throw `TaskRejectedException` during task handoff. Monitor and handle this situation separately.
3. **Follow-up event listener fails:** calling `publisher.publishEvent(...)` does not mean every recipient succeeded. With a synchronous multicaster, uncaught exceptions in a target listener can propagate back to the publishing worker; with an asynchronous multicaster, errors may be handled on another executor.

Strategies to consider:

- **Idempotency:** an `eventId` or business key allows skipping already-applied side effects if a task is retried.
- **Bounded retries:** define max attempts, backoff intervals, retry conditions, and where final failures are recorded. Avoid listeners re-emitting the same event in an unbounded loop.
- **Durability:** `ApplicationEventPublisher` dispatches events inside the context, not as a message broker or durable queue. For critical workflows, combine with an outbox/broker.
- **Observability:** log `eventId`/`orderId`, receive and follow-up publish timestamps, thread name, status, and wait time.
- **Application shutdown:** executor shutdown policies should account for running and queued tasks; graceful shutdown alone does not guarantee recovery from a process crash.

Do not fix lost events merely by increasing thread counts or queue sizes: those parameters tune in-memory execution capacity, not durability.

## 9. Properly Testing Follow-up Event Publication

For the section 4 example, tests should prove both **that a new event occurred** and **that it was published correctly**.

| Case | Expectation |
| --- | --- |
| Synchronous `accept` listener returns `OrderAccepted` | Listener for `OrderAccepted` is invoked |
| `prepareNotification` listener has `@Async` | It executes on an `event-worker-*` thread |
| Async listener calls `publisher.publishEvent(NotificationRequested)` | Listener for `NotificationRequested` is invoked |
| Omit `publisher.publishEvent` in async listener | No `NotificationRequested` is emitted by that listener |
| Async listener throws before publishing | No successful follow-up is emitted; error is tracked |
| Executor rejects task | Workflow is not marked complete; overload policy applies |
| Follow-up published outside a transaction and target uses `@TransactionalEventListener` | By default, transaction-bound target does not run without a transaction |

For async tests, `CountDownLatch`, `CompletableFuture`, or timed waiting mechanisms help reduce flakiness. Do not use a single `Thread.sleep(100)` and conclude "no event occurred" if the listener simply hadn't run yet.

### Three Common Testing Mistakes

**Mistake 1 — asserting immediately after initial publish:**

```java
publisher.publishEvent(new OrderSubmitted("O-42"));
// Do not conclude the async listener has completed solely from this line.
```

**Mistake 2 — verifying only that the async method ran:** the original listener running does not prove the follow-up was published. Tests must attach a listener/spy on the follow-up event type and assert the exact payload.

**Mistake 3 — using logs as proof of ordering:** threads can interleave log lines. Wait for completion callbacks and compare thread-safely recorded data.

## 10. Common Pitfalls

1. **Assuming `@Async @EventListener` can `return new Event()` like a synchronous listener.** Spring does not support that mechanism. Use `void` and call `ApplicationEventPublisher.publishEvent(...)` explicitly.
2. **Confusing Future with event.** `CompletableFuture<Event>` is a computation result, not a promise that Spring will auto-publish the completed value as an event.
3. **Forgetting `@EnableAsync`.** Without enabling async support in plain Spring, listeners may behave differently than expected and thread assumptions will fail.
4. **Internal calls bypassing the proxy.** `this.asyncMethod(...)` in the same bean under default proxy mode can bypass `@Async`.
5. **Publishing follow-up too early.** Publish `NotificationSent` only after sending succeeds, not immediately upon starting.
6. **Ignoring transactions.** Async workers do not automatically see uncommitted data; consider `AFTER_COMMIT`/outbox if events depend on durable data.
7. **Treating `publishEvent` as a guaranteed-delivery queue.** In-process Spring events lack built-in durable persistence/retries.
8. **Relying on listener order instead of explicit dependency models.** `@Order`, if used, does not guarantee completion order of async work.
9. **Missing error handling.** Exceptions from `@Async void` may only reach a handler/log while the publisher returns normally.
10. **Creating event loops.** A listener for `NotificationRequested` continuously emitting `NotificationRequested` itself creates an infinite chain if no stop condition exists.

## 11. Design Checklist

- Every event represents a clearly named business fact or request.
- Synchronous listeners using `return` are distinguished from `@Async` listeners needing explicit publish calls.
- `ApplicationEventPublisher` is injected into the bean and invoked **after successful processing steps**.
- `@EnableAsync` and executors are configured with resource limits and error monitoring.
- Event payloads contain enough information for execution on another thread; avoid relying on mutable entities or transaction contexts.
- Tests use timeouts, verify the exact follow-up event and error conditions, and do not guess from logs.
- If business rules require reliable delivery, design outbox/retries/idempotency.
- Verified whether follow-up events trigger synchronous listeners on the worker thread and assessed the impact on worker latency/exceptions.

**Technical conclusion:** `@EventListener` return values are a follow-up event mechanism meant for **synchronous** processing. For asynchronous listeners, follow-up events must be emitted using an **explicit `ApplicationEventPublisher.publishEvent(...)`** at the exact business milestone.

## References

- [Spring Framework 6.2 — ApplicationContext Events and asynchronous listener limitations](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Javadoc — EventListener](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework — Task Execution and `@Async`](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)