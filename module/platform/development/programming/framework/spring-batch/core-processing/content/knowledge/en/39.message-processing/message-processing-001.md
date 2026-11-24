# ItemReader Reading Messages from a Queue

In Spring Batch, an `ItemReader<T>` can retrieve individual messages from a message queue to feed into chunk processing. The reader receives a message, converts its payload into a Java object, and returns it to the processor and writer. Common systems include JMS queues, RabbitMQ via AMQP, and other messaging platforms.

The challenge with a queue reader is that a message may be marked as received or removed from the queue by the broker before the database chunk commits. If the writer fails after the message has already been acknowledged, data can be lost. Conversely, if a message is redelivered after a rollback or timeout, the writer may receive the same message multiple times. Therefore, you must jointly design how to define batch boundaries, acknowledgement, transactions, idempotency, and restart behavior.

## 1. ItemReader and Message Queues

`ItemReader<T>` is the abstraction that reads one item per call to `read()`:

```java
public interface ItemReader<T> {
    T read() throws Exception;
}
```

The reader returns an item when data is available. When there are no more items in the input for the current run, the reader returns `null`; Spring Batch interprets that as end-of-input and ends the step's reading phase.

With a file or a bounded database query, end-of-input is usually clear. With a continuously active queue, an empty queue at a given moment does not necessarily mean there are no more messages. A new message might arrive right afterward. Therefore, a queue reader needs a rule to determine when the batch ends, such as a registered message count, an end marker, a watermark, or a business-bounded time window for receiving data.

## 2. Pull Readers and Message Listeners

There are two common ways to receive messages:

| Approach | Mechanism | Characteristics |
|---|---|---|
| Pull | The reader actively calls receive/poll from the broker | Suitable when the step controls the pace of reading and chunk processing. |
| Push/listener | The broker/container invokes a listener when a message arrives | Suitable for continuously running consumers; can forward messages into a channel or inbox. |

In the pull model, `ItemReader.read()` waits for a message and returns the payload to Spring Batch. The chunk size determines the maximum number of items collected before the writer runs.

In the listener model, the listener receives messages outside the step's `read()` loop. Messages can be placed into a `BlockingQueue` or a Spring Integration channel for a reader to consume, but you must manage backpressure, acknowledgement, and shutdown. If the listener acknowledges a message upon receipt and only places the payload in an in-memory queue, a step failure can lose messages when the process stops.

An infinitely running queue consumer is usually a better fit for a message-driven service than a single Spring Batch job. Spring Batch is appropriate when you want to process a finite batch with job/step state, checkpoints, reporting, and restartability.

## 3. Defining the Boundary of a Batch

Queues usually do not have a natural ending point. `read()` returning `null` is a signal that the step's input has ended, not a signal that "the queue is currently empty." If the reader uses a short receive timeout and then returns `null`, the step may finish even though the producer is about to send more messages.

Ways to define the scope of a batch:

| Approach | Meaning | Notes |
|---|---|---|
| `maxMessages` | Process at most N messages | Easy to control; must handle the case where a timeout occurs before N messages are reached. |
| End marker | The producer sends an end-of-batch message | Requires a batch ID and processing the marker exactly once. |
| Watermark/sequence | Process up to a finalized sequence or offset | Suitable when the source is ordered and the watermark is reliable. |
| Cutoff time | Process messages belonging to a defined time window | Requires rules for late-arriving messages. |
| Inactivity timeout | End when no messages arrive for a period of time | Use only when the business logic accepts a quiet window as the end. |

If the queue is temporarily empty but the batch has not ended, the reader should keep waiting or report a timeout error according to policy. Do not return `null` just because a single poll yielded no message, unless that timeout itself is the defined batch boundary.

## 4. Example Pull Reader with a Message Count Limit

The following example illustrates a simple reader using `JmsTemplate` to receive payloads from a JMS queue. `maxMessages` defines the number of messages belonging to the batch. If the queue does not provide enough messages within the wait period, the reader throws an exception instead of returning `null` and silently ending the job.

