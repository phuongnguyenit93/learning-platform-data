# Detecting partitions with no messages

In **Spring Kafka Reliability Operations**, a partition having **no messages** for a period of time can be a normal state, or it can be a sign that a producer stopped emitting events, key distribution is skewed, a consumer is not receiving data, a partition is paused, or a business flow is disrupted. Accurately detecting this condition helps operations teams distinguish **a topic genuinely lacking traffic** from **an inactive consumer** and **unprocessed backlog records**.

Spring Kafka provides idle events at both the **listener container level** and the **per-partition level**. To detect a specific partition that is not receiving records, the key is configuring `idlePartitionEventInterval` and observing `ListenerContainerPartitionIdleEvent` alongside the recovery event `ListenerContainerPartitionNoLongerIdleEvent` in supported versions.

However, **idle does not mean broken**. A partition may receive zero writes from producers due to key selection, operating schedules, or low traffic. Conversely, a consumer may keep polling successfully while receiving no new records; that is completely different from a hung consumer thread. Idle detection results must be evaluated in the context of **partition assignment, publish rate, offsets, consumer lag, SLA requirements, and pause state** before alerting or taking automated remediation.

## 1. What does a partition having no messages mean?

A Kafka topic is split into multiple partitions, each acting as an ordered log with its own offsets. A Kafka producer determines the target partition via keys and its partitioner, while a Kafka consumer group distributes partitions across consumer members.

Example topic `orders.events` with four partitions:

~~~text
orders.events
  partition 0: offset 100, 101, 102, 103, ...
  partition 1: offset  40,  41,  42, ...
  partition 2: offset  77,  78,  79, ...
  partition 3: offset  19,  20, ...
~~~

Suppose over the past 10 minutes partitions 0 and 1 continuously receive records, while partitions 2 and 3 receive none. There are at least three possibilities:

1. **No new records published to the partition:** this is genuine input log silence; it may be normal.
2. **Broker has records but the consumer cannot fetch them:** the consumer may be paused, lack read permissions, lack assignment, or encounter errors.
3. **Consumer receives records but business logic does not advance:** the listener is retrying a single offset, downstream is slow, or offsets are not committing; this scenario does not necessarily emit idle events.

Therefore, separate these concepts:

| Symptom | Direct observation | Must not infer |
|---|---|---|
| Partition has no new records | Partition end offset does not advance during observation window | Consumer is hung or broker is down. |
| Partition delivers no records to consumer | Time since consumer last received a record exceeds threshold | Producer has definitely stopped publishing. |
| Listener container idle | Container received no records at all for configured duration | All partitions in the topic lack traffic. |
| Single partition idle | No records received from that partition for long enough per observer | Every other partition is also idle. |
| Consumer non-responsive | Unusually long poll intervals; consumer thread may be blocked | Topic has no messages. |
| Consumer lag growing | End offset moves ahead of committed offset | Producer stopped or a partition has no records. |

**The problem of "detecting a partition with no messages" has two layers:** detecting **the consumer seeing no messages on an assigned partition** and, if needed, verifying **whether the partition's Kafka log is still being appended to**.

## 2. Why observe at the partition level?

A single listener container can own multiple partitions. When one partition has continuous traffic, the container overall appears healthy even though other partitions receive no messages.

Example:

~~~text
Consumer A is assigned:
  orders.events-0: 200 records/min
  orders.events-1:   0 records/min
  orders.events-2: 150 records/min

Container A:
  still continuously receives records from P0 and P2
  -> container-wide idle event may never fire

Partition P1:
  no records for 15 minutes
  -> needs idle detection specifically for P1
~~~

If you only configure `idleEventInterval` for the container, operations teams can miss a silent partition while the container keeps receiving records from other partitions. Therefore, use **per-partition idle signals** when SLAs or business policies apply per partition.

Especially useful for:

- Topics with multiple partitions and uneven traffic distribution.
- Topics keyed by customer/order where one subset of keys may stop emitting events.
- Topics whose producers are expected to send heartbeats or periodic data.
- Reconciliation, IoT, shift-based event streams, or dedicated data channels.
- Suspected paused partitions or lost consumer assignments.
- Verifying the impact of partitioner or key-distribution changes.

Do not assume **every partition must receive records every minute** as a universal rule across all topics. For multi-partition low-traffic topics, silence on several partitions can be completely normal.

## 3. Spring Kafka: idleEventInterval vs idlePartitionEventInterval

Spring Kafka provides lifecycle properties in `ContainerProperties`. Two easily confused settings:

| Property | Observation scope | Related events |
|---|---|---|
| `idleEventInterval` | **Entire listener container** receives no records for configured duration | `ListenerContainerIdleEvent` and `ListenerContainerNoLongerIdleEvent`. |
| `idlePartitionEventInterval` | **Each topic-partition tracked by the consumer container** receives no records for configured duration | `ListenerContainerPartitionIdleEvent` and `ListenerContainerPartitionNoLongerIdleEvent`. |
| `monitorInterval` / `noPollThreshold` | Monitors **hung or non-responsive poll loops** | `NonResponsiveConsumerEvent`, not a partition idle event. |

