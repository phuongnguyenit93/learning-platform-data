# Limitations of Moving Listeners to Async When Ordering Matters — Spring Boot 3.3

## 1. Goal and Key Message

In Spring Boot, `ApplicationEventPublisher` lets one component publish an event and multiple listeners react to it. By default, with `SimpleApplicationEventMulticaster` without another executor configured, listeners are invoked **synchronously on the event publisher's thread**. You can use `@Async` or a `TaskExecutor` to process events asynchronously, yet this shift introduces major changes in **ordering, completion timing, exceptions, transactions, and startup readiness**.

**Core takeaway:** `@Order(10)` ahead of `@Order(20)` can control **the invocation/dispatch order of listeners within an ordering-aware mechanism**, yet **does not guarantee the first listener finishes processing before the second listener** once work is offloaded to another thread. If step B truly needs committed results from step A, express the dependency and completion coordination explicitly — do not just add `@Order`.

After this lesson you will be able to:

- Distinguish **event publication order**, **listener dispatch order**, **execution start order**, **completion order**, and **commit order**.
- Understand `@EventListener`, `ApplicationListener`, `@Order`, `@Async`, `@EnableAsync`, `SimpleApplicationEventMulticaster`, and `TaskExecutor`.
- Analyze why synchronous event listeners generally have more predictable ordering, whereas async listeners can run in parallel, finish out of order, and alter error reporting.
- Understand exceptions related to `TransactionalApplicationListener`, `@TransactionalEventListener`, bootstrap events, and readiness.
- Run a Java 21 / Spring Boot 3.3 example with synchronous, asynchronous, and `CountDownLatch` coordination to verify via controlled observation rather than guessing from random logs.
- Know when to use sequential pipelines, future composition, outboxes, or ordering-guaranteed queues when business requirements demand them.

## 2. How Do Event Listeners Work by Default?

### 2.1. Synchronous Processing Flow

A publisher calls:

```java
publisher.publishEvent(new PaymentAccepted("payment-123"));
```

When matching listeners run synchronously, the conceptual flow is:

```text
Business processing thread
  |
  +-- publishEvent(PaymentAccepted)
        |
        +-- listener A (order = 10)
        |     +-- perform work A
        |     +-- A returns normally
        |
        +-- listener B (order = 20)
        |     +-- perform work B
        |     +-- B returns normally
        |
        +-- publishEvent(...) returns
  |
  +-- Publisher's next statement
```

In this case **listener A has finished its synchronous work** before the container calls listener B. `publishEvent` also returns only after every relevant synchronous listener completes successfully, unless an error interrupts the invocation chain.

The statement above carries important conditions: callbacks must **genuinely be synchronous**, using the default multicaster or a synchronous executor, listener A must not merely hand work to another thread and return, and we are considering **a single publish call on one thread**. With concurrent publishers, multiple application contexts, nested events, or listeners spawning their own async tasks, overall ordering requires separate analysis.

### 2.2. Four Different Kinds of "Order"

| Concept | Question | Is `@Order` enough? |
| --- | --- | --- |
| **Dispatch order** | Does the multicaster select/call A before B? | Can be guided via `@Order` / `Ordered` |
| **Start order** | Does business code A actually start running before code B? | Not guaranteed when the executor has multiple threads |
| **Completion order** | Does A finish processing and updating resources before B finishes? | Not guaranteed by `@Order` when async |
| **Commit / durability order** | Does A's transaction commit durably before B reads data? | Requires dedicated transaction boundaries, storage, and protocols |

Precisely because of these four distinct meanings, saying "we added `@Order` so listeners run in the right order" is imprecise. You must specify **which order** and **under what conditions**.

### 2.3. Where Does `@Order` Work?

Example declaring two synchronous listeners:

```java
@Component
class PaymentListeners {

    @EventListener
    @Order(10)
    public void reserveInventory(PaymentAccepted event) {
        // Handle inventory reservation.
    }

    @EventListener
    @Order(20)
    public void sendConfirmation(PaymentAccepted event) {
        // Handle notification.
    }
}
```

This is an **illustrative snippet** requiring a `PaymentAccepted` definition and imports for `@Component`, `@EventListener`, and `@Order`. With a synchronous multicaster, the same event, and no errors, the order 10 listener is invoked before order 20. Still, designing "send confirmation" to depend on "reserve inventory" via event listener ordering can create implicit coupling; in critical business logic, use an explicit orchestrating service and verifiable transactional state.

For equal order values or unordered listeners, never assume an order based on class name, file layout, or component scan timing.

