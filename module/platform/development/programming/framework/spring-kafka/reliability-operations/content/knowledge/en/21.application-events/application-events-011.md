# ListenerContainerPartitionIdleEvent

In Spring Kafka, a listener can subscribe to a topic containing multiple partitions. There are times when most partitions receive new records while one partition receives no data for a long period. If you only monitor consumer container state or total records processed, this situation is very easy to miss.

**`ListenerContainerPartitionIdleEvent`** is a Spring Kafka application event used to announce that **a partition monitored by the listener container has received no records for the configured idle duration**. This event helps the application distinguish one inactive partition from the entire container stopping consumption, supporting load distribution visibility, detecting silent data sources, and aiding operational workflows.

It is a **partition-level lifecycle and incoming-data observation signal**, not a Kafka record, and not proof that the broker lacks records or that the listener has drained all backlog. To diagnose accurately, combine the event with consumer group assignment, consumer lag, offsets, pause state, and producer status.

## 1. Why track idle at the partition level?

Suppose topic `orders.events` has four partitions:

~~~text
orders.events
    |
    +---- partition 0: steady events
    +---- partition 1: steady events
    +---- partition 2: no new records for 5 minutes
    +---- partition 3: steady events
                              |
                              v
                    Spring Kafka listener
~~~

The consumer continues processing many records per second from partitions 0, 1, and 3. Thus, a "container processing records" metric may look completely normal. Yet if partition 2 corresponds to a critical shard, customer, or data source, prolonged silence may warrant investigation.

`ListenerContainerPartitionIdleEvent` helps detect this **localized idle** state without waiting for the entire container to run out of records.

It is useful in scenarios such as:

- One partition has almost no records while other partitions have traffic.
- An upstream shard or routing key risks having stopped publishing data.
- You need to monitor record distribution and whether some partitions become "cold."
- A workflow wants to track data-absence duration per partition.
- You need to distinguish a running consumer from data failing to arrive on a specific partition.

However, Kafka **does not guarantee** every partition always has traffic. Having idle partitions is completely normal for sparse workloads, time-of-day data, or uneven key distributions. Alerts should only fire when aligned with business contracts.

## 2. Difference between container idle and partition idle

Spring Kafka provides events for **whole-container** idle state and for **individual partitions**.

| Signal | Observation scope | Meaning |
|---|---|---|
| `ListenerContainerIdleEvent` | Entire listener container/consumer | No records received within the container's idle interval. |
| **`ListenerContainerPartitionIdleEvent`** | One specific topic-partition | This partition received no records within the configured idle interval. |
| `ListenerContainerNoLongerIdleEvent` | Container | After container idle time, new records were received. |
| `ListenerContainerPartitionNoLongerIdleEvent` | Partition | A previously idle partition is receiving records again. |
| `NonResponsiveConsumerEvent` | Consumer poll/progress capability | Consumer failed poll monitoring checks per threshold; not equivalent to lacking records. |
| `ConsumerStoppedEvent` | Consumer lifecycle | Consumer stopped, possibly with a reason depending on version. |

Example:

~~~text
Partition 0: 10 records/sec
Partition 1:  8 records/sec
Partition 2:  0 records/sec

Overall container: has records, NOT necessarily idle
Partition 2: idle, may emit PartitionIdleEvent
~~~

Therefore, **do not use `ListenerContainerIdleEvent` as a complete substitute for `ListenerContainerPartitionIdleEvent`** when operations need to know which partition lacks data.

Conversely, do not equate multiple individually idle partitions with the entire container having stopped. A container can operate normally and maintain group membership even without new records.

## 3. Conditions that trigger a partition idle event

Conceptual model:

1. The consumer container is running and tracking its assigned partitions.
2. For each partition, the framework maintains the timestamp of the last received record or corresponding idle-tracking baseline.
3. When a partition's no-record duration reaches the configured threshold, the container can publish `ListenerContainerPartitionIdleEvent`.
4. If the partition continues receiving no records, idle events may be emitted repeatedly at the configured interval.
5. When a previously idle partition receives a record, the framework can publish `ListenerContainerPartitionNoLongerIdleEvent` to report the state change.

