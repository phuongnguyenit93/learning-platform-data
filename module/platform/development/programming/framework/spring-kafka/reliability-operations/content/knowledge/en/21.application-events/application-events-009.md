# ListenerContainerIdleEvent

## 1. What is ListenerContainerIdleEvent?

In Spring Kafka, `ListenerContainerIdleEvent` is an **application event** published by the listener container when the container has not received any records to deliver to the listener within a duration configured by `idleEventInterval`. This event helps the application detect the **idle** state of a Kafka consumption stream without manually building a loop tracking the last record receipt timestamp.

An intuitive example:

~~~text
Kafka topic orders              Spring Kafka listener container
      |                                      |
      | --- record A ---------------------> @KafkaListener(A)
      | --- record B ---------------------> @KafkaListener(B)
      |                                      |
      |        No new records                |
      |        for 30 seconds                |
      |                                      v
      |                        ListenerContainerIdleEvent
      |                                      |
      |                               @EventListener
      |                                      |
      |                        Log / metric / state
~~~

The event is published **inside the Spring application's JVM** through the Spring application events mechanism. It is not a record published by a producer into Kafka, nor a message sent over a separate topic.

Key points:

- **Idle** describes the container receiving no records for the configured threshold; it **does not by itself prove** that the Kafka broker or producer is failing.
- The event reflects **listener container** activity, not the result of directly checking business progress in a database.
- The container can still keep calling `poll()` and maintaining consumer group membership while idle.
- When records arrive again after an idle period, Spring Kafka can publish `ListenerContainerNoLongerIdleEvent` to signal that the container is no longer idle.
- By default, the application must **enable the idle interval** to receive these notifications; do not assume every container emits idle events without configuration.

In Spring Kafka Reliability Operations, `ListenerContainerIdleEvent` is an **observational signal** that must be combined with consumer lag, assignment, producer throughput, and application state before interpreting it as an alert.

## 2. Production goals for using idle events

Idle events are useful when answering these questions:

1. Has the consumer been receiving no data for longer than expected?
2. Is a topic expected to carry continuous events silent because upstream stopped publishing or for another reason?
3. Has the consumer resumed receiving records after a pause?
4. Do we need to update UI/dashboard status, emit metrics, or mark a temporary quiet business period?
5. Is one partition silent while other partitions still have traffic?

For example, the `fraud-detection` service expects payment events at least every few minutes. When the listener container stays idle past the threshold, the application can record a metric for the alerting system to analyze further.

Conversely, a consumer reading a topic that only receives events when users change passwords can stay idle for hours and still be completely normal. An idle event in that case is a state signal, not an incident.

Set expectations from **workload characteristics**. A 30-second threshold suits a continuous event stream yet can create noise for a stream producing only a few events per day.

## 3. Related events in Spring Kafka

| Event | General meaning | When to use |
|---|---|---|
| `ListenerContainerIdleEvent` | Container has received no records for the idle threshold | Record silent periods and observe data-stream liveness |
| `ListenerContainerNoLongerIdleEvent` | Container receives records again after idle state | End idle state, update metrics/status |
| `ListenerContainerPartitionIdleEvent` | A partition has no records for its dedicated tracking threshold | Find partitions with little/no traffic even while others stay active |
| `ListenerContainerPartitionNoLongerIdleEvent` | Partition receives records again after being idle | Record partition resuming activity |
| `ConsumerPausedEvent` | Container applied pause on partitions | Distinguish intentional pause from streams without data |
| `ConsumerResumedEvent` | Container actually resumed partitions | Know that the resume control action took effect |
| `NonResponsiveConsumerEvent` | Poll unresponsive under corresponding monitoring criteria | Investigate blocked consumer poll, distinct from idle due to no records |
| `ConsumerStoppedEvent` / `ContainerStoppedEvent` | Consumer/container ended lifecycle | Do not interpret stopped as a normal idle state |

Do not treat `ListenerContainerIdleEvent`, `ConsumerPausedEvent`, and `NonResponsiveConsumerEvent` as three names for the same incident:

- **Idle:** consumer/container is still operating yet received no records within the idle threshold.
- **Paused:** a pause request or state is active to temporarily suspend fetch/delivery.
- **Non-responsive:** consumer is not meeting poll/monitoring loop expectations; requires separate investigation.

## 4. Conditions for publishing ListenerContainerIdleEvent

### 4.1. idleEventInterval

The `idleEventInterval` property specifies the duration in milliseconds for the container to be considered idle.

Example:

~~~java
factory.getContainerProperties()
    .setIdleEventInterval(30_000L);
~~~

When the container receives no records for the configured interval, Spring Kafka can publish `ListenerContainerIdleEvent`. If the state stays idle, events may continue being published at configured intervals rather than necessarily firing only once for the entire idle period.

Therefore, a prolonged absence of records can generate **multiple idle events**. Event consumers should not fire a new email/alert for the same incident on every received event without deduplication or rate limiting.

### 4.2. The threshold is not an absolute precision clock

Idle detection is checked via listener container activity and the poll loop. Do not assume events appear down to the exact millisecond of `idleEventInterval`, because actual timing depends on poll timing, scheduling, listener processing, JVM load, and Spring Kafka version.

For example, setting a 30-second interval does not mean an event is guaranteed to appear at exactly 30,000 ms from the last record on the business application's wall clock.

### 4.3. Before the first record

A newly started container on a topic with no data yet can also become idle. This state differs from a container that processed many records and then went temporarily quiet. When analyzing incidents, know the startup and assignment timestamps, because a newly started listener may still be waiting for its first data or partition assignment.

If a Spring Kafka version provides a property tuning how idle is measured before the first record, use the exact version's API; do not assume initial idle time always starts from the same point across all releases.

### 4.4. Consumer without assignment

A container not yet assigned partitions or waiting on a rebalance may receive no records. When seeing idle, check assignment before concluding the topic has no data.

The same symptom "listener not invoked" can come from:

- Topic has no new records.
- Consumer does not have partition assignments yet.
- More consumers than partitions, leaving some consumers idle.
- Container is paused.
- Consumer/group is rebalancing.
- Consumer was stopped or misconfigured.
- Records blocked by isolation or offset/retention semantics.

An idle event is a starting point for investigation, not a complete diagnosis.

## 5. Configuration with Spring Boot application.yml

A Spring Boot application can declare the idle event interval in listener properties when supported by the corresponding version:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: inventory-projection
      enable-auto-commit: false
      auto-offset-reset: earliest
    listener:
      type: single
      ack-mode: record
      idle-event-interval: 30s
~~~

Meaning of key settings:

- `idle-event-interval: 30s`: instructs the container to publish idle events when no records arrive for a 30-second interval.
- `type: single`: example using a single-record listener rather than a batch listener.
- `ack-mode: record`: commits offsets upon successful processing of each record in the appropriate mode.
- `enable-auto-commit: false`: delegates commits to the Spring Kafka container instead of consumer timer-based auto-commit.

Verify property names and binding against the running Spring Boot release. If the application manually creates a `ConcurrentKafkaListenerContainerFactory` and bypasses Boot's configuration, that listener factory may not inherit `idle-event-interval` from `application.yml`.

**Note:** Idle events do not depend on whether the consumer has committed offsets. A listener that receives a record and writes to the database successfully can take the container out of idle even if the subsequent offset commit fails; commit failures must be tracked by other signals.

## 6. Explicit configuration on container factory

If you need to guarantee a specific listener factory emits idle events, configure `ContainerProperties` in Java:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, InventoryChanged>
            inventoryKafkaListenerContainerFactory(
                ConsumerFactory<String, InventoryChanged> consumerFactory
            ) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, InventoryChanged>();

        factory.setConsumerFactory(consumerFactory);

        // Publish container idle event with a 30-second threshold.
        factory.getContainerProperties()
            .setIdleEventInterval(30_000L);

        return factory;
    }
}
~~~

The listener must use the newly created factory:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class InventoryConsumer {

    @KafkaListener(
        id = "inventory-listener",
        topics = "inventory.changed",
        groupId = "inventory-projection",
        containerFactory = "inventoryKafkaListenerContainerFactory"
    )
    public void onInventoryChanged(InventoryChanged event) {
        inventoryService.applyIdempotently(event);
    }
}
~~~

`InventoryChanged` and `inventoryService` are illustrative domain code supplied by the project. Appropriate deserializers/converters must be configured so the consumer can actually construct payload objects.

If a project has multiple factories, only the factory configured with an idle interval and referenced by an endpoint exhibits the expected behavior. Setting an idle interval on one factory does not automatically apply to all other listeners.

### 6.1. Configuring intervals per workload

Different thresholds can be chosen:

~~~text
inventory-listener:  30 seconds
payments-listener:   60 seconds
audit-listener:      10 minutes
user-login-listener: may not need idle events
~~~

Do not set a single overly low threshold across all topics. Topics with naturally low traffic can generate many unhelpful events.

