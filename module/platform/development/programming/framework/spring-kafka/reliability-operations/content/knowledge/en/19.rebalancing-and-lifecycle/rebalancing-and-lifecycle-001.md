# Partition assignment event

## 1. What is a partition assignment event?

In Spring Kafka, a **partition assignment event** is a notification related to a Kafka consumer being assigned permission to read one or more partitions. A consumer can only read data from the partitions currently assigned to it. The assignment changes when a consumer group starts up, rebalances, scales the number of instances, a consumer leaves the group, or the subscription changes.

Spring Kafka publishes **application events** so that the application can observe this lifecycle, specifically:

- **ConsumerPartitionAssignedEvent**: notifies that the consumer container has been assigned partitions.
- **ConsumerPartitionRevokedEvent**: notifies that partitions were revoked during a rebalance.
- **ConsumerPartitionLostEvent**: notifies that the consumer has lost partitions under the corresponding scenario.

A partition assignment event is not a Kafka record sent by a producer to a topic. It is an event **inside the Spring application** published by the listener container when managing `KafkaConsumer`.

~~~text
Kafka topic orders.created
    P0    P1    P2    P3
     \     |     |    /
      \    |     |   /
       Consumer group rebalance
                  |
                  v
       Kafka partition assignment
                  |
         +--------+--------+
         |                 |
     Consumer A         Consumer B
       P0, P1             P2, P3
         |                 |
         v                 v
    Spring Kafka       Spring Kafka
  listener container listener container
         |                 |
         +---- publish ----+
                  |
                  v
      ConsumerPartitionAssignedEvent
                  |
                  v
       @EventListener / monitoring
~~~

This lesson belongs to the **Rebalancing and lifecycle** group: you need to understand when the event is generated, what observation or logic it should be used for, how it differs from the Kafka `ConsumerRebalanceListener` callback, and how to operate safely when partition ownership changes.

## 2. Why is assignment important?

Kafka divides a topic into partitions. Within a consumer group, at any valid point in time, each partition is assigned to at most one consumer in the group. This is the basis for the group to distribute load and preserve reading order per partition.

Suppose the topic **orders.created** has six partitions. Three consumers in the same group **fulfillment-workers** may receive:

~~~text
Consumer A -> P0, P1
Consumer B -> P2, P3
Consumer C -> P4, P5
~~~

If Consumer B stops, Kafka needs to assign P2 and P3 to the remaining members. At that point, the partition assignment changes. The application must be ready to:

- Start processing the newly assigned partitions.
- Stop treating the revoked partitions as owned by the old consumer.
- Restore local state that is only valid while owning the partition.
- Handle redelivered records because previous offsets were not committed.
- Observe consumer lag, throughput, and rebalance duration.

An **assignment event** helps the application recognize the ownership transition process. It does not fix offsets by itself, does not guarantee local state is correct, and does not replace error handlers or the Kafka commit mechanism.

## 3. Kafka assignment differs from Spring application events

Two layers need to be distinguished:

| Layer | Component | Responsibility |
|---|---|---|
| Kafka client | Consumer group coordinator and assignor | Decides which partitions belong to which consumer |
| Kafka client callback | ConsumerRebalanceListener | Notifies assignment, revoke, and loss during poll/rebalance |
| Spring Kafka | KafkaMessageListenerContainer | Manages consumer, poll loop, listener, offsets, and lifecycle |
| Spring Kafka | ConcurrentMessageListenerContainer | Manages multiple child containers, each child has its own consumer |
| Spring application event | ConsumerPartitionAssignedEvent | Lets Spring beans observe information about assigned partitions |

**Spring application events do not decide partition assignment**. The decision belongs to the Kafka group protocol, coordinator, and partition assignor. Spring Kafka's event reflects an event in the container's lifecycle.

### 3.1. Two easily confused hook types

An application can receive assignment information via:

1. **@EventListener** handling ConsumerPartitionAssignedEvent.
2. **ConsumerAwareRebalanceListener** attached directly to the container.

Both relate to rebalancing, but do not share the same contract regarding timing, thread, and permission to operate on `KafkaConsumer`. When you need to perform a seek or ensure logic runs synchronously with the rebalance, the rebalance callback is usually more suitable.

## 4. ConsumerPartitionAssignedEvent

The class name provided by Spring Kafka is **org.springframework.kafka.event.ConsumerPartitionAssignedEvent**.

This event describes the partitions assigned to the container. The application can use it to update a dashboard, write logs, or notify an observability system about ownership.

A simple handler:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerPartitionAssignedEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaPartitionLifecycleObserver {

    @EventListener
    public void onAssigned(ConsumerPartitionAssignedEvent event) {
        log.info(
            "Kafka partitions assigned: {}",
            event.getPartitions()
        );
    }
}
~~~