```java
import org.springframework.batch.item.ItemReader;
import org.springframework.jms.core.JmsTemplate;

public class BoundedJmsItemReader<T> implements ItemReader<T> {

    private final JmsTemplate jmsTemplate;
    private final String queueName;
    private final long maxMessages;
    private long readCount;

    public BoundedJmsItemReader(
            JmsTemplate jmsTemplate,
            String queueName,
            long maxMessages) {
        this.jmsTemplate = jmsTemplate;
        this.queueName = queueName;
        this.maxMessages = maxMessages;
    }

    @Override
    @SuppressWarnings("unchecked")
    public T read() {
        if (readCount >= maxMessages) {
            return null;
        }

        Object payload = jmsTemplate.receiveAndConvert(queueName);
        if (payload == null) {
            throw new IllegalStateException(
                    "Queue did not provide the expected message count");
        }

        readCount++;
        return (T) payload;
    }
}
```

The wait duration is configured on `JmsTemplate` (for example, `setReceiveTimeout(...)`). If a receive timeout is enabled, the reader may receive `null` when the wait expires; this code turns that case into an exception because the batch is still expecting `maxMessages`. If no timeout is configured, the receive operation may wait indefinitely and must be accounted for during graceful stop.

This example illustrates pulling and bounding input; it is not a production implementation with checkpoints and safe acknowledgement. In-memory `readCount` is lost on restart, and `receiveAndConvert()` may acknowledge the message depending on the JMS session/acknowledgement mode. Do not use this code as a guarantee that messages will be redelivered if a chunk fails.

In a real application, you must add `ItemStreamReader` if state needs to be persisted, choose an appropriate transaction/acknowledgement mode, and test scenarios where the writer fails after the reader has received a message. The acknowledgement section below explains why persisting `readCount` alone is insufficient.

## 5. Declaring the Reader with @StepScope and JobParameters

The queue name, number of messages to read, or batch ID is often passed when launching the job. You can late-bind them using `@StepScope`:

```java
@Bean
@StepScope
public ItemReader<OrderMessage> orderQueueReader(
        JmsTemplate jmsTemplate,
        @Value("#{jobParameters['queueName']}") String queueName,
        @Value("#{jobParameters['maxMessages']}") Long maxMessages) {

    if (queueName == null || queueName.isBlank()) {
        throw new IllegalArgumentException("queueName is required");
    }
    if (maxMessages == null || maxMessages <= 0) {
        throw new IllegalArgumentException("maxMessages must be positive");
    }

    return new BoundedJmsItemReader<>(jmsTemplate, queueName, maxMessages);
}
```

JobParameters:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("queueName", "orders.queue", true)
        .addLong("maxMessages", 500L, true)
        .addString("batchId", "orders-2026-11-15-01", true)
        .toJobParameters();
```

`@StepScope` creates a target reader for the current `StepExecution`. Identifying parameters help identify the same `JobInstance` upon restart. However, `maxMessages` only specifies the expected count; it does not prove that the broker will redeliver the exact same previous messages after the process stops.

## 6. Acknowledgement Is the Most Critical Part

When a consumer receives a message, the broker needs to know whether the message was processed successfully or must be redelivered. Depending on the technology, this operation is called acknowledgement, offset commit, or delete/complete receipt. The timing of this confirmation determines the risk of losing or doubly processing a message.

Two points in time to distinguish:

- **Ack on receive:** the message is acknowledged immediately after the reader retrieves the payload. If the writer or database transaction fails afterward, the broker may not redeliver the message.
- **Ack after commit:** the message is acknowledged only after the chunk has committed successfully. If the chunk rolls back, the message can be redelivered.

For critical business processing, acknowledging before the target data commits creates the risk of message loss. Acknowledging after commit creates an at-least-once model: a message can be redelivered if the process stops after the database commits but before the ack completes. Therefore, the writer still needs to be idempotent.

```text
Ack too early:
  receive -> ACK -> write database -> error
                           |
                           +--> message already removed from queue
                                but business data has not committed

Ack after commit:
  receive -> write database -> COMMIT -> ACK
                 |
                 +--> rollback: no ACK, broker can redeliver