## 3. What Changes When Moving to Asynchronous Execution?

### 3.1. `@Async` on `@EventListener`

When a listener uses `@Async`, calls to it can be routed by a Spring proxy to another executor:

```java
@Component
class NotificationListener {

    @Async("eventExecutor")
    @EventListener
    @Order(20)
    public void notifyCustomer(PaymentAccepted event) {
        // Executed by eventExecutor when @EnableAsync is active.
    }
}
```

This is an **illustrative snippet**, not a standalone program. It requires `@EnableAsync` and an `Executor` bean named `eventExecutor`. `@Async` normally works through a Spring proxy, so self-invocation (one method calling an `@Async` method on the same object) does not trigger async advice like a call passing through the proxy.

In an async setup:

```text
Publishing thread:
  publishEvent(event)
    +-- submit listener A task to executor
    +-- submit listener B task to executor
  return

Thread executor-1: listener A ──────────────── finishes
Thread executor-2:      listener B ─── finishes
```

B can start and finish **before A finishes**, even though A has `@Order(10)` and B has `@Order(20)`. Depending on OS/pool scheduling, B can even start executing before A. Here `@Order` participates only in **dispatch/enqueue order per the multicaster**, not as a `join()` barrier between the two tasks.

Do not equate "`publishEvent` returned" with "listeners finished." Moreover, **there is no guarantee** the publisher always returns cleanly when dispatching to an executor: a shut-down, saturated, or rejecting executor can throw `TaskRejectedException` right at submission time.

### 3.2. Executor at the ApplicationEventMulticaster Level

Spring Framework allows configuring `SimpleApplicationEventMulticaster` with `setTaskExecutor(...)`. By default, without an async executor specified, listeners run on the publisher's thread. Once an async executor is attached, **many eligible listeners** are offloaded to the executor; the effect can span numerous events/listeners across the context.

Distinguish clearly:

- **`@Async` on a single listener**: makes execution asynchronous for the listener method intercepted by Spring AOP; other listeners are not automatically turned async just because one listener has `@Async`.
- **Executor on `applicationEventMulticaster`**: an async choice at the **multicaster level**, potentially altering behavior across a much broader set of listeners, including framework events published in the context.
- **Manually calling an executor/`CompletableFuture` inside a listener**: the listener may return early even though the callback itself was invoked synchronously by the multicaster; another async layer was created inside.

Avoid accidentally stacking two async layers (async multicaster plus `@Async` on methods) when unnecessary: double submission across executors makes ordering, error handling, and shutdown even harder to observe.

### 3.3. `ApplicationListener.supportsAsyncExecution()` Since Spring 6.1

Not **every** listener can be moved to another thread via multicaster configuration. In Spring Framework 6.1, `ApplicationListener` defines `supportsAsyncExecution()`. A listener returning `false` must be invoked on the publisher thread, even if the multicaster is configured as async.

Crucial case: **`TransactionalApplicationListener`** (the basis of transactional event listening) does not support offloading the transaction synchronization registration step itself to an arbitrary executor. The **target** callback executing after the transaction can still run async logic under its own configuration, yet interacting with the original transaction requires the proper thread context.

Example of a listener requiring synchronous invocation:

```java
public final class StrictListener implements ApplicationListener<DomainEvent> {

    @Override
    public boolean supportsAsyncExecution() {
        return false;
    }

    @Override
    public void onApplicationEvent(DomainEvent event) {
        // Callback must be invoked by the multicaster on the publisher thread.
    }
}
```

This is an **illustration** with `DomainEvent` extending `ApplicationEvent`; it requires importing `org.springframework.context.ApplicationListener` and defining the event class. That method applies to interface-implementing listener instances in Spring 6.1. **It does not automatically make all other listeners synchronous**, nor does it stop code inside the listener from spawning its own async tasks.

### 3.4. Impact on Startup and Readiness

Spring Boot publishes events like `ApplicationStartedEvent` and `ApplicationReadyEvent` during the `SpringApplication.run(...)` lifecycle. If a ready listener merely **offloads async work** and returns, Boot can finish startup while that work is still running.

Never assume:

```text
ApplicationReadyEvent published
    => all async listeners have finished
    => cache/broker/external API is ready
```

Those inferences are false. If a step must complete **before ready**, use a runner or startup coordinator with explicit completion/timeouts; relying on an async listener and hoping `@Order` helps is insufficient.

