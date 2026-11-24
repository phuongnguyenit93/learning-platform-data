# Chunk-Based Acknowledgement

In Spring Batch, when a step reads messages from a broker such as Kafka, RabbitMQ, JMS, or Amazon SQS, the application must decide when to confirm that messages have been processed successfully. This confirmation action is commonly called acknowledgement (ack). With batch processing, a common pattern is processing multiple messages in a chunk and acknowledging the entire group only after business data has committed.

The critical point is that **chunk commit and broker acknowledgement are two separate operations**. A Spring Batch transaction typically commits database changes at the chunk boundary. The broker, meanwhile, has its own ack, offset commit, message deletion, or session commit mechanism. If you ack before the database commits, messages can be lost when the chunk rolls back. If the database commits first but the ack fails, messages can be redelivered and cause duplicate processing.

Therefore, chunk-based acknowledgement must be designed alongside transaction boundaries, redelivery, idempotency, checkpoints, retries, and reconciliation. There is no single ack method that works identically across all brokers.

## 1. What Is Acknowledgement?

A broker retains a message until the consumer confirms processing or until delivery policy determines the message should be discarded. Depending on the broker, acknowledgement can take the form of:

| Broker | Confirmation Action |
| --- | --- |
| JMS | Acknowledge the message or commit a transacted session |
| RabbitMQ | Basic ACK for a delivery tag |
| Kafka | Commit a consumer offset |
| Amazon SQS | Delete the message using a receipt handle |

These operations are not completely equivalent. JMS has acknowledgement modes/session transactions; RabbitMQ acks by delivery tag; Kafka stores the next offset to read; SQS deletes the message from the queue upon receiving its receipt handle.

An ack generally means the consumer has fulfilled its responsibility for processing the message under the system contract. It does not necessarily prove every side effect in all external systems completed atomically.

## 2. Why Ack by Chunk?

Suppose a step processes 100 messages in a chunk:

~~~text
Broker
  |
  v
ItemReader receives 100 messages
  |
  v
Processor validates and transforms
  |
  v
Writer persists business data
  |
  v
Database transaction COMMIT
  |
  v
ACK group of 100 messages
~~~

Acking each message immediately upon reading increases broker round trips and removes messages before the chunk commits. Chunk-based ack reduces confirmation frequency and ties acknowledgement to the outcome of a processing group.

Examples of benefits:

- Reduces offset commits or ack calls when the broker supports group confirmation.
- Confirms messages only after all database operations in the chunk have committed.
- Makes it easier to reconcile counts of received, processed, skipped, and acked messages.
- Allows tuning chunk size to balance throughput, latency, and redelivery scope.

However, larger chunks also mean more messages waiting for ack together. If a chunk fails, the entire group may be redelivered. That increases retry cost and demands stronger idempotency.

## 3. Chunk Transaction and Broker Ack Are Two Boundaries

In a chunk-oriented step, Spring Batch executes one transaction per chunk via the configured transaction manager:

~~~text
BEGIN CHUNK TRANSACTION
    |
    +--> read items
    |
    +--> process items
    |
    +--> write business data
    |
    +--> update Step metadata/checkpoint
    |
COMMIT CHUNK TRANSACTION
    |
    v
ACK broker messages
~~~

This is the desired order when the database stores business outcomes and the broker does not share the same transaction. Ack happens only after the chunk commits successfully.

If ack happens before commit:

~~~text
ACK message
    |
    v
Database write
    |
    v
Chunk rollback
~~~

The broker may not resend the message because it was already confirmed, while the business data does not exist. This creates message-loss risk.

If commit happens before ack:

~~~text
Database COMMIT
    |
    v
ACK message fails
    |
    v
Broker redelivers
    |
    v
Consumer reprocesses message
~~~

This scenario can produce duplicate deliveries, though the data is already committed. That is typically acceptable in an at-least-once system if the writer is idempotent.

## 4. Spring Batch Does Not Automatically Define Ack for Every ItemReader

`ItemReader` defines the contract for reading items; the `ItemReader` interface itself does not define a universal acknowledgement protocol across Kafka, RabbitMQ, JMS, and SQS.

A custom reader or integration module must decide:

- Which API receives messages from the broker?
- Does the broker delete messages on receive or retain them until ack?
- Where are delivery tokens, delivery tags, offsets, or receipt handles stored?
- At what point is ack called?
- What happens when a chunk rolls back?
- How does the broker redeliver messages?
- Can acks be grouped per chunk or only per message?

Do not write a reader that merely calls `receive()` and assume Spring Batch will automatically ack after the writer succeeds. You must clarify the broker library's semantics and transaction configuration.