```

There is no single acknowledgement mode shared across all brokers. You must understand the exact semantics of the JMS provider, RabbitMQ/AMQP, Kafka, or queue service you are using.

## 7. JMS Acknowledgement and Transactions

JMS provides common acknowledgement modes such as `AUTO_ACKNOWLEDGE`, `CLIENT_ACKNOWLEDGE`, and transacted sessions. With `AUTO_ACKNOWLEDGE`, a message may be acknowledged when the receive completes according to the semantics of the JMS provider and the API used. That can happen before the chunk writer commits.

A JMS transacted session can roll back the receive so the broker redelivers the message when the JMS transaction rolls back. However, if the step simultaneously writes to a database via an independent JDBC/JPA transaction manager, the JMS and database transactions are not automatically atomic with each other.

Options:

1. Use JTA/XA with an XA JMS `ConnectionFactory` and an XA database resource if the receive and business write must commit/roll back atomically together.
2. Use manual acknowledgement after the business transaction commits, combined with idempotency to handle redelivery if the ack fails.
3. Receive messages into a durable inbox database table first, and then have Spring Batch read the inbox using a JDBC/JPA reader.

`JmsTransactionManager` manages a local transaction for the JMS resource. It does not automatically coordinate the transaction of another database. Do not use a local JMS transaction manager and a local JPA transaction manager and assume both will commit together.

## 8. AMQP/RabbitMQ Acknowledgement

With an AMQP broker such as RabbitMQ, a consumer can use auto acknowledgement or manual acknowledgement. In manual ack, the application acknowledges delivery after successful processing; if not acked and the channel/connection closes or the message is rejected/requeued per configuration, the broker can redeliver the message.

Key points to understand:

- A delivery tag is a delivery identifier scoped to the channel, not a durable business ID.
- The ack must be sent on the channel associated with the delivery.
- `basicAck` confirms the message; `basicNack`/reject can requeue it or send it to a dead-letter flow depending on configuration.
- Prefetch limits how many messages the broker delivers ahead to the consumer and affects memory/backpressure.
- Auto ack can cause messages to disappear from the queue before the chunk commits.

When using a listener container, you must configure the appropriate acknowledgement mode and transaction settings. With Spring AMQP, mode names are typically expressed via `AcknowledgeMode`; detailed semantics depend on the container and channel transaction configuration. Do not take a delivery tag and ack it on a different channel or thread.

## 9. Ack After Chunk Commit

A manual-ack model can retain delivery metadata within the scope of a chunk and then acknowledge the messages after the business transaction commits. If the chunk rolls back, no ack is sent; messages are requeued/redelivered according to broker configuration.

```text
Chunk starts
    |
    v
Reader receives message (manual ack)
    |
    v
Processor / Writer
    |
    +--> error -> rollback -> no ACK / requeue
    |
    v
Business transaction COMMIT
    |
    v
Chunk after-commit hook
    |
    v
ACK deliveries belonging to the chunk
```

This is a conceptual model. The implementation must retain the proper delivery handle/channel, accurately group the messages belonging to the chunk, and only ack after commit. With RabbitMQ, acknowledgement must use the delivery's exact channel. With JMS, use a transacted session or the acknowledgement API according to the provider's semantics.

Even when acknowledging after commit, there is still a small window: the database has committed, but the application stops before the broker receives the ack. The broker may redeliver the message. Unique constraints or an inbox/idempotency key ensure that reprocessing does not produce duplicate business effects.

## 10. Why a Count Checkpoint Is Not Enough for a Queue

With a file reader, a checkpoint can store a byte offset or record number in an immutable resource. With a database paging reader, a checkpoint can store a key or page position. A destructive-receive queue differs because a message may already have been removed from the ready state by the broker as soon as it is received.

If the reader only stores `readCount = 100` in `ExecutionContext`, upon restart that number will not make the broker resend the 100 already-acknowledged messages. Nor does it identify which messages were committed and which were merely received.

A reliable queue checkpoint must be tied to durable message identifiers or offsets/sequences and the broker's redelivery semantics. For example:

- JMS/AMQP: message ID or application event ID along with acknowledgement transactions.
- Kafka: topic, partition, and offset; offset commits must be coordinated with business writes.
- Database inbox: message ID persisted along with processing status in the database.

Do not use a delivery tag, position in an in-memory queue, or `read()` invocation count as a durable business checkpoint.

## 11. Inbox Pattern: Persisting Queue Messages to a Database Before Batch Processing

An easily controlled pattern is for a consumer to receive messages and persist them into an inbox table first. Spring Batch then uses `JdbcPagingItemReader` or `JdbcCursorItemReader` to read unprocessed rows. Broker acknowledgement happens after the inbox insert is durable; the batch processes the inbox using database transactions.

```text
Message broker
      |
      v
