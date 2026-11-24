# onPartitionsAssigned

In a Kafka consumer group, each partition is assigned to at most one consumer member at a time. When the consumer group starts up, changes the number of members, or rebalances, the consumer needs to know **which partitions have just been assigned to it** in order to begin processing the right data. The `onPartitionsAssigned` callback is the lifecycle hook for that work.

In a Spring Kafka application, `onPartitionsAssigned` is commonly used to log assignments, initialize per-partition processing state, attach local resources, restore application-managed checkpoints, or decide to seek to a specific offset according to policy. This callback sits on the boundary between **Kafka's assignment decision** and **the listener container's processing lifecycle**.

The crucial point is that **being assigned does not mean records have been processed or offsets have been committed**. The callback only notifies that the consumer now has authority to receive the assigned partitions. Reading records, retries, acknowledgements, and commits take place according to the mechanisms of the consumer and the Spring Kafka listener container. If you change offsets in the callback without understanding this, the application can re-read large volumes of data or skip unprocessed messages.

## 1. Position of onPartitionsAssigned in the consumer lifecycle

A Kafka consumer joins a consumer group via `subscribe(...)`. The group coordinator and partition assignor determine which member receives which partitions. Once the assignment is finalized, Kafka invokes `ConsumerRebalanceListener.onPartitionsAssigned(Collection<TopicPartition>)` during `poll()`. The Spring Kafka listener container coordinates the poll loop and can forward the event to a registered rebalance listener.

An illustrative cycle:

~~~mermaid
sequenceDiagram
    participant C as Spring Kafka container
    participant K as Kafka group coordinator
    participant R as Rebalance listener
    participant L as KafkaListener
    C->>K: Subscribe / poll / join group
    K-->>C: New partition assignment
    C->>R: onPartitionsAssigned(partitions)
    R-->>C: Initialize resources / seek by policy
    C->>K: Poll according to current assignment
    K-->>C: ConsumerRecords
    C->>L: Deliver records to listener
    L-->>C: Processing completes or throws exception
    C->>K: Commit offset per AckMode / transaction
~~~

The diagram describes the logical sequence, not a promise that Kafka only invokes the callback once. A consumer can receive the callback multiple times during its lifecycle due to rebalances, subscription changes, or being reassigned partitions after a failure. The callback may also be invoked with an empty list in certain situations; the application should not assume there are always partitions.

### Common invocation points

- **Consumer startup:** the initial group assignment is formed, and the callback indicates which partitions have been assigned.
- **Scale out:** a new consumer joins, and partitions may move to the new member.
- **Scale in or restart:** another member takes over partitions left behind by the old member.
- **Consumer timeout:** partitions of a member that lost authority can be reassigned after a rebalance.
- **Partition count increase or subscription change:** the assignor may redistribute assignments.
- **Cooperative rebalance:** some partitions are retained; some partitions change owners.

Do not use this callback to infer that the producer has stopped publishing, the topic has no more records, or all partitions in the topic belong to the current consumer.

## 2. TopicPartition and callback scope

The argument to the callback is a collection of `TopicPartition`. Each element contains the topic name and partition number; it **does not contain messages**, **does not contain committed offsets**, and **is not a key distinguishing consumer groups**.

~~~text
group.id = orders-service
topic    = orders.events (4 partitions)

Consumer A is assigned:
  TopicPartition(orders.events, 0)
  TopicPartition(orders.events, 2)

Consumer B is assigned:
  TopicPartition(orders.events, 1)
  TopicPartition(orders.events, 3)
~~~

Within the same consumer group, partition 0 is not simultaneously assigned to both A and B once the group has stabilized. If the application has multiple `@KafkaListener`s, multiple groups, or multiple containers, each container will have its own callback and assignment. When logging, include `group.id`, listener ID, and application instance ID to identify which consumer the callback belongs to.

### Assignment is not permanent ownership

Kafka can revoke the assignment in the next rebalance. An asynchronous job started when `onPartitionsAssigned` runs can continue to exist after the partition is revoked. Therefore, per-partition resources and work must be tied to the *assigned → processing → revoked/lost* lifecycle, not merely initialized once at startup.