**Note on bootstrap events:** several of Spring Boot's earliest events are published **before `ApplicationContext` exists**. A context-managed `applicationEventMulticaster` bean does not replace all of that early dispatch mechanism. Early listeners must be registered through `SpringApplication` mechanisms (such as `addListeners` or appropriate metadata), not just by annotating `@Component` and expecting `ApplicationStartingEvent`.

## 4. What Is Guaranteed When Listeners Remain Synchronous?

If two listeners handle the same event, use the default synchronous multicaster, have distinct orders, do not publish nested events, and do not spawn async work themselves, you can expect:

1. Spring picks listener A (order 10) before B (order 20).
2. A is invoked and completes normally.
3. B is invoked and completes normally.
4. The `publishEvent(...)` call returns.

This guarantee holds **within a single publish invocation**, not as global serialization across all publisher threads.

### 4.1. Concurrent Publishers

If two HTTP requests concurrently call `publishEvent(event1)` and `publishEvent(event2)`, each request can run its own event's listeners on its own thread. Therefore:

```text
Request-1: A(event1) -> B(event1)
Request-2: A(event2) -> B(event2)
```

The two sequences **can interleave** across threads. A synchronous multicaster is not a global single-ordered event queue across all requests.

### 4.2. Nested Event Publication

If listener A calls `publishEvent(eventY)` synchronously while processing event X, Y's listeners can run **before A finishes processing X**. Hence callbacks can nest:

```text
publish(X)
  A(X) starts
    publish(Y)
      C(Y)
    publish(Y) returns
  A(X) finishes
  B(X)
```

X's `@Order` does not establish a combined total order across all callbacks of X and Y.

### 4.3. Thread Context When Switching to Async

When a callback switches threads, thread-local data normally does not travel along:

- Active transactions bound to the publisher thread.
- Security context depending on environment/configuration.
- MDC/tracing correlation IDs without explicit context propagation.
- Request-scoped data, locale, classloader, or thread-bound resources.
- Locks or ThreadLocal state implicitly used by business code.

A `TaskDecorator` or context-propagating executor can help forward **certain** appropriate contexts, yet you **must not** directly copy a thread-local transaction onto a worker pretending it is the same transaction. For async tasks, design separate transaction boundaries and pass data via immutable payloads/IDs.

## 5. Complete Example — Java 21 and Spring Boot 3.3.13

The program demonstrates both mechanisms inside **a single non-web application**:

- **SyncSignal:** two synchronous `@EventListener` methods with `@Order(10)` and `@Order(20)`. `publishEvent` returns after both have executed.
- **AsyncSignal:** two `@Async("eventExecutor")` listeners that also carry `@Order`, running on a thread pool with **2 workers**. The first listener is held back with a `CountDownLatch`, allowing the second listener to finish first. The program **actively coordinates with timeout-bounded latches** to prove the point instead of relying on `Thread.sleep(...)`.
- **Ready event:** the milestone Boot publishes when `ApplicationRunner` finishes, which must not be taken as proof for unawaited async tasks.

### 5.1. Project Structure

```text
listener-order-demo/
├── pom.xml
└── src/main/java/com/example/listeners/
    ├── ListenerOrderApplication.java
    ├── Signals.java
    ├── AsyncConfiguration.java
    ├── SyncHandlers.java
    ├── AsyncHandlers.java
    ├── DemoRunner.java
    └── ReadyObserver.java
```

### 5.2. Maven

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>listener-order-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring Boot 3.3 uses Spring Framework 6.1 and is compatible with JDK 21. The example needs only the base starter, with no database or web server.

### 5.3. Defining Two Payload Events

File `src/main/java/com/example/listeners/Signals.java`:

```java
package com.example.listeners;

record SyncSignal(String id) {
}

record AsyncSignal(String id) {
}
```

Both `record` types are **package-private**, valid when placed together in `Signals.java`. They are payload objects and do not need to extend `ApplicationEvent`: Spring can accept objects passed to `publishEvent(Object)` and wrap them in `PayloadApplicationEvent` when needed. Listeners can declare the record type directly as a parameter.

### 5.4. Main Class

File `src/main/java/com/example/listeners/ListenerOrderApplication.java`:

```java
package com.example.listeners;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class ListenerOrderApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(ListenerOrderApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        // Close context after runner finishes so the executor is cleaned up.
        try (ConfigurableApplicationContext context = app.run(args)) {
            // No need to publish here: DemoRunner will handle it.
        }
    }
}
```

The application opens no HTTP port. `ApplicationRunner` is invoked by Boot during `app.run(args)`; `try-with-resources` closes the context after `run` returns.

