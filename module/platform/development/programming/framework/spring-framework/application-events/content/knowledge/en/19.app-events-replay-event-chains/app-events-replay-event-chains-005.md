# Do Not Rely on Return Values in `@Async` When Building Spring Application Event Chains

## 1. Problem Statement: From Event A to Event B

An order processing workflow is often split into business events:

```text
OrderSubmitted -> OrderValidated -> InvoiceRequested -> InvoiceCreated
```

In Spring Framework, a **synchronous** `@EventListener` method can return another object. Spring takes that result and **publishes it as a new Application Event**. However, Spring Framework **does not support publishing follow-up events via the return value of an asynchronous event listener** (a listener using `@Async` or invoked asynchronously).

Therefore, when you want an async listener to produce the next step, inject `ApplicationEventPublisher` and **explicitly call `publishEvent(...)` after the required work succeeds**:

```java
@Async("eventExecutor")
@EventListener
public void onValidated(OrderValidated event) {
    // Complete the necessary work first.
    publisher.publishEvent(new InvoiceRequested(event.orderId()));
}
```

This is illustrative code; it requires a Spring bean with an injected `publisher` field, `@EnableAsync`, an `eventExecutor` bean, and application-defined event types.

**Distinguish the concepts right from the start:**

| Concept | Accurate meaning |
| --- | --- |
| Synchronous `@EventListener` returning an event | Spring can treat the return value as a new event and publish it onward |
| `@Async @EventListener` | The listener runs via async execution; **do not use its return value to publish new events** |
| `ApplicationEventPublisher.publishEvent(...)` | Event-publishing API with `void` return type; does not return listener results to the caller |
| `Future`/`CompletableFuture` from an `@Async` service | Allows **the method's caller** to observe the async result; does not automatically turn the result into a Spring Application Event |
| Chaining | Step A finishes and produces event B, which can extend into a chain |
| Replay | Re-emitting previously stored events; Spring's event publisher **does not store history automatically** |

Spring Application Events is an in-application messaging mechanism. Java return data, event chaining, async threads, transactions, and replay are distinct mechanisms that must be designed explicitly.

## 2. How Does Spring Automatically Publish Events from Return Values?

Consider the following **synchronous** listeners (illustrative code; records are application-defined):

```java
public record OrderSubmitted(String id) {}
public record OrderValidated(String id) {}
public record InvoiceRequested(String id) {}

@Component
public class ValidationListener {
    @EventListener
    public OrderValidated validate(OrderSubmitted event) {
        return new OrderValidated(event.id());
    }
}

@Component
public class BillingListener {
    @EventListener
    public InvoiceRequested prepare(OrderValidated event) {
        return new InvoiceRequested(event.id());
    }
}
```

You must import `org.springframework.stereotype.Component`, `org.springframework.context.event.EventListener`, and the corresponding Spring types when placing this code in an application. Once `OrderSubmitted` is published and Spring has registered the beans/listeners:

```text
publishEvent(OrderSubmitted)
   |
   +-- ValidationListener.validate()
       |
       +-- return OrderValidated
           |
           +-- Spring publishEvent(OrderValidated)
               |
               +-- BillingListener.prepare()
                   |
                   +-- return InvoiceRequested
                       |
                       +-- Spring publishEvent(InvoiceRequested)
```

This is a dedicated feature of listener methods, documented in the `@EventListener` Javadoc and Spring Framework reference documentation. When a synchronous method returns a `Collection` or an array of event objects, Spring can publish **each element as a separate event**.

```java
@EventListener
public List<Object> onValidated(OrderValidated event) {
    return List.of(
            new InvoiceRequested(event.id()),
            new StockReservationRequested(event.id()));
}
```

This is illustrative code; `StockReservationRequested` must be defined and `java.util.List` imported. For methods returning `void` or `null`, no follow-up event is created **from the return value**.

**Warning:** `publishEvent(A)` is still a **`void`** call. The caller does not receive `OrderValidated` as a method result. The framework uses the return value **inside event dispatch**, not as a request–response protocol.

