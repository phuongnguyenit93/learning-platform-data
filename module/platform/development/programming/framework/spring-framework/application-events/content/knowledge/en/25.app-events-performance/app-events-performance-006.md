# Executor Capacity for Async Events in Spring Framework

## 1. Why do asynchronous events need bounded processing capacity?

In Spring Framework Application Events, `ApplicationEventPublisher.publishEvent(...)` is often used to reduce coupling between the publisher and listeners. When listeners run synchronously under the default multicaster, listener work consumes time on the publisher thread. When using `@Async` or configuring an executor on `ApplicationEventMulticaster`, execution can move to worker threads.

Asynchrony **does not make work disappear**: it only shifts work onto finite resources including **active threads, wait queues, CPU, memory, DB connections, and external services**. If events arrive faster than listeners can process them, backlog grows; with an unbounded queue, the application can appear to “still publish fast” until latency spikes or memory runs out.

**Executor capacity** is the system's ability to accept and process event tasks at target load, encompassing:

- **Concurrency:** how many listener tasks can genuinely execute simultaneously?
- **Queue capacity:** how many tasks at most can wait while workers are busy?
- **Throughput:** how many events/s complete steadily, not just how many events/s are submitted?
- **Latency:** how long must an event wait from publish until the handler starts and finishes?
- **Rejection/backpressure:** what does the system do when all workers and the queue are full?
- **Reliability:** what happens when a task fails, an event is rejected, or the JVM restarts?

A well-designed executor does not necessarily make every event run as fast as possible at any load; it must have **clear limits and deliberate reactions under overload**.

## 2. Where do `@Async @EventListener` and the executor fit?

Example listener:

```java
@Async("eventExecutor")
@EventListener
public void onPaymentCaptured(PaymentCaptured event) {
    notificationService.sendReceipt(event.paymentId());
}
```

This is **illustrative code**, not a standalone program. To work properly, it requires:

1. A Spring-managed bean containing this `public` method.
2. `@EnableAsync` configuration.
3. An `Executor` or `TaskExecutor` bean named `eventExecutor`.
4. `PaymentCaptured` as a real application-defined event type.
5. `notificationService` as an appropriate dependency with timeouts and an error-handling policy.

With `@Async("eventExecutor")`, the async interceptor submits the method invocation to the specified executor. `publishEvent(...)` can return before the worker finishes processing. Therefore, `publishEvent()` returning normally **does not prove** the email was sent or the handler completed.

A simple flow:

```text
Publisher thread
  |
  +-- publishEvent(PaymentCaptured)
      |
      +-- Spring finds matching listeners
          |
          +-- @Async proxy submits task
              |
              +-- [running workers]
              +-- [queue of waiting tasks]
              |
              +-- [if full: rejection policy]
  |
  +-- publisher can continue

Worker thread
  |
  +-- picks up task when capacity is available
  +-- listener executes
  +-- success / failure / retry per design
```

**Do not confuse the two distinct async forms:**

- `@Async @EventListener`: async sits on the **listener method**, executed by Spring AOP/interceptor when the event infrastructure invokes the bean proxy.
- `SimpleApplicationEventMulticaster.setTaskExecutor(...)`: async sits on the **multicaster**, potentially applying to all listeners that support async execution.

An application does not need to enable both on the same event path without a clear reason; enabling both can send an event through **multiple submit/hop stages**, complicating latency measurement and executor sizing.

## 3. Understanding `ThreadPoolTaskExecutor` accurately

`org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor` is Spring's adapter/configuration wrapper around Java's `ThreadPoolExecutor`. Key parameters:

| Property | Meaning | Risk if misconfigured |
| --- | --- | --- |
| `corePoolSize` | Number of core threads the pool can maintain | Too low: queue forms early; too high: overhead/DB contention |
| `maxPoolSize` | Maximum thread limit when scaling out | Unbounded: too many threads, memory/context-switch overhead |
| `queueCapacity` | Maximum tasks waiting in the queue | Unbounded: backlog and memory grow, masking overload |
| `keepAliveSeconds` | Idle lifetime of non-core threads | Too short: thread churn; too long: retains resources longer |
| `threadNamePrefix` | Worker thread name prefix | Missing: harder debugging/thread dumps |
| `RejectedExecutionHandler` | How to handle saturation | Ambiguous policy: lost tasks or unintended publisher blocking |
| `waitForTasksToCompleteOnShutdown` | Shutdown policy for already-accepted tasks | Uncontrolled shutdown can lose work |
| `awaitTerminationSeconds` | Wait limit on shutdown | Misconfigured: prolonged shutdown or aborted work |

For `ThreadPoolTaskExecutor`, default settings are typically **core pool 1, practically unbounded max, and unbounded queue**. Because the queue never fills, the pool usually **never scales up to max** as newcomers expect; many tasks simply queue behind a single worker. You must configure **both `queueCapacity` and `maxPoolSize`** to bound resources and allow controlled thread scaling.

### 3.1. Task acceptance algorithm of `ThreadPoolExecutor`

With a finite queue capacity, in principle:

```text
Submit task
  |
  +-- Worker count < corePoolSize?
  |      └-- Yes -> create a new worker to run the task
  |
  +-- Once core is full:
  |      └-- Attempt to put task into queue
  |             └-- Success -> task waits
  |
  +-- Queue full?
  |      └-- Yes -> attempt to add worker (up to maxPoolSize)
  |
  +-- Workers at max and queue full?
         └-- RejectedExecutionHandler handles rejection
```

An easily missed detail: `maxPoolSize=20` **does not mean** 20 workers start immediately when the first 5 tasks arrive. With `corePoolSize=2`, the pool may first run 2 tasks, then **enqueue** subsequent tasks; it usually scales beyond core **only after the queue is full**.

When `queueCapacity=0`, Spring uses direct handoff behavior similar to `SynchronousQueue`, with no finite queue backlog. This can cause the pool to spin up threads rapidly up to `maxPoolSize`, then reject. If `maxPoolSize` is also huge, thread explosion can be dangerous.

**There is no single optimal core/max/queue configuration for every system.** Start from throughput/latency needs and external resource limits, then measure under load.

## 4. Calculating capacity via throughput and service time

Variables:

- \(\lambda\): average event arrival rate, in events/second.
- \(S\): average time a worker spends actively processing one event, in seconds/event.
- \(C\): number of useful concurrent workers (not necessarily just the configured thread count).
- \(\mu \approx C/S\): ideal processing capacity in events/second if tasks are relatively uniform with no other bottlenecks.
- \(W\): average time an event spends in the system from acceptance to completion, including queue time.
- \(L\): average number of tasks being processed or waiting.

By Little's Law under **steady-state** conditions:

\[
L = \lambda W
\]

Considering only tasks **actively being served**, the estimated concurrency demand at average load is:

\[
C_{\text{busy}} \approx \lambda S
\]

### Example 1: steady load

Suppose:

- Publish **200 events/s**.
- Handler takes an average of **50 ms = 0.05 s** to complete.
- Ignoring CPU/DB/network bottlenecks for the moment.

Estimated average busy workers:

\[
C_{\text{busy}} \approx 200 \times 0.05 = 10
\]

If configured with **10 workers** and everything matches the average, utilization approaches 100%; even a small burst or latency spike creates queuing. Targeting roughly 70% utilization for headroom, an initial sizing calculation gives:

\[
C \gtrsim \frac{10}{0.7} \approx 14.3
\]

A starting point to test might be **15 workers**, *provided* CPU, DB pool, and external services support that level of concurrency. This is an **initial sizing estimate**, not proof that 15 is the exact right number. You must also test p95/p99 latency and real burst traffic.

If tasks are CPU-bound and the host only has a few usable CPU cores, increasing from 10 to 15 threads may not raise throughput. If handlers mostly wait on HTTP/DB, higher concurrency can help, but you must account for connection pools, HTTP client limits, and external rate limits.

### Example 2: burst exceeding capacity

Suppose the executor and dependencies are steady at **300 events/s**, but for **2 seconds** a burst of **500 events/s** arrives. Assuming an initially empty queue and ignoring transient effects:

\[
\text{backlog growth} \approx (500 - 300)\times2 = 400\ \text{events}
\]

If input drops back to **100 events/s** after the burst, spare capacity to drain the queue is roughly **200 events/s**, so 400 queued tasks need about **2 seconds** to clear in the ideal model. In reality, tail latency, task size variance, retries, and DB contention can lengthen drain time.

A queue capacity of just 100 tasks will hit its limit early in the scenario above, triggering rejection/backpressure. A queue of 1 million tasks can absorb bursts, yet can also create massive latency if pressure persists. **Increasing queue size cannot fix an arrival rate that continuously exceeds service rate.**

### 4.1. Do not misuse Little's Law

- \(L = \lambda W\) is a steady-state relationship, not a guarantee of zero queuing.
- Use **average time** in the basic formula; do not plug p99 into it and treat the result as a sizing theorem.
- Useful thread count depends on the real throughput of DB, external APIs, CPU, locks, GC, and contention.
- Separate **queue waiting time** from **handler execution time** in measurements.
- To protect SLOs, load-test with realistic peak rates, processing time distributions, and external failures.

## 5. Configuring a bounded executor and choosing a policy

A starting production configuration might look like:

```java
@Configuration
@EnableAsync
class AsyncEventsConfig {

    @Bean("eventExecutor")
    ThreadPoolTaskExecutor eventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(12);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("event-");
        executor.setKeepAliveSeconds(30);
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);
        return executor;
    }
}
```

This is an **illustrative configuration snippet**, not a standalone program. It requires imports for `@Configuration`, `@Bean`, `@EnableAsync`, `ThreadPoolTaskExecutor`, and `java.util.concurrent.ThreadPoolExecutor`; the numbers **are not universal recommendations**.

Characteristics:

- Runs at most **12 worker threads** in this pool; wait queue holds at most **200 tasks**.
- When the queue is full and threads have scaled to 12, the next task is rejected by `AbortPolicy`.
- `@Async("eventExecutor")` explicitly targets this executor; avoid relying on an unspecified default executor per implicit assumptions.
- `ThreadPoolTaskExecutor` translates the underlying executor's rejection into `TaskRejectedException` (part of the `TaskExecutor` contract) on the submission path.
- `setWaitForTasksToCompleteOnShutdown(true)` is a **shutdown policy**, not a durable queue mechanism. If the JVM crashes, pending tasks can still be lost.

Measure how events impact other resources: for example, a 12-thread executor calling an HTTP client capped at 4 connections still bottlenecks on HTTP; adding threads only increases connection wait times.

## 6. Runnable Java 17+ example: full queue and the third event is rejected

This example demonstrates capacity using a **deterministic** scenario rather than random load:

- `ThreadPoolTaskExecutor`: `corePoolSize=1`, `maxPoolSize=1`, `queueCapacity=1`.
- Event A enters the worker and is **held by a latch**, occupying the single thread.
- Event B is submitted and **waits in the queue**, which has exactly one slot.
- Event C is published while **the worker is busy and the queue is full**, so the `@Async` listener submission fails with `TaskRejectedException` via `AbortPolicy`.
- After releasing the latch, the worker finishes A and then B; C never runs.

**Significance:** It is not that event C had the wrong type or an unregistered listener. That is **bounded overload**; if processing C must be guaranteed, the application needs proactive backpressure, persistence, or retry mechanisms.

### 6.1. Project structure

```text
spring-async-capacity-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/AsyncCapacityDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-async-capacity-demo'
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
    mainClass = 'demo.AsyncCapacityDemo'
}
```

Java 17+ and Gradle 8+ suffice for this console project.

### 6.2. `src/main/java/demo/AsyncCapacityDemo.java`

```java
package demo;

import java.util.List;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class AsyncCapacityDemo {

    public record WorkEvent(String id) {}

    // A non-async-proxied bean for observing from main and the worker.
    public static class Probe {
        final CountDownLatch firstStarted = new CountDownLatch(1);
        final CountDownLatch release = new CountDownLatch(1);
        final CountDownLatch finished = new CountDownLatch(2);
        final ConcurrentLinkedQueue<String> completed =
                new ConcurrentLinkedQueue<>();
        final AtomicReference<String> workerName =
                new AtomicReference<>();
    }

    public static class WorkListener {
        private final Probe probe;

        public WorkListener(Probe probe) {
            this.probe = probe;
        }

        @Async("eventExecutor")
        @EventListener
        public void onWork(WorkEvent event) {
            try {
                if ("A".equals(event.id())) {
                    // A starts running, but has not finished yet.
                    probe.firstStarted.countDown();
                    if (!probe.release.await(5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("release timeout");
                    }
                }
                probe.workerName.set(Thread.currentThread().getName());
                probe.completed.add(event.id());
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("interrupted", ex);
            } finally {
                probe.finished.countDown();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class AppConfig {

        @Bean("eventExecutor")
        ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(1);
            executor.setThreadNamePrefix("event-");
            executor.setRejectedExecutionHandler(
                    new ThreadPoolExecutor.AbortPolicy());
            executor.setWaitForTasksToCompleteOnShutdown(true);
            executor.setAwaitTerminationSeconds(5);
            return executor;
        }

        @Bean
        Probe probe() {
            return new Probe();
        }

        @Bean
        WorkListener workListener(Probe probe) {
            return new WorkListener(probe);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            Probe probe = context.getBean(Probe.class);
            ThreadPoolTaskExecutor executor =
                    context.getBean("eventExecutor",
                            ThreadPoolTaskExecutor.class);

            // A holds the worker; use a latch instead of Thread.sleep().
            context.publishEvent(new WorkEvent("A"));
            try {
                if (!probe.firstStarted.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "A did not start on executor");
                }

                // Worker is still held by A: B can only enter the queue.
                context.publishEvent(new WorkEvent("B"));

                int active = executor.getActiveCount();
                int queued =
                        executor.getThreadPoolExecutor()
                                .getQueue().size();

                // A is running + B is queued => C must be rejected.
                boolean rejected = false;
                try {
                    context.publishEvent(new WorkEvent("C"));
                } catch (TaskRejectedException ex) {
                    rejected = true;
                }

                System.out.println("while blocked: active=" + active
                        + ", queued=" + queued);
                System.out.println("third publication rejected="
                        + rejected);

                if (active != 1 || queued != 1 || !rejected) {
                    throw new IllegalStateException(
                            "capacity assertions failed");
                }
            } finally {
                probe.release.countDown();
            }

            if (!probe.finished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "worker tasks did not finish");
            }

            List<String> done = List.copyOf(probe.completed);
            if (!done.equals(List.of("A", "B"))) {
                throw new IllegalStateException(
                        "unexpected completed events: " + done);
            }

            System.out.println("processed=" + String.join(",", done));
            System.out.println("ran on event executor="
                    + probe.workerName.get().startsWith("event-"));
            System.out.println("after drain: queued="
                    + executor.getThreadPoolExecutor()
                            .getQueue().size());
        }
    }
}
```

Run in the project directory:

```bash
gradle -q run
```