### 5.5. Configuring the Executor for @Async

File `src/main/java/com/example/listeners/AsyncConfiguration.java`:

```java
package com.example.listeners;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncConfiguration {

    @Bean("eventExecutor")
    public ThreadPoolTaskExecutor eventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("event-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(5);
        return executor;
    }
}
```

`@EnableAsync` enables Spring's async method interception. The executor has **2 workers**, so two listeners can run concurrently. Queue capacity 16 bounds pending tasks; in production, additionally configure rejection policies, metrics, saturation handling, and appropriate timeouts rather than an unbounded pool.

**Do not misunderstand:** an executor bean named `eventExecutor` **does not automatically make all event listeners async**. The demo only moves methods annotated with `@Async("eventExecutor")` onto the executor. `SyncHandlers` still runs synchronously.

### 5.6. Two Ordered Synchronous Listeners

File `src/main/java/com/example/listeners/SyncHandlers.java`:

```java
package com.example.listeners;

import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
public class SyncHandlers {

    @EventListener
    @Order(10)
    public void first(SyncSignal event) {
        System.out.println("SYNC first");
    }

    @EventListener
    @Order(20)
    public void second(SyncSignal event) {
        System.out.println("SYNC second");
    }
}
```

`SyncHandlers` **has no `@Async`**, and the demo does not customize a global multicaster. Therefore when `SyncSignal` is published from the runner, callbacks execute on the publisher's thread in `@Order` sequence.

### 5.7. Two Async Listeners and Latches Proving Out-of-Order Completion

File `src/main/java/com/example/listeners/AsyncHandlers.java`:

```java
package com.example.listeners;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

@Component
public class AsyncHandlers {

    private final CountDownLatch firstEntered = new CountDownLatch(1);
    private final CountDownLatch allowFirstToFinish = new CountDownLatch(1);
    private final CountDownLatch firstFinished = new CountDownLatch(1);
    private final CountDownLatch secondFinished = new CountDownLatch(1);

    @Async("eventExecutor")
    @EventListener
    @Order(10)
    public void first(AsyncSignal event) {
        firstEntered.countDown();

        try {
            if (!allowFirstToFinish.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("first handler timed out");
            }
            System.out.println("ASYNC first finished");
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("first handler interrupted", ex);
        }
        finally {
            firstFinished.countDown();
        }
    }

    @Async("eventExecutor")
    @EventListener
    @Order(20)
    public void second(AsyncSignal event) {
        System.out.println("ASYNC second finished");
        secondFinished.countDown();
    }

    public void verifyAndRelease() throws InterruptedException {
        // Wait for both first to start and second to finish.
        boolean firstStarted = firstEntered.await(10, TimeUnit.SECONDS);

        try {
            if (!firstStarted || !secondFinished.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("async listeners not scheduled");
            }

            if (firstFinished.getCount() != 1) {
                throw new IllegalStateException("first already finished unexpectedly");
            }

            System.out.println("CHECK: second completed while first waits");
        }
        finally {
            // Release first even if check fails.
            allowFirstToFinish.countDown();
        }

        if (!firstFinished.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("first did not finish");
        }
    }
}
```

Both `first` and `second` are `public`, invoked through the Spring bean proxy rather than self-invocation. Because the executor has two threads, `second` can finish while `first` is waiting on the latch. `verifyAndRelease()` waits and checks with timeouts, so the demo does not rely on non-deterministic sleep durations.

Note: `@Async` with a `void` return type does not propagate listener exceptions back to the thread calling `publishEvent`; production code must have an `AsyncUncaughtExceptionHandler`, logging, monitoring, and suitable retry or failure policies. The demo uses latches solely to prove ordering behavior on the happy path, not as a production synchronization library.

### 5.8. Runner Publishing Both Sync and Async Events

File `src/main/java/com/example/listeners/DemoRunner.java`:

```java
package com.example.listeners;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class DemoRunner implements ApplicationRunner {

    private final ApplicationEventPublisher publisher;
    private final AsyncHandlers asyncHandlers;

    public DemoRunner(
            ApplicationEventPublisher publisher,
            AsyncHandlers asyncHandlers) {
        this.publisher = publisher;
        this.asyncHandlers = asyncHandlers;
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        System.out.println("SYNC publish");
        publisher.publishEvent(new SyncSignal("demo"));
        System.out.println("SYNC returned");

        System.out.println("ASYNC publish");
        publisher.publishEvent(new AsyncSignal("demo"));
        System.out.println("ASYNC returned");

        asyncHandlers.verifyAndRelease();
        System.out.println("RUNNER finished");
    }
}
```

