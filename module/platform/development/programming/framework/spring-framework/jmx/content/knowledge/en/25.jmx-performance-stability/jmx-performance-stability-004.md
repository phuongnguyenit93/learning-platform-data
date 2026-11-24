# Rate-Limiting Notification Emission in Spring Framework JMX

## 1. Why Must Notifications Be Rate-Limited?

Java Management Extensions (**JMX**) supports a **notification** mechanism for MBeans to emit signals when application state changes. In Spring Framework JMX, a bean can be exported as an MBean using `MBeanExporter`, declare notification metadata with `@ManagedNotification`, and emit events via `NotificationPublisher` or standard JMX APIs.

This mechanism fits management events such as:

- A worker transitioning from `RUNNING` to `PAUSED`.
- A queue crossing a warning threshold.
- A cache completing a refresh.
- A connection to an external system being disrupted.
- A maintenance task starting, failing, or completing.

However, **emitting a notification for every tiny change** can place heavy load on MBeans, connectors, and listeners. For instance, a queue processing 50,000 jobs per second that emits a notification on every job addition could generate 50,000 events per second—far exceeding the needs of a management system.

Rate-limiting emission is part of **performance and stability** design, not just a minor optimization. The goal is to reduce redundant events while preserving visibility into important changes.

## 2. Notification Architecture and Where Overload Can Appear

~~~text
Business service / resource
       |
       +-- state transition / threshold
       |
       v
MBean / Spring NotificationPublisher
       |
       +-- event filtering
       +-- throttling / coalescing
       |
       v
MBeanServer / NotificationBroadcaster
       |
       +-- local listener A
       +-- remote listener B
       +-- audit/monitoring listener C
       |
       v
Alerting / logging / dashboard
~~~

There are multiple sources of cost:

| Component | Impact at High Frequency |
| --- | --- |
| Business thread emitting event | Object creation, message formatting, holding locks, calling publisher |
| Notification broadcaster | Iterating listeners, evaluating filters, dispatching |
| Listener | CPU, blocking, logging, network calls |
| Remote JMX connector | Serialization, network, buffering, threads/connections |
| Observability backend | Ingestion, storage, alert fan-out |
| Operator | Alert fatigue, difficulty distinguishing critical events |

Do not assume every notifier dispatches asynchronously. Emission mechanisms may use a dedicated executor or run callbacks depending on the implementation. With synchronous listeners, a single slow handler can slow down the event-emitting path.

**Principle:** control emission frequency as close to the source as possible, while also designing listeners and connectors to handle load.

## 3. Distinguishing Rate Limiting, Throttling, Debounce, Coalescing, and Sampling

These concepts are not identical.

### 3.1. Rate Limiting

Limits the maximum number of notifications emitted within a time window.

Example:

~~~text
At most 10 notifications/second per MBean.
~~~

Token bucket, fixed window, or sliding window can be used.

### 3.2. Throttling

Allows emitting at most one event after a minimum interval.

~~~text
Emit only one queue-depth warning every 5 seconds.
~~~

Any events occurring between allowed emissions may be dropped or aggregated.

### 3.3. Debounce

Waits for a quiet period before emitting. If state continues changing, the emission time is pushed back.

~~~text
Continuous configuration changes
   -> emit only after 500 ms with no further changes
~~~

Debounce is useful for configuration bursts, but can postpone emission indefinitely if events never stop.

### 3.4. Coalescing

Merges multiple events into a single summary.

~~~text
100 queue-depth changes
   -> one notification: "100 changes, latest depth=1320"
~~~

Coalescing can preserve aggregate information instead of merely dropping events.

### 3.5. Sampling

Captures a subset of events, such as 1 in 100 or probabilistically. Sampling fits high-frequency data used for trend analysis, but is unsuitable for rare/critical events that must be recorded.

| Technique | Goal | Trade-Off |
| --- | --- | --- |
| Throttle | Avoid too many events in a short span | Skips intermediate changes |
| Token bucket | Allow controlled bursts | Requires managing tokens and clocks |
| Debounce | Wait for state to stabilize | Adds latency, may delay continuously |
| Coalescing | Merge fluctuations into summaries | Loses individual event detail |
| Sampling | Reduce statistical volume | Does not guarantee keeping specific events |
| Bounded queue | Protect memory and listeners | Requires full-queue policy |

