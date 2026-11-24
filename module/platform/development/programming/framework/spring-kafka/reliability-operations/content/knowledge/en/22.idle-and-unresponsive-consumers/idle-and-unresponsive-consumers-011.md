# Getting current position when idle

## 1. The problem: what offset is the consumer at while idle?

In Spring Kafka, a listener container can be running normally yet receive no additional records from Kafka for a period of time. When the silence exceeds the configured threshold, Spring Kafka can emit `ListenerContainerIdleEvent`. At that moment, operators often want to know:

- What **offset on each partition** is the consumer currently sitting at?
- Has the consumer read all available data or is there still a backlog?
- Does the current position match the consumer group's committed offset?
- Is the listener uninvoked because the topic has no data, because the container is paused, or because of an incident?
- Can the position be read directly from the container's `KafkaConsumer`, or is a new consumer required?

The key answer is: **you can use Kafka's `Consumer.position(TopicPartition)` to read the consumer's current position when an idle event arrives**, provided the call obeys Kafka consumer thread-safety rules.

Example:

~~~text
Topic orders, partition 2

offset:     100  101  102  103  104  105 ...
             |    |    |    |
consumer has polled up to offset 104
current position = 104   (next offset to be read/returned)

committed offset = 101   (progress saved by the group)

end offset = 110         (end boundary at observation time)
~~~

The three values—**current position**, **committed offset**, and **end offset**—have different meanings. This lesson explains how to read each accurately, how to retrieve them safely from `ListenerContainerIdleEvent`, and how to use the results in Spring Kafka Reliability Operations.

## 2. Understanding current position accurately

### 2.1. Kafka consumer position is the next offset

Kafka's `Consumer.position(tp)` returns the consumer's current position on an assigned `TopicPartition`. Per Kafka client semantics, that is **the offset of the next record that will be returned** from that partition.

When `poll()` returns records, position can advance past the fetched records even before the application finishes processing or committing all of them.

Example:

~~~text
poll() returns records at offsets 30, 31, 32

Before poll:
  position(orders-0) = 30

After poll:
  position(orders-0) = 33

Listener has processed:
  Possibly only offset 30 so far

Committed offset:
  May still be 30 or another value
~~~

Therefore, never call current position "the last record processed successfully by business logic" without independent verification.

### 2.2. Position is per partition

There is no single current position for an entire consumer group. Kafka offsets belong to each **topic-partition**, so they must be read individually:

~~~text
orders-0: position 120
orders-1: position 85
orders-2: position 406
~~~

If a listener container has concurrency greater than 1, each child consumer may own a different subset of partitions. Child A's position does not represent all children or the entire group.

### 2.3. Position differs from the last record's offset

Suppose the last record seen by the consumer had offset 49. Position is normally the next offset, i.e., 50. Do not mechanically subtract 1 and assume offset 49 must exist: compacted topics, aborted transactional records, control batches, or skipped offset ranges can leave logs without user-visible records at every consecutive offset.

Position is a **cursor in the Kafka log**, not a count of processed records.

## 3. Distinguishing position, committed offset, and end offset

| Concept | Where obtained | Meaning | Means business processing succeeded? |
|---|---|---|---|
| Current position | `consumer.position(tp)` | Next offset the Kafka consumer can fetch/deliver | No |
| Committed offset | `consumer.committed(...)` or group offset | Position saved by the group to resume from if needed | Only if ack/commit is tied properly to processing outcome |
| End offset | `consumer.endOffsets(...)` | Readable end boundary under isolation semantics | No |
| Beginning offset | `consumer.beginningOffsets(...)` | Earliest readable boundary of the partition | No |
| Last record processed | Business tracking/application state | Last record the listener processed per business contract | Yes, if persisted reliably |
| Last stable offset (LSO) | Kafka transactional visibility | Stable read boundary for `read_committed` when transactions are open | No |

### 3.1. Three offsets side by side

~~~text
orders-0
  beginning offset = 50
  committed offset = 80
  current position = 88
  end offset       = 100
~~~

How to read this:

- If another member takes over the partition and the group resumes from committed offset 80, records starting around offset 80 can be redelivered per retained log.
- The live consumer has position 88, meaning its poll loop reached that boundary; there is no guarantee every record through offset 87 completed side effects.
- End offset 100 shows data exists in the log past position, provided offsets and isolation allow the consumer to read it.
- The gap `end - position = 12` is not an exact count of "12 unprocessed records". It is a distance **in offset units**, not necessarily equal to record count, and the end value is a moving snapshot.

### 3.2. Why can committed offset be smaller than position?

Commonly, the consumer received a batch via `poll()`, yet the listener has not finished or the container has not committed offsets yet. With `AckMode.BATCH` or manual acknowledgment, commits can happen only after multiple records finish processing.

Even after the container delivers records to the listener, a database transaction and a Kafka offset commit remain two separate operations. Position never replaces committed offset when investigating redeliveries after a crash.

### 3.3. Why can position equal end offset?

Once a consumer catches up to readable data on a partition, both values can match:

~~~text
position = 180
end      = 180
~~~

If no producer writes new records, the consumer continues polling empty and the listener container emits idle events after a while.

Still, never conclude "the system is healthy" solely because both numbers match. Verify the consumer still holds the right partition assignments, is not paused, reads the right topic, and whether upstream data is expected.

## 4. How does ListenerContainerIdleEvent help read position?

Spring Kafka emits `ListenerContainerIdleEvent` to report that a listener container received no records within the configured interval. The event supplies metadata on the listener and relevant partitions; in versions providing that API, it also exposes the `Consumer` reference via `getConsumer()`.

Desired flow:

~~~mermaid
sequenceDiagram
    participant K as Kafka broker
    participant C as Listener container
    participant E as Idle event listener
    participant P as Kafka Consumer

    C->>K: poll()
    K-->>C: No new records
    C->>K: next poll()
    K-->>C: No new records
    Note over C: Idle duration exceeds threshold
    C->>E: Publish ListenerContainerIdleEvent
    E->>P: position(topic-partition)
    P-->>E: Current position
    E->>E: Write brief log/metric
    Note over C: Container continues polling normally
~~~

The decisive factor is **which thread executes the callback**. Kafka `Consumer` is not thread-safe; only call `position()` on the container's consumer when the callback runs **synchronously on the appropriate consumer thread**. Never pass the `Consumer` object from an idle event to an executor, REST thread, or scheduler to call later.

Other events such as `ListenerContainerNoLongerIdleEvent` reflect data resuming on the container. They help clear idle state on dashboards, though they do not replace reading the actual position.

## 5. Enabling idle events in Spring Boot

You can configure Spring Boot's listener interval:

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

In Spring Boot versions supporting that property, `idle-event-interval: 30s` sets the listener container's silence threshold.

Distinguish clearly:

- `idle-event-interval`: Spring Kafka threshold for emitting idle application events.
- `session.timeout.ms`: coordinator threshold for detecting missed consumer heartbeats in the classic group protocol.
- `max.poll.interval.ms`: maximum time allowed between valid polls.
- `auto.offset.reset`: policy for picking initial offsets when no valid committed offset exists.

These are distinct mechanisms. Never raise session timeout just because you want `ListenerContainerIdleEvent` after 60 seconds.

If the application defines custom container factories, ensure the factory used by the listener actually has an idle event interval set. YAML properties may not apply when a custom factory bypasses Boot auto-configuration.

## 6. Enabling idle events on the container factory

Direct configuration via `ContainerProperties`:

~~~java
@Configuration
public class InventoryKafkaConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, InventoryChanged>
            inventoryListenerFactory(
                ConsumerFactory<String, InventoryChanged> consumerFactory
            ) {
        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, InventoryChanged>();

        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties().setIdleEventInterval(30_000L);

        return factory;
    }
}
~~~

Listener bound to this factory:

~~~java
@Component
public class InventoryListener {

    @KafkaListener(
        id = "inventory-listener",
        topics = "inventory.changed",
        groupId = "inventory-projection",
        containerFactory = "inventoryListenerFactory"
    )
    public void onInventoryChanged(InventoryChanged event) {
        inventoryService.applyIdempotently(event);
    }
}
~~~

`InventoryChanged` and `inventoryService` are illustrative application types and beans. Projects need suitable serializers/deserializers or message converters.

From an operations perspective, observing current position on an idle event first requires knowing which container emitted the event and which partitions are assigned to that container's consumer.

## 7. Java pattern: reading current position inside the idle callback

This is the core example:

~~~java
import java.util.Collection;
import java.util.Set;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.common.TopicPartition;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaIdlePositionLogger {

    private static final Logger log =
        LoggerFactory.getLogger(KafkaIdlePositionLogger.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        Consumer<?, ?> consumer = event.getConsumer();

        if (consumer == null) {
            log.debug("Idle event has no consumer reference: {}",
                event.getListenerId());
            return;
        }

        Set<TopicPartition> assigned = consumer.assignment();
        Collection<TopicPartition> partitions = event.getTopicPartitions();

        if (partitions == null || partitions.isEmpty()) {
            log.debug(
                "Idle with no partitions: listener={}",
                event.getListenerId()
            );
            return;
        }

        for (TopicPartition partition : partitions) {
            if (!assigned.contains(partition)) {
                continue;
            }

            long position = consumer.position(partition);

            log.info(
                "Listener idle: listener={}, topic={}, partition={}, " +
                "currentPosition={}, idleMs={}",
                event.getListenerId(),
                partition.topic(),
                partition.partition(),
                position,
                event.getIdleTime()
            );
        }
    }
}
~~~

This example uses `ListenerContainerIdleEvent.getConsumer()`, `getTopicPartitions()`, `getListenerId()`, and `getIdleTime()` per the corresponding Spring Kafka API. For other versions, verify exact accessors in your active dependency.

This is a **pattern for reading synchronously inside the event callback**. Do not change it into:

~~~java
@EventListener
public void onIdle(ListenerContainerIdleEvent event) {
    executor.submit(() -> {
        // UNSAFE: calling Kafka Consumer from another thread!
        event.getConsumer().position(someTopicPartition);
    });
}
~~~

The Kafka consumer client does not allow applications to invoke standard APIs on the same consumer instance arbitrarily across threads.

### 7.1. Why check assignment?

`position(tp)` is only meaningful for partitions currently assigned to that consumer. During a group rebalance or assignment change, a partition may no longer belong to that consumer.

`consumer.assignment()` reflects the local assignment at callback time. Checking assignment avoids querying position for a partition no longer owned by the observed consumer.

### 7.2. Keep the callback brief

`position(tp)` often returns from client state, yet in some situations the consumer needs metadata/offset lookups, so the call can block or fail. Reading too many partitions or issuing heavy Kafka requests inside the event callback can slow down the poll loop.

Never call databases, HTTP services, or run heavy work in the callback just to store offset snapshots. Log/record lightweight metrics, and let an async monitoring system process **snapshot values** without ever passing `KafkaConsumer` references across threads.

### 7.3. Never retain the Consumer reference long-term

Never store `event.getConsumer()` in a singleton field, cache, or static holder so a REST endpoint can call `position()` later. Consumer lifecycle and assignments change, and cross-thread access is unsafe.

To expose current position over an API, update a **thread-safe snapshot** inside the idle callback and let the API read that snapshot. Include a timestamp and listener identity on snapshots so callers know whether data is fresh.

## 8. Example storing position snapshots for other systems to read

An observability service can store simple data in a `ConcurrentHashMap`. Reading `consumer.position()` still happens on the synchronous event thread; other threads only read **captured values**, never touching `KafkaConsumer` directly.

~~~java
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class IdlePositionSnapshotStore {

    public record Snapshot(
        String listenerId,
        TopicPartition partition,
        long nextOffset,
        Instant observedAt
    ) {}

    private final ConcurrentMap<String, Snapshot> snapshots =
        new ConcurrentHashMap<>();

    @EventListener
    public void recordIdlePosition(ListenerContainerIdleEvent event) {
        Consumer<?, ?> consumer = event.getConsumer();

        if (consumer == null || event.getTopicPartitions() == null) {
            return;
        }

        for (TopicPartition partition : event.getTopicPartitions()) {
            if (!consumer.assignment().contains(partition)) {
                continue;
            }

            long position = consumer.position(partition);

            Snapshot snapshot = new Snapshot(
                event.getListenerId(),
                partition,
                position,
                Instant.now()
            );

            String key = event.getListenerId() + "/" +
                partition.topic() + "/" + partition.partition();

            snapshots.put(key, snapshot);
        }
    }

    public Map<String, Snapshot> currentSnapshots() {
        return Map.copyOf(snapshots);
    }
}
~~~

`Snapshot` is an immutable record, safe to share between the position-reading thread and reader threads. However, it is **not real-time position state**: it holds values captured **at the last idle event**.

For production, add:

- TTL or cleanup when the listener container stops.
- Removal or stale marking when partitions are revoked/lost.
- Differentiation across child consumers and pods.
- Metadata on assignment, pause, and lifecycle.
- Bounds on stored snapshots if topic/partition sets churn frequently.
- Rate limiting on event logs when idle events repeat continuously.

Never attach the `KafkaConsumer` object to the snapshot; store only the read numbers and identifiers.

## 9. How do reading position and committed offset differ?

The Kafka consumer exposes a committed-offset API. Depending on Kafka client version, overloads may look like:

~~~java
Map<TopicPartition, OffsetAndMetadata> committed =
    consumer.committed(Set.of(partition));

OffsetAndMetadata metadata = committed.get(partition);

Long committedNextOffset =
    metadata == null ? null : metadata.offset();
~~~

However, `consumer.committed(...)` can issue a network request. **Never call this API for every partition on every idle event just for monitoring**, especially with large consumer/partition counts.

A better operational design:

- In the idle callback, quickly read `position(tp)` and emit a snapshot.
- Collect committed offsets periodically via an independent monitoring channel or Kafka group offset metrics/CLI.
- Correlate data by matching topic-partition and nearby timestamps.
- If you truly must read committed offsets in the callback, bound frequency, timeouts, and partition counts, and remember the callback can block the consumer thread.

### 9.1. Reading position does not mean committing offsets

Never write:

~~~java
long position = consumer.position(partition);

// Semantically incorrect for business logic:
// Never commit position directly just because the consumer is idle.
consumer.commitSync(
    Map.of(partition, new OffsetAndMetadata(position))
);
~~~

That snippet is an **anti-pattern**. Position can run ahead of records that have finished processing, so committing it blindly can cause the consumer group to skip records that were never durably persisted.

When the listener container manages acknowledgments via `AckMode.RECORD`, `BATCH`, or manual ack, the application should never interfere with offset commits from an idle callback without a crystal-clear offset-ownership design.

### 9.2. Committed offset can be null

