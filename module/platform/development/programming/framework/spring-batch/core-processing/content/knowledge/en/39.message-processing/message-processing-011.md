# Preventing Message Loss When the Writer Fails

In Spring Batch, a job can read messages from Kafka, RabbitMQ, JMS, or another message source, process them, and write results to a database or external system. One scenario requiring careful design is **the writer failing after the reader has already received messages**.

If a message is acknowledged, deleted from the queue, or has its offset committed before target data is successfully written, the message can vanish even though the chunk failed. Conversely, if target data commits and the application stops before acknowledging the message, the message may be redelivered and processed twice.

The practical goal is usually **at-least-once delivery combined with idempotent processing**: zero message loss on failure, while allowing redelivery without producing duplicate business effects.

Define clearly:

- How messages are fetched from the broker.
- When acknowledgement, deletion, or offset commit occurs.
- Whether the writer and message source share the same transaction.
- How a writer failure rolls back the chunk and triggers redelivery.
- Which retry, skip, and dead-letter queue policies apply.
- How duplicates are prevented when commit succeeds but ack fails to complete.
- How job restarts recover message positions or offsets.

## 1. What Happens When the Writer Fails?

Suppose a job reads a message requesting an order status update and then writes the status to a database:

~~~text
Message broker
      |
      v
ItemReader receives message M-100
      |
      v
Processor transforms into OrderUpdate
      |
      v
ItemWriter writes to database
      |
      +--> error
~~~

If the reader acknowledged `M-100` immediately upon receiving it, the broker may treat the message as handled. When the writer fails, Spring Batch rolls back the chunk, yet the broker no longer has the message to redeliver.

Result: the message is lost from the pipeline even though the database was never updated.

An alternative is committing the database first in the writer and acknowledging the broker afterward. Then, if the application stops between the two operations, the broker redelivers the message. That produces a duplicate, which can be handled safely via idempotency.

| Order | Failure | Outcome |
|---|---|---|
| Ack message → DB write | Writer fails | Risk of message loss |
| DB commit → Ack message | Process stops before ack | Message may be redelivered |
| DB and broker in one atomic transaction | Transaction rolls back | Both changes are undone if configured properly |

Across most database and broker integrations, end-to-end atomic transactions are not automatic. You must design acknowledgement, transaction coordination, and idempotency around the broker's semantics.

## 2. Distinguishing Inbound vs. Outbound Messages

There are two distinct flows.

**Inbound**: The job receives messages from a broker, processes them, and the writer persists to a database. The primary risk is acknowledging messages too early.

~~~text
Broker -> Reader -> Processor -> Database Writer
~~~

**Outbound**: The job reads from a database/file, processes items, and the writer publishes messages to a broker. The primary risk is the database committing while publishing fails, or publishing succeeding while the database rolls back.

~~~text
Database Reader -> Processor -> Message Broker Writer
~~~

One job can do both. Analyze each boundary independently. Acknowledging inbound messages and publishing outbound messages are two operations with different semantics.

This lesson focuses primarily on inbound messages and writer failures. Near the end, it also covers outbox for safely handling writers that publish messages to a broker.

## 3. Chunk Transactions Do Not Automatically Roll Back the Broker

Spring Batch manages chunk transactions via the `PlatformTransactionManager` configured on the step.

~~~text
Begin chunk transaction
        |
        v
Read messages
        |
        v
Process items
        |
        v
Writer writes chunk
        |
        +--> success
        |
        +--> failure
        |
        v
Commit or rollback
~~~

If the writer throws a rollback-classified exception, the chunk transaction rolls back. Database writers participating in that transaction can be undone.

However, the message broker rolls back with the chunk only if message acknowledgement/offset/receive operations genuinely participate in the same transaction or are driven by an appropriate coordination mechanism.

If the reader already called ack independently before the writer ran, a database rollback cannot restore the already-acked message.

Never assume that sharing the same Spring `ApplicationContext` or the same step means the database and broker share a transaction.

## 4. Early Acknowledgement Causes Message Loss

Consider the unsafe order:

~~~text
1. Consumer receives message M-100
2. Consumer ACKs M-100
3. Spring Batch processes item
4. Writer writes database
5. Writer throws exception
6. Chunk rolls back
~~~

The broker already received the ACK in step 2 and will not resend `M-100`. The database rollback in step 6 cannot ask the broker to restore the message.

This is an acknowledgement design flaw. The reader must keep messages unconfirmed until the chunk completes successfully, or use a transaction mechanism ensuring receive/ack and database writes have consistent semantics.

With visibility-timeout queues, receiving a message usually only hides it temporarily. Deleting the message before database commit carries the same risk as early ACK.

## 5. Post-Commit Ack Can Create Duplicates

A safer order to avoid message loss:

~~~text
1. Consumer receives message M-100
2. Keep message unacked / undeleted
3. Spring Batch processes item
4. Writer writes database
5. Chunk transaction COMMITS
6. Consumer ACKs / deletes message
~~~

If the writer fails in step 4, the chunk rolls back and the message remains unacked. The broker can redeliver the message.

However, there is a failure window:

~~~text
Database COMMIT succeeds
          |
          v
Process crashes before ACK
          |
          v
Broker redelivers M-100
          |
          v
Database receives the same message again
~~~

This is duplicate delivery. With at-least-once processing, duplicates are normal situations that must be handled using idempotency, unique keys, or an inbox/deduplication table.

You cannot eliminate both message loss and duplicates across all crash scenarios merely by changing ack order. To achieve effectively-once business outcomes, you need an appropriate atomic transaction or deduplication of redeliveries.

## 6. At-Most-Once, At-Least-Once, and Exactly-Once

Three concepts describe delivery guarantee levels:

| Guarantee | Behavior | Risk |
|---|---|---|
| At-most-once | Messages are confirmed before or during processing | Messages can be lost |
| At-least-once | Confirmed only after processing; failures can redeliver | Duplicate processing possible |
| Exactly-once | Each message creates business effects strictly once | Requires tight transaction/deduplication coordination |

At-least-once is usually the practical choice for batch integrations. It prioritizes zero data loss and tolerates duplicate deliveries.

A broker's "exactly-once" usually has a specific boundary, such as transactions within the broker itself or read-process-write inside the same ecosystem. It does not automatically guarantee an external database and a broker commit atomically together.

Distinguish:

- Exactly-once delivery: a message is delivered only once, which is hard to guarantee across crashes/network retries.
- Exactly-once effect: a message may be delivered multiple times, yet business effects are applied only once via idempotency/deduplication.

System designs typically target exactly-once effects rather than assuming a message arrives strictly once.

## 7. Retries When the Writer Fails

If an error may be transient, Spring Batch can retry the chunk.

~~~java
@Bean
public Step processMessagesStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<IncomingMessage> reader,
        ItemProcessor<IncomingMessage, OrderUpdate> processor,
        ItemWriter<OrderUpdate> writer) {

    return new StepBuilder("processMessagesStep", jobRepository)
            .<IncomingMessage, OrderUpdate>chunk(
                    100,
                    transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .build();
}
~~~

In the example, transient errors can be retried up to the configured limit. Actual exceptions may be translated or wrapped by Spring; classify according to the exceptions the step actually observes.

When retrying a chunk, the reader/processor/writer may be invoked again per fault-tolerant semantics. The writer must tolerate receiving the same items again, especially if side effects occur outside the transaction.

Retries fit:

- Retryable database deadlocks.
- Transient connection failures.
- Temporarily unavailable brokers or services.
- Throttling/rate limits with clear retry-after signals.

Do not infinitely retry invalid data errors, schema mismatches, authorization failures, or permanent constraint violations that cannot resolve on their own.

## 8. Retries Must Have Backoff and Limits

Continuous retries with no delay can overload the system further when the database or broker is degraded.

A sound policy requires:

- Finite retry limit.
- Increasing backoff.
- Jitter when multiple workers retry simultaneously.
- Per-attempt timeouts.
- Separation of transient vs. permanent errors.
- Metrics by exception type and retry count.

Example backoff configuration:

~~~java
@Bean
public Step processMessagesStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<IncomingMessage> reader,
        ItemWriter<OrderUpdate> writer) {

    ExponentialBackOffPolicy backOff =
            new ExponentialBackOffPolicy();
    backOff.setInitialInterval(500L);
    backOff.setMultiplier(2.0);
    backOff.setMaxInterval(10_000L);

    return new StepBuilder("processMessagesStep", jobRepository)
            .<IncomingMessage, OrderUpdate>chunk(
                    50,
                    transactionManager)
            .reader(reader)
            .writer(writer)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(4)
            .backOffPolicy(backOff)
            .build();
}
~~~

Builder APIs and retry policies can vary by Spring Batch version. Verify your project dependencies and test actual timings.

Backoff does not replace broker visibility timeouts. With SQS or lease-based queues, messages must remain invisible long enough or be renewed during retries.

## 9. Do Not Accidentally Skip Failing Writer Messages

Skip means Spring Batch decides to bypass an item or error per skip policy. If business rules forbid losing messages, an overly broad skip configuration can drop data in a way that is valid to the framework yet wrong for the business.

Example to avoid:

~~~java
.faultTolerant()
.skip(Exception.class)
.skipLimit(1000)
~~~

If the writer fails because the database is unavailable and that exception is skipped, messages can be treated as processed even though no target data was written.

Skip only when the business allows rejecting that record and there is durable persistence for failing data. One option is writing rejected messages to dead-letter storage and ACKing the original message only after saving the rejected record succeeds.

