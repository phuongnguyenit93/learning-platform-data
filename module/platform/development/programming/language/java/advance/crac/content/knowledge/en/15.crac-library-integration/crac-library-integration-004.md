# In-flight messages, offsets, acknowledgements, and duplicate processing risk

In a Java application using a message broker, a message passes through several different states: the broker has delivered the message to the consumer, the application is processing it, business work has been durably persisted, and the broker has received the acknowledgement or offset commit. These states typically reside in multiple places: partly in the JVM heap, partly in the database, and partly in the broker.

CRaC (Coordinated Restore at Checkpoint) saves the process state at a single point in time. It does not create an atomic transaction spanning the process image, the database, and the broker. If a checkpoint occurs while a message is being processed, the state in the heap may fall out of sync with the delivery state managed by the broker. Upon restore, the message may be redelivered, offsets may have advanced, or an old delivery lease/channel may no longer be valid. This is the root cause of message loss or duplicate processing risks.

A safe design must coordinate three actions: stop accepting new messages and drain in-flight work before the checkpoint; ack/commit only after business outcomes have been durably persisted; and make consumers capable of processing the same message again without creating duplicate side effects.

## 1. What states does a message pass through?

A typical message-processing flow consists of these steps:

```text
Broker holds message
       |
       v
Broker delivers message to consumer
       |
       v
Consumer begins processing
       |
       v
Execute business logic / write to database
       |
       v
Business result is durably committed
       |
       v
Consumer sends ACK or commits offset
       |
       v
Broker records message as processed
```

The key distinction is that **finishing processing in memory** is not equivalent to **business work having committed**, and **sending an ack** does not guarantee the broker has saved the ack if the outcome has not been confirmed per protocol.

| State | Where typically stored | Protected by CRaC checkpoint? |
| --- | --- | --- |
| Message sitting in queue/topic | Broker storage | No; managed independently by the broker. |
| Message delivered but unacked | Broker delivery state and possibly objects in the heap | Consistency between both sides is not guaranteed. |
| Payload/processing state in listener | Heap, thread stack, executor task | May appear in the process image, but does not prove the broker still keeps the same delivery/session. |
| Committed business change | Database transaction log/storage | Protected by the database according to its durability policy, not by the CRaC image. |
| Committed ack/offset | Broker metadata or consumer group state | Managed independently by the broker; does not roll back with the process image. |
| Retry counter or attempt state | Broker, database, or heap depending on design | If only in the heap, it may become stale or out of sync after restore. |

Because state resides across multiple systems, no single checkpoint timestamp automatically turns the entire process into exactly-once processing.

## 2. Why is checkpointing mid-processing dangerous?

Suppose a consumer receives message `M42`. The handler has updated the database but has not yet committed the offset or sent an ack. The process is checkpointed and paused. Meanwhile, the broker may detect that the consumer is no longer polling/heartbeating or that the delivery lease has expired, and redeliver the message to another consumer.

```text
Consumer A                  Database                 Broker
----------                  --------                 ------
Receive M42  ---------------------------------------> Deliver M42
Update business row ------->
                            COMMIT
       |                                             Ack not received
       | checkpoint                                  |
       X                                             v
                                         Consumer A loses lease/session
                                                     |
                                                     v
                                         Deliver M42 to Consumer B
```

Consumer B reprocesses the message even though the database was already updated by A. If the handler is not idempotent, the side effect may occur twice.

The reverse scenario is even more dangerous: the consumer acks the message or commits the offset before the database transaction completes. If the process stops before data is committed, the broker may treat the message as completed and not redeliver it, while business state was never durably stored. This is a message-loss window.

A common principle is to **complete and durably commit side effects first, then acknowledge the message**. This typically establishes at-least-once semantics: a message may be redelivered if the process stops after the database commit but before the ack. Idempotency handles that duplicate window.

## 3. Offsets, acknowledgements, and delivery tags differ

Brokers do not use the same confirmation concept.

