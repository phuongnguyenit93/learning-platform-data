# ConsumerSeekAware.onIdleContainer

In Spring Kafka, **`ConsumerSeekAware.onIdleContainer`** is a callback that lets a listener know when the **listener container is in an idle state** and perform **seek** operations on the Kafka partitions currently assigned to that consumer. This callback is useful when an application needs to **re-read data from a checkpoint, execute a controlled replay, or reposition its read cursor when no new records are being delivered**.

An easily confused point: **idle does not mean the consumer is hung**. The listener container may still be polling Kafka normally yet receiving no records during the configured interval. Conversely, a consumer stuck in processing or failing to call poll may need to be detected by **`NonResponsiveConsumerEvent`**, rather than relying on `onIdleContainer`.

Nor is `onIdleContainer` a command to automatically seek to the beginning of the topic. **Spring Kafka does not rewind offsets merely because a consumer goes idle.** The application only alters its read position when it proactively invokes a method on **`ConsumerSeekCallback`**. Any seek decision must weigh committed offsets, retention, retries, idempotency, partition ownership, and impact on a live production consumer group.

## 1. What problem does ConsumerSeekAware solve?

`KafkaConsumer` reads records starting from its current position on each `TopicPartition`. In some applications, the listener must control its read position deliberately rather than always continuing from the next offset:

- Reprocessing a historical slice after fixing business logic.
- Re-running previously processed events to rebuild a projection.
- Resuming from a checkpoint persisted by the application outside Kafka.
- Jumping to a specific position on a partition during an approved operational action.
- Repositioning the read cursor while the listener is idle to reduce disruption to a synchronous record-processing callback.

Spring Kafka provides the **`ConsumerSeekAware`** interface so a listener can receive lifecycle callbacks and a **`ConsumerSeekCallback`** safely within a framework-managed context.

~~~text
Kafka topic orders.events
          |
          v
Listener container
          |
          +-- poll records
          +-- dispatch @KafkaListener
          |
          +-- no records delivered long enough
          |
          v
Idle condition
          |
          v
ConsumerSeekAware.onIdleContainer(assignments, callback)
          |
          +-- app does not want to seek -> return
          |
          +-- valid replay request exists -> callback.seek(...)
          |
          v
Subsequent polls read from the new position
~~~

**`ConsumerSeekAware`** fits application-managed seek operations. When you only need to observe the absence of data, a listener for **`ListenerContainerIdleEvent`** usually suffices; implementing `ConsumerSeekAware` is not necessary.

## 2. What is the signature of onIdleContainer?

Spring Kafka typically provides the callback in this form:

~~~java
@Override
public void onIdleContainer(
        Map<TopicPartition, Long> assignments,
        ConsumerSeekCallback callback) {
    // Inspect assignments and decide whether to seek.
}
~~~

Where:

| Parameter | Meaning |
|---|---|
| **`assignments`** | Map of `TopicPartition` assigned to the consumer and current position/offset info supplied by the container |
| **`callback`** | `ConsumerSeekCallback` object used to request seeks on partitions inside this exact lifecycle callback |
| **`TopicPartition`** | Topic and partition pair, e.g., `orders.events` / partition 2 |
| **`Long`** | Position/offset info for the partition; never assume it equals the consumer group's committed offset |

Example map:

~~~text
assignments:
  (orders.events, partition 0) -> 108
  (orders.events, partition 1) -> 55
  (orders.events, partition 2) -> 203
~~~

Conceptually, the listener container provides the assigned partitions and the positions it knows at callback time. **Do not treat these values as confirmation that all preceding business side effects have committed.** `KafkaConsumer` positions and group committed offsets are two distinct concepts.

In the illustrative code, `ConsumerSeekCallback` is a nested type inside `ConsumerSeekAware`. If referenced outside a class implementing the interface, write **`ConsumerSeekAware.ConsumerSeekCallback`** in full to avoid ambiguity.

## 3. What related callbacks does ConsumerSeekAware have?

The `ConsumerSeekAware` interface exposes callbacks for different moments in the listener container lifecycle:

| Callback | When is it useful? |
|---|---|
| **`registerSeekCallback`** | Framework registers a callback so the application can prepare proactive seek mechanisms |
| **`onPartitionsAssigned`** | New assignments arrived; the application can set initial read positions or restore checkpoints |
| **`onPartitionsRevoked`** | Partitions are about to be revoked; the application cleans up ownership-bound state |
| **`onIdleContainer`** | Container detected idle state; the application may seek on assigned partitions |

Simplified lifecycle diagram:

~~~text
Consumer starts
       |
       v
registerSeekCallback(...)
       |
       v
Consumer is assigned partitions
       |
       v
onPartitionsAssigned(...)
       |
       v
Poll / process records
       |
       +-- data continues --> process
       |
       +-- idle long enough
                |
                v
         onIdleContainer(...)
                |
                +-- may seek
                |
                v
          continue polling / processing
       |
       v
Rebalance or shutdown
       |
       v
onPartitionsRevoked(...)
~~~

This is an illustrative diagram, **not a guarantee that every callback fires exactly once in strict order in every scenario**. A consumer can lose group membership, undergo cooperative rebalancing, or be killed before a normal partition revocation callback runs.

`onIdleContainer` does not replace `onPartitionsAssigned`: if you need to seek immediately when a partition is assigned, `onPartitionsAssigned` is usually the right place rather than waiting for the topic to go idle.

## 4. What does idle mean in Spring Kafka?

A listener container is considered idle when **no records have been delivered to the listener for long enough per the idle event configuration**.

Example:

~~~text
10:00:00  Listener processes last record
10:00:05  Consumer keeps polling, no new records
10:00:10  Consumer keeps polling, no new records
10:00:15  Idle interval reached
          -> container detects idle
          -> related callbacks/events fire
~~~

This **does not mean**:

- The Kafka broker has stopped working.
- The consumer group has rebalanced.
- The consumer thread is deadlocked.
- The consumer is paused.
- The topic has zero data across all partitions.
- All records have been processed successfully and committed.

