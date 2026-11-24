# Tracking Paused Duration

In Spring Kafka, **pause** is a way to temporarily stop delivering additional records to a listener without necessarily closing the consumer or leaving the consumer group. An application can pause the entire listener container, pause a single partition, or let a backpressure mechanism request a pause when a database, HTTP service, or internal queue is overloaded.

The operational question does not stop at **is the consumer currently paused?** A partition might be intentionally paused for a few seconds so downstream recovers, yet if kept paused for tens of minutes, data keeps piling up. Therefore, you must measure **how long a pause has lasted**, **total paused time over an observation window**, **pause reason**, **latency from request to actual pause/resume**, and **impact on consumer lag, record age, and business SLOs**.

This lesson presents how to track paused state and duration in the **Pause and Backpressure** chapter of the **Spring Kafka Reliability Operations** module. The focus is on the Spring Kafka listener lifecycle, distinguishing requested vs. effective state, measuring duration with the right clock, handling rebalances, designing metrics/alerts, and building runbooks when pauses last longer than expected.

## 1. Pause is neither stop nor record completion

A Kafka consumer can reside in these operational states:

~~~text
RUNNING: polls and processes records
      |
      | container.pause() / pausePartition()
      v
PAUSE REQUESTED
      |
      | consumer thread applies pause at an appropriate point
      v
PAUSED: can still poll to maintain membership
      |
      | container.resume() / resumePartition()
      v
RESUME REQUESTED
      |
      | consumer thread applies resume
      v
RUNNING: resumes receiving and processing records
~~~

This diagram illustrates conceptual state transitions. Pause/resume is applied at a safe point in the consumer's poll loop; calling the pause request API does not mean every child consumer is immediately paused on that same call.

Comparison:

| Action | Goal | Consumer group | Unfinished records |
|---|---|---|---|
| Pause container | Temporarily halt fetching/delivering more data per container semantics | Usually keeps membership by continuing to poll | Still must finish/ack per policy |
| Pause partition | Block data from a specified partition | Consumer still owns assigned partitions | Must not commit past skipped records |
| Resume | Resume processing after pause | Keeps membership absent other rebalances | Retained data gets processed |
| Stop container | End listener lifecycle | May leave group or alter assignments per protocol | Handled/replayed per stop policy |
| Process crash | Sudden loss of processing capacity | Coordinator may reassign | Uncommitted records may redeliver |

**Pause is not acknowledgment.** A paused record does not mean the record was processed or its offset committed. When the consumer resumes, it must continue processing from the proper position per container, acknowledgment, and committed offsets.

## 2. Why must paused duration be measured?

Without duration metrics, a dashboard might show a paused indicator while operations has no idea whether:

- The pause started 200 milliseconds ago or has lasted 2 hours.
- The pause came from automatic backpressure or manual operator action.
- One partition is paused while other partitions are running normally.
- A resume command was sent yet the consumer thread has not applied it.
- The consumer rebalanced or stopped while telemetry still reports paused.
- Lag is rising due to an intentional pause or due to a slow listener, deserialization error, or hung transaction.
- Pausing relieved downstream load as intended.

For example, a consumer of topic `orders.events` pauses because the database connection pool saturated. Pausing for 10 seconds lets the database recover. However, if the circuit breaker closes after 10 seconds while the listener stays paused for 30 more minutes, the system loses processing time, breaches business SLOs, and grows backlog even while consumer CPU sits low.

Measuring duration helps catch **forgotten pauses**, set escalation thresholds, and analyze the fraction of time consumers are not processing data.

## 3. Multiple types of pause duration must be tracked

A metrics design should separate at least five quantities:

| Quantity | Meaning | Question answered |
|---|---|---|
| Requested pause age | Time since the application requested pause | How long has the pause command been pending? |
| Effective pause age | Time since the container/partition actually paused | How long has it stopped processing? |
| Resume application latency | From resume request until paused state is cleared | Why was resume called yet not running? |
| Completed pause duration | Duration of a finished pause interval | How long did each pause last? |
| Cumulative paused time | Total time in paused state within a window | How much time did the consumer lose to backpressure? |

Never record only a single `pauseRequestedAt` timestamp and call every metric pause duration. A request can be recorded long before the consumer thread applies the pause, especially when the listener is processing a large poll or stuck on a dependency.

### 3.1. Timeline example

~~~text
t=00.0s  Listener is processing a batch
t=00.2s  Service calls container.pause()
t=04.0s  Consumer actually pauses after finishing processing
t=14.0s  Service calls container.resume()
t=15.0s  Consumer applies resume

Requested-to-effective pause latency = 3.8s
Effective paused duration           = 11.0s
Requested pause interval            = 13.8s
Resume application latency          = 1.0s
~~~

If a dashboard measures from t=00.2s to t=15s, it reports 14.8 seconds rather than the 11 seconds the consumer was actually paused. Both numbers are useful, yet serve different purposes.

## 4. Pause/resume APIs in Spring Kafka

Spring Kafka provides pause/resume APIs on the listener container. For listeners declared with `@KafkaListener`, you can fetch the container through **`KafkaListenerEndpointRegistry`** by listener ID.

Example:

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class OrdersListenerControl {

    private final KafkaListenerEndpointRegistry registry;

    public OrdersListenerControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrders() {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

        if (container != null && container.isRunning()) {
            container.pause();
        }
    }

    public void resumeOrders() {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

        if (container != null && container.isRunning()) {
            container.resume();
        }
    }
}
~~~

Corresponding listener:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.events",
    groupId = "orders-worker"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

Depending on Spring Boot configuration and container factories, the registry may be auto-created by Kafka listener infrastructure. In applications with multiple factories or listener IDs, ensure the code controls the **exact** target container.

**Never call `KafkaConsumer.pause()` directly from an arbitrary thread.** `KafkaConsumer` carries no general thread-safety guarantee for such calls. Use the container API to request pause/resume and let the consumer thread apply it at an appropriate time.

## 5. Requested state differs from effective state

Spring Kafka exposes state flags such as:

- **`isPauseRequested()`:** the application has requested a pause for the container.
- **`isConsumerPaused()`:** pause state has been applied per container semantics.
- **`isPartitionPauseRequested(partition)`:** a pause was requested for a specific partition.
- **`isPartitionPaused(partition)`:** the partition is recorded by the container as paused.

Method names and aggregate behavior on `ConcurrentMessageListenerContainer` depend on version. When a container holds multiple child consumers, a single aggregate boolean cannot fully describe every partition.

Inspection example:

~~~java
MessageListenerContainer container =
    registry.getListenerContainer("orders-listener");

if (container != null) {
    boolean requested = container.isPauseRequested();
    boolean effective = container.isConsumerPaused();

    log.info(
        "orders listener pause requested={}, effective={}",
        requested,
        effective
    );
}
~~~

If `requested=true` while `effective=false`, the consumer may still be finishing fetched work or has not yet reached the pause application point. If `requested=false` while `effective=true`, resume may have just been requested without taking effect yet, or the container still holds a partition paused by another mechanism.

Do not rely on a single snapshot to declare a failure. Track state over time and separate global pause from partition-specific pause.

## 6. Tracking per-partition pause

When a topic has multiple partitions, backpressure may occur on only one partition. If metrics only track listener-level `paused=true/false`, dashboards can miss the issue:

~~~text
orders.events:
  partition 0 -> RUNNING, lag 10
  partition 1 -> PAUSED,  lag 25,000
  partition 2 -> RUNNING, lag 20
  partition 3 -> RUNNING, lag 5
~~~

With partition pause, for example:

~~~java
import org.apache.kafka.common.TopicPartition;

TopicPartition target =
    new TopicPartition("orders.events", 1);

MessageListenerContainer container =
    registry.getListenerContainer("orders-listener");

if (container != null) {
    container.pausePartition(target);
    // Actual state takes effect on the consumer thread.
}
~~~

Tracking the partition:

~~~java
boolean requested =
    container.isPartitionPauseRequested(target);

boolean effective =
    container.isPartitionPaused(target);
~~~

Verify these methods against your Spring Kafka version. In particular, if the partition is not yet assigned to the current container, an in-memory request flag must not be interpreted as the Kafka broker having paused that partition.

A good metric can include topic, partition, listener ID, and instance identity. On clusters with tens of thousands of partitions, consider cardinality before putting all of them into metric labels.

## 7. Events when pause or resume is applied

Spring Kafka emits container application events related to pause/resume, such as:

- **`ConsumerPausedEvent`**: notifies that consumer/container pause took effect per framework logic.
- **`ConsumerResumedEvent`**: consumer/container resumed per framework logic.
- **`ConsumerPartitionPausedEvent`**: a partition was paused.
- **`ConsumerPartitionResumedEvent`**: a partition was resumed.

These events let instrumentation measure duration much closer to **effective state** than when code calls `pause()`. Event names, payloads, container references, and timing may vary across Spring Kafka versions; verify Javadocs for your running version.

Event-driven architecture example:

~~~text
PauseService calls pause()
       |
       +--> record requestedAt and reason
       |
       v
Consumer thread applies pause
       |
       v
Spring Kafka publishes paused event
       |
       +--> tracker starts effective timer
       |
       +--> Gauge paused=1, currentPausedSeconds climbs
       |
       v
PauseService calls resume()
       |
       +--> record resumeRequestedAt
       |
       v
Consumer thread applies resume
       |
       v
Spring Kafka publishes resumed event
       |
       +--> tracker stops timer and records duration
       |
       +--> Gauge paused=0, currentPausedSeconds=0
~~~

If the event listener runs asynchronously, callback arrival time can lag behind the true state transition. When high precision is needed, instrument right at the event emission boundary or accept dispatcher/sampling skew and document the precision level.

Never run HTTP/database queries or lengthy logic inside an application event handler running on the consumer thread. Handlers should update in-memory metrics quickly and let metrics exporters scrape asynchronously.

## 8. Measuring duration with a monotonic clock

A common mistake is using:

~~~java
long started = System.currentTimeMillis();
long duration = System.currentTimeMillis() - started;
~~~

Wall clocks can be adjusted by NTP or OS time synchronization; differences sometimes fail to reflect true elapsed time. To measure **durations within a single JVM**, use **`System.nanoTime()`**.

Principles:

- **`System.nanoTime()`:** measures relative time, suited for elapsed durations.
- **`Instant.now()` / `Clock`:** records UTC timestamps for log investigation, dashboards, and incident timelines.
- **Persisted `startedAt`:** if you must know how long a pause spanned across restarts, persist timestamps in durable storage and reconcile against actual state; `System.nanoTime` cannot be carried from one JVM to another.

Example:

~~~java
long startedNanos = System.nanoTime();

// After actually resuming:
long durationNanos = System.nanoTime() - startedNanos;
long durationMillis =
    TimeUnit.NANOSECONDS.toMillis(durationNanos);
~~~

Never persist a `System.nanoTime()` value to a database and reuse it after a restart. The origin of `nanoTime` has no UTC meaning and is not designed for cross-process comparisons.

## 9. Simple tracker for a single pause state

To track a listener container overall, you can store when effective pause started and add elapsed time when state returns to running.

Java example:

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

public final class PauseDurationStats {

    // Value 0 means there is currently no open pause interval.
    private final AtomicLong startedNanos = new AtomicLong(0L);
    private final LongAdder completedNanos = new LongAdder();
    private final LongAdder completedIntervals = new LongAdder();

    public void observe(boolean actuallyPaused) {
        if (actuallyPaused) {
            startedNanos.compareAndSet(0L, System.nanoTime());
            return;
        }

        long start = startedNanos.getAndSet(0L);
        if (start != 0L) {
            long elapsed = Math.max(0L, System.nanoTime() - start);
            completedNanos.add(elapsed);
            completedIntervals.increment();
        }
    }

    public boolean isActive() {
        return startedNanos.get() != 0L;
    }

    public double currentPausedSeconds() {
        long start = startedNanos.get();
        return start == 0L
            ? 0.0
            : Math.max(0L, System.nanoTime() - start) / 1e9;
    }