## 4. Identifying Which Events Can Be Rate-Limited

Not all notifications are equal. Classify them before choosing an algorithm:

**High-frequency informational group:**

- Individual cache hits/misses.
- Continuously changing queue depth.
- Progress updates per small percentage.
- Active thread count fluctuating per request.

Usually it is better to **use metrics/attributes** with polling or aggregation rather than emitting a notification for every change.

**State transition group:**

- `HEALTHY -> DEGRADED`.
- `RUNNING -> FAILED`.
- `CONNECTED -> DISCONNECTED`.
- `PAUSED -> RUNNING`.

Emit when an actual state transition occurs, rather than re-emitting on every check cycle.

**Critical group:**

- Backup task failed.
- Resource exhaustion or risk of data loss.
- Unauthorized administrative action.
- A dangerous operation completed or failed.

For critical events requiring reliable delivery, rate-limiting JMX notifications alone is insufficient. If zero event loss must be guaranteed, use a durable event system, audit log, or dedicated acknowledgment mechanism.

## 5. Designing a Simple Policy Before Coding

Suppose the application has these notification types:

~~~text
com.example.queue.depth.warning
com.example.queue.depth.recovered
com.example.queue.worker.failed
com.example.queue.worker.restarted
~~~

Example policy:

| Event Type | Strategy |
| --- | --- |
| Queue depth crosses warning threshold | Emit on crossing; remind after 60 seconds if still high |
| Queue depth recovers | Emit once when returning to normal range |
| Worker failed | Emit on transition to FAILED |
| Worker restarted | Emit on transition to RUNNING |
| Routine queue depth | Metric/attribute, do not emit notification |

The benefit of **transition-based publishing** is reducing load right in the business logic without needing complex filters later.

Example when the threshold is 1000:

~~~text
depth  900 -> 1100 : WARNING
depth 1100 -> 1200 : no new warning emitted
depth 1200 ->  800 : RECOVERED
depth  800 -> 1300 : new WARNING
~~~

Clarify whether a "reminder warning after 60 seconds" is a new notification or a summary update. The same event type can use a new sequence number and explicitly state the suppressed count so recipients do not misinterpret it.

## 6. Spring MBeans Emitting Notifications with NotificationPublisher

In Spring JMX, a bean can implement `NotificationPublisherAware` to receive a `NotificationPublisher` and emit notifications.

~~~java
package com.example.management;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedNotification;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example:type=Queue,name=payments",
    description = "Payment queue management"
)
@ManagedNotification(
    name = "com.example.queue.depth.warning",
    description = "Queue depth crossed the warning threshold"
)
public class QueueManagement implements NotificationPublisherAware {

    private final AtomicLong sequence = new AtomicLong();
    private volatile int pendingCount;
    private volatile NotificationPublisher publisher;

    @Override
    public void setNotificationPublisher(NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    @ManagedAttribute
    public int getPendingCount() {
        return pendingCount;
    }

    public void onDepthChanged(int depth) {
        pendingCount = depth;

        if (depth > 1000 && publisher != null) {
            Notification event = new Notification(
                "com.example.queue.depth.warning",
                this,
                sequence.incrementAndGet(),
                System.currentTimeMillis(),
                "Queue depth exceeded threshold"
            );

            publisher.sendNotification(event);
        }
    }
}
~~~

This is a **basic unthrottled example**. As the queue continues rising from 1001 to 1002, 1003, 1004..., the logic emits continuously. State transition tracking or a limiter must be added to prevent a notification storm.

Note: `@ManagedNotification` declares metadata about the notification type; it **does not emit events itself and does not rate-limit frequency**. An appropriate exporter, such as `AnnotationMBeanExporter`, is required for Spring to recognize metadata and inject `NotificationPublisher`.

## 7. Approach 1: Emit Only When State Changes

A very effective technique is **edge-triggered notification**.

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

public class QueueThresholdGate {
    private final int warningThreshold;
    private final AtomicBoolean overThreshold = new AtomicBoolean();

    public QueueThresholdGate(int warningThreshold) {
        this.warningThreshold = warningThreshold;
    }