A consumer can be idle because it sits at the end of the log, the topic has low traffic, subscriptions don't match, records are filtered out, the container is paused, or container-specific conditions apply. Inspect assignment, lag, and pause states before concluding a root cause.

## 5. Configuring idleEventInterval

To make the framework detect idle at the desired interval, configure **`idleEventInterval`** on the listener container.

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        idleAwareKafkaFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);

    // Request detecting idle container after roughly 15 seconds.
    factory.getContainerProperties()
            .setIdleEventInterval(15_000L);

    return factory;
}
~~~

This is Java configuration using the `ContainerProperties` API. `ConsumerFactory` and serializer/deserializer beans must be configured separately per application.

Without enabling idle detection, **do not assume `onIdleContainer` will be invoked periodically on its own**. You must configure `idleEventInterval` on the container actually running the listener.

Production configurations may use a larger interval depending on throughput and replay needs. Fifteen seconds is illustrative only. Setting it too low triggers unnecessary idle callbacks on low-traffic topics; setting it too high delays seek-on-idle requests.

If a listener container factory is shared by multiple listeners, the idle interval may apply across multiple containers. When distinct policies are needed per group, create separate factories or configure containers explicitly.

## 6. Example listener implementing ConsumerSeekAware

Illustrative example of a listener consuming `orders.events` that seeks only when a **pre-registered replay request** exists:

~~~java
@Component
public class OrderEventListener implements ConsumerSeekAware {

    private static final Logger log =
            LoggerFactory.getLogger(OrderEventListener.class);

    private final OrderProjectionService projectionService;

    // Seek requests submitted by a controller or operations service.
    private final ConcurrentMap<TopicPartition, Long> pendingSeeks =
            new ConcurrentHashMap<>();

    public OrderEventListener(OrderProjectionService projectionService) {
        this.projectionService = projectionService;
    }

    @KafkaListener(
            id = "orders-idle-seek-listener",
            topics = "orders.events",
            groupId = "orders-projection",
            containerFactory = "idleAwareKafkaFactory")
    public void consume(ConsumerRecord<String, OrderEvent> record) {
        projectionService.apply(record.value());
    }

    public void requestReplay(
            String topic, int partition, long targetOffset) {
        if (targetOffset < 0) {
            throw new IllegalArgumentException(
                    "targetOffset must not be negative");
        }

        pendingSeeks.put(
                new TopicPartition(topic, partition),
                targetOffset);
    }

    @Override
    public void onIdleContainer(
            Map<TopicPartition, Long> assignments,
            ConsumerSeekCallback callback) {

        for (TopicPartition partition : assignments.keySet()) {
            Long targetOffset = pendingSeeks.get(partition);
            if (targetOffset == null) {
                continue;
            }

            log.info(
                    "Seek on idle: partition={}, targetOffset={}",
                    partition,
                    targetOffset);

            callback.seek(
                    partition.topic(),
                    partition.partition(),
                    targetOffset);

            pendingSeeks.remove(partition, targetOffset);
        }
    }
}
~~~

In this example:

1. The listener processes records normally.
2. A control layer calls `requestReplay(...)` with an approved topic, partition, and offset.
3. The request is held in a `ConcurrentHashMap`.
4. When the container goes idle, Spring Kafka invokes `onIdleContainer(...)`.
5. The callback seeks only partitions present in current assignments that have a matching request.
6. The request is removed from the map once handed to the callback.

**This is a technical example of the seek mechanism, not a complete production replay tool.** A real system needs authorization checks on `requestReplay`, topic/partition validation, log start/end offset checks, transaction state awareness, distributed ownership, auditing, seek outcome tracking, and request persistence across process restarts.

## 7. Why must seeks be gated by an explicit request?

A dangerous implementation:

~~~java
@Override
public void onIdleContainer(
        Map<TopicPartition, Long> assignments,
        ConsumerSeekCallback callback) {

    assignments.forEach((partition, position) ->
            callback.seek(
                    partition.topic(),
                    partition.partition(),
                    0L));
}
~~~

Every time the container goes idle, that code rewinds the consumer back to offset 0. On a low-traffic topic, it can re-read the exact same records **infinitely many times**.

~~~text
Consumer reads offsets 0..99
       |
       v
Reaches end of log -> idle
       |
       v
Seeks to offset 0
       |
       v
Re-reads offsets 0..99
       |
       v
Idle -> seeks to offset 0 -> repeats
~~~

Consequences can include:

- Repeatedly calling payment APIs, sending emails, or mutating databases.
- Producing duplicate Kafka outputs.
- Inflating apparent consumer lag and disrupting progress on new records.
- Generating pointless CPU/network churn.
- Bloating audit/log storage and masking real incidents.

Therefore, enforce a **one-shot flag, replay request ID, scoped target, and applied state**. The callback must never automatically rewind on every idle tick without an explicit replay policy.

## 8. What does callback.seek do?

`ConsumerSeekCallback` provides seek methods executed by Spring Kafka within the proper container context.

Example:

~~~java
callback.seek(
        "orders.events",
        2,
        105L);
~~~

This request moves the read position of **partition 2 on topic `orders.events`** to offset 105, provided that partition remains assigned and the offset is valid.

Concepts to distinguish:

| Concept | Meaning |
|---|---|
| **Consumer position** | Next position the consumer expects to read in the partition |
| **Committed offset** | Next position durably saved by the consumer group for recovery/restart |
| **Seek target** | Position the application wants the consumer to read from after seeking |
| **Record offset** | Individual offset of a record already read |

Seeking primarily affects **position**—it is not an offset-commit command. Seeking does not rewrite the Kafka log, delete old records, or undo side effects of prior records.

When a consumer restarts or a group rebalances, committed offsets and container lifecycle still determine the read position. Never assume a transient seek persists across restarts.

## 9. assignments are not committed offsets

Suppose:

~~~text
orders.events / P2

Consumer position: 120
Consumer group committed offset: 115
Last business record processed: 119
~~~

The `assignments` map in the callback supplies current position info, yet is **not proof that the group committed up to that position**.

Even when the listener processed record offset 119, commits may be deferred by `AckMode`, an uncommitted transaction, or a recent publish failure.

