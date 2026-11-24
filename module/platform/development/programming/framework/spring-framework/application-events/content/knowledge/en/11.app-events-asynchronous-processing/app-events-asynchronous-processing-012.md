# Monitoring Queues and Task Rejection in Asynchronous Spring Application Events

## 1. Why Monitor the Queue?

When an `@EventListener` uses `@Async`, the event-handling method is submitted to a `TaskExecutor`. Returning quickly from `publishEvent(...)` **does not mean** the event has been processed: the task may be waiting in the queue, currently running, rejected at submission time, or failing after acceptance.

With `ThreadPoolTaskExecutor`, processing capacity depends on thread count, task duration, queue limit, and incoming event rate. When arrival rate stays higher than processing rate, the queue grows and latency rises; once configured thresholds are reached, the executor must **reject tasks** or apply an alternative policy.

A system needs to answer:

- How many listener tasks are currently running and queued?
- How long must an event wait before processing begins?
- How many tasks were rejected, failed, or lost?
- Under overload, should the event publisher retry, shed load, return an error, or use a durable queue?

**Important limitation:** Spring Application Events are an in-application notification mechanism; `ThreadPoolTaskExecutor` uses an in-memory queue, not a durable message broker. Stopping/crashing the application can lose unfinished tasks. Never equate "published" with "processed successfully."

## 2. Flow from Publisher to Executor

With `@EventListener` paired with `@Async("eventExecutor")`, the general flow is:

```text
publisher.publishEvent(event)
        |
        v
Spring ApplicationEventMulticaster
  finds matching listeners by event type
        |
        v
@Async proxy submits task to eventExecutor
        |
        +--> idle/eligible worker available --> run listener
        |
        +--> cannot run yet --> enqueue in bounded queue
        |
        +--> queue full, cannot add more workers
                                    |
                                    v
                              rejection policy
                          (throw / caller runs / discard)
```

By default, Spring's multicaster invokes listeners synchronously. In this model, `@Async` is what offloads **listener method execution** to the named executor. If `SimpleApplicationEventMulticaster.setTaskExecutor(...)` is configured for multicaster-level asynchronicity, the submission point and scope of impact differ; monitor whichever executor the application actually uses. Do not configure both mechanisms mechanically.

### ThreadPoolExecutor Task Acceptance Rules

With `corePoolSize`, `maxPoolSize`, and `queueCapacity`:

1. While active workers are below `corePoolSize`, the executor can create additional workers to take tasks.
2. Once core workers are populated, subsequent tasks are placed into the queue if space remains.
3. Only when the queue is full does the executor attempt to create more workers up to `maxPoolSize`.
4. When both the queue and worker limits are saturated, the task is rejected according to `RejectedExecutionHandler`.

Therefore, setting `maxPoolSize=32` with an enormous queue can keep the application running near core capacity for a long time; queued tasks pile up before the pool grows. Defaulting to practically unbounded queues under operational load easily causes backlogs and memory pressure. Bounded queues make clear when overload must be handled.

For example, with `corePoolSize=1`, `maxPoolSize=1`, and `queueCapacity=1`: task 1 is running, task 2 sits in the queue, and task 3 is rejected if task 1 has not yet finished.

## 3. Which Metrics Should Be Measured?

| Metric | Source / How to Obtain | Warning Signs |
| --- | --- | --- |
| Queued tasks (queue depth) | `executor.getQueueSize()` or `ThreadPoolExecutor` queue | Sustained growth or staying near capacity |
| Busy workers | `executor.getActiveCount()` | Pinned at maximum for extended periods |
| Current pool size | `executor.getPoolSize()` | Whether the pool scales as expected |
| Remaining queue capacity | `executor.getThreadPoolExecutor().getQueue().remainingCapacity()` | Near 0 repeatedly |
| Completed task count | `getCompletedTaskCount()` on native pool | Completion rate lower than arrival rate |
| Rejected task count | Custom counter in rejection handler or submission catch site | Any increase when critical events must not be lost |
| Wait / processing duration | Timestamps at publish, listener start, and finish | p95/p99 exceeding service targets |
| Processing failures | Counters and logs inside async listener/handler | Tasks accepted yet failing business completion |