    public boolean shouldEmitWarning(int depth) {
        if (depth <= warningThreshold) {
            overThreshold.set(false);
            return false;
        }

        return overThreshold.compareAndSet(false, true);
    }
}
~~~

Example:

~~~java
QueueThresholdGate gate = new QueueThresholdGate(1000);

if (gate.shouldEmitWarning(depth)) {
    emitWarning(depth);
}
~~~

During a continuous series of changes above the threshold, only the first crossing emits a warning. When depth drops to or below the threshold, the gate resets and can emit a new warning on the next crossing.

### Issues When Multiple Threads Update Concurrently

The `AtomicBoolean` example only proves one thread succeeded in transitioning `false -> true`. If threads receive depth snapshots from different instants, a late "recovered" event could reset the flag after a newer over-threshold event.

For systems receiving many concurrent updates, compute state from an ordered source or use synchronization/a state machine protecting both the depth update and the emission decision.

If the threshold uses hysteresis, use separate "enter warning" and "recovery" thresholds to prevent flapping around a single point.

## 8. Hysteresis Reduces Notifications When Metrics Oscillate Around a Threshold

Suppose the warning threshold is 1000. When queue depth oscillates 999 ↔ 1001, a simple gate can repeatedly emit warning/recovered notifications.

Solution: hysteresis.

~~~text
Enter WARNING: depth >= 1000
Return NORMAL: depth <= 800
~~~

With a state machine:

~~~java
public enum QueueHealth {
    NORMAL,
    WARNING
}
~~~

~~~java
public synchronized QueueHealth updateHealth(int depth) {
    if (health == QueueHealth.NORMAL && depth >= 1000) {
        health = QueueHealth.WARNING;
        sendWarning(depth);
    } else if (health == QueueHealth.WARNING && depth <= 800) {
        health = QueueHealth.NORMAL;
        sendRecovered(depth);
    }
    return health;
}
~~~

`health`, `sendWarning`, and `sendRecovered` are members/methods to be defined in the actual bean. The pattern illustrates state transitions. Do not perform blocking I/O inside a synchronized region if the notification callback can be slow; compute the transition under the lock, then dispatch via an appropriate mechanism.

Hysteresis is particularly useful for CPU usage, queue backlogs, memory pressure, and flaky connections.

## 9. Approach 2: Time-Interval Throttling

If an event may repeat but does not need continuous emission, enforce a minimum interval between two emissions.

Example emitting at most one warning every 5 seconds within one JVM:

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

public final class NotificationThrottler {
    private final long intervalNanos;
    private final AtomicLong nextAllowedNanos = new AtomicLong(0L);

    public NotificationThrottler(long duration, TimeUnit unit) {
        if (duration <= 0) {
            throw new IllegalArgumentException("duration must be positive");
        }
        this.intervalNanos = unit.toNanos(duration);
    }

    public boolean tryAcquire(long nowNanos) {
        while (true) {
            long next = nextAllowedNanos.get();

            if (nowNanos < next) {
                return false;
            }

            long updated = nowNanos + intervalNanos;

            if (nextAllowedNanos.compareAndSet(next, updated)) {
                return true;
            }
        }
    }
}
~~~

Usage:

~~~java
NotificationThrottler throttler =
    new NotificationThrottler(5, TimeUnit.SECONDS);

if (throttler.tryAcquire(System.nanoTime())) {
    publishQueueWarning();
}
~~~

**Limitations of the simple pattern:**

- Uses `System.nanoTime()` for elapsed time rather than `currentTimeMillis()`, which is affected by system clock adjustments.
- Assumes uptime has not reached timestamp arithmetic overflow affecting comparisons; production code should use elapsed comparison and explicit initialization state if high durability is needed.
- This limiter only protects **one instance**. Multiple JVM replicas each have their own limiter.
- Does not automatically emit a summary of suppressed events.
- Does not distinguish notification types; multiple types sharing one instance compete for the same quota.

For business cases needing per-event-group separation, manage limiters by a key such as `ObjectName + notificationType`.

## 10. Approach 3: Token Bucket for Controlled Bursts

Throttling allows only one event per interval, yet sometimes short bursts must be permitted when multiple genuinely important state transitions occur.

A **token bucket** has these parameters:

~~~text
capacity = 10 notifications
refillRate = 5 tokens/second
~~~

Each emission requires one token. When the bucket is empty, events are suppressed or aggregated. After a quiet period, tokens refill up to capacity.

Conceptual algorithm:

~~~text
onEvent:
  now = monotonicClock()
  elapsed = now - lastRefill
  tokens = min(capacity, tokens + elapsed * refillRate)
  lastRefill = now