If you need to choose a replay target based on a business checkpoint, fetch that checkpoint from a store designed to persist it rather than subtracting an arbitrary delta from `assignments` positions and assuming it is safe.

With transactional consumers, arbitrary seeks across transaction boundaries can break expectations tying outputs and input offsets together. Restrict seeks to valid callback/lifecycle points with well-defined replay semantics.

## 10. Offsets before log start and past log end

Kafka topics have retention and cleanup policies. A previously valid target offset may no longer exist:

~~~text
orders.events/P2

Log start offset: 200
Log end offset:   340

Replay request target: 105
~~~

Offset 105 sits before log start; brokers have already deleted the segment holding that record. When a consumer seeks to an expired position, an offset-out-of-range error or `auto.offset.reset` behavior may trigger depending on configuration and execution path.

If the target sits at log end, the consumer will receive no immediate records; that is normal behavior. If the target lies beyond end, never assume Kafka will invent or recover historical records.

Before accepting a production replay:

1. Verify the topic and partition exist.
2. Verify the target is non-negative.
3. Verify the target falls within current retention boundaries.
4. Verify the topic was not truncated/recreated in a way that invalidates old offsets.
5. Decide whether to clamp the target to valid beginning/end or reject the request.
6. Avoid silently falling back to `earliest` without a business decision, as that can reprocess huge data volumes.

Perform these checks from a separate administrative component or via Kafka APIs on a proper thread. Never invoke `KafkaConsumer` from an HTTP controller thread to query offsets or seek a Spring-container-managed consumer.

## 11. An idle listener does not mean the topic is empty

Situations that can lead to idle:

- The consumer is at the end of the log for its owned partitions.
- The topic has low traffic or records only arrive on partitions owned by other consumers.
- The listener container is paused.
- The consumer uses a filter and no records pass through to the business listener per container semantics.
- Topic subscription or group offsets prevent the container from receiving more records.
- The consumer is waiting for transactional records to commit under `read_committed`.

Thus, if you plan to use `onIdleContainer` for replay, verify whether the idle reason aligns with your plan.

Never treat idle as proof that **the entire system has finished processing all data**. Unprocessed data may still sit on other partitions, other consumers, or in worker queues outside the listener.

## 12. How does idle differ from NonResponsiveConsumerEvent?

Within the **Idle and Non-Responsive** topic, this is the single most important distinction:

| Aspect | Listener idle | Consumer non-responsive |
|---|---|---|
| Primary sign | No records delivered within configured interval | Consumer fails to poll on cadence per monitor |
| Poll loop | Can still be running normally | May be blocked or spending too long processing |
| Related mechanisms | `idleEventInterval`, `ListenerContainerIdleEvent`, `ConsumerSeekAware.onIdleContainer` | `NonResponsiveConsumerEvent`, `monitorInterval`, `noPollThreshold` |
| Guarantees topic is out of records? | No | No |
| Appropriate for seeking? | Potentially, if a valid replay request exists | No; prioritize diagnosing the slow/stuck consumer thread |
| Typical action | Observe idle or apply a controlled seek | Alert, thread dump, inspect poll/DB/API/locks |

A listener blocked in a long database call can **fail to return to the poll loop**. Even if `onIdleContainer` fires from the container's processing loop, never use it to detect a consumer hung inside a long call.

Conversely, when a Kafka topic is quiet while the consumer keeps polling healthily, a `NonResponsiveConsumerEvent` must not be inferred simply from missing messages.

## 13. Separate non-responsive monitor configuration

Spring Kafka provides mechanisms to monitor whether a consumer polls frequently enough, using settings such as **`monitorInterval`** and **`noPollThreshold`** in supported versions.

Separate configuration example:

~~~java
factory.getContainerProperties()
        .setIdleEventInterval(15_000L);

factory.getContainerProperties()
        .setPollTimeout(1_000L);

factory.getContainerProperties()
        .setNoPollThreshold(3.0f);

factory.getContainerProperties()
        .setMonitorInterval(10);
~~~

This example illustrates two distinct setting groups. Actual values, units of `monitorInterval` and `pollTimeout`, and detection algorithms depend on Spring Kafka version; choose them according to your application's processing times.

**Never turn `onIdleContainer` into a thread-deadlock monitor.** Logic that automatically seeks when a consumer is non-responsive can mask the incident or create additional duplicates once the thread recovers.

When observing non-responsiveness, inspect listener processing duration, `max.poll.interval.ms`, database waits, thread pool saturation, and consumer rebalance counts.

## 14. ListenerContainerIdleEvent vs onIdleContainer

Both mechanisms relate to idle state, yet serve different roles:

### ListenerContainerIdleEvent

This is a **Spring application event**. Applications can subscribe to it:

~~~java
@Component
public class IdleObserver {

    private static final Logger log =
            LoggerFactory.getLogger(IdleObserver.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.info(
                "Listener container idle, listenerId={}, partitions={}",
                event.getListenerId(),
                event.getTopicPartitions());
    }
}
~~~

Event getter APIs can vary by Spring Kafka version; this example shows the pattern of observing idle via `@EventListener` and reading event context. Where getter names differ across versions, use the fields/metadata actually exposed by your dependency.

### ConsumerSeekAware.onIdleContainer

This is a **callback on a listener implementing `ConsumerSeekAware`**:

~~~java
@Override
public void onIdleContainer(
        Map<TopicPartition, Long> assignments,
        ConsumerSeekCallback callback) {
    // Can call callback.seek(...) in the appropriate context.
}
~~~

**Event listeners** suit metrics, alerts, dashboards, or notifications. **`ConsumerSeekAware` callbacks** suit framework-provided seek operations without grabbing `KafkaConsumer` and seeking outside the consumer thread.

Never use a `ListenerContainerIdleEvent` listener to grab the consumer object and hand it to a background thread to seek; `KafkaConsumer` cannot be accessed concurrently at will.

## 15. Which thread runs onIdleContainer?

Spring Kafka invokes `onIdleContainer` while the listener container handles idle state on the **consumer thread**. That matters because seek operations on `KafkaConsumer` must respect thread confinement.