Pool metrics are **approximate point-in-time snapshots**, changing continuously between reads. `getCompletedTaskCount()` is not an exact point-in-time audit figure and **does not automatically track rejections**; reliable rejection tracking requires counting explicitly. Distinguish at least three outcomes: **accepted**, **rejected**, and **processed successfully**.

When setting alerts, evaluate consecutive samples rather than alerting on a single brief queue spike. A system with an empty queue yet constantly failing listeners is still broken; conversely, short queues can be normal for batch bursts. Combine queue depth, latency, rejection rate, and CPU/DB utilization.

## 4. Complete Example: Intentionally Filling the Queue and Catching Rejections

The Java 17+ example below runs in a **Spring Boot 3.x** project with `spring-boot-starter`. The program intentionally holds event 1 in the worker, places event 2 in the queue, and sends event 3 to trigger a rejection. `CountDownLatch` keeps the scenario deterministic without relying on `Thread.sleep(...)`.

Create `src/main/java/example/events/EventQueueDemo.java`:

```java
package example.events;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.context.event.EventListener;

@SpringBootApplication
@EnableAsync
public class EventQueueDemo {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(EventQueueDemo.class, args)) {
            // CommandLineRunner finishes before run(...) returns.
        }
    }

    public record JobRequested(int id) {
    }

    public static class DemoGate {
        final CountDownLatch firstStarted = new CountDownLatch(1);
        final CountDownLatch releaseFirst = new CountDownLatch(1);
        final CountDownLatch processed = new CountDownLatch(2);
        final AtomicInteger rejected = new AtomicInteger();
    }

    public static class JobListener {
        private final DemoGate gate;

        public JobListener(DemoGate gate) {
            this.gate = gate;
        }

        @Async("eventExecutor")
        @EventListener
        public void on(JobRequested event) {
            if (event.id() == 1) {
                gate.firstStarted.countDown();

                try {
                    gate.releaseFirst.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }

            System.out.println("PROCESSED job=" + event.id());
            gate.processed.countDown();
        }
    }

    @Bean
    DemoGate demoGate() {
        return new DemoGate();
    }

    @Bean("eventExecutor")
    ThreadPoolTaskExecutor eventExecutor(DemoGate gate) {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(1);
        executor.setThreadNamePrefix("event-worker-");

        // Count rejections and preserve error-throwing behavior.
        executor.setRejectedExecutionHandler((task, pool) -> {
            gate.rejected.incrementAndGet();
            throw new RejectedExecutionException("Event executor is full");
        });

        return executor; // Spring initializes and manages the bean lifecycle.
    }

    @Bean
    JobListener jobListener(DemoGate gate) {
        return new JobListener(gate);
    }

    @Bean
    CommandLineRunner scenario(
            ApplicationEventPublisher publisher,
            @Qualifier("eventExecutor") ThreadPoolTaskExecutor executor,
            DemoGate gate) {

        return args -> {
            try {
                publisher.publishEvent(new JobRequested(1));

                if (!gate.firstStarted.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Worker 1 did not start");
                }

                publisher.publishEvent(new JobRequested(2));

                System.out.printf(
                        "SATURATED active=%d queued=%d%n",
                        executor.getActiveCount(),
                        executor.getQueueSize());

                try {
                    publisher.publishEvent(new JobRequested(3));
                    throw new IllegalStateException(
                            "Expected job 3 to be rejected");
                } catch (TaskRejectedException ex) {
                    System.out.println("REJECTED job=3");
                }
            } finally {
                // Release worker even if an error occurred during publish.
                gate.releaseFirst.countDown();
            }

            if (!gate.processed.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Jobs 1 and 2 did not finish");
            }

            System.out.println("REJECTIONS=" + gate.rejected.get());
        };
    }
}
```

Run in a project configured with the Gradle wrapper and Spring Boot plugin:

```bash
./gradlew bootRun
```

On Windows, use `gradlew.bat bootRun`. Aside from Spring Boot startup/shutdown logs, the lines printed by the program in order are:

```text
SATURATED active=1 queued=1
REJECTED job=3
PROCESSED job=1
PROCESSED job=2
REJECTIONS=1
```

**Step-by-step explanation:**