## 5. Tying Acknowledgement to Chunk Boundaries

When the broker does not participate in the database transaction, one implementation approach is retaining delivery metadata for read messages and acking them in a callback after the chunk commits.

Spring Batch provides `ChunkListener`:

- `beforeChunk` is called before the chunk is processed inside the transaction.
- `afterChunk` is called after the chunk has committed successfully.
- `afterChunkError` is called when chunk processing encounters an error.

A high-level design:

~~~text
beforeChunk
    |
    v
Reader receives message and records delivery token
    |
    v
Processor / Writer
    |
    +--> success: transaction commit
    |                   |
    |                   v
    |              afterChunk
    |                   |
    |                   v
    |              ACK tokens
    |
    +--> error: rollback
                        |
                        v
                 afterChunkError
                        |
                        v
              Do not ACK; let broker redeliver
~~~

Illustrative listener example:

~~~java
public class ChunkAcknowledgementListener
        implements ChunkListener {

    private final ChunkAckManager ackManager;

    public ChunkAcknowledgementListener(ChunkAckManager ackManager) {
        this.ackManager = ackManager;
    }

    @Override
    public void afterChunk(ChunkContext context) {
        ackManager.acknowledgeCommittedChunk();
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        ackManager.releaseForRedelivery();
    }
}
~~~

This is an illustrative structure. `ChunkAckManager` must know exactly which delivery tokens belong to the just-committed chunk, and how release/requeue works depends on the broker. Never store tokens in a static collection or a singleton list shared across `StepExecution`s or workers.

### Why Is afterChunk Suitable?

`afterChunk` runs after the chunk has committed. If a listener acks in `beforeChunk` or inside the writer before the transaction commits, messages can be confirmed even if the database transaction later rolls back.

However, `afterChunk` also creates a window between the database commit and the broker ack. If the process stops during that window, the broker can redeliver messages already processed by the database. Therefore, post-commit ack still requires idempotency.

### afterChunkError Does Not Automatically Guarantee Redelivery

Not acking only means the consumer has not confirmed success. Whether a message is redelivered immediately or later depends on the broker:

- RabbitMQ can requeue on nack/reject or when the channel/connection closes.
- Kafka requires the consumer not to commit the offset and may need to seek/restart from the committed offset.
- SQS messages typically become visible again after the visibility timeout or when visibility is reset to 0.
- JMS depends on transacted sessions, acknowledgement mode, and session recover/rollback.

A listener cannot force redelivery on its own if the reader/broker adapter lacks the corresponding mechanism.

## 6. Managing Delivery Tokens per Chunk

To ack by chunk, the application must associate each read item with its broker token:

| Broker | Metadata to Retain |
| --- | --- |
| RabbitMQ | Channel and delivery tag |
| Kafka | Topic, partition, offset, and consumer/transaction context |
| SQS | Queue URL, message ID, and current receipt handle |
| JMS | Message/session or transaction context per provider |

Not every token can be saved and reused arbitrarily later. For instance, a RabbitMQ delivery tag is scoped to the channel that received the message; using the tag on a different channel is invalid. An SQS receipt handle is tied to a specific receive call; a redelivery can carry a new receipt handle. Kafka offsets must be committed for the right partition and in safe order.

An `AckManager` typically needs to:

- Bind tokens to the current `StepExecution` or chunk.
- Collect tokens as the reader receives items.
- Identify which items belong to the committing chunk.
- Ack the exact tokens after commit.
- Keep state safe upon rollback.
- Handle ack errors and observe redeliveries.
- Avoid sharing state across threads or partitions.

With readers that can prefetch more than the chunk size, distinguish tokens already placed into the current chunk from tokens merely buffered. Never ack messages that have not been processed by the writer or confirmed complete by policy.

## 7. Handling Filtered or Skipped Items

Not every message received by the reader is written by the writer:

- A processor returning `null` means the item was filtered.
- A skip policy may skip an item after a read, process, or write error depending on configuration.
- An item may be written to a reject/DLQ store instead of the main business table.

When the chunk commits successfully, messages handled according to the step's policy can be acked, including filtered items, provided filtering/skipping is an accepted business outcome.

Example:

~~~text
Chunk receives 5 messages:
  M1 -> written to main table
  M2 -> intentionally filtered
  M3 -> written to main table
  M4 -> data error, reject record saved
  M5 -> written to main table

If transaction and reject handling commit successfully:
  Can ACK M1, M2, M3, M4, M5
~~~