Queue consumer
      |
      v
INSERT inbox_message (message_id, payload, status)
      |
      +--> UNIQUE(message_id) prevents duplicate ingestion
      |
      v
ACK broker after inbox commits
      |
      v
Spring Batch JdbcPagingItemReader
      |
      v
Processor / Writer
      |
      v
UPDATE inbox_message SET status = 'PROCESSED'
```

Illustrative schema:

```sql
CREATE TABLE inbox_message (
    message_id VARCHAR(160) PRIMARY KEY,
    message_type VARCHAR(80) NOT NULL,
    payload JSON NOT NULL,
    status VARCHAR(20) NOT NULL,
    received_at TIMESTAMP NOT NULL,
    processed_at TIMESTAMP NULL
);
```

The unique key prevents the same message from being inserted multiple times if the broker redelivers after the database committed but before the ack reached the broker. Spring Batch only reads messages with `status = 'NEW'` in a stable order. The writer updates the business data and the inbox status in the same database transaction if both reside in the same database.

The inbox pattern decouples message ingestion from batch processing. It creates a durable persistence point that is easier to restart, query, and test than holding unacknowledged messages in a reader's memory.

## 12. Example Reader Reading Messages from an Inbox Table

Once messages are durably persisted in the inbox, the Spring Batch reader can use JDBC paging:

```java
@Bean
public JdbcPagingItemReader<InboxMessage> inboxReader(
        DataSource dataSource,
        PagingQueryProvider queryProvider) {

    return new JdbcPagingItemReaderBuilder<InboxMessage>()
            .name("inboxReader")
            .dataSource(dataSource)
            .queryProvider(queryProvider)
            .parameterValues(Map.of("status", "NEW"))
            .rowMapper(new BeanPropertyRowMapper<>(InboxMessage.class))
            .pageSize(200)
            .saveState(true)
            .build();
}
```

The query provider needs to select the required columns from `inbox_message`, filter by status, and sort by a stable, unique key such as `message_id` or an ascending sequence. `PagingQueryProvider` syntax and how the provider is constructed depend on the database; the example above illustrates wiring the reader to an inbox source.

The writer should update business data and `inbox_message.status` in the same transaction:

```java
UPDATE inbox_message
SET status = 'PROCESSED', processed_at = CURRENT_TIMESTAMP
WHERE message_id = :messageId AND status = 'NEW'
```

In a multi-worker system, messages must be claimed safely so two steps do not process the same row concurrently. You can use a `PROCESSING` status, a lease/lock, `SELECT ... FOR UPDATE SKIP LOCKED` if supported by the database, or non-overlapping partitions. Claiming and status updates must have clear transactions and timeouts.

## 13. Message ID, Correlation ID, and Idempotency Key

A message often carries multiple types of identifiers:

| Identifier | Purpose |
|---|---|
| Message ID | Identifies a specific message in the broker or application. |
| Business key | Identifies the business entity, e.g., `orderId`. |
| Correlation ID | Links multiple messages belonging to the same request or workflow. |
| Batch ID | Groups messages into a processing batch. |
| Delivery tag/receipt handle | Identifies a specific delivery attempt for ack/delete; usually not durable across redelivery. |

For deduplication, prefer a stable application message ID or event ID generated by the producer. Do not use a correlation ID as an idempotency key if one correlation can span multiple distinct messages.

If the producer might resend the same event with a new message ID, you also need a business key/version to recognize the same business operation. If two events share the same order ID but are two valid updates, an event ID or version is required so the newer event is not mistakenly dropped.

## 14. Queues and Delivery Semantics

Brokers typically provide one of the following delivery guarantees:

| Semantics | Meaning | Impact on Batch |
|---|---|---|
| At-most-once | A message is delivered at most once; may be lost on failure | Unsuitable if data loss is unacceptable. |
| At-least-once | A message can be redelivered until acked/committed | Writer must be idempotent and deduplicate. |
| Exactly-once (broker-specific scope) | Broker guarantees certain operations within its supported boundary | Does not automatically cover the database and all external side effects. |

Do not advertise an entire job as exactly-once merely because the broker supports an exactly-once mode within its own scope. If the database commit and broker acknowledgement are not under the same transaction coordinator, there is still a window for replay or data loss.

In practice, at-least-once combined with business keys, unique constraints, inbox/outbox, and an idempotent writer is usually easier to operate than trying to build a distributed transaction across every resource.

## 15. Poison Messages, Retries, and Dead-Letter Queues

A poison message is a message that always fails due to a malformed payload, unsupported schema, or unrecoverable business error. If the broker keeps redelivering this message, the consumer may get stuck on one message and fail to process subsequent messages, depending on ordering and queue configuration.

Mitigations:

- Classify transient errors vs. non-recoverable errors.
- Retry transient errors with limits and backoff.
- After the maximum failure count, reject/dead-letter the message according to broker policy.
- Record the message ID, payload reference, exception, and attempt count for investigation.
- Maintain a procedure to fix data and replay messages from the DLQ.

Do not infinitely retry a JSON parsing error or a missing required field. Nor should you ack a failing message and discard it if the business requires an audit trail. A DLQ or reject table helps retain the message for later handling.

When using Spring Batch, a skip policy can handle errors on items already returned by the reader. However, if a message is redelivered by the broker or the ack fails, the redelivery still needs to be recognized via the message ID. Skip does not replace a DLQ or broker retry policy.

## 16. Backpressure, Prefetch, and Chunk Size

A queue can deliver messages faster than the writer can process them. You need to tune prefetch, consumer count, concurrency, and chunk size so you do not accumulate too many messages in memory or hold unacked messages for too long.

| Parameter | Impact |
|---|---|
| Chunk size | Number of items collected before the writer runs and commits. |
| Prefetch | Number of unacked messages the broker can push ahead to a consumer. |
| Consumer concurrency | Number of threads/consumers receiving messages concurrently. |
| Receive timeout | Time spent waiting for a message; must not be confused with end-of-input if the queue is still open. |
| Transaction timeout | Time limit for holding a transaction/lock while processing a chunk. |

Chunks that are too large can hold many unacked messages, increasing rollback duration and memory usage. Chunks that are too small increase commit/metadata overhead and the number of writer invocations. Measure throughput, latency, redelivery rate, queue depth, unacked count, and transaction duration when tuning.

If message ordering carries business meaning, increasing concurrency or prefetch can cause completion order to differ from receive order. You must use a partition/group key or process sequentially per aggregate if ordering must be preserved.

## 17. Graceful Stop and Shutdown

When a job is requested to stop, the reader should not hold messages indefinitely in memory or acknowledge messages that have not been processed successfully. You need rules for handling in-flight messages:

- Messages in an already-committed chunk: ack according to the chosen mechanism.
- Messages in an uncommitted chunk: roll back and let the broker redeliver/requeue them, or leave them in the inbox in an unprocessed state.
- Messages received but not yet placed into a chunk: do not ack; release/requeue according to broker semantics.
- Running listeners/containers: stop receiving new messages according to the defined shutdown order.

With a pull reader, a finite receive timeout is needed so the job can check the stop signal, but a timeout must not automatically be treated as EOF if the batch has not met its termination condition. You can throw a timeout/retry exception or continue polling up to the batch deadline.

Do not ack all held messages just to shut down quickly. Doing so can turn unprocessed messages into messages permanently lost from the queue.

## 18. How Kafka Differs from Destructive-Receive Queues

Kafka is often used for message processing, but its nature is a distributed log with topics, partitions, and offsets. Consumers read records by offset; committing an offset serves as the consumer group's checkpoint. Messages are not deleted from the log immediately when a consumer reads them.

| JMS/AMQP-style Queue | Kafka |
|---|---|
| Consumers receive and ack/requeue messages | Consumers read records and commit offsets. |
| Redelivery depends on acks and broker queue state | Replay depends on offsets and retention. |
| Messages are typically distributed to one consumer in a queue group | Records are distributed by partition across a consumer group. |
| Delivery tag/session is a detail of a specific delivery | Topic/partition/offset is the log position. |

If using Kafka with Spring Batch, you must coordinate offset commits with business transactions. Committing offsets before the database commits can lose processing; committing the database before committing offsets can lead to replay. An idempotent writer or inbox/deduplication is still required unless the entire transaction is coordinated within a supported boundary.

## 19. Testing a Queue ItemReader

Tests should cover both the reading flow and acknowledgement, not merely verify that the reader returns the right payload.

Key scenarios:

1. **Messages available:** The reader returns payloads in order and of the expected type.
2. **Queue temporarily empty:** The reader does not return `null` prematurely if the batch has not ended.
3. **Batch boundary reached:** The reader returns `null` precisely when the expected message count is reached or a valid end marker is received.
4. **Writer failure:** Messages are not acked and can be redelivered, or inbox records remain in an unprocessed state.
5. **DB commit succeeds, ack fails:** Messages are redelivered, but the idempotent writer produces no duplicate effects.
6. **Job restart:** The same `JobInstance` resumes from durable state rather than relying on an in-memory counter.
7. **Poison message:** Retries are bounded and the message is routed to a DLQ/reject flow.
8. **Shutdown:** Uncommitted messages are not mistakenly acked.
9. **Concurrency:** Multiple consumers do not process the same business key concurrently outside defined policy.
10. **Ordering:** Verify output order if the business requires sequential processing.

For real brokers, integration tests can use Testcontainers or a test broker instance of the same type. Mocking `JmsTemplate`/`AmqpTemplate` is useful for unit testing how the reader converts payloads, but it does not prove the broker's acknowledgement, redelivery, transaction, and DLQ semantics.

## 20. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Returning `null` when the queue is temporarily empty | Spring Batch treats input as finished and stops the step early. | Define a batch boundary; keep waiting or report a timeout. |
| Auto-acking as soon as the reader receives | The writer fails afterward, yet the message is already removed from the queue. | Use manual ack after commit, XA, or the inbox pattern. |
| Storing only the read count in `ExecutionContext` | The broker does not automatically redeliver already-acked messages. | Persist durable message IDs/offsets and coordinate acknowledgement. |
| Acking before the database commits | Messages can be lost when the database transaction rolls back. | Ack after commit or use a transaction coordinator. |
| DB commits then ack fails | The broker redelivers and the writer may run again. | Use an idempotency key, unique constraint, or inbox deduplication. |
| Using a delivery tag as a business key | Tags can change across channels/redeliveries. | Use a stable application message ID or event ID. |
| Infinitely retrying poison messages | The consumer stalls and queue backlog grows. | Limit retries, add backoff, and route to a DLQ. |
| Listener acks then pushes to an in-memory queue | A process crash loses unprocessed messages. | Persist to an inbox before acking or defer ack appropriately. |
| Multiple local transaction managers expected to be atomic | JMS/AMQP and the database can commit independently and diverge. | Use JTA/XA or eventual consistency with outbox/inbox. |
| Prefetch/chunk too large | Many unacked messages, high memory usage, and expensive rollbacks. | Measure load and tune concurrency, prefetch, and chunk size. |

## Conclusion

An `ItemReader` can pull messages from a queue and feed payloads into chunk processing, but queues differ from files and databases in acknowledgement and end-of-input semantics. A temporarily empty queue does not mean the reader should return `null`; you need a batch boundary such as message count, an end marker, or a watermark. Never acknowledge messages before business data is secured, and never assume a JMS/AMQP transaction is automatically atomic with a database transaction. For critical processing, use post-commit acknowledgement combined with idempotency, JTA/XA when atomicity is required, or the inbox pattern to persist messages durably and let Spring Batch read them with a JDBC/JPA reader. Test redelivery, rollback, restart, poison messages, and shutdown against the actual broker to ensure business effects are neither lost nor duplicated.
