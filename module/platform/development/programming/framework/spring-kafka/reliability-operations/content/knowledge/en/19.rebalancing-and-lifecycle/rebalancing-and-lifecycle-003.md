# onPartitionsRevoked

When a Spring Kafka consumer is processing records, Kafka may decide to **revoke ownership of one or more partitions** from that consumer. This event typically happens during a **consumer group rebalance**: a new instance joins the group, an instance leaves the group, a consumer fails to poll on time, or the assignment is recalculated. Kafka invokes the **onPartitionsRevoked** callback to notify that the partitions are about to no longer belong to the consumer's processing authority.

In high-reliability systems, this is not merely a topology change callback. **onPartitionsRevoked is the critical moment to complete or stop work tied to the partitions, coordinate offset commits, and release partition-scoped state** before the partitions are assigned to another consumer. If the callback is handled improperly, the application can commit offsets past unprocessed data, duplicate side effects, lose in-memory state, hold resources too long, or trigger further rebalances.

This lesson explains the revoke mechanism in Kafka and Spring Kafka, the ConsumerRebalanceListener/ConsumerAwareRebalanceListener APIs, offset commit timing, differences between eager/cooperative rebalancing, the relationship with onPartitionsLost, how to protect asynchronous processing, and operational procedures.

## 1. What is onPartitionsRevoked?

A Kafka consumer group distributes partitions across consumer members. For a group at a stable assignment point, each partition is assigned to only one consumer member. When membership or subscription changes, the group must recompute the assignment.

Initial example:

~~~text
Topic orders: P0, P1, P2, P3

Consumer group orders-service
  Consumer A -> P0, P1, P2, P3
~~~

When Consumer B joins:

~~~text
Before rebalance:
  A -> P0, P1, P2, P3
  B -> no partitions yet

Rebalance:
  A receives request to revoke partitions to be handed over
  Group coordinator computes/finalizes new assignment

After rebalance:
  A -> P0, P1
  B -> P2, P3
~~~

Before A gives up P2 and P3, Kafka can invoke the onPartitionsRevoked callback for the revoked partitions. The application gets an opportunity to close resources, record valid processing progress, and avoid starting new tasks on partitions about to depart.

Key points to remember:

- **A revoked partition** is a partition currently in the process of leaving the current consumer's assignment.
- **Rebalance callbacks** run within the consumer poll lifecycle, not as a per-record business event.
- **The partition set passed into the callback** represents the partitions Kafka reports as revoked; do not assume it always contains all of the consumer's partitions.
- **The Kafka consumer group** manages ownership; in-memory application state must adapt to new ownership on its own.

## 2. When is the callback invoked?

Situations that commonly lead to rebalancing or assignment changes:

1. A new replica/consumer joins the group to scale out.
2. A consumer is stopped during a deployment or scale-in.
3. A member fails to meet heartbeat or poll interval requirements per the group protocol.
4. The consumer changes subscription or the topic's partition count changes.
5. The coordinator/consumer encounters connection errors or needs to re-establish membership.
6. The assignment strategy changes across deployments.

Do not assume that **every loss of ownership always invokes onPartitionsRevoked completely before partitions are assigned to another member**. If a consumer loses membership unexpectedly, such as exceeding max.poll.interval.ms or the broker determining the session has expired, the application may only learn that partitions were lost via another callback/error, or the process may die before any callback runs.

Therefore, onPartitionsRevoked helps with graceful handoff but **cannot be the sole mechanism guaranteeing zero data loss**. Proper offset commits, idempotency, and durable state storage remain necessary.

## 3. ConsumerRebalanceListener in the Kafka client

The Kafka client provides the **org.apache.kafka.clients.consumer.ConsumerRebalanceListener** interface with common callbacks:

- **onPartitionsRevoked(Collection<TopicPartition>)**: invoked when the consumer is about to give up the notified partitions.
- **onPartitionsAssigned(Collection<TopicPartition>)**: invoked when the consumer receives a new assignment or completes the assignment phase.
- **onPartitionsLost(Collection<TopicPartition>)**: intended for cases where partitions have already lost ownership, rather than a normal revoke with a handoff opportunity; support and behavior depend on client version.

General flow:

~~~text
Consumer.poll()
     |
     +-- detects rebalance needed
     |
     v
onPartitionsRevoked(...)
     |
     +-- finalize/record processed progress
     +-- prevent new work on revoked partitions
     +-- clean up state to be handed over
     |
     v
Group assignment changes
     |
     v
onPartitionsAssigned(...)
     |
     +-- initialize new partition state
     +-- prepare to resume consuming
~~~

