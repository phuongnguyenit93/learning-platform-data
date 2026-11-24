# Notification Bursts and Listener Pressure in Spring Framework JMX

## 1. Real-World Problem and Objectives

JMX Notification is a mechanism for emitting management signals when an MBean's state changes. For example, an MBean in a Spring application can emit notifications when a connection fails, a queue crosses a threshold, a job completes, or a cache is reset. At low load, notification listeners normally operate lightly. However, when errors occur repeatedly or the system produces thousands of events per second, **notification bursts** can become a source of slowdown for the very application being monitored.

Typical symptoms:

- The method emitting notifications becomes slow because listeners process synchronously.
- Pending tasks in the executor grow continuously.
- Callbacks process slower than the emission rate, leading to backlogs and growing memory usage.
- Overload errors cause notifications to be rejected, dropped, or processed late.
- When remote JMX disconnects, the client cannot assume every notification will be redelivered.
- A critical notification gets buried among thousands of repeated alerts.
- Metrics, logs, and alerts all add extra load precisely when the system is having an incident.

This lesson guides you through identifying and controlling notification pressure with a performance mindset: calculating rates, bounding resources, classifying events, reducing noise, designing non-blocking listeners, and verifying through tests.

After this lesson, you will be able to distinguish synchronous vs. asynchronous dispatch, measure callback latency, estimate backlogs, configure bounded executors, choose overload policies, and design state recovery after missed notifications.

## 2. Notification Pipeline Model

```text
                   Application / MBean
                     event producer
                           |
                   create Notification
                           |
                    sendNotification()
                           |
                +----------+----------+
                |                     |
         Synchronous path       Asynchronous path
                |                     |
          listener callback      Executor / task queue
                |                     |
          process directly        listener callback
                |                     |
                +----------+----------+
                           |
                    logs / metrics /
                    dashboard / actions
```

With Spring JMX, the emitter can use `NotificationPublisherAware` and `NotificationPublisher`; listeners can be registered via `NotificationListenerBean` or directly through the JMX API. Spring helps with wiring, but **using Spring beans does not automatically create backpressure or limit callback concurrency**.

A stable notification architecture must explicitly decide where queues exist, who owns the executor, what the backlog limit is, which events may be dropped, and how to handle limit overflows.

## 3. Notifications Are Not a Durable Message Queue

A common mistake is treating `NotificationBroadcasterSupport` or remote JMX notifications like an event streaming system with guaranteed storage.

JMX notifications have characteristics to keep in mind:

1. Designed to transmit management information, without persistence by default.
2. No durable subscriber offsets like a message broker.
3. Does not provide exactly-once processing for listeners.
4. No built-in durable retry when a listener/connector fails.
5. Does not guarantee remote clients receive all notifications after a disconnect.
6. Completion order depends on the dispatcher and executor.
7. Current state can be re-queried via MBean attributes after a client reconnects.

If notifications are a mandatory data source for updating balances, orders, or audits that must not be lost, use a messaging/event log mechanism that meets those requirements. JMX notifications should be treated as **observability signals**, while authoritative management state resides in MBean attributes, databases, or appropriate services.

## 4. Quantifying Pressure Using Emission and Processing Rates

Suppose a source emits `λ` notifications/second and a listener processes `μ` notifications/second.

With a single worker:

```text
λ = 500 notifications/s
μ = 200 notifications/s

Backlog grows approximately at:
  500 - 200 = 300 notifications/s
```

After 10 seconds of continuous overload, the queue can accumulate around 3,000 tasks (if unbounded, no drops, and rates remain constant).

With `c` equivalent workers each having throughput `μ`, total capacity is approximately `c × μ`; when `λ >= c × μ` for a prolonged period, the queue tends to grow. This is a rough model because real processing involves latency distributions, lock contention, GC, and different queue implementations.

| Symbol | Meaning |
|---|---|
| `λ` | Incoming notification rate |
| `μ` | Processing throughput per worker |
| `c` | Number of processing workers |
| `Q` | Number of queued tasks |
| `W` | Time a task spends waiting and processing |
| `L` | Average number of tasks in the system |

Under steady-state conditions, Little's Law `L = λ × W` helps relate concurrency, throughput, and latency. Do not apply the formula as a guarantee when the queue is continuously overloaded and the system is not in steady state.