Lines **printed by the program** when the configuration and assertions behave as described above:

```text
while blocked: active=1, queued=1
third publication rejected=true
processed=A,B
ran on event executor=true
after drain: queued=0
```

Gradle/Spring may print their own build or logging messages. This output is the expected result per the demo's logic; it **does not assume** fast or slow scheduler timing, because the latch forces A to stay running while B queues and C is submitted.

### 6.3. Explaining the results

1. `AnnotationConfigApplicationContext` creates `WorkListener`, registers `@EventListener`, and enables the async proxy via `@EnableAsync`.
2. Event A is published. The listener proxy submits a task to the pool. Because the pool has no core worker yet, it creates an `event-*` thread to run A.
3. Inside handler A, `firstStarted.countDown()` signals main that A has started, then A waits on `release`.
4. Main waits for `firstStarted` before publishing B. Since the worker is busy and `core=max=1`, B enters the queue of capacity 1.
5. Main captures `active=1`, `queued=1`, then publishes C. The pool cannot create another worker and the queue is full. `AbortPolicy` rejects; the `@Async` submission path throws `TaskRejectedException`, which the publisher catches **in this example**.
6. Even though C was published at the API level, **handler C was not accepted by the executor**. C is never processed; do not call that “processed successfully”.
7. `finally` releases A's latch. The worker finishes A and then pulls B from the queue. Because the pool has one worker, completion order for these two tasks is A then B.
8. Main waits on the completion latch for both tasks, verifying the list `["A", "B"]`, thread prefix, and an empty queue.

**Why use `try/finally`?** If the test unexpectedly throws while checking capacity, `finally` still releases worker A, preventing context shutdown from hanging indefinitely on the task. The program does not use sleeps to guess ordering.

**Limitations of the example:** `AbortPolicy` surfaces the error on the submit path. Another policy might run the task on the publisher thread, discard the task, or run custom logic; do not generalize the output above to every executor/multicaster.

## 7. Rejection policies and backpressure

When an executor runs out of capacity, deciding what happens to rejected tasks is a **business decision**, not merely a technical choice.

Common policies in Java's `ThreadPoolExecutor`:

| Policy | When pool and queue are full | Pros | Risks |
| --- | --- | --- | --- |
| `AbortPolicy` | Throws `RejectedExecutionException` (via `ThreadPoolTaskExecutor`, may be `TaskRejectedException`) | Surfaces overload clearly, easy to measure rejections | Caller must handle errors; events can be lost if merely caught and ignored |
| `CallerRunsPolicy` | Runs task directly on submitting thread **if executor is not shut down** | Creates backpressure by slowing down the publisher | HTTP/transaction threads can block; during shutdown, policy may drop tasks |
| `DiscardPolicy` | Drops the rejected task | Does not slow down the publisher | **Silent event loss**, very dangerous for business-critical events |
| `DiscardOldestPolicy` | Drops the oldest waiting task and retries submission | Prioritizes newer tasks | Loses older tasks, inverts ordering semantics; unsuitable for critical work |
| Custom handler | Depends on implementation: measure, log, route to durable queue, fail | Can meet specialized requirements | Must thoroughly test overload, secondary errors, and shutdown |

### 7.1. Choosing `AbortPolicy` for demos and fail-fast

An event that an executor cannot accept should usually make the system **explicitly aware** of that fact. `AbortPolicy` is easy to test; however, the caller must decide what comes next:

```java
try {
    publisher.publishEvent(new ReportRequested(reportId));
} catch (TaskRejectedException ex) {
    metrics.recordRejectedEvent();
    // Depending on design: return overload status, route work to a
    // durable queue, or let the transaction fail before commit.
    throw ex;
}
```

This is **illustrative code**; `metrics`, `ReportRequested`, and `reportId` are supplied by the application. Do not treat catching and swallowing silently as successful handling. In an event dispatch with multiple listeners, rejection can occur **after an earlier listener has already produced side effects**; never assume `publishEvent` is atomic across all listeners.

### 7.2. Why is `CallerRunsPolicy` both useful and dangerous?

If the publisher is a request thread, this policy can force the request **to execute a slow listener itself** when the pool is full. That slows new submissions, creating backpressure. However:

- HTTP request p99 latency spikes abruptly;
- The publisher thread may be holding locks or a transaction;
- If the event was published before commit, side effects may run before the original transaction completes;
- When the executor has shut down, `CallerRunsPolicy` may skip running the task without necessarily throwing as you expect;
- Running the listener on the caller thread alters security/MDC/transaction context compared to a worker.

Use only when you clearly understand the event contract and have tested saturation; do not pick it as a universal “way to avoid TaskRejectedException”.

### 7.3. Upstream backpressure

If arrival rate exceeds sustained throughput, apply pressure **before the queue fills**:

- Limit request concurrency/rate limit or return `429 Too Many Requests` / `503 Service Unavailable` per API contract.
- Use a semaphore/bulkhead at the producer or consumer; acquire an admission token before accepting work.
- Move critical work to a **durable queue/outbox** that workers read according to capacity; keep the publisher decoupled from in-memory queues.
- Deduplicate redundant events or coalesce notifications where tracking every individual occurrence is unnecessary by business rules.
- Partition events by priority so one slow category does not monopolize the queue of critical categories.
- Optimize handler logic and I/O, shorten connection hold times, and configure timeouts/retries/backoff.