If a group has never committed an offset for a partition, `committed(...)` can return null for that partition. When a consumer starts with no valid committed offset, position may be chosen from `auto.offset.reset` (e.g., earliest/latest).

Thus `position=100` does not prove the group committed 100; it might simply be the initial offset chosen when joining the group.

## 10. Reading beginning and end offsets: when is it useful?

To see whether the consumer has caught up to the log, you can read boundaries:

~~~java
Set<TopicPartition> partitions = consumer.assignment();

Map<TopicPartition, Long> beginnings =
    consumer.beginningOffsets(partitions);

Map<TopicPartition, Long> ends =
    consumer.endOffsets(partitions);
~~~

These calls can contact brokers to query offsets. Never place them on the consumer hot path or call them at high frequency inside event callbacks.

### 10.1. End offset is not last processed offset

`endOffsets` returns a log end boundary per isolation level. It does not indicate whether the listener finished processing the latest record successfully.

### 10.2. read_committed isolation

If the consumer uses `isolation.level=read_committed`, end offset can be bounded by the **last stable offset (LSO)** when an open Kafka transaction exists. An open producer transaction hides records past LSO from the consumer even though the physical Kafka log already contains data.

Therefore, when a `read_committed` consumer's current position equals its end offset, remember that is the readable boundary under the chosen isolation, not necessarily the absolute physical log high watermark/end.

### 10.3. Offset gaps do not equal message counts

With compacted topics or transactional protocols, offsets can contain gaps. Subtracting `end - position` yields only an **offset distance**, not a guaranteed count of unprocessed business messages.

### 10.4. When end changes during measurement

Kafka producers can keep publishing events while your code reads position and end offset. The two measurements are not an atomic snapshot. Any point-in-time lag calculation is therefore an approximation requiring consistent timestamps and polling cadence.

## 11. Can lag be computed from current position?

You can calculate a **provisional distance**:

~~~text
fetch distance = end offset - current position
~~~

Example:

~~~text
position = 1,250
end      = 1,300
distance = 50 offset units
~~~

However, **consumer group lag** is normally computed from committed offset:

~~~text
group lag = log end offset - committed offset
~~~

The two formulas answer different questions.

| Observation | Simple formula | Interpretation |
|---|---|---|
| Fetch distance | `end - position` | How far the local consumer sits from the readable boundary |
| Group offset lag | `end - committed` | How far the group sits behind the log boundary by committed progress |
| Uncommitted distance | `position - committed` | How many offsets ahead of commits the consumer has polled |
| Business work backlog | Dedicated business state | How many events actually have incomplete side effects |

**Warning:** These formulas reflect offset distance and may not equal record counts; neither do they automatically capture in-flight batches, transactions, compaction, filtering, or assignment churn.

For production alerting, prefer official Kafka consumer group lag/consumer metrics combined with listener processing metrics rather than inventing a single "lag" solely from position in an idle callback.

## 12. Why can an idle event fire when position is below end?

Several possibilities:

1. The consumer is paused at container or partition level, so it keeps polling without delivering data from paused partitions.
2. Records are held for retries, backoff, error handling, or the container is transitioning state.
3. The consumer just rebalanced, shifting assignments or positions around observation time.
4. End offset was sampled at a different instant than current position; producers may have just sent more records.
5. Mismatch between the topic-partition/consumer instance of the two measurements.
6. `read_committed` isolation or open transactions make visibility differ from log-end tools.
7. Container-level idle triggered while another partition or consumer holds backlog.

Never conclude "Kafka lost records" merely from seeing `position < end`. Inspect container assignments, polls, pauses, retries, committed offsets, and measurement timestamps.

### 12.1. Intentional pause

When a system calls `container.pause()` for backpressure, the consumer keeps polling to preserve membership without receiving new records from paused partitions. Idle events may fire during that time depending on container/version.

When evaluating current position, inspect `isPauseRequested()`, `isConsumerPaused()`, or corresponding `ConsumerPausedEvent`/`ConsumerResumedEvent` events.

### 12.2. Unassigned partitions

If a child consumer owns no partitions, never call `position(tp)` on that child. When consumers outnumber partitions, some children receive no assignments; their lack of records does not prove the topic lacks traffic.

### 12.3. Data hidden by Kafka transactions

With `read_committed`, an unfinished transaction makes subsequent records invisible. The consumer may go idle on record delivery even while producers actively append. Check LSO and transaction monitoring—never seek or reset offsets to "jump over" unsettled data.

## 13. Interaction with AckMode in Spring Kafka

Offset ownership depends on how the container commits.

| AckMode | Relationship to position and commit |
|---|---|
| `RECORD` | Container commits after each record succeeds in the listener per policy |
| `BATCH` | Container commits per poll/batch progress after processing |
| `TIME` | Commits may be deferred by time interval and container conditions |
| `COUNT` | Commits based on processed record count and config |
| `COUNT_TIME` | Combines count and time conditions |
| `MANUAL` | Listener calls acknowledge; commits follow container semantics |
| `MANUAL_IMMEDIATE` | Acknowledge can trigger immediate commit per conditions/usage |