~~~text
Partition P1
  |
  +---- record at T0
  |
  +---- no records
  |
  +---- reaches idle threshold -> PartitionIdleEvent
  |
  +---- still no records -> may emit subsequent idle events
  |
  +---- new record -> PartitionNoLongerIdleEvent
~~~

This is a **conceptual diagram**. Exact emission timing depends on the `poll()` loop, container implementation, configuration, Spring Kafka version, thread scheduling, and how the consumer is paused/resumed.

The event is not a real-time timer with strict millisecond precision. If the listener is blocked in slow record processing or the container has not returned to the idle check loop, the event may arrive later than the configured threshold.

## 4. Configuring idlePartitionEventInterval

In Spring Kafka, the central property is **`ContainerProperties.idlePartitionEventInterval`**, typically configured via:

~~~java
factory.getContainerProperties()
        .setIdlePartitionEventInterval(30_000L);
~~~

The value in the example is **30,000 milliseconds = 30 seconds**. When the application does not configure this threshold, do not assume the framework automatically emits partition idle events at a useful interval; you must explicitly enable the feature.

A listener container factory:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
public class OrderConsumerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            orderListenerFactory(
                    ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        // After 30 seconds without receiving records on a partition,
        // the container can publish a partition-idle event.
        factory.getContainerProperties()
                .setIdlePartitionEventInterval(30_000L);

        return factory;
    }
}
~~~

Listener using the factory:

~~~java
@KafkaListener(
        id = "orders-listener",
        groupId = "orders-service",
        topics = "orders.events",
        containerFactory = "orderListenerFactory")
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
~~~

In this example, `OrderEvent` and `OrderService` are application-defined business types; the consumer factory bean, serializer/deserializer, and Kafka bootstrap servers must be configured separately.

### 4.1. Do not confuse with idleEventInterval

Two properties are frequently confused:

- **`idleEventInterval`:** tracks idle at the container scope.
- **`idlePartitionEventInterval`:** tracks idle at the individual topic-partition scope.

Example:

~~~java
factory.getContainerProperties().setIdleEventInterval(60_000L);
factory.getContainerProperties().setIdlePartitionEventInterval(15_000L);
~~~

A container can publish a partition-idle event for one partition after 15 seconds even while other partitions still have data. Only when the container receives no records for 60 seconds does the container-level idle event match the threshold in the example.

Some Spring Kafka versions support configuring container-level idle via `@KafkaListener` annotation attributes, but **do not assume partition idle shares the same annotation attribute**. The clear approach is setting `idlePartitionEventInterval` on `ContainerProperties` of the container factory or specific container per your version's API.

### 4.2. Choosing thresholds by data cadence

There is no single threshold suited to every workload:

| Workload | Expected data cadence | Threshold guidance |
|---|---|---|
| Continuous payment events across partitions | Every few seconds or continuous | Relatively short threshold, with noise deduplication. |
| Batch data sync | Every few minutes or scheduled | Threshold longer than batch cycle and normal delay. |
| Very rare events | Possibly hours with no records | Do not alert solely on partition idle. |
| Uneven shards | Depends on each shard | Use per-shard thresholds/context or compare against actual traffic. |
| Near-real-time system with emission SLA | Clear expectation of max silence | Threshold based on SLA plus transport/scheduling time. |

If the threshold is too short, the application can emit many low-value events and alerts. If too long, detecting a stalled data producer will be delayed.

## 5. Receiving the event with @EventListener

Event package:

~~~java
import org.springframework.kafka.event.ListenerContainerPartitionIdleEvent;
~~~

A Spring bean receiving the event:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerPartitionIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class PartitionIdleObserver {

    private static final Logger log =
            LoggerFactory.getLogger(PartitionIdleObserver.class);

    @EventListener
    public void onPartitionIdle(
            ListenerContainerPartitionIdleEvent event) {

        log.info("Kafka partition idle: source={}, container={}",
                event.getSource(),
                event.getContainer());
    }
}
~~~