~~~text
Consumer thread C
     |
     +-- poll
     +-- detects idle
     +-- onIdleContainer(assignments, callback)
     |      |
     |      +-- callback.seek(...)
     |
     +-- continues polling from new position
~~~

Inside the callback:

- Operate only on partitions present in `assignments`.
- Keep seek decisions short and non-blocking.
- Never wait seconds on a REST call or database query.
- Never sleep waiting for data.
- Never acquire global locks that block other listeners.
- Never call `listenerContainer.stop()` synchronously on the consumer thread.

If policies must be fetched from a database or approval system, prepare **replay requests/checkpoints beforehand** in a separate service. `onIdleContainer` only applies pre-prepared decisions, keeping network I/O out of the poll loop.

## 16. Can the callback received in onIdleContainer be saved for later?

Spring Kafka passes callbacks across multiple contexts. Specifically, the callback passed to **`onPartitionsAssigned`** or **`onIdleContainer`** is meant for use inside that lifecycle method, differing semantically from the callback provided to **`registerSeekCallback`**.

Safety rules:

1. **Use the `onIdleContainer` callback parameter directly inside that method.**
2. Never store the `onIdleContainer` callback in a field to invoke later from an HTTP thread.
3. If proactive seeks must be requested from another thread, use **`registerSeekCallback`** and Spring Kafka's scheduled seek mechanism supported in your version.
4. For concurrent listeners, track callbacks per consumer thread/assignment; never overwrite one global callback and seek partitions belonging to a different consumer.

An error-prone pattern:

~~~java
private ConsumerSeekCallback latestCallback;

@Override
public void onIdleContainer(
        Map<TopicPartition, Long> assignments,
        ConsumerSeekCallback callback) {

    latestCallback = callback; // Never store lifecycle callbacks arbitrarily.
}

public void seekFromHttpThread(...) {
    latestCallback.seek(...); // Unsafe when used in the wrong context.
}
~~~

Instead, a simpler pattern places **seek requests** in a `ConcurrentMap` or durable request queue and applies them inside `onIdleContainer` when the framework invokes the callback on the consumer thread.

## 17. When is registerSeekCallback used?

**`registerSeekCallback`** is designed for cases where the application must perform seeks that do not necessarily coincide with an idle or assignment callback. Spring Kafka supports storing the appropriate callback and executing requested seeks via that callback API.

Interface sketch:

~~~java
@Override
public void registerSeekCallback(
        ConsumerSeekCallback callback) {

    // Can store the callback per consumer context,
    // but must follow threading and assignment rules
    // of the Spring Kafka version in use.
}
~~~

Do not confuse this registered callback with the parameter passed into `onIdleContainer`. In high-concurrency applications, one listener bean can be shared by multiple consumer threads. Thus callbacks typically need to be mapped per thread or container instance and updated as assignments/revocations occur.

If your requirement is simply "replay only when idle", a **pending seek map** applied inside `onIdleContainer` is clearer and safer than exposing callbacks externally. If immediate replay is needed without waiting for idle, build a dedicated seek-control service using `registerSeekCallback` per your version's supported API.

## 18. How do rebalances affect pending seeks?

Partitions owned by a listener can change owners during scaling, deployments, or group rebalances.

~~~text
Before:
  Consumer A owns orders.events/P2

Operator requests replay:
  orders.events/P2 -> offset 105

Rebalance:
  P2 moves to Consumer B

After:
  Consumer A no longer has authority to seek P2
  Consumer B is the new owner
~~~

If a pending seek lives in memory inside Consumer A's listener bean, that request **does not automatically migrate to Consumer B**. Consumer A's `onIdleContainer` callback must not try to seek a partition no longer in its assignments.

Two models exist:

- **Best-effort local request:** execute only while the current consumer still holds ownership; if assignment is lost, the request expires or must be resubmitted.
- **Durable replay request:** store the request in a database or command topic with owner coordination, versioning, and auditing; the current partition owner reads and applies it once.

In multi-replica deployments, maintain a single source of truth for replay requests. Never build an admin API that sends a command to a random pod assuming that pod owns the partition.

## 19. How does onPartitionsAssigned complement replay?

When partitions are assigned, a listener can use **`onPartitionsAssigned`** to initialize read positions from a checkpoint or policy:

~~~java
@Override
public void onPartitionsAssigned(
        Map<TopicPartition, Long> assignments,
        ConsumerSeekCallback callback) {

    assignments.forEach((partition, currentPosition) -> {
        Long checkpoint = checkpointService.findReplayCheckpoint(partition);

        if (checkpoint != null) {
            callback.seek(
                    partition.topic(),
                    partition.partition(),
                    checkpoint);
        }
    });
}
~~~

`CheckpointService` here is an application service. This snippet illustrates the logic; to avoid blocking the Kafka consumer thread, checkpoints should be cached or served via a bounded/pre-populated lookup before the callback runs.

**`onPartitionsAssigned`** fits initializing read positions right upon assignment. **`onIdleContainer`** fits triggering seeks only when idle. Never seek the same checkpoint unconditionally in both callbacks without a request/version guard, or you will trigger duplicate replays or prevent the consumer from advancing.

## 20. How should onPartitionsRevoked handle state?

When a consumer loses partition assignments, state and callback context bound to old partitions must be updated:

~~~java
@Override
public void onPartitionsRevoked(
        Collection<TopicPartition> partitions) {

    for (TopicPartition partition : partitions) {
        log.info("Partition revoked: {}", partition);
        // Update partition ownership/metrics.
        // Do not try to seek a partition that left the assignment.
    }
}
~~~

Do not wipe **all** state for **all** partitions when a cooperative rebalance only revokes a subset of assignments. The `partitions` parameter specifies which partitions to handle in the current callback.

For pending durable requests, do not permanently delete a request merely because the previous owner lost its assignment. Let the new owner pick it up or re-coordinate once confirmed the request was not yet applied.

If a consumer is killed abruptly, `onPartitionsRevoked` may never execute. Critical replay workflows must never rely entirely on in-memory cleanup callbacks.