Event names and availability depend on Spring Kafka version. For `idlePartitionEventInterval`, verify that your version supports both the interval and per-partition events.

### Configuration example via listener container factory

~~~java
@Configuration
public class KafkaIdleMonitoringConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
                new ConcurrentKafkaListenerContainerFactory<>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        // Alert when the entire consumer container receives no records.
        factory.getContainerProperties().setIdleEventInterval(60_000L);

        // Track each assigned partition separately.
        factory.getContainerProperties()
                .setIdlePartitionEventInterval(30_000L);

        return factory;
    }
}
~~~

Common imports include `ConcurrentKafkaListenerContainerFactory`, `ConsumerFactory`, and `Configuration`. `OrderEvent` is an application-defined DTO.

In this example:

- `idleEventInterval=60000` sets container-wide idle observation to 60 seconds.
- `idlePartitionEventInterval=30000` sets per-partition idle observation threshold to 30 seconds.
- `concurrency=3` creates up to three child consumers matching the group's partition assignment capacity.
- Each child consumer directly observes only the partitions assigned to it, not every partition in the cluster.

**The thresholds above are illustrative only.** Actual thresholds must match expected message cadence and tolerable business delay.

Listener using this factory:

~~~java
@KafkaListener(
        topics = "orders.events",
        groupId = "orders-service",
        containerFactory = "ordersListenerFactory")
public void onOrderEvent(OrderEvent event) {
    orderService.processIdempotently(event);
}
~~~

When the listener still receives records on one partition but none on another, idle events for the quiet partition can fire even while the container as a whole is not considered idle.

## 4. ListenerContainerPartitionIdleEvent: meaning and timing

`ListenerContainerPartitionIdleEvent` is emitted by Spring Kafka when **a topic-partition tracked by the container receives no records for long enough** per `idlePartitionEventInterval`.

Example:

~~~text
Time:
  10:00:00  orders.events-2 receives last record
  10:00:30  No new records from P2
  10:00:30+ Spring Kafka may emit PartitionIdleEvent(P2)
  10:01:00+ If still idle, may emit subsequent events per check schedule

Meanwhile:
  orders.events-0 still receives records steadily
  orders.events-1 still receives records steadily
~~~

The event is emitted based on **the absence of records observed by the listener container**, not broker confirmation that producers stopped writing to the partition. Actual emission timing can drift from the threshold due to poll cycles, scheduling, and framework idle-check mechanics.

Events can fire **repeatedly** while the partition remains idle. Never build an alerting system that treats every repeated event as a brand-new incident.

### What information does the event carry?

Partition idle events in Spring Kafka typically provide topic-partition, idle duration, listener/container info, and consumer context per the version's API. When writing an event handler, check actual method signatures before accessing those fields.

Conceptual example recording a specific partition:

~~~java
@Component
public class PartitionIdleObserver {

    private static final Logger log =
            LoggerFactory.getLogger(PartitionIdleObserver.class);

    @EventListener
    public void onPartitionIdle(ListenerContainerPartitionIdleEvent event) {
        log.warn(
                "Kafka partition idle: partition={}, idleTimeMs={}",
                event.getTopicPartition(),
                event.getIdleTime());
    }
}
~~~

The example relies on common accessors of Spring Kafka partition-idle events; verify exact methods in your project's Spring Kafka version. `getIdleTime()` is the idle duration reported by the event, **not the number of lost records**.

### Distinguishing poll time from business event time

Records can carry a Kafka timestamp assigned by the producer or recorded by the broker. When detecting idle, Spring Kafka observes how long it has been since **receiving** a record, without inspecting how old a business `event.createdAt` field is.

If a producer writes a backlog record carrying last week's timestamp, the container still just received that record now. Thus, when checking for "no new messages", be explicit:

- **No new records received by processing/receive time**.
- **No new business events by event time**.
- **No new Kafka records appended to the partition**.

These three metrics answer three different questions.

## 5. ListenerContainerPartitionNoLongerIdleEvent: partition resumes activity

When a previously idle partition starts delivering records to the container again, Spring Kafka can emit `ListenerContainerPartitionNoLongerIdleEvent` in supported versions.

This event helps close out the idle state:

~~~text
P2:
  10:00  receives last record
  10:01  idle event: mark P2 IDLE
  10:02  still no records
  10:03  new record arrives
         -> partition no-longer-idle event
         -> mark P2 ACTIVE per receive observation
~~~

Illustrative observer:

~~~java
@Component
public class PartitionActivityObserver {

    private static final Logger log =
            LoggerFactory.getLogger(PartitionActivityObserver.class);

    @EventListener
    public void onIdle(ListenerContainerPartitionIdleEvent event) {
        log.warn("Partition became idle: {}",
                event.getTopicPartition());
    }

    @EventListener
    public void onNoLongerIdle(
            ListenerContainerPartitionNoLongerIdleEvent event) {
        log.info("Partition received records again: {}",
                event.getTopicPartition());
    }
}
~~~