`@EventListener` is invoked by Spring when the application context receives the corresponding event. This is an **in-process** event mechanism; it does not create Kafka records, has no separate consumer group, and does not persist events in the broker.

Depending on the Spring Kafka version, the event also provides metadata such as the idle topic-partition, listener ID, idle duration, consumer, or pause state. In production code, use the published API of your exact version instead of extracting metadata by parsing `source.toString()`.

### 5.1. Getting topic-partition and idle time

With versions providing the corresponding accessors, you can use event metadata to record per-partition metrics:

~~~java
@EventListener
public void onPartitionIdle(
        ListenerContainerPartitionIdleEvent event) {

    TopicPartition partition = event.getTopicPartition();
    long idleMillis = event.getIdleTime();

    log.info(
            "Partition idle topic={} partition={} idleMillis={}",
            partition.topic(),
            partition.partition(),
            idleMillis);
}
~~~

Import `TopicPartition` from `org.apache.kafka.common.TopicPartition`. The `idleMillis` value represents the idle duration reported by the framework at event publication time; it does not necessarily equal the exact threshold and may be larger due to polling/scheduling.

In applications with multiple listeners sharing a topic, include listener/container identity in logs so one consumer group's silence is not mistaken for the entire topic being silent.

### 5.2. Receiving the event with ApplicationListener

If you prefer an explicit listener type declaration:

~~~java
import org.springframework.context.ApplicationListener;
import org.springframework.kafka.event.ListenerContainerPartitionIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class PartitionIdleListener
        implements ApplicationListener<ListenerContainerPartitionIdleEvent> {

    @Override
    public void onApplicationEvent(
            ListenerContainerPartitionIdleEvent event) {
        // Update metrics by topic-partition.
        metrics.recordPartitionIdle(event);
    }
}
~~~

Both `@EventListener` and `ApplicationListener` receive application events; use one consistent approach to avoid recording duplicate metrics unnecessarily.

## 6. When the partition receives records again

A previously idle partition does not necessarily stay idle forever. When records return, Spring Kafka has the corresponding **`ListenerContainerPartitionNoLongerIdleEvent`** in supported versions.

~~~text
P2: has records
     |
     v
30 seconds with no records
     |
     +---- ListenerContainerPartitionIdleEvent
     |
     v
P2 receives new record
     |
     +---- ListenerContainerPartitionNoLongerIdleEvent
     |
     v
P2 state is no longer idle
~~~

Example listener observing both transitions:

~~~java
@Component
public class PartitionActivityLogger {

    private static final Logger log =
            LoggerFactory.getLogger(PartitionActivityLogger.class);

    @EventListener
    public void onIdle(ListenerContainerPartitionIdleEvent event) {
        log.info("Partition entered idle state: {}",
                event.getSource());
    }

    @EventListener
    public void onActive(
            ListenerContainerPartitionNoLongerIdleEvent event) {
        log.info("Partition no longer idle: {}",
                event.getSource());
    }
}
~~~

If the application maintains an idle state gauge, it must handle **both idle and no-longer-idle events** and reconcile when consumers stop/rebalance. Never receive an idle event and increment a permanent state variable, because the partition may later receive data or move to another consumer member.

## 7. Idleness and consumer lag are two different concepts

A partition receiving no records at the listener for a period is not enough to conclude the broker has no data.

**Consumer lag** is typically calculated from the log end offset and the committed consumer group offset:

```text
lag = log end offset - committed offset
```

Interpret carefully because the committed offset can lag behind the consumer position, especially with batch processing or manual acks.

| Partition idle? | Lag | Possible interpretation |
|---|---:|---|
| Yes | 0 | No new data; normal if source is not emitting events. |
| Yes | High | Consumer may be paused, stuck, falling behind, or lag due to uncommitted offsets. |
| No | High | Consumer is processing yet speed cannot keep up with producer. |
| No | 0 or low | Records exist and consumer is able to keep pace with source. |