## 3. Kafka ConsumerRebalanceListener API

The underlying Kafka client API is `ConsumerRebalanceListener` with the related callbacks:

| Callback | When to use | Notes |
|---|---|---|
| `onPartitionsAssigned(partitions)` | After receiving an assignment | Initialize state, log owner, optionally seek per policy. |
| `onPartitionsRevoked(partitions)` | When owned partitions are about to be revoked in a normal rebalance | Clean up state, finalize progress, or save checkpoint if appropriate. |
| `onPartitionsLost(partitions)` | When the consumer has already lost ownership without a normal revoke opportunity | Do not assume you can commit as the current owner; focus on releasing resources safely. |

`onPartitionsLost` has default behavior/support methods depending on the Kafka client version; check the actual API when implementing it yourself. Spring Kafka provides callback variants and ways to integrate with the container to coordinate commits and lifecycle.

Do not confuse `onPartitionsAssigned` with `onPartitionsRevoked`:

- Assigned: the consumer **begins having authority** to process the assigned partitions.
- Revoked: the consumer **is about to lose authority** or end ownership of a set of partitions.
- Lost: the consumer **has already lost authority**; the opportunity for a synchronous commit before revoke may have already passed.

If state initialization logic is placed in assigned, corresponding revocation or invalidation logic must exist in revoked/lost.

## 4. Using ConsumerAwareRebalanceListener in Spring Kafka

Spring Kafka supports `ConsumerAwareRebalanceListener`, allowing callbacks to additionally receive the `Consumer<?, ?>` object managed by the container. This is a convenient way to observe assignments or perform contextually thread-safe consumer operations, such as `seek(...)`.

Example of configuring a listener container factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
            new ConcurrentKafkaListenerContainerFactory<>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    factory.getContainerProperties().setConsumerRebalanceListener(
            new ConsumerAwareRebalanceListener() {
                @Override
                public void onPartitionsAssigned(
                        Consumer<?, ?> consumer,
                        Collection<TopicPartition> partitions) {

                    for (TopicPartition partition : partitions) {
                        log.info("Assigned topic={} partition={}",
                                partition.topic(),
                                partition.partition());
                    }
                }
            });

    return factory;
}
~~~

Relevant imports include `ConcurrentKafkaListenerContainerFactory`, `ConsumerFactory`, `ConsumerAwareRebalanceListener`, `Consumer`, `TopicPartition`, and `Collection`. The example assumes an application logger `log`.

Listener using the factory:

~~~java
@KafkaListener(
        topics = "orders.events",
        groupId = "orders-service",
        containerFactory = "ordersKafkaListenerContainerFactory")
public void onOrderEvent(OrderEvent event) {
    orderService.processIdempotently(event);
}
~~~

The factory creates three child consumers when `concurrency=3`. Each consumer has its own assignment and callbacks. If the topic has two partitions, not all three consumers will receive partitions; one consumer may have no assignment.

### Why does Spring have ConsumerAware?

Kafka consumer is not thread-safe. The Spring Kafka container owns the poll loop on the consumer thread. When callbacks are executed within the container's rebalance cycle, calling allowed consumer operations inside the callback can be safer than passing the consumer reference out to an arbitrary worker thread.

However, **having access to `Consumer` does not mean you should call every method inside the callback**. Avoid long blocking operations, operations contrary to the container lifecycle, or manually committing offsets inconsistent with transactions/AckMode.

## 5. onPartitionsAssigned is not onPartitionsRevoked

Spring Kafka has callbacks allowing revoke handling at different points in the container commit workflow. `ConsumerAwareRebalanceListener` provides hooks such as `onPartitionsRevokedBeforeCommit` and `onPartitionsRevokedAfterCommit` in supported versions.

Typical division of responsibilities:

| Timing | Suitable work | Should not do |
|---|---|---|
| Assigned | Log assignment, register state, prepare consumer position | Commit offsets of unprocessed records. |
| Revoked before commit | Write checkpoint/capture appropriate application state | Block the consumer thread for too long or promise rollback of external side effects. |
| Revoked after commit | Release resources, mark partitions as no longer owned | Continue processing old work as the owner. |
| Lost | Invalidate owner and cancel/mark pending jobs | Try to commit offsets as if still owning. |

