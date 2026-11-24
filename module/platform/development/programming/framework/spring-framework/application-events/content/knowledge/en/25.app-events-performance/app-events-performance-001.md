# Cost of Publishing Events in a Request with Spring Framework Application Events

When an HTTP request or a business call uses `ApplicationEventPublisher.publishEvent(...)`, “publishing an event” **is not automatically a background operation, zero-cost, or without impact on the response**. In Spring Framework, `SimpleApplicationEventMulticaster` invokes listeners **synchronously on the publisher's own thread** by default. Therefore, if an `@EventListener` makes a slow HTTP call, runs a heavy database query, or waits on I/O, that time usually **adds to the time the request must wait**. If a synchronous listener throws an exception, the exception can propagate back to the publisher by default and affect the transaction flow.

This article analyzes the **cost of publishing events in a request** under the *Performance* topic: actual dispatch overhead, listener-induced latency, impact on throughput/thread pools/transactions, the boundary between synchronous and asynchronous execution, how to measure accurately, and optimization strategies without sacrificing consistency or reliability.

## 1. What does “publish event” actually do?

Example service:

```java
@Transactional
public void placeOrder(PlaceOrderCommand command) {
    Order order = orderRepository.save(toOrder(command));
    applicationEventPublisher.publishEvent(
            new OrderPlaced(order.getId(), command.requestId()));
}
```

This is an **illustrative integration snippet**, not standalone: the `Order`, `PlaceOrderCommand`, and repository types belong to the application. Because the `@Transactional` annotation wraps the entire service, synchronous listeners run within the **call stack** and usually also the **transaction/thread context** of the service when the event is published.

A common execution path:

```text
HTTP thread T
  |
  +-- Controller
        |
        +-- @Transactional OrderService.placeOrder(...)
              |
              +-- save(order)
              |
              +-- publishEvent(OrderPlaced)
              |     |
              |     +-- Spring selects listeners matching the event
              |     |
              |     +-- AuditListener       4 ms
              |     +-- ProjectionListener 18 ms
              |     +-- EmailListener     300 ms
              |     |
              |     +-- publishEvent(...) returns
              |
              +-- commit transaction
        |
        +-- return HTTP response
```

The numbers `4 ms`, `18 ms`, and `300 ms` are **hypothetical examples**, not Spring benchmark results. In a synchronous configuration, the request may have to wait for the total duration of the invoked listeners, plus the processing steps outside the event. A listener calling a slow external service can completely dominate latency, even though the actual **framework dispatch** overhead is small.

### Concepts to separate

| Component | What consumes time/resources? | Included in the request by default? |
| --- | --- | --- |
| Event object creation | Allocation, copying data into payload, GC under high frequency | Yes |
| `publishEvent(...)` and multicaster | Dispatching, listener selection, adapters, type/condition checks | Yes |
| Synchronous `@EventListener` | CPU, database, HTTP, logging, locks, I/O waits, handling nested events | **Yes** |
| `@TransactionalEventListener(AFTER_COMMIT)` | Registering callback; handling runs when transaction finishes per phase | **Can still slow down the request** if the callback runs synchronously on the commit thread |
| `@Async @EventListener` | Executor submission overhead, queue management; listener runs later on a worker | Usually only submission cost, **but can block or fail when the executor is overloaded** |
| Outbox + background dispatcher | Writing outbox inside transaction, worker reads/sends after commit | Writing outbox is inside the transaction; external sending is decoupled from the request |

There is no “zero cost” mechanism: offloading work from the request usually trades **latency** for the need to manage **concurrency, queues, retries, consistency, and delivery**.

## 2. Why is synchronous the default?

`ApplicationEventPublisher` provides the publish API; the actual dispatching is handled by `ApplicationEventMulticaster` in the `ApplicationContext`. By default, `SimpleApplicationEventMulticaster` runs listeners on **the thread calling publish**, equivalent to using `SyncTaskExecutor`.

Advantages:

- Simple execution flow: listener order is visible in the stack trace.
- Can participate in a thread-bound transaction alongside the publisher when compatible and on the same thread.
- Synchronous exceptions can propagate back to the publisher by default, enabling fail-fast behavior.
- Typically low work-scheduling overhead, avoiding task/queue/scheduling creation per listener.
- The publisher's ThreadLocal logging/tracing context is normally still present on the same thread.

