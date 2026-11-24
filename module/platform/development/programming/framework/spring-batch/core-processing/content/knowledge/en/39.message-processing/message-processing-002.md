# ItemWriter Sending Messages

In Spring Batch, `ItemWriter<T>` is commonly used to write items to a database or file. However, a step can also send items to other systems via a message broker such as Apache Kafka, a JMS provider, or RabbitMQ. In that setup, the writer acts as a producer: transforming processed items into messages, attaching required keys/headers, and sending them to the appropriate destination.

For example, a job reads orders from a database, runs business validation, and emits `OrderCreated` events so payment, inventory, and notification services can continue processing. `ItemWriter` is a natural integration point because Spring Batch invokes the writer chunk by chunk, allowing multiple items to be batched before sending.

Sending messages in batch introduces a key design consideration: the chunk transaction and the broker's receipt of messages may belong to two separate systems. A database rollback does not automatically revoke messages the broker has already accepted; conversely, a broker commit does not guarantee the database transaction committed. Therefore, you must define delivery guarantees, acknowledgement, retries, idempotency, and failure handling between the two systems.

## What Is a Message-Sending ItemWriter?

`ItemWriter<T>` is the interface for writing a chunk of items. In Spring Batch 5, its primary signature is:

```java
public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
```

The writer receives a `Chunk` rather than individual items one by one. An implementation can iterate through the items, convert them into messages, and send them to the broker. If an unrecoverable error occurs, the writer should throw an exception so the step applies its configured transaction, retry, or skip policy.

Typical processing flow:

```text
ItemReader
    |
    v
ItemProcessor
    |
    v
Chunk<OrderEvent>
    |
    v
Message ItemWriter
    |
    +--> serialize payload
    +--> build key / headers
    +--> send message
    +--> wait for acknowledgement per policy
    |
    v
Kafka / JMS / RabbitMQ broker
    |
    v
Consumer services
```

The writer is responsible for converting items into messages and determining when the send operation counts as successful for the step. The broker is responsible for receiving/storing/forwarding according to its configuration. Consumers are responsible for processing messages and acknowledging according to protocol semantics.

## Why Send Messages in ItemWriter?

Placing message sending inside the writer offers several benefits:

- Leverages chunk processing to group multiple items within a single writer invocation.
- Shares the step's lifecycle, transaction boundaries, retry, and skip behavior.
- Separates reading, transformation, and output logic.
- Can publish messages from output already validated/enriched by the processor.
- Makes the writer easy to unit test independently and the whole job easy to integration test.

However, a writer does not automatically make the message broker part of the database transaction. If a message is sent successfully and the chunk then rolls back, the message may still be visible to consumers. If the writer sends messages asynchronously and returns before the broker confirms, the step may commit the chunk while the message later fails.

Therefore, the writer needs a clear contract: when it returns, which acknowledgement is considered sufficient, and how send errors are propagated up to Spring Batch.

## Designing Payloads Before Sending

Avoid sending JPA entities or internal objects with many lazy relationships directly. Create a stable message contract containing only the data consumers need.

Example:

```java
public record OrderCreatedEvent(
        String eventId,
        String orderId,
        String customerId,
        BigDecimal amount,
        String currency,
        Instant occurredAt,
        int schemaVersion) {
}
```

`eventId` is used for deduplication; `schemaVersion` tells consumers how to interpret the payload; `occurredAt` is when the event happened; `orderId` is the business identifier. In real systems, you may also need tenant, correlation ID, trace ID, or event source.

A message contract should:

- Have clear, stable field names.
- Use data types with consistent semantics between producer and consumer.
- Have versioning or schema compatibility rules.
- Avoid containing secrets, unnecessary sensitive data, or an entire entity graph.
- Avoid depending on internal Java class names if multiple languages consume it.
- Carry a unique ID to support idempotency and tracing.

### Events vs. Commands

An event describes something that has happened, such as `OrderCreated`. A command instructs a system to perform an action, such as `ReserveInventory`. Events are typically broadcast to multiple consumers and should not be interpreted as a request that overwrites source state. Commands usually have a specific recipient and processing rules.

Naming messages according to their business meaning helps consumers understand the right semantics and avoids coupling to the batch job's implementation.

## Converting Items to Messages

Payload construction can be separated from the writer using a mapper:

```java
@FunctionalInterface
public interface MessageMapper<I, M> {
    M toMessage(I item);
}
```

The writer only coordinates conversion and sending:

```java
public class MessageItemWriter<I, M> implements ItemWriter<I> {

    private final MessageMapper<I, M> mapper;
    private final MessageSender<M> sender;

    public MessageItemWriter(
            MessageMapper<I, M> mapper,
            MessageSender<M> sender) {
        this.mapper = mapper;
        this.sender = sender;
    }

    @Override
    public void write(Chunk<? extends I> chunk) throws Exception {
        for (I item : chunk) {
            M message = mapper.toMessage(item);
            sender.send(message);
        }
    }
}
```

`MessageSender` is an application-defined abstraction:

```java
@FunctionalInterface
public interface MessageSender<M> {
    void send(M message) throws Exception;
}
```

Separating the mapper and sender allows unit testing without a real broker. In production, the sender can be implemented using `KafkaTemplate`, `JmsTemplate`, `RabbitTemplate`, or the corresponding client.

For large batches, the writer can send using the broker's batch API instead of calling once per item. Either way, you must wait for the send result according to the chosen policy before the writer reports success if broker errors should affect the current chunk.

## Sending Messages to Kafka

Spring for Apache Kafka provides `KafkaTemplate<K, V>` to send records to Kafka. A record typically consists of a topic, key, value, and optionally headers. The key plays an important role because Kafka uses it to select the partition via the default partitioner, which in turn affects ordering of records with the same key.

Example writer for Spring Kafka 3.x, where `KafkaTemplate.send(...)` returns a `CompletableFuture`:

```java
public class KafkaOrderWriter implements ItemWriter<OrderCreatedEvent> {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;
    private final String topic;

    public KafkaOrderWriter(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate,
            String topic) {
        this.kafkaTemplate = kafkaTemplate;
        this.topic = topic;
    }

    @Override
    public void write(Chunk<? extends OrderCreatedEvent> chunk)
            throws Exception {

        List<CompletableFuture<SendResult<String, OrderCreatedEvent>>> sends =
                new ArrayList<>();

        for (OrderCreatedEvent event : chunk) {
            sends.add(kafkaTemplate.send(
                    topic,
                    event.orderId(),
                    event));
        }

        for (CompletableFuture<SendResult<String, OrderCreatedEvent>> send : sends) {
            send.get(30, TimeUnit.SECONDS);
        }
    }
}
```

The example uses `orderId` as the key so events for the same order are typically routed to the same partition. `get(timeout)` waits for the future to complete and surfaces send errors to the writer. The timeout must match the SLA and broker configuration; do not pick an arbitrarily short timeout that causes the batch to fail when the broker is merely slow.

Older versions of Spring Kafka may use `ListenableFuture` instead of `CompletableFuture`; adapt the code to your dependency version. Do not blindly copy Spring Kafka 3.x future types into an application running an older version.

### Choosing Keys and Partitions

Kafka guarantees ordering within a partition, not global ordering across partitions. If events for the same aggregate must arrive in order, the aggregate/business ID is typically used as the key.

Example:

```java
kafkaTemplate.send("order-events", event.orderId(), event);
```

If you use a random key or a null key, events for the same order may go to different partitions and consumers cannot rely on per-order ordering. The key also affects load distribution; an overly hot key can create a hot partition.

### Producer Acknowledgement

The future completes with the producer/broker result, but actual durability depends on the Kafka producer and cluster configuration. Important settings include:

- `acks`: acknowledgement level the producer requires from the broker.
- `enable.idempotence`: enables producer idempotence within the semantics Kafka provides.
- `retries`: number of times the producer retries recoverable send errors.
- `delivery.timeout.ms`: maximum time allowed for a record to be successfully sent per producer policy.
- Replication factor and `min.insync.replicas`: affect how widely data is accepted by replicas.

`acks=all` with appropriate replication/min-ISR typically increases durability compared to `acks=0` or `acks=1`, but does not automatically create exactly-once between a database transaction and Kafka. Producer idempotence reduces duplicates caused by internal producer retries; it does not replace event IDs and consumer-side idempotency when a batch job resends after a restart.

### Wait for Futures or Send Asynchronously?

If the writer calls `send()` and returns immediately, Spring Batch may commit the chunk before the producer future completes. When the future fails later, the step no longer knows which chunk needs to roll back or retry.

Options:

- Wait for all futures to complete before `write()` returns.
- Use a producer transaction managed appropriately alongside the chunk.
- Send asynchronously but have a flush/await mechanism that surfaces errors to the writer before commit.

Do not ignore futures or swallow exceptions in callbacks. If throughput requires it, you can send concurrently within a chunk and then await all futures; bound concurrency and handle timeouts/exceptions intentionally.

## Sending Messages to JMS

For JMS, Spring provides `JmsTemplate` to send messages to a queue or topic. You can use `convertAndSend` to convert an object into a message via a `MessageConverter`.

Example custom writer:

```java
public class JmsOrderWriter implements ItemWriter<OrderCreatedEvent> {

    private final JmsTemplate jmsTemplate;
    private final String destination;

    public JmsOrderWriter(JmsTemplate jmsTemplate, String destination) {
        this.jmsTemplate = jmsTemplate;
        this.destination = destination;
    }

    @Override
    public void write(Chunk<? extends OrderCreatedEvent> chunk) {
        for (OrderCreatedEvent event : chunk) {
            jmsTemplate.convertAndSend(destination, event, message -> {
                message.setStringProperty("eventId", event.eventId());
                message.setStringProperty("eventType", "OrderCreated");
                return message;
            });
        }
    }
}
```

`MessageConverter` must be configured to serialize payloads according to contract, such as JSON. The destination can be a queue or topic depending on system semantics. Headers/properties are used for routing, correlation, or tracing; do not cram all metadata into the body when it can be properly represented as message properties.

### JMS Transactions

A JMS session can be managed transactionally. When using `JmsTransactionManager` or an appropriate JTA setup, send operations can participate in the JMS transaction. However, the JMS transaction and the chunk's database transaction do not automatically become a single distributed transaction merely because both occur in the same step.

If atomic coordination between the database and JMS is required, you need a transaction manager capable of coordinating resources per system design, such as JTA/XA when both broker and database support it. XA increases operational complexity and should be chosen deliberately. Another common alternative is the transactional outbox.

## Sending Messages to RabbitMQ / AMQP

For RabbitMQ, Spring AMQP provides `RabbitTemplate` to send messages to an exchange with a routing key. The exchange and bindings determine which queues receive the message.

Illustrative example:

```java
public class RabbitOrderWriter implements ItemWriter<OrderCreatedEvent> {

    private final RabbitTemplate rabbitTemplate;
    private final String exchange;
    private final String routingKey;

    public RabbitOrderWriter(
            RabbitTemplate rabbitTemplate,
            String exchange,
            String routingKey) {
        this.rabbitTemplate = rabbitTemplate;
        this.exchange = exchange;
        this.routingKey = routingKey;
    }

    @Override
    public void write(Chunk<? extends OrderCreatedEvent> chunk) {
        for (OrderCreatedEvent event : chunk) {
            rabbitTemplate.convertAndSend(
                    exchange,
                    routingKey,
                    event,
                    message -> {
                        message.getMessageProperties()
                                .setMessageId(event.eventId());
                        message.getMessageProperties()
                                .setType("OrderCreated");
                        return message;
                    });
        }
    }
}
```

This snippet illustrates publishing; converter configuration, delivery mode, publisher confirms, and returns must be configured according to your Spring AMQP/RabbitMQ version. `convertAndSend` returning does not mean a consumer has processed the message. If you need confirmation that the broker received the publish, configure publisher confirms and handle confirms/returns via the corresponding API.

With RabbitMQ, distinguish:

- **Publisher confirm:** the broker confirms the publish was processed according to broker semantics.
- **Publisher return:** the message could not be routed to any queue under mandatory/return settings.
- **Consumer acknowledgement:** the consumer confirms it has processed the message.

These three signals do not replace one another. A successful publisher confirm does not prove a consumer has finished processing.

## Message Keys, Headers, and Correlation Metadata

A message typically has a body and metadata. The body carries the business payload; metadata supports routing, tracing, deduplication, and schema evolution.

Commonly used fields:

| Metadata | Purpose |
| --- | --- |
| `eventId` / message ID | Uniquely identifies an event for deduplication |
| `eventType` | Identifies the event/contract type |
| `schemaVersion` | Selects the appropriate schema or deserializer |
| `correlationId` | Links messages within a business flow |
| `causationId` | Indicates which message/event caused the current event |
| `traceparent` | Propagates distributed tracing context |
| `tenantId` | Separates tenants if required by the architecture |
| partition/routing key | Controls message distribution |

Do not put credentials, access tokens, or secrets in headers. Headers may be logged, stored in the broker, or exposed to operators; send only necessary metadata.

## Chunked Sending and Batching

Spring Batch calls `write()` once per chunk. The writer can send messages individually or use the broker/client's batch API. Chunk size determines the maximum number of items the writer receives in one call.

Example chunk size of 200:

```java
.chunk(200, transactionManager)
```

The writer receives up to 200 items in a chunk and may send 200 messages. If the broker/client supports internal batching, records may be grouped by batch size, linger time, or network request. One `write()` call does not necessarily correspond to a single network request.

Factors affecting throughput:

- Spring Batch chunk size.
- Number of messages per send operation.
- Payload size.
- Producer batch/linger/compression settings.
- Number of partitions/queues and key distribution.
- Number of in-flight requests.
- How the writer waits for acknowledgement.
- Network latency and broker load.