## 7. Receiving ListenerContainerIdleEvent with @EventListener

A Spring `ApplicationContext` can receive events via the `@EventListener` annotation.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class InventoryIdleEventLogger {

    private static final Logger log =
        LoggerFactory.getLogger(InventoryIdleEventLogger.class);

    @EventListener
    public void onContainerIdle(ListenerContainerIdleEvent event) {
        log.warn(
            "Kafka listener idle: listenerId={}, idleMs={}, partitions={}",
            event.getListenerId(),
            event.getIdleTime(),
            event.getTopicPartitions()
        );
    }
}
~~~

The snippet uses common accessors on `ListenerContainerIdleEvent`. If using another Spring Kafka version, check the corresponding class API before adding logic that depends on newer metadata.

This event allows logging:

- Listener/container ID to trace the endpoint.
- `idleTime` to see the reported idle duration.
- Assigned partitions associated with the container emitting the event.
- Timestamp, application instance, and correlation information if supported by the logging system.

Log structured fields rather than full record payloads; when idle, there is typically no current record to log anyway.

### 7.1. @EventListener does not create an extra Kafka consumer

A bean receiving `ListenerContainerIdleEvent` does not join a new consumer group and does not increase partition consumption. It only receives Spring application events from listener containers within the same `ApplicationContext`.

Consequently, event listeners can serve metrics/diagnostics without affecting the processing group's Kafka offsets.

### 7.2. Per-JVM scope

If the application runs three pods, each pod has its own Spring `ApplicationContext`. Pod A's `@EventListener` bean only receives Spring application events published inside Pod A, not events from Pod B or Pod C.

To obtain whole-consumer-group status, aggregate logs/metrics/traces across all instances. Kafka does not propagate `ListenerContainerIdleEvent` to other group members.

## 8. Distinguishing ListenerContainerNoLongerIdleEvent

After a container has been idle and subsequently receives records again, Spring Kafka can publish `ListenerContainerNoLongerIdleEvent`. This is a useful signal to close an idle period.

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.kafka.event.ListenerContainerNoLongerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class InventoryActivityEvents {

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.info(
            "Listener became/stays idle: listenerId={}, idleMs={}",
            event.getListenerId(),
            event.getIdleTime()
        );
    }

    @EventListener
    public void onActive(ListenerContainerNoLongerIdleEvent event) {
        log.info(
            "Listener received records after idle: listenerId={}",
            event.getListenerId()
        );
    }
}
~~~

Because idle events can repeat within the same period, handle events as state transitions:

~~~text
RUNNING / RECEIVING
      |
      | No records for threshold
      v
IDLE  -- more idle events may emit -->
      |
      | Records reappear
      v
ACTIVE / NO_LONGER_IDLE
~~~

Do not assume every `ListenerContainerIdleEvent` will always be followed by an exact matching `NoLongerIdle` event. The container may be stopped, lose assignment, restart, or have its Spring context shut down while idle. Dashboards should factor in container lifecycle and startup events too.

## 9. Container-level idle differs from partition-level idle

A listener container may handle multiple partitions, especially when one consumer is assigned several partitions.

~~~text
inventory.changed
  P0 -> 100 records/minute
  P1 ->   0 records/minute
  P2 ->  20 records/minute

Consumer C owns P0, P1, P2
~~~

Consumer C keeps receiving records from P0/P2, so a container idle event may **not** appear even though P1 has been silent for a long time.

If you need to know whether each individual partition has data, use **partition idle events** in Spring Kafka versions supporting them.

~~~java
factory.getContainerProperties()
    .setIdleEventInterval(30_000L);

factory.getContainerProperties()
    .setIdlePartitionEventInterval(60_000L);
~~~

Meaning:

- `idleEventInterval` checks whether the container receives no records.
- `idlePartitionEventInterval` checks how long no records arrive from **each assigned partition** per container mechanics.

The two thresholds can differ because their objectives differ.

### 9.1. When should you observe partition idle?

- Topic traffic is partitioned by tenant/key and one partition may abnormally lack events.
- The system needs to check partition-local SLAs.
- A producer writes only to a subset of partitions due to a partitioner bug.
- You want to detect a partition whose log end offset grows while the consumer makes no progress.
- You need to distinguish "whole consumer is idle" from "only one partition receives no records."

If a topic has partitions with naturally low or zero traffic, partition idle events can occur normally. Do not trigger high-severity alerts for all partition idle events without checking expected traffic.

## 10. Receiving partition idle events