  if tokens >= 1:
      tokens -= 1
      emit()
  else:
      countSuppressed()
~~~

### Points to Note

- Synchronize all token/refill updates when multiple threads share a bucket.
- Avoid using wall-clock time to measure elapsed time whenever possible.
- Set capacity and refill rate according to event importance.
- Prevent a "noisy" event type from exhausting quota for critical types.
- With multiple JVMs, a local token bucket does not enforce a cluster-wide rate.

**A token bucket is suited to limiting traffic, not guaranteeing the most important event is always kept** if all events share one quota. Priorities and separate budgets can be used.

## 11. Approach 4: Coalescing and Summary Notifications

Instead of silently dropping rate-limited events, record the suppressed count and emit summary information on the next allowed emission.

Example:

~~~text
12:00:00 WARNING depth=1200
12:00:01..12:00:29 487 events suppressed
12:00:30 SUMMARY depth=1380 suppressed=487
~~~

A suppression-counting class:

~~~java
import java.util.concurrent.atomic.AtomicLong;

public final class SuppressedEventCounter {
    private final AtomicLong suppressed = new AtomicLong();

    public void onSuppressed() {
        suppressed.incrementAndGet();
    }

    public long drainSuppressedCount() {
        return suppressed.getAndSet(0L);
    }
}
~~~

When the limiter permits emission:

~~~java
long dropped = counter.drainSuppressedCount();

Notification event = new Notification(
    "com.example.queue.depth.warning.summary",
    this,
    sequence.incrementAndGet(),
    System.currentTimeMillis(),
    "Queue warning; suppressed=" + dropped
);

publisher.sendNotification(event);
~~~

This simple pattern has a possible race: an event suppressed right after draining is counted in the next batch. That is acceptable if summary semantics are defined as "batch recorded up to drain time", though the summary should not be described as an atomic snapshot across all threads without proper synchronization.

In addition to count, a summary can include:

- Latest value.
- Max/min within the window.
- Aggregation time interval.
- Number of state changes.
- Source identifier.

Do not stuff entire raw payloads into a summary's `userData`, as that can make notifications overly large.

## 12. Approach 5: Debouncing Configuration Changes

Suppose an operator changes several settings within one second. If every setter emits a "configuration updated" notification, clients may receive dozens of notifications.

Debouncing can wait 500 ms after the last change:

~~~text
setMaxWorkers()
setTimeout()
setBatchSize()
      |
      +-- debounce 500 ms
               |
               v
    configurationChanged (once)
~~~

However, an uninterrupted stream of changes can prevent debouncing from ever firing. When bounded observability is required, use **debounce with max-wait** or fixed-window aggregation.

When implementing with `ScheduledExecutorService`, cancel previous schedules, handle races between cancel and an already-running task, manage shutdown, and avoid creating a thread per event. Use a scheduler with clear ownership in the Spring context.

## 13. Approach 6: Limiting at the Listener and Bounded Queues

Even when producers already rate-limit, listeners still need self-protection because:

- Multiple emitters may fire simultaneously.
- A listener may connect to many JVMs.
- A producer may fail to follow policy.
- Downstream consumers may be slow or paused.

A design:

~~~text
JMX callback
    |
    v
validate/filter quickly
    |
    v
bounded queue
    |
    v
worker pool
    |
    v
logging / alert service
~~~

In Java:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import javax.management.Notification;
import javax.management.NotificationListener;

public class QueueingListener implements NotificationListener {
    private final BlockingQueue<Notification> queue =
        new ArrayBlockingQueue<>(1000);

    @Override
    public void handleNotification(
            Notification notification, Object handback
    ) {
        boolean accepted = queue.offer(notification);

        if (!accepted) {
            // Increment a dropped-event metric.
        }
    }