**getPartitions()** returns information about the `TopicPartition`s related to the assignment event. Each `TopicPartition` is a pair of topic and partition ID.

Example log:

~~~text
Kafka partitions assigned:
[orders.created-0, orders.created-1]
~~~

The number of partitions may be 0 or change between assignments depending on the group protocol, partition assignor, and rebalance phase. Do not hardcode an assumption that every event always carries all partitions of the topic or that there is exactly one event per deployment.

### 4.1. The event does not contain business records

An assigned event is not a `ConsumerRecord` and does not contain an order payload, `eventId`, or business key. It describes consumer ownership.

Do not use an assignment handler to process record contents in place of `@KafkaListener`. Business data still flows through the Kafka consumer poll and the corresponding listener method.

### 4.2. Do not rely on the event as a distributed lock mechanism

Kafka group assignment guarantees ownership according to consumer group semantics, but a local application event is not a lock or lease for resources outside Kafka.

If the application wants to allow strictly one instance to write to a table/partition outside Kafka, consider fencing, ownership epochs, idempotency, or distributed coordination. Do not simply rely on having received `ConsumerPartitionAssignedEvent` and holding a local boolean forever.

## 5. Partition revoked and partition lost events

To understand the assigned event, you need to know the symmetrical events:

| Event | Operational meaning | Common action |
|---|---|---|
| ConsumerPartitionAssignedEvent | Consumer is assigned partitions | Log, update ownership mapping, prepare local state |
| ConsumerPartitionRevokedEvent | Partitions are revoked during rebalance | Stop processing under old ownership, clean up local state |
| ConsumerPartitionLostEvent | Consumer no longer owns partitions due to a loss scenario | Stop using old ownership, do not attempt to commit as if still owning |

**Revoked** and **lost** are not synonymous. With a normal revoke, the consumer may still have a chance to complete cleanup/commit steps in the rebalance phase via the appropriate callback. With lost, ownership may already have moved elsewhere; it is unsafe to treat the old consumer as still having permission to manipulate offsets.

Observer example:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerPartitionAssignedEvent;
import org.springframework.kafka.event.ConsumerPartitionLostEvent;
import org.springframework.kafka.event.ConsumerPartitionRevokedEvent;
import org.springframework.stereotype.Component;

@Component
public class PartitionEvents {

    @EventListener
    public void assigned(ConsumerPartitionAssignedEvent event) {
        log.info("ASSIGNED {}", event.getPartitions());
    }

    @EventListener
    public void revoked(ConsumerPartitionRevokedEvent event) {
        log.info("REVOKED {}", event.getPartitions());
    }

    @EventListener
    public void lost(ConsumerPartitionLostEvent event) {
        log.warn("LOST {}", event.getPartitions());
    }
}
~~~

These events serve observability. For applications that need to commit, seek, or operate directly on `KafkaConsumer` at rebalance time, use **ConsumerAwareRebalanceListener** in the proper lifecycle instead of performing these tasks indirectly from an observer.

## 6. Timeline when a consumer group starts up

A basic startup flow:

~~~text
Spring Boot startup
         |
         v
@KafkaListener container starts
         |
         v
KafkaConsumer subscribes to topic
         |
         v
KafkaConsumer.poll()
         |
         v
Join group / assignment protocol
         |
         v
Kafka assigns partitions
         |
         v
Rebalance callback
         |
         v
Spring Kafka publishes assignment event
         |
         v
Consumer begins polling assigned partitions
         |
         v
Listener processes records
~~~

The exact order between internal operations depends on the Kafka client version, group protocol, Spring Kafka container, and callbacks. However, by design, the assigned event indicates that the consumer/container has reached the stage of receiving partitions in its lifecycle.

### 6.1. Events can repeat

After startup, the same consumer can receive new assignment events when:

- Adding or removing a replica.
- The container stops and starts again.
- The consumer times out, crashes, or loses group membership.
- Partitions are added to the topic.
- The subscription or assignment strategy changes.
- A rebalance is triggered by a membership change.

Therefore, handling assignment events needs to be **idempotent**. Do not treat it as a callback that runs only once in the entire application lifecycle.

## 7. Eager rebalance and cooperative rebalance

Kafka has different partition assignment strategies. This difference affects the events the application sees.

### 7.1. Eager rebalance

In the eager approach, consumers in the group may revoke most or all of their current assignments and then receive new assignments.

~~~text
Before rebalance:
  A -> P0, P1
  B -> P2, P3

Rebalance:
  revoke old assignment
  compute new assignment

After rebalance:
  A -> P0, P2
  B -> P1, P3
~~~

The application may see many partitions revoked and assigned in a single cycle. This is why a wide rebalance can cause a temporary processing pause.

### 7.2. Cooperative/incremental rebalance

With cooperative assignment, Kafka can migrate partitions incrementally instead of forcing all consumers to give up all partitions immediately.