In return:

- A slow listener prolongs the `publishEvent(...)` call.
- A listener making network calls without timeouts can hold the HTTP worker and transaction for too long.
- While listener A waits, listener B after it may be delayed.
- If a synchronous listener throws an exception without a dedicated handler, remaining listeners may not be invoked.
- If a listener holds a database transaction open while making HTTP calls, it can increase connection/lock hold times and reduce overall system throughput.

**An event having multiple listeners does not mean Spring runs them in parallel.** Under the default configuration, listeners execute on the publisher thread, except for listeners configured with their own async mechanism.

### Latency model

Let:

- `T_before`: request processing time before publish.
- `T_dispatch`: overhead of event creation/dispatching, listener lookup, adapters/filters.
- `T_listener_i`: duration of the `i`-th synchronous listener, **including all work it performs**.
- `T_after`: remaining request work and transaction/commit steps after publish.

Approximate model for a synchronous publish without parallel processing:

```text
T_publish ≈ T_dispatch + Σ T_listener_i
T_request ≈ T_before + T_publish + T_after
```

This is a **mental model**, not a constant formula applicable to every request. A listener can publish additional nested events, events can be filtered out by `condition`, transaction synchronization has post-commit callbacks, and I/O has jitter. With async, the total time a listener runs on a worker **no longer equals** the time the publisher must wait; submission, queue, and execution times must be measured separately.

One request can publish multiple times. If `N` events are published, each with multiple listeners and each listener does expensive work, total cost can grow rapidly with the number of events per request and the processing cost per listener. In a loop publishing an event per order line item, even small overhead can be multiplied significantly.

## 3. Runnable Java 17+ example: a slow listener prolongs publish

This example uses Spring Framework **6.2.9**, requiring no Spring Boot, database, or web server. It creates two independent contexts:

1. **Sync context:** two ordered `@EventListener`s; the first listener sleeps 150 ms to simulate I/O. Publisher code returns only after both listeners finish.
2. **Async context:** a listener annotated with `@Async("eventExecutor")` that sleeps 200 ms. The publisher can return before the listener finishes. The test/demo uses `CountDownLatch` to confirm the work has completed, **not an arbitrary sleep on the caller side to guess completion**.

### 3.1. Structure

```text
event-request-cost-demo/
├── pom.xml
└── src/main/java/example/EventRequestCostDemo.java
```

### 3.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>event-request-cost-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
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
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.EventRequestCostDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 3.3. src/main/java/example/EventRequestCostDemo.java

```java
package example;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class EventRequestCostDemo {

    public record OrderPlaced(String orderId) {}

    public static class OrderService {
        private final ApplicationEventPublisher publisher;

        public OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void place(String orderId) {
            publisher.publishEvent(new OrderPlaced(orderId));
        }
    }

    private static void simulateBlockingIo(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Simulated I/O interrupted", ex);
        }
    }

    public static class SlowSyncListener {
        @EventListener
        @Order(10)
        public void onOrderPlaced(OrderPlaced event) {
            simulateBlockingIo(150);
            System.out.println("sync: slow listener completed " + event.orderId());
        }
    }

    public static class FastSyncListener {
        @EventListener
        @Order(20)
        public void onOrderPlaced(OrderPlaced event) {
            System.out.println("sync: fast listener completed " + event.orderId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class SyncConfig {
        @Bean
        OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }

        @Bean
        SlowSyncListener slowSyncListener() {
            return new SlowSyncListener();
        }

        @Bean
        FastSyncListener fastSyncListener() {
            return new FastSyncListener();
        }
    }

    public static class AsyncListener {
        private final CountDownLatch completed;

        public AsyncListener(CountDownLatch completed) {
            this.completed = completed;
        }

        @Async("eventExecutor")
        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            try {
                simulateBlockingIo(200);
                System.out.println(
                        "async: listener completed " + event.orderId());
            } finally {
                completed.countDown();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class AsyncConfig {
        @Bean
        OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }

        @Bean
        CountDownLatch completed() {
            return new CountDownLatch(1);
        }

        @Bean
        AsyncListener asyncListener(CountDownLatch completed) {
            return new AsyncListener(completed);
        }

        @Bean(name = "eventExecutor")
        ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("event-");
            executor.initialize();
            return executor;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        try (var context =
                     new AnnotationConfigApplicationContext(SyncConfig.class)) {
            System.out.println("sync: before publish");
            long start = System.nanoTime();

            context.getBean(OrderService.class).place("PO-1");

            long elapsed = System.nanoTime() - start;
            System.out.println("sync: after publish");
            System.out.println(
                    "sync: includes blocking work="
                            + (elapsed >= TimeUnit.MILLISECONDS.toNanos(100)));
        }

        try (var context =
                     new AnnotationConfigApplicationContext(AsyncConfig.class)) {
            System.out.println("async: before publish");

            context.getBean(OrderService.class).place("PO-2");

            System.out.println("async: publish returned");
            boolean finished = context.getBean(CountDownLatch.class)
                    .await(5, TimeUnit.SECONDS);
            if (!finished) {
                throw new IllegalStateException("Async listener timed out");
            }
            System.out.println("async: completion confirmed");
        }
    }
}
```

