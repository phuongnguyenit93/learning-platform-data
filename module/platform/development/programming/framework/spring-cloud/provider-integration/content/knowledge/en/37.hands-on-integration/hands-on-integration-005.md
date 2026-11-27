# Coordinating Databases and Queues with Transactional Outbox and Idempotent Processing

## 1. Problem Statement and Objectives

A business operation in Spring Boot often needs to update data and publish a message so another service can continue processing. For example:

- Create an order in the database, then emit an OrderCreated event.
- Record an uploaded document, then send DocumentReady to an OCR worker.
- Update a payment status, then emit PaymentCaptured.
- Modify customer details, then notify search or analytics systems.

If the application writes to the database and publishes a message as two independent operations, a dual-write failure can occur: the database commits while the message is never sent, or the message is sent while the database transaction rolls back. The two systems then fall out of sync.

This lab builds reliable coordination using the **Transactional Outbox** on the producer side and the **Inbox/Idempotent Consumer** on the consumer side. The outbox stores events in the same transaction as business data; a relay sends events to the broker after the transaction commits. The consumer records processed events and updates business data in the same transaction.

Implement the same business contract across three ecosystems:

- **AWS:** Spring Boot + relational database + Amazon SQS, using AWS SDK for Java 2.x or Spring Cloud AWS.
- **Google Cloud:** Spring Boot + relational database + Pub/Sub, using Spring Framework on Google Cloud.
- **Azure:** Spring Boot + relational database + Azure Service Bus, using Spring Cloud Azure.

The database, broker, and workers do not participate in a single distributed transaction. Therefore, an outbox does not give the entire system absolute exactly-once processing. The model is designed so messages can be redelivered while consumers produce idempotent business effects.

After completing this lesson, you will be able to:

- Explain the failure windows of dual writes.
- Design an outbox table and write events in the same transaction as business data.
- Implement a polling relay using leases and FOR UPDATE SKIP LOCKED.
- Distinguish a polling relay from CDC/Debezium.
- Publish messages to SQS, Pub/Sub, and Service Bus using stable event IDs.
- Build a consumer inbox with a unique constraint.
- Place transaction boundaries so ACK happens only after the database commits.
- Handle duplicate deliveries, retries, DLQs, and replays.
- Preserve per-aggregate ordering when business logic requires it.
- Combine broker deduplication with application-layer idempotency.
- Test crashes before/after publish and before/after commit.

> **Scope:** SQL examples use PostgreSQL and Spring Boot with JDBC/JPA at an illustrative level. Choose Spring Cloud AWS, Spring Framework on Google Cloud, and Spring Cloud Azure versions compatible with your project's Spring Boot version; do not mix BOMs across providers. Code snippets focus on transaction boundaries and core APIs; some repositories/models are abstractions to complete according to your application.

## 2. Dual Writes and Failure Windows

### 2.1. An error-prone implementation

A service often begins by saving data and then sending a message:

~~~java
@Transactional
public Order createOrder(CreateOrderRequest request) {
    Order order = orderRepository.save(Order.from(request));

    sqsClient.sendMessage(builder -> builder
            .queueUrl(queueUrl)
            .messageBody(toJson(new OrderCreated(order.getId()))));

    return order;
}
~~~

This code has two problems:

1. The database and broker do not share a transaction manager.
2. @Transactional only manages the database transaction; it does not roll back a message already accepted by the broker.

If publishing happens before the database commits, consumers may receive the event while the record does not yet exist. If publishing happens after commit, the process may crash before sending the message.

### 2.2. Two failure windows

~~~mermaid
sequenceDiagram
    participant API as Spring Boot
    participant DB as Database
    participant MQ as Message broker
    participant C as Consumer

    API->>DB: INSERT order
    DB-->>API: Commit
    Note over API: Process crashes before publish
    API-xMQ: OrderCreated not sent
    Note over DB,MQ: Order exists, event is lost

    API->>DB: INSERT order
    API->>MQ: Publish OrderCreated
    MQ-->>API: Accepted
    MQ->>C: Deliver event
    C->>DB: Read order
    Note over API,DB: Database transaction rollback
    Note over DB,MQ: Event sent, business data does not exist
~~~

| Sequence | Failure | Outcome |
| --- | --- | --- |
| Commit DB → crash → publish | Process dies after commit | Data exists without an event |
| Publish → rollback DB | Transaction fails after broker accepted message | Consumer receives event with no matching data |
| Publish succeeds → response timeout | Broker received it, producer does not know outcome | Producer may resend, creating a duplicate |
| Consumer commit → crash before ACK | DB updated, message not ACKed | Broker redelivers, consumer may run again |

### 2.3. Why not use distributed transactions?

One might consider XA/2PC to coordinate databases and brokers. However, not all brokers and databases support a shared transaction coordinator; distributed transactions increase complexity, latency, coupling, and failure modes.

Transactional outbox uses the database's local transaction to atomically persist:

- Business data changes.
- A record describing the event to be published.

A separate relay reads the outbox and sends messages. If the relay crashes, the event remains in the database to be sent again. If the broker received the message before the relay marked it sent, the relay sends it again with the same event ID; the consumer handles the duplicate safely.

## 3. Transactional Outbox and Inbox Architecture

### 3.1. Overall flow

~~~mermaid
flowchart LR
    CMD["HTTP command"] --> SVC["Spring Boot service"]
    SVC --> TX["One DB transaction"]
    TX --> BIZ["Business tables"]
    TX --> OUT["Outbox table"]
    OUT --> RELAY["Polling relay / CDC"]
    RELAY --> BROKER["SQS / Pub/Sub / Service Bus"]
    BROKER --> CONSUMER["Spring Boot consumer"]
    CONSUMER --> ITX["One consumer DB transaction"]
    ITX --> INBOX["Inbox / processed_messages"]
    ITX --> EFFECT["Business state changes"]
~~~

### 3.2. Role of each component

| Component | Responsibility |
| --- | --- |
| Business service | Execute commands and decide which business events to emit |
| Business database | Store business state |
| Outbox table | Persist events in the same transaction as business state |
| Relay | Read outbox, publish to broker, record publish status |
| Broker | Store and deliver messages per provider delivery semantics |
| Consumer inbox | Track processed events per consumer and event ID |
| Consumer transaction | Insert inbox marker and update business state in one transaction |
| Retry/DLQ | Retain and classify errors for retry or investigation |

### 3.3. Guarantees and limitations

| Pattern | Core guarantee | Limitation |
| --- | --- | --- |
| Transactional outbox | Business updates and event records commit or roll back together | Relay may publish duplicates |
| Polling relay | Unpublished events remain in the database | Polling latency and query load |
| CDC relay | Reads committed changes from the transaction log | Requires connector/CDC infrastructure |
| Consumer inbox | Duplicate events do not repeat DB side effects in the same transaction | Does not automatically protect external system side effects |
| Broker deduplication | Reduces duplicate publishes/deliveries per provider capabilities | Limited by time window, scope, and semantics |
| End-to-end exactly once | Cannot be inferred from outbox or broker alone | Requires idempotency per side effect and system boundary |