~~~text
Before:
  A -> P0, P1
  B -> P2, P3

Transition phase:
  A keeps P0, releases P1
  B keeps P2, P3

Next phase:
  A -> P0
  B -> P1, P2, P3
~~~

In the corresponding versions and protocols, an event may carry only the partitions revoked or newly assigned in a specific step, rather than the full assignment list.

**Do not infer the total partitions a consumer owns from a single standalone event.** If you need a complete ownership picture, aggregate state per consumer or use appropriate Kafka admin/metrics tools.

### 7.3. Things to note when switching assignors

Switching from eager to cooperative is not just changing a single config on one pod in all cases. You must follow the compatibility procedure for the assignment strategy and group protocol of the current Kafka version. An incompatible rollout can cause prolonged group rebalancing or instability.

## 8. Concurrency and per-consumer assignment

When `@KafkaListener` uses `concurrency > 1`, Spring Kafka creates a **ConcurrentMessageListenerContainer** managing multiple child **KafkaMessageListenerContainer** instances.

Example:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "order-fulfillment",
    concurrency = "3"
)
public void consume(OrderCreated event) {
    fulfillmentService.process(event);
}
~~~

Suppose the topic has six partitions and `concurrency=3`:

~~~text
Parent concurrent listener container
       |
       +-- child #0 -> consumer #0 -> P0, P1
       +-- child #1 -> consumer #1 -> P2, P3
       +-- child #2 -> consumer #2 -> P4, P5
~~~

Each child consumer has its own assignment and poll loop. Events are published from the lifecycle of the child containers, so the application may receive multiple assigned events close together rather than a single event for the parent.

**Concurrency does not allow one partition to be processed concurrently by multiple consumers in the same group.** It allows different partitions to be processed across multiple consumers.

### 8.1. Total number of consumers in a deployment

If running four pods, each with `concurrency=3`:

~~~text
4 pods x 3 consumers per pod = 12 consumers
~~~

If the topic only has 8 partitions and the group only subscribes to that topic, some consumers may not receive any partitions. Do not treat the presence of a child consumer without an assignment as evidence that the consumer is failing.

### 8.2. Client ID for correlation

Setting `clientIdPrefix` helps identify child consumers:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-fulfillment",
    concurrency = "3",
    clientIdPrefix = "orders-pod-a"
)
public void consume(OrderCreated event) {
    fulfillmentService.process(event);
}
~~~

Spring Kafka may append suffixes to the client IDs of child consumers, for example `orders-pod-a-0`, `orders-pod-a-1`, and `orders-pod-a-2`.

When investigating assignment events, correlate the client ID, group ID, listener/container ID, and partition assignment. Looking only at the topic/partition without identifying the associated consumer makes it hard to analyze a group with multiple replicas.

## 9. How do Event listener and ConsumerAwareRebalanceListener differ?

Both approaches are useful but serve different purposes.

| Criterion | Spring @EventListener | ConsumerAwareRebalanceListener |
|---|---|---|
| Receives assignment notification | Yes | Yes |
| Integration point | Spring application event system | Kafka consumer rebalance callback in the container |
| Suitable for logging/metrics | Very suitable | Suitable |
| Suitable for consumer.seek | Not preferred | Suitable when called on the right thread |
| Suitable for commit logic at revoke | Not preferred | Has callbacks before/after commit |
| Timing control relative to rebalance | Depends on event multicaster | Interacts directly in rebalance lifecycle |
| Should run heavy I/O | No | No |
| Synchronicity | Usually synchronous by default; can be changed | Runs in the consumer callback lifecycle |

**@EventListener** is suitable when you need to observe and update telemetry. **ConsumerAwareRebalanceListener** is suitable when you need to operate on `KafkaConsumer` during the assignment or revoke phase.

### 9.1. Why not use an event listener to commit manually?

`ApplicationEvent` may be published synchronously by default, but Spring allows configuring `ApplicationEventMulticaster` to run asynchronously. When running on another thread, `KafkaConsumer` is not thread-safe and performing commit/seek from an event listener is unsafe.

Even when the event listener is synchronous, the container already has mechanisms to manage commits/offsets. An arbitrary commit call can conflict with `AckMode`, transactions, or the error handler.

Therefore, let the container manage offsets. If special behavior is needed during rebalance, use the proper lifecycle callback and understand the commit implications.

## 10. ConsumerAwareRebalanceListener

Spring Kafka provides the **org.springframework.kafka.listener.ConsumerAwareRebalanceListener** interface to work with assignment/revoke alongside the `KafkaConsumer` owning the partitions.

Some commonly used hooks:

- **onPartitionsAssigned(Consumer, Collection<TopicPartition>)**
- **onPartitionsRevokedBeforeCommit(Consumer, Collection<TopicPartition>)**
- **onPartitionsRevokedAfterCommit(Consumer, Collection<TopicPartition>)**
- **onPartitionsLost(Consumer, Collection<TopicPartition>)**

Exact hooks and default behavior may vary by Spring Kafka version; check the JavaDoc when using them directly.

Example configuration in a factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        kafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties().setConsumerRebalanceListener(
        new ConsumerAwareRebalanceListener() {

            @Override
            public void onPartitionsAssigned(
                    Consumer<?, ?> consumer,
                    Collection<TopicPartition> partitions) {

                log.info("Assigned {}", partitions);
            }

            @Override
            public void onPartitionsRevokedBeforeCommit(
                    Consumer<?, ?> consumer,
                    Collection<TopicPartition> partitions) {

                log.info("Revoking before commit {}", partitions);
            }

            @Override
            public void onPartitionsRevokedAfterCommit(
                    Consumer<?, ?> consumer,
                    Collection<TopicPartition> partitions) {

                log.info("Revoked after commit {}", partitions);
            }

            @Override
            public void onPartitionsLost(
                    Consumer<?, ?> consumer,
                    Collection<TopicPartition> partitions) {

                log.warn("Partitions lost {}", partitions);
            }
        }
    );

    return factory;
}
~~~

The snippet focuses on the callbacks. The application needs to add imports, deserializers, error handler, and other configurations depending on the use case.

### 10.1. Why are there before commit and after commit?

Spring Kafka separates the revoke hooks to support certain tasks before/after the container processes pending commits according to its rules. This does not mean every revoke is guaranteed to commit successfully; group state, transactions, and broker errors still need to be handled properly.

You should not call **consumer.commitSync()** in every callback if the container already manages `AckMode` and transactions. Arbitrary commits can advance offsets past unprocessed records or conflict with transaction boundaries.

### 10.2. onPartitionsLost differs from onPartitionsRevoked

When partitions have been lost, the consumer may no longer have valid ownership to commit offsets for those partitions. Use the lost callback to clean up local state, stop processing authority, and record ownership loss.

Do not handle lost by trying to do a "final" commit like in a normal revoke. Offset commits must be managed according to container semantics and the validity of consumer group membership.

## 11. Seek when receiving new partitions

A use case may require resetting the read position when partitions are assigned. For example, a specialized application wants to start from an offset stored outside Kafka or replay from an approved point.

With `ConsumerAwareRebalanceListener`, you can perform seek on the consumer thread inside the assignment callback:

~~~java
@Override
public void onPartitionsAssigned(
        Consumer<?, ?> consumer,
        Collection<TopicPartition> partitions) {

    for (TopicPartition partition : partitions) {
        Long requiredOffset = recoveryStore.findOffset(partition);

        if (requiredOffset != null) {
            consumer.seek(partition, requiredOffset);
        }
    }
}
~~~

**Only use this kind of design if there is a clear reason**. In a normal consumer group, Kafka already stores committed offsets and `auto.offset.reset` decides where to start if no offset exists. Manually seeking on every assignment can:

- Re-read old records unexpectedly.
- Skip unprocessed records if the external offset is too high.
- Break retry/recovery policies.
- Cause Kafka group offset state and external checkpoints to diverge.
- Create duplicate side effects after a rebalance.

If you need to seek to bootstrap a replay flow, define a policy, test multi-partition scenarios, and document when the external offset can be trusted.

### 11.1. ConsumerSeekAware is another option

Spring Kafka also provides **ConsumerSeekAware** for cases where a listener needs to adjust the read position on assignment/idle events. This can be a more structured option for interacting with seek callbacks, depending on the listener type and version.

Do not use both `ConsumerSeekAware` and `ConsumerAwareRebalanceListener` to seek the same partition without precedence rules; callback order and offset state can become unpredictable.

## 12. Using events to refresh local state

Some applications maintain caches or state per partition:

~~~text
Partition P0:
  local cache for customer range A
  buffered aggregation state
  in-memory sequence tracker

Partition P1:
  local cache for customer range B
  buffered aggregation state
  in-memory sequence tracker
~~~

When assigned new partitions, the consumer may need to reload the appropriate state. When partitions are revoked or lost, it needs to release ownership and clean up local state.

However, state reconstruction can take a long time. Do not perform a minute-long DB scan directly inside a consumer rebalance callback; this can delay poll, heartbeat, and assignment.

One design approach:

1. Record the assigned partitions.
2. Create an **initializing** state for the partition.
3. Start state preparation logic in a controlled manner.
4. Do not process business records with unready state.
5. Only transition to **ready** once state is restored and ownership is still valid.
6. Upon revoke/lost, cancel old initialization work and clean up state by generation.

If using asynchronous initialization, you must handle races: a partition may be revoked before the restore task completes. Do not let an old task write into the state of a new consumer that has received the partition.

