# Commit before rebalance in Spring Kafka

In a Kafka consumer group, **rebalance** is the process of redistributing partitions across consumers when members join/leave the group, a topic changes its partition count, or the group needs to adjust assignments. A consumer may be processing records from partition P0 and then be asked to return P0 to another consumer. If processed records **have not had their offsets committed**, the new consumer may re-read them. If commits happen **too early**, before business side effects complete, the system may miss processing.

**Commit before rebalance** means taking advantage of the partition revocation phase (*revocation*) to safely finish work and commit genuinely eligible offsets before transferring partition ownership. In Spring Kafka, the listener container already has mechanisms to manage offsets and commit during rebalance; applications can use **ConsumerAwareRebalanceListener** to perform necessary work before and after the container's commit step.

Remember: not every rebalance has a safe revoke phase. When a consumer loses partition ownership due to timeout expiration or fencing, the **onPartitionsLost** callback may occur instead of a normal commit opportunity. Therefore, committing before rebalance helps **reduce redelivery in normal scenarios**, but does not guarantee zero duplicates upon crashes, network drops, or unexpected ownership loss.

## 1. Why does offset commit matter when partitions change owners?

Kafka maintains committed offsets per **consumer group, topic, and partition**. The committed value is the position of the next record to read, not the count of records processed in a JVM.

Example:

~~~text
Topic: orders.events, partition 2

offset 100  --> Event A --> processed successfully
offset 101  --> Event B --> processed successfully
offset 102  --> Event C --> processed successfully
offset 103  --> Event D --> not processed yet
                       |
                       v
If A, B, C have completed:
  safe next offset = 103
  commit offset = 103
~~~

If consumer A owns partition 2 and a rebalance assigns the partition to consumer B:

- **Successfully committed offset 103:** B starts from offset 103 per the committed position, without re-reading A/B/C.
- **New progress not yet committed:** B starts from the old committed offset and may re-read A/B/C.
- **Prematurely committed offset 104 while D is unprocessed:** B may skip D, leading to lost business effects.

Therefore, the goal is not "commit the highest polled offset" but **commit the next offset following the sequence of safely, contiguously processed records for each partition**.

## 2. When does a rebalance occur?

Situations that commonly trigger a rebalance:

1. A new consumer joins the same consumer group.
2. A consumer actively stops or shuts down the application.
3. A consumer loses contact with the group coordinator.
4. A consumer fails to poll on time per max.poll.interval.ms.
5. Partition counts or topic metadata change.
6. Rolling deployments, autoscaling, or Kubernetes pod terminations alter group membership.
7. The group protocol or partition assignment strategy requires adjusting assignments.

~~~text
Initially:
  Consumer A: P0, P1
  Consumer B: P2, P3

Scale out:
  Consumer C joins
          |
          v
Group rebalance
          |
          +--> Consumer A: P0
          +--> Consumer B: P2
          +--> Consumer C: P1, P3
~~~

This is an example of a possible distribution, not a guaranteed assignment result. Depending on the assignor, Kafka may revoke all partitions (*eager rebalance*) or only revoke partitions that need to move (*cooperative rebalance*).

Committing before returning partitions helps the new consumer resume closest to the old consumer's actual progress, though commit authority still depends on whether the old consumer remains a valid group member.

## 3. Distinguishing revoke, lost, and assigned

The Kafka consumer rebalance API has key lifecycle callbacks:

| Callback | When | Should commit? |
|---|---|---|
| onPartitionsRevoked | Consumer is notified partitions are about to be revoked | May be the last chance to commit valid progress while still owning partitions |
| onPartitionsLost | Partitions already lost ownership; not a normal revoke | **Should not rely on committing**; another consumer may have already taken over |
| onPartitionsAssigned | Consumer receives a new assignment | Initialize state and start/resume processing |
| Spring onPartitionsRevokedBeforeCommit | Spring Kafka hook before container's pending offsets commit step | Flush/finalize necessary state before container commits, if safe |
| Spring onPartitionsRevokedAfterCommit | Spring Kafka hook after container handles commit during revoke | Record and release resources of revoked partitions |

A consumer typically receives the revoke callback while polling to handle a rebalance. However, when a consumer has lost ownership due to timeout or fencing, you cannot assume it still has permission to commit offsets for those partitions.

**onPartitionsLost is not a renamed version of onPartitionsRevoked.** In a lost scenario, the commit window may have already passed. The system must accept redelivery, use idempotency, and guard against stale writes.