| System | Identifier/progress | Confirmation | What to watch out for on restore |
| --- | --- | --- | --- |
| Apache Kafka | Per-partition offset; consumer group stores next offset to read | Commit offset | Broker stores committed offset; old consumer assignment and client state must be recreated/rejoined. |
| RabbitMQ | Per-channel delivery tag for each delivery | `basicAck`, `basicNack`, or `basicReject` | Delivery tags are bound to a channel; old channels cannot be treated as valid after reconnect. |
| JMS | Message delivery and session acknowledgement/transaction | Acknowledge or `Session.commit()` depending on mode | Sessions/connections have separate lifecycles; recreate sessions and let the provider redeliver unconfirmed messages. |
| Amazon SQS | Message receipt handle and visibility timeout | `DeleteMessage` | Receipt handles are bound to a receive attempt; visibility expiration can cause redelivery. |

Do not call all of these mechanisms "offsets". Offset is Kafka's partition reading progress; RabbitMQ uses delivery tags; SQS uses receipt handles; JMS uses session acknowledgements/transactions.

## 4. Kafka: offset commits and duplicate-processing windows

In Kafka, offsets belong to each partition. When a consumer commits offset `N`, the standard meaning is that the consumer has processed records before `N` and the next read starts from offset `N`. Therefore, the committed offset is typically the **next offset**, not the last processed offset.

Example of a partition with records 100, 101, and 102:

```text
Processed records:     100   101
Offset to commit:                    102
Next read:                           starts from 102
```

If the consumer processes in parallel, do not commit a higher offset while an earlier record is still incomplete. Suppose record 100 is still processing while 101 and 102 have finished. Committing offset 103 could cause the consumer group to skip record 100 after a restart. Only commit up to the highest contiguous offset for which all prior records have completed.

### Auto commit and manual commit

With `enable.auto.commit=true`, the consumer may commit progress on a schedule based on polled records while the application is still processing asynchronously. This can advance the offset before business processing finishes.

For handlers needing strict control over side-effect ordering, it is usually advisable to disable auto commit and commit manually after durable processing:

```properties
enable.auto.commit=false
```

Simple sequential processing example:

```java
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;

import java.time.Duration;
import java.util.Map;

ConsumerRecords<String, String> records = consumer.poll(Duration.ofMillis(500));

for (ConsumerRecord<String, String> record : records) {
    processAndCommitBusinessTransaction(record);

    TopicPartition partition = new TopicPartition(record.topic(), record.partition());
    long nextOffset = record.offset() + 1;
    consumer.commitSync(Map.of(partition, new OffsetAndMetadata(nextOffset)));
}
```

The example above illustrates sequential processing order; it is not an optimal template for every consumer and must handle batches, multiple partitions, retries, rebalances, and timeouts in a real application. If one poll returns many records on the same partition, committing after every record can be costly; you can batch-commit the highest contiguous completed offset.

### Parallel processing requires committing by contiguous offset

Suppose a partition has three records:

```text
Offset 200: in progress
Offset 201: completed
Offset 202: completed
```

The safe committed offset remains 200 (the next offset of the record before 200, depending on the initial committed position) until 200 completes. You cannot commit 203 merely because 201 and 202 finished. Once 200 finishes, the consumer can advance the committed offset to 203.

Maintain a per-partition completion tracker and commit contiguous offsets while ensuring only the consumer thread calls the KafkaConsumer API because `KafkaConsumer` is not thread-safe. Worker threads should report outcomes back to the consumer thread rather than calling `commitSync()` directly.

## 5. RabbitMQ: acks are tied to channels and delivery tags

RabbitMQ delivers messages over a channel and assigns a delivery tag for that delivery. The consumer sends `basicAck` to confirm processing. If the channel/connection closes before the broker receives the ack, unconfirmed messages may be returned to the queue and delivered to another consumer.

A crucial point is that delivery tags only have meaning within the channel that delivered the message. After CRaC restore and creating a new channel, do not use an old delivery tag from the heap to ack a new delivery. If the old channel has closed, the broker may reject the ack with an unknown delivery tag error or channel-level exception.