`DemoRunner` is invoked after context refresh. It deliberately **awaits the async handlers via latches before returning**, so `RUNNER finished` and the ready event appear only after `first` and `second` finish **in this example**. If you remove `verifyAndRelease()`, the ready event can be published while async listeners have not yet completed.

### 5.9. Observing ApplicationReadyEvent

File `src/main/java/com/example/listeners/ReadyObserver.java`:

```java
package com.example.listeners;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ReadyObserver {

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("BOOT ready");
    }
}
```

This listener is **synchronous** and prints only after Boot finishes calling runners. If the runner does not await async tasks, `BOOT ready` **does not prove** those tasks completed. The right design must start from readiness policies and required preconditions.

### 5.10. Running Commands

Install JDK 21 and Maven; from the `listener-order-demo` directory:

```bash
java -version
mvn -version
mvn package
java -jar target/listener-order-demo-0.0.1-SNAPSHOT.jar
```

You can replace `mvn package` and running the JAR with `mvn spring-boot:run`. Actual logs include banners and Spring Boot messages; below are **the lines printed by the example**, not the complete stdout.

**Deterministic synchronous order:**

```text
SYNC publish
SYNC first
SYNC second
SYNC returned
```

**Controlled relationships in the async section:**

- `ASYNC publish` precedes the `publishEvent(new AsyncSignal(...))` call.
- `ASYNC returned` prints after the publish call has submitted callbacks, **which does not mean both callbacks have finished**.
- `ASYNC second finished` appears before `CHECK: second completed while first waits`.
- `CHECK: second completed while first waits` appears before `ASYNC first finished`, because the runner releases the latch only after printing the check line.
- `ASYNC first finished` appears before `RUNNER finished`.
- `RUNNER finished` appears before `BOOT ready`, because runners complete before `ApplicationReadyEvent`.

**No absolute stdout order is guaranteed** between `ASYNC returned` and `ASYNC second finished`: threads can be scheduled differently. Nor can you use the fact that `first` has `@Order(10)` to conclude `first` will **finish** before `second` with `@Order(20)` — the demo intentionally demonstrates the opposite.

If you lower the executor to one thread, the two async callbacks may serialize on that executor, yet that is merely a local property of the queue/worker, not a guarantee of transaction order, global order across multiple publishers, or order across multiple service instances.

## 6. Two Ways to Enable Async and Scope Consequences

### 6.1. Preferred Approach When Only Specific Listeners Should Be Async

Use `@EnableAsync`, a bounded executor, and `@Async("eventExecutor")` on **the exact listener methods** you want offloaded to the background. No change to the context-wide `applicationEventMulticaster` is needed.

This reduces the risk of accidentally shifting framework listeners, startup events, or transactional listeners onto another thread. Even so, async listeners still require exception management, context propagation, retries, and shutdown handling.

### 6.2. Configuring a Global Multicaster: Weigh Carefully

**The following snippet is an alternative option; do not combine it with the Section 5 demo**, because it changes semantics for the entire context's event multicaster:

```java
@Configuration(proxyBeanMethods = false)
class GlobalEventMulticasterConfig {

    @Bean(name = "applicationEventMulticaster")
    SimpleApplicationEventMulticaster eventMulticaster(
            @Qualifier("eventExecutor") java.util.concurrent.Executor executor) {

        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();
        multicaster.setTaskExecutor(executor);
        return multicaster;
    }
}
```

To use it, import `@Configuration`, `@Bean`, `@Qualifier`, and `org.springframework.context.event.SimpleApplicationEventMulticaster`, alongside a valid `eventExecutor` bean. This is an **additive snippet inside a Spring app**, not standalone.

Caveats:

- The bean name must be **`applicationEventMulticaster`**, per `AbstractApplicationContext` convention.
- A multicaster with an executor can dispatch eligible listeners asynchronously **across the entire context**, not only your domain events.
- Listeners with `supportsAsyncExecution() == false` must still be invoked on the publisher thread.
- Very early events published before the context exists are not governed by a context-created multicaster bean by default.
- Exceptions on workers might not propagate to the publisher; you can configure `setErrorHandler(...)` to log/suppress/propagate as required, though an error handler **is not** a mechanism to roll back the original transaction.
- Changing the global multicaster can affect startup, shutdown, and third-party library listeners. Enable it only after auditing the listeners your application **actually** uses and adding appropriate tests.

