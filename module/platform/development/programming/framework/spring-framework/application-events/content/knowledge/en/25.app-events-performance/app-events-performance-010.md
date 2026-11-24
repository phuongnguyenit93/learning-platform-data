# When Events Are Unsuitable for High Load in Spring Framework Application Events

## 1. Context: events decouple code, not create extra processing capacity

In Spring, `ApplicationEventPublisher.publishEvent(...)` and `@EventListener` let components exchange business events without the producer directly knowing every consumer. This is a convenient design for auditing, cache invalidation, updating projections, or reactions that can be decoupled from the main use case.

However, **Spring Application Events is an internal `ApplicationContext` event-dispatch mechanism**; it does not inherently provide durable queues, brokers, consumer groups, offsets, replay, or distributed backpressure. An architecture with many `@EventListener`s does not automatically handle higher load than a use case calling services directly.

Example:

~~~text
POST /orders
     |
     v
OrderService.placeOrder()
     |
     +--> save Order
     |
     +--> publish(OrderPlaced)
              |
              +--> AuditListener          10 ms
              +--> SearchIndexListener    20 ms
              +--> EmailListener         150 ms
              +--> AnalyticsListener      40 ms
              +--> PromotionListener      30 ms
~~~

If those five listeners run synchronously and sequentially on the request thread, hypothetical total handler time is **250 ms**, before counting the use case's DB work, controller networking, or framework overhead. Just one listener hanging on an external API can stall the request. Adding `@Async` may let the caller return sooner, yet the work still has to run on worker threads and still consumes CPU/DB/network.

*The durations above are illustrative only, not Spring benchmarks.*

**The question to evaluate is not “are events faster than method calls?” but rather: does the system have adequate capacity, latency, backpressure, transaction semantics, and recovery for this kind of work?**

### Lesson objectives

After this lesson, learners can:

- Understand the cost of `publishEvent` and listeners on the synchronous path.
- Analyze fan-out, event chains, handler invocation counts, and amplification.
- Distinguish **request latency**, **event processing latency**, **successful throughput**, and **backlog**.
- Know why `@Async` does not solve high load by itself; configure bounded `ThreadPoolTaskExecutor`s and observe rejections.
- Know when to use direct service calls, batching, coalescing, durable jobs, a transactional outbox, or a broker.
- Build benchmarks/load tests that measure real bottlenecks rather than extrapolating from microbenchmarks.
- Review consequences for transactions, ordering, idempotency, and graceful shutdown.
- Run a Java 17+ example observing synchronous listeners blocking the publisher and fan-out multiplying invocation counts.

## 2. Dispatch mechanism: how do Spring Application Events work?

`ApplicationEventPublisher` is the event-publishing API. In a typical Spring Framework application, `ApplicationContext` dispatches events to `ApplicationEventMulticaster`, which selects matching listeners.

`SimpleApplicationEventMulticaster` processes ordinary listeners **on the caller's thread** by default when no separate executor is configured. The `publishEvent` API expresses handing an event to the dispatch mechanism, not a promise that all consumers succeeded or committed their side effects.

~~~text
publisherThread
    |
    +--> publishEvent(new OrderPlaced(...))
           |
           +--> audit listener
           +--> projection listener
           +--> notification listener
           |
           v
        return from publishEvent
    |
    +--> continue request
~~~

In synchronous dispatch, listeners finish before returning; uncaught exceptions can propagate back to the publisher. If inside `@Transactional` and the transaction manager applies matching rollback rules, a listener error can roll back the source transaction.

The benefit is **simplicity, ease of debugging, and preserving transaction context**. Yet under high load, all listener work contributes to request duration. Spring events are **not free** merely because the producer does not call listeners directly.

### 2.1. Which layers incur an event's cost?

- Creating and retaining the payload (POJO/record, metadata, trace context).
- Looking up listeners by event type, generics, and conditions.
- Reflection/adapters/proxies when using `@EventListener` or AOP.
- Real business work inside every handler: CPU, DB, HTTP, serialization, locks.
- If async: task allocation, enqueue/dequeue, thread scheduling, context propagation.
- If child events are emitted: additional dispatches and side effects.
- If retried: the same task or event runs multiple times, requiring deduplication.

In many applications, **listener I/O is the real bottleneck**, not Spring dispatching an object itself. Thus micro-optimizing lookup cost or creating small records usually matters far less than reducing DB round trips, HTTP calls, fan-out, or duplicate processing.

### 2.2. Metrics easily conflated