1. Job 1 is accepted by the executor and held at `releaseFirst.await()`. `firstStarted` notifies the publishing thread that the worker has begun.
2. Job 2 is submitted while the single worker is busy, occupying the single queue slot.
3. Before releasing job 1, the publishing thread observes `active=1` and `queued=1`; upon submitting job 3, the pool has no remaining capacity.
4. The rejection handler increments `rejected` and throws `RejectedExecutionException`; `ThreadPoolTaskExecutor` translates the submission failure to `TaskRejectedException` for the caller, so the `catch` block around `publishEvent(...)` captures it.
5. The `finally` block releases job 1, after which the single worker processes job 1 and then job 2. Job 3 **is not processed**.
6. The `processed` latch is solely for synchronizing the example and confirming 2 jobs finished; production applications should not block publishers waiting on each event like this.

This is an overload simulation test; the **1-worker, queue-1 configuration** is purely to demonstrate the mechanism, not a recommended production pool size.

## 5. Rejection Policies: Each Choice Has Different Consequences

`ThreadPoolTaskExecutor` allows configuring Java's `RejectedExecutionHandler`. The table below describes common policies when the executor is running and saturated:

| Policy | Behavior | Impact on Event Listeners |
| --- | --- | --- |
| `AbortPolicy` (default) | Throws a rejection error | Publisher can detect task submission failure; requires handling logic |
| `CallerRunsPolicy` | Runs the task on the submitting thread | Creates backpressure, but `publishEvent` can slow down and task runs on publisher thread |
| `DiscardPolicy` | Silently drops the new task | Risk of silent event loss |
| `DiscardOldestPolicy` | Drops the oldest queued task and retries submission | Can lose older events and break ordering expectations |

Alternative handler configuration snippet (this is an **illustrative configuration snippet**, not a standalone file):

```java
executor.setRejectedExecutionHandler(
        new java.util.concurrent.ThreadPoolExecutor.CallerRunsPolicy());
```

With `CallerRunsPolicy`, a listener task may execute directly on the thread calling `publishEvent` when the pool is full, increasing request latency and invalidating the assumption that "listeners always run on a separate thread." Once the pool has shut down, this policy may not run the task. Do not use it merely to avoid seeing exceptions.

With `DiscardPolicy` and `DiscardOldestPolicy`, tasks can be dropped without the publishing method knowing. Consider them only when **task loss is explicitly acceptable** (such as recomputable statistics updates); for transactional emails, payments, or mandatory work, durable persistence and retries are required.

With `AbortPolicy`, catching `TaskRejectedException` on the publishing thread lets you return an overload error, increment a counter, or intentionally route the task to another processing path. Do not lump every exception under "rejected": errors thrown **after the listener starts running** mean something different and must be tracked separately.

## 6. Feeding Metrics into Monitoring Systems

### Direct Inspection via the Executor

You can read figures directly from the `ThreadPoolTaskExecutor` bean:

```java
ThreadPoolTaskExecutor executor = /* injected bean */;
int active = executor.getActiveCount();
int queued = executor.getQueueSize();
int poolSize = executor.getPoolSize();
int remaining = executor.getThreadPoolExecutor()
        .getQueue().remainingCapacity();
long completed = executor.getThreadPoolExecutor()
        .getCompletedTaskCount();
```

The snippet above is **code meant for an administration/monitoring service**, not a standalone program. Do not use queue size at one instant to prove which tasks have completed. Combine time-series statistics with request/event IDs in logs.

### Spring Boot Actuator and Micrometer

When an application includes `spring-boot-starter-actuator`, Spring Boot can automatically register metrics for `ThreadPoolTaskExecutor` beans backed by a native executor. Exact metric names and tags depend on version/registry; inspect `/actuator/metrics` if the app exposes HTTP actuator endpoints. Metrics can be exported to Prometheus/OTLP or other monitoring backends via an appropriate registry.

**Dedicated rejection metrics still need explicit creation:** the `gate.rejected` counter in the example illustrates the counting principle. In production systems, register this counter in Micrometer under an application metric name (e.g., `application.events.rejected`), tagged with executor/event type using bounded-cardinality tags. Never attach `orderId` or UUID as a tag, as that creates excessive time-series cardinality.

A useful dashboard includes: queue depth, active/pool size, rejection rate, event processing latency, event wait latency, and processing error rate. Base alerts on sustained duration, baseline load, and operational goals; thresholds cannot be derived from `queueCapacity` alone.

### Measuring Wait Time

Attach the event publish timestamp to telemetry data or observation records (avoid trusting clocks across different machines), and record when the listener **starts** and **finishes**. Then:

- *Wait latency* ≈ `listenerStart - eventPublishTime`.
- *Processing latency* ≈ `listenerEnd - listenerStart`.
- *End-to-end latency* ≈ `listenerEnd - eventPublishTime`.

This represents end-to-end duration including other overhead; do not treat it solely as time spent sitting in the queue. Track p95/p99 rather than relying only on averages.

## 7. Responding When the Queue Starts Filling Up

**Step 1 — Inspect processing bottlenecks:** Determine whether tasks are slow due to CPU, locks, DB connection pools, HTTP timeouts, or listener logic itself. Adding threads while the DB is already saturated can worsen the problem.

**Step 2 — Set controlled bounds:** Configure `corePoolSize`, `maxPoolSize`, and `queueCapacity` from measured load. Bounded queues are usually clearer than unbounded ones. Test both burst and sustained load, measuring latency and rejection rates.

**Step 3 — Decide publisher responsibility on rejection:** For non-critical events, log and intentionally drop per policy. For mandatory work, use bounded retries with backoff only if safe; never retry in a tight loop while the pool is already full. Consider returning an overload signal so upstream slows down.

**Step 4 — If events must not be lost, change storage mechanism:** Persist a job/outbox record inside the business transaction and let a separate worker read and send messages through a durable broker/queue. Design idempotency keys, retries, dead-letter handling, and duplicate-write guards. Do not rely solely on the event executor's in-memory queue.

**Step 5 — Observe after changes:** Re-measure completion throughput, memory, CPU, wait times, and errors. Increasing `queueCapacity` only increases how much work can wait; it **does not increase processing speed** and can worsen tail latency.

## 8. Common Confusions with @Async and Transactions

- **Task submission errors differ from task execution errors:** Executor rejections are usually surfaced on the task-submitting thread and can be caught by the publisher as in the example. A `void` `@Async` listener throwing an exception **after execution starts** does not propagate that exception back to `publishEvent`; log/emit metrics and configure `AsyncUncaughtExceptionHandler` or catch errors intentionally inside the listener.
- **No automatic transaction propagation across async threads:** A listener running on another thread does not automatically inherit the publisher's transaction and `ThreadLocal`. If post-commit reactions are required, use a suitable event/transaction design—such as evaluating `@TransactionalEventListener` and its execution contract.
- **No guaranteed completion order:** Multiple workers can finish events in a different order than published. `@Order` does not create a global FIFO queue across async tasks.
- **Do not use queue depth as proof of success:** A queue returning to 0 only means no tasks are waiting; tasks may still be running or may have failed. Track accepted/rejected/succeeded/failed counts at each stage.
- **Do not duplicate `@Async` and multicaster async without purpose:** Both can dispatch work via an executor; if combined, know exactly which tasks run on which executor, how errors propagate, and how queues are measured.
- **Do not expect shutdown to drain everything in all cases:** Shutdown can stop/interrupt tasks depending on settings. Graceful shutdown can be configured, yet abrupt process death or machine failure still renders an in-memory queue non-durable.

## 9. Test Scenarios and Production Checklist

| Scenario | What to Verify |
| --- | --- |
| Load below processing capacity | Small queue, tasks complete, `rejected = 0` |
| Worker busy and queue has room | New tasks accepted, queue grows within bounds |
| Worker busy and queue full | Rejection policy invoked; rejection counter increments or backpressure works as designed |
| Listener throws in async thread | Failure recorded; publisher is not misled into treating it as success |
| Slow downstream system | Wait time rises; appropriate timeouts/backpressure/retries apply |
| Shutdown with pending tasks | Shutdown follows configured policy; critical work has recovery mechanisms |
| Scaling worker count | Verify downstream DB/APIs handle load and latency genuinely improves |

Before deploying, confirm: bounded queue capacity; dedicated executor name for events; dashboards for queue/active/rejections/errors/latency; transparent rejection handling; retries with backoff and idempotency where needed; overload and shutdown tests; and durable persistence whenever events must not be lost.

**Remember:** The queue reflects **pending work**, while rejection reflects **work the executor could not accept**. Monitor both and define drop/wait/retry policies per event type. Overload cannot be solved merely by enlarging the queue.

## References

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): how pools use core/max/queue sizes and rejection policies.
- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): default synchronous events, asynchronous listeners, and `@Async` limitations.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Actuator/Micrometer and executor metrics.