## 21. Concurrency: one bean, multiple consumer threads

When `@KafkaListener` uses `concurrency > 1`, Spring Kafka creates multiple consumer threads/child containers. A single bean implementing `ConsumerSeekAware` can be invoked by multiple consumer contexts.

~~~text
OrderEventListener bean
         |
         +-- consumer thread A -> partitions P0,P1
         |
         +-- consumer thread B -> partitions P2,P3
         |
         +-- consumer thread C -> partitions P4,P5
~~~

Inside `onIdleContainer`, each callback's `assignments` belongs to its own consumer context. Therefore:

- Only seek partitions present in the current `assignments`.
- Use a `ConcurrentMap` or thread-safe registry for requests submitted from other threads.
- Never share a single global `currentOffset` variable across all consumers.
- Never store one callback reference and treat it as representing the entire listener.
- Distinguish child listener IDs and current partition owners in logs.
- Never assume P2 always belongs to consumer B; rebalances change assignments.

To replay a specific partition from an admin API, route the request to the owning consumer or persist it in a shared store for the current owner to pick up.

## 22. Why not seek all partitions automatically when idle?

A topic may have six partitions where only one genuinely needs replay while five processed cleanly.

~~~text
orders.events
  P0 -> processed to 500
  P1 -> processed to 700
  P2 -> replay request to 105
  P3 -> processed to 920
  P4 -> processed to 160
  P5 -> processed to 430
~~~

If `onIdleContainer` rewinds all assigned partitions to the start of the log, the system can trigger massive reprocessing and violate ordering/business state across the five unrelated partitions.

A well-formed request should specify:

~~~text
requestId: replay-2026-001
topic: orders.events
partition: 2
targetOffset: 105
reason: rebuild-order-projection
requestedBy: operator-identity
expiresAt: a bounded expiration timestamp
status: PENDING / APPLIED / FAILED
~~~

These fields represent application design, not built-in Kafka record headers. The goal is scoping impact and preserving auditability, rather than firing an uncontrolled cluster-wide seek.

## 23. Replay and processing order

Kafka preserves order **within a single partition** by offset. Seeking backward causes the consumer to re-read previously processed records, which can make business systems see older events after newer ones.

Example:

~~~text
P2:
  offset 105 -> OrderCreated
  offset 106 -> OrderPaid
  offset 107 -> OrderShipped
  offset 108 -> OrderCancelled

Application already processed through 108.
Seek to 105:
  OrderCreated is delivered again after OrderCancelled.
~~~

If a projection applies events in order and supports rebuilding from scratch, replay makes sense. However, if handlers re-send "order created" emails, deduct inventory, or issue refunds, unguarded replay causes unwanted side effects.

Common safeguards:

- Idempotent handlers keyed by event ID.
- Checking aggregate versions or valid state transitions.
- Running replays in a dedicated consumer group or isolated environment.
- Emitting outputs only to rebuild topics without calling external APIs.
- Marking replay mode explicitly so handlers skip non-repeatable side effects.

Never treat Kafka offsets as immutable business identifiers when events may be republished to another topic or cluster.

## 24. Impact on group committed offsets

Seeking changes consumer position, while the group's committed offset may still sit at the old mark.

~~~text
Before replay:
  consumer position = 500
  committed offset  = 500

onIdleContainer seek(200)
  consumer position = 200
  committed offset  = 500 (unchanged yet)

Consumer re-reads and reprocesses from 200
~~~

Subsequently, the container may commit offsets from the newly processed records per `AckMode`/transaction policy. That can cause the group's committed offset to advance along the replay or move backward to the seek target, depending on processing and commit order.

Never rely on a single seek to preserve a read position across restarts without corresponding commit/checkpoint handling.

If you need to replay historical data **without altering a production consumer group's progress**, the safer approach is usually **using a separate consumer group**. A separate group maintains independent committed offsets, avoiding disruption to live topic consumption.

## 25. AckMode and manual acknowledgment

Spring Kafka containers support `AckMode` options such as `RECORD`, `BATCH`, `MANUAL`, and `MANUAL_IMMEDIATE`. How the container commits offsets directly shapes seek outcomes.

Manual-ack listener example:

~~~java
@KafkaListener(
        topics = "orders.events",
        containerFactory = "manualAckFactory")
public void consume(
        ConsumerRecord<String, OrderEvent> record,
        Acknowledgment acknowledgement) {

    projectionService.apply(record.value());
    acknowledgement.acknowledge();
}
~~~

This snippet assumes `manualAckFactory` uses the matching `AckMode`. Acknowledgment happens **after** business logic succeeds. Acking early before seeking or crashing can mark records processed while side effects remain incomplete.

When a listener processes asynchronously, enqueueing a record does not mean it finished; seek-on-idle can run while worker pools are still executing tasks from earlier records. Track in-flight tasks and enforce idempotency.

In Kafka-to-Kafka transactions, consumed offsets may be committed inside the Kafka transaction. Never call `commitSync` manually inside `onIdleContainer` to "save the seek", as that can break the container's transaction semantics.

## 26. Idle callbacks and asynchronous tasks

Suppose a listener receives records and offloads work to an executor:

~~~java
@KafkaListener(topics = "orders.events")
public void consume(OrderEvent event) {
    workerPool.execute(() -> projectionService.apply(event));
}
~~~

Because the method returns immediately, the container can keep polling and later go idle even while the worker pool still holds unfinished jobs.

~~~text
12:00:00  Listener enqueues A, B, C
12:00:01  Listener callback already returned
12:00:15  Container goes idle
           -> onIdleContainer invoked

Yet worker pool:
  A = DONE
  B = RUNNING
  C = QUEUED
~~~

If the callback seeks back to A's offset to replay while B is still updating the database, the system can run two concurrent chains for the same event or invert business effect ordering.

To use seek-on-idle safely in an async system:

1. Track in-flight tasks per partition.
2. Never equate idle with `in-flight = 0`.
3. Wait for a bounded quiescence condition in a coordinator outside the consumer thread.
4. Enqueue the replay request only when business state is safe.
5. Apply the seek briefly inside the callback without waiting on the worker pool inside `onIdleContainer`.
6. Protect against duplicate side effects with idempotency.