Run from the directory containing `pom.xml`; requires JDK 17+, Maven, and dependency download access on the first run:

```bash
mvn -q compile exec:java
```

Lines printed by the program during a normal run, assuming the executor and machine are not severely stalled/degraded:

```text
sync: before publish
sync: slow listener completed PO-1
sync: fast listener completed PO-1
sync: after publish
sync: includes blocking work=true
async: before publish
async: publish returned
async: listener completed PO-2
async: completion confirmed
```

**Explanation of results:**

1. `SlowSyncListener` and `FastSyncListener` are Spring beans. `@Order(10)` and `@Order(20)` determine the invocation order of listeners in the synchronous example. The first listener simulates a 150 ms wait, so `publishEvent(...)` is blocked before printing `sync: after publish`.
2. The expression `elapsed >= 100 ms` is used only as an **illustrative check for blocking work inside publish**. This is neither a benchmark nor a fixed latency guarantee from Spring. Actual timings depend on the JVM, OS, machine load, and thread scheduling.
3. The async context enables `@EnableAsync`, providing a bounded-queue `ThreadPoolTaskExecutor` and the `AsyncListener` bean. The `@Async("eventExecutor")` method runs on the executor, while `publishEvent(...)` typically only needs to schedule the work. Because the listener simulates 200 ms of I/O, the caller usually prints `async: publish returned` before the listener completes.
4. `CountDownLatch.await(...)` lets the demo wait for **actual completion**. In a typical HTTP application, you should not call `await()` right in the controller if the goal is to reduce latency; the demo waits only to produce clear output and close the context safely.
5. The first context and the second context are **independent**, so no listener runs redundantly across both configurations. The example has no database and no transactions; do not infer from this that async preserves the publisher's transaction.
6. If the machine experiences an unusual pause, the log order between the caller and worker may change due to scheduling, and the 5-second timeout is a demo check condition, not a production SLA. Do not write tests tightly coupled to absolute timings to prove an async contract.

**Note:** in `@Async` with a `void` method, exceptions handled on the worker do not automatically propagate back to the publisher. An error handler, logging/metrics, and an appropriate retry mechanism are needed. The fact that an event method actually runs after the publisher returns **does not guarantee** the event is durably persisted.

## 4. Measuring cost properly: separating publish, listener, and request

### 4.1. Do not mistake API processing time for “Spring events overhead”

If a request takes `500 ms` after adding an event, that is not enough to conclude the event dispatcher is slow. You need to distinguish:

- `T_dispatch`: listener selection, wrapper/adapter creation, type and condition checks.
- `T_handler`: actual work inside `@EventListener` — e.g., SQL, HTTP, serialization, logging, CPU.
- `T_queue`: time the task sits in the executor queue (if async).
- `T_commit`: transaction flush, commit, synchronization callbacks.
- `T_request`: total end-to-end time from entry to response.

An example of attaching a stopwatch at the publisher:

```java
long started = System.nanoTime();
publisher.publishEvent(new OrderPlaced(orderId));
long publishNanos = System.nanoTime() - started;
metrics.recordPublishDuration(publishNanos);
```

This is an **illustrative integration snippet**, depending on the application's `publisher`, `metrics`, and `orderId` beans.