If M4 is skipped without storing the raw message anywhere, acking M4 can lose data needed for investigation. Clarify whether skip means valid omission or requires routing to a reject store/DLQ.

If the reject record is written inside the chunk's database transaction, post-commit ack can be safe under at-least-once semantics. If the reject message is published to another broker, that is another external side effect requiring outbox or idempotency.

## 8. JMS Acknowledgement and Chunks

JMS has acknowledgement modes and transacted sessions. Exact behavior depends on how the `Session`, connection factory, listener container, or reader adapter is created.

Common modes:

| Mode | High-Level Meaning |
| --- | --- |
| `AUTO_ACKNOWLEDGE` | Provider automatically acknowledges per session rules after a message is received/handled per API |
| `CLIENT_ACKNOWLEDGE` | Client calls acknowledge on a message; standard JMS semantics may acknowledge all messages consumed by the session |
| `DUPS_OK_ACKNOWLEDGE` | Provider may delay acknowledgement and allow duplicate deliveries |
| `SESSION_TRANSACTED` | Receive and acknowledge are managed via the JMS `Session` transaction; commit confirms, rollback recovers per provider |

### AUTO_ACKNOWLEDGE Can Ack Too Early

If an `ItemReader` calls `receive()` on an `AUTO_ACKNOWLEDGE` session, the message can be acknowledged per provider semantics as soon as the receive completes, before the chunk's processor and writer finish.

If the chunk rolls back afterward, the message may already be confirmed to the broker and will not be redelivered. Therefore, never assume `AUTO_ACKNOWLEDGE` behaves like post-chunk-commit ack.

### CLIENT_ACKNOWLEDGE

`CLIENT_ACKNOWLEDGE` lets the client acknowledge explicitly. However, under JMS semantics, acknowledging one message can confirm all messages consumed by that session up to that point. You must control session boundaries and receive ordering if you intend to ack in groups.

If the reader prefetches messages for the next chunk on the same session, a single acknowledge call can confirm more messages than the items actually committed. That can cause message loss when the subsequent chunk has not completed.

### SESSION_TRANSACTED

A transacted JMS `Session` can coordinate receives and acknowledgements through session commit/rollback. However, for a database writer and JMS session to be atomic together, you need a suitable transaction coordination strategy, typically JTA/XA if both resources support it.

If the JMS session commits separately after the database commit, a duplicate-delivery window remains. If JMS commits before the database commits, message loss remains a risk if the database rolls back.

Never assume a Spring Batch chunk transaction automatically commits a JMS `Session` merely because the reader uses JMS. Verify the actual configured transaction manager and connections/sessions.

## 9. RabbitMQ Chunk-Based Manual Acknowledgement

RabbitMQ manual ack uses channel-scoped delivery tags. The consumer sends `basic.ack` to confirm a delivery.

For single-message ack:

~~~java
channel.basicAck(deliveryTag, false);
~~~

`multiple=false` confirms only the specified delivery tag.

For multi-delivery ack:

~~~java
channel.basicAck(lastDeliveryTag, true);
~~~

`multiple=true` confirms all unacked delivery tags on the same channel up to and including the specified tag.

This is useful when messages are processed sequentially on one channel and every delivery prior to `lastDeliveryTag` has completed.

### Conditions When Using multiple=true

- A delivery tag is meaningful only on the channel that received the message.
- Never ack a delivery that has not been processed successfully.
- Never ack with a last tag if a lower delivery tag is still in flight.
- Never share a channel unsafely across multiple threads.
- Handle channel closure or connection loss before acking.

If multiple workers process messages concurrently, a message with a lower delivery tag might still be in progress while a higher tag finishes. Acking `multiple=true` at the higher tag will confirm the lower message as well, even though it has not finished. In that case, ack per message or maintain a tracker for contiguous completed deliveries.

### Nack and Requeue

When a chunk rolls back, you can use `basic.nack` or `basic.reject` with `requeue=true` to ask the broker to redeliver:

~~~java
channel.basicNack(deliveryTag, false, true);
~~~

Do not infinitely requeue permanently failing messages. They can form a redelivery loop, consuming resources and clogging the queue. Use bounded retries, a dead-letter exchange, or a parking queue per policy.

## 10. Kafka Chunk-Based Offset Commits

Kafka does not ack individual records by delivery tag. Consumers track offsets per topic-partition. Committing offset `N` tells the consumer group that records with offsets less than `N` have been processed per consumer group semantics.

Example for one partition:

~~~text
Partition 0:
  offset 10
  offset 11
  offset 12
  offset 13

Chunk processes 10, 11, 12
DB commit succeeds
Commit offset 13
~~~