With eager rebalancing, many partitions may be revoked and then reassigned. With cooperative rebalancing, only part of the assignment needs to change. Therefore, lifecycle logic should **operate on the partition set reported by the callback**, rather than blindly clearing all container state on every assignment.

## 6. Eager and cooperative rebalance: meaning of the assigned list

The partition assignor and rebalance protocol affect the partition set returned in the callback.

### Eager rebalance

In the eager model, members typically revoke all partitions during a rebalance and then receive a new assignment. Therefore, the assigned callback can receive back partitions that the consumer already owned previously.

If the code clears state or seeks to the beginning of the topic on every assigned callback, the application may re-read excessive records after every scale event or rolling restart.

### Cooperative rebalance

With a cooperative assignor such as `CooperativeStickyAssignor`, consumers can keep partitions that do not need to be transferred; only partitions that must change ownership are revoked/assigned incrementally. The list in the assigned callback **is not necessarily all partitions belonging to the consumer**; some partitions may have been retained across the rebalance.

Example:

~~~text
Before rebalance:
  Consumer A: P0, P1, P2
  Consumer B: P3

After group change:
  Consumer A: P0, P1
  Consumer B: P2, P3

P0, P1 stay on A; P2 moves to B.
Each member's callbacks depend on protocol and assignment.
~~~

Do not implement logic like "whenever onPartitionsAssigned appears, clear the entire state map and rebuild it only from the callback list". In cooperative rebalancing, that approach can wipe out state for partitions still owned.

If you need to know the full assignment, use the appropriate container/consumer API at a valid point in time to cross-check; do not assume the callback list is always a complete snapshot of all partitions across all protocols.

## 7. Initializing state per partition

Some consumers maintain caches, counters, reference data, or processing state per partition. When assigned, the application can initialize an owner record or create the corresponding state container.

Conceptual state management example:

~~~java
public final class PartitionStateRegistry {
    private final ConcurrentMap<TopicPartition, PartitionState> states =
            new ConcurrentHashMap<>();

    public void assigned(Collection<TopicPartition> partitions) {
        partitions.forEach(topicPartition ->
                states.computeIfAbsent(
                        topicPartition,
                        ignored -> new PartitionState()));
    }

    public void revoked(Collection<TopicPartition> partitions) {
        partitions.forEach(states::remove);
    }
}
~~~

The example illustrates a registry; `PartitionState` is an application-defined type. If multiple child containers in the same application operate on the registry, you must manage owners accurately and prevent state leaks after rebalance. `computeIfAbsent` only avoids recreating when state already exists; it does not replace version, checkpoint, or validity controls when a partition changes owner.

### Restoring state from external systems

If state must be loaded from a database or object storage, you should:

1. Identify the exact topic/partition just received.
2. Read version/checkpoint metadata corresponding to the partition and offset position.
3. Verify the checkpoint is compatible with the expected committed offset.
4. Only allow the listener to process once the required state is ready.
5. When the partition is revoked/lost, stop using old state and cancel pending work appropriately.

Do not run multi-minute queries directly in the callback if it prevents the consumer thread from polling. If state is large, consider an asynchronous preparation strategy combined with proper container pause/resume; only resume after restore succeeds and verify that the assignment is still valid.

## 8. Seeking inside onPartitionsAssigned

A Kafka consumer normally starts reading from the consumer group's **committed offset** for the partition. If no valid committed offset exists, the `auto.offset.reset` policy is used to choose the starting point per configuration.

In `onPartitionsAssigned`, you can proactively `seek` to another offset. However, seeking is a decision that alters the consumer's read position:

- `seek(topicPartition, offset)` changes the **position**, without automatically committing the offset.
- `seekToBeginning(...)` requests reading from the start of the retained log.
- `seekToEnd(...)` requests jumping to the current end of the log, which can skip unprocessed backlog if misused.
- `commitSync(...)` records group progress; it is not equivalent to seeking.