### 12.1. Where to store state?

If state is critical for reliability, do not keep it only in the heap. Consider:

- External database with version/ownership metadata.
- Compacted Kafka topic for a changelog suited to a dedicated design.
- Local persistent store with a recovery/rebuild strategy.
- Cache with TTL and idempotent rebuild.
- A specialized stream processing framework if the problem truly requires stateful stream semantics.

A partition assignment event only signals when ownership changes; it does not provide a built-in state store or transactional checkpointing.

## 13. Thread safety and event multicaster

Under common configurations, Spring application events are published synchronously via the default `ApplicationEventMulticaster`. Since the Kafka container publishes events in the consumer lifecycle, a heavy handler can prolong the execution path related to the consumer.

However, the application can customize the multicaster to run async. In that case, the event handler is no longer guaranteed to run on the consumer thread.

**Safety principles:**

- Do not call `KafkaConsumer` from arbitrary threads.
- Do not call `commitSync`/`seek`/`pause` directly from an async event handler.
- Do not run long blocking HTTP/DB calls inside `@EventListener`.
- Do not hold a `KafkaConsumer` reference for later use.
- Record concise metrics/logs without creating heavy work.
- If modifying ownership state, use thread-safe data structures.
- If operating on the consumer, use container hooks/mechanisms guaranteed to run on the right thread.

### 13.1. Event listener exceptions

If an `@EventListener` throws an exception when the event is published synchronously, the exception can affect the container's lifecycle path in undesirable ways. Therefore, observers should avoid letting telemetry/notification errors propagate as business errors.

Example:

~~~java
@EventListener
public void onAssigned(ConsumerPartitionAssignedEvent event) {
    try {
        partitionMetrics.recordAssignment(event.getPartitions());
    }
    catch (RuntimeException ex) {
        log.warn(
            "Cannot publish assignment telemetry, partitions={}",
            event.getPartitions(),
            ex
        );
    }
}
~~~

Do not catch every exception to hide a business-critical assignment/seek error if the hook is used as a mandatory part of correctness. Critical parts should have a retry/fail-fast policy and be implemented in an appropriate lifecycle callback.

## 14. Distinguishing assignment events from pause/resume events

Spring Kafka also has events for pausing/resuming consumers or partitions. These events differ from assignment.

| Event | Meaning |
|---|---|
| Partition assigned | Consumer is assigned permission to read the partition |
| Partition revoked | Partition is revoked from the consumer |
| Partition lost | Consumer loses partition ownership |
| Consumer paused | Consumer/container is pausing fetch/delivery via container API |
| Consumer resumed | Consumer/container resumes |
| Partition paused | A partition is paused |
| Partition resumed | A partition is resumed |

**Pause does not mean revoke.** When paused, the consumer usually still owns the partition and maintains group membership. When revoked, the partition can be assigned to another consumer.

Do not delete per-partition state just because of a pause event if the state needs to be kept for resume. Similarly, an assignment event does not mean the consumer is processing records immediately, because the listener may be paused or waiting for state restoration.

## 15. Group rebalance triggers

Changes that commonly cause assignments to change:

1. A new consumer joins the group.
2. A consumer leaves the group or its process crashes.
3. A consumer is considered inactive due to heartbeat/session timeout.
4. A consumer polls too slowly and violates `max.poll.interval.ms`.
5. The number of partitions in the topic increases.
6. The consumer subscription changes.
7. The assignment strategy or group protocol changes.
8. Pod rolling restart, autoscale, or deployment kill.
9. A consumer encounters an error causing the container to restart or membership to change.

Not every change in the above cases must produce a completely different new distribution. A rebalance may keep some partitions on the old consumer depending on the assignor.

### 15.1. Events may arrive more frequently than expected

When an application restarts continuously or scales too frequently, the number of assignment events can surge. This may be a symptom of system instability, not the root cause.

Compare event timestamps with:

- Pod restart/rollout.
- Health check failures.
- Consumer poll latency.
- JVM GC pauses.
- Broker coordinator logs.
- Group rebalance rate.
- Network partitions and session timeouts.
- Downstream DB/HTTP latency.

## 16. Impact on offset commit and at-least-once

When a consumer loses a partition, records that were processed but not yet committed can be redelivered to the next consumer. Example:

~~~text
Consumer A receives P0, offset 100..104
      |
      +-- processes 100..102 successfully
      |
      +-- has not committed offset 103
      |
      v
Rebalance -> P0 moves to Consumer B
      |
      v
Consumer B reads from old committed offset
      |
      v
100..102 may be redelivered
~~~

This behavior aligns with at-least-once. Assignment events do not create exactly-once for business side effects.

Therefore:

- Business side effects need idempotency.
- `AckMode` must match processing boundaries.
- The error handler needs to define retry/recovery.
- On normal revoke, the container can handle pending offsets according to policy.
- On partition lost, do not assume the old consumer still has commit permission.
- If using Kafka transactions, input offsets and Kafka outputs must be coordinated within the corresponding transaction.

### 16.1. Idempotency example

A consumer writes payment/fulfillment state to a database. If the same event is redelivered after a rebalance, a unique event ID can help prevent duplicates.

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Write `processed_event` and the side effect within the same DB transaction. Do not use only check-before-insert due to race conditions; the unique constraint must be enforced.

## 17. EOS and assignment events

In pure Kafka consume-transform-produce, a transactional listener container can commit Kafka outputs and input offsets in the same transaction. When a rebalance or exception aborts the transaction, uncommitted transactional outputs are not visible to `read_committed` consumers and input offsets are not committed in that transaction.

However, an assignment event is not a transaction event:

~~~text
Assignment event:
   "Consumer just received partition"

Kafka transaction:
   "Outputs and offsets in the transaction are committed/aborted"
~~~

Do not infer that a transaction has committed from an assignment event, and do not use an assignment event to start an arbitrary Kafka transaction in place of the container.

If a transactional listener needs to handle errors, check `AfterRollbackProcessor` and the rollback policy of your Spring Kafka version. When assignment changes due to a rebalance, replays at the listener method can occur even though committed Kafka outputs still follow EOS within the Kafka scope.

## 18. Group subscription and manual partition assignment

A Kafka consumer has two ways of managing partitions:

**Group subscription:** subscribes to a topic or pattern, and the coordinator/assignor automatically distributes partitions among consumers in the group.

**Explicit assignment:** assigns specific `TopicPartition`s via configuration, for example `@KafkaListener(topicPartitions=...)`, without relying on the same group rebalance process for automatic partition distribution.

Subscription example:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "fulfillment-workers"
)
public void consume(OrderCreated event) {
    process(event);
}
~~~

Manual assignment example:

~~~java
@KafkaListener(
    topicPartitions = @TopicPartition(
        topic = "orders.priority",
        partitions = {"0", "1"}
    )
)
public void consumePriority(OrderCreated event) {
    processPriority(event);
}
~~~

When using explicit assignment, do not expect all **group rebalance** callbacks to occur identically to a subscribe-based consumer. Events/lifecycle handling for assigned partitions may behave differently depending on the Spring Kafka version and container type.

If the application depends on events to rebuild state, you must test the exact mode actually used.

## 19. Multiple listeners and filtering by event source

A Spring Boot app can have multiple `@KafkaListener`s, such as orders, payments, and audit. An `@EventListener` receiving `ConsumerPartitionAssignedEvent` can observe events from multiple containers, not just one topic.

Example:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "fulfillment-workers"
)
public void consumeOrder(OrderCreated event) {
    processOrder(event);
}

@KafkaListener(
    id = "audit-listener",
    topics = "orders.audit",
    groupId = "audit-indexer"
)
public void consumeAudit(OrderAudit event) {
    indexAudit(event);
}
~~~

If only general logging is needed, a single observer is enough. If per-listener handling is needed, filter based on appropriate container/source information and topic/partition metadata in the event.

Do not rely on thread names with a format not guaranteed across versions. Declare explicit listener IDs and use version-supported source/container metadata APIs to map to the listener.

### 19.1. Avoid updating a shared map without synchronization

Multiple consumer containers can publish events from different threads. If an observer updates an ownership mapping:

~~~text
consumer-0 -> {orders.created-0, orders.created-1}
consumer-1 -> {orders.created-2, orders.created-3}
~~~

The map must be thread-safe or protected by synchronization. At the same time, handle revoke/lost so stale partition ownership is not retained.

A counter of "received assigned events" does not replace the current state mapping if the event only carries delta assignments.

## 20. Metrics and observability

Partition assignment events are a useful source of information to track group lifecycle. However, events are only part of observability; they need to be combined with Kafka consumer and broker metrics.

| Metric/signal | Meaning |
|---|---|
| Assignment event count | Frequency of consumers receiving partitions |
| Revoked event count | Frequency of partitions being revoked |
| Lost event count | Ownership loss cases needing attention |
| Assigned partition count | Number of partitions the consumer currently owns |
| Group rebalance rate | Whether the group is stable |
| Rebalance duration | Disruption duration due to rebalance |
| Consumer lag per partition | Which partition is lagging |
| Records consumed per client | Whether consumers receive balanced load |
| Listener processing time | Record/batch processing time |
| Commit latency/failures | Whether offsets advance according to policy |
| Pod restart / OOM / GC | Potential reasons a consumer leaves the group |
| Downstream latency | Slow DB/API causing poll interval to exceed limit |