Synchronous return-event works well for short, fast chains that do not require a separate thread. An overly long chain can become deeply nested publish calls, increasing latency and making execution boundaries hard to follow.

## 3. Why Does the Return-Value Mechanism Not Work with `@Async`?

Spring uses `@EnableAsync` and an async advice/proxy to hand `@Async` invocations off to an `Executor`. The caller can regain control **before the listener body finishes executing**:

```text
Publisher thread
  |
  +-- publishEvent(EventA)
       |
       +-- call to @Async listener bean proxy
            |
            +-- submit task to Executor
            |
            +-- return control to event dispatch
  |
  +-- caller continues working

Worker thread
  |
  +-- @Async listener handles EventA
  +-- explicit publishEvent(EventB)
```

This call path has no ordinary event return value available at dispatch time. Spring states clearly under **Asynchronous Listeners**: publishing follow-up events via the **return value** of an async listener is not supported; inject the publisher and publish explicitly.

Do not write:

```java
@Async
@EventListener
public InvoiceRequested onValidated(OrderValidated event) {
    return new InvoiceRequested(event.id());
}
```

This is an **anti-pattern**. Regular `@Async` methods only support `void` or `Future` (including `CompletableFuture`) as return types, not arbitrary event types. In proxy execution, an `@Async` method returning `InvoiceRequested` can error due to an invalid return type; crucially, **you must not expect Spring to publish the event automatically**.

Also do not change it to:

```java
@Async
@EventListener
public CompletableFuture<InvoiceRequested> onValidated(
        OrderValidated event) {
    return CompletableFuture.completedFuture(
            new InvoiceRequested(event.id()));
}
```

This is **not** an event-chaining pattern guaranteed by Spring. `CompletableFuture` expresses the completion value of an async call; it **creates no contract** that the event infrastructure will wait on the future and publish its contents as a new event.

The proper pattern with an async listener:

```java
@Async("eventExecutor")
@EventListener
public void onValidated(OrderValidated event) {
    InvoiceRequested next = new InvoiceRequested(event.id());
    publisher.publishEvent(next);
}
```

`void` accurately communicates that the listener returns no business result to the event dispatcher; the step of emitting the new event is **expressed explicitly in code**.

## 4. Runnable Java 17+ Example: One Synchronous Return Step and One Async Publish Step

This example uses **Spring Framework 6.2.12**, JDK 17+, and Gradle 8+. No Spring Boot or database is needed.

The demonstrated flow:

```text
JobSubmitted
    |
    +-- synchronous @EventListener
          return JobValidated
                |
                +-- @Async @EventListener
                      runs on eventExecutor
                      calls publisher.publishEvent(JobIndexed)
                           |
                           +-- @EventListener receives JobIndexed
```

The application verifies behavior using `CountDownLatch` and `AtomicReference` rather than `Thread.sleep()` or relying on log order across threads.

### 4.1. Project Structure

```text
spring-event-chain-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/AsyncEventChainDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-event-chain-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
}

application {
    mainClass = 'demo.AsyncEventChainDemo'
}
```

### 4.2. `src/main/java/demo/AsyncEventChainDemo.java`

