# Choosing a Bounded Executor for Spring Application Events

## 1. What Is a Bounded Executor and Why Do Events Need One?

By default, Spring Framework dispatches application events **synchronously**: calling `ApplicationEventPublisher.publishEvent(...)` normally invokes listeners on the publisher's own thread. When an application configures `SimpleApplicationEventMulticaster.setTaskExecutor(...)`, listeners that support async execution can run on other threads.

This frees the request from waiting for every listener to finish, yet creates a new problem: if events arrive faster than they can be processed, pending tasks accumulate. An executor with too many threads can exhaust CPU, memory, database connections, or sockets; a nearly unbounded queue can leave events waiting for minutes even while the publisher receives a fast response.

A **bounded executor** is an executor with explicit limits on all three:

- **Concurrent execution count:** maximum number of worker threads that can run.
- **Pending task count:** maximum number of tasks held in the queue before processing.
- **Full-capacity policy:** what the system does when all workers are busy and the queue has reached its limit.

In Spring, `ThreadPoolTaskExecutor` is a common choice because it configures `corePoolSize`, `maxPoolSize`, `queueCapacity`, and `RejectedExecutionHandler`, while exposing operational metrics such as `activeCount` and `queueSize`.

One crucial limit: **each eligible listener can become a separate task** when the multicaster uses an executor. One event with three async listeners can result in three task submissions. Therefore, executor capacity is measured in **listener tasks**, not directly in event objects.

## 2. Event Dispatch Mechanism and Where the Executor Fits

Typical flow:

```text
HTTP request / scheduled job / application service
                    |
                    | publishEvent(new OrderSubmitted(...))
                    v
       SimpleApplicationEventMulticaster
                    |
              select listeners
                    |
            supportsAsyncExecution?
                 /         \
               Yes          No
                |             |
                v             v
          TaskExecutor    Run directly
                |         on publish thread
         +------+------+    
         |             |
     Worker threads  Bounded queue
         ^             |
         +-------------+
                |
         listener runs

    When workers/queue are full:
    executor applies rejection policy;
    the multicaster may also handle the rejection
    depending on implementation/version.
```

`SimpleApplicationEventMulticaster` runs synchronously if no task executor is set. When an executor is configured, it only dispatches asynchronously those `ApplicationListener` instances that declare async support; an important example of a listener that **does not support** moving to another thread is `TransactionalApplicationListener`.

Do not equate "listener has been queued" with "event has been processed successfully." Queuing is only the step of admitting the task into process memory.

## 3. Three Parameters Governing ThreadPoolTaskExecutor Behavior

| Parameter | Meaning | Question to Answer |
| --- | --- | --- |
| `corePoolSize` | Number of core threads the pool prefers to create when receiving tasks | What is the steady-state concurrency level? |
| `maxPoolSize` | Maximum number of workers when the pool must scale up | How many concurrent operations can downstream systems handle? |
| `queueCapacity` | Number of tasks that can wait in the queue | How long can events wait before being considered overloaded? |

Under typical configuration, the `ThreadPoolExecutor` backing `ThreadPoolTaskExecutor` admits work in this order:

1. If running workers are fewer than `corePoolSize`, create another worker.
2. Once core size is reached, try **enqueuing the task**.
3. If the queue is full and workers are below `maxPoolSize`, create another worker.
4. If workers have reached max and the queue is also full, invoke the task rejection policy.

Example:

```text
corePoolSize = 2
maxPoolSize  = 4
queueCapacity = 3

Task 1, 2      -> can activate 2 core workers
Task 3, 4, 5   -> enter queue (while workers are busy)
Task 6, 7      -> pool can scale up to 3rd and 4th workers
Task 8         -> overloaded if 4 workers stay busy and queue is full
```

This is an **illustrative model at a moment of saturation**, while earlier tasks have not completed. If workers finish while new tasks arrive, the outcome differs.

With `ThreadPoolTaskExecutor`, `queueCapacity > 0` uses a bounded `LinkedBlockingQueue` of the configured size. `queueCapacity = 0` uses a `SynchronousQueue`, meaning there is no conventional waiting buffer; the pool must hand off directly or create workers up to max. Queue capacity should generally be chosen from latency bounds, not just because plenty of RAM is available.