Specific metrics depend on the Kafka client, Spring Kafka, Micrometer, exporter, and tracing configuration. Do not assume all metrics are available out of the box.

### 20.1. Structured logging

A useful assignment log:

~~~text
event=partition_assigned
listenerId=orders-listener
groupId=fulfillment-workers
clientId=orders-pod-a-1
partitions=orders.created-2,orders.created-3
timestamp=...
~~~

For revoke:

~~~text
event=partition_revoked
listenerId=orders-listener
groupId=fulfillment-workers
clientId=orders-pod-a-1
partitions=orders.created-3
timestamp=...
~~~

Do not include record key, order ID, event ID, or payload in assignment event logs: that data does not belong to partition ownership and introduces cardinality/privacy risks.

### 20.2. Metric cardinality

If creating metrics per partition and per consumer instance, the number of time series can grow significantly. Choose clearly scoped labels: service, environment, consumer group, and topic. Client ID/partition are useful for diagnostics but require considering retention/cardinality.

## 21. Rebalance loops and common incidents

| Symptom | Possible cause | Investigation |
|---|---|---|
| Assigned/revoked events appear continuously | Repeated group rebalance | Pod restart, heartbeat, max.poll.interval.ms |
| Assigned event has empty partition set | Consumer not yet assigned useful partitions or protocol callback | Compare concurrency with partition count |
| Consumer lag spikes right after scaling | Slow rebalance or state restore | Event timestamps, assignment, downstream |
| A consumer has no assignment | More consumers than partitions or distribution | Check group members and partition count |
| Partitions continuously change owner | Rollout, unstable consumer, or assignor | Check deployment and broker logs |
| Consumer B re-processes A's records | A processed but did not commit before revoke/crash | Idempotency, AckMode, commit logs |
| Local cache wrong after rebalance | Old state not cleared or restore incomplete | Revoke/lost cleanup and state generation |
| Event handler slows down consumer | I/O/blocking in @EventListener | Measure handler latency, decouple telemetry |
| Seek error when event handled async | KafkaConsumer called outside consumer thread | Use rebalance listener/ConsumerSeekAware |
| Lost event and commit failure | Ownership already lost | Do not manually commit, investigate group membership |

Do not immediately increase concurrency or timeouts when seeing lag. First determine whether the lag comes from rebalancing, hot partitions, downstream bottlenecks, commit failures, or open transactions.

## 22. Testing partition assignment events

An integration test can use Embedded Kafka or Testcontainers to run a broker with a multi-partition topic.

### 22.1. Test startup assignment

1. Create topic `orders.created` with four partitions.
2. Start the consumer group with listener `concurrency=2`.
3. Use `@EventListener` to collect `ConsumerPartitionAssignedEvent`.
4. Confirm assignment occurred for consumers in the group.
5. Compare total currently owned partitions against the topic and group membership.
6. Send records and confirm the listener actually consumes them.

Do not rely solely on the number of published events to conclude the partition count: there may be multiple events or events carrying only an assignment subset.

### 22.2. Test rebalance when adding a consumer

1. Start one consumer instance.
2. Wait for the group to stabilize and record the assignment.
3. Start a second instance with the same group ID.
4. Observe revoke/assign events.
5. Confirm partitions are redistributed according to the assignor.
6. Confirm no partition is processed concurrently by two consumers in the same group as two valid owners.
7. Send records to verify the group continues processing.

With a cooperative assignor, you may see partitions migrate in steps; do not hardcode an eager sequence for all versions.

### 22.3. Test consumer crash

1. Consumer A receives partitions and processes some records.
2. Kill process A before committing an offset to simulate failure.
3. Consumer B continues participating in the group.
4. Observe assignment/loss depending on the scenario.
5. Confirm uncommitted records can be redelivered.
6. Verify idempotency or deduplication at the business layer.

### 22.4. Test async event listener

If the application configures `ApplicationEventMulticaster` to run asynchronously, verify the observer does not touch `KafkaConsumer` directly. The test goal is to confirm event telemetry works without affecting consumer poll/lifecycle.

## 23. Practical example: Order Fulfillment scale-out

Suppose topic `orders.created` has eight partitions. Initially the application has two pods, each with `concurrency=2`. Total four consumers in the same group `fulfillment-workers`.

~~~text
Topic partitions: P0 P1 P2 P3 P4 P5 P6 P7

Pod A:
  Consumer A0 -> P0, P1
  Consumer A1 -> P2, P3

Pod B:
  Consumer B0 -> P4, P5
  Consumer B1 -> P6, P7
~~~

The application scales from two to three pods during high order volume. Two new consumers are created. Kafka will rebalance the group; some partitions transfer ownership.

The affected consumers may publish:

~~~text
ConsumerPartitionRevokedEvent
ConsumerPartitionAssignedEvent
~~~

If a pod fails abnormally, a partition lost scenario may occur according to client/container semantics.