Chunks that are too small increase transaction and callback overhead. Chunks that are too large can increase memory usage, processing time, the number of messages needing retry, and rollback scope. Benchmark with message sizes and throughput close to production.

## Transactions Between Spring Batch and the Message Broker

This is the area requiring the most careful design when using a message writer. A chunk-oriented step typically runs within a transaction managed by a `PlatformTransactionManager`. The broker may have its own transaction manager or its own confirmation semantics.

### Database Transaction and Broker Transaction Are Two Resources

Suppose a step reads rows from a database, updates their status, and sends events to Kafka:

```text
Chunk transaction (Database)
    |
    +--> UPDATE orders SET status = 'PUBLISHED'
    |
    +--> send OrderCreated to Kafka
    |
    +--> COMMIT database
```

If Kafka receives the message but the database commit fails, consumers may process an event for an uncommitted change. Conversely, if the database commits successfully but sending the message fails, the system has updated state without the corresponding event.

A local transaction only protects the resource managed by its transaction manager. Never assume a message writer will automatically roll back along with the database transaction.

### Case: Send Succeeds First, Then Database Rolls Back

1. The writer sends the message successfully.
2. Another operation in the chunk fails.
3. The database transaction rolls back.
4. The message still exists on the broker.

Consumers may receive the message even though the related database change was not committed.

### Case: Database Commits, Then Sending Fails

If message sending does not participate in a shared transaction and an error occurs after the database commits, the row may already be marked published even though the broker never received the message. A job restart may skip that row, losing the event.

Execution order and transaction synchronization affect the failure window, but cannot make two independent resources atomic merely by changing call order.

## Delivery Guarantees

When designing a message writer, determine what delivery level the system requires:

| Level | Meaning | Primary Risk |
| --- | --- | --- |
| At-most-once | Messages may be lost but are not actively resent | Lost events if a failure occurs before the broker receives them |
| At-least-once | Retry until proper confirmation is received; duplicates possible | Consumers must be idempotent |
| Broker-scoped exactly-once | Broker supports exactly-once semantics within a specific transaction/protocol scope | Does not automatically cover the database and external side effects |

In batch integration, at-least-once plus idempotent consumers is usually the practical choice. End-to-end exactly-once across database, broker, and consumers generally requires multi-resource coordination design and still needs clear boundaries on what is guaranteed.

### Producer Acknowledgement Is Not Consumer Completion

A producer receiving a broker acknowledgement only confirms that the broker accepted/persisted the message according to its configuration. It does not prove the consumer has read, processed, and committed the result. If the business needs to know when the consumer has finished, you need a response event, reply queue, workflow status, or separate tracking mechanism.

## Transaction Managers and Broker Transactions

Some brokers support their own transactions. Spring also provides transaction managers for Kafka, JMS, or other resources. Which transaction manager a writer uses depends on step configuration and how the template is bound to the transaction.

You cannot assume `.writer(messageWriter)` automatically joins every transaction simply because the step has a `PlatformTransactionManager`. Verify:

- Which resource does the step's transaction manager manage?
- Which connection/session/producer does the template use?
- Where is the broker transaction started and committed?
- When the writer throws an exception, does broker rollback actually happen?
- When the database commit fails, can the broker transaction roll back as well?
- What are the commit ordering and synchronization behaviors of your framework version?

With Kafka, Spring Kafka provides `KafkaTransactionManager` and transactional producers. With JMS, there is `JmsTransactionManager` or JTA/XA depending on the provider. With RabbitMQ, channel transactions and publisher confirms have distinct semantics; publisher confirms are not a distributed transaction with the database.

If atomic commit between database and broker is needed, evaluate JTA/XA when both resources and infrastructure support it. Account for the coordinator, recovery logs, timeouts, heuristic outcomes, and operational overhead. Do not choose XA merely to avoid implementing idempotency if the system does not truly need it or the broker lacks proper support.

## Transactional Outbox

Transactional outbox is a common pattern to avoid losing events when updating a database and publishing messages.

Instead of sending directly to the broker inside the main processing transaction, the job writes an outbox row in the same transaction as the business change:

```text
Chunk transaction (Database)
    |
    +--> UPDATE orders ...
    |
    +--> INSERT INTO outbox(event_id, payload, status)
    |
    +--> COMMIT
             |
             v
       Outbox publisher step/job
             |
             +--> read pending outbox rows
             +--> publish to broker
             +--> mark published
```

If the database transaction rolls back, both the business change and the outbox row roll back. If it commits, the event resides durably in the database and can be retried later by the publisher.

Example schema:

```sql
CREATE TABLE outbox_event (
    event_id VARCHAR(100) PRIMARY KEY,
    aggregate_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL,
    status VARCHAR(20) NOT NULL
);
```