The accurate statement is: **the producer emits events with at-least-once delivery; the consumer achieves idempotent business effects within its database**. If the consumer calls a payment gateway, email service, or external API, use idempotency keys, a downstream outbox, or an appropriate saga.

## 4. Designing the Outbox Table

### 4.1. Schema

An outbox record should contain a stable ID, aggregate key, event type, payload, and relay state:

~~~sql
CREATE TABLE outbox_events (
    event_id           UUID PRIMARY KEY,
    aggregate_type     VARCHAR(100) NOT NULL,
    aggregate_id       VARCHAR(200) NOT NULL,
    aggregate_version  BIGINT,
    event_type         VARCHAR(200) NOT NULL,
    schema_version     INTEGER NOT NULL DEFAULT 1,
    correlation_id     VARCHAR(200),
    payload            JSONB NOT NULL,
    occurred_at        TIMESTAMPTZ NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    published_at       TIMESTAMPTZ,
    attempt_count      INTEGER NOT NULL DEFAULT 0,
    next_attempt_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_owner        VARCHAR(128),
    lease_until        TIMESTAMPTZ,
    last_error         VARCHAR(2000),
    status             VARCHAR(24) NOT NULL DEFAULT 'PENDING'
);
~~~

Field meanings:

- event_id: unique UUID, preserved across all retries and replays.
- aggregate_type: aggregate category, e.g., Order, Document.
- aggregate_id: aggregate key to preserve per-entity ordering if needed.
- aggregate_version: monotonically increasing business version of the aggregate.
- event_type: event name such as OrderCreated, DocumentReady.
- schema_version: payload version so consumers can evolve compatibly.
- payload: event data required by consumers.
- published_at: recorded only after the broker confirms publish.
- attempt_count, next_attempt_at: relay retry policy fields.
- lease_owner, lease_until: prevent multiple relays from claiming the same record.
- last_error: sanitized error information without secrets.
- status: PENDING, IN_FLIGHT, PUBLISHED, or DEAD.

State can alternatively be represented using published_at and lease without a status column; pick one consistent convention and create matching unique/partial indices.

### 4.2. Indices for the relay

With PostgreSQL:

~~~sql
CREATE INDEX idx_outbox_pending
    ON outbox_events (next_attempt_at, created_at)
    WHERE published_at IS NULL
      AND status IN ('PENDING', 'IN_FLIGHT');

CREATE INDEX idx_outbox_aggregate_order
    ON outbox_events (aggregate_type, aggregate_id, aggregate_version);
~~~

The outbox acts as a queue table inside the database. Without indices, the relay scans many already-published rows. If rows are retained long-term, table size and vacuum/maintenance overhead can grow significantly.

### 4.3. Event payloads are contracts

Do not serialize raw JPA entities and send them. Entities may contain lazy relationships, internal fields, secrets, or structures tied to database schemas.

Create explicit event DTOs:

~~~java
import java.time.Instant;
import java.util.UUID;

public record OrderCreatedPayload(
        UUID orderId,
        String customerId,
        long totalAmountMinor,
        String currency,
        Instant createdAt) {
}

public record EventEnvelope<T>(
        UUID eventId,
        String aggregateType,
        String aggregateId,
        Long aggregateVersion,
        String eventType,
        int schemaVersion,
        Instant occurredAt,
        String correlationId,
        T payload) {
}
~~~

Payloads should contain enough data for consumers to process without arbitrarily reading the producer's database. If payloads only contain IDs, consumers must call the producer API; you must then account for producer downtime, authorization, and the fact that current state may differ from the event.

Do not place access tokens, passwords, signed URLs, or unnecessary personal data inside events. Events often persist in databases, brokers, logs, and DLQs far longer than the original request.

## 5. Writing Business Data and Outbox in One Transaction

### 5.1. Service method

The core requirement is that the business repository and outbox repository share the same database and transaction manager:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final OutboxRepository outbox;
    private final ObjectMapper objectMapper;

    public OrderApplicationService(
            OrderRepository orders,
            OutboxRepository outbox,
            ObjectMapper objectMapper) {
        this.orders = orders;
        this.outbox = outbox;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public Order create(CreateOrderRequest request) {
        Order order = orders.save(Order.from(request));

        UUID eventId = UUID.randomUUID();
        OrderCreatedPayload payload = new OrderCreatedPayload(
                order.getId(),
                order.getCustomerId(),
                order.getTotalAmountMinor(),
                order.getCurrency(),
                Instant.now());
        String correlationId = request.correlationId() != null
                ? request.correlationId()
                : eventId.toString();

        outbox.insert(
                eventId,
                "Order",
                order.getId().toString(),
                order.getVersion(),
                "OrderCreated",
                1,
                correlationId,
                writeJson(payload),
                Instant.now());

        return order;
    }

    private String writeJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        }
        catch (JsonProcessingException ex) {
            throw new IllegalStateException("Cannot serialize event", ex);
        }
    }
}
~~~

If serialization fails, the exception rolls back the transaction. If the outbox insert fails, the order change also rolls back. When the transaction commits, both exist together.

### 5.2. Repository insert

Example using NamedParameterJdbcTemplate and PostgreSQL JSONB:

~~~java
import java.sql.Timestamp;
import java.util.Map;
import java.util.UUID;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OutboxRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public OutboxRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(
            UUID eventId,
            String aggregateType,
            String aggregateId,
            Long aggregateVersion,
            String eventType,
            int schemaVersion,
            String correlationId,
            String payloadJson,
            java.time.Instant occurredAt) {

        String sql = """
            INSERT INTO outbox_events (
                event_id, aggregate_type, aggregate_id,
                aggregate_version, event_type, schema_version, correlation_id,
                payload, occurred_at, created_at, status
            )
            VALUES (
                :eventId, :aggregateType, :aggregateId,
                :aggregateVersion, :eventType, :schemaVersion, :correlationId,
                CAST(:payload AS jsonb), :occurredAt, now(), 'PENDING'
            )
            """;

        jdbc.update(sql, Map.of(
                "eventId", eventId,
                "aggregateType", aggregateType,
                "aggregateId", aggregateId,
                "aggregateVersion", aggregateVersion,
                "eventType", eventType,
                "schemaVersion", schemaVersion,
                "correlationId", correlationId,
                "payload", payloadJson,
                "occurredAt", Timestamp.from(occurredAt)));
    }
}
~~~

This is illustrative code; Map.of does not accept null values. If aggregateVersion can be null, use MapSqlParameterSource or enforce a non-null version.

In the service example, CreateOrderRequest is assumed to have an optional correlationId taken from request headers or tracing context. If absent, eventId is used as a fallback correlation ID.

### 5.3. Design anti-patterns to avoid