```java
package demo;

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

public class AsyncEventChainDemo {

    public record JobSubmitted(String jobId) {}

    public record JobValidated(String jobId) {}

    public record JobIndexed(String jobId) {}

    public static class ValidationListener {
        private final AtomicReference<String> validatedId =
                new AtomicReference<>();

        // Synchronous listener returns an event for Spring to publish onward.
        @EventListener
        public JobValidated onSubmitted(JobSubmitted event) {
            validatedId.set(event.jobId());
            return new JobValidated(event.jobId());
        }

        public String validatedId() {
            return validatedId.get();
        }
    }

    public static class AsyncIndexingListener {
        private final ApplicationEventPublisher publisher;
        private final AtomicReference<String> threadName =
                new AtomicReference<>();
        private final CountDownLatch finished = new CountDownLatch(1);

        public AsyncIndexingListener(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        // Do not return an event: explicitly publish from the worker thread.
        @Async("eventExecutor")
        @EventListener
        public void onValidated(JobValidated event) {
            try {
                threadName.set(Thread.currentThread().getName());
                publisher.publishEvent(new JobIndexed(event.jobId()));
            } finally {
                finished.countDown();
            }
        }

        public boolean awaitFinished() throws InterruptedException {
            return finished.await(5, TimeUnit.SECONDS);
        }

        public String threadName() {
            return threadName.get();
        }
    }

    public static class IndexedObserver {
        private final AtomicReference<String> indexedId =
                new AtomicReference<>();
        private final CountDownLatch observed = new CountDownLatch(1);

        @EventListener
        public void onIndexed(JobIndexed event) {
            indexedId.set(event.jobId());
            observed.countDown();
        }

        public boolean awaitObserved() throws InterruptedException {
            return observed.await(5, TimeUnit.SECONDS);
        }

        public String indexedId() {
            return indexedId.get();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class AppConfig {

        @Bean("eventExecutor")
        ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(20);
            executor.setThreadNamePrefix("event-");
            executor.setWaitForTasksToCompleteOnShutdown(true);
            executor.setAwaitTerminationSeconds(5);
            return executor;
        }

        @Bean
        ValidationListener validationListener() {
            return new ValidationListener();
        }

        @Bean
        AsyncIndexingListener asyncIndexingListener(
                ApplicationEventPublisher publisher) {
            return new AsyncIndexingListener(publisher);
        }

        @Bean
        IndexedObserver indexedObserver() {
            return new IndexedObserver();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            ValidationListener validation =
                    context.getBean(ValidationListener.class);
            AsyncIndexingListener async =
                    context.getBean(AsyncIndexingListener.class);
            IndexedObserver indexed =
                    context.getBean(IndexedObserver.class);

            context.publishEvent(new JobSubmitted("J-42"));

            if (!async.awaitFinished()) {
                throw new IllegalStateException(
                        "Async event listener did not finish");
            }
            if (!indexed.awaitObserved()) {
                throw new IllegalStateException(
                        "Follow-up event was not observed");
            }

            System.out.println("sync returned event: "
                    + "J-42".equals(validation.validatedId()));
            System.out.println("async used executor: "
                    + async.threadName().startsWith("event-"));
            System.out.println("explicit follow-up received: "
                    + "J-42".equals(indexed.indexedId()));
        }
    }
}
```

### 4.3. Running and Verifying

With JDK 17+ and Gradle installed:

```bash
gradle -q run
```

Lines printed by the application:

```text
sync returned event: true
async used executor: true
explicit follow-up received: true
```

Gradle or Spring may print other logs depending on configuration. The three lines above are the direct output of `System.out.println`, not the entire terminal output.

**Analysis:**

1. `AnnotationConfigApplicationContext` creates the beans and processes `@EventListener` methods. Spring allows publishing a Java record as a payload event without requiring the record to extend `ApplicationEvent`.
2. When `JobSubmitted("J-42")` is published, the synchronous listener `ValidationListener.onSubmitted` returns `JobValidated`. Spring automatically publishes a new event from that return value.
3. The call to `AsyncIndexingListener.onValidated` goes through a Spring bean proxy thanks to `@EnableAsync`; the async interceptor submits the method body to `eventExecutor`.
4. A worker thread prefixed with `event-` runs the `void` method and **explicitly publishes `JobIndexed`**. That is the sole place inside the async listener where the next event is created.
5. `IndexedObserver` is a regular listener. When it receives `JobIndexed` published from the worker thread, it can execute **on that worker thread** under the default synchronous multicaster.
6. `CountDownLatch` ensures both the async step and the receipt of the final event finish before printing results. `AtomicReference` enables thread-safe observation of values across threads. The program **makes no assumptions** about arbitrary execution order between publisher and executor.
7. There is no `@Async` on `IndexedObserver`'s method, so the final event is not automatically moved to another executor. Changing that requires explicit configuration.