Business step writing to the outbox:

```java
@Bean
JdbcBatchItemWriter<OutboxEvent> outboxWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<OutboxEvent>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO outbox_event(
                        event_id, aggregate_id, event_type,
                        payload, created_at, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """)
            .itemPreparedStatementSetter((event, ps) -> {
                ps.setString(1, event.eventId());
                ps.setString(2, event.aggregateId());
                ps.setString(3, event.eventType());
                ps.setString(4, event.payload());
                ps.setTimestamp(5, Timestamp.from(event.createdAt()));
                ps.setString(6, "PENDING");
            })
            .build();
}
```

A separate publisher step reads pending outbox rows, sends the messages, and then marks them published. If publishing succeeds but updating the published status fails, the publisher may resend; thus event IDs and consumer idempotency are still needed.

### Outbox Does Not Automatically Eliminate Duplicates

Outbox guarantees that the database change and the intent to emit an event commit together. It does not guarantee publishing happens only once. If the publisher crashes after the broker receives the message but before marking the row published, the next run may resend it. Consumers must deduplicate by `eventId` or record an inbox/processed-message table within the same transaction as the business update.

### Claiming Outbox Rows Safely with Multiple Publishers

If multiple workers publish from the outbox concurrently, you need a claim/lease mechanism to prevent processing the same row twice. You can use a `PROCESSING` status, owner, lease expiry, or a database-appropriate locking strategy. Do not hold a database transaction open while waiting on a slow broker if that causes lock contention; design claiming and status updates using short transactions.

## Idempotency and Duplicate Messages

With at-least-once delivery, duplicates are an expected scenario. A writer may resend a chunk after a restart or retry. Producer/broker idempotence does not replace business-level idempotency.

Common approaches:

- Generate a deterministic `eventId` from the event/business operation rather than creating a new ID on every retry.
- Have consumers store processed `eventId`s in an inbox/processed table with a unique constraint.
- Have consumers update business data and record the event ID in the same transaction.
- Use upserts or unique keys to prevent duplicate writes.
- Design handlers so re-execution leaves the final result unchanged.

Example inbox table:

```sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

The consumer starts a transaction and inserts the event ID into this table; if a unique constraint indicates it was already processed, it skips the business effect. When the insert and business update share the same transaction, they commit or roll back together.

Do not generate `eventId = UUID.randomUUID()` inside the writer on each retry if the same business event must preserve its identity. The ID should be generated beforehand and persisted durably in the item or outbox row.

## Retries and Handling Message Send Errors

The writer can encounter errors:

- Broker unavailable or network timeout.
- Authentication/authorization failure.
- Non-existent topic/queue/exchange or misconfigured routing.
- Serialization error.
- Payload exceeding message size limit.
- Broker rejecting publish or quota exceeded.
- Acknowledgement timeout.
- Transaction/producer fencing errors.

Do not retry every error the same way:

| Error Type | Typically Appropriate Handling |
| --- | --- |
| Transient network timeout | Bounded retry, backoff, and timeout |
| Broker unavailable | Bounded retry; fail the step if still unrecoverable |
| Authentication/authorization | Fail fast and alert on configuration |
| Serialization/schema error | Reject/quarantine item or fail per contract; retrying does not fix the payload |
| Non-existent topic/queue | Fail fast, resolve deployment/configuration |
| Message too large | Reject or move to object storage + reference per contract |
| Duplicate due to retry | Handled by consumer idempotency |

Example fault-tolerant step:

```java
return new StepBuilder("publishOrdersStep", jobRepository)
        .<OrderCreatedEvent, OrderCreatedEvent>chunk(100, transactionManager)
        .reader(eventReader)
        .writer(kafkaOrderWriter)
        .faultTolerant()
        .retry(TransientBrokerException.class)
        .retryLimit(3)
        .build();