`ListenerContainerPartitionIdleEvent` measures **how long no records were observed being received on the partition within the container context**. It does not replace APIs reading log end offsets, committed offsets, or consumer positions.

For example, a listener holds partition 4 yet `pause()`s that partition: the container may receive no new records from partition 4 while producers keep writing to it. In that case, "idle" does not mean upstream stopped sending records. Check pause state and lag before alerting.

## 8. Partition assignment and rebalance

A Kafka consumer group assigns each partition to at most one consumer member in the same group at a time. When the group rebalances, a partition can be revoked from the current consumer and assigned to another member.

~~~text
Before rebalance:
  consumer A -> partition 0, partition 1
  consumer B -> partition 2

After rebalance:
  consumer A -> partition 0
  consumer B -> partition 1, partition 2
~~~

If a partition was previously idle on consumer A, after rebalance it may be managed by consumer B. **Historical events from A no longer prove the current state of the partition on B.**

In an application maintaining a per-partition idle state table:

1. Listen to idle/no-longer-idle events to record transitions.
2. Track `onPartitionsAssigned` and `onPartitionsRevoked` via rebalance listener or equivalent APIs.
3. Clear/update state when the container loses ownership of a partition.
4. Do not treat stale idle state as permanently accurate data after a rebalance.
5. Use consumer group metrics to verify the new owner is active.

Do not use partition idle events to replace `ConsumerRebalanceListener` or `ConsumerAwareRebalanceListener`. Those are two mechanisms with different purposes.

### 8.1. An unassigned partition is not necessarily idle

If there are more consumers than partitions, some consumers receive no partitions. You cannot expect partition idle events from a consumer **that does not own that partition**.

Therefore, when observing no events for a partition, check:

- Does the partition exist and belong to the subscribed topic?
- Does a consumer group member currently own it?
- Is the listener container running and polling?
- Was the idle threshold configured?
- Was the partition just reassigned or revoked?
- Is the event observer receiving events from the right application context?

Absence of events is not proof that Kafka is healthy.

## 9. ConcurrentMessageListenerContainer and event scope

A listener with `concurrency = 3` can have three child consumers:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent> ordersFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    factory.getContainerProperties()
            .setIdlePartitionEventInterval(20_000L);

    return factory;
}
~~~

~~~text
Concurrent listener container
      |
      +---- consumer A -> p0, p1
      +---- consumer B -> p2
      +---- consumer C -> p3, p4
~~~

If p1 goes idle, the event relates to partition p1 in the context of the consumer/container owning it. The event does not say all of child consumer A or the entire parent container has no records, because consumer A may still be processing p0.

In monitoring, attach fields:

- Topic and partition.
- Listener ID/container identity.
- Consumer group.
- Instance/pod ID if needed to correlate with deployments.
- Idle duration in milliseconds.
- Pause state and assigned partition count.

When metrics use topic/partition as labels, control cardinality if the cluster has hundreds of thousands of partitions. Avoid placing event IDs, record keys, or offsets on every metric label.

## 10. Impact of pause/resume

Spring Kafka lets you pause a listener container or partition during backpressure, maintenance, or throughput throttling. While paused, the consumer can still poll to maintain group membership without delivering new records to the listener.

Example of a paused partition:

~~~text
Producer keeps writing to partition 3
            |
            v
Broker log end offset increases
            |
            v
Consumer paused partition 3
            |
            v
Listener receives no new records from partition 3
            |
            +---- Partition idle event may appear
            |
            +---- Consumer lag may grow
~~~

Therefore, **before calling a partition idle an upstream outage, check whether the container or partition is currently paused**. An intentional pause normally does not need a "producer stopped" alert.

You can read pause state via appropriate container APIs and event fields if provided by your version. Do not directly invoke `KafkaConsumer` operations such as `pause()`, `resume()`, or `seek()` from an asynchronous event listener without ensuring the right consumer thread.

### 10.1. Do not auto-seek/replay just because a partition is idle