If writing to the DLQ also fails, the original message must remain retained or redelivered. Never mark success merely because you logged the error.

## 10. Dead-Letter Queues for Unprocessable Messages

A poison message is a message that always fails due to invalid data or schema. Infinite retries block queues and waste resources.

~~~text
Main queue
    |
    v
Process message
    |
    +--> success --> ACK
    |
    +--> transient error --> retry / redelivery
    |
    +--> permanent error or limit exceeded
              |
              v
        Publish to DLQ
              |
              v
        Confirm DLQ persistence
              |
              v
        ACK original message
~~~

ACK the original message only after the DLQ has saved the message and required metadata. Metadata should include:

- Original message ID.
- Source topic/queue and partition if applicable.
- Payload or reference to payload.
- Exception class and error code.
- Failure timestamp and attempt count.
- `JobExecution`/`StepExecution` ID.
- Correlation ID and schema version.

DLQs also require retention, alerts, access controls, and replay procedures. A message in a DLQ should not be treated as resolved merely because it left the main queue.

## 11. The Reader Must Preserve Redelivery Capability

An `ItemReader` integrated with a broker must clearly define who owns acknowledgement.

Common models:

1. The reader only reads from a replayable source without committing offsets; the framework or a coordinator commits after the chunk.
2. The reader receives messages in a broker transaction coordinated with the chunk transaction.
3. A listener/container manages acks after the listener or batch unit completes.
4. The reader stores messages/offsets in a staging store first, and the step processes from staging.

Avoid letting the reader ACK immediately inside `read()` before the writer has even run.

If the reader polls multiple messages before returning them one by one, manage buffers and redeliveries carefully. When a chunk rolls back, buffered messages must not be lost simply because the consumer advanced an internal cursor.

For custom readers, specify what `open()`, `read()`, `update()`, and `close()` do with broker state. `ItemStream` checkpoints must align with when broker offsets/acks commit.

## 12. ItemStream and ExecutionContext

Spring Batch uses `ExecutionContext` to save reader/writer state between chunks and support restarts. A reader can store offsets, sequences, or read positions.

Conceptual example:

~~~java
public class CheckpointingMessageReader
        implements ItemStreamReader<IncomingMessage> {

    private long lastReadSequence;

    @Override
    public IncomingMessage read() {
        // Read the next message according to source semantics.
        return null;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong("lastReadSequence", lastReadSequence);
    }

    @Override
    public void open(ExecutionContext context) {
        if (context.containsKey("lastReadSequence")) {
            lastReadSequence =
                    context.getLong("lastReadSequence");
        }
    }
}
~~~

This is an illustrative checkpoint skeleton. A real reader must ensure checkpoints advance only past items belonging to committed chunks, not merely items polled or returned.

If `update(ExecutionContext)` persists a read offset before the chunk commits and the database writer then rolls back, a restart may skip unwritten messages. Therefore, reader state must participate properly in the transaction lifecycle or be designed for safe replay.

Reader names must be stable and `saveState` enabled when the reader supports checkpoints. Do not store large full payloads in `ExecutionContext`; store offsets/IDs or manifest references.

## 13. Offsets and Commits in Kafka

Kafka consumers read records by partition and offset. The offset represents the next position to read in the partition.

If a consumer commits an offset before the database writer commits, a writer failure can cause the record to be skipped when the consumer restarts.

~~~text
poll record offset 42
       |
       v
commit offset 43
       |
       v
database writer fails
       |
       v
restart consumer at offset 43
       |
       v
record 42 is not delivered again
~~~

To prevent losing records, disable auto-commit when the application manages offsets manually and commit offsets only after the corresponding chunk completes successfully. With Spring Batch `KafkaItemReader`, understand how the reader stores offsets in `ExecutionContext` and how the consumer is configured; never assume saving a checkpoint in `JobRepository` means the broker group offset committed.

Kafka consumer configuration typically needs `enable.auto.commit=false` when offsets are managed manually. If using a listener container or another framework integration, follow that container's acknowledgement mode.

## 14. KafkaItemReader and Restarts

Spring Batch provides `KafkaItemReader` in versions supporting Kafka integration. The reader accepts consumer properties, topic/partitions, and can save state for restarts.

Conceptual configuration example:

~~~java
@Bean
@StepScope
public KafkaItemReader<String, String> kafkaItemReader(
        @Value("#{jobParameters['topic']}") String topic) {

    Properties properties = new Properties();
    properties.put(
            ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092");
    properties.put(
            ConsumerConfig.GROUP_ID_CONFIG,
            "batch-order-import");
    properties.put(
            ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
            false);
    properties.put(
            ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);
    properties.put(
            ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);

    return new KafkaItemReaderBuilder<String, String>()
            .name("kafkaOrderReader")
            .consumerProperties(properties)
            .topic(topic)
            .partitions(0, 1)
            .saveState(true)
            .build();
}
~~~

Builder names and methods must match your Spring Batch Kafka module version. This is an illustrative example, not a substitute for real security, deserializer, and partition configuration.

`KafkaItemReader` maintains restart state via `ExecutionContext`. Verify your version's behavior around seek/offsets and whether consumer group offsets are committed. Never enable auto-commit alongside checkpoint management without understanding ordering and consequences.

If offsets must commit strictly after chunk transactions, you may need a custom reader or a listener/container integration designed for acknowledgement timing. Test crashing after writer commit and before offset commit.

## 15. Kafka Transactions Are Not Automatically Atomic with Databases

Kafka transactions can guarantee consuming/producing and committing offsets in one Kafka transaction under appropriate patterns. However, an external database does not automatically join that transaction.

~~~text
Kafka transaction
   +--> produce result event
   +--> send consumed offsets to transaction
   +--> commit Kafka transaction

Database transaction
   +--> update order
   +--> commit database
~~~

When the two transactions are independent, crashing between them still creates an inconsistency window.

Solutions include:

- Outbox: commit database rows and event records in the same DB transaction, then have a publisher send events.
- Inbox/deduplication: store message IDs alongside business updates in the same DB transaction.
- XA/JTA if resources and drivers properly support it and operational complexity is acceptable.
- Idempotent design to reprocess messages safely.

Kafka exactly-once semantics do not automatically cover Spring Batch database commits.

## 16. RabbitMQ Acknowledgement

RabbitMQ consumers usually receive messages and ACK on successful processing. With manual acknowledgement, the application can ACK only after the database chunk commits.

~~~text
RabbitMQ delivers message
        |
        v
Consumer processes message
        |
        v
Database chunk commits
        |
        v
ACK message
~~~

If the writer fails before commit, do not ACK the message. The broker can requeue/redeliver depending on configuration and channel behavior.

If the consumer ACKs before commit, messages can be lost on writer errors. If the database finishes committing and the process stops before ACK, messages can be redelivered.

When using Spring AMQP, understand `AcknowledgeMode`, channel transactions, and transaction synchronization. `AUTO` typically means the container ACKs automatically after the listener finishes normally; it does not mean auto-ack upon message receipt. `MANUAL` lets the application decide exact ACK timing.

Do not call `basicAck` immediately on poll/receive when the chunk has not yet been written successfully. For batch readers, coordinate acks per chunk rather than per `read()`.

## 17. Rabbit Channel Transactions vs. Database Transactions

RabbitMQ has its own transaction/confirm mechanisms for publishing and acknowledgement, but they do not automatically form a shared XA transaction with a database.

Spring AMQP can synchronize channel transactions with an external transaction in certain configurations, yet exact semantics and failure windows depend on the container, `channelTransacted`, and transaction manager.

Test these scenarios:

- Database rollback before channel ACK commits.
- Database commit succeeds while channel commit/ACK fails.
- Connection/channel drops between the two operations.
- Redelivery after restart.
- Multiple messages within one chunk.

Without proven atomic coordination, treat duplicate delivery as possible and use inbox/idempotency.

## 18. JMS Transacted Sessions

With JMS, a transacted session can group receives and acknowledgements/commits within the JMS session transaction. When the session rolls back, received messages can be redelivered per broker semantics.

Example JMS consumer configuration:

~~~java
DefaultMessageListenerContainer container =
        new DefaultMessageListenerContainer();

container.setConnectionFactory(connectionFactory);
container.setDestinationName("orders.in");
container.setSessionTransacted(true);
~~~

This is a container-level example, not direct configuration for a Spring Batch `ItemReader`. When combining JMS receives with database writes, identify which transaction manager governs the JMS session and database.

A local JMS transaction manages only the JMS resource. If the database transaction is another resource, the two are not automatically atomic. Use JTA/XA if broker, database, drivers, and transaction manager support it, or use inbox/outbox/idempotency.

Never assume `sessionTransacted=true` automatically rolls back the database when a database writer fails unless both resources are coordinated in a shared distributed transaction.

## 19. SQS Visibility Timeout and Deletion

Amazon SQS typically delivers a message to a consumer and hides it for a visibility timeout. The consumer must delete the message after successful processing.

~~~text
ReceiveMessage
      |
      v
Message invisible for visibility timeout
      |
      v
Process and write database
      |
      +--> failure: do not delete
      |
      +--> success: delete message
~~~

If the writer fails and the message is not deleted, the message reappears once the visibility timeout expires.

If the database finishes committing but deletion fails, the message can also reappear. Therefore, SQS processing is typically at-least-once and consumers must be idempotent.

If processing exceeds the visibility timeout, the message can be handed to another consumer while the first consumer is still working. Extend visibility timeouts appropriately, while still keeping idempotency because extensions can fail or processes can crash.

## 20. Broker Redelivery and Delivery Counts

Many brokers track delivery attempts or expose equivalent metadata:

- RabbitMQ has a `redelivered` flag and queue delivery/dead-letter behavior.
- JMS has delivery counts and broker-dependent redelivery policies.
- SQS has `ApproximateReceiveCount`.
- Kafka has no built-in queue-style redelivery count; consumers can re-read the same offset when uncommitted.

Use this metadata to observe poison messages and drive DLQ decisions, but do not rely on delivery counts alone to identify messages. Use stable message IDs or business keys.

Avoid configuring infinite redelivery with zero delay because it creates hot loops. Set retry delays, maximum attempts, and DLQ policies per business requirements.

## 21. Inbox Pattern to Prevent Duplicate Processing

The inbox pattern stores processed message IDs in the same database transaction as business updates.

Example table:

~~~sql
CREATE TABLE processed_message (
    message_id VARCHAR(200) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Within the same transaction:

1. Attempt to insert the message ID into `processed_message`.
2. If the insert succeeds, apply the business update.
3. Commit both the inbox record and business update.
4. If the message ID already exists, treat the message as an already-processed duplicate and do not apply the business update again.
5. ACK the message only after the transaction commits.

Pseudocode:

~~~java
@Transactional
public void handle(IncomingMessage message) {
    int inserted = jdbcTemplate.update("""
            INSERT INTO processed_message(message_id, processed_at)
            VALUES (?, CURRENT_TIMESTAMP)
            ON CONFLICT (message_id) DO NOTHING
            """,
            message.messageId());

    if (inserted == 0) {
        return; // Message has already been processed previously.
    }

    orderRepository.apply(message.toOrderUpdate());
}
~~~

`ON CONFLICT` is PostgreSQL-specific; other databases can use `MERGE`, insert-if-absent, or properly handled unique constraint exceptions.

Crucially, the inbox record and business update must commit in the same transaction. If the business update fails, the inbox insert rolls back too so redeliveries can retry.

If the inbox insert commits before the business update, a message can be marked processed even though business data was never saved.

## 22. Using Unique Keys for Idempotency

If a message carries a stable business operation ID, you can place a unique constraint directly on the target table.

~~~sql
CREATE TABLE order_event_result (
    event_id VARCHAR(200) PRIMARY KEY,
    order_id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL
);
~~~

When a message is redelivered, inserting a duplicate `event_id` creates no new result. Depending on business rules, you can ignore duplicates or run conditional upserts.

Do not use a payload hash as a unique identifier if two distinct messages can share identical content as two valid events. Ideally, producers supply unique, immutable message/event IDs.

Idempotency keys must stay stable across retries, redeliveries, and job restarts. Never generate a fresh UUID on every attempt, or the system cannot recognize the same operation.

## 23. Outbox When the Writer Publishes Messages to a Broker

If a Spring Batch writer sends events to a broker after updating a database, do not assume the two operations commit atomically.

Failure example:

~~~text
Database update
      |
      v
DB COMMIT
      |
      v
Publish message
      |
      +--> broker unavailable
~~~

The database changed, yet the message was never published. Reversing the order means the broker could accept the message before the database rolls back.

A transactional outbox solves this by writing business data and the event in the same database transaction:

~~~text
Spring Batch chunk
       |
       +--> Update order
       |
       +--> Insert outbox event
       |
       v
DB COMMIT
       |
       v
Outbox publisher
       |
       v
Broker
~~~

If the chunk rolls back, both the order update and the outbox row roll back. If commit succeeds but the publisher stops, the outbox row persists for re-sending.

The outbox publisher must mark events sent using a durable mechanism. A crash after publishing but before marking `SENT` can cause a resend; consumers should still deduplicate by event ID.

## 24. Outbox Does Not Mean Publish Strictly Once

Outbox ensures events are not lost between database commit and publisher reading, but publishers must generally tolerate resending when unsure whether the broker accepted the message.

~~~text
1. Publisher sends event E-100
2. Broker receives E-100
3. Publisher crashes before marking SENT
4. Publisher restarts
5. E-100 is sent again
~~~

Therefore, outbox usually yields at-least-once publishing. Consumers need idempotency or deduplication.

You can use outbox statuses such as `PENDING`, `IN_PROGRESS`, `SENT` plus leases so multiple publishers do not send the same event concurrently. However, an expired lease after a crash can still resend an event. Stable event IDs remain the foundation for deduplication.

## 25. Transaction Synchronization and After-Commit Callbacks

One option is registering a callback to publish after the transaction commits:

~~~java
TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                messagePublisher.publish(event);
            }
        });