**Do not use unbounded queues as a substitute for backpressure**; that only delays when overload becomes visible.

## 8. Sizing thread pools by workload type

### 8.1. CPU-bound event listeners

Examples: image encoding, large JSON compression/transformation, heavy computation. CPU is the bottleneck; if a host only has 4 available CPU cores, spawning 100 CPU-bound workers will not yield 25x throughput. Instead, it causes context switching and cache pressure.

Practice: try a pool close to the number of CPU cores **actually allocated to the container**, leaving headroom for HTTP/GC and other threads. Measure CPU utilization, runnable threads, GC pauses, and task latency. If some CPU cores serve API traffic, background executors should not starve them.

### 8.2. I/O-bound event listeners

Examples: calling REST services, sending emails, writing to a DB. Threads spend most time waiting on I/O, so concurrency may need to exceed CPU cores. However, the real constraints may be:

- JDBC connection pool size and concurrent transactions;
- HTTP client pool / connections per route;
- Partner rate limits;
- Network call timeouts;
- Open sockets / file descriptors;
- Retry traffic amplification during downstream failures.

If an HTTP service only allows 20 concurrent requests, a 100-thread executor simply builds a backlog **inside the HTTP client** without increasing throughput. Size the entire chain, not just the executor.

### 8.3. Heavy and light events sharing one pool

A slow email handler or timing-out external API can stall many lightweight events in the same queue. Consider **separate executors per workload/SLO**:

```java
@Async("emailExecutor")
@EventListener
public void sendEmail(EmailRequested event) {
    // I/O-bound, constrained by email provider rate limits.
}

@Async("computeExecutor")
@EventListener
public void calculate(CalculationRequested event) {
    // CPU-bound, sized according to core count.
}
```

This is an illustrative snippet. It requires two executor beans, Spring-managed listeners, and `@EnableAsync`. Splitting pools provides **bulkhead isolation**, reducing the chance that one slow downstream paralyzes all event processing. However, adding pools requires managing total thread counts, memory, and application-wide shutdown.

## 9. Which metrics show whether capacity is appropriate?

Do not watch only `poolSize` or publish counts. Track **rate, queue pressure, wait times, failure rates, and side-effect completion**.

| Metric | Meaning / signal |
| --- | --- |
| Active threads | How many workers are busy; staying near max signals saturation risk |
| Pool size / core / max | Whether the pool is scaling out or sitting at core |
| Queue size / remaining capacity | Current backlog and distance to rejection |
| Queue waiting time | How long events wait before the handler begins |
| Handler execution time | Actual work duration: mean/p95/p99 |
| End-to-end event latency | From event receipt/recording until side effect completes |
| Submitted / completed task rate | Whether work debt and backlog are growing |
| Rejected tasks rate | How often the executor runs out of capacity |
| Handler failures / retries | Events accepted but failing or needing retries |
| Oldest pending task age | Age of the longest-waiting task, more useful than queue size for SLOs |
| DB/HTTP pool utilization | Reveals downstream bottlenecks |
| Shutdown pending tasks | Remaining work when the application stops |

Spring's `ThreadPoolTaskExecutor` exposes several indicators:

```java
int active = executor.getActiveCount();
int poolSize = executor.getPoolSize();
int queue = executor.getThreadPoolExecutor().getQueue().size();
long done = executor.getThreadPoolExecutor().getCompletedTaskCount();
```

This is an **illustrative snippet**, where `executor` is an already-created `ThreadPoolTaskExecutor` bean. The values are **snapshots of changing state**, not an atomic transaction. For instance, queue size can change immediately after being read; therefore use metric aggregation and trend-based alerts rather than building business logic that relies strictly on instantaneous reads.

In Spring Boot + Micrometer applications, executor metrics can be bound to monitoring depending on configuration and bean type. Verify the actual meter names in your system, dashboards, and version rather than assuming every custom executor automatically exposes identical metric names.

### 9.1. Recording actual wait times

An event can carry `occurredAt`, but if clocks between publisher and worker are unsynchronized across services, timestamps are not accurate enough for system-wide latency measurement. For in-process events, you can record **monotonic time** at submit and at handler start, or attach a `TaskDecorator` to observe queue waiting time.

An illustration:

```java
long submittedAt = System.nanoTime();
publisher.publishEvent(new WorkRequested(id, submittedAt));

// Inside the handler, before doing work:
long queueWaitNanos = System.nanoTime() - event.submittedAtNanos();
```

This is **in-process illustrative code**, unsuitable for persisting `nanoTime` across JVMs or replaying later. `System.nanoTime()` is only meaningful for elapsed intervals within the same process; if events cross brokers or hosts, use synchronized clocks and proper distributed tracing.

Note that `queueWaitNanos` inside the handler can include dispatch and proxy overhead, not strictly time inside the `ThreadPoolExecutor` queue. For exact isolation, instrument at task submission/start or via a task decorator.