At the business layer:

- Per-partition caches for old partitions must be cleaned up.
- New consumers receiving partitions need to restore local state if applicable.
- Records processed but not yet committed may be redelivered.
- Side effects creating fulfillment must be idempotent by event ID.
- Dashboards need to reflect consumer-to-partition ownership after rebalance.
- Do not run long blocking state restores directly in the event handler.

After the group stabilizes, the operations team should check consumer lag per partition and throughput. If a partition has a hot key, increasing the number of consumers will not allow that partition to be processed by multiple consumers in the same group.

## 24. Implementation checklist

- [ ] Distinguish Kafka group assignment from Spring application events.
- [ ] Know Assigned, Revoked, and Lost events.
- [ ] Do not assume the event only runs once.
- [ ] `@EventListener` only performs observability/lightweight logic when appropriate.
- [ ] If seek is needed, use a callback on the proper consumer thread.
- [ ] If commit logic on revoke is needed, understand `AckMode` and before/after commit lifecycle.
- [ ] Do not try to commit as if still owning a lost partition.
- [ ] Handle event state per consumer, do not conflate multiple child containers.
- [ ] Account for cooperative rebalancing with delta assignments.
- [ ] Clean up local state on revoke/lost and guard against stale restores.
- [ ] Use idempotency for record redelivery after rebalance.
- [ ] Monitor rebalance, lag, commits, restarts, and poll intervals.
- [ ] Test startup, scale-out, crash, and assignment changes.
- [ ] Have runbooks for rebalance loops and hot partitions.
- [ ] Do not use assignment events in place of transactions or distributed locks.

## 25. Production investigation runbook

1. Identify the consumer group, topic, and partition count.
2. Identify the affected listener ID, client ID, and pod/instance.
3. Read timestamps of assigned/revoked/lost events.
4. Check pod rollouts, restarts, OOMs, and readiness/liveness failures.
5. Check current consumer group membership and partition assignment.
6. Check `max.poll.interval.ms`, session timeout, heartbeat, and poll duration.
7. Check consumer lag per partition and processing latency.
8. Check whether downstream DB/API is blocking the listener for too long.
9. Correlate assignor/protocol and partition count changes.
10. If local state exists, verify cleanup/rebuild and generation.
11. If duplicates are seen, check committed offsets, `AckMode`, replay, and idempotency.
12. If Kafka transactional, check abort/recovery and input offset commits.
13. Check whether observers are blocking the consumer or calling `KafkaConsumer` on the wrong thread.
14. After remediation, confirm the group stabilizes and partitions continue processing.
15. Document the root cause and configuration/runbook changes for next time.

## 26. Common misconceptions

**"A partition assignment event is a record in a Kafka topic."** False. It is a Spring application event published by the listener container.

**"Receiving AssignedEvent means the partition will belong to that consumer forever."** False. Rebalances can revoke or transfer ownership.

**"AssignedEvent always contains every partition of the entire group."** False. The event reflects container-related assignment and may be a subset/incremental depending on context.

**"Seeing many assignment events means Kafka is processing duplicate data."** Insufficient conclusion. Check offsets, group state, and side effects.

**"You can seek/commit directly from any @EventListener."** False. `KafkaConsumer` is not thread-safe; if the event listener runs asynchronously, this is very dangerous.

**"Revoked and Lost are the same."** False. Lost may mean the consumer no longer has valid ownership to commit.

**"Pause is revoke."** False. Pause usually retains assignment while temporarily pausing reading/delivery.

**"Increasing concurrency always eliminates lag."** False. Useful concurrency is limited by partition count and downstream capacity.

**"Assignment events manage local state automatically."** False. The application must design restore, cleanup, and idempotency.

**"Assignment changes do not affect already processed records."** False. Uncommitted records may be redelivered.

**"Filtering events by thread name is a stable API."** Not recommended. Use official listener/container metadata.

## 27. Takeaways

A **partition assignment event** in Spring Kafka is a lifecycle signal indicating that partitions have been assigned to a consumer container. The event is commonly observed via **ConsumerPartitionAssignedEvent**, along with `ConsumerPartitionRevokedEvent` and `ConsumerPartitionLostEvent` when ownership changes.

For logging, monitoring, and lightweight state updates, **@EventListener** is a convenient approach. For consumer operations that must run synchronously during rebalance such as seek or controlled revoke handling, prefer **ConsumerAwareRebalanceListener** or appropriate lifecycle APIs, avoiding accessing `KafkaConsumer` from other threads.

In resilient systems, partition ownership can always change due to scaling, restarts, or rebalances. Combine assignment events with proper offset commit policies, local state cleanup, idempotent side effects, consumer lag monitoring, and integration tests so that the consumer group recovers safely without dropping data or producing incorrect business outcomes.
