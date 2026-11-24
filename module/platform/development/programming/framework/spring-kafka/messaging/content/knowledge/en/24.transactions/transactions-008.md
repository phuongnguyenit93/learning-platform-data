# Sending to Kafka and Updating the Database

A business operation often needs to both update data in a database and emit an event to Kafka. For example, when creating an order, the application saves the order to the database and sends an `OrderCreated` event so inventory, payment, or notification services can continue processing.

These two operations act on two independent storage systems. If the database commits while the Kafka send fails, other services do not know the order was created. If Kafka receives the event while the database transaction rolls back, consumers may process an order that does not exist. This is the *dual write* problem.

To solve it, you must clearly define transaction boundaries and ensure events are not lost if the process stops between the two operations. For Spring Kafka applications using a relational database, the Transactional Outbox is a common choice: save the business change and the intent to emit an event within the same database transaction, then have a relay process forward the event to Kafka.

## 1. Why can two independent writes drift out of sync?

A common initial implementation calls a repository and `KafkaTemplate` inside the same method:

```java
@Service
class OrderService {

    private final OrderRepository orderRepository;
    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    @Transactional
    public Order create(CreateOrder command) {
        Order order = Order.create(command);
        orderRepository.save(order);

        kafkaTemplate.send(
                "orders",
                order.getId().toString(),
                new OrderCreated(order.getId(), order.getCustomerId()));

        return order;
    }
}
```

This snippet does not create an atomic transaction spanning both the database and Kafka. `@Transactional` typically controls the transaction of the transaction manager applied to the method, such as `JpaTransactionManager`. Meanwhile, `KafkaTemplate.send()` dispatches data through a Kafka producer and normally returns an asynchronous result.

Two failure situations can happen:

| Failure sequence | Outcome |
| --- | --- |
| Database commits, then Kafka publish fails | Order exists without an event for other services to process |
| Kafka publish succeeds, then database rolls back | Event was emitted while the business data does not exist |
| Publish returns a future, yet the method does not wait for the result | Database can commit before the application knows publishing failed |

Waiting for the `send()` result with `get()` can help detect publish errors before the method finishes, yet it does not turn the two resources into an atomic transaction. If Kafka already received the record and then the database transaction rolls back, the event still exists. If the database commits and the process stops before sending to Kafka, the event can still be lost.

Therefore, placing both calls in the same Java method or under the same `@Transactional` annotation is not enough to guarantee consistent dual writes.

## 2. Kafka transactions and database transactions have different scopes

Spring Kafka supports transactions for Kafka producers. When a producer participates in a Kafka transaction, multiple records sent within the transaction can commit or abort together. This is useful when a flow needs to publish multiple Kafka records as one unit or when implementing consume-transform-produce with appropriate semantics.

However, a Kafka transaction does not automatically include transactions of PostgreSQL, MySQL, or other relational databases. `KafkaTransactionManager` manages Kafka resources; `JpaTransactionManager` or `DataSourceTransactionManager` manages database resources. Selecting one transaction manager for `@Transactional` does not automatically make the other transaction manager part of the same atomic transaction.

Spring has transaction synchronization mechanisms to coordinate commit ordering between some transaction managers. That coordination can still hit states where one resource commits while the other fails to commit. If true atomic commit across multiple resources is required, you must deploy distributed transactions/XA with supporting resource managers and accept the corresponding cost, configuration, and operational constraints. That is not the default for `KafkaTemplate` and JPA.

Distinguish these three goals:

- **Kafka transaction:** ensures a group of Kafka write operations lies within one Kafka transaction.
- **Database transaction:** ensures changes within the same database commit or roll back together.
- **Consistency between database and Kafka:** requires an explicit coordination mechanism, such as Outbox, CDC, or a fully engineered distributed transaction.

## 3. Transactional Outbox solves dual writes

Transactional Outbox stores the event to be emitted in an outbox table inside the same database as the business data. The business method performs two operations within one database transaction:

1. Write or update the business data, such as the order.
2. Insert an outbox row containing the event ID, event type, aggregate key, and payload to send.

If the transaction commits, both the order and the outbox row exist. If the transaction rolls back, neither exists. A relay process reads unpublished outbox rows and sends them to Kafka.