- Calling the broker inside a database transaction and hoping both roll back together.
- Using @TransactionalEventListener(AFTER_COMMIT) as the sole publishing mechanism. The process can crash after commit before the listener runs.
- Writing to the outbox using a different datasource or transaction manager than the business update.
- Creating events before knowing the transaction succeeded and sending directly.
- Serializing entire JPA entities.
- Deleting outbox rows immediately after publish without a retention/audit/recovery policy.

@TransactionalEventListener(AFTER_COMMIT) is still useful to wake the relay early and reduce latency, but polling/CDC must remain the durability guarantee so events are never lost.

## 6. Polling Relay: Claim, Publish, and Mark

### 6.1. Relay workflow

A simple relay can poll continuously:

1. Open a short transaction and claim a batch of unpublished events.
2. Write lease_owner, lease_until, and increment attempt count.
3. Commit the claim transaction.
4. Publish messages to the broker outside any database transaction.
5. Wait for broker acknowledgement.
6. Write published_at, status = PUBLISHED, and clear the lease.
7. If publishing fails, record the error, compute next_attempt_at, and release the lease.

Never hold a database transaction open while waiting on network calls to the broker.

~~~mermaid
sequenceDiagram
    participant R as Outbox relay
    participant DB as Database
    participant MQ as Broker

    R->>DB: Claim pending rows + lease
    DB-->>R: Batch event records
    R->>MQ: Publish eventId + payload
    MQ-->>R: Broker accepted
    R->>DB: Mark PUBLISHED
    DB-->>R: Commit
~~~

### 6.2. Claiming a batch with SKIP LOCKED

PostgreSQL SQL example:

~~~sql
WITH candidates AS (
    SELECT event_id
    FROM outbox_events
    WHERE published_at IS NULL
      AND status IN ('PENDING', 'IN_FLIGHT')
      AND next_attempt_at <= now()
      AND (lease_until IS NULL OR lease_until < now())
    ORDER BY created_at, event_id
    LIMIT :batch_size
    FOR UPDATE SKIP LOCKED
)
UPDATE outbox_events o
SET status = 'IN_FLIGHT',
    lease_owner = :worker_id,
    lease_until = now() + interval '60 seconds',
    attempt_count = attempt_count + 1
FROM candidates c
WHERE o.event_id = c.event_id
RETURNING o.*;
~~~

FOR UPDATE SKIP LOCKED lets multiple relays fetch batches concurrently without claiming the same rows. Leases recover rows if a relay process dies.

Choose a lease longer than the expected publish time for the batch. If batches can take longer, shrink batch sizes or renew leases. When marking published, always check lease_owner so a stalled worker cannot overwrite the state of a worker that reclaimed the row.

### 6.3. Publishing outside transactions and updating state

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

@Component
public class OutboxRelay {

    private final TransactionTemplate transactionTemplate;
    private final OutboxRepository outbox;
    private final EventPublisher publisher;
    private final String workerId = java.util.UUID.randomUUID().toString();

    public OutboxRelay(
            TransactionTemplate transactionTemplate,
            OutboxRepository outbox,
            EventPublisher publisher) {
        this.transactionTemplate = transactionTemplate;
        this.outbox = outbox;
        this.publisher = publisher;
    }

    public void runBatch() {
        List<OutboxRecord> batch = transactionTemplate.execute(
                status -> outbox.claim(workerId, 50, Duration.ofSeconds(60)));

        if (batch == null || batch.isEmpty()) {
            return;
        }

        for (OutboxRecord event : batch) {
            try {
                publisher.publish(event).toCompletableFuture().join();

                transactionTemplate.executeWithoutResult(status ->
                        outbox.markPublished(event.eventId(), workerId, Instant.now()));
            }
            catch (Exception ex) {
                transactionTemplate.executeWithoutResult(status ->
                        outbox.scheduleRetry(
                                event.eventId(),
                                workerId,
                                retryTime(event.attemptCount()),
                                safeError(ex)));
            }
        }
    }

    private Instant retryTime(int attempt) {
        long seconds = Math.min(300, 1L << Math.min(attempt, 8));
        return Instant.now().plusSeconds(seconds);
    }

    private String safeError(Exception ex) {
        return ex.getClass().getSimpleName();
    }
}
~~~

OutboxRecord, EventPublisher, and repository methods are illustrative abstractions. In production:

- Use bounded executors/concurrency; never spawn unbounded threads.
- Compute exponential backoff with jitter.
- Do not store exception messages that could contain credentials or sensitive payloads.
- Update rows guarded by matching event_id and lease_owner.
- Handle null or failed publish futures properly.
- Add a shutdown hook to stop claiming new batches and await in-flight batches within bounds.

### 6.4. Relay duplicate window

Suppose the broker accepts the message, but the relay crashes before writing published_at:

~~~mermaid
sequenceDiagram
    participant R as Relay
    participant MQ as Broker
    participant DB as Outbox DB

    R->>MQ: Publish event E
    MQ-->>R: Accepted
    Note over R: Process crash
    Note over DB: E is not yet PUBLISHED
    R->>MQ: Retry publish event E
    MQ-->>R: Accepted
    Note over MQ: Two deliveries may exist
~~~

This is expected behavior. The relay must republish because it cannot know for certain that the broker received the message without durable confirmation in the database. Keep event_id unchanged so consumers recognize duplicates.

Never mark PUBLISHED before broker confirmation. Doing so risks losing events if publishing fails after the database already marked completion.

### 6.5. Retries and DEAD state

After reaching maximum attempts, transition the event to DEAD, retain payload and sanitized error details, and trigger an alert. Never silently delete failed rows.

Replay procedure:

1. Investigate broker, network, credentials, and payload.
2. Fix the root cause.
3. Verify consumers can process the event.
4. Reset the row to PENDING, reset next_attempt_at, and keep the original event_id.
5. Audit who triggered the replay and when.
6. Monitor publish outcome and consumer processing.

If the event is no longer valid per business rules, mark it CANCELLED with a reason and audit record.

## 7. CDC Relay with Debezium

### 7.1. When to use CDC

Instead of polling the outbox table, CDC (Change Data Capture) reads the database transaction log:

- PostgreSQL: logical decoding/WAL.
- MySQL: binlog.
- Other databases: corresponding transaction logs or change streams.

A Debezium connector watches the outbox table and emits events to Kafka. The Outbox Event Router SMT transforms inserted rows into event messages with appropriate metadata and payloads.

~~~mermaid
flowchart LR
    APP["Spring Boot transaction"] --> DB["Database + outbox"]
    DB --> LOG["WAL / binlog"]
    LOG --> CDC["Debezium connector"]
    CDC --> SMT["Outbox Event Router SMT"]
    SMT --> KAFKA["Kafka topic"]
    KAFKA --> BRIDGE["Sink / bridge / downstream"]
    BRIDGE --> CLOUDMQ["SQS / Pub/Sub / Service Bus"]
~~~

By default, Debezium Outbox Event Router uses these fields:

| Field | Role |
| --- | --- |
| id | Unique event ID; typically placed in headers |
| aggregatetype | Routes topics by aggregate type |
| aggregateid | Event key; can act as message key to preserve ordering within a Kafka partition |
| type | Business event type |
| payload | Event content |

