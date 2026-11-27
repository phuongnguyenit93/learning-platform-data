# Transactional Outbox Pattern and Relay Integration

A Spring service frequently needs to update business data in a database and then emit an event so other services learn about that change. For example, when creating an order, the order service both writes the order to the database and emits `OrderCreated` to Kafka, RabbitMQ, or Pulsar. If these two operations are performed independently, the system can end up with the database committed while the message was never sent, or the message sent while the database rolled back.

Transactional outbox closes this gap by writing business data and the event record inside the same database transaction. A relay reads committed outbox records and sends them to the broker. Because the database transaction does not automatically encompass the broker, the relay may resend when the outcome is uncertain; consumers therefore need idempotency to handle duplicate messages safely.

In the Spring ecosystem, Spring Boot manages transactions and application configuration, Spring Data can persist the outbox, and Spring Cloud Stream provides bindings and binders so the relay can send events to Kafka, RabbitMQ, or any broker with a compatible binder. This lesson covers outbox table design, recording events within the business transaction, building a relay via polling or CDC, handling retries and ordering, integrating with Spring Cloud Stream, testing, and operations.

## Learning Objectives

After this lesson, you will be able to:

- Explain dual-write failures when updating a database and sending a message in two independent operations.
- Design an outbox table storing event ID, aggregate, schema, payload, and send status.
- Write business data and the outbox record in the same transaction.
- Compare a polling relay with Change Data Capture (CDC).
- Use Spring Cloud Stream or `StreamBridge` to send events from the relay to a destination.
- Design claims, leases, retries, and recovery when a relay stops mid-flight.
- Preserve per-aggregate ordering and understand the limits of partition keys.
- Combine outbox with inbox/idempotent consumers to handle at-least-once delivery.
- Test transactions, relays, broker failures, and replay capabilities.

## 1. The Dual-Write Problem

Suppose an order-creation service performs two operations:

1. Save the order to the database.
2. Send an `OrderCreated` event to the broker.

A simple snippet might look like this:

~~~java
@Transactional
public void createOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(Order.from(command));
    streamBridge.send("orders-out-0", toMessage(order));
}
~~~

The `@Transactional` annotation only manages transactions controlled by the database transaction manager. Sending a message to the broker does not automatically become part of the database transaction. Thus, two failure windows arise:

| Sequence | Possible outcome |
|---|---|
| Database commit succeeds, broker send fails | The order exists, but other services never receive `OrderCreated` |
| Broker receives message, database rolls back | Other services process an order that was never successfully created |
| Broker received it, but producer times out before knowing the result | Relay or application may resend, creating a duplicate message |
| Application stops between the two operations | Outcome depends on which operation finished |

This is the dual-write problem: two independent storage systems must be updated as a single business change without one atomic transaction spanning both.

Distributed transactions can be used in some architectures, but coordinating transactions between a database and a broker increases complexity, depends on each system's support, and affects operability. Transactional outbox is a common pattern to eliminate the gap between committing business data and recording the intent to publish an event.

## 2. Transactional Outbox Principles

Instead of sending a message directly inside the business transaction, the application writes an outbox record:

~~~text
Single database transaction:
  1. INSERT order
  2. INSERT OrderCreated event into outbox
  3. COMMIT

Separate relay process:
  1. Read committed outbox events
  2. Send events to broker
  3. Mark events as published after appropriate confirmation
~~~

Both records commit together. If the transaction rolls back, neither the order nor the outbox event exists. If the transaction commits, the event is durably persisted in the database so the relay can send it later, even if the broker is temporarily unavailable.

Transactional outbox does not make the database and broker commit in one distributed transaction. It guarantees the application cannot commit a business change while forgetting to record the event that must be published. The relay is responsible for forwarding persisted events to the broker.

~~~mermaid
flowchart TD
    A[Create order request] --> B[Database transaction]
    B --> C[INSERT Order]
    B --> D[INSERT Outbox Event]
    C --> E[COMMIT same transaction]
    D --> E
    E --> F[Outbox Relay]
    F --> G[Publish via Spring Cloud Stream]
    G --> H[(Kafka / RabbitMQ / Pulsar)]
    H --> I[Consumer]
    I --> J[Idempotent business processing]
~~~

## 3. Designing the Outbox Table

An outbox table must store enough information for the relay to resend the event without reconstructing the payload from the aggregate's current state.