## 4. How does the Spring Kafka listener container manage commits?

In Spring Kafka, the listener container calls KafkaConsumer.poll(), dispatches records to listeners, and tracks offsets according to **AckMode**. When the container manages commits, the application should not manually call consumer.commitSync() inside each listener method unless a special policy has been designed and its impact on container state is fully understood.

Common modes:

| AckMode | When progress is normally committed | Meaning during rebalance |
|---|---|---|
| RECORD | After listener processes each record successfully | Window of processed-but-uncommitted records is usually smaller |
| BATCH | After records of a poll have been processed | Many processed records may not have reached commit point yet |
| TIME | Per ackTime threshold | Pending offsets may exist when rebalance occurs |
| COUNT | Per ackCount threshold | Many uncommitted records may accumulate |
| COUNT_TIME | When count or time threshold is reached | Pending offsets may exist before threshold is met |
| MANUAL | Listener calls acknowledge; container performs commit per manual/batch semantics | Only properly acknowledged progress is committed |
| MANUAL_IMMEDIATE | Acknowledge on consumer thread may commit immediately | Must control thread and acknowledgment order |

On normal rebalance paths, the Spring Kafka listener container has logic to commit pending offsets according to its policy before partitions are revoked. Adding a custom rebalance listener **does not mean you must manually commit a second time**. Instead, use the appropriate hook to finalize resources/flush state before the container handles commits.

In particular, if a listener method returns before side effects actually finish because work was pushed to an async executor, the container may consider the record done too early. Committing before rebalance in that case is also **unsafe**, because the flaw lies at the listener boundary.

## 5. Order of rebalance callbacks in Spring Kafka

Spring Kafka has the **ConsumerAwareRebalanceListener** interface, extending ConsumerRebalanceListener by providing the consumer instance and callbacks aligned with the container's commit cycle.

A generalized revoke cycle:

~~~text
KafkaConsumer.poll() detects rebalance
               |
               v
Spring Kafka container
               |
               +--> onPartitionsRevokedBeforeCommit(...)
               |       |
               |       +--> application can safely flush state
               |            for relevant partitions
               |
               +--> Container commits pending offsets
               |       per ack/error-handling policy
               |
               +--> onPartitionsRevokedAfterCommit(...)
               |       |
               |       +--> release partition-local resources
               |
               v
Kafka group coordinator redistributes
               |
               v
onPartitionsAssigned(...) on consumer assigned partitions
~~~

The diagram shows the typical flow per the Spring Kafka callback API. Commit error scenarios, lost partitions, library versions, and rebalance mechanisms may cause the actual flow to differ from the happy path. The after-commit callback **is not a certificate that all side effects outside Kafka succeeded**.

Operational rules:

- Callbacks run within the consumer/container lifecycle; do not perform long I/O or unbounded blocking.
- Only affect the partitions supplied to the callback when using cooperative rebalancing.
- If flushing state is needed, ensure it is genuinely persisted durably before letting the container commit.
- On lost partitions, do not continue executing side effects or committing as if still owning the partitions.

## 6. Example ConsumerAwareRebalanceListener configuration

Example using Java configuration and AckMode.RECORD:

~~~java
@Configuration
public class OrderKafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    orderListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            PartitionStateService partitionStateService) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        factory.getContainerProperties().setAckMode(
                ContainerProperties.AckMode.RECORD
        );

        factory.getContainerProperties().setConsumerRebalanceListener(
                new ConsumerAwareRebalanceListener() {

                    @Override
                    public void onPartitionsRevokedBeforeCommit(
                            Consumer<?, ?> consumer,
                            Collection<TopicPartition> partitions) {

                        partitionStateService.flushCompleted(partitions);
                    }

                    @Override
                    public void onPartitionsRevokedAfterCommit(
                            Consumer<?, ?> consumer,
                            Collection<TopicPartition> partitions) {

                        partitionStateService.release(partitions);
                    }

                    @Override
                    public void onPartitionsAssigned(
                            Consumer<?, ?> consumer,
                            Collection<TopicPartition> partitions) {

                        partitionStateService.initialize(partitions);
                    }

                    @Override
                    public void onPartitionsLost(
                            Consumer<?, ?> consumer,
                            Collection<TopicPartition> partitions) {

                        partitionStateService.invalidate(partitions);
                    }
                }
        );

        return factory;
    }
}
~~~