### 4.1. Sizing Queue Capacity Purposefully

If a producer can burst to 800 notifications/s for 5 seconds while 4 workers process 600 notifications/s in total, the backlog grows by roughly `(800 - 600) × 5 = 1,000` notifications. A 100-entry queue will fill quickly; a 100,000-entry queue may mask failures for a long time while consuming significant RAM.

Queue capacity should be chosen based on:

- Acceptable burst size and burst duration.
- Average and maximum size of each task/payload.
- Time budget before a notification becomes stale.
- Ability to scale actual processing throughput up/down.
- Policy when the queue is full: drop, reject, coalesce, block, or offload to a durable system.

**Do not use an unbounded queue as the default overload-handling strategy.**

## 5. Synchronous Listeners: Bottleneck Directly on the Emitting Thread

JDK `NotificationBroadcasterSupport` can dispatch to listeners by default on the `sendNotification` call path if no executor is configured.

```java
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;
import javax.management.NotificationListener;
import java.util.concurrent.atomic.AtomicLong;

public class WorkerEmitter extends NotificationBroadcasterSupport {
    private final AtomicLong sequence = new AtomicLong();

    public void event(String type) {
        sendNotification(new Notification(
            type, this, sequence.incrementAndGet(),
            System.currentTimeMillis(), "worker event"));
    }
}
```

An intentionally slow listener:

```java
NotificationListener slowListener = (notification, handback) -> {
    try {
        Thread.sleep(100); // Lab simulation only.
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
    }
};
```

When the callback runs synchronously, a single notification can take at least around 100 ms for this listener. An emitter producing 100 events/s on a single thread will quickly be throttled by the listener, not counting any other listeners.

### 5.1. Frequently Overlooked Consequences

- A notification emitted from a JMX operation prolongs the `invoke` call.
- A notification emitted inside a `synchronized` block keeps the lock held longer.
- A listener calling back into the same MBean can create reentrancy or wait cycles.
- A listener making HTTP/database calls can slow down business threads.
- Higher notification frequency can increase log noise and GC pressure.

A synchronous callback is suitable when processing is very lightweight, such as incrementing a counter or recording a simple state. If it must perform I/O or heavy data processing, use a bounded queue.

## 6. Asynchronous Dispatch with Executor: Beneficial but Not Free

`NotificationBroadcasterSupport` has a constructor accepting an `Executor`. Example:

```java
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;
import java.util.concurrent.Executor;

public final class AsyncStatusEmitter
        extends NotificationBroadcasterSupport {

    public AsyncStatusEmitter(Executor executor) {
        super(executor);
    }

    public void changed(long sequence) {
        sendNotification(new Notification(
            "training.status.changed",
            this,
            sequence,
            System.currentTimeMillis()));
    }
}
```

When the executor accepts the task, the emitting thread can continue without waiting for the callback to finish. However, if the emission rate exceeds processing throughput, the queue accumulates and the system still overloads.

### 6.1. Multi-Threaded Executors Do Not Guarantee Completion Order

```text
Notification #1 -> worker A (500 ms)
Notification #2 -> worker B (10 ms)

Result:
  #2 finishes before #1
```

If listeners only update independent counters, this may be acceptable. If a state machine depends on sequence order, design per-resource ordering or check versions before applying events.

### 6.2. Single Sequential Thread or Multi-Thread Pool?

| Approach | Advantage | Limitation |
|---|---|---|
| Synchronous dispatch | Simple, minimal queueing | Blocks emitting thread |
| Single-thread executor | Preserves submission order easily | Limited throughput |
| Fixed pool | Parallel processing | Requires thread safety, ordering |
| Bounded pool/queue | Bounds memory/concurrency | Requires overflow policy |
| External durable queue | Supports persistence/retry | More complex system |

Do not scale threads unboundedly to chase spikes. If callbacks mainly wait on network I/O, worker count may exceed CPU cores, but connection limits and deadlines are still required.

## 7. ThreadPoolExecutor with a Bounded Queue