Current position can exceed committed offset in every mode if the consumer polled records before commit time arrived. Never replace container-managed acknowledgment by reading position and committing manually inside an idle callback.

### 13.1. Manual ack

Example:

~~~java
@KafkaListener(topics = "orders")
public void onOrder(
    OrderCreated event,
    Acknowledgment acknowledgment
) {
    orderService.applyIdempotently(event);
    acknowledgment.acknowledge();
}
~~~

Acknowledge only after durable side effects complete. Reading position in an idle event does not prove the listener called `acknowledge()` properly on every record.

### 13.2. Database transactions

If a listener writes to a database, a crash can happen after DB commit yet before Kafka offset commit. When the record is redelivered, position may shift while event ID/inbox checks prevent duplicate side effects.

Hence "current position" is **Kafka consumer metadata**, not a database transaction log.

## 14. Consumer position with batch listeners

A batch listener receives multiple records per invocation:

~~~java
@KafkaListener(
    topics = "orders",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(List<ConsumerRecord<String, OrderCreated>> records) {
    orderService.processBatch(records);
}
~~~

A single batch can span records from multiple partitions. Once `poll()` returns the batch, consumer position can jump across many offsets even before the business method finishes processing.

Example:

~~~text
One poll returns:
  orders-0: offsets 10, 11, 12
  orders-1: offsets 40, 41

Right after poll:
  position(orders-0) may be 13
  position(orders-1) may be 42

Listener still running:
  processBatch has not committed database yet
~~~

If a batch fails and retries, never use position to infer which portion succeeded. With `BatchListenerFailedException`, error handlers can handle by index; with generic errors, the entire batch may retry. Track business state and commits per partition separately.

When a container emits idle events after empty polls, the position snapshot only states the consumer's current cursor, not proof that every side effect from prior batches completed.

## 15. Reading current position during retries or seeks

Spring Kafka's error handler may seek back to a failing record's offset or retain records for resubmission without seeking, depending on config and version.

### 15.1. Retries via seek

Suppose processing fails on offset 90 and the error handler seeks back to 90 to redeliver:

~~~text
Before error:
  position = 94 because poll fetched offsets 90..93

After error handler seeks to offset 90:
  position may become 90

After retry succeeds:
  position advances again with polls
~~~

Position **does not strictly increase monotonically** over a consumer's lifetime. Applications or frameworks can `seek()` backward to older offsets.

### 15.2. Retain and resubmit

With certain error handler settings like `seekAfterError=false`, the container can hold unprocessed records in memory and redeliver them to the listener without issuing seeks per record. Meanwhile, `KafkaConsumer` position may already sit ahead of polled records while the container still holds retry work.

Therefore, looking only at `consumer.position(tp)` misses backlog **buffered inside the listener container**. Investigating retries requires inspecting retry attempts, record offsets, error handler state, and metrics.

### 15.3. Recovery/DLT

When an unprocessable record is sent to a DLT successfully, the container can advance offsets per recovery/ack policy. If DLT publishing fails, the record may need recovery retries.

Current position on an idle event does not prove the recoverer published to the DLT successfully. Monitor DLT send outcomes and committed offsets independently.

## 16. Transactional listeners and read_committed

Kafka transactions can combine output Kafka records and source consumer offsets in consume–process–produce flows.

~~~text
Input Kafka record
      |
      v
Transactional listener container
      |
      +-- KafkaTemplate.send(output)
      +-- Send source offset to transaction
      |
      v
Commit Kafka transaction
~~~

When a transaction aborts due to an error or shutdown before commit, source offsets are not committed in that transaction and input records may be redelivered. Consumer position may still have advanced or been rewound per rollback handling.

Before a transaction commits, downstream `read_committed` consumers cannot see aborted or in-flight outputs. When tracking positions, never confuse fetch position with **transaction outcome**.

### 16.1. Last stable offset

In `read_committed` mode, consumers can only read up to the LSO. An open transaction can delay visibility of subsequent records, making current position equal end offset under isolation visibility even while the physical log holds newer data behind it.

If unusual idle occurs on a transactional topic, inspect transaction durations, abort rates, producer fencing, and LSO-related lag before altering consumer offsets.

### 16.2. Kafka exactly-once does not mean the listener runs once

During transaction aborts or rebalances, the listener can reprocess records. Kafka EOS protects output + source offsets within a properly configured transaction; it does not automatically prevent duplicate DB/HTTP side effects.

Never treat current position as proof of end-to-end exactly-once execution.

## 17. Other events to distinguish

| Event/phenomenon | What it reflects | Relationship to current position |
|---|---|---|
| `ListenerContainerIdleEvent` | No records received for idle interval | Safe to snapshot position in sync callback |
| `ListenerContainerNoLongerIdleEvent` | Records resumed after idle | Position may begin advancing again |
| `ListenerContainerPartitionIdleEvent` | Specific partition is silent | May want position for that exact partition |
| `ConsumerPausedEvent` | Pause executed | Position can stay flat even while producers write |
| `ConsumerResumedEvent` | Resume executed | Consumer may resume polling/dispatching |
| `NonResponsiveConsumerEvent` | Consumer polling failed monitor check | Do not assume consumer can be queried as in normal idle |
| Rebalance/partition revoked | Assignment changed | Old position may no longer belong to this consumer |
| Container stopped | Consumer lifecycle stopped | Old position snapshots may be stale |

**Listener idle** and **non-responsive consumer** are separate issues. Idle can be completely healthy: the consumer polls steadily on an empty topic. Non-responsive means polls are blocked or the consumer fails to progress as expected.

Never treat any single event as grounds to auto-restart containers or reset offsets. Investigate data sources, assignments, and health first.

## 18. Reading position when one partition is idle while the container is not

A consumer can own multiple partitions:

~~~text
inventory-0: 100 records/min
inventory-1:   0 records/min
inventory-2:  30 records/min
~~~

Because the container still receives records on P0/P2, it may **not emit container-wide idle events** even though P1 gets no records. In supporting Spring Kafka versions, configure `idlePartitionEventInterval` to observe per-partition idle separately.

~~~java
factory.getContainerProperties()
    .setIdleEventInterval(30_000L);

factory.getContainerProperties()
    .setIdlePartitionEventInterval(60_000L);
~~~

`ListenerContainerPartitionIdleEvent` reflects partition-level idleness. To read current position for that specific partition, obtain the `KafkaConsumer` of the container/child owning that partition per your version's supported API and access it on the proper consumer thread.

Never assume a partition idle event for P1 means current positions on P0/P2 are also stationary.

### 18.1. Using offsets for partition-level SLAs

If a partition is designed to receive an event every minute, partition idle events plus position/end offsets can reveal uneven producer distribution or skewed partitioners.

However, key-partitioned topics rarely have perfectly uniform traffic across all partitions. Silence on one partition for a stretch can be completely valid; establish per-workload baselines.

## 19. Monitoring multiple instances and concurrent containers

Suppose an application runs three pods, each with `concurrency=2`; up to six consumer members may exist:

~~~text
Group orders-service

Pod A:
  child A-0 -> orders-0
  child A-1 -> orders-1

Pod B:
  child B-0 -> orders-2
  child B-1 -> orders-3

Pod C:
  child C-0 -> orders-4
  child C-1 -> orders-5
~~~

When child A-0 emits an idle event, it can only read positions for partitions **currently assigned to A-0**. There is no single `KafkaConsumer` that can read local current positions for the whole group.

To build a centralized dashboard, each JVM publishes **snapshot data** to monitoring, never `KafkaConsumer` references:

~~~text
pod_id, listener_id, topic, partition, position, observed_at

pod-a, orders-0, orders, 0, 120, 2026-...
pod-a, orders-1, orders, 1,  87, 2026-...
pod-b, orders-0, orders, 2, 302, 2026-...
~~~

When a rebalance shifts partition ownership, the old owner's snapshot must be marked stale. You can attach group generation/assignment epoch metadata if your observability stack supports it, and never base offset actions on stale snapshots.

### 19.1. Listener IDs

Events carry a listener/container ID; with concurrent child containers, IDs may carry specific suffixes. Never hardcode assumptions that all children share the same ID or every version formats suffixes identically.

### 19.2. Never mix multiple consumer groups

Two distinct groups can sit at completely different positions on the same topic-partition. Every snapshot must carry a clear `group.id` or consumer group identity; otherwise dashboards can confuse another group's position with the group under investigation.

## 20. Monitoring: lightweight snapshots, safe metrics

Useful fields to capture on idle events:

| Field | Reason |
|---|---|
| Listener/container ID | Know which listener emitted the event |
| Pod/instance ID | Pinpoint which JVM emitted the event |
| Group ID | Separate independent consumption progress |
| Topic and partition | Offsets are always per partition |
| Current position | Consumer's next offset at observation time |
| Idle duration | Recorded silence interval |
| Observed timestamp | Separate fresh snapshots from stale ones |
| Paused state | Know whether fetching was intentionally halted |
| Assignment | Confirm which consumer owns the partition |
| Committed offset | Group-saved progress; collect separately when appropriate |
| End offset/LSO | Readable data boundary |
| Consumer group lag | Backlog derived from committed offsets |
| Listener processing latency | Catch overly slow processing |
| Retry/recovery count | Know if records are retrying/retained |
| Rebalance events | Catch ownership changes |

### 20.1. Do not alert on every idle event

If `idleEventInterval=10s` and a topic has no data for 30 minutes, the container emits many events. Paging on each event creates an alert storm.

Use an `ACTIVE → IDLE → ACTIVE` state machine; alert only when idle duration exceeds a business threshold **and** the system genuinely expects records.

### 20.2. Never use offsets as high-cardinality labels

Metric labels should include bounded values like service, listener, topic, and outcome. Position changes constantly; never put offsets or event IDs into metric labels.

You can use a gauge for position with topic/partition labels if partition counts are manageable, or rely on structured logs to avoid cardinality blowups in clusters with tens of thousands of partitions.

### 20.3. Snapshots are not simultaneous measurements

If you read position at T1 and committed offset from the CLI at T2, producers or containers can advance offsets in between. Include timestamps, sources, and clear interpretations; never expect exact equality without an atomic snapshot.

## 21. Investigation runbook when idle with unknown position

A runbook:

1. Verify the listener container is **running** and the Kafka consumer holds assignments.
2. Check whether `idleEventInterval` is enabled on the factory used by the listener.
3. Record event listener ID, idle duration, and topic-partitions.
4. Read `position(tp)` inside the synchronous callback if the event supplies the consumer and thread safety holds.
5. Cross-check Kafka committed offsets by group ID and partition.
6. Cross-check end offsets/LSO under the consumer's isolation mode.
7. Check requested/actual paused state on the container.
8. Inspect polled records, retry/seek/retained records, and listener processing.
9. Compare producer throughput, broker metadata, and deserialization errors.
10. Check rebalances/partition losses around the event timestamp.
11. If position equals end, check whether upstream is publishing as expected.
12. If position is below end, determine why fetching stopped before seeking/resetting.
13. If committed is below position, check `AckMode`, transactions/retries, and processing progress.
14. Use event ID/inbox records when verifying completed external side effects—never infer from position.
15. After remediation, monitor record delivery, group lag, and fresh position snapshots.

Never use idle events as a default trigger for `seekToEnd()`. Doing so skips unprocessed backlogs and causes business data loss for the consumer group.

## 22. Specific operational scenarios

### 22.1. Idle, position equals end, committed equals position

~~~text
position  = 500
committed = 500
end       = 500
~~~

The consumer has caught up to the topic. If upstream produces no new events, this is normal. If upstream **should** be publishing, inspect the producer, routing, topic name, partitioner, and ingestion monitoring.

Never restart a consumer solely because it has been idle for a long time.

### 22.2. Idle, position equals end, yet committed is lower

~~~text
position  = 500
committed = 495
end       = 500
~~~

The consumer polled up to the log end yet the group only recorded offset 495. Unacked records, delayed/failed commits, or in-flight processing/retries may exist. Never force-commit 500 just to make metrics look clean.

On process restart, the group may re-read from the committed offset if those offsets are still retained. Idempotency is essential.

### 22.3. Idle, position below end, container paused

~~~text
position  = 500
committed = 500
end       = 620
paused    = true
~~~

Backlog is growing because the consumer temporarily stopped receiving. This may be intentional backpressure. Check resume conditions, deadlines, and lag/retention budgets.

### 22.4. Idle, position below end, not paused

~~~text
position  = 500
end       = 620
paused    = false
~~~

Investigate assignments, consumer health, poll latency, isolation, error handling, timeouts, and whether end/position measurements came from the same consumer/partition/timestamp. There is not yet sufficient evidence to blame the Kafka broker.

### 22.5. No current position because partition is unassigned

When `consumer.assignment()` does not contain the target partition, `position(tp)` is invalid for that partition. Do not query a local `KafkaConsumer` assuming it owns the partition.

To inspect offsets for partitions unassigned locally, use independent admin/group-offset APIs with proper permissions; those yield **committed/group/end offsets**, not a local member's current position.

## 23. Testing reading current position when idle

### 23.1. Testing idle on an empty topic

1. Create a single-partition test topic and a new consumer group.
2. Configure a short `idleEventInterval`, e.g., 1–2 seconds.
3. Start the listener and wait for partition assignment.
4. Send no records.
5. Wait for `ListenerContainerIdleEvent` using a latch/Awaitility with timeout.
6. Inside the synchronous callback, read `consumer.position(tp)` for the assigned partition.
7. Record position, committed offset, and end offset via separate measurements.
8. Verify the callback throws no exceptions and the container keeps polling.

Never use `Thread.sleep(2000)` assuming the event definitely arrived on schedule. Idle timers depend on scheduling and poll cycles.

### 23.2. Testing after consuming records

1. Send three records to the test topic.
2. Wait for the listener to process them successfully.
3. Wait for the group commit per chosen `AckMode`.
4. Wait for an idle event.
5. Read current position and compare against the end boundary near that time.
6. Verify position is the **next offset**, not the last record's offset.
7. Verify database side effects using real persisted data, not just offsets.

### 23.3. Testing batch poll with delayed commit

1. Have poll return multiple records using an appropriate batch or manual ack mode.
2. Arrange for commits not to happen immediately after poll.
3. Capture position and committed offset.
4. Verify the two values can differ.
5. After processing/commit completes, observe committed offset advancing.
6. Verify redelivery on restart when offsets remain uncommitted.

### 23.4. Testing pause

1. Have a producer send records continuously.
2. Call `container.pause()`.
3. Wait for `ConsumerPausedEvent` or actual paused state.
4. Observe idle events and position snapshots per version.
5. Verify position does not necessarily advance while paused even though end offset climbs.
6. Resume and verify records are consumed per offset/ack policy.

### 23.5. Testing rebalance

1. Run two consumer members in the same group.
2. Record partition ownership and position snapshots.
3. Trigger a controlled member join/leave.
4. Verify assignments shift.
5. Verify the callback skips partitions no longer assigned.
6. Mark the previous owner's snapshots stale instead of displaying them as current partition position.
7. Let the new member process and verify consumer group lag.

### 23.6. Testing asynchronous event handlers

Never use an asynchronous event listener to call `KafkaConsumer.position` directly. If the application configures an async multicaster, move snapshot capture onto the consumer thread via a supported extension/listener callback, or use an independent offset-monitoring source.

The test goal is verifying **thread safety**, not merely that an API call returned a number once on a developer laptop.

## 24. Common mistakes

**Assuming position equals committed offset:** position can advance right after poll; committed offset depends on acknowledgments and transactions.

**Assuming position equals the last processed record:** position is the next offset; records may still be in-flight.

**Reading position from an event on an executor thread:** `KafkaConsumer` is not thread-safe, risking `ConcurrentModificationException`/`ConcurrentAccessException` or unsupported behavior.

**Storing Consumer from an idle event in a singleton:** the object has lifecycle and ownership; other threads must never use it arbitrarily.

**Calling committed/endOffsets on every idle event without limits:** creates metadata/network overhead and can block the consumer thread.

**Skipping the assignment check:** calling position for a partition not owned by the observed consumer can fail.

**Confusing idle with non-responsive:** idle can be normal empty polling; non-responsive means the consumer failed poll responsiveness.

**Confusing idle with paused:** pausing may be intentional backpressure; idle only states no records arrived within the threshold.

**Computing remaining messages as end - position:** offset distance is not an exact message count.

**Treating read_uncommitted and read_committed identically:** transactional visibility can alter end offsets.

**Treating stale snapshots as current position:** after rebalances, owners and positions change.

**Observing one child and concluding for the whole group:** concurrent containers run multiple independent `KafkaConsumer` instances.

**Using idle callbacks to commit offsets:** risks skipping records whose processing has not completed.

**Using idle callbacks for unchecked seekToEnd:** directly discards unprocessed backlog.

**Blocking the consumer thread in `@EventListener`:** stretches poll intervals, causing lag or rebalances.

**Restarting consumers when position equals end:** if producers send nothing new, restarts solve nothing.

**Omitting group ID and topic-partition:** offsets across different groups or partitions cannot be compared directly.

## 25. Quick decision summary

| Goal | What to do | What not to do |
|---|---|---|
| Know local consumer position when idle | `ListenerContainerIdleEvent` + `event.getConsumer().position(tp)` synchronously on consumer thread | Call same consumer from REST/executor thread |
| Know committed progress | Group committed offsets | Treat position as committed |
| Know partition end boundary | `endOffsets` or Kafka monitoring | Call excessively from idle callbacks |
| Know group backlog | Lag from committed offset/end with timestamps | Compute `end - position` and call it message count |
| Know a specific partition is idle | Partition idle events in supporting versions | Watch container-wide idle alone |
| Know container is paused | Pause API/events and actual state | Infer solely from absence of records |
| Know listener is stuck in poll | Poll/heartbeat/non-responsive monitoring | Infer from idle events |
| Display position on dashboards | Immutable snapshots with timestamp, owner, and partition | Cache `KafkaConsumer` objects |
| Prevent duplicate DB effects | Event ID/inbox/idempotency | Rely on current position |
| Handle commit/rebalance errors | Monitor committed offsets, ownership, and redelivery | Force-commit position inside idle handler |

## 26. Production principles

- Enable `idleEventInterval` on the **right listener container factory** to receive `ListenerContainerIdleEvent`.
- Use `Consumer.position(TopicPartition)` to read current position **per assigned partition**.
- Access `event.getConsumer()` only when the callback runs synchronously on the proper consumer thread; avoid async event handlers for `KafkaConsumer` calls.
- Never store `KafkaConsumer` for use by other threads; export only data snapshots.
- Always tag results with listener ID, group ID, topic, partition, instance ID, and observed timestamp.
- Remember position is the **next offset**, neither committed offset nor business-completed offset.
- When comparing committed/end offsets, collect safely, record timestamps, and account for transaction isolation.
- Distinguish container-level idle from partition-level idle, especially with high concurrency.
- Correlate idle with pause, assignment, poll health, producer activity, and group lag.
- Never commit or seek solely because current position is stationary.
- Keep event callbacks short to avoid destabilizing the poll loop.
- Clean up snapshots on rebalance, container stop, or instance restart.
- Test empty topics, new records, slow acks, pauses, and rebalances before using for automation.

**Conclusion:** When a Spring Kafka listener container goes idle, `ListenerContainerIdleEvent` provides the right context to read the Kafka consumer's **current position** via `Consumer.position(tp)`. To do so safely, read position on the consumer thread, check assignments, and treat the returned value as the consumer's next offset at observation time. Never equate it with committed offset, end offset, or business processing status. Only by pairing current position with consumer lag, pause/rebalance signals, and committed offsets can an idle state be diagnosed reliably.