For concurrent processing, the `multiple=true` option on `basicAck` confirms all unacked delivery tags up to the specified tag. Use it only when all messages before that tag have completed. If messages finish out-of-order, multiple-acking can mistakenly confirm a message still being processed. When completion order is not preserved, ack per message or use a completion tracker that guarantees only a contiguous range is acked.

Conceptual example:

```java
void onMessage(Message message, Channel channel, long deliveryTag) throws Exception {
    processAndCommitBusinessTransaction(message);
    channel.basicAck(deliveryTag, false);
}
```

The ack must only be sent after the business transaction commits successfully. If the process stops after committing but before `basicAck`, RabbitMQ may redeliver the message; the handler must be idempotent. If acked before committing and the database transaction fails, the message may be lost from the queue even though business work was not completed.

## 6. JMS and SQS also have duplicate windows

For JMS, semantics depend on the acknowledgement mode and session transactions. In a transacted session, the application typically processes messages and then calls `Session.commit()` to confirm the session's work per provider semantics. If the session rolls back or the connection closes before commit, messages may be redelivered. With `AUTO_ACKNOWLEDGE` and a listener container, the ack timing depends on how the container invokes the listener and confirms outcomes; read the specific configuration rather than inferring from the handler method returning.

For SQS, messages are delivered with a receipt handle and have a visibility timeout. If the handler has not called `DeleteMessage` before the visibility timeout expires, the message may reappear to another consumer. If checkpoint/restore takes longer than the visibility timeout, a message can still be redelivered while the old process image retains processing state. After restore, the old receipt handle may also no longer be valid for the current delivery attempt.

For both JMS and SQS, the general rule remains: do not treat listener object state in the heap as the source of truth for message state at the broker; confirm according to the active protocol and design handlers to tolerate redelivery.

## 7. Why quiesce and drain consumers before checkpointing?

Quiescing means stopping acceptance of new work; draining means waiting for already-accepted work to finish. This step is critical so that a checkpoint does not cut across the boundary between business commit and broker acknowledgement.

A typical workflow:

1. Transition the application to `REFUSING_TRAFFIC` or maintenance mode if consumers can cause system-wide side effects.
2. Stop the listener container or pause consumers so no new deliveries arrive.
3. Continue processing already-received messages and wait for running handlers to complete within a deadline.
4. For completed messages, commit the database transaction and then ack/commit offsets per protocol.
5. For messages incomplete when the deadline expires, safely cancel work and leave messages unacked/uncommitted so the broker can redeliver them.
6. Close the consumer connection/session/channel/client via the library's API.
7. Create the CRaC checkpoint once no old deliveries/sessions need to continue.

For Kafka, `pause()` prevents poll from returning additional records from paused partitions, though the application typically still needs to call `poll()` to maintain group membership while draining. When preparing for a checkpoint, stop the listener/container via framework APIs and then close the consumer; do not suspend a `KafkaConsumer` across a checkpoint expecting assignments and heartbeats to remain valid.

For RabbitMQ, stop consumers and drain handlers before closing the channel. For SQS, stop receiving new messages and either finish work or let visibility timeout/visibility policy handle incomplete messages; do not save old receipt handles to use after restore.

## 8. Consumer groups, rebalances, and assignment state

Kafka consumer groups manage partition assignments and member liveness. When a consumer fails to poll/heartbeat for a sufficient duration, the broker can remove the member from the group and rebalance partitions to other consumers. During the checkpoint period, the process is inactive; therefore, never assume pre-checkpoint assignments still belong to the process after restore.

After restore:

- Create a new Kafka consumer or let the listener container recreate it per framework lifecycle.
- Subscribe to topics/groups using current configuration.
- Wait for the broker to issue new assignments.
- Read the group's committed offsets and resume from the broker-confirmed position.
- Do not treat old assignments, generations, or in-memory poll state as current partition ownership.