    public Notification take() throws InterruptedException {
        return queue.take();
    }
}
~~~

This pattern only builds a memory-bounded queue; the application must create workers reading from the queue, decide drop handling, shutdown, and metrics. If distinguishing sources is needed, store handback/ObjectName alongside the notification instead of only storing the Notification.

**Do not use an unbounded queue** to "avoid losing notifications" when the consumer can stall indefinitely; that can lead to OutOfMemoryError.

## 14. Spring Configuration: Separating Policy from Publisher

A design can be split into:

~~~text
QueueService
   |
   +-- state changes
   |
   v
QueueNotificationPolicy
   |
   +-- transition guard
   +-- throttle/coalescing
   |
   v
NotificationPublisher
   |
   v
JMX listeners
~~~

Advantages:

- Easy to unit test rate-limiting algorithms without starting an MBeanServer.
- Business services do not need to know `Notification` details.
- Policies can be swapped per event type.
- Metrics can track suppression.
- Keeps `NotificationPublisher` focused solely on emitting valid events.

Spring `@ManagedNotification` is MBean metadata. It **does not have a global rate-limit parameter** that automatically restricts all notifications. Limits are typically designed at the producer, emitter/scheduler, or listener.

## 15. Example Notification Policy Management Service

A simple interface:

~~~java
public interface ManagementEventPolicy {
    boolean shouldPublish(
        String resourceName,
        String notificationType,
        long nowNanos
    );
}
~~~

From this, per-key policies can be implemented:

~~~text
com.example:type=Queue,name=payments
    + com.example.queue.depth.warning
       -> 1 notification/5 seconds

com.example:type=Queue,name=shipping
    + com.example.queue.depth.warning
       -> 1 notification/30 seconds

com.example:type=Worker,name=primary
    + com.example.worker.failed
       -> publish every state transition
~~~

Do not use a single global limiter across all events when importance varies. A noisy emitter can consume the quota and prevent critical events from being sent.

### Managing Key Count

If a policy creates a separate limiter for every ID, and resource IDs are generated dynamically without bound, the limiter map can grow unboundedly. Use a stable registered resource set, an evicting cache, or an appropriate bounded key strategy.

## 16. Ensuring Time and Concurrency Correctness

Rate limiting depends on time and concurrency:

- **Time:** use a monotonic clock for durations.
- **Concurrency:** threads must not consume the same token/window as if only one event occurred.
- **Sequence:** JMX notification sequence numbers should increment per emitted event according to the emitter contract.
- **Publication:** if emitting while updating state, determine client observation ordering.
- **Clock skew:** timestamps across JVMs are insufficient for building global ordering.
- **Restart:** local limiters reset when the process restarts.

A sound testing technique is injecting a `Clock` or `LongSupplier` for time instead of hard-coding `System.nanoTime()` everywhere, keeping tests deterministic.

### Is Distributed Synchronization Needed?

If the requirement is "no more than 100 notifications/second across the entire cluster", a local per-JVM limiter is not enough. An aggregator or shared-state rate limiter may be required. However, for typical monitoring notifications, limiting per MBean/JVM and letting the monitoring system aggregate is usually preferable.

Avoid adding complex distributed coordination when the goal is simply preventing MBeanServer congestion in a single JVM.

## 17. Observability for the Limiter

An unmonitored rate limiter can mask severe conditions. Include metrics:

| Metric | Meaning |
| --- | --- |
| `notification_emitted_total` | Total notifications actually emitted |
| `notification_suppressed_total` | Total blocked by policy |
| `notification_coalesced_total` | Total events merged |
| `notification_delivery_errors_total` | Dispatch/client-layer errors if measurable |
| `notification_queue_depth` | Events waiting to be processed at listener |
| `notification_oldest_age_seconds` | Age of oldest event in queue |
| `notification_publish_duration` | Time spent publishing/dispatching |
| `notification_listener_failures_total` | Handler error count |

The names above are **application metric examples**, not JMX metrics automatically provided by Spring.

Add management attributes:

~~~java
@ManagedAttribute
public long getSuppressedNotificationCount() {
    return suppressedCounter.get();
}

@ManagedAttribute
public long getEmittedNotificationCount() {
    return emittedCounter.get();
}
~~~

This lets operators see the limiter working, avoiding misinterpreting "no notifications" as "system is healthy".

## 18. Do Not Confuse Rate Limiting with Event Preservation Requirements

If a notification is a state signal, coalescing can be acceptable:

~~~text
10,000 queue depth updates
    -> current depth + high-water mark
~~~

However, if each event is a legal/audit requirement that must not be lost, "drop under load" is the wrong architecture. JMX notifications are not a durable message broker with replay, acks, and exactly-once guarantees.

In that case, you can:

1. Write events to a transactional outbox or durable log.
2. Publish through an appropriate message broker.
3. Use JMX only to report status or pending event counts.
4. Emit aggregated JMX notifications as a secondary signal.
5. Design retries, deduplication, and auditing per business requirements.

Rate limiting protects performance, but does not replace guaranteed event delivery mechanisms.

## 19. Risks with Remote Notifications

Remote JMX may use an RMI connector. When notifications travel over the network:

- Serialization consumes CPU and bandwidth.
- Clients unable to keep up can lead to backlogs/notification loss depending on the connector.
- Disconnections can cause clients to miss events.
- Listeners may receive events late or out of the order observed at the source.
- Data in `userData` may require appropriate Serializable/open types.
- Every remote JMX endpoint needs authentication, TLS, and authorization.

Do not rely on JMX notifications as a transport channel for all high-frequency events across multiple JVMs. In distributed systems, use dedicated metric telemetry or event streaming instead.

### Throttling Before Crossing the Connector

If a notification is blocked right at the source, it never passes through the broadcaster or remote connector. This is usually much cheaper than sending everything and letting remote clients drop it.

Still, verify whether any client requires receiving every event. If so, do not apply a global drop policy that blinds that client; use a dedicated channel instead.

## 20. Testing a Rate Limiter

A test suite should verify:

1. Is the first event emitted?
2. Are closely spaced events within the same window suppressed properly?
3. Is an event after the interval expires emitted properly?
4. Do two threads calling concurrently ever exceed the quota?
5. Does a fake clock avoid making tests depend on `sleep`?
6. Do different notification types use independent quotas?
7. After restart, does local policy reset match the contract?
8. Does coalescing record the number of suppressed events?
9. Is a full queue handled according to the defined policy?
10. Are there no memory leaks from per-resource-ID limiter maps?
11. Are critical events ever blocked because informational events consumed the budget?
12. Are WARNING/RECOVERED transitions never mistakenly skipped?

### Unit Testing Throttle with Fake Time

~~~java
import java.util.concurrent.TimeUnit;

NotificationThrottler throttler =
    new NotificationThrottler(5, TimeUnit.SECONDS);

long t0 = TimeUnit.SECONDS.toNanos(100);

assert throttler.tryAcquire(t0);
assert !throttler.tryAcquire(t0 + TimeUnit.SECONDS.toNanos(1));
assert !throttler.tryAcquire(t0 + TimeUnit.SECONDS.toNanos(4));
assert throttler.tryAcquire(t0 + TimeUnit.SECONDS.toNanos(5));
~~~

The test uses passed-in timestamps to verify logic instead of sleeping for 5 seconds.

### Integration Testing with MBeanServer

An integration test can:

- Create an isolated MBeanServer.
- Register an MBean that emits notifications.
- Register a `NotificationListener` that counts events.
- Invoke the event-triggering method multiple times.
- Assert event counts within each window.
- Invoke after simulated time advances.
- Unregister the listener/MBean and release resources.

If using an async executor, the test needs a `CountDownLatch` or state synchronization to await results; do not make immediate assertions that easily turn flaky.

## 21. Common Mistakes

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Notification storm | Emitting event on every metric change | Switch to state transitions/metrics |
| Alerts oscillate around threshold | Missing hysteresis | Use distinct enter/exit thresholds |
| Critical events lost | Sharing limiter with noisy events | Separate priority/budget |
| Listener slows application threads | Blocking handler | Bounded async dispatch |
| Unbounded memory growth | Unbounded queue or limiter map | Bound capacity and eviction |
| Suppressed metric always 0 | Dropped events not counted | Add counter |
| Notifications not received | Listener unregistered or MBean not emitting | Check registration and metadata |
| Remote client misses events | Disconnection, connector backlog | Reconnect/resubscribe, alternative telemetry if needed |
| Same event emitted multiple times | Multiple emitters/registrations or missing dedup | Check ObjectName and subscriptions |
| Local limits set but cluster still noisy | Each replica has its own limiter | Aggregate or limit at collector |
| CPU spikes formatting messages | Formatting payload before rate limit | Gate first before building Notification |
| Unstable limit under concurrency | Non-atomic limiter updates | CAS/lock/state machine |

## 22. Production Deployment Checklist

1. Is a notification needed, or are metrics/attributes sufficient?
2. Which events are critical, and which can be dropped/coalesced?
3. Rate-limit per MBean, notification type, or entire JVM?
4. Are separate thresholds needed to enter/exit alerts?
5. Is there a cap on maximum events per second?
6. Are short bursts needed, or just one event per interval?
7. Is there a mechanism to report suppressed event counts?
8. Are payloads small enough and free of secrets?
9. Do handlers have bounded processing time and queue capacity?
10. Are executors/listeners cleaned up when the Spring context closes?
11. Is re-subscription needed when MBeans or connectors are replaced?
12. With multiple JVMs, is target identity preserved in monitoring?
13. For remote connectors, are TLS/authentication/authorization complete?
14. Are concurrency and time-boundary tests in place?
15. Is there a plan when monitoring needs more detail than summaries?
16. Are there critical events that must never be suppressed?
17. Is there durable auditing/logging for events that must be retained?
18. Are expected latency and potential event loss documented?

## 23. Self-Check Questions

**1. Does Spring `@ManagedNotification` rate-limit emission?** No. The annotation only declares notification metadata; emitting code or a policy layer must enforce limits.

**2. When is throttling better than debouncing?** When you need to guarantee an event can be emitted at a minimum cadence while the source changes continuously; debouncing fits waiting for a quiet period.

**3. Why check state transitions instead of emitting on every metric measurement?** Because many measurements do not represent a new state change; transition-based emission dramatically cuts redundant events.

**4. Should `System.currentTimeMillis()` be used to measure rate-limit intervals?** No, because wall clock time can be adjusted. Use monotonic time such as `System.nanoTime()` for durations.

**5. Does a single `AtomicBoolean` solve all race conditions when updating queue health?** No. You must ensure state updates have proper ordering/atomicity, especially when updates arrive from multiple threads with snapshots from different instants.

**6. Can a local token bucket limit total notifications across an entire cluster?** No. Each JVM has its own quota; cluster-wide limits require coordination or aggregation.

**7. Should an unbounded queue be used to avoid dropping notifications?** No. When consumers are slow, the queue can grow until memory is exhausted. Use a bounded queue and an overload policy.

**8. Are JMX notifications suitable as a durable audit channel?** They should not be treated as a durable storage/replay guarantee. Use an event log or message broker when zero event loss is required.

## 24. Summary

Rate-limiting notification emission is a vital part of performance and stability when using Spring Framework JMX.

Preferred approach:

- **Do not emit events for routine metric changes** when attributes/metrics can be used.
- **Emit on state transitions** and apply hysteresis to prevent flapping around thresholds.
- Use throttling/token buckets for high-frequency events that still need periodic updates.
- Use coalescing/summaries so operators know how many events were suppressed.
- Use bounded queues, fast handlers, and metrics to protect downstream systems.
- Evaluate critical events and durably persisted events separately.
- With remote JMX, reduce volume as close to the source as possible to avoid transport waste.

**The goal is not to eliminate as many events as possible, but to preserve critical management signals with controllable cost and predictable behavior under load.**

### References

- Spring Framework Reference — JMX Notifications: https://docs.spring.io/spring-framework/reference/integration/jmx/notifications.html
- Spring Framework API — `NotificationPublisher`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/notification/NotificationPublisher.html
- Spring Framework API — `NotificationPublisherAware`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/notification/NotificationPublisherAware.html
- Java SE API — `Notification`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/Notification.html
- Java SE API — `NotificationBroadcasterSupport`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotificationBroadcasterSupport.html