~~~

This avoids publishing before commit, yet does not guarantee zero message loss. If the process crashes after database commit but before the callback executes, the event is never sent and there is no durable record for a publisher to recover.

After-commit callbacks work for signals or secondary actions that can tolerate loss or be retried elsewhere. For critical business events, a durable outbox is usually far more reliable.

Never treat an in-memory callback as a substitute for a durable outbox.

## 26. Message Writer Failing After Sending Part of a Chunk

A writer publishing multiple messages in a chunk can succeed on several messages and fail on the next one.

~~~text
Chunk = [E1, E2, E3, E4]

Publish E1 -> success
Publish E2 -> success
Publish E3 -> failure
Publish E4 -> not attempted
~~~

If the broker does not participate in a rollback-capable transaction, `E1` and `E2` persist. When Spring Batch retries the chunk, `E1` and `E2` may be published again.

You need:

- Stable event IDs per item.
- Producer idempotence or transactions if the broker supports them and the pattern fits.
- Consumer deduplication.
- Per-event publish outcome tracking.
- Never assume `writer.write(chunk)` is atomic merely because it is one Java method call.

If using Kafka producer transactions, design proper transaction boundaries and understand their relationship with chunk/database transactions. For HTTP or non-transactional brokers, outbox is usually easier to recover.