A no-longer-idle event only proves **the container received a record**. That record might still fail deserialization, fail listener processing, get retried, or be routed to a DLT. Add **business success / committed offset** metrics if you want to close a business incident completely.

Do not mark the entire consumer group HEALTHY simply because one partition became no-longer-idle: other partitions may remain idle or other consumers may still be failing.

## 6. When do no events fire even though a partition has no messages?

Never treat "no idle event seen" as proof that the topic has data. Possible reasons include:

1. `idlePartitionEventInterval` is not configured or unsupported in the Spring Kafka version.
2. The listener does not use the container factory you configured.
3. The partition is not assigned to this consumer.
4. The consumer/container is stopped or not polling; normal idle events stop firing as they do when active.
5. The consumer is paused; event behavior and paused info must be checked per version.
6. The consumer repeatedly re-reads a poison pill at the same offset: records are redelivered, yet business progress stalls.
7. Another consumer took over the partition after a rebalance.
8. The application event observer is not registered in the right Spring context or the event multicaster failed.
9. The idle threshold is too long relative to the observation window.
10. Records arrive very sparsely yet steadily just before reaching the threshold.

If a partition is unassigned across the group, idle events emitted by live listeners are **not a cluster-wide monitoring tool**. When you need to check unassigned partitions as well, use an independent observer at the Kafka topic/group level.

## 7. Idle does not mean NonResponsiveConsumerEvent

This distinction is the most important operational concept:

**Idle:** the consumer **is still polling**, yet receives no records. It can be completely healthy if the producer sends no data.

**Non-responsive:** the consumer thread **fails to return to poll on schedule**, potentially due to a blocked listener, blocking retry, deadlock, or long I/O. The topic may still hold plenty of records while lag grows.

~~~mermaid
flowchart TD
    A[Listener sees partition has no records] --> B{Consumer still polling on cadence?}
    B -->|No| C[Investigate NonResponsiveConsumerEvent]
    C --> D[Listener timeout, retry, deadlock, GC, max.poll.interval.ms]
    B -->|Yes| E{Partition still assigned and not paused?}
    E -->|No| F[Investigate assignment, rebalance, pause/resume]
    E -->|Yes| G{Log end offset still increasing?}
    G -->|No| H[Producer not publishing to partition or low traffic]
    G -->|Yes| I[Investigate fetch, permissions, lag, and committed offset]
~~~

Spring Kafka offers `NonResponsiveConsumerEvent` and settings like `monitorInterval` and `noPollThreshold` to watch for consumers failing to poll as expected. They do not replace per-partition idle events.

Examples:

| Scenario | Partition idle | Non-responsive consumer | Lag |
|---|---|---|---|
| Producer sends no records, consumer polls normally | Possible | No | Generally does not grow. |
| Listener hangs on an API call, broker has new records | May emit no new event | Possible | May grow. |
| Consumer pauses partition while still polling | Depends on event mechanics/version | Not necessarily | May grow if producer keeps publishing. |
| One partition has no traffic, two others receive steadily | Per-partition idle event possible | No | Idle partition may have lag = 0. |
| Failing record retried repeatedly | Not necessarily idle due to redelivery | Possible if retries block poll too long | Offset may stay flat. |

An alert that only says "Kafka idle" without distinguishing the two types will send operations teams in the wrong direction.

## 8. Container idle and partition idle are two scopes

`ListenerContainerIdleEvent` indicates **the container** received no records during `idleEventInterval`. With a consumer managing multiple partitions, receiving a record from any single partition can prevent container-wide idle even when another partition has no data.

`ListenerContainerPartitionIdleEvent` lets you track each topic-partition independently.

Example:

~~~text
orders.events
  P0: 1,000 records/min
  P1:     0 records/min
  P2:    30 records/min

Child consumer C0:
  assigned P0, P1, P2

Container-wide idle?
  No, because records arrive on P0/P2.

Partition-idle?
  May fire for P1 once threshold is exceeded.
~~~

When a topic has very low traffic and many partitions, avoid setting per-partition thresholds too short. A partition not selected by key hashing for 10 minutes can be completely normal.

## 9. How does idle tracking behave when partition assignments change?

Within a consumer group, partitions can move to another member due to startup, scaling, rebalances, timeouts, or rolling deployments.

~~~text
T1: Consumer A assigned P1, receives no records for 5 minutes.
T2: Group rebalances, P1 moves to Consumer B.
T3: Consumer B starts polling P1.

A:
  no longer holds observation/read ownership of P1.

B:
  observes P1 under B's fresh lifecycle.
~~~

Therefore, do not leave a "Consumer A missing messages on P1" alert open indefinitely after P1 moved ownership. Good monitoring ties state to **topic-partition + consumer group + current assignment** and updates ownership on rebalance.

### Integrating with lifecycle callbacks

- `onPartitionsAssigned`: mark partitions the consumer now owns; initialize tracking state for the new owner.
- `onPartitionsRevoked`: stop treating the current consumer as owner of revoked partitions.
- `onPartitionsLost`: the consumer lost ownership; do not attempt commits/access as a valid owner.
- `ConsumerStoppedEvent`: the consumer stopped; close or invalidate container-scoped tracking state.
- `ListenerContainerPartitionIdleEvent`: a currently tracked partition has received no records past the idle threshold.