Spring Kafka provides specialized events such as `ListenerContainerPartitionIdleEvent` and `ListenerContainerPartitionNoLongerIdleEvent` in supported versions.

Example logging only the event object and container context:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerPartitionIdleEvent;
import org.springframework.kafka.event.ListenerContainerPartitionNoLongerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class PartitionIdleEventLogger {

    @EventListener
    public void onPartitionIdle(ListenerContainerPartitionIdleEvent event) {
        log.warn("Kafka partition idle: {}", event);
    }

    @EventListener
    public void onPartitionActive(
        ListenerContainerPartitionNoLongerIdleEvent event
    ) {
        log.info("Kafka partition active after idle: {}", event);
    }
}
~~~

This is a standalone example; the `log` logger must be declared with SLF4J as in earlier examples. When exporting exact topic-partitions to metrics, use accessors provided by your running Spring Kafka version.

Some versions or configurations may only track container-level events; verify your dependency before relying on partition events. Do not substitute a `ListenerContainerIdleEvent` for partition events and guess which partition lacks data.

## 11. Idle does not mean the consumer is paused

When an application proactively applies backpressure with `container.pause()`, paused partitions stop delivering records to the listener. Depending on poll loop and version, receiving no records can coincide with idle detection.

Therefore, upon seeing an idle event, ask whether the container is currently paused.

~~~text
No records delivered
       |
       +-- Topic genuinely has no data?
       |
       +-- Container is paused?
       |
       +-- No assignment yet?
       |
       +-- Consumer is rebalancing?
       |
       +-- Producer/upstream stopped?
       |
       +-- Consumer error or not polling?
~~~

Spring Kafka provides APIs such as:

- `isPauseRequested()`: a pause request has been issued.
- `isConsumerPaused()`: pause has actually taken effect per container state.
- `ConsumerPausedEvent` and `ConsumerResumedEvent`: track when pause/resume actually take effect.

Use these signals to separate intentional pauses from missing data. Do not automatically restart the consumer solely because an idle event arrived while a backpressure controller is intentionally pausing it.

## 12. Idle does not mean the consumer is dead

A consumer with no new data can still call `poll()` normally and maintain heartbeats with the group coordinator.

~~~text
KafkaConsumer.poll()
      |
      +-- No records
      |
      +-- Container continues operating
      |
      +-- Heartbeat / group membership may still be healthy
      |
      v
After idle interval: ListenerContainerIdleEvent
~~~

This differs from:

- `session.timeout.ms`: broker misses enough heartbeats and may evict the member from the group.
- `max.poll.interval.ms`: consumer fails to call poll in time because processing took too long.
- `NonResponsiveConsumerEvent`: Spring Kafka detects poll appears unresponsive per its dedicated monitor.

A listener taking a long time on business logic so the consumer cannot poll on schedule may **fail to produce idle events on time**, because the container has not returned to the idle check point. Do not use the absence of idle events as proof the consumer is healthy.

### 12.1. Idle and lag are not equivalent

If the topic has no new records and the consumer caught up to log end, lag can be 0 and idle is normal.

If the consumer holds no partitions or is paused while producers keep writing, lag can grow. An idle event in this case must be analyzed alongside lag and assignment to determine whether an issue exists.

| Idle event | Consumer lag | Possible interpretations |
|---|---|---|
| Yes | 0 | Stream may be healthy with no new data |
| Yes | Increasing | May be paused, unprocessed, lacking assignment, or read error |
| No | 0 | Consumer may be processing or hasn't reached idle threshold |
| No | Increasing | Consumer may be processing slowly, stuck in poll, or idle threshold not reached |

This table only guides investigation. No single pair of signals identifies the root cause by itself.

## 13. IdleEvent with concurrency greater than one

When configuring `ConcurrentMessageListenerContainer` with `concurrency > 1`, Spring Kafka creates multiple child consumers. Each child can own different partitions and maintain its own idle state.

Example:

~~~text
Topic orders: P0, P1, P2, P3

Concurrency = 2

Child consumer 0 -> P0, P1  (receiving records)
Child consumer 1 -> P2, P3  (no records)
~~~

Child 1 can publish idle events even while child 0 processes normally. Therefore:

- Do not treat an idle event from **one child consumer** as the entire service receiving no data.
- When logging, include the listener/container ID and assigned partitions.
- When building service-wide dashboards, clarify whether you are tracking "one child idle," "all children idle," or "topic has no data."
- If concurrency exceeds partition count, some consumers hold no assignment so silence can be a configuration consequence rather than an incident.