```text
                  Single database transaction
              +-------------------------------+
Command ----> | UPDATE/INSERT orders           |
              | INSERT outbox_event            |
              +---------------+---------------+
                              |
                         COMMIT / ROLLBACK
                              |
                Relay reads committed outbox
                              |
                              v
                       KafkaTemplate
                              |
                              v
                       Kafka topic
```

The outbox makes the *intent to emit an event* durably stored alongside the business state change. If the application stops after commit, the outbox row remains available for the relay to send when it resumes.

## 4. Designing the outbox table

A basic outbox table might include the following columns:

```sql
CREATE TABLE outbox_event (
    id             VARCHAR(36) PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id   VARCHAR(100) NOT NULL,
    event_type     VARCHAR(150) NOT NULL,
    event_version  INTEGER NOT NULL,
    payload        TEXT NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    published_at   TIMESTAMP NULL,
    attempts       INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_outbox_pending
    ON outbox_event (published_at, created_at);
```

This is an illustrative schema; UUID, JSON/JSONB, timestamp types, and index syntax should be tailored to your database. In environments with multiple relay instances, you can add `status`, `locked_until`, `lease_owner`, `last_error`, or `next_attempt_at` to manage claiming and retries.

Meaning of key columns:

- `id`: unique event ID, used for tracing and preventing duplicate processing.
- `aggregate_type` and `aggregate_id`: identify the business entity emitting the event.
- `event_type` and `event_version`: inform consumers of the event type and schema version.
- `payload`: serialized event content.
- `created_at`: timestamp when the event was created inside the business transaction.
- `published_at`: timestamp when the relay confirmed Kafka received the event.
- `attempts`: number of publish attempts made by the relay.

Avoid arbitrarily storing an entire JPA entity as the payload. Define a stable event contract containing only the data consumers need, with a schema evolution strategy.

## 5. Writing business data and outbox in the same transaction

The business service does not send to Kafka directly. It saves the entity and an outbox record using the same repository/database transaction:

```java
import java.time.Instant;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderService {

    private final OrderRepository orderRepository;
    private final OutboxRepository outboxRepository;
    private final ObjectMapper objectMapper;

    OrderService(
            OrderRepository orderRepository,
            OutboxRepository outboxRepository,
            ObjectMapper objectMapper) {
        this.orderRepository = orderRepository;
        this.outboxRepository = outboxRepository;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public Order create(CreateOrder command) {
        Order order = Order.create(command);
        orderRepository.save(order);

        var event = new OrderCreated(
                UUID.randomUUID(),
                order.getId(),
                order.getCustomerId(),
                Instant.now());

        outboxRepository.save(OutboxEvent.pending(
                event.eventId(),
                "Order",
                order.getId().toString(),
                "OrderCreated",
                1,
                writeJson(event)));

        return order;
    }

    private String writeJson(Object event) {
        try {
            return objectMapper.writeValueAsString(event);
        }
        catch (JsonProcessingException ex) {
            throw new IllegalStateException("Cannot serialize outbox event", ex);
        }
    }
}
```

`Order`, `OrderCreated`, `OutboxEvent`, repositories, and `ObjectMapper` are illustrative application components. The essential requirement is that both repositories participate in the same database transaction manager and the same transaction. Do not place the outbox in an independent database and assume it commits with the order database.

If event serialization fails, the method throws an exception and the database transaction rolls back. No order is then committed without its corresponding outbox event.

## 6. Relay reads the outbox and publishes to Kafka

A polling relay can run on a schedule, fetch unpublished rows, send them using `KafkaTemplate`, and mark them published once the broker confirms success.