This is a single-run example with one job. When processing multiple jobs, each job needs its own completion signal and correlation; do not share a single fixed latch across all production traffic.

## 5. `CompletableFuture` Is Useful, But Does Not Turn Into an Event Chain Automatically

A service method invoked through an async proxy can return `Future<T>` or `CompletableFuture<T>`:

```java
@Async("eventExecutor")
public CompletableFuture<IndexResult> buildIndex(String jobId) {
    IndexResult result = index(jobId);
    return CompletableFuture.completedFuture(result);
}
```

This is an **illustrative snippet**; it requires another Spring bean holding the method, application-defined `IndexResult` and `index(...)`, `@EnableAsync`, and a valid executor. The caller receives the future from the proxied call and can compose with `thenAccept`, `whenComplete`, or `join`.

If you want to emit a follow-up event after an async service succeeds, a synchronous listener can trigger the service and attach a callback that **explicitly publishes**:

```java
@EventListener
public void onValidated(JobValidated event) {
    indexService.buildIndex(event.jobId())
            .thenAccept(result ->
                    publisher.publishEvent(
                            new JobIndexed(result.jobId())))
            .exceptionally(error -> {
                recordFailure(event.jobId(), error);
                return null;
            });
}
```

This is **illustrative code**, not a standalone program: `indexService` is a bean with an async method, `publisher` is injected, `JobIndexed`/`IndexResult` are defined, and `recordFailure(...)` is implemented by the application.

Distinctions to keep clear:

- `onValidated` receives the event and **returns `void`**; it does not use return-value chaining.
- `buildIndex` is an **async service method**, not `@EventListener`'s event-return mechanism.
- The `thenAccept` callback **explicitly** calls `publisher.publishEvent(...)`. If the service fails, the success callback does not run.
- `CompletableFuture` callbacks may execute on the thread that completes the future; if you want a dedicated executor for the callback step, use `thenAcceptAsync(..., executor)`.
- `exceptionally` must perform real error tracking, retries, or dead-letter routing; merely logging and swallowing errors can silently drop work.
- This approach is still **in-memory processing** and is not automatically durable across crashes.

Do not design an `@Async @EventListener` returning `CompletableFuture<NextEvent>` assuming Spring will unwrap the future to publish `NextEvent`. Framework documentation does not guarantee such behavior.

## 6. When Is a New Event Considered to Have Occurred?

An event should reflect a **business milestone actually achieved**, not merely that a task was enqueued. If `ImageReady` is published immediately after submitting an image-resize job while the image has not been created yet, consumers may begin using a resource that does not exist.

A safer execution path:

```text
ImageUploaded
    |
    +-- @Async resizeImage()
         |
         +-- image resized successfully / data saved
                |
                +-- publisher.publishEvent(ImageReady)
                        |
                        +-- listener sends notification
```

Publish the new event **after** the relevant side effect succeeds. If processing fails, do not publish an event named “succeeded”. You can publish `ImageProcessingFailed` under an explicit failure policy or record failure state for retry.

When using a future as in section 5, event B should be published inside the successful completion callback, not immediately after invoking the async service:

```java
CompletableFuture<IndexResult> future =
        indexService.buildIndex(event.jobId());

// Semantically wrong if calling publish right here before indexing finishes.
// Correct: publish inside the successful completion callback.
future.thenAccept(result ->
        publisher.publishEvent(new JobIndexed(result.jobId())));
```

The code above illustrates publication timing, not a complete class. The goal is not “never use return values in general”: `CompletableFuture` can be a useful service return value. What to avoid is **relying on an async event listener's return value for Spring to automatically chain events**.

## 7. Do Not Rely on Completion Order Across Multiple Async Listeners

Suppose event A has two listeners:

```java
@Async("eventExecutor")
@EventListener
public void generateReport(ReportRequested event) {
    // Generate report file.
}

@Async("eventExecutor")
@EventListener
public void sendReportEmail(ReportRequested event) {
    // Must not assume the report file already exists.
}
```