## 27. Writer Exceptions and Chunk Rollbacks

When a writer throws an exception, Spring Batch typically rolls back the chunk transaction per rollback policy. That can prevent reader state/checkpoints from advancing past the failing chunk if reader and repository are configured transactionally.

However, note several exceptions:

- Exceptions classified as `noRollback`.
- Writers catching exceptions and returning normally.
- Side effects occurring outside the transaction.
- Readers that already ACKed messages earlier.
- Checkpoints committed on a different resource.
- Broker offsets auto-committed independently.
- Transaction managers not managing the resource used by the writer.

Do not check only that the step is `FAILED`. Verify messages can still be redelivered or replayed and target data is not lost.

## 28. Never Swallow Exceptions in the Writer

This code is dangerous:

~~~java
public void write(Chunk<? extends OrderUpdate> chunk) {
    try {
        messagePublisher.publish(chunk.getItems());
    } catch (Exception exception) {
        log.error("Publish failed", exception);
        // Return normally.
    }
}
~~~

A composite writer or step may treat the write as successful. The chunk commits and the reader advances its checkpoint, even though messages were never published.

If publishing is mandatory for chunk success, propagate the exception:

~~~java
public void write(Chunk<? extends OrderUpdate> chunk) throws Exception {
    messagePublisher.publish(chunk.getItems());
}
~~~

If transient publish errors should be tolerated, use retries or outbox. If the business allows bypassing, persist a durable `PENDING`/`FAILED` state with a repair workflow.

Logs are not durable message storage.

## 29. Reader and Writer Must Use an Appropriate Transaction Manager

A step accepts only one `PlatformTransactionManager` for the chunk. When the reader receives messages from a broker and the writer writes to a database, establish which resource that transaction manager controls.

Cases:

- `DataSourceTransactionManager`: manages JDBC database transactions.
- `JpaTransactionManager`: manages JPA `EntityManagerFactory`.
- `KafkaTransactionManager`: manages Kafka transactions.
- `JmsTransactionManager`: manages JMS `Session`s.
- `JtaTransactionManager`: can coordinate multiple XA resources when fully configured.

You cannot pass two transaction managers to one chunk and expect Spring Batch to coordinate every resource automatically. If XA/JTA is needed, resources, drivers, broker, and transaction coordinator must all support it; configure recovery logs and operate the transaction manager properly.

Without XA, inbox/outbox or idempotent redelivery is usually simpler and more resilient.

## 30. Separate Transaction Managers Create a Failure Window

Example with independent database and broker transactions:

~~~text
DB transaction begins
      |
      v
DB writer updates order
      |
      v
DB commit
      |
      v
Broker ACK
      |
      +--> error / crash
~~~

If a crash occurs after DB commit but before ACK, the message is redelivered. Inbox deduplication prevents reapplying the business update.

If ACK precedes DB commit:

~~~text
Broker ACK
      |
      v
DB writer update
      |
      +--> error / rollback
~~~

Messages can be lost. Therefore, without coordinated transactions, the priority order is committing business state before ACK and tolerating duplicates.

If DB commits succeed yet broker ACKs fail repeatedly, add monitoring and deduplication. Never try to "fix" it by acking upfront.

## 31. Batch Size and Acknowledgement Granularity

A chunk can contain many messages. If each message is acked immediately when `read()` returns, a chunk rollback cannot redeliver the already-acked messages.

An alternative strategy is acknowledging per chunk after the writer finishes and the transaction commits. That requires retaining the list of delivery tags/receipt handles/offsets corresponding to the chunk.

Keep in mind:

- RabbitMQ delivery tags belong to a channel and must be acked on that exact channel.
- SQS requires the latest receipt handle for the message delivery.
- Kafka offset commits are typically per partition using the next offset, not queue-style per-record acks.
- JMS ack modes/session transactions have distinct semantics.