Example of intentionally reading newly assigned partitions from the beginning:

~~~java
@Override
public void onPartitionsAssigned(
        Consumer<?, ?> consumer,
        Collection<TopicPartition> partitions) {

    if (!partitions.isEmpty() && replayModeEnabled) {
        consumer.seekToBeginning(partitions);
    }
}
~~~

`replayModeEnabled` is an application-managed policy flag; this is illustrative code only. **Do not use this example by default in production.** For a group that already has committed offsets, `seekToBeginning` can cause every rebalance to replay old data. If the listener has business side effects, re-reading must have idempotency and replay approval.

### Seeking to an external checkpoint outside Kafka

A specialized architecture might store checkpoints in a database:

~~~text
Topic orders.events, partition 2
Kafka committed offset: 510
External state checkpoint: 505

If seeking back to 505:
  May reprocess 505..509
  Must ensure corresponding state restore and idempotency

If seeking forward to 520:
  May skip 510..519
  Only valid with an explicit business decision
~~~

Do not mix two checkpoint sources without consistency rules. Kafka committed offsets and external snapshots must be tied to a verifiable state boundary. When a custom checkpoint is not needed, let the container start from the normal committed offset.

## 9. ConsumerSeekAware.onPartitionsAssigned

Spring Kafka provides another approach for seeking at the listener level: the `ConsumerSeekAware` interface. This interface has a callback of the form:

~~~java
void onPartitionsAssigned(
        Map<TopicPartition, Long> assignments,
        ConsumerSeekCallback callback);
~~~

This is the **Spring Kafka `ConsumerSeekAware` callback**, not the same signature as Kafka's `ConsumerRebalanceListener`. The map contains the partitions and positions/offsets provided by the framework at callback time; `ConsumerSeekCallback` provides methods to request seeks in the way Spring Kafka coordinates.

Example listener that only logs partitions and starting offsets:

~~~java
public class OrdersListener implements ConsumerSeekAware {

    @KafkaListener(topics = "orders.events", groupId = "orders-service")
    public void onMessage(OrderEvent event) {
        orderService.processIdempotently(event);
    }

    @Override
    public void onPartitionsAssigned(
            Map<TopicPartition, Long> assignments,
            ConsumerSeekCallback callback) {

        assignments.forEach((tp, offset) ->
                log.info("Spring seek-aware assignment: {}-{} at {}",
                        tp.topic(), tp.partition(), offset));
    }
}
~~~

The class in the example must be registered as an appropriate Spring bean/listener so the container detects `ConsumerSeekAware`. If active seeking is required, use `ConsumerSeekCallback` methods, such as `seek(topic, partition, offset)`, in the supported context.

### Choosing ConsumerAwareRebalanceListener or ConsumerSeekAware?

| Need | Commonly suitable API |
|---|---|
| Log assignments and interact with `KafkaConsumer` directly during rebalance | `ConsumerAwareRebalanceListener` |
| Attach hooks at the listener bean level and seek via Spring Kafka API | `ConsumerSeekAware` |
| Manage revoke/lost and per-partition state resources at the container level | Appropriate rebalance listener |
| Seek by timestamp/offset for replay use cases | `ConsumerSeekAware` or consumer-aware callback, with clear policy |

Do not simultaneously register both mechanisms to seek to two different positions. If multiple callbacks interfere with consumer position in the same lifecycle, execution order and final offset may be unexpected. Choose one component primarily responsible for offset policy.

## 10. Callbacks run on the consumer thread

The Kafka client invokes rebalance callbacks as part of `poll()`. In Spring Kafka, rebalance listener callbacks are invoked within the container's consumer thread context. This is why you can operate on the consumer directly **inside the callback**, but it is also a source of performance risk.

### Do not block the thread for too long

If `onPartitionsAssigned` calls an external service taking 90 seconds, the consumer thread does not continue polling. With many partitions or consecutive rebalances, the group can suffer high latency, risking hitting `max.poll.interval.ms` or timeout limits.

Do not perform the following unbounded tasks inside the callback:

- Calling REST APIs without timeouts.
- Running database migrations or heavy queries.
- Loading entire multi-GB caches from object storage.
- `Thread.sleep` waiting on business conditions.
- Creating unbounded thread pools or spawning jobs untied to partition lifecycle.
- Calling nested `poll()` or arbitrarily committing offsets inside a listener callback.

Keep callbacks small, deciding assignments and initializing metadata quickly. If a workload requires heavy state restoration, design a separate pause/resume/ready mechanism, ensuring the consumer still polls when needed and does not process records before state is ready.

### KafkaConsumer is not thread-safe

Do not save `Consumer<?, ?>` from the callback and pass it to an executor to call `seek` or `commitSync`. `KafkaConsumer` in general is not thread-safe; consumer operations must be coordinated on the appropriate thread. Spring Kafka has container APIs and `ConsumerSeekCallback` for certain operations; use them in the proper lifecycle instead of accessing the consumer directly from a background thread.

## 11. Offset commits and acknowledgements after assignment

`onPartitionsAssigned` does not mean any records have been processed. When a partition has just been assigned, the consumer normally reads from the valid committed offset and the Spring Kafka listener begins processing.

With `enable.auto.commit=false`, the container manages commits according to `AckMode`:

| Mode | Relationship to callback |
|---|---|
| `RECORD` | Offset commits after each record the listener processes successfully; assignment only determines where to read. |
| `BATCH` | Offset commits after a batch per policy; callback is not a batch commit boundary. |
| `MANUAL` | Listener calls `Acknowledgment.acknowledge()` after business logic; assignment does not auto-acknowledge. |
| `MANUAL_IMMEDIATE` | Acknowledge on the consumer thread may commit immediately per policy; do not call prematurely in assignment. |
| Transactional container | Container includes input offsets alongside Kafka outputs in the transaction upon successful processing. |

Dangerous example:

~~~java
@Override
public void onPartitionsAssigned(
        Consumer<?, ?> consumer,
        Collection<TopicPartition> partitions) {

    // Do not commit "end of topic" just because partitions were assigned.
    consumer.seekToEnd(partitions);
    // If continuing to commit these positions under the wrong policy,
    // unprocessed backlog may be skipped after a restart.
}
~~~

Seeking does not commit by itself, but changing position and then processing/committing onward can cause old records not to be delivered in the normal way. If you want to reset offsets, you need a controlled procedure and must ensure the consumer group is not unexpectedly processing concurrently.

### Retries and idempotency

When a partition changes ownership, records whose business logic finished but whose offsets were not committed may be redelivered to the new owner. `onPartitionsAssigned` does not eliminate this duplicate. Use stable event IDs and idempotency mechanisms (such as an inbox table with a unique constraint in the same DB transaction) for effects outside Kafka.

## 12. Rebalance, revoked/lost, and asynchronous tasks

A common risk is a listener receiving a partition and pushing records to an executor. When a rebalance occurs, the old worker can still process records after the partition has been assigned to another consumer.

Example:

~~~text
T1: Consumer A receives P2 (onPartitionsAssigned)
T2: A submits record offset 80 to background worker
T3: Group rebalances, P2 moves from A to B
T4: B starts processing offset 80 from committed offset
T5: A's background worker finishes, intends to commit offset 81
~~~

If A arbitrarily commits offset at T5, the system can suffer wrong ownership or commit failures. If A writes to the database before committing, B can create business duplicates.

To prevent this:

1. Attach an owner/assignment generation or dedicated token to each partition state.
2. When revoked/lost, mark the old token invalid.
3. Cancel, wait for completion, or hand pending work over to a safe recovery mechanism.
4. Do not commit offsets for records that have not completed in partition order.
5. Do not invoke the consumer from a background worker not managed by the container.
6. Use idempotency at the database/API level, because cancelling a worker does not guarantee rolling back side effects that already occurred.

If choosing asynchronous processing, understand how Spring Kafka manages acknowledgements, pause/resume, and out-of-order acks in the running version. Do not rely solely on `onPartitionsAssigned` as the single source of truth for processing authority.

## 13. Combining with static membership

