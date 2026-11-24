# onPartitionsLost

In Spring Kafka, a consumer belonging to a consumer group may only process the partitions currently assigned to it. Assignment is not fixed: Kafka can redistribute partitions when consumers join or leave the group, when the partition count changes, or when a consumer no longer meets the conditions to maintain membership.

**onPartitionsLost** is the callback notifying that the consumer **has lost ownership** of a set of partitions, typically in a situation where there was no longer an opportunity to perform a normal revocation process before the assignment moved to another consumer. This is an important signal in the **rebalancing and lifecycle** mechanism, because after this point the application must not continue acting as if it is still a valid owner of those partitions.

This lesson analyzes the difference between onPartitionsLost and onPartitionsRevoked, how to register callbacks in Spring Kafka, how to stop or invalidate asynchronous work, impacts on offsets and transactions, and cases to test when operating consumer groups.

## 1. Context: partition ownership in a consumer group

Suppose topic orders.events has six partitions and consumer group order-processors has three consumers:

    orders.events:
       P0  P1  P2  P3  P4  P5

    Consumer A: P0, P1
    Consumer B: P2, P3
    Consumer C: P4, P5

Within the same consumer group, a partition is assigned to at most one consumer at a time per the group coordinator's decision. Assignment determines which consumer is responsible for polling and processing records from that partition.

When consumer B loses connectivity for too long, the group coordinator may remove it from the group. Partitions P2 and P3 are assigned to remaining active members. If B recovers connectivity later and rejoins the group, it may learn that it has lost ownership of P2/P3.

    Before incident: Consumer B owns P2, P3
                    |
                    v
          B is no longer a valid group member
                    |
                    v
        Coordinator assigns P2, P3 to another consumer
                    |
                    v
       B resumes activity / polls / rejoins
                    |
                    v
              onPartitionsLost(P2, P3)

What the application needs to react with is not "try to finish committing", but **stop all activities requiring ownership of P2/P3**, clean up local state, and let the new consumer take over.

## 2. Why is there a separate callback for lost?

Kafka has three milestones commonly presented through ConsumerRebalanceListener:

- **onPartitionsAssigned:** the consumer is assigned new partitions; prepare state and begin processing.
- **onPartitionsRevoked:** the consumer is notified of partition revocation in a controlled rebalance; it may still have a chance to finish valid operations per the contract.
- **onPartitionsLost:** partitions were lost without the consumer retaining ownership; it must not assume it can still commit offsets or mutate state as the owner.

Comparison:

| Callback | Meaning | Commit offsets in callback? | Priority action |
|---|---|---|---|
| onPartitionsAssigned | Receives partition ownership | Not the main commit point | Initialize state, lease, cache |
| onPartitionsRevoked | About to yield ownership in a controlled rebalance | Can be considered per contract and commit mode | Safely finish/flush work, stop processing |
| onPartitionsLost | Ownership is already lost | **Should not try to commit as the old owner** | Invalidate old work, release state |
 
In cooperative rebalancing, revoke usually occurs only for partitions that genuinely need to move rather than the entire assignment. In cases of member loss or slow processing, the lost callback remains important because normal handoff may not take place.

Not every rebalance invokes onPartitionsLost. It is not a callback "after every onPartitionsRevoked".

## 3. Most important semantics: no more ownership

After onPartitionsLost, partitions may already be assigned to another consumer. If the old consumer continues committing offsets, updating checkpoints, or writing data as if it were still the owner, the following can happen:

1. The new consumer starts reprocessing records from the committed offset.
2. The old consumer still has background tasks running unfinished.
3. Both execute side effects for the same event.
4. Checkpoints or state from the old consumer overwrite new progress.

Example:

    P2 offset 900: OrderUpdated(evt-900)
                |
                +--> Consumer B called DB, not finished yet
                |
          B loses ownership of P2
                |
                +--> Consumer D is assigned P2
                            |
                            +--> D processes evt-900
                |
                +--> B's old task returns and updates DB

The lost callback helps the old consumer **know to stop or invalidate tasks**, but the callback itself cannot undo operations already sent to external systems outside Kafka. Therefore, preventing duplicate processing and state overwrites requires **idempotency, fencing, or optimistic concurrency** at the data store.

## 4. Kafka client API: ConsumerRebalanceListener