Example PostgreSQL schema:

~~~sql
CREATE TABLE outbox_event (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(120) NOT NULL,
    aggregate_id VARCHAR(160) NOT NULL,
    aggregate_version BIGINT,
    event_type VARCHAR(160) NOT NULL,
    schema_version INTEGER NOT NULL,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    locked_by VARCHAR(120),
    locked_until TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    last_error TEXT,
    CONSTRAINT outbox_status_check
        CHECK (status IN ('PENDING', 'PROCESSING', 'PUBLISHED', 'FAILED'))
);

CREATE INDEX outbox_pending_idx
    ON outbox_event (next_attempt_at, created_at)
    WHERE status = 'PENDING';

CREATE INDEX outbox_lease_idx
    ON outbox_event (locked_until)
    WHERE status = 'PROCESSING';

CREATE UNIQUE INDEX outbox_aggregate_version_idx
    ON outbox_event (aggregate_type, aggregate_id, aggregate_version)
    WHERE aggregate_version IS NOT NULL;
~~~

Key fields:

| Field | Role |
|---|---|
| event_id | Stable, unique ID for an event |
| aggregate_type, aggregate_id | Identifies the aggregate producing the event |
| aggregate_version | Event version or sequence within the aggregate |
| event_type | Event type name, e.g. OrderCreated |
| schema_version | Payload contract version |
| payload | Serialized snapshot of event data |
| occurred_at | Business timestamp when the event occurred |
| status | Relay processing status |
| attempts, next_attempt_at | Attempt count and next eligible retry time |
| locked_by, locked_until | Lease for the currently processing worker |
| published_at | Timestamp when the relay recorded the event as published |
| last_error | Most recent error details for investigation |

The schema above is a reference design. Database engine, storage scale, CDC usage, and auditing requirements may lead to a different structure. For example, when using CDC, per-row status updates like those in a polling relay may not be needed; the connector tracks the transaction log and its own offsets.

### 3.1. Storing an Event Snapshot

The payload should represent the required data at the time the event occurred. Do not store only an aggregate ID and let the relay reload the current entity to construct the event, because the entity may have changed before the relay runs.

For example, `OrderCreated` should contain `orderId`, `customerId`, total amount, and currency at creation time. If the relay reads the order later, it might capture updated or deleted state by mistake.

An event should be treated as immutable once the business transaction commits. If the payload needs changes, emit a new event or apply a deliberate migration/schema versioning strategy.

### 3.2. Event ID and Aggregate Version

`event_id` identifies a single event occurrence and must remain unchanged when the relay retries. Do not generate a new event ID on each resend, or consumers will fail to recognize it as the same event.

`aggregate_version` can be used to validate event ordering per aggregate. For example, `OrderCreated` has version 1, `PaymentAuthorized` has version 2, and `OrderShipped` has version 3. Consumers can detect out-of-order arrivals or missing versions.

Not every domain needs a separate version. If strict ordering is required, clearly define how versions are assigned within the same transaction that updates the aggregate.

## 4. Writing the Outbox in the Same Business Transaction

The business service performs two database operations in the same transaction: saving the aggregate and saving the event to the outbox.

~~~java
@Service
class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final OutboxRepository outboxRepository;
    private final ObjectMapper objectMapper;

    OrderApplicationService(
            OrderRepository orderRepository,
            OutboxRepository outboxRepository,
            ObjectMapper objectMapper) {
        this.orderRepository = orderRepository;
        this.outboxRepository = outboxRepository;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public void createOrder(CreateOrderCommand command) {
        Order order = orderRepository.save(Order.create(command));

        OrderCreated event = new OrderCreated(
                UUID.randomUUID(),
                order.getId(),
                order.getCustomerId(),
                order.getTotal(),
                Instant.now());

        outboxRepository.save(OutboxEvent.pending(
                event.eventId(),
                "Order",
                order.getId(),
                order.getVersion(),
                "OrderCreated",
                1,
                writeJson(event),
                event.occurredAt()));
    }

    private String writeJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("Cannot serialize outbox event", ex);
        }
    }
}
~~~

The classes `Order`, `OrderCreated`, and `OutboxEvent` in the example are illustrative models. The core requirement is that both `orderRepository.save` and `outboxRepository.save` participate in the same database transaction manager. If event serialization fails, the transaction must roll back so an order is not created without its outbox event.