`group.instance.id` allows Kafka to recognize a stable consumer instance across restarts. Static membership can help reduce rebalances during brief restarts, but **does not prevent all assignment callbacks**, nor does it make partition ownership permanently fixed.

If a static member does not return before the session timeout or the group changes for another reason, partitions can still be assigned to another member. In that case, the new owner's `onPartitionsAssigned` must be handled normally.

Do not use fewer callback occurrences as the sole metric to evaluate static membership success. Observe group member count, rebalance duration, partition assignment, and consumer lag as well.

## 14. Illustrative Spring Boot configuration

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-service
      enable-auto-commit: false
      max-poll-records: 100
      properties:
        "[max.poll.interval.ms]": 300000
    listener:
      concurrency: 3
      ack-mode: record
~~~

In this configuration, three consumer threads can be created in the same listener container. Each consumer's `onPartitionsAssigned` reflects the partitions specifically assigned to it.

If the topic has six partitions and there are no other members in the group, each consumer can receive around two partitions depending on the partition assignor. If the topic has two partitions, one consumer may remain idle. Do not increase `concurrency` assuming multiple consumer threads will concurrently process **a single partition**.

The timing and batch values are examples; measure listener latency, retries, database operations, and state restoration callback time before deploying to production.

## 15. Observing onPartitionsAssigned in production

Assignment logs are direct evidence of partitions changing owners. However, logging only partition names without instance/consumer ID makes it hard to reconstruct a timeline when a rebalance occurs.

| Signal | Purpose | Note |
|---|---|---|
| Group ID, member/client ID, listener ID | Identify which consumer the callback belongs to | Do not use per-record varying IDs as metric labels. |
| Assigned topic/partition set | Track current partition owner | Distinguish delta callbacks from full assignments in cooperative rebalancing. |
| Revoked/lost partition set | Identify when old owner lost authority | Correlate with pending workers and offset commits. |
| Timestamp and callback duration | Detect overly slow state initialization callbacks | Alert when restore p95/p99 increases. |
| Consumer lag and committed offset | Check progress after rebalance | Lag must be viewed per partition. |
| Seek count and seek target | Detect unexpected seeks | Do not log payloads or sensitive data. |
| Rebalance count/duration | Assess group stability | Compare against deployments and timeouts. |
| Listener errors/retries | Know whether newly assigned records continue failing | Distinguish data errors from infrastructure errors. |

Suggested log:

~~~text
INFO rebalance_assigned
  groupId=orders-service
  listenerId=ordersListener-1
  instanceId=orders-pod-2
  assigned=[orders.events-0,orders.events-3]
  callbackDurationMs=8
  seekPolicy=committed-offset
~~~

This is an illustrative structure; emit structured logs instead of free-form strings if the system has centralized logging/tracing.

### Do not treat every assigned callback as an error

Callbacks appearing at startup or scaling can be completely normal. Alerts should be based on continuous rebalancing, prolonged callbacks, rising lag, repeated assignment loss, or unintended seeks; do not alert just because `onPartitionsAssigned` occurred once.

## 16. Runbook: onPartitionsAssigned appears continuously

1. Identify group ID, listener ID, instance, and timestamp of each callback.
2. Check deployment/scaling schedule and member count in the group.
3. Read rebalance, session timeout, heartbeat, and `max.poll.interval.ms` logs.
4. Check for slow listener processing, blocking retries, or long state restoration callbacks.
5. Review partition assignor, eager/cooperative strategy, and subscription changes.
6. Check whether there are more consumers than partitions, or instances repeatedly joining/leaving.
7. Fix the root cause of membership instability and re-measure rebalance rate/lag.

Do not increase all timeouts by intuition. If a thread is blocked due to a long query in the callback, increasing session timeout may only slow down failover.

## 17. Runbook: Consumer re-reads from the beginning after rebalance

1. Check if the callback calls `seekToBeginning`, `seek`, or another `ConsumerSeekAware` callback.
2. Read the group's actual committed offsets for the affected topic/partition.
3. Check if the group ID changed across deployments.
4. Remember that `auto.offset.reset` only takes effect when there is no valid committed offset.
5. Cross-check external checkpoints with Kafka offsets and the state restore policy.
6. If manual seeking exists, identify the reason and the owner who approved replay.
7. Use idempotency to control duplicates; do not reset again before understanding the cause.