This is an example of Spring listener container factory structure; PartitionStateService is an application service. The methods flushCompleted, release, initialize, and invalidate must be implemented according to actual business state and thread-safety contracts. Specific callback APIs depend on the Spring Kafka version, especially for the partitions lost callback.

Meaning:

- **BeforeCommit:** only flush results that are completed and eligible for commit; do not mark unfinished async work as successful.
- **AfterCommit:** clean up state tied to revoked partitions.
- **Assigned:** recreate caches or required partition-local state.
- **Lost:** drop authority to operate on lost partitions; do not use this callback to force a new commit.

If the service has no buffered state to flush, the before-commit callback may simply record metrics/logs. There is no need to add a custom listener just to call commitSync when the container already does so.

## 7. Distinguish flushing business state from committing Kafka offsets

"Flush before rebalance" can mean several things:

- Flush a database write buffer, ensuring the DB transaction has committed.
- Wait for in-flight records to be confirmed complete.
- Flush a producer sending Kafka outputs.
- Commit consumer group offsets to Kafka.

These **are not automatically equivalent**.

For example, a Kafka listener uses a buffer to batch multiple records before writing to a database. If the listener returns success while records are still only in RAM, the container may commit offsets even though the database has not saved the data. Upon rebalance or crash, the data in RAM vanishes.

~~~text
Listener receives record
       |
       v
Writes to in-RAM buffer
       |
       v
Listener returns normally
       |
       v
Spring Kafka may mark record processed
       |
       v
Offset committed during rebalance
       |
       v
Process crashes, buffer lost
       |
       v
No record left to re-read
~~~

If buffering is needed, build a proper completion tracking mechanism: only acknowledge/return success after side effects are durable, or manage acknowledgments manually based on real processing progress. Do not rely solely on onPartitionsRevokedBeforeCommit to rescue a listener that reported success prematurely.

Correct offset committing must be based on **contiguous completion progress** per partition, not the highest offset that has merely started processing.

## 8. Manual acknowledgment and rebalance

Example of a record listener using AckMode.MANUAL_IMMEDIATE:

~~~java
@KafkaListener(
        topics = "orders.events",
        groupId = "orders-service",
        containerFactory = "manualAckFactory"
)
public void onOrder(
        ConsumerRecord<String, OrderEvent> record,
        Acknowledgment acknowledgment) {

    orderService.applyIdempotently(record.value());

    // Only acknowledge after the side effect has been safely committed.
    acknowledgment.acknowledge();
}
~~~

Factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
manualAckFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.MANUAL_IMMEDIATE
    );

    return factory;
}
~~~

With MANUAL_IMMEDIATE, acknowledging on the consumer thread can commit immediately; when called from another thread, commit behavior may be deferred by the container depending on implementation. Therefore, **do not assume that an async callback calling acknowledge means the offset is immediately committed**.

If using AckMode.MANUAL, the listener calls acknowledge while the container performs commits per manual/batch semantics. During rebalance, pending acknowledgments and consumer positions must be handled by the container per the version's policy.

In both cases:

1. Only acknowledge after completing business side effects.
2. Do not acknowledge failed records just to reduce consumer lag.
3. Do not manually advance committed offsets past incomplete records.
4. Do not use the consumer object from worker threads outside the thread-safety contract.
5. On shutdown/revoke, prevent async work from continuing to write stale state after partitions change owners.

If the business truly requires asynchronous processing, you need a model managing completion and ordering of acks, with partition ownership tracking on rebalance. It should not be solved by directly committing the offset of the "fastest-completing task".

## 9. Example of choosing a safe offset per partition

Suppose a listener dispatches records of partition 0 to an executor:

~~~text
offset 10 --> processing completed
offset 11 --> processing not completed
offset 12 --> processing completed

Received offsets:        10, 11, 12
Completed offsets:       10,     12
Safely committable offset: 11
~~~

If 13 is committed because record 12 finished, record 11 will be skipped when another consumer takes over. The safe threshold is **the offset after the contiguous completed sequence** starting from the previous committed position, which in the example is 11.

If record 11 later succeeds, progress can be recorded up to 13.

~~~text
Before:
  committed = 10
  complete  = {10, 12}
  pending   = {11}
  safe next = 11

After 11 completes:
  complete  = {10, 11, 12}
  safe next = 13
~~~

Spring Kafka has mechanisms for acknowledgments and handling out-of-order acknowledgments in some versions, though each mechanism has requirements and may pause the consumer while gaps remain. If building your own executor, the developer is responsible for ensuring ordering, completion state, and partition ownership.