Do not call `StreamBridge.send` inside this transaction expecting the database and broker to roll back together. The relay must run after the outbox row has committed.

### 4.1. Defining Clear Transaction Boundaries

A transaction should perform only the database operations needed to keep the aggregate and outbox row consistent. Do not hold a database transaction open while waiting on a broker or making network calls.

Reasons:

- Long transactions hold locks longer and increase contention.
- A slow broker can prolong database transactions.
- Broker timeouts and database timeouts may not align.
- Rolling back the database cannot retract a message already received by the broker.

Therefore, a relay typically has at least two transaction boundaries: one transaction claims the record, then sends the message outside the transaction; finally, another transaction updates the send status or retry schedule.

## 5. Integrating the Relay with Spring Cloud Stream

The relay reads outbox events and emits messages to an output binding. Spring Cloud Stream allows applications to send messages dynamically using `StreamBridge` or using a bound producer function.

### 5.1. Declaring the Output Binding

Example configuration:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: orders-out-0
      bindings:
        orders-out-0:
          destination: orders.events
          content-type: application/json
~~~

With the Kafka binder, `destination` usually maps to a topic. With the Rabbit binder, the binder maps `destination` to an exchange and queues/bindings per configuration. Other binders use the corresponding resources of their broker.

### 5.2. Sending Messages with StreamBridge

Example relay sending an outbox event:

~~~java
@Component
class StreamBridgeEventPublisher {

    private final StreamBridge streamBridge;

    StreamBridgeEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean send(OutboxEvent event) {
        Message<String> message = MessageBuilder
                .withPayload(event.payload())
                .setHeader("eventId", event.eventId().toString())
                .setHeader("eventType", event.eventType())
                .setHeader("aggregateId", event.aggregateId())
                .setHeader("schemaVersion", event.schemaVersion())
                .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
                .build();

        return streamBridge.send("orders-out-0", message);
    }
}
~~~

`StreamBridge` is useful when destinations are selected at runtime or when the relay sends multiple event types through configured bindings. If the application has only a single fixed output binding, a `Supplier`/`Function` can represent the producer source in the functional model.

**Note on send confirmation:** the boolean value returned by `StreamBridge.send` indicates the message was sent to the application channel according to that API. Do not assume `true` means the broker durably persisted the message or confirmed publishing. How the final send result is received depends on the binder and producer client. If the outbox `PUBLISHED` status must mean the broker confirmed receipt, the publishing adapter must wait for or observe the confirmation/acknowledgement mechanism appropriate for the binder in use.

### 5.3. Decoupling the Publisher Contract from the Relay

To keep the relay independent of per-broker details, define an interface:

~~~java
public interface OutboxEventPublisher {
    void publishAndConfirm(OutboxEvent event);
}
~~~

The `publishAndConfirm` contract only completes normally when the adapter reaches the confirmation level required by the application. If the outcome cannot be determined, the adapter should throw an exception or return an indeterminate status so the relay does not prematurely mark the event as `PUBLISHED`.

Implementations can use Kafka producer callbacks/futures, RabbitMQ publisher confirms, or Pulsar's corresponding API. When using Spring Cloud Stream, check how your specific binder and version expose producer results; do not assume one uniform confirmation API across all binders.

## 6. Building a Polling Relay

A polling relay periodically looks for pending outbox rows, claims a batch, sends each event, and updates the result. This pattern is easy to implement with Spring Data/JDBC and works across many broker types.

### 6.1. Claiming with a Lease

If multiple relay instances read the same outbox table, they must coordinate so they do not process the same record simultaneously. PostgreSQL row locks with `SKIP LOCKED` can be used, followed by updating status to `PROCESSING` and setting a lease.

Example SQL:

~~~sql
WITH candidates AS (
    SELECT event_id
    FROM outbox_event
    WHERE
        (status = 'PENDING' AND next_attempt_at <= now())
        OR
        (status = 'PROCESSING' AND locked_until < now())
    ORDER BY created_at
    LIMIT :batch_size
    FOR UPDATE SKIP LOCKED
)
UPDATE outbox_event AS event
SET status = 'PROCESSING',
    locked_by = :worker_id,
    locked_until = :lease_until,
    attempts = event.attempts + 1
FROM candidates
WHERE event.event_id = candidates.event_id
RETURNING event.*;
~~~