If committed offsets were lost due to retention or a new group ID, the reset policy can affect the starting point; verify before concluding the callback is the cause.

## 18. Runbook: Partition assigned but not processing records

1. Confirm the partition is assigned to a consumer with a running listener, not just an old callback log.
2. Check whether the container is paused, stopped, or waiting for state restore.
3. Check whether the listener subscribed to the right topic/partition and Kafka ACLs allow fetching.
4. Compare current position, committed offset, and end offset.
5. Check whether the callback sought to the end of the log or an out-of-range offset.
6. Check whether an exception in `onPartitionsAssigned` or state initialization logic stopped the container.
7. Check downstream blocking, poll interval, and lag after recovery.

Do not run `seekToBeginning` as a default firefighting measure; that can create massive replays and duplicates.

## 19. Runbook: State lost or duplicated after cooperative rebalance

1. Identify which partitions were actually revoked, lost, or assigned.
2. Check whether the code clears the entire state map on every callback.
3. Correlate the event timeline with the rebalance mode and retained partition assignments.
4. Ensure cleanup applies only to revoked/lost partitions.
5. For new partitions, restore state with the matching checkpoint version/offset.
6. Check whether old async workers continued using state after the partition lost ownership.
7. Test partial rebalancing in staging before deploying the fix.

## 20. Runbook: onPartitionsAssigned is too slow

1. Measure callback duration per member and partition count.
2. Identify DB queries, remote APIs, snapshot loads, or locks blocking the callback.
3. Set finite timeouts for all I/O and reduce synchronous work on the consumer thread.
4. Separate heavy state restoration into an asynchronous mechanism with a ready state and proper pause/resume if required by the application.
5. When performing async restore, tag an assignment epoch/owner to discard stale results if the partition is revoked.
6. Monitor `max.poll.interval.ms`, rebalance duration, and listener lag after changes.

Avoid offloading heavy work to an executor and immediately letting the listener read records while state is not yet ready. That only trades a timeout error for a business consistency error.

## 21. onPartitionsAssigned control checklist

| Checkpoint | Question to answer | Evidence |
|---|---|---|
| Callback wiring | Is the rebalance listener attached to the right container factory? | Bean configuration and assigned logs. |
| Assignment semantics | Is the callback list newly assigned partitions or the full assignment in the current rebalance? | Assignor/protocol, pre/post rebalance timeline. |
| Thread ownership | Are consumer APIs called properly from the consumer thread? | Callback location and thread name. |
| State restore | Is state/checkpoint compatible with the partition and committed offset? | Snapshot version, offset, restore result. |
| Seek policy | Is there manual seeking, and is there a risk of re-reading/skipping data? | Seek target, committed offset, and replay approval. |
| Lifecycle | Do revoked/lost clean up state and cancel old workers? | Assignment token, cleanup logs. |
| Backpressure | Does the callback hold polling for too long? | Callback duration, poll interval, and timeout metrics. |
| Ordering/offset | Does the listener ack/commit after business logic finishes? | AckMode, committed offsets, event ID. |
| Rebalance | Is there a rebalance storm, static ID collision, or overloaded consumer? | Member count, rebalance logs, and lag. |
| Recovery | Do restarts, retries, and reassignments create duplicates? | Inbox/unique event ID and fault-injection tests. |

**Conclusion:** `onPartitionsAssigned` is the starting point of the processing lifecycle for Kafka partitions assigned to a consumer. In Spring Kafka, the callback helps observe assignments, initialize state, and perform controlled seeks, but it is not a signal of successful processing or a place for arbitrary offset commits. A solid design must separately handle assigned, revoked, and lost cases; distinguish eager/cooperative rebalancing; avoid blocking the consumer thread for too long; and protect offsets, state, and external side effects against restarts/rebalances. Used properly, `onPartitionsAssigned` enables consumers to resume from a valid position and recover safely whenever partitions change owners.
