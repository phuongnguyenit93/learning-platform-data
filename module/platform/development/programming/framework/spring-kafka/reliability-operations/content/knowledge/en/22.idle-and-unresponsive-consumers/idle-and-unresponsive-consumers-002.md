# idlePartitionEventInterval

In a Kafka consumer group, a single consumer may be assigned multiple partitions. Sometimes `orders-0` receives records steadily while `orders-1` gets no new records for minutes. If you only monitor the consumer at the container level, the application can still look healthy because `orders-0` continuously delivers data. However, operations teams may need to know **which specific partition has stopped delivering records to the listener**, even while other partitions remain active.

Spring Kafka provides the **`idlePartitionEventInterval`** property on the listener container to emit **`ListenerContainerPartitionIdleEvent`** when an assigned partition receives no records within the specified duration. When a previously idle partition receives records again, Spring Kafka can emit **`ListenerContainerPartitionNoLongerIdleEvent`**. These are *state-observation* signals—not commands to automatically retry, seek, commit offsets, pause, or restart the consumer.

Most importantly: **an idle partition does not mean the consumer is broken or Kafka lost data**. The topic may temporarily have no traffic, the producer may have stopped legitimately, the partition may be paused, or the consumer may simply be waiting for records eligible under transaction isolation. This lesson covers configuration, event handling, state differentiation, and reliable operational alerting.

## 1. Per-partition idle vs container-wide idle

Suppose a listener container is assigned three partitions:

```text
Kafka topic: orders

orders-0  -->  10 records/s  --> Consumer A --> @KafkaListener
orders-1  -->   0 records/s  --> Consumer A --> @KafkaListener
orders-2  -->   2 records/s  --> Consumer A --> @KafkaListener
```

The container is still receiving records from `orders-0` and `orders-2`, so a **container-wide idle** alert typically will not fire. Yet `orders-1` may receive no records for an extended period. That exact scenario is why `idlePartitionEventInterval` exists.

| Configuration | Monitoring scope | Question answered |
|---|---|---|
| `idleEventInterval` | Entire listener container | Has the consumer/container received no records at all for a while? |
| `idlePartitionEventInterval` | Each partition assigned to the consumer | Which specific partition has received no records for a while? |
| `noPollThreshold` with `monitorInterval` | Consumer poll responsiveness | Is the consumer stuck too long without returning to `poll()`? |
| Kafka consumer lag | Committed offset vs corresponding log end position | Is there an unprocessed backlog in the consumer group? |

In the example above, setting `idlePartitionEventInterval=60_000` can emit an event for `orders-1` even while total container throughput remains high. `idleEventInterval=60_000` only has a chance to fire when **none of the container's partitions** deliver records within the observation threshold.

Never use the absence of `ListenerContainerIdleEvent` to conclude every partition has data; nor use the presence of `ListenerContainerPartitionIdleEvent` to conclude the entire consumer is hung.

## 2. What does `idlePartitionEventInterval` control?

`idlePartitionEventInterval` is a duration in **milliseconds**. When set, the Spring Kafka listener container tracks idle status per partition and publishes an event when the time without receiving records meets the container's condition.

Example:

```java
factory.getContainerProperties()
       .setIdlePartitionEventInterval(60_000L);
```

The value `60_000L` corresponds to 60 seconds. This is an **event emission threshold**, not a trigger forcing Kafka to poll again, not a retry wait time, and not the Kafka client's `max.poll.interval.ms`.

Key characteristics to understand:

- The event reflects record receipt observed by the **listener container at a point in time**, not a producer SLA guaranteeing at least one record per minute.
- While a partition remains idle, the idle event can be emitted **repeatedly at the configured interval**, not just once in the partition's lifetime.
- When an idle partition receives records again, the *no longer idle* event helps observe when activity resumes.
- Emission timing precision depends on the `poll()` loop, processing time, scheduling, and container lifecycle; it is not an absolute-precision real-time timer.
- Only partitions that the consumer/container is currently **assigned and tracking** are meaningful in this event system. A partition outside an instance's assignment is not an idle partition for that instance.