## 10. Why not call commitSync indiscriminately in callbacks?

The Kafka Consumer API allows:

~~~java
consumer.commitSync(
        Map.of(
                new TopicPartition("orders.events", 0),
                new OffsetAndMetadata(103L)
        )
);
~~~

This is merely a Kafka client example of **committing offset 103 for partition 0**. For the command to be right, 103 must genuinely be the next offset after contiguously completed records, and the consumer must still hold valid group partition ownership.

Do not copy this snippet into Spring Kafka's onPartitionsRevokedBeforeCommit without a custom offset-management design. If the container is already tracking pending offsets, an external commitSync can:

- Commit an offset higher than the actually completed records.
- Duplicate or clash with state the container is about to commit right after the callback.
- Make offset analysis difficult if the container's acknowledgment state differs from self-managed state.
- Fail due to rebalance/generation mismatch.
- Increase callback duration and hurt consumer group stability.

**Prefer letting the Spring Kafka container commit the offsets it tracks**. A custom ConsumerRebalanceListener should focus on lifecycle and application state unless you intentionally manage the entire offset logic.

## 11. CommitSync vs commitAsync near a rebalance

Kafka consumer supports both synchronous and asynchronous offset commits.

| Property | commitSync | commitAsync |
|---|---|---|
| Caller feedback | Waits for broker to return result or error | Returns early, callback receives result |
| Result known when continuing | Yes when call finishes successfully | No, must track callback |
| Latency cost | May be higher | Usually less thread-blocking |
| Commit error | Throws exception to caller | Reported in callback |
| Use during revoke | Easy to confirm offset committed before returning partition | Risk that callback has not returned when ownership changes |

In a consumer managing offsets manually with the raw Kafka client, a common strategy is periodic commitAsync and commitSync on revoke/shutdown while still holding valid ownership, tracking errors on both. However, with a Spring Kafka listener container, **the container itself** already has syncCommits config, commit timeout, AckMode, and rebalance commit logic; do not blindly apply extra commitSync calls in callbacks as a blanket rule.

Spring Kafka can be configured for sync or async commits via ContainerProperties APIs, for example:

~~~java
factory.getContainerProperties().setSyncCommits(true);
~~~

Verify the appropriate configuration and timeout for your Spring Kafka version. When using async commits, monitor callback/commit errors; a dispatched commit call is not proof that the offset was written successfully.

## 12. Handling CommitFailedException

CommitFailedException can occur when an offset commit cannot be completed under the consumer group protocol, for example when the consumer is no longer a valid member due to rebalance or generation change.

An event sequence:

~~~text
Consumer A processes slowly
        |
        v
Exceeds max.poll.interval.ms
        |
        v
Group rebalance
        |
        v
Partition moves to Consumer B
        |
        v
Consumer A attempts to commit offset
        |
        v
CommitFailedException / no valid commit authority
~~~

When encountering this error:

- Do not treat the offset as committed.
- Do not force writing a higher offset unless certain all side effects completed.
- Do not try to "reclaim" the partition by continuing to use the old consumer outside group membership.
- Let the container handle lifecycle/rebalance per contract.
- Use idempotency because consumer B may re-read records.
- Identify the root cause: overly slow listener, max.poll.interval, blocking retries, broker/network errors, overly frequent rebalances.

CommitFailedException is not the kind of error that infinite retries with the same consumer state can always resolve. It can indicate the consumer has lost the required ownership/generation. Recovery typically means accepting the new assignment and letting records be redelivered from the committed position.

## 13. onPartitionsLost: when there is no longer a commit opportunity

A consumer can lose partitions due to timeouts or group protocol before a normal revoke callback runs in time.

~~~text
Consumer A owns P1
       |
       +--> Network drops or processing takes too long
       |
       +--> Coordinator considers A no longer valid
       |
       v
P1 moves to Consumer B
       |
       v
A detects partition lost
       |
       v
A is no longer the valid owner of P1
~~~

In onPartitionsLost:

1. Mark partition-local ownership as no longer valid.
2. Stop or cancel async tasks still using data from that partition whenever possible.
3. Stop emitting side effects based on the assumption of still owning the partition.
4. Do not attempt to commit offsets as in onPartitionsRevoked.
5. Let the new consumer reprocess from the committed offset.
6. Rely on idempotency and version checks to protect external systems.