| Metric | Description | Common mistake |
| --- | --- | --- |
| Request p95/p99 | API duration from entry to response | Assuming the system is healthy just because async makes HTTP fast |
| Publish latency | Duration of the publish call | Equating published with all consumers finished |
| Consumer execution time | Duration of the handler body | Forgetting time spent waiting in the queue |
| End-to-end event lag | From event occurrence until side effect meets its goal | Checking execution time only without queue wait |
| Successful throughput | Correctly completed work units per second | Reporting published/s as processed/s |
| Backlog/queue depth | Work still waiting | Queue growing steadily without throwing exceptions |
| Error/retry rate | Failures and retry attempts | Retry storms inflating total load |

A strong high-load design targets **steady successful throughput** and SLA-compliant latency, not merely calling the publisher quickly.

## 3. Synchronous listeners can stall requests

In a common pattern:

~~~text
HTTP Request Thread
    |
    +--> OrderService.place()
            |
            +--> repository.save(order)
            |
            +--> publish(OrderPlaced)
                    |
                    +--> AuditListener: CPU 5 ms
                    +--> SearchListener: DB 30 ms
                    +--> EmailListener: HTTP 200 ms
                    |
                return
    |
    +--> HTTP response
~~~

If a secondary external API times out, the request thread is held far longer than intended. Under high load, request threads are finite; many requests waiting together on slow listeners reduce capacity for new requests and push p99 upward.

### 3.1. Forms of indirect coupling

**Latency coupling:** adding a new listener slows down the producer, even though the controller code did not change.

**Failure coupling:** a deep handler throws an exception that propagates back; the main business flow can fail or roll back even though the listener was only sending notifications.

**Transaction coupling:** a listener on the same thread can join the publisher's transaction when resources and transaction managers align; a slow handler holds the transaction/connection/locks longer.

**Lifecycle coupling:** events processed during context startup/shutdown can depend on beans that are not ready yet or are being destroyed.

### 3.2. Do not use events to hide a mandatory step

If payment or quota validation must succeed before an order can succeed, a hidden side-effect listener makes the contract opaque. Consider calling a domain/application service directly or using a stateful orchestrator. **Explicit dependencies are sometimes better than hidden coupling via events.**

Conversely, auxiliary auditing, analytics, cache invalidation, or non-mandatory notifications make good event consumers once the business fact is established. The key is clarifying **whether the command's success depends on that work**.

## 4. Fan-out: listener load can multiply publisher load

Suppose each `OrderPlaced` has four listeners:

~~~text
                   +--> audit
                   |
OrderPlaced -------+--> search indexing
                   |
                   +--> email
                   |
                   +--> analytics
~~~

At 1,000 events per second, the system executes roughly **4,000 listener invocations per second**, before counting listeners that emit further events or retries. An event with multiple consumers does not “run once” in terms of resource cost.

A chain can widen rapidly:

~~~text
OrderPlaced
  |
  +--> InvoiceIssued --> AccountingUpdated
  |
  +--> PaymentAuthorized
  |       |
  |       +--> InventoryReserved
  |       +--> FulfillmentReady
  |
  +--> SearchIndexed
  +--> EmailScheduled
~~~

Depth, fan-out, fan-in, and cycles can all amplify load:

- **Depth:** many sequential steps, cumulative latency, hard to trace.
- **Fan-out:** one event triggers multiple listeners, tasks, and side effects.
- **Fan-in:** multiple branches required before proceeding; prone to races.
- **Cycles:** a listener emits an event leading back to the original event type; can trigger an event storm.
- **Retries:** when downstream fails, processing attempts surge right when the system is weakest.

If one event produces an average of `b` child events per level across `d` levels, theoretical node count can grow as `1 + b + b² + ... + b^d`. This is an **illustrative** model, not Spring spontaneously generating events, showing why the event graph matters.

### 4.1. In-process events do not load-balance across pods automatically

Listeners are registered inside a specific context. An event published on pod A is **not automatically delivered** to listeners on pod B or C. Scaling pod counts helps only insofar as incoming traffic/source events are distributed across pods by design.

If multiple workers must share a stream of jobs, you need a queue/broker/job table with consumer groups, partitions, or a proper job-claiming mechanism. `ApplicationEventPublisher` has no concept of consumer groups like a broker.

## 5. @Async: shifts the bottleneck to an executor, does not remove it

A listener can use `@Async`:

~~~java
@Component
public class SearchListener {
    @Async("searchExecutor")
    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        searchIndex.update(event.orderId());
    }
}
~~~

This is a snippet; it requires a Spring bean, imports, `@EnableAsync`, an executor, and matching `OrderPlaced`/`searchIndex`. When the async proxy works, the publisher can return before the handler body finishes. Actual processing time simply shifts from the request thread to a worker thread.

If incoming task rate exceeds worker capacity over a sustained period, the queue grows. If the queue is bounded, tasks may be rejected when capacity is exceeded. If the queue is unbounded, overload hides behind backlogs, allocations, and GC/heap pressure.