This SQL snippet illustrates the claim mechanism using PostgreSQL syntax. The entire statement must execute in a short transaction and commit before the relay sends messages. `SKIP LOCKED` lets other workers pick up unlocked rows instead of blocking behind the first worker.

A time-bounded lease enables recovery when a worker dies after claiming. Once the lease expires, another worker can reclaim the `PROCESSING` record. The lease duration should exceed normal processing time or be renewed during long-running operations.

### 6.2. Sending Outside the Claim Transaction

The processing flow should have three stages:

1. Claim a batch in transaction A and commit.
2. Send messages to the broker outside transaction A.
3. For each event, open transaction B to mark `PUBLISHED` or schedule a retry.

Sketch example:

~~~java
@Component
class OutboxRelay {

    private final OutboxClaimService claimService;
    private final OutboxEventPublisher publisher;
    private final OutboxStateService stateService;

    OutboxRelay(
            OutboxClaimService claimService,
            OutboxEventPublisher publisher,
            OutboxStateService stateService) {
        this.claimService = claimService;
        this.publisher = publisher;
        this.stateService = stateService;
    }

    @Scheduled(fixedDelay = 500)
    public void relayBatch() {
        List<OutboxEvent> events = claimService.claimBatch(100);

        for (OutboxEvent event : events) {
            try {
                publisher.publishAndConfirm(event);
                stateService.markPublished(event.eventId());
            } catch (Exception ex) {
                stateService.scheduleRetry(event.eventId(), ex);
            }
        }
    }
}
~~~

`claimService` and `stateService` should manage their own transactions. Do not wrap the entire `relayBatch` method in a single transaction if doing so holds database locks for the entire broker wait.

This is an architectural skeleton, not a complete implementation. Timeouts, lease handling, logging, metrics, shutdown, and retry policies must be added. If the publisher cannot determine whether the broker received the message, the relay must treat the outcome as uncertain and allow retries; consumers eliminate duplicate effects using the event ID.

### 6.3. Why Is a Lease Necessary?

Suppose worker A claims an event and the process stops before sending. If the record stayed in `PROCESSING` forever, the event would never be sent. A lease lets worker B pick up the event after `locked_until` expires.

Leases must also guard against worker A taking too long while worker B has already reclaimed the record. Use a sufficiently long lease, periodic renewal, or a fencing token/version per claim. When updating state, the worker should verify `locked_by` or the claim token still belongs to it so an old worker cannot overwrite a newer worker's state.

## 7. Delivery Semantics: At-Least-Once and Duplicate Messages

An outbox relay typically provides at-least-once delivery because the following scenario can occur:

1. Relay sends the event and the broker receives it.
2. Relay stops before updating the outbox row to `PUBLISHED`.
3. Lease expires and another worker resends the same event.

The message is published twice even though the broker received it on the first attempt. This is a consequence of the relay being unable to make publishing atomic with the database transaction.

Do not try to solve this by marking `PUBLISHED` before sending. That risks losing events if the relay stops after committing the status update but before the broker receives the message.

The right design accepts controlled duplicates:

- Keep `event_id` stable across all retries.
- Give the consumer an inbox or processed-event table to detect already-processed events.
- Record the event ID marker and update business data in the same consumer transaction.
- Only ack/commit the message after the consumer transaction succeeds per the binder mechanism.

## 8. Idempotent Consumers and the Inbox Pattern

The inbox pattern adds a table tracking processed events:

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(120) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

The consumer uses the event ID to ensure the same logical consumer does not apply the business effect twice:

~~~java
@Transactional
public void handle(OrderCreated event) {
    boolean firstDelivery = processedEventRepository.insertIfAbsent(
            "billing-service", event.eventId());

    if (!firstDelivery) {
        return;
    }

    billingService.createInvoice(event.orderId(), event.total());
}
~~~

`insertIfAbsent` must be implemented with an atomic operation, such as `INSERT ... ON CONFLICT DO NOTHING` and checking the inserted row count. If the event ID already exists, the consumer skips the business effect.

Recording `processed_event` and updating the invoice must be in the same database transaction. If the transaction rolls back, the inbox marker also rolls back, allowing redeliveries to reprocess. If it commits, duplicate messages are detected.