With a synchronous multicaster, `publishNanos` includes **listener execution latency** and dispatch, not pure Spring overhead alone. With async, it may only measure the time to enqueue the task, not completion. If the goal is to identify bottlenecks, you need to instrument **the processing inside each listener** as well as the total HTTP request.

### 4.2. Spring does not automatically create an Observation per @EventListener

According to the Spring Framework documentation, `@EventListener` does not have **automatic Micrometer Observation** by default. If you need metrics/traces for a listener, you can create an observation manually:

```java
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    Observation.createNotStarted("application.event.listener", registry)
            .lowCardinalityKeyValue("event.type", "OrderPlaced")
            .lowCardinalityKeyValue("listener", "InvoiceProjection")
            .highCardinalityKeyValue("event.id", event.eventId())
            .observe(() -> projectionService.update(event));
}
```

This is an **illustrative integration snippet**, requiring the `OrderPlaced`, `projectionService`, `registry` types and Micrometer imports. This snippet cannot be copied into the single-field `OrderPlaced` class in section 3 because the demo record only has `orderId()`; here it represents a production event with `eventId()`.

When the application has an `ObservationRegistry`, handlers, and suitable exporters (such as Spring Boot Actuator + Micrometer), the observation can contribute metrics/tracing. Merely calling `createNotStarted` does not automatically export Prometheus meters or OpenTelemetry spans.

Do not attach `eventId`/`orderId`/email to **low-cardinality metric tags**. These values typically create a new time series per event, causing cardinality explosion; only use them in logs/traces/high-cardinality metadata when appropriate.

### 4.3. Signals worth monitoring

| Signal | What it measures | Why it is useful |
| --- | --- | --- |
| HTTP request duration, p50/p95/p99 | End-to-end latency | Verifies whether events actually prolong responses |
| Event publish duration | Time from calling publish until return | Shows impact on caller; must be interpreted for sync vs. async |
| Listener processing duration | Start-to-end time of listener work | Identifies slow listeners, separates CPU/I/O |
| Listener failure rate | Error count by bounded event/listener type | Detects swallowed errors in async |
| Executor active threads / queue depth | Load and backlog | Reveals whether async is actually keeping up |
| Rejected tasks | Number of submitted tasks rejected | Detects lost work when the executor is full |
| Outbox lag / oldest pending age | Delay from data commit to event processing | Measures business eventual consistency latency |
| Database connection/lock wait | Transaction resource contention | Reveals indirect consequences of synchronous listeners |

Distinguish **publish duration** from **listener processing duration**. If a dashboard only has publisher metrics, an async listener taking 3 seconds may not appear in publisher latency at all.

### 4.4. Microbenchmarks differ from end-to-end load tests

To measure **pure framework overhead** when a handler performs only a trivial operation, a benchmark with warmup/JIT, allocation measurement, and GC control (e.g., JMH) can be useful. However, it does not replace real HTTP request testing.

To measure **in-request impact**, you need a load test with representative traffic: real listener counts, database connections, thread pools, payload sizes, logging/tracing, and external errors/timeouts. Compare request p95/p99 and throughput before and after changes; also measure whether listeners complete within their SLA, not just whether the API returns faster.

**Do not draw performance conclusions from a single `System.nanoTime()` call.** The demo in section 3 illustrates blocking semantics, not benchmark figures for every workload.

## 5. Transactions: lock and connection hold costs can exceed direct latency

With the code:

```java
@Transactional
public void placeOrder(Command command) {
    orderRepository.save(...);
    eventPublisher.publishEvent(new OrderPlaced(...));
}
```

This is **illustrative code**, where `...` represents omitted domain code.

If a synchronous `@EventListener` calls a slow API while the transaction is still open:

- The connection may still be held.
- Locks may be held longer, increasing `lock wait` for other transactions.
- Transaction timeouts may occur under high load.
- The request thread is occupied longer, reducing the number of requests that can be served concurrently.
- When an event listener publishes additional events or calls repositories, the transactional scope can become hard to predict.

The consequence is **not just** that the request slows down by the exact external API duration: holding resources can slow down **many other requests simultaneously**, creating a cascading effect.

If an action is a **business invariant that must be verified before commit**, do not arbitrarily move it to async just to reduce HTTP latency. For example, mandatory inventory checks or quota enforcement should not become fire-and-forget listeners lacking transaction consistency. Handle them explicitly within the use case/transaction or design a proper saga/compensation flow.