Settings such as `max.poll.interval.ms`, `session.timeout.ms`, and heartbeat settings affect when the group evicts a consumer. Increasing timeouts merely to "survive a checkpoint" does not solve consistency for in-flight messages; checkpoint duration can be unpredictably long. Intentionally close/manage the consumer and reinitialize it after restore.

## 9. Ordering business commits and broker acks properly

When the database and broker do not participate in the same distributed transaction, there are two basic orderings:

| Ordering | Failure window | Possible outcome |
| --- | --- | --- |
| Ack/commit offset first, then commit database | Process stops after ack but before DB commit | Broker considers the message done; business changes may be lost. |
| Commit database first, then ack/commit offset | Process stops after DB commit but before ack | Broker redelivers the message; business logic may run a second time. |

The second ordering is usually chosen because duplicates can be handled via idempotency, whereas recovering a message lost after premature acking is much harder. For operations that cannot be safely repeated, a transaction boundary or durable deduplication mechanism is required.

```text
Consumer receives message
       |
       v
BEGIN database transaction
       |
       v
Write business data + inbox/dedup record
       |
       v
COMMIT database transaction
       |
       v
ACK / commit broker offset
```

If the process stops after the database commit but before the ack, the message will be redelivered. The inbox record shows that the message ID has already been processed, allowing the consumer to ack without repeating side effects.

## 10. Idempotent consumers and the inbox pattern

An idempotent consumer is a handler that can receive the same message multiple times while producing a business outcome equivalent to processing it once.

A common approach is storing `message_id` in an inbox table with a unique constraint in the same transaction as the business update:

```sql
CREATE TABLE processed_message (
    message_id VARCHAR(200) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Pseudo-code:

```java
@Transactional
public void handle(Message message) {
    boolean firstDelivery = inboxRepository.insertIfAbsent(message.id());

    if (!firstDelivery) {
        return; // Message was already processed in an earlier transaction.
    }

    applyBusinessChange(message);
}
```

`insertIfAbsent` must rely on a unique constraint or an atomic database operation, not an unsynchronized `SELECT` followed by `INSERT`. If two consumers receive the same message concurrently, the database must guarantee that only one transaction wins inserting the idempotency key.

Ack the message after the transactional method has committed successfully. If the inbox insert and business update are in the same transaction, a processing failure rolls back both; the broker can redeliver and retry later. If the transaction commits but the ack fails, the redelivery sees the inbox record and does not repeat the business update.

Inbox record retention must be long enough relative to how long the broker can redeliver, retry, and replay messages. Deleting records too early can allow a replayed old message to execute side effects a second time.

## 11. Idempotency keys, versioning, and message ordering

Not every message has a reliable unique ID. If the producer does not provide a stable message ID, generate an event ID before publishing and preserve that same ID across retries. Do not generate a new ID for each resend of the same business operation.

For versioned data, conditional updates can provide protection:

```sql
UPDATE account_projection
SET balance = :new_balance,
    version = :incoming_version
WHERE account_id = :account_id
  AND version < :incoming_version;