Across Spring Kafka versions, the introduction and support level of partition events, idle calculation details, and batch listener behavior may vary. When upgrading the library, verify `ContainerProperties.setIdlePartitionEventInterval(...)` and the actual event classes in your dependency.

## 3. Configuration in `ConcurrentKafkaListenerContainerFactory`

This is the clearest way to enable per-partition idle observation for a specific group of listeners:

```java
@Configuration
public class OrdersKafkaConfiguration {

    @Bean("ordersKafkaListenerContainerFactory")
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
                new ConcurrentKafkaListenerContainerFactory<>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        ContainerProperties properties = factory.getContainerProperties();
        properties.setIdlePartitionEventInterval(60_000L);
        properties.setIdleEventInterval(120_000L);
        properties.setPollTimeout(1_000L);
        properties.setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }
}
```

`OrderEvent` is an illustrative domain class; `ConsumerFactory` must be configured with appropriate deserializers, bootstrap servers, security, and group settings. `concurrency=3` may spawn multiple child containers/consumer threads; actual active consumers and assignments depend on partition count and other group members.

In this example:

- After roughly 60 seconds with no records from a partition, the container can emit an idle event for that partition.
- If the entire container receives no records, `idleEventInterval=120_000` allows a container-level idle event.
- `pollTimeout=1_000` is only the timeout for each container-managed Kafka `poll()`; it does **not** set a 1-second idle threshold and does **not** replace `max.poll.interval.ms`.

Do not set thresholds too low relative to traffic cycles and poll cadence, or events will flood in without indicating an incident. For a topic with hourly traffic, a 60-second idle threshold can be completely normal behavior.

## 4. Enabling for a specific listener

To make a listener use the configuration above, specify the factory on `@KafkaListener`:

```java
@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "ordersPartitionMonitor",
            topics = "orders",
            groupId = "order-service",
            containerFactory = "ordersKafkaListenerContainerFactory")
    public void consume(OrderEvent event) {
        orderService.processIdempotently(event);
    }
}
```

Attaching the factory is crucial if the application has multiple `@KafkaListener` beans. Simply declaring a factory bean with idle events enabled does not prove the running listener uses it. When two different consumer groups subscribe to the same topic, each group/assignment can emit its own idle events.

This property can be configured via container APIs or Spring Boot configuration properties when your Boot version supports the corresponding binding. To avoid depending on property naming across releases, the example above uses `ContainerProperties` directly.

## 5. Capturing `ListenerContainerPartitionIdleEvent`

Spring can deliver lifecycle events to a bean using `@EventListener`. An observer should execute quickly, focusing on logging, metrics, or updating tracking state:

```java
import org.apache.kafka.common.TopicPartition;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerPartitionIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class PartitionIdleObserver {

    private static final Logger log = LoggerFactory.getLogger(
            PartitionIdleObserver.class);

    @EventListener
    public void onPartitionIdle(ListenerContainerPartitionIdleEvent event) {
        TopicPartition partition = event.getTopicPartition();

        log.info(
                "Kafka partition idle: topic={}, partition={}, idleMs={}",
                partition.topic(),
                partition.partition(),
                event.getIdleTime());
    }
}
```

`getTopicPartition()` identifies the exact idle partition; `getIdleTime()` reports the idle duration recorded by the event. Other attributes such as listener/container identifier, consumer reference, or pause state depend on the event type and Spring Kafka version. When tagging logs/metrics by container, use the exact API provided by your version.

**Do not turn `@EventListener` into a place for heavy database calls, timeout-free HTTP requests, or batch data processing.** By default, Spring application events are dispatched synchronously on the publishing thread, and slow handling can impact the container's processing loop.

## 6. Capturing the event when data returns to a partition

To measure when an idle period ends, also listen for `ListenerContainerPartitionNoLongerIdleEvent`:

```java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerPartitionNoLongerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class PartitionActiveObserver {

    @EventListener
    public void onActive(ListenerContainerPartitionNoLongerIdleEvent event) {
        TopicPartition partition = event.getTopicPartition();

        // Record in monitoring that the partition is active again.
        metrics.partitionNoLongerIdle(
                partition.topic(),
                partition.partition());
    }
}
```