This is illustrative code. The two listeners can run on two different threads. `@Order` (if configured) can affect **invocation/submission order**, but it does not turn async tasks into a sequentially completing chain.

If the email must go out only after the report file has been generated, design around a **result event**:

```text
ReportRequested
    |
    +-- async generate report
           |
           +-- publish ReportGenerated
                  |
                  +-- send email
```

`ReportGenerated` signifies that the prior step has finished. A chain with multiple async listeners also needs correlation (`requestId`, `eventId`, `aggregateId`), ordering by business key, and idempotency. Do not treat “event published earlier” as meaning “all of its handlers finished earlier”.

## 8. Exceptions in Async Listeners Do Not Return to the Publisher

With default synchronous listeners, exceptions can propagate down the `publishEvent()` call stack depending on the multicaster/error handler. However, an exception occurring on the **worker thread** of an `@Async void` listener **is not automatically sent back to the publisher thread**.

Spring provides `AsyncUncaughtExceptionHandler` to handle uncaught exceptions from `void` async methods:

```java
@Configuration
@EnableAsync
public class AsyncErrorConfig implements AsyncConfigurer {
    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (error, method, parameters) ->
                System.err.println(
                        "Async failed: " + method.getName()
                                + " / " + error.getMessage());
    }
}
```

This is an illustrative snippet; it requires importing `Configuration`, `EnableAsync`, `AsyncConfigurer`, and `AsyncUncaughtExceptionHandler`. In production, use structured logging, metrics, alerting, and real retry/compensation mechanisms.

Failure scenarios:

| Failure point | Possible consequence | How to observe |
| --- | --- | --- |
| Synchronous listener throws runtime exception | May cause publisher to receive exception | Error handler and publish-outcome tests |
| `void` async listener throws while running task | Publisher may have already returned normally; event B is never published | `AsyncUncaughtExceptionHandler`, logs, metrics, retries |
| Executor rejects task | Failure can happen during dispatch/submit | Configure queue/rejection policy, capacity monitoring |
| B is published but consumer B fails | Overall chain is incomplete even though step A finished | Track per-stage status and state |
| Process dies before A publishes B | Event B may be lost | Persisted work / transactional outbox |
| Retry causes B to be published multiple times | Duplicate side effects | Deduplicate via `eventId`, idempotency |

**`publishEvent(A)` returning does not prove async listener A succeeded**. Likewise, a `CompletableFuture` completing in service A does not prove event B's listeners finished processing, unless the program has an explicit completion mechanism.

## 9. `@Async` Proxies and Self-Invocation

In the default mode, `@EnableAsync` applies an async interceptor through a Spring proxy. If a bean calls **its own** async method using `this`, the call bypasses the proxy and is not automatically handed off to the executor.

```java
@Service
public class WorkflowWorker {

    public void start(JobValidated event) {
        this.processAsync(event); // Self-invocation: bypasses the proxy.
    }

    @Async("eventExecutor")
    public void processAsync(JobValidated event) {
        // May run synchronously when invoked this way.
    }
}
```

This is illustrative code; it requires importing `Service`, `Async`, the event types, and the executor. The straightforward solution is to extract the async method into **another Spring-managed bean** and inject that bean, or use `@Async @EventListener` so the event infrastructure invokes it through the proper bean proxy as in section 4's runnable example.

Two independent concepts:

1. The proxy must be active for `@Async` to actually switch threads.
2. **Even when the proxy works properly, return-value event chaining is still unsupported for async listeners.**

Rule #2 cannot be fixed merely by changing the executor or enabling class-based proxies.

## 10. Transactions, Commits, and Follow-Up Events

Suppose a service publishes event A inside a transaction:

```java
@Transactional
public void submitOrder(String id) {
    orderRepository.save(createOrder(id));
    publisher.publishEvent(new OrderSubmitted(id));
}
```