The Kafka Java client provides the interface org.apache.kafka.clients.consumer.ConsumerRebalanceListener. The basic callbacks use Collection<TopicPartition>:

~~~java
public class OrderRebalanceListener implements ConsumerRebalanceListener {

    @Override
    public void onPartitionsAssigned(
            Collection<TopicPartition> partitions) {
        log.info("Assigned partitions: {}", partitions);
    }

    @Override
    public void onPartitionsRevoked(
            Collection<TopicPartition> partitions) {
        log.info("Revoked partitions: {}", partitions);
    }

    @Override
    public void onPartitionsLost(
            Collection<TopicPartition> partitions) {
        log.warn("Lost partitions: {}", partitions);
    }
}
~~~

Key imports:

~~~java
import java.util.Collection;
import org.apache.kafka.clients.consumer.ConsumerRebalanceListener;
import org.apache.kafka.common.TopicPartition;
~~~

onPartitionsLost is a method supported in Kafka client versions with the lost callback mechanism. In some versions, the default implementation of the lost callback may delegate to revoked logic if the application does not override it. **If the revoked handler contains offset commit logic, explicitly override lost to avoid reusing commit logic when ownership is already lost.**

Kafka consumer callbacks run within the consumer's poll/rebalance context, not an arbitrary background worker created by the application. Callbacks should be short, thread-safe, and not block the poll thread for an extended period.

## 5. Spring Kafka API: ConsumerAwareRebalanceListener

Spring Kafka provides ConsumerAwareRebalanceListener so callbacks can also receive the Kafka Consumer object. In a Spring Kafka listener container, this is the commonly used extension point to track assignment lifecycle per consumer.

Common methods:

- onPartitionsAssigned(Consumer<?, ?> consumer, Collection<TopicPartition> partitions)
- onPartitionsRevokedBeforeCommit(Consumer<?, ?> consumer, Collection<TopicPartition> partitions)
- onPartitionsRevokedAfterCommit(Consumer<?, ?> consumer, Collection<TopicPartition> partitions)
- onPartitionsLost(Consumer<?, ?> consumer, Collection<TopicPartition> partitions)

Spring Kafka provides callbacks before/after the container's commit logic to let the application coordinate operations at the appropriate moment. Do not rely on guessing the order of these callbacks under different AckMode or transaction configurations; read the contract for your version in use.

A configuration pattern:

~~~java
@Configuration
public class OrderKafkaListenerConfig {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            PartitionLifecycleService lifecycleService) {

        ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
                new ConcurrentKafkaListenerContainerFactory<>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        factory.getContainerProperties()
                .setConsumerRebalanceListener(
                    new ConsumerAwareRebalanceListener() {

                        @Override
                        public void onPartitionsAssigned(
                                Consumer<?, ?> consumer,
                                Collection<TopicPartition> partitions) {

                            lifecycleService.onAssigned(partitions);
                        }

                        @Override
                        public void onPartitionsRevokedBeforeCommit(
                                Consumer<?, ?> consumer,
                                Collection<TopicPartition> partitions) {

                            lifecycleService.onRevoking(partitions);
                        }

                        @Override
                        public void onPartitionsLost(
                                Consumer<?, ?> consumer,
                                Collection<TopicPartition> partitions) {

                            lifecycleService.onLost(partitions);
                        }
                    }
                );

        return factory;
    }
}
~~~

Listener referencing the factory:

~~~java
@KafkaListener(
    id = "orders",
    topics = "orders.events",
    groupId = "order-processors",
    containerFactory = "ordersListenerFactory"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

OrderEvent and PartitionLifecycleService are application types/beans that must be defined. The example focuses on how to wire callbacks into the container, not a standalone runnable project.

Because one factory can create multiple child containers when concurrency is greater than 1, callbacks and lifecycleService must withstand being called from multiple consumer threads. Do not use a shared mutable variable to store the "current partition" without tying it to a specific owner.

## 6. Basic configuration in Spring Boot

Example consumer group with three consumer threads per instance:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: order-processors
      enable-auto-commit: false
      properties:
        max.poll.interval.ms: 300000
    listener:
      concurrency: 3
      ack-mode: record
~~~

Things to understand:

- concurrency=3 creates three consumers in one application instance when using the appropriate factory.
- If there are two instances with concurrency=3, the group can have six consumers.
- max.poll.interval.ms governs the time between polls; an overly slow listener can prevent the consumer from maintaining valid membership.
- enable-auto-commit=false lets the container manage commits per AckMode.
- AckMode.RECORD is a way to commit per listener record; it does not turn onPartitionsLost into a time when you can commit arbitrarily.

Spring Boot configuration does not auto-register custom callbacks. To use ConsumerAwareRebalanceListener, attach it to the ContainerProperties of the corresponding factory or listener container.

## 7. When is onPartitionsLost called?

Several situations can lead to lost ownership:

**Consumer fails to poll in time:** the listener takes too long, or blocks on HTTP/database, causing it to exceed max.poll.interval.ms. The group may proceed to reassign partitions.

**Connectivity and membership are interrupted:** a consumer loses contact long enough for the coordinator to consider it no longer a valid member. When it recovers and enters the poll/rebalance flow, the lost callback may be invoked.

**Rebalance without normal handoff revocation:** membership or coordinator state changes such that the consumer discovers partitions no longer belong to it.

**Application misuses async workers:** the listener quickly dispatches work to an executor and keeps polling. The consumer still polls, but old tasks can outlive a rebalance and become stale owner work.

Distinguish **the cause of losing ownership** from **the condition for the callback to execute**. If the JVM crashes or the pod is killed immediately, no thread survives to execute onPartitionsLost. If the consumer hangs forever without polling again, the callback may not run in time either. Therefore, never rely solely on the callback to release distributed locks or leases.

## 8. onPartitionsRevoked and onPartitionsLost are not interchangeable

In a normal revoke, the consumer knows in advance it is about to yield partitions. The application can stop accepting new work, finish necessary tasks, and coordinate commits/checkpoints per contract.

In lost, Kafka already considers the consumer no longer the owner. An old task may still be running, and a new consumer may already have started.

    Controlled revoke:
      Owner A -> Revoked callback -> Safely stop/commit -> Owner B

    Lost:
      Owner A evicted from group
           -> Owner B may already have received the partition
           -> Owner A learns later via lost callback

Therefore:

- In revoked, you can design a short graceful drain step and commit offsets if still appropriate.
- In lost, **do not commit offsets**, and do not assert old tasks completed on behalf of the group.
- In both, prevent old tasks from continuing to write side effects when no longer valid.
- In lost, releasing local resources and emitting alert/metric signals may be more important than trying to salvage checkpoints.

If storing a cache used only for owned partitions, ensure the cache is cleared on lost. However, if the cache is shared with a new consumer in the same JVM, deletion must be keyed by the right owner token so it does not accidentally delete state belonging to the new assignment.

## 9. What not to do in onPartitionsLost

Dangerous actions:

~~~java
@Override
public void onPartitionsLost(
        Consumer<?, ?> consumer,
        Collection<TopicPartition> partitions) {

    // DO NOT DO THIS: trying to commit offsets after ownership is lost.
    consumer.commitSync();

    // DO NOT DO THIS: assuming seek restores partition ownership.
    for (TopicPartition tp : partitions) {
        consumer.seek(tp, 0L);
    }
}
~~~

The snippet above is an **anti-example**, not a recommended configuration. Commits may fail because group generation/ownership is no longer valid; an untimely commit also risks recording inaccurate progress. Seek does not re-grant partition ownership.

Other actions to avoid:

- Calling acknowledge() for old records merely because the callback fired.
- Writing external checkpoints marked "completed" when tasks have not finished.
- Waiting indefinitely for an executor to drain inside the callback.
- Holding long locks, making blocking network API calls, or running large database transactions in the callback.
- Swallowing exceptions from task-stopping logic and treating revocation as successful.
- Deleting all state by partition name without knowing whether the state belongs to the old owner or a new assignment.

The callback's goal is to **invalidate old working authority and clean up quickly**. Recovery must be performed by the appropriate mechanism, not a "last-ditch commit" once ownership is lost.

## 10. Safe callback example: recording metrics and signaling lost

A simple strategy is forwarding lost events to a lifecycle management service:

~~~java
public final class PartitionLifecycleService {

    private static final Logger log =
            LoggerFactory.getLogger(PartitionLifecycleService.class);

    private final LongAdder lostCount = new LongAdder();

    public void onAssigned(Collection<TopicPartition> partitions) {
        log.info("Assigned: {}", partitions);
    }

    public void onRevoking(Collection<TopicPartition> partitions) {
        log.info("Revoking: {}", partitions);
    }

    public void onLost(Collection<TopicPartition> partitions) {
        lostCount.add(partitions.size());

        for (TopicPartition partition : partitions) {
            log.warn(
                "Consumer lost ownership topic={} partition={}",
                partition.topic(),
                partition.partition()
            );
        }

        // Cancellation/invalidation signals for old work must be non-blocking.
        // If there are multiple child consumers, match the specific owner token.
    }

    public long lostPartitionsTotal() {
        return lostCount.sum();
    }
}
~~~

Related imports:

~~~java
import java.util.Collection;
import java.util.concurrent.atomic.LongAdder;
import org.apache.kafka.common.TopicPartition;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
~~~

This example only logs and counts events; it does not complete a fencing mechanism. In a system with synchronous-only listener processing and no external owned state, this may be sufficient observation. For asynchronous processing or critical partition-local state, you must add ownership tracking and controlled work cancellation.

Metrics should distinguish lost from revoked. A normal scaling event can generate revoked multiple times; a sudden spike in lost may indicate stalled consumers, overly slow polls, or unstable membership.

## 11. Protecting async work with an ownership token

A listener might hand off records to an ExecutorService for asynchronous processing:

~~~java
@KafkaListener(topics = "orders.events")
public void consume(ConsumerRecord<String, OrderEvent> record) {
    executor.submit(() -> process(record));
}
~~~

This pattern is **unsafe if the container considers the record processed as soon as the listener returns**. Beyond losing ownership, offsets can be committed before process() completes.

If async is truly necessary, the architecture must manage:

1. An assignment token for each partition assignment.
2. Whether the token is still valid or has been lost/revoked.
3. When the task completes and side effects are committed.
4. Acknowledgments tied to actual completion, not to submit().
5. A fencing mechanism in the database or dependency so old tasks cannot overwrite new tasks.

Conceptual token check example:

~~~java
public record PartitionClaim(
        TopicPartition partition,
        long epoch,
        AtomicBoolean valid) {

    public void invalidate() {
        valid.set(false);
    }

    public void assertValid() {
        if (!valid.get()) {
            throw new CancellationException(
                "Partition ownership has been lost"
            );
        }
    }
}
~~~

On onPartitionsAssigned, the system creates a new claim; on onPartitionsLost, it invalidates the claim **belonging to that old consumer**; when a task is about to write data, it checks the claim.

However, merely checking an AtomicBoolean before writing to the DB **is not enough for atomic fencing**: state can change after the check but before the DB commit. If absolute protection against stale owners is needed, the database must enforce the fencing token/epoch in a conditional statement or unique constraint.

Example fenced state check and write:

~~~sql
UPDATE partition_projection
SET processed_offset = :new_offset,
    state_json = :new_state
WHERE topic = :topic
  AND partition_id = :partition
  AND owner_epoch = :current_epoch
  AND processed_offset < :new_offset;
~~~

Here owner_epoch must be guaranteed to increase or change monotonically by a coordinator/lease store. An in-memory counter inside a pod's RAM is not by itself a global fencing token across instances. Additionally, processed_offset is only suitable when state is designed to be monotonic by offset and the DB transaction controls the write condition.

## 12. Do not accidentally delete state of a new assignment

When concurrency is greater than 1, callbacks can run across multiple child consumers. It is also possible for a partition to be revoked from consumer A and then assigned to consumer B in the same application instance.

Incorrect pattern:

~~~java
// Map shared across all child consumers.
Map<TopicPartition, PartitionState> states = new ConcurrentHashMap<>();

void onLost(Collection<TopicPartition> lost) {
    // May delete new state if B already registered state for the same partition.
    lost.forEach(states::remove);
}
~~~

If the old owner's callback runs after the new owner has added state under the same key, a plain remove by partition can wipe out B's valid state.

A design with owner identity:

~~~java
record PartitionState(String ownerId, long epoch) {}

void removeOldOwner(
        TopicPartition partition,
        String oldOwnerId,
        ConcurrentMap<TopicPartition, PartitionState> states) {

    states.computeIfPresent(partition, (tp, current) ->
        current.ownerId().equals(oldOwnerId) ? null : current
    );
}
~~~

The snippet assumes ownerId is a unique ID for **one assignment/consumer owner**, managed by the application. When used in production, supply the right ownerId to the callback and use the same ID in the state created at assignment time.

Core idea: the lost callback is emitted for the old owner, so it may only clean up resources of the old owner. For distributed leases, releasing must also be conditional on the lease token; never release a lock by partition key without verifying the token.

## 13. Offset commit when partitions are lost

Offset committing is an operation sensitive to ownership and group generation. A consumer that no longer holds a valid assignment cannot continue treating its offsets as the group's official progress.

In a controlled onPartitionsRevoked, the application may finish/commit processed offsets per policy; the Spring Kafka container also has mechanisms to commit pending offsets at defined points.

In onPartitionsLost:

- **Do not perform consumer.commitSync()/commitAsync() as a cleanup step.**
- Do not mark offsets that have not been successfully processed as completed.
- Do not manually seek/assign partitions to reclaim ownership.
- Do not perform late acknowledgments for records belonging to a lost assignment as if it were still valid.
- Accept the possibility that some records must be redelivered from the previous committed offset.

Example:

    Committed offset = 400
    A polls offsets 400..409
    A processes 400, 401 but has not committed
    A loses ownership
    B receives partition starting at offset 400

B may reprocess records 400, 401. This matches at-least-once delivery when A's commit had not completed. The application needs idempotency by eventId to avoid duplicate side effects.

To reduce replay, optimize commit timing in the active mode and graceful revocation; **do not use onPartitionsLost to make up for missed commits after ownership is lost**.

## 14. onPartitionsLost with AckMode.MANUAL and MANUAL_IMMEDIATE

With Spring Kafka manual acknowledgment, the application receives an Acknowledgment to confirm a record after completing side effects:

~~~java
@KafkaListener(
    topics = "orders.events",
    groupId = "order-processors"
)
public void consume(
        ConsumerRecord<String, OrderEvent> record,
        Acknowledgment ack) {

    orderService.processIdempotently(record.value());
    ack.acknowledge();
}
~~~

The method above illustrates synchronous processing before acknowledgment. For async listeners, acks may occur after assignment changes depending on the container and async acks policy; separate control is needed.

Points to remember:

- MANUAL and MANUAL_IMMEDIATE differ in when the container performs commits.
- An acknowledgment from an old task after lost must not be treated as a valid mechanism to finalize the old owner's offsets.
- onPartitionsLost is not the place to call ack for leftover records.
- If the container uses Kafka transactions, transactional offsets and outputs have their own semantics; the lost callback still cannot re-grant ownership.
- Manual ack does not by itself make business side effects exactly-once.

The example using a method with Acknowledgment must have a matching container AckMode; if the factory uses RECORD while the listener requests manual acknowledgment, adjust the configuration accordingly.

## 15. Kafka transactions, producer fencing, and lost partitions

When a listener container manages Kafka transactions for consume-process-produce, Kafka outputs and source offsets can be committed in the same transaction.

If a consumer loses assignment during processing, risks that may appear include:

- The running transaction is no longer valid for the current group generation.
- Offsets sent into the transaction may be rejected due to metadata/fencing.
- The container needs to abort or handle transaction failures.
- Input records may be re-read by the new owner.
- Non-Kafka side effect tasks from the old owner may still be running.

Kafka transactions and EOS v2 help protect consistency within Kafka's scope, but do not turn the lost callback into a place to continue publishing/committing on behalf of the new owner.

In onPartitionsLost, avoid creating a "corrective transaction" to commit offsets of lost partitions. If DLT/recovery exists, it must follow the valid lifecycle and ownership of the container/recoverer.

For database or HTTP calls that ran before Kafka rollback, continue using idempotency keys, outboxes/inboxes, or fencing tokens. Aborting a Kafka transaction does not automatically reverse side effects outside Kafka.

## 16. How do pause, stop, and rebalance differ from lost?

A paused partition does not mean the consumer lost ownership of it. Pausing typically only suspends fetching more records, while the assignment remains with the consumer.

A stopped listener container can leave the group via graceful shutdown. Under normal circumstances, revoked callbacks or corresponding cleanup steps can occur before the assignment is handed over.

Comparison:

| Event | Does partition still belong to consumer? | Should processing continue? |
|---|---|---|
| pause() | Logically still belongs to consumer | Depends on pause policy, current tasks |
| resume() | Consumer still holds valid assignment | Can resume polling |
| onPartitionsRevoked | Yielding ownership | Finish/flush per contract |
| onPartitionsLost | **Lost ownership** | Stop/invalidate old tasks immediately |
| Container stop | Stopping consumer lifecycle | Drain/clean up per shutdown policy |
| JVM crash | No callback guaranteed to run | Other systems must recover via lease/replay |

Do not use a paused variable to infer a partition was lost. Conversely, do not use the lost callback to decide to pause; lost is an event after ownership is gone.

## 17. onPartitionsLost and cooperative rebalance

Kafka has different assignment strategies, among which cooperative rebalancing aims to reduce bulk partition revocation when a group changes.

In eager rebalancing, consumers often revoke large assignments before reassigning. In cooperative rebalancing, consumers can keep partitions that do not need to move and only revoke the portion that must change.

This reduces disruption, but does not eliminate all lost scenarios:

- Consumers can still lose membership by failing to poll in time.
- Network partitions can still cause timeouts.
- Coordinator/member generations can still change unexpectedly.
- A consumer that once owned partitions can realize ownership was lost.

Do not build logic assuming cooperative assignment guarantees onPartitionsLost will never happen. Likewise, do not assume every rebalance in cooperative mode invokes onPartitionsRevoked with all partitions.

Operations teams should verify the actual assignment strategy used by Kafka clients and the callback interfaces supported in the running library version.

## 18. Does static membership eliminate lost?

Kafka supports static membership via group.instance.id to reduce unnecessary rebalances during brief instance restarts or temporary disconnections. However, static membership does not make ownership permanent.

If an instance stops heartbeating long enough, the broker can still redistribute partitions. In some paths exceeding max.poll.interval.ms, a static member may stop heartbeating and get reassigned upon session timeout; details depend on the Kafka client/version and timeout configs.

Therefore:

- Static membership can make assignments more stable in some situations.
- It does not replace graceful shutdown and reasonable timeouts.
- It does not replace idempotency/fencing mechanisms.
- It does not guarantee onPartitionsLost will always be invoked before partitions change owners.

Do not reuse the same group.instance.id across two running instances; that causes fencing/membership conflicts.

## 19. Long-running listeners and max.poll.interval.ms

Suppose a listener receives a record and calls an API with a 10-minute timeout, while max.poll.interval.ms is 5 minutes. The consumer may be considered not polling frequently enough, leading to a group membership change.

    poll() receives record
           |
           v
    listener calls 10-minute API
           |
           +---- max.poll.interval.ms exceeded
           |
           +---- coordinator may transfer assignment
           |
           v
    listener returns and consumer continues polling
           |
           v
    Kafka client detects ownership has changed

Even if onPartitionsLost appears, it cannot stop an API call that already finished. If the API executed side effects before the consumer realized it lost ownership, the new consumer may process the same record.

Reduce risk by:

1. Setting timeouts for dependencies.
2. Reducing max.poll.records to bound processing time per poll.
3. Measuring processing duration p95/p99.
4. Considering increasing max.poll.interval.ms with justification, not just to hide bugs.
5. Avoiding unbounded blocking on DB/network.
6. Designing idempotent side effects.
7. If offloading async, managing completion and partition ownership properly.

Setting max.poll.interval.ms too high can slow recovery when a consumer genuinely hangs. Balance failure detection speed against realistic processing duration.

## 20. Cleanup mistakes in callbacks

### 20.1. Blocking the poll thread for too long

~~~java
@Override
public void onPartitionsLost(
        Consumer<?, ?> consumer,
        Collection<TopicPartition> partitions) {

    executor.awaitTermination(10, TimeUnit.MINUTES);
}
~~~

This is an **anti-example**: a callback waiting a long time makes it hard for the consumer to complete rebalancing and rejoin the group. Emit cancellation/invalidation signals quickly, then organize bounded cleanup elsewhere if truly needed.

### 20.2. Unconditionally releasing distributed locks

If a lock has expired and a new consumer acquired a lock on the same key, the old owner calling release(key) can accidentally delete the new consumer's authority. The solution is releasing by token or compare-and-delete.

### 20.3. Using simple ThreadLocal for all state

ThreadLocal is bound to a thread, which is insufficient to represent assignment lifecycles when consumer callbacks and async tasks run on different threads. State should be bound to (consumer owner, topic, partition, assignment token), not just thread ID.

### 20.4. Committing offsets inside the lost callback

Even though commitSync sometimes throws obvious exceptions, you should not wrap it in try/catch to ignore it and proceed as if completed. That is a broken ownership design and can mask replays/duplicates.

### 20.5. Cleaning up state only in onPartitionsRevoked

If only revoked logic exists, losing ownership without normal revocation can leave stale state around. Explicitly override lost and provide a dedicated invalidation path.

### 20.6. Using the callback as a place to reprocess records

onPartitionsLost has no contract for re-running records. Do not manually invoke the listener, send to DLT, or seek partitions in the callback; recovery belongs to valid consumers and container error/recovery infrastructure.

## 21. Designing PartitionLifecycleService for production

A service tracking assignments typically has these components:

    Kafka callback
         |
         v
    PartitionLifecycleService
         |
         +--- map owner token by topic-partition
         |
         +--- cancel/invalidate local processing
         |
         +--- release owner-scoped resources
         |
         +--- metric: assigned / revoked / lost
         |
         +--- structured log: groupId, clientId, partitions
         |
         v
    New consumer processes from committed offset

Rules:

- Each assignment generates a distinct token.
- The token is passed with tasks to check ownership.
- Cleanup must accept the old token, not just the partition name.
- If tasks write to an external store, the store must support sufficiently strong idempotency or fencing.
- Do not treat the lost callback as the sole condition for expiring tokens; require timeout/lease TTL or liveness detection for dead owners.
- Bound the time and queue size of cleanup.
- If synchronous cleanup cannot be done safely, idempotent cleanup tasks can be pushed to an internal queue, provided the queue does not hold exclusive partition authority indefinitely.
- The callback may receive an empty partition collection in some rebalance sequences; the code must tolerate empty sets.

The lost event is a **local signal**, not a consensus message sent to all other consumers. Cross-instance constraints must be protected at the coordination system or where side effects are written.

## 22. Observing lost partitions with metrics

Do not track only the total rebalance count. A group can rebalance due to periodic rollouts without issues, or suffer frequent lost ownership due to stalled listeners.

Suggested metrics:

| Metric | Meaning | Interpretation |
|---|---|---|
| partitions_lost_total | Number of partitions in lost callbacks | Continuous increase signals investigation needed |
| partitions_revoked_total | Number of normally revoked partitions | May increase during scaling/rollouts |
| partitions_assigned_total | Number of assigned partitions | Helps observe ownership churn |
| rebalance_duration | Time for group to change assignments | High values can affect throughput |
| records_processed_duplicate_total | Duplicates detected via eventId | Measures actual impact of redelivery |
| consumer_lag | Backlog by group/topic/partition | May grow during frequent rebalances |
| listener_processing_duration | Processing time p95/p99 | Compare against max.poll.interval.ms |
| commit_failure_total | Offset commit errors | May relate to generation/ownership |
| in_flight_tasks | Tasks still running when partitions are lost | Detects unfenced async work |

If using Micrometer, avoid attaching eventId, offset, or UUID as labels because they cause high cardinality. You can attach consumer group, topic, clientId, and normalized reason category.

Example log:

    level=WARN
    event=consumer_partition_lost
    group=order-processors
    client=orders-2
    partitions=orders.events-2,orders.events-3
    inflight=4

Actual reason information may not be directly provided by the callback. Do not arbitrarily label cause=timeout if you only know a lost event occurred; cross-check Kafka client logs, network, and processing duration.

## 23. Investigation procedure when onPartitionsLost increases

When the lost metric spikes:

1. **Check preceding events:** rolling deployment, scaling, broker outage, or network interruption?
2. **Check the consumer group:** member count, assignments, rebalance count, and duration.
3. **Check polling:** is the listener taking longer than max.poll.interval.ms?
4. **Check dependencies:** are databases/APIs experiencing higher latency, locks, or timeouts?
5. **Check the JVM:** GC pauses, CPU throttling, thread starvation, or out-of-memory.
6. **Check the network:** broker/coordinator connectivity, DNS, and packet loss.
7. **Check callbacks:** is cleanup blocking the poll thread or throwing exceptions?
8. **Check offsets:** commit failures, redelivery, and lag after rebalancing.
9. **Check side effects:** duplicates, out-of-order updates, stale owner writes.
10. **Remediate with measurement:** timeouts, max.poll.records, concurrency, lease/fencing, graceful shutdown.

Do not merely increase max.poll.interval.ms and ignore the root cause. If the cause is a DB slowing down under overload, raising timeouts can slow consumer recovery further; fix the dependency, bound concurrency, or change the work model.

## 24. Testing onPartitionsLost

Unit tests can verify that the callback invokes lifecycleService.onLost(partitions), but are insufficient to prove a consumer truly lost ownership. Integration tests or controlled consumer group experiments are needed.

### 24.1. Callback unit test

~~~java
@Test
void lostInvalidatesOwnerScopedWork() {
    TopicPartition partition = new TopicPartition("orders.events", 0);

    lifecycleService.onAssigned(List.of(partition));
    lifecycleService.onLost(List.of(partition));

    assertThat(lifecycleService.lostPartitionsTotal()).isEqualTo(1);
}
~~~

This is an illustrative service test pattern; when the application uses owner tokens, tests should verify the old assignment's token is invalidated and new assignments are unaffected.

### 24.2. Simulating normal rebalance

1. Create a multi-partition topic and two consumers in the same group.
2. Observe onPartitionsAssigned.
3. Add a third consumer or scale instances.
4. Record onPartitionsRevoked and new assignments.
5. Confirm the lost callback **is not assumed mandatory** for a controlled rebalance.

### 24.3. Simulating ownership loss

1. Have a consumer process a record slowly or create a condition causing the consumer to lose membership.
2. Let the coordinator redistribute partitions to remaining consumers.
3. Let the old consumer continue polling/rejoining if still alive.
4. Observe onPartitionsLost when the Kafka client detects lost state per the active version's mechanism.
5. Confirm the old consumer does not attempt to commit offsets or execute side effects after ownership is lost.
6. Confirm the new consumer processes from the valid committed offset.

In practice, onPartitionsLost is not guaranteed to appear under every failure injection method. Tests should record group assignments and callbacks per Kafka client version, avoiding assertions requiring lost on every restart/crash.

### 24.4. Testing stale async tasks

1. Consumer A receives a partition and spawns a deliberately delayed background task.
2. Transfer the partition to consumer B.
3. Invalidate A's token.
4. Let A's old task proceed to the DB write step.
5. Confirm fencing/idempotency blocks the stale write.
6. Confirm B's new task can still write normally.

### 24.5. Testing crash without callback

1. Consumer A receives a partition and creates an external lease.
2. Kill process A before cleanup callbacks can run.
3. Confirm the lease expires or the coordinator/new owner can acquire authority per policy.
4. Confirm uncommitted records are redelivered.
5. Confirm the system does not depend on A's onPartitionsLost to recover.

Crash tests are crucial: callbacks do not replace distributed fault tolerance.

## 25. Pre-deployment checklist

- Have you properly distinguished onPartitionsRevoked from onPartitionsLost?
- Did you override lost explicitly instead of accidentally reusing revoked offset commit logic?
- Is the callback registered on the right ConcurrentKafkaListenerContainerFactory?
- Are there multiple child consumers/concurrency requiring state synchronization?
- Is cleanup fast, bounded, and non-blocking on the consumer poll thread?
- Does it stop or invalidate async work belonging to the old owner?
- Are there owner tokens so new assignments' state/locks are not deleted?
- Do external DBs/APIs have strong enough idempotency, optimistic concurrency, or fencing?
- Do you avoid offset commits and late acks after partitions are lost?
- Have you measured max.poll.interval.ms, processing duration, and rebalance duration?
- Are there metrics for lost, revoked, assigned, commit failures, and duplicates?
- Have you tested clean rebalance, lost membership, restart/crash, and stale workers?
- Have you verified the Kafka client/Spring Kafka version and specific callback contracts?

## 26. Conclusion

**onPartitionsLost is not a reminder to do one last offset commit.** It is a signal that the old consumer has lost partition ownership and must stop acting as a valid owner. In Spring Kafka, ConsumerAwareRebalanceListener allows applications to receive this signal, clean up local state, invalidate stale work, and observe membership incidents.

Reliability does not stop at the callback: to prevent duplicates and stale writes when partitions change owners, applications must combine safe committed offsets, idempotent side effects, owner fencing, and recovery mechanisms even when a process dies before any callback runs.