### 6.3. Does a Single-Thread Executor Solve All Ordering Problems?

**No.** A single-thread executor can run **tasks submitted to that exact queue** sequentially according to executor policy, yet it does not guarantee:

- Every event in the application goes through that queue.
- Events published from multiple threads follow an absolute business order.
- Synchronous listeners and transactional listeners run on that worker.
- Events in another process or another Kafka/RabbitMQ partition share the same order.
- A's data updates have committed before B reads them.
- Retries, timeouts, shutdown, or task rejections never alter observed ordering.

A single-thread executor also introduces bottleneck, backlog, and head-of-line blocking risks. It can be an appropriate implementation tool in a narrow scope, but it does not replace data contracts or an ordered state machine.

## 7. Transactions and @TransactionalEventListener: Key Limitations

### 7.1. Events Can Be Published Inside a Transaction

Suppose:

```java
@Transactional
public void acceptPayment(String id) {
    repository.markPaid(id);
    publisher.publishEvent(new PaymentAccepted(id));
}
```

This is an **architectural illustration**, not a standalone program; it needs a repository and event type. `publishEvent` runs **inside the transactional method call**, yet when callbacks execute depends on listener type.

- A synchronous `@EventListener` usually runs on the publisher thread and can see the active transaction.
- An `@Async` listener runs on another thread without inheriting the thread-local transaction; it can read data before the publisher's transaction commits.
- A `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` registers a callback bound to the transaction; processing triggers after the transaction commits successfully per the chosen phase.

**Never use `@Order` to ensure an async listener sees committed data.** That is a transaction-boundary and data-consistency problem, not merely a callback-ordering issue.

### 7.2. `@TransactionalEventListener` and an Async Multicaster

Spring Framework 6.1 specifies that transactional listeners **do not allow a multicaster to move transaction-synchronization registration onto another thread**: `TransactionalApplicationListener.supportsAsyncExecution()` returns `false`. Once the transaction finishes, the target callback is processed according to its phase.

This **does not mean** every target callback of `@TransactionalEventListener` can never be async: if an async proxy is placed on the post-commit handler method, the target work itself can run asynchronously. In that case, you must again account for thread context, exception handling, completion order, and post-commit data visibility.

An event published outside a transaction may not trigger a transactional listener unless fallback execution is explicitly enabled. Do not treat transactional listeners as a thoughtless replacement for regular startup/domain events.

### 7.3. When Work Must Not Be Lost

An in-memory async listener is not a durable queue. If the JVM dies after the publisher commits to the DB but before the async task finishes, the task can be lost.

For work requiring zero loss and ordering per business key, consider:

1. **Transactional outbox**: persist business state and an event/outbox record inside the same database transaction.
2. A separate worker/publisher forwards events to a broker or processes them with replay support.
3. **Key-based ordering** (such as `orderId` or `customerId`) via partitions or serialized workflows; avoid promising global ordering across all keys.
4. **Idempotent** consumers managing retries, duplicates, and processed state.
5. Monitoring latency, backlog, poison messages, and dead-letter policies.

This is an **additional architecture for distributed business problems**, not a capability that magically appears by adding `@Async` or `@Order`.

## 8. When A Must Finish Before B, How Should You Design It?

### 8.1. If A and B Belong to One Flow and Must Be Sequential: Call Explicitly

Instead of two independent listeners receiving one event and relying on order:

```java
public void handleBusinessFlow(PaymentAccepted event) {
    inventoryService.reserve(event.paymentId());
    confirmationService.sendAfterReservation(event.paymentId());
}
```

This is an **illustrative snippet** requiring a `PaymentAccepted` record with `paymentId()`, corresponding services, transaction handling, timeouts, and notification policies. This approach clarifies "send confirmation depends on reservation succeeding" and sits cleanly in a workflow/service—not relying on two listeners happening to carry orders 10 and 20.

### 8.2. If Async Is Desired Yet A Must Still Finish Before B: Compose Futures

Java 21 example:

```java
CompletableFuture<Void> flow =
        CompletableFuture.runAsync(() -> reserveInventory(paymentId), executor)
                .thenRunAsync(() -> sendConfirmation(paymentId), executor);

flow.orTimeout(10, TimeUnit.SECONDS).join();
```

This is an **illustrative, non-standalone snippet** requiring imports for `CompletableFuture`, `TimeUnit`, variable `executor`, `paymentId`, and both methods. `thenRunAsync` runs only after the first stage succeeds. `join()` awaits completion (or throws an exception), bounded by `orTimeout`.