An inbox does not automatically guarantee exactly-once for side effects outside the database, such as sending emails or calling payment APIs. Those side effects need idempotency keys, a downstream outbox, or an appropriate coordination mechanism.

## 9. Preserving Order per Aggregate

The outbox table may contain multiple events for the same aggregate. If the relay runs multiple workers or sends concurrently, event version 2 could reach the broker before version 1.

Example:

~~~text
Order 100:
  version 1: OrderCreated
  version 2: PaymentAuthorized
  version 3: OrderShipped
~~~

If this ordering matters, ensure:

- `aggregate_version` is assigned inside the transaction updating the aggregate.
- The relay does not send a newer event before an older event of the same aggregate is confirmed.
- The broker partition key is `aggregate_id` so events of the same aggregate go to the same partition or queue partition.
- Consumers process sequentially within the key scope when business rules require it.

Kafka: use `aggregate_id` as the record key or partition key per binder configuration so events for an aggregate are routed to the same partition. Kafka preserves record order within a partition, though concurrent consumer processing can still cause completion order to differ from read order.

RabbitMQ: use a routing/partition key matching partitioned queues in the Rabbit binder. A queue preserves message receipt order, though multiple consumers, prefetch, redeliveries, and varying processing times can alter completion order.

A straightforward strategy for a polling relay is claiming only the earliest unpublished event per aggregate. Subsequent events become eligible only once all prior versions are `PUBLISHED`. This reduces parallelism within a single aggregate while letting different aggregates proceed concurrently.

## 10. Retries, Backoff, and Persistent Failure Events

The relay must classify errors:

| Error type | Example | Action |
|---|---|---|
| Transient | Broker timeout, brief disconnect | Retry with backoff |
| Overload | Broker rejection or producer throttling | Backoff, reduce batch size or send rate |
| Configuration | Invalid credentials, nonexistent destination | Alert and fix configuration |
| Payload/schema | Invalid JSON or incompatible schema | Quarantine, investigate, and fix data |
| Unknown | Timeout after send, unknown if broker received | Retry with the same event ID; consumer must be idempotent |

Backoff can grow with attempt count:

~~~java
Duration retryDelay(int attempts) {
    long exponent = Math.min(attempts, 10);
    long baseMillis = 500L;
    long cappedMillis = Math.min(300_000L, baseMillis * (1L << exponent));
    long jitterMillis = ThreadLocalRandom.current()
            .nextLong(Math.max(1L, cappedMillis / 2));
    return Duration.ofMillis(cappedMillis / 2 + jitterMillis);
}
~~~

This illustrates exponential backoff with jitter. Production systems need a maximum retry count, maximum retry duration, and `next_attempt_at` persisted in the database. Jitter prevents multiple workers from retrying simultaneously once the broker recovers.

### 10.1. FAILED Status and Replay Procedures

Do not delete an outbox record when retries are exhausted. Transition it to `FAILED`, store `last_error`, and raise an alert. Operators or an automated workflow can:

1. Inspect event ID, aggregate, event type, and error.
2. Verify payload and broker health.
3. Fix configuration or data if needed.
4. Reset the event to `PENDING` or trigger a controlled replay command.
5. Monitor consumers to verify duplicate handling.

Do not infinitely replay a malformed payload automatically. Doing so creates error loops, adds load, and obscures valid events.

### 10.2. Relay Retries vs. Consumer Retries

The two retry layers address different failures:

- Relay retries when an event cannot be published to the broker.
- Consumer retries when an event is received but business processing fails.

Do not conflate these two policies. If the broker already received the event and the consumer failed to process it, the relay should not republish the event just because the consumer has not finished. The consumer/broker must apply retries, redelivery, or DLQ per the binder's mechanism.

## 11. Polling Relay vs. CDC Relay

There are two common ways to deliver outbox events to a broker:

| Criterion | Polling relay | CDC relay |
|---|---|---|
| Read mechanism | Query outbox table on a schedule | Read database transaction log |
| Latency | Depends on poll interval and batch | Can be near real-time |
| Row status updates | Usually updates PENDING/PROCESSING/PUBLISHED | May not require row updates after publish |
| Lock/lease | Needed if multiple workers claim concurrently | Connector manages offset/log position |
| Infrastructure | May only need the application and database | Requires CDC connector and operational infrastructure |
| Controllability | Easy to tune batch size, retries, and schedule | Depends on connector and CDC configuration |
| Database impact | Generates periodic read/status-write queries | Reads WAL/binlog and requires appropriate retention |