The outbox should be treated as insert-only. Never update the payload of an already-emitted event. Custom columns can carry schema version, timestamps, or correlation IDs.

The earlier schema example uses snake_case column names (event_id, aggregate_type, aggregate_id, event_type). When using Debezium defaults, either match the default column names or configure SMT options such as table.field.event.id, route.by.field, and table.field.event.key to map actual column names. Do not assume the SMT automatically detects arbitrary aliases.

### 7.2. CDC does not automatically target every managed queue

Debezium Outbox Event Router typically emits to Kafka topics. If the final destination is SQS, Pub/Sub, or Service Bus, you need an appropriate sink connector, bridge, or publisher service. Do not assume enabling the SMT lets the database publish directly to any cloud queue.

### 7.3. Polling vs. CDC

| Criterion | Polling relay | CDC/Debezium |
| --- | --- | --- |
| Initial setup | Simple, lives inside application | Requires connectors and CDC infrastructure |
| Latency | Driven by polling interval | Near real-time after commit |
| Database load | Queries/indices and lease updates | Reads transaction log; requires retention/replication config |
| Scaling | Multiple relays using leases/SKIP LOCKED | Scale connectors/partitions and downstream |
| Operations | Monitor backlog and leases | Monitor connector lag and slot/binlog retention |
| Best fit | Moderate workloads, fewer moving parts | High throughput, many consumers, or existing Kafka/CDC stack |

Polling is a good starting point for labs. CDC fits organizations already operating Kafka Connect/Debezium or needing to reduce polling load. Both still require handling duplicates and consumer idempotency.

## 8. Standardizing Events and Publishers for Three Providers

### 8.1. Publisher contract

Create a small abstraction:

~~~java
import java.util.concurrent.CompletionStage;

public interface EventPublisher {
    CompletionStage<Void> publish(OutboxRecord event);
}
~~~

publish completes only when the client receives a successful acknowledgement from the broker API. If the outcome is uncertain due to a timeout, the relay treats it as unconfirmed and retries with the same event_id.

### 8.2. AWS SQS publisher

Using AWS SDK for Java 2.x:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import software.amazon.awssdk.services.sqs.SqsAsyncClient;
import software.amazon.awssdk.services.sqs.model.MessageAttributeValue;
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;

public class SqsEventPublisher implements EventPublisher {

    private final SqsAsyncClient sqs;
    private final ObjectMapper mapper;
    private final String queueUrl;

    public SqsEventPublisher(
            SqsAsyncClient sqs,
            ObjectMapper mapper,
            String queueUrl) {
        this.sqs = sqs;
        this.mapper = mapper;
        this.queueUrl = queueUrl;
    }

    @Override
    public CompletionStage<Void> publish(OutboxRecord event) {
        try {
            String body = mapper.writeValueAsString(event.envelope());

            SendMessageRequest request = SendMessageRequest.builder()
                    .queueUrl(queueUrl)
                    .messageBody(body)
                    .messageAttributes(Map.of(
                            "eventId", MessageAttributeValue.builder()
                                    .dataType("String")
                                    .stringValue(event.eventId().toString())
                                    .build()))
                    .build();

            return sqs.sendMessage(request).thenApply(response -> null);
        }
        catch (Exception ex) {
            return CompletableFuture.failedFuture(ex);
        }
    }
}
~~~

The example above targets SQS Standard. For FIFO queues, add:

- messageGroupId: typically aggregate_id to preserve ordering within an aggregate.
- messageDeduplicationId: use the stable event_id.
- If content-based deduplication is enabled, SQS hashes the body; consider whether any payload fields change across retries.

SQS FIFO removes duplicate sends within a 5-minute deduplication window. This is an extra safeguard on the producer side; it does not replace the consumer inbox and does not make database or external API side effects exactly-once.

### 8.3. Google Pub/Sub publisher

Spring Framework on Google Cloud provides PubSubTemplate. Simple example publishing a JSON envelope:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.cloud.spring.pubsub.core.PubSubTemplate;
import com.google.cloud.spring.pubsub.support.GcpPubSubHeaders;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.Map;

public class PubSubEventPublisher implements EventPublisher {

    private final PubSubTemplate pubSubTemplate;
    private final ObjectMapper mapper;
    private final String topic;

    public PubSubEventPublisher(
            PubSubTemplate pubSubTemplate,
            ObjectMapper mapper,
            String topic) {
        this.pubSubTemplate = pubSubTemplate;
        this.mapper = mapper;
        this.topic = topic;
    }

    @Override
    public CompletionStage<Void> publish(OutboxRecord event) {
        try {
            String payload = mapper.writeValueAsString(event.envelope());

            Map<String, String> headers = Map.of(
                    "eventId", event.eventId().toString(),
                    GcpPubSubHeaders.ORDERING_KEY, event.aggregateId());

            return pubSubTemplate.publish(topic, payload, headers)
                    .thenApply(messageId -> null);
        }
        catch (Exception ex) {
            return CompletableFuture.failedFuture(ex);
        }
    }
}
~~~

Include eventId in both payload and headers so consumers can deduplicate. The ORDERING_KEY header uses aggregate_id; enable message ordering on the publisher and configure a regional endpoint when multiple publishers must share ordering. This example uses the CompletableFuture-returning publish API from Spring Framework on Google Cloud 5.6.x; older releases returning ListenableFuture should bridge via the corresponding callback.

Pub/Sub supports exactly-once delivery for pull subscriptions within the same region. That confirms ACKs and suppresses certain redeliveries of the same Pub/Sub message ID; it does not stop a producer from publishing the same event twice with two different message IDs. An inbox keyed by business eventId remains necessary.

### 8.4. Azure Service Bus publisher

You can use the Azure SDK for Java or Spring Messaging Azure Service Bus. SDK example:

~~~java
import com.azure.messaging.servicebus.ServiceBusMessage;
import com.azure.messaging.servicebus.ServiceBusSenderClient;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class ServiceBusEventPublisher implements EventPublisher {

    private final ServiceBusSenderClient sender;
    private final ObjectMapper mapper;

    public ServiceBusEventPublisher(
            ServiceBusSenderClient sender,
            ObjectMapper mapper) {
        this.sender = sender;
        this.mapper = mapper;
    }

    @Override
    public CompletionStage<Void> publish(OutboxRecord event) {
        try {
            String body = mapper.writeValueAsString(event.envelope());

            ServiceBusMessage message = new ServiceBusMessage(body)
                    .setMessageId(event.eventId().toString())
                    .setSubject(event.eventType())
                    .setCorrelationId(event.correlationId());

            sender.sendMessage(message);
            return CompletableFuture.completedFuture(null);
        }
        catch (Exception ex) {
            return CompletableFuture.failedFuture(ex);
        }
    }
}
~~~