If a side effect **is only allowed after commit**, consider `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` or writing to an outbox. However:

**`AFTER_COMMIT` does not automatically mean async.** Transaction callbacks can run synchronously when commit finishes, on the request-handling thread; a slow post-commit listener making HTTP calls can still extend the time before the response is sent. You must measure according to the actual transaction manager and listener configuration.

### Transaction phases

| Phase | When it runs | Impact/limitations |
| --- | --- | --- |
| `BEFORE_COMMIT` | Before commit | Slow work can prolong the transaction and request time |
| `AFTER_COMMIT` | After successful commit | Cannot roll back the committed transaction; synchronous callbacks can still block |
| `AFTER_ROLLBACK` | After rollback | React/alert on failure; avoid masking the root cause of rollback |
| `AFTER_COMPLETION` | After commit or rollback completes | Cleanup/status observation; do not treat every completion as success |

`@TransactionalEventListener` defaults to `AFTER_COMMIT` and defaults to `fallbackExecution = false`: if published outside a suitable transaction, the listener does not run. With reactive transactions, the context resides in Reactor Context and events need to carry the transaction context via supported mechanisms; ThreadLocal assumptions from imperative examples do not apply as-is.

## 6. Moving to async: latency is shifted, not eliminated

Two common approaches:

1. **`@Async` on a specific `@EventListener`.**
2. **A custom `SimpleApplicationEventMulticaster` with a `TaskExecutor`**, affecting listeners that support async execution.

Do not switch every listener to async just because one listener is slow. Listeners relying on the caller's transaction and listeners that do not support async execution have distinct semantics; Spring 6.2 specifies that some listeners, such as transaction-synchronized listeners, **still run on the publisher thread** even when the multicaster is configured with an executor.

### 6.1. @Async on a listener

```java
@Async("notificationExecutor")
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    notificationGateway.send(event);
}
```

This is an **illustrative integration snippet**. It requires `@EnableAsync`, the `notificationExecutor` bean, and corresponding dependencies.

Advantage: the request typically does not have to wait for the notification-sending operation. However:

- Exceptions from the listener do not automatically propagate back to the caller to trigger a rollback.
- The executor has a finite number of threads/queue capacity; when overloaded, it can reject tasks or cause other pressure.
- ThreadLocal transaction/MDC/tracing context is not propagated across to another thread by default.
- If the process crashes after publishing but before the task executes, the event **can be lost**.
- If the listener accesses lazy-loaded JPA entities, running outside the original transaction/thread can fail or read inconsistent state.
- An async listener cannot publish new events via the **return value of `@EventListener`**; it must call the publisher explicitly.

Specifically, the `@Async` annotation must be processed by Spring AOP; calling an async method directly on `this` (self-invocation) can bypass the proxy, causing the method to still run synchronously. In the section 3 example, the event multicaster invokes a Spring-managed listener through the listener registration mechanism, not a manual self-invocation call.

### 6.2. Bounded executor queues and backpressure

Suppose an endpoint receives an average of `λ` events/second, a pool has `c` workers, and each listener takes an average of `s` seconds. Nominal processing capacity with zero overhead and uniform load is roughly `c/s` tasks/second. If events arrive faster than processing capacity over a sustained period, the backlog will grow and cannot be solved with an unbounded queue.

```text
Request threads
     |
     +-- publishEvent(...)
              |
              +-- executor.submit(task)
                        |
                        +-- bounded queue (pending work)
                               |
                               +-- worker threads
                                      |
                                      +-- listener I/O / CPU
```

When the queue is full, the executor/rejection policy determines what happens. It may fail with `TaskRejectedException`/`RejectedExecutionException` or apply another configured policy. If `CallerRunsPolicy` is used, tasks may run on the **request thread**, causing latency to spike again under load. Therefore, “async is always fast” is a false conclusion.

Decisions that must be made:

- **Core/max pool size** suited to CPU-bound/I/O-bound workloads and resource budgets.
- **Bounded queue capacity**, with backlog/rejection metrics.
- **Timeouts** for external I/O and concurrency limits.
- **Bounded retry/backoff**, avoiding retry storms.
- **Shutdown semantics**: what happens to tasks remaining in the queue when the application stops?
- **Handling task loss**: if critical events must be durably persisted, an in-memory executor queue is not enough.