Large chunk sizes increase pending message counts and the volume needing redelivery on error. Small chunk sizes shrink rollback scope while increasing transaction/ack overhead.

Choose chunk size based on throughput, memory, broker limits, and recovery cost. Never ack per message if transaction semantics require chunk-level acks.

## 32. Visibility Timeouts and Chunk Duration

With SQS or lease/visibility brokers, chunk processing time must fit within the timeout.

If a chunk runs for 10 minutes while the visibility timeout is 2 minutes, messages can reappear before the writer finishes. Another consumer can pick up the same messages and write concurrently.

Mitigations:

- Set visibility timeouts longer than expected processing time with a safety margin.
- Renew visibility during processing if supported by the broker.
- Keep chunk sizes and timeouts aligned.
- Use idempotency to guard against concurrent duplicates.
- Use business-key leases/locks when serialization is required.

Visibility timeouts are not absolute transaction locks. A consumer can lose its lease due to network failures or process pauses.

## 33. Poison Messages and Retry Exhaustion

When a message is invalid or consistently causes writer failures, retry limits eventually run out. Define the next state explicitly.

~~~text
Receive
  |
  v
Attempt processing
  |
  +--> Success: commit then ACK
  |
  +--> Transient failure: rollback, delay, redeliver
  |
  +--> Permanent failure: persist to DLQ/rejected store
  |
  +--> Retry limit reached: quarantine / DLQ
~~~

Do not ACK a message merely because the retry limit expired. First ensure payload and metadata are durably written somewhere queryable and replayable.

If DLQ publishing fails, the original message must still be retained or redelivered. Avoid an unbounded DLQ-to-main retry loop.

## 34. Restarting a Job After a Writer Failure

When a step fails, restarting the same `JobInstance` must preserve identifying `JobParameters` and appropriate reader state.

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("batchId", "orders-20261115-001", true)
        .addString("topic", "orders.in", true)
        .toJobParameters();
~~~

Properties affecting the message set must remain stable:

- Topic/queue or subscription.
- Partition assignment or partition set.
- Starting offset/sequence when using snapshots.
- Batch/window ID.
- Consumer/reader name.
- Schema version and mapping policy.
- Input manifest or message range if applicable.

If a restart uses current consumer group offsets yet offsets were committed independently before chunk commit, the reader may skip messages. Establish the offset source of truth: broker committed offsets, Spring Batch `ExecutionContext`, or a manifest/staging store.

Never change identifying parameters between restarts if you intend to resume the same `JobInstance`.

## 35. Broker Retention and Replay Windows

Leaving a message unacked does not mean every system will keep it forever.

- Queues may enforce message TTLs.
- Kafka topics have time/size-based retention.
- SQS has service-defined maximum retention.
- DLQs have their own retention.
- Messages may be dead-lettered after a redelivery count.

If a job stays broken longer than retention, messages can expire before being reprocessed.

Set retention based on maximum recovery time, DLQ operations, and replay workflows. With Kafka, consumers must re-read from offsets still within retention; if offsets have aged out, recover from archives or original sources.

Never treat a broker as permanent storage unless retention policies actually guarantee it.

## 36. Monitoring to Detect Message-Loss Risks

Monitor both the broker and Spring Batch:

| Metric | Meaning |
|---|---|
| `messages_received` | Number of messages received |
| `messages_acknowledged` | Number of messages ACKed/deleted |
| `records_processed` | Number of items processed successfully |
| `writer_error_count` | Number of writer errors |
| `retry_count` | Number of retries |
| `redelivery_count` | Number of redelivered messages |
| `dlq_count` | Number of messages sent to DLQ |
| `consumer_lag` | Distance between current offset and end offset |
| `queue_depth` | Number of pending messages |
| `oldest_message_age` | Age of oldest message |
| `chunk_rollback_count` | Number of chunk rollbacks |
| `duplicate_detected_count` | Number of deduplicated messages |

Metrics must share consistent time windows and definitions. Never compare total received against total processed when redeliveries occur without counting unique message IDs.

Logs should include message ID, correlation ID, source partition/offset or queue, delivery attempt, `JobExecution` ID, and `StepExecution` ID. Avoid logging full sensitive payloads.

Alert when queue age climbs, consumer lag persists, ACKs rise while business writes drop, DLQs grow, or writer errors repeat continuously.

## 37. Testing Writer Failures and Redelivery

An important integration test:

1. Place message `M-100` into a test broker.
2. Reader receives the message without ACKing.
3. Configure the writer to throw an exception intentionally.
4. Verify the chunk rolls back.
5. Verify the message remains in the broker or is redelivered.
6. Fix the writer to succeed.
7. Rerun and verify the business update commits.
8. Verify the message is ACKed only after commit succeeds.