This is an illustrative snippet, with `orderRepository` and `createOrder(...)` defined by the application. If listener A is `@Async @EventListener`, the worker thread can begin processing **before the publisher's transaction commits**. Later the publisher's transaction may roll back, while the listener has already emitted B or sent an email.

Consequences to avoid:

- The worker thread does not automatically carry the publisher thread's JDBC/JPA transaction.
- An async listener reading the DB may not yet see uncommitted records.
- Event B may be published before A's data is durably saved.
- JPA entities/lazy proxies passed in an async event may depend on an expired persistence context.
- An exception in the async listener does not automatically roll back the original transaction.

If B **should only exist after A commits**, consider:

```java
@Async("eventExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderSubmitted event) {
    publisher.publishEvent(new OrderValidated(event.id()));
}
```

This is illustrative; it requires `@EnableAsync`, an executor, a Spring-managed bean, and transaction-event imports. With an active imperative transaction, `@TransactionalEventListener` registers a callback for the `AFTER_COMMIT` phase. When commit succeeds, the callback triggers the listener invocation; the async body can explicitly publish B.

Notes:

- `AFTER_COMMIT` determines **timing**; it does not create retries or event persistence.
- The worker thread does not automatically inherit the original transaction. If DB writes are needed from the worker, open a new transaction at the appropriate service boundary.
- If B is published when the worker thread **has no transaction**, a `@TransactionalEventListener` for B will by default not run because there is no transaction to bind a callback to. If B must attach to the commit of the new step, publish B **inside** that new transaction.
- If the process dies after A's transaction commits but before B is published, the chain can lose a step. When durability is required, use an outbox/queue.

### Transactional Outbox

For critical workflows, consider:

```text
Transaction T1
  +-- update order
  +-- write outbox event A
  +-- COMMIT
        |
        +-- outbox worker reads committed A
              +-- process step A
              +-- save result / outbox event B
              +-- commit separate step
                    |
                    +-- broker/worker continues event B
```

An outbox ensures follow-up work **is saved together with the business change**, though it does not guarantee exactly-once delivery on its own. Consumers still need idempotency, retry/backoff, status tracking, and error observability.

## 11. Chaining Is Not Replay

In the **Replay and Event Chains** group, distinguish:

- **Chaining:** A leads to B, B leads to C as each step finishes.
- **Republishing:** a listener actively emits a follow-up event, either the same type or a new type.
- **Replay:** re-emitting events that were **durably stored** in an event store, a broker with retention, an outbox, or another persistent source.

Standard `ApplicationEventPublisher` does not store event history, does not create a durable queue, and does not automatically replay after a restart. Switching to `@Async` does not turn events into persistent messages either.

If an old event must be reprocessed:

1. The event must be stored with enough payload to reconstruct its business meaning.
2. Have an `eventId` or deduplication key to prevent duplicate side effects.
3. Have a version/sequence and a policy for handling an old event arriving after a newer event.
4. Distinguish **retrying step A** from **publishing a new event B** so you do not trigger an event storm.
5. Maintain processing status, metrics, backoff, dead-letter/compensation, and a recovery policy.

A synchronous listener's return value is only a convenience for **in-memory dispatch**; it does not replace these requirements.

## 12. Avoiding Infinite Cycles and Event Storms

A synchronous listener returning the same event type can re-trigger itself:

```java
@EventListener
public SameEvent onSameEvent(SameEvent event) {
    return event;
}
```

This is an **anti-pattern**; `SameEvent` is an application-defined event. Without a stopping condition, one event can create an endless nested chain leading to stack/deep-recursion errors.

With an async listener explicitly publishing the same event type, a similar loop can produce a **task storm on the executor**, filling queues, spiking memory, or exhausting the thread pool. Even without using return values, cycles still happen if the state machine is misdesigned.

Countermeasures:

- Name events after **achieved business milestones**: `ImageProcessed`, `InvoiceIssued`, instead of always using `SomethingChanged`.
- Define valid state transitions and stopping conditions.
- Include correlation ID, `eventId`, `parentEventId`, hop/TTL count, and retry limits.
- Handle duplicates safely by idempotency key.
- Bound queue capacity, thread pools, timeouts, and rejection policies.
- Move long/complex workflows to a workflow engine or stateful orchestrator when appropriate.