### 5.1. Capacity formula for reasoning, not rigid configuration

Suppose:

- `λ` is events/second.
- `f` is average handler tasks per event.
- `w` is time one task occupies a worker, in seconds.

Incoming task load is `λ × f` tasks/second. Under steady state and suitable assumptions, Little's Law suggests active concurrency is roughly `λ × f × w`.

~~~text
Arrival           = 500 events/s
Average fan-out   = 3 tasks/event
Service time      = 0.020 s/task

Task arrival rate = 1,500 tasks/s
In-service work   ≈ 1,500 * 0.020 = 30 concurrent tasks
~~~

**Do not immediately conclude you need 30 threads.** This is only an estimate: CPU-bound vs. I/O-bound characteristics, variance, p95/p99, burst traffic, retries, and downstream limits determine real capacity. On a 4-core CPU with heavy CPU-bound tasks, 30 runnable threads can worsen throughput due to context switching.

### 5.2. Backlog grows when falling behind

~~~text
Task arrival rate  = 2,000 tasks/s
Task service rate  = 1,500 tasks/s
Growth             ≈ 500 tasks/s
After 60 seconds   ≈ 30,000 queued tasks (without throttling)
~~~

This example assumes constant rates and no drops/backpressure; it is not a measured result. Every task retains event objects, closures, trace data, etc., so growing queues can consume heap. A system returning fast HTTP responses while background tasks lag by minutes can still **fail its business SLA**.

## 6. ThreadPoolTaskExecutor: choosing bounded queues, workers, and rejection policies

An illustrative configuration for internal workloads that may be dropped or rebuilt:

~~~java
@Configuration
@EnableAsync
public class AsyncEventConfig {