Depending on version, the listener/container ID includes a suffix denoting the child instance. Do not hard-code suffix concatenation logic without checking the actual `getListenerId()` value in your runtime environment.

## 14. On which thread does the event callback run?

Under standard Spring application event multicaster settings, Spring Kafka publishes events on the container/consumer thread path, and a synchronous `@EventListener` can run directly on that thread.

This is a critical operational detail: **a slow event handler can slow down the consumer**, even if the event is only for monitoring.

### 14.1. Do

~~~java
@EventListener
public void onIdle(ListenerContainerIdleEvent event) {
    log.info(
        "Idle event: listenerId={}, idleMs={}",
        event.getListenerId(),
        event.getIdleTime()
    );

    idleEventCounter.increment();
}
~~~

For example, `idleEventCounter` is an application-created counter. The callback only writes logs and updates lightweight metrics.

### 14.2. Do not

~~~java
@EventListener
public void onIdle(ListenerContainerIdleEvent event) {
    externalHttpClient.waitForReport(120_000L);
    database.rebuildLargeProjection();
}
~~~

If the handler runs synchronously on the consumer thread, these two operations can block the poll loop, increasing the risk of `max.poll.interval.ms` violations, rebalances, and lag.

### 14.3. Caution with Async multicaster

If the application configures an asynchronous `ApplicationEventMulticaster` or `@Async` on the event listener, the callback can run on a different thread. In that case, never arbitrarily call `KafkaConsumer` methods from event data or another thread, because `KafkaConsumer` is not thread-safe.

If you need pause/resume operations, use container-level APIs. If you need to seek a partition, follow the consumer-thread contract and Spring Kafka-supported mechanisms. Do not turn an async event callback into a place calling `consumer.seek()` directly.

### 14.4. Stopping container from idle event

Some applications want to stop a listener when idle for too long. Do not call a synchronous `stop()` that waits for the consumer thread to finish directly from a callback running on that very consumer thread: it can cause deadlocks or lifecycle hangs.

Send lifecycle management requests to a scheduler/control thread with a deadline, or use non-blocking lifecycle APIs appropriate for your version. If you only want to reduce workload, consider pause instead of stop, keeping in mind pause changes record-delivery behavior and needs a clear resume condition.

## 15. Building an idle state tracker

A practical usage is storing **observed idle** state per listener for dashboard display.

~~~text
Listener inventory-listener

ACTIVE
  |
  | Receive ListenerContainerIdleEvent
  v
IDLE
  |
  | Subsequent idle events continue arriving
  | Only update timestamp, do not open new incident
  |
  | Receive ListenerContainerNoLongerIdleEvent
  v
ACTIVE
~~~

### 15.1. Idempotent event handling

Because idle events can repeat, code should handle state transitions idempotently:

- First ACTIVE → IDLE: record start timestamp of an idle period.
- Subsequent IDLE → IDLE: update last-seen timestamp or metric; do not create duplicate alerts.
- IDLE → ACTIVE: record end and duration of idle period.
- If container stops/restarts: finish or transition state to STOPPED; do not leave dashboards stuck on IDLE forever.

### 15.2. Simple state tracker example

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.kafka.event.ListenerContainerNoLongerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class ListenerIdleTracker {

    private final ConcurrentMap<String, AtomicBoolean> idleByListener =
        new ConcurrentHashMap<>();

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        AtomicBoolean state = idleByListener.computeIfAbsent(
            event.getListenerId(),
            ignored -> new AtomicBoolean(false)
        );

        if (state.compareAndSet(false, true)) {
            log.warn(
                "Listener entered idle state: {}",
                event.getListenerId()
            );
        }
    }

    @EventListener
    public void onActive(ListenerContainerNoLongerIdleEvent event) {
        AtomicBoolean state = idleByListener.computeIfAbsent(
            event.getListenerId(),
            ignored -> new AtomicBoolean(false)
        );

        if (state.compareAndSet(true, false)) {
            log.info(
                "Listener left idle state: {}",
                event.getListenerId()
            );
        }
    }
}
~~~

This example only demonstrates state transitions; the `log` variable must be declared with SLF4J as in previous examples. It does not yet fully handle container stopping, startup, rebalance, child listener identity, `ApplicationContext` shutdown, or multi-instance aggregation.

A production tracker should include timestamps, lifecycle state, pod identity, and expiry/cleanup for stale keys. If switching event delivery to asynchronous, control for out-of-order events.

## 16. Using idle events to alert when upstream stops publishing

A typical use case:

~~~text
Upstream order-service
      |
      v