With cooperative rebalancing, partitions whose owner did not change may be retained. Do not wipe all partition state on every assigned/revoked callback; update only the affected partitions.

## 10. Distinguishing producer not publishing from consumer not fetching

When a per-partition idle event fires, the key verification step is **comparing log end offsets over time**, not looking at a single snapshot.

Suppose for P1:

~~~text
T1: end offset = 500
T2: end offset = 500
T3: end offset = 500

=> No log appends observed during that window.

T1: end offset = 500
T2: end offset = 530
T3: end offset = 560

=> Broker received new records; if consumer gets none, investigate fetch/assignment/pause.
~~~

How to interpret:

| End offset | Committed offset | Interpretation |
|---|---|---|
| Flat | Equal or close to end offset | Likely genuinely no new data; consumer caught up. |
| Rising | Flat | Backlog growing; consumer may be slow, paused, or failing. |
| Rising | Rising together | Data and consumer both advancing; if idle event appears, check identity/window/owner. |
| Flat | Commit still far behind end offset | Existing old backlog unprocessed; do not call the partition healthy just because the producer is quiet. |

**Committed offset** is the group's next position to read, not the timestamp of the last processed record. **End offset** reflects the end of the log per the corresponding API/isolation level; with Kafka transactions there is also a distinction between log end offset and last stable offset. When computing lag, use consistent offset types and sources.

### Where to obtain end offsets?

Use Kafka admin tools or `AdminClient.listOffsets` from an **independent monitoring component**, per your Kafka client API. Do not spin up a new `KafkaConsumer` sharing the same `group.id` solely for observation, as subscribing with it can join the group and trigger rebalances.

Never repeatedly call `endOffsets(...)` from a synchronous `@EventListener` on the consumer thread: that involves network I/O and slows down the poll loop. Sample broker offsets on a separate schedule and correlate with idle events.

Architectural pattern example:

~~~mermaid
flowchart LR
    P[Producer] --> K[Kafka topic partitions]
    K --> C[Spring Kafka consumers]
    C --> I[Partition idle events]
    K --> A[AdminClient offset sampler]
    I --> M[Monitoring state]
    A --> M
    M --> R{SLA traffic/lag breached?}
    R -->|No| N[Normal / expected quiet]
    R -->|Yes| O[Contextual alert]
~~~

If you want to monitor logs of **all partitions**, including unassigned ones, a broker-side offset observer is the essential complement.

## 11. Key distribution: a silent partition can be normal

Kafka producers typically choose partitions based on key/partitioner. Records sharing the same key generally route to the same partition to preserve per-key ordering. This can produce highly skewed distributions.

Example business topic keyed by `customerId`:

~~~text
Customer A has 100,000 events -> P0
Customer B has 1 event       -> P2
Customer C has no events     -> generates no traffic
P1 may receive zero records for minutes
~~~

If user traffic concentrates on certain keys, other partitions can stay idle even when the system is healthy. Increasing partition count does not guarantee balanced load across records.

### When is idle abnormal?

- The topic is designed with **periodic producer heartbeats per partition**.
- Producers follow a contract writing data to fixed shards/partitions.
- Each partition serves a specific data source and SLAs require updates from every source.
- A partition that steadily received high-frequency data suddenly receives none for a long time.
- After a producer deployment, many partitions go idle simultaneously while one spikes: suspect a key/partitioner change.
- End offset stops advancing on a partition that must receive data, even though upstream confirms events were generated.

### When should you not alert?

- The topic only receives traffic during business hours.
- Sparse traffic across a large partition count.
- Certain keys naturally generate no business events during quiet periods.
- The topic uses natural key distribution with hot and cold partitions.
- Planned maintenance is underway during a documented maintenance window.

Alerting on **business expectations** is far more reliable than alerting on "any partition idle over 60 seconds".

## 12. Choosing an appropriate idle threshold

The `idlePartitionEventInterval` threshold should be based on expected inter-arrival time **per individual partition**, not just aggregate topic rate.

A mental model:

~~~text
Expected records / partition / minute
  = topic_records_per_minute
    × expected_share_of_that_partition

Idle threshold
  > expected inter-arrival time
    + traffic variance
    + margin for network/scheduling
~~~

This formula is just a thinking framework. If traffic is uneven or bursty, use empirical per-partition distributions (p95/p99 inter-arrival times) rather than dividing total records evenly by partition count.

Comparison examples:

| Workload | Normal data cadence | Alert design guidance |
|---|---|---|
| Continuous CDC/event ingestion | Steady records every few seconds per shard | Threshold per expected shard throughput, check end offset. |
| Business-hours transactions | Natural quiet gaps overnight | Schedule-aware alerting; suppress during quiet hours. |
| Per-partition heartbeat | Periodic heartbeat on each partition | Threshold larger than heartbeat period plus jitter. |
| Many partitions, very low traffic | Partitions go hours without records | Do not alert per partition unless a dedicated business SLA exists. |
| Daily batch ingestion | Data arrives only during batch window | Track batch completion time and freshness, not second-level idle thresholds. |