    public double totalPausedSeconds() {
        return completedNanos.sum() / 1e9 + currentPausedSeconds();
    }

    public long completedPauseCount() {
        return completedIntervals.sum();
    }
}
~~~

This example illustrates timing principles. It keeps statistics **in one JVM's memory** and does not automatically aggregate across instances. `observe()` must be called on every effective state change or on a consistent sampling schedule. When a listener stops/rebalances, close the interval under a separate **lifecycle reason** rather than interpreting stop as "resumed successfully."

If the same object receives `observe` calls from multiple threads or child consumers, define clear semantics: one tracker per consumer/partition or synchronized aggregation. Never use a single boolean to sum durations across multiple partitions if accurate **partition-seconds** are needed.

## 10. Scheduled state sampling

When millisecond accuracy is unnecessary, a scheduled monitor can inspect the container every second:

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class OrdersPauseSampler {

    private final KafkaListenerEndpointRegistry registry;
    private final PauseDurationStats stats = new PauseDurationStats();

    public OrdersPauseSampler(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    @Scheduled(fixedDelay = 1_000L)
    public void sample() {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

        if (container == null || !container.isRunning()) {
            // Record stop state separately; do not equate it with resume.
            return;
        }

        stats.observe(container.isConsumerPaused());
    }

    public double activePausedSeconds() {
        return stats.currentPausedSeconds();
    }
}
~~~

The application must enable scheduling infrastructure, such as **`@EnableScheduling`**, if not already configured. Scheduled samplers suit container-level state, yet carry limitations:

- Pauses under 1 second may be missed.
- Requested-to-effective latency is not measured if calling only `isConsumerPaused()`.
- With multiple child consumers, an aggregate flag can hide partial pauses.
- After restarts, in-memory durations reset.
- If a container stops while paused, the interval must close with reason `STOPPED` so it does not grow indefinitely.

For dashboards needing accurate per-partition data and reason breakdowns, an event-driven tracker combined with periodic reconciliation is better suited.

## 11. Attaching Micrometer metrics

Spring Boot commonly integrates **Micrometer** to export metrics to Prometheus or other monitoring backends. For pause duration, two main metric families are useful:

**Gauges for ongoing state:**

- `paused.active`: 0 or 1.
- `paused.current.seconds`: seconds of the currently open interval, climbing continuously while paused.
- `pause.requested.current.seconds`: elapsed time of an unapplied pause request if needed.

**Timers/Histograms for completed intervals:**

- `paused.duration`: distribution of completed pause durations.
- `pause.to.effective.latency`: time from request to actual pause.
- `resume.to.effective.latency`: time from resume request to actual resume.

Example registering gauges:

~~~java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

public void registerPauseMetrics(
        MeterRegistry registry,
        PauseDurationStats stats) {

    Gauge.builder(
        "app.kafka.pause.current.seconds",
        stats,
        PauseDurationStats::currentPausedSeconds
    )
    .tag("listener_id", "orders-listener")
    .register(registry);

    Gauge.builder(
        "app.kafka.pause.active",
        stats,
        state -> state.isActive() ? 1.0 : 0.0
    )
    .tag("listener_id", "orders-listener")
    .register(registry);

    Gauge.builder(
        "app.kafka.pause.total.seconds",
        stats,
        PauseDurationStats::totalPausedSeconds
    )
    .tag("listener_id", "orders-listener")
    .register(registry);
}
~~~

These metric names are **custom suggestions**, not built-in metrics guaranteed to exist across all Spring Kafka versions. Micrometer/Prometheus may convert dots to underscores and normalize suffixes per exporter conventions.

Never rely solely on a `Timer` to alert on prolonged pauses: a very long unfinished interval **has not yet been recorded into completed duration histograms**. You must expose a **current paused age** gauge to catch an ongoing pause immediately.

### 11.1. Recording a completed pause

Example on paused -> resumed transition:

~~~java
Timer completedPauseTimer = Timer.builder(
    "app.kafka.pause.duration"
)
    .tag("listener_id", "orders-listener")
    .register(meterRegistry);

// elapsedNanos is measured using a monotonic clock.
completedPauseTimer.record(
    elapsedNanos,
    TimeUnit.NANOSECONDS
);
~~~

A `Timer` provides count, total time, max, and histograms/percentiles if configured. Record duration only when an effective pause interval actually ends.

## 12. Defining a pause interval lifecycle

To avoid double counting, a pause interval needs an explicit state machine:

~~~text
ACTIVE
  |
  | effective pause transition
  v
PAUSED(startNano, reason, assignmentEpoch)
  |
  +-- duplicate paused event --> keep current interval
  |
  +-- effective resume --> close interval(reason=RESUMED)
  |
  +-- partition revoked --> close interval(reason=REVOKED)
  |
  +-- container stopped --> close interval(reason=STOPPED)
  |
  +-- application shutdown --> close interval(reason=SHUTDOWN)
~~~

Repeated/no-op pause events must not reset the start time. If a caller invokes `pause()` every second while the consumer is already paused, duration must keep climbing from the first transition rather than restarting.

Similarly, repeated resumes must not emit multiple completed intervals. Use transition detection, atomic state, or appropriate locking.

A completed interval can record fields:

~~~text
listenerId       = orders-listener
topic            = orders.events
partition        = 3
startedAtUtc     = 2026-11-15T14:00:00Z
endedAtUtc       = 2026-11-15T14:02:15Z
durationSeconds  = 135
reason           = DOWNSTREAM_OVERLOAD
endReason        = RESUMED
instanceId       = orders-pod-7
assignmentEpoch  = ...
~~~

UTC timestamps help with audits/incidents; durations inside the same JVM should still use a monotonic clock.

## 13. Total paused time: listener-seconds or partition-seconds?

A **total paused time** metric is easily misinterpreted when multiple partitions exist.

Suppose a consumer owns 3 partitions:

- Partition 0 paused for 10 seconds.
- Partition 1 paused during the same 10 seconds.
- Partition 2 stayed running.

Then:

- **Container elapsed pause window:** may be 10 seconds if defined as "at least one partition is paused."
- **Partition-seconds:** 10 + 10 = 20 partition-seconds.
- **Paused partition ratio:** 2/3 during that window.
- **Full container paused:** false because partition 2 remained active.

Never sum individual partition durations and report that "the application stopped for 20 seconds." Total partition-seconds measures paused partition resource-time, not wall-clock pause duration.

A good dashboard can display:

| Metric | Definition |
|---|---|
| `app.kafka.pause.partitions` | Number of partitions actually paused at measurement time |
| `app.kafka.pause.partition.seconds.total` | Cumulative duration summed across each partition |
| `app.kafka.pause.any.seconds.current` | Elapsed time since at least one partition paused, if defined that way |
| `app.kafka.pause.container.active` | Whether the entire container is in the paused state |
| `app.kafka.pause.max.partition.age.seconds` | Longest active pause age among currently paused partitions |

These metric names are illustrative modeling examples, not built-in Spring Kafka properties.

## 14. Always record the pause reason

Kafka does not know the **business reason** why an application paused. For operations, pause-control code should attach a bounded-value reason.

Enum example:

~~~java
public enum PauseReason {
    DOWNSTREAM_OVERLOAD,
    IN_MEMORY_QUEUE_HIGH,
    CIRCUIT_OPEN,
    RATE_LIMIT,
    MANUAL_MAINTENANCE,
    CONFIG_ROLLOUT,
    UNKNOWN
}
~~~

When requesting a pause:

~~~text
requestPause(
    listener="orders-listener",
    reason="DOWNSTREAM_OVERLOAD",
    correlationId="incident-417"
)
~~~

The tracker records:

- `requestedAt`.
- `requestedBy` or automation source.
- Normalized `reason`.
- Context/incident ID in logs or traces.
- `expectedResumeCondition`.
- `expectedDeadline` or `reviewAt` for manual pauses.

Never use exception messages, URLs, customer IDs, or event IDs as a `reason` metric label: cardinality can explode unboundedly. Reason labels must be a bounded enum; correlation IDs belong strictly in logs/traces.

### 14.1. One container with multiple pause reasons

Suppose a circuit breaker requested a pause while an operator also enabled a maintenance pause. If the circuit breaker recovers and calls `resume()` immediately, the maintenance pause could be canceled accidentally.

A pause coordinator can store an **active reasons set**:

~~~text
activeReasons = { CIRCUIT_OPEN, MANUAL_MAINTENANCE }

Circuit recovers:
activeReasons = { MANUAL_MAINTENANCE }
=> remain paused

Operator ends maintenance:
activeReasons = {}
=> now request resume
~~~

This is an application-specific policy; Kafka containers do not automatically reference-count every reason. When multiple pause/resume sources exist, centralize control authority in one coordinator instead of letting each component call `resume` independently.

## 15. Backpressure pauses: two watermarks and hysteresis

Backpressure typically occurs when downstream processes slower than records arrive. For example, a listener pushes work onto an executor queue; when the queue nears full, the service must temporarily stop taking more.

An illustrative policy:

~~~text
Queue capacity = 10,000 tasks

Queue usage >= 8,000 (80%)
    -> request pause

Queue usage <= 3,000 (30%)
    -> request resume
~~~

Because the pause and resume thresholds differ, this creates **hysteresis**. It prevents oscillation when the queue fluctuates around a single threshold:

~~~text
Without hysteresis:
79% RUN -> 81% PAUSE -> 79% RESUME -> 81% PAUSE ...

With hysteresis:
80% PAUSE -> 65% still PAUSED -> 30% RESUME
~~~

Track pause duration to evaluate policy effectiveness:

- If pauses are very brief and repeat rapidly, watermarks may be too close together.
- If pauses regularly last tens of minutes, downstream capacity may be insufficient.
- If the queue dropped below the low watermark yet paused age keeps rising, resume coordination may be broken.
- If resuming triggers huge load spikes, add ramp-up/concurrency limits instead of unleashing everything at once.

Never auto-resume solely because a pause exceeded a time limit if the dependency is still failing. Duration is an **alert/escalation condition**, not necessarily a trigger to force resumption.

## 16. Tracking latency from pause request to actual pause

An often overlooked latency is **pause application latency**.

Example:

~~~text
Queue hits 90% at 10:00:00
PauseService calls pause() at 10:00:00.050
Listener is processing a 500-record batch
Consumer applies pause at 10:00:17
~~~

Here, the queue can continue growing for 17 seconds after pause was requested. If autoscaling/backpressure watches only `requested=true`, the system may think ingress is already blocked while the consumer actually keeps processing fetched records.

Measure:

~~~text
pause_apply_latency =
  effective_pause_at - pause_requested_at
~~~

When latency exceeds thresholds:

- Inspect `max.poll.records`.
- Inspect per-record or batch processing times.
- Check whether the listener is blocking on HTTP/database or locks.
- Check `pauseImmediate` support in your Spring Kafka version if stopping after the current record is needed.
- Check CPU starvation/GC pauses.
- Confirm the container is actually running.

A failed request or a container stopping before applying pause must not be recorded as a completed effective pause interval.

## 17. Tracking latency from resume request to actual resume

Similarly, when the dependency recovers:

~~~text
10:05:00  Database healthy
10:05:01  PauseCoordinator calls resume()
10:05:02  Spring Kafka container applies resume
10:05:04  Listener receives new record
~~~

Here:

- Resume application latency: roughly 1 second.
- Time-to-first-record after resume: roughly 2 seconds.
- End-to-end recovery latency: from database healthy to record processed successfully.

If resume was applied yet no records arrive, that is not necessarily a pause bug. The topic might be empty, partitions unassigned, consumer lag genuinely 0, the listener error handler retrying, or downstream still unready.

Combine multiple signals: resumed events, assigned partitions, lag, `records-consumed-rate`, listener success count, and error rate.

## 18. Rebalances make pause duration harder to measure

In a Kafka consumer group, partitions can be revoked from one instance and assigned to another. In that case, **one consumer instance's pause state** is not equivalent to **the business status of the partition across instances**.

Example:

~~~text
t=00s  Pod A owns partition 2, paused due to high queue
t=20s  Rebalance occurs
t=21s  Partition 2 revoked from Pod A
t=25s  Pod B assigned partition 2
t=26s  Pod B may begin processing if no pause policy exists
~~~

If Pod A's monitor keeps the pause interval open waiting for a resumed event, paused age can climb forever even though Pod A no longer owns partition 2.

Use a lifecycle-aware tracker:

- When a partition is revoked/lost, close the old assignment's pause interval with `endReason=REVOKED` or `LOST`.
- When the partition is assigned on a new consumer, open a new assignment epoch.
- If business policy still requires pausing that partition, reconcile desired pause state after assignment.
- Never assume a local in-memory pause request automatically transfers to another Pod.
- Never sum durations from old and new assignments as one continuous interval when reporting per-instance effective time.

For end-to-end visibility of "how long a partition was halted by policy across owners," persist desired state and timestamps in shared storage, then aggregate across partition/assignment epochs.

## 19. ConsumerRebalanceListener helps close intervals

Spring Kafka supports callbacks for assign/revoke/lost partitions. Common callbacks via `ConsumerAwareRebalanceListener` include:

- `onPartitionsAssigned`.
- `onPartitionsRevokedBeforeCommit`.
- `onPartitionsRevokedAfterCommit`.
- `onPartitionsLost`.

Pause tracking should:

1. Record current partition assignments.
2. Record `endReason` when partitions lose ownership.
3. Clear stale gauges or set `active=0` for lost assignments.
4. On reassignment, check desired pause policy and actual state.
5. Track rebalance duration with a separate metric.

Never try to commit offsets or call resume as the old owner after **`onPartitionsLost`**. The consumer may have already lost authority over the partition.

Event callbacks should not run slow database/HTTP operations. If reconciling desired state from a shared store is required, run a separate time-bounded workflow that safely handles ownership changes.

## 20. ConcurrentMessageListenerContainer: avoid misleading aggregate metrics

When `@KafkaListener` has concurrency greater than 1, Spring Kafka can create multiple child consumer containers:

~~~text
orders-listener (concurrency=3)
      |
      +-- child-0 owns partitions [0, 3]
      |
      +-- child-1 owns partitions [1, 4]
      |
      +-- child-2 owns partitions [2, 5]
~~~

When the parent container pauses, each child applies pause along its own poll lifecycle. There can be a window where child-0 is already paused while child-1 is still processing a record.

Therefore:

- The parent requested flag reflects the controller's intent.
- Child effective flags/events reflect each consumer's actual state transition.
- Partition-level events pinpoint exactly which partitions paused.
- A parent boolean represents aggregate status, not a substitute for granular metrics.

Dashboards can display:

- Paused child consumers / total child consumers.
- Paused assigned partitions / total assigned partitions.
- Maximum effective pause age across partitions.
- Maximum pause apply latency across children.

To prevent metric explosion, keep per-partition details in logs or an event store, while exporting aggregates by listener/topic/instance in Prometheus when partition counts are huge.

## 21. Combining pause duration with consumer lag

Pause duration alone does not tell how severely data is impacted. View it alongside:

- Consumer group committed offsets.
- Each partition's log end offset.
- Consumer lag.
- Record arrival rate.
- Oldest unprocessed record age.
- Post-resume throughput and processing latency.

Example:

~~~text
Partition 2 paused for 5 minutes
Producers write 100 more records/second

Theoretical backlog increase:
5 × 60 × 100 = 30,000 records
~~~

This is only an estimate assuming the partition saw zero processing during that period and producer rate stayed constant. Real lag also depends on committed offsets, already-fetched batches, prior backlog, reassignments, and progress commits.

If a pause drags on while the topic has no new data, lag may not grow. Still, **pause policy may need an alert** when it should have resumed already, because the very next incoming record will be delayed.

Conversely, rising lag does not prove the consumer is paused: it could be processing slowly, rebalancing, failing commits, hitting a poison record, or held back by `read_committed` LSO.

## 22. Retention and backlog during long pauses

Kafka retains records by topic retention policy, not by a consumer group's paused state.

If a topic's retention is only a few hours while a consumer stays paused longer, unprocessed records can be deleted from the log per retention before the consumer resumes. That can cause offset out-of-range errors and lose the ability to replay from the original committed offset.

Example:

~~~text
Topic retention: 24 hours
Consumer paused: 30 hours
Producers continuously write records
      |
      v
Old records purged by Kafka per retention
      |
      v
Consumer resumes from stale committed offset
      |
      v
OffsetOutOfRange or reset policy applied
~~~

Actual retention time depends on segment cleanup, topic configuration, and broker behavior; this is a general risk, not an exact deletion cutoff at the 24-hour mark.

Therefore, paused-age alert thresholds must factor in:

- Topic retention.
- Oldest unprocessed record age.
- End-to-end processing SLOs.
- Post-resume catch-up capacity.
- Inbound record volume during outages.

Never assume keeping group membership via pause means records are retained forever.

## 23. Pause and polling: avoid max.poll.interval.ms misunderstandings

Spring Kafka's container pause lets the consumer keep polling at appropriate intervals to retain consumer group membership without delivering records to the listener. This differs from putting a very long `Thread.sleep` inside the listener or blocking the consumer poll thread.

In typical scenarios:

~~~text
Container paused
    |
    +-- KafkaConsumer keeps polling per lifecycle
    |
    +-- Kafka group heartbeat/membership remains maintained
    |
    +-- Listener receives no records from paused partitions
~~~

However, **pause does not exempt the consumer from all group constraints**. If the consumer thread blocks in an HTTP call, GC pause, synchronous event handler, or improper retry loop, it can still miss its poll deadline and violate `max.poll.interval.ms`.

When seeing a paused consumer with rising rebalances:

- Verify whether the container is still polling.
- Check whether the listener has unfinished in-flight tasks.
- Check whether pause was requested mid-large batch.
- Check exception/backoff handlers.
- Measure pause application latency and poll-loop responsiveness.

Never call `KafkaConsumer.pause()` and sleep indefinitely on the consumer thread as a substitute for the container pause API.

## 24. Retry-backoff pause differs from manual pause

Spring Kafka can use backoff mechanisms that temporarily pause the container, such as waiting to retry a record without keeping the poll thread blocked for too long. Some configurations use **`ContainerPausingBackOffHandler`** or equivalent mechanisms.

Not every retry wait is recorded identically to an application calling `container.pause()`. When building metrics:

- Identify which mechanism triggered the pause.
- Verify whether effective paused/resumed events fire on that path.
- Assign a distinct reason such as `RETRY_BACKOFF` rather than `DOWNSTREAM_OVERLOAD`.
- Never miscount elapsed retry backoff as manual operator pause time.
- Also measure retry attempts, retry successes, and retry durations.

If the system uses `@RetryableTopic`, failed records move to retry topics instead of pausing the main container. The main topic continues processing while delay sits in retry queues. Never use the main consumer's paused duration to measure how long records wait on retry topics; use dedicated metrics for retry record age and retry topic lag.

## 25. Cumulative paused ratio and availability

Besides current paused age, you can compute the **paused time ratio** over a window:

~~~text
paused_ratio =
    paused_seconds_in_window / window_seconds
~~~

For example, within 1 hour, one listener instance spent 12 total minutes paused:

~~~text
paused_ratio = 12 / 60 = 20%
~~~

When a container has multiple partitions, define the ratio explicitly:

- **Container fully-paused ratio:** time the entire container was paused / total time.
- **Any-partition-paused ratio:** time at least one partition was paused / total time.
- **Partition-weighted paused ratio:** partition-seconds / total assigned partition-seconds.

These three numbers can differ substantially. Never report a generic "pause percentage" without specifying the denominator and aggregation method.

A high paused ratio can be valid during controlled maintenance, yet for real-time consumers it usually signals insufficient downstream capacity or miscalibrated pause/resume policies.

## 26. Post-resume latency and backlog catch-up

After a pause interval, measure **time from resume until backlog returns to acceptable levels**. Resuming does not mean waiting records have already been processed.

Example timeline:

~~~text
00:00  Consumer pauses
05:00  Consumer resumes
05:05  Listener processes first record after resume
09:00  Consumer lag drops below 100
~~~

Quantities:

- Effective paused duration: 5 minutes.
- Time-to-first-success after resume: 5 seconds.
- Backlog catch-up time: 4 minutes.
- Total data delay: includes paused duration plus time spent waiting in backlog.

Build dashboards combining **pause age**, **lag**, **processing rate**, **oldest record age**, and **estimated drain time** when reliable rate measurements exist.

Estimating drain time:

~~~text
drain_seconds ≈ backlog_records /
                max(processing_rate - incoming_rate, epsilon)
~~~

If processing rate does not exceed incoming rate, backlog cannot shrink; never display a fake precise ETA when the denominator is non-positive.

## 27. Auto-resume must depend on real conditions

A safe backpressure policy should not run a cron every 30 seconds to call `resume()` regardless of whether downstream recovered.

Example state machine:

~~~text
RUNNING
   |
   | queue >= highWatermark or circuit open
   v
PAUSE_REQUESTED
   |
   | pause applied
   v
PAUSED
   |
   | queue <= lowWatermark
   | AND downstream healthy
   | AND minPauseDuration satisfied if configured
   v
RESUME_REQUESTED
   |
   | resume applied
   v
RUNNING
~~~

A **maximum pause duration** can serve as an alert/escalation threshold:

- After 60 seconds: warning.
- After 5 minutes: critical or page on-call.
- After 15 minutes: escalate to manual intervention/load shedding per SLO.

These milestones are illustrative only. Real thresholds must reflect business SLOs, topic retention, ingress rate, and downstream recovery characteristics.

Never force a resume while the circuit remains open merely to reset the `current paused seconds` metric to 0. That can trigger retry storms or worsen dependency outages.

## 28. Avoiding pause/resume flapping

If a consumer pauses and resumes too frequently:

~~~text
Pause 0.2s
Resume 0.1s
Pause 0.3s
Resume 0.1s
...
~~~

Completed duration histograms will show clusters of tiny intervals. This can indicate:

- High/low watermarks are too close together.
- Queue size is oscillating.
- Health checks react too sensitively to a single error.
- Multiple components control the same container without a coordinator.
- Container sampling desynchronizes requested and effective states.

Mitigations:

- Two-threshold hysteresis.
- Bounded minimum pause duration.
- Consecutive-success threshold before resuming.
- Appropriate exponential recovery/backoff.
- Coordinate active reasons instead of letting multiple callers invoke resume.
- Monitor `pause_transition_count` and completed pause duration p50/p95.

Do not set minimum pause so long that it breaches SLOs when downstream recovers early.

## 29. Metric cardinality and ownership

A dashboard might want labels:

~~~text
listener_id
consumer_group
topic
partition
pod
reason
exception_class
event_id
customer_id
~~~

However, `event_id` and `customer_id` have very high cardinality; feeding them directly into Micrometer/Prometheus can cause storage/indexing costs to grow uncontrollably.

Recommendations:

- Aggregate metrics by listener, topic, group, reason, and instance.
- Per-partition metrics only when partition counts and metric retention budgets allow.
- Bound `exception_class` to a known taxonomy.
- Keep `event_id`, correlation IDs, and command IDs in logs/traces.
- Remove or expire dynamic per-partition meters when assignments are revoked.
- Define clear ownership of who can resume manual pauses.

If the system needs long-term auditing of a paused partition across multiple pods, persist pause events with UTC timestamps into durable storage rather than forcing every raw event into timeseries metrics.

## 30. Example dashboard for a listener

A "Kafka Pause & Backpressure" dashboard can organize blocks as follows:

**Instantaneous state**

- Listener running / pause requested / effective paused.
- Number of paused child consumers.
- Paused partitions / assigned partitions.
- Pause reason and owner.
- Current pause age, current resume-request latency.

**Load and impact**

- Consumer lag per partition.
- Oldest unprocessed record age.
- Producer ingress rate.
- Listener processing throughput.
- Downstream queue depth and connection pool usage.

**Control quality**

- Pause transitions per minute.
- Completed pause duration p50/p95/p99.
- Pause requested-to-effective latency.
- Resume requested-to-effective latency.
- Pause ratio over 1 hour / 24 hours.
- Backlog catch-up time after resume.

**Health and lifecycle**

- Consumer assignments/rebalances.
- Container stop/start events.
- Retry/backoff/DLT activity.
- Pod restarts, OOMKills, or forced terminations.

Never build a dashboard containing only a `paused.active` gauge. It cannot explain **why** it paused, **how long**, or **when** intervention is required.

## 31. Alerting by duration and impact severity

Alerts should have clear conditions:

| Alert | Suggested condition | Purpose |
|---|---|---|
| `LongEffectivePause` | Effective pause age exceeds SLO | Detect held containers/partitions |
| `ResumeStuck` | Resume requested while effective paused stays true too long | Detect unapplied resume |
| `PauseRequestStuck` | Pause requested while effective state stays unchanged too long | Detect blocked listener/poll |
| `HighPausedPartitionRatio` | Paused partition ratio exceeds threshold | Detect loss of consumption capacity |
| `PauseLagCritical` | Paused while lag and oldest age breach SLO | Alert on data freshness impact |
| `PauseFlapping` | Many transitions with short durations | Detect oscillating policies |
| `PausedNearRetention` | Oldest record age nearing Kafka retention | Protect replay opportunity |
| `PausedAfterRecovery` | Downstream healthy yet consumer stays unresumed | Detect stale pause state |

Illustrative Prometheus query **for demonstration only**, assuming application-exported metric names:

~~~promql
max by (listener_id) (
  app_kafka_pause_current_seconds
) > 300
~~~

A good alert includes context:

- Affected listener/group/topic/instance.
- Paused age and oldest record age.
- Pause reason and requesting actor/automation.
- Links to dashboards and logs/traces.
- Remediation runbook.

Do not page on-call during approved planned maintenance pauses still within expected windows; use silences/windows or separate alert rules while still tracking duration to catch overruns.

## 32. Observing via Kafka CLI

Kafka CLI cannot directly see the **Spring Kafka paused** state of a listener container. However, it helps observe the impact on consumer group lag and offsets.

Example:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --describe \
  --group orders-worker
~~~

Output might show:

~~~text
TOPIC          PARTITION CURRENT-OFFSET LOG-END-OFFSET LAG
orders.events  0         1200           1210           10
orders.events  1         500            1250           750
orders.events  2         1180           1181           1
~~~

If partition 1 is paused, a lag of 750 aligns with stalled progress on that partition. Still, this output **does not prove** Spring Kafka paused partition 1; correlate with container state, application events/logs, and metrics.

Notes:

- `CURRENT-OFFSET` is typically the consumer group's next committed offset.
- `LOG-END-OFFSET` is the log end position reported by CLI/broker.
- `LAG` is an offset delta, not elapsed time.
- With `read_committed`, LSO can make readable offset bounds differ from LEO.

For paused age, the CLI cannot replace application metrics or a pause-event audit log.

## 33. Runbook: paused too long even though downstream is healthy

### Step 1: Confirm requested vs. effective

Read `isPauseRequested()`, `isConsumerPaused()`, and partition-specific flags. Verify the exact listener ID, whether the container is running, and current assignments.

### Step 2: Identify reason and owner

Locate `pauseRequestedAt`, reason, caller, incident ID, and resume condition. Is a manual maintenance reason still active? Is a circuit open, queue high, or rate limit active?

### Step 3: Check the resume controller

- Has the health check genuinely reported healthy?
- Has the low watermark been reached?
- Did `PauseCoordinator`'s scheduler or consumer fail?
- Is another pause reason still active?
- Is there a mismatch where `requested=false` yet `effective=true`?

### Step 4: Check lifecycle and assignments

- Was the listener stopped?
- Was the partition revoked/reassigned during that window?
- Do metrics belong to an old pod?
- Are static memberships or rebalances in progress?

### Step 5: Controlled resume

Resume only when the dependency and downstream capacity can accept load. With large backlogs, ramp concurrency or reopen partitions selectively, monitoring queues/latency to avoid thundering herds.

### Step 6: Verify recovery

Effective paused age must end, completed duration must record, `records-consumed-rate` and processing successes must rise, and lag/oldest age must drop. Never treat the resume API returning as incident resolution if the consumer is still not processing new records.

## 34. Runbook: pause request takes too long to take effect

Symptom: `requested=true` for a long time while `effective=false` and ingress keeps running.

Check:

1. Is the container processing a large poll batch?
2. Is the listener blocked on database/HTTP calls or locks?
3. What are `max.poll.records`, batch listener settings, and concurrency?
4. Are GC pauses or CPU starvation occurring?
5. Is `pauseImmediate` configured appropriately in the running Spring Kafka version?
6. Is the consumer thread sitting in retry/backoff?
7. Is the container actually running with the right listener ID?

Remediation focuses on shrinking non-preemptible work per poll, setting dependency timeouts, and using the proper container API. Never call `KafkaConsumer.pause` directly from an admin thread to force state transition, because `KafkaConsumer` is not thread-safe in that manner.

## 35. Runbook: paused and consumer lag climbs rapidly

### Step 1: Scope the impact

- How many partitions are paused?
- Where are lag and oldest record age highest?
- What is the current topic ingress rate?
- Is the pause manual or automatic backpressure?

### Step 2: Inspect downstream

- Database connection pools/locks and query latency.
- HTTP service error rates, rate limits, circuit breakers.
- Executor queue depth and worker throughput.
- Pod CPU/memory/throttling.

### Step 3: Estimate catch-up capability

~~~text
Net drain rate = Processing rate - Incoming rate

If net drain rate <= 0:
  Backlog cannot shrink steadily

If net drain rate > 0:
  ETA ≈ Backlog / Net drain rate
~~~

Use a sufficiently wide observation window to smooth instantaneous fluctuations, especially right after resume.

### Step 4: Protect data

- Compare oldest record age against topic retention.
- Never commit offsets for unprocessed records.
- Assess whether capacity must be added or ingress throttled.
- Watch DLT/retries if the consumer resumes into continuously failing records.

### Step 5: Recover and monitor

Resume step-by-step once downstream is healthy. Monitor lag, `records-consumed-rate`, queue depth, error rates, and pause flapping. If lag does not fall after resume, the bottleneck may no longer be pause, but throughput or poison records.

## 36. Testing pause duration measurement

A pause-tracking implementation should test both the tracker's storage/timing semantics and the listener container's integration behavior.

### 36.1. Single pause then resume

- Issue pause.
- Wait for actual paused state.
- Stay paused for a known interval.
- Issue resume.
- Assert completed duration approximates actual pause interval within test clock/scheduling tolerances.

### 36.2. Repeated pause does not reset the timer

- Call pause multiple times while already paused.
- Verify only one active interval exists.
- Duration continues climbing from the first transition.
- Completed count increments exactly once upon resume.

### 36.3. Pause requested before effective

- Keep the listener processing a slow record.
- Call pause.
- Assert `requested=true` before `effective=true`.
- Measure application latency separately without folding it into effective duration.

### 36.4. Very short pause/resume

- Create an interval shorter than the sampling period.
- Verify event-driven instrumentation captures it when precision is required.
- With scheduled samplers, accept missed short pulses or raise sampling frequency appropriately.

### 36.5. Partition revoked while paused

- Pause a partition.
- Trigger a rebalance in the test cluster.
- Verify the old interval closes with `endReason=REVOKED/LOST`.
- Verify no stale gauge remains on the old owner.
- Verify desired state reconciles on the new owner if policy requires.

### 36.6. Container stopped while paused

- Pause the container.
- Stop the listener.
- Do not count the entire stopped duration as an active pause interval.
- Measure shutdown separately.
- Start again and verify the tracker does not retain stale state.

### 36.7. Concurrent consumers and partition pause

- Configure concurrency greater than 1.
- Pause one partition.
- Verify container-wide metrics do not report every partition paused.
- Record per-partition duration independently.

### 36.8. Backpressure recovery

- Use a test queue with high/low watermarks.
- Trigger pause at high watermark.
- Drain queue past low watermark and assert resume.
- Verify zero flapping, time-to-first-success, and backlog drain.

## 37. Common design mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Measuring from calling `pause()` and labeling it effective duration | Includes application wait latency | Separate `requestedAt` and `effectivePausedAt` |
| Exposing only a `paused.active` boolean | Cannot tell how long the pause has lasted | Add `currentPausedSeconds` and completed duration |
| Using only a `Timer` for completed intervals | Hung ongoing pauses stay uncounted | Add a `current pause age` gauge |
| Using `System.currentTimeMillis` for all durations | Clock adjustments distort measurements | Use `nanoTime` for elapsed, UTC for audits |
| Failing to close intervals on revoke/stop | Gauges climb infinitely, stale alerts | Close on lifecycle reasons |
| Repeated `pause()` resets start timestamp | Artificially small paused age displayed | Record start only on state transition |
| Summing 3 paused partitions as 30s wall-clock for 10s real time | Misinterprets total paused duration | Distinguish partition-seconds from elapsed wall time |
| Single parent gauge hides a paused partition | Hot/stuck partition goes unnoticed | Per-partition metrics or paused partition counts |
| Using lag to guess paused state | Lag has many other causes | Combine Spring container flags/events |
| Manual resume overrides maintenance reason | Unintended premature resume | Reference-count/track active reasons set |
| Auto-resuming merely on timeout expiry | Downstream still broken, retry storm | Deadlines alert; resume checks health |
| Metric tags containing `eventId`/`customerId` | Cardinality explosion | Bounded labels; keep IDs in logs/traces |
| Ignoring retention | Long pauses let records expire | Alert when oldest age nears retention |
| Watching pause time without catch-up | Misjudges recovery completion | Monitor backlog drain after resume |
| Not testing rebalance while paused | Stale state or new owner breaks policy | Test revoke/assign and reconciliation |

## 38. Production checklist

Before shipping pause-duration tracking to production:

1. Are **pause requested** and **pause effective** clearly defined?
2. Do metrics separate listener-level, child-consumer, and partition-level where needed?
3. Does the tracker use a monotonic clock for elapsed durations and UTC timestamps for incidents?
4. Are repeated pause/resume calls deduplicated into state transitions?
5. Is current paused age exported even before an interval ends?
6. Are completed durations captured with a `Timer`/histogram using bounded labels?
7. Are requested-to-effective pause and resume latencies tracked?
8. Does every pause carry an explicit reason/owner or requester source?
9. Do multiple pause sources use a coordinator to prevent premature resume?
10. Do partition revoke/lost, container stop, and shutdown close telemetry intervals with proper reasons?
11. After rebalances, is desired pause state reconciled on the new owner where needed?
12. Does a dashboard combine paused age, lag, oldest record age, and downstream health?
13. Do long-pause thresholds account for SLOs, Kafka retention, and ingress rate?
14. Does auto-resume verify low watermarks and dependency health to prevent retry storms?
15. Do metric labels avoid high-cardinality event/customer IDs?
16. Is pause ratio clearly defined as container-level vs. partition-seconds?
17. Are time-to-first-success and post-resume catch-up time tracked?
18. Have requested-vs-effective, repeated commands, rebalances, stops, concurrency, and forced shutdowns been tested?
19. Do runbooks exist for prolonged pauses, unapplied resumes, and rising lag?
20. Does operations know when pause is safe versus when to stop/rebalance or adjust capacity?

**Conclusion:** Tracking paused duration in Spring Kafka requires more than a boolean flag. Measure from **effective pause** to **effective resume**, while separating request-application latency, recording completed intervals, and distinguishing per-partition pauses and operational reasons. Combining duration with consumer lag, record age, retention, downstream health, and rebalance lifecycles catches both dangerous failure modes: **intentional pauses that were forgotten** and **requested resumes where the consumer has not actually resumed**. A reliable pipeline must measure how long it paused, why it paused, and how effectively it catches up once recovered.