```

The version condition prevents an older message from overwriting a projection already updated by a newer event. Choose rules matching the event's semantics; not every event can simply be ignored because of a smaller version.

Idempotency also does not automatically guarantee ordering. If messages for the same key/aggregate must be processed sequentially, partition by key, use FIFO groups, or enforce sequence/version checks in the database. When processing concurrently, only ack/commit up to the highest contiguous completed message and preserve necessary business ordering.

## 12. Exactly-once: limits and conditions

"Exactly-once" usually only has meaning within a well-defined scope. Kafka can support transactions to write output records and commit input offsets within the same Kafka transaction for properly configured consume-transform-produce flows. This does not automatically extend to an atomic transaction across databases, email, HTTP APIs, or external systems.

| Case | Common mechanism | Limits |
| --- | --- | --- |
| Kafka consume → transform → Kafka produce | Kafka producer transaction, sending offsets in the same transaction, consumer reading `read_committed` | Transaction scope is Kafka; requires proper fencing and transactional ID configuration/handling. |
| Broker → database | DB inbox/dedup record + business update in one transaction, then ack broker | Broker may redeliver; handler must be idempotent. |
| Database → broker | Transactional outbox + publisher retry | Messages may be published multiple times; consumers need idempotency. |
| Broker → HTTP/payment API | Idempotency key supported by target API or durable workflow | If the target API lacks dedup support, exactly-once cannot be guaranteed at the consumer alone. |

CRaC does not add a distributed transaction across these systems. It only restores the process. When the process image is restored, broker/database state may have progressed beyond the object state in the heap.

## 13. Do not preserve old deliveries/sessions across restore

Client objects typically hold state tied to broker connections and sessions:

- Kafka consumers hold network connections, group membership, generation, assignment, position, and record buffers.
- RabbitMQ channels hold delivery tags and channel sequence state.
- JMS sessions hold acknowledgement/transaction state.
- SQS receipt handles represent a specific receive attempt and can expire.

These states are managed by the broker or protocol. At checkpoint, close/release the client according to the library's instructions and create fresh clients/sessions/channels after restore. Do not reuse old delivery tags, receipt handles, or sessions as if the broker had not changed.

If the library has official CRaC integration, use the lifecycle supported by the library. If writing a custom Resource, verify how to safely close and recreate the client, and avoid simultaneously invoking both library callbacks and custom callbacks doing the same work twice.

## 14. Example Resource coordinating a consumer across CRaC

The example below uses the `MessageConsumerLifecycle` abstraction to show ordering. It is independent of any specific broker:

```java
import org.crac.Context;
import org.crac.Resource;

public final class MessageConsumerCracResource implements Resource {
    private final MessageConsumerLifecycle consumer;
    private final ReadinessController readiness;

    public MessageConsumerCracResource(
            MessageConsumerLifecycle consumer,
            ReadinessController readiness) {
        this.consumer = consumer;
        this.readiness = readiness;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        readiness.refuseTraffic();
        consumer.stopReceivingNewMessages();

        if (!consumer.awaitInFlightToFinish()) {
            throw new IllegalStateException(
                    "Message handlers did not drain before checkpoint");
        }

        consumer.commitCompletedProgress();
        consumer.closeBrokerResources();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        consumer.createFreshBrokerResources();
        consumer.joinOrSubscribe();
        consumer.validateReady();
        readiness.acceptTraffic();
    }
}
```

The methods above are application abstractions and must have finite timeouts/deadlines. `commitCompletedProgress()` only commits messages that are finished and have durable business outcomes. Messages still in progress when the deadline expires must be safely cancelled and left for the broker to redeliver; never mark them complete merely so the checkpoint can proceed.

In Kafka, `createFreshBrokerResources()` creates a new consumer, and `joinOrSubscribe()` subscribes and awaits assignment. In RabbitMQ, it creates a new connection/channel/consumer. In JMS, it creates a new connection/session. In SQS, it creates a new client and receives messages with new receipt handles.

If the checkpoint is aborted after `stopReceivingNewMessages()` has run, the original process must roll back/resume the consumer via the lifecycle coordinator. Do not rely on `afterRestore` to restart consumers when checkpoint creation fails. If safe resumption is not possible, keep readiness rejecting traffic and let orchestration handle the instance.

## 15. Example Kafka consumer with offset control

The following example illustrates disabling auto commit and committing only after a business transaction succeeds:

```java
Properties properties = new Properties();
properties.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, "false");
properties.put(ConsumerConfig.GROUP_ID_CONFIG, "orders-worker");

KafkaConsumer<String, OrderEvent> consumer = new KafkaConsumer<>(properties);
consumer.subscribe(List.of("orders"));