`metrics` in this snippet is an application-defined adapter, not a built-in Spring Kafka variable. In real implementations, inject an appropriate metric recorder bean into the class rather than referencing an undeclared variable. A complete form can use constructor injection:

```java
@Component
public class PartitionActivityMetrics {

    private final PartitionStatusRecorder metrics;

    public PartitionActivityMetrics(PartitionStatusRecorder metrics) {
        this.metrics = metrics;
    }

    @EventListener
    public void onActive(ListenerContainerPartitionNoLongerIdleEvent event) {
        TopicPartition partition = event.getTopicPartition();
        metrics.markActive(partition.topic(), partition.partition());
    }
}
```

Here `PartitionStatusRecorder` is an application-built interface for storing monitoring state. `ListenerContainerPartitionNoLongerIdleEvent` indicates **the partition just received a record again after an observed idle period**—it does not prove all records succeeded in business processing. If the listener subsequently throws an exception, you still need to monitor retries, DLT, and offsets.

## 7. Event progression per partition

Suppose a consumer manages `payments-0` and `payments-1`, with a per-partition idle threshold of 30 seconds:

```text
Time              payments-0                 payments-1
-----------------------------------------------------------------
t = 0s            receives record            receives record
t = 10s           receives record            no record
t = 20s           receives record            no record
t ~ 30s           receives record            PartitionIdleEvent
t = 40s           receives record            still no record
t ~ 60s           receives record            may emit next idle event
t = 65s           receives record            receives new record
                                             NoLongerIdleEvent
```

This is an illustrative timeline and does not guarantee events fire at the exact 30,000 ms clock mark. Spring Kafka observes idle state within the listener container's run loop, so actual timing depends on `pollTimeout`, record processing speed, and scheduling.

At `t=30s`, `payments-0` is still active, so **the container is not idle** in the sense of receiving zero records. Only `payments-1` emits its own event. At `t=65s`, no-longer-idle for partition 1 lets the system update monitoring state, though it is not yet proof that end-to-end business processing completed.

## 8. Idle events are not `NonResponsiveConsumerEvent`

The chapter title "Idle and Non-Responsive" can lead to confusion: an empty partition and a consumer that stopped polling are **two distinct situations**.

```text
Scenario A: Kafka has no records for the partition
  Consumer keeps polling periodically
  Group membership remains stable
  PartitionIdleEvent may appear

Scenario B: Listener is blocked 8 minutes in an HTTP/SQL call
  Consumer thread has not returned to poll()
  Risks exceeding max.poll.interval.ms
  NonResponsiveConsumerEvent may appear from the monitor
  Risks rebalance and reprocessing of uncommitted offsets
```

`NonResponsiveConsumerEvent` relates to the mechanism monitoring elapsed time since the container's last poll, typically via `monitorInterval`, `noPollThreshold`, and `pollTimeout` in supported Spring Kafka versions. That mechanism is suited for detecting a stuck consumer, whereas `idlePartitionEventInterval` only measures **lack of records from a tracked partition**.

Never use `idlePartitionEventInterval` as a substitute for HTTP client timeouts or deadlock detection. A consumer thread blocked for a long time may **never get a chance to emit idle events as expected**; the absence of events does not prove the consumer is healthy.

## 9. How do idle events differ from consumer lag?

**Idle** describes no records received by the container over a duration. **Lag** describes the gap between a consumer group's committed offset and the corresponding end position of the Kafka log. The two signals may align or diverge.

| Scenario | Idle event | Lag | Interpretation |
|---|---|---|---|
| Topic temporarily has no new events, group caught up | Possible | Near 0 | Normal for a low-traffic topic |
| Partition paused due to downstream overload | Possible depending on lifecycle/config | May increase | Intentional backpressure, not necessarily a producer error |
| Listener very slow, many records already polled | Not necessarily emitted on time | May increase | Measure processing latency and poll responsiveness |
| Producer sends steadily, but consumer receives nothing | Possible | May increase | Check assignment, pause, fetch, auth, group, and transaction LSO |
| Producer only sends to one partition due to key skew | Other partitions may go idle | Skewed lag distribution | Check partitioning/traffic distribution |