### 11.1. Polling Relay

A polling relay fits when you want a simple deployment, moderate throughput, or application-level control over sending logic. Design indexes for pending queries, batch sizes, leases, and cleanup policies.

A poll interval that is too short generates unnecessary queries when idle. An interval that is too long increases latency. Choose based on SLAs and event volume.

### 11.2. CDC Relay

Change Data Capture reads changes from the database transaction log such as PostgreSQL WAL or MySQL binlog. A tool like Debezium can watch the outbox table and transform rows into Kafka events. Debezium's Outbox Event Router SMT can map outbox fields such as event type, aggregate ID, and payload into messages.

With CDC, the application still writes the outbox row inside the business transaction. The connector reads changes after the transaction commits. Connector offsets allow resuming from the saved position after restarts.

CDC reduces polling and per-row status updates, but requires operating connectors, transaction log permissions, retention, schemas, and monitoring. If the final destination is RabbitMQ or Pulsar, an appropriate bridge or integration pipeline is needed; do not assume every CDC setup writes directly to every Spring Cloud Stream binder.

### 11.3. Which One to Choose?

Choose polling when you want the relay inside the Spring application, load is not extreme, and the team wants direct control over retries/leases. Choose CDC when you need high throughput, low latency, and already have operational capability for transaction-log connectors.

Both approaches use an outbox table; the primary difference lies in how records are read and forwarded to the broker.

## 12. Testing Transactional Outbox

A test strategy should cover the database transaction, relay, broker, and consumer.

### 12.1. Testing the Outbox Write Transaction

Verify that when creating an order succeeds, the database contains both the order and the outbox row. When the transaction rolls back, neither exists.

~~~java
@SpringBootTest
class OrderOutboxTransactionTest {

    @Autowired
    OrderApplicationService service;

    @Autowired
    OrderRepository orderRepository;

    @Autowired
    OutboxRepository outboxRepository;

    @Test
    void storesOrderAndEventTogether() {
        service.createOrder(new CreateOrderCommand("customer-1", 2500));

        assertThat(orderRepository.count()).isEqualTo(1);
        assertThat(outboxRepository.count()).isEqualTo(1);
    }
}
~~~

This test needs a real test database or Testcontainers to verify the transaction semantics of the deployed DBMS. If the test framework rolls back test transactions at the end of each test method, pay attention to how the service's transaction participates in the test transaction.

### 12.2. Testing the Relay

Mock `OutboxEventPublisher` to verify:

- `PENDING` events are claimed.
- Successful publish transitions status to `PUBLISHED`.
- Failed publish updates `next_attempt_at` and `attempts`.
- Events with expired leases are reclaimed.
- `FAILED` events are not continuously resent outside the replay policy.

Verify the relay does not mark `PUBLISHED` when the publisher only indicates the message entered an internal channel without the broker confirmation required by the application contract.

### 12.3. Testing Against a Real Broker

Use Testcontainers or a dedicated integration environment to verify:

- Kafka topic/partition and record key.
- RabbitMQ exchange, queue, and publisher confirms.
- Pulsar topic, producer send result, and subscription.
- Message contains the correct event ID, event type, schema version, and payload.
- Broker stopping while the relay is sending.
- Relay restarting after the broker received the message but before the row was marked `PUBLISHED`.

The final scenario must prove the consumer eliminates duplicate effects when the relay resends the same event ID.

### 12.4. Testing the Consumer Inbox

Send the same event twice and verify business logic is applied only once. Then simulate a consumer transaction rollback and verify the inbox marker rolls back too, so redeliveries can reprocess it.

## 13. Operations and Outbox Lifecycle Management

Transactional outbox creates a durable data stream inside the database. If the relay stops, the backlog grows. Monitor:

| Metric | Meaning |
|---|---|
| Outbox pending count | Number of events waiting to be sent |
| Oldest pending age | Age of the oldest waiting event |
| Processing count | Number of events currently holding a lease |
| Expired lease count | Number of events needing reclaim |
| Publish success/failure rate | Ratio of successful vs. failed publishes |
| Retry count | Number of resend attempts |
| Failed event count | Number of events requiring investigation |
| Relay batch duration | Time to process a batch |
| Consumer duplicate count | Number of duplicate events detected by the inbox |