while (running) {
    ConsumerRecords<String, OrderEvent> records =
            consumer.poll(Duration.ofMillis(500));

    for (ConsumerRecord<String, OrderEvent> record : records) {
        processInDatabaseTransaction(record.value());

        TopicPartition partition =
                new TopicPartition(record.topic(), record.partition());
        OffsetAndMetadata next =
                new OffsetAndMetadata(record.offset() + 1);

        consumer.commitSync(Map.of(partition, next));
    }
}
```

This is an illustrative sequential consumer. In a real application, add a shutdown flag, exception handling, commit timeouts, closing the consumer in `finally`, rebalance listeners, and multi-record per-partition management. If using a framework such as Spring Kafka, let the listener container manage the consumer thread and offset policy; the CRaC Resource should stop the container using supported lifecycle APIs rather than invoking consumer methods from another thread.

Do not call `commitAsync()` and treat the method invocation as proof that the broker saved the offset. If a checkpoint must wait for the commit to finish, use a synchronous mechanism or callback/flush with confirmation and an explicit deadline. Likewise, do not commit the offset of an unfinished record merely to reduce redeliveries.

## 16. Retries, dead-letter queues, and attempt counts

A checkpoint can cause an unacked message to be redelivered. Redelivery is not necessarily a producer error; it can be normal behavior under at-least-once delivery.

Retry state should be stored where it can be recovered consistently:

- Broker delivery count/redelivery flags if the broker provides them and semantics are sufficient.
- Retry topics/queues with attempt metadata and next retry time.
- Database records managing workflow/retry state.
- Dead-letter queues (DLQ) for messages exceeding retry policy.

Do not store attempt counters solely in local consumer variables. After restore, a counter in the heap may lag behind the number of times the broker has actually delivered the message or fail to reflect retries by other consumers.

Retries must have bounds, backoff, and error classification. Transient errors such as network timeouts can be retried; invalid payload/schema errors should generally move to a DLQ or quarantine after a defined number of attempts. Avoid unbounded synchronous retries inside a listener because they keep the message in-flight and can prevent checkpoint draining from ever finishing.

## 17. Observability for message processing and checkpoints

To investigate duplicates or lost messages, correlate logs/metrics across the process, broker, and database using a message ID/correlation ID.

Record:

- Message ID, topic/queue, partition, and offset or appropriate delivery tag/receipt metadata.
- Consumer group, consumer instance ID, and assignment generation if provided by the broker.
- Timestamps for receive, processing start/end, database commit, and ack/offset commit.
- Checkpoint attempt ID, quiesce start time, number of running handlers, and drain duration.
- Counts of completed, incomplete, cancelled, and broker-redelivered messages.
- Committed offsets per partition or acknowledgement results per broker.
- Number of duplicates blocked by inbox/idempotency guards.
- Retry counts, DLQ counts, rebalances, and visibility timeout events.
- Readiness state while stopping consumers and after restore.

Do not log sensitive payloads or credentials. For metrics, avoid using message IDs as labels because cardinality can grow unboundedly; use aggregated counters/histograms and place message IDs in structured logs or traces.

## 18. Common errors

| Symptom | Possible cause | Mitigation |
| --- | --- | --- |
| Message processed twice after restore | DB commit succeeded before ack/offset commit; broker redelivery | Use inbox/idempotency records in the same business transaction. |
| Message lost after checkpoint | Ack/offset committed before business transaction committed | Reverse the order: commit durable side effects first, then ack. |
| Kafka skips unprocessed records | Committed offset higher than contiguous completed offset during parallel processing | Track completion per partition and commit only contiguous completed offsets. |
| Kafka consumer rebalances after restore | Consumer stopped polling/heartbeating during checkpoint | Create a new consumer and rejoin the group; do not use old assignments. |
| RabbitMQ reports unknown delivery tag | Acked using an old channel's tag or on a closed channel | Create a new channel and let the broker redeliver unacked deliveries. |
| SQS redelivers message while handler is still running | Visibility timeout expired before delete | Drain before checkpoint or manage bounded visibility extensions; handler must still be idempotent. |
| Message acked despite handler error | Auto ack or improper container ack policy | Choose manual/transactional acknowledgement and verify framework semantics. |
| Consumer drain never finishes | Blocked handler, unbounded retries, or dependency lacking timeouts | Overall deadline, I/O timeouts, and controlled cancellation. |
| Older message overwrites newer state | Out-of-order event processing or replay | Use versioning/sequence numbers and per-aggregate ordering rules. |
| Duplicate causes double payment/double email | Side effect outside DB lacks idempotency | Idempotency keys at the target system or durable workflow/outbox. |

## 19. Testing redelivery and checkpoint–restore

An integration test should deliberately trigger checkpoints at different boundaries:

1. **Before handler begins:** receive a message or prepare a delivery and checkpoint; confirm after restore that the broker delivers a valid message.
2. **While handler is running:** hold the handler with a latch, request a checkpoint, and confirm quiesce/drain waits or cancels at deadline.
3. **After business commit, before ack:** simulate stopping the process; confirm the message is redelivered but inbox/idempotency blocks a second side effect.
4. **After ack/offset commit:** confirm the message is not reprocessed while business state remains durable.
5. **Failure before business commit:** confirm the message is not acked and can be retried.
6. **Kafka parallel processing:** finish a higher offset before a lower offset and confirm the committed offset does not jump past the gap.
7. **Broker session changes:** close channel/session/consumer before checkpoint and confirm restore creates fresh connections/assignments.
8. **Visibility/session timeout:** make the checkpoint exceed the relevant timeout and confirm redelivery is handled idempotently.
9. **Aborted checkpoint:** confirm the consumer safely resumes or the instance remains `NOT_READY`; never leave the listener permanently stopped.
10. **DLQ/retry:** confirm delivery counts and retry policies are not erroneously reset by heap state.

Tests must verify outcomes in all three places: database business state, broker offset/ack state, and application logs/traces. Seeing the handler invoked once in process logs alone does not prove there were no duplicates at the business level.

## 20. Implementation checklist

- [ ] Distinguish offsets, delivery tags, receipt handles, and acknowledgement modes by broker.
- [ ] Clearly identify which messages are delivered, in-progress, business-committed, and acked.
- [ ] Disable auto commit if manual control over offset commit timing is needed.
- [ ] For parallel Kafka processing, commit only the contiguous completed offset per partition.
- [ ] Never ack/commit before durable side effects have completed.
- [ ] Use inbox/deduplication or idempotency keys for consumers with side effects.
- [ ] Stop accepting new messages and drain handlers before checkpointing.
- [ ] Safely cancel messages unfinished at deadline and let the broker redeliver them.
- [ ] Close consumers/channels/sessions before checkpoint via library APIs.
- [ ] After restore, create new clients/sessions and rejoin/re-subscribe with the broker.
- [ ] Never reuse old delivery tags, receipt handles, or assignments.
- [ ] Use outbox/inbox when coordinating a database and a message broker.
- [ ] Configure bounded retries, backoff, and DLQ; do not keep attempt state solely in the heap.
- [ ] Readiness rejects traffic until consumers and dependencies are ready.
- [ ] Include logs/metrics for processing, DB commits, ack/offset commits, redeliveries, and duplicates.
- [ ] Test checkpointing across windows before/after commits and acks.

## 21. Conclusion

In-flight messages, offsets, and acknowledgements belong to systems with distinct lifecycles. CRaC restores process state, while the broker continues managing deliveries, committed offsets, channels/sessions, and visibility timeouts according to its own state. Checkpointing mid-processing can cause messages to be redelivered; if the database has already committed but the broker has not received an ack, the handler will see duplicates. If acked before the database commits, messages can be lost.

Stop receiving new messages, drain handlers, and finish transactions before checkpointing; commit offsets/acks only after side effects are durable; close old clients/sessions and recreate them after restore. Use inbox/idempotency to handle redelivery, outbox for database-driven event publishing, and respect contiguous offsets when processing Kafka concurrently. When these boundaries are explicitly managed, CRaC can shorten process recovery times without weakening message delivery semantics.