The committed offset is the next position to read, not the last processed offset. If a chunk contains offsets 10, 11, and 12, the committed offset is normally 13.

### Disabling Auto-Commit When Coordinating with Chunks

If a consumer automatically commits offsets on a timer, offsets can commit before the database writer finishes. When a chunk rolls back, Kafka may not resend the already-committed records.

With chunk processing, you generally must disable auto-commit and commit offsets only after the chunk commits business data.

### Committing Per Partition

One poll can return records from multiple partitions:

~~~text
Topic orders:
  partition 0: offsets 20, 21
  partition 1: offsets 7, 8, 9
~~~

After the chunk finishes, commit offsets separately per partition:

- partition 0: next offset 22.
- partition 1: next offset 10.

Do not apply a single offset across all partitions.

### Commit Only Contiguous Completed Offsets

If processing concurrently:

~~~text
partition 0:
  offset 20 -> processing
  offset 21 -> completed
  offset 22 -> completed
~~~

Do not commit offset 23 because offset 20 has not finished. Committing offset 23 will cause the consumer group to skip offset 20 after a restart.

Commit only the next offset after a contiguous sequence of successfully processed offsets. If processing concurrently, track completion per partition and never advance past a gap.

### Chunk Commits and Consumer Rebalances

A Kafka consumer can rebalance when heartbeats drop, poll interval is exceeded, or group membership changes. If a partition is revoked while a chunk is running, offset commit may fail or the consumer may no longer own that partition.

The design must:

- Keep chunk processing duration within `max.poll.interval.ms`.
- Manage pause/resume or the poll loop during long processing.
- Handle commit failures and partition revocation.
- Never commit offsets for partitions no longer owned.
- Use an idempotent writer to handle redeliveries after rebalance.

Do not hold one `KafkaConsumer` and call it concurrently from multiple threads; `KafkaConsumer` is not thread-safe. If parallel processing is needed, structure consumer threads and worker handoffs using a supported pattern while tracking contiguous offsets.

## 11. Spring Kafka and Acknowledgement Modes

Spring Kafka provides listener containers and acknowledgement modes. Common modes include:

| Ack Mode | High-Level Meaning |
| --- | --- |
| `RECORD` | Commit offset after the listener finishes each record |
| `BATCH` | Commit offset after all records from one poll batch finish |
| `MANUAL` | Listener calls `acknowledge()` |
| `MANUAL_IMMEDIATE` | Acknowledge may commit immediately depending on thread and configuration |

These modes belong to the Spring Kafka listener container. They do not automatically align with the chunk boundaries of a Spring Batch step.

If a Spring Batch `ItemReader` uses `KafkaConsumer` directly, the reader/adapter must coordinate offsets and chunk commits itself. If using a Spring Kafka listener to feed messages into a job or intermediate queue, ensure the listener acks only after messages are durably handed off to the batch workflow.

Do not assume `AckMode.BATCH` means Spring Batch chunk-based ack. A Kafka poll batch and a Spring Batch chunk can have different sizes, timings, and boundaries.

## 12. Amazon SQS and Chunk-Based Deletion

SQS does not use a RabbitMQ-style ack API. When a consumer receives a message, the message becomes invisible for the visibility timeout duration. To confirm processing, the consumer calls `DeleteMessage` with the receipt handle from the current receive.

Chunk-aligned flow:

~~~text
ReceiveMessage
    |
    v
Retain message ID + receipt handle
    |
    v
Spring Batch processes chunk
    |
    v
Database COMMIT
    |
    v
DeleteMessageBatch for receipt handles
~~~

SQS supports batch deletion with an entry limit per request; the application must split batches to respect API limits and inspect the outcome of each entry. An HTTP request succeeding does not mean every entry was deleted successfully.

### Visibility Timeout

If a chunk takes longer to process than the visibility timeout, messages can become visible again and be received by another consumer before the current chunk finishes.

Solutions:

- Set visibility timeout appropriately for expected processing duration.
- Use `ChangeMessageVisibility` to extend leases when needed.
- Track heartbeats/leases for long-running processing.
- Use idempotency because messages can still be delivered more than once.

A receipt handle can change on each receive. Always delete using the current receipt handle, never a stale handle from an earlier receive.

### Batch Delete Partial Failures

`DeleteMessageBatch` can report success for some entries and failure for others. The ack manager must accurately record which entries were deleted and which need reprocessing. Do not blindly retry the whole batch if retrying deletion might use stale receipt handles or repeat already-succeeded entries.

If the database has committed but some deletes fail, those messages may be redelivered. The writer must be idempotent by message/business ID.