A consumer with `isolation.level=read_committed` may be unable to read records sitting behind an earlier open transaction on a partition because the Last Stable Offset (LSO) has not advanced. This is one reason records exist in the log yet the listener receives none; distinguish it from a topic with no traffic at all.

A reliable alert typically combines `PartitionIdleEvent` with **expected traffic**, **lag**, **producer acknowledgments**, **assignment**, and **pause state**. Never report data loss based solely on one idle notification.

## 10. What does idle after pause/resume mean?

Spring Kafka provides `pause()`/`resume()` at the container level and supports per-partition pause in corresponding versions. When a partition is paused, the consumer generally stops receiving new records from that partition, while the container can keep polling to maintain group membership.

```text
Downstream overloaded
      |
      v
Container.pausePartition(orders-2)
      |
      v
orders-2 is not fetched while paused
      |
      v
If idle event fires, check PAUSED state before alerting
      |
      v
Downstream recovers -> resumePartition(orders-2)
```

Do not automatically call `resumePartition()` merely because a `ListenerContainerPartitionIdleEvent` arrived. A partition may be **intentionally paused** due to a dependency outage or rate limit. Resuming at the wrong time can trigger a retry storm and overload downstream again.

If you want pause state on a dashboard, fetch it from the container-supported API and explicitly model different pause reasons (manual intervention, circuit breaker, backoff). Track idle, pause, and consumer lag as **separate state axes**.

## 11. Concurrency, group assignment, and ownership

With `ConcurrentKafkaListenerContainerFactory`, each child container has its own Kafka consumer. Kafka distributes topic partitions among consumers in the same group; at any given moment a partition belongs to **one assigned member** under the normal group protocol.

```text
orders topic: 6 partitions

Application instance A, group order-service
   child consumer A0 -> orders-0, orders-3
   child consumer A1 -> orders-1

Application instance B, same group
   child consumer B0 -> orders-2, orders-4
   child consumer B1 -> orders-5
```

In this setup, instance A can observe idle events for `orders-0`, `orders-1`, and `orders-3`, but **cannot** observe idle for `orders-2`, `orders-4`, or `orders-5` through consumers it does not own. To gain a group-wide view, aggregate events across all replicas or combine with external Kafka metadata/metrics.

After a rebalance, ownership can shift. An idle event prior to a rebalance should not be stored as "orders-3 is permanently idle on instance A". When a partition is revoked, clear or invalidate state tied to the old assignment. For systems persisting state over time, include timestamps and owner/container identity to prevent stale alerts.

## 12. Rebalance is not partition idle

During the consumer lifecycle, revoke/assign callbacks can occur when an instance is added/removed, a container restarts, or the group rebalances partitions. A recently revoked partition may **not emit idle events** on the old instance because it is no longer part of its assignment.

If you need to clean up partition state when assignments change, use `ConsumerAwareRebalanceListener`:

```java
factory.getContainerProperties().setConsumerRebalanceListener(
        new ConsumerAwareRebalanceListener() {

    @Override
    public void onPartitionsRevokedBeforeCommit(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {
        partitionStatusRecorder.removeOwnership(partitions);
    }

    @Override
    public void onPartitionsAssigned(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {
        partitionStatusRecorder.registerOwnership(partitions);
    }
});
```

`partitionStatusRecorder` is an application bean/adapter used to store observed state. In production code, it must be injected or held in a valid scope. Rebalance callbacks should not run slow database or HTTP calls, as they sit directly on the Kafka consumer group coordination path.

Monitoring partition idle observes **lack of received data**; monitoring rebalances observes **partition ownership**. The two systems should complement each other, never replace each other.

## 13. Keep event listeners short and watch thread affinity

By default, Spring's `ApplicationEventMulticaster` usually invokes event listeners **synchronously on the event-publishing thread**. Kafka listener containers publish idle events from their consumer context, so a slow event listener can slow down polling and increase processing latency.

Do not do this:

```java
@EventListener
public void onIdle(ListenerContainerPartitionIdleEvent event) {
    // Do not make timeout-free HTTP health checks here.
    // Do not run full-table queries or sleep waiting for producers here.
    // Do not manually seek/commit offsets to "fix" idle state.
}
```

Do this instead:

```java
@EventListener
public void onIdle(ListenerContainerPartitionIdleEvent event) {
    TopicPartition partition = event.getTopicPartition();
    metricsRecorder.recordIdle(
            partition.topic(), partition.partition(), event.getIdleTime());
}
```

This snippet assumes `metricsRecorder` is injected; operations should be fast and non-blocking. If the application event multicaster is configured asynchronously, callbacks may execute on a different executor thread. In that case, **never** pass a `KafkaConsumer` obtained from the event to another thread to call `pause()`, `seek()`, or `commitSync()`: `KafkaConsumer` is not thread-safe.

If an administrative action like pause/resume is required, use container APIs through `KafkaListenerEndpointRegistry` or a dedicated coordinator. Never alter consumer assignment, offsets, or lifecycle directly inside an event observer simply because a partition looks idle.

## 14. Designing a state machine for idle alerts

Because idle events can repeat, operations teams should manage state instead of opening a new incident on every event:

```text
              record received
                   |
                   v
                 ACTIVE
                   |
       threshold exceeded, PartitionIdleEvent
                   |
                   v
                  IDLE
                   |
            repeated idle
             (stay IDLE)
                   |
            record arrives
          NoLongerIdleEvent
                   |
                   v
                 ACTIVE
```

A state entry can include `(groupId, topic, partition, ownerInstance, timestamp, idleSince, observedIdleMs, paused, expectedTraffic)`. Not all fields come directly from the event; `groupId`, owner, and expected traffic may come from external configuration/metrics.

To prevent false alarms, enforce conditions such as:

1. The partition has been stably assigned for a minimum period.
2. The partition is **not intentionally paused**.
3. This topic/partition **is expected to have traffic** at the time of observation.
4. The consumer group is not rebalancing or shutting down.
5. Idle duration exceeds a true SLO threshold, not just a single event.

If a partition remains idle while records already exist in the Kafka log, compare producer lag, consumer lag, isolation level, partition assignment, and client fetch metrics to distinguish **producer not sending** from **consumer not receiving**.

## 15. Choosing idle thresholds suited to topic type

No single `idlePartitionEventInterval` fits every topic. Examples:

| Stream type | Characteristics | Threshold guidance |
|---|---|---|
| Realtime payment/transaction | Continuous traffic expected during operating hours | Tens of seconds to a few minutes, combined with expected traffic and SLO |
| Batch events every 15 minutes | Long empty gaps are normal | Alert only after scheduled batch window plus delay margin |
| Low-volume tenant/partition | Hours without events possible | Idle for telemetry only; do not automatically treat as an incident |
| Heartbeat events | Producer commits to a specific cadence | Can correlate cadence against idle events and producer metrics |
| Retry topic | Records only appear when errors need retry | No data is usually a **healthy** state |
| DLT | Should normally have few or no records | Do not alert on idle; alert when DLT rate/backlog grows |

For retry and DLT topics, setting a "60-second partition idle" alert is counterproductive: when the system is healthy, those topics may see no records for days. Alerts must reflect the **business meaning of the topic**, not just a technical framework feature.

If traffic follows time zones or business days, incorporate data production schedules into alert evaluation. Do not generate false incidents every night just because a partition stops receiving orders after business hours.

## 16. Accompanying metrics and observability

Events should be complemented by foundational metrics and logs:

| Signal | Meaning |
|---|---|
| `ListenerContainerPartitionIdleEvent` count | How many times a partition crossed the idle threshold |
| `ListenerContainerPartitionNoLongerIdleEvent` count | How often records resumed after idle |
| Idle duration per partition | Observed duration without records on a partition |
| Consumer assignment/owner | Which consumer is currently responsible for the partition |
| Consumer lag and last committed offset | Whether the group still has an actual backlog |
| Poll count / time between polls | Whether the consumer is still polling steadily |
| `NonResponsiveConsumerEvent` | Signs the consumer is stuck in processing/poll lifecycle |
| Rebalance/partition revoke rate | Whether partition ownership is churning frequently |
| Pause requested / paused state | Whether lack of records is intentional backpressure |
| Producer publish count and errors | Whether the producer is actually writing to the partition |