Example of a Spring `@Bean` owning the executor:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class NotificationExecutorConfig {

    @Bean(destroyMethod = "shutdown")
    public ThreadPoolExecutor jmxNotificationExecutor() {
        return new ThreadPoolExecutor(
            2,
            2,
            0,
            TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<>(256),
            runnable -> {
                Thread t = new Thread(runnable, "jmx-notification");
                t.setDaemon(false);
                return t;
            },
            new ThreadPoolExecutor.AbortPolicy());
    }
}
```

With 2 workers and a queue of at most 256 tasks, the executor will not hold unbounded notification tasks. When the queue is full and workers are busy, `AbortPolicy` throws `RejectedExecutionException`.

You must **clearly determine where rejections are handled**. A broadcaster sending notifications may call `executor.execute` during dispatch; how the exception is handled depends on the implementation and dispatch point. Do not assume all rejections are logged or automatically retried.

### 7.1. Policies When the Queue Is Full

- **Reject/alert:** refuse additional tasks and record a metric, suitable for droppable events.
- **Drop newest:** retain older backlog while dropping incoming events; can delay receiving fresh information.
- **Drop oldest:** prioritize newer updates, useful for state snapshots but loses older state transitions.
- **Coalesce:** merge multiple events for the same resource/info into a single signal.
- **CallerRunsPolicy:** the caller runs the task directly on saturation, creating backpressure, though it may block the notification-emitting path.
- **Persist to durable queue:** appropriate when events must not be lost; in that case consider a message broker instead of JMX notifications as the primary data channel.

Do not choose a policy based solely on throughput benchmarks; base it on **notification semantics**.

## 8. Classifying Notifications by Importance

Not every notification needs to be handled the same way:

| Notification Type | Operational Value | Recommendation |
|---|---|---|
| CPU/queue continuously over threshold | Usually queryable state | Debounce, coalesce |
| Worker transitions RUNNING → PAUSED | Notable transition | Keep sequence/last state |
| Single task completed | Can be very high volume | Aggregate into counters |
| First critical failure | Very important | Alert + separate audit |
| Repeated error with same cause | Low value after first sample | Rate-limit, group by fingerprint |
| Overly frequent heartbeat | Periodic signal | Sample or drop if attributes suffice |
| Business data that must not be lost | Business-critical | Durable messaging, not JMX-only |

A common mistake is emitting a notification for **every request** or **every message**. JMX is not a high-volume event stream. It is usually better to expose `RequestCount`, `ErrorRate`, and `QueueDepth` as MBean attributes/metrics, and emit notifications only on noteworthy state changes.

## 9. Debounce, Throttle, Sampling, and Coalescing

### 9.1. Debounce

Emit a notification only after a condition persists long enough, such as queue depth exceeding 1,000 for 15 seconds. Avoid firing repeatedly when a metric oscillates around a threshold.

### 9.2. Throttle or Rate-Limit

Allow at most N notifications per interval, such as 1 notification per 10 seconds for the same resource and alert type.

### 9.3. Sampling

Sample only a fraction of high-frequency events. This is only suitable for lossy telemetry, never for critical state changes that must be completely recorded.

### 9.4. Coalescing

Multiple `queue.changed` notifications in a short interval can be merged into `queue.state.changed`; upon receiving it, the listener reads the latest `QueueDepth` value from the MBean.

```text
10,000 queue.change events
            |
            v
      Coalescing window
            |
            v
      1 signal "changed"
            |
            v
Listener queries QueueDepth attribute
```

This shifts from a "every change is a payload" model to a "notification signals a need to refresh state" model.

### 9.5. Be Careful with Intermediate Transitions

If an event represents a transition that cannot be skipped—such as changing state from `RUNNING` to `FAILED` and then `RECOVERING`—merging everything into the current state can lose history. Separate **state snapshots** from **audit events**; use an appropriate event log for the latter.

## 10. Example: Reducing Duplicate Notifications Over Time

An emitter can throttle a "queue too deep" signal:

```java
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