### 6.3. TaskDecorator and context propagation

Moving a listener to another thread can lose the current observation, MDC, and trace context. Spring supports `ContextPropagatingTaskDecorator` along with Micrometer Context Propagation to help transfer context in suitable executors.

```java
@Bean("notificationExecutor")
ThreadPoolTaskExecutor notificationExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("notify-");
    executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
    executor.initialize();
    return executor;
}
```

This is an **illustrative integration configuration**, not a file from the section 3 demo; it requires Spring imports, the `io.micrometer:context-propagation` dependency, and appropriate context accessors. Context propagation **does not transfer the request's imperative transaction to the worker** and does not replace commit guarantees, retries, or durable storage.

## 7. Custom multicaster: use only when you understand the global impact

If you want listeners that support async execution to run on an executor at the event bus level:

```java
@Configuration
public class EventBusConfiguration {

    @Bean(name = "applicationEventMulticaster")
    SimpleApplicationEventMulticaster applicationEventMulticaster(
            @Qualifier("eventExecutor") TaskExecutor eventExecutor) {

        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();
        multicaster.setTaskExecutor(eventExecutor);
        return multicaster;
    }
}
```

This is an **illustrative configuration**, not a standalone class; it requires `TaskExecutor`, `@Qualifier`, `@Bean`, `@Configuration`, and an executor bean. Do not create this configuration without a clear reason.

Impacts to review:

- It can change the timing of **many** listeners, not just the slow notification listener.
- Exceptions from listeners running on the executor **do not necessarily propagate** to the publisher thread.
- Thread-bound transaction context is not automatically carried over to the executor.
- Listeners declaring `supportsAsyncExecution() == false` still run on the publisher thread, such as Spring Framework 6.2 transaction-synchronized listeners.
- Completion order no longer equates to registration order or `@Order`.
- If the multicaster has a custom `ErrorHandler`, swallow/log/propagate behavior may change; error paths must also be tested.

**Prefer moving specific listeners to async** when only an independent task needs to be offloaded. Changing the global multicaster is an architectural decision with broad impact on the entire application's semantics.

## 8. Systematic optimization, avoiding business-breaking “quick fixes”

A pragmatic sequence:

### Step 1 — Identify which handler is actually consuming time

Instrument the request and each listener. Look at p95/p99, error rates, SQL/queries, cache hits, network time, lock waits, and GC. A listener may be slow due to N+1 queries, connection pool exhaustion, or external API calls missing timeouts, rather than the event dispatch mechanism itself.

### Step 2 — Separate work types by consistency requirements

| Work type | Typically appropriate approach |
| --- | --- |
| Pre-commit invariant checks, business rule validation | Execute explicitly and synchronously in the use case/transaction; do not fire-and-forget |
| Secondary writes that must be atomic with the aggregate | Same transaction, designed and measured explicitly |
| Read model updates that can lag | Async consumer or outbox, with retry/idempotency |
| Emails/webhooks that must not be lost | Transactional Outbox or durable messaging; send after commit |
| Best-effort metrics/logs | Keep lightweight, with sampling/batching and fail-safe handling |
| Cross-service fan-out | Message broker/workflow/saga per contract; do not use an in-process event bus to imitate a broker |

### Step 3 — Reduce work inside synchronous listeners

- Remove slow network calls that are not part of an invariant.
- Replace many small queries with efficient queries or batching where business logic allows.
- Avoid serializing large payloads if the handler only needs an ID.
- Use immutable value/event records to avoid large JPA object graphs and unexpected lazy loading.
- Avoid publishing inside a per-item loop if a single aggregated event makes appropriate business sense.
- Reduce payload logging and unnecessary high-cardinality metric tags.
- Reduce lock contention by shortening transactions and avoiding unnecessary I/O inside them.
- Keep listener contracts independent; do not force the request path to wait for work whose response it does not need.

### Step 4 — Choose a post-commit strategy with appropriate reliability

If you only need to defer a side effect until commit, `@TransactionalEventListener(AFTER_COMMIT)` may be right for **timing**. However, it does not automatically create a durable queue and does not run in the background by default.

If you need **zero event loss** on process crash, design a **Transactional Outbox**:

```text
Transaction T1:
  INSERT order
  INSERT outbox(eventId, aggregateId, type, payload, status=PENDING)
  COMMIT T1
         |
         v
Background dispatcher
  read pending outbox
  -> send to broker / consumer
  -> retry with backoff
  -> mark SENT per workflow
         |
         v
Idempotent consumer by eventId
```

An outbox adds DB write cost inside the request, but can avoid making the request wait on network calls to external systems. It also provides controlled recovery when the dispatcher or downstream fails. Do not advertise an outbox as “free latency” or “exactly-once end-to-end”; it requires workers, cleanup, backpressure, deduplication, and backlog monitoring.

### Step 5 — Load test after changes

Do not stop at improved response p95. With async/outbox, also check:

- Rate of events eventually processed successfully.
- Latency from commit to listener completion.
- Queue depth, oldest pending age, and retry backlog.
- Memory footprint, thread count, and CPU/GC.
- Number of duplicate/lost events and correctness across service restarts.
- Safe shutdown behavior during rolling deployments or executor shutdown.

If responses are fast but the queue grows without bound, overall performance and business SLAs are still degrading.

## 9. When should events NOT be used to “optimize” a request?

There are use cases where an explicit service call is better than an event:

- The controller needs immediate inventory check results to return HTTP 409.
- The transaction must calculate quotas and persist the result atomically.
- Listener A must succeed before listener B and before commit; an event bus is not an ideal orchestration engine for tightly coupled workflows.
- The task has only one direct consumer with no real decoupling benefit, yet adding an event obscures exception flow.

The event pattern itself is not bad; the problem is using it **to hide a synchronous dependency**. If behavior is inherently synchronous, a method call with an explicit return value and error handling is usually easier to measure and test.

If there are multiple independent behaviors and eventual consistency is acceptable, events are useful, provided thread, transaction, executor, or broker boundaries are chosen explicitly.

## 10. Common mistakes regarding event performance

**Mistake 1 — “`publishEvent(...)` returns immediately because events are async.”**  
False under default configuration. `SimpleApplicationEventMulticaster` invokes listeners on the caller thread, so slow listeners block the request.

**Mistake 2 — Benchmarking `publishEvent` with no listeners and applying it to production.**  
False because production latency is usually dominated by handler I/O, DB, payloads, and contention. Benchmarks need representative workloads.

**Mistake 3 — Moving mandatory listeners to `@Async` to speed things up.**  
Can break transaction semantics: errors on the worker do not roll back the caller transaction. For invariants, keep them synchronous or design an explicit workflow.

**Mistake 4 — Assuming `AFTER_COMMIT` is automatically a background thread.**  
It represents a transaction phase, not an async contract. Synchronous post-commit callbacks can still increase request latency.

**Mistake 5 — Using an unbounded executor queue.**  
During peaks, backlog/memory grow rapidly, event processing latency grows without bound, and the system risks OOM. Bounded queue capacity and an overload policy are required.

**Mistake 6 — Using CallerRunsPolicy without measuring request latency under overload.**  
Tasks are pushed back onto the caller thread when the queue is full; request latency can suddenly degrade.

**Mistake 7 — Not setting timeouts on external calls from listeners.**  
Threads or transactions can be held indefinitely until a lower-layer timeout triggers. Deadlines/timeouts and bounded retries are required.

**Mistake 8 — Comparing the sum of parallel listener durations to single-request latency.**  
Total CPU/wall time across tasks does not equal the critical path. With async, you need publish/submit/start/end timestamps plus trace/queue metrics.

**Mistake 9 — Using `@EventListener` with complex SpEL `condition`s at very high frequency.**  
Condition evaluation also has cost; under high event volume, measure and avoid accessing large data or unnecessary dependencies inside conditions.

**Mistake 10 — Passing whole JPA entities to async listeners.**  
Lazy associations and persistence contexts are not safe to treat as transaction-portable. Pass an ID or immutable snapshot and query in a separate transaction if needed.

**Mistake 11 — Optimizing only the request without looking at overall throughput.**  
A congested async executor can delay event side effects by minutes. Response latency is only part of the SLA.

**Mistake 12 — Treating a single `Thread.sleep` demo run as official performance numbers.**  
The demo only demonstrates thread blocking; actual timings must be measured in the real application under realistic load and dependencies.