If you do not want to block the request thread, **do not call `join()` there**; return the future or let a workflow/worker manage completion and report status. `CompletableFuture.allOf(A, B)` merely waits for both to finish—it **does not** make B wait for A. Use `thenCompose` when stage A returns a new future to chain further.

**Note:** A completing as a `CompletableFuture` does not guarantee A's transaction has committed if you complete the future too early. Ensure the completion signal reflects the exact transaction/protocol milestone B requires.

### 8.3. If You Only Want to Order Synchronous Listeners

If listeners are genuinely independent yet need callback ordering for lightweight logging/auditing, synchronous `@EventListener` + `@Order` works well. Keep callbacks fast, put timeouts on I/O, and measure execution time because they block the publisher's thread.

If B's outcome depends deeply on A, an explicit orchestrator or dependency remains easier to maintain.

### 8.4. If Ordering Is Required Across Multiple JVMs/Services

Ordering listeners inside **one** `ApplicationContext` provides no constraint across other nodes. Use queues/streams ordered by business key, state machines, sequence numbers, outbox/transaction logs, and consumer idempotency. Clarify whether the requirement is per-key FIFO, causal order, or total order; each carries distinct costs and boundaries.

## 9. Exceptions, Cancellation, Timeouts, and Shutdown

### 9.1. Synchronous: Exceptions Usually Return to the Publisher

With the default `SimpleApplicationEventMulticaster` and no error handler swallowing errors, a runtime exception from a synchronous listener can propagate to the publisher and interrupt multicasting. If `publishEvent` is called from startup code, it can fail startup; if called inside a transaction, rollback behavior depends on exception type and transaction configuration.

Do not rely on a listener failing a transaction as a guarantee of "exactly-once events." Distinguish DB transactions from external side effects outside the DB.

### 9.2. Async: Exceptions Follow a Different Path

For an `@Async` method returning `void`, exceptions normally do not propagate directly to the publisher; they can be handled by `AsyncUncaughtExceptionHandler`. With an executor on the multicaster, `setErrorHandler` or the executor's error handling determines how errors are recorded. In both cases, the publisher may already have moved on or returned a successful response.

Therefore you must have:

- Logging tagged with event ID and trace ID.
- Metrics/counts for successes and failures.
- Bounded retry policies, delay/backoff, and deduplication.
- Handling for task rejection or pool saturation.
- Payloads containing enough data for safe processing after the publisher thread finishes.
- Shutdown/drain policies if background tasks must not be lost.

### 9.3. Ordering Under Retries

A can fail and retry later, while B has already succeeded. If the goal is "never process B before A succeeds," sorting with `@Order` is not enough. You need workflow states (PENDING_A, A_DONE, B_DONE), keyed queues, or explicit acknowledgment from A before releasing B.

### 9.4. Shutdown and Late Events

During context close, executors may stop accepting new tasks. If a listener publishes/submits to a shutting-down pool, tasks can be rejected. Do not assume every event during shutdown finishes executing; use lifecycle management and appropriate stop/drain protocols, especially for critical consumers or jobs.

## 10. Common Mistakes

| Misconception / practice | Why it is wrong or incomplete | Alternative |
| --- | --- | --- |
| `@Async` + `@Order(1)` and `@Order(2)` guarantee completion order | Executor can run in parallel; a slow task finishes later | Compose futures or use a sequential workflow |
| Returning from `publishEvent` means all work is done | Async listeners have usually only been submitted | Track future/ack/state or await bounded completion |
| Increasing priority/order fixes read-before-commit | Transactions and thread contexts do not obey `@Order` | AFTER_COMMIT/outbox or explicit transaction boundaries |
| Changing global multicaster to cut latency without testing | Affects many other listeners and events | Prefer selective async; test startup/transactions |
| Setting a single-thread executor and claiming system-wide total ordering | Only serializes the local queue | Define keys/partitions/protocols at a durable layer |
| Returning an object in an `@Async` listener to auto-publish next event | Async listener methods do not publish return values | Inject `ApplicationEventPublisher` and publish explicitly |
| `@TransactionalEventListener` gets pushed off the original transaction by async multicaster | Transaction synchronization registration must run on publisher thread | Understand `supportsAsyncExecution() == false` |
| A new `@Component` listener catches bootstrap events before context creation | Listener bean does not exist at early milestones | Register via `SpringApplication.addListeners` if needed |
| Async events inherit transactions, MDC, and request scope | Thread-locals do not cross executors automatically | Immutable payloads, intentional context propagation |
| Increasing thread count fixes all event bugs | Introduces races, backlogs, contention, duplicate updates | Bounded concurrency, idempotency, targeted ordering |
| Seeing `ApplicationReadyEvent` means all async listeners finished | Startup lifecycle ready does not `join` async listeners | Runner/coordinator awaiting essential tasks |
| Tests using `Thread.sleep(100)` and asserting order | Scheduling varies across machines and load | Latches/barriers/future completion and assertions |