**Default configuration trap:** In Spring Framework 6.2, `ThreadPoolTaskExecutor` defaults to `corePoolSize = 1`, `maxPoolSize = Integer.MAX_VALUE`, and `queueCapacity = Integer.MAX_VALUE`. Because the queue is virtually unbounded, the pool often uses only one core worker and accumulates backlog; raising `maxPoolSize` alone without bounding the queue may fail to achieve the intended concurrency increase.

## 4. Configuring a Dedicated Bounded Executor for Application Events

Spring Configuration example:

```java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.context.support.AbstractApplicationContext;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class EventExecutorConfig {

    @Bean("applicationEventExecutor")
    public ThreadPoolTaskExecutor applicationEventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setKeepAliveSeconds(60);
        executor.setThreadNamePrefix("app-events-");

        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }

    @Bean(name =
            AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME)
    public SimpleApplicationEventMulticaster applicationEventMulticaster(
            @Qualifier("applicationEventExecutor")
            ThreadPoolTaskExecutor executor) {

        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();
        multicaster.setTaskExecutor(executor);
        return multicaster;
    }
}
```

This is a **configuration snippet for use inside an application with a Spring Context**, not a standalone program. Spring initializes and manages the lifecycle of the `ThreadPoolTaskExecutor` returned by `@Bean`. The multicaster bean must have the standard name `applicationEventMulticaster` so `ApplicationContext` uses it.

The numbers `4 / 8 / 100` are only **syntactic examples**, not optimal settings for every system. For listeners calling slow external services, all eight workers might block on I/O; for CPU-bound listeners, eight threads on a two-CPU machine can cause significant contention. Choosing real numbers requires measuring throughput, processing duration, downstream capacity, and latency limits.

`AbortPolicy` is the pool's rejection policy upon saturation. When calling `ThreadPoolTaskExecutor.execute(...)` directly, Spring typically throws `TaskRejectedException`. **Do not assume `publishEvent(...)` always throws that exact exception**: the multicaster is an intermediary call layer; behavior when `executor.execute` rejects depends on the Spring implementation and version, and some versions have fallback paths that run the listener on the caller thread when the executor rejects. Verify via integration tests against the exact Spring version deployed. When you must guarantee an event is rejected **before publishing**, perform admission control on the publishing side or use a delivery system with an explicit accept/reject contract.

## 5. Runnable Java 17 Example: Events Running on a Bounded Executor

The example below uses **Java 17+, Maven, and Spring Framework 6.2.12**. It has two modes:

- **Default:** publishes two events and proves the listener runs on an executor worker thread.
- **`pressure`:** separately tests queue-full behavior on `ThreadPoolTaskExecutor` itself. This mode calls `execute(...)` directly to isolate pool behavior from any fallback behavior of the multicaster.

Directory structure:

```text
bounded-spring-events/
├── pom.xml
└── src/main/java/demo/BoundedEventDemo.java
```

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bounded-spring-events</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
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
                    <mainClass>demo.BoundedEventDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Contents of `src/main/java/demo/BoundedEventDemo.java`:

```java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.context.support.AbstractApplicationContext;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class BoundedEventDemo {

    public record TaskCreated(String id) {}

    public static class TaskListener {
        private final CountDownLatch finished = new CountDownLatch(2);

        @EventListener
        public void onTask(TaskCreated event) {
            if (!Thread.currentThread().getName()
                    .startsWith("app-events-")) {
                throw new IllegalStateException(
                        "Unexpected executor thread");
            }
            System.out.println("HANDLED " + event.id());
            finished.countDown();
        }

        public boolean awaitBoth() throws InterruptedException {
            return finished.await(5, TimeUnit.SECONDS);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean("eventExecutor")
        public ThreadPoolTaskExecutor eventExecutor() {
            var executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(2);
            executor.setThreadNamePrefix("app-events-");
            executor.setRejectedExecutionHandler(
                    new ThreadPoolExecutor.AbortPolicy());
            return executor;
        }

        @Bean(name =
                AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME)
        public SimpleApplicationEventMulticaster applicationEventMulticaster(
                @Qualifier("eventExecutor")
                ThreadPoolTaskExecutor executor) {
            var multicaster = new SimpleApplicationEventMulticaster();
            multicaster.setTaskExecutor(executor);
            return multicaster;
        }

        @Bean
        public TaskListener taskListener() {
            return new TaskListener();
        }
    }

    private static void springEventExample() throws InterruptedException {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            TaskListener listener = context.getBean(TaskListener.class);

            context.publishEvent(new TaskCreated("E1"));
            context.publishEvent(new TaskCreated("E2"));

            if (!listener.awaitBoth()) {
                throw new IllegalStateException("Listener timed out");
            }
        }
    }

    private static void executorPressureExample()
            throws InterruptedException {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(1);
        executor.setThreadNamePrefix("pressure-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.initialize();

        var firstStarted = new CountDownLatch(1);
        var unblockFirst = new CountDownLatch(1);
        var twoFinished = new CountDownLatch(2);

        try {
            executor.execute(() -> {
                firstStarted.countDown();
                try {
                    unblockFirst.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
                System.out.println("FINISHED 1");
                twoFinished.countDown();
            });

            if (!firstStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }

            // Task 1 is running; task 2 enters the queue of capacity 1.
            executor.execute(() -> {
                System.out.println("FINISHED 2");
                twoFinished.countDown();
            });

            // The pool already has one busy worker and one queued task.
            try {
                executor.execute(() ->
                        System.out.println("UNEXPECTED 3"));
                throw new IllegalStateException(
                        "Task 3 should have been rejected");
            } catch (TaskRejectedException expected) {
                System.out.println("REJECTED 3");
            }
        } finally {
            unblockFirst.countDown();
        }

        try {
            if (!twoFinished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Tasks did not finish");
            }
        } finally {
            executor.shutdown();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        if (args.length > 0 && "pressure".equals(args[0])) {
            executorPressureExample();
        } else {
            springEventExample();
        }
    }
}
```

To run event mode:

```bash
mvn -q compile exec:java
```

Lines printed by the application:

```text
HANDLED E1
HANDLED E2
```

Here `corePoolSize = maxPoolSize = 1`, so one worker processes both events in the order tasks enter the queue. Each task verifies the thread name starts with `app-events-`; if the listener mistakenly ran on the caller thread, the example would fail to print both success lines and the wait would throw an error. `@EnableAsync` is not required because this is an executor used by the multicaster, not `@Async`.

To run saturation test mode:

```bash
mvn -q compile exec:java -Dexec.args=pressure
```

Lines printed by the application:

```text
REJECTED 3
FINISHED 1
FINISHED 2
```

Reason: task 1 holds the worker using `CountDownLatch`, task 2 sits in the capacity-1 queue, and task 3 is rejected by `AbortPolicy`. Spring's `ThreadPoolTaskExecutor.execute` throws `TaskRejectedException`; once the test finishes, the latch opens so tasks 1 and 2 complete. The example uses no `Thread.sleep(...)`, avoiding guesswork about thread scheduling.

**Boundary of the example:** `pressure` mode tests the **executor directly**. It does not assert that a rejected `ApplicationEventPublisher.publishEvent` call will always throw an exception or always drop the event. For real events, test the actual `SimpleApplicationEventMulticaster` and Spring version, including full queue, shutting-down application, and non-async-capable listeners.

## 6. Understanding Rejection Policies Accurately

JDK `ThreadPoolExecutor` provides these primary policies:

| Policy | When queue and workers are both full | Impact on events |
| --- | --- | --- |
| `AbortPolicy` | Throws `RejectedExecutionException`; Spring `TaskExecutor` may wrap as `TaskRejectedException` | Produces a clear overload signal at executor level; final behavior through multicaster must be tested |
| `CallerRunsPolicy` | If executor is not shut down, runs the task immediately on the thread calling `execute` | Creates backpressure by slowing the publisher, but can prolong HTTP requests and alter thread context |
| `DiscardPolicy` | Drops the task without reporting an error | Risk of silent event loss; rarely suitable for critical processing |
| `DiscardOldestPolicy` | Drops the oldest queued task and retries inserting the new task | Can lose older events and break business ordering |

Sample `CallerRunsPolicy`:

```java
executor.setRejectedExecutionHandler(
        new ThreadPoolExecutor.CallerRunsPolicy());
```

The snippet above only illustrates an alternative to `AbortPolicy`. It is not a default choice for every event type. If the publisher is holding a lock or inside a transaction, unexpectedly running the listener on the caller thread can introduce high latency, hold onto transactional connections, or cause deadlocks if the listener waits on resources held by the caller.