    @Bean("searchExecutor")
    public ThreadPoolTaskExecutor searchExecutor() {
        ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("search-event-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);
        return executor;
    }
}
~~~

This is a configuration snippet requiring imports for `Configuration`, `EnableAsync`, `Bean`, and `ThreadPoolTaskExecutor`, not a standalone runnable class. The numbers 4/8/200 are illustrative only. When managed as a Spring bean, the container handles init/destroy lifecycle.

### 6.1. How queue size affects pool scaling

With the underlying `ThreadPoolExecutor`, the pool normally uses core threads first; once core threads are busy and the queue has space, tasks enqueue before scaling up to `maxPoolSize`. Thus **raising maxPoolSize while leaving a huge queue will not necessarily increase throughput**.

Spring's default `ThreadPoolTaskExecutor` is not a small bounded queue suitable for every app; per the 6.2 Javadoc, defaults amount to roughly a single worker with an essentially unbounded queue. Set limits based on measured workloads.

`queueCapacity=0` gives near-direct handoff behavior and can scale workers quickly, but also creates thread pressure if `maxPoolSize` is too high. Never pick numbers by guesswork.

### 6.2. Submission errors differ from worker errors

- **Scheduling rejection:** the executor is shutting down or queue/pool is full; `TaskRejectedException`/`RejectedExecutionException` can occur immediately at submit time depending on executor/policy.
- **Worker execution error:** the task was accepted and then throws inside the listener body. With `@Async void`, errors do not automatically propagate back to the publisher; `AsyncUncaughtExceptionHandler` is the relevant observation point.
- **Downstream timeout:** unclear whether side effects occurred; retries require idempotency.

Some rejection handlers (like caller-runs where applicable) execute the task on the caller to apply backpressure, yet raise request latency and can alter failure/transaction semantics. A “discard” policy loses work without persistence. No single rejection policy fits every event.

### 6.3. Bulkheads to isolate workloads

Do not necessarily share one pool across the whole application:

~~~text
OrderPlaced
   |
   +--> Audit               sync (if required)
   +--> Search indexing     bounded searchExecutor
   +--> Notification        bounded notificationExecutor
   +--> Analytics           batch/stream worker
~~~

A slow notification provider can exhaust a shared pool's workers, stalling unrelated tasks. **Bulkheads** partition resources by work type and downstream, though over-fragmenting pools reduces idle-capacity sharing; benchmark to tune.

### 6.4. @Async does not persist jobs durably

Executor queues live in RAM. If the process crashes after database commit but before workers run, tasks are not recovered automatically. `@Async` is a concurrent execution mechanism, **not durable messaging**.

## 7. Complete Java 17+ example: sync blocks publisher and multiplies listener invocations

This example uses Spring Framework 6.2.8, Java 17+, and Maven **without Spring Boot**. It proves two verifiable facts without guessing QPS:

1. A synchronous listener can hold the `publishEvent(...)` call open until it finishes.
2. One event handled by three listeners produces three handler invocations; 1,001 events produce 3,003 invocations.

We use `CountDownLatch` to create a controlled wait point, not `Thread.sleep` as a benchmark.

### 7.1. Directory structure

~~~text
sync-fanout-demo/
├── pom.xml
└── src/main/java/SyncFanoutDemo.java
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>sync-fanout-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>SyncFanoutDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.3. src/main/java/SyncFanoutDemo.java

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public final class SyncFanoutDemo {

    public record WorkArrived(long id) { }

    public static class Gate {
        final CountDownLatch started = new CountDownLatch(1);
        final CountDownLatch release = new CountDownLatch(1);
    }

    public static class Stats {
        final AtomicInteger slow = new AtomicInteger();
        final AtomicInteger audit = new AtomicInteger();
        final AtomicInteger projection = new AtomicInteger();

        public int total() {
            return slow.get() + audit.get() + projection.get();
        }
    }

    public static class SlowListener {
        private final Gate gate;
        private final Stats stats;

        public SlowListener(Gate gate, Stats stats) {
            this.gate = gate;
            this.stats = stats;
        }

        @Order(10)
        @EventListener
        public void on(WorkArrived event) {
            stats.slow.incrementAndGet();

            if (event.id() == 1L) {
                System.out.println("SLOW_LISTENER_STARTED");
                gate.started.countDown();
                try {
                    if (!gate.release.await(30, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                            "Listener gate timed out"
                        );
                    }
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(
                        "Interrupted", ex
                    );
                }
                System.out.println("SLOW_LISTENER_FINISHED");
            }
        }
    }

    public static class AuditListener {
        private final Stats stats;

        public AuditListener(Stats stats) {
            this.stats = stats;
        }

        @Order(20)
        @EventListener
        public void on(WorkArrived event) {
            stats.audit.incrementAndGet();
        }
    }

    public static class ProjectionListener {
        private final Stats stats;

        public ProjectionListener(Stats stats) {
            this.stats = stats;
        }

        @Order(30)
        @EventListener
        public void on(WorkArrived event) {
            stats.projection.incrementAndGet();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        Gate gate() {
            return new Gate();
        }

        @Bean
        Stats stats() {
            return new Stats();
        }

        @Bean
        SlowListener slowListener(Gate gate, Stats stats) {
            return new SlowListener(gate, stats);
        }

        @Bean
        AuditListener auditListener(Stats stats) {
            return new AuditListener(stats);
        }

        @Bean
        ProjectionListener projectionListener(Stats stats) {
            return new ProjectionListener(stats);
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            Gate gate = context.getBean(Gate.class);
            Stats stats = context.getBean(Stats.class);
            AtomicBoolean firstReturned = new AtomicBoolean(false);

            Thread publisherThread = new Thread(() -> {
                context.publishEvent(new WorkArrived(1L));
                firstReturned.set(true);
                System.out.println("FIRST_PUBLISH_RETURNED");
            }, "publisher-thread");

            publisherThread.start();

            if (!gate.started.await(10, TimeUnit.SECONDS)) {
                gate.release.countDown();
                throw new IllegalStateException(
                    "First listener did not start"
                );
            }

            System.out.println(
                "PUBLISH_BLOCKED=" + !firstReturned.get()
            );

            gate.release.countDown();
            publisherThread.join(10_000);
            if (publisherThread.isAlive()) {
                throw new IllegalStateException(
                    "Publisher thread did not finish"
                );
            }

            for (long id = 2L; id <= 1001L; id++) {
                context.publishEvent(new WorkArrived(id));
            }

            System.out.println("PUBLISHED=1001");
            System.out.println(
                "HANDLER_INVOCATIONS=" + stats.total()
            );
        }
    }
}
~~~

Run from the `sync-fanout-demo` directory using JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java
~~~

Output **printed by the program** during a normal run without timeout:

~~~text
SLOW_LISTENER_STARTED
PUBLISH_BLOCKED=true
SLOW_LISTENER_FINISHED
FIRST_PUBLISH_RETURNED
PUBLISHED=1001
HANDLER_INVOCATIONS=3003
~~~

### 7.4. Analyzing the results

- The Spring context refreshes when constructing `AnnotationConfigApplicationContext(Config.class)`, so all three `@EventListener` methods are registered before publishing.
- `publisherThread` publishes `WorkArrived(1)`. `SlowListener` is ordered ahead of the other two via `@Order(10)` and runs on the default publisher thread.
- The listener prints `SLOW_LISTENER_STARTED`, signals the `started` latch, and waits on `release`. Main receives the latch and prints `PUBLISH_BLOCKED=true` because `publishEvent` cannot return while the listener waits.
- After main opens the latch, the listener resumes and prints `SLOW_LISTENER_FINISHED`; the audit and projection listeners for the first event also run. Only then does `FIRST_PUBLISH_RETURNED` print.
- Main publishes 1,000 more events; each invokes three listeners. The total of **1,001 × 3 = 3,003** invocations is deterministic.

This is **not a throughput benchmark**: there is no real DB/network data, no QPS measurement, and no simulation of contended resources. The example simply highlights coupling between publisher and synchronous listeners, plus fan-out. High-load evaluation requires a production-representative load test.

## 8. @Async can sometimes make issues harder to see

### 8.1. CPU-bound work does not benefit from endless threads

If handlers perform heavy CPU computation, raising workers past effective CPU count can increase context switching, memory allocation, and GC time. Measure CPU, lock contention, allocations, and heap, and optimize algorithms or batch work.

### 8.2. I/O-bound work is capped by downstream limits

If handlers wait on DB, HTTP APIs, or search engines, increasing concurrency can help **up to a point**. Once the DB pool or rate limit saturates, adding tasks only causes more timeouts and retries.

Add timeouts, circuit breakers, concurrency limits, and per-downstream bulkheads. If an email provider accepts only 200 requests/s, an executor pushing 2,000 requests/s will not make the provider faster.

### 8.3. Async alters ordering

Two events for the same aggregate can finish out of order across two workers. `@Order` only affects listener dispatch ordering under appropriate conditions; it does not guarantee completion order across executors/processes. If projections require consistency, use aggregate versions/sequences or key-partitioned sequential consumers.

### 8.4. Async changes transaction boundaries

`@Async` usually runs on a worker thread and **does not inherit the publisher's imperative thread-bound transaction**. A listener that previously ran synchronously inside the transaction no longer participates in it; its failure does not automatically roll back the committed aggregate.

Do not move mandatory business steps to async while the API contract still promises that a successful request means all steps completed.

## 9. Global async multicaster is not a universal fix

Spring allows configuring an executor on `SimpleApplicationEventMulticaster`:

~~~java
// Illustrative code in a @Configuration class with appropriate imports/beans.
@Bean(name = "applicationEventMulticaster")
SimpleApplicationEventMulticaster applicationEventMulticaster(
        ThreadPoolTaskExecutor eventExecutor) {
    SimpleApplicationEventMulticaster multicaster =
        new SimpleApplicationEventMulticaster();
    multicaster.setTaskExecutor(eventExecutor);
    return multicaster;
}
~~~

However, switching the multicaster to an executor impacts far more listeners and event lifecycles than putting `@Async` on a specific handler.

- `ApplicationListener.supportsAsyncExecution()` can force listeners onto the publisher thread; transaction-synchronized listeners are the classic example.
- Thread context and transactions do not automatically carry over to workers.
- Handler errors and executor rejections follow different handling paths; some implementations may fall back to running on the caller when tasks are rejected.
- Sharing one pool tightly couples workload capacities; one slow listener can starve other listeners.
- Shutdown lifecycle events may need execution on an appropriate thread rather than a stopping pool.

An easier-to-control alternative is **selective `@Async`, bounded executors per workload group, and outcome monitoring**; for mandatory work needing recovery, use a durable pipeline.

## 10. How do in-process Spring events differ from queues/brokers?

| Capability | Spring Application Events | Properly configured durable queue/broker/job pipeline |
| --- | --- | --- |
| Dispatch within the same JVM/context | Yes | Via consumer/adapter |
| Persists events by default | No | Possible depending on mechanism, retention, and config |
| Replay after crash | Not automatic | Possible via log/offset/job storage |
| Consumer groups load-balancing across nodes | Not built-in | Supported by many systems |
| Contractual bounded backlog/backpressure | Not an event-bus API | Designable via queue/consumer |
| Retry/ack/checkpoint | Not automatic | Implementable, requires policy |
| Consumer lag tracking | Must instrument manually | Often has built-in metrics/support |
| System-wide exactly-once side effects | No | Not automatic either; requires idempotency and transactions |
| Cross-service schema/version changes | Coupled to in-JVM code | Requires contracts, schema evolution, and governance |

Do not assume a broker is always better. Kafka, RabbitMQ, cloud queues, and database job tables differ in ordering, retention, consumer models, and operational cost. For small, lightweight listeners within one service, in-process events can be simpler and safer.

### 10.1. Transactional outbox

When a business fact must be delivered even if the application crashes after commit:

~~~text
Transaction T1:
    save Order
    insert outbox(eventId, OrderPlaced, payload)
    COMMIT
       |
       v
Outbox dispatcher
    |
    +--> message broker / worker
    +--> retry, monitoring, deduplication
       |
       v
Consumer:
    process with stable eventId
    commit local state
    ack / checkpoint
~~~

The **transactional outbox** pattern writes aggregate state and the intent to emit an event inside **the same database transaction**. If the transaction rolls back, neither commits. If it commits and the app crashes, a dispatcher can read pending records afterward.

Under high load, an outbox still requires batch polling, indexes, cleanup, connection pools, parallel claiming, lag tracking, and retries. It solves **durability/recovery**, without magically erasing throughput problems. Delivery is typically **at-least-once**, so consumers still need idempotency.

## 11. When to choose direct calls, batching, or a broker?

| Need | Typically suitable mechanism | Reason |
| --- | --- | --- |
| Mandatory step determining command success | Direct service/domain call | Explicit result, deadline, and transaction |
| Small internal audit/cache listener, droppable | Sync Spring event | Minimal infrastructure |
| Slow internal reaction, reproducible | `@Async` + bounded executor | Decouples request latency and bounds resources |
| Many updates to same key needing only latest state | Coalescing / latest-state reconciliation | Eliminates obsolete work |
| Many updates suited for bulk processing | Batching | Reduces round trips and overhead |
| Work that must survive restarts | Durable job table / transactional outbox | Supports retries |
| Independent consumer scaling across services | Broker/queue with consumer groups or partitions | Distributes work |
| History and offset-based replay | Event log / streaming platform | Retention/checkpoints |
| Multi-step workflow with timeouts/compensation | Orchestrator/saga | Clear state owner and failure policy |

### 11.1. Batching to reduce round trips

Instead of 10,000 `PriceChanged` events issuing 10,000 separate search index updates, batch them into bulk API calls to cut network overhead.

However, batching adds latency until flush, requires memory limits, shutdown flushing, partial-failure handling, retries, and ordering preservation if business rules demand it. If a batch fails partially, never treat all events as processed.

### 11.2. Key-based coalescing

For cache invalidation, multiple “config key X changed” events can sometimes coalesce into one reload of the **latest state**. This differs completely from individual financial facts: never coalesce `PaymentCaptured` events sharing an order ID if they represent distinct transactions.

### 11.3. Fast path and slow path

~~~text
Command/API
   |
   +--> Fast path:
   |      validate -> update aggregate -> commit
   |      respond within SLA
   |
   +--> Slow path:
          outbox / queue / bulk processing
          search indexing, analytics, notifications
~~~

Separate work required before responding from work that can be eventually consistent. If an API merely **accepts a request** for later processing, the response should indicate accepted/pending with an appropriate job ID/status, not pretend the business work is already complete.

## 12. Designing representative benchmarks and load tests

The demo in section 7 does not measure throughput. A production load test must define clear hypotheses and boundaries:

- Which endpoints are affected by fan-out?
- How many times does each event fire per request?
- Which listeners consume the most CPU, DB connections, or HTTP connections?
- Are API p95/p99 and **end-to-end event lag** within SLA?
- Does queue depth stay stable during a long soak test?
- Does raising pool size increase successful processed/s or only increase timeouts?
- Do rejected tasks, duplicate side effects, or post-crash losses occur?
- At 2× traffic, is there enough headroom?

### 12.1. Metrics to collect

**HTTP/use case:** RPS, p50/p95/p99, error rate, request thread pool, DB latency.

**Events:** published total, listeners invoked, processed-success total, processed-failure total, event chain depth, fan-out.

**Executor:** active threads, queue depth, queue wait time, task duration, rejected count, shutdown/drain time.

**Durable pipeline:** consumer lag, oldest pending age, retries, dead-letter, dedup count, broker/DB saturation.

**Infrastructure:** CPU, heap, GC pauses, memory allocation, database pool, connection timeouts, downstream rate limits.

The metric names below are **custom suggested names**, not Spring defaults:

~~~text
app_event_published_total{type="OrderPlaced"}
app_event_listener_duration_seconds{listener="search"}
app_event_listener_failures_total{listener="notification"}
app_event_executor_active_threads{pool="search"}
app_event_executor_queue_depth{pool="search"}
app_event_executor_rejections_total{pool="search"}
app_event_processing_lag_seconds{consumer="billing"}
app_event_deduplicated_total{consumer="billing"}
~~~

Avoid `eventId`, `orderId`, and `customerId` as Prometheus labels due to high cardinality; keep IDs in structured logs/tracing.

### 12.2. A minimal load test plan

1. **Baseline** with synchronous events and current listeners.
2. **Steady state** ramping input rate; identify maximum sustainable successful throughput.
3. **Burst** to observe queue filling/rejections and latency spikes.
4. **Soak** to uncover growing backlogs or heap/GC/connection leaks.
5. **Downstream slowdown** simulating slow DB/API responses and observing retry storms.
6. **Fan-out growth** adding listeners in a test environment to quantify amplification.
7. **Crash/restart** after commit before side effects; verify outbox/job recovery if needed.
8. **Duplicate delivery** with identical event IDs; verify idempotency.
9. **Shutdown** with pending jobs remaining; verify graceful drain and container deadlines.
10. **Ordering** when async processing handles same-aggregate events across multiple workers.

Gatling/k6/JMeter suit HTTP load; JMH suits narrow microbenchmarks; JFR/profilers diagnose CPU, allocations, and lock contention. Never use `System.nanoTime()` around 1,000 demo events to predict production SLAs.

### 12.3. Analyzing results accurately

If request p95 drops upon enabling `@Async` while queue depth and event lag climb endlessly, you are **trading latency for backlog**. If a publisher runs 10,000 calls/s while consumers complete 1,000 calls/s, publish count says nothing about real capacity.

The goal is **successful throughput keeping pace with arrival rate over long intervals**, with p99, lag, rejections, and errors below acceptable thresholds.

## 13. Transactions and consistency when optimizing for load

### 13.1. Sync listeners may run inside the source transaction

If `publishEvent` runs inside `@Transactional`, a synchronous listener on the same thread can join the source transaction (when the transaction manager, resources, and method align). It can extend connection/lock lifetimes; exceptions can propagate and trigger rollback.

When moving to async, workers **do not automatically inherit imperative thread-bound transactions**. If a side effect must be atomic with the use case, you cannot simply offload it to a worker while keeping the same contract.

### 13.2. After-commit only addresses timing

~~~java
// Snippet inside a bean with @EnableAsync, executor, imports, and real services.
@Async("searchExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderPlaced event) {
    searchIndexer.index(event.orderId());
}
~~~

With a matching source transaction, `AFTER_COMMIT` runs only after commit succeeds. If the transaction rolls back, this phase does not run. If published outside a transaction, the listener does not run by default unless `fallbackExecution=true` is intentionally set.

**AFTER_COMMIT is not durable delivery.** Workers can reject tasks, the process can crash, or downstream can fail after commit. If jobs must be delivered without loss, persist job state durably such as via a transactional outbox.

### 13.3. Retries, deduplication, and ordering

As concurrency and retries increase, events can arrive duplicated or finish out of order:

- Keep `eventId` stable for the same fact.
- Make consumers idempotent by event ID with storage suitable across multiple instances.
- Use `aggregateId` and `aggregateVersion`/sequence when projections need ordering.
- Cap retries, use exponential backoff/jitter, alert, and use dead-letter/quarantine.
- Do not use an in-memory `Set<UUID>` as a cluster/restart guarantee.
- Distinguish `occurredAt`, `publishedAt`, and `processedAt` to measure true lag.
- A downstream timeout does not automatically mean the side effect failed; it may have succeeded before the response was lost.

## 14. A pragmatic decision: should Spring events be removed from high-load paths?

**Consider changing architecture** when one or more evidence-backed signs appear:

- A listener accounts for a significant portion of request p95/p99.
- Fan-out amplification is high and grows as new modules are added.
- Async queues grow steadily under steady-state load.
- Throughput is constrained by already-saturated downstream resources.
- Requests return success yet essential side effects can be lost on crash.
- You need partitions, consumer groups, or independent handler scaling across nodes.
- You need backpressure, checkpoints, replay, and SLA-bound lag.
- Event chains conceal multi-step workflows with ownerless retries/compensation.

**No urgent need to change** when listeners do small, independent work within one context and request/processing latency, error rates, and queue depth are healthy. Adding a broker unnecessarily complicates deployment, tracing, schema evolution, and eventual consistency.

### 14.1. Architectural questions to answer

1. Is the event a **domain fact** or hiding a mandatory command?
2. If a listener fails, must the system roll back the use case?
3. On a crash, is losing the event acceptable?
4. After publishing, does the caller need **accepted**, **scheduled**, or **completed**?
5. How many consumers exist, and do they have different SLAs?
6. Does the system need consumer groups or workload partitioning?
7. Can events be coalesced without losing business facts?
8. Have we measured successful throughput, lag, and rejected tasks?
9. Where will traffic spikes be throttled or rejected?
10. When adding instances, which instance should receive which events?
11. Who owns retries, dead-lettering, and duplicate handling?
12. Is there a shutdown and pending-job recovery plan?

Without answers to most of these, adding `@Async` to listeners is usually just a stopgap.

## 15. Common mistakes

1. **Assuming `@EventListener` is async by default:** by default listeners run on the publisher thread.
2. **Switching all listeners to `@Async`:** cuts request latency while backlogs and downstream load remain.
3. **Unbounded queues:** heap and lag explode before errors surface.
4. **Raising `maxPoolSize` with an overly large queue:** the pool does not scale workers as expected.
5. **Failing to measure processed-success/s:** reporting pretty published/s numbers while consumers fail.
6. **Ignoring `TaskRejectedException`:** critical work silently goes undelivered.
7. **Confusing scheduling errors with worker errors:** hooking up the wrong exception handler.
8. **Using one global executor for all workloads:** heavy listeners starve critical listeners.
9. **Treating global `setTaskExecutor` like selective `@Async`:** different scope, threading, and transaction semantics.
10. **Believing `@Order` guarantees async completion order:** it does not.
11. **Using in-process events to load-balance across pods:** there are no automatic consumer groups.
12. **Ignoring fan-out and event chains:** one event can trigger massive I/O.
13. **Unbounded retries:** creates retry storms when downstreams degrade.
14. **Lacking idempotency:** timeouts/retries cause duplicate emails/payments.
15. **Confusing `AFTER_COMMIT` with a durable queue:** post-commit crashes still lose unpersisted tasks.
16. **Moving mandatory steps to async while the API returns completed:** broken contract.
17. **Coalescing financial facts to save work:** loses business facts.
18. **Lacking graceful shutdown:** in-memory queues can be lost on rolling deploys.
19. **Assuming brokers automatically guarantee exactly-once business side effects:** separate transactions/idempotency are still needed.
20. **Using synthetic benchmarks as production QPS:** ignores DB, network, locks, and GC.
21. **Solving high load by adding threads without fixing bottlenecks:** CPU/DB remain saturated.
22. **Ignoring per-aggregate ordering/versions:** projections overwrite newer state with stale state under concurrency.

## 16. Self-check exercises

1. An event has 5 sync listeners, each taking 40 ms. What is the total listener time assuming sequential execution?
2. Why can `@Async` reduce HTTP p95 while increasing event lag?
3. Input is 2,000 tasks/s, capacity is 1,500 tasks/s. How much does backlog grow after one minute without throttling?
4. Why might raising `maxPoolSize` fail to raise throughput if the queue still has plenty of room?
5. Why can `TaskRejectedException` happen before the task body ever runs?
6. When fan-out grows from 2 to 6 listeners, which metrics should you monitor?
7. Is an event published in pod A automatically received in pod B?
8. Should a mandatory payment step be a direct call or a best-effort listener? Why?
9. When can invalidations be batched/coalesced, and when does doing so lose facts?
10. Does `@TransactionalEventListener(AFTER_COMMIT)` guarantee zero event loss on crash?
11. Why does `@Order` not guarantee async projections finish in order?
12. If an API returns immediately after enqueueing a job, what status should the response indicate?
13. Does a broker automatically guarantee exactly-once side effects across email and DB?
14. What does the `SyncFanoutDemo` prove, and what does it NOT prove?
15. What does a steadily rising queue depth during a soak test indicate?

**Hints:** (1) 200 ms; (2) shifts work into a backlog; (3) ~30,000 tasks; (4) executors typically enqueue before scaling workers past core; (5) rejection at submission; (6) p99, listener invocations/s, queue, lag, errors, CPU/DB; (7) not automatically; (8) direct/orchestration with explicit outcomes; (9) coalesce latest state, never merge distinct transactions; (10) no, requires a durable outbox/job; (11) dispatch order differs from completion order; (12) accepted/pending; (13) no; (14) sync blocking and fan-out, not QPS; (15) sustained overload.

## 17. Summary

**“When events are unsuitable for high load”** does not mean Spring Application Events are always slow. It means an in-process event mechanism must not be pushed beyond its execution contract:

- Synchronous listeners can prolong requests and hold transactions/threads.
- Async listeners only move work to worker pools; they do not eliminate CPU/DB/network limits.
- Fan-out and event chains can amplify invocation counts, memory, I/O, and retries.
- In-process events do not automatically provide durable queues, replay, backpressure, or multi-node consumer groups.
- Measure successful throughput, end-to-end lag, p95/p99, queue depth, and errors.
- Direct calls fit mandatory steps; batching/coalescing reduce valid work; transactional outboxes, durable jobs, or brokers fit crash-safe post-commit work and independent consumer scaling.
- Regardless of mechanism, make transactions, ordering, idempotency, timeouts, and failure policies explicit.

A resilient high-load design puts **the right work on the right mechanism**, with bounded resources and observable outcomes, rather than simply multiplying events or threads.

## References

- Spring Framework Reference — *Application Events and Asynchronous Listeners*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework 6.2.8 Javadoc — *ApplicationEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework 6.2.8 Javadoc — *SimpleApplicationEventMulticaster*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework 6.2.8 Javadoc — *ThreadPoolTaskExecutor*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework Reference — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework Reference — *Task Execution and Scheduling*: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