This is a diagram for a controlled revoke/assign cycle. In practice, timing and partition sets differ between eager and cooperative rebalancing; some phases may repeat, be empty, or not occur as shown when a consumer loses membership abruptly.

A raw Kafka listener can be written as:

~~~java
ConsumerRebalanceListener listener =
        new ConsumerRebalanceListener() {

    @Override
    public void onPartitionsRevoked(
            Collection<TopicPartition> partitions) {
        log.info("Partitions revoked: {}", partitions);
    }

    @Override
    public void onPartitionsAssigned(
            Collection<TopicPartition> partitions) {
        log.info("Partitions assigned: {}", partitions);
    }
};
~~~

In Spring Kafka, prefer registering listeners through the **listener container**, so Spring Kafka coordinates callbacks with offset commits and container lifecycle.

## 4. Spring Kafka's ConsumerAwareRebalanceListener

Spring Kafka provides **ConsumerAwareRebalanceListener**, a listener-container-friendly variant. The interface allows callbacks to additionally receive `KafkaConsumer` and provides hooks around the moment the container commits pending offsets.

Important callbacks:

| Callback | Practical meaning |
|---|---|
| **onPartitionsRevokedBeforeCommit** | Called before the container's step to commit pending offsets in a normal revoke flow |
| **onPartitionsRevokedAfterCommit** | Called after the container's pending offsets commit step |
| **onPartitionsAssigned** | Lets the application prepare state when partitions are assigned |
| **onPartitionsLost** | Handles cases where ownership is already lost, when supported by the Kafka/Spring Kafka version |

For applications where a listener container manages offsets, separating **before commit** and **after commit** helps run logic at the right moment rather than manually committing offsets in a single generic callback.

Example listener class:

~~~java
@Component
public class OrderPartitionRebalanceListener
        implements ConsumerAwareRebalanceListener {

    private static final Logger log =
            LoggerFactory.getLogger(OrderPartitionRebalanceListener.class);

    @Override
    public void onPartitionsRevokedBeforeCommit(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {

        log.info("Preparing revoke for {}", partitions);
    }

    @Override
    public void onPartitionsRevokedAfterCommit(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {

        log.info("Revoked after pending commits: {}", partitions);
    }

    @Override
    public void onPartitionsAssigned(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {

        log.info("New assignment: {}", partitions);
    }
}
~~~

The snippet illustrates common Spring Kafka callbacks. Method names/overloads and `onPartitionsLost` support must be verified against your actual dependency version. Only read necessary information from `KafkaConsumer` in the callback; do not arbitrarily pass the `Consumer` object to another thread.

## 5. Registering callbacks on the Spring Kafka listener container

With `ConcurrentKafkaListenerContainerFactory`, you can configure the rebalance listener on `ContainerProperties`:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderKafkaListenerContainerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory,
                OrderPartitionRebalanceListener rebalanceListener) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setConsumerRebalanceListener(rebalanceListener);
    return factory;
}
~~~

And select the factory when declaring the listener:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "orders-service",
        containerFactory = "orderKafkaListenerContainerFactory")
public void handle(ConsumerRecord<String, OrderEvent> record) {
    orderService.process(record.value());
}
~~~

If the factory has concurrency greater than 1, Spring Kafka creates corresponding child containers/consumers; each consumer can receive different partition sets. A single rebalance listener bean may be used by multiple child containers. Therefore:

- Do not store a global variable like `currentPartition` assuming there is only one consumer.
- Do not clear all partition state for all consumers when the callback only revokes a few partitions.
- If using shared state, ensure thread safety and use keys identifying the appropriate consumer/container.
- All operations involving the `Consumer` object must obey `KafkaConsumer` thread-confinement.

Do not attach a new rebalance listener for each `@KafkaListener` by manually altering consumer subscriptions after the container is running; use the container factory or container configuration supported by Spring Kafka.

## 6. Before commit and after commit ordering

The Spring Kafka container may be holding offsets eligible to commit under `AckMode` when a rebalance arrives. Therefore, hooks around the commit have operational significance:

~~~text
Kafka triggers revoke process
       |
       v
onPartitionsRevokedBeforeCommit(...)
       |
       v
Spring Kafka container commits pending offsets
       |
       v
onPartitionsRevokedAfterCommit(...)
       |
       v
Consumer hands over partitions
~~~

**onPartitionsRevokedBeforeCommit** is suitable for finalizing internal state related to completed records, ensuring no new work is accepted on revoked partitions, or logging the count of in-flight tasks.

**onPartitionsRevokedAfterCommit** is suitable for closing partition-bound resources, updating ownership state in the application, or recording checkpoints that the container has attempted to commit.