### 9.2. Alerting on backlog growth rate

Example signals:

- Queue utilization stays high for several minutes;
- `rejected tasks > 0` on critical event categories;
- Queue waiting p99 breaches SLO;
- Completed task rate stays below incoming task rate over an extended window;
- Active threads near max while CPU/DB utilization is low: likely I/O or lock contention;
- Oldest unprocessed event age grows continuously.

Alerts must tie to **operational actions**: scale out, shed/throttle traffic, pause a source, enable backpressure, inspect downstream errors, or process DLQs. Merely raising queue alert thresholds degrades SLOs while silencing alerts.

## 10. The two async mechanisms are not strictly equivalent

### 10.1. `@Async` on listeners

```java
@Async("eventExecutor")
@EventListener
public void handle(WorkRequested event) {
    // Handler runs through the async method proxy when configured properly.
}
```

Benefit: only the annotated method uses the executor, making it easy to dedicate separate pools per event type. Requirements:

- `@EnableAsync`;
- a Spring-proxied bean;
- a method signature supported by `@Async` (`void` or `Future`/`CompletableFuture`);
- awareness of self-invocation (`this.method()` bypasses the proxy);
- configuring `AsyncUncaughtExceptionHandler` for exceptions in `void` async methods.

`@Async @EventListener` **does not support publishing new events via listener return values**. If a follow-up event is needed, call `ApplicationEventPublisher.publishEvent(...)` explicitly inside the handler after the work succeeds.

### 10.2. `SimpleApplicationEventMulticaster.setTaskExecutor(...)`

Another approach is configuring an executor on the event multicaster:

```java
@Bean(name = "applicationEventMulticaster")
ApplicationEventMulticaster applicationEventMulticaster(
        @Qualifier("eventExecutor") TaskExecutor executor) {

    SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();
    multicaster.setTaskExecutor(executor);
    return multicaster;
}
```

This is an **illustrative snippet**, requiring imports for `ApplicationEventMulticaster`, `SimpleApplicationEventMulticaster`, `Qualifier`, `TaskExecutor`, and `Bean`. Replacing the context's multicaster with the special `applicationEventMulticaster` bean allows listeners supporting async execution to be submitted through this executor.

**Important note:** Not every `ApplicationListener` permits async execution via the multicaster. In Spring 6.2, `ApplicationListener.supportsAsyncExecution()` determines this; transaction-synchronized listeners such as `TransactionalApplicationListener` must perform **synchronization registration on the publisher thread** and declare that they do not support async execution via the multicaster. Therefore, if you want post-commit work on a background thread, placing an appropriate `@Async` configuration **on the handler itself** is a separate approach that must preserve transaction phase semantics.

Additionally, **rejection handling can differ between the two paths**. Specific policies on the multicaster, executor, error handler, and version determine whether a task throws, runs on another thread, or falls back. Do not blindly apply “event C throws `TaskRejectedException`” from the section 6 `@Async` example to a customized multicaster.

### 10.3. Why avoid enabling both unintentionally?

If a custom multicaster submits a listener invocation to one executor, and the listener is also `@Async` so its proxy submits again, each event can go through **two task scheduling steps**. This complicates queue/capacity math, obscures thread context/tracing, and creates two separate rejection points.

Simpler architecture:

- Choose **`@Async` per listener** when you need isolation by workload and executor.
- Choose a **multicaster executor** only when you have a clear reason to make most listeners async and have reviewed transaction/ordering/error semantics.
- Keep listeners synchronous if side effects must finish before the publisher returns, or if the work is too trivial to justify scheduling overhead.

## 11. `@TransactionalEventListener`, transactions, and saturation

Business example:

```java
@Transactional
public void createOrder(String orderId) {
    repository.insert(orderId);
    publisher.publishEvent(new OrderCreated(orderId));
}
```

A post-commit listener:

```java
@Async("eventExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCommitted(OrderCreated event) {
    notificationService.send(orderIdFrom(event));
}
```

These are **illustrative snippets**, requiring Spring transaction infrastructure, application-defined repositories/services, and an executor. `AFTER_COMMIT` requires the event to be published **within an active compatible transaction**; the listener runs after the transaction commits and can continue on the executor if configured via async advice.

Capacity details requiring special care:

1. **Worker threads do not automatically carry the publisher's imperative transaction.** If the handler needs to write to the DB, call a service bean with an appropriate new transaction.
2. Immediately after commit, resources of the original transaction may still be bound to the publisher thread during cleanup. When a callback writes to the DB, consider `REQUIRES_NEW` rather than assuming `REQUIRED` creates a fresh commit.
3. If the executor rejects the async task submission during the post-commit callback, **the main transaction has already committed**. You cannot roll back the saved order simply because the queue was full.
4. If the event must still be processed even if the JVM dies after commit, **do not rely on an in-memory queue**; use a transactional outbox or persisted queue.
5. `@TransactionalEventListener` defaults to `fallbackExecution=false`: if published outside a transaction, the listener can be skipped completely.
6. With multiple listeners on an event, one listener being rejected does not mean earlier listeners did not run.