A design flaw is seeing a partition go idle and calling `seekToBeginning` or resetting offsets to "kickstart" data. If the partition has no new records, resetting offsets causes re-reading old records, risking duplicate side effects or out-of-order processing.

A more appropriate response is usually:

1. Observe lag and the producer source.
2. Check consumer assignment/pause state.
3. Cross-check expected event generation schedules by business rules.
4. If needed, emit an alert or flag the silent shard in monitoring.
5. Replay only after an explicit decision and appropriate idempotency checks.

## 11. On which thread does the event listener execute?

Application events pass through Spring's `ApplicationEventMulticaster`. With the default synchronous multicaster, `@EventListener` can be invoked directly on the **consumer thread** publishing the event. If the multicaster is configured with an async executor, the event listener can run on another thread.

This directly affects operational safety:

- Kafka `Consumer` is not thread-safe for ordinary operations.
- An event may carry a consumer reference, yet you must never use that reference from an arbitrary thread.
- Blocking long in a synchronous event handler can slow the `poll()` loop and affect the consumer group.
- Calling container lifecycle methods back from an inappropriate callback can cause deadlocks or races.
- With an async multicaster, event ordering and execution time do not necessarily align with publication time.

Therefore, `@EventListener` for partition idle should stay **lightweight and bounded**:

~~~java
@EventListener
public void onPartitionIdle(ListenerContainerPartitionIdleEvent event) {
    TopicPartition tp = event.getTopicPartition();

    log.info("Partition idle: {}-{}, idleMs={}",
            tp.topic(),
            tp.partition(),
            event.getIdleTime());

    metrics.recordIdleObservation(tp.topic(), tp.partition());
}
~~~

Do not make slow HTTP calls, database migrations, or heavy queries here. If data enrichment is needed, push a **small notification without the `Consumer` object** to a separate executor for processing, with queue limits and deduplication.

If the event is used to request container pause/resume, use thread-safe container APIs supporting such requests and verify your version's behavior; do not misuse consumer references.

## 12. Deduplicating noise and avoiding alert storms

A partition can stay idle across multiple intervals, so the application can receive many idle events without an actual state change.

Example with a 30-second threshold:

~~~text
T+30s  -> PartitionIdleEvent
T+60s  -> PartitionIdleEvent
T+90s  -> PartitionIdleEvent
T+120s -> PartitionIdleEvent
~~~

Do not automatically open a new incident on every event. Instead, maintain a per-partition state machine:

~~~text
ACTIVE
   |
   | first idle
   v
IDLE (open an alert if appropriate)
   |
   | idle continues
   v
IDLE (update duration/metric, do not create duplicate alert)
   |
   | new record
   v
ACTIVE (close alert or record recovered)
~~~

The application must update state during rebalance/restart/stop so it does not keep stale "idle" status for partitions no longer owned by the current consumer.

In many systems, alerts based on **lag + throughput + producer SLO** are more valuable than alerts based on idle alone. For instance, an order-processing events topic with low overnight traffic can normally have idle partitions; whereas a shard heartbeat topic required to emit once per minute makes prolonged idle abnormal.

## 13. Distinguishing upstream issues from consumer issues

Upon receiving `ListenerContainerPartitionIdleEvent`, you can investigate along these branches:

~~~text
Partition idle event
       |
       +---- Consumer still owns partition?
       |          |
       |          +---- No -> check rebalance/assignment
       |
       +---- Is partition paused?
       |          |
       |          +---- Yes -> backpressure/maintenance
       |
       +---- Is lag increasing?
       |          |
       |          +---- Yes -> consumer slow/stuck/uncommitted offsets
       |          |
       |          +---- No -> may have no new data
       |
       +---- Is producer writing to partition?
                  |
                  +---- No -> check upstream routing, source, schedule
                  +---- Yes -> check fetch, permissions, offsets, consumer state
~~~

Common causes:

| Symptom | Possible cause | Evidence to collect |
|---|---|---|
| One partition has no records, lag near 0 | Sparse workload, producer key skew, upstream shard stopped | Records-in per partition, producer logs, business schedule. |
| Partition idle yet lag is high | Pause, blocked consumer, uncommitted offsets, fetch issue | Pause state, consumer metrics, thread dumps, committed offsets. |
| Multiple partitions idle simultaneously | Upstream stopped publishing, system low load | Producer throughput, broker records-in, data schedule. |
| Idle after rebalance | Assignment changed, tracking state just reinitialized | Group assignment, revoke/assign callbacks, instance logs. |
| Idle event absent despite no records | Threshold not enabled, container stopped, missing observer, poll stuck | `ContainerProperties`, lifecycle logs, application event wiring. |
| Idle very frequently in a short span | Threshold too low, repeated events, or multiple containers | Event frequency metrics, concurrency, assigned partitions. |

Do not use a single event to assert root cause. It is an **observed symptom** that must be placed in system context.

## 14. Distinguishing partition idle from a slow listener

Suppose a consumer receives a batch containing records from partitions 0 and 1; the listener processes one record very slowly. Even while the broker has data, the consumer thread may not have returned to `poll()` to fetch more.

In this situation:

- The interval between deliveries to the listener can be long.
- Consumer lag can grow.
- `NonResponsiveConsumerEvent` or poll/processing metrics may raise other signals.
- Partition idle events can arrive late because the container had no chance to check idle conditions on schedule.

Therefore, do not treat partition idle events as a **hung-consumer detector**. For non-polling or blocked consumers, track poll intervals, thread dumps, consumer group rebalances, and processing latency.

If the listener processes slowly, also watch `max.poll.interval.ms` and dependency timeouts. A consumer evicted from the group for taking too long between polls is a different lifecycle issue from a partition simply having no new records.

## 15. Impact of record filters, retries, and transactions

### 15.1. Record filtering

A record may be fetched by the consumer yet filtered out before reaching the business listener (e.g., `RecordFilterStrategy`). Whether idle/no-longer-idle events fire can depend on where Spring Kafka updates record-receipt state in its implementation.

Do not assume "no business handler invocation" always equals "partition idle" if the pipeline has filters, interceptors, or batch listeners. When you need business activity visibility, measure **records accepted and processed successfully by business logic** separately from container record receipt.

### 15.2. Retry and DLT

When a record fails and retries, the partition may not advance at normal pace; with blocking retries, the partition can even be blocked by a poison record. `ListenerContainerPartitionIdleEvent` does not replace retry metrics, error handlers, DLTs, and committed offsets.

Non-blocking retries route records through retry topics; idle on the main topic does not mean the record succeeded on the retry topic. Monitor main, retry, and DLT topics under their respective groups/topics.

### 15.3. Kafka transactions

With a Kafka transactional listener, a record can be received and the listener executed yet the Kafka transaction ultimately rolls back. Idle events only reflect **record-receipt activity**, not that offsets or output transactions committed.

When end-to-end assurance is required, verify:

- Output topics with a `read_committed` consumer.
- Group committed offsets.
- Recovery/`AfterRollbackProcessor` outcomes.
- DLT records once retries are exhausted.
- Business database state and idempotency when side effects exist outside Kafka.

## 16. Logging and metrics for partition idle

An illustrative structured log:

~~~text
event_type=ListenerContainerPartitionIdleEvent
service=orders-worker
listener_id=orders-listener
group_id=orders-service
topic=orders.events
partition=2
idle_ms=60000
instance_id=orders-worker-3
observed_at=2026-11-15T16:00:00Z
~~~

Fields `service`, `group_id`, `instance_id`, and `observed_at` are metadata supplied by the application or enriched from runtime, not necessarily direct properties of the event.

Recommended metrics:

| Metric | Purpose |
|---|---|
| Partition idle event count | Track how often the container records idle. |
| Partition idle duration | Measure no-record duration per partition. |
| Partition currently idle gauge | Reflect latest state; reconcile on rebalance. |
| Records consumed per partition | Distinguish no data from low data. |
| Consumer lag per partition | Check whether partition stalls due to backlog or silent source. |
| Records produced per partition | Check upstream routing/key skew. |
| Partition pause state | Separate intentional idle from errors. |
| Consumer group assignment | Identify which member owns the partition. |
| Listener processing latency | Rule out overly slow consumer processing. |

Do not use topic-partition as an unbounded-cardinality metric if the cluster has hundreds of thousands of partitions. Consider aggregating by service, topic, and partition group with drill-down dashboards.

An alerting system should express **"partition expected to have data had none for X minutes,"** not "every idle partition is an error."

## 17. Integration testing with Embedded Kafka or Testcontainers

An integration test must verify Spring Kafka **actually publishes the event** when a partition receives no records within the threshold. A test calling `onPartitionIdle` directly does not prove the event is generated by the listener container.

How to build the test:

1. Create a topic with at least two partitions, e.g., `idle.test` with partitions 0 and 1.
2. Create a listener container with a short `idlePartitionEventInterval`, such as 1,000–2,000 ms.
3. Ensure the listener holds assignments for the partitions under test.
4. Send records steadily to partition 0, and none to partition 1.
5. Wait for `ListenerContainerPartitionIdleEvent` for partition 1 using a queue/latch.
6. Confirm partition 0 continues receiving records while partition 1 is idle.
7. Send a record to partition 1 and await the no-longer-idle event if supported by your version.
8. Stop the container and clean up consumer groups and topic/test resources.

### 17.1. Event-receiving probe

~~~java
@Component
public class PartitionIdleProbe {

    private final BlockingQueue<ListenerContainerPartitionIdleEvent> events =
            new LinkedBlockingQueue<>();

    @EventListener
    public void onIdle(ListenerContainerPartitionIdleEvent event) {
        events.offer(event);
    }