Use **two thresholds**: technical detection time and business alerting time. For instance, emit idle events after 30 seconds for telemetry, but only alert if a critical partition receives no records past a 10-minute SLA while end offsets remain flat.

## 13. Repeated idle events: preventing alert storms

While a partition stays idle, Spring Kafka can emit multiple idle events per interval. If every event sends an email or page, a topic with hundreds of partitions will cause an alert storm.

Design around a state machine:

~~~mermaid
stateDiagram-v2
    [*] --> UNKNOWN
    UNKNOWN --> ACTIVE: Record arrives / baseline sufficient
    UNKNOWN --> IDLE: Exceeded idle threshold
    ACTIVE --> IDLE: PartitionIdleEvent
    IDLE --> IDLE: Repeated idle events
    IDLE --> ACTIVE: PartitionNoLongerIdleEvent
    ACTIVE --> UNKNOWN: Assignment lost / stop
    IDLE --> UNKNOWN: Assignment lost / stop
~~~

Emit alerts/notifications only on state transitions when warranted; use repeated idle events to update `lastObservedIdleAt` or idle duration.

### Keying state per partition

When tracking multiple consumer groups, a straightforward state key is:

~~~text
Cluster + Environment + ConsumerGroup + Topic + Partition
~~~

To distinguish ownership/rebalances, add listener ID or owner generation in separate metadata. Never key solely by partition number, since partition 0 exists across many topics, groups, and clusters.

### Example in-application state tracker

~~~java
public record PartitionKey(String topic, int partition) { }

@Component
public class PartitionIdleState {

    private final Set<PartitionKey> idle =
            ConcurrentHashMap.newKeySet();

    @EventListener
    public void onIdle(ListenerContainerPartitionIdleEvent event) {
        TopicPartition tp = event.getTopicPartition();
        PartitionKey key = new PartitionKey(tp.topic(), tp.partition());

        if (idle.add(key)) {
            log.warn("Partition entered idle state: {}", key);
        }
    }

    @EventListener
    public void onActive(
            ListenerContainerPartitionNoLongerIdleEvent event) {
        TopicPartition tp = event.getTopicPartition();
        PartitionKey key = new PartitionKey(tp.topic(), tp.partition());

        if (idle.remove(key)) {
            log.info("Partition resumed receiving records: {}", key);
        }
    }
}
~~~

This is a minimal example illustrating duplicate-alert suppression. In production, distinguish cluster/group/listener when the same application context hosts multiple event sources, clean up state on revoke/stop, and persist or centrally aggregate state if restarts discard memory.

Never treat an in-memory map as **cluster-wide source of truth**; multiple pods hold different state copies and consumer assignments shift across rebalances.

## 14. Useful metrics when investigating partition idle

| Metric or signal | Scope | What it helps conclude |
|---|---|---|
| Last received timestamp | Topic-partition at consumer | Most recent time the container received a record from the partition. |
| Idle duration | Topic-partition at consumer | Duration without records as reported by events. |
| Kafka log end offset | Topic-partition at broker | Current log position and whether appends happened during the window. |
| Committed offset | Consumer group + topic-partition | Where the group currently stands. |
| Consumer lag | Group + topic-partition | Offset gap to end/LSO under the corresponding measurement. |
| Records consumed rate | Kafka consumer or client metrics | Consumer receipt rate; watch granularity. |
| Partition assignment | Consumer group | Which consumer currently owns the partition. |
| Paused partitions | Container/consumer | Whether fetching was intentionally halted on the partition. |
| Rebalance count/duration | Consumer group | Whether ownership churn disrupted data delivery. |
| Nonresponsive poll signals | Consumer/container | Whether a poll thread is hung or blocked. |
| Producer send rate/errors | Producer/topic | Whether the producer is actually publishing successfully to Kafka. |

For metric labels, keep `topic`, `partition`, `group`, and `environment` bounded; watch cardinality with large topic/partition counts. Avoid `eventId`, `customerId`, or `orderId` as metric labels.

### Last received time vs last produced time

An application might store `lastReceivedAt` in the listener using the incoming record's timestamp. However, Kafka record timestamps may reflect when the producer created the event earlier; treating that as "last received" skews idle duration.

Distinguish clearly:

- `lastReceivedAt`: timestamp when the **consumer** received the record.
- `record.timestamp()`: Kafka timestamp attached to the record.
- `event.createdAt`: business creation timestamp.
- `lastBrokerAppendObservationAt`: timestamp when monitoring observed log end offset advance.

For business freshness goals, you may need to combine multiple timestamps.

## 15. Consumer pause: a special case

Spring Kafka allows pausing a listener/container or specific partitions in applicable scenarios. Pausing lets the consumer retain group membership and keep polling while temporarily receiving no records from paused partitions.

For example, an application uses pause for backpressure when the database is overloaded. While paused:

- Producers may still append records to the partition.
- Broker end offsets may continue climbing.
- The consumer receives no new records from the partition while paused.
- Lag may grow.
- Listener idle signals may fire or behave according to how Spring Kafka handles pause state in your version.

Never fire a "producer stopped" alert when the real cause is **an intentionally paused consumer**.

### How to handle it

1. Check whether the container/partition is `paused` or `pauseRequested`.
2. Read the pause reason: backpressure, retry, maintenance, or operator action.
3. Inspect when it was paused and the resume policy.
4. Watch broker end offsets and lag.
5. Resume when downstream is ready; do not skip records.
6. Verify the listener receives records again and offsets advance per policy.

Never call `KafkaConsumer.resume(...)` from an unmanaged background thread. Use the corresponding container API with lifecycle/poll coordination supported by Spring Kafka.

## 16. Record retries can mask a stalled partition

If a listener reads offset 500 and fails repeatedly, the error handler may redeliver the same record many times. In that situation:

- The consumer **receives redelivered records**.
- The partition may **not be classified as idle** by record-receipt tracking.
- Committed offset may stay pinned at 500 or earlier.
- Producers may keep writing new records, causing lag to grow.
- The listener may be stuck on a single poison pill without advancing offsets.

Therefore, detecting a "non-progressing" partition requires an additional detector based on **committed offset remaining flat while end offset rises** or **processing success stalling**, rather than relying solely on idle events.

Example:

~~~text
P1:
  End offset       1,000 -> 1,200 -> 1,500
  Committed offset   500 ->   500 ->   500
  Listener retries offset 500 repeatedly

=> P1 is not idle in the no-records-received sense,
   yet actual processing is stuck.
~~~

When investigating, classify exceptions as transient or permanent, inspect `DefaultErrorHandler`, DLT recovery, and backoff. Never skip offset 500 via manual seek/commit without a valid recovery policy.

## 17. Are heartbeat signals really necessary?

For topics where every partition **must** have a periodic signal, businesses sometimes emit heartbeats. However, Kafka does not automatically send heartbeats to every partition if producers publish keyless records or use standard key hashing.

To achieve per-partition heartbeats, producers must explicitly route records to each partition, or an observability service must evaluate broker-level data. Consider the trade-offs:

- Heartbeats increase throughput, storage cost, and consumer processing overhead.
- Heartbeats can affect topic ordering/offsets.
- Consumers must recognize heartbeats and avoid executing business logic on them.
- Heartbeats must never hide the loss of real business events.
- A live producer heartbeat does not prove the business data pipeline succeeded.
- Adding new partitions requires updating heartbeat routing accordingly.

In many systems, **monitoring end offsets and business freshness** is cleaner than injecting heartbeat records into every partition.

### When a partition represents a single data source

If partitions map 1:1 to shards/sources and each shard has its own SLA, per-partition monitoring is fairly accurate. If partitions are simply random key-hash buckets, SLAs belong on the **business source** or aggregate rather than arbitrary partition numbers.

## 18. Testing per-partition idle with Spring Kafka Test

Test both idle detection and idle exit when records resume, in an integration environment with an appropriate test Kafka broker.

A scenario using a two-partition `orders.events` topic:

1. Create a two-partition topic in the test environment and a dedicated test consumer group.
2. Configure `idlePartitionEventInterval` short enough for tests yet allowing scheduling margin.
3. Start the listener container and wait for partition assignment to stabilize.
4. Publish records to partition 0 while **publishing nothing to partition 1**.
5. Wait for `ListenerContainerPartitionIdleEvent` for partition 1.
6. Verify the listener container remains active and processes partition 0.
7. Publish a record to partition 1.
8. Verify `ListenerContainerPartitionNoLongerIdleEvent` or record receipt resumption per supported version.
9. Cross-check committed offsets and record processing success.
10. Stop the container, ensuring test observers leave no dangling background threads or queues hanging shutdown.

Example producer targeting specific partitions:

~~~java
kafkaTemplate.send(
        new ProducerRecord<>("orders.events", 0, "order-A", payloadA));

// Keep partition 1 without records during the test window.

kafkaTemplate.send(
        new ProducerRecord<>("orders.events", 1, "order-B", payloadB));
~~~

`payloadA` and `payloadB` are test payloads with matching serializers. Tests must wait for assignment before measuring idle so startup time is not mistaken for silence.

### Event recorder for tests

~~~java
@Component
public class PartitionIdleEventRecorder {

    private final BlockingQueue<TopicPartition> idleEvents =
            new LinkedBlockingQueue<>();

    @EventListener
    public void onPartitionIdle(ListenerContainerPartitionIdleEvent event) {
        idleEvents.offer(event.getTopicPartition());
    }

    public TopicPartition awaitIdle(long timeout, TimeUnit unit)
            throws InterruptedException {
        return idleEvents.poll(timeout, unit);
    }
}
~~~

This is a conceptual test helper. Import `java.util.concurrent` types and Kafka `TopicPartition`, and verify event APIs for your version. In tests, use bounded waits with finite timeouts instead of arbitrary `Thread.sleep` or absolute-timestamp assertions.