This synchronous example is wrapped in a CompletionStage to illustrate the contract; production adapters should use an async sender if the relay needs high concurrency. Build the sender with ServiceBusClientBuilder and DefaultAzureCredential rather than hardcoding SAS connection strings.

When duplicate detection is enabled on a queue/topic, MessageId must remain stable across retries. When using Service Bus Sessions to preserve per-aggregate ordering, set SessionId to aggregate_id and configure the entity to support sessions.

### 8.5. Spring configuration and workload identity

- AWS: use SqsAsyncClient configured with region and default credentials provider; runtime role needs sqs:SendMessage on the exact queue.
- GCP: use ADC/service account or Workload Identity; publisher needs roles/pubsub.publisher on the topic.
- Azure: use managed identity/workload identity; principal needs Azure Service Bus Data Sender at queue/topic scope.

Never store access keys, service account JSON, or SAS connection strings in source code. Use a secret manager/secret store if any credentials must be configured.

## 9. Preserving Event Ordering per Aggregate

### 9.1. Why ORDER BY created_at is not enough

Two relay workers can claim two events for the same aggregate and publish them out of order:

~~~text
Order-42, version 10 -> worker A (slow publish)
Order-42, version 11 -> worker B (fast publish)
Broker receives version 11 before version 10
~~~

If consumers apply state blindly in arrival order, data can regress or become inconsistent.

### 9.2. Ordering mechanisms

- Assign monotonically increasing aggregate_version in the same transaction as the aggregate update.
- Claim the next event of an aggregate only after prior events have been published.
- Partition or group by aggregate_id.
- Consumers check versions and reject out-of-order stale updates.
- When ordering is unnecessary, allow parallel processing to increase throughput.

Providers offer specific mechanisms:

| Provider | Mechanism |
| --- | --- |
| SQS FIFO | MessageGroupId = aggregate_id; messages within a group are processed in order |
| Pub/Sub | Ordering key = aggregate_id; requires enabling ordering and same region |
| Azure Service Bus | Sessions; SessionId = aggregate_id |

Broker ordering only governs ordering according to broker semantics. If the relay already published version 11 before version 10, the broker cannot retroactively restore original order. The relay must enforce publish sequencing or consumers must verify aggregate versions.

### 9.3. Claiming the next event

An illustrative approach is skipping an event if an earlier unpublished event exists for the same aggregate:

~~~sql
SELECT o.event_id
FROM outbox_events o
WHERE o.published_at IS NULL
  AND o.status = 'PENDING'
  AND o.next_attempt_at <= now()
  AND NOT EXISTS (
      SELECT 1
      FROM outbox_events earlier
      WHERE earlier.aggregate_type = o.aggregate_type
        AND earlier.aggregate_id = o.aggregate_id
        AND earlier.aggregate_version < o.aggregate_version
        AND earlier.published_at IS NULL
  )
ORDER BY o.created_at
LIMIT :batch_size
FOR UPDATE SKIP LOCKED;
~~~

This is illustrative SQL; in practice, combine it with lease updates in the same claim transaction. If an earlier event transitions to DEAD, establish a clear policy: block the aggregate, skip with audit, or fix/replay the earlier event. Never let a dead event silently stall the system indefinitely.

## 10. Consumer Inbox and Idempotent Processing

### 10.1. Inbox schema

The consumer tracks processed events keyed by consumer name and event ID:

~~~sql
CREATE TABLE processed_messages (
    consumer_name  VARCHAR(128) NOT NULL,
    event_id       UUID NOT NULL,
    processed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    outcome        VARCHAR(32) NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

consumer_name allows multiple independent consumers to process the same event. For example, billing-projection and search-indexer can both consume OrderCreated while maintaining separate inboxes.

### 10.2. Inserting into the inbox and updating business state in one transaction

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderEventConsumer {

    private final JdbcTemplate jdbc;
    private final CustomerProjectionRepository projection;

    public OrderEventConsumer(
            JdbcTemplate jdbc,
            CustomerProjectionRepository projection) {
        this.jdbc = jdbc;
        this.projection = projection;
    }

    @Transactional
    public void handle(EventEnvelope<OrderCreatedPayload> event) {
        int inserted = jdbc.update("""
                INSERT INTO processed_messages (
                    consumer_name, event_id, outcome
                )
                VALUES (?, ?, 'STARTED')
                ON CONFLICT (consumer_name, event_id) DO NOTHING
                """,
                "billing-projection",
                event.eventId());

        if (inserted == 0) {
            return;
        }

        projection.applyOrderCreated(event.payload());

        jdbc.update("""
                UPDATE processed_messages
                SET outcome = 'COMPLETED',
                    processed_at = now()
                WHERE consumer_name = ?
                  AND event_id = ?
                """,
                "billing-projection",
                event.eventId());
    }
}
~~~

Both the inbox insert and business update run inside the same transaction:

- If the business update fails, the inbox insert rolls back; the broker can redeliver for retry.
- If the transaction commits and the process crashes before ACK, the broker redelivers; the inbox insert conflicts and the consumer skips the side effect.
- If the event is sent twice with the same event ID, the consumer applies the business update only once.

ON CONFLICT DO NOTHING returns 0 affected rows when the event has already been recorded. Adapt unique conflict handling to your database.

### 10.3. ACK after commit

The listener invokes a @Transactional service through a Spring proxy. When the method returns, the transaction has committed (or thrown an exception). Only ACK/complete the message after the method returns successfully.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant L as Listener
    participant S as Consumer service
    participant DB as Database

    B->>L: Deliver event E
    L->>S: handle(E)
    S->>DB: INSERT inbox(E)
    S->>DB: Apply business update
    S->>DB: COMMIT
    S-->>L: Success
    L->>B: ACK / Complete
    Note over L,B: If crash before ACK, E is redelivered
    B->>L: Redeliver E
    L->>S: handle(E)
    S->>DB: INSERT inbox(E) -> conflict
    S-->>L: No-op success
    L->>B: ACK / Complete
~~~

Never ACK before the transaction commits. Never swallow exceptions from the consumer service and return success to the listener if the database did not commit.

## 11. Spring Boot Consumers for the Three Brokers

### 11.1. AWS SQS with Spring Cloud AWS

Dependencies use the compatible Spring Cloud AWS BOM and SQS starter:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>YOUR_COMPATIBLE_SPRING_CLOUD_AWS_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-sqs</artifactId>
    </dependency>
</dependencies>
~~~

The default ON_SUCCESS listener acknowledges messages after successful processing:

~~~java
import io.awspring.cloud.sqs.annotation.SqsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderSqsListener {

    private final EventDeserializer deserializer;
    private final OrderEventConsumer consumer;

    public OrderSqsListener(
            EventDeserializer deserializer,
            OrderEventConsumer consumer) {
        this.deserializer = deserializer;
        this.consumer = consumer;
    }

    @SqsListener("${app.queues.order-events}")
    public void receive(String body) {
        EventEnvelope<OrderCreatedPayload> event =
                deserializer.orderCreated(body);

        consumer.handle(event);
    }
}
~~~

If consumer.handle throws an exception, the listener fails and SQS can redeliver after the visibility timeout. Configure a redrive policy to move messages to a DLQ after max receives. With manual acknowledgement listeners, call acknowledge() only after the service transaction has committed.

### 11.2. Google Pub/Sub

Dependencies use the Spring Framework on Google Cloud Pub/Sub starter. The Spring Integration adapter can be set to AckMode.MANUAL:

~~~java
import com.google.cloud.spring.pubsub.core.PubSubTemplate;
import com.google.cloud.spring.pubsub.integration.AckMode;
import com.google.cloud.spring.pubsub.integration.inbound.PubSubInboundChannelAdapter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration(proxyBeanMethods = false)
public class OrderPubSubConfiguration {

    @Bean
    MessageChannel orderEventsChannel() {
        return new DirectChannel();
    }

    @Bean
    PubSubInboundChannelAdapter orderEventsAdapter(
            MessageChannel orderEventsChannel,
            PubSubTemplate pubSubTemplate) {

        PubSubInboundChannelAdapter adapter =
                new PubSubInboundChannelAdapter(
                        pubSubTemplate,
                        "order-events-subscription");

        adapter.setOutputChannel(orderEventsChannel);
        adapter.setAckMode(AckMode.MANUAL);
        return adapter;
    }
}
~~~

The handler executes the consumer transaction before ACKing:

~~~java
import com.google.cloud.spring.pubsub.support.BasicAcknowledgeablePubsubMessage;
import com.google.cloud.spring.pubsub.support.GcpPubSubHeaders;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class OrderPubSubHandler {

    private final EventDeserializer deserializer;
    private final OrderEventConsumer consumer;

    public OrderPubSubHandler(
            EventDeserializer deserializer,
            OrderEventConsumer consumer) {
        this.deserializer = deserializer;
        this.consumer = consumer;
    }

    @ServiceActivator(inputChannel = "orderEventsChannel")
    public void receive(Message<String> message) {
        BasicAcknowledgeablePubsubMessage original =
                message.getHeaders().get(
                        GcpPubSubHeaders.ORIGINAL_MESSAGE,
                        BasicAcknowledgeablePubsubMessage.class);

        EventEnvelope<OrderCreatedPayload> event =
                deserializer.orderCreated(message.getPayload());

        consumer.handle(event);
        original.ack();
    }
}
~~~

If consumer.handle throws an exception, do not ACK. Configure a retry policy and dead-letter topic on the subscription. Exactly-once delivery only applies to pull subscriptions within the same region; keep the inbox because producers can still publish duplicate events with different message IDs.

### 11.3. Azure Service Bus

Spring Cloud Azure provides @ServiceBusListener and listener containers. Example:

~~~java
import com.azure.spring.messaging.servicebus.annotation.ServiceBusListener;
import org.springframework.stereotype.Component;

@Component
public class OrderServiceBusListener {

    private final EventDeserializer deserializer;
    private final OrderEventConsumer consumer;

    public OrderServiceBusListener(
            EventDeserializer deserializer,
            OrderEventConsumer consumer) {
        this.deserializer = deserializer;
        this.consumer = consumer;
    }

    @ServiceBusListener(destination = "order-events")
    public void receive(String body) {
        EventEnvelope<OrderCreatedPayload> event =
                deserializer.orderCreated(body);

        consumer.handle(event);
    }
}
~~~

In Peek-Lock mode, the listener container settles the message after the handler succeeds according to the configured version behavior. When the consumer transaction throws an exception, the message should be abandoned or have its lock expire so the broker redelivers it or moves it to the DLQ per delivery count. Verify auto-complete/settlement modes for your Spring Cloud Azure version; do not assume identical behavior to SQS or Pub/Sub.

### 11.4. Configuring consumer identities

| Provider | Consumer permission |
| --- | --- |
| AWS SQS | sqs:ReceiveMessage, sqs:DeleteMessage, sqs:GetQueueAttributes on queue |
| Google Pub/Sub | roles/pubsub.subscriber on subscription |
| Azure Service Bus | Azure Service Bus Data Receiver on queue/subscription |

Use IAM roles, Workload Identity, or managed identities per runtime. Never grant broker administration permissions to a consumer just to receive messages.

## 12. Idempotency Outside the Database

### 12.1. The inbox only protects database transactions

Suppose a consumer executes:

1. Write inbox and update projection in the database.
2. Call a payment gateway.
3. ACK the message.

If the process dies after step 2 but before ACK, the message is redelivered. The inbox may indicate the event was handled and skip the entire handler, even though the payment gateway never returned or its side effect already occurred.

Solutions:

- Pass an idempotency key derived from event_id or business operation ID to the downstream API.
- Persist the result/operation state of external calls.
- Use a second outbox to dispatch commands to an integration worker.
- For multi-service workflows, design sagas/compensations.
- If downstream lacks idempotency support, build reconciliation and uncertain-state handling workflows.

### 12.2. Idempotency keys must represent business intent

Never generate a current timestamp or new random UUID on every retry. The key must be generated once and kept identical across all attempts.

Example:

~~~text
event_id = 6e4b2a5e-4f87-4c4d-a37a-31c2d8e0a9b4
payment_operation_key = capture:order-4821:version-3
thumbnail_key = document-91:generation-1730000000000000
~~~

One event can trigger multiple side effects; each side effect needs its own key if it has an independent lifecycle and retry path.

### 12.3. Idempotency at the HTTP command boundary

If a client retries POST /orders due to a timeout, the application might create two orders and two distinct events. Use an idempotency key at the API boundary:

- Client sends Idempotency-Key.
- Server stores the key, request hash, and response in the same transaction as the order/outbox.
- Repeated requests with the same key and same payload return the stored result.
- Same key with a different payload returns a conflict error.
- A unique constraint protects against concurrent duplicate requests.

The outbox guarantees order and event commit together; the API idempotency key protects order creation before the outbox is ever relayed.

## 13. Broker Deduplication Does Not Replace the Consumer Inbox

Providers offer duplicate-reduction features, each with different limits:

| Provider | Mechanism | Scope / limits |
| --- | --- | --- |
| SQS Standard | At-least-once | May deliver duplicate messages; consumers must be idempotent |
| SQS FIFO | MessageDeduplicationId or content-based dedup | 5-minute deduplication interval; MessageGroupId orders within a group |
| Pub/Sub | Optional exactly-once delivery | Pull subscriptions within the same region; duplicate publishes with distinct message IDs can still occur |
| Service Bus | Duplicate detection by MessageId | Standard/Premium; configurable 20-second to 7-day window; primarily guards against producer-side duplicates |

Never claim end-to-end exactly-once semantics just because a queue offers deduplication. A broker cannot know which side effects a database transaction or external API already committed.

The inbox remains necessary to handle:

- Producers republishing the same event.
- Relay timeouts where broker receipt is uncertain.
- Consumer crashes after commit before ACK.
- Replays from a DLQ.
- Expired broker deduplication windows.
- Multiple queues/subscriptions receiving the same event.

## 14. Retries, DLQs, and Replays

### 14.1. Three separate retry layers

| Layer | Component | What is retried |
| --- | --- | --- |
| Producer transaction | HTTP/client command | Retry business creation using API idempotency keys |
| Outbox relay | Outbox row | Retry publishing to the broker |
| Consumer | Broker delivery + inbox/job | Retry message processing or side effects |

Do not multiply retry counts unchecked. For example, 5 relay retries × 10 broker deliveries × 5 downstream retries can trigger massive execution amplification.

### 14.2. Error classification

| Error | Handling |
| --- | --- |
| Broker timeout/5xx/throttling | Relay retry with exponential backoff + jitter |
| Expired credentials/403 | Alert, fix identity; cap retries and avoid tight retry loops |
| Unsupported payload schema | Move to quarantine/DLQ, preserving event ID and schema version |
| Temporary consumer DB outage | Do not ACK; let broker redeliver |
| Permanent business validation failure | Record REJECTED outcome and ACK after saving result |
| Duplicate event | Inbox conflict; ACK/complete after confirming prior processing |
| Outbox row exceeds retry limit | Mark DEAD, alert, and perform controlled replay |

### 14.3. DLQs are not permanent archives

Configure DLQs per provider:

- SQS: redrive policy and maxReceiveCount.
- Pub/Sub: dead-letter topic and publish/subscribe permissions for the service agent/consumer.
- Service Bus: built-in DLQ; inspect DeadLetterReason and DeadLetterErrorDescription.

Replay procedure:

1. Alert when DLQ or outbox DEAD counts rise.
2. Read metadata and error category; never log secrets.
3. Determine whether the fault is payload, permissions, downstream, or a bug.
4. Fix the root cause.
5. Inspect consumer inbox and business state.
6. Replay with the exact same event_id.
7. Monitor outcomes and write audit records.

If business logic needs to re-run after an event was already successfully processed, issue a new reprocessing command/event with a fresh ID and explicit reason. Never arbitrarily delete old inbox markers because that can re-trigger duplicate side effects.

## 15. Outbox Retention, Cleanup, and Operations

### 15.1. Cleaning up published rows

You do not need to keep outbox rows forever, nor delete them immediately after publishing. Choose retention based on audit requirements and replay needs.

Example deleting rows published more than 14 days ago:

~~~sql
DELETE FROM outbox_events
WHERE published_at < now() - interval '14 days'
  AND status = 'PUBLISHED';
~~~

Run cleanup in batches to avoid huge transactions. If auditing is required, archive rows or retain event metadata in a history table.

Never delete PENDING, IN_FLIGHT, or DEAD rows merely due to age. Establish a reconciliation workflow and business decision process.

### 15.2. Metrics

Monitor:

- outbox_pending_count: events awaiting publish.
- outbox_oldest_pending_age: age of the oldest unpublished event.
- outbox_publish_attempts: publish attempt count.
- outbox_publish_latency: time from commit to broker acceptance.
- outbox_dead_count: rows in DEAD state.
- consumer_duplicate_count: inbox conflict count.
- consumer_processing_latency: event processing duration.
- consumer_retry_count: broker redelivery count.
- consumer_dlq_count: messages moved to DLQ.
- lease_expired_count: expired relay/consumer leases.

### 15.3. Alerts and runbooks

Sample alert conditions:

- Pending outbox grows continuously or oldest pending age breaches SLA.
- Relay lacks heartbeats or has not published successfully for an extended period.
- Outbox DEAD count increases.
- Consumer backlog or age of oldest message increases.
- Sudden spike in DLQ count.
- Abnormal spike in duplicate rate.
- Rising database connection pool saturation or broker throttling.

Runbooks should answer: who owns it, how to look up an event ID, how to inspect broker deliveries, how to replay safely, and how to reconcile business state with consumer projections.

## 16. Event Security and Governance

- Use workload identities instead of long-lived cloud keys.
- Separate producer publisher roles from consumer receiver roles.
- Scope permissions to specific queues/topics.
- Validate event_type, schema_version, tenant, and aggregate ID.
- Never trust client- or event-supplied tenant IDs or URLs without validating against trusted data.
- Omit unnecessary PII/secrets from payloads.
- Encrypt sensitive data and bound retention across outbox, broker, and DLQ.
- Redact payloads/errors in logs.
- Audit replays, purges, manual state overrides, and retry policy changes.
- Verify schema compatibility before deploying mismatched producer/consumer versions.

The outbox holds copies of business events and may be read by relays/operators; apply least-privilege database grants. Consumers only need read permissions on their queues/subscriptions and necessary privileges on their own databases.

## 17. Testing Failure Windows

### 17.1. Producer tests

| Scenario | Expected outcome |
| --- | --- |
| Business insert succeeds, outbox insert succeeds | Both commit |
| Business insert succeeds, outbox insert fails | Both roll back |
| Payload serialization fails | Transaction rolls back |
| Client retries with same idempotency key | No duplicate business record/event created |
| Two concurrent requests with same key | Unique constraint allows only one creation |

### 17.2. Relay tests

- Relay dies before publish: lease expires and event is reclaimed.
- Broker times out: retries with the same event ID.
- Broker accepts message, relay dies before marking published: duplicate publish handled safely by consumer.
- Two relays run concurrently: SKIP LOCKED and leases prevent claiming the same row.
- Lease expires mid-publish: old worker cannot mark the row if lease owner changed.
- Repeated publish failures: event moves to DEAD and triggers an alert.
- Two events for the same aggregate: verify publish order follows aggregate_version.

### 17.3. Consumer tests

- First delivery of an event: inbox and business update commit.
- Duplicate with same event ID: business update does not run a second time.
- Consumer fails before commit: inbox and business update roll back.
- Consumer commits then crashes before ACK: broker redelivers, inbox is a no-op.
- Two consumer instances receive the same event concurrently: unique constraint protects state.
- Unsupported event schema version: quarantined/DLQed.
- External API times out after side effect occurred: retries use the idempotency key.

### 17.4. Integration tests with real brokers

Use a dedicated test database and test queue/topic/subscription:

1. Call API to create a business record.
2. Verify the outbox row committed in the same transaction.
3. Run the relay and verify the message appears in the broker.
4. Send the same event twice.
5. Verify the consumer applies the DB side effect only once.
6. Stop the relay after publish but before marking published; restart and verify the duplicate is handled safely.
7. Stop the consumer after commit before ACK; verify redelivery does not repeat side effects.
8. Make the broker temporarily unavailable; verify outbox retains events and retries.
9. Force consumer failures repeatedly; verify DLQ routing.
10. Replay the same event ID and verify the inbox protects business state.
11. Verify per-aggregate ordering if FIFO/sessions/ordering keys are enabled.
12. Verify metrics, logs, and audit records.

LocalStack, the Pub/Sub emulator, and the Azure Service Bus emulator (where supported) can help test client APIs. IAM/RBAC, deduplication windows, retries, settlement, and managed-service behavior should also be verified against real cloud test accounts.

## 18. Comparing AWS, Google Cloud, and Azure

| Aspect | AWS SQS | Google Pub/Sub | Azure Service Bus |
| --- | --- | --- | --- |
| Spring integration | Spring Cloud AWS / AWS SDK | Spring Framework on Google Cloud | Spring Cloud Azure / Azure SDK |
| Producer permission | sqs:SendMessage | roles/pubsub.publisher | Azure Service Bus Data Sender |
| Consumer permission | Receive/Delete/GetQueueAttributes | roles/pubsub.subscriber | Azure Service Bus Data Receiver |
| Default delivery | Standard: at-least-once | At-least-once | Peek-Lock: at-least-once |
| Producer duplicate reduction | FIFO deduplication ID, 5 minutes | Exactly-once does not deduplicate separate business publishes with different IDs | Duplicate detection by MessageId within configured window |
| Ordering | FIFO MessageGroupId | Ordering key and regional constraints | Sessions/SessionId |
| Consumer settlement | Delete/ACK | ACK/NACK | Complete/Abandon/DeadLetter |
| DLQ | SQS redrive queue | Dead-letter topic | Built-in DLQ |

Key differences:

- SQS FIFO reduces duplicate sends within a 5-minute window; SQS Standard can still deliver duplicates.
- Pub/Sub exactly-once applies only to pull subscriptions in the same region; republishing the same payload can still produce a new message ID.
- Service Bus duplicate detection relies on MessageId within a configured window and does not replace a consumer inbox.
- Ordering keys/groups/sessions only guarantee order within their respective scopes; relays must still publish events in aggregate sequence.
- ACK/settlement semantics differ; never build an abstraction that hides provider settlement failures.

## 19. Comprehensive Hands-On Exercise

**Context:** Build an Order Service in Spring Boot. When a user creates an order, the application must save the order and emit OrderCreated so Billing Service updates its projection. The system must behave correctly when the database, relay, broker, or consumer encounters temporary failures.

### Task A — Business transaction and outbox

1. Create the orders and outbox_events tables.
2. Define the OrderCreated event envelope with eventId, aggregateId, aggregateVersion, eventType, and schemaVersion.
3. Write a @Transactional service saving both the order and outbox row in one transaction.
4. Test an outbox insert failure and verify the order rolls back.

### Task B — Outbox relay

1. Write a polling relay with batch claiming and leases.
2. Publish events via SQS, Pub/Sub, or Service Bus.
3. Mark PUBLISHED only after broker confirmation.
4. Retry transient errors with exponential backoff and jitter.
5. Mark DEAD after retry limits and emit an alert.
6. Test crashing after publish but before updating the outbox.

### Task C — Consumer inbox

1. Create the processed_messages table with primary key (consumer_name, event_id).
2. Insert the inbox marker and update the projection in a single transaction.
3. ACK/complete after the transaction commits.
4. Send the same event twice and verify the projection updates only once.

### Task D — Provider semantics

- SQS: test Standard and FIFO; configure MessageGroupId/MessageDeduplicationId.
- Pub/Sub: configure pull subscriptions; explore exactly-once and ordering keys.
- Service Bus: enable duplicate detection; test MessageId and Sessions.
- Compare retries, settlement, and DLQs.

### Task E — Failure injection

- Kill the relay before publish.
- Kill the relay after publish before marking published.
- Kill the consumer after DB commit before ACK.
- Make the broker unavailable.
- Send an event with an unsupported schema version.
- Replay an event from the DLQ.
- Test two events for the same aggregate arriving concurrently.
- Test API idempotency keys when a client retries order creation.

**Acceptance criteria:** Business state and outbox always commit/roll back together; the relay never loses events across process restarts; duplicate publishes may occur without consumers repeating DB side effects; ACKs occur only after commit; retries/DLQs are bounded and observable; and per-aggregate ordering is preserved when business rules require it.

## 20. Key Takeaways

- Dual writes between a database and a broker create failure windows; @Transactional does not manage broker transactions.
- Transactional outbox writes business state and events in the same database transaction.
- Relays publish after commit and only mark published upon broker confirmation.
- Relays may publish duplicates if they crash after broker acceptance before recording state; keep event IDs stable.
- Polling relays use leases and FOR UPDATE SKIP LOCKED; CDC/Debezium reads the transaction log.
- Debezium Outbox Event Router uses event ID, aggregate type/id, event type, and payload; typically publishing to Kafka.
- Consumer inboxes use a unique constraint keyed by consumer and event ID.
- Inbox inserts and business updates must share the same transaction.
- ACK/complete only after the consumer transaction commits.
- Broker deduplication reduces duplicates but does not replace an idempotent consumer.
- Pub/Sub exactly-once is scoped to same-region pull subscriptions; Service Bus duplicate detection has a time window; SQS FIFO dedup lasts 5 minutes.
- Side effects in external systems require idempotency keys, a downstream outbox, or sagas.
- Preserve order using aggregate versions and partition/group/session keys; relays must publish in sequence.
- Monitor pending outbox counts, oldest event age, relay attempts, consumer duplicates, backlog, and DLQs.
- Replays must be audited and keep the original event ID so the inbox continues recognizing duplicates.

### References

- [Transactional Outbox pattern — Debezium Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html)
- [Spring Framework — Transaction-bound events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Cloud AWS — SQS integration and acknowledgement modes](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html)
- [Amazon SQS — Exactly-once processing in FIFO queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues-exactly-once-processing.html)
- [Amazon SQS — Message deduplication and grouping](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-key-terms.html)
- [Google Cloud Pub/Sub — Exactly-once delivery](https://docs.cloud.google.com/pubsub/docs/exactly-once-delivery)
- [Google Cloud Pub/Sub — Message ordering](https://docs.cloud.google.com/pubsub/docs/ordering)
- [Spring Framework on Google Cloud — Pub/Sub](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/index.html)
- [Spring Framework on Google Cloud — Pub/Sub template and ordering keys](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/pubsub.html)
- [Spring Framework on Google Cloud 5.6.1 — PubSubTemplate API](https://googleapis.dev/java/spring-cloud-gcp/5.6.1/com/google/cloud/spring/pubsub/core/PubSubTemplate.html)
- [Azure Service Bus — Duplicate detection](https://learn.microsoft.com/en-us/azure/service-bus-messaging/duplicate-detection)
- [Azure Service Bus — Prevent message loss and duplicate processing](https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-message-loss-and-duplicates)
- [Azure Service Bus Java — ServiceBusSenderClient](https://learn.microsoft.com/en-us/java/api/com.azure.messaging.servicebus.servicebussenderclient?view=azure-java-stable)
- [Azure Service Bus Java — ServiceBusMessage](https://learn.microsoft.com/en-us/java/api/com.azure.messaging.servicebus.servicebusmessage?view=azure-java-stable)
- [Spring Cloud Azure — Spring Messaging for Service Bus](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/spring-messaging-service-bus-support)