```java
import java.util.concurrent.TimeUnit;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
class OutboxPublisher {

    private final OutboxRepository outboxRepository;
    private final OutboxStatusService statusService;
    private final KafkaTemplate<String, String> kafkaTemplate;

    OutboxPublisher(
            OutboxRepository outboxRepository,
            OutboxStatusService statusService,
            KafkaTemplate<String, String> kafkaTemplate) {
        this.outboxRepository = outboxRepository;
        this.statusService = statusService;
        this.kafkaTemplate = kafkaTemplate;
    }

    @Scheduled(fixedDelayString = "${app.outbox.poll-delay:1000}")
    public void publishPending() {
        for (OutboxEvent event : outboxRepository.findPendingBatch(100)) {
            try {
                kafkaTemplate.send(
                        "domain-events",
                        event.getAggregateId(),
                        event.getPayload()).get(10, TimeUnit.SECONDS);

                statusService.markPublished(event.getId());
            }
            catch (Exception ex) {
                statusService.recordPublishFailure(event.getId(), ex);
            }
        }
    }
}
```

The example uses `get()` to await the send result before marking the outbox row as published. `OutboxStatusService` needs to update status in a separate database transaction. In modern Spring Kafka, `send()` returns `CompletableFuture`; older versions use a different future type, yet all can be awaited via `Future.get()`.

This is a skeleton to explain the flow, not a complete production relay. If multiple instances run simultaneously, `findPendingBatch()` must claim records safely so two instances do not process the same row concurrently. You can use row locking such as `SELECT ... FOR UPDATE SKIP LOCKED`, timed lease states, or an equivalent claim mechanism. Do not hold a database transaction/row lock across the Kafka call if network calls may take long; typically claim in a short transaction, commit the claim, publish externally, and then update the outcome.

When publishing succeeds, set `published_at` or status `PUBLISHED`. When publishing fails, keep the record retryable, increment `attempts`, record the error, and schedule the next attempt with backoff. Have a policy for permanent errors so records are not retried infinitely without attention.

## 7. Why can an Outbox still send duplicates?

An Outbox guarantees the business change and the intent to emit an event commit together. However, the relay and Kafka are still two separate steps. There is a failure window:

1. Kafka confirms the record was written successfully.
2. The relay stops before updating `published_at` in the database.
3. On restart, the relay sees the outbox row is still unpublished and sends the record again.

Therefore, Outbox polling generally provides *at-least-once* semantics: events are not lost if the relay stops before the first publish, yet they can be sent more than once. Do not describe it as end-to-end exactly-once.

Design idempotent consumers so receiving the same event multiple times does not produce duplicate side effects. A common pattern is a `processed_event` table with a unique key on the event ID. Within the same database transaction as the business update, the consumer inserts the event ID; if the ID already exists, it skips the duplicate event.

```java
@Transactional
public void handle(OrderCreated event) {
    boolean firstDelivery = processedEventRepository
            .insertIfAbsent(event.eventId());

    if (!firstDelivery) {
        return;
    }

    inventoryService.reserve(event.orderId());
}
```

`insertIfAbsent` is an illustrative repository operation; implement it with a unique constraint and database-appropriate statement. Recording the processed marker and updating business state must reside in the same transaction. If you record the marker first and update business state in a different transaction, a failure between the two steps could cause the event to be skipped on later delivery.

## 8. Preserving event ordering per aggregate

If multiple events for the same order must be processed in order, the relay should publish with `aggregate_id` as the Kafka key. Kafka routes the same key to the same partition under the standard partitioner, preserving write order within the partition.

However, the key alone does not preserve order if multiple relay instances claim and publish events for the same aggregate concurrently. You can use `aggregate_version` or `sequence_number`, allow publishing the next event only after the previous one is confirmed, or partition relay work by aggregate/partition. Consumers should also inspect versions to detect out-of-order arrivals.

Global ordering across different aggregates is rarely required. Avoid designing a single Kafka key for all events just to achieve global ordering, as that can funnel all load onto a single partition.

## 9. Outbox polling vs. CDC

There are two common ways to move outbox records into Kafka:

| Approach | How it works | Pros | What must be managed |
| --- | --- | --- | --- |
| Polling relay | Application queries pending rows in batches and sends via `KafkaTemplate` | Easy to start, easy to customize business logic and retries | Row claiming, concurrency, backoff, cleanup of published rows, and duplicates |
| Change Data Capture (CDC) | Tools like Debezium read the database transaction log and stream outbox changes to Kafka | No continuous application polling; reads committed changes from the log | Connectors, log-reading permissions, schemas, connector offsets, retention, and CDC infrastructure operations |