If a topic has multiple partitions, verify the **exact partition** reported idle rather than merely asserting any idle event arrived. Spring Kafka Test / EmbeddedKafka setup details can vary across Spring Boot/Spring Kafka versions.

## 19. Fault injection: testing differentiation of no-data modes

| Experiment | How to induce | Expected signals |
|---|---|---|
| Silent producer | Send no records to assigned partition | Partition idle event may fire; broker end offset stays flat. |
| Single silent partition | Send steadily to P0, nothing to P1 | Container remains active; P1 goes idle individually. |
| Whole container idle | Send nothing to any assigned partition | Both container idle and partition idle events may fire. |
| Blocked listener | Controlled block inside test listener | Poll becomes non-responsive; needs dedicated monitor, not just idle. |
| Paused partition | Pause P1 via container API | Consumer still polls, P1 gets no records; inspect pause state. |
| Poison pill retry | Listener repeatedly throws on one offset | Offset stalls and lag may grow despite redelivery. |
| Rebalance | Add another consumer member to group | Ownership shifts; idle state must update per assignment. |
| Consumer stopped | Stop container via lifecycle | Do not treat absence of idle events as topic having data. |

Never run fault injection against production consumer groups or live Kafka clusters serving real traffic, as it can trigger rebalances, duplicate deliveries, and backlogs.

## 20. Operating with multiple replicas

A service runs across multiple pods, each with its own listener concurrency. Each child container tracks only its currently assigned partitions, so idle events can come from different pods after rebalances.

Example:

~~~text
Replica A: P0, P1
Replica B: P2, P3

T1: P1 idle -> Replica A emits event.
T2: Rebalance, P1 moves to Replica B.
T3: If P1 stays idle, Replica B becomes the new observer.
~~~

Centralized alerting must group events by **topic + partition + group** and track the current owner to avoid opening duplicate incidents when a partition moves pods. Include metadata such as assignment generation and observation timestamp whenever possible.

If the same topic is read by two distinct consumer groups, a partition can be idle in group A yet active in group B due to pause, offset reset, or different processing. **Never merge idle events from two groups into one incident** if they serve separate purposes.

## 21. Designing contextual alerts

A useful alert should answer:

- Which topic, partition, and consumer group are affected?
- Was it detected by a per-partition idle event or a broker offset sampler?
- Is that partition assigned? Who is the current owner?
- Is the consumer still polling or non-responsive?
- Is the partition intentionally paused?
- Did the broker end offset advance in the corresponding window?
- What are the committed offset and lag?
- Is traffic on this partition expected per SLA?
- Is there an associated deployment, broker outage, producer change, or maintenance window?

Example severity classification:

| State | Evidence | Action |
|---|---|---|
| Expected quiet | No traffic per business schedule, end offset flat | Record only, do not page. |
| Suspicious producer silence | Partition requires data yet end offset is flat | Alert producer owner or upstream. |
| Consumer delivery issue | End offset rising yet consumer gets nothing despite assignment | Investigate pause, auth, fetch, polling, and group. |
| Processing stalled | End offset rising, committed offset flat, repeated retries | Investigate listener, error handler, DLT. |
| Consumer non-responsive | Abnormal poll interval, thread blocked | Investigate timeouts, GC, deadlocks, max.poll.interval. |
| Recovery | Partition receives records again and processing/offsets advance | Close incident after stability window. |

Never apply one global idle threshold to every partition if traffic distribution differs drastically.

## 22. Runbook: One partition idle while others work fine

1. Record topic, partition, group, listener ID, idle duration, and emitting instance.
2. Check whether the partition is in the consumer's current assignment.
3. Check pause status on the partition and container.
4. Compare broker end offsets at two points in time rather than a single snapshot.
5. Inspect producer metrics and key/partition selection logic.
6. Check operating schedules, business SLAs, and natural low-traffic patterns.
7. If the producer is expected to emit events yet end offset is flat, investigate upstream/producer.
8. If end offset rises, investigate consumer fetch, auth, assignment, retries, and lag.
9. When data resumes, confirm partition no-longer-idle and actual processing/commit progress.

Never reset offsets or change partitioners immediately before knowing the root cause.

## 23. Runbook: Whole topic suddenly goes silent

1. Determine whether all partitions stopped advancing end offsets or only the listener group stopped receiving records.
2. Check producer deployments, publish rates, send failures, credentials, ACLs, and broker health.
3. Correlate silence onset with maintenance schedules or upstream outages.
4. Verify the consumer group has active members and complete partition assignments.
5. Check container idle events, poll health, consumer lag, and paused state.
6. If the Kafka log is not growing, focus on producer/upstream instead of repeatedly restarting consumers.
7. If the log grows while consumers get nothing, focus on consumer, network, and security.
8. Upon recovery, monitor backlog catch-up and event freshness—don't just wait for idle events to disappear.

## 24. Runbook: Repeated partition idle events causing alert storms