## 13. Transactional Acknowledgement and XA

Some systems can coordinate database and broker transactions via a distributed transaction manager or suitable resource transactions.

Example with two resources:

~~~text
Global transaction
    |
    +--> Database resource
    |
    +--> JMS resource
    |
    v
Coordinator decides commit/rollback
~~~

With XA/JTA, the coordinator orchestrates prepare and commit across resources if the database, broker, drivers, and transaction manager support it. This shrinks the drift window between DB commit and message acknowledgement.

However, XA adds complexity:

- Requires XA datasource/connection factory configuration.
- Requires a transaction coordinator and recovery logs.
- Can hold locks/resources longer.
- Requires recovery operations when a coordinator or node crashes.
- Not all brokers/APIs support XA.

Do not adopt XA solely to avoid writing idempotency. Many systems choose at-least-once with outbox/inbox because it is easier to operate and scale.

## 14. Post-Commit Transaction Synchronization

In some applications, you can register a callback after the current transaction commits to perform the ack:

~~~java
TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                ackManager.acknowledgeCommittedChunk();
            }
        });
~~~

The `afterCommit` callback runs only when the transaction commits successfully. It fits when you want to tie the ack action to the active transaction.

However:

- Ensure the callback is registered inside the right chunk's transaction.
- Do not register duplicate callbacks for the same tokens.
- Distinguish callbacks of one chunk from another.
- Ack failures happen after the DB commit and thus cannot roll back the DB.
- The callback does not replace redelivery mechanisms when a transaction rolls back.

`ChunkListener.afterChunk` is often clearer when acknowledgement is a chunk-level action. Transaction synchronization is useful when binding actions to a specific transaction, but state and exceptions must be managed carefully.

Never throw an exception from a post-commit callback expecting the database transaction to roll back. The transaction already committed before `afterCommit` ran.

## 15. Idempotency When Messages Are Redelivered

With at-least-once delivery, duplicates are normal. Consumers must tolerate the same message being processed multiple times.

Example inbox table:

~~~sql
create table processed_message (
    message_id varchar(200) primary key,
    processed_at timestamp not null
);
~~~

Within the chunk's database transaction:

1. Check or insert `message_id` into `processed_message`.
2. If the ID already exists, treat the message as an already-processed duplicate.
3. If the new insert succeeds, apply business changes.
4. Commit both the marker and business data together.
5. Ack the broker only after commit.

Pseudocode:

~~~java
@Transactional
public void processOnce(MessageRecord message) {
    boolean firstDelivery =
            inboxRepository.insertIfAbsent(message.messageId());

    if (!firstDelivery) {
        return;
    }

    orderService.apply(message);
}
~~~

The insert-if-absent implementation depends on the database—for example, a unique constraint, `insert on conflict`, or equivalent statement. Do not check then insert in two separate transactions without a unique constraint, because two workers could both pass the check.

When the inbox marker commits alongside business data, redeliveries after an ack failure are recognized and produce no second business side effect.

### Business Keys and Message IDs

A message ID should stay stable across redeliveries. If a producer generates a new ID for the same event when retrying a publish, consumers cannot detect duplicates via that ID. When needed, use an event ID or business operation key created once by the producer and kept stable.

Do not use an offset alone as a global idempotency key, because an offset is unique only within one partition. If using Kafka identity, keys should include cluster/topic/partition/offset or a stable event ID.

## 16. Transactional Outbox When Emitting Downstream Messages

If a batch both updates a database and emits an event to another broker, do not rely on a composite writer to make those two operations atomic.

Outbox pattern:

~~~text
Spring Batch chunk transaction
    |
    +--> update business tables
    |
    +--> insert outbox event
    |
    v
COMMIT
    |
    v
Outbox publisher
    |
    v
Broker
~~~

The outbox event and business data commit in the same database transaction. A separate publisher sends events to the broker and marks them sent. If the publisher stops after sending but before marking, the event can be resent; consumers need idempotency.

Outbox prevents losing events between DB commit and publishing, but does not create automatic end-to-end exactly-once delivery.

## 17. Retries, Nack, Redelivery, and Dead-Lettering

Not every error should be handled the same way:

| Error Type | Typically Appropriate Behavior |
| --- | --- |
| Transient database or API error | Bounded retry; do not ack before success |
| Malformed schema or business rule violation | Reject/DLQ or save a reject record |
| Configuration error or missing credentials | Stop processing and alert |
| Ack failure after DB commit | Allow redelivery and handle idempotently |
| Consumer crash mid-chunk | Broker redelivers or message visibility/lease expires |