Never use message IDs or offsets as metric labels due to unbounded cardinality. `topic`, `partition`, listener ID, and group ID usually have bounded cardinality, though clusters with many topics/partitions still need care. Use structured logs for granular identifiers during investigation.

When a container has `concurrency > 1`, events can originate from multiple child threads. A service-wide dashboard should aggregate accurately by `group + topic + partition` and retain state only for the **current owner**, avoiding double-counting a partition across both old and new owners after a rebalance.

## 17. Common implementation mistakes

| Symptom | Possible cause | Resolution |
|---|---|---|
| A partition is silent but no event appears | `idlePartitionEventInterval` not set, listener uses another factory, or partition not assigned | Verify actual factory, group assignment, and Spring Kafka version |
| Only `ListenerContainerIdleEvent` appears | Only `idleEventInterval` enabled, partition-level interval unset | Configure `setIdlePartitionEventInterval(...)` |
| Idle events arrive repeatedly every interval | Partition continues receiving no records so events re-fire | Use a state machine/deduplicated alert; do not open an incident per event |
| Healthy consumer alerted as dead | Confused partition idle with non-responsive poll | Check `NonResponsiveConsumerEvent`, poll timing, lag, and assignment |
| Paused partition triggers producer outage alert | Pause prevents container from receiving records | Factor pause reason/state into alert conditions |
| No-longer-idle never fires despite producer sends | Records haven't reached consumer due to pause, assignment, transaction LSO, or fetch error | Inspect broker/consumer lag and record visibility |
| Alarm vanishes after rebalance | State tied to old instance without updating owner | Use rebalance callbacks or aggregate by group and new owner |
| Event listener slows down consumer | Handler writes to DB or makes blocking HTTP calls | Keep only fast metric/log recording; offload slow work to a separate workflow |
| Retry/DLT topics constantly alert idle | Those topics naturally lack regular traffic | Disable idle alerting or apply business-aware policies |
| Changing `pollTimeout` breaks expected idle timing | Confused poll timeout with idle interval | Measure both properties properly and observe actual event timing |

During investigation, always determine which statement is true: **the partition has no records on the broker**, **records exist but are not yet visible**, **the consumer is not assigned**, **the consumer is paused**, or **the consumer is stuck**. The same symptom of no records reaching the listener can stem from any of these five causes and requires five different responses.

## 18. Integration testing `idlePartitionEventInterval`

A good test should use a Kafka test broker or Testcontainers, a multi-partition topic, and a listener container with a short `idlePartitionEventInterval`. Tests should observe events using explicit synchronization, not just `Thread.sleep()` and log inspection.

Recommended scenario:

1. Create topic `orders` with at least two partitions and a dedicated test consumer group.
2. Configure the listener container with `setIdlePartitionEventInterval(1_000L)`; keep `pollTimeout` relatively short for easier test observation.
3. Send records continuously to partition 0, and none to partition 1.
4. Verify `ListenerContainerPartitionIdleEvent` fires for partition 1 even while partition 0 is active.
5. Send a valid record to partition 1; verify `ListenerContainerPartitionNoLongerIdleEvent` fires and the listener receives the record.
6. Leave partition 1 empty again; verify idle events can reappear after the threshold.
7. Pause partition 1, record idle and pause state; the test must not interpret pause as a producer outage.
8. Trigger a rebalance by adding/removing a consumer in the same group; verify the new owner is tracked properly.
9. Intentionally block a listener to trigger non-responsive detection in a separate test, demonstrating the two event types do not replace each other.
10. Verify record processing, committed offsets, and group assignment; an idle event alone does not confirm successful processing.

Example test probe:

```java
@Component
public class PartitionIdleTestProbe {

    private final BlockingQueue<TopicPartition> idlePartitions =
            new LinkedBlockingQueue<>();

    private final BlockingQueue<TopicPartition> activePartitions =
            new LinkedBlockingQueue<>();

    @EventListener
    public void idle(ListenerContainerPartitionIdleEvent event) {
        idlePartitions.offer(event.getTopicPartition());
    }

    @EventListener
    public void active(ListenerContainerPartitionNoLongerIdleEvent event) {
        activePartitions.offer(event.getTopicPartition());
    }

    public TopicPartition awaitIdle(Duration timeout)
            throws InterruptedException {
        return idlePartitions.poll(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }

    public TopicPartition awaitActive(Duration timeout)
            throws InterruptedException {
        return activePartitions.poll(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }
}
```

In tests, explicitly inspect `topic()` and `partition()` popped from the queue. If both partitions emit idle events, the test must filter for the partition under verification rather than assuming the first event always belongs to partition 1. Ensure the consumer group has been assigned partitions before starting the observation window.

This is a probe example; when running multiple tests within the same Spring context, clear queues and state between cases to avoid leftover events. Version specifics, thread dispatch, poll cadence, and child consumer counts should be validated against the real environment.

## 19. Runbook when a partition unexpectedly goes idle

When alerted that a production partition unexpectedly stopped receiving records, proceed in order:

1. **Verify expectations:** Is the topic/partition expected to receive records at this time? Are there batch schedules or hourly traffic patterns?
2. **Check ownership:** Which consumer group and instance currently hold the partition assignment? Did a rebalance or deployment just occur?
3. **Check pause state:** Is the container or partition paused due to backpressure, retry/backoff, or operational action?
4. **Compare broker and consumer:** Is the producer writing records to the partition? What do lag and LSO/high watermark show?
5. **Check poll responsiveness:** Is the consumer still polling and heartbeating steadily? Are there `NonResponsiveConsumerEvent` or `max.poll.interval.ms` warnings?
6. **Inspect listener/error-handler logs:** Were there deserialization, conversion, retry, or DLT errors right before the partition went idle?
7. **Fix the root cause:** Repair producer routing, resume per procedure, restore dependencies, or unblock the stuck consumer; never seek/reset offsets arbitrarily.
8. **Observe recovery:** Wait for the partition to receive new records, verify no-longer-idle, offset progress, and business side effects.
9. **Document the incident:** Record idle duration, owner, root-cause category, impacted data, and alert threshold adjustments if needed.

Never reset consumer offsets to try forcing a partition to "have data again". Rewinding offsets can replay records and create duplicates, while advancing offsets can skip unprocessed records. For a partition that genuinely has no new events, resetting offsets will not make the producer send data.

## 20. Production principles

1. `idlePartitionEventInterval` is a **per-partition idle observation** threshold at the Spring Kafka listener container level.
2. `ListenerContainerPartitionIdleEvent` does not mean the consumer is hung, Kafka lost records, or business logic failed.
3. Distinguish it from container-level `idleEventInterval` and poll-loop-related `NonResponsiveConsumerEvent`.
4. Configure it on the **correct listener container factory**; verify actual group assignments, especially with concurrency and multiple replicas.
5. Handle events quickly; do not block the consumer thread with HTTP/DB calls or invoke Kafka consumer APIs from another thread.
6. Monitor `ListenerContainerPartitionNoLongerIdleEvent` to know when a partition receives records again, without treating it as proof of successful business processing.
7. Combine expected traffic, pause state, rebalances, LSO, lag, and producer metrics before alerting.
8. Do not apply the same alert thresholds across realtime, batch, retry, and DLT topics.
9. Clean up per-partition state when assignments change; use owner/timestamp metadata to avoid post-rebalance confusion.
10. Test all scenarios: one partition idle while another is active, no-longer-idle, pause, rebalance, and non-responsive consumer.

**Conclusion:** `idlePartitionEventInterval` closes an important observability gap: **a single partition can receive no records even while the consumer and other partitions remain active**. When configured properly and paired with assignment state, pause state, consumer lag, producer cadence, and SLO-aligned alerting, this event helps surface partition-level anomalies without equating normal silence with system failure.