With CDC, the application still writes business data and the outbox within the same database transaction. The connector observes committed changes in the transaction log and routes outbox rows into Kafka records, often via Debezium's Outbox Event Router. CDC reduces application-owned relay code, yet still requires idempotent consumers because delivery can repeat when a connector recovers from offsets.

Choose polling when you want to keep mechanisms simple inside the application and outbox load is moderate. Choose CDC when the platform already operates CDC infrastructure or when high throughput, low latency, and decoupling publishing from the application lifecycle are needed.

## 10. Why doesn't an `AFTER_COMMIT` event listener replace Outbox?

Another approach is publishing a Spring application event inside the transaction and using `@TransactionalEventListener(phase = AFTER_COMMIT)` to send to Kafka after the database commits:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCreated(OrderCreated event) {
    kafkaTemplate.send("orders", event.orderId().toString(), event);
}
```

This avoids sending the event before the database transaction commits. However, a gap remains: the database commits, yet the process stops before the callback executes or before the Kafka publish succeeds. An in-memory application event is not a durable queue. If events must not be lost, write an outbox row inside the database transaction instead of relying solely on an after-commit callback.

`AFTER_COMMIT` remains useful for secondary tasks where loss is acceptable or separate recovery exists, such as cache eviction or non-critical notifications. Carefully assess durability requirements before using it.

## 11. When to use Kafka transactions?

Kafka transactions fit when atomicity is needed inside Kafka—for example, a producer writing to multiple topics or a consumer reading a record, writing results to another topic, and committing the offset in the same Kafka transaction. Configuring a producer transaction ID and `KafkaTransactionManager` lets Spring Kafka manage producer transactions; consumers reading transactional data should use `isolation.level=read_committed` when only committed data should be seen.

If the same business operation must update a relational database and send to Kafka, a Kafka transaction alone does not solve dual writes. You can use Outbox so the database transaction saves state alongside the event; a relay later sends the event with a Kafka producer. If the relay needs to publish multiple Kafka records as an atomic group, you can add Kafka transactions for that publish batch, though marking the outbox in the database remains a separate boundary and duplicates must still be handled.

## 12. Testing and operating Outbox

Tests must cover both the happy path and failure points between the two systems:

1. Create an order successfully; verify both `orders` and `outbox_event` rows commit together.
2. Make event serialization or outbox writing fail; verify the database transaction rolls back and the order is not committed.
3. Stop Kafka while the relay is running; verify the outbox row stays pending and is sent once Kafka returns.
4. Simulate the relay stopping after Kafka acknowledges but before marking published; verify duplicates can occur and the idempotent consumer handles them safely.
5. Run multiple relay instances; verify the claim mechanism neither drops records nor publishes out of order for the same aggregate.
6. Emit multiple events for the same aggregate; verify Kafka keys and sequence/version preserve required ordering.
7. Test retries, DLT, and alerts when an outbox row stays unpublished too long.

Metrics to monitor include pending row count, age of the oldest pending row, publish rate, publish failure count, expired-lease row count, time from `created_at` to `published_at`, and duplicates discarded by consumers. Establish a retention/cleanup policy for published outbox rows, deleting only after a window long enough for investigation and replay.

## 13. Solution selection checklist

- [ ] Identified which resources the database transaction and Kafka transaction protect.
- [ ] Not assuming a default `@Transactional` makes database and Kafka commit atomically.
- [ ] If events must not be lost, business data and outbox rows are written in the same database transaction.
- [ ] Relay marks published only after Kafka confirms send success.
- [ ] Relay has a safe claiming mechanism for multi-instance runs and backoff on publish failures.
- [ ] Consumer has an idempotency key and saves processed state in the same business transaction.
- [ ] Kafka key/aggregate sequence is designed when ordering is required.
- [ ] Monitoring covers outbox backlog, event age, publish failures, and duplicates.
- [ ] Failure tests cover gaps between database commit, Kafka publish, and outbox status update.

When the database and Kafka do not share a distributed transaction, Transactional Outbox is a practical way to avoid losing the intent to emit events. The database commits business state and outbox together; the relay delivers events at-least-once; idempotent consumers handle redeliveries. These three parts work together to build reliable messaging without assuming two systems share one local transaction.