However, the name "after commit" **is not a promise that every offset of every asynchronously processed record was committed successfully**. Pending offsets depend on `AckMode` and acknowledgment status. If the commit fails, callbacks/lifecycle may differ; commit errors must be observed separately. With asynchronous processing, the application must know which offsets actually completed before acknowledging.

Do not place `consumer.commitSync()` in the before-commit callback just to "be sure" if the container already manages commits. Extra commits can conflict with pending acks or advance the group offset past incomplete records.

## 7. Why is offset commit the biggest risk?

Kafka consumers commit offsets so the consumer group knows where to read next. If the record at partition P1, offset 40 succeeds, the group usually commits **41**, which is the next position.

~~~text
orders/P1

offset 38 -> completed
offset 39 -> completed
offset 40 -> completed
offset 41 -> not completed

Safe offset to commit: 41
~~~

If there are async tasks at offset 41 and offset 42, committing 43 before offset 41 finishes can cause record 41 to be skipped after a rebalance.

~~~text
Tasks:
  offset 41 -> calling REST API
  offset 42 -> completed

Rebalance arrives

Commit offset 43 -> unsafe
Because offset 41 is not completed
~~~

This commonly happens when a listener receives a record, dispatches work to an `ExecutorService`, and **returns immediately**, while the container uses an ack mode that allows committing when the method finishes.

Principles:

1. Only acknowledge records that have been processed successfully per business semantics.
2. Do not commit offsets past gaps of incomplete records within the same partition.
3. On revoke, block new work and handle in-flight tasks within a deadline.
4. If they cannot complete safely, let uncommitted records be redelivered and rely on idempotency to prevent duplicate side effects.

Correct commits are necessary not to lose records; idempotency is necessary to reduce harm when records are reprocessed.

## 8. AckMode and revoke

Spring Kafka has several `AckMode`s, each affecting when the container commits offsets:

| AckMode | General meaning | Points to note on revoke |
|---|---|---|
| **RECORD** | Commits per record processed successfully by listener | Usually clear with synchronous listeners |
| **BATCH** | Commits after processing records of a poll batch | Revoke may occur while pending offsets exist |
| **TIME / COUNT / COUNT_TIME** | Commits based on time/record-count thresholds | Pending offsets may remain uncommitted before rebalance |
| **MANUAL** | Listener acknowledges, container performs commit per mode semantics | Must control acks during async processing |
| **MANUAL_IMMEDIATE** | Can commit on acknowledge on consumer thread per mode semantics | Do not arbitrarily acknowledge from other threads |

With transactional listeners, consumed offsets can be included in the Kafka transaction managed by the container; do not add manual `commitSync` in the rebalance callback thinking it will join that transaction.

Choose `AckMode` based on the processing model rather than merely wanting to "commit fast". With async processing, understand support for async acks, acknowledgment ordering, and how the container pauses/seeks when gaps exist.

A revoke callback cannot fix an acknowledgment design that is flawed from the start. It is only one part of the lifecycle.

## 9. How do onPartitionsRevoked and onPartitionsLost differ?

The two callbacks represent different partition ownership scenarios:

| Callback | Timing | Allowed actions |
|---|---|---|
| **onPartitionsRevoked** | Consumer is participating in handing over partitions in a normal rebalance | Finalize completed progress, hand over state, stop new work; commit via container when appropriate |
| **onPartitionsLost** | Partitions already lost ownership before the consumer had a normal handoff opportunity | Stop processing, release resources, **do not attempt to commit offsets on lost partitions** |

When partitions are lost, another consumer may already be the valid owner. Trying to commit offsets or write state as if still owning the partitions can cause commit failures, overlapping data, or race conditions.

Example:

~~~text
Consumer A owns P2
    |
    +-- A is stalled past max.poll.interval.ms
    |
Group moves P2 to Consumer B
    |
Consumer A resumes
    |
    +-- detects ownership loss
    +-- onPartitionsLost(P2) if supported by client/container
    |
    +-- DO NOT commit offset of P2 as old owner
    +-- stop related tasks and clear local state
~~~

Some Kafka/Spring Kafka versions have default `onPartitionsLost` methods or callbacks with different signatures; verify the API in use. More important than the exact signature is the principle of **never assuming a graceful revoke precedes every ownership loss**.

## 10. Eager rebalance and cooperative rebalance

The partition assignment strategy directly affects the set of partitions in the revoke callback.

### Eager rebalance

With the traditional eager mechanism, members usually give up their entire current assignment before the group finalizes a new assignment.

~~~text
Before:
  A -> P0, P1
  B -> P2, P3

Eager rebalance:
  A revokes P0, P1
  B revokes P2, P3

After:
  A -> P0
  B -> P1, P2, P3
~~~

The application can observe many partitions revoked even when some partitions are later reassigned to the same consumer.