```

`TransientBrokerException` is an application exception classifying recoverable broker errors. In practice, map the exact exceptions from the Kafka/JMS/AMQP client and define the retry policy according to your framework version. Do not retry serialization or authorization errors as if they were network errors.

### Backoff and Two-Tier Retries

Producer clients often have internal retries. Spring Batch also has retries at the writer/step level. Two tiers can multiply attempt counts and extend wait times unexpectedly. Calculate the total retry budget, `delivery.timeout`, step retry limit, and backoff so you do not create a retry storm.

Do not hold a chunk transaction open too long while waiting on retries if that transaction holds critical database locks. For prolonged broker outages, a separate outbox publisher usually isolates failures better.

## Skip and Dead-Letter Queues

Skip may be appropriate for invalid messages or unserializable items, but ensure errors are classified accurately. If the error is a broker outage, skipping items will lose events.

Several options:

- **Fail the step:** when losing any message is unacceptable.
- **Skip + reject audit:** when data is invalid and the business allows quarantining.
- **Dead-letter queue (DLQ):** when the broker/consumer has a mechanism to move failing messages to a separate queue.
- **Outbox pending/error:** keep events in the database for retry or investigation.

A DLQ usually handles messages consumers cannot process or messages dead-lettered by the broker per policy; it does not automatically replace reject handling on the producer side. If the writer cannot publish because a topic does not exist, a consumer-side DLQ cannot help.

`SkipListener` can record skipped items:

```java
public class MessageSkipListener
        implements SkipListener<OrderCreatedEvent, OrderCreatedEvent> {

    @Override
    public void onSkipInRead(Throwable exception) {
        log.warn("Could not read event", exception);
    }

    @Override
    public void onSkipInProcess(
            OrderCreatedEvent item,
            Throwable exception) {
        log.warn("Event {} rejected during processing", item.eventId(), exception);
    }

    @Override
    public void onSkipInWrite(
            OrderCreatedEvent item,
            Throwable exception) {
        log.error("Event {} failed during publish", item.eventId(), exception);
    }
}
```

If writing to a reject file or database inside the listener, consider transaction scope and idempotency of side effects. Listeners may be invoked along retry/rollback paths; do not create uncontrolled duplicate audit records.

## Ordering and Concurrency

Message order can matter—for example, `OrderCreated` must arrive before `OrderCancelled`. However, a chunk writer might send concurrently or the broker might distribute across partitions/queues.

To preserve ordering:

- Use a stable aggregate-based key in Kafka so events for the same aggregate land in the same partition.
- Avoid sending events with the same key concurrently if send order is required.
- Ensure consumers process sequentially within a partition/queue per required semantics.
- Include a sequence/version in the payload so consumers can detect out-of-order events.
- If global ordering is required, design a single partition/queue or an explicitly ordered coordinator; weigh the throughput limits.

There is no automatic global ordering when sending across multiple topics/partitions/queues. `ItemWriter` iterating in chunk order does not guarantee consumers observe that order if async producers, broker partitioning, or consumer concurrency alters it.

## Serialization and Schema Evolution

Messages are typically serialized as JSON, Avro, Protobuf, or another format. Serialization must be consistent between producer and consumer.

With JSON/Jackson:

```java
String payload = objectMapper.writeValueAsString(event);
```

Do not serialize an object into JSON and then serialize that JSON string a second time, because consumers will receive a JSON string containing JSON instead of an object. Use a converter or serializer matched to the template so it serializes exactly once.

Schema principles:

- Add new fields in a backward/forward-compatible way where older consumers can ignore unknown fields.
- Do not change the meaning or type of existing fields without versioning.
- Specify required fields, defaults, and null semantics.
- Use a schema registry if the ecosystem requires centrally managed contracts.
- Test producer payloads against supported consumer contract versions.

Do not send Java class names as discriminators if messages are consumed by multiple languages or untrusted parties. Use explicit event types/versions and allowlist deserialization.

## Message Size and Large Payloads

Brokers usually enforce message size limits. Do not send large entity graphs or files inside a message if doing so exceeds limits or puts pressure on memory/network.

For large payloads:

1. Write the content to object storage or durable file storage.
2. Generate an immutable reference, checksum, and content type.
3. Send a small message containing the URI/reference, metadata, and event ID.
4. Consumers download the content with appropriate access permissions.

The reference must point to an object durably published before the message is sent. Define retention and access permissions so consumers can fetch the object within the required timeframe.

## Batch Writers and Message Batch APIs

A writer can send records individually via a template or use the broker's batch API. Sending per record makes per-item error handling easier, though it may increase overhead. Batch APIs can increase throughput, but often tie failures to the whole batch or return per-record statuses depending on the client.

When choosing a batch API, determine:

- Does a single failure in the batch fail the entire chunk?
- Can you identify which specific record failed?
- How is partial success represented?
- Can the entire batch be retried without creating duplicates?
- Does the broker limit record count or total bytes per batch?
- Does the batch preserve ordering per key/partition?

Do not catch per-message errors and proceed as if the entire chunk succeeded without explicitly recording failed items. Spring Batch only knows whether `write()` succeeded or threw an exception; if the writer swallows errors, the checkpoint may advance past unpublished items.

## Monitoring and Observability

A message writer should expose metrics to operate both the job and the broker:

- Number of items received by the writer.
- Number of messages sent successfully.
- Number of send failures and retries.
- Acknowledgement latency and timeouts.
- Message size and serialization latency.
- Number of skipped/rejected items.
- Topic/queue/exchange and partition/routing key.
- Correlation ID, event ID, and `JobExecution` ID.
- Number of pending events in the outbox if using that pattern.

Do not log full payloads if they contain personal data or sensitive information. Logging event ID, business key, and correlation ID is usually sufficient for investigation.

When a job fails, operators need to know which messages the broker might have already accepted before the failure. Recording event IDs and send results helps determine the scope needing replay or reconciliation.

## Configuring the Writer in a Step

After creating the writer bean, register it like a normal writer:

```java
@Bean
Step publishOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderCreatedEvent> eventReader,
        ItemProcessor<OrderCreatedEvent, OrderCreatedEvent> validator,
        ItemWriter<OrderCreatedEvent> messageWriter) {

    return new StepBuilder("publishOrdersStep", jobRepository)
            .<OrderCreatedEvent, OrderCreatedEvent>chunk(100, transactionManager)
            .reader(eventReader)
            .processor(validator)
            .writer(messageWriter)
            .build();
}
```

The step processes chunks and calls the writer. If the writer sends messages directly, the step's transaction manager only protects the broker if the writer/template actually participates in that transaction manager/resource. Document this clearly in configuration and operational runbooks.

If the writer needs no state, it does not need to implement `ItemStream`. If the writer holds buffers, temporary files, or checkpoints required for restart, implement `ItemStream` and ensure the stream lifecycle is registered. Producer templates are usually Spring-managed; do not close the template/connection on every `write()` call.

## Scope and Thread Safety

A message writer is often a singleton bean. That is safe only when the implementation holds no mutable state per item or execution and the underlying template/client is thread-safe per its contract.

Guidelines:

- Do not store `currentEvent`, `currentJobExecution`, or shared mutable buffers in fields.
- Build per-item correlation metadata using local variables.
- Use Spring-managed producer templates configured properly for thread safety.
- If the writer needs step-scoped state, consider `@StepScope`.
- If the step runs multithreaded, define producer ordering and concurrency behavior.
- Do not open a new producer connection/session per item when the template already manages pooling/lifecycle.

With JMS, sessions are typically not thread-safe; `JmsTemplate` manages session creation/usage per its contract. Do not hold a singleton `Session` yourself and use it from multiple threads.

## Testing a Message-Sending ItemWriter

Have unit tests for mapping, routing, and errors; and integration tests with a broker or test container for acknowledgement, serialization, transactions, and retries.

### Unit Testing with a Mock MessageSender

With the generic writer above:

```java
@Test
void sendsEveryItemInChunk() throws Exception {
    MessageMapper<Order, OrderCreatedEvent> mapper = order ->
            new OrderCreatedEvent(
                    "event-" + order.orderId(),
                    order.orderId(),
                    order.customerId(),
                    order.amount(),
                    "VND",
                    Instant.parse("2026-11-15T00:00:00Z"),
                    1);

    MessageSender<OrderCreatedEvent> sender = mock(MessageSender.class);
    ItemWriter<Order> writer = new MessageItemWriter<>(mapper, sender);

    writer.write(new Chunk<>(List.of(order1, order2)));

    verify(sender, times(2)).send(any(OrderCreatedEvent.class));
}
```

This test verifies each item is mapped and sent. You can capture arguments to verify event ID, amount, currency, and schema version are accurate.

### Testing Send Failures

Mock the sender to throw an exception on one item and verify `write()` propagates the exception outward. Do not let the writer swallow errors. Check invocation counts and behavior when the first, middle, or last item in a chunk fails.

### Testing Kafka

With Kafka, verify:

- Records are sent to the right topic and key.
- Payloads/headers serialize according to contract.
- Future failures fail the writer.
- Timeouts are handled properly.
- `acks`, idempotence, and transaction settings match requirements.
- Restarts/retries do not cause consumers to apply duplicate business effects.

You can use an embedded broker or Testcontainers Kafka depending on test infrastructure. Testing against a broker equivalent to production is valuable for validating partitioning, authentication, replication, and producer configuration.

### Testing JMS/RabbitMQ

With JMS, verify destination, converter, message properties, delivery mode, and transaction rollback/commit. With RabbitMQ, verify exchange/routing key, queue bindings, publisher confirms/returns, and behavior when the broker is unavailable.

Do not only assert that `convertAndSend` was called; consume messages from the test broker or verify the corresponding publish result/confirm.

### Testing Chunk Transactions

Create a chunk with multiple items, force one send to fail, and verify:

- The writer throws an error for the step to handle.
- Database changes in the chunk roll back if part of the same transaction.
- Messages previously accepted by the broker may still exist if the broker does not participate in a shared transaction.
- Retries/restarts may resend events.
- Consumer idempotency prevents duplicate business effects.

This test should simulate the failure window after publish but before database commit. That is how you demonstrate real transaction boundaries.

### Testing Outbox

If using an outbox, verify:

- Business updates and outbox inserts commit/roll back together.
- The publisher claims only valid pending rows.
- Broker receives an event and the publisher crashes before marking published: the event can be resent.
- Consumers deduplicate by event ID.
- Failing outbox rows are retried or moved to an investigation state per policy.
- Multiple publishers do not claim the same row under the lease/locking mechanism.

## Common Mistakes

### Returning Immediately After Asynchronous Send

The chunk may commit before the broker confirms. Wait for acknowledgement or provide a flush/await mechanism that propagates errors back to the writer.

### Assuming Database Rollback Revokes Messages

The broker is a separate resource. Use coordinated transactions where appropriate or the transactional outbox.

### Confusing Producer Acknowledgement with Consumer Completion

The broker accepting a message does not mean the consumer has processed it. Use a reply/status workflow if completion tracking is needed.

### Lacking a Stable Event ID

Retries/restarts can send duplicates that consumers cannot identify. Generate IDs upfront and preserve them across every redelivery.

### Choosing an Inappropriate Kafka Key

Events for the same aggregate can land in different partitions and lose ordering. Use a stable business key if per-aggregate order is needed.

### Retrying Every Exception

Schema, authentication, or missing-topic errors are not fixed by retrying. Classify transient vs. permanent errors and set a retry budget.

### Swallowing Exceptions in the Writer

Spring Batch may mark the chunk successful even though messages were not sent. Propagate errors or record rejects per a clear contract.

### Sending Oversized Messages

Brokers have size limits and large payloads increase memory/network load. Use object storage references for large content.

### Sending JPA Entities Directly

Payloads may pull in lazy proxies, circular references, or internal fields. Create dedicated DTO/event contracts.

### Skipping Schema Versioning

Older consumers may fail to read new payloads. Manage schema evolution and contract tests.

### Using Skip to Handle Broker Outages

Skip loses events without outbox/reject persistence. Infrastructure outages usually require retry/fail.

### Assuming the Writer Is Called Per Item

The writer receives a chunk. Design batching and error handling around the whole chunk; do not assume each item has its own transaction.

### Ignoring Side Effects Outside the Transaction

Messages, files, and HTTP calls can remain after rollback. Use idempotency, outbox, or compensation.

## Design Principles

When implementing a message-sending `ItemWriter`, determine:

1. Is the message an event or a command, and what is the consumer contract?
2. Does the payload include an event ID, schema version, business key, and correlation metadata?
3. Are the broker/destination/key/routing semantics correct?
4. Does the writer serialize exactly once and bound payload size?
5. After which acknowledgement does the writer return: producer future, publisher confirm, or transaction commit?
6. Are the chunk transaction and broker transaction genuinely coordinated?
7. Should a transactional outbox be used instead of direct publishing?
8. Does the retry budget account for the producer's internal retries as well?
9. Are consumers idempotent to handle duplicates?
10. Is ordering per aggregate/partition guaranteed?
11. Can side effects survive a rollback, and is there a reconciliation mechanism?
12. Does monitoring track event ID, correlation ID, send latency, failures, and retry metrics?
13. Do tests simulate broker unavailability, acknowledgement failures, duplicates, rollbacks, and restarts?

`ItemWriter` is an appropriate integration point for emitting messages per chunk, but the writer must clearly define acknowledgement and transaction semantics. Use event DTOs with IDs/schema versions, stable keys, await send results when errors must affect the step, and classify retries. When database updates and message publishing must stay consistent, a transactional outbox is often easier to operate than direct publishing; consumers still need idempotency because the outbox publisher may resend. Test failure windows between broker acknowledgement and database commit against realistic brokers/clients.

## Key Takeaways

`ItemWriter<T>` receives a `Chunk` and can convert each item into a message sent to Kafka, JMS, or RabbitMQ. Design stable payloads with event IDs, schema versions, business keys, and correlation metadata; use appropriate serializers/converters and avoid sending internal entities or oversized payloads. With Kafka, keys affect partitions/ordering and futures must be awaited if send failures should fail the writer; with JMS/RabbitMQ, configure transactions, confirms/returns, and delivery semantics per broker. A database chunk transaction is not automatically atomic with the broker; published messages may persist after a rollback, or a database commit may succeed when publishing fails. Define delivery guarantees, use bounded retries, consumer idempotency, and a transactional outbox when database-message synchronization is required. Never swallow exceptions, never send async and return before knowing the outcome required by policy, and test acknowledgement, duplicates, rollbacks, and restarts with a production-equivalent broker.