### Avoiding Poison Message Loops

A permanently failing message that is always requeued can be delivered repeatedly in a tight loop:

~~~text
Receive
  |
  v
Processing fails
  |
  v
Requeue
  |
  v
Receive again
  |
  v
Processing fails ...
~~~

Use retry limits, delivery counts, backoff, and dead-letter queues. A DLQ needs procedures for investigation, data repair, and controlled replay.

Do not ack a failing message and merely log the payload if the data must be reprocessed. If intentionally discarding, record the reject reason and retain the raw message per storage/security policy.

## 18. Chunk Size and Batch Acknowledgement

Chunk size determines how many items are processed in one chunk transaction. If one message corresponds to one item and messages are acked by chunk, chunk size also affects how many messages are acked together.

| Chunk Size | Characteristics |
| --- | --- |
| Small | Frequent commits, fewer redeliveries per failure, more ack calls |
| Large | Fewer commits/acks, potentially higher throughput, but larger rollback/redelivery scope |

Chunk size does not always equal the number of messages the broker receives in a single poll. A reader might prefetch, buffer, or return items from multiple partitions. Track the exact tokens belonging to the chunk.

Factors for choosing chunk size:

- Average and p99 processing time.
- Transaction timeout.
- Visibility timeout or broker lease.
- Kafka `max.poll.interval` and heartbeat.
- Number of messages that may redeliver after a rollback.
- Broker batch ack/delete limits.
- Memory consumed by prefetch and buffers.
- Degree of writer idempotency.

Measure actual throughput and ack latency. Larger chunks are not always faster if transactions hold locks too long or messages time out before processing finishes.

## 19. Ack Batches with API Limits

Some brokers allow confirming only a fixed number of messages per request:

- SQS `DeleteMessageBatch` caps the number of entries per request.
- Some clients/APIs cap batch size or record count.
- RabbitMQ `basic.ack` with `multiple=true` can ack a range of delivery tags on the same channel.
- Kafka offset commit is a map of offsets per partition, not a list of per-record acks.

If a chunk exceeds the API limit, `AckManager` must split it into smaller groups. After each request, inspect per-entry success/failure results.

Do not split a database chunk into multiple transactions solely to match ack limits if that changes business semantics. You can commit the chunk once and then send multiple batched ack/delete requests. If one ack batch fails, others may have succeeded; record the results and rely on idempotency for redelivered items.

## 20. Prefetch and Buffering

A broker client may prefetch multiple messages before Spring Batch requests the next read. Therefore:

~~~text
Broker prefetch: M1 ... M500
Spring Batch chunk size: 100

Chunk 1: M1-M100
Chunk 2: M101-M200
Chunk 3: M201-M300
...
~~~

Do not ack all 500 messages after chunk 1 commits. Ack only the deliveries belonging to the completed chunk.

If the reader buffers across multiple chunks, maintain a structure separating tokens by chunk. When a chunk rolls back, the failed chunk's tokens must be retained for redelivery or reprocessing; tokens from already-committed chunks must not be re-acked in a way that causes errors.

Excessive prefetch can:

- Increase memory usage.
- Increase the number of invisible or unacked messages.
- Increase redeliveries after a consumer crash.
- Make messages wait longer before processing.
- Cause imbalance across consumers.

Set prefetch based on chunk size, concurrency, and processing capacity. Do not pick an arbitrarily huge value to maximize throughput.

## 21. Concurrency and Chunk-Based Ack

When multiple chunks execute concurrently, each chunk must have its own independent token set. Do not use a shared ack list inside a singleton listener if multiple threads can write to it simultaneously.

Flawed design example:

~~~java
private final List<DeliveryToken> allTokens = new ArrayList<>();
~~~

Multiple threads can add/remove tokens concurrently; one chunk's listener could ack another chunk's tokens.

Management options:

- One `AckManager` instance per `StepExecution`/partition.
- A chunk-scoped context if the framework and design permit.
- A thread-bound accumulator properly cleaned up on commit/rollback.
- Token batches passed explicitly via wrapper items, then grouped by chunk in the writer/ack coordinator.

With Kafka, offset commits must preserve contiguity per partition. With RabbitMQ, multiple acks must preserve delivery order on the same channel. With SQS, each receipt handle is handled individually and batch deletion may return partial failures.

Do not assume every broker allows acking completed messages out of order.

## 22. Restarts and Broker Offsets/Checkpoints

Spring Batch `ExecutionContext` stores reader/writer checkpoints. The broker stores acknowledgement state separately. These two checkpoint systems do not synchronize automatically without a shared integration transaction.