Do not just mock `ItemReader` and assert the writer was called. Test real broker/consumer acknowledgement or a test harness faithfully modeling the lifecycle.

Use a test container or embedded broker matching production technology. When behavior depends on channels, sessions, or offsets, pure mocks prove nothing.

## 38. Testing Crash After Database Commit Before ACK

This is the most critical duplicate window.

~~~text
1. Receive message M-100
2. DB transaction commits business update + inbox row
3. Intentionally stop process before ACK
4. Restart consumer
5. Broker redelivers M-100
6. Inbox unique key detects duplicate
7. Do not apply business update a second time
8. ACK message
~~~

The test must verify:

- The inbox record exists after the first run.
- The business effect appears only once.
- The message is redelivered.
- The duplicate is recognized via the same message ID.
- The subsequent ACK succeeds.
- The job/consumer creates no extra side effects.

This is concrete proof of exactly-once effect achieved via at-least-once delivery and deduplication.

## 39. Testing Outbox When Publishing Fails

For outbound message writers:

1. Chunk updates business table and inserts outbox event.
2. Database commit succeeds.
3. Make the broker unavailable.
4. Verify the outbox event remains pending.
5. Restore the broker.
6. Publisher sends the event.
7. Simulate crash after publish but before marking `SENT`.
8. Publisher resends the event.
9. Consumer deduplicates by event ID.

Tests must prove events are not lost when publishing fails and duplicates create no duplicate business effects.

Do not check only that the outbox row was inserted. Test retries, leases, crashes, and duplicate publishes too.

## 40. Common Mistakes

### ACKing Directly Inside read()

Messages are confirmed before the writer succeeds. ACK only after chunk commit or use coordinated transactions.

### Using Auto-Commit Offsets When the Writer Can Still Fail

Kafka can skip records whose offsets were committed. Disable auto-commit if managing offsets manually and verify commit timing.

### Assuming Database Rollback Returns Messages to the Queue

The two resources are not automatically atomic. You need coordinated broker transactions, XA if appropriate, or idempotent redelivery.

### ACKing After Commit Without Duplicate Protection

A crash between commit and ACK triggers redelivery. Use an inbox table, unique keys, or idempotency keys.

### Skipping Every Writer Exception

Messages can be dropped even though business updates failed. Skip only when payloads are durably saved to a DLQ/rejected store.

### Retrying Infinitely

Poison messages create hot loops and stall throughput. Use retry limits, backoff, and DLQs.

### Swallowing Exceptions in the Writer

Steps may commit despite failed publishes/writes. Propagate exceptions or persist durable pending states.

### Chunk Acking Per Message Inside read()

A chunk rollback may fail to redeliver already-ACKed messages. Align acknowledgements with chunk semantics.

### Failing to Renew Visibility Timeouts

Messages can be handed to another consumer while the first chunk is still running. Set adequate timeouts and use idempotency.

### Treating ExecutionContext as Proof of Committed Broker Offsets

Local checkpoints and broker committed offsets are two distinct states unless explicitly coordinated. Designate one source of truth.

### Using afterCommit Callbacks Instead of an Outbox

A process crash before the callback loses events. Use a durable outbox for critical messages.

### Assuming Broker Exactly-Once Covers the Database

Guarantees usually apply only inside the broker. Use inbox/outbox or transaction coordination for external systems.

## 41. Zero-Message-Loss Design Checklist

When building a message-processing Spring Batch job, establish:

1. Is the source Kafka, RabbitMQ, JMS, SQS, or another system?
2. When are messages received, ACKed, deleted, or offset-committed?
3. Does the reader acknowledge immediately inside `read()`?
4. Does a writer failure roll back the chunk transaction?
5. Can messages be redelivered after a rollback?
6. Do broker and database share a transaction or run independently?
7. If DB commits yet ACK fails, how are duplicates handled?
8. Are message IDs or idempotency keys stable?
9. Do inbox records commit alongside business updates?
10. Do retry policies have limits and backoff?
11. Does skip durably persist messages to a DLQ before ACK?
12. Do outbound events use a transactional outbox?
13. Do offsets/reader checkpoints advance only past committed chunks?
14. Are visibility timeouts and broker retention long enough?
15. Do restarts preserve the same topic, partition, offset/window, and schema version?
16. Do tests cover writer failures, redeliveries, crash-before-ack, and duplicate handling?

To avoid losing messages when the writer fails, messages must remain redeliverable by the broker until the chunk writes successfully. Without an atomic transaction spanning broker and database, favor at-least-once delivery, commit business data before ACK, persist message IDs in an inbox within the same transaction, and make writers idempotent. For outbound publishing, write business data and outbox events in the same transaction and publish via a retrying worker. Keep retries bounded, ensure DLQs persist durably before ACK, and make restarts restore exact offsets/manifests. That way, writer failures trigger redeliveries without losing data or duplicating business effects.