**Design point:** If a post-commit event represents critical work (invoicing, payment requests, accounting sync), executor capacity must be paired with **persistence and retries**. Raising max threads alone does not survive crashes or sustained overload.

### 11.1. Transactional outbox to prevent lost work

```text
Transaction T1
  +-- INSERT/UPDATE business data
  +-- INSERT outbox(eventId, payload, status=NEW)
  +-- COMMIT
       |
       +-- background worker reads outbox by batch/capacity
           |
           +-- submit/execute with concurrency limits
           +-- success -> mark DONE
           +-- transient failure -> retry with backoff
           +-- permanent failure -> dead-letter/quarantine
```

An outbox puts the **intent to run post-processing** into the same transaction as the business change; if a process crashes, another worker can resume. Idempotency is still required when downstream succeeds but local status update fails, triggering a retry.

A simpler durable queue/broker approach can also fit if the infrastructure already exists, provided DB state and message publication stay synchronized. A JVM executor thread pool is not a message broker.

## 12. Retries and capacity: avoiding load amplification during downstream failures

A handler calling an HTTP service can hit timeouts. If every failed request is retried immediately several times inside the listener itself, **one incoming event generates multiple external calls**, raising service time and lowering throughput.

Example:

```text
Normal:
  100 events/s x 1 HTTP call = 100 calls/s

Downstream failing and immediately retrying up to 3 times:
  100 events/s x up to 3 attempts = 300 calls/s
```

Clearly define **3 attempts** as total calls, not three retries plus the initial attempt. Actual load depends on failure rate and retry policy; the example illustrates the maximum amplification factor.

During widespread failures, instead of retrying synchronously inside the worker:

- Exponential backoff + jitter, capping total time/attempts.
- Circuit breakers when downstream stops serving.
- Per-partner rate limits/bulkheads.
- A durable retry queue with `nextAttemptAt`, instead of blocking worker threads with sleep.
- Dead-letter handling for unrecoverable errors.
- Idempotency keys for side effects that could be sent twice.

**Do not keep worker threads sleeping for seconds while backlog grows** when a scheduler or durable queue can be used. Doing so directly reduces the executor's available throughput.

## 13. Shutdown and lifecycle: capacity when the application stops

A pool might hold:

```text
active=8 tasks
queued=120 tasks
```

If a deploy, scale-down, or pod kill occurs right then, in-memory tasks can be lost. `waitForTasksToCompleteOnShutdown` and timeouts provide **orderly shutdown under certain conditions**, but do not protect against `SIGKILL`, crashes, power loss, or containers forcibly killed past their grace period.

Account for:

- Average/p99 duration of currently running tasks;
- Number of queued tasks and time needed to drain;
- Whether DB connections and HTTP clients remain alive during shutdown;
- Pod termination grace period and readiness/draining;
- Whether another node can resume work if tasks are persisted;
- How the rejection policy behaves once the executor has shut down.

**Do not rely on unbounded shutdown waits for system reliability.** If a task is critical, persist it durably first so workers can recover even after an abrupt shutdown.

For example, `setWaitForTasksToCompleteOnShutdown(true)` in the demo only helps finish A and B within the same process; C was already rejected and therefore **does not reappear** on the next application run.

## 14. Deterministic capacity and overload testing

### 14.1. Why avoid `Thread.sleep()` to induce races?

A test like:

```java
publishEvent(A);
Thread.sleep(20);
publishEvent(B);
publishEvent(C);
```

can flake: on a developer laptop the worker finishes in time, while on a loaded CI runner with different thread scheduling the queue fills earlier. Using `CountDownLatch`/barriers as in section 6 creates **deterministic saturation conditions**.

Tests should verify:

1. A has started running, occupying one worker.
2. B has entered the single-slot queue.
3. C is rejected per the configured policy.
4. Once A is released, both A and B complete.
5. C produces no side effects and is not silently counted as successful.
6. Exceptions/rejections are observed and recorded in metrics.
7. Shutdown does not hang while tasks are waiting.

### 14.2. Load testing to validate real SLOs

Beyond deterministic unit/integration tests, load-test with:

- Steady, peak, and burst rates rather than just a few events;
- Handler duration distributions, especially p95/p99;
- DB/HTTP service latencies and rate limits;
- CPU throttling, memory/GC, and GC pauses;
- Retries under failure, circuit-breaker states, and rejected event counts;
- Queue drain speed once traffic returns to normal;
- Failover/deploy/shutdown while tasks remain queued.

Report **completed throughput and event latency from enqueue to completion**, not merely `publishEvent`/second. A system accepting 10,000 events/s while completing only 1,000 events/s is not “achieving 10,000 events/s” from a business standpoint.

### 14.3. Useful assertions

In tests:

```java
assertEquals(1, executor.getActiveCount());
assertEquals(1,
        executor.getThreadPoolExecutor().getQueue().size());
assertThrows(TaskRejectedException.class,
        () -> publisher.publishEvent(new WorkEvent("C")));
```

This is an **illustrative snippet**, assuming A is held by a latch, B is queued, `AbortPolicy` is active, and event C is handled solely by the `@Async` listener using that executor. Without deterministic saturation setup, these assertions would be unstable.