**Multicaster nuance:** The executor and multicaster are two separate policy layers. When an executor rejects, how `SimpleApplicationEventMulticaster` handles the exception can vary across versions: some implementations use a fallback path invoking the listener inline. In that case, a bounded pool still caps **workers/queue**, yet does not necessarily cap total running work if many publishers are forced to run listeners synchronously. Thus, "using `AbortPolicy`" alone is not enough to claim the system will fail fast or drop events under load.

For provable admission bounds, consider an admission control mechanism **before** `publishEvent` or a queue/broker capable of explicitly confirming whether work was accepted or rejected. Do not mask overload incidents merely by adding logs.

## 7. Sizing Pool and Queue from Measurements

Reasonable sizing depends on workload type and acceptable latency.

### 7.1. Distinguishing CPU-Bound vs. I/O-Bound

- **CPU-bound** (heavy serialization, compression, computation): too many workers cause context switching and CPU contention; start testing near available CPU cores and benchmark.
- **I/O-bound** (HTTP calls, JDBC, email): workers mostly wait on I/O; more threads than CPU cores may be needed, yet thread counts must match connection pools, external rate limits, and timeouts.
- **Mixed workload**: if light and heavy listeners share an executor, heavy tasks can occupy all workers. Consider separate pools or routing event handling paths according to business requirements.

### 7.2. Estimating Concurrency

When load is relatively steady, the number of **actively executing** tasks needed for average traffic can be estimated as:

```text
concurrentWorkers ≈ tasksPerSecond × averageExecutionSeconds
```

For example, with **80 listener invocations/second** and an average duration of **50 ms**:

```text
80 × 0.050 = 4 busy workers on average
```

This estimates **active service** concurrency only, excluding variance, percentiles, downstream stalls, GC pauses, traffic spikes, or queue wait time. Do not substitute "80 events/s" for "80 listener tasks/s" when a single event triggers multiple listeners.

Benchmark under realistic load and leave suitable headroom; if a downstream service only permits 10 concurrent connections, spawning 200 listener threads competing for those 10 connections brings no benefit.

### 7.3. Queues Are Not Infinite Buffers

If a pool has 8 workers and each task holds a worker for 100 ms on average, ideal throughput is roughly 80 tasks/s without other contention. If the queue holds 160 tasks, draining the backlog alone takes about **2 seconds** even under those ideal conditions. An "events processed within 200 ms" requirement is incompatible with an overly deep queue.

A queue large enough to absorb brief bursts is useful, whereas an oversized queue turns an easily detectable overload incident into silent, prolonged latency. Size queues based on **allowed wait-time budgets** and burst load testing, not simply average request rate.

### 7.4. A Verifiable Starting Baseline

There is no single fixed "best configuration." A straightforward process:

1. Measure **listener tasks/s** during normal load and peak bursts.
2. Measure p50/p95/p99 latency per listener, error rate, and downstream utilization.
3. Set `maxPoolSize` from actual resource limits; set `corePoolSize` for normal load.
4. Set a small queue sufficient to absorb bounded bursts without breaching the latency budget.
5. Choose an explicit full-capacity policy; write tests that reproduce overload.
6. Observe `activeCount`, `poolSize`, `queueSize`, rejected/fallback task counts, queue wait time, and task age.
7. Tune after real load testing; never simply inflate pool/queue sizes to hide overload signals.

## 8. Effects of @Async and @TransactionalEventListener

### 8.1. Multicaster Executor vs. @Async

There are two common ways for listeners to run asynchronously:

**Approach A: Set an executor on the multicaster.** Listeners supporting async dispatch through that executor:

```java
multicaster.setTaskExecutor(applicationEventExecutor);
```

**Approach B: Use @Async on the listener and specify an executor.**

```java
@Async("applicationEventExecutor")
@EventListener
public void onOrderSubmitted(OrderSubmitted event) {
    // Runs asynchronously via the @Async proxy.
}
```

Snippet B assumes `@EnableAsync`, the matching executor bean, and `OrderSubmitted` exist in the application.

Approach B lets you choose an executor per listener; Approach A typically serves multiple listeners through one multicaster executor. Avoid blindly enabling **both mechanisms** without understanding the call path: multicaster dispatch plus `@Async` proxying can create two scheduling layers, making capacity planning, context propagation, and error observation harder.