### Cooperative rebalance

With a cooperative strategy, the group tries to minimize partitions that must be given up, keeping partitions that do not need to change owners.

~~~text
Before:
  A -> P0, P1
  B -> P2, P3

Cooperative rebalance:
  A revokes P1
  B keeps P2, P3

After:
  A -> P0
  B -> P1, P2, P3
~~~

The diagram is a simplified illustration; actual cooperative assignment can involve multiple rebalance rounds to transfer ownership safely.

**Consequence:** the callback must not clear a global cache or close P0's resources just because P1 was revoked. Handle precisely the **Collection<TopicPartition> partitions** passed to the callback.

Eager or cooperative strategy is determined by the partition assignment protocol/assignor and compatibility of members in the group; do not guess solely from consumer count.

## 11. How should partition-scoped state be managed?

A listener may hold state tied to individual partitions:

- Buffer of unflushed records.
- Completed checkpoint or watermark.
- In-memory aggregation.
- Partition-dedicated connections or caches.
- File handles, local temporary state, schedulers, executor queues.
- Consumer ownership metadata.

On revoke, only clean up state for partitions in the revoked set:

~~~text
Partition state map

P0 -> state A
P1 -> state B
P2 -> state C
P3 -> state D

onPartitionsRevoked(P1, P3):
  close state B
  close state D

Keep state A, C if P0/P2 are still owned.
~~~

For rebuildable data caches, deleting on revoke usually causes no data loss; for data kept only in memory without a durable checkpoint, immediate deletion can lose uncommitted results.

Therefore, state design should follow a **safely persist/flush then release** flow when time permits; if time does not permit or ownership is already lost, allow records to be replayed from the committed offset and rebuild state from Kafka data.

## 12. Example: managing partition state in callbacks

Suppose the application manages a separate `PartitionState` object per `TopicPartition`. Cleanup logic can be extracted into a dedicated service:

~~~java
public interface PartitionStateRegistry {
    void prepareForRevoke(Collection<TopicPartition> partitions);
    void closeRevoked(Collection<TopicPartition> partitions);
    void initializeAssigned(Collection<TopicPartition> partitions);
}
~~~

And register the rebalance listener:

~~~java
@Component
public class StateAwareRebalanceListener
        implements ConsumerAwareRebalanceListener {

    private final PartitionStateRegistry stateRegistry;

    public StateAwareRebalanceListener(
            PartitionStateRegistry stateRegistry) {
        this.stateRegistry = stateRegistry;
    }

    @Override
    public void onPartitionsRevokedBeforeCommit(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {

        stateRegistry.prepareForRevoke(partitions);
    }

    @Override
    public void onPartitionsRevokedAfterCommit(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {

        stateRegistry.closeRevoked(partitions);
    }

    @Override
    public void onPartitionsAssigned(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {

        stateRegistry.initializeAssigned(partitions);
    }
}
~~~

The example illustrates **lifecycle hooks**, without assuming `stateRegistry` automatically solves concurrency or durability. For state shared across multiple container threads, the registry needs ownership keys sufficient to distinguish instances or child containers.

Do not store the `Consumer` object in the registry for later use on a background thread. `KafkaConsumer` must not be accessed concurrently from multiple threads.

## 13. In-flight asynchronous processing is a dangerous scenario

Suppose a listener dispatches a record to a worker pool:

~~~java
@KafkaListener(topics = "orders")
public void handle(ConsumerRecord<String, OrderEvent> record) {
    executor.submit(() -> orderService.process(record.value()));
}
~~~

This is an anti-pattern if the container interprets the method returning as meaning the record has finished processing. The callback returns before business work completes; a rebalance can occur while the task is still running.

~~~text
Consumer A:
  polls P1@100
  enqueues async task
  listener returns

Rebalance:
  A revokes P1
  Consumer B is assigned P1

Old async task on A:
  can still update database after revoke
~~~

Risks include:

- Offset already committed while async task is incomplete: processing can be lost.
- Offset uncommitted: B reprocesses the record while A still runs the old task, causing duplicate side effects.
- Partition-bound state closed while the task still uses it.
- Callback waits indefinitely to drain the worker pool, stalling the poll loop.

If async is mandatory, you need a Spring Kafka-supported model for async acknowledgments or a custom coordination mechanism with **partition ownership, in-flight tracking, bounded drain, cancellation, and idempotency**.

## 14. Strategy for draining in-flight tasks on revoke

A common strategy:

1. Mark revoked partitions as **closing** in the state registry.
2. Do not enqueue new work for those partitions.
3. Wait for a short bounded period for already accepted tasks to complete.
4. Record checkpoints/acks only for contiguous offsets that truly completed.
5. Cancel or allow retry of unfinished tasks per application semantics.
6. Release state and ownership.

Example:

~~~text
P1 processing:
  offset 100 -> DONE
  offset 101 -> DONE
  offset 102 -> IN_FLIGHT
  offset 103 -> DONE

onPartitionsRevoked(P1):
  mark closing
  drain <= configured deadline
  last contiguous completed = 101
  commit offset 102 (if policy/ownership allows)
  do not commit 104 because offset 102 is incomplete
~~~

The **contiguous completion** principle is especially important when multiple tasks for the same partition can finish out of order. Record 103 DONE does not permit committing past record 102 which is IN_FLIGHT.

If the callback cannot drain within the deadline, the system must accept that unfinished records will be redelivered. Idempotency and retry logic address the risk of partially executed side effects.

Do not turn the revoke callback into a place that waits indefinitely for an entire batch; blocking the callback too long can slow down rebalancing and increase the risk of the consumer losing membership.

## 15. Should you commit offsets inside the callback?

The Kafka client lets some applications managing offsets manually commit in `onPartitionsRevoked` if they still hold ownership and have completed work. However, in a **Spring Kafka listener container**, the container normally manages commits per `AckMode` and rebalance lifecycle.

Therefore, the preferred rules:

- Let the container commit pending offsets according to the configured policy.
- Only acknowledge records that have completed.
- Use `ConsumerAwareRebalanceListener`'s before/after commit callbacks to coordinate state.
- Avoid calling `commitSync`/`commitAsync` directly inside the callback without a clear reason and ownership design.
- Do not attempt to commit lost partitions.

If an application uses a raw `KafkaConsumer`, managing polling and manual commits itself, committing in the revoke callback can be a valid part of an at-least-once protocol. But that design differs from container-managed Spring Kafka; do not copy raw consumer code verbatim into an `@KafkaListener` container that already has commit logic.

A dangerous mistake is committing offsets based on **last delivered** instead of **last completed**. A record received by the listener whose business work has not finished should not be considered processed.

## 16. Manual acknowledgment and revoke callbacks

With a listener using `Acknowledgment`:

~~~java
@KafkaListener(
        topics = "orders",
        containerFactory = "manualAckListenerFactory")
public void handle(
        ConsumerRecord<String, OrderEvent> record,
        Acknowledgment ack) {

    orderService.process(record.value());
    ack.acknowledge();
}
~~~

This is a synchronous example: ack after successful processing. The factory needs to be configured with `AckMode.MANUAL` or `MANUAL_IMMEDIATE` depending on desired semantics.

If switching to async:

~~~text
Listener receives record
  |
  +-- submits task to executor
  +-- returns before processing finishes
  |
  +-- task completes on another thread
          |
          +-- must coordinate acknowledgment via right API/config
~~~

Spring Kafka has options for out-of-order async acknowledgments in some versions, but they come with conditions and consequences for pause/commit. Do not assume you can call `Acknowledgment` from any thread without order control and still guarantee correctness.

Rebalancing complicates things further: a task may finish **after the partition has changed owners**. Check ownership/generation before recording progress, and design idempotent side effects so old tasks do not corrupt state.

## 17. Transactional listeners and revoke

With Kafka container transactions, source offsets are included in the same Kafka transaction as Kafka outputs when the listener succeeds. When the transaction fails, the container can abort and use `AfterRollbackProcessor` for reprocessing.

~~~text
Listener transaction processing P1@100
    |
    +-- produce output in Kafka transaction
    +-- send source offset into transaction on success
    |
    +-- rebalance or commit failure
    |
    v
Transaction may abort
    |
    +-- aborted output not visible to read_committed
    +-- source offset not committed in failed transaction
~~~

**Do not call consumer.commitSync() inside onPartitionsRevoked to supplement offsets for a transactional listener**. Manual commits outside the transaction can break the goal of atomically committing outputs and consumed offsets.

Additionally, Kafka transactions do not protect database/API side effects. If the old consumer wrote to a database before the transaction aborted due to revoke/rebalance, a new consumer reprocessing the same event may write duplicates. Idempotency/outbox or version checks are needed.

With Kafka transactions, callbacks should focus on state and resource lifecycle; offset/transaction completion belongs to the container transaction manager.

## 18. Interaction with max.poll.interval.ms

**max.poll.interval.ms** limits the time between polls under consumer group protocol semantics. When a business listener takes too long or a revoke callback waits too long, the consumer may fail to poll on time.

Example:

~~~text
max.poll.interval.ms = 120 seconds

Business listener processing:   95 seconds
Revoke callback drain:          40 seconds
---------------------------------
Total:                         135 seconds
~~~

In the example, if the actual interval between polls exceeds 120 seconds, the consumer risks losing membership. The callback may not complete a graceful handoff as expected.

Recommendations:

- Keep callbacks short with an explicit deadline.
- Do not call external APIs with unbounded retries during revoke.
- Offload long work from the poll thread using a model with safe ownership and acks.
- Reduce `max.poll.records` if a poll batch is too large.
- Measure listener processing latency and callback duration.
- Tune `max.poll.interval.ms` to realistic SLOs, rather than merely increasing it indefinitely.

If a consumer loses membership, **onPartitionsLost** and commit errors must be handled reasonably. Do not rely on `onPartitionsRevoked` always having enough time to flush everything.

## 19. Is graceful shutdown the same as rebalance revoke?

When an application shuts down or a listener container stops, the consumer leaves the group and partition ownership is handed over to other members. During this lifecycle, callbacks related to revoke/cleanup may be invoked depending on timing and version.

However, **shutdown is not completely equivalent to a normal rebalance**:

- The process may be killed before callbacks run.
- The container has its own shutdown timeout.
- `KafkaConsumer` may no longer have a connection to commit.
- Kubernetes termination grace period may expire before tasks finish.

Therefore, do not make the entire data-flushing mechanism depend on `onPartitionsRevoked`. Valuable data should be persisted regularly or reside in a durable system.

Example during a rolling update deployment:

~~~text
Pod A receives SIGTERM
      |
      v
Spring listener container stops
      |
      v
Consumer leaves group
      |
      v
Partitions move to Pod B

If A receives SIGKILL before cleanup:
  B must still reprocess safely from committed offsets
~~~

A proper design must withstand both graceful shutdown and abrupt termination.

## 20. onPartitionsAssigned and state restoration

`onPartitionsRevoked` is only the first half of the lifecycle. When partitions are assigned to a new consumer, the application may need to reload state:

~~~text
Consumer A:
  onPartitionsRevoked(P2)
  save valid checkpoint
  close partition state

Consumer B:
  onPartitionsAssigned(P2)
  load state from storage
  continue consuming from committed offset
~~~

If Kafka offsets are the primary checkpoint, B reads from the consumer group's committed offset. If local state or an aggregate snapshot exists, ensure the snapshot is synchronized with processed offsets.

For example, if a snapshot records progress up to offset 99 while the group committed offset is 90: when B reads from 90, you must account for records being replayed and the snapshot possibly already including them. A safe approach is writing snapshots together with offset checkpoints in the corresponding store's transaction or making replay idempotent.

Do not manually seek to an offset higher than the group committed offset just because a state cache reports having processed further, unless you have sufficiently reliable durability and consistency mechanisms; doing so can drop records.

## 21. Distinguishing rebalance from partition pause/resume

Spring Kafka can pause/resume containers or partitions for backoff, throttling, or asynchronous processing. **Pause is not revoke**.

| State | Ownership | Can consumer poll? | Revoke callback? |
|---|---|---|---|
| Partition assigned and active | Still owns | Yes | Not just from being active |
| Partition paused | Still owns | Can poll to maintain membership | Not just due to pause |
| Partition revoked | Handing over ownership | Should no longer process that partition | May invoke revoke callback |
| Partition lost | Lost ownership | No longer valid owner | Lost callback when supported |

Do not clean up partition state merely because Spring Kafka paused a partition. If the pause is only to wait for a retry, the state will still be needed upon resume.

Conversely, when `onPartitionsRevoked` is invoked, do not assume you can resume that partition after the callback. Another consumer may become the owner.

## 22. Cooperative rebalance: handling the exact partition set

A common mistake when migrating from eager to cooperative:

~~~java
@Override
public void onPartitionsRevokedBeforeCommit(
        Consumer<?, ?> consumer,
        Collection<TopicPartition> revoked) {

    stateRegistry.clearAll(); // Do not do this: may wipe state of still-owned partitions.
}
~~~

A better design:

~~~java
@Override
public void onPartitionsRevokedBeforeCommit(
        Consumer<?, ?> consumer,
        Collection<TopicPartition> revoked) {

    stateRegistry.prepareForRevoke(revoked);
}
~~~

The registry uses each `TopicPartition` in **revoked** to mark it closing, rather than assuming every partition in the group must stop.

With eager rebalancing, the revoked set may be wider; operating on the parameter set still works. With cooperative rebalancing, this approach is crucial to avoid disrupting partitions that are retained.

When changing the assignor/protocol during a rolling deploy, verify compatibility across consumers in the same group; do not switch a single consumer individually to another mode ignoring group coordination rules.

## 23. Avoiding dangerous operations in callbacks

Things to avoid in `onPartitionsRevoked`:

- **Waiting indefinitely** for async tasks or external APIs.
- **Recording offsets using last fetched offset** instead of last completed offset.
- **Calling consumer.commitSync** outside the container's commit policy without control.
- **Passing the Consumer object to a background thread**, because `KafkaConsumer` is not thread-safe.
- **Clearing state for the entire group** when only a subset of partitions was revoked.
- **Arbitrary seek/pause/resume** inside the callback outside the container lifecycle.
- **Creating a new Kafka listener container** inside the callback.
- **Swallowing flush errors** and treating the checkpoint as successful.
- **Holding a global lock** on a cache/registry too long and blocking other consumer threads.

A safe callback typically only marks partitions closing, flushes completed data within bounded limits, logs state, and releases resources. Long operations should be designed upfront via periodic checkpoints or durable queues, not deferred until rebalance occurs.

## 24. How to handle flush/checkpoint failures during revoke?

Suppose an application performs stateful aggregation and needs to flush a snapshot when a partition is revoked. If flushing fails, do not log success or commit offsets past unpersisted state.

~~~text
Partition P2:
  Kafka consumed offsets 0..100
  In-memory state applied up to 100
  Last durable checkpoint up to 95

Revoke arrives:
  flush state up to 100 -> FAILURE

Must not falsely claim checkpoint up to 100.
~~~

Handling depends on architecture:

- If state can be rebuilt from Kafka, allow replay from a safe checkpoint/offset.
- If losing state causes unrecoverable data loss, persist state to a durable store during processing rather than only on revoke.
- If offset commits and state checkpoints must be consistent, use a state store protocol/transaction or an idempotent replay strategy.
- Record clear failure metrics and alerts; avoid infinite retries inside the callback.

With Spring Kafka container-managed commits, a pre-commit callback cannot block all future commits simply by returning false. Exception propagation/ack logic must be designed per the specific API; do not rely on the callback as a distributed transaction hook.

## 25. Logging and metrics for the rebalance lifecycle

To analyze rebalances, logs must tell **which consumer, which partitions, when, and what it did**.

Example structured log produced by the application:

~~~text
event=partitions_revoked
listenerId=orders-listener-2
groupId=orders-service
partitions=[orders-1,orders-3]
inFlight=4
lastContiguousCompleted={orders-1:104,orders-3:88}
drainTimedOut=true
durationMs=750
~~~

Useful metrics:

- Rebalance count and count of revoked/assigned/lost partitions.
- Revoke callback execution duration, p95/p99.
- Count of in-flight tasks when revoke starts.
- Count of remaining in-flight tasks when callback finishes.
- Count of flush/checkpoint failures.
- Consumer lag and commit failure rate.
- Rebalance duration and member churn.
- Interval between polls.
- Duplicate processing rate after rebalance.
- State loading duration when partitions are assigned.

Do not use offsets or event IDs as high-cardinality metric labels. Offsets belong in logs/traces; metrics should be labeled with controlled value sets such as listener, group, topic, and outcome.

If all consumers continuously revoke/assign and lag rises, investigate processing time, group churn, deployment rollouts, poll intervals, network, and coordinator, rather than merely increasing replicas.

## 26. Investigating when consumers revoke continuously

A diagnostic procedure:

1. Identify which group and consumer instances are rebalancing.
2. Check for pod scale up/down, crashes/restarts, or rolling deployments.
3. Inspect consumer group state and partition assignment.
4. Compare listener processing time against `max.poll.interval.ms`.
5. Check heartbeat logs, commit errors, and coordinator disconnects.
6. Measure `onPartitionsRevoked` callback duration.
7. Check whether async tasks or global locks are holding threads too long.
8. Check eager/cooperative assignor and group member compatibility.
9. Check producer fencing/transaction aborts if the listener is transactional.
10. Verify offsets are not committed past in-flight records.

Do not treat every revoke callback as an error. Rebalances during scaling or deployment are normal operation. It becomes a reliability issue when it is too frequent, prolonged, spikes lag, or leads to uncontrolled data loss/duplicate side effects.

## 27. Testing onPartitionsRevoked with integration tests

Test with a real Kafka broker or Testcontainers Kafka, because mocking a standalone listener callback does not reproduce consumer group protocol, assignment, and commit behavior.

### Test 1: new consumer joins

1. Create a topic with multiple partitions.
2. Start Consumer A in the group.
3. Wait for A to be assigned partitions.
4. Start Consumer B in the same group.
5. Observe revoked/assigned callbacks according to the active assignor.
6. Confirm no records are skipped or misprocessed after handoff.

### Test 2: cooperative partial revoke

1. Use an appropriate assignment strategy supported by all group members.
2. Configure a `TopicPartition`-based state registry.
3. Trigger a rebalance transferring only a subset of partitions.
4. Confirm only state for revoked partitions is closed.
5. Confirm unrevoked partitions continue processing.

### Test 3: unfinished in-flight task

1. Submit a record to a worker pool and block the task via test synchronization.
2. Trigger a rebalance while the task is still in-flight.
3. Confirm the callback does not commit past the incomplete record.
4. Let the new consumer process the uncommitted record.
5. Confirm side effects remain idempotent when the old task completes late.

### Test 4: abrupt shutdown

1. Consumer A is processing records.
2. Kill the process or container without a graceful revoke.
3. Start Consumer B.
4. Confirm B re-reads from the valid committed offset.
5. Confirm data uniqueness does not rely on the revoke callback.

### Test 5: callback drain timeout

1. Simulate an external operation that does not finish within the deadline.
2. Trigger a revoke.
3. Verify the callback returns within the allowed time.
4. Confirm outstanding records still have a retry path.
5. Confirm metrics/alerts report remaining in-flight tasks.

### Test 6: transactional listener

1. Configure transactional Kafka consume-process-produce.
2. Trigger a rebalance or error within the transaction before commit.
3. Confirm aborted Kafka outputs are not visible to downstream `read_committed` consumers.
4. Confirm consumed offsets are not committed erroneously.
5. Confirm DB/API side effects have idempotency if present.

Tests should use fixed event IDs, record keys with predictable partition distribution, and condition-based waits with timeouts. Do not use long sleeps and assume rebalancing has definitely completed.

## 28. Common misconceptions

**onPartitionsRevoked is just a callback for logging.** Incorrect. It is a critical ownership boundary for partition-scoped state, offsets, and in-flight work.

**onPartitionsRevoked is always invoked before a consumer loses partitions.** Incorrect in all failure scenarios. A consumer may lose membership or crash abruptly before a graceful revoke.

**The revoked partition list is always the entire assignment.** Incorrect, especially with cooperative rebalancing.

**AfterCommit means all async tasks have finished.** Incorrect. It only relates to the container's step of committing pending offsets per policy; async completion must be managed separately.

**You can commit the last fetched offset on revoke.** Incorrect. Only commit progress for contiguously completed records; last fetched may be ahead of unprocessed records.

**KafkaConsumer is thread-safe so callbacks can pass Consumer to an executor.** Incorrect. `KafkaConsumer` must not be used concurrently at will.

**onPartitionsLost is also a time to commit offsets.** Incorrect. Ownership is already lost; do not try to commit as the old owner.

**Partition pause means partition revoke.** Incorrect. Pause usually keeps assignment, whereas revoke transfers ownership.

**Adding concurrency always reduces rebalance impact.** Incorrect. Concurrency is bounded by partitions and increases member/resource overhead.

**Kafka transactions will roll back DB side effects on revoke.** Incorrect. Kafka transactions do not automatically roll back DB/API operations outside that transaction.

**Committing offsets fast is always good.** Incorrect. Committing too early can lose processing of incomplete records; committing too late increases replay. You must pick a safe boundary.

## 29. Production design principles

When implementing `onPartitionsRevoked` for Spring Kafka listeners:

1. Understand the group's assignor/protocol: eager or cooperative.
2. Use `ConsumerAwareRebalanceListener` to coordinate with the container's commit lifecycle.
3. Handle strictly the `TopicPartition` set passed into the callback; do not clear all state.
4. Choose `AckMode` and commit policy based on **processed**, not **fetched** records.
5. For async work, have per-partition tracking, contiguous offset completion, and bounded drain.
6. Accept that records may be replayed; protect side effects with idempotency.
7. Do not call `Consumer` APIs from background threads.
8. Do not manually commit offsets outside the Kafka transaction in a transactional listener.
9. In `onPartitionsLost`, perform safe cleanup only; do not assume commit authority remains.
10. Design partition state to be recoverable from storage or Kafka replay after a crash.
11. Keep callbacks short, measure duration, and do not block the poll loop past limits.
12. Monitor rebalances, revoked partitions, in-flight work, commit errors, and consumer lag.
13. Test partial revokes, abrupt shutdowns, async work, and transaction aborts.

**onPartitionsRevoked** is the handoff point of partition ownership between Kafka consumers. In Spring Kafka, this callback must be understood alongside the listener container, `AckMode`, offset commits, `AfterRollbackProcessor`, and the group's rebalance mechanism. When well designed, the callback enables clean state handoffs and limits the risk of lost or duplicated processing. Yet it is **proper offset commits, durable state storage, and idempotent processing** that truly protect the system even in cases where there is no opportunity for a graceful revoke.