Example:

~~~text
Database/Batch:
  Chunk 1 commit
  Chunk 2 commit

Broker:
  Chunk 1 ack succeeded
  Chunk 2 ack not yet succeeded
~~~

After a process restart, the broker may redeliver messages from chunk 2. Spring Batch may restart the same `JobInstance` from the checkpoint after chunk 2 or from the saved reader checkpoint. If the reader and broker offsets are not coordinated, avoid skipping or doubly processing messages.

### Choosing One Source of Truth for Progress

Common models:

1. **Broker offset as primary checkpoint:** the reader resumes from the committed offset; the DB writer is idempotent to tolerate duplicates when DB commits before offset commit.
2. **Spring Batch `ExecutionContext` as primary checkpoint:** the reader saves position/ID in the context and resumes from the checkpoint; broker ack happens only after commit.
3. **Inbox table as business checkpoint:** message IDs are persisted alongside business data; the broker can redeliver and consumers detect duplicates.

Do not let two independent checkpoints advance in separate directions without a reconciliation mechanism.

### Job Restart Does Not Automatically Reset Consumer Offsets

Restarting a `JobInstance` may not reset a Kafka consumer group offset or queue state. If you want to replay from the beginning, use an explicit replay policy such as a new consumer group, controlled offset seek, or a new batch ID.

Never manually advance and commit an offset to skip messages merely because a Spring Batch step failed.

## 23. Monitoring Chunk-Based Acknowledgement

To operate message batching reliably, track at least:

- Messages received from the broker.
- Items processed by the processor.
- Filtered items.
- Skipped/rejected items.
- Items written successfully.
- Messages acked/committed/deleted.
- Ack failures and retries.
- Redeliveries/duplicates.
- Unacked or invisible messages.
- Consumer lag and committed offsets per partition.
- Time from receive to ack.
- Chunk rollbacks and retry counts.
- DLQ depth and age of oldest message.

Counts must be clearly defined. For example, items read do not necessarily equal records written due to filtering/skipping. Successful acks may differ from read messages due to partial failures in batch ack.

Use correlation keys such as `batchId`, `JobExecution` ID, message ID, and partition/offset for reconciliation. Avoid logging entire sensitive payloads.

## 24. Testing Chunk-Based Acknowledgement

Unit tests should verify `AckManager` and the listener:

- Ack is called only after the successful commit callback.
- No ack occurs in `beforeChunk`.
- Failed chunks do not ack tokens.
- Each token is confirmed strictly per policy.
- Tokens from other chunks are not mistakenly acked.
- Ack failures are recorded and not hidden.
- Batch acks split according to API limits.
- Partial successes retry only the necessary entries.

Example listener test:

~~~java
@Test
void acknowledgesOnlyAfterChunkCommit() {
    ChunkAckManager manager = mock(ChunkAckManager.class);
    ChunkAcknowledgementListener listener =
            new ChunkAcknowledgementListener(manager);

    listener.afterChunk(mock(ChunkContext.class));

    verify(manager).acknowledgeCommittedChunk();
}

@Test
void doesNotAcknowledgeFailedChunk() {
    ChunkAckManager manager = mock(ChunkAckManager.class);
    ChunkAcknowledgementListener listener =
            new ChunkAcknowledgementListener(manager);

    listener.afterChunkError(mock(ChunkContext.class));

    verify(manager).releaseForRedelivery();
    verify(manager, never()).acknowledgeCommittedChunk();
}
~~~

This is a callback unit test; it does not prove the callback actually runs after a database commit or that broker redelivery works. Those behaviors require integration tests.

### Integration Tests with a Database

1. Use a real test database and transaction manager.
2. Have the writer write several rows in a chunk.
3. Use a fake `AckManager` to record acks.
4. Trigger an error so the chunk rolls back.
5. Verify the database contains none of the chunk's rows.
6. Verify no successful ack occurred.
7. Rerun the chunk and verify ack happens only after commit.

### Integration Tests with a Broker

With a real broker or suitable test container:

- Send a batch of messages.
- Run the chunk-processing step.
- Verify database commit and message ack.
- Trigger an error before commit and verify messages are redelivered.
- Trigger an ack failure after commit and verify redelivery causes no duplicate business effects.
- Verify visibility timeout, requeue, offset commit, or DLQ per broker.

Do not use a mock broker to draw conclusions about delivery tag semantics, session transactions, consumer rebalances, or SQS receipt handles.

## 25. Common Mistakes

### Acking Immediately When the Reader Receives a Message