After releasing and awaiting `finished`, assert that expected events actually completed and the queue is empty. A `@RecordApplicationEvents` test may record that C **was published** even though C's listener was rejected by the executor; do not confuse a publisher recorder with a completion receipt.

## 15. Diagnosing common capacity issues

| Symptom | Likely cause | Remediation |
| --- | --- | --- |
| `@Async` listener shows high latency under load | Queue backlog, busy workers, or slow downstream | Measure queue wait, service time, and dependency limits |
| `maxPoolSize=50` yet pool uses only 1 thread | Default queue too large/unbounded, core=1 | Set finite queue capacity and appropriate core size |
| High CPU, adding threads makes it slower | CPU-bound overload, context switching | Cap concurrency to real CPU cores, optimize computation |
| Low CPU yet active threads hit max | Blocking I/O, locks, or DB/HTTP pool contention | Check I/O waits, timeouts, and dependency pools |
| `TaskRejectedException` on publish | Pool + queue full and rejection policy | Admission control, durable queue, backpressure, data-driven scaling |
| Event “published” yet never processed | Executor rejection or async failure | Distinguish accepted/submitted/completed; monitor errors |
| HTTP p99 spikes unexpectedly when queue fills | `CallerRunsPolicy` running on publisher thread | Consider AbortPolicy and explicit backpressure |
| Queue grows endlessly without draining | Arrival rate exceeds sustained throughput | Reduce input, raise real capacity, optimize service, or use a persisted queue |
| Retries make outages worse | Retry storm, external rate limits | Backoff+jitter, circuit breaker, and attempt caps |
| Inside a transaction, async event misses newly saved DB rows | Worker runs before commit; different transaction thread | `AFTER_COMMIT` or outbox and proper transaction boundaries |
| Rejected after commit yet order remains in DB | Main transaction already committed | Write outbox in T1; do not expect post-commit rollback |
| Events lost during deploy | In-memory queue is not durable | Durable outbox/broker, graceful drain |
| Flaky queue-size tests | Uncontrolled scheduling | Use latches to hold workers and stabilize queue state |
| Event does not run with `@Async` | Missing `@EnableAsync`, wrong executor name, or bypassed proxy | Check bean/proxy/executor configuration |
| Other listeners slow down despite lightweight events | Shared pool monopolized by slow event type | Separate executors per workload/SLO |

## 16. Checklist for taking async event executors to production

### Architecture and reliability

- [ ] Which events can be dropped under overload, and which must be persisted/retried?
- [ ] If DB data commits while task submission is rejected, is there an **outbox** or recovery path?
- [ ] Are there event IDs, correlation IDs, and idempotency keys to avoid duplicate side effects?
- [ ] Are mutable entities, request objects, and transaction-bound objects kept from crossing threads?
- [ ] Are events published in the proper transaction phase when `AFTER_COMMIT` is needed?

### Capacity and operations

- [ ] Have steady arrival rate, burst rate, and mean/p95/p99 handler service times been measured?
- [ ] Has initial concurrency been calculated from throughput and service time, then load-tested?
- [ ] Are `corePoolSize`, `maxPoolSize`, and `queueCapacity` explicitly bounded?
- [ ] Do dependency pools, rate limits, memory, and CPU have adequate headroom?
- [ ] Was the rejection policy chosen intentionally and tested under overload and shutdown?
- [ ] Are metrics in place for active threads, queue depth, handler latency, rejections, failures, retries, and oldest pending age?
- [ ] Are alerts tied to concrete actions as queues approach capacity?

### Execution path and testing

- [ ] Was `@Async` per listener vs. multicaster executor chosen intentionally without double scheduling?
- [ ] Are `@EnableAsync` and executor names exact, and are methods intercepted by Spring proxies?
- [ ] Have you verified `@TransactionalEventListener` is not routed onto a wrong-thread multicaster executor?
- [ ] Do saturation tests use latches/barriers rather than `Thread.sleep`?
- [ ] Does shutdown have a draining plan, timeouts, and recovery for durable tasks?

**Conclusion:** Executor capacity is part of the **operational and reliability contract** of Spring Application Events. Configure `ThreadPoolTaskExecutor` with bounded `corePoolSize`, `maxPoolSize`, `queueCapacity`, and a deliberate rejection policy; size according to real event rates and processing times; measure latency and backlogs rather than publish counts alone; and when critical work must survive overload or crashes, combine backpressure with a durable outbox/queue. `@Async` only changes scheduling—**it does not create extra CPU, database connections, or durability**.

## Official documentation

- [Spring Framework 6.2 — Task Execution and Scheduling, `@Async` and executors](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 — `ThreadPoolTaskExecutor` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework 6.2 — `SimpleApplicationEventMulticaster` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework 6.2 — `ApplicationListener.supportsAsyncExecution()`](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationListener.html)
- [Spring Framework 6.2 — Application Events and Asynchronous Listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2 — Observability and Context Propagation](https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html)
- [Java SE 17 — `ThreadPoolExecutor` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