## 27. Consumer pause and idle callbacks

Pause and idle are two separate concepts:

| State | Meaning |
|---|---|
| **`RUNNING, ACTIVE`** | Consumer continues delivering records to the listener |
| **`PAUSED`** | Consumer may keep polling, yet pauses delivering records from paused partitions |
| **`IDLE`** | Container delivered no records within `idleEventInterval` |
| **`STOPPED`** | Consumer/container closed per lifecycle |
| **`NON_RESPONSIVE`** | Consumer failed poll cadence per monitor |

A paused consumer receives no records and can therefore look idle depending on version/container behavior. **Never use `onIdleContainer` as a substitute for `pause`/`resume`.**

If an application is paused due to database overload, auto-seeking on idle can inflate the replay backlog, triggering an even bigger load spike upon resume. Check desired pause state and pause reason before applying replays.

Once a container is stopped, idle callbacks do not keep firing like an independent scheduler. If you need scheduled automatic replays, never use `onIdleContainer` as your primary scheduler.

## 28. Idle and ConsumerStoppedEvent

Spring Kafka emits distinct lifecycle events for operations:

~~~text
ListenerContainerIdleEvent
  -> container received no records during idle period

ConsumerStoppedEvent
  -> consumer has stopped

NonResponsiveConsumerEvent
  -> consumer is not polling on cadence

ConsumerPausedEvent / ConsumerResumedEvent
  -> consumer pause/resume took effect
~~~

These events do not substitute for one another:

- Idle does not mean stopped.
- Stopped does not mean idle.
- Paused does not mean the consumer lost group assignments.
- Non-responsive is not a seek request.

Dashboards should separate these states: listener running, current assignment, pause requested/observed, idle duration, non-responsive count, and consumer lag.

## 29. When is seek-on-idle a good idea?

Seek-on-idle can fit well when:

- The consumer drives a **projection rebuild** rather than triggering external side effects.
- Replay targets have been pre-validated.
- Requests are explicit, one-shot, authorized, and audited.
- The consumer group can tolerate re-reading records and shifting progress.
- Handlers are idempotent or operate in rebuild mode.
- The listener is genuinely idle with zero related in-flight work.

Seek-on-idle is generally **inappropriate** when:

- Production listeners process payments or non-idempotent actions.
- The consumer is stuck/not polling and needs non-responsive diagnostics.
- The application needs immediate replay without waiting for idle.
- Replay spans multiple partitions/instances with shifting ownership.
- Source data may have passed retention unchecked.
- You merely want to know why a topic has no records; monitoring alone suffices there.

For a one-time historical scan to rebuild data, a dedicated job or separate consumer group is usually easier to control than steering a production group via idle callbacks.

## 30. Should replay targets use offsets or timestamps?

Kafka locates records by partition + offset. Some use cases specify a point in time instead of an exact offset:

~~~text
Replay request:
  topic = orders.events
  partition = 2
  fromTimestamp = 2026-11-15T10:00:00Z
~~~

In that case, resolve the timestamp into a valid offset or use timestamp-based seek APIs supported by your Spring Kafka version. Never assume a timestamp maps 1:1 to a single event: multiple records can share the same timestamp, and Kafka supports `CREATE_TIME` or `LOG_APPEND_TIME` depending on topic config.

When a reliable checkpoint offset already exists, `callback.seek(topic, partition, offset)` is simplest and clearest. When seeking by timestamp, verify semantics, retention, and clock accuracy on both producer and Kafka topic.

Never pass `System.currentTimeMillis()` directly as an offset; those are completely different units.

## 31. Observability and logging for onIdleContainer

An idle callback must not spam ERROR logs every time no records arrive. Quiet topics can be completely normal.

Useful logs when a replay request exists:

~~~text
event=seek_on_idle_requested
requestId=replay-001
listenerId=orders-idle-seek-listener
topic=orders.events
partition=2
targetOffset=105
requestedBy=operator

event=seek_on_idle_applied
requestId=replay-001
listenerId=orders-idle-seek-listener
topic=orders.events
partition=2
observedPositionBefore=340
targetOffset=105
~~~

This is an application-designed structured log format, not a built-in Spring Kafka log format.

Metrics to track:

- Idle callback count and idle duration.
- Seek request count, applied count, and rejected count.
- Latency from request submission to seek callback execution.
- Replay records processed and replay failure counts.
- Consumer lag and offset commit rate.
- Rebalance count and assignment changes.
- In-flight business tasks if the listener is async.
- Separate `NonResponsiveConsumerEvent` count.
- DLT/retry rates when replayed records fail.

Never use individual offsets or request IDs as metric labels due to high cardinality. Put them in controlled logs/traces instead.

## 32. Avoid heavy work inside the callback

An unsuitable implementation:

~~~java
@Override
public void onIdleContainer(
        Map<TopicPartition, Long> assignments,
        ConsumerSeekCallback callback) {

    for (TopicPartition partition : assignments.keySet()) {
        // Avoid slow REST/DB calls directly on the consumer thread.
        Long target = remoteReplayService.fetchNextOffset(partition);

        if (target != null) {
            callback.seek(
                    partition.topic(),
                    partition.partition(),
                    target);
        }
    }
}
~~~

If `remoteReplayService` runs slowly, the consumer thread cannot return to poll on time. The application can hit `max.poll.interval.ms`, rebalances, or `NonResponsiveConsumerEvent`—the exact failure operations teams want to avoid.

A better model:

~~~text
Admin API / Scheduler / Database worker
       |
       +-- validate request + permissions
       +-- resolve checkpoint/target
       +-- validate offset range
       |
       v
Thread-safe pending replay store
       |
       v
onIdleContainer (consumer thread)
       |
       +-- read prepared request
       +-- callback.seek(...)
       +-- record brief state update
       |
       v
Continue polling
~~~

If durable audit writes could block the thread, push state transitions onto a queue/event and let a separate worker persist the audit log. If auditing is mandatory before replay, record approval/audit **before** the seek callback rather than opening a long DB transaction inside the callback.