The chunk may roll back afterward while the message is already confirmed. Ack only after successful processing or use coordinated broker/database transactions.

### Acking Before the Database Commits

Messages can be lost if the database rolls back. Place acks after commit in an at-least-once model.

### Assuming Post-Commit Ack Cannot Produce Duplicates

The process can stop between DB commit and ack. The broker redelivers; the writer needs idempotency.

### Using AUTO_ACKNOWLEDGE While Thinking Ack Is Chunk-Based

JMS auto acknowledgement can occur at the receive boundary. Inspect the session mode and reader adapter.

### Acknowledging JMS CLIENT_ACKNOWLEDGE on a Session with Prefetch

One acknowledge call can confirm multiple messages consumed by the session. Never ack while messages for the next chunk remain unprocessed.

### RabbitMQ Multiple Ack Crossing Incomplete Deliveries

Acking a high tag with `multiple=true` can confirm lower unprocessed tags. Only ack a contiguous completed range on the same channel.

### Committing Kafka Offsets Without Respecting Partitions

Offsets are per partition. Committing a higher offset when a gap remains can lose unprocessed records.

### Confusing a Kafka Poll Batch with a Spring Batch Chunk

The two boundaries can differ. Acks/commits must tie to committed chunks, not just returned polls.

### Using a Stale SQS Receipt Handle

Receipt handles change across receives. Delete using the handle from the current receive.

### Ignoring Partial Failures in Batch Delete

Some entries may delete successfully while others fail. Track outcomes per entry.

### Neglecting Visibility Timeouts

Messages can be handed to another consumer while a chunk is still processing. Extend visibility and use idempotency.

### Sharing a Token List Across Threads

One chunk may ack another chunk's tokens. Isolate state per execution/partition/chunk.

### Acking Skipped Messages Without Saving Rejects

Failing data can vanish. Persist rejects/DLQ entries durably before acking.

### Assuming Spring Batch Automatically Acks Every Broker

`ItemReader` has no universal acknowledgement contract. You must design adapters and transaction integration per broker.

## 26. Chunk-Based Acknowledgement Design Checklist

Before implementing, answer:

1. Which broker supplies the messages, and what is its corresponding ack API?
2. Does receive automatically acknowledge or delete messages?
3. Do chunk size and broker batch/poll size differ?
4. Which delivery tokens must be retained per item?
5. Which callback performs the ack after the transaction commits?
6. When a chunk rolls back, will the broker requeue, redeliver, recover the session, or let visibility timeout expire?
7. Does an ack failure after DB commit trigger redelivery?
8. Is the writer idempotent by message ID/business key?
9. Are filtered/skipped messages treated as complete or routed to reject/DLQ?
10. For Kafka, are offsets tracked per partition and committed only across contiguous ranges?
11. For RabbitMQ, are channels and delivery tags used within the right scope?
12. For JMS, is the acknowledgement mode/session transaction suitable?
13. For SQS, how are receipt handles and visibility timeouts managed?
14. Can prefetch/buffers hold messages belonging to the next chunk?
15. Is ack state isolated per thread/partition?
16. Do restarts use broker offsets, Batch `ExecutionContext`, or an inbox table as the source of progress?
17. Are outbox/inbox or XA needed when coordinating multiple resources?
18. Does monitoring reconcile received, processed, committed, acked, and redelivered counts?

An at-least-once model that is usually straightforward to operate is: receive messages, process and write data along with an inbox marker inside the chunk transaction, commit the database, and then ack the broker. If the ack fails, messages are redelivered, but the inbox marker prevents duplicate business side effects. For systems requiring atomicity between broker and database, evaluate XA or broker-specific transaction integration; never assume a chunk transaction provides it automatically.

## Conclusion

Chunk-based acknowledgement ties message confirmation to the commit outcome of a group of items in Spring Batch. In an at-least-once model, commit business data first and ack afterward; if ack fails, accept redelivery and use an inbox/unique key to process idempotently. When a chunk rolls back, do not ack and ensure the broker can redeliver messages via requeue, session rollback, uncommitted offsets, or visibility timeouts. Semantics vary across JMS, RabbitMQ, Kafka, and SQS: pay special attention to JMS acknowledgement modes, RabbitMQ delivery tags/channels, contiguous per-partition Kafka offsets, and SQS receipt handles/visibility timeouts. Separate poll/prefetch from chunk boundaries, isolate tokens per chunk/partition, handle filter/skip/DLQ explicitly, and test both callbacks and broker/database integration. Chunk commits and broker acks are atomic only when real transaction coordination is configured; otherwise, design for duplicates and restarts.