    public ListenerContainerPartitionIdleEvent await(Duration timeout)
            throws InterruptedException {
        return events.poll(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }
}
~~~

Key imports include `java.time.Duration`, `java.util.concurrent.BlockingQueue`, `LinkedBlockingQueue`, `TimeUnit`, and the Spring Kafka event class.

To avoid false positives when the context has many listeners, tests should filter by listener ID and topic-partition. A finite-deadline polling loop can be used:

~~~java
ListenerContainerPartitionIdleEvent matching = null;
long deadline = System.nanoTime() + Duration.ofSeconds(20).toNanos();

while (System.nanoTime() < deadline && matching == null) {
    ListenerContainerPartitionIdleEvent event =
            probe.await(Duration.ofMillis(500));

    if (event != null
            && event.getTopicPartition().topic().equals("idle.test")
            && event.getTopicPartition().partition() == 1) {
        matching = event;
    }
}

assertThat(matching).isNotNull();
~~~

This is a test fragment using the declared probe. Create the topic/factory/consumer group and start the listener in the test context before calling it; do not treat the standalone fragment as a complete program.

### 17.2. Testing partition receiving data again

You can send a record targeting a specific partition:

~~~java
kafkaTemplate.send("idle.test", 1, "key-1", "wake-up");
~~~

After partition 1 receives the record, the application can publish `ListenerContainerPartitionNoLongerIdleEvent`. The test should observe that event type or at least verify the listener received the record from partition 1.

For deterministic tests:

- Ensure partition 1 is already **assigned** to the listener under test.
- Use a dedicated consumer group for the test.
- Do not let other tests concurrently write to topic `idle.test`.
- Do not assert on exact wall-clock timestamps of events.
- Set finite timeouts, allowing for scheduling jitter.
- If verifying "partition 0 stays active," send multiple records to partition 0 throughout the observation window.
- Avoid long fixed sleeps; use queues/latches and condition-based waiting.

### 17.3. Testing pause and rebalance

Valuable additional tests:

- **Pause partition 1:** confirm events, lag, and pause state are not misinterpreted as upstream failure.
- **Rebalance:** add/remove consumers; verify the observer does not retain stale idle state for a newly revoked partition.
- **Concurrency > partition count:** confirm idle is not inferred from a consumer holding no partitions.
- **Slow listener processing:** verify event timing can be delayed; do not misattribute it to a stopped broker.
- **Container stop:** no further events arrive from the stopped container, and monitoring state is cleaned up.
- **Retry/DLT:** failing records travel through the retry pipeline; partition idle events are not used as success signals.

Do not run these tests by altering offsets or force-killing consumers on a group shared with other tests.

## 18. Common mistakes

- **Confusing partition idle with container idle:** other partitions may still have traffic.
- **Confusing idle with zero lag:** a partition may receive no records because of pause or slow processing while lag rises.
- **Confusing idle with a dead producer:** a topic/partition may normally have no new events.
- **Not configuring `idlePartitionEventInterval`:** the listener cannot be expected to emit events as desired automatically.
- **Setting the threshold too short:** events repeat excessively and cause alert storms.
- **Listening only to idle events and ignoring no-longer-idle:** metrics stay stuck in idle even after records return.
- **Not handling rebalances:** retaining idle state for partitions the consumer no longer owns.
- **Using the event to reset offsets/replay:** risks duplicates and corrupt business state.
- **Directly manipulating `KafkaConsumer` from an async event listener:** violates thread-ownership constraints.
- **Blocking the consumer thread inside an event handler:** causes poll latency, lag, or unintended rebalances.
- **Assuming the event confirms business processing succeeded:** transactions can still roll back.
- **Treating absence of events as proof the partition is healthy:** the container may be stopped or the observer unsubscribed.
- **Using in-memory events as durable audits:** a JVM crash loses unpersisted events.
- **Counting events as the number of failed producers:** multiple consumers/groups can emit events for one topic-partition.
- **Not filtering events by listener and partition in tests:** an event from another listener causes a false pass.

## 19. Workflow for diagnosing partition idle in production

When observing abnormal partition idle, proceed step by step:

1. **Confirm context:** topic, partition, listener ID, consumer group, and owning instance.
2. **Read lag:** separate "no new records" from "consumer falling behind."
3. **Check pause/resume:** was the container or partition intentionally paused?
4. **Check producer traffic per partition:** key skew, partitioner, upstream outage, or batch schedule.
5. **Inspect consumer state:** container running, poll latency, thread dumps if processing is blocked.
6. **Cross-check rebalance:** did the partition just change owner or is assignment still stabilizing?
7. **Check retries and deserialization errors:** are failing records looping or DLT rising?
8. **Evaluate business expectations:** is this partition required to receive records in the current window?
9. **Assign appropriate alert severity:** many cases only need dashboards, not incidents.
10. **Verify recovery:** records return, lag and processing metrics stabilize, and idle state updates.

If a partition has no records while both producer and broker confirm no new data, the system may be completely normal. If the producer confirms many records were written while the consumer receives none, investigate assignment, fetch, pause, committed offsets, deserialization, and consumer health.

## 20. Designing safe idle-tracking applications

A practical model:

~~~text
ListenerContainerPartitionIdleEvent
                |
                v
Spring @EventListener (lightweight handling)
                |
                +---- structured logs / idle metrics
                +---- update state by topic-partition and owner
                |
                +---- combine:
                        PartitionNoLongerIdleEvent
                        rebalance assignment
                        consumer lag
                        producer throughput
                        pause state
                        business SLA
                |
                v
Alert or operational workflow when sufficient evidence exists
~~~

Events should be **inputs to observability**, not the sole decision point for committing offsets, replaying data, or marking transactions successful. When the consumer group changes, update state for the new ownership; when records return, close the idle state; when the JVM crashes, external monitoring must still rely on committed offsets and broker data.

**`ListenerContainerPartitionIdleEvent`** gives Spring Kafka visibility into the silence of *a specific partition* even while the overall listener continues receiving records from other partitions. Its operational value lies in catching shards that stop behaving as expected early, while avoiding false conclusions by verifying lag, assignment, pause state, and upstream traffic before acting.