Kafka topic orders.created
      |
      v
Spring Kafka orders-projection
      |
      v
ListenerContainerIdleEvent
      |
      v
Metric/alert: "No order events for too long"
~~~

Only use idle events to raise alerts when there is **an explicit traffic contract**. For example:

- Daytime must have at least one order within 5 minutes.
- Weekends may have no orders for 30 minutes.
- Heartbeat streams must have one event every minute.
- Some topics are only published during nightly batch jobs.

An alert may require additional conditions:

1. Container is running and has assigned partitions.
2. Not paused by a backpressure policy.
3. The topic is actually expected to have data in the current time window.
4. Producer rate or source queue depth shows data should be appearing.
5. Consumer lag and broker health do not point to another error.
6. Idle duration has exceeded SLO with a confirmation window to avoid noisy alerts.

If the source topic has naturally uneven traffic, instead of paging immediately, treat idle as a diagnostic event or dashboard state.

## 17. When idle yet consumer lag is increasing

This situation requires careful investigation because the topic has unread data while the listener is not receiving records.

Possibilities:

- Container is paused due to backpressure.
- Consumer lacks assignment on the lagging partition.
- Group just rebalanced and has not stabilized yet.
- Consumer is hitting deserialization errors before messages are dispatched through the normal path.
- Consumer is blocked and not polling on cadence.
- Records are not yet visible under `read_committed` due to an open transaction.
- Wrong topic/partition or group ID is being observed.
- Lag-monitoring system has delay or misaligned timestamps.

Diagnostic workflow:

1. Confirm listener container is running.
2. Check group ID, topic subscription, and assignments.
3. Check paused state and `ConsumerPausedEvent` occurrences.
4. Read Kafka consumer client logs and exceptions.
5. Check poll latency, `max.poll.interval.ms`, and heartbeats.
6. Cross-check log end offset, committed offset, and last stable offset when using transactions.
7. Check deserialization errors and error handlers.
8. Cross-check producer throughput and topic retention.

Do not use idle events to automatically reset consumer offsets, as that can skip or replay business data unintentionally.

## 18. When no idle event appears even though the topic has no data

Several causes:

- `idleEventInterval` was not configured or was set on a different factory.
- Listener container is not running or has not joined the group yet.
- Listener is executing a long operation and has not returned to the poll loop for idle evaluation.
- Event listener was registered in the wrong `ApplicationContext` or is not a Spring bean.
- Event filtering skips the corresponding listener/container ID.
- Occasional records arrive periodically enough to reset the idle clock.
- Spring Kafka version has different semantics for initial idle detection or per-partition tracking.
- Another concurrent child is receiving records, so the overall container is not idle as assumed.

An investigation path:

~~~text
Check idle-event-interval config
       |
       v
Verify correct listener container factory
       |
       v
Verify container RUNNING, has assignment
       |
       v
Verify @EventListener is a Spring bean
       |
       v
Observe poll/record traffic and event logs
       |
       v
Cross-check actual idle interval and version
~~~

Do not conclude an event was lost merely because a callback has not appeared at the exact threshold millisecond on a test clock.

## 19. Events and consumer group rebalances

When a consumer group rebalances, partition assignments can change. Consequently:

- A child consumer that used to receive many records may receive fewer or no partitions.
- Another child may receive the reassigned partitions and begin getting data.
- Pre-rebalance idle state may no longer accurately describe post-reassignment traffic.
- Partition metadata in an event reflects the assignment at the time the event was published.

If the application uses idle events to gauge topic health, **update calculations after assignment changes**. Do not permanently cache the partition set from the first idle event and treat it as the current assignment.

### 19.1. Idle differs from rebalance

Rebalances can temporarily leave a listener without records without being an independent idle problem. When idle events appear near deployment/scaling times, cross-check:

- Member join/leave events.
- Partition revoked/assigned/lost callbacks.
- Consumer group coordinator errors.
- Pod restarts and concurrency.
- Consumer lag per partition.

### 19.2. Stop/restart while idle

A container stopping while idle may not emit `ListenerContainerNoLongerIdleEvent`. Monitoring state should use lifecycle events or check container running state to transition from IDLE to STOPPED/UNKNOWN.

If the application restarts, the old in-memory tracker is lost. Centralized monitoring should treat each pod/process as a separate session, avoiding comparing state from an old instance with a new instance as if they were one continuous lifecycle.

## 20. Monitoring and metrics for idle events

Useful metrics:

| Signal | Meaning |
|---|---|
| Idle event count | How many times the container reported idle |
| Idle state gauge | Whether listener/child is currently idle or active |
| Idle duration | Duration of a continuous idle period |
| Time since last received record | Data-absence window per listener/partition |
| No-longer-idle event count | How many times the container received records again |
| Consumer lag | Unconsumed backlog |
| Partition assignment count | Shows whether consumer is assigned partitions |
| Consumer poll rate/latency | Verifies consumer is still polling |
| Heartbeat/rebalance events | Detects membership instability |
| Pause requested / observed | Distinguishes intentional backpressure |
| Producer rate | Evaluates whether upstream is producing events |
| Listener processing duration | Distinguishes idle from overly slow handlers |

Exact metric names depend on Kafka client, Spring Kafka, Micrometer, and application instrumentation. Do not assume Spring Kafka exports an `idle_state` metric by that name out of the box; you can build a tracker and expose a gauge yourself.

Use metric labels with bounded cardinality such as service, listener ID, topic, state, and environment. Do not use event IDs, record keys, or customer IDs as metric labels.

If dashboards display pause duration or idle duration, clearly state:

- Is idle measured at **container-level or partition-level**?
- Is duration measured from the first idle event or from the last record?
- Does it exclude intervals when the container was stopped/rebalancing?
- Is it aggregated across all pods or per single pod?

Without clear definitions, "consumer idle" charts are very easy to misinterpret.

## 21. Testing ListenerContainerIdleEvent

Test against a test Kafka broker/cluster or an integration environment with dedicated topics and consumer groups.

### 21.1. No-data test

1. Create a test topic and a listener container with a short `idleEventInterval`, such as 1–2 seconds.
2. Start the listener and wait until the container actually receives assignment.
3. Send no new records.
4. Use `CountDownLatch`, Awaitility, or an event-waiting mechanism with a timeout.
5. Verify `ListenerContainerIdleEvent` is received for the expected listener ID.
6. Inspect assigned partitions metadata and idle time.
7. Do not write tests relying on a single fixed `Thread.sleep()` assuming the event appears at the exact millisecond.

### 21.2. Resuming record receipt test

1. Wait for the container to enter idle state.
2. Have a producer send a valid record.
3. Verify `@KafkaListener` is invoked and processes successfully.
4. Observe `ListenerContainerNoLongerIdleEvent` in supported versions.
5. Verify the state tracker transitions from IDLE to ACTIVE.
6. Wait long enough without sending records and observe the container become idle again.

### 21.3. Multi-partition test

1. Create a topic with at least two partitions.
2. Send records continuously to P0.
3. Send no records to P1.
4. Enable `idlePartitionEventInterval`.
5. Verify partition P1 can report idle while the container still receives records from P0.
6. Send a record to P1 and observe the partition no-longer-idle event.
7. Verify dashboards do not mark the whole container idle just because P1 is idle.

### 21.4. Pause test

1. Ensure the listener has assignments and is receiving records.
2. Call `container.pause()`.
3. Observe `ConsumerPausedEvent` or `isConsumerPaused()`.
4. Wait long enough for idle detection to be evaluated.
5. If an idle event appears, verify the system does not raise a missing-producer-data alert when pause is intentional.
6. Resume and verify records continue being processed.

### 21.5. Lifecycle/rebalance test

1. Run two consumer members in the same group.
2. Record listener/container IDs and assignments.
3. Have one member leave the group in a controlled test manner.
4. Verify the state tracker updates when assignments change.
5. Stop an idle container; ensure dashboards do not keep the stale IDLE state forever.
6. Restart and verify events/state belong to the new process lifecycle.

## 22. Test code snippet with CountDownLatch

A simple way to avoid flaky tests is using a listener that receives idle events and counts down a latch:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class TestIdleEventProbe {

    private final CountDownLatch firstIdle =
        new CountDownLatch(1);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        if (event.getListenerId().startsWith("inventory-listener")) {
            firstIdle.countDown();
        }
    }

    public boolean awaitIdle() throws InterruptedException {
        return firstIdle.await(10, TimeUnit.SECONDS);
    }
}
~~~

In tests, you can inject the probe into `ApplicationContext` and assert that `awaitIdle()` returns true after the listener receives assignment. With concurrency, child consumer IDs may carry suffixes; prefix filtering is only an example, so verify exact IDs.

The probe above serves a single simple test run. If multiple tests share the same context, reset/recreate the latch per test round so an idle event from a previous test does not falsely pass the next test.

Do not call `awaitIdle()` on the consumer thread; the event callback should only call `countDown()` quickly.