## 13. Testing Checklist

Valuable tests:

1. **Synchronous listener returning an event:** publish A, verify listener B receives the exact event returned by method A.
2. **Async explicit publish:** publish A, let async listener A explicitly publish B, await B using a latch/future/Awaitility with a timeout.
3. **Never use sleep to guess:** avoid `Thread.sleep(50)` because it is flaky on CI.
4. **No return chaining in async:** inspect method signatures; do not expect event B to be published from the return value of `@Async @EventListener`.
5. **Async exception:** trigger an error before B is published, verify B does not appear and the failure is recorded.
6. **Executor rejection:** saturate pool/queue in a controlled test; verify the error policy.
7. **Ordering:** publish multiple events, verify B can complete out of A's order; use sequencing if business rules require it.
8. **Rollback:** publish A inside a transaction and roll back; an `AFTER_COMMIT` listener must not emit B.
9. **Duplicates/replay:** republish A, verify idempotency and ensure B is not processed twice.
10. **Shutdown:** stop the context while tasks remain; verify pool behavior and guarantees against losing mandatory work.

### Common Errors Table

| Symptom | Common cause | Fix |
| --- | --- | --- |
| `@Async` listener returns B but B never appears | Async return-value chaining is not supported | Change listener to `void`, explicitly call `publisher.publishEvent(B)` |
| `@Async` method returns a plain event object and fails when called | Return type is not `void`/`Future` | Fix `@Async` signature; use publisher to emit events |
| `CompletableFuture<B>` finishes but B is not published | Future results do not automatically become Application Events | Register a `thenAccept` callback that calls publisher |
| `publishEvent(A)` finishes but B is not there yet | Listener A runs on an executor | Await completion/event B with an explicit mechanism |
| Listener still runs on caller thread | Missing `@EnableAsync`, bypassed proxy, or self-invocation | Fix bean/proxy/executor setup, extract to another bean |
| B is published before A commits | Async listener runs while T1 is still open | Use `AFTER_COMMIT` or an outbox per requirements |
| Worker exception does not reach publisher | Exception occurs on a different thread | Async exception handler, logs/metrics |
| Event B repeats many times | Retries, duplicate delivery, cycle | `eventId`, idempotency, state machine |
| B arrives out of order | Multiple worker threads, no completion-order guarantee | Version/order by aggregate key |
| Crash loses the follow-up event | Relying solely on in-memory events | Persisted queue/outbox/worker |

## 14. Guiding Principles

For building Spring Application Event chains:

- **Synchronous listener, short chain:** returning a new event is fine; it is a supported feature of `@EventListener`.
- **`@Async` listener:** always treat emitting the follow-up event as an **explicit action**, calling `ApplicationEventPublisher.publishEvent(...)` after relevant work succeeds.
- **`@Async` service returning `CompletableFuture`:** use the future for coordination and caller observation, and **publish explicitly** in a callback if needed; do not confuse it with a listener's return value.
- **Need A committed before B:** use `AFTER_COMMIT`/outbox; do not emit B from a transaction that might still fail.
- **Need processing across crashes:** persistent outbox, queue/broker, or workflow engine, with retries and idempotency.
- **Need ordering or loop prevention:** design a state machine, event IDs, aggregate versions, and step limits.

**Conclusion:** `@Async` controls where work executes, not a mechanism for “returning a new event to Spring”. To chain events cleanly and testably, publish follow-up events **explicitly** from async listeners, while designing error handling, ordering, transactions, and durability to match business requirements.

## References

- [Spring Framework 6.2 — `@EventListener`, return values, and asynchronous listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — `@EventListener` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework 6.2 — `@Async` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/annotation/Async.html)
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 — `ApplicationEventPublisher` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework 6.2 — AOP proxying and self-invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