1. Verify effective `idlePartitionEventInterval` and partition count.
2. Check whether repeated events on the same topic-partition are opening a new incident each time.
3. Enforce state transitions `ACTIVE → IDLE → ACTIVE`, alerting only on transitions or SLA breaches.
4. Check whether the threshold is shorter than actual record cadence.
5. Group events by cluster, group, topic, partition, and timestamp.
6. Incorporate business/maintenance schedules and partition groups with dedicated SLAs.
7. Monitor observer latency and log volume to protect consumer threads.

## 25. Runbook: Partition paused yet backlog exists

1. Determine whether the pause is container-level or partition-level, who requested it, and since when.
2. Read logs/backpressure state from downstream or the retry subsystem.
3. Compare end offset against committed offset to quantify backlog.
4. Decide whether the pause is still needed and whether downstream has recovered.
5. Resume using Spring Kafka's container API on an appropriate thread/lifecycle.
6. Monitor consumption rate, listener errors, and offset progression.
7. Check idle/no-longer-idle events per version and never treat them as the sole resume condition.

Never force a resume while downstream remains overloaded or transactions are unstable.

## 26. Runbook: Committed offset stalled despite no idle events

1. Check whether new records are arriving in the topic-partition.
2. Check whether the listener is receiving and retrying the exact same offset repeatedly.
3. Inspect exception types, `DefaultErrorHandler`, backoff, and DLT publish results.
4. Check whether the listener offloads incomplete async work that delays acks.
5. Check for Kafka transaction aborts/fencing if using transactions.
6. Monitor consumer poll intervals and `NonResponsiveConsumerEvent`.
7. Fix the business/infrastructure fault or perform controlled recovery.
8. Never commit past unprocessed records without an approved recovery policy.

## 27. Runbook: Partition emits no idle event after rebalance

1. Check which consumer currently owns the partition assignment.
2. Confirm the new container has `idlePartitionEventInterval` and the right listener factory configured.
3. Check whether enough time has elapsed since assignment relative to the interval.
4. Check whether the consumer/container is started or stopped/paused.
5. Verify the `@EventListener` observer lives in the same application context.
6. Inspect logs, the application event multicaster, and executors if running asynchronously.
7. Never initialize idle state from the previous owner's data without checking owner generation.
8. Add an independent broker offset sampler when cluster-wide visibility is needed.

## 28. Runbook: Producer key change suddenly leaves many partitions idle

1. Compare per-partition record distribution before and after the producer deployment.
2. Inspect changes to key serializers, nullable keys, partitioners, and partition counts.
3. Identify whether certain keys became hot or all records collapsed onto one partition.
4. Check aggregate ordering requirements before changing keys.
5. Inspect consumer lag and throughput per partition: a hot partition can become a bottleneck.
6. Restore the partitioner/business key per contract or apply a controlled design change.
7. Never synthesize fake records to hide idle metrics while real data remains skewed.
8. Monitor distribution and idle rates across several traffic cycles after fixing.

## 29. Control checklist for detecting partitions with no messages

| Checkpoint | Question to answer | Evidence |
|---|---|---|
| Idle configuration | Is `idlePartitionEventInterval` enabled on the right container factory? | Effective container properties and event logs. |
| Event scope | Are you using partition idle or container idle events? | Event type and topic-partition metadata. |
| Assignment | Is the partition assigned to the observed consumer? | Group assignment and rebalance logs. |
| Poll health | Is the consumer continuing to poll on cadence? | Poll metrics, `NonResponsiveConsumerEvent`. |
| Pause | Is the partition/container intentionally paused? | Container pause state and reason. |
| Broker input | Is the end offset advancing over time? | AdminClient/broker offset samples. |
| Consumer progress | Are committed offsets and lag advancing? | Group offsets, error handler logs. |
| Producer skew | Are keys/partitioners leaving a partition cold? | Per-partition producer rates, key distribution. |
| SLA | Must this partition actually receive messages in this window? | Business schedule, heartbeat/freshness contract. |
| Retry/DLT | Is a poison pill or retry holding the offset? | Attempt counts, DLT send results, exception classes. |
| Lifecycle | Did a rebalance/stop make monitoring state stale? | Assigned/revoked/lost and container events. |
| Alert quality | Are repeated events causing an alert storm? | State transitions, deduplication, and alert history. |
| Recovery | Are returning records processed/committed successfully? | No-longer-idle events, processing rate, committed offsets. |

**Conclusion:** Detecting partitions with no messages requires observing **individual partitions**, not merely overall listener container state. Spring Kafka supports `idlePartitionEventInterval` together with `ListenerContainerPartitionIdleEvent` and `ListenerContainerPartitionNoLongerIdleEvent` to signal when a managed partition stops and resumes receiving records. Yet idle events only reflect **not receiving records**—they do not by themselves prove a producer stopped or business processing failed. For accurate operations, combine assignments, pause state, poll health, log end offsets, committed offsets, consumer lag, and traffic SLAs. Only by separating **expected quiet**, **producer silence**, **consumer delivery issues**, and **processing stalls** can a system alert accurately and recover without dropping or duplicating messages.