## 23. Common operational mistakes

**Not configuring idleEventInterval yet expecting events:** the container may not emit idle events because the threshold is not enabled.

**Setting interval too low:** low-traffic topics generate excessive events and noisy logs.

**Treating idle as a dead Kafka broker:** the consumer may be healthy while the topic simply has no new data.

**Treating idle as synonymous with consumer paused:** pause is a control operation; idle is receiving no records for a threshold.

**Treating idle as synonymous with session timeout:** session timeout means the group coordinator lost heartbeats, not a listener lacking data.

**Treating idle events as offset committed:** idle does not guarantee commit progress or side-effect completion.

**Listening to one child and concluding the entire group is idle:** concurrent containers can have other active children.

**Measuring only container idle when partition idle is needed:** one partition can sit silent even while other partitions receive records.

**Calling KafkaConsumer from an async event handler:** violates thread-ownership rules and can cause unpredictable bugs.

**Using idle callbacks to run long HTTP/database calls:** can block the consumer thread and cause poll interval issues.

**Synchronously stopping the container on the consumer thread itself:** risks deadlocks or lifecycle hangs.

**Sending an alert on every idle event:** events can repeat within the same period; use state transitions/deduplication.

**Forgetting to distinguish pod/instance:** application events are JVM-scoped and require aggregation in monitoring.

**Not handling container stop/rebalance:** stale IDLE state can linger on dashboards even after the container stopped or partitions changed owners.

**Assuming a NoLongerIdle event must always appear:** stops, restarts, or reassignments can end the lifecycle without that event.

**Using idle events to automatically reset offsets:** risks skipping or replaying business data without business control.

## 24. Investigation workflow when a listener is abnormally idle

A practical runbook:

1. Identify environment, pod, listener ID, group ID, and topic subscription.
2. Check when idle started, its duration, and received events.
3. Confirm the container is still running and holds partition assignments.
4. Check consumer paused state and pause/resume events.
5. Cross-check committed offsets, log end offsets, and consumer lag by partition.
6. Check producer throughput, upstream health, and expected data publication schedule.
7. Identify classic vs. consumer group protocol and whether a rebalance is underway.
8. Check poll rate, heartbeats, `max.poll.interval.ms`, and Kafka client errors.
9. Inspect serializer/deserializer and error handlers if records are not being dispatched.
10. With `read_committed`, check whether open transactions affect visibility.
11. If data is missing due to upstream, investigate the producer pipeline; if the consumer receives nothing while lag grows, investigate pause/assignment/poll.
12. After remediation, observe `ListenerContainerNoLongerIdleEvent` or actual record processing.
13. Document root cause, SLA impact, and alert conditions to reduce false positives.

Do not automatically restart the consumer simply upon seeing idle. If the topic genuinely has no data, restarting only causes group churn. If downstream is intentionally paused, restarting can break backpressure controls. Actions must rely on multiple verified signals.

## 25. Production implementation principles

- Enable `idleEventInterval` on the right listener container factory or effective Spring Boot property.
- Choose thresholds based on **traffic expectations**, not one threshold for all topics.
- Use `@EventListener` to receive `ListenerContainerIdleEvent` and `ListenerContainerNoLongerIdleEvent`; keep callbacks short.
- Distinguish container-level idle from partition-level idle when consumers own multiple partitions.
- With concurrency, track per-child listener IDs and assigned partitions.
- Treat events as **observations**, not definitive proof that Kafka lost data.
- Cross-check idle against consumer lag, producer rate, assignment, pause state, poll/heartbeat, and broker status.
- Never manipulate `KafkaConsumer` from an async application event handler.
- Never block the consumer thread with HTTP/database calls inside idle callbacks.
- Never synchronously stop the container from the consumer thread itself.
- Use state transitions and rate limits to prevent alert storms when idle events repeat.
- Handle lifecycle/rebalance events so stale idle states do not persist after containers stop.
- Use Testcontainers/embedded brokers or a test Kafka environment to verify event timing and behavior.
- Never use idle events in place of error handlers, offset correctness, transactions, or business idempotency.

**Conclusion:** `ListenerContainerIdleEvent` lets a Spring Kafka application detect that a listener container has received no records within a configured interval. Combined with `ListenerContainerNoLongerIdleEvent`, the application can track transitions between idle and active states, measure idle duration, and detect data-flow anomalies. However, idle does not mean paused, stopped, session timeout, or producer failure. Reliable operations require observing the right container/partition, understanding the limits of events, and combining Kafka group, producer, broker, and downstream metrics.