## 11. Decision Checklist: Synchronous vs. Asynchronous

**Keep synchronous** when all of these hold: callbacks are short, low-cost, need immediate error feedback to the publisher, callback order within one publish is an intentional requirement, there is no long I/O, and request/startup paths are not blocked.

**Use async** when work can run independently, the publisher does not need immediate completion, a failure policy exists, data is self-contained outside thread/transaction boundaries, the executor is bounded and monitored, and listeners do not rely on completion order across each other.

**Use orchestration instead of event ordering** when B must run after A commits, independent retries or failures exist, state must survive restarts, ordering is needed across requests/instances, or completion is required before readiness. In those cases, use a service coordinator, future chain, transaction/outbox, keyed/partitioned message queue, or state machine as needed.

### Self-Check Questions

1. Do you need "A invoked before B" or "A committed successfully before B starts"?
2. Are you analyzing one event or multiple events published concurrently?
3. Do any listeners submit background tasks themselves even though the multicaster is synchronous by default?
4. Are there `@Transactional`, MDC, SecurityContext, request scope, or ThreadLocal constraints to handle?
5. When A fails, may B run? Who decides and where are errors reported?
6. If the app restarts between two steps, what persisted state lets it resume safely?
7. If the executor saturates, can events be rejected or is there backpressure?
8. If this is an essential startup step, who awaits completion before `ApplicationReadyEvent`?

## 12. Hands-On Exercises

1. Explain the four concepts: dispatch, start, completion, and commit order. Which concept does `@Order` directly affect?
2. Run the Maven demo and point out the stdout portion that is **strictly ordered** for `SyncSignal`.
3. Why can `ASYNC second finished` appear before `ASYNC first finished` even though their annotations are `@Order(20)` and `@Order(10)` respectively?
4. Why does the demo use `CountDownLatch` with timeouts instead of trying to force a race with `Thread.sleep(500)`?
5. Remove `asyncHandlers.verifyAndRelease()` in the runner. Predict the relative order of `BOOT ready` vs. async lines; why is there no completion guarantee?
6. Change `setCorePoolSize(2)` to 1. Explain the behavioral change and why latch-based tests can time out when the first worker is blocked. Restore two workers afterward.
7. If A and B are two HTTP requests publishing events concurrently with a synchronous multicaster, are all callbacks of request A guaranteed to precede request B?
8. Switch both handlers from `@Async` to synchronous. Predict the effect of `@Order` and the potential deadlock in the latch-based demo.
9. Create a listener implementing `ApplicationListener` whose `supportsAsyncExecution()` returns `false`. How does an async multicaster treat it?
10. Why must `@TransactionalEventListener` register transaction synchronization on the publisher thread?
11. If listener A writes to the DB inside the publisher's transaction, is an `@Async` listener B guaranteed to read that data?
12. Refactor a business flow using `thenRunAsync` so B runs only after A succeeds; add timeouts, logging, and an appropriate retry policy.
13. Does `CompletableFuture.allOf(A, B)` enforce A before B? Why or why not?
14. For critical invoice-processing events, why are an outbox, idempotency, and ordering by `invoiceId` needed instead of `@Order` on local listeners?
15. Name three reasons why a single-thread executor still does not create absolute ordering for a distributed system.
16. Write a startup runner that awaits cache warm-up completion and throws an exception on timeout to prevent a false ready signal.

**Success criteria:** clearly understand the limits of moving listeners to async, never equate `@Order` with completion or commit order, know how to configure a bounded executor, and design workflows that genuinely satisfy ordering requirements.

## 13. Official References

- Spring Framework 6.1 — `SimpleApplicationEventMulticaster` (executor, error handler, sync default, async support): https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework 6.1 — `@EventListener` (async limitations, ordering): https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/EventListener.html
- Spring Framework 6.1 — `TransactionalApplicationListener`: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/event/TransactionalApplicationListener.html
- Spring Framework — Application Events: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework — Task Execution and `@Async`: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Boot 3.3 — Application events and listeners: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