### 13.1. Cleaning Up Outbox Data

Do not delete events immediately after successful sending if the system requires auditing, replay, or investigation. Retain them per policy and archive or batch-delete afterward. When using CDC, distinguish outbox table retention from transaction log retention; the connector must read changes before logs are purged.

### 13.2. Payload Security

Outbox payloads may contain personal data or sensitive business information. Apply least-privilege database access, encrypt where required, restrict payload logging, and set appropriate retention. The relay should only have permission to read/update the columns it needs.

### 13.3. Shutdown and Multiple Instances

During relay shutdown, stop claiming new batches. In-flight claimed events are either finished or left for their lease to expire so another worker can pick them up. When running multiple instances, use row locking/leases or CDC offsets to avoid missed events and coordinate progress.

## 14. Common Design Mistakes

1. **Sending to the broker directly inside the database transaction**: assuming both systems commit together. Write the outbox row in the transaction and relay after commit.
2. **Marking PUBLISHED before sending**: a relay crash can lose events. Only update status after appropriate confirmation.
3. **Treating `StreamBridge.send` returning true as durable broker persistence**: that return value alone does not prove broker confirmation. Use a binder-specific confirmation adapter.
4. **Generating a new event ID on retries**: consumers will not recognize duplicates. Preserve the original event ID across all resends.
5. **Running multiple relays without leases or locks**: multiple workers can send the same event concurrently. Claim records atomically.
6. **Holding the database transaction open during network sends**: prolongs locks and increases contention. Separate claim, publish, and state-update transactions.
7. **Not storing a payload snapshot**: the relay might read an aggregate state newer than when the event occurred. Store an immutable payload in the outbox.
8. **Ignoring per-aggregate ordering**: a newer event version may be sent first. Serialize per aggregate and use a stable partition key.
9. **Infinite retries without backoff**: creates heavy load and error storms. Use exponential backoff, jitter, and a `FAILED` status.
10. **Having an outbox without an idempotent consumer**: crashes after publish can create duplicates. Use an inbox or processed-event table with a unique key.
11. **Assuming the inbox covers side effects outside the database**: emails or HTTP calls can still repeat. Use idempotency keys or a downstream outbox.
12. **Not monitoring the backlog**: the relay could stop without anyone noticing. Monitor oldest pending age and publish rates.
13. **Polling too frequently or with oversized batches**: increases database load or ties up relay workers too long. Measure and tune poll intervals, indexes, and batch sizes.
14. **Choosing CDC without monitoring transaction log retention**: connectors can lose their read position when logs are purged. Monitor lag and configure sufficient retention.

## 15. Transactional Outbox Implementation Workflow

When applying this pattern to a Spring Cloud Stream service:

1. Identify which business changes must emit events.
2. Design an immutable event payload, event ID, event type, and schema version.
3. Create the outbox table with statuses, indexes, and necessary retry/lease fields.
4. Write the aggregate and outbox row in the same database transaction.
5. Choose a polling relay or CDC based on load, latency, and operational capability.
6. If polling, design atomic claims, leases, and bounded batches.
7. Configure the output binding/destination and binder for the broker.
8. Define the exact confirmation level required before marking `PUBLISHED`.
9. Use the aggregate ID as the partition/routing key if per-aggregate ordering is needed.
10. Design retries, backoff, `FAILED` handling, and replay procedures.
11. Build an idempotent consumer using an inbox or processed-event table.
12. Test rollbacks, duplicates, broker outages, relay restarts, and ordering.
13. Set up metrics, alerts, retention, and graceful shutdown.

## Conclusion

Transactional outbox lets a service write business changes and the intent to publish an event inside the same database transaction. A relay reads committed events and sends them to the broker through Spring Cloud Stream. A polling relay uses queries, locks, and leases; a CDC relay reads the transaction log with a connector such as Debezium. Both approaches require dedicated operations and monitoring.

An outbox neither eliminates all duplicate messages nor creates an atomic transaction between database and broker. A relay can publish successfully and stop before marking `PUBLISHED`, resulting in a resend. Therefore, keeping event IDs stable, confirming sends per binder semantics, preserving per-aggregate order, and building idempotent consumers are essential parts of a reliable delivery system.

## References

- [Spring Cloud Stream — StreamBridge](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Debezium — Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html)