Errors occurring inside an `@Async void` body normally belong to the async proxy's exception path; do not expect an `ErrorHandler` attached to the multicaster to always see them.

### 8.2. Transactional Listeners Do Not Automatically Move to the Pool

`@TransactionalEventListener` binds execution to transaction phases like `AFTER_COMMIT`. In modern Spring, transactional listener adapters do not support moving directly onto the multicaster's executor like regular listeners, because they must bind callbacks to the transaction context on the event-publishing thread.

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderSubmitted event) {
    // Callback executes according to the transaction phase.
}
```

This is an illustrative snippet inside a Spring bean. Calling `setTaskExecutor(...)` does not automatically turn every `AFTER_COMMIT` callback into a task on the bounded pool. If heavy work is needed after commit, design an explicitly managed enqueue/dispatch step, along with durable persistence if tasks cannot be lost.

### 8.3. Thread Context Does Not Propagate Automatically

Async tasks do not automatically retain:

- An active transaction on the publisher thread.
- MDC/logging context and trace/span context.
- `SecurityContext` or request-scoped data using `ThreadLocal`.
- Ordering assumptions across multiple listeners.

When correlation IDs are needed, prefer including IDs in immutable payloads. You can use `TaskDecorator` or Micrometer Context Propagation for supported contexts, but never assume you can safely copy an active transaction across to a worker thread.

## 9. Where Does Backpressure Actually Matter?

**A bounded executor only bounds pool resources**, not necessarily the event emission rate. If producers keep emitting 5,000 events/s while listeners process 100 tasks/s, overload policies must take effect somewhere.

Option layers:

| Layer | What It Controls | Limitations |
| --- | --- | --- |
| Admission control before `publishEvent` | Number of requests permitted to publish; fails or defers before publication | Must design fairness, timeouts, quota release, and caller feedback |
| Bounded executor | Threads, queue, in-process wait time | Not durable; rejection handling via multicaster may vary |
| Rate limiting at the source | Rate of events entering the system | Hard to coordinate across all publishers when multiple threads/instances exist |
| Durable message broker/queue | Buffering, independent distribution, policy-based retries | Adds operational complexity; requires idempotency and duplicate handling |
| Transactional outbox | Ties outbound events to source data commits | Requires a relay process, monitoring, and consumer idempotency |

For example, an analytics-only event may tolerate dropping some updates if metrics can be recomputed. An event triggering refunds or invoice creation requires stricter consistency; relying solely on an in-RAM queue is inadequate.

**Choose policies by data criticality.** Do not force `DiscardPolicy` or `CallerRunsPolicy` onto every listener simply because one option is convenient to configure.

## 10. Monitoring and Operating a Bounded Executor

Minimum metrics to monitor include:

- **Pool size / active threads:** `ThreadPoolTaskExecutor.getPoolSize()` and `getActiveCount()` to see if the pool is saturated.
- **Queue occupancy:** `getQueueSize()` compared against `getQueueCapacity()` to detect growing backlogs.
- **Task execution latency:** actual listener runtime (p50/p95/p99).
- **Queue wait latency:** time from task submission until the worker starts executing.
- **Rejection / caller-runs / fallback:** how often the executor runs out of capacity, who runs the work, and publisher impact.
- **Error rate:** listener exceptions, downstream timeouts, retry counts, and final outcomes.
- **Task age / backlog drain time:** age of the oldest queued task; avoid looking solely at `queueSize` since even a small queue can hold very slow tasks.
- **Shutdown behavior:** whether queued tasks finish or stop when the process shuts down.

Declaring `ThreadPoolTaskExecutor` as a bean allows Spring/Micrometer instrumentation to detect it, though actual metric exposure depends on your observability stack and application configuration. Instrument errors, rejections, and queue wait times explicitly where needed; looking at average CPU alone misses tail latency.

For shutdown, define the policy: whether to wait for queued tasks, maximum wait duration, and whether new tasks may be accepted after shutdown signals. `ThreadPoolTaskExecutor` offers lifecycle options such as `setWaitForTasksToCompleteOnShutdown(...)` and `setAwaitTerminationSeconds(...)`; test each setting under load. Shutdown configuration does not replace durable storage if the process is killed abruptly.

## 11. Overload Testing and Limits to Verify

| Scenario | What to Verify |
| --- | --- |
| Below threshold | Listeners run on worker threads, complete properly, no sustained backlog |
| At queue threshold | Pool uses queue before scaling workers up to `maxPoolSize` per implementation rules |
| Both pool and queue full | Actual executor rejection policy **and** how the multicaster reacts |
| Multiple listeners per event | Task count and queue growth; do not miscount one event = one task |
| Very slow listener | Tail latency, queued task age, downstream connection pools |
| Listener throws errors | Errors are observed, caller impact is understood, other tasks continue |
| `@Async` proxy | Correct executor and exception handling path |
| `@TransactionalEventListener` | Correct transaction phase; do not assume multicaster executor changes thread |
| Shutdown with backlog | Work finishes, cancels, or falls back as designed |
| Two event types contending for resources | Low-priority events do not starve critical events' pool |
| Concurrent producers | Races when queue fills; real throughput and backpressure behavior |
| System restart | Whether in-memory events/tasks are lost; whether durable storage is needed |

**Do not test overload by running a few ultra-fast events.** Hold workers busy in a controlled manner (like `CountDownLatch` in the example), fill the queue, and observe exact outcomes. Do not rely solely on `Thread.sleep(...)` and treat timing results as deterministic.

## 12. Common Configuration Mistakes

1. **Setting `maxPoolSize` while leaving the queue nearly unbounded:** the pool rarely scales beyond core, and backlog silently grows.
2. **Setting `queueCapacity = 0` with an overly high `maxPoolSize`:** can cause thread explosions and exhaust downstream resources.
3. **Setting a queue of tens of thousands of tasks to "avoid errors":** latency becomes unpredictable, RAM fills up, and shutdown drags on.
4. **Assuming `publishEvent` returning means listeners finished:** async only means the task was scheduled or the call passed through.
5. **Assuming `AbortPolicy` guarantees the publisher receives an error:** the multicaster may intercept rejections; test your exact version and call path.
6. **Using `CallerRunsPolicy` inside long transactions:** listeners may unexpectedly run on the caller, holding locks/connections longer.
7. **Running business-critical listeners on an in-memory queue:** process crashes can lose unexecuted tasks.
8. **Sharing one pool across all event types:** slow listeners can stall critical events.
9. **Stacking multicaster executor and `@Async` arbitrarily:** adds queuing layers and obscures where delays and context loss occur.
10. **Assuming every listener supports async:** transactional listeners follow special lifecycle rules.
11. **Not recording rejected tasks:** HTTP metrics stay green while background work silently fails to complete.
12. **Ignoring listener count per event:** capacity sized in events/s instead of tasks/s leads to under-provisioning.
13. **Missing I/O timeouts in listeners:** a single worker can hang indefinitely, filling the queue.
14. **Not testing shutdown:** late-arriving events may behave differently than during steady state.

## 13. Pre-Deployment Selection Checklist

- Can this event be lost if the process fails, or must it be persisted durably?
- How many matching listeners exist per event? What is the **listener tasks/s** rate?
- Is each listener mainly CPU-bound or waiting on I/O? How many concurrent connections can downstream handle?
- What is the maximum acceptable processing delay? Does the queue absorb short bursts without violating the SLA?
- Do `corePoolSize`, `maxPoolSize`, and `queueCapacity` all have realistic bounds?
- When the executor is full, does the publisher wait, fail, run the listener inline, or hand off to a durable queue? Was this tested on the exact Spring version?
- Is the multicaster executor clearly distinguished from `@Async`?
- Are any transaction callbacks excluded from moving to the pool?
- Are metrics in place for queue wait, active threads, rejections, and task age?
- Have peak load, shutdown, and restarts been tested?

**Guiding principle:** Configuring a bounded executor is a mandatory step to control workers and backlogs in asynchronous event processing. Yet pool bounds alone do not create a complete backpressure protocol or delivery guarantee. Choose sizes based on execution time, latency budgets, downstream capacity, and especially verified **full-capacity behavior**.

## References

- [Spring Framework — SimpleApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — ApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/ApplicationEventMulticaster.html)
- [Spring Framework Reference — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework Reference — Observability Support](https://springframework.org/spring-framework/reference/6.2/integration/observability.html)