If an async task cannot be cancelled and still writes to the database after partition lost, **two consumers may both produce side effects** within a short window: the new consumer B and the stale task from A. This case requires authority control via version/fencing token, unique event ID, or durable locks at the external resource, not just Kafka offset commits.

## 14. Fencing stale workers when partitions change owners

For example, a listener dispatches database writes to an executor, then the partition transfers from consumer A to B. A may finish its old task while B has already reprocessed the same event.

To prevent stale workers from overwriting new state, you can use:

- A unique constraint on eventId to block the same event from executing side effects twice.
- Optimistic locking with an aggregate version.
- A lease or fencing token stored at the destination system.
- A state machine requiring version-matched state transitions.
- Isolating work strictly on the consumer thread and waiting for completion within a reasonable time.
- Stopping executors/tasks for revoked/lost partitions.

Optimistic update example:

~~~sql
UPDATE orders
SET status = :new_status,
    version = :next_version
WHERE order_id = :order_id
  AND version = :expected_version;
~~~

If an old record arrives late, the UPDATE is not applied when current version differs from expected version. Classify zero updated rows: event already applied, event arrived out of order, or missing data; do not infinitely retry a deterministic state conflict.

This protects database state **outside Kafka**, where offset transactions do not reach.

## 15. Cooperative and eager rebalance

Kafka has different assignment strategies. Two models commonly distinguished:

**Eager rebalance**

- Consumers may have to revoke many or all partitions before receiving a new assignment.
- The processing pause window may be larger.
- The revoke phase typically involves many partitions.

**Cooperative rebalance**

- Consumers can revoke only the partitions that need to change owners.
- Retained partitions can remain with the current consumer.
- The revoke callback may supply only a **subset** of partitions.

Example:

~~~text
Consumer A before rebalance:
  P0, P1, P2

Cooperative rebalance needs to move P2 to B:
  revoked from A: {P2}
  retained by A:  {P0, P1}
~~~

Therefore, the callback should handle precisely the Collection<TopicPartition> passed in, rather than cleaning up/flushing all global state when only one partition is revoked. An application with partition-local buffers or caches needs keys by TopicPartition and separate lifecycles.

Do not assume a callback will be invoked strictly once for the entire group rebalance. Depending on the Kafka protocol, group membership, and implementation, callbacks may repeat or carry empty collections; code should be idempotent.

## 16. Spring Kafka concurrency and partition ownership

ConcurrentMessageListenerContainer creates multiple child containers, each with its own KafkaConsumer. Concurrency increases parallelism across partitions without giving the same partition to multiple simultaneous owners within one consumer group.

~~~text
Topic orders.events: P0 P1 P2 P3 P4 P5
Concurrency: 3

Child Consumer 1: P0, P1
Child Consumer 2: P2, P3
Child Consumer 3: P4, P5
~~~

This is an illustrative partition assignment. When a child consumer rebalances, its lifecycle callbacks relate to the partitions that child is handling. Do not use a single global variable like currentOffset to manage progress across all partitions.

A PartitionStateService should store by TopicPartition:

~~~text
TopicPartition("orders.events", 0) -> safe next offset 101
TopicPartition("orders.events", 1) -> safe next offset 205
TopicPartition("orders.events", 2) -> safe next offset  77
~~~

If state is shared across multiple child consumers, thread-safety and ownership fencing are required. When a partition moves to another child, old state must not continue altering offsets or side effects as if still assigned.

Increasing concurrency beyond the partition count yields no extra useful parallelism for that topic, while still requiring rebalance lifecycle handling.

## 17. Controlled shutdown before rolling deployments

A Kubernetes rolling deployment may send SIGTERM to a pod running a Kafka listener. The normal shutdown path is an opportunity for the listener container to stop accepting data, finish in-progress work, and commit valid offsets before closing the consumer.

~~~text
Deployment begins replacing pod
         |
         v
SIGTERM to old pod
         |
         v
Spring application context closes
         |
         v
Listener container stops
         |
         +--> stops fetching new work
         +--> completes/waits for work per lifecycle
         +--> commits offsets safely per policy
         |
         v
Consumer closes / leaves group
         |
         v
Partitions are reassigned
~~~

This is the **graceful shutdown** path, not a certainty in every situation. OOM kills, node power loss, kill -9, or grace period expiration can prevent final cleanup/commit steps.

Measures:

- Set terminationGracePeriodSeconds sufficiently to match record processing time and container shutdown time.
- Do not keep listeners running unbounded blocking operations.
- Provide an async work drain mechanism before the container stops, if needed.
- Monitor shutdown timeouts, commit errors, and rebalance lag.
- Use idempotency to survive ungraceful crashes.
- Do not attempt to commit offsets after the consumer has closed or lost assignment.

Do not merely increase the grace period while ignoring real processing/commit limits. The system must still remain safe when shutdown is cut short.

## 18. How does static membership help?

Kafka supports static membership via group.instance.id to reduce group membership churn during short restart cycles when configurations and protocols align.

Significance:

- Can reduce how often the group must redistribute partitions in some cases.
- Can be useful during rolling deployments with stable consumer identities.
- Does not completely eliminate rebalances.
- Does not replace offset commits or idempotency.
- If a consumer truly loses membership or partitions are revoked, revoke/lost must still be handled accurately.

When using concurrency, each child consumer must have a valid/unique group.instance.id identity per the corresponding Spring Kafka and Kafka client mechanisms. Do not copy the same static ID across multiple concurrent consumers.

Static membership is a tool to reduce unnecessary rebalances, **not a mechanism guaranteeing exactly-once side effects**.

## 19. Rebalance and Kafka transactions

With a transactional listener container, input offsets and Kafka output records can be committed in the same Kafka transaction. If the listener fails or the transaction aborts, uncommitted outputs are invisible to read_committed consumers and offsets are not committed in that transaction.

~~~text
Consumer processes event E in Kafka transaction
        |
        +--> KafkaTemplate.send(output)
        |
        +--> Listener succeeds
        |       |
        |       v
        |    Input offset added to transaction
        |       |
        |       v
        |    Commit transaction
        |
        +--> Exception / abort
                |
                +--> Output not committed
                +--> Input offset not committed
                |
                v
         AfterRollbackProcessor
                |
                v
           Seek / redelivery
~~~

During rebalance, the transaction may fail or the producer may be fenced if group ownership/generation is no longer valid. Do not try to manually commit offsets outside the Kafka transaction to "salvage" an execution whose transaction aborted.

What must be protected is **the right transaction boundary**: listener completion, Kafka output, input offsets, and exception propagation per the Spring Kafka container.

If the listener also updates a database or calls HTTP, Kafka rollback does not automatically undo those side effects. Transactional inbox/outbox or idempotency is still needed.

## 20. Commit before rebalance does not create database exactly-once

Suppose a record is used to update a database:

~~~text
Consumer A processes event E
        |
        v
Database COMMIT succeeds
        |
        v
Consumer A crashes before Kafka offset commit
        |
        v
Consumer B receives partition
        |
        v
Consumer B re-reads event E
        |
        v
Database may be updated again
~~~

Rebalance callbacks have no chance to run when A crashes abruptly. Therefore, if the goal is applying an effect only once, an idempotent consumer is required:

~~~java
@Transactional
public void process(OrderCreated event) {

    boolean firstTime = processedEvents.insertIfAbsent(
            "order-projector",
            event.eventId()
    );

    if (!firstTime) {
        return;
    }

    orderRepository.applyCreated(event);
}
~~~

insertIfAbsent must use an atomic insert/unique constraint within the same database transaction as orderRepository.applyCreated. If the event was already processed, the method can return normally so the Spring Kafka container commits the offset without creating a second side effect.

Thus, **committing before rebalance reduces the probability of re-reading**, while **idempotency ensures re-reading does not corrupt business results**.

## 21. Premature commit causing data loss

A listener might push work to an executor and return:

~~~java
@KafkaListener(topics = "orders.events")
public void onOrder(OrderEvent event) {

    executor.execute(() -> orderService.apply(event));

    // Listener returns before the executor completes.
}
~~~

With a container using AckMode.RECORD, the listener returning normally can be treated as finishing the record. The offset may be committed while the task is not actually finished. Later, a rebalance or crash loses the task, and the new consumer will not re-read the record because the offset already advanced.

The fix is not adding commitSync to the revoke callback. You must change the completion contract:

- Process synchronously until side effects are durable before returning.
- Or use an async acknowledgment mechanism supported by Spring Kafka that adequately manages completion/revocation state.
- Or persist the work to a durable queue/database before considering the Kafka record complete.
- Do not return success merely because a Runnable was submitted to RAM.

This is a reliability issue larger than choosing sync vs async offset commits.

## 22. Commit failure after successful side effect

Another scenario:

~~~text
Listener processes DB successfully
         |
         v
DB commit succeeds
         |
         v
Rebalance callback / container commits Kafka offset
         |
         v
CommitFailedException
         |
         v
Partition is assigned to Consumer B
         |
         v
Record may be re-read
~~~

Do not try to force the Kafka offset forward at all costs. If consumer A no longer has valid commit authority, it must stop operating under the old assignment. Consumer B re-reads and uses eventId to determine that the DB effect already ran.

Operational guidance:

1. Log commit errors with group/topic/partition/offset without exposing sensitive payloads.
2. Monitor consumer group membership and rebalance count.
3. Check listener processing time and max.poll.interval.ms.
4. Check network/coordinator errors if any.
5. Ensure idempotent redelivery handling.
6. Avoid infinite commit retries by a consumer that lost ownership.

## 23. Comparing commit timings

| Timing | Pros | Risks |
|---|---|---|
| After each successfully processed record (RECORD) | Smaller duplicate window | Frequent commits |
| After each poll batch completes (BATCH) | Reduces commit overhead | Many processed records may remain uncommitted |
| By COUNT/TIME | Optimizes commit frequency | Large pending offsets or long wait times |
| After MANUAL ack | Application controls completion | Early/out-of-order acks can lose data |
| During normal revoke | Reduces replay when partitions change owners | No such opportunity on lost/crash |
| Commit before side effect | Reduces duplicates | **Risk of business data loss** |
| Commit after side effect | Possible redelivery on crash | Requires idempotency, usually safer design |

Commit before rebalance **supplements** the daily acknowledgment policy rather than replacing it. If a system only commits during rebalance, it may hold large numbers of processed-but-uncommitted records while the group is stable and suffer broad replays on crash.

## 24. Common incidents and how to diagnose them

### After rebalance, many old records are re-read

Check committed offsets before and after revoke, AckMode, pending acknowledgment count, and commit errors. If a consumer loses partitions without a commit opportunity, redelivery is normal behavior. Do not jump to blaming a Kafka broker bug.

### onPartitionsRevokedBeforeCommit is not called

The consumer may have lost ownership via onPartitionsLost, the container was killed abruptly, or the rebalance protocol did not revoke partitions along the path you expected. Check container lifecycle events and group logs. Do not place business-uniqueness-guaranteeing logic inside a callback that might not run.

### Called commitSync manually yet duplicates still occur

Commits only take effect if they succeed, the offset is right, and the consumer still has commit authority. A crash can occur after the side effect and before the commit. Duplicates can still happen; idempotency at the database or external system is required.

### CommitFailedException spikes suddenly

Check max.poll.interval.ms, long-blocked listeners, retry backoffs, broker/network, and rebalance frequency. Do not increase timeouts indefinitely to hide a stalled listener.

### New consumer processes same event while old consumer has not stopped

Check async tasks still running after onPartitionsLost and missing fencing. Use idempotent side effects, event versions, or lease tokens at the target resource.

### Cooperative rebalance only revokes one partition yet entire cache is wiped

The callback should only clean up state belonging to the supplied partitions. Do not clear global state while other partitions remain assigned.

### Offset advances yet database is missing records

Check whether the listener returns before DB commit, catches and swallows exceptions, or commits/acks too early. This signals business data loss because Kafka progress moved ahead of real progress.

## 25. Monitoring for rebalance and offset commits

Signals to observe:

| Signal | Meaning |
|---|---|
| Rebalance count/rate | Whether the group shifts assignments too frequently |
| Rebalance duration | Processing pause/disruption time |
| Partitions revoked/assigned/lost | Understand actual lifecycle path |
| Commit rate | Frequency of container offset commits |
| Commit latency | Time for broker to confirm commit |
| Commit failure count | Commit errors due to generation/network/coordinator |
| Consumer lag per partition | Partitions falling behind new data |
| Pending acknowledgments | Records completed but not yet committed |
| Listener processing p95/p99 | Risk of exceeding max.poll.interval.ms |
| Async task backlog | Unfinished work on revoke/lost |
| Duplicate event detection count | How much replay idempotency is preventing |
| Shutdown timeout | Whether there is enough time to drain/commit |

Specific metric names depend on Kafka client, Spring Kafka, Micrometer, and exporters; some metrics for pending acknowledgments or partition-local state must be emitted by the application itself.

Structured logs should include:

~~~text
event=kafka_partition_revoked
group=orders-service
topic=orders.events
partition=2
consumer=orders-0
committed_offset=103
pending_ack_count=0
reason=rebalance
~~~

The example only illustrates format; do not record committed_offset=103 as succeeded before the actual callback/commit confirms it. Use states like commit_requested, commit_succeeded, or commit_failed if data is at different stages.

Avoid using arbitrary eventIds/record keys as metric labels with unbounded cardinality.

## 26. Integration testing rebalance windows

Unit tests calling listener methods directly cannot test Kafka group rebalance and commit semantics. Use Testcontainers Kafka or an integrated Kafka environment to test:

| Scenario | What to verify |
|---|---|
| Second consumer joins group | Revoke/assign callbacks and commit of valid progress |
| Graceful stop of one consumer | Completed pending offsets are committed per policy |
| Kill -9 consumer while processing | New consumer redelivers uncommitted records |
| Consumer exceeds max.poll.interval.ms | Partition lost/rebalance, old commit may fail |
| Listener updates DB, has not committed offset | Replay does not duplicate DB side effect |
| Listener submits async then returns | Expose risk of commit before completion |
| Cooperative rebalance revokes subset only | Does not clean up still-assigned partitions |
| Broker commit fails during revoke | Does not record false success |
| Partially processed batch | Does not commit past incomplete records |
| Failed record routed to DLT | Recovery and offset commits consistent per policy |
| Transactional listener aborts on rebalance | Uncommitted outputs invisible to read_committed |
| Rolling deployment of multiple replicas | Graceful shutdown and group stability meet requirements |

In tests, verify **committed group offsets**, Kafka outputs, database state, and side effects; do not check only how many times callbacks were invoked.

## 27. Workflow for designing commit before rebalance

1. Identify for each topic/partition what side effects occur before a record is considered complete.
2. Choose AckMode based on latency, throughput, and recovery needs.
3. Do not report listener success/ack when side effects have only been placed into an in-RAM queue.
4. If partition-local buffers are needed, design durable flushing and an appropriate pre-commit callback.
5. Use ConsumerAwareRebalanceListener for lifecycle; do not manually commit outside the container indiscriminately.
6. Handle revoke by **partition subset** for cooperative rebalance compatibility.
7. Handle lost partitions as already having lost ownership; do not attempt late commits.
8. Design graceful shutdown while still tolerating ungraceful crashes.
9. Ensure eventId/idempotency and fencing for external side effects.
10. With transactional containers, keep Kafka outputs and offsets inside the proper transaction.
11. Monitor commit failures, rebalances, processing latency, and consumer lag.
12. Run fault injection at the point after side effects but before commit, and right when partitions change owners.

## 28. Pre-production checklist

- Consumer group, topic, and partition assignments are clearly observable.
- AckMode matches the moment side effects actually complete.
- Container manages offset commits; no unnecessary overlapping custom commitSync.
- onPartitionsRevokedBeforeCommit handles partition-local state if present.
- onPartitionsRevokedAfterCommit does not assume all external side effects succeeded.
- onPartitionsLost does not try to commit after ownership is lost.
- onPartitionsAssigned properly initializes state for new partitions.
- Callback processing logic is idempotent and does not block indefinitely.
- Cooperative rebalance only cleans up partitions actually revoked.
- Concurrency does not share a single offset variable across multiple partitions.
- Pending async tasks have drain/cancel/fencing lifecycle on revoke/lost.
- Never commit offsets past the contiguously completed record sequence.
- Commit failures are monitored and redelivery is accepted.
- Database/API side effects have idempotency or unique constraints.
- Transactional listeners do not commit offsets outside the Kafka transaction.
- Shutdown grace period is appropriate, yet the system remains safe on abrupt kills.
- max.poll.interval.ms fits listener processing time.
- Monitoring covers rebalances, commit latency/errors, lag, and duplicates.
- Tested group join/leave, rolling deploy, crashes, and lost partitions.

**Conclusion:** Commit before rebalance is the practice of bringing **genuinely safe** processed offsets into a committed state when partitions are revoked normally. The Spring Kafka listener container manages most offset commits according to AckMode and provides ConsumerAwareRebalanceListener so applications can flush/clean up state at the right time. However, partitions can be lost without a commit opportunity, and crashes can happen after side effects before commits. Therefore, proper design must combine **offset discipline, idempotency, partition ownership/fencing, and graceful lifecycle**, rather than merely adding a commitSync call to a rebalance callback.