## 11. Testing correctness and performance

A sound test suite has three layers:

### Unit tests for publish decisions and payloads

No Spring context is needed if only checking that the service constructs events with the right content. A fake publisher can record event objects and assert event types and data. Do not use this kind of unit test to infer the speed of the real multicaster.

### Spring context integration tests for synchronization and errors

With `AnnotationConfigApplicationContext` or `@SpringBootTest`:

1. Register listeners using the real configuration.
2. Publish an event and assert side effects/sequence in the synchronous case.
3. If a synchronous listener throws `RuntimeException`, assert exception propagation and transaction outcome with a real `@Transactional`.
4. If using `@TransactionalEventListener`, use a real transaction manager and distinguish commit vs. rollback.
5. If an event has multiple listeners, do not assume listeners blocked after an exception will always run.

`spring-test`'s `@RecordApplicationEvents` can be used to verify publication, but it does not prove that an async listener completed or that a transaction committed.

### Integration/load tests for async and outages

- Use `CountDownLatch`, `CompletableFuture`, or a test executor instead of `Thread.sleep` to await completion.
- Induce executor saturation to observe task rejection policies, dropped work, and request p99.
- Inject controlled downstream failures to verify retry/backoff/circuit breakers.
- Simulate shutdown between publish and processing to test for event loss.
- For outbox, test crashes/restarts, duplicate delivery, and consumer idempotency.
- In load tests, record p50/p95/p99 of both requests and **event completion latency**; do not optimize only one of the two.

### A comparison table that must be interpreted properly

| Criterion | Sync listener | `@Async` in-memory | Transactional Outbox |
| --- | --- | --- | --- |
| Does request wait for handler? | Yes (by default) | Usually no; still waits on submit/rejection/backpressure | Waits for outbox write, does not wait for downstream |
| Uses caller transaction? | Possible, when on same thread and compatible | Not inherited automatically | Outbox record is in the same transaction |
| Does handler error affect publisher? | Can propagate by default | Usually does not propagate from worker | Handler errors in dispatcher need separate retries |
| Preserves events on process crash? | Not guaranteed automatically | No, queue is in memory | Recoverable from committed outbox |
| Requires operating queue/backlog? | No separate executor queue by default | Yes | Yes, worker/outbox backlog |
| Complexity | Low | Medium | Higher, suited for reliability requirements |

The right choice depends on **business semantics**, acceptable latency, actual load, transaction boundaries, retry needs, and operational requirements.

## 12. Self-assessment questions

**1. Why can `publishEvent(...)` slow down an HTTP request?**  
Because the default multicaster invokes `@EventListener` synchronously on the request thread; the request waits for the listener to finish.

**2. If a request takes 500 ms when publishing an event, can we conclude Spring's dispatch overhead is 500 ms?**  
No. That figure can include listener HTTP/DB calls, conditions, nested events, logging, and wait times. Dispatcher and handler must be instrumented separately.

**3. Does moving a listener to `@Async` eliminate processing cost?**  
No. It only moves work to workers and a queue; CPU, memory, I/O, retries, coordination, and capacity limits still remain.

**4. Does `@TransactionalEventListener(AFTER_COMMIT)` guarantee the request won't have to wait?**  
No. A transaction phase is not an async contract; the callback can still run synchronously on the commit thread.

**5. What happens when the executor is full?**  
Depending on the queue/rejection policy, tasks may be rejected or run on the caller thread, impacting request latency and risking lost work. Rejections/backpressure must be monitored.

**6. Why measure queue wait alongside listener execution time?**  
An async listener might execute quickly yet wait a long time in a backlog. An SLA of “event processed within 5 seconds” must include queuing time.

**7. When notifications must not be lost after commit, is `@Async` alone sufficient?**  
No. An in-memory queue is not durable. Consider an outbox/durable messaging and idempotency.

**8. Why should an event ID not be placed in a low-cardinality metric tag?**  
Because each event produces a distinct tag value, causing unbounded growth in the number of time series. Event IDs belong in logs/traces instead.

## 13. Official documentation

- [Spring Framework 6.2.9 Javadoc — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework 6.2 — Application Events, @EventListener, @Async](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework — Observability Support for @EventListener](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Framework 6.2.9 Javadoc — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework 6.2.9 Javadoc — ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html)