## 33. Handling seek errors

Not every seek request succeeds:

- Target offset is invalid or past retention.
- Partition left the assignment due to a rebalance.
- Consumer/container is stopping.
- Request targets a topic the listener is not subscribed to.
- Callback is no longer valid per lifecycle.
- Recovery workflow forbids replaying a specific event.

In the `pendingSeeks` example, consider tracking states:

~~~text
PENDING
   |
   +-- invalid target -> REJECTED
   |
   +-- no longer owner -> WAITING_FOR_OWNER
   |
   +-- callback applied -> APPLIED
   |
   +-- exception -> FAILED_RETRYABLE or FAILED_FINAL
~~~

Never mark `REPLAY_COMPLETED` right after `callback.seek`. **Seek applied only means the read position change was requested**; reprocessing records and committing outcomes are a separate stage.

If business-level exactly-once effects are required, enforce transactions/idempotency at the destination sink. Seeking itself never provides exactly-once delivery.

## 34. Kafka transactions and seek-on-idle

In consumer-initiated Kafka transactions, the container coordinates Kafka outputs with consumed offsets via a transactional producer. Seeking alters read position, yet must never be used to skip or force-complete an in-flight transaction.

~~~text
Consumer receives P2@100
      |
      v
Kafka transaction T1
      |
      +-- produce output
      +-- process result
      |
      v
Commit or abort T1 per container
      |
      v
Later, at an appropriate idle lifecycle point,
onIdleContainer may apply a seek request.
~~~

When replaying the same record, the listener can run again and produce outputs inside a new transaction. Kafka transactions guarantee atomicity of records/offsets **within each transaction**, without preventing an intentional replay from creating a fresh Kafka execution.

If outputs from the first pass already committed and the event replays cleanly, downstream consumers may see an equivalent event at a new Kafka offset. Maintain stable event IDs and deduplication rules, or use a dedicated consumer group for rebuilds.

Never call `consumer.commitSync()` inside `onIdleContainer` to force offsets when the container manages Kafka transactions; that can break output-and-offset atomicity.

## 35. Listener idle when a topic has an open transaction

A consumer with `isolation.level=read_committed` only sees committed transactional records. If an open transaction sits ahead of the Last Stable Offset, the consumer may receive no new records even though brokers already appended batches behind it.

~~~text
Topic log:
  committed record A
  open transaction T1
  committed record B behind it

read_committed consumer:
  may have to wait at the Last Stable Offset
~~~

Therefore, a `ListenerContainerIdleEvent` or `onIdleContainer` callback does not prove the topic is empty. The consumer may simply be waiting for a transaction to resolve.

If this creates lag, inspect Kafka transaction durations, producer commit/abort errors, and Last Stable Offset rather than automatically seeking backward to "nudge" the consumer.

Seeking cannot resolve an open transaction or one stuck at the broker coordinator.

## 36. Integration test patterns with a Kafka broker

A unit test invoking `onIdleContainer` directly with a mock map and mock callback can test seek-routing logic. However, proving **container idle → callback → consumer position changes** requires real Kafka in tests, such as Testcontainers Kafka or EmbeddedKafka.

### Test 1: callback invoked when idle

1. Create topic `orders.events`.
2. Start a listener implementing `ConsumerSeekAware` with a short test `idleEventInterval`.
3. Ensure the listener received assignments.
4. Send no records during the interval.
5. Use a `CountDownLatch` in a test observer to verify `onIdleContainer` is called.
6. Verify `assignments` contains the expected `TopicPartition` entries.

Never simply sleep for a fixed duration and assume the callback ran; wait on an explicit condition with timeout.

### Test 2: no automatic seek without a request

1. Send a record and wait for the listener to process it.
2. Let the container go idle.
3. Submit no replay requests.
4. Verify the listener does not reprocess the record merely because it went idle.
5. Verify offsets/processed counts remain accurate.

### Test 3: one-shot replay

1. Produce a record and capture its actual topic/partition/offset.
2. Wait for initial listener processing.
3. Call `requestReplay` with that exact offset.
4. Wait for the idle callback.
5. Verify the listener receives the record one more time within test scope.
6. Wait for idle again and verify no infinite seek loop occurs once the pending request is cleared.

If tests send multiple records, design wait conditions distinguishing replayed records from new ones, such as fixed event IDs and separate counters.

### Test 4: target past retention

1. Configure appropriate topic/retention settings.
2. Pick a target offset before log start.
3. Submit a replay request.
4. Verify application policy rejects or handles the invalid offset cleanly.
5. Verify no infinite retry/seek loop occurs.

### Test 5: rebalance before idle

1. Create a multi-partition topic and two consumer instances in the same group.
2. Queue a pending request for partition P2 on instance A.
3. Trigger a rebalance so P2 moves owners.
4. Verify A does not seek P2 once P2 leaves its assignments.
5. With durable requests, verify the new owner B picks up and applies the request.

### Test 6: non-responsive vs idle

1. Let the consumer poll normally on an empty topic.
2. Verify idle callbacks/events fire as expected.
3. Induce slow listener processing triggering no-poll monitoring.
4. Verify `NonResponsiveConsumerEvent` is tracked under its own policy.
5. Never auto-seek when only a non-responsive alert exists.

### Test 7: callback must not block

1. Have another thread prepare the pending replay target.
2. When the idle callback runs, read only in-memory prepared data and call seek.
3. Measure callback duration.
4. Verify the poll thread never waits on remote network I/O.
5. Verify the consumer does not rebalance because of a blocking callback.

### Test 8: duplicate business effects

1. Send an event with a fixed event ID.
2. Listener writes side effects to an idempotent test database.
3. Seek to replay that record.
4. Verify the listener can be re-invoked without duplicating the side effect.
5. If producing Kafka output, verify event IDs and downstream deduplication strategies.

Tests should set clear timeouts and isolation. Never use production groups or live Kafka data to test backward seeks.

## 37. Common design mistakes