public final class ThrottledQueueEmitter
        extends NotificationBroadcasterSupport {

    private final AtomicLong sequence = new AtomicLong();
    private final AtomicLong nextAllowed = new AtomicLong();
    private final long intervalNanos = TimeUnit.SECONDS.toNanos(10);

    public void reportHighQueue(int depth) {
        long now = System.nanoTime();

        while (true) {
            long allowed = nextAllowed.get();
            if (now - allowed < 0) {
                return;
            }
            if (nextAllowed.compareAndSet(
                    allowed, now + intervalNanos)) {
                break;
            }
        }

        Notification n = new Notification(
            "training.queue.high",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Queue depth above threshold");
        n.setUserData(depth);
        sendNotification(n);
    }
}
```

The example illustrates a throttling principle using a monotonic clock. In a real system, check edge cases around initialization, clock wrap, and "leading/trailing event" policies, and ensure no sensitive data is placed in the payload. With multiple resource IDs, maintain separate throttle state per resource instead of a single shared variable.

Note: throttling reduces **the number of notifications emitted**, rather than just making the listener process faster.

## 11. Lightweight Listeners and Decoupled Heavy Processing

Suppose a listener needs to send alerts to another service. If it calls HTTP directly inside a synchronous callback, whenever the alert service slows down, the application suffers backpressure.

Better model:

```text
JMX callback
   |
   +--> validate type
   +--> snapshot minimal fields
   +--> enqueue bounded task
   +--> return quickly
               |
               v
          Worker executor
               |
               +--> outbound API with timeout
               +--> retry if safe
               +--> metrics/logs
```

Example:

```java
import javax.management.Notification;
import javax.management.NotificationListener;
import java.util.concurrent.Executor;

public final class AlertListener implements NotificationListener {
    private final Executor executor;
    private final AlertSender sender;

    public AlertListener(Executor executor, AlertSender sender) {
        this.executor = executor;
        this.sender = sender;
    }

    @Override
    public void handleNotification(Notification notification,
                                   Object handback) {
        String type = notification.getType();
        long sequence = notification.getSequenceNumber();
        String message = notification.getMessage();

        executor.execute(() ->
            sender.send(type, sequence, message));
    }

    public interface AlertSender {
        void send(String type, long sequence, String message);
    }
}
```

A production implementation must handle `RejectedExecutionException`, keep payloads safe, avoid infinite retries, define shutdown, and log worker errors. If the notification is optional telemetry, it can be dropped while incrementing a counter. If loss is unacceptable, use a persistent queue and an appropriate business mechanism.

## 12. Thread Safety and Memory Visibility

Notifications can be emitted from multiple threads, and listeners can also execute concurrently. Key points:

- Sequence counters should be atomic if there are multiple producers.
- Shared state needs `volatile`, locks, or appropriate concurrent structures.
- Payloads should not contain unsynchronized shared mutable objects.
- Listeners must not assume callbacks always run on the same thread.
- When using a multi-thread executor, callback #2 may finish before callback #1.
- If a listener calls back into the MBean synchronously, avoid lock inversion and deadlocks.

An anti-pattern:

```java
private final java.util.HashMap<String, Integer> counts =
    new java.util.HashMap<>();

public void handleNotification(Notification n, Object handback) {
    counts.merge(n.getType(), 1, Integer::sum);
}
```

If callbacks run concurrently, `HashMap` is not thread-safe. One alternative:

```java
private final java.util.concurrent.ConcurrentHashMap<
    String, java.util.concurrent.atomic.LongAdder> counts =
        new java.util.concurrent.ConcurrentHashMap<>();

public void handleNotification(Notification n, Object handback) {
    counts.computeIfAbsent(
        n.getType(),
        ignored -> new java.util.concurrent.atomic.LongAdder()
    ).increment();
}
```

For state more complex than counters, control multi-field atomicity or use immutable snapshots.

## 13. Listener Exceptions and Unobserved Failures

A callback can fail due to:

- Invalid payload.
- Resource already unregistered.
- Rejection from the executor.
- Database/network dependency failure.
- Race conditions from concurrent updates.
- Queue full or callback timeout.

For callbacks running on an executor, exceptions may appear only on the executor thread. If code does not record logs/metrics, the caller of `sendNotification` may remain unaware.

A pattern:

```java
@Override
public void handleNotification(Notification n, Object handback) {
    try {
        process(n);
    } catch (RuntimeException e) {
        failedNotifications.increment();
        logger.error("JMX listener failed type={}", n.getType(), e);
    }
}
```

`logger` and `failedNotifications` are illustrative dependencies. Depending on the error type and delivery requirements, logging alone may be insufficient; a dead-letter queue or separate durable pipeline may be needed. Do not log full `userData` when it might contain sensitive information.

## 14. Remote JMX Adds Another Queueing Layer and Network Errors

Remote notification listeners do not necessarily execute on the server's business threads. The connector has its own fetch/forward/dispatch mechanisms depending on the JMX implementation and protocol.

```text
Server JVM
  emitter
     |
     v
  MBeanServer
     |
  JMX connector server
     |
  network / fetch
     |
Client JVM
  JMX connector client
     |
  listener callback
```

Factors to consider:

1. Notification forwarding buffers/connectors are bounded.
2. Dropped connections can cause clients to miss notifications.
3. Slow clients can cause backlogs or lead to dropped events.
4. Reconnecting does not automatically replay all missed notifications.
5. The time a callback arrives at the client is not the time the notification was created.
6. Multiple listeners and multiple clients increase fan-out.

**Core solution:** notifications signal changes, while the client re-queries **current state** after reconnecting or when suspecting a gap. If full history is required, store events in a durable system.

## 15. Metrics to Monitor

You cannot control notification pressure without measuring it. Useful metrics:

| Metric | Meaning | When Spiking Abnormally |
|---|---|---|
| notifications_emitted_total | Number of notifications emitted | Producer is too noisy |
| notifications_received_total | Number of callbacks received | Fan-out or abnormal reception |
| notifications_dropped_total | Number of events dropped/rejected | Overload policy is triggering |
| listener_processing_seconds | Callback processing time | Slow callback or dependency |
| listener_queue_depth | Number of queued tasks | Throughput cannot keep up |
| listener_executor_active | Number of busy workers | Saturation |
| listener_errors_total | Exceptions in callbacks | Payload/logic/dependency error |
| reconnect_total | Remote connector reconnects | Unstable network |
| notification_lag_seconds | Time from event timestamp to processing | Events are too stale |
| notification_gap_total | Number of gaps detectable via sequence | Possible lost events |

Some metrics are only feasible if you instrument at the right layer. Do not assume JMX provides all these metric names automatically. They can be implemented with Micrometer, custom counters, or health monitoring depending on architecture.

### 15.1. Avoid High-Cardinality Metric Labels

Do not put `notificationId`, UUIDs, raw messages, or user IDs into labels. Use type, module, and outcome with bounded cardinality. A monitoring system experiencing unbounded series growth can itself become a source of overload.

### 15.2. End-to-End Latency

If a notification carries a timestamp, a listener can compute lag:

```java
long ageMs =
    System.currentTimeMillis() - notification.getTimeStamp();
```

Across remote JVMs, clock skew can make measurements negative or inaccurate. Use synchronized clocks and do not treat subtraction across two different clocks as exact latency. Measure callback duration within the same JVM using `System.nanoTime()`.

## 16. Spring NotificationPublisher and Producer Configuration

A Spring-managed bean can emit notifications via `NotificationPublisherAware`:

```java
import javax.management.Notification;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;

@ManagedResource(
    objectName = "training.spring:type=Queue,name=Orders")
public class QueueManagement implements NotificationPublisherAware {

    private NotificationPublisher publisher;
    private final AtomicLong sequence = new AtomicLong();

    @Override
    public void setNotificationPublisher(NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    @ManagedOperation
    public void signalHighQueue() {
        Notification notification = new Notification(
            "training.queue.high",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Orders queue above threshold");
        publisher.sendNotification(notification);
    }
}
```

This is an example of a bean sending a notification; production code should not create a new notification every time a request crosses a threshold without rate limiting. For notification metadata to appear in JMX, `@ManagedNotification` configuration or an appropriate metadata assembler may be needed depending on how the exporter uses Spring annotations.

Spring `NotificationListenerBean` helps register listeners, filters, and MBean mappings. However, registration does not replace application-level threading/queue design.

## 17. Reducing Unnecessary Fan-Out

One notification can reach multiple listeners, and each listener can spawn new tasks:

```text
1 emitter event
    |
    +-- log listener
    +-- metrics listener
    +-- alert listener
    +-- audit listener
    |
    v
4 callbacks / event
```

At 1,000 events/s, total callback rate can be 4,000/s before even counting remote clients. If each listener emits another notification, the system can create an event loop.

Improvements:

- Register only listeners that are actually needed.
- Use `NotificationFilter` by type.
- Limit repeated emissions for the same state.
- Use metrics aggregation instead of event-by-event processing.
- Do not emit new notifications from inside callbacks without loop-prevention guards.
- Monitor subscriber counts, latency, and queue depth of each critical listener.

A filter only drops events before the callback; it does not necessarily reduce the cost of **creating and dispatching the notification** at the producer if the broadcaster already had to process it. If event volume is too high, reducing at the source yields greater benefit.

## 18. Designing Overload Policies by Signal Type

A system can define policies per category:

```text
State change / queue depth:
    coalesce + query current attribute

Recoverable warning:
    throttle + aggregate count

Critical failure transition:
    emit immediately + durable audit elsewhere

Bulk per-item completion:
    counters/metrics instead of notifications

Remote client reconnect:
    resubscribe + resync state
```

Do not use the same queue and same drop policy for all event types. A critical notification about a stopped node may need a separate path so it is not congested by thousands of log-level changes or heartbeats.

### 18.1. What Does Reserved Capacity Mean?

When critical notifications need priority, you can separate executors/queues by severity or use a priority queue with clear policies. However, a priority queue does not automatically solve bounded memory or starvation issues; total capacity must still be bounded and delayed/dropped events measured.

## 19. Listener Lifecycle and Shutdown Under High Load

An executor holding 10,000 pending tasks when the Spring context closes can prolong shutdown or lose work if stopped abruptly.

Determine:

1. On shutdown, does the system stop emitting new notifications?
2. At what point are listener registrations removed?
3. Does the executor stop accepting tasks via `shutdown()` or `shutdownNow()`?
4. How long should it wait at most for tasks to finish?
5. Are remaining queued events dropped in a controlled way?
6. Do logs/metrics or status stores need flushing?
7. On restart, how will clients resync state?

A pattern:

```java
executor.shutdown();

if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
    java.util.List<Runnable> abandoned =
        executor.shutdownNow();
    System.err.println(
        "Discarded pending tasks: " + abandoned.size());
}
```

This is illustrative, not a zero-loss guarantee. `shutdownNow()` does not guarantee running tasks stop immediately. For critical processing, perform durable handoff before shutdown.

## 20. Testing Bursts and Listener Pressure

### 20.1. Test Scenarios

Set up a lab environment where a producer emits 10,000 notifications in a short burst. Compare three configurations:

1. Slow synchronous listener.
2. Unbounded async queue.
3. Bounded async queue with drop/rejection metrics.

Measure producer completion time, peak queue depth, memory usage, processed event count, dropped event count, and callback latency.

Do not measure only successful throughput; also record **impact on the source application**.

### 20.2. JUnit with a Controlled Executor

You can test queue/backpressure behavior with `ThreadPoolExecutor`:

```java
import org.junit.jupiter.api.Test;
import java.util.concurrent.*;
import static org.junit.jupiter.api.Assertions.*;

class ListenerBackpressureTest {

    @Test
    void boundedQueueRejectsWhenSaturated() throws Exception {
        CountDownLatch release = new CountDownLatch(1);
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
            1, 1, 0, TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<>(1),
            new ThreadPoolExecutor.AbortPolicy());

        try {
            executor.execute(() -> {
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            // One worker is running, one task enters the queue.
            executor.execute(() -> {});

            assertThrows(RejectedExecutionException.class,
                () -> executor.execute(() -> {}));
        } finally {
            release.countDown();
            executor.shutdownNow();
        }
    }
}
```

This test proves the executor's queue/rejection behavior, not by itself how the full broadcaster reports errors. To test JMX end-to-end, register the listener with the emitter and measure actual callback counts, timing, and error policy.

### 20.3. Testing Listener Cleanup

In a Spring integration test, create a context with broadcaster and listener, emit a batch of notifications, close the context, and verify that listener registrations/executor lifecycles do not retain references causing memory leaks. Do not use `Thread.sleep` as a success condition; use latches/counters or test fixture state with explicit deadlines.

## 21. Diagnosing Production Incidents

| Symptom | Possible Cause | Evidence to Collect |
|---|---|---|
| `sendNotification` is slow | Sync callback or CallerRunsPolicy | Thread dumps, callback duration |
| CPU spikes during alert storms | Callbacks, serialization, logs | Profiler, metrics, sampling |
| Heap grows continuously | Unbounded queue/retained payloads | Heap histogram, queue depth |
| Listeners receive notifications very late | Backlog or remote forwarding delay | Event timestamp and processing lag |
| Some events never arrive | Drop/reject, filter, disconnect | Emitted/received/dropped counters |
| Client sees events out of order | Multi-thread dispatch | Sequence vs. completion times |
| Alerts repeat endlessly | Producer lacks throttle or feedback loop | Event type trace/fingerprint |
| Restart loses notifications | Non-durable delivery and shutdown | Recovery/resync design |
| Silent listener failures | Exceptions in workers lack logging | Error counters/executor hooks |
| Alert flood hides critical signals | Shared queue and shared priority | Per-type rates, queue saturation |

Investigation order should start from **event emission rate**, then inspect dispatch mode, queues, processing latency, and remote clients. Do not increase thread counts before determining whether callbacks are CPU-bound, waiting on I/O, or hitting lock contention.

## 22. Operations Checklist

- [ ] Distinguish notifications needing history from state-signaling notifications.
- [ ] Reduce notifications at the producer using throttling/coalescing where appropriate.
- [ ] Do not emit notifications per request when counters suffice.
- [ ] Synchronous listeners must be short and avoid blocking network I/O.
- [ ] Asynchronous executors have a bounded queue and an explicit rejection policy.
- [ ] Callback concurrency is bounded.
- [ ] Metrics exist for emitted/received/dropped/lag/errors.
- [ ] Burst and saturation tests are in place.
- [ ] An ordering policy exists for events requiring sequence order.
- [ ] A resync strategy exists after remote reconnects.
- [ ] Lifecycle cleanup runs when the context closes.
- [ ] JMX notifications are not used as durable business event transport.

## 23. Hands-On Exercises

### Exercise A — Comparing Synchronous and Async

Create a `NotificationBroadcasterSupport` and a listener whose callback sleeps 50 ms in a lab. Emit 200 notifications and measure producer duration. Switch to an executor and compare emission time, processing latency, and pending task count.

### Exercise B — 10,000-Notification Burst

Create a producer emitting 10,000 notifications with three listeners. Measure CPU, heap, callback count, and total processing time. Identify which listener is the bottleneck.

### Exercise C — Bounded Queue

Use an executor with 2 workers and a queue of 100 entries. Block workers with a latch, submit additional notifications, and verify the overload policy. Track counters for rejected/dropped tasks.

### Exercise D — Per-Resource Coalescing

Replace 1,000 `queue.depth.changed` notifications with one notification per time window per queue ID. Have the listener read the `QueueDepth` attribute upon receiving the signal. Evaluate the trade-off if state changes multiple times within the window.

### Exercise E — Remote Reconnect

Run a JMX client in another JVM, register a listener, disconnect, then reconnect. Compare the notification count with the current state. Write a resync step using `MBeanServerConnection.getAttribute`.

### Exercise F — Backpressure and Shutdown

Simulate a queue still holding many tasks when closing the Spring ApplicationContext. Design shutdown wait times, metrics for abandoned tasks, and explain conditions requiring a durable queue instead of JMX.

## 24. Self-Check Questions

1. Why can notification bursts slow down the emitting thread?
2. When does the backlog grow at `λ - μ`?
3. Does async dispatch solve overload by itself?
4. What risks does an unbounded queue introduce?
5. Which thread does `CallerRunsPolicy` push backpressure onto?
6. Why does event sequence not imply callback completion order?
7. When should throttling or coalescing be used?
8. Why is a counter usually better than a per-request notification?
9. Does remote JMX guarantee notification replay after reconnect?
10. Which metrics indicate a listener is overloaded?
11. Why can errors in executor workers be hard to observe?
12. When is a message broker needed instead of JMX notifications?

## 25. References

- Spring Framework Reference — JMX Notifications: https://docs.spring.io/spring-framework/reference/integration/jmx/notifications.html
- Spring Framework API — NotificationPublisher: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/notification/NotificationPublisher.html
- Spring Framework API — NotificationListenerBean: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/notification/NotificationListenerBean.html
- Java SE 21 — NotificationBroadcasterSupport: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotificationBroadcasterSupport.html
- Java SE 21 — ThreadPoolExecutor: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Java SE 21 — MBeanServerConnection: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html

**Remember:** JMX notification is a management signal, not a durable event stream. During event bursts, measure emission and processing rates, reduce noise at the source, bound queues and concurrency, define overload policies, instrument drops/lag/errors, and design resync for remote listeners. The goal is to keep the application stable even when the alerting system operates under heavy load.