| Mistake | Why it is dangerous | Alternative |
|---|---|---|
| Seeking to offset 0 on every idle | Creates an unbounded replay loop | Stateful one-shot replay requests |
| Treating `assignments` positions as committed offsets | Can diverge from commits or transactions | Inspect group committed offsets/checkpoints separately |
| Treating idle as non-responsive consumer | Misdiagnoses root cause | Monitor `NonResponsiveConsumerEvent` separately |
| Calling `KafkaConsumer.seek` from an HTTP thread | Violates thread confinement | Use `ConsumerSeekCallback` in proper lifecycle |
| Saving `onIdleContainer`'s callback for later calls | Invalid lifecycle context | Use callback inside the method; use `registerSeekCallback` for external requests |
| Querying slow databases inside `onIdleContainer` | Blocks poll thread and risks rebalance | Pre-prepare requests via another worker |
| Seeking partitions outside `assignments` | Lost ownership or logic race | Seek only currently assigned partitions |
| Using local in-memory pending requests across pods | Requests don't follow ownership on rebalance | Durable requests + owner coordination |
| Treating seek applied as replay completed | No proof of processing or commit yet | Track replay completion separately |
| Skipping retention checks | Offset may already be purged | Validate log start/end before replay |
| Rewinding production consumer group to rebuild | Disrupts live processing and group offsets | Prefer a dedicated consumer group |
| Lacking idempotency during replay | Duplicate side effects, duplicate outputs | Event IDs, unique constraints, replay mode |

## 38. Relationship to production Spring Kafka applications

Safe operations clearly separate three layers:

~~~text
Control plane
  - Who is authorized to replay?
  - Which topic/partition/offset?
  - Why? Within what time window?
  - Validate retention and approvals
          |
          v
Durable replay request store
          |
          v
Kafka listener owner
  - ConsumerSeekAware.onIdleContainer
  - Apply valid request only when assigned and idle
  - Never block the poll thread
          |
          v
Processing/data plane
  - Consumer re-reads record
  - Idempotent business handling
  - Track Kafka/database outputs
  - Record replay outcome
~~~

The control plane never touches the data plane's `KafkaConsumer` directly. It only submits validated requests. The owning listener applies seeks in the proper lifecycle, while the processing layer governs whether re-read records re-apply effects.

If your goal is automatically retrying failing records, **`DefaultErrorHandler`, backoffs, and DLTs** are usually the right tools. `onIdleContainer` is neither an error-handler replacement nor a retry-delay scheduler.

## 39. Common misconceptions

**`onIdleContainer` runs after every empty `consumer.poll()`.** False. It ties to container idle conditions per `idleEventInterval` and lifecycle config, not every empty poll.

**Idle means the Kafka topic has no data left.** False. Other partitions may hold records, transactions may be open, or the consumer may be paused.

**Idle means the consumer thread is hung.** False. The consumer can be polling healthily with no incoming messages.

**`ConsumerSeekAware.onIdleContainer` and `ListenerContainerIdleEvent` are the same API.** False. One is a listener callback; the other is a Spring application event.

**The `assignments` map definitely contains committed offsets.** False. It contains position/offset info supplied by the container at callback time; separate consumer position from group committed offsets.

**Calling `callback.seek` means Kafka already committed the new offset.** False. Seeking moves the read cursor; committing group offsets is separate.

**Kafka persists seeks forever across restarts.** False. Across restarts/rebalances, committed offsets and assignments determine default start positions unless new seeks/checkpoints apply.

**Seeking backward re-reads only one record and stops.** False. The consumer can re-read the entire sequence from the target through the end of the log.

**`onIdleContainer` guarantees zero in-flight business tasks.** False if the listener uses worker pools or async execution.

**You can invoke `onIdleContainer`'s callback from any thread anytime.** Do not. Use the callback inside its lifecycle method and Spring Kafka's dedicated external seek mechanism when needed.

**Cooperative rebalances revoke all partitions.** False. Only a subset of partitions may change owners.

**A replay request can be sent to any pod.** False. That pod must own the partition or coordinate so the current owner handles it.

**Seek-on-idle automatically handles deserialization, retries, and DLTs.** False. Those belong to separate error-handling mechanisms.

**Kafka transactions eliminate all duplicate side effects on replay.** False. Replay is a fresh execution; databases and APIs still need idempotency.

## 40. Recommended implementation workflow

To use `ConsumerSeekAware.onIdleContainer` in Spring Kafka Reliability Operations:

1. Enable seek-on-idle only for a **clear business need**—never treat idle as a fault.
2. Configure `idleEventInterval` on the right listener container factory.
3. Have the listener bean implement `ConsumerSeekAware` and define `onIdleContainer` with `Map<TopicPartition, Long>` and `ConsumerSeekCallback`.
4. By default, **do not seek** unless an approved replay request exists.
5. Persist requests with topic, partition, target offset, request ID, reason, and status.
6. Validate non-negative targets, valid partitions, and offsets still within retention.
7. Apply seeks only to partitions present in the current callback's `assignments`.
8. Never run REST/DB queries or long sleeps on the consumer thread.
9. Invoke `callback.seek` immediately inside `onIdleContainer`; never stash lifecycle callbacks for arbitrary cross-thread calls.
10. Handle rebalances, partition revocations, and multiple replicas with ownership-aware request tracking.
11. Separate seek-applied from replay-completed, tracking progress and outcomes.
12. Enforce event IDs and idempotency to avoid duplicate side effects when records are re-read.
13. Prefer a separate consumer group when rebuilding history without disturbing production group progress.
14. Keep **idle** metrics separate from **non-responsive**, pause, stop, and rebalance metrics.
15. Test one-shot replays, expired offsets, concurrent consumers, async in-flight tasks, and transaction boundaries against a test Kafka broker.

**`ConsumerSeekAware.onIdleContainer`** is a valuable extension point allowing applications to **seek when a listener container is idle**, using assignment info and `ConsumerSeekCallback` provided by Spring Kafka. It does not cure non-responsive consumers, commit offsets on its own, or remove duplicate-processing risks. Paired with controlled replay requests, accurate ownership, brief callback execution, and idempotent processing, seek-on-idle becomes a reliable operational tool while preserving Kafka's reliability guarantees.
